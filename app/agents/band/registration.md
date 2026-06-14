# Band agent registration + WP-02 spike notes

Freeze gate **G-BAND-CONTRACT**. This is the connector contract the agent ports
(WP-03/04/05) build against. See `band_client.py` for the code seam.

## Agents to register (app.band.ai → New Agent → Remote Agent)

Register each as a **remote** agent (runs in our env via the SDK), copy its
`agent_id` + `X-API-Key` (shown once), and put them in `.env`:

| Role | Handle (suggested) | Env (agent_id / api_key) | Model role (WP-01) |
|---|---|---|---|
| Intake & Normalizer | `@tali-intake` | `BAND_INTAKE_AGENT_ID` / `BAND_INTAKE_API_KEY` | `intake` (Featherless) |
| Ledger & Tax | `@tali-ledger` | `BAND_LEDGER_AGENT_ID` / `BAND_LEDGER_API_KEY` | — (DB writer) |
| CFO & Escalation | `@tali-cfo` | `BAND_CFO_AGENT_ID` / `BAND_CFO_API_KEY` | `cfo` (AI/ML) |
| Compliance/Reviewer (WP-07) | `@tali-compliance` | `BAND_COMPLIANCE_AGENT_ID` / `BAND_COMPLIANCE_API_KEY` | `compliance` (Featherless) |

All four share one **room per user/session** (`BAND_ROOM_ID`). Pro caps (40 agents /
250 rooms / 15 participants) are comfortably clear. Shared context = the room
message/event log via `GET /api/v1/agent/chats/{id}/context` — **not** the Memory API
(Enterprise-only; we are on Pro).

## Decision — WS vs REST (Round 2, G-07): **default to REST**

The WhatsApp webhook is synchronous Flask (sync WSGI, no async runtime, no deploy
config for long-running processes). Persistent WebSocket agents (`await agent.run()`)
would need a separate worker/supervisor process. So the **default** is:

> **Request-scoped REST posting** from the webhook + a **blocking `read_context` poll
> keyed by `correlation_id`** to collect the reply. Keeps Flask synchronous, no
> persistent process, deploys inside the existing app.

Adopt persistent-WS only if the spike shows REST polling can't meet latency within
the deadline. **Time-box: EOD day 2.**

## The reply-collection seam (Round 2, G-05) — the hard part

Today the user-facing reply is produced by *synchronous return-value bubbling* through
the old in-memory broker. Band `send`/`@mention` is **fire-and-forget — no return
value**. So the gateway (WP-06) must:

1. Generate a `correlation_id` for the inbound message and `send` it into the room
   `@tali-intake` (fire-and-forget).
2. Agents coordinate in the room; CFO posts the final reply with `terminal=True` and the
   same `correlation_id`.
3. The gateway `collect_reply(correlation_id, timeout)` blocks (REST: polls
   `read_context` for the terminal message) and returns the text to `send_reply`.

Open: does `send_reply` move **into the gateway** (preferred — keeps Band the active
layer) or stay in the agents? Also account for the already-split out-of-band paths
(dead-letter saga `agent_3_cfo.py:159`, statement documents). Decide in WP-05.

## Spike status

- ✅ Connector seam defined (`band_client.py`): `send / on_message / read_context / collect_reply`.
- ✅ `stub` backend (fire-and-forget, reply-by-correlation_id) — lets WP-03/04/05 build offline; covered by `tests/test_band_client.py`.
- ⏳ `live` backend — `read_context` scaffolded over REST; `send` is `NotImplementedError` pending **(a)** confirmation that band.ai/Thenvoi is THIS hackathon's Band and **(b)** registered agent credentials (open question #1). The live reply round-trip is the WP-02 sign-off and is **not** done yet.
