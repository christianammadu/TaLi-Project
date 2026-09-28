"""Unit and integration tests for WP-10: On-demand Statement Generator (PDF & Excel Export).

Tests:
1. Period date resolution (this_month, last_month, last_90_days, all_time, custom ranges).
2. Business name resolution from User model and JSON profiles.
3. Transaction retrieval and date-range filtering.
4. Summary metrics computation (inflow, outflow, net movement, opening/closing balance).
5. CSV export generation, headers, and formatted currency amounts.
6. PDF export generation using ReportLab renderer (valid PDF binary, correct headers).
7. Excel export generation using openpyxl renderer (valid XLSX binary).
8. Multi-tenant statement data isolation (Merchant A vs Merchant B).
9. Portal statement view authentication check.
10. Authenticated portal statement view rendering and KPI presence.
11. HTMX partial statement preview rendering.
12. End-to-end download handlers: CSV, PDF, and Excel.
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import io
import pytest
from app import create_app
from app.data.models import User
from app.portal.auth import clear_all_portal_lockouts
from app.portal.statement import (
    export_statement_csv,
    export_statement_excel,
    export_statement_pdf,
    get_merchant_business_name,
    get_statement_summary,
    get_statement_transactions,
    resolve_period_dates,
)

USER_A = "018e3812-7000-7000-8000-000000000001"
USER_B = "018e3812-7000-7000-8000-000000000002"


class MockUserRecord:
    def __init__(self, id, display_name="Mama Ngozi", business_profile=None):
        self.id = id
        self.display_name = display_name
        self.business_profile = business_profile or {"name": "Ngozi Provisions Hub"}
        self.phone_number = "+2348011223344"
        self.is_verified = True


@pytest.fixture
def sample_transactions():
    """Deterministic transaction set for User A and User B across time."""
    today = date.today()
    first_of_this_month = date(today.year, today.month, 1)

    # 45 days ago is either last month or earlier
    last_month_date = first_of_this_month - timedelta(days=15)
    two_months_ago = first_of_this_month - timedelta(days=60)

    return [
        # User A - prior history
        {
            "id": "tx-1",
            "user_id": USER_A,
            "date": two_months_ago.isoformat(),
            "type": "income",
            "action": "sale",
            "item": "Flour 50kg",
            "amount": 40000.0,
            "currency": "NGN",
            "category": "Sales",
        },
        # User A - last month
        {
            "id": "tx-2",
            "user_id": USER_A,
            "date": last_month_date.isoformat(),
            "type": "income",
            "action": "sale",
            "item": "Sugar 20kg",
            "amount": 25000.0,
            "currency": "NGN",
            "category": "Sales",
        },
        {
            "id": "tx-3",
            "user_id": USER_A,
            "date": last_month_date.isoformat(),
            "type": "expense",
            "action": "purchase",
            "item": "Diesel Generator Fuel",
            "amount": 10000.0,
            "currency": "NGN",
            "category": "Utilities",
        },
        # User A - this month
        {
            "id": "tx-4",
            "user_id": USER_A,
            "date": today.isoformat(),
            "type": "income",
            "action": "sale",
            "item": "Bread loaves (x50)",
            "amount": 35000.0,
            "currency": "NGN",
            "category": "Sales",
        },
        {
            "id": "tx-5",
            "user_id": USER_A,
            "date": today.isoformat(),
            "type": "expense",
            "action": "purchase",
            "item": "Yeast and Baking powder",
            "amount": 8000.0,
            "currency": "NGN",
            "category": "Supplies",
        },
        # User B - this month (isolation check)
        {
            "id": "tx-6",
            "user_id": USER_B,
            "date": today.isoformat(),
            "type": "income",
            "action": "sale",
            "item": "Dangote Cement 50kg (x10)",
            "amount": 90000.0,
            "currency": "NGN",
            "category": "Building Supplies",
        },
    ]


@pytest.fixture
def mock_statement_env(monkeypatch, sample_transactions):
    """Mock query_statement, query_opening_balance, and session_scope across modules."""
    import app.portal.statement as stmt_mod
    import app.portal.routes as routes_mod

    def mock_query_statement(user_id, filters, limit=5000):
        rows = [t for t in sample_transactions if t["user_id"] == user_id]
        if filters.get("period_start"):
            rows = [t for t in rows if t["date"] >= filters["period_start"]]
        if filters.get("period_end"):
            rows = [t for t in rows if t["date"] <= filters["period_end"]]
        if filters.get("tx_type") and filters["tx_type"] != "all":
            rows = [t for t in rows if t["type"] == filters["tx_type"]]
        return rows

    def mock_query_opening_balance(user_id, before_date):
        if not before_date:
            return {}
        prior = [
            t for t in sample_transactions
            if t["user_id"] == user_id and t["date"] < before_date
        ]
        inflow = sum(t["amount"] for t in prior if t["type"] == "income")
        outflow = sum(t["amount"] for t in prior if t["type"] == "expense")
        return {"NGN": inflow - outflow}

    class MockSession:
        def get(self, model, ident):
            if model is User:
                if ident == USER_A:
                    return MockUserRecord(USER_A, "Mama Ngozi", {"name": "Ngozi Provisions Hub"})
                elif ident == USER_B:
                    return MockUserRecord(USER_B, "Alhaji Bello", {"name": "Bello Building Materials"})
            return None

    @contextmanager
    def mock_scope():
        yield MockSession()

    monkeypatch.setattr(stmt_mod, "query_statement", mock_query_statement)
    monkeypatch.setattr(stmt_mod, "query_opening_balance", mock_query_opening_balance)
    monkeypatch.setattr("app.data.queries.query_statement", mock_query_statement)
    monkeypatch.setattr("app.data.queries.query_opening_balance", mock_query_opening_balance)
    monkeypatch.setattr("app.data.db.session_scope", mock_scope)
    monkeypatch.setattr("app.portal.auth.session_scope", mock_scope)

    return {
        "query_statement": mock_query_statement,
        "query_opening_balance": mock_query_opening_balance,
    }


@pytest.fixture
def app(monkeypatch, mock_statement_env):
    """Flask app configured for testing statement views."""
    import app as app_module
    import app.portal.auth as auth_mod
    import app.portal.routes as routes_mod
    import app.portal.statement as stmt_mod
    import app.portal.metrics as metrics_mod
    import app.admin.metrics as admin_metrics_mod

    @contextmanager
    def mock_scope():
        class MockEmptySession:
            def get(self, model, ident):
                return MockUserRecord(ident, "Mama Ngozi", {"name": "Ngozi Provisions Hub"})
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
    monkeypatch.setattr(metrics_mod, "session_scope", mock_scope)
    monkeypatch.setattr(admin_metrics_mod, "session_scope", mock_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-statement-secret-key",
    )
    return application


@pytest.fixture
def client(app):
    clear_all_portal_lockouts()
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Client with an active merchant session for USER_A."""
    clear_all_portal_lockouts()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["merchant_logged_in"] = True
        sess["merchant_user_id"] = USER_A
        sess["merchant_id"] = USER_A
        sess["merchant_phone"] = "+2348011223344"
        sess["merchant_name"] = "Ngozi Provisions Hub"
    return client



