"""Unified audit-trail surfacing — WP-09 (Regulated & High-Stakes track).

Reconstructs a write's full lifecycle from the durable spine — ``event_id``, which threads
across ``transactions`` / ``inventory_movements`` / ``debt_entries`` / ``processed_events`` —
joined to the AI parse in ``ai_logs`` (model, cost, confidence). Agent handoffs come from
``processed_events`` (per-agent timestamps). The Compliance verdict + human approval live in
Band's room audit trail (live) and merge in via ``room_events``.

``assemble_trail`` is pure (unit-tested); ``lifecycle_for`` adds the DB queries.
"""

from app.data.database import get_db_connection


def assemble_trail(event_id, events, room_events=None):
    """Order heterogeneous lifecycle events chronologically and summarise.

    Each event is a dict: ``{ts, stage, actor, detail, model?, cost?, approved?}``.
    Returns ``{event_id, events: [...ordered...], summary: {...}}``.
    """
    merged = [e for e in (list(events) + list(room_events or [])) if e]
    ordered = sorted(merged, key=lambda e: (e.get("ts") or ""))
    models = sorted({e["model"] for e in ordered if e.get("model")})
    total_cost = round(sum(float(e.get("cost") or 0) for e in ordered), 6)
    verdicts = [e.get("approved") for e in ordered if e.get("approved") is not None]
    approved = all(verdicts) if verdicts else None      # None = no explicit verdict recorded
    return {
        "event_id": event_id,
        "events": ordered,
        "summary": {
            "stages": [e.get("stage") for e in ordered],
            "agents": sorted({e["actor"] for e in ordered if e.get("actor")}),
            "models": models,
            "total_cost": total_cost,
            "approved": approved,
        },
    }


def _iso(ts):
    try:
        return ts.isoformat()
    except AttributeError:
        return str(ts) if ts is not None else ""


def _rows_from_db(event_id, conn):
    """Query the durable tables for one ``event_id`` and normalise to trail events."""
    rows = []
    cur = conn.cursor(dictionary=True)
    like = event_id + ":%"     # split writes use event_id:txN / :invN / :debtN

    # 1. Agent handoffs — which agents processed this event, and when.
    cur.execute(
        "SELECT agent_name, processed_at FROM processed_events "
        "WHERE event_id = %s OR event_id LIKE %s ORDER BY processed_at",
        (event_id, like),
    )
    for r in cur.fetchall():
        rows.append({"ts": _iso(r["processed_at"]), "stage": "handoff",
                     "actor": r["agent_name"], "detail": f"{r['agent_name']} processed event"})

    # 2. The write(s).
    raw_text = None
    cur.execute(
        "SELECT type, action, amount, currency, item, raw_text, created_at "
        "FROM transactions WHERE event_id = %s OR event_id LIKE %s ORDER BY created_at",
        (event_id, like),
    )
    for r in cur.fetchall():
        raw_text = r["raw_text"]
        detail = f"{r['action']} {r['item'] or ''} {r['amount']} {r['currency']}".replace("  ", " ").strip()
        rows.append({"ts": _iso(r["created_at"]), "stage": "write", "actor": "LedgerAgent", "detail": detail})

    # 3. The AI parse (model + cost). ai_logs has no event_id — join by the write's raw_text.
    if raw_text:
        cur.execute(
            "SELECT model_name, estimated_cost, confidence_score, processing_time_ms, created_at, source_agent "
            "FROM ai_logs WHERE original_message = %s ORDER BY created_at DESC LIMIT 1",
            (raw_text,),
        )
        r = cur.fetchone()
        if r:
            rows.append({"ts": _iso(r["created_at"]), "stage": "parse",
                         "actor": r["source_agent"] or "IntakeAgent",
                         "detail": f"intent parsed (confidence {r['confidence_score']})",
                         "model": r["model_name"], "cost": float(r["estimated_cost"] or 0)})
    cur.close()
    return rows


def lifecycle_for(event_id, conn=None, room_events=None):
    """Reconstruct the full lifecycle of one write by its ``event_id``.

    ``room_events`` (optional) carries the Compliance verdict + human approval pulled from
    Band's room audit trail in live mode; merged into the durable DB spine.
    """
    own = conn is None
    if own:
        conn = get_db_connection()
    try:
        rows = _rows_from_db(event_id, conn)
    finally:
        if own and conn is not None and conn.is_connected():
            conn.close()
    return assemble_trail(event_id, rows, room_events=room_events)
