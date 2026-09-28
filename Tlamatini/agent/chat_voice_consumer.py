# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Authenticated direct dictation, isolated from model/chat orchestration."""
import asyncio
import json
import re
from urllib.parse import urlsplit

from channels.generic.websocket import AsyncWebsocketConsumer

from .chat_voice_runtime import runtime, TERMINAL_EVENTS
from .chat_voice_settings import validate_capture_settings


def same_origin(scope):
    """Cookie auth alone cannot authorize cross-site host-microphone capture."""
    headers = dict(scope.get("headers", []))
    try:
        origin = urlsplit(headers.get(b"origin", b"").decode("ascii"))
        host = headers.get(b"host", b"").decode("ascii").lower()
        return origin.scheme in {"http", "https"} and origin.netloc.lower() == host and bool(host)
    except (ValueError, UnicodeError):
        return False


class ChatVoiceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.connected = False
        self.run_id = None
        self.cancelled = False
        self.ready_task = None
        self.start_task = None
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not same_origin(self.scope):
            await self.close(code=4403)
            return
        await self.accept()
        self.connected = True
        self.loop = asyncio.get_running_loop()
        await self.emit({"event": "preparing"})
        self.ready_task = asyncio.create_task(self.prepare())

    async def emit(self, event):
        if self.connected:
            await self.send(text_data=json.dumps(event))

    async def prepare(self):
        try:
            await asyncio.to_thread(runtime.ensure_ready)
            await self.emit({"event": "ready", **runtime.get_options()})
        except Exception:
            await self.emit({"event": "error", "message":
                             "Whisperer could not start. Check the audio runtime and Tlamatini log."})

    async def receive(self, text_data=None, bytes_data=None):
        run_id = None
        try:
            if text_data is None or len(text_data) > 1024:
                raise ValueError("Invalid dictation command.")
            message = json.loads(text_data)
            if not isinstance(message, dict):
                raise ValueError("Expected a dictation command.")
            action, run_id = message.get("action"), message.get("run_id")
            if action == "options":
                if self.run_id:
                    raise ValueError("A recording is active.")
                try:
                    options = await asyncio.to_thread(runtime.get_options, True)
                    await self.emit({"event": "options", **options})
                except Exception:
                    await self.emit({"event": "options", "devices_error": True})
                return
            if action == "start":
                if self.run_id:
                    raise ValueError("This dictation is still active.")
                if not isinstance(run_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", run_id):
                    raise ValueError("Invalid dictation identifier.")
                capture_settings = validate_capture_settings(message.get("settings", {}))
                self.run_id, self.cancelled = run_id, False
                await self.emit({"event": "starting", "run_id": run_id})
                self.start_task = asyncio.create_task(self.start(run_id, capture_settings))
            elif action == "cancel" and run_id == self.run_id:
                self.cancelled = True
                await asyncio.to_thread(runtime.cancel, run_id)
                await self.emit({"event": "cancelling", "run_id": run_id})
            else:
                raise ValueError("Unknown or stale dictation command.")
        except (ValueError, TypeError):
            await self.emit({"event": "rejected", "run_id": run_id if isinstance(run_id, str) else None,
                             "message": "Invalid microphone settings or overlapping dictation command."})

    async def start(self, run_id, capture_settings):
        def relay(event):
            # No socket writes on the audio/worker thread.
            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.on_event(event)))
        try:
            await asyncio.to_thread(runtime.start, run_id, relay, capture_settings)
            if self.cancelled or not self.connected:
                await asyncio.to_thread(runtime.cancel, run_id)
        except Exception as exc:
            if self.run_id == run_id:
                self.run_id = None
            await self.emit({"event": "error", "run_id": run_id, "message": str(exc)})

    async def on_event(self, event):
        if event.get("run_id") != self.run_id:
            return
        if self.cancelled and event.get("event") == "result":
            event = {"event": "cancelled", "run_id": self.run_id}
        if event.get("event") in TERMINAL_EVENTS:
            self.run_id = None
        await self.emit(event)

    async def disconnect(self, close_code):
        self.connected = False
        self.cancelled = True
        if self.run_id:
            await asyncio.to_thread(runtime.cancel, self.run_id)
