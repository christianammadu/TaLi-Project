# Bridge the Band of Agents hackathon gaps — implementation orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**. Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a harness Task and ticks `05` as work lands.

> ⚠️ **Planning artifact only — do not implement without the user's say-so.** This doc is the kickoff plan; it is not a signal to start coding.

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. Single repo (`tali`); each WP owns disjoint paths (one agent file per port WP), so Wave-1 ports run in parallel without collision.
- **Orchestrator** owns `05-tracking.md` checkboxes + the Band agent registrations; **subagents** own one WP each and report Definition-of-Done back.
- **Branch-per-WP**, merge in wave order. Worktrees recommended for Wave 1 (3 parallel agent ports touching sibling files).
- Two hard freeze gates precede everything (Wave 0); they are independent of each other so they run concurrently.

## Freeze gates (hard, sequential within a track)

| Gate | WP | Why it gates | Sign-off check |
|---|---|---|---|
| `G-MODEL-ROUTER` | WP-01 | Agents must not hardcode a provider; the role→provider map + fallback policy must be fixed before any agent adopts it | `get_client(role)` signature frozen; forced-fallback unit test green |
| `G-BAND-CONTRACT` | WP-02 | The connector seam (send / on_message / read_context **/ reply-collection**, G-05) + the WS-vs-REST decision must be fixed before the 3 agent ports build against it | a **reply** round-trips (gateway → `@mention` → 2nd agent → reply collected back to a synchronous caller via `correlation_id`/`read_context`); decision recorded in `04` by EOD day 2 |

## Work-package matrix

| WP | Title | Repo | Wave | Depends on | Output |
|---|---|---|---|---|---|
| WP-01 | Multi-provider model router | tali | 0 | — | `G-MODEL-ROUTER`; `app/services/model_router.py` |
| WP-02 | Band integration spike + connector contract | tali | 0 | — | `G-BAND-CONTRACT`; `app/agents/band/band_client.py` |
| WP-03 | Port Intake onto Band | tali | 1 | G-BAND-CONTRACT, G-MODEL-ROUTER | ported `agent_1_intake.py` |
| WP-04 | Port Ledger + proposed-write envelope | tali | 1 | G-BAND-CONTRACT, G-MODEL-ROUTER | ported `agent_2_ledger.py` |
| WP-05 | Port CFO onto Band | tali | 1 | G-BAND-CONTRACT, G-MODEL-ROUTER | ported `agent_3_cfo.py` |
| WP-06 | Webhook→room gateway; delete broker | tali | 2 | WP-03, WP-04, WP-05 | gateway; `band_sdk.py` removed |
| WP-07 | Compliance/Reviewer agent | tali | 2 | WP-04, G-MODEL-ROUTER | `app/agents/compliance_agent.py` |
| WP-08 | Human-in-the-loop approval in room | tali | 3 | WP-06 | room approval flow |
| WP-09 | Unified audit-trail surfacing | tali | 3 | WP-06 | `app/services/audit.py` + view |
| WP-10 | FinOps per-model cost attribution | tali | 4 | WP-01, WP-09 | finops view |
| WP-11 | Deploy, public repo, demo video | tali | 4 | WP-06, WP-07, WP-08, WP-09 | submission |

### Wave plan (orchestrator spawn order)

