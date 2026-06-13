"""Debt Tracking Agent — tracks customer and supplier outstanding balances and logs.

Handles add_debt, repayment, and full_payment actions while maintaining running balances.
"""

import json
from decimal import Decimal
from mysql.connector import Error
from app.data.database import get_db_connection


class DebtAgent:
    """Agent responsible for tracking customer and supplier debts, balances, and logs."""

    def __init__(self, user_id):
        self.user_id = user_id

    def process(self, text, parsed):
        """Process a debt message and return a structured JSON response.

        Args:
            text: str, the original raw WhatsApp message.
            parsed: dict, the parsed fields from the NLP layer.

        Returns:
            str: JSON response representing the update or clarification needed.
        """
        # 1. Handle clarification needed from NLP layer
        if parsed.get('status') == 'clarification_needed':
            return json.dumps({
                "status": "clarification_needed",
                "question": parsed.get('question', "Please clarify the details of the debt transaction.")
            }, indent=2)

        # 2. Check for required name
        raw_name = parsed.get('name')
        if not raw_name:
            return json.dumps({
                "status": "clarification_needed",
                "question": "Who is the customer or supplier for this debt?"
            }, indent=2)

        # Normalize name: lowercase and trim spaces
        name = str(raw_name).lower().strip()

        # Check for required type
        debt_type = parsed.get('type')
        if not debt_type or debt_type not in ('customer_debt', 'supplier_debt'):
            return json.dumps({
                "status": "clarification_needed",
                "question": f"Is {name} a customer (who owes you) or a supplier (whom you owe)?"
            }, indent=2)

        # Map type to internal DB representation
        # customer_debt -> receivable, supplier_debt -> payable
        db_type = 'receivable' if debt_type == 'customer_debt' else 'payable'

        # Check action
        action = parsed.get('action', 'add_debt').lower().strip()
        if action not in ('add_debt', 'repayment', 'full_payment'):
            action = 'add_debt'

        # Currency
        currency = parsed.get('currency', 'NGN')
        if not currency:
            currency = 'NGN'
        currency = str(currency).strip().upper()[:10]

        # Check amount for non-full_payment actions
        amount_val = parsed.get('amount')
        if action != 'full_payment' and amount_val is None:
            action_verb = "paid" if action == 'repayment' else "owes"
            return json.dumps({
                "status": "clarification_needed",
                "question": f"How much money was {action_verb} by {name}?"
            }, indent=2)

        amount = Decimal('0.00')
        if amount_val is not None:
            try:
                # Ensure positive number
                amount = Decimal(str(amount_val))
                if amount < 0:
                    amount = abs(amount)
            except (ValueError, TypeError):
                return json.dumps({
                    "status": "clarification_needed",
                    "question": f"Please provide a valid amount for {name}."
                }, indent=2)

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            from app.services.uuid_utils import uuid_to_bin, uuid7
            user_id_bin = uuid_to_bin(self.user_id)

            # Get current outstanding balance (if any)
            cursor.execute(
                "SELECT id, outstanding_balance, debt_type FROM debt_balances "
                "WHERE user_id = %s AND person_name = %s AND currency = %s LIMIT 1",
                (user_id_bin, name, currency)
            )
            row = cursor.fetchone()

            previous_balance = Decimal('0.00')
            db_row_id = None

            if row:
                previous_balance = Decimal(str(row['outstanding_balance']))
                db_row_id = row['id']
                # Maintain the original type if it exists, or update it
                current_db_type = row['debt_type']
            else:
                current_db_type = db_type

            # Compute new balance based on action
            if action == 'add_debt':
                new_balance = previous_balance + amount
            elif action == 'repayment':
                new_balance = previous_balance - amount
            elif action == 'full_payment':
                # Clear all outstanding balance
                amount = previous_balance  # The amount cleared is the previous balance
                new_balance = Decimal('0.00')
            else:
                new_balance = previous_balance

            # Update or Insert outstanding balance
            if db_row_id:
                cursor.execute(
                    "UPDATE debt_balances SET outstanding_balance = %s, debt_type = %s "
                    "WHERE id = %s",
                    (new_balance, current_db_type, db_row_id)
                )
            else:
                db_uuid = uuid7()
                cursor.execute(
                    "INSERT INTO debt_balances (id, user_id, person_name, debt_type, outstanding_balance, currency) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (db_uuid.bytes, user_id_bin, name, current_db_type, new_balance, currency)
                )

            # Insert into audit log table `debt_logs`
            log_uuid = uuid7()
            cursor.execute(
                "INSERT INTO debt_logs (id, user_id, person_name, debt_type, action, amount, previous_balance, new_balance, currency, raw_text) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (log_uuid.bytes, user_id_bin, name, current_db_type, action, amount, previous_balance, new_balance, currency, text)
            )

            conn.commit()

            # Return JSON format response
            # Format types back to API interface types (customer_debt/supplier_debt)
            api_type = 'customer_debt' if current_db_type == 'receivable' else 'supplier_debt'

            return json.dumps({
                "name": name,
                "type": api_type,
                "action": action,
                "amount": float(amount),
                "previous_balance": float(previous_balance),
                "new_balance": float(new_balance),
                "status": "updated"
            }, indent=2)

        except Error as e:
            print(f"Database error in DebtAgent: {e}")
            return json.dumps({
                "status": "error",
                "message": "A database error occurred while updating debt records."
            }, indent=2)
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
