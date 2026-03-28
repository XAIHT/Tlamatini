# Gatewayer Agent - Inbound gateway: HTTP webhook / folder-drop ingress,
# validation, normalization, persistence, queuing, and downstream dispatch.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import hashlib
import json
import queue
import shutil
import signal
import ssl
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict
from urllib.parse import parse_qs, urlparse

import logging
import subprocess
import yaml

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
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


# ---------------------------------------------------------------------------
# Helper functions (copied from shoter.py boilerplate)
# ---------------------------------------------------------------------------

def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
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


# PID Management
PID_FILE = "agent.pid"


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
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ---------------------------------------------------------------------------
# Reanimation-state helpers (reanim* files survive crashes/restarts)
# ---------------------------------------------------------------------------

REANIM_QUEUE_FILE = "reanim_queue.json"
REANIM_DEDUP_FILE = "reanim_dedup.json"


def save_reanim_queue(events: list):
    try:
        with open(REANIM_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"GATEWAY_ERROR Failed to save reanim queue: {e}")


def load_reanim_queue() -> list:
    if not os.path.exists(REANIM_QUEUE_FILE):
        return []
    try:
        with open(REANIM_QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"GATEWAY_ERROR Failed to load reanim queue: {e}")
        return []


def save_reanim_dedup(dedup_state: dict):
    try:
        with open(REANIM_DEDUP_FILE, "w", encoding="utf-8") as f:
            json.dump(dedup_state, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"GATEWAY_ERROR Failed to save reanim dedup: {e}")


def load_reanim_dedup() -> dict:
    if not os.path.exists(REANIM_DEDUP_FILE):
        return {}
    try:
        with open(REANIM_DEDUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"GATEWAY_ERROR Failed to load reanim dedup: {e}")
        return {}


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()
event_queue: queue.Queue = queue.Queue()


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

def authenticate_request(handler, auth_cfg: dict) -> bool:
    """Return True if request passes authentication, False otherwise."""
    mode = auth_cfg.get('mode', 'none')

    # IP allowlist (applied regardless of mode when list is non-empty)
    allowed_ips = auth_cfg.get('allowed_ips', [])
    if allowed_ips:
        client_ip = handler.client_address[0]
        if client_ip not in allowed_ips:
            return False

    if mode == 'none':
        return True

    if mode == 'bearer':
        expected_token = auth_cfg.get('bearer_token', '')
        if not expected_token:
            return True  # no token configured -> open
        header_name = auth_cfg.get('header_name', 'Authorization')
        auth_value = handler.headers.get(header_name, '')
        return auth_value == f"Bearer {expected_token}"

    if mode == 'hmac':
        import hmac as hmac_mod
        secret = auth_cfg.get('hmac_secret', '')
        if not secret:
            return True
        sig_header = auth_cfg.get('signature_header', 'X-Tlamatini-Signature')
        ts_header = auth_cfg.get('timestamp_header', 'X-Tlamatini-Timestamp')
        signature = handler.headers.get(sig_header, '')
        timestamp = handler.headers.get(ts_header, '')
        if not signature or not timestamp:
            return False
        max_skew = auth_cfg.get('max_clock_skew_sec', 300)
        try:
            ts_val = float(timestamp)
            if abs(time.time() - ts_val) > max_skew:
                return False
        except (ValueError, TypeError):
            return False
        body_bytes = getattr(handler, '_raw_body', b'')
        expected_sig = hmac_mod.new(
            secret.encode(), timestamp.encode() + body_bytes, hashlib.sha256
        ).hexdigest()
        return hmac_mod.compare_digest(signature, expected_sig)

    return False


# ---------------------------------------------------------------------------
# Event envelope builder
# ---------------------------------------------------------------------------

