# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""
agent/self_healing.py — Self-aware, NEVER-HANGING, self-healing resilience for
Tlamatini's Multi-Turn model steps.

REDESIGN (Angela, 2026-07-06 — NOT a patch, and NOT "retry the same call"):

The failure that must NEVER happen again: ONE model call hung for 120 s, threw
out of the whole 4096-turn loop, discarded every agent that had already run, and
the chain LIED ("no tools were invoked"). Retrying the SAME hanging call is
useless — it just hangs again.

The correct behaviour, exactly as Angela specified:

  • Tlamatini MUST NOT HANG. Every model call runs under a WATCHDOG — if it does
    not answer within a bounded time, the call is ABANDONED (a daemon thread we
    stop waiting on) and she immediately moves on. She never blocks forever.

  • On each failure/timeout she switches to a genuinely DIFFERENT TACTIC to get
    the job done (normal → trim context → minimal request → drop-tools summary →
    patient retry …, then cycles), and she ANNOUNCES the new tactic to the user
    in the first person, live, as it happens — the user SEES the tactic change.

  • She keeps trying, tactic after tactic, up to her full turn budget (4096) and
    NEVER gives up on her own.

  • The ONLY thing that stops her is the USER (the Cancel button). Cancellation
    is checked every 0.25 s — even mid-hang, even on turn 3982. On cancel she
    finishes gracefully from the work already done (Create Flow button intact),
    never a lie, never a discarded run.

Mid-run first-person notifications are pushed to the browser through a
StatusBroadcaster the consumer registers per request (the same
run_coroutine_threadsafe bridge the Ask-Execs broker uses), so they render in
the chat live, as they happen.
"""

from __future__ import annotations

import os
import queue
import random
import threading
import time
from typing import Any, Callable, List, Optional, Tuple

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage



# ── DEMO fault injection (env-controlled; OFF in normal operation) ──────────
# Lets us deliberately CAUSE real failures so the recovery ladder + user
# notifications are exercised end-to-end (Angela wants to SEE real fails and
# Tlamatini announcing new tactics + retrying). Controlled entirely by env:
#   TLAMATINI_SELF_HEAL_FAULT_RATE = 0..1  probability a model STEP's FIRST
#                                          attempt is forced to fail.
#   TLAMATINI_SELF_HEAL_FAULT_MODE = error | hang | mix  (default mix)
# Rate 0 (the default) => no injection, zero effect on production.
def _fault_config() -> Tuple[float, str]:
    try:
        rate = float(os.environ.get("TLAMATINI_SELF_HEAL_FAULT_RATE", "0") or "0")
    except ValueError:
        rate = 0.0
    mode = (os.environ.get("TLAMATINI_SELF_HEAL_FAULT_MODE", "mix") or "mix").lower()
    return max(0.0, min(1.0, rate)), mode


# ── Transient-error classification ──────────────────────────────────────────
# A transient error is a network/backend blip. A non-transient error (a real
# bug: bad schema, KeyError, ...) is NOT masked behind tactic-switching — it is
# surfaced immediately so it can be fixed.
_TRANSIENT_MARKERS = (
    "timed out", "timeout", "read timed out", "read timeout", "connection",
    "reset", "econnreset", "temporarily", "eof occurred", "max retries",
    "connection aborted", "connection refused", "broken pipe", "502", "503",
    "504", "500 internal", "overloaded", "rate limit", "429",
    "too many requests", "service unavailable", "bad gateway", "gateway time",
    "remotedisconnected", "incompleteread", "temporarily unavailable",
    "connection error", "httpcore", "readtimeout", "connecttimeout",
    "apiconnection", "apitimeout", "502 bad", "503 service",
)


def is_transient_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(m in text for m in _TRANSIENT_MARKERS)


def _cancelled_for(user_id: Any = None, run_epoch: Optional[int] = None) -> bool:
    """Was THIS run cancelled?

    Delegates to ``agent/cancellation.py``'s PER-RUN EPOCH LATCH (2026-07-14). The
    old code read a bare process-global boolean — which the cancel handler itself
    lowered again a few milliseconds after raising it (consumers Step 8) — so this
    predicate answered ``False`` for the whole life of a cancelled run, the
    ``user_cancelled`` stop was never raised, and the tactic ladder ran forever
    while re-arming the browser's busy UI. The latch cannot be lowered, so a
    cancelled run now stays cancelled.

    ``user_id``/``run_epoch`` of ``None`` falls back to the legacy boolean, so
    callers (and unit tests) that never learned a run identity behave as before.
    """
    from .cancellation import is_generation_cancelled
    try:
        return bool(is_generation_cancelled(user_id, run_epoch))
    except Exception:  # noqa: BLE001 — a cancellation probe must never crash a model step
        return False


def _cancelled() -> bool:
    """Legacy, identity-less cancellation probe (the raw boolean)."""
    return _cancelled_for(None, None)


# ── StatusBroadcaster: mid-run first-person notifications to the user ────────
# The executor runs in a sync worker thread, so it cannot broadcast to the
# WebSocket directly. The consumer registers a fire-and-forget ``emit(text)``
# (which schedules a Tlamatini ``agent_message`` onto its event loop) keyed by
# the conversation user id; the executor calls ``notify_user`` from its thread.
_STATUS_BROADCASTERS: "dict[Any, Callable[[str], None]]" = {}
_STATUS_LOCK = threading.Lock()


def register_status_broadcaster(user_id: Any, emit: Callable[[str], None]) -> None:
    if user_id is None:
        return
    with _STATUS_LOCK:
        _STATUS_BROADCASTERS[user_id] = emit


def unregister_status_broadcaster(user_id: Any, emit: "Callable[[str], None] | None" = None) -> None:
    """Remove the status emitter for ``user_id``. Pass the SPECIFIC ``emit`` this request
    registered so a finished request's teardown does not pop a concurrent same-user
    request's live emitter (two browser tabs share the user id). (re-audit [2])"""
    with _STATUS_LOCK:
        if emit is not None and _STATUS_BROADCASTERS.get(user_id) is not emit:
            return
        _STATUS_BROADCASTERS.pop(user_id, None)


