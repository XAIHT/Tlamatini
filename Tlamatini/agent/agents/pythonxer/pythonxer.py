# Pythonxer Agent - Deterministic agent to execute a Python script
# Validates with Ruff, executes the script, and triggers downstream
# agents ONLY if the script returns True (exit code 0).

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


def validate_with_ruff(script_path: str) -> bool:
    """
    Run Ruff linter on the script. Returns True if no errors, False if errors found.
    Logs warnings but does NOT block execution.
    """
    try:
        result = subprocess.run(
            ['ruff', 'check', script_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logging.warning(f"   [Ruff] {line}")

        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    logging.warning(f"   [Ruff stderr] {line}")

        if result.returncode == 0:
            logging.info("✅ Ruff validation passed - no issues found")
            return True
        else:
            logging.warning(f"⚠️ Ruff found issues (exit code {result.returncode}) - proceeding anyway")
            return False

    except FileNotFoundError:
        logging.warning("⚠️ Ruff is not installed - skipping validation")
        return True
    except subprocess.TimeoutExpired:
        logging.warning("⚠️ Ruff validation timed out - skipping")
        return True
    except Exception as e:
        logging.warning(f"⚠️ Ruff validation error: {e} - skipping")
        return True


def execute_python_script(script_content: str, execute_forked_window: bool = False) -> bool:
    """
    Write the Python script to a temp file and execute it.
    Returns True if exit code == 0, False otherwise.

    If execute_forked_window is True, the script runs in a new console
    window so that stdout/stderr are visible in real time.
    """
    if not script_content or not script_content.strip():
        logging.error("❌ No script content specified to execute.")
        return False

    try:
        script_path = os.path.abspath("temp_script.py")
        logging.info(f"📝 Writing Python script to: {script_path}")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Validate with Ruff (non-blocking)
        logging.info("🔍 Running Ruff validation...")
        validate_with_ruff(script_path)

        # Execute the script
        cmd = get_python_command() + [script_path]

        if execute_forked_window:
            logging.info("🚀 Executing Python script in forked window...")
            return _execute_in_forked_window(cmd, script_path)

        logging.info("🚀 Executing Python script...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
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

        # Check return code
        if result.returncode == 0:
            logging.info(f"✅ Script returned True (exit code: {result.returncode})")
            return True
        else:
            logging.info(f"⛔ Script returned False (exit code: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        logging.error("❌ Script execution timed out (300s limit)")
        return False
    except Exception as e:
        logging.error(f"❌ Script execution error: {e}")
        return False


def _execute_in_forked_window(cmd: list, script_path: str) -> bool:
    """
    Execute a Python script in a new console window and wait for the
    window to be closed.

    Result logic:
      - Script exits 0  → True
      - Script exits !=0 → False
      - User closes the window (X button) → True
        (the exit code file written by the wrapper is used to distinguish
         a script failure from a manual close)
    """
    # File where the wrapper records the real script exit code
    exitcode_file = os.path.abspath("temp_forked_exitcode.txt")

    # Remove stale file from a previous run
    try:
        if os.path.exists(exitcode_file):
            os.remove(exitcode_file)
    except Exception:
        pass

    try:
        if sys.platform.startswith('win'):
            python_exe = cmd[0]
            wrapper_path = os.path.abspath("temp_forked_wrapper.bat")
            # The wrapper:
            #   1. Runs the Python script
            #   2. Saves %ERRORLEVEL% to a file (persists even if window is closed)
            #   3. Prints a summary banner
            #   4. Pauses so the user can read stdout/stderr
            #   5. Exits with the original error level
            with open(wrapper_path, "w", encoding="utf-8") as wf:
                wf.write(f'@"{python_exe}" "{script_path}"\n')
                wf.write('@set EC=%ERRORLEVEL%\n')
                wf.write(f'@echo %EC%> "{exitcode_file}"\n')
                wf.write('@echo.\n')
                wf.write('@echo ============================================\n')
                wf.write('@echo   Script finished  (exit code: %EC%)\n')
                wf.write('@echo ============================================\n')
                wf.write('@pause\n')
                wf.write('@exit /b %EC%\n')

            process = subprocess.Popen(
                ['cmd.exe', '/c', wrapper_path],
                cwd=os.getcwd(),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            # On Linux/macOS, try common terminal emulators
            terminal_cmds = [
                ['x-terminal-emulator', '-e'] + cmd,
                ['gnome-terminal', '--', *cmd],
                ['xterm', '-hold', '-e'] + cmd,
            ]
            process = None
            for tcmd in terminal_cmds:
                try:
                    process = subprocess.Popen(tcmd, cwd=os.getcwd())
                    break
                except FileNotFoundError:
                    continue
            if process is None:
                logging.warning("⚠️ No terminal emulator found, falling back to direct execution")
                process = subprocess.Popen(cmd, cwd=os.getcwd())

        # Wait indefinitely for the user to close the forked window
        process.wait()

        # Determine the script result.
        # If the exit code file exists, the script actually finished and
        # wrote its real exit code before the window was closed/dismissed.
        # If the file does NOT exist, the window was closed before the
        # script completed (or the script never ran) — treat as True.
        script_exitcode = 0  # default: closing the window = success
        if os.path.exists(exitcode_file):
            try:
                with open(exitcode_file, "r") as ef:
                    script_exitcode = int(ef.read().strip())
            except (ValueError, OSError):
                script_exitcode = 0  # unreadable → treat as success

        if script_exitcode == 0:
            logging.info(f"✅ Script returned True (exit code: {script_exitcode})")
            return True
        else:
            logging.info(f"⛔ Script returned False (exit code: {script_exitcode})")
            return False

    except Exception as e:
        logging.error(f"❌ Forked window execution error: {e}")
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

    script_result = False

    try:
        # Configuration
        script_content = config.get('script', '')
        target_agents = config.get('target_agents', [])
        execute_forked_window = config.get('execute_forked_window', False)

        logging.info("🐍 PYTHONXER AGENT STARTED")
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info(f"🪟 Forked window: {execute_forked_window}")
        logging.info("=" * 60)

        # Execute the Python script
        script_result = execute_python_script(script_content, execute_forked_window=execute_forked_window)

        # Log the result
        if script_result:
            logging.info("PYTHONXER RESULT: TRUE")
        else:
            logging.info("PYTHONXER RESULT: FALSE")

        logging.info("=" * 60)

        # Trigger downstream agents ONLY if script returned True
        if script_result:
            total_triggered = 0
            if target_agents:
                logging.info(f"🚀 Script returned True - triggering {len(target_agents)} downstream agents...")
                for target in target_agents:
                    logging.info(f"   ► Triggering: {target}")
                    if start_agent(target):
                        total_triggered += 1
                logging.info(f"✨ Triggered {total_triggered}/{len(target_agents)} agents.")
            else:
                logging.info("ℹ️ No downstream agents configured.")
        else:
            logging.info("⛔ Script returned False - NOT triggering downstream agents.")

        logging.info(f"🏁 Pythonxer agent finished. Result: {'TRUE' if script_result else 'FALSE'}")

    except Exception as e:
        logging.error(f"❌ Pythonxer agent error: {e}")
        logging.error("PYTHONXER RESULT: FALSE")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0 if script_result else 1)


if __name__ == "__main__":
    main()
