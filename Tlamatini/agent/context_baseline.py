"""Tlamatini - the context gauge AT REST.

Angela, 2026-09-28: *"If the history is cleaned ... the gauge must be set to an
initial value.  If the Context is cleared ... the gauge must be recalculated
... consider the history and the very real state of the context's length! ...
find a way to really ask ollama to its API ... make that gauge counter to be
real, NOT FAKE."*

The meter (``context_governor``) measures a request while it is being sent.
Between messages nothing is sent, so the ring used to freeze on whatever the
last request left there - Clear history and Clear context changed nothing on
screen.  This module answers the question *"how big is the request my NEXT
message will send?"* at every point where that answer changes, and it answers
it with Ollama's own number:

1. REBUILD the next request with the live chain's OWN code - the same
   ``build_request_messages`` the executor uses, the same tool selection, the
   same system prompt, the same (possibly summarized) history, the same
   loaded-context wrapper - so the at-rest frame and a live frame cannot drift
   apart.  Only the question is empty.
2. MEASURE it through the meter (``kind="rest"``) - bytes measured, tokens
   estimated, published at once.
3. PROBE Ollama with that exact request (``num_predict=1``, ``stream=False``,
   through ChatOllama's own client: same host, headers, options, tool JSON)
   and attach the ``prompt_eval_count`` it reports.  That is the REAL figure.

Scope - Angela, 2026-09-28: *"JUST THE METERING MUST BE IN THE MODEL OF THE
MAIN CONNECTION CHAIN FROM TLAMATINI ... AND OF COURSE PER CONNECTED USER."*
Only the main chain's request is rebuilt, and every piece of state here is
keyed by the connected user.

CONTRACTS (do NOT weaken):
  * FAIL OPEN.  Nothing here may raise into the consumer; a failed rebuild or
    probe is logged and the ring keeps its last frame.
  * NEVER GUESS SILENTLY.  What the next question adds (its own text, the
    per-question retrieved context, a freshly written history summary, the
    planner hint, web / system / file-search context) cannot be known before
    it is asked; every frame carries a ``note`` naming what is not included.
  * A request in flight OWNS the ring - an at-rest refresh never runs over it.
  * One refresh per user at a time; requests arriving meanwhile coalesce into
    ONE follow-up run (latest wins).
  * The probe is a real Ollama call and costs real tokens.  It is logged with
    its cost, it is skipped when the request is byte-identical to the last one
    probed (the count is then identical), and it can be switched off.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import context_governor as cg

__all__ = [
    "RefreshFlags",
    "refresh",
    "schedule_refresh",
    "probe_settings",
]


class RefreshFlags:
    """The toolbar switches that change which request the next message sends."""

    __slots__ = ("multi_turn", "acpx", "step_by_step")

    def __init__(self, multi_turn: bool = False, acpx: bool = False,
                 step_by_step: bool = False) -> None:
        self.multi_turn = bool(multi_turn)
        self.acpx = bool(acpx)
        self.step_by_step = bool(step_by_step)

    def as_dict(self) -> Dict[str, bool]:
        return {"multi_turn": self.multi_turn, "acpx": self.acpx,
                "step_by_step": self.step_by_step}


# ── Settings ──────────────────────────────────────────────────────────────────
DEFAULT_PROBE_ENABLED = True
DEFAULT_PROBE_AFTER_ANSWER = True


def probe_settings(config: Any) -> Dict[str, bool]:
    """``{"enabled", "after_answer"}`` from config.json.  Never raises.

    The probe uses ChatOllama's own client, so it inherits the chat's own
    ``llm_client_timeout_seconds`` - there is deliberately no second timeout.
    """
    cfg = config if isinstance(config, dict) else {}

    def _flag(key: str, default: bool) -> bool:
        value = cfg.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value) if isinstance(value, (int, float)) else default

    return {
        "enabled": _flag("context_gauge_probe_enable", DEFAULT_PROBE_ENABLED),
        "after_answer": _flag("context_gauge_probe_after_answer", DEFAULT_PROBE_AFTER_ANSWER),
    }


def _load_config() -> Dict[str, Any]:
    try:
        from .config_loader import load_config
        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ── Per-user scheduling: one run at a time, latest wins ──────────────────────
_LOCK = threading.Lock()
_RUNNING: Dict[Any, bool] = {}
_PENDING: Dict[Any, Tuple[Any, list, RefreshFlags, str, Optional[bool]]] = {}
_LAST_PROBE: Dict[Any, Tuple[str, int, Optional[int], str]] = {}


def _request_in_flight(user_id: Any) -> bool:
    turn = cg.turn_totals(user_id)
    return bool(turn and turn.get("open"))


def schedule_refresh(user_id: Any, rag_chain: Any, history: list,
                     flags: RefreshFlags, reason: str,
                     probe: Optional[bool] = None) -> bool:
    """Run :func:`refresh` on a daemon thread; coalesce per user.  Never raises.

    ``probe=None`` follows ``context_gauge_probe_enable``; ``False`` measures
    without asking Ollama.  Returns True when a run was started or queued.
    """
    try:
        if user_id is None or rag_chain is None:
            return False
        with _LOCK:
            if _RUNNING.get(user_id):
                _PENDING[user_id] = (rag_chain, list(history or []), flags, reason, probe)
                return True
            _RUNNING[user_id] = True

        def _worker(args: Tuple[Any, list, RefreshFlags, str, Optional[bool]]) -> None:
            while True:
                chain, hist, flg, why, want_probe = args
                try:
                    refresh(user_id, chain, hist, flg, why, probe=want_probe)
                except Exception as exc:  # noqa: BLE001 - never kill the worker
                    print(f"--- [CONTEXT-REST] refresh failed ({type(exc).__name__}: {exc})")
                with _LOCK:
                    nxt = _PENDING.pop(user_id, None)
                    if nxt is None:
                        _RUNNING[user_id] = False
                        return
                args = nxt

        threading.Thread(
            target=_worker,
            args=((rag_chain, list(history or []), flags, reason, probe),),
            name=f"tlamatini-context-rest-{user_id}",
            daemon=True,
        ).start()
        return True
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            _RUNNING[user_id] = False
        print(f"--- [CONTEXT-REST] could not schedule a refresh ({exc})")
        return False


# ── Rebuilding the next request with the chain's own code ───────────────────
def _next_request(rag_chain: Any, history: list, flags: RefreshFlags,
                  user_id: Any = None) -> Optional[Dict[str, Any]]:
    """Everything the NEXT message's first model step would send, minus the
    question text.  ``None`` when the main chain cannot be rebuilt."""
    cae = getattr(rag_chain, "unified_agent", None)
    if cae is None or not hasattr(cae, "_get_executor_for_tools"):
        print("--- [CONTEXT-REST] the main chain is not the unified agent - the "
              "at-rest rebuild covers the unified agent only; live requests are "
              "still metered")
        return None

    from .acpx import filter_acpx_tools
    from .mcp_agent import _budget_select_tools, _emergency_core_tools
    from .rag.chains.unified import (
        history_summary_tail,
        summarized_history,
        wrap_loaded_context,
    )

    notes: List[str] = ["the next question's own text"]

    # 1. History exactly as the chain would send it.
    hist = list(history or [])
    tail = history_summary_tail(getattr(rag_chain, "history_summary_cfg", None), hist)
    if tail is not None:
        summary = str(getattr(rag_chain, "last_history_summary", "") or "")
        hist = summarized_history(summary, tail)
        notes.append("the history summary written for that question "
                     + ("(the last one is used here)" if summary else "(none written yet)"))

    # 2. The input: the chain's own wrapper around an EMPTY question.  System
    #    metrics join a question only when that question needs them - the
    #    sidecar sends NOTHING otherwise (no placeholder since 2026-09-28) - so
    #    one-shot and Multi-Turn wrap an empty question identically.
    input_text = ""
    loaded_context = str(getattr(rag_chain, "loaded_context", "") or "")
    if loaded_context:
        input_text = wrap_loaded_context(loaded_context, input_text)
    elif hasattr(rag_chain, "vector_store"):
        # A loaded directory / file is SEARCHED for every question, so which
        # context bytes the next request carries depends on that question -
        # it cannot be known now, and it is never guessed.
        last = int(getattr(rag_chain, "last_retrieved_context_chars", 0) or 0)
        budget = 0
        try:
            budget = int((getattr(rag_chain, "compression_cfg", None) or {})
                         .get("max_context_chars", 24000))
        except (TypeError, ValueError):
            budget = 0
        detail = []
        if budget:
            detail.append(f"up to {budget:,} chars")
        if last:
            detail.append(f"the last question retrieved {last:,}")
        notes.append("the context retrieved for that question"
                     + (f" ({'; '.join(detail)})" if detail else ""))

    # 3. The tool surface AND the fit (full / compact) - the SAME
    #    ``fit_request`` CapabilityAwareToolAgentExecutor.invoke uses
    #    (2026-10-01), so the ring and the Compact-mode dialog show the
    #    request that will really be sent.  A compact request never refreshes
    #    the External-MCP surface (those servers are paused for it).
    if hasattr(cae, "fit_request"):
        def _fit(publish: bool) -> Dict[str, Any]:
            return cae.fit_request(
                input_text=input_text, chat_history=hist,
                request_tools=filter_acpx_tools(cae.tools, flags.acpx),
                multi_turn=flags.multi_turn, step_by_step=flags.step_by_step,
                acpx_requested=flags.acpx, user_id=user_id, publish=publish,
            )
        fit = _fit(publish=False)
        if fit.get("mode") != "compact":
            try:
                cae._refresh_external_mcp_tool_surface()
            except Exception:  # noqa: BLE001
                pass
            fit = _fit(publish=True)
        else:
            cae._publish_fit(fit.get("report"), user_id)
        executor = fit["executor"]
        selected = list(fit.get("tools") or [])
        input_text = fit.get("input", input_text)
        hist = list(fit.get("history") or [])
        dropped = int(fit.get("dropped") or 0)
        if fit.get("mode") == "compact":
            report = fit.get("report")
            notes.append("COMPACT mode: this model is too small for the complete request"
                         + (f" ({report.window_tokens:,}-token window)" if report else ""))
        elif flags.multi_turn:
            if dropped:
                notes.append(f"which tools that question keeps ({len(selected)} of "
                             f"{len(selected) + dropped} kept at rest)")
            notes.append("the planner hint")
    else:
        try:
            cae._refresh_external_mcp_tool_surface()
        except Exception:  # noqa: BLE001
            pass
        request_tools = filter_acpx_tools(cae.tools, flags.acpx)
        if flags.multi_turn:
            selected, _tool_tokens, dropped = _budget_select_tools(
                request_tools,
                system_prompt_text=cae.preeliminary_prompt,
                input_text=input_text,
                chat_history=hist,
                global_execution_plan=None,
            )
            if request_tools and not selected:
                selected = _emergency_core_tools(request_tools)
                dropped = len(request_tools) - len(selected)
            if dropped:
                notes.append(f"which tools that question keeps ({len(selected)} of "
                             f"{len(request_tools)} kept at rest)")
            notes.append("the planner hint")
        else:
            selected = request_tools
        executor = cae._get_executor_for_tools(selected, step_by_step_enabled=flags.step_by_step)

    # 4. The messages - the executor's OWN builder.
    messages, prefix_count = executor.build_request_messages(input_text, hist)
    notes.append("web / system / file-search context, if that question needs it")
    return {
        "executor": executor,
        "messages": messages,
        "prefix_count": prefix_count,
        "tools": len(selected),
        "notes": notes,
    }


def _wire_params(executor: Any, messages: list) -> Tuple[Any, Dict[str, Any]]:
    """ChatOllama's own request body for ``messages`` (tools included)."""
    llm = getattr(executor, "bound_llm", None) or getattr(executor, "llm", None)
    chat = getattr(llm, "bound", None) or llm
    kwargs = getattr(llm, "kwargs", None) or {}
    tools_json = kwargs.get("tools") if isinstance(kwargs, dict) else None
    if tools_json:
        return chat, chat._chat_params(messages, tools=tools_json)
    return chat, chat._chat_params(messages)


