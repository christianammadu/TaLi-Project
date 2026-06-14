"""WP-04 — Ledger ported onto the Band connector + two-phase review gate (G-14).

Tests the propose→review→commit *gate* and the CFO emit against the in-process stub
(no DB, no network). The DB commit logic itself is unchanged and unit-tested elsewhere;
here we prove the gate's decision + that a reject withholds (returns not-approved).
"""

import os
import unittest

from app.agents import agent_2_ledger
from app.agents.agent_2_ledger import LedgerAgent, LEDGER_HANDLE, CFO_HANDLE, COMPLIANCE_HANDLE
from app.agents.band.band_client import get_band_client


class TestLedgerBandPort(unittest.TestCase):
    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.ledger = LedgerAgent("user-1", "sender-1", band=self.band)
        os.environ.pop("BAND_REVIEW_DEFAULT", None)

    def tearDown(self):
        os.environ.pop("BAND_REVIEW_DEFAULT", None)

    def test_bandsdk_import_is_gone(self):
        self.assertFalse(hasattr(agent_2_ledger, "BandSDK"))

    def test_review_gate_approves_on_verdict(self):
        self.band.on_message(COMPLIANCE_HANDLE, lambda m: self.band.send(
            self.ledger.room_id, [LEDGER_HANDLE], "approve",
            correlation_id=m["correlation_id"], sender=COMPLIANCE_HANDLE, terminal=True))
        approved, _ = self.ledger._review_gate({"intent": "split_routing"})
        self.assertTrue(approved)

    def test_review_gate_rejects_and_carries_reason(self):
        self.band.on_message(COMPLIANCE_HANDLE, lambda m: self.band.send(
            self.ledger.room_id, [LEDGER_HANDLE], {"approved": False, "reason": "duplicate"},
            correlation_id=m["correlation_id"], sender=COMPLIANCE_HANDLE, terminal=True))
        approved, reason = self.ledger._review_gate({"intent": "split_routing"})
        self.assertFalse(approved)
        self.assertEqual(reason, "duplicate")

    def test_no_reviewer_default_allow(self):
        self.ledger._review_timeout = 0.2          # no @tali-compliance handler registered
        approved, _ = self.ledger._review_gate({"intent": "x"})
        self.assertTrue(approved)                  # dev default

    def test_no_reviewer_default_deny_is_strict(self):
        os.environ["BAND_REVIEW_DEFAULT"] = "deny"
        self.ledger._review_timeout = 0.2
        approved, _ = self.ledger._review_gate({"intent": "x"})
        self.assertFalse(approved)                 # strict prod posture

    def test_emit_to_cfo_threads_user_correlation_id(self):
        self.ledger._user_cid = "user-9"
        self.ledger._emit_to_cfo({"status": "success"})
        cfo_msgs = [m for m in self.band.read_context(self.ledger.room_id) if CFO_HANDLE in m["mentions"]]
        self.assertEqual(len(cfo_msgs), 1)
        self.assertEqual(cfo_msgs[0]["sender"], LEDGER_HANDLE)
        self.assertEqual(cfo_msgs[0]["correlation_id"], "user-9")


if __name__ == "__main__":
    unittest.main()
