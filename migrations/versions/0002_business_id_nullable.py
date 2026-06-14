"""business_id: drop DEFAULT 1 and NULL the un-provisioned rows

Completes the multi-tenant IDOR fix. ``business_id`` was added with
``DEFAULT 1`` but there is no ``businesses`` table, so every user shared
bucket 1 — letting unrelated users read each other's records. This migration
drops the default (new rows get NULL) and NULLs every existing ``business_id = 1``
row (always the meaningless default, never a real tenant). Reads already fall
back to ``user_id`` scoping when ``business_id`` is NULL (app/queries.py,
reporting_agent.py, snapshot_agent.py).

Revision ID: 0002_business_id_nullable
Revises: 0001_baseline
Create Date: 2026-06-04
"""
from alembic import op

revision = "0002_business_id_nullable"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

TABLES = [
    "users", "transactions", "debt_balances", "debt_logs",
    "debt_entries", "ai_logs", "inventory_items", "inventory_movements",
]


def upgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN business_id DROP DEFAULT")
        op.execute(f"UPDATE {t} SET business_id = NULL WHERE business_id = 1")


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN business_id SET DEFAULT 1")
        op.execute(f"UPDATE {t} SET business_id = 1 WHERE business_id IS NULL")
