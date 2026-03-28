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


def move_mouse_localized(ini_posx: int, ini_posy: int, end_posx: int, end_posy: int,
                         use_actual_position: bool):
    """Move the mouse from an initial position to a final position."""
    if pyautogui is None:
        logging.error("pyautogui is not installed. Cannot move mouse.")
        return

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
    except pyautogui.FailSafeException:
        logging.warning("Fail-safe triggered during localized movement, skipping movement.")
    except Exception as e:
        logging.warning(f"Localized mouse movement error: {e}, skipping movement.")


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', [])
        movement_type = config.get('movement_type', 'random')

        logging.info("MOUSER AGENT STARTED")
        logging.info(f"Movement type: {movement_type}")
        logging.info(f"Targets: {target_agents}")

        if movement_type == 'random':
            total_time = config.get('total_time', 30)
            logging.info(f"Total time: {total_time}s")
            try:
                move_mouse_random(float(total_time))
            except Exception as e:
                logging.warning(f"Random mouse movement failed: {e}")

        elif movement_type == 'localized':
            use_actual_position = config.get('actual_position', True)
            ini_posx = config.get('ini_posx', 0)
            ini_posy = config.get('ini_posy', 0)
            end_posx = config.get('end_posx', 500)
            end_posy = config.get('end_posy', 500)

            logging.info(f"Actual position: {use_actual_position}")
            if not use_actual_position:
                logging.info(f"Initial position: ({ini_posx}, {ini_posy})")
            logging.info(f"Final position: ({end_posx}, {end_posy})")

            try:
                move_mouse_localized(
                    int(ini_posx), int(ini_posy),
                    int(end_posx), int(end_posy),
                    bool(use_actual_position)
                )
            except Exception as e:
                logging.warning(f"Localized mouse movement failed: {e}")
        else:
            logging.error(f"Unknown movement_type: {movement_type}")
            sys.exit(1)

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