def build_event_envelope(handler, body_bytes: bytes, config: dict) -> dict:
    """Normalise an inbound request into a canonical event envelope."""
    payload_cfg = config.get('payload', {})
    event_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()

    parsed_url = urlparse(handler.path)
    query_params = parse_qs(parsed_url.query)

    content_type = handler.headers.get('Content-Type', '')
    body_text = body_bytes.decode('utf-8', errors='replace')

    parsed_body = None
    if payload_cfg.get('parse_json', True) and 'json' in content_type:
        try:
            parsed_body = json.loads(body_text)
        except json.JSONDecodeError:
            parsed_body = None
    elif 'x-www-form-urlencoded' in content_type:
        parsed_body = parse_qs(body_text)

    event_type_field = payload_cfg.get('event_type_field', 'event_type')
    session_id_field = payload_cfg.get('session_id_field', 'session_id')
    correlation_header = payload_cfg.get('correlation_id_header', 'X-Correlation-ID')

    event_type = ''
    session_id = ''
    if isinstance(parsed_body, dict):
        event_type = str(parsed_body.get(event_type_field, ''))
        session_id = str(parsed_body.get(session_id_field, ''))

    correlation_id = handler.headers.get(correlation_header, '')

    body_hash = hashlib.sha256(body_bytes).hexdigest()

    envelope = {
        'event_id': event_id,
        'received_at': now,
        'event_type': event_type,
        'session_id': session_id,
        'correlation_id': correlation_id,
        'body_hash': body_hash,
        'content_type': content_type,
        'method': handler.command,
        'path': handler.path,
        'query_params': query_params if payload_cfg.get('save_query_params', True) else {},
        'headers': dict(handler.headers) if payload_cfg.get('save_headers', True) else {},
        'body': parsed_body if parsed_body is not None else body_text,
        'raw_body': body_text if payload_cfg.get('save_raw_body', True) else None,
    }
    return envelope


# ---------------------------------------------------------------------------
# Payload logging for downstream agents (Forker / Summarizer / Parametrizer)
# ---------------------------------------------------------------------------

