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
#   H) The full Tlamatini answer (including the per-agent Exec Report tables) is
#      converted to plain text and sent back to the Telegram user.
#
# After every successfully completed request cycle, the configured target_agents
# are launched (long-running active agent semantics, like Gatewayer's dispatcher).
#
# IMPORTANT design choices in this rewrite (the previous implementation hung
# silently on "Working on your request..." in some configurations):
#   * Per-chat asyncio.Task isolation — the long Tlamatini call no longer holds
#     the global handler lock, so other chats keep flowing and the user can
#     send a follow-up while a request is in progress (it is queued and then
#     forwarded as a clarifier).
#   * Definitive final-answer detection — the WS receive loop looks for the
#     `multi_turn_used` / `answer_success` keys that `process_llm_response`
#     attaches to the assembled final frame. No more guessing by 8s of silence.
#   * Strict control-frame filter — uses the full constants.py noise list
#     (loading / processing / ready / fallback / restored / etc.) so the
#     "Your request is being processed..." sentinel never leaks to the user.
#   * Websockets compatibility — passes Cookie via `additional_headers` first
#     (websockets >=14) and falls back to `extra_headers` (<14).
#   * Milestone logging at every step — login start / login OK / WS connect /
#     WS open / send message / N-th frame received / final answer / error.
#     If TeleTlamatini ever stalls again, the log will show exactly where.
#   * `processing_message` send is INSIDE the try/except so a Telegram-side
#     error there is logged instead of crashing the cycle silently.

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
from typing import Dict, Any, List, Optional, Tuple

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
    encoding='utf-8',
    force=True,
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
# Tlamatini WebSocket noise / control frames — must mirror the strings
# emitted by Tlamatini/agent/constants.py and consumers.py. Any frame whose
# `message` value normalizes (lowercased) to one of these substrings is NOT
# part of the LLM answer and must be skipped.
# ---------------------------------------------------------------------------

_NOISE_SUBSTRINGS_LOWER: Tuple[str, ...] = (
    # constants.MSG_AGENT_LOADING / LOADING_CONTEXT
    "your agent is loading",
    "loading the context",
    # constants.MSG_AGENT_READY
    "your agent is ready",
    # constants.MSG_AGENT_FALLBACK
    "fallback to a basic prompt only chain",
    # constants.MSG_OVERSIZED_DOCS_WARNING
    "be aware tlamatini might not be able to load",
    # constants.MSG_PROCESSING_REQUEST  ← critical: this one is what TeleTlamatini
    # was previously returning to the Telegram user as the "answer".
    "your request is being processed by tlamatini",
    # constants.MSG_LLM_CANCELLED / DESTROYED / REBUILDING / REESTABLISHED /
    # RECONNECT / CLEARCONTEXT / HISTORY_CLEANED
    "generation was cancelled",
    "connection to ollama has been forcibly terminated",
    "rebuilding agent with fresh connection",
    "successfully re-established",
    "re-connection issued by user",
    "clear-context issued by user",
    "chat history has been cleared",
    # constants.MSG_SESSION_RESTORED / SESSION_AND_CONTEXT_RESTORED
    "welcome back, session restored",
    "welcome back, session and context restored",
    # consumers.py inline strings
    "agent is still loading",
    "request is being processed",
    # not-ready / errors
    "agent cannot process your requests",
    "agent is not ready",
    # establishment sentinel emitted during MCP/tool/agent UI seeding
    "establishment",
    # auth / generic noise
    "you're not authenticated",
)


def _is_noise_frame(msg: str) -> bool:
    """
    Return True iff `msg` is one of Tlamatini's lifecycle/control frames that
    must be excluded from the assembled answer.

    Implementation note: we use case-insensitive substring matches on a
    curated list mirroring Tlamatini/agent/constants.py + consumers.py.
    DO NOT widen this with structural heuristics like "any message containing
    a pipe character" — those silently filter out legitimate LLM answers
    whose exec-report tables include shell commands with pipes.
    """
    if not msg:
        return True
    if msg.strip() == "ping":
        return True
    lowered = msg.lower()
    if any(s in lowered for s in _NOISE_SUBSTRINGS_LOWER):
        return True
    # Establishment frames seeded by the server look like
    #   "<identifier>|<description>|<content>"
    # — a leading bare identifier followed by a pipe. Markdown rows like
    # "| Capability | How |" start with whitespace/pipe and must NOT match.
    if re.match(r'^[A-Za-z][A-Za-z0-9_\-]*\|', msg):
        return True
    return False


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


