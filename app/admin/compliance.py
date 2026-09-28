"""Compliance Review Queue Service and Room Resumption (WP-06).

Provides human-in-the-loop audit governance for transactions flagged by compliance:
- Inspects flagged transactions (high expense > ₦100,000, high debt > ₦50,000, low confidence).
- Approves or rejects transactions with optimistic HTMX row updates.
- Resumes agent rooms via orchestrator.post_human_decision (@tali-human).
- Dispatches instant confirmation/alert notifications to merchants on WhatsApp/Telegram.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

from app.data.db import session_scope
from app.data.models import ReviewQueue, User, Transaction
from app.agents.orchestrator import post_human_decision

logger = logging.getLogger(__name__)

# In-memory mock/active compliance store for demo/tests & offline fallback
_IN_MEMORY_REVIEWS: Dict[str, Dict[str, Any]] = {
    "rev-101": {
        "id": "rev-101",
        "user_id": "usr-01",
        "merchant_name": "Alhaji Musa Enterprise",
        "merchant_phone": "2348031234567",
        "channel": "whatsapp",
        "raw_text": "Paid factory supplier ₦1,250,000 for raw sugar bags invoice #889",
        "amount": 1_250_000.00,
        "currency": "NGN",
        "intent": "record_expense",
        "risk_type": "high_expense",
        "risk_badge": {"label": "High Expense", "color": "red"},
        "confidence_score": 0.96,
        "room_id": "room-usr-01",
        "status": "PENDING",
        "created_at": "2026-09-28 14:22:10",
        "parsed_payload": {
            "amount": 1250000.00,
            "type": "expense",
            "category": "Supplies",
            "item": "raw sugar bags",
            "vendor": "factory supplier",
        }
    },
    "rev-102": {
        "id": "rev-102",
        "user_id": "usr-02",
        "merchant_name": "Balogun Textiles & Sons",
        "merchant_phone": "2348029876543",
        "channel": "telegram",
        "raw_text": "Emeka owes ₦350,000 for 10 lace bundles to pay next Friday",
        "amount": 350_000.00,
        "currency": "NGN",
        "intent": "record_debt",
        "risk_type": "high_debt",
        "risk_badge": {"label": "High Debt", "color": "amber"},
        "confidence_score": 0.94,
        "room_id": "room-usr-02",
        "status": "PENDING",
        "created_at": "2026-09-28 15:45:00",
        "parsed_payload": {
            "amount": 350000.00,
            "type": "debt",
            "debtor": "Emeka",
            "item": "10 lace bundles",
            "due_date": "next Friday"
        }
    },
    "rev-103": {
        "id": "rev-103",
        "user_id": "usr-03",
        "merchant_name": "Kano Provisions Hub",
        "merchant_phone": "2348055554433",
        "channel": "whatsapp",
        "raw_text": "transfer 85k for miscellaneous logistics packaging",
        "amount": 85_000.00,
        "currency": "NGN",
        "intent": "record_expense",
        "risk_type": "low_confidence",
        "risk_badge": {"label": "Low Confidence", "color": "purple"},
        "confidence_score": 0.68,
        "room_id": "room-usr-03",
        "status": "PENDING",
        "created_at": "2026-09-28 16:10:22",
        "parsed_payload": {
            "amount": 85000.00,
            "type": "expense",
            "category": "Logistics",
            "notes": "ambiguous vendor entity"
        }
    }
}


def classify_risk(amount: float, intent: str, confidence: float) -> Tuple[str, Dict[str, str]]:
    """Determine risk classification and visual badge tokens."""
    if confidence < 0.75:
        return "low_confidence", {"label": "Low Confidence", "color": "purple"}
    if "debt" in intent.lower() or amount >= 200_000:
        if amount >= 50_000:
            return "high_debt", {"label": "High Debt", "color": "amber"}
    if amount >= 100_000:
        return "high_expense", {"label": "High Expense", "color": "red"}
    return "review_flag", {"label": "Compliance Flag", "color": "amber"}


def get_pending_reviews(risk_filter: str = "all") -> List[Dict[str, Any]]:
    """Retrieve all pending review items filtered by risk category."""
    reviews: List[Dict[str, Any]] = []

    # 1. Fetch persistent database records if available
    try:
        with session_scope() as session:
            db_rows = session.query(ReviewQueue).all()
            for row in db_rows:
                payload = {}
                try:
                    payload = json.loads(row.parsed_payload) if isinstance(row.parsed_payload, str) else (row.parsed_payload or {})
                except Exception:
                    pass

                amt = float(payload.get("amount") or 0.0)
                intent = payload.get("intent") or "record_transaction"
                conf = float(payload.get("confidence") or 0.95)
                risk_type, risk_badge = classify_risk(amt, intent, conf)

                reviews.append({
                    "id": str(row.id),
                    "user_id": str(row.user_id),
                    "merchant_name": f"Merchant #{str(row.user_id)[:8]}",
                    "merchant_phone": payload.get("sender_id", "2348000000000"),
                    "channel": payload.get("channel", "whatsapp"),
                    "raw_text": row.raw_text,
                    "amount": amt,
                    "currency": payload.get("currency", "NGN"),
                    "intent": intent,
                    "risk_type": risk_type,
                    "risk_badge": risk_badge,
                    "confidence_score": conf,
                    "room_id": payload.get("room_id", f"room-{row.user_id}"),
                    "status": "PENDING",
                    "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
                    "parsed_payload": payload,
                })
    except Exception:
        pass

    # 2. Merge with in-memory store if DB is empty or fallback mode
    if not reviews:
        reviews = list(_IN_MEMORY_REVIEWS.values())

    # Filter by risk if requested
    if risk_filter and risk_filter != "all":
        reviews = [r for r in reviews if r["risk_type"] == risk_filter or r["status"] == risk_filter]

    return reviews


def get_review_by_id(review_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single review item by ID."""
    reviews = get_pending_reviews(risk_filter="all")
    for r in reviews:
        if str(r["id"]) == str(review_id):
            return r
    return _IN_MEMORY_REVIEWS.get(review_id)


