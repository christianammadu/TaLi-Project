"""Routes for the Stakeholder Admin Portal (WP-04).

Provides login, logout, and dashboard landing shells for internal platform operators.
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from app.admin import admin_bp
from app.admin.auth import (
    admin_required, authenticate_stakeholder, login_admin, logout_admin,
    is_admin_authenticated, check_lockout, record_failed_attempt, reset_failed_attempts
)
from app.admin.metrics import get_platform_metrics, get_filtered_ai_logs, get_finops_metrics


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
    """Stakeholder command dashboard with live aggregated metrics (WP-05)."""
    metrics = get_platform_metrics()
    return render_template("admin/dashboard.html", metrics=metrics, active_nav="dashboard")


@admin_bp.route("/finops")
@admin_required
def finops():
    """FinOps spend telemetry, provider distribution, and model inspection (WP-05)."""
    model = request.args.get("model", "all")
    agent = request.args.get("agent", "all")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    page = int(request.args.get("page", 1))
    limit = 50
    offset = (page - 1) * limit

    log_data = get_filtered_ai_logs(
        model=model,
        agent=agent,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    finops_metrics = get_finops_metrics()

    return render_template(
        "admin/finops.html",
        active_nav="finops",
        finops=finops_metrics,
        logs=log_data["logs"],
        available_models=log_data["available_models"],
        available_agents=log_data["available_agents"],
        total_count=log_data["total_count"],
        current_page=page,
        total_pages=max(1, (log_data["total_count"] + limit - 1) // limit),
        selected_model=model,
        selected_agent=agent,
        selected_start_date=start_date,
        selected_end_date=end_date,
    )


@admin_bp.route("/api/finops-metrics")
@admin_required
def api_finops_metrics():
    """JSON API endpoint returning live FinOps telemetry."""
    return jsonify(get_finops_metrics())

