# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Mouser Agent - Mouse pointer movement agent
# Action: Triggered by upstream -> Move mouse (random or localized) -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import random
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

try:
    import pyautogui
    pyautogui.FAILSAFE = True
except ImportError:
    pyautogui = None

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
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
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


def move_mouse_random(total_time: float):
    """Move the mouse randomly for the specified duration in seconds."""
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot move mouse.")
        return

    logging.info(f"Moving mouse randomly for {total_time} seconds...")
    start_time = time.time()

    while (time.time() - start_time) < total_time:
        screen_width, screen_height = pyautogui.size()
        target_x = random.randint(100, screen_width - 100)
        target_y = random.randint(100, screen_height - 100)
        duration = random.uniform(0.5, 2.0)

        remaining = total_time - (time.time() - start_time)
        if remaining <= 0:
            break
        duration = min(duration, remaining)

        try:
            pyautogui.moveTo(
                target_x,
                target_y,
                duration=duration,
                tween=pyautogui.easeInOutQuad
            )
            logging.info(f"Moved mouse to ({target_x}, {target_y})")
        except pyautogui.FailSafeException:
            logging.warning(f"Fail-safe triggered moving to ({target_x}, {target_y}), skipping this movement.")
            continue
        except Exception as e:
            logging.warning(f"Mouse movement to ({target_x}, {target_y}) failed: {e}, skipping.")
            continue

        remaining = total_time - (time.time() - start_time)
        if remaining <= 0:
            break
        sleep_time = min(random.uniform(1.0, 3.0), remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)

    logging.info("Random mouse movement completed.")


def normalize_button_click(button_click: str) -> str:
    normalized = str(button_click or 'none').strip().lower().replace('_', '-')
    aliases = {
        '': 'none',
        'double': 'double-left',
        'doubleclick': 'double-left',
        'double-click': 'double-left',
        'left-double': 'double-left',
        'right-double': 'double-right',
        'middle-double': 'double-middle',
    }
    normalized = aliases.get(normalized, normalized)

    supported = {
        'none',
        'left',
        'right',
        'middle',
        'double-left',
        'double-right',
        'double-middle',
    }
    return normalized if normalized in supported else 'none'


def _drag_button_for_click(normalized_click: str) -> str:
    """Return the pyautogui button name to hold during a drag.

    ``none`` defaults to ``left`` (the only sensible drag default), and the
    ``double-*`` variants collapse to their single-click counterparts because
    a held-down "double click" is not a real interaction.
    """
    if normalized_click in ('none', 'left', 'double-left'):
        return 'left'
    if normalized_click in ('right', 'double-right'):
        return 'right'
    if normalized_click in ('middle', 'double-middle'):
        return 'middle'
    return 'left'


def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_MOUSER<<< block atomically (single logging.info call).

    Mirrors the Shoter / ACPXer / Parametrizer-source convention so this
    agent's structured output is consumable by the Multi-Turn LLM (via the
    wrapped chat-agent run-result KV promotion) AND the Parametrizer's
    canvas pipeline (registered in views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS
    and parametrizer.SECTION_AGENT_TYPES).
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_MOUSER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_MOUSER")


def issue_click_after_reaching_target(end_posx: int, end_posy: int, button_click: str):
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot issue click.")
        return

    normalized_click = normalize_button_click(button_click)
    if normalized_click == 'none':
        logging.info("No button_click configured. Skipping click at final position.")
        return

    current_x, current_y = pyautogui.position()
    tolerance_pixels = 2
    if abs(current_x - end_posx) > tolerance_pixels or abs(current_y - end_posy) > tolerance_pixels:
        logging.warning(
            f"Final position not effectively reached. Expected ({end_posx}, {end_posy}), "
            f"current position is ({current_x}, {current_y}). Skipping configured click '{normalized_click}'."
        )
        return

    try:
        if normalized_click.startswith('double-'):
            button = normalized_click.split('-', 1)[1]
            pyautogui.doubleClick(button=button)
            logging.info(f"Issued configured double {button} click at ({current_x}, {current_y}).")
        else:
            pyautogui.click(button=normalized_click)
            logging.info(f"Issued configured {normalized_click} click at ({current_x}, {current_y}).")
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during configured click, skipping click.")
    except Exception as e:
        logging.warning(f"Configured click '{normalized_click}' failed: {e}")