async def _ws_connect_with_cookie_compat(websockets_mod, ws_url: str, cookie_header: str):
    """
    Open a websockets connection, passing the session cookie. The keyword for
    extra HTTP headers changed names between websockets <14 (`extra_headers`)
    and >=14 (`additional_headers`). Try the new name first, fall back to the
    old one. Returns the connected client.
    """
    try:
        return await websockets_mod.connect(
            ws_url,
            additional_headers={'Cookie': cookie_header},
            max_size=None,
            ping_interval=20,
            open_timeout=30,
        )
    except TypeError:
        return await websockets_mod.connect(
            ws_url,
            extra_headers={'Cookie': cookie_header},
            max_size=None,
            ping_interval=20,
            open_timeout=30,
        )


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
    log_tag: str,
) -> str:
    """
    Authenticate against the Tlamatini Django server and run a single chat
    exchange over the same WebSocket the browser uses. Returns the assembled
    HTML answer (incl. exec-report tables when enabled).

    Detects end-of-response by the unambiguous `multi_turn_used` /
    `answer_success` extras attached by `process_llm_response()` to the final
    broadcast frame. As a safety net, also breaks on `response_idle_timeout`
    seconds of WS silence after at least one non-noise frame.
    """
    import requests
    import websockets

    # ---- HTTP login --------------------------------------------------------
    login_page_url = f"{base_url.rstrip('/')}/"
    logging.info(f"{log_tag} [tla] HTTP GET login page {login_page_url}")
    session = requests.Session()
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
    logging.info(f"{log_tag} [tla] got csrf token (len={len(csrf_token)})")

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
    logging.info(f"{log_tag} [tla] login POST status={post_response.status_code}")
    if post_response.status_code not in (301, 302, 303):
        raise RuntimeError(
            f"Tlamatini login failed: HTTP {post_response.status_code}"
        )
    cookie_header = "; ".join([f"{k}={v}" for k, v in session.cookies.items()])

    # ---- WebSocket exchange ------------------------------------------------
    final_html: Optional[str] = None
    fallback_parts: List[str] = []
    last_event_at = time.monotonic()
    response_started = False
    frame_index = 0

    logging.info(f"{log_tag} [tla] WS connect {ws_url}")
    ws = await _ws_connect_with_cookie_compat(websockets, ws_url, cookie_header)
    logging.info(f"{log_tag} [tla] WS connected, draining ready/restored frames")
    try:
        # Drain pre-existing welcome/ready/restored frames for up to 10 s.
        # If we miss them, no harm done — Tlamatini accepts user input as long
        # as the rag_chain is initialized, and replies with an
        # "agent is still loading" frame (which we recognize as noise) if not.
        ready_deadline = time.monotonic() + 10.0
        while time.monotonic() < ready_deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get('type') != 'agent_message':
                continue
            msg = data.get('message') or ''
            lowered = msg.lower()
            if 'ready' in lowered or 'restored' in lowered or 'fallback' in lowered:
                logging.info(f"{log_tag} [tla] saw ready/restored frame, proceeding")
                break

        # Send the chat message.
        send_payload = {
            'message': user_message,
            'multi_turn_enabled': bool(multi_turn_enabled),
            'exec_report_enabled': bool(exec_report_enabled),
        }
        await ws.send(json.dumps(send_payload))
        logging.info(
            f"{log_tag} [tla] sent user message "
            f"(len={len(user_message)}, multi_turn={multi_turn_enabled}, "
            f"exec_report={exec_report_enabled})"
        )

        deadline = time.monotonic() + float(total_timeout)
        last_progress_log = time.monotonic()

        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                # If we've already collected at least one real frame, accept
                # response_idle_timeout seconds of silence as end-of-response.
                if response_started and (time.monotonic() - last_event_at) >= response_idle_timeout:
                    logging.info(
                        f"{log_tag} [tla] idle timeout ({response_idle_timeout}s) — closing"
                    )
                    break
                # Heartbeat log every 30 s so a future hang is easy to diagnose.
                if (time.monotonic() - last_progress_log) >= 30.0:
                    logging.info(
                        f"{log_tag} [tla] still waiting for Tlamatini answer... "
                        f"(frames_seen={frame_index}, response_started={response_started})"
                    )
                    last_progress_log = time.monotonic()
                continue
            except Exception as recv_err:
                logging.error(f"{log_tag} [tla] WS recv error: {recv_err}")
                break

            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get('type') != 'agent_message':
                continue
            if data.get('username') != 'Tlamatini':
                continue

            msg = data.get('message') or ''
            frame_index += 1

            # Definitive final-answer frame: process_llm_response attaches
            # `multi_turn_used` (boolean) and/or `answer_success` (boolean)
            # ONLY when broadcasting the assembled answer. Use that as the
            # primary completion signal.
            is_final_frame = (
                ('multi_turn_used' in data) or ('answer_success' in data)
            )

            if _is_noise_frame(msg) and not is_final_frame:
                logging.info(
                    f"{log_tag} [tla] frame#{frame_index} noise — "
                    f"first40={msg[:40]!r}"
                )
                continue

            response_started = True
            last_event_at = time.monotonic()
            if is_final_frame:
                final_html = msg
                logging.info(
                    f"{log_tag} [tla] frame#{frame_index} FINAL "
                    f"(len={len(msg)}, multi_turn_used={data.get('multi_turn_used')}, "
                    f"answer_success={data.get('answer_success')})"
                )
                break

            # Any other non-noise frame is a partial / ad-hoc answer (e.g.
            # the basic-chain path that does not set multi_turn_used).
            fallback_parts.append(msg)
            logging.info(
                f"{log_tag} [tla] frame#{frame_index} partial "
                f"(len={len(msg)}, first40={msg[:40]!r})"
            )

        if final_html is None and not fallback_parts and time.monotonic() >= deadline:
            logging.error(
                f"{log_tag} [tla] total_timeout ({total_timeout}s) reached with no answer"
            )
    finally:
        try:
            await ws.close()
        except Exception:
            pass

    if final_html is not None:
        return final_html
    return "\n".join(part for part in fallback_parts if part).strip()


