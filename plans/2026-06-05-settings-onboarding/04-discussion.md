<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Add a settings mechanism plus onboarding that captures display name and usage type (business/personal) so welcomes are personalized and business users can record business info; decide whether settings live on an authenticated web page or via WhatsApp commands. — discussion threads

Decisions resolved + review-pass findings. **Newest first.**

Hand-authored above the rounds-index fence (intro context, conventions). The review action appends new "Round N" sections above the most recent one and keeps the index in sync.

<!-- groundwork:auto:start rounds-index -->
<!-- last_action: review · 2026-06-05T11:29:48Z -->
- **Round 1** (2026-06-05) — channel decision (in-chat WhatsApp) + design lock: **D-01** Variant A locked for Phase 1, **D-02** Variant B retained for Phase 2.
<!-- groundwork:auto:end rounds-index -->

---

_Round entries appear below this divider, newest first._

## Round 1 — channel decision + design lock for onboarding/settings (2026-06-05)

Two questions were resolved this round.

**Channel (settings + onboarding surface).** Confirmed: **in-chat WhatsApp**, not a new authenticated web page. Rationale (see `01-plan.md` §"The headline decision" + `02-research-external.md` §1): TaLi has no logged-in web layer today, so a web page means building login/session/CSRF from scratch — off-thesis and high-cost; the active WhatsApp session already authenticates the user, and interactive buttons/lists need no Meta approval. A web settings page is deferred to Phase 3, only if demand appears.

**Business-info depth.** Confirmed: **name → personal/business → (if business) business name + business category**. 3 questions max; currency optional; **registration number never required** (Nigeria SME informality — `02-research-external.md` §6). Driven by data-minimization evidence (`02-research-external.md` §3).

**Design lock.** Built two comparable mockups in `designs/`, both rendering the same content (onboarding capture + a settings menu + one edit):
- `designs/onboarding-settings-a-conversational.html` (**D-01**) — text-first; the bot asks one question at a time, the user types numbers/words. Ships Phase 1 with zero Meta approval; works on desktop.
- `designs/onboarding-settings-b-interactive.html` (**D-02**) — native WhatsApp reply buttons + list-message bottom-sheet; tap-to-choose.

**Locked (user):** **D-01 (Variant A) as the Phase-1 build target**, with **D-02 (Variant B) retained as the Phase-2 upgrade**. Rationale: A ships immediately (no interactive send code, no Meta review, renders on every device incl. WhatsApp Web); B's tap UX is the natural enhancement once `send_buttons()`/`send_list()` and interactive-reply handling land, and B still needs a text fallback for desktop — so A's text path is foundational either way.

**Considered, not built:** an authenticated web settings page (rejected — off-thesis, no auth layer); collecting everything at registration (rejected — lowers completion).

**Out of scope (this round):** a WhatsApp Flow for the business-profile form, a real `businesses` table (both Phase 2+), and any web settings parity (Phase 3).
