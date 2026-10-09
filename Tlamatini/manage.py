#!/usr/bin/env python
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Django's command-line utility for administrative tasks."""
import collections
import os
import sys
import threading
import time

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
# This must be set BEFORE importing any packages that use MKL (NumPy, SciPy, etc.)
# (collections/threading/time above are pure stdlib — they never touch MKL.)
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# File dispatch must happen before any database/startup work. Resolve the path
# before frozen mode changes cwd, and reuse a ready instance instead of starting
# a second server. Importing this module for tests has no dispatch side effects.
_FLOW_FILE_OPEN = None
if __name__ == '__main__' and len(sys.argv) == 2 and sys.argv[1].lower().endswith(('.flw', '.fpmt')):
    from agent import flow_file_open as _flow_files
    try:
        _file_url, _file_port, _already_opened = _flow_files.prepare_launch(sys.argv[1])
    except Exception as _file_error:
        _flow_files.launch_error(_file_error)
        raise SystemExit(1)
    if _already_opened:
        raise SystemExit(0)
    _FLOW_FILE_OPEN = (_file_url, _file_port)
    sys.argv = [sys.argv[0], 'runserver', '--noreload', f'127.0.0.1:{_file_port}']



def _set_app_user_model_id():
    """Set the explicit AppUserModelID for taskbar identity.

    Must be called BEFORE any window is created.  This ensures that:
    - The running window groups with the pinned desktop shortcut
    - "Pin to taskbar" from the running instance preserves the Tlamatini icon
    - The process is identified distinctly even when hosted by Windows Terminal

    The ID follows Microsoft's recommended CompanyName.ProductName.SubProduct
    pattern.  Failures are silent — identity is cosmetic.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "XAIHT.Tlamatini.Server"
        )
    except Exception:
        pass


_set_app_user_model_id()


def _brand_console_window():
    """Set the console window's title and icon as early as possible.

    - SetConsoleTitleW: honored by BOTH conhost AND Windows Terminal. So even
      when WT is the host, the tab title becomes "Tlamatini" instead of the
      cmd path.
    - WM_SETICON + LoadImageW: honored by conhost (and respected by every
      icon-displaying surface that reads the window's icon). WT ignores it,
      but it costs nothing and reinforces the icon under conhost.

    Failures here are silent — branding is cosmetic and must never block
    server start-up.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        # 1. Window title — works under any host (conhost / WT / future).
        kernel32.SetConsoleTitleW("Tlamatini")

        # 2. Window icon — locate Tlamatini.ico next to the .exe (frozen) or
        # at the project root (source mode).
        if getattr(sys, 'frozen', False):
            install_dir = os.path.dirname(sys.executable)
        else:
            install_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        ico_path = os.path.join(install_dir, 'Tlamatini.ico')
        if not os.path.isfile(ico_path):
            return

        IMAGE_ICON     = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE  = 0x00000040
        WM_SETICON     = 0x0080
        ICON_SMALL     = 0
        ICON_BIG       = 1

        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR,
            wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SendMessageW.restype = ctypes.c_long
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        kernel32.GetConsoleWindow.restype = wintypes.HWND

        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        # Two LoadImageW calls — one large, one small — so both the title
        # bar (small) and Alt-Tab / taskbar (large) get crisp renderings.
        hicon_small = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 16, 16,
            LR_LOADFROMFILE,
        )
        hicon_big = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 32, 32,
            LR_LOADFROMFILE,
        )
        if not hicon_big:
            hicon_big = user32.LoadImageW(
                None, ico_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
    except Exception:
        pass


_brand_console_window()


# Per-line USER attribution hook. Filled in by agent/log_identity.py::install()
# once the Django app boots -- see that module for the full contract. It stays a
# plain slot and NEVER an import, for two reasons: the tee runs BEFORE Django
# exists, so importing `agent.*` here would drag agent/__init__ (and with it
# protobuf/gRPC) into startup; and a launch without that module must simply
# write untagged lines rather than fail. `None` == nothing bound, zero cost.
_USER_TAG_HOOK = None


class _ConsoleWriter:
    """THE CONSOLE SHIELD — the core never writes to the console window itself.

    THE BUG THIS EXISTS TO KILL (Angela, 2026-09-10). Windows consoles ship with
    **QuickEdit Mode ON**. The moment a user clicks or drags inside the window —
    to copy a line of the log, or merely to make it the active window — Windows
    puts the console into SELECTION mode and ``WriteConsoleW`` **stops
    returning**. It does not fail; it BLOCKS, for as long as the selection is
    held. ⚠️ A ``try/except`` cannot save you here: **a block is not an
    exception.**

    Before this class, ``_TeeStream.write`` wrote to the CONSOLE FIRST and to
    ``tlamatini.log`` SECOND, so one click froze three things at once:

      1. the calling thread, parked inside ``WriteConsoleW``;
      2. ``tlamatini.log`` itself — the durable record held hostage by the
         cosmetic one, which is why the log ALSO stopped growing and made the
         freeze look total;
      3. every other thread, one by one, as each reached the same line.

    Django, Channels, the Multi-Turn executor and every pool agent log, so the
    whole application appeared to hang. Users — reasonably — called it a crash.

    THE FIX is to make the console a sink that CANNOT apply backpressure.
    Chunks are handed to a bounded in-memory queue and drained by ONE daemon
    thread; if the console blocks, only that thread blocks. Selecting text now
    pauses the console DISPLAY and nothing else — the core runs at full speed
    and the log file keeps growing the whole time.

    ⚠️ THIS SHIELD IS THE SECOND LINE OF DEFENCE, NOT THE FIRST. Tlamatini SHIPS
    ``console_quick_edit: false`` (see ``_apply_console_quick_edit_policy``), so
    in a frozen build a click cannot start a selection at all and the window
    never pauses. The shield exists for everything that flag cannot reach: a
    source run (where the knob is announced-and-ignored, because the console is
    the developer's own terminal and outlives us), Windows Terminal and other
    hosts that ignore the flag, a piped stdout whose reader stalls, and anyone
    who deliberately sets the knob back to ``true`` to keep mouse-copy. THIS
    shield is therefore NOT mode-gated: the freeze is identical in dev, where
    log text gets selected most, so both modes get it.

    CONTRACTS (do NOT weaken):

      * ``submit`` **NEVER blocks and NEVER raises.** It sits on the hot path of
        every ``print()`` in the process.
      * The queue is **BOUNDED** and drops the **OLDEST** chunk. A selection
        held for ten minutes must not grow memory without limit.
      * **A DROP IS NEVER SILENT.** The count is reported to the console the
        instant it unblocks AND written into ``tlamatini.log``, pointing at the
        log for the complete record.
      * **CONSOLE chunks may be dropped; LOG LINES NEVER ARE.** The file is
        written on the caller's own thread, before anything is queued.
      * ``close`` is **BOUNDED**. A user still holding a selection at exit must
        not be able to hang the process.
      * ⚠️ Nothing here may take ``_TeeStream._LOG_LOCK`` while holding
        ``_cond``, or vice versa. Callers take the log lock, release it, then
        ``submit``; the drain thread releases ``_cond`` before it notes a drop
        in the log. Nest them and you trade a console freeze for a deadlock.
    """

    _MAX_QUEUED_CHUNKS = 10000
    _MAX_BATCH_CHUNKS = 512
    _CLOSE_TIMEOUT_SECONDS = 2.0
    _DROP_NOTICE = (
        "\n--- [CONSOLE-SHIELD] {count} console chunk(s) dropped while this window "
        "was paused (text selected, or output held). Tlamatini kept running the "
        "whole time — the COMPLETE record is in tlamatini.log.\n"
    )

    # Sentinel meaning "flush this stream", never "write this text".
    _FLUSH = object()

    def __init__(self, note_sink=None):
        self._chunks = collections.deque()
        self._cond = threading.Condition()
        self._dropped = 0
        self._closed = False
        self._thread = None
        self._note_sink = note_sink
        # Optional ``_ConsoleColorizer`` (Angela, 2026-10-08). ``None`` = the
        # console gets exactly the text the log file got, as before.
        self._colorizer = None

    def set_colorizer(self, colorizer):
        """Paint console lines by level from now on (``None`` switches it off).

        The painter runs on THIS class's drain thread only, so colouring costs
        the caller of ``print()`` nothing and can never stall it.
        """
        self._colorizer = colorizer

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name='tlamatini-console-writer', daemon=True
        )
        self._thread.start()

    def submit(self, stream, payload):
        """Queue one chunk for the console. NEVER blocks, NEVER raises."""
        try:
            with self._cond:
                if self._closed:
                    return
                if len(self._chunks) >= self._MAX_QUEUED_CHUNKS:
                    self._chunks.popleft()
                    self._dropped += 1
                self._chunks.append((stream, payload))
                self._cond.notify()
        except Exception:
            pass

    def request_flush(self, stream):
        """Ask for a console flush WITHOUT flushing on the caller's thread.

        ``print(..., flush=True)`` lands in ``_TeeStream.flush``; flushing the
        console there would re-open the exact hole this class closes, because a
        flush on a selected console blocks just like a write to one does.
        """
        self.submit(stream, self._FLUSH)

    def _take_batch(self):
        """Block until there is work, then take a bounded slice of it."""
        with self._cond:
            while not self._chunks and not self._closed:
                self._cond.wait()
            batch = []
            while self._chunks and len(batch) < self._MAX_BATCH_CHUNKS:
                batch.append(self._chunks.popleft())
            dropped, self._dropped = self._dropped, 0
            return batch, dropped, self._closed

    def _run(self):
        while True:
            batch, dropped, closed = self._take_batch()
            if dropped:
                notice = self._DROP_NOTICE.format(count=dropped)
                if batch:
                    self._emit(batch[0][0], notice)
                if self._note_sink is not None:
                    try:
                        self._note_sink(notice)
                    except Exception:
                        pass
            touched = []
            for stream, payload in batch:
                if payload is self._FLUSH:
                    self._flush(stream)
                    continue
                self._emit(stream, payload)
                if stream not in touched:
                    touched.append(stream)
            for stream in touched:
                self._flush(stream)
            if closed and not batch:
                return

    def _emit(self, stream, text):
        painter = self._colorizer
        if painter is not None:
            try:
                text = painter.paint(stream, text)
            except Exception:
                pass  # a broken painter costs the colour, never the text
        try:
            stream.write(text)
        except Exception:
            pass

    def _flush(self, stream):
        try:
            stream.flush()
        except Exception:
            pass

    def close(self, timeout=None):
        """Stop draining, waiting AT MOST ``timeout`` seconds for the tail.

        Bounded on purpose: a user who is still holding a mouse selection when
        Tlamatini exits must never be able to keep the process alive.
        """
        try:
            with self._cond:
                self._closed = True
                self._cond.notify_all()
            thread = self._thread
            if thread is not None and thread.is_alive():
                thread.join(
                    self._CLOSE_TIMEOUT_SECONDS if timeout is None else timeout
                )
        except Exception:
            pass


