# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Inventory Models**: `app/data/models.py` has `InventoryItem`, `InventoryMovement`, `Product`, `StockMovement`.
- **Portal Catalog**: `app/portal/inventory.py` manages stock levels and minimum stock thresholds (`minimum_stock_level`).
- **Alert Dispatch**: Can utilize `TelegramChannel.send_text` and WhatsApp outbound notification hooks.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
