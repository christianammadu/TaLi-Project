# TaLi — Project Status

> _Formerly "Bookkeeper". Rebranded to **TaLi** (from "Tally")._

_Last updated: 2026-06-03_

A WhatsApp-based bookkeeping assistant for small business owners. Users record
income, expenses, and inventory in natural language ("Sold rice 5000", "Bought
fuel 2k"), query their finances, and generate business summaries — all over
WhatsApp.

## Architecture

```
WhatsApp (Meta Cloud API)
        │
        ▼
  /webhook (routes.py) ──► command routing (login / code / logout / help)
        │
        ▼
  TransactionAgent (orchestrator)
        │
        ├─► nlp.py        — OpenAI parses message → structured JSON (intent)
        ├─► validators.py — normalize & validate parsed data
        ├─► queries.py    — record / sum / list / balance (MySQL)
        ├─► formatter.py  — WhatsApp-friendly reply strings
        │
        ├─► ReportingAgent  — daily/weekly/monthly summaries
        └─► InventoryAgent  — stock ADD / REMOVE / SET
```

A registration + login web flow (`web_routes.py`, `templates/`) handles account
creation and the verification-link → access-code handshake.

## What's built

| Area | Status | Files |
|------|--------|-------|
| Modular Flask app (blueprints, factory) | ✅ | `app/__init__.py` |
| WhatsApp webhook (verify + receive) | ✅ | `routes.py`, `whatsapp.py` |
| Auth: registration OTP, login token, access code, sessions | ✅ | `auth.py`, `web_routes.py` |
| Database schema + auto-init + seed categories | ✅ | `database.py` |
| Message intelligence (OpenAI intent parsing) | ✅ | `nlp.py` |
| Transaction orchestration + shorthand fast-path | ✅ | `transaction_agent.py` |
| Validation & normalization | ✅ | `validators.py` |
| Queries (sum / list / balance, multi-currency) | ✅ | `queries.py` |
| Reply formatting | ✅ (transactions/queries) | `formatter.py` |
| Reporting agent | ⚠️ returns raw JSON (see bug #4) | `reporting_agent.py` |
| Inventory agent | ⚠️ returns raw JSON (see bug #4) | `inventory_agent.py` |
| Unit tests | ⚠️ validators/formatters only | `tests/` |
| Web registration UI | ✅ basic | `templates/` |

## Data model (MySQL)

- `users` — phone_number (unique), display_name, is_verified
- `whatsapp_accounts` — sender_id → user_id link
- `verification_codes` — registration OTPs & login tokens/codes
- `sessions` — sender_id sessions with expiry
- `categories` — system defaults (user_id NULL) + per-user custom
- `transactions` — type, action, amount, currency, item, category, date
- `products` / `stock_movements` — inventory tracking
- `records` — legacy table, double-written (slated for removal)

## Tech stack

Flask · MySQL (mysql-connector-python) · OpenAI (gpt-4o-mini) · WhatsApp Cloud
API · python-dotenv. Dependencies are currently **unpinned**.
