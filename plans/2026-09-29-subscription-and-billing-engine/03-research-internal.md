# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Data Models**: Add `Subscription`, `Plan`, and `BillingInvoice` in `app/data/models.py`.
- **Auth Decorators**: Add `@tier_required("pro")` in `app/portal/auth.py` alongside `@merchant_required`.
- **Portal Views**: Add billing settings, plan selector, and receipt history in `app/portal/routes.py`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
