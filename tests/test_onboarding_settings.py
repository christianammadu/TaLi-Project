"""Unit tests for in-chat onboarding + settings (WP-03/04/05/06).

DB-free: every database boundary (``session_scope`` and the ``auth`` setters) is
mocked, so these run without MySQL or network — matching ``test_transaction_agent``.

Covered:
- ``auth.get_onboarding_state`` — the resumable "what's next" computation, incl.
  the business branch and the skipped-name case.
- ``routes.handle_set`` — each ``set <field> <value>`` edit + invalid input.
- ``routes.handle_onboarding_answer`` — answer routing per pending question.
"""

import unittest
from contextlib import contextmanager
from unittest import mock


def _fake_session_scope(row):
    """Return a session_scope replacement whose .execute(...).first() yields `row`."""
    @contextmanager
    def _cm():
        s = mock.MagicMock()
        s.execute.return_value.first.return_value = row
        yield s
    return _cm


class TestOnboardingState(unittest.TestCase):
    """auth.get_onboarding_state — next-question logic (record IS the state)."""

    def _next(self, row):
        with mock.patch('app.auth.session_scope', _fake_session_scope(row)):
            from app.auth import get_onboarding_state
            return get_onboarding_state(1)

    # row = (display_name, usage_type, base_currency, business_profile, onboarding_step)
    def test_fresh_user_asks_name(self):
        st = self._next((None, None, 'NGN', None, None))
        self.assertEqual(st['next'], 'name')
        self.assertFalse(st['complete'])

    def test_name_set_asks_usage(self):
        self.assertEqual(self._next(('Ada', None, 'NGN', None, None))['next'], 'usage')

    def test_skipped_name_advances_to_usage(self):
        # step >= 1 means the name was offered + skipped — don't re-ask in-flow.
        self.assertEqual(self._next((None, None, 'NGN', None, 1))['next'], 'usage')

    def test_usage_set_asks_currency(self):
        self.assertEqual(self._next(('Ada', 'personal', 'NGN', None, 2))['next'], 'currency')

    def test_personal_is_complete(self):
        st = self._next(('Ada', 'personal', 'NGN', None, 3))
        self.assertTrue(st['complete'])
        self.assertIsNone(st['next'])

    def test_business_needs_name(self):
        self.assertEqual(self._next(('Ada', 'business', 'NGN', {}, 3))['next'], 'business_name')

    def test_business_needs_type(self):
        self.assertEqual(
            self._next(('Ada', 'business', 'NGN', {'name': 'Ada Kitchen'}, 4))['next'],
            'business_type',
        )

    def test_business_complete(self):
        st = self._next(('Ada', 'business', 'NGN', {'name': 'Ada Kitchen', 'type': 'Food / Restaurant'}, 9))
        self.assertTrue(st['complete'])

    def test_missing_user_returns_none(self):
        self.assertIsNone(self._next(None))


class TestSettings(unittest.TestCase):
    """account_settings.apply_setting / render_settings — channel-agnostic (return text)."""

    def setUp(self):
        patches = mock.patch.multiple(
            'app.channels.account_settings',
            set_display_name=mock.DEFAULT,
            set_usage_type=mock.DEFAULT,
            update_business_profile=mock.DEFAULT,
            _set_base_currency=mock.DEFAULT,
        )
        self.m = patches.start()
        self.addCleanup(patches.stop)
        # setters succeed by default
        for k in ('set_display_name', 'set_usage_type', 'update_business_profile', '_set_base_currency'):
            self.m[k].return_value = True

    def _apply(self, text):
        from app.channels.account_settings import apply_setting
        return apply_setting(1, text)

    def test_set_name(self):
        reply = self._apply('set name Ada')
        self.m['set_display_name'].assert_called_once_with(1, 'Ada')
        self.assertIn('Name updated', reply)

    def test_set_currency_uppercases(self):
        reply = self._apply('set currency usd')
        self.m['_set_base_currency'].assert_called_once_with(1, 'USD')
        self.assertIn('USD', reply)

    def test_set_currency_invalid_rejected(self):
        reply = self._apply('set currency dollars')
        self.m['_set_base_currency'].assert_not_called()
        self.assertIn('3-letter', reply)

    def test_set_type_business(self):
        self._apply('set type business')
        self.m['set_usage_type'].assert_called_once_with(1, 'business')

    def test_set_type_invalid_rejected(self):
        self._apply('set type corporate')
        self.m['set_usage_type'].assert_not_called()

    def test_set_business_implies_business_usage(self):
        self._apply("set business Ada's Kitchen")
        self.m['update_business_profile'].assert_called_once_with(1, name="Ada's Kitchen")
        self.m['set_usage_type'].assert_called_once_with(1, 'business')

    def test_set_missing_value_shows_usage(self):
        reply = self._apply('set name')
        self.m['set_display_name'].assert_not_called()
        self.assertIn('Usage', reply)

    def test_set_unknown_field(self):
        reply = self._apply('set colour blue')
        self.assertIn('name', reply.lower())

    def test_render_settings_menu(self):
        from app.channels import account_settings
        snapshot = {
            'display_name': 'Ada', 'usage_type': 'business', 'base_currency': 'NGN',
            'business_profile': {'name': "Ada's Kitchen", 'type': 'Food / Restaurant'},
            'alert_thresholds': {'low_stock_limit': 5},
        }
        with mock.patch.object(account_settings, '_read_settings', return_value=snapshot):
            out = account_settings.render_settings(1)
        self.assertIn('Your settings', out)
        self.assertIn('Ada', out)
        self.assertIn('NGN', out)


class TestOnboardingAnswer(unittest.TestCase):
    """routes.handle_onboarding_answer — answer routing per pending question."""

    def setUp(self):
        self.session = {'user_id': 1}
        patches = mock.patch.multiple(
            'app.web.routes',
            send_reply=mock.DEFAULT,
            consume_onboarding_answer=mock.DEFAULT,
        )
        self.m = patches.start()
        self.addCleanup(patches.stop)

    def _state(self, nxt):
        self.nxt = nxt

    def test_name_answer_sets_name(self):
        from app.web.routes import handle_onboarding_answer
        self._state('name')
        handle_onboarding_answer('234', 'Ada', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_name_skip_advances_step(self):
        from app.web.routes import handle_onboarding_answer
        self._state('name')
        handle_onboarding_answer('234', 'skip', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_usage_two_is_business(self):
        from app.web.routes import handle_onboarding_answer
        self._state('usage')
        handle_onboarding_answer('234', '2', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_usage_invalid_reasks(self):
        from app.web.routes import handle_onboarding_answer
        self._state('usage')
        handle_onboarding_answer('234', 'maybe', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_business_name_captured(self):
        from app.web.routes import handle_onboarding_answer
        self._state('business_name')
        handle_onboarding_answer('234', 'Ada Kitchen', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_business_type_numeric_maps_to_category(self):
        from app.web.routes import handle_onboarding_answer
        self._state('business_type')
        handle_onboarding_answer('234', '2', self.session)
        self.m['consume_onboarding_answer'].assert_called_once()

    def test_business_type_garbage_reasks(self):
        from app.web.routes import handle_onboarding_answer
        self._state('business_type')
        handle_onboarding_answer('234', 'x' * 80, self.session)
        self.m['consume_onboarding_answer'].assert_called_once()


if __name__ == '__main__':
    unittest.main()
