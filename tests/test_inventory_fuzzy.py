"""Unit tests for WP-03: Canonical Inventory Prompt Injection & Fuzzy SQL Matcher.

Verifies:
1. Multi-tier fuzzy matching: exact match, stemming (eggs -> egg), token containment (rice -> 50kg bag of rice).
2. Tied-score disambiguation: interactive clarification when multiple items match with equal confidence (G-07).
3. Reliable user_id scoping regardless of business_id NULL status.
4. Canonical product injection into NLP build_system_prompt.
5. Integration with InventoryAgent.
"""

import json
import unittest
from unittest.mock import patch, MagicMock

from app.data.queries import (
    _stem_token,
    resolve_inventory_item,
    get_user_product_names,
    query_stock_levels,
)
from app.services.nlp import build_system_prompt
from app.agents.inventory_agent import InventoryAgent


class TestInventoryFuzzyMatcher(unittest.TestCase):
    def setUp(self):
        self.user_id = "test-user-fuzzy"

    def test_stem_token_variations(self):
        """Verify pluralization normalization for common trade and inventory goods."""
        variations = {
            "eggs": "egg",
            "egg": "egg",
            "cartons": "carton",
            "carton": "carton",
            "bags": "bag",
            "boxes": "box",
            "crates": "crate",
            "tomatoes": "tomato",
            "potatoes": "potato",
            "cherries": "cherry",
            "rice": "rice",
            "gas": "gas",
            "glass": "glass",
        }
        for plural, singular in variations.items():
            with self.subTest(plural=plural):
                self.assertEqual(_stem_token(plural), singular)

    @patch("app.data.queries.session_scope")
    def test_exact_match(self, mock_session_scope):
        """Exact casing/whitespace match resolves in Tier 1."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        row_item = MagicMock()
        row_item.id = "uuid-sugar"
        row_item.item_name = "Dangote Sugar"
        row_item.unit = "packets"
        row_item.stock = 15.0

        mock_session.execute.return_value.all.side_effect = [
            [row_item],  # inv_stmt
            [],          # prod_stmt
        ]

        result = resolve_inventory_item(self.user_id, "Dangote Sugar")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["item_name"], "Dangote Sugar")
        self.assertEqual(result["unit"], "packets")
        self.assertEqual(result["stock"], 15.0)

    @patch("app.data.queries.session_scope")
    def test_stemmed_plural_match(self, mock_session_scope):
        """Pluralized query 'eggs' resolves to stored item 'egg' (DoD #2)."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        row_item = MagicMock()
        row_item.id = "uuid-egg"
        row_item.item_name = "egg"
        row_item.unit = "crates"
        row_item.stock = 8.0

        mock_session.execute.return_value.all.side_effect = [
            [row_item],
            [],
        ]

        result = resolve_inventory_item(self.user_id, "eggs")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["item_name"], "egg")
        self.assertEqual(result["unit"], "crates")

    @patch("app.data.queries.session_scope")
    def test_token_containment_match(self, mock_session_scope):
        """Query 'rice' resolves to stored item '50kg bag of rice' (DoD #1)."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        row_item = MagicMock()
        row_item.id = "uuid-rice"
        row_item.item_name = "50kg bag of rice"
        row_item.unit = "bags"
        row_item.stock = 25.0

        mock_session.execute.return_value.all.side_effect = [
            [row_item],
            [],
        ]

        result = resolve_inventory_item(self.user_id, "rice")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["item_name"], "50kg bag of rice")
        self.assertEqual(result["stock"], 25.0)

    @patch("app.data.queries.session_scope")
    def test_tied_matches_trigger_clarification(self, mock_session_scope):
        """Tied substring matches (e.g. 'Golden Penny Flour' vs 'Golden Penny Semovita') ask clarification (DoD #3 / G-07)."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        row_flour = MagicMock()
        row_flour.id = "uuid-gp-flour"
        row_flour.item_name = "Golden Penny Flour"
        row_flour.unit = "bags"
        row_flour.stock = 10.0

        row_semo = MagicMock()
        row_semo.id = "uuid-gp-semo"
        row_semo.item_name = "Golden Penny Semovita"
        row_semo.unit = "bags"
        row_semo.stock = 14.0

        mock_session.execute.return_value.all.side_effect = [
            [row_flour, row_semo],
            [],
        ]

        result = resolve_inventory_item(self.user_id, "Golden Penny")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "clarification_needed")
        self.assertEqual(len(result["matches"]), 2)
        self.assertIn("Golden Penny Flour", result["question"])
        self.assertIn("Golden Penny Semovita", result["question"])

    @patch("app.data.queries.session_scope")
    def test_scoping_by_user_id_handles_null_business_id(self, mock_session_scope):
        """Querying stock levels correctly returns user items even when business_id is NULL (DoD #4)."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        row_inv = MagicMock()
        row_inv.item_name = "Knorr Cubes"
        row_inv.unit = "packets"
        row_inv.stock = 50.0

        row_prod = MagicMock()
        row_prod.name = "Palm Oil"
        row_prod.unit = "litres"
        row_prod.quantity = 20.0

        mock_session.execute.return_value.all.side_effect = [
            [row_inv],
            [row_prod],
        ]

        stock_levels = query_stock_levels(self.user_id)
        self.assertIsNotNone(stock_levels)
        self.assertEqual(len(stock_levels), 2)
        item_names = [item["item"] for item in stock_levels]
        self.assertIn("Knorr Cubes", item_names)
        self.assertIn("Palm Oil", item_names)

    @patch("app.data.queries.session_scope")
    def test_get_user_product_names_deduplicates(self, mock_session_scope):
        """get_user_product_names returns unique sorted product names across both tables."""
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session

        mock_session.execute.return_value.scalars.return_value.all.side_effect = [
            ["Rice", "Beans"],
            ["Rice", "Garri"],
        ]

        names = get_user_product_names(self.user_id)
        self.assertEqual(names, ["Beans", "Garri", "Rice"])

    def test_nlp_system_prompt_injects_available_products(self):
        """build_system_prompt includes AVAILABLE PRODUCTS IN INVENTORY section when provided."""
        categories = [{"name": "Sales", "type": "income"}]
        products = ["50kg bag of rice", "egg", "Golden Penny Flour"]

        prompt = build_system_prompt(categories, products=products)
        self.assertIn("AVAILABLE PRODUCTS IN INVENTORY:", prompt)
        self.assertIn("- 50kg bag of rice", prompt)
        self.assertIn("- egg", prompt)
        self.assertIn("- Golden Penny Flour", prompt)

    @patch("app.agents.inventory_agent.resolve_inventory_item")
    def test_inventory_agent_clarification_on_tied_match(self, mock_resolve):
        """InventoryAgent returns clarification JSON when fuzzy match is tied."""
        mock_resolve.return_value = {
            "status": "clarification_needed",
            "question": "Which Golden Penny product do you mean?"
        }

        agent = InventoryAgent(user_id=self.user_id)
        res_json = agent.process("add 5 Golden Penny", {"product": "Golden Penny", "quantity": 5, "action": "ADD"})
        res = json.loads(res_json)

        self.assertEqual(res["status"], "clarification_needed")
        self.assertIn("Which Golden Penny", res["question"])


if __name__ == "__main__":
    unittest.main()
