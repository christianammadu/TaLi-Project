"""Authentication & session management — ported to the SQLAlchemy ORM.

Public function signatures and return shapes are unchanged (dicts for users and
sessions) so callers (routes, web_routes, agent_router) are unaffected.
"""
import secrets
import string
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.data.db import session_scope
from app.data.models import Session as SessionModel
from app.data.models import BindingToken, ChannelAccount, User, VerificationCode, WhatsappAccount
from app.services.uuid_utils import uuid7

_DEFAULT_THRESHOLDS = {"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000}


def generate_otp():
    """Generate a random 6-digit numeric OTP."""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def generate_token():
    """Generate a secure URL-safe token for verification links."""
    return secrets.token_urlsafe(48)


# --- Registration ---

def create_registration_otp(phone_number):
    """Create and store an OTP for phone registration. Returns the OTP or None."""
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=current_app.config['OTP_EXPIRY_MINUTES'])
    try:
        with session_scope() as s:
            s.execute(
                update(VerificationCode)
                .where(
                    VerificationCode.phone_number == phone_number,
                    VerificationCode.purpose == 'registration',
                    VerificationCode.used.is_(False),
                )
                .values(used=True)
            )
            s.add(VerificationCode(
                phone_number=phone_number, code=otp, purpose='registration', expires_at=expires_at
            ))
        return otp
    except Exception as e:
        print(f"Failed to create registration OTP: {e}")
        return None


def validate_registration_otp(phone_number, code):
    """Validate a registration OTP. Returns True if valid, else False."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(VerificationCode)
                .where(
                    VerificationCode.phone_number == phone_number,
                    VerificationCode.code == code,
                    VerificationCode.purpose == 'registration',
                    VerificationCode.used.is_(False),
                    VerificationCode.expires_at > func.now(),
                )
                .order_by(VerificationCode.created_at.desc())
                .limit(1)
            ).scalars().first()
            if row:
                row.used = True
                return True
            return False
    except Exception as e:
        print(f"Failed to validate registration OTP: {e}")
        return False


def register_user(phone_number):
    """Register a new user or mark an existing one verified. Returns user id or None."""
    try:
        with session_scope() as s:
            user = s.execute(
                select(User).where(User.phone_number == phone_number)
            ).scalars().first()
            if user:
                if not user.is_verified:
                    user.is_verified = True
                return str(user.id)
            user_uuid = uuid7()
            user = User(id=user_uuid, phone_number=phone_number, is_verified=True, alert_thresholds=_DEFAULT_THRESHOLDS)
            s.add(user)
            s.flush()  # populate user.id before the session closes
            return str(user.id)
    except Exception as e:
        print(f"Failed to register user: {e}")
        return None


# --- Login (WhatsApp) ---

def _user_dict(row):
    return {'id': str(row.id), 'phone_number': row.phone_number, 'display_name': row.display_name}


def get_user_by_phone(phone_number):
    """Look up a verified user by phone number. Returns a dict or None."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(User.id, User.phone_number, User.display_name)
                .where(User.phone_number == phone_number, User.is_verified.is_(True))
            ).first()
            return _user_dict(row) if row else None
    except Exception as e:
        print(f"Failed to look up user by phone: {e}")
        return None


