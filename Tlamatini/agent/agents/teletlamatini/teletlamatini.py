# TeleTlamatini Agent - Long-running Telegram bridge to the Tlamatini chat core.
#
# Behavior overview (mirrors agent_page.html's chat from Telegram):
#   A) Stays alive waiting for user messages on Telegram.
#   B) On the first message from a chat, asks for a configured password.
#   C) Wrong password -> gentle rejection. Correct password -> welcome message.
#   D) Once authenticated, the next message is treated as a Tlamatini request.
#   E) An LLM-aided check classifies whether the request is clear and complete.
#   F) If unclear, the agent asks follow-up questions until the request is complete.
#   G) Once complete, the request is forwarded to the local Tlamatini chat
#      (Multi-Turn + Exec Report enabled) over the same WebSocket the browser uses.
#   H) If, while processing, the underlying Tlamatini chat asks for additional
#      input (the agent loop emits a clarification), TeleTlamatini relays the
#      question to the Telegram user and pauses until the user replies.
#   I) The full Tlamatini answer (including the per-agent Exec Report tables) is
#      converted to plain text and sent back to the Telegram user.
#
# After every successfully completed request cycle, the configured target_agents
# are launched (long-running active agent semantics, like Gatewayer's dispatcher).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import json
import yaml
import logging
import asyncio
import re
import html
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, List

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

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
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


# ---------------------------------------------------------------------------
# Config / PID helpers (verbatim from telegramer.py — see Step 1 of the agent
# creation skill; do not modify these utility functions).
# ---------------------------------------------------------------------------

