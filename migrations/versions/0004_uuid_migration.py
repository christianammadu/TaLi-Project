"""UUID migration (NO-OP — superseded by scripts/migrate_int_to_uuid.py)

Revision ID: 0004_uuid_migration
Revises: 0003_settings_onboarding_fields
Create Date: 2026-06-05

History / why this is a no-op
-----------------------------
The original 0004 attempted to ALTER every INT primary/foreign key to
BINARY(16) in-place. That approach was abandoned because:

  * it cast integer ids straight to BINARY without HEX/UNHEX padding, so
    existing rows would have been corrupted;
  * it referenced column shapes that did not match production;
  * it toggled SET FOREIGN_KEY_CHECKS = 0 around the whole batch.

The live INT -> UUID conversion was instead performed once, safely, by
``scripts/migrate_int_to_uuid.py`` (mysqldump backup, temp-column overwrite
via UNHEX(LPAD(HEX(col),32,'0')), FK drop/recreate). Production is already
BINARY(16)-keyed.

Schema ownership going forward
------------------------------
For this single-DB deployment the runtime schema is owned by:
  1. ``app/data/database.py`` startup DDL (CREATE TABLE IF NOT EXISTS +
     additive ADD COLUMN guards) — creates/repairs tables on every boot,
     including ``pending_confirmations``;
  2. the one-time ``scripts/migrate_int_to_uuid.py`` for the id-type change.

Alembic is retained only so a *fresh* install has a coherent revision chain
and so ``alembic stamp head`` can mark the migrated production DB as current.
This revision is intentionally empty; do not re-add destructive ALTERs here.
"""
from alembic import op  # noqa: F401  (kept so the module imports under alembic)
import sqlalchemy as sa  # noqa: F401

revision = "0004_uuid_migration"
down_revision = "0003_settings_onboarding_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Intentional no-op. See module docstring."""
    pass


def downgrade() -> None:
    """Intentional no-op. See module docstring."""
    pass
