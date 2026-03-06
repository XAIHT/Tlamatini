# Ender Agent - No LLM, deterministic agent terminator
# This agent terminates all agents in its connected graph when triggered.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., ender_1, ender_2).
# Source agents (agents to terminate) should be referenced with their cardinal numbers.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import yaml
import logging
import psutil
import subprocess
import time
from typing import List, Dict

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., ender_1 -> ender_1.log)
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
    Deployed agents with cardinals (e.g., monitor_log_1, ender_2) are here.
    Harden logic to support session-based pools.
    """
    # Get directory of THIS script (which is inside the agent's folder, e.g., pools/session_id/monitor_log_1)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # "Up one level" is where this agent lives (the pool directory)
    pool_dir = os.path.dirname(current_dir)
    
    # Validation: Ensure basic sanity
    if not os.path.exists(pool_dir):
         # Fallback for some weird structure
         if getattr(sys, 'frozen', False):
             return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
         return os.path.join(os.path.dirname(os.path.dirname(current_dir)), 'pools')

    return pool_dir


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
    """
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    """
    Get the Python script path for an agent.
    The script is named after the agent's base name (without cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log.py
    - ender_2 -> pool/ender_2/ender.py
    """
    agent_dir = get_agent_directory(agent_name)
    
    # Get base name without cardinal for script file name
    if is_deployed_agent(agent_name):
        # ender_1 -> ender
        base_name = '_'.join(agent_name.rsplit('_', 1)[:-1])
    else:
        # Check if underscore separation exists, try to be smart logic handles standard
        base_name = agent_name
    
    # Check simple first
    script_file = os.path.join(agent_dir, f"{base_name}.py")
    if os.path.exists(script_file):
        return script_file
        
    # Fallback: maybe the folder is ender_1 wraps a script named ender_1.py? (Unlikely with template copy)
    # But let's check exact name match
    script_file_exact = os.path.join(agent_dir, f"{agent_name}.py")
    if os.path.exists(script_file_exact):
        return script_file_exact

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


def find_agent_processes(agent_name: str) -> List[psutil.Process]:
    """
    Find all processes associated with an agent.
    Returns a list of psutil.Process objects.
    
    Uses multiple detection methods for reliability:
    1. Check if agent directory path is in cmdline (case-insensitive on Windows)
    2. Check if script name and agent name are in cmdline
    3. Check if process working directory matches agent directory
    """
    processes = []
    script_path = get_agent_script_path(agent_name)
    script_name = os.path.basename(script_path)
    agent_dir = get_agent_directory(agent_name)
    
    # Normalize paths for comparison (lowercase on Windows for case-insensitive matching)
    is_windows = sys.platform.startswith('win')
    agent_dir_normalized = agent_dir.lower() if is_windows else agent_dir
    script_name_normalized = script_name.lower() if is_windows else script_name
    agent_name_normalized = agent_name.lower() if is_windows else agent_name
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
        try:
            cmdline = proc.info.get('cmdline', [])
            proc_cwd = proc.info.get('cwd', '') or ''
            
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                
                # Normalize for comparison
                cmdline_check = cmdline_str.lower() if is_windows else cmdline_str
                cwd_check = proc_cwd.lower() if is_windows else proc_cwd
                
                # Method 1: Check cmdline for agent directory
                cmdline_dir_match = agent_dir_normalized in cmdline_check
                
                # Method 2: Check cmdline for script name AND agent name
                cmdline_script_match = (script_name_normalized in cmdline_check and 
                                       agent_name_normalized in cmdline_check)
                
                # Method 3: Check process working directory
                cwd_match = agent_dir_normalized in cwd_check
                
                if cmdline_dir_match or cmdline_script_match or cwd_match:
                    processes.append(proc)
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return processes


def terminate_agent(agent_name: str) -> bool:
    """
    Terminate an agent's process(es) using kill signal.
    Returns True if at least one process was terminated, False otherwise.
    """
    processes = find_agent_processes(agent_name)
    
    if not processes:
        logging.info(f"⏭️ Agent '{agent_name}' is not running, skipping.")
        return False
    
    terminated = False
    for proc in processes:
        try:
            pid = proc.pid
            logging.info(f"🛑 Terminating agent '{agent_name}' (PID: {pid})...")
            
            # Try graceful termination first (SIGTERM)
            proc.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                proc.wait(timeout=5)
                logging.info(f"✅ Agent '{agent_name}' (PID: {pid}) terminated gracefully.")
                terminated = True
            except psutil.TimeoutExpired:
                # Force kill if still running (SIGKILL)
                logging.warning(f"⚠️ Agent '{agent_name}' (PID: {pid}) didn't stop gracefully, force killing...")
                proc.kill()
                proc.wait(timeout=3)
                logging.info(f"💀 Agent '{agent_name}' (PID: {pid}) force killed.")
                terminated = True
                
        except psutil.NoSuchProcess:
            logging.info(f"⏭️ Agent '{agent_name}' process already ended.")
            terminated = True
        except psutil.AccessDenied:
            logging.error(f"❌ Access denied when trying to terminate '{agent_name}'.")
        except Exception as e:
            logging.error(f"❌ Error terminating '{agent_name}': {e}")
    
    return terminated


