"""Tlamatini - the CONTEXT GOVERNOR.  **STEP 1: MEASUREMENT ONLY.**

Three streams feed one model request: the static prefix (system prompt + the
bound tool schemas + RAG context), the chat history, and the Multi-Turn tool
loop.  The first two already have a brake.  The third - the one that actually
explodes - has none: every tool call and every FULL tool result is appended and
re-sent on every turn that follows it, up to 4096 turns.

This module is the first slice of the design (``ContextGovernor-design.html``,
Part II step 1 + Part IV): it **measures** what is about to be sent, prints one
grep-able ``--- [CONTEXT]`` line per model step, and publishes a payload for
the gauge in the chat window.

**IT FOLDS NOTHING.**  It does not read, reorder, shorten or drop a single
message.  ``measure()`` takes the list and returns numbers; the caller's list
is never touched.  That is deliberate: this slice cannot change an answer, so
it can be left running for a normal day of use and the watermarks below can
then be set from real numbers instead of guesses.  Steps 2-10 (the folding
ladder) are NOT implemented here.

Contracts (from Part V - do NOT weaken):

* **FAIL OPEN.**  Any error, any malformed message, any doubt about shape:
  return a measurement that says "unknown" and carry on.  Nothing in this
  module may raise into a caller.  A governor that breaks the chat is worse
  than the overflow it prevents.
* **Bytes are MEASURED, tokens are ESTIMATED**, and every surface says which
  is which.  ``total_bytes`` is ``len(text.encode('utf-8'))`` - the literal
  size of what goes on the wire.  ``tokens_estimated`` is a division.  Never
  present the estimate as the measurement.
* **REAL tokens come only from Ollama itself** (2026-09-28).  When the main
  chain's request is answered, Ollama's own ``prompt_eval_count`` replaces the
  estimate on that request's frame (``ratio_is_real``), and the model's own
  context length from ``/api/show`` becomes the denominator.  Only Tlamatini's
  MAIN inference is shown; side calls never reach the ring.  Everything is
  kept per connected user.  See the REAL TOKENS section at the end.
* **On doubt about the ceiling, assume the LARGER budget.**  Under-reporting
  pressure is safe today (nothing folds); over-reporting it would train the
  watermarks wrong.
* **The gauge never slows a turn.**  ``publish_gauge`` is fire-and-forget and
  swallows every failure; the chat path owes the gauge nothing.
* **One definition of the budget.**  This module is the only place the
  watermarks, the zones and the byte arithmetic live.  Do not grow a second
  copy - the ``tlamatini_acpx.py`` drift is the known failure mode here.

Standard library ONLY, and it imports nothing from ``agent.*`` - the same
discipline as ``agent_verdict.py``, ``binary_guard.py`` and ``child_health.py``
- so it behaves identically frozen and from source and can never create an
import cycle.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

__all__ = [
    "GovernorSettings",
    "Measurement",
    "resolve_settings",
    "measure",
    "zone_for",
    "format_log_line",
    "gauge_payload",
    "humanize_bytes",
    "register_gauge_sink",
    "unregister_gauge_sink",
    "publish_gauge",
    "resolve_ceiling_tokens",
    # The meter - EVERY model call site reports through measure_async().
    "ContextMeter",
    "MeterSample",
    "METER",
    "measure_async",
    # REAL tokens - Ollama's own counts (2026-09-28).
    "next_seq",
    "report_real_usage",
    "record_call_usage",
    "begin_turn",
    "end_turn",
    "turn_totals",
    "ollama_context_length",
    "is_cloud_model",
    "apply_real_tokens",
    "usage_from_llm_result",
    "note_run_seq",
    "report_run_usage",
    "latest_frame",
    "KIND_LIVE",
    "KIND_REST",
    "KIND_SIDE",
    "CONTEXT_BLOCKS",
    # The EFFECTIVE window + model capacity (2026-10-01).
    "window_key",
    "learned_window",
    "learned_window_info",
    "measured_chars_per_token",
    "fit_chars_per_token",
    "forget_learned_windows",
    "note_real_count",
    "set_capacity",
    "capacity_for",
    "publish_capacity",
]


# ── Defaults ────────────────────────────────────────────────────────────────
# These ship in config.json too; the literals here are the fallback a missing
# or malformed key resolves to, so a config typo can never stop a request.
DEFAULT_ENABLED = True
DEFAULT_CEILING_TOKENS = 0          # 0 = resolve from the backend
DEFAULT_WATERMARK_COMPACT = 0.60
DEFAULT_WATERMARK_FOLD = 0.75
DEFAULT_WATERMARK_FLOOR = 0.85
DEFAULT_GAUGE_ENABLED = True
DEFAULT_GAUGE_HISTORY_TURNS = 12
DEFAULT_LOG_EACH = True
# Ask Ollama's own /api/show for the model's context length (the REAL
# denominator) instead of trusting a config number.  Cached; worker-thread only.
DEFAULT_CEILING_FROM_BACKEND = True
# Replace the estimate with Ollama's own prompt_eval_count whenever the server
# reports it (every /api/chat and /api/generate response does).
DEFAULT_REAL_TOKENS = True
DEFAULT_SHOW_TIMEOUT_SECONDS = 4.0

# The ceiling used when nothing else answers.  Deliberately LARGE: "on doubt,
# fold less, never more".  It matches the shipped ``ollama_num_ctx`` and the
# limit glm-5.3 names in its own HTTP 400 ("model maximum context length:
# 1048576"), so an unknown backend is assumed to be at least as generous.
FALLBACK_CEILING_TOKENS = 1_048_576

# 1 token ~ 4 characters.  A tokenizer round-trip is an HTTP call on every
# turn, which this module refuses to spend.  Kept a module constant rather
# than a config key on purpose: it is the definition of the estimate, not a
# preference, and every surface that shows it also labels it "est.".
CHARS_PER_TOKEN = 4.0

# Where the user's loaded / retrieved PROJECT CONTEXT sits inside a request.
# Each pair is (opening text, closing text) written by the chain that builds
# the request.  ``rag/chains/unified.py`` IMPORTS these constants to build its
# preambles, so the text that is sent and the text that is measured are one
# definition and cannot drift apart.  The third pair is prompt.pmt's own
# ``<context>`` block (the one-shot chains put the context in the system
# prompt).  Anything between an opening and its closing text is the context.
CONTEXT_FALLBACK_OPEN = "Loaded Context from Knowledge Base Fallback:\n"
CONTEXT_FALLBACK_CLOSE = "\n\nIMPORTANT: The loaded context above"
CONTEXT_RETRIEVED_OPEN = "Retrieved Context from Knowledge Base:\n"
CONTEXT_RETRIEVED_CLOSE = "\n\nUser Question: "
CONTEXT_BLOCKS: Tuple[Tuple[str, str], ...] = (
    (CONTEXT_FALLBACK_OPEN, CONTEXT_FALLBACK_CLOSE),
    (CONTEXT_RETRIEVED_OPEN, CONTEXT_RETRIEVED_CLOSE),
    ("\n<context>\n", "\n</context>"),
)

# What a frame describes.  LIVE = the main chain's request being sent right
# now.  REST = the request the NEXT message would send, measured while idle
# (after Clear history, Clear context, a context load, a reconnect...).
# SIDE = anything that is NOT Tlamatini's main inference: logged, never shown.
KIND_LIVE = "live"
KIND_REST = "rest"
KIND_SIDE = "side"

ZONE_GREEN = "green"
ZONE_AMBER = "amber"
ZONE_RED = "red"
ZONE_FLOOR = "floor"


@dataclass(frozen=True)
class GovernorSettings:
    """Resolved, already-validated knobs.  Built by :func:`resolve_settings`."""

    enabled: bool = DEFAULT_ENABLED
    ceiling_tokens: int = DEFAULT_CEILING_TOKENS
    watermark_compact: float = DEFAULT_WATERMARK_COMPACT
    watermark_fold: float = DEFAULT_WATERMARK_FOLD
    watermark_floor: float = DEFAULT_WATERMARK_FLOOR
    gauge_enabled: bool = DEFAULT_GAUGE_ENABLED
    gauge_history_turns: int = DEFAULT_GAUGE_HISTORY_TURNS
    log_each: bool = DEFAULT_LOG_EACH
    # 2026-09-28 - the REAL numbers.  Both default ON; both fail open.
    ceiling_from_backend: bool = DEFAULT_CEILING_FROM_BACKEND
    real_tokens: bool = DEFAULT_REAL_TOKENS
    show_timeout_seconds: float = DEFAULT_SHOW_TIMEOUT_SECONDS


@dataclass(frozen=True)
class Measurement:
    """What one model step is about to send.

    ``*_bytes`` are measured.  ``tokens_estimated`` and everything derived from
    it (``ratio``, ``zone``) are ESTIMATES, because the ceiling is expressed in
    tokens and we refuse to pay for a tokenizer round-trip per turn.
    """

    prefix_bytes: int = 0
    history_bytes: int = 0
    loop_bytes: int = 0
    total_bytes: int = 0
    total_chars: int = 0
    tokens_estimated: int = 0
    ceiling_tokens: int = FALLBACK_CEILING_TOKENS
    ceiling_source: str = "fallback"
    ratio: float = 0.0
    zone: str = ZONE_GREEN
    messages_count: int = 0
    loop_messages: int = 0
    ok: bool = True
    # The loaded / retrieved project context INSIDE the request, located by
    # the chain's own fixed markers (see CONTEXT_BLOCKS).  Measured, not
    # guessed: 0 means "no context block is in this request".
    context_bytes: int = 0
    context_chars: int = 0
    model: str = ""
    # The prefix messages AFTER the system prompt - in practice the Multi-Turn
    # planner's per-question plan.  Part of prefix_bytes, broken out so the
    # difference between the at-rest prediction and the live request can be
    # accounted for byte by byte (the plan cannot exist before its question).
    plan_bytes: int = 0


# ── Settings ────────────────────────────────────────────────────────────────
def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off"}:
            return False
    return default


def _as_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        if isinstance(value, bool) or value is None:
            return default
        out = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return out if out >= minimum else default


def _as_ratio(value: Any, default: float) -> float:
    """A watermark must land in (0, 1]; anything else falls back."""
    try:
        if isinstance(value, bool) or value is None:
            return default
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return out if 0.0 < out <= 1.0 else default


def resolve_settings(config: Any) -> GovernorSettings:
    """Read the governor's knobs out of ``config.json``.  Never raises."""
    try:
        cfg: Dict[str, Any] = config if isinstance(config, dict) else {}
        compact = _as_ratio(cfg.get("context_watermark_compact"), DEFAULT_WATERMARK_COMPACT)
        fold = _as_ratio(cfg.get("context_watermark_fold"), DEFAULT_WATERMARK_FOLD)
        floor = _as_ratio(cfg.get("context_watermark_floor"), DEFAULT_WATERMARK_FLOOR)
        # Out-of-order watermarks would make the zones meaningless.  Rather
        # than "correcting" the user's intent, fall back to the shipped set.
        if not (compact <= fold <= floor):
            compact, fold, floor = (
                DEFAULT_WATERMARK_COMPACT,
                DEFAULT_WATERMARK_FOLD,
                DEFAULT_WATERMARK_FLOOR,
            )
        return GovernorSettings(
            enabled=_as_bool(cfg.get("context_governor_enable"), DEFAULT_ENABLED),
            ceiling_tokens=_as_int(cfg.get("context_ceiling_tokens"), DEFAULT_CEILING_TOKENS),
            watermark_compact=compact,
            watermark_fold=fold,
            watermark_floor=floor,
            gauge_enabled=_as_bool(cfg.get("context_gauge_enable"), DEFAULT_GAUGE_ENABLED),
            gauge_history_turns=_as_int(
                cfg.get("context_gauge_history_turns"), DEFAULT_GAUGE_HISTORY_TURNS, minimum=1
            ),
            log_each=_as_bool(cfg.get("context_governor_log_each_fold"), DEFAULT_LOG_EACH),
            ceiling_from_backend=_as_bool(
                cfg.get("context_ceiling_from_ollama"), DEFAULT_CEILING_FROM_BACKEND
            ),
            real_tokens=_as_bool(cfg.get("context_gauge_real_tokens"), DEFAULT_REAL_TOKENS),
            show_timeout_seconds=float(_as_int(
                cfg.get("context_ollama_show_timeout_seconds"),
                int(DEFAULT_SHOW_TIMEOUT_SECONDS), minimum=1,
            )),
        )
    except Exception:  # noqa: BLE001 - settings must never break a request
        return GovernorSettings()


