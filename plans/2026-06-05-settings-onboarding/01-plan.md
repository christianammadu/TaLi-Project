<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Settings & Onboarding — name capture, usage type, and where settings live

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-06-05 -->
Add a settings mechanism plus onboarding that captures display name and usage type (business/personal) so welcomes are personalized and business users can record business info; decide whether settings live on an authenticated web page or via WhatsApp commands.
<!-- groundwork:auto:end goal -->

## Context

_Why now, what changed, what's at stake._

TaLi's whole thesis is "bookkeeping that lives in the chat you already use" — there is **no authenticated web app**, only a marketing site and a one-shot register/verify handshake (`docs/auth_system_proposal.md:22`, `03-research-internal.md`). Three gaps have accumulated against that thesis:

1. **Personalization is half-wired and dead.** `User.display_name` exists and the login welcome already reads it — `name = user.get('display_name') or user['phone_number']` (`app/web/routes.py:69`) — but nothing ever *writes* it, so every welcome falls back to a bare phone number.
2. **No way to change settings.** A user cannot change their currency, name, or alert thresholds after registration. `base_currency` and `alert_thresholds` are live columns with no edit surface.
3. **No notion of "what is this account for."** `business_id` is an orphaned column (no `businesses` table; migration `0002` NULLed it after a multi-tenant leak — `app/data/models.py:8`). There's no way to say "I'm a business" and record business info.

This plan closes all three with the **smallest surface that stays on-thesis**: capture a name + usage type during onboarding, and give users an in-chat settings menu. The headline decision — **web page vs. WhatsApp** — is resolved below in favour of WhatsApp, with the reasoning made explicit so it can be challenged.

## The headline decision — settings channel

> **Recommendation: settings and onboarding live IN WhatsApp, not on a new authenticated web page.**

| Factor | In-chat (WhatsApp) | New authenticated web page |
|---|---|---|
| **Build cost** | Reuses the existing command dispatcher + session (`app/web/routes.py:25`, `app/auth.py:269`). | Requires a **net-new logged-in web layer** — cookies, login, CSRF, session store. None exists today. |
| **On-thesis** | ✅ "Everything happens in the chat." | ❌ Contradicts the product's core promise; a second surface to maintain. |
| **Auth** | Already authenticated — the active WhatsApp session *is* the identity. | A second auth ceremony (the user would log into the web *and* WhatsApp). |
| **Capability ceiling** | Buttons (≤3) and lists (≤10 rows) need **no template approval** (`02-research-external.md` §1). Rich multi-field forms need WhatsApp **Flows** (Meta review + no desktop render) (§2). | Unlimited form complexity, desktop-friendly. |
| **Friction** | Lowest — no app/tab switch; conversational. | A context switch out of the chat. |

**Net:** in-chat wins decisively on build cost and thesis-fit; its only real weakness (rich forms) is bounded and only bites for the business-profile capture, which we keep small. We therefore build settings/onboarding **in-chat**, using **interactive list/button messages** (no approval needed) for menus and a **plain text-command fallback** (`settings`, `set name …`). A **WhatsApp Flow** for the multi-field business-profile form is held as an explicit Phase-2 option, not Phase-1, because of the Meta-review + desktop-render constraints. A web settings page is **not** built now; the existing one-shot web "done" page remains available as a fallback host for the name question if we want a zero-new-send-code start (see Phase 1 alternative).

## Architecture

_The shape of the solution at one zoom-out level._

Three layers, all reusing existing seams:

```
WhatsApp inbound ──► app/web/routes.py:webhook()
                       │   (existing command dispatcher)
                       ├── new: onboarding gate ──► if session.display_name is NULL
                       │        → run conversational onboarding (name → usage_type → [business fields])
                       ├── new: 'settings' command ──► interactive LIST menu
                       │        → row tap / text fallback ──► guided single-field edit
                       └── (unchanged) authenticated message ──► AgentRouter (AI pipeline)

Settings store:   users.display_name (exists) · users.base_currency (exists)
                  users.alert_thresholds JSON (exists) · users.usage_type (NEW enum)
                  business profile (NEW — see Schema decision)

Send side:        app/web/whatsapp.py ── new helpers: send_buttons(), send_list()
                  (today only send_reply text + send_otp_template exist)
```

Onboarding is modelled as a **lightweight in-chat state machine** keyed off what's still missing on the user record (progressive profiling — `02-research-external.md` §3). It needs a tiny bit of conversation state; the existing `sessions` table or a small `onboarding_state` column/JSON is the candidate (decided in Schema).

### Shared state contract

_The cross-component state two or more pieces must agree on._

