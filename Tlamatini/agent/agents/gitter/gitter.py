# Gitter Agent - Git operations agent
# Action: Triggered by upstream -> Execute git command -> Log output -> Trigger downstream

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


def build_git_command(config: Dict) -> list:
    """Build the git command list based on config."""
    command = config.get('command', 'status').strip().lower()
    branch = config.get('branch', 'main').strip()
    commit_message = config.get('commit_message', '').strip()
    remote = config.get('remote', '').strip()
    custom_command = config.get('custom_command', '').strip()

    if command == 'clone':
        if not remote:
            logging.error("❌ 'remote' URL is required for clone command.")
            return None
        return ['git', 'clone', remote, '.']
    elif command == 'pull':
        return ['git', 'pull']
    elif command == 'push':
        return ['git', 'push']
    elif command == 'commit':
        if not commit_message:
            commit_message = "Auto-commit by Gitter agent"
        # git add -A && git commit uses shell, so we handle it differently
        return ['git', 'commit', '-am', commit_message]
    elif command == 'checkout':
        return ['git', 'checkout', branch]
    elif command == 'branch':
        return ['git', 'branch']
    elif command == 'diff':
        return ['git', 'diff']
    elif command == 'log':
        return ['git', 'log', '--oneline', '-20']
    elif command == 'status':
        return ['git', 'status']
    elif command == 'custom':
        if not custom_command:
            logging.error("❌ 'custom_command' is required when command is 'custom'.")
            return None
        # Split the custom command string into a list
        return custom_command.split()
    else:
        logging.error(f"❌ Unknown git command: {command}")
        return None


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        repo_path = config.get('repo_path', '').strip()
        target_agents = config.get('target_agents', [])
        command = config.get('command', 'status')

        logging.info("🔧 GITTER AGENT STARTED")
        logging.info(f"📂 Repository: {repo_path}")
        logging.info(f"⚡ Command: git {command}")
        logging.info(f"🎯 Targets: {target_agents}")

        if not repo_path:
            logging.error("❌ 'repo_path' is not configured. Please set the repository path in config.yaml.")
            sys.exit(1)

        if not os.path.isabs(repo_path):
            repo_path = os.path.abspath(os.path.join(script_dir, repo_path))
            logging.info(f"📂 Resolved relative path to: {repo_path}")

        # For clone, create the directory if it doesn't exist
        if command == 'clone':
            os.makedirs(repo_path, exist_ok=True)
        elif not os.path.exists(repo_path):
            logging.error(f"❌ Repository path does not exist: {repo_path}")
            sys.exit(1)

        # For commit, run git add -A first
        if command == 'commit':
            logging.info("📝 Running git add -A...")
            add_result = subprocess.run(
                ['git', 'add', '-A'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            if add_result.returncode != 0:
                logging.error(f"❌ git add -A failed (exit code {add_result.returncode})")
                if add_result.stderr:
                    logging.error(f"   stderr: {add_result.stderr.strip()}")
                sys.exit(1)
            logging.info("✅ git add -A completed successfully.")

        # Build and run the git command
        git_cmd = build_git_command(config)
        if git_cmd is None:
            sys.exit(1)

        logging.info(f"🔧 Executing: {' '.join(git_cmd)}")

        result = subprocess.run(
            git_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Log output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logging.info(f"   {line}")

        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if result.returncode == 0:
                    logging.info(f"   {line}")  # Some git commands write to stderr on success
                else:
                    logging.error(f"   {line}")

        # Print the complete response in structured format
        full_output = ""
        if result.stdout:
            full_output += result.stdout
        if result.stderr:
            if full_output:
                full_output += "\n"
            full_output += result.stderr

        _git_body = full_output if full_output else "(no output)"
        logging.info(
            f"INI_SECTION_GITTER<<<\n"
            f"git_command: git {command}\n"
            f"\n"
            f"{_git_body}\n"
            f">>>END_SECTION_GITTER"
        )

        if result.returncode != 0:
            logging.error(f"❌ Git command failed with exit code {result.returncode}")
            sys.exit(1)

        logging.info(f"✅ Git {command} completed successfully.")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Gitter agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except subprocess.TimeoutExpired:
        logging.error("❌ Git command timed out after 300 seconds.")
        sys.exit(1)
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