# ── The ceiling (the denominator) ───────────────────────────────────────────
def resolve_ceiling_tokens(
    config: Any,
    settings: Optional[GovernorSettings] = None,
    *,
    model: str = "",
    base_url: str = "",
) -> Tuple[int, str]:
    """Return ``(ceiling_tokens, source)``.

    Order:

    1. An explicit ``context_ceiling_tokens`` wins - the operator said so.
    2. **When the model is known, ask Ollama itself** (``POST /api/show`` ->
       ``model_info["<arch>.context_length"]``).  For a ``:cloud`` model that
       IS the limit - ``num_ctx`` is a proven no-op there (a 263,159-token
       prompt sent with ``num_ctx=8192`` was answered in full).  For a LOCAL
       model the KV cache is sized by ``num_ctx`` at load, so the real limit is
       the SMALLER of the two.  Cached per (server, model); never called on a
       request thread - only the meter's worker and the at-rest probe get here.
    3. ``ollama_num_ctx`` (real for a local model, meaningless for cloud - and
       labelled so when the model is known to be cloud).
    4. The large fallback.

    "75% full" means nothing until we know 75% of WHAT; a wrong denominator
    mis-scales every number on the gauge.  Called without ``model`` this
    behaves exactly as it always did - no network, ever.
    """
    try:
        cfg: Dict[str, Any] = config if isinstance(config, dict) else {}
        s = settings or resolve_settings(cfg)
        if s.ceiling_tokens > 0:
            return s.ceiling_tokens, "config"
        num_ctx = _as_int(cfg.get("ollama_num_ctx"), 0, minimum=1)
        name = str(model or "").strip()
        if name:
            # 2026-10-01: a window Ollama PROVED by cutting a larger request
            # outranks every declared number - /api/show cannot see a server
            # that splits its cache into parallel slots.
            learned = learned_window(name, str(base_url or cfg.get("ollama_base_url") or ""))
            if learned:
                return learned, "learned: Ollama read only %d tokens of a larger request" % learned
        if name and s.ceiling_from_backend:
            base = str(base_url or cfg.get("ollama_base_url") or "").strip()
            info = _ollama_show_info(
                name, base, token=str(cfg.get("ollama_token") or ""),
                timeout=s.show_timeout_seconds,
            )
            ctx_len = int(info.get("context_length") or 0)
            if ctx_len > 0:
                if is_cloud_model(name, info):
                    return ctx_len, "ollama /api/show"
                if 0 < num_ctx < ctx_len:
                    return num_ctx, "ollama_num_ctx (< /api/show %d)" % ctx_len
                return ctx_len, "ollama /api/show"
        if num_ctx > 0:
            if name and is_cloud_model(name):
                # Honest label: for a cloud model this number was NOT
                # confirmed by the server and num_ctx does not bind it.
                return num_ctx, "ollama_num_ctx (unverified: cloud ignores num_ctx)"
            return num_ctx, "ollama_num_ctx"
    except Exception:  # noqa: BLE001
        pass
    return FALLBACK_CEILING_TOKENS, "fallback"


def zone_for(ratio: float, settings: Optional[GovernorSettings] = None) -> str:
    """Map a fill ratio onto the four zones the engine and the GUI share."""
    try:
        s = settings or GovernorSettings()
        if ratio >= s.watermark_floor:
            return ZONE_FLOOR
        if ratio >= s.watermark_fold:
            return ZONE_RED
        if ratio >= s.watermark_compact:
            return ZONE_AMBER
    except Exception:  # noqa: BLE001
        return ZONE_GREEN
    return ZONE_GREEN


# ── Measuring ───────────────────────────────────────────────────────────────
def _message_text(message: Any) -> str:
    """Best-effort CONTENT text of ONE message, without importing langchain.

    Content may be a plain string, a list of content blocks, or a dict.  This
    returns the content ONLY - tool calls and the JSON envelope are handled by
    :func:`_message_wire`, because they are part of the WIRE size but not of
    the text the model tokenizes.  Anything unrecognised contributes its
    ``str()`` - never zero, because silently under-counting is the failure this
    module exists to stop.
    """
    if message is None:
        return ""
    try:
        parts = []
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, (list, tuple)):
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(str(block.get("text") or json.dumps(block, default=str)))
                else:
                    parts.append(str(block))
        elif content is not None:
            parts.append(str(content))

        if not parts and not isinstance(message, dict):
            return str(message)
        return "".join(parts)
    except Exception:  # noqa: BLE001
        try:
            return str(message)
        except Exception:  # noqa: BLE001
            return ""


_ROLE_BY_TYPE = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
    "function": "tool",
}


