"""WP-05 — CFO ported onto a Band room handler.

CFO composes the final reply from the room event and posts it terminally so the
gateway/Intake can collect it (G-11). Tested against the in-process stub: the
escalation path needs no DB, and the ledger-update path is exercised with
handle_ledger_update patched (its DB logic is unchanged + tested elsewhere).
"""

import unittest

from app.agents.agent_3_cfo import CFOAgent, CFO_HANDLE, GATEWAY_HANDLE
from app.agents.band.band_client import get_band_client


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

    def test_reply_is_collectable_end_to_end_through_the_room(self):
        # CFO registered as the @tali-cfo room handler; a forwarded escalation should
        # produce a reply collectable by the original correlation id.
        self.band.on_message(CFO_HANDLE, self.cfo.on_room_message)
        self.band.send(self.cfo.room_id, [CFO_HANDLE], _escalation_body(),
                       correlation_id="u9", sender="@tali-intake")
        self.assertEqual(self.band.collect_reply("u9", timeout=2.0), "🤔 didn't catch that")


if __name__ == "__main__":
    unittest.main()
