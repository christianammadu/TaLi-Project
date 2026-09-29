# Branded Digital Receipts Engine — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 2: Daily Workflow & Viral Retention.
- **Branch Discipline:** Base branch `feat/branded-digital-receipts`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Digital Receipt Rendering Engine | Wave 2 | — | `feat/branded-digital-receipts` |
| WP-02 | Merchant Branding & Template Customization | Wave 2 | WP-01 | `feat/branded-digital-receipts` |
| WP-03 | Telegram Native Share & Inline Keyboard Action | Wave 2 | WP-02 | `feat/branded-digital-receipts` |
| WP-04 | WhatsApp Digital Receipt Delivery | Wave 2 | WP-03 | `feat/branded-digital-receipts` |
| WP-05 | Receipt Generation Test Coverage | Wave 2 | WP-04 | `feat/branded-digital-receipts` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Digital Receipt Rendering Engine
- **GOAL:** Create app/services/receipt_renderer.py generating compact, branded PNG and PDF receipts using Pillow/ReportLab.
- **REPO/BRANCH:** tali / `feature/wp-01-digital-receipt-rendering`
- **DEPENDS-ON:** —
- **FILES:** app/services/receipt_renderer.py, tests/test_receipt_renderer.py
- **DEFINITION OF DONE:** Crisp thermal-style or clean card receipts generated in <50ms with merchant name, items, tax, and total.

---

### WP-02 — Merchant Branding & Template Customization
- **GOAL:** Allow merchants to configure business name, phone, address, and receipt footer notes via chat/portal.
- **REPO/BRANCH:** tali / `feature/wp-02-merchant-branding-&-templ`
- **DEPENDS-ON:** WP-01
- **FILES:** app/portal/routes.py, app/templates/portal/settings.html
- **DEFINITION OF DONE:** Custom logo upload, header/footer note configuration stored in merchant business profile.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-03 — Telegram Native Share & Inline Keyboard Action
- **GOAL:** Attach inline keyboard buttons ('Share Receipt', 'Download PDF') beneath sale confirmations in Telegram.
- **REPO/BRANCH:** tali / `feature/wp-03-telegram-native-share-&-i`
- **DEPENDS-ON:** WP-02
- **FILES:** app/channels/telegram.py, app/agents/agent_2_ledger.py
- **DEFINITION OF DONE:** Sale confirmation in Telegram sends receipt document + share button with one tap.

---

### WP-04 — WhatsApp Digital Receipt Delivery
- **GOAL:** Send branded receipt image in WhatsApp with one-tap forward prompt upon completing a sale.
- **REPO/BRANCH:** tali / `feature/wp-04-whatsapp-digital-receipt-`
- **DEPENDS-ON:** WP-03
- **FILES:** app/channels/whatsapp.py, app/agents/agent_2_ledger.py
- **DEFINITION OF DONE:** WhatsApp media message upload via Cloud API; caption with transaction summary.

---

### WP-05 — Receipt Generation Test Coverage
- **GOAL:** Add unit tests verifying receipt rendering, currency formatting, and multi-channel message dispatch.
- **REPO/BRANCH:** tali / `feature/wp-05-receipt-generation-test-c`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_receipt_flow.py
- **DEFINITION OF DONE:** Tests covering multi-item receipts, currency symbol formatting (NGN), and missing logo fallback.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
