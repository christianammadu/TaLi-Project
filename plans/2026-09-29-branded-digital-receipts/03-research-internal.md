# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Existing Report Engine**: `app/services/report_renderer.py` already includes typography (Fraunces, Hanken Grotesk), terracotta brand colors, and PDF/Excel generation. We can add a lightweight PNG/PDF receipt renderer.
- **Merchant Profile**: `app/data/models.py` `User.business_profile` stores merchant details.
- **Outbound Media**: `app/channels/telegram.py` `send_document` / `send_photo`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
