"""Regression for the 2026-10-07 scalar-path Desktop deletion incident.

Run from a confirmed visible persistent console. All mutations use disposable
fixtures under the repository's Temp directory, never the actual Desktop.
"""
import ast
import io
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).parent / 'agents/mover/mover.py'


def load_operations():
    # Mover has process-start logging/chdir side effects. Load its real function
    # definitions without starting that runtime or altering its template log.
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(
        node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    namespace = {'NOISE_DIRS': ('.git', '__pycache__', 'node_modules')}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class MoverFileSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ops = load_operations()

    def setUp(self):
        scratch = ROOT / 'Temp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='mover-safety-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.desktop = self.root / 'Desktop'
        self.desktop.mkdir()
        self.sentinel = self.desktop / 'valuable-reference.pdf'
        self.sentinel.write_bytes(b'USER CONTENT MUST SURVIVE')
        self.log = io.StringIO()
        self.handler = logging.StreamHandler(self.log)
        self.logger = logging.getLogger()
        self.previous_level = self.logger.level
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)
        self.addCleanup(self.logger.removeHandler, self.handler)
        self.addCleanup(self.logger.setLevel, self.previous_level)

    def perform(self, sources, destination=None, operation='copy', **kwargs):
        # The broken implementation recursively erased the destination. Any
        # reintroduction must fail before it can delete even these fixtures.
        with patch('shutil.rmtree', side_effect=AssertionError('destination deletion forbidden')):
            return self.ops['perform_file_operations'](
                operation, sources, str(destination or self.desktop), **kwargs)

    def assert_sentinel(self):
        self.assertEqual(self.sentinel.read_bytes(), b'USER CONTENT MUST SURVIVE')

    def test_scalar_path_copies_once_and_preserves_destination(self):
        source = self.root / 'docker sheet.pdf'
        source.write_bytes(b'PDF content')
        result = self.perform(str(source))
        self.assertTrue(result['success'])
        self.assertEqual(result['completed'], 1)
        self.assertEqual((self.desktop / source.name).read_bytes(), source.read_bytes())
        self.assert_sentinel()

    def test_same_file_copy_and_move_are_verified_noops(self):
        for operation in ('copy', 'move'):
            result = self.perform(str(self.sentinel), operation=operation)
            self.assertTrue(result['success'])
            self.assertEqual(result['unchanged'], 1)
            self.assert_sentinel()

    def test_root_source_refused_without_destination_changes(self):
        result = self.perform([Path(self.root.anchor).as_posix()])
        self.assertFalse(result['success'])
        self.assert_sentinel()

    def test_single_separator_refused(self):
        result = self.perform(os.sep)
        self.assertFalse(result['success'])
        self.assert_sentinel()

    def test_current_directory_cannot_replace_destination_ancestor(self):
        source = self.desktop / 'nested'
        source.mkdir()
        result = self.perform(str(source), self.desktop / 'nested' / 'inside')
        self.assertFalse(result['success'])
        self.assert_sentinel()

    def test_overlapping_directories_refused_in_both_directions(self):
        check = self.ops['_check_transfer_paths']
        for source, dest in [(self.root, self.desktop), (self.desktop, self.root)]:
            with self.assertRaises(ValueError):
                check(str(source), str(dest))
        self.assert_sentinel()

    def test_missing_source_is_failed_with_explicit_receipt(self):
        result = self.perform(str(self.root / 'missing.pdf'))
        self.assertFalse(result['success'])
        self.assertGreater(result['errors'], 0)
        self.assertIn('status: failed', self.log.getvalue())
        self.assertIn('success: False', self.log.getvalue())
        self.assert_sentinel()

    def test_invalid_inputs_do_not_touch_destination(self):
        for sources in (None, 123, [], [''], [None], {'path': str(self.sentinel)}):
            with self.subTest(sources=sources):
                self.assertFalse(self.perform(sources)['success'])
        self.assertFalse(self.perform([str(self.sentinel)], operation='erase')['success'])
        self.assert_sentinel()

    def test_directory_copy_merges_without_erasing_unrelated_files(self):
        source = self.root / 'incoming' / 'bundle'
        source.mkdir(parents=True)
        (source / 'new.txt').write_text('new')
        target = self.desktop / 'bundle'
        target.mkdir()
        (target / 'keep.txt').write_text('keep')
        self.assertTrue(self.perform(str(source))['success'])
        self.assertEqual((target / 'new.txt').read_text(), 'new')
        self.assertEqual((target / 'keep.txt').read_text(), 'keep')
        self.assertTrue(source.exists())
        self.assert_sentinel()

    def test_directory_move_merges_and_only_removes_empty_source(self):
        source = self.root / 'incoming' / 'bundle'
        source.mkdir(parents=True)
        (source / 'new.txt').write_text('new')
        target = self.desktop / 'bundle'
        target.mkdir()
        (target / 'keep.txt').write_text('keep')
        self.assertTrue(self.perform(str(source), operation='move')['success'])
        self.assertEqual((target / 'new.txt').read_text(), 'new')
        self.assertEqual((target / 'keep.txt').read_text(), 'keep')
        self.assertFalse(source.exists())
        self.assert_sentinel()

    def test_copy_error_keeps_existing_target_and_source(self):
        source = self.root / self.sentinel.name
        source.write_bytes(b'replacement')
        with patch('shutil.copy2', side_effect=OSError('simulated disk error')):
            result = self.perform(str(source), operation='move')
        self.assertFalse(result['success'])
        self.assertEqual(source.read_bytes(), b'replacement')
        self.assert_sentinel()
        self.assertFalse(list(self.desktop.glob('.tlamatini-copy-*')))

    def test_copy_and_rename_to_explicit_file(self):
        target = self.root / 'Renamed.pdf'
        self.assertTrue(self.perform(str(self.sentinel), target)['success'])
        self.assertEqual(target.read_bytes(), self.sentinel.read_bytes())
        self.assert_sentinel()

    def test_duplicate_patterns_transfer_only_once(self):
        source = self.root / 'source.txt'
        source.write_text('text')
        result = self.perform([str(source), str(source)])
        self.assertTrue(result['success'])
        self.assertEqual(result['completed'], 1)
        self.assert_sentinel()

    def test_failure_receipt_drives_existing_verdict_engine(self):
        from agent.agent_verdict import classify_payload
        self.perform(str(self.root / 'absent.pdf'))
        verdict = classify_payload({'exit_code': 0, 'status': 'completed',
                                    'log_excerpt': self.log.getvalue()})
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.source, 'agent')


if __name__ == '__main__':
    unittest.main(verbosity=2)
