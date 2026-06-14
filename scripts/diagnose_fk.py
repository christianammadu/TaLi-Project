"""Read-only diagnostic for the ai_logs / review_queue foreign-key failures.

Replays the exact code path that fails in IntakeAgent._log_ai_interaction:
    get_active_session(sender) -> session['user_id'] (a str)
        -> uuid_to_bin(user_id) -> SELECT ... FROM users WHERE id = ?

If that lookup misses while the session itself JOINs users fine, we have an
ID that doesn't round-trip (the silent md5 footgun) or an orphaned row left
by the UUID-v7 migration.

This script ONLY runs SELECTs. It writes nothing.

Usage (PythonAnywhere Bash console, from the project root with the venv active):
    python scripts/diagnose_fk.py
    python scripts/diagnose_fk.py 2348167690780   # focus one sender
"""

import os
import sys

# Allow running as a bare script (python scripts/diagnose_fk.py): ensure the
# project root is importable, not just the scripts/ dir that sys.path[0] points at.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.data.database import get_db_connection
from app.services.uuid_utils import uuid_to_bin, bin_to_uuid


def hexb(b):
    return b.hex() if isinstance(b, (bytes, bytearray)) else repr(b)


def check_sender(cursor, sender_id):
    """Replay the failing path for a single active session row."""
    print(f"\n--- sender {sender_id} ---")
    cursor.execute(
        "SELECT id, user_id, status, is_active, expires_at, "
        "expires_at > NOW() AS not_expired "
        "FROM sessions WHERE sender_id = %s "
        "ORDER BY created_at DESC LIMIT 3",
        (sender_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        print("  no session rows at all -> NLP path should never run for this sender")
        return
    for r in rows:
        raw = r["user_id"]
        print(f"  session {hexb(r['id'])[:16]}.. status={r['status']} "
              f"active={r['is_active']} not_expired={r['not_expired']}")
        print(f"    sessions.user_id (raw bytes): {hexb(raw)}")

        # Does the raw FK byte value actually exist in users? (the JOIN's view)
        cursor.execute("SELECT 1 FROM users WHERE id = %s LIMIT 1", (raw,))
        raw_exists = cursor.fetchone() is not None
        print(f"    raw user_id present in users:   {raw_exists}")

        # Reproduce auth.py: str(uuid) then uuid_to_bin(...) — the logging path
        as_uuid = bin_to_uuid(raw)
        as_str = str(as_uuid)
        rebin = uuid_to_bin(as_str)
        print(f"    str(user_id):                   {as_str}")
        print(f"    uuid_to_bin(str(...)) bytes:    {hexb(rebin)}")
        print(f"    round-trips to same bytes:      {rebin == raw}")

        cursor.execute("SELECT 1 FROM users WHERE id = %s LIMIT 1", (rebin,))
        rebin_exists = cursor.fetchone() is not None
        print(f"    rebuilt user_id present in users:{rebin_exists}  "
              f"<-- this is what ai_logs/review_queue insert with")


def scan_orphans(cursor):
    """Cross-table orphan scan: child user_ids with no users parent."""
    print("\n=== orphaned user_id scan (child rows with no users parent) ===")
    children = [
        ("sessions", "user_id"),
        ("whatsapp_accounts", "user_id"),
        ("ai_logs", "user_id"),
        ("review_queue", "user_id"),
        ("messages", "user_id"),
    ]
    for table, col in children:
        try:
            cursor.execute(
                f"SELECT COUNT(*) AS n FROM {table} c "
                f"LEFT JOIN users u ON u.id = c.{col} "
                f"WHERE c.{col} IS NOT NULL AND u.id IS NULL"
            )
            n = cursor.fetchone()["n"]
            flag = "  <-- ORPHANS" if n else ""
            print(f"  {table}.{col}: {n} orphaned{flag}")
        except Exception as e:
            print(f"  {table}.{col}: skipped ({e})")


def main():
    app = create_app()
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT COUNT(*) AS n FROM users")
            print(f"users total: {cursor.fetchone()['n']}")

            scan_orphans(cursor)

            if len(sys.argv) > 1:
                check_sender(cursor, sys.argv[1])
            else:
                cursor.execute(
                    "SELECT DISTINCT sender_id FROM sessions "
                    "WHERE is_active = 1 AND expires_at > NOW() LIMIT 25"
                )
                senders = [r["sender_id"] for r in cursor.fetchall()]
                print(f"\nactive sessions to inspect: {len(senders)}")
                for s in senders:
                    check_sender(cursor, s)
        finally:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
