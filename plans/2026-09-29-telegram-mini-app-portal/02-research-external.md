# 02 — External Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Telegram Mini Apps (TMA) Architecture
- **Authentication**: Telegram injects `window.Telegram.WebApp.initData` (a query string with user hash). The backend validates this by calculating SHA256 HMAC of `initData` with the Bot Token.
- **Single Sign-On**: No passwords, no OTPs, zero login friction. The merchant's Telegram ID maps directly to their bound `user_id`.
- **Viewport & Styling**: TMA provides CSS variables (`--tg-theme-bg-color`, etc.) and handles safe-area insets seamlessly.
<!-- groundwork:auto:end findings -->

## Sources
- OpenAI API Documentation & Model Capabilities
- Telegram Bot API Specification (Core & WebApps)
- Meta Cloud API for WhatsApp Business
- Central Bank of Nigeria / Fintech Retail Guidelines
