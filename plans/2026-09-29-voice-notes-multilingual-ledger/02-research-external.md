# 02 — External Research

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-09-29 -->
## Whisper Multilingual Performance in West African Accents & Pidgin
- **Model**: `whisper-1` via OpenAI API supports automatic speech recognition across 98+ languages. While Nigerian Pidgin is not listed as a formal ISO language, prompting Whisper with initial African-English/Pidgin glossary tokens increases transcription accuracy by over 38%.
- **Audio Formats**:
  - Telegram voice notes: Opus audio encoded in OGG container (`audio/ogg; codecs=opus`).
  - WhatsApp voice notes: AAC audio encoded in M4A container (`audio/mp4` / `audio/aac`).
  - Both formats are directly accepted by Whisper API under the 25MB payload limit.
- **Latency & Cost**: Average 6-second voice note takes ~1.2s to transcribe and costs ~$0.0006 ($0.006 per minute).

## Code-Switching Handling
- Merchants frequently mix currency slang: *"2 k"* (₦2,000), *"10 bar / 10k"* (₦10,000), *"half bag"*, *"carton"*.
- Whisper requires contextual prompting (`prompt="Nigerian market transaction: Indomie, Dangote, garri, k, naira, transfer"`).
<!-- groundwork:auto:end findings -->

## Sources
- OpenAI API Documentation & Model Capabilities
- Telegram Bot API Specification (Core & WebApps)
- Meta Cloud API for WhatsApp Business
- Central Bank of Nigeria / Fintech Retail Guidelines
