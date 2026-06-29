import importlib.util
import ast
import csv
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
import tempfile as _acpx_tempfile
from functools import lru_cache
from pathlib import Path, Path as _AcpxPath
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
from agent.chat_history_loader import DBChatHistoryLoader
from agent.consumers import AgentConsumer, _sanitize_context_filename
from agent.global_state import get_request_state, global_state
from agent.mcp_agent import CapabilityAwareToolAgentExecutor, _budget_select_tools
from agent.models import AgentMessage
from agent import path_guard
from agent.path_guard import (
    REJECTION_MESSAGE,
    get_runtime_agent_root,
    is_path_allowed,
    is_within_application_root,
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
        bot_user = User.objects.create_user(username='Tlamatini', password='secret123')
        AgentMessage.objects.create(user=self.user, conversation_user=self.user, message='visible to alice')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.user, message='assistant reply')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.other_user, message='must stay private')

        self.client.force_login(self.user)
        response = self.client.get(reverse('agent_page'))

        self.assertEqual(
            [message['message'] for message in response.context['initial_messages']],
            ['visible to alice', 'assistant reply']
        )

    def test_chat_history_loader_can_scope_to_current_user(self):
        bot_user = User.objects.create_user(username='Tlamatini', password='secret123')
        AgentMessage.objects.create(user=self.user, conversation_user=self.user, message='alice prompt')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.user, message='alice assistant')
        AgentMessage.objects.create(user=self.other_user, conversation_user=self.other_user, message='bob prompt')
        AgentMessage.objects.create(user=bot_user, conversation_user=self.other_user, message='bob assistant')

        messages = DBChatHistoryLoader.load(limit=8, conversation_user=self.user)
        contents = [getattr(message, 'content', '') for message in messages]

        self.assertEqual(contents, ['alice prompt', 'alice assistant'])

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
        bot_user = User.objects.create_user(username='Tlamatini', password='secret123')
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


class SetDirectoryAsContextPathTests(TestCase):
    """Validates the fix that lets "Set directory as context" load a project
    living at ANY depth under the application root (not just a direct child).

    The bug was that the browser only sent the leaf folder name; the real fix
    sends the full absolute path (via the native picker) which path_guard must
    accept for arbitrarily deep sub-directories — in BOTH frozen and source
    (non-frozen) runtime modes.
    """

    def test_is_within_application_root_accepts_any_depth(self):
        with tempfile.TemporaryDirectory() as app_root:
            direct = os.path.join(app_root, 'applications')
            deep = os.path.join(app_root, 'applications', 'projA', 'src', 'deep')
            os.makedirs(deep)
            with patch.object(path_guard, '_get_application_root', return_value=app_root):
                # The root itself, a direct child, and a deep descendant all pass.
                self.assertTrue(is_within_application_root(app_root))
                self.assertTrue(is_within_application_root(direct))
                self.assertTrue(is_within_application_root(deep))

    def test_is_within_application_root_rejects_sibling_tree(self):
        with tempfile.TemporaryDirectory() as app_root, tempfile.TemporaryDirectory() as outside:
            with patch.object(path_guard, '_get_application_root', return_value=app_root):
                self.assertFalse(is_within_application_root(outside))

    def test_resolve_runtime_agent_path_accepts_deep_app_root_subdir(self):
        """A full absolute path several levels under the app root resolves."""
        with tempfile.TemporaryDirectory() as app_root:
            nested = os.path.join(app_root, 'applications', 'projA', 'service', 'src')
            os.makedirs(nested)
            with patch.object(path_guard, '_get_application_root', return_value=app_root):
                resolved = resolve_runtime_agent_path(nested)
            self.assertIsNotNone(resolved)
            self.assertEqual(os.path.realpath(resolved), os.path.realpath(nested))

    def test_resolve_runtime_agent_path_rejects_outside_everything(self):
        """A path under no allowed root (not runtime, not app root, not
        allowed_paths) is still rejected — the relaxation is scoped, not open."""
        with tempfile.TemporaryDirectory() as app_root, tempfile.TemporaryDirectory() as outside:
            with patch.object(path_guard, '_get_application_root', return_value=app_root), \
                    patch.object(path_guard, 'is_path_allowed', return_value=False):
                self.assertIsNone(resolve_runtime_agent_path(outside))

    def test_frozen_mode_application_root_is_executable_dir_and_nested_resolves(self):
        """In frozen mode both the application root and the runtime root are the
        install (executable) directory, and a deeply nested project under it
        resolves."""
        with tempfile.TemporaryDirectory() as install_dir:
            fake_executable = os.path.join(install_dir, 'Tlamatini.exe')
            with open(fake_executable, 'w', encoding='utf-8') as handle:
                handle.write('stub exe')
            nested = os.path.join(install_dir, 'applications', 'projB', 'module', 'src')
            os.makedirs(nested)

            with patch.object(path_guard.sys, 'frozen', True, create=True), \
                    patch.object(path_guard.sys, 'executable', fake_executable):
                self.assertEqual(
                    os.path.realpath(path_guard._get_application_root()),
                    os.path.realpath(install_dir),
                )
                self.assertEqual(
                    os.path.realpath(get_runtime_agent_root()),
                    os.path.realpath(install_dir),
                )
                self.assertTrue(is_within_application_root(nested))
                resolved = resolve_runtime_agent_path(nested)

            self.assertIsNotNone(resolved)
            self.assertEqual(os.path.realpath(resolved), os.path.realpath(nested))

    def test_non_frozen_application_root_is_ancestor_of_agent_package(self):
        """In source mode the application root must be an ancestor of the
        agent package directory (so agent-dir descendants stay loadable)."""
        app_root = path_guard._get_application_root()
        agent_dir = os.path.dirname(os.path.abspath(path_guard.__file__))
        self.assertTrue(path_guard.is_path_within_base(app_root, agent_dir))


