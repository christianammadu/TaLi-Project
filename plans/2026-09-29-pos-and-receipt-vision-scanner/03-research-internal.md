# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Media Download**: WhatsApp media download via Graph API (`GET /{media-id}`); Telegram photo download via `getFile` (`file_path`).
- **Duplicate Prevention**: `app/data/models.py` has `Transaction.event_id` with a `UNIQUE` constraint. We can store the hash or RRN in `event_id` (`f"pos_{rrn}"`).
- **Intake Integration**: Send structured parsed payload into `LedgerAgent.handle_intake_payload`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
