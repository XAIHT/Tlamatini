# -*- coding: utf-8 -*-
"""LIVE TEST MONITOR - a window that REFRESHES ITSELF while the test runs.

Angela Lopez Mendoza, 2026-09-21:
    "SHOW A TEST AND ANOTHER WINDOW OF YOUR MONITORING IN REAL TIME ...
     AN ADDITIONAL WINDOW SHOWING EVERY LINE TESTED ... YOU MUST REFRESH
     THAT WINDOW OF TESTS"

So this is NOT a script that prints once and exits.  It is a dashboard that
repaints itself several times a second for as long as the run lasts, showing
every line the test emits, the live gauge reading, the progress bar, and the
first error the moment it appears.

It NEVER writes to the run, never kills anything, and never raises: a monitor
that can break the thing it watches is worse than no monitor.

    python monitor.py <logfile> [total]
"""
from __future__ import annotations

import os
import re
import sys
import time

REFRESH = 0.4                      # seconds between repaints
TAIL = 16                          # how many test lines stay on screen

# the line the runner prints for every prompt:
#   [  7/100] one-shot   | 118.4 KB / 30,3xx tok  | green     | moved
ROW = re.compile(r"^\s*\[\s*(\d+)\s*/\s*(\d+)\s*\]\s*(.*)$")
BAD = ("!!", "Traceback", "[FAIL]", "ERROR", "Timeout", "timeout")

# BOM is tested BEFORE anything else, because PowerShell's Tee-Object writes
# UTF-16LE, which is legitimately full of NUL bytes.  Same ordering contract as
# agent/rag/binary_guard.py and Grepper, longest prefix first.
_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def _enable_ansi() -> None:
    """Turn on VT sequences so the cursor can go home instead of flickering."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def _read(path):
    """Read the run log whatever encoding the shell chose.  Never raises."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception:
        return []
    if not raw:
        return []
    for bom, codec in _BOMS:
        if raw.startswith(bom):
            try:
                return raw.decode(codec, "replace").splitlines()
            except Exception:
                break
    for codec in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(codec).splitlines()
        except Exception:
            continue
    return raw.decode("latin-1", "replace").splitlines()


def _hms(sec):
    sec = int(max(0, sec))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def _bar(done, total, width=46):
    total = max(1, total)
    fill = int(width * min(done, total) / total)
    return "[" + "#" * fill + "." * (width - fill) + "]"


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else "gauge100.txt"
    total_hint = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    log = os.path.abspath(log)

    _enable_ansi()
    started = time.time()
    seen_done = False

    while True:
        try:
            lines = _read(log)
            rows = []
            errs = []
            total = total_hint
            last_n = 0
            for ln in lines:
                m = ROW.match(ln)
                if m:
                    last_n = int(m.group(1))
                    total = int(m.group(2))
                    rows.append(ln.rstrip())
                elif ln.strip() and any(b in ln for b in BAD):
                    errs.append(ln.strip())

            if any(("DONE" in l) or ("elapsed " in l) for l in lines[-25:]):
                seen_done = True

            if not lines:
                state, colour = "WAITING FOR THE RUN TO START", "\x1b[33m"
            elif seen_done:
                state, colour = "RUN FINISHED", "\x1b[32m"
            elif errs:
                state, colour = "RUNNING (problems seen - see below)", "\x1b[31m"
            else:
                state, colour = "RUNNING", "\x1b[36m"

            out = ["\x1b[H\x1b[J"]
            out.append("\x1b[1;36m" + "=" * 78 + "\x1b[0m")
            out.append("\x1b[1;36m  LIVE TEST MONITOR   -   Angela Lopez Mendoza\x1b[0m")
            out.append("\x1b[1;36m  context gauge / every model call measured, live\x1b[0m")
            out.append("\x1b[1;36m" + "=" * 78 + "\x1b[0m")
            out.append("  status  : %s%s\x1b[0m" % (colour, state))
            out.append("  elapsed : %s        repaint: %.1f/s"
                       % (_hms(time.time() - started), 1.0 / REFRESH))
            out.append("  log     : %s" % log)
            out.append("  lines   : %-6d   prompts done: %d / %d" % (len(lines), last_n, total))
            out.append("")
            pct = (100.0 * last_n / total) if total else 0.0
            out.append("  %s %5.1f%%" % (_bar(last_n, total), pct))
            out.append("")
            out.append("\x1b[1m  ---- EVERY LINE TESTED (last %d) %s\x1b[0m" % (TAIL, "-" * 30))
            shown = rows[-TAIL:] if rows else []
            for ln in shown:
                out.append("  " + ln[:112])
            for _ in range(TAIL - len(shown)):
                out.append("")
            out.append("")
            if errs:
                out.append("\x1b[1;31m  ---- PROBLEMS (%d) %s\x1b[0m" % (len(errs), "-" * 44))
                for ln in errs[:6]:
                    out.append("\x1b[31m  " + ln[:112] + "\x1b[0m")
            else:
                out.append("\x1b[32m  no problems seen\x1b[0m")
            out.append("")
            out.append("  (this window refreshes itself - leave it open; Ctrl+C closes it)")
            sys.stdout.write("\n".join(out) + "\n")
            sys.stdout.flush()
        except KeyboardInterrupt:
            return 0
        except Exception:
            pass                       # a monitor must never die
        try:
            time.sleep(REFRESH)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
