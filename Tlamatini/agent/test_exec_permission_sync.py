"""Approval lifecycle regressions; no model, installed app or account database."""
import ast
import asyncio
import json
from pathlib import Path
import threading
import types
import unittest
from unittest.mock import patch

from . import exec_permission as permissions
from . import remote_controller_runtime as runtime
from .remote_controller_guard import claim_chat, release_chat


class ExecPermissionSyncTests(unittest.TestCase):
    def setUp(self):
        cancel = patch.object(permissions, 'is_generation_cancelled', return_value=False)
        cancel.start()
        self.addCleanup(cancel.stop)

    def check_decision(self, action, expected):
        events = []
        def emit(detail):
            events.append(('request', detail.copy()))
            action(broker, detail['request_id'])
        broker = permissions.ExecPermissionBroker(emit, on_resolved=lambda d: events.append(('resolved', d.copy())))
        self.assertEqual(broker.request_permission({'program': 'read-only fixture'}), expected)
        self.assertEqual([e[0] for e in events], ['request', 'resolved'])
        self.assertEqual(events[1][1], {'request_id': events[0][1]['request_id'], 'decision': expected})
        self.assertFalse(broker.resolve(events[0][1]['request_id'], 'proceed'))
        return events

    def test_approval_notifies_once(self):
        self.check_decision(lambda b, i: b.resolve(i, 'proceed'), 'proceed')

    def test_denial_notifies_once(self):
        self.check_decision(lambda b, i: b.resolve(i, 'deny'), 'deny')

    def test_teardown_notifies_denial(self):
        self.check_decision(lambda b, i: b.close(), 'deny')

    def test_cancel_notifies_denial(self):
        with patch.object(permissions, 'is_generation_cancelled', return_value=True):
            self.check_decision(lambda b, i: None, 'deny')

    def test_runtime_relax_notifies_proceed(self):
        self.check_decision(lambda b, i: b.set_auto_proceed(True), 'proceed')

    def test_first_answer_wins_before_waiter_retires_request(self):
        for first, second in [('proceed', 'deny'), ('deny', 'proceed')]:
            def action(b, i):
                self.assertTrue(b.resolve(i, first))
                self.assertFalse(b.resolve(i, second))
                b.set_auto_proceed(True)
                b.close()
            self.check_decision(action, first)

    def test_two_windows_race_accepts_exactly_one_answer(self):
        winners = []
        events = []
        barrier = threading.Barrier(2)
        def emit(detail):
            def respond(decision):
                barrier.wait(timeout=2)
                if broker.resolve(detail['request_id'], decision):
                    winners.append(decision)
            threads = [threading.Thread(target=respond, args=(d,)) for d in ['proceed', 'deny']]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=2)
            self.assertTrue(all(not t.is_alive() for t in threads))
        broker = permissions.ExecPermissionBroker(emit, on_resolved=events.append)
        result = broker.request_permission({})
        self.assertEqual(winners, [result])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['decision'], result)

    def test_failed_request_delivery_retires_partial_prompt(self):
        def failed(_): raise RuntimeError('fixture channel lost')
        events = []
        broker = permissions.ExecPermissionBroker(failed, on_resolved=events.append)
        self.assertEqual(broker.request_permission({}), 'deny')
        self.assertEqual(events[0]['decision'], 'deny')

    def test_notification_failure_does_not_repeat_execution_decision(self):
        def failed(_): raise RuntimeError('fixture notification lost')
        broker = permissions.ExecPermissionBroker(lambda d: broker.resolve(d['request_id'], 'proceed'), on_resolved=failed)
        self.assertEqual(broker.request_permission({}), 'proceed')

    def test_unprompted_paths_do_not_emit_resolution(self):
        events = []
        broker = permissions.ExecPermissionBroker(events.append, on_resolved=events.append)
        broker.set_auto_proceed(True)
        self.assertEqual(broker.request_permission({}), 'proceed')
        broker.close()
        self.assertEqual(broker.request_permission({}), 'deny')
        self.assertEqual(events, [])


