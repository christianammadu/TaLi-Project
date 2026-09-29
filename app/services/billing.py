"""Subscription & Billing Service — Core monetization and entitlement logic.

Handles plan definitions, subscription status checks, grace periods, feature entitlements,
and Paystack webhook / verification engine integration.
"""

import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import requests
from flask import current_app
from sqlalchemy import select, or_

from app.data.db import session_scope
from app.data.models import SubscriptionPlan, MerchantSubscription, BillingInvoice, User
from app.services.uuid_utils import uuid7, uuid_to_bin, bin_to_uuid

# Default Plans & Pricing Strategy
DEFAULT_PLANS = [
    {
        "slug": "starter",
        "name": "Free Starter",
        "price": 0.00,
        "currency": "NGN",
        "billing_interval": "monthly",
        "features": [
            "text_bookkeeping",
            "basic_statements",
            "single_user",
        ],
    },
    {
        "slug": "pro",
        "name": "Merchant Pro",
        "price": 3500.00,
        "currency": "NGN",
        "billing_interval": "monthly",
        "features": [
            "text_bookkeeping",
            "basic_statements",
            "voice_notes",
            "pos_vision_ocr",
            "branded_receipts",
            "automated_debt_reminders",
            "unlimited_transactions",
        ],
    },
    {
        "slug": "business",
        "name": "Business Fleet",
        "price": 9500.00,
        "currency": "NGN",
        "billing_interval": "monthly",
        "features": [
            "text_bookkeeping",
            "basic_statements",
            "voice_notes",
            "pos_vision_ocr",
            "branded_receipts",
            "automated_debt_reminders",
            "unlimited_transactions",
            "credit_passport_dossier",
            "multi_staff_accounts",
            "predictive_restock_alerts",
            "priority_support",
        ],
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_paystack_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse Paystack ISO timestamp string into UTC naive datetime."""
    if not dt_str:
        return None
    try:
        dt_clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_clean)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def verify_paystack_webhook_signature(payload_bytes: bytes, signature: Optional[str], secret_key: Optional[str]) -> bool:
    """Verify that incoming webhook payload matches Paystack HMAC-SHA512 signature."""
    if not signature or not secret_key:
        return False
    try:
        computed = hmac.new(
            secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(signature.strip(), computed)
    except Exception:
        return False


def seed_default_plans(session) -> List[SubscriptionPlan]:
    """Ensure standard starter, pro, and business plans exist in database."""
    plans = []
    for plan_def in DEFAULT_PLANS:
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.slug == plan_def["slug"])
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            plan = SubscriptionPlan(
                slug=plan_def["slug"],
                name=plan_def["name"],
                price=plan_def["price"],
                currency=plan_def["currency"],
                billing_interval=plan_def["billing_interval"],
                features=plan_def["features"],
                is_active=True,
            )
            session.add(plan)
            plans.append(plan)
        else:
            plans.append(existing)
    session.flush()
    return plans


def get_merchant_subscription(user_id) -> Optional[Dict[str, Any]]:
    """Retrieve full subscription summary for a merchant, resolving plan and active status."""
    try:
        with session_scope() as s:
            stmt = select(MerchantSubscription).where(MerchantSubscription.user_id == user_id)
            sub = s.execute(stmt).scalar_one_or_none()
            if not sub:
                # Provision starter trial if no subscription exists
                plans = seed_default_plans(s)
                starter_plan = next((p for p in plans if p.slug == "starter"), None)
                if not starter_plan:
                    return None

                sub_id = uuid7()
                now = _utcnow()
                sub = MerchantSubscription(
                    id=sub_id,
                    user_id=user_id,
                    plan_id=starter_plan.id,
                    status="active",
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )
                s.add(sub)
                s.flush()
                plan_slug = starter_plan.slug
                plan_name = starter_plan.name
                features = starter_plan.features or []
            else:
                plan = s.get(SubscriptionPlan, sub.plan_id)
                plan_slug = plan.slug if plan else "starter"
                plan_name = plan.name if plan else "Free Starter"
                features = plan.features if plan and plan.features else []

            now = _utcnow()
            is_active = (
                sub.status in ("active", "trialing")
                or (sub.status == "past_due" and sub.grace_period_ends_at and sub.grace_period_ends_at > now)
            )

            return {
                "id": str(bin_to_uuid(sub.id) or sub.id),
                "user_id": str(bin_to_uuid(sub.user_id) or sub.user_id),
                "plan_slug": plan_slug,
                "plan_name": plan_name,
                "status": sub.status,
                "is_active": is_active,
                "features": features,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "grace_period_ends_at": sub.grace_period_ends_at,
                "paystack_subscription_code": sub.paystack_subscription_code,
            }
    except Exception as e:
        print(f"[Billing] Error fetching subscription for {user_id}: {e}")
        return None


def is_feature_entitled(user_id, feature_name: str) -> bool:
    """Check if merchant's active plan includes a specific feature entitlement."""
    sub = get_merchant_subscription(user_id)
    if not sub or not sub.get("is_active"):
        return False
    return feature_name in sub.get("features", [])


def handle_paystack_charge_success(data: dict) -> Dict[str, Any]:
    """Process successful payment charge: record invoice, activate/renew subscription."""
    reference = data.get("reference")
    if not reference:
        return {"status": "error", "message": "Missing payment reference"}

    amount_kobo = data.get("amount") or 0
    amount = float(amount_kobo) / 100.0
    currency = data.get("currency", "NGN")
    paid_at = parse_paystack_datetime(data.get("paid_at") or data.get("paidAt")) or _utcnow()

    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")
    metadata = data.get("metadata") or {}
    user_id_str = metadata.get("user_id")
    plan_slug = metadata.get("plan_slug")
    sub_code = (
        data.get("subscription_code")
        or (data.get("plan") or {}).get("subscription_code")
        if isinstance(data.get("plan"), dict)
        else None
    )

    with session_scope() as s:
        # Idempotency check on invoice reference
        inv_stmt = select(BillingInvoice).where(BillingInvoice.paystack_reference == reference)
        existing_inv = s.execute(inv_stmt).scalar_one_or_none()
        if existing_inv and existing_inv.status == "paid":
            return {
                "status": "already_processed",
                "reference": reference,
                "invoice_id": str(bin_to_uuid(existing_inv.id) or existing_inv.id),
            }

        # Resolve user
        resolved_user = None
        if user_id_str:
            resolved_user = user_id_str
        elif customer_code or sub_code:
            match_sub_stmt = select(MerchantSubscription).where(
                or_(
                    MerchantSubscription.paystack_customer_code == customer_code,
                    MerchantSubscription.paystack_subscription_code == sub_code,
                )
            )
            matched_sub = s.execute(match_sub_stmt).scalar_one_or_none()
            if matched_sub:
                resolved_user = matched_sub.user_id

        if not resolved_user:
            return {"status": "error", "message": f"Unable to resolve merchant user for reference {reference}"}

        # Resolve plan
        plans = seed_default_plans(s)
        plan = None
        if plan_slug:
            plan = next((p for p in plans if p.slug == plan_slug), None)
        if not plan:
            # Plan inference by price
            if amount >= 9000:
                plan = next((p for p in plans if p.slug == "business"), None)
            elif amount >= 3000:
                plan = next((p for p in plans if p.slug == "pro"), None)
            else:
                plan = next((p for p in plans if p.slug == "starter"), None)
        if not plan:
            plan = plans[0]

        now = _utcnow()
        interval_days = 365 if getattr(plan, "billing_interval", "monthly") == "yearly" else 30

        # Create or update subscription
        sub_stmt = select(MerchantSubscription).where(MerchantSubscription.user_id == resolved_user)
        sub = s.execute(sub_stmt).scalar_one_or_none()
        if not sub:
            sub = MerchantSubscription(
                id=uuid7(),
                user_id=resolved_user,
                plan_id=plan.id,
                status="active",
                paystack_customer_code=customer_code,
                paystack_subscription_code=sub_code,
                current_period_start=now,
                current_period_end=now + timedelta(days=interval_days),
                grace_period_ends_at=None,
            )
            s.add(sub)
            s.flush()
        else:
            sub.plan_id = plan.id
            sub.status = "active"
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=interval_days)
            sub.grace_period_ends_at = None
            sub.canceled_at = None
            if customer_code:
                sub.paystack_customer_code = customer_code
            if sub_code:
                sub.paystack_subscription_code = sub_code

        # Create or update invoice
        if existing_inv:
            existing_inv.status = "paid"
            existing_inv.amount = amount
            existing_inv.currency = currency
            existing_inv.paid_at = paid_at
            invoice_id = existing_inv.id
        else:
            inv = BillingInvoice(
                id=uuid7(),
                subscription_id=sub.id,
                user_id=resolved_user,
                paystack_reference=reference,
                amount=amount,
                currency=currency,
                status="paid",
                paid_at=paid_at,
                invoice_pdf_url=data.get("receipt_url") or data.get("invoice_pdf_url"),
            )
            s.add(inv)
            s.flush()
            invoice_id = inv.id

        return {
            "status": "success",
            "event": "charge.success",
            "reference": reference,
            "invoice_id": str(bin_to_uuid(invoice_id) or invoice_id),
            "subscription_id": str(bin_to_uuid(sub.id) or sub.id),
            "plan_slug": plan.slug,
            "amount": amount,
        }


def handle_paystack_subscription_create(data: dict) -> Dict[str, Any]:
    """Record newly created Paystack recurring subscription mapping."""
    sub_code = data.get("subscription_code")
    if not sub_code:
        return {"status": "error", "message": "Missing subscription_code"}

    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")
    email_token = data.get("email_token")
    next_payment_date = parse_paystack_datetime(data.get("next_payment_date"))
    metadata = data.get("metadata") or {}
    user_id_str = metadata.get("user_id")

    with session_scope() as s:
        sub = None
        if user_id_str:
            sub = s.execute(
                select(MerchantSubscription).where(MerchantSubscription.user_id == user_id_str)
            ).scalar_one_or_none()

        if not sub and customer_code:
            sub = s.execute(
                select(MerchantSubscription).where(MerchantSubscription.paystack_customer_code == customer_code)
            ).scalar_one_or_none()

        if not sub:
            sub = s.execute(
                select(MerchantSubscription).where(MerchantSubscription.paystack_subscription_code == sub_code)
            ).scalar_one_or_none()

        if sub:
            sub.paystack_subscription_code = sub_code
            if customer_code:
                sub.paystack_customer_code = customer_code
            if email_token:
                sub.paystack_email_token = email_token
            sub.status = "active"
            if next_payment_date:
                sub.current_period_end = next_payment_date
            sub.grace_period_ends_at = None
            return {
                "status": "success",
                "event": "subscription.create",
                "subscription_code": sub_code,
            }

        return {
            "status": "subscription_not_found",
            "event": "subscription.create",
            "subscription_code": sub_code,
        }


def handle_paystack_invoice_failed(data: dict) -> Dict[str, Any]:
    """Handle recurring charge failure: activate 3-day grace period and record failed invoice."""
    sub_data = data.get("subscription")
    sub_code = (
        sub_data.get("subscription_code")
        if isinstance(sub_data, dict)
        else (data.get("subscription_code") or sub_data)
    )
    customer_code = (data.get("customer") or {}).get("customer_code")
    reference = data.get("reference") or f"failed_{int(_utcnow().timestamp())}"
    amount = float(data.get("amount") or 0) / 100.0

    with session_scope() as s:
        sub_stmt = select(MerchantSubscription).where(
            or_(
                MerchantSubscription.paystack_subscription_code == sub_code,
                MerchantSubscription.paystack_customer_code == customer_code,
            )
        )
        sub = s.execute(sub_stmt).scalar_one_or_none()
        if sub:
            now = _utcnow()
            sub.status = "past_due"
            if not sub.grace_period_ends_at or sub.grace_period_ends_at < now:
                sub.grace_period_ends_at = now + timedelta(days=3)

            # Record failed invoice
            inv_stmt = select(BillingInvoice).where(BillingInvoice.paystack_reference == reference)
            existing_inv = s.execute(inv_stmt).scalar_one_or_none()
            if not existing_inv:
                inv = BillingInvoice(
                    id=uuid7(),
                    subscription_id=sub.id,
                    user_id=sub.user_id,
                    paystack_reference=reference,
                    amount=amount,
                    currency=data.get("currency", "NGN"),
                    status="failed",
                    paid_at=None,
                )
                s.add(inv)
            else:
                existing_inv.status = "failed"

            return {
                "status": "grace_period_activated",
                "grace_period_ends_at": sub.grace_period_ends_at.isoformat(),
            }

        return {"status": "subscription_not_found"}


def handle_paystack_subscription_disable(data: dict) -> Dict[str, Any]:
    """Handle cancelled or non-renewed subscription."""
    sub_code = data.get("subscription_code")
    if not sub_code:
        return {"status": "error", "message": "Missing subscription_code"}

    with session_scope() as s:
        sub_stmt = select(MerchantSubscription).where(
            MerchantSubscription.paystack_subscription_code == sub_code
        )
        sub = s.execute(sub_stmt).scalar_one_or_none()
        if sub:
            sub.status = "canceled"
            sub.canceled_at = _utcnow()
            return {"status": "subscription_canceled", "subscription_code": sub_code}

        return {"status": "subscription_not_found"}


def process_paystack_event(event_type: str, data: dict) -> Dict[str, Any]:
    """Dispatch Paystack webhook event to appropriate handler."""
    if event_type == "charge.success":
        return handle_paystack_charge_success(data)
    elif event_type == "subscription.create":
        return handle_paystack_subscription_create(data)
    elif event_type == "invoice.payment_failed":
        return handle_paystack_invoice_failed(data)
    elif event_type in ("subscription.disable", "subscription.not_renew"):
        return handle_paystack_subscription_disable(data)
    else:
        return {"status": "ignored", "event": event_type}


def initialize_paystack_checkout(user_id, plan_slug: str, email: str, callback_url: Optional[str] = None) -> Dict[str, Any]:
    """Initiate a Paystack checkout transaction for the specified subscription plan."""
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY", "")
    api_base = current_app.config.get("PAYSTACK_API_BASE", "https://api.paystack.co")
    is_mock = not secret_key or secret_key.startswith("mock_") or secret_key.startswith("test_mock") or current_app.config.get("TESTING")

    # Resolve plan price
    with session_scope() as s:
        plans = seed_default_plans(s)
        plan = next((p for p in plans if p.slug == plan_slug), None)
        if not plan:
            return {"status": False, "message": f"Plan '{plan_slug}' not found"}
        amount_kobo = int(plan.price * 100)
        paystack_plan_code = plan.paystack_plan_code

    ref = f"tali_sub_{uuid7().hex[:12]}"

    if is_mock:
        return {
            "status": True,
            "message": "Authorization URL created (mock)",
            "data": {
                "authorization_url": f"https://checkout.paystack.com/{ref}",
                "access_code": f"acc_{ref}",
                "reference": ref,
            },
        }

    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": ref,
        "callback_url": callback_url,
        "metadata": {
            "user_id": str(user_id),
            "plan_slug": plan_slug,
        },
    }
    if paystack_plan_code:
        payload["plan"] = paystack_plan_code

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(f"{api_base}/transaction/initialize", json=payload, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"status": False, "message": str(e)}


def verify_paystack_transaction(reference: str) -> Dict[str, Any]:
    """Verify transaction status with Paystack REST API and sync local state."""
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY", "")
    api_base = current_app.config.get("PAYSTACK_API_BASE", "https://api.paystack.co")
    is_mock = not secret_key or secret_key.startswith("mock_") or secret_key.startswith("test_mock") or current_app.config.get("TESTING")

    if is_mock:
        return {
            "status": True,
            "message": "Verification successful (mock)",
            "data": {
                "status": "success",
                "reference": reference,
                "amount": 350000,
                "currency": "NGN",
            },
        }

    headers = {
        "Authorization": f"Bearer {secret_key}",
    }

    try:
        r = requests.get(f"{api_base}/transaction/verify/{reference}", headers=headers, timeout=15)
        res = r.json()
        if res.get("status") and (res.get("data") or {}).get("status") == "success":
            handle_paystack_charge_success(res["data"])
        return res
    except Exception as e:
        return {"status": False, "message": str(e)}
