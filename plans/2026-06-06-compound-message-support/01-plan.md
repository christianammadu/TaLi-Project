<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Support multiple transactions/inventory/debts per WhatsApp message, plus clean up the obsolete 0004 UUID migration and stamp Alembic.

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-06-06 -->
Support multiple transactions/inventory/debts per WhatsApp message, plus clean up the obsolete 0004 UUID migration and stamp Alembic.
<!-- groundwork:auto:end goal -->

## Context

Over this session we got the bot fully working end-to-end: the OpenAI key + `httpx` pin restored NLP, the INT→UUID migration fixed login/OTP and the FK logging errors, the inventory/debt `.get()` crash is fixed, queries are wired, and a confirm-before-record step now shows users a breakdown before committing.

Two gaps remain:

1. **Compound messages can't be represented.** `UnifiedResponseModel` (`app/services/validators.py:187`) has exactly **one** `transaction`, **one** `inventory`, **one** `debt` slot. A message with two independent events — e.g. *"Bought 6 bags of rice at 400 per one and sold 4 for 6000"* (a purchase **and** a sale, +6 then −4 stock) — cannot be captured. The LLM is forced to drop or conflate one side. For a real bookkeeping ledger this is a correctness gap, not a nicety: a dropped purchase means the books don't balance.
2. **The obsolete `0004_uuid_migration.py` is a landmine.** The live DB was migrated to UUIDs by `scripts/migrate_int_to_uuid.py`, *not* by Alembic. Alembic has never been stamped, so a future `alembic upgrade head` would run `0004`'s broken logic (references non-existent `records`/`stock_movements` shapes, does an ASCII-cast type change with `FOREIGN_KEY_CHECKS=0`) against a live UUID DB.

What's at stake: bookkeeping accuracy (every economic event must land as its own ledger row, stock delta, and/or debt entry) under the hard constraint that **the only interface is WhatsApp plain text** — no UI, monospace-only formatting, and the user confirms via `YES`/`NO`.

## Architecture

The pivot is turning the unified NLP response from **single-slot** to **list-based**, then threading lists through every stage of the existing synchronous Band pipeline (Intake → Ledger → CFO). Nothing about the orchestration changes; only the cardinality of the payload.

```
WhatsApp text
  → IntakeAgent.process            (regex fast-path OR LLM parse_message)
  → UnifiedResponseModel           transactions:[], inventory:[], debts:[]   ← cardinality change
  → confirm-before-record          format_confirmation renders N sections    ← loop
  → pending_confirmations          (unchanged — stores the list payload as-is)
  → YES → _publish_intake          → BandSDK "intake_to_ledger"
  → LedgerAgent.handle_intake_payload
       for tx in transactions:  INSERT (own event_id)                        ← loop, atomic
       for inv in inventory:    _process_inventory (own event_id)            ← loop
       for d in debts:          _process_debt (own event_id)                 ← loop
  → BandSDK "ledger_updates" → CFOAgent renders N-line reply                 ← loop
```

Bookkeeping correctness rules baked into the design:
- **Atomicity** — all items in one message commit inside a single DB transaction; any failure rolls back the whole message (no half-recorded compound entry).
- **Idempotency** — the ledger dedups on `event_id` (`processed_events`, plus `UNIQUE event_id` on `transactions`/`inventory_movements`/`debt_*`). Multiple items now share one `IntakePayload.event_id`, so each item needs a **deterministic per-item suffix** (`{event_id}:tx{i}`, `:inv{i}`, `:debt{i}`) or the second INSERT collides. This is the single most important correctness detail.
- **Net stock** — a buy then sell of the same product produces two movements (+6, −4); the displayed/queried level is the SUM of movements, which already works in `_process_inventory`.

### Shared state contract

| Field | Type | Writer | Readers |
|---|---|---|---|
| `UnifiedResponseModel.transactions` | `List[TransactionModel]` | `parse_message` / validator | confirmation formatter, ledger loop |
| `UnifiedResponseModel.inventory` | `List[InventoryModel]` | validator | formatter, ledger loop, CFO low-stock check |
| `UnifiedResponseModel.debts` | `List[DebtModel]` | validator | formatter, ledger loop, CFO high-debt check |
| per-item `event_id` | `str` (`{base}:{kind}{i}`) | ledger loop | `processed_events`, item UNIQUE constraints |
| `pending_confirmations.parsed_json` | JSON (the list payload) | `IntakeAgent._store_pending` | `_apply_confirmation` replay |
| `LedgerUpdateData.{transactions,inventory,debts}` | lists of result models | ledger | CFO reply formatter |

