"""WhatsApp channel adapter — WP-01 · implements ``Channel`` over the Meta Cloud API.

Lifts the transport that lived inline in ``app/web/whatsapp.py`` behind the frozen
``Channel`` seam. Senders are namespaced ``wa:<phone>``; the adapter strips the prefix
when addressing Meta (which wants the bare phone).
"""

import hashlib
import hmac
import mimetypes

import requests
from flask import current_app

from app.channels.base import Channel, InboundMessage, WHATSAPP, make_address, split_address, parse_command

GRAPH = "https://graph.facebook.com/v22.0"


def _post(url, headers, payload, label):
    """POST JSON to the Graph API → ``(ok, detail, response|None)``."""
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"Meta {label} Response: {r.status_code} - {r.text}")
        if 200 <= r.status_code < 300:
            return True, "", r
        try:
            err = r.json().get("error", {})
            return False, (f"{err.get('code', '')} {err.get('message', '')}".strip() or r.text), r
        except Exception:
            return False, r.text, r
    except requests.RequestException as e:
        print(f"Meta {label} request failed: {e}")
        return False, str(e), None


class WhatsAppChannel(Channel):
    name = WHATSAPP

    # ----- inbound -----
    def parse_inbound(self, request):
        try:
            payload = request.get_json(force=True, silent=True) or {}
        except Exception:
            payload = {}
        return self.parse_payload(payload)

    @staticmethod
    def parse_payload(payload):
        """Parse a Meta webhook payload dict → ``InboundMessage``, or ``None`` for non-message
        events (delivery/status callbacks have no ``messages`` array)."""
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            messages = value.get("messages")
            if not messages:
                return None
            msg = messages[0]
            text = msg["text"]["body"] if msg.get("type") == "text" else ""
            command, command_arg = parse_command(text)
            return InboundMessage(
                channel=WHATSAPP,
                sender=make_address(WHATSAPP, msg["from"]),
                text=text,
                message_id=msg.get("id", ""),
                command=command,
                command_arg=command_arg,
                raw=payload,
            )
        except (KeyError, IndexError, TypeError):
            return None

    # ----- auth -----
    def verify(self, request):
        secret = current_app.config.get("APP_SECRET", "")
        if not secret:
            print("[WhatsApp] META_APP_SECRET unset — skipping signature verification (DEV ONLY)")
            return True
        return self.verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256", ""), secret)

    @staticmethod
    def verify_signature(raw_body, signature_header, app_secret):
        """Validate Meta's ``X-Hub-Signature-256`` (``sha256=<hexdigest>`` of the raw body)."""
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(app_secret.encode(), raw_body or b"", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header.split("=", 1)[1])

    # ----- outbound -----
    def _creds(self):
        return current_app.config["PHONE_NUMBER_ID"], current_app.config["ACCESS_TOKEN"]

    def send_text(self, sender, text):
        """Send a text message. Returns the ``requests`` response (or ``None``) for caller logging."""
        native = split_address(sender)[1]
        phone_number_id, token = self._creds()
        url = f"{GRAPH}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": native, "type": "text", "text": {"body": text}}
        _ok, _detail, resp = _post(url, headers, payload, "Text")
        return resp

    def send_document(self, sender, file_path, filename, caption=None):
        """Two-step Cloud API flow: upload media → send a document message. Returns ``(ok, detail)``."""
        native = split_address(sender)[1]
        phone_number_id, token = self._creds()
        base = f"{GRAPH}/{phone_number_id}"
        auth = {"Authorization": f"Bearer {token}"}
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        try:
            with open(file_path, "rb") as fh:
                r = requests.post(f"{base}/media", headers=auth,
                                  data={"messaging_product": "whatsapp", "type": mime},
                                  files={"file": (filename, fh, mime)}, timeout=60)
            print(f"Meta Media-Upload Response: {r.status_code} - {r.text}")
            media_id = r.json().get("id") if 200 <= r.status_code < 300 else None
            if not media_id:
                return False, f"upload failed: {r.text}"
        except Exception as e:
            print(f"Meta media upload failed: {e}")
            return False, str(e)
        document = {"id": media_id, "filename": filename}
        if caption:
            document["caption"] = caption
        payload = {"messaging_product": "whatsapp", "to": native, "type": "document", "document": document}
        ok, detail, _ = _post(f"{base}/messages", {**auth, "Content-Type": "application/json"}, payload, "Document")
        return ok, detail
