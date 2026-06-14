import requests
from flask import current_app

from app.channels import registry

# WhatsApp transport lives in app/channels/whatsapp.py (WP-01); reply/document dispatch
# + history logging is centralized in the channel registry (WP-05). These wrappers keep
# the legacy signatures so routes.py is unchanged, and now route by the recipient's
# namespace — a bare phone resolves to WhatsApp, a tg:<id> to Telegram.


def send_reply(recipient, message_text):
    resp = registry.send_text(recipient, message_text)
    return resp.json() if resp is not None else None


def _post_message(url, headers, payload, label):
    """POST a message to the Graph API. Returns (success, detail).

    detail carries Meta's error (code + message) on failure so it can be logged
    and surfaced for diagnosis.
    """
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        print(f"Meta {label} Response: {r.status_code} - {r.text}")
        if 200 <= r.status_code < 300:
            return True, ""
        try:
            err = r.json().get("error", {})
            return False, (f"{err.get('code', '')} {err.get('message', '')}".strip() or r.text)
        except Exception:
            return False, r.text
    except requests.RequestException as e:
        print(f"Meta {label} request failed: {e}")
        return False, str(e)


def send_document(recipient, file_path, filename, caption=None):
    """Upload a local file to WhatsApp media, then send it as a document message.

    Two-step Cloud API flow (no public hosting needed):
      1. POST multipart to /{phone_number_id}/media -> media_id
      2. POST /messages type=document referencing the media_id

    Returns (success: bool, detail: str).
    """
    return registry.send_document(recipient, file_path, filename, caption)


def send_otp_template(recipient, code):
    """Send an OTP via the approved WhatsApp template.

    Returns (success: bool, detail: str). On template failure, falls back to a
    plain-text message when OTP_TEXT_FALLBACK is enabled (only delivers if the
    recipient is inside WhatsApp's 24h customer-service window).
    """
    phone_number_id = current_app.config['PHONE_NUMBER_ID']
    access_token = current_app.config['ACCESS_TOKEN']
    template_name = current_app.config.get('OTP_TEMPLATE_NAME', 'verification_code')
    lang = current_app.config.get('OTP_TEMPLATE_LANG', 'en_US')

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    template_payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]}
            ],
        },
    }

    success, detail = _post_message(url, headers, template_payload, "Template")

    if not success and current_app.config.get('OTP_TEXT_FALLBACK', True):
        print(f"[OTP] template '{template_name}' ({lang}) failed: {detail} — trying text fallback")
        text_payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": f"Your TaLi verification code is: {code}\n\nIt expires in 10 minutes."},
        }
        t_success, t_detail = _post_message(url, headers, text_payload, "Text-OTP")
        if t_success:
            success, detail = True, "delivered via text fallback"
        else:
            detail = f"template: {detail} | text: {t_detail}"

    if not success:
        print(f"[OTP DELIVERY FAILED] to={recipient}: {detail}")

    # Log outgoing message to messages history table (best-effort)
    try:
        from app.data.database import get_db_connection
        from app.auth import get_active_session
        session = get_active_session(recipient)
        user_id = session['user_id'] if session else None

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, sender_id, direction, message_text) "
            "VALUES (%s, %s, 'outgoing', %s)",
            (user_id, recipient, f"OTP sent ({'ok' if success else 'FAILED'}): {code}")
        )
        conn.commit()
    except Exception as e:
        print(f"[log_outgoing_otp Error] {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

    return success, detail
