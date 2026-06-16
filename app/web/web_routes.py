import hmac
import os
import re
from flask import Blueprint, request, render_template, current_app, jsonify
from sqlalchemy import select
from app.auth import (
    create_registration_otp,
    validate_registration_otp,
    register_user,
    get_user_by_phone,
    validate_token_and_generate_code,
)
from app.data.db import session_scope
from app.data.models import User
from app.web.whatsapp import send_otp_template

# templates/ and static/ live at the app root (one level up from app/web/).
web_bp = Blueprint('web', __name__, template_folder='../templates', static_folder='../static')


@web_bp.app_context_processor
def inject_channel_links():
    """Generic (token-less) channel entry deep-links for the marketing CTAs.

    The landing/marketing "Continue on WhatsApp / Telegram" buttons open the bot
    chat directly; per-user binding tokens are minted later in the register/verify
    flow. Falls back to the web register page when a channel isn't configured so the
    buttons never render as dead links in dev.
    """
    from flask import url_for
    number = (current_app.config.get('WHATSAPP_PUBLIC_NUMBER') or '').strip().lstrip('+')
    username = (current_app.config.get('TELEGRAM_BOT_USERNAME') or '').strip().lstrip('@')
    register = url_for('web.register')
    return {
        'whatsapp_url': f'https://wa.me/{number}' if number else register,
        'telegram_url': f'https://t.me/{username}?start=register' if username else register,
    }


@web_bp.route('/', methods=['GET'])
def index():
    """Public marketing landing page."""
    return render_template('landing.html')


@web_bp.route('/health', methods=['GET'])
def health():
    """Liveness endpoint — point an uptime monitor (UptimeRobot, etc.) here.

    Passive by default and free: it reports the model layer's status from recent real
    traffic ("up"/"down"/"unknown") plus which provider keys are configured and the last
    error per provider — so you can see *when* and *why* the intelligence service is down.
    Returns HTTP 503 when status is "down" so monitors alert automatically.

    ``?probe=1`` forces ONE tiny live model call to confirm reachability right now; it's
    gated by ``AUDIT_TOKEN`` (X-Audit-Token header) in production to avoid cost abuse.
    """
    from app.services import model_router
    want_probe = request.args.get('probe', '').lower() in ('1', 'true', 'yes')
    if want_probe:
        token = os.getenv('AUDIT_TOKEN', '')
        authorized = (
            os.getenv('OTP_DEV_BYPASS', 'false').lower() == 'true' if not token
            else hmac.compare_digest(request.headers.get('X-Audit-Token', ''), token)
        )
        if not authorized:
            want_probe = False  # never spend on an unauthenticated probe — fall back to passive
    models = model_router.health_report(active_probe=want_probe)
    code = 503 if models['status'] == 'down' else 200
    return jsonify({"app": "ok", "models": models}), code


@web_bp.route('/features', methods=['GET'])
def features():
    return render_template('features.html')


@web_bp.route('/pricing', methods=['GET'])
def pricing():
    return render_template('pricing.html')


@web_bp.route('/privacy', methods=['GET'])
def privacy():
    return render_template('privacy.html')


@web_bp.route('/terms', methods=['GET'])
def terms():
    return render_template('terms.html')


@web_bp.route('/faq', methods=['GET'])
def faq():
    return render_template('faq.html')


