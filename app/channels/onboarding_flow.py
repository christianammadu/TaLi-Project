"""Shared in-chat onboarding flow for WhatsApp and Telegram."""

from app.auth import (
    ONBOARDING_DONE,
    get_onboarding_state,
    set_base_currency,
    set_display_name,
    set_onboarding_state,
    set_usage_type,
    update_business_profile,
)

BUSINESS_TYPES = {'1': 'Retail / Shop', '2': 'Food / Restaurant', '3': 'Services', '4': 'Other'}
SKIP_WORDS = {'skip', '/skip'}


def _b(text, markdown):
    return f"*{text}*" if markdown else text


def _i(text, markdown):
    return f"_{text}_" if markdown else text


def _currency_code(value):
    code = (value or "").strip().upper()
    return code if len(code) == 3 and code.isalpha() else None


def prompt_for_state(state, markdown=True):
    """Return the next onboarding prompt for a state, or None when complete."""
    nxt = state["next"]
    if nxt == "name":
        return (
            f"👋 {_b('Welcome to TaLi!', markdown)}\n"
            "I'll keep your books right here in the chat.\n\n"
            f"First, what should I call you? (or reply {_b('skip', markdown)})"
        )
    if nxt == "usage":
        return (
            f"Are you using TaLi for {_b('personal', markdown)} or {_b('business', markdown)} records?\n\n"
            f"Reply {_b('1', markdown)} for Personal\n"
            f"Reply {_b('2', markdown)} for Business"
        )
    if nxt == "currency":
        current = state.get("base_currency") or "NGN"
        return (
            f"What currency should I use by default?\n\n"
            f"Reply with a 3-letter code like {_b('NGN', markdown)}, {_b('USD', markdown)}, or {_b('GHS', markdown)}.\n"
            f"Current default: {_b(current, markdown)}"
        )
    if nxt == "business_name":
        return f"Great, let's set up your business. What's the {_b('business name', markdown)}?"
    if nxt == "business_type":
        return (
            "And what kind of business is it?\n\n"
            "1. Retail / Shop\n"
            "2. Food / Restaurant\n"
            "3. Services\n"
            "4. Other"
        )
    return None


def completion_message(state, markdown=True):
    name = state.get("display_name")
    greet = f"All set, {_b(name, markdown)}!" if name else "All set!"
    biz = (state.get("business_profile") or {}).get("name")
    line2 = f"{_b(biz, markdown)} is ready to go.\n\n" if biz else "\n"
    balance_example = "What's my balance?"
    return (
        f"✅ {greet}\n{line2}"
        "Just tell me what happened, in your own words:\n"
        f"• {_i('Sold rice 5000', markdown)}\n"
        f"• {_i('Bought fuel 2k', markdown)}\n"
        f"• {_i(balance_example, markdown)}\n\n"
        "Type help for everything I can do, or settings to make changes."
    )


def send_next_onboarding(user_id, send_text, markdown=True, error_text=None):
    """Send the next onboarding question. Returns True when onboarding is complete."""
    state = get_onboarding_state(user_id)
    if state is None:
        send_text(error_text or "Something went wrong. Please try again.")
        return False

    prompt = prompt_for_state(state, markdown=markdown)
    if prompt:
        send_text(prompt)
        return False

    set_onboarding_state(user_id, step=ONBOARDING_DONE)
    send_text(completion_message(state, markdown=markdown))
    return True


def handle_onboarding_answer(user_id, text, send_text, markdown=True):
    """Process one onboarding answer. Returns True when the message was consumed."""
    state = get_onboarding_state(user_id)
    if state is None or state["complete"]:
        return False

    answer = (text or "").strip()
    low = answer.lower()
    nxt = state["next"]

    if nxt == "name":
        if low in SKIP_WORDS:
            set_onboarding_state(user_id, step=1)
        else:
            set_display_name(user_id, answer)
    elif nxt == "usage":
        if low in ("1", "personal", "p"):
            set_usage_type(user_id, "personal")
            set_onboarding_state(user_id, step=2)
        elif low in ("2", "business", "b"):
            set_usage_type(user_id, "business")
            set_onboarding_state(user_id, step=2)
        else:
            send_text(f"Please reply {_b('1', markdown)} for Personal or {_b('2', markdown)} for Business.")
            return True
    elif nxt == "currency":
        code = _currency_code(answer)
        if not code:
            send_text(f"Please reply with a 3-letter currency code, e.g. {_b('NGN', markdown)} or {_b('USD', markdown)}.")
            return True
        set_base_currency(user_id, code)
        set_onboarding_state(user_id, step=3)
    elif nxt == "business_name":
        update_business_profile(user_id, name=answer)
        set_onboarding_state(user_id, step=4)
    elif nxt == "business_type":
        biz_type = BUSINESS_TYPES.get(low) or (answer if len(answer) <= 50 else None)
        if not biz_type:
            send_text("Please reply 1, 2, 3, or 4 to pick a category.")
            return True
        update_business_profile(user_id, type=biz_type)
        set_onboarding_state(user_id, step=ONBOARDING_DONE)

    send_next_onboarding(user_id, send_text, markdown=markdown)
    return True
