# Implementation Plan: WhatsApp Financial Operating System (FOS) Upgrade v1.0 (Revised)

We will upgrade the Bookkeeper system into a production-grade WhatsApp Financial Operating System (FOS). This plan has been updated to address critical reviews around Band SDK integration, the explicit addition of the CFO Agent (Agent 3), webhook session verification, dynamic AI cost estimation, and transaction boundaries.

---

## User Review Required

> [!IMPORTANT]
> **Band SDK Orchestration**: We will explicitly route state and context between the three agents via the `BandSDK` event broker channels, rather than direct Python function calls:
> - **Channel `"intake_to_ledger"`**: Agent 1 (Intake) publishes validated JSON payloads to this channel. Agent 2 (Ledger) subscribes to it.
> - **Channel `"ledger_updates"`**: Agent 2 (Ledger) publishes transaction outcomes to this channel. Agent 3 (CFO) subscribes to it.
> - **Channel `"cfo_escalation"`**: Agent 1 (Intake) publishes low-confidence or clarification payloads directly to this channel. Agent 3 (CFO) subscribes to it.
> 
> **Explicit Agent 3 (CFO Agent) Collaboration**: 
> Agent 3 (`app/agent_3_cfo.py`) will listen for updates in the Band room. It will:
> - Receive updates on the `"ledger_updates"` and `"cfo_escalation"` channels.
> - Format the final user-facing message with emoji layouts.
> - Proactively monitor stock levels (checking if new stock level <= 5) and outstanding debts (checking if balance > ₦50,000) to append warning highlights.
> 
> **Web-OTP Auth Verification in Router**:
> Before any incoming message is sent to Agent 1 (Intake), `AgentRouter.route` will query the `sessions` table via `get_active_session(sender_id)`. If the session is inactive or missing, it will return the standard auth prompt: `"🔒 You need to log in first.\n\nType *login* to get started."`
> 
> **Dynamic AI Cost Estimation**:
> Pricing rates will be defined in `config.py` (via environment variables). The OpenAI response parser will extract actual token usage metrics (`prompt_tokens`, `completion_tokens`) and calculate the exact cost dynamically before saving to `ai_logs`.
> 
> **SQL Transaction Boundaries**:
> To prevent partial updates and data synchronization issues, all multi-table ledger writes (e.g. updating inventory items and writing movements) will be wrapped in a single database transaction block:
> - Execute `conn.start_transaction()`
> - Perform database queries
> - Call `conn.commit()`
> - On any error, catch the exception, execute `conn.rollback()`, and raise the error.

---

## Proposed Changes

### 1. Configuration & Cost Tracking

#### [MODIFY] [config.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/config.py)
- Expose default token pricing constants for `gpt-4o-mini`:
  ```python
  OPENAI_INPUT_COST_PER_MILLION = float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "0.150"))
  OPENAI_OUTPUT_COST_PER_MILLION = float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "0.600"))
  ```

#### [MODIFY] [nlp.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/nlp.py)
- Update `parse_message(text, user_id)` to extract and append OpenAI token usage metrics in the response dictionary:
  ```python
  parsed['_usage'] = {
      'prompt_tokens': response.usage.prompt_tokens,
      'completion_tokens': response.usage.completion_tokens,
      'total_tokens': response.usage.total_tokens
  }
  ```

---

### 2. Database Schema & Migrations

#### [MODIFY] [database.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/database.py)
- Update `init_db(app)` to run migrations incrementally:
  - Check and add `base_currency VARCHAR(3) DEFAULT 'NGN'` to `users`.
  - Check and add `currency_code VARCHAR(3) DEFAULT 'NGN'` to `transactions`.
  - Check `webhook_events`: if legacy `message_id` table exists, rename to `webhook_events_legacy` and create new `webhook_events` table with `whatsapp_message_id`, `payload`, `status` ENUM, and `processed_at`.
  - Check `ai_logs`: if legacy table exists, rename to `ai_logs_legacy` and create new `ai_logs` table matching the v1.0 schema (with `model_name`, `original_message`, `confidence_score`, `estimated_cost`, `processing_time_ms`).
  - Create `inventory_items` and `inventory_movements` (v1.0 schema) if not present.
  - Create `messages` table if not present.
  - Seed the requested 11 default categories.

