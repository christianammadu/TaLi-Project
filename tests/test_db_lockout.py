"""Unit tests for multi-worker DB-backed lockout defense (G-08)."""

import pytest
import time
from unittest.mock import MagicMock
from contextlib import contextmanager
from flask import Flask

from app.admin.auth import check_lockout, record_failed_attempt, reset_failed_attempts, clear_all_lockouts
from app.portal.auth import check_phone_lockout, record_phone_failed_attempt, reset_phone_failed_attempts, clear_all_portal_lockouts
from app.data.models import LoginAttempt


class FakeDBStore:
    def __init__(self):
        self.records = {}

    def get(self, model, key):
        return self.records.get(key)

    def add(self, obj):
        self.records[obj.attempt_key] = obj

    def delete(self, obj):
        self.records.pop(obj.attempt_key, None)

    def execute(self, stmt):
        self.records.clear()


@pytest.fixture
def fake_db(monkeypatch):
    store = FakeDBStore()

    @contextmanager
    def mock_scope():
        yield store

    monkeypatch.setattr("app.data.db.session_scope", mock_scope)
    return store


@pytest.fixture
def db_lockout_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-db-lockout-key",
        TESTING=True,
        DB_LOCKOUT_TESTING=True,  # Enables DB path during test
    )
    return app


def test_admin_lockout_multi_worker_persistence(db_lockout_app, fake_db):
    with db_lockout_app.app_context():
        clear_all_lockouts()
        key = "192.168.1.1:admin"

        # Record 4 failed attempts - not locked yet
        for _ in range(4):
            locked, secs = record_failed_attempt(key)
            assert locked is False

        assert "admin:" + key in fake_db.records
        assert fake_db.records["admin:" + key].attempts == 4

        # 5th attempt triggers lockout
        locked, secs = record_failed_attempt(key)
        assert locked is True
        assert secs > 0
        assert fake_db.records["admin:" + key].locked_until > time.time()

        # check_lockout reads from DB
        is_locked, rem = check_lockout(key)
        assert is_locked is True
        assert rem > 0

        # Successful login resets the DB record
        reset_failed_attempts(key)
        assert "admin:" + key not in fake_db.records

        is_locked, rem = check_lockout(key)
        assert is_locked is False


def test_portal_phone_lockout_multi_worker_persistence(db_lockout_app, fake_db):
    with db_lockout_app.app_context():
        clear_all_portal_lockouts()
        phone = "+2348011223344"

        # Record 2 failed attempts - not locked
        for _ in range(2):
            locked, secs, rem_attempts = record_phone_failed_attempt(phone)
            assert locked is False

        assert "portal:" + phone in fake_db.records
        assert fake_db.records["portal:" + phone].attempts == 2

        # 3rd attempt triggers lockout
        locked, secs, rem_attempts = record_phone_failed_attempt(phone)
        assert locked is True
        assert secs > 0
        assert rem_attempts == 0
        assert fake_db.records["portal:" + phone].locked_until > time.time()

        # check_phone_lockout reads from DB
        is_locked, rem = check_phone_lockout(phone)
        assert is_locked is True
        assert rem > 0

        # Successful OTP resets DB record
        reset_phone_failed_attempts(phone)
        assert "portal:" + phone not in fake_db.records

        is_locked, rem = check_phone_lockout(phone)
        assert is_locked is False
