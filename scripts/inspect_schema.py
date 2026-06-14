"""Read-only schema + key inspection for the UUID/INT mismatch.

The app code now writes BINARY(16) UUIDs, but live rows appear to still use
integer ids. To pick the right migration we need the GROUND TRUTH: the actual
MySQL column type of every id / user_id column, plus the real key bytes.

This script ONLY runs SELECTs against INFORMATION_SCHEMA and reads a few id
values. It writes nothing.

Usage (PythonAnywhere Bash console, project root, venv active):
    python scripts/inspect_schema.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.data.database import get_db_connection

# Tables whose id / user_id columns matter for the FK chain.
TABLES = [
    "users", "sessions", "whatsapp_accounts", "ai_logs", "review_queue",
    "messages", "transactions", "inventory_items", "inventory_movements",
    "debt_balances", "debt_logs", "debt_entries", "products",
]


def col_types(cursor, db):
    print("=== column types (id / user_id columns) ===")
    cursor.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, IS_NULLABLE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = %s "
        "AND (COLUMN_NAME = 'id' OR COLUMN_NAME LIKE '%%user_id') "
        "ORDER BY TABLE_NAME, COLUMN_NAME",
        (db,),
    )
    for r in cursor.fetchall():
        print(f"  {r['TABLE_NAME']}.{r['COLUMN_NAME']:<10} "
              f"{r['COLUMN_TYPE']:<14} (data_type={r['DATA_TYPE']}, "
              f"nullable={r['IS_NULLABLE']})")


def fk_list(cursor, db):
    print("\n=== foreign keys referencing users.id ===")
    cursor.execute(
        "SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, "
        "REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
        "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL "
        "ORDER BY TABLE_NAME",
        (db,),
    )
    for r in cursor.fetchall():
        print(f"  {r['TABLE_NAME']}.{r['COLUMN_NAME']} -> "
              f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']} "
              f"({r['CONSTRAINT_NAME']})")


def legacy_tables(cursor, db):
    print("\n=== legacy/backup tables present ===")
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME LIKE '%%legacy%%' "
        "ORDER BY TABLE_NAME",
        (db,),
    )
    rows = cursor.fetchall()
    if not rows:
        print("  (none)")
    for r in rows:
        print(f"  {r['TABLE_NAME']}")


def sample_user_ids(cursor):
    print("\n=== users.id raw values (HEX + length) ===")
    try:
        cursor.execute("SELECT id, HEX(id) AS hx, LENGTH(id) AS len FROM users LIMIT 10")
        for r in cursor.fetchall():
            print(f"  id={r['id']!r:<28} hex={r['hx']:<34} byte_len={r['len']}")
    except Exception as e:
        print(f"  could not read users.id: {e}")


def main():
    app = create_app()
    with app.app_context():
        db = app.config["DB_NAME"]
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            print(f"database: {db}\n")
            col_types(cursor, db)
            fk_list(cursor, db)
            legacy_tables(cursor, db)
            sample_user_ids(cursor)
        finally:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
