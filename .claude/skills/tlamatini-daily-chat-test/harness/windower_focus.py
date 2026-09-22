# Tlamatini Author Banner - do not remove
r"""
THE WINDOW IS BROUGHT FORWARD BY **WINDOWER**, TLAMATINI'S OWN AGENT
===================================================================

WHY THIS EXISTS (2026-09-22)
    A visible test is only worth the photo it produces, and a photo is only
    worth anything if it SHOWS what the test claims. The first run of
    `context_restore_spinner_visible.py` proved the fix in the DOM - twelve
    consecutive samples of `spinner=True` read straight out of the live page -
    and then Shoter photographed a desktop where the browser was buried behind
    the server console the harness had just launched. The measurement was true;
    the evidence was worthless.

    So before every shot the harness FOCUSES the browser with Windower and then
    VERIFIES, from Windower's own `list` output, that the window really is the
    foreground one. If it cannot be verified the harness says so instead of
    shooting a picture that proves nothing.

    Same discipline as `shoter_shot.py`: the work is done BY the agent, not by
    a hand-rolled ctypes call, so using it is also the test of it.

FAIL-OPEN
    `focus()` returns False and SAYS SO. It never pretends. A caller that
    cannot get the window forward should refuse to present its photo as
    evidence rather than quietly present a photo of something else.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

# Prefer this repository's own template (testing the code we are editing),
# then the sibling checkout `shoter_shot.py` points at.
_CANDIDATES = [
    os.path.join(_REPO, "Tlamatini", "agent", "agents", "windower"),
    r"C:\Development\Tlamatini\Tlamatini\agent\agents\windower",
]

_RUNTIME: str = ""


def _template() -> str:
    for path in _CANDIDATES:
        if os.path.isfile(os.path.join(path, "windower.py")):
            return path
    return ""


def _prepare(runtime_base: str) -> str:
    """Copy Windower's template into a working directory. Once."""
    global _RUNTIME
    if _RUNTIME and os.path.isdir(_RUNTIME):
        return _RUNTIME
    tpl = _template()
    if not tpl:
        return ""
    dest = os.path.join(runtime_base, "_windower_runtime")
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(tpl, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.log",
                                                  "*.pid", "pools"))
    _RUNTIME = dest
    return dest


def _run(runtime_base: str, settings: dict, timeout: int = 60):
    rt = _prepare(runtime_base)
    if not rt:
        return None
    cfg = os.path.join(rt, "config.yaml")
    with open(cfg, "w", encoding="utf-8", newline="\n") as fh:
        for key, value in settings.items():
            if isinstance(value, bool):
                fh.write("%s: %s\n" % (key, "true" if value else "false"))
            elif isinstance(value, int):
                fh.write("%s: %d\n" % (key, value))
            else:
                fh.write('%s: "%s"\n' % (key, str(value).replace('"', '\\"')))
        fh.write("target_agents: []\n")
        fh.write("source_agents: []\n")

    # EXPLICIT utf-8 for the same reason shoter_shot.py does it: the agent
    # prints emoji and the Windows codepage cannot decode them.
    return subprocess.run([sys.executable, "windower.py"], cwd=rt,
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def focus(window_title: str, runtime_base: str,
          match_mode: str = "substring", match_index: int = 0) -> bool:
    """Bring `window_title` to the foreground with Windower.

    Returns True when Windower reported `matched: true` and exited cleanly.
    Never raises.

    NOTE ON VERIFICATION. Windower's `list` reports title, state, position,
    size, hwnd and pid - but NOT which window owns the foreground - so it
    cannot confirm the focus landed. Rather than infer it, the caller confirms
    from INSIDE the page it is about to photograph, with `document.hasFocus()`:
    that is true only when the browser window is foreground AND the page is the
    active tab, which is exactly the claim the photo has to support. See
    `_focus_browser_for_photo()` in context_restore_spinner_visible.py.
    """
    try:
        r = _run(runtime_base, {"action": "focus",
                                "window_title": window_title,
                                "match_mode": match_mode,
                                "match_index": match_index})
        if r is None:
            print("   !! Windower template not found - cannot focus the window.")
            return False
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode != 0:
            print("   !! Windower exited %s while focusing %r"
                  % (r.returncode, window_title))
            return False
        if "matched: true" not in out:
            print("   !! Windower matched no window titled %r" % window_title)
            return False
        return True
    except Exception as exc:
        print("   !! Windower FAILED: %s" % exc)
        return False


def set_topmost(window_title: str, runtime_base: str, on: bool,
                match_index: int = 0) -> bool:
    """Pin (or unpin) a window always-on-top with Windower.

    WHY IT IS NEEDED. Raising the window is not enough: between the focus check
    and the shutter, Shoter has to spawn a Python process, and in that window a
    console that is busy printing (the server's RAG progress, for one) can take
    the z-order back - which is exactly how a "verified" photograph ended up
    showing two consoles and no browser. Pinning topmost for the duration of
    the shot closes that gap. ALWAYS unpin afterwards.
    """
    try:
        r = _run(runtime_base, {"action": "topmost" if on else "untopmost",
                                "window_title": window_title,
                                "match_mode": "substring",
                                "match_index": match_index})
        return r is not None and r.returncode == 0
    except Exception:
        return False


def list_windows(window_title: str, runtime_base: str) -> str:
    """Windower's enumeration, for the record. Empty string on any failure."""
    try:
        r = _run(runtime_base, {"action": "list", "window_title": window_title,
                                "match_mode": "substring"})
        if r is None or r.returncode != 0:
            return ""
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""
