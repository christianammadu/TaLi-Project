"""Ledger & Tax Agent (Agent 2).

Receives events from Agent 1, enforces auth scopes, executes CRUD database operations under transaction controls, and publishes updates.
"""

import json
import os
import uuid
from mysql.connector import Error
from app.data.database import get_db_connection
from app.agents.band import get_band_client
from app.services.validators import dump_model
from app.services.uuid_utils import uuid7, uuid_to_bin, bin_to_uuid

# Band room handles (WP-04). Ledger forwards results to the CFO and runs the two-phase
# review with the Compliance agent (WP-07) — all by @mention in the shared room.
LEDGER_HANDLE = "@tali-ledger"
CFO_HANDLE = "@tali-cfo"
COMPLIANCE_HANDLE = "@tali-compliance"


class LedgerAgent:
    """Agent 2 — Ledger & Tax. Interacts directly with database tables to process structured inputs."""

    def __init__(self, user_id, sender_id, band=None):
        self.user_id = user_id
        self.sender_id = sender_id
        # Band connector (WP-04); injectable for tests. One room per sender for now.
        self.band = band if band is not None else get_band_client()
        self.room_id = os.getenv("BAND_ROOM_ID") or f"tali-{sender_id}"
        self._review_timeout = float(os.getenv("BAND_REVIEW_TIMEOUT", "8"))
        self._user_cid = None   # set by on_room_message so CFO's reply is collectable

    def on_room_message(self, msg):
        """Band room handler entry (wired by WP-06). Threads the user correlation_id so
        the eventual CFO reply is collectable, then runs the ledger processing."""
        self._user_cid = msg.get("correlation_id")
        return self.handle_intake_payload(msg.get("body"))

    def _emit_to_cfo(self, event_dict):
        """Forward a ledger event to the CFO agent in the room (fire-and-forget). Threads
        the user correlation_id so CFO can post the terminal reply the gateway collects."""
        self.band.send(self.room_id, [CFO_HANDLE], event_dict,
                       correlation_id=self._user_cid, sender=LEDGER_HANDLE)

    def _review_gate(self, proposed):
        """Two-phase commit seam (WP-04 / G-14): send a proposed-write envelope to the
        Compliance agent BEFORE commit and block for a verdict. Returns (approved, reason).
        A reject PREVENTS the commit. When no reviewer responds yet (pre-WP-07), fall back
        to BAND_REVIEW_DEFAULT (default 'allow' for dev; set 'deny' for strict prod)."""
        review_cid = uuid.uuid4().hex
        self.band.send(self.room_id, [COMPLIANCE_HANDLE],
                       {"type": "proposed_write", "proposed": proposed,
                        "user_correlation_id": self._user_cid},
                       correlation_id=review_cid, sender=LEDGER_HANDLE)
        verdict = self.band.collect_reply(review_cid, timeout=self._review_timeout)
        if verdict is None:
            allow = os.getenv("BAND_REVIEW_DEFAULT", "allow").lower() == "allow"
            return allow, ("no reviewer (default-allow)" if allow else "no reviewer (default-deny)")
        if isinstance(verdict, dict):
            return bool(verdict.get("approved", False)), verdict.get("reason", "")
        v = str(verdict).strip().lower()
        return v in ("approve", "approved", "ok", "allow", "yes"), str(verdict)

    def _build_review_proposal(self, event):
        """Build the compliance review envelope from the payload — used to review BEFORE
        any DB write, so the blocking review never runs inside an open transaction holding
        row locks. Returns the proposed-write dict, or None for read-only/empty intents."""
        p = event.payload
        if p.is_fast_path:
            c = p.fast_path_transaction
            if not c:
                return None
            return {"intent": "record_transaction", "fast_path": True,
                    "amount": float(c.amount) if c.amount is not None else 0.0,
                    "currency": c.currency, "item": c.item}
        parsed = p.nlp_parsed
        if parsed and (parsed.transactions or parsed.inventory or parsed.debts):
            return {"intent": "split_routing",
                    "transactions": len(parsed.transactions),
                    "inventory": len(parsed.inventory),
                    "debts": len(parsed.debts)}
        return None

    def _emit_reject(self, event, intent, reason):
        """Emit a compliance-reject event to the CFO (matching the proposal's intent)."""
        from app.agents.event_schemas import LedgerUpdateEvent, LedgerUpdateEventPayload
        reject_event = LedgerUpdateEvent(
            correlation_id=event.correlation_id, session_id=event.session_id,
            user_id=event.user_id, business_id=event.business_id,
            source_agent="LedgerAgent", event_type="error",
            payload=LedgerUpdateEventPayload(
                status="rejected", intent=intent,
                raw_text=event.payload.raw_text, error_reason=f"Compliance hold: {reason}"),
        )
        self._emit_to_cfo(reject_event.model_dump(mode='json'))

    def handle_intake_payload(self, payload):
        """Processes events from Agent 1."""
        # Deserialize and validate incoming Pydantic IntakePayload
        from app.agents.event_schemas import (
            IntakePayload, LedgerUpdateEvent, LedgerUpdateEventPayload,
            TransactionResult, LedgerUpdateData
        )
        from decimal import Decimal
        import time
        try:
            if isinstance(payload, dict):
                event = IntakePayload.model_validate(payload)
            else:
                event = payload
        except Exception as ve:
            print(f"[LedgerAgent Schema Error] Invalid IntakePayload: {ve}")
            return "❌ Validation Error: Event payload format invalid."

        # Extract context variables for tracing (correlation_id, session_id, user_id, business_id)
        correlation_id = event.correlation_id
        session_id = event.session_id
        user_id = event.user_id
        business_id = event.business_id
        is_fast_path = event.payload.is_fast_path
        raw_text = event.payload.raw_text

        # 1. Authorize user permissions
        if not self._is_authorized():
            return "❌ Authorization Error: User session invalid."

        user_id_bin = uuid_to_bin(self.user_id)

        # Two-phase review (WP-04 / G-14) BEFORE opening any DB transaction. The review
        # blocks on the Compliance agent for up to BAND_REVIEW_TIMEOUT; doing it here (not
        # mid-transaction) means we never hold row locks across that call. A reject prevents
        # the write entirely (nothing is inserted-then-rolled-back).
        review_proposed = self._build_review_proposal(event)
        if review_proposed is not None:
            approved, reason = self._review_gate(review_proposed)
            if not approved:
                self._emit_reject(event, review_proposed["intent"], reason)
                return f"🛑 Not recorded — compliance hold: {reason}"

        retry_delays = [0.1, 0.5, 1.0]
        max_attempts = len(retry_delays) + 1

        for attempt in range(1, max_attempts + 1):
            conn = get_db_connection()
            try:
                conn.start_transaction()
                cursor = conn.cursor(dictionary=True)

                # Idempotency Check: check if event has already been processed by Ledger (Epic 4)
                cursor.execute(
                    "SELECT event_id FROM processed_events WHERE event_id = %s AND agent_name = 'LedgerAgent' LIMIT 1",
                    (str(event.event_id),)
                )
                if cursor.fetchone():
                    conn.rollback()
                    print(f"[LedgerAgent Idempotency] Event {event.event_id} already processed. Dropping.")
                    return "✅ Already processed (idempotency drop)."

                # Fast path execution
                if is_fast_path:
                    cleaned = event.payload.fast_path_transaction
                    if not cleaned:
                        conn.rollback()
                        return "❌ Error: Missing fast path transaction data."

                    # Resolve category ID
                    category_name = cleaned.category or 'Miscellaneous'
                    cursor.execute(
                        "SELECT id FROM categories WHERE name = %s AND (user_id IS NULL OR user_id = %s) LIMIT 1",
                        (category_name, user_id_bin)
                    )
                    cat_row = cursor.fetchone()
                    category_id = cat_row['id'] if cat_row else None
                    if category_id is None:
                        cursor.execute("SELECT id FROM categories WHERE name = 'Miscellaneous' AND user_id IS NULL LIMIT 1")
                        cat_row = cursor.fetchone()
                        category_id = cat_row['id'] if cat_row else None

                    transaction_date = cleaned.date
                    amount = Decimal(str(cleaned.amount))
                    currency = cleaned.currency
                    tx_type = cleaned.type
                    action = cleaned.action
                    item = cleaned.item
                    description = cleaned.description or ''

                    # Resolve user business_id
                    cursor.execute("SELECT business_id FROM users WHERE id = %s LIMIT 1", (user_id_bin,))
                    user_row = cursor.fetchone()
                    user_business_id = user_row['business_id'] if user_row and user_row['business_id'] is not None else None

                    tx_uuid = uuid7()
                    # Insert into transactions (populating id, currency, business_id, and event_id)
                    cursor.execute(
                        "INSERT INTO transactions (id, user_id, business_id, event_id, category_id, type, action, amount, currency, currency_code, item, description, raw_text, transaction_date) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (tx_uuid.bytes, user_id_bin, user_business_id, str(event.event_id), category_id, tx_type, action, amount, currency, currency, item, description, raw_text, transaction_date)
                    )
                    tx_id = tx_uuid.bytes

                    # Legacy records write
                    record_uuid = uuid7()
                    cursor.execute(
                        "INSERT INTO records (id, sender_id, raw_text, amount) VALUES (%s, %s, %s, %s)",
                        (record_uuid.bytes, self.sender_id, raw_text, int(amount))
                    )

                    # Compliance already reviewed before the transaction (no locks held).
                    # Record idempotency log inside the transaction atomically.
                    cursor.execute(
                        "INSERT INTO processed_events (event_id, agent_name) VALUES (%s, 'LedgerAgent')",
                        (str(event.event_id),)
                    )
                    conn.commit()

                    if tx_id:
                        tx_result = TransactionResult(
                            id=str(bin_to_uuid(tx_id)),
                            type=tx_type,
                            action=action,
                            amount=float(amount),
                            currency=currency,
                            item=item,
                            category=category_name,
                            description=description,
                            date=transaction_date,
                        )
                        success_event = LedgerUpdateEvent(
                            correlation_id=correlation_id,
                            session_id=session_id,
                            user_id=user_id,
                            business_id=business_id,
                            source_agent="LedgerAgent",
                            event_type="transaction",
                            payload=LedgerUpdateEventPayload(
                                transaction_id=str(bin_to_uuid(tx_id)),
                                status="success",
                                intent="record_transaction",
                                raw_text=raw_text,
                                data=LedgerUpdateData(transactions=[tx_result])
                            )
                        )
                        self._emit_to_cfo(success_event.model_dump(mode='json'))
                        return "✅ Shorthand saved."
                    return "❌ Failed to record shorthand."

                # NLP path execution
                parsed = event.payload.nlp_parsed
                if not parsed:
                    conn.rollback()
                    return "❌ Error: Missing parsed payload."

                intents = parsed.intents
                results = {}

                # Trigger health snapshot directly (Read-only, rollback transaction)
                if parsed.snapshot or "snapshot" in intents:
                    conn.rollback()
                    success_event = LedgerUpdateEvent(
                        correlation_id=correlation_id,
                        session_id=session_id,
                        user_id=user_id,
                        business_id=business_id,
                        source_agent="LedgerAgent",
                        event_type="report",
                        payload=LedgerUpdateEventPayload(
                            status="success",
                            intent="snapshot",
                            raw_text=raw_text
                        )
                    )
                    self._emit_to_cfo(success_event.model_dump(mode='json'))
                    return "📊 Snapshot requested."

                # Trigger reports directly (Read-only, rollback transaction)
                if "report" in intents and parsed.report:
                    conn.rollback()
                    success_event = LedgerUpdateEvent(
                        correlation_id=correlation_id,
                        session_id=session_id,
                        user_id=user_id,
                        business_id=business_id,
                        source_agent="LedgerAgent",
                        event_type="report",
                        payload=LedgerUpdateEventPayload(
                            status="success",
                            intent="report",
                            raw_text=raw_text,
                            data=LedgerUpdateData(report=parsed.report)
                        )
                    )
                    self._emit_to_cfo(success_event.model_dump(mode='json'))
                    return "📑 Report requested."

                # Trigger queries directly (Read-only, rollback transaction)
                if "query" in intents:
                    conn.rollback()
                    from app.agents.transaction_agent import TransactionAgent
                    tx_agent = TransactionAgent(self.user_id, self.sender_id)
                    query_fields = dump_model(parsed.query) if parsed.query else {}
                    return tx_agent.process(raw_text, {'intent': 'query', **query_fields})

                # Resolve user business_id
                cursor.execute("SELECT business_id FROM users WHERE id = %s LIMIT 1", (user_id_bin,))
                user_row = cursor.fetchone()
                user_business_id = user_row['business_id'] if user_row and user_row['business_id'] is not None else None

                # Standard split execution — each list may carry several items.
                # Per-item event_id suffix keeps the UNIQUE event_id constraint
                # satisfied when one message produces multiple ledger rows.
                from app.agents.event_schemas import (
                    TransactionResult, InventoryResult, DebtResult, LedgerUpdateData,
                )

                tx_results = []
                for i, cleaned in enumerate(parsed.transactions):
                    category_name = cleaned.category or 'Miscellaneous'
                    cursor.execute(
                        "SELECT id FROM categories WHERE name = %s AND (user_id IS NULL OR user_id = %s) LIMIT 1",
                        (category_name, user_id_bin)
                    )
                    cat_row = cursor.fetchone()
                    category_id = cat_row['id'] if cat_row else None
                    if category_id is None:
                        cursor.execute("SELECT id FROM categories WHERE name = 'Miscellaneous' AND user_id IS NULL LIMIT 1")
                        cat_row = cursor.fetchone()
                        category_id = cat_row['id'] if cat_row else None

                    transaction_date = cleaned.date
                    amount = Decimal(str(cleaned.amount))
                    currency = cleaned.currency
                    tx_type = cleaned.type
                    action = cleaned.action
                    item = cleaned.item
                    description = cleaned.description or ''

                    tx_uuid = uuid7()
                    cursor.execute(
                        "INSERT INTO transactions (id, user_id, business_id, event_id, category_id, type, action, amount, currency, currency_code, item, description, raw_text, transaction_date) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (tx_uuid.bytes, user_id_bin, user_business_id, f"{event.event_id}:tx{i}", category_id, tx_type, action, amount, currency, currency, item, description, raw_text, transaction_date)
                    )

                    record_uuid = uuid7()
                    cursor.execute(
                        "INSERT INTO records (id, sender_id, raw_text, amount) VALUES (%s, %s, %s, %s)",
                        (record_uuid.bytes, self.sender_id, raw_text, int(amount))
                    )

                    tx_results.append(TransactionResult(
                        id=str(bin_to_uuid(tx_uuid.bytes)),
                        type=tx_type,
                        action=action,
                        amount=float(amount),
                        currency=currency,
                        item=item,
                        category=category_name,
                        description=description,
                        date=transaction_date
                    ))
                if tx_results:
                    results['transactions'] = tx_results

                inv_results = []
                for i, inv_item in enumerate(parsed.inventory):
                    cleaned = dump_model(inv_item)
                    inv_reply_str = self._process_inventory(cursor, raw_text, cleaned, user_business_id, f"{event.event_id}:inv{i}")
                    inv_reply = json.loads(inv_reply_str)
                    if inv_reply.get('status') == 'clarification_needed':
                        conn.rollback()
                        # Return the human question — never the raw JSON (this reply is
                        # sent straight to the customer, it does not pass through the CFO).
                        return inv_reply.get('question') or "I need a bit more detail to record that stock change."
                    inv_results.append(InventoryResult(**inv_reply))
                if inv_results:
                    results['inventory'] = inv_results

                debt_results = []
                for i, debt_item in enumerate(parsed.debts):
                    cleaned = dump_model(debt_item)
                    debt_reply_str = self._process_debt(cursor, raw_text, cleaned, user_business_id, f"{event.event_id}:debt{i}")
                    debt_reply = json.loads(debt_reply_str)
                    if debt_reply.get('status') == 'clarification_needed':
                        conn.rollback()
                        return debt_reply.get('question') or "I need a bit more detail to record that debt."
                    debt_results.append(DebtResult(**debt_reply))
                if debt_results:
                    results['debts'] = debt_results

                if results:
                    # Compliance already reviewed before the transaction (no locks held).
                    # Record idempotency log inside the transaction atomically.
                    cursor.execute(
                        "INSERT INTO processed_events (event_id, agent_name) VALUES (%s, 'LedgerAgent')",
                        (str(event.event_id),)
                    )
                    conn.commit()

                    tx_id_str = str(tx_results[0].id) if tx_results else None

                    success_event = LedgerUpdateEvent(
                        correlation_id=correlation_id,
                        session_id=session_id,
                        user_id=user_id,
                        business_id=business_id,
                        source_agent="LedgerAgent",
                        event_type="transaction",
                        payload=LedgerUpdateEventPayload(
                            transaction_id=tx_id_str,
                            status="success",
                            intent="split_routing",
                            raw_text=raw_text,
                            data=LedgerUpdateData(
                                transactions=tx_results,
                                inventory=inv_results,
                                debts=debt_results
                            )
                        )
                    )
                    self._emit_to_cfo(success_event.model_dump(mode='json'))
                    # For output display, dump list representations
                    out_results = {k: [dump_model(x) for x in v] for k, v in results.items()}
                    return json.dumps(out_results, indent=2)

                conn.rollback()
                return "❓ No actions processed."

            except Error as db_err:
                if 'conn' in locals() and conn.is_connected():
                    conn.rollback()

                transient_codes = (1205, 1213, 2006, 2013)
                if db_err.errno in transient_codes and attempt < max_attempts:
                    # Close resources before retry
                    if 'cursor' in locals() and cursor:
                        cursor.close()
                    if conn.is_connected():
                        conn.close()

                    delay = retry_delays[attempt - 1]
                    print(f"[LedgerAgent Transient DB Error, Attempt {attempt}] Code {db_err.errno}: {db_err}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    # Non-transient DB error or exhausted retries. The webhook_events
                    # lifecycle is owned by the gateway (keyed by whatsapp_message_id);
                    # the ledger only dead-letters the event to the CFO and returns — it
                    # must not touch webhook_events (it can't target the right row, and the
                    # gateway overwrites it on return anyway).
                    err_event = LedgerUpdateEvent(
                        correlation_id=correlation_id,
                        session_id=session_id,
                        user_id=user_id,
                        business_id=business_id,
                        source_agent="LedgerAgent",
                        event_type="error",
                        payload=LedgerUpdateEventPayload(
                            status="error",
                            intent="error",
                            raw_text=raw_text,
                            error_reason=f"Database Error Code {db_err.errno}: {db_err}"
                        )
                    )
                    self._emit_to_cfo(err_event.model_dump(mode='json'))
                    return {"status": "error_handled_via_pubsub"}

            except Exception as e:
                # Malformed payload, validation error, code bug -> fail immediately!
                # (webhook_events lifecycle is the gateway's, keyed by message_id — see above)
                if 'conn' in locals() and conn.is_connected():
                    conn.rollback()

                err_event = LedgerUpdateEvent(
                    correlation_id=correlation_id,
                    session_id=session_id,
                    user_id=user_id,
                    business_id=business_id,
                    source_agent="LedgerAgent",
                    event_type="error",
                    payload=LedgerUpdateEventPayload(
                        status="error",
                        intent="error",
                        raw_text=raw_text,
                        error_reason=str(e)
                    )
                )
                self._emit_to_cfo(err_event.model_dump(mode='json'))
                return {"status": "error_handled_via_pubsub"}
            finally:
                # Guard cursor independently — it's unbound if conn.cursor() itself raised,
                # and may already be closed by the transient-retry branch above.
                if 'cursor' in locals() and cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                if 'conn' in locals() and conn is not None and conn.is_connected():
                    try:
                        conn.close()
                    except Exception:
                        pass

    def _is_authorized(self):
        """Validate if the user exists in database permissions."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            user_id_bin = uuid_to_bin(self.user_id)
            cursor.execute("SELECT id FROM users WHERE id = %s LIMIT 1", (user_id_bin,))
            return cursor.fetchone() is not None
        except Error:
            return False
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _process_inventory(self, cursor, raw_text, parsed_inv, business_id, event_id=None):
        """Process stock adjustments in the standardized inventory_items and inventory_movements tables."""
        from decimal import Decimal
        item_name = parsed_inv.get('product')
        quantity_val = parsed_inv.get('quantity')
        unit = parsed_inv.get('unit')
        action = parsed_inv.get('action', 'ADD').upper()

        if not item_name or quantity_val is None:
            return json.dumps({"status": "error", "message": "Missing product details."})

        user_id_bin = uuid_to_bin(self.user_id)
        quantity = Decimal(str(quantity_val))

        # Fetch inventory item details using business_id
        cursor.execute(
            "SELECT id, unit FROM inventory_items "
            "WHERE business_id = %s AND item_name = %s LIMIT 1",
            (business_id, item_name)
        )
        item_row = cursor.fetchone()

        db_unit = unit
        if item_row:
            item_id = item_row['id']
            db_unit = item_row['unit'] if item_row['unit'] else unit
            if unit:
                cursor.execute(
                    "UPDATE inventory_items SET unit = %s WHERE id = %s",
                    (unit, item_id)
                )
        else:
            item_uuid = uuid7()
            cursor.execute(
                "INSERT INTO inventory_items (id, user_id, business_id, item_name, unit) VALUES (%s, %s, %s, %s, %s)",
                (item_uuid.bytes, user_id_bin, business_id, item_name, unit)
            )
            item_id = item_uuid.bytes

        # Calculate current stock level from movements
        cursor.execute(
            "SELECT SUM(CASE "
            "  WHEN movement_type = 'stock_in' THEN quantity "
            "  WHEN movement_type = 'stock_out' THEN -quantity "
            "  WHEN movement_type = 'adjustment' THEN quantity "
            "  ELSE 0 "
            "END) as stock_level "
            "FROM inventory_movements WHERE inventory_item_id = %s",
            (item_id,)
        )
        stock_row = cursor.fetchone()
        current_stock = Decimal(str(stock_row['stock_level'])) if stock_row and stock_row['stock_level'] is not None else Decimal('0.00')

        # Process stock logic and compute movements deltas
        if action == 'ADD':
            new_stock = current_stock + quantity
            movement_type = 'stock_in'
            movement_qty = quantity
        elif action == 'REMOVE':
            # A confirmed sale must still record even when tracked stock is short — the
            # merchant may not have logged their opening stock or every purchase. Let the
            # level reflect the true position (it may go negative) so they can reconcile
            # later by recording the missing purchases; the reply nudges them to do so.
            # We do NOT block/roll back the entry on a stock shortfall.
            new_stock = current_stock - quantity
            movement_type = 'stock_out'
            movement_qty = quantity
        elif action == 'SET':
            new_stock = quantity
            movement_type = 'adjustment'
            movement_qty = quantity - current_stock
        else:
            new_stock = current_stock
            movement_type = 'adjustment'
            movement_qty = Decimal('0.00')

        # Log stock movement record (populating business_id and event_id)
        inv_mov_uuid = uuid7()
        cursor.execute(
            "INSERT INTO inventory_movements (id, inventory_item_id, user_id, business_id, event_id, movement_type, quantity, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (inv_mov_uuid.bytes, item_id, user_id_bin, business_id, event_id, movement_type, movement_qty, raw_text)
        )

        # --- DUAL-WRITE TO LEGACY PRODUCTS & STOCK MOVEMENTS ---
        # Lookup legacy product ID
        cursor.execute(
            "SELECT id FROM products WHERE user_id = %s AND name = %s LIMIT 1",
            (user_id_bin, item_name)
        )
        prod_row = cursor.fetchone()
        if prod_row:
            prod_id = prod_row['id']
            cursor.execute(
                "UPDATE products SET quantity = %s, unit = %s WHERE id = %s",
                (new_stock, db_unit, prod_id)
            )
        else:
            prod_uuid = uuid7()
            cursor.execute(
                "INSERT INTO products (id, user_id, name, quantity, unit) VALUES (%s, %s, %s, %s, %s)",
                (prod_uuid.bytes, user_id_bin, item_name, new_stock, db_unit)
            )
            prod_id = prod_uuid.bytes

        legacy_action = 'in' if action == 'ADD' else ('out' if action == 'REMOVE' else 'set')
        stock_mov_uuid = uuid7()
        cursor.execute(
            "INSERT INTO stock_movements (id, product_id, user_id, event_id, movement_type, quantity, description) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (stock_mov_uuid.bytes, prod_id, user_id_bin, event_id, legacy_action, quantity, raw_text)
        )

        return json.dumps({
            "product": item_name,
            "action": action,
            "quantity": float(quantity),
            "unit": db_unit,
            "new_stock": float(new_stock)
        })

    def _process_debt(self, cursor, raw_text, parsed_debt, business_id, event_id=None):
        """Process debt updates using double-entry logic and SQL transaction controls."""
        from decimal import Decimal
        from datetime import date

        name = parsed_debt.get('name')
        debt_type = parsed_debt.get('type')  # 'customer_debt' or 'supplier_debt'
        action = parsed_debt.get('action', 'add_debt').lower().strip()
        amount_val = parsed_debt.get('amount')
        currency = parsed_debt.get('currency', 'NGN') or 'NGN'

        if not name:
            return json.dumps({"status": "error", "message": "Missing debtor/creditor name."})

        user_id_bin = uuid_to_bin(self.user_id)
        name = name.lower().strip()
        db_type = 'receivable' if debt_type == 'customer_debt' else 'payable'

        # Get current outstanding balance from debt_balances
        cursor.execute(
            "SELECT id, outstanding_balance, debt_type FROM debt_balances "
            "WHERE user_id = %s AND person_name = %s AND currency = %s LIMIT 1",
            (user_id_bin, name, currency)
        )
        row = cursor.fetchone()
        previous_balance = Decimal(str(row['outstanding_balance'])) if row else Decimal('0.00')
        db_row_id = row['id'] if row else None
        current_db_type = row['debt_type'] if row else db_type

        # Calculate amount
        amount = Decimal('0.00')
        if amount_val is not None:
            amount = Decimal(str(amount_val))
        
        if action == 'full_payment':
            amount = previous_balance

        # Determine double-entry type for debt_entries:
        # - Customer owes money (customer_debt + add_debt) -> receivable
        # - Customer pays back (customer_debt + repayment) -> payable (offsets receivable)
        # - We owe supplier (supplier_debt + add_debt) -> payable
        # - We pay supplier back (supplier_debt + repayment) -> receivable (offsets payable)
        if debt_type == 'customer_debt':
            entry_type = 'receivable' if action == 'add_debt' else 'payable'
        else:
            entry_type = 'payable' if action == 'add_debt' else 'receivable'

        # 1. Write to debt_entries
        debt_entry_uuid = uuid7()
        cursor.execute(
            "INSERT INTO debt_entries (id, user_id, business_id, event_id, person_name, type, amount, currency, raw_text) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (debt_entry_uuid.bytes, user_id_bin, business_id, event_id, name, entry_type, amount, currency, raw_text)
        )

        # 2. Write to transactions (ledger entry for auditing)
        tx_uuid = uuid7()
        tx_type = 'income' if debt_type == 'customer_debt' else 'expense'
        tx_action = 'sale' if action == 'add_debt' else 'payment'
        cursor.execute(
            "INSERT INTO transactions (id, user_id, business_id, event_id, category_id, type, action, amount, currency, currency_code, item, description, raw_text, transaction_date) "
            "VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                tx_uuid.bytes,
                user_id_bin,
                business_id,
                event_id,
                tx_type,
                tx_action,
                amount,
                currency,
                currency,
                name,
                f"Debt transaction: {name} - {entry_type}",
                raw_text,
                date.today().isoformat()
            )
        )
        tx_id = tx_uuid.bytes

        # 3. Update debt_balances outstanding balance (running total)
        if debt_type == 'customer_debt':
            new_balance = previous_balance + amount if action == 'add_debt' else previous_balance - amount
        else:
            new_balance = previous_balance + amount if action == 'add_debt' else previous_balance - amount
        
        if action == 'full_payment':
            new_balance = Decimal('0.00')

        if db_row_id:
            cursor.execute(
                "UPDATE debt_balances SET outstanding_balance = %s, debt_type = %s "
                "WHERE id = %s",
                (new_balance, current_db_type, db_row_id)
            )
        else:
            debt_bal_uuid = uuid7()
            cursor.execute(
                "INSERT INTO debt_balances (id, user_id, business_id, person_name, debt_type, outstanding_balance, currency) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (debt_bal_uuid.bytes, user_id_bin, business_id, name, current_db_type, new_balance, currency)
            )

        # 4. Log to debt_logs for historical audit log
        debt_log_uuid = uuid7()
        cursor.execute(
            "INSERT INTO debt_logs (id, user_id, business_id, event_id, person_name, debt_type, action, amount, previous_balance, new_balance, currency, raw_text) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (debt_log_uuid.bytes, user_id_bin, business_id, event_id, name, current_db_type, action, amount, previous_balance, new_balance, currency, raw_text)
        )

        api_type = 'customer_debt' if current_db_type == 'receivable' else 'supplier_debt'
        return json.dumps({
            "name": name,
            "type": api_type,
            "action": action,
            "amount": float(amount),
            "previous_balance": float(previous_balance),
            "new_balance": float(new_balance),
            "status": "updated",
            "transaction_id": str(bin_to_uuid(tx_id))
        }, indent=2)
