<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 03 — Internal research

Existing assets, prior work, current constraints relevant to Harden the multi-agent conversational pipeline (off-topic guardrails, compound multi-intent execution, fuzzy inventory matching) and build a platform stakeholder dashboard for AI fleet monitoring and compliance governance.. Cite by `path:line` (or by document title + section for non-file references).

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: review · 2026-09-14T17:09:31Z -->
### 1. Ingestion Pipeline & LLM Fallback (No Pre-Filter)
- `app/agents/agent_1_intake.py:430-449` — Any user message failing regex fast-paths routes directly into `parse_message()`. Unrecognized queries (e.g. poetry, coding, general trivia) trigger 3 retry attempts of LLM calls, logging cost to `ai_logs` without business justification.
- `app/agents/agent_1_intake.py:480-495` — When `confidence < 0.7` or `needs_review`, it generates a standard guidance string, but only *after* paying for the token round-trip.
- `app/agents/agent_1_intake.py:548-552` — Any message with a mutating intent enters `_store_pending()`, awaiting `YES/NO` confirmation. If the message also contained a read-query (e.g. "what is my balance"), the pending state only serializes the write intent; the query intent is lost upon confirmation.

### 2. NLP System Prompt & Entity Extraction
- `app/services/nlp.py:28-85` — `build_system_prompt()` passes categories from `get_categories_for_user(user_id)`, but does NOT pass known inventory items. The model must guess whether an informal phrase (*"bag of short grain"*) matches an existing product or is a new item.
- `app/services/nlp.py:66-67` — Intent 7 ("unknown") is described briefly (*"If message doesn't relate to financial systems"*), but lacks explicit adversarial defense against jailbreak instructions or creative text generation.

### 3. Ledger Multi-Intent Dropping in `split_routing`
- `app/agents/agent_2_ledger.py:540-580` — `_process_inventory()` uses strict SQL equality:
  `SELECT id, unit FROM inventory_items WHERE business_id = %s AND item_name = %s LIMIT 1`
  Fails on pluralization differences, extra spaces, or case variations.
- `app/agents/agent_2_ledger.py:427-440` — When `split_routing` executes, it only loops through:
  `transactions = parsed_data.get('transactions', [])`
  `inventory = parsed_data.get('inventory', [])`
  `debts = parsed_data.get('debts', [])`
  It completely ignores `parsed_data.get('query')` or `parsed_data.get('report')`.

### 4. CFO Response Composition
- `app/agents/agent_3_cfo.py:144-190` — In `split_routing`, CFO formats lines for `txs`, `invs`, and `debts`. It has no handling for `query_result` or `report_result`, so users asking compound questions never get an answer to their read question in the chat response.

### 5. Inventory Query Divergence
- `app/data/queries.py:364-397` — `query_stock_levels()` calculates stock via `inventory_movements` joined with `inventory_items`.
- `app/agents/inventory_agent.py:76-80` — Legacy reads use `SELECT id, quantity, unit FROM products WHERE user_id = %s AND name = %s`.
- Items added under one schema but queried under another produce apparent zero stock or "not found" errors.

### 6. Available Observability & Governance Data Models
- `app/data/models.py:249-263` — `AiLog` records `model_name`, `original_message`, `confidence_score`, `estimated_cost`, `processing_time_ms`, and `created_at`. All data required for the FinOps dashboard is already persisting in production!
- `app/data/models.py:215-223` — `ReviewQueue` records `user_id`, `raw_text`, `parsed_payload`, and `created_at`.
- `app/data/models.py:224-234` — `PendingConfirmation` holds active FSM confirmations.
- `app/data/models.py:110-134` — `Transaction` records hold `amount`, `currency`, `user_id`, and `transaction_date` for GMV and merchant volume metrics.
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — audited file locations and line numbers in the existing codebase proving the root causes of the 3 conversational bugs and validating the data availability for the stakeholder dashboard.

