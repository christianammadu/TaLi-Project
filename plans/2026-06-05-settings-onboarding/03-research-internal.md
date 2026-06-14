<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 03 — Internal research

Existing assets, prior work, current constraints relevant to Add a settings mechanism plus onboarding that captures display name and usage type (business/personal) so welcomes are personalized and business users can record business info; decide whether settings live on an authenticated web page or via WhatsApp commands.. Cite by `path:line` (or by document title + section for non-file references).

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-05T10:56:03Z -->
## The web layer is intentionally thin — no authenticated area exists

TaLi's web surface is, by design, marketing + a 2-step auth handshake only. `app/web/web_routes.py` serves public pages (`/`, `/features`, `/pricing`, `/privacy`, `/terms`, `/faq`) plus `/register` (phone → OTP), `/verify-otp`, and `/verify` (token → 6-digit code display). There is **no logged-in web session** — the OTP/verify pages are stateless and one-shot (`app/web/web_routes.py:50`, `app/web/web_routes.py:164`). The original design doc explicitly states the intent: *"No dashboard. No web-based reporting. Everything happens in the chat… The Web Layer Does (Minimal — 2 pages only)"* (`docs/auth_system_proposal.md:22`). A settings *web page* would therefore require building a brand-new authenticated web-session layer from scratch — cookies/login, CSRF, the works — which does not exist today.

## `display_name` already exists on the model but is never collected

`User.display_name` is a real column (`String(100)`, nullable) at `app/data/models.py:30`. The login welcome **already tries to use it** — `name = user.get('display_name') or user['phone_number']` (`app/web/routes.py:69`) and `_user_dict` carries it everywhere (`app/auth.py:104`). But nothing ever *writes* it: `register_user()` inserts only `phone_number`, `is_verified`, `alert_thresholds` (`app/auth.py:93`), and the registration form collects only country code + phone (`app/web/web_routes.py:80`). So personalization is half-wired and currently dead — the welcome always falls back to the phone number. **Capturing a name is a small, high-leverage change** against existing plumbing.

## `business_id` is an orphaned hook — there is no `businesses` table

`User.business_id` (and the same column on transactions, debts, inventory, ai_logs) exists but is deliberately inert. The model docstring documents the history: it was added with `DEFAULT 1`, which made every user share bucket 1 — *"a multi-tenant data leak"* — and migration `0002` NULLs it; reads now scope by `user_id` unless a real `business_id` is set (`app/data/models.py:8-12`, `app/data/models.py:35`). **There is no `businesses` table.** So "usage type / business info" has a latent column to hang off, but the backing entity must be built. Any business-profile work should be careful not to re-introduce the shared-bucket bug.

## `alert_thresholds` JSON is the existing precedent for per-user settings

`User.alert_thresholds` is a JSON column already used as a settings bag, defaulted to `{"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000}` in both `register_user()` and the web register path (`app/auth.py:18`, `app/auth.py:93`, `app/web/web_routes.py:109`). There is **also** a `base_currency` column (`String(3)`, default `'NGN'`) at `app/data/models.py:33`. So the user already has two settings surfaces (a typed column for currency, a JSON bag for thresholds) — both are natural settings to expose, and the JSON bag is the obvious home for new free-form preferences without a migration per field.

## WhatsApp command routing is a clean, extensible dispatcher

Inbound messages flow through `app/web/routes.py:webhook()` → command checks. There's a tidy command table: `PUBLIC_COMMANDS = {'login','/login'}`, `AUTH_COMMANDS = {'logout','/logout','help','/help'}` (`app/web/routes.py:25`), each with a `handle_*` function (`handle_login`, `handle_logout`, `handle_help`, `handle_access_code`). Adding a `settings` / `name` / `business` command is a **localized, low-risk edit** in the same pattern. Anything not matching a command and past the session gate falls through to the AI `AgentRouter` (`app/web/routes.py:232`). Note: the bot **only handles text today** — non-text messages are rejected (`app/web/routes.py:166`), and there is no existing use of interactive buttons/lists/Flows, so a button-based settings menu would be net-new send-side plumbing in `app/web/whatsapp.py`.

## Session model gives an in-chat "logged-in" context to attach settings edits to

`get_active_session()` returns a dict already carrying `user_id`, `phone_number`, `display_name`, and `business_id` (`app/auth.py:269`, `app/auth.py:282`). So once a user is authenticated in WhatsApp, the handler has everything needed to read/modify their settings in-chat without any new auth — a strong point in favor of the in-chat settings option. Sessions last `SESSION_DURATION_HOURS` (72h default, `.env.example:25`).

## Onboarding has a natural insertion point at end-of-registration or first-login

Two candidate hooks: (a) **web registration** — after `verify_otp` succeeds (`app/web/web_routes.py:149`), the "done" step could collect name + usage type before sending the user to WhatsApp; or (b) **first login** — `handle_access_code` already branches on first successful login (`app/web/routes.py:63`) and could trigger a short in-chat onboarding if `display_name` is null. Option (b) keeps everything in WhatsApp (consistent with the product thesis); option (a) reuses the existing web form but adds fields to a page the user only sees once.

## Migrations are Alembic-owned; adding fields/tables is a known path

Schema is owned by Alembic (`migrations/versions/`), with `app/data/models.py` as the single source of truth (README §Database). Current migrations include `0001_baseline` and `0002` (the `business_id` NULLing). A new migration for `usage_type` on `users` and/or a `businesses` table is the standard `alembic revision --autogenerate` path — no schema surprises. The legacy `init_db()` DDL still runs at boot for back-compat (`app/data/database.py`) and is being retired, so new schema should go through Alembic, not `init_db()`.
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you went looking for inside the existing system / org / archive and why. The research action does not touch this section.
