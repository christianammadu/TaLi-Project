<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# Harden the multi-agent conversational pipeline (off-topic guardrails, compound multi-intent execution, fuzzy inventory matching) and build a platform stakeholder dashboard for AI fleet monitoring and compliance governance. — discussion threads

Decisions resolved + review-pass findings. **Newest first.**

Hand-authored above the rounds-index fence (intro context, conventions). The review action appends new "Round N" sections above the most recent one and keeps the index in sync.

<!-- groundwork:auto:start rounds-index -->
<!-- last_action: review · 2026-09-14T18:12:52Z -->
- **Round 2** (2026-09-14) — Review pass: edge cases in Pidgin guardrails, transaction atomicity in compound statements, inventory tied-match disambiguation, and admin session security. Folded G-05..G-08; locked atomic rollback for multi-writes, tied-match clarification questions, and secure admin cookie standards.
- **Round 1** (2026-09-14) — Architecture deliberation: conversational guardrailing, compound multi-intent execution, inventory fuzzy resolution, and platform dashboard stack. Folded G-01..G-04; locked 4-layer guardrail defense, composite CFO split-routing dispatch, canonical inventory prompt injection + stemming, and server-rendered Flask/Tailwind/Chart.js admin dashboard.
<!-- groundwork:auto:end rounds-index -->

---

_Round entries appear below this divider, newest first._

## Round 2 — Review pass: edge cases in Pidgin guardrails, transaction atomicity, inventory tied-match disambiguation, and admin session security (2026-09-14)

Review pass over the architecture and implementation specifications. Evaluated operational edge cases, colloquial failure modes, partial transaction states, and authentication security. Four critical findings folded (G-05..G-08).

### Critical Gaps Folded

#### G-05 · Pidgin & Market Colloquialism Defense Against Guardrail False Positives
- **Finding**: Nigerian traders routinely converse in Nigerian Pidgin or code-switch (*"I dash am 5k"*, *"Credit 10k for oga Jude"*, *"Wetin be my stock balance?"*, *"Abeg show me wetin remain for shop"*).
- **Risk**: Overly broad English-centric regexes or negative prompts could mistakenly classify legitimate market colloquialisms as off-topic junk.
- **Fold**:
  1. Constrain pre-filter regex exclusively to explicitly non-financial action phrases (`write code`, `python script`, `translate to french`, `essay`, `who is`, `recipe for`).
  2. In `nlp.py`, explicitly enumerate Pidgin synonyms in the prompt: `dash` (gift/expense), `wetin remain` / `how much dey` (stock query), `credit` / `borrow` (debt).
  3. Touches: `01-plan.md` §Schema, `app/services/nlp.py`, `app/agents/agent_1_intake.py`.

#### G-06 · Compound Statement Atomic Rollback on Partial Mutation Failure
- **Finding**: A compound message (*"Sold 5 bags of rice 30k and bought fuel 5k, what is my balance?"*) contains multiple distinct database mutations.
- **Risk**: If the first write commits (e.g. sale recorded) but the second mutation fails (e.g. invalid category or constraint failure), the merchant's books enter an inconsistent, half-written state.
- **Fold**:
  1. Ledger must wrap all mutating operations in a compound statement within a single SQL transaction block (`BEGIN` ... `COMMIT`).
  2. If any individual mutation raises an error, issue a full `ROLLBACK`, report the exact failing item to the user, and do not execute the post-mutation query.
  3. Touches: `01-plan.md` §Phases, `app/agents/agent_2_ledger.py`.

#### G-07 · Multi-Match Disambiguation for Fuzzy Inventory Items
- **Finding**: A merchant may stock multiple related items, e.g. `"Golden Penny Flour 50kg"` and `"Golden Penny Semovita 10kg"`. An input like *"Sold 2 Golden Penny 15k"* matches both with identical substring scores.
- **Risk**: Arbitrarily picking the first match silently decrements the wrong inventory product.
- **Fold**:
  1. In `resolve_inventory_item()`, if multiple items have tied top-level match scores (e.g. multiple items share the same search term), do not guess.
  2. Return `status: clarification_needed` with a numbered list of the matching products.
  3. Touches: `01-plan.md` §Schema, `app/data/queries.py`, `app/agents/agent_2_ledger.py`.

#### G-08 · Stakeholder Admin Authentication Security & Cookie Hardening
- **Finding**: The stakeholder dashboard (`/admin/`) surfaces confidential business GMV, token budgets, and compliance transactions.
- **Risk**: Insecure session storage, missing CSRF protection, or hardcoded passwords risk platform compromise.
- **Fold**:
  1. Configure `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` (bcrypt) via `.env`.
  2. Secure session cookies with `HttpOnly=True`, `SameSite='Lax'`, and `Secure=True` (when running over HTTPS).
  3. Enforce rate-limiting on `/admin/login` (max 5 failed attempts per 15 minutes).
  4. Touches: `01-plan.md` §Critical files, `app/admin/auth.py`.

