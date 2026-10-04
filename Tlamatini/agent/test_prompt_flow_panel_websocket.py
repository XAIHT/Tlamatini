# Tlamatini Author Banner — Angela López Mendoza
"""Real ASGI routing/consumer/runner tests; model adapter is deterministic.

Run from the verified visible foreground menu test console. No database writes.
"""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asgiref.testing import ApplicationCommunicator
from channels.routing import URLRouter
from django.http import HttpRequest
from django.urls import resolve, reverse

from agent import prompt_flow_panel_consumer as consumer
from agent.routing import websocket_urlpatterns
from agent.test_prompt_flow_panel import diagram, node, Runtime


class Adapter(Runtime):
    instances = []

    def __init__(self, user, emit):
        super().__init__()
        self.closed = False
        self.instances.append(self)

    async def close(self):
        self.closed = True


class PromptFlowPanelRouteTests(unittest.TestCase):
    def test_view_url_and_authenticated_template_are_connected(self):
        url = reverse('prompt_flow_panel')
        self.assertEqual(url, '/agent/prompt_flow_panel/')
        request = HttpRequest()
        request.method = 'GET'
        request.user = SimpleNamespace(pk=17, is_authenticated=True)
        response = resolve(url).func(request)
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn('Prompt Flow Panel', text)
        self.assertIn('prompt-flow-panel-model.js', text)
        self.assertIn('prompt-flow-panel.js', text)
        self.assertIn('prompt_flow_panel.css', text)
        self.assertIn('class="pmt-panel"', text)


class PromptFlowPanelSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.communicators = []
        Adapter.instances = []
        self.adapter_patch = patch.object(consumer, 'PromptFlowPanelRuntime', Adapter)
        self.adapter_patch.start()

    async def asyncTearDown(self):
        try:
            for communicator in self.communicators:
                await communicator.send_input({'type': 'websocket.disconnect', 'code': 1000})
                await communicator.wait(timeout=2)
            await asyncio.sleep(0)
        finally:
            self.adapter_patch.stop()

    async def connect(self, authenticated=True):
        communicator = ApplicationCommunicator(URLRouter(websocket_urlpatterns), {
            'type': 'websocket', 'path': '/ws/prompt-flow-panel/',
            'user': SimpleNamespace(pk=17, is_authenticated=authenticated)})
        self.communicators.append(communicator)
        await communicator.send_input({'type': 'websocket.connect'})
        opening = await communicator.receive_output(timeout=2)
        if not authenticated:
            self.assertEqual(opening, {'type': 'websocket.close', 'code': 4401})
        else:
            self.assertEqual(opening['type'], 'websocket.accept')
            self.assertEqual((await self.event(communicator))['event'], 'ready')
        return communicator

    async def send(self, communicator, **message):
        await communicator.send_input({'type': 'websocket.receive', 'text': json.dumps(message)})

    async def event(self, communicator):
        return json.loads((await communicator.receive_output(timeout=2))['text'])

    async def until(self, communicator, event, **values):
        for _ in range(32):
            data = await self.event(communicator)
            if data['event'] == event and all(data.get(k) == v for k, v in values.items()):
                return data
        self.fail(f'No {event} event matching {values}')

    async def start_input(self, communicator):
        await self.send(communicator, action='start', flow=diagram([node('comment', 'user_input'), node('note', 'user_commentary', text='Static review only')]))
        return await self.until(communicator, 'input')

    async def test_anonymous_websocket_is_rejected(self):
        await self.connect(authenticated=False)

    async def test_ping_does_not_start_playback(self):
        socket = await self.connect()
        await self.send(socket, action='ping')
        self.assertEqual((await self.event(socket))['event'], 'pong')
        self.assertEqual(Adapter.instances, [])

    async def test_malformed_commands_fail_without_losing_the_connection(self):
        socket = await self.connect()
        for raw in ('{', '[]', 'null'):
            await socket.send_input({'type': 'websocket.receive', 'text': raw})
            self.assertEqual((await self.event(socket))['event'], 'error')
        await self.send(socket, action='ping')
        self.assertEqual((await self.event(socket))['event'], 'pong')

    async def test_opening_connection_never_executes_a_flow(self):
        socket = await self.connect()
        self.assertTrue(await socket.receive_nothing(timeout=.02))
        self.assertEqual(Adapter.instances, [])

    async def test_stale_run_and_reply_ids_do_not_advance_playback(self):
        socket = await self.connect()
        request = await self.start_input(socket)
        for run_id, request_id in (('stale', request['request_id']), (request['run_id'], 'stale')):
            await self.send(socket, action='reply', run_id=run_id, request_id=request_id, value='wrong')
            self.assertEqual((await self.event(socket))['event'], 'error')
            self.assertEqual(Adapter.instances[0].calls, [])
        await self.send(socket, action='reply', run_id=request['run_id'], request_id=request['request_id'], value='ñ correct')
        result = await self.until(socket, 'state', status='completed')
        self.assertEqual(result['run_id'], request['run_id'])
        self.assertEqual(Adapter.instances[0].calls, [('comment', 'ñ correct')])
        self.assertTrue(Adapter.instances[0].closed)

    async def test_duplicate_start_is_rejected_and_original_run_can_stop(self):
        socket = await self.connect()
        request = await self.start_input(socket)
        await self.send(socket, action='start', flow=diagram([node('other')]))
        self.assertEqual((await self.event(socket))['event'], 'error')
        self.assertEqual(len(Adapter.instances), 1)
        await self.send(socket, action='stop', run_id=request['run_id'])
        await self.until(socket, 'state', status='stopped')
        self.assertTrue(Adapter.instances[0].closed)
        self.assertTrue(Adapter.instances[0].cancelled)

    async def test_pause_holds_completion_until_resume(self):
        socket = await self.connect()
        request = await self.start_input(socket)
        await self.send(socket, action='pause', run_id=request['run_id'])
        await self.until(socket, 'state', status='paused')
        await self.send(socket, action='reply', run_id=request['run_id'], request_id=request['request_id'], value='paused reply')
        self.assertTrue(await socket.receive_nothing(timeout=.05))
        await self.send(socket, action='resume', run_id=request['run_id'])
        await self.until(socket, 'state', status='completed')

    async def test_independent_connections_do_not_share_pending_replies(self):
        first, second = await self.connect(), await self.connect()
        a, b = await self.start_input(first), await self.start_input(second)
        self.assertNotEqual(a['run_id'], b['run_id'])
        await self.send(second, action='reply', run_id=a['run_id'], request_id=a['request_id'], value='wrong socket')
        self.assertEqual((await self.event(second))['event'], 'error')
        for socket, request in ((first, a), (second, b)):
            await self.send(socket, action='stop', run_id=request['run_id'])
            await self.until(socket, 'state', status='stopped')

    async def test_model_failure_stops_before_downstream_side_effects(self):
        socket = await self.connect()
        async def broken(*args):
            raise RuntimeError('Injected provider failure')
        with patch.object(Adapter, 'prompt', broken):
            await self.send(socket, action='start', flow=diagram([node('p'), node('f', 'flush_embeddings')], [('p', 'f', 'next')]))
            result = await self.until(socket, 'state', status='failed')
        self.assertIn('Injected provider failure', result['message'])
        self.assertEqual(Adapter.instances[0].calls, [])
        self.assertTrue(Adapter.instances[0].closed)
