"""Onboarding + cross-channel linking — WP-04 (Path B).

Channel-agnostic handling of the binding commands surfaced by the adapters
(``parse_command`` in base.py). Used by each channel's webhook:

  - ``redeem``  (Telegram ``/start <token>`` · WhatsApp ``LINK-<token>``) → bind this chat
    to the token's user + open a session.
  - ``link <channel>`` → issue a one-time token and hand back the *other* channel's deep-link
    (Path B: the channel you're already on is the auth anchor; no web detour).
  - ``unlink`` → unlink this chat.
  - ``start`` / unbound chat → the onboarding prompt.
"""

from flask import current_app

from app import auth
from app.channels.base import TELEGRAM, WHATSAPP, make_address


# --- deep-link builders (pure-ish; read config) ---

def telegram_deeplink(token):
    username = current_app.config.get("TELEGRAM_BOT_USERNAME", "")
    return f"https://t.me/{username}?start={token}"


def whatsapp_deeplink(token):
    number = current_app.config.get("WHATSAPP_PUBLIC_NUMBER", "")
    return f"https://wa.me/{number}?text=LINK-{token}"


def _deeplink_for(channel, token):
    return telegram_deeplink(token) if channel == TELEGRAM else whatsapp_deeplink(token)


def onboarding_prompt():
    base = current_app.config.get("APP_BASE_URL", "").rstrip("/")
    return ("👋 Hi, I'm TaLi — your pocket bookkeeper. We haven't met yet. "
            f"Set up your free account at {base}/register and I'll send a one-tap "
            "link to connect this chat.")


def resolve(channel, native_id):
    """The user bound to this chat, or None (legacy WhatsApp rows included)."""
    return auth.resolve_channel_user(channel, native_id)


# --- the command handler ---

def handle_command(channel, native_id, command, arg):
    """Process a binding/link command for a chat. Returns the reply text (or None)."""
    if command == "redeem":
        if not arg:
            return "That link is missing its code — get a fresh one from the web or your other app."
        user_id = auth.redeem_binding_token(arg, channel, native_id)
        if user_id:
            auth.open_session(make_address(channel, native_id), user_id)
            return "✅ Linked! Now just tell me what happened — like “Sold rice 5000” — and I'll keep the books."
        return "⚠️ That link has expired or was already used. Get a fresh one and tap again."

    if command == "link":
        target = (arg or "").strip().lower()
        if target not in (WHATSAPP, TELEGRAM) or target == channel:
            other = TELEGRAM if channel == WHATSAPP else WHATSAPP
            return f"Tell me which to add — e.g. “/link {other}”."
        user = resolve(channel, native_id)
        if not user:
            return onboarding_prompt()
        token = auth.issue_binding_token(user["id"], target_channel=target)
        if not token:
            return "Couldn't create a link right now — please try again."
        return (f"Tap to add {target.title()} → {_deeplink_for(target, token)}\n"
                "(The link works once and expires soon.)")

    if command == "unlink":
        auth.unlink_channel(channel, native_id)
        return "Unlinked this chat from your TaLi account. Your other channels still work."

    # "start" with no token, "help", or anything else → onboarding prompt
    return onboarding_prompt()
