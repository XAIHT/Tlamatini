# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Telegrammer Agent — the ONE Telegram send/receive agent.
#
# Uses official Telegram surfaces only:
#   - Bot API over plain HTTPS for bot-safe targets (numeric ids/channels).
#   - Telegram MTProto user session via Telethon when configured, so private
#     @usernames can be messaged by the owner's logged-in Telegram account.
#
# Three run-modes (config `mode`: auto | send | receive):
#   i)  SEND     — send one message, then start target_agents, then die.
#   ii) RECEIVE/timeout — wait up to rx_max_seconds; if NOTHING arrives, report
#                 "no message", start target_agents, die (status=no_message,
#                 Parametrizer-readable).
#   iii) RECEIVE/message — wait up to rx_max_seconds; if a message arrives,
#                 report it, start target_agents, die (status=received, the text
#                 is Parametrizer-readable as response_body).
# `auto` picks SEND when `message` is non-empty, else RECEIVE.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import asyncio
import time
import json
import yaml
import logging
import subprocess
import urllib.parse
import urllib.request
import urllib.error

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

# Set working directory to script location
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


def _resolve_bot_token(config: Dict) -> str:
    tg = config.get('telegram') or {}
    if not isinstance(tg, dict):
        tg = {}
    return _clean(tg.get('bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN'))


# Plain-English ways to say "send AS my own logged-in Telegram account" (the
# user-session / MTProto route) and "send AS the bot" (the Bot API route), so the
# operator can just say "as me" / "as the bot" instead of remembering user/bot.
_USER_PROVIDER_WORDS = frozenset((
    'user', 'mtproto', 'user_account', 'user_session', 'telegram_api',
    'me', 'myself', 'my_self', 'self', 'owner', 'my_account', 'myaccount',
    'personal', 'personal_account', 'my_personal_account', 'account',
    'my_telegram', 'my_telegram_account', 'my_number', 'my_phone',
))
_BOT_PROVIDER_WORDS = frozenset((
    'bot', 'bot_api', 'botapi', 'telegram_bot', 'the_bot', 'a_bot',
    'bot_account', 'robot', 'botfather',
))


def _normalize_provider_word(value: str) -> str:
    """Lowercase a provider string and collapse spaces/hyphens to underscores,
    then strip a leading 'send_'/'as_' so 'send as me' == 'as me' == 'me' and
    'as the bot' == 'the bot'."""
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
    tg = config.get('telegram') or {}
    if not isinstance(tg, dict):
        tg = {}
    raw = _clean(config.get('provider') or tg.get('provider') or os.environ.get('TELEGRAM_PROVIDER'))
    provider = _normalize_provider_word(raw) or 'auto'
    if provider in _USER_PROVIDER_WORDS:
        return 'user'
    if provider in _BOT_PROVIDER_WORDS:
        return 'bot'
    if provider in ('auto', 'bot', 'user'):
        return provider
    logging.warning(f"Unknown Telegram provider {raw!r}; using auto.")
    return 'auto'


def _stable_state_dir() -> str:
    candidates = []
    explicit = (os.environ.get('TLAMATINI_STATE_DIR') or '').strip()
    if explicit:
        candidates.append(explicit)
    contacts_path = (os.environ.get('TLAMATINI_CONTACTS') or '').strip()
    if contacts_path:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(contacts_path)), '.tlamatini'))
    exe = os.path.abspath(sys.executable)
    exe_parent = os.path.dirname(exe)
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


def _resolve_user_session_cfg(config: Dict) -> Dict:
    tg = config.get('telegram') or {}
    if not isinstance(tg, dict):
        tg = {}
    session_name = _clean(
        tg.get('session_name')
        or tg.get('session_path')
        or config.get('telegram_session_name')
        or os.environ.get('TELEGRAM_SESSION_NAME')
        or 'telegrammer_user_session'
    )
    if session_name and not os.path.isabs(session_name):
        session_name = os.path.join(_stable_state_dir(), session_name)
    return {
        'api_id': _clean(tg.get('api_id') or config.get('telegram_api_id') or os.environ.get('TELEGRAM_API_ID') or os.environ.get('TELETLAMATINI_API_ID')),
        'api_hash': _clean(tg.get('api_hash') or config.get('telegram_api_hash') or os.environ.get('TELEGRAM_API_HASH') or os.environ.get('TELETLAMATINI_API_HASH')),
        'session_string': _clean(
            tg.get('session_string')
            or config.get('telegram_session_string')
            or os.environ.get('TELEGRAM_SESSION_STRING')
        ),
        'session_name': session_name,
    }


