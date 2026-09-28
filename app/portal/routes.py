"""Routes for the Merchant Self-Service Web Portal (WP-07)."""

from urllib.parse import urljoin, urlparse
from flask import flash, redirect, render_template, request, session, url_for
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
    return render_template("portal/dashboard.html", merchant=merchant)
