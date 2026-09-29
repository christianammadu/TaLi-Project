# Automated Debt Recovery & Settlement Engine — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 2: Daily Workflow & Viral Retention.
- **Branch Discipline:** Base branch `feat/automated-debt-recovery-engine`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Debt Ledger & Aging Analysis Service | Wave 2 | — | `feat/automated-debt-recovery-engine` |
| WP-02 | Conversational 'Who Dey Owe Me' Intent Parser | Wave 2 | WP-01 | `feat/automated-debt-recovery-engine` |
| WP-03 | Automated Polite WhatsApp/SMS Debt Reminders | Wave 2 | WP-02 | `feat/automated-debt-recovery-engine` |
| WP-04 | Paystack Direct Debt Payment Links & Reconciliation | Wave 2 | WP-03 | `feat/automated-debt-recovery-engine` |
| WP-05 | Debt Recovery Test Suite & Safe Reminder Limits | Wave 2 | WP-04 | `feat/automated-debt-recovery-engine` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Debt Ledger & Aging Analysis Service
- **GOAL:** Build debtor management and aging bucket calculations (0-30 days, 31-60 days, 60+ days) in app/services/debt_service.py.
- **REPO/BRANCH:** tali / `feature/wp-01-debt-ledger-&-aging-analy`
- **DEPENDS-ON:** —
- **FILES:** app/services/debt_service.py, app/data/models.py
- **DEFINITION OF DONE:** Accurate customer debt balances, partial payment deductions, and aging classification.

---

### WP-02 — Conversational 'Who Dey Owe Me' Intent Parser
- **GOAL:** Teach intake agent to parse Nigerian debt queries like 'who dey owe me', 'kemi don pay 5k', 'remind emeka'.
- **REPO/BRANCH:** tali / `feature/wp-02-conversational-'who-dey-o`
- **DEPENDS-ON:** WP-01
- **FILES:** app/agents/debt_agent.py, app/services/nlp.py
- **DEFINITION OF DONE:** High-confidence parsing of debtor names, partial settlements, and reminder triggers.

---

### WP-03 — Automated Polite WhatsApp/SMS Debt Reminders
- **GOAL:** Generate gentle, culturally respectful debt reminder messages with merchant approval step.
- **REPO/BRANCH:** tali / `feature/wp-03-automated-polite-whatsapp`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/debt_reminders.py, app/channels/whatsapp.py
- **DEFINITION OF DONE:** Tone-sensitive reminder templates in English and Pidgin; merchant confirms before dispatch.

---

### WP-04 — Paystack Direct Debt Payment Links & Reconciliation
- **GOAL:** Attach one-click Paystack payment link to debt reminders for instant settlement into merchant's account.
- **REPO/BRANCH:** tali / `feature/wp-04-paystack-direct-debt-paym`
- **DEPENDS-ON:** WP-03
- **FILES:** app/web/billing_routes.py, app/services/debt_service.py
- **DEFINITION OF DONE:** Paystack customer payment link generated; webhook auto-settles debt entry upon successful payment.

---

### WP-05 — Debt Recovery Test Suite & Safe Reminder Limits
- **GOAL:** Add tests validating debt lifecycle, partial repayments, rate limiting (max 1 reminder/day/customer).
- **REPO/BRANCH:** tali / `feature/wp-05-debt-recovery-test-suite-`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_debt_recovery.py
- **DEFINITION OF DONE:** Zero duplicate reminders, correct balance updates after partial payments, harassment-prevention limits.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
