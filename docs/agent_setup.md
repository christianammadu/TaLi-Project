# WhatsApp FOS Multi-Agent Setup Guide

This guide provides instructions for setting up, configuring, and testing the 3-Agent architecture (Intake, Ledger, and CFO) of the Bookkeeper (TaLi) WhatsApp Financial Operating System (FOS).

---

## 1. Prerequisites & Environment Setup

The application is built using **Flask** and **MySQL**. All agents communicate internally via the **Band SDK** pub/sub event broker.

### Step 1: Install Python Dependencies
Ensure you have Python 3.10+ installed. In your terminal, run:
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Create a `.env` file in the root directory (using `.env.example` as a template) with the following values:

```env
# Flask Configuration
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=your_flask_secret_key
APP_BASE_URL=http://localhost:5000  # Replace with ngrok or production URL

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=bookkeeper

# Meta WhatsApp Webhook Configuration
VERIFY_TOKEN=your_meta_webhook_verify_token
APP_SECRET=your_meta_app_secret
WHATSAPP_TOKEN=your_whatsapp_access_token
WHATSAPP_PHONE_NUMBER_ID=your_whatsapp_phone_number_id

# OpenAI NLP Integration
OPENAI_API_KEY=your_openai_api_key
OPENAI_INPUT_COST_PER_MILLION=0.150
OPENAI_OUTPUT_COST_PER_MILLION=0.600
```

---

## 2. Database Setup & Migrations

Before running the agents, you must initialize and migrate the MySQL database schema.

### Step 1: Create Database
Connect to your local MySQL instance and run:
```sql
CREATE DATABASE bookkeeper CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Step 2: Run Alembic Migrations
Initialize database tables using Alembic migrations:
```bash
alembic upgrade head
```

This will automatically configure:
- `users`, `sessions`, and `whatsapp_accounts` for OTP and session management.
- `transactions` and `categories` (pre-seeded with default categories like Sales, Salary, utilities).
- `inventory_items` and `inventory_movements` for stock tracking.
- `debt_balances` and `debt_entries` for double-entry debt ledger.
- `webhook_events`, `processed_events`, and `ai_logs` for idempotency and audits.

---

## 3. Meta Developer Portal Webhook Setup (External)

To connect WhatsApp to your local app:

1. **Start ngrok** (or another tunnel) to expose your local server port `5000`:
   ```bash
   ngrok http 5000
   ```
2. **Configure Webhook in Meta Developer Portal**:
   - Go to your app dashboard on [Meta developers portal](https://developers.facebook.com/).
   - Add the **WhatsApp** product.
   - Go to **Configuration** -> **Webhook**.
   - Set Callback URL to: `https://your-ngrok-subdomain.ngrok-free.app/webhook`
   - Set Verification Token to match `VERIFY_TOKEN` in your `.env`.
   - Subscribe to the `messages` event feed.

---

## 4. Internal Agent Orchestration (Band SDK)

The agents communicate in-memory using an event pub/sub mechanism managed by `BandSDK` (`app/agents/band_sdk.py`).

### Event Flow Channel Configuration:
1. **`"intake_to_ledger"`**:
   - **Publisher**: `IntakeAgent` (`app/agents/agent_1_intake.py`) publishes parsed event schemas (`IntakePayload`).
   - **Subscriber**: `LedgerAgent` (`app/agents/agent_2_ledger.py`) registers its `handle_intake_payload` method.
2. **`"ledger_updates"`**:
   - **Publisher**: `LedgerAgent` publishes successful operations using `LedgerUpdateEvent`.
   - **Subscriber**: `CFOAgent` (`app/agents/agent_3_cfo.py`) registers `handle_ledger_update` to format responses and run stock/debt checks.
3. **`"cfo_escalation"`**:
   - **Publisher**: `IntakeAgent` publishes parsing failures or low-confidence requests.
   - **Subscriber**: `CFOAgent` registers `handle_escalation` to format clarification requests to the user.
4. **`"ledger_errors"`**:
   - **Publisher**: `LedgerAgent` publishes transactional failures/database locks.
   - **Subscriber**: `CFOAgent` registers `handle_ledger_error` to send database warning alerts.

All bindings are registered dynamically in `AgentRouter.route` inside `app/agents/agent_router.py` whenever an incoming message is processed.

---

## 5. Running and Testing Locally

### Start Flask Server:
```bash
python run.py
```

### Local Test suite:
Run unit tests to verify the entire multi-agent routing, pre-classification, and database transaction rollback features:
```bash
python -m pytest tests/test_transaction_agent.py -v --tb=short
```

---

## 6. Deployment to PythonAnywhere

When deploying the application to **PythonAnywhere**, make note of the following environment differences:

### Step 1: Proxy Dependency Compatibility
- PythonAnywhere free accounts route all external API calls (such as OpenAI requests) through an HTTP proxy (`http://proxy.server:3128`).
- The `openai` Python SDK leverages `httpx` internally. A breaking change in `httpx>=0.28.0` removed support for the `proxies` argument. To prevent the `Client.__init__() got an unexpected keyword argument 'proxies'` error in your server logs, the project pins `httpx==0.27.2` in `requirements.txt`.

### Step 2: Database Settings
In your PythonAnywhere `.env` configuration, replace `localhost` with your dedicated MySQL server address:
```env
DB_HOST=<your_username>.mysql.pythonanywhere-services.com
DB_USER=<your_username>
DB_PASSWORD=<your_mysql_password>
DB_NAME=<your_username>$bookkeeper
```

### Step 3: WSGI Configuration
In the **Web** tab on PythonAnywhere, configure your WSGI configuration file (`/var/www/<your_username>_pythonanywhere_com_wsgi.py`):
```python
import sys
import os

# Add your project directory to the sys.path
path = '/home/<your_username>/bookkeeper'
if path not in sys.path:
    sys.path.insert(0, path)

# Import the Flask application factory instance
from run import app as application
```

### Step 4: Database Migrations
To initialize your tables and apply schema configurations, open a Bash Console on PythonAnywhere, navigate to your root directory, and run:
```bash
alembic upgrade head
```
