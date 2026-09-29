# Merchant Desktop Portal & Staff RBAC — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 4: Enterprise Operations, Ecosystem Integrations & MCP.
- **Branch Discipline:** Base branch `feat/merchant-desktop-and-staff-rbac`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Staff Role Model & PIN-Based Authentication | Wave 4 | — | `feat/merchant-desktop-and-staff-rbac` |
| WP-02 | Debtor Management Hub & Aging Analysis UI | Wave 4 | WP-01 | `feat/merchant-desktop-and-staff-rbac` |
| WP-03 | Merchant Business Settings & Receipt Customizer | Wave 4 | WP-02 | `feat/merchant-desktop-and-staff-rbac` |
| WP-04 | Desktop Quick-Action Command Bar & Modal (CMD+K) | Wave 4 | WP-03 | `feat/merchant-desktop-and-staff-rbac` |
| WP-05 | Merchant Desktop & Staff RBAC Test Suite | Wave 4 | WP-04 | `feat/merchant-desktop-and-staff-rbac` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```
---

### WP-01 — Staff Role Model & PIN-Based Authentication
- **GOAL:** Define merchant_staff table with owner, manager, cashier roles, permissions bitmask, and 4-digit PIN authentication.
- **REPO/BRANCH:** tali / `feature/wp-01-merchant-desktop-and-staff-rbac`
- **DEPENDS-ON:** —
- **FILES:** app/data/models.py, app/portal/auth.py, migrations/versions/0007_staff_rbac.py
- **DEFINITION OF DONE:** Models created, PIN hashing with bcrypt, role-permission matrix enforced on portal session.
---

### WP-02 — Debtor Management Hub & Aging Analysis UI
- **GOAL:** Build desktop debtors view with aging buckets (0-30d, 31-60d, 60+d), partial settlement modal, and Paystack link generator.
- **REPO/BRANCH:** tali / `feature/wp-02-merchant-desktop-and-staff-rbac`
- **DEPENDS-ON:** WP-01
- **FILES:** app/portal/debtors.py, app/templates/portal/debtors.html, app/portal/routes.py
- **DEFINITION OF DONE:** Aging debt cards, searchable customer table, instant WhatsApp reminder preview, zero emojis.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-03 — Merchant Business Settings & Receipt Customizer
- **GOAL:** Allow store owners to upload business logo, customize receipt header/footer, set alert thresholds, and manage staff PINs.
- **REPO/BRANCH:** tali / `feature/wp-03-merchant-desktop-and-staff-rbac`
- **DEPENDS-ON:** WP-02
- **FILES:** app/portal/settings.py, app/templates/portal/settings.html
- **DEFINITION OF DONE:** Logo image upload, receipt preview pane, staff management table with PIN reset.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-04 — Desktop Quick-Action Command Bar & Modal (CMD+K)
- **GOAL:** Implement global keyboard shortcut (CMD+K / CTRL+K) opening rapid transaction entry modal with product autocomplete.
- **REPO/BRANCH:** tali / `feature/wp-04-merchant-desktop-and-staff-rbac`
- **DEPENDS-ON:** WP-03
- **FILES:** app/templates/portal/layout.html, app/templates/portal/_quick_record.html
- **DEFINITION OF DONE:** Record sale or expense in <3 seconds without page reload, instant ledger update via HTMX.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-05 — Merchant Desktop & Staff RBAC Test Suite
- **GOAL:** Add comprehensive tests proving cashiers cannot view statements or edit staff, and PIN auth security.
- **REPO/BRANCH:** tali / `feature/wp-05-merchant-desktop-and-staff-rbac`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_portal_staff_rbac.py
- **DEFINITION OF DONE:** Test suite covering role permission denies, PIN lockout defense, and debtor aging calculations.
---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
