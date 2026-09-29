# Platform Admin Operations, Merchant CRM & Admin RBAC — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 4: Enterprise Operations, Ecosystem Integrations & MCP.
- **Branch Discipline:** Base branch `feat/platform-admin-ops-and-crm`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Multi-Admin RBAC & Operator Session Security | Wave 4 | — | `feat/platform-admin-ops-and-crm` |
| WP-02 | Merchant CRM Directory & Account Detail View | Wave 4 | WP-01 | `feat/platform-admin-ops-and-crm` |
| WP-03 | Platform Revenue, MRR & Paystack Webhook Log | Wave 4 | WP-02 | `feat/platform-admin-ops-and-crm` |
| WP-04 | Channel Health Telemetry & Operations Alerting | Wave 4 | WP-03 | `feat/platform-admin-ops-and-crm` |
| WP-05 | Admin Action Audit Trail & Governance Test Suite | Wave 4 | WP-04 | `feat/platform-admin-ops-and-crm` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```
---

### WP-01 — Multi-Admin RBAC & Operator Session Security
- **GOAL:** Create AdminUser model supporting SuperAdmin, ComplianceOfficer, SupportAgent, and FinOpsAuditor roles.
- **REPO/BRANCH:** tali / `feature/wp-01-platform-admin-ops-and-crm`
- **DEPENDS-ON:** —
- **FILES:** app/data/models.py, app/admin/auth.py, migrations/versions/0008_admin_rbac.py
- **DEFINITION OF DONE:** Admin user seeding, permission decorators (@admin_role_required), session audit logging.
---

### WP-02 — Merchant CRM Directory & Account Detail View
- **GOAL:** Build searchable merchant CRM with phone lookup, channel binding status (WhatsApp/Telegram), and activity logs.
- **REPO/BRANCH:** tali / `feature/wp-02-platform-admin-ops-and-crm`
- **DEPENDS-ON:** WP-01
- **FILES:** app/admin/merchants.py, app/templates/admin/merchants.html, app/templates/admin/merchant_detail.html
- **DEFINITION OF DONE:** Instant phone search, channel badges, plan tier pill, transaction drill-down, support notes.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-03 — Platform Revenue, MRR & Paystack Webhook Log
- **GOAL:** Implement revenue analytics dashboard tracking MRR, ARR, tier breakdown, and raw Paystack webhook event stream.
- **REPO/BRANCH:** tali / `feature/wp-03-platform-admin-ops-and-crm`
- **DEPENDS-ON:** WP-02
- **FILES:** app/admin/revenue.py, app/templates/admin/revenue.html
- **DEFINITION OF DONE:** Chart.js subscription growth graph, active/past_due count, webhook event payload inspector.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-04 — Channel Health Telemetry & Operations Alerting
- **GOAL:** Build real-time WhatsApp Cloud API and Telegram Bot health dashboard with automated Slack/Telegram alerts.
- **REPO/BRANCH:** tali / `feature/wp-04-platform-admin-ops-and-crm`
- **DEPENDS-ON:** WP-03
- **FILES:** app/admin/channels.py, app/templates/admin/channels.html, app/services/alerts.py
- **DEFINITION OF DONE:** Token expiration monitor, webhook latency tracker, automated alerts for spend ceiling >80% or webhook errors.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.
---

### WP-05 — Admin Action Audit Trail & Governance Test Suite
- **GOAL:** Add tests validating NDPR-compliant admin audit logging, role segregation, and unauthorized access rejections.
- **REPO/BRANCH:** tali / `feature/wp-05-platform-admin-ops-and-crm`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_admin_crm_rbac.py
- **DEFINITION OF DONE:** 100% test coverage of admin roles, audit trail persistence, and merchant lookup security.
---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
