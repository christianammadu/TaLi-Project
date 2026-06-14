"""Migrate the integer-keyed schema to BINARY(16) UUIDs to match the app code.

The live DB is entirely INT-keyed, but the application (UUID_to_BINARY, uuid7,
uuid_to_bin) writes 16-byte UUIDs. That mismatch makes every UUID write fail its
foreign key -- fatally on login (sessions / whatsapp_accounts) and on every
ai_logs / review_queue insert.

This converts each column the models mark as a UUID (UUID_to_BINARY) from INT to
BINARY(16), remapping each existing integer id `v` to its 16-byte big-endian
form via UNHEX(LPAD(HEX(v), 32, '0')) -- so id 6 -> 0x000...06. The SAME mapping
is applied to every parent PK and every child FK column, so relationships are
preserved and all foreign keys can be re-created.

Columns that stay integer (NOT touched): categories.id, ai_logs.id,
messages.id, webhook_events.id, verification_codes.id, transactions.category_id.

SAFETY:
  * defaults to DRY-RUN -- prints every statement and row counts, changes nothing
  * --apply runs a mysqldump backup FIRST (abort if it fails), then converts
  * note: MySQL auto-commits each DDL statement, so there is no single rollback.
    The mysqldump file is the real safety net -- restore command is printed.

Usage (PythonAnywhere Bash console, project root, venv active):
    python scripts/migrate_int_to_uuid.py            # dry run (safe preview)
    python scripts/migrate_int_to_uuid.py --apply     # perform the migration
"""

import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import current_app
from app import create_app
from app.data.database import get_db_connection

# (table, column, nullable_target) -- every column the models define as UUID_to_BINARY.
COLUMNS = [
    # parent primary keys
    ("users", "id", False),
    ("sessions", "id", False),
    ("transactions", "id", False),
    ("records", "id", False),
    ("products", "id", False),
    ("stock_movements", "id", False),
    ("debt_balances", "id", False),
    ("debt_logs", "id", False),
    ("review_queue", "id", False),
    ("inventory_items", "id", False),
    ("inventory_movements", "id", False),
    ("debt_entries", "id", False),
    # foreign-key / user_id columns
    ("whatsapp_accounts", "user_id", False),
    ("sessions", "user_id", False),
    ("categories", "user_id", True),
    ("transactions", "user_id", False),
    ("products", "user_id", False),
    ("stock_movements", "product_id", False),
    ("stock_movements", "user_id", False),
    ("debt_balances", "user_id", False),
    ("debt_logs", "user_id", False),
    ("review_queue", "user_id", False),
    ("ai_logs", "user_id", True),
    ("inventory_items", "user_id", False),
    ("inventory_movements", "inventory_item_id", False),
    ("inventory_movements", "user_id", False),
    ("inventory_movements", "reference_transaction_id", True),
    ("messages", "user_id", True),
    ("debt_entries", "user_id", False),
]


def fetch_existing_tables(cursor, db):
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s",
        (db,),
    )
    return {r[0] for r in cursor.fetchall()}


def fetch_foreign_keys(cursor, db):
    """All single-column FKs in the schema, with their ON DELETE rule."""
    cursor.execute(
        """
        SELECT kcu.CONSTRAINT_NAME, kcu.TABLE_NAME, kcu.COLUMN_NAME,
               kcu.REFERENCED_TABLE_NAME, kcu.REFERENCED_COLUMN_NAME, rc.DELETE_RULE
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
        JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
          ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
         AND rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
        WHERE kcu.CONSTRAINT_SCHEMA = %s AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY kcu.TABLE_NAME, kcu.CONSTRAINT_NAME
        """,
        (db,),
    )
    return cursor.fetchall()


def users_id_is_int(cursor, db):
    cursor.execute(
        "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'",
        (db,),
    )
    row = cursor.fetchone()
    return bool(row) and row[0].lower() in ("int", "bigint", "smallint", "mediumint", "tinyint")


def build_plan(cursor, db):
    existing = fetch_existing_tables(cursor, db)
    cols = [(t, c, n) for (t, c, n) in COLUMNS if t in existing]
    skipped = sorted({t for (t, _, _) in COLUMNS if t not in existing})
    fks = [fk for fk in fetch_foreign_keys(cursor, db) if fk[1] in existing]
    return cols, skipped, fks


