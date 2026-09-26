# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Model adapter for a single prompt-flow-panel run, using the existing RAG stack."""
import asyncio
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from channels.db import database_sync_to_async

from .services.prompt_flow_panel import FlowError, FlowStopped


class PromptFlowPanelRuntime:
    def __init__(self, user, emit):
        self.user, self.emit = user, emit
        self.key = f"prompt_flow_panel_{user.pk}_{uuid4().hex}"
        self.chain = None
        self.history = []
        self.context = []
        self.directory = None
        self.cancelled = False
        self.active_epoch = None
        self.catalog = None

    @database_sync_to_async
    def _catalog(self):
        from .models import Agent, Mcp, Omission, Tool
        omission = Omission.objects.filter(omissionName="omission-1").first()
        return (
            list(Agent.objects.values("agentName", "agentDescription", "agentContent")),
            list(Mcp.objects.values("mcpName", "mcpDescription", "mcpContent")),
            list(Tool.objects.values("toolName", "toolDescription", "toolContent")),
            omission.omissionContent if omission else "",
        )

    async def _build(self, context=None):
        from .rag import BasicPromptOnlyChain, setup_llm, setup_llm_with_context
        from .path_guard import get_app_temp_root
        if self.catalog is None:
            self.catalog = await self._catalog()
        if self.cancelled:
            raise FlowStopped()
        if context is not None:
            if self.directory is None:
                temp_root = get_app_temp_root()
                Path(temp_root).mkdir(parents=True, exist_ok=True)
                self.directory = Path(tempfile.mkdtemp(prefix="prompt-flow-panel-", dir=temp_root))
            # Every rebuild gets its own filename: embedding caches must not reuse
            # the previous text at a stable path.
            filename = f"context-{uuid4().hex}.txt"
            await asyncio.to_thread((self.directory / filename).write_text, context, encoding="utf-8")
            chain = await asyncio.to_thread(setup_llm_with_context, str(self.directory), *self.catalog, filename=filename)
            if chain is None or isinstance(chain, BasicPromptOnlyChain):
                self._close_chain(chain)
                raise FlowError("Embedding setup failed. The flow stopped without claiming that context was loaded.")
        else:
            chain = await asyncio.to_thread(setup_llm, *self.catalog, include_application_context=False)
            if chain is None:
                raise FlowError("The configured model could not be initialized. Check Tlamatini's model settings and log.")
        if self.cancelled:
            self._close_chain(chain)
            raise FlowStopped()
        old, self.chain = self.chain, chain
        self._close_chain(old)

    @staticmethod
    def _close_chain(chain):
        if chain is not None:
            try:
                client = chain.getHttpxClientInstance()
                if client:
                    client.close()
            except Exception:
                pass

    async def prompt(self, text, config):
        from langchain_core.messages import AIMessage, HumanMessage
        from .cancellation import begin_llm_run
        from .global_state import global_state
        from .rag import ask_rag
        from .self_healing import register_status_broadcaster, unregister_status_broadcaster
        if self.chain is None:
            await self._build()
        if self.cancelled:
            raise FlowStopped()
        self.active_epoch = begin_llm_run(self.key)
        loop = asyncio.get_running_loop()

        def status(message):
            if not self.cancelled:
                asyncio.run_coroutine_threadsafe(self.emit("progress", message=message), loop)

        register_status_broadcaster(self.key, status)
        try:
            output = await asyncio.to_thread(ask_rag, self.chain, {
                "input": text, "conversation_user_id": self.key,
                "cancel_run_epoch": self.active_epoch,
                "multi_turn_enabled": config["multi_turn"], "acpx_enabled": config["acpx"],
            }, chat_history=self.history[-16:])
            if self.cancelled:
                raise FlowStopped()
            if not isinstance(output, str) or not output.strip():
                raise FlowError("The model returned no answer.")
            self.history.extend([HumanMessage(content=text), AIMessage(content=output)])
            return output
        finally:
            unregister_status_broadcaster(self.key, status)
            global_state.set_state(f"last_request_meta::{self.key}", None)
            global_state.set_state(f"last_orphan_survivors::{self.key}", None)
            self.active_epoch = None

    async def feed(self, text):
        if not text.strip():
            raise FlowError("There is no text to embed.")
        candidate = self.context + [text]
        if sum(map(len, candidate)) > 2_000_000:
            raise FlowError("This run's embedding text exceeds 2,000,000 characters. Flush embeddings before adding more.")
        await self._build("\n\n".join(candidate))
        self.context = candidate

    async def flush(self):
        await self._build()
        self.context.clear()

    async def clean_history(self):
        self.history.clear()

    async def comment(self, text):
        from langchain_core.messages import HumanMessage
        self.history.append(HumanMessage(content=text))

    def cancel(self):
        self.cancelled = True
        if self.active_epoch is not None:
            from .cancellation import request_cancel_generation, clear_cancel_generation
            request_cancel_generation(self.key)
            # Keep the run's permanent latch, release the legacy process-wide
            # flag so stopping this designer does not cancel another chat tab.
            clear_cancel_generation()

    async def close(self):
        self._close_chain(self.chain)
        if self.directory is not None:
            await asyncio.to_thread(shutil.rmtree, self.directory, ignore_errors=True)

