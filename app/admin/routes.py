"""Routes for the Stakeholder Admin Portal (WP-04).

Provides login, logout, and dashboard landing shells for internal platform operators.
"""

from flask import render_template, request, redirect, url_for, flash
from app.admin import admin_bp
from app.admin.auth import (
    admin_required, authenticate_stakeholder, login_admin, logout_admin,
    is_admin_authenticated, check_lockout, record_failed_attempt, reset_failed_attempts
)


@admin_bp.route("/")
def index():
    """Admin entrypoint — redirects to dashboard (triggering auth if unauthenticated)."""
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Stakeholder login endpoint with brute-force throttling (G-08)."""
    if is_admin_authenticated():
        return redirect(url_for("admin.dashboard"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("admin.dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
        client_ip = client_ip.split(",")[0].strip()
        lockout_key = f"{client_ip}:{username}" if username else client_ip

        is_locked, remaining_sec = check_lockout(lockout_key)
        if is_locked:
            minutes = max(1, remaining_sec // 60)
            flash(
                f"🔒 Too many failed login attempts. Your account is temporarily locked. Please try again in {minutes} minute(s).",
                "warning"
            )
            return render_template("admin/login.html", next_url=next_url, username=username), 429

        if authenticate_stakeholder(username, password):
            reset_failed_attempts(lockout_key)
            login_admin(username)
            flash("Welcome back, Stakeholder.", "success")
            return redirect(next_url)

        # Authentication failed
        is_locked_now, lock_sec = record_failed_attempt(lockout_key)
        if is_locked_now:
            mins = max(1, lock_sec // 60)
            flash(
                f"🔒 Invalid credentials. 5 failed attempts reached. Account locked for {mins} minutes.",
                "error"
            )
            return render_template("admin/login.html", next_url=next_url, username=username), 429

        flash("❌ Invalid stakeholder username or password.", "error")
        return render_template("admin/login.html", next_url=next_url, username=username), 401

    return render_template("admin/login.html", next_url=next_url)


@admin_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Terminate stakeholder admin session."""
    logout_admin()
    flash("You have been securely signed out.", "info")
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """Stakeholder command dashboard shell (WP-04 placeholder)."""
    # Baseline shell metrics (connected to live queries in WP-05/WP-06)
    metrics = {
        "total_merchants": 42,
        "daily_active_merchants": 18,
        "platform_gmv_ngn": 14_250_000.00,
        "finops": {
            "total_spend_usd": 4.12,
            "ceiling_usd": 25.00,
            "provider_share": {"openai": 0.88, "aiml": 0.12, "featherless": 0.0},
            "p95_latency_ms": 1120,
        },
        "pending_compliance_count": 3
    }
    return render_template("admin/dashboard.html", metrics=metrics, active_nav="dashboard")
