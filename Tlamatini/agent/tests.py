import importlib.util
import ast
import csv
import json
import os
import subprocess
import shutil
import tempfile
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from langchain_core.documents import Document
import yaml

from agent import views
from agent.consumers import AgentConsumer, _sanitize_context_filename
from agent.global_state import get_request_state, global_state
from agent.mcp_agent import CapabilityAwareToolAgentExecutor
from agent.models import AgentMessage
from agent.path_guard import (
    REJECTION_MESSAGE,
    get_runtime_agent_root,
    is_path_allowed,
    resolve_runtime_agent_path,
    safe_join_under,
)
from agent.capability_registry import select_context_capabilities_for_request, select_tools_for_request
from agent.global_execution_planner import build_global_execution_plan
from agent.rag.interface import _validate_accesses_in_prompt
from agent.rag.interface import ask_rag
from agent.rag.factory import _apply_context_prefetch, _build_loaded_documents_fallback_context
from agent.rag.chains.basic import BasicPromptOnlyChain
from agent.rag.chains.unified import UnifiedAgentChain
from agent.services.filesystem import generate_tree_view_content
from agent import tools as agent_tools
from tlamatini.asgi import application

try:
    import agent.chain_files_search_lcel as files_chain_module
    from agent.chain_files_search_lcel import FileSearchRAGChain
except Exception:  # pragma: no cover - optional dependency path
    FileSearchRAGChain = None
    files_chain_module = None
from agent.rag.chains.unified import _has_explicit_file_listing_context, _should_include_file_manifest


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


@lru_cache(maxsize=1)
def _load_parametrizer_module_for_tests():
    module_path = os.path.join(
        os.path.dirname(__file__),
        'agents',
        'parametrizer',
        'parametrizer.py',
    )
    spec = importlib.util.spec_from_file_location('agent_parametrizer_module_for_tests', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Parametrizer module from {module_path}')

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
        async def _attempt_connect():
            communicator = WebsocketCommunicator(application, '/ws/agent/')
            connected = False
            try:
                connected, _subprotocol = await communicator.connect()
                return connected
            finally:
                if connected:
                    await communicator.disconnect()

        connected = async_to_sync(_attempt_connect)()
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

    def test_file_search_builds_application_plan_for_project_home_file_request(self):
        chain = self._build_chain_without_init()

        plan = chain._build_deterministic_plan(
            "Show me README.md located in the project home, and summarize it."
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan["action"], "show")
        self.assertEqual(plan["show"]["file_name"], "README.md")
        self.assertEqual(plan["show"]["base_path_key"], "application")

    def test_file_search_show_prefers_application_root_and_compacts_context(self):
        chain = self._build_chain_without_init()
        runtime_root = get_runtime_agent_root()
        with tempfile.TemporaryDirectory(dir=runtime_root) as temp_dir:
            if not is_path_allowed(temp_dir):
                self.skipTest('Runtime temporary directory unexpectedly falls outside allowed paths.')

            root_readme = os.path.join(temp_dir, 'README.md')
            nested_dir = os.path.join(temp_dir, 'docs')
            nested_readme = os.path.join(nested_dir, 'README.md')
            os.makedirs(nested_dir, exist_ok=True)

            with open(root_readme, 'w', encoding='utf-8') as handle:
                handle.write('root readme content')
            with open(nested_readme, 'w', encoding='utf-8') as handle:
                handle.write('nested readme content')

            chain.async_call_grpc_server = AsyncMock(return_value=[nested_readme, root_readme])

            with patch('agent.chain_files_search_lcel._get_application_root', return_value=temp_dir):
                result = async_to_sync(chain.fetch_files_context)({
                    "action": "show",
                    "show": {"file_name": "README.md", "base_path_key": "application", "include_hidden": False},
                    "__question": "Show me README.md located in the project home, and summarize it.",
                    "__multi_turn_enabled": True,
                })

            self.assertIn('File resolved directly from the application root:', result)
            self.assertIn(root_readme, result)
            self.assertIn('root readme content', result)
            self.assertNotIn("Found 2 files matching 'README.md':", result)
            chain.async_call_grpc_server.assert_not_awaited()

    def test_file_search_deterministic_plan_runs_only_when_multi_turn_enabled(self):
        chain = self._build_chain_without_init()

        with patch.object(
            chain,
            '_build_deterministic_plan',
            side_effect=AssertionError('deterministic plan must not run in legacy mode'),
        ), patch.object(chain, 'should_fetch_files_context', AsyncMock(return_value=False)) as mock_route:
            result = async_to_sync(chain.intelligent_context_fetch)({
                "question": "Show me README.md located in the project home, and summarize it.",
                "multi_turn_enabled": False,
            })

        mock_route.assert_awaited_once()
        self.assertEqual(result["files_context"], "")

    def test_file_search_multi_turn_uses_deterministic_plan_for_project_home_request(self):
        chain = self._build_chain_without_init()

        with patch.object(
            chain,
            'fetch_files_context',
            AsyncMock(return_value='resolved context'),
        ) as mock_fetch, \
                patch.object(
                    chain,
                    'should_fetch_files_context',
                    AsyncMock(side_effect=AssertionError('route step should be skipped')),
                ), \
                patch.object(
                    chain,
                    'plan_file_search',
                    AsyncMock(side_effect=AssertionError('planner step should be skipped')),
                ):
            result = async_to_sync(chain.intelligent_context_fetch)({
                "question": "Show me README.md located in the project home, and summarize it.",
                "multi_turn_enabled": True,
            })

        self.assertEqual(result["files_context"], 'resolved context')
        passed_plan = mock_fetch.await_args.args[0]
        self.assertEqual(passed_plan["action"], "show")
        self.assertEqual(passed_plan["show"]["base_path_key"], "application")
        self.assertTrue(passed_plan["__multi_turn_enabled"])


class UnifiedFileContextGatingTests(TestCase):
    def test_manifest_is_not_forced_for_exact_single_file_requests(self):
        question = "Show me README.md located in the project home, and summarize it."

        self.assertFalse(_should_include_file_manifest(question, question))

    def test_explicit_file_listing_context_detector_ignores_generic_file_words(self):
        self.assertFalse(
            _has_explicit_file_listing_context(
                "This README explains how files are organized in the project."
            )
        )
        self.assertTrue(
            _has_explicit_file_listing_context(
                "FILE MANIFEST (all loaded files in knowledge base):\n- README.md"
            )
        )


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


class LoadedContextFallbackTests(TestCase):
    def test_build_loaded_documents_fallback_context_includes_manifest_and_content(self):
        config = {
            'max_context_chars': 4000,
            'redact_secrets_in_context': False,
            'retrieval_strategy': {'enable_hierarchical_context': False},
        }
        documents = [
            Document(
                page_content='def example():\n    return 42\n',
                metadata={'source': 'context_files/example.py', 'filename': 'example.py', 'file_role': 'other'},
            )
        ]

        context_blob = _build_loaded_documents_fallback_context(documents, config)

        self.assertIn('FILE MANIFEST (loaded files):', context_blob)
        self.assertIn('context_files/example.py', context_blob)
        self.assertIn('def example(): return 42', context_blob)

    @patch('agent.rag.chains.basic.DBChatHistoryLoader.load', return_value=[])
    def test_basic_prompt_only_chain_uses_loaded_context_in_answer_payload(self, _mock_history_load):
        chain = BasicPromptOnlyChain.__new__(BasicPromptOnlyChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = 'FILE MANIFEST (loaded files):\n- example.py\n\n[1] example.py -- def example(): return 42'
        chain.answer_chain = SimpleNamespace(invoke=lambda payload: payload)
        chain.last_programs_name = []
        chain.httpx_client_instance = None
        chain._to_text = lambda response: response

        result = chain.invoke({'input': 'Summarize the loaded code', 'chat_history': []})

        self.assertIn('example.py', result['answer']['context'])
        self.assertIn('def example(): return 42', result['answer']['context'])

    def test_unified_agent_chain_injects_loaded_context_into_agent_input(self):
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'output': 'ok'}

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = 'FILE MANIFEST (loaded files):\n- example.py\n\n[1] example.py -- def example(): return 42'
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({'input': 'Summarize the loaded code', 'chat_history': [SimpleNamespace(content='prior turn')]})

        self.assertEqual(result['answer'], 'ok')
        self.assertIn('Loaded Context from Knowledge Base Fallback:', captured['payload']['input'])
        self.assertIn('example.py', captured['payload']['input'])
        self.assertIn('def example(): return 42', captured['payload']['input'])

    def test_unified_agent_chain_forwards_multi_turn_flag_to_executor(self):
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'output': 'ok'}

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = ''
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({
            'input': 'Check the available tools',
            'chat_history': [],
            'multi_turn_enabled': True,
        })

        self.assertEqual(result['answer'], 'ok')
        self.assertTrue(captured['payload']['multi_turn_enabled'])


