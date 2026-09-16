# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
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
import json
import math

from mouser_coordinates import (
    checked_point, configure_dpi_awareness, desktop_geometry, focus_window,
    resolve_point, select_window, verify_window_point, window_rectangle,
)

_DPI_ERROR = ''
try:
    configure_dpi_awareness()
except Exception as exc:
    _DPI_ERROR = str(exc)

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
        raise RuntimeError('PyAutoGUI is unavailable')
    if not math.isfinite(total_time) or total_time <= 0:
        raise ValueError('total_time must be finite and positive')

    logging.info(f"Moving mouse randomly for {total_time} seconds...")
    start_time = time.time()

    while (time.time() - start_time) < total_time:
        left, top, right, bottom = random.choice(desktop_geometry()['monitors'])
        target_x = random.randint(left + 1, right - 2)
        target_y = random.randint(top + 1, bottom - 2)
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
            raise
        except Exception as e:
            raise RuntimeError(f'Mouse movement failed: {e}') from e

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
    if normalized not in supported:
        raise ValueError(f'Unknown button_click: {button_click}')
    return normalized


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


def issue_click_after_reaching_target(end_posx: int, end_posy: int, button_click: str) -> bool:
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot issue click.")
        return False

    normalized_click = normalize_button_click(button_click)
    if normalized_click == 'none':
        logging.info("No button_click configured. Skipping click at final position.")
        return False

    current_x, current_y = pyautogui.position()
    tolerance_pixels = 2
    if abs(current_x - end_posx) > tolerance_pixels or abs(current_y - end_posy) > tolerance_pixels:
        logging.warning(
            f"Final position not effectively reached. Expected ({end_posx}, {end_posy}), "
            f"current position is ({current_x}, {current_y}). Skipping configured click '{normalized_click}'."
        )
        return False

    try:
        if normalized_click.startswith('double-'):
            button = normalized_click.split('-', 1)[1]
            pyautogui.doubleClick(button=button)
            logging.info(f"Issued configured double {button} click at ({current_x}, {current_y}).")
        else:
            pyautogui.click(button=normalized_click)
            logging.info(f"Issued configured {normalized_click} click at ({current_x}, {current_y}).")
        return True
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during configured click, skipping click.")
    except Exception as e:
        logging.warning(f"Configured click '{normalized_click}' failed: {e}")
    return False


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
        return issue_click_after_reaching_target(end_posx, end_posy, button_click)
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
    clicked = issue_click_after_reaching_target(current_x, current_y, button_click)
    return (current_x, current_y, clicked)


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

    held = False
    try:
        if not use_actual_position:
            logging.info(f"Drag start: moving to ({ini_posx}, {ini_posy})...")
            pyautogui.moveTo(ini_posx, ini_posy, duration=0.4, tween=pyautogui.easeInOutQuad)
        else:
            cx, cy = pyautogui.position()
            logging.info(f"Drag start: using current position ({cx}, {cy}).")

        duration = random.uniform(0.8, 1.8)
        logging.info(f"Dragging with button={drag_button!r} to ({end_posx}, {end_posy}) over {duration:.2f}s...")
        held = True
        pyautogui.mouseDown(button=drag_button)
        pyautogui.moveTo(end_posx, end_posy, duration=duration,
                         tween=pyautogui.easeInOutQuad)
        logging.info(f"Drag completed at ({end_posx}, {end_posy}).")
        return True
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during drag, skipping.")
        return False
    except Exception as e:
        logging.warning(f"Drag error: {e}, skipping.")
        return False
    finally:
        if held:
            # Always release our button, including after the corner fail-safe.
            # Native button-up contains no movement and cannot start a new drag.
            import win32api
            flags = {'left': 0x0004, 'right': 0x0010, 'middle': 0x0040}
            win32api.mouse_event(flags[drag_button], 0, 0, 0, 0)


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


