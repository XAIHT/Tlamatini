# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Fatal analysis reporting must remain independent of Tlamatini recovery.

Run in a verified visible foreground console; keep the console open afterward.
"""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .agents.visual_errors import publish_visual_error
from .visual_error_reporting import bind_visual_error_sink, report_visual_error, unbind_visual_error_sink


ROOT = Path(__file__).parent


def load_agent(name):
    path = ROOT / 'agents' / name / f'{name}.py'
    spec = importlib.util.spec_from_file_location('fatal_test_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FatalDeliveryTests(SimpleTestCase):
    def test_runtime_events_accumulate_with_unique_ids_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            for attempt in range(4):
                publish_visual_error(directory, 'configured-video', f'attempt {attempt}: secret-value', secrets=['secret-value'])
            data = json.loads((Path(directory) / 'notification.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['errors']), 4)
        self.assertEqual(len({e['id'] for e in data['errors']}), 4)
        self.assertNotIn('secret-value', json.dumps(data))
        self.assertTrue(all(e['kind'] == 'fatal_visual_error' for e in data['errors']))

    def test_canvas_poll_retains_accumulated_errors_after_delivery(self):
        from .views import check_all_agents_status_view
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'image_interpreter_1'
            runtime.mkdir()
            publish_visual_error(runtime, 'Image-Interpreter', 'configured model failed')
            with patch('agent.views.get_pool_path', return_value=directory):
                first = json.loads(check_all_agents_status_view(RequestFactory().get('/')).content)
                second = json.loads(check_all_agents_status_view(RequestFactory().get('/')).content)
            self.assertTrue((runtime / 'notification.json').exists())
        self.assertEqual(first['notifications'], second['notifications'])
        self.assertEqual(first['notifications'][0]['kind'], 'fatal_visual_error')

    def test_chat_poll_delivers_errors_even_after_child_has_exited(self):
        from .views import check_chat_runtimes_status_view
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'video_analyzer_001_test'
            runtime.mkdir()
            publish_visual_error(runtime, 'Video-Analyzer', 'merger failed')
            with patch('agent.views._get_chat_runtime_root_path', return_value=directory):
                response = json.loads(check_chat_runtimes_status_view(RequestFactory().get('/')).content)
            info = response['runtimes'][runtime.name]
            self.assertFalse(info['is_running'])
            self.assertEqual(info['notification']['errors'][0]['message'], 'merger failed')
            self.assertTrue((runtime / 'notification.json').exists())

    def test_error_reporting_does_not_cancel_or_pause_recovery(self):
        from . import cancellation
        events = []
        token = bind_visual_error_sink(events.append)
        try:
            with patch.object(cancellation, 'is_generation_cancelled', return_value=False) as cancellation_probe:
                for attempt in range(3):
                    report_visual_error('configured-model', f'tactic {attempt} failed')
                cancellation_probe.assert_not_called()
        finally:
            unbind_visual_error_sink(token)
        self.assertEqual(len(events), 3)

    def test_nested_request_sinks_do_not_mix_errors(self):
        outer, inner = [], []
        first = bind_visual_error_sink(outer.append)
        try:
            second = bind_visual_error_sink(inner.append)
            try:
                report_visual_error('model', 'inner')
            finally:
                unbind_visual_error_sink(second)
            report_visual_error('model', 'outer')
        finally:
            unbind_visual_error_sink(first)
        self.assertEqual([e['message'] for e in outer], ['outer'])
        self.assertEqual([e['message'] for e in inner], ['inner'])

    def test_dialog_delivery_error_cannot_break_recovery(self):
        def broken_sink(event):
            raise RuntimeError('browser disconnected')
        token = bind_visual_error_sink(broken_sink)
        try:
            event = report_visual_error('model', 'failed attempt')
        finally:
            unbind_visual_error_sink(token)
        self.assertEqual(event['message'], 'failed attempt')

    def test_legacy_image_tool_reports_error_and_can_succeed_on_next_attempt(self):
        from .imaging.image_interpreter import _report_visual_tool_errors
        events, attempts = [], []
        @_report_visual_tool_errors
        def analyze():
            attempts.append(1)
            return 'Error: timeout' if len(attempts) == 1 else 'Complete image analysis'
        token = bind_visual_error_sink(events.append)
        try:
            self.assertTrue(analyze().startswith('Error:'))
            self.assertEqual(analyze(), 'Complete image analysis')
        finally:
            unbind_visual_error_sink(token)
        self.assertEqual(len(events), 1)

    def test_runtime_refresh_includes_dialog_support_for_both_agents(self):
        from .services.flow_knowledge import write_runtime_knowledge
        with tempfile.TemporaryDirectory() as directory:
            for name in ('image_interpreter', 'video_analyzer'):
                target = Path(directory) / name
                write_runtime_knowledge(target, name)
                self.assertEqual((target / 'visual_errors.py').read_bytes(),
                                 (ROOT / 'agents/visual_errors.py').read_bytes())

    def test_video_import_does_not_change_process_or_logging(self):
        import logging
        import os
        import subprocess
        before = os.getcwd(), list(logging.getLogger().handlers), subprocess.Popen.__init__
        load_agent('video_analyzer')
        self.assertEqual(before, (os.getcwd(), list(logging.getLogger().handlers), subprocess.Popen.__init__))

    def test_image_failure_reports_error_and_starts_configured_recovery(self):
        module = load_agent('image_interpreter')
        with ExitStack() as stack:
            for name in ('_configure_agent_runtime', 'write_pid_file', 'wait_for_agents_to_stop'):
                stack.enter_context(patch.object(module, name))
            stack.enter_context(patch.object(module.time, 'sleep'))
            stack.enter_context(patch.object(module, 'load_config', return_value={'target_agents': ['recovery_1']}))
            stack.enter_context(patch.object(module, 'build_pipeline', side_effect=RuntimeError('configured model failed')))
            report = stack.enter_context(patch.object(module, 'report_fatal_error'))
            start = stack.enter_context(patch.object(module, 'start_agent'))
            cleanup = stack.enter_context(patch.object(module, 'remove_pid_file'))
            with self.assertRaises(SystemExit) as ended:
                module.main()
        self.assertEqual(ended.exception.code, 1)
        self.assertIn('configured model failed', str(report.call_args.args[0]))
        start.assert_called_once_with('recovery_1')
        cleanup.assert_called_once()

    def test_runtime_notification_io_failure_cannot_break_recovery(self):
        for agent in ('image_interpreter', 'video_analyzer'):
            with self.subTest(agent=agent):
                module = load_agent(agent)
                with patch.object(module, '_publish_fatal_error', side_effect=OSError('notification path unavailable')):
                    module.report_fatal_error('model failed', {})


class StreamIntegrityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.image = load_agent('image_interpreter')
        cls.video = load_agent('video_analyzer')


def stream_test(agent_name, body):
    def test(self):
        module = getattr(self, agent_name)
        with patch.object(module.urllib.request, 'urlopen', return_value=io.BytesIO(body)):
            with self.assertRaises((RuntimeError, ValueError, AttributeError, TypeError)):
                module._call_ollama_chat('http://localhost:1', '', 'configured-only', [], 'TEST')
    return test


for _name, _body in {
    'truncated': b'{"message":{"content":"partial"}}\n',
    'empty': b'{"done":true}\n',
    'malformed': b'not-json\n{"done":true}\n',
    'server_error': b'{"error":"model failed"}\n',
    'array': b'[]\n{"done":true}\n',
    'null': b'null\n',
    'empty_message': b'{"message":{"content":"   "},"done":true}\n',
}.items():
    for _agent in ('image', 'video'):
        setattr(StreamIntegrityTests, f'test_{_agent}_{_name}_is_failure', stream_test(_agent, _body))
