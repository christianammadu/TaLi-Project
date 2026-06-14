import re
import hmac
import hashlib
from flask import Blueprint, request, jsonify, current_app
from mysql.connector import Error
from app.data.database import get_db_connection
from app.web.whatsapp import send_reply
from app.auth import (
    get_user_by_sender,
    get_user_by_phone,
    get_active_session,
    create_login_token,
    validate_access_code,
    end_session,
    create_pending_session,
    set_display_name,
    set_usage_type,
    update_business_profile,
    get_onboarding_state,
    set_onboarding_state,
    ONBOARDING_DONE,
)
from sqlalchemy import select, update
from app.data.db import session_scope
from app.data.models import User

webhook_bp = Blueprint('webhook', __name__)

# Regex to match a 6-digit code
SIX_DIGIT_PATTERN = re.compile(r'^\d{6}$')

# Commands that don't require authentication
PUBLIC_COMMANDS = {'login', '/login'}
REGISTRATION_COMMANDS = {'register', '/register', 'signup', '/signup'}
AUTH_COMMANDS = {'logout', '/logout', 'help', '/help', 'settings', '/settings'}

# Onboarding business-category menu (matches design D-01).
BUSINESS_TYPES = {'1': 'Retail / Shop', '2': 'Food / Restaurant', '3': 'Services', '4': 'Other'}
SKIP_WORDS = {'skip', '/skip'}


def send_unregistered_welcome(sender):
    """One consistent first-contact message for unregistered numbers."""
    send_reply(
        sender,
        "👋 Hi, I'm TaLi — your pocket bookkeeper.\n\n"
        "I keep your business books right here in the chat: sales, expenses, "
        "stock, debts and reports — just tell me in your own words.\n\n"
        "We're not set up yet. Create your free account here:\n"
        f"{current_app.config['APP_BASE_URL']}/register\n\n"
        "Then come back and type *login* to connect."
    )


def handle_login(sender):
    """Handle the login command — generate a verification link."""
    # Look up user by sender_id (check if they've linked before). Fall back to a
    # phone-number lookup so a freshly-registered user (not yet linked in
    # whatsapp_accounts) can still log in — the WhatsApp sender_id IS their phone.
    user = get_user_by_sender(sender) or get_user_by_phone(sender)

    if user:
        phone = user['phone_number']
        create_pending_session(sender, user['id'])
    else:
        # If sender hasn't linked before, we can't proceed without knowing their phone
        send_unregistered_welcome(sender)
        return

    token = create_login_token(phone)
    if token:
        verify_url = f"{current_app.config['APP_BASE_URL']}/verify?t={token}"
        send_reply(
            sender,
            f"🔐 *Let's log you in*\n\n"
            f"Tap to get your access code:\n{verify_url}\n\n"
            f"Then send me the 6-digit code and you're in.\n"
            f"⏰ The link expires in {current_app.config['TOKEN_EXPIRY_MINUTES']} minutes."
        )
    else:
        send_reply(sender, "❌ Something went wrong. Please try again.")


def handle_access_code(sender, code):
    """Handle a 6-digit access code submission."""
    user = validate_access_code(sender, code)
    if user == "reuse_or_expired":
        send_reply(sender, "❌ This code has already been used or is expired.")
    elif user:
        # First-time users haven't finished onboarding — start it instead of the
        # generic welcome. Returning users get the personalised greeting (WP-05).
        state = get_onboarding_state(user['id'])
        if state and not state['complete']:
            _send_next_onboarding(sender, user['id'])
            return
        name = user.get('display_name') or user['phone_number']
        send_reply(
            sender,
            f"✅ *Welcome back, {name}!*\n\n"
            "You're logged in — your books are ready.\n\n"
            "Try:\n"
            "• _\"Sold rice 5000\"_\n"
            "• _\"Bought fuel 2k\"_\n"
            "• _\"What's my balance?\"_\n"
            "• _\"Send me a report for this month\"_\n\n"
            "Type *help* anytime to see everything I can do."
        )
    else:
        send_reply(
            sender,
            "❌ Invalid or expired code.\n\n"
            "Type *login* to get a new verification link."
        )


