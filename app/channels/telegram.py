"""Telegram channel adapter — WP-03 · implements ``Channel`` over the Telegram Bot API.

Free, multi-user, stable webhook (unlike the unpaid WhatsApp API). Senders are namespaced
``tg:<chat_id>``; the adapter strips the prefix when addressing the Bot API. Inbound
``/start <token>`` / ``/link <chan>`` commands are surfaced via ``InboundMessage.command``
for the onboarding + Path B flow (WP-04).
"""

import mimetypes

import requests
from flask import current_app

from app.channels.base import Channel, InboundMessage, TELEGRAM, make_address, split_address, parse_command


class TelegramChannel(Channel):
    name = TELEGRAM

    # ----- helpers -----
    def _api(self, method):
        base = current_app.config.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
        token = current_app.config["TELEGRAM_BOT_TOKEN"]
        return f"{base}/bot{token}/{method}"

    # ----- inbound -----
    def parse_inbound(self, request):
        try:
            update = request.get_json(force=True, silent=True) or {}
        except Exception:
            update = {}
        return self.parse_update(update)

    @staticmethod
    def parse_update(update):
        """Parse a Telegram ``Update`` dict → ``InboundMessage``, or ``None`` for updates with no
        usable private-chat text message (edited messages, channel posts, callbacks…)."""
        msg = update.get("message") if isinstance(update, dict) else None
        if not msg:
            return None
        chat = msg.get("chat") or {}
        if chat.get("type") not in (None, "private"):   # v1: 1:1 chats only
            return None
        chat_id = chat.get("id")
        if chat_id is None:
            return None
        text = msg.get("text", "") or ""
        contact = msg.get("contact")
        sender_id = msg.get("from", {}).get("id") if isinstance(msg.get("from"), dict) else None
        if contact and contact.get("user_id") is not None and contact.get("user_id") == sender_id:
            command = "share_contact"
            command_arg = contact.get("phone_number")
        else:
            command, command_arg = parse_command(text)

        return InboundMessage(
            channel=TELEGRAM,
            sender=make_address(TELEGRAM, chat_id),
            text=text,
            message_id=str(msg.get("message_id", "")),
            command=command,
            command_arg=command_arg,
            raw=update,
        )

    # ----- auth -----
    def verify(self, request):
        secret = current_app.config.get("TELEGRAM_WEBHOOK_SECRET", "")
        if not secret:
            # Fail closed in production; only the explicit dev flag accepts unsigned updates.
            if current_app.config.get("OTP_DEV_BYPASS"):
                print("[Telegram] TELEGRAM_WEBHOOK_SECRET unset — accepting (OTP_DEV_BYPASS dev mode)")
                return True
            print("[Telegram] TELEGRAM_WEBHOOK_SECRET unset — rejecting webhook (set it, or OTP_DEV_BYPASS for dev)")
            return False
        return self.verify_secret(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), secret)

    @staticmethod
    def verify_secret(header_value, secret):
        """Telegram echoes our configured secret in ``X-Telegram-Bot-Api-Secret-Token``."""
        import hmac
        return bool(header_value) and hmac.compare_digest(header_value, secret)

    # ----- outbound -----
    def send_text(self, sender, text, reply_markup=None):
        chat_id = split_address(sender)[1]
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = requests.post(self._api("sendMessage"), json=payload, timeout=15)
            print(f"Telegram sendMessage: {r.status_code} - {r.text[:200]}")
            return r
        except requests.RequestException as e:
            print(f"Telegram sendMessage failed: {e}")
            return None

    def send_document(self, sender, file_path, filename, caption=None):
        chat_id = split_address(sender)[1]
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        try:
            with open(file_path, "rb") as fh:
                r = requests.post(self._api("sendDocument"), data=data,
                                  files={"document": (filename, fh, mime)}, timeout=60)
            print(f"Telegram sendDocument: {r.status_code} - {r.text[:200]}")
            if 200 <= r.status_code < 300 and (r.json().get("ok") if r.headers.get("content-type","").startswith("application/json") else True):
                return True, ""
            return False, r.text
        except Exception as e:
            print(f"Telegram sendDocument failed: {e}")
            return False, str(e)

    # ----- ops -----
    def set_webhook(self, base_url):
        """Register the webhook (one call, no expiry). Returns ``(ok, detail)``."""
        secret = current_app.config.get("TELEGRAM_WEBHOOK_SECRET", "")
        url = f"{base_url.rstrip('/')}/webhook/telegram"
        try:
            r = requests.post(self._api("setWebhook"), json={"url": url, "secret_token": secret}, timeout=15)
            return (200 <= r.status_code < 300), r.text
        except requests.RequestException as e:
            return False, str(e)
