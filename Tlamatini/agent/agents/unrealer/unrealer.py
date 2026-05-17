# Unrealer Agent — drives Unreal Engine via the Unreal MCP plugin's TCP
# socket protocol (127.0.0.1:55557 by default). Self-contained — does NOT
# import from agent.acpx or any Tlamatini-internal package, because pool
# subprocesses run as separate Python interpreters with no path back into
# the Django app. The UnrealConnection mirrors the upstream Unreal MCP
# implementation inline (~80 lines).

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
import socket
import time
import yaml
import logging
import subprocess

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
# HELPER FUNCTIONS (from shoter.py boilerplate)
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
    for _ in range(5):
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
# UNREAL CONNECTION (inline mirror of upstream UnrealConnection)
# ========================================
#
# The Unreal MCP plugin embedded in the UE5 editor accepts one JSON
# command per TCP connection on 127.0.0.1:55557 (configurable). Each
# turn opens a fresh socket, sends ``{"type":<command>,"params":{...}}``
# without a trailing newline, reads the JSON response, and closes the
# socket. This adapter is a verbatim port (minus the FastMCP plumbing)
# so the agent works the same way as any other Unreal MCP client.

class UnrealConnection:
    def __init__(self, host: str = "127.0.0.1", port: int = 55557,
                 connect_timeout: float = 5.0, read_timeout: float = 10.0):
        self.host = host
        self.port = int(port)
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)
        self.socket = None
        self.connected = False

    def connect(self) -> bool:
        try:
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            logging.info(f"🔌 Connecting to Unreal at {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.connect_timeout)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logging.info("✅ Connected to Unreal Engine")
            return True
        except Exception as e:
            logging.error(f"❌ Failed to connect to Unreal: {e}")
            self.connected = False
            return False

    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
        self.connected = False

    def receive_full_response(self, sock, buffer_size: int = 4096) -> bytes:
        chunks = []
        sock.settimeout(self.read_timeout)
        try:
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    if not chunks:
                        raise Exception("Connection closed before receiving data")
                    break
                chunks.append(chunk)
                data = b''.join(chunks)
                try:
                    json.loads(data.decode('utf-8'))
                    logging.info(f"📥 Received complete response ({len(data)} bytes)")
                    return data
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logging.warning(f"⚠️ Error processing response chunk: {e}")
                    continue
        except socket.timeout:
            logging.warning("⚠️ Socket timeout during receive")
            if chunks:
                data = b''.join(chunks)
                try:
                    json.loads(data.decode('utf-8'))
                    return data
                except Exception:
                    pass
            raise Exception("Timeout receiving Unreal response")

    def send_command(self, command: str, params: dict | None = None) -> dict:
        # The Unreal MCP plugin's TCP listener on Windows occasionally hands a
        # freshly-accepted socket back to its inner Recv loop in a transient
        # state where the very first ``recv`` returns 0 bytes (the kernel races
        # the SYN/ACK against the first read). The plugin interprets that as
        # "peer closed" and silently drops the connection; the agent's recv
        # then waits the full read_timeout for a response that will never
        # come. Retry the entire round-trip once with a brief back-off to mask
        # that race even on plugin builds that lack the matching server-side
        # fix. Two attempts is plenty — sustained connect failures still
        # surface to the caller.
        last_error = ""
        for attempt in range(1, 3):
            response = self._send_command_once(command, params, attempt=attempt)
            if response.get("status") != "error":
                return response
            err = (response.get("error") or "").lower()
            transient = (
                "timeout" in err
                or "connection closed" in err
                or "connection reset" in err
                or "broken pipe" in err
            )
            last_error = response.get("error", "")
            if attempt < 2 and transient:
                logging.warning(
                    f"⚠️ Transient socket failure on attempt {attempt} "
                    f"({last_error!r}); retrying once."
                )
                time.sleep(0.25)
                continue
            return response
        return {"status": "error", "error": last_error or "Unreal command failed"}

    def _send_command_once(self, command: str, params: dict | None, attempt: int) -> dict:
        # Always open a fresh socket per command (Unreal closes after each).
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            self.connected = False

        if not self.connect():
            return {"status": "error", "error": f"Failed to connect to Unreal at {self.host}:{self.port}"}

        try:
            command_obj = {"type": command, "params": params or {}}
            command_json = json.dumps(command_obj)
            prefix = "📤 Sending command" if attempt == 1 else f"🔁 Resending command (attempt {attempt})"
            logging.info(f"{prefix}: {command_json}")
            self.socket.sendall(command_json.encode('utf-8'))
            response_data = self.receive_full_response(self.socket)
            response = json.loads(response_data.decode('utf-8'))
            logging.info(f"📨 Response from Unreal: {response}")

            # Normalize Unity-style {"success": false, ...} into the
            # status=error shape so downstream code can rely on one shape.
            if response.get("status") == "error":
                if "error" not in response:
                    response["error"] = response.get("message", "Unknown Unreal error")
            elif response.get("success") is False:
                err = response.get("error") or response.get("message", "Unknown Unreal error")
                response = {"status": "error", "error": err}

            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            self.connected = False
            return response

        except Exception as e:
            logging.error(f"❌ Error sending command: {e}")
            self.connected = False
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            return {"status": "error", "error": str(e)}


# ========================================
# PARAM NORMALIZATION
# ========================================

# UE's virtual content root is "/Game/" (mapped to <Project>/Content/ on disk).
# Callers sometimes pass "/Content/..." — the disk-folder name — which the
# plugin's asset registry rejects with "does not map to a root" and renders
# the resulting asset unreachable to any subsequent UMG command. Normalize
# /Content/X → /Game/X (and bare X → /Game/X) before sending so the demo
# prompt works even on plugin builds that still have the legacy normalizer.
def _normalize_content_path(value: str) -> str:
    if not isinstance(value, str):
        return value
    text = value.strip().replace('\\', '/')
    if not text:
        return text
    while text.endswith('/') and len(text) > 1:
        text = text[:-1]
    if text.startswith('/Content/'):
        return '/Game/' + text[len('/Content/'):]
    if text == '/Content':
        return '/Game'
    return text


_PATH_PARAM_KEYS = ('path', 'package_root', 'content_path', 'asset_path')


def _normalize_params_for_unreal(params: dict) -> dict:
    """Apply defensive in-place fixups to a params dict before sending."""
    if not isinstance(params, dict):
        return params
    for key in _PATH_PARAM_KEYS:
        val = params.get(key)
        if isinstance(val, str) and val:
            normalized = _normalize_content_path(val)
            if normalized != val:
                logging.info(f"   ↳ Normalized params.{key}: {val!r} → {normalized!r}")
                params[key] = normalized
    return params


# ========================================
# MAIN
# ========================================

def _format_response_for_section(response: dict) -> str:
    """Pretty JSON of the Unreal response, capped to keep logs readable."""
    try:
        text = json.dumps(response, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = repr(response)
    # The parser stores everything after the first blank line under
    # ``response_body`` — no need to truncate, but keep it bounded.
    if len(text) > 64 * 1024:
        text = text[:64 * 1024] + "\n...[truncated]"
    return text


def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        host = str(config.get('host', '127.0.0.1'))
        port = int(config.get('port', 55557))
        command = str(config.get('command', '') or '').strip()
        params = config.get('params') or {}
        if not isinstance(params, dict):
            logging.warning(f"⚠️ params is not a dict ({type(params).__name__}); coercing to empty")
            params = {}
        connect_timeout = float(config.get('connect_timeout', 5))
        read_timeout = float(config.get('read_timeout', 10))
        target_agents = config.get('target_agents', []) or []

        logging.info("🎮 UNREALER AGENT STARTED")
        logging.info(f"🌐 Unreal endpoint: {host}:{port}")
        logging.info(f"🛠️  Command: {command}")
        logging.info(f"📦 Params: {params}")
        logging.info(f"🎯 Targets: {target_agents}")

        if not command:
            err_msg = "No 'command' configured in config.yaml"
            logging.error(f"❌ {err_msg}")
            # Still emit a section so Parametrizer + Exec Report see the failure
            logging.info(
                "INI_SECTION_UNREALER<<<\n"
                f"host: {host}\n"
                f"port: {port}\n"
                f"command: \n"
                f"status: error\n"
                f"\n"
                f"{err_msg}\n"
                ">>>END_SECTION_UNREALER"
            )
        else:
            params = _normalize_params_for_unreal(params)
            conn = UnrealConnection(host=host, port=port,
                                    connect_timeout=connect_timeout,
                                    read_timeout=read_timeout)
            response = conn.send_command(command, params)
            status = "error" if response.get("status") == "error" else "ok"
            error_msg = response.get("error", "") if status == "error" else ""
            body = _format_response_for_section(response)
            # Atomic single-call section emission (parametrizer parser
            # rule: each section must be one logging.info() call).
            logging.info(
                "INI_SECTION_UNREALER<<<\n"
                f"host: {host}\n"
                f"port: {port}\n"
                f"command: {command}\n"
                f"status: {status}\n"
                f"error: {error_msg}\n"
                f"\n"
                f"{body}\n"
                ">>>END_SECTION_UNREALER"
            )
            if status == "error":
                logging.warning(f"⚠️ Unreal returned error: {error_msg}")
            else:
                logging.info("✅ Unreal command completed successfully")

        # Always trigger downstream agents (success OR error) so flows
        # can route on the section's status field via Parametrizer.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Unrealer finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