def _message_wire(message: Any) -> Tuple[int, int]:
    """Return ``(wire_bytes, prompt_chars)`` for ONE message.

    **These are two different questions and they get two different numbers.**

    ``wire_bytes`` is the length of the JSON object the server actually
    receives: the envelope, the keys, the tool-call block — and the
    **escaping**.  That escaping is not a rounding error.  Every newline costs
    two bytes as ``\\n`` and every quote and backslash doubles, so on the
    content Tlamatini really sends — source code, logs, exec-report HTML — the
    JSON form measures **~10 % larger** than the raw text (measured
    2026-09-20).  Counting the raw text and calling it "the wire" under-reports
    every single request, which is exactly the plausible-but-wrong failure this
    module exists to prevent.

    ``prompt_chars`` is the RAW content, because Ollama parses the JSON away
    before the tokenizer ever sees it: a ``\\n`` on the wire is ONE newline to
    the model.  Estimating tokens from the escaped form would inflate the
    percentage by the same ~10 %.

    Never raises.
    """
    if message is None:
        return 0, 0
    try:
        text = _message_text(message)

        role = getattr(message, "type", None)
        if role is None and isinstance(message, dict):
            role = message.get("role") or message.get("type")
        role_key = str(role or "").lower()
        payload: Dict[str, Any] = {
            "role": _ROLE_BY_TYPE.get(role_key, role_key or "user"),
            "content": text,
        }

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls is None and isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        chars = len(text)
        if tool_calls:
            payload["tool_calls"] = tool_calls
            # A tool CALL is prompt text to the model as well as wire bytes.
            try:
                chars += len(json.dumps(tool_calls, default=str))
            except Exception:  # noqa: BLE001
                chars += len(str(tool_calls))

        for key in ("tool_call_id", "name"):
            value = getattr(message, key, None)
            if value is None and isinstance(message, dict):
                value = message.get(key)
            if value:
                payload[key] = value

        wire = json.dumps(payload, ensure_ascii=False, default=str)
        return len(wire.encode("utf-8")), chars
    except Exception:  # noqa: BLE001 - fall back to the raw text, never raise
        try:
            fallback = _message_text(message)
            return len(fallback.encode("utf-8")), len(fallback)
        except Exception:  # noqa: BLE001
            return 0, 0


def _context_span(text: str) -> Tuple[int, int]:
    """``(chars, utf8_bytes)`` of the project-context blocks inside ``text``.

    Finds every CONTEXT_BLOCKS opening and the FIRST matching close after it.
    Raw text (what the model reads), not the JSON-escaped wire form.  Never
    raises; no block -> ``(0, 0)``.
    """
    chars = 0
    size = 0
    try:
        if not text:
            return 0, 0
        for opener, closer in CONTEXT_BLOCKS:
            start = text.find(opener)
            while start >= 0:
                body_start = start + len(opener)
                end = text.find(closer, body_start)
                if end < 0:
                    break
                body = text[body_start:end]
                chars += len(body)
                size += len(body.encode("utf-8"))
                start = text.find(opener, end + len(closer))
    except Exception:  # noqa: BLE001
        return 0, 0
    return chars, size


def _bucket(messages: Iterable[Any]) -> Tuple[int, int, int]:
    """Return ``(wire_bytes, prompt_chars, count)`` for a slice of the list."""
    total_bytes = 0
    total_chars = 0
    count = 0
    for message in messages:
        wire_bytes, prompt_chars = _message_wire(message)
        total_bytes += wire_bytes
        total_chars += prompt_chars
        count += 1
    return total_bytes, total_chars, count


def measure(
    messages: Any,
    *,
    loop_start_index: int = 0,
    prefix_message_count: int = 1,
    extra_prefix_bytes: int = 0,
    extra_prefix_chars: Optional[int] = None,
    config: Any = None,
    settings: Optional[GovernorSettings] = None,
    model: str = "",
    base_url: str = "",
) -> Measurement:
    """Measure what this model step is about to send.  **Never raises.**

    ``prefix_message_count`` is how many leading messages are the static
    prefix (the system prompt, plus the planner's system message when there is
    one).  ``loop_start_index`` is where the Multi-Turn loop began appending -
    everything from there on is the hot bucket, the one that grows without
    limit.  ``extra_prefix_bytes`` carries the bound tool schemas, which are
    sent with every request but live nowhere in ``messages``.

    The list is READ, never modified.
    """
    try:
        s = settings or resolve_settings(config)
        items = list(messages) if messages is not None else []
        n = len(items)
        head = max(0, min(prefix_message_count, n))
        start = max(head, min(loop_start_index if loop_start_index > 0 else n, n))

        p_bytes, p_chars, _ = _bucket(items[:head])
        plan_bytes, _plan_chars, _ = _bucket(items[1:head])
        h_bytes, h_chars, _ = _bucket(items[head:start])
        l_bytes, l_chars, l_count = _bucket(items[start:])

        extra = max(0, int(extra_prefix_bytes or 0))
        # The tool surface has a wire size AND a prompt size, and they differ
        # for the same reason a message's do (JSON structure + escaping). The
        # caller measures both because only it can see the bound tools; if it
        # gives only one, assume they are the same rather than inventing a
        # ratio.
        extra_chars = extra if extra_prefix_chars is None else max(0, int(extra_prefix_chars or 0))
        prefix_bytes = p_bytes + extra
        total_bytes = prefix_bytes + h_bytes + l_bytes
        # Chars drive the TOKEN estimate, so the schema blob is counted here
        # too - it is the single largest part of the prefix and the model
        # tokenizes it like everything else.
        total_chars = p_chars + h_chars + l_chars + extra_chars

        tokens = int(total_chars / CHARS_PER_TOKEN) if total_chars > 0 else 0
        ctx_chars = 0
        ctx_bytes = 0
        for message in items:
            c_chars, c_bytes = _context_span(_message_text(message))
            ctx_chars += c_chars
            ctx_bytes += c_bytes
        ceiling, source = resolve_ceiling_tokens(
            config, s, model=model, base_url=base_url
        )
        ratio = (tokens / ceiling) if ceiling > 0 else 0.0
        return Measurement(
            prefix_bytes=prefix_bytes,
            history_bytes=h_bytes,
            loop_bytes=l_bytes,
            total_bytes=total_bytes,
            total_chars=total_chars,
            tokens_estimated=tokens,
            ceiling_tokens=ceiling,
            ceiling_source=source,
            ratio=ratio,
            zone=zone_for(ratio, s),
            messages_count=n,
            loop_messages=l_count,
            ok=True,
            context_bytes=ctx_bytes,
            context_chars=ctx_chars,
            model=str(model or ""),
            plan_bytes=plan_bytes,
        )
    except Exception:  # noqa: BLE001 - measurement must never break a request
        return Measurement(ok=False)


# ── Reporting ───────────────────────────────────────────────────────────────
def humanize_bytes(num: int) -> str:
    """``402551`` -> ``'393.1 KB'``.  Companionable, never the headline."""
    try:
        value = float(num)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def format_log_line(measurement: Measurement, label: str = "") -> str:
    """ONE grep-able line per model step, in the ``[BINARY-GUARD]`` house style.

    Bytes first and unrounded (that is the measurement); the token figure and
    the percentage both carry ``est.`` because they are not.
    """
    try:
        if not measurement.ok:
            return "--- [CONTEXT] measurement unavailable (fail-open, nothing changed)"
        pct = measurement.ratio * 100.0
        where = f" [{label}]" if label else ""
        return (
            f"--- [CONTEXT]{where} {measurement.total_bytes} B "
            f"({humanize_bytes(measurement.total_bytes)}) on the wire | "
            f"prefix {humanize_bytes(measurement.prefix_bytes)} + "
            f"history {humanize_bytes(measurement.history_bytes)} + "
            f"loop {humanize_bytes(measurement.loop_bytes)} "
            f"({measurement.loop_messages} msg) | "
            f"~{measurement.tokens_estimated} tokens est. of "
            f"{measurement.ceiling_tokens} ({measurement.ceiling_source}) "
            f"= {pct:.1f}% est. | zone {measurement.zone.upper()}"
        )
    except Exception:  # noqa: BLE001
        return "--- [CONTEXT] measurement unavailable (fail-open, nothing changed)"


def gauge_payload(measurement: Measurement, settings: Optional[GovernorSettings] = None,
                  label: str = "") -> Dict[str, Any]:
    """The frame body the browser gauge renders.

    ``bytes_total`` is the exact integer and is never rounded away here - the
    GUI shows the humanised form and keeps the integer for the hover.
    """
    try:
        s = settings or GovernorSettings()
        return {
            "ok": bool(measurement.ok),
            "bytes_total": int(measurement.total_bytes),
            "bytes_prefix": int(measurement.prefix_bytes),
            # Of bytes_prefix: the per-question planner plan (0 when none).
            "bytes_plan": int(measurement.plan_bytes),
            "bytes_history": int(measurement.history_bytes),
            "bytes_loop": int(measurement.loop_bytes),
            "bytes_human": humanize_bytes(measurement.total_bytes),
            # Characters drive the truncation verdict when Ollama's real
            # count arrives (a request cannot hold more chars than physics
            # allows per token - see note_real_count).
            "chars_total": int(measurement.total_chars),
            "tokens_estimated": int(measurement.tokens_estimated),
            "tokens_are_estimated": True,
            "ceiling_tokens": int(measurement.ceiling_tokens),
            "ceiling_source": str(measurement.ceiling_source),
            "ratio": round(float(measurement.ratio), 6),
            "zone": str(measurement.zone),
            "messages": int(measurement.messages_count),
            "loop_messages": int(measurement.loop_messages),
            "label": str(label or ""),
            # The project context inside this request (measured, raw UTF-8).
            "bytes_context": int(measurement.context_bytes),
            "chars_context": int(measurement.context_chars),
            "model": str(measurement.model or ""),
            # REAL tokens arrive later from Ollama itself (prompt_eval_count)
            # and are merged by apply_real_tokens().  Until then the frame is
            # an ESTIMATE and says so - the GUI must never show it as real.
            "tokens_real": None,
            "ratio_is_real": False,
            "ratio_estimated": round(float(measurement.ratio), 6),
            "tokens_source": "estimate (chars / %g)" % CHARS_PER_TOKEN,
            "watermarks": {
                "compact": s.watermark_compact,
                "fold": s.watermark_fold,
                "floor": s.watermark_floor,
            },
            "history_turns": int(s.gauge_history_turns),
        }
    except Exception:  # noqa: BLE001
        return {"ok": False}


