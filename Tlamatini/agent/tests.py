import importlib.util
import ast
import os
import shutil
import tempfile
from functools import lru_cache
from unittest.mock import AsyncMock, call, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from agent import views
from agent.consumers import AgentConsumer, _sanitize_context_filename
from agent.models import AgentMessage
from agent.path_guard import (
    REJECTION_MESSAGE,
    get_runtime_agent_root,
    is_path_allowed,
    resolve_runtime_agent_path,
    safe_join_under,
)
from agent.rag.interface import _validate_accesses_in_prompt
from agent.services.filesystem import generate_tree_view_content
from tlamatini.asgi import application

try:
    from agent.chain_files_search_lcel import FileSearchRAGChain
except Exception:  # pragma: no cover - optional dependency path
    FileSearchRAGChain = None


def _load_seeded_prompt_contents():
    migration_path = os.path.join(
        os.path.dirname(__file__),
        'migrations',
        '0002_populate_db.py',
    )
    with open(migration_path, 'r', encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), filename=migration_path)

    prompt_contents = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != 'get_or_create':
            continue
        for keyword in node.keywords:
            if keyword.arg != 'defaults' or not isinstance(keyword.value, ast.Dict):
                continue
            for key_node, value_node in zip(keyword.value.keys, keyword.value.values):
                if (
                    isinstance(key_node, ast.Constant)
                    and key_node.value == 'promptContent'
                    and isinstance(value_node, ast.Constant)
                    and isinstance(value_node.value, str)
                ):
                    prompt_contents.append(value_node.value)
    return prompt_contents