def _user_session_configured(cfg: Dict) -> bool:
    return bool(cfg.get('api_id') and cfg.get('api_hash') and (cfg.get('session_string') or cfg.get('session_name')))


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
    import unicodedata

    def _n(value: str) -> str:
        s = ' '.join(str(value or '').strip().lower().split())
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

    needle = _n(query)
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
        return [_n(n) for n in raw if str(n or '').strip()]

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


def _resolve_recipient_detail(config: Dict) -> Tuple[str, str]:
    tg = config.get('telegram') or {}
    contact_name = str(config.get('contact_name') or tg.get('contact_name') or '').strip()
    default_chat_id = str(config.get('chat_id') or tg.get('chat_id') or '').strip()
    if contact_name:
        # Try the contacts book FIRST so self-words ('me' / 'myself') resolve to the
        # owner's OWN contact when one exists (e.g. 'me' → @blackangy). Only fall back
        # to the configured default telegram.chat_id when no contact matched.
        resolved = _resolve_contact(contact_name, 'telegram')
        if resolved:
            logging.info(f"📇 Resolved contact '{contact_name}' → Telegram '{resolved}'")
            return resolved, 'contact_name'
        if contact_name.lower() in ('me', 'myself', 'self', 'owner', 'default'):
            if default_chat_id:
                logging.info(f"📇 Contact '{contact_name}' means configured default Telegram chat_id")
                return default_chat_id, 'default_chat_id'
            logging.error("❌ Contact 'me' requested but telegram.chat_id is empty and no 'me' contact exists.")
            return '', 'missing_default_chat_id'
        logging.error(f"❌ Contact '{contact_name}' not found (or has no 'telegram') in contacts.json")
        return '', 'missing_contact'
    return default_chat_id, 'chat_id'


def _resolve_recipient(config: Dict) -> str:
    recipient, _source = _resolve_recipient_detail(config)
    return recipient


# ─────────────────────────────────────────────────────────────
# Telegram Bot API (official, stdlib only)
# ─────────────────────────────────────────────────────────────

