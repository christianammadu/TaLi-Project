<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Telegram channel + dual-CTA landing + total rebrand — TaLi

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-06-13 -->
Add Telegram as a second channel alongside WhatsApp (channel abstraction + Telegram bot + web deep-link onboarding), update the landing to dual WhatsApp/Telegram CTAs, and execute a total visual rebrand (keeping the TaLi name).
<!-- groundwork:auto:end goal -->

## Context

_Why now, what changed, what's at stake._

TaLi works over WhatsApp, but the **WhatsApp Business API is unpaid**: a single test number, a webhook token that expires, and no real multi-user testing — a poor footing for a hackathon demo and for onboarding real users. **Telegram's Bot API is free, instant, multi-user, and has a stable webhook**, so adding it as a second channel de-risks the demo and broadens reach immediately.

Three things ship together:
1. **Telegram channel** alongside WhatsApp, behind a channel abstraction so the Band agent layer is untouched.
2. **Dual-CTA landing** — "Continue on WhatsApp" + "Continue on Telegram".
3. **Total visual rebrand** (keep the **TaLi** name; new logo, palette, type, voice) — direction chosen from 3 explored options (see `designs/`).

**Locked decisions (this plan):** keep the name *TaLi*; Telegram onboarding via a **web deep-link token** (no phone/OTP in Telegram); explore **3 rebrand directions** then lock one.

## Architecture

_The shape of the solution at one zoom-out level._

A **channel abstraction** sits in front of the existing Band gateway. The gateway + four agents stay **channel-agnostic** (they already just produce a reply string).

```
WhatsApp Cloud API ─┐                                  ┌─ WhatsAppChannel.send_text/send_document
                    ├─▶ /webhook/<channel> ─▶ normalize ─▶ AgentRouter (Band room) ─▶ reply ─▶ originating channel
Telegram Bot API  ──┘     (HMAC / secret)     to (channel, sender, text, msg_id)               └─ TelegramChannel.send_text/send_document
```