def _write_pid_file(agent_dir: str, pid: int):
    """Write the PID to agent.pid in the agent directory."""
    pid_file = os.path.join(agent_dir, "agent.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(str(pid))
        logging.info(f"   📝 PID file created: {pid_file} (PID: {pid})")
    except Exception as e:
        logging.error(f"   ❌ Failed to write PID file: {e}")


def launch_agent(agent_name: str):
    """Launch an output agent (e.g. Cleaner)."""
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    
    if not os.path.exists(script_path):
        logging.error(f"❌ Script not found for output agent: {script_path}")
        return

    logging.info(f"🚀 Launching output agent: {agent_name}...")
    try:
        # Launch independently using robust python command
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")
        
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # KEY FIX: Write the PID file so the backend can detect it is running!
        _write_pid_file(agent_dir, process.pid)
        
        logging.info(f"✅ Launch command sent for {agent_name} (PID: {process.pid})")
        
    except Exception as e:
        logging.error(f"❌ Failed to launch {agent_name}: {e}")


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
    """Main execution for the Ender agent - terminates targets then launches outputs."""
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    
    try:
        source_agents: List[str] = config.get('source_agents', [])
        # Backward compatibility: support legacy 'target_agents' key from older .flw files
        if not source_agents:
            source_agents = config.get('target_agents', [])
            if source_agents:
                logging.warning("⚠️ Using legacy 'target_agents' key. Please update your flow file to use 'source_agents'.")
        output_agents: List[str] = config.get('output_agents', [])

        if not source_agents and not output_agents:
            logging.error("❌ No source or output agents configured.")
            logging.info("💡 Connect agents to Ender on the canvas.")
            return  # Will trigger finally block

        # --- AUTO-CORRECTION & DISCOVERY ---
        # 1. Fix potential configuration errors (remove Cleaner from sources)
        corrected_sources = []
        for agent in source_agents:
            if 'cleaner' in agent.lower():
                logging.warning(f"⚠️ Auto-correcting: Removing '{agent}' from Sources.")
            else:
                corrected_sources.append(agent)
        source_agents = corrected_sources

        # 2. Auto-Discover all Cleaner agents in the pool
        # Ender should always launch any Cleaner present in the current session.
        try:
            pool_path = get_pool_path()
            if os.path.exists(pool_path):
                seen_outputs = set(output_agents)
                for item in os.listdir(pool_path):
                    # Check for cleaner folders (e.g., cleaner_1)
                    if item.lower().startswith('cleaner_') and os.path.isdir(os.path.join(pool_path, item)):
                        # Add to outputs if not already present
                        if item not in seen_outputs:
                            logging.info(f"✨ Auto-Discovered Cleaner: '{item}' -> Adding to Outputs")
                            output_agents.append(item)
                            seen_outputs.add(item)
        except Exception as e:
            logging.error(f"⚠️ Error during auto-discovery: {e}")
        # -----------------------------------
        
        logging.info("💀 ENDER AGENT STARTED")
        logging.info(f"📁 Pool path: {get_pool_path()}")
        if source_agents:
            logging.info(f"🎯 Source agents to terminate: {source_agents}")
        if output_agents:
            logging.info(f"📋 Output agents to trigger: {output_agents}")

        logging.info("=" * 60)

        # 1. Terminate source agents
        if source_agents:
            logging.info("💀 INITIATING IMMEDIATE TERMINATION SEQUENCE...")
            terminated_count = 0
            skipped_count = 0

            for agent in source_agents:
                logging.info(f"\n🎯 Processing: {agent}")
                if terminate_agent(agent):
                    terminated_count += 1
                else:
                    skipped_count += 1

            logging.info(f"💀 TERMINATION COMPLETE: {terminated_count} terminated, {skipped_count} already stopped.")
        
        logging.info("=" * 60)

        # 2. Launch Outputs (e.g., Cleaner)
        if output_agents:
            logging.info("🚀 TRIGGERING OUTPUT AGENTS...")
            for out_agent in output_agents:
                launch_agent(out_agent)
                
        logging.info("==" * 30)
        logging.info("👋 Ender agent exiting.")
        
    except Exception as e:
        logging.error(f"❌ Error in Ender agent: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()

