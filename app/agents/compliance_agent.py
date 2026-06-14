"""Compliance/Reviewer Agent (Agent 4) — WP-07, the review leg.

Reviews the Ledger's proposed-write envelope BEFORE commit (the two-phase gate, G-14)
and posts an approve/reject verdict back to @tali-ledger, keyed by the review
correlation id the Ledger is blocking on. Rule-based threshold/anomaly checks today;
an optional AI/ML ('compliance', Featherless) anomaly pass sits behind a flag.

Wired into the room by the gateway (WP-06). This is what turns the sequential chain
into a real plan→execute→review loop: a flagged write is rejected pre-commit, in the room.
"""

import json
import os

from app.agents.band import get_band_client

COMPLIANCE_HANDLE = "@tali-compliance"
LEDGER_HANDLE = "@tali-ledger"


class ComplianceAgent:
    """Agent 4 — Compliance & Risk. Vetoes risky writes before they commit."""

    def __init__(self, user_id, sender_id, band=None):
        self.user_id = user_id
        self.sender_id = sender_id
        self.band = band if band is not None else get_band_client()
        self.room_id = os.getenv("BAND_ROOM_ID") or f"tali-{sender_id}"
        self.large_amount = float(os.getenv("COMPLIANCE_LARGE_AMOUNT", "100000"))

    def on_room_message(self, msg):
        """Review a proposed-write envelope and post a verdict to @tali-ledger (terminal)."""
        body = msg.get("body") or {}
        approved, reason = self.review(body.get("proposed") or {})
        verdict = {"approved": approved, "reason": reason}
        self.band.send(self.room_id, [LEDGER_HANDLE], verdict,
                       correlation_id=msg.get("correlation_id"),
                       sender=COMPLIANCE_HANDLE, terminal=True)
        return verdict

    def review(self, proposed):
        """Pre-commit risk checks. Returns (approved: bool, reason: str)."""
        # 1. Large-amount flag — high-value writes need explicit approval.
        amount = proposed.get("amount")
        if isinstance(amount, (int, float)) and amount >= self.large_amount:
            return False, (f"amount ₦{int(amount):,} exceeds the review threshold "
                           f"(₦{int(self.large_amount):,}) — needs human approval")
        # 2. Optional LLM anomaly pass (off by default; deterministic rules are the floor).
        verdict = self._llm_review(proposed)
        if verdict is not None:
            return verdict
        return True, "ok"

    def _llm_review(self, proposed):
        """AI/ML 'compliance' (Featherless) anomaly check. Enable with COMPLIANCE_LLM_REVIEW=true."""
        if os.getenv("COMPLIANCE_LLM_REVIEW", "false").lower() != "true":
            return None
        try:
            from app.services import model_router
            res = model_router.chat_completion("compliance", messages=[
                {"role": "system", "content": "You are a financial compliance reviewer. Given a "
                 "proposed bookkeeping write as JSON, reply ONLY with {\"approved\": bool, "
                 "\"reason\": str}. Reject only clear fraud, duplication, or policy violations."},
                {"role": "user", "content": json.dumps(proposed)},
            ], response_format={"type": "json_object"}, temperature=0.0, max_tokens=150)
            data = json.loads(res["content"])
            return bool(data.get("approved", True)), str(data.get("reason", ""))
        except Exception as e:
            print(f"[ComplianceAgent LLM review fallback] {e}")
            return None