def get_user_by_sender(sender_id):
    """Look up a verified user by their WhatsApp sender_id. Returns a dict or None."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(User.id, User.phone_number, User.display_name)
                .join(WhatsappAccount, User.id == WhatsappAccount.user_id)
                .where(WhatsappAccount.sender_id == sender_id, User.is_verified.is_(True))
            ).first()
            return _user_dict(row) if row else None
    except Exception as e:
        print(f"Failed to look up user by sender_id: {e}")
        return None


def create_login_token(phone_number):
    """Create a login verification token. Returns the token or None."""
    token = generate_token()
    expires_at = datetime.utcnow() + timedelta(minutes=current_app.config['TOKEN_EXPIRY_MINUTES'])
    try:
        with session_scope() as s:
            s.execute(
                update(VerificationCode)
                .where(
                    VerificationCode.phone_number == phone_number,
                    VerificationCode.purpose == 'login',
                    VerificationCode.used.is_(False),
                )
                .values(used=True)
            )
            s.add(VerificationCode(
                phone_number=phone_number, code='', token=token, purpose='login', expires_at=expires_at
            ))
        return token
    except Exception as e:
        print(f"Failed to create login token: {e}")
        return None


def validate_token_and_generate_code(token):
    """Validate a login token and attach a fresh 6-digit code.
    Returns (phone_number, code) on success, (None, None) otherwise."""
    code = generate_otp()
    try:
        with session_scope() as s:
            row = s.execute(
                select(VerificationCode)
                .where(
                    VerificationCode.token == token,
                    VerificationCode.purpose == 'login',
                    VerificationCode.used.is_(False),
                    VerificationCode.expires_at > func.now(),
                )
                .limit(1)
            ).scalars().first()
            if row:
                row.code = code  # keep used=False until the code is entered
                return row.phone_number, code
            return None, None
    except Exception as e:
        print(f"Failed to validate token: {e}")
        return None, None


def validate_access_code(sender_id, code):
    """Validate a 6-digit access code entered in WhatsApp, scoped to the sender's
    phone (the WhatsApp sender_id is the E.164 number the code was delivered to),
    then link the account and open an ACTIVE session.

    Returns a user dict on success, 'reuse_or_expired' if the claim fails, or None.
    """
    try:
        with session_scope() as s:
            # Atomic single-use claim scoped to this sender's phone — prevents a
            # code issued for user A from being redeemed by sender B (takeover).
            res = s.execute(
                update(VerificationCode)
                .where(
                    VerificationCode.code == code,
                    VerificationCode.phone_number == sender_id,
                    VerificationCode.purpose == 'login',
                    VerificationCode.used.is_(False),
                    VerificationCode.expires_at > func.now(),
                )
                .values(used=True)
            )
            claimed = res.rowcount
            # Commit the claim immediately so single-use holds even if a later
            # step fails (mirrors the previous two-commit behaviour).
            s.commit()
            if claimed == 0:
                return "reuse_or_expired"

            rec = s.execute(
                select(VerificationCode.phone_number)
                .where(
                    VerificationCode.code == code,
                    VerificationCode.phone_number == sender_id,
                    VerificationCode.purpose == 'login',
                    VerificationCode.used.is_(True),
                )
                .order_by(VerificationCode.created_at.desc())
                .limit(1)
            ).first()
            if not rec:
                return None

            user = s.execute(
                select(User.id, User.phone_number, User.display_name)
                .where(User.phone_number == rec.phone_number, User.is_verified.is_(True))
            ).first()
            if not user:
                return None

            # Link sender_id -> user (upsert).
            s.execute(
                mysql_insert(WhatsappAccount)
                .values(sender_id=sender_id, user_id=user.id)
                .on_duplicate_key_update(user_id=user.id, linked_at=func.now())
            )

            # Replace any prior active session with a fresh ACTIVE one.
            s.execute(
                update(SessionModel)
                .where(SessionModel.sender_id == sender_id, SessionModel.is_active.is_(True))
                .values(is_active=False, status='EXPIRED')
            )
            expires_at = datetime.utcnow() + timedelta(hours=current_app.config['SESSION_DURATION_HOURS'])
            session_uuid = uuid7()
            s.add(SessionModel(
                id=session_uuid, sender_id=sender_id, user_id=user.id, expires_at=expires_at, status='ACTIVE', is_active=True
            ))
            return _user_dict(user)
    except Exception as e:
        print(f"Failed to validate access code: {e}")
        return None


# --- Session Management ---

def get_active_session(sender_id):
    """Return the sender's active session as a dict (60s grace for PENDING), or None."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(
                    SessionModel.id, SessionModel.user_id, SessionModel.expires_at,
                    SessionModel.status, SessionModel.created_at,
                    User.phone_number, User.display_name, User.business_id,
                )
                .join(User, SessionModel.user_id == User.id)
                .where(
                    SessionModel.sender_id == sender_id,
                    SessionModel.is_active.is_(True),
                    SessionModel.expires_at > func.now(),
                )
                .order_by(SessionModel.created_at.desc())
                .limit(1)
            ).first()
            if not row:
                return None
            data = {
                'id': str(row.id), 'user_id': str(row.user_id), 'expires_at': row.expires_at,
                'status': row.status, 'created_at': row.created_at,
                'phone_number': row.phone_number, 'display_name': row.display_name,
                'business_id': row.business_id,
            }
            if row.status == 'ACTIVE':
                return data
            if row.status == 'PENDING':
                time_diff = datetime.utcnow() - row.created_at
                if abs(time_diff.total_seconds()) < 60:
                    return data
            return None
    except Exception as e:
        print(f"Failed to check session: {e}")
        return None


def end_session(sender_id):
    """Deactivate all active sessions for a sender. Returns True on success."""
    try:
        with session_scope() as s:
            s.execute(
                update(SessionModel)
                .where(SessionModel.sender_id == sender_id, SessionModel.is_active.is_(True))
                .values(is_active=False, status='EXPIRED')
            )
        return True
    except Exception as e:
        print(f"Failed to end session: {e}")
        return False


