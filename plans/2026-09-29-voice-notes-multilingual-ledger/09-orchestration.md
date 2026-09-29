# Multilingual Voice Notes Ledger — Implementation Orchestration

How to drive the build with **one orchestrator agent + per-work-package subagents**.
Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.

> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**

<!-- groundwork:auto:start orchestration -->

## Execution model

- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.
- **Wave Assignment:** Wave 3: Multimodal Intelligence & Growth.
- **Branch Discipline:** Base branch `feat/voice-notes-multilingual-ledger`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.
- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.

## Freeze gates (hard, sequential)

| Gate | Work Package | Why it gates | Sign-off check |
|---|---|---|---|
| `G-WP-01` | WP-01 | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |

## Work-package matrix

| WP | Title | Wave | Depends on | PR target / Output |
|---|---|---|---|---|
| WP-01 | Multi-Channel Audio Inbound Handler & Transcoder | Wave 3 | — | `feat/voice-notes-multilingual-ledger` |
| WP-02 | OpenAI Whisper Transcription Service | Wave 3 | WP-01 | `feat/voice-notes-multilingual-ledger` |
| WP-03 | Local Language & Pidgin Code-Switching Grammar Lexicon | Wave 3 | WP-02 | `feat/voice-notes-multilingual-ledger` |
| WP-04 | Conversational Audio Confirmation & TTS Voice Reply | Wave 3 | WP-03 | `feat/voice-notes-multilingual-ledger` |
| WP-05 | Voice Bookkeeping End-to-End Test Suite | Wave 3 | WP-04 | `feat/voice-notes-multilingual-ledger` |

### Wave plan (orchestrator spawn order)

- **Phase 1 (Foundations & Models):** WP-01
- **Phase 2 (Core Business Logic):** WP-02, WP-03
- **Phase 3 (Delivery & Verification):** WP-04, WP-05

## Subagent brief template

```
GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS
```

---

### WP-01 — Multi-Channel Audio Inbound Handler & Transcoder
- **GOAL:** Download and convert inbound voice notes (WhatsApp OGG Opus / Telegram OGA/MP3) to 16kHz WAV.
- **REPO/BRANCH:** tali / `feature/wp-01-multi-channel-audio-inbou`
- **DEPENDS-ON:** —
- **FILES:** app/services/audio_service.py, app/web/routes.py, app/web/telegram_routes.py
- **DEFINITION OF DONE:** Reliable download from Meta Cloud API and Telegram Bot API; ffmpeg/pydub audio normalization.

---

### WP-02 — OpenAI Whisper Transcription Service
- **GOAL:** Integrate OpenAI Whisper API with Nigerian accent and dialect prompt hints for fast, accurate speech-to-text.
- **REPO/BRANCH:** tali / `feature/wp-02-openai-whisper-transcript`
- **DEPENDS-ON:** WP-01
- **FILES:** app/services/audio_service.py, tests/test_audio_service.py
- **DEFINITION OF DONE:** Transcribes noisy market audio with >90% keyword accuracy; fallback to text if audio unclear.

---

### WP-03 — Local Language & Pidgin Code-Switching Grammar Lexicon
- **GOAL:** Build Nigerian commercial dictionary (k, bag, carton, derica, mudu, ego, kudi, owo) for intent parsing.
- **REPO/BRANCH:** tali / `feature/wp-03-local-language-&-pidgin-c`
- **DEPENDS-ON:** WP-02
- **FILES:** app/services/nlp.py, app/agents/agent_1_intake.py
- **DEFINITION OF DONE:** Accurate extraction of item, quantity, unit, and price from mixed Pidgin/English voice transcripts.

---

### WP-04 — Conversational Audio Confirmation & TTS Voice Reply
- **GOAL:** Reply with both text summary and optional brief audio confirmation for illiterate or busy merchants.
- **REPO/BRANCH:** tali / `feature/wp-04-conversational-audio-conf`
- **DEPENDS-ON:** WP-03
- **FILES:** app/services/audio_service.py, app/channels/base.py
- **DEFINITION OF DONE:** Audio message generated and sent back to WhatsApp/Telegram chat confirming transaction recording.

---

### WP-05 — Voice Bookkeeping End-to-End Test Suite
- **GOAL:** Add end-to-end tests with synthetic audio fixtures covering sales, purchases, and debt logging.
- **REPO/BRANCH:** tali / `feature/wp-05-voice-bookkeeping-end-to-`
- **DEPENDS-ON:** WP-04
- **FILES:** tests/test_voice_bookkeeping.py
- **DEFINITION OF DONE:** Mocked Whisper tests proving flawless flow from voice note to committed database record.

---

## Tracking protocol

- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.
- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.

<!-- groundwork:auto:end orchestration -->
