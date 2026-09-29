"""Billing and Subscription Routes (WP-02 / G-BILLING).

Handles Paystack inbound webhook events (charge.success, subscription.create,
invoice.payment_failed, subscription.disable) with HMAC-SHA512 verification,
and provides transaction verification and initialization endpoints.
"""

from flask import Blueprint, request, jsonify, current_app, session, redirect, url_for

from app.services.billing import (
    verify_paystack_webhook_signature,
    process_paystack_event,
    verify_paystack_transaction,
    initialize_paystack_checkout,
    get_merchant_subscription,
)

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


@billing_bp.route("/webhook/paystack", methods=["POST"])
@billing_bp.route("/webhook", methods=["POST"])
def paystack_webhook():
    """Inbound Paystack webhook processor with HMAC-SHA512 signature verification."""
    signature = request.headers.get("X-Paystack-Signature")
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY", "")

    is_testing = current_app.config.get("TESTING", False) or current_app.config.get("OTP_DEV_BYPASS", False)

    # Validate HMAC signature unless in testing mode without a configured secret key
    if not secret_key and is_testing:
        # Development / testing bypass if no secret key configured
        pass
    else:
        if not signature or not verify_paystack_webhook_signature(request.get_data(), signature, secret_key):
            current_app.logger.warning("[Paystack Webhook] Invalid or missing signature")
            return jsonify({"status": "error", "message": "Invalid webhook signature"}), 401

    payload = request.get_json(silent=True) or {}
    event_type = payload.get("event")
    data = payload.get("data", {})

    if not event_type:
        return jsonify({"status": "error", "message": "Missing event type"}), 400

    current_app.logger.info(f"[Paystack Webhook] Received event: {event_type}")
    result = process_paystack_event(event_type, data)
    return jsonify({"status": "ok", "event": event_type, "result": result}), 200


# Mark csrf_exempt for custom or 3rd-party CSRF middlewares
paystack_webhook.csrf_exempt = True


@billing_bp.route("/verify", methods=["GET"])
def verify_transaction():
    """Verify transaction reference with Paystack and synchronize subscription status."""
    reference = request.args.get("reference")
    if not reference:
        return jsonify({"status": False, "message": "Missing transaction reference"}), 400

    result = verify_paystack_transaction(reference)

    # Check if redirect is requested (e.g. from Paystack payment callback)
    if request.args.get("redirect") or "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("portal.dashboard") + "?payment=verified")

    return jsonify(result), 200


@billing_bp.route("/initialize", methods=["POST"])
def initialize_checkout():
    """Initialize a Paystack checkout session for the current merchant."""
    # Resolve merchant user_id from session or JSON body
    merchant_user_id = session.get("merchant_user_id")
    body = request.get_json(silent=True) or {}

    user_id = merchant_user_id or body.get("user_id")
    if not user_id:
        return jsonify({"status": False, "message": "Authentication required"}), 401

    plan_slug = body.get("plan_slug", "pro")
    email = body.get("email") or (session.get("merchant_phone", "") + "@tali.africa" if session.get("merchant_phone") else "merchant@tali.africa")
    callback_url = body.get("callback_url") or (current_app.config.get("APP_BASE_URL", "") + "/billing/verify?redirect=1")

    res = initialize_paystack_checkout(
        user_id=user_id,
        plan_slug=plan_slug,
        email=email,
        callback_url=callback_url,
    )
    return jsonify(res), 200


@billing_bp.route("/subscription", methods=["GET"])
def merchant_subscription_status():
    """Get active subscription and entitlement details for the merchant."""
    merchant_user_id = session.get("merchant_user_id") or request.args.get("user_id")
    if not merchant_user_id:
        return jsonify({"status": False, "message": "Authentication required"}), 401

    sub = get_merchant_subscription(merchant_user_id)
    if not sub:
        return jsonify({"status": False, "message": "Subscription not found"}), 404

    return jsonify({"status": True, "subscription": sub}), 200
