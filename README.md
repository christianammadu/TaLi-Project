<div align="center">

# 📊 TaLi

### Bookkeeping that lives in the chat you already use.

**TaLi** (from _"Tally"_) is an AI bookkeeping assistant for small businesses in
Africa. Owners record income, expenses, inventory and debts in plain language
over **WhatsApp** — _"Sold rice 5000"_ — and TaLi turns each message into clean
records, live reports and accurate stock. No app to install, no spreadsheets.

`WhatsApp` · `Flask` · `MySQL` · `SQLAlchemy` · `OpenAI` · `Meta Cloud API`

</div>

---

## Table of contents

- [Why TaLi](#why-tali)
- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Database & migrations](#database--migrations)
- [Running & testing](#running--testing)
- [Design system](#design-system)
- [Documentation](#documentation)
- [Roadmap](#roadmap)

---

## Why TaLi

Most small traders keep their books in their head or a torn notebook, and never
really know if they're making money. TaLi meets them where they already are —
WhatsApp — and does the bookkeeping for them from ordinary messages.

> _"Bought fuel 2k"_ → **Expense · Fuel · ₦2,000** recorded.
> _"What's my profit this month?"_ → **Income ₦612,400 · Expenses ₦288,150 · Profit ₦324,250**

## Features

| | Feature | What it does |
|---|---------|--------------|
| 💸 | **Income & expenses** | Natural-language capture with smart auto-categorisation and shorthand (`2k`, `5h`, `50k`). |
| 📈 | **Reports on demand** | Daily / weekly / monthly summaries with real profit, per currency. |
| 📦 | **Inventory** | "Added 20 bags of rice" updates stock; low-stock alerts before you run out. |
| 🧾 | **Debt tracking** | Track receivables & payables per person, with running balances. |
| 🌍 | **Multi-currency** | ₦, $, £ and more, kept separate so totals never mix. |
| 🔍 | **Just ask** | Plain-language questions, exact answers — balances, totals, lists. |
| 🔐 | **Private & secure** | Locked to your WhatsApp number; webhook signature verification. |

## How it works

```
1. Message it          2. AI understands         3. Books update
   "Sold rice 5000"  →  amount · type · item   →  records, reports
   over WhatsApp         category · date            and stock stay live
```

## Architecture

TaLi receives WhatsApp webhooks, authenticates the sender, then runs the message
through a multi-agent pipeline (a lightweight pub/sub "Band SDK") before replying.

```mermaid
flowchart TD
    WA[WhatsApp Cloud API] -->|webhook| WH[web/routes.py · /webhook]
    WH -->|verify signature + dedup| AUTH[auth.py · sessions]
    WH --> ROUTER[agents/agent_router.py]
    ROUTER --> A1[Intake Agent<br/>NLP parse + classify]
    A1 -->|intake_to_ledger| A2[Ledger Agent<br/>record tx / inventory / debt]
    A2 -->|ledger_updates| A3[CFO Agent<br/>format reply + alerts]
    A3 -->|reply| WH
    WH -->|send_reply| WA

    A1 -.-> NLP[services/nlp.py · OpenAI]
    A2 -.-> Q[data/queries.py]
    A3 -.-> REP[agents/reporting_agent.py]
    Q --> DB[(MySQL)]
    REP --> DB
    AUTH --> DB
```

- **Intake → Ledger → CFO** agents communicate over `agents/band_sdk.py`
  (in-process pub/sub), with `agents/event_schemas.py` (Pydantic) as the contract.
- **Idempotency**: inbound `message_id`s are deduped via a `webhook_events` table.
- **Data layer**: migrating from raw `mysql.connector` to **SQLAlchemy** (pooled
  engine + ORM) with **Alembic** migrations — see
  [`docs/sqlalchemy_migration.md`](docs/sqlalchemy_migration.md).

## Project structure

```
bookkeeper/
├── app.py                     # entry point — create_app()
├── app/
│   ├── __init__.py            # Flask app factory (engine, init_db, blueprints)
│   ├── config.py              # env-driven configuration
│   ├── auth.py                # registration, login, sessions (ORM)
│   ├── agents/                # the multi-agent intelligence pipeline
│   │   ├── agent_router.py        # dispatch + dedup
│   │   ├── agent_1_intake.py      # NLP parse & classify
│   │   ├── agent_2_ledger.py      # write transactions / inventory / debt
│   │   ├── agent_3_cfo.py         # compose replies, alerts, reports
│   │   ├── transaction_agent.py   # transaction helpers
│   │   ├── inventory_agent.py · reporting_agent.py · snapshot_agent.py · debt_agent.py
│   │   ├── band_sdk.py            # in-process pub/sub
│   │   └── event_schemas.py      # Pydantic event contracts
│   ├── data/                  # persistence
│   │   ├── db.py                  # SQLAlchemy engine + session_scope()
│   │   ├── models.py              # ORM models (one per table)
│   │   ├── queries.py             # transaction reads/writes (ORM)
│   │   └── database.py            # legacy init_db() (being retired for Alembic)
│   ├── services/              # domain helpers
│   │   ├── nlp.py                 # OpenAI intent parsing
│   │   ├── validators.py · formatter.py · utils.py
│   ├── web/                   # HTTP + messaging
│   │   ├── routes.py              # /webhook (WhatsApp inbound)
│   │   ├── web_routes.py          # registration / verify pages
│   │   └── whatsapp.py            # Meta Cloud API send helpers
│   ├── templates/             # auth pages (TaLi-branded, light/dark)
│   └── static/                # style.css
├── migrations/                # Alembic (env.py + versions/)
├── design/                    # design system & page mockups (design/tali/)
├── docs/                      # project status, bug review, migration plan
├── tests/                     # unit tests
├── .env.example               # all config documented here
└── requirements.txt
```

## Tech stack

- **Backend:** Python · Flask
- **Database:** MySQL · SQLAlchemy 2.0 (ORM) · Alembic (migrations)
- **AI:** OpenAI (intent parsing) · Pydantic (validation/contracts)
- **Messaging:** WhatsApp Cloud API (Meta Graph API)

## Getting started

### Prerequisites
- Python 3.11+
- MySQL 8+
- A Meta WhatsApp Cloud API app (access token, phone number id, verify token, app secret)
- An OpenAI API key

### Setup

```bash
git clone https://github.com/christianammadu/bookkeeper.git
cd bookkeeper

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill in the values (see Configuration)

# Create the schema:
#   fresh database:
alembic upgrade head
#   existing database already built by init_db():
#   alembic stamp 0001_baseline && alembic upgrade head

python app.py                 # starts the Flask server on :5000
```

Expose `:5000` publicly (e.g. `ngrok http 5000`) and point your Meta webhook at
`https://<public-url>/webhook` using your `VERIFY_TOKEN`.

## Configuration

All settings come from environment variables (`.env`). See
[`.env.example`](.env.example) for the full list. Key ones:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask secret — set a strong random value in production. |
| `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` | WhatsApp Cloud API credentials. |
| `META_APP_SECRET` | Verifies inbound webhook signatures (**set in production**). |
| `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MySQL connection. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | AI parsing (default `gpt-4o-mini`). |
| `SESSION_DURATION_HOURS`, `OTP_EXPIRY_MINUTES`, `TOKEN_EXPIRY_MINUTES` | Auth windows. |

## Database & migrations

Schema is owned by **Alembic** (`migrations/`), with the ORM models in
`app/data/models.py` as the single source of truth.

```bash
alembic upgrade head                              # apply migrations
alembic revision --autogenerate -m "describe"     # create a new migration
alembic downgrade -1                              # roll back one
```

The legacy `init_db()` still runs at boot for backward compatibility and will be
retired once Alembic is verified against a live database
([migration plan](docs/sqlalchemy_migration.md)).

## Running & testing

```bash
python app.py            # run the server
python -m pytest         # run the unit tests (tests/)
```

## Design system

The product's marketing, auth and legal pages have a full design system —
dark/light themes, a tally-marks logomark and a line-icon set — under
[`design/tali/`](design/tali/). Open `design/tali/index.html` to browse all
pages. Earlier exploration lives in `design/landing-wireframes/`.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [`docs/project_status.md`](docs/project_status.md) | Architecture & build status. |
| [`docs/critical_bugs.md`](docs/critical_bugs.md) | Security/correctness review with fix status. |
| [`docs/sqlalchemy_migration.md`](docs/sqlalchemy_migration.md) | SQLAlchemy + Alembic migration plan. |

## Roadmap

- [x] Multi-agent WhatsApp pipeline (intake → ledger → CFO)
- [x] Webhook dedup, signature verification, sender-scoped login
- [x] SQLAlchemy + Alembic foundation; `auth` / `queries` ported to the ORM
- [ ] Finish porting agents off raw SQL; retire `init_db()` DDL
- [ ] Format report/inventory replies (no raw JSON), async webhook ack
- [ ] Rate limiting, structured logging, broader test coverage

---

<div align="center">
<sub>© 2026 TaLi · Made for African small business · <em>Tally, simplified.</em></sub>
</div>
