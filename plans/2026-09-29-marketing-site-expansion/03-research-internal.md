# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Existing Routes**: `app/web/web_routes.py` serves `/` and onboarding flows.
- **Templates**: `app/templates/` can be extended with `privacy.html`, `terms.html`, `faq.html`, `help.html`, and `changelog.html` matching existing Fraunces & Obsidian design language.
- **Navigation**: Update footer links in `register.html` and public landing pages.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
