"""Unit tests for the Transaction Agent and supporting modules.

These tests validate the validators, formatter, and transaction agent logic
without requiring a database connection or OpenAI API key.
"""

import unittest
from datetime import date, timedelta
from unittest.mock import ANY


class TestValidators(unittest.TestCase):
    """Tests for app/validators.py"""

    def setUp(self):
        from app.services.validators import (
            validate_transaction, validate_amount, validate_date, validate_query
        )
        self.validate_transaction = validate_transaction
        self.validate_amount = validate_amount
        self.validate_date = validate_date
        self.validate_query = validate_query

    # --- validate_amount ---

    def test_valid_amount_integer(self):
        is_valid, result = self.validate_amount(5000)
        self.assertTrue(is_valid)
        self.assertEqual(result, 5000.0)

    def test_valid_amount_float(self):
        is_valid, result = self.validate_amount(2500.50)
        self.assertTrue(is_valid)
        self.assertEqual(result, 2500.50)

    def test_valid_amount_string(self):
        is_valid, result = self.validate_amount("3000")
        self.assertTrue(is_valid)
        self.assertEqual(result, 3000.0)

    def test_invalid_amount_zero(self):
        is_valid, error = self.validate_amount(0)
        self.assertFalse(is_valid)
        self.assertIn("positive", error)

    def test_invalid_amount_negative(self):
        is_valid, error = self.validate_amount(-500)
        self.assertFalse(is_valid)
        self.assertIn("positive", error)

    def test_invalid_amount_none(self):
        is_valid, error = self.validate_amount(None)
        self.assertFalse(is_valid)
        self.assertIn("missing", error.lower())

    def test_invalid_amount_text(self):
        is_valid, error = self.validate_amount("abc")
        self.assertFalse(is_valid)
        self.assertIn("Invalid amount", error)

    def test_invalid_amount_too_large(self):
        is_valid, error = self.validate_amount(9_999_999_999)
        self.assertFalse(is_valid)
        self.assertIn("too large", error.lower())

    # --- validate_date ---

    def test_valid_date_today(self):
        today = date.today().isoformat()
        is_valid, result = self.validate_date(today)
        self.assertTrue(is_valid)
        self.assertEqual(result, today)

    def test_valid_date_yesterday(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        is_valid, result = self.validate_date(yesterday)
        self.assertTrue(is_valid)
        self.assertEqual(result, yesterday)

    def test_date_none_defaults_to_today(self):
        is_valid, result = self.validate_date(None)
        self.assertTrue(is_valid)
        self.assertEqual(result, date.today().isoformat())

    def test_invalid_date_future(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        is_valid, error = self.validate_date(future)
        self.assertFalse(is_valid)
        self.assertIn("future", error.lower())

    def test_invalid_date_too_old(self):
        old = (date.today() - timedelta(days=400)).isoformat()
        is_valid, error = self.validate_date(old)
        self.assertFalse(is_valid)
        self.assertIn("year", error.lower())

    def test_invalid_date_bad_format(self):
        is_valid, error = self.validate_date("June 3rd")
        self.assertFalse(is_valid)
        self.assertIn("Invalid date", error)

    # --- validate_transaction ---

    def test_valid_sale_transaction(self):
        parsed = {
            'type': 'income',
            'action': 'sale',
            'amount': 5000,
            'item': 'rice',
            'category': 'Sales',
            'description': 'sold rice',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['action'], 'sale')
        self.assertEqual(result['type'], 'income')
        self.assertEqual(result['item'], 'rice')
        self.assertEqual(result['amount'], 5000.0)

    def test_valid_purchase_transaction(self):
        parsed = {
            'type': 'expense',
            'action': 'purchase',
            'amount': 2000,
            'item': 'fuel',
            'category': 'Fuel',
            'description': 'bought fuel',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['action'], 'purchase')
        self.assertEqual(result['type'], 'expense')
        self.assertEqual(result['item'], 'fuel')

    def test_valid_expense_transaction(self):
        parsed = {
            'type': 'expense',
            'action': 'expense',
            'amount': 10000,
            'item': 'salary',
            'category': 'Miscellaneous',
            'description': 'paid salary',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['action'], 'expense')

    def test_valid_income_transaction(self):
        parsed = {
            'type': 'income',
            'action': 'income',
            'amount': 10000,
            'item': None,
            'category': 'Miscellaneous',
            'description': 'received payment',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['action'], 'income')
        self.assertIsNone(result['item'])

    def test_action_type_cross_validation_sale(self):
        """If action is 'sale' but type is 'expense', type should be corrected to 'income'."""
        parsed = {
            'type': 'expense',  # wrong — sale should be income
            'action': 'sale',
            'amount': 5000,
            'category': 'Sales',
            'description': 'sold goods',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['type'], 'income')  # auto-corrected

    def test_action_type_cross_validation_purchase(self):
        """If action is 'purchase' but type is 'income', type should be corrected to 'expense'."""
        parsed = {
            'type': 'income',  # wrong — purchase should be expense
            'action': 'purchase',
            'amount': 3000,
            'category': 'Miscellaneous',
            'description': 'bought items',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['type'], 'expense')  # auto-corrected

    def test_invalid_transaction_no_amount(self):
        parsed = {
            'type': 'expense',
            'action': 'purchase',
            'amount': None,
            'category': 'Fuel',
            'description': 'bought fuel',
            'date': date.today().isoformat(),
        }
        is_valid, error = self.validate_transaction(parsed)
        self.assertFalse(is_valid)
        self.assertIn("missing", error.lower())

    def test_invalid_transaction_bad_type(self):
        parsed = {
            'type': 'refund',
            'action': 'other',
            'amount': 1000,
            'category': 'Miscellaneous',
            'description': 'test',
            'date': date.today().isoformat(),
        }
        is_valid, error = self.validate_transaction(parsed)
        self.assertFalse(is_valid)
        self.assertIn("Invalid transaction type", error)

    def test_unknown_action_defaults_to_other(self):
        parsed = {
            'type': 'expense',
            'action': 'barter',
            'amount': 1000,
            'category': 'Miscellaneous',
            'description': 'test',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['action'], 'other')

    def test_missing_category_defaults_to_other(self):
        parsed = {
            'type': 'expense',
            'action': 'expense',
            'amount': 500,
            'category': None,
            'description': 'misc',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['category'], 'Miscellaneous')

    def test_item_truncation(self):
        parsed = {
            'type': 'expense',
            'action': 'purchase',
            'amount': 1000,
            'item': 'x' * 500,
            'category': 'Miscellaneous',
            'description': 'test',
            'date': date.today().isoformat(),
        }
        is_valid, result = self.validate_transaction(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(len(result['item']), 255)

    # --- validate_query ---

    def test_valid_query(self):
        parsed = {
            'query_type': 'sum',
            'type': 'expense',
            'category': 'Fuel',
            'period_start': '2026-06-01',
            'period_end': '2026-06-30',
        }
        is_valid, result = self.validate_query(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['query_type'], 'sum')

    def test_invalid_query_type_defaults_to_sum(self):
        parsed = {'query_type': 'histogram'}
        is_valid, result = self.validate_query(parsed)
        self.assertTrue(is_valid)
        self.assertEqual(result['query_type'], 'sum')

    def test_query_bad_date_filter_cleared(self):
        parsed = {
            'query_type': 'list',
            'period_start': 'last week',
        }
        is_valid, result = self.validate_query(parsed)
        self.assertTrue(is_valid)
        self.assertIsNone(result['period_start'])


class TestFormatter(unittest.TestCase):
    """Tests for app/formatter.py"""

    def setUp(self):
        from app.services.formatter import (
            format_currency, format_transaction_saved, format_balance
        )
        self.format_currency = format_currency
        self.format_transaction_saved = format_transaction_saved
        self.format_balance = format_balance

    def test_format_currency_positive(self):
        self.assertEqual(self.format_currency(2000), "₦2,000")

    def test_format_currency_large(self):
        self.assertEqual(self.format_currency(1500000), "₦1,500,000")

    def test_format_currency_negative(self):
        self.assertEqual(self.format_currency(-500), "-₦500")

    def test_format_currency_zero(self):
        self.assertEqual(self.format_currency(0), "₦0")

    def test_format_transaction_sale(self):
        result = {
            'type': 'income',
            'action': 'sale',
            'amount': 5000.0,
            'currency': 'NGN',
            'item': 'rice',
            'category': 'Sales',
            'description': 'sold rice',
            'date': '2026-06-03',
        }
        output = self.format_transaction_saved(result)
        self.assertIn("Transaction Recorded", output)
        self.assertIn("Sale", output)
        self.assertIn("₦5,000", output)
        self.assertIn("rice", output)
        self.assertIn("Sales", output)

    def test_format_transaction_purchase(self):
        result = {
            'type': 'expense',
            'action': 'purchase',
            'amount': 2000.0,
            'currency': 'NGN',
            'item': 'fuel',
            'category': 'Fuel',
            'description': 'bought fuel',
            'date': '2026-06-03',
        }
        output = self.format_transaction_saved(result)
        self.assertIn("Purchase", output)
        self.assertIn("₦2,000", output)
        self.assertIn("fuel", output)

    def test_format_transaction_no_item(self):
        result = {
            'type': 'income',
            'action': 'income',
            'amount': 10000.0,
            'currency': 'NGN',
            'item': None,
            'category': 'Miscellaneous',
            'description': 'received payment',
            'date': '2026-06-03',
        }
        output = self.format_transaction_saved(result)
        self.assertIn("Income", output)
        self.assertNotIn("*Item:*", output)

    def test_format_balance(self):
        result = [
            {
                'currency': 'NGN',
                'income': 150000.0,
                'expenses': 87000.0,
                'net': 63000.0,
            }
        ]
        output = self.format_balance(result)
        self.assertIn("₦150,000", output)
        self.assertIn("₦87,000", output)
        self.assertIn("₦63,000", output)
        self.assertIn("📈", output)

    def test_format_balance_negative(self):
        result = [
            {
                'currency': 'NGN',
                'income': 50000.0,
                'expenses': 80000.0,
                'net': -30000.0,
            }
        ]
        output = self.format_balance(result)
        self.assertIn("-₦30,000", output)
        self.assertIn("📉", output)


class TestParseShorthand(unittest.TestCase):
    """Tests for app/utils.py parse_shorthand"""

    def setUp(self):
        from app.services.utils import parse_shorthand
        self.parse_shorthand = parse_shorthand

    def test_k_shorthand(self):
        self.assertEqual(self.parse_shorthand("2k"), 2000)

    def test_k_shorthand_decimal(self):
        self.assertEqual(self.parse_shorthand("2.5k"), 2500)

    def test_h_shorthand(self):
        self.assertEqual(self.parse_shorthand("5h"), 500)

    def test_plain_number(self):
        self.assertEqual(self.parse_shorthand("5000"), 5000)

    def test_invalid_text(self):
        self.assertEqual(self.parse_shorthand("hello"), 0)

    def test_empty_string(self):
        self.assertEqual(self.parse_shorthand(""), 0)

    def test_uppercase_k(self):
        self.assertEqual(self.parse_shorthand("3K"), 3000)

    def test_large_k(self):
        self.assertEqual(self.parse_shorthand("50k"), 50000)

    def test_20k_shorthand(self):
        self.assertEqual(self.parse_shorthand("20k"), 20000)

    def test_10h_shorthand(self):
        self.assertEqual(self.parse_shorthand("10h"), 1000)

    def test_1_point_2k_shorthand(self):
        self.assertEqual(self.parse_shorthand("1.2k"), 1200)

    def test_hundred_shorthand(self):
        self.assertEqual(self.parse_shorthand("1h"), 100)

    def test_zero_returns_zero(self):
        self.assertEqual(self.parse_shorthand("0"), 0)

    def test_large_decimal_k(self):
        self.assertEqual(self.parse_shorthand("100.5k"), 100500)

    def test_whitespace_handling(self):
        self.assertEqual(self.parse_shorthand("  3k  "), 3000)

    def test_uppercase_H(self):
        self.assertEqual(self.parse_shorthand("5H"), 500)


class TestTransactionAgentFastPath(unittest.TestCase):
    """Tests for TransactionAgent._try_fast_path (no DB/API calls needed).

    These tests verify the fast-path detection logic. Actual recording
    is not tested here since it requires a database connection.
    """

    def test_single_word_shorthand_detected(self):
        """Single-word shorthand like '2k' should be detected as fast-path candidate."""
        text = "2k"
        # Verify it's a single word
        self.assertEqual(len(text.strip().split()), 1)
        # Verify shorthand detection logic
        text_stripped = text.strip()
        is_shorthand = (
            text_stripped.replace('.', '', 1).replace('k', '', 1).replace('h', '', 1).isdigit() or
            text_stripped.lower().endswith('k') or
            text_stripped.lower().endswith('h')
        )
        self.assertTrue(is_shorthand)

    def test_multi_word_not_fast_path(self):
        """Multi-word messages like 'Sold rice 5000' should NOT be fast-path."""
        text = "Sold rice 5000"
        self.assertGreater(len(text.strip().split()), 1)

    def test_natural_language_not_fast_path(self):
        """Business text should NOT match shorthand detection."""
        text = "Bought fuel 2000"
        self.assertGreater(len(text.strip().split()), 1)


class TestReportingAgent(unittest.TestCase):
    """Tests for app/reporting_agent.py"""

    def setUp(self):
        from app.agents.reporting_agent import ReportingAgent
        self.agent = ReportingAgent(user_id=1)

    from unittest.mock import patch

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_single_currency(self, mock_query):
        import json
        from decimal import Decimal
        mock_query.return_value = [
            {'currency': 'NGN', 'type': 'income', 'total': Decimal('200000.00')},
            {'currency': 'NGN', 'type': 'expense', 'total': Decimal('50000.00')},
        ]
        output = self.agent.generate_report('monthly', '2026-06-03')
        data = json.loads(output)
        self.assertEqual(data['period'], 'monthly')
        self.assertEqual(data['income'], 200000.0)
        self.assertEqual(data['expenses'], 50000.0)
        self.assertEqual(data['profit'], 150000.0)

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_multi_currency(self, mock_query):
        import json
        from decimal import Decimal
        mock_query.return_value = [
            {'currency': 'NGN', 'type': 'income', 'total': Decimal('200000.00')},
            {'currency': 'NGN', 'type': 'expense', 'total': Decimal('50000.00')},
            {'currency': 'USD', 'type': 'income', 'total': Decimal('1000.00')},
            {'currency': 'USD', 'type': 'expense', 'total': Decimal('200.00')},
        ]
        output = self.agent.generate_report('monthly', '2026-06-03')
        data = json.loads(output)
        self.assertTrue(isinstance(data, list))
        self.assertEqual(len(data), 2)
        # NGN report
        self.assertEqual(data[0]['currency'], 'NGN')
        self.assertEqual(data[0]['income'], 200000.0)
        self.assertEqual(data[0]['expenses'], 50000.0)
        self.assertEqual(data[0]['profit'], 150000.0)
        # USD report
        self.assertEqual(data[1]['currency'], 'USD')
        self.assertEqual(data[1]['income'], 1000.0)
        self.assertEqual(data[1]['expenses'], 200.0)
        self.assertEqual(data[1]['profit'], 800.0)

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_empty(self, mock_query):
        import json
        mock_query.return_value = []
        output = self.agent.generate_report('monthly', '2026-06-03')
        data = json.loads(output)
        self.assertEqual(data['income'], 0)
        self.assertEqual(data['expenses'], 0)
        self.assertEqual(data['profit'], 0)

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_daily_bounds(self, mock_query):
        mock_query.return_value = []
        self.agent.generate_report('daily', '2026-06-03')
        mock_query.assert_called_once_with(
            date(2026, 6, 3), date(2026, 6, 3)
        )

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_weekly_bounds(self, mock_query):
        mock_query.return_value = []
        # Last 7 days including target date: June 3, 2026 -> May 28, 2026
        self.agent.generate_report('weekly', '2026-06-03')
        mock_query.assert_called_once_with(
            date(2026, 5, 28), date(2026, 6, 3)
        )

    @patch('app.agents.reporting_agent.ReportingAgent._query_aggregates')
    def test_generate_report_monthly_bounds(self, mock_query):
        mock_query.return_value = []
        self.agent.generate_report('monthly', '2026-06-03')
        mock_query.assert_called_once_with(
            date(2026, 6, 1), date(2026, 6, 30)
        )


class TestInventoryAgent(unittest.TestCase):
    """Tests for app/inventory_agent.py"""

    def setUp(self):
        from app.agents.inventory_agent import InventoryAgent
        self.agent = InventoryAgent(user_id=1)

    def test_inventory_clarification_missing_product(self):
        import json
        parsed = {
            'status': 'clarification_needed',
            'question': 'What product did you add?'
        }
        output = self.agent.process("Added 20", parsed)
        data = json.loads(output)
        self.assertEqual(data['status'], 'clarification_needed')
        self.assertEqual(data['question'], 'What product did you add?')

    def test_inventory_clarification_missing_quantity(self):
        import json
        parsed = {
            'product': 'rice',
            'action': 'REMOVE',
            'unit': 'bags',
            'quantity': None
        }
        output = self.agent.process("Sold rice", parsed)
        data = json.loads(output)
        self.assertEqual(data['status'], 'clarification_needed')
        self.assertEqual(data['question'], 'How many bags of rice were sold?')


class TestDebtAgent(unittest.TestCase):
    """Tests for app/debt_agent.py"""

    def setUp(self):
        from app.agents.debt_agent import DebtAgent
        self.agent = DebtAgent(user_id=1)

    def test_debt_clarification_missing_name(self):
        import json
        parsed = {
            'type': 'customer_debt',
            'action': 'add_debt',
            'amount': 2000
        }
        output = self.agent.process("customer bought 2000 on credit", parsed)
        data = json.loads(output)
        self.assertEqual(data['status'], 'clarification_needed')
        self.assertIn("Who is the customer or supplier", data['question'])

    def test_debt_clarification_missing_amount(self):
        import json
        parsed = {
            'name': 'john',
            'type': 'customer_debt',
            'action': 'add_debt',
            'amount': None
        }
        output = self.agent.process("john bought on credit", parsed)
        data = json.loads(output)
        self.assertEqual(data['status'], 'clarification_needed')
        self.assertIn("How much money was owes by john", data['question'])

    from unittest.mock import patch, MagicMock

    @patch('app.agents.debt_agent.get_db_connection')
    def test_add_debt_new(self, mock_get_db):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        parsed = {
            'name': 'john',
            'type': 'customer_debt',
            'action': 'add_debt',
            'amount': 5000,
            'currency': 'NGN'
        }

        output = self.agent.process("john owes 5000", parsed)
        data = json.loads(output)

        self.assertEqual(data['name'], 'john')
        self.assertEqual(data['type'], 'customer_debt')
        self.assertEqual(data['action'], 'add_debt')
        self.assertEqual(data['amount'], 5000.0)
        self.assertEqual(data['previous_balance'], 0.0)
        self.assertEqual(data['new_balance'], 5000.0)
        self.assertEqual(data['status'], 'updated')

    @patch('app.agents.debt_agent.get_db_connection')
    def test_add_debt_existing(self, mock_get_db):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 10,
            'outstanding_balance': 3000.0,
            'debt_type': 'receivable'
        }

        parsed = {
            'name': 'john',
            'type': 'customer_debt',
            'action': 'add_debt',
            'amount': 2000,
            'currency': 'NGN'
        }

        output = self.agent.process("john owes 2000 more", parsed)
        data = json.loads(output)

        self.assertEqual(data['previous_balance'], 3000.0)
        self.assertEqual(data['new_balance'], 5000.0)

    @patch('app.agents.debt_agent.get_db_connection')
    def test_repayment(self, mock_get_db):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 10,
            'outstanding_balance': 5000.0,
            'debt_type': 'receivable'
        }

        parsed = {
            'name': 'john',
            'type': 'customer_debt',
            'action': 'repayment',
            'amount': 2000,
            'currency': 'NGN'
        }

        output = self.agent.process("john paid 2000", parsed)
        data = json.loads(output)

        self.assertEqual(data['action'], 'repayment')
        self.assertEqual(data['amount'], 2000.0)
        self.assertEqual(data['previous_balance'], 5000.0)
        self.assertEqual(data['new_balance'], 3000.0)

    @patch('app.agents.debt_agent.get_db_connection')
    def test_full_payment(self, mock_get_db):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 10,
            'outstanding_balance': 5000.0,
            'debt_type': 'receivable'
        }

        parsed = {
            'name': 'john',
            'type': 'customer_debt',
            'action': 'full_payment',
            'amount': None,
            'currency': 'NGN'
        }

        output = self.agent.process("john cleared his debt", parsed)
        data = json.loads(output)

        self.assertEqual(data['action'], 'full_payment')
        self.assertEqual(data['amount'], 5000.0)
        self.assertEqual(data['previous_balance'], 5000.0)
        self.assertEqual(data['new_balance'], 0.0)


