# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Zavuerer Agent - Zavu unified-messaging bridge (https://www.zavu.dev)
# Action: Triggered by upstream -> POST to the Zavu REST API (/v1/messages) with a
#         single API key -> send SMS / WhatsApp / Telegram / Email / Voice with
#         optional ML smart-routing (channel="auto") + automatic fallback ->
#         log the result -> emit INI_SECTION_ZAVUERER -> ALWAYS trigger downstream
#         (success OR failure, so a Forker can branch on {success}/{status}).
#
# Zavuerer is Tlamatini's integration of Zavu — "one API for all your messages".
# Instead of maintaining Twilio (SMS) + Meta Cloud API (WhatsApp) + SMTP (Email)
# separately, Zavuerer sends through Zavu's single REST endpoint. It talks DIRECTLY
# to the Zavu API over HTTP using only the Python standard library (urllib) —
# exactly like the Kalier / Apirer agents — so it works identically in source and
# frozen builds and never depends on `requests` or `@zavudev/sdk` being importable
# inside the agent-pool subprocess. The agent pool runs as standalone Python
# subprocesses with no path back into the Django app, so this file is fully
# self-contained and does NOT import from agent.*.
#
# Authorized, opted-in recipients only: every channel has anti-spam / consent
# rules (A2P, TCPA, WhatsApp 24-hour window, GDPR). Zavu handles the compliance
# plumbing, but the operator is responsible for messaging only people who agreed.

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
# HELPER FUNCTIONS (from shoter.py / kalier.py boilerplate — copy verbatim)
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
    system Python or a user-set ``PYTHON_HOME``.
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
    """Wait until ALL specified agents have stopped running."""
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
# ZAVU REST API CONTRACT
# (https://www.zavu.dev — POST /v1/messages with a Bearer API key; no external deps)
# ========================================

# action -> (HTTP method, endpoint path) relative to zavu_base_url.
_ACTION_ROUTES = {
    "send":   ("POST", "messages"),
    # Zavu has NO /health route (it 404s "Route not found"). /senders is the
    # cheapest authenticated GET that proves BOTH the key is accepted AND a
    # sending identity exists, so it is the real readiness probe.
    "health": ("GET",  "senders"),
}

# Channels Zavu accepts. "auto" lets Zavu's ML pick the best/cheapest channel.
_VALID_CHANNELS = ("auto", "sms", "whatsapp", "telegram", "voice", "email")


def _cfg(config: dict, key: str, default=""):
    """Fetch a config value, coercing None to the default (yaml empties parse as None)."""
    val = config.get(key, default)
    return default if val is None else val


def _coerce_bool(val, default: bool = True) -> bool:
    """Coerce a config value (which may arrive as a wrapped-parser string) to bool,
    never raising. 'true'/'1'/'yes'/'on' -> True; 'false'/'0'/'no'/'off'/'' -> False."""
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on", "y"):
        return True
    if s in ("false", "0", "no", "off", "n", ""):
        return False
    return default


_TERMINAL_STATUSES = ("delivered", "read", "failed", "undelivered", "rejected")


def _await_delivery(message_id: str, config: dict, max_seconds: int = 45) -> str:
    """Poll GET /messages/<id> until the status is TERMINAL, and return it.

    Zavu answers a send with 202 + "queued"; the carrier verdict lands a few
    seconds later. Without this the agent reports "queued" (or worse, "ok") for
    a message the network went on to REJECT -- which is precisely how a whole
    evening was lost believing WhatsApp was delivering when it was not.
    Returns "" if no terminal state is reached in time (caller keeps "queued").
    """
    import urllib.request                       # local, like call_zavu_api does

    base_url = str(_cfg(config, "zavu_base_url", "https://api.zavu.dev/v1")).rstrip("/")
    api_key = str(_cfg(config, "zavu_api_key")).strip()
    if not api_key or not message_id:
        return ""
    url = f"{base_url}/messages/{message_id}"
    deadline = time.time() + max_seconds
    latest = ""
    while time.time() < deadline:
        request = urllib.request.Request(url, method="GET")
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Accept", "application/json")
        # Cloudflare 403s a User-Agent-less request ("browser_signature_banned").
        request.add_header(
            "User-Agent", "Tlamatini-Zavuerer/1.0 (+https://github.com/XAIHT/Tlamatini)")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            envelope = payload.get("message") if isinstance(payload.get("message"), dict) else payload
            latest = str(envelope.get("status", "")).strip().lower()
            if latest in _TERMINAL_STATUSES:
                return latest
        except Exception as exc:                                # noqa: BLE001
            logging.warning(f"Delivery poll failed ({exc}); keeping '{latest or 'queued'}'.")
            return latest
        time.sleep(3)
    logging.warning(f"Delivery did not settle within {max_seconds}s "
                    f"(last seen '{latest or 'queued'}').")
    return latest


