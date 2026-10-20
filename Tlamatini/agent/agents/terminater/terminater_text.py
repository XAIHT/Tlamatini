# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""terminater_text.py -- the pure-text half of Terminater (stdlib only, no I/O).

Everything in this module is deterministic and side-effect free, so it is tested
without a shell:

  * ``VTScreen``      a small virtual terminal that turns the raw VT stream a
                      ConPTY produces into real text (cursor moves, erases,
                      wrapping, scrollback) and reports OSC 133 prompt markers;
  * ``plan_typing``   the HUMAN TYPIST: the per-key delays that make Tlamatini
                      type like a person.  There is deliberately NO function here
                      that "pastes" a string -- the engine has no instant path;
  * ``LineTracker``   rebuilds the line the USER is typing from raw keystrokes;
  * ``advise_line``   a deterministic safety net that spots dangerous or
                      mistyped commands while they are being typed;
  * ``key_bytes``     named keys ("ctrl+c", "enter", "up") -> terminal bytes.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections import deque
from typing import Deque, Dict, List, NamedTuple, Optional, Tuple

# --------------------------------------------------------------------------- #
# Human typing                                                                 #
# --------------------------------------------------------------------------- #

#: An experienced ("senior") typist averages 50-60 words per minute.  50 keeps the
#: terminal watchable and leaves the user time to read what is being typed.
DEFAULT_WPM = 50
MIN_WPM = 20
MAX_WPM = 160
#: The fastest any key may follow the previous one.  Real fingers do not go
#: below ~30 ms between keystrokes; this is the floor that makes "instant paste"
#: structurally impossible, whatever a caller asks for.
MIN_KEY_DELAY_S = 0.030
#: TEST HOOK ONLY.  The suites set this below 1.0 so a 200-test run does not take
#: an hour.  It is a module global on purpose: it is NOT reachable from the API,
#: from config.yaml or from the LLM, so nothing at run time can switch typing off.
TEST_TIME_SCALE = 1.0

_SHIFT_CHARS = set('~!@#$%^&*()_+{}|:"<>?')


def clamp_wpm(value) -> int:
    try:
        wpm = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_WPM
    return max(MIN_WPM, min(MAX_WPM, wpm))


class KeyStroke(NamedTuple):
    key: str        # a single character to type ("\r" is Enter, "\t" is Tab)
    delay: float    # seconds to wait BEFORE pressing it


def _split_characters(text: str) -> List[str]:
    """One entry per typed key: a code point, with combining marks kept attached."""
    out: List[str] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def plan_typing(
    text: str,
    wpm: int = DEFAULT_WPM,
    rng: Optional[random.Random] = None,
    submit: bool = False,
    lead_in: bool = True,
) -> List[KeyStroke]:
    """The keystroke schedule for ``text``.

    The model: ``base = 60 / (wpm * 5)`` seconds per key (a "word" is five keys);
    each key is multiplied by a log-normal factor (people are fast and slow in
    bursts, not metronomic), shifted keys cost extra, word boundaries cost extra,
    and about one boundary in twenty-five carries a short "thinking" pause.  The
    result always respects ``MIN_KEY_DELAY_S``.
    """
    rng = rng or random.Random()
    wpm = clamp_wpm(wpm)
    base = 60.0 / (wpm * 5.0)
    scale = TEST_TIME_SCALE if 0 < TEST_TIME_SCALE <= 1.0 else 1.0
    floor = MIN_KEY_DELAY_S * scale
    plan: List[KeyStroke] = []

    def _clip(value: float) -> float:
        return max(floor, value * scale)

    keys = _split_characters(text.replace("\r\n", "\n"))
    previous = ""
    for index, ch in enumerate(keys):
        if ch == "\n":
            ch = "\r"
        jitter = rng.lognormvariate(0.0, 0.30)
        jitter = max(0.45, min(3.0, jitter))
        delay = base * jitter
        if ch in _SHIFT_CHARS or (len(ch) == 1 and ch.isupper()):
            delay += base * 0.35
        if previous == " ":
            delay += base * 0.15
            if rng.random() < 0.04:
                delay += rng.uniform(0.25, 0.70)
        if ch == "\r":
            delay += rng.uniform(0.15, 0.40)
        if index == 0 and lead_in:
            delay += rng.uniform(0.35, 0.80)
        plan.append(KeyStroke(ch, _clip(delay)))
        previous = ch
    if submit:
        # A person re-reads the line before pressing Enter.
        plan.append(KeyStroke("\r", _clip(base * 2.0 + rng.uniform(0.25, 0.60))))
    return plan


