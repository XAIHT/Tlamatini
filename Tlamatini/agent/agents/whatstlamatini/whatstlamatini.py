# WhatsTlamatini Agent — pure WhatsApp-Cloud-API bridge to the Tlamatini chat core.
#
# Mirror of TeleTlamatini, swapping Telegram for Meta's WhatsApp Cloud API
# (https://developers.facebook.com/docs/whatsapp/cloud-api/).
#
# Architecture parity with TeleTlamatini:
#   * Single persistent Tlamatini bridge (one HTTP login, one WS, reused
#     for every WhatsApp message — no per-message re-login overhead).
#   * Per-chat phase state machine (AWAIT_PASSWORD / READY / PROCESSING /
#     AWAIT_INFO). Reanim-aware via reanim.state.
#   * Optional Ollama-based completeness gate (off by default; fire-and-go
#     by default like TeleTlamatini).
#   * Configurable target_agents started after each completed cycle.
#
# Differences vs. Telegram (forced by the WhatsApp protocol surface):
#   * WhatsApp does NOT expose message editing for free-tier text replies the
#     same way Telegram does. Instead, we send "🔄 Working on it…" once and
#     post the assembled answer as a follow-up reply. The user's experience
#     is the same — request in, status, answer out.
#   * Inbound = HTTP POST webhook from Meta to a configurable host:port path.
#     The user must expose this URL publicly (ngrok / domain / port-forward).
#     A small stdlib http.server runs in a daemon thread and pushes parsed
#     messages onto an asyncio.Queue consumed by the main loop.
#   * Outbound = HTTP POST to Graph API
#     `https://graph.facebook.com/v20.0/<phone_number_id>/messages`.
#
# Required Meta credentials (from https://business.facebook.com →
# WhatsApp Manager → API Setup):
#   * phone_number_id   — the test/production WABA number's ID.
#   * access_token      — system-user permanent token.
#   * verify_token      — any string of your choice; Meta sends it back during
#                         webhook subscription, the agent echoes the challenge.

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
import threading
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
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
# Config / PID helpers (verbatim from teletlamatini.py — these are the agent
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
# in this agent. Real chat answers carry NO `type` field; UI-control frames DO;
# only `multi_turn_used` / `answer_success` extras mark the assembled final.
# (Same contract as TeleTlamatini — keep in sync if upstream changes.)
# ---------------------------------------------------------------------------

