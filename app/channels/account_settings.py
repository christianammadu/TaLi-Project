"""Account settings — channel-agnostic (WhatsApp + Telegram).

Pure functions that read/format the settings menu and apply a ``set <field> <value>``
edit, returning the reply *text* so each channel's webhook can send it via its own
transport (WhatsApp ``send_reply`` / Telegram ``send_text``). Lifted out of
``web/routes.py`` so Telegram gets settings too (matches design D-01).
"""

import re

from sqlalchemy import select, update

from app.auth import set_display_name, set_usage_type, update_business_profile
from app.data.db import session_scope
from app.data.models import User


def _read_settings(user_id):
    """Read the current settings snapshot for the menu. Returns a dict or None."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(User.display_name, User.usage_type, User.base_currency,
                       User.business_profile, User.alert_thresholds)
                .where(User.id == user_id)
            ).first()
            if not row:
                return None
            return {
                'display_name': row.display_name,
                'usage_type': row.usage_type,
                'base_currency': row.base_currency or 'NGN',
                'business_profile': row.business_profile or {},
                'alert_thresholds': row.alert_thresholds or {},
            }
    except Exception as e:
        print(f"Failed to read settings: {e}")
        return None


def _set_base_currency(user_id, code):
    try:
        with session_scope() as s:
            res = s.execute(update(User).where(User.id == user_id).values(base_currency=code))
            return res.rowcount > 0
    except Exception as e:
        print(f"Failed to set currency: {e}")
        return False


def render_settings(user_id):
    """The settings menu text (matches design D-01), or an error line."""
    cfg = _read_settings(user_id)
    if cfg is None:
        return "❌ Couldn't load your settings. Please try again."
    name = cfg['display_name'] or 'Not set'
    usage = (cfg['usage_type'] or 'Not set').capitalize()
    biz = cfg['business_profile']
    if cfg['usage_type'] == 'business':
        biz_line = f"{biz.get('name', 'Not set')}" + (f" · {biz['type']}" if biz.get('type') else '')
    else:
        biz_line = 'n/a (personal)'
    low_stock = cfg['alert_thresholds'].get('low_stock_limit', 5)
    return (
        "⚙️ *Your settings*\n\n"
        f"1. Name — {name}\n"
        f"2. Usage — {usage}\n"
        f"3. Business — {biz_line}\n"
        f"4. Currency — {cfg['base_currency']}\n"
        f"5. Alerts — Low stock < {low_stock}\n\n"
        "To change one, type e.g.:\n"
        "• *set name Ada*\n"
        "• *set currency USD*\n"
        "• *set type business*\n"
        "• *set business Ada's Kitchen*"
    )


def apply_setting(user_id, text):
    """Parse and apply a ``set <field> <value>`` edit. Returns the reply text."""
    parts = text.strip().split(None, 2)  # ['set', '<field>', '<value...>']
    if len(parts) < 3 or not parts[2].strip():
        return ("Usage: *set <name|currency|type|business> <value>*\n"
                "e.g. *set currency USD*")
    field, value = parts[1].lower(), parts[2].strip()

    if field == 'name':
        ok = set_display_name(user_id, value)
        return f"✅ Name updated to *{value}*." if ok else "❌ Couldn't update your name."
    elif field == 'currency':
        code = value.upper().strip()
        if not re.fullmatch(r'[A-Z]{3}', code):
            return "Please give a 3-letter currency code, e.g. *set currency USD*."
        ok = _set_base_currency(user_id, code)
        return (f"✅ Currency updated to *{code}*.\nNew transactions will use {code}."
                if ok else "❌ Couldn't update your currency.")
    elif field == 'type':
        usage = value.lower().strip()
        if usage not in ('personal', 'business'):
            return "Usage type must be *personal* or *business*."
        ok = set_usage_type(user_id, usage)
        extra = "\nTell me your business name with *set business <name>*." if (ok and usage == 'business') else ""
        return f"✅ Usage type set to *{usage}*.{extra}" if ok else "❌ Couldn't update usage type."
    elif field == 'business':
        ok = update_business_profile(user_id, name=value)
        # Setting a business name implies business usage.
        if ok:
            set_usage_type(user_id, 'business')
        return f"✅ Business name set to *{value}*." if ok else "❌ Couldn't update your business."
    else:
        return ("I can change *name*, *currency*, *type* or *business*.\n"
                "e.g. *set currency USD*")
