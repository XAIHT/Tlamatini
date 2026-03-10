from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from agent.consumers import AgentConsumer
from agent.models import AgentMessage
from tlamatini.asgi import application


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