---

### Clarifying Answers from Round 1
- **Compliance Notification**: Approved transactions in the web compliance queue *do* fire an immediate WhatsApp/Telegram notification to the merchant confirming approval.
- **Merchant Web Portal**: Deferred to Phase 3; will use WhatsApp magic-link OTP authentication rather than username/password.

---

### What's Locked vs. What's Open
**Locked this round:**
- Strict scoping of pre-filter regex with Pidgin inclusion.
- All-or-nothing SQL transaction atomicity for compound mutations.
- Interactive disambiguation when fuzzy inventory matches are tied.
- Bcrypt + hardened session cookies for the Admin Dashboard.
**Still open:**
- Auto-refresh polling interval for the live compliance queue in the web UI (Default: 10s HTMX polling).

---

## Round 1 — Architecture deliberation: conversational guardrailing, compound multi-intent execution, inventory fuzzy resolution, and platform dashboard stack (2026-09-14)

Founding architecture round addressing operational feedback from live chat testing and planning the stakeholder observability portal. Four major capability gaps analyzed, trade-offs evaluated, and design decisions locked.

### Critical Gaps Analyzed & Folded

#### G-01 · LLM Scope Creep & Vulnerability to Prompt Abuse
- **Problem**: Users on WhatsApp/Telegram frequently attempt off-topic interactions (essay writing, coding questions, general trivia, translations, or prompt injection). Currently, all unrecognized text that misses the regex fast-paths routes directly into `parse_message()`, consuming LLM tokens and risking confusing conversational responses or prompt leakage.
- **Evaluation**:
  1. *Option A: Rely entirely on LLM system prompt instructions.* High latency, consumes tokens on off-topic junk, and vulnerable to jailbreaks.
  2. *Option B: Standalone moderation classifier API.* Extra network round-trip and extra latency per webhook.
  3. *Option C (Chosen): 4-layer defense in depth.*
     - **Layer 1 (Deterministic Fast-Reject)**: Pre-LLM regex/keyword interceptor in `agent_1_intake.py` checking for known off-topic keywords (e.g. `code`, `essay`, `translate`, `recipe`, `jailbreak`, `DAN`). Returns instant canned guidance with zero token cost.
     - **Layer 2 (System Prompt Hard Negatives)**: Explicit boundary in `nlp.py` mandating that non-bookkeeping text MUST be classified as `{"intents": ["unknown"], "confidence": 0.0, "status": "unknown"}`.
     - **Layer 3 (Strict Pydantic Output Enforcement)**: `UnifiedResponseModel` strips out any free-text responses from the model and enforces standard branded fallback guidance.
     - **Layer 4 (FinOps Abuse Throttling)**: A user triggering 3 consecutive `unknown` intents is placed on a 10-minute LLM cooldown, protecting the budget ceiling.
- **Decision (Locked)**: Implement Option C. Zero token burn on obvious junk; multi-tier containment on ambiguous inputs.

#### G-02 · Compound Statement Execution Failure in `split_routing`
- **Problem**: Natural business messages often combine multiple intents: a transaction write + an inventory delta + a financial report or balance question (*"Sold 5 bags of rice for 30k cash, what's my total rice stock now and show my balance for today"*).
  - While `nlp.py` correctly parses multiple intents (`record_transaction`, `inventory`, `query`), the downstream execution pipeline drops the query.
  - In `agent_1_intake.py:548`, mutating intents trigger `_store_pending`, holding the write for confirmation but dropping the read query.
  - In `agent_2_ledger.py:427` and `agent_3_cfo.py:144`, `split_routing` only processes `transactions`, `inventory`, and `debts`. There is no execution logic for `query`, `report`, or `statement`.
- **Evaluation**:
  1. *Option A: Split into multiple sequential turn prompts.* Forces the user into a disjointed back-and-forth chat.
  2. *Option B: Ignore read queries if a write is present.* Degrades merchant trust; merchant asked a question and got silence.
  3. *Option C (Chosen): Unified Composite Dispatch.*
     - When `split_routing` is dispatched, the Ledger writes the transactions, inventory movements, and debt entries.
     - Immediately following write persistence (or during pending confirmation review), the query payload is handed to `TransactionAgent.query(parsed_query)` on the current state.
     - Both the write confirmations and the query answers are bundled into the event payload passed to `agent_3_cfo.py`.
     - `agent_3_cfo.py` composes a unified, structured WhatsApp response with distinct visual sections (Recorded ✅, Inventory 📦, Balance/Report 📊).
- **Decision (Locked)**: Implement Option C. Support multi-intent compound statements end-to-end without dropping read queries.

