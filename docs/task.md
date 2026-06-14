# Bookkeeper Development Tasks ✅

Branch: `feature/auth-system`

## 1. Authentication & Web Portal ✅
- [x] 1.1 Update `app/database.py` — add users, whatsapp_accounts, verification_codes, and sessions tables
- [x] 1.2 Update `app/config.py` — add session duration (default 72 hours), app URL, and token configs
- [x] 1.3 Create `app/auth.py` — session management, OTP, and access code validation logic
- [x] 1.4 Create `app/web_routes.py` — Flask handlers for login verification and registrations
- [x] 1.5 Create HTML templates (`register.html`, `verify.html`, `error.html`) & `style.css`
- [x] 1.6 Update `app/routes.py` — routing controls for public/session-gated WhatsApp messages
- [x] 1.7 Update `app/web_routes.py` — deliver registration OTP using WhatsApp message templates (`send_otp_template`)
- [x] 1.8 Update `docs/auth_system_proposal.md` — resolve open questions (LLM NLP, 72-hour sessions, WhatsApp OTP, multi-currency)

## 2. Message Intelligence Layer & Transaction Agent ✅
- [x] 2.1 Update `app/database.py` — add `action`, `item`, and `currency` columns to `transactions` table
- [x] 2.2 Migrate database default categories to exactly 8 standard items:
  - `Sales` (income)
  - `Inventory Purchase` (expense)
  - `Transport` (expense)
  - `Fuel` (expense)
  - `Salary` (expense)
  - `Utilities` (expense)
  - `Rent` (expense)
  - `Miscellaneous` (expense) - strictly configured as an expense.
- [x] 2.3 Update `app/nlp.py` — enhance OpenAI GPT prompt to strictly output the 8 categories and extract currency codes (e.g. NGN, USD, EUR, etc.), defaulting to NGN
- [x] 2.4 Create `app/validators.py` — validation logic for parsed amounts, dates, transactions, and queries (including currency validation and fallback normalization)
- [x] 2.5 Create `app/transaction_agent.py` — orchestrator for shorthand fast-path, NLP parsing, validators, and queries (with currency and Miscellaneous category default)
- [x] 2.6 Update `app/queries.py` — support inserts with currency and query aggregates/balances grouped by currency
- [x] 2.7 Update `app/formatter.py` — format multi-currency transaction confirmations, list results, sum queries, and balances grouped by currency with symbols
- [x] 2.8 Update `tests/test_transaction_agent.py` — refactor unit tests to assert standard categories, currency fields, and multi-currency formats

## 3. Reporting Agent & Business Summaries ✅
- [x] 3.1 Create `app/reporting_agent.py` — calculate daily, weekly (last 7 days), and monthly business summaries grouped by currency
- [x] 3.2 Update `app/database.py` — change category type of `Miscellaneous` default category from `both` to `expense`
- [x] 3.3 Update `app/nlp.py` — add report intent parsing to recognize daily, weekly, and monthly report request keywords
- [x] 3.4 Update `app/transaction_agent.py` — route the `report` intent to the new `ReportingAgent`
- [x] 3.5 Update `tests/test_transaction_agent.py` — write test cases for Reporting Agent date calculation bounds (daily, weekly, monthly) and multi-currency formatted outputs
- [x] 3.6 Format output of Reporting Agent to return exact structured JSON representation (Income, Expenses, Profit) matching `rpt001` specification

## 4. Inventory Agent & Product Tracking ✅
- [x] 4.1 Update `app/database.py` — create `products` and `stock_movements` tables to support inventory tracking
- [x] 4.2 Update `app/nlp.py` — add inventory intent to system prompt supporting `ADD`, `REMOVE`, and `SET` actions, and extraction of product, quantity, and unit
- [x] 4.3 Create `app/inventory_agent.py` — coordinate stock increments/decrements, prevent negative stock, and generate structured JSON responses
- [x] 4.4 Update `app/transaction_agent.py` — route `inventory` intent to `InventoryAgent`
- [x] 4.5 Update `tests/test_transaction_agent.py` — add unit test coverage for Inventory Agent clarification flow
- [x] 4.6 Commit and push all updates to GitHub remote branch `feature/auth-system`

## 5. Debt Tracking Agent ✅
- [x] 5.1 Update `app/database.py` — create `debt_balances` and `debt_logs` tables to support debt tracking
- [x] 5.2 Update `app/nlp.py` — add debt intent to system prompt supporting name, type, action, amount, and currency extraction
- [x] 5.3 Create `app/debt_agent.py` — implement DebtAgent logic with normalized names, previous/new balances, mapping to receivable/payable, positive amounts, and full_payment logic
- [x] 5.4 Update `app/transaction_agent.py` — route `debt` intent to `DebtAgent`
- [x] 5.5 Update `tests/test_transaction_agent.py` — write unit test cases verifying all debt states, actions, currency awareness, and clarification flows
- [x] 5.6 Commit and push all updates to GitHub remote branch `feature/auth-system`