def notify_user(user_id: Any, text: str) -> None:
    """Push a first-person status line to the user's chat. Called from the
    executor worker thread — must NEVER raise into the caller."""
    if user_id is None:
        return
    with _STATUS_LOCK:
        emit = _STATUS_BROADCASTERS.get(user_id)
    if emit is None:
        return
    try:
        emit(text)
    except Exception:
        pass


# ── Watchdog: run a blocking call WITHOUT ever hanging on it ─────────────────
def _run_with_watchdog(fn: Callable[[], Any], timeout: float, poll: float = 0.25,
                       cancelled: Callable[[], bool] = _cancelled,
                       ) -> Tuple[str, Any]:
    """Run ``fn()`` in a daemon thread and wait at most ``timeout`` seconds.

    Returns ``(status, payload)``:
      ("ok", result)       — fn returned in time.
      ("error", exc)       — fn raised.
      ("timeout", None)    — fn did not answer in time; the thread is ABANDONED
                             (still running as a daemon, but we no longer wait on
                             it — this is what guarantees Tlamatini never hangs).
      ("cancelled", None)  — the USER cancelled while we were waiting.

    Cancellation is polled every ``poll`` seconds, so a user Cancel is honoured
    within a quarter-second even while a model call is stuck.
    """
    result_q: "queue.Queue[Tuple[str, Any]]" = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result_q.put(("ok", fn()))
        except BaseException as exc:  # noqa: BLE001 — capture everything, never crash the thread host
            try:
                result_q.put(("error", exc))
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()

    waited = 0.0
    while waited < timeout:
        if cancelled():
            return ("cancelled", None)
        try:
            outcome = result_q.get(timeout=poll)
        except queue.Empty:
            waited += poll
            continue
        # The call came back (ok OR error) — but the user may have cancelled in that
        # same instant. On this path ``result_q.get`` returns immediately, so the
        # ``cancelled()`` probe at the top of the loop is SKIPPED entirely. Without
        # this second probe a cancel-adjacent error is handed straight to the
        # transient classifier and retried as if nothing had happened. (2026-07-14)
        if cancelled():
            return ("cancelled", None)
        return outcome
    return ("timeout", None)


# ── Graceful stop signals ───────────────────────────────────────────────────
class ModelStepUnrecoverable(Exception):
    """Raised only when Tlamatini must stop chasing a single model step —
    because the USER cancelled, or (backstop) an absurd number of distinct
    tactics were exhausted. The caller then assembles the answer deterministically
    from the work already done; the run is NEVER silently discarded."""

    def __init__(self, reason: str, attempts: int, tactics_tried: List[str],
                 last_exc: Optional[BaseException] = None):
        self.reason = reason              # "user_cancelled" | "exhausted"
        self.attempts = attempts
        self.tactics_tried = list(tactics_tried)
        self.last_exc = last_exc
        super().__init__(f"{reason} after {attempts} attempt(s) {tactics_tried}: {last_exc}")


