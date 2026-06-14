"""WP-03 — Intake agent ported onto the Band connector.

Tests the Band-handoff seam against the in-process stub (no DB, no network): Intake
posts as a distinct room participant, @mentions Ledger, and collects the reply via
the reply-collection seam (G-05). Also guards that the retired broker is gone.
"""

import unittest

from app.agents import agent_1_intake
from app.agents.agent_1_intake import IntakeAgent, INTAKE_HANDLE, LEDGER_HANDLE
from app.agents.band.band_client import get_band_client


class TestIntakeBandPort(unittest.TestCase):
    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.agent = IntakeAgent("user-1", "sender-1", band=self.band)

    def test_bandsdk_import_is_gone(self):
        # WP-03 DoD: no BandSDK import remains in the module.
        self.assertFalse(hasattr(agent_1_intake, "BandSDK"))

    def test_posts_as_intake_mentions_ledger_and_collects_reply(self):
        # Fake Ledger: on an @tali-ledger message, post a terminal reply for the correlation id.
        def ledger(msg):
            self.band.send(self.agent.room_id, [INTAKE_HANDLE],
                           "Recorded: " + msg["body"]["payload"]["intent"],
                           correlation_id=msg["correlation_id"], sender=LEDGER_HANDLE, terminal=True)
        self.band.on_message(LEDGER_HANDLE, ledger)

        reply = self.agent._band_send_collect([LEDGER_HANDLE], {"payload": {"intent": "record_transaction"}})
        self.assertEqual(reply, "Recorded: record_transaction")

        # Intake posted as a distinct participant, @mentioning Ledger.
        first = self.band.read_context(self.agent.room_id)[0]
        self.assertEqual(first["sender"], INTAKE_HANDLE)
        self.assertIn(LEDGER_HANDLE, first["mentions"])

    def test_returns_none_when_no_handler_registered(self):
        # Pre-WP-04/06 in-app state (no Ledger/gateway yet) -> graceful None, not a hang.
        self.agent._reply_timeout = 0.2
        self.assertIsNone(self.agent._band_send_collect([LEDGER_HANDLE], {"payload": {"intent": "x"}}))


if __name__ == "__main__":
    unittest.main()