_SPECIAL_TYPES_TO_SKIP: Tuple[str, ...] = (
    "mcp", "tool", "agent",
    "heartbeat", "session-restored", "context-path-set",
    "establishment-completed",
    # Ask-Execs UI-control frames. The bot never enables Ask Execs
    # (ask_execs_enabled is hard-pinned False), so it never triggers these
    # for its OWN requests. But the consumer broadcasts `exec-permission-
    # request` to the whole per-user room group (chat_user_<id>); if a human
    # browser is logged into the SAME Tlamatini account and ticks Ask Execs,
    # that frame lands on the bot's socket too. Skip it explicitly so it can
    # never be mistaken for a partial/final answer. (Run the bot on a
    # dedicated account to avoid this cross-talk entirely — see config.yaml.)
    "exec-permission-request", "exec-permission-response",
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
# WhatsApp-friendly HTML→text stripping for the assembled answer.
# WhatsApp text supports very limited inline formatting (*bold*, _italic_,
# ~strike~, ```mono```), so we strip everything to plain text and let line
# breaks do the structuring. Identical philosophy to TeleTlamatini.
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
# TlamatiniBridge — single persistent session+WS, reused across all chats.
# Verbatim port from teletlamatini.py (only the docstring chat platform
# noun differs). The bridge is platform-agnostic.
# ---------------------------------------------------------------------------

class TlamatiniBridge:
    """
    Maintains ONE Django session and ONE WebSocket connection to Tlamatini
    for the lifetime of the agent. Every WhatsApp message is forwarded
    through the same WS, saving the per-request HTTP login + WS handshake +
    establishment-frame burst that a stateless implementation would pay
    every single time.
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
        # the planner for this request, so the LLM can run the complete ACPX
        # scheme (acp_doctor → acp_spawn → acp_send_and_wait → acp_relay →
        # acp_kill, plus list_skills / invoke_skill) straight from a WhatsApp
        # message. When False, `agent.acpx.filter_acpx_tools()` strips them out
        # and the request falls back to the legacy Multi-Turn / one-shot flow.
        # Mirrors the `#acpx-enabled` toolbar checkbox (and TeleTlamatini).
        self.acpx_enabled = acpx_enabled
        self.total_timeout = float(total_timeout)
        self.idle_timeout = float(idle_timeout)

        self._ws = None  # websockets client connection
        self._cookie_header: Optional[str] = None
        self._lock = asyncio.Lock()
        self._closed = False

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

    async def _drain_queued(self, log_tag: str, max_frames: int = 200):
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
                logging.warning(
                    f"{log_tag} bridge: drained stale {v} frame "
                    f"({_summarize_frame_for_log(data)})"
                )
        if drained:
            logging.info(f"{log_tag} bridge: drained {drained} stale frames")

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
        for attempt in (1, 2):
            try:
                await self.ensure_connected(log_tag)
                await self._drain_queued(log_tag)
                return await self._send_and_collect(log_tag, user_message)
            except Exception as e:
                logging.warning(
                    f"{log_tag} bridge: chat attempt {attempt} failed: {e}"
                )
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
            # Ask-Execs is HARD-PINNED OFF for the bot. The per-tool
            # Proceed/Deny gate (consumers.py) renders as a BROWSER modal —
            # a WhatsApp operator can never answer it, so a request with
            # ask_execs on would BLOCK the executor thread until total_timeout
            # and then return empty. By design WhatsTlamatini is fully
            # authorized: every state-changing tool runs unattended (the
            # access password IS the authorization). We send the flag
            # explicitly as False rather than omitting it so a future change
            # to the server-side default can never silently re-gate the bot.
            'ask_execs_enabled': False,
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
# WhatsApp Cloud API client — outbound text messages via Graph API.
# ---------------------------------------------------------------------------

class WhatsAppCloudClient:
    """Thin sync wrapper around the Meta Graph API. We call this from a
    thread (`asyncio.to_thread`) so the event loop never blocks on HTTP."""

    GRAPH_API_VERSION = "v20.0"
    MAX_BODY_LEN = 4000  # WhatsApp text-body hard limit is 4096; leave headroom

    def __init__(self, phone_number_id: str, access_token: str,
                 graph_base: str = "https://graph.facebook.com"):
        self.phone_number_id = (phone_number_id or '').strip()
        self.access_token = (access_token or '').strip()
        self.graph_base = graph_base.rstrip('/')

    def _send_one(self, to: str, text: str) -> Tuple[bool, str]:
        if not self.phone_number_id or not self.access_token:
            return False, "phone_number_id or access_token missing"
        url = f"{self.graph_base}/{self.GRAPH_API_VERSION}/{self.phone_number_id}/messages"
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": str(to),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                if 200 <= resp.status < 300:
                    return True, resp_body
                return False, f"HTTP {resp.status}: {resp_body[:300]}"
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                err_body = str(e)
            return False, f"HTTPError {e.code}: {err_body[:300]}"
        except Exception as e:
            return False, f"send error: {e}"

    def send(self, to: str, text: str) -> bool:
        """Send a (possibly long) text by chunking. Returns True if all
        chunks succeeded."""
        if not text:
            return True
        chunks = [text[i:i + self.MAX_BODY_LEN]
                  for i in range(0, len(text), self.MAX_BODY_LEN)] or [text]
        all_ok = True
        for chunk in chunks:
            ok, info = self._send_one(to, chunk)
            if ok:
                logging.info(f"WhatsApp send → {to}: OK ({len(chunk)} chars)")
            else:
                all_ok = False
                logging.error(f"WhatsApp send → {to}: FAIL — {info}")
                break
        return all_ok


# ---------------------------------------------------------------------------
# Inbound webhook (Meta posts here when a WhatsApp message arrives).
#
# Meta requires an HTTPS endpoint in production. For local development you
# can expose this listener via ngrok / cloudflared / a router port-forward
# and configure the resulting URL in your WhatsApp App's webhook settings.
# Subscribe to the `messages` field on the WABA app.
# ---------------------------------------------------------------------------

class _WebhookHTTPHandler(BaseHTTPRequestHandler):
    # Set by WebhookServer.bind_handler before serving
    inbox_queue: "asyncio.Queue" = None  # type: ignore
    main_loop: asyncio.AbstractEventLoop = None  # type: ignore
    expected_path: str = "/wa-webhook"
    verify_token: str = ""

    def log_message(self, fmt, *args):  # noqa: A003 — overriding stdlib API
        logging.info("webhook: " + (fmt % args))

    def _respond(self, status: int, body: bytes = b"", content_type: str = "text/plain"):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except Exception as e:
            logging.error(f"webhook: failed to write response: {e}")

    def do_GET(self):  # noqa: N802 — stdlib API
        # Meta verification handshake:
        # GET <url>?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<n>
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != self.expected_path:
                self._respond(404, b"not found")
                return
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            mode = qs.get("hub.mode")
            token = qs.get("hub.verify_token")
            challenge = qs.get("hub.challenge", "")
            if mode == "subscribe" and token and token == self.verify_token:
                logging.info("webhook: Meta verification OK")
                self._respond(200, challenge.encode("utf-8"))
                return
            logging.warning(
                f"webhook: verification rejected (mode={mode!r}, token_match={token == self.verify_token})"
            )
            self._respond(403, b"forbidden")
        except Exception as e:
            logging.error(f"webhook GET error: {e}")
            self._respond(500, b"error")

    def do_POST(self):  # noqa: N802 — stdlib API
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != self.expected_path:
                self._respond(404, b"not found")
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except Exception as e:
                logging.warning(f"webhook: non-JSON body ({e}); ack anyway")
                self._respond(200, b"ok")
                return

            # Meta requires a 200 ack within ~5 s, regardless of processing.
            self._respond(200, b"ok")

            # Walk the standard Meta payload structure and extract every
            # text message. The schema is documented at
            # https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
            for entry in payload.get("entry", []) or []:
                for change in entry.get("changes", []) or []:
                    value = change.get("value", {}) or {}
                    messages = value.get("messages", []) or []
                    for msg in messages:
                        msg_type = msg.get("type")
                        sender = msg.get("from")
                        msg_id = msg.get("id")
                        if not sender:
                            continue
                        if msg_type == "text":
                            text = ((msg.get("text") or {}).get("body") or "").strip()
                            if text:
                                self._enqueue(sender, text, msg_id)
                        elif msg_type == "interactive":
                            inter = msg.get("interactive") or {}
                            kind = inter.get("type")
                            if kind == "button_reply":
                                text = ((inter.get("button_reply") or {}).get("title") or "").strip()
                            elif kind == "list_reply":
                                text = ((inter.get("list_reply") or {}).get("title") or "").strip()
                            else:
                                text = ""
                            if text:
                                self._enqueue(sender, text, msg_id)
                        else:
                            # Unsupported message types (image / audio / etc.)
                            self._enqueue(
                                sender,
                                f"[unsupported message type: {msg_type}]",
                                msg_id,
                            )
        except Exception as e:
            logging.error(f"webhook POST error: {e}", exc_info=True)
            try:
                self._respond(500, b"error")
            except Exception:
                pass

    def _enqueue(self, sender: str, text: str, msg_id: Optional[str]):
        item = {"sender": sender, "text": text, "msg_id": msg_id}
        try:
            asyncio.run_coroutine_threadsafe(
                self.inbox_queue.put(item),
                self.main_loop,
            )
            logging.info(f"webhook: queued message id={msg_id} from={sender} len={len(text)}")
        except Exception as e:
            logging.error(f"webhook: failed to enqueue message: {e}")


class WebhookServer:
    """Runs a stdlib ThreadingHTTPServer in a daemon thread."""

    def __init__(self, host: str, port: int, path: str, verify_token: str,
                 inbox_queue: asyncio.Queue, main_loop: asyncio.AbstractEventLoop):
        self.host = host
        self.port = int(port)
        self.path = path or "/wa-webhook"
        self.verify_token = verify_token or ""
        self.inbox_queue = inbox_queue
        self.main_loop = main_loop
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        # Bind handler-class fields once; instances inherit them.
        _WebhookHTTPHandler.inbox_queue = self.inbox_queue
        _WebhookHTTPHandler.main_loop = self.main_loop
        _WebhookHTTPHandler.expected_path = self.path
        _WebhookHTTPHandler.verify_token = self.verify_token

        self._httpd = ThreadingHTTPServer((self.host, self.port), _WebhookHTTPHandler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="WhatsTlamatini-Webhook",
            daemon=True,
        )
        self._thread.start()
        logging.info(
            f"webhook: listening on http://{self.host}:{self.port}{self.path} "
            f"(expose this URL publicly and register it in Meta App → Webhooks)"
        )

    def stop(self):
        try:
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
        except Exception as e:
            logging.warning(f"webhook: shutdown error: {e}")


# ---------------------------------------------------------------------------
# Config resolvers (mirror TeleTlamatini's flat-or-legacy shape, adapted
# for WhatsApp credentials).
# ---------------------------------------------------------------------------

PHASE_AWAIT_PASSWORD = "AWAIT_PASSWORD"
PHASE_READY = "READY"
PHASE_PROCESSING = "PROCESSING"
PHASE_AWAIT_INFO = "AWAIT_INFO"  # only used when completeness_check.enabled


def _resolve_whatsapp_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    wa = config.get('whatsapp') or {}
    return {
        'phone_number_id': str(wa.get('phone_number_id') or '').strip(),
        'access_token': str(wa.get('access_token') or '').strip(),
        'verify_token': str(wa.get('verify_token') or '').strip(),
        'webhook_host': str(wa.get('webhook_host') or '0.0.0.0').strip(),
        'webhook_port': int(wa.get('webhook_port') or 8765),
        'webhook_path': str(wa.get('webhook_path') or '/wa-webhook').strip(),
        'graph_base': str(wa.get('graph_base') or 'https://graph.facebook.com').rstrip('/'),
    }


def _resolve_password(config: Dict[str, Any]) -> str:
    return str(
        config.get('password')
        or (config.get('access') or {}).get('password')
        or ''
    ).strip()


def _resolve_completeness_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
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
        ws_url = base.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/agent/'
    multi_turn_enabled = bool(tla.get('multi_turn_enabled', True))
    # ACPX defaults to False at the resolver level (matching the chat toolbar's
    # system-wide default) so a WhatsTlamatini deploy from before this change
    # keeps its legacy behavior. The shipped config.yaml sets `acpx_enabled:
    # true` so fresh deploys can drive the full ACPX scheme out of the box.
    acpx_enabled = bool(tla.get('acpx_enabled', False))
    # ACPX needs the Multi-Turn planner to bind the 12 acp_* / *_skill tools;
    # with multi_turn off, the planner never runs and the ACPX surface is
    # effectively dead. Warn (non-fatal) rather than silently no-op.
    if acpx_enabled and not multi_turn_enabled:
        logging.warning(
            "tlamatini.acpx_enabled is true but multi_turn_enabled is false — "
            "the ACPX tool surface only binds under Multi-Turn, so ACPX will be "
            "inert this run. Set multi_turn_enabled: true to use ACPX."
        )
    return {
        'base_url': base,
        'ws_url': ws_url,
        'username': tla.get('username', 'user'),
        'password': tla.get('password', 'changeme'),
        'multi_turn_enabled': multi_turn_enabled,
        'exec_report_enabled': bool(tla.get('exec_report_enabled', True)),
        'acpx_enabled': acpx_enabled,
        'total_timeout': float(tla.get('total_timeout', 1800)),
        'idle_timeout': float(tla.get('response_idle_timeout', 8)),
    }


# Hard-coded user-facing strings. WhatsApp doesn't have /start in the
# Telegram sense; the gate triggers on the first message regardless.
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
_MSG_RESULT_HEADER = "✅ Result:\n"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def _whatsapp_main_loop(config: Dict[str, Any]):
    wa_cfg = _resolve_whatsapp_cfg(config)
    password_gate = _resolve_password(config)
    cc_cfg = _resolve_completeness_cfg(config)
    tla_cfg = _resolve_tlamatini_cfg(config)
    target_agents = config.get('target_agents', []) or []

    if not wa_cfg['phone_number_id'] or not wa_cfg['access_token']:
        logging.error(
            "whatsapp.phone_number_id / whatsapp.access_token missing in "
            "config.yaml. Get both from Meta WhatsApp Manager → API Setup."
        )
        return
    if not wa_cfg['verify_token']:
        logging.error(
            "whatsapp.verify_token missing in config.yaml. Pick any string; "
            "Meta will echo it back during webhook subscription."
        )
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
        logging.error(
            f"Initial Tlamatini bridge connect failed: {e}. "
            "The bot will start anyway and retry on first message."
        )

    # --- WhatsApp client (outbound) + webhook server (inbound) ---
    wa_client = WhatsAppCloudClient(
        phone_number_id=wa_cfg['phone_number_id'],
        access_token=wa_cfg['access_token'],
        graph_base=wa_cfg['graph_base'],
    )

    inbox_queue: asyncio.Queue = asyncio.Queue()
    main_loop = asyncio.get_running_loop()
    webhook = WebhookServer(
        host=wa_cfg['webhook_host'],
        port=wa_cfg['webhook_port'],
        path=wa_cfg['webhook_path'],
        verify_token=wa_cfg['verify_token'],
        inbox_queue=inbox_queue,
        main_loop=main_loop,
    )
    try:
        webhook.start()
    except Exception as e:
        logging.error(f"Failed to start webhook server: {e}", exc_info=True)
        return

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

    async def _send(chat_key: str, text: str):
        if not text:
            return
        ok = await asyncio.to_thread(wa_client.send, chat_key, text)
        if not ok:
            logging.warning(f"[chat={chat_key}] send returned False (see error above)")

    async def _process_request(chat_key: str, request_text: str):
        log_tag = f"[chat={chat_key}]"
        try:
            await _send(chat_key, _MSG_WORKING)
            logging.info(f"{log_tag} status message sent")
        except Exception as e:
            logging.error(f"{log_tag} send(working) failed: {e}")

        try:
            answer_html, counters = await bridge.chat(log_tag, request_text)
            answer_text = _strip_html_to_text(answer_html) or _MSG_EMPTY_RESULT
            logging.info(
                f"{log_tag} answer ready (html_len={len(answer_html)}, "
                f"text_len={len(answer_text)}, counters={counters})"
            )
            # WhatsApp has no edit-message; deliver as a fresh reply with a
            # short result header so the user can correlate it.
            await _send(chat_key, _MSG_RESULT_HEADER + answer_text)
        except Exception as exc:
            logging.error(f"{log_tag} bridge.chat failed: {exc}", exc_info=True)
            try:
                await _send(chat_key, f"{_MSG_ERROR_PREFIX}{exc}")
            except Exception as send_err:
                logging.error(f"{log_tag} failed to deliver error: {send_err}")

        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for tgt in target_agents:
                start_agent(tgt)

    async def _process_with_pending(chat_key: str, chat_state: Dict[str, Any]):
        try:
            req_text = "\n".join(
                t['content'] for t in chat_state.get('conversation', [])
                if t.get('role') == 'user'
            ).strip()
            await _process_request(chat_key, req_text)
            pending = chat_state.pop('pending_info', []) or []
            if pending:
                logging.info(f"[chat={chat_key}] {len(pending)} queued follow-ups")
                follow = "\n".join(pending).strip()
                if follow:
                    chat_state['conversation'] = [{'role': 'user', 'content': follow}]
                    await _process_request(chat_key, follow)
        finally:
            chat_state['conversation'] = []
            chat_state['phase'] = PHASE_READY
            chat_state.pop('task_running', None)
            await _persist()

    async def _handle_inbound(item: Dict[str, Any]):
        text = (item.get('text') or '').strip()
        chat_key = str(item.get('sender') or '').strip()
        if not text or not chat_key:
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
                    await _send(chat_key, _format_auth_ok(
                        tla_cfg['multi_turn_enabled'],
                        tla_cfg['exec_report_enabled'],
                        tla_cfg['acpx_enabled'],
                    ))
                    return
                elif not password_gate:
                    chat_state['phase'] = PHASE_READY
                    await _persist()
                    phase = PHASE_READY
                    # Fall through — first message becomes the first request.
                else:
                    await _send(chat_key, _MSG_AUTH_REJECTED)
                    await _send(chat_key, _MSG_PASSWORD_PROMPT)
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
                        await _send(
                            chat_key,
                            f"{_MSG_NEED_INFO}\n{verdict.get('ask') or 'Could you clarify?'}",
                        )
                        return

                chat_state['phase'] = PHASE_PROCESSING
                chat_state['task_running'] = True
                await _persist()
                asyncio.create_task(_process_with_pending(chat_key, chat_state))
                return

    logging.info(
        f"WhatsTlamatini ready. completeness_check={cc_cfg['enabled']} "
        f"multi_turn={tla_cfg['multi_turn_enabled']} "
        f"exec_report={tla_cfg['exec_report_enabled']} "
        f"acpx={tla_cfg['acpx_enabled']} "
        f"target_agents={target_agents} "
        f"webhook=http://{wa_cfg['webhook_host']}:{wa_cfg['webhook_port']}{wa_cfg['webhook_path']}"
    )

    try:
        while True:
            try:
                item = await inbox_queue.get()
            except asyncio.CancelledError:
                break
            try:
                await _handle_inbound(item)
            except Exception as e:
                logging.error(f"Inbound handler error: {e}", exc_info=True)
    finally:
        webhook.stop()
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
        logging.info("WHATSTLAMATINI AGENT STARTED (WhatsApp Cloud API bridge)")
        logging.info(f"Sources: {config.get('source_agents') or []}")
        logging.info(f"Targets: {config.get('target_agents') or []}")
        try:
            asyncio.run(_whatsapp_main_loop(config))
        except KeyboardInterrupt:
            logging.info("WhatsTlamatini stopped by user.")
        except Exception as e:
            logging.error(f"WhatsTlamatini fatal error: {e}", exc_info=True)
    finally:
        time.sleep(0.4)
        remove_pid_file()
        logging.info("WhatsTlamatini stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
