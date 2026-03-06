# Scper Agent - Deterministic agent to send/receive files via SCP
# Connects to a remote host and transfers a file.
# On SUCCESS: triggers downstream agents
# On FAILURE: logs failure detail in one line, does NOT trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
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

def get_pool_path() -> str:
    """Get the pool directory path where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)

    if os.path.basename(grandparent) == 'pools':
        return parent

    if os.path.basename(parent) == 'pools':
        return parent

    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
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
    """Start a downstream agent."""
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

        # Write PID file for fast status checking
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


def validate_windows_path(path: str) -> bool:
    """Validate that a path looks like a Windows path."""
    # Matches: C:\..., D:\..., \\server\share, or relative paths with backslashes
    if re.match(r'^[A-Za-z]:\\', path):
        return True
    if path.startswith('\\\\'):
        return True
    # Also accept forward-slash Windows paths like C:/Users/...
    if re.match(r'^[A-Za-z]:/', path):
        return True
    return False


def validate_linux_path(path: str) -> bool:
    """Validate that a path looks like a Linux/Unix path."""
    # Matches: /home/..., /tmp/..., ~/..., or relative paths with forward slashes
    if path.startswith('/'):
        return True
    if path.startswith('~'):
        return True
    return False


def execute_scp(user: str, ip: str, file_path: str, direction: str) -> bool:
    """
    Transfer a file to/from a remote host via SCP.
    direction='send': local file -> remote host
    direction='receive': remote file -> local host
    Returns True on success (exit code 0), False on failure.
    Requires pre-configured SSH keys for passwordless authentication.
    """
    if not ip or not ip.strip():
        logging.error("❌ No IP address specified.")
        return False

    if not file_path or not file_path.strip():
        logging.error("❌ No file path specified.")
        return False

    direction = (direction or 'send').strip().lower()
    if direction not in ('send', 'receive'):
        logging.error(f"❌ Invalid direction: {direction}. Must be 'send' or 'receive'.")
        return False

    file_path = file_path.strip()

    # Validate path structure based on direction
    if direction == 'send':
        if not validate_windows_path(file_path):
            logging.error(f"❌ Invalid path for 'send': expected a Windows-like path, got: {file_path}")
            return False
    else:  # receive
        if not validate_linux_path(file_path):
            logging.error(f"❌ Invalid path for 'receive': expected a Linux-like path, got: {file_path}")
            return False

    # Build target: user@ip if user is provided, otherwise just ip
    target = f"{user.strip()}@{ip.strip()}" if user and user.strip() else ip.strip()

    try:
        if direction == 'send':
            # Send local file to remote: scp <local_file> user@ip:<remote_dest>
            # Remote destination defaults to home directory
            cmd = ['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
                   file_path, f"{target}:"]
            logging.info(f"📤 Sending file '{file_path}' to {target}...")
        else:
            # Receive remote file to local: scp user@ip:<remote_file> <local_dest>
            # Local destination defaults to current directory
            cmd = ['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
                   f"{target}:{file_path}", '.']
            logging.info(f"📥 Receiving file '{file_path}' from {target}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        # Log stdout if present
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logging.info(f"   [stdout] {line}")

        # Log stderr if present
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    logging.warning(f"   [stderr] {line}")

        if result.returncode == 0:
            logging.info(f"✅ SCP transfer completed with exit code: {result.returncode}")
            return True
        else:
            logging.error(f"❌ SCP transfer failed with exit code: {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logging.error("❌ SCP transfer timed out (300s limit)")
        return False
    except Exception as e:
        logging.error(f"❌ SCP transfer error: {e}")
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

    execution_success = False

    try:
        # Configuration
        user = config.get('user', '')
        ip = config.get('ip', '')
        file_path = config.get('file', '')
        direction = config.get('direction', 'send')
        target_agents = config.get('target_agents', [])

        logging.info("📋 SCPER AGENT STARTED")
        logging.info(f"👤 User: {user}")
        logging.info(f"🌐 Remote IP: {ip}")
        logging.info(f"📁 File: {file_path}")
        logging.info(f"🔄 Direction: {direction}")
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info("=" * 60)

        # Execute SCP transfer
        execution_success = execute_scp(user, ip, file_path, direction)

        # Log the result
        if execution_success:
            logging.info("SCP TRANSFER SUCCESS")
        else:
            logging.error("SCP TRANSFER FAILED")

        logging.info("=" * 60)

        # Trigger downstream agents ONLY on success
        if execution_success:
            total_triggered = 0
            if target_agents:
                logging.info(f"🚀 SCP succeeded - triggering {len(target_agents)} downstream agents...")
                for target in target_agents:
                    logging.info(f"   ► Triggering: {target}")
                    if start_agent(target):
                        total_triggered += 1
                logging.info(f"✨ Triggered {total_triggered}/{len(target_agents)} agents.")
            else:
                logging.info("ℹ️ No downstream agents configured.")
        else:
            logging.info("⛔ SCP failed - NOT triggering downstream agents.")

        logging.info(f"🏁 Scper agent finished. Result: {'SUCCESS' if execution_success else 'FAILED'}")

    except Exception as e:
        logging.error(f"❌ Scper agent error: {e}")
        logging.error("SCP TRANSFER FAILED")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0 if execution_success else 1)


if __name__ == "__main__":
    main()
