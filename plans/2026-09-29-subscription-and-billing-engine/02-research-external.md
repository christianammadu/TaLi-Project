# 02 — External Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Paystack Recurring Billing Architecture
- **Subscriptions API**: Paystack handles recurring debit schedules on cards via tokenization.
- **Webhook Events**:
  - `subscription.create`: Initial subscription established.
  - `charge.success`: Renewal payment debited successfully.
  - `invoice.payment_failed`: Payment failed (trigger grace period & notification).
  - `subscription.disable`: Canceled subscription.
- **Pricing Strategy**:
  - **Starter (Free)**: Up to 50 transactions/month, basic reports, text only.
  - **Merchant Pro (₦3,500/month)**: Unlimited transactions, Voice notes, POS scanning, branded receipts.
  - **Business (₦9,500/month)**: Multi-staff accounts, Credit Dossier exports, priority support.
<!-- groundwork:auto:end findings -->

## Sources
- OpenAI API Documentation & Model Capabilities
- Telegram Bot API Specification (Core & WebApps)
- Meta Cloud API for WhatsApp Business
- Central Bank of Nigeria / Fintech Retail Guidelines
