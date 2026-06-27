# Whatsapper Agent — the ONE WhatsApp send/receive agent.
#
# Uses ONLY Meta's OFFICIAL WhatsApp Cloud API (Graph API) over plain HTTPS
# (stdlib urllib) — NO Twilio, NO TextMeBot, NO WhatsApp Web gateway. Get the
# Phone number ID + Access token from Meta (see HOW_TO_GET_YOUR_WHATSAPP_ASSETS.md).
#
# Three run-modes (config `mode`: auto | send | receive):
#   i)  SEND     — send one message (or template), then start target_agents, die.
#   ii) RECEIVE/timeout — run the official webhook listener up to rx_max_seconds;
#                 if NOTHING arrives, report "no message", start target_agents,
#                 die (status=no_message, Parametrizer-readable).
#   iii) RECEIVE/message — if a WhatsApp message arrives in the window, report it,
#                 start target_agents, die (status=received, text is
#                 Parametrizer-readable as response_body).
# `auto` picks SEND when `message` or `template` is set, else RECEIVE.
#
# RECEIVE NOTE: WhatsApp Cloud API delivers inbound messages by POSTing to a
# PUBLIC https webhook (there is no polling). So receive mode runs a tiny stdlib
# HTTP server; for Meta to reach it you expose this port publicly (ngrok /
# cloudflared / router) and set that URL + verify_token in the WhatsApp app's
# webhook config. Without a public URL the listener simply times out (mode ii).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import json
import yaml
import logging
import threading
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

# -- conhost.exe orphan guard ------------------------------------------
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

from typing import Dict, Optional, Tuple

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"


# ─────────────────────────────────────────────────────────────
# Pool boilerplate (verbatim from the shoter.py reference)
# ─────────────────────────────────────────────────────────────

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


def get_user_python_home() -> str:
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
    if not agent_names:
        return
    waited = 0.0
    poll_interval = 0.5
    while True:
        still_running = [name for name in agent_names if is_agent_running(name)]
        if not still_running:
            return
        if waited >= 10.0:
            logging.error(f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running. Will keep waiting...")
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
            with open(os.path.join(agent_dir, "agent.pid"), "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"⚠️ Failed to write PID file for target {agent_name}: {pid_err}")
        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


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
        except Exception:
            return


def _start_targets(target_agents) -> int:
    total = 0
    if target_agents:
        wait_for_agents_to_stop(target_agents)
        logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
        for target in target_agents:
            if start_agent(target):
                total += 1
    return total


# ─────────────────────────────────────────────────────────────
# Credentials + contacts
# ─────────────────────────────────────────────────────────────

def _clean(value) -> str:
    v = str(value or '').strip()
    return '' if (v.startswith('<') and v.endswith('>')) else v


def _normalize_msisdn(number: str) -> str:
    return ''.join(ch for ch in str(number or '') if ch.isdigit())


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


# ─────────────────────────────────────────────────────────────
# Identity provider
#   'cloud' -> official Meta WhatsApp Cloud API (sends from the BUSINESS number;
#              needs the System User / templates / 24h-window rules).
#   'web'   -> UNOFFICIAL WhatsApp Web automation (sends from YOUR OWN personal
#              number after a one-time QR login). NOT a Meta-sanctioned API; for
#              messaging your own contacts from your own number only.
# Plain English is accepted so the operator can just say "as me".
# ─────────────────────────────────────────────────────────────

_WEB_PROVIDER_WORDS = frozenset((
    'web', 'me', 'myself', 'my_self', 'self', 'owner', 'my_account', 'myaccount',
    'personal', 'personal_account', 'my_personal_account', 'my_number',
    'my_phone', 'whatsapp_web', 'web_whatsapp', 'wa_web', 'my_whatsapp',
))
_CLOUD_PROVIDER_WORDS = frozenset((
    'cloud', 'cloud_api', 'official', 'business', 'the_business', 'meta',
    'graph', 'api', 'bot', 'the_bot', 'a_bot', 'business_account', 'company',
))


def _normalize_provider_word(value: str) -> str:
    """Lowercase + collapse spaces/hyphens to underscores, then strip a leading
    'send_'/'as_' so 'send as me' == 'as me' == 'me'."""
    word = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    while '__' in word:
        word = word.replace('__', '_')
    prev = None
    while prev != word:
        prev = word
        for pfx in ('send_', 'as_'):
            if word.startswith(pfx):
                word = word[len(pfx):]
    return word


def _resolve_provider(config: Dict) -> str:
    wa = config.get('whatsapp') or {}
    if not isinstance(wa, dict):
        wa = {}
    raw = _clean(config.get('provider') or wa.get('provider') or os.environ.get('WHATSAPP_PROVIDER'))
    provider = _normalize_provider_word(raw) or 'auto'
    if provider in _WEB_PROVIDER_WORDS or provider == 'web':
        return 'web'
    if provider in _CLOUD_PROVIDER_WORDS or provider in ('cloud', 'auto'):
        return 'cloud'
    logging.warning(f"Unknown WhatsApp provider {raw!r}; using cloud.")
    return 'cloud'


def _stable_state_dir() -> str:
    """A durable per-install directory for the WhatsApp Web login profile, resolved
    the same way contacts/config are (so the QR login survives restarts/updates)."""
    candidates = []
    explicit = (os.environ.get('TLAMATINI_STATE_DIR') or '').strip()
    if explicit:
        candidates.append(explicit)
    contacts_path = (os.environ.get('TLAMATINI_CONTACTS') or '').strip()
    if contacts_path:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(contacts_path)), '.tlamatini'))
    exe_parent = os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(exe_parent).lower() == 'python':
        candidates.append(os.path.join(os.path.dirname(exe_parent), '.tlamatini'))
    cur = os.path.dirname(os.path.abspath(__file__))
    for _ in range(12):
        if os.path.basename(cur).lower() == 'agents':
            candidates.append(os.path.join(os.path.dirname(cur), '.tlamatini'))
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    candidates.append(os.path.join(script_dir, '.tlamatini'))
    for path in candidates:
        if not path:
            continue
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            continue
    return script_dir


