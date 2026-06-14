"""SQLAlchemy ORM models for TaLi — one class per existing MySQL table.

These mirror the schema currently built by ``app.data.database.init_db`` so that an
Alembic baseline (``migrations/versions``) matches a live database. Types use
the MySQL dialect (ENUM / JSON / BIGINT / TIMESTAMP) where the column is
MySQL-specific; everything else is generic SQLAlchemy.

Note on ``business_id``: there is no ``businesses`` table — the column was added
with ``DEFAULT 1``, so every user shared bucket 1 (a multi-tenant data leak).
Models now default it to NULL and reads scope by ``user_id`` unless a real
``business_id`` is set (see app/queries.py); migration ``0002`` drops the old
default and NULLs the existing ``business_id = 1`` rows.
"""

from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Index, Integer, Numeric, String,
    Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.mysql import BIGINT, ENUM, JSON, SMALLINT, TIMESTAMP

from app.data.db import Base, UUID_to_BINARY

_NOW = text("CURRENT_TIMESTAMP")


class User(Base):
    __tablename__ = "users"
    id = Column(UUID_to_BINARY, primary_key=True)
    phone_number = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100))
    is_verified = Column(Boolean, server_default=text("0"))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    base_currency = Column(String(3), server_default=text("'NGN'"))
    alert_thresholds = Column(JSON)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    usage_type = Column(ENUM("personal", "business"))
    business_profile = Column(JSON)
    onboarding_step = Column(SMALLINT)


class WhatsappAccount(Base):
    __tablename__ = "whatsapp_accounts"
    sender_id = Column(String(50), primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    linked_at = Column(TIMESTAMP, server_default=_NOW)


class ChannelAccount(Base):
    """Multi-channel identity (WP-02 / G-IDENTITY): maps (channel, channel_user_id) → user.

    One user can have several rows (e.g. ``whatsapp``+``telegram``) → one ledger across
    channels. Supersedes ``whatsapp_accounts`` (backfilled by migration 0005)."""
    __tablename__ = "channel_accounts"
    channel = Column(String(20), primary_key=True)          # 'whatsapp' | 'telegram'
    channel_user_id = Column(String(64), primary_key=True)  # phone / chat_id
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    linked_at = Column(TIMESTAMP, server_default=_NOW)
    __table_args__ = (Index("idx_channel_account_user", "user_id"),)


class BindingToken(Base):
    """Single-use deep-link token (WP-02) that binds a channel chat to a user — the
    Telegram onboarding + Path B cross-channel link primitive. ``token`` ≤64 chars,
    URL-safe, short TTL; consumed on redemption (``used_at`` set)."""
    __tablename__ = "binding_tokens"
    token = Column(String(64), primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_channel = Column(String(20))     # optional hint: which channel this token is for
    expires_at = Column(TIMESTAMP, nullable=False)
    used_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=_NOW)


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), nullable=False)
    code = Column(String(6), nullable=False)
    token = Column(String(100), unique=True)
    purpose = Column(ENUM("registration", "login"), nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    used = Column(Boolean, server_default=text("0"))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    __table_args__ = (
        Index("idx_phone_purpose", "phone_number", "purpose"),
        Index("idx_token", "token"),
    )


class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID_to_BINARY, primary_key=True)
    sender_id = Column(String(50), nullable=False)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    is_active = Column(Boolean, server_default=text("1"))
    status = Column(ENUM("PENDING", "ACTIVE", "EXPIRED"), server_default=text("'ACTIVE'"))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    __table_args__ = (Index("idx_sender_active", "sender_id", "is_active"),)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    type = Column(ENUM("income", "expense", "both"), nullable=False, server_default=text("'both'"))


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    type = Column(ENUM("income", "expense"), nullable=False)
    action = Column(String(20), nullable=False, server_default=text("'other'"))
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), nullable=False, server_default=text("'NGN'"))
    item = Column(String(255))
    description = Column(String(255))
    raw_text = Column(String(500), nullable=False)
    transaction_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=_NOW)
    currency_code = Column(String(3), server_default=text("'NGN'"))
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    event_id = Column(String(100), unique=True)
    __table_args__ = (
        Index("idx_user_date", "user_id", "transaction_date"),
        Index("idx_user_category", "user_id", "category_id"),
        Index("idx_user_type", "user_id", "type"),
        Index("idx_user_action", "user_id", "action"),
    )


class Record(Base):
    """Legacy records table (slated for removal)."""
    __tablename__ = "records"
    id = Column(UUID_to_BINARY, primary_key=True)
    sender_id = Column(String(50), nullable=False)
    raw_text = Column(String(255), nullable=False)
    amount = Column(Integer, nullable=False)
    timestamp = Column(TIMESTAMP, server_default=_NOW)


