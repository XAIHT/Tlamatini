# GatewayRelayer Agent - Long-running deterministic ingress relay that bridges
# third-party webhook providers (e.g. GitHub) into Gatewayer's canonical
# timestamp+body HMAC format.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import hashlib
import hmac as hmac_mod
import json
import signal
import ssl
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

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
# Shared state
# ---------------------------------------------------------------------------

shutdown_event = threading.Event()


# ---------------------------------------------------------------------------
# GitHub signature verification
# ---------------------------------------------------------------------------

def verify_github_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 from GitHub."""
    if not secret:
        return True  # no secret configured -> skip verification
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac_mod.compare_digest(signature_header, f"sha256={expected}")


# ---------------------------------------------------------------------------
# Gatewayer HMAC signing
# ---------------------------------------------------------------------------

def sign_for_gatewayer(secret: str, timestamp: str, body: bytes) -> str:
    """Produce timestamp+body HMAC-SHA256 signature for Gatewayer."""
    return hmac_mod.new(
        secret.encode(), timestamp.encode() + body, hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Payload transformer
# ---------------------------------------------------------------------------

def transform_payload(event_type: str, delivery_id: str, upstream_body: dict) -> bytes:
    """Build the canonical payload that Gatewayer expects."""
    canonical = {
        "event_type": event_type,
        "session_id": delivery_id,
    }
    canonical.update(upstream_body)
    return json.dumps(canonical, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Forward to Gatewayer
# ---------------------------------------------------------------------------

def forward_to_gatewayer(payload: bytes, config: dict, correlation_id: str) -> dict:
    """POST the signed payload to the configured Gatewayer endpoint."""
    forward_url = config.get("forward_url", "http://127.0.0.1:8787/gatewayer")
    forward_secret = config.get("forward_hmac_secret", "")
    sig_header = config.get("forward_signature_header", "X-Tlamatini-Signature")
    ts_header = config.get("forward_timestamp_header", "X-Tlamatini-Timestamp")
    ct = config.get("forward_content_type", "application/json")
    corr_header = config.get("correlation_id_header", "X-Correlation-ID")
    timeout = int(config.get("request_timeout_sec", 15))

    timestamp = str(time.time())

    headers = {
        "Content-Type": ct,
        ts_header: timestamp,
    }

    if forward_secret:
        signature = sign_for_gatewayer(forward_secret, timestamp, payload)
        headers[sig_header] = signature

    if correlation_id:
        headers[corr_header] = correlation_id

    req = Request(forward_url, data=payload, headers=headers, method="POST")

    try:
        resp = urlopen(req, timeout=timeout)  # noqa: S310
        resp_body = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(resp_body)
        except (json.JSONDecodeError, ValueError):
            return {"status": "ok", "raw": resp_body}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"status": "error", "http_status": e.code, "body": body}
    except URLError as e:
        return {"status": "error", "reason": str(e.reason)}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


# ---------------------------------------------------------------------------
# Payload logging for downstream agents (Forker / Summarizer / Parametrizer)
# ---------------------------------------------------------------------------

def _log_relay_payload(event_type: str, delivery_id: str, upstream_body: dict):
    """Log relayed event payload in two formats for downstream consumption.

    1. **Flat key-value lines** (``MESSAGE_<KEY>: <VALUE>``) — one per
       top-level body field.  Forker can pattern-match these directly
       (e.g. ``MESSAGE_REF: refs/heads/main``).

    2. **Structured output block** wrapped in
       ``INI_RELAY_EVENT<<< … >>>END_RELAY_EVENT`` delimiters with one
       ``key: value`` per line.  Parametrizer parses individual fields;
       Summarizer can feed the whole block to an LLM.
    """
    # ── 1) Flat key-value lines for Forker ───────────────────────────
    logging.info(f"MESSAGE_EVENT_TYPE: {event_type}")
    if delivery_id:
        logging.info(f"MESSAGE_DELIVERY_ID: {delivery_id}")

    # Log selected top-level fields that are common routing criteria
    for key in ('action', 'ref', 'ref_type', 'sender', 'repository'):
        if key in upstream_body:
            value = upstream_body[key]
            if isinstance(value, dict):
                # For nested objects log the most useful sub-field
                value = value.get('full_name', value.get('login', value.get('name', json.dumps(value, ensure_ascii=False))))
            logging.info(f"MESSAGE_{key.upper()}: {value}")

    # ── 2) Structured block for Summarizer / Parametrizer ────────────
    # Extract human-readable values from nested objects for structured fields
    action = upstream_body.get('action', '')
    ref = upstream_body.get('ref', '')
    repo = upstream_body.get('repository', {})
    repo_name = repo.get('full_name', '') if isinstance(repo, dict) else str(repo)
    sender = upstream_body.get('sender', {})
    sender_login = sender.get('login', '') if isinstance(sender, dict) else str(sender)

    block = (
        f"event_type: {event_type}\n"
        f"delivery_id: {delivery_id}\n"
        f"action: {action}\n"
        f"ref: {ref}\n"
        f"repository: {repo_name}\n"
        f"sender: {sender_login}\n"
        f"body: {json.dumps(upstream_body, ensure_ascii=False)}"
    )

    logging.info(
        f"INI_RELAY_EVENT<<<\n{block}\n>>>END_RELAY_EVENT"
    )


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

_relay_config: Dict = {}
_relay_log_cfg: dict = {}
_relay_forward_count: int = 0
_forward_count_lock = threading.Lock()


class RelayHandler(BaseHTTPRequestHandler):
    """Handle inbound upstream webhook requests and relay to Gatewayer."""

    def log_message(self, format, *args):  # noqa: A002
        logging.info(f"HTTP {args[0] if args else ''}")

    def _send_json(self, status: int, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        global _relay_forward_count
        log_cfg = _relay_log_cfg
        config = _relay_config

        provider_mode = config.get("provider_mode", "github")

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        # --- GitHub provider ---
        if provider_mode == "github":
            self._handle_github(body_bytes, config, log_cfg)
        else:
            logging.error(f"{log_cfg.get('error_word', 'RELAY_ERROR')} unknown provider_mode={provider_mode}")
            self._send_json(400, {"status": "error", "reason": f"unknown provider_mode: {provider_mode}"})

    def _handle_github(self, body_bytes: bytes, config: dict, log_cfg: dict):
        global _relay_forward_count

        provider_secret = config.get("provider_secret", "")
        allowed_events = config.get("allowed_events", [])
        allowed_refs = config.get("allowed_refs", [])
        respond_ping = config.get("respond_ping_ok", True)

        # Validate upstream signature
        sig_header_value = self.headers.get("X-Hub-Signature-256", "")
        if provider_secret and not verify_github_signature(provider_secret, body_bytes, sig_header_value):
            logging.info(f"{log_cfg.get('rejected_word', 'RELAY_REJECTED')} signature_invalid")
            self._send_json(401, {"status": "rejected", "reason": "signature_invalid"})
            return

        # Read event metadata
        event_type = self.headers.get("X-GitHub-Event", "")
        delivery_id = self.headers.get("X-GitHub-Delivery", "")

        # Handle ping
        if event_type == "ping" and respond_ping:
            logging.info(f"{log_cfg.get('accepted_word', 'RELAY_ACCEPTED')} event=ping delivery={delivery_id}")
            self._send_json(200, {"status": "pong", "delivery": delivery_id})
            return

        # Filter event type
        if allowed_events and event_type not in allowed_events:
            logging.info(f"{log_cfg.get('rejected_word', 'RELAY_REJECTED')} event={event_type} not_allowed")
            self._send_json(202, {"status": "ignored", "reason": "event_not_allowed", "event": event_type})
            return

        # Parse body
        try:
            upstream_body = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            logging.info(f"{log_cfg.get('rejected_word', 'RELAY_REJECTED')} invalid_json")
            self._send_json(400, {"status": "rejected", "reason": "invalid_json"})
            return

        # Filter refs (for push events)
        if allowed_refs and event_type == "push":
            ref = upstream_body.get("ref", "")
            if ref not in allowed_refs:
                logging.info(f"{log_cfg.get('rejected_word', 'RELAY_REJECTED')} ref={ref} not_allowed")
                self._send_json(202, {"status": "ignored", "reason": "ref_not_allowed", "ref": ref})
                return

        logging.info(f"{log_cfg.get('accepted_word', 'RELAY_ACCEPTED')} event={event_type} delivery={delivery_id}")

        # Log upstream payload for downstream agents (Forker, Summarizer, Parametrizer)
        _log_relay_payload(event_type, delivery_id, upstream_body)

        # Transform payload
        payload = transform_payload(event_type, delivery_id, upstream_body)

        # Forward to Gatewayer
        result = forward_to_gatewayer(payload, config, delivery_id)

        fwd_status = result.get("status", "unknown")
        if fwd_status in ("accepted", "ok", "duplicate"):
            logging.info(f"{log_cfg.get('forwarded_word', 'RELAY_FORWARDED')} event={event_type} delivery={delivery_id} gw_status={fwd_status}")
            with _forward_count_lock:
                _relay_forward_count += 1
            self._send_json(200, {"status": "forwarded", "event": event_type, "delivery": delivery_id, "gateway_response": result})

            # Trigger downstream target_agents after successful forward
            target_agents = config.get("target_agents", [])
            if target_agents:
                wait_for_agents_to_stop(target_agents)
                logging.info(f"Triggering {len(target_agents)} downstream agents...")
                for target in target_agents:
                    start_agent(target)
        else:
            logging.error(f"{log_cfg.get('error_word', 'RELAY_ERROR')} forward_failed event={event_type} delivery={delivery_id} result={result}")
            self._send_json(502, {"status": "forward_failed", "event": event_type, "delivery": delivery_id, "gateway_response": result})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _relay_config, _relay_log_cfg

    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        _relay_config = config
        _relay_log_cfg = config.get("logging_behavior", {})

        target_agents = config.get("target_agents", [])
        host = config.get("listen_host", "127.0.0.1")
        port = int(config.get("listen_port", 9090))
        provider_mode = config.get("provider_mode", "github")

        logging.info("GATEWAY_RELAYER AGENT STARTED")
        logging.info(f"Provider mode: {provider_mode}")
        logging.info(f"Listening on {host}:{port}{config.get('listen_path', '/relay')}")
        logging.info(f"Forward URL: {config.get('forward_url', '')}")
        logging.info(f"Targets: {target_agents}")

        # Graceful shutdown handler
        def _signal_handler(signum, frame):
            logging.info("Shutdown signal received, stopping...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        server = HTTPServer((host, port), RelayHandler)

        if config.get("use_tls", False):
            cert_file = config.get("tls_cert", "")
            key_file = config.get("tls_key", "")
            if cert_file and key_file:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(cert_file, key_file)
                server.socket = ctx.wrap_socket(server.socket, server_side=True)
                logging.info("TLS enabled")

        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        graceful_sec = config.get("graceful_shutdown_sec", 5)
        shutdown_event.wait()
        logging.info("Shutting down relay server...")
        server.shutdown()
        server_thread.join(timeout=graceful_sec)

        logging.info("GatewayRelayer agent finished.")

    except Exception as e:
        logging.error(f"{_relay_log_cfg.get('error_word', 'RELAY_ERROR')} {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
