"""WP-10 — FinOps per-provider/model spend attribution.

Drives the router with faked provider clients and asserts the spend accumulator splits
by provider + model, plus the WhatsApp formatter. No network, no DB.
"""

import os
import unittest

from app.services import model_router
from app.agents.reporting_agent import format_router_spend


class _FakeResp:
    def __init__(self):
        msg = type("M", (), {"content": "{}"})()
        self.choices = [type("C", (), {"message": msg})()]
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()


class _FakeClient:
    def __init__(self, fn):
        self.chat = type("Chat", (), {"completions": type("Cmp", (), {"create": staticmethod(fn)})()})()


class TestFinOps(unittest.TestCase):
    def setUp(self):
        for k in ("OPENAI_API_KEY", "AIML_API_KEY", "FEATHERLESS_API_KEY"):
            os.environ.setdefault(k, "test-key")
        model_router.reset_spend()
        self._real = model_router.get_client
        model_router.get_client = lambda name: _FakeClient(lambda **kw: _FakeResp())

    def tearDown(self):
        model_router.get_client = self._real
        model_router.reset_spend()

    def test_spend_split_by_provider_and_model(self):
        model_router.chat_completion("intake", [{"role": "user", "content": "x"}])   # featherless
        model_router.chat_completion("intake", [{"role": "user", "content": "x"}])   # featherless
        model_router.chat_completion("cfo", [{"role": "user", "content": "x"}])       # aiml
        rep = model_router.spend_report()
        self.assertEqual({r["provider"] for r in rep["rows"]}, {"featherless", "aiml"})
        self.assertEqual(rep["total_calls"], 3)
        self.assertEqual(rep["by_provider"]["featherless"]["calls"], 2)
        self.assertGreater(rep["by_provider"]["aiml"]["cost"], 0)          # aiml rate > 0
        self.assertAlmostEqual(rep["total_cost"], sum(r["cost"] for r in rep["rows"]))

    def test_reset_clears_accumulator(self):
        model_router.chat_completion("intake", [{"role": "user", "content": "x"}])
        self.assertEqual(model_router.spend_report()["total_calls"], 1)
        model_router.reset_spend()
        self.assertEqual(model_router.spend_report()["total_calls"], 0)

    def test_formatter_renders_breakdown_and_empty(self):
        rep = {"rows": [{"provider": "featherless", "model": "Qwen", "calls": 2, "cost": 0.0003,
                         "prompt_tokens": 20, "completion_tokens": 10}],
               "by_provider": {"featherless": {"calls": 2, "cost": 0.0003}},
               "total_cost": 0.0003, "total_calls": 2}
        txt = format_router_spend(rep)
        self.assertIn("featherless", txt)
        self.assertIn("Session total", txt)
        self.assertEqual(format_router_spend({"rows": []}), "*Live session spend (this run):* none yet.")


if __name__ == "__main__":
    unittest.main()