def _wa_web_profile_dir(config: Dict) -> str:
    wa = config.get('whatsapp') or {}
    web = (wa.get('web') if isinstance(wa, dict) else {}) or {}
    explicit = _clean(web.get('profile_dir')) if isinstance(web, dict) else ''
    path = explicit or os.path.join(_stable_state_dir(), 'whatsapp_web_profile')
    if not os.path.isabs(path):
        path = os.path.join(_stable_state_dir(), path)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _build_wa_web_send_url(number: str, text: str) -> str:
    """The official web.whatsapp.com deep link that opens a chat with the message
    pre-filled. Digits only (no '+'), text URL-encoded."""
    return 'https://web.whatsapp.com/send?' + urllib.parse.urlencode(
        {'phone': _normalize_msisdn(number), 'text': text or ''}
    )


def _resolve_whatsapp_cfg(config: Dict) -> Dict:
    wa = config.get('whatsapp') or {}
    if not isinstance(wa, dict):
        wa = {}
    return {
        'phone_number_id': _clean(wa.get('phone_number_id') or os.environ.get('WHATSAPP_PHONE_NUMBER_ID')),
        'access_token': _clean(wa.get('access_token') or os.environ.get('WHATSAPP_ACCESS_TOKEN')),
        'graph_base': (_clean(wa.get('graph_base') or os.environ.get('WHATSAPP_GRAPH_BASE')) or 'https://graph.facebook.com'),
        'api_version': (_clean(wa.get('api_version') or os.environ.get('WHATSAPP_API_VERSION')) or 'v20.0'),
        'verify_token': (_clean(wa.get('verify_token') or os.environ.get('WHATSAPP_VERIFY_TOKEN')) or 'tlamatini'),
        'webhook_host': (_clean(wa.get('webhook_host')) or '0.0.0.0'),
        'webhook_port': int(wa.get('webhook_port') or os.environ.get('WHATSAPP_WEBHOOK_PORT') or 8086),
        'webhook_path': (_clean(wa.get('webhook_path')) or '/wa-webhook'),
        'to': _clean(wa.get('to')),
    }