def handle_logout(sender):
    """Handle the logout command."""
    if end_session(sender):
        send_reply(sender, "👋 You've been logged out.\n\nType *login* to sign in again.")
    else:
        send_reply(sender, "❌ Something went wrong. Please try again.")


def handle_help(sender):
    """Send help message with available commands."""
    send_reply(
        sender,
        "📖 *TaLi Help*\n\n"
        "*📝 Record*\n"
        "• _\"Sold rice 5000\"_\n"
        "• _\"Bought fuel 2k\"_\n"
        "• _\"Sold 3 bags of rice 5000 on credit to John\"_\n\n"
        "*📦 Stock*\n"
        "• _\"Add 10 bags of rice\"_  ·  _\"Set rice to 50\"_\n\n"
        "*👥 Debts*\n"
        "• _\"John owes 5000\"_  ·  _\"John paid 2000\"_\n\n"
        "*📊 Ask*\n"
        "• _\"What's my balance?\"_\n"
        "• _\"How much did I spend this month?\"_\n"
        "• _\"How is my business doing?\"_\n\n"
        "*📑 Reports*\n"
        "• _\"Monthly report\"_ — quick summary\n"
        "• _\"Statement of my sales for June\"_ — chat, PDF or Excel\n\n"
        "*⚙️ Commands*\n"
        "*login* · *logout* · *settings* · *help*"
    )


# --- Onboarding (WP-03) ---
#
# A lightweight, resumable in-chat state machine. The user record IS the state
# (see auth.get_onboarding_state); each inbound message answers the first
# unanswered question. Name is skippable. Categories match design D-01.

def _send_next_onboarding(sender, user_id):
    """Send the next onboarding question, or the completion message if done.
    Returns True when onboarding is complete."""
    state = get_onboarding_state(user_id)
    if state is None:
        send_reply(sender, "❌ Something went wrong. Type *login* to try again.")
        return False

    nxt = state['next']
    if nxt == 'name':
        send_reply(sender, "👋 *Welcome to TaLi!*\n"
                           "I'll keep your books right here in the chat.\n\n"
                           "First — what should I call you? _(or reply *skip*)_")
    elif nxt == 'usage':
        send_reply(sender, "Are you using TaLi for *personal* or *business*?\n\n"
                           "Reply *1* for Personal\nReply *2* for Business")
    elif nxt == 'business_name':
        send_reply(sender, "Great — let's set up your business. What's the *business name*?")
    elif nxt == 'business_type':
        send_reply(sender, "And what kind of business is it?\n\n"
                           "1️⃣ Retail / Shop\n2️⃣ Food / Restaurant\n3️⃣ Services\n4️⃣ Other")
    else:
        # Complete — mark done and send a personalised wrap-up.
        set_onboarding_state(user_id, step=ONBOARDING_DONE)
        name = state.get('display_name')
        greet = f"All set, *{name}*!" if name else "All set!"
        biz = (state.get('business_profile') or {}).get('name')
        line2 = f"*{biz}* is ready to go.\n\n" if biz else "\n"
        send_reply(sender, f"✅ {greet}\n{line2}"
                           "Just tell me what happened, in your own words:\n"
                           "• _\"Sold rice 5000\"_\n"
                           "• _\"Bought fuel 2k\"_\n"
                           "• _\"What's my balance?\"_\n\n"
                           "Type *help* for everything I can do, or *settings* to make changes.")
        return True
    return False


def handle_onboarding_answer(sender, text, session):
    """Process one onboarding answer based on the current pending question."""
    user_id = session['user_id']
    state = get_onboarding_state(user_id)
    if state is None or state['complete']:
        return  # nothing to do; caller will fall through
    nxt = state['next']
    answer = text.strip()
    low = answer.lower()

    if nxt == 'name':
        if low in SKIP_WORDS:
            # Skip the name — advance past it so we don't re-ask in-flow (re-asked later).
            set_onboarding_state(user_id, step=1)
        else:
            set_display_name(user_id, answer)
    elif nxt == 'usage':
        if low in ('1', 'personal', 'p'):
            set_usage_type(user_id, 'personal')
        elif low in ('2', 'business', 'b'):
            set_usage_type(user_id, 'business')
        else:
            send_reply(sender, "Please reply *1* for Personal or *2* for Business.")
            return
    elif nxt == 'business_name':
        update_business_profile(user_id, name=answer)
    elif nxt == 'business_type':
        biz_type = BUSINESS_TYPES.get(low) or (answer if len(answer) <= 50 else None)
        if not biz_type:
            send_reply(sender, "Please reply *1*–*4* to pick a category.")
            return
        update_business_profile(user_id, type=biz_type)

    _send_next_onboarding(sender, user_id)


