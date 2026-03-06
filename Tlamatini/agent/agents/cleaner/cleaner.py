# Cleaner Agent - Cleans up logs/pids of target agents and triggers restarts
# This agent is designed to run AFTER an Ender agent.
# It deletes .log and .pid files for target agents but PRESERVES .pos files.
# Then it triggers execution of agents connected to its output.

import os
import sys
import yaml
import time
import logging
import subprocess
from typing import List, Dict

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Setup logging
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
    
    if sys.platform.startswith('win'):
        # Check for bundled python.exe next to main executable
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']
    
    return ['python3']


def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
    # Get directory of THIS script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Pool dir is parent
    pool_dir = os.path.dirname(current_dir)
    
    if not os.path.exists(pool_dir):
        # Fallback mechanism
        if getattr(sys, 'frozen', False):
            return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
        return os.path.join(os.path.dirname(os.path.dirname(current_dir)), 'pools')
        
    return pool_dir


def load_config(path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        return {}
    except yaml.YAMLError as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        return {}


def get_agent_directory(agent_name: str) -> str:
    """Get the full path to an agent's directory."""
    pool_path = get_pool_path()
    
    # Check exact match first
    path = os.path.join(pool_path, agent_name)
    if os.path.exists(path):
        return path
        
    # Check underscore version (frontend IDs often use hyphens, backend uses underscores)
    normalized_name = agent_name.replace('-', '_')
    path = os.path.join(pool_path, normalized_name)
    if os.path.exists(path):
        return path
        
    # Return original assumption if neither exists
    return os.path.join(pool_path, agent_name)


def clean_agent_files(agent_name: str):
    """
    Delete .log and .pid files for the specified agent.
    Preserve .pos files.
    """
    agent_dir = get_agent_directory(agent_name)
    if not os.path.exists(agent_dir):
        logging.warning(f"⚠️ Agent directory not found: {agent_dir}")
        return

    logging.info(f"🧹 CLeaning files for agent: {agent_name}")
    
    # Let's list files and delete matching extensions
    try:
        for filename in os.listdir(agent_dir):
            file_path = os.path.join(agent_dir, filename)
            
            if filename.endswith(".log"):
                try:
                    os.remove(file_path)
                    logging.info(f"   🗑️ Deleted log: {filename}")
                except Exception as e:
                    logging.error(f"   ❌ Failed to delete {filename}: {e}")
            
            elif filename.endswith(".pid"):
                try:
                    os.remove(file_path)
                    logging.info(f"   🗑️ Deleted pid: {filename}")
                except Exception as e:
                    logging.error(f"   ❌ Failed to delete {filename}: {e}")
            
            elif filename.endswith(".pos"):
                logging.info(f"   💾 Preserved pos: {filename}")
                
    except Exception as e:
        logging.error(f"❌ Error accessing directory {agent_dir}: {e}")

def _write_pid_file(agent_dir: str, pid: int):
    """Write the PID to agent.pid in the agent directory."""
    pid_file = os.path.join(agent_dir, "agent.pid")
    try:
        with open(pid_file, "w") as f:
            f.write(str(pid))
        logging.info(f"   📝 PID file created: {pid_file} (PID: {pid})")
    except Exception as e:
        logging.error(f"   ❌ Failed to write PID file: {e}")

def execute_agent(agent_name: str):
    """Execute a target agent."""
    agent_dir = get_agent_directory(agent_name)
    
    # Determine script name (remove cardinal suffix for base script name)
    # e.g. starter_1 -> starter.py OR monitor-log-1 -> monitor_log.py
    
    base_name = agent_name
    # Strip suffix if present (e.g. -1 or _1)
    if '-' in base_name and base_name.rsplit('-', 1)[1].isdigit():
        base_name = base_name.rsplit('-', 1)[0]
    elif '_' in base_name and base_name.rsplit('_', 1)[1].isdigit():
        base_name = base_name.rsplit('_', 1)[0]
        
    # Valid script names usually use underscores (python modules)
    script_name_candidates = [
        f"{base_name}.py",
        f"{base_name.replace('-', '_')}.py",
        f"{base_name.replace('_', '-')}.py",
        f"{agent_name}.py" # Fallback to exact
    ]
    
    script_path = None
    for candidate in script_name_candidates:
        candidate_path = os.path.join(agent_dir, candidate)
        if os.path.exists(candidate_path):
            script_path = candidate_path
            break
            
    if not script_path:
        # Fallback to default constructed path for logging error
        script_path = os.path.join(agent_dir, f"{base_name}.py")
    
    if not os.path.exists(script_path):
        logging.error(f"❌ Script not found: {script_path}")
        return

    logging.info(f"🚀 Starting agent: {agent_name}...")
    try:
        # Launch independently using robust python command
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")
        
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # Write PID for the started agent
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
    logging.info("🧼 CLEANER AGENT STARTED")
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    
    try:
        # 1. Clean Targets (from Ender connection)
        # The config should have 'agents_to_clean' populated by the backend when connecting Ender->Cleaner
        agents_to_clean = config.get('agents_to_clean', [])
        
        if not agents_to_clean:
            logging.warning("⚠️ No agents configured to clean.")
        else:
            logging.info(f"📋 Agents to clean: {agents_to_clean}")
            for agent in agents_to_clean:
                clean_agent_files(agent)
                
        # 2. Restart/Start Output Agents
        # The config should have 'output_agents' populated by backend
        output_agents = config.get('output_agents', [])
        
        if not output_agents:
            logging.warning("⚠️ No output agents configured to start.")
        else:
            logging.info(f"📋 Agents to start: {output_agents}")
            for agent in output_agents:
                execute_agent(agent)
                
        logging.info("✅ Cleaning and restarting sequence complete.")
        # Cleaner doesn't need to stay running. It does its job and exits.
        
    except Exception as e:
        logging.error(f"❌ Error in Cleaner agent: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        import time
        time.sleep(0.4)
        remove_pid_file()

if __name__ == "__main__":
    main()

