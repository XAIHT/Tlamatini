# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""End-to-end loopback tests for the External MCP network transports.

These are deliberately NOT mocks. Each test stands up a tiny REAL MCP server
(streamable-http via ``http.server``, legacy SSE via ``http.server``, and
WebSocket via ``websockets.sync.server``) on an ephemeral localhost port, then
drives the matching client (``_StreamableHttpMcpClient`` / ``_SseMcpClient`` /
``_WebSocketMcpClient``) through the full MCP handshake: connect -> initialize
-> tools/list -> tools/call -> close. If a transport client is subtly wrong,
these round-trips fail — which is the whole point (a passing mock would give
false confidence).

The suite also pins the SAFE-degradation contract that makes "MCPs never fail"
real: an unreachable server, an unsupported carrier, and a bad URL must all
resolve to a clean ``None`` + recorded error (never a crash, never a hang into
the chat-build path), and network clients must be invisible to the command
watchdog (no child PID).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from django.test import SimpleTestCase

from agent import external_mcp_manager as em


# ---------------------------------------------------------------------------
# Shared MCP server brain: one JSON-RPC request -> one response (or None for a
# notification). Exposes a single "echo" tool so tools/list and tools/call can
# both be asserted.
# ---------------------------------------------------------------------------

_TOOL_DEF = {
    "name": "echo",
    "description": "Echo the provided text back.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


def _handle_rpc(msg: dict):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "loopback-mcp", "version": "1.0"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [_TOOL_DEF]}}
    if method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": f"echo:{args.get('text', '')}"}],
            "isError": False,
        }}
    if mid is None:
        return None  # a notification (e.g. notifications/initialized)
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}


# ---------------------------------------------------------------------------
# Streamable HTTP server (single endpoint, application/json responses)
# ---------------------------------------------------------------------------

class _StreamableHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        try:
            msg = json.loads(body or b"{}")
        except Exception:
            msg = {}
        resp = _handle_rpc(msg)
        if resp is None:
            self.send_response(202)
            self.send_header("Mcp-Session-Id", "loopback-session")
            self.end_headers()
            return
        payload = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Mcp-Session-Id", "loopback-session")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence test server logging
        pass


# ---------------------------------------------------------------------------
# Legacy SSE server (GET announces a POST endpoint; responses stream back)
# ---------------------------------------------------------------------------

class _SseHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(b"event: endpoint\ndata: /messages\n\n")
            self.wfile.flush()
            while True:
                try:
                    resp = self.server.rpc_queue.get(timeout=20)
                except Exception:
                    break
                if resp is None:
                    break
                frame = f"event: message\ndata: {json.dumps(resp)}\n\n".encode("utf-8")
                self.wfile.write(frame)
                self.wfile.flush()
        except Exception:
            pass

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        try:
            msg = json.loads(body or b"{}")
        except Exception:
            msg = {}
        resp = _handle_rpc(msg)
        self.send_response(202)
        self.end_headers()
        if resp is not None:
            self.server.rpc_queue.put(resp)

    def log_message(self, *args):
        pass


