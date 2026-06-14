"""Channel registry + reply dispatch — WP-05.

Resolves a (namespaced) sender to its ``Channel`` and sends replies/documents on the
**originating** channel — so a statement requested over Telegram is delivered over
Telegram, and a WhatsApp reply goes to WhatsApp. Outgoing message-history logging is
centralized here (one site, all channels). Bare/legacy senders (no prefix) → WhatsApp.
"""

from app.channels.base import split_address, WHATSAPP, TELEGRAM

_CACHE = {}


def get_channel(name):
    """Return a cached adapter instance for a channel name (default WhatsApp)."""
    name = name or WHATSAPP
    if name not in _CACHE:
        if name == TELEGRAM:
            from app.channels.telegram import TelegramChannel
            _CACHE[name] = TelegramChannel()
        else:
            from app.channels.whatsapp import WhatsAppChannel
            _CACHE[name] = WhatsAppChannel()
    return _CACHE[name]


def channel_name(sender):
    """The channel a (namespaced) sender belongs to; a bare/legacy id → WhatsApp."""
    ch, _ = split_address(sender)
    return ch or WHATSAPP


def channel_for(sender):
    return get_channel(channel_name(sender))


def _log_outgoing(sender, text):
    """Best-effort outgoing message-history row (channel-agnostic)."""
    try:
        from app.data.database import get_db_connection
        from app.auth import get_active_session
        session = get_active_session(sender)
        user_id = session['user_id'] if session else None
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, sender_id, direction, message_text) "
            "VALUES (%s, %s, 'outgoing', %s)",
            (user_id, sender, text),
        )
        conn.commit()
    except Exception as e:
        print(f"[log_outgoing Error] {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


def send_text(sender, text):
    """Send a text reply via the sender's own channel. Returns the transport response."""
    resp = channel_for(sender).send_text(sender, text)
    _log_outgoing(sender, text)
    return resp


def send_document(sender, file_path, filename, caption=None):
    """Send a document via the sender's own channel. Returns ``(ok, detail)``."""
    ok, detail = channel_for(sender).send_document(sender, file_path, filename, caption)
    _log_outgoing(sender, f"[document] {filename} ({'ok' if ok else 'FAILED'})")
    return ok, detail
