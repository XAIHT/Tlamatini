# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Contract tests for the CONFIGURABLE WEB PORT — ``config.json`` → ``django_port``.

The web port is no longer hardcoded to 8000. ``manage.py`` reads ``django_port``
from ``config.json`` (``_resolve_django_port``) and applies it to EVERY launch path
(``_apply_configured_port``): the frozen double-click, the ``.flw`` association, the
frozen browser auto-open, source ``runserver``, and ``startserver``.

Two invariants these tests exist to protect:

  1. **Fail-open.** A missing / unreadable / out-of-range ``django_port`` must fall
     back to 8000 and NEVER stop the server from starting. A config typo must not
     brick the app.
  2. **The explicit CLI port always wins.** ``runserver 9100`` must never be
     second-guessed or double-appended by the injector.

``manage.py`` CANNOT be imported in a test process — it has module-level side effects
(console branding, the stdout/stderr tee, the Temp-dir pin). So, exactly like
``test_temp_dir_policy.py`` does, we treat its source as the contract: we lift the port
helpers out of the AST and exec those nodes alone in a clean namespace.

Run:
    python Tlamatini/manage.py test agent.test_django_port_config
    python -m unittest agent.test_django_port_config          # Django-free too
"""
import ast
import json
import os
import sys
import tempfile
import unittest

#   <repo>/Tlamatini/agent/test_django_port_config.py  ->  <repo>/Tlamatini
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANAGE_PY = os.path.join(_PROJECT_DIR, 'manage.py')
_CONFIG_JSON = os.path.join(_PROJECT_DIR, 'agent', 'config.json')

_WANTED_FUNCS = ('_resolve_config_path', '_resolve_django_port', '_apply_configured_port')
_DEFAULT_PORT = 8000


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _load_port_helpers():
    """Exec ONLY the port helpers out of manage.py — never import the module."""
    tree = ast.parse(_read(_MANAGE_PY), filename=_MANAGE_PY)
    picked = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANTED_FUNCS:
            picked.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == '_SERVER_COMMANDS' for t in node.targets
        ):
            picked.append(node)
    namespace = {'os': os, 'sys': sys}
    exec(compile(ast.Module(body=picked, type_ignores=[]), _MANAGE_PY, 'exec'), namespace)  # noqa: S102
    return namespace


class _PortHelperCase(unittest.TestCase):
    """Base: loads the helpers once and gives subclasses a temp config.json."""

    @classmethod
    def setUpClass(cls):
        cls.helpers = _load_port_helpers()
        for name in _WANTED_FUNCS:
            if name not in cls.helpers:
                raise AssertionError(
                    f"manage.py no longer defines {name}() — the configurable-port "
                    f"contract was removed or renamed. See docs/claude/architecture.md "
                    f"→ 'Configurable web port'."
                )

    def setUp(self):
        self._saved_config_path = os.environ.get('CONFIG_PATH')
        # tempfile.tempdir is pinned to <app>/Temp by manage.py/settings.py under the
        # Django runner, so this honors the Temp policy automatically.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._restore_config_path)

    def _restore_config_path(self):
        if self._saved_config_path is None:
            os.environ.pop('CONFIG_PATH', None)
        else:
            os.environ['CONFIG_PATH'] = self._saved_config_path

    def _write_config(self, raw_text=None, **keys):
        """Point CONFIG_PATH at a temp config.json holding *keys* (or raw text)."""
        path = os.path.join(self._tmp.name, 'config.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(raw_text if raw_text is not None else json.dumps(keys))
        os.environ['CONFIG_PATH'] = path
        return path

    def _resolve(self):
        return self.helpers['_resolve_django_port']()

    def _apply(self, argv):
        return self.helpers['_apply_configured_port'](list(argv))


class ConfigJsonDjangoPortContractTests(unittest.TestCase):
    """The shipped config.json must carry the key AND its self-documenting note."""

    def setUp(self):
        with open(_CONFIG_JSON, 'r', encoding='utf-8-sig') as fh:
            self.config = json.load(fh)

    def test_django_port_key_present_and_valid(self):
        self.assertIn('django_port', self.config,
                      "config.json must ship a 'django_port' key (default 8000).")
        port = self.config['django_port']
        self.assertIsInstance(port, int)
        self.assertTrue(1 <= port <= 65535)

    def test_shipped_default_is_8000(self):
        self.assertEqual(self.config['django_port'], _DEFAULT_PORT,
                         "The SHIPPED default must stay 8000 — users who never touch "
                         "config.json must keep the documented http://127.0.0.1:8000/.")

    def test_section_note_explains_the_winerror_10013_case(self):
        note = self.config.get('_section_django_port', '')
        self.assertTrue(note, "config.json must keep the '_section_django_port' explainer.")
        self.assertIn('10013', note)
        self.assertIn('8000', note)


class ResolveDjangoPortTests(_PortHelperCase):
    """_resolve_django_port(): reads the key, and FAILS OPEN on anything wrong."""

    def test_reads_a_configured_port(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._resolve(), 9000)

    def test_accepts_a_numeric_string(self):
        self._write_config(django_port='9100')
        self.assertEqual(self._resolve(), 9100)

    def test_tolerates_a_utf8_bom(self):
        self._write_config(raw_text='﻿{"django_port": 9200}')
        self.assertEqual(self._resolve(), 9200)

    def test_missing_key_falls_back_to_8000(self):
        self._write_config(chained_model='glm-5.2:cloud')
        self.assertEqual(self._resolve(), _DEFAULT_PORT)

    def test_missing_file_falls_back_to_8000(self):
        os.environ['CONFIG_PATH'] = os.path.join(self._tmp.name, 'nope.json')
        self.assertEqual(self._resolve(), _DEFAULT_PORT)

    def test_unparseable_json_falls_back_to_8000(self):
        self._write_config(raw_text='{ this is not json')
        self.assertEqual(self._resolve(), _DEFAULT_PORT)

    def test_non_numeric_port_falls_back_to_8000(self):
        self._write_config(django_port='not-a-port')
        self.assertEqual(self._resolve(), _DEFAULT_PORT)

    def test_out_of_range_ports_fall_back_to_8000(self):
        for bad in (0, -1, 65536, 999999):
            with self.subTest(port=bad):
                self._write_config(django_port=bad)
                self.assertEqual(self._resolve(), _DEFAULT_PORT)


class ApplyConfiguredPortTests(_PortHelperCase):
    """_apply_configured_port(): injects the port ONLY when the CLI omitted one."""

    def test_runserver_without_a_port_gets_the_configured_one(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._apply(['manage.py', 'runserver']),
                         ['manage.py', 'runserver', '9000'])

    def test_flags_are_not_mistaken_for_an_addrport(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._apply(['manage.py', 'runserver', '--noreload']),
                         ['manage.py', 'runserver', '--noreload', '9000'])

    def test_startserver_gets_the_configured_port_too(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._apply(['manage.py', 'startserver']),
                         ['manage.py', 'startserver', '9000'])

    def test_explicit_cli_port_always_wins(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._apply(['manage.py', 'runserver', '9100']),
                         ['manage.py', 'runserver', '9100'])

    def test_explicit_ipaddr_port_always_wins(self):
        self._write_config(django_port=9000)
        self.assertEqual(self._apply(['manage.py', 'runserver', '127.0.0.1:9100']),
                         ['manage.py', 'runserver', '127.0.0.1:9100'])

    def test_frozen_rewrite_is_never_double_appended(self):
        # The frozen block already appends an explicit 0.0.0.0:<port>.
        self._write_config(django_port=9000)
        frozen = ['manage.py', 'runserver', '--noreload', '0.0.0.0:9000']
        self.assertEqual(self._apply(frozen), frozen)

    def test_non_server_commands_are_untouched(self):
        self._write_config(django_port=9000)
        for argv in (['manage.py', 'migrate'],
                     ['manage.py', 'test', 'agent.test_django_port_config'],
                     ['manage.py', 'createsuperuser'],
                     ['manage.py']):
            with self.subTest(argv=argv):
                self.assertEqual(self._apply(argv), argv)

    def test_a_broken_config_still_yields_a_startable_argv(self):
        """Fail-open, end to end: a corrupt config must still boot on 8000."""
        self._write_config(raw_text='{ broken')
        self.assertEqual(self._apply(['manage.py', 'runserver']),
                         ['manage.py', 'runserver', '8000'])


class ManagePyWiringTests(unittest.TestCase):
    """Source contract: the launch paths must go THROUGH the resolver, not around it."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(_MANAGE_PY)

    def test_main_applies_the_configured_port(self):
        self.assertIn('sys.argv = _apply_configured_port(sys.argv)', self.src)

    def test_no_hardcoded_bind_address_survives(self):
        self.assertNotIn("'0.0.0.0:8000'", self.src)
        self.assertNotIn('"0.0.0.0:8000"', self.src)

    def test_frozen_paths_resolve_the_port(self):
        self.assertIn("f'0.0.0.0:{_resolve_django_port()}'", self.src)

    def test_browser_auto_open_uses_the_resolved_port(self):
        self.assertIn("f'http://localhost:{_resolve_django_port()}/'", self.src)
        self.assertNotIn("_schedule_browser_open('http://localhost:8000/'", self.src)

    def test_config_path_resolution_honors_the_env_override(self):
        self.assertIn("os.environ.get('CONFIG_PATH')", self.src)


if __name__ == '__main__':
    unittest.main()