def _coerce_param_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(p) for p in value]
    text = str(value).strip()
    return [p.strip() for p in text.split('||') if p.strip()] if text else []


def _find_contacts_file() -> str:
    candidate = (os.environ.get('TLAMATINI_CONTACTS') or '').strip()
    if candidate and os.path.isfile(candidate):
        return candidate
    cur = os.path.dirname(os.path.abspath(__file__))
    seen = []
    for _ in range(10):
        seen.append(os.path.join(cur, 'contacts.json'))
        seen.append(os.path.join(cur, 'agent', 'contacts.json'))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if getattr(sys, 'frozen', False):
        seen.append(os.path.join(os.path.dirname(sys.executable), 'contacts.json'))
    for path in seen:
        if os.path.isfile(path):
            return path
    return ''


def _resolve_contact(query: str, channel: str) -> str:
    needle = ' '.join(str(query or '').strip().lower().split())
    if not needle:
        return ''
    path = _find_contacts_file()
    if not path:
        return ''
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            data = json.load(handle)
    except Exception as exc:
        logging.warning(f"Could not read contacts.json ({path}): {exc}")
        return ''
    contacts = data.get('contacts', []) if isinstance(data, dict) else data
    if not isinstance(contacts, list):
        return ''

    def _names(contact):
        raw = [contact.get('name', '')] + list(contact.get('aliases') or [])
        return [' '.join(str(n).strip().lower().split()) for n in raw if str(n or '').strip()]

    for contact in contacts:
        if isinstance(contact, dict) and needle in _names(contact):
            return str(contact.get(channel) or '').strip()
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        for name in _names(contact):
            tokens = name.split()
            if needle in name or name in needle or (needle.split() and all(t in tokens for t in needle.split())):
                return str(contact.get(channel) or '').strip()
    return ''


def _resolve_recipient(config: Dict, wa_cfg: Dict) -> str:
    contact_name = str(config.get('contact_name') or '').strip()
    if contact_name:
        resolved = _resolve_contact(contact_name, 'whatsapp')
        if resolved:
            logging.info(f"📇 Resolved contact '{contact_name}' → WhatsApp '{resolved}'")
            return resolved
        logging.error(f"❌ Contact '{contact_name}' not found (or has no 'whatsapp') in contacts.json")
        return ''
    return str(config.get('to') or wa_cfg.get('to') or '').strip()


# ─────────────────────────────────────────────────────────────
# Meta WhatsApp Cloud API — outbound (official, stdlib only)
# ─────────────────────────────────────────────────────────────