def _log_event_payload(envelope: dict):
    """Log accepted event payload in two formats for downstream consumption.

    1. **Flat key-value lines** (``MESSAGE_<KEY>: <VALUE>``) — one per body
       field when the body is a JSON object, or a single ``MESSAGE_BODY:``
       line otherwise.  These are designed so that Forker can pattern-match
       on specific payload values (e.g. ``MESSAGE_TYPE: TELEGRAM``).

    2. **Structured output block** wrapped in
       ``INI_GATEWAY_EVENT<<< … >>>END_GATEWAY_EVENT`` delimiters with one
       ``key: value`` per line.  Parametrizer parses individual fields from
       these lines; Summarizer can feed the whole block to an LLM.
    """
    event_id = envelope.get('event_id', '')
    body = envelope.get('body')

    # ── 1) Flat key-value lines for Forker pattern matching ──────────
    if isinstance(body, dict):
        for key, value in body.items():
            logging.info(f"MESSAGE_{key.upper()}: {value}")
    elif body:
        logging.info(f"MESSAGE_BODY: {body}")

    if envelope.get('event_type'):
        logging.info(f"EVENT_TYPE: {envelope['event_type']}")
    if envelope.get('session_id'):
        logging.info(f"SESSION_ID: {envelope['session_id']}")

    # ── 2) Structured block for Summarizer / Parametrizer ────────────
    body_str = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body or '')
    block = (
        f"event_id: {event_id}\n"
        f"event_type: {envelope.get('event_type', '')}\n"
        f"session_id: {envelope.get('session_id', '')}\n"
        f"correlation_id: {envelope.get('correlation_id', '')}\n"
        f"content_type: {envelope.get('content_type', '')}\n"
        f"method: {envelope.get('method', '')}\n"
        f"path: {envelope.get('path', '')}\n"
        f"body: {body_str}"
    )

    logging.info(
        f"INI_GATEWAY_EVENT<<<\n{block}\n>>>END_GATEWAY_EVENT"
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_request(handler, body_bytes: bytes, config: dict) -> str | None:
    """Return an error string if the request is invalid, else None."""
    payload_cfg = config.get('payload', {})

    content_type = handler.headers.get('Content-Type', '')
    accepted = payload_cfg.get('accepted_content_types', [])
    if accepted and not any(ct in content_type for ct in accepted):
        return f"Unsupported Content-Type: {content_type}"

    max_bytes = payload_cfg.get('max_body_bytes', 1_048_576)
    if len(body_bytes) > max_bytes:
        return f"Payload too large: {len(body_bytes)} > {max_bytes}"

    required_fields = payload_cfg.get('required_fields', [])
    if required_fields and 'json' in content_type:
        try:
            body_obj = json.loads(body_bytes)
        except json.JSONDecodeError:
            return "Invalid JSON body"
        if isinstance(body_obj, dict):
            for field in required_fields:
                if field not in body_obj:
                    return f"Missing required field: {field}"

    return None


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def compute_dedup_key(envelope: dict, key_fields: list) -> str:
    parts = []
    for field in key_fields:
        parts.append(str(envelope.get(field, '')))
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()


def is_duplicate(dedup_key: str, dedup_state: dict, window_sec: int) -> bool:
    now = time.time()
    if dedup_key in dedup_state:
        if now - dedup_state[dedup_key] < window_sec:
            return True
    return False


def prune_dedup_state(dedup_state: dict, window_sec: int):
    now = time.time()
    expired = [k for k, ts in dedup_state.items() if now - ts >= window_sec]
    for k in expired:
        del dedup_state[k]


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def persist_event(envelope: dict, config: dict):
    """Write event artifacts to disk."""
    storage_cfg = config.get('storage', {})
    output_dir = storage_cfg.get('output_dir', 'gateway_events')
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(script_dir, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    event_id = envelope['event_id']
    event_dir = os.path.join(output_dir, event_id)
    os.makedirs(event_dir, exist_ok=True)

    if storage_cfg.get('write_event_json', True):
        with open(os.path.join(event_dir, 'event.json'), 'w', encoding='utf-8') as f:
            json.dump(envelope, f, ensure_ascii=False, indent=2)

    if storage_cfg.get('write_request_body', True) and envelope.get('raw_body'):
        with open(os.path.join(event_dir, 'request_body.txt'), 'w', encoding='utf-8') as f:
            f.write(envelope['raw_body'])

    if storage_cfg.get('write_headers_json', True) and envelope.get('headers'):
        with open(os.path.join(event_dir, 'headers.json'), 'w', encoding='utf-8') as f:
            json.dump(envelope['headers'], f, ensure_ascii=False, indent=2)

    # Update latest event pointer
    latest_file = storage_cfg.get('latest_event_file', 'latest_event.json')
    latest_path = os.path.join(output_dir, latest_file)
    try:
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(envelope, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"GATEWAY_ERROR Failed to write latest event file: {e}")


# ---------------------------------------------------------------------------
# HTTP Webhook Handler
# ---------------------------------------------------------------------------

# These are set before the server starts — avoids class-level mutable sharing issues
_gatewayer_config: Dict = {}
_gatewayer_dedup_state: dict = {}
_gatewayer_dedup_lock = threading.Lock()
_gatewayer_log_cfg: dict = {}


class GatewayerHandler(BaseHTTPRequestHandler):
    """Handle inbound webhook requests."""

    def log_message(self, format, *args):  # noqa: A002
        logging.info(f"HTTP {args[0] if args else ''}")

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get('Content-Length', 0))
        payload_cfg = _gatewayer_config.get('payload', {})
        max_bytes = payload_cfg.get('max_body_bytes', 1_048_576)
        to_read = min(content_length, max_bytes + 1)
        return self.rfile.read(to_read)

    def _send_json(self, status: int, body: dict):
        resp_cfg = _gatewayer_config.get('response', {})
        ct = resp_cfg.get('content_type', 'application/json')
        raw = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        self._handle_request()

    def do_PUT(self):  # noqa: N802
        self._handle_request()

    def do_PATCH(self):  # noqa: N802
        self._handle_request()

    def _handle_request(self):
        resp_cfg = _gatewayer_config.get('response', {})
        log_cfg = _gatewayer_log_cfg
        queue_cfg = _gatewayer_config.get('queue', {})

        body_bytes = self._read_body()
        self._raw_body = body_bytes  # used by HMAC auth

        # Authenticate
        auth_cfg = _gatewayer_config.get('auth', {})
        if not authenticate_request(self, auth_cfg):
            logging.info(f"{log_cfg.get('rejected_word', 'GATEWAY_EVENT_REJECTED')} auth_failed")
            self._send_json(
                resp_cfg.get('rejected_status', 401),
                {'status': 'rejected', 'reason': 'authentication_failed'}
            )
            return

        # Validate
        err = validate_request(self, body_bytes, _gatewayer_config)
        if err:
            logging.info(f"{log_cfg.get('rejected_word', 'GATEWAY_EVENT_REJECTED')} {err}")
            self._send_json(
                resp_cfg.get('error_status', 500),
                {'status': 'rejected', 'reason': err}
            )
            return

        # Build canonical envelope
        envelope = build_event_envelope(self, body_bytes, _gatewayer_config)
        event_id = envelope['event_id']

        # Dedup check
        if queue_cfg.get('dedup_enabled', False):
            key_fields = queue_cfg.get('dedup_key_fields', [])
            window = queue_cfg.get('dedup_window_sec', 30)
            dedup_key = compute_dedup_key(envelope, key_fields)
            with _gatewayer_dedup_lock:
                if is_duplicate(dedup_key, _gatewayer_dedup_state, window):
                    logging.info(f"{log_cfg.get('rejected_word', 'GATEWAY_EVENT_REJECTED')} duplicate event_id={event_id}")
                    self._send_json(
                        resp_cfg.get('accepted_status', 202),
                        {'status': 'duplicate', 'event_id': event_id}
                    )
                    return
                _gatewayer_dedup_state[dedup_key] = time.time()
                prune_dedup_state(_gatewayer_dedup_state, window)
                save_reanim_dedup(_gatewayer_dedup_state)

        # Persist
        try:
            persist_event(envelope, _gatewayer_config)
        except Exception as e:
            logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} persist failed: {e}")

        logging.info(f"{log_cfg.get('accepted_word', 'GATEWAY_EVENT_ACCEPTED')} event_id={event_id}")

        # Log payload details for downstream agents (Forker, Summarizer, Parametrizer)
        _log_event_payload(envelope)

        # Enqueue
        max_pending = queue_cfg.get('max_pending_events', 100)
        overflow = queue_cfg.get('overflow_policy', 'reject_new')
        if event_queue.qsize() >= max_pending:
            if overflow == 'reject_new':
                logging.warning(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} queue full, rejecting event_id={event_id}")
                self._send_json(
                    resp_cfg.get('error_status', 500),
                    {'status': 'rejected', 'reason': 'queue_full', 'event_id': event_id}
                )
                return

        event_queue.put(envelope)
        logging.info(f"{log_cfg.get('queued_word', 'GATEWAY_EVENT_QUEUED')} event_id={event_id} queue_size={event_queue.qsize()}")

        # Persist queue snapshot for crash recovery
        _persist_queue_snapshot()

        # Return immediate ack
        self._send_json(
            resp_cfg.get('accepted_status', 202),
            {'status': 'accepted', 'event_id': event_id}
        )