# ── The gauge sink ──────────────────────────────────────────────────────────
# Same shape as ``self_healing``'s status broadcaster and ``exec_permission``'s
# broker: the executor runs in a sync worker thread and cannot touch the
# WebSocket, so the consumer registers a fire-and-forget ``emit(payload)`` that
# schedules a group_send onto its own event loop, keyed by the conversation
# user id.  ONE-WAY and NEVER awaited - the gauge must not be able to slow a
# turn down.  If the emit fails, the turn continues and the ring simply keeps
# its last value.
_GAUGE_SINKS: "Dict[Any, Callable[[Dict[str, Any]], None]]" = {}
_GAUGE_LOCK = threading.Lock()


def register_gauge_sink(user_id: Any, emit: "Callable[[Dict[str, Any]], None]") -> None:
    if user_id is None or emit is None:
        return
    with _GAUGE_LOCK:
        _GAUGE_SINKS[user_id] = emit


def unregister_gauge_sink(user_id: Any, emit: "Optional[Callable[[Dict[str, Any]], None]]" = None) -> None:
    """Remove the sink for ``user_id``.

    Pass the SPECIFIC ``emit`` this request registered so a finishing request
    cannot tear down a concurrent same-user request's live sink - two browser
    tabs share one user id.  (The lesson ``unregister_status_broadcaster``
    already learned.)
    """
    with _GAUGE_LOCK:
        if emit is not None and _GAUGE_SINKS.get(user_id) is not emit:
            return
        _GAUGE_SINKS.pop(user_id, None)


def publish_gauge(user_id: Any, payload: Dict[str, Any]) -> bool:
    """Push one gauge frame.  Returns whether a sink took it.  Never raises."""
    if user_id is None:
        return False
    with _GAUGE_LOCK:
        emit = _GAUGE_SINKS.get(user_id)
    if emit is None:
        return False
    try:
        # 2026-10-01: every frame carries this user's model-capacity verdict
        # (full / compact) so the page reacts from the frame that draws the ring.
        cap = capacity_for(user_id)
        if cap and isinstance(payload, dict):
            payload = dict(payload)
            payload["capacity"] = cap
        emit(payload)
        return True
    except Exception:  # noqa: BLE001 - the chat path owes the gauge nothing
        return False


# ── THE METER: recalculate OFF the request thread ───────────────────────────
# Angela, 2026-09-21: *"CREATE A THREAD TO TAKE THE REAL DATA FROM THE REAL
# CONTEXT, MARK SEMAPHORES TO TAKE THE INFORMATION WHEN SOMETHING CHANGED AND
# THE THREAD MUST RECALCULATE, BUT DON'T RECALCULATE ONLINE ... WITHOUT
# BLOCKING THE MAIN THREAD."*
#
# Measuring means SERIALIZING the payload, and a real conversation here reaches
# 1.7 MB. Doing that inline before every model call spends the user's own
# latency on a number that only decorates a ring. So the request thread does
# the one thing only it can do - take a consistent snapshot of a list that is
# still being appended to - and hands it over. One daemon worker does the
# arithmetic.
#
# CONTRACTS (do NOT weaken):
#   1. ``submit()`` NEVER blocks on the measurement and NEVER raises. It holds
#      the mutex only long enough to swap one pointer.
#   2. COALESCING: only the NEWEST sample survives. A gauge needs the latest
#      value, not a backlog - five samples arriving during one computation must
#      cost ONE computation, not five. Superseded samples are counted, not
#      hidden.
#   3. The heavy work runs OUTSIDE the lock, so a slow measurement can never
#      stall a submitting thread.
#   4. The worker CANNOT die. Every iteration is guarded; a meter that stopped
#      silently would freeze the ring on a stale number, which is precisely the
#      bug this replaces.
#   5. The snapshot is taken on the CALLER's thread deliberately: the executor
#      appends to ``messages`` between turns, so iterating it from another
#      thread would be a race ("list changed size during iteration").
#   6. Daemon thread: it can never hold the process open at exit.


@dataclass(frozen=True)
class MeterSample:
    """One request to measure. Immutable, and already snapshotted."""

    user_id: Any = None
    messages: Tuple[Any, ...] = field(default_factory=tuple)
    label: str = ""
    source: str = "model"
    loop_start_index: int = 0
    prefix_message_count: int = 1
    extra_prefix_bytes: int = 0
    extra_prefix_chars: Optional[int] = None
    config: Any = None
    settings: Optional[GovernorSettings] = None
    # 2026-09-28: pairing with Ollama's REAL count.  ``seq`` identifies this
    # exact request so the prompt_eval_count that comes back for it lands on
    # the right frame; ``kind`` is "live" (being sent now) or "rest" (the
    # request the NEXT message would send, measured while idle).
    seq: int = 0
    model: str = ""
    base_url: str = ""
    kind: str = "live"
    note: str = ""


