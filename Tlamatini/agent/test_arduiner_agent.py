"""Automated tests for the Arduiner workflow agent and its surrounding infrastructure.

Arduiner bridges Tlamatini to the **Arduino CLI** (https://arduino.github.io/arduino-cli/).
Like ESP32er (PlatformIO `pio`) and unlike STM32er (an MCP stdio server), arduino-cli
is itself a complete CLI, so Arduiner invokes `arduino-cli` subcommands DIRECTLY (the
Kalier / Executer / ESP32er pattern) using only the stdlib (``subprocess`` + ``urllib`` +
``zipfile`` + ``tarfile`` + ``json`` + ``threading``). It is a standalone pool agent under
``agent/agents/arduiner/`` loaded here through ``importlib.util.spec_from_file_location``
with a cwd + logging-handler save/restore so its module-level ``os.chdir`` /
``open(LOG_FILE_PATH)`` / ``logging.basicConfig`` side effects do not leak.

No arduino-cli install, no Arduino hardware and no network are required: a tiny FAKE
`arduino-cli` (a pure-stdlib temp Python script) answers `version` / `version --json` /
`board list --json` / `core list --json` / `core install` / `compile` / `sketch new`
exactly as the real CLI would, and is invoked through the REAL ``_cli`` / ``_run_action`` /
``_preflight`` / ``_ensure_core_installed`` helpers via an explicit
``cli_cmd = [sys.executable, fake_cli]`` — so the genuine subprocess + capture +
fail-safe-gating code paths are exercised deterministically.

Covers:
- Action sets: _ALL_ACTIONS / _HARDWARE_ACTIONS / _FILE_ACTIONS / _BUILD_ACTIONS / _MANAGE_ACTIONS
- Helpers: _cfg / _as_int / _as_bool / _fqbn_platform_id / _fqbn_looks_valid /
  _additional_urls_args / _ok / _wrap
- File ops: _write_source / _read_source / _list_sources (round-trip + path-escape)
- _create_project from the bundled ArduinoTemplateProject (rename .ino, stamp sketch.yaml)
- _ensure_core_installed: already-present / auto-install / refusal when auto_core_install off
- _cli / _run_action routing against the FAKE cli (build / device_list / system_info / core_list)
- _probe_serial: JSON parse, Arduino USB-VID detection, matched-FQBN, no-port / cli-error
- _preflight fail-safe gating: no cli -> fatal; build needs a sketch -> fatal; build needs
  fqbn -> fatal; upload needs a serial port -> fatal; bad FQBN -> warning never refuses
- _bounded_monitor: drains a streaming child for monitor_seconds then terminates it
- _emit_section: single atomic INI_SECTION_ARDUINER block
- main() end-stage: section always emitted + target_agents always started, on a successful
  device_list run AND on the preflight-refused path
- Registry integration: ChatWrappedAgentSpec, Exec Report row, agent contract +
  parametrizer fields, name normalization, config.yaml defaults, config.json globals,
  CSS gradient (unique), URL route, migration presence (0109 + 0110), bundled template
"""

import importlib.util
import io
import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import textwrap
import unittest
import zipfile
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_arduiner_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'arduiner', 'arduiner.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_arduiner_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Arduiner module from {module_path}')

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


