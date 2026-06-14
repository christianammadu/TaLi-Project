from flask import Flask
from app.config import Config
from app.data.database import init_db
from app.data.db import init_engine

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialise the pooled SQLAlchemy engine (used by the ORM data layer).
    init_engine(app)

    # Initialize Database tables.
    # NOTE: schema is being migrated to Alembic (see migrations/). init_db is
    # kept for now so existing deployments keep booting; once Alembic is verified
    # against the live DB, the DDL here can be retired in favour of migrations.
    init_db(app)

    # Register blueprints
    from app.web.routes import webhook_bp
    app.register_blueprint(webhook_bp)

    from app.web.web_routes import web_bp
    app.register_blueprint(web_bp)

    from app.web.audit_routes import audit_bp
    app.register_blueprint(audit_bp)

    from app.web.telegram_routes import telegram_bp
    app.register_blueprint(telegram_bp)

    return app
