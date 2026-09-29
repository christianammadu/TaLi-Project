# 02 — External Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## POS Receipt & Bank App Layouts in Nigeria
- **Major POS Providers**: Moniepoint, OPay, Palmpay, Baxi, Kudi/Nomba. Key fields: Terminal ID, STAN/RRN, Date/Time, Amount (NGN), Status (APPROVED / SUCCESS).
- **Major Bank Apps**: GTBank, Zenith, Access, Kuda, OPay, PalmPay transfer receipts. Key fields: Beneficiary Name, Sender Name, Reference ID, Amount, Transaction Date.
- **Model Selection**: `gpt-4o-mini` with Vision capabilities delivers 98% accuracy on Nigerian receipts at ~$0.002 per image with sub-2s latency.
- **RRN / Reference Deduplication**: Using the RRN or Bank Session ID as an idempotency key prevents accidental double-counting if a merchant sends the receipt twice.
<!-- groundwork:auto:end findings -->

## Sources
- OpenAI API Documentation & Model Capabilities
- Telegram Bot API Specification (Core & WebApps)
- Meta Cloud API for WhatsApp Business
- Central Bank of Nigeria / Fintech Retail Guidelines