@lru_cache(maxsize=1)
def _load_ender_module_for_tests():
    module_path = os.path.join(
        os.path.dirname(__file__),
        'agents',
        'ender',
        'ender.py',
    )
    spec = importlib.util.spec_from_file_location('agent_ender_module_for_tests', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Ender module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
    return module


class P0HardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='secret123')
        self.other_user = User.objects.create_user(username='bob', password='secret123')

    def test_agent_page_only_shows_current_users_messages(self):
        AgentMessage.objects.create(user=self.user, conversation_user=self.user, message='visible to alice')
        AgentMessage.objects.create(user=self.other_user, conversation_user=self.other_user, message='must stay private')

        self.client.force_login(self.user)
        response = self.client.get(reverse('agent_page'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['initial_messages']), 1)
        self.assertEqual(response.context['initial_messages'][0]['message'], 'visible to alice')

    def test_agent_page_keeps_bot_history_for_current_user(self):
        bot_user = User.objects.create_user(username='LLM_Bot', password='secret123')
        AgentMessage.objects.create(user=self.user, conversation_user=self.user, message='visible to alice')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.user, message='assistant reply')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.other_user, message='must stay private')

        self.client.force_login(self.user)
        response = self.client.get(reverse('agent_page'))

        self.assertEqual(
            [message['message'] for message in response.context['initial_messages']],
            ['visible to alice', 'assistant reply']
        )

    def test_load_canvas_requires_login(self):
        response = self.client.get(reverse('load_canvas', args=['demo.py']))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/?next=', response['Location'])

    def test_clear_pool_requires_post_for_authenticated_users(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('clear_pool'))
        self.assertEqual(response.status_code, 405)

    def test_clear_pool_enforces_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse('clear_pool'),
            HTTP_X_AGENT_SESSION_ID='csrf-check',
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_messages_for_user_is_scoped(self):
        bot_user = User.objects.create_user(username='LLM_Bot', password='secret123')
        AgentMessage.objects.create(user=self.user, conversation_user=self.user, message='delete me')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.user, message='delete me too')
        AgentMessage.objects.create(user=self.other_user, conversation_user=self.other_user, message='keep me')

        consumer = AgentConsumer()
        async_to_sync(consumer.delete_messages_for_user)(self.user)

        self.assertFalse(AgentMessage.objects.filter(conversation_user=self.user).exists())
        self.assertTrue(AgentMessage.objects.filter(conversation_user=self.other_user).exists())

    def test_anonymous_websocket_connection_is_rejected(self):
        communicator = WebsocketCommunicator(application, '/ws/agent/')
        connected, _subprotocol = async_to_sync(communicator.connect)()
        self.assertFalse(connected)

    def test_login_invalid_credentials_render_inline_feedback(self):
        response = self.client.post(
            reverse('home'),
            {'username': self.user.username, 'password': 'wrong-password'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'login-error-panel')
        self.assertContains(response, self.user.username)


class P1HardeningTests(TestCase):
    def test_sanitize_context_filename_rejects_path_escapes(self):
        self.assertEqual(_sanitize_context_filename('safe_file.py'), 'safe_file.py')
        self.assertIsNone(_sanitize_context_filename('../secret.py'))
        self.assertIsNone(_sanitize_context_filename('nested\\secret.py'))
        self.assertIsNone(_sanitize_context_filename('..'))
        self.assertIsNone(_sanitize_context_filename('bad:name.py'))

    def test_safe_join_under_rejects_parent_traversal(self):
        runtime_root = get_runtime_agent_root()
        self.assertIsNone(safe_join_under(runtime_root, '..'))
        self.assertIsNotNone(safe_join_under(runtime_root, 'context_files'))

    def test_resolve_runtime_agent_path_accepts_runtime_child_directory(self):
        runtime_root = get_runtime_agent_root()
        with tempfile.TemporaryDirectory(dir=runtime_root) as temp_dir:
            relative_name = os.path.basename(temp_dir)
            resolved = resolve_runtime_agent_path(relative_name)
            self.assertEqual(os.path.realpath(resolved), os.path.realpath(temp_dir))

    def test_resolve_runtime_agent_path_rejects_parent_traversal(self):
        self.assertIsNone(resolve_runtime_agent_path('..'))
        self.assertIsNone(resolve_runtime_agent_path('..\\outside'))

    def test_generate_tree_view_content_rejects_outside_directory(self):
        result = generate_tree_view_content('..')
        self.assertIn('outside the allowed paths', result)

    def test_generate_tree_view_content_accepts_runtime_directory(self):
        runtime_root = get_runtime_agent_root()
        with tempfile.TemporaryDirectory(dir=runtime_root) as temp_dir:
            sample_file = os.path.join(temp_dir, 'example.txt')
            with open(sample_file, 'w', encoding='utf-8') as handle:
                handle.write('hello world')

            result = generate_tree_view_content(os.path.basename(temp_dir))

            self.assertIn('example.txt', result)
            self.assertIn('Total files: 1', result)


class PromptPathHardeningTests(TestCase):
    def _build_chain_without_init(self):
        if FileSearchRAGChain is None:
            self.skipTest('FileSearchRAGChain dependencies are unavailable in this environment.')
        return FileSearchRAGChain.__new__(FileSearchRAGChain)

    def test_file_search_direct_path_rejects_disallowed_absolute_path(self):
        chain = self._build_chain_without_init()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(outside_dir, ignore_errors=True))
        if is_path_allowed(outside_dir):
            self.skipTest('Temporary directory unexpectedly falls inside allowed paths.')

        outside_file = os.path.join(outside_dir, 'secret.txt')
        with open(outside_file, 'w', encoding='utf-8') as handle:
            handle.write('top secret')

        prompt = f"show secret.txt in {outside_dir}"
        result = async_to_sync(chain.fetch_files_context)({"__question": prompt})

        self.assertEqual(result, REJECTION_MESSAGE)

    def test_file_search_direct_path_allows_allowed_absolute_path(self):
        chain = self._build_chain_without_init()
        runtime_root = get_runtime_agent_root()
        with tempfile.TemporaryDirectory(dir=runtime_root) as temp_dir:
            if not is_path_allowed(temp_dir):
                self.skipTest('Runtime temporary directory unexpectedly falls outside allowed paths.')

            sample_file = os.path.join(temp_dir, 'allowed.txt')
            with open(sample_file, 'w', encoding='utf-8') as handle:
                handle.write('allowed content')

            prompt = f"show allowed.txt in {temp_dir}"
            result = async_to_sync(chain.fetch_files_context)({"__question": prompt})

            self.assertIn('<FILE_CONTENT_START>', result)
            self.assertIn('allowed content', result)

    def test_file_search_rejects_outside_grpc_result_path(self):
        chain = self._build_chain_without_init()
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(outside_dir, ignore_errors=True))
        if is_path_allowed(outside_dir):
            self.skipTest('Temporary directory unexpectedly falls inside allowed paths.')

        outside_file = os.path.join(outside_dir, 'secret.txt')
        with open(outside_file, 'w', encoding='utf-8') as handle:
            handle.write('top secret')

        chain.async_call_grpc_server = AsyncMock(return_value=[outside_file])
        result = async_to_sync(chain.fetch_files_context)({
            "action": "show",
            "show": {"file_name": "secret.txt", "base_path_key": None, "include_hidden": False},
            "__question": "show secret.txt",
        })

        self.assertEqual(result, REJECTION_MESSAGE)


