# Dockerer Agent - Docker container management agent
# Action: Triggered by upstream -> Execute docker command -> Trigger downstream (on success or error)

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

    # Check if deployed in session: pools/<session_id>/<agent_dir>
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


def build_docker_commands_to_try(config: Dict) -> list:
    """Build a list of docker/docker-compose commands to try sequentially."""
    command = config.get('command', 'ps')
    compose_file = config.get('compose_file', '')
    service_name = config.get('service_name', '')
    container_name = config.get('container_name', '')
    build_context = config.get('build_context', '.')
    dockerfile = config.get('dockerfile', '')
    image_tag = config.get('image_tag', '')
    extra_args = config.get('extra_args', '')
    custom_command = config.get('custom_command', '')

    commands_to_try = []

    # Helper to add extra args
    def add_args(cmd):
        if extra_args:
            cmd.extend(extra_args.split())
        return cmd

    # Custom raw command fallback logic
    if command == 'custom' and custom_command:
        parts = custom_command.split()
        if not parts:
            return [['docker', 'ps']] # Extreme fallback
            
        primary = parts[:]
        commands_to_try.append(primary)
        
        # If the user forgot 'docker', add it as a fallback
        if parts[0] not in ('docker', 'docker-compose'):
            commands_to_try.append(['docker'] + parts)
            
        # If they used docker-compose, provide a raw docker fallback
        if parts[0] == 'docker-compose':
            fb = ['docker'] + parts[1:]
            # basic clean up of compose-specific flags
            if '-f' in fb:
                idx = fb.index('-f')
                if len(fb) > idx + 1:
                    del fb[idx:idx+2]
            commands_to_try.append(fb)
            
        return commands_to_try

    # Compose-based inherently commands
    compose_commands = ['up', 'down']
    
    # Are we using compose?
    using_compose = bool(compose_file) or command in compose_commands

    if using_compose:
        cmd1 = ['docker-compose']
        if compose_file:
            cmd1.extend(['-f', compose_file])
        cmd1.append(command)
        if service_name:
            cmd1.append(service_name)
        commands_to_try.append(add_args(cmd1))
        
        # Add fallback to raw docker if compose fails (unless it's 'up'/'down' which have no direct equivalent)
        if command not in compose_commands:
            cmd2 = ['docker', command]
            if container_name:
                cmd2.append(container_name)
            elif service_name:
                 cmd2.append(service_name)
            commands_to_try.append(add_args(cmd2))
    else:
        # Direct docker commands
        cmd = ['docker']
        if command == 'build':
            cmd.append('build')
            if dockerfile:
                cmd.extend(['-f', dockerfile])
            if image_tag:
                cmd.extend(['-t', image_tag])
            cmd.append(build_context)
        elif command == 'exec':
            cmd.extend(['exec', container_name] if container_name else ['exec'])
        elif command in ('restart', 'stop', 'start'):
            cmd.extend([command, container_name] if container_name else [command])
        elif command == 'logs':
            cmd.extend(['logs', '--tail', '100'])
            if container_name:
                cmd.append(container_name)
        elif command == 'ps':
            cmd.append('ps')
        elif command == 'pull':
            cmd.append('pull')
            if image_tag:
                cmd.append(image_tag)
        else:
            cmd.append(command)
            
        commands_to_try.append(add_args(cmd))

    return commands_to_try


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

    try:
        target_agents = config.get('target_agents', [])

        logging.info("🐳 DOCKERER AGENT STARTED")

        # Build docker commands
        commands_to_try = build_docker_commands_to_try(config)
        logging.info(f"🎯 Targets: {target_agents}")

        # Execute docker commands sequentially
        exit_code = 1
        success = False

        for attempt, cmd in enumerate(commands_to_try, 1):
            logging.info(f"🔧 Attempt {attempt}/{len(commands_to_try)} Command: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                exit_code = result.returncode

                # Log stdout
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        logging.info(f"📋 {line}")

                # Log stderr
                if result.stderr:
                    for line in result.stderr.strip().split('\n'):
                        if exit_code == 0:
                            logging.info(f"📋 {line}")
                        else:
                            logging.warning(f"⚠️ {line}")

                if exit_code == 0:
                    logging.info(f"✅ Command successful (exit code: {exit_code})")
                    success = True
                    break  # Success! Break out of retry loop
                else:
                    logging.error(f"❌ Command failed with exit code: {exit_code}")
                    if attempt < len(commands_to_try):
                        logging.info("🔄 Falling back to next command...")

            except subprocess.TimeoutExpired:
                logging.error("❌ Command timed out after 300 seconds")
                if attempt < len(commands_to_try):
                    logging.info("🔄 Falling back to next command...")
            except FileNotFoundError:
                logging.error(f"❌ Executable '{cmd[0]}' not found. Is it installed and on PATH?")
                if attempt < len(commands_to_try):
                    logging.info("🔄 Falling back to next command...")
            except Exception as e:
                logging.error(f"❌ Command execution failed: {e}")
                if attempt < len(commands_to_try):
                    logging.info("🔄 Falling back to next command...")

        if not success:
            logging.error("🚨 All command attempts failed.")

        # Trigger downstream agents regardless of success or failure
        total_triggered = 0
        if target_agents:
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents (exit_code={exit_code})...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Dockerer agent finished. Exit code: {exit_code}. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
