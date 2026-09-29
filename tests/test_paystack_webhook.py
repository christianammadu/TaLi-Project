"""Unit and integration tests for WP-02: Paystack Webhook & Verification Engine.

Tests:
1. HMAC-SHA512 webhook signature verification & tamper defense.
2. ISO datetime parsing for Paystack timestamps.
3. Inbound webhook endpoint security (rejects invalid/missing signatures with 401).
4. `charge.success` handling (invoice creation, subscription activation, idempotency).
5. `subscription.create` handling (linking Paystack subscription and customer codes).
6. `invoice.payment_failed` handling (activating 3-day grace period, recording failed invoice).
7. `subscription.disable` handling (graceful cancellation).
8. Ignored unhandled events (acknowledges with 200 OK).
9. Transaction initialize, verify, and subscription status endpoints.
"""

import hmac
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import pytest

from app import create_app
from app.data.models import SubscriptionPlan, MerchantSubscription, BillingInvoice
from app.services.billing import (
    verify_paystack_webhook_signature,
    parse_paystack_datetime,
    seed_default_plans,
    get_merchant_subscription,
    is_feature_entitled,
)
from app.services.uuid_utils import uuid7, uuid_to_bin, bin_to_uuid

TEST_PAYSTACK_SECRET = "sk_test_mock_paystack_secret_key_12345"


class MockBillingStore:
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
                    def first(self):
                        return self._it[0] if self._it else None
                return Scalars(self._items)

        params = stmt.compile().params
        str_stmt = str(stmt).lower()

        if "subscription_plans" in str_stmt:
            target_slug = None
            for k, v in params.items():
                if isinstance(v, str):
                    target_slug = v
                    break
            if target_slug:
                matches = [p for p in self.plans.values() if p.slug == target_slug or getattr(p, "paystack_plan_code", None) == target_slug]
                return Result(matches)
            return Result(list(self.plans.values()))

        if "billing_invoices" in str_stmt:
            target_ref = None
            for k, v in params.items():
                if isinstance(v, str):
                    target_ref = v
                    break
            if target_ref and target_ref in self.invoices:
                return Result([self.invoices[target_ref]])
            matches = [inv for inv in self.invoices.values() if inv.paystack_reference == target_ref]
            return Result(matches)

        if "merchant_subscriptions" in str_stmt:
            target_val = None
            for k, v in params.items():
                if v is not None:
                    target_val = v
                    break

            for sub in self.subscriptions.values():
                if sub.user_id == target_val or sub.user_id == uuid_to_bin(target_val):
                    return Result([sub])
                if getattr(sub, "paystack_subscription_code", None) == target_val:
                    return Result([sub])
                if getattr(sub, "paystack_customer_code", None) == target_val:
                    return Result([sub])
            return Result([])

        return Result([])

    def get(self, model, key):
        if model == SubscriptionPlan:
            return self.plans.get(key)
        if model == MerchantSubscription:
            for s in self.subscriptions.values():
                if s.id == key or s.user_id == key:
                    return s
            return None
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
            self.invoices[obj.paystack_reference] = obj

    def flush(self):
        pass

    def commit(self):
        pass


@pytest.fixture
def billing_store():
    store = MockBillingStore()
    seed_default_plans(store)
    return store


@pytest.fixture
def app(monkeypatch, billing_store):
    import app as app_mod
    import app.services.billing as billing_mod

    @contextmanager
    def mock_scope():
        yield billing_store

    monkeypatch.setattr(app_mod, "init_db", lambda a: None)
    monkeypatch.setattr(app_mod, "init_engine", lambda a: None)
    monkeypatch.setattr(billing_mod, "session_scope", mock_scope)

    app_instance = create_app()
    app_instance.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key-123",
        PAYSTACK_SECRET_KEY=TEST_PAYSTACK_SECRET,
        PAYSTACK_PUBLIC_KEY="pk_test_mock_12345",
    )
    return app_instance


@pytest.fixture
def client(app):
    return app.test_client()


def _compute_paystack_sig(payload_bytes: bytes, secret: str = TEST_PAYSTACK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha512).hexdigest()


# ============================================================================
# 1. Signature Verification & Date Parsing Unit Tests
# ============================================================================