class WhatsAppCloudClient:
    MAX_BODY_LEN = 4000

    def __init__(self, phone_number_id, access_token, graph_base, api_version):
        self.phone_number_id = _clean(phone_number_id)
        self.access_token = _clean(access_token)
        self.graph_base = (_clean(graph_base) or "https://graph.facebook.com").rstrip('/')
        self.api_version = _clean(api_version) or "v20.0"

    @property
    def configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    @staticmethod
    def _format_meta_error(status_code: int, raw: str) -> str:
        summary = raw[:400]
        try:
            err = (json.loads(raw).get("error") or {})
            message = str(err.get("message") or "").strip()
            code = str(err.get("code") or "").strip()
            err_type = str(err.get("type") or "").strip()
            fbtrace = str(err.get("fbtrace_id") or "").strip()
            if status_code == 401 or code == "190":
                summary = (
                    "Meta WhatsApp Cloud API authentication failed. The access token is "
                    "expired, revoked, malformed, or does not belong to this app/WABA/phone_number_id. "
                    "Generate a fresh System User permanent token with whatsapp_business_messaging "
                    "and whatsapp_business_management, assign the WhatsApp asset, update "
                    "whatsapp_access_token, then restart Tlamatini."
                )
            elif code == "131047" or "re-engagement" in message.lower():
                summary = (
                    "Meta rejected this as a cold free-form message outside the 24-hour customer "
                    "service window. Use an approved WhatsApp template for the first outbound message."
                )
            elif message:
                summary = message
            details = []
            if code:
                details.append(f"code={code}")
            if err_type:
                details.append(f"type={err_type}")
            if fbtrace:
                details.append(f"fbtrace_id={fbtrace}")
            if details:
                summary = f"{summary} ({', '.join(details)})"
        except Exception:
            pass
        return f"HTTPError {status_code}: {summary}"

    def _post(self, payload: Dict) -> Tuple[bool, str, str]:
        if not self.configured:
            return False, "whatsapp.phone_number_id or whatsapp.access_token missing", ""
        url = f"{self.graph_base}/{self.api_version}/{self.phone_number_id}/messages"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.access_token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if 200 <= resp.status < 300:
                    mid = ""
                    try:
                        msgs = json.loads(body).get("messages") or []
                        if msgs:
                            mid = str(msgs[0].get("id") or "")
                    except Exception:
                        pass
                    return True, body, mid
                return False, f"HTTP {resp.status}: {body[:400]}", ""
        except urllib.error.HTTPError as exc:
            try:
                err = exc.read().decode("utf-8", errors="replace")
            except Exception:
                err = str(exc)
            return False, self._format_meta_error(exc.code, err), ""
        except Exception as exc:
            return False, f"send error: {exc}", ""

    def send_text(self, to: str, text: str) -> Tuple[bool, str, str]:
        recipient = _normalize_msisdn(to)
        if not recipient:
            return False, "no recipient (empty WhatsApp number)", ""
        if not text:
            return True, "", ""
        chunks = [text[i:i + self.MAX_BODY_LEN] for i in range(0, len(text), self.MAX_BODY_LEN)] or [text]
        ok_all, last_info, last_id = True, "", ""
        for chunk in chunks:
            ok, info, mid = self._post({
                "messaging_product": "whatsapp", "recipient_type": "individual",
                "to": recipient, "type": "text",
                "text": {"preview_url": False, "body": chunk},
            })
            last_info, last_id = info, (mid or last_id)
            if ok:
                logging.info(f"✅ WhatsApp(Cloud) text → {recipient}: OK ({len(chunk)} chars)")
            else:
                ok_all = False
                logging.error(f"❌ WhatsApp(Cloud) text → {recipient}: FAIL — {info}")
                if "131047" in info or "re-engagement" in info.lower():
                    logging.error("   ↳ Outside the 24h window — a cold message needs an approved `template`.")
                break
        return ok_all, last_info, last_id

    def send_template(self, to: str, template_name: str, language: str, body_params) -> Tuple[bool, str, str]:
        recipient = _normalize_msisdn(to)
        if not recipient:
            return False, "no recipient (empty WhatsApp number)", ""
        template = {"name": template_name, "language": {"code": (language or "en_US").strip()}}
        if body_params:
            template["components"] = [{"type": "body",
                                       "parameters": [{"type": "text", "text": str(p)} for p in body_params]}]
        ok, info, mid = self._post({
            "messaging_product": "whatsapp", "recipient_type": "individual",
            "to": recipient, "type": "template", "template": template,
        })
        if ok:
            logging.info(f"✅ WhatsApp(Cloud) template '{template_name}' → {recipient}: OK")
        else:
            logging.error(f"❌ WhatsApp(Cloud) template '{template_name}' → {recipient}: FAIL — {info}")
        return ok, info, mid


# ─────────────────────────────────────────────────────────────
# WhatsApp Web — outbound from YOUR OWN number (UNOFFICIAL, Playwright)
# ─────────────────────────────────────────────────────────────

