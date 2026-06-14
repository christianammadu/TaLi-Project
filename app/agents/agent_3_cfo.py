"""CFO & Escalation Agent (Agent 3).

Listens continuously to ledger updates, executes alert queries, generates snapshots, and builds user-facing WhatsApp text.
"""

import json
import os
from app.agents.reporting_agent import ReportingAgent
from app.agents.snapshot_agent import SnapshotAgent
from app.agents.band import get_band_client

# Band room handles (WP-05). CFO is the terminal participant: it composes the final
# user-facing reply from room context and posts it back for the gateway to collect.
CFO_HANDLE = "@tali-cfo"
GATEWAY_HANDLE = "@tali-gateway"


class CFOAgent:
    """Agent 3 — CFO & Escalation. Formats final message replies and executes reporting queries."""

    def __init__(self, user_id, sender_id, band=None):
        self.user_id = user_id
        self.sender_id = sender_id
        # Band connector (WP-05); injectable for tests. One room per sender for now.
        self.band = band if band is not None else get_band_client()
        self.room_id = os.getenv("BAND_ROOM_ID") or f"tali-{sender_id}"

    def on_room_message(self, msg):
        """Band room handler (wired by WP-06): compose the final user-facing reply from the
        room event and post it terminally so the gateway/Intake collects it. Reply ownership
        lives with this CFO→gateway seam (G-11), not the out-of-band send_reply path."""
        body = msg.get("body") or {}
        reply = self._synthesize(self._compose_reply(body))
        self.band.send(self.room_id, [GATEWAY_HANDLE], reply,
                       correlation_id=msg.get("correlation_id"), sender=CFO_HANDLE, terminal=True)
        return reply

    def _compose_reply(self, body):
        """Route a room event to the right formatter and return user-facing text."""
        payload = body.get("payload") or {}
        if body.get("source_agent") == "IntakeAgent":      # low-confidence escalation
            return self.handle_escalation(body)
        status = payload.get("status")
        if status == "rejected":                           # Compliance veto (WP-07)
            reason = payload.get("error_reason") or "compliance hold"
            return f"🛑 Not recorded — {reason}."
        if status == "error":                              # dead-letter / DB failure
            return ("⚠️ I understood your request, but saving it failed (a temporary issue). "
                    "Please try again.")
        return self.handle_ledger_update(body)

    def _synthesize(self, reply):
        """Optional AI/ML ('cfo' role) rephrase of the final wording. Off by default —
        deterministic formatting is the source of truth; enable with CFO_LLM_SYNTHESIS=true."""
        if os.getenv("CFO_LLM_SYNTHESIS", "false").lower() != "true":
            return reply
        try:
            from app.services import model_router
            res = model_router.chat_completion("cfo", messages=[
                {"role": "system", "content": "Rephrase this WhatsApp bookkeeping reply to be "
                 "concise and friendly. Keep every figure, emoji and fact identical."},
                {"role": "user", "content": reply},
            ], temperature=0.2, max_tokens=300)
            return res.get("content") or reply
        except Exception as e:
            print(f"[CFOAgent synthesis fallback] {e}")
            return reply

    def handle_ledger_update(self, payload):
        """Processes database updates and formats user response alerts."""
        # Deserialize and validate strict LedgerUpdateEvent
        from app.agents.event_schemas import LedgerUpdateEvent
        from app.data.database import get_db_connection
        from mysql.connector import Error
        try:
            if isinstance(payload, dict):
                event = LedgerUpdateEvent.model_validate(payload)
            else:
                event = payload
        except Exception as ve:
            print(f"[CFOAgent Schema Error] Invalid LedgerUpdateEvent: {ve}")
            return "❌ Validation Error: Event payload format invalid."

        # Idempotency Check: prevent duplicate alerts (Epic 4)
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT event_id FROM processed_events WHERE event_id = %s AND agent_name = 'CFOAgent' LIMIT 1",
                (str(event.event_id),)
            )
            if cursor.fetchone():
                return "✅ Already processed (idempotency drop)."

            # Record CFO idempotency
            cursor.execute(
                "INSERT INTO processed_events (event_id, agent_name) VALUES (%s, 'CFOAgent')",
                (str(event.event_id),)
            )
            conn.commit()
        except Error as err:
            print(f"[CFOAgent Idempotency Error] {err}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

        intent = event.payload.intent
        data_obj = event.payload.data

        if intent == 'snapshot':
            snapshot_agent = SnapshotAgent(self.user_id)
            return snapshot_agent.generate_snapshot()

        elif intent == 'report':
            period = 'monthly'
            target_date = None
            if data_obj and data_obj.report:
                period = data_obj.report.period or 'monthly'
                target_date = data_obj.report.date
            reporting_agent = ReportingAgent(self.user_id)
            if period == 'finops':
                # Return FinOps aggregation cost summary report
                return reporting_agent.generate_finops_report()
            return reporting_agent.generate_report(period, target_date)

        # Standard record transaction confirmation (fast path — single tx in the list)
        if intent == 'record_transaction':
            txs = data_obj.transactions if data_obj else []
            tx = txs[0] if txs else None
            thresholds = self._get_evaluated_thresholds()
            large_expense_flag = thresholds['large_expense_flag']
            amount = float(tx.amount) if tx else 0.0

            warnings = []
            if tx and tx.type == 'expense' and amount >= large_expense_flag:
                warnings.append(f"🔔 High Expense Alert: recorded expense of ₦{int(amount):,} exceeds flag limit (₦{int(large_expense_flag):,}).")

            reply = f"✅ Recorded: {tx.category if tx else 'Expense'} — ₦{int(tx.amount if tx else 0):,}"
            if warnings:
                reply += "\n\n" + "\n".join(warnings)
            return reply

        elif intent == 'split_routing':
            thresholds = self._get_evaluated_thresholds()
            low_stock_limit = thresholds['low_stock_limit']
            high_debt_limit = thresholds['high_debt_limit']
            large_expense_flag = thresholds['large_expense_flag']

            txs = data_obj.transactions if data_obj else []
            invs = data_obj.inventory if data_obj else []
            debts = data_obj.debts if data_obj else []

            # Resolve internal clarifications nested in any sub-result first
            for sub_result in (*txs, *invs, *debts):
                if sub_result and getattr(sub_result, 'status', None) == 'clarification_needed':
                    return getattr(sub_result, 'question', None) or getattr(sub_result, 'message', None) or "Could you clarify that, please?"

            warnings = []
            for inv in invs:
                if inv.status != 'clarification_needed' and inv.new_stock <= low_stock_limit:
                    warnings.append(f"⚠️ Warning: stock of '{inv.product}' is low ({int(inv.new_stock)} left).")
            for debt in debts:
                if debt.new_balance > high_debt_limit:
                    warnings.append(f"📈 Alert: '{debt.name}' outstanding debt is high (₦{int(debt.new_balance):,}).")
            for tx in txs:
                amount = float(tx.amount)
                if tx.type == 'expense' and amount >= large_expense_flag:
                    warnings.append(f"🔔 High Expense Alert: recorded expense of ₦{int(amount):,} exceeds flag limit (₦{int(large_expense_flag):,}).")

            reply_lines = []
            for tx in txs:
                reply_lines.append(f"✅ Recorded: {tx.category} — ₦{int(tx.amount):,}")
            for inv in invs:
                reply_lines.append(f"📦 Inventory Updated: {inv.product} stock level is now {int(inv.new_stock)} {inv.unit or 'units'}.")
            for debt in debts:
                action_lbl = "repaid" if debt.action == 'repayment' else "owes"
                reply_lines.append(f"👥 Debt Ledger: {debt.name} {action_lbl} ₦{int(debt.amount):,}. Outstanding: ₦{int(debt.new_balance):,}.")

            if warnings:
                reply_lines.append("")
                reply_lines.extend(warnings)

            if not reply_lines:
                return "✅ Got it — I processed that, but there's nothing to show for it."

            return "\n".join(reply_lines)

        return "✅ Got it."

    def handle_escalation(self, payload):
        """Processes Agent 1 escalations — returns the human-readable message,
        never the raw event payload."""
        from app.agents.event_schemas import CFOEscalationEvent
        try:
            if isinstance(payload, dict):
                event = CFOEscalationEvent.model_validate(payload)
            else:
                event = payload
            msg = getattr(event.payload, 'message', None)
            return msg or "🤔 I didn't quite catch that. Type *help* to see what I can do."
        except Exception as ve:
            print(f"[CFOAgent Escalation Error] Invalid CFOEscalationEvent: {ve}")
            return "⚠️ Something went wrong understanding that. Please try again."


    def handle_ledger_error(self, payload):
        """Read-Only Compensation Handler for Dead-Letter Saga channel."""
        from app.agents.event_schemas import LedgerUpdateEvent
        from app.channels.registry import send_text   # reply on the originating channel (WP-05)
        try:
            if isinstance(payload, dict):
                event = LedgerUpdateEvent.model_validate(payload)
            else:
                event = payload
            print(f"[CFOAgent Dead-Letter Saga] Transaction failed: {event.payload.error_reason}")
        except Exception as ve:
            print(f"[CFOAgent Schema Error] Invalid LedgerUpdateEvent on ledger_errors: {ve}")
            
        msg = "⚠️ I understood your request, but our database encountered a temporary lock. Your transaction was not saved. Please try again."
        send_text(self.sender_id, msg)
        return msg

    def _get_evaluated_thresholds(self):
        """Resolves alert thresholds using the Override Hierarchy:
        1. System Defaults -> 2. User Thresholds -> 3. Adaptive Adjustments (LLM placeholder).
        """
        from flask import current_app
        from app.data.database import get_db_connection
        
        # 1. System Defaults
        thresholds = {
            "low_stock_limit": float(current_app.config.get("DEFAULT_LOW_STOCK_LIMIT", 5)),
            "high_debt_limit": float(current_app.config.get("DEFAULT_HIGH_DEBT_LIMIT", 50000)),
            "large_expense_flag": float(current_app.config.get("DEFAULT_LARGE_EXPENSE_FLAG", 100000))
        }

        # 2. User Thresholds (DB query override)
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT alert_thresholds FROM users WHERE id = %s LIMIT 1", (self.user_id,))
            row = cursor.fetchone()
            if row and row['alert_thresholds']:
                val = row['alert_thresholds']
                user_limits = json.loads(val) if isinstance(val, str) else val
                if user_limits:
                    for k in ("low_stock_limit", "high_debt_limit", "large_expense_flag"):
                        if k in user_limits and user_limits[k] is not None:
                            thresholds[k] = float(user_limits[k])
        except Exception as e:
            print(f"[CFOAgent Threshold Hierarchy Error] {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

        # 3. Adaptive Adjustments (Future LLM hooks override placeholder)
        adaptive = self._adaptive_llm_threshold_hooks()
        if adaptive:
            for k in ("low_stock_limit", "high_debt_limit", "large_expense_flag"):
                if k in adaptive and adaptive[k] is not None:
                    thresholds[k] = float(adaptive[k])

        return thresholds

    def _adaptive_llm_threshold_hooks(self):
        """Placeholder hook for future LLM-based adaptive threshold adjustments."""
        return {}
