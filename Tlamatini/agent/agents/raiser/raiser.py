# Raiser Agent - No LLM, deterministic event-driven agent launcher
# This agent monitors log files of source agents for a configurable pattern string
# and starts target agents when the pattern is detected.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., raiser_1, raiser_2).
# Source and target agents should also be referenced with their cardinal numbers.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess
import psutil
from typing import List, Dict, Optional, Tuple

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., raiser_1 -> raiser_1.log)
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

REANIM_FILE = "reanim.pos"


def get_application_path() -> str:
    """Get the base application path, handling frozen and non-frozen modes."""
    if getattr(sys, 'frozen', False):
        # Frozen mode (PyInstaller): executable directory
        return os.path.dirname(sys.executable)
    else:
        # Development mode: navigate up to find the agent directory
        # This script could be in:
        # - agents/raiser/raiser.py (template)
        # - agents/pool/raiser_1/raiser.py (deployed instance)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if we're in pool directory
        if 'pool' in current_dir:
            # We're in agents/pool/raiser_X/ -> go up to agents/
            return os.path.dirname(os.path.dirname(current_dir))
        else:
            # We're in agents/raiser/ -> go up to agents/
            return os.path.dirname(current_dir)


def get_pool_path() -> str:
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., monitor_log_1, raiser_2) are here.
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


def get_python_command():
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

def get_template_agents_path() -> str:
    """
    Get the template agents directory path (non-deployed agents).
    Template agents without cardinals (e.g., monitor_log, raiser) are here.
    """
    if getattr(sys, 'frozen', False):
        # Frozen mode: templates are in <exe_dir>/agents/
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
        # Development mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if we're in pool directory
        if 'pool' in current_dir:
            # We're in agents/pool/raiser_X/ -> templates are in agents/
            return os.path.dirname(os.path.dirname(current_dir))
        else:
            # We're in agents/raiser/ -> templates are in agents/
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


def get_agent_log_path(agent_name: str) -> str:
    """
    Get the log file path for an agent.
    The log file is named after the agent's directory name (with cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log_1.log
    - monitor_netstat -> agents/monitor_netstat/monitor_netstat.log
    """
    agent_dir = get_agent_directory(agent_name)
    
    # Log file uses the full directory name (including cardinal)
    log_file = os.path.join(agent_dir, f"{agent_name}.log")
    return log_file


def get_agent_script_path(agent_name: str) -> str:
    """
    Get the Python script path for an agent.
    The script is named after the agent's base name (without cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log.py
    - raiser_2 -> pool/raiser_2/raiser.py
    """
    agent_dir = get_agent_directory(agent_name)
    
    # Get base name without cardinal for script file name
    if is_deployed_agent(agent_name):
        # raiser_1 -> raiser
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


def save_reanim_offsets(offsets: Dict[str, int]):
    """Save file offsets for reanimation after restart."""
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            yaml.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not save reanimation offsets: {e}")


def load_reanim_offsets() -> Dict[str, int]:
    """Load saved file offsets for reanimation."""
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not load reanimation offsets: {e}")
        return {}


def check_log_for_pattern(log_path: str, offset: int, patterns: List[str], file_sizes: Dict[str, int]) -> Tuple[bool, int, Optional[str]]:
    """
    Check a log file for any of the configurable patterns starting from offset.
    Smart polling that handles:
    - Log files that don't exist initially (waits for appearance)
    - Log files that are truncated/recreated (resets offset to 0)
    - Log files that decrease in size (treats as new file)
    
    Args:
        log_path: Path to the log file
        offset: Current read offset
        patterns: List of pattern strings to search for (OR logic)
        file_sizes: Dictionary tracking last known file sizes (modified in-place)
    
    Returns: (pattern_found: bool, new_offset: int, matched_line: str or None)
    """
    last_known_size = file_sizes.get(log_path, -1)  # -1 means never seen
    
    if not os.path.exists(log_path):
        # File doesn't exist - reset tracking and wait
        file_sizes[log_path] = -1  # Mark as "waiting for file"
        return False, 0, None  # Reset offset to 0 to catch content when file appears
    
    try:
        current_size = os.path.getsize(log_path)
        
        # Detect file truncation/recreation scenarios:
        if current_size < offset or last_known_size == -1 or current_size < last_known_size:
            if last_known_size == -1:
                logging.info(f"📁 Log file appeared: {log_path}")
            elif current_size < last_known_size:
                logging.info(f"🔄 Log file truncated/recreated: {log_path} ({last_known_size} -> {current_size} bytes)")
            else:
                logging.info(f"🔄 Stale offset detected for {log_path}, resetting")
            offset = 0  # Read from beginning
        
        # Update tracking
        file_sizes[log_path] = current_size
        
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()
        
        # Check for ANY pattern
        for pattern in patterns:
            if pattern in new_content:
                # Find the line containing the pattern
                for line in new_content.split('\n'):
                    if pattern in line:
                        return True, new_offset, line.strip()
        
        return False, new_offset, None
    
    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return False, offset, None


