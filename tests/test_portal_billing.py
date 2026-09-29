"""Unit and integration tests for WP-03: Merchant Portal Billing & Upgrade Hub.

Tests:
1. Authentication gating on all billing routes (/portal/billing, /initialize, /verify, /receipt).
2. Authenticated portal billing hub view rendering, active subscription, and plan cards.
3. Paystack checkout session initialization (valid tier, invalid tier, mock handling).
4. Paystack transaction verification callback and flash message feedback.
5. Merchant invoice receipt rendering and multi-tenant isolation.
6. Strict UI compliance checks (zero emojis, zero em dashes) across all billing templates.
"""

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import re
import pytest

from app import create_app
from app.portal.auth import clear_all_portal_lockouts
from app.services.billing import (
    get_available_plans,
    get_merchant_billing_overview,
    get_merchant_invoices,
    get_merchant_usage,
)

USER_A = "018e3812-7000-7000-8000-000000000001"
USER_B = "018e3812-7000-7000-8000-000000000002"


class MockUserRecord:
    def __init__(self, id, display_name="Mama Ngozi Provisions", phone="+2348011223344"):
        self.id = id
        self.display_name = display_name
        self.phone_number = phone
        self.is_verified = True
        self.business_profile = {"name": display_name}


class MockSubscriptionRecord:
    def __init__(self, user_id, plan_slug="starter", status="active"):
        self.id = b"sub_mock_bytes_1"
        self.user_id = user_id
        self.plan_id = 1
        self.status = status
        self.current_period_start = datetime.now(timezone.utc).replace(tzinfo=None)
        self.current_period_end = self.current_period_start + timedelta(days=30)
        self.grace_period_ends_at = None
        self.paystack_customer_code = "CUS_mock_123"
        self.paystack_subscription_code = "SUB_mock_123"
        self.paystack_email_token = None
        self.canceled_at = None


class MockPlanRecord:
    def __init__(self, slug, name, price, features):
        self.id = 1
        self.slug = slug
        self.name = name
        self.price = price
        self.currency = "NGN"
        self.billing_interval = "monthly"
        self.features = features
        self.is_active = True
        self.paystack_plan_code = f"PLN_{slug}"


class MockInvoiceRecord:
    def __init__(self, id, user_id, reference, amount=3500.00, status="paid"):
        self.id = id
        self.subscription_id = b"sub_mock_bytes_1"
        self.user_id = user_id
        self.paystack_reference = reference
        self.amount = amount
        self.currency = "NGN"
        self.status = status
        self.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.created_at = self.paid_at
        self.invoice_pdf_url = None


@pytest.fixture
def mock_billing_env(monkeypatch):
    """Mock database access for billing routes and services."""
    import app.services.billing as billing_mod
    import app.portal.routes as routes_mod

    mock_invoices = [
        MockInvoiceRecord(
            id=b"inv_mock_001_bin",
            user_id=USER_A,
            reference="tali_inv_ref_001",
            amount=3500.00,
            status="paid",
        ),
        MockInvoiceRecord(
            id=b"inv_mock_002_bin",
            user_id=USER_B,
            reference="tali_inv_ref_002",
            amount=9500.00,
            status="paid",
        ),
    ]

    mock_plans = [
        MockPlanRecord("starter", "Free Starter", 0.00, ["text_bookkeeping", "basic_statements"]),
        MockPlanRecord("pro", "Merchant Pro", 3500.00, ["text_bookkeeping", "voice_notes", "branded_receipts"]),
        MockPlanRecord("business", "Business Fleet", 9500.00, ["text_bookkeeping", "voice_notes", "credit_passport_dossier"]),
    ]

    @contextmanager
    def mock_scope():
        class MockBillingSession:
            def execute(self, stmt):
                class MockResult:
                    def __init__(self, items):
                        self.items = items
                    def scalars(self):
                        return self
                    def all(self):
                        return self.items
                    def scalar_one_or_none(self):
                        return self.items[0] if self.items else None
                    def scalar(self):
                        return len(self.items)

                # Route query matching
                stmt_str = str(stmt).lower()
                if "merchant_subscriptions" in stmt_str:
                    return MockResult([MockSubscriptionRecord(USER_A, "starter", "active")])
                elif "subscription_plans" in stmt_str:
                    matched_plan = None
                    try:
                        for crit in getattr(stmt, "_where_criteria", ()):
                            right = getattr(crit, "right", None)
                            val = getattr(right, "value", None)
                            if val:
                                matched_plan = next((p for p in mock_plans if p.slug == val), None)
                    except Exception:
                        pass
                    if matched_plan:
                        return MockResult([matched_plan])
                    return MockResult(mock_plans)
                elif "billing_invoices" in stmt_str:
                    if str(USER_A) in stmt_str or "idx_invoice_user" in stmt_str:
                        return MockResult([mock_invoices[0]])
                    return MockResult(mock_invoices)
                elif "count(" in stmt_str:
                    class CountResult:
                        def scalar(self):
                            return 12
                    return CountResult()
                return MockResult([])

            def get(self, model, ident):
                if model.__name__ == "SubscriptionPlan":
                    for p in mock_plans:
                        if p.id == ident or p.slug == ident:
                            return p
                    return mock_plans[0]
                elif model.__name__ == "User":
                    return MockUserRecord(ident)
                return None

            def add(self, obj):
                pass
            def flush(self):
                pass

        yield MockBillingSession()

    monkeypatch.setattr(billing_mod, "session_scope", mock_scope)
    monkeypatch.setattr("app.data.db.session_scope", mock_scope)
    monkeypatch.setattr("app.portal.auth.session_scope", mock_scope)

    return {
        "mock_invoices": mock_invoices,
        "mock_plans": mock_plans,
    }