def _find_contacts_file() -> str:
    """Locate contacts.json exactly the way Telegrammer does: next to the frozen
    exe in an install, or <repo>/Tlamatini/agent/contacts.json in a checkout."""
    candidate = (os.environ.get("TLAMATINI_CONTACTS") or "").strip()
    if candidate and os.path.isfile(candidate):
        return candidate
    cur = os.path.dirname(os.path.abspath(__file__))
    seen = []
    for _ in range(10):
        seen.append(os.path.join(cur, "contacts.json"))
        seen.append(os.path.join(cur, "agent", "contacts.json"))
        seen.append(os.path.join(cur, "Tlamatini", "agent", "contacts.json"))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if getattr(sys, "frozen", False):
        seen.append(os.path.join(os.path.dirname(sys.executable), "contacts.json"))
    for path in seen:
        if os.path.isfile(path):
            return path
    return ""


def _normalize_msisdn(value: str) -> str:
    """Mexican mobiles need the '1' after the country code on WhatsApp (+521...).

    Stored as +52 55 ... the API ACCEPTS the send and the carrier then silently
    fails it -- a failure with no error text anywhere. Normalise it here.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    only = "".join(ch for ch in raw if ch.isdigit())
    if only.startswith("52") and not only.startswith("521") and len(only) == 12:
        only = "521" + only[2:]
    return ("+" + only) if only else ""


def _resolve_contact(query: str, channel: str) -> str:
    """Resolve a contacts.json name/alias to an address for this channel.

    Matching is case- AND accent-insensitive, so 'angela', 'Angela' and
    'Ángela López Mendoza' all resolve. Without this, a perfectly ordinary
    request like "send a WhatsApp to Angela with Zavuerer" produced NO message
    at all, because Zavuerer only ever understood a raw number.
    """
    import unicodedata

    def _n(value):
        text = " ".join(str(value or "").strip().lower().split())
        return "".join(c for c in unicodedata.normalize("NFKD", text)
                       if not unicodedata.combining(c))

    needle = _n(query)
    if not needle:
        return ""
    path = _find_contacts_file()
    if not path:
        logging.error("contact_name '%s' given but no contacts.json was found." % query)
        return ""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception as exc:                                    # noqa: BLE001
        logging.warning("Could not read contacts.json (%s): %s" % (path, exc))
        return ""
    contacts = data.get("contacts", []) if isinstance(data, dict) else data
    field = "email" if str(channel).strip().lower() == "email" else "whatsapp"
    for entry in contacts or []:
        if not isinstance(entry, dict):
            continue
        names = [entry.get("name", "")] + list(entry.get("aliases", []) or [])
        if any(_n(name) == needle for name in names if name):
            value = str(entry.get(field) or "").strip()
            if not value:
                logging.error("Contact '%s' has no '%s' entry in %s"
                              % (query, field, path))
                return ""
            resolved = value if field == "email" else _normalize_msisdn(value)
            logging.info("Resolved contact '%s' -> %s '%s' (%s)"
                         % (query, field, resolved, path))
            return resolved
    logging.error("Contact '%s' not found in %s" % (query, path))
    return ""


def _build_payload(action: str, config: dict) -> dict:
    """Build the JSON body for the chosen action, mirroring Zavu's documented
    `messages.send({ to, text, channel, fallbackEnabled })` shape."""
    if action == "send":
        channel = str(_cfg(config, "channel", "auto")).strip().lower() or "auto"
        # `to` wins; otherwise resolve `contact_name` through contacts.json so
        # "send a WhatsApp to Angela" works without anyone typing a number.
        to_value = str(_cfg(config, "to")).strip()
        if to_value:
            if channel != "email":
                to_value = _normalize_msisdn(to_value)
        else:
            to_value = _resolve_contact(str(_cfg(config, "contact_name")).strip(), channel)
        body = {
            "to": to_value,
            "text": str(_cfg(config, "text")),
            "channel": channel,
            "fallbackEnabled": _coerce_bool(_cfg(config, "fallback", True), True),
        }
        subject = str(_cfg(config, "subject")).strip()
        if subject:
            body["subject"] = subject
        sender = str(_cfg(config, "from_sender")).strip()
        if sender:
            body["from"] = sender
        return body

    # health -> GET, no body
    return {}


def call_zavu_api(action: str, config: dict) -> dict:
    """Invoke the chosen Zavu endpoint over HTTP using only urllib.

    Returns a normalized dict:
        {ok, http_status, success, status, channel, message_id, base_url,
         endpoint, method, response_body, raw}
    where `success` reflects an HTTP 2xx AND a non-error message status, and `ok`
    reflects whether the HTTP round-trip itself succeeded.
    """
    import urllib.request
    import urllib.error

    method, endpoint = _ACTION_ROUTES[action]
    base_url = str(_cfg(config, "zavu_base_url", "https://api.zavu.dev/v1")).rstrip("/")
    api_key = str(_cfg(config, "zavu_api_key")).strip()
    try:
        timeout = int(_cfg(config, "timeout", 60) or 60)
    except (TypeError, ValueError):
        timeout = 60

    url = f"{base_url}/{endpoint}"
    payload = _build_payload(action, config)

    logging.info(f"✉️ {method} {url}")
    if method == "POST":
        logging.info(f"📦 Payload: {json.dumps(payload)[:1000]}")

    headers = {
        "Accept": "application/json",
        # The Zavu API sits behind Cloudflare, which blocks the bare Python-urllib
        # User-Agent (Error 1010 "browser_signature_banned"). Present an explicit,
        # honest client UA so the request is not rejected before it reaches Zavu.
        "User-Agent": "Tlamatini-Zavuerer/1.0 (+https://github.com/XAIHT/Tlamatini)",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = None
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
        hint = ""
        if e.code in (401, 403):
            hint = " (check your zavu_api_key — get one at https://www.zavu.dev — pay-as-you-go pricing)"
        return {
            "ok": False, "http_status": e.code, "success": False, "status": "failed",
            "channel": "", "message_id": "", "base_url": base_url,
            "endpoint": endpoint, "method": method,
            "response_body": (err_body or f"HTTP {e.code}: {e.reason}") + hint, "raw": {},
        }
    except urllib.error.URLError as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        reason = getattr(e, "reason", e)
        logging.error(f"❌ Cannot reach Zavu at {url}: {reason} ({elapsed}ms)")
        return {
            "ok": False, "http_status": -1, "success": False, "status": "unreachable",
            "channel": "", "message_id": "", "base_url": base_url,
            "endpoint": endpoint, "method": method,
            "response_body": (
                f"Cannot reach the Zavu API at {url}: {reason}. Check `zavu_base_url`, "
                f"your network, and that https://www.zavu.dev is up."
            ),
            "raw": {},
        }
    except Exception as e:
        elapsed = round((time.time() - start_time) * 1000, 2)
        logging.error(f"❌ Request to {url} failed: {e} ({elapsed}ms)")
        return {
            "ok": False, "http_status": -1, "success": False, "status": "error",
            "channel": "", "message_id": "", "base_url": base_url,
            "endpoint": endpoint, "method": method,
            "response_body": f"Request failed: {e}", "raw": {},
        }

    elapsed = round((time.time() - start_time) * 1000, 2)
    logging.info(f"✅ HTTP {http_status} from {url} ({elapsed}ms)")

    try:
        parsed = json.loads(raw_text) if raw_text.strip() else {}
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    http_ok = 200 <= http_status < 300
    # send -> {id|messageId, channel, status:"queued"|"sent"|...}; health -> {status:"operational"|...}
    # Zavu wraps a send response as {"message": {...}} — read THAT envelope, not
    # the top level. Reading the top level made status/message_id come back empty
    # and turned a REJECTED send into success=True (a message that never arrived
    # was reported as sent). Do NOT revert to parsed.get("status").
    envelope = parsed.get("message") if isinstance(parsed.get("message"), dict) else parsed
    msg_status = str(envelope.get("status", "")).strip()
    channel_used = str(envelope.get("channel", "")).strip()
    message_id = str(envelope.get("id", envelope.get("messageId", ""))).strip()
    success = http_ok and msg_status.lower() not in ("failed", "error", "rejected", "undelivered")
    body = json.dumps(parsed, indent=2) if parsed else (raw_text or "(no response body)")

    return {
        "ok": True, "http_status": http_status, "success": success,
        "status": msg_status or ("ok" if http_ok else "unknown"),
        "channel": channel_used, "message_id": message_id, "base_url": base_url,
        "endpoint": endpoint, "method": method, "response_body": body, "raw": parsed,
    }


# ========================================
# STRUCTURED OUTPUT (Parametrizer / KV-promotion contract)
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_ZAVUERER<<< block atomically (single logging.info call).

    The KV header field names below MUST stay aligned with the Parametrizer
    registration (agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['zavuerer'],
    views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['zavuerer'], parametrizer.SECTION_AGENT_TYPES)
    and the wrapped-tool KV promotion (tools._PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR).
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_ZAVUERER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_ZAVUERER")


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
        action = str(_cfg(config, 'action', 'send') or 'send').strip().lower()
        base_url = str(_cfg(config, 'zavu_base_url', 'https://api.zavu.dev/v1'))
        channel = str(_cfg(config, 'channel', 'auto')).strip().lower() or "auto"
        to = str(_cfg(config, 'to')).strip()

        logging.info("✉️ ZAVUERER AGENT STARTED (Zavu unified-messaging bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Base URL: {base_url}")
        logging.info(f"Targets: {target_agents}")

        # Resolve `contact_name` -> `to` BEFORE the preflight, otherwise a
        # perfectly valid "send to Angela" is refused for "no recipient" even
        # though the contacts book has her. Also normalises MX +52 -> +521.
        if not to:
            resolved_contact = _resolve_contact(
                str(_cfg(config, "contact_name")).strip(), channel)
            if resolved_contact:
                to = resolved_contact
                config["to"] = resolved_contact
                logging.info(f"Recipient resolved from contacts.json -> {to}")
        elif channel != "email":
            normalized = _normalize_msisdn(to)
            if normalized and normalized != to:
                logging.info(f"Recipient normalised {to} -> {normalized}")
                to = normalized
                config["to"] = normalized

        # ── Fail-safe preflight (refuse rather than mis-send) ──────────────
        preflight_error = None
        if action not in _ACTION_ROUTES:
            valid = ", ".join(sorted(_ACTION_ROUTES.keys()))
            preflight_error = f"Unknown action {action!r}. Valid actions: {valid}."
        elif action == "send":
            if not str(_cfg(config, 'zavu_api_key')).strip():
                preflight_error = (
                    "Zavuerer is NOT configured: `zavu_api_key` is empty. Get a key at https://www.zavu.dev "
                    "(free sign-up; pay-as-you-go to send) and paste it into the agent "
                    "config (or Config -> Access Keys), then run again."
                )
            elif not to:
                preflight_error = "No recipient: set `to` (a +E.164 phone for SMS/WhatsApp/Voice/Telegram, or an email for Email)."
            elif not str(_cfg(config, 'text')) and channel != "voice":
                preflight_error = "No message body: set `text` (the message to send)."
            elif channel not in _VALID_CHANNELS:
                preflight_error = f"Unknown channel {channel!r}. Valid channels: {', '.join(_VALID_CHANNELS)}."

        if preflight_error:
            logging.error(f"❌ {preflight_error}")
            outcome = {
                "action": action, "channel": channel, "to": to, "status": "refused",
                "message_id": "", "success": "false", "base_url": base_url,
            }
            _emit_section(outcome, preflight_error)
        else:
            logging.info(f"Channel: {channel!r}  To: {to!r}")
            result = call_zavu_api(action, config)

            # A send returns 202 + status "queued". QUEUED IS NOT DELIVERED --
            # Meta can still reject it seconds later (closed 24h window, bad
            # number, throttling) and Zavu flips it to "failed". Reporting the
            # first answer is how this agent used to claim success for messages
            # that never arrived. Poll to a TERMINAL state and report THAT.
            if (action == "send" and result.get("ok") and result.get("message_id")
                    and str(result.get("status", "")).lower() in ("queued", "accepted", "")):
                final = _await_delivery(result["message_id"], config)
                if final:
                    if final != result["status"]:
                        logging.info(f"Delivery status settled: "
                                     f"{result['status']} -> {final}")
                    result["status"] = final
                    result["success"] = final in ("delivered", "read", "sent")

            outcome = {
                "action": action,
                "channel": result["channel"] or channel,
                "to": to,
                "status": result["status"],
                "message_id": result["message_id"],
                "success": "true" if result["success"] else "false",
                "base_url": result["base_url"],
            }
            body = result["response_body"] or "(no output)"
            _emit_section(outcome, body)

            if result["ok"] and result["success"]:
                logging.info(
                    f"🏁 Zavu {action} OK: channel={result['channel'] or channel} "
                    f"status={result['status']} id={result['message_id']}"
                )
            else:
                logging.warning(
                    f"⚠️ Zavu {action} did not complete cleanly "
                    f"(status={result['status']}, http={result['http_status']})."
                )

        # Always trigger downstream agents regardless of success or failure, so a
        # downstream Forker / Raiser can branch on {success} / {status}.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 Zavuerer agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
