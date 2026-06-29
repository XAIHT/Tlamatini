# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Windower Agent - Application window manager
# Action: Triggered by upstream -> locate a window by title and run a window
#         lifecycle op (focus / move / resize / min / max / restore / close /
#         topmost / arrange) OR enumerate all open windows -> emit
#         INI_SECTION_WINDOWER -> trigger downstream.
#
# Windower is the WINDOW MANAGER peer of Mouser (pointer) and Keyboarder (keys):
# it acts on the WINDOW itself, never on controls inside it. It is implemented
# self-contained with the Win32 API (pywin32 win32gui / win32con / win32process
# + ctypes), porting the window-management subset of Microsoft's Windows-MCP
# inline — the agent pool runs as standalone subprocesses with no path back into
# the Django app, so (like ACPXer) it must NOT import from agent.* and instead
# reproduces the needed primitives directly.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
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

# --- Win32 window-management backend ----------------------------------
# Primary backend is pywin32 (win32gui/win32con/win32process). ctypes is used
# for the few user32/kernel32 calls pywin32 does not surface cleanly
# (GetCurrentThreadId, AllowSetForegroundWindow, SystemParametersInfoW). All
# imports are guarded so a non-Windows host or a stripped frozen build degrades
# gracefully into a clear error section instead of crashing the chain.
try:
    import win32gui
    import win32con
    import win32process
    _WIN32_OK = True
    _WIN32_ERR = ""
except Exception as _imp_err:  # pragma: no cover - platform dependent
    win32gui = None
    win32con = None
    win32process = None
    _WIN32_OK = False
    _WIN32_ERR = f"{type(_imp_err).__name__}: {_imp_err}"

try:
    import ctypes
    import ctypes.wintypes
    _CTYPES_OK = True
except Exception:  # pragma: no cover - platform dependent
    ctypes = None
    _CTYPES_OK = False

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


# ========================================
# HELPER FUNCTIONS (from shoter.py / mouser.py boilerplate — copy verbatim)
# ========================================

def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

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
    env = os.environ.copy()

    if sys.platform.startswith('win'):
        try:
            import ctypes as _ct
            if hasattr(_ct.windll.kernel32, 'SetDllDirectoryW'):
                _ct.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

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
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)

    if not os.path.exists(script_path):
        logging.error(f"Agent script not found: {script_path}")
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

        try:
            pid_path = os.path.join(agent_dir, "agent.pid")
            with open(pid_path, "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ========================================
# WIN32 WINDOW-MANAGEMENT PRIMITIVES
# (ported inline from Microsoft Windows-MCP's desktop service; no agent.* import)
# ========================================

# ShowWindow command codes (winuser.h) — defined locally so we never hard-depend
# on win32con being importable while win32gui is.
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_MINIMIZE = 6
SW_RESTORE = 9

# SetWindowPos hWndInsertAfter values + flags
HWND_TOP = 0
HWND_BOTTOM = 1
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

WM_CLOSE = 0x0010
SPI_GETWORKAREA = 0x0030


def _is_maximized(hwnd) -> bool:
    """Return True if the window is maximized.

    Primary path is ``win32gui.GetWindowPlacement(hwnd)[1]`` (the ``showCmd``
    field == ``SW_SHOWMAXIMIZED`` (3)). GetWindowPlacement is present in EVERY
    pywin32 build, whereas ``win32gui.IsZoomed`` is NOT exported by some builds
    (e.g. pywin32 311), so IsZoomed is only consulted, behind a getattr guard,
    as a fallback — and the last-resort raw ``user32.IsZoomed`` ctypes call is
    HWND-typed so a 64-bit window handle is never truncated to 32 bits.
    """
    try:
        return win32gui.GetWindowPlacement(hwnd)[1] == SW_MAXIMIZE  # SW_SHOWMAXIMIZED == 3
    except Exception:
        pass
    is_zoomed = getattr(win32gui, "IsZoomed", None)
    if is_zoomed is not None:
        try:
            return bool(is_zoomed(hwnd))
        except Exception:
            pass
    if _CTYPES_OK:
        try:
            user32 = ctypes.windll.user32
            user32.IsZoomed.argtypes = [ctypes.wintypes.HWND]
            user32.IsZoomed.restype = ctypes.c_int
            return bool(user32.IsZoomed(ctypes.wintypes.HWND(int(hwnd))))
        except Exception:
            pass
    return False


def _window_state(hwnd) -> str:
    """Map a window handle to one of minimized | maximized | normal | hidden."""
    try:
        if win32gui.IsIconic(hwnd):
            return "minimized"
        if _is_maximized(hwnd):
            return "maximized"
        if win32gui.IsWindowVisible(hwnd):
            return "normal"
        return "hidden"
    except Exception:
        return "unknown"


def enum_windows() -> list:
    """Enumerate every visible, titled, non-zero-size top-level window.

    Returns a list of dicts (Z-order as reported by EnumWindows):
        {hwnd, title, left, top, width, height, state, pid}
    """
    results = []

    def _callback(hwnd, _lparam):
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w = right - left
            h = bottom - top
            if w <= 0 or h <= 0:
                return True
            pid = 0
            try:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = 0
            results.append({
                "hwnd": int(hwnd),
                "title": title,
                "left": int(left),
                "top": int(top),
                "width": int(w),
                "height": int(h),
                "state": _window_state(hwnd),
                "pid": int(pid),
            })
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_callback, None)
    return results


