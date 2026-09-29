"""Subscription & Billing Service — Core monetization and entitlement logic.

Handles plan definitions, subscription status checks, grace periods, and feature entitlements.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select

from app.data.db import session_scope
from app.data.models import SubscriptionPlan, MerchantSubscription, BillingInvoice
from app.services.uuid_utils import uuid7

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
                "id": str(sub.id),
                "plan_slug": plan_slug,
                "plan_name": plan_name,
                "status": sub.status,
                "is_active": is_active,
                "features": features,
                "current_period_end": sub.current_period_end,
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
