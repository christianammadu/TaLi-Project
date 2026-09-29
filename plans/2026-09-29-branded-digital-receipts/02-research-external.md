# 02 — External Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Design Principles for Mobile Receipts
- **Dimensions**: Optimized for mobile chat feeds: 1080x1350px (4:5 vertical portrait) or 1080x1080px (1:1 square).
- **Branding Elements**: Merchant Business Name, Date/Time, Itemized List, Subtotal, Discount/Tax, Total Paid, Payment Method (Cash/Transfer), Verification QR code.
- **Telegram Inline Share**: Telegram Bot API supports `SwitchInlineQuery` and `url` buttons (`https://t.me/share/url?url=...&text=...`), enabling single-tap forwarding.
- **WhatsApp Share**: Pre-filled `https://wa.me/?text=...` deep-link or direct document forwarding.
<!-- groundwork:auto:end findings -->

## Sources
- OpenAI API Documentation & Model Capabilities
- Telegram Bot API Specification (Core & WebApps)
- Meta Cloud API for WhatsApp Business
- Central Bank of Nigeria / Fintech Retail Guidelines
