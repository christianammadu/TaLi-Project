"""Settings & onboarding fields on users

Adds the columns the in-chat onboarding + settings surfaces read & write:

- ``usage_type``        — ENUM('personal','business'), NULL until the user chooses.
- ``business_profile``  — JSON bag for business fields (name, type, currency),
                          mirroring the ``alert_thresholds`` JSON precedent so no
                          ``businesses`` table is needed for Phase 1 (Option A).
- ``onboarding_step``   — SMALLINT, resumable first-run progress (NULL = not started).

Deliberately does NOT touch ``business_id`` — it stays NULL (see 0002); reviving the
old ``DEFAULT 1`` would re-open the multi-tenant bucket leak.

Revision ID: 0003_settings_onboarding_fields
Revises: 0002_business_id_nullable
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003_settings_onboarding_fields"
down_revision = "0002_business_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("usage_type", mysql.ENUM("personal", "business"), nullable=True))
    op.add_column("users", sa.Column("business_profile", mysql.JSON(), nullable=True))
    op.add_column("users", sa.Column("onboarding_step", mysql.SMALLINT(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "onboarding_step")
    op.drop_column("users", "business_profile")
    op.drop_column("users", "usage_type")
