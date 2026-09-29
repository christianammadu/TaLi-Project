"""Subscription and billing engine (WP-01).

Adds the tables for commercial launch monetization:
- ``subscription_plans`` — pricing tiers ('starter', 'pro', 'business') with feature entitlements.
- ``merchant_subscriptions`` — per-merchant active subscription state, Paystack codes, and period windows.
- ``billing_invoices`` — payment receipts and audit trail.

Revision ID: 0006_subscription_billing
Revises: 0005_channel_accounts
Create Date: 2026-09-29
"""
from alembic import op

from app.data.db import Base  # noqa: F401
import app.data.models as m

revision = "0006_subscription_billing"
down_revision = "0005_channel_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    m.SubscriptionPlan.__table__.create(bind, checkfirst=True)
    m.MerchantSubscription.__table__.create(bind, checkfirst=True)
    m.BillingInvoice.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    m.BillingInvoice.__table__.drop(bind, checkfirst=True)
    m.MerchantSubscription.__table__.drop(bind, checkfirst=True)
    m.SubscriptionPlan.__table__.drop(bind, checkfirst=True)
