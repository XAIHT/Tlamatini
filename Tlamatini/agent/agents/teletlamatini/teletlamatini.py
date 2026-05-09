# TeleTlamatini Agent — pure Telegram-bot bridge to the Tlamatini chat core.
#
# This is a focused redesign of the original TeleTlamatini. The original was
# carrying legacy from Telegramer's user-account mode (`listen_chat`,
# user-account fallback, customizable strings for every message, per-request
# HTTP login, 10-second drain on every message, mandatory LLM completeness
# gate with a slow cloud model). For a bot, all of that is dead weight. This
# rewrite cuts straight to the bone:
#
#   * BOT MODE ONLY. `bot_token` is required. No `listen_chat`, no
#     "user-account fallback". Telegramer / TelegramRX exist for the
#     user-account direction; TeleTlamatini is a bot, period.
#   * PERSISTENT TLAMATINI BRIDGE. We log into Tlamatini ONCE on startup,
#     open ONE WebSocket, and reuse it for every Telegram message. No more
#     1–2 s of HTTP login + WS handshake per CPU-usage question.
#   * COMPLETENESS GATE IS OFF BY DEFAULT. Set `completeness_check.enabled:
#     true` only if you want the LLM to ask follow-up questions before
#     forwarding to Tlamatini. The default is fire-and-go (OpenClaw-style):
#     every message goes straight through.
#   * EDITABLE STATUS MESSAGE. The user sees ONE "🔄 Working on it…" message
#     that gets edited in place to "✅ Result:" + answer when ready, instead
#     of a wall of intermediate notifications.
#   * COMPACT CONFIG. Required keys are flat and obvious. Old keys are read
#     for backward-compat but ignored when superseded by the new shape.
#
# Behaviour from the user's perspective (Telegram side):
#   1. /start  → bot asks for the access password.
#   2. <password> → if correct, "✅ Authenticated." Otherwise rejection.
#   3. <any text> → "🔄 Working on it…", then the assembled Tlamatini answer
#      (incl. per-agent Exec Report tables) edited into the status message.
#
# After every successfully completed request, configured `target_agents` are
# launched (long-running active-agent semantics, like Gatewayer's dispatcher).

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
# Config / PID helpers (verbatim from telegramer.py — these are the agent
# platform contract; do not modify).
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
# Reanim state (which chats are past the password gate)
# ---------------------------------------------------------------------------

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
# Tlamatini WS frame classifier — the single most important piece of logic
# in this agent. See the previous bug-fix commits for the full rationale:
# real chat answers carry NO `type` field; UI-control frames DO; and only
# `multi_turn_used` / `answer_success` extras mark the assembled final.
# ---------------------------------------------------------------------------

_SPECIAL_TYPES_TO_SKIP: Tuple[str, ...] = (
    "mcp", "tool", "agent",
    "heartbeat", "session-restored", "context-path-set",
    "establishment-completed",
)

_NOISE_SUBSTRINGS_LOWER: Tuple[str, ...] = (
    "your agent is loading",
    "loading the context",
    "your agent is ready",
    "fallback to a basic prompt only chain",
    "be aware tlamatini might not be able to load",
    "your request is being processed by tlamatini",
    "generation was cancelled",
    "connection to ollama has been forcibly terminated",
    "rebuilding agent with fresh connection",
    "successfully re-established",
    "re-connection issued by user",
    "clear-context issued by user",
    "chat history has been cleared",
    "welcome back, session restored",
    "welcome back, session and context restored",
    "agent is still loading",
    "request is being processed",
)

_FAILURE_SUBSTRINGS_LOWER: Tuple[str, ...] = (
    "agent cannot process your requests",
    "agent is not ready",
    "you're not authenticated",
)


