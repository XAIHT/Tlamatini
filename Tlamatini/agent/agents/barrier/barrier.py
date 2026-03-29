# Barrier Agent - OS-process-level synchronization barrier for flow control
# Each source agent STARTS a separate barrier process ("input sub-process").
# Each input sub-process creates a flag file for its caller, then atomically
# checks whether ALL flags are now present.  The LAST arrival fires the
# downstream target agents and exits.  No long-running polling process.
# Cross-process synchronization uses file-based locking (no threading).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
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

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
# Log clearing is handled inside main() — only manual/direct starts clear.
# Input sub-processes always append so we never lose sibling entries.
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

# Windows file-locking helpers for cross-process mutual exclusion
if sys.platform.startswith('win'):
    import msvcrt

    def _lock_file(fh):
        """Lock the first byte of an open file handle (blocking)."""
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock_file(fh):
        """Unlock the first byte of an open file handle."""
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock_file(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

    def _unlock_file(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

CROSS_PROCESS_LOCK_FILE = os.path.join(script_dir, "barrier.lock")


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
    """Wait until ALL specified agents have stopped running."""
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


# ---------------------------------------------------------------------------
# FLAG FILE helpers
# ---------------------------------------------------------------------------

def _flag_path(source_agent_name: str) -> str:
    """Return the absolute path for a source agent's flag file."""
    return os.path.join(script_dir, f"started_flag-{source_agent_name}.flg")


def _all_flags_present(source_agents: list) -> bool:
    """Check whether every source agent has its flag file."""
    return all(os.path.exists(_flag_path(s)) for s in source_agents)


def _count_existing_flags(source_agents: list) -> int:
    """Count how many flag files currently exist."""
    return sum(1 for s in source_agents if os.path.exists(_flag_path(s)))


def _delete_all_flags(source_agents: list):
    """Delete all flag files."""
    for s in source_agents:
        fp = _flag_path(s)
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except Exception as e:
            logging.warning(f"⚠️ Could not remove flag {fp}: {e}")


def _detect_caller() -> str:
    """Detect which source agent started this barrier process.

    Priority:
      1. BARRIER_CALLER environment variable (explicit)
      2. Parent process working directory inspection via psutil
    """
    caller = os.environ.get('BARRIER_CALLER', '')
    if caller:
        return caller

    try:
        import psutil
        parent = psutil.Process(os.getppid())
        parent_cwd = parent.cwd()
        return os.path.basename(parent_cwd)
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# MAIN — no long-running process, no polling.
# Each input sub-process creates its flag, checks if ALL are present.
# The LAST arrival fires the targets and exits.
# ---------------------------------------------------------------------------

def main():
    config = load_config()

    try:
        source_agents = config.get('source_agents', [])
        target_agents = config.get('target_agents', [])

        # Detect which source agent started this barrier process
        caller = _detect_caller()

        if not caller:
            # No caller detected — direct/manual start (e.g., from canvas restart)
            write_pid_file()
            if _IS_REANIMATED:
                logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
                logging.info("=" * 60)

            # Clear log for fresh manual/direct starts
            if not _IS_REANIMATED:
                for handler in logging.getLogger().handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                        logging.getLogger().removeHandler(handler)
                open(LOG_FILE_PATH, 'w').close()
                fh = logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
                fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logging.getLogger().addHandler(fh)

            logging.info("🚧 BARRIER AGENT STARTED (manual/direct)")
            logging.info(f"👀 Source agents (inputs): {source_agents}")
            logging.info(f"🎯 Target agents (outputs): {target_agents}")

            # Clean up stale state from previous run
            if source_agents:
                _delete_all_flags(source_agents)
            logging.info("🗑️ Cleaned stale flags from previous run")
            logging.info("🏁 Barrier agent finished (no caller specified).")
            return

        # --- INPUT SUB-PROCESS ---
        # Immediately remove agent.pid that our calling source agent wrote.
        # Other source agents call wait_for_agents_to_stop("barrier_1")
        # before starting their own barrier process — if agent.pid lingers
        # they deadlock.
        remove_pid_file()

        logging.info(f"🚧 BARRIER INPUT for {caller}")
        logging.info(f"👀 Source agents: {source_agents}")
        logging.info(f"🎯 Target agents: {target_agents}")

        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)

        if caller not in source_agents:
            logging.warning(f"⚠️ Caller '{caller}' not in source_agents — registering anyway")

        # Atomically: create flag → check if ALL flags present → fire if so
        should_fire = False
        with open(CROSS_PROCESS_LOCK_FILE, 'a+') as lf:
            _lock_file(lf)
            try:
                flag = _flag_path(caller)

                # Do NOT recreate/overwrite if flag already exists
                if not os.path.exists(flag):
                    with open(flag, 'w') as ff:
                        ff.write(caller)
                    logging.info(f"🏳️ Flag created for {caller}")
                else:
                    logging.info(f"🏳️ Flag already exists for {caller} — skipping")

                present = _count_existing_flags(source_agents)

                if _all_flags_present(source_agents):
                    logging.info(f"🔓 All flags present ({present}/{len(source_agents)}) — barrier UNLOCKED!")
                    _delete_all_flags(source_agents)
                    logging.info("🗑️ All flag files deleted")
                    should_fire = True
                else:
                    logging.info(f"⏳ {present}/{len(source_agents)} flags — waiting for more arrivals")
            finally:
                _unlock_file(lf)

        if should_fire:
            # This is the last arrival — fire downstream agents
            write_pid_file()
            if target_agents:
                wait_for_agents_to_stop(target_agents)
                logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
                total = 0
                for target in target_agents:
                    if start_agent(target):
                        total += 1
                logging.info(f"🏁 Barrier fired. Triggered {total}/{len(target_agents)} agents.")
            else:
                logging.info("🏁 Barrier fired (no target agents configured).")
        else:
            logging.info(f"🏁 Input sub-process for {caller} done — exiting")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
