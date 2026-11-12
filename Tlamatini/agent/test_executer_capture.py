# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Real Windows regression for detached children holding Executer's output handles.

The fixture uses explicit ready/finished/release markers. A correct runner returns
when the outer batch exits; it must neither wait for nor terminate its detached
child. No model, user's application, process-name kill or profile temp folder is used.
"""
import ast
import concurrent.futures
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid


EXECUTER_SOURCE = Path(__file__).parent / "agents" / "executer" / "executer.py"
TEST_TEMP_ROOT = Path(__file__).resolve().parents[2] / "Temp" / "executer-capture-tests"


def _execute_function(logger):
    """Lift functions, not Executer's import-time chdir/log/Popen modifications."""
    tree = ast.parse(EXECUTER_SOURCE.read_text(encoding="utf-8"))
    namespace = dict(os=os, sys=sys, re=re, time=time, subprocess=subprocess,
                     tempfile=tempfile, logging=logger, uuid=uuid, Path=Path, Dict=dict,
                     __file__=str(EXECUTER_SOURCE), __name__="executer_capture_fixture", _TIMEOUT=20)
    functions = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.append(node)
        elif isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    namespace[target.id] = value
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(EXECUTER_SOURCE), "exec"), namespace)
    namespace["_TIMEOUT"] = 20
    return namespace["execute_script"]


class _Records(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class _OwnedProcess:
    """Retain a native handle after checking the fixture's exact creation time."""
    def __init__(self, pid, created):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel = kernel
        self.handle = kernel.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "Could not retain fixture process handle")
        stamps = [wintypes.FILETIME() for _ in range(4)]
        ok = kernel.GetProcessTimes(self.handle, *(ctypes.byref(stamp) for stamp in stamps))
        observed = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
        if not ok or observed != created:
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise AssertionError("Fixture process identity changed before its handle was retained")

    def finish(self):
        try:
            state = self.kernel.WaitForSingleObject(self.handle, 5000)
            if state == 0x102:
                # Only the exact fixture process represented by this owned handle.
                if not self.kernel.TerminateProcess(self.handle, 97):
                    raise OSError(ctypes.get_last_error(), "Could not stop owned fixture")
                if self.kernel.WaitForSingleObject(self.handle, 5000) != 0:
                    raise AssertionError("Owned fixture did not terminate")
            elif state != 0:
                raise OSError(ctypes.get_last_error(), "Could not wait for owned fixture")
        finally:
            self.kernel.CloseHandle(self.handle)


FIXTURE = r'''
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time

mode, root = sys.argv[1], Path(sys.argv[2])
deadline = time.monotonic() + 30
if mode == "wait-ready":
    while not (root / "ready.json").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Child did not become ready")
        time.sleep(0.02)
elif mode == "outer-finished":
    (root / "outer-finished").write_text("finished", encoding="ascii")
else:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    stamps = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(ctypes.byref(s) for s in stamps)):
        raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
    created = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    parent_pid = os.getppid()
    parent_handle = kernel.OpenProcess(0x1000, False, parent_pid)
    if not parent_handle:
        raise OSError(ctypes.get_last_error(), "Could not identify fixture shell")
    try:
        if not kernel.GetProcessTimes(parent_handle, *(ctypes.byref(s) for s in stamps)):
            raise OSError(ctypes.get_last_error(), "Could not identify fixture shell creation time")
        parent_created = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
    finally:
        kernel.CloseHandle(parent_handle)
    print("CHILD_STDOUT_BEFORE", flush=True)
    print("CHILD_STDERR_BEFORE", file=sys.stderr, flush=True)
    staging = root / "ready.staging"
    staging.write_text(json.dumps({"pid": os.getpid(), "created": created,
                                  "parent_pid": parent_pid, "parent_created": parent_created}), encoding="ascii")
    staging.replace(root / "ready.json")
    while not (root / "release-child").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Fixture's finite deadline expired")
        time.sleep(0.02)
    print("CHILD_STDOUT_AFTER", flush=True)
    print("CHILD_STDERR_AFTER", file=sys.stderr, flush=True)
    (root / "child-finished").write_text("finished", encoding="ascii")
'''


