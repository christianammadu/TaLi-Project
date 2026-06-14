<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Bridge the Band of Agents hackathon gaps — TaLi WhatsApp FOS

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-06-13 -->
Bridge the Band of Agents hackathon gaps: make Band the real coordination layer for 3+ agents, route models across AI/ML API + Featherless with OpenAI fallback, turn the sequential chain into a plan->execute->review loop, and surface a regulated-track audit trail.
<!-- groundwork:auto:end goal -->

## Context

_Why now, what changed, what's at stake._

TaLi is a mature WhatsApp Financial Operating System (Intake → Ledger → CFO agents, NLP intake, inventory/debt/reporting, PDF/Excel statements) with genuinely strong enterprise plumbing: idempotency (`processed_events`), webhook dedup state machine (`webhook_events`), retry/backoff, a dead-letter saga channel, AI cost logging (`ai_logs`), a human review queue (`review_queue`), confirm-before-write, and correlation IDs on every event.

It is being entered into the **Band of Agents Hackathon (June 12–19, 2026, deadline 19th 20:30 IST)**. A gap analysis against the rules and the Band (band.ai / Thenvoi) SDK surfaced **one disqualifying gap and three scoring gaps**:

1. **"Band" is not Band.** `app/agents/band_sdk.py` is a 36-line in-memory pub/sub broker — the team's own docs call it that. It never touches the official Band Agent API. The rules require Band to be the *active coordination layer* ("cannot be a thin wrapper"), and the **Application of Technology** judging axis is literally *"how effectively does the solution use Band as the coordination layer."* Today: ~0.
2. **Partner tooling unused.** Only OpenAI `gpt-4o-mini`. AI/ML API ($10) and Featherless ($25) are absent → ~$35 credits and both partner prizes left on the table.
3. **Sequential chain, not collaboration.** Intake→Ledger→CFO are synchronous in-process calls. No planning, no review loop, no shared context.
4. **Enterprise/audit assets not surfaced through Band, no track chosen.** The audit plumbing is a natural fit for the **Regulated & High-Stakes Workflows** track but isn't exposed or routed through Band's unified audit trail.

The MIT licence (a submission requirement) is being handled by the user separately and is out of scope for this plan.

## Architecture

_The shape of the solution at one zoom-out level._

**Current (disqualifying):**
```
WhatsApp webhook → AgentRouter → IntakeAgent.process()
   └─ BandSDK.publish("intake_to_ledger")  [in-process fn call]
        → LedgerAgent → BandSDK.publish("ledger_updates")
             → CFOAgent → returns string
```
One OpenAI model. Linear. `BandSDK` is global mutable class state cleared per request.

**Target:**
```
                       ┌──────────── Band chat room (band.ai / Thenvoi) ────────────┐
WhatsApp webhook ──▶ Gateway ──▶ │  @Intake  ⇄  @Ledger  ⇄  @CFO  ⇄  @Compliance  ⇄  human │
   (drops user msg into room)    │   @mention routing · room message/event log = shared ctx │
                                 │   plan → execute → review → human-approve                 │
                                 └────────────────────────────────────────────────────────────┘
        every agent call routed by role → get_client(role): AI/ML API · Featherless · OpenAI(fallback)
        every action + handoff + model + cost + approval → unified audit trail (ai_logs ⨝ Band)
```

