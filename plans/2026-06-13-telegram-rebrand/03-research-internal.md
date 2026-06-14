<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 03 — Internal research

Existing assets, prior work, current constraints relevant to Add Telegram as a second channel alongside WhatsApp (channel abstraction + Telegram bot + web deep-link onboarding), update the landing to dual WhatsApp/Telegram CTAs, and execute a total visual rebrand (keeping the TaLi name).. Cite by `path:line` (or by document title + section for non-file references).

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-13T17:59:55Z -->
### The channel seam is already shallow — the agents are channel-agnostic

- WhatsApp webhook entry: `app/web/routes.py:349` `/webhook` (GET verify + POST). `handle_authenticated_message(sender, text, session, message_id)` at `routes.py:334`; it calls `AgentRouter(user_id, sender_id).route(text, message_id)` (`:342-343`) and `send_reply(sender, reply)` (`:346`). The reply is a plain string — **channel-agnostic already**.
- WhatsApp transport to lift: `app/web/whatsapp.py` — `send_reply`, `send_document`, and HMAC verify (`X-Hub-Signature-256`). These become `app/channels/whatsapp.py` behind the `Channel` interface.
- The Band gateway (`app/agents/agent_router.py`) takes `(user_id, sender_id)` and returns a reply string — it does **not** care about the channel; only the `sender_id` is WhatsApp-shaped today.

### `sender_id` is the WhatsApp phone everywhere — namespacing touches these

- `sender_id` (the phone) is the key in `auth.get_active_session(sender_id)`, `webhook_events.sender_id`, `pending_confirmations.sender_id`, and is passed into every agent. Namespacing to `wa:<phone>` / `tg:<chat_id>` (WP-02) needs a back-compat lookup + a one-time backfill of existing rows.
- Auth: `app/auth.py` — `get_active_session`, `get_user_by_sender` / `get_user_by_phone`, the OTP flow; `sessions` keyed by sender.
- Registration: `app/web/web_routes.py` `/register` + `/verify-otp` — phone + OTP via a WhatsApp template. Telegram will reuse the register page to **issue a binding token** instead.

### Brand surfaces to restyle (token-first)

- Landing: `app/templates/landing.html` + `app/static/landing.css`; design system at `design/tali/shared/tali.css`; marketing/legal at `design/tali/commercial/*` + `design/tali/legal/*`.
- Scroll-narrative inputs already exist: `design/landing-wireframes/A-the-conversation.html`, `B-the-ledger.html`, `C-the-numbers.html` — reusable as the rebrand's scroll story.
- In-app templates: `app/templates/register.html`, `verify.html`, `error.html`, `_sprite.html`.

### Config + migrations

- `app/config.py` carries the WhatsApp creds (`ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN`, `META_APP_SECRET`); add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` alongside.
- Migrations: `migrations/versions/0001..0004` exist; next is **`0005`** for `channel_accounts` + `binding_tokens` (WP-02).
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you went looking for inside the existing system / org / archive and why. The research action does not touch this section.
