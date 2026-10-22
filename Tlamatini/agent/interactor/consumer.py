# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Session-authenticated, same-origin editor transport. Browsers send receipts only."""
import asyncio
import ipaddress
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from ..chat_voice_consumer import same_origin
from .hub import hub
from .protocol import MAX_FRAME, InteractorError


class InteractorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.client_id = None
        user = self.scope.get("user")
        session_key = getattr(self.scope.get("session"), "session_key", None)
        if not user or not user.is_authenticated or not session_key:
            await self.close(code=4401)
            return
        if not same_origin(self.scope):
            await self.close(code=4403)
            return
        try:
            local = ipaddress.ip_address((self.scope.get("client") or ("",))[0]).is_loopback
        except ValueError:
            local = False
        self.loop = asyncio.get_running_loop()
        self.outbox = asyncio.Queue(maxsize=16)
        try:
            self.client_id = hub.connect((str(user.pk), session_key), self.emit, local)
        except InteractorError:
            await self.close(code=4429)
            return
        await self.accept()
        self.sender = asyncio.create_task(self.send_loop())
        await self.send(text_data=json.dumps({"t": "hello", "client_id": self.client_id, "local": local}))

    def emit(self, message):
        def enqueue():
            try:
                self.outbox.put_nowait(message)
            except asyncio.QueueFull:
                hub.disconnect(self.client_id)
                asyncio.create_task(self.close(code=4429))
        self.loop.call_soon_threadsafe(enqueue)

    async def send_loop(self):
        while True:
            await self.send(text_data=json.dumps(await self.outbox.get()))

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data or len(text_data) > MAX_FRAME:
            await self.close(code=4400)
            return
        try:
            message = json.loads(text_data)
            if not isinstance(message, dict) or message.get("t") not in {"access", "receipt", "stop", "ping"}:
                raise ValueError("Invalid editor frame")
            if message["t"] == "ping":
                await self.send(text_data='{"t":"pong"}')
            else:
                hub.receive(self.client_id, message)
        except (ValueError, TypeError):
            await self.close(code=4400)

    async def disconnect(self, close_code):
        if self.client_id:
            hub.disconnect(self.client_id)
        sender = getattr(self, "sender", None)
        if sender:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
