import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "tali-dev-secret-key")

    # WhatsApp / Meta Cloud API
    ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
    PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
    VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
    # Meta App Secret — used to verify the X-Hub-Signature-256 on inbound webhooks.
    APP_SECRET = os.getenv("META_APP_SECRET", "")

    # MySQL Database
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")

    # Authentication
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
    SESSION_DURATION_HOURS = int(os.getenv("SESSION_DURATION_HOURS", "72"))
    OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
    TOKEN_EXPIRY_MINUTES = int(os.getenv("TOKEN_EXPIRY_MINUTES", "5"))
    OTP_TEMPLATE_NAME = os.getenv("OTP_TEMPLATE_NAME", "verification_code")
    # MUST match the language of your approved WhatsApp template (e.g. en or en_US).
    OTP_TEMPLATE_LANG = os.getenv("OTP_TEMPLATE_LANG", "en_US")
    # When the template send fails, also try a plain-text OTP (only delivers if the
    # recipient is inside WhatsApp's 24-hour customer-service window — useful for testing).
    OTP_TEXT_FALLBACK = os.getenv("OTP_TEXT_FALLBACK", "true").lower() == "true"
    # DEV ONLY (default OFF — opt in explicitly). When enabled, registration
    # proceeds to the OTP step even if WhatsApp delivery fails, and the code is
    # printed to the server console for testing. NEVER enable in production: it
    # stops real users receiving codes and logs OTP values. Set OTP_DEV_BYPASS=true.
    OTP_DEV_BYPASS = os.getenv("OTP_DEV_BYPASS", "false").lower() == "true"

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_INPUT_COST_PER_MILLION = float(os.getenv("OPENAI_INPUT_COST_PER_MILLION", "0.150"))
    OPENAI_OUTPUT_COST_PER_MILLION = float(os.getenv("OPENAI_OUTPUT_COST_PER_MILLION", "0.600"))

    # --- Multi-provider model routing (WP-01 / G-MODEL-ROUTER) ---
    # AI/ML API and Featherless are OpenAI-compatible; app/services/model_router.py reaches every
    # provider through the OpenAI SDK with a swapped base_url, and falls back to OpenAI on
    # timeout / 429 / quota / connection error. Keys/models are read from env by the router;
    # mirrored here so the rest of the app can introspect them.
    AIML_API_KEY = os.getenv("AIML_API_KEY", "")
    AIML_BASE_URL = os.getenv("AIML_BASE_URL", "https://api.aimlapi.com/v1")
    FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
    FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
    # Per-role model overrides (provider defaults live in model_router.ROLE_ROUTES).
    FEATHERLESS_INTAKE_MODEL = os.getenv("FEATHERLESS_INTAKE_MODEL", "Qwen/Qwen2.5-72B-Instruct")
    FEATHERLESS_COMPLIANCE_MODEL = os.getenv("FEATHERLESS_COMPLIANCE_MODEL", "mistralai/Mistral-Small-24B-Instruct-2501")
    AIML_CFO_MODEL = os.getenv("AIML_CFO_MODEL", "gpt-4o")
    AIML_ESCALATION_MODEL = os.getenv("AIML_ESCALATION_MODEL", "gpt-4o")
    # Optional per-process spend ceiling (USD); 0 = unlimited. Enforced by the router so a
    # demo run can't blow the small AI/ML credit (Round 2 risk).
    MODEL_ROUTER_SPEND_CEILING_USD = float(os.getenv("MODEL_ROUTER_SPEND_CEILING_USD", "0"))

    # --- Band platform (WP-02 / G-BAND-CONTRACT) ---
    # "stub" = in-process fire-and-forget connector (offline dev/tests); "live" = real
    # band.ai / Thenvoi over REST/WS. WS-vs-REST defaults to REST (Round 2) — confirm in WP-02.
    BAND_BACKEND = os.getenv("BAND_BACKEND", "stub")
    BAND_REST_URL = os.getenv("THENVOI_REST_URL", "https://app.band.ai/")
    BAND_WS_URL = os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket")
    BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "")
    # Optional tenant REST key from Settings → REST API Keys. If present, the live
    # backend uses it for Band REST calls and keeps per-agent keys as fallback.
    BAND_API_KEY = os.getenv("BAND_API_KEY", "")
    # Per-agent credentials (agent_id + X-API-Key), registered on app.band.ai (Pro).
    BAND_INTAKE_AGENT_ID = os.getenv("BAND_INTAKE_AGENT_ID", "")
    BAND_INTAKE_API_KEY = os.getenv("BAND_INTAKE_API_KEY", "")
    BAND_LEDGER_AGENT_ID = os.getenv("BAND_LEDGER_AGENT_ID", "")
    BAND_LEDGER_API_KEY = os.getenv("BAND_LEDGER_API_KEY", "")
    BAND_CFO_AGENT_ID = os.getenv("BAND_CFO_AGENT_ID", "")
    BAND_CFO_API_KEY = os.getenv("BAND_CFO_API_KEY", "")
    BAND_COMPLIANCE_AGENT_ID = os.getenv("BAND_COMPLIANCE_AGENT_ID", "")
    BAND_COMPLIANCE_API_KEY = os.getenv("BAND_COMPLIANCE_API_KEY", "")
    # Each agent's @handle on YOUR Band tenant (default = the internal contract handle).
    # The live backend posts to the room under each agent and translates the internal
    # @tali-* mentions to these, so registered agents with different handles still work.
    BAND_INTAKE_HANDLE = os.getenv("BAND_INTAKE_HANDLE", "@tali-intake")
    BAND_LEDGER_HANDLE = os.getenv("BAND_LEDGER_HANDLE", "@tali-ledger")
    BAND_CFO_HANDLE = os.getenv("BAND_CFO_HANDLE", "@tali-cfo")
    BAND_COMPLIANCE_HANDLE = os.getenv("BAND_COMPLIANCE_HANDLE", "@tali-compliance")
    # REST path for posting a message into a room (live mirror). Overridable in case your
    # Band tenant's endpoint differs; {chat_id} is filled with BAND_ROOM_ID.
    BAND_MESSAGE_PATH = os.getenv("BAND_MESSAGE_PATH", "/api/v1/agent/chats/{chat_id}/messages")

    # --- Multi-channel identity (WP-02 / G-IDENTITY) ---
    # TTL (minutes) for single-use deep-link binding tokens (Telegram onboarding + Path B /link).
    BINDING_TOKEN_TTL_MIN = int(os.getenv("BINDING_TOKEN_TTL_MIN", "15"))

    # --- Telegram channel (WP-03/04) ---
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")   # without @ ; feeds the deep-link
    TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
    # Public WhatsApp number for the wa.me Path-B deep-link (the display number, not PHONE_NUMBER_ID).
    WHATSAPP_PUBLIC_NUMBER = os.getenv("WHATSAPP_PUBLIC_NUMBER", "")