| Field | Type | Writer | Readers |
|---|---|---|---|
| `users.display_name` | `VARCHAR(100)` (exists) | onboarding step 1; `settings` edit | login welcome (`routes.py:69`), settings menu |
| `users.usage_type` | `ENUM('personal','business')` **(NEW)** | onboarding step 2; `settings` edit | onboarding branch, settings menu, future reports |
| `users.base_currency` | `VARCHAR(3)` (exists) | onboarding (business); `settings` edit | ledger/reporting, settings menu |
| `users.alert_thresholds` | `JSON` (exists) | `settings` edit | inventory/debt/CFO agents |
| business profile (name, type, …) | NEW (table or JSON — see Schema) | onboarding (business branch); `settings` edit | settings menu, future business reports |
| onboarding progress | NEW (column/JSON) | onboarding gate | onboarding gate (resume across messages) |

## Phases

> **Detail scales with proximity.** Phase 1 is fully detailed; Phase 2 sketched; Phase 3 stubbed.

### Phase 1 — Onboarding + name capture + usage type (in-chat, text-first)

The high-leverage, low-cost core. Answers **all three** of the user's questions with the minimum schema and zero new Meta approvals. **Locked design: `designs/onboarding-settings-a-conversational.html` (D-01)** — see Round 1. The interactive variant (`onboarding-settings-b-interactive.html`, D-02) is the Phase-2 target.

- **Schema:** add `users.usage_type ENUM('personal','business') NULL` and an onboarding-progress marker (Alembic migration `0003`). Decide business-profile storage (Schema section) — Phase 1 uses the **lighter** option.
- **Onboarding gate** in `webhook()`: when an authenticated user has `display_name IS NULL`, intercept before the AgentRouter and run a 2–3 question conversational onboarding:
  1. *"👋 Welcome! What should I call you?"* → `display_name` (one field — the single highest-leverage capture; `02-research-external.md` §3–4).
  2. *"Are you using TaLi for **personal** or **business**?"* → `usage_type` (2 reply buttons; text "1/2/personal/business" fallback).
  3. **If business:** *"What's your business name?"* → business name; *"What kind of business?"* → business type/category (short list). Currency optional. Registration number **not** asked (Nigeria informality — `02-research-external.md` §6).
- **Personalized welcome:** once name is set, the login/first-message welcome uses it (the `routes.py:69` fallback finally lights up).
- **`settings` command (text-first):** `settings` prints a numbered menu; `set name <x>`, `set currency <ISO>`, `set type <personal|business>`, `set business <name>` apply edits. Text-only so Phase 1 ships without interactive-message send code.
- **Phase 1 alternative (optional):** collect the name on the existing web `/verify-otp` "done" step (`web_routes.py:149`) instead of in-chat — reuses an existing form, zero new send code, but adds a field to a page the user sees once. In-chat is recommended for thesis-fit; this is the fallback if send-side work must be deferred.

### Phase 2 — Interactive menus + richer business profile (sketch)

Upgrade the text menus to **native interactive UX** and deepen the business profile.

- Add `send_buttons()` / `send_list()` helpers to `app/web/whatsapp.py`; render `settings` as an interactive **list** (Name · Usage type · Currency · Business info · Alerts) and onboarding usage-type as **buttons**.
- Handle interactive replies in `webhook()` (today only `type == 'text'` is accepted — `routes.py:166`).
- Optionally introduce a **WhatsApp Flow** for the business-profile form (multi-field in one screen) — gated on Meta review + the desktop-render caveat (`02-research-external.md` §2). Key open question: is a Flow worth the review overhead vs. a 2–3 button/text sequence?
- Promote business storage to a real `businesses` table if multi-tenant/multi-business is wanted (carefully, to avoid re-introducing the shared-bucket leak).

### Phase 3 — Settings depth & web parity (stub)

Per-business categories, notification preferences, language/locale, data export, and (only if demand appears) a read-only authenticated web settings view. Explicitly out of scope until Phases 1–2 prove the in-chat surface.

## Schema / contract

The pivotal decision is **how to store the business profile**. Two options:

- **Option A — light (recommended for Phase 1):** add `users.usage_type` + a `users.business_profile` **JSON** column (`{name, type, currency?}`), mirroring the existing `alert_thresholds` JSON precedent (`app/data/models.py:34`). No new table, one migration, no FK churn, no shared-bucket risk. Migration path to Option B stays open.
- **Option B — full:** a real `businesses` table (`id`, `owner_user_id`, `name`, `type`, `currency`, …) and point `users.business_id` at the new row. Proper multi-tenancy and the natural home for the orphaned `business_id`/transactions columns — but heavier, and **must avoid** the `DEFAULT 1` shared-bucket bug that migration `0002` cleaned up (`app/data/models.py:8`).

> **Freeze gate `G-SCHEMA`:** the `usage_type` enum values and the business-profile storage shape (A vs B) must lock before onboarding + settings code is written, since both read/write it. Recommended lock: **Option A** for Phase 1.

Concrete Phase-1 migration (`0003`): `ALTER TABLE users ADD COLUMN usage_type ENUM('personal','business') NULL`, `ADD COLUMN business_profile JSON NULL`, plus an onboarding-progress marker (e.g. `onboarding_step` small int, or fold into a JSON state).

