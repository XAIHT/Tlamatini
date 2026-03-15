# Stopper Agent - Single-threaded pattern-based agent terminator
# This agent monitors source agent log files for configurable patterns
# and terminates those agents when their patterns are detected.
#
# Key Features:
# - Single-threaded: Sequential polling of all source agents in main loop
# - Per-source .pos files: Each source gets its own position file
# - Continuous execution: Runs until the Stopper is killed
# - Supports 1-256 source agents
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., stopper_1, stopper_2).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import psutil
import glob
from typing import List, Dict

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., stopper_1 -> stopper_1.log)
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

PID_FILE = "agent.pid"

# Shutdown flag (single-threaded, checked in main loop)
shutdown_flag = False


def get_pool_path() -> str:
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., monitor_log_1, stopper_2) are here.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pool_dir = os.path.dirname(current_dir)
    
    if not os.path.exists(pool_dir):
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
            int(parts[1])
            return True
        except ValueError:
            return False
    return False


def get_agent_directory(agent_name: str) -> str:
    """Get the full path to an agent's directory."""
    return os.path.join(get_pool_path(), agent_name)


def get_agent_log_path(agent_name: str) -> str:
    """
    Get the log file path for an agent.
    Examples: monitor_log_1 -> pool/monitor_log_1/monitor_log_1.log
    """
    agent_dir = get_agent_directory(agent_name)
    log_file = os.path.join(agent_dir, f"{agent_name}.log")
    return log_file


def get_agent_script_path(agent_name: str) -> str:
    """
    Get the Python script path for an agent.
    Examples: stopper_1 -> pool/stopper_1/stopper.py
    """
    agent_dir = get_agent_directory(agent_name)
    
    if is_deployed_agent(agent_name):
        base_name = '_'.join(agent_name.rsplit('_', 1)[:-1])
    else:
        base_name = agent_name
    
    script_file = os.path.join(agent_dir, f"{base_name}.py")
    if os.path.exists(script_file):
        return script_file
    
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


def get_pos_filename(source_agent: str) -> str:
    """Get the .pos filename for a specific source agent."""
    # Sanitize agent name for filename
    safe_name = source_agent.replace('-', '_').replace(' ', '_')
    return f"reanim_{safe_name}.pos"


def save_pos_file(pos_file: str, offset: int, file_size: int):
    """Save position data to a .pos file."""
    try:
        with open(pos_file, "w", encoding="utf-8") as f:
            yaml.dump({'offset': offset, 'file_size': file_size}, f)
    except Exception as e:
        logging.warning(f"⚠️ Could not save position file {pos_file}: {e}")