## Phases

> **Detail scales with proximity.** Phase 1 is fully detailed; Phase 2 is independent and self-contained.

### Phase 1 — Multi-item (compound message) support

Convert the schema and pipeline to lists, end to end. Concrete tasks:

1. **Schema** (`validators.py`) — add `transactions: List[TransactionModel] = []`, `inventory: List[InventoryModel] = []`, `debts: List[DebtModel] = []` to `UnifiedResponseModel`. Keep the singular `transaction`/`inventory`/`debt` fields temporarily and add a `model_validator` that folds a singular into its list (back-compat for any cached/pending payloads and the regex fast-paths that still emit singular). New code reads only the lists.
2. **Prompt** (`nlp.py`) — change the unified JSON schema so `transactions`/`inventory`/`debts` are arrays; give the compound worked example ("Bought 6 … and sold 4 …" → two transactions + two inventory movements). Bump `max_tokens` (currently 300 — too small for multi-item JSON; raise to ~700).
3. **Ledger** (`agent_2_ledger.py`) — turn the three single `if` blocks (lines ~220/271/282) into loops over the lists, each item with its own suffixed `event_id`; accumulate `results['transactions']`/`['inventory']`/`['debts']` as lists; keep the whole message in one transaction/commit. Update `LedgerUpdateData` to carry lists.
4. **Confirmation breakdown** (`formatter.py`) — `format_confirmation` already iterates per-section; extend to loop N transactions / N inventory / N debts, numbering them (`Transaction 1`, `Transaction 2`).
5. **CFO reply** (`agent_3_cfo.py`) — the `split_routing` reply builder loops over result lists; warnings (low-stock / high-debt / large-expense) evaluate per item.
6. **Intake interception** (`agent_1_intake.py`) — `MUTATING_INTENTS` check already keys off `intents`; no change beyond reading lists.

### Phase 2 — Alembic / `0004` cleanup (independent)

Make Alembic consistent with the UUID DB the script produced, so `alembic upgrade` is safe.

- Rewrite `migrations/versions/0004_uuid_migration.py` `upgrade()`/`downgrade()` to **no-ops** (the conversion is done out-of-band by `scripts/migrate_int_to_uuid.py`; record that in a docstring), OR delete it and re-baseline.
- `alembic stamp head` on the live DB so Alembic's `alembic_version` matches reality without re-running DDL.
- Add `pending_confirmations` to the Alembic baseline/models so a fresh environment built via Alembic matches `database.py`.
- Document the dual-schema reality (startup `database.py` `CREATE TABLE IF NOT EXISTS` vs. Alembic) in the migration docstring / README so the next person doesn't run the wrong one.

## Schema / contract

The freeze gate for Phase 1 is the new `UnifiedResponseModel` shape (the contract every downstream stage reads). Draft target:

```python
class UnifiedResponseModel(BaseModel):
    intents: List[str] = Field(default_factory=list)
    confidence: float
    needs_review: bool = False
    status: Literal['ok', 'clarification_needed', 'error', 'unknown'] = 'ok'
    question: Optional[str] = None
    transactions: List[TransactionModel] = Field(default_factory=list)
    inventory: List[InventoryModel] = Field(default_factory=list)
    debts: List[DebtModel] = Field(default_factory=list)
    report: Optional[ReportModel] = None
    query: Optional[QueryModel] = None
    snapshot: bool = False
    # back-compat: fold legacy singular {transaction, inventory(dict), debt} into the lists
```

`report`/`query`/`snapshot` stay singular (a message asks one question / one report). Only the mutating events pluralize.

## Critical files

### `bookkeeper/`

- `app/services/validators.py` — extend `UnifiedResponseModel` to lists + back-compat folder validator
- `app/services/nlp.py` — prompt arrays + compound example + raise `max_tokens`
- `app/agents/agent_2_ledger.py` — loop the transaction/inventory/debt blocks; per-item `event_id`; lists in `results`
- `app/agents/event_schemas.py` — `LedgerUpdateData` carries `List[...]` results
- `app/agents/agent_3_cfo.py` — `split_routing` reply + warnings loop over lists
- `app/services/formatter.py` — `format_confirmation` numbers multiple sections
- `migrations/versions/0004_uuid_migration.py` — no-op / delete (Phase 2)
- `app/data/models.py` — already has `PendingConfirmation`; ensure Alembic baseline includes it (Phase 2)

