# ═══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Terminater Agent - visible, user-supervised terminals (CMD / PowerShell)
# Action: raise / type into / read / abort / kill real terminals the USER can watch,
#         type into and take over -> emit INI_SECTION_TERMINATER -> trigger downstream
#
# THE POINT OF THIS AGENT: Executer runs a command and returns text.  Terminater runs
# it in a terminal the user SEES (and can interrupt, answer, or finish typing).
# Tlamatini types every key like a person; there is no paste and no instant mode.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
import time
import yaml
import logging
import subprocess
import urllib.request
import urllib.error

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

from typing import Any, Dict, List, Optional

# Temp/Templates policy: transient files live under <app>/Temp, never %TEMP%.
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    import tempfile as _tlt_tempfile
    _tlt_tempfile.tempdir = os.environ['TLAMATINI_TEMP'].strip()

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")
    script_dir = os.getcwd()

# Flat sibling modules travel with the pool copy of this template.
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Strict yes/no parsing lives in the stdlib-only text sibling, shared with the engine.
import terminater_text as _tx  # noqa: E402

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


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
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
    """Resolve the Python home used to spawn pool-agent subprocesses.

    FROZEN: ALWAYS prefer the Python interpreter CARRIED INSIDE Tlamatini's
    installation (``<install_dir>/python``) so pool agents NEVER depend on a
    system Python or a user-set ``PYTHON_HOME``. Only when the carried
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


# ─────────────────────────────────────────────────────────────────────────────
# Terminater proper
# ─────────────────────────────────────────────────────────────────────────────

ENV_TOKEN = "TLAMATINI_TERMINATER_TOKEN"
ENV_URL = "TLAMATINI_TERMINATER_URL"
RENDEZVOUS_NAME = ".terminater_hub.json"

#: Config keys handed to the hub as parameters (everything else is agent plumbing).
PARAM_KEYS = (
    "terminal", "kind", "title", "cwd", "text", "text_b64", "submit", "secret", "typing_wpm",
    "wait", "wait_seconds", "hang_seconds", "user_wait_seconds", "until", "pattern", "idle_seconds",
    "which", "read_chars", "offset", "keys", "cursor", "message", "severity", "suggestion", "hint",
    "layout", "area", "show", "close_after", "load_profile", "advisor", "user",
    "create_if_missing", "clear_line", "check_line", "use_my_defaults", "explanation",
)

#: Yes/no parameters.  They are read STRICTLY (terminater_text.parse_flag): a value that is not
#: a clean yes/no falls to the SAFE side below -- never press Enter for the caller, hide a
#: secret, never close a terminal, never invent a terminal -- and the reply names it in `notes`.
FLAG_KEYS = (
    "submit", "wait", "secret", "close_after", "load_profile", "advisor", "show",
    "create_if_missing", "clear_line", "check_line",
)
FLAG_SAFE_SIDE = {
    "submit": False, "secret": True, "close_after": False,
    "create_if_missing": False, "clear_line": False,
}

#: Header fields of INI_SECTION_TERMINATER (kept in step with agent_contracts.py).
SECTION_FIELDS = (
    "action", "status", "success", "terminal_id", "kind", "title", "terminal_state", "command",
    "exit_code", "duration_seconds", "output_chars", "truncated", "hung", "aborted_by", "typed",
    "user_part", "user_line", "user_keys", "cursor", "watch_reason", "wait_reason", "layout",
    "area", "terminals", "hub", "message", "verified", "screen_line", "enter_pressed", "notes",
)


def _read_rendezvous() -> Dict[str, Any]:
    """The file the Django hub writes: where it listens and the token to present."""
    roots = []
    temp = (os.environ.get('TLAMATINI_TEMP') or '').strip().strip('"')
    if temp:
        roots.append(temp)
    probe = script_dir
    for _ in range(10):
        if os.path.exists(os.path.join(probe, 'manage.py')):
            roots.append(os.path.join(probe, 'Temp'))
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if getattr(sys, 'frozen', False):
        roots.append(os.path.join(os.path.dirname(sys.executable), 'Temp'))
    probe = script_dir
    for _ in range(10):
        candidate = os.path.join(probe, 'Temp')
        if os.path.isdir(candidate):
            roots.append(candidate)
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    for root in roots:
        path = os.path.join(root, RENDEZVOUS_NAME)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("url") and data.get("token"):
                return data
        except (OSError, ValueError):
            continue
    return {}


class HubClient:
    """Talks to the Tlamatini terminal hub over loopback HTTP (job-polled)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.url = str(config.get("hub_url") or "").strip() or os.environ.get(ENV_URL, "").strip()
        self.token = os.environ.get(ENV_TOKEN, "").strip()
        self._file = _read_rendezvous()
        if not self.url:
            self.url = str(self._file.get("url") or "")
        if not self.token:
            self.token = str(self._file.get("token") or "")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _post(self, payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url.rstrip("/") + "/agent/terminater/api/", data=data, method="POST",
            headers={"Content-Type": "application/json", "X-Terminater-Token": self.token})
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and self._file.get("token") and self._file.get("token") != self.token:
                self.token = str(self._file["token"])
                return self._post(payload, timeout)
            try:
                return json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                return {"ok": False, "status": "unavailable", "code": f"http_{exc.code}",
                        "message": f"The terminal hub answered HTTP {exc.code}."}

    def reachable(self) -> bool:
        if not (self.url and self.token):
            return False
        try:
            res = self._post({"action": "ping"}, timeout=4.0)
            return bool(res.get("pong"))
        except Exception:  # noqa: BLE001
            return False

    def call(self, action: str, params: Dict[str, Any], deadline_s: float) -> Dict[str, Any]:
        first = self._post({"action": action, "params": params}, timeout=60.0)
        job = first.get("job")
        if not job:
            return first
        started = time.time()
        last_note = started
        while True:
            time.sleep(0.5)
            res = self._post({"action": "job", "params": {"id": job}}, timeout=30.0)
            if res.get("job_state") == "done":
                return res
            if res.get("job_state") == "unknown":
                return {"ok": False, "status": "error", "code": "job_lost",
                        "message": "The hub forgot this job (it may have restarted)."}
            now = time.time()
            if now - last_note >= 15:
                logging.info(f"⏳ still {action}... ({int(now - started)}s)")
                last_note = now
            if now - started > deadline_s:
                return {"ok": False, "status": "timeout", "success": False, "code": "agent_deadline",
                        "message": f"The agent stopped waiting after {int(deadline_s)}s; the terminal "
                                   "may still be working (use action='wait' or 'read')."}


