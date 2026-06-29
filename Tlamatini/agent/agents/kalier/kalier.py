# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Kalier Agent - MCP-Kali-Server bridge (AI-assisted penetration testing)
# Action: Triggered by upstream -> POST to the MCP-Kali-Server Flask API
#         (/api/command, /api/tools/<tool>, /health) -> log the tool output ->
#         emit INI_SECTION_KALIER -> ALWAYS trigger downstream (success OR failure).
#
# Kalier is Tlamatini's integration of the MCP-Kali-Server
# (https://www.kali.org/tools/mcp-kali-server/). The upstream project is a Flask
# API server (server.py) that runs ON the Kali box plus a thin FastMCP stdio
# bridge (client.py) that just forwards to that API. Kalier talks DIRECTLY to the
# Flask API over HTTP using only the Python standard library (urllib) — exactly
# like the Apirer agent — so it works identically in source and frozen builds and
# never depends on the `requests` / `mcp` packages being importable inside the
# agent-pool subprocess. The agent pool runs as standalone Python subprocesses
# with no path back into the Django app, so (like ACPXer / Windower) this file is
# fully self-contained and does NOT import from agent.* or mcp-kali-server.
#
# Authorized use only: Kalier is a thin transport to offensive-security tooling.
# The operator is responsible for ensuring every target is owned or explicitly
# in-scope (pentest engagement, CTF, lab).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
import time
import yaml
import logging
import subprocess

# -- conhost.exe orphan guard ------------------------------------------
# When Tlamatini's runtime launches us with DETACHED_PROCESS we have no
# console attached. Any child we Popen WITHOUT CREATE_NO_WINDOW makes
# Windows allocate a fresh console (and a companion conhost.exe) for the
# child -- which lingers as an orphan bearing the Tlamatini icon if we
# exit before the child detaches. Default every Popen to
# CREATE_NO_WINDOW unless the caller explicitly asked for a console
# (CREATE_NEW_CONSOLE) or detached the child themselves.
if os.name == 'nt' and not getattr(subprocess, '_conhost_guard_applied', False):
    _CHG_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _CHG_RESPECT = (
        _CHG_NO_WINDOW
        | getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
        | getattr(subprocess, 'DETACHED_PROCESS', 0)
    )
    _chg_orig_init = subprocess.Popen.__init__
    def _chg_guarded_init(self, *args, **kwargs):
        cf = kwargs.get('creationflags', 0) or 0
        if not (cf & _CHG_RESPECT):
            kwargs['creationflags'] = cf | _CHG_NO_WINDOW
        return _chg_orig_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _chg_guarded_init
    subprocess._conhost_guard_applied = True

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
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


# ========================================
# HELPER FUNCTIONS (from shoter.py / windower.py boilerplate — copy verbatim)
# ========================================

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
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

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
    """Resolve the Python home used to spawn pool-agent subprocesses.

    FROZEN: ALWAYS prefer the Python interpreter CARRIED INSIDE Tlamatini's
    installation (``<install_dir>/python``) so pool agents NEVER depend on a
    system Python or a user-set ``PYTHON_HOME``. The carried interpreter is
    pinned to Python 3.12.10 (shipped by the installer). Only when the carried
    interpreter is somehow absent (e.g. running from source) does this fall
    back to the registry / environment ``PYTHON_HOME``.
    """
    if getattr(sys, 'frozen', False):
        _carried = os.path.join(os.path.dirname(sys.executable), 'python')
        if sys.platform.startswith('win'):
            _exe = os.path.join(_carried, 'python.exe')
        else:
            _exe = os.path.join(_carried, 'bin', 'python3')
        if os.path.isfile(_exe):
            return _carried
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
    env = os.environ.copy()

    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

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


# ========================================
# MCP-KALI-SERVER API CONTRACT
# (ported inline from mcp-kali-server/client.py KaliToolsClient — no external deps)
# ========================================

# action -> (HTTP method, endpoint path). Endpoints mirror server.py's Flask routes
# verbatim so any MCP-Kali-Server release works without changes here.
_ACTION_ROUTES = {
    "command":    ("POST", "api/command"),
    "nmap":       ("POST", "api/tools/nmap"),
    "gobuster":   ("POST", "api/tools/gobuster"),
    "dirb":       ("POST", "api/tools/dirb"),
    "nikto":      ("POST", "api/tools/nikto"),
    "sqlmap":     ("POST", "api/tools/sqlmap"),
    "metasploit": ("POST", "api/tools/metasploit"),
    "hydra":      ("POST", "api/tools/hydra"),
    "john":       ("POST", "api/tools/john"),
    "wpscan":     ("POST", "api/tools/wpscan"),
    "enum4linux": ("POST", "api/tools/enum4linux"),
    "health":     ("GET",  "health"),
}


def _cfg(config: dict, key: str, default=""):
    """Fetch a config value, coercing None to the default (yaml empties parse as None)."""
    val = config.get(key, default)
    return default if val is None else val


