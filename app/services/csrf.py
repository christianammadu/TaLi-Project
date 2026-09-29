"""Lightweight, secure CSRF protection for Flask web routes and HTMX requests.

Implements cryptographically random session-scoped CSRF tokens, constant-time
validation, automatic Jinja2 context injection, and webhook path exemptions.
"""

import hmac
import secrets
import sys
from flask import Flask, abort, current_app, request, session


def generate_csrf_token() -> str:
    """Generate or retrieve a cryptographically secure CSRF token for the session."""
    token = session.get("_csrf_token")
    if not token or not isinstance(token, str):
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token(provided_token: str | None) -> bool:
    """Constant-time validation of provided token against active session token."""
    expected_token = session.get("_csrf_token")
    if not expected_token or not provided_token:
        return False
    return hmac.compare_digest(str(provided_token).strip(), str(expected_token).strip())


def init_csrf(app: Flask):
    """Register context processor and before_request hook for CSRF protection."""
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    # Exempt paths (webhooks validated by cryptographic signatures or server-to-server)
    exempt_prefixes = (
        "/webhook",
        "/telegram",
    )

    @app.before_request
    def check_csrf():
        # Only validate state-changing HTTP methods
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None

        # Allow testing mode to bypass CSRF validation unless explicitly enabled
        csrf_enabled = current_app.config.get("CSRF_ENABLED")
        if csrf_enabled is False:
            return None
        if csrf_enabled is not True and (current_app.config.get("TESTING") or current_app.testing or "pytest" in sys.modules):
            return None


        # Exempt external webhook endpoints
        if any(request.path.startswith(prefix) for prefix in exempt_prefixes):
            return None

        # Extract token from HTTP header (HTMX / Fetch / AJAX) or Form data
        token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
        if not token:
            token = request.form.get("csrf_token")

        if not validate_csrf_token(token):
            abort(403, description="CSRF token missing or invalid.")
