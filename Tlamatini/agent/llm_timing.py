"""Ollama call timing instrumentation.

Logs, into ``tlamatini.log`` with timestamps, the *exact* moment Tlamatini
starts waiting for an answer from Ollama and *exactly how long* Ollama took to
answer — so the elapsed time is clearly attributed to **Ollama (the LLM
backend), not to Tlamatini's own code**.

Output goes through ``print()`` (captured by manage.py's stdout tee into
tlamatini.log) AND the logger, so it is visible regardless of Django's logging
config. Wired in as a LangChain callback attached to every chat-path LLM
instance (rag/factory.py OllamaLLM, mcp_agent.py ChatOllama). Fires on every
``.invoke()`` / ``.stream()`` including via ``bind_tools()``.

Hard contract: pure instrumentation — a callback exception is swallowed so
timing can NEVER break, slow, or alter a real LLM call.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent.ollama_timing")

try:
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:  # pragma: no cover
    try:
        from langchain.callbacks.base import BaseCallbackHandler  # type: ignore
    except Exception:  # pragma: no cover
        class BaseCallbackHandler:  # type: ignore
            """Minimal stand-in when LangChain is unavailable."""


def _emit(msg: str, *, warn: bool = False) -> None:
    """Emit a timing line both to stdout (tee -> tlamatini.log) and the logger."""
    try:
        print("--- " + msg, flush=True)
    except Exception:  # pragma: no cover
        pass
    try:
        (logger.warning if warn else logger.info)(msg)
    except Exception:  # pragma: no cover
        pass


def _now_hms() -> str:
    try:
        return time.strftime("%H:%M:%S")
    except Exception:  # pragma: no cover
        return "??:??:??"


def _model_name(serialized: Any, kwargs: Any) -> str:
    """Best-effort model-name extraction across LangChain versions."""
    try:
        inv = kwargs.get("invocation_params") if isinstance(kwargs, dict) else None
        if isinstance(inv, dict):
            for k in ("model", "model_name", "model_id"):
                v = inv.get(k)
                if v:
                    return str(v)
    except Exception:
        pass
    try:
        if isinstance(serialized, dict):
            kw = serialized.get("kwargs")
            if isinstance(kw, dict):
                for k in ("model", "model_name", "model_id"):
                    v = kw.get(k)
                    if v:
                        return str(v)
            rep = serialized.get("repr") or ""
            if "model=" in rep:
                return rep.split("model=", 1)[1].split()[0].strip("'\" ,)")
    except Exception:
        pass
    return "ollama"


class OllamaTimingCallback(BaseCallbackHandler):
    """Logs WAIT-START (timestamp) and WAIT-END (elapsed seconds) around every
    LLM / chat-model call, so the user sees that a long wait is Ollama
    answering — not Tlamatini working."""

    def __init__(self) -> None:
        self._starts: Dict[Any, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _start(self, run_id: Any, model: str) -> None:
        try:
            with self._lock:
                self._starts[run_id] = {"t": time.monotonic(), "model": model, "ft": None}
            _emit(f"⏳ [OLLAMA-TIMING] WAIT-START model={model} at {_now_hms()} — "
                  f"Tlamatini sent the request and is now BLOCKED waiting for Ollama to answer…")
        except Exception:  # pragma: no cover
            pass

    def _first_token(self, run_id: Any) -> None:
        try:
            with self._lock:
                rec = self._starts.get(run_id)
                if not rec or rec.get("ft") is not None:
                    return
                rec["ft"] = time.monotonic()
                elapsed = rec["ft"] - rec["t"]
                model = rec.get("model", "ollama")
            _emit(f"… [OLLAMA-TIMING] first token after {elapsed:.1f}s "
                  f"(Ollama started answering) model={model}")
        except Exception:  # pragma: no cover
            pass

    def _finish(self, run_id: Any, *, error: Optional[BaseException] = None) -> None:
        try:
            with self._lock:
                rec = self._starts.pop(run_id, None)
            model = rec.get("model") if rec else "ollama"
            elapsed = (time.monotonic() - rec["t"]) if rec else -1.0
            if error is not None:
                _emit(f"❌ [OLLAMA-TIMING] model={model} FAILED after {elapsed:.1f}s "
                      f"(waiting on Ollama): {error}", warn=True)
            else:
                _emit(f"✅ [OLLAMA-TIMING] WAIT-END model={model} at {_now_hms()} — "
                      f"Ollama took {elapsed:.1f}s to answer (that {elapsed:.1f}s was OLLAMA, not Tlamatini)")
        except Exception:  # pragma: no cover
            pass

    # ---- LangChain hooks ----
    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs):
        self._start(run_id, _model_name(serialized, kwargs))

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs):
        self._start(run_id, _model_name(serialized, kwargs))

    def on_llm_new_token(self, token, *, run_id=None, **kwargs):
        self._first_token(run_id)

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        self._finish(run_id)

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        self._finish(run_id, error=error)


OLLAMA_TIMER = OllamaTimingCallback()


def llm_timing_callbacks() -> List[Any]:
    """Return the callback list to pass to an LLM constructor (``callbacks=...``)."""
    return [OLLAMA_TIMER] if OLLAMA_TIMER is not None else []
