"""Unit tests for the multi-provider model router (WP-01 / G-MODEL-ROUTER).

No network and no Flask app context: provider clients are faked, so these tests
prove the *routing + fallback* contract, not real provider calls.
"""

import os
import unittest

from app.services import model_router


# --- Fake OpenAI-compatible client -----------------------------------------

class _FakeResp:
    def __init__(self, content):
        msg = type("M", (), {"content": content})()
        self.choices = [type("C", (), {"message": msg})()]
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()


class _Completions:
    def __init__(self, fn):
        self._fn = fn

    def create(self, **kw):
        return self._fn(**kw)


class _FakeClient:
    def __init__(self, fn):
        self.chat = type("Chat", (), {"completions": _Completions(fn)})()


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        # Dummy keys so get_client can build real OpenAI clients for binding checks.
        for k in ("OPENAI_API_KEY", "AIML_API_KEY", "FEATHERLESS_API_KEY"):
            os.environ.setdefault(k, "test-key")
        os.environ.pop("MODEL_ROUTER_SPEND_CEILING_USD", None)
        model_router._spent_usd = 0.0
        self._real_get_client = model_router.get_client

    def tearDown(self):
        model_router.get_client = self._real_get_client
        model_router._spent_usd = 0.0

    # --- route() ordering ---

    def test_role_chains_primary_and_fallback(self):
        self.assertEqual(model_router.route("intake")[0][0], "featherless")
        self.assertEqual(model_router.route("cfo")[0][0], "aiml")
        self.assertEqual(model_router.route("escalation")[0][0], "aiml")
        # Every chain terminates in OpenAI as the fallback.
        for role in ("intake", "cfo", "escalation", "compliance", "format"):
            self.assertEqual(model_router.route(role)[-1][0], "openai")

    def test_unknown_role_defaults_to_intake_chain(self):
        self.assertEqual(model_router.route("nonsense"), model_router.route(model_router.DEFAULT_ROLE))

    # --- get_client() binding ---

    def test_get_client_binds_role_primary_provider(self):
        self.assertIn("featherless", str(model_router.get_client("intake").base_url))
        self.assertIn("aimlapi", str(model_router.get_client("cfo").base_url))
        self.assertIn("openai", str(model_router.get_client("openai").base_url))

    def test_get_client_rejects_unknown(self):
        with self.assertRaises(ValueError):
            model_router.get_client("does-not-exist")

    # --- chat_completion() routing + fallback ---

    def test_primary_provider_used_on_success(self):
        model_router.get_client = lambda name: _FakeClient(lambda **kw: _FakeResp('{"p":"%s"}' % name))
        res = model_router.chat_completion("intake", [{"role": "user", "content": "hi"}])
        self.assertEqual(res["provider"], "featherless")
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(res["content"], '{"p":"featherless"}')

    def test_falls_back_to_openai_when_primary_errors(self):
        def factory(name):
            def fn(**kw):
                if name == "openai":
                    return _FakeResp('{"ok": true}')
                raise TimeoutError(f"{name} unavailable")
            return _FakeClient(fn)
        model_router.get_client = factory

        res = model_router.chat_completion("intake", [{"role": "user", "content": "hi"}])
        self.assertEqual(res["provider"], "openai")   # Featherless failed -> OpenAI fallback
        self.assertEqual(res["attempts"], 2)
        self.assertEqual(res["content"], '{"ok": true}')

    def test_raises_when_every_provider_fails(self):
        def fail(name):
            def fn(**kw):
                raise RuntimeError(f"{name} down")
            return _FakeClient(fn)
        model_router.get_client = fail
        with self.assertRaises(RuntimeError):
            model_router.chat_completion("cfo", [{"role": "user", "content": "hi"}])

    def test_openai_cost_is_estimated_from_usage(self):
        model_router.get_client = lambda name: _FakeClient(lambda **kw: _FakeResp("{}"))
        # Force the openai branch by failing the partner provider.
        def factory(name):
            def fn(**kw):
                if name == "openai":
                    return _FakeResp("{}")
                raise TimeoutError("down")
            return _FakeClient(fn)
        model_router.get_client = factory
        res = model_router.chat_completion("intake", [{"role": "user", "content": "hi"}])
        # 10 prompt @0.15/M + 5 completion @0.60/M
        self.assertAlmostEqual(res["estimated_cost"], 10 * 0.150 / 1_000_000 + 5 * 0.600 / 1_000_000)


if __name__ == "__main__":
    unittest.main()
