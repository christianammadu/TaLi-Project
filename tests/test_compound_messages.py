"""Tests for WP-02: Multi-Intent Compound Split-Routing & Composite CFO (Issue #14).

Covers:
1. Composite reply formatting in CFOAgent (Recorded ✅, Inventory 📦, Balance/Report 📊).
2. Pending confirmation holding a mutating entry preserves and executes bundled read query upon 'YES'.
3. Atomic transaction rollback (G-06): If any individual mutation in a multi-write fails,
   all mutations roll back cleanly, and the error explicitly indicates the failing item.
4. Post-commit query execution on the committed state.
5. Backwards compatibility: Existing single-intent transactions format identically without regression.
"""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from app.agents.agent_1_intake import IntakeAgent
from app.agents.agent_2_ledger import LedgerAgent, LEDGER_HANDLE, CFO_HANDLE
from app.agents.agent_3_cfo import CFOAgent, GATEWAY_HANDLE
from app.agents.band.band_client import get_band_client
from app.agents.event_schemas import (
    IntakePayload, IntakeEventPayload,
    LedgerUpdateEvent, LedgerUpdateEventPayload, LedgerUpdateData,
    TransactionResult, InventoryResult, DebtResult
)
from app.services.validators import UnifiedResponseModel, TransactionModel, InventoryModel, QueryModel


