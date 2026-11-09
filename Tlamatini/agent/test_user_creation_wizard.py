# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Distinct deterministic account-wizard cases; no real accounts or consoles.

These tests cover the native request contract and failure boundaries. They do
not replace the separate visible browser-to-console/account-creation checks.
"""
from importlib import import_module
from datetime import datetime, timezone
from pathlib import Path
import re
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from agent import user_creation_wizard as wizard


_legacy = import_module('agent.migrations.0219_user_wizard_graphical_notifications')
_current = import_module('agent.migrations.0223_create_superuser_console_handoff')
TEMPLATES = {
    'catalog_before_0219': _legacy.OLD_WIZARD_PROMPT,
    'catalog_0219': _legacy.WIZARD_PROMPT,
    'catalog_0223': _current.WIZARD_PROMPT,
}
USERNAMES = (
    ('plain', 'angela'),
    ('other_user', 'alice'),
    ('digits', 'admin2'),
    ('dot', 'qa.demo'),
    ('underscore', 'qa_user'),
    ('hyphen', 'qa-user'),
    ('plus', 'qa+test'),
    ('email_shape', 'user@example.test'),
    ('accent', 'Ángela'),
    ('non_latin', 'usuario_長'),
)


def filled(template, username):
    if re.search(r'(?m)^Username:', template):
        return re.sub(r'(?m)^Username:.*$', lambda _: 'Username: ' + username, template, count=1)
    return re.sub(r'\A(.*?named ")[^"\r\n]*("\.)',
                  lambda match: match[1] + username + match[2], template, count=1)


def install_case(cls, name, callback):
    """Each matrix row is a separately named unittest case, not a subtest count."""
    if hasattr(cls, name):
        raise ValueError('Duplicate regression case: ' + name)
    callback.__name__ = name
    setattr(cls, name, callback)


class CatalogAccountIntentTests(SimpleTestCase):
    """Recognize shipped cards, never a broad createsuperuser keyword match."""


for _edition, _template in TEMPLATES.items():
    for _label, _username in USERNAMES:
        def _accepted(self, template=_template, username=_username):
            self.assertEqual(wizard.catalog_request(filled(template, username)), (True, username))
        install_case(CatalogAccountIntentTests, f'test_accept_{_edition}_{_label}', _accepted)

    def _placeholder(self, template=_template):
        self.assertEqual(wizard.catalog_request(template), (True, None))
    install_case(CatalogAccountIntentTests, f'test_placeholder_{_edition}', _placeholder)


_NOT_INSTRUCTIONS = {
    'quoted': lambda text: '"' + text + '"',
    'code_fenced': lambda text: '```text\n' + text + '\n```',
    'explain_only': lambda text: 'Explain this card without executing it:\n' + text,
    'negative_prefix': lambda text: 'Do not execute any command.\n' + text,
    'negative_suffix': lambda text: text + '\nDo not open the console.',
    'custom_suffix': lambda text: text + '\nMy own instruction: do not create users.',
    'changed_first_instruction': lambda text: text.replace('help me', 'do not help me', 1),
    'shell_injection_suffix': lambda text: text + '\nscript=whoami && echo injected',
    'different_instance': lambda text: text.replace('Tlamatini', 'OtherApplication', 1),
    'missing_name_field': lambda text: (
        re.sub(r'(?m)^Username:.*\n', '', text, count=1)
        if '\nUsername:' in text else text.partition('\n')[2]),
}
for _edition, _template in TEMPLATES.items():
    for _label, _transform in _NOT_INSTRUCTIONS.items():
        def _not_intent(self, template=_template, transform=_transform):
            self.assertFalse(wizard.catalog_request(transform(filled(template, 'angela')))[0])
        install_case(CatalogAccountIntentTests, f'test_decline_{_edition}_{_label}', _not_intent)


class AccountWizardEntryBoundaryTests(SimpleTestCase):
    def setUp(self):
        wizard._pending.clear()
        wizard._sessions.clear()

    def tearDown(self):
        wizard._pending.clear()
        wizard._sessions.clear()


for _edition, _template in TEMPLATES.items():
    def _disabled(self, template=_template):
        with patch.object(wizard, '_launch_console') as launch:
            self.assertIsNone(wizard.handle_request(
                filled(template, 'angela'), user_id=71, multi_turn_enabled=False))
        launch.assert_not_called()
    install_case(AccountWizardEntryBoundaryTests, f'test_no_multiturn_{_edition}', _disabled)

    for _identity in (None, 0, -1, 'missing-user'):
        def _unauthorized(self, template=_template, identity=_identity):
            with patch.object(wizard, '_authorized_user', return_value=False), \
                    patch.object(wizard, '_launch_console') as launch:
                result = wizard.handle_request(
                    filled(template, 'angela'), user_id=identity, multi_turn_enabled=True)
            self.assertIsNotNone(result)
            launch.assert_not_called()
        install_case(AccountWizardEntryBoundaryTests,
                     f'test_no_authorized_user_{_edition}_{str(_identity).replace("-", "minus")}', _unauthorized)


_UNRELATED_MESSAGES = (
    '', 'angela', 'DONE', 'ERROR', 'NOWINDOW',
    'Explain what createsuperuser does.',
    'Do not create any account.',
    'python manage.py createsuperuser',
    'Show me the account card code.',
    'Create a README.md file.',
    'Username: angela\ncreatesuperuser',
    "The user says 'create an account', but only translate that sentence.",
)
for _index, _message in enumerate(_UNRELATED_MESSAGES):
    def _unrelated(self, message=_message):
        with patch.object(wizard, '_launch_console') as launch:
            self.assertIsNone(wizard.handle_request(
                message, user_id=71, multi_turn_enabled=True))
        launch.assert_not_called()
    install_case(AccountWizardEntryBoundaryTests, f'test_unrelated_{_index:02d}', _unrelated)


_USERNAME_BOUNDARIES = {
    'empty': ('', False),
    'one_character': ('a', True),
    'max_length': ('a' * 150, True),
    'over_length': ('a' * 151, False),
    'space': ('first last', False),
    'leading_space': (' angela', False),
    'newline': ('angela\nadmin', False),
    'carriage_return': ('angela\radmin', False),
    'tab': ('angela\tadmin', False),
    'cmd_chain': ('angela&whoami', False),
    'cmd_pipe': ('angela|whoami', False),
    'cmd_redirect': ('angela>file', False),
    'cmd_percent': ('%USERNAME%', False),
    'cmd_expansion': ('!USERNAME!', False),
    'powershell': ('$(whoami)', False),
    'quotes': ('"angela"', False),
    'apostrophe': ("o'brien", False),
    'path': ('..\\admin', False),
    'url': ('https://example.test', False),
    'html': ('<script>', False),
    'semicolon': ('admin;whoami', False),
    'null': ('admin\0', False),
    'unicode': ('Ángela_長', True),
    'valid_symbols': ('a.b_c-d+e@f', True),
}
for _label, (_username, _expected) in _USERNAME_BOUNDARIES.items():
    def _validation(self, username=_username, expected=_expected):
        self.assertEqual(wizard._valid_username(username), expected)
    install_case(CatalogAccountIntentTests, f'test_username_boundary_{_label}', _validation)


def session(username='angela', running=True):
    process = Mock(pid=4567)
    process.poll.return_value = None if running else 0
    return {
        'process': process, 'id': 'console-test-id', 'username': username,
        'started': datetime.now(timezone.utc),
        'argv': ['C:/English/Tlamatini.exe', 'createuserconsole'],
        'cwd': 'C:/English',
        'last_reply': 'Waiting for account input.',
        'awaiting_reply': True,
    }


class AccountWizardPolicyTests(SimpleTestCase):
    def setUp(self):
        wizard._pending.clear()
        wizard._sessions.clear()
        self.request = filled(TEMPLATES['catalog_0223'], 'angela')
        self.auth = patch.object(wizard, '_authorized_user', return_value=True)
        self.cancel = patch('agent.cancellation.is_run_cancelled', return_value=False)
        self.auth.start()
        self.cancel.start()
        self.addCleanup(self.auth.stop)
        self.addCleanup(self.cancel.stop)

    def tearDown(self):
        wizard._pending.clear()
        wizard._sessions.clear()

    def call(self, text=None, **options):
        # Status tests answer the owned handoff unless they explicitly supply
        # unrelated/empty history to exercise the conversation boundary.
        if text is not None and 'chat_history' not in options and 71 in wizard._sessions:
            options['chat_history'] = [
                {'role': 'assistant', 'content': wizard._sessions[71].get('last_reply', '')}]
        return wizard.handle_request(self.request if text is None else text, user_id=71,
                                     multi_turn_enabled=True, **options)

    def status(self, result):
        return result['metadata']['user_creation_wizard']['status']

    def test_cancel_before_approval_never_opens_or_requests_permission(self):
        with patch('agent.cancellation.is_run_cancelled', return_value=True), \
                patch('agent.exec_permission.get_broker') as broker, \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call(ask_execs_enabled=True, run_epoch=9)
        self.assertEqual(self.status(result), 'cancelled')
        broker.assert_not_called()
        launch.assert_not_called()

    def test_cancel_after_approval_never_opens(self):
        broker = Mock()
        broker.request_permission.return_value = 'proceed'
        with patch('agent.cancellation.is_run_cancelled', side_effect=[False, True]), \
                patch('agent.exec_permission.get_broker', return_value=broker), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call(ask_execs_enabled=True, run_epoch=9)
        self.assertEqual(self.status(result), 'cancelled')
        broker.request_permission.assert_called_once()
        launch.assert_not_called()

    def test_ask_execs_missing_broker_denies(self):
        with patch('agent.exec_permission.get_broker', return_value=None), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call(ask_execs_enabled=True)
        self.assertEqual(self.status(result), 'denied')
        self.assertIsNotNone(result['metadata']['exec_report_denied'])
        launch.assert_not_called()

    def test_ask_execs_approval_opens_exactly_one_console(self):
        broker = Mock()
        broker.request_permission.return_value = 'proceed'
        with patch('agent.exec_permission.get_broker', return_value=broker), \
                patch.object(wizard, '_launch_console', return_value=session()) as launch:
            result = self.call(ask_execs_enabled=True)
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once_with(71, 'angela')
        self.assertEqual(broker.request_permission.call_args.args[0]['shell'], 'native')

    def test_no_tools_required_for_native_account_handoff(self):
        with patch('agent.exec_permission.get_broker') as broker, \
                patch.object(wizard, '_launch_console', return_value=session()) as launch:
            result = self.call()
        broker.assert_not_called()
        launch.assert_called_once()
        self.assertEqual(result['metadata']['tool_calls_log'], [])
        self.assertIn('DONE', result['output'])
        self.assertTrue(result['output'].endswith('END-RESPONSE'))

    def test_pending_name_does_not_launch(self):
        with patch.object(wizard, '_launch_console') as launch:
            result = self.call(TEMPLATES['catalog_0223'])
        self.assertEqual(self.status(result), 'username_required')
        self.assertIn(71, wizard._pending)
        launch.assert_not_called()

    def test_pending_name_continues_only_the_same_catalog_exchange(self):
        card = TEMPLATES['catalog_0223']
        wizard._pending[71] = True
        history = [{'role': 'user', 'content': card},
                   {'role': 'assistant', 'content': 'Enter the username'}]
        with patch.object(wizard, '_launch_console', return_value=session()) as launch:
            result = self.call('angela', chat_history=history)
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once_with(71, 'angela')
        self.assertNotIn(71, wizard._pending)

    def test_pending_name_ignores_appended_current_question_in_history(self):
        wizard._pending[71] = True
        history = [{'type': 'human', 'content': TEMPLATES['catalog_0223']},
                   {'type': 'ai', 'content': 'Enter the username'},
                   {'type': 'human', 'content': 'alice'}]
        with patch.object(wizard, '_launch_console', return_value=session('alice')) as launch:
            result = self.call('alice', chat_history=history)
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once_with(71, 'alice')

    def test_pending_different_user_does_not_claim_a_bare_username(self):
        wizard._pending[99] = True
        history = [{'type': 'human', 'content': TEMPLATES['catalog_0223']},
                   {'type': 'ai', 'content': 'Enter the username'}]
        with patch.object(wizard, '_launch_console') as launch:
            self.assertIsNone(self.call('angela', chat_history=history))
        launch.assert_not_called()

    def test_repeated_card_reuses_living_console(self):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_focus_owned_console') as focus, \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call()
        self.assertEqual(self.status(result), 'waiting_for_user')
        focus.assert_called_once_with(owned)
        launch.assert_not_called()

    def test_closed_console_allows_one_explicit_card_retry(self):
        wizard._sessions[71] = session(running=False)
        with patch.object(wizard, '_launch_console', return_value=session()) as launch:
            result = self.call()
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once_with(71, 'angela')

    def test_done_does_not_claim_an_unverified_account(self):
        wizard._sessions[71] = session()
        with patch.object(wizard, '_created_account', return_value=False), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call('DONE')
        self.assertEqual(self.status(result), 'waiting_for_user')
        self.assertIn('not yet confirmed', result['output'])
        launch.assert_not_called()

    def test_done_checks_real_account_state_before_completed_result(self):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_created_account', return_value=True) as created, \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call('DONE: Superuser created successfully')
        self.assertEqual(self.status(result), 'completed')
        created.assert_called_once_with(owned)
        launch.assert_not_called()

    def test_nowindow_attempts_only_owned_focus_without_relaunch(self):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_focus_owned_console') as focus, \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call('NOWINDOW')
        self.assertEqual(self.status(result), 'waiting_for_user')
        focus.assert_called_once_with(owned)
        launch.assert_not_called()


for _decision in ('deny', 'cancel', 'timeout', '', None):
    def _denied(self, decision=_decision):
        broker = Mock()
        broker.request_permission.return_value = decision
        with patch('agent.exec_permission.get_broker', return_value=broker), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call(ask_execs_enabled=True)
        self.assertEqual(self.status(result), 'denied')
        launch.assert_not_called()
    install_case(AccountWizardPolicyTests, f'test_permission_denies_{str(_decision) or "empty"}', _denied)

for _label, _failure in (
        ('access_denied', PermissionError('Access denied')),
        ('missing_executable', FileNotFoundError('Missing executable')),
        ('generic_os_error', OSError('Console launch unavailable')),
        ('html_error', OSError('<script>bad</script>'))):
    def _failed_launch(self, failure=_failure):
        with patch.object(wizard, '_launch_console', side_effect=failure) as launch:
            result = self.call()
        self.assertEqual(self.status(result), 'launch_failed')
        self.assertNotIn('<script>', result['output'])
        self.assertNotIn(71, wizard._sessions)
        launch.assert_called_once()
    install_case(AccountWizardPolicyTests, f'test_launch_failure_{_label}', _failed_launch)

for _label, _history in (
        ('empty', []),
        ('other_question', [{'role': 'user', 'content': 'Hello'},
                            {'role': 'assistant', 'content': 'Enter the username'}]),
        ('other_answer', [{'role': 'user', 'content': TEMPLATES['catalog_0223']},
                          {'role': 'assistant', 'content': 'What do you want to do next?'}]),
        ('named_card', [{'role': 'user', 'content': filled(TEMPLATES['catalog_0223'], 'alice')},
                        {'role': 'assistant', 'content': 'Enter the username'}]),
        ('wrong_roles', [{'role': 'assistant', 'content': TEMPLATES['catalog_0223']},
                         {'role': 'user', 'content': 'Enter the username'}])):
    def _stale(self, history=_history):
        wizard._pending[71] = True
        with patch.object(wizard, '_launch_console') as launch:
            self.assertIsNone(self.call('angela', chat_history=history))
        launch.assert_not_called()
    install_case(AccountWizardPolicyTests, f'test_pending_rejects_{_label}', _stale)

for _label, _reply in (('bare', 'ERROR'), ('details', 'ERROR: The username already exists.'),
                       ('untrusted_html', 'ERROR: <script>not-safe</script>')):
    def _error(self, reply=_reply):
        wizard._sessions[71] = session()
        with patch.object(wizard, '_launch_console') as launch:
            result = self.call(reply)
        self.assertEqual(self.status(result), 'error_reported')
        self.assertNotIn('<script>', result['output'])
        launch.assert_not_called()
    install_case(AccountWizardPolicyTests, f'test_account_error_{_label}', _error)


class AccountWizardTrustedCommandTests(SimpleTestCase):
    """The command uses exact argv, never shell text or a username interpolation."""


_RUNTIME_LOCATIONS = {
    'simple': 'C:/Tlamatini',
    'spaces': 'C:/Program Files/XAIHT/Tlamatini',
    'unicode': 'C:/Aplicación/Ángela/Tlamatini',
    'ampersand': 'C:/Apps & Tools/Tlamatini',
    'percent': 'C:/Apps%Test/Tlamatini',
    'exclamation': 'C:/Apps!Test/Tlamatini',
    'apostrophe': "C:/App's/Tlamatini",
}
for _mode in ('source', 'frozen'):
    for _label, _root in _RUNTIME_LOCATIONS.items():
        def _command(self, mode=_mode, root=_root):
            executable = str(Path(root, 'Tlamatini.exe' if mode == 'frozen'
                                  else 'python/python.exe'))
            module = str(Path(root, 'Tlamatini/agent/user_creation_wizard.py'))
            with patch.object(wizard.sys, 'executable', executable), \
                    patch.object(wizard.sys, 'frozen', mode == 'frozen', create=True), \
                    patch.object(wizard, '__file__', module):
                argv, cwd = wizard.management_command()
            expected = [str(Path(executable).resolve())]
            if mode == 'source':
                expected.append(str(Path(module).resolve().parents[1] / 'manage.py'))
            expected.append('createuserconsole')
            self.assertEqual(argv, expected)
            self.assertEqual(cwd, str(Path(executable).resolve().parent) if mode == 'frozen'
                             else str(Path(module).resolve().parents[1]))
            self.assertNotIn('angela', argv)
        install_case(AccountWizardTrustedCommandTests, f'test_argv_{_mode}_{_label}', _command)


class AccountWizardCleanupProtectionTests(SimpleTestCase):
    def setUp(self):
        wizard._sessions.clear()

    def tearDown(self):
        wizard._sessions.clear()

    def protected_sets(self):
        from agent import command_watchdog, orphan_reaper
        with patch('agent.models.ChatAgentRun.objects.filter') as runs, \
                patch('agent.models.AgentProcess.objects.all') as processes, \
                patch('agent.terminal_hub.live_pids', return_value=set()), \
                patch('agent.external_mcp_manager.external_mcp_root_pids', return_value=set()):
            runs.return_value.only.return_value = []
            processes.return_value.only.return_value = []
            return (orphan_reaper._tracked_running_pids(),
                    command_watchdog._external_mcp_protected_pids())

    def test_both_cleanup_paths_protect_the_owned_live_console_handle(self):
        owned = session()
        wizard._sessions[71] = owned
        self.assertEqual(wizard.live_pids(), {owned['process'].pid})
        for protected in self.protected_sets():
            self.assertIn(owned['process'].pid, protected)

    def test_finished_owned_console_does_not_leave_a_stale_pid_exemption(self):
        closed = session(running=False)
        wizard._sessions[71] = closed
        self.assertEqual(wizard.live_pids(), set())
        for protected in self.protected_sets():
            self.assertNotIn(closed['process'].pid, protected)


class AccountWizardConversationBoundaryTests(SimpleTestCase):
    """Follow-ups belong to the preceding owned handoff, not arbitrary chat."""
    setUp = AccountWizardPolicyTests.setUp
    tearDown = AccountWizardPolicyTests.tearDown
    call = AccountWizardPolicyTests.call
    status = AccountWizardPolicyTests.status

    def test_invalid_name_remains_at_validation_without_calling_a_model(self):
        initial = self.call(_current.WIZARD_PROMPT)
        history = [{'role': 'assistant', 'content': initial['output']}]
        with patch.object(wizard, '_launch_console') as launch:
            result = self.call('Angela Smith', chat_history=history)
        self.assertIsNotNone(result)
        self.assertEqual(self.status(result), 'username_required')
        launch.assert_not_called()

    def test_repeated_invalid_names_can_be_corrected_in_the_same_pending_chain(self):
        previous = self.call(_current.WIZARD_PROMPT)
        with patch.object(wizard, '_launch_console', return_value=session()) as launch:
            for invalid in ('Angela Smith', 'a' * 151, 'admin&whoami'):
                history = [{'role': 'assistant', 'content': previous['output']}]
                previous = self.call(invalid, chat_history=history)
                self.assertEqual(self.status(previous), 'username_required')
            launch.assert_not_called()
            result = self.call('angela', chat_history=[
                {'role': 'assistant', 'content': previous['output']}])
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once_with(71, 'angela')
        self.assertNotIn(71, wizard._pending)

    def test_pending_reply_accepts_history_with_html_and_terminal_marker_removed(self):
        previous = self.call(_current.WIZARD_PROMPT)
        sanitized = wizard._normalized_reply(previous['output'])
        with patch.object(wizard, '_launch_console', return_value=session()) as launch:
            result = self.call('angela', chat_history=[
                {'role': 'assistant', 'content': sanitized}])
        self.assertEqual(self.status(result), 'waiting_for_user')
        launch.assert_called_once()

    def test_pending_state_does_not_consume_an_answer_to_another_assistant_message(self):
        self.call(_current.WIZARD_PROMPT)
        with patch.object(wizard, '_launch_console') as launch:
            result = self.call('alice', chat_history=[
                {'role': 'assistant', 'content': 'Which document should I open?'}])
        self.assertIsNone(result)
        self.assertNotIn(71, wizard._pending)
        launch.assert_not_called()

    def test_status_without_owned_previous_assistant_reply_is_ordinary_chat(self):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_created_account') as account:
            result = self.call('ERROR', chat_history=[])
        self.assertIsNone(result)
        self.assertFalse(owned['awaiting_reply'])
        self.assertIn(owned['process'].pid, wizard.live_pids())
        account.assert_not_called()

    def test_status_after_other_chat_does_not_revive_a_stale_wizard(self):
        owned = session()
        wizard._sessions[71] = owned
        self.assertIsNone(self.call('ERROR', chat_history=[
            {'role': 'assistant', 'content': 'Here is your unrelated build result.'}]))
        self.assertIsNone(self.call('DONE', chat_history=[
            {'role': 'assistant', 'content': owned['last_reply']}]))
        self.assertIn(owned['process'].pid, wizard.live_pids())

    def test_completed_account_retires_reply_context_but_keeps_console_ownership(self):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_created_account', return_value=True) as account:
            result = self.call('DONE')
            self.assertEqual(self.status(result), 'completed')
            self.assertIsNone(self.call('ERROR'))
        account.assert_called_once_with(owned)
        self.assertFalse(owned['awaiting_reply'])
        self.assertIn(owned['process'].pid, wizard.live_pids())

    def test_unauthorized_followup_retires_pending_context(self):
        previous = self.call(_current.WIZARD_PROMPT)
        with patch.object(wizard, '_authorized_user', return_value=False), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call('angela', chat_history=[
                {'role': 'assistant', 'content': previous['output']}])
        self.assertEqual(self.status(result), 'refused')
        self.assertNotIn(71, wizard._pending)
        launch.assert_not_called()

    def test_cancelled_followup_retires_pending_context(self):
        previous = self.call(_current.WIZARD_PROMPT)
        with patch('agent.cancellation.is_run_cancelled', return_value=True), \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call('angela', chat_history=[
                {'role': 'assistant', 'content': previous['output']}])
        self.assertEqual(self.status(result), 'cancelled')
        self.assertNotIn(71, wizard._pending)
        launch.assert_not_called()

    def test_candidate_admission_performs_no_authorization_or_launch(self):
        with patch.object(wizard, '_authorized_user') as authorize, \
                patch.object(wizard, '_launch_console') as launch:
            self.assertTrue(wizard.request_candidate(
                self.request, user_id=71, multi_turn_enabled=True))
        authorize.assert_not_called()
        launch.assert_not_called()

    def test_candidate_does_not_admit_ordinary_chat_without_wizard_state(self):
        self.assertFalse(wizard.request_candidate(
            'Please summarize my README.', user_id=71, multi_turn_enabled=True))

    def test_candidate_disabled_multiturn_does_not_admit_even_exact_card(self):
        self.assertFalse(wizard.request_candidate(
            self.request, user_id=71, multi_turn_enabled=False))

    def test_candidate_admits_invalid_pending_username_for_the_real_validator(self):
        self.call(_current.WIZARD_PROMPT)
        self.assertTrue(wizard.request_candidate(
            'not a valid username', user_id=71, multi_turn_enabled=True))

    def test_candidate_does_not_admit_an_old_completed_status(self):
        owned = session()
        owned['awaiting_reply'] = False
        wizard._sessions[71] = owned
        self.assertFalse(wizard.request_candidate('DONE', user_id=71, multi_turn_enabled=True))

    def test_result_html_normalization_preserves_user_visible_text(self):
        owned = session()
        wizard._sessions[71] = owned
        wizard._result('Wait for <b>angela</b> &amp; finish.', session=owned)
        with patch.object(wizard, '_created_account', return_value=False):
            result = self.call('DONE', chat_history=[
                {'role': 'assistant', 'content': 'Wait for angela & finish.'}])
        self.assertEqual(self.status(result), 'waiting_for_user')


for _label, _reply, _kind in (
        ('english_done', 'DONE', 'done'), ('spanish_done', 'HECHO', 'done'),
        ('english_nowindow', 'NOWINDOW', 'nowindow'),
        ('spanish_nowindow', 'SIN VENTANA', 'nowindow')):
    def _alias(self, reply=_reply, kind=_kind):
        owned = session()
        wizard._sessions[71] = owned
        with patch.object(wizard, '_created_account', return_value=False) as account, \
                patch.object(wizard, '_focus_owned_console') as focus, \
                patch.object(wizard, '_launch_console') as launch:
            result = self.call(reply)
        self.assertEqual(self.status(result), 'waiting_for_user')
        self.assertEqual(account.call_count, int(kind == 'done'))
        self.assertEqual(focus.call_count, int(kind == 'nowindow'))
        launch.assert_not_called()
    install_case(AccountWizardConversationBoundaryTests, f'test_reply_alias_{_label}', _alias)




