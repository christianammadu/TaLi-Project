# Predictive Inventory & Restock Alerts — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 3: Multimodal Intelligence & Growth.
- **Branch Discipline:** Base branch `feat/predictive-inventory-and-restock`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Sales Velocity & Stock Burn-Rate Calculator | Wave 3 | — | `feat/predictive-inventory-and-restock` |
| WP-02 | Predictive Restock Thresholds & Lead-Time Estimator | Wave 3 | WP-01 | `feat/predictive-inventory-and-restock` |
| WP-03 | Proactive Low-Stock WhatsApp/Telegram Alerts | Wave 3 | WP-02 | `feat/predictive-inventory-and-restock` |
| WP-04 | Instant Restock Purchase Order Draft Generator | Wave 3 | WP-03 | `feat/predictive-inventory-and-restock` |
| WP-05 | Predictive Inventory Simulation & Test Suite | Wave 3 | WP-04 | `feat/predictive-inventory-and-restock` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Sales Velocity & Stock Burn-Rate Calculator
- **GOAL:** Calculate daily units sold and average burn rate per SKU over 7-day and 30-day rolling windows.
- **REPO/BRANCH:** tali / `feature/wp-01-sales-velocity-&-stock-bu`
- **DEPENDS-ON:** —
- **FILES:** app/services/inventory_forecast.py, app/data/queries.py
- **DEFINITION OF DONE:** Computes days-of-stock-remaining for every active inventory item.

---

### WP-02 — Predictive Restock Thresholds & Lead-Time Estimator
- **GOAL:** Dynamically compute reorder point = (velocity * supplier lead time) + safety stock.
- **REPO/BRANCH:** tali / `feature/wp-02-predictive-restock-thresh`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/inventory_forecast.py, app/data/models.py
- **DEFINITION OF DONE:** Adapts reorder points to merchant sales spikes (e.g. weekend surges).

---

### WP-03 — Proactive Low-Stock WhatsApp/Telegram Alerts
- **GOAL:** Send actionable warnings before merchant stocks out: 'You have 3 bags of rice left (approx 2 days of stock)'.
- **REPO/BRANCH:** tali / `feature/wp-03-proactive-low-stock-whats`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/inventory_alerts.py, app/channels/base.py
- **DEFINITION OF DONE:** Scheduled daily scan; batches low-stock alerts into a single digest to prevent spam.

---

### WP-04 — Instant Restock Purchase Order Draft Generator
- **GOAL:** Generate one-click purchase order or WhatsApp message to supplier with suggested reorder quantities.
- **REPO/BRANCH:** tali / `feature/wp-04-instant-restock-purchase-`
- **DEPENDS-ON:** WP-03
- **FILES:** app/services/inventory_forecast.py, app/portal/routes.py
- **DEFINITION OF DONE:** Merchant clicks 'Restock' in portal or replies 'Order' in chat to format supplier message.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-05 — Predictive Inventory Simulation & Test Suite
- **GOAL:** Add tests validating velocity calculations, zero-sale SKUs, seasonality adjustments, and alert deduping.
- **REPO/BRANCH:** tali / `feature/wp-05-predictive-inventory-simu`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_predictive_inventory.py
- **DEFINITION OF DONE:** 100% test coverage of forecasting formulas and alert trigger thresholds.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
