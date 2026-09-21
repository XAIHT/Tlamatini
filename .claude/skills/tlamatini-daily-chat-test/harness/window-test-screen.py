#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WINDOW TEST SCREEN - a graphical instrument panel Claude drives in real time.

    Angela Lopez Mendoza, 2026-09-21:
        "THAT WINDOW RENDERED BY YOU IN REAL TIME MUST MONITOR AND SHOW
         EVERYTHING INTERESTING IN THE LOG FILE OF THE SYSTEM, THE ACTUAL
         MEMORY USED BY THE SYSTEM TESTED, THE PAGINATION, THE FILES OPENED,
         EVERYTHING ... controlled by you using websockets or rpc or sockets,
         but you must stay connected to that window; put a LED indicator in the
         window to see the active connection with you, and a LED indicator
         showing the transfer I/O between you and the window; make it be
         rendered in graphical mode, not a text window."

WHAT THIS IS
    A Tk instrument panel with a JSON-over-TCP control link.  It is a SERVER:
    it opens a socket, and Claude connects to it and pushes frames.  Two LEDs
    report that link honestly -- LINK is lit only while a socket is actually
    open or a frame arrived seconds ago, and I/O flashes on real bytes moving
    in each direction.  Neither LED is decorative and neither is ever faked.

    Everything else it gathers itself, live, about the SYSTEM UNDER TEST:
    resident memory, page faults per second (the pagination Angela asked for),
    pagefile charge, open handles, CPU, thread count, disk I/O, the files the
    process has open, and every interesting line of tlamatini.log.

TWO MODES, ONE FILE
    python window-test-screen.py                 open the panel (server)
    python window-test-screen.py --send '<json>' push one frame (this is Claude)
    python window-test-screen.py --send "text"   shorthand for a spoken note

CONTROL PROTOCOL  (newline-delimited JSON, one object per line)
    {"k":"hello","who":"Claude"}
    {"k":"say",  "text":"...", "level":"info|ok|warn|err"}
    {"k":"test", "n":7,"total":100,"mode":"one-shot","bytes":121344,
                 "tokens":30336,"zone":"green","moved":true,"note":""}
    {"k":"mark", "text":"...", "level":"ok|warn|err"}
    {"k":"watch","pid":1234}            retarget telemetry at a process
    {"k":"watch","port":8000}           ... or at whoever listens on a port
    {"k":"logfile","path":"..."}        retarget the log tail
    {"k":"ping"}                        heartbeat
    every frame is answered with a pong carrying the panel's live stats, so the
    link is genuinely bidirectional and the I/O LED has real traffic to show.

CONTRACTS
    * The panel NEVER writes to, kills, or slows the system it watches.  Every
      sampler is read-only and every one of them is wrapped: an instrument that
      can break the thing it measures is worse than no instrument.
    * NOTHING here may raise into the Tk main loop.  A panel that dies mid-run
      takes Angela's only live view with it.
    * A value that could not be sampled is drawn as "--", never as zero.  A
      fabricated reading is worse than a missing one.
    * stdlib + psutil only, so it runs from source or beside a frozen install.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import socket
import socketserver
import sys
import threading
import time

# ── optional dependencies, both degrade instead of failing ─────────────────
try:
    import psutil
except Exception:                                            # pragma: no cover
    psutil = None

try:
    import tkinter as tk
    from tkinter import font as tkfont
    HAVE_TK = True
except Exception:                                            # pragma: no cover
    tk = None
    tkfont = None
    HAVE_TK = False


if not HAVE_TK:
    # Client mode ("--send", which is how Claude talks to the panel) must still
    # import on a machine with no Tk, so the widget classes below need a base
    # class to exist.  They are never instantiated without a real Tk.
    class _NoTk(object):
        Canvas = object
        Frame = object
        Label = object
        Text = object

    tk = _NoTk()


# ══════════════════════════════════════════════════════════════════════════
#  PALETTE
# ══════════════════════════════════════════════════════════════════════════
BG_APP = "#080B12"
BG_PANEL = "#0E1320"
BG_PANEL_2 = "#121829"
BG_HEAD = "#0A0F1A"
EDGE = "#1E2A44"
EDGE_HI = "#2C3F66"

FG = "#D8E2F2"
FG_DIM = "#6F7F9C"
FG_FAINT = "#3E4C66"

CYAN = "#22D3EE"
VIOLET = "#A855F7"
MAGENTA = "#EC4899"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"
BLUE = "#60A5FA"

ZONE_COLOUR = {"green": GREEN, "amber": AMBER, "warn": AMBER,
               "red": RED, "danger": RED, "": FG_DIM}

LEVEL_COLOUR = {"info": FG, "ok": GREEN, "warn": AMBER, "err": RED,
                "claude": VIOLET, "sys": CYAN}

MONO = "Consolas"
UI = "Segoe UI"

# ══════════════════════════════════════════════════════════════════════════
#  FONTS  -  every one of them NAMED, so Ctrl +/- rescales the whole panel
# ══════════════════════════════════════════════════════════════════════════
# Angela, 2026-09-21: "make it sizeable with Ctrl+(+/-)".
#
# Tk only rescales a font that widgets refer to BY NAME. Literal ("Consolas",
# 8) tuples are copied into each widget at build time and can never be changed
# afterwards, so every font here is a named tkfont.Font and every widget and
# canvas item refers to the object. Changing one size repaints everything that
# uses it - no rebuild, no restart, no reflow bugs.
FONT_SPECS = {
    "title":  (UI, 13, "bold"),
    "claude": (UI, 10, ""),
    "h9b":    (UI, 9, "bold"),
    "sub":    (UI, 9, ""),
    "hdr":    (UI, 8, "bold"),
    "lbl":    (UI, 8, ""),
    "cap":    (UI, 7, "bold"),
    "small":  (UI, 7, ""),
    "clock":  (MONO, 14, "bold"),
    "read":   (MONO, 11, "bold"),
    "mono9":  (MONO, 9, ""),
    "mono":   (MONO, 8, ""),
    "tiny":   (MONO, 7, ""),
}

FONTS = {}
ZOOM_MIN = 0.6
ZOOM_MAX = 2.4


def init_fonts():
    """Build the named fonts once, after a Tk root exists.  Never raises."""
    if FONTS or tkfont is None:
        return
    for key, (family, size, weight) in FONT_SPECS.items():
        try:
            FONTS[key] = tkfont.Font(family=family, size=size,
                                     weight=(weight or "normal"))
        except Exception:
            FONTS[key] = (family, size) if not weight else (family, size, weight)


def apply_font_zoom(zoom):
    """Rescale every named font.  Returns the zoom actually applied."""
    zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(zoom)))
    for key, (_family, size, _weight) in FONT_SPECS.items():
        font = FONTS.get(key)
        try:
            font.configure(size=max(6, int(round(size * zoom))))
        except Exception:
            pass              # a tuple fallback simply cannot zoom; not fatal
    return zoom



