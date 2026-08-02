# Tlamatini Author Banner - do not remove
r"""
TEST SCREENSHOTS ARE TAKEN BY **SHOTER**, TLAMATINI'S OWN AGENT
===============================================================

ANGELA'S RULE (2026-08-02), NO EXCEPTIONS
    Using `PIL.ImageGrab` in a test is FORBIDDEN. Every screenshot is taken by
    Tlamatini's **Shoter** agent. Full stop.

WHY IT MATTERS (this is not ceremony)
    Tlamatini's tests are run WITH Tlamatini. A test that grabs its own shots
    with Pillow never exercises Shoter - so Shoter's defects never surface.
    That is exactly what happened: Shoter called `ImageGrab.grab()` WITHOUT
    `all_screens`, so on a two-monitor machine it captured only the primary and
    silently lost half the desktop. The gap sat there until Angela asked why the
    tests were not using Shoter. Using it IS the test of Shoter.

HOW IT WORKS
    This module is the LAUNCHER: it copies the agent template into a working
    directory (once per run), writes its `config.yaml` with output_dir,
    filename and all_screens, then runs `python shoter.py`. The agent does the
    work and drops the image where it was told - the same path production uses.

FAIL-OPEN
    If Shoter cannot be launched, `take_shot()` returns None and SAYS SO. It
    never falls back to Pillow: a test with a missing photo is a visible
    problem; a test that lies about who took the photo is worse.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

TEMPLATE = r"C:\Development\Tlamatini\Tlamatini\agent\agents\shoter"

_RUNTIME: str = ""


def _prepare(runtime_base: str) -> str:
    """Copy Shoter's template into a working directory. Once."""
    global _RUNTIME
    if _RUNTIME and os.path.isdir(_RUNTIME):
        return _RUNTIME
    dest = os.path.join(runtime_base, "_shoter_runtime")
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(TEMPLATE, dest,
                    ignore=shutil.ignore_patterns("__pycache__", "*.log",
                                                  "*.pid", "shoter_*"))
    _RUNTIME = dest
    return dest


def take_shot(output_dir: str, name: str, runtime_base: str = "",
              timeout: int = 60):
    """
    Capture the WHOLE DESKTOP with the Shoter agent.

    Returns the absolute path of the image, or None if Shoter could not.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        base = runtime_base or output_dir
        rt = _prepare(base)

        cfg = os.path.join(rt, "config.yaml")
        with open(cfg, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("output_dir: %s\n" % output_dir.replace("\\", "/"))
            fh.write("all_screens: true\n")
            fh.write("filename: %s\n" % name)
            fh.write("target_agents: []\n")

        # EXPLICIT utf-8: Shoter prints emoji (📸 🖥️ ✅) and without this Python
        # decodes its output with the Windows codepage (cp1252), which does not
        # know them — the reader thread dies with UnicodeDecodeError and dirties
        # the console even though the photo was taken fine.
        r = subprocess.run([sys.executable, "shoter.py"], cwd=rt,
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")

        expected = os.path.join(output_dir, name)
        if os.path.isfile(expected):
            return os.path.abspath(expected)

        log = os.path.join(rt, os.path.basename(rt) + ".log")
        if os.path.isfile(log):
            for ln in open(log, encoding="utf-8", errors="replace"):
                if "output_path:" in ln:
                    path = ln.split("output_path:", 1)[1].strip()
                    if os.path.isfile(path):
                        return path
        print("   !! Shoter left no photo (%s). rc=%s %s"
              % (name, r.returncode, (r.stderr or "")[:120]))
        return None
    except Exception as exc:                      # noqa: BLE001 - fail-open
        print("   !! could not launch Shoter for %s: %s" % (name, str(exc)[:120]))
        return None