class CapabilitySelectionTests(TestCase):
    def test_select_tools_for_request_prefers_wrapped_agent_and_run_controls(self):
        tools = [
            SimpleNamespace(name='chat_agent_crawler', description='Crawl URLs and capture content.'),
            SimpleNamespace(name='chat_agent_run_status', description='Get the current status of a wrapped run.'),
            SimpleNamespace(name='chat_agent_run_log', description='Read the latest log excerpt of a wrapped run.'),
            SimpleNamespace(name='chat_agent_run_stop', description='Stop a wrapped run by run id.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]

        selected = select_tools_for_request(
            'Crawl https://example.com and keep checking the run status and logs.',
            tools,
            max_selected=2,
        )
        selected_names = [tool.name for tool in selected]

        self.assertIn('chat_agent_crawler', selected_names)
        self.assertIn('chat_agent_run_status', selected_names)
        self.assertIn('chat_agent_run_log', selected_names)
        self.assertIn('chat_agent_run_stop', selected_names)
        self.assertNotIn('execute_command', selected_names)

    def test_select_tools_for_request_falls_back_to_all_tools_when_uncertain(self):
        tools = [
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
            SimpleNamespace(name='get_current_time', description='Return the current date and time.'),
        ]

        selected = select_tools_for_request('Investigate this carefully.', tools)

        self.assertEqual([tool.name for tool in selected], [tool.name for tool in tools])


class ContextCapabilitySelectionTests(TestCase):
    def test_select_context_capabilities_for_system_request(self):
        selected = select_context_capabilities_for_request(
            'What is the current CPU usage and memory load?',
            system_enabled=True,
            files_enabled=True,
        )

        self.assertEqual(selected, ('system_context',))

    def test_select_context_capabilities_for_file_request(self):
        selected = select_context_capabilities_for_request(
            'Show me README.md in the project and list related files.',
            system_enabled=True,
            files_enabled=True,
        )

        self.assertEqual(selected, ('files_context',))

    def test_select_context_capabilities_can_choose_both(self):
        selected = select_context_capabilities_for_request(
            'Check disk usage and find README.md in the repo.',
            system_enabled=True,
            files_enabled=True,
        )

        self.assertEqual(selected, ('system_context', 'files_context'))


class GlobalExecutionPlannerTests(TestCase):
    def test_build_global_execution_plan_creates_context_only_dag_when_context_is_sufficient(self):
        tools = [
            SimpleNamespace(name='get_current_time', description='Return the current date and time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]

        plan = build_global_execution_plan(
            'Show me README.md in the project home and summarize it.',
            tools,
            system_enabled=True,
            files_enabled=True,
        )

        self.assertEqual(plan.execution_mode, 'context_only')
        self.assertEqual(plan.selected_contexts, ('files_context',))
        self.assertEqual(plan.selected_tool_names, ())
        self.assertEqual(plan.nodes[0].node_id, 'prefetch:files_context')
        self.assertEqual(plan.nodes[-1].node_id, 'answer:final')

    def test_build_global_execution_plan_creates_tool_and_monitor_nodes_for_wrapped_agent_requests(self):
        tools = [
            SimpleNamespace(name='chat_agent_gitter', description='Run git operations through the Gitter template agent.'),
            SimpleNamespace(name='chat_agent_run_status', description='Get the current status of a wrapped run.'),
            SimpleNamespace(name='chat_agent_run_log', description='Read the latest log excerpt of a wrapped run.'),
            SimpleNamespace(name='chat_agent_run_stop', description='Stop a wrapped run by run id.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]

        plan = build_global_execution_plan(
            'Check disk usage, then run git status in the repo and monitor the run status and logs.',
            tools,
            system_enabled=True,
            files_enabled=True,
        )

        self.assertEqual(plan.execution_mode, 'tool_augmented')
        self.assertIn('system_context', plan.selected_contexts)
        self.assertIn('files_context', plan.selected_contexts)
        self.assertIn('chat_agent_gitter', plan.selected_tool_names)
        self.assertIn('chat_agent_run_status', plan.selected_tool_names)
        self.assertIn('chat_agent_run_log', plan.selected_tool_names)
        monitor_nodes = [node for node in plan.nodes if node.stage == 'monitor']
        self.assertGreaterEqual(len(monitor_nodes), 1)


class FrozenModeCompatibilityTests(TestCase):
    def test_file_search_default_config_path_uses_executable_directory_when_frozen(self):
        if files_chain_module is None:
            self.skipTest('FileSearchRAGChain dependencies are unavailable in this environment.')

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_executable = os.path.join(temp_dir, 'Tlamatini.exe')
            with open(fake_executable, 'w', encoding='utf-8') as handle:
                handle.write('stub exe')

            with patch.object(files_chain_module.sys, 'frozen', True, create=True), \
                    patch.object(files_chain_module.sys, 'executable', fake_executable):
                config_path = files_chain_module._get_default_config_path()
                application_root = files_chain_module._get_application_root()

        self.assertEqual(config_path, os.path.join(temp_dir, 'config.json'))
        self.assertEqual(application_root, temp_dir)

    def test_file_search_chain_loads_default_config_from_frozen_executable_directory(self):
        if files_chain_module is None:
            self.skipTest('FileSearchRAGChain dependencies are unavailable in this environment.')

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_executable = os.path.join(temp_dir, 'Tlamatini.exe')
            with open(fake_executable, 'w', encoding='utf-8') as handle:
                handle.write('stub exe')

            config_path = os.path.join(temp_dir, 'config.json')
            with open(config_path, 'w', encoding='utf-8') as handle:
                json.dump({
                    'ollama_base_url': 'http://frozen.example:11434',
                    'chained-model': 'frozen-model',
                    'mcp_files_search_grpc_target': 'frozen-host:50505',
                }, handle)

            fake_llm = SimpleNamespace()
            with patch.object(files_chain_module.sys, 'frozen', True, create=True), \
                    patch.object(files_chain_module.sys, 'executable', fake_executable), \
                    patch('agent.chain_files_search_lcel.OllamaLLM', return_value=fake_llm) as mock_llm:
                chain = FileSearchRAGChain()

        self.assertIs(chain.llm, fake_llm)
        self.assertEqual(chain.grpc_target, 'frozen-host:50505')
        self.assertEqual(mock_llm.call_args.kwargs['base_url'], 'http://frozen.example:11434')
        self.assertEqual(mock_llm.call_args.kwargs['model'], 'frozen-model')

    def test_template_agent_roots_include_frozen_install_layouts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_executable = os.path.join(temp_dir, 'Tlamatini.exe')
            with open(fake_executable, 'w', encoding='utf-8') as handle:
                handle.write('stub exe')

            direct_agents = os.path.join(temp_dir, 'agents')
            nested_agents = os.path.join(temp_dir, 'Tlamatini', 'agent', 'agents')
            os.makedirs(direct_agents, exist_ok=True)
            os.makedirs(nested_agents, exist_ok=True)

            with patch.object(agent_tools.sys, 'frozen', True, create=True), \
                    patch.object(agent_tools.sys, 'executable', fake_executable):
                roots = agent_tools._get_template_agents_roots()

        self.assertIn(os.path.realpath(os.path.abspath(direct_agents)), roots)
        self.assertIn(os.path.realpath(os.path.abspath(nested_agents)), roots)


class ContextPrefetchGatingTests(TestCase):
    def setUp(self):
        global_state.set_state('mcp_system_status', 'enabled')
        global_state.set_state('mcp_files_search_status', 'enabled')

    def test_legacy_prefetch_keeps_both_fetchers_when_multi_turn_disabled(self):
        with patch('agent.rag.factory.SystemRAGChain', object()), \
                patch('agent.rag.factory.FileSearchRAGChain', object()), \
                patch(
                    'agent.rag.factory.get_system_context_sync',
                    side_effect=lambda payload: {**payload, 'system_context': 'system'},
                ) as mock_system, \
                patch(
                    'agent.rag.factory.get_files_context_sync',
                    side_effect=lambda payload: {**payload, 'files_context': 'files'},
                ) as mock_files:
            result = _apply_context_prefetch(
                {'input': 'What is the current CPU usage?', 'multi_turn_enabled': False},
                'legacy-test',
            )

        mock_system.assert_called_once()
        mock_files.assert_called_once()
        self.assertEqual(result['system_context'], 'system')
        self.assertEqual(result['files_context'], 'files')

    def test_phase2_prefetch_selects_only_matching_contexts(self):
        with patch('agent.rag.factory.SystemRAGChain', object()), \
                patch('agent.rag.factory.FileSearchRAGChain', object()), \
                patch(
                    'agent.rag.factory.get_system_context_sync',
                    side_effect=lambda payload: {**payload, 'system_context': 'system'},
                ) as mock_system, \
                patch(
                    'agent.rag.factory.get_files_context_sync',
                    side_effect=lambda payload: {**payload, 'files_context': 'files'},
                ) as mock_files:
            result = _apply_context_prefetch(
                {'input': 'Show me README.md in the project.', 'multi_turn_enabled': True},
                'phase2-test',
            )

        mock_system.assert_not_called()
        mock_files.assert_called_once()
        self.assertNotIn('system_context', result)
        self.assertEqual(result['files_context'], 'files')

    def test_phase3_prefetch_attaches_global_execution_plan_when_multi_turn_enabled(self):
        with patch('agent.rag.factory.SystemRAGChain', object()), \
                patch('agent.rag.factory.FileSearchRAGChain', object()), \
                patch(
                    'agent.rag.factory.get_mcp_tools',
                    return_value=[SimpleNamespace(name='get_current_time', description='Return the current date and time.')],
                ), \
                patch(
                    'agent.rag.factory.get_system_context_sync',
                    side_effect=lambda payload: {**payload, 'system_context': 'system'},
                ) as mock_system, \
                patch(
                    'agent.rag.factory.get_files_context_sync',
                    side_effect=lambda payload: {**payload, 'files_context': 'files'},
                ) as mock_files:
            result = _apply_context_prefetch(
                {'input': 'Show me README.md in the project and summarize it.', 'multi_turn_enabled': True},
                'phase3-plan-test',
            )

        mock_system.assert_not_called()
        mock_files.assert_called_once()
        self.assertIn('global_execution_plan', result)
        self.assertEqual(result['global_execution_plan']['execution_mode'], 'context_only')
        self.assertEqual(result['global_execution_plan']['selected_contexts'], ['files_context'])
        self.assertIn('planner_summary', result)


class AskRagMultiTurnTests(TestCase):
    def test_ask_rag_passes_multi_turn_flag_to_chain_payload(self):
        captured = {}

        class _FakeChain:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'answer': 'ok'}

        with patch('agent.rag.interface._validate_accesses_in_prompt', return_value=None):
            result = ask_rag(
                _FakeChain(),
                {'input': 'What time is it?', 'multi_turn_enabled': True},
                inet_enabled=False,
            )

        self.assertEqual(result, 'ok')
        self.assertTrue(captured['payload']['multi_turn_enabled'])

    def test_unified_agent_chain_forwards_global_execution_plan_to_executor(self):
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'output': 'ok'}

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = ''
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        plan = {
            'planner_version': 'phase3_global_dag_v1',
            'execution_mode': 'context_only',
            'selected_contexts': ['files_context'],
            'selected_tool_names': [],
            'nodes': [{'node_id': 'answer:final', 'stage': 'answer', 'capability_key': 'final_response'}],
        }
        result = chain.invoke({
            'input': 'Show me README.md in the project.',
            'chat_history': [SimpleNamespace(content='prior turn')],
            'multi_turn_enabled': True,
            'global_execution_plan': plan,
            'planner_summary': 'planner summary here',
        })

        self.assertEqual(result['answer'], 'ok')
        self.assertEqual(captured['payload']['global_execution_plan'], plan)
        self.assertEqual(captured['payload']['planner_summary'], 'planner summary here')

    def test_ask_rag_bypasses_prompt_shape_validation_when_multi_turn_enabled(self):
        captured = {}

        class _FakeChain:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'answer': 'ok'}

        with patch('agent.rag.interface._validate_accesses_in_prompt', return_value=None):
            result = ask_rag(
                _FakeChain(),
                {
                    'input': 'README.md located in the project home, then summary',
                    'multi_turn_enabled': True,
                },
                inet_enabled=False,
            )

        self.assertEqual(result, 'ok')
        self.assertEqual(
            captured['payload']['input'],
            'README.md located in the project home, then summary',
        )
        self.assertTrue(captured['payload']['multi_turn_enabled'])

    def test_ask_rag_keeps_legacy_prompt_shape_validation_when_multi_turn_disabled(self):
        class _FakeChain:
            def invoke(self, payload):
                raise AssertionError('legacy prompt validation should reject before chain invocation')

        result = ask_rag(
            _FakeChain(),
            {
                'input': 'README.md located in the project home, then summary',
                'multi_turn_enabled': False,
            },
            inet_enabled=False,
        )

        self.assertEqual(
            result,
            'Please rephrase your input as a clear question or command. '
            'Examples: "How do I...?", "What is...?", "Show me...", "Create a...", or "Explain..."',
        )


class MultiTurnBackgroundLaunchTests(TestCase):
    def test_capability_executor_scopes_console_suppression_to_multi_turn_requests(self):
        observed = []

        class _RecordingExecutor:
            def invoke(self, payload):
                observed.append(get_request_state('suppress_visible_consoles', False))
                return {'output': 'ok'}

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = object()
        executor.preeliminary_prompt = ''
        executor.tools = []
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor()
        executor._get_executor_for_tools = lambda tools_subset: _RecordingExecutor()

        with patch('agent.mcp_agent.select_tools_for_request', return_value=[]):
            result = CapabilityAwareToolAgentExecutor.invoke(
                executor,
                {'input': 'run something', 'multi_turn_enabled': True},
            )

        self.assertEqual(result, {'output': 'ok'})
        self.assertEqual(observed, [True])
        self.assertFalse(get_request_state('suppress_visible_consoles', False))

    def test_capability_executor_uses_global_plan_tool_subset_before_selector(self):
        captured = {}

        class _RecordingExecutor:
            def __init__(self, tool_names):
                self.tool_names = tool_names

            def invoke(self, payload):
                captured['tool_names'] = self.tool_names
                captured['payload'] = payload
                return {'output': 'ok'}

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = object()
        executor.preeliminary_prompt = ''
        executor.tools = [
            SimpleNamespace(name='get_current_time', description='Return current time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor(['legacy'])
        executor._get_executor_for_tools = lambda tools_subset: _RecordingExecutor([tool.name for tool in tools_subset])

        with patch('agent.mcp_agent.select_tools_for_request', side_effect=AssertionError('selector should not run when a global plan is present')):
            result = CapabilityAwareToolAgentExecutor.invoke(
                executor,
                {
                    'input': 'Tell me the current time.',
                    'multi_turn_enabled': True,
                    'global_execution_plan': {
                        'planner_version': 'phase3_global_dag_v1',
                        'execution_mode': 'tool_augmented',
                        'selected_tool_names': ['get_current_time'],
                        'selected_contexts': [],
                        'nodes': [],
                    },
                    'planner_summary': 'use get_current_time only',
                },
            )

        self.assertEqual(result, {'output': 'ok'})
        self.assertEqual(captured['tool_names'], ['get_current_time'])
        self.assertEqual(captured['payload']['planner_summary'], 'use get_current_time only')

    def test_capability_executor_allows_context_only_global_plan_with_no_tools(self):
        captured = {}

        class _RecordingExecutor:
            def __init__(self, tool_names):
                self.tool_names = tool_names

            def invoke(self, payload):
                captured['tool_names'] = self.tool_names
                captured['payload'] = payload
                return {'output': 'ok'}

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = object()
        executor.preeliminary_prompt = ''
        executor.tools = [
            SimpleNamespace(name='get_current_time', description='Return current time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor(['legacy'])
        executor._get_executor_for_tools = lambda tools_subset: _RecordingExecutor([tool.name for tool in tools_subset])

        with patch('agent.mcp_agent.select_tools_for_request', side_effect=AssertionError('selector should not run when a global plan is present')):
            result = CapabilityAwareToolAgentExecutor.invoke(
                executor,
                {
                    'input': 'Show me README.md in the project home and summarize it.',
                    'multi_turn_enabled': True,
                    'global_execution_plan': {
                        'planner_version': 'phase3_global_dag_v1',
                        'execution_mode': 'context_only',
                        'selected_tool_names': [],
                        'selected_contexts': ['files_context'],
                        'nodes': [],
                    },
                    'planner_summary': 'context only plan',
                },
            )

        self.assertEqual(result, {'output': 'ok'})
        self.assertEqual(captured['tool_names'], [])

    def test_capability_executor_ignores_global_plan_when_multi_turn_disabled(self):
        captured = {}

        class _RecordingExecutor:
            def __init__(self, label):
                self.label = label

            def invoke(self, payload):
                captured['label'] = self.label
                captured['payload'] = payload
                return {'output': 'ok'}

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = object()
        executor.preeliminary_prompt = ''
        executor.tools = [
            SimpleNamespace(name='get_current_time', description='Return current time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor('legacy')
        executor._get_executor_for_tools = lambda tools_subset: _RecordingExecutor([tool.name for tool in tools_subset])

        result = CapabilityAwareToolAgentExecutor.invoke(
            executor,
            {
                'input': 'Tell me the current time.',
                'multi_turn_enabled': False,
                'global_execution_plan': {
                    'planner_version': 'phase3_global_dag_v1',
                    'execution_mode': 'tool_augmented',
                    'selected_tool_names': ['get_current_time'],
                    'selected_contexts': [],
                    'nodes': [],
                },
            },
        )

        self.assertEqual(result, {'output': 'ok'})
        self.assertEqual(captured['label'], 'legacy')
        self.assertEqual(captured['payload'], {'input': 'Tell me the current time.'})

    def test_launch_in_new_terminal_keeps_legacy_shell_launch_when_not_suppressed(self):
        with patch('agent.tools.subprocess.Popen', return_value=SimpleNamespace(pid=1234)) as mock_popen:
            agent_tools.launch_in_new_terminal(r'C:\Temp\demo.py', '--flag "hello world"')

        args, kwargs = mock_popen.call_args
        self.assertTrue(kwargs['shell'])
        self.assertIn('start "Tlamatini Console" cmd /k', args[0])

    def test_launch_in_new_terminal_uses_headless_background_launch_when_suppressed(self):
        with patch('agent.tools.subprocess.Popen', return_value=SimpleNamespace(pid=1234)) as mock_popen, \
                patch('agent.tools.get_request_state', return_value=True):
            agent_tools.launch_in_new_terminal(r'C:\Temp\demo.py', '--flag "hello world"')

        args, kwargs = mock_popen.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][1], r'C:\Temp\demo.py')
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertFalse(kwargs.get('shell', False))
        if os.name == 'nt':
            self.assertNotEqual(kwargs.get('creationflags', 0), 0)
        else:
            self.assertTrue(kwargs.get('start_new_session'))

    def test_start_template_agent_process_keeps_legacy_console_when_not_suppressed(self):
        with patch('agent.tools.subprocess.Popen', return_value=SimpleNamespace(pid=4321)) as mock_popen:
            agent_tools._start_template_agent_process('python.exe', r'C:\Temp\agent.py', r'C:\Temp')

        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ['python.exe', r'C:\Temp\agent.py'])
        self.assertEqual(kwargs['cwd'], r'C:\Temp')
        if os.name == 'nt':
            self.assertEqual(
                kwargs.get('creationflags', 0),
                getattr(subprocess, 'CREATE_NEW_CONSOLE', 0),
            )
        else:
            self.assertNotIn('start_new_session', kwargs)

    def test_start_template_agent_process_uses_headless_background_launch_when_suppressed(self):
        with patch('agent.tools.subprocess.Popen', return_value=SimpleNamespace(pid=4321)) as mock_popen, \
                patch('agent.tools.get_request_state', return_value=True):
            agent_tools._start_template_agent_process('python.exe', r'C:\Temp\agent.py', r'C:\Temp')

        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ['python.exe', r'C:\Temp\agent.py'])
        self.assertEqual(kwargs['cwd'], r'C:\Temp')
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        if os.name == 'nt':
            self.assertNotEqual(kwargs.get('creationflags', 0), 0)
        else:
            self.assertTrue(kwargs.get('start_new_session'))


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


class OpenAgentInstanceInAppTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='open-in-app-user', password='secret123')
        self.client.force_login(self.user)

    def test_open_in_app_resolves_agent_instance_directory_for_explorer(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            agent_dir = os.path.join(pool_dir, 'counter_1')
            os.makedirs(agent_dir, exist_ok=True)

            with patch('agent.views.get_pool_path', return_value=pool_dir), \
                    patch('agent.views.subprocess.Popen') as mock_popen:
                response = self.client.post(reverse('open_in_app'), {
                    'app_id': 'explorer',
                    'agent_name': 'counter-1',
                })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})
        mock_popen.assert_called_once_with(['explorer', os.path.realpath(agent_dir)])

    def test_open_in_app_opens_cmd_in_agent_instance_directory(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            agent_dir = os.path.join(pool_dir, 'counter_1')
            os.makedirs(agent_dir, exist_ok=True)

            with patch('agent.views.get_pool_path', return_value=pool_dir), \
                    patch('agent.views.os.name', 'nt'), \
                    patch('agent.views.subprocess.Popen') as mock_popen:
                response = self.client.post(reverse('open_in_app'), {
                    'app_id': 'cmd',
                    'agent_name': 'counter-1',
                })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'success': True})
        mock_popen.assert_called_once_with(
            ['cmd.exe', '/K'],
            cwd=os.path.realpath(agent_dir),
            creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0),
        )


class ParametrizerMarkerMappingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='parametrizer-marker-user', password='secret123')
        self.client.force_login(self.user)

    def test_get_parametrizer_dialog_data_includes_configured_markers(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            parametrizer_dir = os.path.join(pool_dir, 'parametrizer_1')
            target_dir = os.path.join(pool_dir, 'prompter_1')
            os.makedirs(parametrizer_dir, exist_ok=True)
            os.makedirs(target_dir, exist_ok=True)

            with open(os.path.join(parametrizer_dir, 'config.yaml'), 'w', encoding='utf-8') as handle:
                yaml.safe_dump({
                    'source_agent': 'file_extractor_1',
                    'target_agent': 'prompter_1',
                    'source_agents': ['file_extractor_1'],
                    'target_agents': ['prompter_1'],
                }, handle, sort_keys=False)

            with open(os.path.join(target_dir, 'config.yaml'), 'w', encoding='utf-8') as handle:
                yaml.safe_dump({
                    'prompt': 'Please summarize:\n\n{content}\n\nSource: {file_path}',
                    'llm': {
                        'host': 'http://localhost:11434',
                        'model': 'gpt-oss:120b-cloud',
                    },
                }, handle, sort_keys=False)

            with patch('agent.views.get_pool_path', return_value=pool_dir):
                response = self.client.get(reverse('get_parametrizer_dialog_data', args=['parametrizer-1']))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('prompt', payload['target_params'])
        self.assertCountEqual(payload['target_markers']['prompt'], ['content', 'file_path'])
        self.assertCountEqual(payload['source_fields'], ['file_path', 'response_body'])

    def test_save_parametrizer_scheme_persists_target_marker_column(self):
        with tempfile.TemporaryDirectory() as pool_dir:
            parametrizer_dir = os.path.join(pool_dir, 'parametrizer_1')
            os.makedirs(parametrizer_dir, exist_ok=True)

            with patch('agent.views.get_pool_path', return_value=pool_dir):
                response = self.client.post(
                    reverse('save_parametrizer_scheme', args=['parametrizer-1']),
                    data=json.dumps({
                        'mappings': [{
                            'source_field': 'response_body',
                            'target_param': 'prompt',
                            'target_marker': 'content',
                        }]
                    }),
                    content_type='application/json',
                )

            self.assertEqual(response.status_code, 200)
            scheme_path = os.path.join(parametrizer_dir, 'interconnection-scheme.csv')
            with open(scheme_path, 'r', encoding='utf-8', newline='') as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source_field'], 'response_body')
        self.assertEqual(rows[0]['target_param'], 'prompt')
        self.assertEqual(rows[0]['target_marker'], 'content')

    def test_apply_mappings_to_config_uses_marker_template_for_each_iteration(self):
        parametrizer_module = _load_parametrizer_module_for_tests()

        with tempfile.TemporaryDirectory() as pool_dir:
            target_dir = os.path.join(pool_dir, 'prompter_1')
            os.makedirs(target_dir, exist_ok=True)
            config_path = os.path.join(target_dir, 'config.yaml')

            template_config = {
                'prompt': 'Please summarize:\n\n{content}\n\nSource: {file_path}',
                'llm': {
                    'host': 'http://localhost:11434',
                    'model': 'gpt-oss:120b-cloud',
                },
            }

            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump(template_config, handle, sort_keys=False)

            mappings = [
                {
                    'source_field': 'response_body',
                    'target_param': 'prompt',
                    'target_marker': 'content',
                },
                {
                    'source_field': 'file_path',
                    'target_param': 'prompt',
                    'target_marker': 'file_path',
                },
            ]

            with patch.object(parametrizer_module, 'get_agent_directory', return_value=target_dir):
                first_ok = parametrizer_module.apply_mappings_to_config(
                    'prompter_1',
                    mappings,
                    {'response_body': 'First summary', 'file_path': 'alpha.md'},
                    base_config=template_config,
                )
                with open(config_path, 'r', encoding='utf-8') as handle:
                    first_config = yaml.safe_load(handle)

                second_ok = parametrizer_module.apply_mappings_to_config(
                    'prompter_1',
                    mappings,
                    {'response_body': 'Second summary', 'file_path': 'beta.md'},
                    base_config=template_config,
                )
                with open(config_path, 'r', encoding='utf-8') as handle:
                    second_config = yaml.safe_load(handle)

        self.assertTrue(first_ok)
        self.assertTrue(second_ok)
        self.assertEqual(first_config['prompt'], 'Please summarize:\n\nFirst summary\n\nSource: alpha.md')
        self.assertEqual(second_config['prompt'], 'Please summarize:\n\nSecond summary\n\nSource: beta.md')
        self.assertEqual(template_config['prompt'], 'Please summarize:\n\n{content}\n\nSource: {file_path}')


class ParametrizerSequentialExecutionTests(TestCase):
    def test_extract_next_output_block_returns_first_complete_segment_only(self):
        parametrizer_module = _load_parametrizer_module_for_tests()

        unread_log = (
            "noise before blocks\n"
            "<git status> RESPONSE {\n"
            "first body\n"
            "}\n"
            "<git diff> RESPONSE {\n"
            "second body\n"
            "}\n"
        )

        output_block, end_bytes = parametrizer_module.extract_next_output_block('gitter', unread_log)

        expected_prefix = (
            "noise before blocks\n"
            "<git status> RESPONSE {\n"
            "first body\n"
            "}"
        )
        self.assertEqual(output_block['git_command'], 'git status')
        self.assertEqual(output_block['response_body'], 'first body')
        self.assertEqual(end_bytes, len(expected_prefix.encode('utf-8')))

    def test_process_output_block_restores_target_config_and_commits_offset(self):
        parametrizer_module = _load_parametrizer_module_for_tests()

        with tempfile.TemporaryDirectory() as pool_dir:
            source_dir = os.path.join(pool_dir, 'gitter_1')
            target_dir = os.path.join(pool_dir, 'prompter_1')
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(target_dir, exist_ok=True)

            config_path = os.path.join(target_dir, 'config.yaml')
            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({
                    'prompt': 'Please summarize:\n\n{content}\n\nCommand: {command}',
                }, handle, sort_keys=False)

            mappings = [
                {
                    'source_field': 'response_body',
                    'target_param': 'prompt',
                    'target_marker': 'content',
                },
                {
                    'source_field': 'git_command',
                    'target_param': 'prompt',
                    'target_marker': 'command',
                },
            ]
            progress_state = parametrizer_module.default_progress_state()
            saved_states = []

            def _agent_dir(name):
                if name == 'gitter_1':
                    return source_dir
                if name == 'prompter_1':
                    return target_dir
                raise AssertionError(f'unexpected agent lookup: {name}')

            def _save_state(_source_agent, state):
                saved_states.append({
                    'stage': state.get('stage'),
                    'offset': state.get('offset'),
                    'processed_count': state.get('processed_count'),
                    'inflight_end_offset': state.get('inflight_end_offset'),
                })

            with patch.object(parametrizer_module, 'get_agent_directory', side_effect=_agent_dir), \
                    patch.object(parametrizer_module, 'wait_for_agents_to_stop') as mock_wait, \
                    patch.object(parametrizer_module, 'start_agent', return_value=True) as mock_start, \
                    patch.object(parametrizer_module, 'save_progress_state', side_effect=_save_state):
                parametrizer_module.process_output_block(
                    'gitter_1',
                    'prompter_1',
                    mappings,
                    {'git_command': 'git status', 'response_body': 'clean'},
                    block_end_offset=87,
                    file_size=120,
                    progress_state=progress_state,
                )

            with open(config_path, 'r', encoding='utf-8') as handle:
                restored_config = yaml.safe_load(handle)

            self.assertEqual(restored_config['prompt'], 'Please summarize:\n\n{content}\n\nCommand: {command}')
            self.assertFalse(os.path.exists(config_path + '.bck'))
            self.assertEqual(progress_state['offset'], 87)
            self.assertEqual(progress_state['processed_count'], 1)
            self.assertEqual(progress_state['stage'], parametrizer_module.STATE_STAGE_IDLE)
            self.assertEqual(mock_wait.call_args_list, [call(['prompter_1']), call(['prompter_1'])])
            mock_start.assert_called_once_with('prompter_1')
            self.assertEqual(
                [entry['stage'] for entry in saved_states],
                [
                    parametrizer_module.STATE_STAGE_BACKUP_READY,
                    parametrizer_module.STATE_STAGE_CONFIG_APPLIED,
                    parametrizer_module.STATE_STAGE_WAITING_TARGET,
                    parametrizer_module.STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING,
                    parametrizer_module.STATE_STAGE_IDLE,
                ],
            )

    def test_reconcile_reanimation_state_retries_interrupted_segment_after_restoring_backup(self):
        parametrizer_module = _load_parametrizer_module_for_tests()

        with tempfile.TemporaryDirectory() as pool_dir:
            source_dir = os.path.join(pool_dir, 'gitter_1')
            target_dir = os.path.join(pool_dir, 'prompter_1')
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(target_dir, exist_ok=True)

            config_path = os.path.join(target_dir, 'config.yaml')
            backup_path = config_path + '.bck'
            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'mutated value'}, handle, sort_keys=False)
            with open(backup_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'template value'}, handle, sort_keys=False)

            progress_state = {
                'offset': 14,
                'file_size': 99,
                'processed_count': 2,
                'stage': parametrizer_module.STATE_STAGE_WAITING_TARGET,
                'inflight_block': {'response_body': 'segment C'},
                'inflight_end_offset': 33,
            }
            saved_states = []

            def _agent_dir(name):
                if name == 'prompter_1':
                    return target_dir
                if name == 'gitter_1':
                    return source_dir
                raise AssertionError(f'unexpected agent lookup: {name}')

            with patch.object(parametrizer_module, 'get_agent_directory', side_effect=_agent_dir), \
                    patch.object(parametrizer_module, 'save_progress_state', side_effect=lambda _src, state: saved_states.append(dict(state))):
                recovered = parametrizer_module.reconcile_reanimation_state('gitter_1', 'prompter_1', progress_state)

            with open(config_path, 'r', encoding='utf-8') as handle:
                restored_config = yaml.safe_load(handle)

            self.assertEqual(restored_config['prompt'], 'template value')
            self.assertFalse(os.path.exists(backup_path))
            self.assertEqual(recovered['offset'], 14)
            self.assertEqual(recovered['processed_count'], 2)
            self.assertEqual(recovered['stage'], parametrizer_module.STATE_STAGE_IDLE)
            self.assertIsNone(recovered['inflight_block'])
            self.assertIsNone(recovered['inflight_end_offset'])
            self.assertEqual(saved_states[-1]['offset'], 14)

    def test_reconcile_reanimation_state_commits_finished_segment_after_restore(self):
        parametrizer_module = _load_parametrizer_module_for_tests()

        with tempfile.TemporaryDirectory() as pool_dir:
            source_dir = os.path.join(pool_dir, 'gitter_1')
            target_dir = os.path.join(pool_dir, 'prompter_1')
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(target_dir, exist_ok=True)

            config_path = os.path.join(target_dir, 'config.yaml')
            backup_path = config_path + '.bck'
            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'mutated value'}, handle, sort_keys=False)
            with open(backup_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'template value'}, handle, sort_keys=False)

            progress_state = {
                'offset': 14,
                'file_size': 120,
                'processed_count': 2,
                'stage': parametrizer_module.STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING,
                'inflight_block': {'response_body': 'segment C'},
                'inflight_end_offset': 48,
            }
            saved_states = []

            def _agent_dir(name):
                if name == 'prompter_1':
                    return target_dir
                if name == 'gitter_1':
                    return source_dir
                raise AssertionError(f'unexpected agent lookup: {name}')

            with patch.object(parametrizer_module, 'get_agent_directory', side_effect=_agent_dir), \
                    patch.object(parametrizer_module, 'save_progress_state', side_effect=lambda _src, state: saved_states.append(dict(state))):
                recovered = parametrizer_module.reconcile_reanimation_state('gitter_1', 'prompter_1', progress_state)

            with open(config_path, 'r', encoding='utf-8') as handle:
                restored_config = yaml.safe_load(handle)

            self.assertEqual(restored_config['prompt'], 'template value')
            self.assertFalse(os.path.exists(backup_path))
            self.assertEqual(recovered['offset'], 48)
            self.assertEqual(recovered['processed_count'], 3)
            self.assertEqual(recovered['stage'], parametrizer_module.STATE_STAGE_IDLE)
            self.assertIsNone(recovered['inflight_block'])
            self.assertIsNone(recovered['inflight_end_offset'])
            self.assertEqual(saved_states[-1]['offset'], 48)
