# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   ·   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner · do not remove (releases scrub the name automatically)
"""Per-line USER attribution for ``tlamatini.log`` (Angela, 2026-08-13).

WHY THIS EXISTS
---------------
Tlamatini serves SEVERAL logged-in users at once on the same machine — open a
session as ``angela`` and another as ``alice`` and both are served concurrently
by the same process, the same event loop and the same thread pool. Until this
module landed, ``tlamatini.log`` interleaved both users' work with **no way to
tell whose line was whose**: a Multi-Turn burst from alice and a RAG rebuild for
angela were one indistinguishable stream.

Every line that belongs to a user now carries a tiny prefix naming that user and
the turn (request) it came from:

    [a3] --- Message parsed: 'compile the report' ...
    [b1] --- [BINARY-GUARD] ENABLED - sampling 8192 bytes/file
    --- [WHO] a = angela (user id 1)          <- the one-time legend line

TWO HARD CONSTRAINTS, both from Angela, both honoured by construction
--------------------------------------------------------------------
1. **MINIMAL CHARACTERS.** The default tag is FIVE characters — ``[a3] `` — a
   one-letter user code plus the turn number, not a verbose
   ``[user=angela thread=Thread-42]`` preamble. Lines that belong to NO user
   (startup, the MCP servers, the reaper) get **no prefix at all**, so nothing
   is spent on them. Blank lines are never tagged either.
2. **MINIMAL CPU.** The prefix is rendered ONCE per (user, turn) and stored
   READY-TO-WRITE in a ``ContextVar``. The logging hot path therefore costs one
   ``ContextVar.get()`` plus one string concatenation — no formatting, no
   lookup, no lock, no ``inspect``, no thread scan, per line. When nothing is
   bound (the common case at startup) the tee pays a single ``is not None``
   test on a module global.

HOW THE IDENTITY TRAVELS
------------------------
``contextvars.ContextVar`` is the right primitive and ``threading.local`` is the
wrong one: ONE event-loop thread serves EVERY connected user, so a thread-local
would smear angela's identity over alice's coroutine. A ``ContextVar`` is scoped
to the asyncio task, which is exactly "one WebSocket connection / one request".
``asgiref``'s ``sync_to_async`` propagates the context into the worker thread,
so the whole synchronous Multi-Turn executor stays attributed for free.

Raw ``threading.Thread`` spawns (the self-healing watchdog, the Tier-2 reaper,
agent launchers) would otherwise start with an EMPTY context and lose the tag —
so ``install()`` also wraps ``Thread.start`` to run the thread body inside a
copy of the spawning context. That is precisely what asyncio and asgiref already
do; it is additive (a fresh thread has no context of its own to lose) and it is
what makes the attribution TOTAL instead of merely usual.

CONTRACT — do NOT weaken
------------------------
* **FAIL-OPEN, ALWAYS.** Every function swallows its own errors and degrades to
  "no tag". A logging decoration that can raise into a caller is infinitely
  worse than an untagged line — it could take down the chat path.
* **Stdlib only, and it imports nothing from ``agent.*``.** It is reachable from
  ``manage.py``'s tee, which runs BEFORE Django exists, and it must behave
  identically frozen and from source.
* **The tee is never imported by this module and this module is never imported
  by the tee.** Coupling is inverted: ``manage.py`` exposes an empty hook slot
  (``_USER_TAG_HOOK``) and ``install()`` fills it in when the Django app boots.
  A direct import either way would drag protobuf/gRPC (via ``agent/__init__``)
  into pre-Django startup, or hard-wire the tee to a module that may be absent.
* **ASCII only in the prefix.** The tee also writes to the Windows console,
  whose code page is cp1252; a non-ASCII prefix on the hot path is an encode
  error waiting to happen on every single line.

CONFIGURATION (``config.json``, all fail-open)
----------------------------------------------
``log_user_tags``               master switch, default ``true``
``log_user_tag_style``          ``"short"`` (default, ``[a3] ``) | ``"name"``
                                (``[angela#3] ``) | ``"off"``
``log_user_tag_thread_inherit`` default ``true`` — child threads inherit the tag
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
import threading

__all__ = [
    'STYLE_NAME',
    'STYLE_OFF',
    'STYLE_SHORT',
    'begin_turn',
    'bind',
    'current_tag',
    'install',
    'legend',
    'reset',
]

STYLE_SHORT = 'short'
STYLE_NAME = 'name'
STYLE_OFF = 'off'
_VALID_STYLES = (STYLE_SHORT, STYLE_NAME, STYLE_OFF)

#: The ready-to-write prefix for the CURRENT context, e.g. ``'[a3] '``.
#: Empty string == this line belongs to no particular user; write it bare.
_TAG: contextvars.ContextVar = contextvars.ContextVar('tlamatini_log_tag', default='')

_LOCK = threading.RLock()
_CODES: dict = {}          # user id -> short code ('a', 'b', ... 'u42')
_NAMES: dict = {}          # user id -> login name (for the legend)
_TURNS: dict = {}          # user id -> turn counter
_STYLE = None              # resolved once, lazily
_INSTALLED = False
_THREAD_PATCHED = False


# ---------------------------------------------------------------------------
# Configuration (stdlib-only; mirrors manage.py::_resolve_config_path exactly)
# ---------------------------------------------------------------------------

def _config_path() -> str:
    override = os.environ.get('CONFIG_PATH')
    if override:
        return override
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def _read_config() -> dict:
    try:
        with open(_config_path(), 'r', encoding='utf-8-sig') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_style() -> str:
    """Resolve the tag style ONCE. Any problem falls back to the default."""
    global _STYLE
    if _STYLE is not None:
        return _STYLE
    style = STYLE_SHORT
    try:
        config = _read_config()
        if not bool(config.get('log_user_tags', True)):
            style = STYLE_OFF
        else:
            raw = str(config.get('log_user_tag_style', STYLE_SHORT)).strip().lower()
            if raw in _VALID_STYLES:
                style = raw
    except Exception:
        style = STYLE_SHORT
    _STYLE = style
    return style


# ---------------------------------------------------------------------------
# User codes + the legend
# ---------------------------------------------------------------------------

def _code_for(user_id: int, username: str) -> str:
    """``1 -> 'a'``, ``2 -> 'b'`` … in first-seen order. Past 26 users, ``u<id>``.

    The FIRST time a user is seen, one legend line is printed so the reader
    never has to guess what ``[a3]`` means. That is one line per user per run —
    the whole cost of making a 5-character tag self-describing.
    """
    code = _CODES.get(user_id)
    if code is not None:
        return code
    announce = False
    with _LOCK:
        code = _CODES.get(user_id)
        if code is None:
            index = len(_CODES)
            code = chr(97 + index) if index < 26 else 'u%d' % user_id
            _CODES[user_id] = code
            _NAMES[user_id] = username
            announce = True
    if announce:
        try:
            # The legend is a statement ABOUT the tags, so it must not wear one
            # — not even the tag of whoever happened to be bound when this new
            # user was first seen. Clear for the duration of the print, restore
            # after. First sight per user only, so the hot path never pays.
            token = _TAG.set('')
            try:
                print('--- [WHO] %s = %s (user id %d)' % (code, username, user_id))
            finally:
                _TAG.reset(token)
        except Exception:
            pass
    return code


def legend() -> dict:
    """``{user_id: (code, username)}`` — every user seen so far this run."""
    with _LOCK:
        return {uid: (code, _NAMES.get(uid, '')) for uid, code in _CODES.items()}


def _render(user_id: int, username: str, turn: int) -> str:
    style = _resolve_style()
    if style == STYLE_OFF:
        return ''
    if style == STYLE_NAME:
        return '[%s#%d] ' % (username, turn)
    return '[%s%d] ' % (_code_for(user_id, username), turn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bind(user_id, username: str = '', turn=None):
    """Attribute every log line written from HERE ON in this context to a user.

    Returns a token for :func:`reset` (or ``None`` if anything went wrong).
    Passing ``user_id=None`` clears the attribution — the correct thing for an
    anonymous or system context, which then writes bare, untagged lines.
    """
    try:
        if user_id is None:
            return _TAG.set('')
        uid = int(user_id)
        name = username or _NAMES.get(uid) or ('u%d' % uid)
        if turn is None:
            turn = _TURNS.get(uid, 1)
        return _TAG.set(_render(uid, name, int(turn)))
    except Exception:
        try:
            return _TAG.set('')
        except Exception:
            return None


def begin_turn(user_id, username: str = ''):
    """Start a NEW turn (request) for a user and bind to it.

    The turn number is what separates two concurrent requests of the SAME user
    — e.g. two browser tabs — so ``[a7]`` and ``[a8]`` never blur together.
    """
    try:
        uid = int(user_id)
    except Exception:
        return bind(None)
    try:
        with _LOCK:
            turn = _TURNS.get(uid, 0) + 1
            _TURNS[uid] = turn
            if username:
                _NAMES.setdefault(uid, username)
        return bind(uid, username, turn)
    except Exception:
        return bind(uid, username)


def current_tag() -> str:
    """The ready-to-write prefix for this context. THE logging hot path."""
    try:
        return _TAG.get()
    except Exception:
        return ''


def reset(token) -> None:
    """Undo a :func:`bind` / :func:`begin_turn`. Never raises."""
    if token is None:
        return
    try:
        _TAG.reset(token)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Installation — hook the tee, make threads inherit
# ---------------------------------------------------------------------------

def _install_tee_hook() -> bool:
    """Fill ``manage.py``'s ``_USER_TAG_HOOK`` slot with :func:`current_tag`.

    Inverted coupling on purpose (see the module docstring): the tee never
    imports us, we install ourselves into it. ``manage.py`` runs as
    ``__main__`` in BOTH source and frozen mode, so that is where we look. If
    the slot is absent (a bare ``daphne`` launch, a unit test), we simply do
    nothing and every line stays untagged — fail-open.
    """
    try:
        main = sys.modules.get('__main__')
        if main is not None and hasattr(main, '_USER_TAG_HOOK'):
            main._USER_TAG_HOOK = current_tag
            return True
    except Exception:
        pass
    return False


def _install_thread_inheritance() -> bool:
    """Make a child thread inherit the spawning context's user tag.

    A brand-new thread starts with an EMPTY context, so the self-healing
    watchdog, the Tier-2 reaper and every agent launcher would drop the tag
    exactly when the user most wants to follow their own request. Copying the
    context at ``start()`` is what asyncio and asgiref already do for their own
    hand-offs; ``copy_context()`` returns a FRESH object per call, so two
    threads can never fight over one context. Idempotent and fail-open.
    """
    global _THREAD_PATCHED
    if _THREAD_PATCHED:
        return True
    try:
        if not bool(_read_config().get('log_user_tag_thread_inherit', True)):
            return False
        original_start = threading.Thread.start
        if getattr(original_start, '_tlamatini_ctx_wrapped', False):
            _THREAD_PATCHED = True
            return True

        def start(self):  # noqa: ANN001 - stdlib signature
            try:
                context = contextvars.copy_context()
                inner_run = self.run
                self.run = lambda: context.run(inner_run)
            except Exception:
                pass  # never block a thread from starting
            return original_start(self)

        start._tlamatini_ctx_wrapped = True
        threading.Thread.start = start
        _THREAD_PATCHED = True
        return True
    except Exception:
        return False


def install() -> bool:
    """Wire up per-line user attribution. Idempotent, fail-open, cheap.

    Called automatically on import, so ``import agent.log_identity`` is all any
    caller ever needs to do.
    """
    global _INSTALLED
    if _INSTALLED:
        return True
    _INSTALLED = True
    hooked = _install_tee_hook()
    _install_thread_inheritance()
    return hooked


install()