class LocalHub:
    """Standalone mode: private terminals that live and die inside this agent run."""

    def __init__(self) -> None:
        import terminater_engine as eng
        self.eng = eng
        self.hub = eng.TerminalHub(max_terminals=6)

    def call(self, action: str, params: Dict[str, Any], deadline_s: float) -> Dict[str, Any]:
        return self.hub.call(action, {**params, "user": params.get("user") or "local"})

    def shutdown(self) -> None:
        self.hub.shutdown()


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "":
            return default
        return text not in ("0", "false", "no", "off", "none", "null")
    return bool(value)


def build_params(config: Dict[str, Any], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    """The parameters handed to the hub.  Yes/no settings are read STRICTLY: one that is not a
    clean yes/no falls to its safe side (see ``FLAG_SAFE_SIDE``) and is named in ``notes``."""
    params: Dict[str, Any] = {}
    for key in PARAM_KEYS:
        if key in config and config[key] not in (None, ""):
            params[key] = config[key]
    for key in FLAG_KEYS:
        if key in config and config[key] not in (None, ""):
            value, note = _tx.parse_flag(config[key], True, FLAG_SAFE_SIDE.get(key))
            params[key] = value
            if note and notes is not None:
                notes.append(f"{key}: {note}")
    return params


def _deadline(action: str, params: Dict[str, Any]) -> float:
    inherit = _tx.parse_flag(params.get('use_my_defaults'), False, False)[0]
    # Account defaults are resolved in the Django hub. The pool agent allows
    # their documented maxima; the hub still enforces the actual shorter waits.
    wait_s = 3600 if inherit else float(params.get("wait_seconds") or 120)
    text = str(params.get("text") or "")
    encoded = str(params.get('text_b64') or '')
    if encoded:
        import base64
        try:
            text = base64.b64decode(encoded, validate=True).decode('utf-8')
        except (ValueError, UnicodeError):
            text = encoded  # The hub will reject malformed input.
    wpm = 20 if inherit else max(20, min(160, float(params.get('typing_wpm') or 50)))
    typing = 12 / wpm * len(text) + 5 if action in ("run", "type", "handover") else 0
    handoffs = max(text.count('<<USER'), int(action == 'handover'))
    user = (3600 if inherit else float(params.get("user_wait_seconds") or 300)) * handoffs
    return wait_s + typing + user + 210  # Bounded narration receipt plus transport margin.


def _sanitize_value(value: Any) -> str:
    return str(value if value is not None else "").replace("\r", " ").replace("\n", " ").strip()


def emit_section(action: str, res: Dict[str, Any], backend: str, hub_listing: Optional[Dict[str, Any]]) -> None:
    """ONE atomic INI_SECTION_TERMINATER block (a Parametrizer source)."""
    status = str(res.get("status") or ("error" if not res.get("ok", True) else "completed"))
    success = res.get("success")
    if success is None:
        success = bool(res.get("ok", True)) and status not in (
            "refused", "unavailable", "error", "timeout", "hung", "command_failed", "aborted",
            "operator_required", "typing_unverified")
    ui = res.get("ui") or {}
    terminals = ""
    if isinstance(res.get("terminals"), list):
        terminals = str(len(res["terminals"]))
    header = {
        "action": action,
        "status": status,
        "success": bool(success),
        "terminal_id": res.get("terminal_id") or (res.get("terminal") or {}).get("id", ""),
        "kind": res.get("kind") or (res.get("terminal") or {}).get("kind", ""),
        "title": res.get("title") or (res.get("terminal") or {}).get("title", ""),
        "terminal_state": res.get("terminal_state") or (res.get("terminal") or {}).get("state", ""),
        "command": res.get("command", ""),
        "exit_code": "" if res.get("exit_code") is None else res.get("exit_code"),
        "duration_seconds": res.get("duration_seconds", ""),
        "output_chars": res.get("output_chars", ""),
        "truncated": res.get("truncated", ""),
        "hung": res.get("hung", ""),
        "aborted_by": res.get("aborted_by", ""),
        "typed": res.get("typed", ""),
        "user_part": res.get("user_part", ""),
        "user_line": res.get("line", ""),
        "user_keys": res.get("keys", ""),
        "cursor": res.get("cursor", ""),
        "watch_reason": res.get("watch_reason", ""),
        "wait_reason": res.get("wait_reason", ""),
        "layout": ui.get("layout", ""),
        "area": ui.get("area", ""),
        "terminals": terminals,
        "hub": backend,
        "message": res.get("message", ""),
        "verified": "" if res.get("verified") is None else res.get("verified"),
        "screen_line": res.get("screen_line", ""),
        "enter_pressed": "" if res.get("enter_pressed") is None else res.get("enter_pressed"),
        "notes": res.get("notes", ""),
    }
    body_parts = []
    if res.get("output"):
        body_parts.append(str(res["output"]))
    if isinstance(res.get("terminals"), list):
        rows = [f"{t.get('id')}  {t.get('kind'):<10} {t.get('state'):<14} pid={t.get('pid')}  "
                f"{t.get('title')}  cwd={t.get('cwd')}"
                + (f"  RUNNING: {t.get('running_command')}" if t.get("running_command") else "")
                for t in res["terminals"]]
        body_parts.append("\n".join(rows) if rows else "(no terminals open)")
    if isinstance(res.get("commands"), list):
        body_parts.append("\n".join(
            f"#{c.get('id')} [{c.get('source')}] {c.get('state')} exit={c.get('exit_code')} "
            f"{c.get('command')}" for c in res["commands"]))
    if res.get("submitted"):
        body_parts.append("USER SUBMITTED:\n" + "\n".join(
            f"  {s.get('line')}" for s in res["submitted"]))
    if res.get("advice"):
        body_parts.append("ADVICE:\n" + "\n".join(
            f"  [{a.get('severity')}] {a.get('message')} {a.get('suggestion') or ''}".rstrip()
            for a in res["advice"]))
    if res.get("message") and not body_parts:
        body_parts.append(str(res["message"]))
    body = "\n\n".join(body_parts)
    text = "\n".join(f"{k}: {_sanitize_value(v)}" for k, v in header.items())
    logging.info(f"INI_SECTION_TERMINATER<<<\n{text}\n\n{body}\n>>>END_SECTION_TERMINATER")


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    local_hub: Optional[LocalHub] = None
    exit_code = 0
    try:
        target_agents = config.get('target_agents', []) or []
        action = str(config.get('action') or 'run').strip().lower().replace('-', '_') or 'run'
        mode = str(config.get('mode') or 'auto').strip().lower()
        param_notes: List[str] = []
        params = build_params(config, param_notes)

        logging.info("🖥️ TERMINATER AGENT STARTED")
        logging.info(f"⚙️ action={action} terminal={params.get('terminal', '(active)')} "
                     f"kind={params.get('kind', 'powershell')} mode={mode}")
        if params.get('text') and not params.get('secret'):
            logging.info(f"⌨️ will type: {str(params['text'])[:200]}")
        logging.info(f"🎯 Targets: {target_agents}")

        backend = "hub"
        client: Any = None
        if mode != "standalone":
            hub = HubClient(config)
            if hub.reachable():
                client = hub
        if client is None:
            if mode == "hub":
                res = {"ok": False, "status": "unavailable", "success": False, "code": "hub_unavailable",
                       "message": "No Tlamatini terminal hub is reachable, and mode='hub' forbids "
                                  "standalone terminals. Is Tlamatini running?"}
                emit_section(action, res, "none", None)
                logging.error("❌ " + res["message"])
                client = None
                res_done = True
            else:
                logging.warning("⚠️ No Tlamatini hub is reachable: running STANDALONE. The terminals "
                                "live inside this agent and are not shown in the browser.")
                try:
                    local_hub = LocalHub()
                except Exception as exc:  # noqa: BLE001
                    res = {"ok": False, "status": "unavailable", "success": False, "code": "no_engine",
                           "message": f"The terminal engine could not start: {exc}"}
                    emit_section(action, res, "none", None)
                    logging.error("❌ " + res["message"])
                    client = None
                    res_done = True
                else:
                    client = local_hub
                    backend = "standalone"
                    res_done = False
        else:
            res_done = False

        if client is not None and not res_done:
            res = client.call(action, params, _deadline(action, params))
            if param_notes:
                res["notes"] = "; ".join(n for n in [res.get("notes"), *param_notes] if n)
            if action in ("run", "open") and res.get("ok") and backend == "hub":
                logging.info("👀 The terminal is visible in Tlamatini's Terminals area.")
            emit_section(action, res, backend, None)
            if res.get("ok") and res.get("status") not in ("error", "typing_unverified"):
                logging.info(f"✅ Terminater {action}: {res.get('status')}")
            else:
                logging.error(f"❌ Terminater {action}: {res.get('status')} - {res.get('message', '')}")
            if str(res.get("status")) == "error":
                exit_code = 1

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Terminater agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        if local_hub is not None:
            try:
                local_hub.shutdown()
            except Exception:  # noqa: BLE001
                pass
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
