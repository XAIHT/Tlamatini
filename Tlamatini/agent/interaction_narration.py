# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Bounded narration receipts. Browsers can acknowledge, never issue commands."""
from __future__ import annotations

import secrets
import logging
import threading
import time

from .interaction_settings import spoken_text

logger = logging.getLogger(__name__)


class Narration:
    @staticmethod
    def emit(client, event):
        try:
            client['emit'](event)
            return True
        except Exception:  # A speech transport failure cannot change a command result.
            logger.warning('Terminal narration connection became unavailable.', exc_info=True)
            return False

    def __init__(self):
        self.lock = threading.RLock()
        self.clients = {}
        self.pending = {}

    def connect(self, user, emit):
        key = secrets.token_urlsafe(24)
        with self.lock:
            self.clients[key] = {"user": str(user), "emit": emit, "visible": False, "seen": 0}
        return key

    def disconnect(self, key):
        with self.lock:
            self.clients.pop(key, None)
            for item in self.pending.values():
                if item["client"] == key:
                    item["result"] = "cancel"
                    item["event"].set()

    def receive(self, key, message):
        with self.lock:
            client = self.clients.get(key)
            if not client:
                return
            if message.get("t") == "narration_presence":
                client.update(visible=message.get("visible") is True, seen=time.monotonic())
            elif message.get("t") == "narration_receipt":
                item = self.pending.get(message.get("id"))
                status = message.get("status")
                if item and item["client"] == key and status in {"spoken", "skip", "cancel"}:
                    item["result"] = status
                    item["event"].set()

    def send(self, user, text, *, terminal="", wait=False, cancelled=lambda: False):
        with self.lock:
            candidates = [(key, client) for key, client in self.clients.items()
                          if client["user"] == str(user) and client["visible"] and time.monotonic() - client["seen"] < 35]
            if not candidates:
                return not wait
            key, client = max(candidates, key=lambda pair: pair[1]["seen"])
            command_id = secrets.token_urlsafe(18)
            item = {"client": key, "event": threading.Event(), "result": None}
            if wait:
                self.pending[command_id] = item
        try:
            sent = self.emit(client, {"t": "narration", "id": command_id, "terminal": terminal,
                                     "text": text, "wait": wait, "deadline": time.time() * 1000 + 120_000})
            if not sent:
                return not wait
            if not wait:
                return True
            deadline = time.monotonic() + 120
            while not item["event"].wait(.1):
                if cancelled() or time.monotonic() >= deadline:
                    return False
            return not cancelled() and item["result"] in {"spoken", "skip"}
        finally:
            with self.lock:
                self.pending.pop(command_id, None)
            if wait and (item["result"] not in {"spoken", "skip"} or cancelled()):
                self.emit(client, {"t": "narration_cancel", "id": command_id, "terminal": terminal})

    def cancel_terminal(self, user, terminal):
        with self.lock:
            clients = [client for client in self.clients.values() if client["user"] == str(user)]
        for client in clients:
            self.emit(client, {"t": "narration_cancel", "terminal": terminal})

    def present(self, stage, session, params):
        preferences = params.get("_interaction", {})
        if not preferences.get("narrate_terminal"):
            return True
        if stage == "cancel":
            self.cancel_terminal(params["user"], session.id)
            return True
        when = preferences["narration_when"]
        if (stage == "before" and when not in {"before", "during"}) or (stage == "after" and when != "after"):
            return True
        cancellation = params.get("_cancel_event")

        def cancelled():
            return session._abort_typing.is_set() or (isinstance(cancellation, threading.Event) and cancellation.is_set()) or not session.pty_alive()

        from .terminal_hub import load_engine
        engine = load_engine()
        secret = engine._tx.parse_flag(params.get("secret"), False, True)[0]
        text = spoken_text(engine.TerminalHub._text(params), params.get("explanation", ""), preferences, secret=secret)
        return self.send(params["user"], text, terminal=session.id,
                         wait=stage == "before" and when == "before" and preferences["narration_wait"], cancelled=cancelled)

    def outcome(self, action, params, result):
        if action not in {"run", "type", "handover", "wait"}:
            return
        preferences = params.get("_interaction", {})
        if not preferences.get("narrate_terminal"):
            return
        status = result.get("status")
        messages = {"completed": "The command finished.", "typed": "The line is ready. Press Enter when you want to run it.",
                    "command_failed": "The command failed. Review its output.", "hung": "The command has been silent. Review it or keep waiting.",
                    "operator_required": "This step needs your input.", "typing_unverified": "The typed line could not be verified. Please review it.",
                    "aborted": "Typing stopped.", "timeout": "The command is still running after the wait window."}
        mode = preferences.get("announce_outcomes", "errors")
        if status in messages and (mode == "all" or mode == "errors" and status not in {"completed", "typed"}):
            self.send(params["user"], messages[status], terminal=result.get("terminal_id", ""))


narration = Narration()
