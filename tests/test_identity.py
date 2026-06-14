"""WP-02 — multi-channel identity + binding tokens.

Unit-tests the pure pieces (no DB): token generation/expiry and the address-resolution
routing. The DB-backed CRUD (link/redeem/resolve against MySQL) is integration glue,
verified against a live DB + the 0005 migration.
"""

import re
from datetime import datetime, timedelta

import app.auth as auth
from app.data.models import ChannelAccount, BindingToken  # import sanity


def test_binding_token_format():
    toks = {auth.generate_binding_token() for _ in range(200)}
    assert len(toks) == 200                       # unique
    for t in toks:
        assert isinstance(t, str)
        assert 0 < len(t) <= 64                   # Telegram /start payload limit
        assert re.fullmatch(r"[A-Za-z0-9_-]+", t) # URL-safe / deep-link-safe charset


def test_binding_token_expiry():
    now = datetime(2026, 6, 14, 12, 0, 0)
    assert auth.binding_token_is_expired(now - timedelta(minutes=1), now) is True
    assert auth.binding_token_is_expired(now + timedelta(minutes=1), now) is False
    assert auth.binding_token_is_expired(None, now) is True


def test_resolve_user_by_address_routes_by_namespace(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "resolve_channel_user", lambda ch, cid: calls.append(("channel", ch, cid)) or {"id": "u"})
    monkeypatch.setattr(auth, "get_user_by_sender", lambda sid: calls.append(("legacy", sid)) or {"id": "u"})

    auth.resolve_user_by_address("wa:2348012345678")
    auth.resolve_user_by_address("tg:559912345")
    auth.resolve_user_by_address("2348012345678")    # bare legacy phone

    assert calls == [
        ("channel", "whatsapp", "2348012345678"),
        ("channel", "telegram", "559912345"),
        ("legacy", "2348012345678"),
    ]


def test_models_have_expected_tables():
    assert ChannelAccount.__tablename__ == "channel_accounts"
    assert BindingToken.__tablename__ == "binding_tokens"
    assert {"channel", "channel_user_id", "user_id"} <= set(ChannelAccount.__table__.columns.keys())
    assert {"token", "user_id", "expires_at", "used_at"} <= set(BindingToken.__table__.columns.keys())
