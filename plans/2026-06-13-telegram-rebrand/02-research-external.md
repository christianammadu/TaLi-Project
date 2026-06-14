<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 02 — External research

Outside research backing Add Telegram as a second channel alongside WhatsApp (channel abstraction + Telegram bot + web deep-link onboarding), update the landing to dual WhatsApp/Telegram CTAs, and execute a total visual rebrand (keeping the TaLi name).. Cite every claim with a URL + access date. Hand-authored sections live between fences; the research action only writes inside.

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-13T17:59:55Z -->
### Telegram Bot API — free, multi-user, stable webhook

- **Create a bot** via **@BotFather** (`/newbot`) → returns a **bot token** + lets you set the username. Free, instant, no business verification (unlike WhatsApp Cloud API).
- **Webhook:** `setWebhook(url, secret_token)` — Telegram POSTs `Update` objects to your HTTPS URL; verify each with the **`X-Telegram-Bot-Api-Secret-Token`** header. One call to set; **no expiry**. Dev alternative: long-polling `getUpdates` (no public URL needed).
- **Send:** `POST https://api.telegram.org/bot<token>/sendMessage` `{chat_id, text, parse_mode}`; **`sendDocument`** (multipart) for statements/files. Markdown/HTML supported.
- **Deep-link:** `https://t.me/<bot_username>?start=<payload>` opens the bot; tapping **Start** sends `/start <payload>` as the first message. Payload **≤64 chars, `[A-Za-z0-9_-]`** — ideal for a one-time binding token.
- **Identity:** each update carries `message.chat.id` (stable per chat) + `message.from.id` (user). Use `chat.id` as `channel_user_id`.
- **Cost/limits:** no per-message cost; ~30 msg/s overall, ~1 msg/s per chat.

### Why add Telegram (vs the WhatsApp blocker)

WhatsApp Cloud API on the free tier: business verification, single test number, 24-hour customer-service window, template approval, and a webhook token that expires — fragile for a demo and for real onboarding. Telegram has none of that: the bot is live in minutes, multi-user immediately, with a stable webhook. So Telegram becomes the **primary demo + onboarding channel**; WhatsApp stays wired but optional.

### Dual-channel architecture pattern

Standard "messaging gateway": keep the agent layer channel-agnostic; put a thin **Channel adapter** per platform that (a) parses an inbound payload into a normalized message and (b) sends text/documents. Namespace identities per channel (`wa:` / `tg:`) so one account can link both.

### Deep-link account binding (vs OTP)

Telegram-native onboarding avoids SMS/OTP entirely: issue a **single-use, short-TTL token** on the web, embed it in the `t.me/...?start=` deep-link, resolve it on `/start`, and bind `chat_id → user`. Cleaner than asking for a phone number inside Telegram.

### Rebrand (keep the name)

A total visual rebrand that keeps the *TaLi* name = new logo, palette, type scale, motion, and voice. Implement as **design tokens** (CSS variables) so templates restyle without per-page rewrites. Explore 2–3 directions and **lock one** before applying, to avoid scope creep.
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you specifically went looking for and why. The research action does not touch this section. Keep it terse; the findings above are the substance.

## Sources

<!-- groundwork:auto:start sources -->
<!-- last_action: research · 2026-06-13T17:59:55Z -->
1. Telegram Bot API reference — https://core.telegram.org/bots/api (accessed 2026-06-13)
2. Bots: BotFather + features — https://core.telegram.org/bots/features (accessed 2026-06-13)
3. Deep linking (`?start=` payload) — https://core.telegram.org/bots/features#deep-linking (accessed 2026-06-13)
4. setWebhook + secret token — https://core.telegram.org/bots/api#setwebhook (accessed 2026-06-13)
5. sendMessage / sendDocument — https://core.telegram.org/bots/api#sendmessage (accessed 2026-06-13)
6. WhatsApp Cloud API (limits / pricing / verification) — https://developers.facebook.com/docs/whatsapp/cloud-api (accessed 2026-06-13)
<!-- groundwork:auto:end sources -->