def load_pos_file(pos_file: str) -> Dict:
    """Load position data from a .pos file."""
    if not os.path.exists(pos_file):
        return {'offset': 0, 'file_size': -1}
    try:
        with open(pos_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {'offset': 0, 'file_size': -1}
    except Exception as e:
        logging.warning(f"⚠️ Could not load position file {pos_file}: {e}")
        return {'offset': 0, 'file_size': -1}


def cleanup_pos_files():
    """Delete all .pos files when the Stopper agent exits."""
    try:
        pos_files = glob.glob("reanim_*.pos")
        for pos_file in pos_files:
            try:
                os.remove(pos_file)
                logging.info(f"🗑️ Deleted position file: {pos_file}")
            except Exception as e:
                logging.warning(f"⚠️ Could not delete {pos_file}: {e}")
        logging.info(f"🧹 Cleaned up {len(pos_files)} position file(s)")
    except Exception as e:
        logging.error(f"❌ Error cleaning up position files: {e}")


def check_log_for_pattern(log_path: str, offset: int, pattern: str, last_size: int) -> tuple:
    """
    Check a log file for a pattern string starting from offset.
    Handles log files that don't exist, are truncated, or decrease in size.
    
    Returns: (pattern_found, new_offset, matched_line, new_file_size)
    """
    if not os.path.exists(log_path):
        return False, 0, None, -1
    
    try:
        current_size = os.path.getsize(log_path)
        
        # Detect file truncation/recreation
        if current_size < offset or last_size == -1 or current_size < last_size:
            if last_size == -1:
                logging.info(f"📁 Log file appeared: {log_path}")
            elif current_size < last_size:
                logging.info(f"🔄 Log file truncated: {log_path}")
            offset = 0
        
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()
        
        if pattern in new_content:
            for line in new_content.split('\n'):
                if pattern in line:
                    return True, new_offset, line.strip(), current_size
        
        return False, new_offset, None, current_size
    
    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return False, offset, None, last_size


def find_agent_processes(agent_name: str) -> List[psutil.Process]:
    """
    Find all processes associated with an agent.
    Returns a list of psutil.Process objects.
    """
    processes = []
    script_path = get_agent_script_path(agent_name)
    script_name = os.path.basename(script_path)
    agent_dir = get_agent_directory(agent_name)
    
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
                cmdline_check = cmdline_str.lower() if is_windows else cmdline_str
                cwd_check = proc_cwd.lower() if is_windows else proc_cwd
                
                cmdline_dir_match = agent_dir_normalized in cmdline_check
                cmdline_script_match = (script_name_normalized in cmdline_check and 
                                       agent_name_normalized in cmdline_check)
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
            
            proc.terminate()
            
            try:
                proc.wait(timeout=5)
                logging.info(f"✅ Agent '{agent_name}' (PID: {pid}) terminated gracefully.")
                terminated = True
            except psutil.TimeoutExpired:
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


def check_source_agent(source_agent: str, pattern: str, index: int,
                       pos_states: Dict[str, Dict]) -> None:
    """
    Check a single source agent's log file for a pattern (one-shot check).
    Called sequentially from the main loop each poll cycle.
    """
    pos_file = get_pos_filename(source_agent)
    log_path = get_agent_log_path(source_agent)

    # Get or initialize state for this source
    if source_agent not in pos_states:
        pos_data = load_pos_file(pos_file)
        pos_states[source_agent] = {
            'offset': pos_data.get('offset', 0),
            'file_size': pos_data.get('file_size', -1),
        }

    state = pos_states[source_agent]

    try:
        pattern_found, new_offset, matched_line, new_file_size = check_log_for_pattern(
            log_path, state['offset'], pattern, state['file_size']
        )

        state['offset'] = new_offset
        state['file_size'] = new_file_size

        # Save position after each check
        save_pos_file(pos_file, new_offset, new_file_size)

        if pattern_found:
            logging.info(f"🚨 [{index}]: PATTERN DETECTED in '{source_agent}': {matched_line}")
            logging.info(f"🛑 [{index}]: Terminating agent '{source_agent}'...")
            terminate_agent(source_agent)
            # Continue monitoring - agent may restart and need to be stopped again

    except Exception as e:
        logging.error(f"❌ [{index}] error checking '{source_agent}': {e}")


def write_pid_file():
    """Write PID file for LED indicator support."""
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    """Remove PID file on exit."""
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
    """Main execution for the Stopper agent - single-threaded sequential monitoring."""
    config = load_config()

    # Write PID file immediately
    write_pid_file()

    try:
        source_agents: List[str] = config.get('source_agents', [])
        patterns: List[str] = config.get('patterns', [])
        output_agents: List[str] = config.get('output_agents', [])
        poll_interval: int = config.get('poll_interval', 1)  # Default 1s

        # Validate configuration
        if not source_agents:
            logging.error("❌ No source agents configured.")
            logging.info("💡 Connect agents to Stopper's input on the canvas.")
            return

        if not patterns:
            logging.error("❌ No patterns configured.")
            logging.info("💡 Configure patterns in the Stopper's config dialog.")
            return

        if len(source_agents) != len(patterns):
            logging.error(f"❌ Configuration error: {len(source_agents)} source agents but {len(patterns)} patterns.")
            logging.error("💡 Each source agent must have exactly one corresponding pattern.")
            logging.error(f"   Source agents: {source_agents}")
            logging.error(f"   Patterns: {patterns}")
            return

        logging.info("🛑 STOPPER AGENT STARTED")
        logging.info(f"📁 Pool path: {get_pool_path()}")
        logging.info(f"👀 Monitoring {len(source_agents)} source agent(s)")
        logging.info(f"⏱️ Poll interval: {poll_interval}s")
        if output_agents:
            logging.info(f"📤 Output agents (for autoconfiguration): {output_agents}")

        # Log each source-pattern pair
        for i, (src, pat) in enumerate(zip(source_agents, patterns)):
            logging.info(f"   [{i+1}] {src} → pattern: '{pat}'")

        logging.info("=" * 60)

        # State for per-source position tracking
        pos_states: Dict[str, Dict] = {}

        logging.info(f"✅ Monitoring {len(source_agents)} source(s) sequentially (single-threaded)")
        logging.info("=" * 60)

        # Single-threaded main loop: check all sources each cycle
        while True:
            for i, (source, pattern) in enumerate(zip(source_agents, patterns)):
                check_source_agent(source, pattern, i + 1, pos_states)

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logging.info("\n⛔ Stopper agent stopped by user.")
    except Exception as e:
        logging.error(f"❌ Stopper agent error: {e}")
        raise
    finally:
        # Cleanup
        logging.info("🧹 Cleaning up...")
        cleanup_pos_files()
        remove_pid_file()
        logging.info("👋 Stopper agent exiting.")


if __name__ == "__main__":
    main()