def _classify_frame(data: Dict[str, Any]) -> str:
    frame_type = data.get('type')
    if frame_type and frame_type in _SPECIAL_TYPES_TO_SKIP:
        return "skip"
    username = data.get('username')
    msg = data.get('message') or ''
    if username == 'ping' or not msg or msg.strip() == 'ping':
        return "skip"
    if username != 'Tlamatini':
        return "skip"
    if ('multi_turn_used' in data) or ('answer_success' in data):
        return "final"
    lowered = msg.lower()
    if any(s in lowered for s in _FAILURE_SUBSTRINGS_LOWER):
        return "failure"
    if any(s in lowered for s in _NOISE_SUBSTRINGS_LOWER):
        return "noise"
    if re.match(r'^[A-Za-z][A-Za-z0-9_\-]*\|', msg):
        return "skip"
    return "partial"


def _summarize_frame_for_log(data: Dict[str, Any]) -> str:
    msg = data.get('message') or ''
    extras: List[str] = []
    if 'multi_turn_used' in data:
        extras.append(f"multi_turn_used={data.get('multi_turn_used')}")
    if 'answer_success' in data:
        extras.append(f"answer_success={data.get('answer_success')}")
    if data.get('tool_calls_log'):
        extras.append(f"tool_calls_log_len={len(data.get('tool_calls_log') or [])}")
    extras_s = (' ' + ' '.join(extras)) if extras else ''
    return (
        f"type={data.get('type')!r} username={data.get('username')!r} "
        f"len={len(msg)}{extras_s} first80={msg[:80]!r}"
    )


# ---------------------------------------------------------------------------
# Optional LLM-aided completeness check (off by default)
# ---------------------------------------------------------------------------

def _classify_request_completeness(host: str, model: str, instruction: str,
                                   conversation: List[Dict[str, str]]) -> Dict[str, Any]:
    transcript_lines = []
    for turn in conversation:
        role = turn.get('role', 'user').upper()
        content = (turn.get('content') or '').strip()
        if content:
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)
    prompt = f"{instruction}\n\nCONVERSATION:\n{transcript}\n\nJSON:"
    url = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = (body.get("response") or "").strip()
        match = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if not match:
            return {"complete": True, "ask": ""}
        parsed = json.loads(match.group(0))
        return {
            "complete": bool(parsed.get("complete", True)),
            "ask": str(parsed.get("ask") or "").strip(),
        }
    except Exception as e:
        logging.error(f"Completeness check failed (failing open): {e}")
        return {"complete": True, "ask": ""}


# ---------------------------------------------------------------------------
# Telegram-friendly HTML→text stripping for the assembled answer
# ---------------------------------------------------------------------------

def _strip_html_to_text(html_content: str) -> str:
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


# ---------------------------------------------------------------------------
# TlamatiniBridge — single persistent session+WS, reused across all chats
# ---------------------------------------------------------------------------

