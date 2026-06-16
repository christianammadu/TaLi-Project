"""Telegram webhook — WP-03/04.

Verifies the secret token, normalizes the update, handles onboarding/link commands
(Path B), and routes a bound user's message through the Band gateway, replying in
Telegram. Unbound chats only ever get the onboarding prompt. (Unifying the WhatsApp
route + the document/dead-letter reply paths behind the channel is WP-05.)
"""

from flask import Blueprint, jsonify, request

from app.channels import onboarding
from app.channels.account_settings import render_settings, apply_setting
from app.channels.base import split_address
from app.channels.telegram import TelegramChannel

telegram_bp = Blueprint("telegram", __name__)
_tg = TelegramChannel()
_SUPPRESS = ("__DUPLICATE_DROP__", "__ERROR_HANDLED_SAGA__", "__ASYNC_STARTED__")


@telegram_bp.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    if not _tg.verify(request):
        return "forbidden", 403
    msg = _tg.parse_inbound(request)
    if not msg:
        return jsonify(ok=True)          # non-message / non-private update — ack and ignore

    channel, native = split_address(msg.sender)

    # 1. Onboarding + Path B link commands (/start, /link, /unlink, /help).
    if msg.command:
        reply = onboarding.handle_command(channel, native, msg.command, msg.command_arg)
        if reply:
            if msg.command == "share_contact" and reply.startswith("✅"):
                remove_kb = {"remove_keyboard": True}
                _tg.send_text(msg.sender, reply, reply_markup=remove_kb)
            elif reply == onboarding.onboarding_prompt():
                kb = {
                    "keyboard": [[{"text": "📱 Share Contact", "request_contact": True}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
                _tg.send_text(msg.sender, reply, reply_markup=kb)
            else:
                _tg.send_text(msg.sender, reply)
        return jsonify(ok=True)

    # 1b. Friendly bare "help"/"menu" (no slash) → the same command/capability list.
    if msg.text.strip().lower() in ("help", "menu"):
        _tg.send_text(msg.sender, onboarding.help_text(channel))
        return jsonify(ok=True)

    # 2. Must be a bound user to do anything else.
    user = onboarding.resolve(channel, native)
    if not user:
        kb = {
            "keyboard": [[{"text": "📱 Share Contact", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        _tg.send_text(msg.sender, onboarding.onboarding_prompt(), reply_markup=kb)
        return jsonify(ok=True)

    # 3. Bound chat: auto-renew the session (the bind is the trust anchor), then run the gateway.
    from app.auth import get_active_session, open_session
    if not get_active_session(msg.sender):
        open_session(msg.sender, user["id"])

    # 3b. Settings menu + "set <field> <value>" edits (same surface as WhatsApp).
    low = msg.text.strip().lower()
    if low in ("settings", "/settings"):
        _tg.send_text(msg.sender, render_settings(user["id"]))
        return jsonify(ok=True)
    if low.startswith("set "):
        _tg.send_text(msg.sender, apply_setting(user["id"], msg.text))
        return jsonify(ok=True)

    from app.agents.agent_router import AgentRouter
    reply = AgentRouter(user_id=user["id"], sender_id=msg.sender).route(msg.text, msg.message_id)
    if reply and reply not in _SUPPRESS:
        _tg.send_text(msg.sender, reply)
    return jsonify(ok=True)
