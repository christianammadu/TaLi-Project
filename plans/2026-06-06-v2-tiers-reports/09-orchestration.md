# TaLi v2 — implementation orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**. Each WP is a
self-contained brief a fresh subagent can execute against the `bookkeeper` repo.

> **Source of truth**: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into
> a harness Task and ticks the `05` checkbox on completion. **Plan-only for now — do not start
> Phase 2c/2d until the `04` open decisions are resolved.**

<!-- groundwork:auto:start orchestration -->
<!-- last_action: orchestrate · 2026-06-06T16:47:51Z -->
## Execution model

- **Isolation axis:** one git repo (`bookkeeper`), disjoint file scopes per WP (mostly new files
  or distinct functions in shared files). Use **feature branches** per WP (`v2/<slug>`); a worktree
  is optional given the low parallel count.
- **Orchestrator** owns `05-tracking.md` checkboxes + the harness Task mirror; **subagents** own one
  WP each and report Definition-of-Done back.
- v2 **extends v1** (statement + cashflow). Subagents reuse `report_renderer`, `statement_agent`,
  `queries._scope`, `whatsapp.send_document` rather than reinventing them.

## Freeze gates (hard, sequential)

| Gate | WP | Why it gates | Sign-off check |
|---|---|---|---|
| **G-REPORT-SCHEMA** | WP-01 | report_type enum + render dispatch every suite WP consumes | enum parses 4 new kinds; `render()` dispatches each; v1 still renders |
| **G-TIER-SCHEMA** | WP-06 | plan/usage/schedule tables entitlements, payments, scheduler read | DDL applies on scratch DB; models import; columns present |

## Wave plan (spawn order)

- **Wave 0 (gates, parallel to each other):** WP-01, WP-06
- **Wave 1:** WP-02, WP-03, WP-04, WP-05 (after WP-01) · WP-07, WP-10, WP-13 (after WP-06)
- **Wave 2:** WP-08, WP-09, WP-12 (after WP-07) · WP-11 (after WP-10+WP-07)
- **Wave 3:** WP-14 (after suite + WP-07 + WP-13)

## Intra-repo isolation (disjoint scopes for parallel WPs)

- WP-02..05 each add **one** `query_*` fn + **one** `_render_*` table + **one** nlp example —
  disjoint functions; only `report_renderer.py` / `queries.py` / `nlp.py` are shared, edited in
  non-overlapping spots. Land WP-01 first so the dispatch keys exist.
- WP-07..12 cluster in `entitlements.py` / `payments.py` / route files — WP-07 lands the module
  surface first; the rest import it.

## Mock contract (so cross-boundary agents don't serialize)

1. **G-REPORT-SCHEMA stub (lets WP-02..05 start before each other):** WP-01 ships `render(kind,…)`
   with a stub branch per kind returning a one-row "coming soon" table. Each suite WP replaces its
   own branch. Disjoint → no merge conflict.
2. **entitlements seam (lets WP-08/09/11/12 start before real tiers):** WP-07 ships
   `can(user, capability)` reading the matrix; until WP-06 data exists it defaults everyone to
   `free`. Consumers code against `can()`, not the DB.

## Subagent brief template

```
GOAL · REPO/BRANCH · DEPENDS-ON · FILES (create/touch) · CONSUMES · PRODUCES ·
DO-NOT-TOUCH · DEFINITION OF DONE · MOCK (if upstream not ready) · REPORT
```

---

### WP-01 — Report-schema freeze gate (G-REPORT-SCHEMA)
- **GOAL:** add `pnl|category|inventory|debt` to `StatementModel.report_type`; define `render(kind,…)` kind set + `statement_agent` dispatch+titles.
- **BRANCH:** v2/report-schema · **DEPENDS-ON:** —
- **FILES:** `app/services/validators.py`, `app/services/nlp.py`, `app/services/report_renderer.py` (dispatch stubs), `app/agents/statement_agent.py`
- **PRODUCES:** frozen enum + dispatch. **DO-NOT-TOUCH:** query layer, v1 render bodies.
- **DoD:** 4 new kinds parse; `render()` dispatches each (stub ok); v1 transactions/cashflow unaffected. **REPORT:** enum diff + dispatch map.

