<div align="center">
 
# 📊 TaLi
 
### Collaborative Multi-Agent Bookkeeping over WhatsApp & Telegram
 
**TaLi** (from _"Tally"_) is an enterprise-grade, multi-agent bookkeeping system built for small businesses in Africa. It enables traders, shop owners, and freelancers to manage their transactions, inventory, and debts in plain natural language directly from **WhatsApp** and **Telegram**, backed by a collaborative agent network.
 
`WhatsApp` · `Telegram` · `Band SDK` · `Featherless AI` · `AI/ML API` · `Flask` · `SQLAlchemy` · `MySQL` · `Alembic`
 
</div>
 
---
 
## 🤝 Band of Agents Hackathon Alignment
 
TaLi was specifically built and designed for the **Band of Agents Hackathon (June 12–19, 2026)** to address **Track 1: Internal Enterprise Workflows** and **Track 3: Regulated & High-Stakes Workflows**. It showcases a collaborative, conversation-driven agent network operated inside a shared environment.
 
- **Collaboration Layer (Band)**: Instead of a linear, hardcoded script, TaLi deploys a team of **5 specialized agents** collaborating inside a shared **Band Room**. Communication, task handoffs, and state coordination occur dynamically via native `@mentions` and structured JSON message events.
- **Traceability & Safety (Human-in-the-Loop)**: High-risk actions (large expenses or debt changes) trigger an active compliance review and require inline human approval in the room before database persistence occurs.
- **Technology Partners (Featherless AI & AI/ML API)**: Powered by a multi-provider router that matches task complexity to the optimal provider (e.g. Featherless AI for compliance auditing; AI/ML API for CFO analytics), backed by automatic failovers.
 
---
 
## Table of contents
 
