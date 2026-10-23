# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Run from a verified foreground PowerShell -NoExit console. Browser checks are headed."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, SimpleTestCase

from .interaction_settings import ACCOUNT_DEFAULTS, FIELDS, snapshot, terminal_preferences, spoken_text, validate
from .interaction_narration import Narration
from .models import InteractionSettings
from .terminal_hub import load_engine


class SettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('interaction-review', password='test-only')
        self.other = get_user_model().objects.create_user('interaction-other', password='test-only')
        self.client.force_login(self.user)
        self.url = '/agent/interaction-settings/'

    def save(self, changes, revision=0):
        return self.client.post(self.url, json.dumps({'preferences': {**ACCOUNT_DEFAULTS, **changes}, 'revision': revision}), content_type='application/json')

    def test_defaults_are_read_only_and_schema_is_shared(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['preferences'], ACCOUNT_DEFAULTS)
        self.assertEqual(response.json()['fields'], FIELDS)
        self.assertFalse(InteractionSettings.objects.exists())

    def test_save_account_isolation_and_conflict(self):
        self.assertEqual(self.save({'editor_wpm': 60, 'execution': 'manual'}).status_code, 200)
        self.assertEqual(snapshot(self.user.pk)[0]['editor_wpm'], 60)
        self.assertEqual(snapshot(self.other.pk)[0]['editor_wpm'], 100)
        self.assertEqual(self.save({'editor_wpm': 80}).status_code, 409)
        self.assertEqual(snapshot(self.user.pk)[0]['editor_wpm'], 60)

    def test_authentication_csrf_and_body_bounds(self):
        self.assertEqual(Client().get(self.url).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, '{}', content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(self.url, 'x' * 17000, content_type='application/json').status_code, 413)

    def test_invalid_values_never_save(self):
        for values in ({'editor_wpm': 0}, {'terminal_wpm': 161}, {'segment_pause': 4}, {'execution': 'auto'},
                       {'narrate_terminal': 'false'}, {'wait_seconds': float('nan')}, {'editor_wpm': True},
                       {'editor_wpm': 50.5}, {'shell': 'bash'}, {'editor_font': 18}, {'user': self.other.pk}):
            with self.subTest(values=values):
                self.assertEqual(self.save(values).status_code, 400)
        self.assertFalse(InteractionSettings.objects.exists())

    def test_linked_speed_uses_supported_intersection(self):
        self.assertEqual(self.save({'link_speeds': True, 'editor_wpm': 40, 'terminal_wpm': 20}).status_code, 200)
        self.assertEqual(snapshot(self.user.pk)[0]['terminal_wpm'], 40)

    def test_chat_preserves_explicit_shell_but_uses_saved_pacing(self):
        from .interaction_settings import chat_preferences
        self.save({'shell': 'cmd', 'terminal_wpm': 40, 'wait_seconds': 240})
        config = {'kind': 'powershell', 'typing_wpm': 160, 'wait_seconds': 10, 'use_my_defaults': True}
        chosen = chat_preferences(config, {'kind': 'pwsh'}, self.user.pk)
        self.assertEqual((chosen['kind'], chosen['typing_wpm'], chosen['wait_seconds']), ('pwsh', 40, 240))
        self.assertIs(chosen['use_my_defaults'], False)
        self.assertEqual(chat_preferences(config, {}, self.user.pk)['kind'], 'cmd')
        from .terminater_tool import shell_kind
        with patch('agent.context_governor.current_user', return_value=self.user.pk):
            self.assertEqual(shell_kind({'text': 'echo Hello'}), 'cmd')
            self.assertEqual(shell_kind({'kind': 'pwsh'}), 'pwsh')

    def test_runtime_inheritance_and_legacy_explicit_fields(self):
        self.save({'terminal_wpm': 80, 'shell': 'cmd', 'wait_seconds': 240, 'hang_seconds': 90, 'user_wait_seconds': 600, 'advisor': False})
        engine = load_engine()
        params = {'user': str(self.user.pk), 'typing_wpm': 30, 'kind': 'powershell', 'wait_seconds': 15}
        explicit = terminal_preferences('run', params, engine)
        self.assertEqual((explicit['typing_wpm'], explicit['kind'], explicit['wait_seconds']), (30, 'powershell', 15))
        inherited = terminal_preferences('run', {**params, 'use_my_defaults': True}, engine)
        self.assertEqual((inherited['typing_wpm'], inherited['kind'], inherited['wait_seconds'], inherited['advisor']), (80, 'cmd', 240, False))
        self.assertEqual((inherited['hang_seconds'], inherited['user_wait_seconds']), (90, 600))

    def test_manual_enter_blocks_aliases_controls_and_base64(self):
        self.save({'execution': 'manual'})
        engine = load_engine()
        hub = engine.TerminalHub()
        self.addCleanup(hub.shutdown)
        hub.prepare_action = lambda action, params: terminal_preferences(action, params, engine)
        for params in ({'text': 'echo one\necho two'}, {'text': 'echo one\r'}, {'text': 'echo one\x1b'},
                       {'text_b64': base64.b64encode(b'echo one\necho two').decode()}):
            with self.subTest(params=params):
                result = hub.call('execute', {'user': str(self.user.pk), **params})
                self.assertEqual(result['code'], 'manual_enter')
        for keys in ('enter', 'return', 'ctrl+m'):
            with self.subTest(keys=keys):
                result = hub.call('send_key', {'user': str(self.user.pk), 'keys': keys})
                self.assertEqual(result['code'], 'manual_enter')
        self.assertFalse(hub.list(str(self.user.pk))['terminals'])
        params = terminal_preferences('run', {'user': str(self.user.pk), 'text': 'echo one', 'submit': True}, engine)
        self.assertIs(params['submit'], False)

    def test_editor_settings_reach_real_tool_payload_and_deadline(self):
        from .interactor.context import Request, current
        from .interactor.tool import perform
        self.save({'editor_wpm': 60, 'segment_pause': 2, 'teaching_detail': 'detailed', 'narrate_editor': True})
        request = Request((str(self.user.pk), 'session'), 'client', self.user.pk, 1, document_id='doc', revision=0)
        token = current.set(request)
        self.addCleanup(current.reset, token)
        before = {'document_id': 'doc', 'revision': 0, 'text': '', 'active': True, 'selection': {'from': 0, 'to': 0}}
        after = {**before, 'revision': 1, 'text': 'FROM '}
        with patch('agent.interactor.tool.hub.call', side_effect=[{'snapshot': before}, {'snapshot': after, 'ok': True}]) as call:
            result = json.loads(perform('type', text='FROM ', typing_wpm=160))
        self.assertTrue(result['verified'])
        self.assertEqual(call.call_args.args[2]['typing_wpm'], 60)
        self.assertEqual(call.call_args.args[2]['preferences']['segment_pause'], 2)
        self.assertGreater(call.call_args.kwargs['timeout'], 125)


