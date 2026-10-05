# Tlamatini Author Banner — Angela López Mendoza
"""Run from a verified visible foreground console; no hidden test execution."""
import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import flow_file_open as files


class FlowFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.queue = patch.object(files, 'request_directory', return_value=self.directory / 'queue')
        self.queue.start()
        self.addCleanup(self.queue.stop)
        self.addCleanup(self.temp.cleanup)
        self.flw = {'schemaVersion': 2, 'nodes': [
            {'id': 'sleeper-1', 'text': 'Sleeper', 'left': '100px', 'top': '50px', 'configData': {'seconds': 1}}
        ], 'connections': [], 'artifacts': {'custom': 'preserved'}}
        root = Path(__file__).resolve().parents[2]
        self.fpmt = json.loads((root / 'docs/examples/prompting-kickoff.fpmt').read_text(encoding='utf-8'))

    def encode(self, value):
        return json.dumps(value, ensure_ascii=False).encode('utf-8')

    def test_both_formats_utf8_bom_case_and_round_trip(self):
        for value, name in ((self.flw, 'Agents ñ.FLW'), (self.fpmt, 'Comments ñ.FPMT')):
            expected = files.decode_file(self.encode(value), name)
            self.assertEqual(files.decode_file(b'\xef\xbb\xbf' + self.encode(value), name), expected)
            token = files.create_request(self.encode(value), name, user_id=7)
            result = files.consume_request(token, 7, Path(name).suffix.lower())
            self.assertEqual(result, {'filename': name, 'flow': expected})
            self.assertEqual(files.decode_file(self.encode(result['flow']), name), expected)
            with self.assertRaises(files.FlowError):
                files.consume_request(token, 7, Path(name).suffix.lower())

    def test_old_flw_without_version_or_ids(self):
        self.flw.pop('schemaVersion')
        self.flw['nodes'][0].pop('id')
        self.assertEqual(files.decode_file(self.encode(self.flw), 'old.flw'), self.flw)

    def test_rejects_wrong_extension_wrong_format_future_version_and_corruption(self):
        for data, name in ((b'{}', 'x.flw'), (b'[]', 'x.flw'), (b'null', 'x.flw'),
                           (b'{broken', 'x.fpmt'), (b'\xff', 'x.flw'), (b'{}', 'x.fmt'),
                           (self.encode(self.fpmt), 'x.flw'), (self.encode(self.flw), 'x.fpmt'),
                           (b'{"nodes":[],"connections":[],"schemaVersion":999}', 'x.flw'),
                           (b'{"nodes":[],"connections":[],"extra":NaN}', 'x.flw'),
                           (b'{"nodes":[],"connections":[],"extra":1e999}', 'x.flw')):
            with self.subTest(name=name, data=data[:30]), self.assertRaises(files.FlowError):
                files.decode_file(data, name)

    def test_rejects_bad_agents_edges_and_duplicates_without_dropping_data(self):
        broken = []
        for key, value in (('text', None), ('left', 'expression(bad)'), ('configData', [])):
            item = copy.deepcopy(self.flw)
            item['nodes'][0][key] = value
            broken.append(item)
        item = copy.deepcopy(self.flw)
        item['nodes'].append(copy.deepcopy(item['nodes'][0]))
        broken.append(item)
        for edge in ({'sourceIndex': 0, 'targetIndex': 2}, {'sourceIndex': True, 'targetIndex': 0},
                     {'sourceIndex': 0, 'targetIndex': 0, 'inputSlot': -1}):
            item = copy.deepcopy(self.flw)
            item['connections'] = [edge]
            broken.append(item)
        for item in broken:
            with self.assertRaises(files.FlowError):
                files.decode_file(self.encode(item), 'bad.flw')

    def test_size_limit_and_untrusted_path_tokens(self):
        with self.assertRaises(files.FlowError):
            files.decode_file(b' ' * (files.MAX_FILE_BYTES + 1), 'big.fpmt')
        for token in ('../secret', '', 'a' * 63, 'A' * 64):
            with self.assertRaises(files.FlowError):
                files.consume_request(token, 7, '.fpmt')

    def test_owner_and_editor_mismatch_do_not_consume_request(self):
        token = files.create_request(self.encode(self.fpmt), 'note.fpmt', user_id=7)
        with self.assertRaises(files.FlowError):
            files.consume_request(token, 8, '.fpmt')
        with self.assertRaises(files.FlowError):
            files.consume_request(token, 7, '.flw')
        self.assertEqual(files.consume_request(token, 7, '.fpmt')['filename'], 'note.fpmt')

    def test_external_capability_and_expiry(self):
        token = files.create_request(self.encode(self.flw), 'external.flw')
        self.assertEqual(files.consume_request(token, 9, '.flw')['flow'], self.flw)
        token = files.create_request(self.encode(self.flw), 'expired.flw')
        path = files.request_directory() / (token + '.json')
        os.utime(path, (1, 1))
        with self.assertRaisesRegex(files.FlowError, 'expired'):
            files.consume_request(token, 9, '.flw')
        self.assertFalse(path.exists())

    def test_parallel_requests_are_independent_and_queue_is_bounded(self):
        tokens = [files.create_request(self.encode(self.flw), f'{n}.flw') for n in range(files.MAX_PENDING)]
        self.assertEqual(len(set(tokens)), files.MAX_PENDING)
        with self.assertRaisesRegex(files.FlowError, 'Too many'):
            files.create_request(self.encode(self.flw), 'extra.flw')
        for n, token in enumerate(tokens):
            self.assertEqual(files.consume_request(token, 1, '.flw')['filename'], f'{n}.flw')

    def test_ready_server_is_reused_without_launch_mutex(self):
        path = self.directory / 'several words ñ.fpmt'
        path.write_bytes(self.encode(self.fpmt))
        with patch.object(files, 'configured_port', return_value=8123), \
             patch.object(files, 'running_instance', return_value='ready'), \
             patch.object(files, 'acquire_launch_mutex') as mutex, \
             patch.object(files.webbrowser, 'open', return_value=True) as browser:
            url, port, opened = files.prepare_launch(str(path))
        self.assertTrue(opened)
        self.assertEqual(port, 8123)
        self.assertTrue(url.startswith('http://localhost:8123/agent/prompt_flow_panel/?open='))
        mutex.assert_not_called()
        browser.assert_called_once_with(url, new=2)

    def test_cold_launch_and_occupied_port(self):
        path = self.directory / 'agent.flw'
        path.write_bytes(self.encode(self.flw))
        with patch.object(files, 'running_instance', return_value='absent'), \
             patch.object(files, 'acquire_launch_mutex', return_value=True):
            url, _, opened = files.prepare_launch(str(path))
        self.assertFalse(opened)
        self.assertIn('/agent/agentic_control_panel/?open=', url)
        with patch.object(files, 'running_instance', return_value='occupied'), \
             patch.object(files, 'acquire_launch_mutex', return_value=True), \
             self.assertRaisesRegex(files.FlowError, 'already used'):
            files.prepare_launch(str(path))
        self.assertEqual(len(list(files.request_directory().glob('*.json'))), 1)

    def test_concurrent_cold_launch_waits_for_first(self):
        path = self.directory / 'agent.flw'
        path.write_bytes(self.encode(self.flw))
        with patch.object(files, 'running_instance', return_value='absent'), \
             patch.object(files, 'acquire_launch_mutex', return_value=False), \
             patch.object(files, 'wait_ready', return_value=True), \
             patch.object(files.webbrowser, 'open', return_value=True):
            self.assertTrue(files.prepare_launch(str(path))[2])

    def test_dispatch_precedes_protected_database_startup(self):
        text = (Path(__file__).resolve().parents[1] / 'manage.py').read_text(encoding='utf-8')
        tree = ast.parse(text)
        dispatch = next(n for n in tree.body if isinstance(n, ast.If) and '_FLOW_FILE_OPEN' in ast.unparse(n))
        swap = next(n for n in tree.body if isinstance(n, ast.Expr) and '_apply_pending_db_swap()' == ast.unparse(n))
        self.assertLess(dispatch.lineno, swap.lineno)

    def test_failed_browser_does_not_report_success_or_leave_a_snapshot(self):
        path = self.directory / 'agent.flw'
        path.write_bytes(self.encode(self.flw))
        with patch.object(files, 'running_instance', return_value='ready'), \
             patch.object(files.webbrowser, 'open', return_value=False), \
             self.assertRaisesRegex(files.FlowError, 'browser'):
            files.prepare_launch(str(path))
        self.assertEqual(list(files.request_directory().glob('*.json')), [])
