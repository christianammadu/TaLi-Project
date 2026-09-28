"""Unit and integration tests for WP-05: AI Fleet Observability & FinOps Spend Panel.

Tests:
1. Metric calculations and alert state transitions:
   - Green state (<70% budget ceiling consumed)
   - Yellow state (70-90% budget ceiling consumed)
   - Red state (>90% budget ceiling consumed)
2. Provider classification and routing attribution:
   - OpenAI, AI/ML API, and Featherless model classification.
3. Latency calculations and percentiles (p95 and average).
4. Direct aggregation tests with mocked database session.
5. Graceful degradation when database is unavailable.
6. Route integration and views:
   - Authenticated GET /admin/dashboard renders live platform & FinOps metrics.
   - Authenticated GET /admin/finops renders filterable log table and provider shares.
   - Filter query params on /admin/finops (model, agent, date).
   - Authenticated GET /admin/api/finops-metrics returns valid JSON telemetry.
   - Unauthenticated requests redirect to /admin/login.
"""

import pytest
from contextlib import contextmanager
from decimal import Decimal
from datetime import datetime
from app import create_app
import app.admin.metrics as metrics_mod
from app.admin.metrics import (
    determine_alert_state,
    infer_provider,
    get_spend_ceiling,
    get_finops_metrics,
    get_platform_metrics,
    get_filtered_ai_logs
)


class MockAiLogRow:
    def __init__(self, id=1, model_name="gpt-4o-mini", estimated_cost=0.0004, processing_time_ms=350, source_agent="IntakeAgent", intent="record_sale", original_message="sold 2 bags rice"):
        self.id = id
        self.model_name = model_name
        self.estimated_cost = Decimal(str(estimated_cost))
        self.processing_time_ms = processing_time_ms
        self.source_agent = source_agent
        self.parsed_intent = intent
        self.confidence_score = Decimal("0.98")
        self.original_message = original_message
        self.created_at = datetime(2026, 9, 28, 12, 0, 0)

    def __getitem__(self, idx):
        if idx == 0:
            return self.model_name
        return None


class MockQuery:
    def __init__(self, items=None, scalar_val=42):
        self._items = items or []
        self._scalar_val = scalar_val

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def count(self):
        return len(self._items)

    def scalar(self):
        return self._scalar_val

    def all(self):
        return self._items


class MockSession:
    def __init__(self, logs=None):
        self._logs = logs if logs is not None else [
            MockAiLogRow(1, "gpt-4o-mini", 0.0005, 400),
            MockAiLogRow(2, "gpt-4o", 0.0020, 950),
            MockAiLogRow(3, "meta-llama/Llama-3.3-70B-Instruct", 0.0010, 800),
            MockAiLogRow(4, "Qwen/Qwen2.5-72B-Instruct", 0.0005, 1200),
        ]

    def query(self, *args):
        # If querying AiLog for models or agents
        return MockQuery(self._logs, scalar_val=42)


@contextmanager
def mock_session_scope():
    yield MockSession()


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    """Ensure fast DB mock is used across all tests in this module."""
    monkeypatch.setattr(metrics_mod, "session_scope", mock_session_scope)


@pytest.fixture
def app(monkeypatch):
    """Create Flask application configured for admin metrics testing."""
    import app as app_module
    monkeypatch.setattr(app_module, "init_db", lambda a: None)
    monkeypatch.setattr(app_module, "init_engine", lambda a: None)
    application = create_app()
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-admin-secret-key-12345",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD="tali-admin-secret-2026",
        MODEL_ROUTER_SPEND_CEILING_USD=25.00,
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
# 1. FinOps Alert State & Provider Unit Tests
# ============================================================================

def test_determine_alert_state_green():
    color, label = determine_alert_state(spend_usd=10.0, ceiling_usd=25.0)  # 40%
    assert color == "green"
    assert "Safe" in label


def test_determine_alert_state_yellow():
    color, label = determine_alert_state(spend_usd=18.0, ceiling_usd=25.0)  # 72%
    assert color == "yellow"
    assert "Warning" in label


def test_determine_alert_state_red():
    color, label = determine_alert_state(spend_usd=23.5, ceiling_usd=25.0)  # 94%
    assert color == "red"
    assert "Critical" in label


def test_determine_alert_state_zero_ceiling():
    color, label = determine_alert_state(spend_usd=10.0, ceiling_usd=0.0)
    assert color == "green"
    assert label == "Unlimited"


def test_infer_provider_openai():
    assert infer_provider("gpt-4o-mini") == "openai"
    assert infer_provider("gpt-4o") == "openai"
    assert infer_provider("text-embedding-3-small") == "openai"


