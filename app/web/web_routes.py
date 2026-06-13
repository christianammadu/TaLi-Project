import re
from flask import Blueprint, request, render_template, current_app
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


@web_bp.route('/', methods=['GET'])
def index():
    """Public marketing landing page."""
    return render_template('landing.html')


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

    # Check if user is already registered and verified
    existing_user = get_user_by_phone(phone)
    if existing_user:
        return render_template('register.html', step='phone', message=None,
                               error='This phone number is already registered. '
                                     'Send "login" on WhatsApp to get started.',
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
            return render_template('register.html', step='done', phone=phone,
                                   message='✅ Registration complete! Open WhatsApp and send "login" to start using TaLi.',
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
