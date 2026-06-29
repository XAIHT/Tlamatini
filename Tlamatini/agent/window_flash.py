# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# agent/window_flash.py
"""Flash the Tlamatini.exe console window's taskbar button + log an UPPERCASE
attention banner when a browser surface needs the user.

Why this exists
---------------
Page JavaScript inside ``agent_page.html`` / ``agentic_control_panel.html`` is
sandboxed: it CANNOT flash its own browser taskbar button (the same Windows
sandbox wall that ruled out OS toasts). But the Django process *is* the
``Tlamatini.exe`` that owns the console window, so it can call ``FlashWindowEx``
on its own HWND — the guaranteed Win10/11 "needs attention" taskbar highlight.

So the browser detects the event (an Ask-Execs approval prompt or a Notifier
notification), POSTs to ``/agent/flash_window/``, and this module flashes the
console taskbar button AND prints an uppercase banner naming the page that
needs attention — so the notice survives in ``tlamatini.log`` even when both the
browser and the console are minimized and unseen.

Fail-safe contract
-------------------
Nothing here ever raises into the request path: every Win32 call is guarded and
a failure is swallowed (a flash that crashes a request is worse than a missed
flash). Non-Windows hosts and windowless launches (pythonw / headless) degrade
gracefully to the log banner only.
"""
import os

# FlashWindowEx dwFlags (winuser.h)
_FLASHW_CAPTION = 0x00000001   # flash the window caption
_FLASHW_TRAY = 0x00000002      # flash the taskbar button
_FLASHW_ALL = _FLASHW_CAPTION | _FLASHW_TRAY  # caption + taskbar button

# Human-readable page labels (uppercased at banner-build time).
_PAGE_LABELS = {
    "agent_page.html": "agent_page.html (the Tlamatini chat)",
    "agentic_control_panel.html": (
        "agentic_control_panel.html (the Agentic Control Panel)"
    ),
}

# Reason -> uppercase banner line.
_REASON_LABELS = {
    "execution-approval": "AN EXECUTION APPROVAL (ASK-EXECS) IS PENDING",
    "notification": "A NOTIFIER NOTIFICATION HAS BEEN RAISED",
}


def _console_hwnd():
    """Return this process's console-window HWND, or ``None`` if there is no
    console (windowless launch / non-Windows / API failure)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleWindow.restype = wintypes.HWND
        hwnd = kernel32.GetConsoleWindow()
        return hwnd or None
    except Exception:
        return None


def flash_console_window(count: int = 5) -> bool:
    """Flash the Tlamatini.exe console taskbar button ``count`` times, then
    leave it highlighted until the window is next activated (the classic
    "application needs attention" orange highlight).

    Returns ``True`` if the flash was dispatched, ``False`` otherwise. Never
    raises.
    """
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD),
                ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        user32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
        user32.FlashWindowEx.restype = wintypes.BOOL

        info = FLASHWINFO(
            ctypes.sizeof(FLASHWINFO),
            hwnd,
            _FLASHW_ALL,        # caption + taskbar button
            max(1, int(count)),
            0,                  # 0 = default (cursor-blink) flash rate
        )
        user32.FlashWindowEx(ctypes.byref(info))
        return True
    except Exception:
        return False


def build_attention_banner(page: str, reason: str) -> str:
    """Build the UPPERCASE multi-line attention banner written to the log."""
    page_label = _PAGE_LABELS.get(page, page or "a Tlamatini page")
    reason_label = _REASON_LABELS.get(reason, "A TLAMATINI EVENT NEEDS YOU")
    bar = "!" * 72
    return (
        "\n" + bar + "\n"
        "  *** TLAMATINI NEEDS YOUR ATTENTION ***\n"
        f"  {reason_label}\n"
        f"  PLEASE RETURN TO {page_label.upper()}.\n"
        + bar
    )


def notify_attention(page: str, reason: str, count: int = 5) -> bool:
    """Flash the console taskbar button AND print the uppercase log banner.

    Returns ``True`` if the taskbar flash was dispatched (the banner is always
    printed regardless). Never raises into the caller.
    """
    flashed = False
    try:
        flashed = flash_console_window(count=count)
    except Exception:
        flashed = False
    try:
        # print() is tee'd to tlamatini.log process-wide by manage.py, so the
        # banner survives in the log even when no console is visible.
        print(build_attention_banner(page, reason), flush=True)
    except Exception:
        pass
    return flashed