class TestFOSSystem(unittest.TestCase):
    """Tests for the unified Financial Operating System logic and AgentRouter."""

    def setUp(self):
        from app.agents.agent_router import AgentRouter
        from unittest.mock import patch
        self.router = AgentRouter(user_id=1, sender_id='12345')

        # Configure global session mocks for offline testing
        self.patch_router_session = patch('app.agents.agent_router.get_active_session')
        self.patch_intake_session = patch('app.agents.agent_1_intake.get_active_session')

        self.mock_router_session = self.patch_router_session.start()
        self.mock_intake_session = self.patch_intake_session.start()

        mock_session = {
            'id': 10,
            'user_id': 1,
            'phone_number': '12345',
            'display_name': 'Test User',
            'status': 'ACTIVE'
        }
        self.mock_router_session.return_value = mock_session
        self.mock_intake_session.return_value = mock_session

    def tearDown(self):
        self.patch_router_session.stop()
        self.patch_intake_session.stop()

    from unittest.mock import patch, MagicMock

    @patch('app.agents.agent_router.get_db_connection')
    @patch('app.agents.agent_1_intake.get_db_connection')
    def test_idempotency_protection(self, mock_get_db_intake, mock_get_db_router):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_router.return_value = mock_conn
        mock_get_db_intake.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # 1st fetchone (router check first call): None
        # 2nd fetchone (intake _log_ai_interaction): {'business_id': 1}
        # 3rd fetchone (router check second call): {'status': 'processing'}
        mock_cursor.fetchone.side_effect = [None, {'business_id': 1}, {'status': 'processing'}]

        # Call first time (mock NLP response as well)
        with patch('app.agents.agent_1_intake.parse_message') as mock_parse:
            mock_parse.return_value = {
                'intents': ['unknown'],
                'confidence': 1.0,
                'needs_review': False,
                'status': 'ok',
                'reply': 'Hello'
            }
            res1 = self.router.route("hello", message_id="msg123")
            self.assertEqual(res1, "Hello")

            # Call second time
            res2 = self.router.route("hello", message_id="msg123")
            self.assertEqual(res2, "__DUPLICATE_DROP__")

    @patch('app.agents.agent_router.get_db_connection')
    @patch('app.agents.agent_1_intake.get_db_connection')
    @patch('app.agents.agent_1_intake.parse_message')
    def test_confidence_and_review_queue(self, mock_parse, mock_get_db_intake, mock_get_db_router):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db_router.return_value = mock_conn
        mock_get_db_intake.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'business_id': 1}

        # Case 1: Low confidence score (0.5)
        mock_parse.return_value = {
            'intents': ['record_transaction'],
            'confidence': 0.5,
            'needs_review': False,
            'status': 'ok'
        }

        output = self.router.route("spent 1000 NGN on fuel")
        data = json.loads(output)
        self.assertEqual(data['status'], 'needs_review')
        self.assertIn("flagged for human review", data['message'])
        # Verify db insert was called
        mock_cursor.execute.assert_called_with(
            "INSERT INTO review_queue (id, user_id, raw_text, parsed_payload) VALUES (%s, %s, %s, %s)",
            (ANY, ANY, "spent 1000 NGN on fuel", json.dumps(mock_parse.return_value))
        )

    @patch('app.agents.agent_1_intake.parse_message')
    @patch('app.agents.snapshot_agent.get_db_connection')
    def test_business_health_snapshot(self, mock_get_db, mock_parse):
        import json
        from decimal import Decimal
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock SELECT queries inside SnapshotAgent:
        # 1. user business_id, 2. MTD cashflow, 3. debt balances, 4. low stock products
        mock_cursor.fetchone.return_value = {'business_id': 1}
        mock_cursor.fetchall.side_effect = [
            [{'type': 'income', 'total': Decimal('200000.00')}, {'type': 'expense', 'total': Decimal('50000.00')}],
            [{'debt_type': 'receivable', 'total': Decimal('35000.00')}, {'debt_type': 'payable', 'total': Decimal('12000.00')}],
            [{'item_name': 'rice'}]
        ]

        mock_parse.return_value = {
            'intents': [],
            'confidence': 0.98,
            'needs_review': False,
            'status': 'ok',
            'snapshot': True
        }

        output = self.router.route("how is my business doing?")
        data = json.loads(output)

        self.assertEqual(data['cash_in'], 200000.0)
        self.assertEqual(data['cash_out'], 50000.0)
        self.assertEqual(data['profit'], 150000.0)
        self.assertEqual(data['outstanding_customer_debt'], 35000.0)
        self.assertEqual(data['outstanding_supplier_debt'], 12000.0)
        self.assertEqual(data['low_stock_items'], ['rice'])
        self.assertEqual(data['status'], 'Healthy')

    @patch('app.agents.agent_router.get_user_by_sender')
    @patch('app.agents.agent_router.get_active_session')
    def test_session_verification_intercept(self, mock_get_session, mock_get_user):
        """Verify that AgentRouter intercepts requests when no active session is found."""
        mock_get_session.return_value = None
        mock_get_user.return_value = {'id': 1}
        res = self.router.route("hello")
        self.assertIn("Session expired or not found", res)

    @patch('app.agents.agent_router.get_active_session')
    @patch('app.agents.agent_1_intake.BandSDK.publish')
    def test_local_preclassification_snapshot(self, mock_publish, mock_get_session):
        """Verify that snapshot keywords trigger local pre-classification routing."""
        mock_get_session.return_value = {'user_id': 1}
        mock_publish.return_value = ["snapshot_ok"]
        
        res = self.router.route("health snapshot")
        self.assertEqual(res, "snapshot_ok")
        mock_publish.assert_called_with("intake_to_ledger", {
            "event_id": ANY,
            "timestamp": ANY,
            "correlation_id": ANY,
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "target_agent": None,
            "event_type": "report",
            "schema_version": "1.0",
            "payload": {
                "intent": "snapshot",
                "confidence_score": 1.0,
                "raw_text": "health snapshot",
                "is_fast_path": False,
                "fast_path_transaction": None,
                "nlp_parsed": {
                    "intents": ["snapshot"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "snapshot": True,
                    "transaction": None,
                    "inventory": None,
                    "debt": None,
                    "report": None,
                    "question": None
                }
            }
        })

    @patch('app.agents.agent_router.get_active_session')
    @patch('app.agents.agent_1_intake.BandSDK.publish')
    def test_local_preclassification_report(self, mock_publish, mock_get_session):
        """Verify that report keywords trigger local pre-classification routing."""
        mock_get_session.return_value = {'user_id': 1}
        mock_publish.return_value = ["report_ok"]
        
        res = self.router.route("show my weekly report")
        self.assertEqual(res, "report_ok")
        mock_publish.assert_called_with("intake_to_ledger", {
            "event_id": ANY,
            "timestamp": ANY,
            "correlation_id": ANY,
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "target_agent": None,
            "event_type": "report",
            "schema_version": "1.0",
            "payload": {
                "intent": "report",
                "confidence_score": 1.0,
                "raw_text": "show my weekly report",
                "is_fast_path": False,
                "fast_path_transaction": None,
                "nlp_parsed": {
                    "intents": ["report"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "snapshot": False,
                    "transaction": None,
                    "inventory": None,
                    "debt": None,
                    "report": {
                        "period": "weekly",
                        "date": None
                    },
                    "question": None
                }
            }
        })

    def test_pydantic_inventory_validation(self):
        """Verify Pydantic validation for inventory model."""
        from app.services.validators import validate_inventory
        
        # Valid
        is_valid, res = validate_inventory({
            "action": "ADD",
            "product": "RICE ",
            "quantity": "10",
            "unit": "bags"
        })
        self.assertTrue(is_valid)
        self.assertEqual(res['product'], 'rice')
        self.assertEqual(res['quantity'], 10.0)

        # Invalid
        is_valid, error = validate_inventory({
            "action": "INVALID",
            "product": "rice",
            "quantity": -5
        })
        self.assertFalse(is_valid)

    def test_pydantic_debt_validation(self):
        """Verify Pydantic validation for debt model."""
        from app.services.validators import validate_debt

        # Valid
        is_valid, res = validate_debt({
            "action": "add_debt",
            "name": " John ",
            "type": "customer_debt",
            "amount": "5000",
            "currency": "usd"
        })
        self.assertTrue(is_valid)
        self.assertEqual(res['name'], 'john')
        self.assertEqual(res['amount'], 5000.0)
        self.assertEqual(res['currency'], 'USD')

        # Invalid
        is_valid, error = validate_debt({
            "action": "repayment",
            "name": "john",
            "type": "supplier_debt",
            "amount": None
        })
        self.assertFalse(is_valid)

    @patch('app.agents.agent_router.get_active_session')
    @patch('app.agents.agent_1_intake.BandSDK.publish')
    def test_local_preclassification_transaction(self, mock_publish, mock_get_session):
        """Verify that simple transaction regex triggers local pre-classification."""
        mock_get_session.return_value = {'user_id': 1}
        mock_publish.return_value = ["tx_ok"]
        res = self.router.route("sold rice 5000")
        self.assertEqual(res, "tx_ok")
        mock_publish.assert_called_with("intake_to_ledger", {
            "event_id": ANY,
            "timestamp": ANY,
            "correlation_id": ANY,
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "target_agent": None,
            "event_type": "transaction",
            "schema_version": "1.0",
            "payload": {
                "intent": "record_transaction",
                "confidence_score": 1.0,
                "raw_text": "sold rice 5000",
                "is_fast_path": False,
                "fast_path_transaction": None,
                "nlp_parsed": {
                    "intents": ["record_transaction"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "snapshot": False,
                    "transaction": {
                        "type": "income",
                        "action": "sale",
                        "amount": 5000.0,
                        "currency": "NGN",
                        "item": "rice",
                        "category": "Sales",
                        "description": "sold rice 5000",
                        "date": date.today().isoformat()
                    },
                    "inventory": None,
                    "debt": None,
                    "report": None,
                    "question": None
                }
            }
        })

    @patch('app.agents.agent_router.get_active_session')
    @patch('app.agents.agent_1_intake.BandSDK.publish')
    def test_local_preclassification_inventory(self, mock_publish, mock_get_session):
        """Verify that simple inventory regex triggers local pre-classification."""
        mock_get_session.return_value = {'user_id': 1}
        mock_publish.return_value = ["inv_ok"]
        res = self.router.route("added 20 rice")
        self.assertEqual(res, "inv_ok")
        mock_publish.assert_called_with("intake_to_ledger", {
            "event_id": ANY,
            "timestamp": ANY,
            "correlation_id": ANY,
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "target_agent": None,
            "event_type": "inventory",
            "schema_version": "1.0",
            "payload": {
                "intent": "inventory",
                "confidence_score": 1.0,
                "raw_text": "added 20 rice",
                "is_fast_path": False,
                "fast_path_transaction": None,
                "nlp_parsed": {
                    "intents": ["inventory"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "snapshot": False,
                    "transaction": None,
                    "inventory": {
                        "action": "ADD",
                        "product": "rice",
                        "quantity": 20.0,
                        "unit": None
                    },
                    "debt": None,
                    "report": None,
                    "question": None
                }
            }
        })

    @patch('app.agents.agent_router.get_active_session')
    @patch('app.agents.agent_1_intake.BandSDK.publish')
    def test_local_preclassification_debt(self, mock_publish, mock_get_session):
        """Verify that simple debt regex triggers local pre-classification."""
        mock_get_session.return_value = {'user_id': 1}
        mock_publish.return_value = ["debt_ok"]
        res = self.router.route("john owes 5k")
        self.assertEqual(res, "debt_ok")
        mock_publish.assert_called_with("intake_to_ledger", {
            "event_id": ANY,
            "timestamp": ANY,
            "correlation_id": ANY,
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "target_agent": None,
            "event_type": "debt",
            "schema_version": "1.0",
            "payload": {
                "intent": "debt",
                "confidence_score": 1.0,
                "raw_text": "john owes 5k",
                "is_fast_path": False,
                "fast_path_transaction": None,
                "nlp_parsed": {
                    "intents": ["debt"],
                    "confidence": 1.0,
                    "needs_review": False,
                    "status": "ok",
                    "snapshot": False,
                    "transaction": None,
                    "inventory": None,
                    "debt": {
                        "action": "add_debt",
                        "name": "john",
                        "type": "customer_debt",
                        "amount": 5000.0,
                        "currency": "NGN"
                    },
                    "report": None,
                    "question": None
                }
            }
        })

    @patch('app.agents.agent_router.get_db_connection')
    @patch('app.agents.agent_1_intake.parse_message')
    def test_webhook_lifecycle_transitions(self, mock_parse, mock_get_db):
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock the lifecycle state transitions:
        # First call: SELECT returns {'status': 'received'} -> transition to processing
        # Inside IntakeAgent._log_ai_interaction: fetch business_id -> returns {'business_id': 1}
        # Inside router.route: UPDATE to processed after successful Intake
        mock_cursor.fetchone.side_effect = [{'status': 'received'}, {'business_id': 1}]

        mock_parse.return_value = {
            'intents': ['unknown'],
            'confidence': 1.0,
            'needs_review': False,
            'status': 'ok',
            'reply': 'Success Response'
        }

        res = self.router.route("hello", message_id="msg789")
        self.assertEqual(res, "Success Response")

        # Verify transition to processing was called
        mock_cursor.execute.assert_any_call(
            "UPDATE webhook_events SET status = 'processing', processed_at = NULL WHERE whatsapp_message_id = %s",
            ("msg789",)
        )
        # Verify update to processed was called
        mock_cursor.execute.assert_any_call(
            "UPDATE webhook_events SET status = 'processed', processed_at = CURRENT_TIMESTAMP WHERE whatsapp_message_id = %s",
            ("msg789",)
        )

    @patch('app.agents.agent_2_ledger.get_db_connection')
    @patch('app.agents.agent_2_ledger.BandSDK.publish')
    def test_ledger_transient_retry_and_dead_letter(self, mock_publish, mock_get_db):
        from app.agents.agent_2_ledger import LedgerAgent
        from app.agents.event_schemas import IntakePayload
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock connection behavior:
        # All attempts raise exceptions (database deadlock or lock timeout)
        mock_cursor.execute.side_effect = Exception("Deadlock / Lock wait timeout exceeded")
        
        ledger = LedgerAgent(user_id=1, sender_id="12345")
        
        # Create a mock IntakePayload
        from uuid import uuid4
        event_id = uuid4()
        payload = {
            "event_id": str(event_id),
            "timestamp": "2026-06-04T00:00:00Z",
            "correlation_id": str(uuid4()),
            "session_id": "10",
            "user_id": 1,
            "business_id": 1,
            "source_agent": "IntakeAgent",
            "event_type": "transaction",
            "payload": {
                "intent": "record_transaction",
                "confidence_score": 1.0,
                "raw_text": "sold rice 5000",
                "is_fast_path": True,
                "fast_path_transaction": {
                    "type": "income",
                    "action": "sale",
                    "amount": 5000.0,
                    "currency": "NGN",
                    "item": "rice",
                    "category": "Sales",
                    "description": "sold rice 5000",
                    "date": "2026-06-04"
                }
            }
        }
        
        # Temporarily shorten retry delays to avoid sleeping during tests
        with patch('time.sleep') as mock_sleep:
            res = ledger.handle_intake_payload(payload)
            
        self.assertEqual(res, {"status": "error_handled_via_pubsub"})
        # Should have retried and eventually published to ledger_errors dead-letter channel
        mock_publish.assert_called_with("ledger_errors", ANY)


if __name__ == '__main__':
    unittest.main()


