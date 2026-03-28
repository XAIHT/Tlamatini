# AND Agent - Deterministic AND gate logic
# Monitors two source log files for specific patterns.
# Raises target agents only if BOTH patterns are detected (latched behavior).

import os
import sys
import time
import yaml
import logging
import subprocess
import psutil
from typing import Dict, Optional, Tuple

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

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

REANIM_FILE = "reanim.pos"

def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
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

def get_template_agents_path() -> str:
    """Get the template agents directory path."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
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
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return True
    return False

def get_agent_directory(agent_name: str) -> str:
    if is_deployed_agent(agent_name):
        return os.path.join(get_pool_path(), agent_name)
    else:
        return os.path.join(get_template_agents_path(), agent_name)

def get_agent_log_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    return os.path.join(agent_dir, f"{agent_name}.log")

def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    if is_deployed_agent(agent_name):
        base_name = '_'.join(agent_name.rsplit('_', 1)[:-1])
    else:
        base_name = agent_name
    return os.path.join(agent_dir, f"{base_name}.py")

def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"❌ Error loading config {path}: {e}")
        sys.exit(1)

def save_reanim_offsets(offsets: Dict[str, int]):
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            yaml.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not save reanimation offsets: {e}")

def load_reanim_offsets() -> Dict[str, int]:
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception:
        return {}

def check_log_for_pattern(log_path: str, offset: int, pattern: str, file_sizes: Dict[str, int]) -> Tuple[bool, int, Optional[str]]:
    """
    Check a log file for a configurable pattern string starting from offset.
    Smart polling that handles:
    - Log files that don't exist initially (waits for appearance)
    - Log files that are truncated/recreated (resets offset to 0)
    - Log files that decrease in size (treats as new file)
    
    Args:
        log_path: Path to the log file
        offset: Current read offset
        pattern: Pattern string to search for
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
        # 1. File size decreased (truncated or recreated with less content)
        # 2. File appeared after being absent (last_known_size was -1)
        # 3. Current offset is beyond file size (stale offset from reanim.pos)
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
    script_path = get_agent_script_path(agent_name)
    script_name = os.path.basename(script_path)
    agent_dir = get_agent_directory(agent_name)
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline:
                cmdline_str = ' '.join(cmdline)
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

def get_python_command() -> list:
    """Get the command to run a Python script."""
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
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    
    try:
        # Inputs
        source_1 = config.get('source_agent_1')
        pattern_1 = config.get('pattern_1', 'EVENT DETECTED')
        
        source_2 = config.get('source_agent_2')
        pattern_2 = config.get('pattern_2', 'EVENT DETECTED')
        
        # Outputs
        target_agents = config.get('target_agents', [])
        poll_interval = config.get('poll_interval', 1)  # Default 1s
        
        if not source_1 and not source_2:
            logging.warning("⚠️ No source agents configured. AND Agent acts as false.")
        
        logging.info("🔥 AND AGENT STARTED (Cyan)")
        if source_1:
            logging.info(f"👀 Input 1: {source_1} (Pattern: '{pattern_1}')")
        if source_2:
            logging.info(f"👀 Input 2: {source_2} (Pattern: '{pattern_2}')")
        logging.info(f"🎯 Targets: {target_agents}")
        
        offsets = load_reanim_offsets()
        
        # Initialize file size tracking for smart polling
        # -1 means file hasn't been seen yet (waiting for appearance)
        file_sizes: Dict[str, int] = {}

        # Latches
        found_1_latch = False
        found_2_latch = False

        # Initialize offsets
        sources = []
        if source_1:
            sources.append(source_1)
        if source_2:
            sources.append(source_2)
        
        for src in sources:
            if src not in offsets:
                log_path = get_agent_log_path(src)
                if os.path.exists(log_path):
                    # Start from beginning to catch events that happened before startup
                    offsets[src] = 0
                    file_sizes[log_path] = os.path.getsize(log_path)
                else:
                    # Log file may not exist yet (source agent hasn't started)
                    # This is normal - just initialize offset to 0 and wait silently
                    offsets[src] = 0
                    file_sizes[log_path] = -1

        poll_count = 0
        while True:
            poll_count += 1
            # Check Source 1
            if source_1:
                log_path_1 = get_agent_log_path(source_1)
                found_1, new_off_1, line_1 = check_log_for_pattern(log_path_1, offsets.get(source_1, 0), pattern_1, file_sizes)
                offsets[source_1] = new_off_1
                if found_1:
                    logging.info(f"✅ Input 1 Triggered: {source_1} - {line_1}")
                    found_1_latch = True

            # Check Source 2
            if source_2:
                log_path_2 = get_agent_log_path(source_2)
                found_2, new_off_2, line_2 = check_log_for_pattern(log_path_2, offsets.get(source_2, 0), pattern_2, file_sizes)
                offsets[source_2] = new_off_2
                if found_2:
                    logging.info(f"✅ Input 2 Triggered: {source_2} - {line_2}")
                    found_2_latch = True

            # Gate Logic
            # Only trigger if BOTH are true (latched)
            # If one source is missing, treat it as False? Or ignore?
            # Standard AND: All inputs must be True.
            
            ready_to_fire = False
            
            if source_1 and source_2:
                if found_1_latch and found_2_latch:
                    ready_to_fire = True
            elif source_1 and not source_2:
                # If only 1 input configured, act as buffer? Or stays false because source_2 is null?
                # User asked for 2 inputs. If 1 is missing, it's not an AND of 2. 
                # Assuming safe to ignore if not configured, but strictly it waits for both.
                # If unmatched, it waits forever.
                pass
            
            if ready_to_fire:
                logging.info("🚨 AND GATE TRIGGERED, EVENT DETECTED (Both inputs satisfied)")
                
                wait_for_agents_to_stop(target_agents)
                for target in target_agents:
                    logging.info(f"🚀 Starting target '{target}'...")
                    start_agent(target)
                
                # Reset latches after firing? 
                # Usually event correlation implies "Event A happened AND Event B happened -> Action".
                # Then reset to wait for new pair.
                found_1_latch = False
                found_2_latch = False
                logging.info("🔄 Latches reset. Waiting for new events.")
            
            # Heartbeat logging every 10 polls to show agent is alive
            if poll_count % 10 == 0:
                src_status = []
                if source_1:
                    log_path_1 = get_agent_log_path(source_1)
                    exists_1 = os.path.exists(log_path_1)
                    latch_1 = "🔒" if found_1_latch else "⬜"
                    src_status.append(f"{source_1}:{'✓' if exists_1 else '?'}{latch_1}")
                if source_2:
                    log_path_2 = get_agent_log_path(source_2)
                    exists_2 = os.path.exists(log_path_2)
                    latch_2 = "🔒" if found_2_latch else "⬜"
                    src_status.append(f"{source_2}:{'✓' if exists_2 else '?'}{latch_2}")
                logging.info(f"💓 Heartbeat #{poll_count} - Polling [{', '.join(src_status)}]")
            
            save_reanim_offsets(offsets)
            time.sleep(poll_interval)
            
    except KeyboardInterrupt:
        logging.info("⛔ AND agent stopped.")
    except Exception as e:
        logging.error(f"❌ Error: {e}")
        raise
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()

if __name__ == "__main__":
    main()