class ContextDirectoryPickerViewTests(TestCase):
    """Covers the new /agent/pick_context_directory/ endpoint that returns the
    full absolute path chosen in the native server-side folder picker."""

    def setUp(self):
        self.user = User.objects.create_user(username='ctx_picker', password='pw123456')
        self.client = Client()
        self.client.force_login(self.user)

    def test_returns_full_absolute_path(self):
        chosen = 'C:\\apps\\proj\\service\\src' if os.name == 'nt' else '/apps/proj/service/src'
        with patch.object(views, '_run_native_picker', return_value=chosen):
            response = self.client.get(reverse('pick_context_directory'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('path'), os.path.abspath(chosen))

    def test_reports_cancel_when_dialog_closed(self):
        with patch.object(views, '_run_native_picker', return_value=''):
            response = self.client.get(reverse('pick_context_directory'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('path'), '')
        self.assertTrue(data.get('canceled'))

    def test_reports_picker_unavailable(self):
        from agent.native_dialogs import NativeDialogUnavailable

        def _boom(*_args, **_kwargs):
            raise NativeDialogUnavailable('native folder dialog requires Windows')

        with patch.object(views, '_run_native_picker', side_effect=_boom):
            response = self.client.get(reverse('pick_context_directory'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('path'), '')
        self.assertTrue(data.get('picker_unavailable'))

    def test_requires_authentication(self):
        anon = Client()
        response = anon.get(reverse('pick_context_directory'))
        self.assertEqual(response.status_code, 302)


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

    def test_unified_agent_chain_forwards_exec_report_flag_and_round_trips_entries(self):
        # Regression guard: UnifiedAgentChain.invoke rebuilds the payload as
        # a new dict with a hardcoded key whitelist. Any key missing from
        # that whitelist is silently dropped before reaching the executor.
        # This once stripped `exec_report_enabled`, which made the Exec
        # report feature produce no tables in the final answer.
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {
                    'output': 'done',
                    'tool_calls_log': [],
                    'exec_report_enabled': bool(payload.get('exec_report_enabled')),
                    'exec_report_entries': [
                        {
                            'tool_name': 'chat_agent_dockerer',
                            'agent_key': 'dockerer',
                            'agent_display': 'Dockerer',
                            'command': 'docker ps',
                            'success': True,
                        },
                    ],
                }

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = ''
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({
            'input': 'list containers',
            'chat_history': [],
            'multi_turn_enabled': True,
            'exec_report_enabled': True,
        })

        self.assertTrue(
            captured['payload'].get('exec_report_enabled'),
            'exec_report_enabled must survive the UnifiedAgentChain payload whitelist',
        )
        self.assertTrue(result.get('exec_report_enabled'))
        self.assertEqual(len(result.get('exec_report_entries', [])), 1)
        self.assertEqual(result['exec_report_entries'][0]['agent_key'], 'dockerer')
        self.assertEqual(result['exec_report_entries'][0]['command'], 'docker ps')

    def test_unified_agent_chain_omits_exec_report_fields_when_flag_off(self):
        # When the user has not toggled the Exec report checkbox on, the
        # chain must NOT surface exec_report_entries in its result dict,
        # so the downstream renderer stays dormant.
        class _FakeAgent:
            def invoke(self, payload):
                return {
                    'output': 'done',
                    'tool_calls_log': [],
                    'exec_report_enabled': False,
                    'exec_report_entries': [],
                }

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = ''
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({
            'input': 'run something',
            'chat_history': [],
            'multi_turn_enabled': True,
            # exec_report_enabled intentionally absent
        })

        self.assertNotIn('exec_report_enabled', result)
        self.assertNotIn('exec_report_entries', result)


class ExecReportCaptureTests(TestCase):
    """Exercise MultiTurnToolAgentExecutor's Exec report capture across the
    full set of state-changing tools. Each call must land in
    ``exec_report_entries`` tagged with the right ``agent_key`` /
    ``agent_display`` and the correct success verdict."""

    def _fake_llm_for_calls(self, calls_per_turn):
        """Build a fake LLM that issues ``calls_per_turn[i]`` tool calls on
        turn ``i+1`` and then returns an empty tool-call final turn.
        Each item in ``calls_per_turn`` is a list of ``(tool_name, args_dict)``.
        """
        iterator = iter(calls_per_turn + [[]])

        class _FakeLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                try:
                    calls = next(iterator)
                except StopIteration:
                    calls = []
                if not calls:
                    return SimpleNamespace(content='wrap up', tool_calls=[])
                tool_calls = [
                    {'id': f'c{idx}', 'name': name, 'args': args}
                    for idx, (name, args) in enumerate(calls)
                ]
                return SimpleNamespace(content='', tool_calls=tool_calls)

        return _FakeLLM()

    def _build_executor(self, tools, calls_per_turn):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        return MultiTurnToolAgentExecutor(
            llm=self._fake_llm_for_calls(calls_per_turn),
            system_prompt='test',
            tools=tools,
            max_iterations=10,
        )

    def test_direct_executer_and_pythonxer_are_captured_with_correct_agent_keys(self):
        from langchain.tools import tool

        @tool
        def execute_command(command: str) -> str:
            """Run a shell command."""
            return f"Command '{command}' executed successfully."

        @tool
        def execute_file(command: str) -> str:
            """Run a Python script."""
            return f"Command '{command}' executed successfully."

        exe = self._build_executor(
            tools=[execute_command, execute_file],
            calls_per_turn=[
                [('execute_command', {'command': 'git status'})],
                [('execute_file', {'command': 'install.py'})],
            ],
        )
        result = exe.invoke({'input': 'do things', 'exec_report_enabled': True})

        entries = result['exec_report_entries']
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['agent_key'], 'executer')
        self.assertEqual(entries[0]['agent_display'], 'Executer')
        self.assertEqual(entries[0]['command'], 'git status')
        self.assertTrue(entries[0]['success'])
        self.assertEqual(entries[1]['agent_key'], 'pythonxer')
        self.assertEqual(entries[1]['agent_display'], 'Pythonxer')

    def test_wrapped_chat_agent_tools_are_captured_across_agent_types(self):
        """Simulate a real multi-turn that fans out across Dockerer, SSHer,
        and SQLer wrapped launches. All three must land in
        exec_report_entries tagged with the right agent_key."""
        from langchain.tools import Tool

        def _make_stub(tool_name):
            def runner(request: str) -> str:
                return json.dumps({'status': 'ok', 'tool': tool_name})
            return Tool.from_function(func=runner, name=tool_name,
                                      description=f'Launch {tool_name}.')

        tools = [
            _make_stub('chat_agent_dockerer'),
            _make_stub('chat_agent_ssher'),
            _make_stub('chat_agent_sqler'),
        ]
        exe = self._build_executor(
            tools=tools,
            calls_per_turn=[
                [
                    ('chat_agent_dockerer', {'__arg1': 'docker ps -a'}),
                    ('chat_agent_ssher', {'__arg1': "ssh admin@10.0.0.1 'uptime'"}),
                ],
                [
                    ('chat_agent_sqler', {'__arg1': "SELECT 1 FROM users"}),
                ],
            ],
        )
        result = exe.invoke({'input': 'fleet check', 'exec_report_enabled': True})

        keys = [e['agent_key'] for e in result['exec_report_entries']]
        self.assertEqual(keys, ['dockerer', 'ssher', 'sqler'])
        commands = [e['command'] for e in result['exec_report_entries']]
        self.assertIn('docker ps -a', commands)
        self.assertTrue(any("ssh admin@10.0.0.1" in c for c in commands))
        self.assertIn('SELECT 1 FROM users', commands)

    def test_observational_agent_captured_but_management_and_direct_readonly_not(self):
        """Completeness contract (2026-06-07): an observational chat-agent like
        ``chat_agent_crawler`` IS now captured — EVERY agent that runs in
        Multi-Turn must appear in the Exec report. Management/polling helpers
        (``chat_agent_run_status``) and direct read-only @tools (``googler``)
        are still NEVER captured."""
        from langchain.tools import Tool

        def _make_stub(name):
            def runner(request: str) -> str:
                return json.dumps({'status': 'ok'})
            return Tool.from_function(func=runner, name=name,
                                      description=f'Launch {name}.')

        tools = [
            _make_stub('chat_agent_crawler'),
            _make_stub('chat_agent_run_status'),
            _make_stub('googler'),
        ]
        exe = self._build_executor(
            tools=tools,
            calls_per_turn=[
                [
                    ('chat_agent_crawler', {'__arg1': 'crawl example.com'}),
                    ('chat_agent_run_status', {'__arg1': 'status'}),
                    ('googler', {'__arg1': 'python tutorials'}),
                ],
            ],
        )
        result = exe.invoke({'input': 'mixed', 'exec_report_enabled': True})

        # crawler captured; run_status (management) + googler (direct read-only) excluded.
        keys = [e['agent_key'] for e in result['exec_report_entries']]
        self.assertEqual(keys, ['crawler'])
        self.assertEqual(result['exec_report_entries'][0]['agent_display'], 'Crawler')

    def test_every_multiturn_agent_is_capturable_including_observational(self):
        """AUDIT: ``_resolve_exec_report_spec`` returns a (key, display) for
        EVERY wrapped chat-agent that can run in Multi-Turn — observational
        agents (Talker/Shoter/Camcorder/Recorder/AudioPlayer/VideoPlayer) and
        read-only LLM agents (Crawler/Prompter/Summarizer/...) included — so the
        Exec report shows them all. Only management/polling helpers and direct
        read-only @tools resolve to None."""
        from agent.mcp_agent import _resolve_exec_report_spec, _MANAGEMENT_TOOLS
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME

        missing = []
        for tool_name in WRAPPED_CHAT_AGENT_BY_TOOL_NAME:
            spec = _resolve_exec_report_spec(tool_name)
            if tool_name in _MANAGEMENT_TOOLS:
                self.assertIsNone(spec, f"{tool_name} is management — must NOT capture")
            elif spec is None:
                missing.append(tool_name)
            else:
                self.assertTrue(spec[0] and spec[1], f"{tool_name} bad spec {spec}")
        self.assertEqual(missing, [], f"Multi-Turn agents NOT captured: {missing}")

        # The agents that USED to be excluded are now captured with nice names.
        for tn, disp in (
            ('chat_agent_talker', 'Talker'),
            ('chat_agent_shoter', 'Shoter'),
            ('chat_agent_camcorder', 'Camcorder'),
            ('chat_agent_recorder', 'Recorder'),
            ('chat_agent_audioplayer', 'AudioPlayer'),
            ('chat_agent_videoplayer', 'VideoPlayer'),
            ('chat_agent_crawler', 'Crawler'),
            ('chat_agent_prompter', 'Prompter'),
        ):
            spec = _resolve_exec_report_spec(tn)
            self.assertIsNotNone(spec, f"{tn} must be captured")
            self.assertEqual(spec[1], disp)

        # Management + a direct read-only @tool are never captured.
        self.assertIsNone(_resolve_exec_report_spec('chat_agent_run_status'))
        self.assertIsNone(_resolve_exec_report_spec('googler'))
        self.assertIsNone(_resolve_exec_report_spec('get_current_time'))

    def test_failing_tool_is_captured_with_success_false(self):
        """Executer returning an ``Error:`` string must mark the entry as
        failed; the existing ``call_success`` heuristic covers both the
        JSON-status path and the plain-text path."""
        from langchain.tools import tool

        @tool
        def execute_command(command: str) -> str:
            """Run a shell command."""
            return json.dumps({'status': 'error', 'message': 'boom'})

        exe = self._build_executor(
            tools=[execute_command],
            calls_per_turn=[[('execute_command', {'command': 'bad-cmd'})]],
        )
        result = exe.invoke({'input': 'fails', 'exec_report_enabled': True})

        self.assertEqual(len(result['exec_report_entries']), 1)
        self.assertFalse(result['exec_report_entries'][0]['success'])

    def test_acpx_and_skill_tools_are_captured_with_correct_keys_and_commands(self):
        """ACPX child-process launchers (acp_spawn / acp_send / acp_kill)
        and the Skill harness invoker (invoke_skill) must land in
        exec_report_entries. The user explicitly asked: when ACPX is in
        play during Multi-Turn, the per-agent operation tables are
        fundamental — they must show regardless of SUCCESS/FAILURE.

        acp_spawn, acp_send and acp_kill share the ``acpx`` agent_key on
        purpose so they merge into one "List of ACPx Operations" table
        in execution order. invoke_skill gets its own ``skill`` table.

        Each entry's ``command`` field must use the tool-specific
        formatter so the report shows meaningful intent (which CLI was
        spawned, which skill was invoked, which session was killed)
        instead of a raw dict dump."""
        from langchain.tools import StructuredTool

        def _stub(name, fields):
            # StructuredTool lets the executor pass a multi-key dict
            # matching the real ACPX tool signatures (acp_spawn takes
            # agent_id+task+mode, acp_send takes session_id+text, etc.).
            # langchain infers the schema from the function signature, so
            # build a typed function with the exact kwargs each tool needs.
            def runner(**kwargs):
                return json.dumps({'ok': True, 'tool': name})
            sig = ', '.join(f'{f}: str = ""' for f in fields)
            body = ', '.join(f'{f}={f}' for f in fields)
            ns = {'_runner_impl': runner}
            exec(f'def runner_typed({sig}):\n    return _runner_impl({body})', ns)
            return StructuredTool.from_function(
                func=ns['runner_typed'], name=name, description=f'ACPX tool {name}.',
            )

        tools = [
            _stub('acp_spawn', ['agent_id', 'task', 'mode']),
            _stub('acp_send',  ['session_id', 'text']),
            _stub('acp_kill',  ['session_id']),
            _stub('invoke_skill', ['skill_name', 'args_json']),
        ]
        exe = self._build_executor(
            tools=tools,
            calls_per_turn=[
                [
                    ('acp_spawn', {
                        'agent_id': 'cursor',
                        'task': 'refactor the auth module',
                        'mode': 'session',
                    }),
                ],
                [
                    ('acp_send', {
                        'session_id': 'sess-42',
                        'text': 'now also add unit tests',
                    }),
                ],
                [
                    ('invoke_skill', {
                        'skill_name': 'notion',
                        'args_json': '{"page":"home"}',
                    }),
                ],
                [
                    ('acp_kill', {'session_id': 'sess-42'}),
                ],
            ],
        )
        result = exe.invoke({'input': 'use acpx', 'exec_report_enabled': True})
        entries = result['exec_report_entries']

        # All four state-changing ACPX/skill calls must be captured.
        self.assertEqual(len(entries), 4)
        keys = [e['agent_key'] for e in entries]
        displays = [e['agent_display'] for e in entries]
        commands = [e['command'] for e in entries]

        # spawn / send / kill all share the ``acpx`` key; invoke_skill
        # owns the ``skill`` key.
        self.assertEqual(keys, ['acpx', 'acpx', 'skill', 'acpx'])
        self.assertEqual(displays, ['ACPx', 'ACPx', 'Skill', 'ACPx'])

        # Tool-specific command formatters produce meaningful intent
        # strings, not raw key=value dumps.
        self.assertEqual(commands[0], '[cursor] refactor the auth module')
        self.assertEqual(commands[1], '[sess-42] now also add unit tests')
        self.assertEqual(commands[2], 'notion({"page":"home"})')
        self.assertEqual(commands[3], 'kill sess-42')

    def test_acpx_failure_and_skill_failure_are_captured_with_success_false(self):
        """The user explicitly asked the tables to appear regardless of
        whether the answer was correctly generated or not — so failed
        ACPX / Skill calls must still produce exec_report_entries with
        ``success=False``. Tests both the JSON ``status: 'error'`` path
        and the JSON ``ok: false`` path that ACPX tools actually emit."""
        from langchain.tools import StructuredTool

        def _spawn_fail(agent_id: str = '', task: str = '', mode: str = '') -> str:
            # Mirrors the ``acpx.tools._err`` envelope shape.
            return json.dumps({
                'status': 'error',
                'reason': 'agent unhealthy',
                'code': 'AGENT_UNHEALTHY',
            })

        def _skill_fail(skill_name: str = '', args_json: str = '') -> str:
            return json.dumps({
                'status': 'failed',
                'reason': 'budget exceeded',
            })

        tools = [
            StructuredTool.from_function(func=_spawn_fail, name='acp_spawn',
                                         description='spawn'),
            StructuredTool.from_function(func=_skill_fail, name='invoke_skill',
                                         description='skill'),
        ]
        exe = self._build_executor(
            tools=tools,
            calls_per_turn=[[
                ('acp_spawn', {'agent_id': 'kimi', 'task': 'do thing'}),
                ('invoke_skill', {'skill_name': 'pdf-to-text'}),
            ]],
        )
        result = exe.invoke({'input': 'fails', 'exec_report_enabled': True})
        entries = result['exec_report_entries']

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['agent_key'], 'acpx')
        self.assertFalse(entries[0]['success'])
        self.assertEqual(entries[0]['command'], '[kimi] do thing')
        self.assertEqual(entries[1]['agent_key'], 'skill')
        self.assertFalse(entries[1]['success'])
        self.assertEqual(entries[1]['command'], 'pdf-to-text')

    def test_acpx_render_groups_spawn_send_kill_into_one_acpx_table(self):
        """The renderer must merge acp_spawn + acp_send + acp_kill into a
        single "List of ACPx Operations" table, in the order they
        executed, regardless of SUCCESS/FAILURE on individual rows."""
        from agent.services.response_parser import _render_exec_report_html

        entries = [
            {'tool_name': 'acp_spawn', 'agent_key': 'acpx',
             'agent_display': 'ACPx', 'command': '[cursor] refactor', 'success': True},
            {'tool_name': 'invoke_skill', 'agent_key': 'skill',
             'agent_display': 'Skill', 'command': 'notion', 'success': False},
            {'tool_name': 'acp_send', 'agent_key': 'acpx',
             'agent_display': 'ACPx', 'command': '[sess-1] follow up', 'success': True},
            {'tool_name': 'acp_kill', 'agent_key': 'acpx',
             'agent_display': 'ACPx', 'command': 'kill sess-1', 'success': True},
        ]
        html = _render_exec_report_html(entries)

        # Exactly one ACPx caption and one Skill caption — spawn/send/kill
        # were merged into a single table.
        self.assertEqual(html.count('List of ACPx Operations'), 1)
        self.assertEqual(html.count('List of Skill Operations'), 1)
        # All three ACPx commands appear in their merged table, in order.
        spawn_idx = html.index('[cursor] refactor')
        send_idx = html.index('[sess-1] follow up')
        kill_idx = html.index('kill sess-1')
        self.assertLess(spawn_idx, send_idx)
        self.assertLess(send_idx, kill_idx)
        # Per-agent CSS class on the captions so the gradient mirrors the
        # canvas-item tile.
        self.assertIn('exec-report-caption-acpx', html)
        self.assertIn('exec-report-caption-skill', html)
        # Failed Skill row carries the FAILURE verdict; ACPx successes
        # carry SUCCESS — proving capture is independent of any
        # downstream answer-success classification.
        self.assertIn('>FAILURE<', html)
        self.assertIn('>SUCCESS<', html)

    def test_exec_report_entries_are_emitted_even_when_flag_off(self):
        """The flag gates RENDERING, not CAPTURE. Capturing unconditionally
        means a future payload-whitelist bug cannot silently hide the data."""
        from langchain.tools import tool

        @tool
        def execute_command(command: str) -> str:
            """Run a shell command."""
            return f"Command '{command}' executed successfully."

        exe = self._build_executor(
            tools=[execute_command],
            calls_per_turn=[[('execute_command', {'command': 'dir'})]],
        )
        # Explicitly DO NOT pass exec_report_enabled.
        result = exe.invoke({'input': 'just run'})

        self.assertFalse(result['exec_report_enabled'])
        self.assertEqual(len(result['exec_report_entries']), 1)

    def test_render_groups_entries_by_agent_key_in_first_appearance_order(self):
        """The renderer must emit one table per unique agent_key, in the
        order each agent first fired — not alphabetical."""
        from agent.services.response_parser import _render_exec_report_html

        entries = [
            {'tool_name': 'chat_agent_ssher',   'agent_key': 'ssher',    'agent_display': 'SSHer',    'command': 'uptime', 'success': True},
            {'tool_name': 'execute_command',    'agent_key': 'executer', 'agent_display': 'Executer', 'command': 'dir',    'success': True},
            {'tool_name': 'chat_agent_ssher',   'agent_key': 'ssher',    'agent_display': 'SSHer',    'command': 'df -h',  'success': False},
            {'tool_name': 'chat_agent_dockerer','agent_key': 'dockerer', 'agent_display': 'Dockerer', 'command': 'docker ps', 'success': True},
        ]
        html = _render_exec_report_html(entries)

        # SSHer appears first (its first fire was index 0) then Executer then Dockerer.
        ssher_idx = html.index('List of SSHer Operations')
        executer_idx = html.index('List of Executer Operations')
        dockerer_idx = html.index('List of Dockerer Operations')
        self.assertLess(ssher_idx, executer_idx)
        self.assertLess(executer_idx, dockerer_idx)

        # The SSHer table groups both SSHer commands.
        self.assertIn('uptime', html)
        self.assertIn('df -h', html)
        # Success / failure cells both appear.
        self.assertIn('>SUCCESS<', html)
        self.assertIn('>FAILURE<', html)
        # Each agent's caption carries its own CSS class.
        self.assertIn('exec-report-caption-ssher', html)
        self.assertIn('exec-report-caption-executer', html)
        self.assertIn('exec-report-caption-dockerer', html)


class NotificationDebtGuardTests(TestCase):
    """The completion-notification ("notification debt") guard: when the user
    asks to be notified ON COMPLETION (Telegram / email / WhatsApp / notifier)
    and the model tries to finish WITHOUT having called a notification tool,
    the executor injects ONE nudge so the notification is actually sent — and
    it preserves the substantive (deliverable) answer. Regression guard for the
    FlowPills 'transient network error' confabulation bug (2026-06-24)."""

    # ---- detector ----
    def test_detector_matches_notify_on_completion_phrasings(self):
        from agent.mcp_agent import _detect_completion_notification_request as d
        self.assertTrue(d("Analyze the code and when you finish send me a Telegram telling me you finished, go!"))
        self.assertTrue(d("Run the build and email me when it's done."))
        self.assertTrue(d("Once the scan completes, notify me on WhatsApp."))
        self.assertTrue(d("After finishing, send me a notification."))

    def test_detector_ignores_unrelated_or_send_now_requests(self):
        from agent.mcp_agent import _detect_completion_notification_request as d
        self.assertFalse(d("Send me a Telegram saying hello."))          # no completion cue
        self.assertFalse(d("Summarize this project's source code."))     # no notify
        self.assertFalse(d("What security issues exist in this code?"))  # neither
        self.assertFalse(d("Finish the report and show it here."))       # completion, no notify channel

    # ---- guard behavior ----
    def _telegram_tool(self):
        from langchain.tools import Tool

        def runner(request: str) -> str:
            return json.dumps({'status': 'ok', 'tool': 'chat_agent_telegrammer'})
        return Tool.from_function(func=runner, name='chat_agent_telegrammer',
                                  description='Send a Telegram message.')

    def _build_executor(self, tools, llm):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        return MultiTurnToolAgentExecutor(
            llm=llm, system_prompt='test', tools=tools, max_iterations=10,
        )

    def test_guard_nudges_and_sends_when_notification_was_skipped(self):
        """Model 'finishes' with the analysis but never called Telegram. The
        guard must nudge it; on the nudged turn the model sends Telegram; and
        the final answer must still be the substantive analysis (stash restore)."""
        deliverable = "FULL FLOWPILLS SECURITY ANALYSIS: 3 Critical, 4 High..."

        class _Fake:
            def __init__(self):
                self.turn = 0

            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                self.turn += 1
                nudged = any(
                    'you have NOT yet called any' in str(getattr(m, 'content', '') or '')
                    for m in messages
                )
                if not nudged:
                    # First "final" turn: try to finish WITHOUT notifying.
                    return SimpleNamespace(content=deliverable, tool_calls=[])
                # Look back: have we already sent the telegram?
                sent = any(
                    getattr(m, 'name', '') == 'chat_agent_telegrammer'
                    for m in messages
                )
                if not sent:
                    return SimpleNamespace(content='', tool_calls=[
                        {'id': 't1', 'name': 'chat_agent_telegrammer',
                         'args': {'__arg1': "contact_name='me' and message='done'"}}
                    ])
                # Telegram sent — produce a short confirmation final answer.
                return SimpleNamespace(content='Sent.', tool_calls=[])

        exe = self._build_executor([self._telegram_tool()], _Fake())
        result = exe.invoke({
            'input': 'Analyze the code and when you finish send me a Telegram telling me you finished.',
            'exec_report_enabled': True,
        })

        # Telegram WAS actually called (captured in the exec report).
        keys = [e['agent_key'] for e in result['exec_report_entries']]
        self.assertIn('telegrammer', keys)
        # The deliverable analysis is preserved, not replaced by "Sent.".
        self.assertIn('FLOWPILLS SECURITY ANALYSIS', result['output'])

    def test_guard_silent_when_notification_not_requested(self):
        """No completion-notification ask → no nudge, Telegram never forced."""
        class _Fake:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                return SimpleNamespace(content='here is the summary', tool_calls=[])

        exe = self._build_executor([self._telegram_tool()], _Fake())
        result = exe.invoke({
            'input': 'Summarize this project source code, please.',
            'exec_report_enabled': True,
        })
        self.assertEqual(result['exec_report_entries'], [])
        self.assertIn('summary', result['output'])

    def test_guard_does_not_double_send_when_already_notified(self):
        """Model sends Telegram during the work, then finishes. The guard must
        NOT fire a second notification, and the model's own final answer stands."""
        class _Fake:
            def __init__(self):
                self.turn = 0

            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                self.turn += 1
                if self.turn == 1:
                    return SimpleNamespace(content='', tool_calls=[
                        {'id': 't1', 'name': 'chat_agent_telegrammer',
                         'args': {'__arg1': "message='done'"}}
                    ])
                return SimpleNamespace(content='All done and notified.', tool_calls=[])

        exe = self._build_executor([self._telegram_tool()], _Fake())
        result = exe.invoke({
            'input': 'Do the work and email me when finished.',
            'exec_report_enabled': True,
        })
        keys = [e['agent_key'] for e in result['exec_report_entries']]
        self.assertEqual(keys.count('telegrammer'), 1)  # exactly one send
        self.assertIn('notified', result['output'])


class ExecReportPersistenceTests(TestCase):
    """Regression guard for the behaviour the end-user asked for: once the
    Exec report tables are generated, the Tlamatini chat message stored in
    the DB must contain them too — so reloading the page restores the same
    content the user saw live. The DB row must carry the tables regardless
    of whether the answer was classified as SUCCESS or FAILURE, and when the
    Exec report toggle is off the row must stay table-free."""

    def setUp(self):
        self.user = User.objects.create_user(username='persister', password='pw')
        self.entries = [
            {
                'tool_name': 'execute_command',
                'agent_key': 'executer',
                'agent_display': 'Executer',
                'command': 'dir',
                'success': True,
            },
            {
                'tool_name': 'chat_agent_dockerer',
                'agent_key': 'dockerer',
                'agent_display': 'Dockerer',
                'command': 'docker ps',
                'success': False,
            },
        ]

    def _run_processor(self, *, exec_report_enabled, entries, multi_turn_used=True,
                       tool_calls_log=(('execute_command', {'command': 'dir'}),),
                       answer_success=True):
        from agent.services.response_parser import process_llm_response

        async def _analyzer(_text):
            return answer_success

        with patch(
            'agent.services.response_parser.analyze_answer_success',
            side_effect=_analyzer,
        ):
            final = async_to_sync(process_llm_response)(
                'done<br>END-RESPONSE',
                None,
                None,
                None,
                conversation_user=self.user,
                tool_calls_log=list(tool_calls_log) if tool_calls_log else None,
                multi_turn_used=multi_turn_used,
                exec_report_enabled=exec_report_enabled,
                exec_report_entries=entries,
            )
        return final

    def _latest_bot_message(self):
        return (
            AgentMessage.objects
            .filter(conversation_user=self.user, user__username='Tlamatini')
            .order_by('-timestamp')
            .first()
        )

    def test_exec_report_tables_are_persisted_into_agent_message_row(self):
        final = self._run_processor(
            exec_report_enabled=True,
            entries=self.entries,
            answer_success=True,
        )
        row = self._latest_bot_message()
        self.assertIsNotNone(row, 'Expected a Tlamatini AgentMessage row to be saved')
        # The persisted text MUST match what was broadcast to the WebSocket
        # — including the Exec report HTML — so reload parity is guaranteed.
        self.assertEqual(row.message, final)
        self.assertIn('exec-report-block', row.message)
        self.assertIn('List of Executer Operations', row.message)
        self.assertIn('List of Dockerer Operations', row.message)
        self.assertIn('>SUCCESS<', row.message)
        self.assertIn('>FAILURE<', row.message)

    def test_exec_report_tables_are_persisted_even_when_answer_is_failure(self):
        # The user explicitly asked: the tables must persist independently
        # of whether the LLM answer is classified SUCCESS or FAILURE.
        final = self._run_processor(
            exec_report_enabled=True,
            entries=self.entries,
            answer_success=False,
        )
        row = self._latest_bot_message()
        self.assertIsNotNone(row)
        self.assertEqual(row.message, final)
        self.assertIn('exec-report-block', row.message)
        self.assertIn('List of Executer Operations', row.message)

    def test_persisted_message_has_no_tables_when_exec_report_disabled(self):
        self._run_processor(
            exec_report_enabled=False,
            entries=self.entries,
            answer_success=True,
        )
        row = self._latest_bot_message()
        self.assertIsNotNone(row)
        self.assertNotIn('exec-report-block', row.message)
        self.assertNotIn('List of Executer Operations', row.message)

    def test_persisted_message_has_no_tables_when_no_entries_captured(self):
        # Flag on, but no state-changing tool fired. Row must stay clean and
        # NOT carry an empty <div class="exec-report-block"></div> husk.
        self._run_processor(
            exec_report_enabled=True,
            entries=[],
            answer_success=True,
        )
        row = self._latest_bot_message()
        self.assertIsNotNone(row)
        self.assertNotIn('exec-report-block', row.message)


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


class ToolSurfaceBudgetTests(TestCase):
    def test_exhausted_prompt_budget_keeps_only_core_tools_that_fit(self):
        tools = [
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
            SimpleNamespace(name='chat_agent_pythonxer', description='Launch Pythonxer.'),
            SimpleNamespace(name='chat_agent_file_creator', description='Create files.'),
            SimpleNamespace(name='chat_agent_kalier', description='Kali operations.'),
            SimpleNamespace(name='chat_agent_esp32er', description='ESP32 operations.'),
        ]

        with patch('agent.mcp_agent.get_int_config_value', return_value=1000), \
                patch('agent.mcp_agent._estimate_tool_schema_tokens', return_value=100):
            selected, used, dropped = _budget_select_tools(
                tools,
                system_prompt_text='',
                input_text='x' * 3600,
                chat_history=[],
                global_execution_plan=None,
            )

        self.assertEqual([tool.name for tool in selected], ['execute_command'])
        self.assertEqual(used, 100)
        self.assertEqual(dropped, 4)

    def test_exhausted_prompt_budget_does_not_reopen_fresh_tool_budget(self):
        tools = [
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
            SimpleNamespace(name='chat_agent_pythonxer', description='Launch Pythonxer.'),
            SimpleNamespace(name='chat_agent_kalier', description='Kali operations.'),
        ]

        with patch('agent.mcp_agent.get_int_config_value', return_value=1000), \
                patch('agent.mcp_agent._estimate_tool_schema_tokens', return_value=100):
            selected, used, dropped = _budget_select_tools(
                tools,
                system_prompt_text='',
                input_text='x' * 5000,
                chat_history=[],
                global_execution_plan=None,
            )

        self.assertEqual(selected, [])
        self.assertEqual(used, 0)
        self.assertEqual(dropped, 3)

    def test_safe_prompt_budget_still_binds_full_surface(self):
        tools = [
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
            SimpleNamespace(name='get_current_time', description='Return the current date and time.'),
            SimpleNamespace(name='chat_agent_kalier', description='Kali operations.'),
        ]

        with patch('agent.mcp_agent.get_int_config_value', return_value=20000), \
                patch('agent.mcp_agent._estimate_tool_schema_tokens', return_value=100):
            selected, used, dropped = _budget_select_tools(
                tools,
                system_prompt_text='system prompt',
                input_text='short request',
                chat_history=[],
                global_execution_plan=None,
            )

        self.assertEqual([tool.name for tool in selected], [tool.name for tool in tools])
        self.assertEqual(used, 300)
        self.assertEqual(dropped, 0)


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


class AcpxCapabilityScoringTests(TestCase):
    """
    The ACPX tool surface (acp_send_and_wait, acp_transcript, acp_relay,
    acp_session_status, acp_list_sessions) was originally invisible on
    the planner path because each tool scored ~10 and lost the slot
    race to higher-scoring chat_agent_* peers. These tests pin the
    keyword-boost contract added by the ACPX-section-A follow-up so the
    new tools reliably make the cut on real ACPX prompts.
    """

    @staticmethod
    def _full_acpx_toolset():
        """A representative slice of the live tool surface with both
        ACPX tools and competing wrapped chat agents. Same shape as
        what get_mcp_tools() produces in production."""
        return [
            SimpleNamespace(name='execute_file', description='Execute a Python file.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
            SimpleNamespace(name='chat_agent_executer', description='Launch the Executer template agent.'),
            SimpleNamespace(name='chat_agent_pythonxer', description='Launch the Pythonxer template agent.'),
            SimpleNamespace(name='chat_agent_dockerer', description='Launch the Dockerer template agent.'),
            SimpleNamespace(name='chat_agent_jenkinser', description='Launch the Jenkinser template agent.'),
            SimpleNamespace(name='chat_agent_summarize_text', description='Summarize text.'),
            SimpleNamespace(name='chat_agent_file_creator', description='Create files.'),
            SimpleNamespace(name='chat_agent_notifier', description='Send a desktop notification.'),
            SimpleNamespace(name='chat_agent_run_list', description='List wrapped runs.'),
            SimpleNamespace(name='chat_agent_run_status', description='Get wrapped run status.'),
            SimpleNamespace(name='chat_agent_run_log', description='Read wrapped run log.'),
            SimpleNamespace(name='chat_agent_run_stop', description='Stop a wrapped run.'),
            SimpleNamespace(name='acp_spawn', description='Spawn an external coding-agent CLI as an ACP child.'),
            SimpleNamespace(name='acp_send', description='Send a follow-up turn to an existing ACP session.'),
            SimpleNamespace(name='acp_send_and_wait', description='Send a follow-up turn and wait for the child to settle.'),
            SimpleNamespace(name='acp_kill', description='Terminate an ACP session.'),
            SimpleNamespace(name='acp_doctor', description='Run a health probe of the ACPX runtime.'),
            SimpleNamespace(name='acp_transcript', description='Read the on-disk transcript for an ACP session.'),
            SimpleNamespace(name='acp_session_status', description='Return the current status of one ACP session.'),
            SimpleNamespace(name='acp_list_sessions', description='Enumerate live ACP sessions.'),
            SimpleNamespace(name='acp_relay', description='Hand off content from one ACP session to another.'),
            SimpleNamespace(name='list_acp_agents', description='List all registered ACP agents.'),
            SimpleNamespace(name='invoke_skill', description='Invoke a registered Tlamatini skill.'),
            SimpleNamespace(name='list_skills', description='List all registered Tlamatini skills.'),
        ]

    def test_acp_transcript_is_selected_on_harvest_transcript_prompt(self):
        from agent.capability_registry import (
            _normalize_text,
            _score_capability,
            _tokenize,
            build_tool_capabilities,
        )

        tools = self._full_acpx_toolset()
        prompt = (
            "Step 5: harvest the transcript from acp_spawn session_id, "
            "summarize it, and cite the transcript_path as evidence."
        )
        capabilities = build_tool_capabilities(tools)
        text = _normalize_text(prompt)
        toks = _tokenize(text)
        scores = {c.tool_name: _score_capability(c, text, toks) for c in capabilities}

        # acp_transcript must outscore any chat_agent_* peer on this prompt.
        wrapped_peer_max = max(
            score for name, score in scores.items() if name.startswith("chat_agent_")
        )
        self.assertGreater(scores["acp_transcript"], wrapped_peer_max,
                            f"transcript={scores['acp_transcript']} peer_max={wrapped_peer_max}")

    def test_acp_relay_is_selected_on_handoff_prompt(self):
        from agent.capability_registry import (
            _normalize_text,
            _score_capability,
            _tokenize,
            build_tool_capabilities,
        )

        tools = self._full_acpx_toolset()
        prompt = (
            "Multi-CLI ACPX Relay demo: hand off the analysis from leg A to "
            "leg B by relaying the transcript content into the second session."
        )
        capabilities = build_tool_capabilities(tools)
        text = _normalize_text(prompt)
        toks = _tokenize(text)
        scores = {c.tool_name: _score_capability(c, text, toks) for c in capabilities}

        self.assertGreaterEqual(scores["acp_relay"], 24,
                                 f"acp_relay scored {scores['acp_relay']} (need ≥24)")

    def test_acp_send_and_wait_is_selected_on_wait_for_answer_prompt(self):
        from agent.capability_registry import (
            _normalize_text,
            _score_capability,
            _tokenize,
            build_tool_capabilities,
        )

        tools = self._full_acpx_toolset()
        prompt = (
            "Spawn the gemini agent and wait for the complete answer to "
            "settle before continuing. Use synchronous send-and-wait."
        )
        capabilities = build_tool_capabilities(tools)
        text = _normalize_text(prompt)
        toks = _tokenize(text)
        scores = {c.tool_name: _score_capability(c, text, toks) for c in capabilities}

        self.assertGreaterEqual(scores["acp_send_and_wait"], 24)

    def test_acp_session_status_and_list_score_above_threshold_on_status_prompt(self):
        from agent.capability_registry import (
            _normalize_text,
            _score_capability,
            _tokenize,
            build_tool_capabilities,
        )

        tools = self._full_acpx_toolset()
        prompt = (
            "List all live ACP sessions and report which session_id is alive "
            "with its pid and transcript size."
        )
        capabilities = build_tool_capabilities(tools)
        text = _normalize_text(prompt)
        toks = _tokenize(text)
        scores = {c.tool_name: _score_capability(c, text, toks) for c in capabilities}

        # Both must be well above the planner threshold of 6.
        self.assertGreaterEqual(scores["acp_list_sessions"], 14)
        self.assertGreaterEqual(scores["acp_session_status"], 14)

    def test_select_tools_for_request_picks_acp_transcript_on_harvest_prompt(self):
        tools = self._full_acpx_toolset()
        selected = select_tools_for_request(
            "Step 5: harvest the transcript via acp_transcript and cite "
            "transcript_path as evidence in the report.",
            tools,
            max_selected=8,
        )
        names = {t.name for t in selected}
        self.assertIn("acp_transcript", names)

    def test_select_tools_for_request_picks_acp_relay_on_handoff_prompt(self):
        tools = self._full_acpx_toolset()
        selected = select_tools_for_request(
            "Hand off the leg A transcript to leg B using acp_relay so the "
            "second ACP child can produce a verdict.",
            tools,
            max_selected=8,
        )
        names = {t.name for t in selected}
        self.assertIn("acp_relay", names)

    def test_acpx_signal_token_boost_compounds(self):
        """Multiple ACPX signal tokens compound to push scores past the
        chat_agent_* peer plateau (the original failure mode at score=10)."""
        from agent.capability_registry import (
            _normalize_text,
            _score_capability,
            _tokenize,
            build_tool_capabilities,
        )

        tools = self._full_acpx_toolset()
        prompt = (
            "ACPX run: spawn an agent_id child, harvest the transcript, "
            "relay to a second session, then kill both legs."
        )
        capabilities = build_tool_capabilities(tools)
        text = _normalize_text(prompt)
        toks = _tokenize(text)
        scores = {c.tool_name: _score_capability(c, text, toks) for c in capabilities}

        # All four mutating ACPX tools should ride the boost above 18.
        for name in ("acp_spawn", "acp_relay", "acp_transcript", "acp_kill"):
            self.assertGreaterEqual(scores[name], 18,
                                     f"{name}={scores[name]}")


class AcpxPlannerCoSelectionTests(TestCase):
    """
    The planner must auto-co-select operational siblings of primary
    ACPX tools (acp_spawn → acp_doctor + acp_kill, acp_relay →
    acp_transcript + acp_kill). Same shape as the run-control
    auto-injection contract.
    """

    @staticmethod
    def _toolset():
        return AcpxCapabilityScoringTests._full_acpx_toolset()

    def test_acp_spawn_co_selects_doctor_and_kill_in_planner(self):
        tools = self._toolset()
        plan = build_global_execution_plan(
            "Spawn the gemini agent_id with task 'analyze trade-offs' and "
            "verify the ACPX runtime first.",
            tools,
            system_enabled=False,
            files_enabled=False,
            max_selected_tools=6,
        )
        self.assertIn("acp_spawn", plan.selected_tool_names)
        self.assertIn("acp_doctor", plan.selected_tool_names)
        self.assertIn("acp_kill", plan.selected_tool_names)

    def test_acp_relay_co_selects_transcript_and_kill_in_planner(self):
        tools = self._toolset()
        plan = build_global_execution_plan(
            "Use acp_relay to hand off content from session A to session B "
            "as part of the multi-cli relay.",
            tools,
            system_enabled=False,
            files_enabled=False,
            max_selected_tools=6,
        )
        self.assertIn("acp_relay", plan.selected_tool_names)
        self.assertIn("acp_transcript", plan.selected_tool_names)
        self.assertIn("acp_kill", plan.selected_tool_names)

    def test_acp_send_and_wait_co_selects_transcript_in_planner(self):
        tools = self._toolset()
        plan = build_global_execution_plan(
            "Use acp_send_and_wait so the gemini child has time to produce "
            "the complete answer; then summarize and cite evidence.",
            tools,
            system_enabled=False,
            files_enabled=False,
            max_selected_tools=6,
        )
        self.assertIn("acp_send_and_wait", plan.selected_tool_names)
        self.assertIn("acp_transcript", plan.selected_tool_names)

    def test_select_tools_for_request_co_selects_acpx_siblings(self):
        tools = AcpxCapabilityScoringTests._full_acpx_toolset()
        selected = select_tools_for_request(
            "Spawn the gemini agent_id and have it analyze the project.",
            tools,
            max_selected=3,  # Force a tight cap to prove sibling injection works.
        )
        names = {t.name for t in selected}
        self.assertIn("acp_spawn", names)
        # Even with max_selected=3, doctor + kill must be auto-injected.
        self.assertIn("acp_doctor", names)
        self.assertIn("acp_kill", names)

    def test_co_selection_is_idempotent_when_sibling_already_selected(self):
        """If both acp_spawn and acp_kill score high enough independently,
        the co-selection rule must not double-add or reorder them."""
        tools = AcpxCapabilityScoringTests._full_acpx_toolset()
        plan = build_global_execution_plan(
            "Spawn the gemini agent_id, run the task, then call acp_kill on "
            "the session.",
            tools,
            system_enabled=False,
            files_enabled=False,
            max_selected_tools=6,
        )
        # No duplicates in the selected list.
        self.assertEqual(len(plan.selected_tool_names),
                         len(set(plan.selected_tool_names)))
        self.assertIn("acp_spawn", plan.selected_tool_names)
        self.assertIn("acp_kill", plan.selected_tool_names)


class AcpxNonAcpxRequestRegressionTests(TestCase):
    """The new ACPX boosts must NOT bleed into requests that have nothing
    to do with ACPX. Otherwise the planner would start auto-injecting
    acp_doctor / acp_kill on shell-command requests."""

    def test_pure_shell_request_does_not_pull_in_acpx_tools(self):
        # Production always runs with at least one MCP context enabled, so
        # the realistic threshold is 6, not the empty-context fallback of 2.
        tools = AcpxCapabilityScoringTests._full_acpx_toolset()
        plan = build_global_execution_plan(
            "Run 'pip install requests' in the project directory.",
            tools,
            system_enabled=True,
            files_enabled=True,
            max_selected_tools=6,
        )
        for name in plan.selected_tool_names:
            self.assertFalse(
                name.startswith("acp_"),
                f"unexpected ACPX tool {name} on a pure shell request",
            )

    def test_pure_summarization_request_does_not_pull_in_acpx_tools(self):
        tools = AcpxCapabilityScoringTests._full_acpx_toolset()
        plan = build_global_execution_plan(
            "Summarize this README.md and produce a 5-bullet overview.",
            tools,
            system_enabled=True,
            files_enabled=True,
            max_selected_tools=6,
        )
        for name in plan.selected_tool_names:
            self.assertFalse(
                name.startswith("acp_"),
                f"unexpected ACPX tool {name} on a pure summarization request",
            )


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
        executor._get_executor_for_tools = (
            lambda tools_subset, step_by_step_enabled=False: _RecordingExecutor()
        )

        with patch('agent.external_mcp_manager.get_external_mcp_tools', return_value=[]):
            result = CapabilityAwareToolAgentExecutor.invoke(
                executor,
                {'input': 'run something', 'multi_turn_enabled': True},
            )

        self.assertEqual(result, {'output': 'ok'})
        self.assertEqual(observed, [True])
        self.assertFalse(get_request_state('suppress_visible_consoles', False))

    def test_multi_turn_binds_full_surface_even_with_a_narrow_plan(self):
        # MANDATE (<REDACTED>, 2026-06-16): Multi-Turn binds EVERY enabled tool — even
        # when the planner named only a subset. The operator loop must never be
        # starved ("I don't have a file-writing or shell tool bound this turn").
        captured = {}

        class _RecordingExecutor:
            def __init__(self, tool_names):
                self.tool_names = tool_names

            def invoke(self, payload):
                captured['tool_names'] = self.tool_names
                captured['payload'] = payload
                return {'output': 'ok'}

        class _BindableLLM:
            def bind_tools(self, tools):
                return self
            def invoke(self, messages):
                return SimpleNamespace(content='', tool_calls=[])

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = _BindableLLM()
        executor.preeliminary_prompt = ''
        executor.tools = [
            SimpleNamespace(name='get_current_time', description='Return current time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor(['legacy'])
        executor._get_executor_for_tools = (
            lambda tools_subset, step_by_step_enabled=False: _RecordingExecutor([tool.name for tool in tools_subset])
        )

        with patch('agent.external_mcp_manager.get_external_mcp_tools', return_value=[]):
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
        # The plan named only get_current_time, but Multi-Turn binds the FULL surface.
        self.assertEqual(captured['tool_names'], ['get_current_time', 'execute_command'])
        # The planner summary is still forwarded for the prompt's ordering hint.
        self.assertEqual(captured['payload']['planner_summary'], 'use get_current_time only')

    def test_multi_turn_binds_full_surface_even_for_context_only_plan(self):
        # MANDATE (<REDACTED>, 2026-06-16): even a context_only plan must NOT starve
        # Multi-Turn — the user may still ask Tlamatini to ACT, so every enabled
        # tool stays available. (This deliberately reverses the old "context_only
        # binds zero tools" behavior.)
        captured = {}

        class _RecordingExecutor:
            def __init__(self, tool_names):
                self.tool_names = tool_names

            def invoke(self, payload):
                captured['tool_names'] = self.tool_names
                captured['payload'] = payload
                return {'output': 'ok'}

        class _BindableLLM:
            def bind_tools(self, tools):
                return self
            def invoke(self, messages):
                return SimpleNamespace(content='', tool_calls=[])

        executor = CapabilityAwareToolAgentExecutor.__new__(CapabilityAwareToolAgentExecutor)
        executor.llm = _BindableLLM()
        executor.preeliminary_prompt = ''
        executor.tools = [
            SimpleNamespace(name='get_current_time', description='Return current time.'),
            SimpleNamespace(name='execute_command', description='Execute a shell command.'),
        ]
        executor.max_iterations = 1
        executor._executor_cache = {}
        executor.legacy_executor = _RecordingExecutor(['legacy'])
        executor._get_executor_for_tools = (
            lambda tools_subset, step_by_step_enabled=False: _RecordingExecutor([tool.name for tool in tools_subset])
        )

        with patch('agent.external_mcp_manager.get_external_mcp_tools', return_value=[]):
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
        # context_only no longer starves Multi-Turn: the full surface stays bound.
        self.assertEqual(captured['tool_names'], ['get_current_time', 'execute_command'])

    def test_capability_executor_ignores_global_plan_when_multi_turn_disabled(self):
        # When Multi-Turn is disabled (and ACPX off), the executor must IGNORE
        # the global execution plan entirely and fall back to the legacy
        # one-shot binding. The current implementation builds a FRESH
        # MultiTurnToolAgentExecutor over the request-scoped (acpx-filtered) tool
        # set rather than reusing self.legacy_executor (so disabling ACPX in
        # legacy mode also strips the ACPX tools from the LLM bind_tools list).
        captured = {}

        class _RecordingLegacyExecutor:
            def __init__(self, llm=None, system_prompt='', tools=None, max_iterations=1):
                captured['tools'] = [tool.name for tool in (tools or [])]
                captured['max_iterations'] = max_iterations

            def invoke(self, payload):
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
        # self.legacy_executor (the cached full-tool executor) must NOT run on the
        # acpx-disabled legacy path — it builds a FRESH executor over the
        # request-scoped tools via the real _get_executor_for_tools (which
        # constructs the patched MultiTurnToolAgentExecutor below).
        executor.legacy_executor = SimpleNamespace(
            invoke=lambda payload: (_ for _ in ()).throw(
                AssertionError('self.legacy_executor must not run on the acpx-disabled legacy path')))

        with patch('agent.mcp_agent.MultiTurnToolAgentExecutor', _RecordingLegacyExecutor), \
             patch('agent.external_mcp_manager.get_external_mcp_tools', return_value=[]):
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
        # Fresh legacy executor built over the full request-scoped tool set...
        self.assertEqual(captured['tools'], ['get_current_time', 'execute_command'])
        # ...and the global plan was NOT forwarded (multi-turn disabled ignores it).
        self.assertEqual(captured['payload']['input'], 'Tell me the current time.')
        self.assertEqual(captured['payload']['chat_history'], [])
        self.assertNotIn('global_execution_plan', captured['payload'])

    def test_launch_in_new_terminal_opens_visible_new_console_when_not_suppressed(self):
        with patch('agent.tools.subprocess.Popen', return_value=SimpleNamespace(pid=1234)) as mock_popen:
            agent_tools.launch_in_new_terminal(r'C:\Temp\demo.py', '--flag "hello world"')

        args, kwargs = mock_popen.call_args
        if os.name == 'nt':
            # Robust visible console: cmd.exe via CREATE_NEW_CONSOLE + an explicit
            # SW_SHOWNORMAL STARTUPINFO — NOT `start ... shell=True`, which was a
            # confirmed false-OK in the Daphne worker thread (no console/window
            # station) and let cmd AutoRun overwrite the title.
            self.assertFalse(kwargs.get('shell', False))
            self.assertIn('cmd.exe /k title Tlamatini Console - demo.py', args[0])
            self.assertIn(r'C:\Temp\demo.py', args[0])
            self.assertEqual(
                kwargs.get('creationflags', 0),
                subprocess.CREATE_NEW_CONSOLE,
            )
            startupinfo = kwargs.get('startupinfo')
            self.assertIsNotNone(startupinfo)
            self.assertEqual(startupinfo.wShowWindow, 1)  # SW_SHOWNORMAL
        else:
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

    def _run_execute_file_foreground(self, verify_result):
        """Drive the REAL execute_file foreground path with a valid temp script,
        a no-op launch, and a stubbed window-verification verdict."""
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as handle:
            handle.write("print('ok')\n")
            script_path = handle.name

        def _cleanup_script():
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
            except PermissionError:
                pass

        self.addCleanup(_cleanup_script)
        with patch('agent.tools._resolve_script_path', return_value=script_path), \
                patch('agent.tools.validate_tool_path', return_value=None), \
                patch('agent.tools.launch_in_new_terminal') as mock_launch, \
                patch('agent.tools._verify_foreground_window', return_value=verify_result):
            result = agent_tools.execute_file.func(script_path, foreground=True)
        mock_launch.assert_called_once()
        # foreground=True must propagate as force_foreground=True.
        self.assertTrue(mock_launch.call_args.kwargs.get('force_foreground'))
        return result

    def test_execute_file_foreground_confirms_when_window_verified(self):
        result = self._run_execute_file_foreground(True)
        self.assertIn('CONFIRMED', result)
        self.assertNotIn('did NOT appear', result)

    def test_execute_file_foreground_reports_failure_when_window_missing(self):
        # The whole point: NO MORE false-OK. A window that never appeared must be
        # reported as a failure the LLM can act on, not "ran visibly on your desktop".
        result = self._run_execute_file_foreground(False)
        self.assertIn('did NOT appear', result)
        self.assertIn('DO NOT report this as success', result)

    def test_execute_file_foreground_neutral_when_unverifiable(self):
        result = self._run_execute_file_foreground(None)
        self.assertIn('could not be', result)
        self.assertNotIn('CONFIRMED', result)
        self.assertNotIn('did NOT appear', result)

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

        # Gitter (like every section-generating agent) now emits the unified
        # INI_SECTION_<TYPE><<< ... >>>END_SECTION_<TYPE> format. The parser must
        # return ONLY the first complete block and not bleed into the second.
        unread_log = (
            "noise before blocks\n"
            "INI_SECTION_GITTER<<<\n"
            "git_command: git status\n"
            "\n"
            "first body\n"
            ">>>END_SECTION_GITTER\n"
            "INI_SECTION_GITTER<<<\n"
            "git_command: git diff\n"
            "\n"
            "second body\n"
            ">>>END_SECTION_GITTER\n"
        )

        output_block, end_bytes = parametrizer_module.extract_next_output_block('gitter', unread_log)

        expected_prefix = (
            "noise before blocks\n"
            "INI_SECTION_GITTER<<<\n"
            "git_command: git status\n"
            "\n"
            "first body\n"
            ">>>END_SECTION_GITTER"
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
            target_log_path = os.path.join(target_dir, 'prompter_1.log')
            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({
                    'prompt': 'Please summarize:\n\n{content}\n\nCommand: {command}',
                }, handle, sort_keys=False)
            with open(target_log_path, 'w', encoding='utf-8') as handle:
                handle.write('target output for segment 1\n')

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
            with open(os.path.join(target_dir, 'prompter_1_segment_1.log'), 'r', encoding='utf-8') as handle:
                archived_log = handle.read()
            self.assertEqual(archived_log, 'target output for segment 1\n')
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
            target_log_path = os.path.join(target_dir, 'prompter_1.log')
            with open(config_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'mutated value'}, handle, sort_keys=False)
            with open(backup_path, 'w', encoding='utf-8') as handle:
                yaml.safe_dump({'prompt': 'template value'}, handle, sort_keys=False)
            with open(target_log_path, 'w', encoding='utf-8') as handle:
                handle.write('target output for segment 3\n')

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
            with open(os.path.join(target_dir, 'prompter_1_segment_3.log'), 'r', encoding='utf-8') as handle:
                archived_log = handle.read()
            self.assertEqual(archived_log, 'target output for segment 3\n')
            self.assertEqual(recovered['offset'], 48)
            self.assertEqual(recovered['processed_count'], 3)
            self.assertEqual(recovered['stage'], parametrizer_module.STATE_STAGE_IDLE)
            self.assertIsNone(recovered['inflight_block'])
            self.assertIsNone(recovered['inflight_end_offset'])
            self.assertEqual(saved_states[-1]['offset'], 48)


class AssignmentParserRobustnessTests(TestCase):
    """Regression coverage for the tools.py key=value parser.

    These tests pin the fixes that prevent multi-line Python scripts with
    embedded apostrophes (``node's knapsack``, ``"w"`` kwargs, ``r\"\"\"``
    docstrings) from being truncated or from leaving a stray leading quote
    on the coerced value — the root cause of the ``SyntaxError:
    unterminated string literal`` failure in pythonxer_010.
    """

    def setUp(self):
        from agent.tools import (
            _coerce_assignment_value,
            _extract_verbatim_assignment,
            _parse_requested_assignments,
            _split_assignment_segment,
            _split_assignment_segments,
        )
        self._split_segments = _split_assignment_segments
        self._split_segment = _split_assignment_segment
        self._coerce_value = _coerce_assignment_value
        self._parse_assignments = _parse_requested_assignments
        self._extract_verbatim = _extract_verbatim_assignment

    def test_multi_line_script_with_embedded_apostrophes_parses(self):
        failing = (
            "script='\n"
            "import os\n"
            'base = r"C:\\Development\\AngysBackInCUDA"\n'
            'content = r"""# Distributed Multiple Knapsack Solver\n'
            "\n"
            "The worker's GPU runs HyperQ. Each node's knapsack gets other nodes' items.\n"
            "Don't put a node's own items in its own knapsack.\n"
            '"""\n'
            "with open(os.path.join(base, 'README.md'), 'w') as f:\n"
            "    f.write(content)\n"
            "'\n"
        )

        segments = self._split_segments(failing)
        self.assertEqual(len(segments), 1)

        key, value = self._split_segment(segments[0])
        self.assertEqual(key, 'script')

        coerced = self._coerce_value(value)
        self.assertIsInstance(coerced, str)
        self.assertFalse(coerced.startswith("'"),
                         f"leading orphan quote: {coerced[:40]!r}")
        # Must parse as real Python — this is the syntactic contract Pythonxer depends on.
        ast.parse(coerced)
        self.assertIn('import os', coerced)

    def test_comma_separated_multi_assignment_still_splits(self):
        request = (
            "smtp.host='smtp.gmail.com', "
            "smtp.port=587, "
            "smtp.username='user@example.com', "
            "subject='Hello', "
            "body='All good'"
        )
        segments = self._split_segments(request)
        self.assertEqual(len(segments), 5)

    def test_triple_quoted_value_round_trips(self):
        request = (
            'script="""import os\n'
            "# docstring with don't worry\n"
            "print('hello')"
            '"""'
        )
        segments = self._split_segments(request)
        self.assertEqual(len(segments), 1)
        key, value = self._split_segment(segments[0])
        self.assertEqual(key, 'script')
        coerced = self._coerce_value(value)
        ast.parse(coerced)
        self.assertIn('import os', coerced)

    def test_single_line_python_kwargs_do_not_split_on_inner_comma(self):
        # Regression: Python kwargs like open(path, 'w', encoding='utf-8')
        # must not trick the parser into treating the inner ``',`` as a
        # top-level separator when the outer value is a multi-line script.
        request = (
            "script='\n"
            "with open('f.txt', 'w', encoding='utf-8') as f:\n"
            "    f.write(\"hello\")\n"
            "'"
        )
        segments = self._split_segments(request)
        self.assertEqual(len(segments), 1)
        key, value = self._split_segment(segments[0])
        self.assertEqual(key, 'script')
        coerced = self._coerce_value(value)
        ast.parse(coerced)

    def test_coerce_strips_orphan_leading_quote(self):
        # Direct coverage of the salvage branch: a value that starts with
        # ``'`` but whose closing quote was lost earlier should not retain
        # the leading ``'`` (which would become line 1 of a Python script
        # and raise SyntaxError at subprocess time).
        coerced = self._coerce_value("'\nimport os\nprint('hi')")
        self.assertIsInstance(coerced, str)
        self.assertFalse(coerced.startswith("'"))

    def test_parametric_pythonxer_example_request_still_parses(self):
        # The canonical example from WRAPPED_CHAT_AGENT_SPECS must keep working.
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_pythonxer']
        parsed, err = self._parse_assignments(spec.example_request)
        self.assertIsNone(err)
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertIn('script', values)
        ast.parse(values['script'])

    def test_and_conjunction_splits_file_creator_pair(self):
        # Regression for the AngysBackInCUDA failure mode: file_creator runs
        # 001-006 each produced garbage paths like
        # ``C:\\...\\drone_knap.h' and content='/*...`` because the parser
        # only split on ``,``/``;`` while the LLM uses ``and`` (per the
        # registry's example_request style). The conjunction must become a
        # top-level separator. The content value intentionally contains a
        # real embedded apostrophe (``nodes' knapsacks``) — the exact
        # pattern that appeared in the failing production runs.
        request = (
            "filepath='C:\\Development\\AngysBackInCUDA\\drone_knap.h' "
            "and content='/* drone_knap.h\n"
            " * nodes' knapsacks contain other nodes' items\n"
            " */'"
        )
        parsed, err = self._parse_assignments(request)
        self.assertIsNone(err, f"parse error: {err}")
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertIn('filepath', values)
        self.assertIn('content', values)
        # file_path must NOT contain ``and content=`` — that is the canary
        # for the old broken behavior (splitter failed, value absorbed tail).
        self.assertNotIn(" and content=", str(values['filepath']))
        self.assertNotIn("and content=", str(values['filepath']))
        self.assertTrue(
            str(values['filepath']).endswith('drone_knap.h'),
            f"filepath was {values['filepath']!r}",
        )
        # Content should round-trip and include the body markers.
        self.assertIn('drone_knap.h', str(values['content']))
        self.assertIn('*/', str(values['content']))

    def test_same_line_multiline_content_with_quote_semicolon_not_truncated(self):
        # Regression for the SuperDemoPage SecurityHeadersFilter.java
        # truncation (2026-06-12): the LLM opened the content quote on the
        # SAME line as the payload (``content='package com…`` — no newline
        # right after the quote), so _is_multiline_quote_open() left the
        # value in single-line mode, where ANY internal quote followed by
        # ``;``/``,`` closes it. Java CSP literals contain exactly that
        # sequence (``'self';``), so the file was cut mid-line at
        # ``"default-src 'self`` while the Exec Report (which renders the
        # raw pre-parse request) looked complete. The fix upgrades the
        # value to multi-line mode the moment a newline is consumed inside
        # it. This test reproduces the incident content byte-faithfully.
        java = (
            "package com.superdemo.filter;\n"
            "\n"
            "/**\n"
            " * The CSP is strict but compatible with the demo page (Google\n"
            " * Fonts + inline styles permitted for the theme switcher; no\n"
            " * inline scripts, no eval, no remote frames).\n"
            " */\n"
            "public class SecurityHeadersFilter implements Filter {\n"
            "\n"
            "    private static final String HSTS =\n"
            "            \"max-age=31536000; includeSubDomains; preload\";\n"
            "\n"
            "    private static final String CSP =\n"
            "            \"default-src 'self'; \"\n"
            "          + \"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; \"\n"
            "          + \"object-src 'none'\";\n"
            "}\n"
        )
        request = (
            "filepath='C:\\Development\\SuperDemoPage\\src\\main\\java\\com\\"
            "superdemo\\filter\\SecurityHeadersFilter.java' "
            "and content='" + java.rstrip() + "'"
        )
        parsed, err = self._parse_assignments(request)
        self.assertIsNone(err, f"parse error: {err}")
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertIn('filepath', values)
        self.assertIn('content', values)
        content = str(values['content'])
        # The old bug cut the value at the first ``'self';`` — everything
        # after ``"default-src 'self`` vanished. The full payload must
        # survive, all the way to the closing brace.
        self.assertIn("\"default-src 'self'; \"", content)
        self.assertIn("'unsafe-inline'", content)
        self.assertIn("object-src 'none'", content)
        self.assertTrue(content.rstrip().endswith('}'),
                        f"content truncated; tail = {content[-60:]!r}")
        self.assertEqual(content, java.rstrip())

    def test_verbatim_keeps_java_regex_backslashes(self):
        # Regression for the FormValidatorGeneratingClass.java corruption
        # (Eclipse: "illegal escape character" / "unclosed string literal"):
        # the generic value coercion collapses ``\\`` -> ``\`` (shell/SQL
        # escaping), so a Java regex source ``Pattern.compile("\\.")`` (whose
        # ON-DISK bytes are two backslashes + dot) came out as ``"\."`` — an
        # illegal Java escape. The verbatim extractor must return the content
        # BYTE-FOR-BYTE, backslashes intact.
        java = (
            "package com.example.validation;\n"
            "\n"
            "import java.util.regex.Pattern;\n"
            "\n"
            "public class FormValidatorGeneratingClass {\n"
            "    private static final Pattern EMAIL =\n"
            "        Pattern.compile(\"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}$\");\n"
            "    private static final Pattern DIGITS = Pattern.compile(\"\\\\d+\");\n"
            "    private static final String TAB = \"\\t\";\n"
            "}\n"
        )
        request = (
            "filepath='C:\\Dev\\App\\FormValidatorGeneratingClass.java' "
            "and content='" + java.rstrip() + "'"
        )
        verbatim = self._extract_verbatim(request, "content")
        self.assertIsNotNone(verbatim)
        # Byte-exact: the double-backslash regex escapes survive untouched.
        self.assertEqual(verbatim, java.rstrip())
        self.assertIn('\\\\.[A-Za-z]', verbatim)   # ``\\.`` still two backslashes
        self.assertIn('\\\\d+', verbatim)            # ``\\d`` still two backslashes
        self.assertIn('\\t', verbatim)               # literal backslash-t survives
        # The CURRENT generic coercion would have collapsed these — prove the
        # verbatim path diverges from it exactly where it must.
        values = {a['requested_key']: a['value']
                  for a in self._parse_assignments(request)[0]['assignments']}
        self.assertNotEqual(
            values['content'], verbatim,
            "generic coercion unexpectedly already byte-exact — test is moot",
        )

    def test_verbatim_handles_content_first_then_filepath(self):
        # content may be sent BEFORE filepath; the verbatim extractor must
        # still find it and stop at the ``and filepath=`` boundary.
        request = (
            "content='line1 with a \\\\ backslash\nline2' "
            "and filepath='C:\\Dev\\out.txt'"
        )
        verbatim = self._extract_verbatim(request, "content")
        self.assertEqual(verbatim, "line1 with a \\\\ backslash\nline2")
        self.assertNotIn('filepath', verbatim)

    def test_verbatim_returns_none_for_unquoted_or_missing(self):
        self.assertIsNone(self._extract_verbatim("filepath='x'", "content"))
        self.assertIsNone(
            self._extract_verbatim("content=bare unquoted value", "content"))

    def test_with_conjunction_also_splits(self):
        # ``with`` is the alternate conjunction used by several
        # example_request strings (e.g. the crawler's sample).
        request = (
            "url='https://example.com' "
            "with system_prompt='Extract the headings' "
            "and content_mode='text'"
        )
        parsed, err = self._parse_assignments(request)
        self.assertIsNone(err, f"parse error: {err}")
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertEqual(values['url'], 'https://example.com')
        self.assertEqual(values['system_prompt'], 'Extract the headings')
        self.assertEqual(values['content_mode'], 'text')

    def test_parametric_file_creator_example_request_parses(self):
        # The registry's canonical example_request for file_creator must
        # round-trip through the parser without collapsing into a single arg.
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_file_creator']
        parsed, err = self._parse_assignments(spec.example_request)
        self.assertIsNone(err, f"parse error: {err}")
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertIn('filepath', values)
        self.assertIn('content', values)
        # Neither value must contain the conjunction — that is the
        # canary for a failed split.
        self.assertNotIn(' and ', str(values['filepath']))
        self.assertNotIn(' and ', str(values['content'])[:80])

    def test_no_registry_example_leaks_conjunction_into_a_value(self):
        """Every registry example must parse without leaking a conjunction
        (``and KEY=`` / ``with KEY=``) into any resulting value.

        This is the real invariant that the file_creator regression
        violated: the file_path value absorbed the whole ``and content=…``
        tail. Counting segments is unreliable (examples embed literal
        commas inside script bodies, and ``with`` appears as both a
        separator and a natural-language preamble), but scanning values
        for a leaked conjunction cleanly distinguishes broken-parse from
        healthy-parse every time.
        """
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        leak_pattern = re.compile(
            r"""['"]\s+(?:and|with)\s+[A-Za-z_][A-Za-z0-9_.\-]*\s*=""",
            flags=re.IGNORECASE,
        )
        for spec in WRAPPED_CHAT_AGENT_SPECS:
            parsed, err = self._parse_assignments(spec.example_request)
            self.assertIsNone(
                err,
                f"[{spec.key}] parse error on canonical example: {err}\n"
                f"example = {spec.example_request!r}",
            )
            for assignment in parsed['assignments']:
                value_repr = repr(assignment['value'])
                # Scan the first 160 chars: long script bodies can
                # legitimately contain ``and``/``with`` as English words,
                # but a leaked separator ALWAYS appears close to the
                # start, right after the first real value's closing quote.
                head = value_repr[:160]
                self.assertIsNone(
                    leak_pattern.search(head),
                    f"[{spec.key}] key={assignment['requested_key']!r} value "
                    f"leaked a conjunction separator: {head!r}\n"
                    f"example = {spec.example_request!r}",
                )

    def test_windows_path_backslash_escapes_are_preserved(self):
        # Regression for the AngysBackInCUDA file_creator_001 failure: the
        # LLM sent ``filepath='C:\Development\AngysBackInCUDA\angys_knapsack.cuh'``
        # and ``ast.literal_eval`` decoded ``\a`` as 0x07 (bell), so
        # file_creator tried to create
        # ``C:\Development\AngysBackInCUDA\x07ngys_knapsack.cuh`` and the
        # OS returned [Errno 22] Invalid argument. A Windows path must
        # round-trip byte-for-byte through _coerce_assignment_value.
        hazards = [
            r"C:\Development\AngysBackInCUDA\angys_knapsack.cuh",   # \a -> bell
            r"C:\Users\angel\bin\tool.exe",                         # \b -> backspace
            r"C:\temp\file.txt",                                    # \t -> tab
            r"D:\var\vendor\pkg",                                   # \v -> vertical tab
            r"C:\new\path.log",                                     # \n -> newline
            r"C:\repo\readme.md",                                   # \r -> CR
            r"C:\forms\form.pdf",                                   # \f -> form feed
            r"C:\x07 and \0nul\junk",                               # \xNN and \0
        ]
        for raw in hazards:
            single = f"'{raw}'"
            double = f'"{raw}"'
            self.assertEqual(
                self._coerce_value(single), raw,
                f"single-quoted Windows path corrupted: {raw!r} -> {self._coerce_value(single)!r}",
            )
            self.assertEqual(
                self._coerce_value(double), raw,
                f"double-quoted Windows path corrupted: {raw!r} -> {self._coerce_value(double)!r}",
            )

    def test_windows_path_assignment_end_to_end(self):
        # End-to-end: a wrapped-agent request of the shape the file_creator
        # LLM actually emits must surface the Windows path unchanged, so
        # the downstream yaml.safe_dump -> child-process re-load roundtrip
        # cannot reintroduce the bell-character mangling.
        request = (
            r"filepath='C:\Development\AngysBackInCUDA\angys_knapsack.cuh' "
            r"and content='#pragma once"
            "\n"
            r"// AngysBackInCUDA"
            "'"
        )
        parsed, err = self._parse_assignments(request)
        self.assertIsNone(err, f"parse error: {err}")
        values = {a['requested_key']: a['value'] for a in parsed['assignments']}
        self.assertEqual(
            values['filepath'],
            r"C:\Development\AngysBackInCUDA\angys_knapsack.cuh",
        )
        # The bell char (0x07) must never appear in the coerced path.
        self.assertNotIn('\x07', values['filepath'])
        self.assertNotIn('\x08', values['filepath'])
        self.assertNotIn('\t', values['filepath'])

    def test_every_registry_example_resolves_against_its_template(self):
        """Regression guard: every wrapped chat agent's ``example_request``
        must be accepted by ``_apply_requested_assignments_to_config``
        against the corresponding template's ``config.yaml`` — i.e. every
        key the example emits must resolve to a real path in the template
        (the runtime uses normalized-identifier matching, so ``filepath``
        correctly maps to ``file_path``, ``smtp.host`` to ``smtp_host``,
        etc.). When this fails, the LLM faithfully copies the broken
        example, the parser rejects with ``Parameter 'X' was not found
        in the target agent config.``, and Multi-Turn burns an iteration
        + leaves a failed pool directory. Four live incidents caught this
        on the running instance — executer, pser, and follow-ups — which
        this test now pins.

        The check invokes the SAME resolver used at runtime, so this
        test cannot false-positive when the resolver legitimately
        normalizes a key (e.g. ``filepath`` ↔ ``file_path``).
        """
        import os
        import yaml
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        from agent.tools import _apply_requested_assignments_to_config

        repo_agents_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'agents')
        )

        failures = []
        for spec in WRAPPED_CHAT_AGENT_SPECS:
            template_yaml = os.path.join(
                repo_agents_root, spec.template_dir, 'config.yaml'
            )
            if not os.path.isfile(template_yaml):
                continue
            with open(template_yaml, 'r', encoding='utf-8') as fh:
                template_cfg = yaml.safe_load(fh) or {}
            if not isinstance(template_cfg, dict):
                continue

            _, err, _ = _apply_requested_assignments_to_config(
                template_cfg, spec.example_request
            )
            if err:
                failures.append(f"[{spec.key}] {err}\n    example = {spec.example_request!r}")

        self.assertEqual(
            failures, [],
            "Registry ↔ template drift (fix by renaming either the "
            "example_request key or the template YAML key):\n  "
            + "\n  ".join(failures),
        )

    def test_supported_quote_escapes_still_decode(self):
        # The helper intentionally decodes ONLY the two escapes that are
        # ambiguous without decoding: ``\\`` (literal backslash) and
        # ``\<outer-quote>`` (embedded matching quote). ``\n``/``\r``/``\t``
        # stay verbatim so Windows paths survive; scripts that actually
        # need those escapes use the triple-quoted branch.
        self.assertEqual(self._coerce_value(r"'he said \'hi\''"), "he said 'hi'")
        self.assertEqual(self._coerce_value(r'"quote: \""'), 'quote: "')
        self.assertEqual(self._coerce_value(r"'two\\slashes'"), r"two\slashes")
        # Verbatim backslash escapes survive (they are what paths need).
        self.assertEqual(self._coerce_value(r"'line1\nline2'"), r"line1\nline2")
        self.assertEqual(self._coerce_value(r"'a\tb'"), r"a\tb")
        # A non-matching inner quote needs no escape and does not get one.
        self.assertEqual(self._coerce_value("'he said \"hi\"'"), 'he said "hi"')


class UnifiedChainTransientRetryTests(TestCase):
    """Regression coverage for the 502 / forcibly-closed retry helper.

    Before the fix, a transient ``(status code: 502)`` from the cloud
    Ollama endpoint caused the unified agent call to fall back to the
    basic-LLM path immediately — silently dropping the user's Multi-Turn
    tool-calling intent. The helper now retries bounded transient errors
    before falling back.
    """

    def setUp(self):
        from agent.rag.chains.unified import (
            _invoke_unified_agent_with_retry,
            _is_transient_agent_error,
        )
        self._invoke_with_retry = _invoke_unified_agent_with_retry
        self._is_transient = _is_transient_agent_error

    def test_classifier_recognizes_cloud_ollama_502(self):
        exc = Exception(
            'Post "https://ollama.com:443/api/chat?ts=1776988025": '
            'read tcp 10.61.253.43:61552->34.36.133.15:443: wsarecv: '
            'An existing connection was forcibly closed by the remote host. '
            '(status code: 502)'
        )
        self.assertTrue(self._is_transient(exc))

    def test_classifier_lets_non_transient_errors_pass(self):
        self.assertFalse(self._is_transient(Exception('KeyError: missing key')))
        self.assertFalse(self._is_transient(Exception('AttributeError: no attr')))

    def test_retry_recovers_after_transient_failure(self):
        call_counter = {'n': 0}

        class _FakeAgent:
            def invoke(self, payload):
                call_counter['n'] += 1
                if call_counter['n'] < 3:
                    raise Exception('read tcp: connection forcibly closed (status code: 502)')
                return {'output': 'recovered'}

        with patch('agent.rag.chains.unified.time.sleep'):
            result, exc = self._invoke_with_retry(_FakeAgent(), {})
        self.assertIsNone(exc)
        self.assertEqual(result, {'output': 'recovered'})
        self.assertEqual(call_counter['n'], 3)

    def test_non_transient_error_does_not_retry(self):
        call_counter = {'n': 0}

        class _FakeAgent:
            def invoke(self, payload):
                call_counter['n'] += 1
                raise KeyError('boom')

        with patch('agent.rag.chains.unified.time.sleep'):
            result, exc = self._invoke_with_retry(_FakeAgent(), {})
        self.assertIsNone(result)
        self.assertIsInstance(exc, KeyError)
        self.assertEqual(call_counter['n'], 1)

    def test_retry_bounded_when_transient_persists(self):
        call_counter = {'n': 0}

        class _FakeAgent:
            def invoke(self, payload):
                call_counter['n'] += 1
                raise Exception('Read timed out after 60s')

        with patch('agent.rag.chains.unified.time.sleep'):
            result, exc = self._invoke_with_retry(_FakeAgent(), {}, max_attempts=3)
        self.assertIsNone(result)
        self.assertIsNotNone(exc)
        self.assertEqual(call_counter['n'], 3)


class MultiTurnToolQuotaTests(TestCase):
    """Regression coverage for the per-tool quota in MultiTurnToolAgentExecutor.

    The consecutive-signature repetition detector doesn't catch cases where
    the LLM keeps reaching for the same hammer (e.g. chat_agent_pythonxer)
    with varying arguments — exactly the pattern that launched 10+
    pythonxer runs in a single request. The quota caps this behaviour.
    """

    def _make_executor(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        executor = MultiTurnToolAgentExecutor.__new__(MultiTurnToolAgentExecutor)
        executor.llm = object()
        executor.system_prompt = 'sys'
        executor.tools = []
        executor.tool_map = {}
        executor.max_iterations = 1
        executor.bound_llm = None
        executor._tool_calls_log = []
        executor._exec_report_enabled = False
        executor._exec_report_entries = []
        executor._tool_call_counts = {}
        executor._wrapped_agent_signatures = set()
        return executor

    def test_quota_constants_are_sane(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        # Soft warn fires before hard stop.
        self.assertLess(
            MultiTurnToolAgentExecutor._TOOL_QUOTA_SOFT_WARN,
            MultiTurnToolAgentExecutor._TOOL_QUOTA_HARD_STOP,
        )
        # Polling/listing tools must stay exempt — polling a run_id dozens
        # of times is legitimate.
        self.assertIn('chat_agent_run_status', MultiTurnToolAgentExecutor._TOOL_QUOTA_EXEMPT)
        self.assertIn('chat_agent_run_log', MultiTurnToolAgentExecutor._TOOL_QUOTA_EXEMPT)
        self.assertIn('get_current_time', MultiTurnToolAgentExecutor._TOOL_QUOTA_EXEMPT)
        # Pythonxer must have an alternative-suggestion hint wired.
        self.assertIn(
            'chat_agent_pythonxer',
            MultiTurnToolAgentExecutor._TOOL_ALTERNATIVE_HINT,
        )
        self.assertIn(
            'chat_agent_file_creator',
            MultiTurnToolAgentExecutor._TOOL_ALTERNATIVE_HINT['chat_agent_pythonxer'],
        )


# ──────────────────────────────────────────────────────────────────────
#  ACPX + SKILLS — automated test suite (Django-integrated)
# ──────────────────────────────────────────────────────────────────────
# (`_acpx_tempfile` and `_AcpxPath` are imported at the top of the module.)


class AcpxConfigDjangoTests(TestCase):
    def test_default_when_acpx_block_absent(self):
        from agent.acpx import load_acpx_config, PERMISSION_MODES
        cfg = load_acpx_config({})
        self.assertIn(cfg.permission_mode, PERMISSION_MODES)
        self.assertEqual(cfg.permission_mode, "approve-reads")
        self.assertEqual(cfg.non_interactive, "deny")
        self.assertFalse(cfg.plugin_tools_mcp_bridge)
        self.assertFalse(cfg.openclaw_tools_mcp_bridge)
        self.assertEqual(cfg.timeout_seconds, 120)
        self.assertEqual(cfg.mcp_servers, {})
        self.assertEqual(cfg.agents, {})

    def test_full_override_block(self):
        from agent.acpx import load_acpx_config
        cfg = load_acpx_config({"acpx": {
            "permissionMode": "deny-all",
            "nonInteractivePermissions": "fail",
            "timeoutSeconds": 45,
            "agents": {"claude": {"command": "/tmp/claude.cmd"}},
            "mcpServers": {
                "files": {"command": "python", "args": ["-m", "files"], "env": {"X": "1"}}
            },
        }})
        self.assertEqual(cfg.permission_mode, "deny-all")
        self.assertEqual(cfg.non_interactive, "fail")
        self.assertEqual(cfg.timeout_seconds, 45)
        self.assertEqual(cfg.agents["claude"], "/tmp/claude.cmd")
        self.assertEqual(cfg.mcp_servers["files"].command, "python")
        self.assertEqual(cfg.mcp_servers["files"].env, {"X": "1"})

    def test_invalid_permission_mode_falls_back_to_approve_reads(self):
        from agent.acpx import load_acpx_config
        cfg = load_acpx_config({"acpx": {"permissionMode": "yolo"}})
        self.assertEqual(cfg.permission_mode, "approve-reads")

    def test_dangerous_flag_is_only_approve_all(self):
        from agent.acpx.permissions import is_dangerous_config
        self.assertTrue(is_dangerous_config("approve-all"))
        self.assertFalse(is_dangerous_config("approve-reads"))
        self.assertFalse(is_dangerous_config("deny-all"))


class AcpxAgentRegistryDjangoTests(TestCase):
    EXPECTED = {"claude", "cursor", "codex", "copilot", "gemini", "qwen",
                "pi", "droid", "iflow", "kilocode", "kimi", "kiro", "opencode"}

    def test_default_registry_contains_all_acp_router_ids(self):
        from agent.acpx import build_agent_registry
        registry = build_agent_registry()
        for agent_id in self.EXPECTED:
            self.assertIn(agent_id, registry)

    def test_default_registry_command_is_lowercase_id_for_most_agents(self):
        from agent.acpx import DEFAULT_ACP_AGENTS
        self.assertEqual(DEFAULT_ACP_AGENTS["claude"].command, "claude")
        self.assertEqual(DEFAULT_ACP_AGENTS["qwen"].command, "qwen-code")
        self.assertEqual(DEFAULT_ACP_AGENTS["cursor"].command, "cursor-agent")

    def test_user_override_replaces_command_only(self):
        from agent.acpx import build_agent_registry, DEFAULT_ACP_AGENTS
        registry = build_agent_registry({"claude": "/usr/local/bin/claude"})
        self.assertEqual(registry["claude"].command, "/usr/local/bin/claude")
        self.assertEqual(
            registry["claude"].args, DEFAULT_ACP_AGENTS["claude"].args
        )

    def test_user_can_register_brand_new_agent_id(self):
        from agent.acpx import build_agent_registry
        registry = build_agent_registry({"my-agent": "/opt/me"})
        self.assertIn("my-agent", registry)
        self.assertEqual(registry["my-agent"].command, "/opt/me")


class AcpxPermissionGateDjangoTests(TestCase):
    def test_deny_all_blocks_every_kind(self):
        from agent.acpx.permissions import Action, PermissionGate
        gate = PermissionGate("deny-all")
        for kind in ("fs.read", "fs.write", "shell", "net", "db", "tool"):
            self.assertFalse(
                gate.decide(Action(kind, {}), interactive=True).allowed,
                f"{kind} should be denied",
            )

    def test_approve_all_allows_every_kind(self):
        from agent.acpx.permissions import Action, PermissionGate
        gate = PermissionGate("approve-all")
        for kind in ("fs.read", "fs.write", "shell", "net", "db", "tool"):
            self.assertTrue(
                gate.decide(Action(kind, {}), interactive=False).allowed
            )

    def test_approve_reads_allows_reads_only_when_non_interactive(self):
        from agent.acpx.permissions import Action, PermissionGate
        gate = PermissionGate("approve-reads", "deny")
        self.assertTrue(gate.decide(Action("fs.read", {}), False).allowed)
        write_decision = gate.decide(Action("fs.write", {}), False)
        self.assertFalse(write_decision.allowed)

    def test_approve_reads_prompts_when_interactive(self):
        from agent.acpx.permissions import Action, PermissionGate
        gate = PermissionGate("approve-reads", "deny")
        d = gate.decide(Action("fs.write", {}), interactive=True)
        self.assertTrue(d.allowed)
        self.assertTrue(d.needs_prompt)

    def test_non_interactive_fail_emits_failure_reason(self):
        from agent.acpx.permissions import Action, PermissionGate
        gate = PermissionGate("approve-reads", "fail")
        d = gate.decide(Action("shell", {}), interactive=False)
        self.assertFalse(d.allowed)
        self.assertIn("fail", d.reason)


class AcpxSessionStoreDjangoTests(TestCase):
    def test_round_trip_persists_record(self):
        from agent.acpx import FileSessionStore, AcpSessionRecord
        from agent.acpx.session_store import make_session_id, now_epoch
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            sid = make_session_id()
            rec = AcpSessionRecord(
                session_id=sid, name="t", agent_id="claude",
                cwd=tmp, state_path=str(_AcpxPath(tmp) / f"{sid}.json"),
                transcript_path=str(_AcpxPath(tmp) / f"{sid}.t.ndjson"),
                pid=None, created_at=now_epoch(), last_active_at=now_epoch(),
            )
            store.save(rec)
            loaded = store.load(sid)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.agent_id, "claude")

    def test_mark_fresh_blocks_one_load_then_clears_after_save(self):
        from agent.acpx import FileSessionStore, AcpSessionRecord
        from agent.acpx.session_store import make_session_id, now_epoch
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            sid = make_session_id()
            rec = AcpSessionRecord(
                session_id=sid, name="t", agent_id="cursor",
                cwd=tmp, state_path="", transcript_path="", pid=None,
                created_at=now_epoch(), last_active_at=now_epoch(),
            )
            store.save(rec)
            store.mark_fresh(sid)
            self.assertIsNone(store.load(sid))
            store.save(rec)
            self.assertIsNotNone(store.load(sid))

    def test_list_all_enumerates_every_record(self):
        from agent.acpx import FileSessionStore, AcpSessionRecord
        from agent.acpx.session_store import make_session_id, now_epoch
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            for _ in range(4):
                store.save(AcpSessionRecord(
                    session_id=make_session_id(), name="x",
                    agent_id="qwen", cwd=tmp,
                    state_path="", transcript_path="", pid=None,
                    created_at=now_epoch(), last_active_at=now_epoch(),
                ))
            self.assertEqual(len(store.list_all()), 4)

    def test_session_id_sanitization_blocks_path_traversal(self):
        from agent.acpx import FileSessionStore
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            store = FileSessionStore(tmp)
            self.assertIsNone(store.load(""))
            # _path_for sanitizes traversal chars; the resolved path must
            # stay inside the state_dir, never escape via "../".
            unsafe = store._path_for("../../etc/passwd")
            self.assertEqual(unsafe.parent, _AcpxPath(tmp))
            self.assertNotIn("..", str(unsafe))
            # An entirely-invalid id (only sanitizable chars) must raise.
            with self.assertRaises(ValueError):
                store._path_for("///")


class AcpxRuntimeUnitDjangoTests(TestCase):
    def test_get_runtime_returns_singleton(self):
        from agent.acpx import get_acpx_runtime
        a = get_acpx_runtime()
        b = get_acpx_runtime()
        self.assertIs(a, b)

    def test_list_agents_includes_default_registry_with_resolvable_field(self):
        from agent.acpx import get_acpx_runtime
        rt = get_acpx_runtime()
        listing = rt.list_agents()
        self.assertGreaterEqual(len(listing), 13)
        for entry in listing:
            self.assertIn("agent_id", entry)
            self.assertIn("command", entry)
            self.assertIn("description", entry)
            self.assertIn("resolvable", entry)
            self.assertIsInstance(entry["resolvable"], bool)

    def test_spawn_denied_when_permission_mode_is_deny_all(self):
        from agent.acpx import AcpxRuntime, AcpxConfig, AcpRuntimeError
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            cfg = AcpxConfig(cwd=tmp, state_dir=tmp,
                             permission_mode="deny-all")
            rt = AcpxRuntime(config=cfg)
            with self.assertRaises(AcpRuntimeError) as cm:
                rt.spawn(agent_id="claude", task="hi")
            self.assertEqual(cm.exception.code, "PERMISSION_DENIED")

    def test_spawn_unknown_agent_raises(self):
        from agent.acpx import AcpxRuntime, AcpxConfig, AcpRuntimeError
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            cfg = AcpxConfig(cwd=tmp, state_dir=tmp)
            rt = AcpxRuntime(config=cfg)
            with self.assertRaises(AcpRuntimeError) as cm:
                rt.spawn(agent_id="not-a-real-agent", task="hi")
            self.assertEqual(cm.exception.code, "UNKNOWN_AGENT")

    def test_doctor_returns_a_dict_even_without_a_probe_being_called(self):
        from agent.acpx import AcpxRuntime, AcpxConfig
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            cfg = AcpxConfig(cwd=tmp, state_dir=tmp)
            rt = AcpxRuntime(config=cfg)
            report = rt.doctor()
            self.assertIsInstance(report, dict)
            self.assertIn("ok", report)
            self.assertIn("message", report)


class AcpxToolEnvelopeTests(TestCase):
    def test_list_acp_agents_returns_ok_envelope(self):
        from agent.acpx import list_acp_agents
        out = json.loads(list_acp_agents.invoke({}))
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["agents"], list)
        self.assertGreaterEqual(len(out["agents"]), 13)

    def test_list_skills_returns_ok_envelope(self):
        from agent.acpx import list_skills
        out = json.loads(list_skills.invoke({"filter_keywords": ""}))
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["skills"], list)
        self.assertGreaterEqual(len(out["skills"]), 1)

    def test_invoke_skill_with_unknown_name_returns_failure_envelope(self):
        from agent.acpx import invoke_skill
        out = json.loads(invoke_skill.invoke({
            "skill_name": "no-such-skill", "args_json": "{}"
        }))
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], "UNKNOWN_SKILL")

    def test_invoke_skill_with_bad_json_returns_failure_envelope(self):
        from agent.acpx import invoke_skill
        out = json.loads(invoke_skill.invoke({
            "skill_name": "hello-world", "args_json": "{not json"
        }))
        self.assertFalse(out["ok"])
        self.assertEqual(out["code"], "BAD_JSON")

    def test_acp_doctor_returns_status_dict(self):
        from agent.acpx import acp_doctor
        out = json.loads(acp_doctor.invoke({}))
        self.assertIn("ok", out)
        self.assertIn("message", out)


