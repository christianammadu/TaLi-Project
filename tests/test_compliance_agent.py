"""WP-07 — Compliance/Reviewer agent (the review leg).

Tests the rule-based verdict, the room verdict-post, and the end-to-end two-phase gate:
the Ledger's _review_gate consulting a live Compliance agent over the shared stub and a
flagged write being rejected pre-commit. Plus the gateway auto-wiring it into the room.
"""

import os
import unittest

from app.agents.compliance_agent import ComplianceAgent, COMPLIANCE_HANDLE, LEDGER_HANDLE
from app.agents.agent_2_ledger import LedgerAgent
from app.agents.agent_router import AgentRouter
from app.agents.band.band_client import get_band_client


class TestComplianceAgent(unittest.TestCase):
    def setUp(self):
        os.environ.pop("COMPLIANCE_LARGE_AMOUNT", None)   # default 100,000
        self.band = get_band_client(backend="stub")
        self.compliance = ComplianceAgent("user-1", "sender-1", band=self.band)

    def test_review_approves_normal_amount(self):
        approved, reason = self.compliance.review({"intent": "record_transaction", "amount": 5000})
        self.assertTrue(approved)
        self.assertEqual(reason, "ok")

    def test_review_rejects_over_threshold(self):
        approved, reason = self.compliance.review({"intent": "record_transaction", "amount": 250000})
        self.assertFalse(approved)
        self.assertIn("exceeds the review threshold", reason)

    def test_on_room_message_posts_verdict_to_ledger(self):
        msg = {"body": {"type": "proposed_write", "proposed": {"amount": 250000}},
               "correlation_id": "rev-1"}
        verdict = self.compliance.on_room_message(msg)
        self.assertFalse(verdict["approved"])
        posted = [m for m in self.band.read_context(self.compliance.room_id)
                  if LEDGER_HANDLE in m["mentions"]][-1]
        self.assertEqual(posted["sender"], COMPLIANCE_HANDLE)
        self.assertEqual(posted["correlation_id"], "rev-1")
        self.assertTrue(posted["terminal"])

    def test_ledger_review_gate_rejects_flagged_write_end_to_end(self):
        # Wire a live Compliance reviewer onto the shared connector, then drive the
        # Ledger's two-phase gate through it (the WP-07 DoD).
        ledger = LedgerAgent("user-1", "sender-1", band=self.band)
        self.band.on_message(COMPLIANCE_HANDLE, self.compliance.on_room_message)

        approved, reason = ledger._review_gate({"intent": "record_transaction", "amount": 250000})
        self.assertFalse(approved)                          # rejected pre-commit
        self.assertIn("exceeds the review threshold", reason)

        approved_ok, _ = ledger._review_gate({"intent": "record_transaction", "amount": 5000})
        self.assertTrue(approved_ok)                        # normal write approved

    def test_gateway_auto_wires_compliance(self):
        router = AgentRouter(user_id="user-1", sender_id="sender-1")
        self.assertTrue(hasattr(router, "compliance"))
        self.assertIn(COMPLIANCE_HANDLE, router.band._backend._handlers)


if __name__ == "__main__":
    unittest.main()