# --- Settings (WP-04) ---

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


def handle_settings(sender, session):
    """Print the settings menu (matches design D-01)."""
    cfg = _read_settings(session['user_id'])
    if cfg is None:
        send_reply(sender, "❌ Couldn't load your settings. Please try again.")
        return
    name = cfg['display_name'] or 'Not set'
    usage = (cfg['usage_type'] or 'Not set').capitalize()
    biz = cfg['business_profile']
    if cfg['usage_type'] == 'business':
        biz_line = f"{biz.get('name', 'Not set')}" + (f" · {biz['type']}" if biz.get('type') else '')
    else:
        biz_line = 'n/a (personal)'
    low_stock = cfg['alert_thresholds'].get('low_stock_limit', 5)
    send_reply(
        sender,
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


def _set_base_currency(user_id, code):
    try:
        with session_scope() as s:
            res = s.execute(update(User).where(User.id == user_id).values(base_currency=code))
            return res.rowcount > 0
    except Exception as e:
        print(f"Failed to set currency: {e}")
        return False


def handle_set(sender, text, session):
    """Parse and apply a `set <field> <value>` edit."""
    user_id = session['user_id']
    parts = text.strip().split(None, 2)  # ['set', '<field>', '<value...>']
    if len(parts) < 3 or not parts[2].strip():
        send_reply(sender, "Usage: *set <name|currency|type|business> <value>*\n"
                           "e.g. *set currency USD*")
        return
    field, value = parts[1].lower(), parts[2].strip()

    if field == 'name':
        ok = set_display_name(user_id, value)
        send_reply(sender, f"✅ Name updated to *{value}*." if ok else "❌ Couldn't update your name.")
    elif field == 'currency':
        code = value.upper().strip()
        if not re.fullmatch(r'[A-Z]{3}', code):
            send_reply(sender, "Please give a 3-letter currency code, e.g. *set currency USD*.")
            return
        ok = _set_base_currency(user_id, code)
        send_reply(sender, f"✅ Currency updated to *{code}*.\nNew transactions will use {code}."
                   if ok else "❌ Couldn't update your currency.")
    elif field == 'type':
        usage = value.lower().strip()
        if usage not in ('personal', 'business'):
            send_reply(sender, "Usage type must be *personal* or *business*.")
            return
        ok = set_usage_type(user_id, usage)
        extra = "\nTell me your business name with *set business <name>*." if (ok and usage == 'business') else ""
        send_reply(sender, f"✅ Usage type set to *{usage}*.{extra}" if ok else "❌ Couldn't update usage type.")
    elif field == 'business':
        ok = update_business_profile(user_id, name=value)
        # Setting a business name implies business usage.
        if ok:
            set_usage_type(user_id, 'business')
        send_reply(sender, f"✅ Business name set to *{value}*." if ok else "❌ Couldn't update your business.")
    else:
        send_reply(sender, "I can change *name*, *currency*, *type* or *business*.\n"
                           "e.g. *set currency USD*")


def handle_authenticated_message(sender, text, session, message_id=None):
    """Process a message from an authenticated user using the Agent Router.

    The router classifies the message and dispatches it to the appropriate agent.
    """
    from app.agents.agent_router import AgentRouter

    user_id = session['user_id']
    router = AgentRouter(user_id=user_id, sender_id=sender)
    reply = router.route(text, message_id)
    if reply in ("__DUPLICATE_DROP__", "__ERROR_HANDLED_SAGA__"):
        return
    send_reply(sender, reply)


@webhook_bp.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Verification logic for Meta dashboard
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == current_app.config['VERIFY_TOKEN']:
            return challenge, 200
        return 'Verification failed', 403

    if request.method == 'POST':
        # Verify Meta's HMAC signature before trusting any payload.
        app_secret = current_app.config.get('APP_SECRET')
        if app_secret:
            signature = request.headers.get('X-Hub-Signature-256', '')
            expected = 'sha256=' + hmac.new(
                app_secret.encode(), request.get_data(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                print("Webhook signature verification failed — rejecting payload")
                return jsonify({"status": "forbidden"}), 403
        else:
            print("WARNING: META_APP_SECRET not configured — webhook signature NOT verified")

        data = request.json
        # LOG 1: See the raw data Meta sends you
        print(f"Full Data Received: {data}")

        try:
            if 'messages' in data['entry'][0]['changes'][0]['value']:
                message = data['entry'][0]['changes'][0]['value']['messages'][0]
                sender = message['from']
                # Guard non-text messages (image / voice / sticker / location):
                # they have no message['text'] and would otherwise raise KeyError.
                if message.get('type') != 'text' or 'text' not in message:
                    send_reply(sender, "🤖 I can only read text messages right now. "
                                       "Please type your transaction, e.g. \"Sold rice 5000\".")
                    return jsonify({"status": "ok"}), 200
                text = message['text']['body'].strip()
                text_lower = text.lower()
                message_id = message.get('id')

                print(f"Message from {sender} (ID: {message_id}): {text}")

                # --- COMMAND ROUTING ---
                session = get_active_session(sender)
                user_id = session['user_id'] if session else None

                # Log incoming message to messages table and register received webhook event
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO messages (user_id, sender_id, direction, message_text, whatsapp_message_id) "
                        "VALUES (%s, %s, 'incoming', %s, %s)",
                        (user_id, sender, text, message_id)
                    )
                    if message_id:
                        import json
                        cursor.execute(
                            "INSERT IGNORE INTO webhook_events (whatsapp_message_id, sender_id, payload, status) "
                            "VALUES (%s, %s, %s, 'received')",
                            (message_id, sender, json.dumps({"text": text}))
                        )
                    conn.commit()
                except Exception as db_err:
                    print(f"Error logging incoming message or webhook event: {db_err}")
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()

                # 1. Login command (no auth required)
                if text_lower in PUBLIC_COMMANDS:
                    handle_login(sender)
                    return jsonify({"status": "ok"}), 200

                # 1b. Registration commands (no auth required)
                if text_lower in REGISTRATION_COMMANDS:
                    send_unregistered_welcome(sender)
                    return jsonify({"status": "ok"}), 200

                # 2. Check if it's a 6-digit access code (no auth required)
                if SIX_DIGIT_PATTERN.match(text):
                    handle_access_code(sender, text)
                    return jsonify({"status": "ok"}), 200

                if not session:
                    # Not authenticated. Check if user is registered.
                    user = get_user_by_sender(sender) or get_user_by_phone(sender)
                    if user:
                        send_reply(
                            sender,
                            "🔒 Session expired or not found. Type *login* to authenticate."
                        )
                    else:
                        send_unregistered_welcome(sender)
                    return jsonify({"status": "ok"}), 200

                # 4. Auth commands (require session)
                if text_lower in {'logout', '/logout'}:
                    handle_logout(sender)
                    return jsonify({"status": "ok"}), 200

                if text_lower in {'help', '/help'}:
                    handle_help(sender)
                    return jsonify({"status": "ok"}), 200

                if text_lower in {'settings', '/settings'}:
                    handle_settings(sender, session)
                    return jsonify({"status": "ok"}), 200

                if text_lower.startswith('set '):
                    handle_set(sender, text, session)
                    return jsonify({"status": "ok"}), 200

                # 4b. Onboarding gate — until onboarding is complete, every other
                # message is an onboarding answer, not a transaction.
                ob = get_onboarding_state(session['user_id'])
                if ob and not ob['complete']:
                    handle_onboarding_answer(sender, text, session)
                    return jsonify({"status": "ok"}), 200

                # 5. Authenticated message — process as transaction
                handle_authenticated_message(sender, text, session, message_id)

        except Exception as e:
            # LOG 3: If the code crashes, this tells you why
            print(f"CRITICAL ERROR: {e}")

        return jsonify({"status": "ok"}), 200
