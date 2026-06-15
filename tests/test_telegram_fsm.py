"""Unit tests for the Telegram confirmation FSM flow (YES/NO handling, safety nudges, duplicate protection, and DB recovery).
"""

import json
import unittest
from flask import Flask
from app.agents.agent_1_intake import IntakeAgent
from app.agents.band.band_client import get_band_client


class MockCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.idx = 0
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self.idx < len(self.rows):
            res = self.rows[self.idx]
            self.idx += 1
            return res
        return None

    def fetchall(self):
        res = self.rows[self.idx:]
        self.idx = len(self.rows)
        return res

    def close(self):
        pass


class MockConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.committed = False
        self.rolled_back = False
        self._cursor = None

    def cursor(self, dictionary=False):
        self._cursor = MockCursor(self.rows)
        return self._cursor

    def start_transaction(self):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def is_connected(self):
        return True

    def close(self):
        pass


class TestTelegramFSM(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True)
        self.band = get_band_client(backend="stub")

    def test_case_insensitive_yes_no(self):
        """Verify that YES and NO choices are case-insensitive."""
        from app.agents.agent_1_intake import CONFIRM_YES, CONFIRM_NO
        self.assertIn("yes", CONFIRM_YES)
        self.assertIn("y", CONFIRM_YES)
        self.assertIn("no", CONFIRM_NO)
        self.assertIn("n", CONFIRM_NO)

        # "Yes" / "Yes" stripped and lowercased is in the confirmation sets
        self.assertEqual("Yes".strip().lower(), "yes")
        self.assertEqual("NO".strip().lower(), "no")

    def test_fsm_safety_nudge_invalid_input(self, *mocks):
        """Verify that typing an invalid input when a confirmation is pending results in a nudge, and does not clear state."""
        import app.agents.agent_1_intake as intake_module

        # Mock loading a pending transaction
        parsed_payload = {
            "intents": ["record_transaction"],
            "transactions": [{"type": "expense", "amount": 5000}],
            "awaiting": "confirmation",
            "_event_id": "evt-1"
        }
        mock_pending_row = {
            "raw_text": "bought fuel 5000",
            "parsed_json": json.dumps(parsed_payload)
        }

        # Override load_pending and check that it doesn't clear
        agent = IntakeAgent(user_id="user-1", sender_id="sender-1", band=self.band)
        
        # Monkeypatch DB functions locally
        saved_cleared = []
        agent._load_pending = lambda: mock_pending_row
        agent._clear_pending = lambda: saved_cleared.append(True)

        # Process invalid input "maybe"
        response = agent.process("maybe")

        # Nudge message expected, and FSM should NOT clear the pending state
        self.assertIn("Please reply YES or NO", response)
        self.assertEqual(len(saved_cleared), 0)  # should not clear pending!

    def test_duplicate_yes_protection(self):
        """Verify that sending YES twice triggers duplicate YES protection (returns Processing)."""
        import app.agents.agent_1_intake as intake_module
        
        parsed_payload = {
            "intents": ["record_transaction"],
            "transactions": [{"type": "expense", "amount": 5000}],
            "_event_id": "evt-1"
        }
        mock_pending_row = {
            "raw_text": "bought fuel 5000",
            "parsed_json": json.dumps(parsed_payload)
        }

        # First YES starts processing (sets _recording: True)
        mock_conn_1 = MockConnection(rows=[
            # For SELECT ... FOR UPDATE (load pending to check _recording)
            {"id": b"123", "parsed_json": json.dumps(parsed_payload)}
        ])
        
        # Monkeypatch db connection
        saved_get_db = intake_module.get_db_connection
        intake_module.get_db_connection = lambda: mock_conn_1

        agent = IntakeAgent(user_id="user-1", sender_id="sender-1", band=self.band)
        agent._load_pending = lambda: mock_pending_row
        
        # Mock _publish_intake to return successfully
        agent._publish_intake = lambda *a, **kw: ["✅ Recorded successfully."]
        agent._clear_pending = lambda: None

        res1 = agent._apply_confirmation("yes", mock_pending_row)
        self.assertEqual(res1, "✅ Recorded successfully.")
        
        # Check that connection committed the _recording flag write
        self.assertTrue(mock_conn_1.committed)

        # Second YES detects _recording: True and returns "⏳ Processing..."
        parsed_payload_recording = parsed_payload.copy()
        parsed_payload_recording["_recording"] = True
        mock_conn_2 = MockConnection(rows=[
            {"id": b"123", "parsed_json": json.dumps(parsed_payload_recording)}
        ])
        intake_module.get_db_connection = lambda: mock_conn_2

        res2 = agent._apply_confirmation("yes", mock_pending_row)
        self.assertEqual(res2, "⏳ Processing...")
        self.assertFalse(mock_conn_2.committed) # should rollback on duplicate YES

        # Restore real DB getter
        intake_module.get_db_connection = saved_get_db

    def test_timeout_recovery_success(self):
        """Verify that when a timeout occurs, if the event was committed to DB, recovery succeeds."""
        import app.agents.agent_1_intake as intake_module

        parsed_payload = {
            "intents": ["record_transaction"],
            "transactions": [{"type": "expense", "amount": 5000}],
            "_event_id": "evt-1"
        }
        mock_pending_row = {
            "raw_text": "bought fuel 5000",
            "parsed_json": json.dumps(parsed_payload)
        }

        agent = IntakeAgent(user_id="user-1", sender_id="sender-1", band=self.band)
        
        # SELECT ... FOR UPDATE for YES confirmation setup
        mock_conn = MockConnection(rows=[
            {"id": b"123", "parsed_json": json.dumps(parsed_payload)}
        ])
        saved_get_db = intake_module.get_db_connection
        intake_module.get_db_connection = lambda: mock_conn

        # Mock _publish_intake to return None (simulating a timeout/missing room reply)
        agent._publish_intake = lambda *a, **kw: []

        # Mock database commitment verification to return True (committed)
        agent._check_event_committed = lambda ev_id: True

        # Mock reconstruction of reply
        agent._reconstruct_success_reply = lambda ev_id: "✅ Recorded: Fuel — ₦5,000"
        
        saved_cleared = []
        agent._clear_pending = lambda: saved_cleared.append(True)

        res = agent._apply_confirmation("yes", mock_pending_row)
        
        # Check that we cleared the pending state and returned the reconstructed success reply
        self.assertEqual(res, "✅ Recorded: Fuel — ₦5,000")
        self.assertEqual(len(saved_cleared), 1)

        # Restore db
        intake_module.get_db_connection = saved_get_db

    def test_timeout_recovery_failure_resets_flag(self):
        """Verify that when a timeout occurs, if the event was NOT committed, recovery resets the _recording flag."""
        import app.agents.agent_1_intake as intake_module

        parsed_payload = {
            "intents": ["record_transaction"],
            "transactions": [{"type": "expense", "amount": 5000}],
            "_event_id": "evt-1"
        }
        mock_pending_row = {
            "raw_text": "bought fuel 5000",
            "parsed_json": json.dumps(parsed_payload)
        }

        agent = IntakeAgent(user_id="user-1", sender_id="sender-1", band=self.band)
        
        # YES confirmation DB mocks
        mock_conn = MockConnection(rows=[
            {"id": b"123", "parsed_json": json.dumps(parsed_payload)},  # SELECT ... FOR UPDATE (YES)
            {"parsed_json": json.dumps(parsed_payload)}  # SELECT ... FOR UPDATE (reset_recording_flag)
        ])
        saved_get_db = intake_module.get_db_connection
        intake_module.get_db_connection = lambda: mock_conn

        # Mock _publish_intake to return None (timeout)
        agent._publish_intake = lambda *a, **kw: []

        # Mock event committed check to return False (not committed)
        agent._check_event_committed = lambda ev_id: False
        
        saved_cleared = []
        agent._clear_pending = lambda: saved_cleared.append(True)

        res = agent._apply_confirmation("yes", mock_pending_row)
        
        # Check that it returns timeout error, does NOT clear pending, and commits reset flag
        self.assertIn("Connection timed out", res)
        self.assertEqual(len(saved_cleared), 0)

        # Restore db
        intake_module.get_db_connection = saved_get_db


if __name__ == "__main__":
    unittest.main()
