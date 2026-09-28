"""Authentication and session management for the Merchant Self-Service Web Portal (WP-07).

Provides passwordless authentication via WhatsApp OTP, rate-limiting & brute-force
lockout defenses, and role-enforced merchant session cookies.
"""

import re
import secrets
import string
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import current_app, redirect, request, session, url_for
from sqlalchemy import func, select, update

from app.auth import get_user_by_phone
from app.data.db import session_scope
from app.data.models import User, VerificationCode

# Lockout defense: max 3 failed OTP attempts locks phone for 10 minutes
_FAILED_OTP_ATTEMPTS = {}
MAX_OTP_ATTEMPTS = 3
OTP_LOCKOUT_SECONDS = 600  # 10 minutes
OTP_WINDOW_SECONDS = 600


def normalize_phone(raw_phone: str) -> str:
    """Normalize user-entered phone number to standard E.164 (+234...) format."""
    if not raw_phone:
        return ""
    clean = raw_phone.strip()
    digits = "".join(ch for ch in clean if ch.isdigit())

    if clean.startswith("+"):
        return f"+{digits}"
    # Nigerian 11 digits starting with 0: e.g. 08012345678 -> +2348012345678
    if len(digits) == 11 and digits.startswith("0"):
        return f"+234{digits[1:]}"
    # Nigerian 13 digits without leading plus: 2348012345678 -> +2348012345678
    if len(digits) == 13 and digits.startswith("234"):
        return f"+{digits}"
    # Generic international format if length is appropriate
    if len(digits) >= 10:
        return f"+{digits}"
    return clean


def check_phone_lockout(phone: str) -> tuple[bool, int]:
    """Check if the phone is currently locked out from OTP attempts.

    Returns:
        (is_locked, remaining_seconds)
    """
    now = time.time()
    state = _FAILED_OTP_ATTEMPTS.get(phone)
    if not state:
        return False, 0

    if state.get("locked_until", 0) > now:
        remaining = int(state["locked_until"] - now)
        return True, max(1, remaining)

    # Window expired; reset
    if now - state.get("first_failed", 0) > OTP_WINDOW_SECONDS:
        _FAILED_OTP_ATTEMPTS.pop(phone, None)

    return False, 0


def record_phone_failed_attempt(phone: str) -> tuple[bool, int, int]:
    """Record an invalid OTP attempt for the phone.

    Returns:
        (is_now_locked, lock_seconds, remaining_attempts)
    """
    now = time.time()
    state = _FAILED_OTP_ATTEMPTS.setdefault(
        phone, {"attempts": 0, "locked_until": 0.0, "first_failed": now}
    )

    if now - state.get("first_failed", now) > OTP_WINDOW_SECONDS and state.get("locked_until", 0) <= now:
        state["attempts"] = 0
        state["first_failed"] = now

    state["attempts"] += 1
    remaining_attempts = max(0, MAX_OTP_ATTEMPTS - state["attempts"])

    if state["attempts"] >= MAX_OTP_ATTEMPTS:
        state["locked_until"] = now + OTP_LOCKOUT_SECONDS
        return True, OTP_LOCKOUT_SECONDS, 0

    return False, 0, remaining_attempts


def reset_phone_failed_attempts(phone: str):
    """Clear failed attempts upon successful OTP verification."""
    _FAILED_OTP_ATTEMPTS.pop(phone, None)


def clear_all_portal_lockouts():
    """Clear all lockout states (used for test setup/teardown)."""
    global _FAILED_OTP_ATTEMPTS
    _FAILED_OTP_ATTEMPTS.clear()


def find_registered_merchant(raw_phone: str) -> dict | None:
    """Find a verified merchant user by normalized or alternate phone representations."""
    norm = normalize_phone(raw_phone)
    if norm:
        user = get_user_by_phone(norm)
        if user:
            return user

    clean = raw_phone.strip() if raw_phone else ""
    if clean and clean != norm:
        user = get_user_by_phone(clean)
        if user:
            return user

    digits = "".join(c for c in clean if c.isdigit())
    candidates = []
    if digits.startswith("234") and len(digits) >= 12:
        candidates.append("0" + digits[3:])
        candidates.append(digits)
    elif digits.startswith("0") and len(digits) == 11:
        candidates.append("+234" + digits[1:])
        candidates.append("234" + digits[1:])

    for c in candidates:
        user = get_user_by_phone(c)
        if user:
            return user

    return None


