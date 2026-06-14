"""Intake & Normalizer Agent (Agent 1).

Receives user messages, normalizes shorthand, resolves NL, logs AI calls, and escalates when confidence is low.
"""

import json
import os
import uuid
from datetime import date
from mysql.connector import Error
from app.data.database import get_db_connection
from app.services.nlp import parse_message
from app.services.utils import parse_shorthand
from app.agents.band import get_band_client

# Band room handles (WP-03). Agents coordinate by @mention in a shared room instead of
# the retired in-memory BandSDK broker. Ledger/CFO consume these once WP-04/05 land; the
# webhook→room gateway is wired in WP-06.
INTAKE_HANDLE = "@tali-intake"
LEDGER_HANDLE = "@tali-ledger"
CFO_HANDLE = "@tali-cfo"
HUMAN_HANDLE = "@tali-human"   # the human approver, surfaced in-room (WP-08)

# Intents that mutate the ledger and therefore require an explicit confirmation.
MUTATING_INTENTS = {'record_transaction', 'inventory', 'debt'}
CONFIRM_YES = {'yes', 'y', 'yeah', 'yep', 'ok', 'okay', 'confirm', 'correct', 'sure', '✅'}
CONFIRM_NO = {'no', 'n', 'nope', 'cancel', 'stop', '❌'}

# Replies that answer the "chat or PDF?" question for a pending statement.
FORMAT_REPLIES = {
    '1': 'chat', 'chat': 'chat', 'text': 'chat', 'message': 'chat', 'summary': 'chat',
    '2': 'pdf', 'pdf': 'pdf', 'document': 'pdf', 'doc': 'pdf',
    '3': 'xlsx', 'excel': 'xlsx', 'xlsx': 'xlsx', 'spreadsheet': 'xlsx', 'sheet': 'xlsx',
    'both': 'both', 'all': 'both',
}

# Signals that a "report"-ish message actually wants a downloadable, filtered
# document (statement intent) rather than the legacy quick text summary — so it
# must skip the report fast-path and go to the NLP layer for filter parsing.
_MONTH_WORDS = ('january', 'february', 'march', 'april', 'may', 'june', 'july',
                'august', 'september', 'october', 'november', 'december',
                'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept',
                'oct', 'nov', 'dec')
_STATEMENT_WORDS = ('statement', 'cashflow', 'cash flow', 'pdf', 'excel',
                    'spreadsheet', 'export', 'download', 'purchases', 'sales')


def _wants_statement(text_lower):
    """True if a report-ish message has document/filter signals (date range,
    month name, format keyword, or an explicit statement word)."""
    if any(w in text_lower for w in _STATEMENT_WORDS):
        return True
    if any(w in text_lower for w in _MONTH_WORDS):
        return True
    if ' to ' in text_lower or ' from ' in text_lower or ' for ' in text_lower:
        return True
    return False


def _items_missing_amount(parsed):
    """Return human labels for parsed sales/debts that have no price yet.

    A compound message like 'sold 2 bags of water, 5 crates of malt on credit'
    parses cleanly but carries no amounts — those can't be recorded, so we ask
    the user for the prices instead of failing the whole message.
    """
    labels = []
    # map product -> "qty unit product" from the inventory side, for nicer labels
    inv_by_product = {}
    for inv in parsed.get('inventory') or []:
        prod = (inv.get('product') or '').lower()
        if prod:
            qty = inv.get('quantity')
            unit = inv.get('unit')
            qty_str = (f"{int(qty)} " if isinstance(qty, (int, float)) and float(qty).is_integer()
                       else (f"{qty} " if qty is not None else ""))
            inv_by_product[prod] = f"{qty_str}{(unit + ' of ') if unit else ''}{prod}".strip()

    for tx in parsed.get('transactions') or []:
        if tx.get('amount') in (None, 0):
            item = (tx.get('item') or '').lower()
            labels.append(inv_by_product.get(item) or tx.get('item') or tx.get('description') or 'an item')
    for debt in parsed.get('debts') or []:
        if debt.get('action') != 'full_payment' and debt.get('amount') in (None, 0):
            who = debt.get('name') or 'someone'
            labels.append(f"debt for {who}")
    return labels


