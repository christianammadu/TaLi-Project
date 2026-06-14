<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Ship TaLi v2: full report suite (P&L, category, inventory valuation, debt aging) + subscription tiers (Free/Pro/Business), Paystack paywall, rate limiting, and scheduled reports — within PythonAnywhere free-tier limits.

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-06-06 -->
Ship TaLi v2: full report suite (P&L, category, inventory valuation, debt aging) + subscription tiers (Free/Pro/Business), Paystack paywall, rate limiting, and scheduled reports — within PythonAnywhere free-tier limits.
<!-- groundwork:auto:end goal -->

## Context

TaLi v1 gives every user filtered **statement** + **cashflow** documents (PDF/Excel) over
WhatsApp. v2 turns reporting depth into a **paid product**: a fuller accounting report
suite, gated by **subscription tier**, enforced by a **paywall** + **rate limits**, with
optional **scheduled/auto-sent** reports. Report depth, automation, and volume are the
things users will pay for — so the tier system and the report suite are designed together.

Source notes drafted at `/Users/admin/.claude-mine/plans/tali-v2-tiers-and-reports.md`.
This is **plan-only** — no implementation in this pass.

**The binding constraint is PythonAnywhere's free tier:** whitelist-only outbound (may block
Paystack API/webhooks), **1 daily scheduled task**, single worker, tight CPU-seconds.
Real monetization likely needs a **paid PA plan** — that hosting decision gates Phases 2c/2d
(see `04-discussion.md` open questions). Phases 2a/2b are buildable on free tier as-is.

## Architecture

v2 extends v1's read-only document pipeline and adds a monetization layer in front of it:

```
WhatsApp ─▶ IntakeAgent (NLP) ─▶ entitlements.can(user, capability)
                                      │ allow ─▶ StatementAgent ─▶ report_renderer ─▶ send_document
                                      │ deny  ─▶ upsell + Paystack link
Paystack webhook ─▶ payments.verify ─▶ entitlements.activate(plan)
PA scheduled task ─▶ scheduled-report runner ─▶ StatementAgent (per due schedule)
```

Two freeze gates anchor the build: **G-REPORT-SCHEMA** (the extended statement contract the
report suite fans out from) and **G-TIER-SCHEMA** (the plan/usage DB shape entitlements,
gating, payments and the scheduler all read).

### Shared state contract

| Field | Type | Writer | Readers |
|---|---|---|---|
| `StatementModel.report_type` | enum (+pnl/category/inventory/debt) | WP-01 | report_renderer, statement_agent, nlp |
| `users.plan` / `plan_status` / `plan_expires_at` | enum/timestamp | WP-06, payments (WP-11), expiry (WP-12) | entitlements (WP-07) |
| tier→capability matrix | dict | WP-07 (`entitlements.py`) | gating (WP-08), upsell (WP-09), scheduler (WP-14) |
| `usage_counters` (per user/day) | rows | WP-08 | WP-08 (rate-limit check) |
| `report_schedules.next_run_at` | timestamp | WP-13, runner (WP-14) | runner (WP-14) |
| Paystack `reference` (idempotency) | string | WP-11 | WP-11 (replay guard, reuses processed_events pattern) |

## Phases

> **Detail scales with proximity.** Current phase is fully detailed (concrete paths, tasks, risks). Next phase is sketched (scope + key open questions). Later phases are stubbed (one paragraph each). Use `(sketch)` / `(stub)` annotations on phase headers so the contract is explicit.

### Phase 2a — Full report suite (detailed)

Extends v1's renderer/agent/queries with four new report kinds (P&L, category breakdown,
inventory valuation, debt/receivables aging), default format **both PDF+Excel**. Independent
of monetization — ships value on free tier immediately. Gated by **G-REPORT-SCHEMA** (WP-01);
WP-02..05 fan out in parallel after it.

### Phase 2b — Tiers + gating + rate limiting (detailed)

Plan/usage DB shape (**G-TIER-SCHEMA**, WP-06) → `entitlements.py` (WP-07) → gate + rate-limit
enforcement (WP-08) → manual-upgrade + upsell copy (WP-09). Testable end-to-end with manual
plan upgrades, no payment provider yet. Buildable on free tier.

### Phase 2c — Paywall / Paystack (sketch)

Payment-link init + signature-verified webhook that activates plans; subscription expiry.
**Blocked on the PA-hosting + provider decisions** (outbound/webhook reachability on free tier).

### Phase 2d — Scheduled / automated reports (sketch)

`report_schedules` + a PA scheduled-task runner that generates due reports via StatementAgent;
cadence richness tied to tier. Free tier allows only 1 daily task → one batched run.

## Freeze gates

- **G-REPORT-SCHEMA** (owner WP-01) — the extended `StatementModel.report_type` enum + the
  `report_renderer.render(kind, …)` kind set + `statement_agent` dispatch map. Must lock before
  WP-02..05 (each new report) and WP-14 (scheduler) build. Sign-off: schema PR merged, the four
  new kinds parse, renderer dispatch stubbed for each.
- **G-TIER-SCHEMA** (owner WP-06) — `users.plan/plan_status/plan_started_at/plan_expires_at`,
  `subscriptions`, `usage_counters`, `report_schedules` tables (startup DDL + models). Must lock
  before entitlements (WP-07), payments (WP-10/11), expiry (WP-12), scheduler (WP-13/14).
  Sign-off: DDL applied on a scratch DB, models import, columns present.

## Critical files

### `bookkeeper/` (extends v1)