def _persist_queue_snapshot():
    """Snapshot pending events in queue to reanim file."""
    items = list(event_queue.queue)
    save_reanim_queue(items)


# ---------------------------------------------------------------------------
# Folder-drop watcher
# ---------------------------------------------------------------------------

def folder_watch_loop(config: dict):
    """Poll a directory for new files and enqueue them as events."""
    fw_cfg = config.get('folder_watch', {})
    log_cfg = config.get('logging_behavior', {})
    watch_path = fw_cfg.get('watch_path', '')
    if not watch_path:
        logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} folder_watch.watch_path not set")
        return
    if not os.path.isabs(watch_path):
        watch_path = os.path.join(script_dir, watch_path)

    pattern = fw_cfg.get('file_pattern', '*.json')
    poll_interval = fw_cfg.get('poll_interval', 2)
    archive = fw_cfg.get('archive_processed', True)
    processed_dir = fw_cfg.get('processed_dir', 'processed')

    import fnmatch
    os.makedirs(watch_path, exist_ok=True)

    while not shutdown_event.is_set():
        try:
            files = [f for f in os.listdir(watch_path) if fnmatch.fnmatch(f, pattern) and os.path.isfile(os.path.join(watch_path, f))]
            for fname in sorted(files):
                if shutdown_event.is_set():
                    break
                fpath = os.path.join(watch_path, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        body_text = f.read()
                except Exception as e:
                    logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} read {fname}: {e}")
                    continue

                event_id = uuid.uuid4().hex
                now = datetime.now(timezone.utc).isoformat()
                body_hash = hashlib.sha256(body_text.encode()).hexdigest()
                parsed_body = None
                try:
                    parsed_body = json.loads(body_text)
                except (json.JSONDecodeError, ValueError):
                    pass

                payload_cfg = config.get('payload', {})
                event_type = ''
                session_id = ''
                if isinstance(parsed_body, dict):
                    event_type = str(parsed_body.get(payload_cfg.get('event_type_field', 'event_type'), ''))
                    session_id = str(parsed_body.get(payload_cfg.get('session_id_field', 'session_id'), ''))

                envelope = {
                    'event_id': event_id,
                    'received_at': now,
                    'event_type': event_type,
                    'session_id': session_id,
                    'correlation_id': '',
                    'body_hash': body_hash,
                    'content_type': 'application/json' if parsed_body is not None else 'text/plain',
                    'method': 'FILE_DROP',
                    'path': fpath,
                    'query_params': {},
                    'headers': {},
                    'body': parsed_body if parsed_body is not None else body_text,
                    'raw_body': body_text,
                    'source_file': fname,
                }

                # Persist and enqueue
                try:
                    persist_event(envelope, config)
                except Exception as e:
                    logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} persist {fname}: {e}")

                logging.info(f"{log_cfg.get('accepted_word', 'GATEWAY_EVENT_ACCEPTED')} file={fname} event_id={event_id}")

                # Log payload details for downstream agents (Forker, Summarizer, Parametrizer)
                _log_event_payload(envelope)

                event_queue.put(envelope)
                logging.info(f"{log_cfg.get('queued_word', 'GATEWAY_EVENT_QUEUED')} event_id={event_id}")
                _persist_queue_snapshot()

                # Archive processed file
                if archive:
                    archive_dir = os.path.join(watch_path, processed_dir)
                    os.makedirs(archive_dir, exist_ok=True)
                    try:
                        shutil.move(fpath, os.path.join(archive_dir, fname))
                    except Exception as e:
                        logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} archive {fname}: {e}")
                else:
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} remove {fname}: {e}")

        except Exception as e:
            logging.error(f"{log_cfg.get('error_word', 'GATEWAY_ERROR')} folder_watch loop: {e}")

        shutdown_event.wait(poll_interval)


