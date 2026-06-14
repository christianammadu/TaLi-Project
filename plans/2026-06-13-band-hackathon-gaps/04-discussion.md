<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Bridge the Band of Agents hackathon gaps: make Band the real coordination layer for 3+ agents, route models across AI/ML API + Featherless with OpenAI fallback, turn the sequential chain into a plan->execute->review loop, and surface a regulated-track audit trail. — discussion threads

Decisions resolved + review-pass findings. **Newest first.**

Hand-authored above the rounds-index fence (intro context, conventions). The review action appends new "Round N" sections above the most recent one and keeps the index in sync.

<!-- groundwork:auto:start rounds-index -->
<!-- last_action: review · 2026-06-13T13:22:08Z -->
- **Round 2** (2026-06-13) — Review pass: the synchronous reply contract is the real, unowned integration risk. Folded G-05..G-14; locked the reply-collection seam into `G-BAND-CONTRACT`, a WP-02 time-box + REST-default fallback, a green-test gate, and a two-phase Ledger commit.
- **Round 1** (2026-06-13) — Gap analysis vs hackathon rules + Band SDK; founding plan locked. Folded G-01..G-04; locked real-Band coordination, 3-provider routing (OpenAI fallback), plan→execute→review via a Compliance agent, and the Regulated track.
<!-- groundwork:auto:end rounds-index -->

---

_Round entries appear below this divider, newest first._

## Round 2 — review pass: the synchronous reply contract is the real, unowned integration risk (2026-06-13)

First review pass (reviewer agent, whole-plan, lens: structural-gaps + risks + contradictions + readiness). The agent read `01`/`02`/`03`/`05`/`09` + `.groundwork.json` **and the actual app code** (the three agents, `band_sdk.py`, `agent_router.py`, `transaction_agent.py`, `nlp.py`, the test suite). The headline: the plan correctly identifies *that* Band must replace the broker, but under-specifies *how the user-facing reply gets back* — today the entire reply is produced by synchronous return-value bubbling through `BandSDK.publish`, and real Band's `@mention`/`send_message` is fire-and-forget with no return value. Ten findings folded.

### Critical gaps folded
- **G-05 · Reply-aggregation seam missing from `G-BAND-CONTRACT`** → the reply bubbles `CFO → Ledger(responses[0]) → Intake → AgentRouter.route() → send_reply()` (verified `agent_2_ledger.py:157`, `agent_1_intake.py:706`, `agent_router.py:104,126`, `routes.py:343`). Band has no return channel. Added a **4th element to `G-BAND-CONTRACT`** (reply-collection seam: gateway blocks on `correlation_id`/terminal message via `read_context`) in `01` §Schema/contract + WP-02 DoD in `05`/`09`. This is the hard part of the bridge — frozen in WP-02 before any port.
- **G-06 · The mock contract hides the very risk it's meant to de-risk** → `09` §Mock contract backed the stub with the in-memory broker, which *is* the synchronous return channel. Ports verified against it pass locally, then break on `BAND_BACKEND=live`. Changed the stub to **fire-and-forget** (reply via callback/poll) so ports code against real async semantics; WP-02 must round-trip a *reply* end-to-end, not just a message.
- **G-07 · WP-02 is an unbounded, externally-blocked node on the critical path** → riskiest node, blocked on open-question #1 (user must confirm Band rules), gating all of Wave 1, with no time-box or fallback. Added a **WP-02 spike time-box (EOD day 2)** and a stated **default fallback = request-scoped REST posting + a blocking `read_context` poll keyed by `correlation_id`** (keeps Flask synchronous, avoids persistent `await agent.run()`), unless the WS spike clearly wins. Folded into `01` §Risks + `09` open questions.

