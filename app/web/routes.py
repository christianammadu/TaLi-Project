import re
import hmac
import hashlib
from flask import Blueprint, request, jsonify, current_app
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
    get_onboarding_state,
)
from app.channels import onboarding
from app.channels.account_settings import render_settings, apply_setting
from app.channels.base import parse_command, WHATSAPP
from app.channels.onboarding_flow import handle_onboarding_answer as consume_onboarding_answer
from app.channels.onboarding_flow import send_next_onboarding as send_onboarding_prompt

webhook_bp = Blueprint('webhook', __name__)

# Regex to match a 6-digit code
SIX_DIGIT_PATTERN = re.compile(r'^\d{6}$')

# Commands that don't require authentication
PUBLIC_COMMANDS = {'login', '/login'}
REGISTRATION_COMMANDS = {'register', '/register', 'signup', '/signup'}
AUTH_COMMANDS = {'logout', '/logout', 'help', '/help', 'settings', '/settings'}

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
        "*login* · *logout* · *settings* · *help*\n\n"
        "*🔗 Add Telegram*\n"
        "Send */link telegram* — I'll reply with a one-tap link so you can use TaLi "
        "on Telegram too, on the same books."
    )


# --- Onboarding (WP-03) ---
#
# A lightweight, resumable in-chat state machine. The user record IS the state
# (see auth.get_onboarding_state); each inbound message answers the first
# unanswered question. Name is skippable. Categories match design D-01.

def _send_next_onboarding(sender, user_id):
    """Send the next onboarding question, or the completion message if done.
    Returns True when onboarding is complete."""
    return send_onboarding_prompt(
        user_id,
        lambda text: send_reply(sender, text),
        markdown=True,
        error_text="❌ Something went wrong. Type *login* to try again.",
    )


def handle_onboarding_answer(sender, text, session):
    """Process one onboarding answer based on the current pending question."""
    consume_onboarding_answer(session['user_id'], text, lambda reply: send_reply(sender, reply), markdown=True)


# --- Settings (WP-04) ---
# The read/format/apply logic is channel-agnostic and lives in
# app/channels/account_settings.py (so Telegram gets settings too); these are thin
# WhatsApp transport wrappers.

def handle_settings(sender, session):
    """Print the settings menu (matches design D-01)."""
    send_reply(sender, render_settings(session['user_id']))


def handle_set(sender, text, session):
    """Parse and apply a `set <field> <value>` edit."""
    send_reply(sender, apply_setting(session['user_id'], text))


def handle_authenticated_message(sender, text, session, message_id=None):
    """Process a message from an authenticated user using the Agent Router.

    The router classifies the message and dispatches it to the appropriate agent.
    """
    from app.agents.agent_router import AgentRouter

    user_id = session['user_id']
    router = AgentRouter(user_id=user_id, sender_id=sender)
    reply = router.route(text, message_id)
    if reply in ("__DUPLICATE_DROP__", "__ERROR_HANDLED_SAGA__", "__ASYNC_STARTED__"):
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
        elif current_app.config.get('OTP_DEV_BYPASS'):
            print("WARNING: META_APP_SECRET unset — signature NOT verified (OTP_DEV_BYPASS dev mode)")
        else:
            # Fail closed: never process unauthenticated webhooks in production.
            print("META_APP_SECRET not configured — rejecting webhook (set it, or OTP_DEV_BYPASS for dev)")
            return jsonify({"status": "forbidden"}), 403

        data = request.get_json(silent=True) or {}

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

                # 2b. First-time channel binding from the web registration/link flow.
                cmd, cmd_arg = parse_command(text)
                if cmd == "redeem":
                    reply = onboarding.handle_command(WHATSAPP, sender, cmd, cmd_arg)
                    if reply:
                        send_reply(sender, reply)
                    user = onboarding.resolve(WHATSAPP, sender)
                    if user and reply and reply.startswith("✅ Linked"):
                        _send_next_onboarding(sender, user["id"])
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

                # 4b. Cross-channel linking (Path B): /link <channel>, /unlink.
                # The channel you're already on is the auth anchor — resolve the user,
                # mint a one-time token, and hand back the other channel's deep-link.
                if cmd in ("link", "unlink"):
                    reply = onboarding.handle_command(WHATSAPP, sender, cmd, cmd_arg)
                    if reply:
                        send_reply(sender, reply)
                    return jsonify({"status": "ok"}), 200

                # 4c. Onboarding gate — until onboarding is complete, every other
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
