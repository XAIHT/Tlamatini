# Starter Agent - No LLM, deterministic agent starter
# This agent starts all agents connected to its output when executed.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., starter_1, starter_2).
# Target agents should be referenced with their cardinal numbers.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import yaml
import logging
import subprocess
import psutil
import time
from typing import List, Dict, Optional

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., starter_1 -> starter_1.log)
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
        # Check for bundled python.exe next to main executable
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
    Deployed agents with cardinals (e.g., monitor_log_1, starter_2) are here.
    """
    if getattr(sys, 'frozen', False):
        # Frozen mode: pool is in <exe_dir>/agents/pools/
        return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
    else:
        # Development mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return parent
            
        # Fallback: agents/<agent_name> -> agents/pools
        return os.path.join(os.path.dirname(current_dir), 'pools')


def get_template_agents_path() -> str:
    """
    Get the template agents directory path (non-deployed agents).
    Template agents without cardinals (e.g., monitor_log, starter) are here.
    """
    if getattr(sys, 'frozen', False):
        # Frozen mode: templates are in <exe_dir>/agents/
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
        # Development mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            # pools/<session>/<agent> -> pools -> agents
            return os.path.dirname(grandparent)
            
        # Fallback: agents/<agent_name> -> agents
        return os.path.dirname(current_dir)


def is_deployed_agent(agent_name: str) -> bool:
    """
    Check if an agent name has a cardinal suffix (is a deployed instance).
    Examples: monitor_log_1 -> True, monitor_log -> False
    """
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2:
        try:
            int(parts[1])  # Check if last part is a number
            return True
        except ValueError:
            return False
    return False


def get_agent_directory(agent_name: str) -> str:
    """
    Get the full path to an agent's directory.
    Deployed agents (with cardinal, e.g., monitor_log_1) are in pool/.
    Template agents (without cardinal, e.g., monitor_log) are in agents/.
    """
    if is_deployed_agent(agent_name):
        # Deployed agent in pool directory
        return os.path.join(get_pool_path(), agent_name)
    else:
        # Template agent in main agents directory
        return os.path.join(get_template_agents_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    """
    Get the Python script path for an agent.
    The script is named after the agent's base name (without cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log.py
    - starter_2 -> pool/starter_2/starter.py
    """
    agent_dir = get_agent_directory(agent_name)
    
    # Get base name without cardinal for script file name
    if is_deployed_agent(agent_name):
        # starter_1 -> starter
        base_name = '_'.join(agent_name.rsplit('_', 1)[:-1])
    else:
        base_name = agent_name
    
    script_file = os.path.join(agent_dir, f"{base_name}.py")
    return script_file


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


def is_agent_running(agent_name: str) -> Optional[int]:
    """
    Check if an agent is currently running.
    Returns the PID if running, None otherwise.
    """
    script_path = get_agent_script_path(agent_name)
    script_name = os.path.basename(script_path)
    agent_dir = get_agent_directory(agent_name)
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                # Check if this process is running from the agent's directory
                if agent_dir in cmdline_str or (script_name in cmdline_str and agent_name in cmdline_str):
                    return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return None

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


def recursive_kill(pid: int):
    """Recursively kill a process and all its children."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return

    # Kill children first
    for child in children:
        try:
            logging.info(f"🔪 Killing child process PID {child.pid} ({child.name()})...")
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Kill parent
    try:
        logging.info(f"🔪 Killing process PID {parent.pid} ({parent.name()})...")
        parent.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def stop_agent(pid: int, agent_name: str) -> bool:
    """
    Stop a running agent by PID.
    Returns True if stopped, False otherwise.
    """
    logging.info(f"🛑 Stopping agent '{agent_name}' (PID: {pid})...")
    recursive_kill(pid)
    
    # Wait briefly for process to disappear
    try:
        psutil.Process(pid).wait(timeout=3)
        return True
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        logging.warning(f"⚠️ Timed out waiting for agent '{agent_name}' to stop.")
        return False
    except Exception as e:
        logging.error(f"❌ Error stopping agent '{agent_name}': {e}")
        return False


def start_agent(agent_name: str) -> bool:
    """
    Start a target agent.
    Returns True if started successfully, False otherwise.
    """
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    
    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
        return False
    
    if not os.path.exists(agent_dir):
        logging.error(f"❌ Agent directory not found: {agent_dir}")
        return False
    
    try:
        # Start the agent using robust python commmand
        cmd = get_python_command() + [script_path]
        logging.info(f"  Command: {cmd}")
        
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # Write PID file for fast status checking (reduces race condition)
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
    """Main execution for the Starter agent."""
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    
    try:
        target_agents: List[str] = config.get('target_agents', [])
        exit_after_start: bool = config.get('exit_after_start', True)
        
        if not target_agents:
            logging.error("❌ No target agents configured. Nothing to start.")
            logging.info("💡 Connect agents from Starter's output on the canvas to populate target_agents.")
            return  # Will trigger finally block
        
        logging.info("🚀 STARTER AGENT STARTED")
        logging.info(f"📁 Pool path: {get_pool_path()}")
        logging.info(f"🎯 Target agents to start: {target_agents}")
        logging.info("=" * 60)
        
        started_count = 0

        # Wait for all target agents to stop before starting them
        wait_for_agents_to_stop(target_agents)
        for target in target_agents:
            logging.info(f"\n🎯 Processing target: {target}")
            logging.info(f"🚀 Starting agent '{target}'...")
            if start_agent(target):
                started_count += 1

        logging.info("=" * 60)
        logging.info(f"🚀 STARTUP COMPLETE: {started_count} started")
        logging.info("=" * 60)
        
        if exit_after_start:
            logging.info("👋 Starter agent exiting after startup sequence.")
        else:
            logging.info("⏳ Starter agent staying running (exit_after_start=false)")
            # Could add a loop here for manual trigger mode
        
    except Exception as e:
        logging.error(f"❌ Error in Starter agent: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()

