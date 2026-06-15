from contextlib import contextmanager

import mysql.connector
from mysql.connector import Error, pooling
from flask import current_app

_pool = None

def get_db_connection():
    """Returns an active secure pooled connection to your MySQL Server."""
    global _pool
    if _pool is None:
        try:
            _pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="tali_pool",
                pool_size=10,
                host=current_app.config['DB_HOST'],
                user=current_app.config['DB_USER'],
                password=current_app.config['DB_PASSWORD'],
                database=current_app.config['DB_NAME']
            )
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            return mysql.connector.connect(
                host=current_app.config['DB_HOST'],
                user=current_app.config['DB_USER'],
                password=current_app.config['DB_PASSWORD'],
                database=current_app.config['DB_NAME']
            )
    try:
        return _pool.get_connection()
    except Exception as e:
        from app.services.alerts import alert_db_pool_saturation
        alert_db_pool_saturation()
        print(f"Pool connection failed: {e}. Falling back to direct connection.")
        return mysql.connector.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME']
        )


@contextmanager
def db_cursor(dictionary=False, commit=False):
    """Yield a cursor with guaranteed cleanup — replaces the fragile
    ``finally: if 'conn' in locals() and conn.is_connected(): cursor.close()`` idiom
    (which NameErrors if ``conn.cursor()`` itself raises). Commits on clean exit when
    ``commit=True``, rolls back on exception, and always closes cursor + connection.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=dictionary)
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None and conn.is_connected():
            conn.close()

def init_db(app):
    """Runs when the webserver boots to build all TaLi tables automatically."""
    try:
        conn = mysql.connector.connect(
            host=app.config['DB_HOST'],
            user=app.config['DB_USER'],
            password=app.config['DB_PASSWORD'],
            database=app.config['DB_NAME']
        )
        cursor = conn.cursor()

        # --- USERS & AUTHENTICATION ---

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id BINARY(16) PRIMARY KEY,
                phone_number VARCHAR(20) UNIQUE NOT NULL,
                display_name VARCHAR(100) NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Check if base_currency column exists in users table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = 'base_currency'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE users ADD COLUMN base_currency VARCHAR(3) DEFAULT 'NGN'")
            print("Added base_currency column to users table.")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whatsapp_accounts (
                sender_id VARCHAR(50) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_codes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL,
                code VARCHAR(6) NOT NULL,
                token VARCHAR(100) UNIQUE NULL,
                purpose ENUM('registration', 'login') NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_phone_purpose (phone_number, purpose),
                INDEX idx_token (token)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id BINARY(16) PRIMARY KEY,
                sender_id VARCHAR(50) NOT NULL,
                user_id BINARY(16) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                status ENUM('PENDING', 'ACTIVE', 'EXPIRED') DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_sender_active (sender_id, is_active),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # --- BOOKKEEPING ---

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BINARY(16) NULL,
                name VARCHAR(100) NOT NULL,
                type ENUM('income', 'expense', 'both') NOT NULL DEFAULT 'both',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                category_id INT NULL,
                type ENUM('income', 'expense') NOT NULL,
                action VARCHAR(20) NOT NULL DEFAULT 'other',
                amount DECIMAL(15, 2) NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'NGN',
                item VARCHAR(255) NULL,
                description VARCHAR(255) NULL,
                raw_text VARCHAR(500) NOT NULL,
                transaction_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
                INDEX idx_user_date (user_id, transaction_date),
                INDEX idx_user_category (user_id, category_id),
                INDEX idx_user_type (user_id, type),
                INDEX idx_user_action (user_id, action)
            )
        ''')

        # Check if currency column exists in transactions table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'transactions' AND COLUMN_NAME = 'currency'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE transactions ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'NGN'")
            print("Added currency column to transactions table.")

        # Check if currency_code column exists in transactions table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'transactions' AND COLUMN_NAME = 'currency_code'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE transactions ADD COLUMN currency_code VARCHAR(3) DEFAULT 'NGN'")
            print("Added currency_code column to transactions table.")

        # Keep legacy records table for backward compatibility
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id BINARY(16) PRIMARY KEY,
                sender_id VARCHAR(50) NOT NULL,
                raw_text VARCHAR(255) NOT NULL,
                amount INT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # --- INVENTORY TRACKING ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                name VARCHAR(100) NOT NULL,
                quantity DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
                unit VARCHAR(50) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY idx_user_product (user_id, name)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_movements (
                id BINARY(16) PRIMARY KEY,
                product_id BINARY(16) NOT NULL,
                user_id BINARY(16) NOT NULL,
                movement_type ENUM('in', 'out', 'set') NOT NULL,
                quantity DECIMAL(12, 2) NOT NULL,
                description VARCHAR(255) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # --- DEBT TRACKING ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debt_balances (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                person_name VARCHAR(100) NOT NULL,
                debt_type ENUM('receivable', 'payable') NOT NULL,
                outstanding_balance DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
                currency VARCHAR(10) NOT NULL DEFAULT 'NGN',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY idx_user_person_currency (user_id, person_name, currency)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debt_logs (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                person_name VARCHAR(100) NOT NULL,
                debt_type ENUM('receivable', 'payable') NOT NULL,
                action ENUM('add_debt', 'repayment', 'full_payment') NOT NULL,
                amount DECIMAL(15, 2) NOT NULL,
                previous_balance DECIMAL(15, 2) NOT NULL,
                new_balance DECIMAL(15, 2) NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'NGN',
                raw_text VARCHAR(500) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # --- IDEMPOTENCY & REVIEW QUEUE ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id VARCHAR(100) PRIMARY KEY,
                sender_id VARCHAR(50) NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id VARCHAR(100) NOT NULL,
                agent_name VARCHAR(50) NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, agent_name)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS review_queue (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                raw_text VARCHAR(500) NOT NULL,
                parsed_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # Pending confirmations — a parsed write awaiting the user's YES/NO.
        # One row per sender (UNIQUE), replaced on each new pending entry.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                sender_id VARCHAR(50) NOT NULL UNIQUE,
                raw_text VARCHAR(500) NOT NULL,
                parsed_json JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # --- WEBHOOK EVENTS & AI LOGS ---
        # Migrating webhook_events
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'webhook_events' AND COLUMN_NAME = 'whatsapp_message_id'
        """, (app.config['DB_NAME'],))
        col_check = cursor.fetchone()
        if col_check and col_check[0] == 0:
            try:
                cursor.execute("RENAME TABLE webhook_events TO webhook_events_legacy")
                print("Renamed legacy webhook_events to webhook_events_legacy.")
            except Error as err:
                print(f"Failed to rename webhook_events: {err}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS webhook_events (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                whatsapp_message_id VARCHAR(100) UNIQUE NOT NULL,
                sender_id VARCHAR(50) NOT NULL,
                payload JSON,
                status ENUM('received', 'processing', 'processed', 'failed') DEFAULT 'received',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP NULL
            )
        ''')

        # Migrating ai_logs
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'ai_logs' AND COLUMN_NAME = 'model_name'
        """, (app.config['DB_NAME'],))
        ai_col_check = cursor.fetchone()
        if ai_col_check and ai_col_check[0] == 0:
            try:
                cursor.execute("RENAME TABLE ai_logs TO ai_logs_legacy")
                print("Renamed legacy ai_logs to ai_logs_legacy.")
            except Error as err:
                print(f"Failed to rename ai_logs: {err}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BINARY(16) NULL,
                model_name VARCHAR(50),
                original_message TEXT,
                parsed_intent VARCHAR(100),
                parsed_json JSON,
                confidence_score DECIMAL(5,4),
                estimated_cost DECIMAL(12,6),
                processing_time_ms INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')

        # --- STANDARDIZED INVENTORY ---
        # Migrating inventory_items
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'inventory_items' AND COLUMN_NAME = 'item_name'
        """, (app.config['DB_NAME'],))
        inv_col_check = cursor.fetchone()
        if inv_col_check and inv_col_check[0] == 0:
            try:
                cursor.execute("RENAME TABLE inventory_movements TO inventory_movements_legacy")
                cursor.execute("RENAME TABLE inventory_items TO inventory_items_legacy")
                print("Renamed legacy inventory tables.")
            except Error as err:
                print(f"Failed to rename inventory tables: {err}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_items (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                item_name VARCHAR(150) NOT NULL,
                unit VARCHAR(50),
                minimum_stock_level DECIMAL(15,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_movements (
                id BINARY(16) PRIMARY KEY,
                inventory_item_id BINARY(16) NOT NULL,
                user_id BINARY(16) NOT NULL,
                movement_type ENUM('stock_in', 'stock_out', 'adjustment') NOT NULL,
                quantity DECIMAL(15,2) NOT NULL,
                reference_transaction_id BINARY(16) NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (reference_transaction_id) REFERENCES transactions(id) ON DELETE SET NULL
            )
        ''')

        # --- MESSAGE AUDITING ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BINARY(16) NULL,
                sender_id VARCHAR(50),
                direction ENUM('incoming', 'outgoing') NOT NULL,
                message_text TEXT,
                whatsapp_message_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # --- DEBT ENTRIES (DOUBLE ENTRY STRICTNESS) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS debt_entries (
                id BINARY(16) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                person_name VARCHAR(100) NOT NULL,
                type ENUM('receivable', 'payable') NOT NULL,
                amount DECIMAL(15, 2) NOT NULL,
                currency VARCHAR(10) NOT NULL DEFAULT 'NGN',
                raw_text VARCHAR(500) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_person (user_id, person_name)
            )
        ''')

        # Check if alert_thresholds column exists in users table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = 'alert_thresholds'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE users ADD COLUMN alert_thresholds JSON NULL")
            print("Added alert_thresholds column to users table.")

        # Seed default thresholds for users who have it NULL
        cursor.execute(
            "UPDATE users SET alert_thresholds = %s WHERE alert_thresholds IS NULL",
            ('{"low_stock_limit": 5, "high_debt_limit": 50000, "large_expense_flag": 100000}',)
        )

        # Settings & onboarding columns (migration 0003). Added idempotently here
        # too so the live DB self-heals on boot — the app provisions via init_db,
        # and the ORM model selects these columns (missing them raises 1054).
        for col, ddl in (
            ("usage_type", "ALTER TABLE users ADD COLUMN usage_type ENUM('personal','business') NULL"),
            ("business_profile", "ALTER TABLE users ADD COLUMN business_profile JSON NULL"),
            ("onboarding_step", "ALTER TABLE users ADD COLUMN onboarding_step SMALLINT NULL"),
        ):
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users' AND COLUMN_NAME = %s
            """, (app.config['DB_NAME'], col))
            if cursor.fetchone()[0] == 0:
                cursor.execute(ddl)
                print(f"Added {col} column to users table.")

        # Check if status column exists in sessions table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'sessions' AND COLUMN_NAME = 'status'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE sessions ADD COLUMN status ENUM('PENDING', 'ACTIVE', 'EXPIRED') DEFAULT 'ACTIVE'")
            print("Added status column to sessions table.")

        # --- MIGRATIONS FOR BUSINESS_ID & MULTI-TENANCY ---
        tables_to_migrate = ['users', 'transactions', 'inventory_items', 'inventory_movements', 'debt_balances', 'debt_logs', 'debt_entries', 'ai_logs']
        for table in tables_to_migrate:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = 'business_id'
            """, (app.config['DB_NAME'], table))
            if cursor.fetchone()[0] == 0:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN business_id INT DEFAULT 1")
                print(f"Added business_id column to {table} table.")

        # Check if source_agent column exists in ai_logs table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'ai_logs' AND COLUMN_NAME = 'source_agent'
        """, (app.config['DB_NAME'],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE ai_logs ADD COLUMN source_agent VARCHAR(50) DEFAULT 'IntakeAgent'")
            print("Added source_agent column to ai_logs table.")
        # --- MIGRATIONS FOR UNIQUE EVENT_ID IDEMPOTENCY ---
        event_id_tables = ['transactions', 'inventory_movements', 'debt_entries', 'stock_movements', 'debt_logs']
        for table in event_id_tables:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = 'event_id'
            """, (app.config['DB_NAME'], table))
            if cursor.fetchone()[0] == 0:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN event_id VARCHAR(100) NULL")
                    cursor.execute(f"ALTER TABLE {table} ADD UNIQUE KEY idx_event_id_uni_{table} (event_id)")
                    print(f"Added unique event_id column to {table} table.")
                except Error as err:
                    print(f"Failed to add event_id column to {table}: {err}")

        # --- SEED DEFAULT CATEGORIES ---
        cursor.execute("SELECT id, name FROM categories WHERE user_id IS NULL")
        existing_defaults = cursor.fetchall()
        name_to_id = {row[1]: row[0] for row in existing_defaults} if existing_defaults else {}

        target_categories = {
            'Food': 'expense',
            'Transport': 'expense',
            'Fuel': 'expense',
            'Rent': 'expense',
            'Utilities': 'expense',
            'Shopping': 'expense',
            'Salary': 'income',
            'Business': 'income',
            'Freelance': 'income',
            'Gift': 'both',
            'Other': 'both'
        }

        # Ensure 'Other' exists first for fallback mapping
        other_id = name_to_id.get('Other')
        if not other_id:
            cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (NULL, 'Other', 'both')")
            other_id = cursor.lastrowid
            name_to_id['Other'] = other_id

        # Update or insert categories
        for name, cat_type in target_categories.items():
            if name in name_to_id:
                cursor.execute("UPDATE categories SET type = %s WHERE name = %s AND user_id IS NULL", (cat_type, name))
            else:
                cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (NULL, %s, %s)", (name, cat_type))
                print(f"Seeded category '{name}' ({cat_type}).")

        # Delete old default categories that are not in target_categories
        old_defaults_to_delete = [name for name in name_to_id if name not in target_categories]
        if old_defaults_to_delete:
            old_ids = [name_to_id[name] for name in old_defaults_to_delete]
            format_strings = ','.join(['%s'] * len(old_ids))
            cursor.execute(
                f"UPDATE transactions SET category_id = %s WHERE category_id IN ({format_strings})",
                tuple([other_id] + old_ids)
            )
            cursor.execute(
                f"DELETE FROM categories WHERE id IN ({format_strings})",
                tuple(old_ids)
            )
            print(f"Cleaned up legacy categories: {old_defaults_to_delete}")

        # --- PRODUCTION HARDENING TABLES ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_requests (
                idempotency_key VARCHAR(100) PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS background_jobs (
                id VARCHAR(50) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                sender_id VARCHAR(50) NOT NULL,
                text TEXT NOT NULL,
                message_id VARCHAR(100) NULL,
                status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transaction_state (
                event_id VARCHAR(100) PRIMARY KEY,
                user_id BINARY(16) NOT NULL,
                state ENUM('RECEIVED', 'PENDING_CONFIRMATION', 'CONFIRMED', 'PROCESSING_LEDGER', 'COMPLETED', 'FAILED') NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_deliveries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sender_id VARCHAR(50) NOT NULL,
                message_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        print("MySQL Tables Initialized successfully.")

        # The channel-identity tables (channel_accounts, binding_tokens) are introduced
        # by Alembic migration 0005 and are NOT in the raw CREATE TABLE block above. Create
        # them idempotently from the ORM here so a deploy that hasn't run `alembic upgrade
        # head` still has the multi-channel link feature working (without these,
        # issue_binding_token / redeem fail silently → "Couldn't create a link").
        try:
            from app.data.db import Base, get_engine
            import app.data.models as _models
            Base.metadata.create_all(
                bind=get_engine(),
                tables=[_models.ChannelAccount.__table__, _models.BindingToken.__table__],
                checkfirst=True,
            )
            print("Channel-identity tables ensured (channel_accounts, binding_tokens).")
        except Exception as ce:
            print(f"Could not ensure channel-identity tables: {ce}")
    except Error as e:
        print(f"MySQL Table Initialization failed: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def set_transaction_state(event_id, user_id, state):
    """Update the transaction state machine (Saga Pattern) atomically in the DB."""
    try:
        from app.services.uuid_utils import uuid_to_bin
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transaction_state (event_id, user_id, state) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE state = VALUES(state)",
            (str(event_id), uuid_to_bin(user_id), state)
        )
        conn.commit()
    except Exception as e:
        print(f"Error setting transaction state: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
