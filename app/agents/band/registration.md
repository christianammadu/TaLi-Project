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

## Decision — SDK REST client inside Flask; WebSocket SDK workers later

The WhatsApp/Telegram webhooks are synchronous Flask (sync WSGI, no async runtime, no
deploy config for long-running worker processes). Persistent WebSocket agents
(`await Agent.run()`) would need a separate worker/supervisor process. So the current
production path is:

> **Request-scoped `band-sdk` REST client calls** from the webhook while the local
> Python agents execute synchronously through the shared connector. Keeps Flask
> synchronous, deploys inside the existing app, and makes Band the room, participant,
> message, and audit surface.

Adopt persistent WebSocket SDK agents only when there is a separate worker process.

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
- ✅ `live` backend — implemented + **verified end-to-end against the real Band API** (in-process orchestration + a real room mirror with auto-provisioning). See below.

## Going live — `_LiveBackend` uses `band-sdk`

The agents are **local** (the Ledger writes our MySQL; all agent logic is in
`app/agents/`), while Band is the **coordination/audit surface**. `_LiveBackend`:

1. **Inherits the stub** — synchronous in-process `@mention` dispatch + `collect_reply`, so the
   webhook still gets its answer reliably (no polling, no async runtime).
2. **Mirrors every handoff into the real Band room** through `band-sdk`'s
   `band.client.rest.RestClient`, under the sending agent's `X-API-Key`, so
   `app.band.ai` shows the four participants and the
   `intake → ledger → compliance → cfo` handoffs.

### SDK methods used
```
from band.client.rest import RestClient

client.agent_api_chats.get_agent_chat(...)
client.agent_api_chats.create_agent_chat(...)
client.agent_api_participants.add_agent_chat_participant(...)
client.agent_api_messages.create_agent_chat_message(...)
client.agent_api_events.create_agent_chat_event(...)
```
Messages that target real Band participants are posted as chat messages with mentions.
Terminal/gateway messages that do not target a real Band participant are posted as
`task` events so they still appear in the room transcript.

### Room resolution (auto-provision)
`get_band_client()` is called per request, so the resolved room is cached **per process**
(`_LIVE_ROOM_CACHE`) — without that we'd create a room per message. On first send `_LiveBackend`:
1. If `BAND_ROOM_ID` is set **and** the owner agent (`@tali-intake`) is already a member
   (`GET /agent/chats/{id}` → 200) → use it. *(This is the stable path — add the 4 agents to
   your room in the Band UI and it's used directly.)*
2. Else **auto-provisions** an agent-owned room, adds the other three as participants, and logs
   `watch it at https://app.band.ai/chat/<id>`. (Agents can't self-join a human-owned room via
   the agent API, so a room you created in the UI without adding them falls back to this.)

The mirror is best-effort: any room failure only logs — bookkeeping always proceeds in-process.

**To switch on:**
```
BAND_BACKEND=live
BAND_INTAKE_AGENT_ID / BAND_INTAKE_API_KEY
BAND_LEDGER_AGENT_ID / BAND_LEDGER_API_KEY
BAND_CFO_AGENT_ID / BAND_CFO_API_KEY
BAND_COMPLIANCE_AGENT_ID / BAND_COMPLIANCE_API_KEY
BAND_*_HANDLE=@owner/slug             # the agent's real handle (GET /agent/me → "handle"); maps internally
AIML_API_KEY=<key>                    # so the CFO runs on the frontier model
BAND_ROOM_ID=<your room>              # optional; only used if you add the 4 agents to it in the UI,
                                      # otherwise the gateway auto-provisions + logs a room URL
```