def move_mouse_localized(ini_posx: int, ini_posy: int, end_posx: int, end_posy: int,
                         use_actual_position: bool, button_click: str) -> bool:
    """Move the mouse from an initial position to a final position. Returns
    True if the configured click was issued at the destination."""
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot move mouse.")
        return False

    try:
        if not use_actual_position:
            logging.info(f"Moving mouse to initial position ({ini_posx}, {ini_posy})...")
            pyautogui.moveTo(ini_posx, ini_posy, duration=0.5, tween=pyautogui.easeInOutQuad)
        else:
            current_x, current_y = pyautogui.position()
            logging.info(f"Using actual mouse position ({current_x}, {current_y}) as start.")

        duration = random.uniform(0.8, 2.0)
        logging.info(f"Moving mouse to final position ({end_posx}, {end_posy})...")
        pyautogui.moveTo(
            end_posx,
            end_posy,
            duration=duration,
            tween=pyautogui.easeInOutQuad
        )
        logging.info(f"Mouse moved to ({end_posx}, {end_posy}).")
        issue_click_after_reaching_target(end_posx, end_posy, button_click)
        return normalize_button_click(button_click) != 'none'
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during localized movement, skipping movement.")
        return False
    except Exception as e:
        logging.warning(f"Localized mouse movement error: {e}, skipping movement.")
        return False


def click_at_current_position(button_click: str) -> tuple:
    """Issue a click at wherever the pointer currently is. Returns (x, y, clicked)."""
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot click.")
        return (0, 0, False)
    current_x, current_y = pyautogui.position()
    issue_click_after_reaching_target(current_x, current_y, button_click)
    return (current_x, current_y, normalize_button_click(button_click) != 'none')


def drag_mouse(ini_posx: int, ini_posy: int, end_posx: int, end_posy: int,
               use_actual_position: bool, button_click: str) -> bool:
    """Drag from a start point to an end point with `button_click` held down.

    A drag with ``button_click='none'`` defaults to a left-button drag — the only
    sensible behaviour, since a "drag without holding any button" is just a move.
    """
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot drag.")
        return False

    normalized_click = normalize_button_click(button_click)
    drag_button = _drag_button_for_click(normalized_click)

    try:
        if not use_actual_position:
            logging.info(f"Drag start: moving to ({ini_posx}, {ini_posy})...")
            pyautogui.moveTo(ini_posx, ini_posy, duration=0.4, tween=pyautogui.easeInOutQuad)
        else:
            cx, cy = pyautogui.position()
            logging.info(f"Drag start: using current position ({cx}, {cy}).")

        duration = random.uniform(0.8, 1.8)
        logging.info(f"Dragging with button={drag_button!r} to ({end_posx}, {end_posy}) over {duration:.2f}s...")
        pyautogui.dragTo(
            end_posx,
            end_posy,
            duration=duration,
            button=drag_button,
            tween=pyautogui.easeInOutQuad,
        )
        logging.info(f"Drag completed at ({end_posx}, {end_posy}).")
        return True
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during drag, skipping.")
        return False
    except Exception as e:
        logging.warning(f"Drag error: {e}, skipping.")
        return False


def scroll_at_current(scroll_amount: int) -> tuple:
    """Scroll the wheel `scroll_amount` clicks at the current pointer position."""
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot scroll.")
        return (0, 0, False)
    try:
        x, y = pyautogui.position()
        clicks = int(scroll_amount)
        if clicks == 0:
            logging.warning("scroll_amount=0; nothing to scroll.")
            return (x, y, False)
        logging.info(f"Scrolling {clicks} click(s) at ({x}, {y})...")
        pyautogui.scroll(clicks)
        logging.info("Scroll completed.")
        return (x, y, True)
    except Exception as e:
        logging.warning(f"Scroll error: {e}, skipping.")
        return (0, 0, False)


