# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""terminater_conpty.py -- a Windows ConPTY (pseudo console) wrapper in pure ctypes.

WHY THIS EXISTS (and why it is not ``pywinpty``)
------------------------------------------------
Terminater drives REAL interactive shells (cmd.exe, powershell.exe) so that the
user can SEE them, type into them and take over at any moment.  A shell that is
started with plain pipes is not interactive: it prints no prompt, does no line
editing, and a program such as ``python`` or ``ssh`` refuses to treat it as a
terminal.  The only supported way to give a Windows console program a real
terminal is the ConPTY API (Windows 10 1809+): ``CreatePseudoConsole`` plus
``PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE``.

This module talks to that API through ``ctypes`` and imports NOTHING outside the
standard library.  That matters twice over for Tlamatini:

  * the module is loaded by the Django process (the terminal hub) AND runs
    unchanged inside a pool agent subprocess (standalone mode) -- two different
    interpreters, one file;
  * adding a binary dependency would mean touching the carried-Python and
    PyInstaller carriage for every build, forever.

CONTRACTS (do NOT weaken)
-------------------------
1. Importing this module NEVER raises on a machine without ConPTY; only
   ``ConPty(...)`` does, with ``ConPtyUnavailable`` and a human sentence.
2. Every Win32 prototype declares ``argtypes``/``restype``.  Handles are
   pointer-sized; the ctypes default (``c_int``) truncates them on 64-bit
   Windows, which fails intermittently and only on some machines.
3. The shell is started inside a JOB OBJECT with KILL_ON_JOB_CLOSE, so a forced
   kill removes the WHOLE process tree (the shell plus everything it started).
   If the job cannot be created or assigned (a parent job that forbids nesting),
   the wrapper degrades to a psutil/taskkill tree kill and says so.
4. ``close()`` never deadlocks: ``ClosePseudoConsole`` can block until the output
   pipe is drained, so it runs on its own thread while a drain loop keeps
   reading.
5. Nothing here raises into a caller after construction: ``write`` / ``read`` /
   ``resize`` return a falsy value or ``b''`` on a dead terminal.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

IS_WINDOWS = os.name == "nt"


class ConPtyError(RuntimeError):
    """Base class for every error this module raises."""


class ConPtyUnavailable(ConPtyError):
    """The machine cannot host a pseudo console (not Windows, or too old)."""


# --------------------------------------------------------------------------- #
# Win32 constants                                                              #
# --------------------------------------------------------------------------- #

PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_SUSPENDED = 0x00000004
STARTF_USESTDHANDLES = 0x00000100
STILL_ACTIVE = 259
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
ERROR_BROKEN_PIPE = 109
ERROR_NO_DATA = 232

DEFAULT_COLS = 120
DEFAULT_ROWS = 30


class _Api:
    """Lazily-built namespace of Win32 prototypes (so import never touches them)."""

    pass


_API: Optional[_Api] = None
_API_LOCK = threading.Lock()


