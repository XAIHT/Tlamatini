# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Bounded request/receipt bridge between synchronous tools and an authenticated tab.

No background worker, process, polling loop or disk mirror. Read always makes a
round trip to CodeMirror. Disconnect/cancellation releases waiting tool calls.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from . import context
from .protocol import InteractorError


@dataclass
class Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None


@dataclass
class Endpoint:
    owner: tuple[str, str]
    emit: object
    local: bool
    enabled: bool = True
    stop_version: int = 0
    pending: dict = field(default_factory=dict)
    mutation: threading.Lock = field(default_factory=threading.Lock)


class Hub:
    def __init__(self):
        self.lock = threading.RLock()
        self.clients = {}

    def connect(self, owner, emit, local):
        with self.lock:
            if len(self.clients) >= 128:
                raise InteractorError("Too many live editor connections. Close an unused tab.")
            client_id = secrets.token_urlsafe(24)
            self.clients[client_id] = Endpoint(owner, emit, local)
            return client_id

    def endpoint(self, request):
        with self.lock:
            endpoint = self.clients.get(request.client_id)
            if endpoint is None or endpoint.owner != request.owner:
                raise InteractorError("The originating editor tab is not connected. Open the chat editor and send the request there.", "disconnected")
            if not endpoint.enabled:
                raise InteractorError("Live editor access is paused by the user.", "paused")
            if request.stop_version is None:
                request.stop_version = endpoint.stop_version
            elif request.stop_version != endpoint.stop_version:
                raise InteractorError("The user took over this editing turn. Wait for a new chat request.", "aborted")
            return endpoint

    def disconnect(self, client_id):
        with self.lock:
            endpoint = self.clients.pop(client_id, None)
            if endpoint:
                self._finish_pending(endpoint, "The editor tab disconnected.", "disconnected")

    def _finish_pending(self, endpoint, message, status):
        for pending in endpoint.pending.values():
            pending.result = {"ok": False, "status": status, "message": message}
            pending.event.set()

    def receive(self, client_id, message):
        with self.lock:
            endpoint = self.clients.get(client_id)
            if not endpoint:
                return
            if message.get("t") == "access":
                endpoint.enabled = message.get("enabled") is True
                if not endpoint.enabled:
                    endpoint.stop_version += 1
                    self._finish_pending(endpoint, "The user paused live editor access.", "paused")
            elif message.get("t") == "stop":
                endpoint.stop_version += 1
                self._finish_pending(endpoint, "The user took over the editor. End this editing turn.", "aborted")
            elif message.get("t") == "receipt":
                pending = endpoint.pending.get(message.get("id"))
                if pending and not pending.event.is_set() and isinstance(message.get("result"), dict):
                    pending.result = message["result"]
                    pending.event.set()

    def call(self, request, action, payload=None, timeout=10, visibility_grace=0):
        if context.cancelled(request):
            raise InteractorError("This chat request was cancelled.", "aborted")
        endpoint = self.endpoint(request)
        mutation = action != "read"
        if mutation and not endpoint.mutation.acquire(blocking=False):
            raise InteractorError("An editor action is already running. Read before trying again.", "busy")
        command_id = secrets.token_urlsafe(18)
        pending = Pending()
        # The browser may pause presentation while its tab is covered/minimized.
        # One bounded command survives that pause; never replay its typed prefix.
        timeout += min(120, max(0, visibility_grace))
        try:
            with self.lock:
                if len(endpoint.pending) >= 4:
                    raise InteractorError("The editor has too many pending requests.", "busy")
                endpoint.pending[command_id] = pending
            endpoint.emit({"t": "command", "id": command_id, "action": action,
                           "deadline": time.time() * 1000 + timeout * 1000,
                           "payload": payload or {}})
            until = time.monotonic() + timeout
            while not pending.event.wait(.1):
                if context.cancelled(request) or time.monotonic() >= until:
                    endpoint.emit({"t": "cancel", "id": command_id})
                    raise InteractorError("Editor action cancelled or timed out. Read the live buffer; a partially typed prefix may remain. Never replay it blindly.", "aborted")
            result = pending.result or {}
            if result.get("ok") is not True:
                raise InteractorError(str(result.get("message") or "The editor refused this action."),
                                      str(result.get("status") or "refused"))
            return result
        finally:
            with self.lock:
                endpoint.pending.pop(command_id, None)
            if mutation:
                endpoint.mutation.release()


hub = Hub()
