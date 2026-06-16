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


class TestBandLiveBackend(unittest.TestCase):
    def test_live_backend_mirror_posts_to_messages_endpoint(self):
        from unittest.mock import MagicMock
        from app.agents.band.band_client import _LiveBackend

        config = {
            "rest_url": "https://fake.band.ai",
            "room_id": "room-123",
            "agents": {
                "@tali-intake": {"agent_id": "intake-id", "api_key": "intake-key", "remote_handle": "tali/tali-intake"},
                "@tali-cfo": {"agent_id": "cfo-id", "api_key": "cfo-key", "remote_handle": "tali/tali-cfo"}
            }
        }

        backend = _LiveBackend(config)
        backend._resolve_room = lambda: "room-123"

        post_calls = []
        def fake_post(url, headers, json, timeout):
            post_calls.append((url, headers, json))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        backend._requests = MagicMock()
        backend._requests.post = fake_post
        backend._mirror_on = True

        # Case 1: Send with targets (Intake mentions CFO)
        backend._mirror(["@tali-cfo"], "Hello CFO", sender="@tali-intake")
        self.assertEqual(len(post_calls), 1)
        url, headers, json_payload = post_calls[0]
        self.assertEqual(url, "https://fake.band.ai/api/v1/agent/chats/room-123/messages")
        self.assertEqual(headers["X-API-Key"], "intake-key")
        self.assertIn("@tali/tali-cfo", json_payload["message"]["content"])

        # Case 2: Send with no registered targets (CFO replies to gateway)
        post_calls.clear()
        backend._mirror(["@tali-gateway"], "Terminal reply", sender="@tali-cfo")
        self.assertEqual(len(post_calls), 1)
        url, headers, json_payload = post_calls[0]
        # Should post to messages path as a standard message instead of events path!
        self.assertEqual(url, "https://fake.band.ai/api/v1/agent/chats/room-123/messages")
        self.assertEqual(headers["X-API-Key"], "cfo-key")
        self.assertIn("@tali-gateway", json_payload["message"]["content"])
        self.assertIn("Terminal reply", json_payload["message"]["content"])


if __name__ == "__main__":
    unittest.main()