def _build_api() -> _Api:
    from ctypes import wintypes

    api = _Api()
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    api.k32 = k32
    api.wintypes = wintypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    api.COORD = COORD
    api.STARTUPINFOW = STARTUPINFOW
    api.STARTUPINFOEXW = STARTUPINFOEXW
    api.PROCESS_INFORMATION = PROCESS_INFORMATION
    api.JOBOBJECT_EXTENDED_LIMIT_INFORMATION = JOBOBJECT_EXTENDED_LIMIT_INFORMATION

    H = wintypes.HANDLE
    PH = ctypes.POINTER(wintypes.HANDLE)

    def _proto(name, restype, *argtypes):
        fn = getattr(k32, name)
        fn.restype = restype
        fn.argtypes = list(argtypes)
        return fn

    api.CreatePipe = _proto("CreatePipe", wintypes.BOOL, PH, PH, ctypes.c_void_p, wintypes.DWORD)
    api.CloseHandle = _proto("CloseHandle", wintypes.BOOL, H)
    api.ReadFile = _proto(
        "ReadFile", wintypes.BOOL, H, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    )
    api.WriteFile = _proto(
        "WriteFile", wintypes.BOOL, H, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    )
    api.WaitForSingleObject = _proto("WaitForSingleObject", wintypes.DWORD, H, wintypes.DWORD)
    api.GetExitCodeProcess = _proto(
        "GetExitCodeProcess", wintypes.BOOL, H, ctypes.POINTER(wintypes.DWORD)
    )
    api.TerminateProcess = _proto("TerminateProcess", wintypes.BOOL, H, wintypes.UINT)
    api.ResumeThread = _proto("ResumeThread", wintypes.DWORD, H)

    # Pseudo console (optional: absent on pre-1809 Windows -> AttributeError).
    try:
        api.CreatePseudoConsole = _proto(
            "CreatePseudoConsole", ctypes.c_long, COORD, H, H, wintypes.DWORD, PH
        )
        api.ResizePseudoConsole = _proto("ResizePseudoConsole", ctypes.c_long, H, COORD)
        api.ClosePseudoConsole = _proto("ClosePseudoConsole", None, H)
        api.has_conpty = True
    except AttributeError:
        api.has_conpty = False

    api.InitializeProcThreadAttributeList = _proto(
        "InitializeProcThreadAttributeList", wintypes.BOOL, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t),
    )
    api.UpdateProcThreadAttribute = _proto(
        "UpdateProcThreadAttribute", wintypes.BOOL, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
    )
    api.DeleteProcThreadAttributeList = _proto(
        "DeleteProcThreadAttributeList", None, ctypes.c_void_p
    )
    api.CreateProcessW = _proto(
        "CreateProcessW", wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW),
        ctypes.POINTER(PROCESS_INFORMATION),
    )
    api.CreateJobObjectW = _proto("CreateJobObjectW", H, ctypes.c_void_p, wintypes.LPCWSTR)
    api.SetInformationJobObject = _proto(
        "SetInformationJobObject", wintypes.BOOL, H, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    )
    api.AssignProcessToJobObject = _proto("AssignProcessToJobObject", wintypes.BOOL, H, H)
    api.TerminateJobObject = _proto("TerminateJobObject", wintypes.BOOL, H, wintypes.UINT)
    return api


def _api() -> _Api:
    global _API
    if _API is None:
        with _API_LOCK:
            if _API is None:
                _API = _build_api()
    return _API


