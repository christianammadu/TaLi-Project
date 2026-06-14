"""WP-05 — channel registry routes replies/documents by the sender's namespace."""

from app.channels import registry


def test_channel_name_resolves_by_prefix():
    assert registry.channel_name("tg:559912345") == "telegram"
    assert registry.channel_name("wa:2348012345678") == "whatsapp"
    assert registry.channel_name("2348012345678") == "whatsapp"   # bare/legacy → WhatsApp


class _Fake:
    def __init__(self, name):
        self.name = name
    def send_text(self, sender, text):
        return ("text", self.name, sender, text)
    def send_document(self, sender, file_path, filename, caption=None):
        return (True, self.name)   # (ok, detail) contract; detail carries the channel for the assert


def test_send_text_routes_to_originating_channel(monkeypatch):
    monkeypatch.setattr(registry, "get_channel", lambda name: _Fake(name))
    monkeypatch.setattr(registry, "_log_outgoing", lambda s, t: None)
    assert registry.send_text("tg:559", "hi") == ("text", "telegram", "tg:559", "hi")
    assert registry.send_text("2348012345678", "yo") == ("text", "whatsapp", "2348012345678", "yo")


def test_send_document_routes_to_originating_channel(monkeypatch):
    monkeypatch.setattr(registry, "get_channel", lambda name: _Fake(name))
    monkeypatch.setattr(registry, "_log_outgoing", lambda s, t: None)
    assert registry.send_document("tg:559", "/tmp/x.pdf", "June.pdf")[1] == "telegram"
    assert registry.send_document("wa:234", "/tmp/x.xlsx", "June.xlsx")[1] == "whatsapp"