def _mix(colour: str, other: str, t: float) -> str:
    """Blend two #rrggbb colours.  t=0 -> colour, t=1 -> other."""
    try:
        t = max(0.0, min(1.0, float(t)))
        a = (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))
        b = (int(other[1:3], 16), int(other[3:5], 16), int(other[5:7], 16))
        return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    except Exception:
        return colour


def _bytes(n) -> str:
    try:
        n = float(n)
    except Exception:
        return "--"
    for unit, size in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= size:
            return "%.1f %s" % (n / size, unit)
    return "%d B" % int(n)


def _num(n) -> str:
    try:
        return "{:,}".format(int(n))
    except Exception:
        return "--"


# ══════════════════════════════════════════════════════════════════════════
#  LED  -  an honest indicator
# ══════════════════════════════════════════════════════════════════════════
class Led(tk.Canvas):
    """A glowing lamp.  `level` decays on its own so a flash reads as a flash."""

    def __init__(self, master, caption, colour=GREEN, size=15):
        pad = 9
        super().__init__(master, width=size + pad * 2, height=size + pad * 2,
                         bg=BG_HEAD, highlightthickness=0, bd=0)
        self._size = size
        self._pad = pad
        self.colour = colour
        self.level = 0.0            # 0 dark .. 1 full
        self.steady = 0.0           # floor the lamp never falls below
        self.caption = caption
        self._items = []
        self.redraw()

    def flash(self, colour=None, level=1.0):
        if colour:
            self.colour = colour
        self.level = max(self.level, float(level))

    def set_steady(self, level, colour=None):
        if colour:
            self.colour = colour
        self.steady = max(0.0, min(1.0, float(level)))

    def tick(self, decay=0.82):
        self.level = max(self.steady, self.level * decay)
        self.redraw()

    def redraw(self):
        try:
            for i in self._items:
                self.delete(i)
            self._items = []
            s, p = self._size, self._pad
            cx = cy = p + s / 2.0
            lit = max(0.0, min(1.0, self.level))
            # outer halo, then a tighter glow, then the lamp itself
            for ring, alpha in ((s / 2.0 + 8, 0.14), (s / 2.0 + 4, 0.30)):
                if lit <= 0.02:
                    break
                self._items.append(self.create_oval(
                    cx - ring, cy - ring, cx + ring, cy + ring,
                    fill=_mix(BG_HEAD, self.colour, alpha * lit), outline=""))
            body = _mix("#101725", self.colour, 0.15 + 0.85 * lit)
            self._items.append(self.create_oval(
                cx - s / 2.0, cy - s / 2.0, cx + s / 2.0, cy + s / 2.0,
                fill=body, outline=_mix(EDGE, self.colour, lit), width=1))
            if lit > 0.35:                       # specular highlight
                r = s / 6.0
                self._items.append(self.create_oval(
                    cx - s / 4.0 - r, cy - s / 4.0 - r, cx - s / 4.0 + r, cy - s / 4.0 + r,
                    fill=_mix(body, "#FFFFFF", 0.55 * lit), outline=""))
        except Exception:
            pass


class LedBlock(tk.Frame):
    """A lamp plus its caption and a one-line value, laid out horizontally."""

    def __init__(self, master, caption, colour=GREEN):
        super().__init__(master, bg=BG_HEAD)
        self.led = Led(self, caption, colour)
        self.led.grid(row=0, column=0, rowspan=2)
        self.cap = tk.Label(self, text=caption, bg=BG_HEAD, fg=FG_DIM,
                            font=FONTS["cap"], anchor="w")
        self.cap.grid(row=0, column=1, sticky="w", padx=(2, 12))
        self.val = tk.Label(self, text="--", bg=BG_HEAD, fg=FG,
                            font=FONTS["mono"], anchor="w")
        self.val.grid(row=1, column=1, sticky="w", padx=(2, 12))

    def set_value(self, text, colour=None):
        try:
            self.val.configure(text=text, fg=colour or FG)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
#  CHART  -  a filled sparkline with a live read-out
# ══════════════════════════════════════════════════════════════════════════
class Chart(tk.Canvas):
    def __init__(self, master, title, colour=CYAN, height=58, maxlen=220,
                 fmt=None, unit=""):
        super().__init__(master, height=height, bg=BG_PANEL,
                         highlightthickness=1, highlightbackground=EDGE, bd=0)
        self.base_height = height
        self.title = title
        self.colour = colour
        self.unit = unit
        self.fmt = fmt or (lambda v: "%.0f" % v)
        self.data = collections.deque(maxlen=maxlen)
        self.latest = None
        self.bind("<Configure>", lambda e: self.redraw())

    def push(self, value):
        if value is None:
            self.latest = None
            return
        try:
            v = float(value)
        except Exception:
            return
        self.data.append(v)
        self.latest = v

    def redraw(self):
        try:
            self.delete("all")
            w = max(self.winfo_width(), 10)
            h = max(self.winfo_height(), 10)
            top, bottom, left, right = 20, 5, 6, 6
            plot_h = max(h - top - bottom, 8)
            plot_w = max(w - left - right, 8)

            self.create_text(10, 8, text=self.title.upper(), anchor="nw",
                             fill=FG_DIM, font=FONTS["cap"])
            read = self.fmt(self.latest) if self.latest is not None else "--"
            self.create_text(w - 10, 6, text=read, anchor="ne",
                             fill=self.colour if self.latest is not None else FG_FAINT,
                             font=FONTS["read"])
            if self.unit and self.latest is not None:
                self.create_text(w - 10, 22, text=self.unit, anchor="ne",
                                 fill=FG_FAINT, font=FONTS["small"])

            for i in range(1, 4):                    # grid
                y = top + plot_h * i / 4.0
                self.create_line(left, y, w - right, y, fill="#141B2C")

            pts = list(self.data)
            if len(pts) < 2:
                # Only when there is room: in a short chart this text landed
                # on top of the title and read out as a smudge.
                if plot_h > 18:
                    self.create_text(w / 2.0, top + plot_h / 2.0 + 2,
                                     text="sampling...", fill=FG_FAINT,
                                     font=FONTS["tiny"])
                return

            lo, hi = min(pts), max(pts)
            if hi - lo < 1e-9:
                lo, hi = lo - 1.0, hi + 1.0
            span = hi - lo
            step = plot_w / float(len(pts) - 1)

            coords = []
            for i, v in enumerate(pts):
                x = left + i * step
                y = top + plot_h - (v - lo) / span * plot_h
                coords.extend((x, y))

            area = list(coords) + [left + plot_w, top + plot_h, left, top + plot_h]
            self.create_polygon(area, fill=_mix(BG_PANEL, self.colour, 0.16),
                                outline="")
            self.create_line(coords, fill=self.colour, width=2,
                             smooth=True, splinesteps=6)
            # the live head
            self.create_oval(coords[-2] - 3, coords[-1] - 3,
                             coords[-2] + 3, coords[-1] + 3,
                             fill=self.colour, outline=BG_PANEL, width=1)
            self.create_text(left + 2, top + 1, text=self.fmt(hi), anchor="nw",
                             fill=FG_FAINT, font=FONTS["tiny"])
            self.create_text(left + 2, top + plot_h - 1, text=self.fmt(lo),
                             anchor="sw", fill=FG_FAINT, font=FONTS["tiny"])
        except Exception:
            pass


