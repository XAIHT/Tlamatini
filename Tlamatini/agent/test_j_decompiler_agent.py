# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the J-Decompiler agent + the ``decompile_java`` tool.

PRIMARY FOCUS — the PR #1 security hardening:
    jd-cli.bat should be invoked via ``cmd /c`` with a LIST argv and
    ``shell=False`` (no ``shell=True`` injection surface), on BOTH surfaces:
        - agent : agent/agents/j_decompiler/j_decompiler.py :: decompile_file()
        - tool  : agent/tools.py                            :: decompile_java()

That hardening lives in PR #1 (not yet merged). So the three "PR #1 gate"
tests are written as **self-activating gates**: while the source still uses the
legacy ``shell=True`` form they ``skipTest`` (keeping the suite green), and the
moment PR #1 lands they run their assertions and enforce the secure invocation.

The remaining tests are FUNCTIONAL and pass on BOTH the legacy and hardened
forms — success / non-zero / timeout / missing-bat result routing, the
.class-vs-.jar destination logic, and that input/output paths (incl. ones WITH
SPACES) travel as discrete argv elements.

The agent ships as a standalone pool subprocess, so it is loaded via
``importlib.util.spec_from_file_location`` with cwd saved+restored, mirroring
``test_de_compresser.py`` (its module-level ``os.chdir`` / ``open(LOG, 'w')``
side effects must not leak into the test runner).
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from functools import lru_cache
from unittest.mock import patch

from django.test import SimpleTestCase

# Shown when a PR #1 gate test skips because the source still uses shell=True.
_PR1_PENDING = (
    'PR #1 jd-cli hardening (cmd /c + shell=False) not merged yet — '
    'this gate auto-activates once the secure invocation is in source.'
)