@unittest.skipUnless(sys.platform == "win32", "Real Windows CMD start/handle-inheritance regression")
class ExecuterCaptureTests(unittest.TestCase):
    def setUp(self):
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="case-", dir=TEST_TEMP_ROOT)
        self.directory = Path(self.temp.name)
        self.assertTrue(self.directory.resolve().is_relative_to(TEST_TEMP_ROOT.resolve()))
        self.original_cwd = Path.cwd()
        os.chdir(self.directory)
        self.records = _Records()
        logger = logging.Logger("executer-capture-test", level=logging.DEBUG)
        logger.addHandler(self.records)
        self.execute = _execute_function(logger)
        self.fixture = self.directory / "fixture.py"
        self.fixture.write_text(FIXTURE, encoding="utf-8")
        self.future = None
        self.thread = None
        self.owned = None
        self.owned_shell = None

    def tearDown(self):
        try:
            # Retain the identity even if an earlier assertion failed just as the child started.
            if self.owned is None and (self.directory / "ready.json").exists():
                self._own_ready_child()
            (self.directory / "release-child").write_text("release", encoding="ascii")
            if self.owned is not None:
                self.owned.finish()
            if self.owned_shell is not None:
                self.owned_shell.finish()
            if self.thread is not None:
                self.thread.join(timeout=10)
                self.assertFalse(self.thread.is_alive(), "Executer worker remained blocked after child release")
        finally:
            os.chdir(self.original_cwd)
            self.temp.cleanup()

    def _command(self, mode):
        return f'"{sys.executable}" "{self.fixture}" "{mode}" "{self.directory}"'

    def _start(self, script):
        self.future = concurrent.futures.Future()

        def work():
            try:
                self.future.set_result(self.execute(script, non_blocking=False, execute_forked_window=False))
            except BaseException as exc:
                self.future.set_exception(exc)

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()

    def _wait_marker(self, name, seconds=10):
        marker = self.directory / name
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if marker.exists():
                return marker
            if self.future is not None and self.future.done() and not self.future.result():
                self.fail("Executer failed before fixture readiness: " + "\n".join(self.records.messages))
            time.sleep(0.02)
        self.fail(f"Fixture marker {name!r} did not appear: " + "\n".join(self.records.messages))

    def _own_ready_child(self):
        identity = json.loads((self.directory / "ready.json").read_text(encoding="ascii"))
        self.owned = _OwnedProcess(identity["pid"], identity["created"])
        self.owned_shell = _OwnedProcess(identity["parent_pid"], identity["parent_created"])

    def _start_detached_fixture(self, *, share_streams=False):
        start_option = " /b" if share_streams else ""
        self._start("\n".join((
            "@echo off",
            f'start "Tlamatini capture regression"{start_option} cmd.exe /d /c "{self._command("child")}"',
            self._command("wait-ready"),
            "echo OUTER_STDOUT", "echo OUTER_STDERR 1>&2",
            self._command("outer-finished"), "exit /b 0",
        )))
        self._wait_marker("ready.json")
        self._own_ready_child()
        self._wait_marker("outer-finished")
        try:
            success = self.future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            self.fail("Outer batch finished, but Executer still waits for the detached child's output handles")
        self.assertTrue(success)
        self.assertFalse((self.directory / "child-finished").exists())
        self.assertEqual(self.owned.kernel.WaitForSingleObject(self.owned.handle, 0), 0x102)
        observed = "\n".join(self.records.messages)
        self.assertIn("OUTER_STDOUT", observed)
        self.assertIn("OUTER_STDERR", observed)
        return observed

    def test_start_returns_after_outer_exit_while_detached_child_keeps_running(self):
        # Normal START creates a console. Windows may give that console its own
        # regular-file stdout/stderr handles. Its child's text need not appear in
        # the outer capture; only the outer script's output belongs to this check.
        self._start_detached_fixture()

    def test_start_b_preserves_shared_streams_and_late_child_output(self):
        # START /B explicitly keeps the current console and shared standard
        # streams. This is the distinct contract that exercises late appends.
        observed = self._start_detached_fixture(share_streams=True)
        self.assertIn("CHILD_STDOUT_BEFORE", observed)
        self.assertIn("CHILD_STDERR_BEFORE", observed)
        # The inherited write handles remain usable after the parent takes its snapshot.
        (self.directory / "release-child").write_text("release", encoding="ascii")
        self._wait_marker("child-finished")
        captures = [path.read_bytes() for path in self.directory.iterdir()
                    if path.is_file() and path.suffix.lower() not in {".py", ".bat", ".json"}]
        self.assertTrue(any(b"CHILD_STDOUT_BEFORE" in data and b"CHILD_STDOUT_AFTER" in data
                            and b"OUTER_STDOUT" in data for data in captures),
                        "Detached stdout must remain appended in its capture file")
        self.assertTrue(any(b"CHILD_STDERR_BEFORE" in data and b"CHILD_STDERR_AFTER" in data
                            and b"OUTER_STDERR" in data for data in captures),
                        "Detached stderr must remain appended in its capture file")

    def test_direct_child_remains_blocking_until_it_exits(self):
        self._start("@echo off\n" + self._command("child") + "\nexit /b 0\n")
        self._wait_marker("ready.json")
        self._own_ready_child()
        self.assertFalse(self.future.done(), "A direct child was incorrectly detached")
        (self.directory / "release-child").write_text("release", encoding="ascii")
        self.assertTrue(self.future.result(timeout=5))
        observed = "\n".join(self.records.messages)
        self.assertIn("CHILD_STDOUT_AFTER", observed)
        self.assertIn("CHILD_STDERR_AFTER", observed)

    def test_nonzero_exit_and_both_output_streams_are_preserved(self):
        success = self.execute("@echo off\necho FINITE_STDOUT\necho FINITE_STDERR 1>&2\nexit /b 7\n")
        self.assertFalse(success)
        observed = "\n".join(self.records.messages)
        self.assertIn("FINITE_STDOUT", observed)
        self.assertIn("FINITE_STDERR", observed)
        self.assertIn("7", observed)