def create_pending_session(sender_id, user_id):
    """Open a PENDING session (1-hour window) for the sender. Returns True on success."""
    try:
        with session_scope() as s:
            s.execute(
                update(SessionModel)
                .where(SessionModel.sender_id == sender_id, SessionModel.is_active.is_(True))
                .values(is_active=False, status='EXPIRED')
            )
            expires_at = datetime.utcnow() + timedelta(hours=1)
            session_uuid = uuid7()
            s.add(SessionModel(
                id=session_uuid, sender_id=sender_id, user_id=user_id, expires_at=expires_at, status='PENDING', is_active=True
            ))
        return True
    except Exception as e:
        print(f"Failed to create pending session: {e}")
        return False


# --- Settings & onboarding (WP-02) ---
#
# Read/write surface for display name, usage type, business profile, and resumable
# onboarding progress. Storage shape is the G-SCHEMA freeze (migration 0003):
# users.usage_type ENUM, users.business_profile JSON, users.onboarding_step SMALLINT.
# Signatures match the mock contract in 09-orchestration.md so callers (routes.py)
# are stable.

VALID_USAGE_TYPES = ('personal', 'business')

# Onboarding step constants — the resumable position marker. NULL/None = not started.
ONBOARDING_NAME = 0        # name offered (may have been skipped)
ONBOARDING_USAGE = 1       # usage type chosen
ONBOARDING_BIZ_NAME = 2    # business name captured
ONBOARDING_DONE = 9        # onboarding complete


def set_display_name(user_id, name):
    """Set a user's display name. Returns True on success."""
    name = (name or '').strip()
    if not name:
        return False
    try:
        with session_scope() as s:
            res = s.execute(
                update(User).where(User.id == user_id).values(display_name=name[:100])
            )
            return res.rowcount > 0
    except Exception as e:
        print(f"Failed to set display name: {e}")
        return False


def set_usage_type(user_id, usage):
    """Set a user's usage type ('personal' | 'business'). Returns True on success."""
    usage = (usage or '').strip().lower()
    if usage not in VALID_USAGE_TYPES:
        return False
    try:
        with session_scope() as s:
            res = s.execute(
                update(User).where(User.id == user_id).values(usage_type=usage)
            )
            return res.rowcount > 0
    except Exception as e:
        print(f"Failed to set usage type: {e}")
        return False


def update_business_profile(user_id, **fields):
    """Merge fields (name=, type=, currency=) into the business_profile JSON bag.
    None values are ignored; existing keys not in `fields` are preserved.
    Returns True on success."""
    clean = {k: v for k, v in fields.items() if v is not None and str(v).strip() != ''}
    if not clean:
        return False
    try:
        with session_scope() as s:
            user = s.execute(
                select(User).where(User.id == user_id)
            ).scalars().first()
            if not user:
                return False
            profile = dict(user.business_profile or {})
            for k, v in clean.items():
                profile[k] = v.strip() if isinstance(v, str) else v
            user.business_profile = profile
            return True
    except Exception as e:
        print(f"Failed to update business profile: {e}")
        return False


def set_onboarding_state(user_id, **fields):
    """Update onboarding progress. Accepts `step` (int) and/or the same profile
    fields update_business_profile takes. Returns True on success."""
    step = fields.pop('step', None)
    ok = True
    try:
        if step is not None:
            with session_scope() as s:
                res = s.execute(
                    update(User).where(User.id == user_id).values(onboarding_step=step)
                )
                ok = res.rowcount > 0
        if fields:
            ok = update_business_profile(user_id, **fields) and ok
        return ok
    except Exception as e:
        print(f"Failed to set onboarding state: {e}")
        return False