def test_infer_provider_aiml():
    assert infer_provider("meta-llama/Llama-3.3-70B-Instruct") == "aiml"
    assert infer_provider("deepseek/deepseek-chat") == "aiml"
    assert infer_provider("aiml-custom-model") == "aiml"


def test_infer_provider_featherless():
    assert infer_provider("Qwen/Qwen2.5-72B-Instruct") == "featherless"
    assert infer_provider("mistralai/Mistral-Small-24B-Instruct-2501") == "featherless"
    assert infer_provider("featherless-fast") == "featherless"


def test_get_spend_ceiling(app):
    with app.app_context():
        assert get_spend_ceiling() == 25.00
        app.config["MODEL_ROUTER_SPEND_CEILING_USD"] = 50.00
        assert get_spend_ceiling() == 50.00
        app.config["MODEL_ROUTER_SPEND_CEILING_USD"] = 0
        assert get_spend_ceiling() == 25.00  # Default fallback when 0


# ============================================================================
# 2. Metrics Aggregation Structure Tests
# ============================================================================

def test_get_finops_metrics_calculation(app):
    with app.app_context():
        metrics = get_finops_metrics()
        assert metrics["total_spend_usd"] == pytest.approx(0.004, abs=1e-4)
        assert metrics["ceiling_usd"] == 25.00
        assert metrics["total_ai_calls"] == 4
        assert metrics["p95_latency_ms"] == 1200
        assert metrics["avg_latency_ms"] == 837
        assert metrics["provider_share"]["openai"] == 50.0
        assert metrics["provider_share"]["aiml"] == 25.0
        assert metrics["provider_share"]["featherless"] == 25.0
        assert metrics["alert_color"] == "green"


def test_get_platform_metrics_structure(app):
    with app.app_context():
        platform = get_platform_metrics()
        assert platform["total_merchants"] == 42
        assert platform["daily_active_merchants"] == 42
        assert platform["platform_gmv_ngn"] == 42.0
        assert platform["total_transactions"] == 42
        assert platform["pending_compliance_count"] == 42
        assert "finops" in platform


def test_get_filtered_ai_logs_structure(app):
    with app.app_context():
        data = get_filtered_ai_logs(model="all", limit=10)
        assert len(data["logs"]) == 4
        assert data["total_count"] == 4
        first = data["logs"][0]
        assert first["model_name"] == "gpt-4o-mini"
        assert first["provider"] == "openai"


def test_graceful_degradation_on_db_exception(app, monkeypatch):
    @contextmanager
    def failing_session_scope():
        raise RuntimeError("Simulated DB connection failure")
        yield

    monkeypatch.setattr(metrics_mod, "session_scope", failing_session_scope)

    with app.app_context():
        finops = get_finops_metrics()
        assert finops["total_spend_usd"] >= 0.0
        assert "provider_share" in finops
        assert finops["p95_latency_ms"] > 0

        platform = get_platform_metrics()
        assert platform["total_merchants"] == 42
        assert platform["platform_gmv_ngn"] == 14250000.00


# ============================================================================
# 3. HTTP Endpoints & View Tests (Impeccable Mode: Operate)
# ============================================================================

def test_unauthenticated_finops_redirects(client):
    res = client.get("/admin/finops")
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_unauthenticated_api_redirects(client):
    res = client.get("/admin/api/finops-metrics")
    assert res.status_code == 302
    assert "/admin/login" in res.headers["Location"]


def test_authenticated_dashboard_renders_metrics(auth_client):
    res = auth_client.get("/admin/dashboard")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Platform Fleet Overview" in html
    assert "Platform GMV" in html
    assert "AI Spend / Budget" in html
    assert "fleetSpendChart" in html
    assert "OpenAI (Primary)" in html


def test_authenticated_finops_renders_view(auth_client):
    res = auth_client.get("/admin/finops")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "AI Fleet &amp; FinOps Spend Panel" in html or "AI Fleet & FinOps Spend Panel" in html
    assert "Ceiling Spend" in html
    assert "Inference Calls" in html
    assert "p95 / Avg Latency" in html
    assert "finopsChart" in html
    assert "Inference Audit Log" in html
    assert "Model Name" in html


def test_authenticated_finops_filter_params(auth_client):
    res = auth_client.get("/admin/finops?model=gpt-4o-mini&agent=IntakeAgent&page=1")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Inference Audit Log" in html


def test_authenticated_api_finops_metrics_json(auth_client):
    res = auth_client.get("/admin/api/finops-metrics")
    assert res.status_code == 200
    assert res.is_json
    data = res.get_json()
    assert "total_spend_usd" in data
    assert "ceiling_usd" in data
    assert "provider_share" in data
    assert "openai" in data["provider_share"]
    assert "p95_latency_ms" in data
