# TaLi Model Context Protocol (MCP) Server — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 4: Enterprise Operations, Ecosystem Integrations & MCP.
- **Branch Discipline:** Base branch `feat/tali-mcp-server`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Model Context Protocol Server Architecture & Transport | Wave 4 | — | `feat/tali-mcp-server` |
| WP-02 | Merchant Ledger & Cashflow Tools | Wave 4 | WP-01 | `feat/tali-mcp-server` |
| WP-03 | Stock & Inventory Management Tools | Wave 4 | WP-02 | `feat/tali-mcp-server` |
| WP-04 | Debtor Management & Statement Tools | Wave 4 | WP-03 | `feat/tali-mcp-server` |
| WP-05 | TaLi MCP Server Security, Auth & Verification Test Suite | Wave 4 | WP-04 | `feat/tali-mcp-server` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```
---

### WP-01 — Model Context Protocol Server Architecture & Transport
- **GOAL:** Build Python-based MCP server with stdio transport and SSE HTTP transport (/mcp/sse) using standard MCP specification.
- **REPO/BRANCH:** tali / `feature/wp-01-tali-mcp-server`
- **DEPENDS-ON:** —
- **FILES:** app/mcp/server.py, app/mcp/__init__.py, requirements.txt
- **DEFINITION OF DONE:** Standard JSON-RPC 2.0 handshake, merchant API key authentication header, tool discovery capability.
---

### WP-02 — Merchant Ledger & Cashflow Tools
- **GOAL:** Implement MCP tools: record_sale, record_expense, get_financial_summary, search_transactions.
- **REPO/BRANCH:** tali / `feature/wp-02-tali-mcp-server`
- **DEPENDS-ON:** WP-01
- **FILES:** app/mcp/tools_ledger.py
- **DEFINITION OF DONE:** Pydantic parameter schemas, natural language output summaries, idempotency keys.
---

### WP-03 — Stock & Inventory Management Tools
- **GOAL:** Implement MCP tools: check_stock_levels, get_low_stock_alerts, adjust_inventory.
- **REPO/BRANCH:** tali / `feature/wp-03-tali-mcp-server`
- **DEPENDS-ON:** WP-02
- **FILES:** app/mcp/tools_inventory.py
- **DEFINITION OF DONE:** Item fuzzy search, stock level reporting, instant restock and shrinkage logging.
---

### WP-04 — Debtor Management & Statement Tools
- **GOAL:** Implement MCP tools: list_debtors, send_debt_reminder, generate_statement_summary.
- **REPO/BRANCH:** tali / `feature/wp-04-tali-mcp-server`
- **DEPENDS-ON:** WP-03
- **FILES:** app/mcp/tools_reports.py
- **DEFINITION OF DONE:** Aging debt reporting, reminder triggering with tone preview, period statement summaries.
---

### WP-05 — TaLi MCP Server Security, Auth & Verification Test Suite
- **GOAL:** Add tests validating tool call authorization, tenant isolation (cannot query other merchants), and JSON-RPC compliance.
- **REPO/BRANCH:** tali / `feature/wp-05-tali-mcp-server`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_tali_mcp.py
- **DEFINITION OF DONE:** Comprehensive test suite verifying all tool calls, invalid key rejection, and schema validation.
---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
