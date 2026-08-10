# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Executer Agent - Deterministic agent to execute a command
# Logs EXECUTION SUCCESS or EXECUTION FAILED based on result
# Always triggers downstream agents regardless of success/failure

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core and inherited by every
# spawned agent via get_agent_env's os.environ.copy()) so every temp file this
# agent writes lands under <app>/Temp — never C:\Temp, %TEMP%, or the OS default
# temp dir. Fail-open: when the handle is unset (agent launched fully standalone)
# Python's default tempdir is used.
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    try:
        import tempfile as _tlt_tempfile
        _tlt_temp_root = os.environ['TLAMATINI_TEMP'].strip()
        os.makedirs(_tlt_temp_root, exist_ok=True)
        _tlt_tempfile.tempdir = _tlt_temp_root
        os.environ['TEMP'] = _tlt_temp_root
        os.environ['TMP'] = _tlt_temp_root
    except Exception:
        pass

import time
import yaml
import logging
import subprocess

# -- conhost.exe orphan guard ------------------------------------------
# When Tlamatini's runtime launches us with DETACHED_PROCESS we have no
# console attached. Any child we Popen WITHOUT CREATE_NO_WINDOW makes
# Windows allocate a fresh console (and a companion conhost.exe) for the
# child -- which lingers as an orphan bearing the Tlamatini icon if we
# exit before the child detaches. Default every Popen to
# CREATE_NO_WINDOW unless the caller explicitly asked for a console
# (CREATE_NEW_CONSOLE) or detached the child themselves.
if os.name == 'nt' and not getattr(subprocess, '_conhost_guard_applied', False):
    _CHG_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _CHG_RESPECT = (
        _CHG_NO_WINDOW
        | getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        | getattr(subprocess, 'DETACHED_PROCESS', 0)
    )
    _chg_orig_init = subprocess.Popen.__init__
    def _chg_guarded_init(self, *args, **kwargs):
        cf = kwargs.get('creationflags', 0) or 0
        if not (cf & _CHG_RESPECT):
            kwargs['creationflags'] = cf | _CHG_NO_WINDOW
        return _chg_orig_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _chg_guarded_init
    subprocess._conhost_guard_applied = True
from typing import Dict

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
    """Get the command to run a Python script."""
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    
    # Prefer PYTHON_HOME from USER environment variables
    python_home = get_user_python_home()
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(python_exe):
            return [python_exe]

    if sys.platform.startswith('win'):
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']
    
    return ['python3']



def get_user_python_home() -> str:
    """Resolve the Python home used to spawn pool-agent subprocesses.

    FROZEN: ALWAYS prefer the Python interpreter CARRIED INSIDE Tlamatini's
    installation (``<install_dir>/python``) so pool agents NEVER depend on a
    system Python or a user-set ``PYTHON_HOME``. The carried interpreter is
    pinned to Python 3.12.10 (shipped by the installer). Only when the carried
    interpreter is somehow absent (e.g. running from source) does this fall
    back to the registry / environment ``PYTHON_HOME``.
    """
    if getattr(sys, 'frozen', False):
        _carried = os.path.join(os.path.dirname(sys.executable), 'python')
        if sys.platform.startswith('win'):
            _exe = os.path.join(_carried, 'python.exe')
        else:
            _exe = os.path.join(_carried, 'bin', 'python3')
        if os.path.isfile(_exe):
            return _carried
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env() -> dict:
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()
    
    # Reset PyInstaller's DLL search path alteration on Windows
    # If we don't do this, child Python processes will WinError 1114 when loading C extensions (like torch)
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = getattr(sys, '_MEIPASS')
        if meipass:
            path_parts = env.get('PATH', '').split(os.pathsep)
            path_parts = [p for p in path_parts if os.path.normpath(p) != os.path.normpath(meipass)]
            env['PATH'] = os.pathsep.join(path_parts)
            
    python_home = get_user_python_home()
    if not python_home:
        return env
        
    env['PYTHON_HOME'] = python_home
    scripts_dir = os.path.join(python_home, 'Scripts')
    current_path = env.get('PATH', '')
    env['PATH'] = f"{python_home};{scripts_dir};{current_path}"
    return env

