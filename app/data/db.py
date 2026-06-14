"""SQLAlchemy engine + session management for TaLi (MySQL).

This is the foundation of the migration off raw ``mysql.connector`` calls:

* a single pooled :class:`~sqlalchemy.engine.Engine` (fixes the "new connection
  per operation" problem),
* a configured :class:`~sqlalchemy.orm.sessionmaker`, and
* a ``session_scope()`` context manager that commits/rolls-back/closes.

Schema is owned by Alembic (see ``migrations/``); ORM models live in
``app.data.models`` and share the :data:`Base` declared here.

Usage::

    from app.data.db import session_scope
    from app.data.models import User

    with session_scope() as s:
        user = s.get(User, user_id)
"""

from contextlib import contextmanager
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Single declarative base shared by every model in app.data.models.
Base = declarative_base()

# Session factory — bound to the engine once init_engine() runs.
SessionLocal = sessionmaker(autoflush=False, autocommit=False, expire_on_commit=False, future=True)

_engine = None


def build_database_url(config):
    """Build a SQLAlchemy MySQL URL from a Flask config mapping.

    Uses the mysql-connector-python driver that the rest of the app already
    depends on, so no new DBAPI is introduced.
    """
    user = quote_plus(str(config.get("DB_USER") or ""))
    password = quote_plus(str(config.get("DB_PASSWORD") or ""))
    host = config.get("DB_HOST") or "localhost"
    name = config.get("DB_NAME") or ""
    return f"mysql+mysqlconnector://{user}:{password}@{host}/{name}"


def init_engine(app):
    """Create the pooled engine from ``app.config`` and bind the session factory.

    Called once from the application factory. ``pool_pre_ping`` guards against
    MySQL's idle-connection drops; ``pool_recycle`` keeps connections under
    ``wait_timeout``.
    """
    global _engine
    _engine = create_engine(
        build_database_url(app.config),
        pool_size=int(app.config.get("DB_POOL_SIZE", 10)),
        max_overflow=int(app.config.get("DB_MAX_OVERFLOW", 5)),
        pool_pre_ping=True,
        pool_recycle=int(app.config.get("DB_POOL_RECYCLE", 1800)),
        future=True,
    )
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine():
    """Return the engine, lazily initialising it from the current Flask app."""
    if _engine is None:
        from flask import current_app
        init_engine(current_app._get_current_object())
    return _engine


@contextmanager
def session_scope():
    """Provide a transactional scope: commit on success, rollback on error."""
    if _engine is None:
        get_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


import uuid
from sqlalchemy.types import TypeDecorator, BINARY

class UUID_to_BINARY(TypeDecorator):
    """Custom type to handle UUID objects as BINARY(16) in MySQL."""
    impl = BINARY
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(BINARY(16))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value.bytes
        if isinstance(value, bytes):
            return value
        if isinstance(value, int):
            return uuid.UUID(int=value).bytes
        if isinstance(value, str):
            if value.isdigit():
                return uuid.UUID(int=int(value)).bytes
            try:
                return uuid.UUID(value).bytes
            except ValueError:
                import hashlib
                return hashlib.md5(value.encode('utf-8')).digest()
        return uuid.UUID(value).bytes

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(bytes=value)
        except Exception:
            return value