class _ConsoleColorizer:
    """COLOURS FOR THE CONSOLE WINDOW, by level (Angela, 2026-10-08).

    Angela: *"make the log to be rendered with multicolor depending on debug,
    info, warn, error, fatals"*. Only the WINDOW is painted. ``tlamatini.log``
    never receives a colour code: the tee writes the file on the caller's
    thread BEFORE anything is queued (``_TeeStream._plain`` even strips the
    codes other libraries print, such as Django's coloured access log), and
    this painter runs afterwards, on the console drain thread, on the console
    copy alone.

    The palette uses the standard 16-colour SGR codes, which conhost, Windows
    Terminal and every ANSI terminal render the same way:

        FATAL / CRITICAL            bright white on red
        ERROR and tracebacks        bright red
        WARNING                     bright yellow
        success (the green tick,
        a unittest ``OK``)          bright green
        DEBUG                       grey
        INFO                        the console's own colour, with the
                                    subsystem tag (``--- [MODEL-BRAIN]``) in
                                    cyan and the user tag (``[a3]``) in
                                    magenta, so lines are quick to scan.

    A line's level is decided from its TEXT, deterministically, most specific
    signal first, and only from the START of the line (a word deep inside a
    sentence never repaints it):

      1. a Python traceback: ``Traceback (most recent call last):``, every
         indented line under it, and the exception line that closes it;
      2. an explicit level field in a known log layout (``- ERROR -``,
         ``] WARNING``, ``[DEBUG]``, ``ERROR:``, ``--- ERROR``);
      3. unittest results (``FAIL:``, ``ERROR:``, ``FAILED (``, ``OK``);
      4. the status emoji Tlamatini already prints (the red cross, no-entry,
         stop sign, warning sign, green tick);
      5. a leading word (``Error``, ``Failed``, ``Warning``, ``Debug``);
      6. an exception line (``ValueError: ...``) or a Python warning
         (``file.py:12: DeprecationWarning: ...``);
      7. an HTTP access line's status (5xx red, 4xx yellow).

    A plain INFO line keeps the console's colour. A line that already carries
    colour codes (Django colours its own access log) is left exactly as is.

    CONTRACTS (do NOT weaken):
      * It runs ONLY on the console drain thread (``_ConsoleWriter._emit``),
        never on the caller's thread: painting is off the hot path, and a
        slow or broken painter can never stall a ``print()``.
      * Every painted piece is closed with a reset IN THE SAME WRITE, so a
        colour can never bleed into another stream's text, or into the shell
        prompt after Tlamatini exits.
      * It never changes a character of the text; it only adds colour codes
        around it. It never raises into ``_emit`` (which keeps the plain text
        if it ever did).
      * Only a stream that IS a console able to render colour is painted
        (``_enable_console_colors`` decides); a pipe or a file never gets an
        escape code.
      * ``re`` is imported locally: the tests lift this class out of
        manage.py on its own, the same way they lift the console shield.
    """

    RESET = '\x1b[0m'
    STYLES = {
        'fatal': '\x1b[97;41m',     # bright white on red
        'error': '\x1b[91m',        # bright red
        'warning': '\x1b[93m',      # bright yellow
        'success': '\x1b[92m',      # bright green
        'debug': '\x1b[90m',        # grey
    }
    TAG_STYLE = '\x1b[96m'          # subsystem tag on a plain line: bright cyan
    USER_STYLE = '\x1b[95m'         # per-user tag "[a3]": bright magenta
    _LEVEL_WORDS = {
        'CRITICAL': 'fatal', 'FATAL': 'fatal', 'ERROR': 'error',
        'WARNING': 'warning', 'WARN': 'warning', 'DEBUG': 'debug', 'INFO': None,
    }
    _WORD_LEVELS = {
        'Fatal': 'fatal', 'Error': 'error', 'Failed': 'error', 'FAILED': 'error',
        'Failure': 'error', 'Exception': 'error', 'Warning': 'warning',
        'Debug': 'debug',
    }
    _EMOJI = (
        ('❌', 'error'),        # red cross mark
        ('⛔', 'error'),        # no entry
        ('\U0001f6d1', 'error'),    # stop sign
        ('\U0001f4a5', 'error'),    # collision
        ('⚠', 'warning'),      # warning sign
        ('✅', 'success'),      # green check mark
        ('✔', 'success'),      # heavy check mark
    )
    _HEAD = 120                     # a level is read from the start of a line

    def __init__(self, streams):
        import re
        self._states = {
            id(stream): {'start': True, 'style': None, 'traceback': False}
            for stream in streams
        }
        self._user_re = re.compile(r'\[[^\]\s]{1,40}\d\] ')
        self._tag_re = re.compile(r'(-{2,} )?(\[[A-Za-z0-9][^\]\n]{0,47}\])')
        self._level_re = re.compile(
            r'(?:^-*\s*|\[|\s-\s|\]\s)'
            r'(CRITICAL|FATAL|ERROR|WARNING|WARN|DEBUG|INFO)(?=\]|:|\s|$)'
        )
        self._test_re = re.compile(r'(?:FAIL|ERROR): |FAILED \(|OK(?: \(|$)')
        self._word_re = re.compile(
            r'(?:-{2,}\s*)?(?:\[[^\]\n]{1,48}\]\s*)?'
            r'(Fatal|Error|Failed|FAILED|Failure|Exception|Warning|Debug)\b'
        )
        self._exception_re = re.compile(
            r'[A-Za-z_][\w.]*(Error|Exception|Interrupt|Exit|Warning)(?:: |$)'
        )
        self._traceback_end_re = re.compile(r'[A-Za-z_][\w.]*(?:: |$)')
        self._pywarning_re = re.compile(r':\d+: [A-Za-z]*Warning: ')
        self._http_re = re.compile(
            r'(?:"[A-Z]+ [^"]*"|\b(?:HTTP|WebSocket) [A-Z]+ \S+) ([1-5]\d\d)\b'
        )

    def paint(self, stream, text):
        """Return ``text`` with colour codes added, for ``stream``'s window."""
        state = self._states.get(id(stream))
        if state is None or not text:
            return text
        out = []
        pos = 0
        size = len(text)
        while True:
            newline = text.find('\n', pos)
            end = size if newline < 0 else newline
            if end > pos:
                piece = text[pos:end]
                if state['start']:
                    out.append(self._paint_line_start(piece, state))
                elif state['style']:
                    out.append(state['style'] + piece + self.RESET)
                else:
                    out.append(piece)
            if newline < 0:
                break
            out.append('\n')
            state['start'] = True
            state['style'] = None
            pos = newline + 1
        return ''.join(out)

    def _paint_line_start(self, piece, state):
        out = []
        body = piece
        match = self._user_re.match(piece)
        if match:
            user = match.group(0)
            out.append(self.USER_STYLE + user[:-1] + self.RESET + ' ')
            body = piece[len(user):]
            if not body:
                return ''.join(out)  # the line itself arrives in the next write
        state['start'] = False
        if '\x1b' in body:
            state['style'] = None    # already coloured by its author: leave it
            out.append(body)
            return ''.join(out)
        level = self._classify(body, state)
        style = self.STYLES.get(level) if level else None
        state['style'] = style
        if style:
            out.append(style + body + self.RESET)
            return ''.join(out)
        match = self._tag_re.match(body)
        if match:
            out.append((match.group(1) or '') + self.TAG_STYLE + match.group(2)
                       + self.RESET + body[match.end():])
        else:
            out.append(body)
        return ''.join(out)

    def _classify(self, body, state):
        if state['traceback']:
            if (not body.strip() or body[:1] in ' \t'
                    or body.startswith(('During handling', 'The above exception'))):
                return 'error'
            state['traceback'] = False
            if self._traceback_end_re.match(body):
                return 'error'   # the exception line that closes the traceback
        head = body[:self._HEAD]
        if 'Traceback (most recent call last)' in head:
            state['traceback'] = True
            return 'error'
        if body.startswith(('During handling of the above exception',
                            'The above exception was the direct cause')):
            return 'error'
        match = self._level_re.search(head)
        if match and self._LEVEL_WORDS[match.group(1)] is not None:
            return self._LEVEL_WORDS[match.group(1)]
        match = self._test_re.match(body)
        if match:
            return 'success' if match.group(0).startswith('OK') else 'error'
        level = self._emoji_level(head)
        if level:
            return level
        match = self._word_re.match(body)
        if match:
            return self._WORD_LEVELS[match.group(1)]
        match = self._exception_re.match(body)
        if match:
            return 'warning' if match.group(1) == 'Warning' else 'error'
        if self._pywarning_re.search(head):
            return 'warning'
        match = self._http_re.search(body)
        if match:
            code = match.group(1)
            if code[0] == '5':
                return 'error'
            if code[0] == '4':
                return 'warning'
        return None

    def _emoji_level(self, head):
        best, best_at = None, len(head)
        for mark, level in self._EMOJI:
            at = head.find(mark)
            if 0 <= at < best_at:
                best, best_at = level, at
        return best


