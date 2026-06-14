# Settings & Onboarding — implementation orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**. Each work package (WP) is a self-contained brief a fresh agent can execute from cold.

> **Source of truth**: `05-tracking.md`. At kickoff the orchestrator mirrors each WP into a harness Task and ticks the `05` checkbox on completion, keeping the live view and the durable record in lockstep.

<!-- groundwork:auto:start orchestration -->
<!-- last_action: orchestrate · 2026-06-05 -->

## Execution model

- **One repo, one branch.** All WPs land on `feature/settings-and-onboarding` (already checked out). Isolation axis = **disjoint files within one repo**, not separate repos.
- **Orchestrator** owns `05-tracking.md` status + merge order. **Subagents** own one WP each and report Definition-of-Done back.
- **The one real contention is `app/web/routes.py`** — both WP-03 and WP-04 edit it. They are *not* run by two parallel agents; one owner does both (or they run strictly sequentially), to avoid clobbering the same file.
- All other WPs touch disjoint files (`models.py` + migration; `auth.py`; `tests/`) and can overlap freely once their deps are met.

## Freeze gate (hard, sequential)

| Gate | WP | Why it gates | Sign-off check |
|---|---|---|---|
| **G-SCHEMA** | WP-01 | `usage_type` enum values + `business_profile` JSON shape are read/written by every downstream WP. Locked decision: **Option A** (columns on `users`, no new table). | `alembic upgrade head` then `alembic downgrade -1` both succeed; `app/data/models.py` `User` carries `usage_type` + `business_profile` + onboarding marker. |

Nothing in Wave 1+ starts until G-SCHEMA is signed off.

## Work-package matrix

| WP | Title | Repo | Depends on | Parallel with | Output |
|---|---|---|---|---|---|
| WP-01 | Schema migration | bookkeeper | — | — | Alembic `0003` + G-SCHEMA |
| WP-02 | Auth/data setters | bookkeeper | WP-01 | — | setter API in `app/auth.py` |
| WP-03 | Onboarding gate | bookkeeper | WP-02 | WP-04 (shared `routes.py`) | onboarding flow · D-01 |
| WP-04 | `settings` command | bookkeeper | WP-02 | WP-03 (shared `routes.py`) | settings surface · D-01 |
| WP-05 | Personalized welcome | bookkeeper | WP-03 | WP-06 | greet-by-name |
| WP-06 | Tests | bookkeeper | WP-03, WP-04 | WP-05 | pytest coverage |

### Wave plan (orchestrator spawn order)

- **Wave 0 (gate)** — WP-01 → lock G-SCHEMA.
- **Wave 1** — WP-02.
- **Wave 2 (file-coordinated)** — WP-03 + WP-04, single owner of `app/web/routes.py`.
- **Wave 3** — WP-05 + WP-06 (parallel).

### Intra-repo isolation (disjoint file scopes)

| WP | Owns (writes) | Must not touch |
|---|---|---|
| WP-01 | `app/data/models.py` (`User` only), `migrations/versions/0003_*.py` | `routes.py`, `auth.py` |
| WP-02 | `app/auth.py` (new setters) | `routes.py`, `models.py` |
| WP-03 + WP-04 | `app/web/routes.py` (one owner) | `auth.py` internals, `models.py` |
| WP-05 | `app/web/routes.py` welcome copy (after WP-03/04 merge) | setters, schema |
| WP-06 | `tests/` (new modules) | app code |

## Mock contract (so Wave 2 needn't wait on polish)

