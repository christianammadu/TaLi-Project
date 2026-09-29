# Daily Victory Evening Recap — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 2: Daily Workflow & Viral Retention.
- **Branch Discipline:** Base branch `feat/daily-victory-evening-recap`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Daily Financial Aggregator & Milestone Detection | Wave 2 | — | `feat/daily-victory-evening-recap` |
| WP-02 | Celebration Copy Generator & Pidgin Financial Insights | Wave 2 | WP-01 | `feat/daily-victory-evening-recap` |
| WP-03 | Scheduled 8:00 PM Multi-Channel Dispatcher | Wave 2 | WP-02 | `feat/daily-victory-evening-recap` |
| WP-04 | Visual Evening Victory Card Image Generator | Wave 2 | WP-03 | `feat/daily-victory-evening-recap` |
| WP-05 | Daily Recap Scheduler & Formatting Test Suite | Wave 2 | WP-04 | `feat/daily-victory-evening-recap` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Daily Financial Aggregator & Milestone Detection
- **GOAL:** Calculate daily total sales, margin, top-selling product, and compare with 7-day average.
- **REPO/BRANCH:** tali / `feature/wp-01-daily-financial-aggregato`
- **DEPENDS-ON:** —
- **FILES:** app/services/recap_service.py, app/data/queries.py
- **DEFINITION OF DONE:** Fast aggregation query executed in <20ms; detects milestones (highest sales day, best seller).

---

### WP-02 — Celebration Copy Generator & Pidgin Financial Insights
- **GOAL:** Draft warm, motivating evening summary in Nigerian Pidgin or standard English celebrating business effort.
- **REPO/BRANCH:** tali / `feature/wp-02-celebration-copy-generato`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/recap_service.py, app/services/formatter.py
- **DEFINITION OF DONE:** Natural, upbeat recap copy with clear breakdown of Cash In, Cash Out, and Net Profit.

---

### WP-03 — Scheduled 8:00 PM Multi-Channel Dispatcher
- **GOAL:** Build scheduled cron worker delivering the daily recap to active merchants at 8:00 PM local time.
- **REPO/BRANCH:** tali / `feature/wp-03-scheduled-8:00-pm-multi-c`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/recap_scheduler.py, app/channels/registry.py
- **DEFINITION OF DONE:** Multi-channel dispatch (WhatsApp or Telegram based on user preference); skips inactive accounts.

---

### WP-04 — Visual Evening Victory Card Image Generator
- **GOAL:** Generate an aesthetic summary card image suitable for sharing on WhatsApp Status or Instagram Stories.
- **REPO/BRANCH:** tali / `feature/wp-04-visual-evening-victory-ca`
- **DEPENDS-ON:** WP-03
- **FILES:** app/services/report_renderer.py, tests/test_recap_image.py
- **DEFINITION OF DONE:** Rendered PNG victory card with merchant branding, clean layout, no emojis, professional typography.

---

### WP-05 — Daily Recap Scheduler & Formatting Test Suite
- **GOAL:** Add tests validating timezone handling (WAT UTC+1), empty-day fallback message, and dispatch failure retries.
- **REPO/BRANCH:** tali / `feature/wp-05-daily-recap-scheduler-&-f`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_daily_recap.py
- **DEFINITION OF DONE:** Comprehensive test suite covering milestone detection, zero-transaction days, and dispatch safety.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
