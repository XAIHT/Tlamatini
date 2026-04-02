# J-Decompiler Agent - Decompile .class, .jar, .war, .ear files using jd-cli
# Action: Triggered by upstream -> Decompile Java files -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import glob
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


# ---------------------------------------------------------------------------
# JD-CLI DECOMPILER HELPERS
# ---------------------------------------------------------------------------

def get_jd_cli_path() -> str:
    """Locate the jd-cli directory based on frozen or dev mode."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        # In dev: j_decompiler.py is in agent/agents/j_decompiler/
        # jd-cli is in Tlamatini/jd-cli/ (3 levels up from agents dir)
        application_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))

    jd_cli_dir = os.path.join(application_path, 'jd-cli')
    return jd_cli_dir


def decompile_file(filepath: str, jd_cli_dir: str) -> bool:
    """Decompile a single .class, .jar, .war, or .ear file using jd-cli."""
    jd_cli_bat = os.path.join(jd_cli_dir, 'jd-cli.bat')

    if not os.path.exists(jd_cli_bat):
        logging.error(f"❌ jd-cli.bat not found at '{jd_cli_bat}'")
        return False

    file_ext = os.path.splitext(filepath)[1].lower()
    file_basename = os.path.splitext(os.path.basename(filepath))[0]
    file_dir = os.path.dirname(filepath)

    if file_ext == '.class':
        # For .class files, output the .java beside the .class
        dest_dir = file_dir
    else:
        # For .jar, .war, .ear files, create a directory beside the archive
        dest_dir = os.path.join(file_dir, file_basename)

    os.makedirs(dest_dir, exist_ok=True)

    cmd = [jd_cli_bat, filepath, dest_dir]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=jd_cli_dir, shell=True, timeout=300
        )
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout
            logging.error(f"❌ Error decompiling '{filepath}': {error_msg}")
            return False
        logging.info(f"✅ Decompiled '{filepath}' -> '{dest_dir}'")
        return True
    except subprocess.TimeoutExpired:
        logging.error(f"❌ Timeout decompiling '{filepath}' (300s)")
        return False
    except Exception as e:
        logging.error(f"❌ Failed to decompile '{filepath}': {e}")
        return False


def collect_files(directory_param: str, recursive: bool) -> list:
    """Collect files matching wildcard patterns from the directory parameter.

    The directory parameter format is: base_path\\*.ext1,*.ext2,...
    or just a base_path (defaults to *.class,*.jar,*.war,*.ear).
    """
    # Split by last path separator to extract base dir and wildcard patterns
    # e.g. "C:\\Temp\\*.class,*.jar,*.war,*.ear"
    # Try to detect if wildcards are embedded in the path
    parts = directory_param.rsplit('\\', 1)
    if len(parts) == 2 and ('*' in parts[1] or '?' in parts[1]):
        base_dir = parts[0]
        pattern_str = parts[1]
    else:
        # Try forward slash
        parts = directory_param.rsplit('/', 1)
        if len(parts) == 2 and ('*' in parts[1] or '?' in parts[1]):
            base_dir = parts[0]
            pattern_str = parts[1]
        else:
            # No wildcards in last component — treat entire string as base dir
            base_dir = directory_param
            pattern_str = "*.class,*.jar,*.war,*.ear"

    if not os.path.isdir(base_dir):
        logging.error(f"❌ Directory does not exist: {base_dir}")
        return []

    # Split comma-separated patterns
    patterns = [p.strip() for p in pattern_str.split(',') if p.strip()]

    found_files = []
    for pattern in patterns:
        if recursive:
            search_pattern = os.path.join(base_dir, '**', pattern)
            found_files.extend(glob.glob(search_pattern, recursive=True))
        else:
            search_pattern = os.path.join(base_dir, pattern)
            found_files.extend(glob.glob(search_pattern))

    # Deduplicate while preserving order
    seen = set()
    unique_files = []
    for f in found_files:
        abs_f = os.path.abspath(f)
        if abs_f not in seen:
            seen.add(abs_f)
            unique_files.append(abs_f)

    return unique_files


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

    try:
        directory = config.get('directory', 'C:\\Temp\\*.class,*.jar,*.war,*.ear')
        recursive = config.get('recursive', False)
        target_agents = config.get('target_agents', [])

        logging.info("🔧 J-DECOMPILER AGENT STARTED")
        logging.info(f"📁 Directory: {directory}")
        logging.info(f"🔄 Recursive: {recursive}")
        logging.info(f"🎯 Targets: {target_agents}")

        # Locate jd-cli
        jd_cli_dir = get_jd_cli_path()
        jd_cli_bat = os.path.join(jd_cli_dir, 'jd-cli.bat')
        if not os.path.exists(jd_cli_bat):
            logging.error(f"❌ jd-cli.bat not found at '{jd_cli_bat}'")
            sys.exit(1)
        logging.info(f"🔧 Using jd-cli at: {jd_cli_dir}")

        # Collect files to decompile
        files = collect_files(directory, recursive)
        logging.info(f"📋 Found {len(files)} file(s) to decompile")

        if not files:
            logging.info("ℹ️ No files found matching the patterns — nothing to decompile.")
        else:
            success_count = 0
            fail_count = 0
            for filepath in files:
                logging.info(f"🔧 Decompiling: {filepath}")
                if decompile_file(filepath, jd_cli_dir):
                    success_count += 1
                else:
                    fail_count += 1

            logging.info(f"📊 Decompilation complete: {success_count} succeeded, {fail_count} failed")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 J-Decompiler agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