class ContextMeter:
    """A single background worker that measures whatever arrived last."""

    #: Minimum gap between two measurements, in seconds.
    #
    # ⚠️ This is NOT cosmetic pacing - it is what keeps the promise that the
    # request thread stays free. Python has ONE interpreter lock: a worker
    # serializing 1.7 MB back-to-back steals it from the thread trying to
    # submit, and a measured submit() then costs as much as measuring inline
    # did (5.8 ms observed before this throttle). Bounding the worker's duty
    # cycle bounds that contention. ~7 refreshes a second is still real time
    # to a human eye, and the latest-wins rule means nothing is lost - only
    # recomputed less often.
    MIN_INTERVAL_SECONDS = 0.15

    def __init__(self, min_interval: float = MIN_INTERVAL_SECONDS) -> None:
        # ONE condition variable = the mutex AND the "something changed"
        # signal. Two primitives would need an ordering rule between them;
        # one cannot deadlock against itself.
        self._cond = threading.Condition()
        self._min_interval = max(0.0, float(min_interval or 0.0))
        self._last_run = 0.0
        self._pending: Optional[MeterSample] = None
        self._dirty = False
        self._thread: Optional[threading.Thread] = None
        self._measured = 0
        self._superseded = 0
        self._failures = 0
        self._last: Optional[Measurement] = None

    # ── hot path: called by the request thread ──────────────────────────
    def submit(self, sample: MeterSample) -> bool:
        """Hand a snapshot to the worker. Returns whether it was accepted."""
        try:
            with self._cond:
                if self._pending is not None:
                    # Superseded before it was ever measured - correct for a
                    # gauge, and counted so it is never a silent drop.
                    self._superseded += 1
                self._pending = sample
                self._dirty = True
                self._ensure_worker_locked()
                self._cond.notify()
            return True
        except Exception:  # noqa: BLE001 - the model call owes the gauge nothing
            return False

    def _ensure_worker_locked(self) -> None:
        """Start the worker on first use. Called holding ``_cond``.

        Starting a thread under the lock is safe: the new thread's first act is
        to acquire the same lock, so it simply waits the microsecond until the
        submitter releases it.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        worker = threading.Thread(
            target=self._run, name="tlamatini-context-meter", daemon=True
        )
        self._thread = worker
        worker.start()

    # ── the worker ──────────────────────────────────────────────────────
    def _run(self) -> None:
        while True:
            sample = None
            try:
                # 1. Sleep until something changed. ``wait()`` releases the
                #    mutex, so a submitter is never delayed by a waiting
                #    worker.
                with self._cond:
                    while not self._dirty:
                        self._cond.wait()

                # 2. Throttle OUTSIDE the lock, so submits stay free while we
                #    are pacing ourselves.
                gap = self._min_interval - (time.monotonic() - self._last_run)
                if gap > 0:
                    time.sleep(gap)

                # 3. Only NOW take the sample - so anything that arrived
                #    during the pause supersedes what triggered us, and the
                #    measurement is of the freshest state, never a stale one.
                with self._cond:
                    sample = self._pending
                    self._pending = None
                    self._dirty = False
                if sample is not None:
                    self._last_run = time.monotonic()
                    self._measure_and_publish(sample)
            except Exception:  # noqa: BLE001 - the worker must never die
                try:
                    with self._cond:
                        self._failures += 1
                except Exception:  # noqa: BLE001
                    pass
                try:
                    time.sleep(0.05)   # never spin hot on a repeating fault
                except Exception:  # noqa: BLE001
                    pass

    def _measure_and_publish(self, sample: MeterSample) -> None:
        settings = sample.settings or resolve_settings(sample.config)
        if not settings.enabled:
            return
        measurement = measure(
            sample.messages,
            loop_start_index=sample.loop_start_index,
            prefix_message_count=sample.prefix_message_count,
            extra_prefix_bytes=sample.extra_prefix_bytes,
            extra_prefix_chars=sample.extra_prefix_chars,
            config=sample.config,
            settings=settings,
            model=sample.model,
            base_url=sample.base_url,
        )
        with self._cond:
            self._measured += 1
            self._last = measurement
        if settings.log_each:
            print(format_log_line(measurement, sample.label))
        if sample.kind == KIND_SIDE:
            # Not Tlamatini's main inference (an ACPX child's prompt, say):
            # logged for the record, NEVER shown on the ring - the ring is the
            # main chain's request and nothing else (Angela, 2026-09-28).
            return
        if settings.gauge_enabled:
            payload = gauge_payload(measurement, settings, sample.label)
            payload["source"] = sample.source or "model"
            payload["seq"] = int(sample.seq or 0)
            payload["kind"] = str(sample.kind or "live")
            if sample.note:
                payload["note"] = str(sample.note)
            _remember_and_publish(sample.user_id, payload, settings)

    # ── introspection (tests, diagnostics) ──────────────────────────────
    def stats(self) -> Dict[str, Any]:
        with self._cond:
            return {
                "measured": self._measured,
                "superseded": self._superseded,
                "failures": self._failures,
                "pending": self._pending is not None,
                "alive": bool(self._thread is not None and self._thread.is_alive()),
            }

    def latest(self) -> Optional[Measurement]:
        with self._cond:
            return self._last

    def drain(self, timeout: float = 2.0) -> bool:
        """Wait until nothing is pending. For TESTS only - never on a request."""
        deadline = time.time() + max(0.0, timeout)
        while time.time() < deadline:
            with self._cond:
                if not self._dirty and self._pending is None:
                    return True
            time.sleep(0.005)
        return False


METER = ContextMeter()


# ── Whose request is this? ──────────────────────────────────────────────────
# A LangChain callback fires deep inside a chain and has no idea which user it
# serves, so the consumer BINDS the id once per request and every call site
# downstream inherits it.
#
# ⚠️ A ContextVar, never a thread-local: ONE event-loop thread serves EVERY
# connected user, so a thread-local would smear one user's id across another's
# coroutine. ``sync_to_async`` propagates the context, so the whole synchronous
# chain stack is covered for free. (The same reasoning as log_identity.py.)
_CURRENT_USER: "contextvars.ContextVar[Any]" = contextvars.ContextVar(
    "tlamatini_context_user", default=None
)


def bind_user(user_id: Any) -> Any:
    """Bind the conversation user for this request. Returns a reset token."""
    try:
        return _CURRENT_USER.set(user_id)
    except Exception:  # noqa: BLE001
        return None


def unbind_user(token: Any) -> None:
    """Restore the previous binding. Never raises."""
    if token is None:
        return
    try:
        _CURRENT_USER.reset(token)
    except Exception:  # noqa: BLE001
        pass


def current_user() -> Any:
    try:
        return _CURRENT_USER.get()
    except Exception:  # noqa: BLE001
        return None


def measure_async(
    user_id: Any,
    messages: Any,
    *,
    label: str = "",
    source: str = "model",
    loop_start_index: int = 0,
    prefix_message_count: int = 1,
    extra_prefix_bytes: int = 0,
    extra_prefix_chars: Optional[int] = None,
    config: Any = None,
    settings: Optional[GovernorSettings] = None,
    meter: Optional[ContextMeter] = None,
    seq: Optional[int] = None,
    model: str = "",
    base_url: str = "",
    kind: str = "live",
    note: str = "",
) -> bool:
    """**The one entry point every model call site uses.**

    Snapshot on this thread (cheap: a tuple of pointers), measure on the
    worker. Returns whether the sample was accepted - never raises, so a
    caller can invoke it on the line before ``llm.invoke`` without a guard.

    ``messages`` may be a message list OR a bare prompt string (ACPX sends one
    string to a child), so every surface can report through the same door.
    """
    try:
        if isinstance(messages, str):
            snapshot: Tuple[Any, ...] = (messages,)
        elif messages is None:
            snapshot = ()
        else:
            # THE FENCE: a shallow copy, taken here, while this thread still
            # owns the list. Microseconds for a few hundred pointers.
            snapshot = tuple(messages)
    except Exception:  # noqa: BLE001
        return False
    if user_id is None:
        # A chain callback does not know the user; the request bound it.
        user_id = current_user()
    try:
        sample = MeterSample(
            user_id=user_id,
            messages=snapshot,
            label=str(label or ""),
            source=str(source or "model"),
            loop_start_index=int(loop_start_index or 0),
            prefix_message_count=int(prefix_message_count or 0),
            extra_prefix_bytes=int(extra_prefix_bytes or 0),
            extra_prefix_chars=extra_prefix_chars,
            config=config,
            settings=settings,
            # Pass the SAME number to report_real_usage() when Ollama answers,
            # or the real count cannot be paired with this frame.
            seq=int(seq) if seq else next_seq(),
            model=str(model or ""),
            base_url=str(base_url or ""),
            kind=str(kind or "live"),
            note=str(note or ""),
        )
    except Exception:  # noqa: BLE001
        return False
    return (meter or METER).submit(sample)


# ══ REAL TOKENS - Ollama's own counts (2026-09-28) ═══════════════════════════
# Angela, 2026-09-28: *"make that gauge counter to be real, NOT FAKE ... this is
# going to be metered by NVIDIA/INTEL/CISCO systems in real executions, SO
# BETTER YOU DONT LIE!"*
#
# Everything above ESTIMATES tokens (chars / 4) because it runs BEFORE the
# request leaves.  Ollama reports the real number AFTER: every /api/chat and
# /api/generate reply carries ``prompt_eval_count`` (prompt tokens the server
# evaluated - system prompt, tool schemas, history, context, question, all of
# it, after the model's own chat template) and ``eval_count`` (tokens it
# generated).  Ollama has NO /api/tokenize (measured: HTTP 404), so that reply
# is the only real count it exposes - and it is the one used here.
#
# CONTRACTS (do NOT weaken):
#   1. A number is shown as REAL only when it came from Ollama's own reply.
#      Every frame says which: ``ratio_is_real`` + ``tokens_source``.
#   2. A real count is PAIRED to the exact request that produced it by
#      ``seq``.  A count for an older request never overwrites the frame of a
#      newer one - it only updates ``last_real``.
#   3. FAIL OPEN.  A missing / malformed count leaves the estimate in place,
#      still labelled an estimate.  Nothing here raises into a caller.
#   4. Stdlib only; /api/show is plain urllib, cached, and never called on a
#      request thread (only the meter worker and the at-rest probe reach it).

_SEQ_LOCK = threading.Lock()
_SEQ_COUNTER = [0]


def next_seq() -> int:
    """A process-wide, strictly increasing request number.  Never raises."""
    with _SEQ_LOCK:
        _SEQ_COUNTER[0] += 1
        return _SEQ_COUNTER[0]


def _nonneg_int(value: Any) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


# ── The model's real context length (the denominator) ─────────────────────────
_SHOW_CACHE: "Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]]" = {}
_SHOW_LOCK = threading.Lock()
_SHOW_TTL_OK_SECONDS = 3600.0     # a model's context length does not change
_SHOW_TTL_FAIL_SECONDS = 60.0     # ...but a server that was down may come back


def is_cloud_model(model: str, info: Optional[Dict[str, Any]] = None) -> bool:
    """Ollama cloud models are tagged ``:cloud`` or ``:<size>-cloud``.

    ``/api/show`` does not say so (``remote_host`` came back ``null`` for
    ``glm-5.3:cloud``, measured 2026-09-28), so the tag is the evidence.
    """
    try:
        if info and info.get("remote_host"):
            return True
        tag = str(model or "").strip().lower()
        if ":" in tag:
            tag = tag.rsplit(":", 1)[1]
        return tag == "cloud" or tag.endswith("-cloud")
    except Exception:  # noqa: BLE001
        return False


def _ollama_show_info(
    model: str,
    base_url: str = "",
    *,
    token: str = "",
    timeout: float = DEFAULT_SHOW_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """``POST /api/show`` -> ``{"context_length": int, "remote_host": ...}``.

    Cached per (server, model).  Returns ``{}`` on any failure.  The token is
    sent as a Bearer header exactly as the chat client sends it, and is never
    printed.
    """
    name = str(model or "").strip()
    if not name:
        return {}
    base = (str(base_url or "").strip() or "http://127.0.0.1:11434").rstrip("/")
    key = (base, name)
    now = time.monotonic()
    with _SHOW_LOCK:
        hit = _SHOW_CACHE.get(key)
        if hit is not None and hit[0] > now:
            return dict(hit[1])
    info: Dict[str, Any] = {}
    ctx_len = 0
    error = ""
    try:
        headers = {"Content-Type": "application/json"}
        tok = str(token or "").strip()
        if tok and not tok.startswith("<"):       # "<KEY goes here>" = no key
            headers["Authorization"] = "Bearer " + tok
        request = urllib.request.Request(
            base + "/api/show",
            data=json.dumps({"model": name}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=max(1.0, float(timeout or 4.0))) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        model_info = data.get("model_info") or {}
        if isinstance(model_info, dict):
            for k, v in model_info.items():
                if str(k).endswith(".context_length"):
                    n = _nonneg_int(v) or 0
                    ctx_len = max(ctx_len, n)
        info = {
            "context_length": ctx_len,
            "remote_host": data.get("remote_host"),
            "family": str((data.get("details") or {}).get("family") or ""),
        }
    except Exception as exc:  # noqa: BLE001 - fail open to config/fallback
        error = type(exc).__name__
        info = {}
    ok = ctx_len > 0
    with _SHOW_LOCK:
        _SHOW_CACHE[key] = (
            now + (_SHOW_TTL_OK_SECONDS if ok else _SHOW_TTL_FAIL_SECONDS),
            dict(info),
        )
    try:
        if ok:
            print(f"--- [CONTEXT-CEILING] {name}: context_length {ctx_len} "
                  f"(REAL, from {base}/api/show)")
        else:
            print(f"--- [CONTEXT-CEILING] {name}: /api/show gave no context_length"
                  f"{' (' + error + ')' if error else ''} - using config / fallback")
    except Exception:  # noqa: BLE001
        pass
    return info


def ollama_context_length(
    model: str,
    base_url: str = "",
    *,
    token: str = "",
    timeout: float = DEFAULT_SHOW_TIMEOUT_SECONDS,
) -> int:
    """The model's own context length from Ollama, or 0 when unknown."""
    try:
        return int(_ollama_show_info(model, base_url, token=token, timeout=timeout)
                   .get("context_length") or 0)
    except Exception:  # noqa: BLE001
        return 0