def _probe_key(params: Dict[str, Any]) -> str:
    body = dict(params)
    body.pop("stream", None)
    try:
        opts = dict(body.get("options") or {})
    except Exception:  # noqa: BLE001
        opts = {}
    opts.pop("num_predict", None)
    body["options"] = {k: v for k, v in opts.items() if v is not None}
    try:
        body["messages"] = [dict(m) if not isinstance(m, dict) else m
                            for m in body.get("messages") or []]
    except Exception:  # noqa: BLE001
        pass
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _probe(chat: Any, params: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], float]:
    """Send the exact request with ONE output token; return Ollama's counts."""
    body = dict(params)
    try:
        opts = dict(body.get("options") or {})
    except Exception:  # noqa: BLE001
        opts = {}
    opts["num_predict"] = 1
    body["options"] = opts
    body["stream"] = False
    started = time.perf_counter()
    resp = chat._client.chat(**body)
    seconds = time.perf_counter() - started

    def _get(key: str) -> Any:
        if hasattr(resp, "get"):
            try:
                return resp.get(key)
            except Exception:  # noqa: BLE001
                pass
        return getattr(resp, key, None)

    prompt = _get("prompt_eval_count")
    completion = _get("eval_count")
    return (int(prompt) if prompt is not None else None,
            int(completion) if completion is not None else None,
            seconds)