class _TeeStream:
    """Duplicates writes to the original console stream and a log file.

    Both sinks are written defensively: if the console window is closed
    (or its handle otherwise becomes invalid), writing to ``self._original``
    can raise OSError. We MUST swallow that — an exception escaping a
    logging call on a background thread can wedge that thread and make the
    server appear hung even though the console is merely gone. The log
    file is the durable record either way.

    Buffered flush policy (speed batch, 2026-07-02): the log-file ``write``
    itself stays per-call (it only fills the file object's internal buffer,
    which is cheap), but the EXPENSIVE ``flush()`` — an OS-level write that
    used to run on every single line and serialized every thread on file
    I/O — is now deferred. The log file is flushed when ANY of these hold:

      * ~8 KB accumulated since the last flush, or
      * >= 1 second passed since the last flush, or
      * the chunk carries an urgent marker (ERROR / Traceback / Exception /
        CRITICAL / FATAL / '!!!' / '❌' / '⛔') — errors must be readable in
        ``tlamatini.log`` IMMEDIATELY, never sitting in a buffer, or
      * somebody calls ``flush()`` explicitly (``print(..., flush=True)``), or
      * process exit / quiet period — ``_setup_log_tee`` registers an atexit
        flush AND a 1-second idle-flusher daemon thread, so the file never
        lags more than ~1 s behind even when the app goes silent mid-burst.

    ``_LOG_LOCK`` is a CLASS-level lock shared by the stdout and stderr tees
    (they write the SAME file handle), so concurrent writes from different
    threads/streams cannot interleave mid-chunk.
    """

    _FLUSH_THRESHOLD_BYTES = 8192
    _FLUSH_INTERVAL_SECONDS = 1.0
    _URGENT_MARKERS = (
        'ERROR', 'Error', 'Traceback', 'Exception', 'CRITICAL', 'Critical',
        'FATAL', 'Fatal', '!!!', '❌', '⛔',
    )
    _LOG_LOCK = threading.RLock()

    # The shared console drain thread, installed by ``_setup_log_tee``. Class
    # level so BOTH tees (stdout and stderr) hand their chunks to the SAME
    # queue: they target the same window, so one queue keeps their relative
    # order intact. ``None`` means "no shield" — a tee built directly (unit
    # tests, or a launch where the shield could not start) then writes to its
    # console inline, exactly as it did before 2026-09-10.
    _CONSOLE_WRITER = None

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file
        self._pending_bytes = 0
        self._last_flush = time.monotonic()
        self._at_line_start = True

    # Terminal colour/cursor codes (CSI sequences), compiled on first use.
    _ANSI_RE = None

    @classmethod
    def _plain(cls, text):
        """``text`` without terminal colour codes. Never raises.

        Costs one ``in`` test when the text has no ESC character, which is
        almost every write. ``re`` is imported here, not at module level, so
        the tests can lift this class out of manage.py on its own.

        It is called OUTSIDE the file write's ``try``, so it must never raise:
        a caller that hands the tee BYTES (or anything that is not text) gets
        it back unchanged, and the file write below swallows it exactly as it
        did before this method existed.
        """
        if not isinstance(text, str) or '\x1b' not in text:
            return text
        try:
            pattern = cls._ANSI_RE
            if pattern is None:
                import re
                pattern = cls._ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
            return pattern.sub('', text)
        except Exception:
            return text

    def _tag_lines(self, data, tag):
        """Prefix every LINE START in ``data`` with the caller's user tag.

        ``print()`` writes the text and its newline as TWO calls, so "am I at
        the start of a line?" is state, not something one chunk can answer --
        ``_at_line_start`` carries it across writes. A chunk that is only a
        newline is left BARE: a blank line belongs to nobody, and tagging it
        would spend characters on nothing (Angela's minimal-space rule).
        """
        ends_newline = data[-1] == '\n'
        body = data[:-1] if ends_newline else data
        if not body:
            self._at_line_start = True
            return data
        head = tag if self._at_line_start else ''
        self._at_line_start = ends_newline
        if '\n' in body:
            body = body.replace('\n', '\n' + tag)
        return head + body + ('\n' if ends_newline else '')

    def write(self, data):
        # --- Per-line USER attribution (Angela, 2026-08-13) --------------
        # ``_USER_TAG_HOOK`` is installed by agent/log_identity.py when the
        # Django app boots. Until then this costs ONE ``is not None`` test;
        # once a user is bound it costs one ContextVar read plus one string
        # concatenation, because the prefix ('[a3] ') was rendered when the
        # user was BOUND, not here. Lines belonging to no user stay bare.
        #
        # ``data`` is never reassigned: the tagged text goes to ``payload``
        # so the return value below stays the number of characters the
        # CALLER asked to write -- a write() that claims it wrote more than
        # it was given would lie to any caller that loops on partial writes.
        payload = data
        if _USER_TAG_HOOK is not None and data:
            try:
                tag = _USER_TAG_HOOK()
                if tag:
                    payload = self._tag_lines(data, tag)
                else:
                    self._at_line_start = data[-1] == '\n'
            except Exception:
                payload = data
        # --- DURABLE SINK FIRST (console shield, Angela, 2026-09-10) ---------
        # ⚠️ This order is load-bearing and was REVERSED on purpose. The console
        # used to be written FIRST, so a user selecting text in the window
        # blocked the caller inside WriteConsoleW and ``tlamatini.log`` stopped
        # growing too — the durable record held hostage by the cosmetic one.
        # A file write can never block on a human, so the file goes first and
        # always wins. Do NOT put the console back above this block.
        #
        # The FILE gets plain text (Angela, 2026-10-08): colour codes belong to
        # the console window only. ``_plain`` strips codes that a library put
        # in the text itself (Django colours its access log), so tlamatini.log
        # never shows "←[32m" in an editor; the console copy keeps them.
        plain = self._plain(payload)
        try:
            with self._LOG_LOCK:
                self._log_file.write(plain)
                self._pending_bytes += len(plain)
                if (
                    self._pending_bytes >= self._FLUSH_THRESHOLD_BYTES
                    or (time.monotonic() - self._last_flush) >= self._FLUSH_INTERVAL_SECONDS
                    or any(marker in plain for marker in self._URGENT_MARKERS)
                ):
                    self._log_file.flush()
                    self._pending_bytes = 0
                    self._last_flush = time.monotonic()
        except Exception:
            pass

        # --- CONSOLE SINK SECOND, and never on THIS thread --------------------
        # ``submit`` hands the chunk to the drain thread and returns at once, so
        # a console held open by a mouse selection can no longer stall the
        # caller. ⚠️ It is called OUTSIDE the ``_LOG_LOCK`` block above — see the
        # lock-ordering contract in ``_ConsoleWriter``. The inline write is kept
        # as the fallback for a tee built without a shield, so this class stays
        # correct on its own.
        writer = self._CONSOLE_WRITER
        if writer is not None:
            writer.submit(self._original, payload)
        else:
            try:
                self._original.write(payload)
            except Exception:
                pass
        return len(data) if isinstance(data, str) else None

    def flush_log_only(self):
        """Flush the DURABLE sink alone — used by the idle-tail flusher.

        The console needs no sentinel every second: the drain thread already
        flushes it after each batch. Keeping the idle flusher off the queue
        means a paused console cannot slowly fill it with flush markers.
        """
        try:
            with self._LOG_LOCK:
                self._log_file.flush()
                self._pending_bytes = 0
                self._last_flush = time.monotonic()
        except Exception:
            pass

    def flush(self):
        # File first and SYNCHRONOUSLY: an explicit flush() must leave the
        # durable record complete before it returns. The console flush is
        # DELEGATED, because flushing a console a user has selected blocks
        # exactly like writing to one does.
        self.flush_log_only()
        writer = self._CONSOLE_WRITER
        if writer is not None:
            writer.request_flush(self._original)
        else:
            try:
                self._original.flush()
            except Exception:
                pass

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def __getattr__(self, name):
        return getattr(self._original, name)


