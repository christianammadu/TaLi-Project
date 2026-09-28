"""Unit and integration tests for WP-08: Merchant Cashflow & Ledger Visualizer.

Tests:
1. Financial summary calculations (lifetime, MTD, today, receivables, payables).
2. Multi-tenant isolation (Merchant A cannot see Merchant B's transactions).
3. Empty state handling (zero transactions, zero division safety).
4. Cashflow trends daily binning and series alignment.
5. Ledger transactions retrieval, type filtering, search filtering, and pagination.
6. Dashboard view rendering with live KPI metrics and Chart.js payload.
7. Full ledger transactions view rendering.
8. HTMX partial transaction rows rendering.
9. JSON API for cashflow chart period switching.
10. Access control and unauthenticated redirects.
"""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from app import create_app
from app.portal.auth import clear_all_portal_lockouts, login_merchant
from app.portal.metrics import (
    get_merchant_cashflow_trends,
    get_merchant_financial_summary,
    get_merchant_transactions,
    get_recent_merchant_transactions,
)


class MockTx:
    def __init__(self, id, user_id, type, action, amount, currency, item, description, raw_text, tx_date):
        self.id = id
        self.user_id = user_id
        self.type = type
        self.action = action
        self.amount = Decimal(str(amount))
        self.currency = currency
        self.item = item
        self.description = description
        self.raw_text = raw_text
        self.transaction_date = tx_date
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.category_id = None
        self.business_id = None


class MockDebt:
    def __init__(self, user_id, person_name, debt_type, balance):
        self.user_id = user_id
        self.person_name = person_name
        self.debt_type = debt_type
        self.outstanding_balance = Decimal(str(balance))
        self.currency = "NGN"


class MockStore:
    def __init__(self):
        self.transactions = []
        self.debts = []
        self.inventory = []


@pytest.fixture
def store():
    s = MockStore()
    today = date.today()
    user_a = "018e3812-7000-7000-8000-000000000001"
    user_b = "018e3812-7000-7000-8000-000000000002"

    # User A transactions
    s.transactions.append(MockTx("tx-1", user_a, "income", "sale", 50000.00, "NGN", "50kg Bag of Rice", "Sold 1 bag of rice", "sold 1 rice 50k", today))
    s.transactions.append(MockTx("tx-2", user_a, "income", "sale", 25000.00, "NGN", "Vegetable Oil 25L", "Sold 1 keg oil", "sold 1 oil 25k", today - timedelta(days=2)))
    s.transactions.append(MockTx("tx-3", user_a, "expense", "purchase", 15000.00, "NGN", "Petrol Fuel", "Shop generator fuel", "bought fuel 15k", today - timedelta(days=1)))

    # User B transactions (to test isolation)
    s.transactions.append(MockTx("tx-4", user_b, "income", "sale", 99000.00, "NGN", "Cement 50kg", "Sold cement", "sold cement 99k", today))

    # User A debts
    s.debts.append(MockDebt(user_a, "Uncle Jude", "receivable", 12000.00))
    s.debts.append(MockDebt(user_a, "Flour Mill PLC", "payable", 8000.00))

    # User A inventory
    s.inventory.append({"user_id": user_a, "item_name": "Rice 50kg"})
    s.inventory.append({"user_id": user_a, "item_name": "Oil 25L"})

    return s