# ---------------------------------------------------------------------------
# Telegram glue
# ---------------------------------------------------------------------------

async def _send_telegram_text(client, chat, text: str):
    """Send a long text in 3800-char chunks (Telegram message limit is 4096)."""
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
    bot_token = (telegram_cfg.get('bot_token') or '').strip()
    # In bot mode, respond to any user that messages the bot (chats=None = no filter).
    # In user-account mode, default to Saved Messages ("me") unless the user picks a chat.
    # Treat null / empty string / whitespace-only as "no explicit chat" so the
    # canvas dialog can't silently break the handler by writing '' instead of null.
    raw_listen_chat = telegram_cfg.get('listen_chat', None if bot_token else 'me')
    if isinstance(raw_listen_chat, str) and not raw_listen_chat.strip():
        raw_listen_chat = None
    listen_chat = raw_listen_chat if raw_listen_chat is not None else (None if bot_token else 'me')
    is_bot_mode = bool(bot_token)

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

    # Per-chat state. Each chat has its own asyncio.Lock, its own conversation
    # buffer, and its own (optional) in-flight processing task. The previous
    # implementation used a SINGLE global lock across all chats and held it
    # for the entire duration of the Tlamatini call — meaning a slow chat
    # would freeze every other Telegram conversation, including the chat's
    # own follow-ups. With per-chat locks, multiple Telegram users can be
    # served concurrently and a user can queue a clarification while their
    # own request is in flight.
    chat_states: Dict[str, Dict[str, Any]] = {}
    chat_locks: Dict[str, asyncio.Lock] = {}

    if _IS_REANIMATED:
        loaded = load_reanim_state()
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if isinstance(v, dict):
                    # On reanimation we cannot resume a half-processed
                    # request (the WS exchange is already gone), so coerce
                    # any leftover PROCESSING phase back to AWAIT_REQUEST.
                    if v.get('phase') == PHASE_PROCESSING:
                        v['phase'] = PHASE_AWAIT_REQUEST
                        v.pop('task_running', None)
                    chat_states[k] = v

    state_persist_lock = asyncio.Lock()

    async def _persist_locked():
        async with state_persist_lock:
            try:
                save_reanim_state(chat_states)
            except Exception:
                pass

    def _get_chat_lock(chat_key: str) -> asyncio.Lock:
        lock = chat_locks.get(chat_key)
        if lock is None:
            lock = asyncio.Lock()
            chat_locks[chat_key] = lock
        return lock

    async def _process_complete_request(chat, chat_key: str, request_text: str):
        log_tag = f"[chat={chat_key}]"
        try:
            await _send_telegram_text(client, chat, processing_message)
            logging.info(f"{log_tag} sent processing_message to user")
        except Exception as e:
            logging.error(f"{log_tag} failed to send processing_message: {e}")

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
                log_tag=log_tag,
            )
            answer_text = _strip_html_to_text(answer_html) or "(empty response)"
            logging.info(
                f"{log_tag} Tlamatini answer ready "
                f"(html_len={len(answer_html)}, text_len={len(answer_text)})"
            )
            await _send_telegram_text(client, chat, f"{completed_prefix}\n\n{answer_text}")
        except Exception as exc:
            logging.error(f"{log_tag} Tlamatini chat call failed: {exc}", exc_info=True)
            try:
                await _send_telegram_text(client, chat, f"{error_prefix} {exc}")
            except Exception as send_err:
                logging.error(f"{log_tag} failed to deliver error to user: {send_err}")

        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                start_agent(target)

    async def _process_with_pending(chat, chat_key: str, chat_state: Dict[str, Any]):
        """Run one full request cycle, then drain any pending mid-flight follow-ups."""
        try:
            full_request = "\n".join(
                turn['content']
                for turn in chat_state.get('conversation', [])
                if turn.get('role') == 'user'
            ).strip()
            await _process_complete_request(chat, chat_key, full_request)

            # If user pinged us during processing, fold those into a fresh
            # follow-up cycle instead of dropping them.
            pending = chat_state.pop('pending_info', []) or []
            if pending:
                logging.info(f"[chat={chat_key}] processing {len(pending)} queued follow-ups")
                chat_state['conversation'] = [
                    {'role': 'user', 'content': p} for p in pending
                ]
                follow_text = "\n".join(pending).strip()
                if follow_text:
                    await _process_complete_request(chat, chat_key, follow_text)
        finally:
            chat_state['conversation'] = []
            chat_state['phase'] = PHASE_AWAIT_REQUEST
            chat_state.pop('task_running', None)
            await _persist_locked()

    handler_filter = events.NewMessage() if listen_chat is None else events.NewMessage(chats=listen_chat)

    @client.on(handler_filter)
    async def handler(event):
        try:
            text = (event.raw_text or '').strip()
            if not text:
                return
            chat_key = str(event.chat_id)

            # Bot-mode courtesy: greet on /start before the password gate.
            if is_bot_mode and text.lower() in ('/start', '/help'):
                await _send_telegram_text(client, event.chat, password_prompt)
                return

            chat_lock = _get_chat_lock(chat_key)

            async with chat_lock:
                chat_state = chat_states.setdefault(chat_key, {
                    'phase': PHASE_AWAIT_PASSWORD,
                    'conversation': [],
                })

                phase = chat_state.get('phase', PHASE_AWAIT_PASSWORD)
                logging.info(f"[chat={chat_key}] phase={phase} received={text!r}")

                if phase == PHASE_AWAIT_PASSWORD:
                    if text == expected_password:
                        chat_state['phase'] = PHASE_AWAIT_REQUEST
                        chat_state['conversation'] = []
                        await _persist_locked()
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

                if phase == PHASE_PROCESSING:
                    # Mid-processing user reply: queue it; the running task
                    # will pick it up after the current cycle finishes.
                    chat_state.setdefault('pending_info', []).append(text)
                    await _persist_locked()
                    logging.info(f"[chat={chat_key}] queued mid-processing follow-up")
                    return

                if phase == PHASE_AWAIT_INFO:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    await _persist_locked()
                    chat_state['phase'] = PHASE_AWAIT_REQUEST
                    phase = PHASE_AWAIT_REQUEST
                    # Fall through.

                if phase == PHASE_AWAIT_REQUEST:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    await _persist_locked()

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
                        await _persist_locked()
                        await _send_telegram_text(
                            client,
                            event.chat,
                            f"{awaiting_info_intro}\n{question}",
                        )
                        return

                    chat_state['phase'] = PHASE_PROCESSING
                    chat_state['task_running'] = True
                    await _persist_locked()
                    # Detach the long Tlamatini call from the per-chat lock so
                    # the user can queue follow-ups while it runs. The task is
                    # fire-and-forget; cleanup is in its own finally block.
                    asyncio.create_task(_process_with_pending(event.chat, chat_key, chat_state))
                    return

        except Exception as e:
            logging.error(f"Telegram handler error: {e}", exc_info=True)

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
