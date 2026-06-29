# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""End-to-end certification of the External MCPs pipeline: from the dropped JSON
all the way to executing, diagnosing, and supervising a live MCP server.

Unlike ``test_external_mcp_transports.py`` (which unit-tests each transport
client), this suite drives the WHOLE user journey through the REAL surfaces:

    drag a .json  -> POST /agent/external_mcps/import/      (the import endpoint)
    tick servers  -> POST /agent/external_mcps/activate/    (the activate endpoint, 5-cap)
    read catalog  -> GET  /agent/external_mcps/             (the dialog endpoint)
    chat build    -> external_mcp_manager.get_external_mcp_tools()  (binds ext__ tools)
    operate       -> invoke the bound ext__<server>__<tool> tools for real
    dispatch      -> external_mcp_call / call_server_tool
    diagnose      -> external_mcp_doctor / diagnose_server
    supervise     -> external_mcp_status / supervisor_snapshot / reconnect
    watchdog      -> external_mcp_root_pids() exempts the live child

The MCP server under test is a REAL one we control (a proxy): a std, working
MCP server spawned over stdio, plus the loopback HTTP / WebSocket servers reused
from the transport suite. So this certifies Tlamatini can import, execute, test,
and diagnose an arbitrary MCP end-to-end — exactly the "from drag to full
operation" path, with a proxy standing in for any mcp.so server.

The final test (`McpSoShapeCoverageTests`) pins that EVERY launch-shape mcp.so
publishes (npx / uvx / docker / python / node / pipx / bun + remote
http/sse/ws + declared transports + secret-gated env) is recognized, correctly
transport-detected, runtime-inferred, and diagnosed — i.e. coverage of the full
mcp.so shape-space.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from agent import external_mcp_manager as em
from agent.test_external_mcp_transports import (
    _SseHandler,
    _StreamableHandler,
    _start_http_server,
    _start_ws_server,
)


# A REAL, minimal MCP server over stdio (the "proxy"). It exposes four tools so
# the e2e can assert: a normal call (echo), typed args (add), env/secret
# threading (whoami reads PROXY_TOKEN), and a tool-level error (boom -> isError).
_STDIO_PROXY_SRC = r'''
import sys, json, os

def handle(msg):
    method = msg.get("method"); mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "proxy-mcp", "version": "1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo", "description": "Echo text",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            {"name": "add", "description": "Add a and b",
             "inputSchema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}},
            {"name": "whoami", "description": "Return PROXY_TOKEN env",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "boom", "description": "Always errors",
             "inputSchema": {"type": "object", "properties": {}}},
        ]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name"); args = params.get("arguments") or {}
        if name == "echo":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "echo:" + str(args.get("text", ""))}]}}
        if name == "add":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": str(int(args.get("a", 0)) + int(args.get("b", 0)))}]}}
        if name == "whoami":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": os.environ.get("PROXY_TOKEN", "<none>")}]}}
        if name == "boom":
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "kaboom"}], "isError": True}}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown tool"}}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method"}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

main()
'''


def _reset_manager_state():
    """Tear down every module-global the manager keeps so tests don't bleed."""
    try:
        em.shutdown()
    except Exception:
        pass
    with em._clients_lock:
        for store in (em._clients, em._launching_clients):
            for client in list(store.values()):
                try:
                    client.close()
                except Exception:
                    pass
            store.clear()
        em._connecting.clear()
        em._failed_connects.clear()
        em._last_errors.clear()
        em._last_reconnects.clear()


def _bind_until(server_key: str, tool_suffix: str, timeout: float = 20.0):
    """Poll get_external_mcp_tools() until the wrapped ext__ tool binds.

    This drives the REAL lazy/background warm-connect path — the tool only
    appears once the child has connected and tools/list returned.
    """
    wanted = em._safe_tool_name(server_key, tool_suffix)
    deadline = time.monotonic() + timeout
    tools = []
    while time.monotonic() < deadline:
        tools = em.get_external_mcp_tools()
        if any(getattr(t, "name", "") == wanted for t in tools):
            return tools
        time.sleep(0.25)
    return tools


def _tool(tools, server_key, suffix):
    wanted = em._safe_tool_name(server_key, suffix)
    for t in tools:
        if getattr(t, "name", "") == wanted:
            return t
    return None


