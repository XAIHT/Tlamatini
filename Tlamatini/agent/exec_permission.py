# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# agent/exec_permission.py
"""Ask-Execs permission broker.

Bridges the **synchronous** Multi-Turn tool executor (which runs in a worker
thread via ``sync_to_async(ask_rag, thread_sensitive=False)``) with the
**asynchronous** WebSocket consumer, so the executor can BLOCK on a per-tool
permission prompt rendered in the browser before it runs a state-changing
Tool / MCP / Agent.

Flow:

1. The consumer creates one :class:`ExecPermissionBroker` per request and
   registers it under the user's id with :func:`register_broker`. Its
   ``emit`` callback schedules a WebSocket ``exec_permission_request`` frame
   onto the consumer's event loop (``asyncio.run_coroutine_threadsafe``).
2. The executor thread calls :meth:`ExecPermissionBroker.request_permission`
   with a detail dict. That emits the frame and BLOCKS on a
   :class:`threading.Event` until the browser answers, the request is
   cancelled, or the broker is closed.
3. The browser shows the modal dialog and sends back an
   ``exec-permission-response`` frame. The consumer routes it to
   :func:`resolve_permission`, which sets the event and unblocks the executor.

Safety contract (mirrors the orphan reaper's "never break the chat path"):

- Blocking is cancel-aware: it polls ``global_state['cancel_generation']`` on
  a short tick so a mid-flight Cancel never deadlocks the worker thread.
- If the emit itself fails (loop gone, socket closed), the request resolves to
  ``"deny"`` — when Ask Execs is on we must never run an unconfirmed
  state-changing tool just because the round-trip broke.
- :meth:`close` resolves every still-pending request to ``"deny"`` so a
  disconnect / request teardown can never leave the executor blocked forever.
"""

import logging
import threading
import uuid
from typing import Any, Callable, Dict, Optional

from .global_state import global_state

logger = logging.getLogger(__name__)

# Registry of live brokers keyed by the consumer's user id. Exactly one broker
# is active per in-flight request (the chain runs under the consumer's
# rag_lock), so a flat dict keyed by user id is sufficient and lets the
# ``exec-permission-response`` handler find the right broker without threading
# a token through the whole chain.
_REGISTRY_LOCK = threading.Lock()
_BROKERS: Dict[Any, "ExecPermissionBroker"] = {}


class _PendingPermission:
    __slots__ = ("event", "decision")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.decision: Optional[str] = None