def plan_duration(plan: List[KeyStroke]) -> float:
    return float(sum(k.delay for k in plan))


# --------------------------------------------------------------------------- #
# Named keys                                                                   #
# --------------------------------------------------------------------------- #

_NAMED_KEYS: Dict[str, str] = {
    "enter": "\r", "return": "\r", "tab": "\t", "esc": "\x1b", "escape": "\x1b",
    "backspace": "\x7f", "bksp": "\x7f", "space": " ",
    "delete": "\x1b[3~", "del": "\x1b[3~", "insert": "\x1b[2~",
    "up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D",
    "home": "\x1b[H", "end": "\x1b[F", "pageup": "\x1b[5~", "pgup": "\x1b[5~",
    "pagedown": "\x1b[6~", "pgdn": "\x1b[6~", "shift+tab": "\x1b[Z",
    "f1": "\x1bOP", "f2": "\x1bOQ", "f3": "\x1bOR", "f4": "\x1bOS",
    "f5": "\x1b[15~", "f6": "\x1b[17~", "f7": "\x1b[18~", "f8": "\x1b[19~",
    "f9": "\x1b[20~", "f10": "\x1b[21~", "f11": "\x1b[23~", "f12": "\x1b[24~",
}


def key_bytes(name: str) -> Optional[str]:
    """Terminal bytes for one named key, or None when the name is unknown."""
    raw = (name or "").strip()
    if not raw:
        return None
    if len(raw) == 1:
        return raw                      # a bare printable key keeps its case
    token = re.sub(r"\s*[+\-]\s*", "+", raw.lower())
    token = re.sub(r"[\s_]+", "", token).replace("control+", "ctrl+")
    if not token:
        return None
    if token in _NAMED_KEYS:
        return _NAMED_KEYS[token]
    m = re.fullmatch(r"ctrl\+([a-z])", token)
    if m:
        return chr(ord(m.group(1)) - 96)
    if token == "ctrl+[":
        return "\x1b"
    if token == "ctrl+\\":
        return "\x1c"
    if token in ("ctrl+break", "ctrl+pause"):
        return "\x03"
    if len(token) == 1:
        return token
    return None


def parse_key_sequence(spec: str) -> Tuple[List[str], List[str]]:
    """"ctrl+c enter" -> (['\\x03', '\\r'], [])  (second list: names not understood)."""
    out: List[str] = []
    bad: List[str] = []
    for part in re.split(r"[,\s]+", (spec or "").strip()):
        if not part:
            continue
        data = key_bytes(part)
        if data is None:
            bad.append(part)
        else:
            out.append(data)
    return out, bad


# --------------------------------------------------------------------------- #
# The virtual screen                                                           #
# --------------------------------------------------------------------------- #

class OscEvent(NamedTuple):
    kind: str       # 'A' 'B' 'C' 'D' (OSC 133), 'title', 'cwd'
    arg: str
    abs_row: int
    col: int


_WIDE = ("W", "F")


def _char_width(ch: str) -> int:
    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in _WIDE:
        return 2
    return 1


