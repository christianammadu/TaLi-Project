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
