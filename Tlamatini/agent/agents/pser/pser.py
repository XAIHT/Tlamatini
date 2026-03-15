# Pser Agent - Process finder agent with LLM-powered fuzzy matching
# Action: Triggered by upstream -> List processes (no admin) -> Ask LLM for best match -> Log result -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import json
import logging
import subprocess
import urllib.request
import urllib.error
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


def query_ollama(host: str, model: str, prompt: str) -> str:
    """
    Send a prompt to an Ollama LLM and return the full response text.
    Uses urllib (stdlib) so no external dependencies are needed.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e


def get_process_list() -> str:
    """
    Obtain a process list without administrative privileges.
    Cross-platform: uses 'tasklist' on Windows, 'ps aux' on Unix.
    Returns raw text output with process name, PID, memory, CPU, and user info.
    """
    commands_to_try = []

    if sys.platform.startswith('win'):
        # tasklist /FO CSV gives structured output; /V adds verbose info (CPU time, user)
        # /V may fail without admin for some processes, so we try both
        commands_to_try = [
            ['tasklist', '/FO', 'CSV', '/V'],
            ['tasklist', '/FO', 'CSV'],
            ['tasklist'],
        ]
    else:
        # Unix: ps aux gives user, PID, %CPU, %MEM, command
        commands_to_try = [
            ['ps', 'aux'],
            ['ps', '-ef'],
        ]

    for cmd in commands_to_try:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue

    raise RuntimeError("Failed to obtain process list with any available command.")


def parse_llm_response(response_text: str) -> dict:
    """
    Parse the LLM response to extract process information.
    Expects JSON with keys: process_name, pid, cpu_usage, memory_usage, user
    Falls back to text parsing if JSON extraction fails.
    """
    # Try to extract JSON from the response
    # Look for JSON block in markdown code fences or raw JSON
    json_str = None

    # Try markdown code fence
    if '```json' in response_text:
        start = response_text.index('```json') + 7
        end = response_text.index('```', start)
        json_str = response_text[start:end].strip()
    elif '```' in response_text:
        start = response_text.index('```') + 3
        end = response_text.index('```', start)
        json_str = response_text[start:end].strip()
    else:
        # Try to find raw JSON object
        brace_start = response_text.find('{')
        brace_end = response_text.rfind('}')
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            json_str = response_text[brace_start:brace_end + 1]

    if json_str:
        try:
            data = json.loads(json_str)
            return {
                'process_name': str(data.get('process_name', 'UNKNOWN')),
                'pid': str(data.get('pid', 'N/A')),
                'cpu_usage': str(data.get('cpu_usage', 'N/A')),
                'memory_usage': str(data.get('memory_usage', 'N/A')),
                'user': str(data.get('user', 'N/A')),
                'found': data.get('found', True),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # If JSON parsing failed, return as not found
    return {
        'process_name': 'UNKNOWN',
        'pid': 'N/A',
        'cpu_usage': 'N/A',
        'memory_usage': 'N/A',
        'user': 'N/A',
        'found': False,
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
        likely_process_name = config.get('likely_process_name', '')
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'llama3')
        target_agents = config.get('target_agents', [])

        logging.info("🔍 PSER AGENT STARTED")
        logging.info(f"🎯 Looking for process: '{likely_process_name}'")
        logging.info(f"🤖 Model: {model} @ {host}")
        logging.info(f"🎯 Targets: {target_agents}")
        logging.info("=" * 60)

        if not likely_process_name.strip():
            logging.error("❌ No likely_process_name configured. Set it in config.yaml.")
            return

        # Step 1: Get process list (no admin needed)
        logging.info("📋 Collecting process list (no admin privileges required)...")
        try:
            process_list = get_process_list()
            line_count = len(process_list.split('\n'))
            logging.info(f"📋 Got {line_count} lines of process data.")
        except RuntimeError as e:
            logging.error(f"❌ Failed to get process list: {e}")
            return

        # Step 2: Ask LLM to find the best matching process
        prompt = f"""You are a process-matching expert. I need you to find the SINGLE best matching process from the list below.

I am looking for a process whose name is most similar to: "{likely_process_name}"

IMPORTANT MATCHING RULES:
- Match semantically AND by name similarity. For example, if I search for "Paint", the best match is "mspaint.exe" (Microsoft Paint), NOT "paintbrush" or some unrelated process.
- If I search for "Chrome", match "chrome.exe". If "Word", match "WINWORD.EXE". If "Excel", match "EXCEL.EXE". If "Notepad", match "notepad.exe". Etc.
- Consider common program names, abbreviations, and official executable names.
- Ignore case when comparing names.
- Pick the ONE process that is the closest semantic match in both name length and meaning.
- If NO process reasonably matches, set "found" to false.

PROCESS LIST:
{process_list}

Respond with ONLY a JSON object (no markdown, no explanation) in this exact format:
{{"process_name": "exact_process_name_from_list", "pid": "12345", "cpu_usage": "0:00:01 or 0.5%", "memory_usage": "50,000 K or 2.1%", "user": "DOMAIN\\\\username or N/A", "found": true}}

If no matching process is found:
{{"process_name": "UNKNOWN", "pid": "N/A", "cpu_usage": "N/A", "memory_usage": "N/A", "user": "N/A", "found": false}}"""

        logging.info(f"📝 Sending process list + query to {model}...")

        try:
            response_text = query_ollama(host, model, prompt)
        except RuntimeError as e:
            logging.error(f"❌ LLM query failed: {e}")
            return

        logging.info(f"✅ LLM response received ({len(response_text)} chars)")

        # Step 3: Parse the LLM response
        result = parse_llm_response(response_text)

        if result['found']:
            # Log in the required format
            logging.info(
                f"PROCESS FOUND: {result['process_name']}, {result['pid']}, "
                f"{result['cpu_usage']}, {result['memory_usage']}, {result['user']}"
            )
        else:
            logging.warning(f"⚠️ No process matching '{likely_process_name}' was found.")
            logging.info(f"LLM raw response: {response_text[:500]}")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Pser agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"❌ Pser agent error: {e}")
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
