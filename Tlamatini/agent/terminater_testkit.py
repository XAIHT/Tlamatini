# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Shared helpers for the Terminater test suites (not a test module itself).

The engine / ConPTY / text modules live LOOSE in ``agents/terminater/`` and are loaded
BY PATH by ``terminal_hub.load_engine()``; the suites go through the same loader so they
test the one definition the web process, the pool agent and the Prompt Flow Panel share.
"""
from __future__ import annotations

import sys
import time
from typing import Any, Callable

from . import terminal_hub

IS_WINDOWS = sys.platform == "win32"


def engine() -> Any:
    return terminal_hub.load_engine()


def tx() -> Any:
    return engine()._tx


def cp() -> Any:
    return engine()._cp


def conpty_ok() -> bool:
    try:
        return bool(IS_WINDOWS and cp().conpty_available())
    except Exception:  # noqa: BLE001
        return False


class FastTyping:
    """Context manager: shrink every typing delay (the 30 ms floor scales too).

    The scale is a module global of ``terminater_text`` that nothing at run time can reach
    (no API, no config, no LLM) -- it exists so a 250-test suite does not take an hour.
    """

    def __init__(self, scale: float = 0.04) -> None:
        self.scale = scale
        self.saved = 1.0

    def __enter__(self) -> "FastTyping":
        mod = tx()
        self.saved = mod.TEST_TIME_SCALE
        mod.TEST_TIME_SCALE = self.scale
        return self

    def __exit__(self, *exc: Any) -> None:
        tx().TEST_TIME_SCALE = self.saved


def wait_until(predicate: Callable[[], Any], timeout: float = 30.0, interval: float = 0.05) -> Any:
    """Poll ``predicate`` until it returns something truthy; return it (or None on timeout)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
        except Exception:  # noqa: BLE001
            value = None
        if value:
            return value
        time.sleep(interval)
    return None


def fresh_hub(max_terminals: int = 6, hang_seconds: float = 6.0) -> Any:
    """A private hub (never the process-wide one), so suites cannot disturb each other."""
    return engine().TerminalHub(max_terminals=max_terminals, hang_seconds=hang_seconds)


def run_ok(result: dict) -> bool:
    return bool(result) and result.get("ok") is not False and result.get("status") not in {
        "refused", "error", "unavailable"}