class WhatsAppWebClient:
    """Sends a WhatsApp message from the user's OWN personal number by driving
    web.whatsapp.com through a PERSISTENT (logged-in) Playwright browser profile.

    This is NOT a Meta-sanctioned API — it automates WhatsApp Web the same way a
    person would. It needs a ONE-TIME QR-code login (open it headed once, scan with
    the phone under Linked Devices); the session is then remembered in the profile
    dir, exactly like WhatsApp Web/Desktop. Use it only to send your own messages.
    """

    # WhatsApp Web's compose box (several fallbacks; the site changes its DOM).
    _COMPOSE_SELECTORS = (
        'div[aria-label="Type a message"][contenteditable="true"]',
        'div[contenteditable="true"][data-tab="10"]',
        'footer div[contenteditable="true"]',
    )
    _SEND_SELECTORS = (
        'button[aria-label="Send"]',
        'span[data-icon="send"]',
        'button[data-tab="11"]',
    )

    def __init__(self, profile_dir, headless=False, login_wait_seconds=120, settle_seconds=8):
        self.profile_dir = profile_dir
        self.headless = bool(headless)
        self.login_wait_seconds = int(login_wait_seconds or 120)
        self.settle_seconds = int(settle_seconds or 8)

    def send_text(self, to: str, text: str) -> Tuple[bool, str, str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return False, (
                f"Playwright is not installed in this Python environment ({exc}). "
                "Run: pip install playwright && playwright install chromium"
            ), ""
        number = _normalize_msisdn(to)
        if not number:
            return False, "no recipient (empty WhatsApp number)", ""
        if not text:
            return True, "empty message", ""
        url = _build_wa_web_send_url(number, text)
        try:
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    self.profile_dir,
                    headless=self.headless,
                    args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
                )
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto(url, timeout=60000)
                    box = self._wait_for_compose(page)
                    if box is None:
                        if self._invalid_number(page):
                            return False, (
                                "WhatsApp Web reports this number is invalid / not on WhatsApp. "
                                "Use the full international number with country code."
                            ), ""
                        return False, (
                            "WhatsApp Web is not logged in yet (no chat appeared within "
                            f"{self.login_wait_seconds}s). Run this once with headless:false and scan "
                            "the QR code on your phone (WhatsApp -> Linked devices); the login is then "
                            "remembered for next time."
                        ), ""
                    # The deep link pre-fills the text; click into the box and send.
                    try:
                        box.click()
                        page.wait_for_timeout(400)
                    except Exception:
                        pass
                    if not self._click_send(page):
                        try:
                            box.press('Enter')
                        except Exception as exc:
                            return False, f"could not press Send: {exc}", ""
                    page.wait_for_timeout(min(self.settle_seconds, 15) * 1000)
                    logging.info(f"✅ WhatsApp Web (personal) → {number}: message sent")
                    return True, "ok", ""
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        except Exception as exc:
            return False, f"WhatsApp Web send error: {exc}", ""

    def _wait_for_compose(self, page):
        deadline = time.monotonic() + self.login_wait_seconds
        while time.monotonic() < deadline:
            for sel in self._COMPOSE_SELECTORS:
                try:
                    el = page.query_selector(sel)
                    if el is not None:
                        return el
                except Exception:
                    pass
            try:
                page.wait_for_timeout(1000)
            except Exception:
                time.sleep(1)
        return None

    def _click_send(self, page) -> bool:
        for sel in self._SEND_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el is not None:
                    el.click()
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _invalid_number(page) -> bool:
        try:
            body = (page.inner_text('body') or '').lower()
        except Exception:
            return False
        return (
            'phone number shared via url is invalid' in body
            or "isn't on whatsapp" in body
            or 'is not on whatsapp' in body
        )


# ─────────────────────────────────────────────────────────────
# Meta WhatsApp Cloud API — inbound (official webhook, stdlib HTTP server)
# ─────────────────────────────────────────────────────────────

class _Box:
    captured: Optional[Dict] = None
    event = threading.Event()