def consumer_approval_methods():
    # Load the actual production methods without booting models, providers or
    # the application's startup jobs. Their channel transport is exercised below.
    tree = ast.parse(Path(__file__).with_name('consumers.py').read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AgentConsumer')
    names = {'_register_exec_permission_broker', 'exec_permission_request', 'exec_permission_resolved'}
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert len(methods) == len(names)
    module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    scope = {'__name__': 'agent.approval_consumer_fixture', '__package__': 'agent', 'asyncio': asyncio, 'json': json}
    exec(compile(module, 'consumers.py:approval methods', 'exec'), scope)
    return types.SimpleNamespace(**{name: scope[name] for name in names})


class ApprovalTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_rc_answer_retires_desktop_and_rc_prompt_before_return(self):
        for decision in ['proceed', 'deny']:
            methods = consumer_approval_methods()
            frames, progress = [], []
            consumer = types.SimpleNamespace(room_group_name='chat_user_approval_test')
            async def send(*, text_data): frames.append(json.loads(text_data))
            consumer.send = send
            class Layer:
                async def group_send(_, group, event):
                    self.assertEqual(group, consumer.room_group_name)
                    await getattr(methods, event['type'])(consumer, event)
            session = runtime.RuntimeSession(types.SimpleNamespace(pk=75112), progress.append)
            session._capturing = True
            consumer.channel_layer = runtime._OwnedChannelLayer(Layer(), consumer.room_group_name, session)
            session._consumer = consumer
            with patch.object(runtime, 'chat_loop', return_value=None), patch.object(permissions, 'is_generation_cancelled', return_value=False):
                self.assertTrue(claim_chat(75112, consumer))
                broker = methods._register_exec_permission_broker(consumer, 75112, 1)
                try:
                    waiting = asyncio.create_task(asyncio.to_thread(broker.request_permission, {'tool_name': 'read-only fixture'}))
                    for _ in range(100):
                        if progress: break
                        await asyncio.sleep(.01)
                    self.assertTrue(progress)
                    request_id = progress[0]['request_id']
                    self.assertTrue(await session.respond_permission(request_id, decision))
                    self.assertEqual(await asyncio.wait_for(waiting, 3), decision)
                    self.assertEqual([f['type'] for f in frames], ['exec-permission-request', 'exec-permission-resolved'])
                    self.assertEqual(frames[-1]['detail'], {'request_id': request_id, 'decision': decision})
                    self.assertEqual(progress[-1], {'type': 'permission', 'request_id': request_id, 'decision': decision})
                    self.assertNotIn(request_id, session._permission_ids)
                    self.assertFalse(await session.respond_permission(request_id, 'proceed'))
                finally:
                    permissions.unregister_broker(75112, broker)
                    release_chat(75112, consumer)

    async def test_slow_prompt_delivery_is_not_a_denial(self):
        # A busy server delivers the prompt late; that delay is not the person saying no.
        methods = consumer_approval_methods()
        frames = []
        consumer = types.SimpleNamespace(room_group_name='chat_user_slow_prompt', EXEC_PROMPT_DELIVERY_SECONDS=0.05)
        async def send(*, text_data): frames.append(json.loads(text_data))
        consumer.send = send
        class Layer:
            async def group_send(_, group, event):
                if event['type'] == 'exec_permission_request':
                    await asyncio.sleep(0.3)
                await getattr(methods, event['type'])(consumer, event)
        consumer.channel_layer = Layer()
        with patch.object(permissions, 'is_generation_cancelled', return_value=False):
            broker = methods._register_exec_permission_broker(consumer, 75115, 1)
            try:
                waiting = asyncio.create_task(asyncio.to_thread(broker.request_permission, {'tool_name': 'read-only fixture'}))
                for _ in range(200):
                    if frames: break
                    await asyncio.sleep(.01)
                self.assertEqual([f['type'] for f in frames], ['exec-permission-request'])
                self.assertFalse(waiting.done(), 'A late prompt must still wait for the answer')
                self.assertTrue(broker.resolve(frames[0]['detail']['request_id'], 'proceed'))
                self.assertEqual(await asyncio.wait_for(waiting, 3), 'proceed')
            finally:
                permissions.unregister_broker(75115, broker)

    async def test_prompt_that_never_arrives_is_denied(self):
        methods = consumer_approval_methods()
        consumer = types.SimpleNamespace(room_group_name='chat_user_lost_prompt', EXEC_PROMPT_DELIVERY_SECONDS=0.05)
        async def send(*, text_data): pass
        consumer.send = send
        class Layer:
            async def group_send(_, group, event):
                if event['type'] == 'exec_permission_request':
                    await asyncio.sleep(0.2)
                    raise RuntimeError('fixture channel lost')
                await getattr(methods, event['type'])(consumer, event)
        consumer.channel_layer = Layer()
        with patch.object(permissions, 'is_generation_cancelled', return_value=False):
            broker = methods._register_exec_permission_broker(consumer, 75116, 1)
            try:
                result = await asyncio.wait_for(asyncio.to_thread(broker.request_permission, {}), 3)
                self.assertEqual(result, 'deny')
            finally:
                permissions.unregister_broker(75116, broker)

    async def test_resolution_does_not_retire_another_runtime_request(self):
        progress = []
        session = runtime.RuntimeSession(types.SimpleNamespace(pk=75113), progress.append)
        session._capturing = True
        session._permission_ids.update(['a' * 32, 'b' * 32])
        await session._capture({'type': 'exec_permission_resolved', 'detail': {'request_id': 'a' * 32, 'decision': 'deny'}})
        self.assertEqual(session._permission_ids, {'b' * 32})
        self.assertEqual(len(progress), 1)

    async def test_invalid_resolution_is_not_forwarded(self):
        progress = []
        session = runtime.RuntimeSession(types.SimpleNamespace(pk=75114), progress.append)
        session._capturing = True
        for detail in [{'request_id': 'a' * 32, 'decision': 'allow'}, {'request_id': 'invalid', 'decision': 'deny'}]:
            await session._capture({'type': 'exec_permission_resolved', 'detail': detail})
        self.assertEqual(progress, [])