def conpty_available() -> bool:
    """True when this machine can host a pseudo console. Never raises."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(_api().has_conpty)
    except Exception:  # noqa: BLE001 -- probing must never raise
        return False


def _env_block(env: Dict[str, str]) -> str:
    """Build a CreateProcessW Unicode environment block (``K=V\\0...\\0\\0``)."""
    parts = []
    for key in sorted(env, key=lambda k: k.upper()):
        value = env[key]
        if "\0" in key or "\0" in value or "=" in key:
            continue
        parts.append(f"{key}={value}")
    return "\0".join(parts) + "\0\0"


class ConPty:
    """One shell process hosted inside one pseudo console."""

    def __init__(
        self,
        cmdline: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> None:
        if not IS_WINDOWS:
            raise ConPtyUnavailable("Terminater needs Windows: it hosts shells with ConPTY.")
        try:
            self._a = _api()
        except Exception as exc:  # noqa: BLE001
            raise ConPtyUnavailable(f"Win32 API could not be loaded: {exc}") from exc
        if not self._a.has_conpty:
            raise ConPtyUnavailable(
                "This Windows build has no pseudo console (ConPTY needs Windows 10 1809 or newer)."
            )

        self.cols = max(2, int(cols))
        self.rows = max(1, int(rows))
        self.cmdline = cmdline
        self.pid = 0
        self._lock = threading.Lock()
        self._closed = False
        self._closing = False
        self._exited = threading.Event()
        self._exit_code: Optional[int] = None
        self._eof = threading.Event()
        self._reader_attached = False

        self._hpc = None
        self._in_write = None
        self._out_read = None
        self._proc = None
        self._thread = None
        self._job = None
        self._job_ok = False
        self._attr_buf = None

        try:
            self._spawn(cmdline, cwd, env)
        except Exception:
            self._cleanup_handles()
            raise
        threading.Thread(target=self._watch_exit, name=f"conpty-exit-{self.pid}", daemon=True).start()

    # ------------------------------------------------------------------ spawn
    def _spawn(self, cmdline: str, cwd: Optional[str], env: Optional[Dict[str, str]]) -> None:
        a = self._a
        w = a.wintypes
        in_read, in_write = w.HANDLE(), w.HANDLE()
        out_read, out_write = w.HANDLE(), w.HANDLE()
        if not a.CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0):
            raise ConPtyError(f"CreatePipe(input) failed: {ctypes.get_last_error()}")
        if not a.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0):
            a.CloseHandle(in_read)
            a.CloseHandle(in_write)
            raise ConPtyError(f"CreatePipe(output) failed: {ctypes.get_last_error()}")
        self._in_write = in_write
        self._out_read = out_read

        hpc = w.HANDLE()
        coord = a.COORD(self.cols, self.rows)
        hr = a.CreatePseudoConsole(coord, in_read, out_write, 0, ctypes.byref(hpc))
        # The pseudo console duplicated the pipe ends it needs; ours can go.
        a.CloseHandle(in_read)
        a.CloseHandle(out_write)
        if hr != 0:
            raise ConPtyError(f"CreatePseudoConsole failed (HRESULT 0x{hr & 0xFFFFFFFF:08X}).")
        self._hpc = hpc

        # Attribute list carrying the pseudo console handle.
        size = ctypes.c_size_t(0)
        a.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        self._attr_buf = ctypes.create_string_buffer(size.value)
        if not a.InitializeProcThreadAttributeList(self._attr_buf, 1, 0, ctypes.byref(size)):
            raise ConPtyError(f"InitializeProcThreadAttributeList failed: {ctypes.get_last_error()}")
        if not a.UpdateProcThreadAttribute(
            self._attr_buf, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
            hpc, ctypes.sizeof(w.HANDLE), None, None,
        ):
            raise ConPtyError(f"UpdateProcThreadAttribute failed: {ctypes.get_last_error()}")

        si = a.STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(a.STARTUPINFOEXW)
        # STARTF_USESTDHANDLES with NULL handles is what makes the shell take its
        # standard handles from the pseudo console. Without it, a parent whose own
        # stdout is a PIPE (every test harness, every pool agent) leaks that pipe to
        # the child and the shell's output never reaches the terminal at all.
        si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        si.StartupInfo.hStdInput = None
        si.StartupInfo.hStdOutput = None
        si.StartupInfo.hStdError = None
        si.lpAttributeList = ctypes.cast(self._attr_buf, ctypes.c_void_p)
        pi = a.PROCESS_INFORMATION()

        cmd_buf = ctypes.create_unicode_buffer(cmdline)
        env_buf = ctypes.create_unicode_buffer(_env_block(env)) if env is not None else None
        flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED
        cwd_arg = cwd if (cwd and os.path.isdir(cwd)) else None
        ok = a.CreateProcessW(
            None, cmd_buf, None, None, False, flags,
            ctypes.cast(env_buf, ctypes.c_void_p) if env_buf is not None else None,
            cwd_arg, ctypes.byref(si), ctypes.byref(pi),
        )
        if not ok:
            raise ConPtyError(f"CreateProcessW failed for {cmdline!r}: error {ctypes.get_last_error()}")
        self._proc = pi.hProcess
        self._thread = pi.hThread
        self.pid = int(pi.dwProcessId)

        # Put the shell in a kill-on-close job BEFORE it runs a single instruction.
        try:
            job = a.CreateJobObjectW(None, None)
            if job:
                info = a.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if a.SetInformationJobObject(
                    job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                    ctypes.byref(info), ctypes.sizeof(info),
                ) and a.AssignProcessToJobObject(job, self._proc):
                    self._job = job
                    self._job_ok = True
                else:
                    a.CloseHandle(job)
        except Exception:  # noqa: BLE001 -- the psutil fallback covers this
            self._job_ok = False
        a.ResumeThread(self._thread)

    # --------------------------------------------------------------- watchers
    def _watch_exit(self) -> None:
        a = self._a
        try:
            a.WaitForSingleObject(self._proc, INFINITE)
            code = a.wintypes.DWORD(0)
            if a.GetExitCodeProcess(self._proc, ctypes.byref(code)):
                self._exit_code = int(code.value)
        except Exception:  # noqa: BLE001
            pass
        self._exited.set()
        # Give ConPTY a moment to flush the shell's last bytes, then close the
        # pseudo console so a blocked reader sees EOF instead of waiting forever.
        time.sleep(0.25)
        self._close_pseudo_console()

    def _close_pseudo_console(self) -> None:
        with self._lock:
            hpc, self._hpc = self._hpc, None
        if hpc is None:
            return
        done = threading.Event()

        def _run() -> None:
            try:
                self._a.ClosePseudoConsole(hpc)
            except Exception:  # noqa: BLE001
                pass
            finally:
                done.set()

        threading.Thread(target=_run, name="conpty-close", daemon=True).start()
        # If nobody is draining the pipe, ClosePseudoConsole can stall: drain it.
        if not self._reader_attached:
            deadline = time.monotonic() + 3.0
            while not done.is_set() and time.monotonic() < deadline:
                if not self._drain_once():
                    break
        done.wait(timeout=2.0)

    def _drain_once(self) -> bool:
        try:
            buf = ctypes.create_string_buffer(4096)
            got = self._a.wintypes.DWORD(0)
            if self._out_read is None:
                return False
            ok = self._a.ReadFile(self._out_read, buf, 4096, ctypes.byref(got), None)
            return bool(ok) and got.value > 0
        except Exception:  # noqa: BLE001
            return False

    # -------------------------------------------------------------------- I/O
    def attach_reader(self) -> None:
        """Declare that a dedicated thread is draining ``read()`` (close() relies on it)."""
        self._reader_attached = True

    def read(self, size: int = 65536) -> bytes:
        """Block until bytes are available. Returns ``b''`` once the console is gone."""
        if self._out_read is None:
            return b""
        a = self._a
        buf = ctypes.create_string_buffer(size)
        got = a.wintypes.DWORD(0)
        try:
            ok = a.ReadFile(self._out_read, buf, size, ctypes.byref(got), None)
        except Exception:  # noqa: BLE001
            self._eof.set()
            return b""
        if not ok or got.value == 0:
            self._eof.set()
            return b""
        return buf.raw[: got.value]

    def write(self, data: bytes) -> int:
        """Write bytes to the terminal's input. Returns bytes written (0 when dead)."""
        if not data or self._closed or self._in_write is None:
            return 0
        a = self._a
        total = 0
        with self._lock:
            handle = self._in_write
            while total < len(data):
                chunk = data[total:]
                buf = ctypes.create_string_buffer(chunk, len(chunk))
                wrote = a.wintypes.DWORD(0)
                try:
                    ok = a.WriteFile(handle, buf, len(chunk), ctypes.byref(wrote), None)
                except Exception:  # noqa: BLE001
                    return total
                if not ok or wrote.value == 0:
                    return total
                total += int(wrote.value)
        return total

    def resize(self, cols: int, rows: int) -> bool:
        cols, rows = max(2, int(cols)), max(1, int(rows))
        with self._lock:
            hpc = self._hpc
        if hpc is None:
            return False
        try:
            hr = self._a.ResizePseudoConsole(hpc, self._a.COORD(cols, rows))
        except Exception:  # noqa: BLE001
            return False
        if hr == 0:
            self.cols, self.rows = cols, rows
            return True
        return False

    # ------------------------------------------------------------------ state
    def is_alive(self) -> bool:
        return not self._exited.is_set()

    def exit_code(self) -> Optional[int]:
        return self._exit_code

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for the shell to exit. True when it has."""
        return self._exited.wait(timeout)

    @property
    def tree_kill_is_atomic(self) -> bool:
        """True when a kill uses the job object (the whole tree dies as one)."""
        return self._job_ok

    # ------------------------------------------------------------------- kill
    def terminate_tree(self) -> bool:
        """Force-kill the shell and EVERYTHING it started. Idempotent."""
        killed = False
        a = self._a
        if self._job is not None:
            try:
                killed = bool(a.TerminateJobObject(self._job, 1))
            except Exception:  # noqa: BLE001
                killed = False
        if not killed:
            killed = self._kill_tree_fallback()
        return killed

    def _kill_tree_fallback(self) -> bool:
        pid = self.pid
        if not pid:
            return False
        try:
            import psutil  # type: ignore

            try:
                root = psutil.Process(pid)
                victims = root.children(recursive=True) + [root]
            except psutil.NoSuchProcess:
                return True
            for proc in victims:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            return True
        except ImportError:
            pass
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        except Exception:  # noqa: BLE001
            return False

    def child_pids(self) -> list:
        """Live descendant PIDs of the shell (what a user would call 'the command')."""
        try:
            import psutil  # type: ignore

            return [p.pid for p in psutil.Process(self.pid).children(recursive=True)]
        except Exception:  # noqa: BLE001
            return []

    def kill_children(self) -> int:
        """Kill the shell's descendants but leave the shell itself alive."""
        count = 0
        try:
            import psutil  # type: ignore

            for proc in psutil.Process(self.pid).children(recursive=True):
                try:
                    proc.kill()
                    count += 1
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        return count

    # ------------------------------------------------------------------ close
    def close(self, force: bool = False) -> None:
        """Release everything. ``force`` kills the process tree first."""
        if self._closed:
            return
        self._closing = True
        if force and not self._exited.is_set():
            self.terminate_tree()
        self._close_pseudo_console()
        if not self._exited.is_set():
            # Closing the pseudo console sends CTRL_CLOSE_EVENT; allow it to act.
            self._exited.wait(2.0)
        if not self._exited.is_set():
            self.terminate_tree()
            self._exited.wait(2.0)
        self._closed = True
        self._cleanup_handles()

    def _cleanup_handles(self) -> None:
        a = self._a
        # The reader may still be inside ReadFile; a short grace lets it see EOF.
        self._eof.wait(0.5)
        for name in ("_in_write", "_out_read", "_proc", "_thread", "_job"):
            handle = getattr(self, name, None)
            setattr(self, name, None)
            if handle:
                try:
                    a.CloseHandle(handle)
                except Exception:  # noqa: BLE001
                    pass
        if self._attr_buf is not None:
            try:
                a.DeleteProcThreadAttributeList(self._attr_buf)
            except Exception:  # noqa: BLE001
                pass
            self._attr_buf = None
        with self._lock:
            hpc, self._hpc = self._hpc, None
        if hpc:
            try:
                threading.Thread(target=a.ClosePseudoConsole, args=(hpc,), daemon=True).start()
            except Exception:  # noqa: BLE001
                pass


def _selftest() -> int:  # pragma: no cover -- manual probe, never imported by tests
    if not conpty_available():
        print("ConPTY unavailable")
        return 2
    pty = ConPty(r"C:\Windows\System32\cmd.exe /D /K echo conpty-ok", cols=100, rows=20)
    pty.attach_reader()
    deadline = time.monotonic() + 5
    seen = b""
    while time.monotonic() < deadline and b"conpty-ok" not in seen:
        seen += pty.read()
    pty.close(force=True)
    print("ok" if b"conpty-ok" in seen else "FAILED", len(seen), "bytes")
    return 0 if b"conpty-ok" in seen else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_selftest())
