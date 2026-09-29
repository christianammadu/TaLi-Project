# External Accounting Integrations & Public Developer API — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 4: Enterprise Operations, Ecosystem Integrations & MCP.
- **Branch Discipline:** Base branch `feat/accounting-integrations-and-public-api`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Standard Accounting Ledger Schema Normalizer | Wave 4 | — | `feat/accounting-integrations-and-public-api` |
| WP-02 | QuickBooks Online & Xero Export Adapters | Wave 4 | WP-01 | `feat/accounting-integrations-and-public-api` |
| WP-03 | Public Merchant Developer REST API (v1) | Wave 4 | WP-02 | `feat/accounting-integrations-and-public-api` |
| WP-04 | Inbound E-Commerce Webhook Ingestors (Shopify & WooCommerce) | Wave 4 | WP-03 | `feat/accounting-integrations-and-public-api` |
| WP-05 | Accounting Integrations & Public API Test Suite | Wave 4 | WP-04 | `feat/accounting-integrations-and-public-api` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```
---

### WP-01 — Standard Accounting Ledger Schema Normalizer
- **GOAL:** Map TaLi single-entry sales/expenses into double-entry chart of accounts (Assets, Liabilities, Equity, Revenue, COGS).
- **REPO/BRANCH:** tali / `feature/wp-01-accounting-integrations-and-public-api`
- **DEPENDS-ON:** —
- **FILES:** app/services/accounting_export.py, tests/test_accounting_normalizer.py
- **DEFINITION OF DONE:** Deterministic double-entry transformation; verifies Debit == Credit for every transaction batch.
---

### WP-02 — QuickBooks Online & Xero Export Adapters
- **GOAL:** Implement batch export generators for QuickBooks (IIF/QBO format) and Xero/Zoho Books (CSV format).
- **REPO/BRANCH:** tali / `feature/wp-02-accounting-integrations-and-public-api`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/integrations/quickbooks.py, app/services/integrations/xero.py
- **DEFINITION OF DONE:** Validated export files accepted by QuickBooks and Xero import validators without syntax errors.
---

### WP-03 — Public Merchant Developer REST API (v1)
- **GOAL:** Build bearer-token authenticated REST endpoints (/api/v1/transactions, /api/v1/inventory, /api/v1/debts).
- **REPO/BRANCH:** tali / `feature/wp-03-accounting-integrations-and-public-api`
- **DEPENDS-ON:** WP-02
- **FILES:** app/web/api_v1.py, app/services/api_keys.py
- **DEFINITION OF DONE:** Scoped API key authentication, rate limiting (60 req/min), standard JSON error envelopes.
---

### WP-04 — Inbound E-Commerce Webhook Ingestors (Shopify & WooCommerce)
- **GOAL:** Handle incoming order webhooks from Shopify, WooCommerce, and Paystack Storefront to auto-log sales.
- **REPO/BRANCH:** tali / `feature/wp-04-accounting-integrations-and-public-api`
- **DEPENDS-ON:** WP-03
- **FILES:** app/web/ecommerce_webhooks.py, app/services/webhook_verifier.py
- **DEFINITION OF DONE:** HMAC verification of Shopify/WooCommerce webhooks; creates sales and updates stock balance automatically.
---

### WP-05 — Accounting Integrations & Public API Test Suite
- **GOAL:** Add tests validating chart of accounts balance, developer API rate limiting, and webhook ingest accuracy.
- **REPO/BRANCH:** tali / `feature/wp-05-accounting-integrations-and-public-api`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_accounting_api.py
- **DEFINITION OF DONE:** Complete test suite covering export generation, API key lifecycle, and order auto-recording.
---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
