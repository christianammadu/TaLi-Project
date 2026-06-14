"""Transaction Agent — handles transaction recording and financial queries.

Focuses strictly on transaction processing logic, validators, database writes, and query formatting.
"""

from datetime import date
from app.services.validators import validate_transaction, validate_query
from app.data.queries import record_transaction, query_sum, query_list, query_balance
from app.services.formatter import (
    format_transaction_saved,
    format_sum_query,
    format_list_query,
    format_balance,
)
from app.services.utils import parse_shorthand


class TransactionAgent:
    """Processes WhatsApp transaction records and queries."""

    def __init__(self, user_id, sender_id):
        self.user_id = user_id
        self.sender_id = sender_id

    def process(self, text, parsed=None):
        """Processes transaction requests.

        ``parsed`` is supplied by the Ledger when routing a query. The old
        ``AgentRouter`` re-entry fallback was retired in WP-06 (G-09): the Band gateway
        is the single entry point now, so re-routing here would recurse through the room.
        """
        if parsed is None:
            return ("🤔 I couldn't read that as a transaction. Try e.g. "
                    "\"Sold rice 5000\" or \"Bought fuel 2k\".")

        intent = parsed.get('intent')
        if intent == 'record_transaction':
            return self._handle_record(text, parsed)
        elif intent == 'query':
            return self._handle_query(parsed)
        else:
            return "❌ Invalid transaction intent."

    def process_fast_path(self, text):
        """Process pure shorthand fast path."""
        text_stripped = text.strip()
        amount = parse_shorthand(text)
        if amount > 0:
            quick_parsed = {
                'type': 'expense',
                'action': 'expense',
                'amount': amount,
                'currency': 'NGN',
                'item': None,
                'category': 'Miscellaneous',
                'description': text_stripped,
                'date': date.today().isoformat(),
            }
            result = record_transaction(
                self.user_id, self.sender_id, text, quick_parsed
            )
            if result:
                return format_transaction_saved(result)
        return "❌ Failed to save. Please try again."

    def _handle_record(self, raw_text, parsed):
        """Validate and record a transaction."""
        # Validate
        is_valid, result = validate_transaction(parsed)
        if not is_valid:
            return (
                f"❌ *Validation Error*\n\n{result}\n\n"
                "Please try again with a valid transaction, e.g.:\n"
                "• \"Sold rice 5000\"\n"
                "• \"Bought fuel 2k\""
            )

        # Check amount is present
        amount = result.get('amount', 0)
        if not amount or amount <= 0:
            return (
                "❓ I understood the transaction but couldn't find an amount.\n\n"
                "Try again with a clear amount, e.g.:\n"
                "• \"Bought fuel 2000\"\n"
                "• \"Sold rice 5k\""
            )

        # Record
        db_result = record_transaction(
            self.user_id, self.sender_id, raw_text, result
        )

        if db_result:
            return format_transaction_saved(db_result)
        else:
            return "❌ Failed to save the transaction. Please try again."

    def _handle_query(self, parsed):
        """Validate and execute a financial query."""
        is_valid, cleaned = validate_query(parsed)
        if not is_valid:
            return f"❌ Invalid query: {cleaned}"

        query_type = cleaned.get('query_type', 'sum')

        if query_type == 'balance':
            result = query_balance(self.user_id)
            if result:
                return format_balance(result)
            return "❌ Couldn't retrieve your balance. Please try again."

        elif query_type == 'list':
            items = query_list(self.user_id, cleaned)
            if items is not None:
                return format_list_query(items, cleaned)
            return "❌ Couldn't retrieve transactions. Please try again."

        elif query_type in ('sum', 'count'):
            result = query_sum(self.user_id, cleaned)
            if result:
                return format_sum_query(result)
            return "❌ Couldn't calculate the total. Please try again."

        else:
            result = query_sum(self.user_id, cleaned)
            if result:
                return format_sum_query(result)
            return "❌ Couldn't process your query. Please try again."
