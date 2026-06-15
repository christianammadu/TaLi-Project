"""Snapshot Agent — compiles month-to-date business health metrics.

Aggregates cash flow, total outstanding receivables/payables, and lists low-stock products.
"""

from datetime import date
from decimal import Decimal
from mysql.connector import Error
from app.data.database import get_db_connection, db_cursor


def _naira(v):
    v = float(v)
    return f"-₦{abs(v):,.0f}" if v < 0 else f"₦{v:,.0f}"


def format_snapshot(cash_in, cash_out, profit, customer_debt, supplier_debt, low_stock_items, status):
    """Render the snapshot as a human-readable chat message (never raw JSON)."""
    status_emoji = {"Healthy": "🟢", "Warning": "🟡", "Unhealthy": "🔴"}.get(status, "")
    trend = "📈" if float(profit) >= 0 else "📉"
    lines = [
        f"📊 Business Health: {status} {status_emoji}".rstrip(),
        "",
        "This month",
        f"• Money in: {_naira(cash_in)}",
        f"• Money out: {_naira(cash_out)}",
        f"• Profit: {_naira(profit)} {trend}",
        "",
        f"• Owed to you: {_naira(customer_debt)}",
        f"• You owe: {_naira(supplier_debt)}",
    ]
    lines.append(
        f"⚠️ Low stock: {', '.join(low_stock_items)}" if low_stock_items
        else "✅ Stock levels look fine"
    )
    return "\n".join(lines)


class SnapshotAgent:
    """Agent responsible for querying business health snaps from ledger, debt, and stock databases."""

    def __init__(self, user_id):
        self.user_id = user_id
        # NULL until provisioned into a business — never default to a shared
        # constant, which would leak transactions across unrelated users.
        self.business_id = None
        from app.services.uuid_utils import uuid_to_bin
        try:
            with db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT business_id FROM users WHERE id = %s LIMIT 1", (uuid_to_bin(user_id),))
                row = cursor.fetchone()
                if row and row['business_id'] is not None:
                    self.business_id = row['business_id']
        except Exception as e:
            print(f"Error fetching business_id for SnapshotAgent: {e}")

    def _scope(self, col="business_id"):
        """Return (sql_fragment, value): business-scoped when provisioned, else
        user-scoped — avoids cross-tenant leaks and empty results when NULL."""
        if self.business_id is not None:
            return f"{col} = %s", self.business_id
        from app.services.uuid_utils import uuid_to_bin
        return f"{col.replace('business_id', 'user_id')} = %s", uuid_to_bin(self.user_id)

    def generate_snapshot(self):
        """Aggregate monthly cash flow, outstanding debts, and low stock to produce a status health snap.

        Returns:
            str: JSON health snapshot response.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Get calendar month range bounds
            today = date.today()
            start_date = date(today.year, today.month, 1)

            if today.month == 12:
                end_date = date(today.year, 12, 31)
            else:
                from datetime import timedelta
                next_month = date(today.year, today.month + 1, 1)
                end_date = next_month - timedelta(days=1)

            # 1. Month-to-date income and expense
            from app.services.uuid_utils import uuid_to_bin
            scope_col, scope_val = (
                ("business_id", self.business_id) if self.business_id is not None
                else ("user_id", uuid_to_bin(self.user_id))
            )
            cursor.execute(
                "SELECT type, COALESCE(SUM(amount), 0) as total FROM transactions "
                f"WHERE {scope_col} = %s AND transaction_date BETWEEN %s AND %s "
                "GROUP BY type",
                (scope_val, start_date, end_date)
            )
            tx_rows = cursor.fetchall()
            cash_in = Decimal('0.00')
            cash_out = Decimal('0.00')
            for r in tx_rows:
                if r['type'] == 'income':
                    cash_in = Decimal(str(r['total']))
                elif r['type'] == 'expense':
                    cash_out = Decimal(str(r['total']))

            # 2. Outstanding debt balances (Accounts Receivable and Payable)
            clause, val = self._scope()
            cursor.execute(
                "SELECT debt_type, COALESCE(SUM(outstanding_balance), 0) as total "
                f"FROM debt_balances WHERE {clause} "
                "GROUP BY debt_type",
                (val,)
            )
            debt_rows = cursor.fetchall()
            customer_debt = Decimal('0.00')
            supplier_debt = Decimal('0.00')
            for r in debt_rows:
                if r['debt_type'] == 'receivable':
                    customer_debt = Decimal(str(r['total']))
                elif r['debt_type'] == 'payable':
                    supplier_debt = Decimal(str(r['total']))

            # 3. Products with stock levels <= 5
            clause_inv, val_inv = self._scope("i.business_id")
            cursor.execute(
                "SELECT i.item_name, COALESCE(SUM(CASE "
                "  WHEN im.movement_type = 'stock_in' THEN im.quantity "
                "  WHEN im.movement_type = 'stock_out' THEN -im.quantity "
                "  WHEN im.movement_type = 'adjustment' THEN im.quantity "
                "  ELSE 0 "
                "END), 0) as current_stock "
                "FROM inventory_items i "
                "LEFT JOIN inventory_movements im ON i.id = im.inventory_item_id "
                f"WHERE {clause_inv} "
                "GROUP BY i.id, i.item_name "
                "HAVING current_stock <= 5",
                (val_inv,)
            )
            stock_rows = cursor.fetchall()
            low_stock_items = [r['item_name'] for r in stock_rows]

            # 4. Profitability and status classification
            profit = cash_in - cash_out
            if profit < 0:
                status = "Unhealthy"
            elif customer_debt > (profit * Decimal('0.50')) and profit > 0:
                status = "Warning"
            else:
                status = "Healthy"

            return format_snapshot(cash_in, cash_out, profit, customer_debt,
                                   supplier_debt, low_stock_items, status)

        except Error as e:
            print(f"Database error in SnapshotAgent: {e}")
            return "⚠️ I couldn't compile your business snapshot right now. Please try again shortly."
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