# -----------------------------------------------------------------------------
# Unit Tests: Period Resolution & Math
# -----------------------------------------------------------------------------

def test_resolve_period_dates_this_month():
    start, end, label = resolve_period_dates("this_month")
    today = date.today()
    assert start == date(today.year, today.month, 1).isoformat()
    assert end == today.isoformat()
    assert today.strftime("%B %Y") in label


def test_resolve_period_dates_last_month():
    start, end, label = resolve_period_dates("last_month")
    today = date.today()
    first_this = date(today.year, today.month, 1)
    last_prev = first_this - timedelta(days=1)
    start_prev = date(last_prev.year, last_prev.month, 1)

    assert start == start_prev.isoformat()
    assert end == last_prev.isoformat()
    assert last_prev.strftime("%B %Y") in label


def test_resolve_period_dates_last_90_days():
    start, end, label = resolve_period_dates("last_90_days")
    today = date.today()
    assert start == (today - timedelta(days=90)).isoformat()
    assert end == today.isoformat()
    assert "Last 90 Days" in label


def test_resolve_period_dates_all_time():
    start, end, label = resolve_period_dates("all_time")
    assert start is None
    assert end is None
    assert label == "All Time"


def test_resolve_period_dates_custom():
    start, end, label = resolve_period_dates("custom", "2026-01-15", "2026-02-20")
    assert start == "2026-01-15"
    assert end == "2026-02-20"
    assert "15 Jan 2026 – 20 Feb 2026" in label

    # Reversed dates should auto-correct order
    start_rev, end_rev, _ = resolve_period_dates("custom", "2026-03-01", "2026-01-01")
    assert start_rev == "2026-01-01"
    assert end_rev == "2026-03-01"

    # Malformed dates fall back to this month
    start_bad, end_bad, _ = resolve_period_dates("custom", "invalid", "dates")
    assert start_bad == date(date.today().year, date.today().month, 1).isoformat()


def test_get_merchant_business_name(mock_statement_env):
    name_a = get_merchant_business_name(USER_A)
    assert name_a == "Ngozi Provisions Hub"

    name_b = get_merchant_business_name(USER_B)
    assert name_b == "Bello Building Materials"

    name_missing = get_merchant_business_name("00000000-0000-0000-0000-000000000000", default_name="Fallback Biz")
    assert name_missing == "Fallback Biz"


def test_get_statement_transactions_and_isolation(mock_statement_env):
    # User A gets only User A's transactions
    txs_a = get_statement_transactions(USER_A)
    assert len(txs_a) == 5
    for t in txs_a:
        assert t["user_id"] == USER_A
        assert "Cement" not in t["item"]

    # User B gets only User B's transactions
    txs_b = get_statement_transactions(USER_B)
    assert len(txs_b) == 1
    assert txs_b[0]["item"] == "Dangote Cement 50kg (x10)"


