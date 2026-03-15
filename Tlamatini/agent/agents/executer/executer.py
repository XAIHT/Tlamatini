# Executer Agent - Deterministic agent to execute a command
# Logs EXECUTION SUCCESS or EXECUTION FAILED based on result
# Always triggers downstream agents regardless of success/failure

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


def execute_script(script_content: str, non_blocking: bool = False,
                    execute_forked_window: bool = False) -> bool:
    """
    Write the script content to a temporary file and execute it.
    Returns True on success, False on failure.

    If non_blocking=True, the script is launched as a detached process and
    the function returns immediately without waiting for completion.
    This is useful for starting long-running services like GlassFish.

    If execute_forked_window=True, the script runs in a visible console
    window so stdout/stderr are shown in real time.  This works in both
    blocking and non_blocking modes.
    """
    if not script_content or not script_content.strip():
        logging.error("❌ No script content specified to execute.")
        return False
    
    try:
        # Determine file extension and execution command based on OS
        is_windows = sys.platform.startswith('win')
        ext = '.bat' if is_windows else '.sh'
        
        # For NON-BLOCKING mode: Save script to TEMP directory (OUTSIDE pool)
        # This prevents the script and its spawned processes from being killed
        # by the Ender agent or flow cleanup, which scan the pool directory.
        if non_blocking:
            import tempfile
            # Use a unique filename to avoid conflicts
            temp_dir = tempfile.gettempdir()
            script_filename = f"tlamatini_nb_{os.getpid()}{ext}"
            script_path = os.path.join(temp_dir, script_filename)
            logging.info(f"📝 Non-blocking: Writing script to TEMP: {script_path}")
        else:
            # For blocking mode: Use pool directory as before
            script_filename = f"temp_script{ext}"
            script_path = os.path.abspath(script_filename)
            logging.info(f"📝 Writing script to: {script_path}")
        
        # Write content to file
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        # Make executable (important for Linux)
        try:
            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | 0o111)
        except Exception as e:
            logging.warning(f"⚠️ Failed to set execution permissions: {e}")

        logging.info(f"🚀 Executing script... (non_blocking={non_blocking})")
        
        cmd = [script_path]
        
        # NON-BLOCKING MODE: Fire-and-forget for long-running processes
        if non_blocking:
            logging.info("🔥 Non-blocking mode: Launching script as detached process...")

            if is_windows:
                # Use PowerShell Start-Process which creates a TRULY independent process
                # This is the most reliable method on Windows to break free from:
                # - Windows Job Objects
                # - Console associations
                # - Parent-child process relationships
                #
                # -FilePath: The script to run
                # -WindowStyle: Normal (visible) when execute_forked_window is on,
                #               Hidden when off
                # -PassThru is NOT used so we don't wait for process object

                # Escape the path for PowerShell
                escaped_path = script_path.replace("'", "''")

                # CRITICAL: Use TEMP as working directory (not pool!)
                # This ensures the spawned process has no association with the pool
                # and won't be killed by Ender/cleanup scans
                temp_dir = os.path.dirname(script_path)  # Already in TEMP

                window_style = 'Normal' if execute_forked_window else 'Hidden'
                ps_command = (
                    f'Start-Process -FilePath "{escaped_path}" '
                    f'-WorkingDirectory "{temp_dir}" '
                    f'-WindowStyle {window_style}'
                )

                logging.info(f"   PowerShell command: {ps_command}")

                # Run PowerShell to execute Start-Process
                # PowerShell Start-Process creates a process NOT tied to this session
                process = subprocess.Popen(
                    ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_command],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=temp_dir,  # Also run PowerShell from TEMP
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                # Wait for PowerShell to finish executing Start-Process
                # (PowerShell exits immediately after spawning the independent process)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logging.warning("⚠️ PowerShell took too long, continuing anyway...")

            else:
                # Unix: Use start_new_session to detach from parent
                # Also use nohup-style approach for maximum independence
                if execute_forked_window:
                    # Try to launch in a visible terminal emulator
                    terminal_cmds = [
                        ['x-terminal-emulator', '-e', script_path],
                        ['gnome-terminal', '--', script_path],
                        ['xterm', '-hold', '-e', script_path],
                    ]
                    launched = False
                    for tcmd in terminal_cmds:
                        try:
                            subprocess.Popen(
                                tcmd,
                                cwd=os.getcwd(),
                                start_new_session=True,
                                close_fds=True
                            )
                            launched = True
                            break
                        except FileNotFoundError:
                            continue
                    if not launched:
                        logging.warning("⚠️ No terminal emulator found, falling back to hidden")
                        subprocess.Popen(
                            ['nohup', script_path],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            cwd=os.getcwd(),
                            start_new_session=True,
                            close_fds=True
                        )
                else:
                    subprocess.Popen(
                        ['nohup', script_path],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        cwd=os.getcwd(),
                        start_new_session=True,
                        close_fds=True
                    )

            logging.info(f"✅ Script launched as independent process (detached, not waiting, window={'visible' if execute_forked_window else 'hidden'})")
            return True
        
        # FORKED WINDOW MODE: Run in a visible console window
        if execute_forked_window:
            logging.info("🪟 Forked window mode: Launching script in new console...")
            return _execute_in_forked_window(script_path)

        # BLOCKING MODE: Wait for script to complete (original behavior)
        result = subprocess.run(
            cmd,
            shell=True,
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
            logging.info(f"✅ Script execution completed with exit code: {result.returncode}")
            return True
        else:
            logging.error(f"❌ Script execution failed with exit code: {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        logging.error("❌ Script execution timed out (300s limit)")
        return False
    except Exception as e:
        logging.error(f"❌ Script execution error: {e}")
        return False
    finally:
        # User requested: "The temporary file must be created... and overwriten... each time"
        # Since we overwrite on next run, we technically don't HAVE to delete it, 
        # but cleanup is usually good practice. 
        # However, the user said "overwritten... each time", implying it stays there?
        # "At execution time ... the script should be writen ... and finally execute."
        # No explicit instruction to delete it. Leaving it might be useful for debugging.
        pass


def _execute_in_forked_window(script_path: str) -> bool:
    """
    Execute a script in a new console window and wait for it to finish.
    The forked window stays open after the script completes so the user
    can read stdout and stderr.  Returns True if exit code == 0.
    """
    try:
        if sys.platform.startswith('win'):
            # Build a tiny wrapper .bat that:
            #   1. Calls the real script
            #   2. Saves %ERRORLEVEL%
            #   3. Prints a separator so the user knows it finished
            #   4. Pauses so the window stays open
            #   5. Exits with the original error level
            wrapper_path = os.path.abspath("temp_forked_wrapper.bat")
            with open(wrapper_path, "w", encoding="utf-8") as wf:
                wf.write(f'@call "{script_path}"\n')
                wf.write('@set EC=%ERRORLEVEL%\n')
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
            # xterm -hold keeps the window open after the command exits
            terminal_cmds = [
                ['x-terminal-emulator', '-e'] + [script_path],
                ['gnome-terminal', '--', script_path],
                ['xterm', '-hold', '-e', script_path],
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
                process = subprocess.Popen([script_path], cwd=os.getcwd())

        # Wait for the forked window process to finish
        # (on Windows this waits until the user presses a key in the window)
        process.wait(timeout=300)

        if process.returncode == 0:
            logging.info(f"✅ Script execution completed with exit code: {process.returncode}")
            return True
        else:
            logging.error(f"❌ Script execution failed with exit code: {process.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logging.error("❌ Forked window script execution timed out (300s limit)")
        try:
            process.kill()
        except Exception:
            pass
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
    
    execution_success = False
    
    try:
        # Configuration
        # Support both 'script' (new) and 'command' (legacy fallback)
        script_content = config.get('script', config.get('command', ''))
        target_agents = config.get('target_agents', [])
        non_blocking = config.get('non_blocking', False)
        execute_forked_window = config.get('execute_forked_window', False)

        logging.info("🔥 EXECUTER AGENT STARTED (SCRIPT MODE)")
        # logging.info(f"📋 Script Content: {script_content}") # Don't log full script to avoid clutter
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info(f"⚡ Non-blocking: {non_blocking}")
        logging.info(f"🪟 Forked window: {execute_forked_window}")
        logging.info("=" * 60)

        # Execute the script
        execution_success = execute_script(
            script_content, non_blocking=non_blocking,
            execute_forked_window=execute_forked_window
        )
        
        # Log the required status message
        if execution_success:
            logging.info("EXECUTION SUCCESS")
        else:
            logging.error("EXECUTION FAILED")
        
        logging.info("=" * 60)
        
        # Trigger downstream agents REGARDLESS of success/failure
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                logging.info(f"   ► Triggering: {target}")
                if start_agent(target):
                    total_triggered += 1
            logging.info(f"✨ Triggered {total_triggered}/{len(target_agents)} agents.")
        else:
            logging.info("ℹ️ No downstream agents configured.")
        
        logging.info(f"🏁 Executer agent finished. Result: {'SUCCESS' if execution_success else 'FAILED'}")
        
    except Exception as e:
        logging.error(f"❌ Executer agent error: {e}")
        logging.error("EXECUTION FAILED")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
    
    sys.exit(0 if execution_success else 1)


if __name__ == "__main__":
    main()