def _build_payload(action: str, config: dict) -> dict:
    """Build the JSON body for the chosen action, mirroring the parameter names
    each Flask endpoint in server.py expects. Only the keys relevant to `action`
    are included so the server applies its own sensible defaults for the rest."""
    if action == "command":
        return {"command": str(_cfg(config, "command"))}

    if action == "nmap":
        body = {"target": str(_cfg(config, "target"))}
        if _cfg(config, "scan_type"):
            body["scan_type"] = str(_cfg(config, "scan_type"))
        if _cfg(config, "ports"):
            body["ports"] = str(_cfg(config, "ports"))
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "gobuster":
        body = {"url": str(_cfg(config, "url")), "mode": str(_cfg(config, "mode", "dir"))}
        if _cfg(config, "wordlist"):
            body["wordlist"] = str(_cfg(config, "wordlist"))
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "dirb":
        body = {"url": str(_cfg(config, "url"))}
        if _cfg(config, "wordlist"):
            body["wordlist"] = str(_cfg(config, "wordlist"))
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "nikto":
        body = {"target": str(_cfg(config, "target"))}
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "sqlmap":
        body = {"url": str(_cfg(config, "url"))}
        if _cfg(config, "data"):
            body["data"] = str(_cfg(config, "data"))
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "metasploit":
        raw_options = config.get("options", {})
        if isinstance(raw_options, str):
            # The wrapped Multi-Turn grammar is flat key=value, so options may
            # arrive as a JSON string — parse it back into a mapping.
            try:
                raw_options = json.loads(raw_options) if raw_options.strip() else {}
            except Exception:
                logging.warning(f"⚠️ Could not parse metasploit options as JSON: {raw_options!r}; sending empty options.")
                raw_options = {}
        if not isinstance(raw_options, dict):
            raw_options = {}
        return {"module": str(_cfg(config, "module")), "options": raw_options}

    if action == "hydra":
        body = {"target": str(_cfg(config, "target")), "service": str(_cfg(config, "service"))}
        for key in ("username", "username_file", "password", "password_file", "additional_args"):
            if _cfg(config, key):
                body[key] = str(_cfg(config, key))
        return body

    if action == "john":
        body = {"hash_file": str(_cfg(config, "hash_file"))}
        if _cfg(config, "wordlist"):
            body["wordlist"] = str(_cfg(config, "wordlist"))
        if _cfg(config, "format"):
            body["format"] = str(_cfg(config, "format"))
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "wpscan":
        body = {"url": str(_cfg(config, "url"))}
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    if action == "enum4linux":
        body = {"target": str(_cfg(config, "target"))}
        if _cfg(config, "additional_args"):
            body["additional_args"] = str(_cfg(config, "additional_args"))
        return body

    # health -> GET, no body
    return {}


def _subject_for(action: str, config: dict) -> str:
    """The human-facing subject of this run (target / url / command / module),
    used for the section header and log lines."""
    if action == "command":
        return str(_cfg(config, "command"))
    if action == "metasploit":
        return str(_cfg(config, "module"))
    if action in ("gobuster", "dirb", "sqlmap", "wpscan"):
        return str(_cfg(config, "url"))
    if action in ("nmap", "nikto", "hydra", "enum4linux"):
        return str(_cfg(config, "target"))
    if action == "john":
        return str(_cfg(config, "hash_file"))
    return "(health probe)"


