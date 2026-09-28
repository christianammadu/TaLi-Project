"""Unit and integration tests for WP-06: Compliance Review Queue Web Hub & Room Resumption.

Tests:
1. Risk classification and badge mapping:
   - High Expense (>= ₦100,000)
   - High Debt (>= ₦50,000)
   - Low Confidence (< 75%)
2. Compliance queue operations:
   - Fetching pending reviews with risk filtering.
   - Resolving review with 'approve' action (resumes room, notifies merchant).
   - Resolving review with 'reject' action (vetoes transaction, notifies merchant).
3. Orchestrator human-in-the-loop room events:
   - post_human_decision delivery under @tali-human mention targeting @tali-ledger and @tali-cfo.
4. HTTP route access control and HTMX interactions:
   - Unauthenticated requests redirect to /admin/login.
   - Authenticated GET /admin/compliance renders review table with risk badges.
   - Filter query parameters (?filter=high_expense, ?filter=high_debt).
   - HTMX POST /admin/compliance/<id>/action with 'approve' returns partial row with 'Approved by Admin'.
   - HTMX POST /admin/compliance/<id>/action with 'reject' returns partial row with 'Rejected / Vetoed'.
"""

import pytest
from app import create_app
from app.agents.orchestrator import (
    OrchestrationEngine,
    OrchestratorClient,
    post_human_decision
)
from app.admin.compliance import (
    classify_risk,
    get_pending_reviews,
    get_review_by_id,
    resolve_review,
    get_compliance_stats,
    _IN_MEMORY_REVIEWS
)


@pytest.fixture(autouse=True)
def reset_compliance_state():
    """Ensure in-memory reviews are reset to PENDING before each test."""
    for item in _IN_MEMORY_REVIEWS.values():
        item["status"] = "PENDING"
        item.pop("reviewed_by", None)
        item.pop("reviewed_at", None)
        item.pop("decision_reason", None)
    yield


@pytest.fixture
def app(monkeypatch):
    """Create Flask application configured for compliance testing."""
    import app as app_module
    import app.admin.metrics as metrics_mod
    import app.admin.compliance as compliance_mod
    from contextlib import contextmanager

    @contextmanager
    def fast_offline_scope():
        raise RuntimeError("offline DB test")
        yield

    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    monkeypatch.setattr(metrics_mod, "session_scope", fast_offline_scope)
    monkeypatch.setattr(compliance_mod, "session_scope", fast_offline_scope)

    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-admin-secret-key-12345",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="tali-admin-secret-2026",
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["admin_user"] = "admin"
    return client


# ============================================================================
# 1. Risk Classification Unit Tests
# ============================================================================

def test_classify_risk_high_expense():
    risk_type, badge = classify_risk(amount=150_000.0, intent="record_expense", confidence=0.98)
    assert risk_type == "high_expense"
    assert badge["color"] == "red"
    assert "High Expense" in badge["label"]


def test_classify_risk_high_debt():
    risk_type, badge = classify_risk(amount=75_000.0, intent="record_debt", confidence=0.95)
    assert risk_type == "high_debt"
    assert badge["color"] == "amber"
    assert "High Debt" in badge["label"]


def test_classify_risk_low_confidence():
    risk_type, badge = classify_risk(amount=5_000.0, intent="record_expense", confidence=0.62)
    assert risk_type == "low_confidence"
    assert badge["color"] == "purple"
    assert "Low Confidence" in badge["label"]


# ============================================================================
# 2. Compliance Queue & Resolution Unit Tests
# ============================================================================

def test_get_pending_reviews_and_filtering():
    all_reviews = get_pending_reviews(risk_filter="all")
    assert len(all_reviews) >= 3

    expense_reviews = get_pending_reviews(risk_filter="high_expense")
    assert len(expense_reviews) >= 1
    assert all(r["risk_type"] == "high_expense" for r in expense_reviews)

    debt_reviews = get_pending_reviews(risk_filter="high_debt")
    assert len(debt_reviews) >= 1
    assert all(r["risk_type"] == "high_debt" for r in debt_reviews)


