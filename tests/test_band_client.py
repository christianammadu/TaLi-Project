"""Unit tests for the Band connector stub (WP-02 / G-BAND-CONTRACT).

Proves the seam the agent ports build against: @mention delivery, a fire-and-forget
``send`` (no synchronous return value, unlike the retired broker — G-06), the shared
room log via ``read_context``, and the reply-collection seam (G-05) that lets a
synchronous caller get its answer back out of an async room.
"""

import os
import unittest

from app.agents.band.band_client import get_band_client, BandClient


class TestBandStubConnector(unittest.TestCase):
    def setUp(self):
        self.client = get_band_client(backend="stub")
        self.room = "room-1"

    def test_default_backend_is_stub(self):
        os.environ.pop("BAND_BACKEND", None)
        self.assertIsInstance(get_band_client(), BandClient)  # builds with no creds => stub

    def test_send_is_fire_and_forget(self):
        # A handler that returns a value; send must NOT surface it (fire-and-forget).
        self.client.on_message("@ledger", lambda msg: "handler-return-value")
        ret = self.client.send(self.room, ["@ledger"], "hi", sender="@gateway")
        self.assertIsInstance(ret, str)                 # a message id...
        self.assertNotEqual(ret, "handler-return-value")  # ...not the handler's return

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
        self.assertEqual(bodies, ["m1", "m2"])          # scoped to the room

    def test_reply_round_trip_via_mention_and_collect(self):
        received = []

        def ledger_handler(msg):
            received.append(msg)
            # Ledger replies terminally with the same correlation id (the seam, G-05).
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
        self.assertIsNone(self.client.collect_reply("no-such-corr", timeout=0.2))

    def test_terminal_reply_is_collected_not_redispatched(self):
        # Regression: a terminal reply is a point-to-point answer for collect_reply, the
        # END of a chain — it must NOT also be dispatched to an @mentioned handler. The
        # Compliance verdict posts terminally @mentioning @tali-ledger; re-entering the
        # Ledger handler there corrupted its per-message state and tripped schema errors.
        calls = []
        self.client.on_message("@ledger", lambda m: calls.append(m))

        reply = self.client.send(self.room, ["@ledger"], {"approved": True, "reason": "ok"},
                                 correlation_id="rev-1", sender="@compliance", terminal=True)
        self.assertIsInstance(reply, str)                       # message id
        self.assertEqual(calls, [])                             # handler NOT re-entered
        self.assertEqual(self.client.collect_reply("rev-1", timeout=2.0),
                         {"approved": True, "reason": "ok"})    # but still collectable


if __name__ == "__main__":
    unittest.main()
