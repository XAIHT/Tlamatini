# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Automated tests for the Discoverer workflow agent and its surrounding wiring.

Discoverer bridges Tlamatini to the **ProjectDiscovery** security-tool suite
(subfinder / httpx / naabu / katana / nuclei / cvemap). Like ESP32er / Arduiner /
Kalier it invokes each tool's own CLI DIRECTLY (no MCP server) using only the stdlib.
ZERO-CONFIG: the first call downloads a PRIVATE Go compiler into ``<install_dir>/Go``
and ``go install``s the tool into ``<install_dir>/Go/bin-tools``.

These tests are fully OFFLINE and deterministic: NO network, NO Go download, NO real
tool runs. They drive the REAL pure helpers (_build_argv / _preflight / coercion /
Go-path resolution / _emit_section) directly, and exercise main() only on the
``validate`` path (no bootstrap) and a preflight-REFUSED path (with _ensure_tool
patched so it never reaches the Go download).

The pool script lives under ``agent/agents/discoverer/`` and is loaded via
``importlib.util.spec_from_file_location`` with a cwd + logging-handler save/restore
so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` / ``logging.basicConfig``
side effects do not leak.
"""

import importlib.util
import logging
import os
import tempfile
import unittest
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_discoverer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'discoverer', 'discoverer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_discoverer_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Discoverer module from {module_path}')
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


# ===========================================================================
# Pure helpers + selection contract
# ===========================================================================


class DiscovererHelperTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_discoverer_module()

    def test_selection_sets(self):
        m = self.mod
        self.assertEqual(m._SCAN_TOOLS, {"subfinder", "httpx", "naabu", "katana", "nuclei", "cvemap"})
        self.assertEqual(m._META_ACTIONS, {"bootstrap", "validate", "update_templates", "list_tools"})
        for sel in ("subfinder", "httpx", "naabu", "katana", "nuclei", "cvemap",
                    "bootstrap", "validate", "update_templates", "list_tools"):
            self.assertIn(sel, m._ALL_SELECTIONS, sel)
        # cvemap searches the CVE DB, so it does NOT require a target.
        self.assertNotIn("cvemap", m._NEED_TARGET)
        self.assertIn("subfinder", m._NEED_TARGET)
        # Every scan tool has a go-install module path.
        self.assertEqual(set(m._TOOL_MODULES), m._SCAN_TOOLS)

    def test_coercion_helpers(self):
        m = self.mod
        self.assertEqual(m._cfg({"a": None}, "a", "x"), "x")
        self.assertEqual(m._as_int("100", 1), 100)
        # The regex-extraction path: a wrapped string like "100 ports" -> 100.
        self.assertEqual(m._as_int("100 ports", 1), 100)
        self.assertEqual(m._as_int("nope", 4), 4)
        self.assertTrue(m._as_bool("yes", False))
        self.assertFalse(m._as_bool("", True))  # '' -> False
        self.assertTrue(m._as_bool(True, False))

    def test_go_archive_and_paths(self):
        m = self.mod
        self.assertEqual(m._go_archive_name("1.24.5", "windows", "amd64"), "go1.24.5.windows-amd64.zip")
        self.assertEqual(m._go_archive_name("1.24.5", "linux", "amd64"), "go1.24.5.linux-amd64.tar.gz")
        self.assertIn(m._go_arch(), ("amd64", "arm64", "386"))
        self.assertIn(m._go_os(), ("windows", "linux", "darwin"))
        go_exe = m._go_exe_path(os.path.join("C:\\", "X", "Go"))
        self.assertTrue(go_exe.endswith(os.path.join("bin", "go" + m._exe_suffix())))
        tool = m._tool_exe_path(os.path.join("C:\\", "X", "Go", "bin-tools"), "nuclei")
        self.assertTrue(tool.endswith("nuclei" + m._exe_suffix()))

    def test_go_dir_resolves_under_install_dir(self):
        m = self.mod
        # The core exports TLAMATINI_TEMP as <install_dir>/Temp; go_dir is <install_dir>/Go.
        with tempfile.TemporaryDirectory() as app:
            temp = os.path.join(app, "Temp")
            os.makedirs(temp, exist_ok=True)
            with patch.dict(os.environ, {"TLAMATINI_TEMP": temp}):
                self.assertEqual(m._app_root(), os.path.normpath(app))
                self.assertEqual(m._default_go_dir({}), os.path.join(os.path.normpath(app), "Go"))
                self.assertEqual(
                    m._default_gobin({}, m._default_go_dir({})),
                    os.path.join(os.path.normpath(app), "Go", "bin-tools"),
                )
                # An explicit go_dir overrides the default.
                self.assertEqual(m._default_go_dir({"go_dir": "D:/custom/go"}), "D:/custom/go")

    def test_build_argv_subfinder(self):
        m = self.mod
        a = m._build_argv("subfinder", "subfinder.exe",
                          {"target": "example.com", "json_output": True,
                           "subfinder_all_sources": True}, "out.json")
        self.assertEqual(a[0], "subfinder.exe")
        self.assertIn("-d", a)
        self.assertIn("example.com", a)
        self.assertIn("-oJ", a)
        self.assertIn("-all", a)
        self.assertIn("-silent", a)

    def test_build_argv_targets_file(self):
        m = self.mod
        a = m._build_argv("subfinder", "subfinder.exe",
                          {"targets_file": "doms.txt", "json_output": True}, "out.json")
        self.assertIn("-dL", a)
        self.assertIn("doms.txt", a)
        self.assertNotIn("-d", a)

    def test_build_argv_httpx(self):
        m = self.mod
        a = m._build_argv("httpx", "httpx.exe",
                          {"target": "https://x", "json_output": True,
                           "httpx_probes": "status_code,title,tech_detect"}, "o.json")
        self.assertIn("-u", a)
        self.assertIn("-json", a)
        self.assertIn("-sc", a)
        self.assertIn("-title", a)
        self.assertIn("-td", a)

    def test_build_argv_naabu(self):
        m = self.mod
        a = m._build_argv("naabu", "naabu.exe",
                          {"target": "10.0.0.1", "json_output": True,
                           "naabu_top_ports": "100", "naabu_scan_type": "c"}, "o.json")
        self.assertIn("-host", a)
        self.assertIn("-top-ports", a)
        self.assertIn("100", a)
        self.assertEqual(a[a.index("-s") + 1], "c")

    def test_build_argv_naabu_explicit_ports(self):
        m = self.mod
        a = m._build_argv("naabu", "naabu.exe",
                          {"target": "10.0.0.1", "naabu_ports": "80,443"}, "o.json")
        self.assertIn("-p", a)
        self.assertIn("80,443", a)
        self.assertNotIn("-top-ports", a)

    def test_build_argv_katana(self):
        m = self.mod
        a = m._build_argv("katana", "katana.exe",
                          {"target": "https://x", "json_output": True,
                           "katana_depth": 2, "katana_js_crawl": True}, "o.jsonl")
        self.assertIn("-u", a)
        self.assertIn("-jsonl", a)
        self.assertEqual(a[a.index("-d") + 1], "2")
        self.assertIn("-jc", a)

    def test_build_argv_nuclei(self):
        m = self.mod
        a = m._build_argv("nuclei", "nuclei.exe",
                          {"target": "https://x", "json_output": True,
                           "nuclei_severity": "high,critical", "nuclei_tags": "cve"}, "o.jsonl")
        self.assertIn("-u", a)
        self.assertIn("-jsonl", a)
        self.assertEqual(a[a.index("-s") + 1], "high,critical")
        self.assertEqual(a[a.index("-tags") + 1], "cve")
        self.assertIn("-duc", a)  # disable the update check for a bounded run

    def test_build_argv_cvemap(self):
        m = self.mod
        a = m._build_argv("cvemap", "cvemap.exe",
                          {"cvemap_id": "CVE-2021-44228", "json_output": True}, "o.json")
        self.assertEqual(a[a.index("-id") + 1], "CVE-2021-44228")
        self.assertIn("-json", a)
        # cvemap needs no target flag.
        self.assertNotIn("-u", a)
        self.assertNotIn("-host", a)

    def test_build_argv_extra_args(self):
        m = self.mod
        a = m._build_argv("subfinder", "subfinder.exe",
                          {"target": "example.com", "extra_args": "-timeout 30"}, "o.json")
        self.assertIn("-timeout", a)
        self.assertIn("30", a)

    def test_emit_section_atomic(self):
        m = self.mod
        with _LogCapture() as cap:
            m._emit_section({"tool": "subfinder", "success": "true"}, "body text")
        blocks = [r for r in cap.records if "INI_SECTION_DISCOVERER<<<" in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn(">>>END_SECTION_DISCOVERER", blocks[0])
        self.assertIn("tool: subfinder", blocks[0])


# ===========================================================================
# Preflight — fail-safe gating
# ===========================================================================


class DiscovererPreflightTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_discoverer_module()

    def test_no_target_is_fatal(self):
        m = self.mod
        pf = m._preflight("subfinder", {"go_bootstrap": True}, "subfinder.exe")
        self.assertFalse(pf["ok"])
        self.assertTrue(any("target" in f.lower() for f in pf["fatals"]))

    def test_with_target_ok(self):
        m = self.mod
        pf = m._preflight("subfinder", {"go_bootstrap": True, "target": "example.com"}, "subfinder.exe")
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_cvemap_needs_no_target(self):
        m = self.mod
        pf = m._preflight("cvemap", {"go_bootstrap": True, "cvemap_id": "CVE-2021-44228"}, "cvemap.exe")
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_tool_unresolvable_and_no_bootstrap_is_fatal(self):
        m = self.mod
        pf = m._preflight("subfinder", {"go_bootstrap": False, "target": "example.com"}, "")
        self.assertFalse(pf["ok"])
        self.assertTrue(any("go_bootstrap" in f or "not installed" in f for f in pf["fatals"]))

    def test_tool_unresolvable_with_bootstrap_only_target_gates(self):
        # With go_bootstrap on, an unresolved tool is NOT fatal (it will be installed);
        # only the missing target gates here.
        m = self.mod
        pf = m._preflight("subfinder", {"go_bootstrap": True, "target": "example.com"}, "")
        self.assertTrue(pf["ok"], pf["fatals"])

    def test_naabu_syn_on_windows_warns_not_fatal(self):
        m = self.mod
        pf = m._preflight("naabu", {"go_bootstrap": True, "target": "10.0.0.1",
                                    "naabu_scan_type": "s"}, "naabu.exe")
        self.assertTrue(pf["ok"], pf["fatals"])  # SYN choice is never fatal
        if os.name == "nt":
            self.assertTrue(any("Npcap" in w for w in pf["warnings"]))


# ===========================================================================
# main() end-stage — section ALWAYS emitted + target_agents ALWAYS started
# ===========================================================================


class DiscovererMainTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_discoverer_module()

    def _run_main(self, config, extra_patches=None):
        m = self.mod
        started = []
        env = os.environ.copy()
        patches = [
            patch.object(m, "load_config", return_value=config),
            patch.object(m, "write_pid_file"),
            patch.object(m, "remove_pid_file"),
            patch.object(m, "get_agent_env", return_value=env),
            patch.object(m, "wait_for_agents_to_stop"),
            patch.object(m, "start_agent", side_effect=lambda n: started.append(n) or True),
        ]
        for p in (extra_patches or []):
            patches.append(p)
        with _LogCapture() as cap:
            for p in patches:
                p.start()
            try:
                with self.assertRaises(SystemExit):
                    m.main()
            finally:
                for p in patches:
                    p.stop()
        sections = [r for r in cap.records if "INI_SECTION_DISCOVERER<<<" in r]
        return sections, started

    def test_main_validate_emits_and_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"tool": "validate", "go_dir": os.path.join(tmp, "Go"),
                   "tools_bin": os.path.join(tmp, "Go", "bin-tools"),
                   "output_dir": os.path.join(tmp, "out"),
                   "target_agents": ["parametrizer_1"]}
            sections, started = self._run_main(cfg)
        self.assertEqual(len(sections), 1)
        self.assertIn("success: true", sections[0])
        self.assertIn("stage: validate", sections[0])
        self.assertEqual(started, ["parametrizer_1"])

    def test_main_preflight_refused_still_emits_and_triggers(self):
        m = self.mod
        with tempfile.TemporaryDirectory() as tmp:
            # subfinder with NO target -> preflight refuses. Patch _ensure_tool so the
            # run never reaches the Go bootstrap/download.
            ensure = patch.object(m, "_ensure_tool",
                                  return_value=("", {"steps": [], "tool": "subfinder"}, False))
            cfg = {"tool": "subfinder", "target": "", "go_bootstrap": True,
                   "go_dir": os.path.join(tmp, "Go"), "tools_bin": os.path.join(tmp, "Go", "bin"),
                   "output_dir": os.path.join(tmp, "out"), "target_agents": ["ender_1"]}
            sections, started = self._run_main(cfg, extra_patches=[ensure])
        self.assertEqual(len(sections), 1)
        self.assertIn("success: false", sections[0])
        self.assertIn("PREFLIGHT REFUSED", sections[0])
        self.assertEqual(started, ["ender_1"])


# ===========================================================================
# Registry / integration wiring (no agent subprocess)
# ===========================================================================


class DiscovererIntegrationTests(SimpleTestCase):
    def test_wrapped_spec(self):
        from agent.chat_agent_registry import (
            WRAPPED_CHAT_AGENT_BY_TOOL_NAME, WRAPPED_CHAT_AGENT_MAP,
        )
        self.assertIn("discoverer", WRAPPED_CHAT_AGENT_MAP)
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_discoverer"]
        self.assertEqual(spec.display_name, "Discoverer")
        self.assertEqual(spec.template_dir, "discoverer")

    def test_exec_report_capturable_via_generic_fallback(self):
        # Discoverer relies on the generic _resolve_exec_report_spec fallback (it has
        # NO _EXEC_REPORT_TOOLS entry). It MUST still be capturable and NOT a management tool.
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        from agent.mcp_agent import _MANAGEMENT_TOOLS
        self.assertIn("chat_agent_discoverer", WRAPPED_CHAT_AGENT_BY_TOOL_NAME)
        self.assertNotIn("chat_agent_discoverer", _MANAGEMENT_TOOLS)

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS["discoverer"]
        for key in ("tool", "target", "returncode", "success", "findings_count",
                    "json_path", "pdcp_used", "stage", "response_body"):
            self.assertIn(key, fields)

    def test_display_name_normalization(self):
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertEqual(display_name_from_agent_type("discoverer"), "Discoverer")

    def test_parametrizer_section_type(self):
        path = os.path.join(os.path.dirname(__file__), "agents", "parametrizer", "parametrizer.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("'discoverer'", f.read())

    def test_config_yaml_defaults(self):
        path = os.path.join(os.path.dirname(__file__), "agents", "discoverer", "config.yaml")
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["tool"], "subfinder")
        self.assertTrue(cfg["go_bootstrap"])
        self.assertIn("go_version", cfg)
        for key in ("target", "targets_file", "json_output", "naabu_scan_type",
                    "pdcp_api_key", "go_dir", "tools_bin", "source_agents", "target_agents"):
            self.assertIn(key, cfg)

    def test_css_gradient_present(self):
        path = os.path.join(os.path.dirname(__file__), "static", "agent", "css",
                            "agentic_control_panel.css")
        with open(path, encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".canvas-item.discoverer-agent", css)

    def test_url_route(self):
        path = os.path.join(os.path.dirname(__file__), "urls.py")
        with open(path, encoding="utf-8") as f:
            self.assertIn("update_discoverer_connection", f.read())

    def test_migrations_present(self):
        mig_dir = os.path.join(os.path.dirname(__file__), "migrations")
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0148_add_discoverer_demo_prompts.py")))
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0149_add_discoverer.py")))
        self.assertTrue(os.path.exists(os.path.join(mig_dir, "0150_add_chat_agent_discoverer_tool.py")))

    def test_demo_prompts_seeded(self):
        # Read the seeding migration (SimpleTestCase blocks DB access).
        path = os.path.join(os.path.dirname(__file__), "migrations",
                            "0148_add_discoverer_demo_prompts.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("DISCOVERER RECON SWEEP", src)
        self.assertIn("DISCOVERER AUTHORIZED PROBE", src)


if __name__ == "__main__":
    unittest.main()