def match_windows(windows: list, title: str, match_mode: str) -> list:
    """Filter `windows` by `title` using substring | exact | regex matching."""
    title = (title or "").strip()
    if not title:
        return list(windows)
    mode = (match_mode or "substring").strip().lower()
    title_l = title.lower()
    matched = []
    if mode == "regex":
        try:
            pattern = re.compile(title, re.IGNORECASE)
        except re.error as e:
            logging.warning(f"Invalid regex match pattern {title!r}: {e}. Falling back to substring.")
            mode = "substring"
            pattern = None
        if pattern is not None:
            return [w for w in windows if pattern.search(w["title"])]
    if mode == "exact":
        matched = [w for w in windows if w["title"].lower() == title_l]
    else:  # substring (default / fallback)
        matched = [w for w in windows if title_l in w["title"].lower()]
    return matched


def _current_thread_id() -> int:
    if _CTYPES_OK:
        try:
            return int(ctypes.windll.kernel32.GetCurrentThreadId())
        except Exception:
            return 0
    return 0


def bring_to_front(hwnd) -> bool:
    """Reliably bring `hwnd` to the foreground (restore if minimized first).

    Ports Windows-MCP's AttachThreadInput focus-transfer dance: a plain
    SetForegroundWindow frequently fails when the caller is not the active
    process, so we temporarily attach our thread input to both the current
    foreground window's thread AND the target's thread, which lets the focus
    change succeed. Every step is best-effort — an elevated target may refuse
    AttachThreadInput, and we still try the direct path.
    """
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, SW_RESTORE)

        foreground = win32gui.GetForegroundWindow()
        if not foreground or not win32gui.IsWindow(foreground):
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            win32gui.BringWindowToTop(hwnd)
            return True

        fg_thread, _ = win32process.GetWindowThreadProcessId(foreground)
        tgt_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        cur_tid = _current_thread_id()

        if not fg_thread or not tgt_thread or fg_thread == tgt_thread:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            win32gui.BringWindowToTop(hwnd)
            return True

        if _CTYPES_OK:
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

        attached = []
        try:
            for thread in (fg_thread, tgt_thread):
                if thread and thread != cur_tid:
                    try:
                        win32process.AttachThreadInput(cur_tid, thread, True)
                        attached.append(thread)
                    except Exception as e:
                        logging.debug(f"AttachThreadInput failed for thread {thread} (likely elevated): {e}")
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetWindowPos(
                hwnd, HWND_TOP, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
        finally:
            for thread in reversed(attached):
                try:
                    win32process.AttachThreadInput(cur_tid, thread, False)
                except Exception:
                    pass
        return True
    except Exception as e:
        logging.warning(f"bring_to_front failed: {e}")
        return False


def get_work_area() -> tuple:
    """Return the primary monitor's work area (desktop minus taskbar) as
    (left, top, right, bottom). Falls back to full-screen metrics."""
    if _CTYPES_OK:
        try:
            rect = ctypes.wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
        try:
            cx = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            cy = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            return (0, 0, int(cx), int(cy))
        except Exception:
            pass
    return (0, 0, 1920, 1080)


def compute_arrange_rect(arrange_mode: str, width: int, height: int) -> tuple:
    """Compute (x, y, w, h) for an arrange_mode within the work area."""
    wl, wt, wr, wb = get_work_area()
    work_w = max(wr - wl, 1)
    work_h = max(wb - wt, 1)
    half_w = work_w // 2
    half_h = work_h // 2
    mode = (arrange_mode or "left").strip().lower().replace("_", "-")

    table = {
        "left": (wl, wt, half_w, work_h),
        "right": (wl + half_w, wt, work_w - half_w, work_h),
        "top": (wl, wt, work_w, half_h),
        "bottom": (wl, wt + half_h, work_w, work_h - half_h),
        "top-left": (wl, wt, half_w, half_h),
        "top-right": (wl + half_w, wt, work_w - half_w, half_h),
        "bottom-left": (wl, wt + half_h, half_w, work_h - half_h),
        "bottom-right": (wl + half_w, wt + half_h, work_w - half_w, work_h - half_h),
        "full": (wl, wt, work_w, work_h),
    }
    if mode == "center":
        cw = min(int(width) if width else half_w, work_w)
        ch = min(int(height) if height else half_h, work_h)
        cx = wl + (work_w - cw) // 2
        cy = wt + (work_h - ch) // 2
        return (cx, cy, cw, ch)
    return table.get(mode, table["left"])


def set_window_pos(hwnd, x=None, y=None, w=None, h=None, activate=True) -> None:
    """Move and/or resize a window via SetWindowPos. None coordinates are kept."""
    flags = SWP_NOZORDER
    if not activate:
        flags |= SWP_NOACTIVATE
    cur_left, cur_top, cur_right, cur_bottom = win32gui.GetWindowRect(hwnd)
    if x is None or y is None:
        flags |= SWP_NOMOVE
        nx, ny = 0, 0
    else:
        nx, ny = int(x), int(y)
    if w is None or h is None:
        flags |= SWP_NOSIZE
        nw, nh = 0, 0
    else:
        nw, nh = int(w), int(h)
    win32gui.SetWindowPos(hwnd, HWND_TOP, nx, ny, nw, nh, flags)


def set_topmost(hwnd, topmost: bool) -> None:
    insert_after = HWND_TOPMOST if topmost else HWND_NOTOPMOST
    win32gui.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)