def call_kali_api(action: str, config: dict) -> dict:
    """Invoke the chosen MCP-Kali-Server endpoint over HTTP using only urllib.

    Returns a normalized dict:
        {ok, return_code, success, timed_out, endpoint, method, server_url,
         response_body, raw}
    where `success` reflects the tool's own success flag (or HTTP 2xx for /health)
    and `ok` reflects whether the HTTP round-trip itself succeeded.
    """
    import urllib.request
    import urllib.error

    method, endpoint = _ACTION_ROUTES[action]
    server_url = str(_cfg(config, "server_url", "http://127.0.0.1:5000")).rstrip("/")
    try:
        timeout = int(_cfg(config, "timeout", 300) or 300)
    except (TypeError, ValueError):
        timeout = 300

    url = f"{server_url}/{endpoint}"
    payload = _build_payload(action, config)

    logging.info(f"🐉 {method} {url}")
    if method == "POST":
        # Mask credential-shaped fields in the logged payload.
        safe_payload = {
            k: ("***" if k in ("password", "password_file") and v else v)
            for k, v in payload.items()
        }
        logging.info(f"📦 Payload: {json.dumps(safe_payload)[:1000]}")

    data = None
    headers = {"Accept": "application/json"}
    if method == "POST":
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    start_time = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            http_status = response.getcode()
    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        logging.warning(f"⚠️ HTTP {e.code} {e.reason} from {url} ({elapsed}ms)")
        return {
            "ok": False, "return_code": e.code, "success": False, "timed_out": False,
            "endpoint": endpoint, "method": method, "server_url": server_url,
            "response_body": err_body or f"HTTP {e.code}: {e.reason}", "raw": {},
        }
    except urllib.error.URLError as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        reason = getattr(e, "reason", e)
        logging.error(f"❌ Cannot reach MCP-Kali-Server at {url}: {reason} ({elapsed}ms)")
        return {
            "ok": False, "return_code": -1, "success": False, "timed_out": False,
            "endpoint": endpoint, "method": method, "server_url": server_url,
            "response_body": (
                f"Cannot reach MCP-Kali-Server at {url}: {reason}. Is server.py running "
                f"on the Kali box and reachable (consider an SSH tunnel)?"
            ),
            "raw": {},
        }
    except Exception as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ Request to {url} failed: {e} ({elapsed}ms)")
        return {
            "ok": False, "return_code": -1, "success": False, "timed_out": False,
            "endpoint": endpoint, "method": method, "server_url": server_url,
            "response_body": f"Request failed: {e}", "raw": {},
        }

    elapsed = round((time.time() - start_time) * 1000, 2)
    logging.info(f"✅ HTTP {http_status} from {url} ({elapsed}ms)")

    # Parse the JSON envelope returned by server.py.
    try:
        parsed = json.loads(raw_text) if raw_text.strip() else {}
    except Exception:
        parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    # /health returns {status, tools_status, ...}; tool endpoints return
    # {stdout, stderr, return_code, success, timed_out, partial_results}.
    if action == "health":
        body = json.dumps(parsed, indent=2) if parsed else raw_text
        return {
            "ok": True, "return_code": 0,
            "success": str(parsed.get("status", "")).lower() == "healthy",
            "timed_out": False, "endpoint": endpoint, "method": method,
            "server_url": server_url, "response_body": body, "raw": parsed,
        }

    if "error" in parsed and "stdout" not in parsed:
        return {
            "ok": False, "return_code": -1, "success": False, "timed_out": False,
            "endpoint": endpoint, "method": method, "server_url": server_url,
            "response_body": str(parsed.get("error")), "raw": parsed,
        }

    stdout = str(parsed.get("stdout", ""))
    stderr = str(parsed.get("stderr", ""))
    body_parts = []
    if stdout:
        body_parts.append(stdout)
    if stderr:
        body_parts.append(f"[stderr]\n{stderr}")
    response_body = "\n".join(body_parts) if body_parts else (raw_text or "(no output)")

    return {
        "ok": True,
        "return_code": parsed.get("return_code", 0),
        "success": bool(parsed.get("success", False)),
        "timed_out": bool(parsed.get("timed_out", False)),
        "endpoint": endpoint, "method": method, "server_url": server_url,
        "response_body": response_body, "raw": parsed,
    }


# ========================================
# STRUCTURED OUTPUT (Parametrizer / KV-promotion contract)
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_KALIER<<< block atomically (single logging.info call).

    Mirrors the Apirer / Windower / ACPXer convention so this agent's structured
    output is consumable by the Multi-Turn LLM (via the wrapped chat-agent
    run-result KV promotion) AND the Parametrizer canvas pipeline (registered in
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS and parametrizer.SECTION_AGENT_TYPES).
    The KV header field names below MUST stay aligned with that registration.
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_KALIER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_KALIER")


# ========================================
# MAIN
# ========================================

def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        action = str(_cfg(config, 'action', 'nmap') or 'nmap').strip().lower()
        server_url = str(_cfg(config, 'server_url', 'http://127.0.0.1:5000'))

        logging.info("🐉 KALIER AGENT STARTED (MCP-Kali-Server bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Server: {server_url}")
        logging.info(f"Targets: {target_agents}")

        if action not in _ACTION_ROUTES:
            valid = ", ".join(sorted(_ACTION_ROUTES.keys()))
            body = f"Unknown action {action!r}. Valid actions: {valid}."
            logging.error(f"❌ {body}")
            outcome = {
                "action": action, "endpoint": "", "method": "",
                "subject": "", "return_code": -1, "success": "false",
                "timed_out": "false", "server_url": server_url,
            }
            _emit_section(outcome, body)
        else:
            subject = _subject_for(action, config)
            logging.info(f"Subject: {subject!r}")
            result = call_kali_api(action, config)

            outcome = {
                "action": action,
                "endpoint": result["endpoint"],
                "method": result["method"],
                "subject": subject,
                "return_code": result["return_code"],
                "success": "true" if result["success"] else "false",
                "timed_out": "true" if result["timed_out"] else "false",
                "server_url": result["server_url"],
            }
            body = result["response_body"] or "(no output)"
            _emit_section(outcome, body)

            if result["ok"]:
                logging.info(
                    f"🏁 Kali {action} complete: success={result['success']} "
                    f"return_code={result['return_code']} timed_out={result['timed_out']}"
                )
            else:
                logging.warning(f"⚠️ Kali {action} did not complete cleanly (transport/server error).")

        # Always trigger downstream agents regardless of success or failure, so a
        # downstream Forker / Raiser can branch on {success} / {return_code}.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Kalier agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
