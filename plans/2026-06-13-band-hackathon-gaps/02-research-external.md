<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 02 — External research

Outside research backing Bridge the Band of Agents hackathon gaps: make Band the real coordination layer for 3+ agents, route models across AI/ML API + Featherless with OpenAI fallback, turn the sequential chain into a plan->execute->review loop, and surface a regulated-track audit trail.. Cite every claim with a URL + access date. Hand-authored sections live between fences; the research action only writes inside.

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-13T12:52:37Z -->
### Hackathon rules (what's mandatory + how it's scored)

- **Band is mandatory as the *active* coordination layer.** "Agents… must use the official Band Agent API to coordinate." "The Band platform cannot be used as a simple notification alert or thin wrapper. It must serve as the active layer where context, task handoffs, state changes, and agent discovery loops happen." (lablab page via search index + Internshala mirror.)
- **≥3 unique specialized agents actively communicating** — "at least 3 unique, specialized AI agents actively communicating with each other," that "plan, execute, review, and hand off work together."
- **Judging axes (qualitative, no published weights):** (1) **Business Value** — solves a real enterprise workflow problem; (2) **Application of Technology** — "how effectively does the solution use Band as the coordination layer between multiple specialized agents" (task handoffs, shared context, role specialization, task state); (3) **Presentation** — clarity of the demo + agent roles + Band's role.
- **Tracks:** Internal Enterprise Workflows; Multi-Agent Software Development (Codeband); **Regulated & High-Stakes Workflows** — "air-gapped or sensitive environments where strict traceability, explicit audit trails, and risk management matter most." ← our target.
- **Deliverables:** <5 min / <300 MB demo video, public GitHub repo, deployed platform + live demo URL, submit on lablab.ai; "submissions must be original and MIT-compliant."
- **Timeline:** build June 12–19, 2026; hard deadline **June 19 2026 @ 20:30 IST**.
- **Confidence caveat:** lablab is Cloudflare-blocked; rule/criteria text recovered via search index + Internshala mirror — high confidence, not byte-verified. Judging weights + the "$10 AI/ML" figure not independently re-verified. Confirm on the official page.

### Band platform (band.ai / Thenvoi)

- **Identity:** Band = product of **Thenvoi AI Ltd. (d/b/a Band)**; site band.ai; docs **docs.band.ai**; app **app.band.ai**; GitHub org `thenvoi`. Brand "Band" but code/classes/env are `thenvoi`.
- **What it is:** a shared interaction & context layer beside your existing agents — persistent identity, multi-agent coordination, structured memory, **unified audit trail across all agents**; cross-framework (LangGraph/CrewAI/Anthropic/OpenAI/…).
- **Core primitives:** **Agent** (remote = runs in your env via SDK, or platform); **Execution** (one per agent per room); **Chat Room** (the coordination space); **Contact** (consent-gated cross-owner link); **Handle** (`@owner/agent-slug`); **@mention routing** (a message is delivered ONLY to @mentioned agents — this is the subscribe mechanism); **messages vs events** (events = `thought`/`tool_call`/`tool_result` records, never delivered as messages).
- **SDK:** pip **`band-sdk`** (import `from thenvoi import Agent`), Python ≥3.11; framework extras (`band-sdk[anthropic]`, `[openai]`, `[langgraph]`…). `Agent.create(adapter, agent_id, api_key, ws_url, rest_url)` then `await agent.run()` (persistent WebSocket; auto-subscribes; processes only @mentions). Auth header `X-API-Key`. Env `THENVOI_REST_URL=https://app.band.ai/`, `THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket`.
- **Send/receive:** agents reply by calling the `thenvoi_send_message(content, mentions)` tool — "regular LLM text responses are treated as internal thoughts and are NOT visible to other participants." Read shared context: `GET /api/v1/agent/chats/{chat_id}/context` (returns msgs the agent sent + msgs that @mention it; `X-API-Key`).
- **Collaboration patterns (documented):** sequential (`@A → @B → @C`), parallel/broadcast (multi-@mention), and the recommended **dynamic** pattern — a coordinator discovers peers (`thenvoi_lookup_peers`) and recruits them (`thenvoi_add_participant`) at runtime. Flagship use case = **DevSquad**: Planner+Engineer+Reviewer trio in one room (the plan→execute→review loop). Transparency via `thenvoi_send_event(message_type="thought")`.
- **Pro vs Enterprise (pricing page):** **Pro $17.99/mo** = up to 40 remote agents, 40 platform agents, 250 rooms, 15 participants/room, chat export. **Memory API / `enable_memory_tools` and the Human API are ENTERPRISE-ONLY.** → with Pro, use the room log + REST context endpoint for shared state, not Memory.

### AI/ML API ($10 credits)

- Unified API to many frontier/commercial/OS models; **OpenAI-SDK-compatible** (swap `base_url` to the AI/ML endpoint + key). Partner prize: "strongest use of AI/ML API." → use for frontier reasoning/orchestration (CFO synthesis) + the confidence<0.7 escalation. Reserve the small $10 for the hard ~10%.

### Featherless AI ($25 credits)

- Serverless inference for open-source models (Qwen, Mistral, Llama, Qwen2.5-Coder, …); **OpenAI-compatible** endpoint. "$25 credits per participant, up to 1,000 participants, first-come." Partner prize: meaningful use of Featherless. → use for high-volume OS workers (intake extraction, reply formatting, the Compliance reviewer).
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you specifically went looking for and why. The research action does not touch this section. Keep it terse; the findings above are the substance.

## Sources

<!-- groundwork:auto:start sources -->
<!-- last_action: research · 2026-06-13T12:52:37Z -->
1. Band of Agents Hackathon — https://lablab.ai/ai-hackathons/band-of-agents-hackathon (canonical; Cloudflare-blocked to direct fetch, content via search index) (accessed 2026-06-13)
2. Band of Agents Hackathon (mirror, verbatim rules + tracks) — https://internshala.com/competitions/band-of-agents-hackathon/ (accessed 2026-06-13)
3. Band docs — welcome / what it is — https://docs.band.ai/welcome (accessed 2026-06-13)
4. Band docs — core concepts (agents, rooms, @mention routing) — https://docs.band.ai/core-concepts and https://docs.band.ai/core-concepts/chat-rooms (accessed 2026-06-13)
5. Band docs — SDK reference (classes, tools, adapters) — https://docs.band.ai/integrations/sdks/reference (accessed 2026-06-13)
6. Band docs — setup / auth / env vars — https://docs.band.ai/integrations/sdks/tutorials/setup (accessed 2026-06-13)
7. Band docs — agent chat context endpoint — https://docs.band.ai/api/agent-api/agent-api-context/get-agent-chat-context (accessed 2026-06-13)
8. Band docs — memories (Enterprise-only) — https://docs.band.ai/api/agent-api/agent-api-memories (accessed 2026-06-13)
9. Band pricing (Free/Pro/Enterprise) — https://www.band.ai/pricing (accessed 2026-06-13)
10. PyPI `band-sdk` — https://pypi.org/project/band-sdk/ (accessed 2026-06-13)
11. AI/ML API partner page — https://lablab.ai/tech/aiml-api (accessed 2026-06-13)
12. Featherless AI partner page — https://lablab.ai/tech/featherless (accessed 2026-06-13)
<!-- groundwork:auto:end sources -->