def _setup_log_tee():
    """Redirect stdout and stderr to both the console and tlamatini.log."""
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    log_path = os.path.join(log_dir, 'tlamatini.log')
    try:
        log_file = open(log_path, 'w', encoding='utf-8')  # noqa: SIM115
    except OSError:
        return

    # --- Install the console shield BEFORE the tees go live ------------------
    # One drain thread owns every write to the console window from here on, so
    # a user who selects text in it (QuickEdit Mode) can no longer block the
    # core. Full contract — and the bug it exists to kill — in _ConsoleWriter.
    # ``_note_in_log`` lets the drain thread record a drop in tlamatini.log as
    # well as on screen; it takes ``_LOG_LOCK`` only, never ``_cond``, so the
    # lock ordering stays one-way.
    def _note_in_log(text):
        try:
            with _TeeStream._LOG_LOCK:
                log_file.write(text)
                log_file.flush()
        except Exception:
            pass

    console_writer = _ConsoleWriter(note_sink=_note_in_log)
    console_writer.start()
    _TeeStream._CONSOLE_WRITER = console_writer

    tees = (_TeeStream(sys.stdout, log_file), _TeeStream(sys.stderr, log_file))
    sys.stdout, sys.stderr = tees

    print("--- [CONSOLE-SHIELD] Console writes are queued on a drain thread — "
          "selecting text in this window can no longer block Tlamatini.")

    def _flush_tees():
        for tee in tees:
            try:
                tee.flush()
            except Exception:
                pass

    def _shutdown_console_shield():
        """Exit path: durable record first, then a BOUNDED console drain.

        The buffered tee may hold up to ~1 s / 8 KB of tail, so it must reach
        tlamatini.log on interpreter shutdown. The console tail is drained
        afterwards with a hard timeout — a user still holding a mouse selection
        when Tlamatini exits must never be able to keep the process alive.
        """
        _flush_tees()
        console_writer.close()

    import atexit
    atexit.register(_shutdown_console_shield)

    # Idle-tail flusher: the flush-on-write policy only runs when the NEXT
    # write arrives, so a burst followed by silence would leave its tail
    # invisible to anyone reading tlamatini.log live. This daemon keeps the
    # file no more than ~1 s behind at all times; it swallows everything so
    # interpreter shutdown can never make it raise.
    def _idle_flush_loop():
        while True:
            try:
                time.sleep(_TeeStream._FLUSH_INTERVAL_SECONDS)
                # LOG FILE ONLY (console shield, 2026-09-10). The console is
                # already flushed by the drain thread after every batch, so
                # asking for one here would just post a sentinel per second
                # into a queue that a paused console cannot empty.
                for tee in tees:
                    tee.flush_log_only()
            except Exception:
                pass

    threading.Thread(
        target=_idle_flush_loop, name='tlamatini-log-flusher', daemon=True
    ).start()


_setup_log_tee()


def _enforce_app_temp_dir():
    """Pin ALL temporary files to ``<application-root>/Temp`` — never elsewhere.

    Tlamatini's policy is that every transient artefact (the core process, every
    pool agent it spawns, the STM32 MCP server, external coding-agent CLIs, and
    any third-party library) lives under one ``Temp`` directory at the app root,
    so a single wipe cleans everything and nothing leaks to ``C:\\Temp`` /
    ``%TEMP%``.  We set this BEFORE Django (and before anything imports
    ``tempfile``) so the very first temp allocation already lands correctly, and
    we export the env vars so EVERY child process inherits the same directory
    (``get_agent_env`` in the pool agents does ``os.environ.copy()``).

    Resolution mirrors ``agent/path_guard.py::_get_application_root`` exactly:
      * frozen → directory of the executable (e.g. ``C:\\Tlamatini\\Temp``)
      * source → repo root, two levels above this file's own directory
                 (``manage.py`` sits in the Django project dir, inside the repo
                 root) — e.g. ``D:\\devenv\\source\\Tlamatini\\Temp``.
    Self-contained (no Django / agent import) and fail-open.
    """
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_root = os.path.join(base, 'Temp')
        os.makedirs(temp_root, exist_ok=True)
        for var in ('TMP', 'TEMP', 'TMPDIR'):
            os.environ[var] = temp_root
        os.environ['TLAMATINI_TEMP'] = temp_root
        import tempfile
        tempfile.tempdir = temp_root
        print(f"--- [TEMP] Temporary files pinned to: {temp_root}")
        # Templates: the DEFAULT parent for the template-projects the firmware /
        # engine agents (STM32er / ESP32er / Arduiner / Unrealer) scaffold, unless
        # the user names another path. Exported so spawned agents inherit it.
        templates_root = os.path.join(base, 'Templates')
        os.makedirs(templates_root, exist_ok=True)
        os.environ['TLAMATINI_TEMPLATES'] = templates_root
        print(f"--- [TEMPLATES] Template projects default to: {templates_root}")
    except Exception as exc:
        print(f"--- [TEMP] Could not pin temp/templates directories (non-fatal): {exc}")