## Critical files

### `bookkeeper/`

- `app/data/models.py` — **extend** `User` with `usage_type`, `business_profile` (and onboarding marker).
- `migrations/versions/0003_*.py` — **create** the new migration.
- `app/web/routes.py` — **extend** `webhook()` with the onboarding gate + `settings`/`set …` commands; add `handle_settings`, `handle_onboarding_*`.
- `app/auth.py` — **extend** `register_user()` / add setters (`set_display_name`, `set_usage_type`, `update_business_profile`); the session dict already carries the fields.
- `app/web/web_routes.py` — **(optional, Phase-1 alt)** add name field to the post-OTP "done" step.
- `app/web/whatsapp.py` — **(Phase 2)** add `send_buttons()` / `send_list()`.
- `tests/` — **add** onboarding state-machine + settings-edit unit tests.

## Reuse map — what we lift, reimplement, or drop

| Concern | Strategy | Source / target | Notes |
|---|---|---|---|
| Per-user settings bag | **Reuse** | `users.alert_thresholds` JSON pattern → `business_profile` JSON | Established precedent; no per-field migration. |
| Name in welcome | **Reuse (activate)** | `app/web/routes.py:69` already reads `display_name` | Just needs a writer — no new read path. |
| Auth/session for settings | **Reuse** | `get_active_session()` returns `user_id`/`display_name`/`business_id` (`app/auth.py:269`) | In-chat settings need **no new auth**. |
| Command routing | **Extend** | `PUBLIC/AUTH_COMMANDS` + `handle_*` (`app/web/routes.py:25`) | Add `settings`/`set …` in the same pattern. |
| `business_id` orphan column | **Defer / avoid** | leave NULL in Phase 1 (Option A) | Don't re-introduce the `DEFAULT 1` shared-bucket leak (`models.py:8`). |
| Interactive buttons/lists | **Build fresh (Phase 2)** | new helpers in `app/web/whatsapp.py` | Today only text + OTP template send exist. |
| WhatsApp Flow form | **Build fresh (Phase 2, optional)** | Meta-reviewed Flow for business profile | Gated on review + desktop caveat. |

## Risks + alternatives

- **Risk — onboarding state across messages.** WhatsApp is stateless per message; a multi-step onboarding needs resumable progress. *Mitigation:* persist an onboarding marker (column/JSON) and key the gate off "what's still missing," so any message resumes the next unanswered question.
- **Risk — onboarding blocks real use.** Forcing questions before a user can record a transaction could frustrate. *Mitigation:* keep it to 1 question for personal (name), 3 for business; allow "skip" → name defaults to null and we re-ask later (progressive profiling).
- **Risk — interactive messages / Flows scope creep.** *Mitigation:* Phase 1 is text-only; buttons/lists/Flows are explicitly Phase 2.
- **Risk — re-introducing the multi-tenant leak.** *Mitigation:* Phase 1 uses JSON on the user (Option A), not `business_id`; any future `businesses` table (Option B) gets explicit owner scoping + a test.
- **Alternative rejected — authenticated web settings page.** Off-thesis and requires a whole new logged-in web layer that doesn't exist (`docs/auth_system_proposal.md:22`). Revisit only in Phase 3 if demand appears.
- **Alternative rejected — collect everything at registration.** Data-minimization evidence (`02-research-external.md` §3) says more upfront fields lower completion; we capture the minimum and enrich later.

## ID registry

The full ID registry is in `.groundwork.json.ids`. Local cross-reference index:

<!-- groundwork:auto:start ids -->
<!-- last_action: init · 2026-06-05 -->
_No IDs allocated yet. The review action populates this index._
<!-- groundwork:auto:end ids -->

## Verification

### Phase 1 verification

1. `alembic upgrade head` applies `0003` cleanly; `usage_type` + `business_profile` exist on `users`; `alembic downgrade -1` reverses it.
2. New user with `display_name IS NULL` triggers onboarding on next authenticated message; answering the name question sets `display_name` and the **welcome greets by name** (not phone number).
3. Selecting "business" collects business name + type into `business_profile`; selecting "personal" skips business questions and lands the user straight in normal use.
4. `settings` prints the menu; `set name X`, `set currency NGN`, `set type personal` each persist and echo confirmation; invalid input is rejected gracefully.
5. Onboarding resumes correctly mid-flow (answer name, send an unrelated message, get re-prompted for the next unanswered question — no data loss).
6. `python -m pytest` green, including new onboarding + settings tests.

### Phase 2 verification (sketch)

1. `settings` renders as an interactive list; tapping a row opens the right edit; text fallback still works.
2. Usage-type onboarding renders as buttons; a button reply is handled (not rejected by the text-only guard at `routes.py:166`).
3. (If built) the business-profile Flow submits structured data and writes `business_profile`.