## 6. Agent Router Layer (Separation of Concerns) ✅
- [x] 6.1 Create `app/agent_router.py` — implement AgentRouter logic for intent classification and clean delegation
- [x] 6.2 Update `app/transaction_agent.py` — split routing logic out, making TransactionAgent focus strictly on financial transaction recording and querying
- [x] 6.3 Update `app/routes.py` — route incoming WhatsApp messages through `AgentRouter` instead of `TransactionAgent`
- [x] 6.4 Verify routing and commit/push changes to GitHub remote branch `feature/auth-system`

## 7. Financial Operating System (FOS) Enhancements ✅
- [x] 7.1 Update `app/database.py` — add `processed_messages` and `review_queue` tables
- [x] 7.2 Update `app/nlp.py` — rearchitect system prompt to output the unified multi-intent schema with confidence scoring and needs_review flags
- [x] 7.3 Create `app/snapshot_agent.py` — implement business health snapshots
- [x] 7.4 Update `app/reporting_agent.py` — enhance report aggregates to fetch receivables, payables, and top-selling product
- [x] 7.5 Update `app/agent_router.py` — enforce idempotency checking, confidence scoring filters, human review queueing, and multi-intent split-routing execution
- [x] 7.6 Update `app/routes.py` — extract message IDs from WhatsApp webhook and pass to AgentRouter
- [x] 7.7 Update `tests/test_transaction_agent.py` — add comprehensive tests verifying idempotency, review queueing, split intents, snapshots, and extended reports
- [x] 7.8 Commit and push everything to branch on GitHub

## 8. Definitive Agent Architecture (Band SDK Integration) ✅
- [x] 8.1 Create `app/band_sdk.py` — implement event pub-sub channel communications
- [x] 8.2 Create `app/agent_1_intake.py` — Intake & Normalizer agent with local parser, low-confidence warning prompts, and ai_logs / review_queue persistence
- [x] 8.3 Create `app/agent_2_ledger.py` — Ledger & Tax agent executing SQL logic (inventory_items/movements, transaction currency)
- [x] 8.4 Create `app/agent_3_cfo.py` — CFO & Escalation agent with health alerts and formatted WhatsApp confirmation outputs
- [x] 8.5 Refactor `app/agent_router.py` — orchestrate agent pub-sub registration and drive inputs via IntakeAgent process loops
- [x] 8.6 Update `tests/test_transaction_agent.py` — align FOS test patches with IntakeAgent namespace
- [x] 8.7 Commit and push all updates to GitHub remote branch `feature/auth-system`

## 9. WhatsApp FOS Upgrade v1.0 (Execution Phase) 🚀
- [x] 9.1 Add `pydantic` to `requirements.txt` and install it.
- [x] 9.2 Update `app/database.py` — run schema migrations incrementally (safe tables renaming, add base_currency, add currency_code, create messages, create new inventory schema, seed default 11 categories).
- [x] 9.3 Update `app/config.py` — expose cost calculation rates.
- [x] 9.4 Update `app/nlp.py` — capture prompt & completion token usage metrics inside OpenAI API response wrapper.
- [x] 9.5 Update `app/validators.py` — implement Pydantic V2 schemas (`TransactionModel`, `InventoryModel`, `DebtModel`, `ReportModel`, `UnifiedResponseModel`) and wrappers.
- [x] 9.6 Update `app/agent_router.py` — intercept active session validation checks, check duplicate messages, manage processing webhook events state.
- [x] 9.7 Update `app/agent_1_intake.py` — implement pre-classification keyword matching rules, Pydantic response validation, dynamic cost tracking, and time profiling.
- [x] 9.8 Update `app/agent_2_ledger.py` — wrap all writes in transactions (rollback on exception), execute Pydantic validations before writes, write inventory items & movements.
- [x] 9.9 Update `app/agent_3_cfo.py` — format final user confirmations and run proactive alert checks (low stock, high outstanding debt).
- [x] 9.10 Update `app/routes.py` — audit history log (incoming and outgoing messages in messages table).
- [x] 9.11 Update `tests/test_transaction_agent.py` — add test cases (SDK routing, pre-classification, validation, session intercept, token cost tracking).
- [x] 9.12 Run tests, verify FOS upgrade builds cleanly, and push all changes to GitHub branch.