### WP-02 — Profit & Loss / income statement
- **GOAL:** revenue, expenses-by-category, net profit per currency/period → PDF+Excel.
- **BRANCH:** v2/report-pnl · **DEPENDS-ON:** WP-01
- **FILES:** `app/data/queries.py` (`query_pnl`), `report_renderer.py` (`_render_pnl_pdf/_xlsx`), `nlp.py` (example)
- **CONSUMES:** G-REPORT-SCHEMA dispatch. **DoD:** unit-renders both formats; net profit == `query_balance` net. **REPORT:** sample files + reconciliation.

### WP-03 — Category breakdown
- **GOAL:** income & expense by category, % of total, top categories.
- **BRANCH:** v2/report-category · **DEPENDS-ON:** WP-01
- **FILES:** `queries.py` (`query_category_breakdown`), `report_renderer.py`, `nlp.py`
- **DoD:** both formats; category totals == `query_sum`. **REPORT:** sample + reconciliation.

### WP-04 — Inventory valuation
- **GOAL:** running stock per item × last cost, total value, low-stock flags.
- **BRANCH:** v2/report-inventory · **DEPENDS-ON:** WP-01
- **FILES:** `queries.py` (`query_inventory_valuation`), `report_renderer.py`, `nlp.py`
- **DoD:** stock matches ledger guard logic; both formats. **REPORT:** sample + a spot-checked item.

### WP-05 — Debt / receivables aging
- **GOAL:** outstanding per person, buckets 0–30/31–60/61–90/90+ from `debt_logs`/`debt_balances`.
- **BRANCH:** v2/report-debt-aging · **DEPENDS-ON:** WP-01
- **FILES:** `queries.py` (`query_debt_aging`), `report_renderer.py`, `nlp.py`
- **DoD:** buckets sum to total outstanding; both formats. **REPORT:** sample + bucket sum check.

### WP-06 — Tier & usage schema freeze gate (G-TIER-SCHEMA)
- **GOAL:** `users.plan/plan_status/plan_started_at/plan_expires_at` + `subscriptions`, `usage_counters`, `report_schedules` tables via startup DDL + models.
- **BRANCH:** v2/tier-schema · **DEPENDS-ON:** —
- **FILES:** `app/data/database.py`, `app/data/models.py`
- **PRODUCES:** G-TIER-SCHEMA. **DO-NOT-TOUCH:** id-type of existing tables (additive only).
- **DoD:** DDL applies on scratch DB; models import; `plan` defaults `free`. **REPORT:** DDL + model diff.

### WP-07 — Entitlements module
- **GOAL:** tier→capability matrix + `can(user, capability) -> (bool, reason)`.
- **BRANCH:** v2/entitlements · **DEPENDS-ON:** WP-06
- **FILES:** `app/services/entitlements.py` (new)
- **DoD:** unit matrix free/pro/business → expected allow/deny per capability. **MOCK:** default `free` until data exists. **REPORT:** matrix + tests.

### WP-08 — Gating + rate-limit enforcement
- **GOAL:** enforce `can()` before report gen; per-user/day `usage_counters` (reports + nlp); limit message.
- **BRANCH:** v2/gating · **DEPENDS-ON:** WP-07
- **FILES:** `statement_agent.py`, `agent_1_intake.py`, `entitlements.py` (counters)
- **DoD:** gated→upsell; over-cap→limit msg; counter resets by date key. **REPORT:** before/after for a free vs pro user.

