import os
import shutil
import tempfile
from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from agent.consumers import AgentConsumer, _sanitize_context_filename
from agent.models import AgentMessage
from agent.path_guard import (
    REJECTION_MESSAGE,
    get_runtime_agent_root,
    is_path_allowed,
    resolve_runtime_agent_path,
    safe_join_under,
)
from agent.services.filesystem import generate_tree_view_content
from tlamatini.asgi import application

try:
    from agent.chain_files_search_lcel import FileSearchRAGChain
except Exception:  # pragma: no cover - optional dependency path
    FileSearchRAGChain = None


class P0HardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='secret123')
        self.other_user = User.objects.create_user(username='bob', password='secret123')

    def test_agent_page_only_shows_current_users_messages(self):
        AgentMessage.objects.create(user=self.user, message='visible to alice')
        AgentMessage.objects.create(user=self.other_user, message='must stay private')

        self.client.force_login(self.user)
        response = self.client.get(reverse('agent_page'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['initial_messages']), 1)
        self.assertEqual(response.context['initial_messages'][0]['message'], 'visible to alice')

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
        AgentMessage.objects.create(user=self.user, message='delete me')
        AgentMessage.objects.create(user=self.other_user, message='keep me')

        consumer = AgentConsumer()
        async_to_sync(consumer.delete_messages_for_user)(self.user)

        self.assertFalse(AgentMessage.objects.filter(user=self.user).exists())
        self.assertTrue(AgentMessage.objects.filter(user=self.other_user).exists())

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
