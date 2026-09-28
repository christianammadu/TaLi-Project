"""Admin Blueprint for platform operators and stakeholders (WP-04).
"""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.admin import routes  # noqa: E402, F401