def test_get_statement_summary_math(mock_statement_env):
    summary = get_statement_summary(USER_A, period="this_month")
    # This month for User A: tx-4 (+35,000) and tx-5 (-8,000)
    assert summary["transaction_count"] == 2
    assert summary["total_inflow"] == 35000.0
    assert summary["total_outflow"] == 8000.0
    assert summary["net_movement"] == 27000.0
    # Prior opening balance: tx-1 (+40k) + tx-2 (+25k) - tx-3 (-10k) = 55,000
    assert summary["opening_balance"] == 55000.0
    assert summary["closing_balance"] == 82000.0
    assert summary["has_rows"] is True
    assert "₦35,000" in summary["total_inflow_fmt"]


# -----------------------------------------------------------------------------
# Exporter Tests: CSV, PDF, Excel
# -----------------------------------------------------------------------------

def test_export_statement_csv(mock_statement_env):
    csv_text, filename = export_statement_csv(USER_A, period="this_month", business_name="Ngozi Hub")
    assert filename.startswith("tali_statement_ngozi_hub_")
    assert filename.endswith(".csv")

    lines = csv_text.strip().split("\r\n" if "\r\n" in csv_text else "\n")
    header = lines[0].split(",")
    assert "Date" in header
    assert "Description" in header
    assert "Money In" in header
    assert "Money Out" in header
    assert "Amount" in header

    # Contains this month's items
    assert any("Bread loaves" in l for l in lines)
    assert any("Yeast and Baking powder" in l for l in lines)
    # Does not contain User B's cement
    assert not any("Dangote Cement" in l for l in lines)


def test_export_statement_pdf(mock_statement_env):
    pdf_bytes, filename = export_statement_pdf(USER_A, period="this_month", business_name="Ngozi Hub")
    assert filename.startswith("tali_statement_ngozi_hub_")
    assert filename.endswith(".pdf")
    assert len(pdf_bytes) > 0
    # Valid PDF signature
    assert pdf_bytes.startswith(b"%PDF")


def test_export_statement_excel(mock_statement_env):
    xlsx_bytes, filename = export_statement_excel(USER_A, period="this_month", business_name="Ngozi Hub")
    assert filename.startswith("tali_statement_ngozi_hub_")
    assert filename.endswith(".xlsx")
    assert len(xlsx_bytes) > 0
    # Valid ZIP (OOXML) file signature
    assert xlsx_bytes.startswith(b"PK\x03\x04")


# -----------------------------------------------------------------------------
# Route & Web Integration Tests
# -----------------------------------------------------------------------------

def test_statement_routes_require_auth(client):
    res_view = client.get("/portal/statement")
    assert res_view.status_code == 302
    assert "/portal/login" in res_view.headers["Location"]

    res_export = client.get("/portal/statement/export?format=csv")
    assert res_export.status_code == 302
    assert "/portal/login" in res_export.headers["Location"]


def test_statement_view_authenticated(auth_client, mock_statement_env):
    res = auth_client.get("/portal/statement")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Financial Statements" in html
    assert "Ngozi Provisions Hub" in html
    assert "Total Inflow" in html
    assert "Total Outflow" in html
    assert "Net Movement" in html
    assert "Download PDF" in html
    assert "Download Excel" in html
    assert "Download CSV" in html


def test_statement_view_htmx_partial(auth_client, mock_statement_env):
    res = auth_client.get("/portal/statement?period=last_month", headers={"HX-Request": "true"})
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "<!DOCTYPE html>" not in html
    assert "statement-preview-container" in html
    assert "Sugar 20kg" in html
    assert "Diesel Generator Fuel" in html


def test_statement_export_csv_download(auth_client, mock_statement_env):
    res = auth_client.get("/portal/statement/export?format=csv&period=this_month")
    assert res.status_code == 200
    assert "text/csv" in res.headers["Content-Type"]
    assert "attachment;" in res.headers["Content-Disposition"]
    assert ".csv" in res.headers["Content-Disposition"]

    content = res.data.decode("utf-8")
    assert "Date,Description,Category,Type" in content
    assert "Bread loaves" in content


def test_statement_export_pdf_download(auth_client, mock_statement_env):
    res = auth_client.get("/portal/statement/export?format=pdf&period=this_month")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/pdf"
    assert "attachment;" in res.headers["Content-Disposition"]
    assert ".pdf" in res.headers["Content-Disposition"]
    assert res.data.startswith(b"%PDF")


def test_statement_export_excel_download(auth_client, mock_statement_env):
    res = auth_client.get("/portal/statement/export?format=excel&period=this_month")
    assert res.status_code == 200
    assert "openxmlformats" in res.headers["Content-Type"]
    assert "attachment;" in res.headers["Content-Disposition"]
    assert ".xlsx" in res.headers["Content-Disposition"]
    assert res.data.startswith(b"PK\x03\x04")


def test_statement_export_custom_range(auth_client, mock_statement_env):
    today = date.today().isoformat()
    res = auth_client.get(f"/portal/statement/export?format=csv&period=custom&start_date={today}&end_date={today}")
    assert res.status_code == 200
    content = res.data.decode("utf-8")
    assert "Bread loaves" in content
