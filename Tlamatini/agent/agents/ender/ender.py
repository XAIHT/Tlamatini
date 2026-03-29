# Ender Agent - No LLM, deterministic agent terminator
# This agent terminates all agents listed in target_agents when triggered.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., ender_1, ender_2).
# Target agents (agents to kill) should be referenced with their cardinal numbers.
# source_agents are graphical connections only (never killed, never started).
# output_agents are agents to launch after killing (typically Cleaners).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import yaml
import logging
import psutil
import subprocess
import time
from typing import Dict, List

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., ender_1 -> ender_1.log)
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


def is_flowbacker_agent(agent_name: str) -> bool:
    """Return True when the provided agent name refers to FlowBacker."""
    normalized_name = (agent_name or "").strip().lower().replace("-", "_")
    return normalized_name == "flowbacker" or normalized_name.startswith("flowbacker_")


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


def terminate_agent(agent_name: str) -> str:
    """
    Terminate an agent's process(es) using kill signal.
    Returns one of:
    - "terminated": all matching processes were terminated or already ended
    - "not_running": no matching process was found
    - "failed": one or more matching processes could not be terminated
    """
    processes = find_agent_processes(agent_name)
    
    if not processes:
        logging.info(f"⏭️ Agent '{agent_name}' is not running, skipping.")
        return "not_running"
    
    terminated = False
    all_resolved = True
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
            all_resolved = False
        except Exception as e:
            logging.error(f"❌ Error terminating '{agent_name}': {e}")
            all_resolved = False
    
    if terminated and all_resolved:
        return "terminated"

    return "failed"


def clear_reanimation_assets(agent_name: str) -> int:
    """
    Delete any reanimation assets for a target agent after Ender resolves it.

    Reanimation assets follow the shared `reanim*` naming convention
    (for example: reanim.pos, reanim.counter, reanim_<source>.pos).
    """
    agent_dir = get_agent_directory(agent_name)
    if not os.path.isdir(agent_dir):
        logging.info(
            f"ℹ️ Agent directory missing while clearing reanimation assets for '{agent_name}', skipping."
        )
        return 0

    removed = 0
    try:
        for filename in os.listdir(agent_dir):
            if not filename.startswith("reanim"):
                continue

            asset_path = os.path.join(agent_dir, filename)
            if not os.path.isfile(asset_path):
                continue

            try:
                os.remove(asset_path)
                removed += 1
                logging.info(f"🧹 Cleared reanimation asset for '{agent_name}': {filename}")
            except Exception as e:
                logging.warning(f"⚠️ Could not delete reanimation asset '{asset_path}': {e}")
    except Exception as e:
        logging.warning(f"⚠️ Could not inspect reanimation assets for '{agent_name}': {e}")
        return removed

    if removed == 0:
        logging.info(f"💾 No reanimation assets to clear for '{agent_name}'.")

    return removed


def _write_pid_file(agent_dir: str, pid: int):
    """Write the PID to agent.pid in the agent directory."""
    pid_file = os.path.join(agent_dir, "agent.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(str(pid))
        logging.info(f"   📝 PID file created: {pid_file} (PID: {pid})")
    except Exception as e:
        logging.error(f"   ❌ Failed to write PID file: {e}")


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
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    
    try:
        # target_agents = agents to KILL; output_agents = agents to START (Cleaners)
        # source_agents = graphical connections only (never killed, never started)
        kill_agents: List[str] = config.get('target_agents', [])
        # Backward compatibility: support legacy flows where source_agents was the kill list
        if not kill_agents:
            kill_agents = config.get('source_agents', [])
            if kill_agents:
                logging.warning("⚠️ Using legacy 'source_agents' as kill list. Please update your flow to use 'target_agents'.")
        output_agents: List[str] = config.get('output_agents', []) or []

        if not kill_agents and not output_agents:
            logging.error("❌ No target or output agents configured.")
            logging.info("💡 Connect agents to Ender on the canvas.")
            return  # Will trigger finally block

        # --- AUTO-CORRECTION & DISCOVERY ---
        # 1. Fix potential configuration errors (remove Cleaner from kill targets)
        corrected_kills = []
        for agent in kill_agents:
            if 'cleaner' in agent.lower():
                logging.warning(f"⚠️ Auto-correcting: Removing '{agent}' from kill targets.")
            else:
                corrected_kills.append(agent)
        kill_agents = corrected_kills

        # 2. Auto-discover Cleaner agents only for legacy flows with no explicit outputs.
        # If Ender already has outputs configured, respect that wiring and do not add
        # Cleaner in parallel. This is critical for FlowBacker -> Cleaner chains because
        # Cleaner would otherwise delete logs before the backup copy completes.
        try:
            pool_path = get_pool_path()
            if output_agents:
                if any(is_flowbacker_agent(agent) for agent in output_agents):
                    logging.info(
                        "ℹ️ Skipping Cleaner auto-discovery because FlowBacker is already "
                        "configured as an explicit output."
                    )
                else:
                    logging.info(
                        "ℹ️ Skipping Cleaner auto-discovery because explicit output_agents "
                        "are already configured."
                    )
            elif os.path.exists(pool_path):
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
        if kill_agents:
            logging.info(f"🎯 Target agents to terminate: {kill_agents}")
        if output_agents:
            logging.info(f"📋 Output agents to trigger: {output_agents}")

        logging.info("=" * 60)

        # 1. Terminate target agents (kill list)
        if kill_agents:
            logging.info("💀 INITIATING IMMEDIATE TERMINATION SEQUENCE...")
            terminated_count = 0
            skipped_count = 0
            failed_agents: List[str] = []
            cleared_reanimation_assets = 0

            for agent in kill_agents:
                logging.info(f"\n🎯 Processing: {agent}")
                termination_status = terminate_agent(agent)

                if termination_status == "terminated":
                    terminated_count += 1
                    cleared_reanimation_assets += clear_reanimation_assets(agent)
                elif termination_status == "not_running":
                    skipped_count += 1
                    cleared_reanimation_assets += clear_reanimation_assets(agent)
                else:
                    failed_agents.append(agent)

            logging.info(f"💀 TERMINATION COMPLETE: {terminated_count} terminated, {skipped_count} already stopped.")
            logging.info(f"🧹 Reanimation cleanup complete: {cleared_reanimation_assets} asset(s) removed.")
            if failed_agents:
                logging.warning(
                    f"⚠️ Reanimation cleanup skipped for agents with termination errors: {failed_agents}"
                )
        
        logging.info("=" * 60)

        # 2. Launch Outputs (e.g., Cleaner)
        if output_agents:
            wait_for_agents_to_stop(output_agents)
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
