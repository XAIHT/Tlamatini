# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""terminater_engine.py -- sessions, the hub and the action API of Terminater.

This single module is shared by THREE callers, each with a different job:

  * the Django process        -> ``terminal_hub.py`` owns one ``TerminalHub`` and
                                 feeds it to the browser (WebSocket) and to the
                                 pool agents (loopback HTTP);
  * the pool agent            -> ``terminater.py`` talks to that hub, or, when no
                                 hub is reachable (standalone / "independent of
                                 Tlamatini"), builds a private ``TerminalHub``
                                 and drives real shells itself;
  * the test suites           -> exercise every behaviour against REAL cmd.exe and
                                 powershell.exe processes.

It is stdlib-only and loads its two siblings (``terminater_conpty`` and
``terminater_text``) from its own directory, so a pool copy of the template runs
anywhere with no import path set up.

THE RULES THIS ENGINE ENFORCES (do NOT weaken -- each one is a user requirement)
-------------------------------------------------------------------------------
1. Tlamatini TYPES.  There is no code path that writes a string into a terminal
   in one go: ``TerminalSession.type_text`` feeds one key at a time through the
   human typist (``terminater_text.plan_typing``), with real, jittered delays
   and a hard per-key floor.  No "paste", no "instant" switch, no raw write.
2. Every command's result is kept IN FULL (up to a stated cap) and returned with
   an honest ``truncated`` flag -- never silently cut.
3. A hung command is DETECTED (no output for ``hang_seconds``), reported, and can
   be aborted (Ctrl+C -> Ctrl+C -> kill the shell's children) without losing the
   terminal; a terminal itself can be closed gracefully or killed forcefully with
   its whole process tree.
4. The USER always wins: a key the user presses is never lost, Esc/Ctrl+C stops
   Tlamatini's typing at once, and a command line Tlamatini only half-typed is
   handed over for the user to finish (``<<USER:hint>>``).
5. Everything the user types is observable in real time (``watch_user``) so
   Tlamatini can help, and ``advise_line`` warns about dangerous or mistyped
   commands without waiting for a model round trip.
6. NOTHING IS REPORTED AS TYPED UNLESS THE SCREEN SHOWS IT.  A line left on the prompt
   (``submit=false``) is read back from the virtual screen and reported as ``typed``
   only when it is there (``typing_unverified`` otherwise); the echo of a submitted
   command is compared with what was typed; a line already waiting on the prompt is
   never typed over or duplicated.  A flag that is not a clean yes/no never presses
   Enter for the caller, and a terminal that is not there is refused, not invented.
"""

from __future__ import annotations

import base64
import itertools
import os
import random
import re
import sys
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import terminater_conpty as _cp  # noqa: E402
import terminater_text as _tx  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

KINDS = ("cmd", "powershell", "pwsh")
KIND_ALIASES = {
    "cmd": "cmd", "cmd.exe": "cmd", "command prompt": "cmd", "commandprompt": "cmd", "dos": "cmd",
    "powershell": "powershell", "ps": "powershell", "powershell.exe": "powershell",
    "windows powershell": "powershell", "posh": "powershell",
    "pwsh": "pwsh", "pwsh.exe": "pwsh", "powershell 7": "pwsh", "powershell7": "pwsh",
}
LAYOUTS = ("tabs", "tile", "tile-h", "tile-v", "grid")
AREAS = ("dock", "full")

DEFAULT_COLS = 120
DEFAULT_ROWS = 30
RAW_RING_CHARS = 400_000          # replay buffer for a reconnecting browser
MAX_OUTPUT_CHARS = 400_000        # per command, kept in full below this
MAX_COMMANDS_KEPT = 300
HANG_SECONDS_DEFAULT = 45
INPUT_IDLE_SECONDS = 1.6          # silent this long + a question on screen => awaiting input
OSC_MARKER_GRACE = 6.0            # no OSC 133 within this after start => prompt-regex mode
PROMPT_RE = {
    "cmd": re.compile(r"^[A-Za-z]:\\[^<>|?*\"]*>\s*$"),
    "powershell": re.compile(r"^PS [^>]*>\s*$"),
    "pwsh": re.compile(r"^PS [^>]*>\s*$"),
}

_SCRUBBED_ENV = ("TLAMATINI_TERMINATER_TOKEN", "TLAMATINI_TERMINATER_URL", "DJANGO_SECRET_KEY")

# States
ST_STARTING = "starting"
ST_PROMPT = "prompt"
ST_TYPING = "typing"
ST_AWAITING_USER = "awaiting_user"
ST_RUNNING = "running"
ST_EXITED = "exited"
ST_CLOSED = "closed"


class TerminaterError(RuntimeError):
    """A request the engine refuses, with a human sentence in ``args[0]``."""

    def __init__(self, message: str, code: str = "refused") -> None:
        super().__init__(message)
        self.code = code


def normalize_kind(value: Any, default: str = "powershell") -> str:
    token = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not token:
        return default
    kind = KIND_ALIASES.get(token)
    if not kind:
        raise TerminaterError(
            f"Unknown terminal type {value!r}. Terminater hosts: cmd | powershell | pwsh.", "bad_kind")
    return kind


def _which(*names: str) -> Optional[str]:
    import shutil

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def kind_available(kind: str) -> bool:
    return bool(_resolve_shell(kind, quiet=True))


def available_kinds() -> List[str]:
    return [k for k in KINDS if kind_available(k)]


def _resolve_shell(kind: str, quiet: bool = False) -> Optional[str]:
    windir = os.environ.get("SystemRoot") or r"C:\Windows"
    if kind == "cmd":
        path = os.path.join(windir, "System32", "cmd.exe")
        return path if os.path.isfile(path) else _which("cmd.exe")
    if kind == "powershell":
        path = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        return path if os.path.isfile(path) else _which("powershell.exe")
    if kind == "pwsh":
        return _which("pwsh.exe", "pwsh")
    return None


_PS_SETUP = r"""
$ErrorActionPreference = 'SilentlyContinue'
$global:__tl_prev = $function:prompt
$global:__tl_first = $true
function global:prompt {
    $__ok = $?
    $__le = $global:LASTEXITCODE
    $__code = if ($__ok) { 0 } elseif ($__le) { $__le } else { 1 }
    $e = [char]27
    $o = ''
    if (-not $global:__tl_first) { $o += "$e]133;D;$__code$e\" }
    $global:__tl_first = $false
    $o += "$e]133;A$e\"
    $o += "$e]9;9;`"$($executionContext.SessionState.Path.CurrentLocation.ProviderPath)`"$e\"
    $p = & $global:__tl_prev
    "$o$p$e]133;B$e\"
}
try { Set-PSReadLineOption -PredictionSource None } catch { }
$ErrorActionPreference = 'Continue'
"""


def build_shell_launch(kind: str, load_profile: bool = True) -> Tuple[str, Dict[str, str]]:
    """``(command line, environment overrides)`` for a shell of this kind."""
    exe = _resolve_shell(kind)
    if not exe:
        raise TerminaterError(f"{kind} is not installed on this machine.", "kind_unavailable")
    if kind == "cmd":
        # OSC 133 A/B bracket the prompt; OSC 9;9 carries the working directory.
        prompt = "$E]133;A$E\\$E]9;9;$P$E\\$P$G$E]133;B$E\\"
        return f'"{exe}" /D /K chcp 65001>nul', {"PROMPT": prompt}
    encoded = base64.b64encode(_PS_SETUP.encode("utf-16-le")).decode("ascii")
    flags = "-NoLogo -NoExit" + ("" if load_profile else " -NoProfile")
    return f'"{exe}" {flags} -ExecutionPolicy Bypass -EncodedCommand {encoded}', {}


# --------------------------------------------------------------------------- #
# Records                                                                      #
# --------------------------------------------------------------------------- #

class CommandRecord:
    """One command that ran in a terminal (typed by Tlamatini or by the user)."""

    def __init__(self, cid: int, source: str) -> None:
        self.id = cid
        self.source = source                 # 'tlamatini' | 'user'
        self.text = ""
        self.started = time.time()
        self.ended: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.exit_known = False
        self.output = ""
        self.truncated = False
        self.hung = False
        self.aborted_by = ""
        self.state = "running"               # running | completed | aborted | killed | hung
        self.start_row = 0
        self.start_col = 0

    def duration(self) -> float:
        return round(((self.ended or time.time()) - self.started), 3)

    def public(self, with_output: bool = True, limit: int = 0, offset: int = 0) -> Dict[str, Any]:
        out = self.output
        total = len(out)
        if offset:
            out = out[offset:]
        more = False
        if limit and len(out) > limit:
            out, more = out[:limit], True
        data: Dict[str, Any] = {
            "id": self.id, "source": self.source, "command": self.text, "state": self.state,
            "exit_code": self.exit_code if self.exit_known else None,
            "exit_known": self.exit_known, "duration_seconds": self.duration(),
            "started": self.started, "ended": self.ended, "hung": self.hung,
            "aborted_by": self.aborted_by, "output_chars": total,
            "truncated": self.truncated or more, "more": more,
        }
        if with_output:
            data["output"] = out
        return data


# --------------------------------------------------------------------------- #
# One terminal                                                                 #
# --------------------------------------------------------------------------- #

class TerminalSession:
    """A real shell inside a pseudo console, watched, typed into and recorded."""

    def __init__(
        self,
        sid: str,
        kind: str,
        title: str,
        cwd: str,
        emit: Callable[[Dict[str, Any]], None],
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
        load_profile: bool = True,
        hang_seconds: float = HANG_SECONDS_DEFAULT,
        advisor: bool = True,
    ) -> None:
        self.id = sid
        self.kind = kind
        self.title = _tx.sanitize_title(title, default=sid)
        self.cwd = cwd or ""
        self.created = time.time()
        self.cols, self.rows = cols, rows
        self.hang_seconds = max(3.0, float(hang_seconds or HANG_SECONDS_DEFAULT))
        self.advisor_enabled = bool(advisor)
        self._emit_cb = emit

        self.cv = threading.Condition(threading.RLock())
        self.state = ST_STARTING
        self.state_since = time.time()
        self.screen = _tx.VTScreen(cols, rows)
        self.seq = 0
        self.raw: Deque[Tuple[int, str]] = deque()
        self.raw_chars = 0
        self.last_output_at = time.time()
        self.started_at = time.time()
        self.markers_seen = False
        self.commands: List[CommandRecord] = []
        self._cid = itertools.count(1)
        self.current: Optional[CommandRecord] = None
        self.suspected_hung = False
        self.awaiting_input_hint = ""
        self.exit_code: Optional[int] = None

        # typing / hand-over
        self._type_lock = threading.Lock()
        self._abort_typing = threading.Event()
        self._typing_by = ""
        self.handover_hint = ""
        self.handover_remaining: List[str] = []
        self.handover_secret = False
        self.handover_resume = threading.Event()
        self._handover_prefix = ""

        # the user
        self.tracker = _tx.LineTracker()
        self.user_keys: Deque[Tuple[int, float, str]] = deque(maxlen=4000)
        self._key_seq = itertools.count(1)
        self.user_line_screen: Optional[str] = None
        self.user_submitted: Deque[Tuple[int, float, str]] = deque(maxlen=200)
        self.last_user_key_at = 0.0
        self.warnings: Deque[Dict[str, Any]] = deque(maxlen=60)
        self._last_advice_line = ""
        self._advised: set = set()
        self.secret_input = False

        self._decoder = _utf8_decoder()
        self.pty: Optional[_cp.ConPty] = None
        self._reader: Optional[threading.Thread] = None
        self._closed = False

        cmdline, env_extra = build_shell_launch(kind, load_profile=load_profile)
        env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED_ENV}
        env.update(env_extra)
        env["TERM_PROGRAM"] = "Tlamatini-Terminater"
        self.pty = _cp.ConPty(cmdline, cwd=self.cwd or None, env=env, cols=cols, rows=rows)
        self.pid = self.pty.pid
        self.pty.attach_reader()
        self._reader = threading.Thread(target=self._read_loop, name=f"term-{sid}-read", daemon=True)
        self._reader.start()

    # ---------------------------------------------------------------- emitting
    def emit(self, event: Dict[str, Any]) -> None:
        event.setdefault("id", self.id)
        try:
            self._emit_cb(event)
        except Exception:  # noqa: BLE001 -- a broken listener must never stop the terminal
            pass

    def _set_state(self, state: str, **extra: Any) -> None:
        with self.cv:
            if self.state == state and not extra:
                return
            old = self.state
            self.state = state
            self.state_since = time.time()
            self.cv.notify_all()
        self.emit({"t": "state", "state": state, "previous": old, **extra})

    # ------------------------------------------------------------------ output
    def _read_loop(self) -> None:
        pty = self.pty
        while pty is not None:
            data = pty.read()
            if not data:
                break
            text = self._decoder.decode(data)
            if text:
                self._on_output(text)
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self._on_output(tail)
        self._on_exit()

    def _on_output(self, text: str) -> None:
        with self.cv:
            events = self.screen.feed(text)
            self.seq += 1
            seq = self.seq
            self.raw.append((seq, text))
            self.raw_chars += len(text)
            while self.raw_chars > RAW_RING_CHARS and len(self.raw) > 1:
                _, old = self.raw.popleft()
                self.raw_chars -= len(old)
            self.last_output_at = time.time()
            self.suspected_hung = False
            self.awaiting_input_hint = ""
            if self.screen.cwd and self.screen.cwd != self.cwd:
                self.cwd = self.screen.cwd
            for ev in events:
                self._on_osc(ev)
            self.cv.notify_all()
        self.emit({"t": "out", "seq": seq, "d": text})

    def _on_osc(self, ev: "_tx.OscEvent") -> None:
        if ev.kind == "title":
            self.emit({"t": "title", "title": ev.arg})
            return
        if ev.kind == "cwd":
            self.emit({"t": "cwd", "cwd": ev.arg})
            return
        self.markers_seen = True
        if ev.kind == "D":
            code = None
            try:
                code = int(ev.arg.split(";")[0])
            except (ValueError, IndexError):
                pass
            if self.current is not None:
                if code is not None:
                    self.current.exit_code = code
                    self.current.exit_known = True
            return
        if ev.kind == "B":
            self._prompt_ready(ev.abs_row, ev.col)
        elif ev.kind == "A":
            self._finish_current(ev.abs_row)

    def _prompt_ready(self, row: int, col: int) -> None:
        self._prompt_row, self._prompt_col = row, col
        if self.state in (ST_STARTING, ST_RUNNING):
            self._set_state(ST_PROMPT)
        elif self.state == ST_PROMPT:
            self.cv.notify_all()

    def _finish_current(self, prompt_abs_row: int, end_row: Optional[int] = None) -> None:
        rec = self.current
        if rec is None:
            return
        self.current = None
        end = (end_row if end_row is not None else prompt_abs_row) - 1
        out, truncated = self._command_output(rec, max(rec.start_row, end))
        rec.output = out
        rec.truncated = truncated or rec.truncated
        rec.ended = time.time()
        if rec.state == "running":
            rec.state = "hung" if rec.hung else "completed"
        self.suspected_hung = False
        self.awaiting_input_hint = ""
        self.emit({"t": "command", "command": rec.public(with_output=False)})

    def _command_output(self, rec: CommandRecord, end: int) -> Tuple[str, bool]:
        """Read this command's retained output, including when no prompt follows it."""
        lost_start = rec.start_row < self.screen.dropped
        lines, truncated = self.screen.logical_lines(
            rec.start_row, end, 0 if lost_start else rec.start_col)
        if lines and not lost_start:
            echoed = lines[0]
            if not rec.text:
                rec.text = echoed.strip()
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines.pop()
        out = "\n".join(lines)
        if len(out) > MAX_OUTPUT_CHARS:
            out, truncated = out[:MAX_OUTPUT_CHARS], True
        return out, truncated

    def _on_exit(self) -> None:
        code = self.pty.exit_code() if self.pty else None
        with self.cv:
            self.exit_code = code
            if self.current is not None:
                rec = self.current
                self.current = None
                rec.ended = time.time()
                rec.state = "killed" if rec.aborted_by else "completed"
                rec.exit_code, rec.exit_known = code, code is not None
                rec.output, truncated = self._command_output(rec, self.screen.abs_row())
                rec.truncated = rec.truncated or truncated
                self.emit({"t": "command", "command": rec.public(with_output=False)})
            self.cv.notify_all()
        self._set_state(ST_CLOSED if self._closed else ST_EXITED, exit_code=code)
        self.emit({"t": "exit", "exit_code": code})

    # ----------------------------------------------------- prompt-regex fallback
    def tick(self, now: float) -> None:
        """Called every ~0.4 s by the hub watchdog: hang / question / fallback detection."""
        hint = ""
        hung_event = False
        command_text = ""
        with self.cv:
            state = self.state
            idle = now - self.last_output_at
            prompt_re = PROMPT_RE.get(self.kind, PROMPT_RE["cmd"])
            if state == ST_STARTING:
                # A shell that never emits OSC 133 (a custom prompt) is still usable:
                # recognise its prompt by shape once the startup output goes quiet.
                if idle > 1.2 and not self.markers_seen \
                        and prompt_re.match(self.screen.last_nonempty_line().strip() or "-"):
                    self._prompt_via_regex()
                return
            if state != ST_RUNNING or self.current is None:
                return
            if not self.markers_seen and idle > 0.35:
                last = self.screen.last_nonempty_line().strip()
                if last and prompt_re.match(last) and self.screen.abs_row() > self.current.start_row:
                    self._finish_current(self.screen.abs_row(), end_row=self.screen.abs_row())
                    self._set_state(ST_PROMPT)
                    return
            if idle >= INPUT_IDLE_SECONDS and not self.awaiting_input_hint:
                last = self.screen.last_nonempty_line()
                if _tx.looks_like_input_request(last):
                    self.awaiting_input_hint = last.strip()
                    hint = self.awaiting_input_hint
                    self.cv.notify_all()
            if idle >= self.hang_seconds and not self.suspected_hung:
                self.suspected_hung = True
                self.current.hung = True
                command_text = self.current.text
                hung_event = True
                self.cv.notify_all()
        if hint:
            self.emit({"t": "input_request", "hint": hint})
        if hung_event:
            self.emit({"t": "hung", "idle_seconds": round(idle, 1), "command": command_text})

    def _prompt_via_regex(self) -> None:
        row = self.screen.abs_row()
        self._prompt_row, self._prompt_col = row, len(self.screen.last_nonempty_line().rstrip())
        self._set_state(ST_PROMPT)

    def pty_alive(self) -> bool:
        return bool(self.pty and self.pty.is_alive())

    # ---------------------------------------------- reading the prompt back
    def input_line(self) -> str:
        """What is sitting on the prompt line RIGHT NOW, read back from the screen.

        This is the ground truth for "was the line really typed?": it is what the shell
        echoed, not what Tlamatini wrote to the pipe.  Empty when nothing follows the
        prompt, and also when the screen cannot be read -- a read-back must never break
        typing.
        """
        with self.cv:
            try:
                if self.state in (ST_PROMPT, ST_TYPING) and hasattr(self, "_prompt_row"):
                    return self.screen.text_from(self._prompt_row, self._prompt_col).rstrip()
                return self.screen.cursor_line_text(0).rstrip()
            except Exception:  # noqa: BLE001
                return ""

    def echo_of(self, rec: "CommandRecord") -> str:
        """The command line the shell echoed for ``rec`` (what really ran), or ''."""
        with self.cv:
            try:
                if rec.start_row < self.screen.dropped:
                    return ""
                return self.screen.text_from(rec.start_row, rec.start_col).rstrip()
            except Exception:  # noqa: BLE001
                return ""

    def settle(self, quiet: float = 0.25, timeout: float = 3.0) -> bool:
        """Wait until the terminal has stopped printing, so an echo can be read back."""
        deadline = time.time() + max(0.05, float(timeout))
        with self.cv:
            while True:
                now = time.time()
                if now - self.last_output_at >= quiet:
                    return True
                if now >= deadline or self.state in (ST_EXITED, ST_CLOSED):
                    return False
                self.cv.wait(min(0.05, max(0.01, deadline - now)))

    def verify_line(self, expected: str, timeout: float = 3.0) -> Dict[str, Any]:
        """Read the prompt line back and compare it with ``expected``.

        Polls for up to ``timeout`` seconds, because a shell echoes a little after the
        keys arrive.  ``verified`` is True only when the screen really shows the text.
        """
        deadline = time.time() + max(0.2, float(timeout))
        seen, ok, how = "", False, "empty"
        while True:
            self.settle(0.2, max(0.05, min(1.0, deadline - time.time())))
            seen = self.input_line()
            ok, how = _tx.line_matches(seen, expected)
            if ok or time.time() >= deadline:
                break
            time.sleep(0.1)
        return {"verified": ok, "screen_line": seen[:400], "match": how}

    def clear_input_line(self) -> bool:
        """Empty the prompt line with Esc (PSReadLine's RevertLine; the console's own editor)."""
        if self.state != ST_PROMPT:
            return False
        self._write(chr(27))
        end = time.time() + 2.5
        while time.time() < end:
            self.settle(0.15, 0.6)
            if not self.input_line().strip():
                return True
        return False

    # ----------------------------------------------------------------- queries
    def info(self) -> Dict[str, Any]:
        cur = self.current
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "cwd": self.cwd,
            "pid": self.pid, "state": self.state,
            "since": round(time.time() - self.state_since, 1),
            "alive": self.pty_alive(), "exit_code": self.exit_code,
            "cols": self.cols, "rows": self.rows,
            "commands": len(self.commands), "running_command": cur.text if cur else "",
            "suspected_hung": self.suspected_hung,
            "awaiting_input": self.awaiting_input_hint,
            "handover_hint": self.handover_hint if self.state == ST_AWAITING_USER else "",
            "typing": self.state == ST_TYPING,
            "markers": self.markers_seen, "created": self.created,
            "user_line": self.user_line(), "advisor": self.advisor_enabled,
        }

    def snapshot(self, chars: int = 120_000) -> str:
        with self.cv:
            parts: List[str] = []
            total = 0
            for _, text in reversed(self.raw):
                parts.append(text)
                total += len(text)
                if total >= chars:
                    break
            return "".join(reversed(parts))

    def screen_text(self, last_lines: int = 0) -> str:
        with self.cv:
            return self.screen.text(last_lines=last_lines or None)

    def user_line(self) -> str:
        if self.secret_input:
            return ""
        if self.user_line_screen is not None:
            return self.user_line_screen
        return self.tracker.line

    # ----------------------------------------------------------------- resize
    def resize(self, cols: int, rows: int) -> bool:
        cols, rows = max(20, min(400, int(cols))), max(5, min(120, int(rows)))
        ok = bool(self.pty and self.pty.resize(cols, rows))
        with self.cv:
            self.screen.resize(cols, rows)
            self.cols, self.rows = cols, rows
        return ok

    # ----------------------------------------------------------- raw key write
    def _write(self, data: str) -> int:
        if not self.pty or not self.pty_alive():
            return 0
        return self.pty.write(data.encode("utf-8"))

    # --------------------------------------------------------- command bookkeeping
    def _begin_command(self, source: str, text: str = "") -> CommandRecord:
        with self.cv:
            rec = CommandRecord(next(self._cid), source)
            rec.text = text.strip()
            rec.start_row = getattr(self, "_prompt_row", self.screen.abs_row())
            rec.start_col = getattr(self, "_prompt_col", 0)
            self.current = rec
            self.commands.append(rec)
            while len(self.commands) > MAX_COMMANDS_KEPT:
                self.commands.pop(0)
            self.suspected_hung = False
            self.awaiting_input_hint = ""
        self._set_state(ST_RUNNING, command=rec.text, source=source)
        return rec

    # ------------------------------------------------------------ user input
    def user_input(self, data: str) -> Dict[str, Any]:
        """Keys the USER pressed.  Always honoured, except while Tlamatini is typing."""
        if not data or not self.pty_alive():
            return {"accepted": False}
        with self.cv:
            state = self.state
        if state == ST_TYPING:
            if data in ("\x1b", "\x03"):
                self._abort_typing.set()
                self.emit({"t": "notice", "level": "info",
                           "message": "You took over - Tlamatini stopped typing."})
                if data == "\x03":
                    self._write(data)
                return {"accepted": True, "took_over": True}
            self.emit({"t": "notice", "level": "info",
                       "message": "Tlamatini is typing - press Esc to take over."})
            return {"accepted": False, "reason": "tlamatini_typing"}
        if state == ST_AWAITING_USER and self.handover_remaining and "\r" in data:
            # "Enter" means "I finished my part": let Tlamatini type the rest.
            self.handover_resume.set()
            return {"accepted": True, "handback": True}
        if not self.secret_input:
            with self.cv:
                self.user_keys.append((next(self._key_seq), time.time(), data))
        self.last_user_key_at = time.time()
        events = self.tracker.feed(data) if not self.secret_input else []
        submitted_line = None
        if "submit" in events:
            submitted_line = self._line_before_submit(data)
        if state == ST_PROMPT and (submitted_line is not None or "\r" in data):
            # A reader thread may receive the next prompt before write() returns.
            self._begin_command("user", submitted_line or "")
        if state == ST_AWAITING_USER and not self.handover_remaining and "\r" in data and self.current is None:
            # Nothing is left for Tlamatini to type, so the user's Enter RUNS the line.  Open the
            # command's record BEFORE the Enter reaches the shell, or a fast command could
            # finish first and the terminal would never see its prompt again.
            ran = "<hidden>" if self.secret_input else (self._handover_prefix + (submitted_line or ""))
            self._begin_command("tlamatini", ran)
        self._write(data)
        if submitted_line is not None or ("\r" in data and state in (ST_PROMPT, ST_AWAITING_USER)):
            line = submitted_line or ""
            if state in (ST_PROMPT, ST_AWAITING_USER):
                if not self.secret_input:
                    self.user_submitted.append((next(self._key_seq), time.time(), line))
                if state == ST_AWAITING_USER:
                    self.handover_resume.set()
        with self.cv:
            self.cv.notify_all()
        if self.advisor_enabled and not self.secret_input:
            self._advise()
        return {"accepted": True}

    def _line_before_submit(self, data: str) -> str:
        """The line the user had typed at the moment they pressed Enter."""
        screen_line = self.user_line_screen
        text = screen_line if screen_line is not None else self.tracker.last_line
        self.user_line_screen = None
        return text or ""

    def set_user_line(self, text: str) -> None:
        """The browser reports the real prompt line (xterm's own buffer: ground truth)."""
        if self.secret_input:
            return
        with self.cv:
            self.user_line_screen = (text or "")[:2000]
            self.cv.notify_all()
        if self.advisor_enabled:
            self._advise()

    def _advise(self) -> None:
        line = self.user_line()
        if not line:
            # An emptied line ends the episode: the same mistake typed again is warned again.
            self._last_advice_line = ""
            self._advised.clear()
            return
        if line == self._last_advice_line:
            return
        self._last_advice_line = line
        for adv in _tx.advise_line(line, "cmd" if self.kind == "cmd" else "powershell"):
            key = (adv.code, line)
            if key in self._advised:
                continue
            self._advised.add(key)
            item = {"severity": adv.severity, "code": adv.code, "message": adv.message,
                    "suggestion": adv.suggestion, "line": line, "source": "advisor", "ts": time.time()}
            self.warnings.append(item)
            self.emit({"t": "warn", **item})

    # -------------------------------------------------------------- typing
    def type_text(
        self,
        text: str,
        wpm: int = _tx.DEFAULT_WPM,
        submit: bool = True,
        rng: Optional[random.Random] = None,
        secret: bool = False,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Type ``text`` like a person, one key at a time.  Returns what was typed.

        ``<<USER:hint>>`` placeholders hand the keyboard to the user: Tlamatini
        types the text before it, waits while the user types their part, and
        resumes (or lets the user's Enter run the line) afterwards.
        """
        segments = split_user_segments(text)
        if not self.pty_alive():
            raise TerminaterError("That terminal has already exited.", "terminal_dead")
        if not self._type_lock.acquire(blocking=False):
            raise TerminaterError("Tlamatini is already typing in that terminal.", "busy")
        typed: List[str] = []
        user_part = ""
        result: Dict[str, Any] = {"typed": "", "aborted": False, "enter_pressed": False}
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise TerminaterError("The terminal operation was cancelled.", "cancelled")
            self._abort_typing.clear()
            self._typing_by = "tlamatini"
            self.secret_input = bool(secret)
            self.handover_resume.clear()
            was_prompt = self.state == ST_PROMPT
            self._set_state(ST_TYPING, text=("" if secret else text[:200]))
            for index, (kind, payload) in enumerate(segments):
                if kind == "type":
                    plan = _tx.plan_typing(payload, wpm=wpm, rng=rng, submit=False,
                                           lead_in=(index == 0))
                    for key in plan:
                        if self._abort_typing.wait(key.delay) or (cancel_event is not None and cancel_event.is_set()):
                            result["aborted"] = True
                            break
                        if not self._write(key.key):
                            result["aborted"] = True
                            break
                        typed.append(key.key)
                    if result["aborted"]:
                        break
                else:
                    remaining = [p for k, p in segments[index + 1:] if k == "type"]
                    self._handover_prefix = "".join(typed)
                    user_part = self._hand_over(payload, remaining, secret)
                    if self._handover_timed_out:
                        # the wait expired, the user took the keyboard back, or the shell died
                        result["aborted"] = True
                        result["handover"] = "user_took_over" if self._abort_typing.is_set() else "timeout"
                        break
                    if not remaining:
                        # Enter with nothing after the user's part: the user already ran the line
                        # (user_input opened its record), so Tlamatini must not press Enter again.
                        typed.append(user_part)
                        result["user_submitted"] = True
                        result["handover"] = "submitted_by_user"
                        break
                    result["handover"] = "handed_back"
                    typed.append(user_part)
                    self.handover_resume.clear()
                    self._set_state(ST_TYPING, text="")
            if not result["aborted"] and not result.get("user_submitted") and submit:
                final = _tx.plan_typing("", submit=True, rng=rng, lead_in=False)
                for key in final:
                    if self._abort_typing.wait(key.delay) or (cancel_event is not None and cancel_event.is_set()):
                        result["aborted"] = True
                        break
                    typed_line = "".join(typed)
                    if was_prompt and self.state in (ST_TYPING, ST_PROMPT):
                        self._pre_submit(typed_line, secret)
                    if not self._write(key.key):
                        result["aborted"] = True
                        break
                    result["enter_pressed"] = True
        finally:
            self._typing_by = ""
            self.secret_input = False
            self._type_lock.release()
        result["typed"] = "" if secret else "".join(typed)
        result["user_part"] = "<hidden>" if secret and user_part else user_part
        if self.state not in (ST_EXITED, ST_CLOSED) and (result["aborted"] or self.state == ST_TYPING):
            # Typing is over.  An aborted line, a line left for the user (submit=False) and an
            # answer typed into a program that was already running all end here: the state must
            # go back to what the terminal is REALLY doing, or the user's keys keep being refused
            # ("Tlamatini is typing") and wait() never sees the prompt again.
            self._set_state(ST_PROMPT if self.current is None else ST_RUNNING)
        return result

    _handover_timed_out = False

    def _pre_submit(self, line: str, secret: bool) -> None:
        """Called right before Tlamatini presses Enter: open the command record."""
        if self.current is None:
            self._begin_command("tlamatini", "<hidden>" if secret else line)

    def _hand_over(self, hint: str, remaining: List[str], secret: bool, wait_s: float = 300.0) -> str:
        self.handover_hint = hint or "your part"
        self.handover_remaining = remaining
        self.handover_secret = secret
        self.user_line_screen = None
        self.tracker.reset()
        self.secret_input = bool(secret)
        self._handover_timed_out = False
        self.handover_resume.clear()
        self._set_state(ST_AWAITING_USER, hint=self.handover_hint, secret=bool(secret),
                        resume=bool(remaining))
        self.emit({"t": "handover", "hint": self.handover_hint, "secret": bool(secret),
                   "will_continue": bool(remaining)})
        before = self.tracker.line
        deadline = time.time() + max(5.0, float(getattr(self, "user_wait_seconds", wait_s)))
        while not self.handover_resume.is_set():
            if self._abort_typing.is_set() or not self.pty_alive():
                self._handover_timed_out = True
                break
            if time.time() > deadline:
                self._handover_timed_out = True
                break
            self.handover_resume.wait(0.25)
        part = "" if secret else (self.user_line_screen if self.user_line_screen is not None
                                  else self.tracker.line)
        self.handover_hint = ""
        self.handover_remaining = []
        self.secret_input = False
        _ = before
        return part or ""

    # -------------------------------------------------------------- send keys
    def send_keys(self, spec: str) -> Dict[str, Any]:
        """Named keys, e.g. 'ctrl+c', 'enter', 'up up enter'.  One key at a time."""
        keys, bad = _tx.parse_key_sequence(spec)
        if bad:
            raise TerminaterError(f"Unknown key name(s): {', '.join(bad)}", "bad_key")
        if not keys:
            raise TerminaterError("No keys given.", "bad_key")
        if not self._type_lock.acquire(blocking=False):
            raise TerminaterError("Tlamatini is already typing in that terminal.", "busy")
        try:
            sent = []
            for data in keys:
                time.sleep(random.uniform(0.06, 0.14))
                if "\r" == data and self.state == ST_PROMPT and self.current is None:
                    self._pre_submit(self.user_line() or "", False)
                if not self._write(data):
                    raise TerminaterError("That terminal has already exited.", "terminal_dead")
                sent.append(data)
            return {"sent": len(sent)}
        finally:
            self._type_lock.release()

    # ------------------------------------------------------------------ waiting
    def wait(
        self,
        timeout: float = 120.0,
        until: str = "prompt",
        pattern: str = "",
        hang_seconds: Optional[float] = None,
        idle_seconds: float = 0.0,
    ) -> Dict[str, Any]:
        """Block until the command finishes, hangs, asks something or time runs out."""
        deadline = time.time() + max(0.1, float(timeout))
        rx = re.compile(pattern, re.I | re.M) if pattern else None
        if hang_seconds:
            self.hang_seconds = max(3.0, float(hang_seconds))
        reason = "timeout"
        with self.cv:
            while True:
                now = time.time()
                if self.state in (ST_EXITED, ST_CLOSED):
                    reason = "exited"
                    break
                if until in ("prompt", "completed", "") and self.state == ST_PROMPT and self.current is None:
                    reason = "completed"
                    break
                if self.state == ST_AWAITING_USER:
                    reason = "awaiting_user"
                    break
                if self.suspected_hung and until != "never_hung":
                    reason = "suspected_hung"
                    break
                if self.awaiting_input_hint and until in ("prompt", "completed", "input", ""):
                    reason = "awaiting_input"
                    break
                if rx is not None and rx.search(self.screen.text(last_lines=80)):
                    reason = "pattern"
                    break
                if idle_seconds and now - self.last_output_at >= idle_seconds:
                    reason = "idle"
                    break
                if now >= deadline:
                    reason = "timeout"
                    break
                self.cv.wait(min(0.25, max(0.02, deadline - now)))
        return {"reason": reason, "state": self.state}

    def last_command(self) -> Optional[CommandRecord]:
        with self.cv:
            return self.commands[-1] if self.commands else None

    def read(self, which: str = "last", limit: int = 20000, offset: int = 0) -> Dict[str, Any]:
        """Output of the last command, a command number, the live screen or all text."""
        which = (which or "last").strip().lower()
        if which in ("screen", "visible"):
            text = self.screen.visible_text()
            return {"scope": "screen", "output": text, "output_chars": len(text), "truncated": False}
        if which in ("all", "transcript"):
            text = self.screen.text()
            part = text[offset:offset + limit] if limit else text[offset:]
            return {"scope": "all", "output": part, "output_chars": len(text),
                    "truncated": bool(self.screen.dropped or (limit and len(text) - offset > limit)),
                    "more": bool(limit and len(text) - offset > limit)}
        rec = None
        with self.cv:
            if which == "last":
                rec = self.commands[-1] if self.commands else None
            elif which.isdigit():
                rec = next((c for c in self.commands if c.id == int(which)), None)
            if rec is not None and rec is self.current:
                # still running: show what has been produced so far
                live, truncated = self._command_output(rec, self.screen.abs_row())
                more = bool(limit and len(live) - offset > limit)
                data = rec.public(with_output=False)
                data.update({"output": live[offset:offset + limit] if limit else live[offset:],
                             "output_chars": len(live), "live": True, "more": more,
                             "truncated": rec.truncated or truncated or more})
                return {"scope": "command", **data}
        if rec is None:
            return {"scope": "command", "output": "", "output_chars": 0, "command": "", "state": "none"}
        return {"scope": "command", **rec.public(limit=limit, offset=offset)}

    # --------------------------------------------------------------- aborting
    def abort(self) -> Dict[str, Any]:
        """Stop the running command without losing the terminal."""
        self._abort_typing.set()
        if self.current is None and self.state != ST_RUNNING:
            return {"aborted_by": "nothing_running", "state": self.state}
        rec = self.current
        steps = []
        self._write("\x03")
        steps.append("ctrl_c")
        if self._wait_prompt(3.0):
            return self._aborted(rec, steps)
        text = self.screen.last_nonempty_line().lower()
        if "terminate batch job" in text:
            self._write("y\r")
            steps.append("batch_yes")
            if self._wait_prompt(3.0):
                return self._aborted(rec, steps)
        self._write("\x03")
        steps.append("ctrl_c_again")
        if self._wait_prompt(3.0):
            return self._aborted(rec, steps)
        killed = self.pty.kill_children() if self.pty else 0
        steps.append(f"kill_children:{killed}")
        if self._wait_prompt(4.0):
            return self._aborted(rec, steps)
        return self._aborted(rec, steps, still_running=True)

    def _aborted(self, rec: Optional[CommandRecord], steps: List[str], still_running: bool = False) -> Dict[str, Any]:
        if rec is not None:
            rec.aborted_by = "+".join(steps)
            if rec.state in ("running", "hung", "completed"):
                rec.state = "aborted"
        return {"aborted_by": "+".join(steps), "state": self.state, "still_running": still_running}

    def _wait_prompt(self, seconds: float) -> bool:
        deadline = time.time() + seconds
        with self.cv:
            while time.time() < deadline:
                if self.state in (ST_EXITED, ST_CLOSED):
                    return True
                if self.state == ST_PROMPT and self.current is None:
                    return True
                self.cv.wait(0.1)
        return False

    # -------------------------------------------------------------- lifecycle
    def close(self, force: bool = False) -> Dict[str, Any]:
        """Close the terminal.  Graceful: Ctrl+C, close the console, wait; then kill."""
        self._abort_typing.set()
        self._closed = True
        pty = self.pty
        method = "force" if force else "graceful"
        if pty is not None:
            if not force and self.state == ST_RUNNING:
                self._write("\x03")
                time.sleep(0.2)
            pty.close(force=force)
            if not pty.is_alive():
                pass
        with self.cv:
            self.cv.notify_all()
        if self._reader is not None:
            self._reader.join(timeout=3.0)
        self._set_state(ST_CLOSED)
        self.emit({"t": "closed"})
        return {"closed": True, "method": method, "tree_kill_atomic": bool(pty and pty.tree_kill_is_atomic)}


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _utf8_decoder():
    import codecs

    return codecs.getincrementaldecoder("utf-8")(errors="replace")


_USER_RE = re.compile(r"<<USER(?::([^>]{0,80}))?>>")


def split_user_segments(text: str) -> List[Tuple[str, str]]:
    """'ping <<USER:host>> -n 2' -> [('type','ping '), ('user','host'), ('type',' -n 2')]."""
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in _USER_RE.finditer(text or ""):
        if m.start() > pos:
            out.append(("type", text[pos:m.start()]))
        out.append(("user", (m.group(1) or "your part").strip()))
        pos = m.end()
    if pos < len(text or ""):
        out.append(("type", text[pos:]))
    return out or [("type", text or "")]


# --------------------------------------------------------------------------- #
# The hub                                                                      #
# --------------------------------------------------------------------------- #

class UserSpace:
    """Everything one user owns: terminals, UI layout, event listeners."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.sessions: Dict[str, TerminalSession] = {}
        self.order: List[str] = []
        self.active: str = ""
        self.ui: Dict[str, Any] = {"layout": "tabs", "area": "dock", "visible": False, "focus": ""}
        self.listeners: List[Callable[[Dict[str, Any]], None]] = []
        self.counter = itertools.count(1)
        self.opening = 0
        self.lock = threading.RLock()
        self.last_used = time.time()


class TerminalHub:
    """Owns the terminals of every user and exposes the whole action API."""

    def __init__(self, max_terminals: int = 12, hang_seconds: float = HANG_SECONDS_DEFAULT) -> None:
        self.max_terminals = max(1, int(max_terminals))
        self.hang_seconds = hang_seconds
        self._spaces: Dict[str, UserSpace] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._watch, name="terminater-watchdog", daemon=True)
        self._watchdog.start()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()

    # ---------------------------------------------------------------- spaces
    def space(self, user: Optional[str] = None, create: bool = True) -> UserSpace:
        with self._lock:
            key = self.resolve_user(user)
            sp = self._spaces.get(key)
            if sp is None and create:
                sp = self._spaces[key] = UserSpace(key)
            if sp is None:
                raise TerminaterError("No terminals exist yet.", "no_space")
            sp.last_used = time.time()
            return sp

    def resolve_user(self, user: Optional[str]) -> str:
        user = (str(user).strip() if user not in (None, "") else "")
        if user and user not in ("auto", "active"):
            return user
        with self._lock:
            connected = [k for k, s in self._spaces.items() if s.listeners]
            if len(connected) == 1:
                return connected[0]
            if connected:
                return max(connected, key=lambda k: self._spaces[k].last_used)
            if self._spaces:
                return max(self._spaces, key=lambda k: self._spaces[k].last_used)
        return "local"

    def add_listener(self, user: str, cb: Callable[[Dict[str, Any]], None]) -> None:
        sp = self.space(user)
        with sp.lock:
            sp.listeners.append(cb)

    def remove_listener(self, user: str, cb: Callable[[Dict[str, Any]], None]) -> None:
        try:
            sp = self.space(user, create=False)
        except TerminaterError:
            return
        with sp.lock:
            if cb in sp.listeners:
                sp.listeners.remove(cb)

    def _emitter(self, sp: UserSpace) -> Callable[[Dict[str, Any]], None]:
        def emit(event: Dict[str, Any]) -> None:
            for cb in list(sp.listeners):
                try:
                    cb(event)
                except Exception:  # noqa: BLE001
                    pass
        return emit

    def broadcast(self, user: str, event: Dict[str, Any]) -> None:
        self._emitter(self.space(user))(event)

    # -------------------------------------------------------------- sessions
    def _get(self, sp: UserSpace, ref: Any, required: bool = True) -> Optional[TerminalSession]:
        with sp.lock:
            ref = (str(ref).strip() if ref not in (None, "") else "")
            problem = _tx.terminal_ref_problem(ref)
            if problem:
                raise TerminaterError(
                    f"{ref[:70]!r} cannot be a terminal id or title: {problem}. Pass the exact "
                    "terminal_id returned by action='open' or action='list' (like 't2'), "
                    "as its own parameter.", "bad_terminal_ref")
            if not ref or ref in ("active", "last", "current"):
                ref = sp.active or (sp.order[-1] if sp.order else "")
            if ref in sp.sessions:
                return sp.sessions[ref]
            low = ref.lower()
            matches = [s for s in sp.sessions.values() if s.title.lower() == low]
            if not matches and low:
                matches = [s for s in sp.sessions.values() if low in s.title.lower()]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise TerminaterError(
                    f"Terminal name {ref!r} matches several terminals. Use an exact terminal ID: "
                    + ", ".join(s.id for s in matches), "ambiguous_terminal")
        if required:
            raise TerminaterError(
                f"No terminal named {ref!r}. Open one first, or use action='list'.", "no_terminal")
        return None

    def open(self, user: Optional[str] = None, kind: str = "powershell", title: str = "",
             cwd: str = "", cols: int = DEFAULT_COLS, rows: int = DEFAULT_ROWS,
             load_profile: bool = True, hang_seconds: Optional[float] = None,
             show: bool = True, advisor: bool = True) -> Dict[str, Any]:
        sp = self.space(user)
        kind = normalize_kind(kind)
        if not _cp.conpty_available():
            raise TerminaterError(
                "This machine cannot host terminals: ConPTY needs Windows 10 1809 or newer.",
                "conpty_unavailable")
        with sp.lock:
            alive = [s for s in sp.sessions.values() if s.state not in (ST_EXITED, ST_CLOSED)]
            if len(alive) + sp.opening >= self.max_terminals:
                raise TerminaterError(
                    f"The limit of {self.max_terminals} open terminals is reached. Close one first.",
                    "too_many")
            n = next(sp.counter)
            sid = f"t{n}"
            sp.opening += 1
        start_dir = cwd if cwd and os.path.isdir(cwd) else os.path.expanduser("~")
        label = _tx.sanitize_title(title, default=f"{'CMD' if kind == 'cmd' else 'PowerShell'} {n}")
        try:
            session = TerminalSession(
                sid, kind, label, start_dir, self._emitter(sp), cols=cols, rows=rows,
                load_profile=load_profile, hang_seconds=hang_seconds or self.hang_seconds,
                advisor=advisor)
        except BaseException:
            with sp.lock:
                sp.opening -= 1
            raise
        with sp.lock:
            sp.opening -= 1
            sp.sessions[sid] = session
            sp.order.append(sid)
            sp.active = sid
            if show:
                sp.ui["visible"] = True
            sp.ui["focus"] = sid
        self._emitter(sp)({"t": "opened", "terminal": session.info(), "ui": dict(sp.ui)})
        # wait (bounded) for the first prompt so the caller can type straight away
        deadline = time.time() + 25.0
        with session.cv:
            while session.state == ST_STARTING and time.time() < deadline:
                session.cv.wait(0.2)
                if session.state == ST_STARTING:
                    session.tick(time.time())
        return {"terminal": session.info(), "ui": dict(sp.ui)}

    def list(self, user: Optional[str] = None) -> Dict[str, Any]:
        sp = self.space(user)
        with sp.lock:
            items = [sp.sessions[i].info() for i in sp.order if i in sp.sessions]
            return {"terminals": items, "active": sp.active, "ui": dict(sp.ui),
                    "available_kinds": available_kinds(), "max_terminals": self.max_terminals}

    def close(self, user: Optional[str], ref: Any, force: bool = False, remove: bool = True) -> Dict[str, Any]:
        sp = self.space(user)
        session = self._get(sp, ref)
        info = session.close(force=force)
        if remove:
            with sp.lock:
                sp.sessions.pop(session.id, None)
                if session.id in sp.order:
                    sp.order.remove(session.id)
                if sp.active == session.id:
                    sp.active = sp.order[-1] if sp.order else ""
                    sp.ui["focus"] = sp.active
        self._emitter(sp)({"t": "removed", "id": session.id, "active": sp.active})
        return {"terminal_id": session.id, **info}

    def kill_all(self, user: Optional[str] = None, force: bool = True) -> Dict[str, Any]:
        sp = self.space(user)
        ids = list(sp.order)
        for sid in ids:
            try:
                self.close(user, sid, force=force)
            except TerminaterError:
                pass
        return {"closed": ids}

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            spaces = list(self._spaces.values())
        for sp in spaces:
            for session in list(sp.sessions.values()):
                try:
                    session.close(force=True)
                except Exception:  # noqa: BLE001
                    pass

    def live_pids(self) -> List[int]:
        pids: List[int] = []
        with self._lock:
            spaces = list(self._spaces.values())
        for sp in spaces:
            for s in list(sp.sessions.values()):
                if s.pty_alive() and s.pid:
                    pids.append(s.pid)
        return pids

    def _watch(self) -> None:
        while not self._stop.wait(0.4):
            with self._lock:
                spaces = list(self._spaces.values())
            now = time.time()
            for sp in spaces:
                for s in list(sp.sessions.values()):
                    try:
                        s.tick(now)
                    except Exception:  # noqa: BLE001 -- the watchdog must survive anything
                        pass

    # ------------------------------------------------------------ the actions
    def call(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run one action synchronously.  Never raises: errors become ``ok: False``."""
        params = dict(params or {})
        action = re.sub(r"[\s\-]+", "_", str(action or "").strip().lower())
        action = _ACTION_ALIASES.get(action, action)
        handler = getattr(self, f"_a_{action}", None)
        if handler is None:
            return {"ok": False, "status": "refused", "code": "unknown_action",
                    "message": f"Unknown action {action!r}. Valid: {', '.join(ACTIONS)}."}
        try:
            # Resolve once: opening a shell can take seconds, during which another
            # browser can become the most recently active user.
            params["user"] = self.resolve_user(params.get("user"))
            result = handler(params)
            result.setdefault("ok", True)
            result.setdefault("action", action)
            return result
        except TerminaterError as exc:
            return {"ok": False, "action": action, "status": "refused", "code": exc.code,
                    "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "action": action, "status": "error", "code": "internal",
                    "message": f"{type(exc).__name__}: {exc}"}

    # -- helpers
    def _sess(self, p: Dict[str, Any]) -> Tuple[UserSpace, TerminalSession]:
        sp = self.space(p.get("user"))
        session = self._get(sp, p.get("terminal"))
        # In-process flow cancellation must remember this exact session, not a
        # tab that the user may focus later. JSON callers cannot supply callbacks.
        selected = p.get("_on_terminal")
        if callable(selected):
            selected(session.id)
        return sp, session

    @staticmethod
    def _num(p: Dict[str, Any], key: str, default: float, lo: float, hi: float) -> float:
        try:
            value = float(p.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(lo, min(hi, value))

    @staticmethod
    def _text(p: Dict[str, Any]) -> str:
        if p.get("text_b64"):
            try:
                return base64.b64decode("".join(str(p["text_b64"]).split()), validate=True).decode("utf-8")
            except Exception as exc:  # noqa: BLE001
                raise TerminaterError(f"text_b64 is not valid base64/UTF-8: {exc}", "bad_text")
        return str(p.get("text") or "")

    @staticmethod
    def _flag(p: Dict[str, Any], key: str, default: bool, safe: Optional[bool] = None) -> Tuple[bool, str]:
        """A yes/no parameter read STRICTLY: ``(value, note)``.

        A clean yes/no is taken as given; blank means ``default``; anything else falls to
        the SAFE side (``safe``) and the note names it, so the reply can say what really
        happened.  (A sentence glued to ``submit`` used to read as TRUE and pressed Enter.)
        """
        value, note = _tx.parse_flag(p.get(key), default, safe)
        return value, (f"{key}: {note}" if note else "")

    def _open_kwargs(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """The keyword arguments ``open()`` takes, read from an action's parameters."""
        return {
            "kind": p.get("kind") or "powershell",
            "title": str(p.get("title") or ""),
            "cwd": str(p.get("cwd") or ""),
            "load_profile": self._flag(p, "load_profile", True)[0],
            "hang_seconds": self._num(p, "hang_seconds", self.hang_seconds, 3, 86400),
            "show": self._flag(p, "show", True)[0],
            "advisor": self._flag(p, "advisor", True)[0],
        }

    def _result_for(self, session: TerminalSession, rec: Optional[CommandRecord], extra: Dict[str, Any],
                    read_chars: int) -> Dict[str, Any]:
        data: Dict[str, Any] = {"terminal_id": session.id, "kind": session.kind, "title": session.title,
                                "terminal_state": session.state}
        if rec is not None:
            data.update(rec.public(limit=read_chars))
        data.update(extra)
        return data

    # -- actions
    def _a_status(self, p: Dict[str, Any]) -> Dict[str, Any]:
        out = self.list(p.get("user"))
        out["status"] = "listed"
        out["conpty"] = _cp.conpty_available()
        return out

    def _a_list(self, p: Dict[str, Any]) -> Dict[str, Any]:
        out = self.list(p.get("user"))
        out["status"] = "listed"
        return out

    def _a_open(self, p: Dict[str, Any]) -> Dict[str, Any]:
        out = self.open(p.get("user"), **self._open_kwargs(p))
        out["status"] = "opened"
        out["terminal_id"] = out["terminal"]["id"]
        return out

    def _a_focus(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        with sp.lock:
            sp.active = session.id
            sp.ui["focus"] = session.id
            sp.ui["visible"] = True
        self._emitter(sp)({"t": "ui", "ui": dict(sp.ui), "active": session.id})
        return {"status": "focused", "terminal_id": session.id, "ui": dict(sp.ui)}

    def _a_rename(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        session.title = _tx.sanitize_title(p.get("title") or p.get("text"), default=session.id)
        session.emit({"t": "title_set", "title": session.title})
        return {"status": "completed", "terminal_id": session.id, "title": session.title}

    def _a_layout(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp = self.space(p.get("user"))
        layout = str(p.get("layout") or "").strip().lower()
        area = str(p.get("area") or "").strip().lower()
        if layout:
            layout = {"horizontal": "tile-h", "vertical": "tile-v", "tiled": "tile", "tabbed": "tabs",
                      "tab": "tabs", "side-by-side": "tile-h", "stacked": "tile-v"}.get(layout, layout)
            if layout not in LAYOUTS:
                raise TerminaterError(f"layout must be one of {', '.join(LAYOUTS)}.", "bad_layout")
            sp.ui["layout"] = layout
        if area:
            area = {"canvas": "full", "whole": "full", "fill": "full", "lower": "dock", "bottom": "dock"}.get(area, area)
            if area not in AREAS:
                raise TerminaterError(f"area must be one of {', '.join(AREAS)}.", "bad_area")
            sp.ui["area"] = area
        if "show" in p and p["show"] not in ("", None):
            sp.ui["visible"] = bool(p["show"]) if not isinstance(p["show"], str) \
                else p["show"].strip().lower() not in ("false", "0", "no", "hide", "off")
        elif layout or area:
            sp.ui["visible"] = True
        self._emitter(sp)({"t": "ui", "ui": dict(sp.ui), "active": sp.active})
        return {"status": "completed", "ui": dict(sp.ui)}

    def _a_type(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        text = self._text(p)
        if not text.strip():
            raise TerminaterError("Nothing to type: pass text (or text_b64).", "empty_text")
        # Every yes/no is read STRICTLY.  One that is not a clean yes/no falls to the side that
        # does LESS (do not press Enter, hide a secret) and is named in `notes`.
        notes: List[str] = []
        flags: Dict[str, bool] = {}
        for key, default, safe in (("submit", True, False), ("wait", True, None),
                                   ("secret", False, True), ("check_line", True, None),
                                   ("clear_line", False, False)):
            flags[key], note = self._flag(p, key, default, safe)
            notes.append(note)
        submit, wait, secret = flags["submit"], flags["wait"], flags["secret"]
        check_line, clear_line = flags["check_line"], flags["clear_line"]
        wpm = _tx.clamp_wpm(p.get("typing_wpm", _tx.DEFAULT_WPM))
        timeout = self._num(p, "wait_seconds", 120, 1, 86400)
        read_chars = int(self._num(p, "read_chars", 20000, 0, 2_000_000))
        session.hang_seconds = self._num(p, "hang_seconds", session.hang_seconds, 3, 86400)
        session.user_wait_seconds = self._num(p, "user_wait_seconds", 300, 5, 86400)
        with sp.lock:
            sp.active = session.id
            sp.ui["visible"] = True
            sp.ui["focus"] = session.id
        self._emitter(sp)({"t": "ui", "ui": dict(sp.ui), "active": session.id})
        if session.state == ST_RUNNING and session.current is not None and not session.awaiting_input_hint \
                and not session.suspected_hung:
            raise TerminaterError(
                "A command is still running in that terminal. Wait for it, answer its question, "
                "use action='abort', or open another terminal.", "busy")
        # Typing into a program that asked a question is allowed (answering it).
        starts_command = session.state == ST_PROMPT

        # What does the caller expect to SEE on the prompt?  The last non-empty line of the
        # text (earlier lines of a multi-line text are each submitted by their own Enter).
        body_lines = [ln for ln in text.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10)).split(chr(10))
                      if ln.strip()]
        has_marker = "<<USER" in text
        single_line = len(body_lines) == 1 and not has_marker
        expected = body_lines[-1] if (body_lines and not has_marker) else ""

        # What is ALREADY on the prompt line?  Typing now would glue the new text onto it
        # (the user may be typing there, or an earlier line was left unsubmitted).
        to_type, already_present = text, False
        if starts_command and not secret and check_line:
            existing = session.input_line()
            if existing.strip():
                if single_line and _tx.norm_line(existing) == _tx.norm_line(expected):
                    # The very same line is already waiting: typing it again would DUPLICATE it.
                    to_type, already_present = "", True
                    notes.append("the same line was already on the prompt, so it was not typed a second time")
                elif clear_line:
                    if not session.clear_input_line():
                        raise TerminaterError(
                            f"The prompt line is not empty and could not be cleared: it shows {existing[:200]!r}. "
                            "Look with action='read' (which='screen') or ask the user to clear it.",
                            "prompt_not_empty")
                    notes.append(f"the prompt line was cleared first (it held {existing[:120]!r})")
                else:
                    raise TerminaterError(
                        f"The prompt line is not empty: it already shows {existing[:200]!r}. Typing now would glue "
                        "the new text onto it. The user may be typing there (action='watch_user'), or an earlier "
                        "line was left unsubmitted: ask the user, or pass clear_line=true to replace it.",
                        "prompt_not_empty")

        cancellation = p.get("_cancel_event")
        options = {"cancel_event": cancellation} if isinstance(cancellation, threading.Event) else {}
        if already_present and not submit:
            typed: Dict[str, Any] = {"typed": "", "user_part": "", "aborted": False, "enter_pressed": False}
        else:
            typed = session.type_text(to_type, wpm=wpm, submit=submit, secret=secret, **options)
        extra: Dict[str, Any] = {"typed": text if (already_present and not secret) else typed.get("typed", ""),
                                 "user_part": typed.get("user_part", ""),
                                 "aborted_typing": typed.get("aborted", False),
                                 "enter_pressed": bool(typed.get("enter_pressed")),
                                 "already_present": already_present}
        if typed.get("handover"):
            extra["handover"] = typed["handover"]
        if typed.get("aborted"):
            reason = typed.get("handover") or "user_took_over"
            extra["notes"] = "; ".join(n for n in notes if n)
            return self._result_for(session, None, {
                **extra, "status": "operator_required" if reason == "timeout" else "aborted",
                "success": False, "reason": reason,
                "message": ("The user did not finish their part in time." if reason == "timeout"
                            else "The user took over the keyboard; typing stopped.")}, read_chars)

        # READ IT BACK.  "I sent the keys" is not "the line is on the prompt": ask the screen.
        verify: Dict[str, Any] = {}
        if not submit and not secret and check_line and expected and not typed.get("handover"):
            verify = session.verify_line(expected)
        if verify:
            extra["verified"] = bool(verify["verified"])
            extra["screen_line"] = verify["screen_line"]
        extra["notes"] = "; ".join(n for n in notes if n)
        if not submit and not typed.get("user_submitted"):
            if verify and not verify["verified"]:
                return self._result_for(session, None, {
                    **extra, "status": "typing_unverified", "success": False,
                    "message": ("The keys were sent, but the screen does NOT show the line: the prompt shows "
                                f"{verify['screen_line']!r}. Do not tell the user the line is on their prompt. "
                                "Look with action='read' (which='screen'), then retry or tell the user plainly "
                                "what happened.")}, read_chars)
            return self._result_for(session, None, {
                **extra, "status": "typed", "success": True,
                "message": "Typed without pressing Enter; the line is waiting for the user."
                           + (" The screen shows it." if verify else "")}, read_chars)
        rec = session.current or session.last_command()
        if not wait:
            return self._result_for(session, rec, {**extra, "status": "started", "success": True,
                                                   "message": "Command started; not waiting."}, read_chars)
        w = session.wait(timeout=timeout, until="prompt")
        rec = rec if rec is not None else session.last_command()
        out = self._finish_wait(session, rec, w, extra, read_chars, starts_command)
        if starts_command and submit and single_line and not secret and check_line and expected and rec is not None:
            # The echo of the submitted command is what the shell REALLY received.  (Only for a line
            # that STARTED a command: an answer typed into a running program is not echoed there.)
            echo = session.echo_of(rec)
            if echo:
                matched, _how = _tx.line_matches(echo, expected)
                out["verified"], out["screen_line"] = matched, echo[:400]
                if not matched:
                    mismatch = f"the shell echoed {echo[:200]!r} instead of the typed {expected[:200]!r}"
                    out["notes"] = "; ".join(n for n in (out.get("notes"), mismatch) if n)
                    if out.get("status") in ("completed", "command_failed"):
                        out["status"], out["success"] = "typing_unverified", False
                        out["message"] = (f"The command ran, but {mismatch}. What ran may not be what was meant: "
                                          "read the output and say so plainly.")
        return out

    def _finish_wait(self, session: TerminalSession, rec: Optional[CommandRecord], w: Dict[str, Any],
                     extra: Dict[str, Any], read_chars: int, starts_command: bool = True) -> Dict[str, Any]:
        reason = w["reason"]
        extra = dict(extra)
        extra["wait_reason"] = reason
        if reason == "completed":
            code = rec.exit_code if rec is not None and rec.exit_known else None
            failed = code not in (None, 0)
            extra.update({"status": "command_failed" if failed else "completed",
                          "success": not failed})
        elif reason == "suspected_hung":
            extra.update({"status": "hung", "success": False,
                          "message": "No output for a long time: the command looks hung. "
                                     "Use action='abort' (or 'kill') or keep waiting with action='wait'."})
        elif reason == "awaiting_input":
            extra.update({"status": "operator_required", "success": False,
                          "awaiting_input": session.awaiting_input_hint,
                          "message": "The program is asking something: "
                                     f"{session.awaiting_input_hint!r}. Answer with action='type' "
                                     "(text='y') or let the user answer."})
        elif reason == "awaiting_user":
            extra.update({"status": "operator_required", "success": False,
                          "message": "Waiting for the user to complete their part of the command."})
        elif reason == "exited":
            code = rec.exit_code if rec is not None and rec.exit_known else session.exit_code
            aborted = bool(rec is not None and rec.aborted_by)
            failed = code not in (None, 0)
            extra.update({"status": "aborted" if aborted else "command_failed" if failed else "completed",
                          "success": not (failed or aborted),
                          "message": "The terminal's shell exited."})
        else:
            extra.update({"status": "timeout", "success": False,
                          "message": "Still running after the wait window. Use action='wait' to keep "
                                     "waiting, or action='read' to see the output so far."})
            if rec is not None and rec is session.current:
                live = session.read("last", limit=read_chars)
                return {**self._result_for(session, None, extra, read_chars),
                        "output": live.get("output", ""), "output_chars": live.get("output_chars", 0),
                        "command": live.get("command", ""), "state": "running",
                        "truncated": live.get("truncated", False), "more": live.get("more", False)}
        return self._result_for(session, rec, extra, read_chars)

    def _a_run(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Open-or-reuse a terminal, type a command like a person, wait, read."""
        sp = self.space(p.get("user"))
        ref = str(p.get("terminal") or "").strip()
        session = self._get(sp, ref, required=False) if ref else None
        if session is None or session.state in (ST_EXITED, ST_CLOSED):
            if ref and session is None:
                # Naming a terminal that is NOT there is a MISTAKE unless the caller said a missing
                # one may be created -- otherwise a typo, or a fragment of a sentence, quietly raises
                # a NEW terminal and the command runs where nobody is looking.  An id ('t3') is
                # never a name to create.
                create, _note = self._flag(p, "create_if_missing", True, safe=False)
                if _tx.looks_like_terminal_id(ref):
                    raise TerminaterError(
                        f"There is no terminal {ref!r} (it may have been closed). Use action='list' to see the "
                        "open terminals, or action='open' to raise a new one.", "no_terminal")
                if not create:
                    raise TerminaterError(
                        f"There is no terminal named {ref!r}, and create_if_missing is off. Use action='list' "
                        "to see the open terminals, action='open' to raise a new one, or pass "
                        "create_if_missing=true.", "no_terminal")
            kwargs = self._open_kwargs(p)
            kwargs["title"] = kwargs["title"] or (session.title if session is not None else ref)
            opened = self.open(p.get("user"), **kwargs)
            p = {**p, "terminal": opened["terminal"]["id"]}
        close_after = self._flag(p, "close_after", False, safe=False)[0]
        out = self._a_type(p)
        if close_after and out.get("status") in ("completed", "command_failed"):
            try:
                self.close(p.get("user"), p.get("terminal"), force=False)
                out["closed_after"] = True
            except TerminaterError:
                pass
        return out

    def _a_send_key(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        spec = str(p.get("keys") or p.get("key") or p.get("text") or "")
        res = session.send_keys(spec)
        pressed_enter = any(key == chr(13) for key in _tx.parse_key_sequence(spec)[0])
        return {"status": "typed", "success": True, "terminal_id": session.id,
                "enter_pressed": pressed_enter, **res}

    def _a_wait(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        w = session.wait(timeout=self._num(p, "wait_seconds", 120, 0.1, 86400),
                         until=str(p.get("until") or "prompt").lower(),
                         pattern=str(p.get("pattern") or ""),
                         hang_seconds=self._num(p, "hang_seconds", 0, 0, 86400) or None,
                         idle_seconds=self._num(p, "idle_seconds", 0, 0, 3600))
        rec = session.current or session.last_command()
        if w["reason"] in ("pattern", "idle"):
            live = session.read("last", limit=int(self._num(p, "read_chars", 20000, 0, 2_000_000)))
            return {"status": "completed", "success": True, "terminal_id": session.id,
                    "wait_reason": w["reason"], **{k: v for k, v in live.items() if k != "scope"}}
        return self._finish_wait(session, rec, w, {}, int(self._num(p, "read_chars", 20000, 0, 2_000_000)))

    def _a_read(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        which = str(p.get("which") or p.get("scope") or p.get("until") or "last")
        res = session.read(which, limit=int(self._num(p, "read_chars", 20000, 0, 2_000_000)),
                           offset=int(self._num(p, "offset", 0, 0, 10**9)))
        res.update({"status": "read", "success": True, "terminal_id": session.id,
                    "terminal_state": session.state})
        return res

    def _a_commands(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        with session.cv:
            items = [c.public(with_output=False) for c in session.commands[-50:]]
        return {"status": "listed", "success": True, "terminal_id": session.id, "commands": items}

    def _a_abort(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        res = session.abort()
        ok = not res.get("still_running")
        return {"status": "aborted" if ok else "hung", "success": ok, "terminal_id": session.id, **res}

    def _a_kill(self, p: Dict[str, Any]) -> Dict[str, Any]:
        res = self.close(p.get("user"), p.get("terminal"), force=False)
        return {"status": "killed", "success": True, **res}

    def _a_force_kill(self, p: Dict[str, Any]) -> Dict[str, Any]:
        res = self.close(p.get("user"), p.get("terminal"), force=True)
        return {"status": "killed", "success": True, **res}

    _a_close = _a_kill

    def _a_kill_all(self, p: Dict[str, Any]) -> Dict[str, Any]:
        res = self.kill_all(p.get("user"), force=True)
        return {"status": "killed", "success": True, **res}

    def _a_clear(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        session.emit({"t": "clear"})
        return {"status": "completed", "success": True, "terminal_id": session.id}

    def _a_resize(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        ok = session.resize(int(self._num(p, "cols", DEFAULT_COLS, 20, 400)),
                            int(self._num(p, "rows", DEFAULT_ROWS, 5, 120)))
        return {"status": "completed", "success": ok, "terminal_id": session.id,
                "cols": session.cols, "rows": session.rows}

    def _a_watch_user(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Real-time view of what the USER is typing.  Blocks until something happens."""
        sp, session = self._sess(p)
        cursor = int(self._num(p, "cursor", 0, 0, 10**12))
        timeout = self._num(p, "wait_seconds", 30, 0.1, 3600)
        until = str(p.get("until") or "idle").lower()      # idle | submit | key | timeout
        idle = self._num(p, "idle_seconds", 2.0, 0.2, 600)
        deadline = time.time() + timeout
        reason = "timeout"
        with session.cv:
            while True:
                new = [k for k in session.user_keys if k[0] > cursor]
                subs = [s for s in session.user_submitted if s[0] > cursor]
                now = time.time()
                if subs and until in ("submit", "idle", "key"):
                    reason = "submitted"
                    break
                if new and until == "key":
                    reason = "key"
                    break
                if new and until == "idle" and now - session.last_user_key_at >= idle:
                    reason = "idle"
                    break
                if session.state in (ST_EXITED, ST_CLOSED):
                    reason = "exited"
                    break
                if now >= deadline:
                    reason = "timeout" if not new else "idle"
                    break
                session.cv.wait(min(0.25, max(0.02, deadline - now)))
            new = [k for k in session.user_keys if k[0] > cursor]
            subs = [s for s in session.user_submitted if s[0] > cursor]
        keys = "".join(k[2] for k in new)
        masked = session.secret_input
        last_cursor = max([cursor] + [k[0] for k in new] + [s[0] for s in subs])
        advice = [a._asdict() for a in _tx.advise_line(session.user_line(),
                                                       "cmd" if session.kind == "cmd" else "powershell")]
        return {"status": "observed", "success": True, "terminal_id": session.id,
                "watch_reason": reason, "cursor": last_cursor,
                "line": "" if masked else session.user_line(),
                "uncertain": session.tracker.uncertain,
                "keys": "" if masked else _printable(keys),
                "key_count": len(new),
                "submitted": [{"ts": s[1], "line": s[2]} for s in subs],
                "advice": advice, "terminal_state": session.state,
                "since_last_key": round(time.time() - session.last_user_key_at, 2)
                if session.last_user_key_at else None}

    def _a_warn_user(self, p: Dict[str, Any]) -> Dict[str, Any]:
        sp, session = self._sess(p)
        message = str(p.get("message") or p.get("text") or "").strip()
        if not message:
            raise TerminaterError("Nothing to warn about: pass message.", "empty_text")
        severity = str(p.get("severity") or "warning").lower()
        if severity not in ("info", "hint", "warning", "danger"):
            severity = "warning"
        item = {"severity": severity, "code": "tlamatini", "message": message[:600],
                "suggestion": str(p.get("suggestion") or "")[:300], "line": session.user_line(),
                "source": "tlamatini", "ts": time.time()}
        session.warnings.append(item)
        session.emit({"t": "warn", **item})
        with sp.lock:
            sp.ui["visible"] = True
            # A warning nobody can see is no warning: bring the warned terminal to the front.
            sp.active = session.id
            sp.ui["focus"] = session.id
        self._emitter(sp)({"t": "ui", "ui": dict(sp.ui), "active": session.id})
        return {"status": "warned", "success": True, "terminal_id": session.id}

    def _a_handover(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """Type a partial command and give the keyboard to the user (no Enter)."""
        hint = str(p.get("hint") or p.get("message") or "your part")
        text = self._text(p)
        if "<<USER" not in text:
            text = f"{text}<<USER:{hint}>>"
        # A hand-over is very often the FIRST step of a flow.  With no terminal named and none alive
        # a terminal is raised, exactly as `run` does; naming a terminal that does not exist is still
        # a refusal (that is a mistake, not a first step).
        sp = self.space(p.get("user"))
        if not p.get("terminal") and not any(s.state not in (ST_EXITED, ST_CLOSED) for s in sp.sessions.values()):
            opened = self.open(p.get("user"), **self._open_kwargs(p))
            p = {**p, "terminal": opened["terminal"]["id"]}
        return self._a_type({**p, "text": text})

    # -- jobs for slow actions (the HTTP API polls these) -----------------------
    SLOW = ("type", "run", "wait", "watch_user", "handover", "abort", "kill", "close", "force_kill")

    def submit(self, action: str, params: Dict[str, Any]) -> str:
        params = {**params, "user": self.resolve_user(params.get("user"))}
        job_id = uuid.uuid4().hex[:12]
        with self._jobs_lock:
            if len(self.jobs) >= 200:
                completed = next((key for key, job in self.jobs.items() if job["state"] == "done"), None)
                if completed is None:
                    raise TerminaterError("The limit of 200 pending terminal jobs is reached.", "too_many_jobs")
                self.jobs.pop(completed)
            self.jobs[job_id] = {"state": "running", "started": time.time(), "result": None,
                                 "action": action}

        def run() -> None:
            res = self.call(action, params)
            with self._jobs_lock:
                self.jobs[job_id].update({"state": "done", "result": res, "finished": time.time()})

        threading.Thread(target=run, name=f"terminater-job-{job_id}", daemon=True).start()
        return job_id

    def job(self, job_id: str) -> Dict[str, Any]:
        with self._jobs_lock:
            data = self.jobs.get(job_id)
            return dict(data) if data else {"state": "unknown"}


ACTIONS = (
    "run", "open", "type", "send_key", "wait", "read", "commands", "abort", "kill", "force_kill",
    "kill_all", "list", "status", "focus", "rename", "layout", "clear", "resize", "watch_user",
    "warn_user", "handover",
)
_ACTION_ALIASES = {
    "execute": "run", "exec": "run", "command": "run", "launch": "open", "new": "open", "spawn": "open",
    "raise": "open", "create": "open", "press": "send_key", "key": "send_key", "keys": "send_key",
    "output": "read", "result": "read", "get_output": "read", "interrupt": "abort", "cancel": "abort",
    "ctrl_c": "abort", "terminate": "kill", "close": "kill", "destroy": "force_kill", "tile": "layout",
    "arrange": "layout", "show": "layout", "hide": "layout", "watch": "watch_user", "observe": "watch_user",
    "warn": "warn_user", "advise": "warn_user", "ask_user": "handover", "history": "commands",
    "force": "force_kill", "kill_force": "force_kill", "forcekill": "force_kill", "killall": "kill_all",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "none", "null")
    return bool(value)


def _printable(keys: str) -> str:
    """Human-readable form of raw keystrokes for the model (ESC sequences named)."""
    out = []
    names = {"\r": "<Enter>", "\t": "<Tab>", "\x7f": "<Backspace>", "\x03": "<Ctrl+C>",
             "\x1b[A": "<Up>", "\x1b[B": "<Down>", "\x1b[C": "<Right>", "\x1b[D": "<Left>",
             "\x1b": "<Esc>", "\x1b[3~": "<Del>"}
    i = 0
    while i < len(keys):
        for seq in ("\x1b[3~", "\x1b[A", "\x1b[B", "\x1b[C", "\x1b[D"):
            if keys.startswith(seq, i):
                out.append(names[seq])
                i += len(seq)
                break
        else:
            ch = keys[i]
            out.append(names.get(ch, ch if ch >= " " else f"<0x{ord(ch):02x}>"))
            i += 1
    return "".join(out)