def generate_portal_otp() -> str:
    """Generate a random 6-digit numeric OTP."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def request_portal_otp(phone: str) -> tuple[bool, str, str | None]:
    """Generate and dispatch an OTP for portal login.

    Returns:
        (success: bool, message: str, dev_otp: str | None)
    """
    is_locked, remaining = check_phone_lockout(phone)
    if is_locked:
        mins = max(1, (remaining + 59) // 60)
        return False, f"Too many failed attempts. Please wait {mins} minute(s) before trying again.", None

    user = find_registered_merchant(phone)
    if not user:
        return False, "This phone number is not registered. Please sign up on TaLi first.", None

    # Canonicalize phone number from the verified user record
    canonical_phone = user["phone_number"]
    otp = generate_portal_otp()
    expiry_minutes = current_app.config.get("OTP_EXPIRY_MINUTES", 10)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=expiry_minutes)

    try:
        with session_scope() as s:
            # Invalidate any pending unused login codes for this phone
            s.execute(
                update(VerificationCode)
                .where(
                    VerificationCode.phone_number == canonical_phone,
                    VerificationCode.purpose == "login",
                    VerificationCode.used.is_(False),
                )
                .values(used=True)
            )
            s.add(
                VerificationCode(
                    phone_number=canonical_phone,
                    code=otp,
                    purpose="login",
                    expires_at=expires_at,
                    used=False,
                )
            )
    except Exception as e:
        current_app.logger.error(f"Failed to persist portal OTP: {e}")
        return False, "Failed to generate login code. Please try again.", None

    # Dev bypass / testing mode
    is_dev = current_app.config.get("OTP_DEV_BYPASS", False) or current_app.config.get("TESTING", False)
    if is_dev:
        return True, "Login code dispatched.", otp

    # Dispatch via WhatsApp template or text
    try:
        from app.web.whatsapp import send_reply
        msg = (
            f"🔑 *TaLi Merchant Portal Login*\n\n"
            f"Your one-time login code is: *{otp}*\n\n"
            f"This code will expire in {expiry_minutes} minutes. "
            f"Never share this code with anyone."
        )
        send_reply(canonical_phone, msg)
    except Exception as e:
        current_app.logger.error(f"WhatsApp OTP dispatch failed: {e}")

    return True, "A 6-digit login code has been sent to your WhatsApp.", None


def verify_portal_otp(phone: str, code: str) -> tuple[bool, str, dict | None]:
    """Verify an entered OTP for merchant portal authentication.

    Returns:
        (success: bool, message: str, user_dict: dict | None)
    """
    is_locked, remaining = check_phone_lockout(phone)
    if is_locked:
        mins = max(1, (remaining + 59) // 60)
        return False, f"Account temporarily locked. Please wait {mins} minute(s).", None

    clean_code = code.strip() if code else ""
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False, "Please enter a valid 6-digit verification code.", None

    user = find_registered_merchant(phone)
    if not user:
        return False, "User not found or unverified.", None

    canonical_phone = user["phone_number"]

    try:
        with session_scope() as s:
            row = s.execute(
                select(VerificationCode)
                .where(
                    VerificationCode.phone_number == canonical_phone,
                    VerificationCode.code == clean_code,
                    VerificationCode.purpose == "login",
                    VerificationCode.used.is_(False),
                    VerificationCode.expires_at > func.now(),
                )
                .order_by(VerificationCode.created_at.desc())
                .limit(1)
            ).scalars().first()

            if row:
                row.used = True
                s.commit()
                reset_phone_failed_attempts(phone)
                reset_phone_failed_attempts(canonical_phone)
                return True, "Login successful.", user
    except Exception as e:
        current_app.logger.error(f"Error checking OTP: {e}")
        return False, "Verification failed due to a server error. Please try again.", None

    # Failed attempt
    is_now_locked, lock_seconds, remaining_attempts = record_phone_failed_attempt(canonical_phone)
    if phone != canonical_phone:
        record_phone_failed_attempt(phone)

    if is_now_locked:
        mins = max(1, (lock_seconds + 59) // 60)
        return False, f"Too many failed attempts. Account locked for {mins} minutes.", None

    return False, f"Invalid or expired verification code. {remaining_attempts} attempt(s) remaining.", None


# Session Management
def login_merchant(user_id: str, phone_number: str, display_name: str | None = None):
    """Store merchant authentication credentials in the active session."""
    session["merchant_logged_in"] = True
    session["merchant_user_id"] = str(user_id)
    session["merchant_phone"] = phone_number
    session["merchant_name"] = display_name or phone_number
    session.permanent = True


def logout_merchant():
    """Destroy merchant session state."""
    session.pop("merchant_logged_in", None)
    session.pop("merchant_user_id", None)
    session.pop("merchant_phone", None)
    session.pop("merchant_name", None)
    session.pop("portal_pending_phone", None)


def is_merchant_authenticated() -> bool:
    """Return True if session contains valid merchant credentials."""
    return bool(session.get("merchant_logged_in") and session.get("merchant_user_id"))


def get_current_merchant() -> dict | None:
    """Return dictionary of current authenticated merchant, or None."""
    if not is_merchant_authenticated():
        return None
    return {
        "user_id": session.get("merchant_user_id"),
        "phone_number": session.get("merchant_phone"),
        "display_name": session.get("merchant_name"),
    }


def merchant_required(f):
    """Route decorator enforcing merchant authentication on portal endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_merchant_authenticated():
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("portal.login", next=next_url))
        return f(*args, **kwargs)
    return decorated_function