class VTScreen:
    """A fixed-size character grid plus scrollback, driven by a VT/ANSI stream.

    It models what ConPTY really sends: absolute cursor addressing relative to the
    visible viewport, erases, scroll regions and autowrap.  It does NOT model
    colour, the alternate screen or mouse modes -- text is all Terminater needs.
    """

    def __init__(self, cols: int = 120, rows: int = 30, scrollback: int = 20000) -> None:
        self.cols = max(2, int(cols))
        self.rows = max(1, int(rows))
        self.max_scrollback = max(self.rows, int(scrollback))
        self.title = ""
        self.cwd = ""
        self.osc_log: Deque[OscEvent] = deque(maxlen=4000)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self.grid: List[List[str]] = [self._blank() for _ in range(self.rows)]
        self.wrap: List[bool] = [False] * self.rows
        self.scroll: Deque[Tuple[str, bool]] = deque()
        self.dropped = 0
        self.cx = 0
        self.cy = 0
        self.pending = False
        self.top = 0
        self.bottom = self.rows - 1
        self._saved = (0, 0)
        self._st = 0
        self._csi = ""
        self._osc = ""
        self._chars_fed = 0

    def _blank(self) -> List[str]:
        return [" "] * self.cols

    # ------------------------------------------------------------- geometry
    def resize(self, cols: int, rows: int) -> None:
        cols, rows = max(2, int(cols)), max(1, int(rows))
        if cols == self.cols and rows == self.rows:
            return
        if cols != self.cols:
            for r in range(len(self.grid)):
                row = self.grid[r]
                self.grid[r] = (row + [" "] * cols)[:cols]
            self.cols = cols
        if rows < self.rows:
            while len(self.grid) > rows:
                self._push_scrollback(0)
                self.grid.pop(0)
                self.wrap.pop(0)
                self.cy = max(0, self.cy - 1)
        else:
            while len(self.grid) < rows:
                self.grid.append(self._blank())
                self.wrap.append(False)
        self.rows = rows
        self.top, self.bottom = 0, rows - 1
        self.cx = min(self.cx, self.cols - 1)
        self.cy = min(self.cy, self.rows - 1)
        self.pending = False

    def abs_row(self, row: Optional[int] = None) -> int:
        return self.dropped + len(self.scroll) + (self.cy if row is None else row)

    @property
    def total_rows(self) -> int:
        return self.dropped + len(self.scroll) + self.rows

    # ------------------------------------------------------------------- feed
    def feed(self, data: str) -> List[OscEvent]:
        events: List[OscEvent] = []
        self._chars_fed += len(data)
        i, n = 0, len(data)
        while i < n:
            ch = data[i]
            st = self._st
            if st == 0:
                if ch >= " " and ch != "\x7f":
                    self._put(ch)
                elif ch == "\x1b":
                    self._st = 1
                else:
                    self._control(ch)
                i += 1
            elif st == 1:
                i += 1
                self._st = 0
                if ch == "[":
                    self._st, self._csi = 2, ""
                elif ch == "]":
                    self._st, self._osc = 3, ""
                elif ch in "PX^_":
                    self._st = 5
                elif ch in "()*+#%":
                    self._st = 6
                elif ch == "7":
                    self._saved = (self.cx, self.cy)
                elif ch == "8":
                    self.cx, self.cy = self._saved
                    self.pending = False
                elif ch == "M":
                    self._reverse_index()
                elif ch == "D":
                    self._line_feed()
                elif ch == "E":
                    self.cx = 0
                    self._line_feed()
                elif ch == "c":
                    self.reset()
            elif st == 2:
                i += 1
                if "@" <= ch <= "~":
                    self._st = 0
                    self._dispatch_csi(self._csi, ch)
                elif " " <= ch <= "?":
                    if len(self._csi) < 64:
                        self._csi += ch
                else:
                    self._st = 0
            elif st == 3:
                i += 1
                if ch == "\x07":
                    self._st = 0
                    self._finish_osc(events)
                elif ch == "\x1b":
                    self._st = 4
                elif len(self._osc) < 8192:
                    self._osc += ch
            elif st == 4:
                self._st = 0
                if ch == "\\":
                    i += 1
                    self._finish_osc(events)
                else:
                    self._finish_osc(events)
                    self._st = 1
            elif st == 5:
                i += 1
                if ch == "\x07":
                    self._st = 0
                elif ch == "\x1b":
                    self._st = 7
            elif st == 7:
                i += 1
                self._st = 0
            elif st == 6:
                i += 1
                self._st = 0
            else:
                self._st = 0
        return events

    # --------------------------------------------------------------- controls
    def _control(self, ch: str) -> None:
        if ch == "\r":
            self.cx = 0
            self.pending = False
        elif ch in "\n\x0b\x0c":
            self._line_feed()
        elif ch == "\b":
            self.cx = max(0, self.cx - 1)
            self.pending = False
        elif ch == "\t":
            self.cx = min(self.cols - 1, (self.cx // 8 + 1) * 8)
            self.pending = False

    def _put(self, ch: str) -> None:
        width = _char_width(ch)
        if width == 0:
            if self.cx > 0 and not self.pending:
                self.grid[self.cy][self.cx - 1] += ch
            return
        if self.pending:
            self._wrap_line()
        if width == 2 and self.cx == self.cols - 1:
            self._wrap_line()
        row = self.grid[self.cy]
        row[self.cx] = ch
        if width == 2 and self.cx + 1 < self.cols:
            row[self.cx + 1] = ""
        self.cx += width
        if self.cx >= self.cols:
            self.cx = self.cols - 1
            self.pending = True

    def _wrap_line(self) -> None:
        self.cx = 0
        self.pending = False
        self._line_feed()
        self.wrap[self.cy] = True

    def _line_feed(self) -> None:
        self.pending = False
        if self.cy == self.bottom:
            self._scroll_up(1)
        elif self.cy < self.rows - 1:
            self.cy += 1

    def _reverse_index(self) -> None:
        self.pending = False
        if self.cy == self.top:
            self._scroll_down(1)
        elif self.cy > 0:
            self.cy -= 1

    def _push_scrollback(self, row_index: int) -> None:
        self.scroll.append(("".join(self.grid[row_index]), self.wrap[row_index]))
        while len(self.scroll) > self.max_scrollback:
            self.scroll.popleft()
            self.dropped += 1

    def _scroll_up(self, count: int) -> None:
        for _ in range(max(1, count)):
            if self.top == 0 and self.bottom == self.rows - 1:
                self._push_scrollback(0)
            del self.grid[self.top]
            del self.wrap[self.top]
            self.grid.insert(self.bottom, self._blank())
            self.wrap.insert(self.bottom, False)

    def _scroll_down(self, count: int) -> None:
        for _ in range(max(1, count)):
            del self.grid[self.bottom]
            del self.wrap[self.bottom]
            self.grid.insert(self.top, self._blank())
            self.wrap.insert(self.top, False)

    # -------------------------------------------------------------------- CSI
    @staticmethod
    def _params(raw: str) -> List[Optional[int]]:
        body = raw.lstrip("?<=>")
        out: List[Optional[int]] = []
        for part in body.replace(":", ";").split(";"):
            part = part.strip(" ")
            if part.isdigit():
                out.append(int(part))
            else:
                out.append(None)
        return out or [None]

    def _dispatch_csi(self, raw: str, final: str) -> None:
        private = raw[:1] in ("?", "<", "=", ">")
        if private:
            return  # modes (cursor visibility, bracketed paste, win32-input...): not text
        p = self._params(raw)

        def n(index: int, default: int = 1) -> int:
            if index < len(p) and p[index] not in (None, 0):
                return int(p[index])  # type: ignore[arg-type]
            return default

        self.pending = False
        if final == "A":
            self.cy = max(self.top if self.cy >= self.top else 0, self.cy - n(0))
        elif final == "B":
            self.cy = min(self.bottom if self.cy <= self.bottom else self.rows - 1, self.cy + n(0))
        elif final == "C":
            self.cx = min(self.cols - 1, self.cx + n(0))
        elif final == "D":
            self.cx = max(0, self.cx - n(0))
        elif final == "E":
            self.cy = min(self.rows - 1, self.cy + n(0))
            self.cx = 0
        elif final == "F":
            self.cy = max(0, self.cy - n(0))
            self.cx = 0
        elif final == "G":
            self.cx = min(self.cols - 1, n(0) - 1)
        elif final in ("H", "f"):
            self.cy = min(self.rows - 1, n(0) - 1)
            self.cx = min(self.cols - 1, n(1) - 1)
        elif final == "d":
            self.cy = min(self.rows - 1, n(0) - 1)
        elif final == "J":
            mode = p[0] or 0
            if mode == 0:
                self._erase_cells(self.cy, self.cx, self.cols)
                for r in range(self.cy + 1, self.rows):
                    self._erase_row(r)
            elif mode == 1:
                for r in range(0, self.cy):
                    self._erase_row(r)
                self._erase_cells(self.cy, 0, self.cx + 1)
            elif mode in (2, 3):
                for r in range(self.rows):
                    self._erase_row(r)
                if mode == 3:
                    self.dropped += len(self.scroll)
                    self.scroll.clear()
        elif final == "K":
            mode = p[0] or 0
            if mode == 0:
                self._erase_cells(self.cy, self.cx, self.cols)
            elif mode == 1:
                self._erase_cells(self.cy, 0, self.cx + 1)
            else:
                self._erase_row(self.cy)
        elif final == "X":
            self._erase_cells(self.cy, self.cx, min(self.cols, self.cx + n(0)))
        elif final == "@":
            row = self.grid[self.cy]
            count = min(n(0), self.cols - self.cx)
            row[self.cx:self.cx] = [" "] * count
            del row[self.cols:]
        elif final == "P":
            row = self.grid[self.cy]
            count = min(n(0), self.cols - self.cx)
            del row[self.cx:self.cx + count]
            row.extend([" "] * count)
        elif final == "L":
            if self.top <= self.cy <= self.bottom:
                for _ in range(min(n(0), self.bottom - self.cy + 1)):
                    del self.grid[self.bottom]
                    del self.wrap[self.bottom]
                    self.grid.insert(self.cy, self._blank())
                    self.wrap.insert(self.cy, False)
        elif final == "M":
            if self.top <= self.cy <= self.bottom:
                for _ in range(min(n(0), self.bottom - self.cy + 1)):
                    del self.grid[self.cy]
                    del self.wrap[self.cy]
                    self.grid.insert(self.bottom, self._blank())
                    self.wrap.insert(self.bottom, False)
        elif final == "S":
            self._scroll_up(n(0))
        elif final == "T":
            self._scroll_down(n(0))
        elif final == "r":
            top = n(0) - 1
            bottom = (p[1] - 1) if len(p) > 1 and p[1] else self.rows - 1
            if 0 <= top < bottom < self.rows:
                self.top, self.bottom = top, bottom
            else:
                self.top, self.bottom = 0, self.rows - 1
            self.cx, self.cy = 0, 0
        elif final == "s":
            self._saved = (self.cx, self.cy)
        elif final == "u":
            self.cx, self.cy = self._saved
        # 'm' (colour), 'n', 'c', 'q', 't' ... carry no text: ignored on purpose.

    def _erase_row(self, r: int) -> None:
        self.grid[r] = self._blank()
        self.wrap[r] = False

    def _erase_cells(self, r: int, start: int, stop: int) -> None:
        row = self.grid[r]
        for c in range(max(0, start), min(self.cols, stop)):
            row[c] = " "

    # -------------------------------------------------------------------- OSC
    def _finish_osc(self, events: List[OscEvent]) -> None:
        text, self._osc = self._osc, ""
        head, _, rest = text.partition(";")
        pos = (self.abs_row(), self.cx)
        if head in ("0", "2"):
            self.title = rest
            events.append(OscEvent("title", rest, *pos))
        elif head == "133":
            kind, _, arg = rest.partition(";")
            kind = kind[:1].upper()
            if kind in ("A", "B", "C", "D"):
                ev = OscEvent(kind, arg, *pos)
                events.append(ev)
                self.osc_log.append(ev)
        elif head == "9":
            sub, _, value = rest.partition(";")
            if sub == "9":
                self.cwd = value.strip().strip('"')
                events.append(OscEvent("cwd", self.cwd, *pos))

    # ---------------------------------------------------------------- reading
    def _row_text(self, abs_row: int) -> Optional[Tuple[str, bool]]:
        if abs_row < self.dropped:
            return None
        rel = abs_row - self.dropped
        if rel < len(self.scroll):
            return self.scroll[rel]
        idx = rel - len(self.scroll)
        if 0 <= idx < self.rows:
            return "".join(self.grid[idx]), self.wrap[idx]
        return None

    def logical_lines(self, first: int, last: int, start_col: int = 0) -> Tuple[List[str], bool]:
        """Text of absolute rows ``first .. last`` inclusive, wrapped rows rejoined.

        Returns ``(lines, truncated)``; ``truncated`` is True when ``first`` has
        already scrolled out of the retained history.
        """
        truncated = first < self.dropped
        first = max(first, self.dropped)
        lines: List[str] = []
        current: Optional[str] = None
        for r in range(first, last + 1):
            info = self._row_text(r)
            if info is None:
                break
            text, wrapped = info
            if r == first and start_col:
                text = text[start_col:]
            nxt = self._row_text(r + 1) if r + 1 <= last else None
            keep_tail = bool(nxt and nxt[1])
            if not keep_tail:
                text = text.rstrip()
            if wrapped and current is not None and r != first:
                current += text
            else:
                if current is not None:
                    lines.append(current.rstrip())
                current = text
        if current is not None:
            lines.append(current.rstrip())
        return lines, truncated

    def text(self, last_lines: Optional[int] = None) -> str:
        first = self.dropped
        last = self.dropped + len(self.scroll) + self.rows - 1
        lines, _ = self.logical_lines(first, last)
        while lines and not lines[-1]:
            lines.pop()
        if last_lines:
            lines = lines[-int(last_lines):]
        return "\n".join(lines)

    def visible_text(self) -> str:
        top = self.dropped + len(self.scroll)
        lines, _ = self.logical_lines(top, top + self.rows - 1)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    def cursor_line_text(self, from_col: int = 0) -> str:
        """The logical line holding the cursor (wrapped rows joined), from ``from_col``."""
        row = self.abs_row()
        start = row
        while True:
            info = self._row_text(start)
            if info is None or not info[1] or start <= self.dropped:
                break
            start -= 1
        end = row
        while True:
            nxt = self._row_text(end + 1)
            if nxt is None or not nxt[1]:
                break
            end += 1
        lines, _ = self.logical_lines(start, end, start_col=from_col)
        return "".join(lines) if lines else ""

    def last_nonempty_line(self) -> str:
        top = self.dropped + len(self.scroll)
        for r in range(top + self.rows - 1, top - 1, -1):
            info = self._row_text(r)
            if info and info[0].strip():
                return info[0].rstrip()
        return ""


# --------------------------------------------------------------------------- #
# Misc text helpers                                                            #
# --------------------------------------------------------------------------- #

_ANSI_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"      # OSC ... BEL | ST
    r"|\x1b\[[0-?]*[ -/]*[@-~]"                # CSI
    r"|\x1b[PX^_][^\x1b]*\x1b\\"               # DCS / SOS / PM / APC
    r"|\x1b[()*+#%][0-~]"                      # charset
    r"|\x1b[=>78MDEc]"                         # single escapes
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


#: Does the last visible line look like a program asking the user something?
INPUT_REQUEST_RE = re.compile(
    r"(\[[YyNn]\s*/\s*[YyNn]\]|\([YyNn]\s*/\s*[YyNn]\)|\(yes\s*/\s*no\)|\[Y\]es|"
    r"press any key|press enter|hit enter|pass(?:word|phrase)\s*:|"
    r"terminate batch job|continue\s*\?|proceed\s*\?|overwrite .{0,60}\?|"
    r"are you sure|enter (?:a |the |your )?[\w .-]{0,40}:\s*$|\?\s*$|"
    r"^[A-Za-z][\w .'-]{0,38}:\s*$)",          # a short label ending in a colon: 'Name:', 'Username:'
    re.IGNORECASE,
)


def looks_like_input_request(line: str) -> bool:
    return bool(line and INPUT_REQUEST_RE.search(line.strip()))


# --------------------------------------------------------------------------- #
# The line the USER is typing                                                  #
# --------------------------------------------------------------------------- #

class LineTracker:
    """Rebuilds the user's current command line from raw terminal input bytes."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.buf: List[str] = []
        self.pos = 0
        self.uncertain = False
        self.pasted = False
        self.last_line = ""          # the line as it was when Enter was pressed
        self._esc = ""
        self._paste = False
        self._paste_cr = False

    @property
    def line(self) -> str:
        return "".join(self.buf)

    def feed(self, data: str) -> List[str]:
        """Consume input; returns events: 'submit', 'cancel', 'clear', 'edit'."""
        events: List[str] = []
        if data == "\x1b" and not self._esc:
            # A chunk that is exactly ESC is the Esc KEY (arrows etc. arrive whole).
            # It clears the line in cmd.exe and in PSReadLine.
            self._submit_reset()
            return ["clear"]
        for ch in data:
            if self._esc:
                self._esc += ch
                if len(self._esc) == 2:
                    if ch not in "[O":
                        self._esc = ""      # Alt+<key>: carries no text
                elif self._esc[1] == "[":
                    if "@" <= ch <= "~":
                        self._csi(self._esc, events)
                        self._esc = ""
                    elif len(self._esc) > 16:
                        self._esc = ""
                else:
                    self._esc = ""          # SS3 sequence (ESC O x): F1-F4, Home/End
                continue
            if ch == "\x1b":
                self._esc = "\x1b"
                continue
            if self._paste:
                if ch in "\r\n":
                    # a CRLF pair (every Windows clipboard) is ONE line break, not two
                    if not (ch == "\n" and self._paste_cr):
                        self._insert(" ")
                    self._paste_cr = ch == "\r"
                elif ch >= " ":
                    self._insert(ch)
                    self._paste_cr = False
                continue
            if ch in "\r\n":
                events.append("submit")
                self.last_line = self.line
                self._submit_reset()
            elif ch in ("\x7f", "\b"):
                if self.pos > 0:
                    del self.buf[self.pos - 1]
                    self.pos -= 1
                events.append("edit")
            elif ch == "\x03":
                events.append("cancel")
                self._submit_reset()
            elif ch == "\x15":
                del self.buf[:self.pos]
                self.pos = 0
                events.append("edit")
            elif ch == "\x17":
                while self.pos > 0 and self.buf[self.pos - 1] == " ":
                    del self.buf[self.pos - 1]
                    self.pos -= 1
                while self.pos > 0 and self.buf[self.pos - 1] != " ":
                    del self.buf[self.pos - 1]
                    self.pos -= 1
                events.append("edit")
            elif ch == "\x01":
                self.pos = 0
            elif ch == "\x05":
                self.pos = len(self.buf)
            elif ch == "\t":
                self.uncertain = True
                events.append("edit")
            elif ch >= " ":
                self._insert(ch)
                events.append("edit")
        return events

    def _insert(self, ch: str) -> None:
        self.buf.insert(self.pos, ch)
        self.pos += 1

    def _submit_reset(self) -> None:
        self.buf = []
        self.pos = 0
        self.uncertain = False
        self.pasted = False

    def _csi(self, seq: str, events: List[str]) -> None:
        body = seq[2:]
        if body == "200~":
            self._paste = True
            self.pasted = True
        elif body == "201~":
            self._paste = False
        elif body in ("A", "B"):
            self.uncertain = True            # history navigation: the text is not ours
            events.append("edit")
        elif body == "D":
            self.pos = max(0, self.pos - 1)
        elif body == "C":
            self.pos = min(len(self.buf), self.pos + 1)
        elif body in ("H", "1~"):
            self.pos = 0
        elif body in ("F", "4~"):
            self.pos = len(self.buf)
        elif body == "3~":
            if self.pos < len(self.buf):
                del self.buf[self.pos]
            events.append("edit")


# --------------------------------------------------------------------------- #
# The advisor: danger and typo detection while the user types                  #
# --------------------------------------------------------------------------- #

class Advice(NamedTuple):
    severity: str      # 'danger' | 'warning' | 'hint'
    code: str
    message: str
    suggestion: str = ""


_DANGER_RULES: List[Tuple[str, str, str, str]] = [
    (r"\bformat\s+[a-z]:", "format-drive", "This formats a whole drive and erases everything on it.", ""),
    (r"\b(?:rd|rmdir)\s+(?:/[sq]\s*)+[\"']?[a-z]:\\?[\"']?(?:\s|$)", "rmdir-root",
     "This deletes an entire drive's folder tree.", ""),
    (r"\bdel\s+(?:/[a-z]\s*)*[\"']?[a-z]:\\(?:\*|\*\.\*)?[\"']?(?:\s|$)", "del-root",
     "This deletes files at the root of a drive.", ""),
    (r"remove-item\b[^|;]*-recurse[^|;]*\s[\"']?[a-z]:\\?[\"']?(?:\s|$)", "ps-remove-root",
     "This recursively deletes an entire drive's contents.", ""),
    (r"\bformat-volume\b|\bclear-disk\b|\binitialize-disk\b", "ps-disk",
     "This erases or re-initialises a disk.", ""),
    (r"\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+(?:/|~|\*)(?:\s|$)", "rm-rf-root",
     "This recursively deletes the root or home directory.", ""),
    (r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:", "fork-bomb", "This is a fork bomb: it will hang the machine.", ""),
    (r"\bdiskpart\b", "diskpart", "diskpart edits disk partitions; a wrong 'select' loses data.", ""),
    (r"\breg\s+delete\s+hk(?:lm|cr|u)\b", "reg-delete", "This deletes registry keys.", ""),
    (r"\b(?:shutdown|stop-computer|restart-computer)\b", "power", "This shuts down or restarts the machine.", ""),
    (r"\b(?:iwr|invoke-webrequest|irm|invoke-restmethod|curl|wget)\b[^|]*\|\s*(?:iex|invoke-expression)\b",
     "remote-exec", "This downloads code from the internet and runs it immediately.", ""),
]

# first-token typos / wrong-shell habits -> (message, suggestion)
_TYPOS: Dict[str, Tuple[str, str]] = {
    "gti": ("Probably a typo.", "git"), "gut": ("Probably a typo.", "git"),
    "pyhton": ("Probably a typo.", "python"), "pytohn": ("Probably a typo.", "python"),
    "pyton": ("Probably a typo.", "python"), "pythn": ("Probably a typo.", "python"),
    "npn": ("Probably a typo.", "npm"), "nmp": ("Probably a typo.", "npm"),
    "ndoe": ("Probably a typo.", "node"), "cler": ("Probably a typo.", "clear / cls"),
    "claer": ("Probably a typo.", "cls"), "ipconfg": ("Probably a typo.", "ipconfig"),
    "pign": ("Probably a typo.", "ping"), "pnig": ("Probably a typo.", "ping"),
    "tasklsit": ("Probably a typo.", "tasklist"), "netsat": ("Probably a typo.", "netstat"),
}
_CMD_HABITS: Dict[str, Tuple[str, str]] = {
    "ls": ("cmd.exe has no 'ls'.", "dir"), "cat": ("cmd.exe has no 'cat'.", "type <file>"),
    "clear": ("cmd.exe has no 'clear'.", "cls"), "rm": ("cmd.exe has no 'rm'.", "del <file>"),
    "mv": ("cmd.exe has no 'mv'.", "move <src> <dst>"), "cp": ("cmd.exe has no 'cp'.", "copy <src> <dst>"),
    "grep": ("cmd.exe has no 'grep'.", "findstr"), "touch": ("cmd.exe has no 'touch'.", "type nul > <file>"),
    "pwd": ("cmd.exe has no 'pwd'.", "cd"), "which": ("cmd.exe has no 'which'.", "where <name>"),
    "man": ("cmd.exe has no 'man'.", "help <command>"), "ifconfig": ("Windows uses ipconfig.", "ipconfig"),
    "sudo": ("There is no sudo on Windows.", "open an elevated terminal"),
}
_PS_HABITS: Dict[str, Tuple[str, str]] = {
    "ifconfig": ("Windows uses ipconfig.", "ipconfig"),
    "sudo": ("There is no sudo on Windows.", "open an elevated terminal"),
    "touch": ("PowerShell has no 'touch'.", "New-Item <file>"),
    "grep": ("PowerShell uses Select-String.", "Select-String"),
    "which": ("PowerShell uses Get-Command.", "Get-Command <name>"),
}


def advise_line(line: str, kind: str = "cmd") -> List[Advice]:
    """Danger first, then typos/habits.  Pure and cheap: safe to call per keystroke."""
    text = (line or "").strip()
    if not text:
        return []
    out: List[Advice] = []
    low = text.lower()
    for pattern, code, message, suggestion in _DANGER_RULES:
        if re.search(pattern, low):
            sev = "danger" if code in {
                "format-drive", "rmdir-root", "del-root", "ps-remove-root", "ps-disk",
                "rm-rf-root", "fork-bomb"} else "warning"
            out.append(Advice(sev, code, message, suggestion))
    if " " in text:
        first = low.split()[0]
        table = _CMD_HABITS if kind == "cmd" else _PS_HABITS
        for source, label in ((_TYPOS, "typo"), (table, "wrong-shell")):
            if first in source:
                msg, sug = source[first]
                out.append(Advice("hint", f"{label}:{first}", msg, sug))
                break
        if kind != "cmd" and re.match(r"^(ls|dir)\s+-[a-z]*[la]", low):
            out.append(Advice("hint", "ps-flags", "PowerShell's ls/dir does not take Linux flags.",
                              "Get-ChildItem -Force"))
        if kind != "cmd" and re.match(r"^rm\s+-[a-z]*r", low) and "remove-item" not in low:
            out.append(Advice("hint", "ps-rm-flags", "In PowerShell use Remove-Item.",
                              "Remove-Item -Recurse -Force <path>"))
    return out


def sanitize_title(value: str, default: str = "terminal", limit: int = 40) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    return cleaned[:limit] or default