def test_verify_paystack_webhook_signature():
    payload = b'{"event": "charge.success", "data": {}}'
    sig = _compute_paystack_sig(payload, TEST_PAYSTACK_SECRET)

    assert verify_paystack_webhook_signature(payload, sig, TEST_PAYSTACK_SECRET) is True
    # Tampered payload fails
    assert verify_paystack_webhook_signature(b'{"event": "tampered"}', sig, TEST_PAYSTACK_SECRET) is False
    # Wrong secret fails
    assert verify_paystack_webhook_signature(payload, sig, "wrong_secret") is False
    # Missing signature or secret fails
    assert verify_paystack_webhook_signature(payload, None, TEST_PAYSTACK_SECRET) is False
    assert verify_paystack_webhook_signature(payload, sig, "") is False


def test_parse_paystack_datetime():
    dt = parse_paystack_datetime("2026-10-29T12:00:00.000Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 10
    assert dt.day == 29
    assert dt.hour == 12

    assert parse_paystack_datetime(None) is None
    assert parse_paystack_datetime("invalid-date-string") is None


# ============================================================================
# 2. Webhook Endpoint Authentication Tests
# ============================================================================

def test_webhook_rejects_missing_signature(client):
    res = client.post("/billing/webhook/paystack", json={"event": "charge.success"})
    assert res.status_code == 401
    assert "Invalid webhook signature" in res.get_json()["message"]


def test_webhook_rejects_tampered_signature(client):
    headers = {"X-Paystack-Signature": "invalid_hex_signature"}
    res = client.post("/billing/webhook/paystack", json={"event": "charge.success"}, headers=headers)
    assert res.status_code == 401


# ============================================================================
# 3. Charge Success & Idempotency Tests
# ============================================================================

def test_webhook_charge_success_activates_subscription(client, billing_store):
    test_user_id = str(uuid7())
    payload = {
        "event": "charge.success",
        "data": {
            "reference": "ref_paystack_test_001",
            "amount": 350000,  # 3,500 NGN
            "currency": "NGN",
            "status": "success",
            "paid_at": "2026-09-29T10:00:00.000Z",
            "customer": {
                "customer_code": "CUS_test_001",
                "email": "merchant@example.com",
            },
            "metadata": {
                "user_id": test_user_id,
                "plan_slug": "pro",
            },
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    res = client.post(
        "/billing/webhook/paystack",
        data=raw_bytes,
        headers={"Content-Type": "application/json", "X-Paystack-Signature": sig},
    )
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "ok"
    assert res_data["result"]["status"] == "success"
    assert res_data["result"]["plan_slug"] == "pro"

    # Verify invoice recorded
    assert "ref_paystack_test_001" in billing_store.invoices
    inv = billing_store.invoices["ref_paystack_test_001"]
    assert inv.amount == 3500.0
    assert inv.status == "paid"

    # Verify subscription activated
    sub = billing_store.subscriptions.get(test_user_id) or billing_store.subscriptions.get(uuid_to_bin(test_user_id))
    assert sub is not None
    assert sub.status == "active"
    assert sub.paystack_customer_code == "CUS_test_001"


def test_webhook_charge_success_idempotency(client, billing_store):
    test_user_id = str(uuid7())
    payload = {
        "event": "charge.success",
        "data": {
            "reference": "ref_paystack_idempotent_002",
            "amount": 350000,
            "currency": "NGN",
            "status": "success",
            "paid_at": "2026-09-29T10:00:00.000Z",
            "customer": {"customer_code": "CUS_test_002"},
            "metadata": {"user_id": test_user_id, "plan_slug": "pro"},
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    # First delivery
    res1 = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res1.status_code == 200
    assert res1.get_json()["result"]["status"] == "success"

    # Duplicate delivery
    res2 = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res2.status_code == 200
    assert res2.get_json()["result"]["status"] == "already_processed"


# ============================================================================
# 4. Subscription Lifecycle Events Tests
# ============================================================================

def test_webhook_subscription_create(client, billing_store):
    user_id = uuid7()
    user_bin = uuid_to_bin(user_id)
    # Pre-existing subscription row
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sub = MerchantSubscription(
        id=uuid7(),
        user_id=user_bin,
        plan_id=2,
        status="trialing",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    billing_store.subscriptions[user_bin] = sub

    payload = {
        "event": "subscription.create",
        "data": {
            "subscription_code": "SUB_test_sub_999",
            "email_token": "token_email_abc",
            "customer": {"customer_code": "CUS_sub_999"},
            "next_payment_date": "2026-10-29T12:00:00.000Z",
            "metadata": {"user_id": str(user_id)},
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    res = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res.status_code == 200
    assert res.get_json()["result"]["status"] == "success"

    updated_sub = billing_store.subscriptions[user_bin]
    assert updated_sub.paystack_subscription_code == "SUB_test_sub_999"
    assert updated_sub.paystack_customer_code == "CUS_sub_999"
    assert updated_sub.paystack_email_token == "token_email_abc"
    assert updated_sub.status == "active"


def test_webhook_invoice_failed_activates_grace_period(client, billing_store):
    user_id = uuid7()
    user_bin = uuid_to_bin(user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sub = MerchantSubscription(
        id=uuid7(),
        user_id=user_bin,
        plan_id=2,
        status="active",
        paystack_subscription_code="SUB_fail_test",
        current_period_start=now - timedelta(days=30),
        current_period_end=now,
    )
    billing_store.subscriptions[user_bin] = sub

    payload = {
        "event": "invoice.payment_failed",
        "data": {
            "subscription_code": "SUB_fail_test",
            "amount": 350000,
            "reference": "inv_failed_ref_123",
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    res = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res.status_code == 200
    assert res.get_json()["result"]["status"] == "grace_period_activated"

    updated_sub = billing_store.subscriptions[user_bin]
    assert updated_sub.status == "past_due"
    assert updated_sub.grace_period_ends_at is not None
    # Grace period should be in future (~3 days)
    assert updated_sub.grace_period_ends_at > now

    # Verify failed invoice is recorded
    assert "inv_failed_ref_123" in billing_store.invoices
    assert billing_store.invoices["inv_failed_ref_123"].status == "failed"


def test_webhook_subscription_disable_cancels(client, billing_store):
    user_id = uuid7()
    user_bin = uuid_to_bin(user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sub = MerchantSubscription(
        id=uuid7(),
        user_id=user_bin,
        plan_id=2,
        status="active",
        paystack_subscription_code="SUB_cancel_test",
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
    )
    billing_store.subscriptions[user_bin] = sub

    payload = {
        "event": "subscription.disable",
        "data": {
            "subscription_code": "SUB_cancel_test",
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    res = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res.status_code == 200
    assert res.get_json()["result"]["status"] == "subscription_canceled"

    updated_sub = billing_store.subscriptions[user_bin]
    assert updated_sub.status == "canceled"
    assert updated_sub.canceled_at is not None


def test_webhook_unhandled_event_returns_ignored(client):
    payload = {"event": "transfer.success", "data": {}}
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _compute_paystack_sig(raw_bytes)

    res = client.post("/billing/webhook/paystack", data=raw_bytes, headers={"Content-Type": "application/json", "X-Paystack-Signature": sig})
    assert res.status_code == 200
    assert res.get_json()["result"]["status"] == "ignored"


# ============================================================================
# 5. Initialization, Verification & Subscription API Tests
# ============================================================================

def test_initialize_checkout_endpoint(client):
    test_user_id = str(uuid7())
    res = client.post(
        "/billing/initialize",
        json={
            "user_id": test_user_id,
            "plan_slug": "pro",
            "email": "test@tali.africa",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] is True
    assert "authorization_url" in data["data"]
    assert "access_code" in data["data"]
    assert "reference" in data["data"]


def test_verify_transaction_endpoint(client):
    res = client.get("/billing/verify?reference=test_ref_98765")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] is True
    assert data["data"]["reference"] == "test_ref_98765"


def test_merchant_subscription_status_endpoint(client):
    test_user_id = str(uuid7())
    res = client.get(f"/billing/subscription?user_id={test_user_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] is True
    assert data["subscription"]["plan_slug"] == "starter"
    assert data["subscription"]["is_active"] is True
