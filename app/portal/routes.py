"""Routes for the Merchant Self-Service Web Portal (WP-07)."""

from urllib.parse import urljoin, urlparse
from flask import flash, jsonify, redirect, render_template, request, session, url_for
from app.portal import portal_bp
from app.portal.auth import (
    get_current_merchant,
    is_merchant_authenticated,
    login_merchant,
    logout_merchant,
    merchant_required,
    normalize_phone,
    request_portal_otp,
    verify_portal_otp,
)
from app.portal.metrics import (
    get_merchant_cashflow_trends,
    get_merchant_financial_summary,
    get_merchant_transactions,
    get_recent_merchant_transactions,
)


def is_safe_url(target: str) -> bool:
    """Verify that the target URL is local and safe for redirection."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and ref_url.netloc == test_url.netloc
        and target.startswith("/portal")
    )


@portal_bp.route("/", methods=["GET"])
def index():
    """Redirect portal root to dashboard or login."""
    if is_merchant_authenticated():
        return redirect(url_for("portal.dashboard"))
    return redirect(url_for("portal.login"))


@portal_bp.route("/login", methods=["GET"])
def login():
    """Render merchant login view (phone entry or OTP verification)."""
    if is_merchant_authenticated():
        return redirect(url_for("portal.dashboard"))

    step = request.args.get("step", "phone")
    phone = request.args.get("phone") or session.get("portal_pending_phone", "")
    next_url = request.args.get("next", "")

    return render_template(
        "portal/login.html",
        step=step,
        phone=phone,
        next_url=next_url,
    )


@portal_bp.route("/request-otp", methods=["POST"])
def request_otp():
    """Handle phone number submission and trigger WhatsApp OTP dispatch."""
    raw_phone = request.form.get("phone", "").strip()
    next_url = request.form.get("next", "")

    if not raw_phone:
        flash("Please enter your phone number.", "error")
        return render_template("portal/login.html", step="phone", phone="", next_url=next_url), 400

    phone = normalize_phone(raw_phone)
    success, message, dev_otp = request_portal_otp(phone)

    if not success:
        flash(message, "error")
        return render_template("portal/login.html", step="phone", phone=raw_phone, next_url=next_url), 400

    session["portal_pending_phone"] = phone
    flash_msg = message
    if dev_otp:
        flash_msg += f" (Dev Code: {dev_otp})"
    flash(flash_msg, "success")

    return render_template(
        "portal/login.html",
        step="verify",
        phone=phone,
        dev_otp=dev_otp,
        next_url=next_url,
    )


@portal_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    """Verify submitted OTP and establish merchant session."""
    phone = (
        request.form.get("phone")
        or session.get("portal_pending_phone")
        or ""
    ).strip()
    code = request.form.get("code", "").strip()
    next_url = request.form.get("next", "")

    if not phone or not code:
        flash("Phone number and 6-digit code are required.", "error")
        return render_template("portal/login.html", step="verify", phone=phone, next_url=next_url), 400

    success, message, user = verify_portal_otp(phone, code)

    if not success:
        flash(message, "error")
        # Check if error message indicates lockout
        status_code = 429 if "locked" in message.lower() else 400
        return render_template("portal/login.html", step="verify", phone=phone, next_url=next_url), status_code

    # Login successful
    login_merchant(user["id"], user["phone_number"], user.get("display_name"))
    session.pop("portal_pending_phone", None)
    flash("Welcome back to your TaLi portal!", "success")

    if next_url and is_safe_url(next_url):
        return redirect(next_url)
    return redirect(url_for("portal.dashboard"))


@portal_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Log out the merchant and clear session."""
    logout_merchant()
    flash("You have been signed out.", "info")
    return redirect(url_for("portal.login"))


@portal_bp.route("/dashboard", methods=["GET"])
@merchant_required
def dashboard():
    """Merchant Portal Home Dashboard."""
    merchant = get_current_merchant()
    user_id = merchant["user_id"]
    summary = get_merchant_financial_summary(user_id)
    chart_data = get_merchant_cashflow_trends(user_id, days=30)
    recent_transactions = get_recent_merchant_transactions(user_id, limit=5)

    return render_template(
        "portal/dashboard.html",
        merchant=merchant,
        summary=summary,
        chart_data=chart_data,
        recent_transactions=recent_transactions,
    )


@portal_bp.route("/transactions", methods=["GET"])
@merchant_required
def transactions():
    """Searchable and filterable ledger transactions view."""
    merchant = get_current_merchant()
    user_id = merchant["user_id"]

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    limit = 20
    offset = (page - 1) * limit

    tx_type = request.args.get("type", "").strip() or None
    search = request.args.get("search", "").strip() or None
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None

    items, total_count = get_merchant_transactions(
        user_id=user_id,
        limit=limit,
        offset=offset,
        tx_type=tx_type,
        search=search,
        start_date=start_date,
        end_date=end_date,
    )

    total_pages = max(1, (total_count + limit - 1) // limit)

    # Return partial rows if HTMX request
    if request.headers.get("HX-Request"):
        return render_template(
            "portal/_transaction_rows.html",
            items=items,
            page=page,
            total_pages=total_pages,
            total_count=total_count,
        )

    return render_template(
        "portal/transactions.html",
        merchant=merchant,
        items=items,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        tx_type=tx_type or "",
        search=search or "",
        start_date=start_date or "",
        end_date=end_date or "",
    )


@portal_bp.route("/api/cashflow-chart", methods=["GET"])
@merchant_required
def cashflow_chart_api():
    """Return cashflow chart data as JSON for interactive period switching."""
    merchant = get_current_merchant()
    user_id = merchant["user_id"]

    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        days = 30

    data = get_merchant_cashflow_trends(user_id, days=days)
    return jsonify(data)