### WP-09 — Manual upgrade + upsell copy
- **GOAL:** manual `plan` upgrade path (testable w/o payments) + WhatsApp upsell copy.
- **BRANCH:** v2/manual-upgrade · **DEPENDS-ON:** WP-07
- **FILES:** `app/web/routes.py`, `entitlements.py`
- **DoD:** manual upgrade flips entitlements live; upsell renders for a denied capability. **REPORT:** demo transcript.

### WP-10 — Paystack payments service
- **GOAL:** init transaction → payment link; verify by reference.
- **BRANCH:** v2/payments · **DEPENDS-ON:** WP-06 · **DECISION-GATED:** PA hosting + provider (`04`)
- **FILES:** `app/services/payments.py` (new)
- **DoD:** test-mode init returns a link; verify confirms a paid reference. **REPORT:** test-mode call logs.

### WP-11 — Paystack webhook + activation
- **GOAL:** `POST /payments/paystack/webhook` HMAC-SHA512 verify; on `charge.success` activate plan +30d + WhatsApp confirm; idempotent on `reference`.
- **BRANCH:** v2/payment-webhook · **DEPENDS-ON:** WP-10, WP-07 · **DECISION-GATED**
- **FILES:** `app/web/routes.py` or `payment_routes.py` (new), `entitlements.py` (activate)
- **DoD:** test webhook upgrades plan; replay idempotent; tampered body rejected. **REPORT:** 3 webhook cases.

### WP-12 — Subscription lifecycle expiry
- **GOAL:** expire lapsed plans (`plan_expires_at < now → expired`, downgrade).
- **BRANCH:** v2/sub-expiry · **DEPENDS-ON:** WP-07
- **FILES:** `entitlements.py`, `scripts/expire_subscriptions.py` (new PA task)
- **DoD:** lapsed user downgraded; entitlements reflect it. **REPORT:** before/after.

### WP-13 — Report schedules
- **GOAL:** `report_schedules` rows + create/list over WhatsApp.
- **BRANCH:** v2/schedules · **DEPENDS-ON:** WP-06
- **FILES:** `models.py` (model in G-TIER-SCHEMA), `statement_agent.py` (commands)
- **DoD:** create/list a schedule; correct `next_run_at`. **REPORT:** demo.

### WP-14 — Scheduled-report runner + rollout
- **GOAL:** PA scheduled task: find due schedules → generate via StatementAgent → deliver → advance `next_run_at`; cadence gated by tier; e2e rollout verification.
- **BRANCH:** v2/scheduler · **DEPENDS-ON:** WP-13, WP-02, WP-03, WP-04, WP-05, WP-07 · **DECISION-GATED** (cadence/hosting)
- **FILES:** `scripts/run_scheduled_reports.py` (new)
- **DoD:** dry-run generates due reports + advances `next_run_at`; free users get none; one batched daily run fits free-tier task budget. **REPORT:** dry-run log.

---

## Tracking protocol

- **Kickoff:** orchestrator reads `05-tracking.md`, calls `TaskCreate` once per WP (title `WP-NN <title>`, body = DoD), mirroring wave deps.
- **Live run:** on each WP completion, set the Task `completed` **and** tick the `05` checkbox (durable SoT) in lockstep.
- **Blocked / needs-decision:** WP-10, WP-11, WP-14 wait on the `04` decisions — keep `[!]` until resolved.
- **Merge order:** gates (WP-01, WP-06) first; then per-wave; WP-14 last.

## Open coordination questions (resolve at kickoff)

From `04-discussion.md` (all unresolved — gate Phases 2c/2d):
1. **PA hosting** — free vs paid? (gates WP-10/11/14 feasibility)
2. **Payment provider** — Paystack vs Flutterwave? (lean Paystack)
3. **Tier boundaries + ₦ pricing** — confirm matrix; set Pro/Business prices.
4. **Tier count** — Free/Pro/Business vs Free/Pro to start?
<!-- groundwork:auto:end orchestration -->