class Bar(tk.Canvas):
    """A labelled horizontal bar - used for whole-machine RAM and progress."""

    def __init__(self, master, title, colour=VIOLET, height=42):
        super().__init__(master, height=height, bg=BG_PANEL,
                         highlightthickness=1, highlightbackground=EDGE, bd=0)
        self.base_height = height
        self.title = title
        self.colour = colour
        self.frac = 0.0
        self.caption = "--"
        self.bind("<Configure>", lambda e: self.redraw())

    def set(self, frac, caption, colour=None):
        try:
            self.frac = max(0.0, min(1.0, float(frac)))
        except Exception:
            self.frac = 0.0
        self.caption = caption
        if colour:
            self.colour = colour

    def redraw(self):
        """Lay out from MEASURED text height, never from fixed offsets.

        The first version put the labels at y=6 and the bar at h-16. At the
        compact size those two rows are the same rows, so the coloured fill
        was painted straight over "MACHINE MEMORY  15.0 GB / 15.5 GB" and made
        it unreadable. The bar is now placed strictly BELOW the text, and if
        there is genuinely no room for both, the bar is dropped rather than
        drawn on top of the numbers - the numbers are the information.
        """
        try:
            self.delete("all")
            w = max(self.winfo_width(), 10)
            h = max(self.winfo_height(), 10)
            pad = 8
            top = 3
            try:
                line = int(FONTS["cap"].metrics("linespace"))
            except Exception:
                line = 11

            self.create_text(pad, top, text=self.title.upper(), anchor="nw",
                             fill=FG_DIM, font=FONTS["cap"])
            self.create_text(w - pad, top, text=self.caption, anchor="ne",
                             fill=FG, font=FONTS["mono"])

            y0 = top + line + 3                 # always under the text
            y1 = h - 4
            if y1 - y0 < 3:                     # no room: text wins
                return
            if y1 - y0 > 10:                    # keep the bar slim
                y0 = y1 - 10

            self.create_rectangle(pad, y0, w - pad, y1,
                                  fill="#141B2C", outline="")
            end = pad + (w - pad * 2) * self.frac
            if end > pad + 1:
                self.create_rectangle(pad, y0, end, y1,
                                      fill=self.colour, outline="")
                self.create_rectangle(max(pad, end - 2), y0, end, y1,
                                      fill=_mix(self.colour, "#FFFFFF", 0.5),
                                      outline="")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
#  TELEMETRY  -  read-only samplers for the system under test
# ══════════════════════════════════════════════════════════════════════════
class Telemetry(threading.Thread):
    """Samples the watched process once a second.  Never touches it."""

    def __init__(self, sink, target_port=8000, pid=None, interval=1.0):
        super().__init__(daemon=True, name="telemetry")
        self.sink = sink
        self.target_port = target_port
        self.pid = pid
        self.interval = interval
        self._proc = None
        self._last_faults = None
        self._last_io = None
        self._last_t = None
        self._files_at = 0.0
        self._files = []
        self.stop_flag = threading.Event()

    # -- finding the process is itself best-effort -------------------------
    # Two independent ways to find the system under test, because on Windows
    # psutil.net_connections() can come back empty or AccessDenied for
    # processes we do not own -- and a panel that reports "no process" while
    # the server is plainly answering requests is an instrument that lies.
    CMDLINE_HINTS = ("manage.py runserver", "manage.py startserver", "daphne")

    def _find_by_port(self):
        if psutil is None or not self.target_port:
            return None
        try:
            for c in psutil.net_connections(kind="inet"):
                if (c.status == psutil.CONN_LISTEN and c.laddr
                        and c.laddr.port == self.target_port and c.pid):
                    return c.pid
        except Exception:
            pass
        return self._find_by_cmdline()

    def _find_by_cmdline(self):
        """Fallback: the Django server names itself in its own command line."""
        if psutil is None:
            return None
        try:
            for proc in psutil.process_iter(["name", "cmdline"]):
                name = (proc.info.get("name") or "").lower()
                if "python" not in name:
                    continue
                line = " ".join(proc.info.get("cmdline") or [])
                if any(hint in line for hint in self.CMDLINE_HINTS):
                    return proc.pid
        except Exception:
            pass
        return None

    def _resolve(self):
        if psutil is None:
            return None
        try:
            if self._proc is not None and self._proc.is_running():
                return self._proc
        except Exception:
            pass
        self._proc = None
        self._last_faults = None
        self._last_io = None
        pid = self.pid or self._find_by_port()
        if not pid:
            return None
        try:
            p = psutil.Process(pid)
            p.cpu_percent(None)             # prime the CPU window
            self._proc = p
        except Exception:
            self._proc = None
        return self._proc

    def retarget(self, pid=None, port=None):
        if pid:
            self.pid = int(pid)
        if port:
            self.target_port = int(port)
            self.pid = None
        self._proc = None

    def run(self):
        while not self.stop_flag.is_set():
            sample = {"k": "telemetry", "t": time.time(), "ok": False}
            try:
                if psutil is not None:
                    vm = psutil.virtual_memory()
                    sample["sys_used"] = vm.total - vm.available
                    sample["sys_total"] = vm.total
                    sample["sys_pct"] = vm.percent
                    try:
                        sw = psutil.swap_memory()
                        sample["swap_used"] = sw.used
                        sample["swap_total"] = sw.total
                    except Exception:
                        pass

                p = self._resolve()
                if p is not None:
                    now = time.time()
                    with p.oneshot():
                        mi = p.memory_info()
                        sample["pid"] = p.pid
                        sample["name"] = p.name()
                        sample["rss"] = getattr(mi, "rss", None)
                        sample["vms"] = getattr(mi, "vms", None)
                        sample["pagefile"] = getattr(mi, "pagefile", None)
                        sample["peak_wset"] = getattr(mi, "peak_wset", None)
                        sample["threads"] = p.num_threads()
                        try:
                            sample["cpu"] = p.cpu_percent(None)
                        except Exception:
                            sample["cpu"] = None
                        try:
                            sample["handles"] = p.num_handles()
                        except Exception:
                            sample["handles"] = None
                        try:
                            sample["created"] = p.create_time()
                        except Exception:
                            pass

                        faults = getattr(mi, "num_page_faults", None)
                        if faults is not None:
                            if self._last_faults is not None and self._last_t:
                                dt = max(now - self._last_t, 1e-6)
                                sample["faults_s"] = max(0.0, (faults - self._last_faults) / dt)
                            sample["faults_total"] = faults
                            self._last_faults = faults

                        try:
                            io = p.io_counters()
                            if self._last_io is not None and self._last_t:
                                dt = max(now - self._last_t, 1e-6)
                                sample["io_read_s"] = max(0.0, (io.read_bytes - self._last_io[0]) / dt)
                                sample["io_write_s"] = max(0.0, (io.write_bytes - self._last_io[1]) / dt)
                            sample["io_read"] = io.read_bytes
                            sample["io_write"] = io.write_bytes
                            self._last_io = (io.read_bytes, io.write_bytes)
                        except Exception:
                            pass

                    self._last_t = now

                    # open_files() is expensive - sample it far more slowly
                    if now - self._files_at > 3.0:
                        self._files_at = now
                        try:
                            paths = [f.path for f in p.open_files()]
                            self._files = paths[-400:]
                            sample["files"] = self._files
                            sample["files_n"] = len(paths)
                        except Exception:
                            sample["files"] = None
                    sample["ok"] = True
            except Exception:
                pass
            try:
                self.sink(sample)
            except Exception:
                pass
            self.stop_flag.wait(self.interval)