class MockMetricsSession:
    def __init__(self, store: MockStore):
        self.store = store

    def execute(self, stmt):
        class Row:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class Result:
            def __init__(self, items):
                self._items = items if isinstance(items, list) else [items]

            def scalars(self):
                return self

            def scalar(self):
                return self._items[0] if self._items else None

            def scalar_one_or_none(self):
                return self._items[0] if self._items else None

            def first(self):
                return self._items[0] if self._items else None

            def all(self):
                return self._items

        stmt_str = str(stmt).lower()
        params = getattr(stmt, "compile", lambda: None)().params if hasattr(stmt, "compile") else {}
        target_user = next((v for k, v in params.items() if "user" in k and isinstance(v, str)), None)
        search_param = next((v.strip("%").lower() for v in params.values() if isinstance(v, str) and v.startswith("%")), None)

        # 1. Business ID lookup
        if "business_id" in stmt_str and "from users" in stmt_str:
            return Result(None)

        # 2. Debt Balances aggregation
        if "from debt_balances" in stmt_str:
            user_id = target_user
            rec = sum(float(d.outstanding_balance) for d in self.store.debts if d.user_id == user_id and d.debt_type == "receivable")
            pay = sum(float(d.outstanding_balance) for d in self.store.debts if d.user_id == user_id and d.debt_type == "payable")
            return Result(Row(receivables=rec, payables=pay))

        # 3. Inventory / Product counts
        if "count" in stmt_str and ("inventory_items" in stmt_str or "products" in stmt_str):
            user_id = target_user
            cnt = sum(1 for i in self.store.inventory if i["user_id"] == user_id)
            return Result(cnt)

        # 4. Cashflow trends daily group by
        if "group by transactions.transaction_date" in stmt_str:
            user_id = target_user
            daily_groups = {}
            for tx in self.store.transactions:
                if tx.user_id == user_id:
                    d = tx.transaction_date
                    daily_groups.setdefault(d, {"income": 0.0, "expense": 0.0})
                    if tx.type == "income":
                        daily_groups[d]["income"] += float(tx.amount)
                    elif tx.type == "expense":
                        daily_groups[d]["expense"] += float(tx.amount)
            rows = [Row(transaction_date=d, day_income=v["income"], day_expense=v["expense"]) for d, v in daily_groups.items()]
            return Result(rows)

        # 5. Financial Summary aggregates
        if "sum" in stmt_str and "from transactions" in stmt_str and "group by" not in stmt_str:
            user_id = target_user
            today = date.today()
            month_start = today.replace(day=1)
            user_txs = [t for t in self.store.transactions if t.user_id == user_id]

            tot_in = sum(float(t.amount) for t in user_txs if t.type == "income")
            tot_out = sum(float(t.amount) for t in user_txs if t.type == "expense")
            m_in = sum(float(t.amount) for t in user_txs if t.type == "income" and t.transaction_date >= month_start)
            m_out = sum(float(t.amount) for t in user_txs if t.type == "expense" and t.transaction_date >= month_start)
            t_in = sum(float(t.amount) for t in user_txs if t.type == "income" and t.transaction_date == today)

            return Result(Row(
                total_in=tot_in,
                total_out=tot_out,
                month_in=m_in,
                month_out=m_out,
                today_in=t_in,
                tx_count=len(user_txs),
            ))

        # 6. Count subquery for transactions list
        if "select count" in stmt_str:
            user_id = target_user
            tx_type = next((v for k, v in params.items() if "type" in k), None)
            filtered = [t for t in self.store.transactions if t.user_id == user_id]
            if tx_type:
                filtered = [t for t in filtered if t.type == tx_type]
            if search_param:
                filtered = [t for t in filtered if search_param in (t.item or "").lower() or search_param in (t.description or "").lower()]
            return Result(len(filtered))

        # 7. Paginated transactions list
        user_id = target_user
        tx_type = next((v for k, v in params.items() if "type" in k), None)
        rows = [t for t in self.store.transactions if t.user_id == user_id]

        if tx_type:
            rows = [t for t in rows if t.type == tx_type]
        if search_param:
            rows = [t for t in rows if search_param in (t.item or "").lower() or search_param in (t.description or "").lower()]

        res_rows = [
            Row(
                id=t.id,
                type=t.type,
                action=t.action,
                amount=t.amount,
                currency=t.currency,
                item=t.item,
                description=t.description,
                raw_text=t.raw_text,
                transaction_date=t.transaction_date,
                created_at=t.created_at,
                category_name="General",
            )
            for t in sorted(rows, key=lambda x: x.transaction_date, reverse=True)
        ]

        limit_val = getattr(stmt, "_limit", None)
        offset_val = getattr(stmt, "_offset", 0) or 0
        if limit_val is not None:
            res_rows = res_rows[offset_val : offset_val + limit_val]

        return Result(res_rows)


@pytest.fixture
def app(monkeypatch, store):
    """Flask application configured for portal metrics testing."""
    import app as app_module
    import app.portal.metrics as metrics_mod
    import app.portal.auth as auth_mod
    import app.admin.metrics as admin_metrics_mod

    @contextmanager
    def mock_scope():
        yield MockMetricsSession(store)

    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    monkeypatch.setattr(metrics_mod, "session_scope", mock_scope)
    monkeypatch.setattr(auth_mod, "session_scope", mock_scope)
    monkeypatch.setattr(admin_metrics_mod, "session_scope", mock_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-metrics-portal-key",
    )
    return application


