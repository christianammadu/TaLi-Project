"""Authentication and session management for the Stakeholder Admin Portal (WP-04).

Implements bcrypt password verification, session tracking, hardened cookies,
and brute-force lockout defense (G-08).
"""

import time
from functools import wraps
from flask import session, redirect, url_for, request, current_app
import bcrypt

# FinOps & Admin Security Lockout State (G-08)
# key: "ip:username" or "ip" -> {"attempts": int, "locked_until": float, "first_failed": float}
_FAILED_LOGIN_ATTEMPTS = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
ATTEMPT_WINDOW_SECONDS = 900    # 15 minutes


def _is_db_lockout_active() -> bool:
    try:
        if not current_app:
            return False
        if current_app.config.get("TESTING") and not current_app.config.get("DB_LOCKOUT_TESTING"):
            return False
        return bool(current_app.config.get("DB_LOCKOUT_ENABLED", True))
    except Exception:
        return False


def check_lockout(key: str) -> tuple[bool, int]:
    """Check if the given key (IP or IP:username) is currently locked out.

    Returns:
        (is_locked, remaining_seconds)
    """
    now = time.time()
    if _is_db_lockout_active():
        try:
            from app.data.db import session_scope
            from app.data.models import LoginAttempt
            with session_scope() as s:
                attempt = s.get(LoginAttempt, f"admin:{key}")
                if attempt:
                    locked_until = float(attempt.locked_until or 0)
                    if locked_until > now:
                        return True, max(1, int(locked_until - now))
                    first_failed = float(attempt.first_failed or 0)
                    if now - first_failed > ATTEMPT_WINDOW_SECONDS:
                        s.delete(attempt)
                        return False, 0
                    return False, 0
        except Exception:
            pass


    state = _FAILED_LOGIN_ATTEMPTS.get(key)
    if not state:
        return False, 0

    if state.get("locked_until", 0) > now:
        remaining = int(state["locked_until"] - now)
        return True, max(1, remaining)

    # Window expired; reset
    if now - state.get("first_failed", 0) > ATTEMPT_WINDOW_SECONDS:
        _FAILED_LOGIN_ATTEMPTS.pop(key, None)

    return False, 0


def record_failed_attempt(key: str) -> tuple[bool, int]:
    """Record a failed login attempt for the key.

    Returns:
        (is_now_locked, remaining_seconds)
    """
    now = time.time()
    if _is_db_lockout_active():
        try:
            from app.data.db import session_scope
            from app.data.models import LoginAttempt
            with session_scope() as s:
                attempt = s.get(LoginAttempt, f"admin:{key}")
                if not attempt:
                    attempt = LoginAttempt(
                        attempt_key=f"admin:{key}",
                        attempts=1,
                        first_failed=now,
                        locked_until=0.0,
                    )
                    s.add(attempt)
                    attempts_count = 1
                else:
                    first_failed = float(attempt.first_failed or now)
                    locked_until = float(attempt.locked_until or 0.0)
                    if now - first_failed > ATTEMPT_WINDOW_SECONDS and locked_until <= now:
                        attempt.attempts = 1
                        attempt.first_failed = now
                        attempt.locked_until = 0.0
                        attempts_count = 1
                    else:
                        attempt.attempts += 1
                        attempts_count = attempt.attempts

                if attempts_count >= MAX_FAILED_ATTEMPTS:
                    attempt.locked_until = now + LOCKOUT_DURATION_SECONDS
                    _FAILED_LOGIN_ATTEMPTS[key] = {
                        "attempts": attempts_count,
                        "locked_until": now + LOCKOUT_DURATION_SECONDS,
                        "first_failed": float(attempt.first_failed),
                    }
                    return True, LOCKOUT_DURATION_SECONDS

                _FAILED_LOGIN_ATTEMPTS[key] = {
                    "attempts": attempts_count,
                    "locked_until": 0.0,
                    "first_failed": float(attempt.first_failed),
                }
                return False, 0
        except Exception:
            pass

    state = _FAILED_LOGIN_ATTEMPTS.setdefault(
        key, {"attempts": 0, "locked_until": 0.0, "first_failed": now}
    )

    # If previous window expired, restart count
    if now - state.get("first_failed", now) > ATTEMPT_WINDOW_SECONDS and state.get("locked_until", 0) <= now:
        state["attempts"] = 0
        state["first_failed"] = now

    state["attempts"] += 1

    if state["attempts"] >= MAX_FAILED_ATTEMPTS:
        state["locked_until"] = now + LOCKOUT_DURATION_SECONDS
        return True, LOCKOUT_DURATION_SECONDS

    return False, 0


