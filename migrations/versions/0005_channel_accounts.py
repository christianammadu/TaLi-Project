"""Multi-channel identity: channel_accounts + binding_tokens (WP-02 / G-IDENTITY)

Adds the tables that let one account span WhatsApp + Telegram:

- ``channel_accounts`` — maps ``(channel, channel_user_id) → user_id``. Existing
  ``whatsapp_accounts`` rows are **backfilled** so current WhatsApp users keep resolving.
- ``binding_tokens`` — single-use, short-TTL deep-link tokens for Telegram onboarding +
  the Path B cross-channel ``/link`` flow.

Tables are created from the ORM models (type-matched UUID BINARY(16) FKs). Non-destructive;
``whatsapp_accounts`` is left in place as the legacy fallback.

Revision ID: 0005_channel_accounts
Revises: 0004_uuid_migration
Create Date: 2026-06-14
"""
from alembic import op

from app.data.db import Base  # noqa: F401  (shared metadata)
import app.data.models as m

revision = "0005_channel_accounts"
down_revision = "0004_uuid_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    m.ChannelAccount.__table__.create(bind, checkfirst=True)
    m.BindingToken.__table__.create(bind, checkfirst=True)
    # Backfill: existing WhatsApp accounts resolve via the new lookup (back-compat).
    op.execute(
        "INSERT INTO channel_accounts (channel, channel_user_id, user_id, linked_at) "
        "SELECT 'whatsapp', sender_id, user_id, linked_at FROM whatsapp_accounts "
        "ON DUPLICATE KEY UPDATE user_id = VALUES(user_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    m.BindingToken.__table__.drop(bind, checkfirst=True)
    m.ChannelAccount.__table__.drop(bind, checkfirst=True)
