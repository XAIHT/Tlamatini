# Mover Agent - Deterministic agent to copy/move files
# Triggers: Immediate or Event-based (Source Log)
# Action: Move or Copy files based on patterns

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import shutil
import glob
import subprocess
from typing import List, Dict

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

REANIM_FILE = "reanim.pos"

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
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not load reanimation offsets: {e}")
        return {}

def resolve_log_paths(source_agents: List[str]) -> List[str]:
    """
    Resolves agent names to their log file paths in the pool directory.
    Assumes standard pool structure: .../pool/{agent_name}/{agent_name}.log
    """
    resolved_paths = []
    # Current dir is .../pool/{mover_agent_name}/
    pool_dir = os.path.dirname(os.getcwd()) # Go up one level to pool dir
    
    for agent_name in source_agents:
        if not agent_name:
            continue
        
        # Agent folder name usually matches agent_name (e.g. monitor_log_1)
        # Log file is inside that folder with same name + .log
        log_path = os.path.join(pool_dir, agent_name, f"{agent_name}.log")
        
        if os.path.exists(log_path):
            resolved_paths.append(log_path)
            logging.info(f"🔗 Resolved log path for {agent_name}: {log_path}")
        else:
            logging.warning(f"⚠️ Could not find log file for agent: {agent_name} at {log_path}")
            
    return resolved_paths

def perform_file_operations(operation: str, sources_list: List[str], destination_folder: str):
    """
    Executes the move/copy operation for the given list of source patterns.
    """
    if not os.path.exists(destination_folder):
        try:
            os.makedirs(destination_folder)
            logging.info(f"📁 Created destination folder: {destination_folder}")
        except Exception as e:
            logging.error(f"❌ Failed to create destination folder {destination_folder}: {e}")
            return

    total_success = 0
    total_failed = 0

    for original_pattern in sources_list:
        patterns_to_check = [original_pattern]
        # Enhancement: Treat *.* as * to include items without extensions (common Windows expectation)
        if original_pattern.endswith('*.*'):
             patterns_to_check.append(original_pattern[:-3] + '*')
        
        processed_paths = set()

        for pattern in patterns_to_check:
            # Handle wildcards
            files_found = glob.glob(pattern)
            if not files_found:
                 if pattern == original_pattern: # Only warn if original pattern yielded nothing
                    logging.warning(f"⚠️ No files found for pattern: {pattern}")
                 continue
            
            for file_path in files_found:
                if file_path in processed_paths:
                    continue
                processed_paths.add(file_path)

                filename = os.path.basename(file_path)
                dest_path = os.path.join(destination_folder, filename)
                
                try:
                    if os.path.isdir(file_path):
                        # Directory Operation - overwrite if destination exists
                        if os.path.exists(dest_path):
                            logging.info(f"🔄 Overwriting existing destination: {dest_path}")
                            shutil.rmtree(dest_path)
                        
                        if operation.lower() == 'move':
                            shutil.move(file_path, dest_path)
                            logging.info(f"🚚 Moved Folder: {filename} -> {destination_folder}")
                        else: # Copy
                            shutil.copytree(file_path, dest_path)
                            logging.info(f"📋 Copied Folder: {filename} -> {destination_folder}")
                        total_success += 1

                    elif os.path.isfile(file_path):
                        # File Operation - overwrite if destination exists
                        if os.path.exists(dest_path):
                            logging.info(f"🔄 Overwriting existing file: {dest_path}")
                        
                        if operation.lower() == 'move':
                            shutil.move(file_path, dest_path)
                            logging.info(f"🚚 Moved File: {filename} -> {destination_folder}")
                        else: # Copy
                            shutil.copy2(file_path, dest_path)
                            logging.info(f"📋 Copied File: {filename} -> {destination_folder}")
                        total_success += 1
                
                except Exception as e:
                    logging.error(f"❌ Failed to {operation} {filename}: {e}")
                    total_failed += 1

    logging.info(f"✅ Operation Completed. Success: {total_success}, Failed: {total_failed}")


def check_log_for_event(log_path: str, offset: int, event_string: str) -> tuple:
    if not os.path.exists(log_path):
        return False, offset

    try:
        file_size = os.path.getsize(log_path)
        if file_size < offset:
             offset = 0 # Rotation detected
        
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()

        if event_string in new_content:
            return True, new_offset
        
        return False, new_offset

    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return False, offset