@pytest.fixture
def app(monkeypatch, mock_billing_env):
    """Flask application configured for testing portal billing."""
    import app as app_module
    import app.portal.auth as auth_mod
    import app.admin.metrics as admin_metrics_mod

    @contextmanager
    def mock_scope():
        class MockEmptySession:
            def get(self, model, ident):
                return MockUserRecord(ident)
            def execute(self, stmt):
                class EmptyResult:
                    def all(self):
                        return []
                    def scalar_one_or_none(self):
                        return None
                    def first(self):
                        return None
                return EmptyResult()
        yield MockEmptySession()

    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    monkeypatch.setattr(auth_mod, "session_scope", mock_scope)
    monkeypatch.setattr(admin_metrics_mod, "session_scope", mock_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-portal-billing-secret",
        PAYSTACK_SECRET_KEY="mock_sec_key_123",
        PAYSTACK_PUBLIC_KEY="mock_pub_key_123",
    )
    return application


@pytest.fixture
def client(app):
    clear_all_portal_lockouts()
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Authenticated merchant client for USER_A."""
    clear_all_portal_lockouts()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["merchant_logged_in"] = True
        sess["merchant_user_id"] = USER_A
        sess["merchant_id"] = USER_A
        sess["merchant_phone"] = "+2348011223344"
        sess["merchant_name"] = "Mama Ngozi Provisions"
        sess["merchant_email"] = "ngozi@example.com"
    return client


# -----------------------------------------------------------------------------
# Route Authentication Tests
# -----------------------------------------------------------------------------

def test_billing_routes_require_authentication(client):
    """Verify unauthenticated access to billing endpoints redirects to login."""
    res_hub = client.get("/portal/billing")
    assert res_hub.status_code == 302
    assert "/portal/login" in res_hub.headers["Location"]

    res_init = client.post("/portal/billing/initialize", json={"plan_slug": "pro"})
    assert res_init.status_code == 302
    assert "/portal/login" in res_init.headers["Location"]

    res_verify = client.get("/portal/billing/verify?reference=ref_123")
    assert res_verify.status_code == 302
    assert "/portal/login" in res_verify.headers["Location"]

    res_receipt = client.get("/portal/billing/invoices/inv_123/receipt")
    assert res_receipt.status_code == 302
    assert "/portal/login" in res_receipt.headers["Location"]


# -----------------------------------------------------------------------------
# Billing Hub View Tests
# -----------------------------------------------------------------------------

def test_billing_hub_view_authenticated(auth_client, mock_billing_env):
    """Verify authenticated merchant can view the billing hub with plan cards."""
    res = auth_client.get("/portal/billing")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    assert "Subscription & Billing" in html
    assert "Mama Ngozi Provisions" in html
    assert "Free Starter" in html
    assert "Merchant Pro" in html
    assert "Business Fleet" in html
    assert "Monthly Ledger Usage" in html
    assert "Select Subscription Plan" in html
    assert "Billing Records & Tax Invoices" in html


def test_billing_initialize_endpoint(auth_client, mock_billing_env):
    """Verify initiating Paystack checkout returns reference and authorization."""
    # Pro tier initialization
    res_pro = auth_client.post("/portal/billing/initialize", json={"plan_slug": "pro"})
    assert res_pro.status_code == 200
    data_pro = res_pro.get_json()
    assert data_pro["status"] is True
    assert "reference" in data_pro["data"]
    assert "authorization_url" in data_pro["data"]

    # Business tier initialization
    res_biz = auth_client.post("/portal/billing/initialize", json={"plan_slug": "business"})
    assert res_biz.status_code == 200
    data_biz = res_biz.get_json()
    assert data_biz["status"] is True

    # Rejection of starter tier (free, no checkout)
    res_starter = auth_client.post("/portal/billing/initialize", json={"plan_slug": "starter"})
    assert res_starter.status_code == 400
    assert "Invalid or unsupported" in res_starter.get_json()["message"]

    # Rejection of invalid tier
    res_invalid = auth_client.post("/portal/billing/initialize", json={"plan_slug": "enterprise_custom"})
    assert res_invalid.status_code == 400


def test_billing_verify_callback(auth_client, monkeypatch):
    """Verify transaction status verification callback and redirect."""
    import app.portal.routes as routes_mod

    # Mock verify_paystack_transaction
    monkeypatch.setattr(
        routes_mod,
        "verify_paystack_transaction",
        lambda ref: {"status": True, "data": {"status": "success", "reference": ref}},
    )

    res = auth_client.get("/portal/billing/verify?reference=tali_sub_valid_123")
    assert res.status_code == 302
    assert "/portal/billing" in res.headers["Location"]


def test_billing_invoice_receipt_view(auth_client, monkeypatch):
    """Verify viewing official tax receipt for a valid invoice."""
    import app.portal.routes as routes_mod

    monkeypatch.setattr(
        routes_mod,
        "get_invoice_by_id",
        lambda uid, iid: {
            "id": iid,
            "reference": "tali_inv_ref_001",
            "amount": 3500.0,
            "amount_formatted": "₦3,500.00",
            "currency": "NGN",
            "status": "paid",
            "paid_at": "Sep 29, 2026",
            "created_at": "Sep 29, 2026",
            "invoice_pdf_url": None,
        } if (uid == USER_A and iid == "tali_inv_ref_001") else None,
    )

    # Valid invoice for USER_A
    res = auth_client.get("/portal/billing/invoices/tali_inv_ref_001/receipt")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Official Payment Receipt" in html
    assert "INVOICE tali_inv_ref_001" in html
    assert "₦3,500.00" in html
    assert "Mama Ngozi Provisions" in html
    assert "Print Receipt" in html

    # Unauthorized access (invoice belonging to someone else)
    res_unauth = auth_client.get("/portal/billing/invoices/unknown_or_other_user/receipt")
    assert res_unauth.status_code == 302
    assert "/portal/billing" in res_unauth.headers["Location"]


# -----------------------------------------------------------------------------
# UI & Visual Design Compliance Tests (Zero Emojis & Zero Em Dashes)
# -----------------------------------------------------------------------------

def test_no_emojis_in_billing_templates():
    """Guarantee absolute zero emojis in all billing UI templates."""
    # Common emoji Unicode pattern
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50]|[\u3030]"
    )

    templates_to_check = [
        "app/templates/portal/billing.html",
        "app/templates/portal/_plan_card.html",
        "app/templates/portal/receipt.html",
    ]

    for tpl_path in templates_to_check:
        with open(tpl_path, "r", encoding="utf-8") as f:
            content = f.read()
            matches = emoji_pattern.findall(content)
            assert len(matches) == 0, f"Found emojis in {tpl_path}: {matches}"


def test_no_em_dashes_in_billing_templates():
    """Guarantee absolute zero em dashes (—) in all billing UI templates."""
    templates_to_check = [
        "app/templates/portal/billing.html",
        "app/templates/portal/_plan_card.html",
        "app/templates/portal/receipt.html",
    ]

    for tpl_path in templates_to_check:
        with open(tpl_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "—" not in content, f"Found prohibited em dash (—) in {tpl_path}"
