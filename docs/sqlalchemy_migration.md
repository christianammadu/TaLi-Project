# SQLAlchemy + Alembic migration

_Started 2026-06-04 on branch `feature/sqlalchemy-mysql`._

Goal: move TaLi's data layer off hand-written `mysql.connector` calls onto
SQLAlchemy (pooled engine + ORM), with Alembic owning the schema.

> ⚠️ **Not yet runtime-verified.** This was authored without a MySQL instance to
> run against (syntax-checked + reviewed only). Run the steps below against a
> real database before relying on it.

## What's in place (foundation)

| Piece | File |
|-------|------|
| Pooled engine + `Session` + `session_scope()` | `app/db.py` |
| ORM models for every table (~20) | `app/models.py` |
| Alembic config | `alembic.ini` |
| Alembic env (URL from `.env`, targets `Base.metadata`) | `migrations/env.py` |
| Baseline migration (creates all tables) | `migrations/versions/0001_baseline.py` |
| `business_id` IDOR-completion migration | `migrations/versions/0002_business_id_nullable.py` |
| Engine wired into the app factory | `app/__init__.py` (`init_engine`) |

The engine uses `pool_pre_ping` + `pool_recycle` and a real pool — this resolves
the "new connection per operation" finding (#11) for any code that uses
`session_scope()`.

## One-time setup

```bash
pip install -r requirements.txt          # adds SQLAlchemy + alembic

# Existing database (already built by init_db): mark it at the baseline,
# WITHOUT recreating tables, then apply later migrations.
alembic stamp 0001_baseline
alembic upgrade head                      # applies 0002 (business_id fix)

# Fresh database instead:
alembic upgrade head                      # creates everything, then 0002
```

`migrations/env.py` reads `DB_USER/DB_PASSWORD/DB_HOST/DB_NAME` from `.env`
(see `.env.example`).

## Future schema changes

Edit `app/models.py`, then:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Models are the single source of truth.

## Ported so far

- ✅ `app/queries.py` — record/sum/list/balance on `session_scope()` + ORM.
- ✅ `app/auth.py` — registration / login / sessions on the ORM.
- ✅ `app/web_routes.py` — inline user-creation block on the ORM.

## Still to do (incremental port — do with a live DB)

1. **Port the remaining modules** from `mysql.connector` to `session_scope()` +
   ORM: the agents (`agent_1/2/3`, `agent_router`, `debt_agent`,
   `snapshot_agent`, `reporting_agent`, `inventory_agent`), `routes.py`,
   `nlp.py` and the outgoing-message logging in `whatsapp.py`.
2. **Retire `init_db()` DDL** once Alembic is verified — keep only the default
   category / threshold **seeding** (move it into a migration or a small seed
   script).
3. **Run `0002`** to finish closing the `business_id` multi-tenant leak on the
   live database.
4. Add tests around the ported modules (addresses review #16).

Each step should be verified against a running MySQL before merging.
