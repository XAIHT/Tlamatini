import os
import sys
import time
import yaml
import logging
import json
import subprocess
from typing import TypedDict, Literal, List, Any
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., notifier_1 -> notifier_1.log)
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
NOTIFICATION_FILE = "notification.json"
PID_FILE = "agent.pid"
REANIM_FILE = "reanim.pos"

# Custom handler that flushes immediately
class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = FlushingFileHandler(LOG_FILE_PATH, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

def load_config(path="config.yaml"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("❌ Error: config.yaml not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error loading config: {e}")
        sys.exit(1)

CONFIG = load_config()

# --- Helper Functions ---

def get_python_command() -> List[str]:
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

def get_agent_directory(agent_name: str) -> str:
    # Assuming standard pool structure: .../pools/notifier_1/
    # And other agents are tasks/siblings: .../pools/monitor_log_1/
    # agent_name should be the folder name (e.g. monitor_log_1)
    current_pool_dir = os.path.dirname(os.path.abspath(__file__)) # e.g. .../pools/notifier_1
    pools_root = os.path.dirname(current_pool_dir) # .../pools
    return os.path.join(pools_root, agent_name)

def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    # script name is base name without cardinal: monitor_log_1 -> monitor_log.py
    # Logic copied from starter.py
    if len(agent_name.rsplit('_', 1)) == 2 and agent_name.rsplit('_', 1)[1].isdigit():
        base_name = '_'.join(agent_name.rsplit('_', 1)[:-1])
    else:
        base_name = agent_name
    return os.path.join(agent_dir, f"{base_name}.py")

def start_agent(agent_name: str) -> bool:
    script_path = get_agent_script_path(agent_name)
    agent_dir = get_agent_directory(agent_name)
    
    if not os.path.exists(script_path):
        logging.error(f"❌ Script not found for {agent_name}: {script_path}")
        return False
        
    try:
        cmd = get_python_command() + [script_path]
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        # Write PID for target
        try:
            with open(os.path.join(agent_dir, "agent.pid"), "w") as f:
                f.write(str(process.pid))
        except Exception:
            pass
            
        logging.info(f"✅ Started target agent '{agent_name}' (PID: {process.pid})")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start target {agent_name}: {e}")
        return False

def save_reanim_offset(offsets: dict):
    try:
        with open(REANIM_FILE, "w") as f:
            json.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Could not save reanim offsets: {e}")

def get_reanim_offset() -> dict:
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}

def trigger_frontend_notification(matches: List[str], source_agent: str):
    """Writes a notification file that the frontend polls for."""
    try:
        data = {
            "type": "notifier_alert",
            "agent_id": CURRENT_DIR_NAME, # e.g. notifier_1
            "matches": matches,
            "source_agent": source_agent,
            "timestamp": time.time(),
            "sound_enabled": CONFIG['target'].get('sound_enabled', False),
            "message": f"Detected: {', '.join(matches)} in {source_agent}"
        }
        
        # Write to atomic file then rename to avoid read race conditions?
        # For simplicity, just write JSON. The frontend deletes it after reading.
        with open(NOTIFICATION_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f)
            
        logging.info(f"🔔 Notification file created for: {matches}")
        
    except Exception as e:
        logging.error(f"❌ Failed to create notification file: {e}")

# --- Agent Logic ---

@tool
def check_logs() -> str:
    """Checks input logs for patterns."""
    return "check_logs"

class NotifierState(TypedDict):
    messages: List[Any]
    loop_count: int
    offsets: dict

def agent_node(state: NotifierState):
    # Determine next action. For this focused agent, we essentially just loop check_logs.
    # We can skip LLM invocation for pure pattern matching to save resources/time,
    # OR we can keep it to allow 'smart' detection if needed later.
    # Given requirements: "find/detect certain configurable string patterns" -> Regex/String matching is faster and safer.
    # The prompt implies inheriting structure, but logic can be custom.
    # I will implement the logic inside the tool_node (act) directly or a custom processing node.
    # But to satisfy the "Agent" structure, we'll return a tool call trigger.
    
    return {
        "messages": [ToolMessage(content="Triggering log check", tool_call_id="pseudo_call", name="check_logs")],
        "loop_count": state.get('loop_count', 1) + 1
    }

def tool_node(state: NotifierState):
    offsets = state.get('offsets', {})
    search_strings = [s.strip() for s in CONFIG['target'].get('search_strings', '').split(',') if s.strip()]
    source_agents = CONFIG.get('source_agents', [])
    
    if not source_agents:
        logging.warning("⚠️ No source agents configured to monitor.")
        time.sleep(5)
        return {"messages": [], "offsets": offsets}

    for agent_name in source_agents:
        # Resolve log path: sibling folder
        agent_dir = get_agent_directory(agent_name)
        log_path = os.path.join(agent_dir, f"{agent_name}.log")
        
        if not os.path.exists(log_path):
            continue
            
        current_offset = offsets.get(agent_name, 0)
        
        try:
            file_size = os.path.getsize(log_path)
            if file_size < current_offset:
                current_offset = 0 # Rotated
            
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(current_offset)
                new_content = f.read()
                new_offset = f.tell()
                
                if new_content:
                    # Check for matches
                    matches = []
                    for s in search_strings:
                        if s in new_content:
                            matches.append(s)
                    
                    if matches:
                        logging.critical(f"🚨 DETECTED {matches} in {agent_name}")
                        trigger_frontend_notification(matches, agent_name)
                        
                        # Start Targets
                        targets = CONFIG.get('target_agents', [])
                        for target in targets:
                            start_agent(target)
                            
                        # Shutdown check
                        if CONFIG['target'].get('shutdown_on_match', False):
                            logging.info("🛑 Shutdown on match enabled. Exiting...")
                            # Clean exit
                            remove_pid_file()
                            save_reanim_offset(offsets) # Save logic inside tool node? updating map first
                            sys.exit(0)

                offsets[agent_name] = new_offset
                
        except Exception as e:
            logging.error(f"Error reading log {log_path}: {e}")

    save_reanim_offset(offsets)
    
    interval = CONFIG['target'].get('poll_interval', 2)
    time.sleep(interval)
    
    return {
        "messages": [], # Reset messages
        "offsets": offsets
    }

def router(state: NotifierState) -> Literal["tools", "__end__"]:
    # Always loop
    return "tools"

# Simplified Workflow
workflow = StateGraph(NotifierState)
workflow.add_node("agent", agent_node) # Decides to check
workflow.add_node("tools", tool_node) # Performs check & sleep
workflow.add_edge(START, "tools") # Start directly with check
workflow.add_edge("tools", "tools") # Loop forever

app = workflow.compile()

# PID Management
def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID: {e}")

def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception:
            return

if __name__ == "__main__":
    write_pid_file()
    try:
        logging.info("🔥 NOTIFIER AGENT STARTED")
        offsets = get_reanim_offset()
        app.invoke({"messages": [], "loop_count": 0, "offsets": offsets}, config={"recursion_limit": 100000}) 
    except SystemExit:
        pass
    except Exception as e:
        logging.error(f"❌ CRASH: {e}")
    finally:
        remove_pid_file()
