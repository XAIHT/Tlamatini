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
HARD real-scenario tests for the **Editor** agent (surgical in-place find/replace).

The behaviour tests run the REAL ``agent/agents/editor/editor.py`` as a subprocess
against tailored ``config.yaml`` files in throwaway dirs (no mocking of the thing
under test), covering every status path the agent can emit and the byte-exact
contract (backslashes + CRLF preserved). The registry tests assert the agent is
wired into the wrapped-tool registry, the Agent-Contract / Parametrizer fields,
the Exec-Report map, the URL route, and the canvas CSS.
"""
import base64
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
EDITOR_PY = os.path.join(_THIS_DIR, "agents", "editor", "editor.py")
EDITOR_CFG = os.path.join(_THIS_DIR, "agents", "editor", "config.yaml")


def _run_editor(target_path, **over):
    """Copy editor.py into an isolated 'editor' dir, write config.yaml, run it,
    and return (log_text, result_file_bytes_or_None)."""
    tmp = tempfile.mkdtemp(prefix="editor_test_")
    edir = os.path.join(tmp, "editor")
    os.makedirs(edir, exist_ok=True)
    try:
        shutil.copy(EDITOR_PY, os.path.join(edir, "editor.py"))
        cfg = {
            "file_path": target_path,
            "old_string": over.get("old_string", ""),
            "new_string": over.get("new_string", ""),
            "old_string_b64": over.get("old_string_b64", ""),
            "new_string_b64": over.get("new_string_b64", ""),
            "replace_all": over.get("replace_all", False),
            "source_agents": [],
            "target_agents": over.get("target_agents", []),
        }
        with open(os.path.join(edir, "config.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        subprocess.run(
            [sys.executable, "editor.py"], cwd=edir, timeout=60, capture_output=True,
        )
        with open(os.path.join(edir, "editor.log"), encoding="utf-8") as f:
            log = f.read()
        data = None
        if target_path and os.path.isfile(target_path):
            with open(target_path, "rb") as f:
                data = f.read()
        return log, data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _section(log):
    m = re.search(r"INI_SECTION_EDITOR<<<(.*?)>>>END_SECTION_EDITOR", log, re.S)
    assert m, f"no INI_SECTION_EDITOR in log:\n{log}"
    body = m.group(1)
    status = re.search(r"status:\s*(\S+)", body).group(1)
    repl = int(re.search(r"replacements:\s*(\d+)", body).group(1))
    return status, repl


class EditorAgentBehaviorTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="editor_target_")
        self.target = os.path.join(self.tmp, "sample.txt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, data: bytes):
        with open(self.target, "wb") as f:
            f.write(data)

    def test_edited_unique(self):
        self._write(b"alpha\nKEY=1\nomega\n")
        log, data = _run_editor(self.target, old_string="KEY=1", new_string="KEY=2")
        self.assertEqual(_section(log), ("edited", 1))
        self.assertEqual(data, b"alpha\nKEY=2\nomega\n")
        self.assertIn("Editor agent finished", log)

    def test_not_found(self):
        self._write(b"nothing here\n")
        log, data = _run_editor(self.target, old_string="MISSING", new_string="X")
        self.assertEqual(_section(log)[0], "not_found")
        self.assertEqual(data, b"nothing here\n")  # untouched

    def test_not_unique_refuses(self):
        self._write(b"dup\ndup\n")
        log, data = _run_editor(self.target, old_string="dup", new_string="x")
        self.assertEqual(_section(log)[0], "not_unique")
        self.assertEqual(data, b"dup\ndup\n")  # untouched - refused

    def test_replace_all(self):
        self._write(b"dup\ndup\ndup\n")
        log, data = _run_editor(self.target, old_string="dup", new_string="x", replace_all=True)
        self.assertEqual(_section(log), ("edited", 3))
        self.assertEqual(data, b"x\nx\nx\n")

    def test_noop_when_equal(self):
        self._write(b"same value here\n")
        log, data = _run_editor(self.target, old_string="value", new_string="value")
        self.assertEqual(_section(log)[0], "noop")
        self.assertEqual(data, b"same value here\n")

    def test_missing_file(self):
        log, _ = _run_editor(os.path.join(self.tmp, "does_not_exist.txt"),
                             old_string="a", new_string="b")
        self.assertEqual(_section(log)[0], "not_found")

    def test_byte_exact_backslashes_via_b64(self):
        # A real source line with single backslashes must survive verbatim.
        self._write(b'path = "C:\\Temp\\x"\n')
        old_b64 = base64.b64encode(b"C:\\Temp\\x").decode()
        new_b64 = base64.b64encode(b"C:\\Temp\\y").decode()
        log, data = _run_editor(self.target, old_string_b64=old_b64, new_string_b64=new_b64)
        self.assertEqual(_section(log), ("edited", 1))
        self.assertEqual(data, b'path = "C:\\Temp\\y"\n')  # backslashes preserved exactly

    def test_crlf_preserved(self):
        self._write(b"line1\r\nTOKEN\r\nline3\r\n")
        log, data = _run_editor(self.target, old_string="TOKEN", new_string="DONE")
        self.assertEqual(_section(log), ("edited", 1))
        self.assertEqual(data, b"line1\r\nDONE\r\nline3\r\n")  # CRLF intact


class EditorWiringTests(SimpleTestCase):
    def test_config_parses_and_has_keys(self):
        with open(EDITOR_CFG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        for k in ("file_path", "old_string", "new_string", "old_string_b64",
                  "new_string_b64", "replace_all", "source_agents", "target_agents"):
            self.assertIn(k, cfg)

    def test_wrapped_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get("chat_agent_editor")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, "Editor")
        self.assertEqual(spec.template_dir, "editor")

    def test_exec_report_membership(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get("chat_agent_editor"), ("editor", "Editor"))

    def test_agent_contract_parametrizer_fields(self):
        from agent.services.agent_contracts import get_agent_contract
        c = get_agent_contract("editor")
        for fld in ("file_path", "status", "replacements", "response_body"):
            self.assertIn(fld, c.parametrizer_fields)

    def test_url_route_resolves(self):
        url = reverse("update_editor_connection", args=["editor-1"])
        self.assertIn("update_editor_connection/editor-1/", url)

    def test_parametrizer_section_type_registered(self):
        param = os.path.join(_THIS_DIR, "agents", "parametrizer", "parametrizer.py")
        with open(param, encoding="utf-8") as f:
            self.assertIn("'editor'", f.read())

    def test_canvas_css_class_present_and_unique(self):
        css = os.path.join(_THIS_DIR, "static", "agent", "css", "agentic_control_panel.css")
        with open(css, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count(".canvas-item.editor-agent {"), 1)