class PromptValidationDecisionTests(TestCase):
    def test_seeded_prompts_use_deterministic_validation_only(self):
        seeded_prompts = _load_seeded_prompt_contents()
        self.assertGreater(len(seeded_prompts), 0)

        with patch('agent.rag.interface._acces_aimed_prompt', side_effect=AssertionError('LLM path classifier should not run for seeded prompts.')), \
             patch('agent.rag.interface._indirect_file_access_prompt', side_effect=AssertionError('LLM indirect classifier should not run for seeded prompts.')):
            for prompt in seeded_prompts:
                result = _validate_accesses_in_prompt(prompt)
                self.assertIsNone(result, msg=prompt)

    def test_explicit_outside_absolute_path_is_rejected_deterministically(self):
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(outside_dir, ignore_errors=True))
        if is_path_allowed(outside_dir):
            self.skipTest('Temporary directory unexpectedly falls inside allowed paths.')

        outside_file = os.path.join(outside_dir, 'secret.txt')
        prompt = f"Open {outside_file}, please."

        with patch('agent.rag.interface._acces_aimed_prompt', side_effect=AssertionError('Deterministic rejection should happen before LLM fallback.')):
            result = _validate_accesses_in_prompt(prompt)

        self.assertEqual(result, REJECTION_MESSAGE)

    def test_relative_path_access_is_rejected_deterministically(self):
        with patch('agent.rag.interface._indirect_file_access_prompt', side_effect=AssertionError('Deterministic relative-path rejection should happen before LLM fallback.')):
            result = _validate_accesses_in_prompt('Open ..\\secret.txt, please.')

        self.assertIn('not relative routes/paths are allowed', result)

    def test_informational_prompt_with_outside_path_can_use_llm_fallback(self):
        outside_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(outside_dir, ignore_errors=True))
        if is_path_allowed(outside_dir):
            self.skipTest('Temporary directory unexpectedly falls inside allowed paths.')

        outside_file = os.path.join(outside_dir, 'secret.txt')
        prompt = f'Explain why the code hardcodes "{outside_file}" and why that is risky.'

        with patch('agent.rag.interface._acces_aimed_prompt', return_value=False) as mock_classifier:
            result = _validate_accesses_in_prompt(prompt)

        self.assertIsNone(result)
        mock_classifier.assert_called_once()


class EnderAgentTests(TestCase):
    def test_clear_reanimation_assets_only_removes_reanim_files(self):
        ender_module = _load_ender_module_for_tests()

        with tempfile.TemporaryDirectory() as agent_dir:
            reanim_pos = os.path.join(agent_dir, 'reanim.pos')
            reanim_counter = os.path.join(agent_dir, 'reanim.counter')
            agent_log = os.path.join(agent_dir, 'counter_1.log')
            custom_pos = os.path.join(agent_dir, 'custom.pos')

            for path in (reanim_pos, reanim_counter, agent_log, custom_pos):
                with open(path, 'w', encoding='utf-8') as handle:
                    handle.write('sample')

            with patch.object(ender_module, 'get_agent_directory', return_value=agent_dir):
                removed = ender_module.clear_reanimation_assets('counter_1')

            self.assertEqual(removed, 2)
            self.assertFalse(os.path.exists(reanim_pos))
            self.assertFalse(os.path.exists(reanim_counter))
            self.assertTrue(os.path.exists(agent_log))
            self.assertTrue(os.path.exists(custom_pos))

    def test_main_clears_reanimation_assets_for_resolved_targets_only(self):
        ender_module = _load_ender_module_for_tests()
        config = {
            'target_agents': ['counter_1', 'monitor_log_1', 'raiser_1'],
            'output_agents': [],
        }

        with tempfile.TemporaryDirectory() as pool_dir, \
                patch.object(ender_module, 'load_config', return_value=config), \
                patch.object(ender_module, 'write_pid_file'), \
                patch.object(ender_module, 'remove_pid_file'), \
                patch.object(ender_module, 'launch_agent'), \
                patch.object(ender_module, 'get_pool_path', return_value=pool_dir), \
                patch.object(
                    ender_module,
                    'terminate_agent',
                    side_effect=['terminated', 'not_running', 'failed'],
                ), \
                patch.object(ender_module, 'clear_reanimation_assets', return_value=1) as mock_clear, \
                patch.object(ender_module.time, 'sleep'):
            ender_module.main()

        self.assertEqual(
            mock_clear.call_args_list,
            [call('counter_1'), call('monitor_log_1')],
        )


class RestartAgentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='restart-user', password='secret123')
        self.client.force_login(self.user)

    def test_context_menu_restart_preserves_reanimation_assets(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            agent_dir = os.path.join(pool_dir, 'counter_1')
            os.makedirs(agent_dir, exist_ok=True)

            script_path = os.path.join(agent_dir, 'counter.py')
            reanim_pos = os.path.join(agent_dir, 'reanim.pos')
            reanim_counter = os.path.join(agent_dir, 'reanim.counter')
            with open(script_path, 'w', encoding='utf-8') as handle:
                handle.write('print("hello")\n')
            with open(reanim_pos, 'w', encoding='utf-8') as handle:
                handle.write('offset: 10\n')
            with open(reanim_counter, 'w', encoding='utf-8') as handle:
                handle.write('counter: 3\n')

            fake_process = type('FakeProcess', (), {'pid': 4321})()

            with patch('agent.views.get_pool_path', return_value=pool_dir), \
                    patch('agent.views.get_python_command', return_value=['python']), \
                    patch('agent.views.get_agent_env', return_value={}), \
                    patch(
                        'agent.views._stop_running_agent_processes_for_restart',
                        return_value=(True, 1, None),
                    ) as mock_stop, \
                    patch('agent.views.subprocess.Popen', return_value=fake_process) as mock_popen, \
                    patch('agent.views._write_pid_file') as mock_write_pid:
                response = self.client.post(reverse('restart_agent', args=['counter-1']))

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload['success'])
            self.assertEqual(payload['pid'], 4321)
            self.assertTrue(os.path.exists(reanim_pos))
            self.assertTrue(os.path.exists(reanim_counter))
            mock_stop.assert_called_once_with(agent_dir, 'counter_1', 'counter.py')
            mock_popen.assert_called_once()
            mock_write_pid.assert_called_once_with(agent_dir, 4321)

    def test_context_menu_restart_fails_if_agent_cannot_be_fully_stopped(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            agent_dir = os.path.join(pool_dir, 'counter_1')
            os.makedirs(agent_dir, exist_ok=True)

            script_path = os.path.join(agent_dir, 'counter.py')
            reanim_pos = os.path.join(agent_dir, 'reanim.pos')
            with open(script_path, 'w', encoding='utf-8') as handle:
                handle.write('print("hello")\n')
            with open(reanim_pos, 'w', encoding='utf-8') as handle:
                handle.write('offset: 10\n')

            with patch('agent.views.get_pool_path', return_value=pool_dir), \
                    patch(
                        'agent.views._stop_running_agent_processes_for_restart',
                        return_value=(False, 1, 'remaining pid'),
                    ), \
                    patch('agent.views.subprocess.Popen') as mock_popen:
                response = self.client.post(reverse('restart_agent', args=['counter-1']))

            self.assertEqual(response.status_code, 409)
            payload = response.json()
            self.assertFalse(payload['success'])
            self.assertEqual(payload['killed_count'], 1)
            self.assertTrue(os.path.exists(reanim_pos))
            mock_popen.assert_not_called()

    def test_stop_running_agent_processes_requires_no_remaining_processes(self):
        proc = type('FakeProcess', (), {'pid': 7777})()

        with patch.object(
            views,
            '_find_agent_processes_for_restart',
            side_effect=[[proc], [proc], [proc], [proc], [proc]],
        ), \
                patch.object(views, '_terminate_process_tree_for_restart', return_value=True), \
                patch.object(views.time, 'sleep'):
            stop_ok, killed_count, error_message = views._stop_running_agent_processes_for_restart(
                'C:\\pool\\counter_1',
                'counter_1',
                'counter.py',
            )

        self.assertFalse(stop_ok)
        self.assertEqual(killed_count, 1)
        self.assertIn('Remaining PID(s): [7777]', error_message)