def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    
    if os.path.basename(grandparent) == 'pools':
        return parent
    
    if os.path.basename(parent) == 'pools':
        return parent
        
    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")
        
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")
             
    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name: str) -> bool:
    """Check if an agent is currently running by verifying its PID file and process."""
    agent_dir = get_agent_directory(agent_name)
    pid_path = os.path.join(agent_dir, "agent.pid")

    if not os.path.exists(pid_path):
        return False

    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return False

    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return True
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_agents_to_stop(agent_names: list):
    """
    Wait until ALL specified agents have stopped running.
    Logs ERROR every 10 seconds while waiting. Never proceeds until all have stopped.
    """
    if not agent_names:
        return

    waited = 0.0
    poll_interval = 0.5

    while True:
        still_running = [name for name in agent_names if is_agent_running(name)]
        if not still_running:
            return

        if waited >= 10.0:
            logging.error(
                f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0

        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    """Start a downstream agent."""
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)

    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
        return False

    try:
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")

        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        # Write PID file for fast status checking
        try:
            pid_path = os.path.join(agent_dir, "agent.pid")
            with open(pid_path, "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"⚠️ Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


# ============================================================
#  BEST-EFFORT VISIBLE-WINDOW RESCUE  (Angela, 2026-08-05)
# ============================================================
#
# Angela's standing rule is that she must SEE what runs. Windows does not always
# allow it: when this agent is launched by the session MCP host, the console it
# creates belongs to a window station/desktop that is not the interactive one, and
# NO combination of creation flags escapes that (measured: Start-Process
# -WindowStyle Normal, and a direct Popen with CREATE_NEW_CONSOLE |
# CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB — Windower confirmed the
# window was absent both times).
#
# Her instruction: MAKE A BEST EFFORT ANYWAY. So we do, and this is the one avenue
# flags cannot reach — a window that EXISTS but was never SHOWN. If the console
# object is on a desktop we can touch, ShowWindow/SetForegroundWindow will reveal
# it. If it is not, nothing here can, and we say so plainly instead of pretending.
#
# MEASURED RESULT (2026-08-05, same session): this rescue DOES change the outcome.
#   BEFORE it, the Windower agent scanned the desktop TWICE and found NO window.
#   AFTER it, Windower FINDS the console, FOCUSES it and MAXIMIZES it
#   (`Focused 'LATEXER-RESCUE-FINAL' (hwnd=0x00280292); brought_to_front=True`).
# So the window goes from "does not exist anywhere we can reach" to "a real,
# addressable, focusable window".
#
# ✅ AND ANGELA CONFIRMED SHE SAW IT ON HER SCREEN (2026-08-05). That is the only
# oracle that actually matters for her rule, and it settles it: the rescue puts
# real pixels on the real desktop, not merely a handle in the Win32 API. (A cloud
# vision pass over the screenshot had said otherwise — it was WRONG, the same
# model having already misread that screen once. A human beat the model.)
#
# The log still says "rescue attempted … confirm with Windower" rather than
# declaring success, because it is confirmed for THIS host and cannot be promised
# for every future one. Under-claim, then verify. Windower is the oracle; this
# code never awards itself the win.
#
# TWO HARD RULES:
#   1. NEVER let this affect whether the user's script RUNS. It runs first; this
#      only tries to reveal the window afterwards, and every call is wrapped so a
#      failure is logged and swallowed. A rescue that breaks execution is worse
#      than an invisible window.
#   2. NEVER relaunch the script to get a window — that would run the user's work
#      TWICE (double writes, double tests). Reveal only.
#
# Why NEW-window detection instead of matching the PID: a console window is owned
# by conhost.exe, NOT by the cmd.exe we spawned, so GetWindowThreadProcessId
# usually reports a PID we never saw. Snapshotting console windows before the
# launch and diffing afterwards is the reliable identification.

_CONSOLE_WINDOW_CLASSES = (
    "ConsoleWindowClass",               # classic conhost
    "CASCADIA_HOSTING_WINDOW_CLASS",    # Windows Terminal
    "PseudoConsoleWindow",              # ConPTY
)

SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9


def _console_window_snapshot():
    """Every console-ish top-level window right now (visible OR hidden).

    Returns a set of HWND ints. NEVER raises — an empty set simply means
    "cannot tell", and the caller degrades to doing nothing.
    """
    handles = set()
    if os.name != 'nt':
        return handles
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _collect(hwnd, _lparam):
            try:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                if buf.value in _CONSOLE_WINDOW_CLASSES:
                    handles.add(int(hwnd))
            except Exception:
                pass
            return True

        user32.EnumWindows(enum_proc(_collect), 0)
    except Exception:
        return handles
    return handles


def _force_show_new_consoles(before, timeout_seconds=6.0):
    """BEST EFFORT: reveal any console window that appeared since *before*.

    Returns {"appeared": n, "revealed": n, "already_visible": n}. NEVER raises.
    """
    result = {"appeared": 0, "revealed": 0, "already_visible": 0,
              "still_visible": 0}
    if os.name != 'nt':
        return result
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        deadline = time.time() + max(0.5, float(timeout_seconds))
        seen = set()

        while time.time() < deadline:
            nuevos = _console_window_snapshot() - before - seen
            for hwnd in nuevos:
                seen.add(hwnd)
                result["appeared"] += 1
                try:
                    if user32.IsWindowVisible(wintypes.HWND(hwnd)):
                        result["already_visible"] += 1
                        # Still pull it forward — a window buried behind a
                        # maximized editor is, to a human, not visible.
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
                        user32.SetForegroundWindow(wintypes.HWND(hwnd))
                        continue
                    # THE CASE THIS WHOLE HELPER EXISTS FOR: the console object is
                    # real but was never shown. If it lives on a desktop we can
                    # touch, these three calls put it on screen.
                    user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWNORMAL)
                    user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOW)
                    user32.BringWindowToTop(wintypes.HWND(hwnd))
                    user32.SetForegroundWindow(wintypes.HWND(hwnd))
                    if user32.IsWindowVisible(wintypes.HWND(hwnd)):
                        result["revealed"] += 1
                except Exception:
                    continue
            if result["appeared"]:
                break
            time.sleep(0.25)

        # ⚠️ VERIFY AT THE END, and report ONLY what survives.
        #
        # The first version of this helper reported "window is visible" the moment
        # it saw a new console handle — and was WRONG: short-lived consoles from
        # our own launcher come and go, so it announced success while Windower
        # showed no such window on the desktop. Overclaiming here would reproduce
        # exactly the lie this rescue was written to remove. So: settle, then count
        # only the handles that are STILL alive and STILL visible.
        time.sleep(0.4)
        for hwnd in seen:
            try:
                if (user32.IsWindow(wintypes.HWND(hwnd))
                        and user32.IsWindowVisible(wintypes.HWND(hwnd))):
                    result["still_visible"] += 1
            except Exception:
                continue
    except Exception:
        return result
    return result