### Important gaps folded
- **G-08 · No test-migration / rollback strategy** → 106 tests exist; ≥6 `@patch(...BandSDK.publish)` assert both the return-value round-trip and the exact event-dict shape — WP-06 deletes the broker and they fail wholesale, owned by no WP. Added a **green-test gate** to `01` §Verification + a test-migration line to WP-03/04/05/06 DoDs, and a rollback note (`BAND_BACKEND=stub` + the `../tali-history-backup.bundle`).
- **G-09 · WP-06 grep-clean misses `AgentRouter` dependents** → `transaction_agent.py:31-33` calls `AgentRouter(...).route()` as a fallback — not a `BandSDK` importer, so the scoped grep misses it. Broadened WP-06 to grep **`AgentRouter` callers** and added `app/agents/transaction_agent.py` to its scope + `01` §Critical files.
- **G-10 · "no overlap" isolation claim is false** → WP-08 also edits `agent_1_intake.py` (pending hooks), two waves after WP-03 ports it. Corrected `09` §Intra-repo isolation to note WP-08 re-touches the file after WP-03 (serial, merge-order-safe).
- **G-11 · CFO already calls `send_reply` directly (split reply paths)** → the dead-letter saga (`agent_3_cfo.py:159`) and statement/document flows send out-of-band today. Recorded the decision point in `01` §Architecture + WP-05/06 DoD: does `send_reply` move into the gateway, or do agents keep calling it (weakening the "Band as active layer" claim)?
- **G-12 · Persistent-WS vs sync-WSGI + no deploy config undermines WP-11** → app is pure-sync WSGI with no Procfile/Dockerfile; persistent `await agent.run()` agents need a long-running process model WP-11 doesn't account for. Added a process-model line to WP-11 + fed it into the WP-02 WS-vs-REST decision.
- **G-14 · Compliance pre-commit review needs a two-phase commit not in WP-04** → Ledger commits inline today; "reject pre-commit" requires Ledger to split into propose→(await review)→commit over the async room — a re-entrant suspend/resume (same family as G-05). Spelled out the two-phase contract in WP-04 DoD + the WP-07→WP-04 dependency.

### Polish folded
- **G-13 · Stale `docs/agent_setup.md`** still calls Band an "in-memory pub/sub broker" — for a public repo + judged submission this contradicts the real-Band claim. Added a doc-rewrite item to WP-11.

### New risks folded (→ `01` §Risks)
- **Async reply latency** — routing through a room (envelope → review → synthesis → reply) adds hops + LLM calls while Meta's webhook waits. Mitigation: return 200 immediately, reply out-of-band on CFO's terminal message; room-convergence timeout with a "still working…" fallback; keep the happy path ≤2 LLM hops.
- **Demo-time credit exhaustion / rate limits** — $10 AI/ML is tiny; a 429/quota during the recorded demo is catastrophic. Mitigation: per-session spend ceiling + fast OpenAI-fallback on 429/quota (extend the G-MODEL-ROUTER fallback beyond timeouts); rehearse in OpenAI-only mode; cache a known-good demo transcript backstop.

### Second-pass audit
Findings G-05/G-06/G-07 form one chain (the reply contract → the stub that hides it → the unbounded node), not three overlaps; G-11/G-14 are the same async-suspend family applied to replies and to commits. The reviewer deliberately did **not** manufacture findings about the model router or the track choice (both sound). Every finding carries a concrete fold + touches.

### Strengths the reviewer said to defend
- Room-log + REST `…/context` for shared state (not the Enterprise-only Memory API) — correct + forced for a Pro account.
- Reusing `event_schemas.py` Pydantic bodies as Band payloads — IDs map 1:1, schemas battle-tested.
- MVP-first ordering; independent parallel Wave-0 gates; Regulated-track fit; the confidence<0.7 escalation reuse.

### Reviewed and NOT reopened
- Real Band replaces the broker · 3-provider routing + OpenAI fallback · plan→execute→review via Compliance · Regulated track · room-context-not-Memory · MVP-first ordering. All survived — only sharpened, not reopened.

### Plan files touched
- `01-plan.md` — §Schema/contract (reply seam), §Architecture (split reply paths), §Critical files (`transaction_agent.py`), §Risks (5 new), §Verification (green-test gate); `ids` index extended G-05..G-14.
- `05-tracking.md` — WP-02/04/06/11 DoDs tightened; round-fold updated.
- `09-orchestration.md` — mock contract (fire-and-forget), `G-BAND-CONTRACT` row (reply seam), isolation table (WP-08), WP-02 time-box + REST default, open questions extended.

### What's locked, what's still open
**Locked this round:** reply-collection seam belongs in `G-BAND-CONTRACT`; WP-02 is a vertical reply-round-trip slice with a time-box + REST-default fallback; green-test gate; two-phase commit for Ledger; `send_reply` ownership is a WP-02/05 decision.

**Still open (→ `clarify`):**
- Where the reply is collected from the room and handed to `send_reply` (the aggregation seam) — freeze in WP-02.
- WS persistent-agent vs request-scoped-REST — now leans REST-default, decided in WP-02.
- Does `send_reply` move into the gateway or stay in the agents?
- Two-phase commit contract for Ledger (WP-04).
- Test-migration ownership: which WP re-points the patched `BandSDK.publish` seam; do the event-shape assertions survive.

