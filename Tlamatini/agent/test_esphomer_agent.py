# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the ESPHomer workflow agent and its surrounding infrastructure.

ESPHomer bridges Tlamatini to **ESPHome** (https://esphome.io) — smart-home device
firmware from a SIMPLE YAML config (no C++). Like ESP32er (PlatformIO) and Arduiner
(arduino-cli), ESPHome ships a complete `esphome` CLI, so ESPHomer invokes `esphome`
subcommands DIRECTLY using only the stdlib (``subprocess`` + ``glob`` + ``json`` +
``threading``). It is a standalone pool agent under ``agent/agents/esphomer/`` loaded
here through ``importlib.util.spec_from_file_location`` with a cwd + logging-handler
save/restore so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` /
``logging.basicConfig`` side effects do not leak into the test process.

No ESPHome install, no board and no network are required: a tiny FAKE `esphome` (a
pure-stdlib temp Python script) answers `version` / `config <f>` / `compile <f>` /
`clean <f>` / `upload` / `logs` exactly as the real CLI would, and is invoked through
the REAL ``_esphome`` / ``_run_action`` / ``_preflight`` helpers via an explicit
``esphome_cmd = [sys.executable, fake_esphome]`` — so the genuine subprocess +
capture + fail-safe-gating code paths are exercised deterministically.
"""

import importlib.util
import logging
import os
import sys
import tempfile
import textwrap
import unittest
from functools import lru_cache
from unittest.mock import patch

import yaml


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_esphomer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'esphomer', 'esphomer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_esphomer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load ESPHomer module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


ESP = _load_esphomer_module()


class _LogCapture:
    """Context manager that captures root-logger messages into a list."""

    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self._handler = _H()
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *_a):
        logging.getLogger().removeHandler(self._handler)
        return False


# A tiny FAKE `esphome`. Pure stdlib; mimics the ESPHome CLI surface ESPHomer uses.
# Invoked through the REAL helpers as [sys.executable, <this file>, *args]. Reads env
# knob FAKE_ESPHOME_RC (rc for config/compile/upload/logs; default 0).
_FAKE_ESPHOME = textwrap.dedent(r'''
    import sys, os

    args = sys.argv[1:]

    def out(s):
        sys.stdout.write(s + "\n")

    rc = int(os.environ.get("FAKE_ESPHOME_RC", "0"))

    if args[:1] == ["version"]:
        out("Version: 2026.4.5")
        sys.exit(0)
    if args[:1] == ["config"]:
        out("INFO Configuration is valid!")
        sys.exit(rc)
    if args[:1] == ["compile"]:
        out("INFO Successfully compiled program.")
        out("Linking .esphome/build/dev/.pioenvs/dev/firmware.elf")
        sys.exit(rc)
    if args[:1] == ["clean"]:
        out("INFO Done.")
        sys.exit(rc)
    if args[:1] == ["upload"]:
        out("INFO Successfully uploaded program.")
        sys.exit(rc)
    if args[:1] == ["logs"]:
        out("[logs] booting tlamatini device")
        sys.exit(rc)
    out("unknown: " + " ".join(args))
    sys.exit(2)
''').strip()


def _write_fake_esphome(tmpdir):
    path = os.path.join(tmpdir, 'fake_esphome.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_FAKE_ESPHOME)
    return [sys.executable, path]


# ---------------------------------------------------------------------------
# Action-set / helper tests (pure, no subprocess)
# ---------------------------------------------------------------------------


class ActionSetTests(unittest.TestCase):
    def test_all_actions_partition(self):
        # Every advertised action is in exactly one (or the union) of the sets.
        self.assertIn('compile', ESP._ALL_ACTIONS)
        self.assertIn('upload', ESP._ALL_ACTIONS)
        self.assertIn('new_config', ESP._ALL_ACTIONS)
        self.assertIn('scaffold_compile_upload', ESP._ALL_ACTIONS)
        self.assertIn('logs', ESP._ALL_ACTIONS)

    def test_hardware_actions(self):
        self.assertEqual(ESP._HARDWARE_ACTIONS, ESP._UPLOAD_ACTIONS | ESP._LOG_ACTIONS)
        self.assertIn('upload', ESP._HARDWARE_ACTIONS)
        self.assertIn('logs', ESP._HARDWARE_ACTIONS)
        self.assertNotIn('compile', ESP._HARDWARE_ACTIONS)

    def test_file_actions_are_stdlib_only(self):
        for a in ('new_config', 'write_config', 'read_config', 'list_artifacts'):
            self.assertIn(a, ESP._FILE_ACTIONS)


class CoercionHelperTests(unittest.TestCase):
    def test_cfg_none_to_default(self):
        self.assertEqual(ESP._cfg({'a': None}, 'a', 'x'), 'x')
        self.assertEqual(ESP._cfg({'a': 'v'}, 'a', 'x'), 'v')

    def test_as_int(self):
        self.assertEqual(ESP._as_int('7', 1), 7)
        self.assertEqual(ESP._as_int('nope', 3), 3)
        self.assertEqual(ESP._as_int(True, 3), 3)

    def test_as_bool(self):
        self.assertTrue(ESP._as_bool('yes', False))
        self.assertFalse(ESP._as_bool('off', True))
        self.assertTrue(ESP._as_bool(None, True))

    def test_ok_and_wrap(self):
        self.assertTrue(ESP._ok({'ok': True}))
        self.assertFalse(ESP._ok({'ok': False}))
        self.assertFalse(ESP._ok({'error': 'x'}))
        self.assertTrue(ESP._ok({'stdout': 'fine'}))
        w = ESP._wrap('t', {'ok': True})
        self.assertEqual(w['tool'], 't')
        self.assertTrue(w['ok'])

    def test_slug(self):
        self.assertEqual(ESP._slug('Tlamatini Light!'), 'tlamatini-light')
        self.assertEqual(ESP._slug('   '), 'tlamatini-device')

    def test_is_ota_target(self):
        self.assertTrue(ESP._is_ota_target('192.168.1.4'))
        self.assertTrue(ESP._is_ota_target('device.local'))
        self.assertFalse(ESP._is_ota_target('COM5'))
        self.assertFalse(ESP._is_ota_target('/dev/ttyUSB0'))
        self.assertFalse(ESP._is_ota_target(''))


# ---------------------------------------------------------------------------
# Config-file ops
# ---------------------------------------------------------------------------


class ConfigFileOpsTests(unittest.TestCase):
    def test_new_config_generates_valid_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'light.yaml')
            res = ESP._new_config({
                'config_path': path, 'name': 'My Light', 'platform': 'esp32',
                'board': 'esp32dev', 'led_pin': 'GPIO2',
            })
            self.assertTrue(res['ok'], res)
            self.assertTrue(os.path.exists(path))
            doc = yaml.safe_load(open(path, encoding='utf-8'))
            self.assertEqual(doc['esphome']['name'], 'my-light')
            self.assertIn('esp32', doc)
            self.assertEqual(doc['esp32']['board'], 'esp32dev')
            self.assertIn('api', doc)
            self.assertIn('wifi', doc)
            self.assertEqual(doc['light'][0]['platform'], 'binary')

    def test_new_config_rejects_unknown_platform(self):
        res = ESP._new_config({'platform': 'bogus'})
        self.assertFalse(res['ok'])

    def test_new_config_defaults_to_templates_root(self):
        """No config_path -> scaffold under <app>/Templates (TLAMATINI_TEMPLATES),
        the deliverable location exported by the core (manage.py / settings.py) and
        inherited by every spawned agent. NEVER os.getcwd() (the pool dir, which in
        a frozen build lives inside the possibly read-only install tree)."""
        with tempfile.TemporaryDirectory() as d:
            templates = os.path.join(d, 'Templates')
            with patch.dict(os.environ, {'TLAMATINI_TEMPLATES': templates}):
                res = ESP._new_config({'name': 'Front Lamp', 'platform': 'esp32'})
            self.assertTrue(res['ok'], res)
            expected = os.path.join(templates, 'front-lamp', 'front-lamp.yaml')
            self.assertEqual(os.path.normcase(res['config_path']),
                             os.path.normcase(expected))
            self.assertTrue(os.path.exists(expected))

    def test_new_config_failopen_to_cwd_without_templates_env(self):
        """TLAMATINI_TEMPLATES unset (agent launched fully standalone) -> fail-open
        to os.getcwd() so a generated device still lands somewhere writable rather
        than crashing."""
        saved_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                with patch.dict(os.environ):
                    os.environ.pop('TLAMATINI_TEMPLATES', None)
                    res = ESP._new_config({'name': 'standalone-dev', 'platform': 'esp32'})
                self.assertTrue(res['ok'], res)
                expected = os.path.join(os.getcwd(), 'standalone-dev', 'standalone-dev.yaml')
                self.assertEqual(os.path.normcase(res['config_path']),
                                 os.path.normcase(expected))
                self.assertTrue(os.path.exists(expected))
            finally:
                os.chdir(saved_cwd)

    def test_esphome_lib_dir_is_per_user_localappdata(self):
        """ESPHome installs to a per-user dir OUTSIDE the install tree (like ESP32er /
        Arduiner) so it survives self-update + works in a read-only install."""
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\\Users\\x\\AppData\\Local"}):
            d = ESP._esphome_lib_dir()
        self.assertTrue(d.replace("\\", "/").endswith("Tlamatini/esphome-lib"), d)

    def test_env_with_esphome_lib_prepends_pythonpath(self):
        base = {"PYTHONPATH": os.path.join("X", "existing")}
        e = ESP._env_with_esphome_lib(base)
        parts = e["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(parts[0], ESP._esphome_lib_dir())
        self.assertIn(os.path.join("X", "existing"), parts)
        self.assertEqual(base["PYTHONPATH"], os.path.join("X", "existing"))

    def test_env_with_esphome_lib_sets_pythonpath_when_absent(self):
        e = ESP._env_with_esphome_lib({})
        self.assertEqual(e["PYTHONPATH"], ESP._esphome_lib_dir())

    def test_write_then_read_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'dev.yaml')
            body = 'esphome:\n  name: x\n'
            w = ESP._write_config({'config_path': path, 'content': body})
            self.assertTrue(w['ok'])
            r = ESP._read_config({'config_path': path})
            self.assertTrue(r['ok'])
            self.assertEqual(r['stdout'], body)

    def test_write_config_requires_content(self):
        res = ESP._write_config({'config_path': 'x.yaml', 'content': ''})
        self.assertFalse(res['ok'])


# ---------------------------------------------------------------------------
# CLI routing through the FAKE esphome
# ---------------------------------------------------------------------------


class CliRoutingTests(unittest.TestCase):
    def test_version_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = _write_fake_esphome(d)
            ok, text = ESP._esphome_version(cmd, os.environ.copy())
            self.assertTrue(ok)
            self.assertIn('2026', text)

    def test_resolve_explicit_executable(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = _write_fake_esphome(d)
            # explicit single-string executable won't run as python; instead verify
            # _resolve falls through to `python -m esphome` only when present. Here we
            # just assert the resolver returns [] when nothing is usable.
            resolved = ESP._resolve_esphome_cmd(
                {'esphome_executable': os.path.join(d, 'nope')},
                {'PATH': ''}, ['this-python-does-not-exist'])
            self.assertEqual(resolved, [])
            # And that a working candidate resolves.
            ok, _ = ESP._esphome_version(cmd, os.environ.copy())
            self.assertTrue(ok)

    def test_compile_routes(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = _write_fake_esphome(d)
            cfg = os.path.join(d, 'dev.yaml')
            open(cfg, 'w').write('esphome:\n  name: dev\n')
            env = dict(os.environ, FAKE_ESPHOME_RC='0')
            res = ESP._run_action('compile', {'config_path': cfg}, cmd, env, 60)
            self.assertTrue(res['ok'])
            self.assertIn('compiled', res['result']['stdout'].lower())

    def test_compile_nonzero_rc(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = _write_fake_esphome(d)
            cfg = os.path.join(d, 'dev.yaml')
            open(cfg, 'w').write('esphome:\n  name: dev\n')
            env = dict(os.environ, FAKE_ESPHOME_RC='1')
            res = ESP._run_action('compile', {'config_path': cfg}, cmd, env, 60)
            self.assertFalse(res['ok'])


# ---------------------------------------------------------------------------
# Preflight fail-safe gating
# ---------------------------------------------------------------------------


class PreflightTests(unittest.TestCase):
    def test_no_esphome_is_fatal(self):
        pf = ESP._preflight('compile', {'config_path': 'x.yaml'}, [])
        self.assertFalse(pf['ok'])
        self.assertTrue(any('NOT resolvable' in f for f in pf['fatals']))

    def test_compile_needs_config(self):
        pf = ESP._preflight('compile', {'config_path': ''}, ['esphome'])
        self.assertFalse(pf['ok'])

    def test_upload_needs_serial_or_ota(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, 'dev.yaml')
            open(cfg, 'w').write('esphome:\n  name: dev\nesp32:\n  board: esp32dev\n')
            with patch.object(ESP, '_enumerate_serial_ports', return_value=[]):
                pf = ESP._preflight('upload', {'config_path': cfg, 'port': ''}, ['esphome'])
                self.assertFalse(pf['ok'])
            # An OTA host satisfies the hardware requirement (no serial needed).
            pf2 = ESP._preflight('upload', {'config_path': cfg, 'port': '192.168.1.9'}, ['esphome'])
            self.assertTrue(pf2['ok'], pf2)

    def test_compile_ok_when_config_present(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, 'dev.yaml')
            open(cfg, 'w').write('esphome:\n  name: dev\n')
            pf = ESP._preflight('compile', {'config_path': cfg}, ['esphome'])
            self.assertTrue(pf['ok'], pf)


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


class EmitSectionTests(unittest.TestCase):
    def test_single_atomic_block(self):
        with _LogCapture() as cap:
            ESP._emit_section({'action': 'compile', 'ok': 'true'}, 'body text')
        blocks = [m for m in cap.records if m.startswith('INI_SECTION_ESPHOMER<<<')]
        self.assertEqual(len(blocks), 1)
        self.assertIn('>>>END_SECTION_ESPHOMER', blocks[0])
        self.assertIn('action: compile', blocks[0])
        self.assertIn('body text', blocks[0])


# ---------------------------------------------------------------------------
# Registration / integration (no DB needed)
# ---------------------------------------------------------------------------


class RegistrationTests(unittest.TestCase):
    def test_wrapped_chat_agent_spec(self):
        from agent import chat_agent_registry as reg
        spec = reg.WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_esphomer')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, 'ESPHomer')
        self.assertEqual(spec.template_dir, 'esphomer')

    def test_parametrizer_output_fields(self):
        from agent.services import agent_contracts
        self.assertIn('esphomer', agent_contracts._PARAMETRIZER_OUTPUT_FIELDS)
        fields = agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['esphomer']
        self.assertIn('config_path', fields)
        self.assertIn('response_body', fields)

    def test_migrations_present(self):
        mig_dir = os.path.join(os.path.dirname(__file__), 'migrations')
        for fname in ('0138_add_esphomer.py',
                      '0139_add_chat_agent_esphomer_tool.py',
                      '0140_add_esphomer_demo_prompts.py'):
            self.assertTrue(os.path.exists(os.path.join(mig_dir, fname)), fname)

    def test_config_yaml_defaults(self):
        cfg_path = os.path.join(os.path.dirname(__file__), 'agents', 'esphomer', 'config.yaml')
        cfg = yaml.safe_load(open(cfg_path, encoding='utf-8'))
        self.assertEqual(cfg['action'], 'validate')
        self.assertTrue(cfg['auto_bootstrap'])
        self.assertIn('target_agents', cfg)


if __name__ == '__main__':
    unittest.main()