def execute_script(script_content: str, non_blocking: bool = False,
                    execute_forked_window: bool = False) -> bool:
    """
    Write the script content to a temporary file and execute it.
    Returns True on success, False on failure.

    If non_blocking=True, the script is launched as a detached process and
    the function returns immediately without waiting for completion.
    This is useful for starting long-running services like GlassFish.

    If execute_forked_window=True, the script runs in a visible console
    window so stdout/stderr are shown in real time.  This works in both
    blocking and non_blocking modes.
    """
    if not script_content or not script_content.strip():
        logging.error("❌ No script content specified to execute.")
        return False
    
    try:
        # Determine file extension and execution command based on OS
        is_windows = sys.platform.startswith('win')
        ext = '.bat' if is_windows else '.sh'
        
        # For NON-BLOCKING mode: Save script to the Tlamatini Temp directory.
        # This sits OUTSIDE the pool (so the Ender agent / flow cleanup, which
        # scan the pool directory, do NOT kill the script or its spawned
        # processes) yet still INSIDE Tlamatini (<app>/Temp), honoring the
        # "never write temp outside Tlamatini" policy. TLAMATINI_TEMP is
        # exported by the core; gettempdir() also returns it because the
        # module-load _enforce_tlamatini_temp() pinned tempfile.tempdir.
        if non_blocking:
            import tempfile
            # Use a unique filename to avoid conflicts
            temp_dir = (os.environ.get('TLAMATINI_TEMP') or '').strip() or tempfile.gettempdir()
            script_filename = f"tlamatini_nb_{os.getpid()}{ext}"
            script_path = os.path.join(temp_dir, script_filename)
            logging.info(f"📝 Non-blocking: Writing script to Tlamatini Temp: {script_path}")
        else:
            # For blocking mode: Use pool directory as before
            script_filename = f"temp_script{ext}"
            script_path = os.path.abspath(script_filename)
            logging.info(f"📝 Writing script to: {script_path}")
        
        # Write content to file
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        # Make executable (important for Linux)
        try:
            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | 0o111)
        except Exception as e:
            logging.warning(f"⚠️ Failed to set execution permissions: {e}")

        logging.info(f"🚀 Executing script... (non_blocking={non_blocking})")
        
        cmd = [script_path]
        
        # NON-BLOCKING MODE: Fire-and-forget for long-running processes
        if non_blocking:
            logging.info("🔥 Non-blocking mode: Launching script as detached process...")

            if is_windows:
                # ⚠️ VISIBILITY IS DECIDED BY THE HOST, NOT BY THESE FLAGS
                # (measured by Angela, 2026-08-05 — do not "fix" this again blindly).
                #
                # When this agent is launched by the SESSION MCP SERVER, the console
                # requested here NEVER APPEARS on the interactive desktop, even though
                # the script really runs and writes its log. Proved with Tlamatini's
                # own tools: Windower scanned the visible windows twice and the console
                # was absent both times — first with the `Start-Process -WindowStyle
                # Normal` below, then again with a direct Popen using
                # CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB.
                # Creation flags CANNOT fix it: the constraint is the window station /
                # desktop the MCP host itself lives in, which no child flag can leave.
                #
                # So: the flags below are correct and were LEFT ALONE. What changed is
                # the LOG — it used to claim "window=visible" unconditionally, which was
                # a lie whenever this ran under the MCP host, and a lie in a log is
                # worse than a missing window because it hides the problem.
                #
                # TO ACTUALLY GET A WINDOW ANGELA CAN SEE: launch from a shell that is
                # already on her desktop (`Start-Process powershell -NoExit …` with
                # dangerouslyDisableSandbox), not through this agent. Memory:
                # project_mcp_forked_window_invisible.
                #
                # Use PowerShell Start-Process which creates a TRULY independent process
                # This is the most reliable method on Windows to break free from:
                # - Windows Job Objects
                # - Console associations
                # - Parent-child process relationships
                #
                # -FilePath: The script to run
                # -WindowStyle: Normal (visible) when execute_forked_window is on,
                #               Hidden when off
                # -PassThru is NOT used so we don't wait for process object

                # Escape the path for PowerShell
                escaped_path = script_path.replace("'", "''")

                # CRITICAL: Use TEMP as working directory (not pool!)
                # This ensures the spawned process has no association with the pool
                # and won't be killed by Ender/cleanup scans
                temp_dir = os.path.dirname(script_path)  # Already in TEMP

                window_style = 'Normal' if execute_forked_window else 'Hidden'
                ps_command = (
                    f'Start-Process -FilePath "{escaped_path}" '
                    f'-WorkingDirectory "{temp_dir}" '
                    f'-WindowStyle {window_style}'
                )

                logging.info(f"   PowerShell command: {ps_command}")

                # Snapshot console windows BEFORE launching, so the rescue below can
                # tell OUR new console apart from every console already on the box.
                consoles_before = (_console_window_snapshot()
                                   if execute_forked_window else set())

                # Run PowerShell to execute Start-Process
                # PowerShell Start-Process creates a process NOT tied to this session
                process = subprocess.Popen(
                    ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_command],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=temp_dir,  # Also run PowerShell from TEMP
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # Wait for PowerShell to finish executing Start-Process
                # (PowerShell exits immediately after spawning the independent process)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logging.warning("⚠️ PowerShell took too long, continuing anyway...")

                # BEST-EFFORT RESCUE — the script is ALREADY running by now, so
                # nothing here can stop it. We only try to put its window on screen.
                if execute_forked_window:
                    try:
                        rescue = _force_show_new_consoles(consoles_before,
                                                          timeout_seconds=6.0)
                        if rescue["revealed"] and rescue["still_visible"]:
                            logging.info(
                                "   🪟 Window RESCUED: %d hidden console(s) forced "
                                "visible with ShowWindow; %d still on screen."
                                % (rescue["revealed"], rescue["still_visible"]))
                        elif rescue["still_visible"]:
                            logging.info(
                                "   🪟 %d new console window(s) are on this desktop "
                                "and were brought to the front. (This counts CONSOLES, "
                                "not titles — confirm it is YOUR window with the "
                                "Windower agent.)" % rescue["still_visible"])
                        elif rescue["appeared"]:
                            logging.warning(
                                "   🪟 A console appeared but could NOT be shown — it "
                                "is on another window station/desktop. Nothing in "
                                "this process can reach it.")
                        else:
                            logging.warning(
                                "   🪟 NO console window was created on this desktop. "
                                "The script IS running (its output still lands in the "
                                "log) but Angela cannot see it: this agent was "
                                "launched by a host whose desktop is not the "
                                "interactive one. To get a window she can watch, "
                                "launch from a shell already on her desktop.")
                    except Exception as rescue_error:      # never break the launch
                        logging.warning("   🪟 Window rescue failed harmlessly: %s"
                                        % rescue_error)

            else:
                # Unix: Use start_new_session to detach from parent
                # Also use nohup-style approach for maximum independence
                if execute_forked_window:
                    # Try to launch in a visible terminal emulator
                    terminal_cmds = [
                        ['x-terminal-emulator', '-e', script_path],
                        ['gnome-terminal', '--', script_path],
                        ['xterm', '-hold', '-e', script_path],
                    ]
                    launched = False
                    for tcmd in terminal_cmds:
                        try:
                            subprocess.Popen(
                                tcmd,
                                cwd=os.getcwd(),
                                start_new_session=True,
                                close_fds=True
                            )
                            launched = True
                            break
                        except FileNotFoundError:
                            continue
                    if not launched:
                        logging.warning("⚠️ No terminal emulator found, falling back to hidden")
                        subprocess.Popen(
                            ['nohup', script_path],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            cwd=os.getcwd(),
                            start_new_session=True,
                            close_fds=True
                        )
                else:
                    subprocess.Popen(
                        ['nohup', script_path],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        cwd=os.getcwd(),
                        start_new_session=True,
                        close_fds=True
                    )

            # Say what was REQUESTED, never what was achieved. Under the session MCP
            # host the window is requested and never shown (see the note above), and
            # the old unconditional "window=visible" turned that into a silent lie —
            # which is how it went unnoticed. Verify with the Windower agent.
            if execute_forked_window:
                window_note = ("window=visible REQUESTED + rescue attempted "
                               "(NOT guaranteed - confirm with the Windower agent)")
            else:
                window_note = "window=hidden"
            logging.info("✅ Script launched as independent process "
                         "(detached, not waiting, %s)" % window_note)
            return True
        
        # FORKED WINDOW MODE: Run in a visible console window
        if execute_forked_window:
            logging.info("🪟 Forked window mode: Launching script in new console...")
            return _execute_in_forked_window(script_path)

        # BLOCKING MODE: Wait for script to complete (original behavior)
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=os.getcwd(),
            timeout=300  # 5 minute timeout
        )
        
        # Log stdout if present
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logging.info(f"   [stdout] {line}")
        
        # Log stderr if present
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    logging.warning(f"   [stderr] {line}")
        
        # Check return code
        if result.returncode == 0:
            logging.info(f"✅ Script execution completed with exit code: {result.returncode}")
            return True
        else:
            logging.error(f"❌ Script execution failed with exit code: {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        logging.error("❌ Script execution timed out (300s limit)")
        return False
    except Exception as e:
        logging.error(f"❌ Script execution error: {e}")
        return False
    finally:
        # User requested: "The temporary file must be created... and overwriten... each time"
        # Since we overwrite on next run, we technically don't HAVE to delete it, 
        # but cleanup is usually good practice. 
        # However, the user said "overwritten... each time", implying it stays there?
        # "At execution time ... the script should be writen ... and finally execute."
        # No explicit instruction to delete it. Leaving it might be useful for debugging.
        pass


def _execute_in_forked_window(script_path: str) -> bool:
    """
    Execute a script in a new console window and wait for it to finish.
    The forked window stays open after the script completes so the user
    can read stdout and stderr.  Returns True if exit code == 0.
    """
    try:
        if sys.platform.startswith('win'):
            # Build a tiny wrapper .bat that:
            #   1. Calls the real script
            #   2. Saves %ERRORLEVEL%
            #   3. Prints a separator so the user knows it finished
            #   4. Pauses so the window stays open
            #   5. Exits with the original error level
            wrapper_path = os.path.abspath("temp_forked_wrapper.bat")

            # ⚠️ DO NOT go back to `@pause` (fixed 2026-08-08). A pool agent's
            # stdin is NOT an interactive console, so `pause` sees EOF and returns
            # INSTANTLY — the window flashed and vanished before Angela could read
            # a single line, while the log still claimed success. Measured on this
            # machine: plain `@pause` exited after 0.97s, and `@pause < CON`
            # (the usual workaround) after 2.32s — both useless. `timeout /t` is
            # no good either ("ERROR: Input redirection is not supported").
            # So the window is held open by a BOUNDED PowerShell Start-Sleep (which
            # needs no stdin) and the script's exit code is handed back through this
            # sentinel file, so the agent returns as soon as the WORK is done
            # instead of waiting out the hold.
            sentinel_path = os.path.abspath("temp_forked_exitcode.txt")
            # How long the finished window stays readable. Bounded on purpose —
            # see the wrapper below. Override with FORKED_WINDOW_HOLD_SECONDS.
            try:
                _hold = int(os.environ.get("FORKED_WINDOW_HOLD_SECONDS", "900"))
            except (TypeError, ValueError):
                _hold = 900
            _hold = max(5, min(_hold, 86400))
            try:
                if os.path.exists(sentinel_path):
                    os.remove(sentinel_path)
            except OSError:
                pass

            with open(wrapper_path, "w", encoding="utf-8") as wf:
                wf.write(f'@call "{script_path}"\n')
                wf.write('@set EC=%ERRORLEVEL%\n')
                wf.write('@echo.\n')
                wf.write('@echo ============================================\n')
                wf.write('@echo   Script finished  (exit code: %EC%)\n')
                wf.write(f'@echo   This window stays open for {_hold} seconds - or close it now.\n')
                wf.write('@echo ============================================\n')
                wf.write(f'@echo %EC%> "{sentinel_path}"\n')
                # BOUNDED hold, never an unbounded `cmd /k`. Under the session MCP
                # host the console is created on a window station Angela cannot
                # see (measured 2026-08-05), so an unbounded hold would leak an
                # INVISIBLE cmd.exe on every single run — exactly the orphan-process
                # class the three-tier reaper exists to prevent. Start-Sleep needs
                # no stdin, so unlike `pause` it actually holds.
                wf.write(f'@powershell -NoProfile -Command "$env:TLAMATINI_KEEP_CONSOLE_ALIVE=1; Start-Sleep -Seconds {_hold}"\n')
                wf.write('@exit /b %EC%\n')

            # Same best-effort rescue as the non-blocking path: snapshot the
            # consoles that exist BEFORE, so we can find and force-show ours.
            consoles_before = _console_window_snapshot()

            # `/c`, NOT `/k`: the wrapper's bounded Start-Sleep is what keeps the
            # window readable, and it TERMINATES. `/k` holds the console FOREVER,
            # which under the MCP host (where the window is invisible) silently
            # leaks one cmd.exe per run. The agent still does not block on this
            # process — it waits on the sentinel file below instead.
            process = subprocess.Popen(
                # TLAMATINI_KEEP_CONSOLE_ALIVE es una MARCA, no un argumento
                # que el wrapper lea: el orphan reaper perdona a toda consola
                # cuya LINEA DE COMANDOS la lleve (orphan_reaper.py,
                # INTERACTIVE_CONSOLE_MARKERS; la comparacion es en minusculas).
                # Sin ella el Start-Sleep acotado de abajo se ve identico a un
                # shell colgado -- cero CPU, cero I/O -- y en la window station
                # invisible el reaper tampoco ve la ventana, asi que mataria
                # justo la ventana que este codigo existe para mantener abierta.
                ['cmd.exe', '/c', wrapper_path,
                 'TLAMATINI_KEEP_CONSOLE_ALIVE'],
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

            # This path BLOCKS on the window below, so the rescue runs on a
            # daemon thread. It is pure best-effort: it can only reveal a
            # window, never affect the script that is already running.
            try:
                # Imported HERE, not at module top: this file is a pool agent whose
                # import block is guarded (ruff E402 around the TLAMATINI_TEMP pin),
                # and a rescue helper must never be able to break the module import.
                import threading as _threading

                _threading.Thread(
                    target=_force_show_new_consoles,
                    args=(consoles_before,),
                    kwargs={"timeout_seconds": 6.0},
                    daemon=True,
                ).start()
            except Exception as rescue_error:
                logging.warning("   🪟 Window rescue thread not started (%s) — the "
                                "script still runs normally." % rescue_error)
        else:
            # On Linux/macOS, try common terminal emulators
            # xterm -hold keeps the window open after the command exits
            terminal_cmds = [
                ['x-terminal-emulator', '-e'] + [script_path],
                ['gnome-terminal', '--', script_path],
                ['xterm', '-hold', '-e', script_path],
            ]
            process = None
            for tcmd in terminal_cmds:
                try:
                    process = subprocess.Popen(tcmd, cwd=os.getcwd())
                    break
                except FileNotFoundError:
                    continue
            if process is None:
                logging.warning("⚠️ No terminal emulator found, falling back to direct execution")
                process = subprocess.Popen([script_path], cwd=os.getcwd())

        # Wait for the SCRIPT to finish — NOT for the user to close the window.
        # The window is deliberately held open by `cmd /k` (see above), so
        # process.wait() here would block until the window is closed BY HAND,
        # hanging the agent. The sentinel file tells us the work is done while the
        # console stays on screen, readable, for as long as Angela wants it.
        if sys.platform.startswith('win'):
            exit_code = None
            deadline = time.time() + 300
            while time.time() < deadline:
                if os.path.exists(sentinel_path):
                    try:
                        with open(sentinel_path, 'r', encoding='utf-8',
                                  errors='replace') as sf:
                            exit_code = int((sf.read().strip() or '0'))
                    except (OSError, ValueError):
                        exit_code = 0
                    break
                if process.poll() is not None:
                    # Console was closed before the script wrote its code.
                    exit_code = process.returncode
                    break
                time.sleep(0.25)

            if exit_code is None:
                logging.error("❌ Forked window script execution timed out (300s limit)")
                return False

            try:
                os.remove(sentinel_path)
            except OSError:
                pass
        else:
            process.wait(timeout=300)
            exit_code = process.returncode

        if exit_code == 0:
            logging.info(f"✅ Script execution completed with exit code: {exit_code}")
            logging.info("   🪟 The forked window is STILL OPEN — close it when you have read it.")
            return True
        else:
            logging.error(f"❌ Script execution failed with exit code: {exit_code}")
            logging.info("   🪟 The forked window is STILL OPEN — close it when you have read it.")
            return False

    except subprocess.TimeoutExpired:
        logging.error("❌ Forked window script execution timed out (300s limit)")
        try:
            process.kill()
        except Exception:
            pass
        return False
    except Exception as e:
        logging.error(f"❌ Forked window execution error: {e}")
        return False


# PID Management
PID_FILE = "agent.pid"

def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")

def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


def main():
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    
    execution_success = False
    
    try:
        # Configuration
        # Support both 'script' (new) and 'command' (legacy fallback)
        script_content = config.get('script', config.get('command', ''))
        target_agents = config.get('target_agents', [])
        non_blocking = config.get('non_blocking', False)
        execute_forked_window = config.get('execute_forked_window', False)

        logging.info("🔥 EXECUTER AGENT STARTED (SCRIPT MODE)")
        # logging.info(f"📋 Script Content: {script_content}") # Don't log full script to avoid clutter
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info(f"⚡ Non-blocking: {non_blocking}")
        logging.info(f"🪟 Forked window: {execute_forked_window}")
        logging.info("=" * 60)

        # Execute the script
        execution_success = execute_script(
            script_content, non_blocking=non_blocking,
            execute_forked_window=execute_forked_window
        )
        
        # Log the required status message
        if execution_success:
            logging.info("EXECUTION SUCCESS")
        else:
            logging.error("EXECUTION FAILED")
        
        logging.info("=" * 60)
        
        # Trigger downstream agents REGARDLESS of success/failure
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                logging.info(f"   ► Triggering: {target}")
                if start_agent(target):
                    total_triggered += 1
            logging.info(f"✨ Triggered {total_triggered}/{len(target_agents)} agents.")
        else:
            logging.info("ℹ️ No downstream agents configured.")
        
        logging.info(f"🏁 Executer agent finished. Result: {'SUCCESS' if execution_success else 'FAILED'}")
        
    except Exception as e:
        logging.error(f"❌ Executer agent error: {e}")
        logging.error("EXECUTION FAILED")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
    
    sys.exit(0 if execution_success else 1)


if __name__ == "__main__":
    main()