## Round 1 — gap analysis vs hackathon rules + Band SDK; founding plan locked (2026-06-13)

Founding pass. Reviewed the live TaLi codebase (the three agents, `band_sdk.py`, `nlp.py`, `config.py`) against the Band of Agents Hackathon rules and the Band (band.ai / Thenvoi) docs + SDK, alongside web research into both (lablab was Cloudflare-blocked → mirrors; Band via docs.band.ai). Lens: rule violations + architecture + tool optimization + competitive edge.

### Critical gaps folded
- **G-01 · "Band" is not Band** → `app/agents/band_sdk.py` is a 36-line in-memory pub/sub broker (the team's own `docs/agent_setup.md:9,93` calls it that), not the official Band Agent API. The rules require Band to be the *active* coordination layer ("cannot be a thin wrapper") and the **Application of Technology** axis scores exactly this. Folded into `01` §Architecture (target = Band room + @mention) and the WP-02→03→04→05→06 chain in `05`.
- **G-02 · Partner tooling unused** → only OpenAI `gpt-4o-mini` (`nlp.py:197`); AI/ML API ($10) + Featherless ($25) absent → ~$35 credits + both partner prizes unclaimed. Folded into `01` §Phase 1 + WP-01 (model router).

### Important gaps folded
- **G-03 · Sequential chain, not collaboration** → Intake→Ledger→CFO are synchronous in-process calls via `BandSDK.publish`; no planning, no review loop, no shared context. Folded into `01` §Architecture + WP-07 (Compliance review leg) + WP-08 (human-in-loop).
- **G-04 · Audit assets not surfaced through Band; no track chosen** → strong audit/idempotency plumbing exists but isn't exposed or routed through Band; the regulated track is unclaimed. Folded into WP-09 (audit surfacing) + WP-10 (FinOps) + the track decision below.

### Decisions
- **Target the Regulated & High-Stakes Workflows track** — best fit for the existing audit / idempotency / human-review plumbing.
- **Model routing:** Featherless = high-volume workers (intake extraction, reply formatting, the Compliance reviewer); AI/ML API = frontier reasoning (CFO synthesis) + the `confidence < 0.7` escalation (`agent_1_intake.py:374`); **OpenAI = fallback only**.
- **Shared context via the room message/event log + REST context endpoint, NOT the Memory API** (Enterprise-only; user has Pro).
- **Ship order:** Phase 1+2 (real Band + router) is the must-ship MVP that clears the disqualifying gap; Phase 3 differentiators are independently droppable; Phase 4 polish last.
- **MIT licence: user owns it (out of scope for this plan).**

### New risks folded
- **Architectural shift** — Band agents are persistent WebSocket processes (`await agent.run()`), not request-scoped functions; bridging the Flask webhook is the core risk. WP-02 spikes WS-vs-REST before any porting.
- **Time box** — ~6 days to 2026-06-19 20:30 IST; MVP-first ordering mitigates.

### Strengths the reviewer said to defend
- The enterprise plumbing (idempotency, dead-letter saga, `ai_logs` cost logging, `review_queue`, confirm-before-write, correlation IDs) is genuinely strong — do **not** rebuild it; surface it (WP-09) and reuse it (WP-08).
- The Pydantic event schemas (`event_schemas.py`) map ~1:1 onto Band messages — reuse, don't rewrite.
- The 3-agent role split (Intake / Ledger / CFO) is sound; it just needs to ride Band.

### Plan files touched
- `01-plan.md` — Context, Architecture, Shared-state contract, Phases, Critical files, Reuse map, Risks, Verification authored from this pass.
- `05-tracking.md` — WP-01..WP-11 + critical path authored.
- `.groundwork.json` — G-01..G-04, G-MODEL-ROUTER, G-BAND-CONTRACT, WP-01..WP-11 registered.

### What's locked, what's still open
**Locked this round:** real-Band coordination; 3-provider routing with OpenAI fallback; plan→execute→review via a Compliance agent; regulated track; room-context (not Memory) for shared state; MVP-first ordering.

**Still open (→ `clarify`):**
- Confirm the Band↔band.ai identity + the exact "official Band API / no thin wrapper" rule wording on the official lablab page + the Band dashboard (research came via mirrors).
- WP-02 decision: persistent WebSocket agents vs request-scoped REST posting from the Flask webhook.
- Exact AI/ML + Featherless model picks (e.g. Qwen2.5-72B vs Mistral) and base URLs — confirm in the dashboards.
