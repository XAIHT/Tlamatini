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
agent/cancellation.py — the PER-RUN cancellation latch.

THE BUG THIS EXISTS TO KILL (Angela, 2026-07-14):
--------------------------------------------------
Cancelling a Multi-Turn run did not cancel it. Tlamatini came back to life a few
seconds later, flipped the Send button back to "Cancel" by itself, and kept doing
that forever — every Cancel click just fed the loop.

Why: cancellation was ONE process-global BOOLEAN with a ~20-millisecond lifetime.
``consumers.py``'s ``cancel-current`` handler SET it (Step 1) and then CLEARED it
again (Step 8) a few milliseconds later — it had to, because ``setup_rag_chain()``
refuses to rebuild the chain while that boolean is up, and Step 9 rebuilds the
chain. ``rag/interface.py::ask_rag`` cleared it a SECOND time at the top of every
new request. Meanwhile the cancelled run was still ALIVE on its worker thread, and
its only cancellation observer (``self_healing._cancelled()``) polls that same
boolean every 0.25 s — so it read ``False`` for the rest of its life and NEVER
raised ``ModelStepUnrecoverable("user_cancelled")``. The Multi-Turn executor itself
(``mcp_agent.py``) contained ZERO cancellation reads, so tools kept firing too.

THE FIX — a LATCH, not a flag:
-------------------------------
Each request is given a monotonically-increasing **run epoch**, keyed PER USER.
Cancelling LATCHES that user's current epoch permanently:

    is_run_cancelled(uid, my_epoch)  ==  latched_epoch(uid) >= my_epoch

* A cancelled run stays cancelled **FOREVER** — the latch is never lowered, so
  neither Step 8 nor a new ``ask_rag`` can resurrect it (that was the whole bug).
* The user's **NEXT** run gets a strictly HIGHER epoch, so it is NOT cancelled and
  runs normally.
* ``clear_cancel_generation()`` clears ONLY the legacy boolean — Step 8 keeps
  working (the chain rebuild is not blocked), and the latch is untouched.

TWO NON-NEGOTIABLE INVARIANTS (do NOT "simplify" either one away):
------------------------------------------------------------------
1. **KEYED PER USER — never one process-global high-water mark.** ``global_state``
   is a single process-wide singleton and Tlamatini admits CONCURRENT runs
   (TeleTlamatini + a browser; two tabs). The codebase already had to key
   ``last_request_meta::<uid>`` per user for exactly this reason. A global
   ``cancelled_epoch >= epoch`` mark would let Angela's Cancel permanently kill a
   Telegram user's healthy in-flight run.
2. **A MISSING EPOCH MEANS "NOT CANCELLED" (fail-open).** ``run_epoch`` is plumbed
   through the chain payloads, and ``unified.py``'s payload rebuild uses a
   hardcoded whitelist (the drop-on-rebuild bug class that once broke
   ``exec_report_enabled``). If the key were ever dropped and a missing epoch meant
   "cancelled", EVERY request after the first-ever cancel would self-cancel on
   arrival. So ``is_run_cancelled(uid, None)`` is ALWAYS ``False``.

Stdlib + ``global_state`` only — no Django import — so this is safe to import from
the executor's worker thread and from unit tests.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from .global_state import global_state

# The legacy process-global boolean. STILL the source of truth for the chain-SETUP
# guards (consumers.setup_rag_chain / setup_contextual_rag_chain) and the streaming
# callbacks, which have no run identity. Kept deliberately.
_BOOL_KEY = "cancel_generation"

_lock = threading.Lock()


def _epoch_key(user_id: Any) -> str:
    return f"llm_run_epoch::{user_id}"


