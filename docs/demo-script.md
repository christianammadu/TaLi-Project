# TaLi — Band of Agents demo script (target < 5 min)

A shot-by-shot script for the submission video. The story: a WhatsApp bookkeeping
message is handled by **four specialized agents coordinating in a Band room** with a real
**plan → execute → review → human-approve** loop and a **unified audit trail** — the
Regulated & High-Stakes Workflows track.

## Pre-flight (before recording)
- [ ] `docs/credentials-setup.local.md` filled; 4 agents registered on app.band.ai (Pro).
- [ ] `.env`: `BAND_BACKEND=live`, AI/ML + Featherless keys, `BAND_*` creds, MySQL up, `alembic upgrade head`.
- [ ] `COMPLIANCE_LARGE_AMOUNT` set low (e.g. `50000`) so a demo "big" sale triggers the veto.
- [ ] `MODEL_ROUTER_SPEND_CEILING_USD` set (e.g. `8`) so credits can't be exhausted mid-demo.
- [ ] Rehearse once in `BAND_BACKEND=stub` / OpenAI-only to reserve partner credits; have a backup recording.
- [ ] Telegram bot live per [`docs/telegram-setup.md`](telegram-setup.md) (`setWebhook` done); a test account already linked to the **same** TaLi user as the WhatsApp number (so both channels share one ledger).
- [ ] Open: WhatsApp chat · **Telegram chat** · the Band room (app.band.ai) · a terminal · the `/audit` endpoint.

## Beats

**0:00–0:30 — The problem (Business Value).**
"Small businesses bookkeep over WhatsApp. TaLi turns a chat message into clean books —
and does it with a *network of agents* coordinating on **Band**, with compliance review
and a full audit trail for regulated finance."

**0:30–1:30 — Happy path + the room (Application of Technology).**
- Send WhatsApp: **`Sold 2 bags of rice 5000`**.
- Cut to the **Band room**: show the four participants and the live handoffs —
  `@tali-intake` → `@tali-ledger` → `@tali-compliance` (approve) → `@tali-cfo`.
- Back to WhatsApp: the reply `✅ Recorded: Sales — ₦5,000`.
- Voiceover: "Intake parsed it on an open-source model via Featherless; the CFO synthesised
  the reply on a frontier model via AI/ML API; OpenAI is the automatic fallback."

**1:30–2:45 — The review loop + human-in-the-loop (the differentiator).**
- Send: **`Bought generator 250000`** (over the compliance threshold).
- Band room: `@tali-ledger` posts a **proposed write**, `@tali-compliance` **rejects it
  pre-commit** ("exceeds review threshold — needs human approval"). Show the DB is untouched.
- Send the confirm reply (**`yes`**) → show the `@tali-human` decision logged in the room →
  the write commits. "The DB commit was *withheld* until reviewed and approved — two-phase."

**2:45–3:45 — The audit trail (Regulated track).**
- Terminal: `curl -H "X-Audit-Token: $AUDIT_TOKEN" localhost:5000/audit/<event_id>`.
- Walk the JSON: **parse → handoffs → write**, with the **model + cost** per step and the
  **approval**. "Every action, handoff, model, cost and approval is reconstructable by id."

**3:45–4:10 — FinOps (deliberate credit optimization).**
- Send: **`finops`** → show the reply: live **spend split by provider/model** (Featherless
  workers cheap + high-volume; AI/ML reserved for reasoning; OpenAI fallback). "We route the
  cheap, high-volume work to Featherless and reserve the $10 AI/ML credit for hard reasoning."

**4:10–4:40 — Same books, any chat (dual-channel).**
- Cut to **Telegram**, same business. Send: **`income statement for this month as pdf`**.
- The bot replies with the **branded PDF** (terracotta letterhead, COGS→gross→net) — open it on screen.
- Voiceover: "Same agents, same ledger — over WhatsApp *or* Telegram. The message arrives on
  either channel, the gateway routes it to the Band room, and the reply (or document) goes back
  out the channel it came in on. One business, one set of books, two front doors."
- _(If time is tight: just send `Sold rice 5000` on Telegram and show the same `Got it ✓`
  confirmation — proof the second channel hits the same gateway.)_

**4:40–5:00 — Close.**
"Four agents, one Band room, plan-execute-review with human-in-the-loop and a regulated-grade
audit trail — over WhatsApp and Telegram, built on Band as the coordination layer. Thanks."

## On-screen checklist (what each beat must show)
- The Band room with 4 named participants + @mention handoffs (the core scoring evidence).
- A pre-commit **rejection** that prevents a DB write.
- A human approval **in the room**.
- The `/audit/<event_id>` lifecycle JSON.
- The FinOps per-provider spend.
- The **same ledger on a second channel** (Telegram) — a message/document over both WhatsApp and Telegram.

## Fallbacks if live misbehaves
- Band live flaky → narrate over the `BAND_BACKEND=stub` run (same flow, in-process).
- Provider 429 / quota → the router falls back to OpenAI automatically; mention it as a feature.
- Keep the whole take under 5 min / 300 MB (submission limit).