class ExecPermissionBroker:
    """One-request bridge for the Ask-Execs permission prompt."""

    # Poll granularity while blocked, so a Cancel (or broker close) can unblock
    # the worker thread promptly without busy-waiting.
    _WAIT_TICK_SECONDS = 0.25

    def __init__(self, emit: Callable[[Dict[str, Any]], None]):
        self._emit = emit
        self._lock = threading.Lock()
        self._pending: Dict[str, _PendingPermission] = {}
        self._closed = False
        # When the user unchecks "Ask Execs" WHILE this run is in flight, the
        # consumer flips this flag via :meth:`set_auto_proceed`. From then on
        # every tool auto-proceeds for the REMAINDER of the request (no prompt
        # emitted). Re-checking the box flips it back so prompting resumes.
        self._auto_proceed = False

    def request_permission(self, detail: Dict[str, Any]) -> str:
        """Emit a permission request and BLOCK until answered.

        Returns ``"proceed"`` or ``"deny"``. Always returns ``"deny"`` on any
        failure / cancel / close so an unconfirmed execution never slips
        through while Ask Execs is enabled. If the user relaxed the gate
        mid-run (``_auto_proceed``), returns ``"proceed"`` immediately without
        emitting a prompt.
        """
        request_id = uuid.uuid4().hex
        pending = _PendingPermission()
        with self._lock:
            if self._closed:
                return "deny"
            if self._auto_proceed:
                # User turned Ask Execs off mid-run — stop prompting for the
                # rest of this request and let the tool run.
                return "proceed"
            self._pending[request_id] = pending

        payload = dict(detail or {})
        payload["request_id"] = request_id
        try:
            self._emit(payload)
        except Exception as exc:  # noqa: BLE001 — emit must never raise into executor
            logger.error("[ExecPermissionBroker] emit failed (%s); denying.", exc)
            with self._lock:
                self._pending.pop(request_id, None)
            return "deny"

        try:
            while True:
                if pending.event.wait(self._WAIT_TICK_SECONDS):
                    break
                # Wake periodically to honour a mid-flight Cancel or a close.
                if global_state.get_state("cancel_generation"):
                    logger.info("[ExecPermissionBroker] cancel detected; denying %s", request_id)
                    return "deny"
                with self._lock:
                    if self._closed:
                        return "deny"
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

        return pending.decision or "deny"

    def resolve(self, request_id: str, decision: str) -> bool:
        """Resolve a pending request from the browser's response frame.

        Returns True if a matching pending request was found and resolved.
        """
        normalized = "proceed" if str(decision).strip().lower() == "proceed" else "deny"
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is None:
                return False
            pending.decision = normalized
            pending.event.set()
        return True

    def set_auto_proceed(self, enabled: bool) -> None:
        """Relax (``enabled=True``) or re-arm (``enabled=False``) the gate for
        the REMAINDER of this request.

        Called when the user toggles the "Ask Execs" checkbox WHILE the run is
        already executing. When relaxed, every subsequent
        :meth:`request_permission` returns ``"proceed"`` without emitting a
        prompt, and any prompt currently blocking the executor is resolved to
        ``"proceed"`` right away (so an open dialog stops blocking the chain).
        When re-armed, future tools prompt again. No-op once :meth:`close` has
        run — a torn-down request must never spring back to life.
        """
        with self._lock:
            if self._closed:
                return
            self._auto_proceed = bool(enabled)
            if not self._auto_proceed:
                return
            pending_items = list(self._pending.values())
        # Unblock anything already waiting as "proceed" (mirrors close(), which
        # unblocks pending as "deny"). Done outside the lock; setting the event
        # is thread-safe and request_permission re-checks under its own lock.
        for pending in pending_items:
            if pending.decision is None:
                pending.decision = "proceed"
            pending.event.set()

    def close(self) -> None:
        """Resolve every still-pending request to ``deny`` and stop accepting
        new ones. Idempotent."""
        with self._lock:
            self._closed = True
            pending_items = list(self._pending.values())
        for pending in pending_items:
            if pending.decision is None:
                pending.decision = "deny"
            pending.event.set()


def register_broker(key: Any, broker: ExecPermissionBroker) -> None:
    """Register ``broker`` under ``key`` (the user id). Any broker already
    registered under the same key is closed first so a stale request can never
    leave the executor blocked."""
    with _REGISTRY_LOCK:
        old = _BROKERS.get(key)
        _BROKERS[key] = broker
    if old is not None:
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass


def get_broker(key: Any) -> Optional[ExecPermissionBroker]:
    with _REGISTRY_LOCK:
        return _BROKERS.get(key)


def unregister_broker(key: Any) -> None:
    """Remove and close the broker registered under ``key`` (if any)."""
    with _REGISTRY_LOCK:
        broker = _BROKERS.pop(key, None)
    if broker is not None:
        try:
            broker.close()
        except Exception:  # noqa: BLE001
            pass


def resolve_permission(key: Any, request_id: str, decision: str) -> bool:
    """Route a browser ``exec-permission-response`` to the right broker."""
    broker = get_broker(key)
    if broker is None:
        return False
    return broker.resolve(request_id, decision)


def set_broker_auto_proceed(key: Any, auto_proceed: bool) -> bool:
    """Relax / re-arm the live broker registered under ``key`` mid-run.

    Called when the user toggles "Ask Execs" while a run is in flight. Returns
    True if a broker was found (a run gated by Ask Execs is executing), False
    otherwise (nothing to relax — e.g. the run started with Ask Execs off, so
    no broker was ever registered)."""
    broker = get_broker(key)
    if broker is None:
        return False
    broker.set_auto_proceed(auto_proceed)
    return True
