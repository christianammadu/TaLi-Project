"""WP-09 — audit-trail assembly (Regulated track).

Unit-tests the pure `assemble_trail` (chronological ordering + summary). The DB-querying
`lifecycle_for` / `_rows_from_db` are integration glue verified against a live DB.
"""

import unittest

from app.services.audit import assemble_trail


class TestAuditTrail(unittest.TestCase):
    def test_orders_events_chronologically(self):
        events = [
            {"ts": "2026-06-14T20:00:03", "stage": "write", "actor": "LedgerAgent", "detail": "sale rice 5000 NGN"},
            {"ts": "2026-06-14T20:00:01", "stage": "parse", "actor": "IntakeAgent", "model": "Qwen/Qwen2.5-72B-Instruct", "cost": 0.0009},
            {"ts": "2026-06-14T20:00:02", "stage": "handoff", "actor": "LedgerAgent", "detail": "processed"},
        ]
        trail = assemble_trail("evt-1", events)
        self.assertEqual([e["stage"] for e in trail["events"]], ["parse", "handoff", "write"])
        self.assertEqual(trail["event_id"], "evt-1")

    def test_summary_aggregates_models_cost_agents(self):
        events = [
            {"ts": "1", "stage": "parse", "actor": "IntakeAgent", "model": "Qwen2.5-72B", "cost": 0.001},
            {"ts": "2", "stage": "synth", "actor": "CFOAgent", "model": "gpt-4o", "cost": 0.004},
            {"ts": "3", "stage": "write", "actor": "LedgerAgent"},
        ]
        s = assemble_trail("evt-2", events)["summary"]
        self.assertEqual(s["models"], ["Qwen2.5-72B", "gpt-4o"])
        self.assertAlmostEqual(s["total_cost"], 0.005)
        self.assertEqual(s["agents"], ["CFOAgent", "IntakeAgent", "LedgerAgent"])

    def test_approved_reflects_verdicts(self):
        approved_room = [{"ts": "9", "stage": "review", "actor": "ComplianceAgent", "approved": True},
                         {"ts": "10", "stage": "human", "actor": "@tali-human", "approved": True}]
        self.assertTrue(assemble_trail("e", [], room_events=approved_room)["summary"]["approved"])

        rejected_room = [{"ts": "9", "stage": "review", "actor": "ComplianceAgent", "approved": False}]
        self.assertFalse(assemble_trail("e", [], room_events=rejected_room)["summary"]["approved"])

    def test_no_verdict_is_none_and_empty_is_zero_cost(self):
        s = assemble_trail("e", [])["summary"]
        self.assertIsNone(s["approved"])
        self.assertEqual(s["total_cost"], 0)


if __name__ == "__main__":
    unittest.main()