## Reuse map — what we lift, reimplement, or drop

| Concern | Strategy | Source / target | Notes |
|---|---|---|---|
| Per-item inventory write | **Reuse** | `_process_inventory` (already dict-based) | call once per inventory item in the loop |
| Per-item debt write | **Reuse** | `_process_debt` (already dict-based) | call once per debt item |
| Confirmation rendering | **Extend** | `format_confirmation` (already sectioned) | wrap each section type in a loop with an index label |
| Singular→list compat | **Build fresh** | `model_validator` in `UnifiedResponseModel` | one place; lets regex fast-paths keep emitting singular |
| UUID type conversion | **Drop (Alembic)** | `0004_uuid_migration.py` | superseded by `scripts/migrate_int_to_uuid.py`; no-op it |

## Renderer / adapter contracts

No pluggable seams. The one interface contract is `UnifiedResponseModel` (above) — it gates the ledger, formatter, and CFO simultaneously, so it must be locked before those three are touched.

## Risks + alternatives

- **Idempotency collision (highest).** One `IntakePayload.event_id` now spawns N writes; without per-item suffixes the second item's `UNIQUE event_id` INSERT fails and rolls back the whole message. Mitigation: deterministic `{event_id}:tx{i}` / `:inv{i}` / `:debt{i}`. Verify with a replayed (duplicate) compound message → no double-record.
- **LLM mis-parse of compound math.** "6 at 400" = 2400; "sold 4 for 6000" = 6000. The model may miscount or merge. Mitigation: the confirmation breakdown is the safety net (user sees N entries, replies NO if wrong). This is *why* compound support and confirmation ship together.
- **Output truncation.** `max_tokens=300` truncates multi-item JSON → JSON parse error → retry loop wastes calls. Mitigation: raise to ~700; the validator's retry already handles a bad parse.
- **Back-compat break.** Many readers currently access `parsed.transaction` (singular). Mitigation: keep singular fields with a folding validator during transition; grep every `.transaction`/`.inventory`/`.debt` reader and migrate to lists; the fast-path branches in `agent_1_intake.py` emit singular and rely on the folder.
- **Partial failure mid-list.** If item 3 of 4 fails, the whole message must roll back (no orphaned half-entry). Mitigation: keep the existing single-transaction/commit boundary around the whole loop.
- **Alternative considered — keep singular, ask users to split messages.** Rejected: a bookkeeping tool that silently drops the second event in "bought X and sold Y" is wrong by default; one-message-per-event is a teachable workaround, not a fix.

## ID registry

The full ID registry is in `.groundwork.json.ids`. Local cross-reference index:

<!-- groundwork:auto:start ids -->
<!-- last_action: init · 2026-06-06 -->
_No IDs allocated yet. The review action populates this index._
<!-- groundwork:auto:end ids -->

## Verification

_Per-phase ship gates — concrete, runnable checks. Each item must be observable (a passing test, a green typecheck, a manual screenshot diff, a user-confirmed signal). "Stakeholders are happy" is not a verification item; "DSP smoke test renders the fixture in <10s on a dev box" is._

### Phase 1 verification

1. Send *"Bought 6 bags of rice at 400 per one and sold 4 for 6000"* → confirmation shows **two** transactions (purchase ₦2,400, sale ₦6,000) and **two** inventory movements (+6, −4).
2. Reply `YES` → both transactions recorded; `transactions` table has 2 new rows; rice stock level = SUM of movements = +2.
3. Replay the same compound message (duplicate `message_id`/event) → no double-record (per-item `event_id` idempotency holds).
4. `"what are my purchases?"` reflects the purchase; `"how much did I sell?"` reflects the sale.
5. Single-event messages and regex fast-paths (`sold rice 5000`) still work unchanged (back-compat folder validator).
6. Force a failure on item 2 of a 3-item message → nothing is recorded (atomic rollback).

### Phase 2 verification

1. `alembic current` runs without error and reports `head` after `alembic stamp head`.
2. `alembic upgrade head` on the live UUID DB is a no-op (no DDL, no error).
3. A fresh DB built from Alembic baseline matches the `database.py` runtime schema (including `pending_confirmations`).