def notify_merchant(recipient: str, message: str, channel: str = "whatsapp") -> bool:
    """Send immediate transaction review decision to the merchant."""
    try:
        if channel == "telegram":
            from app.channels.telegram import get_telegram_client
            client = get_telegram_client()
            if client:
                client.send_text(recipient, message)
                return True
        else:
            from app.web.whatsapp import send_reply
            send_reply(recipient, message)
            return True
    except Exception as e:
        logger.warning("[Compliance Notification] Failed to notify %s via %s: %s", recipient, channel, e)
    return False


def resolve_review(
    review_id: str,
    action: str,
    reviewer: str = "Admin",
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """Execute compliance decision (Approve or Reject/Veto) for a flagged transaction.

    Args:
        review_id: ID of the review queue item
        action: 'approve' or 'reject'
        reviewer: Name or handle of the human officer
        reason: Optional human veto rationale

    Returns:
        Dict detailing the resolution outcome
    """
    review = get_review_by_id(review_id)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if not review:
        return {
            "success": False,
            "review_id": review_id,
            "error": f"Review item #{review_id} not found."
        }

    is_approval = (action.lower() == "approve")
    status = "APPROVED" if is_approval else "REJECTED"

    # 1. Update in-memory state
    if review_id in _IN_MEMORY_REVIEWS:
        _IN_MEMORY_REVIEWS[review_id]["status"] = status
        _IN_MEMORY_REVIEWS[review_id]["reviewed_by"] = reviewer
        _IN_MEMORY_REVIEWS[review_id]["reviewed_at"] = now_str
        _IN_MEMORY_REVIEWS[review_id]["decision_reason"] = reason

    # 2. Update database record if exists
    try:
        with session_scope() as session:
            db_item = session.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
            if db_item:
                session.delete(db_item)
    except Exception:
        pass

    # 3. Resume the agent room via Orchestrator (@tali-human)
    room_id = review.get("room_id") or f"room-{review.get('user_id')}"
    post_human_decision(
        room_id=room_id,
        review_id=review_id,
        decision="approved" if is_approval else "rejected",
        reason=reason,
    )

    # 4. Dispatch notification to merchant
    recipient = review.get("merchant_phone") or review.get("user_id")
    channel = review.get("channel", "whatsapp")
    amt_fmt = f"₦{review.get('amount', 0):,.2f}"

    if is_approval:
        user_msg = f"✅ Your transaction of {amt_fmt} has been approved by compliance and recorded to your ledger."
    else:
        user_msg = f"❌ Your transaction of {amt_fmt} was reviewed and declined by compliance."
        if reason:
            user_msg += f"\nReason: {reason}"

    notify_merchant(recipient, user_msg, channel=channel)

    return {
        "success": True,
        "review_id": review_id,
        "action": action,
        "status": status,
        "amount": review.get("amount", 0.0),
        "merchant_name": review.get("merchant_name", "Merchant"),
        "raw_text": review.get("raw_text", ""),
        "reviewed_by": reviewer,
        "reviewed_at": now_str,
        "reason": reason,
        "message": user_msg,
    }


def get_compliance_stats() -> Dict[str, int]:
    """Summary counts for compliance hub header badges."""
    reviews = get_pending_reviews(risk_filter="all")
    pending = [r for r in reviews if r.get("status") == "PENDING"]

    return {
        "total_pending": len(pending),
        "high_expense_count": sum(1 for r in pending if r.get("risk_type") == "high_expense"),
        "high_debt_count": sum(1 for r in pending if r.get("risk_type") == "high_debt"),
        "low_confidence_count": sum(1 for r in pending if r.get("risk_type") == "low_confidence"),
    }
