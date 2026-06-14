"""Reporting Agent — generates daily, weekly, and monthly business summaries.

Calculates aggregates (Income, Expenses, Profit, Debts, Top Selling Product)
and returns a refined WhatsApp text report (never raw JSON).
"""

from datetime import date, datetime, timedelta
from mysql.connector import Error
from app.data.database import get_db_connection, db_cursor
from app.services.formatter import format_period_report


def format_router_spend(report):
    """Render the model router's live per-provider/model session spend as WhatsApp text (WP-10)."""
    if not report or not report.get("rows"):
        return "*Live session spend (this run):* none yet."
    lines = ["*Live session spend by provider (this run):*"]
    for provider, agg in sorted(report.get("by_provider", {}).items()):
        lines.append(f"• *{provider}*: ${agg['cost']:.5f} ({agg['calls']} calls)")
    lines.append("_by model:_")
    for r in report["rows"]:
        lines.append(f"   – {r['provider']}/{r['model']}: ${r['cost']:.5f} ({r['calls']} calls)")
    lines.append(f"*Session total:* ${report['total_cost']:.5f} across {report['total_calls']} calls")
    return "\n".join(lines)


class ReportingAgent:
    """Agent responsible for compiling and formatting transaction summaries."""

    def __init__(self, user_id):
        self.user_id = user_id
        # NULL until the user is explicitly provisioned into a business — never
        # default to a shared constant, which would leak data across users.
        self.business_id = None
        from app.services.uuid_utils import uuid_to_bin
        try:
            with db_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT business_id FROM users WHERE id = %s LIMIT 1", (uuid_to_bin(user_id),))
                row = cursor.fetchone()
                if row and row['business_id'] is not None:
                    self.business_id = row['business_id']
        except Exception as e:
            print(f"Error fetching business_id for ReportingAgent: {e}")

    def _scope(self, col="business_id"):
        """Return (sql_fragment, value) scoping a read to the user's business when
        provisioned, else strictly to the user (no shared-business leak, and no
        empty results once business_id is NULL). ``col`` may be table-qualified."""
        if self.business_id is not None:
            return f"{col} = %s", self.business_id
        from app.services.uuid_utils import uuid_to_bin
        return f"{col.replace('business_id', 'user_id')} = %s", uuid_to_bin(self.user_id)

    def generate_report(self, period, date_str=None):
        """Compile a report for the given period (daily, weekly, monthly) and date.

        Args:
            period: str, one of 'daily', 'weekly', 'monthly'.
            date_str: str, target date in 'YYYY-MM-DD' format (optional, defaults to today).

        Returns:
            str: formatted WhatsApp text report.
        """
        # Validate period
        if not period or period not in ('daily', 'weekly', 'monthly'):
            return "🤔 Which period — *daily*, *weekly*, or *monthly*?"

        # Parse target date
        target_date = date.today()
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass  # bad date from NLP — fall back to today rather than fail

        # Calculate bounds
        if period == 'daily':
            start_date = target_date
            end_date = target_date
        elif period == 'weekly':
            # Last 7 days including today (as per simplified weekly report requirement)
            start_date = target_date - timedelta(days=6)
            end_date = target_date
        else:  # monthly
            # Current month (from 1st of the month to last day of target month)
            start_date = date(target_date.year, target_date.month, 1)
            if target_date.month == 12:
                end_date = date(target_date.year, 12, 31)
            else:
                next_month = date(target_date.year, target_date.month + 1, 1)
                end_date = next_month - timedelta(days=1)

        # Query aggregates grouped by currency and type
        data = self._query_aggregates(start_date, end_date)
        if data is None:
            return "❌ Couldn't pull your numbers right now. Please try again shortly."

        # Query debt metrics and top selling product
        customer_debt, supplier_debt = self._query_debt_balances()
        top_selling = self._query_top_selling_product()

        # Organize data by currency
        currency_data = {}
        for row in data:
            currency = row['currency']
            tx_type = row['type']
            total = float(row['total'])

            if currency not in currency_data:
                currency_data[currency] = {'income': 0.0, 'expenses': 0.0}

            if tx_type == 'income':
                currency_data[currency]['income'] = total
            elif tx_type == 'expense':
                currency_data[currency]['expenses'] = total

        if start_date == end_date:
            range_label = start_date.strftime('%b %d, %Y')
        else:
            range_label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')}"

        return format_period_report({
            'period_label': f"{period.capitalize()} Report — {range_label}",
            'per_currency': currency_data,
            'customer_debt': customer_debt,
            'supplier_debt': supplier_debt,
            'top_selling_product': top_selling,
        })

    def _query_aggregates(self, start_date, end_date):
        """Fetch sums of income and expenses in the date range grouped by currency."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            from app.services.uuid_utils import uuid_to_bin
            scope_col, scope_val = (
                ("business_id", self.business_id) if self.business_id is not None
                else ("user_id", uuid_to_bin(self.user_id))
            )
            cursor.execute(
                "SELECT currency, type, COALESCE(SUM(amount), 0) as total "
                "FROM transactions "
                f"WHERE {scope_col} = %s AND transaction_date BETWEEN %s AND %s "
                "GROUP BY currency, type",
                (scope_val, start_date, end_date)
            )
            rows = cursor.fetchall()
            return rows
        except Error as e:
            print(f"Error querying aggregates for report: {e}")
            return None
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _query_debt_balances(self):
        """Fetch outstanding customer receivables and supplier payables."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            clause, val = self._scope()
            cursor.execute(
                "SELECT debt_type, COALESCE(SUM(outstanding_balance), 0) as total "
                f"FROM debt_balances WHERE {clause} "
                "GROUP BY debt_type",
                (val,)
            )
            rows = cursor.fetchall()
            customer_debt = 0.0
            supplier_debt = 0.0
            for row in rows:
                if row['debt_type'] == 'receivable':
                    customer_debt = float(row['total'])
                elif row['debt_type'] == 'payable':
                    supplier_debt = float(row['total'])
            return customer_debt, supplier_debt
        except Error as e:
            print(f"Error querying debts for report: {e}")
            return 0.0, 0.0
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def _query_top_selling_product(self):
        """Identify the product with the highest quantity sold in stock movements or sales."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Check stock movements first
            clause, val = self._scope("im.business_id")
            cursor.execute(
                "SELECT i.item_name, SUM(im.quantity) as total_qty "
                "FROM inventory_movements im "
                "JOIN inventory_items i ON im.inventory_item_id = i.id "
                f"WHERE {clause} AND im.movement_type = 'stock_out' "
                "GROUP BY i.item_name "
                "ORDER BY total_qty DESC LIMIT 1",
                (val,)
            )
            row = cursor.fetchone()
            if row:
                return row['item_name']

            # Fallback to transactions items if no inventory movements are logged
            clause, val = self._scope()
            cursor.execute(
                "SELECT item, COUNT(*) as count FROM transactions "
                f"WHERE {clause} AND type = 'income' AND action = 'sale' AND item IS NOT NULL "
                "GROUP BY item ORDER BY count DESC LIMIT 1",
                (val,)
            )
            row_tx = cursor.fetchone()
            if row_tx:
                return row_tx['item']

            return "None"
        except Error as e:
            print(f"Error querying top selling product: {e}")
            return "None"
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    def generate_finops_report(self):
        """Compile a breakdown of OpenAI API usage costs grouped by agent and intent type."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            clause, val = self._scope()
            cursor.execute(
                "SELECT COUNT(*) as total_calls, "
                "COALESCE(SUM(estimated_cost), 0) as total_cost, "
                "COALESCE(AVG(processing_time_ms), 0) as avg_latency "
                f"FROM ai_logs WHERE {clause}",
                (val,)
            )
            stats = cursor.fetchone()
            total_calls = stats['total_calls'] if stats else 0
            total_cost = float(stats['total_cost']) if stats else 0.0
            avg_latency = float(stats['avg_latency']) if stats else 0.0

            clause, val = self._scope()
            cursor.execute(
                "SELECT source_agent, parsed_intent, COUNT(*) as calls, "
                "COALESCE(SUM(estimated_cost), 0) as cost "
                f"FROM ai_logs WHERE {clause} "
                "GROUP BY source_agent, parsed_intent "
                "ORDER BY cost DESC",
                (val,)
            )
            rows = cursor.fetchall()

            breakdown_lines = []
            for r in rows:
                agent = r['source_agent']
                intent = r['parsed_intent']
                calls = r['calls']
                cost = float(r['cost'])
                breakdown_lines.append(f"• *{intent}* ({agent}): ${cost:.5f} ({calls} calls)")

            breakdown_str = "\n".join(breakdown_lines) if breakdown_lines else "• No API usage logged yet."

            report = (
                f"📊 *FinOps API Billing & Cost Report*\n"
                f"---------------------------------\n"
                f"• *Total API Calls:* {total_calls}\n"
                f"• *Total API Spend:* ${total_cost:.5f}\n"
                f"• *Avg Model Latency:* {int(avg_latency)}ms\n\n"
                f"*Spend by Feature/Intent (logged):*\n"
                f"{breakdown_str}"
            )
            # Append the model router's live per-provider/model spend for this run (WP-10).
            from app.services import model_router
            report += "\n\n" + format_router_spend(model_router.spend_report())
            return report

        except Error as e:
            print(f"Error generating FinOps report: {e}")
            return "❌ Failed to compile FinOps cost report."
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