class NarrationTests(SimpleTestCase):
    def test_secret_and_handoff_values_never_enter_speech(self):
        preferences = validate({'narration_content': 'both'})
        for secret, text in ((True, 'password-value'), (False, 'echo <<USER:private input>>')):
            result = spoken_text(text, 'password-value', preferences, secret=secret)
            self.assertNotIn('password-value', result)
            self.assertNotIn('<<USER', result)

    def test_only_one_visible_account_tab_receives_narration(self):
        broker, events = Narration(), []
        for user, visible in [('1', True), ('1', True), ('2', True), ('1', False)]:
            key = broker.connect(user, lambda event: events.append(event))
            broker.receive(key, {'t': 'narration_presence', 'visible': visible})
        self.assertTrue(broker.send('1', 'Example'))
        self.assertEqual(len(events), 1)

    def test_receipt_is_bound_to_selected_connection(self):
        broker, ready = Narration(), threading.Event()
        events = []
        selected = broker.connect('1', lambda event: (events.append(event), ready.set()))
        other = broker.connect('2', lambda _: None)
        broker.receive(selected, {'t': 'narration_presence', 'visible': True})
        with ThreadPoolExecutor() as pool:
            future = pool.submit(broker.send, '1', 'Example', wait=True)
            self.assertTrue(ready.wait(2))
            broker.receive(other, {'t': 'narration_receipt', 'id': events[0]['id'], 'status': 'spoken'})
            self.assertFalse(future.done())
            broker.receive(selected, {'t': 'narration_receipt', 'id': events[0]['id'], 'status': 'spoken'})
            self.assertTrue(future.result(timeout=2))
        self.assertFalse(broker.pending)

    def test_disconnect_and_takeover_wake_waiter_without_replay(self):
        for disconnect in (True, False):
            broker, ready, stopped = Narration(), threading.Event(), threading.Event()
            events = []
            key = broker.connect('1', lambda event: (events.append(event), ready.set()))
            broker.receive(key, {'t': 'narration_presence', 'visible': True})
            with ThreadPoolExecutor() as pool:
                future = pool.submit(broker.send, '1', 'Example', wait=True, cancelled=stopped.is_set)
                self.assertTrue(ready.wait(2))
                if disconnect:
                    broker.disconnect(key)
                else:
                    stopped.set()
                self.assertFalse(future.result(timeout=2))
            self.assertEqual(sum(event['t'] == 'narration' for event in events), 1)
            self.assertFalse(broker.pending)

    def test_waiting_without_a_visible_listener_refuses_to_proceed(self):
        self.assertFalse(Narration().send('1', 'Example', wait=True))
