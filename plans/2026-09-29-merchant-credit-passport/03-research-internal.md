# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Report Engine**: `app/services/report_renderer.py` provides high-fidelity PDF canvas tools and typography.
- **Metrics Calculation**: `app/portal/metrics.py` calculates cashflow, revenue, expenses, and transaction velocity.
- **Public Verification Route**: Can be registered in `app/web/routes.py` or a dedicated `verify_bp`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