# ---------------------------------------------------------------------------
# Dispatch loop — drains event_queue and triggers downstream target_agents
# ---------------------------------------------------------------------------

def dispatch_loop(config: dict):
    """Background thread: drain the event queue and start target_agents one at a time."""
    target_agents = config.get('target_agents', [])
    log_cfg = config.get('logging_behavior', {})
    idle_ms = config.get('runtime', {}).get('idle_sleep_ms', 250)
    idle_sec = idle_ms / 1000.0

    while not shutdown_event.is_set():
        try:
            envelope = event_queue.get(timeout=idle_sec)
        except queue.Empty:
            continue

        event_id = envelope.get('event_id', '?')

        # Persist response record
        try:
            storage_cfg = config.get('storage', {})
            output_dir = storage_cfg.get('output_dir', 'gateway_events')
            if not os.path.isabs(output_dir):
                output_dir = os.path.join(script_dir, output_dir)
            resp_path = os.path.join(output_dir, event_id, 'dispatch.json')
            if os.path.isdir(os.path.join(output_dir, event_id)):
                with open(resp_path, 'w', encoding='utf-8') as f:
                    json.dump({'dispatched_at': datetime.now(timezone.utc).isoformat()}, f)
        except Exception:
            pass

        if target_agents:
            # Concurrency guard: wait for all targets to stop before dispatching
            wait_for_agents_to_stop(target_agents)
            logging.info(f"{log_cfg.get('dispatched_word', 'GATEWAY_EVENT_DISPATCHED')} event_id={event_id} targets={target_agents}")
            for target in target_agents:
                start_agent(target)
        else:
            logging.info(f"{log_cfg.get('dispatched_word', 'GATEWAY_EVENT_DISPATCHED')} event_id={event_id} (no target_agents)")

        # Update reanim snapshot (remove dispatched)
        _persist_queue_snapshot()