class Product(Base):
    __tablename__ = "products"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False, server_default=text("0.00"))
    unit = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    __table_args__ = (UniqueConstraint("user_id", "name", name="idx_user_product"),)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(UUID_to_BINARY, primary_key=True)
    product_id = Column(UUID_to_BINARY, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movement_type = Column(ENUM("in", "out", "set"), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False)
    description = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    event_id = Column(String(100), unique=True)


class DebtBalance(Base):
    __tablename__ = "debt_balances"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person_name = Column(String(100), nullable=False)
    debt_type = Column(ENUM("receivable", "payable"), nullable=False)
    outstanding_balance = Column(Numeric(15, 2), nullable=False, server_default=text("0.00"))
    currency = Column(String(10), nullable=False, server_default=text("'NGN'"))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    updated_at = Column(TIMESTAMP, server_default=_NOW, server_onupdate=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    __table_args__ = (
        UniqueConstraint("user_id", "person_name", "currency", name="idx_user_person_currency"),
    )


class DebtLog(Base):
    __tablename__ = "debt_logs"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person_name = Column(String(100), nullable=False)
    debt_type = Column(ENUM("receivable", "payable"), nullable=False)
    action = Column(ENUM("add_debt", "repayment", "full_payment"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    previous_balance = Column(Numeric(15, 2), nullable=False)
    new_balance = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), nullable=False, server_default=text("'NGN'"))
    raw_text = Column(String(500), nullable=False)
    created_at = Column(TIMESTAMP, server_default=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    event_id = Column(String(100), unique=True)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    message_id = Column(String(100), primary_key=True)
    sender_id = Column(String(50), nullable=False)
    processed_at = Column(TIMESTAMP, server_default=_NOW)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    event_id = Column(String(100), primary_key=True)
    agent_name = Column(String(50), primary_key=True)
    processed_at = Column(TIMESTAMP, server_default=_NOW)


class ReviewQueue(Base):
    __tablename__ = "review_queue"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_text = Column(String(500), nullable=False)
    parsed_payload = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=_NOW)


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(String(50), nullable=False, unique=True)
    raw_text = Column(String(500), nullable=False)
    parsed_json = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, server_default=_NOW)
    expires_at = Column(TIMESTAMP, nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    whatsapp_message_id = Column(String(100), unique=True, nullable=False)
    sender_id = Column(String(50), nullable=False)
    payload = Column(JSON)
    status = Column(
        ENUM("received", "processing", "processed", "failed"),
        server_default=text("'received'"),
    )
    created_at = Column(TIMESTAMP, server_default=_NOW)
    processed_at = Column(TIMESTAMP, nullable=True)


class AiLog(Base):
    __tablename__ = "ai_logs"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="SET NULL"))
    model_name = Column(String(50))
    original_message = Column(Text)
    parsed_intent = Column(String(100))
    parsed_json = Column(JSON)
    confidence_score = Column(Numeric(5, 4))
    estimated_cost = Column(Numeric(12, 6))
    processing_time_ms = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    source_agent = Column(String(50), server_default=text("'IntakeAgent'"))


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(150), nullable=False)
    unit = Column(String(50))
    minimum_stock_level = Column(Numeric(15, 2), server_default=text("0"))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id = Column(UUID_to_BINARY, primary_key=True)
    inventory_item_id = Column(UUID_to_BINARY, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movement_type = Column(ENUM("stock_in", "stock_out", "adjustment"), nullable=False)
    quantity = Column(Numeric(15, 2), nullable=False)
    reference_transaction_id = Column(UUID_to_BINARY, ForeignKey("transactions.id", ondelete="SET NULL"))
    notes = Column(Text)
    created_at = Column(TIMESTAMP, server_default=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    event_id = Column(String(100), unique=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_id = Column(UUID_to_BINARY)  # nullable, no FK in the existing schema
    sender_id = Column(String(50))
    direction = Column(ENUM("incoming", "outgoing"), nullable=False)
    message_text = Column(Text)
    whatsapp_message_id = Column(String(100))
    created_at = Column(TIMESTAMP, server_default=_NOW)


class DebtEntry(Base):
    __tablename__ = "debt_entries"
    id = Column(UUID_to_BINARY, primary_key=True)
    user_id = Column(UUID_to_BINARY, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    person_name = Column(String(100), nullable=False)
    type = Column(ENUM("receivable", "payable"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), nullable=False, server_default=text("'NGN'"))
    raw_text = Column(String(500))
    created_at = Column(TIMESTAMP, server_default=_NOW)
    business_id = Column(Integer)  # NULL until provisioned; see 0002 migration
    event_id = Column(String(100), unique=True)
    __table_args__ = (Index("idx_user_person", "user_id", "person_name"),)
