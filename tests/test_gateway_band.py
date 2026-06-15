"""WP-06 — webhook→room gateway replaces the in-memory broker.

Verifies the broker is gone, all agents share ONE Band connector, the room handlers
are wired, and a message routed through the shared client comes back collectable.
Constructing AgentRouter touches no DB; route() (which needs a session/DB) is not called.
"""

import importlib
import unittest
from unittest import mock

from app.agents.agent_router import AgentRouter
from app.agents.agent_2_ledger import LEDGER_HANDLE, CFO_HANDLE
from app.agents.agent_3_cfo import GATEWAY_HANDLE


def _escalation_body():
    return {"source_agent": "IntakeAgent", "event_type": "error",
            "payload": {"status": "needs_review", "message": "🤔 didn't catch that",
                        "raw_text": "x", "parsed": {}}}


class TestBandGateway(unittest.TestCase):
    def setUp(self):
        self.router = AgentRouter(user_id="user-1", sender_id="sender-1")

    def test_in_memory_broker_is_deleted(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("app.agents.band_sdk")

    def test_all_agents_share_one_connector(self):
        r = self.router
        self.assertIs(r.intake.band, r.band)
        self.assertIs(r.ledger.band, r.band)
        self.assertIs(r.cfo.band, r.band)

    def test_room_handlers_are_wired(self):
        handlers = self.router.band._backend._handlers
        self.assertIn(LEDGER_HANDLE, handlers)
        self.assertIn(CFO_HANDLE, handlers)

    def test_message_routed_through_shared_client_comes_back_collectable(self):
        # A message @mentioning the CFO is handled by the wired CFO and replied terminally.
        self.router.band.send(self.router.cfo.room_id, [CFO_HANDLE], _escalation_body(),
                              correlation_id="u1", sender="@tali-intake")
        reply = self.router.band.collect_reply("u1", timeout=2.0)
        self.assertEqual(reply, "🤔 didn't catch that")

    def test_duplicate_webhook_is_dropped(self):
        """An already-seen message_id (claim updates 0 rows, the row still exists) is
        dropped without reaching Intake — webhook idempotency."""
        class _Cur:
            rowcount = 0                       # claim matched nothing (already processing/processed)
            def execute(self, *a, **k): pass
            def fetchone(self): return {"status": "processed"}
            def close(self): pass
        class _Conn:
            def cursor(self, dictionary=False): return _Cur()
            def commit(self): pass
            def is_connected(self): return True
            def close(self): pass
        with mock.patch("app.agents.agent_router.get_active_session", return_value={"user_id": 1}), \
             mock.patch("app.agents.agent_router.get_db_connection", return_value=_Conn()):
            res = self.router.route("hello", message_id="m-dup")
        self.assertEqual(res, "__DUPLICATE_DROP__")

    def test_cfo_posts_terminal_reply_to_gateway(self):
        self.router.band.send(self.router.cfo.room_id, [CFO_HANDLE], _escalation_body(),
                              correlation_id="u2", sender="@tali-intake")
        terminal = [m for m in self.router.band.read_context(self.router.cfo.room_id)
                    if m.get("terminal")][-1]
        self.assertIn(GATEWAY_HANDLE, terminal["mentions"])


if __name__ == "__main__":
    unittest.main()
