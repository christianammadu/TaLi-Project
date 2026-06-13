"""Inventory Agent — tracks products, stock levels, and movements from user messages.

Calculates stock updates (ADD, REMOVE, SET) and returns structured JSON responses.
"""

import json
from decimal import Decimal
from mysql.connector import Error
from app.data.database import get_db_connection


class InventoryAgent:
    """Agent responsible for tracking products, quantities, and stock movements."""

    def __init__(self, user_id):
        self.user_id = user_id

    def process(self, text, parsed):
        """Process an inventory message and return a structured JSON response.

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
                "question": parsed.get('question', "Please clarify the details of the inventory update.")
            }, indent=2)

        # 2. Check for required fields
        product = parsed.get('product')
        if not product:
            return json.dumps({
                "status": "clarification_needed",
                "question": "What product is this inventory update for?"
            }, indent=2)

        quantity_val = parsed.get('quantity')
        if quantity_val is None:
            # Generate contextual question
            action_verb = "sold" if parsed.get('action') == 'REMOVE' else "added"
            unit_str = f" of {product}"
            if parsed.get('unit'):
                unit_str = f" {parsed.get('unit')} of {product}"
            return json.dumps({
                "status": "clarification_needed",
                "question": f"How many{unit_str} were {action_verb}?"
            }, indent=2)

        try:
            quantity = Decimal(str(quantity_val))
        except (ValueError, TypeError):
            return json.dumps({
                "status": "clarification_needed",
                "question": f"Please provide a valid number for the quantity of {product}."
            }, indent=2)

        unit = parsed.get('unit')
        action = parsed.get('action', 'ADD').upper()

        # Connect to DB and fetch product stock details
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            from app.services.uuid_utils import uuid_to_bin, uuid7
            user_id_bin = uuid_to_bin(self.user_id)

            # Get current product stock
            cursor.execute(
                "SELECT id, quantity, unit FROM products "
                "WHERE user_id = %s AND name = %s LIMIT 1",
                (user_id_bin, product)
            )
            prod_row = cursor.fetchone()

            current_stock = Decimal('0.00')
            prod_id = None
            db_unit = unit

            if prod_row:
                prod_id = prod_row['id']
                current_stock = Decimal(str(prod_row['quantity']))
                db_unit = prod_row['unit'] if prod_row['unit'] else unit

            # If unit is specified in the message, we can use it to update/set the unit
            if unit:
                db_unit = unit

            # Process stock logic based on action
            if action == 'ADD':
                new_stock = current_stock + quantity
            elif action == 'REMOVE':
                new_stock = current_stock - quantity
                # Prevent negative stock
                if new_stock < 0:
                    cursor.close()
                    conn.close()
                    unit_label = db_unit if db_unit else "units"
                    return json.dumps({
                        "status": "clarification_needed",
                        "question": f"Insufficient stock! You only have {float(current_stock):.0f} {unit_label} of {product} in stock. How many did you sell/use?"
                    }, indent=2)
            elif action == 'SET':
                new_stock = quantity
            else:
                new_stock = current_stock

            # Update database
            if prod_row:
                cursor.execute(
                    "UPDATE products SET quantity = %s, unit = %s WHERE id = %s",
                    (new_stock, db_unit, prod_id)
                )
            else:
                prod_uuid = uuid7()
                cursor.execute(
                    "INSERT INTO products (id, user_id, name, quantity, unit) VALUES (%s, %s, %s, %s, %s)",
                    (prod_uuid.bytes, user_id_bin, product, new_stock, db_unit)
                )
                prod_id = prod_uuid.bytes

            # Log stock movement
            db_action = 'in' if action == 'ADD' else ('out' if action == 'REMOVE' else 'set')
            mov_uuid = uuid7()
            cursor.execute(
                "INSERT INTO stock_movements (id, product_id, user_id, movement_type, quantity, description) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (mov_uuid.bytes, prod_id, user_id_bin, db_action, quantity, text)
            )

            conn.commit()

            return json.dumps({
                "product": product,
                "action": action,
                "quantity": float(quantity),
                "unit": db_unit,
                "new_stock": float(new_stock)
            }, indent=2)

        except Error as e:
            print(f"Database error in InventoryAgent: {e}")
            return json.dumps({
                "status": "error",
                "message": "A database error occurred while updating inventory."
            }, indent=2)
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