- [Why TaLi](#why-tali)
- [How it works](#how-it-works)
- [Multi-Agent Collaboration Architecture](#multi-agent-collaboration-architecture)
- [Technology Partner Integrations](#technology-partner-integrations)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Database & Migrations](#database--migrations)
- [Running & Testing](#running--testing)
- [Design System & UI](#design-system--ui)
 
---
 
## Why TaLi
 
Most small traders and informal merchants keep their accounts in their head or on easily misplaced paper logs. Existing accounting software has a steep learning curve and requires spreadsheets. TaLi meets merchants where they already are — chat apps — and does the bookkeeping for them through simple, conversational messages.
 
> 💬 **Merchant:** *"Sold 3 bags of rice 18k"*  
> 🤖 **TaLi:** *"Recorded a ₦18,000 sale. Stock updated: 12 bags of rice remaining. ✓"*
 
---
 
## How it works
 
```
1. Chat Message       2. Band Room Handoff       3. Compliance & Human       4. Live Update
  "Sold rice 18k"  →   NLP Parse & Propose   →    Audit policy rules    →    DB committed &
  via WA/Telegram      via @tali-intake           & human loop approval        CFO replies
```
 
---
 
## Multi-Agent Collaboration Architecture
 
TaLi receives inbound messaging webhooks, resolves the user session, and dispatches the payload to a shared **Band Room** (using `BAND_BACKEND=stub` for local offline dev, and `live` for the real platform). Inside the room, **five specialized agents** coordinate the lifecycle of the request:
 
1. **`@tali-intake` (Intake Agent)**: Receives the raw text, uses NLP (`Featherless AI`) to parse the intent, amount, units, date, and entities, and `@mentions` the Ledger Agent with the structured transaction proposal.
2. **`@tali-ledger` (Ledger Agent)**: Maintains the ledger state machine. It verifies balance changes, structures database records, and `@mentions` the Compliance Agent to request an audit before committing.
3. **`@tali-compliance` (Compliance Agent)**: Audits the transaction against system safety thresholds (e.g. flagging single expenses > ₦100k or debts > ₦50k) and either raises a veto or `@mentions` the Ledger Agent with approval.
4. **`@tali-human` (Human Loop Agent)**: Active when compliance flags a transaction for manual oversight. It pauses execution, sends an interactive approval request, and notifies the Ledger Agent once a manager approves.
5. **`@tali-cfo` (CFO Agent)**: Summarizes the outcome, calculates total cashflow and multi-currency balances, monitors low stock alerts, and posts the final customer-facing reply back to the chat gateway.
 
```mermaid
flowchart TD
    WA[WhatsApp / Telegram API] -->|Webhook| WH[web/routes.py · /webhook]
    WH -->|Verify & Dedup| AUTH[auth.py · Sessions]
    WH --> GW[agents/agent_router.py · Band Gateway]
 
    subgraph ROOM[Band Room · Dynamic Handoffs]
      A1["@tali-intake<br/>NLP Parser"]
      A2["@tali-ledger<br/>Ledger State Manager"]
      A4["@tali-compliance<br/>Policy Auditor"]
      A3["@tali-cfo<br/>Financial Reporter"]
      HU["@tali-human<br/>Human Approval Portal"]
    end
 
    GW --> A1
    A1 -->|@ledger| A2
    A2 -->|Proposes Write| A4
    A4 -->|Approve / Veto| A2
    A2 -.->|Threshold Trigger| HU
    HU -.->|Approval Event| A2
    A2 -->|@cfo| A3
    A3 -->|Terminal Response| GW
    GW -->|Send Reply| WA
 
    A1 -.-> MR[services/model_router.py]
    A4 -.-> MR
    MR -.-> P{{Featherless AI & AI/ML API}}
    A2 -.-> DB[(MySQL Database)]
```
 
---
 
## Technology Partner Integrations
 
TaLi implements a native **Multi-provider Model Router** ([model_router.py](file:///c:/Users/chris/OneDrive/Desktop/TaLi-Project/app/services/model_router.py)) that routes agent roles to optimized serverless endpoints:
 
- **Featherless AI**: Powers our specialized open-source reasoning models. We use `Qwen/Qwen2.5-72B-Instruct` for natural language parsing (`intake`) and `mistralai/Mistral-Small-24B-Instruct-2501` for structured policy checks (`compliance`).
- **AI/ML API**: Connects to frontier commercial models like `gpt-4o` for CFO analysis, cost forecasting, and complex escalation reasoning.
- **Graceful Failovers**: Every routing chain has automatic fallbacks to OpenAI (`gpt-4o-mini`) in case of provider timeouts, 429s, or service outages, ensuring high availability.
- **FinOps Spending Controls**: Tracks token usage and costs per model in real-time, enforcing a budget limit (`MODEL_ROUTER_SPEND_CEILING_USD`) to prevent runaway API spend.
 
---
 
## Features
 
| Category | Feature | What it does |
|:---:|---|---|
| 💸 | **Income & Expenses** | Record sales, costs, and purchases using conversational text and short-hand amounts (`2k`, `5h`, `50k`). |
| 📦 | **Auto Inventory** | Inventory adjustments are updated on transaction commits (e.g. "Added 20 bags of rice" or "Sold 3 bags"); tags alert when stock drops below minimum limits. |
| 🧾 | **Debt Ledger** | Track accounts receivable and payable by name, offering summaries of who owes who. |
| 🌍 | **Multi-Currency** | Keep totals in Naira (₦), Dollars ($), and Pounds (£) separated so conversion errors never pollute local accounts. |
| 🔐 | **Security & Verification** | Two-factor verification using access codes, signed webhook checks, and phone number session bindings. |
 
---
 
## Project Structure
 
```
TaLi-Project/
├── run.py                     # App entry point (creates & launches Flask server)
├── alembic.ini                # Database migration configuration
├── app/
│   ├── __init__.py            # Flask app factory (pooled engine setup, routes, context)
│   ├── config.py              # Environment configuration loader
│   ├── auth.py                # OTP delivery, link minting, session validation
│   ├── agents/                # Band room intelligence pipeline
│   │   ├── agent_router.py        # Gateway routing and event deduping
│   │   ├── agent_1_intake.py      # NLP parser (Featherless AI)
│   │   ├── agent_2_ledger.py      # Database read/writes and transaction hooks
│   │   ├── agent_3_cfo.py         # Response compilation and stock alerts
│   │   └── band_sdk.py            # Local in-process pub/sub stub
│   ├── data/                  # Persistent data layers
│   │   ├── db.py                  # SQLAlchemy engine & session scopes
│   │   ├── models.py              # Declarative database models (Users, Ledger, Webhooks)
│   │   └── database.py            # Legacy schema initializer
│   ├── services/              # External integrations
│   │   ├── model_router.py        # Multi-provider router (Featherless & AI/ML API)
│   │   └── nlp.py                 # Core LLM prompt structures
│   ├── templates/             # Jinja2 templates (landing, pricing, registers)
│   │   ├── _meta.html             # Reusable SEO, OG, and layout meta tags
│   │   └── ...
│   └── static/                # Stylesheets (style.css, landing.css) and assets
├── migrations/                # Alembic versions and migration hooks
├── tests/                     # Project test suite
└── requirements.txt           # Main project dependencies
```
 
---
 
## Getting Started
 
### Prerequisites
- Python 3.11+
- MySQL 8+
- An OpenAI API Key
- An AI/ML API Key & Featherless AI API Key
- Meta WhatsApp Cloud API credentials
 
### Installation & Setup
 
1. **Clone the repository**:
   ```bash
   git clone https://github.com/christianammadu/TaLi-Project.git
   cd TaLi-Project
   ```
 
2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
 
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
 
4. **Configure environment**:
   Create a `.env` file based on `.env.example` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
 
5. **Run migrations**:
   ```bash
   alembic upgrade head
   ```
 
6. **Start the server**:
   ```bash
   python run.py
   ```
 
---
 
## Configuration
 
TaLi is configured via environment variables. Refer to [`.env.example`](.env.example) for details. Key variables:
 
- `OPENAI_API_KEY`, `AIML_API_KEY`, `FEATHERLESS_API_KEY`: API access for model providers.
- `BAND_BACKEND`: Set to `stub` for offline development (simulates agent room exchanges), or `live` for connecting to the Band production servers.
- `WHATSAPP_PUBLIC_NUMBER`, `TELEGRAM_BOT_USERNAME`: User access entry points.
- `META_APP_SECRET`: Key used to verify Meta Cloud Webhook signatures.
 
---
 
## Database & Migrations
 
Database schema changes are managed by **Alembic** under `migrations/`. The database models are defined in [models.py](file:///c:/Users/chris/OneDrive/Desktop/TaLi-Project/app/data/models.py).
 
```bash
alembic upgrade head                              # Apply all migrations
alembic revision --autogenerate -m "description"  # Generate new migration version
alembic downgrade -1                              # Roll back last migration
```
 
---
 
## Running & Testing
 
Launch tests to verify the integrity of session mapping and agent stubs:
```bash
python run.py             # Start dev server
python -m pytest          # Execute unit tests
```
 
---
 
## Design System & UI
 
TaLi features a custom design system ("Market Ledger" style) utilizing Hanken Grotesk and Fraunces fonts. The branding is configured in [landing.css](file:///c:/Users/chris/OneDrive/Desktop/TaLi-Project/app/static/landing.css) and [style.css](file:///c:/Users/chris/OneDrive/Desktop/TaLi-Project/app/static/style.css), which are optimized for mobile and desktop screens.
 
We serve a custom Open Graph marketing asset located at [og-image.png](file:///c:/Users/chris/OneDrive/Desktop/TaLi-Project/app/static/og-image.png) for link preview rendering on chat clients and search indexers.
 
---
 
<div align="center">
<sub>© 2026 TaLi · Built for the Band of Agents Hackathon · <em>Tally, simplified.</em></sub>
</div>