@pytest.fixture
def auth_client(app):
    """Test client logged in as merchant user_a."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["merchant_logged_in"] = True
        sess["merchant_user_id"] = "018e3812-7000-7000-8000-000000000001"
        sess["merchant_phone"] = "+2348012345678"
        sess["merchant_name"] = "Mama Ngozi Provisions"
    return client


# ============================================================================
# 1. Financial Summary & KPI Calculation Tests
# ============================================================================

def test_financial_summary_calculations(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        summary = get_merchant_financial_summary(user_a)

        assert summary["total_revenue"] == 75000.00
        assert summary["total_expense"] == 15000.00
        assert summary["net_cashflow"] == 60000.00
        assert summary["today_revenue"] == 50000.00
        assert summary["total_receivables"] == 12000.00
        assert summary["total_payables"] == 8000.00
        assert summary["active_skus"] == 2
        assert summary["transaction_count"] == 3


def test_multi_tenant_user_isolation(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        user_b = "018e3812-7000-7000-8000-000000000002"

        summary_a = get_merchant_financial_summary(user_a)
        summary_b = get_merchant_financial_summary(user_b)

        # User A's revenue does not include User B's 99k sale
        assert summary_a["total_revenue"] == 75000.00
        assert summary_b["total_revenue"] == 99000.00

        # Ledger isolation
        txs_a, count_a = get_merchant_transactions(user_a)
        txs_b, count_b = get_merchant_transactions(user_b)
        assert count_a == 3
        assert count_b == 1
        assert not any("Cement" in (t["item"] or "") for t in txs_a)
        assert any("Cement" in (t["item"] or "") for t in txs_b)


def test_empty_state_summary(app, store):
    with app.app_context():
        user_empty = "018e3812-7000-7000-8000-000000000099"
        summary = get_merchant_financial_summary(user_empty)

        assert summary["total_revenue"] == 0.0
        assert summary["total_expense"] == 0.0
        assert summary["net_cashflow"] == 0.0
        assert summary["transaction_count"] == 0
        assert "₦0" in summary["total_revenue_fmt"]


# ============================================================================
# 2. Cashflow Trends Tests
# ============================================================================

def test_cashflow_trends_daily_series(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        trends = get_merchant_cashflow_trends(user_a, days=7)

        assert len(trends["labels"]) == 7
        assert len(trends["revenue"]) == 7
        assert len(trends["expense"]) == 7
        assert len(trends["net"]) == 7

        # Check total aggregated in trend equals 75,000 revenue
        assert sum(trends["revenue"]) == 75000.00
        assert sum(trends["expense"]) == 15000.00


# ============================================================================
# 3. Transactions Retrieval & Filter Tests
# ============================================================================

def test_get_merchant_transactions_type_filter(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"

        # Income only
        incomes, inc_count = get_merchant_transactions(user_a, tx_type="income")
        assert inc_count == 2
        assert all(t["type"] == "income" for t in incomes)

        # Expense only
        expenses, exp_count = get_merchant_transactions(user_a, tx_type="expense")
        assert exp_count == 1
        assert expenses[0]["type"] == "expense"


def test_get_merchant_transactions_search_filter(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"

        results, count = get_merchant_transactions(user_a, search="Rice")
        assert count == 1
        assert "Rice" in results[0]["item"]


def test_recent_transactions_limit(app, store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        recent = get_recent_merchant_transactions(user_a, limit=2)
        assert len(recent) <= 2


# ============================================================================
# 4. View & Endpoint Integration Tests
# ============================================================================

def test_authenticated_dashboard_renders_metrics(auth_client):
    res = auth_client.get("/portal/dashboard")
    assert res.status_code == 200
    assert b"Mama Ngozi Provisions" in res.data
    assert b"Cashflow Velocity" in res.data
    assert b"Recent Ledger Entries" in res.data
    assert b"50kg Bag of Rice" in res.data


def test_transactions_view_renders_ledger(auth_client):
    res = auth_client.get("/portal/transactions")
    assert res.status_code == 200
    assert b"Business Ledger" in res.data
    assert b"50kg Bag of Rice" in res.data
    assert b"Vegetable Oil 25L" in res.data
    assert b"Petrol Fuel" in res.data


def test_transactions_htmx_partial_render(auth_client):
    res = auth_client.get("/portal/transactions", headers={"HX-Request": "true"})
    assert res.status_code == 200
    assert b'id="transactions-table-container"' in res.data
    assert b"<html" not in res.data  # partial component only


def test_cashflow_chart_api(auth_client):
    res = auth_client.get("/portal/api/cashflow-chart?days=7")
    assert res.status_code == 200
    json_data = res.get_json()
    assert "labels" in json_data
    assert "revenue" in json_data
    assert "expense" in json_data
    assert len(json_data["labels"]) == 7


def test_unauthenticated_transactions_redirects(app):
    client = app.test_client()
    res = client.get("/portal/transactions")
    assert res.status_code == 302
    assert "/portal/login" in res.headers["Location"]
    assert "next=" in res.headers["Location"]