class SkillRegistryDjangoTests(TestCase):
    EXPECTED_NAMES = {
        "hello-world", "skill-creator", "acp-router",
        "tlamatini-new-acp-agent", "tlamatini-flow-from-objective",
        "tlamatini-flw-doctor", "tlamatini-exec-report-row-adder",
        "tlamatini-planner-trace-replay", "tlamatini-allowed-hosts-tighten",
        "tlamatini-csrf-exempt-audit", "tlamatini-static-version-bumper",
        "github", "notion", "jira", "slack", "gmail", "todoist", "trello",
        "summarize", "weather",
    }

    def test_registry_loads_all_seed_skills(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        loaded = {s.name for s in skill_registry.all()}
        for name in self.EXPECTED_NAMES:
            self.assertIn(name, loaded, f"missing skill: {name}")

    def test_registry_get_returns_none_for_unknown(self):
        from agent.skills.registry import skill_registry
        self.assertIsNone(skill_registry.get("does-not-exist"))

    def test_registry_list_filter_is_keyword_AND(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        out = skill_registry.list("notion")
        names = [s["name"] for s in out]
        self.assertIn("notion", names)
        for s in out:
            hay = (s["name"] + " " + s["description"]).lower()
            self.assertIn("notion", hay)

    def test_planner_records_have_triggers_and_preview(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        for record in skill_registry.planner_records():
            self.assertIn("triggers_keywords", record)
            self.assertIn("triggers_file_globs", record)
            self.assertIn("body_preview", record)
            self.assertLessEqual(len(record["body_preview"]), 200)


class SkillFrontmatterDjangoTests(TestCase):
    def test_minimal_skill_parses(self):
        from agent.skills.frontmatter import parse_skill_md
        fm, body = parse_skill_md("---\nname: t\ndescription: x\n---\nbody\n")
        self.assertEqual(fm.name, "t")
        self.assertEqual(fm.runtime, "in-process")
        self.assertEqual(body.strip(), "body")

    def test_runtime_acpx_without_agent_raises(self):
        from agent.skills.frontmatter import parse_skill_md, SkillParseError
        text = (
            "---\nname: t\ndescription: x\n"
            "metadata:\n  tlamatini:\n    runtime: acpx\n"
            "---\nbody\n"
        )
        with self.assertRaises(SkillParseError):
            parse_skill_md(text)

    def test_runtime_acpx_with_agent_parses(self):
        from agent.skills.frontmatter import parse_skill_md
        text = (
            "---\nname: t\ndescription: x\n"
            "metadata:\n  tlamatini:\n    runtime: acpx\n    acpx_agent: cursor\n"
            "---\nbody\n"
        )
        fm, _ = parse_skill_md(text)
        self.assertEqual(fm.runtime, "acpx")
        self.assertEqual(fm.acpx_agent, "cursor")

    def test_invalid_runtime_value_raises(self):
        from agent.skills.frontmatter import parse_skill_md, SkillParseError
        text = (
            "---\nname: t\ndescription: x\n"
            "metadata:\n  tlamatini:\n    runtime: telepathy\n"
            "---\nbody\n"
        )
        with self.assertRaises(SkillParseError):
            parse_skill_md(text)

    def test_missing_frontmatter_raises(self):
        from agent.skills.frontmatter import parse_skill_md, SkillParseError
        with self.assertRaises(SkillParseError):
            parse_skill_md("just body, no frontmatter")

    def test_invalid_yaml_raises(self):
        from agent.skills.frontmatter import parse_skill_md, SkillParseError
        with self.assertRaises(SkillParseError):
            parse_skill_md("---\nname: t\n  : bad\n---\nbody\n")


class SkillIoContractDjangoTests(TestCase):
    def test_required_input_missing_is_a_failure(self):
        from agent.skills.io_contract import validate_inputs
        v = validate_inputs([{"name": "x", "type": "string", "required": True}], {})
        self.assertFalse(v.ok)
        self.assertEqual(len(v.errors), 1)

    def test_default_applied_when_optional_input_missing(self):
        from agent.skills.io_contract import validate_inputs
        v = validate_inputs(
            [{"name": "x", "type": "string", "default": "fallback"}], {}
        )
        self.assertTrue(v.ok)
        self.assertEqual(v.coerced["x"], "fallback")

    def test_enum_validation_rejects_non_choice(self):
        from agent.skills.io_contract import validate_inputs
        decls = [{"name": "k", "type": "enum", "values": ["a", "b"], "required": True}]
        self.assertTrue(validate_inputs(decls, {"k": "a"}).ok)
        self.assertFalse(validate_inputs(decls, {"k": "z"}).ok)

    def test_array_type_rejects_non_list(self):
        from agent.skills.io_contract import validate_inputs
        decls = [{"name": "xs", "type": "array", "required": True}]
        self.assertFalse(validate_inputs(decls, {"xs": "not a list"}).ok)
        self.assertTrue(validate_inputs(decls, {"xs": [1, 2]}).ok)

    def test_string_to_number_coercion(self):
        from agent.skills.io_contract import validate_inputs
        decls = [{"name": "n", "type": "number", "required": True}]
        v = validate_inputs(decls, {"n": "3.14"})
        self.assertTrue(v.ok)
        self.assertAlmostEqual(v.coerced["n"], 3.14)

    def test_extra_keys_pass_through(self):
        from agent.skills.io_contract import validate_inputs
        v = validate_inputs([], {"opaque": {"a": 1}})
        self.assertTrue(v.ok)
        self.assertIn("opaque", v.coerced)

    def test_validate_outputs_required_missing_fails(self):
        from agent.skills.io_contract import validate_outputs
        decls = [{"name": "ans", "type": "string", "required": True}]
        self.assertFalse(validate_outputs(decls, {}).ok)
        self.assertTrue(validate_outputs(decls, {"ans": "x"}).ok)

    def test_validate_outputs_non_dict_fails(self):
        from agent.skills.io_contract import validate_outputs
        v = validate_outputs([{"name": "x", "type": "string"}], "not a dict")
        self.assertFalse(v.ok)


class SkillHarnessDjangoTests(TestCase):
    def test_invoke_hello_world_returns_ok_envelope(self):
        from agent.skills.harness import SkillHarness
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("hello-world")
        self.assertIsNotNone(skill)
        result = SkillHarness(skill).invoke({"who": "tester"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["skill"], "hello-world")
        self.assertEqual(result["runtime"], "in-process")
        self.assertIn("greeting", result["output"])
        self.assertIn("audit_id", result)
        self.assertGreater(result["iterations_used"], 0)

    def test_input_contract_violation_routes_to_failure_envelope(self):
        from agent.skills.harness import SkillHarness
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("tlamatini-allowed-hosts-tighten")
        result = SkillHarness(skill).invoke({})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "input_contract_violation")
        self.assertIn("hosts", result["detail"])

    def test_envelope_includes_permissions_block(self):
        from agent.skills.harness import SkillHarness
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("github")
        result = SkillHarness(skill).invoke({"action": "list-prs"})
        self.assertTrue(result["ok"])
        env = result["output"]["_skill_envelope"]
        self.assertIn("permissions", env)
        self.assertIn("requires_tools", env)

    def test_unknown_runtime_fails_cleanly(self):
        from agent.skills.harness import SkillHarness
        from agent.skills.registry import Skill
        skill = Skill(
            name="bogus", description="x", runtime="does-not-exist",
            acpx_agent="", requires_tools=[], requires_mcps=[],
            max_iterations=2, max_seconds=5, max_tokens=1000,
            permissions={}, inputs=[], outputs=[],
            triggers_keywords=[], triggers_file_globs=[],
            body="body", body_sha256="x",
            skill_dir=_AcpxPath("."), skill_md_path=_AcpxPath("."),
            frontmatter_json="{}", last_loaded_at=0.0,
        )
        result = SkillHarness(skill).invoke({})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "runtime_error")

    def test_budget_max_iterations_zero_raises(self):
        from agent.skills.harness import Budget, BudgetExceeded
        b = Budget(max_iterations=0, max_seconds=60, max_tokens=1000)
        with self.assertRaises(BudgetExceeded):
            b.tick_iteration()

    def test_audit_log_writes_open_and_close(self):
        from agent.skills.harness import SkillAuditLog
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            audit = SkillAuditLog(
                skill_name="t", user_id=1, base_dir=_AcpxPath(tmp)
            )
            audit.write({"event": "hello"})
            audit.close()
            files = list(_AcpxPath(tmp).rglob("*.ndjson"))
            self.assertEqual(len(files), 1)
            content = files[0].read_text(encoding="utf-8")
            self.assertIn("audit_open", content)
            self.assertIn("hello", content)
            self.assertIn("audit_close", content)


class SkillMigrationSeedTests(TestCase):
    def test_seven_acpx_tool_rows_seeded(self):
        from agent.models import Tool
        names = set(Tool.objects.values_list("toolName", flat=True))
        for expected in (
            "acpx-spawn", "acpx-send", "acpx-kill", "acpx-doctor",
            "acpx-list-agents", "acpx-invoke-skill", "acpx-list-skills",
        ):
            self.assertIn(expected, names)

    def test_acp_agent_table_exists(self):
        from agent.models import AcpAgent
        self.assertEqual(AcpAgent.objects.filter(agent_id="__nope__").count(), 0)

    def test_skill_table_exists(self):
        from agent.models import Skill as SkillRow
        self.assertEqual(SkillRow.objects.filter(name="__nope__").count(), 0)

    def test_acp_session_table_exists(self):
        from agent.models import AcpSession
        self.assertEqual(AcpSession.objects.filter(session_uuid="x").count(), 0)

    def test_skill_invocation_table_exists(self):
        from agent.models import SkillInvocation
        self.assertEqual(SkillInvocation.objects.filter(skill_name="x").count(), 0)


class AcpxToolsRegistrationTests(TestCase):
    def setUp(self):
        from agent.global_state import global_state
        for key in (
            "tool_acpx-spawn_status", "tool_acpx-send_status",
            "tool_acpx-kill_status", "tool_acpx-doctor_status",
            "tool_acpx-list-agents_status", "tool_acpx-invoke-skill_status",
            "tool_acpx-list-skills_status",
        ):
            global_state.set_state(key, "enabled")

    def test_get_mcp_tools_includes_all_seven_acpx_tools(self):
        from agent.tools import get_mcp_tools
        names = {t.name for t in get_mcp_tools()}
        for expected in (
            "acp_spawn", "acp_send", "acp_kill", "acp_doctor",
            "list_acp_agents", "invoke_skill", "list_skills",
        ):
            self.assertIn(expected, names)

    def test_get_mcp_tools_drops_a_disabled_acpx_tool(self):
        from agent.global_state import global_state
        from agent.tools import get_mcp_tools
        global_state.set_state("tool_acpx-spawn_status", "disabled")
        try:
            names = {t.name for t in get_mcp_tools()}
            self.assertNotIn("acp_spawn", names)
            for expected in (
                "acp_send", "acp_kill", "acp_doctor",
                "list_acp_agents", "invoke_skill", "list_skills",
            ):
                self.assertIn(expected, names)
        finally:
            global_state.set_state("tool_acpx-spawn_status", "enabled")


class AcpxLintCommandTests(TestCase):
    def test_lint_command_emits_json_with_all_ok(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with self.assertRaises(SystemExit) as cm:
            call_command("acpx_lint", "--json", stdout=out)
        self.assertEqual(cm.exception.code, 0)
        report = json.loads(out.getvalue().strip())
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["total"], 20)
        for row in report["rows"]:
            self.assertTrue(row["ok"], f"failing row: {row}")


class AcpxCanvasContractTests(TestCase):
    JS_PATH = _AcpxPath(__file__).resolve().parent / "static" / "agent" / "js" / "acp-canvas-core.js"
    CSS_PATH = _AcpxPath(__file__).resolve().parent / "static" / "agent" / "css" / "agentic_control_panel.css"

    def test_classmap_has_skill_and_acpx(self):
        text = self.JS_PATH.read_text(encoding="utf-8")
        self.assertIn("'skill': 'skill-agent'", text)
        self.assertIn("'acpx':  'acpx-agent'", text)

    def test_css_has_skill_agent_block(self):
        text = self.CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".canvas-item.skill-agent", text)
        self.assertIn(".canvas-item.skill-agent:hover", text)

    def test_css_has_acpx_agent_block(self):
        text = self.CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".canvas-item.acpx-agent", text)
        self.assertIn(".canvas-item.acpx-agent:hover", text)


