"""VISIBLE end-to-end proof that Ctrl+C actually quits Tlamatini.

Angela, 2026-08-29. The installed app hung forever on Ctrl+C: a py-spy dump of
the wedged process showed an eleven-deep tower of nested
``signal_handler -> cleanup_pool_on_shutdown`` frames deadlocked in
``Thread.start() -> self._started.wait()``. A source-contract test
(``agent/test_ctrl_c_shutdown.py``) pins the SHAPE of the fix; this one proves
the BEHAVIOUR on the real server: boot Tlamatini, send a REAL console Ctrl+C,
and demand that the process is gone within the grace period.

Run it in a visible foreground window:

    python Tlamatini/tests_e2e/test_ctrl_c_quits_visible.py

It boots the real Django/Daphne stack on a spare port (so it never fights the
installed app on 8000), waits until the port is actually LISTENING, then
attaches to the child's console and raises CTRL_C_EVENT — the same event the
keyboard produces. Nothing is mocked: no fake handler, no simulated signal.

PASS  = the process exited on its own, and fast.
FAIL  = it outlived the deadline (the bug is back) and is killed so the machine
        is left clean either way.
"""

import os
import socket
import subprocess
import sys
import time


# The server gets its own port so a running C:\Tlamatini install is untouched.
PORT = 8043
BOOT_TIMEOUT_SECONDS = 180
# apps.py gives cleanup _SHUTDOWN_GRACE_SECONDS (12s) then hard-exits, so a
# healthy shutdown must land well inside this. The old code never exited at all.
QUIT_DEADLINE_SECONDS = 25

CREATE_NEW_CONSOLE = 0x00000010
CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANAGE_PY = os.path.join(_REPO_ROOT, 'manage.py')


def _say(msg):
    print(msg, flush=True)


def _port_is_listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def _wait_for_boot(proc, port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, f"server exited during boot (code {proc.returncode})"
        if _port_is_listening(port):
            return True, f"listening on :{port}"
        time.sleep(1.0)
    return False, f"never started listening on :{port} within {timeout}s"


# The signal is raised by a THROWAWAY HELPER PROCESS, never by this one.
#
# CTRL_C_EVENT cannot be addressed to a foreign process group, so the sender has
# to FreeConsole() and AttachConsole(child) — and that DETACHES THE SENDER FROM
# ITS OWN CONSOLE. Doing it inline silently destroyed this test's stdout: every
# line after step [2/4] — including the verdict Angela is watching for — went
# nowhere, and the visible window just froze mid-test. A separate helper takes
# the console damage and dies; this process keeps its window and prints the
# result. (Angela, 2026-08-29 — a visible test whose verdict is invisible is
# not a visible test.)
_CTRL_C_SENDER = """
import ctypes, sys
pid = int(sys.argv[1])
k32 = ctypes.windll.kernel32
k32.FreeConsole()
if not k32.AttachConsole(ctypes.c_uint(pid)):
    sys.exit(10)
k32.SetConsoleCtrlHandler(None, True)
sys.exit(0 if k32.GenerateConsoleCtrlEvent(0, 0) else 11)
"""


def _send_real_ctrl_c(pid):
    """Raise a genuine console CTRL_C_EVENT in the child's console."""
    helper = subprocess.run(
        [sys.executable, '-c', _CTRL_C_SENDER, str(pid)],
        capture_output=True, timeout=30,
    )
    if helper.returncode == 0:
        return True, "CTRL_C_EVENT delivered (via helper process)"
    if helper.returncode == 10:
        return False, f"helper could not AttachConsole({pid})"
    return False, f"helper failed to raise CTRL_C_EVENT (rc={helper.returncode})"


def main():
    _say("=" * 74)
    _say("  VISIBLE TEST - Ctrl+C MUST QUIT TLAMATINI")
    _say("  Angela Lopez Mendoza | regression guard for the 2026-08-29 hang")
    _say("=" * 74)

    if not sys.platform.startswith('win'):
        _say("SKIP: this test proves Windows console Ctrl+C behaviour.")
        return 0

    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'

    _say(f"\n[1/4] Booting Tlamatini from source on port {PORT} "
         "(its own console window)...")
    proc = subprocess.Popen(
        [sys.executable, _MANAGE_PY, 'runserver', '--noreload', f'127.0.0.1:{PORT}'],
        cwd=_REPO_ROOT,
        env=env,
        creationflags=CREATE_NEW_CONSOLE,
    )
    _say(f"      server PID = {proc.pid}")

    booted, why = _wait_for_boot(proc, PORT, BOOT_TIMEOUT_SECONDS)
    if not booted:
        _say(f"\n  INCONCLUSIVE: {why}")
        _say("  (The server never came up, so Ctrl+C was never exercised.)")
        try:
            proc.kill()
        except Exception:
            pass
        return 2
    _say(f"      OK - {why}")

    _say("\n[2/4] Sending a REAL console Ctrl+C (CTRL_C_EVENT)...")
    sent_at = time.time()
    sent, detail = _send_real_ctrl_c(proc.pid)
    _say(f"      {detail}")
    if not sent:
        try:
            proc.send_signal(CTRL_BREAK_EVENT)
            _say("      fell back to CTRL_BREAK_EVENT (same handler)")
        except Exception as exc:
            _say(f"      could not signal the server: {exc}")
            proc.kill()
            return 2

    _say(f"\n[3/4] Waiting up to {QUIT_DEADLINE_SECONDS}s for it to exit "
         "on its own...")
    exited = True
    try:
        proc.wait(timeout=QUIT_DEADLINE_SECONDS)
    except subprocess.TimeoutExpired:
        exited = False
    elapsed = time.time() - sent_at

    _say("\n[4/4] Verdict")
    _say("-" * 74)
    if exited:
        _say(f"  PASS - Tlamatini quit {elapsed:.1f}s after Ctrl+C "
             f"(exit code {proc.returncode}).")
        _say("  Ctrl+C terminates the process. The 2026-08-29 hang is fixed.")
        _say("-" * 74)
        return 0

    _say(f"  FAIL - still alive {elapsed:.1f}s after Ctrl+C. THE HANG IS BACK.")
    _say("  Dump its stacks with:  py-spy dump --pid %d" % proc.pid)
    _say("  Expect a tower of signal_handler -> cleanup_pool_on_shutdown frames.")
    _say("-" * 74)
    try:
        proc.kill()
        _say("  (killed it so your machine is left clean)")
    except Exception:
        pass
    return 1


if __name__ == '__main__':
    code = main()
    print("\nPress Enter to close this window...", flush=True)
    try:
        input()
    except Exception:
        pass
    sys.exit(code)
