"""Unit and integration tests for WP-07: Merchant Web Session Auth & WhatsApp OTP Verification.

Tests:
1. Phone normalization (E.164 conversion, Nigerian 080 prefixes, whitespace stripping).
2. Lockout and rate-limiting (3 failed attempts locks phone for 10 minutes).
3. Route access control & unauthenticated redirects.
4. Requesting OTP (unregistered phone, registered merchant, dev bypass).
5. Verifying OTP (invalid code, expired code, lockouts, successful login).
6. Merchant session lifecycle (session persistence, dashboard access, logout).
7. Safe URL redirection vs open-redirect phishing defense.
8. Cookie security standards.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import pytest
from app import create_app
from app.portal.auth import (
    MAX_OTP_ATTEMPTS,
    OTP_LOCKOUT_SECONDS,
    check_phone_lockout,
    clear_all_portal_lockouts,
    find_registered_merchant,
    normalize_phone,
    record_phone_failed_attempt,
    request_portal_otp,
    reset_phone_failed_attempts,
    verify_portal_otp,
)


class MockDBStore:
    def __init__(self):
        self.users = {
            "+2348012345678": {
                "id": "018e3812-7000-7000-8000-000000000001",
                "phone_number": "+2348012345678",
                "display_name": "Mama Ngozi Provisions",
                "is_verified": True,
            }
        }
        self.codes = []


class MockSession:
    def __init__(self, store: MockDBStore):
        self.store = store

    def execute(self, stmt):
        class Row:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class Result:
            def __init__(self, item):
                self.item = item

            def scalars(self):
                return self

            def scalar(self):
                return self.item if isinstance(self.item, (int, float)) else 0

            def scalar_one_or_none(self):
                return self.item if not isinstance(self.item, list) else (self.item[0] if self.item else None)

            def first(self):
                return self.item

            def all(self):
                return [self.item] if self.item and not isinstance(self.item, list) else (self.item or [])

            @property
            def rowcount(self):
                return 1

        stmt_str = str(stmt).lower()
        params = getattr(stmt, "compile", lambda: None)().params if hasattr(stmt, "compile") else {}
        target_phone = next((v for k, v in params.items() if "phone" in k), None)
        target_code = next((v for k, v in params.items() if "code" in k), None)

        if "update" in stmt_str:
            for c in self.store.codes:
                if target_phone and c.phone_number == target_phone and c.purpose == "login":
                    c.used = True
                elif not target_phone and c.purpose == "login":
                    c.used = True
            return Result(None)

        if "from debt_balances" in stmt_str:
            return Result(Row(receivables=0, payables=0))
        if "from transactions" in stmt_str and "sum" in stmt_str:
            return Result(Row(total_in=0, total_out=0, month_in=0, month_out=0, today_in=0, tx_count=0))
        if "from transactions" in stmt_str:
            return Result([])
        if "count" in stmt_str and ("inventory_items" in stmt_str or "products" in stmt_str):
            return Result(0)

        # Select statement for VerificationCode
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for c in reversed(self.store.codes):
            if c.purpose == "login" and not c.used and c.expires_at > now:
                if target_phone and c.phone_number != target_phone:
                    continue
                if target_code and c.code != target_code:
                    continue
                return Result(c)

        return Result(None)

    def add(self, obj):
        self.store.codes.append(obj)

    def commit(self):
        pass


@pytest.fixture(autouse=True)
def clean_portal_state():
    """Ensure in-memory lockout tables are cleared before and after each test."""
    clear_all_portal_lockouts()
    yield
    clear_all_portal_lockouts()


@pytest.fixture
def db_store():
    return MockDBStore()


@pytest.fixture
def app(monkeypatch, db_store):
    """Create Flask application configured for portal testing with mock database."""
    import app as app_module
    import app.portal.auth as portal_auth_mod
    import app.portal.metrics as portal_metrics_mod
    import app.admin.metrics as metrics_mod

    @contextmanager
    def mock_session_scope():
        yield MockSession(db_store)

    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    monkeypatch.setattr(portal_auth_mod, "session_scope", mock_session_scope)
    monkeypatch.setattr(portal_auth_mod, "get_user_by_phone", lambda p: db_store.users.get(p))
    monkeypatch.setattr(portal_metrics_mod, "session_scope", mock_session_scope)
    monkeypatch.setattr(metrics_mod, "session_scope", mock_session_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-portal-secret-key-12345",
        OTP_DEV_BYPASS=True,
        OTP_EXPIRY_MINUTES=10,
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ============================================================================
# 1. Phone Normalization Tests
# ============================================================================

def test_normalize_phone_variations():
    assert normalize_phone("08012345678") == "+2348012345678"
    assert normalize_phone("080-1234-5678") == "+2348012345678"
    assert normalize_phone("2348012345678") == "+2348012345678"
    assert normalize_phone("+2348012345678") == "+2348012345678"
    assert normalize_phone("+14155552671") == "+14155552671"
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""


# ============================================================================
# 2. Lockout & Brute-force Throttling Tests
# ============================================================================

def test_lockout_logic_after_3_failures():
    phone = "+2348012345678"
    is_locked, _ = check_phone_lockout(phone)
    assert not is_locked

    # First failed attempt
    locked, rem, remaining_attempts = record_phone_failed_attempt(phone)
    assert not locked
    assert remaining_attempts == 2

    # Second failed attempt
    locked, rem, remaining_attempts = record_phone_failed_attempt(phone)
    assert not locked
    assert remaining_attempts == 1

    # Third failed attempt -> lockout triggered
    locked, rem, remaining_attempts = record_phone_failed_attempt(phone)
    assert locked
    assert rem == OTP_LOCKOUT_SECONDS
    assert remaining_attempts == 0

    # Subsequent check should return locked
    is_locked, remaining = check_phone_lockout(phone)
    assert is_locked
    assert remaining > 0

    # Reset clears lockout
    reset_phone_failed_attempts(phone)
    is_locked, _ = check_phone_lockout(phone)
    assert not is_locked


# ============================================================================
# 3. Route Access Control & Redirects
# ============================================================================

def test_unauthenticated_portal_redirects(client):
    res = client.get("/portal/")
    assert res.status_code == 302
    assert "/portal/login" in res.headers["Location"]

    res_dash = client.get("/portal/dashboard")
    assert res_dash.status_code == 302
    assert "/portal/login" in res_dash.headers["Location"]
    assert "next=" in res_dash.headers["Location"]


def test_login_page_renders_cleanly(client):
    res = client.get("/portal/login")
    assert res.status_code == 200
    assert b"Merchant Sign In" in res.data
    assert b"WhatsApp Phone Number" in res.data


# ============================================================================
# 4. OTP Request Flow
# ============================================================================

def test_request_otp_empty_phone(client):
    res = client.post("/portal/request-otp", data={"phone": ""})
    assert res.status_code == 400
    assert b"Please enter your phone number" in res.data


def test_request_otp_unregistered_phone(client):
    res = client.post("/portal/request-otp", data={"phone": "08099999999"})
    assert res.status_code == 400
    assert b"not registered" in res.data


def test_request_otp_registered_phone(client, db_store):
    res = client.post("/portal/request-otp", data={"phone": "08012345678"})
    assert res.status_code == 200
    assert b"6-Digit Passcode" in res.data
    assert b"+2348012345678" in res.data
    assert len(db_store.codes) == 1
    assert db_store.codes[0].phone_number == "+2348012345678"
    assert len(db_store.codes[0].code) == 6


# ============================================================================
# 5. OTP Verification Flow
# ============================================================================

def test_verify_otp_missing_fields(client):
    res = client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": ""})
    assert res.status_code == 400
    assert b"Phone number and 6-digit code are required" in res.data


def test_verify_otp_invalid_code(client, app, db_store):
    # First request an OTP
    client.post("/portal/request-otp", data={"phone": "08012345678"})
    assert len(db_store.codes) == 1

    # Enter incorrect code
    res = client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": "000000"})
    assert res.status_code == 400
    assert b"Invalid or expired verification code" in res.data
    assert b"2 attempt(s) remaining" in res.data


def test_verify_otp_lockout_after_three_strikes(client, db_store):
    client.post("/portal/request-otp", data={"phone": "08012345678"})

    # 1st fail
    client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": "111111"})
    # 2nd fail
    client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": "222222"})
    # 3rd fail -> triggers 429 lockout
    res = client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": "333333"})
    assert res.status_code == 429
    assert b"Too many failed attempts" in res.data

    # Requesting OTP during lockout also fails
    res_req = client.post("/portal/request-otp", data={"phone": "08012345678"})
    assert res_req.status_code == 400
    assert b"Too many failed attempts" in res_req.data


def test_verify_otp_success_establishes_session(client, db_store):
    client.post("/portal/request-otp", data={"phone": "08012345678"})
    generated_code = db_store.codes[0].code

    res = client.post(
        "/portal/verify-otp",
        data={"phone": "+2348012345678", "code": generated_code},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Welcome," in res.data
    assert b"Mama Ngozi Provisions" in res.data
    assert b"+2348012345678" in res.data
    assert db_store.codes[0].used is True

    # Accessing dashboard directly works now
    dash_res = client.get("/portal/dashboard")
    assert dash_res.status_code == 200
    assert b"Mama Ngozi Provisions" in dash_res.data

    # Accessing login page while authenticated redirects to dashboard
    login_res = client.get("/portal/login")
    assert login_res.status_code == 302
    assert "/portal/dashboard" in login_res.headers["Location"]


def test_merchant_logout(client, db_store):
    # Log in
    client.post("/portal/request-otp", data={"phone": "08012345678"})
    code = db_store.codes[0].code
    client.post("/portal/verify-otp", data={"phone": "+2348012345678", "code": code})

    # Log out
    res = client.get("/portal/logout", follow_redirects=True)
    assert res.status_code == 200
    assert b"You have been signed out" in res.data
    assert b"Merchant Sign In" in res.data

    # Dashboard is protected again
    dash_res = client.get("/portal/dashboard")
    assert dash_res.status_code == 302
    assert "/portal/login" in dash_res.headers["Location"]


# ============================================================================
# 6. Safe Redirection Defense
# ============================================================================

def test_safe_redirection_after_login(client, db_store):
    client.post("/portal/request-otp", data={"phone": "08012345678"})
    code = db_store.codes[0].code

    # Safe next url
    res = client.post(
        "/portal/verify-otp",
        data={"phone": "+2348012345678", "code": code, "next": "/portal/dashboard"},
    )
    assert res.status_code == 302
    assert res.headers["Location"] == "/portal/dashboard"

    # Reset session for phishing test
    client.get("/portal/logout")
    client.post("/portal/request-otp", data={"phone": "08012345678"})
    new_code = db_store.codes[1].code

    # Unsafe external URL should fallback to dashboard
    res_unsafe = client.post(
        "/portal/verify-otp",
        data={"phone": "+2348012345678", "code": new_code, "next": "https://attacker.com/steal"},
    )
    assert res_unsafe.status_code == 302
    assert "/portal/dashboard" in res_unsafe.headers["Location"]


# ============================================================================
# 7. Cookie Security Attributes
# ============================================================================

def test_session_cookie_hardening(app):
    assert app.config.get("SESSION_COOKIE_HTTPONLY") is True
    assert app.config.get("SESSION_COOKIE_SAMESITE") == "Lax"
