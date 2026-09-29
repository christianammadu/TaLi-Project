"""Unit tests for CSRF token generation and enforcement."""

import pytest
from flask import Flask
from app.services.csrf import generate_csrf_token, validate_csrf_token, init_csrf


@pytest.fixture
def csrf_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-csrf-secret-key",
        TESTING=True,
        CSRF_ENABLED=True,  # Explicitly enable for this test suite
    )
    init_csrf(app)

    @app.route("/test-view", methods=["GET", "POST"])
    def test_view():
        return "OK"

    @app.route("/webhook/test", methods=["POST"])
    def webhook_test():
        return "WEBHOOK OK"

    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_csrf_token_generation_and_validation(csrf_app):
    with csrf_app.test_request_context():
        token1 = generate_csrf_token()
        assert len(token1) == 64
        # Same session returns same token
        token2 = generate_csrf_token()
        assert token1 == token2

        assert validate_csrf_token(token1) is True
        assert validate_csrf_token("invalid_token") is False
        assert validate_csrf_token(None) is False


def test_csrf_get_requests_are_allowed(csrf_client):
    res = csrf_client.get("/test-view")
    assert res.status_code == 200
    assert res.data.decode("utf-8") == "OK"


def test_csrf_post_without_token_is_blocked(csrf_client):
    res = csrf_client.post("/test-view")
    assert res.status_code == 403


def test_csrf_post_with_invalid_token_is_blocked(csrf_client):
    res = csrf_client.post("/test-view", data={"csrf_token": "wrong-token"})
    assert res.status_code == 403


def test_csrf_post_with_valid_form_token(csrf_client):
    with csrf_client.session_transaction() as sess:
        sess["_csrf_token"] = "valid-token-12345"

    res = csrf_client.post("/test-view", data={"csrf_token": "valid-token-12345"})
    assert res.status_code == 200
    assert res.data.decode("utf-8") == "OK"


def test_csrf_post_with_valid_header_token(csrf_client):
    with csrf_client.session_transaction() as sess:
        sess["_csrf_token"] = "header-token-67890"

    res = csrf_client.post("/test-view", headers={"X-CSRFToken": "header-token-67890"})
    assert res.status_code == 200
    assert res.data.decode("utf-8") == "OK"


def test_csrf_webhook_exempt_from_token(csrf_client):
    res = csrf_client.post("/webhook/test", json={"test": "payload"})
    assert res.status_code == 200
    assert res.data.decode("utf-8") == "WEBHOOK OK"