class TlamatiniBridge:
    """
    Maintains ONE Django session and ONE WebSocket connection to Tlamatini for
    the entire lifetime of the agent. Every Telegram message is forwarded
    through the same WS, saving the per-request HTTP login + WS handshake +
    establishment-frame burst that the original implementation paid every
    single time.

    Concurrency model: a single asyncio.Lock serializes chat calls. Tlamatini
    only processes one rag_chain LLM call per consumer at a time anyway, so
    pipelining gains nothing; the lock just keeps the receive loop's framing
    simple and prevents two Telegram users from accidentally interleaving
    each other's frames.
    """

    def __init__(
        self,
        base_url: str,
        ws_url: str,
        username: str,
        password: str,
        multi_turn_enabled: bool,
        exec_report_enabled: bool,
        acpx_enabled: bool,
        total_timeout: float,
        idle_timeout: float = 8.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.ws_url = ws_url
        self.username = username
        self.password = password
        self.multi_turn_enabled = multi_turn_enabled
        self.exec_report_enabled = exec_report_enabled
        # ACPX gate — when True, Tlamatini exposes the 12 ACPX/Skill tools to
        # the planner for this request, which means the LLM can run the
        # complete ACPX schemes (acp_doctor → acp_spawn → acp_send_and_wait →
        # acp_relay → acp_kill, plus list_skills / invoke_skill). When False,
        # `agent.acpx.filter_acpx_tools()` strips them out and the request
        # falls back to the legacy Multi-Turn / one-shot flow. Mirrors the
        # `#acpx-enabled` toolbar checkbox in the chat UI.
        self.acpx_enabled = acpx_enabled
        self.total_timeout = float(total_timeout)
        self.idle_timeout = float(idle_timeout)

        self._ws = None  # websockets client connection
        self._cookie_header: Optional[str] = None
        self._lock = asyncio.Lock()
        self._closed = False

    # -- HTTP login (rare; run once + on reconnect) -------------------------

    def _http_login_sync(self) -> str:
        """Returns a 'k=v; k=v' cookie header suitable for the WS upgrade."""
        import requests
        login_url = f"{self.base_url}/"
        session = requests.Session()
        page = session.get(login_url, timeout=30)
        csrf = session.cookies.get('csrftoken')
        if not csrf:
            m = re.search(
                r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']',
                page.text,
            )
            if m:
                csrf = m.group(1)
        if not csrf:
            raise RuntimeError("Could not obtain CSRF token from Tlamatini login page")
        post = session.post(
            login_url,
            data={
                'username': self.username,
                'password': self.password,
                'csrfmiddlewaretoken': csrf,
            },
            headers={'Referer': login_url},
            allow_redirects=False,
            timeout=30,
        )
        if post.status_code not in (301, 302, 303):
            raise RuntimeError(f"Tlamatini login failed: HTTP {post.status_code}")
        return "; ".join(f"{k}={v}" for k, v in session.cookies.items())

    # -- WS lifecycle -------------------------------------------------------

    async def _ws_open(self):
        import websockets
        try:
            return await websockets.connect(
                self.ws_url,
                additional_headers={'Cookie': self._cookie_header},
                max_size=None,
                ping_interval=20,
                open_timeout=30,
            )
        except TypeError:
            return await websockets.connect(
                self.ws_url,
                extra_headers={'Cookie': self._cookie_header},
                max_size=None,
                ping_interval=20,
                open_timeout=30,
            )

    async def ensure_connected(self, log_tag: str):
        if self._closed:
            raise RuntimeError("TlamatiniBridge already closed")
        if self._ws is not None:
            try:
                # `closed` attr exists on websockets <14; on >=14 the handle is
                # still usable until a recv/send raises ConnectionClosed.
                if getattr(self._ws, 'closed', False):
                    self._ws = None
            except Exception:
                self._ws = None
        if self._ws is not None:
            return

        if self._cookie_header is None:
            logging.info(f"{log_tag} bridge: HTTP login {self.base_url}")
            self._cookie_header = await asyncio.to_thread(self._http_login_sync)
            logging.info(f"{log_tag} bridge: HTTP login OK")
        logging.info(f"{log_tag} bridge: WS connect {self.ws_url}")
        self._ws = await self._ws_open()
        logging.info(f"{log_tag} bridge: WS open")

    async def close(self):
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    # -- Drain any frames queued from previous activity --------------------

    async def _drain_queued(self, log_tag: str, max_frames: int = 200):
        """Quickly consume anything Tlamatini may have buffered for us
        between chat calls (browser activity, MCP heartbeats, session
        restores, etc.)."""
        drained = 0
        while drained < max_frames:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=0.05)
            except asyncio.TimeoutError:
                break
            except Exception:
                break
            drained += 1
            try:
                data = json.loads(raw)
            except Exception:
                continue
            v = _classify_frame(data)
            if v in ("partial", "final", "failure"):
                # Stale answer to a previous request? Log and discard, so a
                # late frame from a prior chat doesn't poison the next one.
                logging.warning(
                    f"{log_tag} bridge: drained stale {v} frame "
                    f"({_summarize_frame_for_log(data)})"
                )
        if drained:
            logging.info(f"{log_tag} bridge: drained {drained} stale frames")

    # -- The main entry: send one user message, return final HTML ----------

    async def chat(
        self,
        log_tag: str,
        user_message: str,
    ) -> Tuple[str, Dict[str, int]]:
        async with self._lock:
            return await self._chat_locked(log_tag, user_message)

    async def _chat_locked(
        self,
        log_tag: str,
        user_message: str,
    ) -> Tuple[str, Dict[str, int]]:
        # One reconnect retry on a clean send/recv failure.
        for attempt in (1, 2):
            try:
                await self.ensure_connected(log_tag)
                await self._drain_queued(log_tag)
                return await self._send_and_collect(log_tag, user_message)
            except Exception as e:
                logging.warning(
                    f"{log_tag} bridge: chat attempt {attempt} failed: {e}"
                )
                # Force reconnect on retry
                try:
                    if self._ws is not None:
                        await self._ws.close()
                except Exception:
                    pass
                self._ws = None
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    async def _send_and_collect(
        self,
        log_tag: str,
        user_message: str,
    ) -> Tuple[str, Dict[str, int]]:
        send_payload = {
            'message': user_message,
            'multi_turn_enabled': bool(self.multi_turn_enabled),
            'exec_report_enabled': bool(self.exec_report_enabled),
            'acpx_enabled': bool(self.acpx_enabled),
        }
        await self._ws.send(json.dumps(send_payload))
        logging.info(
            f"{log_tag} bridge: sent (len={len(user_message)}, "
            f"multi_turn={self.multi_turn_enabled}, "
            f"exec_report={self.exec_report_enabled}, "
            f"acpx={self.acpx_enabled})"
        )

        final_html: Optional[str] = None
        last_failure_msg: Optional[str] = None
        partial_parts: List[str] = []
        last_event_at = time.monotonic()
        response_started = False
        counters: Dict[str, int] = {
            "total": 0, "skip": 0, "noise": 0, "failure": 0,
            "partial": 0, "final": 0, "non_json": 0, "recv_error": 0,
        }
        deadline = time.monotonic() + self.total_timeout
        last_progress_log = time.monotonic()

        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                if response_started and (time.monotonic() - last_event_at) >= self.idle_timeout:
                    logging.info(
                        f"{log_tag} bridge: idle {self.idle_timeout}s — closing. "
                        f"counters={counters}"
                    )
                    break
                if (time.monotonic() - last_progress_log) >= 30.0:
                    logging.info(
                        f"{log_tag} bridge: still waiting... counters={counters}"
                    )
                    last_progress_log = time.monotonic()
                continue
            except Exception as recv_err:
                counters["recv_error"] += 1
                logging.error(f"{log_tag} bridge: WS recv error: {recv_err}")
                raise

            try:
                data = json.loads(raw)
            except Exception:
                counters["non_json"] += 1
                continue

            counters["total"] += 1
            v = _classify_frame(data)
            counters[v] = counters.get(v, 0) + 1
            summary = _summarize_frame_for_log(data)

            if v == "skip":
                if counters["skip"] % 25 == 1:
                    logging.info(f"{log_tag} bridge: frame#{counters['total']} skip ({summary})")
                continue
            if v == "noise":
                logging.info(f"{log_tag} bridge: frame#{counters['total']} noise ({summary})")
                continue
            msg = data.get('message') or ''
            if v == "failure":
                last_failure_msg = msg
                response_started = True
                last_event_at = time.monotonic()
                logging.info(f"{log_tag} bridge: frame#{counters['total']} failure ({summary})")
                continue
            response_started = True
            last_event_at = time.monotonic()
            if v == "final":
                final_html = msg
                logging.info(f"{log_tag} bridge: frame#{counters['total']} FINAL ({summary})")
                break
            partial_parts.append(msg)
            logging.info(f"{log_tag} bridge: frame#{counters['total']} partial ({summary})")

        if final_html is None and not partial_parts and time.monotonic() >= deadline:
            logging.error(f"{log_tag} bridge: total_timeout reached. counters={counters}")

        if final_html is not None:
            return final_html, counters
        if partial_parts:
            return "\n".join(p for p in partial_parts if p).strip(), counters
        if last_failure_msg:
            return last_failure_msg, counters
        return "", counters


