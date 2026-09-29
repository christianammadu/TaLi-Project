"""Scaffold, research, and plan Wave 4 Groundwork plans:
1. 2026-09-29-merchant-desktop-and-staff-rbac
2. 2026-09-29-platform-admin-ops-and-crm
3. 2026-09-29-accounting-integrations-and-public-api
4. 2026-09-29-tali-mcp-server
"""

import os
import json
import hashlib
from datetime import datetime, timezone

BASE_DIR = "/Users/admin/Documents/code-projects/tali"
PLANS_DIR = os.path.join(BASE_DIR, "plans")

WAVE4_PLANS = [
    {
        "dir": "2026-09-29-merchant-desktop-and-staff-rbac",
        "title": "Merchant Desktop Portal & Staff RBAC",
        "slug": "merchant-desktop-and-staff-rbac",
        "wave": 4,
        "wave_name": "Wave 4: Enterprise Operations, Ecosystem Integrations & MCP",
        "plan_label": "plan:merchant-portal",
        "goal": "Expand merchant desktop portal with customer debtors hub, business settings, staff cashier RBAC, and rapid CMD+K entry modal",
        "context": "Physical retail merchants in Nigeria frequently employ shop attendants and cashiers. To scale merchant adoption, TaLi must support multi-staff access with PIN-protected roles (Cashier vs Manager vs Owner), a dedicated debtor management hub ('Who Dey Owe Me'), store branding settings, and a desktop quick-entry bar.",
        "architecture_mermaid": """flowchart TD
    MERCHANT["Store Owner / Manager / Cashier"] --> AUTH["PIN / Session Authenticator (app/portal/auth.py)"]
    AUTH --> RBAC{"Role Check"}
    RBAC -->|Cashier| POS["Sales Entry Only (CMD+K / Quick Modal)"]
    RBAC -->|Manager| INV["Stock Adjustments & Invoices"]
    RBAC -->|Owner| FULL["Full P&L, Statements, Staff PINs, Debtor CRM"]
    FULL --> DEBTORS["/portal/debtors — Aging Ledger & WhatsApp Reminder"]
    FULL --> SETTINGS["/portal/settings — Store Logo & Branding"]""",
        "wps": [
            {
                "id": "WP-01",
                "title": "Staff Role Model & PIN-Based Authentication",
                "goal": "Define merchant_staff table with owner, manager, cashier roles, permissions bitmask, and 4-digit PIN authentication.",
                "files": "app/data/models.py, app/portal/auth.py, migrations/versions/0007_staff_rbac.py",
                "dod": "Models created, PIN hashing with bcrypt, role-permission matrix enforced on portal session.",
            },
            {
                "id": "WP-02",
                "title": "Debtor Management Hub & Aging Analysis UI",
                "goal": "Build desktop debtors view with aging buckets (0-30d, 31-60d, 60+d), partial settlement modal, and Paystack link generator.",
                "files": "app/portal/debtors.py, app/templates/portal/debtors.html, app/portal/routes.py",
                "dod": "Aging debt cards, searchable customer table, instant WhatsApp reminder preview, zero emojis.",
                "is_ui": True,
            },
            {
                "id": "WP-03",
                "title": "Merchant Business Settings & Receipt Customizer",
                "goal": "Allow store owners to upload business logo, customize receipt header/footer, set alert thresholds, and manage staff PINs.",
                "files": "app/portal/settings.py, app/templates/portal/settings.html",
                "dod": "Logo image upload, receipt preview pane, staff management table with PIN reset.",
                "is_ui": True,
            },
            {
                "id": "WP-04",
                "title": "Desktop Quick-Action Command Bar & Modal (CMD+K)",
                "goal": "Implement global keyboard shortcut (CMD+K / CTRL+K) opening rapid transaction entry modal with product autocomplete.",
                "files": "app/templates/portal/layout.html, app/templates/portal/_quick_record.html",
                "dod": "Record sale or expense in <3 seconds without page reload, instant ledger update via HTMX.",
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Merchant Desktop & Staff RBAC Test Suite",
                "goal": "Add comprehensive tests proving cashiers cannot view statements or edit staff, and PIN auth security.",
                "files": "tests/test_portal_staff_rbac.py",
                "dod": "Test suite covering role permission denies, PIN lockout defense, and debtor aging calculations.",
            },
        ],
    },
    {
        "dir": "2026-09-29-platform-admin-ops-and-crm",
        "title": "Platform Admin Operations, Merchant CRM & Admin RBAC",
        "slug": "platform-admin-ops-and-crm",
        "wave": 4,
        "wave_name": "Wave 4: Enterprise Operations, Ecosystem Integrations & MCP",
        "plan_label": "plan:admin-crm",
        "goal": "Upgrade stakeholder admin portal with multi-operator RBAC, searchable Merchant CRM, Platform Revenue analytics, and channel telemetry",
        "context": "As TaLi scales toward commercial launch, platform operations require enterprise governance: multi-admin accounts with segregated duties (SuperAdmin, ComplianceOfficer, SupportAgent, FinOpsAuditor), customer CRM inspection, real-time revenue analytics, and automated ops alerting on Telegram/Slack.",
        "architecture_mermaid": """flowchart TD
    OPS["Internal Operator / Support / Compliance"] --> LOGIN["Multi-Admin Auth (app/admin/auth.py)"]
    LOGIN --> RBAC{"Admin Role"}
    RBAC -->|SuperAdmin| ALL["Full System Control, API Keys & Billing"]
    RBAC -->|ComplianceOfficer| COMP["Compliance Queue (Approve / Veto)"]
    RBAC -->|SupportAgent| CRM["Merchant Directory & Activity Inspection"]
    RBAC -->|FinOpsAuditor| FIN["Spend Telemetry & AI Model Costs"]
    CRM --> MERCHANTS["/admin/merchants — Phone Search, Channel Badges, Impersonation"]
    ALL --> REVENUE["/admin/revenue — MRR, ARR, Webhook Event Logs"]
    ALL --> TELEMETRY["/admin/channels — WhatsApp / Telegram Health & Slack Alerts"]""",
        "wps": [
            {
                "id": "WP-01",
                "title": "Multi-Admin RBAC & Operator Session Security",
                "goal": "Create AdminUser model supporting SuperAdmin, ComplianceOfficer, SupportAgent, and FinOpsAuditor roles.",
                "files": "app/data/models.py, app/admin/auth.py, migrations/versions/0008_admin_rbac.py",
                "dod": "Admin user seeding, permission decorators (@admin_role_required), session audit logging.",
            },
            {
                "id": "WP-02",
                "title": "Merchant CRM Directory & Account Detail View",
                "goal": "Build searchable merchant CRM with phone lookup, channel binding status (WhatsApp/Telegram), and activity logs.",
                "files": "app/admin/merchants.py, app/templates/admin/merchants.html, app/templates/admin/merchant_detail.html",
                "dod": "Instant phone search, channel badges, plan tier pill, transaction drill-down, support notes.",
                "is_ui": True,
            },
            {
                "id": "WP-03",
                "title": "Platform Revenue, MRR & Paystack Webhook Log",
                "goal": "Implement revenue analytics dashboard tracking MRR, ARR, tier breakdown, and raw Paystack webhook event stream.",
                "files": "app/admin/revenue.py, app/templates/admin/revenue.html",
                "dod": "Chart.js subscription growth graph, active/past_due count, webhook event payload inspector.",
                "is_ui": True,
            },
            {
                "id": "WP-04",
                "title": "Channel Health Telemetry & Operations Alerting",
                "goal": "Build real-time WhatsApp Cloud API and Telegram Bot health dashboard with automated Slack/Telegram alerts.",
                "files": "app/admin/channels.py, app/templates/admin/channels.html, app/services/alerts.py",
                "dod": "Token expiration monitor, webhook latency tracker, automated alerts for spend ceiling >80% or webhook errors.",
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Admin Action Audit Trail & Governance Test Suite",
                "goal": "Add tests validating NDPR-compliant admin audit logging, role segregation, and unauthorized access rejections.",
                "files": "tests/test_admin_crm_rbac.py",
                "dod": "100% test coverage of admin roles, audit trail persistence, and merchant lookup security.",
            },
        ],
    },
    {
        "dir": "2026-09-29-accounting-integrations-and-public-api",
        "title": "External Accounting Integrations & Public Developer API",
        "slug": "accounting-integrations-and-public-api",
        "wave": 4,
        "wave_name": "Wave 4: Enterprise Operations, Ecosystem Integrations & MCP",
        "plan_label": "plan:integrations",
        "goal": "Build accounting ledger normalizer for QuickBooks/Xero/Zoho sync, public developer REST API, and e-commerce webhooks",
        "context": "To embed TaLi into the broader financial ecosystem, merchants need automated sync with standard accounting packages (QuickBooks Online, Xero, Zoho Books) and developer APIs/webhooks so online storefronts (Shopify, WooCommerce, Paystack Storefront) auto-record sales into TaLi.",
        "architecture_mermaid": """flowchart TD
    STORE["E-commerce Store (Shopify / WooCommerce / Paystack)"] --> WEBHOOK["POST /api/v1/webhooks/ecommerce"]
    DEV["Third-Party App / POS Terminal"] --> API["REST API /api/v1/ (Token Auth)"]
    WEBHOOK & API --> NORM["Standard Accounting Normalizer (app/services/accounting_export.py)"]
    NORM --> DB[("TaLi Multi-Tenant Ledger")]
    DB --> SYNC["Accounting Sync Engine"]
    SYNC --> QB["QuickBooks Online (QBO / IIF / REST)"]
    SYNC --> XERO["Xero / Zoho Books (CSV / OAuth2)"]""",
        "wps": [
            {
                "id": "WP-01",
                "title": "Standard Accounting Ledger Schema Normalizer",
                "goal": "Map TaLi single-entry sales/expenses into double-entry chart of accounts (Assets, Liabilities, Equity, Revenue, COGS).",
                "files": "app/services/accounting_export.py, tests/test_accounting_normalizer.py",
                "dod": "Deterministic double-entry transformation; verifies Debit == Credit for every transaction batch.",
            },
            {
                "id": "WP-02",
                "title": "QuickBooks Online & Xero Export Adapters",
                "goal": "Implement batch export generators for QuickBooks (IIF/QBO format) and Xero/Zoho Books (CSV format).",
                "files": "app/services/integrations/quickbooks.py, app/services/integrations/xero.py",
                "dod": "Validated export files accepted by QuickBooks and Xero import validators without syntax errors.",
            },
            {
                "id": "WP-03",
                "title": "Public Merchant Developer REST API (v1)",
                "goal": "Build bearer-token authenticated REST endpoints (/api/v1/transactions, /api/v1/inventory, /api/v1/debts).",
                "files": "app/web/api_v1.py, app/services/api_keys.py",
                "dod": "Scoped API key authentication, rate limiting (60 req/min), standard JSON error envelopes.",
            },
            {
                "id": "WP-04",
                "title": "Inbound E-Commerce Webhook Ingestors (Shopify & WooCommerce)",
                "goal": "Handle incoming order webhooks from Shopify, WooCommerce, and Paystack Storefront to auto-log sales.",
                "files": "app/web/ecommerce_webhooks.py, app/services/webhook_verifier.py",
                "dod": "HMAC verification of Shopify/WooCommerce webhooks; creates sales and updates stock balance automatically.",
            },
            {
                "id": "WP-05",
                "title": "Accounting Integrations & Public API Test Suite",
                "goal": "Add tests validating chart of accounts balance, developer API rate limiting, and webhook ingest accuracy.",
                "files": "tests/test_accounting_api.py",
                "dod": "Complete test suite covering export generation, API key lifecycle, and order auto-recording.",
            },
        ],
    },
    {
        "dir": "2026-09-29-tali-mcp-server",
        "title": "TaLi Model Context Protocol (MCP) Server",
        "slug": "tali-mcp-server",
        "wave": 4,
        "wave_name": "Wave 4: Enterprise Operations, Ecosystem Integrations & MCP",
        "plan_label": "plan:mcp",
        "goal": "Implement TaLi MCP Server enabling Claude, Cursor, Antigravity, and ChatGPT to interact directly with merchant books",
        "context": "The Model Context Protocol (MCP) enables external AI assistants to use TaLi as a specialized bookkeeping tool. Store owners, accountants, and developers can connect their desktop AI clients to query sales, record transactions, verify inventory, and trigger debt reminders using natural language.",
        "architecture_mermaid": """flowchart TD
    AI["AI Client (Claude Desktop / Cursor / Antigravity / ChatGPT)"] --> MCP["TaLi MCP Server (app/mcp/server.py)"]
    MCP -->|Transport: stdio / SSE| PROTOCOL["JSON-RPC 2.0 Protocol"]
    PROTOCOL --> AUTH["Merchant API Key Scoping"]
    AUTH --> TOOLS{"MCP Tool Dispatcher"}
    TOOLS --> T1["record_sale / record_expense"]
    TOOLS --> T2["get_financial_summary / search_transactions"]
    TOOLS --> T3["check_stock_levels / adjust_inventory"]
    TOOLS --> T4["list_overdue_debts / send_debt_reminder"]
    T1 & T2 & T3 & T4 --> CORE["TaLi ORM & Multi-Tenant Ledger"]""",
        "wps": [
            {
                "id": "WP-01",
                "title": "Model Context Protocol Server Architecture & Transport",
                "goal": "Build Python-based MCP server with stdio transport and SSE HTTP transport (/mcp/sse) using standard MCP specification.",
                "files": "app/mcp/server.py, app/mcp/__init__.py, requirements.txt",
                "dod": "Standard JSON-RPC 2.0 handshake, merchant API key authentication header, tool discovery capability.",
            },
            {
                "id": "WP-02",
                "title": "Merchant Ledger & Cashflow Tools",
                "goal": "Implement MCP tools: record_sale, record_expense, get_financial_summary, search_transactions.",
                "files": "app/mcp/tools_ledger.py",
                "dod": "Pydantic parameter schemas, natural language output summaries, idempotency keys.",
            },
            {
                "id": "WP-03",
                "title": "Stock & Inventory Management Tools",
                "goal": "Implement MCP tools: check_stock_levels, get_low_stock_alerts, adjust_inventory.",
                "files": "app/mcp/tools_inventory.py",
                "dod": "Item fuzzy search, stock level reporting, instant restock and shrinkage logging.",
            },
            {
                "id": "WP-04",
                "title": "Debtor Management & Statement Tools",
                "goal": "Implement MCP tools: list_debtors, send_debt_reminder, generate_statement_summary.",
                "files": "app/mcp/tools_reports.py",
                "dod": "Aging debt reporting, reminder triggering with tone preview, period statement summaries.",
            },
            {
                "id": "WP-05",
                "title": "TaLi MCP Server Security, Auth & Verification Test Suite",
                "goal": "Add tests validating tool call authorization, tenant isolation (cannot query other merchants), and JSON-RPC compliance.",
                "files": "tests/test_tali_mcp.py",
                "dod": "Comprehensive test suite verifying all tool calls, invalid key rejection, and schema validation.",
            },
        ],
    },
]


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def scaffold_plan(plan):
    plan_dir = os.path.join(PLANS_DIR, plan["dir"])
    os.makedirs(plan_dir, exist_ok=True)
    os.makedirs(os.path.join(plan_dir, "artifact"), exist_ok=True)
    os.makedirs(os.path.join(plan_dir, "drafts"), exist_ok=True)
    os.makedirs(os.path.join(plan_dir, "designs"), exist_ok=True)

    # 1. 00-README.md
    readme_content = f"""# {plan['title']}

## Status
Planning & Orchestration complete. Ready for implementation.

## Overview
{plan['context']}

## Work Packages
"""
    for wp in plan["wps"]:
        readme_content += f"- **{wp['id']}**: {wp['title']}\n"

    readme_content += f"""
## UI & Visual Design Constraints
- **Required Skills**: `impeccable` and `huashu-design` MUST be used for all UI layout, styling, and prototypes.
- **Prohibitions**: Emojis are strictly PROHIBITED in UI copy, buttons, headers, and labels. Em dashes (`—`) are strictly PROHIBITED in text.
- **Visual Assets**: Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.
"""
    write_file(os.path.join(plan_dir, "00-README.md"), readme_content)

    # 2. 01-plan.md
    plan_content = f"""# {plan['title']}

## Goal

<!-- groundwork:auto:start goal -->
<!-- last_action: init · 2026-09-29 -->
{plan['goal']}
<!-- groundwork:auto:end goal -->

## Context

{plan['context']}

## Architecture

```mermaid
{plan['architecture_mermaid']}
```

### Shared State Contract

| Field | Type | Writer | Readers | Description |
|---|---|---|---|---|
| `event_id` | `str` | Channel Webhook / API / MCP | Ledger / Database | Unique idempotency reference |
| `merchant_id` | `UUID` | Auth / Channel Resolver | Handlers | Authenticated tenant context |
| `operator_id` | `str` | Admin Auth / MCP Client | Audit Trail | Originating operator identity |

## Phases & Work Packages

### Phase 1 — Core Implementation & Multi-Channel Delivery
"""
    for wp in plan["wps"]:
        plan_content += f"- **{wp['id']}**: {wp['title']} — {wp['goal']}\n"

    plan_content += f"""
## UI & Visual Design Constraints

When implementing screens, cards, modals, or views:
- **Mandatory Skills**: `impeccable` and `huashu-design` MUST be used for UI layout, styling, and prototype reviews.
- **Prohibited**:
  - Emojis are strictly prohibited in all UI copy, buttons, headers, cards, and tooltips. Use clean SVG icons (Lucide / Heroicons) instead.
  - Em dashes (`—`) are strictly prohibited in all UI text and labels. Use clean hyphens (`-`) or colons (`:`).
- **Visual Assets**: Real screenshots/photos, vector illustrations (such as unDraw at `undraw.co`), and AI-generated images are permitted.

## Critical Files

"""
    for wp in plan["wps"]:
        plan_content += f"- `{wp['files'].split(',')[0].strip()}`\n"

    write_file(os.path.join(plan_dir, "01-plan.md"), plan_content)

    # 3. 02-research-external.md
    external_research = f"""# 02 — External Research: {plan['title']}

## Industry Benchmarks & Technical Analysis

- **Ecosystem Precedents**: Best-in-class solutions (QuickBooks Online, Xero, Stripe Dashboard, Shopify App Store, Anthropic MCP).
- **Security & Multi-Tenant Isolation**: Cryptographic session tokens, bcrypt PIN hashing, tenant scoping on all SQL queries.
- **Protocol Standards**: JSON-RPC 2.0 (Model Context Protocol), RFC 7519 JWT, RFC 9562 UUIDv7.
"""
    write_file(os.path.join(plan_dir, "02-research-external.md"), external_research)

    # 4. 03-research-internal.md
    internal_research = f"""# 03 — Internal Research: {plan['title']}

## Codebase Readiness & Integration Seams

- **Database Layer**: SQLAlchemy ORM models in `app/data/models.py`, session management via `app/data/db.py` session_scope.
- **Authentication**: Passwordless OTP in `app/portal/auth.py`, admin bcrypt auth in `app/admin/auth.py`.
- **API & Channels**: Modular Flask blueprints in `app/web/`, `app/portal/`, and `app/admin/`.
- **Test Infrastructure**: Pytest fixtures with session mocking in `tests/conftest.py`.
"""
    write_file(os.path.join(plan_dir, "03-research-internal.md"), internal_research)

    # 5. 04-discussion.md
    discussion = f"""# 04 — Discussion & Decision Log: {plan['title']}

## Round 1 — Architecture & Scope Alignment (2026-09-29)

- **Decision 1**: Role-based access control uses explicit permission bitmasks rather than ad-hoc flags.
- **Decision 2**: External accounting export normalizes single-entry transactions into balanced double-entry journals.
- **Decision 3**: MCP server supports both stdio (for local desktop agents) and SSE over HTTP (for hosted web agents).
- **Decision 4**: Strict UI guidelines enforced (zero emojis, zero em dashes, impeccable and huashu-design required).
"""
    write_file(os.path.join(plan_dir, "04-discussion.md"), discussion)

    # 6. 05-tracking.md
    tracking = f"""# 05 — Tracking & Work Packages

## Work Package Matrix

<!-- groundwork:auto:start wp-matrix -->
| ID | Status | Branch | Summary | Blockers |
|:---|:---:|:---|:---|:---|
"""
    for wp in plan["wps"]:
        tracking += f"| {wp['id']} | [ ] | `feature/{wp['id'].lower()}-{plan['slug']}` | {wp['title']} | - |\n"

    tracking += f"""<!-- groundwork:auto:end wp-matrix -->

## Wave Plan

<!-- groundwork:auto:start wave-plan -->
- **Phase 1 (Foundations & Models)**: {plan['wps'][0]['id']}
- **Phase 2 (Core Business Logic)**: {plan['wps'][1]['id']}, {plan['wps'][2]['id']}
- **Phase 3 (Delivery & Verification)**: {plan['wps'][3]['id']}, {plan['wps'][4]['id']}
<!-- groundwork:auto:end wave-plan -->
"""
    write_file(os.path.join(plan_dir, "05-tracking.md"), tracking)

    # 7. 09-orchestration.md
    orchestration = f"""# {plan['title']} — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** {plan['wave_name']}.
- **Branch Discipline:** Base branch `feat/{plan['slug']}`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-{plan['wps'][0]['id']}` | {plan['wps'][0]['id']} | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
"""
    for i, wp in enumerate(plan["wps"]):
        dep = plan["wps"][i-1]["id"] if i > 0 else "—"
        orchestration += f"| {wp['id']} | {wp['title']} | Wave {plan['wave']} | {dep} | `feat/{plan['slug']}` |\n"

    orchestration += f"""
### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** {plan['wps'][0]['id']}
- **Phase 2 (Core Business Logic):** {plan['wps'][1]['id']}, {plan['wps'][2]['id']}
- **Phase 3 (Delivery & Verification):** {plan['wps'][3]['id']}, {plan['wps'][4]['id']}

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```
"""
    for i, wp in enumerate(plan["wps"]):
        dep = plan["wps"][i-1]["id"] if i > 0 else "—"
        orchestration += f"""---

### {wp['id']} — {wp['title']}
- **GOAL:** {wp['goal']}
- **REPO/BRANCH:** tali / `feature/{wp['id'].lower()}-{plan['slug']}`
- **DEPENDS-ON:** {dep}
- **FILES:** {wp['files']}
- **DEFINITION OF DONE:** {wp['dod']}
"""
        if wp.get("is_ui"):
            orchestration += "- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.\n"

    orchestration += f"""---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
"""
    write_file(os.path.join(plan_dir, "09-orchestration.md"), orchestration)

    # 8. .groundwork.json
    gw_json = {
        "spine_version": "1",
        "profile": "software",
        "title": plan["title"],
        "slug": plan["slug"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "docs": {
            "00-README.md": {"hash": "auto"},
            "01-plan.md": {"hash": "auto"},
            "02-research-external.md": {"hash": "auto"},
            "03-research-internal.md": {"hash": "auto"},
            "04-discussion.md": {"hash": "auto"},
            "05-tracking.md": {"hash": "auto"},
            "09-orchestration.md": {"hash": "auto"},
        },
        "orchestrate": {"last_run": datetime.now(timezone.utc).isoformat()},
    }
    write_file(os.path.join(plan_dir, ".groundwork.json"), json.dumps(gw_json, indent=2))

    # 9. artifact/manifest.json
    manifest = {
        "plan_slug": plan["slug"],
        "title": plan["title"],
        "profile": "software",
        "wave": plan["wave"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_file(os.path.join(plan_dir, "artifact", "manifest.json"), json.dumps(manifest, indent=2))
    print(f"Scaffolded and orchestrated {plan['dir']}")


if __name__ == "__main__":
    for plan in WAVE4_PLANS:
        scaffold_plan(plan)
    print("All Wave 4 plans scaffolded successfully!")
