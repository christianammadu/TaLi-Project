# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Telegram Webhook**: `app/web/telegram_routes.py` and `app/channels/telegram.py` currently inspect `msg.get("text")`. Needs extension to capture `msg.get("voice")` or `msg.get("audio")` and fetch file via `TelegramChannel.get_file(file_id)`.
- **WhatsApp Webhook**: `app/web/routes.py` and `app/web/whatsapp.py` parse text messages. Needs handling for `messages[0].type == 'audio'` or `'voice'`, using Meta Graph API media download endpoint with bearer token.
- **Intake Pipeline**: `app/agents/agent_1_intake.py` receives raw text. It can receive the transcribed text with a flag `is_voice_transcription=True`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
