"""WP-04 (web slice) — verify-otp issues a binding token + renders the dual-channel deep-links.

Uses the Flask test client with auth monkeypatched (no DB). create_app prints a DB-connect
warning at boot (no MySQL here) but still returns the app; the route under test hits no DB.
"""

import app.web.web_routes as wr
import app.auth as auth
from app import create_app


def test_verify_otp_renders_both_deeplinks(monkeypatch):
    monkeypatch.setattr(wr, "validate_registration_otp", lambda phone, code: True)
    monkeypatch.setattr(wr, "register_user", lambda phone: "user-1")
    monkeypatch.setattr(auth, "issue_binding_token", lambda user_id: "TOK")

    app = create_app()
    app.config.update(TELEGRAM_BOT_USERNAME="TaLiBot", WHATSAPP_PUBLIC_NUMBER="2348000000000")
    client = app.test_client()

    r = client.post("/verify-otp", data={"phone": "2348012345678", "code": "123456"})
    body = r.data.decode()
    assert r.status_code == 200
    assert "https://t.me/TaLiBot?start=TOK" in body
    assert "https://wa.me/2348000000000?text=LINK-TOK" in body
    assert "Continue on Telegram" in body and "Continue on WhatsApp" in body