def test_resolve_review_approval(monkeypatch):
    notifications = []
    monkeypatch.setattr("app.admin.compliance.notify_merchant", lambda rec, msg, channel='whatsapp': notifications.append((rec, msg)))

    res = resolve_review("rev-101", action="approve", reviewer="Officer Sarah")
    assert res["success"] is True
    assert res["status"] == "APPROVED"
    assert res["reviewed_by"] == "Officer Sarah"
    assert len(notifications) == 1
    assert "approved" in notifications[0][1].lower()

    # Check updated item in queue
    item = get_review_by_id("rev-101")
    assert item["status"] == "APPROVED"


def test_resolve_review_rejection_veto(monkeypatch):
    notifications = []
    monkeypatch.setattr("app.admin.compliance.notify_merchant", lambda rec, msg, channel='whatsapp': notifications.append((rec, msg)))

    res = resolve_review("rev-102", action="reject", reviewer="Officer John", reason="Unverified counterparty")
    assert res["success"] is True
    assert res["status"] == "REJECTED"
    assert res["reason"] == "Unverified counterparty"
    assert len(notifications) == 1
    assert "declined" in notifications[0][1].lower() or "rejected" in notifications[0][1].lower()
    assert "Unverified counterparty" in notifications[0][1]


def test_get_compliance_stats():
    stats = get_compliance_stats()
    assert "total_pending" in stats
    assert "high_expense_count" in stats
    assert "high_debt_count" in stats
    assert "low_confidence_count" in stats
    assert stats["total_pending"] >= 3


# ============================================================================
# 3. Orchestrator Human Decision Resumption
# ============================================================================

def test_post_human_decision_resumes_room():
    engine = OrchestrationEngine()
    client = OrchestratorClient(engine)
    room_id = "test-compliance-room-99"

    delivered_messages = []
    client.on_message("@tali-ledger", lambda msg: delivered_messages.append(msg))

    msg_id = post_human_decision(
        room_id=room_id,
        review_id="rev-test-1",
        decision="approved",
        reason="Verified by compliance team",
        orchestrator=client
    )

    assert msg_id is not None
    assert len(delivered_messages) == 1
    delivered = delivered_messages[0]
    assert delivered["sender"] == "@tali-human"
    assert "@tali-ledger" in delivered["mentions"]
    assert delivered["body"]["type"] == "human_decision"
    assert delivered["body"]["decision"] == "approved"
    assert delivered["body"]["review_id"] == "rev-test-1"


# ============================================================================
# 4. HTTP Routes & HTMX Partial Swaps
# ============================================================================

def test_unauthenticated_compliance_redirects(client):
    res = client.get("/admin/compliance")
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_unauthenticated_action_redirects(client):
    res = client.post("/admin/compliance/rev-101/action", data={"action": "approve"})
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_authenticated_compliance_renders_queue(auth_client):
    res = auth_client.get("/admin/compliance")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Compliance Review Queue" in html
    assert "Pending Holds" in html
    assert "High Expense" in html
    assert "High Debt" in html
    assert "#rev-101" in html
    assert "₦1,250,000.00" in html


def test_authenticated_compliance_filter_view(auth_client):
    res = auth_client.get("/admin/compliance?filter=high_expense")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "high_expense" in html.lower()
    assert "#rev-101" in html


def test_htmx_approve_action_swaps_partial_row(auth_client, monkeypatch):
    monkeypatch.setattr("app.admin.compliance.notify_merchant", lambda r, m, channel='whatsapp': True)

    res = auth_client.post(
        "/admin/compliance/rev-101/action",
        data={"action": "approve"},
        headers={"HX-Request": "true"}
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "✓ Approved by Admin" in html
    assert "Room Resumed" in html
    assert "review-row-rev-101" in html


def test_htmx_reject_action_swaps_partial_row(auth_client, monkeypatch):
    monkeypatch.setattr("app.admin.compliance.notify_merchant", lambda r, m, channel='whatsapp': True)

    res = auth_client.post(
        "/admin/compliance/rev-102/action",
        data={"action": "reject", "reason": "Suspected duplicate"},
        headers={"HX-Request": "true"}
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "✕ Rejected / Vetoed" in html
    assert "Transaction Aborted" in html
    assert "review-row-rev-102" in html


def test_json_api_compliance_action(auth_client, monkeypatch):
    monkeypatch.setattr("app.admin.compliance.notify_merchant", lambda r, m, channel='whatsapp': True)

    res = auth_client.post(
        "/admin/compliance/rev-103/action",
        json={"action": "approve"},
        headers={"Content-Type": "application/json"}
    )
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert data["success"] is True
    assert data["status"] == "APPROVED"
