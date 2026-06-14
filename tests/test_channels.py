"""WP-01 — Channel contract + WhatsApp adapter.

No network: the Meta HTTP call is monkeypatched, signature verify uses a computed HMAC,
and inbound parsing runs on sample webhook payloads. Proves the frozen G-CHANNEL-CONTRACT
seam (parse_inbound · verify · send_text) round-trips.
"""

import hashlib
import hmac

from flask import Flask

from app.channels.base import make_address, split_address, WHATSAPP, TELEGRAM, InboundMessage
from app.channels.whatsapp import WhatsAppChannel
import app.channels.whatsapp as wa_mod


# --- namespacing ---

def test_make_and_split_address_round_trip():
    assert make_address(WHATSAPP, "2348012345678") == "wa:2348012345678"
    assert make_address(TELEGRAM, "559912345") == "tg:559912345"
    assert split_address("wa:2348012345678") == (WHATSAPP, "2348012345678")
    assert split_address("tg:559912345") == (TELEGRAM, "559912345")


def test_split_tolerates_bare_legacy_id():
    # legacy WhatsApp rows stored the raw phone with no prefix
    assert split_address("2348012345678") == (None, "2348012345678")


# --- inbound parsing ---

_WA_TEXT = {"object": "whatsapp_business_account", "entry": [{"id": "X", "changes": [{"value": {
    "messaging_product": "whatsapp",
    "messages": [{"from": "2348012345678", "id": "wamid.ABC", "type": "text",
                  "text": {"body": "Sold rice 5000"}}],
}, "field": "messages"}]}]}

_WA_STATUS = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.ABC", "status": "delivered"}]},
                                       "field": "messages"}]}]}


def test_parse_payload_text_message():
    msg = WhatsAppChannel.parse_payload(_WA_TEXT)
    assert isinstance(msg, InboundMessage)
    assert msg.channel == WHATSAPP
    assert msg.sender == "wa:2348012345678"
    assert msg.native_id == "2348012345678"
    assert msg.text == "Sold rice 5000"
    assert msg.message_id == "wamid.ABC"


def test_parse_payload_status_callback_is_none():
    assert WhatsAppChannel.parse_payload(_WA_STATUS) is None
    assert WhatsAppChannel.parse_payload({}) is None


# --- signature verify ---

def test_verify_signature():
    body, secret = b'{"entry":[]}', "s3cret"
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert WhatsAppChannel.verify_signature(body, good, secret) is True
    assert WhatsAppChannel.verify_signature(body, "sha256=deadbeef", secret) is False
    assert WhatsAppChannel.verify_signature(body, "", secret) is False          # missing header


# --- outbound (mocked) ---

class _FakeResp:
    status_code = 200
    text = "{}"
    def json(self):
        return {"messages": [{"id": "wamid.OUT"}]}


def test_send_text_strips_namespace_and_posts(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        captured.update(url=url, json=json, headers=headers)
        return _FakeResp()

    monkeypatch.setattr(wa_mod.requests, "post", fake_post)
    app = Flask(__name__)
    app.config.update(PHONE_NUMBER_ID="PNID", ACCESS_TOKEN="TOK")
    with app.app_context():
        resp = WhatsAppChannel().send_text("wa:2348012345678", "hello")

    assert captured["json"]["to"] == "2348012345678"          # prefix stripped for Meta
    assert captured["json"]["text"]["body"] == "hello"
    assert "PNID/messages" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer TOK"
    assert resp.json()["messages"][0]["id"] == "wamid.OUT"