# A tiny FAKE `arduino-cli`. Pure stdlib; mimics the surface Arduiner uses. Invoked
# through the REAL helpers as [sys.executable, <this file>, *args]. Reads env knobs
# FAKE_CLI_PORTS (board-list JSON), FAKE_CLI_CORES (installed-core ids), FAKE_CLI_CORE_RC
# (core install rc) and FAKE_CLI_COMPILE_RC (compile rc).
_FAKE_CLI = textwrap.dedent(r'''
    import sys, os, json

    args = sys.argv[1:]

    def out(s):
        sys.stdout.write(s + "\n")

    if args[:1] == ["version"] and "--json" not in args:
        out("arduino-cli  Version: 1.5.0 Commit: deadbeef Date: 2026-01-01")
        sys.exit(0)
    if args[:1] == ["version"]:
        out(json.dumps({"VersionString": "1.5.0", "Commit": "deadbeef"}))
        sys.exit(0)
    if args[:2] == ["board", "list"]:
        ports = json.loads(os.environ.get("FAKE_CLI_PORTS", "[]"))
        out(json.dumps({"detected_ports": ports}))
        sys.exit(0)
    if args[:2] == ["board", "search"]:
        out(json.dumps({"boards": []}))
        sys.exit(0)
    if args[:2] == ["core", "list"]:
        cores = json.loads(os.environ.get("FAKE_CLI_CORES", "[]"))
        out(json.dumps({"platforms": [{"id": c, "installed_version": "1.0.0"} for c in cores]}))
        sys.exit(0)
    if args[:2] == ["core", "search"]:
        out(json.dumps({"platforms": []}))
        sys.exit(0)
    if args[:2] == ["core", "update-index"]:
        out("Downloading index: package_index.tar.bz2 downloaded")
        sys.exit(0)
    if args[:2] == ["core", "install"]:
        rc = int(os.environ.get("FAKE_CLI_CORE_RC", "0"))
        if rc == 0:
            out("Platform %s installed" % (args[2] if len(args) > 2 else "?"))
        else:
            sys.stderr.write("Error: platform not found\n")
        sys.exit(rc)
    if args[:2] in (["core", "uninstall"], ["lib", "install"], ["lib", "update-index"]):
        out("ok")
        sys.exit(0)
    if args[:2] == ["lib", "list"] or args[:2] == ["lib", "search"]:
        out(json.dumps({"installed_libraries": []}))
        sys.exit(0)
    if args[:2] == ["config", "init"]:
        out("Config written")
        sys.exit(0)
    if args[:1] == ["compile"]:
        rc = int(os.environ.get("FAKE_CLI_COMPILE_RC", "0"))
        if rc == 0:
            out("Sketch uses 924 bytes (2%) of program storage space.")
            out("Global variables use 9 bytes (0%) of dynamic memory.")
            sys.exit(0)
        sys.stderr.write("Error during build: exit status 1\n")
        sys.exit(rc)
    if args[:2] == ["sketch", "new"]:
        out("Sketch created in: %s" % (args[2] if len(args) > 2 else "?"))
        sys.exit(0)
    sys.stderr.write("unknown command: %r\n" % (args,))
    sys.exit(2)
''')


