# TaLi — Critical Bugs & Gaps

_Original review 2026-06-03. **Re-audited 2026-06-04** against the current code._

> **Architecture note:** the message pipeline has been rebuilt since the first
> review. `routes.py` now dispatches to `agent_router.py`, which fans out through
> a Band-SDK pub/sub into `agent_1_intake` → `agent_2_ledger` → `agent_3_cfo`
> (plus `debt_agent`, `snapshot_agent`). The original `TransactionAgent`,
> `ReportingAgent` and `InventoryAgent` still exist and run **downstream** of the
> new agents (e.g. `agent_2_ledger.py:206` calls `TransactionAgent`,
> `agent_3_cfo.py:67` calls `ReportingAgent`). Line numbers and statuses below
> reflect the current tree.

**Status legend:** ✅ fixed · 🟡 partially fixed · ❌ open

## 🔴 Critical bugs

### 1. 🟡 Access codes aren't bound to the sender — account takeover
**File:** `app/auth.py:244-269` (`validate_access_code`)

**Progress:** atomic single-use is now enforced — the code is claimed with
`UPDATE … SET used = TRUE WHERE code = %s AND purpose='login' AND used=FALSE AND
expires_at > NOW()` and returns `"reuse_or_expired"` when `rowcount == 0`
(`auth.py:252-261`). That closes the replay / double-spend window.

**Still open:** the lookup is **still not scoped to the sender's phone** — both
the claim (`auth.py:253-257`) and the follow-up `SELECT phone_number …`
(`auth.py:264-269`) match on `code` alone. A 6-digit code issued for user A can
still be claimed by sender B, linking B's WhatsApp to A's account. There is also
still **no per-sender attempt limit**.

**Fix:** scope the claim/lookup to the sender's phone (`sender_id` *is* the Meta
phone number) and cap failed attempts.

### 2. ❌ No webhook signature verification
**File:** `app/routes.py:126-138` (`webhook`)

`/webhook` still accepts any POST — no `X-Hub-Signature-256` HMAC check anywhere
in `app/` (grep confirms). Anyone with the URL can inject messages/transactions
for any sender with a session, or flood the endpoint.

**Fix:** verify the HMAC signature against the app secret before processing.

### 3. ❌ First login is impossible for a freshly-registered user
**Files:** `app/routes.py:26-42` (`handle_login`), `app/auth.py:149` (`get_user_by_sender`)

`handle_login` still only calls `get_user_by_sender`, which JOINs
`whatsapp_accounts` — empty until the first successful `validate_access_code`. A
newly-registered user who sends "login" still hits the "register first" dead end.
(`create_pending_session` was added at `routes.py:33` but the lookup gap remains.)

**Fix:** fall back to `get_user_by_phone(sender)` when no link exists yet.

### 4. 🟡 Reports & clarifications still send raw JSON to users
**Files:** `app/agent_3_cfo.py:65-71` & `~120`, `app/reporting_agent.py:136,139`, `app/inventory_agent.py:30+`

**Progress:** transaction confirmations are now formatted nicely in the CFO agent
(`✅ Recorded: … ₦…`, `agent_3_cfo.py:83-87`).

**Still open:** the report path returns `reporting_agent.generate_report(...)`
**verbatim**, which is `json.dumps(...)` (`reporting_agent.py:136,139`) — a user
asking for a "monthly report" still gets a JSON blob. `split_routing`
clarifications also `return json.dumps(val, …)` (`agent_3_cfo.py:~120`), and
`inventory_agent` returns `json.dumps` throughout. `formatter.py` still has **no**
`format_report` / `format_inventory`.

**Fix:** add `format_report()` / `format_inventory()` and have the CFO agent
return display text, not JSON.

### 5. 🟡 Dedup added; processing still synchronous
**Files:** `app/routes.py:148,165-171,208`, `app/agent_router.py` (`route`), `app/database.py:257` (`webhook_events`)

**Progress:** message dedup is now implemented — `message_id` is captured
(`routes.py:148`), a `webhook_events` table with a unique `whatsapp_message_id`
backs an `INSERT IGNORE` (`routes.py:165-171`), and the router drops repeats via
`__DUPLICATE_DROP__`. This prevents the double-record on Meta retries.

**Still open:** the webhook still calls OpenAI **synchronously before returning
200** (`routes.py:137-214`), so a slow model call can still trigger Meta retries
(now deduped, but latency/timeout risk remains).

**Fix:** ack 200 immediately and process asynchronously (queue/worker/thread).

## 🟠 Security & correctness

- **6. ❌ No rate limiting** — registration OTP (paid template sends), login
  attempts and `/webhook` are all unthrottled (no limiter in `app/` or deps).
- **7. ❌ UTC vs DB-local timezone mismatch** (`auth.py:26,177,298,349`) — expiries
  are computed with `datetime.utcnow()` but compared against MySQL `NOW()`
  (`get_active_session` at `auth.py:337`). Windows drift if the DB isn't on UTC.
- **8. ❌ Non-text messages crash silently** (`routes.py:146`) —
  `message['text']['body']` raises `KeyError` on image/voice/sticker; caught by
  the broad `except` (#9), so the user gets no reply.
- **9. ❌ Broad `except Exception` swallows everything** (`routes.py:210`, plus a
  second swallow at `routes.py:173`) — failures produce silence, not a fallback.
- **10. ❌ Fast-path records bare numbers as expenses**
  (`transaction_agent.py:43` `process_fast_path`, still reachable via
  `agent_2_ledger.py:206-208`) — a lone `500` or `2024` still books a
  Miscellaneous expense.

## 🟡 Reliability & architecture

- **11. ❌ New DB connection per operation, no pooling** (`database.py:5`) — and the
  new agent pipeline multiplies connections per message.
- **12. ❌ `send_reply` has no timeout / error handling** (`whatsapp.py:18,79`) — a
  bare `requests.post` can hang the worker.
- **13. ❌ `print()` instead of `logging`** — no `logging` import anywhere in `app/`.
- **14. ❌ Legacy `records` double-write truncates decimals** (`queries.py:67`,
  `int(amount)`).
- **15. ❌ Inventory stock update is a read-modify-write with no lock**
  (`inventory_agent.py:94-109`) — concurrent messages can race.

## 🟢 Testing & tooling

- **16. ❌ Risky code is untested — and the gap is now much larger.** Only
  `tests/test_transaction_agent.py` exists. The entire new architecture
  (`agent_router`, `band_sdk`, `agent_1/2/3`, `debt_agent`, `snapshot_agent`,
  `auth`) has zero tests.
- **17. ❌ Unpinned dependencies** (`requirements.txt` — now adds `pydantic`, still
  no versions).
- **18. ❌ Missing hygiene** — no `README`, no `.env.example`, no CI; `SECRET_KEY`
  still has a hardcoded dev default (`config.py:8`).

## Recommended fix order

1. **#1 (sender binding) + #2 (signature verification)** — still exploitable today.
2. **#3 (first-login dead-end) + #4 (report JSON)** — break core UX right now.
3. **#5 (async ack)** — dedup is done; decoupling processing removes the last
   retry/timeout risk.
4. Reliability (#11, #12) and tests (#16) — the test gap grew with the refactor.