class LogTail(threading.Thread):
    """Incremental, BOM-aware, truncation-aware tail of the application log.

    tlamatini.log is opened with mode 'w' on every server start, so the file
    SHRINKS.  A tail that only ever seeks forward would go silent for the rest
    of the session; noticing the shrink and starting over is the whole job.
    """

    BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
            (b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"),
            (b"\xfe\xff", "utf-16-be"))

    def __init__(self, sink, path, interval=0.5):
        super().__init__(daemon=True, name="logtail")
        self.sink = sink
        self.path = path
        self.interval = interval
        self.pos = 0
        self.codec = None
        self.stop_flag = threading.Event()
        self._carry = b""

    def retarget(self, path):
        self.path = path
        self.pos = 0
        self.codec = None
        self._carry = b""

    def _decode(self, raw: bytes) -> str:
        if self.codec:
            try:
                return raw.decode(self.codec, "replace")
            except Exception:
                pass
        for codec in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(codec)
            except Exception:
                continue
        return raw.decode("latin-1", "replace")

    def run(self):
        while not self.stop_flag.is_set():
            try:
                path = self.path
                if path and os.path.exists(path):
                    size = os.path.getsize(path)
                    if size < self.pos:                 # truncated -> restart
                        self.pos = 0
                        self.codec = None
                        self._carry = b""
                        self.sink({"k": "log", "line": "--- log truncated, following again ---",
                                   "level": "sys"})
                    if self.pos == 0 and size:
                        with open(path, "rb") as fh:
                            head = fh.read(4)
                        for bom, codec in self.BOMS:
                            if head.startswith(bom):
                                self.codec = codec
                                self.pos = len(bom)
                                break
                    if size > self.pos:
                        with open(path, "rb") as fh:
                            fh.seek(self.pos)
                            chunk = fh.read(size - self.pos)
                        self.pos = size
                        buf = self._carry + chunk
                        nl = buf.rfind(b"\n")
                        if nl >= 0:
                            self._carry = buf[nl + 1:]
                            buf = buf[:nl]
                        else:
                            self._carry = buf
                            buf = b""
                        if buf:
                            for line in self._decode(buf).splitlines():
                                if line.strip():
                                    self.sink({"k": "log", "line": line.rstrip()})
            except Exception:
                pass
            self.stop_flag.wait(self.interval)


# ══════════════════════════════════════════════════════════════════════════
#  CONTROL LINK  -  the socket Claude talks to
# ══════════════════════════════════════════════════════════════════════════
class LinkState(object):
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = 0
        self.last_rx = 0.0
        self.last_tx = 0.0
        self.rx_frames = 0
        self.tx_frames = 0
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.peer = ""

    def snapshot(self):
        with self.lock:
            return dict(clients=self.clients, last_rx=self.last_rx,
                        last_tx=self.last_tx, rx_frames=self.rx_frames,
                        tx_frames=self.tx_frames, rx_bytes=self.rx_bytes,
                        tx_bytes=self.tx_bytes, peer=self.peer)


def make_handler(sink, link: LinkState, stats_fn):
    class Handler(socketserver.StreamRequestHandler):
        timeout = 600

        def handle(self):
            with link.lock:
                link.clients += 1
                link.peer = "%s:%s" % self.client_address[:2]
            sink({"k": "link", "event": "open", "peer": link.peer})
            try:
                for raw in self.rfile:
                    if not raw:
                        break
                    with link.lock:
                        link.rx_frames += 1
                        link.rx_bytes += len(raw)
                        link.last_rx = time.time()
                    try:
                        msg = json.loads(raw.decode("utf-8", "replace"))
                        if not isinstance(msg, dict):
                            raise ValueError("not an object")
                    except Exception:
                        msg = {"k": "say",
                               "text": raw.decode("utf-8", "replace").strip()}
                    sink(msg)
                    try:
                        reply = json.dumps(
                            {"ok": True, "k": "pong", "t": time.time(),
                             "stats": stats_fn()},
                            default=str).encode("utf-8") + b"\n"
                        self.wfile.write(reply)
                        self.wfile.flush()
                        with link.lock:
                            link.tx_frames += 1
                            link.tx_bytes += len(reply)
                            link.last_tx = time.time()
                    except Exception:
                        break
            except Exception:
                pass
            finally:
                with link.lock:
                    link.clients = max(0, link.clients - 1)
                sink({"k": "link", "event": "close"})

        def handle_timeout(self):
            pass

    return Handler


class LinkServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ══════════════════════════════════════════════════════════════════════════
#  THE PANEL
# ══════════════════════════════════════════════════════════════════════════
class Panel(object):
    LOG_KEEP = 900
    TEST_KEEP = 400

    HOT = (
        ("[CONTEXT]", CYAN), ("[BINARY-GUARD]", BLUE), ("[LLM-", VIOLET),
        ("[Tier-", BLUE), ("[PORT]", BLUE), ("[WHO]", FG_DIM),
        ("Traceback", RED), ("ERROR", RED), ("CRITICAL", RED),
        ("Exception", RED), ("WARNING", AMBER), ("Forbidden", AMBER),
        ("500", RED), ("404", AMBER), ("Starting", GREEN),
        ("AGENT STARTED", GREEN), ("finished", GREEN),
    )

    def __init__(self, args):
        self.args = args
        self.queue = collections.deque()
        self.qlock = threading.Lock()
        self.link = LinkState()
        self.started = time.time()
        self.tel = {}
        self.last_test = None
        self.progress = (0, args.total)
        self.file_seen = collections.OrderedDict()
        self.claude_line = "waiting for Claude to connect..."
        self.claude_level = "info"
        self.claude_at = 0.0
        self.server = None

        self.root = tk.Tk()
        self.root.title("TLAMATINI  -  WINDOW TEST SCREEN   (driven by Claude)")
        self.root.configure(bg=BG_APP)
        self.root.geometry("1420x900+40+20")
        # Small enough to sit in one quadrant of a 2x2 tiled desktop: Angela
        # tiles four windows on a 1707x1067 logical screen, so a quadrant is
        # 853x533 and a larger minimum silently refuses to be tiled.
        self.root.minsize(640, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        init_fonts()
        self._zoom = 1.0
        self._zoom_note = ""
        self._zoom_at = 0.0

        self._build()
        self._bind_zoom()
        # Angela reads small text comfortably and wants the density, so the
        # panel STARTS compact rather than at 100%.  Ctrl +/- moves it from
        # here in either direction; --zoom sets a different starting point.
        start = getattr(args, "zoom", None) or 0.8
        if abs(float(start) - 1.0) > 0.01:
            self.zoom_set(float(start))

        # background workers, all read-only, all daemons
        self.telemetry = Telemetry(self.push, target_port=args.target_port,
                                   pid=args.pid)
        self.telemetry.start()
        self.logtail = LogTail(self.push, args.log)
        self.logtail.start()
        self._serve(args.host, args.port)

        self.root.after(60, self._pump)
        self.root.after(120, self._paint)

    # ── layout ────────────────────────────────────────────────────────────
    def _build(self):
        root = self.root
        # ⚠️ THE LOG MUST ALWAYS BE VISIBLE, AND EVERY PANE MUST BE RESIZABLE
        # (Angela, 2026-09-21: "make the log always visible in the monitoring
        # window ... compress its content and make it sizeable").
        #
        # The panel is tiled into a 853 px quadrant. With fixed columns of 330
        # and 310 px there was nothing left for the middle one, so the log
        # collapsed to zero width and looked as if it had never been built.
        # Fixed columns are therefore gone: the body is a PanedWindow, every
        # divider is draggable, each pane declares its own minimum, and the log
        # is the pane that KEEPS the space when the window shrinks.
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # ── header ────────────────────────────────────────────────────────
        head = tk.Frame(root, bg=BG_HEAD, highlightthickness=1,
                        highlightbackground=EDGE_HI)
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 4))
        head.grid_columnconfigure(1, weight=1)

        title_box = tk.Frame(head, bg=BG_HEAD)
        title_box.grid(row=0, column=0, sticky="w", padx=14, pady=8)
        tk.Label(title_box, text="WINDOW  TEST  SCREEN", bg=BG_HEAD, fg=FG,
                 font=FONTS["title"]).pack(anchor="w")
        tk.Label(title_box,
                 text="live instrument panel  \u00b7  rendered and driven by Claude",
                 bg=BG_HEAD, fg=VIOLET, font=FONTS["sub"]).pack(anchor="w")

        right = tk.Frame(head, bg=BG_HEAD)
        right.grid(row=0, column=2, sticky="e", padx=14)
        self.clock = tk.Label(right, text="--:--:--", bg=BG_HEAD, fg=FG,
                              font=FONTS["clock"])
        self.clock.pack(anchor="e")
        tk.Label(right, text="Angela L\u00f3pez Mendoza", bg=BG_HEAD, fg=FG_DIM,
                 font=FONTS["sub"]).pack(anchor="e")

        # ── LED strip ─────────────────────────────────────────────────────
        strip = tk.Frame(root, bg=BG_HEAD, highlightthickness=1,
                         highlightbackground=EDGE)
        strip.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 6))

        self.led_link = LedBlock(strip, "CLAUDE LINK", RED)
        self.led_io = LedBlock(strip, "I/O  CLAUDE \u2194 WINDOW", CYAN)
        self.led_sut = LedBlock(strip, "SYSTEM UNDER TEST", AMBER)
        self.led_run = LedBlock(strip, "TEST RUN", FG_DIM)
        for i, b in enumerate((self.led_link, self.led_io, self.led_sut, self.led_run)):
            b.grid(row=0, column=i, sticky="w", padx=(10, 18), pady=4)
        strip.grid_columnconfigure(4, weight=1)

        self.link_note = tk.Label(strip, text="listening...", bg=BG_HEAD,
                                  fg=FG_DIM, font=FONTS["mono9"], anchor="e")
        self.link_note.grid(row=0, column=4, sticky="e", padx=14)

        # ── the body: two nested PanedWindows, every divider draggable ────
        vpane = tk.PanedWindow(root, orient="vertical", bg=EDGE, bd=0,
                               sashwidth=5, sashrelief="flat",
                               showhandle=False, opaqueresize=True)
        vpane.grid(row=2, column=0, columnspan=3, sticky="nsew",
                   padx=6, pady=(0, 4))
        self.vpane = vpane

        hpane = tk.PanedWindow(vpane, orient="horizontal", bg=EDGE, bd=0,
                               sashwidth=5, sashrelief="flat",
                               showhandle=False, opaqueresize=True)
        self.hpane = hpane

        # ── left pane : the numbers Angela asked for ──────────────────────
        left = tk.Frame(hpane, bg=BG_APP)
        # Five charts share the stretch; the bar gets a fixed row of its
        # own.  Without this the bar had no row configured at all and
        # Tk drew it ON TOP of the CPU chart.
        for r in range(5):
            left.grid_rowconfigure(r, weight=1, minsize=34)
        left.grid_rowconfigure(5, weight=0, minsize=42)
        left.grid_columnconfigure(0, weight=1)

        self.c_mem = Chart(left, "memory  \u00b7  resident (RSS)", GREEN,
                           fmt=lambda v: _bytes(v))
        self.c_fault = Chart(left, "pagination  \u00b7  page faults / s", VIOLET,
                             fmt=lambda v: _num(v), unit="faults/s")
        self.c_threads = Chart(left, "threads opened", MAGENTA,
                               fmt=lambda v: _num(v), unit="threads")
        self.c_files = Chart(left, "open handles", BLUE, fmt=lambda v: _num(v))
        self.c_cpu = Chart(left, "cpu", AMBER, fmt=lambda v: "%.0f%%" % v)
        self.charts = (self.c_mem, self.c_fault, self.c_threads,
                       self.c_files, self.c_cpu)
        for i, c in enumerate(self.charts):
            c.grid(row=i, column=0, sticky="nsew", pady=(0, 3))

        self.b_ram = Bar(left, "machine memory", VIOLET)
        self.b_ram.grid(row=5, column=0, sticky="ew", pady=(0, 2))

        # ── centre pane : the system log, the one that keeps its space ────
        centre = tk.Frame(hpane, bg=BG_PANEL, highlightthickness=1,
                          highlightbackground=EDGE)
        centre.grid_rowconfigure(1, weight=1)
        centre.grid_columnconfigure(0, weight=1)

        hdr = tk.Frame(centre, bg=BG_PANEL_2)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text="SYSTEM LOG", bg=BG_PANEL_2, fg=FG_DIM,
                 font=FONTS["hdr"]).pack(side="left", padx=10, pady=4)
        self.log_where = tk.Label(hdr, text=os.path.basename(self.args.log),
                                  bg=BG_PANEL_2, fg=FG_FAINT,
                                  font=FONTS["tiny"], anchor="w")
        self.log_where.pack(side="left")
        self.log_count = tk.Label(hdr, text="0 lines", bg=BG_PANEL_2, fg=FG_FAINT,
                                  font=FONTS["mono"])
        self.log_count.pack(side="right", padx=10)

        self.log = tk.Text(centre, bg=BG_PANEL, fg=FG, font=FONTS["mono"],
                           bd=0, highlightthickness=0, wrap="none",
                           insertbackground=FG, state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(2, 6))
        sb = tk.Scrollbar(centre, command=self.log.yview, bg=EDGE,
                          troughcolor=BG_PANEL, bd=0, highlightthickness=0,
                          activebackground=EDGE_HI, relief="flat",
                          elementborderwidth=0, width=9)
        sb.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        for name, colour in (("plain", FG_DIM), ("hot", FG), ("err", RED),
                             ("warn", AMBER), ("ok", GREEN), ("sys", CYAN),
                             ("ctx", CYAN), ("claude", VIOLET)):
            self.log.tag_configure(name, foreground=colour)

        # ── right pane : files + process facts ─────────────────────────────
        rightc = tk.Frame(hpane, bg=BG_APP)
        rightc.grid_rowconfigure(1, weight=1)
        rightc.grid_columnconfigure(0, weight=1)

        facts = tk.Frame(rightc, bg=BG_PANEL, highlightthickness=1,
                         highlightbackground=EDGE)
        facts.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        tk.Label(facts, text="SYSTEM UNDER TEST", bg=BG_PANEL, fg=FG_DIM,
                 font=FONTS["hdr"]).grid(row=0, column=0, columnspan=2,
                                            sticky="w", padx=10, pady=(6, 2))
        self.facts = {}
        rows = ("process", "pid", "threads", "handles", "pagefile",
                "peak memory", "page faults", "disk read/s", "disk write/s",
                "uptime")
        for i, key in enumerate(rows):
            tk.Label(facts, text=key, bg=BG_PANEL, fg=FG_FAINT,
                     font=FONTS["small"], anchor="w").grid(row=i + 1, column=0,
                                                    sticky="w", padx=(12, 6))
            v = tk.Label(facts, text="--", bg=BG_PANEL, fg=FG,
                         font=FONTS["mono"], anchor="e")
            v.grid(row=i + 1, column=1, sticky="e", padx=(6, 12))
            self.facts[key] = v
        facts.grid_columnconfigure(1, weight=1)
        tk.Frame(facts, bg=BG_PANEL, height=6).grid(row=len(rows) + 1, column=0)

        fbox = tk.Frame(rightc, bg=BG_PANEL, highlightthickness=1,
                        highlightbackground=EDGE)
        fbox.grid(row=1, column=0, sticky="nsew")
        rightc.grid_rowconfigure(1, weight=1, minsize=70)
        fbox.grid_rowconfigure(1, weight=1)
        fbox.grid_columnconfigure(0, weight=1)
        fh = tk.Frame(fbox, bg=BG_PANEL_2)
        fh.grid(row=0, column=0, sticky="ew")
        tk.Label(fh, text="FILES OPENED", bg=BG_PANEL_2, fg=FG_DIM,
                 font=FONTS["hdr"]).pack(side="left", padx=10, pady=4)
        self.files_count = tk.Label(fh, text="--", bg=BG_PANEL_2, fg=FG_FAINT,
                                    font=FONTS["mono"])
        self.files_count.pack(side="right", padx=10)
        self.files = tk.Text(fbox, bg=BG_PANEL, fg=FG_DIM, font=FONTS["tiny"],
                             bd=0, highlightthickness=0, wrap="none",
                             state="disabled")
        self.files.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        self.files.tag_configure("new", foreground=GREEN)
        self.files.tag_configure("old", foreground=FG_FAINT)

        # ── bottom pane : the test stream ─────────────────────────────────
        test = tk.Frame(vpane, bg=BG_PANEL, highlightthickness=1,
                        highlightbackground=EDGE)

        # Panes are added last, each with the minimum it stays readable at.
        # The log pane STRETCHES and the two side panes do not, so shrinking
        # the window narrows the sides and never erases the log.
        hpane.add(left, minsize=210, stretch="never", padx=0, pady=0)
        hpane.add(centre, minsize=240, stretch="always", padx=0, pady=0)
        hpane.add(rightc, minsize=170, stretch="never", padx=0, pady=0)
        vpane.add(hpane, minsize=200, stretch="always", padx=0, pady=0)
        vpane.add(test, minsize=90, stretch="never", padx=0, pady=0)
        test.grid_rowconfigure(2, weight=1)
        test.grid_columnconfigure(0, weight=1)

        th = tk.Frame(test, bg=BG_PANEL_2)
        th.grid(row=0, column=0, sticky="ew")
        tk.Label(th, text="TEST STREAM  \u00b7  every line tested",
                 bg=BG_PANEL_2, fg=FG_DIM, font=FONTS["hdr"]).pack(
                     side="left", padx=10, pady=4)
        self.test_note = tk.Label(th, text="no run yet", bg=BG_PANEL_2,
                                  fg=FG_FAINT, font=FONTS["mono"])
        self.test_note.pack(side="right", padx=10)

        self.b_prog = Bar(test, "progress", CYAN, height=44)
        self.b_prog.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 4))

        self.test = tk.Text(test, bg=BG_PANEL, fg=FG, font=FONTS["mono"], bd=0,
                            highlightthickness=0, wrap="none", state="disabled")
        self.test.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        for name, colour in (("green", GREEN), ("amber", AMBER), ("red", RED),
                             ("dim", FG_DIM), ("head", CYAN)):
            self.test.tag_configure(name, foreground=colour)

        # ── footer : what Claude is saying right now ──────────────────────
        foot = tk.Frame(root, bg=BG_HEAD, highlightthickness=1,
                        highlightbackground=EDGE_HI)
        foot.grid(row=4, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
        foot.grid_columnconfigure(1, weight=1)
        tk.Label(foot, text="CLAUDE", bg=BG_HEAD, fg=VIOLET,
                 font=FONTS["h9b"]).grid(row=0, column=0, padx=(14, 8), pady=7)
        self.claude_lbl = tk.Label(foot, text=self.claude_line, bg=BG_HEAD,
                                   fg=FG, font=FONTS["claude"], anchor="w")
        self.claude_lbl.grid(row=0, column=1, sticky="w")
        self.counters = tk.Label(foot, text="", bg=BG_HEAD, fg=FG_FAINT,
                                 font=FONTS["mono"], anchor="e")
        self.counters.grid(row=0, column=2, sticky="e", padx=14)

    # ── plumbing ──────────────────────────────────────────────────────────
    def push(self, msg):
        try:
            with self.qlock:
                self.queue.append(msg)
        except Exception:
            pass

    def _stats(self):
        t = self.tel or {}
        return {"rss": t.get("rss"), "faults_s": t.get("faults_s"),
                "handles": t.get("handles"), "cpu": t.get("cpu"),
                "pid": t.get("pid"), "progress": list(self.progress),
                "uptime": round(time.time() - self.started, 1)}

    def _serve(self, host, port):
        try:
            handler = make_handler(self.push, self.link, self._stats)
            self.server = LinkServer((host, port), handler)
            threading.Thread(target=self.server.serve_forever,
                             kwargs={"poll_interval": 0.2},
                             daemon=True, name="linkserver").start()
            real = self.server.server_address[1]
            self.link_note.configure(text="listening on %s:%d" % (host, real))
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "window-test-screen.port"), "w") as fh:
                    fh.write(str(real))
            except Exception:
                pass
            self._log_line("control link listening on %s:%d - waiting for Claude"
                           % (host, real), "sys")
        except Exception as exc:
            self.link_note.configure(text="link unavailable: %s" % exc, fg=RED)
            self._log_line("control link FAILED: %s" % exc, "err")

    # ── text helpers ──────────────────────────────────────────────────────
    def _append(self, widget, text, tag, keep):
        try:
            widget.configure(state="normal")
            widget.insert("end", text + "\n", tag)
            lines = int(widget.index("end-1c").split(".")[0])
            if lines > keep:
                widget.delete("1.0", "%d.0" % (lines - keep))
            widget.see("end")
            widget.configure(state="disabled")
        except Exception:
            pass

    def _log_tag(self, line):
        for token, colour in self.HOT:
            if token in line:
                if colour is RED:
                    return "err"
                if colour is AMBER:
                    return "warn"
                if colour is GREEN:
                    return "ok"
                if colour in (CYAN, BLUE):
                    return "ctx"
                return "hot"
        return "plain"

    def _log_line(self, line, tag=None):
        self._append(self.log, line, tag or self._log_tag(line), self.LOG_KEEP)
        try:
            n = int(self.log.index("end-1c").split(".")[0])
            self.log_count.configure(text="%s lines" % _num(n))
        except Exception:
            pass

    # ── message pump : the only place Tk state is touched ─────────────────
    def _bind_zoom(self):
        """Browser-style zoom.  bind_all, so it works whatever has focus."""
        try:
            for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>",
                        "<Control-Shift-plus>"):
                self.root.bind_all(seq, lambda e: self.zoom_by(0.1))
            for seq in ("<Control-minus>", "<Control-underscore>",
                        "<Control-KP_Subtract>"):
                self.root.bind_all(seq, lambda e: self.zoom_by(-0.1))
            self.root.bind_all("<Control-0>", lambda e: self.zoom_set(1.0))
            self.root.bind_all("<Control-KP_0>", lambda e: self.zoom_set(1.0))
            self.root.bind_all("<Control-MouseWheel>", self._wheel_zoom)
        except Exception:
            pass

    def zoom_by(self, delta):
        return self.zoom_set(self._zoom + delta)

    def zoom_set(self, value):
        """Rescale every font, then every chart, so nothing is clipped.

        Fonts alone are not enough: a chart is a fixed-height canvas, so at
        150% the read-out would simply be cut off by the frame it lives in.
        Height follows the same factor, which keeps the whole panel readable
        instead of merely bigger.
        """
        try:
            self._zoom = apply_font_zoom(value)
            for chart in self.charts:
                chart.configure(height=max(34, int(round(
                    chart.base_height * self._zoom))))
            for bar in (self.b_ram, self.b_prog):
                bar.configure(height=max(22, int(round(
                    bar.base_height * self._zoom))))
            self._zoom_note = "zoom %d%%" % int(round(self._zoom * 100))
            self._zoom_at = time.time()
        except Exception:
            pass
        return "break"

    def _wheel_zoom(self, event):
        try:
            self.zoom_by(0.1 if getattr(event, "delta", 0) > 0 else -0.1)
        except Exception:
            pass
        return "break"

    def _pump(self):
        try:
            with self.qlock:
                batch, self.queue = list(self.queue), collections.deque()
            for msg in batch:
                try:
                    self._handle(msg)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self.root.after(60, self._pump)

    def _handle(self, msg):
        kind = (msg.get("k") or "").lower()

        if kind == "telemetry":
            self.tel = msg
            self.c_mem.push(msg.get("rss"))
            self.c_fault.push(msg.get("faults_s"))
            self.c_threads.push(msg.get("threads"))
            self.c_files.push(msg.get("handles"))
            self.c_cpu.push(msg.get("cpu"))
            files = msg.get("files")
            if files:
                fresh = [p for p in files if p not in self.file_seen]
                for p in files:
                    self.file_seen[p] = True
                while len(self.file_seen) > 4000:
                    self.file_seen.popitem(last=False)
                for p in fresh[-40:]:
                    self._append(self.files, p, "new", 500)
                self.files_count.configure(
                    text="%s open  \u00b7  %s seen" % (_num(msg.get("files_n")),
                                                       _num(len(self.file_seen))))
            return

        if kind == "log":
            self._log_line(msg.get("line", ""), msg.get("level"))
            return

        if kind == "link":
            if msg.get("event") == "open":
                self._log_line("Claude connected from %s" % msg.get("peer", "?"), "claude")
            else:
                self._log_line("Claude disconnected", "sys")
            return

        if kind in ("say", "note", "mark"):
            text = str(msg.get("text", ""))
            level = msg.get("level", "claude")
            self.claude_line = text
            self.claude_level = level
            self.claude_at = time.time()
            self._log_line("CLAUDE: " + text, "claude")
            return

        if kind == "test":
            n = int(msg.get("n") or 0)
            total = int(msg.get("total") or self.progress[1] or 1)
            self.progress = (n, total)
            self.last_test = msg
            zone = str(msg.get("zone") or "")
            tag = {"green": "green", "amber": "amber", "red": "red"}.get(zone, "dim")
            row = "[%3d/%d] %-11s %12s %12s  %-6s %s" % (
                n, total, str(msg.get("mode") or "")[:11],
                _bytes(msg.get("bytes")) if msg.get("bytes") is not None else "--",
                (_num(msg.get("tokens")) + " tok") if msg.get("tokens") is not None else "--",
                zone or "--",
                ("MOVED" if msg.get("moved") else "same") +
                ((" | " + str(msg.get("note"))) if msg.get("note") else ""))
            self._append(self.test, row, tag, self.TEST_KEEP)
            self.test_note.configure(
                text="last: %s  \u00b7  %s" % (_bytes(msg.get("bytes")), zone or "--"))
            return

        if kind == "watch":
            self.telemetry.retarget(pid=msg.get("pid"), port=msg.get("port"))
            self._log_line("telemetry retargeted -> %s" %
                           (msg.get("pid") or ("port " + str(msg.get("port")))), "sys")
            return

        if kind == "logfile":
            path = msg.get("path")
            if path:
                self.logtail.retarget(path)
                self.log_where.configure(text=path)
                self._log_line("now following %s" % path, "sys")
            return

        if kind in ("hello", "ping"):
            if kind == "hello":
                self._log_line("hello from %s" % msg.get("who", "Claude"), "claude")
            return

        self._log_line("unrecognised frame: %s" % json.dumps(msg, default=str)[:180],
                       "warn")

    # ── repaint ───────────────────────────────────────────────────────────
    def _paint(self):
        try:
            now = time.time()
            self.clock.configure(text=time.strftime("%H:%M:%S"))

            # -- LEDs ------------------------------------------------------
            s = self.link.snapshot()
            since_rx = now - s["last_rx"] if s["last_rx"] else 1e9
            if s["clients"] > 0:
                self.led_link.led.set_steady(0.85, GREEN)
                self.led_link.set_value("connected \u00b7 %s" % s["peer"], GREEN)
            elif since_rx < 25:
                self.led_link.led.set_steady(0.55, GREEN)
                self.led_link.set_value("active %.0fs ago" % since_rx, GREEN)
            elif since_rx < 90:
                self.led_link.led.set_steady(0.35, AMBER)
                self.led_link.set_value("idle %.0fs" % since_rx, AMBER)
            else:
                self.led_link.led.set_steady(0.10, RED)
                self.led_link.set_value("no link", RED)

            if now - s["last_rx"] < 0.9:
                self.led_io.led.flash(CYAN, 1.0)
            elif now - s["last_tx"] < 0.9:
                self.led_io.led.flash(MAGENTA, 0.9)
            self.led_io.set_value("%s in / %s out \u00b7 %s fr" % (
                _bytes(s["rx_bytes"]), _bytes(s["tx_bytes"]),
                _num(s["rx_frames"])), CYAN if since_rx < 25 else FG_DIM)

            t = self.tel or {}
            if t.get("ok"):
                self.led_sut.led.set_steady(0.8, GREEN)
                self.led_sut.set_value("%s  pid %s" % (t.get("name", "?"),
                                                       t.get("pid", "?")), GREEN)
            else:
                self.led_sut.led.set_steady(0.12, RED)
                self.led_sut.set_value(
                    "no process on port %s" % self.telemetry.target_port, RED)

            done, total = self.progress
            if done and done < total:
                self.led_run.led.flash(CYAN, 0.8)
                self.led_run.led.set_steady(0.5, CYAN)
                self.led_run.set_value("prompt %d of %d" % (done, total), CYAN)
            elif done and done >= total:
                self.led_run.led.set_steady(0.8, GREEN)
                self.led_run.set_value("complete", GREEN)
            else:
                self.led_run.led.set_steady(0.08, FG_DIM)
                self.led_run.set_value("idle", FG_DIM)

            for b in (self.led_link, self.led_io, self.led_sut, self.led_run):
                b.led.tick()

            # -- charts ----------------------------------------------------
            for c in self.charts:
                c.redraw()

            if t.get("sys_total"):
                self.b_ram.set(
                    (t.get("sys_used") or 0) / float(t["sys_total"]),
                    "%s / %s  (%.0f%%)" % (_bytes(t.get("sys_used")),
                                           _bytes(t["sys_total"]),
                                           t.get("sys_pct") or 0.0),
                    RED if (t.get("sys_pct") or 0) > 90 else VIOLET)
            self.b_ram.redraw()

            pct = (done / float(total)) if total else 0.0
            self.b_prog.set(pct, "%d / %d   %.0f%%" % (done, total, pct * 100.0),
                            GREEN if done >= total and done else CYAN)
            self.b_prog.redraw()

            # -- facts -----------------------------------------------------
            up = ""
            if t.get("created"):
                up = "%.1f min" % ((now - t["created"]) / 60.0)
            vals = {
                "process": str(t.get("name") or "--"),
                "pid": str(t.get("pid") or "--"),
                "threads": _num(t.get("threads")) if t.get("threads") is not None else "--",
                "handles": _num(t.get("handles")) if t.get("handles") is not None else "--",
                "pagefile": _bytes(t.get("pagefile")) if t.get("pagefile") else "--",
                "peak memory": _bytes(t.get("peak_wset")) if t.get("peak_wset") else "--",
                "page faults": _num(t.get("faults_total")) if t.get("faults_total") else "--",
                "disk read/s": (_bytes(t.get("io_read_s")) + "/s") if t.get("io_read_s") is not None else "--",
                "disk write/s": (_bytes(t.get("io_write_s")) + "/s") if t.get("io_write_s") is not None else "--",
                "uptime": up or "--",
            }
            for k, lbl in self.facts.items():
                lbl.configure(text=vals.get(k, "--"))

            # -- footer ----------------------------------------------------
            age = now - self.claude_at if self.claude_at else 1e9
            self.claude_lbl.configure(
                text=self.claude_line,
                fg=LEVEL_COLOUR.get(self.claude_level, FG) if age < 25
                else _mix(BG_HEAD, LEVEL_COLOUR.get(self.claude_level, FG), 0.55))
            tail = ""
            if self._zoom_note and now - self._zoom_at < 4:
                tail = "   \u00b7   " + self._zoom_note
            elif abs(self._zoom - 1.0) > 0.01:
                tail = "   \u00b7   %d%%" % int(round(self._zoom * 100))
            self.counters.configure(
                text=("panel up %s   \u00b7   link %s in / %s out   \u00b7   "
                      "%s frames%s   \u00b7   Ctrl +/- zoom" % (
                          time.strftime("%H:%M:%S", time.gmtime(now - self.started)),
                          _bytes(s["rx_bytes"]), _bytes(s["tx_bytes"]),
                          _num(s["rx_frames"] + s["tx_frames"]), tail)))
        except Exception:
            pass
        finally:
            self.root.after(120, self._paint)

    def close(self):
        try:
            self.telemetry.stop_flag.set()
            self.logtail.stop_flag.set()
            if self.server:
                self.server.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════════════
