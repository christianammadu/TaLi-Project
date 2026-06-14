"""WP-03 — Telegram channel adapter. No network: HTTP is monkeypatched."""

from flask import Flask

from app.channels.base import TELEGRAM
from app.channels.telegram import TelegramChannel
import app.channels.telegram as tg_mod


def _app():
    app = Flask(__name__)
    app.config.update(TELEGRAM_BOT_TOKEN="123:ABC", TELEGRAM_API_BASE="https://api.telegram.org")
    return app


_TEXT = {"update_id": 1, "message": {"message_id": 42, "chat": {"id": 559912345, "type": "private"},
                                     "text": "Sold rice 5000"}}
_START = {"message": {"message_id": 1, "chat": {"id": 559, "type": "private"}, "text": "/start abc123tok"}}
_LINK = {"message": {"message_id": 2, "chat": {"id": 559, "type": "private"}, "text": "/link whatsapp"}}
_GROUP = {"message": {"message_id": 3, "chat": {"id": -100, "type": "group"}, "text": "hi"}}
_EDIT = {"edited_message": {"message_id": 4, "chat": {"id": 5, "type": "private"}, "text": "x"}}


def test_parse_update_text():
    m = TelegramChannel.parse_update(_TEXT)
    assert m.channel == TELEGRAM
    assert m.sender == "tg:559912345"
    assert m.native_id == "559912345"
    assert m.text == "Sold rice 5000"
    assert m.message_id == "42"
    assert m.command is None


def test_parse_update_commands():
    s = TelegramChannel.parse_update(_START)
    assert (s.command, s.command_arg) == ("redeem", "abc123tok")
    l = TelegramChannel.parse_update(_LINK)
    assert (l.command, l.command_arg) == ("link", "whatsapp")


def test_parse_update_ignores_groups_edits_and_empty():
    assert TelegramChannel.parse_update(_GROUP) is None      # v1: private chats only
    assert TelegramChannel.parse_update(_EDIT) is None        # no "message"
    assert TelegramChannel.parse_update({}) is None


def test_verify_secret():
    assert TelegramChannel.verify_secret("s3cret", "s3cret") is True
    assert TelegramChannel.verify_secret("wrong", "s3cret") is False
    assert TelegramChannel.verify_secret("", "s3cret") is False


def test_send_text_addresses_chat_and_hits_bot_api(monkeypatch):
    captured = {}

    class _R:
        status_code = 200
        text = '{"ok":true}'
    def fake_post(url, json=None, timeout=None, **kw):
        captured.update(url=url, json=json)
        return _R()

    monkeypatch.setattr(tg_mod.requests, "post", fake_post)
    with _app().app_context():
        TelegramChannel().send_text("tg:559912345", "hi there")

    assert captured["json"] == {"chat_id": "559912345", "text": "hi there"}
    assert captured["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