- **Wave 0 (gates, parallel):** WP-01, WP-02 — both must land before Wave 1.
- **Wave 1 (post-gate fan-out, parallel):** WP-03, WP-04, WP-05 — disjoint agent files; worktrees recommended.
- **Wave 2:** WP-06 (needs all three ports), WP-07 (needs WP-04's envelope) — parallel.
- **Wave 3:** WP-08, WP-09 — both need the room gateway (WP-06); parallel.
- **Wave 4:** WP-10 (needs WP-01 + WP-09), then WP-11 (submission; pulls in whatever differentiators landed).

### Intra-repo isolation (disjoint scopes for parallel waves)

- WP-01 → `app/services/model_router.py`, `app/services/nlp.py`, `app/config.py`, `.env.example`
- WP-02 → `app/agents/band/`, `requirements.txt`
- WP-03 → `app/agents/agent_1_intake.py` · WP-04 → `app/agents/agent_2_ledger.py` · WP-05 → `app/agents/agent_3_cfo.py` (disjoint within Wave 1)
- **WP-08 re-touches `app/agents/agent_1_intake.py`** (pending hooks) two waves after WP-03 ports it (G-10) — *not* "no overlap"; serial, so merge WP-08 after WP-03 (no conflict, just sequencing).
- WP-06 → `app/web/whatsapp.py`, `app/agents/agent_router.py`, `app/agents/transaction_agent.py` (retire `AgentRouter` fallback), removes `app/agents/band_sdk.py`
- WP-07 → `app/agents/compliance_agent.py` · WP-09 → `app/services/audit.py`

## Mock contract (so cross-boundary agents don't serialize)

- **`G-BAND-CONTRACT` mock (lets WP-03/04/05 start before WP-02 fully lands):** a `band_client` stub exposing `send(mentions, body)`, `on_message(cb)`, `read_context(room_id)` behind `BAND_BACKEND=stub|live`. **The stub MUST be fire-and-forget (no return value — reply arrives via callback/poll), NOT the in-memory broker (G-06):** backing it with the broker would preserve the synchronous return channel live Band lacks, so ports would pass locally then break on `live`. The stub forces ports to code against the real async + reply-collection semantics.
- **`G-MODEL-ROUTER` mock:** `get_client(role)` returning the current OpenAI client for every role until provider keys are wired — lets ports proceed, then routing turns on by config.

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · CONSUMES · PRODUCES ·
DO-NOT-TOUCH · DEFINITION OF DONE · MOCK (if upstream not ready) · REPORT
```

---

### WP-01 — Multi-provider model router
- **GOAL:** Generalize `get_openai_client()` into `get_client(role)` routing across AI/ML API (frontier), Featherless (OS workers), OpenAI (fallback).
- **REPO/BRANCH:** tali / `feat/model-router`
- **DEPENDS-ON:** —
- **FILES:** create `app/services/model_router.py`; touch `app/services/nlp.py` (`:7`, `:197`), `app/config.py`, `.env.example`.
- **CONSUMES/PRODUCES:** produces `G-MODEL-ROUTER`.
- **DO-NOT-TOUCH:** agent files, `band_sdk.py`.
- **DoD:** unit test proves role routing + forced-primary-error→OpenAI fallback; `ai_logs` records real provider+model+cost (Phase-1 verification #1–2).
- **REPORT:** the frozen `get_client` signature + role map.

### WP-02 — Band integration spike + connector contract
- **GOAL:** Stand up `band-sdk`, register 3 remote agents on `app.band.ai` (Pro), create a room, prove a **reply round-trips** (not just one-way); freeze the reply-collection seam; decide persistent-WS vs request-scoped REST. **Time-box: EOD day 2.**
- **REPO/BRANCH:** tali / `feat/band-connector`
- **DEFAULT FALLBACK (G-07):** if WS doesn't clearly win → request-scoped REST posting + a blocking `read_context` poll keyed by `correlation_id` (keeps Flask synchronous, no persistent `await agent.run()`).
- **DEPENDS-ON:** —
- **FILES:** create `app/agents/band/band_client.py`, `app/agents/band/registration.md`; touch `requirements.txt` (`+band-sdk`), `app/config.py`, `.env.example`.
- **CONSUMES/PRODUCES:** produces `G-BAND-CONTRACT` (reuses `event_schemas.py` bodies as message payloads).
- **DO-NOT-TOUCH:** the 3 agent classes.
- **DoD:** a script posts via the gateway, a 2nd agent receives via `@mention`, **and the reply is collected back and returned to a synchronous caller**; WS-vs-REST decision recorded in `04` (Phase-1 verification #3).
- **REPORT:** the connector interface (incl. reply-collection) + the WS/REST decision.

### WP-03 — Port Intake onto Band
- **GOAL:** Replace `BandSDK.publish("intake_to_ledger"/"cfo_escalation")` with Band send/@mention; adopt `get_client("intake")` (Featherless, escalate to AI/ML on `confidence<0.7`).
- **REPO/BRANCH:** tali / `feat/band-intake` · **DEPENDS-ON:** G-BAND-CONTRACT, G-MODEL-ROUTER
- **FILES:** `app/agents/agent_1_intake.py`. **DO-NOT-TOUCH:** sibling agents.
- **DoD:** Intake posts to the room as a distinct participant; no `BandSDK` import remains.

### WP-04 — Port Ledger + proposed-write envelope
- **GOAL:** Port Ledger off `BandSDK.publish("ledger_updates"/"ledger_errors")`; emit a pre-commit "proposed write" envelope for Compliance (WP-07).
- **REPO/BRANCH:** tali / `feat/band-ledger` · **DEPENDS-ON:** G-BAND-CONTRACT, G-MODEL-ROUTER
- **FILES:** `app/agents/agent_2_ledger.py`. **DO-NOT-TOUCH:** sibling agents.
- **TWO-PHASE COMMIT (G-14):** split inline commit into **propose → (await Compliance review) → commit** over the async room (re-entrant suspend/resume keyed by `correlation_id`); the reject must *prevent* the commit, not annotate it.
- **DoD:** room I/O works; envelope published **and DB commit withheld until Compliance approves**; test seam re-pointed + green (G-08).

### WP-05 — Port CFO onto Band
- **GOAL:** Port CFO off the `ledger_updates`/`cfo_escalation`/`ledger_errors` subscriptions onto room handlers; `get_client("cfo")` (AI/ML) for synthesis.
- **REPO/BRANCH:** tali / `feat/band-cfo` · **DEPENDS-ON:** G-BAND-CONTRACT, G-MODEL-ROUTER
- **FILES:** `app/agents/agent_3_cfo.py`. **DO-NOT-TOUCH:** sibling agents.
- **DoD:** CFO composes the user-facing reply from room context; no `BandSDK` import remains.

### WP-06 — Webhook→room gateway; delete broker
- **GOAL:** Replace `AgentRouter.route` with a gateway that drops the inbound WhatsApp message into the Band room; delete `app/agents/band_sdk.py`.
- **REPO/BRANCH:** tali / `feat/band-gateway` · **DEPENDS-ON:** WP-03, WP-04, WP-05
- **FILES:** `app/web/whatsapp.py`, `app/agents/agent_router.py` (replace), `app/agents/transaction_agent.py` (retire `AgentRouter().route()` fallback `:31-33`), remove `app/agents/band_sdk.py`.
- **GREP-CLEAN (G-09):** grep **both `BandSDK` importers and `AgentRouter` callers** before deleting — `transaction_agent.py` is the known hidden dependent.
- **DoD:** "Sold rice 5000" works end-to-end with `band_sdk.py` deleted; reply arrives over WhatsApp; room shows 3 participants; **migrated test suite green** (G-08); rollback via `BAND_BACKEND=stub`.

### WP-07 — Compliance/Reviewer agent (the review leg)
- **GOAL:** New 4th agent on a Featherless model reviewing Ledger's proposed-write envelope **before commit** (duplicate/threshold/anomaly checks reusing `_get_evaluated_thresholds`, `agent_3_cfo.py:173`); approve/reject/escalate.
- **REPO/BRANCH:** tali / `feat/compliance-agent` · **DEPENDS-ON:** WP-04, G-MODEL-ROUTER
- **FILES:** create `app/agents/compliance_agent.py`; register a 4th Band agent.
- **DoD:** a flagged write is rejected pre-commit, visible in the room (Phase-3 verification #1).

### WP-08 — Human-in-the-loop approval in the room
- **GOAL:** Route confirm-before-write (`_store_pending`) + `review_queue` as a human-participant approval inside the room.
- **REPO/BRANCH:** tali / `feat/human-in-loop` · **DEPENDS-ON:** WP-06
- **FILES:** `app/agents/agent_1_intake.py` (pending hooks), gateway, a human room participant.
- **DoD:** a human approve/reject in the room gates a pending write (Phase-3 verification #2).

### WP-09 — Unified audit-trail surfacing (Regulated track)
- **GOAL:** Join `ai_logs`/`processed_events`/`correlation_id` to Band's unified audit trail; expose a lifecycle/traceability view keyed by `correlation_id`.
- **REPO/BRANCH:** tali / `feat/audit-trail` · **DEPENDS-ON:** WP-06
- **FILES:** create `app/services/audit.py`; a read-only route/view.
- **DoD:** reconstruct one transaction's full lifecycle (model, cost, handoffs, approval) from its `correlation_id` (Phase-3 verification #3).

### WP-10 — FinOps per-model cost attribution
- **GOAL:** Extend cost logging across the three providers; per-agent / per-model spend view (proves deliberate credit optimization).
- **REPO/BRANCH:** tali / `feat/finops` · **DEPENDS-ON:** WP-01, WP-09
- **FILES:** `app/agents/reporting_agent.py`, `app/services/model_router.py`.
- **DoD:** FinOps report shows spend split by provider+agent for a session.

### WP-11 — Deploy, public repo, demo video
- **GOAL:** Deploy the Band-integrated build; public repo; record a <5-min demo around the live Band room (plan→execute→review→human-approve→audit). MIT licence added by the user.
- **REPO/BRANCH:** tali / `chore/submission` · **DEPENDS-ON:** WP-06 (must-ship); WP-07/08/09 (differentiators if landed)
- **PROCESS MODEL (G-12):** pure-sync WSGI, no deploy config today. REST path (WP-02 default) deploys inside Flask; WS path needs a worker/supervisor process model added here.
- **DOC REWRITE (G-13):** rewrite `docs/agent_setup.md` §4 (still calls Band an "in-memory pub/sub broker") to the real Band room + `@mention` model — it's public + judge-facing.
- **FILES:** `docs/` (incl. `agent_setup.md`), `README.md`, deploy config (if WS), demo script.
- **DoD:** live URL + public repo + video <5 min/300 MB submitted on lablab.ai; `agent_setup.md` no longer describes an in-memory broker.

---

## Tracking protocol

- **Kickoff:** orchestrator reads `05-tracking.md`, calls `TaskCreate` once per WP (title `WP-NN <title>`, body = DoD), mirroring wave deps.
- **Live run:** on each WP completion, set the Task `completed` **and** tick the `05` checkbox — durable SoT (`05`) and live view stay in lockstep.
- **Blocked / needs-decision:** mark `[!]` in `05` + surface the open question here.
- **Merge order:** wave order; Wave-1 ports merge before WP-06 deletes the broker.

## Open coordination questions (resolve at kickoff)

1. **Confirm Band identity + rules** — verify band.ai/Thenvoi is THIS hackathon's Band and the exact "official Band API / no thin wrapper" wording on the official lablab page + Band dashboard (research came via mirrors). *Blocks WP-02 sign-off.*
2. **WS vs REST** — persistent WebSocket agents (`await agent.run()`) vs request-scoped REST posting. *Decided in WP-02 by EOD day 2; **REST is the default** unless WS clearly wins.*
3. **Reply-collection seam (G-05/G-11)** — where the final reply is collected from the async room and handed to `send_reply`; does `send_reply` move into the gateway or stay in the agents? *Frozen into `G-BAND-CONTRACT` in WP-02.*
4. **Two-phase Ledger commit (G-14)** — the propose→review→commit contract so Compliance can *reject* pre-commit. *Specified in WP-04.*
5. **Test-migration ownership (G-08)** — which WP re-points the patched `BandSDK.publish` seam; do the exact-event-shape assertions survive `event_schemas` reuse? *Green-test gate in WP-06.*
6. **Model picks + base URLs** — exact AI/ML + Featherless models (e.g. Qwen2.5-72B vs Mistral) and OpenAI-compatible base URLs. *Confirm in dashboards during WP-01.*
7. **MIT licence** — owned by the user (out of scope), but required before submission (WP-11).

<!-- groundwork:auto:end orchestration -->