class AcpxModelsTests(TestCase):
    def test_acpagent_round_trip(self):
        from agent.models import AcpAgent
        AcpAgent.objects.create(
            agent_id="z", command="zsh", description="d",
            enabled=True, healthy=False,
        )
        row = AcpAgent.objects.get(agent_id="z")
        self.assertEqual(row.command, "zsh")
        self.assertFalse(row.healthy)

    def test_skill_row_round_trip(self):
        from agent.models import Skill as SkillRow
        SkillRow.objects.create(
            name="x", description="d", runtime="in-process",
            frontmatter_json="{}", body_sha256="abc",
        )
        row = SkillRow.objects.get(name="x")
        self.assertEqual(row.runtime, "in-process")

    def test_acpsession_user_fk_is_nullable(self):
        from agent.models import AcpSession
        s = AcpSession.objects.create(
            session_uuid="abcd", agent_id="claude", cwd="/tmp",
        )
        self.assertIsNone(s.user)

    def test_skillinvocation_links_to_acpsession(self):
        from agent.models import AcpSession, SkillInvocation
        s = AcpSession.objects.create(session_uuid="link", agent_id="cursor")
        inv = SkillInvocation.objects.create(
            skill_name="t", args_json="{}", acp_session=s,
        )
        self.assertEqual(s.skill_invocations.count(), 1)
        self.assertEqual(inv.acp_session.agent_id, "cursor")


