# Merchant Credit Passport & Audit Dossier — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 3: Multimodal Intelligence & Growth.
- **Branch Discipline:** Base branch `feat/merchant-credit-passport`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Credit Health Scoring & Metrics Aggregator | Wave 3 | — | `feat/merchant-credit-passport` |
| WP-02 | 3-Page Certified Dossier PDF Template | Wave 3 | WP-01 | `feat/merchant-credit-passport` |
| WP-03 | Tamper-Proof Verification Token & QR Code Generator | Wave 3 | WP-02 | `feat/merchant-credit-passport` |
| WP-04 | Public Digital Verification Route & UI | Wave 3 | WP-03 | `feat/merchant-credit-passport` |
| WP-05 | Credit Passport Export & Verification Test Suite | Wave 3 | WP-04 | `feat/merchant-credit-passport` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Credit Health Scoring & Metrics Aggregator
- **GOAL:** Build proprietary 0-100 credit health scoring based on revenue consistency, operating profit, and cash reserves.
- **REPO/BRANCH:** tali / `feature/wp-01-credit-health-scoring-&-m`
- **DEPENDS-ON:** —
- **FILES:** app/services/credit_score.py, tests/test_credit_score.py
- **DEFINITION OF DONE:** Deterministic algorithm evaluating 6 core financial indicators; generates health grade (A, B, C, D).

---

### WP-02 — 3-Page Certified Dossier PDF Template
- **GOAL:** Design and render bank-grade, audit-ready financial statement PDF with revenue charts and integrity seals.
- **REPO/BRANCH:** tali / `feature/wp-02-3-page-certified-dossier-`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/report_renderer.py, tests/test_passport_pdf.py
- **DEFINITION OF DONE:** ReportLab rendered 3-page document with monthly cash flow breakdown and formal verification footer.

---

### WP-03 — Tamper-Proof Verification Token & QR Code Generator
- **GOAL:** Mint cryptographic verification tokens (HMAC-SHA256) and embed QR codes linking to public verification page.
- **REPO/BRANCH:** tali / `feature/wp-03-tamper-proof-verification`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/passport_security.py, app/data/models.py
- **DEFINITION OF DONE:** QR code scanned by loan officer resolves to authenticated, tamper-evident verification route.

---

### WP-04 — Public Digital Verification Route & UI
- **GOAL:** Build /verify/passport/<token> web endpoint displaying audited business overview and certification status.
- **REPO/BRANCH:** tali / `feature/wp-04-public-digital-verificati`
- **DEPENDS-ON:** WP-03
- **FILES:** app/web/passport_routes.py, app/templates/passport_verify.html
- **DEFINITION OF DONE:** Public verification screen for banks/fintechs. Strict zero emoji and zero em dash compliance.
- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.

---

### WP-05 — Credit Passport Export & Verification Test Suite
- **GOAL:** Add tests validating scoring calculations, PDF generation, QR validity, and verification route access.
- **REPO/BRANCH:** tali / `feature/wp-05-credit-passport-export-&-`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_credit_passport.py
- **DEFINITION OF DONE:** Complete test suite validating bank-grade integrity and token expiration.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