class TestCompoundMessagesCFOFormatting(unittest.TestCase):
    """Test composite CFO formatting in split_routing."""

    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.cfo = CFOAgent("user-1", "sender-1", band=self.band)

    def _run_cfo_ledger_update(self, payload):
        conn = mock.MagicMock()
        conn.cursor.return_value.fetchone.return_value = None  # not yet processed
        conn.is_connected.return_value = True
        thresholds = {"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000}
        with mock.patch("app.data.database.get_db_connection", return_value=conn), \
             mock.patch.object(self.cfo, "_get_evaluated_thresholds", return_value=thresholds):
            return self.cfo.handle_ledger_update(payload)

    def test_single_intent_transaction_formats_identically(self):
        """Single-intent transaction continues to format identically without regression."""
        payload = {
            "source_agent": "LedgerAgent",
            "event_type": "transaction",
            "user_id": "user-1",
            "payload": {
                "transaction_id": "tx-1",
                "status": "success",
                "intent": "split_routing",
                "raw_text": "Sold 5 bags of rice 30k",
                "data": {
                    "transactions": [{
                        "id": "tx-1", "type": "income", "action": "sale", "amount": 30000,
                        "currency": "NGN", "item": "rice", "category": "Sales",
                        "description": "sold rice", "date": "2026-09-28"
                    }],
                    "inventory": [],
                    "debts": []
                }
            }
        }
        reply = self._run_cfo_ledger_update(payload)
        self.assertEqual(reply, "✅ Recorded: Sales — ₦30,000")

    def test_single_intent_inventory_formats_identically(self):
        """Single-intent inventory continues to format identically."""
        payload = {
            "source_agent": "LedgerAgent",
            "event_type": "transaction",
            "user_id": "user-1",
            "payload": {
                "transaction_id": None,
                "status": "success",
                "intent": "split_routing",
                "raw_text": "Added 15 bags of rice",
                "data": {
                    "transactions": [],
                    "inventory": [{
                        "product": "rice", "action": "ADD", "quantity": 15,
                        "unit": "bags", "new_stock": 15
                    }],
                    "debts": []
                }
            }
        }
        reply = self._run_cfo_ledger_update(payload)
        self.assertEqual(reply, "📦 Inventory Updated: rice stock level is now 15 bags.")

    def test_single_intent_debt_formats_identically(self):
        """Single-intent debt continues to format identically."""
        payload = {
            "source_agent": "LedgerAgent",
            "event_type": "transaction",
            "user_id": "user-1",
            "payload": {
                "transaction_id": None,
                "status": "success",
                "intent": "split_routing",
                "raw_text": "John owes 5000",
                "data": {
                    "transactions": [],
                    "inventory": [],
                    "debts": [{
                        "name": "john", "type": "customer_debt", "action": "add_debt",
                        "amount": 5000, "previous_balance": 0, "new_balance": 5000,
                        "status": "recorded"
                    }]
                }
            }
        }
        reply = self._run_cfo_ledger_update(payload)
        self.assertEqual(reply, "👥 Debt Ledger: john owes ₦5,000. Outstanding: ₦5,000.")

    def test_compound_sale_inventory_and_query_produces_three_part_reply(self):
        """Utterance 'Sold 5 bags of rice 30k, how many bags left and what is my balance?'
        formats a clean composite reply with all 3 answers."""
        balance_str = "💰 *Your Balance*\n\n*NGN Balance:*\n• *Income:* ₦30,000\n• *Expenses:* ₦0\n• *Net:* ₦30,000 📈"
        payload = {
            "source_agent": "LedgerAgent",
            "event_type": "transaction",
            "user_id": "user-1",
            "payload": {
                "transaction_id": "tx-1",
                "status": "success",
                "intent": "split_routing",
                "raw_text": "Sold 5 bags of rice 30k, how many bags left and what is my balance?",
                "data": {
                    "transactions": [{
                        "id": "tx-1", "type": "income", "action": "sale", "amount": 30000,
                        "currency": "NGN", "item": "rice", "category": "Sales",
                        "description": "sold 5 bags of rice", "date": "2026-09-28"
                    }],
                    "inventory": [{
                        "product": "rice", "action": "REMOVE", "quantity": 5,
                        "unit": "bags", "new_stock": 15
                    }],
                    "debts": [],
                    "query_result": balance_str
                }
            }
        }
        reply = self._run_cfo_ledger_update(payload)

        # Answer 1: Sale recorded
        self.assertIn("✅ Recorded: Sales — ₦30,000", reply)
        # Answer 2: Inventory updated / remaining stock
        self.assertIn("📦 Inventory Updated: rice stock level is now 15 bags.", reply)
        # Answer 3: Current balance query
        self.assertIn("💰 *Your Balance*", reply)
        self.assertIn("• *Net:* ₦30,000 📈", reply)

    def test_cfo_surfaces_error_reason_with_failing_item(self):
        """When ledger fails with error_reason, CFO includes the exact failing item reason."""
        err_body = {
            "source_agent": "LedgerAgent",
            "payload": {
                "status": "error",
                "error_reason": "Failed to update inventory for 'rice': Database lock timeout"
            }
        }
        reply = self.cfo._compose_reply(err_body)
        self.assertIn("Failed to update inventory for 'rice'", reply)


class MockCursor:
    def __init__(self, failing_param=None, failing_exception=None):
        self.last_query = ""
        self.last_params = None
        self.failing_param = failing_param
        self.failing_exception = failing_exception

    def execute(self, query, params=None):
        self.last_query = str(query)
        self.last_params = params
        if self.failing_param and params and self.failing_param in str(params):
            raise (self.failing_exception or Exception("Simulated DB failure"))

    def fetchone(self):
        if "processed_events" in self.last_query:
            return None
        if "categories" in self.last_query:
            return {'id': 1}
        if "users" in self.last_query:
            return {'business_id': 1}
        return None

    def close(self):
        pass


class TestCompoundLedgerAtomicExecution(unittest.TestCase):
    """Test atomic transactions (G-06) and post-commit query in LedgerAgent."""

    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.ledger = LedgerAgent("user-1", "sender-1", band=self.band)
        self._patch_state = mock.patch("app.agents.agent_2_ledger.set_transaction_state")
        self._patch_state.start()

    def tearDown(self):
        self._patch_state.stop()

    def test_atomic_rollback_when_inventory_fails_in_multi_write(self):
        """If inventory mutation fails during a multi-write, all mutations roll back cleanly
        and error indicates the failing item."""
        import uuid
        parsed = UnifiedResponseModel(
            intents=["record_transaction", "inventory"],
            confidence=0.95,
            transactions=[TransactionModel(
                type="income", action="sale", amount=30000.0,
                item="rice", category="Sales", date="2026-09-28"
            )],
            inventory=[InventoryModel(
                action="REMOVE", product="rice", quantity=5.0, unit="bags"
            )]
        )
        ev = SimpleNamespace(
            correlation_id=str(uuid.uuid4()), session_id="s1", user_id="user-1", business_id=None,
            event_id=str(uuid.uuid4()),
            payload=SimpleNamespace(
                is_fast_path=False,
                raw_text="Sold 5 bags of rice 30k",
                fast_path_transaction=None,
                nlp_parsed=parsed
            )
        )
        self.ledger._is_authorized = lambda: True
        self.ledger._build_review_proposal = lambda e: None

        conn = mock.MagicMock()
        cursor = MockCursor()
        conn.cursor.return_value = cursor

        # Mock _process_inventory to return error for 'rice'
        self.ledger._process_inventory = mock.MagicMock(
            return_value=json.dumps({"status": "error", "message": "Item locked by concurrent process"})
        )

        with mock.patch("app.agents.agent_2_ledger.get_db_connection", return_value=conn):
            result = self.ledger.handle_intake_payload(ev)

        # Rollback was called on the connection
        conn.rollback.assert_called()
        conn.commit.assert_not_called()

        # The error response explicitly names the failing item
        self.assertIn("Failed to update inventory for 'rice'", result)
        self.assertIn("Item locked", result)

    def test_atomic_rollback_when_second_transaction_fails(self):
        """If second transaction insertion fails, all mutations roll back cleanly."""
        import uuid
        parsed = UnifiedResponseModel(
            intents=["record_transaction"],
            confidence=0.95,
            transactions=[
                TransactionModel(type="income", action="sale", amount=10000.0, item="rice", category="Sales", date="2026-09-28"),
                TransactionModel(type="income", action="sale", amount=20000.0, item="beans", category="Sales", date="2026-09-28")
            ]
        )
        ev = SimpleNamespace(
            correlation_id=str(uuid.uuid4()), session_id="s2", user_id="user-1", business_id=None,
            event_id=str(uuid.uuid4()),
            payload=SimpleNamespace(
                is_fast_path=False,
                raw_text="Sold rice 10k and beans 20k",
                fast_path_transaction=None,
                nlp_parsed=parsed
            )
        )
        self.ledger._is_authorized = lambda: True
        self.ledger._build_review_proposal = lambda e: None

        conn = mock.MagicMock()
        cursor = MockCursor(failing_param=":tx1", failing_exception=Exception("Deadlock detected during insert"))
        conn.cursor.return_value = cursor

        with mock.patch("app.agents.agent_2_ledger.get_db_connection", return_value=conn):
            result = self.ledger.handle_intake_payload(ev)

        conn.rollback.assert_called()
        conn.commit.assert_not_called()
        self.assertIn("Failed to record transaction for 'beans'", result)

    def test_post_commit_query_executed_on_committed_state(self):
        """Mutations commit before query is executed; query result is packaged into event data."""
        import uuid
        parsed = UnifiedResponseModel(
            intents=["record_transaction", "query"],
            confidence=0.95,
            transactions=[TransactionModel(
                type="income", action="sale", amount=30000.0,
                item="rice", category="Sales", date="2026-09-28"
            )],
            query=QueryModel(query_type="balance")
        )
        ev = SimpleNamespace(
            correlation_id=str(uuid.uuid4()), session_id="s3", user_id="user-1", business_id=None,
            event_id=str(uuid.uuid4()),
            payload=SimpleNamespace(
                is_fast_path=False,
                raw_text="Sold 30k rice and what is my balance?",
                fast_path_transaction=None,
                nlp_parsed=parsed
            )
        )
        self.ledger._is_authorized = lambda: True
        self.ledger._build_review_proposal = lambda e: None

        conn = mock.MagicMock()
        cursor = MockCursor()
        conn.cursor.return_value = cursor

        emitted_events = []
        self.ledger._emit_to_cfo = lambda e: emitted_events.append(e)

        mock_query_output = "💰 *Your Balance*\n\n*Net Balance: ₦30,000*"
        with mock.patch("app.agents.agent_2_ledger.get_db_connection", return_value=conn), \
             mock.patch("app.agents.transaction_agent.TransactionAgent.query", return_value=mock_query_output) as mock_q:
            result = self.ledger.handle_intake_payload(ev)

        # Ensure commit happened
        conn.commit.assert_called()
        mock_q.assert_called_once()

        # Query result packaged into emitted event data
        self.assertEqual(len(emitted_events), 1)
        event_data = emitted_events[0]["payload"]["data"]
        self.assertEqual(event_data["query_result"], mock_query_output)

        # Result string contains query_result
        res_json = json.loads(result)
        self.assertEqual(res_json["query_result"], mock_query_output)


class TestIntakePendingConfirmationCompoundFlow(unittest.TestCase):
    """Test that IntakeAgent holds compound entries and executes query upon confirmation."""

    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.intake = IntakeAgent("user-1", "sender-1", band=self.band)
        self._patch_state = mock.patch("app.agents.agent_1_intake.set_transaction_state")
        self._patch_state.start()

    def tearDown(self):
        self._patch_state.stop()

    def test_intake_holds_compound_message_preserving_query(self):
        """Intake holds mutating compound entry as pending while preserving the bundled query."""
        parsed = {
            "intents": ["record_transaction", "inventory", "query"],
            "confidence": 0.95,
            "status": "ok",
            "transactions": [{
                "type": "income", "action": "sale", "amount": 30000.0,
                "currency": "NGN", "item": "rice", "category": "Sales",
                "description": "sold 5 bags of rice", "date": "2026-09-28"
            }],
            "inventory": [{
                "action": "REMOVE", "product": "rice", "quantity": 5.0, "unit": "bags"
            }],
            "query": {"query_type": "balance"}
        }

        stored_payloads = []
        self.intake._store_pending_json = lambda text, p: stored_payloads.append(p) or True
        self.intake._load_pending = lambda: None

        with mock.patch("app.agents.agent_1_intake.parse_message", return_value=parsed), \
             mock.patch("app.agents.agent_1_intake.get_active_session", return_value={"id": "s1", "business_id": 1}):
            prompt = self.intake.process("Sold 5 bags of rice 30k, how many bags left and what is my balance?")

        # Prompt requests confirmation for transaction & inventory
        self.assertIn("Please confirm this entry", prompt)
        self.assertIn("Sale (income)", prompt)
        self.assertIn("rice", prompt)
        self.assertIn("₦30,000", prompt)
        self.assertIn("Reply *YES* to record or *NO* to cancel", prompt)

        # The preserved payload retains query
        self.assertEqual(len(stored_payloads), 1)
        saved = stored_payloads[0]
        self.assertIn("query", saved)
        self.assertEqual(saved["query"]["query_type"], "balance")

    def test_confirmation_yes_executes_compound_and_returns_all_three_answers(self):
        """Replying YES to a pending compound transaction executes mutations and bundled query."""
        pending_json = {
            "_event_id": "e-pending-1",
            "intents": ["record_transaction", "inventory", "query"],
            "confidence": 0.95,
            "status": "ok",
            "transactions": [{
                "type": "income", "action": "sale", "amount": 30000.0,
                "currency": "NGN", "item": "rice", "category": "Sales",
                "description": "sold 5 bags of rice", "date": "2026-09-28"
            }],
            "inventory": [{
                "action": "REMOVE", "product": "rice", "quantity": 5.0, "unit": "bags"
            }],
            "query": {"query_type": "balance"}
        }
        pending_record = {
            "raw_text": "Sold 5 bags of rice 30k, how many bags left and what is my balance?",
            "parsed_json": pending_json
        }

        self.intake._load_pending = lambda: pending_record
        self.intake._clear_pending = mock.MagicMock()

        # Mock DB locking in _apply_confirmation
        conn = mock.MagicMock()
        cursor = mock.MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchone.return_value = {"id": "p1", "parsed_json": json.dumps(pending_json)}

        expected_reply = (
            "✅ Recorded: Sales — ₦30,000\n"
            "📦 Inventory Updated: rice stock level is now 15 bags.\n\n"
            "💰 *Your Balance*\n\n*Net Balance: ₦30,000* 📈"
        )

        with mock.patch("app.agents.agent_1_intake.get_db_connection", return_value=conn), \
             mock.patch.object(self.intake, "_publish_intake", return_value=[expected_reply]) as mock_pub:
            reply = self.intake.process("YES")

        self.intake._clear_pending.assert_called_once()
        self.assertEqual(reply, expected_reply)

        # Check published event payload
        call_kwargs = mock_pub.call_args.kwargs
        self.assertEqual(call_kwargs["intent"], "split_routing")
        self.assertEqual(call_kwargs["extracted_data"]["parsed"]["query"]["query_type"], "balance")
        self.assertEqual(len(call_kwargs["extracted_data"]["parsed"]["transactions"]), 1)
        self.assertEqual(len(call_kwargs["extracted_data"]["parsed"]["inventory"]), 1)


if __name__ == "__main__":
    unittest.main()