- **`Channel` interface** (`app/channels/base.py`): `parse_inbound(request) -> InboundMessage{channel, sender, text, message_id, attachment?}`, `send_text(sender, text)`, `send_document(sender, file, caption)`, `verify(request)`. Implementations: `whatsapp.py` (lifted from today's `app/web/whatsapp.py`), `telegram.py` (new).
- **Channel-namespaced identity**: `sender` becomes `wa:<phone>` / `tg:<chat_id>`. A `channel_accounts` table maps `(channel, channel_user_id) → user_id`; one user can link both. Sessions key off the namespaced sender.
- **Telegram onboarding (web deep-link):** the web register page issues a short-lived **binding token**; the user taps `t.me/<bot>?start=<token>`; the bot's `/start <token>` resolves the token → binds `tg:<chat_id>` to the user + opens a session. **No phone/OTP in Telegram.**
- **Cross-channel linking — Path B (locked):** a user adds their *second* channel **from inside the channel they're already on**, using the same one-time-token primitive (the current channel is the auth anchor — no web detour). `/link telegram` in WhatsApp replies with a `t.me/<bot>?start=<token>` deep-link; `/link whatsapp` in Telegram replies with a `wa.me/<number>?text=LINK-<token>` link. Redeeming the token adds a second `channel_accounts` row pointing at the **same `user_id`**, so both channels share one ledger. (A web "Connected channels" page is a secondary path, not required.)
- **Landing**: a `Continue on WhatsApp` (`wa.me/<number>`) and `Continue on Telegram` (`t.me/<bot>`) CTA pair, on the rebranded page.
- **Rebrand**: new identity tokens in `design/tali/shared/tali.css` + `app/static/`, applied across marketing/legal/in-app templates and the bot welcome copy.

### Shared state contract

| Field | Type | Writer | Readers |
|---|---|---|---|
| `InboundMessage` (channel, sender, text, message_id) | dataclass | the channel adapter (`parse_inbound`) | gateway |
| namespaced `sender` (`wa:<phone>` / `tg:<chat_id>`) | string | channel adapters | auth, gateway, agents, `webhook_events` |
| `channel_accounts(channel, channel_user_id) → user_id` | table | onboarding (WP-02/04) | `auth.get_active_session`, gateway |
| `binding_tokens(token → user_id, expires_at)` | table | web register (WP-04) | bot `/start` handler |
| outbound reply transport | `Channel.send_text/send_document` | gateway/webhook | the originating channel |
| locked brand tokens (`--brand-*`, logo, type) | CSS/asset | design lock `G-BRAND` (WP-06) | all templates + landing |

## Phases

> Detail scales with proximity. Phase 1 detailed; Phase 2 sketched; Phases 3–4 stubbed.

### Phase 1 — Channel abstraction + identity (foundations)

- **`WP-01` → `G-CHANNEL-CONTRACT`**: define `app/channels/base.py` (`Channel` + `InboundMessage`) and refactor today's WhatsApp send/verify out of `app/web/whatsapp.py` into `app/channels/whatsapp.py`; namespace its sender as `wa:<phone>`. The gateway calls the channel, not WhatsApp directly.
- **`WP-02` → `G-IDENTITY`**: Alembic migration for `channel_accounts` + `binding_tokens`; make `auth` sessions key off the namespaced sender with back-compat for existing WhatsApp rows.
- In parallel: the **design exploration** (3 directions → lock `G-BRAND`).

### Phase 2 — Telegram channel + deep-link onboarding (sketch)

`TelegramChannel` (Bot API `sendMessage`/`sendDocument`, `setWebhook`, update parsing) at `/webhook/telegram` (`WP-03`, dep `G-CHANNEL-CONTRACT`); web-issued binding token → bot `/start <token>` binds + opens a session (`WP-04`, dep `G-IDENTITY`+`WP-03`); wire both channels into the gateway and reply on the originating channel (`WP-05`).

### Phase 3 — Rebrand + dual-CTA landing (stub)

Apply the locked direction: brand tokens/logo/type (`WP-06`, dep `G-BRAND`); rebranded landing + marketing/legal with the dual WhatsApp/Telegram CTA, scroll-driven narrative where it fits (`WP-07`); in-app templates + bot welcome copy (`WP-08`).

### Phase 4 — Setup doc + polish (stub)

Telegram setup/integration doc, `.env`, deploy notes, demo update (`WP-09`). See `docs/telegram-setup.md` (drafted now).

## Schema / contract

The freeze artifacts:
- **`G-CHANNEL-CONTRACT`** — `Channel` interface (`parse_inbound`/`send_text`/`send_document`/`verify`) + the `InboundMessage` shape + the `wa:`/`tg:` sender namespacing. Frozen by WP-01 before the Telegram adapter is built.
- **`G-IDENTITY`** — `channel_accounts` + `binding_tokens` schema + channel-scoped session lookup (with WhatsApp back-compat). Frozen by WP-02 before onboarding.
- **`G-BRAND`** — the locked rebrand direction (one of `designs/D-01..D-03`): palette, type scale, logo, voice. Frozen by the design step before any template is restyled.

## Critical files

### `tali/` (this repo)
- `app/channels/base.py` — **new** `Channel` + `InboundMessage` (WP-01).
- `app/channels/whatsapp.py` — **new**, lifted from `app/web/whatsapp.py` (send/verify) (WP-01).
- `app/channels/telegram.py` — **new** Telegram Bot API adapter (WP-03).
- `app/web/whatsapp.py` — **shrink** to a thin wrapper over the channel (or remove once callers move) (WP-01/05).
- `app/web/routes.py` — **extend** `/webhook` to be channel-aware + add `/webhook/telegram`; reply via the originating channel (WP-05).
- `app/web/web_routes.py` — register page **issues a Telegram binding token** + shows both CTAs (WP-04/07).
- `app/auth.py` — **channel-scoped sessions** + binding-token resolve (WP-02/04).
- `migrations/versions/0005_*` — **new** `channel_accounts` + `binding_tokens` (WP-02).
- `app/agents/agent_router.py` — minimal: accept the namespaced sender (gateway already channel-agnostic) (WP-05).
- `design/tali/shared/tali.css`, `app/static/landing.css`, `app/static/style.css` — **rebrand** tokens (WP-06).
- `app/templates/*`, `design/tali/**` — **restyle** + dual CTA (WP-07/08).
- `.env.example`, `app/config.py` — **add** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET` (WP-03).

## Reuse map — what we lift, reimplement, or drop

| Concern | Strategy | Source / target | Notes |
|---|---|---|---|
| Band agent layer / gateway | **Reuse as-is** | already channel-agnostic (returns a reply string) | only the sender id is namespaced |
| WhatsApp send/verify | **Lift** | `app/web/whatsapp.py` → `app/channels/whatsapp.py` behind `Channel` | no behaviour change |
| OTP/session (WhatsApp) | **Reuse** | existing phone+OTP path stays for WhatsApp | Telegram uses deep-link instead |
| Telegram adapter | **Build fresh** | `app/channels/telegram.py` (WP-03) | Bot API over HTTP; no SDK needed |
| Deep-link onboarding | **Build fresh** | `binding_tokens` + `/start` handler (WP-04) | reuse the web register page |
| Brand system | **Rebrand** | `design/tali/shared/tali.css` + templates | from the locked `G-BRAND` direction |
| Landing wireframes | **Reuse as input** | `design/landing-wireframes/*` inform the scroll narrative | rebuilt under the new brand |

## Renderer / adapter contracts

The pluggable seam is the **`Channel`** adapter (`G-CHANNEL-CONTRACT`): `parse_inbound`, `send_text`, `send_document`, `verify`. WhatsApp + Telegram implement it; the gateway depends only on this surface. Frozen by WP-01 before WP-03/05.

## Risks + alternatives

- **WhatsApp unpaid / expiring webhook (the motivator).** Single test number, token expiry → unreliable demo. *Mitigation:* Telegram becomes the primary demo channel; WhatsApp stays wired but optional.
- **Identity migration risk.** Namespacing `sender` (`wa:`/`tg:`) could break existing WhatsApp sessions/`webhook_events`. *Mitigation:* WP-02 migration backfills the `wa:` prefix + a back-compat lookup; verify against existing rows.
- **Rebrand scope creep.** A total rebrand can sprawl. *Mitigation:* lock ONE direction (`G-BRAND`) from the 3 explored before any template is touched; restyle via tokens, not per-page rewrites.
- **Telegram webhook needs a public HTTPS URL** (same constraint as WhatsApp). *Mitigation:* ngrok for dev; the deploy step sets the webhook; `setWebhook` is a single call (easier than Meta).
- **Document delivery differs.** Statements send files; `sendDocument` (Telegram, multipart) vs WhatsApp media upload differ. *Mitigation:* the `Channel.send_document` contract abstracts it; test both.
- **Bot spam / unauthenticated chats.** Anyone can message a public bot. *Mitigation:* unbound chats get only the onboarding deep-link prompt; the gateway requires a bound session before processing.

## ID registry

The full ID registry is in `.groundwork.json.ids`. Local cross-reference index:

<!-- groundwork:auto:start ids -->
<!-- last_action: review · 2026-06-13T17:59:55Z -->
| ID | Kind | Origin | Summary |
|---|---|---|---|
| G-CHANNEL-CONTRACT | freeze gate | WP-01 | `Channel` interface (parse_inbound/send_text/send_document/verify) + `InboundMessage` + `wa:`/`tg:` sender namespacing |
| G-IDENTITY | freeze gate | WP-02 | `channel_accounts` + `binding_tokens` + channel-scoped sessions (WhatsApp back-compat) |
| G-BRAND | freeze gate | design lock | the locked rebrand direction (palette / type / logo / voice) from `designs/D-01..D-03` |
| WP-01 … WP-09 | work packages | 05-tracking.md | see `05-tracking.md` + `09-orchestration.md` |
| D-01 … D-03 | designs | `designs/` | 3 rebrand + dual-CTA landing directions (huashu); lock one → `G-BRAND` |
<!-- groundwork:auto:end ids -->

## Verification

### Phase 1 verification
1. `Channel` interface frozen; WhatsApp adapter passes a parse_inbound→send_text round-trip test; sender is namespaced `wa:<phone>`.
2. Migration creates `channel_accounts` + `binding_tokens`; an existing WhatsApp user still resolves a session via the back-compat lookup.
3. 3 rebrand directions rendered in `designs/`; one locked as `G-BRAND`.

### Phase 2 verification (sketch)
1. A message to the Telegram bot from an **unbound** chat returns the onboarding deep-link prompt (no processing).
2. Web register → tap `t.me/<bot>?start=<token>` → the bot binds the chat and replies "linked"; a subsequent "Sold rice 5000" records end-to-end and replies **in Telegram**.
3. The same build still serves WhatsApp unchanged.

### Phase 3 verification (sketch)
1. Landing shows both CTAs; each deep-links to the right channel; the page is on the new brand.
2. Marketing/legal/in-app templates + bot welcome all reflect the locked brand (grep shows no old tokens left).
