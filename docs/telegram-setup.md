# Telegram bot — setup & integration guide

How to stand up the TaLi Telegram channel end-to-end. The **plan** for this work is
[`plans/2026-06-13-telegram-rebrand/`](../plans/2026-06-13-telegram-rebrand/); this doc is
the operator/dev guide that WP-09 finalises. **No secrets in this file** — the bot token
lives in `.env` (gitignored); keep operator notes in `docs/credentials-setup.local.md`.

---

## 0. Prerequisites (app up + DB migrated)

Get the app itself running first — the Telegram channel rides on it:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the values (see §5 + the rest of .env)
alembic upgrade head            # create/upgrade the MySQL schema
python run.py                   # serves on http://localhost:5000
```
You need a **public HTTPS URL** for Telegram to reach the webhook — a deployed host, or
`ngrok http 5000` in dev (§2). Set `APP_BASE_URL` to that URL.

## 1. Create the bot (BotFather)

1. In Telegram, message **@BotFather** → `/newbot`.
2. Give it a display name and a **username** ending in `bot` (e.g. `TaLiBookkeeperBot`).
3. BotFather returns a **bot token** like `123456:ABC-DEF...`. Treat it like a password.
4. Optional polish: `/setdescription`, `/setabouttext`, `/setuserpic`, and `/setcommands`
   (e.g. `start - Link your account`, `help - What I can do`).

Put these in `.env`:
```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...        # from BotFather
TELEGRAM_BOT_USERNAME=TaLiBookkeeperBot     # without the @ ; feeds the landing CTA + deep-link
TELEGRAM_WEBHOOK_SECRET=<random hex>         # python -c "import secrets;print(secrets.token_hex(16))"
```

## 2. Point Telegram at our webhook

Telegram pushes every message to an HTTPS URL you register **once** (no expiry — unlike
the WhatsApp token). The endpoint is `POST /webhook/telegram` (WP-03).

```bash
# Public URL: a deployed host, or ngrok for dev:  ngrok http 5000
BASE=https://<your-host>            # e.g. https://abc123.ngrok-free.app
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=$BASE/webhook/telegram" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
# verify:
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```
Every incoming update carries the header `X-Telegram-Bot-Api-Secret-Token`; the adapter
rejects any request whose value ≠ `TELEGRAM_WEBHOOK_SECRET`.

> **Dev without a public URL:** use long-polling (`getUpdates`) instead of a webhook — a small
> poller loop hits the same gateway. The deployed setup uses the webhook above.

**Deploy:** the webhook registration is **persistent** — Telegram keeps pushing to that URL
with no expiry, so you only re-run `setWebhook` when the host/URL changes (new deploy domain,
rotated `TELEGRAM_WEBHOOK_SECRET`). The public landing's **Continue on Telegram** / **Continue
on WhatsApp** buttons (WP-07) are built from `TELEGRAM_BOT_USERNAME` and `WHATSAPP_PUBLIC_NUMBER`,
so set both in the deployed `.env` for the CTAs to deep-link correctly.

## 3. How onboarding works (web deep-link — no phone/OTP)

```
Web /register  ──issues──▶  binding_tokens(token, user_id, expires_at)
                              │
   landing/register shows:  t.me/<TELEGRAM_BOT_USERNAME>?start=<token>
                              │ user taps → Telegram sends "/start <token>"
/webhook/telegram  ──/start <token>──▶ resolve token → bind tg:<chat_id> → channel_accounts → open session
                              │
                         bot replies "✅ Linked! Now just tell me what happened — like 'Sold rice 5000'."
```
- Tokens are single-use, short-TTL, `[A-Za-z0-9_-]` ≤ 64 chars (Telegram's `start` payload limit).
- An **unbound** chat (any stranger messaging the bot) only ever gets the deep-link prompt; the
  gateway requires a bound session before it processes anything.

## 3a. Linking a second channel — Path B (from inside the chat)

A user who already uses one channel adds the other **without touching the web** — the
channel they're already on is the auth anchor:

```
On Telegram, want to add WhatsApp:
   /link whatsapp  → bot replies:  "Add WhatsApp →  wa.me/<tali-number>?text=LINK-<token>"
   tap → WhatsApp opens with a prefilled "LINK-<token>" → Send
   → WhatsApp webhook detects LINK-<token>, redeems it → channel_accounts(whatsapp:<phone>) → same user_id

On WhatsApp, want to add Telegram:
   /link telegram  → bot replies:  "Add Telegram →  t.me/<bot>?start=<token>"
   tap → Start → /start <token> redeemed → channel_accounts(telegram:<chat_id>) → same user_id
```

Both channels now point at one `user_id`, so they share one ledger (record on WhatsApp,
pull a statement on Telegram). Same token rules as §3 (single-use, short-TTL). `/unlink <channel>`
removes that one row; the other keeps working. A web "Connected channels" page is optional.

## 4. Sending replies

The Telegram `Channel` adapter implements the same surface as WhatsApp:
- text → `POST https://api.telegram.org/bot<token>/sendMessage` `{chat_id, text, parse_mode}`
- statements/files → `sendDocument` (multipart).

The agents are unchanged — they return a reply string; the gateway sends it via whichever
channel the message arrived on.

## 5. Env summary
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_SECRET=
APP_BASE_URL=https://<your-host>     # used to build the deep-link + setWebhook URL
```

## 6. Smoke test
1. `setWebhook` (step 2) → `getWebhookInfo` shows your URL, no errors.
2. Register on the web → tap the `t.me/...?start=` link → bot replies "Linked".
3. Send **`Sold rice 5000`** in Telegram → a confirmation like `Got it ✓ Recorded a ₦5,000 sale`.
4. Send **`finops`** → spend-by-provider report. Send a stranger message from another account →
   only the deep-link prompt (no processing).

## 7. Notes / caveats
- Rate limits: ~30 msg/s overall, ~1 msg/s per chat — fine for our volume.
- One bot serves all users (multi-user out of the box) — the key advantage over the unpaid
  WhatsApp test number.
- Group chats: out of scope for v1 (1:1 chats only); the adapter ignores non-private chats.
