"""baseline — current TaLi schema captured as ORM models

Creates every table from ``app.data.models`` metadata. This is the migration
baseline:

* **Fresh database:** ``alembic upgrade head`` creates all tables.
* **Existing database** (already built by ``init_db``): run
  ``alembic stamp 0001_baseline`` once to mark it current WITHOUT recreating
  anything, then use ``alembic upgrade head`` for future revisions.

Subsequent schema changes should be generated with
``alembic revision --autogenerate -m "..."`` so the ORM models stay the single
source of truth.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-04
"""
from alembic import op

from app.data.db import Base
import app.data.models  # noqa: F401  (populates Base.metadata)

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