# ── The EFFECTIVE window: what Ollama REALLY reads (Angela, 2026-10-01) ─────
# ``/api/show`` names the context a model was TRAINED for.  A LOCAL Ollama can
# serve less, and no API says so.  Measured 2026-10-01 on ``qwen2.5:latest``:
# ``/api/show`` and ``/api/ps`` both reported 32,768, yet every ~52,000-token
# request came back with ``prompt_eval_count = 16386`` - the server runs with
# ``OLLAMA_NUM_PARALLEL=2``, which splits the 32,768-token cache into two
# 16,384-token slots, and Ollama silently DROPPED two thirds of every request.
# The model then answered "what is my CPU usage?" with the time of day.
#
# The only honest source for the real window is therefore Ollama's own count.
# A request whose characters cannot possibly fit in the tokens Ollama says it
# read was CUT, and the count it reports IS the window.  ``note_real_count()``
# is fed every main-chain count (live steps and at-rest probes); the window it
# learns is consulted FIRST by ``resolve_ceiling_tokens`` after an explicit
# ``context_ceiling_tokens``, so the gauge, the tool budgeter and the request
# fitter all agree on one number - one definition of the budget.
#
# CONTRACTS (do NOT weaken):
#   * FAIL OPEN - nothing here raises; an unusable observation is ignored.
#   * Judge only what physics can judge: a request is called "cut" only when
#     its characters per reported token are beyond anything a tokenizer
#     produces (or beyond this model's own measured ratio by a wide margin).
#   * A learned window is forgotten the moment Ollama reads MORE than it in
#     one request - the evidence moved, so the belief must move with it.
TRUNCATION_MIN_CHARS = 6000
TRUNCATION_CHARS_PER_TOKEN = 6.0
TRUNCATION_MEASURED_FACTOR = 1.6
DEFAULT_FIT_CHARS_PER_TOKEN = 3.0
_WINDOW_LOCK = threading.Lock()
_LEARNED_WINDOWS: "Dict[Tuple[str, str], Dict[str, Any]]" = {}
_MEASURED_CPT: "Dict[Tuple[str, str], float]" = {}


def window_key(model: str, base_url: str = "") -> Tuple[str, str]:
    """``(server, model)`` normalised so 127.0.0.1 / localhost / 0.0.0.0 agree."""
    base = (str(base_url or "").strip() or "http://127.0.0.1:11434").rstrip("/").lower()
    for alias in ("//localhost", "//0.0.0.0", "//[::1]"):
        base = base.replace(alias, "//127.0.0.1")
    return base, str(model or "").strip().lower()


def learned_window(model: str, base_url: str = "") -> Optional[int]:
    """The window Ollama PROVED for this model (a cut request), or None."""
    try:
        with _WINDOW_LOCK:
            hit = _LEARNED_WINDOWS.get(window_key(model, base_url))
        return int(hit["tokens"]) if hit else None
    except Exception:  # noqa: BLE001
        return None


def learned_window_info(model: str, base_url: str = "") -> Optional[Dict[str, Any]]:
    try:
        with _WINDOW_LOCK:
            hit = _LEARNED_WINDOWS.get(window_key(model, base_url))
        return dict(hit) if hit else None
    except Exception:  # noqa: BLE001
        return None


def measured_chars_per_token(model: str, base_url: str = "") -> Optional[float]:
    """This model's measured characters-per-token on Tlamatini's own requests."""
    try:
        with _WINDOW_LOCK:
            value = _MEASURED_CPT.get(window_key(model, base_url))
        return float(value) if value else None
    except Exception:  # noqa: BLE001
        return None


def fit_chars_per_token(model: str, base_url: str = "") -> float:
    """The ratio a FITTER should plan with: measured when known (with a 10 %
    safety margin), otherwise a deliberately pessimistic 3.0 - over-counting
    tokens only shrinks a request a little more; under-counting gets it cut."""
    measured = measured_chars_per_token(model, base_url)
    if measured:
        return max(1.5, min(4.5, measured * 0.9))
    return DEFAULT_FIT_CHARS_PER_TOKEN


def forget_learned_windows() -> None:
    """Drop every learned window and ratio (tests, and a model change)."""
    with _WINDOW_LOCK:
        _LEARNED_WINDOWS.clear()
        _MEASURED_CPT.clear()


def note_real_count(
    model: str,
    base_url: str,
    prompt_tokens: Any,
    request_chars: Any,
    *,
    source: str = "",
) -> Dict[str, Any]:
    """Judge one REAL count: was this request cut?  Learn from it.  Never raises.

    Returns ``{"truncated": bool, "window": int|None, "chars_per_token": float,
    "kept_pct": float}`` (``{}`` when the observation cannot be judged).
    """
    try:
        tokens = _nonneg_int(prompt_tokens) or 0
        chars = _nonneg_int(request_chars) or 0
        name = str(model or "").strip()
        if not name or tokens <= 0 or chars <= 0:
            return {}
        key = window_key(name, base_url)
        cpt = chars / float(tokens)
        with _WINDOW_LOCK:
            measured = _MEASURED_CPT.get(key)
            known = _LEARNED_WINDOWS.get(key)
        limit = TRUNCATION_CHARS_PER_TOKEN
        if measured:
            limit = min(limit, max(measured * TRUNCATION_MEASURED_FACTOR, 4.2))
        truncated = chars >= TRUNCATION_MIN_CHARS and cpt > limit
        if (not truncated and known and chars >= TRUNCATION_MIN_CHARS
                and abs(tokens - int(known["tokens"])) <= 16
                and cpt > (measured or DEFAULT_FIT_CHARS_PER_TOKEN) * 1.15):
            # Exactly the window we already learned, from a request that is
            # clearly larger than it: the same wall, hit again.
            truncated = True
        result: Dict[str, Any] = {"truncated": truncated, "window": None,
                                  "chars_per_token": round(cpt, 3)}
        if truncated:
            expected = chars / float(measured or DEFAULT_FIT_CHARS_PER_TOKEN)
            kept_pct = max(0.0, min(100.0, tokens * 100.0 / expected)) if expected else 0.0
            info = {"tokens": tokens, "at": time.time(), "chars": chars,
                    "source": str(source or ""), "kept_pct": round(kept_pct, 1)}
            with _WINDOW_LOCK:
                _LEARNED_WINDOWS[key] = info
            result.update(window=tokens, kept_pct=round(kept_pct, 1))
            print(f"--- [CONTEXT-WINDOW] {name}: Ollama CUT a request - it read only "
                  f"{tokens} tokens of ~{chars} characters ({cpt:.1f} chars/token, "
                  f"limit {limit:.1f}; ~{kept_pct:.0f}% kept). The REAL window of this "
                  f"model on this server is {tokens} tokens - learned"
                  f"{' (' + source + ')' if source else ''}.")
            return result
        if chars >= 2000:
            with _WINDOW_LOCK:
                prev = _MEASURED_CPT.get(key)
                _MEASURED_CPT[key] = cpt if not prev else (prev * 0.7 + cpt * 0.3)
        if known and tokens > int(known["tokens"]) + 16:
            with _WINDOW_LOCK:
                _LEARNED_WINDOWS.pop(key, None)
            print(f"--- [CONTEXT-WINDOW] {name}: Ollama read {tokens} tokens, more than the "
                  f"{known['tokens']} learned earlier - that window is forgotten")
        return result
    except Exception:  # noqa: BLE001
        return {}


# ── Per-user MODEL CAPACITY (Angela, 2026-10-01) ────────────────────────────
# The fitter (``agent/context_fitter.py``) decides, for every request, whether
# the model can hold Tlamatini's COMPLETE request ("full") or must run in
# "compact" mode.  That verdict is per connected user (each tab may run a
# different chain) and rides on EVERY gauge frame as ``capacity``, so the page
# can show the Compact-mode dialog, the badge and the locked ACPX switch from
# the same frame that draws the ring - no second channel to drift.
_CAPACITY_LOCK = threading.Lock()
_CAPACITY: "Dict[Any, Dict[str, Any]]" = {}


