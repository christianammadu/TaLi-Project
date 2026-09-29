# Marketing Site Expansion & Trust Center — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 1: Launch Foundations & Monetization.
- **Branch Discipline:** Base branch `feat/marketing-site-expansion`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | NDPR-Compliant Privacy Policy & Terms of Service | Wave 1 | — | `feat/marketing-site-expansion` |
| WP-02 | Interactive Categorized FAQ Page | Wave 1 | WP-01 | `feat/marketing-site-expansion` |
| WP-03 | Help Center & Knowledge Base Hub | Wave 1 | WP-02 | `feat/marketing-site-expansion` |
| WP-04 | Public Product Changelog & Release Notes Feed | Wave 1 | WP-03 | `feat/marketing-site-expansion` |
| WP-05 | Marketing Navigation, SEO & Metadata Polish | Wave 1 | WP-04 | `feat/marketing-site-expansion` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — NDPR-Compliant Privacy Policy & Terms of Service
- **GOAL:** Author and deploy legally sound Privacy Policy and Terms of Service web pages compliant with NDPR.
- **REPO/BRANCH:** tali / `feature/wp-01-ndpr-compliant-privacy-po`
- **DEPENDS-ON:** —
- **FILES:** app/web/web_routes.py, app/templates/legal/privacy.html, app/templates/legal/terms.html
- **DEFINITION OF DONE:** Compliant legal terms covering data processing, WhatsApp/Telegram messaging consent, and Paystack payments.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-02 — Interactive Categorized FAQ Page
- **GOAL:** Create searchable, accordion-based FAQ page addressing security, pricing, and messaging channel commands.
- **REPO/BRANCH:** tali / `feature/wp-02-interactive-categorized-f`
- **DEPENDS-ON:** WP-01
- **FILES:** app/templates/faq.html, app/web/web_routes.py
- **DEFINITION OF DONE:** Category tabs, instant search filtering, clear bookkeeping command examples.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-03 — Help Center & Knowledge Base Hub
- **GOAL:** Build structured guides page with step-by-step visual tutorials for onboarding and core bookkeeping actions.
- **REPO/BRANCH:** tali / `feature/wp-03-help-center-&-knowledge-b`
- **DEPENDS-ON:** WP-02
- **FILES:** app/templates/help/index.html, app/templates/help/article.html
- **DEFINITION OF DONE:** Step-by-step walkthroughs with vector illustrations (unDraw) and screenshot mockups.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-04 — Public Product Changelog & Release Notes Feed
- **GOAL:** Implement dynamic changelog template showcasing weekly feature releases, improvements, and fixes.
- **REPO/BRANCH:** tali / `feature/wp-04-public-product-changelog-`
- **DEPENDS-ON:** WP-03
- **FILES:** app/templates/changelog.html, app/web/web_routes.py
- **DEFINITION OF DONE:** Timeline layout with version tags, release dates, and category pills (New, Improved, Fixed).
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-05 — Marketing Navigation, SEO & Metadata Polish
- **GOAL:** Update global headers/footers with legal links, OpenGraph social preview cards, and mobile navigation.
- **REPO/BRANCH:** tali / `feature/wp-05-marketing-navigation,-seo`
- **DEPENDS-ON:** WP-04
- **FILES:** app/templates/layout.html, app/templates/index.html
- **DEFINITION OF DONE:** Social preview cards, SEO meta tags, mobile hamburger menu, accessible footer.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
