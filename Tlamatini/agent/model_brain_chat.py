# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""The chat model the Model Brain configures (agent/model_brain.py).

``langchain-ollama`` 0.2.1 (the version Tlamatini ships) can neither send Ollama's
``think`` parameter nor keep the ``thinking`` a model returns: every reasoning model in
Tlamatini's tool loop started each step with NO memory of why it had called the previous
tool.  The vendors document the opposite for tool calling (Z.ai "return the historical
reasoning_content ... to keep the reasoning coherent", OpenAI harmony "pass the previous
chain-of-thought back in", DeepSeek "must be fully passed back", Moonshot "keep all of the
reasoning content", Google Gemma 4 "tool call turns ... thinking content should be
preserved").  Ollama's own API carries it both ways (``message.thinking``).

``BrainChatOllama`` is ``ChatOllama`` plus exactly three things, nothing else changed:
1. the model's ``thinking`` is kept on the returned ``AIMessage`` as
   ``additional_kwargs["reasoning_content"]`` (never in ``content``: the user never sees it);
2. when that message is sent back inside the same tool loop, it carries ``thinking`` again;
3. ``think`` (a level the model publishes) and sampling options ``ChatOllama`` has no field
   for (``presence_penalty`` ...) are sent when the brain chose them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union, cast

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_ollama import ChatOllama
from langchain_ollama.chat_models import (
    _get_tool_calls_from_response,
    _get_usage_metadata_from_generation_info,
)

REASONING_KEY = "reasoning_content"


def client_accepts_think(value: Any) -> bool:
    """Can the INSTALLED ollama client send this ``think`` value?  (0.5.x validates it.)"""
    if value is None or isinstance(value, bool):
        return True
    try:
        import typing
        from ollama._types import ChatRequest
        allowed = set()
        for arg in typing.get_args(ChatRequest.model_fields["think"].annotation):
            allowed.update(a for a in typing.get_args(arg) if isinstance(a, str))
        return str(value) in allowed
    except Exception:  # noqa: BLE001 - unknown client: do not risk a request that fails validation
        return False


def client_option_names() -> set:
    try:
        from ollama._types import Options
        return set(Options.model_fields)
    except Exception:  # noqa: BLE001
        return set()


class BrainChatOllama(ChatOllama):
    """ChatOllama that keeps and returns a reasoning model's thinking, and sends ``think``."""

    think: Optional[Union[bool, str]] = None
    """A thinking level the model publishes (``/api/show``); None = the model's default."""

    keep_reasoning: bool = True
    """Send each step's reasoning back with that step inside the current tool loop."""

    extra_options: Optional[Dict[str, Any]] = None
    """Ollama options ChatOllama has no field for (presence_penalty, frequency_penalty)."""

    # ── what is SENT ────────────────────────────────────────────────────────
    def _chat_params(self, messages: List[BaseMessage], stop: Optional[List[str]] = None,
                     **kwargs: Any) -> Dict[str, Any]:
        params = super()._chat_params(messages, stop, **kwargs)
        extra = {k: v for k, v in (self.extra_options or {}).items() if v is not None}
        if extra:
            from ollama._types import Options
            options = params.get("options")
            merged = options.model_dump(exclude_none=True) if hasattr(options, "model_dump") else dict(options or {})
            known = client_option_names()
            merged.update({k: v for k, v in extra.items() if k in known})
            params["options"] = Options(**merged)
        if self.think is not None and "think" not in params and client_accepts_think(self.think):
            params["think"] = self.think
        return params

    def _convert_messages_to_ollama_messages(self, messages: List[BaseMessage]):
        converted = list(super()._convert_messages_to_ollama_messages(messages))
        if not self.keep_reasoning:
            return converted
        returned, chars = 0, 0
        for source, target in zip(messages, converted):
            if isinstance(source, AIMessage) and isinstance(target, dict):
                reasoning = (source.additional_kwargs or {}).get(REASONING_KEY)
                if isinstance(reasoning, str) and reasoning.strip():
                    target["thinking"] = reasoning
                    returned += 1
                    chars += len(reasoning)
        if returned:
            print("--- [MODEL-BRAIN] %s: returned the reasoning of %d earlier tool step(s) "
                  "(%d chars) inside this tool loop ---" % (self.model, returned, chars))
        return converted

    # ── what is KEPT ────────────────────────────────────────────────────────
    @staticmethod
    def _chunk_from(stream_resp: Any) -> ChatGenerationChunk:
        has_message = "message" in stream_resp
        message = stream_resp["message"] if has_message else {}
        content = message["content"] if has_message and "content" in message else ""
        thinking = message.get("thinking") if has_message else None
        return ChatGenerationChunk(
            message=AIMessageChunk(
                content=content or "",
                additional_kwargs={REASONING_KEY: thinking} if thinking else {},
                usage_metadata=_get_usage_metadata_from_generation_info(stream_resp),
                tool_calls=_get_tool_calls_from_response(stream_resp),
            ),
            generation_info=(dict(stream_resp) if stream_resp.get("done") is True else None),
        )

    def _chat_stream_with_aggregation(self, messages, stop=None, run_manager=None, verbose=False,
                                      **kwargs) -> ChatGenerationChunk:
        final_chunk = None
        for stream_resp in self._create_chat_stream(messages, stop, **kwargs):
            if isinstance(stream_resp, str):
                continue
            chunk = self._chunk_from(stream_resp)
            final_chunk = chunk if final_chunk is None else final_chunk + chunk
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk, verbose=verbose)
        if final_chunk is None:
            raise ValueError("No data received from Ollama stream.")
        return final_chunk

    async def _achat_stream_with_aggregation(self, messages, stop=None, run_manager=None,
                                             verbose=False, **kwargs) -> ChatGenerationChunk:
        final_chunk = None
        async for stream_resp in self._acreate_chat_stream(messages, stop, **kwargs):
            if isinstance(stream_resp, str):
                continue
            chunk = self._chunk_from(stream_resp)
            final_chunk = chunk if final_chunk is None else final_chunk + chunk
            if run_manager:
                await run_manager.on_llm_new_token(chunk.text, chunk=chunk, verbose=verbose)
        if final_chunk is None:
            raise ValueError("No data received from Ollama stream.")
        return final_chunk

    def _result_from(self, final_chunk: ChatGenerationChunk) -> ChatResult:
        message = cast(AIMessageChunk, final_chunk.message)
        additional = dict(message.additional_kwargs or {})
        if not self.keep_reasoning:
            # Kept on the reply ONLY when it is really sent back: the context
            # gauge counts what a message carries, so it must never count
            # reasoning that does not go out.
            additional.pop(REASONING_KEY, None)
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(
                content=final_chunk.text,
                additional_kwargs=additional,
                usage_metadata=message.usage_metadata,
                tool_calls=message.tool_calls,
            ),
            generation_info=final_chunk.generation_info,
        )])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._result_from(self._chat_stream_with_aggregation(
            messages, stop, run_manager, verbose=self.verbose, **kwargs))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._result_from(await self._achat_stream_with_aggregation(
            messages, stop, run_manager, verbose=self.verbose, **kwargs))
