# POS & Paper Receipt Vision Scanner — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 3: Multimodal Intelligence & Growth.
- **Branch Discipline:** Base branch `feat/pos-and-receipt-vision-scanner`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Inbound Image Normalization & Preprocessing Pipeline | Wave 3 | — | `feat/pos-and-receipt-vision-scanner` |
| WP-02 | GPT-4o-Vision OCR Structured Schema Extractor | Wave 3 | WP-01 | `feat/pos-and-receipt-vision-scanner` |
| WP-03 | Multi-Provider POS Slip Parser (Moniepoint, OPay, PalmPay) | Wave 3 | WP-02 | `feat/pos-and-receipt-vision-scanner` |
| WP-04 | Image Confidence Scoring & Clarification Fallback Flow | Wave 3 | WP-03 | `feat/pos-and-receipt-vision-scanner` |
| WP-05 | Vision Extraction Test Suite & Synthetic Slips Fixture | Wave 3 | WP-04 | `feat/pos-and-receipt-vision-scanner` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Inbound Image Normalization & Preprocessing Pipeline
- **GOAL:** Handle inbound photos of POS terminal slips and receipts, apply contrast enhancement and orientation correction.
- **REPO/BRANCH:** tali / `feature/wp-01-inbound-image-normalizati`
- **DEPENDS-ON:** —
- **FILES:** app/services/vision_service.py, app/channels/base.py
- **DEFINITION OF DONE:** Image resizing, compression, and EXIF orientation auto-rotation for optimal LLM vision parsing.

---

### WP-02 — GPT-4o-Vision OCR Structured Schema Extractor
- **GOAL:** Use GPT-4o-vision with Pydantic structured output to extract merchant, amount, date, reference, and line items.
- **REPO/BRANCH:** tali / `feature/wp-02-gpt-4o-vision-ocr-structu`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/vision_service.py, app/agents/event_schemas.py
- **DEFINITION OF DONE:** Structured JSON output matching TransactionEvent schema; confidence score per field.

---

### WP-03 — Multi-Provider POS Slip Parser (Moniepoint, OPay, PalmPay)
- **GOAL:** Fine-tune prompts and regex anchors for top Nigerian POS terminal slips (OPay, Moniepoint, PalmPay, Baxi).
- **REPO/BRANCH:** tali / `feature/wp-03-multi-provider-pos-slip-p`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/vision_service.py, tests/test_vision_service.py
- **DEFINITION OF DONE:** High precision extraction of Stanbic/OPay/Moniepoint transaction reference and final amount.

---

### WP-04 — Image Confidence Scoring & Clarification Fallback Flow
- **GOAL:** If image is blurry or amount is ambiguous, prompt merchant with quick yes/no button confirmation.
- **REPO/BRANCH:** tali / `feature/wp-04-image-confidence-scoring-`
- **DEPENDS-ON:** WP-03
- **FILES:** app/agents/agent_1_intake.py, app/channels/base.py
- **DEFINITION OF DONE:** Safe fallback: asks 'I saw ₦4,500 for OPay transfer. Is this correct?' before committing.

---

### WP-05 — Vision Extraction Test Suite & Synthetic Slips Fixture
- **GOAL:** Add comprehensive test suite with fixtures of clean, crumpled, and low-light receipt images.
- **REPO/BRANCH:** tali / `feature/wp-05-vision-extraction-test-su`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_pos_vision.py
- **DEFINITION OF DONE:** Unit tests ensuring zero hallucinations on missing fields and accurate transaction posting.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