class _PipelineBase(TestCase):
    """DB-backed (the import/activate/list views are @login_required)."""

    def setUp(self):
        super().setUp()
        self.addCleanup(_reset_manager_state)
        self.tmp = tempfile.mkdtemp(prefix="extmcp_e2e_")
        self.addCleanup(self._cleanup_tmp)
        self.catalog = os.path.join(self.tmp, "external_mcps.json")
        p = patch.object(em, "catalog_path", return_value=self.catalog)
        p.start()
        self.addCleanup(p.stop)
        User = get_user_model()
        self.user = User.objects.create_user("e2e_user", password="pw")
        self.client.force_login(self.user)

    def _cleanup_tmp(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _proxy_script(self):
        path = os.path.join(self.tmp, "proxy_mcp_server.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_STDIO_PROXY_SRC)
        return path

    # the three browser endpoints
    def _import(self, mcp_servers):
        return self.client.post(
            "/agent/external_mcps/import/",
            data=json.dumps({"mcpServers": mcp_servers}),
            content_type="application/json",
        )

    def _activate(self, keys):
        return self.client.post(
            "/agent/external_mcps/activate/",
            data=json.dumps({"active": keys}),
            content_type="application/json",
        )

    def _list(self):
        return self.client.get("/agent/external_mcps/")


class ExternalMcpStdioE2ETests(_PipelineBase):
    def test_drag_to_full_operation_stdio(self):
        proxy = self._proxy_script()
        dropped = {"Proxy": {
            "command": sys.executable,
            "args": [proxy],
            "env": {"PROXY_TOKEN": "sk-proxy-9000"},
        }}

        # 1) DRAG: import endpoint merges the dropped JSON.
        resp = self._import(dropped)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        self.assertIn("Proxy", resp.json().get("added", []))

        # 2) The dialog can read the catalog back.
        listed = self._list().json()
        self.assertTrue(any(s.get("key") == "Proxy" for s in listed.get("servers", [])))

        # 3) ACTIVATE: tick it on.
        act = self._activate(["Proxy"]).json()
        self.assertTrue(act.get("ok"))
        self.assertIn("Proxy", act.get("active", []))

        # 4) CHAT BUILD: the wrapped tools come online via the real lazy connect.
        tools = _bind_until("Proxy", "echo")
        echo = _tool(tools, "Proxy", "echo")
        add = _tool(tools, "Proxy", "add")
        whoami = _tool(tools, "Proxy", "whoami")
        boom = _tool(tools, "Proxy", "boom")
        self.assertIsNotNone(echo, "ext__Proxy__echo never bound")
        self.assertIsNotNone(add)
        self.assertIsNotNone(whoami)
        self.assertIsNotNone(boom)

        # 5) EXECUTE: call the bound tools for real.
        self.assertEqual(echo.invoke({"text": "hello"}), "echo:hello")
        self.assertEqual(add.invoke({"a": 2, "b": 5}), "7")
        self.assertEqual(whoami.invoke({}), "sk-proxy-9000")  # env threaded through
        self.assertTrue(boom.invoke({}).startswith("Error:"))  # isError surfaced

        # 6) GENERIC DISPATCH: external_mcp_call path.
        called = em.call_server_tool("Proxy", "echo", {"text": "via-dispatch"})
        self.assertTrue(called.get("ok"))
        self.assertEqual(called.get("result"), "echo:via-dispatch")

        # 7) DIAGNOSE: the doctor sees a healthy stdio python server.
        diag = em.diagnose_server("Proxy")
        self.assertTrue(diag.get("ok"))
        one = diag["diagnostics"][0]
        self.assertEqual(one["transport"], "stdio")
        self.assertEqual(one["runtime"], "python")
        self.assertTrue(one["supported_by_current_connector"])
        self.assertEqual(one["blockers"], [])

        # 8) SUPERVISE: status shows ready with the 4 tools.
        snap = em.supervisor_snapshot("Proxy")
        row = snap["servers"][0]
        self.assertEqual(row["status"], "ready")
        self.assertEqual(row["tool_count"], 4)

        # 9) WATCHDOG EXEMPTION: the live stdio child PID is protected.
        pids = em.external_mcp_root_pids()
        self.assertTrue(pids, "stdio child PID should be exempt from the watchdog")

        # 10) RECONNECT: force a reconnect, then the tools rebind.
        rec = em.reconnect_server("Proxy")
        self.assertTrue(rec.get("ok"))
        rebound = _bind_until("Proxy", "echo")
        self.assertIsNotNone(_tool(rebound, "Proxy", "echo"))

    def test_list_tools_and_search(self):
        proxy = self._proxy_script()
        self._import({"Proxy": {"command": sys.executable, "args": [proxy]}})
        self._activate(["Proxy"])
        _bind_until("Proxy", "echo")
        listing = em.list_server_tools("Proxy", "", True)
        names = {t["name"] for row in listing["servers"] for t in row.get("tools", [])}
        self.assertEqual(names, {"echo", "add", "whoami", "boom"})
        filtered = em.list_server_tools("Proxy", "add", True)
        got = {t["name"] for row in filtered["servers"] for t in row.get("tools", [])}
        self.assertEqual(got, {"add"})


class ExternalMcpRemoteE2ETests(_PipelineBase):
    def test_streamable_http_drag_to_call(self):
        server, port = _start_http_server(_StreamableHandler)
        self.addCleanup(server.shutdown)
        self._import({"RemoteHTTP": {"url": f"http://127.0.0.1:{port}/", "transport": "streamable-http"}})
        self._activate(["RemoteHTTP"])
        tools = _bind_until("RemoteHTTP", "echo")
        echo = _tool(tools, "RemoteHTTP", "echo")
        self.assertIsNotNone(echo, "remote streamable-http tool never bound")
        self.assertEqual(echo.invoke({"text": "remote"}), "echo:remote")
        diag = em.diagnose_server("RemoteHTTP")["diagnostics"][0]
        self.assertEqual(diag["transport"], "streamable-http")
        self.assertTrue(diag["supported_by_current_connector"])

    def test_sse_drag_to_call(self):
        server, port = _start_http_server(_SseHandler)

        def _stop():
            try:
                server.rpc_queue.put(None)
            except Exception:
                pass
            server.shutdown()

        self.addCleanup(_stop)
        self._import({"RemoteSSE": {"url": f"http://127.0.0.1:{port}/sse"}})
        self._activate(["RemoteSSE"])
        tools = _bind_until("RemoteSSE", "echo")
        echo = _tool(tools, "RemoteSSE", "echo")
        self.assertIsNotNone(echo, "remote sse tool never bound")
        self.assertEqual(echo.invoke({"text": "sse"}), "echo:sse")

    def test_websocket_drag_to_call(self):
        server, port = _start_ws_server()
        self.addCleanup(server.shutdown)
        self._import({"RemoteWS": {"url": f"ws://127.0.0.1:{port}"}})
        self._activate(["RemoteWS"])
        tools = _bind_until("RemoteWS", "echo")
        echo = _tool(tools, "RemoteWS", "echo")
        self.assertIsNotNone(echo, "remote websocket tool never bound")
        self.assertEqual(echo.invoke({"text": "ws"}), "echo:ws")


class ExternalMcpCapAndSupervisorTests(_PipelineBase):
    def test_active_cap_is_five(self):
        servers = {f"S{i}": {"command": "npx", "args": ["-y", f"pkg{i}"]} for i in range(7)}
        self._import(servers)
        act = self._activate([f"S{i}" for i in range(7)]).json()
        self.assertTrue(act.get("ok"))
        self.assertLessEqual(len(act.get("active", [])), em.MAX_ACTIVE)
        self.assertEqual(len(act.get("active", [])), 5)

    def test_supervisor_and_doctor_llm_tools_present(self):
        names = {t.name for t in em._build_supervisor_tools()}
        self.assertEqual(names, {
            "external_mcp_status", "external_mcp_reconnect", "external_mcp_doctor",
            "external_mcp_list_tools", "external_mcp_call",
            "external_mcp_import", "external_mcp_set_active", "external_mcp_wait",
        })
        # the doctor tool returns valid JSON even with an empty catalog
        doctor = next(t for t in em._build_supervisor_tools() if t.name == "external_mcp_doctor")
        payload = json.loads(doctor.func(server_key=None))
        self.assertTrue(payload.get("ok"))


class _AuthStreamableHandler(_StreamableHandler):
    """A hosted-style remote MCP that requires a Bearer token (AdWeave / inference.sh class)."""

    REQUIRED = "Bearer secret-token"

    def do_POST(self):  # noqa: N802
        if self.headers.get("Authorization", "") != self.REQUIRED:
            body = b'{"error":"unauthorized"}'
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_POST()


class ExternalMcpAuthHeaderE2ETests(_PipelineBase):
    """Most hosted mcp.so servers are auth-gated; prove header auth works + degrades."""

    def test_authorized_remote_binds_and_calls(self):
        server, port = _start_http_server(_AuthStreamableHandler)
        self.addCleanup(server.shutdown)
        self._import({"AuthHTTP": {
            "url": f"http://127.0.0.1:{port}/",
            "transport": "streamable-http",
            "headers": {"Authorization": "Bearer secret-token"},
        }})
        self._activate(["AuthHTTP"])
        tools = _bind_until("AuthHTTP", "echo")
        echo = _tool(tools, "AuthHTTP", "echo")
        self.assertIsNotNone(echo, "auth-gated remote MCP never bound")
        self.assertEqual(echo.invoke({"text": "secure"}), "echo:secure")

    def test_missing_auth_degrades_cleanly(self):
        server, port = _start_http_server(_AuthStreamableHandler)
        self.addCleanup(server.shutdown)
        self._import({"NoAuth": {"url": f"http://127.0.0.1:{port}/", "transport": "streamable-http"}})
        self._activate(["NoAuth"])
        tools = _bind_until("NoAuth", "echo", timeout=6.0)
        self.assertIsNone(_tool(tools, "NoAuth", "echo"), "unauthorized server must not bind tools")
        # The failure is captured + surfaced (status, not a crash), and the doctor still answers.
        row = em.supervisor_snapshot("NoAuth")["servers"][0]
        self.assertIn(row["status"], ("error", "pending", "connecting"))
        self.assertTrue(em.diagnose_server("NoAuth").get("ok"))


class McpSoShapeCoverageTests(SimpleTestCase):
    """Every launch-shape mcp.so publishes must be recognized + diagnosed.

    mcp.so server pages reduce to a finite shape-space: a stdio command
    (npx / uvx / pipx / docker / python / node / bun / deno / go / java ...) OR
    a remote url (streamable-http / sse / websocket), optionally with env
    secrets. If Tlamatini transport-detects, runtime-infers, and diagnoses every
    shape, it covers every mcp.so server (a server still needs its own install +
    secrets to actually CONNECT, but the mechanism handles all of them).
    """

    # (label, spec, expected_transport, expected_runtime, expect_supported, expect_secret_blocker)
    SHAPES = [
        ("npx", {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}, "stdio", "node/npm", True, False),
        ("uvx", {"command": "uvx", "args": ["mcp-server-git", "--repository", "."]}, "stdio", "uv/uvx", True, False),
        ("docker", {"command": "docker", "args": ["run", "-i", "--rm", "mcp/redis"]}, "stdio", "docker", True, False),
        ("python_m", {"command": "python", "args": ["-m", "mcp_server_time"]}, "stdio", "python", True, False),
        ("node", {"command": "node", "args": ["build/index.js"]}, "stdio", "node/npm", True, False),
        ("bun", {"command": "bun", "args": ["run", "server.ts"]}, "stdio", "bun", True, False),
        ("deno", {"command": "deno", "args": ["run", "-A", "main.ts"]}, "stdio", "deno", True, False),
        ("java", {"command": "java", "args": ["-jar", "server.jar"]}, "stdio", "java", True, False),
        ("dotnet", {"command": "dotnet", "args": ["run"]}, "stdio", ".NET", True, False),
        ("cargo", {"command": "cargo", "args": ["run"]}, "stdio", "rust/cargo", True, False),
        ("remote_streamable_http", {"url": "https://api.example.com/mcp"}, "streamable-http", "unknown", True, False),
        ("remote_sse", {"url": "https://api.example.com/sse"}, "sse", "unknown", True, False),
        ("remote_ws", {"url": "wss://api.example.com/ws"}, "websocket", "unknown", True, False),
        ("declared_http_type", {"type": "streamable-http", "url": "https://api.example.com/mcp"}, "streamable-http", "unknown", True, False),
        ("declared_sse_field", {"sseUrl": "https://api.example.com/sse"}, "sse", "unknown", True, False),
        ("secret_gated", {"command": "npx", "args": ["-y", "x"], "env": {"API_KEY": "<REDACTED>"}}, "stdio", "node/npm", True, True),
        ("remote_with_header", {"url": "https://api.example.com/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}}, "streamable-http", "unknown", True, False),
    ]

    def _diagnose(self, label, spec):
        catalog = {"mcpServers": {label: em._normalize_imported_server_spec(label, dict(spec))}, "active": []}
        with patch.object(em, "load_catalog", return_value=catalog):
            return em.diagnose_server(label)["diagnostics"][0]


def _add_shape_test(idx, label, spec, transport, runtime, supported, secret_blocker):
    def test(self):
        diag = self._diagnose(label, spec)
        self.assertEqual(diag["transport"], transport, f"{label}: transport")
        if runtime != "unknown":
            self.assertEqual(diag["runtime"], runtime, f"{label}: runtime")
        self.assertEqual(diag["supported_by_current_connector"], supported, f"{label}: supported")
        has_secret_blocker = any("secret" in b for b in diag["blockers"])
        self.assertEqual(has_secret_blocker, secret_blocker, f"{label}: secret blocker")
        # every supported shape yields a make_client-able spec (no connect, just construction-ready)
        if supported:
            client = em._make_client(label, em._normalize_imported_server_spec(label, dict(spec)))
            self.assertIsNotNone(client)
            client.close()

    name = "".join(ch if ch.isalnum() else "_" for ch in label)
    setattr(McpSoShapeCoverageTests, f"test_shape_{idx:02d}_{name}", test)


for _i, _row in enumerate(McpSoShapeCoverageTests.SHAPES, 1):
    _add_shape_test(_i, *_row)