def _pin_playwright_browsers():
    """Point Playwright at the browsers CARRIED inside the install (frozen only).

    Playwright keeps its browser binaries OUTSIDE site-packages (normally in
    ``%LOCALAPPDATA%/ms-playwright``), which does not exist on a machine that
    never ran ``playwright install``. The build ships them to
    ``<install_dir>/ms-playwright`` (build.py::bundle_playwright_browsers), so
    here — before Django and before any agent spawns — we export
    ``PLAYWRIGHT_BROWSERS_PATH`` to that directory. Every child process inherits
    it (pool agents do ``os.environ.copy()``), so BOTH the in-process Googler
    tool and the Playwrighter pool agent find chromium/firefox/webkit without a
    system Python or a prior ``playwright install``. Source mode is left alone
    (dev uses the default cache). Fail-open.
    """
    try:
        if not getattr(sys, 'frozen', False):
            return
        browsers = os.path.join(os.path.dirname(sys.executable), 'ms-playwright')
        if os.path.isdir(browsers):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers
            print(f"--- [PLAYWRIGHT] Browsers pinned to: {browsers}")
        else:
            print(f"--- [PLAYWRIGHT] Carried browsers not found at {browsers} "
                  "(Playwrighter/Googler may be unavailable).")
    except Exception as exc:
        print(f"--- [PLAYWRIGHT] Could not pin browser path (non-fatal): {exc}")


def _pin_bundled_tools():
    """Put the CARRIED external runtimes (Java, Git) on JAVA_HOME / PATH (frozen).

    The build carries a JDK/JRE into ``<install_dir>/jre`` and Git into
    ``<install_dir>/git`` (build.py::bundle_java_runtime / bundle_git). Here —
    before Django and before any agent spawns — we export ``JAVA_HOME`` and
    prepend the bundled ``jre/bin`` and ``git/cmd`` (+ mingw64/usr bins) to PATH.
    Every child process inherits this (pool agents do ``os.environ.copy()``), so
    J-Decompiler (java -jar jd-cli.jar), Gitter (bare ``git``), and the STM32er
    MCP git-clone bootstrap all work on a machine with no system Java/Git.
    Source mode is left alone. Fail-open.
    """
    try:
        if not getattr(sys, 'frozen', False):
            return
        base = os.path.dirname(sys.executable)
        extra_path = []
        jre = os.path.join(base, 'jre')
        if os.path.isdir(jre):
            os.environ['JAVA_HOME'] = jre
            jre_bin = os.path.join(jre, 'bin')
            if os.path.isdir(jre_bin):
                extra_path.append(jre_bin)
            print(f"--- [JAVA] JAVA_HOME pinned to carried JRE: {jre}")
        git = os.path.join(base, 'git')
        if os.path.isdir(git):
            for sub in ('cmd', os.path.join('mingw64', 'bin'), os.path.join('usr', 'bin')):
                d = os.path.join(git, sub)
                if os.path.isdir(d):
                    extra_path.append(d)
            print(f"--- [GIT] Carried Git on PATH: {os.path.join(git, 'cmd')}")
        if extra_path:
            os.environ['PATH'] = os.pathsep.join(extra_path) + os.pathsep + os.environ.get('PATH', '')
    except Exception as exc:
        print(f"--- [TOOLS] Could not pin carried Java/Git (non-fatal): {exc}")


def _isolate_carried_python():
    """Frozen only: make every spawned pool agent (which runs on the CARRIED Python
    at <install>/python) IGNORE any stray per-user site-packages (%APPDATA%/Python),
    so agents run COMPLETELY on the carried interpreter's own libs — deterministic and
    immune to a user's --user installs. Exported here (before Django) so every child
    inherits it via os.environ. The firmware agents' per-user lib dirs (e.g. ESPHomer's
    esphome-lib) use PYTHONPATH, which PYTHONNOUSERSITE does NOT disable — they keep
    working. Source mode is left alone (dev relies on its environment). Fail-open.
    """
    try:
        if getattr(sys, 'frozen', False):
            os.environ['PYTHONNOUSERSITE'] = '1'
            print("--- [PYTHON] Pool agents pinned to the carried interpreter (user-site disabled)")
    except Exception as exc:
        print(f"--- [PYTHON] Could not pin carried-Python isolation (non-fatal): {exc}")


def _silence_the_tests():
    """A test run must NEVER make a sound on the developer's desktop.

    Set the flag before anything else initialises, so every spawned pool agent
    inherits it via get_agent_env()'s os.environ.copy(). The audio agents
    (Talker / AudioPlayer / VideoPlayer) check TLAMATINI_NO_AUDIO at the single
    point where sound leaves the machine and skip playback under it.
    """
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'test':
            os.environ['TLAMATINI_NO_AUDIO'] = '1'
    except Exception:
        pass


_silence_the_tests()
_enforce_app_temp_dir()
_pin_playwright_browsers()
_pin_bundled_tools()
_isolate_carried_python()


def _print_version_banner():
    """Print the running Tlamatini version on every startup.

    Lands in both stdout AND ``tlamatini.log`` (the tee is already
    installed by the time we run).  Cheap, never raises, and gives oncall
    a one-line answer to "what's actually deployed here?" without having
    to hit ``/agent/version/``.  See VERSIONING.md.
    """
    try:
        from agent.version import get_version
        version = get_version()
    except Exception:
        version = "0.0.0+unknown"
    print(f"--- [VERSION] Tlamatini {version}")


_print_version_banner()


