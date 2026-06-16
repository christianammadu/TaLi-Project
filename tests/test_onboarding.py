"""WP-04 — onboarding + Path B cross-channel linking. Pure dispatch (auth monkeypatched)."""

from flask import Flask

from app.channels.base import parse_command
from app.channels import onboarding


def _app():
    app = Flask(__name__)
    app.config.update(TELEGRAM_BOT_USERNAME="TaLiBot", WHATSAPP_PUBLIC_NUMBER="2348000000000",
                      APP_BASE_URL="https://tali.example")
    return app


# --- shared command parser ---

def test_parse_command():
    assert parse_command("/start abc") == ("redeem", "abc")
    assert parse_command("/start") == ("start", None)
    assert parse_command("LINK-xyz") == ("redeem", "xyz")
    assert parse_command("/link telegram") == ("link", "telegram")
    assert parse_command("/unlink") == ("unlink", None)
    assert parse_command("/link@TaLiBot whatsapp") == ("link", "whatsapp")   # group @suffix stripped
    assert parse_command("Sold rice 5000") == (None, None)


# --- deep-links ---

def test_deeplinks():
    with _app().app_context():
        assert onboarding.telegram_deeplink("TOK") == "https://t.me/TaLiBot?start=TOK"
        assert onboarding.whatsapp_deeplink("TOK") == "https://wa.me/2348000000000?text=LINK-TOK"


# --- command dispatch ---

def test_redeem_success_links_and_opens_session(monkeypatch):
    seen = {}
    monkeypatch.setattr(onboarding.auth, "redeem_binding_token", lambda tok, ch, cid: (seen.update(redeem=(tok, ch, cid)), "user-1")[1])
    monkeypatch.setattr(onboarding.auth, "open_session", lambda sender, uid: (seen.update(session=(sender, uid)), True)[1])
    with _app().app_context():
        reply = onboarding.handle_command("telegram", "559", "redeem", "tok123")
    assert "Linked" in reply
    assert seen["redeem"] == ("tok123", "telegram", "559")
    assert seen["session"] == ("tg:559", "user-1")


def test_redeem_failure(monkeypatch):
    monkeypatch.setattr(onboarding.auth, "redeem_binding_token", lambda *a: None)
    with _app().app_context():
        assert "expired" in onboarding.handle_command("telegram", "559", "redeem", "bad")


def test_link_from_bound_user_returns_other_channel_deeplink(monkeypatch):
    monkeypatch.setattr(onboarding.auth, "resolve_channel_user", lambda ch, cid: {"id": "user-1"})
    monkeypatch.setattr(onboarding.auth, "issue_binding_token", lambda uid, target_channel=None: "TOK")
    with _app().app_context():
        reply = onboarding.handle_command("whatsapp", "234", "link", "telegram")
    assert "https://t.me/TaLiBot?start=TOK" in reply


def test_link_from_unbound_user_prompts(monkeypatch):
    monkeypatch.setattr(onboarding.auth, "resolve_channel_user", lambda ch, cid: None)
    with _app().app_context():
        assert "register" in onboarding.handle_command("telegram", "559", "link", "whatsapp")


def test_unlink(monkeypatch):
    monkeypatch.setattr(onboarding.auth, "unlink_channel", lambda ch, cid: True)
    with _app().app_context():
        assert "Unlinked" in onboarding.handle_command("whatsapp", "234", "unlink", None)


def test_help_lists_commands_and_capabilities():
    with _app().app_context():
        tg = onboarding.handle_command("telegram", "559", "help", None)
        wa = onboarding.handle_command("whatsapp", "234", "help", None)
    # Capabilities are listed…
    assert "Sold rice 5000" in tg and "Statement" in tg
    # …and the /link command points at the *other* channel for each side.
    assert "/link whatsapp" in tg and "/link telegram" in wa
    # Plain text only — no WhatsApp markdown that Telegram would render literally.
    assert "*" not in tg and "_" not in tg


def test_share_contact_existing_user(monkeypatch):
    seen = {}
    monkeypatch.setattr(onboarding.auth, "get_user_by_phone", lambda p: {"id": "user-existing"})
    monkeypatch.setattr(onboarding.auth, "link_channel", lambda uid, ch, cid: seen.update(link=(uid, ch, cid)))
    monkeypatch.setattr(onboarding.auth, "open_session", lambda sender, uid: seen.update(session=(sender, uid)))

    with _app().app_context():
        reply = onboarding.handle_command("telegram", "559", "share_contact", "2348123456789")

    assert "linked your Telegram account" in reply
    assert seen["link"] == ("user-existing", "telegram", "559")
    assert seen["session"] == ("tg:559", "user-existing")


def test_share_contact_new_user(monkeypatch):
    seen = {}
    monkeypatch.setattr(onboarding.auth, "get_user_by_phone", lambda p: None)
    monkeypatch.setattr(onboarding.auth, "register_user", lambda p: (seen.update(register=p), "user-new")[1])
    monkeypatch.setattr(onboarding.auth, "link_channel", lambda uid, ch, cid: seen.update(link=(uid, ch, cid)))
    monkeypatch.setattr(onboarding.auth, "open_session", lambda sender, uid: seen.update(session=(sender, uid)))

    with _app().app_context():
        reply = onboarding.handle_command("telegram", "559", "share_contact", "2348123456789")

    assert "Welcome to TaLi" in reply
    assert seen["register"] == "2348123456789"
    assert seen["link"] == ("user-new", "telegram", "559")
    assert seen["session"] == ("tg:559", "user-new")


def test_share_contact_missing_or_invalid_arg(monkeypatch):
    with _app().app_context():
        reply_missing = onboarding.handle_command("telegram", "559", "share_contact", None)
        reply_invalid = onboarding.handle_command("telegram", "559", "share_contact", "abc")
    assert "Failed" in reply_missing
    assert "Failed" in reply_invalid