def reset_failed_attempts(key: str):
    """Clear failed attempts upon successful authentication."""
    _FAILED_LOGIN_ATTEMPTS.pop(key, None)
    if _is_db_lockout_active():
        try:
            from app.data.db import session_scope
            from app.data.models import LoginAttempt
            with session_scope() as s:
                attempt = s.get(LoginAttempt, f"admin:{key}")
                if attempt:
                    s.delete(attempt)
        except Exception:
            pass


def clear_all_lockouts():
    """Clear all lockout states (used for test teardown and admin maintenance)."""
    global _FAILED_LOGIN_ATTEMPTS
    _FAILED_LOGIN_ATTEMPTS.clear()
    if _is_db_lockout_active():
        try:
            from app.data.db import session_scope
            from app.data.models import LoginAttempt
            from sqlalchemy import delete
            with session_scope() as s:
                s.execute(delete(LoginAttempt).where(LoginAttempt.attempt_key.like("admin:%")))
        except Exception:
            pass




def hash_password(password: str) -> str:
    """Generate a secure bcrypt hash for a plaintext password."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(provided_password: str, stored_hash: str) -> bool:
    """Verify provided password against a bcrypt or fallback hash."""
    if not provided_password or not stored_hash:
        return False

    if stored_hash.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            return bcrypt.checkpw(
                provided_password.encode("utf-8"), stored_hash.encode("utf-8")
            )
        except Exception:
            return False

    # Werkzeug hashes start with method prefix: e.g. 'scrypt:' or 'pbkdf2:'
    if stored_hash.startswith(("scrypt:", "pbkdf2:")):
        try:
            from werkzeug.security import check_password_hash
            return check_password_hash(stored_hash, provided_password)
        except Exception:
            return False

    # Direct constant-time comparison fallback for dev/testing when plaintext is configured
    import hmac
    return hmac.compare_digest(provided_password, stored_hash)


def authenticate_stakeholder(username: str, password: str) -> bool:
    """Validate stakeholder credentials against application configuration."""
    expected_user = current_app.config.get("ADMIN_USERNAME", "admin")
    if username != expected_user:
        return False

    stored_hash = current_app.config.get("ADMIN_PASSWORD_HASH")
    if stored_hash:
        return verify_password(password, stored_hash)

    # Fallback to plaintext config if hash not yet seeded
    fallback_pwd = current_app.config.get("ADMIN_PASSWORD", "tali-admin-secret-2026")
    return verify_password(password, fallback_pwd)


def login_admin(username: str):
    """Establish authenticated stakeholder session."""
    session["admin_logged_in"] = True
    session["admin_user"] = username
    session.permanent = True


def logout_admin():
    """Destroy authenticated stakeholder session."""
    session.pop("admin_logged_in", None)
    session.pop("admin_user", None)
    session.clear()


def is_admin_authenticated() -> bool:
    """Return True if the current request session is an authenticated admin."""
    return bool(session.get("admin_logged_in"))


def admin_required(f):
    """Route decorator requiring authenticated stakeholder session.

    Redirects unauthenticated requests to the admin login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_authenticated():
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("admin.login", next=next_url))
        return f(*args, **kwargs)
    return decorated_function
