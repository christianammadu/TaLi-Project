"""WP-05 — CFO ported onto a Band room handler.

CFO composes the final reply from the room event and posts it terminally so the
gateway/Intake can collect it (G-11). Tested against the in-process stub: the
escalation path needs no DB, and the ledger-update path is exercised with
handle_ledger_update patched (its DB logic is unchanged + tested elsewhere).
"""

import unittest
from unittest import mock

from app.agents.agent_3_cfo import CFOAgent, CFO_HANDLE, GATEWAY_HANDLE
from app.agents.band.band_client import get_band_client


def _split_routing_payload(new_stock):
    """A split_routing success event: one sale + one stock-out leaving `new_stock`."""
    return {
        "source_agent": "LedgerAgent", "event_type": "transaction", "user_id": "user-1",
        "payload": {
            "transaction_id": "tx-1", "status": "success", "intent": "split_routing",
            "raw_text": "sold 2 bags of satchel water 3000",
            "data": {
                "transactions": [{"id": "tx-1", "type": "income", "action": "sale", "amount": 3000,
                                  "currency": "NGN", "item": "satchel water", "category": "Sales",
                                  "description": "sold", "date": "2026-06-15"}],
                "inventory": [{"product": "satchel water", "action": "REMOVE", "quantity": 2,
                               "unit": "bags", "new_stock": new_stock}],
                "debts": [],
            },
        },
    }


def _escalation_body():
    return {
        "source_agent": "IntakeAgent",
        "event_type": "error",
        "payload": {"status": "needs_review", "message": "🤔 didn't catch that",
                    "raw_text": "asdf", "parsed": {}},
    }


class TestCFOBandPort(unittest.TestCase):
    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.cfo = CFOAgent("user-1", "sender-1", band=self.band)

    def test_compose_reply_rejected_and_error(self):
        rejected = {"source_agent": "LedgerAgent",
                    "payload": {"status": "rejected", "error_reason": "Compliance hold: duplicate"}}
        self.assertEqual(self.cfo._compose_reply(rejected), "🛑 Not recorded — Compliance hold: duplicate.")
        err = {"source_agent": "LedgerAgent", "payload": {"status": "error"}}
        self.assertIn("saving it failed", self.cfo._compose_reply(err))

    def test_synthesize_is_passthrough_by_default(self):
        self.assertEqual(self.cfo._synthesize("✅ Recorded: Sales — ₦5,000"), "✅ Recorded: Sales — ₦5,000")

    def test_on_room_message_posts_terminal_reply_for_escalation(self):
        msg = {"body": _escalation_body(), "correlation_id": "u1"}
        reply = self.cfo.on_room_message(msg)
        self.assertEqual(reply, "🤔 didn't catch that")
        posted = self.band.read_context(self.cfo.room_id)[-1]
        self.assertEqual(posted["sender"], CFO_HANDLE)
        self.assertIn(GATEWAY_HANDLE, posted["mentions"])
        self.assertTrue(posted["terminal"])
        self.assertEqual(posted["correlation_id"], "u1")

    def test_ledger_update_path_posts_terminal_reply(self):
        self.cfo.handle_ledger_update = lambda body: "✅ Recorded: Sales — ₦5,000"  # avoid DB
        msg = {"body": {"source_agent": "LedgerAgent", "payload": {"status": "success", "intent": "record_transaction"}},
               "correlation_id": "u2"}
        reply = self.cfo.on_room_message(msg)
        self.assertEqual(reply, "✅ Recorded: Sales — ₦5,000")

    def _run_ledger_update(self, payload):
        """Drive handle_ledger_update past its DB idempotency check + threshold lookup."""
        conn = mock.MagicMock()
        conn.cursor.return_value.fetchone.return_value = None   # not yet processed
        conn.is_connected.return_value = True
        thresholds = {"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000}
        with mock.patch("app.data.database.get_db_connection", return_value=conn), \
             mock.patch.object(self.cfo, "_get_evaluated_thresholds", return_value=thresholds):
            return self.cfo.handle_ledger_update(payload)

    def test_oversold_stock_records_and_nudges_to_reconcile(self):
        """A confirmed sale that drives stock negative still records, never returns raw JSON,
        and reads as a reconcile nudge (not a confusing 'low (-2 left)' warning)."""
        reply = self._run_ledger_update(_split_routing_payload(new_stock=-2))
        self.assertIn("Recorded", reply)                 # the sale was honoured
        self.assertIn("satchel water", reply)
        self.assertIn("reconcile", reply.lower())        # gentle nudge, not a block
        self.assertNotIn("is low", reply)                # negative != "low stock" warning
        self.assertNotIn('"status"', reply)              # no JSON leaked

    def test_positive_low_stock_still_warns(self):
        reply = self._run_ledger_update(_split_routing_payload(new_stock=3))
        self.assertIn("is low", reply)                   # 3 <= low_stock_limit(5) → warn

    def test_reply_is_collectable_end_to_end_through_the_room(self):
        # CFO registered as the @tali-cfo room handler; a forwarded escalation should
        # produce a reply collectable by the original correlation id.
        self.band.on_message(CFO_HANDLE, self.cfo.on_room_message)
        self.band.send(self.cfo.room_id, [CFO_HANDLE], _escalation_body(),
                       correlation_id="u9", sender="@tali-intake")
        self.assertEqual(self.band.collect_reply("u9", timeout=2.0), "🤔 didn't catch that")


if __name__ == "__main__":
    unittest.main()
