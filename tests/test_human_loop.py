"""WP-08 — human-in-the-loop approval surfaced in the Band room.

The durable gate is the pre-existing `pending_confirmations` DB flow; WP-08 makes the
human approval visible + auditable in the room. Tests the room-posting helper directly
(no DB): the approval request and the human's decision land as @tali-human events.
"""

import unittest

from app.agents.agent_1_intake import IntakeAgent, HUMAN_HANDLE, INTAKE_HANDLE
from app.agents.band.band_client import get_band_client


class TestHumanInLoop(unittest.TestCase):
    def setUp(self):
        self.band = get_band_client(backend="stub")
        self.agent = IntakeAgent("user-1", "sender-1", band=self.band)

    def _human_msgs(self):
        return [m for m in self.band.read_context(self.agent.room_id) if HUMAN_HANDLE in m["mentions"]]

    def test_approval_request_posted_to_human(self):
        self.agent._post_human_event({"type": "approval_request", "summary": "Record ₦5,000?",
                                      "raw_text": "sold rice 5000"})
        msgs = self._human_msgs()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["sender"], INTAKE_HANDLE)
        self.assertEqual(msgs[0]["body"]["type"], "approval_request")

    def test_human_decision_posted(self):
        self.agent._post_human_event({"type": "human_decision", "decision": "approved"})
        self.assertEqual(self._human_msgs()[-1]["body"]["decision"], "approved")

    def test_post_is_fire_and_forget_and_resilient(self):
        class _Boom:
            def send(self, *a, **k):
                raise RuntimeError("connector down")
        agent = IntakeAgent("u", "s", band=_Boom())
        agent._post_human_event({"type": "x"})  # must swallow — never break the user flow


if __name__ == "__main__":
    unittest.main()