def _make_handler(verify_token: str, path: str, box: _Box, rx_from: str, needle: str):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: A003
            try:
                logging.info("webhook: " + (fmt % args))
            except Exception:
                pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query)
            if (parsed.path == path
                    and q.get('hub.mode', [''])[0] == 'subscribe'
                    and q.get('hub.verify_token', [''])[0] == verify_token):
                challenge = q.get('hub.challenge', [''])[0].encode('utf-8')
                self.send_response(200)
                self.end_headers()
                self.wfile.write(challenge)
                logging.info("✅ Webhook verification handshake OK")
            else:
                self.send_response(403)
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b''
            # Ack immediately so Meta doesn't retry.
            self.send_response(200)
            self.end_headers()
            try:
                data = json.loads(raw.decode('utf-8', 'replace'))
                for entry in data.get('entry', []) or []:
                    for change in entry.get('changes', []) or []:
                        value = change.get('value', {}) or {}
                        for m in value.get('messages', []) or []:
                            frm = str(m.get('from') or '')
                            text = ((m.get('text') or {}).get('body')) or m.get('type') or ''
                            if rx_from and _normalize_msisdn(frm) != _normalize_msisdn(rx_from):
                                continue
                            if needle and needle.lower() not in str(text).lower():
                                continue
                            box.captured = {"text": text, "from": frm, "id": m.get('id')}
                            box.event.set()
                            return
            except Exception as exc:
                logging.warning(f"webhook parse error: {exc}")
    return _Handler


def receive_one(wa_cfg: Dict, rx_max_seconds: int, rx_from: str, rx_match: str) -> Optional[Dict]:
    box = _Box()
    box.event = threading.Event()
    box.captured = None
    handler = _make_handler(wa_cfg['verify_token'], wa_cfg['webhook_path'], box,
                            str(rx_from or ''), str(rx_match or ''))
    try:
        server = HTTPServer((wa_cfg['webhook_host'], wa_cfg['webhook_port']), handler)
    except Exception as exc:
        logging.error(f"❌ Could not start webhook server on "
                      f"{wa_cfg['webhook_host']}:{wa_cfg['webhook_port']}: {exc}")
        return None
    server.timeout = 1
    logging.info(f"🌐 Webhook listening on {wa_cfg['webhook_host']}:{wa_cfg['webhook_port']}"
                 f"{wa_cfg['webhook_path']} (verify_token set). Expose it publicly + set it in "
                 f"Meta → WhatsApp → Configuration for real inbound delivery.")
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    t.start()
    got = box.event.wait(timeout=rx_max_seconds)
    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass
    return box.captured if got else None


