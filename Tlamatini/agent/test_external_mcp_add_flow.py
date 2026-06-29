"""Certify the fix for: "I don't have a file-writing or shell tool bound this turn"
when the user asks to add an MCP (e.g. 'add the redis MCP') under Multi-Turn.

Root cause was a real capability gap: the External-MCP tool surface was READ-ONLY
(doctor / status / list_tools / call / reconnect) — there was NO tool to ADD or
ACTIVATE a server, so Tlamatini could only write the JSON by hand (file tool not
bound) or push the user to the dialog. This suite certifies the two new tools —
`external_mcp_import` + `external_mcp_set_active` — let Tlamatini do it herself,
end to end, with no file/shell tool, and that the planner force-binds them.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase

from agent import external_mcp_manager as em
from agent.global_execution_planner import _external_mcp_force_names
from agent.test_external_mcp_e2e import (
    _STDIO_PROXY_SRC,
    _bind_until,
    _reset_manager_state,
    _tool,
)


def _supervisor_tool(name):
    for tool in em._build_supervisor_tools():
        if tool.name == name:
            return tool
    return None


class ExternalMcpAddToolsExistTests(SimpleTestCase):
    def test_import_and_activate_tools_are_built(self):
        names = {t.name for t in em._build_supervisor_tools()}
        self.assertIn("external_mcp_import", names)
        self.assertIn("external_mcp_set_active", names)

    def test_recognized_as_external_mcp_tools(self):
        self.assertTrue(em.is_external_mcp_tool_name("external_mcp_import"))
        self.assertTrue(em.is_external_mcp_tool_name("external_mcp_set_active"))
        self.assertTrue(em.is_external_mcp_tool_name("external_mcp_wait"))

    def test_wait_tool_is_built(self):
        names = {t.name for t in em._build_supervisor_tools()}
        self.assertIn("external_mcp_wait", names)

    def test_planner_force_binds_add_tools_for_add_redis_prompt(self):
        names = (
            "external_mcp_status", "external_mcp_doctor", "external_mcp_import",
            "external_mcp_set_active", "external_mcp_list_tools", "external_mcp_call",
            "external_mcp_reconnect",
        )
        tools = [type("T", (), {"name": n})() for n in names]
        forced = _external_mcp_force_names("add the redis mcp to tlamatini", tools)
        self.assertIn("external_mcp_import", forced)
        self.assertIn("external_mcp_set_active", forced)


class ExternalMcpAddFlowTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(_reset_manager_state)
        self.tmp = tempfile.mkdtemp(prefix="extmcp_add_")
        self.addCleanup(self._rm)
        self.catalog = os.path.join(self.tmp, "external_mcps.json")
        p = patch.object(em, "catalog_path", return_value=self.catalog)
        p.start()
        self.addCleanup(p.stop)

    def _rm(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_llm_can_add_and_activate_redis_without_a_file_tool(self):
        # THE reported scenario: "add the redis MCP", no file/shell tool needed.
        imp = _supervisor_tool("external_mcp_import")
        setact = _supervisor_tool("external_mcp_set_active")
        redis_json = json.dumps({"mcpServers": {"redis": {
            "command": "docker", "args": ["run", "-i", "--rm", "mcp/redis"]}}})

        out = json.loads(imp.func(redis_json))
        self.assertTrue(out.get("ok"))
        self.assertIn("redis", out.get("added", []))
        self.assertIn("external_mcp_set_active", out.get("next_step", ""))
        self.assertIn("redis", em.load_catalog()["mcpServers"])

        out2 = json.loads(setact.func("redis"))
        self.assertTrue(out2.get("ok"))
        self.assertEqual(out2.get("active"), ["redis"])
        self.assertEqual(em.load_catalog()["active"], ["redis"])

    def test_import_tool_accepts_dict_via_schema(self):
        # THE bug Angela hit: the LLM passed a JSON OBJECT; the str-only schema
        # rejected it and she fumbled into "retry with a string". Now the schema
        # accepts a dict directly through tool.invoke (the real LLM call path).
        imp = _supervisor_tool("external_mcp_import")
        out = json.loads(imp.invoke({"servers_json": {
            "mcpServers": {"redis": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/redis"]}}}}))
        self.assertTrue(out.get("ok"))
        self.assertIn("redis", em.load_catalog()["mcpServers"])
        # the string form still works through the schema too
        out2 = json.loads(imp.invoke({"servers_json": json.dumps(
            {"mcpServers": {"weather": {"url": "https://example.test/mcp"}}})}))
        self.assertTrue(out2.get("ok"))
        self.assertIn("weather", em.load_catalog()["mcpServers"])

    def test_set_active_tool_accepts_list_via_schema(self):
        imp = _supervisor_tool("external_mcp_import")
        setact = _supervisor_tool("external_mcp_set_active")
        imp.invoke({"servers_json": {"mcpServers": {
            "a": {"command": "npx", "args": ["-y", "pa"]},
            "b": {"command": "npx", "args": ["-y", "pb"]}}}})
        out = json.loads(setact.invoke({"server_keys": ["a", "b"]}))  # list form
        self.assertEqual(set(out["active"]), {"a", "b"})
        out2 = json.loads(setact.invoke({"server_keys": "a"}))  # string form
        self.assertEqual(out2["active"], ["a"])

    def test_import_accepts_bare_single_server_then_caps_active_at_five(self):
        imp = _supervisor_tool("external_mcp_import")
        setact = _supervisor_tool("external_mcp_set_active")
        imp.func(json.dumps({"name": "weather", "url": "https://example.test/mcp"}))
        self.assertIn("weather", em.load_catalog()["mcpServers"])
        for i in range(6):
            imp.func(json.dumps({"mcpServers": {f"s{i}": {"command": "npx", "args": ["-y", f"p{i}"]}}}))
        out = json.loads(setact.func(",".join(f"s{i}" for i in range(6))))
        self.assertLessEqual(len(out["active"]), em.MAX_ACTIVE)
        self.assertEqual(len(out["active"]), 5)

    def test_import_handles_bad_json_gracefully(self):
        imp = _supervisor_tool("external_mcp_import")
        out = json.loads(imp.func("{not valid json"))
        self.assertFalse(out.get("ok"))
        self.assertIn("invalid JSON", out.get("error", ""))

    def test_wait_fast_fails_on_unknown_and_inactive(self):
        # The fast-fail paths return immediately (no blocking loop): unknown server
        # and catalogued-but-inactive server both give a clear, actionable error.
        out = em.wait_for_server("nope", timeout_seconds=90)
        self.assertFalse(out.get("ok"))
        self.assertIn("unknown MCP server", out.get("error", ""))
        em.import_servers({"mcpServers": {"idle": {"command": "npx", "args": ["-y", "x"]}}})
        out2 = em.wait_for_server("idle", timeout_seconds=90)  # imported but not active
        self.assertFalse(out2.get("ok"))
        self.assertIn("not active", out2.get("error", ""))

    def test_doctor_unknown_server_points_at_import_tool(self):
        # The exact thing the LLM saw ("unknown MCP server: redis") now carries an
        # actionable next step naming external_mcp_import instead of dead-ending.
        result = em.diagnose_server("redis")
        self.assertFalse(result.get("ok"))
        self.assertIn("external_mcp_import", result.get("next_step", ""))

    def test_add_then_connect_and_call_end_to_end(self):
        proxy = os.path.join(self.tmp, "proxy.py")
        with open(proxy, "w", encoding="utf-8") as fh:
            fh.write(_STDIO_PROXY_SRC)
        imp = _supervisor_tool("external_mcp_import")
        setact = _supervisor_tool("external_mcp_set_active")
        imp.func(json.dumps({"mcpServers": {"echosrv": {"command": sys.executable, "args": [proxy]}}}))
        setact.func("echosrv")
        tools = _bind_until("echosrv", "echo")
        echo = _tool(tools, "echosrv", "echo")
        self.assertIsNotNone(echo, "imported + activated MCP never bound its tools")
        self.assertEqual(echo.invoke({"text": "added-via-tool"}), "echo:added-via-tool")
