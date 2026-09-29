# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Metrics Module**: `app/portal/metrics.py` has `compute_portal_metrics` for date-bounded periods.
- **Outbound Telegram**: `app/channels/telegram.py` `send_text` and `send_document`.
- **Scheduler**: Can integrate with background cron or worker scheduler.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