PID_FILE = "agent.pid"
REANIM_STATE_FILE = "reanim.state"


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
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
            logging.error(
                f"WAITING FOR AGENTS TO STOP: {still_running} still running "
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
        except Exception:
            return


# ---------------------------------------------------------------------------
# Per-chat conversation state (persisted to reanim.state for pause/resume)
# ---------------------------------------------------------------------------

# State machine phases
PHASE_AWAIT_PASSWORD = "AWAIT_PASSWORD"
PHASE_AWAIT_REQUEST = "AWAIT_REQUEST"
PHASE_PROCESSING = "PROCESSING"
PHASE_AWAIT_INFO = "AWAIT_INFO"


def load_reanim_state() -> Dict[str, Any]:
    if os.path.exists(REANIM_STATE_FILE):
        try:
            with open(REANIM_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to read reanim state: {e}")
    return {}


def save_reanim_state(state: Dict[str, Any]):
    try:
        with open(REANIM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:
        logging.error(f"Failed to write reanim state: {e}")


# ---------------------------------------------------------------------------
# LLM-aided request understanding (uses local Ollama, like Prompter)
# ---------------------------------------------------------------------------

def _classify_request_completeness(host: str, model: str, instruction: str,
                                   conversation: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Ask the LLM whether the accumulated request from the user is clear and
    complete. Returns {"complete": bool, "ask": "<follow-up question>"}.

    On any error the function fails OPEN (treats the request as complete) so
    the agent does not block the user with infinite clarification rounds when
    the LLM is unreachable.
    """
    transcript_lines = []
    for turn in conversation:
        role = turn.get('role', 'user').upper()
        content = (turn.get('content') or '').strip()
        if content:
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)
    prompt = f"{instruction}\n\nCONVERSATION:\n{transcript}\n\nJSON:"

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
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = (body.get("response") or "").strip()
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if not match:
            logging.warning(f"Completeness classifier returned no JSON: {text[:200]}")
            return {"complete": True, "ask": ""}
        parsed = json.loads(match.group(0))
        return {
            "complete": bool(parsed.get("complete", True)),
            "ask": str(parsed.get("ask") or "").strip(),
        }
    except Exception as e:
        logging.error(f"LLM completeness check failed (failing open): {e}")
        return {"complete": True, "ask": ""}


# ---------------------------------------------------------------------------
# Tlamatini WebSocket bridge — behaves like agent_page.html's chat client.
# ---------------------------------------------------------------------------

def _strip_html_to_text(html_content: str) -> str:
    """
    Convert the LLM HTML response (including BEGIN-CODE blocks and exec-report
    tables) into a Telegram-friendly plain-text rendering.
    """
    if not html_content:
        return ""
    text = html_content
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:div|tr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:td|th)[^>]*>', ' | ', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:pre|code)[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def _login_and_chat_via_websocket(
    base_url: str,
    ws_url: str,
    username: str,
    password: str,
    user_message: str,
    multi_turn_enabled: bool,
    exec_report_enabled: bool,
    response_idle_timeout: float,
    total_timeout: float,
) -> str:
    """
    Authenticate against the Tlamatini Django server and run a single chat
    exchange over the same WebSocket the browser uses. Returns the assembled
    HTML answer (incl. exec-report tables when enabled).
    """
    import requests
    import websockets

    session = requests.Session()
    login_page_url = f"{base_url.rstrip('/')}/"
    login_response = session.get(login_page_url, timeout=30)
    csrf_token = session.cookies.get('csrftoken')
    if not csrf_token:
        match = re.search(
            r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']',
            login_response.text,
        )
        if match:
            csrf_token = match.group(1)
    if not csrf_token:
        raise RuntimeError("Could not obtain CSRF token from Tlamatini login page")

    post_response = session.post(
        login_page_url,
        data={
            'username': username,
            'password': password,
            'csrfmiddlewaretoken': csrf_token,
        },
        headers={'Referer': login_page_url},
        allow_redirects=False,
        timeout=30,
    )
    if post_response.status_code not in (301, 302, 303):
        raise RuntimeError(
            f"Tlamatini login failed: HTTP {post_response.status_code}"
        )

    cookies = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])

    final_response_parts: List[str] = []
    last_event_at = time.monotonic()
    response_started = False

    async with websockets.connect(
        ws_url,
        additional_headers={'Cookie': cookies},
        max_size=None,
        ping_interval=20,
    ) as ws:
        # Wait for the agent_ready message before sending our user input.
        ready_deadline = time.monotonic() + 60
        while time.monotonic() < ready_deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get('type') == 'agent_message' and data.get('username') == 'Tlamatini':
                msg = data.get('message') or ''
                if 'ready' in msg.lower() or 'fallback' in msg.lower() or 'restored' in msg.lower():
                    break
        # Send the chat message
        await ws.send(json.dumps({
            'message': user_message,
            'multi_turn_enabled': bool(multi_turn_enabled),
            'exec_report_enabled': bool(exec_report_enabled),
        }))

        deadline = time.monotonic() + float(total_timeout)
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                if response_started and (time.monotonic() - last_event_at) >= response_idle_timeout:
                    break
                continue
            last_event_at = time.monotonic()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get('type') != 'agent_message':
                continue
            if data.get('username') != 'Tlamatini':
                continue
            msg = data.get('message') or ''
            lowered = msg.lower()
            if msg in ('ping',) or '|' in msg or 'establishment' in lowered:
                continue
            if any(marker in lowered for marker in (
                'still loading', 'agent is loading', 'loading the agent',
                'reestablished', 'reanimated',
            )):
                continue
            response_started = True
            final_response_parts.append(msg)
            # Heuristic: if the message is non-trivial and a real LLM answer,
            # we still wait for `response_idle_timeout` to confirm no further
            # appended payloads (e.g., follow-up messages) are coming.

    return "\n".join(part for part in final_response_parts if part).strip()


# ---------------------------------------------------------------------------
# Telegram glue
# ---------------------------------------------------------------------------

async def _send_telegram_text(client, chat, text: str):
    """Send a long text in 4000-char chunks (Telegram message limit is 4096)."""
    if not text:
        return
    chunk_size = 3800
    pieces = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)] or [text]
    for piece in pieces:
        try:
            await client.send_message(chat, piece)
        except Exception as e:
            logging.error(f"Failed to send Telegram message chunk: {e}")
            break


async def _telegram_main_loop(config: Dict[str, Any]):
    from telethon import TelegramClient, events

    telegram_cfg = config.get('telegram', {}) or {}
    api_id = telegram_cfg.get('api_id')
    api_hash = telegram_cfg.get('api_hash')
    listen_chat = telegram_cfg.get('listen_chat', 'me')
    bot_token = (telegram_cfg.get('bot_token') or '').strip()

    access_cfg = config.get('access', {}) or {}
    expected_password = str(access_cfg.get('password') or '').strip()
    welcome_message = access_cfg.get('welcome_message') or "Welcome."
    rejection_message = access_cfg.get('rejection_message') or "Authentication failed."
    password_prompt = access_cfg.get('password_prompt') or "Please send the password."
    unclear_prompt = access_cfg.get('unclear_request_prompt') or "Could you clarify?"
    awaiting_info_intro = access_cfg.get('awaiting_info_intro') or "Need more info:"
    processing_message = access_cfg.get('processing_message') or "Working on it..."
    completed_prefix = access_cfg.get('completed_prefix') or "Result:"
    error_prefix = access_cfg.get('error_prefix') or "Error:"

    tlamatini_cfg = config.get('tlamatini', {}) or {}
    base_url = tlamatini_cfg.get('base_url', 'http://127.0.0.1:8000')
    ws_url = tlamatini_cfg.get('ws_url', 'ws://127.0.0.1:8000/ws/agent/')
    tla_user = tlamatini_cfg.get('username', 'user')
    tla_pass = tlamatini_cfg.get('password', 'changeme')
    multi_turn_enabled = bool(tlamatini_cfg.get('multi_turn_enabled', True))
    exec_report_enabled = bool(tlamatini_cfg.get('exec_report_enabled', True))
    idle_timeout = float(tlamatini_cfg.get('response_idle_timeout', 8))
    total_timeout = float(tlamatini_cfg.get('total_timeout', 1800))

    llm_cfg = config.get('llm', {}) or {}
    llm_host = llm_cfg.get('host', 'http://localhost:11434')
    llm_model = llm_cfg.get('model', 'llama3')
    llm_instruction = llm_cfg.get('understanding_prompt') or (
        "Decide if the user request is clear and complete. Respond JSON "
        "{\"complete\":bool,\"ask\":\"<question>\"}."
    )

    target_agents = config.get('target_agents', []) or []

    if not api_id or not api_hash:
        logging.error("Telegram api_id or api_hash missing in config.yaml")
        return
    if not expected_password:
        logging.error("access.password is empty in config.yaml; refusing to start without a password gate.")
        return

    session_name = os.path.join(script_dir, 'teletlamatini_session')
    client = TelegramClient(session_name, api_id, api_hash)
    if bot_token:
        await client.start(bot_token=bot_token)
    else:
        await client.start()

    state: Dict[str, Dict[str, Any]] = {}
    if _IS_REANIMATED:
        loaded = load_reanim_state()
        if isinstance(loaded, dict):
            state.update(loaded)

    loop_lock = asyncio.Lock()

    def _persist():
        try:
            save_reanim_state(state)
        except Exception:
            pass

    async def _process_complete_request(chat, request_text: str):
        await _send_telegram_text(client, chat, processing_message)
        try:
            answer_html = await _login_and_chat_via_websocket(
                base_url=base_url,
                ws_url=ws_url,
                username=tla_user,
                password=tla_pass,
                user_message=request_text,
                multi_turn_enabled=multi_turn_enabled,
                exec_report_enabled=exec_report_enabled,
                response_idle_timeout=idle_timeout,
                total_timeout=total_timeout,
            )
            answer_text = _strip_html_to_text(answer_html) or "(empty response)"
            await _send_telegram_text(client, chat, f"{completed_prefix}\n\n{answer_text}")
        except Exception as exc:
            logging.error(f"Tlamatini chat call failed: {exc}")
            await _send_telegram_text(client, chat, f"{error_prefix} {exc}")

        # Trigger downstream target_agents after each completed cycle.
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                start_agent(target)

    @client.on(events.NewMessage(chats=listen_chat))
    async def handler(event):
        try:
            text = (event.raw_text or '').strip()
            if not text:
                return
            chat_key = str(event.chat_id)

            async with loop_lock:
                chat_state = state.setdefault(chat_key, {
                    'phase': PHASE_AWAIT_PASSWORD,
                    'conversation': [],
                })

                phase = chat_state.get('phase', PHASE_AWAIT_PASSWORD)
                logging.info(f"[chat={chat_key}] phase={phase} received={text!r}")

                if phase == PHASE_AWAIT_PASSWORD:
                    if text == expected_password:
                        chat_state['phase'] = PHASE_AWAIT_REQUEST
                        chat_state['conversation'] = []
                        _persist()
                        await _send_telegram_text(client, event.chat, welcome_message)
                        await _send_telegram_text(
                            client,
                            event.chat,
                            "Send your request to Tlamatini whenever you are ready.",
                        )
                    else:
                        await _send_telegram_text(client, event.chat, rejection_message)
                        await _send_telegram_text(client, event.chat, password_prompt)
                    return

                if phase == PHASE_AWAIT_INFO:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    _persist()
                    chat_state['phase'] = PHASE_AWAIT_REQUEST
                    # Fall through to the AWAIT_REQUEST evaluation below.
                    phase = PHASE_AWAIT_REQUEST

                if phase == PHASE_AWAIT_REQUEST:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    _persist()

                    verdict = await asyncio.to_thread(
                        _classify_request_completeness,
                        llm_host,
                        llm_model,
                        llm_instruction,
                        chat_state['conversation'],
                    )
                    logging.info(f"[chat={chat_key}] completeness verdict={verdict}")

                    if not verdict.get('complete', True):
                        question = verdict.get('ask') or unclear_prompt
                        chat_state['phase'] = PHASE_AWAIT_INFO
                        _persist()
                        await _send_telegram_text(
                            client,
                            event.chat,
                            f"{awaiting_info_intro}\n{question}",
                        )
                        return

                    full_request = "\n".join(
                        turn['content']
                        for turn in chat_state['conversation']
                        if turn.get('role') == 'user'
                    ).strip()
                    chat_state['phase'] = PHASE_PROCESSING
                    _persist()

                    try:
                        await _process_complete_request(event.chat, full_request)
                    finally:
                        chat_state['conversation'] = []
                        chat_state['phase'] = PHASE_AWAIT_REQUEST
                        _persist()
                    return

                if phase == PHASE_PROCESSING:
                    # Mid-processing user reply: queue it as additional info.
                    chat_state.setdefault('pending_info', []).append(text)
                    _persist()
                    return

        except Exception as e:
            logging.error(f"Telegram handler error: {e}")

    logging.info("Connected. Listening for Telegram messages. Press Ctrl+C to stop.")
    try:
        await client.run_until_disconnected()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    write_pid_file()

    if _IS_REANIMATED:
        logging.info(f"{CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        logging.info("TELETLAMATINI AGENT STARTED (Telegram-Blue to Crimson)")
        target_agents = config.get('target_agents', []) or []
        source_agents = config.get('source_agents', []) or []
        logging.info(f"Sources: {source_agents}")
        logging.info(f"Targets: {target_agents}")

        try:
            asyncio.run(_telegram_main_loop(config))
        except KeyboardInterrupt:
            logging.info("TeleTlamatini agent stopped by user.")
        except Exception as e:
            logging.error(f"TeleTlamatini fatal error: {e}")

    finally:
        time.sleep(0.4)
        remove_pid_file()
        logging.info("TeleTlamatini stopped.")

    sys.exit(0)


if __name__ == "__main__":
    main()
