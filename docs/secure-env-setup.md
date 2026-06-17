# Secure Environment Configuration Guide

This guide details best practices and step-by-step instructions to configure the `.env` file securely on your production or staging instances. The `.env` file contains sensitive API keys, database passwords, and cryptographic secrets. Securing this file prevents unauthorized access to your cloud infrastructure, databases, and third-party integration platforms.

---

## 🔒 1. Host Instance Security Principles

### Rule 1: Never Commit Secrets to Source Control
Ensure the `.env` file remains listed in the project's `.gitignore` file. Never commit it to git. If a secret is accidentally committed:
1. Immediately rotate the secret at the provider (OpenAI, Band, Telegram, etc.).
2. Purge the git history using `git-filter-repo` or a similar tool.

### Rule 2: Enforce Strict Linux File Permissions
On a Linux VPS or cloud instance, restrict read/write access to the `.env` file exclusively to the user owning/running the application process (e.g., the `root` or `ubuntu` user, or a dedicated `tali` user).

Configure permissions immediately after creating the `.env` file:
```bash
# Restrict permissions so only the file owner can read and write
chmod 600 .env

# Verify file ownership and permissions
ls -la .env
# Output should show: -rw------- 1 ubuntu ubuntu ... .env
```

### Rule 3: Generate Cryptographically Secure Keys
For production, avoid simple text or default keys. Generate high-entropy values for variables like `SECRET_KEY` and `DB_ROOT_PASSWORD`.

Use one of the following commands on the instance to generate 32-byte secure hexadecimal keys:
```bash
# Using OpenSSL (Recommended)
openssl rand -hex 32

# Using Python's secrets module
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## ⚙️ 2. Recommended `.env` Template for Docker

Create a new file named `.env` in the root of the project (`/app/TaLi-Project/.env`) and configure the variables below.

```ini
# ==============================================================================
# TaLi — Production Environment Configuration
# ==============================================================================

# --- Flask & General Security ---
# Generate a strong key using `openssl rand -hex 32`
SECRET_KEY=9a2b8e3a...c4d9e0f

# --- MySQL Database Configuration ---
# Used to bootstrap the MySQL container on startup
DB_ROOT_PASSWORD=super-secure-root-password-here
DB_NAME=tali
DB_USER=tali_user
DB_PASSWORD=secure-user-password-here

# --- WhatsApp / Meta Cloud API ---
# Access tokens and IDs for Meta Business API integration
ACCESS_TOKEN=your-meta-cloud-api-access-token
PHONE_NUMBER_ID=your-whatsapp-phone-number-id
VERIFY_TOKEN=custom-random-verify-token-for-webhooks
META_APP_SECRET=your-meta-app-secret-from-dashboard

# --- Authentication & TTLs ---
APP_BASE_URL=https://tali.yourdomain.com
SESSION_DURATION_HOURS=72
OTP_EXPIRY_MINUTES=10
TOKEN_EXPIRY_MINUTES=5
OTP_TEMPLATE_NAME=verification_code
OTP_TEMPLATE_LANG=en_US
OTP_TEXT_FALLBACK=true
OTP_DEV_BYPASS=false

# --- LLM Providers & Multi-Provider Routing ---
# Primary OpenAI Key (used as a fallback)
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini

# AI/ML API (Reasoning + CFO model provider)
AIML_API_KEY=your-aiml-api-key
AIML_BASE_URL=https://api.aimlapi.com/v1

# Featherless (OS NLP Parser + Compliance auditor)
FEATHERLESS_API_KEY=your-featherless-api-key
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1

# Cost and Budget Control Limits
MODEL_ROUTER_SPEND_CEILING_USD=10.0
AGENT_PIPELINE_TIMEOUT_SECONDS=20

# --- Band Platform Integration ---
# "live" for production, "stub" for offline testing
BAND_BACKEND=live
THENVOI_REST_URL=https://app.band.ai/
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
BAND_ROOM_ID=your-band-coordination-room-id
BAND_API_KEY=your-tenant-rest-api-key

# Per-Agent Credentials (from Settings -> Remote Agents in app.band.ai)
BAND_INTAKE_AGENT_ID=your-intake-agent-id
BAND_INTAKE_API_KEY=your-intake-api-key
BAND_LEDGER_AGENT_ID=your-ledger-agent-id
BAND_LEDGER_API_KEY=your-ledger-api-key
BAND_CFO_AGENT_ID=your-cfo-agent-id
BAND_CFO_API_KEY=your-cfo-api-key
BAND_COMPLIANCE_AGENT_ID=your-compliance-agent-id
BAND_COMPLIANCE_API_KEY=your-compliance-api-key

# --- Compliance & Audit Settings ---
COMPLIANCE_LARGE_AMOUNT=100000
AUDIT_TOKEN=secure-audit-retrieval-bearer-token

# --- Telegram Bot Channel Configuration ---
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_BOT_USERNAME=your-bot-username-without-at
TELEGRAM_WEBHOOK_SECRET=strong-random-webhook-secret-token
TELEGRAM_API_BASE=https://api.telegram.org
WHATSAPP_PUBLIC_NUMBER=whatsapp-public-display-number-e164
```

---

## 🛠️ 3. Deployment Workflow with Docker Compose

1. **Clone the Project on the Instance**:
   ```bash
   git clone https://github.com/christianammadu/TaLi-Project.git
   cd TaLi-Project
   ```

2. **Create and Secure the `.env` File**:
   ```bash
   touch .env
   chmod 600 .env
   nano .env
   # Copy the template above, fill in the real credentials, and save the file.
   ```

3. **Verify the Configuration and Launch Services**:
   ```bash
   # Build the container and start the services in detached mode
   docker compose up -d --build
   ```

4. **Verify Container Health**:
   ```bash
   docker compose ps
   # Ensure both 'tali-mysql-db' and 'tali-flask-app' are running and healthy.
   ```

5. **Exposed Ports**:
   - The Flask Web App is exposed on host port `5000` (can be reversed proxied via Nginx/Caddy with SSL).
   - MySQL is exposed on host port `3306` for external database administration if needed.
