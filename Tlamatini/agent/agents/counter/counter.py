# Counter Agent - Deterministic agent that maintains a persistent counter
# and routes to Path L (less than) or Path G (greater than or equal) based
# on comparing the counter value against a configured threshold.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., counter_1, counter_2).
# Source and target agents should also be referenced with their cardinal numbers.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess
from typing import Dict

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., counter_1 -> counter_1.log)
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

# Reanimation file for the persistent counter value
REANIM_COUNTER_FILE = "reanim.counter"

# Maximum value for an unsigned long (64-bit) — Python has arbitrary precision,
# but we enforce a ceiling matching C/C++ unsigned long long max.
MAX_COUNTER_VALUE = 2**64 - 1


def load_config(path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
    """
    Get the command to run a Python script.
    - In Dev: Use current sys.executable (handles venvs).
    - In Frozen (Windows): Check for bundled python.exe, else fallback to 'python'.
    - In Frozen (Unix): Fallback to 'python3'.
    """
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
    """Read PYTHON_HOME exclusively from USER environment variables (Windows registry)."""
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

    # Check if deployed in session: pools/<session_id>/<agent_dir>
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
    """Start a target agent. Returns True if started successfully."""
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


def load_counter() -> int:
    """Load counter value from reanimation file. Returns None if file doesn't exist."""
    if not os.path.exists(REANIM_COUNTER_FILE):
        return None
    try:
        with open(REANIM_COUNTER_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is not None and 'counter' in data:
                return int(data['counter'])
    except Exception as e:
        logging.warning(f"Could not load counter from reanimation file: {e}")
    return None


def save_counter(value: int):
    """Save counter value to reanimation file."""
    try:
        with open(REANIM_COUNTER_FILE, "w", encoding="utf-8") as f:
            yaml.dump({'counter': value}, f)
    except Exception as e:
        logging.warning(f"Could not save counter to reanimation file: {e}")


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for _ in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


def main():
    """Main entry point for the Counter agent."""
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        initial_value = int(config.get('initial_value', 0))
        threshold_value = int(config.get('threshold_value', 10))
        target_agents_l = config.get('target_agents_l', [])
        target_agents_g = config.get('target_agents_g', [])

        logging.info("COUNTER AGENT STARTED")
        logging.info(f"Initial value: {initial_value}")
        logging.info(f"Threshold value: {threshold_value}")
        logging.info(f"Path L agents (less than): {target_agents_l}")
        logging.info(f"Path G agents (greater/equal): {target_agents_g}")

        # Load counter from reanimation file
        counter = load_counter()

        if counter is None:
            # First run or flow restarted — initialize with initial_value
            counter = initial_value
            logging.info(f"Counter initialized to initial_value: {counter}")
        else:
            logging.info(f"Counter loaded from reanimation file: {counter}")

        # Increment counter with overflow protection
        if counter >= MAX_COUNTER_VALUE:
            logging.warning(
                f"WARNING: Counter overflow detected! The number of executions is trying "
                f"to wrap around the counter value. Counter clamped to MAX value: {MAX_COUNTER_VALUE}"
            )
            counter = MAX_COUNTER_VALUE
        else:
            counter += 1
            logging.info(f"Counter incremented to: {counter}")

        # Save updated counter back to reanimation file
        save_counter(counter)
        logging.info(f"Counter saved to reanimation file: {counter}")

        # Compare counter with threshold and route accordingly
        if counter < threshold_value:
            logging.info(f"Counter ({counter}) < threshold ({threshold_value}) -> Path L (less than)")
            if target_agents_l:
                wait_for_agents_to_stop(target_agents_l)
                logging.info(f"Triggering Path L: {len(target_agents_l)} agents...")
                total_started = 0
                for target in target_agents_l:
                    logging.info(f"   Starting: {target}")
                    if start_agent(target):
                        total_started += 1
                logging.info(f"Path L: started {total_started}/{len(target_agents_l)} agents.")
            else:
                logging.info("No agents configured for Path L.")
        else:
            logging.info(f"Counter ({counter}) >= threshold ({threshold_value}) -> Path G (greater/equal)")
            if target_agents_g:
                wait_for_agents_to_stop(target_agents_g)
                logging.info(f"Triggering Path G: {len(target_agents_g)} agents...")
                total_started = 0
                for target in target_agents_g:
                    logging.info(f"   Starting: {target}")
                    if start_agent(target):
                        total_started += 1
                logging.info(f"Path G: started {total_started}/{len(target_agents_g)} agents.")
            else:
                logging.info("No agents configured for Path G.")

        logging.info("Counter agent finished.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
