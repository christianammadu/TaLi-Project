"""Unit and integration tests for WP-09: Self-Service Catalog & Inventory Manager.

Tests:
1. Catalog retrieval with stock status flags (IN_STOCK, LOW_STOCK, OUT_OF_STOCK).
2. Multi-tenant catalog isolation (Merchant A vs Merchant B).
3. Search filtering and low-stock warning toggle.
4. Adding new catalog products (validation, duplicate prevention).
5. Stock adjustments (restock, loss/damage, count correction).
6. Summary statistics (SKU counts by stock status).
7. Web endpoints & HTMX partial rendering.
8. Route access control.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from app import create_app
from app.portal.auth import clear_all_portal_lockouts
from app.portal.inventory import (
    add_merchant_inventory_item,
    adjust_merchant_stock,
    get_inventory_summary_stats,
    get_merchant_inventory_items,
)


class MockProd:
    def __init__(self, id, user_id, name, quantity, unit="pcs", min_stock=5.0):
        self.id = id
        self.user_id = user_id
        self.name = name
        self.quantity = Decimal(str(quantity))
        self.unit = unit
        self.min_stock = Decimal(str(min_stock))
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)


class MockInventoryStore:
    def __init__(self):
        user_a = "018e3812-7000-7000-8000-000000000001"
        user_b = "018e3812-7000-7000-8000-000000000002"

        self.products = [
            MockProd("p-1", user_a, "50kg Bag of Rice", 20.0, "bags"),
            MockProd("p-2", user_a, "Vegetable Oil 25L", 3.0, "kegs"),      # Low stock (<= 5)
            MockProd("p-3", user_a, "Indomie Noodles Super Pack", 0.0, "cartons"), # Out of stock
            MockProd("p-4", user_b, "Dangote Cement 50kg", 100.0, "bags"), # User B
        ]
        self.movements = []


class MockInventorySession:
    def __init__(self, store: MockInventoryStore):
        self.store = store

    def execute(self, stmt):
        class Result:
            def __init__(self, items):
                self._items = items if isinstance(items, list) else [items]

            def scalars(self):
                return self

            def scalar(self):
                return self._items[0] if self._items else None

            def first(self):
                return self._items[0] if self._items else None

            def all(self):
                return self._items

        stmt_str = str(stmt).lower()
        params = getattr(stmt, "compile", lambda: None)().params if hasattr(stmt, "compile") else {}
        target_user = next((v for k, v in params.items() if "user" in k and isinstance(v, str)), None)
        target_id = next((v for k, v in params.items() if "user" not in k and "id" in k and isinstance(v, str)), None)
        name_param = next((v.lower() for k, v in params.items() if ("name" in k or "lower" in k) and isinstance(v, str) and not v.startswith("%")), None)
        search_param = next((v.strip("%").lower() for v in params.values() if isinstance(v, str) and v.startswith("%")), None)

        # 1. Product select
        if "from products" in stmt_str:
            rows = [p for p in self.store.products if p.user_id == target_user]
            if target_id:
                rows = [p for p in rows if str(p.id) == target_id]
            if name_param:
                rows = [p for p in rows if p.name.lower() == name_param]
            if search_param:
                rows = [p for p in rows if search_param in p.name.lower()]
            return Result(rows)

        # 2. Inventory items select (fallback table)
        if "from inventory_items" in stmt_str:
            rows = [p for p in self.store.products if p.user_id == target_user and str(p.id) == target_id] if target_id else []
            return Result(rows)

        return Result([])

    def add(self, obj):
        if hasattr(obj, "name") and hasattr(obj, "quantity"):
            self.store.products.append(obj)
        elif hasattr(obj, "movement_type"):
            self.store.movements.append(obj)

    def commit(self):
        pass


@pytest.fixture
def inv_store():
    return MockInventoryStore()


@pytest.fixture
def app(monkeypatch, inv_store):
    """Flask app configured for inventory testing."""
    import app as app_module
    import app.portal.inventory as inv_mod
    import app.portal.auth as auth_mod
    import app.portal.metrics as metrics_mod
    import app.admin.metrics as admin_metrics_mod

    @contextmanager
    def mock_inv_scope():
        yield MockInventorySession(inv_store)

    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    monkeypatch.setattr(inv_mod, "session_scope", mock_inv_scope)
    monkeypatch.setattr(auth_mod, "session_scope", mock_inv_scope)
    monkeypatch.setattr(metrics_mod, "session_scope", mock_inv_scope)
    monkeypatch.setattr(admin_metrics_mod, "session_scope", mock_inv_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-inventory-portal-key",
    )
    return application


@pytest.fixture
def auth_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["merchant_logged_in"] = True
        sess["merchant_user_id"] = "018e3812-7000-7000-8000-000000000001"
        sess["merchant_phone"] = "+2348012345678"
        sess["merchant_name"] = "Mama Ngozi Provisions"
    return client


# ============================================================================
# 1. Catalog & Stock Query Tests
# ============================================================================

def test_get_merchant_inventory_items_status(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        items = get_merchant_inventory_items(user_a)

        assert len(items) == 3
        # Check stock statuses
        rice = next(i for i in items if "Rice" in i["name"])
        oil = next(i for i in items if "Oil" in i["name"])
        noodles = next(i for i in items if "Noodles" in i["name"])

        assert rice["status"] == "IN_STOCK"
        assert rice["is_low_stock"] is False
        assert oil["status"] == "LOW_STOCK"
        assert oil["is_low_stock"] is True
        assert noodles["status"] == "OUT_OF_STOCK"
        assert noodles["is_low_stock"] is True


def test_inventory_multi_tenant_isolation(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        user_b = "018e3812-7000-7000-8000-000000000002"

        items_a = get_merchant_inventory_items(user_a)
        items_b = get_merchant_inventory_items(user_b)

        assert len(items_a) == 3
        assert len(items_b) == 1
        assert not any("Cement" in i["name"] for i in items_a)
        assert any("Cement" in i["name"] for i in items_b)


def test_inventory_search_and_low_stock_filters(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"

        # Search filter
        search_res = get_merchant_inventory_items(user_a, search="Oil")
        assert len(search_res) == 1
        assert "Oil" in search_res[0]["name"]

        # Low stock filter
        low_res = get_merchant_inventory_items(user_a, low_stock_only=True)
        assert len(low_res) == 2
        assert all(i["is_low_stock"] for i in low_res)


def test_inventory_summary_stats(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        stats = get_inventory_summary_stats(user_a)

        assert stats["total_skus"] == 3
        assert stats["in_stock"] == 1
        assert stats["low_stock"] == 1
        assert stats["out_of_stock"] == 1


# ============================================================================
# 2. Add Product & Stock Adjustments Tests
# ============================================================================

def test_add_inventory_item_success(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        success, msg, item = add_merchant_inventory_item(
            user_id=user_a,
            name="Sugar 50kg",
            unit="bags",
            initial_quantity=15.0,
            min_stock=5.0,
        )

        assert success is True
        assert item["name"] == "Sugar 50kg"
        assert item["quantity"] == 15.0


def test_add_inventory_item_validation(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"

        # Empty name
        success, msg, _ = add_merchant_inventory_item(user_a, name="   ")
        assert success is False
        assert "required" in msg.lower()

        # Duplicate product name
        success_dup, msg_dup, _ = add_merchant_inventory_item(user_a, name="50kg Bag of Rice")
        assert success_dup is False
        assert "already exists" in msg_dup.lower()


def test_adjust_stock_restock(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"
        # Rice starts at 20.0, restock +10
        success, msg, new_qty = adjust_merchant_stock(
            user_id=user_a,
            item_id="p-1",
            adjustment_type="restock",
            quantity=10.0,
            notes="New delivery",
        )

        assert success is True
        assert new_qty == 30.0


def test_adjust_stock_loss_and_correction(app, inv_store):
    with app.app_context():
        user_a = "018e3812-7000-7000-8000-000000000001"

        # Damage/Loss: Rice starts at 20, reduce by 5
        success, msg, new_qty = adjust_merchant_stock(
            user_id=user_a,
            item_id="p-1",
            adjustment_type="damage",
            quantity=5.0,
        )
        assert success is True
        assert new_qty == 15.0

        # Exact correction (set)
        success_set, msg_set, set_qty = adjust_merchant_stock(
            user_id=user_a,
            item_id="p-1",
            adjustment_type="set",
            quantity=18.0,
        )
        assert success_set is True
        assert set_qty == 18.0


# ============================================================================
# 3. View & Endpoint Integration Tests
# ============================================================================

def test_authenticated_inventory_renders(auth_client):
    res = auth_client.get("/portal/inventory")
    assert res.status_code == 200
    assert b"Catalog &amp; Inventory" in res.data or b"Catalog & Inventory" in res.data
    assert b"50kg Bag of Rice" in res.data
    assert b"Vegetable Oil 25L" in res.data
    assert b"Low Stock" in res.data


def test_inventory_htmx_partial_render(auth_client):
    res = auth_client.get("/portal/inventory", headers={"HX-Request": "true"})
    assert res.status_code == 200
    assert b'id="inventory-table-container"' in res.data
    assert b"<html" not in res.data


def test_inventory_add_route(auth_client):
    res = auth_client.post(
        "/portal/inventory/add",
        data={
            "name": "Milo 500g",
            "unit": "tins",
            "quantity": "25",
            "min_stock": "5",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Milo 500g" in res.data


def test_inventory_adjust_route(auth_client):
    res = auth_client.post(
        "/portal/inventory/p-1/adjust",
        data={
            "adjustment_type": "restock",
            "quantity": "5",
            "notes": "Added 5 bags",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Stock updated" in res.data


def test_unauthenticated_inventory_redirects(app):
    client = app.test_client()
    res = client.get("/portal/inventory")
    assert res.status_code == 302
    assert "/portal/login" in res.headers["Location"]
