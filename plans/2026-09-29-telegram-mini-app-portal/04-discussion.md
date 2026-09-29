# 04 — Deliberation & Architectural Decisions

## Round 1 — Initial Design & Scope Lock (2026-09-29)

### Decisions Locked
1. **Multi-Channel Parity**: Ensure every feature works natively across both WhatsApp and Telegram, taking advantage of Telegram's inline keyboards and free push notifications where advantageous.
2. **Offline-Safe Testing**: All new services must feature dedicated test suites utilizing dependency injection and mocks so CI runs in seconds without live API credentials.
3. **Tenancy Safety**: Strict multi-tenant isolation on all models and queries.
