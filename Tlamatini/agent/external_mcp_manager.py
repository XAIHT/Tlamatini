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
External MCP client layer.

Lets Tlamatini connect to arbitrary external MCP servers declared in
``external_mcps.json`` (the standard ``mcpServers`` shape, identical to a
Claude-Code ``.mcp.json``), discover their tools over stdio JSON-RPC, and
expose those tools to the Multi-Turn unified agent as LangChain tools — the
same way Claude Code surfaces an installed MCP.

Design contract (the "hundreds of servers" story):
  * The CATALOG (potentially hundreds of servers) lives in external_mcps.json.
  * Only the ACTIVE set (capped at ``MAX_ACTIVE`` = 5) is ever spawned and
    connected, so the LLM never sees hundreds of tools and the machine never
    spawns hundreds of subprocesses.
  * Each active server is spawned ONCE as a stdio child, kept alive, its tools
    listed + cached; tool calls reuse the live child.
  * Fully defensive: a missing / broken / slow server is skipped and never
    raises into the tool-binding path. A cleanup that crashes the chat path is
    worse than a server that fails to connect.

This is a self-contained, stdlib + langchain-core implementation (no new pip
dependency, no async event loop) — the same sync-stdio-JSON-RPC pattern the
STM32er pool agent already uses, generalised and config-driven.
"""

import atexit
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ACTIVE = 5
_MCP_PROTOCOL_VERSION = "2024-11-05"
_CALL_TIMEOUT = 120.0       # seconds for a single tools/call

_CREATE_NO_WINDOW = 0x08000000

_catalog_lock = threading.RLock()
_clients: Dict[str, "_StdioMcpClient"] = {}
_launching_clients: Dict[str, "_StdioMcpClient"] = {}
_clients_lock = threading.RLock()
# Servers with an in-flight BACKGROUND connect (so we never start two at once,
# and never connect synchronously on the chat-build path).
_connecting: set = set()
# Last connect error per server, surfaced in the log + list_catalog for
# diagnosis (e.g. "initialize timed out", a Docker daemon error, an image pull).
_last_errors: Dict[str, str] = {}
# Negative cache: a server that just failed to connect is skipped for a short
# cooldown so a down/unreachable active server isn't retried on a tight loop.
_failed_connects: Dict[str, float] = {}
_last_reconnects: Dict[str, float] = {}
_FAIL_COOLDOWN = 60.0
_ZERO_TOOL_RECONNECT_GRACE = 45.0
_ZERO_TOOL_RECONNECT_COOLDOWN = 90.0

# Carriers Tlamatini can actually CONNECT to (not merely catalogue). stdio
# launches a local child; the rest reach an already-running server over a
# network carrier. MCP is the same JSON-RPC on every one — only the carrier
# differs — so each transport client below mirrors the _StdioMcpClient surface
# and the supervisor/status/binding code treats them identically.
_HTTP_TRANSPORTS = frozenset({"streamable-http", "sse"})
_SUPPORTED_TRANSPORTS = frozenset({"stdio", "streamable-http", "sse", "websocket"})

_SUPERVISOR_TOOL_NAMES = frozenset({
    "external_mcp_status",
    "external_mcp_reconnect",
    "external_mcp_list_tools",
    "external_mcp_call",
    "external_mcp_doctor",
    "external_mcp_import",
    "external_mcp_set_active",
    "external_mcp_wait",
})


def _connect_timeout() -> float:
    """Timeout for the initialize + tools/list handshake. Generous by default —
    Docker / cold-start / npx MCP servers can take far longer than a few seconds
    to answer ``initialize`` (a first ``docker run`` may even pull an image), so
    a short timeout silently drops a perfectly valid server (this was the 12 s
    bug that killed the redis MCP). Tune via the env var
    TLAMATINI_EXTERNAL_MCP_CONNECT_TIMEOUT (seconds; default 60)."""
    raw = os.environ.get("TLAMATINI_EXTERNAL_MCP_CONNECT_TIMEOUT", "").strip()
    try:
        return max(5.0, float(raw)) if raw else 60.0
    except ValueError:
        return 60.0


# ---------------------------------------------------------------------------
# Catalog file (frozen / source aware — resolved next to config.json)
# ---------------------------------------------------------------------------

def catalog_path() -> str:
    """Resolve external_mcps.json next to config.json (CONFIG_PATH > frozen > source)."""
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path:
        base = os.path.dirname(env_path)
    elif getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "external_mcps.json")


def load_catalog() -> Dict[str, Any]:
    """Read the catalog, fail-open to an empty catalog on any error."""
    path = catalog_path()
    with _catalog_lock:
        try:
            if not os.path.exists(path):
                return {"mcpServers": {}, "active": []}
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh) or {}
        except Exception:
            logger.exception("[ExternalMCP] failed to read %s", path)
            return {"mcpServers": {}, "active": []}
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    if not isinstance(data.get("active"), list):
        data["active"] = []
    return data


def save_catalog(data: Dict[str, Any]) -> None:
    path = catalog_path()
    with _catalog_lock:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)


def _server_transport(spec: Dict[str, Any]) -> str:
    """Return the declared/derived MCP message transport.

    MCP itself is JSON-RPC. The transport is just the carrier for those frames:
    stdio, Streamable HTTP/SSE, WebSocket, TCP/raw socket, or a named pipe.
    """
    transport = str(spec.get("transport") or spec.get("type") or "").strip().lower()
    if transport in {"stdio", "streamable-http", "streamable_http", "http", "sse", "websocket", "ws", "tcp", "socket", "raw", "pipe", "named-pipe"}:
        return {
            "http": "streamable-http",
            "streamable_http": "streamable-http",
            "ws": "websocket",
            "socket": "tcp",
            "raw": "tcp",
            "pipe": "named-pipe",
        }.get(transport, transport)
    if spec.get("command"):
        return "stdio"
    url = str(spec.get("url") or "").strip().lower()
    if url.startswith(("ws://", "wss://")):
        return "websocket"
    if url.startswith(("tcp://", "socket://", "raw://")):
        return "tcp"
    if url.startswith(("pipe://", "npipe://", "unix://")):
        return "named-pipe"
    if url.startswith(("http://", "https://")):
        if spec.get("sse") or "sse" in url:
            return "sse"
        return "streamable-http"
    if spec.get("host") and spec.get("port"):
        return "tcp"
    if spec.get("socketPath") or spec.get("namedPipe") or spec.get("pipe"):
        return "named-pipe"
    return "stdio"


def _is_roblox_server(key: str, spec: Dict[str, Any]) -> bool:
    text = " ".join([
        key,
        str(spec.get("command", "")),
        " ".join(str(item) for item in (spec.get("args", []) or [])),
    ]).lower()
    return "roblox" in text or "studiomcp" in text or "mcp.bat" in text


def _zero_tool_diagnostic(key: str, spec: Dict[str, Any], client: Optional["_StdioMcpClient"]) -> str:
    tail = (getattr(client, "stderr_tail", "") or "").strip()
    if _is_roblox_server(key, spec):
        base = (
            "Roblox StudioMCP is running, but it currently exposes 0 MCP tools. "
            "In Roblox Studio, open Assistant > ... > Manage MCP Servers, turn on "
            "Enable Studio as MCP server, then confirm the green connected-client "
            "indicator. If Studio logs localhost:4932 /poll connection failures, "
            "the Studio-side local bridge is not accepting the long-poll yet."
        )
        if tail:
            return f"{base} Child stderr tail: {tail[-500:]}"
        return base
    if tail:
        return f"Connected but exposed 0 tools. Child stderr tail: {tail[-500:]}"
    return (
        "Connected but exposed 0 tools. The server may still be warming up, "
        "waiting for its backend application, or requiring an enable/authorize step."
    )


def _status_label(status: str) -> str:
    return {
        "inactive": "inactive",
        "connecting": "connecting",
        "ready": "ready",
        "no_tools": "0 tools",
        "error": "error",
        "pending": "pending",
    }.get(status, status)


def _server_status_payload(
    key: str,
    spec: Dict[str, Any],
    active: List[str],
) -> Dict[str, Any]:
    client = _clients.get(key)
    alive = bool(client and client.alive())
    connecting = key in _connecting
    error = _last_errors.get(key, "")
    tool_count = len(client.tools) if alive and client is not None else None
    pid = None
    stderr_tail = ""
    zero_tools_for = 0.0
    if client is not None:
        proc = getattr(client, "proc", None)
        pid = getattr(proc, "pid", None)
        stderr_tail = (client.stderr_tail or "")[-1000:]
        if alive and not client.tools and client.zero_tools_since:
            zero_tools_for = max(0.0, time.monotonic() - client.zero_tools_since)

    if key not in active:
        status = "inactive"
    elif connecting:
        status = "connecting"
    elif error and not alive:
        status = "error"
    elif alive and tool_count:
        status = "ready"
    elif alive:
        status = "no_tools"
    else:
        status = "pending"

    diagnostic = ""
    if status == "no_tools":
        diagnostic = _zero_tool_diagnostic(key, spec, client)
    elif status == "error":
        diagnostic = error
    elif status == "pending":
        diagnostic = "Active but not connected yet; Tlamatini will warm-connect it in the background."

    return {
        "key": key,
        "display": key.replace("_", " ").strip() or key,
        "command": spec.get("command", ""),
        "transport": _server_transport(spec),
        "active": key in active,
        "tool_count": tool_count,
        "connecting": connecting,
        "alive": alive,
        "pid": pid,
        "status": status,
        "status_label": _status_label(status),
        "error": error,
        "diagnostic": diagnostic,
        "stderr_tail": stderr_tail,
        "zero_tools_for_seconds": round(zero_tools_for, 1),
    }


def list_catalog() -> Dict[str, Any]:
    """Catalog payload for the External MCPs dialog (one entry per server)."""
    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers]
    out = []
    for key in sorted(servers.keys()):
        spec = servers[key] or {}
        out.append(_server_status_payload(key, spec, active))
    return {"servers": out, "active": active, "max_active": MAX_ACTIVE,
            "count": len(out)}


def set_active(keys: List[str]) -> Dict[str, Any]:
    """Persist the active set (capped at MAX_ACTIVE) and drop stale connections."""
    data = load_catalog()
    servers = data.get("mcpServers", {})
    valid = [k for k in keys if k in servers]
    capped = valid[:MAX_ACTIVE]
    data["active"] = capped
    save_catalog(data)
    # Close any client that is no longer active so it stops consuming a slot.
    with _clients_lock:
        for key in list(_clients.keys()):
            if key not in capped:
                try:
                    _clients.pop(key).close()
                except Exception:
                    pass
        # Re-activating a server is an explicit "try again": clear its cooldown
        # so the warm-connect below retries immediately even if it failed before.
        for key in capped:
            _failed_connects.pop(key, None)
    # Warm-connect the active servers in the BACKGROUND now, so their (possibly
    # slow / Docker / cold-start) initialize happens at Continue-click — off the
    # chat path — and the tools are usually ready by the user's next prompt.
    _warm_connect_async(capped, servers)
    return {"ok": True, "active": capped, "capped": len(valid) > MAX_ACTIVE}


def _normalize_import_args(args: Any) -> List[str]:
    if args is None:
        return []
    if isinstance(args, str):
        stripped = args.strip()
        return [stripped] if stripped else []
    if isinstance(args, (list, tuple)):
        return [str(item) for item in args if item is not None]
    return [str(args)]


def _normalize_import_env(env: Any) -> Dict[str, str]:
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items() if value is not None}


def _normalize_imported_server_spec(key: str, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize marketplace/client MCP config variants into Tlamatini's catalog shape.

    The official MCP client shape is intentionally small, but public catalogs
    commonly add fields such as ``disabled``, ``alwaysAllow``, ``type``, or
    ``transport``. Keep those fields for provenance while canonicalizing the
    pieces Tlamatini must execute: command, args, env, cwd, and url.
    """
    if not isinstance(spec, dict):
        return None
    normalized = dict(spec)

    command = normalized.get("command")
    if command is not None:
        normalized["command"] = str(command).strip()
    normalized["args"] = _normalize_import_args(normalized.get("args"))
    normalized["env"] = _normalize_import_env(normalized.get("env"))
    if normalized.get("cwd") is not None:
        normalized["cwd"] = str(normalized.get("cwd") or "").strip()

    url = (
        normalized.get("url")
        or normalized.get("endpoint")
        or normalized.get("sseUrl")
        or normalized.get("sse_url")
        or normalized.get("streamableHttpUrl")
        or normalized.get("streamable_http_url")
        or normalized.get("wsUrl")
        or normalized.get("ws_url")
        or normalized.get("websocketUrl")
        or normalized.get("webSocketUrl")
    )
    if url:
        normalized["url"] = str(url).strip()

    transport = str(normalized.get("transport") or normalized.get("type") or "").strip().lower()
    if transport:
        normalized["transport"] = transport
    elif normalized.get("sseUrl") or normalized.get("sse_url"):
        normalized["transport"] = "sse"
    elif normalized.get("streamableHttpUrl") or normalized.get("streamable_http_url"):
        normalized["transport"] = "streamable-http"
    elif normalized.get("wsUrl") or normalized.get("ws_url") or normalized.get("websocketUrl") or normalized.get("webSocketUrl"):
        normalized["transport"] = "websocket"
    elif normalized.get("host") and normalized.get("port"):
        normalized["transport"] = "tcp"
        normalized.setdefault("url", f"tcp://{normalized.get('host')}:{normalized.get('port')}")
    elif normalized.get("socketPath") or normalized.get("namedPipe") or normalized.get("pipe"):
        normalized["transport"] = "named-pipe"
        normalized.setdefault(
            "url",
            str(normalized.get("socketPath") or normalized.get("namedPipe") or normalized.get("pipe") or ""),
        )
    elif normalized.get("command"):
        normalized["transport"] = "stdio"

    if not normalized.get("command") and not normalized.get("url"):
        logger.warning(
            "[ExternalMCP] skipped imported server '%s': no command or url in spec",
            key,
        )
        return None
    return normalized


