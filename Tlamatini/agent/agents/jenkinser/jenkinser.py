# Jenkinser Agent - CI/CD Pipeline Trigger
# Action: Triggered by upstream -> Trigger Jenkins build -> Log result -> Trigger downstream (always)

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess
import json

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


def load_config(path: str = "config.yaml") -> dict:
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


def trigger_jenkins_build(config: dict) -> dict:
    """Trigger a Jenkins build using urllib (no external dependencies)."""
    import urllib.request
    import urllib.error
    import urllib.parse

    jenkins_url = config.get('jenkins_url', '').rstrip('/')
    job_name = config.get('job_name', '')
    user = config.get('user', '')
    api_token = config.get('api_token', '')
    parameters = config.get('parameters', {})
    use_parameters = config.get('use_parameters', False)

    if not jenkins_url:
        return {'success': False, 'error': 'No jenkins_url configured', 'status_code': 0}

    if not job_name:
        return {'success': False, 'error': 'No job_name configured', 'status_code': 0}

    # Determine build endpoint
    if parameters or use_parameters:
        build_url = f"{jenkins_url}/job/{urllib.parse.quote(job_name, safe='')}/buildWithParameters"
    else:
        build_url = f"{jenkins_url}/job/{urllib.parse.quote(job_name, safe='')}/build"

    logging.info(f"🔧 Jenkins URL: {jenkins_url}")
    logging.info(f"📋 Job: {job_name}")
    logging.info(f"🌐 Build URL: {build_url}")

    # Build auth header
    headers = {}
    if user and api_token:
        import base64
        credentials = base64.b64encode(f"{user}:{api_token}".encode('utf-8')).decode('utf-8')
        headers['Authorization'] = f'Basic {credentials}'
        logging.info(f"🔑 Auth: {user}:***")

    # Try to get CSRF crumb (required for most modern Jenkins setups)
    try:
        crumb_url = f"{jenkins_url}/crumbIssuer/api/json"
        crumb_req = urllib.request.Request(crumb_url, headers=headers)
        crumb_response = urllib.request.urlopen(crumb_req, timeout=10)
        crumb_data = json.loads(crumb_response.read().decode('utf-8'))
        headers[crumb_data['crumbRequestField']] = crumb_data['crumb']
        logging.info("🛡️ CSRF crumb retrieved successfully.")
    except Exception as crumb_err:
        logging.warning(f"⚠️ Could not retrieve CSRF crumb: {crumb_err}. Trying without...")

    # Prepare request body for parameterized builds
    data = None
    if parameters and isinstance(parameters, dict):
        params_encoded = urllib.parse.urlencode(parameters).encode('utf-8')
        data = params_encoded
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        logging.info(f"📦 Parameters: {parameters}")

    try:
        start_time = time.time()
        req = urllib.request.Request(build_url, data=data, headers=headers, method='POST')
        response = urllib.request.urlopen(req, timeout=30)
        elapsed = round((time.time() - start_time) * 1000, 2)

        status_code = response.getcode()
        response.read()

        logging.info(f"✅ Build triggered! Status: {status_code} ({elapsed}ms)")

        # Try to extract queue location
        queue_url = response.getheader('Location')
        if queue_url:
            logging.info(f"📍 Queue URL: {queue_url}")

        return {
            'success': True,
            'status_code': status_code,
            'queue_url': queue_url or '',
            'elapsed_ms': elapsed,
            'error': None
        }

    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        error_body = ''
        try:
            error_body = e.read().decode('utf-8', errors='replace')
        except Exception:
            pass

        logging.warning(f"⚠️ HTTP Error: {e.code} {e.reason} ({elapsed}ms)")
        if error_body:
            preview = error_body[:500]
            logging.warning(f"📄 Error body: {preview}")

        return {
            'success': False,
            'status_code': e.code,
            'queue_url': '',
            'elapsed_ms': elapsed,
            'error': f"HTTP {e.code}: {e.reason}"
        }

    except urllib.error.URLError as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ URL Error: {e.reason} ({elapsed}ms)")
        return {
            'success': False,
            'status_code': 0,
            'queue_url': '',
            'elapsed_ms': elapsed,
            'error': f"URL Error: {e.reason}"
        }

    except Exception as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ Request failed: {e} ({elapsed}ms)")
        return {
            'success': False,
            'status_code': 0,
            'queue_url': '',
            'elapsed_ms': elapsed,
            'error': str(e)
        }


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

        logging.info("🔧 JENKINSER AGENT STARTED")
        logging.info(f"🌐 Jenkins: {config.get('jenkins_url', 'NOT SET')}")
        logging.info(f"📋 Job: {config.get('job_name', 'NOT SET')}")
        logging.info(f"🎯 Targets: {target_agents}")

        # Trigger the Jenkins build
        result = trigger_jenkins_build(config)

        # Always trigger downstream agents regardless of build trigger success or failure
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents (result: {'SUCCESS' if result['success'] else 'ERROR'})...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Jenkinser agent finished. Build trigger: {'SUCCESS' if result['success'] else 'FAILED'}, Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
