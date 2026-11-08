# Tlamatini Author Banner — Angela López Mendoza
"""Release metadata and real log-tee tests without Django/server startup.

Run visibly from this checkout. All generated files stay in its Temp directory.
"""
import ast
import collections
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Tlamatini'))
import versioning  # noqa: E402
import agent  # noqa: E402
from agent import version  # noqa: E402

SCRATCH = ROOT / 'Temp' / 'release-type-tests'
SCRATCH.mkdir(parents=True, exist_ok=True)


class ReleaseTypeTests(unittest.TestCase):
    def test_cli_explicit_type_and_no_environment_inference(self):
        for kind in ('private', 'public'):
            for option in (['--release-type', kind], ['--release-type=' + kind]):
                args = ['build.py', '--self-modify', *option]
                self.assertEqual(versioning.extract_cli_release_type(args), kind)
                self.assertEqual(args, ['build.py', '--self-modify'])
        with patch.dict(os.environ, {'TLAMATINI_RELEASE_TYPE': 'public'}):
            self.assertEqual(versioning.extract_cli_release_type(['build.py']), 'unspecified')
        for option in (['--release-type'], ['--release-type=garbage'],
                       ['--release-type', 'public', '--release-type', 'private']):
            with self.assertRaises(ValueError):
                versioning.extract_cli_release_type(['build.py', *option])

    def test_emission_persists_and_replaces_release_type(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary, ExitStack() as stack:
            root = Path(temporary)
            target = root / '_version.py'
            stack.enter_context(patch.object(versioning, 'VERSION_MODULE_PATH', target))
            stack.enter_context(patch.object(versioning, 'PYINSTALLER_VERSION_FILE', root / 'version.txt'))
            stack.enter_context(patch.dict(os.environ))
            for kind in ('private', 'public', 'unspecified'):
                versioning.emit_build_artifacts('9.8.7', release_type=kind)
                namespace = {}
                exec(compile(target.read_text(encoding='utf-8'), str(target), 'exec'), namespace)
                self.assertEqual(namespace['__release_type__'], kind)
                self.assertEqual(namespace['__version__'], '9.8.7')
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                versioning.emit_build_artifacts('9.8.7', release_type='garbage')
            self.assertEqual(target.read_bytes(), before)

    def test_runtime_ignores_environment_and_source_leftovers(self):
        for stored, expected in (('private', 'private'), ('public', 'public'),
                                 ('invalid', 'unspecified'), (None, 'unspecified')):
            generated = types.SimpleNamespace(__version__='9.8.7', __release_type__=stored)
            with patch.object(agent, '_version', generated, create=True), \
                    patch.object(sys, 'frozen', True, create=True), \
                    patch.dict(os.environ, {'TLAMATINI_RELEASE_TYPE': 'public'}):
                self.assertEqual(version.get_release_type(), expected)
                self.assertEqual(version.get_version_info()['release_type'], expected)
                with patch.object(sys, 'frozen', False):
                    self.assertEqual(version.get_release_type(), 'development')

    def test_real_tee_writes_release_banner_as_first_log_lines(self):
        # Execute the actual console classes, banner and tee setup in isolation.
        # Exclude all application startup calls: no DB, server, port or branding.
        source = ROOT / 'Tlamatini' / 'manage.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        names = {'_ConsoleWriter', '_ConsoleColorizer', '_TeeStream',
                 '_print_version_banner', '_setup_log_tee'}
        definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                       and node.name in names]
        self.assertEqual(len(definitions), len(names))
        for kind in ('private', 'public'):
            with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary, ExitStack() as stack:
                root = Path(temporary)
                namespace = dict(os=os, sys=sys, time=time, threading=threading,
                                 collections=collections, _USER_TAG_HOOK=None,
                                 __file__=str(root / 'manage.py'))
                exec(compile(ast.Module(body=definitions, type_ignores=[]), str(source), 'exec'), namespace)
                generated = types.SimpleNamespace(__version__='9.8.7', __release_type__=kind)
                stack.enter_context(patch.object(agent, '_version', generated, create=True))
                stack.enter_context(patch.object(sys, 'frozen', True, create=True))
                stack.enter_context(patch.object(sys, 'executable', str(root / 'Tlamatini.exe')))
                callbacks = []
                stack.enter_context(patch('atexit.register', side_effect=callbacks.append))
                # Keep the actual console drain thread; suppress only the endless
                # idle flusher so the test can close the fixture log deterministically.
                actual_thread = threading.Thread
                class NoIdleThread:
                    def start(self):
                        pass
                def make_thread(*args, **kwargs):
                    if kwargs.get('name') == 'tlamatini-log-flusher':
                        return NoIdleThread()
                    return actual_thread(*args, **kwargs)
                stack.enter_context(patch.object(threading, 'Thread', side_effect=make_thread))
                stdout, stderr = sys.stdout, sys.stderr
                opened = []
                actual_open = open
                def record_open(*args, **kwargs):
                    handle = actual_open(*args, **kwargs)
                    opened.append(handle)
                    return handle
                namespace['open'] = record_open
                try:
                    namespace['_setup_log_tee']()
                    print('After startup: test message.', flush=True)
                finally:
                    for callback in reversed(callbacks):
                        callback()
                    sys.stdout, sys.stderr = stdout, stderr
                    for handle in opened:
                        handle.close()
                lines = (root / 'tlamatini.log').read_text(encoding='utf-8').splitlines()
                self.assertIn('[VERSION]', lines[0])
                self.assertIn('9.8.7', lines[0])
                self.assertIn('[RELEASE]', lines[1])
                self.assertIn(kind.upper(), lines[1].upper())
                self.assertTrue(any('After startup: test message.' in line for line in lines))

    def test_build_wires_type_into_existing_frozen_version_module(self):
        tree = ast.parse((ROOT / 'build.py').read_text(encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'emit_build_artifacts']
        self.assertEqual(len(calls), 1)
        self.assertIn('release_type', {k.arg for k in calls[0].keywords})
        self.assertIn('--hidden-import=agent._version',
                      (ROOT / 'build.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