def set_capacity(user_id: Any, info: Optional[Dict[str, Any]]) -> bool:
    """Store this user's capacity verdict.  Returns True when the MODE, the
    model or the window changed (the page needs a fresh frame)."""
    try:
        if user_id is None or not isinstance(info, dict):
            return False
        with _CAPACITY_LOCK:
            prev = _CAPACITY.get(user_id)
            _CAPACITY[user_id] = dict(info)
        if prev is None:
            return True
        return any(prev.get(k) != info.get(k) for k in ("mode", "model", "window_tokens"))
    except Exception:  # noqa: BLE001
        return False


def capacity_for(user_id: Any) -> Optional[Dict[str, Any]]:
    try:
        with _CAPACITY_LOCK:
            hit = _CAPACITY.get(user_id)
        return dict(hit) if hit else None
    except Exception:  # noqa: BLE001
        return None


def publish_capacity(user_id: Any) -> bool:
    """Re-send this user's newest frame so a changed verdict reaches the page
    at once.  Never raises."""
    try:
        return _republish_latest(user_id)
    except Exception:  # noqa: BLE001
        return False


# ── Reading Ollama's counts out of a LangChain result ────────────────────────
def usage_from_llm_result(obj: Any) -> Optional[Dict[str, Any]]:
    """Ollama's own ``prompt_eval_count`` / ``eval_count`` from a result.

    Accepts an ``LLMResult`` (callbacks), an ``AIMessage`` (a chat model's
    return value) or Ollama's raw reply dict.  Duck-typed: this module never
    imports langchain.  Returns ``None`` when no real count is present - the
    caller must then keep the estimate, labelled as one.
    """
    try:
        infos = []
        messages = []
        if isinstance(obj, dict):
            infos.append(obj)
        else:
            gens = getattr(obj, "generations", None)
            if isinstance(gens, (list, tuple)) and gens:
                first = gens[0]
                if isinstance(first, (list, tuple)):
                    first = first[0] if first else None
                if first is not None:
                    gen_info = getattr(first, "generation_info", None)
                    if isinstance(gen_info, dict):
                        infos.append(gen_info)
                    msg = getattr(first, "message", None)
                    if msg is not None:
                        messages.append(msg)
            else:
                messages.append(obj)
        for msg in messages:
            meta = getattr(msg, "response_metadata", None)
            if isinstance(meta, dict):
                infos.append(meta)
        for info in infos:
            prompt = _nonneg_int(info.get("prompt_eval_count"))
            if prompt is not None:
                return {
                    "prompt_tokens": prompt,
                    "completion_tokens": _nonneg_int(info.get("eval_count")),
                    "model": str(info.get("model") or ""),
                    "field": "prompt_eval_count",
                }
        for msg in messages:
            usage = getattr(msg, "usage_metadata", None)
            if isinstance(usage, dict):
                prompt = _nonneg_int(usage.get("input_tokens"))
                if prompt is not None:
                    return {
                        "prompt_tokens": prompt,
                        "completion_tokens": _nonneg_int(usage.get("output_tokens")),
                        "model": "",
                        "field": "usage_metadata.input_tokens",
                    }
    except Exception:  # noqa: BLE001
        return None
    return None


# ── Frames, pairing, and the last real count ─────────────────────────────────
_REAL_LOCK = threading.Lock()
_LAST_FRAME: "Dict[Any, Dict[str, Any]]" = {}
_PENDING_REAL: "Dict[Tuple[Any, int], Dict[str, Any]]" = {}
_LAST_REAL: "Dict[Any, Dict[str, Any]]" = {}
_RUN_SEQ: "Dict[str, Tuple[Any, int]]" = {}
_TURNS: "Dict[Any, Dict[str, Any]]" = {}
_PENDING_LIMIT = 64
_RUN_SEQ_LIMIT = 256


def _settings_from_watermarks(payload: Dict[str, Any]) -> GovernorSettings:
    wm = payload.get("watermarks") or {}
    try:
        return GovernorSettings(
            watermark_compact=float(wm.get("compact", DEFAULT_WATERMARK_COMPACT)),
            watermark_fold=float(wm.get("fold", DEFAULT_WATERMARK_FOLD)),
            watermark_floor=float(wm.get("floor", DEFAULT_WATERMARK_FLOOR)),
        )
    except Exception:  # noqa: BLE001
        return GovernorSettings()


def apply_real_tokens(payload: Dict[str, Any], real: Dict[str, Any]) -> Dict[str, Any]:
    """Merge Ollama's own count into a frame (in place).  Never raises.

    From here on the ring, the percentage and the zone are computed from the
    REAL count.  The estimate stays in the frame beside it, with the error
    between the two, so anyone can check the arithmetic.
    """
    try:
        prompt = _nonneg_int((real or {}).get("prompt_tokens"))
        if prompt is None:
            return payload
        payload["tokens_real"] = prompt
        payload["completion_tokens_real"] = _nonneg_int(real.get("completion_tokens"))
        payload["ratio_is_real"] = True
        payload["tokens_source"] = "Ollama " + str(real.get("field") or "prompt_eval_count")
        payload["real_model"] = str(real.get("model") or payload.get("model") or "")
        ceiling = int(payload.get("ceiling_tokens") or 0)
        if ceiling > 0:
            ratio = prompt / float(ceiling)
            payload["ratio"] = round(ratio, 6)
            payload["zone"] = zone_for(ratio, _settings_from_watermarks(payload))
        estimate = int(payload.get("tokens_estimated") or 0)
        if prompt > 0:
            payload["estimate_error_pct"] = round((estimate - prompt) * 100.0 / prompt, 2)
        # 2026-10-01: a REAL count that is physically too small for the
        # characters sent means Ollama CUT the request.  Never draw that as
        # "50% used" - it is 100% full and something was thrown away.
        chars = int(payload.get("chars_total") or 0)
        if (prompt > 0 and chars >= TRUNCATION_MIN_CHARS
                and chars / float(prompt) > TRUNCATION_CHARS_PER_TOKEN):
            payload["truncated"] = True
            payload["ratio"] = 1.0
            payload["zone"] = ZONE_FLOOR
            payload["truncated_note"] = (
                "Ollama read only %d tokens of this request and DROPPED the rest - "
                "the model's real window is smaller than its declared one" % prompt)
    except Exception:  # noqa: BLE001
        pass
    return payload


def _turn_snapshot_locked(user_id: Any) -> Optional[Dict[str, Any]]:
    turn = _TURNS.get(user_id)
    if not turn:
        return None
    snap = dict(turn)
    snap["models"] = {k: dict(v) for k, v in (turn.get("models") or {}).items()}
    return snap


def _format_real_line(payload: Optional[Dict[str, Any]], real: Dict[str, Any]) -> str:
    try:
        label = str(real.get("label") or (payload or {}).get("label") or "")
        where = f" [{label}]" if label else ""
        prompt = int(real.get("prompt_tokens") or 0)
        completion = real.get("completion_tokens")
        head = (f"--- [CONTEXT-REAL]{where} seq={real.get('seq')} "
                f"model={real.get('model') or (payload or {}).get('model') or '?'} "
                f"prompt_eval_count={prompt} eval_count="
                f"{completion if completion is not None else '?'}")
        if not payload:
            return head + " | estimate for this request not measured yet"
        est = int(payload.get("tokens_estimated") or 0)
        err = payload.get("estimate_error_pct")
        ceiling = int(payload.get("ceiling_tokens") or 0)
        pct = (prompt * 100.0 / ceiling) if ceiling else 0.0
        return (f"{head} | estimate {est} "
                f"({'%+.2f%%' % err if err is not None else 'n/a'}) | "
                f"{prompt} of {ceiling} ({payload.get('ceiling_source')}) = "
                f"{pct:.2f}% REAL | {payload.get('kind', 'live')}")
    except Exception:  # noqa: BLE001
        return "--- [CONTEXT-REAL] (unformattable)"


def _remember_and_publish(user_id: Any, payload: Dict[str, Any],
                          settings: Optional[GovernorSettings] = None) -> bool:
    """Store a fresh frame as this user's latest and publish it.

    Merges a real count that arrived BEFORE the measurement finished, attaches
    ``last_real`` and the current turn's totals, and refuses to let an older
    frame replace a newer one.  Never raises.
    """
    try:
        seq = int(payload.get("seq") or 0)
        use_real = settings is None or settings.real_tokens
        with _REAL_LOCK:
            prev = _LAST_FRAME.get(user_id)
            if prev is not None and seq and int(prev.get("seq") or 0) > seq:
                return False                     # a newer frame is already showing
            real = _PENDING_REAL.pop((user_id, seq), None) if seq else None
            for key in [k for k in _PENDING_REAL if k[0] == user_id and k[1] < seq]:
                _PENDING_REAL.pop(key, None)     # superseded, never measured
            last_real = dict(_LAST_REAL[user_id]) if user_id in _LAST_REAL else None
            turn = _turn_snapshot_locked(user_id)
        if real and use_real:
            apply_real_tokens(payload, real)
            print(_format_real_line(payload, real))
        if last_real:
            payload["last_real"] = last_real
        if turn:
            payload["turn"] = turn
        with _REAL_LOCK:
            _LAST_FRAME[user_id] = payload
        return publish_gauge(user_id, dict(payload))
    except Exception:  # noqa: BLE001
        return False


