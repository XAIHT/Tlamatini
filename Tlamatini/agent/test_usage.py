# Tlamatini Author Banner — Angela López Mendoza
"""Usage correctness, isolation, failure handling and source-carriage contracts."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.migrations.state import ProjectState
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from agent import context_governor as governor
from agent import usage_provider as provider
from agent import usage_tracking as tracking
from agent import usage_views as views
from agent.models import UsageDaily

urlpatterns = [path('usage/', login_required(views.usage_view))]
NOW = datetime(2026, 10, 10, 14, tzinfo=timezone.utc)


def usage_fixture(days=31):
    start = (NOW - timedelta(days=days - 1)).replace(hour=0)
    rows = [{"from": (start + timedelta(days=i)).isoformat(),
             "until": (start + timedelta(days=i + 1)).isoformat(),
             "usage_usd": .25, "request_count": 2, "input_tokens": 1000,
             "cached_input_tokens": 200, "output_tokens": 100,
             "partial": i == days - 1} for i in range(days)]
    return {"scope": "account", "from": start.isoformat(), "until": NOW.isoformat(),
            "totals": {key: sum(r[key] for r in rows) for key in provider.METRICS}, "buckets": rows}


def balance_fixture():
    return {'included': {'balance_usd': 40.89496, 'allowance_usd': 60,
                         'period': {'from': '2026-10-08T20:28:37Z', 'until': '2026-11-08T20:28:37Z'}},
            'purchased': {'balance_usd': 20}}


def snapshot_fixture():
    return {"account_key": "fixture-account", "account_available": True,
            "account": "Usage test account", "balance": {"data": provider.normalize_balance(balance_fixture())}, "ranges": {
                name: {"data": provider.normalize_usage(usage_fixture(days)), "stale": False,
                       "updated_at": NOW.isoformat(), "error": None}
                for name, days in (("7d", 8), ("30d", 31))}, "models": [], "running": []}


class ProviderTests(SimpleTestCase):
    def tearDown(self):
        provider._CACHE.clear()

    def test_missing_counts_are_not_zero(self):
        raw = usage_fixture()
        del raw['totals']['output_tokens']
        raw['buckets'][0]['input_tokens'] = 'NaN'
        result = provider.normalize_usage(raw)
        self.assertIsNone(result['totals']['output_tokens'])
        self.assertIsNone(result['daily'][0]['input_tokens'])
        self.assertIsNone(provider.normalize_usage({'error': 'unavailable'}))

    def test_decimal_negative_boolean_and_infinite_values(self):
        for value in (None, True, -1, 'NaN', 'Infinity', 'invalid', '1e100'):
            self.assertIsNone(provider.number(value))
        self.assertEqual(provider.number('0.123456'), .123456)
        self.assertEqual(provider.instant('2026-10-01').tzinfo, timezone.utc)

    def test_authoritative_monthly_and_purchased_balance(self):
        result = provider.normalize_balance(balance_fixture())
        self.assertEqual(result['kind'], 'credits')
        self.assertEqual(result['allowance'], 60)
        self.assertEqual(result['monthly_remaining'], 40.89496)
        self.assertEqual(result['used'], 19.10504)
        self.assertEqual(result['remaining'], 60.89496)
        self.assertEqual(result['end'], '2026-11-08T20:28:37+00:00')

    def test_free_zero_balance_and_max_allowance_use_returned_values(self):
        for allowance, remaining in ((0, 0), (1, 0), (300, 279.123456), (1000, 890)):
            raw = balance_fixture()
            raw['included'].update(allowance_usd=allowance, balance_usd=remaining)
            raw['purchased']['balance_usd'] = 0
            result = provider.normalize_balance(raw)
            self.assertEqual(result['allowance'], allowance)
            self.assertEqual(result['remaining'], remaining)
            self.assertEqual(result['percent'], None if not allowance else result['used'] / allowance * 100)

    def test_signed_balance_is_not_clamped_to_zero(self):
        raw = balance_fixture()
        raw['included']['balance_usd'] = -0.5
        raw['purchased']['balance_usd'] = -1
        result = provider.normalize_balance(raw)
        self.assertEqual(result['remaining'], -1.5)
        self.assertEqual(result['used'], 60.5)
        self.assertGreater(result['percent'], 100)

    def test_legacy_plan_preserves_session_and_weekly_limits(self):
        result = provider.normalize_balance({'included': {
            'session': {'remaining_percent': 75.12345, 'resets_at': '2026-10-10T19:00:00Z'},
            'weekly': {'remaining_percent': 0, 'resets_at': '2026-10-15T19:00:00Z'}},
            'purchased': {'balance_usd': 25}})
        self.assertEqual(result['kind'], 'legacy')
        self.assertEqual(result['limits'][0]['remaining_percent'], 75.12345)
        self.assertEqual(result['limits'][1]['remaining_percent'], 0)
        self.assertNotIn('allowance', result)

    def test_missing_credit_fields_never_become_zero_or_unlimited(self):
        for raw in ({}, {'error': 'unavailable'}, {'included': {'unlimited': True}},
                    {'included': {'session': {'remaining_percent': 101}}},
                    {'included': {'allowance_usd': 1, 'balance_usd': 2}}):
            self.assertIsNone(provider.normalize_balance(raw))
        raw = balance_fixture()
        raw.pop('purchased')
        result = provider.normalize_balance(raw)
        self.assertIsNone(result['remaining'])
        self.assertIsNone(result['purchased'])
        self.assertEqual(provider.normalize_balance({'purchased': {'balance_usd': 0}})['kind'], 'purchased')

    def test_connection_never_accepts_embedded_credentials(self):
        with patch.object(provider, 'load_config', return_value={'unified_agent_base_url': 'https://key:secret@host'}):
            with self.assertRaises(ValueError):
                provider.connection()

    def test_cache_and_stale_snapshot_preserve_timestamp(self):
        def fetch(base, token, path, method):
            return {'data': {'id': 'test'}} if path == '/api/me' else {'data': usage_fixture()} if 'usage?' in path else {'data': balance_fixture()} if path == '/api/balance' else {'data': {}}
        with patch.object(provider, 'connection', return_value=('http://test', 'secret', 'key')), patch.object(provider, '_fetch', side_effect=fetch) as fetcher:
            first = provider.snapshot()
            provider.snapshot()
            self.assertEqual(fetcher.call_count, 7)
            provider._CACHE['key']['at'] = 0
            fetcher.side_effect = lambda b, t, p, m: {'data': {'id': 'test'}} if p == '/api/me' else {'error': 'unavailable'}
            stale = provider.snapshot()
            self.assertTrue(stale['ranges']['7d']['stale'])
            self.assertEqual(stale['ranges']['7d']['updated_at'], first['ranges']['7d']['updated_at'])
            self.assertEqual(stale['balance']['data'], first['balance']['data'])
            self.assertTrue(stale['balance']['stale'])
            self.assertNotIn('secret', json.dumps(stale))

    def test_changed_account_does_not_inherit_stale_data(self):
        def fetch(base, token, path, method):
            return {'data': {'id': 'first'}} if path == '/api/me' else {'data': usage_fixture()} if 'usage?' in path else {'data': {}}
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), patch.object(provider, '_fetch', side_effect=fetch) as fetcher:
            first = provider.snapshot()
            provider._CACHE['key']['at'] = 0
            fetcher.side_effect = lambda b, t, p, m: {'data': {'id': 'second'}} if p == '/api/me' else {'error': 'unavailable'}
            second = provider.snapshot()
            self.assertNotEqual(first['account_key'], second['account_key'])
            self.assertIsNone(second['ranges']['7d']['data'])
            self.assertIsNone(second['balance']['data'])


@override_settings(ROOT_URLCONF=__name__, LOGIN_URL='/login/')
class LedgerAndViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('usage-one')
        self.other = get_user_model().objects.create_user('usage-two')
        self.client.force_login(self.user)

    def test_recorded_calls_aggregate_by_user_day_model_without_content(self):
        with patch.object(tracking.timezone, 'now', return_value=NOW):
            tracking.record_usage(user_id=self.user.pk, model='alpha', input_tokens=100, output_tokens=20)
            tracking.record_usage(user_id=self.user.pk, model='alpha', input_tokens=200, output_tokens=None)
            tracking.record_usage(user_id=self.other.pk, model='beta', input_tokens=9999, output_tokens=9999)
        result = tracking.activity(self.user.pk, 7, NOW)
        self.assertEqual(result['totals'], {'calls': 2, 'input_tokens': 300, 'output_tokens': 20, 'missing_output_calls': 1})
        self.assertEqual(result['models'][0]['peak_day'], '2026-10-10')
        self.assertEqual(len(result['daily']), 7)
        self.assertEqual(UsageDaily.objects.filter(user=self.user).count(), 1)
        self.assertNotIn('beta', json.dumps(result))

    def test_gauge_republish_never_adds_another_call(self):
        old_sink = governor._USAGE_SINK
        try:
            governor.register_usage_sink(tracking.record_usage)
            governor.record_call_usage(100, 20, user_id=self.user.pk, model='test')
            governor.report_real_usage(self.user.pk, 123456789, 100, 20, model='test')
            governor.report_real_usage(self.user.pk, 123456789, 100, 20, model='test')
            self.assertEqual(UsageDaily.objects.get(user=self.user).calls, 1)
        finally:
            governor.register_usage_sink(old_sink)

    def test_sink_failure_cannot_break_chat(self):
        with patch.object(governor, '_USAGE_SINK', side_effect=RuntimeError('test')):
            self.assertTrue(governor.record_call_usage(1, 1, user_id=self.user.pk))

    def test_anonymous_reads_redirect_and_post_cannot_write(self):
        self.assertEqual(Client().get('/usage/').status_code, 302)
        self.assertEqual(self.client.post('/usage/', '{}', content_type='application/json').status_code, 405)

    def test_unavailable_provider_keeps_user_ledger(self):
        tracking.record_usage(user_id=self.user.pk, model='alpha', input_tokens=123, output_tokens=4)
        with patch.object(provider, 'snapshot', side_effect=OSError('down')):
            response = self.client.get('/usage/').json()
        self.assertEqual(response['activity']['totals']['input_tokens'], 123)
        self.assertIn('provider_error', response)

    def test_range_and_private_cache_headers(self):
        self.assertEqual(self.client.get('/usage/?range=forever').status_code, 400)
        with patch.object(provider, 'snapshot', return_value=snapshot_fixture()):
            response = self.client.get('/usage/')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response.json()['user_id'], self.user.pk)



class CarriageTests(SimpleTestCase):
    def test_new_assets_have_runtime_and_snapshot_floors(self):
        root = Path(__file__).resolve().parents[2]
        runtime = (root / 'build_runtime_assets.py').read_text(encoding='utf-8')
        snapshot = (root / 'copy_source_assets.py').read_text(encoding='utf-8')
        build = (root / 'build.py').read_text(encoding='utf-8')
        for path_name in ('js/usage_dashboard.js', 'css/usage_dashboard.css'):
            self.assertIn('agent/' + path_name, runtime)
            self.assertIn('Tlamatini/agent/static/agent/' + path_name, snapshot)
        self.assertIn('templates/agent/usage_dialog.html', runtime)
        for module in ('usage_tracking', 'usage_provider', 'usage_views'):
            self.assertIn('--hidden-import=agent.' + module, build)
            self.assertIn('"agent.' + module + '"', build)
            self.assertIn('Tlamatini/agent/' + module + '.py', snapshot)
        self.assertIn('0213_usage_ledger.py', snapshot)

    def test_migration_matches_model_state(self):
        from django.apps import apps
        migration = importlib.import_module('agent.migrations.0213_usage_ledger').Migration('0213_usage_ledger', 'agent')
        state = ProjectState.from_apps(apps)
        for name in ('usagedaily',):
            del state.models['agent', name]
        for operation in migration.operations:
            operation.state_forwards('agent', state)
        actual = ProjectState.from_apps(apps)
        for name in ('usagedaily',):
            self.assertEqual(state.models['agent', name], actual.models['agent', name])
