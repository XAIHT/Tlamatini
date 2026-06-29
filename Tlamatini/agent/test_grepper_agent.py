# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
HARD real-scenario tests for the **Grepper** agent (read-only regex content search).

The behaviour tests run the REAL ``agent/agents/grepper/grepper.py`` as a subprocess
against tailored ``config.yaml`` files over throwaway directory trees (no mocking),
covering matches / no_matches / not_found / output modes / case-insensitivity /
invalid-regex / binary-skip / max_results truncation. The wiring tests assert the
registry, contract, exec-report, URL and CSS wiring.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml
from django.test import SimpleTestCase
from django.urls import reverse

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GREPPER_PY = os.path.join(_THIS_DIR, "agents", "grepper", "grepper.py")


def _run_grepper(path, **over):
    tmp = tempfile.mkdtemp(prefix="grepper_test_")
    gdir = os.path.join(tmp, "grepper")
    os.makedirs(gdir, exist_ok=True)
    try:
        shutil.copy(GREPPER_PY, os.path.join(gdir, "grepper.py"))
        cfg = {
            "pattern": over.get("pattern", ""),
            "path": path,
            "glob": over.get("glob", ""),
            "case_insensitive": over.get("case_insensitive", False),
            "output_mode": over.get("output_mode", "content"),
            "max_results": over.get("max_results", 200),
            "source_agents": [],
            "target_agents": [],
        }
        with open(os.path.join(gdir, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        subprocess.run([sys.executable, "grepper.py"], cwd=gdir, timeout=60, capture_output=True)
        with open(os.path.join(gdir, "grepper.log"), encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _section(log):
    m = re.search(r"INI_SECTION_GREPPER<<<(.*?)>>>END_SECTION_GREPPER", log, re.S)
    assert m, f"no INI_SECTION_GREPPER in log:\n{log}"
    body = m.group(1)
    out = {"_body": body}
    for key in ("matches", "files_searched"):
        out[key] = int(re.search(rf"{key}:\s*(\d+)", body).group(1))
    out["status"] = re.search(r"status:\s*(\S+)", body).group(1)
    return out


class GrepperBehaviorTests(SimpleTestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="grepper_tree_")
        os.makedirs(os.path.join(self.tree, "sub"))
        self._w("a.py", "def foo():\n    return MARK\n")
        self._w(os.path.join("sub", "b.py"), "x = 1  # MARK here\n")
        self._w("c.txt", "MARK in text\n")
        with open(os.path.join(self.tree, "bin.dat"), "wb") as f:
            f.write(b"\x00\x01MARK\xff\xfe")  # binary - must be skipped

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def _w(self, rel, data):
        with open(os.path.join(self.tree, rel), "w", encoding="utf-8") as f:
            f.write(data)

    def test_matches_with_glob(self):
        s = _section(_run_grepper(self.tree, pattern="MARK", glob="*.py"))
        self.assertEqual(s["status"], "matches")
        self.assertEqual(s["matches"], 2)  # a.py + sub/b.py, NOT c.txt (glob)
        self.assertIn("a.py:2:", s["_body"])
        self.assertIn("b.py:1:", s["_body"])
        self.assertNotIn("c.txt", s["_body"])

    def test_no_matches(self):
        s = _section(_run_grepper(self.tree, pattern="ZZZNOPE", glob="*.py"))
        self.assertEqual(s["status"], "no_matches")
        self.assertEqual(s["matches"], 0)

    def test_not_found(self):
        s = _section(_run_grepper(os.path.join(self.tree, "nope_dir"), pattern="MARK"))
        self.assertEqual(s["status"], "not_found")

    def test_output_mode_files(self):
        s = _section(_run_grepper(self.tree, pattern="MARK", glob="*.py", output_mode="files"))
        self.assertEqual(s["status"], "matches")
        # body lists each matching file ONCE (paths only)
        self.assertIn("a.py", s["_body"])
        self.assertIn("b.py", s["_body"])
        self.assertNotIn(":2:", s["_body"])

    def test_output_mode_count(self):
        s = _section(_run_grepper(self.tree, pattern="MARK", glob="*.py", output_mode="count"))
        self.assertEqual(s["status"], "matches")
        self.assertIn("1\t", s["_body"])  # per-file count column

    def test_case_insensitive(self):
        self._w("d.py", "value = mark\n")
        s = _section(_run_grepper(self.tree, pattern="MARK", glob="d.py", case_insensitive=True))
        self.assertEqual(s["matches"], 1)

    def test_invalid_regex_errors(self):
        s = _section(_run_grepper(self.tree, pattern="(unclosed", glob="*.py"))
        self.assertEqual(s["status"], "error")
        self.assertIn("Invalid regex", s["_body"])

    def test_binary_file_skipped_not_crash(self):
        # Search everything (no glob): bin.dat contains MARK bytes but must be skipped.
        s = _section(_run_grepper(self.tree, pattern="MARK"))
        self.assertEqual(s["status"], "matches")
        self.assertNotIn("bin.dat", s["_body"])

    def test_max_results_truncation(self):
        big = os.path.join(self.tree, "big.py")
        with open(big, "w", encoding="utf-8") as f:
            for _ in range(50):
                f.write("MARK\n")
        s = _section(_run_grepper(self.tree, pattern="MARK", glob="big.py", max_results=10))
        self.assertEqual(s["matches"], 10)
        self.assertIn("truncated: True", s["_body"])


class GrepperWiringTests(SimpleTestCase):
    def test_wrapped_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get("chat_agent_grepper")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, "Grepper")
        self.assertEqual(spec.template_dir, "grepper")

    def test_exec_report_membership(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get("chat_agent_grepper"), ("grepper", "Grepper"))

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import get_agent_contract
        c = get_agent_contract("grepper")
        for fld in ("pattern", "path", "matches", "status", "response_body"):
            self.assertIn(fld, c.parametrizer_fields)

    def test_url_route_resolves(self):
        url = reverse("update_grepper_connection", args=["grepper-1"])
        self.assertIn("update_grepper_connection/grepper-1/", url)

    def test_parametrizer_section_type_registered(self):
        param = os.path.join(_THIS_DIR, "agents", "parametrizer", "parametrizer.py")
        with open(param, encoding="utf-8") as f:
            self.assertIn("'grepper'", f.read())

    def test_canvas_css_class_present_and_unique(self):
        css = os.path.join(_THIS_DIR, "static", "agent", "css", "agentic_control_panel.css")
        with open(css, encoding="utf-8") as f:
            self.assertEqual(f.read().count(".canvas-item.grepper-agent {"), 1)