class AcpxRouterSkillTests(TestCase):
    def test_acp_router_inputs_cover_all_default_agents(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("acp-router")
        self.assertIsNotNone(skill)
        harness_input = next(
            (d for d in skill.inputs if d.get("name") == "harness"), None
        )
        self.assertIsNotNone(harness_input)
        self.assertEqual(harness_input["type"], "enum")
        for agent_id in (
            "claude", "cursor", "codex", "copilot", "gemini",
            "qwen", "pi", "droid", "iflow", "kilocode", "kimi", "kiro", "opencode",
        ):
            self.assertIn(agent_id, harness_input["values"])


class HelloWorldSkillTests(TestCase):
    def test_hello_world_is_in_process_runtime(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("hello-world")
        self.assertEqual(skill.runtime, "in-process")
        self.assertEqual(skill.requires_tools, [])
        self.assertEqual(skill.requires_mcps, [])

    def test_hello_world_default_who_is_world(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("hello-world")
        who = next((d for d in skill.inputs if d["name"] == "who"), None)
        self.assertIsNotNone(who)
        self.assertEqual(who.get("default"), "world")

    def test_hello_world_declares_greeting_output(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        skill = skill_registry.get("hello-world")
        names = [d["name"] for d in skill.outputs]
        self.assertIn("greeting", names)


# ──────────────────────────────────────────────────────────────────────
#  ACPX config — DEEP per-parameter coverage in both source and frozen modes
# ──────────────────────────────────────────────────────────────────────
class AcpxConfigParameterCoverageTests(TestCase):
    """
    Every single parameter in the documented `acpx` block, tested twice:
    once for its DEFAULT value (when the key is absent) and once for an
    explicit OVERRIDE through `load_acpx_config`. This is the per-key
    contract test the user asked for ("very complete tests for each
    parameter in the config").
    """

    # ── cwd ────────────────────────────────────────────────────────
    def test_cwd_default_is_process_cwd(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertTrue(cfg.cwd)  # never empty
        self.assertTrue(_AcpxPath(cfg.cwd).is_absolute() or
                        _AcpxPath(cfg.cwd).expanduser().is_absolute())

    def test_cwd_override_honored(self):
        from agent.acpx.config import load_acpx_config
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            cfg = load_acpx_config({"acpx": {"cwd": tmp}})
            self.assertEqual(cfg.cwd, tmp)

    # ── stateDir ───────────────────────────────────────────────────
    def test_state_dir_default_is_user_home_tlamatini(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertIn(".tlamatini", cfg.state_dir)
        self.assertIn("acpx-state", cfg.state_dir)

    def test_state_dir_override_creates_directory(self):
        from agent.acpx.config import load_acpx_config
        with _acpx_tempfile.TemporaryDirectory() as tmp:
            target = _AcpxPath(tmp) / "custom-state"
            cfg = load_acpx_config({"acpx": {"stateDir": str(target)}})
            self.assertEqual(cfg.state_dir, str(target))
            self.assertTrue(target.exists())

    # ── probeAgent ─────────────────────────────────────────────────
    def test_probe_agent_default_is_none(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertIsNone(cfg.probe_agent)

    def test_probe_agent_override_honored(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"probeAgent": "claude"}})
        self.assertEqual(cfg.probe_agent, "claude")

    # ── permissionMode (3-mode matrix) ──────────────────────────────
    def test_permission_mode_default_is_approve_reads(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(cfg.permission_mode, "approve-reads")

    def test_permission_mode_approve_all_accepted_but_dangerous(self):
        from agent.acpx.config import load_acpx_config
        from agent.acpx.permissions import is_dangerous_config
        cfg = load_acpx_config({"acpx": {"permissionMode": "approve-all"}})
        self.assertEqual(cfg.permission_mode, "approve-all")
        self.assertTrue(is_dangerous_config(cfg.permission_mode))

    def test_permission_mode_deny_all_accepted(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"permissionMode": "deny-all"}})
        self.assertEqual(cfg.permission_mode, "deny-all")

    def test_permission_mode_invalid_falls_back_to_default(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"permissionMode": "yolo"}})
        self.assertEqual(cfg.permission_mode, "approve-reads")

    # ── nonInteractivePermissions ──────────────────────────────────
    def test_non_interactive_default_is_deny(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(cfg.non_interactive, "deny")

    def test_non_interactive_fail_accepted(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"nonInteractivePermissions": "fail"}})
        self.assertEqual(cfg.non_interactive, "fail")

    def test_non_interactive_invalid_falls_back_to_deny(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"nonInteractivePermissions": "ignore"}})
        self.assertEqual(cfg.non_interactive, "deny")

    # ── timeoutSeconds ─────────────────────────────────────────────
    def test_timeout_default_is_120(self):
        from agent.acpx.config import load_acpx_config, DEFAULT_TIMEOUT_SECONDS
        cfg = load_acpx_config({})
        self.assertEqual(cfg.timeout_seconds, DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(cfg.timeout_seconds, 120)

    def test_timeout_override_honored(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"timeoutSeconds": 45.5}})
        self.assertEqual(cfg.timeout_seconds, 45.5)

    def test_timeout_invalid_string_falls_back(self):
        from agent.acpx.config import load_acpx_config
        # "0" is falsy → coerced to default
        cfg = load_acpx_config({"acpx": {"timeoutSeconds": 0}})
        self.assertEqual(cfg.timeout_seconds, 120)

    # ── pluginToolsMcpBridge / openClawToolsMcpBridge ──────────────
    def test_plugin_tools_bridge_default_off(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertFalse(cfg.plugin_tools_mcp_bridge)

    def test_plugin_tools_bridge_can_be_turned_on(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"pluginToolsMcpBridge": True}})
        self.assertTrue(cfg.plugin_tools_mcp_bridge)

    def test_openclaw_tools_bridge_default_off(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertFalse(cfg.openclaw_tools_mcp_bridge)

    def test_openclaw_tools_bridge_can_be_turned_on(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"openClawToolsMcpBridge": True}})
        self.assertTrue(cfg.openclaw_tools_mcp_bridge)

    # ── strictWindowsCmdWrapper (legacy compatibility flag) ─────────
    def test_strict_windows_wrapper_default_off(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertFalse(cfg.strict_windows_cmd_wrapper)

    def test_strict_windows_wrapper_accepted(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"strictWindowsCmdWrapper": True}})
        self.assertTrue(cfg.strict_windows_cmd_wrapper)

    # ── mcpServers ─────────────────────────────────────────────────
    def test_mcp_servers_default_empty(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(cfg.mcp_servers, {})

    def test_mcp_servers_full_entry_parsed(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"mcpServers": {
            "files": {"command": "python", "args": ["-m", "f"], "env": {"K": "V"}}
        }}})
        self.assertIn("files", cfg.mcp_servers)
        spec = cfg.mcp_servers["files"]
        self.assertEqual(spec.command, "python")
        self.assertEqual(spec.args, ["-m", "f"])
        self.assertEqual(spec.env, {"K": "V"})

    def test_mcp_servers_missing_command_skipped(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"mcpServers": {
            "bogus": {"args": ["only", "args"]}
        }}})
        self.assertNotIn("bogus", cfg.mcp_servers)

    def test_mcp_servers_non_dict_value_skipped(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"mcpServers": {
            "scalar": "string-not-a-dict"
        }}})
        self.assertEqual(cfg.mcp_servers, {})

    # ── agents (per-id command override) ────────────────────────────
    def test_agents_default_empty(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(cfg.agents, {})

    def test_agents_override_honored(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"agents": {
            "claude": {"command": "/usr/local/bin/claude"}
        }}})
        self.assertEqual(cfg.agents["claude"], "/usr/local/bin/claude")

    def test_agents_missing_command_skipped(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"agents": {"x": {}}}})
        self.assertNotIn("x", cfg.agents)

    def test_agents_non_dict_value_skipped(self):
        from agent.acpx.config import load_acpx_config
        cfg = load_acpx_config({"acpx": {"agents": {"x": 42}}})
        self.assertEqual(cfg.agents, {})


