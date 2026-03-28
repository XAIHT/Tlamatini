# Asker Agent - Deterministic agent that asks the user to choose a path
# When started, writes ASKER_CHOICE_NEEDED to log.
# The frontend detects this and shows an A/B dialog.
# Once the user picks, the backend writes choice.txt with "A" or "B".
# This script reads choice.txt and triggers the corresponding target agents.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import yaml
import logging
import subprocess
import time
from typing import List, Dict

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., asker_1 -> asker_1.log)
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
    """Load configuration from YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> List[str]:
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
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., asker_1, starter_2) are here.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return parent

        # Fallback: agents/<agent_name> -> agents/pools
        return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
    """Get the full path to an agent's directory in the pool."""
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    """
    Get the Python script path for an agent.
    The script is named after the agent's base name (without cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log.py
    - asker_2 -> pool/asker_2/asker.py
    """
    agent_dir = get_agent_directory(agent_name)

    # Get base name without cardinal for script file name
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2:
        try:
            int(parts[1])
            base_name = parts[0]
        except ValueError:
            base_name = agent_name
    else:
        base_name = agent_name

    return os.path.join(agent_dir, f"{base_name}.py")


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


# PID Management
PID_FILE = "agent.pid"
CHOICE_FILE = "choice.txt"
STATUS_FILE = "agent.status"


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


def write_status_file(status):
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(status)
    except Exception as e:
        logging.error(f"❌ Failed to write status file: {e}")


def remove_status_file():
    try:
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)
    except Exception as e:
        logging.error(f"❌ Failed to remove status file: {e}")


def cleanup_choice_file():
    """Remove the choice file if it exists."""
    try:
        if os.path.exists(CHOICE_FILE):
            os.remove(CHOICE_FILE)
    except Exception as e:
        logging.error(f"⚠️ Failed to remove choice file: {e}")


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    # Clean up any stale choice file from previous runs
    cleanup_choice_file()
    # Clean up any stale status file
    remove_status_file()

    try:
        target_agents_a: List[str] = config.get('target_agents_a', [])
        target_agents_b: List[str] = config.get('target_agents_b', [])

        logging.info("🤔 ASKER AGENT STARTED")
        logging.info(f"🅰️ Path A agents: {target_agents_a}")
        logging.info(f"🅱️ Path B agents: {target_agents_b}")
        logging.info("=" * 60)

        # Signal the frontend to show the choice dialog
        logging.info("ASKER_CHOICE_NEEDED")
        write_status_file("waiting_for_user_input")

        # Poll for choice.txt (written by backend when user picks A or B)
        logging.info("⏳ Waiting for user choice...")
        max_wait = 300  # 5 minutes max
        elapsed = 0
        poll_interval = 0.5
        choice = None

        while elapsed < max_wait:
            if os.path.exists(CHOICE_FILE):
                try:
                    with open(CHOICE_FILE, "r", encoding="utf-8") as f:
                        choice = f.read().strip().upper()
                    if choice in ("A", "B"):
                        logging.info(f"✅ User selected: Path {choice}")
                        break
                    else:
                        logging.warning(f"⚠️ Invalid choice in file: '{choice}', waiting...")
                        choice = None
                except Exception as e:
                    logging.error(f"⚠️ Error reading choice file: {e}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        # Remove status file as soon as we have a choice or timeout
        remove_status_file()

        if choice is None:
            logging.error("❌ Timed out waiting for user choice (5 minutes)")
            return

        # Clean up choice file
        cleanup_choice_file()

        # Trigger the chosen path
        if choice == "A":
            agents_to_start = target_agents_a
            path_label = "A"
        else:
            agents_to_start = target_agents_b
            path_label = "B"

        if not agents_to_start:
            logging.warning(f"⚠️ No agents configured for Path {path_label}")
        else:
            logging.info(f"🚀 Triggering Path {path_label}: {len(agents_to_start)} agents...")
            wait_for_agents_to_stop(agents_to_start)
            total_triggered = 0
            for target in agents_to_start:
                logging.info(f"   ► Triggering: {target}")
                if start_agent(target):
                    total_triggered += 1
            logging.info(f"✨ Triggered {total_triggered}/{len(agents_to_start)} agents.")

        logging.info(f"🏁 Asker agent finished. Choice: Path {path_label}")

    except Exception as e:
        logging.error(f"❌ Asker agent error: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        # Also ensure status file is gone
        remove_status_file()
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()
