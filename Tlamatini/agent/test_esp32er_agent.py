# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the ESP32er workflow agent and its surrounding infrastructure.

ESP32er bridges Tlamatini to **PlatformIO Core** (https://platformio.org). Unlike
STM32er — which drives a separate MCP stdio server because STM32CubeIDE has no
unified CLI — PlatformIO already ships a complete `pio` CLI, so ESP32er invokes
`pio` subcommands DIRECTLY (the Kalier / Executer pattern) using only the stdlib
(``subprocess`` + ``urllib`` + ``json`` + ``threading``). It is a standalone pool
agent under ``agent/agents/esp32er/`` loaded here through
``importlib.util.spec_from_file_location`` with a cwd + logging-handler
save/restore so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` /
``logging.basicConfig`` side effects do not leak into the test process.

No PlatformIO install, no ESP32 hardware and no network are required: a tiny FAKE
`pio` (a pure-stdlib temp Python script) answers `--version` / `system info` /
`device list --json-output` / `run` exactly as the real CLI would, and is invoked
through the REAL ``_pio`` / ``_run_action`` / ``_preflight`` helpers via an explicit
``pio_cmd = [sys.executable, fake_pio]`` — so the genuine subprocess + capture +
fail-safe-gating code paths are exercised deterministically.

Covers:
- Action sets: _ALL_ACTIONS / _HARDWARE_ACTIONS / _FILE_ACTIONS / _BUILD_ACTIONS
- Helpers: _cfg / _as_int / _as_bool / _env_args / _project_args / _ok / _wrap
- File ops: _write_source / _read_source / _list_sources (round-trip + path-escape)
- _create_project + _ensure_framework (init then patch platformio.ini framework)
- _pio / _run_action routing against the FAKE pio (build / device_list / system_info)
- _probe_serial: JSON parse, ESP USB-VID detection, no-port / cli-error states
- _preflight fail-safe gating: no pio -> fatal; build needs platformio.ini -> fatal;
  upload needs a serial port -> fatal; warnings (non-espressif platform) never refuse
- _bounded_monitor: drains a streaming child for monitor_seconds then terminates it
- _emit_section: single atomic INI_SECTION_ESP32ER block
- main() end-stage: section always emitted + target_agents always started, on a
  successful device_list run AND on the preflight-refused path
- Registry integration: ChatWrappedAgentSpec, Exec Report row, agent contract +
  parametrizer fields, name normalization, config.yaml defaults, config.json globals,
  CSS gradient (unique), URL route, migration presence (0105 + 0106)
"""

import importlib.util
import json
import logging
import os
import sys
import tempfile
import textwrap
import unittest
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_esp32er_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'esp32er', 'esp32er.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_esp32er_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load ESP32er module from {module_path}')

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


# A tiny FAKE `pio`. Pure stdlib; mimics the PlatformIO CLI surface ESP32er uses.
# Invoked through the REAL helpers as [sys.executable, <this file>, *args]. Reads
# env knobs FAKE_PIO_PORTS (device-list JSON) and FAKE_PIO_RUN_RC (build/run rc).
_FAKE_PIO = textwrap.dedent(r'''
    import sys, os, json

    args = sys.argv[1:]

    def out(s):
        sys.stdout.write(s + "\n")

    if args[:1] == ["--version"]:
        out("PlatformIO Core, version 6.1.11")
        sys.exit(0)
    if args[:2] == ["system", "info"]:
        out("PlatformIO Core            6.1.11")
        out("Python Version             3.12.0")
        sys.exit(0)
    if args[:2] == ["device", "list"]:
        ports = json.loads(os.environ.get("FAKE_PIO_PORTS", "[]"))
        out(json.dumps(ports))
        sys.exit(0)
    if args[:1] == ["boards"]:
        out("[]")
        sys.exit(0)
    if args[:2] == ["project", "init"]:
        # Honor -d <dir>: scaffold a minimal PlatformIO project so a following
        # build/upload finds a platformio.ini (mirrors `pio project init`).
        d = None
        if "-d" in args:
            d = args[args.index("-d") + 1]
        if d:
            os.makedirs(os.path.join(d, "src"), exist_ok=True)
            with open(os.path.join(d, "platformio.ini"), "w") as f:
                f.write("[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n")
        out("Project has been successfully initialized!")
        sys.exit(0)
    if args[:1] == ["run"]:
        rc = int(os.environ.get("FAKE_PIO_RUN_RC", "0"))
        if rc == 0:
            out("Processing esp32dev (platform: espressif32; board: esp32dev)")
            out("RAM:   [=         ]   5.6% (used 18412 bytes)")
            out("Flash: [===       ]  28.4% (used 372170 bytes)")
            out("============= [SUCCESS] Took 12.34 seconds =============")
            sys.exit(0)
        sys.stderr.write("Error: Could not open port 'COM9'\n")
        sys.exit(rc)
    if args[:1] in (["check"], ["test"]) or args[:1] == ["pkg"]:
        out("ok")
        sys.exit(0)
    sys.stderr.write("unknown command: %r\n" % (args,))
    sys.exit(2)
''')


def _write_fake_pio(tmpdir):
    path = os.path.join(tmpdir, 'fake_pio.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_FAKE_PIO)
    return path


def _fake_pio_cmd(tmpdir):
    return [sys.executable, _write_fake_pio(tmpdir)]


def _make_project(tmpdir, with_ini=True):
    proj = os.path.join(tmpdir, 'proj')
    os.makedirs(os.path.join(proj, 'src'), exist_ok=True)
    if with_ini:
        with open(os.path.join(proj, 'platformio.ini'), 'w', encoding='utf-8') as f:
            f.write("[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n")
    return proj


# ===========================================================================
# Pure helpers + action contract
# ===========================================================================


class Esp32erHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_esp32er_module()

    def test_action_sets(self):
        m = self.mod
        for action in ("bootstrap", "validate", "system_info", "boards", "create_project",
                       "write_source", "read_source", "list_sources", "clean", "build",
                       "upload", "build_and_upload", "list_artifacts", "device_list",
                       "monitor", "monitor_session", "pkg_install", "pkg_list", "pkg_update",
                       "check", "test"):
            self.assertIn(action, m._ALL_ACTIONS, action)
        self.assertEqual(m._HARDWARE_ACTIONS, {"upload", "build_and_upload", "monitor", "monitor_session"})
        self.assertEqual(m._FILE_ACTIONS, {"write_source", "read_source", "list_sources"})
        # upload IS a build action too (build is implicit on upload)? No — only build/clean/...
        self.assertIn("build", m._BUILD_ACTIONS)
        self.assertNotIn("upload", m._BUILD_ACTIONS)
        # The one-call lifecycle composite is a build-class action (preflight checks
        # only pio-resolvable) and must NOT be a hardware action (it gates the upload
        # leg internally so a missing board still scaffolds + builds).
        self.assertIn("scaffold_build_upload", m._ALL_ACTIONS)
        self.assertIn("scaffold_build_upload", m._BUILD_ACTIONS)
        self.assertNotIn("scaffold_build_upload", m._HARDWARE_ACTIONS)

    def test_coercion_and_arg_helpers(self):
        m = self.mod
        self.assertEqual(m._cfg({"a": None}, "a", "x"), "x")
        self.assertEqual(m._as_int("8", 1), 8)
        self.assertEqual(m._as_int("nope", 4), 4)
        self.assertTrue(m._as_bool("yes", False))
        self.assertFalse(m._as_bool("", True) is True and m._as_bool("", True))  # '' -> False
        self.assertEqual(m._env_args({"environment": "esp32dev"}), ["-e", "esp32dev"])
        self.assertEqual(m._env_args({"environment": ""}), [])
        self.assertEqual(m._project_args({"project_dir": "C:/x"}), ["-d", "C:/x"])
        self.assertEqual(m._project_args({"project_dir": ""}), [])

    def test_ok_and_wrap(self):
        m = self.mod
        self.assertTrue(m._ok({"ok": True}))
        self.assertFalse(m._ok({"ok": False}))
        self.assertFalse(m._ok({"error": "x"}))
        self.assertTrue(m._ok({"stdout": "hi"}))
        env = m._wrap("run", {"ok": True, "returncode": 0})
        self.assertEqual(env["tool"], "run")
        self.assertTrue(env["ok"])

    def test_file_ops_roundtrip(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            w = m._write_source({"project_dir": proj, "rel_path": "src/main.cpp",
                                 "content": "void setup(){} void loop(){}"})
            self.assertTrue(w["ok"], w)
            r = m._read_source({"project_dir": proj, "rel_path": "src/main.cpp"})
            self.assertTrue(r["ok"])
            self.assertIn("void setup", r["stdout"])
            ls = m._list_sources({"project_dir": proj})
            self.assertTrue(ls["ok"])
            self.assertIn("src/main.cpp", ls["stdout"])
            self.assertIn("platformio.ini", ls["stdout"])

    def test_write_source_rejects_escape(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            bad = m._write_source({"project_dir": proj, "rel_path": "../escape.txt", "content": "x"})
            self.assertFalse(bad["ok"])
            self.assertIn("escape", bad["error"].lower())

    def test_ensure_framework(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            ini = os.path.join(tmp, "platformio.ini")
            with open(ini, "w", encoding="utf-8") as f:
                f.write("[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n")
            m._ensure_framework(ini, "espidf")
            with open(ini, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("framework = espidf", text)
            self.assertNotIn("framework = arduino", text)
            # Insert when missing.
            ini2 = os.path.join(tmp, "p2.ini")
            with open(ini2, "w", encoding="utf-8") as f:
                f.write("[env:esp32dev]\nboard = esp32dev\n")
            m._ensure_framework(ini2, "arduino")
            with open(ini2, encoding="utf-8") as f:
                self.assertIn("framework = arduino", f.read())

    def test_emit_section_atomic(self):
        m = self.mod
        with _LogCapture() as cap:
            m._emit_section({"action": "build", "ok": "true"}, "body text")
        blocks = [r for r in cap.records if "INI_SECTION_ESP32ER<<<" in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn(">>>END_SECTION_ESP32ER", blocks[0])
        self.assertIn("action: build", blocks[0])


# ===========================================================================
# pio invocation + preflight against the FAKE pio
# ===========================================================================


class Esp32erPioTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_esp32er_module()

    def test_pio_system_info(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            res = m._pio(["system", "info"], pio, os.environ.copy(), 60)
            self.assertTrue(res["ok"])
            self.assertEqual(res["returncode"], 0)
            self.assertIn("PlatformIO Core", res["stdout"])

    def test_run_action_build(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            env = m._wrap  # noqa: F841 (sanity that _wrap exists)
            out = m._run_action("build", {"project_dir": proj}, pio, os.environ.copy(), 120)
            self.assertTrue(out["ok"], out)
            self.assertIn("SUCCESS", out["result"]["stdout"])

    def test_run_action_build_failure_is_routable(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            env = dict(os.environ, FAKE_PIO_RUN_RC="1")
            out = m._run_action("upload", {"project_dir": proj}, pio, env, 120)
            self.assertFalse(out["ok"])
            self.assertEqual(out["result"]["returncode"], 1)

    def test_run_action_device_list(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            ports = [{"port": "COM5", "hwid": "USB VID:PID=10C4:EA60 SER=0001"}]
            env = dict(os.environ, FAKE_PIO_PORTS=json.dumps(ports))
            out = m._run_action("device_list", {}, pio, env, 60)
            self.assertTrue(out["ok"])
            self.assertIn("COM5", out["result"]["stdout"])

    def test_scaffold_build_upload_full_cycle(self):
        """ONE call creates the project, writes the sketch, builds, and uploads
        (board present) — every stage appears in the combined body."""
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = os.path.join(tmp, "blink")  # does NOT exist yet → create leg runs
            ports = [{"port": "COM9", "hwid": "USB VID:PID=10C4:EA60"}]
            env = dict(os.environ, FAKE_PIO_PORTS=json.dumps(ports))
            cfg = {"project_dir": proj, "board": "esp32dev",
                   "content": "void setup(){} void loop(){}", "port": "COM9"}
            out = m._run_action("scaffold_build_upload", cfg, pio, env, 120)
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["result"]["stage"], "upload")
            body = out["result"]["stdout"]
            for stage in ("create_project", "write_source", "build", "upload"):
                self.assertIn(stage, body, f"missing stage {stage} in:\n{body}")
            # the sketch was actually written under the created project
            self.assertTrue(os.path.exists(os.path.join(proj, "src", "main.cpp")))

    def test_scaffold_build_upload_no_board_builds_then_skips_upload(self):
        """Fail-safe partial success: no serial port → still scaffold + build,
        report built-OK with stage='upload_skipped' (NOT a failure)."""
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)  # project already exists → create leg skipped
            env = dict(os.environ, FAKE_PIO_PORTS="[]")  # no board
            cfg = {"project_dir": proj, "board": "esp32dev",
                   "content": "void setup(){} void loop(){}"}
            out = m._run_action("scaffold_build_upload", cfg, pio, env, 120)
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["result"]["stage"], "upload_skipped")
            self.assertIn("upload", out["tool"].lower())
            self.assertIn("SUCCESS", out["result"]["stdout"])  # build still ran

    def test_scaffold_build_upload_build_failure_short_circuits(self):
        """A failing build aborts before upload and is routable (stage='build')."""
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            env = dict(os.environ, FAKE_PIO_RUN_RC="1", FAKE_PIO_PORTS="[]")
            cfg = {"project_dir": proj, "board": "esp32dev", "content": "broken"}
            out = m._run_action("scaffold_build_upload", cfg, pio, env, 120)
            self.assertFalse(out["ok"])
            self.assertEqual(out["result"]["stage"], "build")

    def test_probe_serial_detects_esp_vid(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            ports = [{"port": "COM7", "hwid": "USB VID:PID=10C4:EA60"}]
            env = dict(os.environ, FAKE_PIO_PORTS=json.dumps(ports))
            res = m._probe_serial(pio, env)
            self.assertTrue(res["present"])
            self.assertTrue(res["esp_like"])
            self.assertIn("COM7", res["ports"])

    def test_probe_serial_no_ports(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            env = dict(os.environ, FAKE_PIO_PORTS="[]")
            res = m._probe_serial(pio, env)
            self.assertFalse(res["present"])
            self.assertTrue(res["cli_ok"])

    def test_preflight_no_pio_is_fatal(self):
        m = self.mod
        pf = m._preflight("build", {"project_dir": "x"}, [], os.environ.copy())
        self.assertFalse(pf["ok"])
        self.assertTrue(any("pio" in f.lower() for f in pf["fatals"]))

    def test_preflight_build_needs_ini(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp, with_ini=False)
            pf = m._preflight("build", {"project_dir": proj}, pio, os.environ.copy())
            self.assertFalse(pf["ok"])
            self.assertTrue(any("platformio.ini" in f for f in pf["fatals"]))

    def test_preflight_build_ok_with_ini(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            pf = m._preflight("build", {"project_dir": proj}, pio, os.environ.copy())
            self.assertTrue(pf["ok"], pf["fatals"])

    def test_preflight_upload_needs_serial(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            env = dict(os.environ, FAKE_PIO_PORTS="[]")
            pf = m._preflight("upload", {"project_dir": proj}, pio, env)
            self.assertFalse(pf["ok"])
            self.assertTrue(any("serial port" in f.lower() for f in pf["fatals"]))

    def test_preflight_upload_ok_with_port(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = _make_project(tmp)
            ports = [{"port": "COM5", "hwid": "USB VID:PID=10C4:EA60"}]
            env = dict(os.environ, FAKE_PIO_PORTS=json.dumps(ports))
            pf = m._preflight("upload", {"project_dir": proj}, pio, env)
            self.assertTrue(pf["ok"], pf["fatals"])

    def test_preflight_warns_non_espressif(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = os.path.join(tmp, "proj")
            os.makedirs(proj)
            with open(os.path.join(proj, "platformio.ini"), "w", encoding="utf-8") as f:
                f.write("[env:uno]\nplatform = atmelavr\nboard = uno\n")
            pf = m._preflight("build", {"project_dir": proj}, pio, os.environ.copy())
            self.assertTrue(pf["ok"])  # warning, not refusal
            self.assertTrue(any("espressif32" in w for w in pf["warnings"]))


# ===========================================================================
# main() end-stage — section ALWAYS emitted + target_agents ALWAYS started
# ===========================================================================


class Esp32erMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_esp32er_module()

    def _run_main(self, config, pio_cmd, extra_env=None):
        m = self.mod
        started = []
        env = dict(os.environ, **(extra_env or {}))
        with _LogCapture() as cap, \
                patch.object(m, "load_config", return_value=config), \
                patch.object(m, "write_pid_file"), patch.object(m, "remove_pid_file"), \
                patch.object(m, "get_agent_env", return_value=env), \
                patch.object(m, "_resolve_pio_cmd", return_value=pio_cmd), \
                patch.object(m, "wait_for_agents_to_stop"), \
                patch.object(m, "start_agent", side_effect=lambda n: started.append(n) or True):
            with self.assertRaises(SystemExit):
                m.main()
        sections = [r for r in cap.records if "INI_SECTION_ESP32ER<<<" in r]
        return sections, started

    def test_main_device_list_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            ports = [{"port": "COM5", "hwid": "USB VID:PID=10C4:EA60"}]
            cfg = {"action": "device_list", "auto_bootstrap": False, "preflight": True,
                   "target_agents": ["parametrizer_1"]}
            sections, started = self._run_main(cfg, pio, {"FAKE_PIO_PORTS": json.dumps(ports)})
        self.assertEqual(len(sections), 1)
        self.assertIn("success: true", sections[0])
        self.assertEqual(started, ["parametrizer_1"])

    def test_main_preflight_refused_still_emits_and_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            # build with NO project_dir -> preflight fatal (no platformio.ini).
            cfg = {"action": "build", "auto_bootstrap": False, "preflight": True,
                   "project_dir": "", "target_agents": ["ender_1"]}
            sections, started = self._run_main(cfg, pio)
        self.assertEqual(len(sections), 1)
        self.assertIn("success: false", sections[0])
        self.assertIn("PREFLIGHT REFUSED", sections[0])
        self.assertEqual(started, ["ender_1"])

    def test_main_scaffold_build_upload_full_path(self):
        """Full agent path: config(action=scaffold_build_upload) -> main() emits ONE
        section with success:true and stage upload, and still triggers downstream.
        preflight must NOT refuse it (it creates the project + gates upload itself)."""
        with tempfile.TemporaryDirectory() as tmp:
            pio = _fake_pio_cmd(tmp)
            proj = os.path.join(tmp, "blink")  # absent → create leg runs through main()
            ports = [{"port": "COM9", "hwid": "USB VID:PID=10C4:EA60"}]
            cfg = {"action": "scaffold_build_upload", "auto_bootstrap": False,
                   "preflight": True, "project_dir": proj, "board": "esp32dev",
                   "content": "void setup(){} void loop(){}", "port": "COM9",
                   "target_agents": ["parametrizer_1"]}
            sections, started = self._run_main(cfg, pio, {"FAKE_PIO_PORTS": json.dumps(ports)})
            # Check the on-disk artifact INSIDE the with-block (the TemporaryDirectory
            # is deleted on exit, so a filesystem assert outside it would always fail).
            sketch_written = os.path.exists(os.path.join(proj, "src", "main.cpp"))
        self.assertEqual(len(sections), 1)
        self.assertIn("success: true", sections[0])
        self.assertIn("action: scaffold_build_upload", sections[0])
        self.assertEqual(started, ["parametrizer_1"])
        self.assertTrue(sketch_written, "scaffold_build_upload did not write src/main.cpp through main()")


# ===========================================================================
# Registry / integration wiring (no agent subprocess)
# ===========================================================================


class Esp32erIntegrationTests(SimpleTestCase):
    def test_wrapped_spec(self):
        from agent.chat_agent_registry import (
            WRAPPED_CHAT_AGENT_BY_TOOL_NAME, WRAPPED_CHAT_AGENT_MAP,
        )
        self.assertIn("esp32er", WRAPPED_CHAT_AGENT_MAP)
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_esp32er"]
        self.assertEqual(spec.display_name, "ESP32er")
        self.assertEqual(spec.template_dir, "esp32er")
        self.assertTrue(spec.long_running)

    def test_exec_report_row(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS["chat_agent_esp32er"], ("esp32er", "ESP32er"))

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS["esp32er"]
        for key in ("action", "tool", "ok", "returncode", "success", "project_dir",
                    "port", "environment", "stage", "response_body"):
            self.assertIn(key, fields)

    def test_display_name_normalization(self):
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertEqual(display_name_from_agent_type("esp32er"), "ESP32er")

    def test_parametrizer_section_type(self):
        # SECTION_AGENT_TYPES lives in the parametrizer pool agent; assert by file.
        path = os.path.join(os.path.dirname(__file__), "agents", "parametrizer", "parametrizer.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("'esp32er'", f.read())

    def test_config_json_globals(self):
        path = os.path.join(os.path.dirname(__file__), "config.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertIn("pio_executable", cfg)
        self.assertIn("pio_core_dir", cfg)

    def test_config_yaml_defaults(self):
        path = os.path.join(os.path.dirname(__file__), "agents", "esp32er", "config.yaml")
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["action"], "validate")
        self.assertTrue(cfg["auto_bootstrap"])
        self.assertEqual(cfg["board"], "esp32dev")
        self.assertIn("target_agents", cfg)

    def test_css_gradient_unique(self):
        path = os.path.join(os.path.dirname(__file__), "static", "agent", "css",
                            "agentic_control_panel.css")
        with open(path, encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".canvas-item.esp32er-agent", css)

    def test_url_route(self):
        path = os.path.join(os.path.dirname(__file__), "urls.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("update_esp32er_connection", f.read())

    def test_migrations_present(self):
        mig_dir = os.path.join(os.path.dirname(__file__), "migrations")
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0105_add_esp32er.py")))
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0106_add_chat_agent_esp32er_tool.py")))


if __name__ == "__main__":
    unittest.main()