class AcpxConfigSourceModeTests(TestCase):
    """The on-disk source-tree config.json contains the documented `acpx` block."""

    SOURCE_CONFIG = (_AcpxPath(__file__).resolve().parent / "config.json")

    def test_source_config_json_has_acpx_block(self):
        text = self.SOURCE_CONFIG.read_text(encoding="utf-8")
        data = json.loads(text)
        self.assertIn("acpx", data)
        self.assertIsInstance(data["acpx"], dict)

    def test_source_config_acpx_documents_every_key(self):
        text = self.SOURCE_CONFIG.read_text(encoding="utf-8")
        data = json.loads(text)
        for key in (
            "cwd", "stateDir", "probeAgent", "permissionMode",
            "nonInteractivePermissions", "timeoutSeconds",
            "pluginToolsMcpBridge", "openClawToolsMcpBridge",
            "strictWindowsCmdWrapper", "mcpServers", "agents",
        ):
            self.assertIn(key, data["acpx"], f"missing acpx.{key}")

    def test_source_config_safe_defaults_in_acpx_block(self):
        data = json.loads(self.SOURCE_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(data["acpx"]["permissionMode"], "approve-reads")
        self.assertEqual(data["acpx"]["nonInteractivePermissions"], "deny")
        self.assertFalse(data["acpx"]["pluginToolsMcpBridge"])
        self.assertFalse(data["acpx"]["openClawToolsMcpBridge"])
        self.assertEqual(data["acpx"]["timeoutSeconds"], 120)
        self.assertEqual(data["acpx"]["mcpServers"], {})
        self.assertIsInstance(data["acpx"]["agents"], dict)  # populated per-user; only type checked

    def test_source_config_section_keys_present_for_documentation(self):
        data = json.loads(self.SOURCE_CONFIG.read_text(encoding="utf-8"))
        for key in ("_section_acpx", "_section_acpx_skills",
                    "_section_acpx_tools", "_acpx_doc_url"):
            self.assertIn(key, data, f"missing documentation key: {key}")

    def test_source_config_acpx_keys_have_documentation_siblings(self):
        data = json.loads(self.SOURCE_CONFIG.read_text(encoding="utf-8"))
        block = data["acpx"]
        for key in ("cwd", "stateDir", "probeAgent", "permissionMode",
                    "nonInteractivePermissions", "timeoutSeconds",
                    "pluginToolsMcpBridge", "openClawToolsMcpBridge",
                    "strictWindowsCmdWrapper", "mcpServers", "agents"):
            comment_key = f"_acpx_{key}_comment"
            self.assertIn(comment_key, block,
                          f"missing inline doc for acpx.{key}")
            self.assertGreater(len(block[comment_key]), 20)


class AcpxConfigDynamicGenerationTests(TestCase):
    """
    `ensure_acpx_block_in_config_json()` self-heals legacy config files
    that pre-date the ACPX rollout. Tests cover BOTH modes:
        - frozen (`sys.frozen=True`, executable next to config.json)
        - source (default Python module layout)
    """

    def _legacy_config(self) -> dict:
        # A typical pre-ACPX config.json snapshot. Note: NO `acpx` key.
        return {
            "_comment": "Legacy config",
            "embeding-model": "qwen3-embedding:8b",
            "chained-model": "kimi-k2.6:cloud",
            "ollama_base_url": "http://127.0.0.1:11434",
            "enable_unified_agent": True,
            "_section_misc": "Miscellaneous Settings",
            "load_hidden": True,
        }

    def _write_config(self, tmp: _AcpxPath, payload: dict) -> _AcpxPath:
        target = tmp / "config.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target

    def test_backfill_appends_acpx_block_when_absent(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            target = self._write_config(tmp, self._legacy_config())
            self.assertTrue(ensure_acpx_block_in_config_json(config_path=target))
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertIn("acpx", data)
            self.assertEqual(data["acpx"]["permissionMode"], "approve-reads")

    def test_backfill_preserves_every_existing_key_in_order(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        legacy = self._legacy_config()
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            target = self._write_config(tmp, legacy)
            ensure_acpx_block_in_config_json(config_path=target)
            data = json.loads(target.read_text(encoding="utf-8"))
            # Original keys retained in the same order at the top
            original_keys = list(legacy.keys())
            new_keys = list(data.keys())
            self.assertEqual(new_keys[:len(original_keys)], original_keys)

    def test_backfill_is_idempotent_when_acpx_already_present(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            payload = self._legacy_config()
            payload["acpx"] = {"permissionMode": "deny-all"}
            target = self._write_config(tmp, payload)
            self.assertFalse(
                ensure_acpx_block_in_config_json(config_path=target)
            )
            data = json.loads(target.read_text(encoding="utf-8"))
            # User customization preserved
            self.assertEqual(data["acpx"]["permissionMode"], "deny-all")

    def test_backfill_overwrite_replaces_existing_block(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            payload = self._legacy_config()
            payload["acpx"] = {"permissionMode": "deny-all"}
            target = self._write_config(tmp, payload)
            self.assertTrue(
                ensure_acpx_block_in_config_json(
                    config_path=target, overwrite=True
                )
            )
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["acpx"]["permissionMode"], "approve-reads")

    def test_backfill_silent_no_op_when_file_missing(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            target = _AcpxPath(raw_tmp) / "absent.json"
            self.assertFalse(
                ensure_acpx_block_in_config_json(config_path=target)
            )

    def test_backfill_silent_no_op_when_file_is_invalid_json(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            target = _AcpxPath(raw_tmp) / "config.json"
            target.write_text("not json at all", encoding="utf-8")
            self.assertFalse(
                ensure_acpx_block_in_config_json(config_path=target)
            )

    def test_backfill_silent_no_op_when_file_is_a_list(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            target = _AcpxPath(raw_tmp) / "config.json"
            target.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertFalse(
                ensure_acpx_block_in_config_json(config_path=target)
            )

    def test_backfill_writes_atomically_via_temp_file(self):
        from agent.acpx.config import ensure_acpx_block_in_config_json
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            target = self._write_config(tmp, self._legacy_config())
            ensure_acpx_block_in_config_json(config_path=target)
            # No leftover .tmp sidecar should remain after success
            siblings = [p.name for p in tmp.iterdir()]
            self.assertNotIn("config.json.tmp", siblings)

    def test_default_block_value_matches_loaded_acpxconfig(self):
        from agent.acpx.config import (
            DEFAULT_ACPX_CONFIG_BLOCK,
            load_acpx_config,
        )
        # The user-facing JSON defaults must produce the same AcpxConfig as
        # `load_acpx_config({})` — i.e. the documented defaults are *the*
        # defaults the runtime uses when the block is absent.
        cfg_from_block = load_acpx_config({"acpx": dict(DEFAULT_ACPX_CONFIG_BLOCK)})
        cfg_from_empty = load_acpx_config({})
        self.assertEqual(cfg_from_block.permission_mode, cfg_from_empty.permission_mode)
        self.assertEqual(cfg_from_block.non_interactive, cfg_from_empty.non_interactive)
        self.assertEqual(cfg_from_block.timeout_seconds, cfg_from_empty.timeout_seconds)
        self.assertEqual(cfg_from_block.plugin_tools_mcp_bridge,
                         cfg_from_empty.plugin_tools_mcp_bridge)
        self.assertEqual(cfg_from_block.openclaw_tools_mcp_bridge,
                         cfg_from_empty.openclaw_tools_mcp_bridge)
        self.assertEqual(cfg_from_block.mcp_servers, cfg_from_empty.mcp_servers)
        self.assertEqual(cfg_from_block.agents, cfg_from_empty.agents)


class AcpxConfigFrozenModePathTests(TestCase):
    """
    Frozen-mode resolution: when sys.frozen is True, find_config_json_path
    looks next to sys.executable; load_tlamatini_config_json reads from
    there; the skill registry adds <install-dir>/agent/skills_pkg/ as a
    root if it exists. These tests fake sys.frozen / sys.executable to
    exercise that branch without actually building a PyInstaller bundle.
    """

    def test_find_config_json_path_uses_executable_dir_when_frozen(self):
        from agent.acpx import config as acpx_config
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            fake_exe = tmp / "manage.exe"
            fake_exe.write_text("", encoding="utf-8")
            target_config = tmp / "config.json"
            target_config.write_text("{}", encoding="utf-8")
            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(fake_exe)):
                resolved = acpx_config.find_config_json_path()
            self.assertEqual(resolved, target_config)

    def test_load_tlamatini_config_json_in_frozen_mode_reads_install_dir(self):
        from agent.acpx import config as acpx_config
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            fake_exe = tmp / "manage.exe"
            fake_exe.write_text("", encoding="utf-8")
            payload = {
                "acpx": {
                    "permissionMode": "deny-all",
                    "timeoutSeconds": 90,
                }
            }
            (tmp / "config.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(fake_exe)):
                loaded = acpx_config.load_tlamatini_config_json()
            self.assertEqual(loaded["acpx"]["permissionMode"], "deny-all")
            self.assertEqual(loaded["acpx"]["timeoutSeconds"], 90)

    def test_skill_registry_picks_up_install_dir_skills_pkg_in_frozen_mode(self):
        # Drop a single SKILL.md into a fake install dir and verify the
        # registry picks it up as an extra root in frozen mode.
        from agent.skills.registry import SkillRegistry
        with _acpx_tempfile.TemporaryDirectory() as raw_tmp:
            tmp = _AcpxPath(raw_tmp)
            fake_exe = tmp / "manage.exe"
            fake_exe.write_text("", encoding="utf-8")
            skills_root = tmp / "agent" / "skills_pkg" / "frozen_only"
            skills_root.mkdir(parents=True)
            (skills_root / "SKILL.md").write_text(
                "---\nname: frozen-only\ndescription: marker\n---\nbody\n",
                encoding="utf-8",
            )
            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(fake_exe)):
                registry = SkillRegistry()
                registry.reload()
            self.assertIn("frozen-only", {s.name for s in registry.all()})


class AcpxConfigBuildPipelineTests(TestCase):
    """The PyInstaller / install-time pipeline bundles config.json + skills."""

    BUILD_PY = (_AcpxPath(__file__).resolve().parents[2] / "build.py")

    def test_build_py_bundles_skills_pkg_via_add_data(self):
        text = self.BUILD_PY.read_text(encoding="utf-8")
        # The PyInstaller --add-data line for skills_pkg into the bundle
        self.assertIn("Tlamatini/agent/skills_pkg", text)
        self.assertIn("agent/skills_pkg", text)

    def test_build_py_post_build_copies_skills_pkg_next_to_exe(self):
        text = self.BUILD_PY.read_text(encoding="utf-8")
        # The post-build copy that places skills_pkg into <install-dir>/agent/
        self.assertIn('"skills_pkg"', text)

    def test_build_py_bundles_config_json(self):
        text = self.BUILD_PY.read_text(encoding="utf-8")
        self.assertIn("Tlamatini/agent/config.json", text)


class AcpxConfigDocumentedDefaultsConsistencyTests(TestCase):
    """
    The documented DEFAULT_ACPX_CONFIG_BLOCK in agent/acpx/config.py is the
    SAME default vector that load_acpx_config({}) yields. If they ever
    diverge, users editing config.json would see a different runtime
    behavior than the documentation claims.
    """

    def test_default_block_permission_mode_matches_runtime_default(self):
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        self.assertEqual(
            DEFAULT_ACPX_CONFIG_BLOCK["permissionMode"],
            load_acpx_config({}).permission_mode,
        )

    def test_default_block_non_interactive_matches_runtime_default(self):
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        self.assertEqual(
            DEFAULT_ACPX_CONFIG_BLOCK["nonInteractivePermissions"],
            load_acpx_config({}).non_interactive,
        )

    def test_default_block_timeout_matches_runtime_default(self):
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        self.assertEqual(
            DEFAULT_ACPX_CONFIG_BLOCK["timeoutSeconds"],
            load_acpx_config({}).timeout_seconds,
        )

    def test_default_block_bridges_match_runtime_default(self):
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(
            DEFAULT_ACPX_CONFIG_BLOCK["pluginToolsMcpBridge"],
            cfg.plugin_tools_mcp_bridge,
        )
        self.assertEqual(
            DEFAULT_ACPX_CONFIG_BLOCK["openClawToolsMcpBridge"],
            cfg.openclaw_tools_mcp_bridge,
        )

    def test_default_block_servers_and_agents_match_runtime_default(self):
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        cfg = load_acpx_config({})
        self.assertEqual(DEFAULT_ACPX_CONFIG_BLOCK["mcpServers"], cfg.mcp_servers)
        self.assertEqual(DEFAULT_ACPX_CONFIG_BLOCK["agents"], cfg.agents)

    def test_default_block_keys_match_documented_keys(self):
        # Every parameter the user sees in the JSON must appear in the
        # AcpxConfig dataclass via load_acpx_config (otherwise it's a
        # dead documented key).
        from agent.acpx.config import DEFAULT_ACPX_CONFIG_BLOCK, load_acpx_config
        load_acpx_config({"acpx": dict(DEFAULT_ACPX_CONFIG_BLOCK)})
        for key in (
            "cwd", "stateDir", "probeAgent", "permissionMode",
            "nonInteractivePermissions", "timeoutSeconds",
            "pluginToolsMcpBridge", "openClawToolsMcpBridge",
            "strictWindowsCmdWrapper", "mcpServers", "agents",
        ):
            self.assertIn(key, DEFAULT_ACPX_CONFIG_BLOCK,
                          f"DEFAULT_ACPX_CONFIG_BLOCK missing {key}")


# ============================================================
# CHAT RUNTIME ASKER / NOTIFIER GUI BRIDGE TESTS
# ============================================================
# These tests pin the contract that lets the chat page (agent_page.html)
# show the same Asker A/B dialog and Notifier toast that ACP shows, but
# for agents launched inside _chat_runs_/ via Multi-Turn.

class ChatRuntimeStatusViewTests(TestCase):
    """End-to-end coverage of /agent/check_chat_runtimes_status/."""

    def setUp(self):
        self.user = User.objects.create_user(username='chatrun', password='secret123')
        self.client.force_login(self.user)
        # Point the chat-runtime root at a temp directory we control. The
        # view resolves _get_chat_runtime_root_path() at call time, so the
        # patch only needs to cover the request.
        self._tmp = tempfile.mkdtemp(prefix='chat_runtime_test_')

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_runtime(self, name, *, status=None, notification=None, pid=None):
        runtime_dir = os.path.join(self._tmp, name)
        os.makedirs(runtime_dir, exist_ok=True)
        if status is not None:
            with open(os.path.join(runtime_dir, 'agent.status'), 'w') as f:
                f.write(status)
        if notification is not None:
            with open(os.path.join(runtime_dir, 'notification.json'), 'w', encoding='utf-8') as f:
                json.dump(notification, f)
        if pid is not None:
            with open(os.path.join(runtime_dir, 'agent.pid'), 'w') as f:
                f.write(str(pid))
        return runtime_dir

    def test_asker_waiting_status_is_surfaced(self):
        self._make_runtime('asker_001_a1b2c3d4', status='waiting_for_user_input')
        with patch('agent.views._get_chat_runtime_root_path', return_value=self._tmp):
            response = self.client.get(reverse('check_chat_runtimes_status'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('asker_001_a1b2c3d4', data['runtimes'])
        self.assertEqual(data['runtimes']['asker_001_a1b2c3d4']['status'], 'waiting_for_user_input')

    def test_notifier_payload_is_surfaced_and_then_consumed(self):
        notif_payload = {
            'type': 'notifier_alert',
            'matches': ['BUILD DONE'],
            'source_agent': 'notifier_002_aaaa1111',
            'sound_enabled': True,
            'outcome_detail': 'Build finished',
            'timestamp': 12345.0,
        }
        runtime_dir = self._make_runtime('notifier_002_aaaa1111', notification=notif_payload)
        with patch('agent.views._get_chat_runtime_root_path', return_value=self._tmp):
            first = self.client.get(reverse('check_chat_runtimes_status'))
            self.assertEqual(first.status_code, 200)
            first_data = json.loads(first.content)
            self.assertIn('notifier_002_aaaa1111', first_data['runtimes'])
            self.assertEqual(
                first_data['runtimes']['notifier_002_aaaa1111']['notification']['matches'],
                ['BUILD DONE'],
            )
            # Second poll: notification.json must have been removed so we
            # don't re-fire the toast on every tick.
            self.assertFalse(
                os.path.exists(os.path.join(runtime_dir, 'notification.json')),
                'notification.json must be deleted after the first read',
            )
            second = self.client.get(reverse('check_chat_runtimes_status'))
            second_data = json.loads(second.content)
            self.assertNotIn('notifier_002_aaaa1111', second_data['runtimes'])

    def test_pool_poller_still_ignores_chat_runs_root(self):
        # Sanity guard: the existing ACP poller (check_all_agents_status_view)
        # explicitly skips the chat-runtime root by name. If somebody removes
        # that guard, both pollers would render duplicated dialogs.
        from agent.chat_agent_runtime import CHAT_RUNTIME_ROOT_NAME
        with open(os.path.join(
            os.path.dirname(views.__file__), 'views.py'
        ), 'r', encoding='utf-8') as f:
            views_src = f.read()
        self.assertIn(
            "folder_name == CHAT_RUNTIME_ROOT_NAME",
            views_src,
            "ACP pool poller must continue to skip the chat-runtime root",
        )
        # And CHAT_RUNTIME_ROOT_NAME itself must keep its expected value.
        self.assertEqual(CHAT_RUNTIME_ROOT_NAME, '_chat_runs_')


class ChatRuntimeNameValidationTests(TestCase):
    """Path-traversal guard on chat-runtime names."""

    def test_valid_names_accepted(self):
        from agent.views import _is_valid_chat_runtime_name
        self.assertTrue(_is_valid_chat_runtime_name('asker_001_a1b2c3d4'))
        self.assertTrue(_is_valid_chat_runtime_name('notifier_002_abc12345'))

    def test_traversal_attempts_rejected(self):
        from agent.views import _is_valid_chat_runtime_name
        bad = [
            '..',
            '../etc/passwd',
            'asker/../../etc',
            'asker_001_../',
            'asker\\..\\etc',
            'asker_001_a1b2c3d4/extra',
            '',
            'no_seq_or_hash',
        ]
        for name in bad:
            self.assertFalse(
                _is_valid_chat_runtime_name(name),
                f"name should be rejected: {name!r}",
            )

    def test_resolve_returns_none_for_missing_dir(self):
        from agent.views import _resolve_chat_runtime_dir
        self.assertIsNone(_resolve_chat_runtime_dir('asker_999_deadbeef'))

    def test_resolve_returns_none_for_traversal(self):
        from agent.views import _resolve_chat_runtime_dir
        self.assertIsNone(_resolve_chat_runtime_dir('../etc/passwd'))


class AskerChoiceChatRuntimeTests(TestCase):
    """asker_choice_view must accept chat-runtime names and write
    choice.txt under _chat_runs_/, with a path-traversal guard."""

    def setUp(self):
        self.user = User.objects.create_user(username='askchat', password='secret123')
        self.client.force_login(self.user)
        self._tmp = tempfile.mkdtemp(prefix='asker_choice_chat_test_')

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_choice_written_into_chat_runtime_dir(self):
        runtime_name = 'asker_001_a1b2c3d4'
        runtime_dir = os.path.join(self._tmp, runtime_name)
        os.makedirs(runtime_dir)
        csrf_client = Client(enforce_csrf_checks=False)
        csrf_client.force_login(self.user)
        with patch('agent.views._get_chat_runtime_root_path', return_value=self._tmp):
            response = csrf_client.post(
                reverse('asker_choice', args=[runtime_name]),
                data=json.dumps({'choice': 'A'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        choice_path = os.path.join(runtime_dir, 'choice.txt')
        self.assertTrue(os.path.exists(choice_path))
        with open(choice_path, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read().strip(), 'A')

    def test_traversal_payload_is_rejected(self):
        # The URL pattern uses [^/]+ so paths containing `/` never reach the
        # view (they 404 at the URL resolver). What the view itself must
        # reject is a name that *passes* the URL filter but still tries to
        # escape the chat-runtime root, e.g. an `asker..weird` name. That
        # falls through to the canvas-id branch, which now explicitly
        # rejects names containing `..`.
        csrf_client = Client(enforce_csrf_checks=False)
        csrf_client.force_login(self.user)
        # Have to construct the URL by hand because Django's reverse()
        # rejects `..` as a path arg. The route accepts [^/]+ so this URL
        # string reaches the view.
        traversal_name = 'asker..%2E%2E_evil'
        with patch('agent.views._get_chat_runtime_root_path', return_value=self._tmp):
            response = csrf_client.post(
                f'/agent/asker_choice/{traversal_name}/',
                data=json.dumps({'choice': 'A'}),
                content_type='application/json',
                HTTP_X_AGENT_SESSION_ID='trav',
            )
        # Either 400 (rejected by view) or 404 (canvas pool dir missing) is
        # acceptable; what matters is that NO file landed under self._tmp.
        self.assertIn(response.status_code, (400, 404))
        # And no file was written anywhere inside the chat-runtime tmp.
        for root, _dirs, files in os.walk(self._tmp):
            for fname in files:
                self.assertNotEqual(
                    fname, 'choice.txt',
                    f"choice.txt unexpectedly written under {root}",
                )

    def test_invalid_choice_returns_400(self):
        csrf_client = Client(enforce_csrf_checks=False)
        csrf_client.force_login(self.user)
        runtime_name = 'asker_001_a1b2c3d4'
        os.makedirs(os.path.join(self._tmp, runtime_name))
        with patch('agent.views._get_chat_runtime_root_path', return_value=self._tmp):
            response = csrf_client.post(
                reverse('asker_choice', args=[runtime_name]),
                data=json.dumps({'choice': 'C'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)


class ChatAgentAskerSpecTests(TestCase):
    """The new chat_agent_asker spec must be present and parseable by
    the same machinery the rest of the registry uses."""

    def test_chat_agent_asker_is_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.assertIn('chat_agent_asker', WRAPPED_CHAT_AGENT_BY_TOOL_NAME)
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_asker']
        self.assertEqual(spec.template_dir, 'asker')
        self.assertEqual(spec.display_name, 'Asker')

    def test_asker_example_request_parses_against_template(self):
        # Same contract the existing
        # test_every_registry_example_resolves_against_its_template enforces:
        # every key in the example_request must resolve against the actual
        # asker/config.yaml.
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        from agent.tools import _apply_requested_assignments_to_config

        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_asker']
        template_yaml = os.path.join(
            os.path.dirname(__file__), 'agents', spec.template_dir, 'config.yaml'
        )
        with open(template_yaml, 'r', encoding='utf-8') as fh:
            template_cfg = yaml.safe_load(fh) or {}
        _, err, _ = _apply_requested_assignments_to_config(
            template_cfg, spec.example_request
        )
        self.assertIsNone(err, f"Asker example_request did not resolve: {err}")


class NotifierOneshotModeTests(TestCase):
    """Drive notifier.tool_node directly with mode='oneshot' and assert
    that a notification.json is written and the function exits cleanly."""

    def test_oneshot_writes_notification_and_exits(self):
        notifier_dir = os.path.join(
            os.path.dirname(__file__), 'agents', 'notifier'
        )
        # Load notifier.py as a fresh module so we can monkey-patch its
        # CONFIG, CURRENT_DIR_NAME, NOTIFICATION_FILE, and time.sleep.
        spec = importlib.util.spec_from_file_location(
            'notifier_under_test',
            os.path.join(notifier_dir, 'notifier.py'),
        )
        module = importlib.util.module_from_spec(spec)
        # The module's top-level code calls load_config() and chdir()s
        # into its own folder; that's fine because notifier/config.yaml
        # is committed and harmless.
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            self.fail("notifier module raised SystemExit at import")

        with tempfile.TemporaryDirectory() as tmp:
            notif_path = os.path.join(tmp, 'notification.json')
            with patch.object(module, 'NOTIFICATION_FILE', notif_path), \
                 patch.object(module, 'CONFIG', {
                     'target': {
                         'mode': 'oneshot',
                         'search_strings': 'BUILD DONE',
                         'outcome_detail': 'Build finished successfully',
                         'sound_enabled': True,
                     },
                     'source_agents': [],
                     'target_agents': [],
                 }), \
                 patch.object(module.time, 'sleep', return_value=None), \
                 patch.object(module, 'remove_pid_file', return_value=None):
                with self.assertRaises(SystemExit) as cm:
                    module.tool_node({'messages': [], 'loop_count': 0, 'offsets': {}})
                self.assertEqual(cm.exception.code, 0)
                self.assertTrue(os.path.exists(notif_path))
                with open(notif_path, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
                self.assertEqual(payload['type'], 'notifier_alert')
                self.assertIn('BUILD DONE', payload['matches'])
                self.assertTrue(payload['sound_enabled'])
                self.assertEqual(payload['outcome_detail'], 'Build finished successfully')


class DiagramRenderingTests(TestCase):
    """The chat container renders bot messages in a proportional font, so ASCII /
    box-drawing diagrams emitted by the LLM lose their column alignment unless
    they are wrapped in a fixed-width <pre> block. The pipeline supports two
    surfaces: explicit BEGIN-DIAGRAM / END-DIAGRAM blocks (rule 13 in
    prompt.pmt) and an auto-detection safety net for older messages and
    uncooperative outputs. These tests pin both."""

    def _wrap(self, text):
        from agent.services.response_parser import _wrap_diagram_blocks
        return _wrap_diagram_blocks(text)

    def _process(self, raw):
        """Drive the full process_llm_response pipeline against a raw LLM
        answer, return the persisted bot-message text. Patches the answer
        analyzer + Channel layer so the test stays focused on rendering."""
        from agent.services.response_parser import process_llm_response

        async def _analyzer(_text):
            return True

        with patch(
            'agent.services.response_parser.analyze_answer_success',
            side_effect=_analyzer,
        ):
            return async_to_sync(process_llm_response)(
                raw,
                None,
                None,
                None,
                conversation_user=None,
                tool_calls_log=None,
                multi_turn_used=False,
                exec_report_enabled=False,
                exec_report_entries=None,
            )

    def test_explicit_begin_diagram_block_is_wrapped_in_pre_ascii_diagram(self):
        text = (
            "Here is the architecture:\n"
            "BEGIN-DIAGRAM\n"
            "+----------+      +----------+\n"
            "|  Client  | ---> |  Server  |\n"
            "+----------+      +----------+\n"
            "END-DIAGRAM\n"
            "Hope that helps."
        )
        wrapped, placeholders = self._wrap(text)
        self.assertEqual(len(placeholders), 1)
        self.assertIn('class="ascii-diagram"', placeholders[0])
        # Box-drawing chars must be HTML-escaped or copied verbatim — but the
        # `|`, `+`, `-` we put in are safe; what we DO need is the literal
        # diagram preserved and NOT touched by later regex passes.
        self.assertIn('|  Client  | ---&gt; |  Server  |', placeholders[0])
        # Surrounding prose remains. Wrappers themselves are gone.
        self.assertIn('Here is the architecture:', wrapped)
        self.assertNotIn('BEGIN-DIAGRAM', wrapped)
        self.assertNotIn('END-DIAGRAM', wrapped)
        self.assertIn('\x00DGRM_0\x00', wrapped)

    def test_unicode_box_drawing_block_is_auto_detected_without_wrappers(self):
        # The LLM forgot the BEGIN-DIAGRAM wrappers. Auto-detection must
        # still wrap the run because of the U+2500..U+257F characters.
        text = (
            "Auto-detect this:\n"
            "┌──────────┐      ┌──────────┐\n"
            "│  Client  │ ───▶ │  Server  │\n"
            "└──────────┘      └──────────┘\n"
            "Done."
        )
        wrapped, placeholders = self._wrap(text)
        self.assertEqual(len(placeholders), 1)
        self.assertIn('class="ascii-diagram"', placeholders[0])
        # The Unicode box-drawing chars must round-trip into the placeholder
        # (HTML-escaped output preserves them — they're not <, >, &, " or ').
        self.assertIn('┌──────────┐', placeholders[0])
        self.assertIn('│  Client  │', placeholders[0])
        # Adjacent prose is untouched.
        self.assertIn('Auto-detect this:', wrapped)
        self.assertIn('Done.', wrapped)

    def test_single_diagram_line_is_not_auto_wrapped(self):
        # A single line with `---` should NOT be promoted to a diagram block;
        # the auto-detector requires at least 2 consecutive diagram-like lines
        # to avoid wrapping innocuous separators in prose.
        text = "First paragraph.\n---\nSecond paragraph."
        wrapped, placeholders = self._wrap(text)
        self.assertEqual(placeholders, [])
        self.assertEqual(wrapped, text)

    def test_inline_code_inside_diagram_is_not_substituted(self):
        # The bold and inline-code substitutions in process_llm_response would
        # otherwise turn `**foo**` -> <strong>foo</strong> and `` `bar` `` ->
        # <code>bar</code> even when those characters appear inside the
        # diagram. The placeholder mechanism must protect them.
        raw = (
            "Setup:\n"
            "BEGIN-DIAGRAM\n"
            "| **bold-looking** | `code-looking` |\n"
            "+------------------+----------------+\n"
            "END-DIAGRAM\n"
            "END-RESPONSE"
        )
        final = self._process(raw)
        self.assertIn('class="ascii-diagram"', final)
        # Bold/code regex MUST NOT have fired inside the diagram.
        self.assertNotIn('<strong>bold-looking</strong>', final)
        self.assertNotIn('<code>code-looking</code>', final)
        # The diagram body, HTML-escaped, must round-trip.
        self.assertIn('| **bold-looking** | `code-looking` |', final)

    def test_lowercase_begin_diagram_wrappers_also_match(self):
        # Mirror the BEGIN-CODE/begin-code lenience.
        text = (
            "begin-diagram\n"
            "A --> B\n"
            "B --> C\n"
            "end-diagram"
        )
        wrapped, placeholders = self._wrap(text)
        self.assertEqual(len(placeholders), 1)
        self.assertIn('A --&gt; B', placeholders[0])

    def test_multiple_diagrams_get_distinct_placeholders(self):
        text = (
            "First:\n"
            "BEGIN-DIAGRAM\n"
            "A --> B\n"
            "B --> C\n"
            "END-DIAGRAM\n"
            "Second:\n"
            "BEGIN-DIAGRAM\n"
            "X --> Y\n"
            "Y --> Z\n"
            "END-DIAGRAM"
        )
        wrapped, placeholders = self._wrap(text)
        self.assertEqual(len(placeholders), 2)
        self.assertIn('\x00DGRM_0\x00', wrapped)
        self.assertIn('\x00DGRM_1\x00', wrapped)
        self.assertIn('A --&gt; B', placeholders[0])
        self.assertIn('X --&gt; Y', placeholders[1])

    def test_full_pipeline_renders_diagram_after_all_substitutions(self):
        raw = (
            "Diagram time:\n"
            "BEGIN-DIAGRAM\n"
            "[Client] -> [Server]\n"
            "[Server] -> [DB]\n"
            "END-DIAGRAM\n"
            "Notes: **important**\n"
            "END-RESPONSE"
        )
        final = self._process(raw)
        # Diagram is wrapped.
        self.assertIn('<pre class="ascii-diagram">', final)
        self.assertIn('[Client] -&gt; [Server]', final)
        # Bold OUTSIDE the diagram still runs.
        self.assertIn('<strong>important</strong>', final)
        # END-RESPONSE has been collapsed to <br>.
        self.assertNotIn('END-RESPONSE', final)
        # Wrappers are no longer in the rendered HTML.
        self.assertNotIn('BEGIN-DIAGRAM', final)
        self.assertNotIn('END-DIAGRAM', final)

    def test_prose_with_arrows_but_only_one_line_is_left_alone(self):
        # A single line containing an arrow glyph is NOT a diagram. Two or
        # more consecutive lines ARE.
        single = "We use ▲ for upward."
        wrapped, placeholders = self._wrap(single)
        self.assertEqual(placeholders, [])
        self.assertEqual(wrapped, single)

        multi = "▲\n▼\n"
        wrapped, placeholders = self._wrap(multi)
        self.assertEqual(len(placeholders), 1)

    def test_consecutive_load_in_canvas_anchors_are_never_wrapped_as_diagram(self):
        # REGRESSION (image.png): a multi-program answer injects several
        # `<a ... onclick="loadCanvas(..)">---Load in canvas: NAME---</a>`
        # anchors on consecutive lines. The `---` in the label matches the
        # ASCII-art-run heuristic, so the auto-detector USED to wrap the whole
        # block in <pre class="ascii-diagram"> and HTML-escape it — turning the
        # clickable links into unclickable raw text. They must survive intact.
        raw = (
            "## Solution\n"
            "Here's the working code:\n"
            "BEGIN-CODE<<<AuthFilter.java>>>\n"
            "public class AuthFilter {}\n"
            "END-CODE\n"
            "BEGIN-CODE<<<TokenHelper.java>>>\n"
            "public class TokenHelper {}\n"
            "END-CODE\n"
            "BEGIN-CODE<<<MainClient.java>>>\n"
            "public class MainClient {}\n"
            "END-CODE\n"
            "---\n"
            "END-RESPONSE"
        )
        final = self._process(raw)
        # The anchors are rendered as live HTML, NOT escaped source text.
        self.assertIn("loadCanvas(", final)
        self.assertIn("Load in canvas: ", final)
        self.assertNotIn("&lt;a ", final)
        self.assertNotIn("onclick=&#39;loadCanvas", final)
        # And the auto-detector did NOT mistake the anchor block (or the lone
        # `---` rule) for a diagram.
        self.assertNotIn('class="ascii-diagram"', final)

    def test_html_list_lines_with_arrows_are_not_wrapped_as_diagram(self):
        # REGRESSION (image copy.png): an LLM-emitted HTML list whose <li>
        # lines contain a `->`/arrow glyph matched the flowchart-arrow
        # heuristic, so two consecutive <li> lines were wrapped + escaped and
        # shown as raw source instead of a rendered bullet list.
        multi = (
            "<li><strong>Fade IN</strong> – duty cycle ramps 0 → 255</li>\n"
            "<li><strong>Fade OUT</strong> – duty cycle ramps 255 → 0</li>\n"
        )
        wrapped, placeholders = self._wrap(multi)
        self.assertEqual(placeholders, [])
        self.assertEqual(wrapped, multi)

    def test_ascii_art_with_angle_brackets_is_still_auto_detected(self):
        # The HTML-tag guard must NOT over-exclude: ASCII art that uses `<` as
        # part of an arrow (`<--->`) carries no real tag, so it stays a diagram.
        art = "<---->\n<---->\n"
        wrapped, placeholders = self._wrap(art)
        self.assertEqual(len(placeholders), 1)
        self.assertIn('class="ascii-diagram"', placeholders[0])

    def test_is_diagram_line_excludes_real_html_tags_only(self):
        from agent.services.response_parser import _is_diagram_line
        # Real tags → not a diagram line, even when they also carry diagram glyphs.
        self.assertFalse(_is_diagram_line("<a href='#'>---Load in canvas: x---</a>"))
        self.assertFalse(_is_diagram_line("<li>ramps 0 → 255</li>"))
        self.assertFalse(_is_diagram_line("text<br>more"))
        # ASCII art / box drawing → still a diagram line.
        self.assertTrue(_is_diagram_line("+----------+"))
        self.assertTrue(_is_diagram_line("│  Client  │ ───▶ │  Server  │"))
        self.assertTrue(_is_diagram_line("<---->"))
        self.assertTrue(_is_diagram_line("a < b and c > d ===="))


class AgentDescriptionsFileTests(TestCase):
    """The shipped ``agents_descriptions.md`` must be present at the repo root
    and parse cleanly. These guard the artefact end users actually consume."""

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[2]
        self.descriptions_path = self.project_root / 'agents_descriptions.md'

    def test_descriptions_file_exists_at_project_root(self):
        self.assertTrue(
            self.descriptions_path.exists(),
            f"agents_descriptions.md must live next to manage.py for the "
            f"loader's __file__-anchored resolution to find it. Looked at: "
            f"{self.descriptions_path}",
        )

    def test_descriptions_file_contains_workflow_agents_heading(self):
        text = self.descriptions_path.read_text(encoding='utf-8')
        self.assertIn(
            '## Workflow Agents', text,
            "Parser only reads rows under '## Workflow Agents'. Without that "
            "exact level-2 heading the entire file is invisible to it.",
        )

    def test_descriptions_file_parses_to_at_least_sixty_entries(self):
        # 60 = current agent count. Allow growth ('>='); flag shrinkage hard
        # so accidental row deletions don't slip through review.
        with open(self.descriptions_path, 'r', encoding='utf-8') as handle:
            purpose_map = views._parse_agent_purpose_map(handle.readlines())
        self.assertGreaterEqual(
            len(purpose_map), 60,
            f"Expected >=60 entries; got {len(purpose_map)}. "
            f"Did a row get deleted or its **Name** wrapping break?",
        )

    def test_every_description_is_non_empty_after_strip(self):
        with open(self.descriptions_path, 'r', encoding='utf-8') as handle:
            purpose_map = views._parse_agent_purpose_map(handle.readlines())
        empties = [k for k, v in purpose_map.items() if not v.strip()]
        self.assertEqual(
            empties, [],
            f"Empty descriptions defeat the whole point of the file: {empties}",
        )

    def test_no_description_contains_unescaped_pipe(self):
        # The parser regex stops at the first `|` after the description.
        # An unescaped pipe inside a description silently truncates it.
        with open(self.descriptions_path, 'r', encoding='utf-8') as handle:
            purpose_map = views._parse_agent_purpose_map(handle.readlines())
        with_pipe = [k for k, v in purpose_map.items() if '|' in v]
        self.assertEqual(
            with_pipe, [],
            f"Descriptions containing '|' get truncated by the parser: {with_pipe}",
        )


class AgentDescriptionsCoverageTests(TestCase):
    """For every workflow-agent folder under ``agent/agents/``, the loader
    must return a non-empty description. This is the regression-catcher: a
    new agent added to the codebase but forgotten in agents_descriptions.md
    will fail this test."""

    EXCLUDED_DIRS = frozenset({'pools'})

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        agents_dir = Path(__file__).resolve().parent / 'agents'
        cls.folder_keys: dict[str, str] = {}
        for child in sorted(agents_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith('.'):
                continue  # tooling caches (.ruff_cache, .pytest_cache, …) are never agents
            if child.name.lower() in cls.EXCLUDED_DIRS:
                continue
            cls.folder_keys[child.name] = views._normalize_agent_purpose_key(child.name)

    def test_every_agent_folder_has_a_loader_entry(self):
        purpose_map = views._load_agent_purpose_map()
        missing = [
            f"{folder} (key='{key}')"
            for folder, key in self.folder_keys.items()
            if not purpose_map.get(key, '').strip()
        ]
        self.assertEqual(
            missing, [],
            "Every agent folder under agent/agents/ must have a non-empty "
            "row in agents_descriptions.md. Missing entries:\n  - "
            + '\n  - '.join(missing),
        )

    def test_normalization_is_idempotent_and_punctuation_insensitive(self):
        # Sanity: the normalizer collapses every variant of an identifier
        # to the same key, so 'Kyber-KeyGen' / 'kyber keygen' / 'kyberkeygen'
        # all hit the same dict slot.
        for variant in ('Kyber-KeyGen', 'kyber keygen', 'KyberKeyGen', 'KYBER_KEYGEN'):
            self.assertEqual(views._normalize_agent_purpose_key(variant), 'kyberkeygen')
        for variant in ('Gateway Relayer', 'gateway-relayer', 'GATEWAY_RELAYER'):
            self.assertEqual(views._normalize_agent_purpose_key(variant), 'gatewayrelayer')

    def test_explicit_migration_display_names_all_resolve(self):
        # Each *_add_*.py migration writes a specific agentDescription string.
        # The frontend feeds those exact strings through normalization, so
        # the loader must return a real description for every one.
        purpose_map = views._load_agent_purpose_map()
        migrations_dir = Path(__file__).resolve().parent / 'migrations'
        display_name_re = re.compile(r"agentDescription='([^']+)'")
        seen: set[str] = set()
        for migration in migrations_dir.glob('*_add_*.py'):
            text = migration.read_text(encoding='utf-8')
            for match in display_name_re.finditer(text):
                # Skip the .filter() / .delete() callsites; only collect the
                # values written by .create(). Both look identical in this
                # regex so we just dedup by display name.
                seen.add(match.group(1))
        unresolved = sorted(
            name for name in seen
            if not purpose_map.get(views._normalize_agent_purpose_key(name), '').strip()
        )
        self.assertEqual(
            unresolved, [],
            f"Migration-declared display names with no description: {unresolved}",
        )


class AgentDescriptionsParserBoundaryTests(TestCase):
    """The parser walks ``## Workflow Agents`` to the next ``## `` heading.
    These tests pin that boundary contract so future edits don't accidentally
    hide rows or pull in unrelated tables."""

    def test_subsection_h3_does_not_terminate_the_section(self):
        markdown = (
            "# Title\n"
            "## Workflow Agents\n"
            "### Control Agents\n"
            "| Agent | Description |\n"
            "|-------|-------------|\n"
            "| **Starter** | Kicks off a flow. |\n"
            "### Action Agents\n"
            "| **Executer** | Runs a shell command. |\n"
            "## Notes\n"
            "| **NotAnAgent** | This row lives outside the Workflow Agents section. |\n"
        )
        result = views._parse_agent_purpose_map(markdown.splitlines(keepends=True))
        self.assertEqual(result.get('starter'), 'Kicks off a flow.')
        self.assertEqual(result.get('executer'), 'Runs a shell command.')
        self.assertNotIn('notanagent', result)

    def test_h2_heading_after_workflow_agents_terminates_parse(self):
        markdown = (
            "## Workflow Agents\n"
            "| **Starter** | Inside the section. |\n"
            "## Some Other Section\n"
            "| **Ghost** | Outside the section. |\n"
        )
        result = views._parse_agent_purpose_map(markdown.splitlines(keepends=True))
        self.assertIn('starter', result)
        self.assertNotIn('ghost', result)

    def test_table_header_and_separator_rows_are_skipped(self):
        markdown = (
            "## Workflow Agents\n"
            "| Agent | Description |\n"
            "|-------|-------------|\n"
            "| **Starter** | Real row. |\n"
        )
        result = views._parse_agent_purpose_map(markdown.splitlines(keepends=True))
        self.assertEqual(set(result), {'starter'})

    def test_missing_workflow_agents_heading_yields_empty_map(self):
        markdown = "## Random\n| **Starter** | nope |\n"
        self.assertEqual(views._parse_agent_purpose_map(markdown.splitlines(keepends=True)), {})


class AgentDescriptionsLoaderResolutionTests(TestCase):
    """Resolution order, fallback, and frozen-mode path probing.
    Each test isolates the loader from the real filesystem so behavior is
    deterministic regardless of what's actually on disk."""

    SAMPLE_PRIMARY = (
        "## Workflow Agents\n"
        "| **Alpha** | Description from primary file. |\n"
    )
    SAMPLE_FALLBACK = (
        "## Workflow Agents\n"
        "| **Alpha** | Description from fallback. |\n"
        "| **Beta** | Only in fallback. |\n"
    )

    def _isolated_loader(self, files: dict[str, str]):
        """Return a loader that only sees the supplied (path -> content)
        mapping, with everything else patched away."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        candidate_paths: list[str] = []
        for relative, content in files.items():
            full = root / relative
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding='utf-8')
            candidate_paths.append(str(full))
        # Always include both 'preferred' and 'fallback' positions so the
        # loader's iteration order is exercised — even if only one exists.
        for relative in ('agents_descriptions.md', 'README.md'):
            full = root / relative
            if str(full) not in candidate_paths:
                candidate_paths.append(str(full))
        return candidate_paths

    def test_primary_file_wins_over_fallback_when_both_present(self):
        candidates = self._isolated_loader({
            'agents_descriptions.md': self.SAMPLE_PRIMARY,
            'README.md': self.SAMPLE_FALLBACK,
        })
        with patch.object(views, '_resolve_agent_descriptions_search_paths',
                          return_value=candidates):
            result = views._load_agent_purpose_map()
        self.assertEqual(result.get('alpha'), 'Description from primary file.')
        self.assertNotIn('beta', result, "Fallback must not be merged on top of primary.")

    def test_falls_back_to_readme_when_primary_missing(self):
        candidates = self._isolated_loader({
            # primary intentionally absent
            'README.md': self.SAMPLE_FALLBACK,
        })
        with patch.object(views, '_resolve_agent_descriptions_search_paths',
                          return_value=candidates):
            result = views._load_agent_purpose_map()
        self.assertEqual(result.get('alpha'), 'Description from fallback.')
        self.assertEqual(result.get('beta'), 'Only in fallback.')

    def test_falls_back_to_readme_when_primary_has_no_workflow_agents_section(self):
        # Empty parse should NOT short-circuit — try the next candidate.
        candidates = self._isolated_loader({
            'agents_descriptions.md': "# Just a heading, no workflow agents table.\n",
            'README.md': self.SAMPLE_FALLBACK,
        })
        with patch.object(views, '_resolve_agent_descriptions_search_paths',
                          return_value=candidates):
            result = views._load_agent_purpose_map()
        self.assertEqual(result.get('alpha'), 'Description from fallback.')

    def test_returns_empty_dict_without_raising_when_all_sources_missing(self):
        candidates = self._isolated_loader({})  # nothing on disk
        with patch.object(views, '_resolve_agent_descriptions_search_paths',
                          return_value=candidates):
            result = views._load_agent_purpose_map()
        self.assertEqual(result, {})

    def test_search_paths_always_include_project_root_pair(self):
        with patch.object(views, 'sys', create=False) as mock_sys:
            # Simulate non-frozen interpreter
            mock_sys.frozen = False
            # Real os.path needs to keep working — only sys is patched.
            paths = views._resolve_agent_descriptions_search_paths()
        names = [Path(p).name for p in paths]
        self.assertIn('agents_descriptions.md', names)
        self.assertIn('README.md', names)
        self.assertEqual(
            names.index('agents_descriptions.md'),
            0,
            "agents_descriptions.md must be probed BEFORE README.md so an "
            "explicit description always wins over the legacy fallback.",
        )

    def test_frozen_mode_adds_executable_dir_probes(self):
        fake_exe_dir = Path(tempfile.mkdtemp(prefix='tlamatini_frozen_'))
        self.addCleanup(shutil.rmtree, fake_exe_dir, ignore_errors=True)
        fake_executable = fake_exe_dir / 'Tlamatini.exe'
        fake_executable.write_bytes(b'')

        with patch.object(views.sys, 'frozen', True, create=True), \
             patch.object(views.sys, 'executable', str(fake_executable)):
            paths = views._resolve_agent_descriptions_search_paths()

        normalized = {os.path.normcase(os.path.abspath(p)) for p in paths}
        for must_have in ('agents_descriptions.md', 'README.md'):
            expected = os.path.normcase(os.path.abspath(str(fake_exe_dir / must_have)))
            self.assertIn(
                expected, normalized,
                f"Frozen-mode probe missing {must_have} next to the executable. "
                f"Got: {sorted(normalized)}",
            )

    def test_search_paths_are_deduplicated(self):
        # If __file__ and sys.executable collapse to the same dir (which can
        # happen in some PyInstaller layouts), the loader must not double-probe.
        paths = views._resolve_agent_descriptions_search_paths()
        normalized = [os.path.normcase(os.path.abspath(p)) for p in paths]
        self.assertEqual(
            len(normalized), len(set(normalized)),
            f"Duplicate candidate paths slipped through dedup: {normalized}",
        )

    def test_legacy_alias_points_to_new_loader(self):
        # The old name is preserved so any out-of-tree caller (dev script,
        # scheduled remote agent) keeps working without code changes.
        self.assertIs(views._load_agent_purpose_map_from_readme, views._load_agent_purpose_map)


class AgentDescriptionsViewIntegrationTests(TestCase):
    """The view feeds the loaded map into the template via ``json_script``.
    Pin the contract that the view exposes the dict as a real dict (so it
    serializes to JSON) and that the live shipped file populates it."""

    def test_loaded_map_is_a_plain_dict_for_json_script(self):
        # Django's json_script filter only handles JSON-serializable values.
        # A custom object would silently render as garbage.
        purpose_map = views._load_agent_purpose_map()
        self.assertIsInstance(purpose_map, dict)
        # All keys/values must be strings — the JS map is `Record<string, string>`.
        for key, value in purpose_map.items():
            self.assertIsInstance(key, str, f"Non-string key: {key!r}")
            self.assertIsInstance(value, str, f"Non-string value for {key!r}: {value!r}")

    def test_shipped_file_yields_a_non_empty_map(self):
        # The whole point of the original bug fix: this dict must NOT be empty
        # in production. If it ever returns to empty silently, the tooltip UI
        # falls back to 'No description was found...' for every agent.
        purpose_map = views._load_agent_purpose_map()
        self.assertGreater(
            len(purpose_map), 0,
            "Loader returned an empty map — the entire workflow-agent tooltip "
            "system would be broken. Check that agents_descriptions.md exists "
            "at the project root (or next to the executable in frozen mode).",
        )


# ──────────────────────────────────────────────────────────────────────
# ACPX-Skills admin menu — HTTP endpoints + tool-surface gating
# ──────────────────────────────────────────────────────────────────────
class SkillsAdminEndpointTests(TestCase):
    """
    Covers the four HTTP endpoints behind the ACPX-Skills navbar dropdown:
      - GET /agent/skills/                  list (Browse pane)
      - GET /agent/skills/<name>/           detail (Browse detail pane)
      - POST /agent/skills/_/reload/        re-run boot_skills()
      - GET /agent/skills/_/diagnostics/    cross-check report
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="skills-admin", password="testpw"
        )
        from agent.acpx.service import boot_skills
        try:
            boot_skills()
        except Exception:
            pass

    def setUp(self):
        self.client = Client()
        self.client.login(username="skills-admin", password="testpw")

    def test_list_endpoint_returns_skills_array(self):
        resp = self.client.get("/agent/skills/")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertIn("skills", payload)
        self.assertIn("count", payload)
        self.assertIn("orphan_db_rows", payload)
        if payload["count"] > 0:
            row = payload["skills"][0]
            for key in ("name", "description", "runtime", "enabled",
                        "requires_tools", "max_iterations"):
                self.assertIn(key, row)

    def test_list_endpoint_requires_auth(self):
        anon = Client()
        resp = anon.get("/agent/skills/")
        self.assertIn(resp.status_code, (302, 403))

    def test_detail_endpoint_404_for_unknown_skill(self):
        resp = self.client.get("/agent/skills/__definitely_not_a_skill__/")
        self.assertEqual(resp.status_code, 404)

    def test_detail_endpoint_returns_body_for_known_skill(self):
        from agent.skills.registry import skill_registry
        skill_registry.reload_if_stale()
        any_skill = next(iter(skill_registry.all()), None)
        if any_skill is None:
            self.skipTest("No SKILL.md packages on disk in this environment.")
        resp = self.client.get(f"/agent/skills/{any_skill.name}/")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertEqual(payload["name"], any_skill.name)
        self.assertIn("body", payload)
        self.assertIn("inputs", payload)
        self.assertIn("outputs", payload)
        self.assertIn("permissions", payload)

    def test_reload_endpoint_succeeds(self):
        resp = self.client.post("/agent/skills/_/reload/")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertTrue(payload["ok"])
        self.assertIn("skills_loaded", payload)
        self.assertIn("db_rows_after", payload)

    def test_reload_endpoint_rejects_get(self):
        resp = self.client.get("/agent/skills/_/reload/")
        self.assertIn(resp.status_code, (405, 403))

    def test_diagnostics_endpoint_returns_expected_keys(self):
        resp = self.client.get("/agent/skills/_/diagnostics/")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        for key in (
            "skill_count", "db_row_count",
            "missing_tools", "missing_mcps", "unknown_acpx_agents",
            "orphan_db_rows", "tools_known", "mcps_known", "acpx_agents_known",
        ):
            self.assertIn(key, payload)


class SkillsToolSurfaceGatingTests(TestCase):
    """
    Verifies the `Skill.enabled = False` toggle hides the skill from
    list_skills and causes invoke_skill to return SKILL_DISABLED.
    """

    def test_list_skills_hides_disabled_rows(self):
        from agent.models import Skill as SkillRow
        from agent.acpx.tools import list_skills
        from agent.acpx.service import boot_skills
        try:
            boot_skills()
        except Exception:
            pass
        any_row = SkillRow.objects.first()
        if any_row is None:
            self.skipTest("No Skill DB rows in this environment.")
        prev = any_row.enabled
        try:
            any_row.enabled = False
            any_row.save(update_fields=["enabled"])
            envelope = json.loads(list_skills.func(""))
            self.assertTrue(envelope.get("ok"))
            names = {s["name"] for s in envelope.get("skills", [])}
            self.assertNotIn(any_row.name, names,
                             "Disabled skill leaked through list_skills filter")
        finally:
            any_row.enabled = prev
            any_row.save(update_fields=["enabled"])

    def test_invoke_skill_rejects_disabled(self):
        from agent.models import Skill as SkillRow
        from agent.acpx.tools import invoke_skill
        from agent.acpx.service import boot_skills
        try:
            boot_skills()
        except Exception:
            pass
        any_row = SkillRow.objects.first()
        if any_row is None:
            self.skipTest("No Skill DB rows in this environment.")
        prev = any_row.enabled
        try:
            any_row.enabled = False
            any_row.save(update_fields=["enabled"])
            envelope = json.loads(invoke_skill.func(any_row.name, "{}"))
            self.assertFalse(envelope.get("ok"))
            self.assertEqual(envelope.get("code"), "SKILL_DISABLED")
        finally:
            any_row.enabled = prev
            any_row.save(update_fields=["enabled"])

    def test_invoke_skill_unknown_returns_unknown_skill(self):
        from agent.acpx.tools import invoke_skill
        envelope = json.loads(invoke_skill.func("__definitely_unknown__", "{}"))
        self.assertFalse(envelope.get("ok"))
        self.assertEqual(envelope.get("code"), "UNKNOWN_SKILL")


class SkillsNavbarTemplateContractTests(TestCase):
    """
    Pin the agent_page.html structure so a careless template edit doesn't
    silently drop the ACPX-Skills menu.
    """
    TEMPLATE = (
        Path(__file__).resolve().parent / "templates" / "agent" / "agent_page.html"
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.text = cls.TEMPLATE.read_text(encoding="utf-8")

    def test_dropdown_present(self):
        self.assertIn('id="skills-menu-button"', self.text)
        self.assertIn(">ACPX-Skills<", self.text)

    def test_all_four_menu_items_present(self):
        for handler in (
            "OpenSkillsBrowseDialog",
            "OpenSkillsConfigureDialog",
            "OpenSkillsDiagnosticsDialog",
            "ReloadSkillRegistry",
        ):
            self.assertIn(handler + "(event)", self.text,
                          f"Menu item {handler} missing from template")

    def test_dialog_containers_present(self):
        for div_id in (
            "skills-configure-dialog-message",
            "skills-browse-dialog-message",
            "skills-diagnostics-dialog-message",
        ):
            self.assertIn(f'id="{div_id}"', self.text,
                          f"Dialog container {div_id} missing")

    def test_assets_loaded(self):
        self.assertIn("skills_dialog.js", self.text)
        self.assertIn("skills_dialog.css", self.text)


class LoadedContextPriorityTests(TestCase):
    """The user-loaded `<context>` (a directory/file attached via the chat
    Context menu) MUST take priority over Tlamatini's own `<self_knowledge>`
    block for generic "summarize/explain the project / the source code / the
    provided context" requests. Before this fix, the large authoritative
    self-knowledge block (Tlamatini.md) hijacked such requests and Tlamatini
    summarized herself instead of the loaded project. The fix lives in two
    places that these tests pin: (a) the shared prompt contract in prompt.pmt,
    and (b) the deterministic, model-agnostic scope header applied to the
    loaded context by every RAG/agent chain via
    ``agent.rag.utils.prepend_loaded_context_scope``."""

    def _read_prompt_pmt(self):
        prompt_path = os.path.join(os.path.dirname(views.__file__), 'prompt.pmt')
        with open(prompt_path, 'r', encoding='utf-8') as handle:
            return handle.read()

    def test_prompt_self_knowledge_block_is_scoped_to_tlamatini_not_loaded_project(self):
        text = self._read_prompt_pmt()
        self.assertIn('CRITICAL SCOPE', text)
        # The self-knowledge block must declare it is never the user's project.
        self.assertIn("NEVER the user's loaded project", text)

    def test_prompt_rule5_declares_loaded_context_priority(self):
        text = self._read_prompt_pmt()
        self.assertIn('Loaded-context priority', text)
        # The priority must be explicit: loaded context wins over self-knowledge.
        self.assertRegex(
            text,
            r"loaded `?<context>`? ALWAYS wins over self-knowledge",
        )

    def test_prepend_loaded_context_scope_prefixes_nonempty_context(self):
        from agent.rag.utils import prepend_loaded_context_scope
        raw = 'FILE MANIFEST (loaded files):\n- example.py\n\ndef example(): return 42'
        scoped = prepend_loaded_context_scope(raw)
        # Original content is preserved verbatim, after the scope header.
        self.assertTrue(scoped.endswith(raw))
        self.assertNotEqual(scoped, raw)
        # The header names the loaded content as the user's project, not Tlamatini.
        self.assertIn('LOADED USER CONTEXT', scoped)
        self.assertIn("NOT Tlamatini's own source code", scoped)
        self.assertIn('never with', scoped)

    def test_prepend_loaded_context_scope_leaves_empty_untouched(self):
        from agent.rag.utils import prepend_loaded_context_scope
        self.assertEqual(prepend_loaded_context_scope(''), '')
        self.assertEqual(prepend_loaded_context_scope(None), '')

    def test_all_loaded_context_chains_apply_the_scope_header(self):
        """Regression guard: every chain that binds the loaded context to the
        prompt/agent input must route it through prepend_loaded_context_scope,
        so removing the call in any single chain is caught here."""
        import agent.rag.chains.history_aware as history_aware
        import agent.rag.chains.unified as unified
        import agent.rag.chains.basic as basic
        for module in (history_aware, unified, basic):
            with open(module.__file__, 'r', encoding='utf-8') as handle:
                source = handle.read()
            self.assertIn(
                'prepend_loaded_context_scope', source,
                f"{module.__name__} no longer scopes the loaded context — "
                "loaded-context priority would silently regress in that chain",
            )

    def test_unified_agent_chain_marks_loaded_context_as_user_project(self):
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {'output': 'ok'}

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = (
            'FILE MANIFEST (loaded files):\n- example.py\n\n'
            '[1] example.py -- def example(): return 42'
        )
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({
            'input': "Summarize in very detail the project's source code in the provided context",
            'chat_history': [SimpleNamespace(content='prior turn')],
        })

        self.assertEqual(result['answer'], 'ok')
        agent_input = captured['payload']['input']
        # The pre-existing fallback label is preserved...
        self.assertIn('Loaded Context from Knowledge Base Fallback:', agent_input)
        # ...and now it is explicitly scoped to the user's project, not Tlamatini.
        self.assertIn("NOT Tlamatini's own", agent_input)
        self.assertIn('example.py', agent_input)


class PreLaunchScriptPreviewTests(TestCase):
    """The wrapped chat-agent launcher surfaces what the spawned agent is
    ABOUT to do in ``tlamatini.log`` BEFORE the child starts, so the user
    can see in plain text exactly what is going to run.

    Pure-helper unit tests covering both shapes (body / params / both),
    secret-key redaction, truncation, and a source-level contract test that
    the launcher actually calls the helper at the right point, plus a
    coverage contract that every wrapped chat-agent is accounted for.
    """

    def _spec(self, template_dir, display_name=None):
        return SimpleNamespace(
            template_dir=template_dir,
            display_name=display_name or template_dir.capitalize(),
            key=template_dir,
        )

    # -- existing shape: body-only (Executer / Pythonxer) -----------------

    def test_executer_preview_contains_command_body_and_runtime_dir(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('executer'),
            {'script': 'echo Hello && dir', 'non_blocking': False, 'execute_forked_window': True},
            r'C:\runtime\executer_3_abc',
            r'C:\runtime\executer_3_abc\executer_3_abc.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('EXECUTER COMMAND TO RUN', body)
        self.assertIn('echo Hello && dir', body)
        self.assertIn(r'C:\runtime\executer_3_abc', body)
        self.assertIn('forked_window  : True', body)
        self.assertIn('non_blocking   : False', body)
        self.assertIn('--- begin command ---', body)
        self.assertIn('--- end command ---', body)

    def test_pythonxer_preview_contains_python_code_and_size_summary(self):
        from agent import tools
        code = "import sys\nprint('Hello from Pythonxer!')\nsys.exit(0)"
        body = tools._render_pre_launch_script_preview(
            self._spec('pythonxer'),
            {'script': code, 'execute_forked_window': False},
            r'C:\runtime\pythonxer_1_xyz',
            r'C:\runtime\pythonxer_1_xyz\pythonxer_1_xyz.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('PYTHONXER SCRIPT TO RUN', body)
        self.assertIn("print('Hello from Pythonxer!')", body)
        self.assertIn('sys.exit(0)', body)
        self.assertIn('3 line(s)', body)
        self.assertIn('--- begin python script ---', body)
        self.assertIn('--- end python script ---', body)

    def test_preview_truncates_oversized_script_with_marker(self):
        from agent import tools
        cap = tools._PRE_LAUNCH_PREVIEW_MAX_CHARS
        oversized = 'X' * (cap + 1234)
        body = tools._render_pre_launch_script_preview(
            self._spec('pythonxer'),
            {'script': oversized},
            r'C:\runtime\pythonxer_2_big',
            r'C:\runtime\pythonxer_2_big\pythonxer_2_big.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('[TRUNCATED]', body)
        self.assertIn('1234 chars omitted', body)
        # The visible payload is the cap, not the full oversized blob.
        self.assertLess(body.count('X'), len(oversized))
        self.assertGreaterEqual(body.count('X'), cap)

    def test_preview_handles_missing_or_empty_script_field(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('executer'),
            {'non_blocking': True},  # no 'script' key at all
            '/tmp/r',
            '/tmp/r/log',
        )
        self.assertIsNotNone(body)
        self.assertIn('EXECUTER COMMAND TO RUN', body)
        self.assertIn('(empty)', body)
        self.assertIn('0 line(s), 0 char(s)', body)

    def test_preview_handles_non_dict_or_missing_inputs(self):
        from agent import tools
        self.assertIsNone(
            tools._render_pre_launch_script_preview(None, {'script': 'x'}, '/tmp', '/tmp/l'),
        )
        self.assertIsNone(
            tools._render_pre_launch_script_preview(
                self._spec('executer'), None, '/tmp', '/tmp/l',
            ),
        )
        self.assertIsNone(
            tools._render_pre_launch_script_preview(
                self._spec('executer'), 'not-a-dict', '/tmp', '/tmp/l',
            ),
        )

    # -- new shape: body + params (Ssher, Apirer, File-Creator, ...) ------

    def test_ssher_preview_surfaces_remote_command_with_user_and_ip(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('ssher', 'SSHer'),
            {'user': 'ops', 'ip': '10.0.0.5', 'script': 'systemctl status nginx'},
            '/runtime/ssher_1_xx',
            '/runtime/ssher_1_xx/ssher_1_xx.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('SSHER REMOTE COMMAND TO RUN', body)
        self.assertIn('param user', body)
        self.assertIn('ops', body)
        self.assertIn('param ip', body)
        self.assertIn('10.0.0.5', body)
        self.assertIn('--- begin remote command ---', body)
        self.assertIn('systemctl status nginx', body)
        self.assertIn('--- end remote command ---', body)

    def test_apirer_preview_surfaces_method_url_and_request_body(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('apirer', 'Apirer'),
            {
                'method': 'POST',
                'url': 'https://api.example.com/v1/orders',
                'headers': {'Content-Type': 'application/json'},
                'body': '{"sku": "ABC", "qty": 3}',
                'expected_status': 201,
                'timeout': 30,
            },
            '/runtime/apirer_2_yy',
            '/runtime/apirer_2_yy/apirer_2_yy.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('APIRER HTTP REQUEST TO SEND', body)
        self.assertIn('POST', body)
        self.assertIn('https://api.example.com/v1/orders', body)
        self.assertIn('Content-Type', body)
        self.assertIn('--- begin request body ---', body)
        self.assertIn('"sku": "ABC"', body)

    def test_file_creator_preview_surfaces_path_and_content(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('file_creator', 'File Creator'),
            {'file_path': r'C:\tmp\hello.py', 'content': 'print("hello")\n'},
            '/runtime/file_creator_4',
            '/runtime/file_creator_4/file_creator.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('FILE-CREATOR FILE TO WRITE', body)
        self.assertIn(r'C:\tmp\hello.py', body)
        self.assertIn('--- begin file content ---', body)
        self.assertIn('print("hello")', body)

    # -- params-only shape (Deleter, Mover, Kuberneter, ...) --------------

    def test_deleter_preview_lists_target_glob_without_body_block(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('deleter', 'Deleter'),
            {
                'files_to_delete': ['C:/Temp/*.tmp', 'D:/Logs/*.bak'],
                'recursive': True,
                'filetype_exclusions': '.profile',
                'trigger_mode': 'immediate',
                'trigger_event_string': 'EVENT DETECTED',
            },
            '/runtime/deleter_3',
            '/runtime/deleter_3/deleter.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('DELETER FILE DELETION TO PERFORM', body)
        # Lists render in compact json.
        self.assertIn('C:/Temp/*.tmp', body)
        self.assertIn('D:/Logs/*.bak', body)
        self.assertIn('recursive', body)
        # Params-only agents must NOT have begin/end body markers.
        self.assertNotIn('--- begin', body)
        self.assertNotIn('--- end', body)

    def test_kuberneter_preview_lists_command_namespace_and_extras(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('kuberneter', 'Kuberneter'),
            {
                'command': 'apply',
                'namespace': 'production',
                'extra_args': '-f deployment.yaml',
                'custom_command': '',
            },
            '/runtime/kuberneter_1',
            '/runtime/kuberneter_1/kuberneter.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('KUBERNETER kubectl COMMAND TO RUN', body)
        self.assertIn('param command', body)
        self.assertIn('apply', body)
        self.assertIn('production', body)
        self.assertIn('deployment.yaml', body)

    # -- dotted nested config paths (Emailer / Telegrammer / SQLer / ...) --

    def test_emailer_preview_resolves_dotted_smtp_and_email_paths(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('emailer', 'Send Email'),
            {
                'smtp': {
                    'host': 'smtp.gmail.com',
                    'port': 587,
                    'username': 'me@example.com',
                    'password': 'SUPER-SECRET',  # MUST be redacted
                    'use_tls': True,
                    'use_ssl': False,
                },
                'email': {
                    'from_address': 'me@example.com',
                    'to_addresses': ['ops@example.com'],
                    'cc_addresses': [],
                    'bcc_addresses': [],
                    'subject': '[ALERT] {source_agent}',
                    'body': 'Pattern matched at {timestamp}.',
                },
                'pattern': 'EVENT DETECTED',
                'attach_log': False,
            },
            '/runtime/emailer_5',
            '/runtime/emailer_5/emailer.log',
        )
        self.assertIsNotNone(body)
        self.assertIn('EMAILER MESSAGE TO SEND', body)
        self.assertIn('smtp.host', body)
        self.assertIn('smtp.gmail.com', body)
        self.assertIn('smtp.port', body)
        self.assertIn('587', body)
        self.assertIn('email.subject', body)
        self.assertIn('[ALERT] {source_agent}', body)
        self.assertIn('--- begin email body ---', body)
        self.assertIn('Pattern matched at {timestamp}.', body)
        # Secret-key redaction defense-in-depth.
        self.assertNotIn('SUPER-SECRET', body)

    # -- secret-key redaction --------------------------------------------

    def test_redaction_hides_value_for_secret_looking_leaf_keys(self):
        from agent import tools
        # Even if a future registry entry accidentally surfaced a password
        # field, the value MUST be redacted, never logged in clear.
        self.assertTrue(tools._looks_like_secret_key('smtp.password'))
        self.assertTrue(tools._looks_like_secret_key('tlamatini.password'))
        self.assertTrue(tools._looks_like_secret_key('telegram.api_hash'))
        self.assertTrue(tools._looks_like_secret_key('whatsapp.access_token'))
        self.assertTrue(tools._looks_like_secret_key('private_key'))
        self.assertFalse(tools._looks_like_secret_key('smtp.host'))
        self.assertFalse(tools._looks_like_secret_key('username'))
        rendered = tools._format_preview_value('hunter2', 'smtp.password')
        self.assertIn('REDACTED', rendered)
        self.assertNotIn('hunter2', rendered)
        # Empty secrets are explicitly noted as (unset), not as 0-char REDACTED.
        self.assertEqual(tools._format_preview_value('', 'smtp.password'), '(unset)')

    def test_redaction_hides_kyber_private_key_body_field(self):
        """If a body_field's KEY looks secret, the whole body is suppressed
        (size summary only)."""
        from agent import tools
        # Synthesize a registry entry whose body field is a secret-shaped key,
        # then render against a normal config -- result should NOT contain the
        # secret content even though the registry asked for it.
        original = dict(tools._PRE_LAUNCH_PREVIEW_BY_TEMPLATE)
        try:
            tools._PRE_LAUNCH_PREVIEW_BY_TEMPLATE['kyber_decipher'] = {
                'title': 'KYBER-DECIPHER (synthetic body-secret test)',
                'body': ('private_key', 'private key'),
            }
            body = tools._render_pre_launch_script_preview(
                self._spec('kyber_decipher', 'Kyber-Decipher'),
                {'private_key': 'BASE64-PRIVATE-KEY-MATERIAL'},
                '/runtime/kd', '/runtime/kd/k.log',
            )
        finally:
            tools._PRE_LAUNCH_PREVIEW_BY_TEMPLATE.clear()
            tools._PRE_LAUNCH_PREVIEW_BY_TEMPLATE.update(original)
        self.assertIsNotNone(body)
        self.assertNotIn('BASE64-PRIVATE-KEY-MATERIAL', body)
        self.assertIn('REDACTED', body)

    # -- value-rendering edge cases --------------------------------------

    def test_unset_and_missing_values_render_clearly(self):
        from agent import tools
        # Missing dotted path -> `(missing from config)`.
        body = tools._render_pre_launch_script_preview(
            self._spec('scper', 'SCPer'),
            {'direction': 'send'},  # user/ip/file all missing
            '/runtime/scper', '/runtime/scper/log',
        )
        self.assertIsNotNone(body)
        self.assertIn('(missing from config)', body)
        # Empty string -> `(unset)`.
        body2 = tools._render_pre_launch_script_preview(
            self._spec('scper', 'SCPer'),
            {'direction': 'send', 'user': '', 'ip': '', 'file': ''},
            '/runtime/scper2', '/runtime/scper2/log',
        )
        self.assertIsNotNone(body2)
        self.assertIn('(unset)', body2)
        self.assertNotIn('(missing from config)', body2)

    def test_list_and_dict_values_render_as_compact_json(self):
        from agent import tools
        body = tools._render_pre_launch_script_preview(
            self._spec('jenkinser', 'Jenkinser'),
            {
                'jenkins_url': 'http://ci.example.com',
                'job_name': 'deploy',
                'user': 'svc',
                'parameters': {'BRANCH': 'main', 'ENV': 'prod'},
                'use_parameters': True,
            },
            '/runtime/jenkinser', '/runtime/jenkinser/log',
        )
        self.assertIsNotNone(body)
        # Compact JSON for nested dict -> contains both keys on one line.
        self.assertIn('BRANCH', body)
        self.assertIn('ENV', body)
        self.assertIn('main', body)
        self.assertIn('prod', body)

    # -- coverage contract ------------------------------------------------

    def test_every_wrapped_chat_agent_is_in_preview_or_observational_set(self):
        """Every wrapped chat-agent template_dir MUST be in EXACTLY ONE of
        the preview registry (state-changing, surface it) or the
        observational frozenset (read-only, skip on purpose). Catches the
        drift case where someone adds a new wrapped agent and forgets to
        categorize it."""
        from agent import tools
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        preview = set(tools._PRE_LAUNCH_PREVIEW_BY_TEMPLATE)
        observational = set(tools._PRE_LAUNCH_PREVIEW_OBSERVATIONAL_TEMPLATES)
        overlap = preview & observational
        self.assertFalse(
            overlap,
            f'template_dirs in both preview AND observational sets: {sorted(overlap)}',
        )
        uncategorized = []
        for spec in WRAPPED_CHAT_AGENT_SPECS:
            td = spec.template_dir
            if td not in preview and td not in observational:
                uncategorized.append(td)
        self.assertFalse(
            uncategorized,
            f'wrapped chat-agents missing from BOTH sets (add to one): {sorted(uncategorized)}',
        )

    # -- launcher wires the helper at the right point ---------------------

    def test_launcher_logs_preview_immediately_before_subprocess_start(self):
        """Source-level contract: the launcher must INFO-log the preview
        AFTER all config-mutating steps (so what we log is what we run) and
        BEFORE ``start_chat_agent_subprocess(...)`` (so the user sees the
        intent before any side effect)."""
        import inspect as _inspect
        from agent import tools
        src = _inspect.getsource(tools._launch_wrapped_chat_agent)
        self.assertIn('_render_pre_launch_script_preview(', src)
        preview_at = src.index('_render_pre_launch_script_preview(')
        spawn_at = src.index('start_chat_agent_subprocess(')
        self.assertLess(
            preview_at, spawn_at,
            'preview render+log must happen BEFORE start_chat_agent_subprocess',
        )
        write_back_at = src.index('yaml.safe_dump(')
        self.assertLess(
            write_back_at, preview_at,
            'preview must be rendered AFTER config.yaml is finalized to disk',
        )


class ExecPermissionBrokerTests(TestCase):
    """Unit coverage for the Ask-Execs permission broker — the bridge that
    lets the synchronous Multi-Turn executor block on a browser Proceed/Deny
    choice."""

    def _make_broker(self, decider):
        """Build a broker whose emit synchronously resolves each request with
        ``decider(detail)`` so request_permission returns without real I/O."""
        from agent.exec_permission import ExecPermissionBroker

        captured = []

        def emit(detail):
            captured.append(detail)
            broker.resolve(detail['request_id'], decider(detail))

        broker = ExecPermissionBroker(emit)
        return broker, captured

    def test_proceed_decision_round_trips(self):
        broker, captured = self._make_broker(lambda d: 'proceed')
        decision = broker.request_permission({'tool_name': 'execute_command', 'program': 'dir'})
        self.assertEqual(decision, 'proceed')
        self.assertEqual(len(captured), 1)
        self.assertIn('request_id', captured[0])
        self.assertEqual(captured[0]['program'], 'dir')

    def test_deny_decision_round_trips(self):
        broker, _ = self._make_broker(lambda d: 'deny')
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'deny')

    def test_unknown_decision_normalizes_to_deny(self):
        broker, _ = self._make_broker(lambda d: 'maybe')
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'deny')

    def test_emit_failure_fails_safe_to_deny(self):
        from agent.exec_permission import ExecPermissionBroker

        def boom(_detail):
            raise RuntimeError('socket gone')

        broker = ExecPermissionBroker(boom)
        # Must NOT raise into the executor and must deny rather than run an
        # unconfirmed tool.
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'deny')

    def test_close_unblocks_pending_request_as_deny(self):
        import threading
        from agent.exec_permission import ExecPermissionBroker

        # emit does nothing, so request_permission blocks until close().
        broker = ExecPermissionBroker(lambda detail: None)
        result = {}

        def worker():
            result['decision'] = broker.request_permission({'tool_name': 'execute_command'})

        t = threading.Thread(target=worker)
        t.start()
        # Give the worker a moment to enter the wait loop, then close.
        t.join(timeout=0.1)
        broker.close()
        t.join(timeout=5)
        self.assertFalse(t.is_alive(), 'request_permission must unblock on close()')
        self.assertEqual(result.get('decision'), 'deny')

    def test_auto_proceed_skips_prompt_for_future_tools(self):
        # User unchecked Ask Execs mid-run: subsequent tools must run without
        # ever emitting a prompt.
        from agent.exec_permission import ExecPermissionBroker

        captured = []
        broker = ExecPermissionBroker(lambda detail: captured.append(detail))
        broker.set_auto_proceed(True)
        decision = broker.request_permission({'tool_name': 'execute_command', 'program': 'dir'})
        self.assertEqual(decision, 'proceed')
        self.assertEqual(captured, [], 'no prompt should be emitted once auto-proceed is on')

    def test_auto_proceed_unblocks_currently_pending_prompt_as_proceed(self):
        import threading
        from agent.exec_permission import ExecPermissionBroker

        # emit does nothing, so request_permission blocks (a prompt is showing)
        # until the user relaxes the gate mid-run.
        broker = ExecPermissionBroker(lambda detail: None)
        result = {}

        def worker():
            result['decision'] = broker.request_permission({'tool_name': 'execute_command'})

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=0.1)  # let the worker enter the wait loop
        broker.set_auto_proceed(True)
        t.join(timeout=5)
        self.assertFalse(t.is_alive(), 'set_auto_proceed(True) must unblock the pending prompt')
        self.assertEqual(result.get('decision'), 'proceed')

    def test_auto_proceed_can_be_rearmed_to_resume_prompting(self):
        # Re-checking Ask Execs mid-run must restore prompting behavior.
        broker, captured = self._make_broker(lambda d: 'proceed')
        broker.set_auto_proceed(True)
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'proceed')
        self.assertEqual(len(captured), 0)
        broker.set_auto_proceed(False)  # re-arm
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'proceed')
        self.assertEqual(len(captured), 1, 're-armed gate must emit a prompt again')

    def test_auto_proceed_is_noop_after_close(self):
        # A torn-down request must never spring back to life.
        from agent.exec_permission import ExecPermissionBroker

        broker = ExecPermissionBroker(lambda detail: None)
        broker.close()
        broker.set_auto_proceed(True)
        # Still denies — close() wins over a late relax.
        self.assertEqual(broker.request_permission({'tool_name': 'execute_command'}), 'deny')

    def test_set_broker_auto_proceed_helper_routes_to_registered_broker(self):
        from agent.exec_permission import (
            ExecPermissionBroker, register_broker, unregister_broker,
            set_broker_auto_proceed,
        )
        broker = ExecPermissionBroker(lambda d: None)
        register_broker('user-relax', broker)
        try:
            self.assertTrue(set_broker_auto_proceed('user-relax', True))
            self.assertEqual(
                broker.request_permission({'tool_name': 'execute_command'}), 'proceed'
            )
        finally:
            unregister_broker('user-relax')
        # No broker registered → helper reports nothing to relax.
        self.assertFalse(set_broker_auto_proceed('user-relax', True))

    def test_resolve_unknown_request_id_returns_false(self):
        broker, _ = self._make_broker(lambda d: 'proceed')
        self.assertFalse(broker.resolve('nonexistent', 'proceed'))

    def test_registry_register_get_unregister(self):
        from agent.exec_permission import (
            ExecPermissionBroker, register_broker, get_broker, unregister_broker,
        )
        broker = ExecPermissionBroker(lambda d: None)
        register_broker('user-xyz', broker)
        self.assertIs(get_broker('user-xyz'), broker)
        unregister_broker('user-xyz')
        self.assertIsNone(get_broker('user-xyz'))

    def test_resolve_permission_helper_routes_to_registered_broker(self):
        from agent.exec_permission import (
            ExecPermissionBroker, register_broker, unregister_broker, resolve_permission,
        )
        seen = {}

        def emit(detail):
            seen['request_id'] = detail['request_id']

        broker = ExecPermissionBroker(emit)
        register_broker('user-route', broker)
        try:
            import threading
            out = {}

            def worker():
                out['decision'] = broker.request_permission({'tool_name': 'execute_command'})

            t = threading.Thread(target=worker)
            t.start()
            # Wait until emit has captured the request_id, then resolve via the
            # module-level helper (the path the consumer's receive() uses).
            for _ in range(50):
                if 'request_id' in seen:
                    break
                t.join(timeout=0.05)
            self.assertTrue(resolve_permission('user-route', seen['request_id'], 'proceed'))
            t.join(timeout=5)
            self.assertEqual(out.get('decision'), 'proceed')
        finally:
            unregister_broker('user-route')


class AskExecsExecutorGateTests(TestCase):
    """Exercise the Ask-Execs permission gate inside the Multi-Turn executor:
    a Deny halts the chain and records the denial; a Proceed runs normally."""

    def _fake_llm_for_calls(self, calls_per_turn):
        iterator = iter(calls_per_turn + [[]])

        class _FakeLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                try:
                    calls = next(iterator)
                except StopIteration:
                    calls = []
                if not calls:
                    return SimpleNamespace(content='wrap up', tool_calls=[])
                tool_calls = [
                    {'id': f'c{idx}', 'name': name, 'args': args}
                    for idx, (name, args) in enumerate(calls)
                ]
                return SimpleNamespace(content='', tool_calls=tool_calls)

        return _FakeLLM()

    def _build_executor(self, tools, calls_per_turn):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        return MultiTurnToolAgentExecutor(
            llm=self._fake_llm_for_calls(calls_per_turn),
            system_prompt='test',
            tools=tools,
            max_iterations=10,
        )

    def _register_decider_broker(self, user_id, decider):
        from agent.exec_permission import ExecPermissionBroker, register_broker

        def emit(detail):
            broker.resolve(detail['request_id'], decider(detail))

        broker = ExecPermissionBroker(emit)
        register_broker(user_id, broker)
        self.addCleanup(self._unregister, user_id)
        return broker

    @staticmethod
    def _unregister(user_id):
        from agent.exec_permission import unregister_broker
        unregister_broker(user_id)

    def _executer_tool(self):
        from langchain.tools import tool

        @tool
        def execute_command(command: str) -> str:
            """Run a shell command."""
            return f"Command '{command}' executed successfully."

        return execute_command

    def _pythonxer_tool(self):
        from langchain.tools import tool

        @tool
        def execute_file(command: str) -> str:
            """Run a Python script."""
            return f"Command '{command}' executed successfully."

        return execute_file

    def test_deny_on_first_tool_halts_chain_and_records_denial(self):
        self._register_decider_broker('u1', lambda d: 'deny')
        exe = self._build_executor(
            tools=[self._executer_tool()],
            calls_per_turn=[[('execute_command', {'command': 'rm -rf /'})]],
        )
        result = exe.invoke({
            'input': 'wipe everything',
            'exec_report_enabled': True,
            'ask_execs_enabled': True,
            'ask_execs_user_id': 'u1',
        })
        # Tool NEVER ran → no exec report entries captured.
        self.assertEqual(result['exec_report_entries'], [])
        denied = result.get('exec_report_denied')
        self.assertIsNotNone(denied)
        self.assertEqual(denied['agent_display'], 'Executer')
        self.assertEqual(denied['kind'], 'Tool')
        self.assertEqual(denied['command'], 'rm -rf /')
        self.assertIn('⛔', result['output'])
        self.assertIn('interrupted', result['output'].lower())

    def test_proceed_runs_tool_normally(self):
        self._register_decider_broker('u2', lambda d: 'proceed')
        exe = self._build_executor(
            tools=[self._executer_tool()],
            calls_per_turn=[[('execute_command', {'command': 'git status'})]],
        )
        result = exe.invoke({
            'input': 'status',
            'exec_report_enabled': True,
            'ask_execs_enabled': True,
            'ask_execs_user_id': 'u2',
        })
        self.assertIsNone(result.get('exec_report_denied'))
        self.assertEqual(len(result['exec_report_entries']), 1)
        self.assertEqual(result['exec_report_entries'][0]['command'], 'git status')
        self.assertEqual(result['output'], 'wrap up')

    def test_deny_on_second_tool_keeps_first_execution_in_report(self):
        # Proceed for the executer, deny when the pythonxer install.py runs.
        def decider(detail):
            return 'deny' if 'install.py' in (detail.get('program') or '') else 'proceed'

        self._register_decider_broker('u3', decider)
        exe = self._build_executor(
            tools=[self._executer_tool(), self._pythonxer_tool()],
            calls_per_turn=[
                [('execute_command', {'command': 'git status'})],
                [('execute_file', {'command': 'install.py'})],
            ],
        )
        result = exe.invoke({
            'input': 'do two things',
            'exec_report_enabled': True,
            'ask_execs_enabled': True,
            'ask_execs_user_id': 'u3',
        })
        # First tool executed and is in the report; second was denied.
        self.assertEqual(len(result['exec_report_entries']), 1)
        self.assertEqual(result['exec_report_entries'][0]['agent_key'], 'executer')
        denied = result.get('exec_report_denied')
        self.assertIsNotNone(denied)
        self.assertEqual(denied['agent_display'], 'Pythonxer')
        self.assertEqual(denied['command'], 'install.py')

    def test_gate_disabled_runs_without_prompting(self):
        # No broker registered, ask_execs off → tool runs, no denial.
        exe = self._build_executor(
            tools=[self._executer_tool()],
            calls_per_turn=[[('execute_command', {'command': 'echo hi'})]],
        )
        result = exe.invoke({'input': 'go', 'exec_report_enabled': True})
        self.assertIsNone(result.get('exec_report_denied'))
        self.assertEqual(len(result['exec_report_entries']), 1)

    def test_missing_broker_fails_open_and_runs(self):
        # ask_execs on but no broker registered for the user (detached
        # browser / test) → fail-open: the tool still runs.
        exe = self._build_executor(
            tools=[self._executer_tool()],
            calls_per_turn=[[('execute_command', {'command': 'echo hi'})]],
        )
        result = exe.invoke({
            'input': 'go',
            'exec_report_enabled': True,
            'ask_execs_enabled': True,
            'ask_execs_user_id': 'no-such-user',
        })
        self.assertIsNone(result.get('exec_report_denied'))
        self.assertEqual(len(result['exec_report_entries']), 1)


class AskExecsHelperTests(TestCase):
    """Coverage for the pure classification / gate helpers."""

    def test_classify_tool_kind(self):
        from agent.mcp_agent import _classify_tool_kind
        self.assertEqual(_classify_tool_kind('execute_command'), 'Tool')
        self.assertEqual(_classify_tool_kind('chat_agent_ssher'), 'Agent')
        self.assertEqual(_classify_tool_kind('acp_spawn'), 'MCP / ACPX agent')
        self.assertEqual(_classify_tool_kind('invoke_skill'), 'Skill')

    def test_infer_execution_shell(self):
        from agent.mcp_agent import _infer_execution_shell
        self.assertEqual(_infer_execution_shell('chat_agent_pser', {}), 'PowerShell')
        self.assertEqual(_infer_execution_shell('execute_file', {}), 'Python interpreter')
        self.assertIn('SSH', _infer_execution_shell('chat_agent_ssher', {'host': '10.0.0.1'}))
        self.assertIn('10.0.0.1', _infer_execution_shell('chat_agent_ssher', {'host': '10.0.0.1'}))
        # Generic tools resolve to the platform shell (non-empty string).
        self.assertTrue(_infer_execution_shell('execute_command', {'command': 'dir'}))

    def test_requires_exec_permission_gate(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        exe = MultiTurnToolAgentExecutor.__new__(MultiTurnToolAgentExecutor)
        # Allowlist: ONLY the Tier 1 + Tier 2 execution agents are gated.
        # Tier 1 (arbitrary command / script execution).
        self.assertTrue(exe._requires_exec_permission('execute_command'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_executer'))
        self.assertTrue(exe._requires_exec_permission('execute_file'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_pythonxer'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_ssher'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_kalier'))
        # Tier 2 (domain / tool-specific command runners + ACPX).
        self.assertTrue(exe._requires_exec_permission('chat_agent_pser'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_dockerer'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_kuberneter'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_jenkinser'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_gitter'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_sqler'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_mongoxer'))
        self.assertTrue(exe._requires_exec_permission('decompile_java'))
        self.assertTrue(exe._requires_exec_permission('chat_agent_j_decompiler'))
        # Explicitly omitted from the gate per request: De-Compresser,
        # Unrealer, STM32er, and ACPXer (the acp_* family).
        self.assertFalse(exe._requires_exec_permission('chat_agent_de_compresser'))
        self.assertFalse(exe._requires_exec_permission('unzip_file'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_unrealer'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_stm32er'))
        self.assertFalse(exe._requires_exec_permission('acp_spawn'))
        self.assertFalse(exe._requires_exec_permission('acp_send'))
        self.assertFalse(exe._requires_exec_permission('acp_send_and_wait'))
        self.assertFalse(exe._requires_exec_permission('acp_kill'))
        self.assertFalse(exe._requires_exec_permission('acp_relay'))
        # NOT in Tier 1/2 → no prompt, even though several are state-changing.
        self.assertFalse(exe._requires_exec_permission('invoke_skill'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_scper'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_file_creator'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_deleter'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_apirer'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_send_email'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_keyboarder'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_mouser'))
        self.assertFalse(exe._requires_exec_permission('chat_agent_playwrighter'))
        # Read-only / inspection tools were never executions to approve.
        self.assertFalse(exe._requires_exec_permission('chat_agent_crawler'))
        self.assertFalse(exe._requires_exec_permission('googler'))
        # Management / polling tools are inspection, not execution → exempt.
        self.assertFalse(exe._requires_exec_permission('chat_agent_run_status'))
        self.assertFalse(exe._requires_exec_permission('get_current_time'))
        self.assertFalse(exe._requires_exec_permission('window_present'))
        self.assertFalse(exe._requires_exec_permission(''))

    def test_build_exec_permission_detail_shape(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        exe = MultiTurnToolAgentExecutor.__new__(MultiTurnToolAgentExecutor)
        detail = exe._build_exec_permission_detail({
            'name': 'execute_command',
            'args': {'command': 'ipconfig /all'},
        })
        self.assertEqual(detail['tool_name'], 'execute_command')
        self.assertEqual(detail['agent_display'], 'Executer')
        self.assertEqual(detail['kind'], 'Tool')
        self.assertEqual(detail['program'], 'ipconfig /all')
        self.assertTrue(detail['shell'])
        self.assertIn('command', detail['parameters'])


class AskExecsDenialBannerTests(TestCase):
    """Coverage for the red 'Execution interrupted' banner renderer."""

    def test_banner_renders_with_denied_detail(self):
        from agent.services.response_parser import _render_exec_denied_banner
        html = _render_exec_denied_banner({
            'kind': 'Agent',
            'agent_display': 'SSHer',
            'tool_name': 'chat_agent_ssher',
            'command': "ssh admin@10.0.0.1 'rm -rf /'",
            'shell': 'Remote SSH shell @ 10.0.0.1',
            'parameters': '{"host": "10.0.0.1"}',
        })
        self.assertIn('exec-denied-banner', html)
        self.assertIn('Execution interrupted', html)
        self.assertIn('SSHer', html)
        # Command is HTML-escaped (the single quotes become &#39;).
        self.assertIn('rm -rf /', html)
        self.assertIn('Remote SSH shell', html)
        self.assertNotIn("ssh admin@10.0.0.1 'rm", html)  # raw quotes escaped

    def test_banner_empty_when_no_denial(self):
        from agent.services.response_parser import _render_exec_denied_banner
        self.assertEqual(_render_exec_denied_banner(None), '')
        self.assertEqual(_render_exec_denied_banner({}), '')


class AskExecsChainPropagationTests(TestCase):
    """The denial detail must survive the UnifiedAgentChain payload rebuild
    (the same whitelist that once dropped exec_report_enabled) and be
    forwarded to the executor + returned to the consumer."""

    def test_chain_forwards_ask_execs_and_round_trips_denial(self):
        captured = {}

        class _FakeAgent:
            def invoke(self, payload):
                captured['payload'] = payload
                return {
                    'output': '⛔ Execution interrupted.',
                    'tool_calls_log': [],
                    'exec_report_denied': {
                        'tool_name': 'execute_command',
                        'agent_display': 'Executer',
                        'kind': 'Tool',
                        'command': 'rm -rf /',
                        'shell': 'cmd.exe',
                        'parameters': '{}',
                    },
                }

        chain = UnifiedAgentChain.__new__(UnifiedAgentChain)
        chain.history_summary_cfg = {'enable': False}
        chain.loaded_context = ''
        chain.unified_agent = _FakeAgent()
        chain.last_programs_name = []
        chain.httpx_client_instance = None

        result = chain.invoke({
            'input': 'wipe everything',
            'chat_history': [],
            'multi_turn_enabled': True,
            'ask_execs_enabled': True,
            'conversation_user_id': 4242,
        })

        # ask_execs_enabled + the user id must survive the payload whitelist.
        self.assertTrue(captured['payload'].get('ask_execs_enabled'))
        self.assertEqual(captured['payload'].get('ask_execs_user_id'), 4242)
        # Denial is returned regardless of the Exec report toggle.
        self.assertIn('exec_report_denied', result)
        self.assertEqual(result['exec_report_denied']['command'], 'rm -rf /')


class FlashWindowAttentionTests(TestCase):
    """Taskbar-flash + uppercase-log-banner attention notice for Ask-Execs
    prompts and Notifier notifications. Drives the REAL view and the REAL
    ``window_flash`` helper (no mocking the code under test) — the Win32 flash
    simply degrades to ``False`` in a headless test process, exactly as it does
    in a windowless launch."""

    def setUp(self):
        self.user = User.objects.create_user(username='flash_user', password='pw123456')
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, body):
        return self.client.post(
            reverse('flash_window'),
            data=json.dumps(body),
            content_type='application/json',
        )

    def test_view_logs_uppercase_banner_naming_the_page(self):
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            resp = self._post({'page': 'agent_page.html', 'reason': 'execution-approval'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertIn('flashed', data)  # bool — False in headless test, True with a console
        printed = buf.getvalue()
        self.assertIn('TLAMATINI NEEDS YOUR ATTENTION', printed)
        self.assertIn('AN EXECUTION APPROVAL (ASK-EXECS) IS PENDING', printed)
        self.assertIn('AGENT_PAGE.HTML', printed)

    def test_view_handles_notification_for_acp_page(self):
        import io
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            resp = self._post({'page': 'agentic_control_panel.html', 'reason': 'notification'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))
        printed = buf.getvalue()
        self.assertIn('A NOTIFIER NOTIFICATION HAS BEEN RAISED', printed)
        self.assertIn('AGENTIC_CONTROL_PANEL.HTML', printed)

    def test_view_tolerates_malformed_body(self):
        # Garbage body must not 500 — the view falls back to an empty dict and
        # emits the generic banner so the attention notice still fires.
        resp = self.client.post(
            reverse('flash_window'),
            data='this is not json',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))

    def test_view_requires_authentication(self):
        anon = Client()
        resp = anon.post(reverse('flash_window'), data='{}', content_type='application/json')
        self.assertEqual(resp.status_code, 302)

    def test_view_rejects_get(self):
        resp = self.client.get(reverse('flash_window'))
        self.assertEqual(resp.status_code, 405)

    def test_banner_is_fully_uppercase(self):
        from agent.window_flash import build_attention_banner

        banner = build_attention_banner('agent_page.html', 'execution-approval')
        # No lowercase letters anywhere — the user asked for MAYÚSCULAS.
        self.assertEqual(banner, banner.upper())

    def test_banner_falls_back_on_unknown_page_and_reason(self):
        from agent.window_flash import build_attention_banner

        banner = build_attention_banner('', '')
        self.assertEqual(banner, banner.upper())
        self.assertIn('TLAMATINI NEEDS YOUR ATTENTION', banner)
        self.assertIn('A TLAMATINI EVENT NEEDS YOU', banner)

    def test_helpers_never_raise_headless(self):
        from agent import window_flash

        # Both must return a bool and never raise, regardless of console state.
        self.assertIsInstance(window_flash.flash_console_window(), bool)
        self.assertIsInstance(
            window_flash.notify_attention('agent_page.html', 'notification'), bool
        )



class ConditionalRuleBlockTests(TestCase):
    """Pins item-3 of the weak-model prompt audit: the ACPX (Rule 12) and
    Templates (Rule 16) rule blocks are sentinel-wrapped in prompt.pmt and are
    injected into the Multi-Turn system prompt ONLY when their tool surface is
    actually bound for the request — so a smaller model is never handed ~1.8k
    words of ACPX instructions (or the firmware Templates rule) for tools it
    does not have. A leaked sentinel marker, or the wrong inclusion decision,
    fails here."""

    @staticmethod
    def _agent_dir():
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def _tool(name):
        # _build_system_prompt only reads .name and .description off each tool.
        return SimpleNamespace(name=name, description=f"{name} description")

    # --- the pure helper -------------------------------------------------
    def test_apply_conditional_rule_blocks_include_keeps_body_strips_markers(self):
        from agent.rag.config import apply_conditional_rule_blocks
        sample = ("HEAD\n<!--ACPX_RULES_BEGIN-->\nACPX BODY\n<!--ACPX_RULES_END-->\n"
                  "MID\n<!--TEMPLATES_RULES_BEGIN-->\nTPL BODY\n<!--TEMPLATES_RULES_END-->\nTAIL")
        out = apply_conditional_rule_blocks(sample, include_acpx=True, include_templates=True)
        self.assertIn("ACPX BODY", out)
        self.assertIn("TPL BODY", out)
        self.assertNotIn("ACPX_RULES_BEGIN", out)
        self.assertNotIn("ACPX_RULES_END", out)
        self.assertNotIn("TEMPLATES_RULES_BEGIN", out)
        self.assertNotIn("TEMPLATES_RULES_END", out)
        for anchor in ("HEAD", "MID", "TAIL"):
            self.assertIn(anchor, out)

    def test_apply_conditional_rule_blocks_exclude_drops_whole_block(self):
        from agent.rag.config import apply_conditional_rule_blocks
        sample = ("HEAD\n<!--ACPX_RULES_BEGIN-->\nACPX BODY\n<!--ACPX_RULES_END-->\n"
                  "MID\n<!--TEMPLATES_RULES_BEGIN-->\nTPL BODY\n<!--TEMPLATES_RULES_END-->\nTAIL")
        out = apply_conditional_rule_blocks(sample, include_acpx=False, include_templates=False)
        self.assertNotIn("ACPX BODY", out)
        self.assertNotIn("TPL BODY", out)
        self.assertNotIn("ACPX_RULES_BEGIN", out)
        self.assertNotIn("TEMPLATES_RULES_BEGIN", out)
        # Surrounding prose is untouched.
        for anchor in ("HEAD", "MID", "TAIL"):
            self.assertIn(anchor, out)

    def test_apply_conditional_rule_blocks_mixed_inclusion(self):
        from agent.rag.config import apply_conditional_rule_blocks
        sample = ("<!--ACPX_RULES_BEGIN-->\nACPX BODY\n<!--ACPX_RULES_END-->\n"
                  "<!--TEMPLATES_RULES_BEGIN-->\nTPL BODY\n<!--TEMPLATES_RULES_END-->")
        out = apply_conditional_rule_blocks(sample, include_acpx=True, include_templates=False)
        self.assertIn("ACPX BODY", out)
        self.assertNotIn("TPL BODY", out)

    def test_apply_conditional_rule_blocks_missing_markers_is_noop(self):
        from agent.rag.config import apply_conditional_rule_blocks
        sample = "no markers here at all"
        self.assertEqual(
            apply_conditional_rule_blocks(sample, include_acpx=False, include_templates=False),
            sample,
        )

    # --- the real prompt + _build_system_prompt integration --------------
    def test_real_prompt_pmt_has_balanced_sentinel_pairs(self):
        with open(os.path.join(self._agent_dir(), "prompt.pmt"), "r", encoding="utf-8") as fh:
            raw = fh.read()
        # Each marker wraps TWO spans: the full Rule block AND its one-line
        # Quick-Map pointer. begin/end counts must match per family.
        self.assertEqual(raw.count("<!--ACPX_RULES_BEGIN-->"),
                         raw.count("<!--ACPX_RULES_END-->"))
        self.assertEqual(raw.count("<!--TEMPLATES_RULES_BEGIN-->"),
                         raw.count("<!--TEMPLATES_RULES_END-->"))
        self.assertEqual(raw.count("<!--ACPX_RULES_BEGIN-->"), 2)
        self.assertEqual(raw.count("<!--TEMPLATES_RULES_BEGIN-->"), 2)

    def _build(self, tool_names):
        from agent.rag.config import load_config_and_prompt
        from agent.mcp_agent import _build_system_prompt
        _, prompt_template, _ = load_config_and_prompt(self._agent_dir())
        return _build_system_prompt(prompt_template, [self._tool(n) for n in tool_names])

    def test_acpx_rule_present_only_when_acpx_tool_bound(self):
        with_acpx = self._build(["acp_spawn", "execute_command"])
        self.assertIn("12) ACPX mechanics rule", with_acpx)
        # The Quick-Map pointer line gates with the rule block.
        self.assertIn("→ Rule 12", with_acpx)
        without_acpx = self._build(["execute_command"])
        self.assertNotIn("12) ACPX mechanics rule", without_acpx)
        self.assertNotIn("→ Rule 12", without_acpx)

    def test_templates_rule_present_only_when_firmware_tool_bound(self):
        with_fw = self._build(["chat_agent_stm32er"])
        self.assertIn("16) Template / project directory location rule", with_fw)
        self.assertIn("→ Rule 16", with_fw)
        without_fw = self._build(["execute_command"])
        self.assertNotIn("16) Template / project directory location rule", without_fw)
        self.assertNotIn("→ Rule 16", without_fw)
        # Rule 15's Quick-Map pointer must survive (it is NOT inside the block).
        self.assertIn("→ Rule 15", without_fw)

    def test_no_sentinel_marker_ever_leaks_into_system_prompt(self):
        for tool_names in (["execute_command"], ["acp_spawn"],
                           ["chat_agent_esp32er"], ["acp_relay", "chat_agent_unrealer"]):
            prompt = self._build(tool_names)
            for marker in ("ACPX_RULES_BEGIN", "ACPX_RULES_END",
                           "TEMPLATES_RULES_BEGIN", "TEMPLATES_RULES_END"):
                self.assertNotIn(marker, prompt,
                                 f"sentinel {marker} leaked with tools {tool_names}")


class WrappedAgentVisibilityGatingTests(TestCase):
    """Disabling an agent in **Configure Agents** (its ``Agent`` row) OR its
    wrapper Tool row (**Chat-Agent-<Name>** in Configure Mcps/Tools) MUST make
    the wrapped ``chat_agent_*`` tool invisible to the LLM — i.e. absent from
    ``get_mcp_tools()`` — so the LLM reports the agent as unknown/nonexistent.

    Uses Talker as the worked example (``agent_talker_status`` /
    ``tool_chat-agent-talker_status``) but the gate is generic across every
    wrapped chat-agent.
    """

    # global_state is a process-wide singleton; restore the two flags to the
    # fail-open default after each test so the rest of the suite is unaffected.
    def setUp(self):
        self._keys = ('tool_chat-agent-talker_status', 'agent_talker_status')
        self._saved = {k: global_state.get_state(k, 'enabled') for k in self._keys}

    def tearDown(self):
        for k, v in self._saved.items():
            global_state.set_state(k, v)

    def _talker_visible(self):
        from agent.tools import get_mcp_tools
        return any(getattr(t, 'name', '') == 'chat_agent_talker' for t in get_mcp_tools())

    def _set(self, tool_flag, agent_flag):
        global_state.set_state('tool_chat-agent-talker_status', tool_flag)
        global_state.set_state('agent_talker_status', agent_flag)

    def test_visible_when_both_agent_and_wrapper_enabled(self):
        self._set('enabled', 'enabled')
        self.assertTrue(self._talker_visible(),
                        "Talker should be bound when both its Agent row and "
                        "wrapper Tool row are enabled")

    def test_hidden_when_agent_disabled_in_configure_agents(self):
        # Uncheck "Talker" in Configure Agents -> agent_talker_status disabled.
        self._set('enabled', 'disabled')
        self.assertFalse(self._talker_visible(),
                         "Disabling the Talker Agent row must hide chat_agent_talker")

    def test_hidden_when_wrapper_tool_disabled_in_configure_mcps(self):
        # Uncheck "Chat-Agent-Talker" in Configure Mcps/Tools -> tool flag disabled.
        self._set('disabled', 'enabled')
        self.assertFalse(self._talker_visible(),
                         "Disabling the Chat-Agent-Talker wrapper must hide chat_agent_talker")

    def test_hidden_when_both_disabled(self):
        self._set('disabled', 'disabled')
        self.assertFalse(self._talker_visible())

    def test_gate_is_generic_across_wrapped_agents(self):
        # Spot-check a second agent (Shoter) to prove the gate is not Talker-specific.
        saved = {k: global_state.get_state(k, 'enabled')
                 for k in ('tool_chat-agent-shoter_status', 'agent_shoter_status')}
        try:
            from agent.tools import get_mcp_tools

            def shoter_visible():
                return any(getattr(t, 'name', '') == 'chat_agent_shoter'
                           for t in get_mcp_tools())

            global_state.set_state('tool_chat-agent-shoter_status', 'enabled')
            global_state.set_state('agent_shoter_status', 'enabled')
            self.assertTrue(shoter_visible())
            global_state.set_state('agent_shoter_status', 'disabled')
            self.assertFalse(shoter_visible())
        finally:
            for k, v in saved.items():
                global_state.set_state(k, v)

    def test_direct_tool_agent_also_gated_by_agent_row(self):
        # The direct @tool agents (Executer/execute_command, Pythonxer/execute_file,
        # Googler/googler) hide when their Agent row is disabled — consistent with
        # the wrapped gate, so disabling the canvas agent hides BOTH surfaces.
        saved = {k: global_state.get_state(k, 'enabled')
                 for k in ('tool_execute-command_status', 'agent_executer_status')}
        try:
            from agent.tools import get_mcp_tools

            def execute_command_visible():
                return any(getattr(t, 'name', '') == 'execute_command'
                           for t in get_mcp_tools())

            global_state.set_state('tool_execute-command_status', 'enabled')
            global_state.set_state('agent_executer_status', 'enabled')
            self.assertTrue(execute_command_visible())
            global_state.set_state('agent_executer_status', 'disabled')
            self.assertFalse(execute_command_visible(),
                             "Disabling the Executer Agent row must hide execute_command")
        finally:
            for k, v in saved.items():
                global_state.set_state(k, v)