Four specialized agents collaborate in **one Band room** via **@mention routing**. Coordination becomes conversation-driven (Band's documented model), not hardcoded. A new **Compliance/Reviewer agent** validates Ledger's *proposed* writes before commit (the review loop). Model calls are routed per role across three providers. The existing audit tables are joined to Band's unified audit trail and exposed for the regulated track.

> **Key constraint:** the user has **Band Pro**, not Enterprise. Band's cross-agent **Memory API is Enterprise-only**. Shared context therefore rides the **room message/event log + REST context endpoint** (`GET /api/v1/agent/chats/{id}/context`), never the Memory feature.

> **Reply-path constraint (Round 2, G-05/G-11):** today the user-facing reply is produced by *synchronous return-value bubbling* through the broker (`CFO → Ledger(responses[0]) → Intake → AgentRouter.route() → send_reply`). Band `@mention` send is **fire-and-forget**, so WP-02 must freeze a **reply-collection seam**, and we must decide whether `send_reply` moves **into the gateway** (reply collected from the room — keeps Band the active layer) or stays **in the agents** (room becomes a side-channel — weakens the scoring claim). Note the reply path is *already split* today: the dead-letter saga (`agent_3_cfo.py:159`) and statement/document flows call `send_reply`/`send_document` out-of-band.

### Shared state contract

_The cross-component state two or more pieces must agree on._

| Field | Type | Writer | Readers |
|---|---|---|---|
| Band `room_id` (per user/session) | string (UUID) | Gateway (WP-06) | all 4 agents |
| Agent `handle` / `agent_id` + `X-API-Key` | string | Band dashboard registration (WP-02) | each agent's connector |
| Band message/event body (lifted from `event_schemas.py`) | JSON (Pydantic) | publishing agent | mentioned agents |
| `correlation_id` (threads a user msg across agents + audit) | UUID | Intake (origin) | all agents, audit (WP-09) |
| model-router role map `{role → (provider, model)}` | config | WP-01 | all agents |
| provider order + fallback policy | config/env | WP-01 | `get_client(role)` |
| "proposed write" envelope (pre-commit, for review) | JSON | Ledger (WP-04) | Compliance (WP-07), human (WP-08) |

## Phases

> Detail scales with proximity. Phase 1 detailed; Phase 2 sketched; Phases 3–4 stubbed.

### Phase 1 — Foundations & contracts

The two seams everything else depends on. Both are buildable **today** with no dependency on each other, so they run in parallel as the freeze gates.

- **Model router (`WP-01` → `G-MODEL-ROUTER`).** Generalize `app/services/nlp.py:7` `get_openai_client()` into a `get_client(role)` factory. Both AI/ML API and Featherless are OpenAI-compatible (base-URL + key swap), so this is a low-risk change. Role map: high-volume extraction/workers → **Featherless** (Qwen/Mistral); frontier reasoning/orchestration + the existing `confidence < 0.7` escalation (`agent_1_intake.py:374`) → **AI/ML API**; **OpenAI = fallback** on any provider error/timeout. Carry per-provider cost metadata so `ai_logs` stays accurate.
- **Band integration spike + contract (`WP-02` → `G-BAND-CONTRACT`).** Add `band-sdk`, register 3 remote agents on `app.band.ai` (Pro), create a room, prove a message round-trips via `@mention` + a REST context read. Freeze the connector seam (how an agent connects, sends, receives, reads context) the agent ports will build against.

### Phase 2 — Port agents onto Band, retire the broker (sketch)

Gated by `G-BAND-CONTRACT`. Port Intake / Ledger / CFO to send/receive through Band instead of `BandSDK.publish` (`WP-03/04/05`, parallel, disjoint files). Then replace `AgentRouter` with a **gateway** that drops the inbound WhatsApp message into the room and delete the in-memory broker (`WP-06`). Open question: persistent WebSocket agents (`await agent.run()`) vs request-scoped REST posting — decide in WP-02.

### Phase 3 — Collaboration loop + regulated-track audit (stub)

Add the **Compliance/Reviewer** agent (4th agent, Featherless model) that reviews proposed Ledger writes pre-commit (`WP-07`); route confirm-before-write + `review_queue` as a **human-in-the-loop** approval in the room (`WP-08`); surface the **unified audit trail** for the regulated track (`WP-09`); add **FinOps per-model cost attribution** (`WP-10`).

### Phase 4 — Submission polish (stub)

Deploy, public repo, 5-min demo video built around the live Band room showing plan→execute→review→human-approve→audit (`WP-11`). MIT licence added by the user.

## Schema / contract

The pivotal freeze artifacts:
- **`G-BAND-CONTRACT`** — the Band connector seam, **four** elements: (1) agent registration (handle, `agent_id`, `X-API-Key`); (2) send (`thenvoi_send_message` / `@mention`); (3) receive (adapter `on_message`); (4) **reply collection (Round 2, G-05)** — how the gateway blocks on a `correlation_id` / terminal room message (via `read_context`) and returns the final reply to the *synchronous* WhatsApp caller, since `@mention` send is fire-and-forget with no return value. Reuses `app/agents/event_schemas.py` Pydantic bodies as message payloads. Frozen by WP-02 before WP-03/04/05 start.
- **`G-MODEL-ROUTER`** — the `get_client(role)` signature, the role→provider map, and the provider-order/fallback policy (**fallback fires on timeout *and* 429/quota**, Round 2). Frozen by WP-01 before agents adopt it.

## Critical files

### `tali/` (this repo)

- `app/agents/band_sdk.py` — **delete** (in-memory broker) once WP-06 lands.
- `app/agents/agent_router.py` — **replace** with the Band gateway (WP-06).
- `app/agents/transaction_agent.py` — **retire** its `AgentRouter().route()` fallback (`:31-33`) — a hidden dependent of the router replaced in WP-06 (G-09).
- `app/agents/agent_1_intake.py`, `agent_2_ledger.py`, `agent_3_cfo.py` — **port** off `BandSDK.publish` onto Band send/receive (WP-03/04/05).
- `app/agents/event_schemas.py` — **reuse** as Band message/event bodies (no rewrite).
- `app/agents/band/` — **new** package: `band_client.py` connector + agent registration/config (WP-02).
- `app/agents/compliance_agent.py` — **new** 4th agent (WP-07).
- `app/services/model_router.py` — **new** `get_client(role)` factory (WP-01).
- `app/services/nlp.py` — **extend** to call the router instead of `get_openai_client()` (WP-01).
- `app/services/audit.py` — **new** unified-audit surfacing over `ai_logs`/`processed_events` (WP-09).
- `app/web/whatsapp.py` — **extend** to bridge inbound messages into the Band room (WP-06).
- `app/config.py`, `.env.example` — **extend** with AI/ML, Featherless, Band creds (WP-01/02).
- `requirements.txt` — **add** `band-sdk` (WP-02).

## Reuse map — what we lift, reimplement, or drop

| Concern | Strategy | Source / target | Notes |
|---|---|---|---|
| Event schemas | **Reuse** | `app/agents/event_schemas.py` → Band message/event bodies | `correlation_id`/`event_id`/`schema_version` map 1:1 onto Band messages |
| Audit tables | **Reuse** | `ai_logs`, `processed_events`, `webhook_events`, `review_queue`, `debt_logs` → WP-09 surfacing | already populated; join to Band's audit trail |
| Confidence-escalation signal | **Reuse** | `agent_1_intake.py:374` `confidence < 0.7` → WP-01 router escalation trigger | cheap-worker → frontier escalation |
| Confirm-before-write + review queue | **Reuse** | `_store_pending` / `review_queue` → WP-08 human-in-loop in room | becomes room participant approval |
| OpenAI client factory | **Extend** | `nlp.py:7` `get_openai_client()` → `model_router.get_client(role)` | OpenAI demoted to fallback |
| Band connector | **Build fresh** | `app/agents/band/band_client.py` (WP-02) | wraps `band-sdk` / `thenvoi` |
| Compliance/Reviewer agent | **Build fresh** | `app/agents/compliance_agent.py` (WP-07) | the missing review leg |
| In-memory pub/sub broker | **Drop** | `app/agents/band_sdk.py` removed in WP-06 | replaced by Band room; grep for `BandSDK` importers first |

### Upstream library posture

Net-zero forks. Integrate `band-sdk` / `openai` via their published surfaces; AI/ML API + Featherless via the OpenAI-compatible client (base-URL swap), no SDK forks.

## Renderer / adapter contracts

The one pluggable seam is the **Band framework adapter** (`G-BAND-CONTRACT`): the agents are framework-agnostic Python; the connector exposes `send(mentions, body)`, an inbound `on_message(msg, ctx)` callback, and `read_context(room_id)`. Whether it wraps a built-in `band-sdk` adapter (e.g. `AnthropicAdapter`/`OpenAIAdapter`) or the raw REST/WS surface is decided in WP-02 and frozen before WP-03/04/05.

## Risks + alternatives

- **Biggest risk — the synchronous reply bridge (Round 2, G-05/G-06/G-07).** Band agents are long-running WebSocket processes (`await agent.run()`), and `@mention` send is fire-and-forget — but the WhatsApp webhook is synchronous and the reply is produced by return-value bubbling today. The reply-collection seam is the actual hard part, and WP-02 is an unbounded, externally-blocked node gating all of Wave 1. *Mitigation:* **time-box the WP-02 spike (EOD day 2)**; **default fallback = request-scoped REST posting + a blocking `read_context` poll keyed by `correlation_id`** (keeps Flask synchronous, no persistent `await agent.run()`), adopted unless the WS spike clearly wins; the spike must round-trip a *reply* end-to-end, not just a message.
- **Async reply latency (Round 2).** Routing through a room (envelope → review → synthesis → reply) adds hops + LLM calls while Meta's webhook waits. *Mitigation:* return 200 to Meta immediately and send the reply out-of-band on CFO's terminal room message; room-convergence timeout with a "still working…" fallback; keep the happy path ≤2 LLM hops.
- **Demo-time credit exhaustion / rate limits (Round 2).** A 429/quota during the recorded demo is catastrophic. *Mitigation:* per-session spend ceiling + fast OpenAI-fallback on 429/quota (extend `G-MODEL-ROUTER` beyond timeouts); rehearse in OpenAI-only mode; cache a known-good demo transcript as a backstop.
- **Test breakage / no rollback (Round 2, G-08).** 106 tests exist; ≥6 patch `BandSDK.publish` and assert the return round-trip + exact event shape — WP-06 deletes the broker and they fail wholesale. *Mitigation:* a **green-test gate** (below) + a test-migration line in WP-03/04/05/06; rollback via `BAND_BACKEND=stub` and the `../tali-history-backup.bundle`.
- **Persistent-process deployment (Round 2, G-12).** App is pure-sync WSGI with no Procfile/Dockerfile; persistent WS agents need a long-running process model. *Mitigation:* prefer the request-scoped-REST path (runs inside the existing Flask app); if WS wins, WP-11 must add a worker/supervisor process model.
- **Time — ~6 days to deadline.** *Mitigation:* Phase 1+2 (real Band + router) is the must-ship MVP that clears the disqualifying gap; Phase 3 is the differentiator; Phase 4 is polish. Ship in that order; Phase 3 items are independently droppable.
- **Band Pro limits.** Memory API + Human API are Enterprise-only; 40 remote agents / 250 rooms / 15 participants per room. *Mitigation:* use room context (not Memory); well within Pro caps for a 4-agent demo.
- **Credit exhaustion.** $10 AI/ML is small. *Mitigation:* keep high-volume calls on Featherless ($25); reserve AI/ML for the ~10% escalations; OpenAI fallback absorbs outages.
- **`BandSDK` concurrency bug (pre-existing).** Global mutable `_subscribers` cleared per request is not thread-safe under multiple workers — additional reason to retire it in WP-06, not a blocker.
- **Unverified externally.** Band↔band.ai identity and the exact "must use official Band API / no thin wrapper" wording came via docs.band.ai + an Internshala mirror (lablab was Cloudflare-blocked). *Mitigation:* user to confirm on the official rules page + Band dashboard before WP-02 ships (tracked as an open question in `04`).

## ID registry

The full ID registry is in `.groundwork.json.ids`. Local cross-reference index:

<!-- groundwork:auto:start ids -->
<!-- last_action: review · 2026-06-13T13:22:09Z -->
| ID | Kind | Origin | Summary |
|---|---|---|---|
| G-01 | gap · critical | 04 R1 | "Band" is an in-memory broker, not the official Band Agent API |
| G-02 | gap · critical | 04 R1 | AI/ML API + Featherless unused; single OpenAI model |
| G-03 | gap · important | 04 R1 | Sequential chain — no planning / review / shared context |
| G-04 | gap · important | 04 R1 | Audit assets not surfaced through Band; no track chosen |
| G-05 | gap · critical | 04 R2 | Reply-aggregation seam missing from `G-BAND-CONTRACT` (sync return → fire-and-forget) |
| G-06 | gap · critical | 04 R2 | Mock contract hides the risk — stub preserves sync semantics live Band lacks |
| G-07 | gap · critical | 04 R2 | WP-02 is an unbounded, externally-blocked critical-path node — no time-box/fallback |
| G-08 | gap · important | 04 R2 | No test-migration / rollback strategy; 106 tests assert the broker round-trip |
| G-09 | gap · important | 04 R2 | WP-06 grep misses `AgentRouter` dependents (`transaction_agent.py`) |
| G-10 | gap · important | 04 R2 | "no overlap" isolation claim false — WP-08 re-touches `agent_1_intake.py` |
| G-11 | gap · important | 04 R2 | CFO already calls `send_reply` directly — split reply paths unaddressed |
| G-12 | gap · important | 04 R2 | Persistent-WS vs sync-WSGI + no deploy config undermines WP-11 |
| G-13 | gap · nice | 04 R2 | Stale `docs/agent_setup.md` still calls Band an in-memory broker |
| G-14 | gap · important | 04 R2 | Compliance pre-commit review needs a two-phase commit not in WP-04 |
| G-MODEL-ROUTER | freeze gate | WP-01 | `get_client(role)` + role→provider map + fallback (incl. 429/quota) |
| G-BAND-CONTRACT | freeze gate | WP-02 | Band connector seam: send / on_message / read_context / **reply-collection** |
| WP-01 … WP-11 | work packages | 05-tracking.md | See `05-tracking.md` §"Work packages" and `09-orchestration.md` |
<!-- groundwork:auto:end ids -->

## Verification

### Phase 1 verification

1. `get_client("intake")` returns a Featherless-backed client; `get_client("cfo")` an AI/ML-backed client; killing the primary provider falls back to OpenAI — proven by a unit test with a forced provider error.
2. `ai_logs` rows record the actual provider + model + cost for a routed call (not hardcoded `gpt-4o-mini`).
3. **Vertical reply slice (WP-02 spike acceptance, Round 2):** a message posted via the gateway is received by a second agent via `@mention`, **and the reply is collected back** (via a `correlation_id`/terminal-message poll on `read_context`) and returned to a *synchronous* caller — not just a one-way message. The WS-vs-REST decision is recorded in `04` by the time-box (EOD day 2; REST-posting is the default).

### Phase 2 verification

1. A WhatsApp "Sold rice 5000" produces a recorded transaction **with `BandSDK` deleted** — the flow runs entirely through the Band room, and the user receives the reply over WhatsApp (reply-collection seam works end-to-end, including the dead-letter + statement-document paths).
2. The Band room transcript shows Intake→Ledger→CFO as distinct @mentioned participants (visible in the Band dashboard).
3. **Green-test gate (Round 2, G-08):** the existing suite (`tests/`, 106 tests) is migrated — the `@patch(...BandSDK.publish)` seams re-pointed to `band_client` — and passes; no `band_sdk.py` import remains.

### Phase 3 verification (sketch)

1. A flagged write (e.g. duplicate / over-threshold) is **rejected by the Compliance agent before commit**, visible in the room.
2. A human "approve/reject" in the room gates a pending write end-to-end.
3. The audit view reconstructs one transaction's full lifecycle (model, cost, handoffs, approval) from `correlation_id`.