def conversion_statements(cols):
    """Yield the per-column statements (the temp-column overwrite dance)."""
    for table, col, nullable in cols:
        null_sql = "NULL" if nullable else "NOT NULL"
        yield f"ALTER TABLE `{table}` ADD COLUMN `_uuid_tmp` BINARY(16) NULL;"
        yield (f"UPDATE `{table}` SET `_uuid_tmp` = UNHEX(LPAD(HEX(`{col}`), 32, '0')) "
               f"WHERE `{col}` IS NOT NULL;")
        yield f"ALTER TABLE `{table}` MODIFY `{col}` BINARY(16) {null_sql};"
        yield f"UPDATE `{table}` SET `{col}` = `_uuid_tmp`;"
        yield f"ALTER TABLE `{table}` DROP COLUMN `_uuid_tmp`;"


def fk_drop_statements(fks):
    for name, table, _col, _rt, _rc, _rule in fks:
        yield f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`;"


def fk_add_statements(fks):
    for name, table, col, rt, rc, rule in fks:
        yield (f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` "
               f"FOREIGN KEY (`{col}`) REFERENCES `{rt}` (`{rc}`) ON DELETE {rule};")


def print_dry_run(cursor, cols, skipped, fks):
    print("\n=== DRY RUN (no changes made) ===")
    print(f"\ncolumns to convert to BINARY(16): {len(cols)}")
    for t, c, n in cols:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM `{t}`")
            rows = cursor.fetchone()[0]
        except Exception:
            rows = "?"
        print(f"  {t}.{c} ({'NULL' if n else 'NOT NULL'})  rows={rows}")
    if skipped:
        print(f"\ntables in spec but absent from DB (skipped): {', '.join(skipped)}")
    print(f"\nforeign keys to drop & recreate: {len(fks)}")
    for name, table, col, rt, rc, rule in fks:
        print(f"  {table}.{col} -> {rt}.{rc}  ON DELETE {rule}  ({name})")
    print("\n--- SQL that WOULD run (in order) ---")
    for s in fk_drop_statements(fks):
        print("  " + s)
    for s in conversion_statements(cols):
        print("  " + s)
    for s in fk_add_statements(fks):
        print("  " + s)
    print("\nRun again with --apply to execute (a mysqldump backup is taken first).")


def backup(db):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"backup_{db}_{ts}.sql")
    cfg = current_app.config
    env = dict(os.environ, MYSQL_PWD=cfg["DB_PASSWORD"])
    cmd = ["mysqldump", "-h", cfg["DB_HOST"], "-u", cfg["DB_USER"], cfg["DB_NAME"]]
    print(f"\nBacking up to {out} ...")
    with open(out, "wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump failed: {proc.stderr.decode(errors='ignore')}")
    size = os.path.getsize(out)
    if size < 100:
        raise RuntimeError(f"backup looks empty ({size} bytes) -- aborting")
    print(f"  backup OK ({size} bytes)")
    return out


def apply_migration(conn, cursor, db, cols, fks):
    backup_path = backup(db)
    restore = (f"mysql -h {current_app.config['DB_HOST']} -u {current_app.config['DB_USER']} "
               f"-p {db} < {backup_path}")
    print(f"\n[restore if needed]  {restore}\n")

    def run(stmts):
        for s in stmts:
            print("  " + s)
            cursor.execute(s)

    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        print("\n-- dropping foreign keys --")
        run(fk_drop_statements(fks))
        print("\n-- converting columns --")
        run(conversion_statements(cols))
        print("\n-- recreating foreign keys --")
        run(fk_add_statements(fks))
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
        print("\nMigration applied.")
    except Exception as e:
        print(f"\n!!! FAILED midway: {e}")
        print(f"!!! DDL is auto-committed, so the schema may be partial.")
        print(f"!!! RESTORE FROM BACKUP:\n    {restore}")
        raise
    finally:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except Exception:
            pass


def verify(cursor, db):
    print("\n=== verification ===")
    ok = users_id_is_int(cursor, db)
    print(f"  users.id still integer: {ok}  (expected False)")
    cursor.execute("SELECT id, HEX(id), LENGTH(id) FROM users LIMIT 5")
    for r in cursor.fetchall():
        print(f"  users.id hex={r[1]} byte_len={r[2]}")


def main():
    do_apply = "--apply" in sys.argv
    app = create_app()
    with app.app_context():
        db = current_app.config["DB_NAME"]
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if not users_id_is_int(cursor, db):
                print("users.id is already non-integer -- looks migrated. Aborting.")
                return
            cols, skipped, fks = build_plan(cursor, db)
            if not do_apply:
                print_dry_run(cursor, cols, skipped, fks)
                return
            apply_migration(conn, cursor, db, cols, fks)
            verify(cursor, db)
        finally:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    main()