def main():
    config = load_config()
    
    # Configuration
    trigger_mode = config.get('trigger_mode', 'immediate') # 'immediate' or 'event'
    operation = config.get('operation', 'copy') # 'move' or 'copy'
    source_patterns = config.get('source_files', []) # List of file paths/patterns
    source_agents = config.get('source_agents', []) # List of source agents for event triggering
    destination = config.get('destination_folder', '')
    
    target_agents = config.get('target_agents', [])
    trigger_event_string = config.get('trigger_event_string', 'EVENT DETECTED')
    poll_interval = config.get('poll_interval', 5)

    logging.info("🔥 MOVER AGENT STARTED")
    logging.info(f"⚙️ Mode: {trigger_mode}")
    logging.info(f"⚙️ Operation: {operation}")
    logging.info(f"📂 Destination: {destination}")
    logging.info(f"🎯 Targets: {target_agents}")

    # PID Management
    PID_FILE = "agent.pid"
    
    # Write PID file immediately
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")

    try:
        if not destination:
            logging.error("❌ No destination folder configured. Exiting.")
            return  # Will trigger finally block

        if trigger_mode.lower() == 'immediate':
            logging.info("🚀 Executing immediate operation...")
            
            try:
                perform_file_operations(operation, source_patterns, destination)
            except Exception as e:
                logging.error(f"❌ Operation terminated with error: {e}")
                logging.warning("⚠️ Proceeding to downstream agents despite errors...")

            # Trigger downstream agents
            if target_agents:
                logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
                triggered_count = 0
                for target in target_agents:
                    logging.info(f"   ► Triggering: {target}")
                    if start_agent(target):
                        triggered_count += 1
                logging.info(f"✨ Triggered {triggered_count}/{len(target_agents)} agents.")
            else:
                logging.info("ℹ️ No downstream agents configured.")

            logging.info("🏁 Immediate task finished. Exiting.")

        elif trigger_mode.lower() == 'event':
            log_paths = resolve_log_paths(source_agents)
            
            if not log_paths:
                logging.error("❌ No valid source agent logs found for event mode. Exiting.")
                return  # Will trigger finally block
                 
            logging.info(f"👀 Monitoring {len(log_paths)} log(s)")
            logging.info(f"WAITING FOR: '{trigger_event_string}'")

            offsets = load_reanim_offsets()
            
            # Initialize offsets for new logs
            for path in log_paths:
                if path not in offsets:
                    offsets[path] = 0

            while True:
                any_event_triggered = False
                
                for path in log_paths:
                    current_offset = offsets.get(path, 0)
                    event_found, new_offset = check_log_for_event(path, current_offset, trigger_event_string)
                    
                    offsets[path] = new_offset
                    
                    if event_found:
                        logging.info(f"🚨 EVENT DETECTED in {os.path.basename(path)}")
                        any_event_triggered = True

                save_reanim_offsets(offsets)

                if any_event_triggered:
                    logging.info("🚀 Executing operation...")
                    perform_file_operations(operation, source_patterns, destination)
                    
                    # Trigger downstream agents
                    if target_agents:
                        logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
                        for target in target_agents:
                            start_agent(target)
                            
                    logging.info("💤 Waiting for next event...")

                time.sleep(poll_interval)

        else:
            logging.error(f"❌ Unknown trigger mode: {trigger_mode}")

    except KeyboardInterrupt:
        logging.info("\n⛔ Mover agent stopped by user.")
    except Exception as e:
        logging.error(f"❌ Mover agent error: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        # Cleanup PID file
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")


# Helper functions for Agent Triggering (Adapted from Croner)


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

def get_agent_directory(agent_name: str) -> str:
    # agents are in pool dir
    return os.path.join(get_pool_path(), agent_name)

def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    # script name assumption: agent_name.py or base name
    # e.g. "monitor_log_1" -> "monitor_log.py" usually? NO, often "monitor_log_1.py" if deployed?
    # Actually, in Tlamatini, deployed scripts are often named same as folder or base py?
    # Let's check how Croner does it:
    # if deployed: base_name = '_'.join(agent_name.rsplit('_', 1)[:-1]) -> "monitor_log"
    # But files in pool are often just copied? 
    # Let's rely on finding the .py file in the folder.
    
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")
        
    # Try removing ID suffix
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
             return os.path.join(agent_dir, f"{base}.py")
             
    # Fallback to finding any .py that matches?
    return os.path.join(agent_dir, f"{agent_name}.py")

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




if __name__ == "__main__":
    main()
