# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""A time limit for the context sidecars' own Ollama calls.

THE BUG THIS EXISTS TO KILL (Angela, 2026-10-05):
-------------------------------------------------
Before the main chain answers, the Files-Search and System-Metrics sidecars
(``chain_files_search_lcel.py`` / ``chain_system_lcel.py``) ask Ollama small
questions of their own: "does this question need a file search?", "plan the
search as JSON". Those calls had NO time limit and wrote NOTHING to
``tlamatini.log`` while they waited. On 2026-10-05 the Files-Search planning
call to ``nemotron-3-ultra:cloud`` took about five minutes (00:06:47 ->
00:11:38). The log sat on "Fetching file search context ..." the whole time,
so Tlamatini looked frozen and looked as if she had never called Ollama.

THE FIX:
--------
* Every sidecar call is bounded by ``context_sidecar_llm_timeout_seconds``
  (``config.json``, default 60 s). An explicit value is obeyed exactly.
* The user's Cancel ends the wait at once (checked every 0.25 s).
* When the limit is hit the sidecar SKIPS its context and SAYS SO in the log;
  the main answer goes ahead without it.
* The sidecar LLMs carry the ``[OLLAMA-TIMING]`` callbacks, so the wait is
  visible in the log like every other Ollama call.

FAIL-OPEN: a bad config value falls back to the default, and a broken cancel
check reads "not cancelled". The only exceptions raised to a caller are the
two named below, and the sidecars catch both.

Stdlib only, and nothing from ``agent.*`` is imported at module level (the
cancel check imports it lazily), so the chains still import when they are
run as scripts.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Callable, Mapping, Optional

CONFIG_KEY = "context_sidecar_llm_timeout_seconds"
DEFAULT_TIMEOUT_SECONDS = 60.0
CANCEL_POLL_SECONDS = 0.25
# The HTTP client gets a slightly longer limit, so the wall-clock limit below
# always fires first and the log names the real cause.
HTTP_BACKSTOP_EXTRA_SECONDS = 5.0
# How long an abandoned call may take to unwind after it is cancelled.
_UNWIND_SECONDS = 2.0


class SidecarLLMTimeout(Exception):
    """Ollama did not answer a sidecar call within the time limit."""


class SidecarLLMCancelled(Exception):
    """The user pressed Cancel while a sidecar call was waiting on Ollama."""


def resolve_timeout(config: Optional[Mapping[str, Any]]) -> float:
    """The sidecar time limit in seconds; the default on any bad value."""
    try:
        raw = (config or {}).get(CONFIG_KEY, DEFAULT_TIMEOUT_SECONDS)
    except AttributeError:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(raw, bool):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return value


def client_kwargs_with_timeout(client_kwargs: Optional[Mapping[str, Any]], timeout: float) -> dict:
    """``client_kwargs`` for ``OllamaLLM`` with an HTTP-level backstop limit.

    A ``timeout`` the caller already set is kept.
    """
    merged = dict(client_kwargs or {})
    merged.setdefault("timeout", float(timeout) + HTTP_BACKSTOP_EXTRA_SECONDS)
    return merged


def make_cancel_check(user_id: Any, run_epoch: Any) -> Callable[[], bool]:
    """A function that says whether THIS request was cancelled by the user."""

    def _cancelled() -> bool:
        try:
            try:
                from .cancellation import is_generation_cancelled
            except ImportError:
                from cancellation import is_generation_cancelled  # script mode
            return bool(is_generation_cancelled(user_id, run_epoch))
        except Exception:  # noqa: BLE001 - never raise into the chat path
            return False

    return _cancelled


def _say(message: str) -> None:
    try:
        print("--- " + message, flush=True)
    except Exception:  # pragma: no cover
        pass


async def ainvoke_with_time_limit(
    runnable: Any,
    inputs: Any,
    *,
    timeout: float,
    label: str,
    model: str = "ollama",
    cancelled: Optional[Callable[[], bool]] = None,
) -> Any:
    """Await ``runnable.ainvoke(inputs)`` for at most ``timeout`` seconds.

    Raises ``SidecarLLMTimeout`` when the limit is reached and
    ``SidecarLLMCancelled`` when ``cancelled()`` turns true. In both cases the
    pending call is cancelled before returning. Any other error from the call
    itself is raised unchanged.
    """
    started = time.monotonic()
    task = asyncio.ensure_future(runnable.ainvoke(inputs))
    try:
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout - elapsed
            if remaining <= 0:
                _say(
                    f"⌛ [CONTEXT-SIDECAR] {label}: Ollama (model={model}) did not answer "
                    f"within {timeout:g}s - skipping this step; the answer goes ahead "
                    f"without it (setting: {CONFIG_KEY})"
                )
                raise SidecarLLMTimeout(f"{label}: no answer from {model} within {timeout:g}s")
            done, _pending = await asyncio.wait({task}, timeout=min(CANCEL_POLL_SECONDS, remaining))
            if task in done:
                return task.result()
            if cancelled is not None and cancelled():
                _say(
                    f"🛑 [CONTEXT-SIDECAR] {label}: cancelled by the user after "
                    f"{time.monotonic() - started:.1f}s - stopped waiting for Ollama"
                )
                raise SidecarLLMCancelled(label)
    finally:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait({task}, timeout=_UNWIND_SECONDS)
            except Exception:  # noqa: BLE001
                pass
        if task.done() and not task.cancelled():
            # Collect the exception so asyncio never reports it as unretrieved.
            task.exception()