def _resolve_window_anchor(win, anchor: str) -> tuple:
    """Compute (x, y) inside `win` for the requested anchor.

    Falls back to the window center when the anchor name is unknown so a typo
    never breaks the click — just lands somewhere safe.
    """
    anchor = (anchor or 'center').strip().lower()
    left, top, width, height = win.left, win.top, win.width, win.height
    cx = left + max(width // 2, 1)
    cy = top + max(height // 2, 1)
    if anchor == 'topleft':
        return (left + 8, top + 8)
    if anchor == 'topright':
        return (left + width - 8, top + 8)
    if anchor == 'bottomleft':
        return (left + 8, top + height - 8)
    if anchor == 'bottomright':
        return (left + width - 8, top + height - 8)
    if anchor == 'titlebar':
        return (cx, top + 12)
    return (cx, cy)


def click_at_window(window_title: str, anchor: str, button_click: str) -> tuple:
    """Find a window by title (substring match), focus it, click the anchor.

    Returns (x, y, clicked, located_via). On no match returns (0, 0, False, "no_match").
    Designed as the canonical "focus this window before typing" primitive — bypasses
    the Shoter→Image-Interpreter→coords dance entirely for a known window title.
    """
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot click_at_window.")
        return (0, 0, False, "pyautogui_missing")
    title = (window_title or '').strip()
    if not title:
        logging.error("window_title is empty for movement_type='click_at_window'.")
        return (0, 0, False, "no_window_title")
    try:
        get_windows = getattr(pyautogui, 'getWindowsWithTitle', None)
        if get_windows is None:
            logging.error("pyautogui.getWindowsWithTitle is not available on this platform.")
            return (0, 0, False, "platform_unsupported")
        candidates = get_windows(title) or []
        candidates = [w for w in candidates if getattr(w, 'width', 0) > 0 and getattr(w, 'height', 0) > 0]
        if not candidates:
            logging.warning(f"No window matched title={title!r}.")
            return (0, 0, False, "no_match")
        win = candidates[0]
        try:
            if hasattr(win, 'activate'):
                win.activate()
        except Exception as activate_err:
            logging.debug(f"Window activate failed (non-fatal): {activate_err}")
        target_x, target_y = _resolve_window_anchor(win, anchor)
        logging.info(
            f"Window match: title={getattr(win, 'title', '?')!r} "
            f"rect=({win.left},{win.top},{win.width},{win.height}); anchor={anchor!r} "
            f"→ click at ({target_x}, {target_y})."
        )
        duration = random.uniform(0.4, 1.0)
        pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.easeInOutQuad)
        issue_click_after_reaching_target(target_x, target_y, button_click)
        clicked = normalize_button_click(button_click) != 'none'
        return (target_x, target_y, clicked, "window_title")
    except Exception as e:
        logging.warning(f"click_at_window error: {e}")
        return (0, 0, False, f"error:{e}")


def click_at_located_image(image_path: str, confidence: float, button_click: str) -> tuple:
    """Locate a reference image on screen and click its center.

    Returns (x, y, clicked, located_via). On no match returns (0, 0, False, "no_match").
    Uses ``pyautogui.locateCenterOnScreen`` which falls back to opencv-python (cv2)
    when ``confidence`` is supplied — required for antialiased UI icons / DPI scaling.
    """
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot click_at_located_image.")
        return (0, 0, False, "pyautogui_missing")
    if not image_path or not os.path.isfile(image_path):
        logging.error(f"locate_image_path is not a valid file: {image_path!r}")
        return (0, 0, False, "no_image_file")
    try:
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.8
        conf = max(0.5, min(1.0, conf))
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=conf)
        except TypeError:
            # Older pyautogui without confidence support — fall back to exact match.
            location = pyautogui.locateCenterOnScreen(image_path)
        if location is None:
            logging.warning(f"Reference image not found on screen: {image_path!r} (confidence={conf}).")
            return (0, 0, False, "no_match")
        target_x, target_y = int(location[0]), int(location[1])
        logging.info(f"Located reference image at ({target_x}, {target_y}); clicking.")
        duration = random.uniform(0.4, 1.0)
        pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.easeInOutQuad)
        issue_click_after_reaching_target(target_x, target_y, button_click)
        clicked = normalize_button_click(button_click) != 'none'
        return (target_x, target_y, clicked, "locate_image")
    except Exception as e:
        logging.warning(f"click_at_located_image error: {e}")
        return (0, 0, False, f"error:{e}")


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', [])
        movement_type = str(config.get('movement_type', 'random') or 'random').strip().lower()
        button_click = config.get('button_click', 'none')
        normalized_click = normalize_button_click(button_click)

        logging.info("MOUSER AGENT STARTED")
        logging.info(f"Movement type: {movement_type}")
        logging.info(f"Configured button click: {normalized_click}")
        logging.info(f"Targets: {target_agents}")

        # Outcome fields populated by whichever branch runs — drives the
        # INI_SECTION_MOUSER block emitted at the end.
        end_x = 0
        end_y = 0
        clicked = False
        located_via = "manual"
        outcome_body = ""

        if movement_type == 'random':
            total_time = config.get('total_time', 30)
            logging.info(f"Total time: {total_time}s")
            if normalized_click != 'none':
                logging.info("button_click is ignored when movement_type is random.")
            try:
                move_mouse_random(float(total_time))
                if pyautogui is not None:
                    end_x, end_y = pyautogui.position()
                located_via = "random"
                outcome_body = f"Random wander completed for {total_time}s; final cursor at ({end_x}, {end_y})."
            except Exception as e:
                logging.warning(f"Random mouse movement failed: {e}")
                outcome_body = f"Random wander failed: {e}"

        elif movement_type == 'localized':
            use_actual_position = config.get('actual_position', True)
            ini_posx = config.get('ini_posx', 0)
            ini_posy = config.get('ini_posy', 0)
            end_posx = int(config.get('end_posx', 500))
            end_posy = int(config.get('end_posy', 500))

            logging.info(f"Actual position: {use_actual_position}")
            if not use_actual_position:
                logging.info(f"Initial position: ({ini_posx}, {ini_posy})")
            logging.info(f"Final position: ({end_posx}, {end_posy})")
            logging.info(f"Localized button_click: {normalized_click}")

            try:
                clicked = move_mouse_localized(
                    int(ini_posx), int(ini_posy),
                    end_posx, end_posy,
                    bool(use_actual_position),
                    button_click
                )
                end_x, end_y = end_posx, end_posy
                located_via = "manual"
                outcome_body = (
                    f"Moved to ({end_x}, {end_y}); click={normalized_click}; "
                    f"clicked={clicked}."
                )
            except Exception as e:
                logging.warning(f"Localized mouse movement failed: {e}")
                outcome_body = f"Localized movement failed: {e}"

        elif movement_type == 'click':
            try:
                end_x, end_y, clicked = click_at_current_position(button_click)
                located_via = "current_position"
                outcome_body = (
                    f"Clicked at current position ({end_x}, {end_y}); "
                    f"click={normalized_click}; clicked={clicked}."
                )
            except Exception as e:
                logging.warning(f"Click at current position failed: {e}")
                outcome_body = f"Click failed: {e}"

        elif movement_type == 'drag':
            use_actual_position = config.get('actual_position', True)
            ini_posx = config.get('ini_posx', 0)
            ini_posy = config.get('ini_posy', 0)
            end_posx = int(config.get('end_posx', 500))
            end_posy = int(config.get('end_posy', 500))
            try:
                ok = drag_mouse(
                    int(ini_posx), int(ini_posy),
                    end_posx, end_posy,
                    bool(use_actual_position),
                    button_click
                )
                end_x, end_y = end_posx, end_posy
                clicked = ok  # drag IS a click-and-hold-and-release operation
                located_via = "manual"
                outcome_body = (
                    f"Drag from ({ini_posx},{ini_posy}) → ({end_x},{end_y}) "
                    f"with button={_drag_button_for_click(normalized_click)}; ok={ok}."
                )
            except Exception as e:
                logging.warning(f"Drag failed: {e}")
                outcome_body = f"Drag failed: {e}"

        elif movement_type == 'scroll':
            scroll_amount = int(config.get('scroll_amount', 0) or 0)
            end_x, end_y, ok = scroll_at_current(scroll_amount)
            located_via = "current_position"
            outcome_body = f"Scrolled {scroll_amount} click(s) at ({end_x}, {end_y}); ok={ok}."

        elif movement_type == 'click_at_window':
            window_title = config.get('window_title', '')
            window_anchor = config.get('window_anchor', 'center')
            end_x, end_y, clicked, located_via = click_at_window(
                window_title, window_anchor, button_click
            )
            outcome_body = (
                f"click_at_window(title={window_title!r}, anchor={window_anchor!r}) "
                f"→ ({end_x}, {end_y}); located_via={located_via}; clicked={clicked}."
            )

        elif movement_type == 'locate_image':
            locate_image_path = config.get('locate_image_path', '')
            locate_confidence = config.get('locate_confidence', 0.8)
            end_x, end_y, clicked, located_via = click_at_located_image(
                locate_image_path, locate_confidence, button_click
            )
            outcome_body = (
                f"locate_image(path={locate_image_path!r}, confidence={locate_confidence}) "
                f"→ ({end_x}, {end_y}); located_via={located_via}; clicked={clicked}."
            )

        else:
            logging.error(f"Unknown movement_type: {movement_type}")
            sys.exit(1)

        # Emit the structured-output block. Atomic single logging.info call —
        # downstream Parametrizer + the wrapped tool's KV promotion both rely
        # on this block being intact.
        _emit_section(
            {
                "movement_type": movement_type,
                "end_posx": end_x,
                "end_posy": end_y,
                "button_click": normalized_click,
                "clicked": str(bool(clicked)).lower(),
                "located_via": located_via,
            },
            outcome_body or "Mouser run completed.",
        )

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Mouser agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