- `app/services/validators.py` — extend `StatementModel.report_type` enum (WP-01)
- `app/services/nlp.py` — new report-kind examples/rules (WP-01..05)
- `app/data/queries.py` — `query_pnl`, `query_category_breakdown`, `query_inventory_valuation`, `query_debt_aging` (WP-02..05)
- `app/services/report_renderer.py` — one `_render_*` table per new kind (WP-02..05)
- `app/agents/statement_agent.py` — dispatch + titles/labels + gate check (WP-01, WP-08)
- `app/data/database.py` + `app/data/models.py` — plan/usage/schedule tables (WP-06, WP-13)
- `app/services/entitlements.py` *(new)* — tier→capability matrix + `can()` (WP-07)
- `app/services/payments.py` *(new)* — Paystack init + verify (WP-10)
- `app/web/routes.py` or `payment_routes.py` *(new)* — Paystack webhook (WP-11)
- `scripts/run_scheduled_reports.py` *(new)* — PA scheduled-task runner (WP-14)

## Reuse map — what we lift, reimplement, or drop

_For any non-trivial software project that integrates with existing code. The explicit "we built this fresh / we copied that / we delegated there / we deleted that" table. Lifts go in `drafts/` with the standard header; built-fresh goes in `05-tracking.md` as a WP; deletes are a WP too._

| Concern | Strategy | Source / target | Notes |
|---|---|---|---|
| _e.g._ Schema | **Lift** | from `pkgs/_review/<x>/.../schema.ts` → `drafts/schema.ts` → consumer WP-NN | byte-identical with `<other source>`; renamed `Beat → Cell` at the boundary |
| _e.g._ Canvas primitive | **Extract** | from `shell/src/shell/home/home.tsx` → `contract/src/canvas/` | gates WP-NN; see `06-canvas-extraction.md` diff plan |
| _e.g._ Adapter A | **Build fresh** | `WP-NN` ships `path/to/adapter.ts` | depends on contract WP-NN |
| _e.g._ Library X | **Net-zero-fork** | npm-depend `@org/x@version`; integrate via the public surface | upstream stability check: `<source>` |
| _e.g._ Legacy viewer | **Drop** | `path/to/old-viewer.tsx` removed in WP-NN | nothing depends on it; verified by grep |

### Upstream library posture

_If integrating with multiple libraries, document the per-library strategy. Studio's "net zero forks" policy is a useful default — never fork an upstream; integrate via published API surfaces or peer sidecars._

## Renderer / adapter contracts

_Trait / interface definitions for any pluggable seam. Each must lock before its consumers start (`G-ADAPTER`-style gate). Annotate with `(locked Round N)` when frozen._

## Risks + alternatives

- **R1 — PA free-tier outbound whitelist blocks Paystack.** The single biggest risk; gates 2c.
  Mitigation: confirm reachability early, or upgrade to paid PA (decision in `04`). Alternative
  considered: Flutterwave (same constraint).
- **R2 — 1 daily scheduled task on free tier** caps scheduled-report cadence. Mitigation: one
  batched daily run for all due schedules; richer cadence requires paid hosting.
- **R3 — Synchronous webhook + heavier reports** (P&L/inventory across large books) risk webhook
  timeout on the single worker. Mitigation: keep queries indexed, cap rows, lean on existing
  idempotency; revisit async only if needed.
- **R4 — Payment-state correctness** (double-charge, replayed webhook, expiry race). Mitigation:
  idempotency on Paystack `reference` (processed_events pattern), signature verification, an
  explicit lifecycle state machine (WP-12).
- **R5 — OpenAI cost blowout** from heavy users. Mitigation: the rate-limit counters double as a
  per-tier NLP-call cost guard (WP-08).
- **Alternative rejected:** building monetization before the report suite — there'd be nothing
  worth gating. Suite (2a) first, then tiers.

## ID registry

The full ID registry is in `.groundwork.json.ids`. Local cross-reference index:

<!-- groundwork:auto:start ids -->
<!-- last_action: init · 2026-06-06 -->
_No IDs allocated yet. The review action populates this index._
<!-- groundwork:auto:end ids -->

## Verification

_Per-phase ship gates — concrete, runnable checks. Each item must be observable (a passing test, a green typecheck, a manual screenshot diff, a user-confirmed signal). "Stakeholders are happy" is not a verification item; "DSP smoke test renders the fixture in <10s on a dev box" is._

### Phase 2a verification

1. Each new report (P&L, category, inventory, debt-aging) unit-renders a valid PDF + XLSX from
   sample rows (magic-byte check, as v1 did in `/tmp/test_reports.py`).
2. Live NLP classifies a request for each kind into `intents:["statement"]` with the right `report_type`.
3. P&L net profit reconciles against `balance`; category totals reconcile against `query_sum`.

### Phase 2b verification

1. `entitlements.can()` unit matrix: free vs pro vs business → expected allow/deny per capability.
2. A gated request as a free user returns the upsell; as pro returns the document.
3. Exceeding the daily report cap returns the limit message; counter resets next day.

### Phase 2c verification

1. Paystack **test mode** end-to-end: link → test card → webhook upgrades plan → WhatsApp confirmation.
2. Replayed webhook is idempotent (no double upgrade); tampered body fails signature check.
3. Expiry task downgrades a lapsed plan; entitlements reflect it.

### Phase 2d verification

1. Scheduled-task dry-run finds due schedules, generates via StatementAgent, advances `next_run_at`.
2. Tier gating respected (free user gets no scheduled reports).
