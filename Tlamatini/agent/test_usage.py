# Tlamatini Author Banner — Angela López Mendoza
"""Usage correctness, isolation, failure handling and source-carriage contracts."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import ssl
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
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
        clock = [1000.0]
        def fetch(base, token, path, method):
            return {'data': {'id': 'test'}} if path == '/api/me' else {'data': usage_fixture()} if 'usage?' in path else {'data': balance_fixture()} if path == '/api/balance' else {'data': {}}
        with patch.object(provider, 'connection', return_value=('http://test', 'secret', 'key')), patch.object(provider, '_fetch', side_effect=fetch) as fetcher, \
                patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            first = provider.snapshot()
            provider.snapshot()
            self.assertEqual(fetcher.call_count, 7)
            clock[0] += 61
            fetcher.side_effect = lambda b, t, p, m: {'data': {'id': 'test'}} if p == '/api/me' else {'error': 'unavailable'}
            stale = provider.snapshot()
            self.assertTrue(stale['ranges']['7d']['stale'])
            self.assertEqual(stale['ranges']['7d']['updated_at'], first['ranges']['7d']['updated_at'])
            self.assertEqual(stale['balance']['data'], first['balance']['data'])
            self.assertTrue(stale['balance']['stale'])
            self.assertNotIn('secret', json.dumps(stale))

    def test_changed_account_does_not_inherit_stale_data(self):
        clock = [1000.0]
        def fetch(base, token, path, method):
            return {'data': {'id': 'first'}} if path == '/api/me' else {'data': usage_fixture()} if 'usage?' in path else {'data': {}}
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), patch.object(provider, '_fetch', side_effect=fetch) as fetcher, \
                patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            first = provider.snapshot()
            clock[0] += 61
            fetcher.side_effect = lambda b, t, p, m: {'data': {'id': 'second'}} if p == '/api/me' else {'error': 'unavailable'}
            second = provider.snapshot()
            self.assertNotEqual(first['account_key'], second['account_key'])
            self.assertIsNone(second['ranges']['7d']['data'])
            self.assertIsNone(second['balance']['data'])

    def test_transport_errors_are_actionable_logged_and_do_not_expose_credentials(self):
        cases = ((urllib.error.URLError(ConnectionRefusedError('private-token')), 'connection', 15),
                 (urllib.error.URLError(TimeoutError('private-token')), 'timeout', 15),
                 (TimeoutError('private-token'), 'timeout', 15),
                 (ConnectionResetError('private-token'), 'connection_reset', 15),
                 (urllib.error.URLError(ConnectionAbortedError('private-token')), 'connection_reset', 15),
                 (ssl.SSLCertVerificationError('private-token'), 'tls', 60),
                 (ValueError('private-token'), 'invalid_json', 15))
        for error, kind, delay in cases:
            with self.subTest(kind=kind), patch.object(provider.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertLogs(provider.logger, level='WARNING') as logs:
                    result = provider._fetch('https://test.invalid', 'private-token', '/api/balance')
                self.assertEqual(result['error_kind'], kind)
                self.assertEqual(result['retry_after'], delay)
                self.assertNotIn('private-token', json.dumps(result) + str(logs.output))

    def test_account_request_is_bodyless_and_recovers_after_disconnection(self):
        """Exercise real HTTP serialization and retry caching, not mocked requests."""
        requests = []
        ready = threading.Event()

        class OllamaFixture(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                body = self.rfile.read(length) if length else b''
                requests.append((self.path, body, self.headers.get('Content-Type')))
                if not ready.is_set() or body:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.respond({'id': 'reconnected-account'})

            def do_GET(self):
                data = balance_fixture() if self.path == '/api/balance' else usage_fixture() if 'usage?' in self.path else {}
                self.respond(data)

            def respond(self, data):
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(('127.0.0.1', 0), OllamaFixture)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        clock = [1000.0]
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with patch.object(provider, 'connection', return_value=(base, '', 'recovery-test')), \
                 patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
                first = provider.snapshot()
                self.assertFalse(first['account_available'])
                self.assertIn('closed this usage connection', first['account_error'])
                self.assertIsNotNone(first['balance']['data'])
                self.assertEqual(first['retry_after_seconds'], 15)
                ready.set()
                clock[0] += 16
                recovered = provider.snapshot()
                self.assertTrue(recovered['account_available'])
                self.assertIsNone(recovered['account_error'])
                self.assertNotIn('retry_after_seconds', recovered)
                provider.snapshot(refresh=True)
                self.assertEqual(requests, [('/api/me', b'', 'application/json')] * 2)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_http_errors_keep_rate_limit_and_authentication_distinct(self):
        headers = Message()
        headers['Retry-After'] = '120'
        for status, kind, delay in ((429, 'rate_limit', 120), (503, 'http_503', 120),
                                    (401, 'authentication', 60), (404, 'unsupported', 60)):
            with self.subTest(status=status), patch.object(provider.urllib.request, 'build_opener') as opener:
                opener.return_value.open.side_effect = urllib.error.HTTPError('https://test.invalid', status, 'private-token', headers, None)
                with self.assertLogs(provider.logger, level='WARNING'):
                    result = provider._fetch('https://test.invalid', 'private-token', '/api/balance')
                self.assertEqual((result['error_kind'], result['retry_after']), (kind, delay))

    def test_retry_after_accepts_http_date_and_rejects_invalid_values(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        self.assertGreaterEqual(provider._retry_after({'Retry-After': future.strftime('%a, %d %b %Y %H:%M:%S GMT')}), 118)
        for value in ('', 'invalid', '-10', 'NaN'):
            self.assertEqual(provider._retry_after({'Retry-After': value}), 60)

    def test_refused_startup_recovers_without_waiting_for_healthy_cache_ttl(self):
        clock = [1000.0]
        def fetch(base, token, path, method):
            if clock[0] == 1000:
                return {'error': 'Connection refused', 'retry_after': 15}
            if path == '/api/me':
                return {'data': {'id': 'same-account'}}
            return {'data': balance_fixture() if path == '/api/balance' else usage_fixture() if 'usage?' in path else {}}
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
             patch.object(provider, '_fetch', side_effect=fetch) as fetcher, \
             patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            failed = provider.snapshot()
            self.assertEqual(failed['retry_after_seconds'], 15)
            clock[0] += 10
            self.assertEqual(provider.snapshot()['retry_after_seconds'], 5)
            self.assertEqual(fetcher.call_count, 7)
            clock[0] += 6
            recovered = provider.snapshot()
            self.assertIsNotNone(recovered['balance']['data'])
            self.assertNotIn('retry_after_seconds', recovered)
            self.assertEqual(fetcher.call_count, 14)
            clock[0] += 20
            provider.snapshot()
            self.assertEqual(fetcher.call_count, 14, 'Healthy snapshots still cache for one minute')

    def test_rate_limit_cannot_be_bypassed_by_refresh(self):
        clock = [1000.0]
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
             patch.object(provider, '_fetch', return_value={'error': 'Rate limited', 'retry_after': 120}) as fetcher, \
             patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertEqual(provider.snapshot()['retry_after_seconds'], 120)
            clock[0] += 61
            self.assertEqual(provider.snapshot()['retry_after_seconds'], 59)
            provider.snapshot(refresh=True)
            self.assertEqual(fetcher.call_count, 7)

    def test_refresh_or_reopen_retries_refused_connection_immediately(self):
        ready = [False]
        def fetch(base, token, path, method):
            if not ready[0]:
                return {'error': 'Connection refused', 'retry_after': 15, 'request_not_sent': True}
            if path == '/api/me':
                return {'data': {'id': 'same-account'}}
            return {'data': balance_fixture() if path == '/api/balance' else usage_fixture() if 'usage?' in path else {}}
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
             patch.object(provider, '_fetch', side_effect=fetch) as fetcher, \
             patch.object(provider.time, 'monotonic', return_value=1000):
            provider.snapshot()
            ready[0] = True
            self.assertIsNone(provider.snapshot()['balance']['data'])
            self.assertIsNotNone(provider.snapshot(refresh=True)['balance']['data'])
            self.assertEqual(fetcher.call_count, 14)
            provider.snapshot(refresh=True)
            self.assertEqual(fetcher.call_count, 14, 'Explicit refresh must preserve healthy cache limits')

    def test_manual_refresh_retries_timed_out_identity_without_repeating_billing(self):
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
             patch.object(provider, '_fetch', return_value={'error': 'Timed out', 'error_kind': 'timeout', 'retry_after': 15, 'request_not_sent': False}) as fetcher:
            provider.snapshot()
            provider.snapshot(refresh=True)
            self.assertEqual(fetcher.call_count, 8)
            self.assertEqual(fetcher.call_args.args[2], '/api/me')

    def test_account_retry_does_not_repeat_successful_billing_requests(self):
        paths = []
        clock = [1000.0]
        ready = [False]

        def fetch(base, token, path, method):
            paths.append(path)
            if path == '/api/me':
                return {'data': {'id': 'recovered'}} if ready[0] else {
                    'error': 'Account connection reset', 'error_kind': 'connection_reset', 'retry_after': 15}
            return {'data': balance_fixture() if path == '/api/balance' else usage_fixture() if 'usage?' in path else {}}

        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
                patch.object(provider, '_fetch', side_effect=fetch), \
                patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            first = provider.snapshot()
            manual = provider.snapshot(refresh=True)
            self.assertEqual(len(paths), 8)
            self.assertEqual(paths.count('/api/balance'), 1)
            self.assertEqual(first['balance']['updated_at'], manual['balance']['updated_at'])
            self.assertIsNotNone(manual['balance']['data'])
            clock[0] += 16
            provider.snapshot()
            self.assertEqual(len(paths), 9, 'Automatic retry must also request only the failed account endpoint')
            ready[0] = True
            recovered = provider.snapshot(refresh=True)
            self.assertTrue(recovered['account_available'])
            self.assertEqual(paths.count('/api/balance'), 2, 'Verify billing again once account identity is established')
            self.assertEqual(paths.count('/api/tags'), 1)

    def test_partial_account_retry_respects_other_endpoint_rate_limits(self):
        paths = []
        clock = [1000.0]

        def fetch(base, token, path, method):
            paths.append(path)
            if path == '/api/me':
                return {'error': 'Account connection reset', 'error_kind': 'connection_reset', 'retry_after': 15}
            if 'usage?' in path:
                return {'error': 'Rate limited', 'error_kind': 'rate_limit', 'retry_after': 120}
            return {'data': balance_fixture() if path == '/api/balance' else {}}

        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
                patch.object(provider, '_fetch', side_effect=fetch), \
                patch.object(provider.time, 'monotonic', side_effect=lambda: clock[0]):
            self.assertEqual(provider.snapshot()['retry_after_seconds'], 15)
            clock[0] += 16
            provider.snapshot()
            provider.snapshot(refresh=True)
            self.assertEqual(paths.count('/api/me'), 3)
            self.assertEqual(paths.count('/api/usage?range=7d'), 1)
            self.assertEqual(paths.count('/api/usage?range=30d'), 1)
            self.assertEqual(paths.count('/api/balance'), 1)

    def test_overlapping_refresh_reports_pending_and_starts_no_duplicate_requests(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(base, token, path, method):
            if path == '/api/me':
                entered.set()
                release.wait(5)
                return {'data': {'id': 'same-account'}}
            return {'data': {}}
        provider._CACHE['key'] = {'at': 0, 'value': {'account': 'previous verified account'}}
        with patch.object(provider, 'connection', return_value=('http://test', '', 'key')), \
             patch.object(provider, '_fetch', side_effect=fetch) as fetcher, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(provider.snapshot)
            try:
                self.assertTrue(entered.wait(3))
                pending = provider.snapshot(refresh=True)
                self.assertTrue(pending['pending'])
                self.assertEqual(pending['account'], 'previous verified account')
            finally:
                release.set()
            future.result(timeout=5)
            self.assertEqual(fetcher.call_count, 7)


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

    def test_explicit_refresh_is_forwarded_without_trusting_other_query_values(self):
        with patch.object(provider, 'snapshot', return_value=snapshot_fixture()) as snapshot:
            self.client.get('/usage/?refresh=1')
            snapshot.assert_called_once_with(refresh=True)
            snapshot.reset_mock()
            self.client.get('/usage/?refresh=anything')
            snapshot.assert_called_once_with(refresh=False)

    def test_menu_disables_when_cloud_is_down_and_local_ledger_is_empty(self):
        with patch.object(provider, 'snapshot', side_effect=OSError('down')):
            state = self.client.get('/usage/').json()['readiness']
        self.assertFalse(state['ready'])
        self.assertEqual(state['retry_after_seconds'], 15)

    def test_menu_enables_automatically_after_provider_recovers(self):
        snapshot = {'balance': {'data': {'kind': 'purchased', 'purchased': 0}},
                    'account_error': 'Account name unavailable', 'retry_after_seconds': 15}
        with patch.object(provider, 'snapshot', side_effect=[OSError('down'), snapshot]):
            self.assertFalse(self.client.get('/usage/').json()['readiness']['ready'])
            state = self.client.get('/usage/').json()['readiness']
        self.assertTrue(state['ready'])
        self.assertEqual(state['default_tab'], 'account')

    def test_menu_can_open_recorded_chat_when_cloud_is_unavailable(self):
        tracking.record_usage(user_id=self.user.pk, model='alpha', input_tokens=123, output_tokens=4)
        with patch.object(provider, 'snapshot', side_effect=OSError('down')):
            state = self.client.get('/usage/').json()['readiness']
        self.assertTrue(state['ready'])
        self.assertEqual(state['default_tab'], 'activity')

    def test_pending_empty_data_is_not_ready_and_zero_cloud_totals_are_valid(self):
        base = {'range': '7d', 'provider': {'pending': True}, 'activity': {'totals': {'calls': 0}}}
        self.assertEqual(views.readiness(base)['state'], 'checking')
        self.assertFalse(views.readiness(base)['ready'])
        base['provider'] = {'ranges': {'7d': {'data': {'totals': {'request_count': 0}}}}}
        self.assertTrue(views.readiness(base)['ready'])
        base['provider']['ranges']['7d']['data']['totals'] = {'request_count': None}
        self.assertFalse(views.readiness(base)['ready'])

    def test_readiness_does_not_expose_another_users_local_activity(self):
        tracking.record_usage(user_id=self.other.pk, model='private', input_tokens=123, output_tokens=4)
        with patch.object(provider, 'snapshot', return_value={}):
            self.assertFalse(self.client.get('/usage/').json()['readiness']['ready'])



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
