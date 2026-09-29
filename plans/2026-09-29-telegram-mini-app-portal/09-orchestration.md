# Telegram Mini App & Portal Bridge — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 1: Launch Foundations & Monetization.
- **Branch Discipline:** Base branch `feat/telegram-mini-app-portal`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Telegram initData HMAC Verification Authenticator | Wave 1 | — | `feat/telegram-mini-app-portal` |
| WP-02 | Seamless Portal Auto-Login Middleware | Wave 1 | WP-01 | `feat/telegram-mini-app-portal` |
| WP-03 | Telegram Bot Menu Button & Deep Link Integration | Wave 1 | WP-02 | `feat/telegram-mini-app-portal` |
| WP-04 | Responsive Viewport & Telegram Theme Adaptation | Wave 1 | WP-03 | `feat/telegram-mini-app-portal` |
| WP-05 | Mini App Authentication & Portal Test Suite | Wave 1 | WP-04 | `feat/telegram-mini-app-portal` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Telegram initData HMAC Verification Authenticator
- **GOAL:** Implement cryptographic validator verifying Telegram WebApp credentials against bot secret token.
- **REPO/BRANCH:** tali / `feature/wp-01-telegram-initdata-hmac-ve`
- **DEPENDS-ON:** —
- **FILES:** app/portal/auth.py, tests/test_telegram_auth.py
- **DEFINITION OF DONE:** SHA256 HMAC verification of Telegram initData query string; prevents replay attacks and hash spoofing.

---

### WP-02 — Seamless Portal Auto-Login Middleware
- **GOAL:** Add route handler and session bridge in app/portal/routes.py authenticating merchants via WebApp headers.
- **REPO/BRANCH:** tali / `feature/wp-02-seamless-portal-auto-logi`
- **DEPENDS-ON:** WP-01
- **FILES:** app/portal/routes.py, app/portal/auth.py
- **DEFINITION OF DONE:** Instant authentication into portal session without SMS/WhatsApp OTP when opened inside Telegram.

---

### WP-03 — Telegram Bot Menu Button & Deep Link Integration
- **GOAL:** Configure Telegram bot menu button and inline /portal command launching the in-app WebApp.
- **REPO/BRANCH:** tali / `feature/wp-03-telegram-bot-menu-button-`
- **DEPENDS-ON:** WP-02
- **FILES:** app/channels/telegram.py, app/web/telegram_routes.py
- **DEFINITION OF DONE:** Bot Menu Button configured via Telegram Bot API setChatMenuButton; /portal replies with WebApp button.

---

### WP-04 — Responsive Viewport & Telegram Theme Adaptation
- **GOAL:** Inject Telegram WebApp JS SDK into app/templates/portal/layout.html and optimize mobile touch navigation.
- **REPO/BRANCH:** tali / `feature/wp-04-responsive-viewport-&-tel`
- **DEPENDS-ON:** WP-03
- **FILES:** app/templates/portal/layout.html, app/templates/portal/dashboard.html
- **DEFINITION OF DONE:** Theme variables (bg_color, text_color, button_color) match user's Telegram client theme. Zero emojis.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-05 — Mini App Authentication & Portal Test Suite
- **GOAL:** Add unit tests validating HMAC signature verification, session creation, and replay attack prevention.
- **REPO/BRANCH:** tali / `feature/wp-05-mini-app-authentication-&`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_telegram_miniapp.py
- **DEFINITION OF DONE:** Full test coverage of initData verification with valid, expired, and tampered payloads.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