def is_agent_running(agent_name: str) -> Optional[int]:
    """
    Check if an agent is currently running.
    Returns the PID if running, None otherwise.
    
    Uses multiple detection methods for reliability:
    1. Check if agent directory path is in cmdline (case-insensitive on Windows)
    2. Check if script name and agent name are in cmdline
    3. Check if process working directory matches agent directory
    """
    # Get the script path to search for in running processes
    script_path = get_agent_script_path(agent_name)
    script_name = os.path.basename(script_path)
    
    # Also check for the agent directory in cmdline (more reliable)
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
                    return proc.info['pid']
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return None


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
        # Start the agent as a subprocess
        python_cmd = get_python_command()
        cmd = python_cmd + [script_path]
        logging.info(f"   Command: {cmd}")
        
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
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
    """Main loop for the Raiser agent."""
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    
    source_agents: List[str] = config.get('source_agents', [])
    target_agents: List[str] = config.get('target_agents', [])
    
    # Parse patterns (support list or comma-separated string)
    pattern_config = config.get('pattern', 'EVENT DETECTED')
    if isinstance(pattern_config, list):
        patterns = pattern_config
    else:
        patterns = [p.strip() for p in str(pattern_config).split(',') if p.strip()]

    poll_interval: int = config.get('poll_interval', 1)  # Default 1s
    
    if not source_agents:
        logging.error("❌ No source agents configured. Exiting.")
        sys.exit(1)
    
    if not target_agents:
        logging.error("❌ No target agents configured. Exiting.")
        sys.exit(1)
    
    logging.info("🔥 RAISER AGENT STARTED")
    logging.info(f"📁 Pool path: {get_pool_path()}")
    logging.info(f"📁 Template path: {get_template_agents_path()}")
    logging.info(f"👀 Monitoring source agents: {source_agents}")
    logging.info(f"🔍 Patterns to detect: {patterns}")
    logging.info(f"🎯 Target agents to start: {target_agents}")
    logging.info(f"⏱️ Poll interval: {poll_interval}s")
    
    # Log resolved paths for debugging
    for source in source_agents:
        log_path = get_agent_log_path(source)
        logging.info(f"   📄 {source} log: {log_path} (exists: {os.path.exists(log_path)})")
    
    for target in target_agents:
        script_path = get_agent_script_path(target)
        logging.info(f"   🎯 {target} script: {script_path} (exists: {os.path.exists(script_path)})")
    
    logging.info("=" * 60)
    
    # Load saved offsets for reanimation
    offsets = load_reanim_offsets()
    
    # Initialize file size tracking for smart polling
    # -1 means file hasn't been seen yet (waiting for appearance)
    file_sizes: Dict[str, int] = {}
    
    # Initialize offsets for new sources
    for source in source_agents:
        if source not in offsets:
            log_path = get_agent_log_path(source)
            if os.path.exists(log_path):
                # Start from beginning to catch events that happened before startup
                offsets[source] = 0
                file_sizes[log_path] = os.path.getsize(log_path)
                logging.info(f"📍 Initialized offset for {source}: {offsets[source]}")
            else:
                # Log file may not exist yet (source agent hasn't started)
                # This is normal - just initialize offset to 0 and wait silently
                offsets[source] = 0
                file_sizes[log_path] = -1  # Mark as waiting
    
    try:
        while True:
            events_detected = []
            
            # Check each source agent's log file
            for source in source_agents:
                log_path = get_agent_log_path(source)
                current_offset = offsets.get(source, 0)
                
                pattern_found, new_offset, matched_line = check_log_for_pattern(log_path, current_offset, patterns, file_sizes)
                offsets[source] = new_offset
                
                if pattern_found:
                    logging.info(f"🚨 PATTERN DETECTED from '{source}': {matched_line}")
                    events_detected.append(source)
            
            # If any events detected, start target agents
            if events_detected:
                logging.info(f"📢 Events detected from {len(events_detected)} source(s). Checking target agents...")
                
                for target in target_agents:
                    running_pid = is_agent_running(target)
                    
                    if running_pid:
                        logging.info(f"⏭️ Target agent '{target}' already running (PID: {running_pid}), skipping.")
                    else:
                        logging.info(f"🚀 Starting target agent '{target}'...")
                        start_agent(target)
                
                logging.info("=" * 60)
            
            # Save offsets for reanimation
            save_reanim_offsets(offsets)
            
            # Wait before next poll
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logging.info("\n⛔ Raiser agent stopped by user.")
    except Exception as e:
        logging.error(f"❌ Raiser agent error: {e}")
        raise
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()
