# Telegrammer Agent — the ONE Telegram send/receive agent.
#
# Uses ONLY Telegram's OFFICIAL Bot API over plain HTTPS (stdlib urllib) — no
# third-party library, no Telethon, no gateway. Get a Bot Token from @BotFather
# (see HOW_TO_GET_YOUR_TELEGRAM_ASSETS.md).
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


def _resolve_recipient(config: Dict) -> str:
    tg = config.get('telegram') or {}
    contact_name = str(config.get('contact_name') or tg.get('contact_name') or '').strip()
    if contact_name:
        resolved = _resolve_contact(contact_name, 'telegram')
        if resolved:
            logging.info(f"📇 Resolved contact '{contact_name}' → Telegram '{resolved}'")
            return resolved
        logging.error(f"❌ Contact '{contact_name}' not found (or has no 'telegram') in contacts.json")
        return ''
    return str(config.get('chat_id') or tg.get('chat_id') or '').strip()


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
            logging.info(f"✅ Telegram sent → {chat_id} (message_id {mid})")
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


def tg_get_updates(token: str, offset: Optional[int], timeout: int) -> Dict:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    url = _api(token, "getUpdates") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout + 15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _looks_numeric(value: str) -> bool:
    """A Telegram numeric chat id (users positive, groups negative)."""
    return str(value or "").lstrip("-").isdigit()


def resolve_send_chat_id(token: str, recipient: str) -> Tuple[str, str]:
    """Turn a recipient into something the Bot API's sendMessage accepts.

    The Telegram Bot API can only DM a USER by their NUMERIC chat id — a user
    @username is NOT resolvable by the API. A public @channelusername IS accepted
    as-is. So: numeric → use directly; '@name' → scan getUpdates for a user who
    messaged the bot with that username and use their numeric chat id; if none is
    found, pass '@name' through (works only for public channels).
    Returns (send_target, note)."""
    rec = str(recipient or "").strip()
    if not rec:
        return "", "empty recipient"
    if _looks_numeric(rec):
        return rec, "numeric chat id"
    if rec.startswith("@"):
        uname = rec[1:].lower()
        try:
            data = tg_get_updates(token, None, 0)
        except Exception as exc:
            return rec, f"could not read updates to resolve {rec}: {exc}"
        for upd in reversed(data.get("result") or []):
            msg = upd.get("message") or upd.get("channel_post") or {}
            frm = msg.get("from") or {}
            if str(frm.get("username") or "").lower() == uname:
                cid = str((msg.get("chat") or {}).get("id") or "")
                if cid:
                    return cid, f"resolved {rec} -> numeric chat id {cid} (from getUpdates)"
        return rec, (f"{rec} not found in the bot's recent updates. For a USER, they must send the "
                     f"bot a message first so it learns their numeric id; OR give the numeric chat "
                     f"id directly. (Passing @name through only works for public channels.)")
    return rec, "passthrough"


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

def main():
    config = load_config()
    write_pid_file()
    exit_code = 0
    try:
        if _IS_REANIMATED:
            logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
            logging.info("=" * 60)

        token = _resolve_bot_token(config)
        mode = str(config.get('mode') or 'auto').strip().lower()
        message = str(config.get('message') or '').strip()
        target_agents = config.get('target_agents', []) or []

        logging.info("✈️ TELEGRAMMER AGENT STARTED (official Telegram Bot API)")
        if not token:
            logging.error("❌ No Bot Token. Set telegram.bot_token (or env TELEGRAM_BOT_TOKEN). "
                          "See HOW_TO_GET_YOUR_TELEGRAM_ASSETS.md")

        do_send = (mode == 'send') or (mode == 'auto' and message != '')

        if do_send:
            # ── Mode (i): SEND ──────────────────────────────────────────
            chat_id = _resolve_recipient(config)
            logging.info(f"📤 SEND mode → recipient={chat_id!r}")
            send_target, note = resolve_send_chat_id(token, chat_id) if token else (chat_id, "")
            if note:
                logging.info(f"   ↳ {note}")
            ok, info, mid = tg_send_message(token, send_target, message)
            status = 'sent' if ok else 'failed'
            if not ok:
                logging.error(f"❌ Telegram send failed: {info}")
                exit_code = 1
            emit_section('send', 'out', send_target or chat_id, status, mid, message if ok else info)
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
