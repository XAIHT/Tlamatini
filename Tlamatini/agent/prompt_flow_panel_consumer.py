# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Authenticated, connection-scoped playback; never infer completion from prose."""
import asyncio
import json
from uuid import uuid4

from channels.generic.websocket import AsyncWebsocketConsumer

from .prompt_flow_panel_runtime import PromptFlowPanelRuntime
from .services.prompt_flow_panel import FlowError, FlowRunner, FlowStopped, MAX_FILE_BYTES


class PromptFlowPanelConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.runner = None
        self.task = None
        self.connected = False
        self.run_id = None
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()
        self.connected = True
        await self.emit("ready")

    async def emit(self, event, **data):
        if self.connected:
            await self.send(text_data=json.dumps({"event": event, "run_id": self.run_id, **data}))

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data is None or len(text_data.encode("utf-8")) > MAX_FILE_BYTES:
                raise FlowError("Send a .fpmt document smaller than 5 MiB.")
            message = json.loads(text_data)
            if not isinstance(message, dict):
                raise FlowError("Expected a flow command.")
            action = message.get("action")
            active = self.task is not None and not self.task.done()
            if action == "start":
                if active:
                    raise FlowError("The current run is still active. Stop it before starting another.")
                runtime = PromptFlowPanelRuntime(self.user, self.emit)
                runner = FlowRunner(message.get("flow"), runtime, self.emit)
                self.run_id = uuid4().hex
                self.runner = runner
                await self.emit("state", status="running")
                self.task = asyncio.create_task(self._play(runner, runtime))
            elif action == "ping":
                await self.emit("pong")
            elif not active or message.get("run_id") != self.run_id:
                raise FlowError("This flow run is no longer active.")
            elif action == "stop":
                self.runner.stop()
                await self.emit("state", status="stopping")
            elif action in {"pause", "resume"}:
                if self.runner.stopped.is_set():
                    raise FlowError("The flow is stopping.")
                if action == "pause":
                    self.runner.resumed.clear()
                else:
                    self.runner.resumed.set()
                await self.emit("state", status="paused" if action == "pause" else "running")
            elif action == "reply":
                self.runner.reply(message.get("request_id"), message.get("value"))
            else:
                raise FlowError("Unknown flow command.")
        except (ValueError, TypeError, KeyError) as exc:
            await self.emit("error", message=str(exc), command=True)

    async def _play(self, runner, runtime):
        status, message = "completed", "Flow completed."
        try:
            await runner.run()
        except FlowStopped:
            status, message = "stopped", "Flow stopped. No further operations will run."
        except Exception as exc:
            status, message = "failed", str(exc)
        finally:
            try:
                await runtime.close()
            finally:
                await self.emit("state", status=status, message=message)

    async def disconnect(self, close_code):
        self.connected = False
        if self.runner and self.task and not self.task.done():
            # Do not cancel asyncio.to_thread: cancellation of its awaiter does
            # not stop the model worker. Drain it before freeing its resources.
            self.runner.stop()

