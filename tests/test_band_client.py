"""Unit tests for the Native Multi-Agent Orchestrator connector.

Proves the seam the agent ports build against: @mention delivery, fire-and-forget
``send``, the shared room blackboard via ``read_context``, and the event-driven
reply-collection seam that lets a synchronous caller get its answer back out of an async room.
"""

import os
import unittest

from app.agents.band.band_client import get_band_client, BandClient, _LiveBackend
from app.agents.orchestrator import OrchestratorClient, OrchestrationEngine, AgentRoom


class TestOrchestratorConnector(unittest.TestCase):
    def setUp(self):
        self.engine = OrchestrationEngine()
        self.client = OrchestratorClient(self.engine)
        self.room = "room-1"

    def test_default_backend_builds_client(self):
        os.environ.pop("BAND_BACKEND", None)
        client = get_band_client()
        self.assertIsInstance(client, BandClient)

    def test_send_is_fire_and_forget(self):
        # A handler that returns a value; send must NOT surface it (fire-and-forget).
        self.client.on_message("@ledger", lambda msg: "handler-return-value")
        ret = self.client.send(self.room, ["@ledger"], "hi", sender="@gateway")
        self.assertIsInstance(ret, str)                   # a unique message id
        self.assertNotEqual(ret, "handler-return-value")  # not the handler's return value

    def test_only_mentioned_agents_receive(self):
        got = []
        self.client.on_message("@cfo", lambda m: got.append(m))
        self.client.send(self.room, ["@ledger"], "not for cfo", sender="@gateway")
        self.assertEqual(got, [])

    def test_read_context_returns_room_log_in_order(self):
        self.client.send(self.room, ["@a"], "m1", sender="@x")
        self.client.send(self.room, ["@a"], "m2", sender="@x")
        self.client.send("other-room", ["@a"], "elsewhere", sender="@x")
        bodies = [m["body"] for m in self.client.read_context(self.room)]
        self.assertEqual(bodies, ["m1", "m2"])          # scoped strictly to the room

    def test_reply_round_trip_via_mention_and_collect(self):
        received = []

        def ledger_handler(msg):
            received.append(msg)
            # Ledger replies terminally with the same correlation id
            self.client.send(self.room, ["@gateway"], "recorded: " + msg["body"],
                             correlation_id=msg["correlation_id"], sender="@ledger", terminal=True)

        self.client.on_message("@ledger", ledger_handler)

        cid = "corr-123"
        self.client.send(self.room, ["@ledger"], "Sold rice 5000",
                         correlation_id=cid, sender="@gateway")

        reply = self.client.collect_reply(cid, timeout=2.0)
        self.assertEqual(reply, "recorded: Sold rice 5000")
        self.assertEqual(len(received), 1)

    def test_collect_reply_times_out_without_a_terminal_message(self):
        self.assertIsNone(self.client.collect_reply("no-such-corr", timeout=0.1))

    def test_terminal_reply_is_collected_not_redispatched(self):
        # A terminal reply is the END of a chain — it must NOT be dispatched to an @mentioned handler.
        calls = []
        self.client.on_message("@ledger", lambda m: calls.append(m))

        reply = self.client.send(self.room, ["@ledger"], {"approved": True, "reason": "ok"},
                                 correlation_id="rev-1", sender="@compliance", terminal=True)
        self.assertIsInstance(reply, str)                       # message id
        self.assertEqual(calls, [])                             # handler NOT re-entered
        self.assertEqual(self.client.collect_reply("rev-1", timeout=2.0),
                         {"approved": True, "reason": "ok"})    # collectable

    def test_multiple_mentions_all_receive(self):
        delivered = []
        self.client.on_message("@agent1", lambda m: delivered.append(("a1", m["body"])))
        self.client.on_message("@agent2", lambda m: delivered.append(("a2", m["body"])))

        self.client.send(self.room, ["@agent1", "@agent2"], "broadcast-payload", sender="@intake")
        self.assertEqual(len(delivered), 2)
        self.assertIn(("a1", "broadcast-payload"), delivered)
        self.assertIn(("a2", "broadcast-payload"), delivered)

    def test_room_context_limit(self):
        for i in range(10):
            self.client.send(self.room, ["@a"], f"msg-{i}")
        recent = self.client.read_context(self.room, limit=3)
        self.assertEqual(len(recent), 3)
        self.assertEqual([m["body"] for m in recent], ["msg-7", "msg-8", "msg-9"])


class TestNativeOrchestrationLiveCompatibility(unittest.TestCase):
    def test_live_backend_instantiates_cleanly_without_external_sdk(self):
        backend = _LiveBackend({"room_id": "room-live-1"})
        client = OrchestratorClient(backend)
        client.on_message("@cfo", lambda m: None)
        msg_id = client.send("room-live-1", ["@cfo"], "test live", sender="@intake")
        self.assertIsInstance(msg_id, str)
        ctx = client.read_context("room-live-1")
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["body"], "test live")


if __name__ == "__main__":
    unittest.main()