class IntakeAgent:
    """Agent 1 — Intake & Normalizer. Processes raw inputs and dispatches payloads
    into the shared Band room via the connector (WP-03)."""

    def __init__(self, user_id, sender_id, band=None):
        self.user_id = user_id
        self.sender_id = sender_id
        # Band connector (WP-03). Defaults to the configured backend (stub offline,
        # live in prod); injectable for tests. One room per sender for now.
        self.band = band if band is not None else get_band_client()
        self.room_id = os.getenv("BAND_ROOM_ID") or f"tali-{sender_id}"
        self._reply_timeout = float(os.getenv("BAND_REPLY_TIMEOUT", "8"))

    def _band_send_collect(self, mentions, payload):
        """Send an event into the room (fire-and-forget) and block for the terminal
        reply via the reply-collection seam (G-05). Returns the reply text or None.

        Replaces the old synchronous ``BandSDK.publish(...)[0]`` return: Band send has
        no return value, so the answer is collected out-of-band by ``correlation_id``.
        Until WP-04/05 register the Ledger/CFO handlers and WP-06 wires the gateway,
        this returns None in-app (no handler), which callers degrade gracefully.
        """
        correlation_id = uuid.uuid4().hex
        self.band.send(self.room_id, mentions, payload,
                       correlation_id=correlation_id, sender=INTAKE_HANDLE)
        return self.band.collect_reply(correlation_id, timeout=self._reply_timeout)

    def process(self, text):
        """Standard intake entry point for routing WhatsApp messages."""
        import re
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        # Pending gates: a YES/NO commits or discards a pending parsed write; a
        # format word (chat/pdf/excel/1/2/3) answers a pending "chat or PDF?"
        # statement question. Both are checked before anything else.
        if text_lower in CONFIRM_YES or text_lower in CONFIRM_NO or text_lower in FORMAT_REPLIES:
            pending = self._load_pending()
            if pending:
                pj = pending['parsed_json']
                pj = pj if isinstance(pj, dict) else json.loads(pj)
                if pj.get('awaiting') == 'statement_format':
                    return self._apply_format_choice(text_lower, pj)
                if text_lower in CONFIRM_YES or text_lower in CONFIRM_NO:
                    return self._apply_confirmation(text_lower, pending)

        # Define regex matchers upfront to enforce strict priority
        inv_match_add = re.match(r'^(?:add|added)\s+(\d+(?:\.\d+)?)\s+(?:bags\s+of\s+|units\s+of\s+)?(\w+)$', text_lower)
        inv_match_remove = re.match(r'^(?:remove|removed)\s+(\d+(?:\.\d+)?)\s+(?:bags\s+of\s+|units\s+of\s+)?(\w+)$', text_lower)
        inv_match_set = re.match(r'^set\s+(\w+)\s+(?:to\s+)?(\d+(?:\.\d+)?)$', text_lower)

        debt_match_owes = re.match(r'^(\w+)\s+(?:owes|credit)\s+(\d+(?:\.\d+)?[kh]?)$', text_lower)
        debt_match_repay = re.match(r'^(?:repay|repayment)\s+(\w+)\s+(\d+(?:\.\d+)?[kh]?)$', text_lower)
        debt_match_paid = re.match(r'^(\w+)\s+(?:paid|repaid)\s+(\d+(?:\.\d+)?[kh]?)$', text_lower)

        tx_match_sold = re.match(r'^(sold|sell|sale)\s+(\w+)\s+(\d+(?:\.\d+)?[kh]?)$', text_lower)
        tx_match_bought = re.match(r'^(bought|buy|purchase)\s+(\w+)\s+(\d+(?:\.\d+)?[kh]?)$', text_lower)
        tx_match_spent = re.match(r'^spent\s+(\d+(?:\.\d+)?[kh]?)\s+on\s+(\w+)$', text_lower)

        # 1. System Queries (Snapshot, Reports, FinOps)
        if any(kw in text_lower for kw in ('snapshot', 'health', 'how is my business', 'how is the business')):
            payload = {
                "intents": ["snapshot"],
                "confidence": 1.0,
                "needs_review": False,
                "status": "ok",
                "snapshot": True
            }
            results = self._publish_intake(
                intent="snapshot",
                extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                confidence=1.0
            )
            return results[0] if results else "❌ Snapshot failed."

        elif any(kw in text_lower for kw in ('cost', 'billing', 'finops', 'api spend')):
            payload = {
                "intents": ["report"],
                "confidence": 1.0,
                "needs_review": False,
                "status": "ok",
                "report": {
                    "period": "finops",
                    "date": None
                }
            }
            results = self._publish_intake(
                intent="report",
                extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                confidence=1.0
            )
            return results[0] if results else "❌ FinOps report failed."

        elif any(kw in text_lower for kw in ('report', 'summary', 'monthly', 'weekly', 'daily', 'cfo')) and not _wants_statement(text_lower):
            period = 'monthly'
            if 'daily' in text_lower:
                period = 'daily'
            elif 'weekly' in text_lower:
                period = 'weekly'

            payload = {
                "intents": ["report"],
                "confidence": 1.0,
                "needs_review": False,
                "status": "ok",
                "report": {
                    "period": period,
                    "date": None
                }
            }
            results = self._publish_intake(
                intent="report",
                extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                confidence=1.0
            )
            return results[0] if results else "❌ Report failed."

        # 2. Inventory (Stock levels)
        elif inv_match_add or inv_match_remove or inv_match_set:
            if inv_match_add:
                inv_action = 'ADD'
                qty_str = inv_match_add.group(1)
                product = inv_match_add.group(2)
                unit = 'bags' if 'bags' in text_lower else None
            elif inv_match_remove:
                inv_action = 'REMOVE'
                qty_str = inv_match_remove.group(1)
                product = inv_match_remove.group(2)
                unit = 'bags' if 'bags' in text_lower else None
            else:
                inv_action = 'SET'
                product = inv_match_set.group(1)
                qty_str = inv_match_set.group(2)
                unit = None

            try:
                qty = float(qty_str)
                payload = {
                    "intents": ["inventory"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "inventory": {
                        "action": inv_action,
                        "product": product,
                        "quantity": qty,
                        "unit": unit
                    }
                }
                results = self._publish_intake(
                    intent="inventory",
                    extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                    confidence=1.0
                )
                return results[0] if results else "❌ Inventory update failed."
            except ValueError:
                pass

        # 3. Debt (Receivables/Payables)
        elif debt_match_owes or debt_match_repay or debt_match_paid:
            if debt_match_owes:
                debt_action = 'add_debt'
                name = debt_match_owes.group(1)
                amount_str = debt_match_owes.group(2)
                debt_type = 'customer_debt'
            elif debt_match_repay:
                debt_action = 'repayment'
                name = debt_match_repay.group(1)
                amount_str = debt_match_repay.group(2)
                debt_type = 'customer_debt'
            else:
                debt_action = 'repayment'
                name = debt_match_paid.group(1)
                amount_str = debt_match_paid.group(2)
                debt_type = 'customer_debt'

            amount = parse_shorthand(amount_str)
            if amount > 0:
                payload = {
                    "intents": ["debt"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "debt": {
                        "action": debt_action,
                        "name": name,
                        "type": debt_type,
                        "amount": amount,
                        "currency": "NGN"
                    }
                }
                results = self._publish_intake(
                    intent="debt",
                    extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                    confidence=1.0
                )
                return results[0] if results else "❌ Debt update failed."

        # 4. Fast-path Shorthand
        elif self._is_shorthand(text):
            amount = parse_shorthand(text)
            if amount > 0:
                payload = {
                    "intent": "record_transaction",
                    "type": "expense",
                    "action": "expense",
                    "amount": amount,
                    "currency": "NGN",
                    "item": None,
                    "category": "Miscellaneous",
                    "description": text_stripped,
                    "date": date.today().isoformat(),
                    "raw_text": text,
                    "is_fast_path": True
                }
                results = self._publish_intake(
                    intent="record_transaction",
                    extracted_data=payload,
                    confidence=1.0
                )
                return results[0] if results else "❌ Shorthand processing failed."

        # 5. Transactions
        elif tx_match_sold or tx_match_bought or tx_match_spent:
            if tx_match_sold:
                action = 'sale'
                tx_type = 'income'
                item = tx_match_sold.group(2)
                amount_str = tx_match_sold.group(3)
                category = 'Sales'
            elif tx_match_bought:
                action = 'purchase'
                tx_type = 'expense'
                item = tx_match_bought.group(2)
                amount_str = tx_match_bought.group(3)
                category = item.title() if item.title() in ('Fuel', 'Transport', 'Rent', 'Salary', 'Utilities', 'Food', 'Shopping') else 'Other'
            else:
                action = 'expense'
                tx_type = 'expense'
                amount_str = tx_match_spent.group(1)
                item = tx_match_spent.group(2)
                category = item.title() if item.title() in ('Fuel', 'Transport', 'Rent', 'Salary', 'Utilities', 'Food', 'Shopping') else 'Other'

            amount = parse_shorthand(amount_str)
            if amount > 0:
                payload = {
                    "intents": ["record_transaction"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "transaction": {
                        "type": tx_type,
                        "action": action,
                        "amount": amount,
                        "currency": "NGN",
                        "item": item,
                        "category": category,
                        "description": text_stripped,
                        "date": date.today().isoformat()
                    }
                }
                results = self._publish_intake(
                    intent="record_transaction",
                    extracted_data={"parsed": payload, "raw_text": text, "is_fast_path": False},
                    confidence=1.0
                )
                return results[0] if results else "❌ Transaction failed."

        # 6. Fallback LLM Classification
        import time
        start_time = time.time()
        
        parsed = None
        retry_count = 3
        for attempt in range(retry_count):
            try:
                parsed = parse_message(text, self.user_id)
                from app.services.validators import UnifiedResponseModel, dump_model
                validated = UnifiedResponseModel(**parsed)
                parsed = dump_model(validated)
                break
            except Exception as e:
                print(f"NLP Attempt {attempt + 1} validation failed: {e}")
                parsed = None
        
        end_time = time.time()
        processing_time_ms = int((end_time - start_time) * 1000)

        if not parsed:
            parsed = {
                "intents": ["unknown"],
                "confidence": 0.0,
                "needs_review": True,
                "status": "error",
                "reply": "⚠️ The intelligence service is temporarily unavailable."
            }

        # Prefer the router's accurate per-provider cost (WP-10); fall back to OpenAI rates.
        from flask import current_app
        meta = parsed.get('_meta') or {}
        if meta.get('estimated_cost') is not None:
            estimated_cost = float(meta['estimated_cost'])
        else:
            input_rate = current_app.config.get('OPENAI_INPUT_COST_PER_MILLION', 0.15)
            output_rate = current_app.config.get('OPENAI_OUTPUT_COST_PER_MILLION', 0.60)
            usage = parsed.get('_usage', {})
            estimated_cost = (usage.get('prompt_tokens', 0) * input_rate / 1_000_000) + \
                             (usage.get('completion_tokens', 0) * output_rate / 1_000_000)

        self._log_ai_interaction(text, parsed, processing_time_ms, estimated_cost)

        if parsed.get('status') == 'clarification_needed':
            return parsed.get('question', "Please clarify your request.")

        confidence = parsed.get('confidence', 1.0)
        needs_review = parsed.get('needs_review', False)

        if confidence < 0.7 or needs_review:
            self._log_to_review_queue(text, parsed)
            # Build a friendly, human-readable reply — never surface raw JSON to
            # the user. An NLP/parse error gets a "try again" note; an otherwise
            # unparseable message (e.g. a greeting like "Hi") gets a gentle nudge
            # toward what TaLi can actually do.
            if parsed.get('status') == 'error':
                question = (parsed.get('reply')
                            or "⚠️ I'm having trouble understanding right now. Please try again in a moment.")
            else:
                question = (
                    "🤔 I didn't quite catch that. Tell me a transaction like "
                    "\"Sold rice 5000\" or \"Bought fuel 2k\", or ask \"What's my balance?\".\n\n"
                    "Type *help* to see everything I can do."
                )

            from app.agents.event_schemas import CFOEscalationEvent, CFOEscalationEventPayload
            from app.auth import get_active_session
            session = get_active_session(self.sender_id)
            session_id = str(session['id']) if session else None
            business_id = session.get('business_id', 1) if session and 'business_id' in session else 1

            event = CFOEscalationEvent(
                user_id=self.user_id,
                session_id=session_id,
                business_id=business_id,
                source_agent="IntakeAgent",
                event_type="error",
                payload=CFOEscalationEventPayload(
                    status="needs_review",
                    message=question,
                    raw_text=text,
                    parsed=parsed
                )
            )
            reply = self._band_send_collect([CFO_HANDLE], event.model_dump(mode='json'))
            # Never dump raw JSON to the user — fall back to the human message.
            return reply if reply else question


        # Missing-price guard: a clear parse that names items/debts but has no
        # amount can't be recorded. Ask for the prices instead of the old vague
        # "intelligence service unavailable" failure.
        if MUTATING_INTENTS.intersection(parsed.get('intents', [])):
            missing = _items_missing_amount(parsed)
            if missing:
                bullets = "\n".join(f"• {m}" for m in missing)
                return (
                    "📝 I understood your entry, but I need the *price* for each before I can record it:\n\n"
                    f"{bullets}\n\n"
                    "Please resend with the amounts included, e.g. "
                    "_\"Sold 2 bags of water 3000, 5 crates of malt 13000, 1 bag of rice 70000 on credit to Mr Amadi\"_."
                )

        # Statement/report: read-only, handled here directly rather than via the
        # ledger (which only knows mutating/text intents). If the user didn't
        # name a delivery format, ask "chat or PDF?" first and hold the request.
        if 'statement' in parsed.get('intents', []) and parsed.get('statement'):
            statement = dict(parsed['statement'])
            if not statement.get('format'):
                question = self._ask_statement_format(text, statement)
                if question:
                    return question
                statement['format'] = 'pdf'  # couldn't hold the request — sensible default
            return self._run_statement(statement, raw_text=text)

        # Confirm-before-record: any LLM-parsed write (transaction/inventory/debt)
        # is held as pending and shown back to the user for a YES/NO. Read-only
        # intents (query/report/snapshot) fall through and run immediately.
        if MUTATING_INTENTS.intersection(parsed.get('intents', [])):
            prompt = self._store_pending(text, parsed)
            if prompt:
                return prompt

        results = self._publish_intake(
            intent="split_routing",
            extracted_data={"parsed": parsed, "raw_text": text, "is_fast_path": False},
            confidence=parsed.get('confidence', 1.0)
        )
        return results[0] if results else "❌ Ledger processing failed."

    def _run_statement(self, statement, raw_text=''):
        """Generate/deliver a statement. After an in-chat render, re-hold the
        request so a follow-up 'pdf'/'excel' upgrades it to a file."""
        from app.agents.statement_agent import StatementAgent
        reply = StatementAgent(self.user_id, self.sender_id).generate_and_send(statement)
        if statement.get('format') == 'chat':
            self._store_pending_json(raw_text or 'statement', {
                'awaiting': 'statement_format', 'statement': statement,
            })
        return reply

    def _ask_statement_format(self, text, statement):
        """Hold a formatless statement request and ask chat-or-PDF.
        Returns the question, or None if the request couldn't be held."""
        from app.agents.statement_agent import describe
        held = self._store_pending_json(text, {
            'awaiting': 'statement_format', 'statement': statement,
        })
        if not held:
            return None
        title, period = describe(statement)
        return (
            f"📊 *{title}* — {period}\n\n"
            "How would you like it?\n\n"
            "1️⃣ Chat summary\n"
            "2️⃣ PDF document\n"
            "3️⃣ Excel spreadsheet\n\n"
            "Reply *1*, *2* or *3*."
        )

    def _apply_format_choice(self, text_lower, pj):
        """Resolve a reply to a pending 'chat or PDF?' statement question."""
        fmt = FORMAT_REPLIES.get(text_lower)
        if not fmt:
            if text_lower in CONFIRM_NO:
                self._clear_pending()
                return "❌ Okay — report cancelled."
            # A bare 'yes'/'ok' doesn't pick a format; nudge once more.
            return ("Which format would you like?\n\n"
                    "1️⃣ Chat summary\n2️⃣ PDF document\n3️⃣ Excel spreadsheet\n\n"
                    "Reply *1*, *2* or *3*.")
        self._clear_pending()
        statement = dict(pj.get('statement') or {})
        statement['format'] = fmt
        return self._run_statement(statement)

    def _post_human_event(self, body):
        """Surface a human-in-the-loop event in the Band room (fire-and-forget) so the
        approval is visible + auditable (WP-08). The durable gate stays `pending_confirmations`."""
        try:
            self.band.send(self.room_id, [HUMAN_HANDLE], body, sender=INTAKE_HANDLE)
        except Exception as e:
            print(f"[IntakeAgent human-loop post failed] {e}")

    def _store_pending(self, text, parsed):
        """Persist a parsed write awaiting confirmation; return the breakdown prompt."""
        from app.services.formatter import format_confirmation
        prompt = format_confirmation(parsed)
        if not prompt:
            return None
        if self._store_pending_json(text, parsed):
            # Human-in-the-loop (WP-08): record that a human's approval is required, in-room.
            self._post_human_event({"type": "approval_request", "summary": prompt, "raw_text": text})
            return prompt
        return None  # fall through to record directly rather than lose the entry

    def _store_pending_json(self, text, payload):
        """Upsert this sender's pending row (confirmation or format question).
        Returns True on success."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            from app.services.uuid_utils import uuid7, uuid_to_bin
            cursor.execute(
                "INSERT INTO pending_confirmations (id, user_id, sender_id, raw_text, parsed_json, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE)) "
                "ON DUPLICATE KEY UPDATE id = VALUES(id), user_id = VALUES(user_id), "
                "raw_text = VALUES(raw_text), parsed_json = VALUES(parsed_json), "
                "created_at = NOW(), expires_at = VALUES(expires_at)",
                (uuid7().bytes, uuid_to_bin(self.user_id), self.sender_id, text[:500], json.dumps(payload))
            )
            conn.commit()
        except Error as e:
            print(f"Error storing pending payload: {e}")
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
        return True

    def _load_pending(self):
        """Return the sender's unexpired pending confirmation row, or None."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT raw_text, parsed_json FROM pending_confirmations "
                "WHERE sender_id = %s AND expires_at > NOW() LIMIT 1",
                (self.sender_id,)
            )
            return cursor.fetchone()
        except Error as e:
            print(f"Error loading pending confirmation: {e}")
            return None
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _clear_pending(self):
        """Remove any pending confirmation for this sender."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_confirmations WHERE sender_id = %s", (self.sender_id,))
            conn.commit()
        except Error as e:
            print(f"Error clearing pending confirmation: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _apply_confirmation(self, decision, pending):
        """Commit (YES) or discard (NO) a pending parsed write."""
        self._clear_pending()
        # Human-in-the-loop (WP-08): record the human's decision in-room for the audit trail.
        self._post_human_event({"type": "human_decision",
                                "decision": "rejected" if decision in CONFIRM_NO else "approved"})
        if decision in CONFIRM_NO:
            return "❌ Cancelled — nothing was recorded. Send it again to retry."

        pj = pending['parsed_json']
        parsed = pj if isinstance(pj, (dict, list)) else json.loads(pj)
        results = self._publish_intake(
            intent="split_routing",
            extracted_data={"parsed": parsed, "raw_text": pending['raw_text'], "is_fast_path": False},
            confidence=parsed.get('confidence', 1.0)
        )
        return results[0] if results else "❌ Ledger processing failed."

    def _is_shorthand(self, text):
        """Determines if a message is a single-word numeric shorthand."""
        text_stripped = text.strip()
        if len(text_stripped.split()) != 1:
            return False
        return (
            text_stripped.replace('.', '', 1).replace('k', '', 1).replace('h', '', 1).isdigit() or
            text_stripped.lower().endswith('k') or
            text_stripped.lower().endswith('h')
        )

    def _log_ai_interaction(self, text, parsed, processing_time_ms, estimated_cost):
        """Audits the prompt content and parsed outputs into ai_logs."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            from app.services.uuid_utils import uuid_to_bin
            user_id_bin = uuid_to_bin(self.user_id)
            cursor.execute("SELECT business_id FROM users WHERE id = %s LIMIT 1", (user_id_bin,))
            user_row = cursor.fetchone()
            business_id = user_row['business_id'] if user_row and user_row['business_id'] is not None else None

            intents = parsed.get('intents', [])
            intent = intents[0] if intents else 'unknown'
            
            parsed_clean = parsed.copy()
            parsed_clean.pop('_usage', None)
            parsed_clean.pop('_meta', None)
            # Record the model the router actually used (WP-10), not a hardcoded one.
            model_used = (parsed.get('_meta') or {}).get('model') or 'gpt-4o-mini'

            cursor.execute(
                "INSERT INTO ai_logs (user_id, business_id, source_agent, model_name, original_message, parsed_intent, parsed_json, confidence_score, estimated_cost, processing_time_ms) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id_bin,
                    business_id,
                    "IntakeAgent",
                    model_used,
                    text,
                    intent,
                    json.dumps(parsed_clean),
                    parsed.get('confidence', 1.0),
                    estimated_cost,
                    processing_time_ms
                )
            )
            conn.commit()
        except Error as e:
            print(f"Error logging to ai_logs: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _log_to_review_queue(self, text, parsed):
        """Registers a complex or low-confidence task into review_queue."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            parsed_clean = parsed.copy()
            parsed_clean.pop('_usage', None)
            from app.services.uuid_utils import uuid7, uuid_to_bin
            rq_uuid = uuid7()
            cursor.execute(
                "INSERT INTO review_queue (id, user_id, raw_text, parsed_payload) VALUES (%s, %s, %s, %s)",
                (rq_uuid.bytes, uuid_to_bin(self.user_id), text, json.dumps(parsed_clean))
            )
            conn.commit()
        except Error as e:
            print(f"Error logging to review queue: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _publish_intake(self, intent, extracted_data, confidence):
        """Serialize and publish intake payload using IntakePayload Pydantic model."""
        from app.services.validators import UnifiedResponseModel, TransactionModel
        from app.auth import get_active_session
        from app.agents.event_schemas import IntakePayload, IntakeEventPayload
        
        session = get_active_session(self.sender_id)
        session_id = str(session['id']) if session else None
        business_id = session.get('business_id', 1) if session and 'business_id' in session else 1
        
        if intent == 'record_transaction':
            event_type = 'transaction'
        elif intent == 'inventory':
            event_type = 'inventory'
        elif intent == 'debt':
            event_type = 'debt'
        elif intent in ('report', 'snapshot'):
            event_type = 'report'
        else:
            event_type = 'transaction'

        is_fast_path = extracted_data.get('is_fast_path', False)
        raw_text = extracted_data.get('raw_text', '')

        fast_path_tx = None
        nlp_parsed = None

        if is_fast_path:
            fast_path_tx = TransactionModel(**extracted_data)
            raw_text = extracted_data.get('description', '')
        else:
            parsed_data = extracted_data.get('parsed', {})
            nlp_parsed = UnifiedResponseModel(**parsed_data)

        event = IntakePayload(
            user_id=self.user_id,
            session_id=session_id,
            business_id=business_id,
            source_agent="IntakeAgent",
            event_type=event_type,
            payload=IntakeEventPayload(
                intent=intent,
                confidence_score=confidence,
                raw_text=raw_text,
                is_fast_path=is_fast_path,
                fast_path_transaction=fast_path_tx,
                nlp_parsed=nlp_parsed
            )
        )
        # Hand off to the Ledger agent in the room; the reply is collected out-of-band.
        # Callers keep their `results[0] if results else ...` shape, so wrap as a list.
        reply = self._band_send_collect([LEDGER_HANDLE], event.model_dump(mode='json'))
        return [reply] if reply is not None else []