def _start_http_server(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    server.daemon_threads = True
    import queue as _queue
    server.rpc_queue = _queue.Queue()
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


# ---------------------------------------------------------------------------
# WebSocket server
# ---------------------------------------------------------------------------

def _start_ws_server():
    from websockets.sync.server import serve

    def _handler(websocket):
        try:
            for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                resp = _handle_rpc(msg)
                if resp is not None:
                    websocket.send(json.dumps(resp))
        except Exception:
            pass

    server = serve(_handler, "127.0.0.1", 0)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


class ExternalMcpStreamableHttpTransportTests(SimpleTestCase):
    def test_streamable_http_round_trip(self):
        server, port = _start_http_server(_StreamableHandler)
        try:
            client = em._StreamableHttpMcpClient("Loop", f"http://127.0.0.1:{port}/")
            client.connect()
            self.assertTrue(client.alive())
            self.assertEqual(len(client.tools), 1)
            self.assertEqual(client.tools[0]["name"], "echo")
            self.assertEqual(client._session_id, "loopback-session")
            out = client.call_tool("echo", {"text": "hi"})
            self.assertEqual(out, "echo:hi")
            self.assertGreater(client.refresh_tools(), 0)
            client.close()
            self.assertFalse(client.alive())
        finally:
            server.shutdown()

    def test_make_client_picks_streamable_http(self):
        client = em._make_client("X", {"transport": "streamable-http", "url": "https://x/mcp"})
        self.assertIsInstance(client, em._StreamableHttpMcpClient)
        client = em._make_client("Y", {"url": "https://x/mcp"})  # http url -> streamable-http
        self.assertIsInstance(client, em._StreamableHttpMcpClient)


class ExternalMcpSseTransportTests(SimpleTestCase):
    def test_sse_round_trip(self):
        server, port = _start_http_server(_SseHandler)
        try:
            client = em._SseMcpClient("LoopSSE", f"http://127.0.0.1:{port}/sse")
            client.connect()
            self.assertTrue(client.alive())
            self.assertTrue(client._endpoint.endswith("/messages"))
            self.assertEqual(len(client.tools), 1)
            out = client.call_tool("echo", {"text": "sse"})
            self.assertEqual(out, "echo:sse")
            client.close()
        finally:
            server.rpc_queue.put(None)
            server.shutdown()

    def test_make_client_picks_sse(self):
        client = em._make_client("S", {"transport": "sse", "url": "https://x/sse"})
        self.assertIsInstance(client, em._SseMcpClient)


class ExternalMcpWebSocketTransportTests(SimpleTestCase):
    def test_websocket_round_trip(self):
        server, port = _start_ws_server()
        try:
            client = em._WebSocketMcpClient("LoopWS", f"ws://127.0.0.1:{port}")
            client.connect()
            self.assertTrue(client.alive())
            self.assertEqual(len(client.tools), 1)
            out = client.call_tool("echo", {"text": "ws"})
            self.assertEqual(out, "echo:ws")
            self.assertGreater(client.refresh_tools(), 0)
            client.close()
            self.assertFalse(client.alive())
        finally:
            server.shutdown()

    def test_make_client_picks_websocket(self):
        client = em._make_client("W", {"transport": "websocket", "url": "ws://x/ws"})
        self.assertIsInstance(client, em._WebSocketMcpClient)
        client = em._make_client("W2", {"url": "wss://x/ws"})  # ws url -> websocket
        self.assertIsInstance(client, em._WebSocketMcpClient)


class ExternalMcpSafeDegradationTests(SimpleTestCase):
    """The "never fail" contract: bad input degrades, it does not crash or hang."""

    def test_unsupported_transport_returns_none_with_reason(self):
        em._last_errors.pop("TcpServer", None)
        client = em._connect("TcpServer", {"transport": "tcp", "url": "tcp://127.0.0.1:9"})
        self.assertIsNone(client)
        self.assertIn("tcp", em._last_errors.get("TcpServer", "").lower())

    def test_unreachable_http_returns_none_fast(self):
        # Port 1 is not listening; connect must fail cleanly, not raise or hang.
        em._last_errors.pop("Dead", None)
        start = time.monotonic()
        client = em._connect("Dead", {"transport": "streamable-http", "url": "http://127.0.0.1:1/mcp"})
        elapsed = time.monotonic() - start
        self.assertIsNone(client)
        self.assertTrue(em._last_errors.get("Dead"))
        self.assertLess(elapsed, em._connect_timeout() + 30.0)

    def test_make_client_rejects_urlless_network_spec(self):
        with self.assertRaises(Exception):
            em._make_client("NoUrl", {"transport": "websocket"})

    def test_network_clients_have_no_watchdog_pid(self):
        # A network client carries no child process, so external_mcp_root_pids
        # (the watchdog exemption) must never surface a PID for it.
        client = em._StreamableHttpMcpClient("NoProc", "http://127.0.0.1:9/mcp")
        self.assertIsNone(getattr(client, "proc", "missing"))

    def test_free_port_helper_smoke(self):
        # Sanity: ephemeral bind works in this environment (guards the suite).
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.assertGreater(sock.getsockname()[1], 0)
        sock.close()
