<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 03 — Internal research

Existing assets, prior work, current constraints relevant to Bridge the Band of Agents hackathon gaps: make Band the real coordination layer for 3+ agents, route models across AI/ML API + Featherless with OpenAI fallback, turn the sequential chain into a plan->execute->review loop, and surface a regulated-track audit trail.. Cite by `path:line` (or by document title + section for non-file references).

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-13T12:52:37Z -->
### The "Band" layer is an in-memory stub, not the platform

- `app/agents/band_sdk.py:5-35` — `BandSDK` is a class with a `_subscribers` dict + `subscribe`/`publish`/`clear_subscriptions` classmethods. `publish` synchronously calls each subscriber callback in-process and collects return values. No network, no band.ai.
- `docs/agent_setup.md:9,93` — the team's own docs: "All agents communicate internally via the Band SDK pub/sub event broker… in-memory." Confirms it's not the platform.
- `requirements.txt:1-11` — has `openai`, `Flask`, `mysql-connector-python`, etc.; **no `band-sdk`**.
- Concurrency hazard: `BandSDK._subscribers` is global class state cleared per request (`agent_router.py:46`) — not thread-safe under multiple workers. Extra reason to retire it (WP-06).

### The flow is a synchronous linear chain

- `app/agents/agent_router.py:46-57` — wires `intake_to_ledger → ledger.handle_intake_payload`, `ledger_updates → cfo.handle_ledger_update`, `cfo_escalation`/`ledger_errors → cfo` on every request, then calls `intake.process(text)`.
- `agent_1_intake.py:706` publishes `intake_to_ledger`; `agent_2_ledger.py:156,330` publishes `ledger_updates`; `agent_3_cfo.py:18` consumes it. Unidirectional Intake→Ledger→CFO; CFO only *formats*, never *reviews*. No planning step, no agent recruits peers.

### Single-model NLP; the escalation signal already exists

- `app/services/nlp.py:7` `get_openai_client()` → the one factory to generalize. `nlp.py:196-205` makes the single `chat.completions.create` call with `OPENAI_MODEL`.
- `app/config.py:41-42` — only `OPENAI_API_KEY` / `OPENAI_MODEL` (`gpt-4o-mini`); no AI/ML or Featherless config.
- `agent_1_intake.py:374` — `if confidence < 0.7 or needs_review:` — the natural cheap→frontier escalation trigger to reuse in WP-01.
- `.env.example:39-43` — only the OpenAI block; needs AI/ML + Featherless + Band creds added (WP-01/02).

### The audit/enterprise plumbing already exists (reuse, don't rebuild)

- Idempotency: `processed_events` (per-agent dedup) — `agent_2_ledger.py:64-71,302-306`, `agent_3_cfo.py:37-48`.
- Webhook dedup state machine: `webhook_events` (received→processing→processed/failed) — `agent_router.py:64-94`.
- Dead-letter saga: `ledger_errors` channel + `CFOAgent.handle_ledger_error` — `agent_2_ledger.py:384,421`, `agent_3_cfo.py:156-171`.
- AI cost logging: `ai_logs` (model, estimated_cost, processing_time_ms, confidence) — `agent_1_intake.py:595-634`.
- Human review queue: `review_queue` — `agent_1_intake.py:636-655`.
- Confirm-before-write: `_store_pending` / `pending_confirmations` — `agent_1_intake.py:501-534`.
- Thresholds (anomaly signals for the Compliance agent to reuse): `agent_3_cfo.py:173-214` `_get_evaluated_thresholds` (low_stock / high_debt / large_expense).
- Correlation IDs + schema_version on every event: `app/agents/event_schemas.py:11-21` `BaseBandEvent`. Maps onto Band messages 1:1 (WP-02 reuse).

### Migration base for git history

- The repo was just re-initialised to a clean 25-commit history (June 12–14); the hackathon work lands on top. Backup bundle at `../tali-history-backup.bundle`.
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you went looking for inside the existing system / org / archive and why. The research action does not touch this section.
