# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""``ws/terminals/`` -- the browser side of Terminater.

One connection per open page (chat, Agentic Control Panel, Prompt Flow Panel).
Every connection of the same user sees the SAME terminals: the hub owns them, the
page is only a window onto them.  Closing a page therefore never kills a shell.

Frames (all JSON):

  browser -> server   open | in | resize | line | close | kill | focus | layout |
                      rename | snapshot | handback | abort_typing | abort |
                      advisor | ping
  server -> browser   hello | opened | out | replay | state | exit | closed |
                      removed | command | hung | input_request | handover |
                      warn | notice | ui | title | cwd | title_set | clear | error

Keystrokes are processed strictly in order (one worker per connection): a
reordered "ls" would be a different command.  Slow requests (opening a shell
waits for its first prompt) run beside that worker so typing never stalls.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from . import terminal_hub
from .chat_voice_consumer import same_origin

logger = logging.getLogger(__name__)

MAX_FRAME = 1_000_000            # bytes of an incoming frame we are willing to parse
OUT_CHUNK = 65_536               # characters per outgoing output frame
MAX_PENDING_CHARS = 4_000_000    # output buffered for a slow browser before it must resync
FLUSH_DELAY = 0.016              # ~60 fps coalescing of terminal output
REPLAY_CHARS = 60_000

_ORDERED = {"in", "resize", "line", "handback", "abort_typing", "advisor"}


class TerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        self.connected = False
        self._closed = False
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not same_origin(self.scope):
            await self.close(code=4403)
            return
        if not terminal_hub.terminals_enabled():
            await self.close(code=4404)
            return
        self.user_key = str(user.pk)
        self.loop = asyncio.get_running_loop()
        self._outq: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._inq: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._buf: Dict[str, list] = {}
        self._seq: Dict[str, int] = {}
        self._flush_scheduled = False
        self._tasks: set = set()
        await self.accept()
        self.connected = True
        try:
            self.hub = await asyncio.to_thread(terminal_hub.get_hub)
            server = self.scope.get("server") or (None, None)
            terminal_hub.note_server_port(server[1] or 0)
            terminal_hub.ensure_ready()
        except Exception as exc:  # noqa: BLE001
            logger.warning("--- [TERMINATER] hub unavailable: %s", exc)
            await self._send({"t": "error", "code": "hub_unavailable",
                              "message": f"Terminals are unavailable: {exc}"})
            await self.close(code=1011)
            return
        self._sender = self._spawn(self._send_loop())
        self._worker = self._spawn(self._ordered_loop())
        self._cb = self._on_hub_event
        await asyncio.to_thread(self.hub.add_listener, self.user_key, self._cb)
        await self._send_hello()

    def _spawn(self, coro) -> "asyncio.Task":
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------------ output
    def _on_hub_event(self, event: Dict[str, Any]) -> None:
        """Called from engine threads: hop onto the loop and never block."""
        try:
            self.loop.call_soon_threadsafe(self._enqueue, event)
        except RuntimeError:
            pass  # loop closed: the connection is going away

    def _enqueue(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        if event.get("t") == "out":
            tid = str(event.get("id") or "")
            entry = self._buf.setdefault(tid, [0, []])
            text = event.get("d") or ""
            entry[1].append(text)
            entry[0] += len(text)
            self._seq[tid] = int(event.get("seq") or 0)
            if entry[0] > MAX_PENDING_CHARS:
                # The browser cannot keep up: drop the backlog and make it resync
                # from the server-side replay instead of growing without bound.
                self._buf[tid] = [0, []]
                self._outq.put_nowait({"t": "resync", "id": tid})
                return
            if not self._flush_scheduled:
                self._flush_scheduled = True
                self.loop.call_later(FLUSH_DELAY, self._flush)
            return
        self._flush()          # keep the order: output before the state change that follows it
        self._outq.put_nowait(event)

    def _flush(self) -> None:
        self._flush_scheduled = False
        for tid, entry in list(self._buf.items()):
            if not entry[1]:
                continue
            data = "".join(entry[1])
            self._buf[tid] = [0, []]
            seq = self._seq.get(tid, 0)
            for start in range(0, len(data), OUT_CHUNK):
                self._outq.put_nowait({"t": "out", "id": tid, "d": data[start:start + OUT_CHUNK], "seq": seq})

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self.connected and not self._closed:
            try:
                await self.send(text_data=json.dumps(payload, default=str))
            except Exception:  # noqa: BLE001 -- a dead socket ends the loops below
                self._closed = True

    async def _send_loop(self) -> None:
        while not self._closed:
            event = await self._outq.get()
            await self._send(event)

    async def _send_hello(self) -> None:
        listing = await asyncio.to_thread(self.hub.call, "list", {"user": self.user_key})
        replay: Dict[str, str] = {}
        sp = await asyncio.to_thread(self.hub.space, self.user_key)
        for sid, session in list(sp.sessions.items()):
            replay[sid] = await asyncio.to_thread(session.snapshot, REPLAY_CHARS)
        await self._send({
            "t": "hello", "terminals": listing.get("terminals", []), "active": listing.get("active", ""),
            "ui": listing.get("ui", {}), "kinds": listing.get("available_kinds", []),
            "max": listing.get("max_terminals", 0), "replay": replay,
        })

    # ------------------------------------------------------------------- input
    async def receive(self, text_data: Optional[str] = None, bytes_data: Optional[bytes] = None) -> None:
        if not text_data or len(text_data) > MAX_FRAME:
            return
        try:
            msg = json.loads(text_data)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        kind = str(msg.get("t") or "")
        if kind == "ping":
            await self._send({"t": "pong"})
        elif kind in _ORDERED:
            self._inq.put_nowait(msg)
        else:
            self._spawn(self._run_unordered(msg))

    async def _ordered_loop(self) -> None:
        while not self._closed:
            msg = await self._inq.get()
            try:
                await asyncio.to_thread(self._handle_ordered, msg)
            except Exception:  # noqa: BLE001
                logger.debug("--- [TERMINATER] ordered frame failed", exc_info=True)

    def _session(self, msg: Dict[str, Any]):
        sp = self.hub.space(self.user_key)
        return sp, self.hub._get(sp, msg.get("id"), required=False)

    def _handle_ordered(self, msg: Dict[str, Any]) -> None:
        kind = msg.get("t")
        _, session = self._session(msg)
        if session is None:
            return
        if kind == "in":
            data = msg.get("d")
            if isinstance(data, str) and data and len(data) <= 100_000:
                session.user_input(data)
        elif kind == "resize":
            try:
                session.resize(int(msg.get("cols", 0)), int(msg.get("rows", 0)))
            except (TypeError, ValueError):
                pass
        elif kind == "line":
            session.set_user_line(str(msg.get("text") or ""))
        elif kind == "handback":
            session.handover_resume.set()
        elif kind == "abort_typing":
            session._abort_typing.set()
        elif kind == "advisor":
            session.advisor_enabled = bool(msg.get("on", True))

    async def _run_unordered(self, msg: Dict[str, Any]) -> None:
        try:
            await asyncio.to_thread(self._handle_unordered, msg)
        except Exception as exc:  # noqa: BLE001
            await self._send({"t": "error", "code": "internal", "message": str(exc)})

    def _handle_unordered(self, msg: Dict[str, Any]) -> None:
        kind = msg.get("t")
        user = self.user_key
        hub = self.hub
        if kind == "open":
            res = hub.call("open", {"user": user, "kind": msg.get("kind") or "powershell",
                                    "title": msg.get("title") or "", "cwd": msg.get("cwd") or "",
                                    "show": True})
            if not res.get("ok"):
                self._emit_error(res)
        elif kind in ("close", "kill"):
            res = hub.call("force_kill" if msg.get("force") else "kill",
                           {"user": user, "terminal": msg.get("id")})
            if not res.get("ok"):
                self._emit_error(res)
        elif kind == "abort":
            hub.call("abort", {"user": user, "terminal": msg.get("id")})
        elif kind == "focus":
            hub.call("focus", {"user": user, "terminal": msg.get("id")})
        elif kind == "layout":
            hub.call("layout", {"user": user, "layout": msg.get("layout") or "",
                                "area": msg.get("area") or "", "show": msg.get("show", "")})
        elif kind == "rename":
            hub.call("rename", {"user": user, "terminal": msg.get("id"), "title": msg.get("title") or ""})
        elif kind == "snapshot":
            sp, session = self._session(msg)
            if session is not None:
                self.loop.call_soon_threadsafe(
                    self._outq.put_nowait,
                    {"t": "replay", "id": session.id, "d": session.snapshot(REPLAY_CHARS), "seq": session.seq})

    def _emit_error(self, res: Dict[str, Any]) -> None:
        self.loop.call_soon_threadsafe(
            self._outq.put_nowait,
            {"t": "error", "code": res.get("code", "error"), "message": res.get("message", "Request failed.")})

    # -------------------------------------------------------------- disconnect
    async def disconnect(self, close_code: int) -> None:
        self._closed = True
        self.connected = False
        hub = getattr(self, "hub", None)
        cb = getattr(self, "_cb", None)
        if hub is not None and cb is not None:
            try:
                await asyncio.to_thread(hub.remove_listener, self.user_key, cb)
            except Exception:  # noqa: BLE001
                pass
        for task in list(getattr(self, "_tasks", ())):
            task.cancel()
