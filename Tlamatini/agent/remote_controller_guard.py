# Tlamatini — Created by Angela López Mendoza · @angelahack1
"""Account-scoped ownership shared by desktop chat and Remote-Controller.

The chat executor, cancellation epoch and permission broker are keyed by account.
One active owner keeps a second connection from replacing those live identities.
This module deliberately imports neither Django nor the consumer.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_owners: dict[int, tuple[object, str]] = {}
_chat_loop = None


def register_chat_loop(loop) -> None:
    """Remember the ASGI loop that owns the desktop channel-layer queues."""
    global _chat_loop
    with _lock:
        _chat_loop = loop


def chat_loop():
    with _lock:
        loop = _chat_loop
    return loop if loop is not None and not loop.is_closed() and loop.is_running() else None


def reserve_chat(user_id: int, owner: object) -> bool:
    """Reserve preparation for a remote chat without starting an execution."""
    with _lock:
        if user_id in _owners:
            return False
        _owners[user_id] = (owner, "reserved")
        return True


def claim_chat(user_id: int, owner: object) -> bool:
    """Claim execution once, optionally consuming this owner's reservation."""
    with _lock:
        previous = _owners.get(user_id)
        if previous is not None and not (
            previous[0] is owner and previous[1] == "reserved"
        ):
            return False
        _owners[user_id] = (owner, "running")
        return True


def release_chat(user_id: int, owner: object) -> None:
    """Only the current owner can release an account."""
    with _lock:
        previous = _owners.get(user_id)
        if previous is not None and previous[0] is owner:
            del _owners[user_id]


def chat_busy(user_id: int) -> bool:
    with _lock:
        return user_id in _owners


def owns_chat(user_id: int, owner: object) -> bool:
    with _lock:
        previous = _owners.get(user_id)
        return previous is not None and previous[0] is owner