def import_servers(mcp_servers: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a dropped ``mcpServers`` map into the catalog. Returns added/updated keys."""
    if not isinstance(mcp_servers, dict) or not mcp_servers:
        return {"ok": False, "error": "no mcpServers found in payload"}
    if isinstance(mcp_servers.get("mcpServers"), dict):
        mcp_servers = mcp_servers.get("mcpServers") or {}
    if (
        "mcpServers" not in mcp_servers
        and ("command" in mcp_servers or "url" in mcp_servers or "endpoint" in mcp_servers)
    ):
        inferred = str(mcp_servers.get("name") or "Imported_MCP").strip() or "Imported_MCP"
        inferred = "".join(ch if (ch.isalnum() or ch in "_.-") else "_" for ch in inferred)
        mcp_servers = {inferred: mcp_servers}
    data = load_catalog()
    servers = data.setdefault("mcpServers", {})
    added, updated = [], []
    for key, spec in mcp_servers.items():
        server_key = str(key)
        normalized = _normalize_imported_server_spec(server_key, spec)
        if normalized is None:
            continue
        (updated if server_key in servers else added).append(server_key)
        servers[server_key] = normalized
    save_catalog(data)
    return {"ok": True, "added": added, "updated": updated}


def remove_servers(keys: List[str]) -> Dict[str, Any]:
    """Delete server(s) from the catalog (the dialog's drop/delete control).

    Drops the key(s) from ``mcpServers`` and from the ``active`` set, closes any
    live client so the slot frees immediately, and clears the negative-connect
    cooldown. Returns the keys actually removed plus any that were not found.
    """
    if isinstance(keys, str):
        keys = [keys]
    requested = [str(k) for k in (keys or []) if str(k)]
    if not requested:
        return {"ok": False, "error": "no server key(s) to remove"}
    data = load_catalog()
    servers = data.get("mcpServers", {})
    removed, missing = [], []
    for key in requested:
        if key in servers:
            servers.pop(key, None)
            removed.append(key)
        else:
            missing.append(key)
    if not removed:
        return {"ok": False, "error": "no matching server(s) in catalog",
                "missing": missing}
    data["active"] = [k for k in data.get("active", []) if k in servers]
    save_catalog(data)
    with _clients_lock:
        for key in removed:
            client = _clients.pop(key, None)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            _failed_connects.pop(key, None)
    return {"ok": True, "removed": removed, "missing": missing,
            "active": data["active"]}


# ---------------------------------------------------------------------------
# stdio JSON-RPC client (one long-lived child per active server)
# ---------------------------------------------------------------------------

class _StdioMcpClient:
    """Minimal synchronous MCP stdio client: line-delimited JSON-RPC."""

    def __init__(self, key: str, command: str, args: List[str],
                 env: Optional[Dict[str, str]] = None, cwd: str = ""):
        self.key = key
        self.command = command
        self.args = list(args or [])
        self.cwd = cwd or None
        self.env = os.environ.copy()
        if env:
            self.env.update({str(k): str(v) for k, v in env.items()})
        self.proc: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self.stderr_tail: str = ""
        self._tools_dirty: bool = False
        self.connected_at: float = 0.0
        self.last_tool_refresh_at: float = 0.0
        self.zero_tools_since: float = 0.0
        self._id = 0
        self._id_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending: Dict[int, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _next_id(self) -> int:
        with self._id_lock:
            self._id += 1
            return self._id

    def _resolve_argv(self) -> List[str]:
        """Build the spawn argv, resolving Windows command shims.

        On Windows a bare ``npx`` / ``npm`` / ``uvx`` / ``yarn`` / ``pnpm`` is a
        ``.cmd`` (or ``.bat``) batch shim, NOT an ``.exe``. ``CreateProcess``
        only auto-appends ``.exe``, so spawning the bare name fails with
        ``[WinError 2] The system cannot find the file specified`` -- exactly
        what broke the (very common) npx-launched MCP servers. Resolve the
        command through PATHEXT (``shutil.which`` finds ``npx.cmd``) and route a
        ``.cmd``/``.bat`` through the command processor, the only way a batch
        shim can actually be executed. POSIX behaviour is unchanged.
        """
        exe = os.path.expandvars(self.command)
        rest = [os.path.expandvars(a) for a in self.args]
        if os.name != "nt":
            return [exe, *rest]
        resolved = shutil.which(exe) or exe
        if resolved.lower().endswith((".cmd", ".bat")):
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            return [comspec, "/c", resolved, *rest]
        return [resolved, *rest]

    def _spawn(self) -> None:
        argv = self._resolve_argv()
        kwargs: Dict[str, Any] = dict(
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, cwd=self.cwd, env=self.env,
        )
        if os.name == "nt":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        self.proc = subprocess.Popen(argv, **kwargs)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # Drain stderr into a bounded tail so a connect failure can report the
        # REAL reason (e.g. "Cannot connect to the Docker daemon", an image
        # pull, a missing binary) instead of an opaque timeout — stderr used to
        # be discarded to DEVNULL, which made every failure a black box.
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = (line or "").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue  # server banner / non-JSON noise
            mid = msg.get("id")
            if mid is None:
                if msg.get("method") == "notifications/tools/list_changed":
                    self._tools_dirty = True  # server's tool set changed — re-list
                continue  # other notifications — ignore
            with self._pending_lock:
                q = self._pending.pop(mid, None)
            if q is not None:
                q.put(msg)
        # stdout closed → the child EXITED. Unblock every pending request now so
        # a crash / unknown command / "image not found" / server-that-dies-on-
        # startup fails FAST with a clear reason, instead of hanging until the
        # connect timeout (which made every startup failure look like a timeout).
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for q in pending:
            try:
                q.put_nowait({"error": {"message": "server process exited before responding "
                                                   "(see child stderr)"}})
            except Exception:
                pass

    def _drain_stderr(self) -> None:
        """Accumulate the child's stderr into a bounded tail (best-effort)."""
        try:
            if not self.proc or not self.proc.stderr:
                return
            for line in self.proc.stderr:
                if line:
                    self.stderr_tail = (self.stderr_tail + line)[-4000:]
        except Exception:
            pass

    def _send(self, obj: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("client not started")
        with self._send_lock:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()

    def _request(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        mid = self._next_id()
        q: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[mid] = q
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(mid, None)
            raise TimeoutError(f"{method} timed out after {timeout}s")
        if "error" in msg:
            raise RuntimeError(str(msg["error"]))
        return msg.get("result", {}) or {}

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _apply_tools_result(self, result: Dict[str, Any]) -> int:
        self.tools = result.get("tools", []) or []
        now = time.monotonic()
        self.last_tool_refresh_at = now
        if self.tools:
            self.zero_tools_since = 0.0
        elif not self.zero_tools_since:
            self.zero_tools_since = now
        self._tools_dirty = False
        return len(self.tools)

    def connect(self) -> None:
        """Spawn + initialize handshake + tools/list. Raises on failure."""
        timeout = _connect_timeout()
        self._spawn()
        self._request("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Tlamatini", "version": "1.x"},
        }, timeout=timeout)
        self._notify("notifications/initialized", {})
        result = self._request("tools/list", {}, timeout=timeout)
        self.connected_at = time.monotonic()
        self._apply_tools_result(result)
        logger.info("[ExternalMCP] '%s' connected — %d tool(s)", self.key, len(self.tools))
        if not self.tools:
            logger.warning(
                "[ExternalMCP] '%s' connected but exposes 0 tools — the backend it bridges to "
                "is likely not ready yet (e.g. Roblox Studio not open / its MCP plugin not "
                "connected; or a server whose tools appear only once its session is up). "
                "Tlamatini re-lists every turn, so they appear once the server offers them.",
                self.key)

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = self._request("tools/call",
                               {"name": name, "arguments": arguments or {}},
                               timeout=_CALL_TIMEOUT)
        parts = []
        for block in result.get("content", []) or []:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
        text = "\n".join(p for p in parts if p)
        if result.get("isError"):
            return "Error: " + (text or "tool reported an error")
        return text or json.dumps(result, ensure_ascii=False)

    def refresh_tools(self) -> int:
        """Re-run tools/list. A server may expose tools only AFTER its backend
        connects (e.g. Roblox Studio opening) or after a tools/list_changed
        event — re-listing lets those tools appear without a reconnect."""
        if not self.alive():
            return len(self.tools)
        try:
            result = self._request("tools/list", {}, timeout=2.0)
            self._apply_tools_result(result)
        except Exception as exc:
            logger.info("[ExternalMCP] '%s' tools refresh failed: %s", self.key, exc)
        return len(self.tools)

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        if not proc:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Non-stdio transports (Streamable HTTP / legacy SSE / WebSocket)
#
# These reach a server that is ALREADY running over a network carrier. Each one
# implements the SAME public surface as ``_StdioMcpClient`` (``alive`` /
# ``tools`` / ``call_tool`` / ``refresh_tools`` / ``close`` / ``stderr_tail`` /
# ``connected_at`` / ``last_tool_refresh_at`` / ``zero_tools_since`` /
# ``_tools_dirty`` and ``proc=None``) so the supervisor, status, watchdog, and
# tool-binding code treat every transport identically. The shared base owns the
# MCP handshake; subclasses own only the carrier (open / send-request /
# send-notification / close). httpx and websockets are imported lazily so a
# build that somehow lacks them degrades to a clean catalogued-not-connected
# diagnosis instead of breaking module import.
# ---------------------------------------------------------------------------

def _server_url(spec: Dict[str, Any]) -> str:
    """Best-effort URL for a network MCP spec (import already normalizes to url)."""
    for field in (
        "url", "endpoint", "streamableHttpUrl", "streamable_http_url",
        "sseUrl", "sse_url", "wsUrl", "ws_url", "websocketUrl", "webSocketUrl",
    ):
        value = spec.get(field)
        if value:
            return os.path.expandvars(str(value).strip())
    return ""


def _spec_headers(spec: Dict[str, Any]) -> Dict[str, str]:
    """Custom HTTP/WebSocket headers (e.g. ``Authorization``) from the spec."""
    raw = spec.get("headers")
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if value is not None:
            out[str(key)] = os.path.expandvars(str(value))
    return out


class _NetworkMcpClientBase:
    """Shared MCP-protocol logic for the non-stdio (network) transports."""

    proc = None  # no child process — the command watchdog skips these

    def __init__(self, key: str, url: str, headers: Optional[Dict[str, str]] = None):
        self.key = key
        self.url = os.path.expandvars(str(url or "").strip())
        self.headers = dict(headers or {})
        self.tools: List[Dict[str, Any]] = []
        self.stderr_tail: str = ""
        self._tools_dirty: bool = False
        self.connected_at: float = 0.0
        self.last_tool_refresh_at: float = 0.0
        self.zero_tools_since: float = 0.0
        self._protocol_version: str = _MCP_PROTOCOL_VERSION
        self._closed: bool = False
        self._id = 0
        self._id_lock = threading.Lock()

    transport_label = "network"

    def _next_id(self) -> int:
        with self._id_lock:
            self._id += 1
            return self._id

    def _apply_tools_result(self, result: Dict[str, Any]) -> int:
        self.tools = result.get("tools", []) or []
        now = time.monotonic()
        self.last_tool_refresh_at = now
        if self.tools:
            self.zero_tools_since = 0.0
        elif not self.zero_tools_since:
            self.zero_tools_since = now
        self._tools_dirty = False
        return len(self.tools)

    # --- carrier hooks (subclasses implement) ---
    def _open(self) -> None:
        raise NotImplementedError

    def _rpc(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        raise NotImplementedError

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        raise NotImplementedError

    def alive(self) -> bool:
        return not self._closed

    def close(self) -> None:
        self._closed = True

    # --- shared MCP handshake / calls (identical semantics to _StdioMcpClient) ---
    def connect(self) -> None:
        timeout = _connect_timeout()
        self._open()
        init = self._rpc("initialize", {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Tlamatini", "version": "1.x"},
        }, timeout=timeout)
        if isinstance(init, dict) and init.get("protocolVersion"):
            self._protocol_version = str(init["protocolVersion"])
        self._notify("notifications/initialized", {})
        result = self._rpc("tools/list", {}, timeout=timeout)
        self.connected_at = time.monotonic()
        self._apply_tools_result(result)
        logger.info("[ExternalMCP] '%s' connected (%s) — %d tool(s)",
                    self.key, self.transport_label, len(self.tools))
        if not self.tools:
            logger.warning(
                "[ExternalMCP] '%s' connected (%s) but exposes 0 tools — the server's "
                "backend may not be ready, or it needs an enable/authorize step. "
                "Tlamatini re-lists every turn, so tools appear once offered.",
                self.key, self.transport_label)

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        result = self._rpc("tools/call",
                            {"name": name, "arguments": arguments or {}},
                            timeout=_CALL_TIMEOUT)
        parts: List[str] = []
        for block in result.get("content", []) or []:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
        text = "\n".join(p for p in parts if p)
        if result.get("isError"):
            return "Error: " + (text or "tool reported an error")
        return text or json.dumps(result, ensure_ascii=False)

    def refresh_tools(self) -> int:
        if not self.alive():
            return len(self.tools)
        try:
            result = self._rpc("tools/list", {}, timeout=2.0)
            self._apply_tools_result(result)
        except Exception as exc:
            logger.info("[ExternalMCP] '%s' tools refresh failed: %s", self.key, exc)
        return len(self.tools)


class _StreamableHttpMcpClient(_NetworkMcpClientBase):
    """MCP Streamable HTTP transport (single endpoint; JSON or SSE responses)."""

    transport_label = "streamable-http"

    def __init__(self, key: str, url: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(key, url, headers)
        self._client = None
        self._session_id = ""

    def alive(self) -> bool:
        return (not self._closed) and self._client is not None

    def _open(self) -> None:
        import httpx
        self._client = httpx.Client(
            timeout=httpx.Timeout(_connect_timeout(), read=_CALL_TIMEOUT, write=30.0, pool=30.0),
            follow_redirects=True,
        )

    def _request_headers(self, is_initialize: bool) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(self.headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if not is_initialize:
            headers["MCP-Protocol-Version"] = self._protocol_version
        return headers

    def _post(self, payload: Dict[str, Any], timeout: float, is_initialize: bool):
        headers = self._request_headers(is_initialize)
        with self._client.stream("POST", self.url, json=payload, headers=headers, timeout=timeout) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                self._session_id = sid
            ctype = (resp.headers.get("content-type") or "").lower()
            status = resp.status_code
            if status >= 400:
                body = resp.read().decode("utf-8", "replace")
                raise RuntimeError(f"HTTP {status} from MCP endpoint: {body[:400]}")
            if "text/event-stream" in ctype:
                messages: List[Any] = []
                for line in resp.iter_lines():
                    text = line if isinstance(line, str) else (line or b"").decode("utf-8", "replace")
                    if not text.startswith("data:"):
                        continue
                    data = text[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        messages.append(json.loads(data))
                    except Exception:
                        continue
                return status, messages
            raw = resp.read().decode("utf-8", "replace").strip()
            if not raw:
                return status, []
            try:
                parsed = json.loads(raw)
            except Exception:
                return status, []
            return status, (parsed if isinstance(parsed, list) else [parsed])

    def _rpc(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        rid = self._next_id()
        status, messages = self._post(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
            timeout, is_initialize=(method == "initialize"))
        for msg in messages:
            if isinstance(msg, dict) and str(msg.get("id")) == str(rid):
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result", {}) or {}
        raise RuntimeError(f"{method}: no matching JSON-RPC response (HTTP {status})")

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params},
                       timeout=15.0, is_initialize=False)
        except Exception:
            pass  # notifications are fire-and-forget

    def close(self) -> None:
        self._closed = True
        client = self._client
        self._client = None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


class _WebSocketMcpClient(_NetworkMcpClientBase):
    """MCP over a WebSocket carrier (line- or frame-delimited JSON-RPC)."""

    transport_label = "websocket"

    def __init__(self, key: str, url: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(key, url, headers)
        self._ws = None
        self._pending: Dict[str, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None

    def alive(self) -> bool:
        return (not self._closed) and self._ws is not None

    def _open(self) -> None:
        from websockets.sync.client import connect as ws_connect
        kwargs: Dict[str, Any] = {"open_timeout": _connect_timeout(), "max_size": None}
        if self.headers:
            kwargs["additional_headers"] = self.headers
        self._ws = ws_connect(self.url, **kwargs)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        ws = self._ws
        try:
            while ws is not None:
                raw = ws.recv()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                for line in str(raw).splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    mid = msg.get("id")
                    if mid is None:
                        if msg.get("method") == "notifications/tools/list_changed":
                            self._tools_dirty = True
                        continue
                    with self._pending_lock:
                        pending = self._pending.pop(str(mid), None)
                    if pending is not None:
                        pending.put(msg)
        except Exception:
            pass
        finally:
            with self._pending_lock:
                waiting = list(self._pending.values())
                self._pending.clear()
            for pending in waiting:
                try:
                    pending.put_nowait({"error": {"message": "websocket closed before responding"}})
                except Exception:
                    pass

    def _send_raw(self, obj: Dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            raise RuntimeError("websocket not connected")
        ws.send(json.dumps(obj))

    def _rpc(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        rid = self._next_id()
        response: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[str(rid)] = response
        self._send_raw({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = response.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(str(rid), None)
            raise TimeoutError(f"{method} timed out after {timeout}s")
        if "error" in msg:
            raise RuntimeError(str(msg["error"]))
        return msg.get("result", {}) or {}

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        try:
            self._send_raw({"jsonrpc": "2.0", "method": method, "params": params})
        except Exception:
            pass

    def close(self) -> None:
        self._closed = True
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


class _SseMcpClient(_NetworkMcpClientBase):
    """Legacy MCP HTTP+SSE transport: GET stream announces a POST endpoint,
    responses arrive back over the same SSE stream (matched by JSON-RPC id)."""

    transport_label = "sse"

    def __init__(self, key: str, url: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(key, url, headers)
        self._client = None
        self._stream_cm = None
        self._stream_resp = None
        self._endpoint = ""
        self._endpoint_event = threading.Event()
        self._pending: Dict[str, queue.Queue] = {}
        self._pending_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None

    def alive(self) -> bool:
        return (not self._closed) and self._client is not None

    def _open(self) -> None:
        import httpx
        self._client = httpx.Client(
            timeout=httpx.Timeout(_connect_timeout(), read=None, write=30.0, pool=30.0),
            follow_redirects=True,
        )
        headers = {"Accept": "text/event-stream"}
        headers.update(self.headers)
        self._stream_cm = self._client.stream("GET", self.url, headers=headers)
        self._stream_resp = self._stream_cm.__enter__()
        if self._stream_resp.status_code >= 400:
            raise RuntimeError(f"HTTP {self._stream_resp.status_code} opening SSE stream")
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        if not self._endpoint_event.wait(timeout=_connect_timeout()):
            raise RuntimeError("SSE server did not announce a POST endpoint")

    def _resolve_endpoint(self, raw: str) -> str:
        raw = (raw or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
        from urllib.parse import urljoin
        return urljoin(self.url, raw)

    def _read_loop(self) -> None:
        event = ""
        data_lines: List[str] = []
        try:
            for line in self._stream_resp.iter_lines():
                text = line if isinstance(line, str) else (line or b"").decode("utf-8", "replace")
                if text == "":
                    payload = "\n".join(data_lines)
                    kind = event or "message"
                    event, data_lines = "", []
                    if kind == "endpoint":
                        self._endpoint = self._resolve_endpoint(payload)
                        self._endpoint_event.set()
                        continue
                    try:
                        msg = json.loads(payload)
                    except Exception:
                        continue
                    mid = msg.get("id")
                    if mid is None:
                        if msg.get("method") == "notifications/tools/list_changed":
                            self._tools_dirty = True
                        continue
                    with self._pending_lock:
                        pending = self._pending.pop(str(mid), None)
                    if pending is not None:
                        pending.put(msg)
                    continue
                if text.startswith(":"):
                    continue  # SSE comment / heartbeat
                if text.startswith("event:"):
                    event = text[6:].strip()
                elif text.startswith("data:"):
                    data_lines.append(text[5:].lstrip())
        except Exception:
            pass
        finally:
            with self._pending_lock:
                waiting = list(self._pending.values())
                self._pending.clear()
            for pending in waiting:
                try:
                    pending.put_nowait({"error": {"message": "SSE stream closed before responding"}})
                except Exception:
                    pass

    def _post(self, payload: Dict[str, Any], timeout: float) -> None:
        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)
        resp = self._client.post(self._endpoint, json=payload, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} posting to SSE endpoint: {resp.text[:300]}")

    def _rpc(self, method: str, params: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        rid = self._next_id()
        response: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[str(rid)] = response
        self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, timeout)
        try:
            msg = response.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(str(rid), None)
            raise TimeoutError(f"{method} timed out after {timeout}s")
        if "error" in msg:
            raise RuntimeError(str(msg["error"]))
        return msg.get("result", {}) or {}

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params}, timeout=15.0)
        except Exception:
            pass

    def close(self) -> None:
        self._closed = True
        stream_cm = self._stream_cm
        client = self._client
        self._stream_cm = None
        self._stream_resp = None
        self._client = None
        if stream_cm is not None:
            try:
                stream_cm.__exit__(None, None, None)
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _make_client(key: str, spec: Dict[str, Any]):
    """Construct the right transport client for a spec, or raise with the reason."""
    transport = _server_transport(spec)
    if transport == "stdio":
        if not spec.get("command"):
            raise RuntimeError("stdio MCP server has no command")
        return _StdioMcpClient(
            key=key,
            command=spec.get("command", ""),
            args=spec.get("args", []) or [],
            env=spec.get("env", {}) or {},
            cwd=spec.get("cwd", "") or "",
        )
    if transport in ("streamable-http",):
        url = _server_url(spec)
        if not url:
            raise RuntimeError("streamable-http MCP server has no url")
        return _StreamableHttpMcpClient(key, url, _spec_headers(spec))
    if transport == "sse":
        url = _server_url(spec)
        if not url:
            raise RuntimeError("sse MCP server has no url")
        return _SseMcpClient(key, url, _spec_headers(spec))
    if transport == "websocket":
        url = _server_url(spec)
        if not url:
            raise RuntimeError("websocket MCP server has no url")
        return _WebSocketMcpClient(key, url, _spec_headers(spec))
    raise RuntimeError(
        f"Unsupported External MCP transport '{transport}'. Tlamatini connects "
        "stdio, streamable-http, sse, and websocket servers; this carrier "
        f"({transport}) needs a stdio bridge or a future transport adapter."
    )


def _connect(key: str, spec: Dict[str, Any]) -> Optional[Any]:
    transport = _server_transport(spec)
    try:
        client = _make_client(key, spec)
    except Exception as exc:
        msg = str(exc)
        logger.info("[ExternalMCP] '%s' skipped: %s", key, msg)
        _last_errors[key] = msg
        return None
    try:
        with _clients_lock:
            _launching_clients[key] = client
        client.connect()
        _last_errors.pop(key, None)
        return client
    except Exception as exc:
        tail = (getattr(client, "stderr_tail", "") or "").strip()
        if transport == "stdio":
            hint = (
                f"  | child stderr (tail): ...{tail[-600:]}" if tail else
                "  | (the child produced no stderr — the command likely blocked or "
                "the server never started; is the binary/daemon available?)"
            )
        else:
            hint = (
                f"  | {transport} carrier at {getattr(client, 'url', '') or _server_url(spec)} "
                "did not complete the MCP handshake — is the server running and the "
                "URL/headers correct?"
            )
        detail = str(exc) + hint
        logger.warning("[ExternalMCP] '%s' failed to connect: %s", key, detail)
        _last_errors[key] = detail
        try:
            client.close()
        except Exception:
            pass
        return None
    finally:
        with _clients_lock:
            if _launching_clients.get(key) is client:
                _launching_clients.pop(key, None)


def _warm_connect_one(key: str, spec: Dict[str, Any]) -> None:
    """Connect ONE server (runs on a background thread). Stores the live client
    on success, or arms the cooldown on failure (``_connect`` logs the reason)."""
    try:
        client = _connect(key, spec)
        with _clients_lock:
            if client is not None:
                _clients[key] = client
                _failed_connects.pop(key, None)
            else:
                _failed_connects[key] = time.monotonic() + _FAIL_COOLDOWN
    finally:
        with _clients_lock:
            _connecting.discard(key)


def _warm_connect_async(active: List[str], servers: Dict[str, Any]) -> None:
    """Kick BACKGROUND connects for active servers that aren't live yet.

    Never connects on the calling thread — so it is safe to call from the
    chat-build path (``get_external_mcp_tools``) AND from ``set_active`` without
    ever stalling. The slow / Docker / cold-start ``initialize`` happens
    off-thread; the tools appear once the handshake completes. This is the fix
    for the 12 s synchronous connect that stalled the chat and dropped redis.
    """
    now = time.monotonic()
    with _clients_lock:
        for key in active:
            spec = servers.get(key)
            if not spec:
                continue
            client = _clients.get(key)
            if client is not None and client.alive():
                continue
            if client is not None:
                _clients.pop(key, None)  # dead — drop and reconnect
            if key in _connecting:
                continue  # a connect is already in flight
            if _failed_connects.get(key, 0.0) > now:
                continue  # in cooldown after a recent failure
            _connecting.add(key)
            threading.Thread(
                target=_warm_connect_one, args=(key, spec), daemon=True
            ).start()
            logger.info("[ExternalMCP] warm-connect started for '%s'", key)


def _refresh_and_supervise_active(
    active: List[str],
    servers: Dict[str, Any],
    *,
    force_refresh: bool = False,
) -> None:
    """Refresh live active clients and restart zero-tool bridges that stay stuck.

    This is intentionally conservative. A server that exposes 0 tools for a few
    seconds is often just warming up; a server that stays at 0 tools past the
    grace window is usually waiting on a backend bridge, so a reconnect is worth
    trying while the UI/status tool tells the user what is still missing.
    """
    now = time.monotonic()
    to_close: List["_StdioMcpClient"] = []
    reconnect_keys: List[str] = []

    with _clients_lock:
        live = [
            (key, _clients.get(key), servers.get(key) or {})
            for key in active
        ]

    for key, client, spec in live:
        if client is None or not client.alive():
            continue
        should_refresh = (
            force_refresh
            or client._tools_dirty
            or not client.tools
            or (now - client.last_tool_refresh_at) > 15.0
        )
        if should_refresh:
            before = len(client.tools)
            after = client.refresh_tools()
            if after and not before:
                logger.info("[ExternalMCP] '%s' now exposes %d tool(s) after supervisor refresh",
                            key, after)

        if client.tools:
            continue
        zero_since = client.zero_tools_since or now
        stuck_for = now - zero_since
        last_reconnect = _last_reconnects.get(key, 0.0)
        if (
            stuck_for >= _ZERO_TOOL_RECONNECT_GRACE
            and (now - last_reconnect) >= _ZERO_TOOL_RECONNECT_COOLDOWN
            and key not in _connecting
        ):
            logger.warning(
                "[ExternalMCP] '%s' stuck with 0 tools for %.0fs; reconnecting. %s",
                key, stuck_for, _zero_tool_diagnostic(key, spec, client),
            )
            with _clients_lock:
                if _clients.get(key) is client:
                    _clients.pop(key, None)
                    _failed_connects.pop(key, None)
                    _last_reconnects[key] = now
                    reconnect_keys.append(key)
                    to_close.append(client)

    for client in to_close:
        try:
            client.close()
        except Exception:
            pass
    if reconnect_keys:
        _warm_connect_async(reconnect_keys, servers)


def supervisor_snapshot(server_key: str = "", refresh: bool = True) -> Dict[str, Any]:
    """Return a structured External-MCP health snapshot for tools/UI/logs."""
    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if active:
        _warm_connect_async(active, servers)
        if refresh:
            _refresh_and_supervise_active(active, servers, force_refresh=True)

    keys = [server_key] if server_key else sorted(servers.keys())
    rows = []
    for key in keys:
        if key in servers:
            rows.append(_server_status_payload(key, servers[key] or {}, active))

    return {
        "ok": True,
        "active": active,
        "max_active": MAX_ACTIVE,
        "servers": rows,
        "ready_count": sum(1 for row in rows if row.get("status") == "ready"),
        "zero_tool_count": sum(1 for row in rows if row.get("status") == "no_tools"),
        "connecting_count": sum(1 for row in rows if row.get("status") == "connecting"),
        "error_count": sum(1 for row in rows if row.get("status") == "error"),
    }


def list_server_tools(
    server_key: str = "",
    search: str = "",
    include_schema: bool = True,
) -> Dict[str, Any]:
    """Describe tools exposed by active External MCP servers.

    This is the generic escape hatch for large MCP servers. Tlamatini may avoid
    binding hundreds of direct ``ext__...`` function schemas at once, but the
    model can still inspect every active server's exact tool names and schemas
    and then call any of them through ``external_mcp_call``.
    """
    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if active:
        _warm_connect_async(active, servers)
        _refresh_and_supervise_active(active, servers, force_refresh=True)

    wanted = str(server_key or "").strip()
    needle = str(search or "").strip().lower()
    rows: List[Dict[str, Any]] = []
    with _clients_lock:
        live = {
            key: client
            for key, client in _clients.items()
            if key in active and client.alive()
        }

    keys = [wanted] if wanted else sorted(active)
    for key in keys:
        client = live.get(key)
        if client is None:
            rows.append({
                "server_key": key,
                "ready": False,
                "tools": [],
                "diagnostic": _server_status_payload(
                    key, servers.get(key, {}) or {}, active
                ).get("diagnostic", "Server is not connected."),
            })
            continue
        tools: List[Dict[str, Any]] = []
        for tool in client.tools:
            name = str(tool.get("name", ""))
            desc = str(tool.get("description", ""))
            haystack = f"{key} {name} {desc}".lower()
            if needle and needle not in haystack:
                continue
            item = {
                "name": name,
                "wrapped_name": _safe_tool_name(key, name),
                "description": desc,
            }
            if include_schema:
                item["inputSchema"] = tool.get("inputSchema") or {}
            tools.append(item)
        rows.append({
            "server_key": key,
            "ready": True,
            "tool_count": len(client.tools),
            "returned_tool_count": len(tools),
            "tools": tools,
        })

    return {
        "ok": True,
        "active": active,
        "servers": rows,
    }


def call_server_tool(server_key: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call any tool exposed by an active External MCP server."""
    key = str(server_key or "").strip()
    name = str(tool_name or "").strip()
    if not key:
        return {"ok": False, "error": "server_key is required"}
    if not name:
        return {"ok": False, "error": "tool_name is required"}

    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if key not in servers:
        return {"ok": False, "error": f"unknown MCP server: {key}"}
    if key not in active:
        return {"ok": False, "error": f"MCP server is not active: {key}"}

    _warm_connect_async([key], servers)
    with _clients_lock:
        client = _clients.get(key)
    if client is None or not client.alive():
        return {
            "ok": False,
            "error": f"external MCP '{key}' is not connected",
            "status": _server_status_payload(key, servers.get(key, {}) or {}, active),
        }

    if client._tools_dirty or not client.tools:
        client.refresh_tools()
    known = {str(tool.get("name", "")) for tool in client.tools}
    if name not in known:
        return {
            "ok": False,
            "error": f"unknown tool '{name}' for External MCP server '{key}'",
            "available_tools": sorted(known),
        }
    try:
        result = client.call_tool(name, arguments or {})
        return {
            "ok": True,
            "server_key": key,
            "tool_name": name,
            "result": result,
        }
    except Exception as exc:
        return {
            "ok": False,
            "server_key": key,
            "tool_name": name,
            "error": str(exc),
        }


def _which_executable(command: str) -> Dict[str, Any]:
    expanded = os.path.expandvars(str(command or "").strip())
    if not expanded:
        return {"command": "", "found": False, "resolved": ""}
    if os.path.isabs(expanded) or os.sep in expanded or (os.altsep and os.altsep in expanded):
        return {
            "command": expanded,
            "found": os.path.exists(expanded),
            "resolved": expanded if os.path.exists(expanded) else "",
        }
    resolved = shutil.which(expanded) or ""
    return {"command": expanded, "found": bool(resolved), "resolved": resolved}


def _infer_runtime(command: str, args: List[str]) -> str:
    exe = os.path.basename(str(command or "").lower())
    joined = " ".join(str(arg).lower() for arg in args or [])
    if exe in {"docker", "docker.exe"} or "docker" in joined:
        return "docker"
    if exe in {"npx", "npx.cmd", "npm", "npm.cmd", "node", "node.exe"}:
        return "node/npm"
    if exe in {"uvx", "uvx.exe", "uv", "uv.exe"}:
        return "uv/uvx"
    if exe in {"python", "python.exe", "python3", "py", "py.exe"}:
        return "python"
    if exe in {"bun", "bun.exe"}:
        return "bun"
    if exe in {"deno", "deno.exe"}:
        return "deno"
    if exe in {"cargo", "cargo.exe"}:
        return "rust/cargo"
    if exe in {"dotnet", "dotnet.exe"}:
        return ".NET"
    if exe in {"java", "java.exe"}:
        return "java"
    if exe in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return "shell wrapper"
    return exe or "unknown"


def _looks_like_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    markers = (
        "your_", "changeme", "change_me", "replace_me", "placeholder",
        "example_token", "api_key_here", "token_here", "<", ">",
        "${", "%", "xxx", "todo",
    )
    return any(marker in lowered for marker in markers)


def _missing_secret_hints(spec: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    env = spec.get("env") if isinstance(spec.get("env"), dict) else {}
    for key, value in env.items():
        key_text = str(key)
        key_lower = key_text.lower()
        secretish = any(part in key_lower for part in ("key", "token", "secret", "password", "auth", "bearer"))
        if secretish and _looks_like_placeholder(value):
            hints.append(key_text)
    for idx, arg in enumerate(spec.get("args") or []):
        text = str(arg)
        lower = text.lower()
        if any(part in lower for part in ("api_key", "apikey", "token", "secret", "password")) and _looks_like_placeholder(text):
            hints.append(f"args[{idx}]")
    return hints


def _known_source_urls(spec: Dict[str, Any]) -> List[str]:
    urls: List[str] = []
    for key in (
        "source", "homepage", "homePage", "repository", "repo", "docs",
        "documentation", "readme", "url",
    ):
        value = spec.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            urls.append(value.strip())
    return list(dict.fromkeys(urls))


def _diagnose_one_server(key: str, spec: Dict[str, Any], active: List[str]) -> Dict[str, Any]:
    spec = spec or {}
    transport = _server_transport(spec)
    args = _normalize_import_args(spec.get("args"))
    command = str(spec.get("command") or "").strip()
    command_probe = _which_executable(command) if command else {"command": "", "found": False, "resolved": ""}
    runtime = _infer_runtime(command, args)
    missing_secret_fields = _missing_secret_hints(spec)
    source_urls = _known_source_urls(spec)
    status = _server_status_payload(key, spec, active)

    url = _server_url(spec)
    if transport == "stdio":
        supported = bool(command)
    elif transport in _SUPPORTED_TRANSPORTS:
        supported = bool(url)
    else:
        supported = False

    blockers: List[str] = []
    if transport not in _SUPPORTED_TRANSPORTS:
        blockers.append(f"transport not connectable here: {transport} (needs a stdio bridge)")
    elif transport == "stdio":
        if not command:
            blockers.append("stdio server has no command")
        elif not command_probe["found"]:
            blockers.append(f"command not found on PATH: {command}")
    elif not url:
        blockers.append(f"{transport} server has no url")
    if missing_secret_fields:
        blockers.append("missing or placeholder secret fields: " + ", ".join(missing_secret_fields))

    if transport not in _SUPPORTED_TRANSPORTS:
        next_step = (
            f"This server uses {transport}, which Tlamatini cannot connect directly yet. "
            "Wrap it with a stdio MCP bridge, or expose it over streamable-http/sse/websocket."
        )
    elif transport == "stdio" and not command:
        next_step = "Add the server command from the MCP documentation, then import the JSON again."
    elif transport == "stdio" and not command_probe["found"]:
        next_step = f"Install or expose `{command}` on PATH, then ask Tlamatini to reconnect this MCP."
    elif transport != "stdio" and not url:
        next_step = f"Add the {transport} server url to the JSON, then re-import via external_mcp_import."
    elif missing_secret_fields:
        next_step = "Fill the required secret/environment fields, then reconnect the MCP."
    elif key not in active:
        next_step = f"Call external_mcp_set_active with '{key}' to activate and warm-connect it."
    else:
        next_step = "Run external_mcp_status, then external_mcp_list_tools, then perform one safe smoke-test tool call."

    investigation_steps = [
        "Identify the authoritative docs: use source/docs/repository URLs if present; otherwise search the MCP name plus its command/package.",
        "Verify prerequisites for the inferred runtime before activation.",
        "Check secrets/env placeholders and ask the user for missing keys without exposing stored secret values.",
        "Activate and inspect initialize + tools/list through external_mcp_status.",
        "Use external_mcp_list_tools to learn exact tool names and schemas.",
        "Use external_mcp_call for a small safe read-only or reversible write smoke test.",
        "Teach the user one READY-gated step at a time when Step-by-Step is enabled.",
    ]

    return {
        "server_key": key,
        "display": key.replace("_", " ").strip() or key,
        "transport": transport,
        "url": url,
        "supported_by_current_connector": supported,
        "runtime": runtime,
        "command_probe": command_probe,
        "args": args,
        "active": key in active,
        "status": status,
        "source_urls": source_urls,
        "missing_secret_fields": missing_secret_fields,
        "blockers": blockers,
        "next_step": next_step,
        "investigation_steps": investigation_steps,
    }


def diagnose_server(server_key: str = "") -> Dict[str, Any]:
    """Return setup/usage diagnostics for one or all catalogued External MCPs."""
    wanted = str(server_key or "").strip()
    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if wanted and wanted not in servers:
        return {
            "ok": False,
            "error": f"unknown MCP server: {wanted}",
            "next_step": (
                f"'{wanted}' is not in the catalog yet. If the user gave its JSON config, call "
                "external_mcp_import with that JSON, then external_mcp_set_active to connect it. "
                "Otherwise ask the user for the server's mcpServers JSON (a command/args or a url)."
            ),
            "catalog_servers": sorted(servers.keys()),
        }

    keys = [wanted] if wanted else sorted(servers.keys())
    diagnostics = [
        _diagnose_one_server(key, servers.get(key, {}) or {}, active)
        for key in keys
    ]
    return {
        "ok": True,
        "server_key": wanted,
        "count": len(diagnostics),
        "diagnostics": diagnostics,
    }


def reconnect_server(server_key: str) -> Dict[str, Any]:
    """Force a reconnect for one active External MCP server."""
    key = str(server_key or "").strip()
    data = load_catalog()
    servers = data.get("mcpServers", {})
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if not key:
        return {"ok": False, "error": "server_key is required"}
    if key not in servers:
        return {"ok": False, "error": f"unknown MCP server: {key}"}
    if key not in active:
        return {"ok": False, "error": f"MCP server is not active: {key}"}

    with _clients_lock:
        if key in _connecting:
            return {
                "ok": True,
                "server_key": key,
                "message": "Reconnect already in progress.",
                "snapshot": supervisor_snapshot(key, refresh=False),
            }
        client = _clients.pop(key, None)
        _failed_connects.pop(key, None)
        _last_errors.pop(key, None)
        _last_reconnects[key] = time.monotonic()

    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    _warm_connect_async([key], servers)
    return {
        "ok": True,
        "server_key": key,
        "message": "Reconnect started.",
        "snapshot": supervisor_snapshot(key, refresh=False),
    }


def wait_for_server(server_key: str, timeout_seconds: float = 90.0) -> Dict[str, Any]:
    """Block (up to a timeout) until an ACTIVE server is connected and exposing
    tools, driving the background warm-connect + relist as it goes.

    This is the cure for a slow first-run server (e.g. a Docker image being
    PULLED on first use): instead of the model polling external_mcp_status in a
    tight loop and giving up (the repetition breaker), it makes ONE call that
    waits server-side until the tools come online — or returns a clear, still
    actionable status on timeout. Fail-safe: never raises into the tool layer.
    """
    key = str(server_key or "").strip()
    if not key:
        return {"ok": False, "error": "server_key is required"}
    data = load_catalog()
    servers = data.get("mcpServers", {})
    if key not in servers:
        return {"ok": False, "error": f"unknown MCP server: {key}"}
    active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
    if key not in active:
        return {"ok": False, "error": f"MCP server is not active: {key} — call external_mcp_set_active first"}

    budget = max(5.0, min(float(timeout_seconds or 90.0), 300.0))
    deadline = time.monotonic() + budget
    last_row: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            _warm_connect_async(active, servers)
            _refresh_and_supervise_active(active, servers, force_refresh=True)
            last_row = _server_status_payload(key, servers.get(key, {}) or {}, active)
        except Exception as exc:  # never raise into the tool layer
            return {"ok": False, "server_key": key, "error": str(exc)}
        status = last_row.get("status")
        if status == "ready" and (last_row.get("tool_count") or 0) > 0:
            return {
                "ok": True, "server_key": key, "status": "ready",
                "tool_count": last_row.get("tool_count"),
                "next_step": "Tools are live now — call the bound ext__%s__<tool> tools "
                             "(or external_mcp_list_tools + external_mcp_call)." % key,
                "snapshot": last_row,
            }
        if status == "error":
            return {
                "ok": False, "server_key": key, "status": "error",
                "error": last_row.get("error", ""),
                "diagnostic": last_row.get("diagnostic", ""),
                "snapshot": last_row,
            }
        time.sleep(1.5)
    return {
        "ok": False, "server_key": key, "timed_out": True,
        "status": (last_row or {}).get("status", "connecting"),
        "message": (
            f"'{key}' was not ready within {int(budget)}s. A FIRST-run Docker image pull "
            "(or a cold npx/uvx download) can take longer than this — call external_mcp_wait "
            "again with a larger timeout_seconds (e.g. 180), or external_mcp_status to keep "
            "watching. Do NOT abandon the task; the server is still coming online."
        ),
        "snapshot": last_row,
    }


# ---------------------------------------------------------------------------
# LangChain tool wrapping
# ---------------------------------------------------------------------------

def _safe_tool_name(server_key: str, tool_name: str) -> str:
    raw = f"ext__{server_key}__{tool_name}"
    cleaned = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in raw)
    return cleaned[:64]


def _json_type_to_py(jtype: Any) -> Any:
    mapping = {"string": str, "integer": int, "number": float,
               "boolean": bool, "array": list, "object": dict}
    if isinstance(jtype, list):
        types = [mapping[t] for t in jtype if t != "null" and t in mapping]
        return _union_type(types) if types else Any
    return mapping.get(jtype, Any)


def _union_type(types: List[Any]) -> Any:
    from typing import Union

    unique: List[Any] = []
    for typ in types:
        if typ is Any:
            return Any
        if typ not in unique:
            unique.append(typ)
    if not unique:
        return Any
    if len(unique) == 1:
        return unique[0]
    return Union[tuple(unique)]


def _schema_to_py_type(schema: Dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return Any
    variants: List[Any] = []
    for key in ("anyOf", "oneOf"):
        raw = schema.get(key)
        if isinstance(raw, list):
            variants.extend(
                _schema_to_py_type(item)
                for item in raw
                if isinstance(item, dict) and item.get("type") != "null"
            )
    if variants:
        return _union_type(variants)

    if "allOf" in schema and isinstance(schema["allOf"], list):
        non_null = [
            _schema_to_py_type(item)
            for item in schema["allOf"]
            if isinstance(item, dict) and item.get("type") != "null"
        ]
        return non_null[0] if non_null else Any

    if "const" in schema:
        return type(schema["const"])
    if "enum" in schema and isinstance(schema["enum"], list):
        return _union_type([type(item) for item in schema["enum"] if item is not None])
    return _json_type_to_py(schema.get("type"))


def _args_model_from_schema(model_name: str, schema: Optional[Dict[str, Any]]):
    from typing import Optional as Opt

    from pydantic import Field, create_model
    schema = schema or {}
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    fields: Dict[str, Any] = {}
    for pname, pdef in props.items():
        pdef = pdef or {}
        pytype = _schema_to_py_type(pdef)
        desc = pdef.get("description", "")
        if pname in required:
            fields[pname] = (pytype, Field(..., description=desc))
        else:
            fields[pname] = (Opt[pytype], Field(default=None, description=desc))
    return create_model(model_name, **fields)


def _build_tool(server_key: str, tool_def: Dict[str, Any]):
    from langchain_core.tools import StructuredTool
    tool_name = tool_def.get("name", "")
    if not tool_name:
        return None
    safe = _safe_tool_name(server_key, tool_name)
    description = (
        f"External MCP server '{server_key}', tool '{tool_name}'. "
        + (tool_def.get("description") or "")
    )[:1024]
    args_model = _args_model_from_schema(safe + "_Args", tool_def.get("inputSchema"))

    def _call(**kwargs):
        with _clients_lock:
            client = _clients.get(server_key)
        if client is None or not client.alive():
            return f"Error: external MCP '{server_key}' is not connected."
        try:
            return client.call_tool(tool_name, kwargs)
        except Exception as exc:
            return f"Error calling {server_key}.{tool_name}: {exc}"

    return StructuredTool.from_function(
        func=_call, name=safe, description=description, args_schema=args_model,
    )


def _build_supervisor_tools() -> List[Any]:
    from typing import Optional as Opt
    from typing import Union

    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model

    StatusArgs = create_model(
        "ExternalMcpStatusArgs",
        server_key=(Opt[str], Field(default=None, description="Optional MCP server key to inspect.")),
        refresh=(bool, Field(default=True, description="Refresh tools/list before reporting.")),
    )
    ReconnectArgs = create_model(
        "ExternalMcpReconnectArgs",
        server_key=(str, Field(..., description="Active MCP server key to reconnect.")),
    )
    DoctorArgs = create_model(
        "ExternalMcpDoctorArgs",
        server_key=(
            Opt[str],
            Field(
                default=None,
                description=(
                    "Optional MCP server key to diagnose. Empty diagnoses the whole "
                    "External MCP catalog."
                ),
            ),
        ),
    )
    ListToolsArgs = create_model(
        "ExternalMcpListToolsArgs",
        server_key=(Opt[str], Field(default=None, description="Optional active MCP server key to inspect.")),
        search=(Opt[str], Field(default=None, description="Optional text filter for tool names/descriptions.")),
        include_schema=(bool, Field(default=True, description="Include each tool inputSchema.")),
    )
    CallArgs = create_model(
        "ExternalMcpCallArgs",
        server_key=(str, Field(..., description="Active MCP server key, e.g. Redis or Roblox_Studio.")),
        tool_name=(str, Field(..., description="Raw MCP tool name from external_mcp_list_tools, not the wrapped ext__ name.")),
        arguments=(Dict[str, Any], Field(default_factory=dict, description="JSON object of tool arguments.")),
    )
    ImportArgs = create_model(
        "ExternalMcpImportArgs",
        servers_json=(Union[Dict[str, Any], str], Field(..., description=(
            "MCP server config — the same mcpServers shape a Claude-Code .mcp.json uses. "
            "Pass it as a JSON OBJECT (preferred) OR a JSON string, e.g. "
            '{"mcpServers": {"redis": {"command": "docker", "args": ["run","-i","--rm","mcp/redis"]}}}. '
            "A bare single-server object or a {name: spec} map is also accepted."))),
    )
    SetActiveArgs = create_model(
        "ExternalMcpSetActiveArgs",
        server_keys=(Union[List[str], str], Field(..., description=(
            "Catalog server keys to ACTIVATE (max 5). Pass a LIST (preferred) like "
            "['redis'] or ['redis','Roblox_Studio'], OR a comma-separated string like "
            "'redis,Roblox_Studio'. Only active servers connect and expose their tools."))),
    )
    WaitArgs = create_model(
        "ExternalMcpWaitArgs",
        server_key=(str, Field(..., description="Active MCP server key to wait for, e.g. 'memory'.")),
        timeout_seconds=(int, Field(default=90, description=(
            "How long to block while the server connects (5-300s). A FIRST-run Docker image "
            "pull or cold npx/uvx download can be slow, so use 120-180 for a brand-new server."))),
    )

    def _status(server_key: Optional[str] = None, refresh: bool = True) -> str:
        return json.dumps(
            supervisor_snapshot(server_key or "", bool(refresh)),
            ensure_ascii=False,
            indent=2,
        )

    def _reconnect(server_key: str) -> str:
        return json.dumps(
            reconnect_server(server_key),
            ensure_ascii=False,
            indent=2,
        )

    def _doctor(server_key: Optional[str] = None) -> str:
        return json.dumps(
            diagnose_server(server_key or ""),
            ensure_ascii=False,
            indent=2,
        )

    def _list_tools(
        server_key: Optional[str] = None,
        search: Optional[str] = None,
        include_schema: bool = True,
    ) -> str:
        return json.dumps(
            list_server_tools(server_key or "", search or "", bool(include_schema)),
            ensure_ascii=False,
            indent=2,
        )

    def _call(server_key: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        return json.dumps(
            call_server_tool(server_key, tool_name, arguments or {}),
            ensure_ascii=False,
            indent=2,
        )

    def _import(servers_json: str) -> str:
        try:
            data = json.loads(servers_json) if isinstance(servers_json, str) else servers_json
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"invalid JSON: {exc}"}, ensure_ascii=False)
        if not isinstance(data, dict):
            return json.dumps({"ok": False, "error": "expected a JSON object"}, ensure_ascii=False)
        result = import_servers(data)
        if result.get("ok"):
            keys = list(result.get("added") or []) + list(result.get("updated") or [])
            result["next_step"] = (
                "Now call external_mcp_set_active with " + ", ".join(keys)
                + " to connect it, then external_mcp_status to verify."
            ) if keys else "No servers were parsed from the JSON."
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _set_active(server_keys: str) -> str:
        if isinstance(server_keys, str):
            keys = [k.strip() for k in server_keys.replace(";", ",").split(",") if k.strip()]
        elif isinstance(server_keys, (list, tuple)):
            keys = [str(k).strip() for k in server_keys if str(k).strip()]
        else:
            keys = []
        result = set_active(keys)
        result["next_step"] = (
            "Servers warm-connect in the BACKGROUND (a first-run Docker pull or npx/uvx "
            "download can take a minute). Call external_mcp_wait('<key>', 120) to BLOCK until "
            "it is ready instead of polling external_mcp_status in a loop, then use the bound "
            "ext__<server>__<tool> tools (or external_mcp_list_tools + external_mcp_call)."
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    def _wait(server_key: str, timeout_seconds: int = 90) -> str:
        return json.dumps(
            wait_for_server(server_key, timeout_seconds),
            ensure_ascii=False,
            indent=2,
        )

    return [
        StructuredTool.from_function(
            func=_status,
            name="external_mcp_status",
            description=(
                "Inspect active External MCP servers, their connection state, tool count, "
                "PIDs, stderr tails, and diagnostics. Use this whenever the user asks "
                "about MCPs, Roblox Studio MCP, missing external tools, or bridge health."
            ),
            args_schema=StatusArgs,
        ),
        StructuredTool.from_function(
            func=_reconnect,
            name="external_mcp_reconnect",
            description=(
                "Force reconnect one active External MCP server by key. Use after "
                "external_mcp_status shows a stuck, dead, or zero-tool server and the "
                "user wants recovery."
            ),
            args_schema=ReconnectArgs,
        ),
        StructuredTool.from_function(
            func=_doctor,
            name="external_mcp_doctor",
            description=(
                "Diagnose catalogued External MCP servers before or after activation. "
                "Infers transport, runtime prerequisites, command/PATH health, source "
                "URLs, missing secret placeholders, current status, blockers, and the "
                "next user-facing setup step. Use for every new or unknown MCP from a "
                "marketplace before giving installation instructions."
            ),
            args_schema=DoctorArgs,
        ),
        StructuredTool.from_function(
            func=_list_tools,
            name="external_mcp_list_tools",
            description=(
                "List exact tool names, descriptions, and schemas exposed by active External MCP "
                "servers. Use this before claiming a tool is unavailable, and whenever a large "
                "MCP server may have tools that were not directly bound into the current prompt."
            ),
            args_schema=ListToolsArgs,
        ),
        StructuredTool.from_function(
            func=_call,
            name="external_mcp_call",
            description=(
                "Call any tool on an active External MCP server by server_key, raw tool_name, "
                "and JSON arguments. Use this generic dispatcher when the direct ext__ tool "
                "was not selected or when external_mcp_list_tools showed the needed tool."
            ),
            args_schema=CallArgs,
        ),
        StructuredTool.from_function(
            func=_import,
            name="external_mcp_import",
            description=(
                "ADD one or more External MCP servers to Tlamatini's catalog from a JSON config "
                "(the mcpServers shape). Use this to set up a NEW MCP the user names or pastes "
                "(e.g. 'add the redis MCP') — you do NOT need a file-writing or shell tool, and "
                "you do NOT need the user to open the dialog; call this directly with the JSON. "
                "After importing, call external_mcp_set_active to connect it."
            ),
            args_schema=ImportArgs,
        ),
        StructuredTool.from_function(
            func=_set_active,
            name="external_mcp_set_active",
            description=(
                "ACTIVATE catalogued External MCP servers (max 5) so they connect and expose "
                "their tools. Call after external_mcp_import, or to enable an already-catalogued "
                "server, then call external_mcp_wait to block until it is ready."
            ),
            args_schema=SetActiveArgs,
        ),
        StructuredTool.from_function(
            func=_wait,
            name="external_mcp_wait",
            description=(
                "WAIT (block) until an active External MCP server is connected and exposing its "
                "tools. Use this right after external_mcp_set_active instead of polling "
                "external_mcp_status in a loop — it gives a slow first-run server (a Docker image "
                "being pulled, or a cold npx/uvx download) time to come online, then returns when "
                "ready. On timeout it says so and tells you to wait longer; never give up on the task."
            ),
            args_schema=WaitArgs,
        ),
    ]


def is_external_mcp_tool_name(name: str) -> bool:
    return str(name or "").startswith("ext__") or str(name or "") in _SUPERVISOR_TOOL_NAMES


# At most one supervise pass runs at a time — a second chat request while one is
# in flight is a cheap no-op (the running pass already covers the active set).
_supervise_gate = threading.Lock()


def _supervise_active_async(active: List[str], servers: Dict[str, Any]) -> None:
    """Run ``_refresh_and_supervise_active`` on a BACKGROUND thread.

    NEVER on the calling thread — so the chat-build path
    (``get_external_mcp_tools``) never blocks on a ``tools/list`` round-trip or a
    zero-tool reconnect. This is the fix for the synchronous supervise+refresh
    that stalled the chat while merely re-listing tools that were already cached.
    Fail-safe: swallows every error (never raises into the tool-binding path).
    """
    if not active:
        return
    if not _supervise_gate.acquire(blocking=False):
        return  # a supervise pass is already running

    def _run() -> None:
        try:
            _refresh_and_supervise_active(list(active), dict(servers))
        except Exception:
            logger.exception("[ExternalMCP] background supervise failed")
        finally:
            _supervise_gate.release()

    threading.Thread(target=_run, daemon=True).start()


def get_external_mcp_tools() -> List[Any]:
    """Return LangChain tools for every active external MCP server's tools.

    Defensive: never raises into the tool-binding path — returns [] on error.
    Fast path: returns [] immediately when no servers are active.
    """
    try:
        tools: List[Any] = _build_supervisor_tools()
        data = load_catalog()
        servers = data.get("mcpServers", {})
        active = [k for k in data.get("active", []) if k in servers][:MAX_ACTIVE]
        if not active:
            return tools
        # Kick background connects for any active server not yet live. We do NOT
        # connect synchronously here — that synchronous handshake is exactly
        # what stalled the chat and dropped the redis MCP at 12 s. We only bind
        # tools from servers that are ALREADY live; the rest come online shortly.
        _warm_connect_async(active, servers)
        # Refresh live clients + restart stuck zero-tool bridges on a BACKGROUND
        # thread — NEVER inline. The synchronous tools/list re-list here used to
        # stall the whole chat build (a hung server could block for the full
        # tools/list timeout) while only re-listing tools that were ALREADY
        # cached. We bind from the CACHED client.tools; a server whose tools land
        # after this turn surfaces them on the next request, and the background
        # supervisor keeps the cache fresh + reconnects stuck bridges. (audit [7])
        _supervise_active_async(active, servers)
        with _clients_lock:
            live = [(k, _clients[k]) for k in active
                    if k in _clients and _clients[k].alive()]
        for key, client in live:
            for tdef in client.tools:
                try:
                    built = _build_tool(key, tdef)
                    if built is not None:
                        tools.append(built)
                except Exception:
                    logger.exception("[ExternalMCP] failed to wrap %s tool", key)
        live_keys = {k for k, _ in live}
        not_live = [k for k in active if k not in live_keys]
        if not_live:
            # Visibility: say WHY each active server isn't bound yet, so the log
            # explains the gap instead of it being silent (the redis case).
            details = "; ".join(
                f"{k}: {('connecting' if k in _connecting else _last_errors.get(k, 'pending'))}"
                for k in not_live
            )
            logger.info("[ExternalMCP] active but not yet bound — %s", details)
        if tools:
            logger.info("[ExternalMCP] bound %d external tool(s) from %d live server(s)",
                        len(tools), len(live))
        return tools
    except Exception:
        logger.exception("[ExternalMCP] get_external_mcp_tools failed")
        return []


def external_mcp_root_pids() -> set:
    """PIDs of the live external-MCP server launcher processes. The command
    watchdog MUST NOT reap these: a stdio MCP server is long-lived and sits IDLE
    between JSON-RPC messages, which otherwise looks exactly like a hung
    ``cmd.exe`` — which was tearing down the Roblox StudioMCP proxy (and its
    :4932 listener) a few minutes after connect. Fail-safe: returns an empty set
    on any error (never raises into the watchdog).
    """
    pids: set = set()
    try:
        with _clients_lock:
            clients = list(_clients.values()) + list(_launching_clients.values())
        for c in clients:
            proc = getattr(c, "proc", None)
            pid = getattr(proc, "pid", None)
            if pid:
                pids.add(int(pid))
    except Exception:
        pass
    return pids


def shutdown() -> None:
    with _clients_lock:
        for key in list(_clients.keys()):
            try:
                _clients.pop(key).close()
            except Exception:
                pass


atexit.register(shutdown)