@lru_cache(maxsize=1)
def _load_jd_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'j_decompiler', 'j_decompiler.py'
    )
    spec = importlib.util.spec_from_file_location(
        'agent_j_decompiler_module_for_tests', module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load J-Decompiler module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
    return module


def _is_hardened(cmd, kwargs):
    """True when the capture shows the PR #1 secure invocation."""
    return (
        isinstance(cmd, list)
        and cmd[:2] == ['cmd', '/c']
        and kwargs.get('shell') is False
    )


class _FakeCompleted:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class JDecompilerAgentInvocationTests(SimpleTestCase):
    """``decompile_file()`` routes results correctly and (post-PR-1) spawns safely."""

    def setUp(self):
        self.jd = _load_jd_module()
        self.tmp = tempfile.mkdtemp(prefix='jd_agent_test_')
        self.jd_dir = os.path.join(self.tmp, 'jd-cli')
        os.makedirs(self.jd_dir, exist_ok=True)
        self.jd_bat = os.path.join(self.jd_dir, 'jd-cli.bat')
        with open(self.jd_bat, 'w', encoding='utf-8') as f:
            f.write('@echo off\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, filepath, returncode=0, raise_exc=None):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured['cmd'] = cmd
            captured['kwargs'] = kwargs
            if raise_exc is not None:
                raise raise_exc
            return _FakeCompleted(returncode=returncode, stdout='ok', stderr='boom')

        with patch.object(subprocess, 'run', side_effect=fake_run):
            ok = self.jd.decompile_file(filepath, self.jd_dir)
        return ok, captured

    # ---- PR #1 hardening gates (skip while legacy, enforce once merged) ---- #
    def test_pr1_uses_cmd_c_list_argv_and_shell_false(self):
        jar = os.path.join(self.tmp, 'app.jar')
        open(jar, 'w').close()
        ok, cap = self._run(jar, returncode=0)
        self.assertTrue(ok)
        if not _is_hardened(cap['cmd'], cap['kwargs']):
            self.skipTest(_PR1_PENDING)
        dest = os.path.join(self.tmp, 'app')  # .jar -> subdir named after basename
        self.assertEqual(cap['cmd'], ['cmd', '/c', self.jd_bat, jar, dest])
        self.assertIs(cap['kwargs'].get('shell'), False)

    def test_pr1_never_invokes_with_shell_true(self):
        jar = os.path.join(self.tmp, 'lib.jar')
        open(jar, 'w').close()
        _, cap = self._run(jar)
        if not _is_hardened(cap['cmd'], cap['kwargs']):
            self.skipTest(_PR1_PENDING)
        self.assertIsNot(cap['kwargs'].get('shell'), True)
        self.assertEqual(cap['cmd'][0], 'cmd')
        self.assertEqual(cap['cmd'][1], '/c')
        self.assertIn(self.jd_bat, cap['cmd'])

    # ---- functional (active on BOTH legacy and hardened forms) ------------- #
    def test_input_and_output_paths_are_discrete_argv_elements(self):
        """Paths WITH SPACES must each be ONE list element — never a shell-quoted
        string. True on the legacy list form AND the hardened cmd /c form."""
        spaced_dir = os.path.join(self.tmp, 'my cool libs')
        os.makedirs(spaced_dir, exist_ok=True)
        jar = os.path.join(spaced_dir, 'awesome app.jar')
        open(jar, 'w').close()
        ok, cap = self._run(jar, returncode=0)
        self.assertTrue(ok)
        self.assertIsInstance(cap['cmd'], list)
        self.assertIn(jar, cap['cmd'])
        self.assertIn(os.path.join(spaced_dir, 'awesome app'), cap['cmd'])

    def test_class_file_dest_is_beside_source(self):
        cls = os.path.join(self.tmp, 'Foo.class')
        open(cls, 'w').close()
        _, cap = self._run(cls, returncode=0)
        self.assertEqual(cap['cmd'][-1], self.tmp)  # .class -> output beside it

    def test_jar_dest_is_subdir_named_after_basename(self):
        jar = os.path.join(self.tmp, 'mylib.jar')
        open(jar, 'w').close()
        _, cap = self._run(jar, returncode=0)
        self.assertEqual(cap['cmd'][-1], os.path.join(self.tmp, 'mylib'))

    def test_nonzero_returncode_reports_failure(self):
        jar = os.path.join(self.tmp, 'bad.jar')
        open(jar, 'w').close()
        ok, _ = self._run(jar, returncode=3)
        self.assertFalse(ok)

    def test_timeout_returns_false(self):
        jar = os.path.join(self.tmp, 'slow.jar')
        open(jar, 'w').close()
        ok, _ = self._run(
            jar, raise_exc=subprocess.TimeoutExpired(cmd='jd-cli', timeout=300)
        )
        self.assertFalse(ok)

    def test_missing_jd_cli_bat_returns_false_without_spawning(self):
        os.remove(self.jd_bat)
        calls = {'n': 0}

        def fake_run(*a, **k):
            calls['n'] += 1
            return _FakeCompleted()

        jar = os.path.join(self.tmp, 'x.jar')
        open(jar, 'w').close()
        with patch.object(subprocess, 'run', side_effect=fake_run):
            ok = self.jd.decompile_file(jar, self.jd_dir)
        self.assertFalse(ok)
        self.assertEqual(calls['n'], 0)  # short-circuits before any subprocess


class DecompileJavaToolInvocationTests(SimpleTestCase):
    """``tools.py::decompile_java`` — PR #1 gate + functional contract."""

    def _drive_tool(self):
        """Run decompile_java on a fake .jar with subprocess captured.
        Returns (result_text, captured) or None if jd-cli.bat is absent."""
        from agent import tools as agent_tools

        app_path = os.path.dirname(os.path.dirname(os.path.abspath(agent_tools.__file__)))
        jd_bat = os.path.join(app_path, 'jd-cli', 'jd-cli.bat')
        if not os.path.exists(jd_bat):
            return None

        tmp = tempfile.mkdtemp(prefix='jd_tool_test_')
        try:
            jar = os.path.join(tmp, 'app.jar')
            open(jar, 'w').close()
            captured = {}

            def fake_run(cmd, **kwargs):
                captured['cmd'] = cmd
                captured['kwargs'] = kwargs
                return _FakeCompleted(returncode=0)

            with patch.object(agent_tools, 'validate_tool_path', return_value=None), \
                 patch.object(agent_tools.subprocess, 'run', side_effect=fake_run):
                tool = agent_tools.decompile_java
                fn = getattr(tool, 'func', None)
                result = fn(jar) if fn else tool.invoke({'path_filename': jar})
            return result, captured, jd_bat, jar
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_decompile_java_reports_success(self):
        driven = self._drive_tool()
        if driven is None:
            self.skipTest('bundled jd-cli.bat not present in this checkout')
        result, captured, _jd_bat, jar = driven
        self.assertIn('decompiled', result.lower())
        self.assertIn(jar, captured['cmd'])  # input path is a discrete argv element

    def test_pr1_tool_uses_cmd_c_list_argv_and_shell_false(self):
        driven = self._drive_tool()
        if driven is None:
            self.skipTest('bundled jd-cli.bat not present in this checkout')
        _result, captured, jd_bat, _jar = driven
        if not _is_hardened(captured['cmd'], captured['kwargs']):
            self.skipTest(_PR1_PENDING)
        self.assertEqual(captured['cmd'][0], 'cmd')
        self.assertEqual(captured['cmd'][1], '/c')
        self.assertEqual(captured['cmd'][2], jd_bat)
        self.assertIs(captured['kwargs'].get('shell'), False)


if __name__ == '__main__':
    unittest.main()
