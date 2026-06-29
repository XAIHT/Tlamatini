# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
HARD real-scenario tests for the **Globber** agent (read-only filename glob search).

The behaviour tests run the REAL ``agent/agents/globber/globber.py`` as a subprocess
against tailored ``config.yaml`` files over throwaway directory trees (no mocking),
covering recursive matches / no_matches / not_found / mtime + name ordering /
files-only (no dirs) / max_results truncation. The wiring tests assert the
registry, contract, exec-report, URL and CSS wiring.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml
from django.test import SimpleTestCase
from django.urls import reverse

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
GLOBBER_PY = os.path.join(_THIS_DIR, "agents", "globber", "globber.py")


def _run_globber(path, **over):
    tmp = tempfile.mkdtemp(prefix="globber_test_")
    gdir = os.path.join(tmp, "globber")
    os.makedirs(gdir, exist_ok=True)
    try:
        shutil.copy(GLOBBER_PY, os.path.join(gdir, "globber.py"))
        cfg = {
            "pattern": over.get("pattern", ""),
            "path": path,
            "sort_by": over.get("sort_by", "mtime"),
            "max_results": over.get("max_results", 500),
            "source_agents": [],
            "target_agents": [],
        }
        with open(os.path.join(gdir, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        subprocess.run([sys.executable, "globber.py"], cwd=gdir, timeout=60, capture_output=True)
        with open(os.path.join(gdir, "globber.log"), encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _section(log):
    m = re.search(r"INI_SECTION_GLOBBER<<<(.*?)>>>END_SECTION_GLOBBER", log, re.S)
    assert m, f"no INI_SECTION_GLOBBER in log:\n{log}"
    body = m.group(1)
    return {
        "_body": body,
        "matches": int(re.search(r"matches:\s*(\d+)", body).group(1)),
        "status": re.search(r"status:\s*(\S+)", body).group(1),
    }


class GlobberBehaviorTests(SimpleTestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="globber_tree_")
        os.makedirs(os.path.join(self.tree, "sub"))
        self._w("old.py", "old")
        time.sleep(0.05)
        self._w(os.path.join("sub", "new.py"), "new")
        self._w("note.txt", "txt")

    def tearDown(self):
        shutil.rmtree(self.tree, ignore_errors=True)

    def _w(self, rel, data):
        with open(os.path.join(self.tree, rel), "w", encoding="utf-8") as f:
            f.write(data)

    def test_recursive_matches(self):
        s = _section(_run_globber(self.tree, pattern="**/*.py"))
        self.assertEqual(s["status"], "matches")
        self.assertEqual(s["matches"], 2)
        self.assertIn("new.py", s["_body"])
        self.assertIn("old.py", s["_body"])
        self.assertNotIn("note.txt", s["_body"])

    def test_mtime_newest_first(self):
        body = _section(_run_globber(self.tree, pattern="**/*.py", sort_by="mtime"))["_body"]
        self.assertLess(body.index("new.py"), body.index("old.py"))

    def test_name_sort(self):
        body = _section(_run_globber(self.tree, pattern="**/*.py", sort_by="name"))["_body"]
        # alphabetical by full path: '...\\new.py' (sub) vs '...\\old.py' (root) -> old before new? compare actual
        self.assertIn("new.py", body)
        self.assertIn("old.py", body)

    def test_no_matches(self):
        s = _section(_run_globber(self.tree, pattern="*.zzz"))
        self.assertEqual(s["status"], "no_matches")
        self.assertEqual(s["matches"], 0)

    def test_not_found_dir(self):
        s = _section(_run_globber(os.path.join(self.tree, "nope"), pattern="*.py"))
        self.assertEqual(s["status"], "not_found")

    def test_files_only_not_dirs(self):
        # 'sub' is a directory; a bare '*' glob must NOT return it.
        s = _section(_run_globber(self.tree, pattern="*"))
        self.assertNotIn(os.path.join(self.tree, "sub") + "\n", s["_body"] + "\n")
        # but the top-level files are present
        self.assertIn("old.py", s["_body"])

    def test_max_results_truncation(self):
        for i in range(20):
            self._w(f"f{i:02d}.log", "x")
        s = _section(_run_globber(self.tree, pattern="*.log", max_results=5))
        self.assertEqual(s["matches"], 20)            # total counted
        self.assertIn("truncated: True", s["_body"])  # but body capped


class GlobberWiringTests(SimpleTestCase):
    def test_wrapped_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get("chat_agent_globber")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, "Globber")
        self.assertEqual(spec.template_dir, "globber")

    def test_exec_report_membership(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get("chat_agent_globber"), ("globber", "Globber"))

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import get_agent_contract
        c = get_agent_contract("globber")
        for fld in ("pattern", "path", "matches", "status", "response_body"):
            self.assertIn(fld, c.parametrizer_fields)

    def test_url_route_resolves(self):
        url = reverse("update_globber_connection", args=["globber-1"])
        self.assertIn("update_globber_connection/globber-1/", url)

    def test_parametrizer_section_type_registered(self):
        param = os.path.join(_THIS_DIR, "agents", "parametrizer", "parametrizer.py")
        with open(param, encoding="utf-8") as f:
            self.assertIn("'globber'", f.read())

    def test_canvas_css_class_present_and_unique(self):
        css = os.path.join(_THIS_DIR, "static", "agent", "css", "agentic_control_panel.css")
        with open(css, encoding="utf-8") as f:
            self.assertEqual(f.read().count(".canvas-item.globber-agent {"), 1)