#### G-03 · Inventory Lookup Failures ("Item not found even though it exists")
- **Problem**: When merchants ask *"how much rice do I have left?"* or record sales of existing items, the system frequently fails to locate existing stock records. Root-cause analysis revealed four structural flaws:
  1. *Strict Exact Equality SQL*: `WHERE item_name = %s` or `WHERE name = %s` fails when the item was saved as `"50kg bag of rice"` and queried as `"rice"`.
  2. *Pluralization / Stemming Mismatches*: Words like `"eggs"` vs `"egg"`, `"cartons"` vs `"carton"`, `"shoe"` vs `"shoes"` fail exact comparison.
  3. *Dual Table Drift*: `products` (legacy) vs `inventory_items` (new model). `query_stock_levels` only queries `inventory_movements` + `inventory_items`, returning zero if items only exist in `products`.
  4. *`business_id` NULL Mismatches*: Queries filtering by `business_id = %s` return empty rows because session `business_id` is often `NULL` while rows may have `business_id = 1`.
- **Evaluation**:
  1. *Option A: Raw SQL `LIKE %item%` alone.* Fast, but still misses synonyms or word boundary variations.
  2. *Option B: Vector semantic search on inventory names.* High complexity, requires vector DB and extra embedding API calls on every item lookup.
  3. *Option C (Chosen): Multi-Tiered Canonical Resolution.*
     - **Tier 1 (Prompt Canonicalization)**: When building the system prompt in `nlp.py`, inject the merchant's list of existing active product names (`AVAILABLE PRODUCTS: [...]`) alongside categories. The LLM then maps informal phrasing (*"sold 2 bags of golden penny"*) directly to the canonical database name (`golden penny flour`).
     - **Tier 2 (Fuzzy & Stemmed SQL Fallback)**: In `agent_2_ledger.py` and `inventory_agent.py`, if exact match fails, fallback to case-insensitive lower match -> singular/plural stemming (`rstrip('s')`) -> substring `LIKE %item%`.
     - **Tier 3 (Schema & Scope Unification)**: Scope all inventory queries by `user_id` consistently, ensuring dual-write integrity between `inventory_items` and `products` until the legacy table is retired.
- **Decision (Locked)**: Implement Option C. Combines LLM-side canonical normalization with robust DB-side fuzzy fallback.

#### G-04 · Platform Stakeholder & Operations Dashboard Architecture
- **Problem**: TaLi currently has no administrative or operational visibility. Stakeholders cannot view aggregate transaction volume, monitor LLM costs against the FinOps ceiling, track model fallback frequencies, or manage transactions held in the compliance review queue.
- **Evaluation**:
  1. *Option A: Standalone Single-Page Application (React / Next.js).* Requires separate deployment, Node build pipeline, CORS configuration, and JWT authentication. Heavy overhead for current stage.
  2. *Option B (Chosen): Flask Blueprint + Server-Rendered Jinja2 + Tailwind CSS + Chart.js / HTMX.*
     - Leverages existing Flask application factory, database connection pooling, and configuration.
     - Zero additional build steps or node dependencies; runs directly inside the Python container.
     - Delivers responsive, high-performance dashboards, real-time charts via Chart.js, and interactive tab switches via HTMX.
     - Implements role-based stakeholder session authentication (`app/admin/auth.py`).
- **Surfaces Included in Stakeholder Dashboard**:
  1. **AI Fleet & FinOps Monitor**: Live spend tracking, provider share (% OpenAI vs % AI/ML API fallback), p95 latency, error rates, and prompt token usage from `ai_logs`.
  2. **Compliance & Human-in-the-Loop Hub**: Live queue of transactions flagged by `compliance_agent.py` or sitting in `ReviewQueue`. One-click approve/reject actions that resume the agent room.
  3. **Merchant Operations & GMV Overview**: Daily active merchants, transaction counts, platform GMV (Naira, USD, GBP), and onboarding completion rates.
- **Decision (Locked)**: Implement Option B. Fast, zero-dependency, production-ready admin blueprint integrated directly into the Flask application.

---

### What's Locked vs. What's Open

#### Locked in Round 1:
- 4-layer defense in depth for chat scope enforcement (Pre-filter regex -> System prompt -> Schema validation -> FinOps throttling).
- Composite `split_routing` in `agent_2_ledger.py` and `agent_3_cfo.py` so compound messages execute writes AND return query/report answers in one response.
- Multi-tier inventory resolution: Known product names injected into NLP system prompt + fuzzy/stemmed SQL fallbacks scoped by `user_id`.
- Stakeholder dashboard implemented as an integrated Flask blueprint (`app/admin/`) with server-rendered Jinja2, Tailwind, and Chart.js.

#### Open Questions for Phase 2:
- Does the compliance web approval action trigger a webhook notification back to the merchant on WhatsApp/Telegram immediately upon approval? (Default: Yes, via `send_reply`).
- Should merchant-facing web access (user portal) share the admin auth system or use magic-link OTP via WhatsApp? (Default: Magic-link OTP).