def _republish_latest(user_id: Any) -> bool:
    """Re-send this user's newest frame with fresh ``last_real`` / ``turn``."""
    try:
        with _REAL_LOCK:
            frame = _LAST_FRAME.get(user_id)
            if frame is None:
                return False
            frame = dict(frame)
            if user_id in _LAST_REAL:
                frame["last_real"] = dict(_LAST_REAL[user_id])
            turn = _turn_snapshot_locked(user_id)
            if turn:
                frame["turn"] = turn
            _LAST_FRAME[user_id] = frame
        return publish_gauge(user_id, dict(frame))
    except Exception:  # noqa: BLE001
        return False


def latest_frame(user_id: Any) -> Optional[Dict[str, Any]]:
    """The newest frame published for ``user_id`` (a copy), or None."""
    with _REAL_LOCK:
        frame = _LAST_FRAME.get(user_id)
        return dict(frame) if frame is not None else None


def report_real_usage(
    user_id: Any,
    seq: Any,
    prompt_tokens: Any,
    completion_tokens: Any = None,
    *,
    model: str = "",
    label: str = "",
    field_name: str = "prompt_eval_count",
    config: Any = None,
) -> bool:
    """Ollama answered request ``seq``: attach its REAL prompt count.

    Returns whether the count was accepted.  Never raises.
    """
    try:
        if user_id is None:
            user_id = current_user()
        prompt = _nonneg_int(prompt_tokens)
        seq_i = int(seq or 0)
        if user_id is None or prompt is None or seq_i <= 0:
            return False
        settings = resolve_settings(config) if config is not None else GovernorSettings()
        if not settings.real_tokens:
            return False
        real = {
            "prompt_tokens": prompt,
            "completion_tokens": _nonneg_int(completion_tokens),
            "model": str(model or ""),
            "label": str(label or ""),
            "field": str(field_name or "prompt_eval_count"),
            "seq": seq_i,
            "at": time.time(),
        }
        merged = None
        with _REAL_LOCK:
            _LAST_REAL[user_id] = {
                "tokens": prompt,
                "completion_tokens": real["completion_tokens"],
                "model": real["model"],
                "label": real["label"],
                "seq": seq_i,
                "at": real["at"],
            }
            frame = _LAST_FRAME.get(user_id)
            frame_seq = int(frame.get("seq") or 0) if frame is not None else 0
            if frame is not None and frame_seq == seq_i:
                merged = dict(frame)
            elif frame_seq < seq_i:
                # Its measurement has not been published yet: park it; the
                # worker merges it the moment that frame is ready.
                _PENDING_REAL[(user_id, seq_i)] = real
                while len(_PENDING_REAL) > _PENDING_LIMIT:
                    _PENDING_REAL.pop(next(iter(_PENDING_REAL)), None)
        if merged is not None:
            apply_real_tokens(merged, real)
            print(_format_real_line(merged, real))
            with _REAL_LOCK:
                if int((_LAST_FRAME.get(user_id) or {}).get("seq") or 0) == seq_i:
                    merged["last_real"] = dict(_LAST_REAL[user_id])
                    turn = _turn_snapshot_locked(user_id)
                    if turn:
                        merged["turn"] = turn
                    _LAST_FRAME[user_id] = merged
                else:
                    merged = None
            if merged is not None:
                publish_gauge(user_id, dict(merged))
                return True
        else:
            print(_format_real_line(None, real))
        _republish_latest(user_id)
        return True
    except Exception:  # noqa: BLE001
        return False


def note_run_seq(run_id: Any, seq: Any, user_id: Any = None) -> None:
    """Remember which frame a LangChain run (``run_id``) belongs to.

    The one-shot chains measure in ``on_chat_model_start`` and learn Ollama's
    count in ``on_llm_end``; the run id is the only thing the two callbacks
    share.  Bounded; never raises.
    """
    try:
        if run_id is None or not seq:
            return
        uid = user_id if user_id is not None else current_user()
        with _REAL_LOCK:
            _RUN_SEQ[str(run_id)] = (uid, int(seq))
            while len(_RUN_SEQ) > _RUN_SEQ_LIMIT:
                _RUN_SEQ.pop(next(iter(_RUN_SEQ)), None)
    except Exception:  # noqa: BLE001
        pass


def report_run_usage(run_id: Any, usage: Optional[Dict[str, Any]], label: str = "") -> bool:
    """Pair a finished LangChain run's real count with its frame, if any."""
    try:
        if run_id is None or not usage:
            return False
        with _REAL_LOCK:
            hit = _RUN_SEQ.pop(str(run_id), None)
        if hit is None:
            return False
        uid, seq = hit
        return report_real_usage(
            uid, seq, usage.get("prompt_tokens"), usage.get("completion_tokens"),
            model=str(usage.get("model") or ""), label=label,
            field_name=str(usage.get("field") or "prompt_eval_count"),
        )
    except Exception:  # noqa: BLE001
        return False


# ── Per-answer totals: every Ollama call a chat turn makes ────────────────────
# One answer is rarely one call: the internet / access classifiers, the
# history summarizer, the system-metrics and file-search sidecars, and every
# Multi-Turn step each send their own prompt.  The gauge ring shows the size
# of ONE request; this is what the whole answer really cost, call by call, in
# Ollama's own numbers.  Workflow agents run as separate processes and meter
# themselves - they are NOT in these totals, and the GUI says so.

def begin_turn(user_id: Any = None, label: str = "") -> None:
    """Start counting a new answer for ``user_id``.  Never raises."""
    try:
        uid = user_id if user_id is not None else current_user()
        if uid is None:
            return
        with _REAL_LOCK:
            _TURNS[uid] = {
                "label": str(label or ""),
                "started_at": time.time(),
                "open": True,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "largest_prompt": 0,
                "models": {},
            }
    except Exception:  # noqa: BLE001
        pass


def record_call_usage(
    prompt_tokens: Any,
    completion_tokens: Any = None,
    *,
    user_id: Any = None,
    model: str = "",
    source: str = "",
) -> bool:
    """Add ONE real Ollama call to the current answer's totals.  Never raises."""
    try:
        prompt = _nonneg_int(prompt_tokens)
        if prompt is None:
            return False
        completion = _nonneg_int(completion_tokens) or 0
        uid = user_id if user_id is not None else current_user()
        name = str(model or "?")
        line = (f"--- [CONTEXT-CALL] {name} prompt_eval_count={prompt} "
                f"eval_count={completion} ({source or 'ollama'})")
        if uid is None:
            print(line + " | no user bound - not attributed to an answer")
            return False
        with _REAL_LOCK:
            turn = _TURNS.get(uid)
            if turn is None:
                turn = {
                    "label": "", "started_at": time.time(), "open": True,
                    "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "largest_prompt": 0, "models": {},
                }
                _TURNS[uid] = turn
            turn["calls"] += 1
            turn["prompt_tokens"] += prompt
            turn["completion_tokens"] += completion
            turn["largest_prompt"] = max(int(turn.get("largest_prompt") or 0), prompt)
            per = turn["models"].setdefault(
                name, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
            )
            per["calls"] += 1
            per["prompt_tokens"] += prompt
            per["completion_tokens"] += completion
            totals = (turn["calls"], turn["prompt_tokens"], turn["completion_tokens"])
        print(f"{line} | answer so far: {totals[0]} call(s), "
              f"{totals[1]} prompt + {totals[2]} output tokens (REAL)")
        _republish_latest(uid)
        return True
    except Exception:  # noqa: BLE001
        return False


def turn_totals(user_id: Any = None) -> Optional[Dict[str, Any]]:
    """A copy of the current answer's totals, or None."""
    try:
        uid = user_id if user_id is not None else current_user()
        with _REAL_LOCK:
            return _turn_snapshot_locked(uid)
    except Exception:  # noqa: BLE001
        return None


def end_turn(user_id: Any = None) -> Optional[Dict[str, Any]]:
    """Close the answer's totals, log them once, and return them."""
    try:
        uid = user_id if user_id is not None else current_user()
        with _REAL_LOCK:
            turn = _TURNS.get(uid)
            if turn is None:
                return None
            turn["open"] = False
            turn["ended_at"] = time.time()
            snap = _turn_snapshot_locked(uid)
        seconds = (snap.get("ended_at", 0) - snap.get("started_at", 0)) if snap else 0
        print(f"--- [CONTEXT-TURN] answer finished: {snap['calls']} Ollama call(s), "
              f"{snap['prompt_tokens']} prompt + {snap['completion_tokens']} output "
              f"tokens (REAL, prompt_eval_count/eval_count), largest single prompt "
              f"{snap['largest_prompt']}, {seconds:.1f} s")
        _republish_latest(uid)
        return snap
    except Exception:  # noqa: BLE001
        return None
