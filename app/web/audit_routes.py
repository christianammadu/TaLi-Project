"""Read-only audit-trail endpoint — WP-09 (Regulated & High-Stakes track).

Surfaces one write's full lifecycle (parse → handoffs → write, with model + cost) by its
``event_id``. Guarded by an optional ``X-Audit-Token`` header matching ``AUDIT_TOKEN`` — set
that env var in any regulated deployment; left open only when unset (dev).
"""

import hmac
import os
from flask import Blueprint, jsonify, request

from app.services.audit import lifecycle_for

audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/audit/<event_id>", methods=["GET"])
def audit_view(event_id):
    token = os.getenv("AUDIT_TOKEN", "")
    if not token:
        # Fail closed: an unset AUDIT_TOKEN would expose every write's lifecycle
        # (raw text, amounts, model, cost). Only the explicit dev flag opens it.
        if os.getenv("OTP_DEV_BYPASS", "false").lower() != "true":
            return jsonify({"error": "audit endpoint disabled (set AUDIT_TOKEN)"}), 403
    elif not hmac.compare_digest(request.headers.get("X-Audit-Token", ""), token):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(lifecycle_for(event_id))