@web_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Show the phone registration form (GET) and process it (POST)."""
    if request.method == 'GET':
        resend_phone = request.args.get('resend', '').strip().lstrip('+')
        if resend_phone:
            # Resend OTP for an existing registration attempt
            otp = create_registration_otp(resend_phone)
            if otp:
                delivered, detail = send_otp_template(resend_phone, otp)
                if delivered:
                    return render_template('register.html', step='otp',
                                           message='A new verification code has been sent to your WhatsApp.',
                                           error=None, phone=resend_phone)
                elif current_app.config.get('OTP_DEV_BYPASS'):
                    print(f"[OTP DEV BYPASS] resend failed ({detail}); code for ***{resend_phone[-4:]}: {otp}")
                    return render_template('register.html', step='otp',
                                           message='Dev mode: enter the code shown in the server console.',
                                           error=None, phone=resend_phone)
                else:
                    print(f"[OTP resend failed] {resend_phone}: {detail}")
                    return render_template('register.html', step='otp', message=None,
                                           error='Failed to deliver the verification code. Please try again.',
                                           phone=resend_phone)
            else:
                return render_template('register.html', step='otp', message=None,
                                       error='Failed to generate a new code. Please try again.',
                                       phone=resend_phone)
        return render_template('register.html', step='phone', message=None, error=None, phone=None)

    country_code = request.form.get('country_code', '').strip()
    phone = request.form.get('phone', '').strip()

    if not phone:
        return render_template('register.html', step='phone', message=None,
                               error='Please enter a valid phone number.', phone=None)

    # Combine the country code with the local number into the full international
    # number (digits only, no +) so it matches the WhatsApp sender_id used at login.
    # e.g. '+234' + '08167690780' -> '2348167690780'.
    cc = re.sub(r'\D', '', country_code)
    local = re.sub(r'\D', '', phone)
    phone = local if (cc and local.startswith(cc)) else (cc + local.lstrip('0'))

    # Check if user is already registered and verified.
    # Registration creates a *new* account; an existing user who wants a second channel
    # (e.g. add Telegram) does it from the channel they already have via Path B — the
    # channel they're on is the auth anchor, so we never re-verify here (that would let
    # anyone who knows your number link their own chat to your books).
    existing_user = get_user_by_phone(phone)
    if existing_user:
        wa = (current_app.config.get('WHATSAPP_PUBLIC_NUMBER') or '').strip().lstrip('+')
        return render_template(
            'register.html', step='phone', message=None,
            error='You already have a TaLi account for this number. To use TaLi on '
                  'Telegram too, open WhatsApp and send “/link telegram” — I’ll reply '
                  'with a one-tap link to connect this chat to your existing books. '
                  '(Just signing in? Send “login” on WhatsApp.)',
            link_hint=(f'https://wa.me/{wa}?text=%2Flink%20telegram' if wa else None),
            phone=None)

    # Create an unverified user if one doesn't exist yet.
    try:
        with session_scope() as s:
            exists = s.execute(select(User.id).where(User.phone_number == phone)).first()
            if not exists:
                s.add(User(
                    phone_number=phone, is_verified=False,
                    alert_thresholds={"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000},
                ))
    except Exception as e:
        print(f"Error checking/creating user: {e}")

    # Generate OTP and send via WhatsApp Template
    otp = create_registration_otp(phone)
    if otp:
        delivered, detail = send_otp_template(phone, otp)
        if delivered:
            return render_template('register.html', step='otp',
                                   message='A verification code has been sent to your WhatsApp.',
                                   error=None, phone=phone)
        elif current_app.config.get('OTP_DEV_BYPASS'):
            # Dev-only: only reached when the bypass is explicitly enabled.
            print(f"[OTP DEV BYPASS] delivery failed ({detail}); code for ***{phone[-4:]}: {otp}")
            return render_template('register.html', step='otp',
                                   message='Dev mode: enter the code shown in the server console.',
                                   error=None, phone=phone)
        else:
            print(f"[OTP send failed] {phone}: {detail}")
            return render_template('register.html', step='phone', message=None,
                                   error='Failed to deliver the verification code. Please try again.',
                                   phone=None)
    else:
        return render_template('register.html', step='phone', message=None,
                               error='Failed to send verification code. Please try again.',
                               phone=None)


@web_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Validate the OTP entered by the user to complete registration."""
    phone = request.form.get('phone', '').strip().lstrip('+')
    code = request.form.get('code', '').strip()

    if not phone or not code:
        return render_template('register.html', step='otp', message=None,
                               error='Please enter the verification code.', phone=phone)

    if validate_registration_otp(phone, code):
        # Mark user as verified
        user_id = register_user(phone)
        if user_id:
            # WP-04: mint a one-time binding token + offer both channels (web-first onboarding).
            from app.auth import issue_binding_token
            from app.channels.onboarding import telegram_deeplink, whatsapp_deeplink
            token = issue_binding_token(user_id)
            return render_template('register.html', step='done', phone=phone,
                                   message='✅ Registration complete! Tap to start in your chat app:',
                                   telegram_link=(telegram_deeplink(token) if token else None),
                                   whatsapp_link=(whatsapp_deeplink(token) if token else None),
                                   error=None)
        else:
            return render_template('register.html', step='otp', message=None,
                                   error='Registration failed. Please try again.', phone=phone)
    else:
        return render_template('register.html', step='otp', message=None,
                               error='Invalid or expired code. Please try again.', phone=phone)


@web_bp.route('/verify', methods=['GET'])
def verify():
    """Display the 6-digit access code after the user clicks the verification link from WhatsApp."""
    token = request.args.get('t', '')

    if not token:
        return render_template('error.html',
                               message='No verification token provided.')

    phone, code = validate_token_and_generate_code(token)

    if code:
        return render_template('verify.html', code=code)
    else:
        return render_template('error.html',
                               message='This verification link has expired or is invalid.')