---

### 3. Verification & Session Logic

#### [MODIFY] [agent_router.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/agent_router.py)
- **Session Verification**: Import `get_active_session` from `app.auth`. Check if an active session exists for `sender_id`. If not, return the login prompt without proceeding to Agent 1.
- **Idempotency Flow**:
  - Search `webhook_events` for `whatsapp_message_id`. If state is `'processing'` or `'processed'`, return duplicate JSON.
  - Insert webhook tracking row with status `'processing'`.
  - Execute agents via the Band SDK.
  - Update webhook tracking row with status `'processed'` (on success) or `'failed'` (on exception) and commit.

---

### 4. Agent 1: Intake & Normalizer

#### [MODIFY] [agent_1_intake.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/agent_1_intake.py)
- **Local Routing Decision Rule**: Before running OpenAI, test keywords:
  - If text contains `report` or `summary` -> publish custom report parameters to `"intake_to_ledger"`.
  - If text contains `snapshot` or `how is my business` -> publish snapshot parameter to `"intake_to_ledger"`.
  - If text is a single-word shorthand (e.g. `2k`, `5h`, `10000`) -> parse locally and publish to `"intake_to_ledger"`.
- Fallback to OpenAI API parsing:
  - Validate response format using Pydantic models.
  - If `confidence` < 0.7 or `needs_review` is true, write message to `review_queue`, publish to `"cfo_escalation"`, and return the escalation text.
  - Compute cost: `(prompt_tokens * input_rate) + (completion_tokens * output_rate)`. Log data in `ai_logs` alongside API time elapsed in milliseconds.

---

### 5. Agent 2: Ledger & Tax

#### [MODIFY] [agent_2_ledger.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/agent_2_ledger.py)
- **SQL Transaction Boundaries**: Wrap all writes in a database transaction block. On database error, issue a `conn.rollback()` before propagating the exception.
- **Inventory Updates**: Parse input using `InventoryModel` Pydantic schema. Write items to `inventory_items` and stock movements to `inventory_movements` (mapping actions to `stock_in`, `stock_out`, and `adjustment`).
- **Debt Updates**: Parse input using `DebtModel` Pydantic schema. Maintain outstanding debt totals inside the `debt_balances` table and audit details in `debt_logs`.
- **Publication**: Publish results to `"ledger_updates"` channel.

---

### 6. Agent 3: CFO & Anomaly Detection

#### [MODIFY] [agent_3_cfo.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/agent_3_cfo.py)
- Listen to `"ledger_updates"` and `"cfo_escalation"`.
- Formulate user confirmations with localized emoji formatting.
- **Proactive Alerts**: Extract inventory changes and outstanding debt. If inventory remaining <= 5 or debt > ₦50,000, append alert warning indicators to the final message response.

---

### 7. Historical Audit Log

#### [MODIFY] [routes.py](file:///c:/Users/chris/OneDrive/Desktop/bookkeeper/app/routes.py)
- Insert every incoming WhatsApp body and outgoing response string into the `messages` table for a complete user communication audit log.

---

## Verification Plan

### Automated Tests
- Run existing transaction agent tests:
  ```powershell
  python -m unittest tests/test_transaction_agent.py
  ```
- Add test suites in `tests/test_transaction_agent.py` to cover:
  - Band SDK event broker publication and subscriber routing.
  - Agent Router local keyword rules.
  - Pydantic models.
  - Dynamic cost estimation logging.
  - Web-OTP session intercept in `AgentRouter`.
