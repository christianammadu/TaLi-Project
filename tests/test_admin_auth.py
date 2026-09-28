"""Unit and integration tests for WP-04: Admin Flask Blueprint & Stakeholder Session Auth.

Tests:
1. Route access control & redirects:
   - Unauthenticated GET /admin/ -> redirects to /admin/dashboard -> redirects to /admin/login.
   - Unauthenticated GET /admin/dashboard -> redirects to /admin/login?next=...
   - Authenticated GET /admin/dashboard -> 200 OK with dashboard metrics.
   - Authenticated GET /admin/login -> redirects to /admin/dashboard.
2. Stakeholder authentication:
   - Valid credentials log in successfully and redirect to dashboard.
   - Invalid credentials return 401 with error flash.
   - Bcrypt hash verification with fallback support.
3. Brute-force lockout enforcement (G-08):
   - 5 failed attempts trigger 429 Too Many Requests lockout.
   - Locked IP receives 429 on subsequent attempts.
   - Successful login resets failed attempts counter.
4. Session lifecycle & cookie hardening:
   - Logout clears session and redirects to /admin/login.
   - Session cookie security attributes (HttpOnly, SameSite).
"""

import pytest
import time
from app import create_app
from app.admin.auth import (
    authenticate_stakeholder,
    check_lockout,
    record_failed_attempt,
    reset_failed_attempts,
    clear_all_lockouts,
    LOCKOUT_DURATION_SECONDS,
    MAX_FAILED_ATTEMPTS
)


@pytest.fixture(autouse=True)
def clean_lockout_state():
    """Ensure in-memory lockout tables are cleared before and after each test."""
    clear_all_lockouts()
    yield
    clear_all_lockouts()


@pytest.fixture
def app(monkeypatch):
    """Create Flask application configured for admin testing."""
    import app as app_module
    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-admin-secret-key-12345",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="tali-admin-secret-2026",
        # Pre-computed bcrypt hash for 'tali-admin-secret-2026'
        ADMIN_PASSWORD_HASH="$2b$12$wqX7NM/IDlJPCRis5l7jhuKPvk1A7nJGoZUtnELbWASCQdBt6oGYu",
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ============================================================================
# 1. Direct Auth Unit Tests
# ============================================================================

def test_authenticate_stakeholder_bcrypt_success(app):
    with app.app_context():
        assert authenticate_stakeholder("admin", "tali-admin-secret-2026") is True


def test_authenticate_stakeholder_invalid_password(app):
    with app.app_context():
        assert authenticate_stakeholder("admin", "wrong-password") is False


def test_authenticate_stakeholder_invalid_username(app):
    with app.app_context():
        assert authenticate_stakeholder("intruder", "tali-admin-secret-2026") is False


def test_authenticate_stakeholder_plaintext_fallback(app):
    with app.app_context():
        # Clear the hash to test plaintext fallback
        app.config["ADMIN_PASSWORD_HASH"] = ""
        app.config["ADMIN_PASSWORD"] = "fallback-pass-99"
        assert authenticate_stakeholder("admin", "fallback-pass-99") is True
        assert authenticate_stakeholder("admin", "bad-pass") is False


def test_lockout_logic_after_5_failures():
    key = "127.0.0.1:admin"
    is_locked, _ = check_lockout(key)
    assert not is_locked

    for i in range(1, MAX_FAILED_ATTEMPTS):
        locked, rem = record_failed_attempt(key)
        assert not locked
        assert rem == 0

    # 5th attempt triggers lockout
    locked, rem = record_failed_attempt(key)
    assert locked is True
    assert 0 < rem <= LOCKOUT_DURATION_SECONDS

    # Immediate subsequent check confirms lockout
    is_locked, rem = check_lockout(key)
    assert is_locked is True
    assert rem > 0

    # Reset clears lockout
    reset_failed_attempts(key)
    is_locked, _ = check_lockout(key)
    assert not is_locked


# ============================================================================
# 2. HTTP Endpoint & Redirection Tests
# ============================================================================

def test_admin_index_redirects_to_dashboard(client):
    res = client.get("/admin/")
    assert res.status_code == 302
    assert "/admin/dashboard" in res.headers["Location"]


def test_unauthenticated_dashboard_redirects_to_login(client):
    res = client.get("/admin/dashboard")
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]
    assert "next=" in res.headers["Location"]


def test_get_login_page_renders_form(client):
    res = client.get("/admin/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "TaLi" in html
    assert "Command &amp; Governance" in html or "Command & Governance" in html
    assert 'name="username"' in html
    assert 'name="password"' in html


def test_successful_login_and_dashboard_access(client):
    # Perform POST login
    res = client.post(
        "/admin/login",
        data={"username": "admin", "password": "tali-admin-secret-2026"},
        follow_redirects=False
    )
    assert res.status_code == 302
    assert "/admin/dashboard" in res.headers["Location"]

    # Access dashboard with the active session
    dash_res = client.get("/admin/dashboard")
    assert dash_res.status_code == 200
    dash_html = dash_res.data.decode("utf-8")
    assert "Executive Command Overview" in dash_html
    assert "Registered Merchants" in dash_html
    assert "Platform GMV" in dash_html
    assert "AI Spend / Budget" in dash_html


def test_already_authenticated_redirected_away_from_login(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_user"] = "admin"

    res = client.get("/admin/login")
    assert res.status_code == 302
    assert "/admin/dashboard" in res.headers["Location"]


def test_failed_login_returns_401(client):
    res = client.post(
        "/admin/login",
        data={"username": "admin", "password": "incorrect-password"}
    )
    assert res.status_code == 401
    html = res.data.decode("utf-8")
    assert "Invalid stakeholder username or password" in html


def test_brute_force_lockout_returns_429(client):
    # Perform 5 failed attempts
    for _ in range(4):
        res = client.post(
            "/admin/login",
            data={"username": "admin", "password": "wrong-password"}
        )
        assert res.status_code == 401

    # 5th attempt locks out and returns 429
    res5 = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong-password"}
    )
    assert res5.status_code == 429
    assert "locked" in res5.data.decode("utf-8").lower()

    # 6th attempt (even with valid password!) is locked out with 429
    res6 = client.post(
        "/admin/login",
        data={"username": "admin", "password": "tali-admin-secret-2026"}
    )
    assert res6.status_code == 429
    assert "Too many failed login attempts" in res6.data.decode("utf-8")


def test_logout_clears_session_and_redirects(client):
    # Establish session
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_user"] = "admin"

    # Call logout
    res = client.post("/admin/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]

    # Verify session is cleared
    with client.session_transaction() as sess:
        assert not sess.get("admin_logged_in")

    # Attempting dashboard now redirects to login
    dash_res = client.get("/admin/dashboard")
    assert dash_res.status_code == 302
    assert "/admin/login" in dash_res.headers["Location"]


def test_cookie_security_flags(client, app):
    res = client.post(
        "/admin/login",
        data={"username": "admin", "password": "tali-admin-secret-2026"}
    )
    assert res.status_code == 302
    cookie_header = res.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header