def _api(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def tg_send_message(token: str, chat_id: str, text: str) -> Tuple[bool, str, str]:
    if not token:
        return False, "telegram.bot_token missing", ""
    if not chat_id:
        return False, "no recipient (telegram.chat_id or contact_name)", ""
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        _api(token, "sendMessage"),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        if body.get("ok"):
            mid = str(((body.get("result") or {}).get("message_id")) or "")
            logging.info(f"✅ Telegram sent (message_id {mid})")
            return True, "ok", mid
        return False, f"API error: {body.get('description')}", ""
    except urllib.error.HTTPError as exc:
        try:
            err = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err = str(exc)
        return False, f"HTTPError {exc.code}: {err[:300]}", ""
    except Exception as exc:
        return False, f"send error: {exc}", ""


async def _tg_user_send_message_async(user_cfg: Dict, recipient: str, text: str) -> Tuple[bool, str, str]:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:
        return False, f"Telethon is not installed in this Python environment: {exc}", ""

    try:
        api_id = int(str(user_cfg.get('api_id') or '').strip())
    except Exception:
        return False, "telegram.api_id must be numeric for Telegram user-session sends", ""
    api_hash = str(user_cfg.get('api_hash') or '').strip()
    if not api_id or not api_hash:
        return False, "telegram.api_id and telegram.api_hash are required for Telegram user-session sends", ""
    if not recipient:
        return False, "no recipient (telegram.chat_id or contact_name)", ""
    if not text:
        return True, "empty message", ""

    session_string = str(user_cfg.get('session_string') or '').strip()
    session_name = str(user_cfg.get('session_name') or '').strip() or os.path.join(script_dir, 'telegrammer_user_session')
    session = StringSession(session_string) if session_string else session_name
    client = TelegramClient(session, api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return (
                False,
                "Telegram user session is not authorized yet. Log in once with the official "
                "Telegram API credentials/session, or let Telegrammer learn the Bot API route from the local cache.",
                "",
            )
        msg = await client.send_message(recipient, text)
        mid = str(getattr(msg, 'id', '') or '')
        logging.info(f"✅ Telegram user-session sent → {recipient} (message_id {mid})")
        return True, "ok", mid
    except Exception as exc:
        return False, f"Telegram user-session send error: {exc}", ""
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def tg_user_send_message(user_cfg: Dict, recipient: str, text: str) -> Tuple[bool, str, str]:
    return asyncio.run(_tg_user_send_message_async(user_cfg, recipient, text))


def tg_get_updates(token: str, offset: Optional[int], timeout: int) -> Dict:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    url = _api(token, "getUpdates") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout + 15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def tg_get_chat(token: str, chat_id: str) -> Dict:
    params = {"chat_id": chat_id}
    url = _api(token, "getChat") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _looks_numeric(value: str) -> bool:
    """A Telegram numeric chat id (users positive, groups negative)."""
    return str(value or "").lstrip("-").isdigit()


def _looks_username(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("@") and len(text) > 1


def _username_key(value: str) -> str:
    return "@" + str(value or "").strip().lstrip("@").lower()


def _username_cache_path() -> str:
    return os.path.join(_stable_state_dir(), "telegrammer_username_cache.json")


def _username_cache_load() -> Dict:
    try:
        with open(_username_cache_path(), "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _username_cache_save(data: Dict) -> None:
    path = _username_cache_path()
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception as exc:
        logging.warning(f"Could not update Telegram username cache: {exc}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _username_cache_get(username: str) -> str:
    data = _username_cache_load()
    entry = data.get(_username_key(username))
    if not isinstance(entry, dict):
        return ""
    # Keep username routes durable. Official lookups update this when Telegram
    # exposes a newer route, but @username configs should not rot every few days.
    chat_id = str(entry.get("chat_id") or "").strip()
    return chat_id if _looks_numeric(chat_id) else ""


def _username_cache_put(username: str, chat_id: str, source: str) -> None:
    if not _looks_username(username) or not _looks_numeric(chat_id):
        return
    data = _username_cache_load()
    data[_username_key(username)] = {
        "chat_id": str(chat_id).strip(),
        "source": source,
        "updated_at": time.time(),
    }
    _username_cache_save(data)


def _chat_username_matches(chat: Dict, username: str) -> bool:
    result = chat.get("result") if isinstance(chat, dict) else {}
    if not isinstance(result, dict):
        return False
    got = str(result.get("username") or "").strip()
    return bool(got) and _username_key(got) == _username_key(username)


def _scan_updates_for_username(token: str, username: str) -> Tuple[str, str]:
    uname = _username_key(username).lstrip("@")
    try:
        data = tg_get_updates(token, None, 0)
    except Exception as exc:
        return "", f"could not read updates to resolve {username}: {exc}"
    for upd in reversed(data.get("result") or []):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
        frm = msg.get("from") or {}
        chat = msg.get("chat") or {}
        candidates = (
            (frm.get("username"), (frm.get("id") or chat.get("id")), "getUpdates.from"),
            (chat.get("username"), chat.get("id"), "getUpdates.chat"),
        )
        for cand_user, cand_id, source in candidates:
            if str(cand_user or "").lower() == uname and cand_id:
                cid = str(cand_id)
                if _looks_numeric(cid):
                    _username_cache_put(username, cid, source)
                    return cid, f"resolved {username} -> Bot API route from {source}"
    return "", (
        f"{username} not found in the bot's recent updates. For a private user, they must press "
        f"Start or message the bot once so the Bot API can legally address them, OR configure "
        f"Telegrammer's official user session so @username can be used directly."
    )


def resolve_send_chat_id(token: str, recipient: str) -> Tuple[str, str]:
    """Turn a recipient into something the Bot API's sendMessage accepts.

    The Telegram Bot API can only DM a USER by their NUMERIC chat id — a user
    @username is not generally resolvable by bots. A public @channelusername can
    resolve through getChat, and private users can be resolved only if the bot has
    seen them in getUpdates. So: numeric -> use directly; @name -> cache, getChat,
    then getUpdates; if none is found, pass @name through only as a last public
    channel/group attempt.
    Returns (send_target, note)."""
    rec = str(recipient or "").strip()
    if not rec:
        return "", "empty recipient"
    if _looks_numeric(rec):
        return rec, "numeric chat id"
    if _looks_username(rec):
        cached = _username_cache_get(rec)
        if cached:
            return cached, f"resolved {rec} -> Bot API route from local username cache"
        try:
            chat = tg_get_chat(token, rec)
            result = chat.get("result") if isinstance(chat, dict) else {}
            cid = str((result or {}).get("id") or "")
            if cid and _chat_username_matches(chat, rec):
                _username_cache_put(rec, cid, "Bot API getChat")
                return cid, f"resolved {rec} -> chat id from Bot API getChat"
        except Exception as exc:
            logging.info(f"   ↳ Bot API getChat could not resolve {rec}: {exc}")
        cid, note = _scan_updates_for_username(token, rec)
        if cid:
            return cid, note
        return rec, note
    return rec, "passthrough"


def _should_use_user_provider(provider: str, user_cfg: Dict, recipient: str, source: str) -> bool:
    if provider == 'user':
        return True
    if provider == 'bot':
        return False
    if not _user_session_configured(user_cfg):
        return False
    rec = str(recipient or '').strip()
    if _looks_username(rec):
        return True
    if rec.startswith('+'):
        return True
    return False


def _private_username_needs_user_session(recipient: str, source: str) -> bool:
    return source == 'contact_name' and _looks_username(recipient)


def _username_lookup_requires_user_session(recipient: str, source: str, send_target: str) -> bool:
    return source == 'contact_name' and _looks_username(recipient) and send_target == recipient


def receive_one(token: str, rx_max_seconds: int, rx_from_chat_id: str,
                rx_match: str) -> Optional[Dict]:
    """Long-poll getUpdates for up to rx_max_seconds. Returns the first matching
    message dict {text, chat_id, message_id, sender} or None on timeout."""
    rx_from = str(rx_from_chat_id or '').strip()
    needle = str(rx_match or '').strip().lower()
    # Skip any backlog so we only catch messages that arrive during the window.
    offset: Optional[int] = None
    try:
        d = tg_get_updates(token, -1, 0)
        res = d.get("result") or []
        if res:
            offset = res[-1]["update_id"] + 1
    except Exception as exc:
        logging.warning(f"⚠️ Initial getUpdates failed (continuing): {exc}")

    start = time.monotonic()
    while time.monotonic() - start < rx_max_seconds:
        remaining = rx_max_seconds - (time.monotonic() - start)
        long_poll = max(1, min(25, int(remaining)))
        try:
            d = tg_get_updates(token, offset, long_poll)
        except urllib.error.HTTPError as exc:
            # 409 = a webhook is set on this bot; getUpdates can't be used then.
            logging.error(f"❌ getUpdates HTTP {exc.code} (a webhook may be set on the bot). Retrying...")
            time.sleep(2)
            continue
        except Exception as exc:
            logging.warning(f"⚠️ getUpdates error: {exc}")
            time.sleep(2)
            continue
        if not d.get("ok"):
            logging.warning(f"⚠️ getUpdates not ok: {d.get('description')}")
            time.sleep(2)
            continue
        for upd in d.get("result") or []:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("channel_post") or {}
            if not msg:
                continue
            text = msg.get("text") or msg.get("caption") or ""
            chat = msg.get("chat") or {}
            cid = str(chat.get("id") or "")
            if rx_from and cid != rx_from:
                continue
            if needle and needle not in text.lower():
                continue
            sender = ((msg.get("from") or {}).get("username")
                      or (msg.get("from") or {}).get("first_name") or "")
            return {"text": text, "chat_id": cid, "message_id": msg.get("message_id"), "sender": sender}
    return None


def emit_section(mode: str, direction: str, chat_id: str, status: str,
                 message_id, body: str):
    logging.info(
        "INI_SECTION_TELEGRAMMER<<<\n"
        f"mode: {mode}\n"
        f"direction: {direction}\n"
        f"chat_id: {chat_id}\n"
        f"status: {status}\n"
        f"message_id: {message_id if message_id is not None else ''}\n"
        f"\n"
        f"{body}\n"
        ">>>END_SECTION_TELEGRAMMER"
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def _do_user_login(user_cfg: Dict) -> bool:
    """One-time interactive login of YOUR Telegram account (Telethon) so
    Telegrammer can resolve and message ANY @username at runtime, forever.
    It does NOT create, change, or delete your bot - it logs in your own user
    account (the only account type Telegram lets resolve @usernames). Run once
    in a visible console; it asks for your phone + the code Telegram sends."""
    try:
        from telethon import TelegramClient
    except Exception as exc:
        logging.error("Telethon is not installed in this Python: %s -- run: pip install telethon", exc)
        return False
    try:
        api_id = int(str(user_cfg.get("api_id") or "").strip())
    except Exception:
        api_id = 0
    api_hash = str(user_cfg.get("api_hash") or "").strip()
    if not api_id or not api_hash:
        logging.error(
            "Need telegram.api_id + telegram.api_hash to log in. Get them FREE at "
            "https://my.telegram.org (API development tools), put them in the Telegrammer "
            "config or the Access Keys Wizard, then run login again."
        )
        return False
    session_name = str(user_cfg.get("session_name") or "").strip() or os.path.join(
        _stable_state_dir(), "telegrammer_user_session"
    )
    logging.info("=" * 60)
    logging.info("TELEGRAMMER ONE-TIME LOGIN - logs in YOUR Telegram account so it")
    logging.info("can message ANY @username. It does NOT touch or delete your bot.")
    logging.info("You will be asked for your phone, then the code Telegram sends you.")
    logging.info("=" * 60)
    client = TelegramClient(session_name, api_id, api_hash)
    try:
        client.start()
        me = client.loop.run_until_complete(client.get_me())
        who = ("@" + me.username) if getattr(me, "username", None) else (getattr(me, "first_name", "") or "your account")
        logging.info("\u2705 Logged in as %s. Session saved at %s -- Telegrammer can now send to any @username.", who, session_name)
        return True
    except Exception as exc:
        logging.error("\u274c Telegram login failed: %s", exc)
        return False
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def _launch_interactive_login(user_cfg: Dict) -> bool:
    """Pop a VISIBLE console so the user logs in their own Telegram account ONCE
    (phone + the code Telegram sends), wait for it to finish, then let the caller
    retry the send. Mirrors Executer's PROVEN forked-window recipe (a wrapper .bat
    launched via cmd.exe /c with CREATE_NEW_CONSOLE + a forced-visible STARTUPINFO)
    so the window RELIABLY appears on the user's desktop even when this agent runs
    headless from the chat. It does NOT create, change, or delete the bot - it logs
    in the user account that can resolve @usernames (the only account Telegram lets)."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        py = list(get_python_command())
    except Exception:
        py = [sys.executable]
    py_exe = py[0] if py else sys.executable
    runner = os.path.join(here, "_tg_login_runner.py")
    try:
        with open(runner, "w", encoding="utf-8") as f:
            f.write(
                "import telegrammer as T\n"
                "T._do_user_login(T._resolve_user_session_cfg(T.load_config()))\n"
                "try:\n"
                "    input(chr(10) + 'Login finished - press Enter to close this window...')\n"
                "except Exception:\n"
                "    pass\n"
            )
    except Exception as exc:
        logging.error("Could not write the Telegram login runner: %s", exc)
        return False
    try:
        logging.info("Opening the one-time Telegram login window "
                     "(type your phone, then the code Telegram sends; close it when done).")
        if os.name == "nt":
            wrapper = os.path.join(here, "_tg_login_window.bat")
            with open(wrapper, "w", encoding="utf-8") as wf:
                wf.write("@echo off\r\n")
                wf.write("title Telegram one-time login\r\n")
                wf.write('cd /d "' + here + '"\r\n')
                wf.write('"' + py_exe + '" "' + runner + '"\r\n')
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1  # SW_SHOWNORMAL - force the window visible
            proc = subprocess.Popen(
                # The trailing token is a watchdog/reaper EXEMPTION MARKER: both
                # command_watchdog and orphan_reaper recognise it (and the
                # _tg_login* file names) and NEVER kill this login window, however
                # long the user takes to type the phone + code.
                ["cmd.exe", "/c", wrapper, "TLAMATINI_KEEP_CONSOLE_ALIVE"],
                cwd=here, env=get_agent_env(),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=si,
            )
        else:
            proc = subprocess.Popen(py + [runner], cwd=here, env=get_agent_env())
        proc.wait()
        return True
    except Exception as exc:
        logging.error("Could not open the Telegram login window: %s", exc)
        return False


def _user_send_with_autologin(user_cfg: Dict, recipient: str, text: str) -> Tuple[bool, str, str]:
    """Send via the user session. If there is no authorized session yet, pop the
    ONE-TIME setup window (phone + code), wait for the user, then retry once.

    Behaviour the user sees:
      * First send on a fresh install -> setup window appears.
      * Window closed WITHOUT finishing -> a clear "setup interrupted" message,
        nothing sent, bot untouched; the NEXT send re-opens the window.
      * Setup finished -> the message is sent, and every later send goes straight
        through with NO window for the life of this installation.
      * Only deleting C:\\Tlamatini + reinstalling brings the window back once."""
    ok, info, mid = tg_user_send_message(user_cfg, recipient, text)
    if ok or ("not authorized" not in (info or "").lower()):
        return ok, info, mid

    logging.info("No authorized Telegram session yet - opening the one-time setup window...")
    _launch_interactive_login(user_cfg)

    # The window has closed. Try exactly once more with whatever session now exists.
    ok, info, mid = tg_user_send_message(user_cfg, recipient, text)
    if (not ok) and ("not authorized" in (info or "").lower()):
        logging.info("Telegram setup interrupted - no session was created; will re-prompt next send.")
        info = (
            "Telegram initial setup was INTERRUPTED: the login window was closed before it "
            "finished (your phone number + the code Telegram sends you). Nothing was sent and "
            "your bot was NOT touched. Just ask me to send the Telegram again - the setup window "
            "will reappear; once you complete it the message goes through, and you will not be "
            "asked again on this installation."
        )
    return ok, info, mid


def main():
    config = load_config()
    write_pid_file()
    exit_code = 0
    try:
        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)

        provider = _resolve_provider(config)
        token = _resolve_bot_token(config)
        user_cfg = _resolve_user_session_cfg(config)
        mode = str(config.get('mode') or 'auto').strip().lower()
        message = str(config.get('message') or '').strip()
        target_agents = config.get('target_agents', []) or []

        logging.info(f"✈️ TELEGRAMMER AGENT STARTED (official provider={provider})")
        if provider != 'user' and not token:
            logging.error("❌ No Bot Token. Set telegram.bot_token (or env TELEGRAM_BOT_TOKEN). "
                          "See HOW_TO_GET_YOUR_TELEGRAM_ASSETS.md")
        if provider == 'user' and not _user_session_configured(user_cfg):
            logging.error("❌ Telegram user-session provider selected, but telegram.api_id/api_hash/session are missing.")

        do_send = (mode == 'send') or (mode == 'auto' and message != '')

        if mode == 'login':
            _do_user_login(user_cfg)
        elif do_send:
            # ── Mode (i): SEND ──────────────────────────────────────────
            chat_id, recipient_source = _resolve_recipient_detail(config)
            logging.info(f"📤 SEND mode → recipient={chat_id!r} (source={recipient_source})")
            send_target = chat_id
            if _should_use_user_provider(provider, user_cfg, chat_id, recipient_source):
                logging.info("   ↳ Using official Telegram user-session API for this recipient.")
                ok, info, mid = _user_send_with_autologin(user_cfg, chat_id, message)
            elif provider == 'user':
                ok, info, mid = False, "Telegram user-session provider is not fully configured", ""
            else:
                send_target, note = resolve_send_chat_id(token, chat_id) if token else (chat_id, "")
                if note:
                    logging.info(f"   ↳ {note}")
                if _username_lookup_requires_user_session(chat_id, recipient_source, send_target):
                    info = (
                        f"{note} Keep @username in contacts/configs, but configure Telegrammer with "
                        "an authorized official Telegram user session (telegram.api_id, telegram.api_hash, "
                        "and telegram.session_name/session_string), or have that user press Start/message "
                        "the bot once so the Bot API can cache the address."
                    )
                    logging.error(f"❌ {info}")
                    ok, mid = False, ""
                else:
                    ok, info, mid = tg_send_message(token, send_target, message)
            status = 'sent' if ok else 'failed'
            if not ok:
                logging.error(f"❌ Telegram send failed: {info}")
                exit_code = 1
            emit_section('send', 'out', chat_id, status, mid, message if ok else info)
        else:
            # ── Mode (ii)/(iii): RECEIVE ────────────────────────────────
            rx_max = int(config.get('rx_max_seconds') or 60)
            rx_from = str(config.get('rx_from_chat_id') or '').strip()
            rx_match = str(config.get('rx_match') or '').strip()
            logging.info(f"📥 RECEIVE mode → waiting up to {rx_max}s "
                         f"(from={rx_from or 'any'}, match={rx_match or 'any'})")
            got = None
            if token:
                got = receive_one(token, rx_max, rx_from, rx_match)
            if got:
                # (iii) message received
                logging.info(f"📨 Message received from {got['chat_id']} "
                             f"(@{got.get('sender')}): {got['text']!r}")
                emit_section('receive', 'in', got['chat_id'], 'received',
                             got.get('message_id'), got['text'])
            else:
                # (ii) nothing received within the window
                logging.info(f"🕒 No message received during {rx_max}s window.")
                emit_section('receive', 'in', rx_from, 'no_message', '',
                             'NO_MESSAGE_RECEIVED')

        # ALL modes: start outputs, then die.
        triggered = _start_targets(target_agents)
        logging.info(f"🏁 Telegrammer finished. Triggered {triggered}/{len(target_agents)} agents.")
    except Exception as e:
        logging.error(f"Critical Error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