def _write_fake_cli(tmpdir):
    path = os.path.join(tmpdir, 'fake_arduino_cli.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_FAKE_CLI)
    return path


def _fake_cli_cmd(tmpdir):
    return [sys.executable, _write_fake_cli(tmpdir)]


def _make_sketch(tmpdir, name='blink', with_ino=True):
    sketch = os.path.join(tmpdir, name)
    os.makedirs(sketch, exist_ok=True)
    if with_ino:
        with open(os.path.join(sketch, f'{name}.ino'), 'w', encoding='utf-8') as f:
            f.write("void setup(){}\nvoid loop(){}\n")
    return sketch


def _port_row(address="COM5", vid="0x2341", fqbn="arduino:avr:uno"):
    return {
        "port": {"address": address, "protocol": "serial",
                 "properties": {"vid": vid, "pid": "0x0043"}},
        "matching_boards": [{"name": "Arduino Uno", "fqbn": fqbn}],
    }


# ===========================================================================
# Pure helpers + action contract
# ===========================================================================


class ArduinerHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_arduiner_module()

    def test_action_sets(self):
        m = self.mod
        for action in ("bootstrap", "validate", "system_info", "boards", "device_list",
                       "core_update_index", "core_search", "core_list", "core_install",
                       "core_uninstall", "lib_update_index", "lib_search", "lib_list",
                       "lib_install", "create_project", "write_source", "read_source",
                       "list_sources", "build", "clean", "upload", "build_and_upload",
                       "list_artifacts", "monitor", "monitor_session"):
            self.assertIn(action, m._ALL_ACTIONS, action)
        self.assertEqual(m._HARDWARE_ACTIONS, {"upload", "build_and_upload", "monitor", "monitor_session"})
        self.assertEqual(m._FILE_ACTIONS, {"write_source", "read_source", "list_sources"})
        self.assertIn("core_install", m._MANAGE_ACTIONS)

    def test_coercion_helpers(self):
        m = self.mod
        self.assertEqual(m._cfg({"a": None}, "a", "x"), "x")
        self.assertEqual(m._as_int("8", 1), 8)
        self.assertEqual(m._as_int("nope", 4), 4)
        self.assertTrue(m._as_bool("yes", False))
        self.assertFalse(m._as_bool("", True))  # '' -> False

    def test_fqbn_helpers(self):
        m = self.mod
        self.assertEqual(m._fqbn_platform_id("arduino:avr:uno"), "arduino:avr")
        self.assertEqual(m._fqbn_platform_id("esp32:esp32:esp32:FlashSize=4M"), "esp32:esp32")
        self.assertEqual(m._fqbn_platform_id("nonsense"), "")
        self.assertTrue(m._fqbn_looks_valid("arduino:avr:uno"))
        self.assertTrue(m._fqbn_looks_valid("arduino:avr:nano:cpu=atmega328"))
        self.assertFalse(m._fqbn_looks_valid("arduino:avr"))
        self.assertFalse(m._fqbn_looks_valid(""))

    def test_additional_urls_args(self):
        m = self.mod
        self.assertEqual(m._additional_urls_args({"additional_urls": ""}), [])
        a = m._additional_urls_args({"additional_urls": "http://a/x.json http://b/y.json"})
        self.assertEqual(a[0], "--additional-urls")
        self.assertIn("http://a/x.json", a[1])
        self.assertIn("http://b/y.json", a[1])

    def test_ok_and_wrap(self):
        m = self.mod
        self.assertTrue(m._ok({"ok": True}))
        self.assertFalse(m._ok({"ok": False}))
        self.assertFalse(m._ok({"error": "x"}))
        self.assertTrue(m._ok({"stdout": "hi"}))
        env = m._wrap("compile", {"ok": True, "returncode": 0})
        self.assertEqual(env["tool"], "compile")
        self.assertTrue(env["ok"])

    def test_file_ops_roundtrip(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            sketch = _make_sketch(tmp)
            w = m._write_source({"sketch_path": sketch, "rel_path": "blink.ino",
                                 "content": "void setup(){} void loop(){}"})
            self.assertTrue(w["ok"], w)
            r = m._read_source({"sketch_path": sketch, "rel_path": "blink.ino"})
            self.assertTrue(r["ok"])
            self.assertIn("void setup", r["stdout"])
            ls = m._list_sources({"sketch_path": sketch})
            self.assertTrue(ls["ok"])
            self.assertIn("blink.ino", ls["stdout"])

    def test_write_source_rejects_escape(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            sketch = _make_sketch(tmp)
            bad = m._write_source({"sketch_path": sketch, "rel_path": "../escape.txt", "content": "x"})
            self.assertFalse(bad["ok"])
            self.assertIn("escape", bad["error"].lower())

    def test_create_project_from_template(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "myblink")
            res = m._create_project(
                {"sketch_path": dest, "fqbn": "arduino:avr:uno", "port": "COM3"},
                ["nonexistent-cli"], os.environ.copy(), 60,
            )
            self.assertTrue(res["ok"], res)
            # The primary .ino was renamed to match the destination folder.
            self.assertTrue(os.path.exists(os.path.join(dest, "myblink.ino")))
            # The multi-file src/ helper was copied.
            self.assertTrue(os.path.exists(os.path.join(dest, "src", "Heartbeat.h")))
            # sketch.yaml was stamped with the FQBN.
            with open(os.path.join(dest, "sketch.yaml"), encoding="utf-8") as f:
                sk = yaml.safe_load(f)
            self.assertEqual(sk["default_fqbn"], "arduino:avr:uno")
            self.assertEqual(sk["default_port"], "COM3")

    def test_emit_section_atomic(self):
        m = self.mod
        with _LogCapture() as cap:
            m._emit_section({"action": "build", "ok": "true"}, "body text")
        blocks = [r for r in cap.records if "INI_SECTION_ARDUINER<<<" in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn(">>>END_SECTION_ARDUINER", blocks[0])
        self.assertIn("action: build", blocks[0])


# ===========================================================================
# arduino-cli invocation + preflight against the FAKE cli
# ===========================================================================


class ArduinerCliTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_arduiner_module()

    def test_cli_system_info(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            out = m._run_action("system_info", {}, cli, os.environ.copy(), 60)
            self.assertTrue(out["ok"], out)
            self.assertIn("1.5.0", out["result"]["stdout"])

    def test_run_action_build_autoinstalls_core(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            # No cores installed -> auto_core_install drives `core install`, then compile.
            env = dict(os.environ, FAKE_CLI_CORES="[]")
            out = m._run_action("build", {"sketch_path": sketch, "fqbn": "arduino:avr:uno",
                                          "auto_core_install": True}, cli, env, 120)
            self.assertTrue(out["ok"], out)
            self.assertIn("program storage", out["result"]["stdout"])

    def test_run_action_build_core_present(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            env = dict(os.environ, FAKE_CLI_CORES='["arduino:avr"]')
            out = m._run_action("build", {"sketch_path": sketch, "fqbn": "arduino:avr:uno"},
                                cli, env, 120)
            self.assertTrue(out["ok"], out)

    def test_build_refused_when_core_missing_and_autoinstall_off(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            env = dict(os.environ, FAKE_CLI_CORES="[]")
            out = m._run_action("build", {"sketch_path": sketch, "fqbn": "arduino:avr:uno",
                                          "auto_core_install": False}, cli, env, 120)
            self.assertFalse(out["ok"])
            self.assertIn("core", out["result"]["error"].lower())

    def test_run_action_build_failure_is_routable(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            env = dict(os.environ, FAKE_CLI_CORES='["arduino:avr"]', FAKE_CLI_COMPILE_RC="1")
            out = m._run_action("upload", {"sketch_path": sketch, "fqbn": "arduino:avr:uno",
                                           "port": "COM5"}, cli, env, 120)
            self.assertFalse(out["ok"])
            self.assertEqual(out["result"]["returncode"], 1)

    def test_run_action_device_list(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            env = dict(os.environ, FAKE_CLI_PORTS=json.dumps([_port_row("COM5")]))
            out = m._run_action("device_list", {}, cli, env, 60)
            self.assertTrue(out["ok"])
            self.assertIn("COM5", out["result"]["stdout"])

    def test_ensure_core_installed_already_present(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            env = dict(os.environ, FAKE_CLI_CORES='["arduino:avr"]')
            res = m._ensure_core_installed({"fqbn": "arduino:avr:uno"}, cli, env, 60)
            self.assertTrue(res["ensured"])
            self.assertFalse(res["installed_now"])

    def test_probe_serial_detects_arduino_vid_and_fqbn(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            env = dict(os.environ, FAKE_CLI_PORTS=json.dumps([_port_row("COM7", "0x2341")]))
            res = m._probe_serial(cli, env)
            self.assertTrue(res["present"])
            self.assertTrue(res["arduino_like"])
            self.assertIn("COM7", res["ports"])
            self.assertIn("arduino:avr:uno", res["matched_fqbns"])

    def test_probe_serial_no_ports(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            env = dict(os.environ, FAKE_CLI_PORTS="[]")
            res = m._probe_serial(cli, env)
            self.assertFalse(res["present"])
            self.assertTrue(res["cli_ok"])

    def test_preflight_no_cli_is_fatal(self):
        m = self.mod
        pf = m._preflight("build", {"sketch_path": "x", "fqbn": "arduino:avr:uno"}, [], os.environ.copy())
        self.assertFalse(pf["ok"])
        self.assertTrue(any("arduino-cli" in f.lower() for f in pf["fatals"]))

    def test_preflight_build_needs_sketch(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            empty = _make_sketch(tmp, "empty", with_ino=False)
            pf = m._preflight("build", {"sketch_path": empty, "fqbn": "arduino:avr:uno"},
                              cli, os.environ.copy())
            self.assertFalse(pf["ok"])
            self.assertTrue(any(".ino" in f for f in pf["fatals"]))

    def test_preflight_build_needs_fqbn(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            pf = m._preflight("build", {"sketch_path": sketch, "fqbn": ""}, cli, os.environ.copy())
            self.assertFalse(pf["ok"])
            self.assertTrue(any("fqbn" in f.lower() for f in pf["fatals"]))

    def test_preflight_build_ok(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            pf = m._preflight("build", {"sketch_path": sketch, "fqbn": "arduino:avr:uno"},
                              cli, os.environ.copy())
            self.assertTrue(pf["ok"], pf["fatals"])

    def test_preflight_upload_needs_serial(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            env = dict(os.environ, FAKE_CLI_PORTS="[]")
            pf = m._preflight("upload", {"sketch_path": sketch, "fqbn": "arduino:avr:uno"}, cli, env)
            self.assertFalse(pf["ok"])
            self.assertTrue(any("serial port" in f.lower() for f in pf["fatals"]))

    def test_preflight_upload_ok_with_port(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            env = dict(os.environ, FAKE_CLI_PORTS=json.dumps([_port_row("COM5")]))
            pf = m._preflight("upload", {"sketch_path": sketch, "fqbn": "arduino:avr:uno"}, cli, env)
            self.assertTrue(pf["ok"], pf["fatals"])

    def test_preflight_bad_fqbn_warns_not_refuses(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            sketch = _make_sketch(tmp)
            pf = m._preflight("build", {"sketch_path": sketch, "fqbn": "justuno"}, cli, os.environ.copy())
            self.assertTrue(pf["ok"])  # warning, not refusal
            self.assertTrue(any("VENDOR:ARCH:BOARD" in w for w in pf["warnings"]))

    def test_bounded_monitor_drains_then_terminates(self):
        m = self.mod
        # A fake "monitor" that streams a few lines forever, drained for 1s then killed.
        with tempfile.TemporaryDirectory() as tmp:
            streamer = os.path.join(tmp, "streamer.py")
            with open(streamer, "w", encoding="utf-8") as f:
                f.write(textwrap.dedent(r'''
                    import sys, time
                    # ignore all args; just stream
                    for i in range(100000):
                        sys.stdout.write("[heartbeat] beat #%d\n" % i)
                        sys.stdout.flush()
                        time.sleep(0.05)
                '''))
            cli = [sys.executable, streamer]
            res = m._bounded_monitor(cli, {"monitor_seconds": 1, "baud": 115200}, os.environ.copy())
            self.assertTrue(res["ok"])
            self.assertIn("heartbeat", res["stdout"])


# ===========================================================================
# main() end-stage — section ALWAYS emitted + target_agents ALWAYS started
# ===========================================================================


class ArduinerMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_arduiner_module()

    def _run_main(self, config, cli_cmd, extra_env=None):
        m = self.mod
        started = []
        env = dict(os.environ, **(extra_env or {}))
        with _LogCapture() as cap, \
                patch.object(m, "load_config", return_value=config), \
                patch.object(m, "write_pid_file"), patch.object(m, "remove_pid_file"), \
                patch.object(m, "get_agent_env", return_value=env), \
                patch.object(m, "_resolve_cli_cmd", return_value=cli_cmd), \
                patch.object(m, "wait_for_agents_to_stop"), \
                patch.object(m, "start_agent", side_effect=lambda n: started.append(n) or True):
            with self.assertRaises(SystemExit):
                m.main()
        sections = [r for r in cap.records if "INI_SECTION_ARDUINER<<<" in r]
        return sections, started

    def test_main_device_list_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            cfg = {"action": "device_list", "auto_bootstrap": False, "preflight": True,
                   "target_agents": ["parametrizer_1"]}
            sections, started = self._run_main(
                cfg, cli, {"FAKE_CLI_PORTS": json.dumps([_port_row("COM5")])})
        self.assertEqual(len(sections), 1)
        self.assertIn("success: true", sections[0])
        self.assertEqual(started, ["parametrizer_1"])

    def test_main_preflight_refused_still_emits_and_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = _fake_cli_cmd(tmp)
            # build with NO sketch_path -> preflight fatal (no .ino).
            cfg = {"action": "build", "auto_bootstrap": False, "preflight": True,
                   "sketch_path": "", "fqbn": "arduino:avr:uno", "target_agents": ["ender_1"]}
            sections, started = self._run_main(cfg, cli)
        self.assertEqual(len(sections), 1)
        self.assertIn("success: false", sections[0])
        self.assertIn("PREFLIGHT REFUSED", sections[0])
        self.assertEqual(started, ["ender_1"])


# ===========================================================================
# Registry / integration wiring (no agent subprocess)
# ===========================================================================


class ArduinerIntegrationTests(SimpleTestCase):
    def test_wrapped_spec(self):
        from agent.chat_agent_registry import (
            WRAPPED_CHAT_AGENT_BY_TOOL_NAME, WRAPPED_CHAT_AGENT_MAP,
        )
        self.assertIn("arduiner", WRAPPED_CHAT_AGENT_MAP)
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_arduiner"]
        self.assertEqual(spec.display_name, "Arduiner")
        self.assertEqual(spec.template_dir, "arduiner")
        self.assertTrue(spec.long_running)

    def test_exec_report_row(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS["chat_agent_arduiner"], ("arduiner", "Arduiner"))

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS["arduiner"]
        for key in ("action", "tool", "ok", "returncode", "success", "fqbn",
                    "port", "sketch_path", "stage", "response_body"):
            self.assertIn(key, fields)

    def test_display_name_normalization(self):
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertEqual(display_name_from_agent_type("arduiner"), "Arduiner")

    def test_parametrizer_section_type(self):
        path = os.path.join(os.path.dirname(__file__), "agents", "parametrizer", "parametrizer.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("'arduiner'", f.read())

    def test_config_json_globals(self):
        path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertIn("arduino_cli_executable", cfg)
        self.assertIn("arduino_cli_install_dir", cfg)

    def test_config_yaml_defaults(self):
        path = os.path.join(os.path.dirname(__file__), "agents", "arduiner", "config.yaml")
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["action"], "validate")
        self.assertTrue(cfg["auto_bootstrap"])
        self.assertEqual(cfg["fqbn"], "arduino:avr:uno")
        self.assertTrue(cfg["auto_core_install"])
        self.assertIn("target_agents", cfg)

    def test_template_project_ships(self):
        base = os.path.join(os.path.dirname(__file__), "agents", "arduiner", "ArduinoTemplateProject")
        self.assertTrue(os.path.exists(os.path.join(base, "ArduinoTemplateProject.ino")))
        self.assertTrue(os.path.exists(os.path.join(base, "sketch.yaml")))
        self.assertTrue(os.path.exists(os.path.join(base, "src", "Heartbeat.h")))
        self.assertTrue(os.path.exists(os.path.join(base, "src", "Heartbeat.cpp")))

    def test_css_gradient_unique(self):
        path = os.path.join(os.path.dirname(__file__), "static", "agent", "css",
                            "agentic_control_panel.css")
        with open(path, encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".canvas-item.arduiner-agent", css)

    def test_url_route(self):
        path = os.path.join(os.path.dirname(__file__), "urls.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("update_arduiner_connection", f.read())

    def test_migrations_present(self):
        mig_dir = os.path.join(os.path.dirname(__file__), "migrations")
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0109_add_arduiner.py")))
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0110_add_chat_agent_arduiner_tool.py")))


# ---------------------------------------------------------------------------
# PR #1 archive-extraction hardening gate (Zip-Slip / tar path-traversal)
# ---------------------------------------------------------------------------
# Self-activating: while main still calls plain ``extractall`` (in _extract_cli)
# the hardened ``_safe_*_extractall`` helpers do not exist, so these skip. Once
# PR #1 adds them, the probes push a real malicious ``../escape`` archive
# through the helper and assert the traversal is BLOCKED.
_PR1_EXTRACT_PENDING = (
    "PR #1 extraction hardening (_safe_*_extractall) not merged yet — "
    "this Zip-Slip gate auto-activates once the safe extractors are in source."
)


class ArduinerExtractionHardeningTests(SimpleTestCase):
    """Zip-Slip / tar-traversal gate for the Arduiner PR #1 hardening
    (the arduino-cli archive extractor ``_extract_cli``)."""

    def test_zip_slip_member_is_rejected(self):
        m = _load_arduiner_module()
        if not hasattr(m, "_safe_zip_extractall"):
            self.skipTest(_PR1_EXTRACT_PENDING)
        tmp = tempfile.mkdtemp(prefix="ard_zipslip_")
        try:
            dest = os.path.join(tmp, "dest")
            os.makedirs(dest)
            evil = os.path.join(tmp, "evil.zip")
            with zipfile.ZipFile(evil, "w") as zf:
                zf.writestr("../escape.txt", "pwned")
            with zipfile.ZipFile(evil, "r") as zf:
                with self.assertRaises(zipfile.BadZipFile):
                    m._safe_zip_extractall(zf, dest)
            self.assertFalse(
                os.path.exists(os.path.join(tmp, "escape.txt")),
                "zip-slip member escaped the destination",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tar_traversal_is_contained(self):
        m = _load_arduiner_module()
        if not hasattr(m, "_safe_tar_extractall"):
            self.skipTest(_PR1_EXTRACT_PENDING)
        tmp = tempfile.mkdtemp(prefix="ard_tartrav_")
        try:
            dest = os.path.join(tmp, "dest")
            os.makedirs(dest)
            evil = os.path.join(tmp, "evil.tar")
            payload = b"pwned"
            with tarfile.open(evil, "w") as tf:
                info = tarfile.TarInfo("../escape.txt")
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
            with tarfile.open(evil, "r") as tf:
                try:
                    m._safe_tar_extractall(tf, dest)
                except Exception:
                    pass  # raising is fine; the security property is no escape
            self.assertFalse(
                os.path.exists(os.path.join(tmp, "escape.txt")),
                "tar traversal member escaped the destination",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
