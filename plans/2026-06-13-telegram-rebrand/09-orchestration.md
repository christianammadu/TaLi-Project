# Telegram channel + dual-CTA landing + total rebrand — implementation orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**. Source of truth: `05-tracking.md`.

> ⚠️ **Planning artifact only — do not implement without the user's say-so.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint dirs. Two independent tracks — **channel** (`app/channels/`, `app/web/`, `app/auth.py`, migrations) and **rebrand** (`design/`, `app/static/`, `app/templates/`) — touch mostly disjoint files, so the tracks run in parallel.
- **Orchestrator** owns `05` checkboxes; subagents own one WP each. Branch-per-WP, merge in wave order. Worktrees recommended for the two parallel tracks.
- **Three freeze gates** precede the dependent work and are independent of each other (Wave 0).

## Freeze gates (hard)

| Gate | WP | Why it gates | Sign-off check |
|---|---|---|---|
| `G-CHANNEL-CONTRACT` | WP-01 | the Telegram adapter (WP-03) + gateway wiring (WP-05) build against the `Channel` seam | WhatsApp adapter round-trips `parse_inbound`→`send_text`; interface frozen |
| `G-IDENTITY` | WP-02 | onboarding (WP-04) needs the multi-channel identity tables + lookup | migration up/down clean; existing `wa:` user resolves; `(channel,id)` lookup works |
| `G-BRAND` | design lock | every restyle WP (06/07/08) depends on the locked direction | one of `designs/D-01..D-03` locked; palette/type/logo/voice fixed |

## Work-package matrix

| WP | Title | Wave | Depends on | Output |
|---|---|---|---|---|
| WP-01 | Channel adapter interface + WhatsApp refactor | 0 | — | `G-CHANNEL-CONTRACT`; `app/channels/{base,whatsapp}.py` |
| WP-02 | Multi-channel identity + binding tokens | 0 | — | `G-IDENTITY`; `0005` migration |
| WP-03 | Telegram channel adapter | 1 | G-CHANNEL-CONTRACT | `app/channels/telegram.py` + `/webhook/telegram` |
| WP-04 | Telegram deep-link onboarding | 2 | G-IDENTITY, WP-03 | token → `/start` bind + session |
| WP-05 | Wire both channels into the gateway | 2 | WP-01, WP-03 | channel-aware `/webhook`; reply on origin channel |
| WP-06 | Rebrand design system | 1 | G-BRAND | brand tokens/logo/type |
| WP-07 | Rebranded landing + dual WA/TG CTA | 2 | WP-06 | landing + marketing/legal |
| WP-08 | Rebrand in-app templates + bot welcome | 2 | WP-06 | register/verify/error + welcome copy |
| WP-09 | Telegram setup doc + deploy + demo | 3 | WP-03, WP-04 | `docs/telegram-setup.md` |

### Wave plan
- **Wave 0 (parallel):** WP-01, WP-02, + design lock (`G-BRAND`).
- **Wave 1:** WP-03 (needs G-CHANNEL-CONTRACT) ‖ WP-06 (needs G-BRAND).
- **Wave 2:** WP-04, WP-05, WP-07, WP-08.
- **Wave 3:** WP-09.

### Intra-repo isolation (disjoint scopes)
- Channel track: `app/channels/`, `app/web/routes.py`, `app/web/whatsapp.py`, `app/auth.py`, `migrations/`, `app/config.py`, `.env.example`.
- Rebrand track: `design/`, `app/static/`, `app/templates/`. (WP-08 touches `app/templates/register|verify|error`; WP-07 touches `landing|features|pricing|legal` — split by file.)

## Mock contracts (so the tracks don't serialise)
- **`G-CHANNEL-CONTRACT` mock:** a fake `Channel` (in-memory send buffer) lets WP-05 + tests run before the real Telegram adapter lands.
- **`G-BRAND` mock:** a placeholder token set (`--brand-*` = current palette) lets WP-07/08 scaffold before the direction is locked, then flip to the real tokens.

## Subagent brief template
```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES · DO-NOT-TOUCH · DEFINITION OF DONE · MOCK · REPORT
```

---

### WP-01 — Channel adapter interface + WhatsApp refactor
- **GOAL:** `app/channels/base.py` (`Channel` + `InboundMessage`); lift WhatsApp send/verify into `app/channels/whatsapp.py`; namespace sender `wa:<phone>`.
- **BRANCH:** `feat/channel-abstraction` · **DEPENDS-ON:** — · **PRODUCES:** `G-CHANNEL-CONTRACT`.
- **FILES:** create `app/channels/{base,whatsapp}.py`; shrink `app/web/whatsapp.py`; touch `app/web/routes.py`. **DO-NOT-TOUCH:** agents/Band.
- **DoD:** interface frozen; WhatsApp `parse_inbound`→`send_text` round-trips (unit test); existing flow unchanged.

