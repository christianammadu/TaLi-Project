"""Unit tests for Subscription & Billing Data Models and Entitlements (WP-01)."""

import pytest
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

from app.data.models import SubscriptionPlan, MerchantSubscription, BillingInvoice
from app.services.billing import seed_default_plans, get_merchant_subscription, is_feature_entitled
from app.services.uuid_utils import uuid7


class FakeDBStore:
    def __init__(self):
        self.plans = {}
        self.subscriptions = {}
        self.invoices = {}
        self._next_plan_id = 1

    def execute(self, stmt):
        class Result:
            def __init__(self, items):
                self._items = items
            def scalar_one_or_none(self):
                return self._items[0] if self._items else None
            def scalars(self):
                class Scalars:
                    def __init__(self, it):
                        self._it = it
                    def all(self):
                        return list(self._it)
                return Scalars(self._items)

        params = stmt.compile().params
        str_stmt = str(stmt).lower()
        if "subscription_plans" in str_stmt:
            target_slug = None
            for v in params.values():
                if isinstance(v, str):
                    target_slug = v
                    break
            if target_slug:
                matching = [p for p in self.plans.values() if p.slug == target_slug]
                return Result(matching)
            return Result(list(self.plans.values()))

        if "merchant_subscriptions" in str_stmt:
            target_user = None
            for v in params.values():
                target_user = v
                break
            if target_user and target_user in self.subscriptions:
                return Result([self.subscriptions[target_user]])
            return Result([])
        return Result([])


    def get(self, model, key):
        if model == SubscriptionPlan:
            return self.plans.get(key)
        if model == MerchantSubscription:
            return self.subscriptions.get(key)
        return None

    def add(self, obj):
        if isinstance(obj, SubscriptionPlan):
            if not obj.id:
                obj.id = self._next_plan_id
                self._next_plan_id += 1
            self.plans[obj.id] = obj
        elif isinstance(obj, MerchantSubscription):
            self.subscriptions[obj.user_id] = obj
        elif isinstance(obj, BillingInvoice):
            self.invoices[obj.id] = obj

    def flush(self):
        pass


@pytest.fixture
def fake_billing_db(monkeypatch):
    store = FakeDBStore()

    @contextmanager
    def mock_scope():
        yield store

    monkeypatch.setattr("app.services.billing.session_scope", mock_scope)
    return store


def test_seed_default_plans(fake_billing_db):
    plans = seed_default_plans(fake_billing_db)
    assert len(plans) == 3
    slugs = {p.slug for p in plans}
    assert slugs == {"starter", "pro", "business"}

    pro = next(p for p in plans if p.slug == "pro")
    assert pro.price == 3500.00
    assert "voice_notes" in pro.features
    assert "pos_vision_ocr" in pro.features


def test_merchant_subscription_provisioning_and_entitlements(fake_billing_db):
    user_id = uuid7()
    sub = get_merchant_subscription(user_id)
    assert sub is not None
    assert sub["plan_slug"] == "starter"
    assert sub["is_active"] is True
    assert "text_bookkeeping" in sub["features"]
    assert "voice_notes" not in sub["features"]

    # Upgrade to Pro
    plans = seed_default_plans(fake_billing_db)
    pro_plan = next(p for p in plans if p.slug == "pro")
    fake_billing_db.subscriptions[user_id].plan_id = pro_plan.id

    sub_pro = get_merchant_subscription(user_id)
    assert sub_pro["plan_slug"] == "pro"
    assert is_feature_entitled(user_id, "voice_notes") is True
    assert is_feature_entitled(user_id, "pos_vision_ocr") is True
    assert is_feature_entitled(user_id, "credit_passport_dossier") is False


def test_grace_period_entitlement_retention(fake_billing_db):
    user_id = uuid7()
    seed_default_plans(fake_billing_db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Past due but within 3-day grace period
    sub = MerchantSubscription(
        id=uuid7(),
        user_id=user_id,
        plan_id=2,  # Pro
        status="past_due",
        current_period_start=now - timedelta(days=31),
        current_period_end=now - timedelta(days=1),
        grace_period_ends_at=now + timedelta(days=2),
    )
    fake_billing_db.subscriptions[user_id] = sub

    sub_status = get_merchant_subscription(user_id)
    assert sub_status["is_active"] is True
    assert is_feature_entitled(user_id, "voice_notes") is True

    # Grace period expired
    sub.grace_period_ends_at = now - timedelta(hours=1)
    sub_status_expired = get_merchant_subscription(user_id)
    assert sub_status_expired["is_active"] is False
    assert is_feature_entitled(user_id, "voice_notes") is False