# ---------------------------------------------------------------------------
# Telegram glue — pure bot mode
# ---------------------------------------------------------------------------

PHASE_AWAIT_PASSWORD = "AWAIT_PASSWORD"
PHASE_READY = "READY"
PHASE_PROCESSING = "PROCESSING"
PHASE_AWAIT_INFO = "AWAIT_INFO"  # only used when completeness_check.enabled


def _resolve_telegram_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read telegram credentials from the new flat shape AND from the legacy
    `telegram: {api_id, api_hash, bot_token, listen_chat?}` shape, so old
    config.yaml files keep working. `listen_chat` is silently ignored — bot
    mode is the only mode now.
    """
    flat = {
        'api_id': config.get('api_id') or (config.get('telegram') or {}).get('api_id'),
        'api_hash': config.get('api_hash') or (config.get('telegram') or {}).get('api_hash'),
        'bot_token': (
            (config.get('bot_token') or '').strip()
            if isinstance(config.get('bot_token'), str)
            else ((config.get('telegram') or {}).get('bot_token') or '').strip()
        ),
    }
    legacy_listen_chat = (config.get('telegram') or {}).get('listen_chat')
    if legacy_listen_chat is not None:
        logging.warning(
            "telegram.listen_chat is ignored — TeleTlamatini is bot-only. "
            "(Telegramer / TelegramRX cover user-account mode.)"
        )
    return flat


def _resolve_password(config: Dict[str, Any]) -> str:
    # New flat: `password: ...`
    # Legacy nested: `access.password: ...`
    return str(
        config.get('password')
        or (config.get('access') or {}).get('password')
        or ''
    ).strip()


def _resolve_completeness_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    # New: `completeness_check: {enabled, host, model, instruction}`
    # Legacy: `llm: {host, model, understanding_prompt}` + always-on behaviour
    new = config.get('completeness_check') or {}
    legacy_llm = config.get('llm') or {}
    enabled = bool(new.get('enabled', False))
    return {
        'enabled': enabled,
        'host': new.get('host') or legacy_llm.get('host', 'http://localhost:11434'),
        'model': new.get('model') or legacy_llm.get('model', 'llama3'),
        'instruction': (
            new.get('instruction')
            or legacy_llm.get('understanding_prompt')
            or "Decide if the user request is clear and complete. Respond JSON "
               "{\"complete\":bool,\"ask\":\"<question>\"}."
        ),
    }


def _resolve_tlamatini_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    tla = config.get('tlamatini') or {}
    base = (tla.get('base_url') or 'http://127.0.0.1:8000').rstrip('/')
    ws_url = tla.get('ws_url')
    if not ws_url:
        # Derive ws:// from http:// automatically — one less thing to keep in
        # sync in config.yaml.
        ws_url = base.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/agent/'
    return {
        'base_url': base,
        'ws_url': ws_url,
        'username': tla.get('username', 'user'),
        'password': tla.get('password', 'changeme'),
        'multi_turn_enabled': bool(tla.get('multi_turn_enabled', True)),
        'exec_report_enabled': bool(tla.get('exec_report_enabled', True)),
        # ACPX defaults to False at the resolver level (matching the chat
        # toolbar's system-wide default) so a TeleTlamatini deploy from
        # before this change keeps its legacy behavior. The shipped
        # config.yaml sets `acpx_enabled: true` so fresh deploys can drive
        # the full ACPX scheme out of the box.
        'acpx_enabled': bool(tla.get('acpx_enabled', False)),
        'total_timeout': float(tla.get('total_timeout', 1800)),
        'idle_timeout': float(tla.get('response_idle_timeout', 8)),
    }


# Hard-coded user-facing strings (formerly configurable via 9 different keys).
_MSG_PASSWORD_PROMPT = "🔒 Send the access password to use this bot."
_MSG_AUTH_REJECTED = "❌ Wrong password. Try again."
def _format_auth_ok(multi_turn_enabled: bool, exec_report_enabled: bool, acpx_enabled: bool) -> str:
    flags = []
    if multi_turn_enabled:
        flags.append("Multi-Turn")
    if exec_report_enabled:
        flags.append("Exec Report")
    if acpx_enabled:
        flags.append("ACPX")
    suffix = f" ({' + '.join(flags)})" if flags else " (legacy one-shot)"
    examples = ["\"What's my CPU usage?\""]
    if acpx_enabled:
        examples.append("\"Use ACPX to spawn claude and ask it to summarize the current branch\"")
    return (
        "✅ Authenticated. Send any request — I'll forward it to Tlamatini"
        f"{suffix}. For example: {' or '.join(examples)}."
    )
_MSG_WORKING = "🔄 Working on your request..."
_MSG_NEED_INFO = "🟡 I need a bit more detail:"
_MSG_EMPTY_RESULT = "⚠️ Tlamatini returned an empty response."
_MSG_ERROR_PREFIX = "❌ Error: "
_MAX_TG_CHUNK = 3800


async def _send_long(client, chat, text: str) -> Optional[Any]:
    """Send a (possibly long) text and return the FIRST sent Message."""
    if not text:
        return None
    chunks = [text[i:i + _MAX_TG_CHUNK] for i in range(0, len(text), _MAX_TG_CHUNK)] or [text]
    first_msg = None
    for chunk in chunks:
        try:
            m = await client.send_message(chat, chunk)
            if first_msg is None:
                first_msg = m
        except Exception as e:
            logging.error(f"send_message chunk failed: {e}")
            break
    return first_msg


async def _edit_or_send(client, chat, status_msg, text: str):
    """Edit the existing status message; if too long or edit fails, send fresh."""
    if status_msg is None or len(text) > _MAX_TG_CHUNK:
        # Edit the status to a brief "done" then send the full answer.
        if status_msg is not None:
            try:
                await client.edit_message(chat, status_msg.id, "✅ Result:")
            except Exception:
                pass
        await _send_long(client, chat, text)
        return
    try:
        await client.edit_message(chat, status_msg.id, text)
    except Exception as e:
        logging.warning(f"edit_message failed, sending fresh: {e}")
        await _send_long(client, chat, text)


async def _telegram_main_loop(config: Dict[str, Any]):
    from telethon import TelegramClient, events

    tg_cfg = _resolve_telegram_cfg(config)
    password_gate = _resolve_password(config)
    cc_cfg = _resolve_completeness_cfg(config)
    tla_cfg = _resolve_tlamatini_cfg(config)
    target_agents = config.get('target_agents', []) or []

    if not tg_cfg['api_id'] or not tg_cfg['api_hash']:
        logging.error("api_id / api_hash missing in config.yaml. Get them from "
                      "https://my.telegram.org → API development tools.")
        return
    if not tg_cfg['bot_token']:
        logging.error("bot_token missing in config.yaml. TeleTlamatini is "
                      "bot-only — get a token from @BotFather.")
        return

    # --- Persistent Tlamatini bridge (one login, one WS, reused forever) ---
    bridge = TlamatiniBridge(
        base_url=tla_cfg['base_url'],
        ws_url=tla_cfg['ws_url'],
        username=tla_cfg['username'],
        password=tla_cfg['password'],
        multi_turn_enabled=tla_cfg['multi_turn_enabled'],
        exec_report_enabled=tla_cfg['exec_report_enabled'],
        acpx_enabled=tla_cfg['acpx_enabled'],
        total_timeout=tla_cfg['total_timeout'],
        idle_timeout=tla_cfg['idle_timeout'],
    )
    try:
        await bridge.ensure_connected(log_tag="[bridge:init]")
    except Exception as e:
        logging.error(f"Initial Tlamatini bridge connect failed: {e}. "
                      "The bot will start anyway and retry on first message.")

    # --- Telegram client ---
    session_name = os.path.join(script_dir, 'teletlamatini_session')
    client = TelegramClient(session_name, tg_cfg['api_id'], tg_cfg['api_hash'])
    await client.start(bot_token=tg_cfg['bot_token'])

    # --- Per-chat state ---
    chat_states: Dict[str, Dict[str, Any]] = {}
    chat_locks: Dict[str, asyncio.Lock] = {}
    if _IS_REANIMATED:
        loaded = load_reanim_state()
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if isinstance(v, dict):
                    if v.get('phase') == PHASE_PROCESSING:
                        v['phase'] = PHASE_READY
                    chat_states[k] = v

    state_persist_lock = asyncio.Lock()

    async def _persist():
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

    # --- The actual Tlamatini call, with editable status message ----------

    async def _process_request(event_chat, chat_key: str, request_text: str):
        log_tag = f"[chat={chat_key}]"
        status_msg = None
        try:
            status_msg = await client.send_message(event_chat, _MSG_WORKING)
            logging.info(f"{log_tag} status message sent")
        except Exception as e:
            logging.error(f"{log_tag} send_message(working) failed: {e}")

        try:
            answer_html, counters = await bridge.chat(log_tag, request_text)
            answer_text = _strip_html_to_text(answer_html) or _MSG_EMPTY_RESULT
            logging.info(
                f"{log_tag} answer ready (html_len={len(answer_html)}, "
                f"text_len={len(answer_text)}, counters={counters})"
            )
            await _edit_or_send(client, event_chat, status_msg, answer_text)
        except Exception as exc:
            logging.error(f"{log_tag} bridge.chat failed: {exc}", exc_info=True)
            err_text = f"{_MSG_ERROR_PREFIX}{exc}"
            try:
                if status_msg is not None:
                    await client.edit_message(event_chat, status_msg.id, err_text)
                else:
                    await _send_long(client, event_chat, err_text)
            except Exception as send_err:
                logging.error(f"{log_tag} failed to deliver error: {send_err}")

        # Trigger downstream target_agents per cycle (Gatewayer-style semantics).
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for tgt in target_agents:
                start_agent(tgt)

    async def _process_with_pending(event_chat, chat_key: str, chat_state: Dict[str, Any]):
        try:
            req_text = "\n".join(
                t['content'] for t in chat_state.get('conversation', [])
                if t.get('role') == 'user'
            ).strip()
            await _process_request(event_chat, chat_key, req_text)
            pending = chat_state.pop('pending_info', []) or []
            if pending:
                logging.info(f"[chat={chat_key}] {len(pending)} queued follow-ups")
                follow = "\n".join(pending).strip()
                if follow:
                    chat_state['conversation'] = [{'role': 'user', 'content': follow}]
                    await _process_request(event_chat, chat_key, follow)
        finally:
            chat_state['conversation'] = []
            chat_state['phase'] = PHASE_READY
            chat_state.pop('task_running', None)
            await _persist()

    # --- Event handler ----------------------------------------------------

    @client.on(events.NewMessage())
    async def handler(event):
        try:
            text = (event.raw_text or '').strip()
            if not text:
                return
            chat_key = str(event.chat_id)

            # Pre-auth courtesy on /start /help
            if text.lower() in ('/start', '/help'):
                state = chat_states.get(chat_key)
                if state and state.get('phase') in (PHASE_READY, PHASE_PROCESSING, PHASE_AWAIT_INFO):
                    await client.send_message(event.chat,
                        "🟢 Already authenticated. Send a request to Tlamatini.")
                else:
                    await client.send_message(event.chat, _MSG_PASSWORD_PROMPT)
                return

            chat_lock = _get_chat_lock(chat_key)
            async with chat_lock:
                chat_state = chat_states.setdefault(chat_key, {
                    'phase': PHASE_AWAIT_PASSWORD,
                    'conversation': [],
                })
                phase = chat_state.get('phase', PHASE_AWAIT_PASSWORD)
                logging.info(f"[chat={chat_key}] phase={phase} received={text[:80]!r}")

                if phase == PHASE_AWAIT_PASSWORD:
                    if password_gate and text == password_gate:
                        chat_state['phase'] = PHASE_READY
                        chat_state['conversation'] = []
                        await _persist()
                        await client.send_message(event.chat, _format_auth_ok(
                            tla_cfg['multi_turn_enabled'],
                            tla_cfg['exec_report_enabled'],
                            tla_cfg['acpx_enabled'],
                        ))
                    elif not password_gate:
                        # No password configured → first message acts as request
                        chat_state['phase'] = PHASE_READY
                        await _persist()
                        # Fall through into the READY branch below
                        phase = PHASE_READY
                    else:
                        await client.send_message(event.chat, _MSG_AUTH_REJECTED)
                        await client.send_message(event.chat, _MSG_PASSWORD_PROMPT)
                        return

                if phase == PHASE_PROCESSING:
                    chat_state.setdefault('pending_info', []).append(text)
                    await _persist()
                    logging.info(f"[chat={chat_key}] queued mid-processing")
                    return

                if phase == PHASE_AWAIT_INFO:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    await _persist()
                    chat_state['phase'] = PHASE_READY
                    phase = PHASE_READY
                    # Fall through to READY processing.

                if phase == PHASE_READY:
                    chat_state['conversation'].append({'role': 'user', 'content': text})
                    await _persist()

                    # Optional clarification gate (off by default — fast path).
                    if cc_cfg['enabled']:
                        verdict = await asyncio.to_thread(
                            _classify_request_completeness,
                            cc_cfg['host'], cc_cfg['model'], cc_cfg['instruction'],
                            chat_state['conversation'],
                        )
                        logging.info(f"[chat={chat_key}] completeness verdict={verdict}")
                        if not verdict.get('complete', True):
                            chat_state['phase'] = PHASE_AWAIT_INFO
                            await _persist()
                            await client.send_message(
                                event.chat,
                                f"{_MSG_NEED_INFO}\n{verdict.get('ask') or 'Could you clarify?'}",
                            )
                            return

                    chat_state['phase'] = PHASE_PROCESSING
                    chat_state['task_running'] = True
                    await _persist()
                    asyncio.create_task(_process_with_pending(event.chat, chat_key, chat_state))
                    return

        except Exception as e:
            logging.error(f"Telegram handler error: {e}", exc_info=True)

    logging.info(
        f"TeleTlamatini ready. completeness_check={cc_cfg['enabled']} "
        f"multi_turn={tla_cfg['multi_turn_enabled']} "
        f"exec_report={tla_cfg['exec_report_enabled']} "
        f"acpx={tla_cfg['acpx_enabled']} "
        f"target_agents={target_agents}"
    )
    try:
        await client.run_until_disconnected()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        await bridge.close()


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
        logging.info("TELETLAMATINI AGENT STARTED (pure bot mode)")
        logging.info(f"Sources: {config.get('source_agents') or []}")
        logging.info(f"Targets: {config.get('target_agents') or []}")
        try:
            asyncio.run(_telegram_main_loop(config))
        except KeyboardInterrupt:
            logging.info("TeleTlamatini stopped by user.")
        except Exception as e:
            logging.error(f"TeleTlamatini fatal error: {e}", exc_info=True)
    finally:
        time.sleep(0.4)
        remove_pid_file()
        logging.info("TeleTlamatini stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