def trim_messages(messages: List[BaseMessage], keep_tail: int) -> List[BaseMessage]:
    """Leaner request: keep the leading SystemMessage(s) + the LAST ``keep_tail``
    messages. An oversized accumulated context is a common cause of cloud stalls,
    so trimming is a genuinely different tactic. The tail is repaired so it never
    starts on an orphaned ToolMessage (schema-invalid without its tool_call)."""
    if len(messages) <= keep_tail + 2:
        return list(messages)
    system = [m for m in messages[:3] if isinstance(m, SystemMessage)]
    tail = list(messages[-keep_tail:])
    while tail and isinstance(tail[0], ToolMessage):
        tail = tail[1:]
    return system + tail


class SelfHealingInvoker:
    """Drives ONE model step to completion through an ESCALATING, CYCLING ladder
    of distinct tactics, each under a watchdog so she never hangs, each announced
    to the user. Only success or a USER cancel ends it (a very high backstop cap
    guards against a literal infinite loop)."""

    def __init__(self, *, user_id: Any = None, plain_llm: Any = None,
                 max_attempts: int = 4096, attempt_timeout: float = 80.0,
                 run_user_id: Any = None, run_epoch: Optional[int] = None):
        self.user_id = user_id
        # This run's CANCELLATION IDENTITY (2026-07-14). Both default to None, which
        # falls back to the legacy boolean — so every existing construction (and the
        # unit tests) keep working unchanged. When they ARE set, a Cancel latches
        # this run's epoch permanently and the ladder below stops for good.
        self.run_user_id = run_user_id
        self.run_epoch = run_epoch
        self.plain_llm = plain_llm                 # tool-less LLM for the summary tactic
        self.max_attempts = max(1, int(max_attempts))
        # Env override (used by the visible self-healing demo to shorten the
        # watchdog so injected hangs are abandoned fast).
        _env_to = os.environ.get("TLAMATINI_LLM_STEP_TIMEOUT")
        if _env_to:
            try:
                attempt_timeout = float(_env_to)
            except ValueError:
                pass
        # Floor prevents an absurdly-low watchdog in production; low enough to be
        # unit-testable.
        self.attempt_timeout = max(2.0, float(attempt_timeout))
        self.recovery_events: List[str] = []       # transcript of what she went through
        self.recovered = False                     # True if any tactic beyond the first worked

    def _is_cancelled(self) -> bool:
        """Did the USER cancel THIS run? (per-run epoch latch, boolean fallback)"""
        return _cancelled_for(self.run_user_id, self.run_epoch)

    def _announce(self, text: str) -> None:
        self.recovery_events.append(text)
        notify_user(self.user_id, text)

    def _inject_fault(self, thunk: Callable[[], Any], timeout: float, name: str
                      ) -> Tuple[Callable[[], Any], str]:
        """Env-controlled DEMO fault: with probability RATE, replace the call
        with a real failure so recovery is exercised. No-op when RATE is 0."""
        rate, mode = _fault_config()
        if rate <= 0.0 or random.random() >= rate:
            return thunk, name
        pick = mode if mode in ("error", "hang") else random.choice(("error", "hang"))
        if pick == "hang":
            def _faulty_hang():
                time.sleep(timeout + 5)   # exceeds the watchdog → abandoned
                return None
            return _faulty_hang, name + "+injected-hang"

        def _faulty_error():
            raise TimeoutError("INJECTED transient network fault (self-healing demo)")
        return _faulty_error, name + "+injected-error"

    def _tactic(self, attempt: int, bound_llm: Any, messages: List[BaseMessage]
                ) -> Tuple[str, str, Callable[[], Any], float]:
        """Return the (name, human_description, call_thunk, timeout) for this
        attempt. Attempt 1 is the plain request. The EARLY recovery tactics are
        tool-bound RETRIES (so a transient blip clears WITHOUT losing the
        task — tools stay available and the agent still runs); only as a LAST
        resort does she drop the tools to summarize. Cycles so she never gives
        up."""
        t = self.attempt_timeout
        cycle = (attempt - 1) % 6
        if cycle == 0:
            return ("normal", "trying the full request again",
                    lambda: bound_llm.invoke(messages), t)
        if cycle == 1:
            # Same tool-bound request — a transient blip usually clears on a
            # plain retry, and this PRESERVES tool-calling so the task continues.
            return ("retry", "retrying the same request — tools still available",
                    lambda: bound_llm.invoke(messages), t)
        if cycle == 2:
            return ("patient-retry", "waiting a moment, then retrying with more patience",
                    lambda: bound_llm.invoke(messages), t + 30)
        if cycle == 3:
            lean = trim_messages(messages, keep_tail=12)
            return ("trim-context",
                    "trimming my context to the essentials and retrying — tools still available",
                    lambda: bound_llm.invoke(lean), t)
        if cycle == 4:
            tiny = trim_messages(messages, keep_tail=6)
            return ("minimal",
                    "stripping to a MINIMAL request — tools still available",
                    lambda: bound_llm.invoke(tiny), t)
        if self.plain_llm is not None:
            summ = trim_messages(messages, keep_tail=8) + [HumanMessage(content=(
                "Summarize for the user, truthfully and concisely, what was accomplished "
                "from the tool results above. Do NOT call any tools."
            ))]
            return ("plain-summary",
                    "as a LAST resort, dropping the tools and summarizing what I already gathered",
                    lambda: self.plain_llm.invoke(summ), t)
        return ("patient-retry", "retrying the full request",
                lambda: bound_llm.invoke(messages), t + 30)

    def invoke(self, bound_llm: Any, messages: List[BaseMessage], *, label: str) -> Any:
        tactics_tried: List[str] = []
        last_exc: Optional[BaseException] = None

        for attempt in range(1, self.max_attempts + 1):
            if self._is_cancelled():
                self._announce("🛑 You cancelled — stopping here and keeping everything I already did.")
                raise ModelStepUnrecoverable("user_cancelled", attempt, tactics_tried, last_exc)

            name, how, thunk, timeout = self._tactic(attempt, bound_llm, messages)

            # DEMO fault injection (env-controlled, OFF in production): force the
            # FIRST attempt of some steps to fail for REAL — a hang the watchdog
            # must abandon, or a transient error — so the recovery ladder + the
            # user-facing tactic notifications are exercised end-to-end.
            if attempt == 1:
                thunk, name = self._inject_fault(thunk, timeout, name)

            # Announce every attempt after the first, so the user SEES the tactic
            # change and knows Tlamatini is actively working, not hung.
            if attempt > 1:
                self._announce(
                    f"🔁 Tactic #{attempt} while {label} — {how}. "
                    "I will NOT hang; only you can stop me (with Cancel button)."
                )

            status, payload = _run_with_watchdog(thunk, timeout, cancelled=self._is_cancelled)

            # ── A CANCEL BEATS EVERY OTHER OUTCOME (Angela, 2026-07-14) ──
            # Checked here — BEFORE the ok/timeout/error branches and BEFORE any
            # _announce() — because that ordering is exactly what was broken:
            #   * the "timeout" branch announced a new tactic and `continue`d WITHOUT
            #     ever consulting cancellation. That classification-free path (not the
            #     transient classifier) was the real engine of the endless post-cancel
            #     tactic storm.
            #   * an error landing just after a Cancel would otherwise go to
            #     is_transient_error() and be retried as a "network blip".
            #   * announcing first would leak one more "🔁 Tactic #…" frame to the
            #     browser — the frame that re-armed the Cancel button by itself.
            if self._is_cancelled():
                self._announce("🛑 You cancelled — stopping here and keeping everything I already did.")
                raise ModelStepUnrecoverable("user_cancelled", attempt, tactics_tried, last_exc)

            if status == "ok":
                if attempt > 1:
                    self.recovered = True
                    self._announce(f"✅ Tactic '{name}' worked — continuing the run right where I left off.")
                return payload

            if status == "cancelled":
                self._announce("🛑 You cancelled — stopping here and keeping everything I already did.")
                raise ModelStepUnrecoverable("user_cancelled", attempt, tactics_tried, last_exc)

            tactics_tried.append(f"{attempt}:{name}")

            if status == "timeout":
                self._announce(
                    f"⏱️ Tactic '{name}' was taking too long ({int(timeout)}s) — I'm ABANDONING that "
                    "call so I never hang, and switching to a different tactic."
                )
                continue

            # status == "error"
            exc = payload
            last_exc = exc
            if not is_transient_error(exc):
                # A real bug, not a network blip — surface it so it gets fixed,
                # do not loop forever on a deterministic failure.
                raise exc
            self._announce(
                f"⚠️ Tactic '{name}' hit a transient network error ({type(exc).__name__}) — "
                "switching to a different tactic."
            )
            self._interruptible_sleep(min(2 ** (attempt % 4), 8))

        # Backstop only — realistically the user cancels long before this.
        raise ModelStepUnrecoverable("exhausted", self.max_attempts, tactics_tried, last_exc)

    def _interruptible_sleep(self, seconds: float) -> None:
        slept = 0.0
        while slept < seconds:
            if self._is_cancelled():
                return
            time.sleep(0.25)
            slept += 0.25


def recovery_preamble(events: List[str]) -> str:
    """Render the recovery transcript into a compact, honest banner Tlamatini
    prepends to her final answer, so the user ALWAYS knows what she went through.
    Returns '' when nothing went wrong."""
    if not events:
        return ""
    lines = "\n".join(f"- {e}" for e in events)
    return (
        "SELF-HEALING NOTE — I hit trouble during this run and worked through it:\n"
        f"{lines}\n\n"
    )