def click_at_window(window_title, anchor, button_click, config=None):
    """Resolve one window and click an explicit anchor in its client rectangle."""
    config = dict(config or {}, window_title=window_title)
    hwnd = config.get('_target_hwnd') or select_window(config)
    focus_window(hwnd)
    left, top, width, height = window_rectangle(hwnd, config.get('window_area', 'client'))
    anchors = {
        'center': (0.5, 0.5), 'topleft': (0.05, 0.05),
        'topright': (0.95, 0.05), 'bottomleft': (0.05, 0.95),
        'bottomright': (0.95, 0.95),
    }
    anchor = str(anchor or 'center').lower()
    if anchor == 'titlebar':
        # Title-bar height is measured from the window/client origins, not a
        # fixed 12-pixel guess. Custom chrome needs an actual control locator.
        wl, wt, ww, _ = window_rectangle(hwnd, 'window')
        _, client_top, _, _ = window_rectangle(hwnd, 'client')
        if client_top <= wt:
            raise ValueError('Window has no measurable standard title bar')
        point = (wl + ww // 2, wt + (client_top - wt) // 2)
    elif anchor in anchors:
        ax, ay = anchors[anchor]
        point = (left + round(ax * (width - 1)), top + round(ay * (height - 1)))
    else:
        raise ValueError(f'Unknown window_anchor: {anchor}')
    point = checked_point(*point, desktop_geometry())
    pyautogui.moveTo(*point, duration=0.3)
    verify_window_point(hwnd, point)
    return (*point, issue_click_after_reaching_target(*point, button_click), 'window_title')


def click_at_located_image(image_path, confidence, button_click, config=None):
    """Match on the physical virtual desktop, including secondary monitors."""
    from PIL import ImageGrab

    if not image_path or not os.path.isfile(image_path):
        raise ValueError('locate_image_path must name an existing image')
    conf = float(confidence)
    if not 0.5 <= conf <= 1.0:
        raise ValueError('locate_confidence must be in [0.5, 1.0]')
    config = config or {}
    hwnd = config.get('_target_hwnd')
    geometry = desktop_geometry()
    screenshot = ImageGrab.grab(all_screens=True)
    if screenshot.size != (geometry['width'], geometry['height']):
        raise RuntimeError('Capture dimensions do not match the physical desktop')
    origin_x, origin_y = geometry['left'], geometry['top']
    if hwnd:
        left, top, width, height = window_rectangle(hwnd, config.get('window_area', 'client'))
        right = min(geometry['left'] + geometry['width'], left + width)
        bottom = min(geometry['top'] + geometry['height'], top + height)
        left, top = max(left, origin_x), max(top, origin_y)
        if right <= left or bottom <= top:
            raise ValueError('Target window is outside the captured desktop')
        screenshot = screenshot.crop((left - origin_x, top - origin_y,
                                      right - origin_x, bottom - origin_y))
        origin_x, origin_y = left, top
    matches = []
    try:
        for box in pyautogui.locateAll(image_path, screenshot, confidence=conf):
            # Adjacent template-match pixels represent the same button.
            if not any(abs(box.left - old.left) < box.width / 2 and
                       abs(box.top - old.top) < box.height / 2 for old in matches):
                matches.append(box)
            if len(matches) > 1:
                raise ValueError('Reference image is ambiguous; restrict it to a target window')
    except pyautogui.ImageNotFoundException:
        pass
    if not matches:
        raise ValueError('Reference image was not found on the current desktop')
    box = matches[0]
    point = checked_point(origin_x + box.left + box.width // 2,
                          origin_y + box.top + box.height // 2, geometry)
    pyautogui.moveTo(*point, duration=0.3)
    if hwnd:
        verify_window_point(hwnd, point)
    clicked = issue_click_after_reaching_target(*point, button_click)
    return (*point, clicked, 'locate_image')


def dispatch(config, fields=None):
    """Convert coordinates before sending any input; report only observed facts."""
    if _DPI_ERROR:
        raise RuntimeError(_DPI_ERROR)
    if pyautogui is None:
        raise RuntimeError('PyAutoGUI is unavailable')
    geometry = desktop_geometry()
    mode = str(config.get('movement_type', 'random')).lower()
    space = str(config.get('coordinate_space', 'screen')).lower()
    button = normalize_button_click(config.get('button_click', 'none'))
    if fields is None:
        fields = {}
    fields.update({
        'movement_type': mode, 'coordinate_space': space, 'button_click': button,
        'clicked': 'false', 'status': 'observed', 'located_via': 'manual',
        'desktop_left': geometry['left'], 'desktop_top': geometry['top'],
        'desktop_width': geometry['width'], 'desktop_height': geometry['height'],
        'monitors_json': json.dumps(geometry['monitors']),
    })
    clicked = False
    target = None
    has_window = bool(config.get('window_title') or config.get('window_handle'))
    hwnd = None
    rect = None
    if mode != 'inspect' and (has_window or space.startswith('window')):
        hwnd = select_window(config)
        focus_window(hwnd)
        rect = window_rectangle(hwnd, config.get('window_area', 'client'))
        fields['window_handle'] = hwnd
    actual = str(config.get('actual_position', True)).lower() not in ('false', '0', 'no')
    if mode == 'inspect':
        fields['located_via'] = 'desktop_geometry'
    elif mode in ('localized', 'drag') or (mode == 'click' and not actual):
        target = resolve_point(config.get('end_posx', 500), config.get('end_posy', 500),
                               config, geometry, rect)
        start = tuple(pyautogui.position()) if actual or mode == 'click' else resolve_point(
            config.get('ini_posx', 0), config.get('ini_posy', 0), config, geometry, rect)
        checked_point(*start, geometry)
        if mode == 'drag':
            if hwnd:
                verify_window_point(hwnd, start)
                verify_window_point(hwnd, target)
            clicked = drag_mouse(*start, *target, False, button)
            if not clicked:
                raise RuntimeError('Drag input failed')
        else:
            if not actual and mode == 'localized':
                pyautogui.moveTo(*start, duration=0.2)
            pyautogui.moveTo(*target, duration=0.3)
            if hwnd:
                verify_window_point(hwnd, target)
            clicked = issue_click_after_reaching_target(*target, button)
        fields['located_via'] = space
    elif mode == 'click_at_window':
        x, y, clicked, via = click_at_window(config.get('window_title', ''),
                                           config.get('window_anchor', 'center'), button,
                                           dict(config, _target_hwnd=hwnd))
        target = (x, y)
        fields['located_via'] = via
    elif mode == 'locate_image':
        locate_config = dict(config, _target_hwnd=hwnd)
        x, y, clicked, via = click_at_located_image(config.get('locate_image_path', ''),
                                                   config.get('locate_confidence', 0.8),
                                                   button, locate_config)
        target = (x, y)
        fields['located_via'] = via
    elif mode in ('click', 'scroll'):
        point = checked_point(*pyautogui.position(), geometry)
        if hwnd:
            verify_window_point(hwnd, point)
        if mode == 'click':
            _, _, clicked = click_at_current_position(button)
        else:
            _, _, ok = scroll_at_current(int(config.get('scroll_amount', 0)))
            if not ok:
                raise RuntimeError('Scroll input failed or scroll_amount is zero')
        fields['located_via'] = 'current_position'
    elif mode == 'random':
        move_mouse_random(float(config.get('total_time', 30)))
        fields['located_via'] = 'random'
    else:
        raise ValueError(f'Unknown movement_type: {mode}')
    fields['clicked'] = str(clicked).lower()
    actual_x, actual_y = pyautogui.position()
    fields.update(end_posx=actual_x, end_posy=actual_y, clicked=str(clicked).lower())
    if target:
        fields.update(requested_posx=target[0], requested_posy=target[1])
        if abs(actual_x - target[0]) > 2 or abs(actual_y - target[1]) > 2:
            raise RuntimeError('Cursor did not reach the resolved physical target')
    if mode not in ('inspect', 'random', 'scroll') and button != 'none' and not clicked:
        raise RuntimeError('Configured click was not issued')
    if mode != 'inspect':
        fields['status'] = 'input_sent'
    return fields


def main():
    config = load_config()
    write_pid_file()
    logging.info('MOUSER AGENT %s', 'REANIMATED' if _IS_REANIMATED else 'STARTED')
    exit_code = 0
    fields = {'movement_type': config.get('movement_type', ''), 'clicked': 'false'}
    try:
        try:
            dispatch(config, fields)
            body = 'Physical coordinates resolved. Input delivery does not verify the application outcome.'
        except Exception as exc:
            exit_code = 1
            fields.update(status='error', located_via='error')
            body = str(exc).replace('\n', ' ')
            logging.error('Mouser failed: %s', body)
        fields['action_status'] = fields['status']
        _emit_section(fields, body)
        targets = config.get('target_agents', []) or []
        if targets:
            wait_for_agents_to_stop(targets)
            for target in targets:
                start_agent(target)
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
