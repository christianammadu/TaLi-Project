# 03 — Internal Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Codebase Touchpoints
- **Debt Models**: `app/data/models.py` has `DebtBalance`, `DebtLog`, and `DebtEntry`.
- **Query Scopes**: `app/data/queries.py` contains `query_debt_summary` and customer balances.
- **Ledger Mutation**: `app/agents/agent_2_ledger.py` handles `add_debt`, `repayment`, and `full_payment`.
<!-- groundwork:auto:end findings -->

## Existing Architecture Constraints
- Must maintain 100% test isolation without requiring external network connections in test suite.
- All database queries must enforce tenant scoping (`user_id` / `business_id`).
- Outbound responses must handle both WhatsApp (Meta Cloud API) and Telegram Bot API.