def get_onboarding_state(user_id):
    """Return the user's onboarding progress and the next field to ask for, or None
    on lookup failure. Shape:

        {'complete': bool, 'next': 'name'|'usage'|'business_name'|'business_type'|None,
         'step': int|None, 'display_name': str|None, 'usage_type': str|None,
         'business_profile': dict}

    `next` is computed from what's already on the record (the record IS the state),
    so the flow resumes at the first unanswered question. Name is skippable: once
    onboarding_step has advanced past ONBOARDING_NAME, a still-null name no longer
    blocks (we re-ask later, not in-flow)."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(User.display_name, User.usage_type, User.business_profile, User.onboarding_step)
                .where(User.id == user_id)
            ).first()
            if not row:
                return None
            display_name, usage_type, profile, step = row
            profile = profile or {}

            # Name first — unless it was already offered (step advanced) and skipped.
            if not display_name and (step is None or step < ONBOARDING_NAME + 1):
                nxt = 'name'
            elif not usage_type:
                nxt = 'usage'
            elif usage_type == 'business' and not profile.get('name'):
                nxt = 'business_name'
            elif usage_type == 'business' and not profile.get('type'):
                nxt = 'business_type'
            else:
                nxt = None

            return {
                'complete': nxt is None,
                'next': nxt,
                'step': step,
                'display_name': display_name,
                'usage_type': usage_type,
                'business_profile': profile,
            }
    except Exception as e:
        print(f"Failed to get onboarding state: {e}")
        return None


# --- Multi-channel identity + binding tokens (WP-02 / G-IDENTITY) ---

def generate_binding_token():
    """A single-use deep-link token — URL-safe and ≤64 chars (Telegram /start payload limit)."""
    return secrets.token_urlsafe(24)   # 32 chars, charset [A-Za-z0-9_-]


def binding_token_is_expired(expires_at, now=None):
    """Pure check: True if a token's expiry has passed (or is missing)."""
    if expires_at is None:
        return True
    return expires_at <= (now or datetime.utcnow())


def issue_binding_token(user_id, target_channel=None, ttl_minutes=None):
    """Mint a single-use binding token for a user (deep-link onboarding + Path B /link).
    Returns the token string, or None."""
    token = generate_binding_token()
    minutes = ttl_minutes or int(current_app.config.get("BINDING_TOKEN_TTL_MIN", 15))
    expires_at = datetime.utcnow() + timedelta(minutes=minutes)
    try:
        with session_scope() as s:
            s.add(BindingToken(token=token, user_id=user_id,
                               target_channel=target_channel, expires_at=expires_at))
        return token
    except Exception as e:
        print(f"Failed to issue binding token: {e}")
        return None


def link_channel(user_id, channel, channel_user_id):
    """Upsert a (channel, channel_user_id) → user_id link. Returns True on success."""
    try:
        with session_scope() as s:
            s.execute(
                mysql_insert(ChannelAccount)
                .values(channel=channel, channel_user_id=str(channel_user_id), user_id=user_id)
                .on_duplicate_key_update(user_id=user_id)
            )
        return True
    except Exception as e:
        print(f"Failed to link channel: {e}")
        return False


def unlink_channel(channel, channel_user_id):
    """Remove a channel link (the other channels keep working). Returns True on success."""
    try:
        with session_scope() as s:
            s.execute(
                delete(ChannelAccount).where(
                    ChannelAccount.channel == channel,
                    ChannelAccount.channel_user_id == str(channel_user_id),
                )
            )
        return True
    except Exception as e:
        print(f"Failed to unlink channel: {e}")
        return False


def redeem_binding_token(token, channel, channel_user_id):
    """Validate + consume a binding token and link the channel to its user.
    Returns the user_id (str) on success, else None."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(BindingToken).where(BindingToken.token == token, BindingToken.used_at.is_(None))
            ).scalars().first()
            if not row or binding_token_is_expired(row.expires_at):
                return None
            row.used_at = func.now()
            user_id = row.user_id
            s.execute(
                mysql_insert(ChannelAccount)
                .values(channel=channel, channel_user_id=str(channel_user_id), user_id=user_id)
                .on_duplicate_key_update(user_id=user_id)
            )
            return str(user_id)
    except Exception as e:
        print(f"Failed to redeem binding token: {e}")
        return None


def resolve_channel_user(channel, channel_user_id):
    """Resolve a (channel, channel_user_id) to a verified user dict, or None.
    Falls back to the legacy ``whatsapp_accounts`` table for WhatsApp rows predating WP-02."""
    try:
        with session_scope() as s:
            row = s.execute(
                select(User.id, User.phone_number, User.display_name)
                .join(ChannelAccount, User.id == ChannelAccount.user_id)
                .where(
                    ChannelAccount.channel == channel,
                    ChannelAccount.channel_user_id == str(channel_user_id),
                    User.is_verified.is_(True),
                )
            ).first()
            if row:
                return _user_dict(row)
    except Exception as e:
        print(f"Failed to resolve channel user: {e}")
    if channel == "whatsapp":          # legacy fallback (pre-channel_accounts rows)
        return get_user_by_sender(channel_user_id)
    return None


def resolve_user_by_address(address):
    """Resolve a namespaced sender (``wa:..`` / ``tg:..``, or a bare legacy phone) to a user dict."""
    from app.channels.base import split_address
    channel, native = split_address(address)
    if channel is None:                # bare legacy WhatsApp sender id
        return get_user_by_sender(native)
    return resolve_channel_user(channel, native)
