# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Portal Routes**: `app/portal/routes.py` and `app/portal/auth.py`. We can add an authenticator for `initData`.
- **Telegram Routes**: `app/web/telegram_routes.py` can attach the WebApp menu button via `setChatMenuButton`.
- **Layout Template**: `app/templates/portal/layout.html` can include Telegram WebApp JS SDK (`https://telegram.org/js/telegram-web-app.js`).
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
