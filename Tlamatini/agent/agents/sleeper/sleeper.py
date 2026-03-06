# Sleeper Agent - Deterministic agent to wait and then trigger downstream
# Action: Triggered by upstream -> Wait -> Trigger downstream

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
        # Check for bundled python.exe next to main executable
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']
    
    return ['python3']


# Helper functions for Agent Triggering
def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if deployed in session: pools/<session_id>/<agent_dir>
    # pools/session/agent -> parent=pools/session -> grandparent=pools
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    
    if os.path.basename(grandparent) == 'pools':
         return parent
         
    # Fallback/Dev: pools/<agent> -> parent=pools
    if os.path.basename(parent) == 'pools':
        return parent
        
    # Standard Dev fallback
    return os.path.join(os.path.dirname(current_dir), 'pools')


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

def get_agent_directory(agent_name: str) -> str:
    # agents are in pool dir
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

def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    
    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
        return False
    
    try:
        # Start the agent using robust python command
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")
        
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
    
    try:
        # Configuration
        # Defaults to 5000ms (5 seconds)
        duration_ms = config.get('duration_ms', 5000)
        target_agents = config.get('target_agents', [])
        
        try:
            duration_ms = int(duration_ms)
            if duration_ms < 0:
                logging.warning(f"⚠️ Invalid duration {duration_ms}ms, using 0ms")
                duration_ms = 0
        except ValueError:
            logging.error(f"❌ Invalid duration format: {duration_ms}. Using 5000ms.")
            duration_ms = 5000
    
        duration_sec = duration_ms / 1000.0
    
        logging.info("🔥 SLEEPER AGENT STARTED")
        logging.info(f"⏱️ Sleeping for {duration_ms} ms ({duration_sec} sec)")
        logging.info(f"🎯 Targets: {target_agents}")
    
        # SLEEP with Per-Second Logging
        elapsed = 0
        remaining = duration_sec
        
        while remaining > 0:
            sleep_chunk = min(1.0, remaining)
            time.sleep(sleep_chunk)
            remaining -= sleep_chunk
            elapsed += sleep_chunk
            
            # Log every integer second (approximately)
            if int(elapsed) > int(elapsed - sleep_chunk):
                logging.info(f"⏳ Waiting... {int(elapsed)}s elapsed / {int(duration_sec)}s total")
        
        logging.info("⏰ Woke up from sleep.")
    
        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1
                
        logging.info(f"🏁 Sleeper agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
        
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
        
    sys.exit(0)

if __name__ == "__main__":
    main()