**Seam: WP-02 setter API** (lets WP-03/WP-04 start against a frozen surface before WP-02's internals are final). Agreed signatures:

```python
# app/auth.py
def set_display_name(user_id: int, name: str) -> bool: ...
def set_usage_type(user_id: int, usage: str) -> bool:          # 'personal' | 'business'
def update_business_profile(user_id: int, **fields) -> bool:   # name=, type=, currency=
def get_onboarding_state(user_id: int) -> dict | None          # what's still missing
def set_onboarding_state(user_id: int, **fields) -> bool
```

If WP-02 isn't merged yet, WP-03/WP-04 code against these names and the orchestrator wires the real impl at merge.

## Subagent brief template

```
GOAL · REPO · BRANCH/SCOPE · DEPENDS-ON · FILES (create/touch) · CONSUMES · PRODUCES ·
DO-NOT-TOUCH · DESIGN REFERENCE (if a locked D-NN applies) · DEFINITION OF DONE · MOCK · REPORT
```

---

### WP-01 — Schema migration (`usage_type` + `business_profile`)
- **GOAL**: Add the columns onboarding/settings read & write; lock the storage shape (Option A — no new table).
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: —
- **FILES**: extend `app/data/models.py` (`User` only); create `migrations/versions/0003_*.py`.
- **CONSUMES** / **PRODUCES**: — / **G-SCHEMA** (frozen schema).
- **DO-NOT-TOUCH**: the orphaned `business_id` columns (stay NULL — do not revive `DEFAULT 1`); `init_db()` DDL.
- **DEFINITION OF DONE**: `alembic upgrade head` adds `users.usage_type ENUM('personal','business') NULL`, `users.business_profile JSON NULL`, and an onboarding-progress marker; `alembic downgrade -1` reverses cleanly; model matches. See `05-tracking.md` §WP-01.
- **REPORT**: migration revision id + the exact column DDL.

### WP-02 — Auth/data setters + onboarding accessors
- **GOAL**: The read/write surface for name, usage type, business profile, onboarding progress.
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: WP-01 (G-SCHEMA)
- **FILES**: `app/auth.py` (add the setters in the Mock-contract block; extend `register_user` if needed).
- **CONSUMES** / **PRODUCES**: G-SCHEMA / the setter API for WP-03/WP-04.
- **DO-NOT-TOUCH**: existing auth/session signatures (`get_active_session`, `validate_access_code`, … keep return shapes stable).
- **DEFINITION OF DONE**: each setter persists + is unit-tested in isolation; a name written by `set_display_name` is read back by `get_active_session`. See `05-tracking.md` §WP-02.
- **REPORT**: final signatures (confirm they match the mock contract).

### WP-03 — Onboarding state machine + gate
- **GOAL**: First-run conversational onboarding — name → personal/business → (if business) business name + category; resumable across messages.
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: WP-02
- **FILES**: `app/web/routes.py` (onboarding gate before `AgentRouter` + `handle_onboarding_*`).
- **DESIGN REFERENCE**: `designs/onboarding-settings-a-conversational.html` (D-01) — match the question copy + the 4-row category list.
- **CONSUMES** / **PRODUCES**: WP-02 setters / a completed profile that unlocks normal use.
- **DO-NOT-TOUCH**: the `AgentRouter` pipeline; WP-04's `settings` handlers (shared file — coordinate).
- **DEFINITION OF DONE**: a `display_name IS NULL` user is gated into onboarding on next authenticated message; name sets it; business branch writes name + category into `business_profile`; an unrelated message mid-flow re-prompts the next unanswered question (no data loss). See `05-tracking.md` §WP-03.
- **MOCK**: if WP-02 unmerged, code against the Mock-contract signatures.
- **REPORT**: the gate insertion point in `webhook()` + the state-resume logic.

### WP-04 — `settings` command + `set …` edits
- **GOAL**: In-chat settings menu + single-field edits (text-first).
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: WP-02 · **shares `routes.py` with WP-03 (same owner)**
- **FILES**: `app/web/routes.py` (`handle_settings`; `set name|currency|type|business` parsing; extend `AUTH_COMMANDS`).
- **DESIGN REFERENCE**: `designs/onboarding-settings-a-conversational.html` (D-01) — match the numbered menu + `set currency USD` confirmation copy.
- **CONSUMES** / **PRODUCES**: WP-02 setters / the editable settings surface.
- **DO-NOT-TOUCH**: the onboarding gate (WP-03).
- **DEFINITION OF DONE**: `settings` prints the menu; `set currency USD`, `set name X`, `set type personal` each persist + echo confirmation; invalid input rejected gracefully. See `05-tracking.md` §WP-04.
- **MOCK**: same Mock-contract signatures if WP-02 unmerged.
- **REPORT**: the command table additions.

### WP-05 — Personalized welcome wiring
- **GOAL**: Greet by name once captured (light up the dead `app/web/routes.py:69` path).
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: WP-03
- **FILES**: `app/web/routes.py` (`handle_access_code` welcome + first-login welcome).
- **CONSUMES** / **PRODUCES**: captured `display_name` / personalized greeting.
- **DO-NOT-TOUCH**: unrelated reply copy.
- **DEFINITION OF DONE**: after onboarding, login welcome reads "Welcome, Ada!" not the phone number. See `05-tracking.md` §WP-05.
- **REPORT**: before/after of the welcome string.

### WP-06 — Tests
- **GOAL**: Lock the onboarding state machine + settings edits with unit tests.
- **REPO**: bookkeeper · **BRANCH**: feature/settings-and-onboarding
- **DEPENDS-ON**: WP-03, WP-04
- **FILES**: `tests/` (new modules).
- **CONSUMES** / **PRODUCES**: WP-03/WP-04 behavior / regression coverage.
- **DO-NOT-TOUCH**: app code.
- **DEFINITION OF DONE**: `python -m pytest` green, covering onboarding resume + each `set …` edit + the business branch. See `05-tracking.md` §WP-06.
- **REPORT**: test count + coverage of the resume path.

---

## Tracking protocol

- **Kickoff**: orchestrator reads `05-tracking.md`, calls `TaskCreate` once per WP (title `WP-NN <title>`, body = its Definition of Done), mirroring wave deps.
- **Live run**: on each WP completion, set the Task `completed` **and** tick the `05` checkbox — live view + durable SoT stay in lockstep.
- **Blocked / needs-decision**: mark `[!]` in `05` and surface to the user; do not guess.
- **Merge order**: WP-01 → WP-02 → (WP-03+WP-04 together) → WP-05 → WP-06. Run the full `pytest` suite before the final merge to `main`.

## Open coordination questions (resolve at kickoff)

1. **Onboarding-progress storage** — a dedicated `onboarding_step` column vs. folding state into the `business_profile` JSON. WP-01 picks one; WP-02/WP-03 must agree. (Lean: a small nullable column for clarity.)
2. **"Skip" affordance** — should onboarding allow skipping the name (re-ask later) or require it? Plan leans skippable (progressive profiling); confirm copy with the user.
3. **Phase-2 trigger** — none of these WPs touch interactive messages; D-02 stays unbuilt until Phase 2 is opened.

<!-- groundwork:auto:end orchestration -->