def _resolve_db_folder_root():
    """Directory that hosts the user-facing ``DB/ToLoad`` and ``DB/Older``
    trees.  In frozen mode this lives next to ``Tlamatini.exe`` (the
    installation root the user can browse to); in source mode it sits next
    to ``manage.py``.  Kept in sync with the user-spec:

      Frozen:   <Drive>:\\<InstallationDir>\\Tlamatini\\DB\\ToLoad\\
      Source:   <Drive>:\\<DevelopmentOptionalDir>\\Tlamatini\\Tlamatini\\DB\\ToLoad\\
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'DB')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DB')


def _resolve_live_db_path():
    """Absolute path of the live ``db.sqlite3`` file Django will open.

    Mirrors ``settings.py``'s ``BASE_DIR / 'db.sqlite3'`` computation
    without importing Django (this runs BEFORE Django is touched):

      * Source: ``<manage.py dir>/db.sqlite3``
      * Frozen: ``<_MEIPASS>/db.sqlite3`` — same place Django will resolve
        ``BASE_DIR`` to, because ``BASE_DIR`` is derived from the bundled
        ``tlamatini/settings.py``'s ``__file__``, which lives inside
        ``_MEIPASS``.  Falls back to the executable directory when
        ``_MEIPASS`` is not set.
    """
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return os.path.join(meipass, 'db.sqlite3')
        return os.path.join(os.path.dirname(sys.executable), 'db.sqlite3')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.sqlite3')


def _apply_pending_db_swap():
    """Replace the live ``db.sqlite3`` with the one in ``DB/ToLoad`` (if any).

    Executed BEFORE any Django import so Django opens the swapped file from
    the very first connection.  Sequence (only if ``DB/ToLoad/db.sqlite3``
    exists):

      1. ``DB/Older/<timestamp>/`` is created.
      2. The current live ``db.sqlite3`` **and its ``-wal``/``-shm``/
         ``-journal`` sidecars** are *moved* into that timestamped directory
         so the user keeps a COMPLETE, restorable audit trail.
      3. Any sidecar still sitting next to the live path is DELETED.
      4. ``DB/ToLoad/db.sqlite3`` is *moved* on top of the live path (its own
         stale sidecars, if any, are dropped too).

    ⚠️ STEP 3 IS LOAD-BEARING — do NOT remove it (Angela, 2026-08-16).
    The database runs in WAL mode (``settings.py`` -> ``PRAGMA
    journal_mode=WAL``). Before this, the swap replaced ``db.sqlite3`` and
    left the PREVIOUS database's ``-wal`` beside it — so on the next open
    SQLite replayed that stale WAL and its pages OVERRODE the database that
    had just been loaded. Set DB therefore appeared to do nothing (Angela ran
    it three times in a row at 22:46/22:48/22:49 against a 3.5 MB stale WAL),
    and in the worst case it merges two different databases, which is real
    corruption. The sidecars are archived FIRST and deleted SECOND: a WAL is
    data, so it is never destroyed, only moved out of the way.

    The moves use :func:`shutil.move` (rename-where-possible, copy+delete
    across filesystems) so the source files are removed once the swap
    completes — a re-launch with the same files in place is a no-op.

    Failures are caught and logged: a corrupt/locked DB must not stop
    Tlamatini from starting up at all.
    """
    import shutil  # local — avoid earliest-startup cost when no swap pending
    import datetime

    try:
        db_root = _resolve_db_folder_root()
        to_load_path = os.path.join(db_root, 'ToLoad', 'db.sqlite3')
        older_root = os.path.join(db_root, 'Older')

        if not os.path.isfile(to_load_path):
            return False  # nothing to swap; common case

        # Stdlib-only and bundled with the app. If this import ever fails, the
        # safe action is to leave the staged DB untouched and abort this swap;
        # falling back to moving only db.sqlite3 recreates the WAL data-loss
        # bug this path exists to prevent.
        from agent import sqlite_copy

        live_db_path = _resolve_live_db_path()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        archive_dir = os.path.join(older_root, timestamp)
        os.makedirs(archive_dir, exist_ok=True)

        if os.path.isfile(live_db_path):
            moved = sqlite_copy.move_with_sidecars(live_db_path, archive_dir)
            print(f"--- [DB SWAP] Archived previous database ({len(moved)} file(s)) "
                  f"-> {archive_dir}")
        else:
            print(f"--- [DB SWAP] No previous db.sqlite3 found at {live_db_path}")

        # THE fix: nothing of the OLD database may survive beside the new one.
        leftovers = sqlite_copy.remove_sidecars(live_db_path, strict=True)
        if leftovers:
            print("--- [DB SWAP] Removed stale WAL/SHM left by the previous "
                  f"database: {', '.join(os.path.basename(p) for p in leftovers)}")

        live_parent = os.path.dirname(live_db_path)
        if live_parent:
            os.makedirs(live_parent, exist_ok=True)
        shutil.move(to_load_path, live_db_path)
        sqlite_copy.remove_sidecars(to_load_path, strict=True)
        print(f"--- [DB SWAP] Loaded DB/ToLoad/db.sqlite3 -> {live_db_path}")
        return True
    except Exception as exc:
        print(f"--- [DB SWAP] Skipped due to error: {exc}")
        return False


_apply_pending_db_swap()


def _post_update_migrate_flag_path():
    """Path of the marker the updater drops to request a post-update migrate.

    Lives in the PRESERVED ``DB`` folder so it survives the self-update file
    swap (``apply_update.ps1`` preserves ``DB``).
    """
    return os.path.join(_resolve_db_folder_root(), 'post_update_migrate.flag')


def _run_post_update_migrate_if_flagged():
    """Migrate the user's database after a self-update, preserving their data.

    The updater (``apply_update.ps1``) copies the user's live ``db.sqlite3`` into
    ``DB/ToLoad`` and drops ``DB/post_update_migrate.flag``. On the next launch
    ``_apply_pending_db_swap()`` (above) restores that database over the freshly
    shipped one, then this applies Django ``migrate`` so new migrations -- new
    agents / ``chat_agent_*`` tools / demo prompts -- are added to the user's
    data WITHOUT wiping their chat history or custom Tool/Mcp/Agent toggles.

    ``migrate`` runs in a CHILD process: ``agent.apps.AgentConfig.ready()`` only
    starts the MCP servers for ``runserver``/``startserver``/``daphne``/``asgi``
    commands, so a child ``migrate`` starts no servers and cannot recurse. It is
    invoked ONLY from the server-launch path (never from the child), and is
    fail-safe -- a migrate error is logged but never blocks startup, and the
    flag is always cleared afterwards so a launch can never loop.
    """
    import subprocess
    try:
        flag = _post_update_migrate_flag_path()
        if not os.path.isfile(flag):
            return
    except Exception:
        return
    print("--- [DB MIGRATE] Post-update migration flagged; bringing your database "
          "to the current version (your history + toggles are kept)...")
    try:
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, 'migrate', '--noinput']
        else:
            cmd = [sys.executable, os.path.abspath(__file__), 'migrate', '--noinput']
        result = subprocess.run(cmd)
        if result.returncode == 0:
            print("--- [DB MIGRATE] Database migrated to the current version.")
        else:
            print(f"--- [DB MIGRATE] migrate exited with code {result.returncode}; continuing startup.")
    except Exception as exc:
        print(f"--- [DB MIGRATE] Skipped due to error: {exc}")
    finally:
        try:
            os.remove(_post_update_migrate_flag_path())
        except OSError:
            pass


def _resolve_config_path():
    """Absolute path to config.json.

    ``CONFIG_PATH`` env overrides; otherwise it sits next to the frozen
    ``Tlamatini.exe`` and at ``agent/config.json`` in source mode. Stdlib-only
    on purpose: this runs before Django is imported.
    """
    override = os.environ.get('CONFIG_PATH')
    if override:
        return override
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent', 'config.json')


def _apply_console_quick_edit_policy():
    """Honour config.json's ``console_quick_edit``. **Tlamatini SHIPS it FALSE.**

    QuickEdit Mode is what lets a user select text in the console window with
    the mouse — and, because Windows freezes console output while a selection
    is held, it is what used to hang Tlamatini (see ``_ConsoleWriter``).

    ⚠️ SHIPPED VALUE ``false``; CODE FALLBACK ``true``. Those are two different
    things and both are deliberate. The shipped `config.json` says ``false`` so
    a click can never start a selection; a **missing or malformed** key still
    falls back to ``true`` so a broken config can never stop startup.

    ⚠️ IT SHIPPED ``true`` FOR ONE DAY AND THAT WAS WRONG (Angela, 2026-09-10).
    The reasoning was that the queue shield already keeps the core and the log
    file alive under a selection, so taking mouse-copy away would be removing a
    feature people legitimately use. What that reasoning missed is that a user
    cannot SEE the core: Angela clicked the window, the lines stopped, and
    Tlamatini looked hung until she pressed Enter and the backlog flooded in.
    Her ruling, verbatim: *"LOG MUST BE STILL INCREMENTING, I DONT CARE IF THE
    STUPID USER CANT COPY CONTENT FROM THE CONSOLE WINDOW"*. A visibly-live
    console beats drag-to-select. Copy with right-click ▸ Mark instead.

    ⚠️ ``ENABLE_EXTENDED_FLAGS`` MUST be OR-ed in. Without it Windows ignores a
    change to the QuickEdit/Insert bits entirely and the call silently does
    nothing.

    ⚠️ FROZEN BUILDS ONLY (Angela, 2026-09-10). Console mode belongs to the
    CONSOLE, not to the process that changes it. In a frozen build Tlamatini
    OWNS its window and the window dies with the process, so the change is
    contained. From SOURCE, Tlamatini is a GUEST inside the developer's own
    terminal, which OUTLIVES it — disabling QuickEdit there would leave that
    terminal unable to select text after the server exits, with nothing on
    screen to explain why. Save-and-restore was considered and rejected: a hard
    kill (``taskkill``, the updater's process-tree kill) skips ``atexit``, so it
    would still leak, just less often. The queue shield itself is deliberately
    NOT gated — the freeze is identical in dev, where log text gets selected
    most, so gating it would leave the developer holding the bug.

    Honest limit: this is a **conhost** setting. Windows Terminal does not
    honour it the same way, and selecting text there can still stall output —
    which is precisely why the queue shield, not this knob, is the actual fix.
    This only ever touches the STDIN handle's mode; the console window's title
    and Tlamatini icon (``_brand_console_window``) live on the HWND and are
    completely untouched by it. Fail-open throughout.
    """
    if os.name != 'nt':
        return
    try:
        import json
        enabled = True
        try:
            with open(_resolve_config_path(), 'r', encoding='utf-8-sig') as fh:
                raw = json.load(fh).get('console_quick_edit', True)
            if isinstance(raw, bool):
                enabled = raw
            elif isinstance(raw, str):
                enabled = raw.strip().lower() not in ('false', '0', 'no', 'off')
        except FileNotFoundError:
            pass
        if enabled:
            return  # Windows default — the shield makes selecting safe already.

        # Frozen-only gate. Announced rather than silent: the user explicitly
        # asked for something, so they are told exactly why it did not happen.
        if not getattr(sys, 'frozen', False):
            print("--- [CONSOLE-SHIELD] console_quick_edit=false IGNORED in source mode: "
                  "this is your terminal, not Tlamatini's window, and the setting would "
                  "outlive the server. It applies to frozen builds only. The queue shield "
                  "protects you here either way.")
            return

        import ctypes
        from ctypes import wintypes

        STD_INPUT_HANDLE = -10
        ENABLE_PROCESSED_INPUT = 0x0001   # ⚠️ THIS BIT IS CTRL+C. Never clear it.
        ENABLE_QUICK_EDIT_INPUT = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        if not handle or handle == wintypes.HANDLE(-1).value:
            return
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            print("--- [CONSOLE-SHIELD] console_quick_edit=false, but this host "
                  "has no console input mode to change (ignored).")
            return
        # ⚠️⚠️ CTRL+C PROTECTION (Angela, 2026-09-10) — DO NOT WEAKEN. ⚠️⚠️
        #
        # Ctrl+C is ``ENABLE_PROCESSED_INPUT`` (0x0001). It is a DIFFERENT bit from
        # QuickEdit, but it lives in the SAME DWORD, so a careless SetConsoleMode is
        # precisely how a program silently loses Ctrl+C. In Tlamatini that would not
        # merely be an annoyance: SIGINT is what runs ``apps.py``'s Tier-3 orphan
        # reaper and the pool-directory cleanup, so a lost Ctrl+C means a build-up of
        # orphaned agent processes and a session that can only be killed from Task
        # Manager. Two rules, both belt-and-braces:
        #
        #   1. FORCE the bit ON rather than merely preserving it, so Tlamatini can
        #      never ship — or inherit — a console whose Ctrl+C is off.
        #   2. READ THE MODE BACK, and if Ctrl+C did not survive, ROLL THE WHOLE
        #      CHANGE BACK to the exact mode we found and give up on QuickEdit.
        #
        # FAIL TOWARD CTRL+C, ALWAYS. Keeping QuickEdit on costs a paused console
        # window; losing Ctrl+C costs the user control of their own machine. When
        # the two conflict, Ctrl+C wins — no exceptions, no "it probably works".
        new_mode = ((mode.value | ENABLE_EXTENDED_FLAGS | ENABLE_PROCESSED_INPUT)
                    & ~ENABLE_QUICK_EDIT_INPUT)
        ok = bool(kernel32.SetConsoleMode(handle, new_mode))
        if ok:
            check = wintypes.DWORD()
            if (kernel32.GetConsoleMode(handle, ctypes.byref(check))
                    and not (check.value & ENABLE_PROCESSED_INPUT)):
                kernel32.SetConsoleMode(handle, mode.value)  # ROLL BACK, exactly.
                print("--- [CONSOLE-SHIELD] QuickEdit change ROLLED BACK: this host "
                      "dropped ENABLE_PROCESSED_INPUT, which would have broken Ctrl+C. "
                      "Ctrl+C is more important than mouse selection, so the console "
                      "mode was restored untouched. The queue shield still protects "
                      "Tlamatini.")
                return
        if ok:
            print("--- [CONSOLE-SHIELD] QuickEdit DISABLED (console_quick_edit=false): "
                  "mouse selection is off; copy with right-click ▸ Mark. Under Windows "
                  "Terminal this flag may be ignored — the queue shield still protects you.")
        else:
            print("--- [CONSOLE-SHIELD] Could not disable QuickEdit (host refused); "
                  "the queue shield still protects Tlamatini.")
    except Exception as exc:  # noqa: BLE001 - a console knob must never stop startup
        print(f"--- [CONSOLE-SHIELD] QuickEdit policy skipped (non-fatal): {exc}")


def _console_vt_on(std_id):
    """Make one Windows console output handle RENDER colour codes. True = it does.

    Colour codes are only drawn when the console has VIRTUAL TERMINAL
    PROCESSING on (``ENABLE_VIRTUAL_TERMINAL_PROCESSING``, 0x0004); without it
    they print as "←[91m" garbage. This ADDS that bit and
    ``ENABLE_PROCESSED_OUTPUT`` (0x0001, which it needs), NEVER clears a bit,
    and READS THE MODE BACK: only a console that really has the bit on now
    counts. Unlike QuickEdit this is safe in both modes: it takes nothing away
    from a developer's terminal (PowerShell and Windows Terminal already run
    with it on), it only lets colour render. Never raises.
    """
    try:
        import ctypes
        from ctypes import wintypes

        ENABLE_PROCESSED_OUTPUT = 0x0001
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        handle = kernel32.GetStdHandle(std_id)
        if not handle or handle == wintypes.HANDLE(-1).value:
            return False
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        kernel32.SetConsoleMode(
            handle,
            mode.value | ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING,
        )
        check = wintypes.DWORD()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(check))
                    and check.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        return False


def _owner_process_name(hwnd):
    """Executable name of the process that OWNS window ``hwnd`` ('' if none).

    stdlib only (manage.py runs before Django): GetWindow(GW_OWNER), then
    GetAncestor(GA_ROOTOWNER), then the owner's process image name.
    """
    try:
        import ctypes
        from ctypes import wintypes

        # PRIVATE library objects: the argtypes set below must not leak into the
        # shared ctypes.windll function cache other code in this process uses.
        user32 = ctypes.WinDLL('user32')
        kernel32 = ctypes.WinDLL('kernel32')
        user32.GetWindow.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        owner = user32.GetWindow(hwnd, 4)            # GW_OWNER
        if not owner:
            owner = user32.GetAncestor(hwnd, 3)      # GA_ROOTOWNER
        if not owner or owner == hwnd:
            return ''
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId(owner, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return ''
        kernel32.OpenProcess.restype = wintypes.HANDLE
        process = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not process:
            return ''
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(1024)
            if not kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return ''
            return os.path.basename(buffer.value)
        finally:
            kernel32.CloseHandle(process)
    except Exception:  # noqa: BLE001
        return ''


def _console_host():
    """WHICH program is drawing this console window. Never raises.

    Measured, not guessed, from the window class of the console handle:

      * ``ConsoleWindowClass``  - the classic Windows console (conhost);
      * ``PseudoConsoleWindow`` - a pseudo-console: a terminal app draws the
        text. Windows Terminal (``WT_SESSION``) is the DEFAULT console on
        Windows 11, so a double-clicked Tlamatini.exe lands there too; the VS
        Code / Antigravity terminal sets ``TERM_PROGRAM=vscode``.

    It matters because the hosts differ: Windows Terminal always renders colour
    and UTF-8 but IGNORES the QuickEdit flag (the queue shield covers it), and
    conhost needs virtual-terminal processing switched on to draw colour.
    """
    if os.name != 'nt':
        return os.environ.get('TERM_PROGRAM') or 'terminal'
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleWindow.restype = wintypes.HWND
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return 'no console window'
        buffer = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(hwnd, buffer, 64)
        window_class = buffer.value
        if window_class == 'ConsoleWindowClass':
            return 'conhost (classic Windows console)'
        if window_class == 'PseudoConsoleWindow':
            # The terminal app OWNS the hidden pseudo-console window. Its process
            # name is the measurement; environment variables are only a fallback,
            # because a child INHERITS them from whatever launched it (a program
            # started from an IDE terminal still carries TERM_PROGRAM=vscode even
            # when Windows hands its window to Windows Terminal).
            terminal = _owner_process_name(hwnd)
            names = {
                'windowsterminal.exe': 'Windows Terminal',
                'code.exe': 'VS Code terminal',
                'code - insiders.exe': 'VS Code terminal',
                'antigravity.exe': 'Antigravity terminal',
                'cursor.exe': 'Cursor terminal',
            }
            if terminal:
                return names.get(terminal.lower(), terminal)
            if os.environ.get('WT_SESSION'):
                return 'Windows Terminal'
            if os.environ.get('TERM_PROGRAM', '').lower() == 'vscode':
                return 'VS Code-family terminal'
            return 'a pseudo-console terminal (Windows Terminal or similar)'
        return window_class or 'unknown console'
    except Exception:  # noqa: BLE001 - a label must never stop startup
        return 'unknown console'


def _console_utf8():
    """Make the console's OUTPUT CODE PAGE UTF-8 (65001); return a status text.

    Tlamatini's own lines are unaffected by the code page (Python writes the
    console in UTF-16), but CHILD programs that share the window write BYTES,
    and under the old DOS code page (437/850) their accents and symbols turn
    into "Γëê"-style garbage. FROZEN builds only, for the same reason as
    QuickEdit: from source the console is the developer's own terminal and the
    code page would OUTLIVE the server. Read back after setting; never raises.
    """
    if os.name != 'nt':
        return 'UTF-8'
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        current = int(kernel32.GetConsoleOutputCP())
        if current == 65001:
            return 'code page 65001 (UTF-8)'
        if not getattr(sys, 'frozen', False):
            return 'code page %d (your terminal\'s, left as is in source mode)' % current
        kernel32.SetConsoleOutputCP(65001)
        if int(kernel32.GetConsoleOutputCP()) == 65001:
            return 'code page 65001 (UTF-8, switched from %d)' % current
        return 'code page %d (the console refused UTF-8)' % current
    except Exception:  # noqa: BLE001
        return 'code page unknown'


def _enable_console_colors():
    """Paint the CONSOLE WINDOW by level (Angela, 2026-10-08). Never stops startup.

    Errors red, fatals white on red, warnings yellow, debug grey, successes
    green, plain INFO in the console's own colour. Full palette and rules:
    ``_ConsoleColorizer``. ``tlamatini.log`` stays plain text either way.

    Off when any of these hold, and it SAYS which:
      * config.json ``console_colors`` is false (it SHIPS true; a missing or
        malformed value counts as true);
      * the ``NO_COLOR`` environment variable is set (https://no-color.org);
      * the output is not a console (a pipe or a file never gets an escape
        code), or the console cannot render colour (``_console_vt_on``).

    Lines printed before ``main()`` runs (the first startup banner) stay
    uncoloured; everything after this call is painted.
    """
    writer = _TeeStream._CONSOLE_WRITER
    if writer is None:
        return
    try:
        import json
        # The console TYPE is measured and announced first (Angela: "make sure
        # the type of console is assured"): every line below names it.
        host = _console_host()
        codepage = _console_utf8()
        print(f"--- [CONSOLE] host: {host} | {codepage}")
        if os.environ.get('NO_COLOR'):
            print("--- [CONSOLE-COLORS] OFF: the NO_COLOR environment variable is set "
                  f"(host: {host}).")
            return
        enabled = True
        try:
            with open(_resolve_config_path(), 'r', encoding='utf-8-sig') as fh:
                raw = json.load(fh).get('console_colors', True)
            if isinstance(raw, bool):
                enabled = raw
            elif isinstance(raw, str):
                enabled = raw.strip().lower() not in ('false', '0', 'no', 'off')
        except Exception:  # noqa: BLE001 - a missing/bad config keeps the default
            pass
        if not enabled:
            print("--- [CONSOLE-COLORS] OFF (console_colors=false in config.json; "
                  f"host: {host}).")
            return
        consoles = []
        for name, std_id in (('stdout', -11), ('stderr', -12)):
            original = getattr(getattr(sys, name, None), '_original', None)
            if original is None:
                continue
            try:
                if not original.isatty():
                    continue
            except Exception:  # noqa: BLE001
                continue
            consoles.append((original, std_id))
        if not consoles:
            # A pipe or a file: never put escape codes there.
            print("--- [CONSOLE-COLORS] OFF: the output is a pipe or a file, not a "
                  "console window.")
            return
        if os.name == 'nt':
            consoles = [(stream, std_id) for stream, std_id in consoles
                        if _console_vt_on(std_id)]
            if not consoles:
                print("--- [CONSOLE-COLORS] OFF: this console cannot render colours "
                      f"(virtual-terminal processing was refused; host: {host}).")
                return
        writer.set_colorizer(_ConsoleColorizer([stream for stream, _ in consoles]))
        print(f"--- [CONSOLE-COLORS] ON in {host}: errors red, fatals white on red, "
              "warnings yellow, debug grey, successes green. tlamatini.log stays "
              "plain text.")
    except Exception as exc:  # noqa: BLE001 - colour must never stop startup
        print(f"--- [CONSOLE-COLORS] skipped (non-fatal): {exc}")


def _resolve_django_port(default_port: int = 8000) -> int:
    """Django/Daphne listen port, read from config.json's ``django_port``.

    Lets a machine where Windows/Hyper-V has reserved port 8000 (``WinError
    10013`` — "an attempt was made to access a socket in a way forbidden by
    its access permissions") move the dev server WITHOUT a rebuild, just by
    editing config.json. Fails open to *default_port* on any missing /
    unreadable / out-of-range value so a bad config can never stop the server
    from starting.
    """
    try:
        import json
        with open(_resolve_config_path(), 'r', encoding='utf-8-sig') as fh:
            raw = json.load(fh).get('django_port', default_port)
        port = int(raw)
        if 1 <= port <= 65535:
            return port
        print(f"--- [PORT] config.json django_port={raw!r} out of range 1-65535; using {default_port}")
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001 - never let a bad config stop startup
        print(f"--- [PORT] Could not read django_port from config.json ({exc}); using {default_port}")
    return default_port


_SERVER_COMMANDS = ('runserver', 'startserver')


def _apply_configured_port(argv):
    """Inject config.json's ``django_port`` when a server command omits a port.

    ONE rule for EVERY launch path, so the configured port is not a frozen-only
    privilege:

      * frozen bare double-click / ``.flw`` association — the frozen block above
        already appended an explicit ``0.0.0.0:<port>``, so this is a no-op there;
      * source ``python manage.py runserver`` (the documented dev command);
      * ``python manage.py startserver`` — its ``addrport`` is forwarded verbatim
        to ``runserver`` (see ``agent/management/commands/startserver.py``).

    An EXPLICIT ``[ipaddr:]port`` on the command line ALWAYS WINS — it is the
    documented override and is never second-guessed. A bare port is appended (not
    ``0.0.0.0:<port>``) so Django's default host binding stays LOOPBACK in source
    mode; only the frozen paths deliberately bind ``0.0.0.0``.

    Anything that is not a server command is returned untouched.
    """
    if len(argv) < 2 or argv[1] not in _SERVER_COMMANDS:
        return argv
    # Any positional (non-flag) token after the command IS the addrport → user wins.
    if any(not token.startswith('-') for token in argv[2:]):
        return argv
    return argv + [str(_resolve_django_port())]


def _schedule_browser_open(url: str, delay_seconds: float = 10.0) -> None:
    """Open the default browser at *url* after *delay_seconds*.

    Used when the desktop/taskbar shortcut launches Tlamatini.exe directly
    (no PowerShell wrapper) so users still get the auto-open behavior the
    legacy Tlamatini.ps1 wrapper provided.
    """
    import threading
    import webbrowser

    def _open():
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"--- [BROWSER] Failed to open {url}: {e}")

    timer = threading.Timer(delay_seconds, _open)
    timer.daemon = True
    timer.start()
    print(f"--- [BROWSER] {url} will open in {int(delay_seconds)} seconds...")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tlamatini.settings')

    # Console QuickEdit policy (Angela, 2026-09-10). A no-op unless the user
    # explicitly set ``console_quick_edit: false``. Skipped for ``test`` so a
    # developer's own terminal is never reconfigured by a test run.
    if not (len(sys.argv) >= 2 and sys.argv[1] == 'test'):
        _apply_console_quick_edit_policy()

    # Console colours by level (Angela, 2026-10-08). Every command, both modes:
    # it only ADDS the bit that lets a console render colour, and a pipe or a
    # file never receives a colour code. tlamatini.log stays plain text.
    _enable_console_colors()

    if getattr(sys, 'frozen', False):
        try:
            os.chdir(os.path.dirname(sys.executable))
        except OSError:
            pass
        if len(sys.argv) == 1:
            sys.argv = [sys.argv[0], 'runserver', '--noreload', f'0.0.0.0:{_resolve_django_port()}']
    if _FLOW_FILE_OPEN:
        from agent.flow_file_open import schedule_open
        schedule_open(*_FLOW_FILE_OPEN)
    elif getattr(sys, 'frozen', False) and len(sys.argv) >= 2 and sys.argv[1] == 'runserver':
        _schedule_browser_open(f'http://localhost:{_resolve_django_port()}/', delay_seconds=10.0)

    # Configurable web port: honor config.json's ``django_port`` on EVERY launch
    # path — the frozen rewrites above, the source ``runserver``, and
    # ``startserver`` — unless the command line already carries an explicit
    # [ipaddr:]port, which always wins. Fail-open: a missing/bad key keeps 8000.
    sys.argv = _apply_configured_port(sys.argv)

    # Post-update database migration: bring the user's just-restored DB to the
    # current schema BEFORE the server starts. Gated on the launch command so
    # the child ``migrate`` it spawns (whose argv is ``migrate``) can never
    # re-enter this branch and recurse.
    if len(sys.argv) >= 2 and sys.argv[1] in ('runserver', 'startserver'):
        _run_post_update_migrate_if_flagged()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHON_HOME environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
