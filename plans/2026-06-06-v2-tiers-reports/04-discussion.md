<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Ship TaLi v2: full report suite (P&L, category, inventory valuation, debt aging) + subscription tiers (Free/Pro/Business), Paystack paywall, rate limiting, and scheduled reports — within PythonAnywhere free-tier limits. — discussion threads

Decisions resolved + review-pass findings. **Newest first.**

Hand-authored above the rounds-index fence (intro context, conventions). The review action appends new "Round N" sections above the most recent one and keeps the index in sync.

## Open questions

These four decisions gate Phases 2c/2d and the tier matrix. Phases 2a/2b can start without them.

- **PA hosting** — stay on free tier (limits scheduled reports to 1/day, may block Paystack
  outbound/webhooks) or upgrade to a paid PA plan? (lean: upgrade once monetization is real;
  gates WP-10/11/14) — _unresolved_
- **Payment provider** — Paystack vs Flutterwave for NGN? (lean: Paystack) — _unresolved_
- **Tier boundaries + ₦ pricing** — confirm the draft Free/Pro/Business matrix (report kinds,
  formats, history depth, reports/day, scheduled cadence, NLP/day) and set Pro/Business prices.
  Draft matrix in `/Users/admin/.claude-mine/plans/tali-v2-tiers-and-reports.md` — _unresolved_
- **Tier count** — ship 3 tiers (Free/Pro/Business) or start Free/Pro only? (lean: Free/Pro to
  start, add Business later) — _unresolved_

<!-- groundwork:auto:start rounds-index -->
<!-- last_action: init · 2026-06-06 -->
_No rounds yet. Run `groundwork review` to add one._
<!-- groundwork:auto:end rounds-index -->

---

_Round entries appear below this divider, newest first._