def close_window(hwnd) -> None:
    """Politely request the window to close (same as the X button)."""
    win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)


# ========================================
# STRUCTURED OUTPUT (Parametrizer / KV-promotion contract)
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_WINDOWER<<< block atomically (single logging.info call).

    Mirrors the Mouser / Shoter / ACPXer / Parametrizer-source convention so this
    agent's structured output is consumable by the Multi-Turn LLM (via the wrapped
    chat-agent run-result KV promotion) AND the Parametrizer's canvas pipeline
    (registered in agent_contracts._PARAMETRIZER_OUTPUT_FIELDS and
    parametrizer.SECTION_AGENT_TYPES). The KV header field names below MUST stay
    aligned with that registration.
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_WINDOWER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_WINDOWER")


# ========================================
# DISPATCH
# ========================================

def dispatch(config: dict) -> dict:
    """Run the configured window operation. Returns the outcome dict used to
    populate the INI_SECTION_WINDOWER header and decide success/failure."""
    action = str(config.get('action', 'focus') or 'focus').strip().lower()
    window_title = str(config.get('window_title', '') or '')
    match_mode = str(config.get('match_mode', 'substring') or 'substring')
    try:
        match_index = int(config.get('match_index', 0) or 0)
    except (TypeError, ValueError):
        match_index = 0
    activate_after = bool(config.get('activate_after', True))
    fail_if_absent = bool(config.get('fail_if_absent', False))

    outcome = {
        "action": action,
        "window_title": window_title,
        "matched": "false",
        "match_count": 0,
        "state": "",
        "left": "",
        "top": "",
        "width": "",
        "height": "",
    }

    if not _WIN32_OK:
        outcome["state"] = "win32_unavailable"
        body = (
            "Windower requires the Win32 API (pywin32) which failed to import on "
            f"this host: {_WIN32_ERR or 'unknown import error'}. Window management "
            "is a Windows-only capability."
        )
        return {"outcome": outcome, "body": body, "ok": False, "windows": []}

    windows = enum_windows()

    # action="list" — enumerate (optionally filtered) and return.
    if action == "list":
        listed = match_windows(windows, window_title, match_mode) if window_title else windows
        outcome["matched"] = "true" if listed else "false"
        outcome["match_count"] = len(listed)
        lines = [
            f"[{i}] {w['title']!r} | state={w['state']} | "
            f"pos=({w['left']},{w['top']}) size={w['width']}x{w['height']} | "
            f"hwnd=0x{w['hwnd']:08X} pid={w['pid']}"
            for i, w in enumerate(listed)
        ]
        body = "\n".join(lines) if lines else "No visible windows matched."
        if listed:
            top = listed[0]
            outcome.update({
                "state": top["state"], "left": top["left"], "top": top["top"],
                "width": top["width"], "height": top["height"],
            })
        return {"outcome": outcome, "body": body, "ok": True, "windows": listed}

    # All other actions require a target window.
    if not window_title:
        body = f"action={action!r} requires a non-empty window_title."
        outcome["state"] = "no_window_title"
        return {"outcome": outcome, "body": body, "ok": not fail_if_absent, "windows": []}

    matched = match_windows(windows, window_title, match_mode)
    outcome["match_count"] = len(matched)
    if not matched:
        body = (
            f"No window matched title={window_title!r} (match_mode={match_mode}). "
            f"{len(windows)} visible window(s) scanned."
        )
        outcome["state"] = "no_match"
        logging.warning(body)
        return {"outcome": outcome, "body": body, "ok": not fail_if_absent, "windows": []}

    if match_index < 0 or match_index >= len(matched):
        logging.warning(
            f"match_index={match_index} out of range for {len(matched)} match(es); using 0."
        )
        match_index = 0
    win = matched[match_index]
    hwnd = win["hwnd"]
    outcome["matched"] = "true"
    outcome["window_title"] = win["title"]

    pos_x = config.get('pos_x', 0)
    pos_y = config.get('pos_y', 0)
    width = config.get('width', 0)
    height = config.get('height', 0)
    arrange_mode = config.get('arrange_mode', 'left')

    body = ""
    try:
        if action == "focus":
            ok = bring_to_front(hwnd)
            body = f"Focused {win['title']!r} (hwnd=0x{hwnd:08X}); brought_to_front={ok}."
        elif action == "minimize":
            win32gui.ShowWindow(hwnd, SW_MINIMIZE)
            body = f"Minimized {win['title']!r}."
        elif action == "maximize":
            win32gui.ShowWindow(hwnd, SW_MAXIMIZE)
            if activate_after:
                bring_to_front(hwnd)
            body = f"Maximized {win['title']!r}."
        elif action == "restore":
            win32gui.ShowWindow(hwnd, SW_RESTORE)
            if activate_after:
                bring_to_front(hwnd)
            body = f"Restored {win['title']!r} to normal size."
        elif action == "move":
            set_window_pos(hwnd, x=pos_x, y=pos_y, activate=activate_after)
            body = f"Moved {win['title']!r} to ({pos_x}, {pos_y})."
        elif action == "resize":
            set_window_pos(hwnd, w=width, h=height, activate=activate_after)
            body = f"Resized {win['title']!r} to {width}x{height}."
        elif action == "move_resize":
            win32gui.ShowWindow(hwnd, SW_RESTORE)  # cannot move/resize a maximized window
            set_window_pos(hwnd, x=pos_x, y=pos_y, w=width, h=height, activate=activate_after)
            body = f"Moved+resized {win['title']!r} to ({pos_x},{pos_y}) {width}x{height}."
        elif action == "close":
            close_window(hwnd)
            body = f"Sent close (WM_CLOSE) to {win['title']!r}."
        elif action == "topmost":
            set_topmost(hwnd, True)
            body = f"Pinned {win['title']!r} always-on-top."
        elif action == "untopmost":
            set_topmost(hwnd, False)
            body = f"Cleared always-on-top on {win['title']!r}."
        elif action == "arrange":
            win32gui.ShowWindow(hwnd, SW_RESTORE)
            ax, ay, aw, ah = compute_arrange_rect(arrange_mode, width, height)
            set_window_pos(hwnd, x=ax, y=ay, w=aw, h=ah, activate=activate_after)
            body = f"Arranged {win['title']!r} as {arrange_mode!r} → ({ax},{ay}) {aw}x{ah}."
        else:
            outcome["state"] = "unknown_action"
            body = f"Unknown action: {action!r}."
            return {"outcome": outcome, "body": body, "ok": False, "windows": matched}

        # Re-read the live geometry/state after the op for the section header.
        try:
            gl, gt, gr, gb = win32gui.GetWindowRect(hwnd)
            outcome.update({
                "left": int(gl), "top": int(gt),
                "width": int(gr - gl), "height": int(gb - gt),
                "state": _window_state(hwnd),
            })
        except Exception:
            # close may have already destroyed the window — keep the pre-op values.
            outcome["state"] = win["state"]
            outcome.update({"left": win["left"], "top": win["top"],
                            "width": win["width"], "height": win["height"]})
        logging.info(body)
        return {"outcome": outcome, "body": body, "ok": True, "windows": matched}
    except Exception as e:
        body = f"action={action!r} on {win['title']!r} failed: {e}"
        logging.warning(body)
        outcome["state"] = "error"
        return {"outcome": outcome, "body": body, "ok": False, "windows": matched}


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', [])
        action = str(config.get('action', 'focus') or 'focus').strip().lower()

        logging.info("🪟 WINDOWER AGENT STARTED")
        logging.info(f"Action: {action}")
        logging.info(f"Window title: {config.get('window_title', '')!r}")
        logging.info(f"Targets: {target_agents}")

        result = dispatch(config)
        outcome = result["outcome"]
        body = result["body"] or "Windower run completed."

        # Emit the structured-output block atomically. Downstream Parametrizer +
        # the wrapped tool's KV promotion both rely on this block being intact.
        _emit_section(outcome, body)

        # Hard-fail path: when fail_if_absent is set and the op did not succeed,
        # exit non-zero so an upstream gate / Forker can branch on the failure —
        # but still trigger target_agents below first so the chain is not stranded.
        hard_fail = (not result["ok"]) and bool(config.get('fail_if_absent', False))

        # Trigger downstream agents (Windower IS an active agent — it starts others).
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Windower agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(1 if (locals().get('hard_fail')) else 0)


if __name__ == "__main__":
    main()