def refresh(user_id: Any, rag_chain: Any, history: list, flags: RefreshFlags,
            reason: str, *, probe: Optional[bool] = None,
            _refit: bool = False) -> Optional[Dict[str, Any]]:
    """Rebuild, measure and (optionally) probe the next request for ``user_id``.

    Returns a small summary dict (for tests and the lab), or None when nothing
    was published.  Never raises.
    """
    try:
        if _request_in_flight(user_id):
            print(f"--- [CONTEXT-REST] skipped ({reason}): a request is in flight "
                  "and owns the gauge")
            return None
        config = _load_config()
        settings = cg.resolve_settings(config)
        if not settings.enabled or not settings.gauge_enabled:
            return None
        built = _next_request(rag_chain, history, flags, user_id)
        if built is None:
            return None
        executor = built["executor"]
        messages = built["messages"]
        schema_bytes, schema_chars = executor._tool_schema_prefix_bytes()
        model, base_url = executor._llm_identity(
            getattr(executor, "bound_llm", None) or executor.llm
        )
        note = "not included yet: " + "; ".join(built["notes"])
        seq = cg.next_seq()
        cg.measure_async(
            user_id,
            messages,
            label=f"next message · at rest ({reason})",
            source="multi-turn" if flags.multi_turn else "one-shot",
            loop_start_index=len(messages),
            prefix_message_count=built["prefix_count"],
            extra_prefix_bytes=schema_bytes,
            extra_prefix_chars=schema_chars,
            config=config,
            settings=settings,
            seq=seq,
            model=model,
            base_url=base_url,
            kind=cg.KIND_REST,
            note=note,
        )
        summary: Dict[str, Any] = {
            "seq": seq, "reason": reason, "messages": len(messages),
            "tools": built["tools"], "model": model, "flags": flags.as_dict(),
            "prompt_tokens": None, "probed": False, "cached": False,
        }

        want_probe = probe_settings(config)["enabled"] if probe is None else bool(probe)
        if not want_probe or not settings.real_tokens:
            print(f"--- [CONTEXT-REST] ({reason}) measured {len(messages)} message(s), "
                  f"{built['tools']} tool(s); Ollama probe OFF - estimate only")
            return summary

        chat, params = _wire_params(executor, messages)
        key = _probe_key(params)
        with _LOCK:
            last = _LAST_PROBE.get(user_id)
        if last is not None and last[0] == key:
            _, prompt, completion, last_model = last
            print(f"--- [CONTEXT-PROBE] ({reason}) request is byte-identical to the one "
                  f"already probed - reusing Ollama's count {prompt} (no new call)")
            cg.report_real_usage(user_id, seq, prompt, completion,
                                 model=last_model or model,
                                 label="next message · at rest",
                                 field_name="prompt_eval_count (probe, identical request)",
                                 config=config)
            summary.update(prompt_tokens=prompt, probed=True, cached=True)
            return summary

        if _request_in_flight(user_id):
            print(f"--- [CONTEXT-PROBE] ({reason}) skipped: a request started meanwhile")
            return summary
        prompt, completion, seconds = _probe(chat, params)
        if prompt is None:
            print(f"--- [CONTEXT-PROBE] ({reason}) Ollama returned no prompt_eval_count "
                  "- the frame stays an ESTIMATE")
            return summary
        with _LOCK:
            _LAST_PROBE[user_id] = (key, prompt, completion, model)
        print(f"--- [CONTEXT-PROBE] ({reason}) {model}: prompt_eval_count={prompt} "
              f"eval_count={completion} in {seconds:.2f} s - this probe cost "
              f"{prompt} prompt + {completion or 0} output tokens")
        cg.report_real_usage(user_id, seq, prompt, completion, model=model,
                             label="next message · at rest",
                             field_name="prompt_eval_count (probe, num_predict=1)",
                             config=config)
        summary.update(prompt_tokens=prompt, probed=True, seconds=round(seconds, 3))
        # 2026-10-01: did Ollama CUT this request?  Then its count IS the
        # model's real window - learn it and rebuild the next request ONCE,
        # fitted to that window, so the ring and the Compact-mode dialog are
        # right BEFORE the user's first question (not after it fails).
        try:
            from .context_fitter import message_chars
            chars = message_chars(messages) + int(schema_chars or 0)
            verdict = cg.note_real_count(model, base_url, prompt, chars,
                                         source=f"at-rest probe ({reason})")
            if verdict.get("truncated") and not _refit:
                summary["truncated"] = True
                print(f"--- [CONTEXT-PROBE] ({reason}) Ollama cut the probed request at "
                      f"{verdict.get('window')} tokens - re-fitting the next request")
                with _LOCK:
                    _LAST_PROBE.pop(user_id, None)
                refit = refresh(user_id, rag_chain, history, flags, f"{reason}, re-fitted",
                                probe=probe, _refit=True)
                if refit is not None:
                    summary["refit"] = refit
        except Exception as cut_err:  # noqa: BLE001
            print(f"--- [CONTEXT-PROBE] cut check skipped ({cut_err})")
        return summary
    except Exception as exc:  # noqa: BLE001 - the gauge owes the chat nothing
        print(f"--- [CONTEXT-REST] ({reason}) failed open: {type(exc).__name__}: {exc}")
        return None


def forget_user(user_id: Any) -> None:
    """Drop this user's probe cache (e.g. on disconnect).  Never raises."""
    try:
        with _LOCK:
            _LAST_PROBE.pop(user_id, None)
            _PENDING.pop(user_id, None)
    except Exception:  # noqa: BLE001
        pass
