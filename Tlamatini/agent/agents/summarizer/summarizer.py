# Summarizer Agent - Log file monitoring and LLM-powered event detection
# Action: Started -> Continuously poll source agent logs -> Query LLM with system_prompt
#         -> Detect [EVENT_TRIGGERED] -> Start/restart target agents

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import json
import logging
import subprocess
import urllib.request
import urllib.error
from typing import Dict, List

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
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
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
        logging.error(f"Agent script not found: {script_path}")
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
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ============================================================
# LLM Query
# ============================================================

def query_ollama(host: str, model: str, system_prompt: str, context: str) -> str:
    """
    Send a prompt to an Ollama LLM with a system prompt and log content context,
    and return the full response text.
    """
    url = f"{host.rstrip('/')}/api/generate"
    full_prompt = f"{system_prompt}\n\n--- BEGIN LOG CONTENT ---\n{context}\n--- END LOG CONTENT ---"

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
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


# ============================================================
# Log File Reading
# ============================================================

def get_source_log_path(source_agent: str) -> str:
    """Get the log file path for a source agent."""
    agent_dir = get_agent_directory(source_agent)
    # Log file name matches the directory name
    return os.path.join(agent_dir, f"{source_agent}.log")


def read_log_file(log_path: str) -> str:
    """Read the contents of a log file. Returns empty string if not found."""
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception as e:
        logging.error(f"Failed to read log file {log_path}: {e}")
    return ""


# ============================================================
# Event Detection
# ============================================================

EVENT_TRIGGERED_PATTERN = re.compile(r'\[EVENT_TRIGGERED\]', re.IGNORECASE)


def detect_event_triggered(llm_response: str) -> bool:
    """
    Check if the LLM response contains [EVENT_TRIGGERED].
    The system_prompt instructs the LLM to output outcome_word:[EVENT_TRIGGERED]
    when a positive event is detected, or outcome_word:[NONE] otherwise.
    We do NOT hardcode the outcome_word — only the bracket tag matters.
    """
    return bool(EVENT_TRIGGERED_PATTERN.search(llm_response))


# ============================================================
# Core Polling Logic
# ============================================================

def poll_source_agents(source_agents: List[str], system_prompt: str,
                       host: str, model: str, poll_interval: int) -> bool:
    """
    Continuously poll all source agent log files until at least one triggers
    a positive event via the LLM analysis.
    Returns True if any event was triggered.
    """
    # Track which source agents have already been fully checked with content
    checked_with_content = set()
    event_triggered = False

    logging.info(f"Polling {len(source_agents)} source agent(s) every {poll_interval}s...")

    while not event_triggered and len(checked_with_content) < len(source_agents):
        for source in source_agents:
            if source in checked_with_content:
                continue

            log_path = get_source_log_path(source)
            log_content = read_log_file(log_path)

            if not log_content.strip():
                logging.info(f"  [{source}] Log empty or not found, will retry...")
                continue

            logging.info(f"  [{source}] Log has {len(log_content)} chars, querying LLM...")

            try:
                llm_response = query_ollama(host, model, system_prompt, log_content)
            except RuntimeError as e:
                logging.error(f"  [{source}] LLM query failed: {e}")
                continue

            logging.info(
                f"INI_RESPONSE_SUMMARIZER<<<\n"
                f"--------------------LLM Response (model: {model}, "
                f"source: {source})------------------"
                f" {{\n{llm_response}\n}}\n"
                f">>>END_RESPONSE_SUMMARIZER"
            )

            checked_with_content.add(source)

            if detect_event_triggered(llm_response):
                logging.info(f"  [{source}] [EVENT_TRIGGERED] detected!")
                event_triggered = True
                break
            else:
                logging.info(f"  [{source}] No event triggered ([NONE] or no match).")

        if not event_triggered and len(checked_with_content) < len(source_agents):
            logging.info(f"  Waiting {poll_interval}s before next poll cycle...")
            time.sleep(poll_interval)

    return event_triggered


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()

    try:
        source_agents = config.get('source_agents', [])
        system_prompt = config.get('system_prompt', '')
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'llama3.1:8b')
        poll_interval = config.get('poll_interval', 5)
        target_agents = config.get('target_agents', [])

        logging.info("SUMMARIZER AGENT STARTED")
        logging.info(f"Source agents: {source_agents}")
        logging.info(f"Model: {model} @ {host}")
        logging.info(f"Poll interval: {poll_interval}s")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        if not source_agents:
            logging.error("No source_agents configured. Connect source agents on the canvas.")
            return

        if not system_prompt.strip():
            logging.error("No system_prompt configured. Set the 'system_prompt' field in config.yaml.")
            return

        # Poll source agent logs and detect events via LLM
        event_triggered = poll_source_agents(
            source_agents, system_prompt, host, model, poll_interval
        )

        if event_triggered:
            logging.info("[EVENT_TRIGGERED] detected — starting target agents...")
            total_triggered = 0
            if target_agents:
                wait_for_agents_to_stop(target_agents)
                logging.info(f"Triggering {len(target_agents)} downstream agents...")
                for target in target_agents:
                    if start_agent(target):
                        total_triggered += 1
            logging.info(f"Summarizer agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
        else:
            logging.info("All source agents checked. No events triggered.")
            logging.info("Summarizer agent finished. No downstream agents started.")

    except Exception as e:
        logging.error(f"Summarizer agent error: {e}")
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