### WP-02 — Multi-channel identity + binding tokens
- **GOAL:** `0005` migration for `channel_accounts` + `binding_tokens`; channel-scoped session lookup with WhatsApp back-compat.
- **BRANCH:** `feat/channel-identity` · **DEPENDS-ON:** — · **PRODUCES:** `G-IDENTITY`.
- **FILES:** `migrations/versions/0005_channel_accounts.py`, `app/auth.py`, `app/data/models.py`.
- **DoD:** migration up/down clean; existing `wa:` user resolves a session; `(channel, channel_user_id)` lookup returns the user.

### WP-03 — Telegram channel adapter
- **GOAL:** `app/channels/telegram.py` (Bot API `sendMessage`/`sendDocument`, update parsing, secret-token `verify`); `/webhook/telegram`; `setWebhook` helper.
- **BRANCH:** `feat/telegram-adapter` · **DEPENDS-ON:** G-CHANNEL-CONTRACT.
- **FILES:** `app/channels/telegram.py`, `app/web/routes.py`, `app/config.py`, `.env.example`.
- **DoD:** update parses to `InboundMessage`; send (mocked) hits the Bot API; forged secret-token rejected.

### WP-04 — Telegram deep-link onboarding
- **GOAL:** web register issues a binding token + `t.me/<bot>?start=<token>` link; bot `/start <token>` binds `tg:<chat_id>` + opens a session. No phone/OTP.
- **BRANCH:** `feat/telegram-onboarding` · **DEPENDS-ON:** G-IDENTITY, WP-03.
- **FILES:** `app/web/web_routes.py`, `app/auth.py`, `app/channels/telegram.py`.
- **DoD:** unbound chat → deep-link prompt; token bind → linked + session; a write records + replies in Telegram.

### WP-05 — Wire both channels into the gateway
- **GOAL:** channel-aware `/webhook`; gateway on the namespaced sender; reply (text + documents) via the originating channel.
- **BRANCH:** `feat/channel-gateway` · **DEPENDS-ON:** WP-01, WP-03.
- **FILES:** `app/web/routes.py`, `app/agents/agent_router.py`, the statement/document reply path.
- **DoD:** WhatsApp + Telegram messages both round-trip through one gateway, each replying on its own channel.

### WP-06 — Rebrand design system
- **GOAL:** implement the locked `G-BRAND` direction as tokens (palette/type/radii/logo/motion/voice).
- **BRANCH:** `feat/rebrand-system` · **DEPENDS-ON:** G-BRAND.
- **FILES:** `design/tali/shared/tali.css`, `app/static/landing.css`, `app/static/style.css`, logo asset(s).
- **DoD:** tokens + logo land; a sample renders on the new brand; old tokens grep-clean.

### WP-07 — Rebranded landing + dual WA/TG CTA
- **GOAL:** rebuild the landing on the new brand with **Continue on WhatsApp** + **Continue on Telegram**; scroll narrative where it fits; update marketing/legal.
- **BRANCH:** `feat/landing-dual-cta` · **DEPENDS-ON:** WP-06.
- **FILES:** `app/templates/landing.html|features.html|pricing.html|legal`, `design/tali/commercial/*`.
- **DoD:** both CTAs present + deep-link correctly; page on the new brand.

### WP-08 — Rebrand in-app templates + bot welcome
- **GOAL:** restyle `register/verify/error`; update WhatsApp + Telegram welcome/onboarding copy + voice.
- **BRANCH:** `feat/rebrand-app` · **DEPENDS-ON:** WP-06.
- **FILES:** `app/templates/register.html|verify.html|error.html|_sprite.html`; channel welcome strings.
- **DoD:** no old palette/voice remains (grep); welcome matches the brand.

### WP-09 — Telegram setup doc + deploy + demo
- **GOAL:** finalise `docs/telegram-setup.md` (BotFather, token, webhook, deep-link), `.env`/config, deploy notes (`setWebhook`), update the demo for both channels.
- **BRANCH:** `chore/telegram-docs` · **DEPENDS-ON:** WP-03, WP-04.
- **FILES:** `docs/telegram-setup.md`, `.env.example`, `docs/demo-script.md`.
- **DoD:** a new dev stands the bot up from the doc; demo covers WhatsApp + Telegram.

---

## Tracking protocol
- Kickoff: orchestrator reads `05`, mirrors each WP into a harness Task; ticks `05` as work lands.
- Two parallel tracks → two worktrees (channel, rebrand); merge channel WPs before WP-09, rebrand WPs before the landing CTA references the bot username.

## Open coordination questions (resolve at kickoff)
1. **Telegram bot identity** — create the bot via BotFather; the username feeds the landing CTA + deep-link (WP-07 depends on it). See `docs/telegram-setup.md`.
2. **Identity backfill** — confirm the `wa:` backfill against live `sessions`/`webhook_events` rows before flipping the namespaced lookup (WP-02).
3. **Brand direction** — lock one of `designs/D-01..D-03` (`G-BRAND`) before any restyle WP starts.
4. **Deploy/webhook** — both channels need a public HTTPS URL; Telegram `setWebhook` is one call (WP-09).

<!-- groundwork:auto:end orchestration -->