# ---------------------------------------------------------------------------
# Old-event cleanup
# ---------------------------------------------------------------------------

def cleanup_old_events(config: dict):
    storage_cfg = config.get('storage', {})
    keep_days = storage_cfg.get('keep_days', 7)
    if keep_days <= 0:
        return
    output_dir = storage_cfg.get('output_dir', 'gateway_events')
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(script_dir, output_dir)
    if not os.path.isdir(output_dir):
        return
    cutoff = time.time() - keep_days * 86400
    for entry in os.listdir(output_dir):
        entry_path = os.path.join(output_dir, entry)
        if os.path.isdir(entry_path):
            try:
                mtime = os.path.getmtime(entry_path)
                if mtime < cutoff:
                    shutil.rmtree(entry_path, ignore_errors=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _gatewayer_config, _gatewayer_dedup_state, _gatewayer_log_cfg

    config = load_config()
    write_pid_file()

    try:
        _gatewayer_config = config
        _gatewayer_log_cfg = config.get('logging_behavior', {})

        target_agents = config.get('target_agents', [])
        listen_mode = config.get('listen_mode', 'http_webhook')

        logging.info("GATEWAYER AGENT STARTED")
        logging.info(f"Listen mode: {listen_mode}")
        logging.info(f"Targets: {target_agents}")

        # Restore reanim state
        restored_queue = load_reanim_queue()
        if restored_queue:
            logging.info(f"Restoring {len(restored_queue)} events from reanim queue")
            for ev in restored_queue:
                event_queue.put(ev)

        _gatewayer_dedup_state = load_reanim_dedup()

        # Cleanup old events on startup
        cleanup_old_events(config)

        # Graceful shutdown handler
        def _signal_handler(signum, frame):
            logging.info("Shutdown signal received, stopping...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        # Start dispatch loop thread
        dispatch_thread = threading.Thread(target=dispatch_loop, args=(config,), daemon=True)
        dispatch_thread.start()

        # Start folder watch thread if enabled
        fw_cfg = config.get('folder_watch', {})
        if fw_cfg.get('enabled', False):
            fw_thread = threading.Thread(target=folder_watch_loop, args=(config,), daemon=True)
            fw_thread.start()
            logging.info("Folder-drop watcher started")

        # Start HTTP server if enabled
        http_cfg = config.get('http', {})
        if http_cfg.get('enabled', True):
            host = http_cfg.get('host', '127.0.0.1')
            port = int(http_cfg.get('port', 8787))

            server = HTTPServer((host, port), GatewayerHandler)

            if http_cfg.get('use_tls', False):
                cert_file = http_cfg.get('cert_file', '')
                key_file = http_cfg.get('key_file', '')
                if cert_file and key_file:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.load_cert_chain(cert_file, key_file)
                    server.socket = ctx.wrap_socket(server.socket, server_side=True)
                    logging.info("TLS enabled")

            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            logging.info(f"HTTP webhook listening on {host}:{port}{http_cfg.get('path', '/gatewayer')}")

            # Block until shutdown
            graceful_sec = config.get('runtime', {}).get('graceful_shutdown_sec', 5)
            shutdown_event.wait()
            logging.info("Shutting down HTTP server...")
            server.shutdown()
            dispatch_thread.join(timeout=graceful_sec)
        else:
            # No HTTP, just wait for shutdown
            shutdown_event.wait()

        logging.info("Gatewayer agent finished.")

    except Exception as e:
        logging.error(f"{_gatewayer_log_cfg.get('error_word', 'GATEWAY_ERROR')} {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
