# Subscription & Billing Engine (Paystack Launch Engine) — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 1: Launch Foundations & Monetization.
- **Branch Discipline:** Base branch `feat/subscription-and-billing-engine`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Subscription & Billing Data Models | Wave 1 | — | `feat/subscription-and-billing-engine` |
| WP-02 | Paystack Webhook & Verification Engine | Wave 1 | WP-01 | `feat/subscription-and-billing-engine` |
| WP-03 | Merchant Portal Billing & Upgrade Hub | Wave 1 | WP-02 | `feat/subscription-and-billing-engine` |
| WP-04 | Feature Entitlement & Tier Gating Middleware | Wave 1 | WP-03 | `feat/subscription-and-billing-engine` |
| WP-05 | Billing Lifecycle & Webhook Test Suite | Wave 1 | WP-04 | `feat/subscription-and-billing-engine` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Subscription & Billing Data Models
- **GOAL:** Define SubscriptionPlan, MerchantSubscription, and BillingInvoice ORM models with Alembic migration 0006.
- **REPO/BRANCH:** tali / `feature/wp-01-subscription-&-billing-da`
- **DEPENDS-ON:** —
- **FILES:** app/data/models.py, app/data/database.py, migrations/versions/0006_subscription_billing.py
- **DEFINITION OF DONE:** Alembic upgrade green, models with proper indices, seed default plans (starter, pro, business).

---

### WP-02 — Paystack Webhook & Verification Engine
- **GOAL:** Implement secure Paystack webhook endpoint with HMAC-SHA512 verification and subscription lifecycle handlers.
- **REPO/BRANCH:** tali / `feature/wp-02-paystack-webhook-&-verifi`
- **DEPENDS-ON:** WP-01
- **FILES:** app/web/billing_routes.py, app/services/billing.py, tests/test_paystack_webhook.py
- **DEFINITION OF DONE:** Signature check with constant-time comparison, handles charge.success, subscription.create, invoice.payment_failed (3-day grace period), subscription.disable. 100% test coverage.

---

### WP-03 — Merchant Portal Billing & Upgrade Hub
- **GOAL:** Build merchant self-service billing UI showing active plan, renewal date, usage limits, and Paystack inline checkout modal.
- **REPO/BRANCH:** tali / `feature/wp-03-merchant-portal-billing-&`
- **DEPENDS-ON:** WP-02
- **FILES:** app/portal/routes.py, app/templates/portal/billing.html, app/templates/portal/_plan_card.html
- **DEFINITION OF DONE:** Visual tier upgrade cards, invoice download history, Paystack inline checkout integration. UI follows impeccable and huashu-design with zero emojis and zero em dashes.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-04 — Feature Entitlement & Tier Gating Middleware
- **GOAL:** Implement @tier_required and @feature_required route decorators and chat quota enforcement.
- **REPO/BRANCH:** tali / `feature/wp-04-feature-entitlement-&-tie`
- **DEPENDS-ON:** WP-03
- **FILES:** app/portal/auth.py, app/services/billing.py, app/channels/base.py
- **DEFINITION OF DONE:** Gating for voice notes, POS vision, and credit dossier. Friendly upsell message emitted when hitting limit.

---

### WP-05 — Billing Lifecycle & Webhook Test Suite
- **GOAL:** Add end-to-end integration tests covering the complete subscription lifecycle, grace period degradation, and renewal.
- **REPO/BRANCH:** tali / `feature/wp-05-billing-lifecycle-&-webho`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_billing_integration.py
- **DEFINITION OF DONE:** Simulated multi-month renewal, failed charge retries, cancellation, and reactivation.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
