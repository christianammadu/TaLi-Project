"""Orchestrate Groundwork Plans and Generate GitHub Issues with Wave/Phase/Milestone tagging."""

import os
import json
import subprocess
from datetime import datetime, timezone
import hashlib

BASE_DIR = "/Users/admin/Documents/code-projects/tali"
PLANS_DIR = os.path.join(BASE_DIR, "plans")

# Definition of the 10 Plans and their Work Packages across 3 Waves
PLANS_DATA = [
    # -------------------------------------------------------------
    # WAVE 1: Launch Foundations & Monetization
    # -------------------------------------------------------------
    {
        "dir": "2026-09-29-subscription-and-billing-engine",
        "title": "Subscription & Billing Engine (Paystack Launch Engine)",
        "slug": "subscription-and-billing-engine",
        "wave": 1,
        "wave_name": "Wave 1: Launch Foundations & Monetization",
        "plan_label": "plan:billing",
        "critical_files": ["app/web/billing_routes.py", "app/services/billing.py", "app/data/models.py", "app/portal/routes.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Subscription & Billing Data Models",
                "goal": "Define SubscriptionPlan, MerchantSubscription, and BillingInvoice ORM models with Alembic migration 0006.",
                "files": "app/data/models.py, app/data/database.py, migrations/versions/0006_subscription_billing.py",
                "dod": "Alembic upgrade green, models with proper indices, seed default plans (starter, pro, business).",
                "completed": True,
            },
            {
                "id": "WP-02",
                "title": "Paystack Webhook & Verification Engine",
                "goal": "Implement secure Paystack webhook endpoint with HMAC-SHA512 verification and subscription lifecycle handlers.",
                "files": "app/web/billing_routes.py, app/services/billing.py, tests/test_paystack_webhook.py",
                "dod": "Signature check with constant-time comparison, handles charge.success, subscription.create, invoice.payment_failed (3-day grace period), subscription.disable. 100% test coverage.",
                "completed": True,
            },
            {
                "id": "WP-03",
                "title": "Merchant Portal Billing & Upgrade Hub",
                "goal": "Build merchant self-service billing UI showing active plan, renewal date, usage limits, and Paystack inline checkout modal.",
                "files": "app/portal/routes.py, app/templates/portal/billing.html, app/templates/portal/_plan_card.html",
                "dod": "Visual tier upgrade cards, invoice download history, Paystack inline checkout integration. UI follows impeccable and huashu-design with zero emojis and zero em dashes.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-04",
                "title": "Feature Entitlement & Tier Gating Middleware",
                "goal": "Implement @tier_required and @feature_required route decorators and chat quota enforcement.",
                "files": "app/portal/auth.py, app/services/billing.py, app/channels/base.py",
                "dod": "Gating for voice notes, POS vision, and credit dossier. Friendly upsell message emitted when hitting limit.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Billing Lifecycle & Webhook Test Suite",
                "goal": "Add end-to-end integration tests covering the complete subscription lifecycle, grace period degradation, and renewal.",
                "files": "tests/test_billing_integration.py",
                "dod": "Simulated multi-month renewal, failed charge retries, cancellation, and reactivation.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-marketing-site-expansion",
        "title": "Marketing Site Expansion & Trust Center",
        "slug": "marketing-site-expansion",
        "wave": 1,
        "wave_name": "Wave 1: Launch Foundations & Monetization",
        "plan_label": "plan:marketing",
        "critical_files": ["app/web/web_routes.py", "app/templates/legal/", "app/templates/help/"],
        "wps": [
            {
                "id": "WP-01",
                "title": "NDPR-Compliant Privacy Policy & Terms of Service",
                "goal": "Author and deploy legally sound Privacy Policy and Terms of Service web pages compliant with NDPR.",
                "files": "app/web/web_routes.py, app/templates/legal/privacy.html, app/templates/legal/terms.html",
                "dod": "Compliant legal terms covering data processing, WhatsApp/Telegram messaging consent, and Paystack payments.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-02",
                "title": "Interactive Categorized FAQ Page",
                "goal": "Create searchable, accordion-based FAQ page addressing security, pricing, and messaging channel commands.",
                "files": "app/templates/faq.html, app/web/web_routes.py",
                "dod": "Category tabs, instant search filtering, clear bookkeeping command examples.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-03",
                "title": "Help Center & Knowledge Base Hub",
                "goal": "Build structured guides page with step-by-step visual tutorials for onboarding and core bookkeeping actions.",
                "files": "app/templates/help/index.html, app/templates/help/article.html",
                "dod": "Step-by-step walkthroughs with vector illustrations (unDraw) and screenshot mockups.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-04",
                "title": "Public Product Changelog & Release Notes Feed",
                "goal": "Implement dynamic changelog template showcasing weekly feature releases, improvements, and fixes.",
                "files": "app/templates/changelog.html, app/web/web_routes.py",
                "dod": "Timeline layout with version tags, release dates, and category pills (New, Improved, Fixed).",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Marketing Navigation, SEO & Metadata Polish",
                "goal": "Update global headers/footers with legal links, OpenGraph social preview cards, and mobile navigation.",
                "files": "app/templates/layout.html, app/templates/index.html",
                "dod": "Social preview cards, SEO meta tags, mobile hamburger menu, accessible footer.",
                "completed": False,
                "is_ui": True,
            },
        ],
    },
    {
        "dir": "2026-09-29-telegram-mini-app-portal",
        "title": "Telegram Mini App & Portal Bridge",
        "slug": "telegram-mini-app-portal",
        "wave": 1,
        "wave_name": "Wave 1: Launch Foundations & Monetization",
        "plan_label": "plan:telegram",
        "critical_files": ["app/portal/auth.py", "app/portal/routes.py", "app/templates/portal/layout.html"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Telegram initData HMAC Verification Authenticator",
                "goal": "Implement cryptographic validator verifying Telegram WebApp credentials against bot secret token.",
                "files": "app/portal/auth.py, tests/test_telegram_auth.py",
                "dod": "SHA256 HMAC verification of Telegram initData query string; prevents replay attacks and hash spoofing.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "Seamless Portal Auto-Login Middleware",
                "goal": "Add route handler and session bridge in app/portal/routes.py authenticating merchants via WebApp headers.",
                "files": "app/portal/routes.py, app/portal/auth.py",
                "dod": "Instant authentication into portal session without SMS/WhatsApp OTP when opened inside Telegram.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Telegram Bot Menu Button & Deep Link Integration",
                "goal": "Configure Telegram bot menu button and inline /portal command launching the in-app WebApp.",
                "files": "app/channels/telegram.py, app/web/telegram_routes.py",
                "dod": "Bot Menu Button configured via Telegram Bot API setChatMenuButton; /portal replies with WebApp button.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Responsive Viewport & Telegram Theme Adaptation",
                "goal": "Inject Telegram WebApp JS SDK into app/templates/portal/layout.html and optimize mobile touch navigation.",
                "files": "app/templates/portal/layout.html, app/templates/portal/dashboard.html",
                "dod": "Theme variables (bg_color, text_color, button_color) match user's Telegram client theme. Zero emojis.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Mini App Authentication & Portal Test Suite",
                "goal": "Add unit tests validating HMAC signature verification, session creation, and replay attack prevention.",
                "files": "tests/test_telegram_miniapp.py",
                "dod": "Full test coverage of initData verification with valid, expired, and tampered payloads.",
                "completed": False,
            },
        ],
    },

    # -------------------------------------------------------------
    # WAVE 2: Daily Workflow & Viral Retention
    # -------------------------------------------------------------
    {
        "dir": "2026-09-29-branded-digital-receipts",
        "title": "Branded Digital Receipts Engine",
        "slug": "branded-digital-receipts",
        "wave": 2,
        "wave_name": "Wave 2: Daily Workflow & Viral Retention",
        "plan_label": "plan:receipts",
        "critical_files": ["app/services/receipt_renderer.py", "app/web/receipt_routes.py", "app/templates/receipt.html"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Digital Receipt Rendering Engine",
                "goal": "Create app/services/receipt_renderer.py generating compact, branded PNG and PDF receipts using Pillow/ReportLab.",
                "files": "app/services/receipt_renderer.py, tests/test_receipt_renderer.py",
                "dod": "Crisp thermal-style or clean card receipts generated in <50ms with merchant name, items, tax, and total.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "Merchant Branding & Template Customization",
                "goal": "Allow merchants to configure business name, phone, address, and receipt footer notes via chat/portal.",
                "files": "app/portal/routes.py, app/templates/portal/settings.html",
                "dod": "Custom logo upload, header/footer note configuration stored in merchant business profile.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-03",
                "title": "Telegram Native Share & Inline Keyboard Action",
                "goal": "Attach inline keyboard buttons ('Share Receipt', 'Download PDF') beneath sale confirmations in Telegram.",
                "files": "app/channels/telegram.py, app/agents/agent_2_ledger.py",
                "dod": "Sale confirmation in Telegram sends receipt document + share button with one tap.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "WhatsApp Digital Receipt Delivery",
                "goal": "Send branded receipt image in WhatsApp with one-tap forward prompt upon completing a sale.",
                "files": "app/channels/whatsapp.py, app/agents/agent_2_ledger.py",
                "dod": "WhatsApp media message upload via Cloud API; caption with transaction summary.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Receipt Generation Test Coverage",
                "goal": "Add unit tests verifying receipt rendering, currency formatting, and multi-channel message dispatch.",
                "files": "tests/test_receipt_flow.py",
                "dod": "Tests covering multi-item receipts, currency symbol formatting (NGN), and missing logo fallback.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-automated-debt-recovery-engine",
        "title": "Automated Debt Recovery & Settlement Engine",
        "slug": "automated-debt-recovery-engine",
        "wave": 2,
        "wave_name": "Wave 2: Daily Workflow & Viral Retention",
        "plan_label": "plan:debt-recovery",
        "critical_files": ["app/agents/debt_agent.py", "app/services/debt_service.py", "app/data/models.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Debt Ledger & Aging Analysis Service",
                "goal": "Build debtor management and aging bucket calculations (0-30 days, 31-60 days, 60+ days) in app/services/debt_service.py.",
                "files": "app/services/debt_service.py, app/data/models.py",
                "dod": "Accurate customer debt balances, partial payment deductions, and aging classification.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "Conversational 'Who Dey Owe Me' Intent Parser",
                "goal": "Teach intake agent to parse Nigerian debt queries like 'who dey owe me', 'kemi don pay 5k', 'remind emeka'.",
                "files": "app/agents/debt_agent.py, app/services/nlp.py",
                "dod": "High-confidence parsing of debtor names, partial settlements, and reminder triggers.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Automated Polite WhatsApp/SMS Debt Reminders",
                "goal": "Generate gentle, culturally respectful debt reminder messages with merchant approval step.",
                "files": "app/services/debt_reminders.py, app/channels/whatsapp.py",
                "dod": "Tone-sensitive reminder templates in English and Pidgin; merchant confirms before dispatch.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Paystack Direct Debt Payment Links & Reconciliation",
                "goal": "Attach one-click Paystack payment link to debt reminders for instant settlement into merchant's account.",
                "files": "app/web/billing_routes.py, app/services/debt_service.py",
                "dod": "Paystack customer payment link generated; webhook auto-settles debt entry upon successful payment.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Debt Recovery Test Suite & Safe Reminder Limits",
                "goal": "Add tests validating debt lifecycle, partial repayments, rate limiting (max 1 reminder/day/customer).",
                "files": "tests/test_debt_recovery.py",
                "dod": "Zero duplicate reminders, correct balance updates after partial payments, harassment-prevention limits.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-daily-victory-evening-recap",
        "title": "Daily Victory Evening Recap",
        "slug": "daily-victory-evening-recap",
        "wave": 2,
        "wave_name": "Wave 2: Daily Workflow & Viral Retention",
        "plan_label": "plan:daily-recap",
        "critical_files": ["app/services/recap_service.py", "app/agents/reporting_agent.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Daily Financial Aggregator & Milestone Detection",
                "goal": "Calculate daily total sales, margin, top-selling product, and compare with 7-day average.",
                "files": "app/services/recap_service.py, app/data/queries.py",
                "dod": "Fast aggregation query executed in <20ms; detects milestones (highest sales day, best seller).",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "Celebration Copy Generator & Pidgin Financial Insights",
                "goal": "Draft warm, motivating evening summary in Nigerian Pidgin or standard English celebrating business effort.",
                "files": "app/services/recap_service.py, app/services/formatter.py",
                "dod": "Natural, upbeat recap copy with clear breakdown of Cash In, Cash Out, and Net Profit.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Scheduled 8:00 PM Multi-Channel Dispatcher",
                "goal": "Build scheduled cron worker delivering the daily recap to active merchants at 8:00 PM local time.",
                "files": "app/services/recap_scheduler.py, app/channels/registry.py",
                "dod": "Multi-channel dispatch (WhatsApp or Telegram based on user preference); skips inactive accounts.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Visual Evening Victory Card Image Generator",
                "goal": "Generate an aesthetic summary card image suitable for sharing on WhatsApp Status or Instagram Stories.",
                "files": "app/services/report_renderer.py, tests/test_recap_image.py",
                "dod": "Rendered PNG victory card with merchant branding, clean layout, no emojis, professional typography.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Daily Recap Scheduler & Formatting Test Suite",
                "goal": "Add tests validating timezone handling (WAT UTC+1), empty-day fallback message, and dispatch failure retries.",
                "files": "tests/test_daily_recap.py",
                "dod": "Comprehensive test suite covering milestone detection, zero-transaction days, and dispatch safety.",
                "completed": False,
            },
        ],
    },

    # -------------------------------------------------------------
    # WAVE 3: Multimodal Intelligence & Growth
    # -------------------------------------------------------------
    {
        "dir": "2026-09-29-voice-notes-multilingual-ledger",
        "title": "Multilingual Voice Notes Ledger",
        "slug": "voice-notes-multilingual-ledger",
        "wave": 3,
        "wave_name": "Wave 3: Multimodal Intelligence & Growth",
        "plan_label": "plan:voice-notes",
        "critical_files": ["app/services/audio_service.py", "app/agents/agent_1_intake.py", "app/services/nlp.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Multi-Channel Audio Inbound Handler & Transcoder",
                "goal": "Download and convert inbound voice notes (WhatsApp OGG Opus / Telegram OGA/MP3) to 16kHz WAV.",
                "files": "app/services/audio_service.py, app/web/routes.py, app/web/telegram_routes.py",
                "dod": "Reliable download from Meta Cloud API and Telegram Bot API; ffmpeg/pydub audio normalization.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "OpenAI Whisper Transcription Service",
                "goal": "Integrate OpenAI Whisper API with Nigerian accent and dialect prompt hints for fast, accurate speech-to-text.",
                "files": "app/services/audio_service.py, tests/test_audio_service.py",
                "dod": "Transcribes noisy market audio with >90% keyword accuracy; fallback to text if audio unclear.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Local Language & Pidgin Code-Switching Grammar Lexicon",
                "goal": "Build Nigerian commercial dictionary (k, bag, carton, derica, mudu, ego, kudi, owo) for intent parsing.",
                "files": "app/services/nlp.py, app/agents/agent_1_intake.py",
                "dod": "Accurate extraction of item, quantity, unit, and price from mixed Pidgin/English voice transcripts.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Conversational Audio Confirmation & TTS Voice Reply",
                "goal": "Reply with both text summary and optional brief audio confirmation for illiterate or busy merchants.",
                "files": "app/services/audio_service.py, app/channels/base.py",
                "dod": "Audio message generated and sent back to WhatsApp/Telegram chat confirming transaction recording.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Voice Bookkeeping End-to-End Test Suite",
                "goal": "Add end-to-end tests with synthetic audio fixtures covering sales, purchases, and debt logging.",
                "files": "tests/test_voice_bookkeeping.py",
                "dod": "Mocked Whisper tests proving flawless flow from voice note to committed database record.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-pos-and-receipt-vision-scanner",
        "title": "POS & Paper Receipt Vision Scanner",
        "slug": "pos-and-receipt-vision-scanner",
        "wave": 3,
        "wave_name": "Wave 3: Multimodal Intelligence & Growth",
        "plan_label": "plan:pos-vision",
        "critical_files": ["app/services/vision_service.py", "app/agents/agent_1_intake.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Inbound Image Normalization & Preprocessing Pipeline",
                "goal": "Handle inbound photos of POS terminal slips and receipts, apply contrast enhancement and orientation correction.",
                "files": "app/services/vision_service.py, app/channels/base.py",
                "dod": "Image resizing, compression, and EXIF orientation auto-rotation for optimal LLM vision parsing.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "GPT-4o-Vision OCR Structured Schema Extractor",
                "goal": "Use GPT-4o-vision with Pydantic structured output to extract merchant, amount, date, reference, and line items.",
                "files": "app/services/vision_service.py, app/agents/event_schemas.py",
                "dod": "Structured JSON output matching TransactionEvent schema; confidence score per field.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Multi-Provider POS Slip Parser (Moniepoint, OPay, PalmPay)",
                "goal": "Fine-tune prompts and regex anchors for top Nigerian POS terminal slips (OPay, Moniepoint, PalmPay, Baxi).",
                "files": "app/services/vision_service.py, tests/test_vision_service.py",
                "dod": "High precision extraction of Stanbic/OPay/Moniepoint transaction reference and final amount.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Image Confidence Scoring & Clarification Fallback Flow",
                "goal": "If image is blurry or amount is ambiguous, prompt merchant with quick yes/no button confirmation.",
                "files": "app/agents/agent_1_intake.py, app/channels/base.py",
                "dod": "Safe fallback: asks 'I saw ₦4,500 for OPay transfer. Is this correct?' before committing.",
                "completed": False,
            },
            {
                "id": "WP-05",
                "title": "Vision Extraction Test Suite & Synthetic Slips Fixture",
                "goal": "Add comprehensive test suite with fixtures of clean, crumpled, and low-light receipt images.",
                "files": "tests/test_pos_vision.py",
                "dod": "Unit tests ensuring zero hallucinations on missing fields and accurate transaction posting.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-predictive-inventory-and-restock",
        "title": "Predictive Inventory & Restock Alerts",
        "slug": "predictive-inventory-and-restock",
        "wave": 3,
        "wave_name": "Wave 3: Multimodal Intelligence & Growth",
        "plan_label": "plan:inventory",
        "critical_files": ["app/services/inventory_forecast.py", "app/agents/inventory_agent.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Sales Velocity & Stock Burn-Rate Calculator",
                "goal": "Calculate daily units sold and average burn rate per SKU over 7-day and 30-day rolling windows.",
                "files": "app/services/inventory_forecast.py, app/data/queries.py",
                "dod": "Computes days-of-stock-remaining for every active inventory item.",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "Predictive Restock Thresholds & Lead-Time Estimator",
                "goal": "Dynamically compute reorder point = (velocity * supplier lead time) + safety stock.",
                "files": "app/services/inventory_forecast.py, app/data/models.py",
                "dod": "Adapts reorder points to merchant sales spikes (e.g. weekend surges).",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Proactive Low-Stock WhatsApp/Telegram Alerts",
                "goal": "Send actionable warnings before merchant stocks out: 'You have 3 bags of rice left (approx 2 days of stock)'.",
                "files": "app/services/inventory_alerts.py, app/channels/base.py",
                "dod": "Scheduled daily scan; batches low-stock alerts into a single digest to prevent spam.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Instant Restock Purchase Order Draft Generator",
                "goal": "Generate one-click purchase order or WhatsApp message to supplier with suggested reorder quantities.",
                "files": "app/services/inventory_forecast.py, app/portal/routes.py",
                "dod": "Merchant clicks 'Restock' in portal or replies 'Order' in chat to format supplier message.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Predictive Inventory Simulation & Test Suite",
                "goal": "Add tests validating velocity calculations, zero-sale SKUs, seasonality adjustments, and alert deduping.",
                "files": "tests/test_predictive_inventory.py",
                "dod": "100% test coverage of forecasting formulas and alert trigger thresholds.",
                "completed": False,
            },
        ],
    },
    {
        "dir": "2026-09-29-merchant-credit-passport",
        "title": "Merchant Credit Passport & Audit Dossier",
        "slug": "merchant-credit-passport",
        "wave": 3,
        "wave_name": "Wave 3: Multimodal Intelligence & Growth",
        "plan_label": "plan:credit-passport",
        "critical_files": ["app/services/credit_score.py", "app/services/report_renderer.py", "app/web/passport_routes.py"],
        "wps": [
            {
                "id": "WP-01",
                "title": "Credit Health Scoring & Metrics Aggregator",
                "goal": "Build proprietary 0-100 credit health scoring based on revenue consistency, operating profit, and cash reserves.",
                "files": "app/services/credit_score.py, tests/test_credit_score.py",
                "dod": "Deterministic algorithm evaluating 6 core financial indicators; generates health grade (A, B, C, D).",
                "completed": False,
            },
            {
                "id": "WP-02",
                "title": "3-Page Certified Dossier PDF Template",
                "goal": "Design and render bank-grade, audit-ready financial statement PDF with revenue charts and integrity seals.",
                "files": "app/services/report_renderer.py, tests/test_passport_pdf.py",
                "dod": "ReportLab rendered 3-page document with monthly cash flow breakdown and formal verification footer.",
                "completed": False,
            },
            {
                "id": "WP-03",
                "title": "Tamper-Proof Verification Token & QR Code Generator",
                "goal": "Mint cryptographic verification tokens (HMAC-SHA256) and embed QR codes linking to public verification page.",
                "files": "app/services/passport_security.py, app/data/models.py",
                "dod": "QR code scanned by loan officer resolves to authenticated, tamper-evident verification route.",
                "completed": False,
            },
            {
                "id": "WP-04",
                "title": "Public Digital Verification Route & UI",
                "goal": "Build /verify/passport/<token> web endpoint displaying audited business overview and certification status.",
                "files": "app/web/passport_routes.py, app/templates/passport_verify.html",
                "dod": "Public verification screen for banks/fintechs. Strict zero emoji and zero em dash compliance.",
                "completed": False,
                "is_ui": True,
            },
            {
                "id": "WP-05",
                "title": "Credit Passport Export & Verification Test Suite",
                "goal": "Add tests validating scoring calculations, PDF generation, QR validity, and verification route access.",
                "files": "tests/test_credit_passport.py",
                "dod": "Complete test suite validating bank-grade integrity and token expiration.",
                "completed": False,
            },
        ],
    },
]


def generate_orchestration_file(plan):
    plan_path = os.path.join(PLANS_DIR, plan["dir"])
    target_file = os.path.join(plan_path, "09-orchestration.md")

    lines = []
    lines.append(f"# {plan['title']} — Implementation Orchestration")
    lines.append("")
    lines.append(f"How to drive the build with **one orchestrator agent + per-work-package subagents**.")
    lines.append(f"Source of truth: `05-tracking.md`. At kickoff the orchestrator mirrors each work package into a GitHub Issue / Task.")
    lines.append("")
    lines.append("> ⚠️ **Planning artifact only — follow the wave order and branch discipline strictly.**")
    lines.append("")
    lines.append("<!-- groundwork:auto:start orchestration -->")
    lines.append("")
    lines.append("## Execution model")
    lines.append("")
    lines.append(f"- **Isolation axis:** git repo + disjoint files. All work lands in `tali` repository.")
    lines.append(f"- **Wave Assignment:** {plan['wave_name']}.")
    lines.append(f"- **Branch Discipline:** Base branch `feat/{plan['slug']}`; each work package micro-branches on `feature/<wp-id>-<slug>`, tests cleanly, and PRs into base branch.")
    lines.append("- **UI & Visual Standards:** If a work package builds or touches UI, `impeccable` and `huashu-design` MUST be used. Emojis and em dashes (`—`) are strictly PROHIBITED in copy/labels. Real photography, unDraw vector illustrations (`undraw.co`), and AI-generated images are permitted.")
    lines.append("")
    lines.append("## Freeze gates (hard, sequential)")
    lines.append("")
    lines.append("| Gate | Work Package | Why it gates | Sign-off check |")
    lines.append("|---|---|---|---|")
    first_wp = plan["wps"][0]
    lines.append(f"| `G-{first_wp['id']}` | {first_wp['id']} | Core foundations and schemas must be locked before consumer features build | Unit tests passing, schema migration verified |")
    lines.append("")
    lines.append("## Work-package matrix")
    lines.append("")
    lines.append("| WP | Title | Wave | Depends on | PR target / Output |")
    lines.append("|---|---|---|---|---|")
    for i, wp in enumerate(plan["wps"]):
        dep = plan["wps"][i-1]["id"] if i > 0 else "—"
        lines.append(f"| {wp['id']} | {wp['title']} | Wave {plan['wave']} | {dep} | `feat/{plan['slug']}` |")
    lines.append("")
    lines.append("### Wave plan (orchestrator spawn order)")
    lines.append("")
    lines.append(f"- **Phase 1 (Foundations & Models):** {plan['wps'][0]['id']}")
    lines.append(f"- **Phase 2 (Core Business Logic):** {plan['wps'][1]['id']}, {plan['wps'][2]['id']}")
    lines.append(f"- **Phase 3 (Delivery & Verification):** {plan['wps'][3]['id']}, {plan['wps'][4]['id']}")
    lines.append("")
    lines.append("## Subagent brief template")
    lines.append("")
    lines.append("```")
    lines.append("GOAL · REPO · BRANCH · DEPENDS-ON · FILES (create/touch) · DEFINITION OF DONE · UI CONSTRAINTS")
    lines.append("```")
    lines.append("")
    for i, wp in enumerate(plan["wps"]):
        dep = plan["wps"][i-1]["id"] if i > 0 else "—"
        lines.append("---")
        lines.append("")
        lines.append(f"### {wp['id']} — {wp['title']}")
        lines.append(f"- **GOAL:** {wp['goal']}")
        lines.append(f"- **REPO/BRANCH:** tali / `feature/{wp['id'].lower()}-{wp['title'].lower().replace(' ', '-')[:25]}`")
        lines.append(f"- **DEPENDS-ON:** {dep}")
        lines.append(f"- **FILES:** {wp['files']}")
        lines.append(f"- **DEFINITION OF DONE:** {wp['dod']}")
        if wp.get("is_ui"):
            lines.append("- **UI CONSTRAINTS:** Mandatory `impeccable` and `huashu-design` skills. Zero emojis. Zero em dashes. Real photos, unDraw SVG, or AI images.")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Tracking protocol")
    lines.append("")
    lines.append("- Durable cross-session source of truth: `05-tracking.md` and GitHub Issues.")
    lines.append("- On each WP completion: run pytest, commit, push branch, create PR targeting base branch, and merge after check passes.")
    lines.append("")
    lines.append("<!-- groundwork:auto:end orchestration -->")
    lines.append("")

    content = "\n".join(lines)
    with open(target_file, "w") as f:
        f.write(content)
    print(f"Generated {target_file}")

    # Update .groundwork.json
    gw_json_path = os.path.join(plan_path, ".groundwork.json")
    if os.path.exists(gw_json_path):
        try:
            with open(gw_json_path, "r") as f:
                gw_data = json.load(f)
            hasher = hashlib.sha256()
            hasher.update(content.encode("utf-8"))
            gw_data.setdefault("docs", {})["09-orchestration.md"] = {
                "hash": hasher.hexdigest(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            gw_data.setdefault("orchestrate", {})["last_run"] = datetime.now(timezone.utc).isoformat()
            with open(gw_json_path, "w") as f:
                json.dump(gw_data, f, indent=2)
        except Exception as e:
            print(f"Error updating .groundwork.json in {plan['dir']}: {e}")


def create_github_issues():
    for plan in PLANS_DATA:
        for wp in plan["wps"]:
            title = f"[{plan['slug']}] {wp['id']}: {wp['title']}"
            body_lines = [
                f"## Work Package {wp['id']}: {wp['title']}",
                "",
                f"**Plan**: [{plan['title']}](plans/{plan['dir']})",
                f"**Wave**: {plan['wave_name']}",
                f"**Target Branch**: `feat/{plan['slug']}`",
                "",
                "### Goal",
                wp["goal"],
                "",
                "### Target Files",
                f"`{wp['files']}`",
                "",
                "### Definition of Done",
                f"- [ ] {wp['dod']}",
                "- [ ] All tests passing with 0 errors.",
                "- [ ] Micro-branch PR targeting base branch reviewed and merged.",
            ]
            if wp.get("is_ui"):
                body_lines.extend([
                    "",
                    "### UI & Visual Standards",
                    "- [ ] Mandatory skills: `impeccable` and `huashu-design`.",
                    "- [ ] **No Emojis**: Emojis are strictly banned from UI copy, buttons, headers, cards, and navigation.",
                    "- [ ] **No Em Dashes**: Em dashes (`—`) are strictly banned from UI copy and labels.",
                    "- [ ] **Visual Assets**: Real photography, unDraw vector illustrations (`undraw.co`), or AI-generated images.",
                ])

            body = "\n".join(body_lines)
            cmd = [
                "gh", "issue", "create",
                "--title", title,
                "--body", body,
                "--milestone", plan["wave_name"],
                "--label", f"wave:{plan['wave']}",
                "--label", "type:work-package",
                "--label", plan["plan_label"],
            ]
            print(f"Creating issue: {title}")
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                issue_url = res.stdout.strip()
                print(f"  -> Created: {issue_url}")
                if wp.get("completed"):
                    # Extract issue number and close
                    issue_num = issue_url.split("/")[-1]
                    subprocess.run(["gh", "issue", "close", issue_num, "--comment", "Completed in WP-01/WP-02 PRs."], check=True)
                    print(f"  -> Closed issue #{issue_num} (already completed)")
            except subprocess.CalledProcessError as e:
                print(f"  Error creating issue for {wp['id']}: {e.stderr}")


if __name__ == "__main__":
    print("--- 1. Generating 09-orchestration.md for all 10 plans ---")
    for plan in PLANS_DATA:
        generate_orchestration_file(plan)

    print("\n--- 2. Creating GitHub Issues with Wave/Plan/Milestone tagging ---")
    create_github_issues()
    print("\nAll done!")