def emit_section(mode: str, direction: str, recipient: str, status: str,
                 message_id, body: str):
    logging.info(
        "INI_SECTION_WHATSAPPER<<<\n"
        f"mode: {mode}\n"
        f"direction: {direction}\n"
        f"recipient: {recipient}\n"
        f"status: {status}\n"
        f"message_id: {message_id if message_id is not None else ''}\n"
        f"\n"
        f"{body}\n"
        ">>>END_SECTION_WHATSAPPER"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    config = load_config()
    write_pid_file()
    exit_code = 0
    try:
        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)

        wa_cfg = _resolve_whatsapp_cfg(config)
        mode = str(config.get('mode') or 'auto').strip().lower()
        message = str(config.get('message') or '').strip()
        template = _clean(config.get('template'))
        provider = _resolve_provider(config)
        target_agents = config.get('target_agents', []) or []

        logging.info(f"💬 WHATSAPPER AGENT STARTED (provider={provider})")

        do_send = (mode == 'send') or (mode == 'auto' and (message != '' or template != ''))

        if do_send and provider == 'web':
            # ── Mode (i-web): SEND from YOUR OWN number via WhatsApp Web ──
            recipient = _resolve_recipient(config, wa_cfg)
            wa = config.get('whatsapp') or {}
            web_cfg = (wa.get('web') if isinstance(wa, dict) else {}) or {}
            if not isinstance(web_cfg, dict):
                web_cfg = {}
            logging.info(f"📤 SEND mode (WhatsApp Web / personal account) → to={recipient!r}")
            if template:
                logging.warning("⚠️ WhatsApp Web (personal) mode ignores `template` "
                                "(templates are a Cloud-API concept); sending the free-form message.")
            client = WhatsAppWebClient(
                _wa_web_profile_dir(config),
                headless=_as_bool(web_cfg.get('headless', False)),
                login_wait_seconds=int(web_cfg.get('login_wait_seconds') or 120),
                settle_seconds=int(web_cfg.get('settle_seconds') or 8),
            )
            if not recipient:
                ok, info, mid = False, "no recipient (set contact_name or to)", ""
            else:
                ok, info, mid = client.send_text(recipient, message)
            status, body = ('sent', message) if ok else ('failed', info)
            if not ok:
                exit_code = 1
                logging.error(f"❌ WhatsApp Web send failed: {info}")
            emit_section('send', 'out', _normalize_msisdn(recipient), status, mid, body)
        elif do_send:
            # ── Mode (i): SEND via the official Meta Cloud API ──────────
            recipient = _resolve_recipient(config, wa_cfg)
            client = WhatsAppCloudClient(wa_cfg['phone_number_id'], wa_cfg['access_token'],
                                         wa_cfg['graph_base'], wa_cfg['api_version'])
            logging.info(f"📤 SEND mode → to={recipient!r}")
            if not client.configured:
                logging.error("❌ Not configured. Set whatsapp.phone_number_id + whatsapp.access_token "
                              "(or env WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN). "
                              "See HOW_TO_GET_YOUR_WHATSAPP_ASSETS.md")
                ok, info, mid = False, "phone_number_id or access_token missing", ""
            elif template:
                ok, info, mid = client.send_template(
                    recipient, template, _clean(config.get('template_language')) or 'en_US',
                    _coerce_param_list(config.get('template_params')))
            else:
                ok, info, mid = client.send_text(recipient, message)
            if not ok:
                status, body = 'failed', info
                exit_code = 1
            elif template:
                # An APPROVED template DELIVERS even outside the 24-hour window.
                status, body = 'sent', template
            else:
                # A free-form text is only ACCEPTED by Meta; it DELIVERS only inside
                # the recipient's 24-hour customer-service window. Without an inbound
                # delivery webhook we cannot confirm delivery, so report 'accepted'
                # (NOT 'sent') and say how to guarantee arrival.
                status, body = 'accepted', message
                logging.warning(
                    "⚠️ Meta ACCEPTED the text (wamid %s) but a FREE-FORM WhatsApp message "
                    "DELIVERS only inside the 24-hour window: the recipient must have messaged "
                    "THIS number in the last 24h. If it did NOT arrive, that window is closed — "
                    "have them message your number first, OR send an approved TEMPLATE "
                    "(set template='hello_world'); templates deliver anytime.", mid)
            emit_section('send', 'out', _normalize_msisdn(recipient), status, mid, body)
        else:
            # ── Mode (ii)/(iii): RECEIVE ────────────────────────────────
            rx_max = int(config.get('rx_max_seconds') or 60)
            rx_from = str(config.get('rx_from') or '').strip()
            rx_match = str(config.get('rx_match') or '').strip()
            logging.info(f"📥 RECEIVE mode → waiting up to {rx_max}s "
                         f"(from={rx_from or 'any'}, match={rx_match or 'any'})")
            got = receive_one(wa_cfg, rx_max, rx_from, rx_match)
            if got:
                logging.info(f"📨 Message received from {got['from']}: {got['text']!r}")
                emit_section('receive', 'in', got['from'], 'received', got.get('id'), got['text'])
            else:
                logging.info(f"🕒 No message received during {rx_max}s window.")
                emit_section('receive', 'in', rx_from, 'no_message', '', 'NO_MESSAGE_RECEIVED')

        triggered = _start_targets(target_agents)
        logging.info(f"🏁 Whatsapper finished. Triggered {triggered}/{len(target_agents)} agents.")
    except Exception as e:
        logging.error(f"Critical Error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
