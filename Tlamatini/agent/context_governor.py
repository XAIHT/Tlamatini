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
        )
    except Exception:  # noqa: BLE001 - settings must never break a request
        return GovernorSettings()


# ── The ceiling (the denominator) ───────────────────────────────────────────
def resolve_ceiling_tokens(config: Any, settings: Optional[GovernorSettings] = None) -> Tuple[int, str]:
    """Return ``(ceiling_tokens, source)``.

    Order: an explicit ``context_ceiling_tokens`` wins; else the local model's
    ``ollama_num_ctx`` (which is real for a LOCAL model - it sizes the KV cache
    at load); else the large fallback.  "75% full" means nothing until we know
    75% of what, and a wrong denominator mis-scales every number on the gauge.

    (The design's second rung - learning the ceiling from the server's own
    HTTP 400 "model maximum context length: N" - belongs to step 2 and is
    deliberately not implemented here.)
    """
    try:
        cfg: Dict[str, Any] = config if isinstance(config, dict) else {}
        s = settings or resolve_settings(cfg)
        if s.ceiling_tokens > 0:
            return s.ceiling_tokens, "config"
        num_ctx = _as_int(cfg.get("ollama_num_ctx"), 0, minimum=1)
        if num_ctx > 0:
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
        ceiling, source = resolve_ceiling_tokens(config, s)
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
            "bytes_history": int(measurement.history_bytes),
            "bytes_loop": int(measurement.loop_bytes),
            "bytes_human": humanize_bytes(measurement.total_bytes),
            "tokens_estimated": int(measurement.tokens_estimated),
            "tokens_are_estimated": True,
            "ceiling_tokens": int(measurement.ceiling_tokens),
            "ceiling_source": str(measurement.ceiling_source),
            "ratio": round(float(measurement.ratio), 6),
            "zone": str(measurement.zone),
            "messages": int(measurement.messages_count),
            "loop_messages": int(measurement.loop_messages),
            "label": str(label or ""),
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
        )
        with self._cond:
            self._measured += 1
            self._last = measurement
        if settings.log_each:
            print(format_log_line(measurement, sample.label))
        if settings.gauge_enabled:
            payload = gauge_payload(measurement, settings, sample.label)
            payload["source"] = sample.source or "model"
            publish_gauge(sample.user_id, payload)

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
        )
    except Exception:  # noqa: BLE001
        return False
    return (meter or METER).submit(sample)