def _latch_key(user_id: Any) -> str:
    return f"llm_cancelled_epoch::{user_id}"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def begin_llm_run(user_id: Any) -> int:
    """Start a new run for ``user_id`` and return its epoch (1, 2, 3, …).

    Also lowers the legacy boolean, preserving the old
    ``clear_cancel_generation()``-at-the-top-of-``ask_rag`` behaviour. It NEVER
    touches the cancelled-epoch latch — that is the entire point: a brand-new run
    gets a HIGHER epoch than any latched one, so it is not cancelled, while every
    run that WAS cancelled stays cancelled forever.
    """
    with _lock:
        epoch = _as_int(global_state.get_state(_epoch_key(user_id))) + 1
        global_state.set_state(_epoch_key(user_id), epoch)
    global_state.set_state(_BOOL_KEY, False)
    return epoch


def current_run_epoch(user_id: Any) -> int:
    """The epoch of ``user_id``'s most recently started run (0 when unknown)."""
    return _as_int(global_state.get_state(_epoch_key(user_id)))


def cancelled_run_epoch(user_id: Any) -> int:
    """The highest epoch of ``user_id`` that has been cancelled (0 when none)."""
    return _as_int(global_state.get_state(_latch_key(user_id)))


def request_cancel_generation(user_id: Any = None) -> int:
    """The user pressed Cancel.

    Raises the legacy boolean (for the setup guards + streaming callbacks) AND
    permanently LATCHES this user's current run epoch, so the run that is executing
    RIGHT NOW can never be un-cancelled — not by Step 8's
    ``clear_cancel_generation()``, and not by the user typing a new message.

    ``user_id=None`` keeps only the legacy boolean, so any caller without a user
    identity behaves exactly as it did before.
    """
    global_state.set_state(_BOOL_KEY, True)
    if user_id is None:
        return 0
    with _lock:
        latched = max(
            _as_int(global_state.get_state(_latch_key(user_id))),
            _as_int(global_state.get_state(_epoch_key(user_id))),
        )
        global_state.set_state(_latch_key(user_id), latched)
    return latched


def clear_cancel_generation() -> None:
    """Lower the legacy boolean ONLY — the epoch latch is NEVER cleared here.

    ``consumers.py``'s ``cancel-current`` Step 8 must keep calling this so Step 9's
    blocking ``await self.setup_rag_chain()`` is not aborted by the setup guards
    (which read the boolean and would otherwise leave ``self.rag_chain = None``).
    Because the latch survives, the cancelled run stays cancelled anyway.
    """
    global_state.set_state(_BOOL_KEY, False)


def is_run_cancelled(user_id: Any, run_epoch: Optional[int]) -> bool:
    """Was THIS specific run cancelled? The single source of truth for the executor.

    Fail-open by design: an unknown/missing ``run_epoch`` is NOT cancelled (see
    invariant 2 in the module docstring) and any internal error returns False — a
    crash here must never break the chat path.
    """
    if run_epoch is None:
        return False
    try:
        epoch = int(run_epoch)
    except (TypeError, ValueError):
        return False
    if epoch <= 0:
        return False
    try:
        return cancelled_run_epoch(user_id) >= epoch
    except Exception:  # noqa: BLE001 — never raise into the chat path
        return False


def is_generation_cancelled(user_id: Any = None, run_epoch: Optional[int] = None) -> bool:
    """``is_run_cancelled(...)`` OR the legacy boolean.

    Used by the call sites that must honour BOTH shapes (the self-healing invoker,
    the Ask-Execs broker, the streaming callbacks, ``ask_rag``'s guards), so a
    caller that never learned its run epoch still behaves exactly as before.
    """
    if is_run_cancelled(user_id, run_epoch):
        return True
    try:
        return bool(global_state.get_state(_BOOL_KEY))
    except Exception:  # noqa: BLE001
        return False


def reset_for_tests(user_id: Any = None) -> None:
    """Clear the boolean and (optionally) one user's epoch + latch.

    Unit tests MUST call this in tearDown: the latch is a permanent high-water
    mark, so a test that cancels without resetting would leave every later test's
    run born-cancelled.
    """
    global_state.set_state(_BOOL_KEY, False)
    if user_id is not None:
        global_state.set_state(_epoch_key(user_id), 0)
        global_state.set_state(_latch_key(user_id), 0)