#  CLIENT SIDE  -  this is what Claude runs to talk to the panel
# ══════════════════════════════════════════════════════════════════════════
def resolve_port(explicit=None):
    if explicit:
        return int(explicit)
    env = os.environ.get("WTS_PORT")
    if env:
        try:
            return int(env)
        except Exception:
            pass
    side = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "window-test-screen.port")
    try:
        with open(side) as fh:
            return int(fh.read().strip())
    except Exception:
        return 8791


def send(frames, host="127.0.0.1", port=None, timeout=4.0):
    """Send one or more frames and return the panel's replies.  Never raises."""
    port = resolve_port(port)
    if isinstance(frames, (dict, str)):
        frames = [frames]
    out = []
    try:
        with socket.create_connection((host, port), timeout=timeout) as sk:
            sk.settimeout(timeout)
            rf = sk.makefile("rb")
            for frame in frames:
                if isinstance(frame, str):
                    try:
                        frame = json.loads(frame)
                        if not isinstance(frame, dict):
                            raise ValueError
                    except Exception:
                        frame = {"k": "say", "text": str(frame)}
                sk.sendall(json.dumps(frame, default=str).encode("utf-8") + b"\n")
                line = rf.readline()
                if not line:
                    break
                try:
                    out.append(json.loads(line.decode("utf-8", "replace")))
                except Exception:
                    out.append({"ok": False, "raw": line[:200].decode("utf-8", "replace")})
        return out
    except Exception as exc:
        return [{"ok": False, "error": str(exc), "port": port}]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tlamatini window test screen")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--target-port", type=int, default=8000,
                    help="watch whoever listens here (the system under test)")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--log", default=os.path.join(
        "C:\\", "Development", "XAIHT", "Tlamatini", "Tlamatini", "tlamatini.log"))
    ap.add_argument("--total", type=int, default=100)
    ap.add_argument("--zoom", type=float, default=0.8,
                    help="starting text size (1.0 = 100%%; Ctrl +/- changes it live)")
    ap.add_argument("--send", default=None,
                    help="client mode: send one JSON frame (or plain text) and exit")
    args = ap.parse_args(argv)

    if args.send is not None:
        for reply in send(args.send, host=args.host, port=args.port):
            print(json.dumps(reply, default=str))
        return 0

    if tk is None:
        sys.stderr.write("tkinter is not available - cannot open the panel\n")
        return 2
    Panel(args).run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
