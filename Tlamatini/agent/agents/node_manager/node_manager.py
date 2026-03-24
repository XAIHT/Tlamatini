# NodeManager Agent - Infrastructure registry and node supervision agent
# Action: Long-running agent that maintains a live registry of local/remote nodes,
#         probes health, detects capability changes, persists state, exports manifests,
#         and triggers downstream target_agents on configured node events.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import copy
import json
import socket
import time
import yaml
import logging
import subprocess
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

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


# ========================================
# UTILITY FUNCTIONS (copied from shoter.py)
# ========================================

def load_config(path: str = "config.yaml") -> Dict:
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
    """
    Get the command to run a Python script.
    - In Dev: Use current sys.executable (handles venvs).
    - In Frozen (Windows): Check for bundled python.exe, else fallback to 'python'.
    - In Frozen (Unix): Fallback to 'python3'.
    """
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

    # Prefer PYTHON_HOME from USER environment variables
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
    """Read PYTHON_HOME exclusively from USER environment variables (Windows registry)."""
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
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()

    # Reset PyInstaller's DLL search path alteration on Windows
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes
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
    """Get the pool directory path where deployed agents reside."""
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
    """Check if an agent is currently running by verifying its PID file and process."""
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
    """
    Wait until ALL specified agents have stopped running.
    Logs ERROR every 10 seconds while waiting. Never proceeds until all have stopped.
    """
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


# ========================================
# PID MANAGEMENT
# ========================================

PID_FILE = "agent.pid"


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
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


# ========================================
# NODE STATE CONSTANTS
# ========================================

STATE_ONLINE = "ONLINE"
STATE_OFFLINE = "OFFLINE"
STATE_DEGRADED = "DEGRADED"
STATE_UNKNOWN = "UNKNOWN"

EVENT_NODE_ONLINE = "NODE_ONLINE"
EVENT_NODE_OFFLINE = "NODE_OFFLINE"
EVENT_NODE_DEGRADED = "NODE_DEGRADED"
EVENT_NODE_CAPABILITIES_CHANGED = "NODE_CAPABILITIES_CHANGED"

REANIM_FILE = "reanim_registry.json"


# ========================================
# PROBING FUNCTIONS
# ========================================

def probe_ping(host: str, timeout_sec: int = 5) -> bool:
    """Non-destructive ICMP ping probe."""
    try:
        param = '-n' if sys.platform.startswith('win') else '-c'
        timeout_flag = '-w' if sys.platform.startswith('win') else '-W'
        timeout_val = str(timeout_sec * 1000) if sys.platform.startswith('win') else str(timeout_sec)
        cmd = ['ping', param, '1', timeout_flag, timeout_val, host]
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout_sec + 5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        return result.returncode == 0
    except Exception:
        return False


def probe_tcp(host: str, port: int, timeout_sec: int = 3, collect_banner: bool = False) -> dict:
    """TCP connectivity probe. Returns {reachable: bool, banner: str|None}."""
    result = {"reachable": False, "banner": None}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        sock.connect((host, port))
        result["reachable"] = True
        if collect_banner:
            try:
                sock.settimeout(2)
                banner = sock.recv(1024)
                result["banner"] = banner.decode('utf-8', errors='replace').strip()
            except Exception:
                pass
        sock.close()
    except Exception:
        pass
    return result


def probe_ssh(host: str, port: int = 22, timeout_sec: int = 3) -> bool:
    """SSH reachability check via TCP connect to SSH port."""
    return probe_tcp(host, port, timeout_sec)["reachable"]


def probe_winrm(host: str, timeout_sec: int = 3) -> bool:
    """WinRM reachability check via TCP connect to ports 5985/5986."""
    for port in [5985, 5986]:
        if probe_tcp(host, port, timeout_sec)["reachable"]:
            return True
    return False


def probe_http(host: str, paths: list, timeout_sec: int = 5) -> dict:
    """HTTP probe — attempt GET on each path. Returns {reachable: bool, status_codes: dict}."""
    import urllib.request
    import urllib.error
    result = {"reachable": False, "status_codes": {}}
    for path in paths:
        url = f"http://{host}{path}"
        try:
            req = urllib.request.Request(url, method='GET')
            resp = urllib.request.urlopen(req, timeout=timeout_sec)
            result["status_codes"][path] = resp.status
            result["reachable"] = True
        except urllib.error.HTTPError as e:
            result["status_codes"][path] = e.code
            result["reachable"] = True
        except Exception:
            result["status_codes"][path] = 0
    return result


# ========================================
# CAPABILITY DETECTION
# ========================================

def detect_capabilities(node: dict, config: dict) -> dict:
    """
    Detect capabilities for a node. For V1, only local detection is supported.
    Remote command probes are gated behind security.allow_command_probes.
    Returns a dict of capability -> value.
    """
    caps = {}
    cap_cfg = config.get('capabilities', {})
    host = node.get('host', '')

    is_local = host in ('localhost', '127.0.0.1', '::1', socket.gethostname())

    if is_local:
        if cap_cfg.get('detect_os', True):
            caps['os'] = sys.platform
            if sys.platform.startswith('win'):
                caps['os_family'] = 'windows'
            else:
                caps['os_family'] = 'linux'

        if cap_cfg.get('detect_python', True):
            caps['python'] = sys.version.split()[0]

        if cap_cfg.get('detect_git', True):
            try:
                r = subprocess.run(
                    ['git', '--version'], capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                caps['git'] = r.stdout.decode().strip() if r.returncode == 0 else None
            except Exception:
                caps['git'] = None

        if cap_cfg.get('detect_docker', True):
            try:
                r = subprocess.run(
                    ['docker', '--version'], capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                caps['docker'] = r.stdout.decode().strip() if r.returncode == 0 else None
            except Exception:
                caps['docker'] = None

        if cap_cfg.get('detect_kubectl', False):
            try:
                r = subprocess.run(
                    ['kubectl', 'version', '--client', '--short'], capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                caps['kubectl'] = r.stdout.decode().strip() if r.returncode == 0 else None
            except Exception:
                caps['kubectl'] = None

        if cap_cfg.get('detect_gpu', False):
            try:
                r = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                    capture_output=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                if r.returncode == 0:
                    gpus = [g.strip() for g in r.stdout.decode().strip().split('\n') if g.strip()]
                    caps['gpu'] = gpus
                else:
                    caps['gpu'] = None
            except Exception:
                caps['gpu'] = None
    else:
        # Remote capability detection requires command probes
        caps['os'] = 'unknown'
        caps['os_family'] = 'unknown'

    return caps


# ========================================
# NODE REGISTRY
# ========================================

class NodeRegistry:
    """Maintains the live registry of nodes, their state, and capabilities."""

    def __init__(self, config: dict):
        self.config = config
        self.nodes: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._pending_events: List[dict] = []

        storage = config.get('storage', {})
        self.registry_dir = storage.get('registry_dir', 'node_registry')
        self.snapshot_file = storage.get('snapshot_file', 'nodes_snapshot.json')
        self.selected_nodes_file = storage.get('selected_nodes_file', 'selected_nodes.json')
        self.events_file = storage.get('events_file', 'node_events.jsonl')
        self.write_per_node = storage.get('write_per_node_files', True)
        self.keep_days = storage.get('keep_days', 14)

        os.makedirs(self.registry_dir, exist_ok=True)

    def load_reanim(self):
        """Load persisted registry state from reanim file."""
        if os.path.exists(REANIM_FILE):
            try:
                with open(REANIM_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.nodes = data.get('nodes', {})
                logging.info(f"♻️ Restored {len(self.nodes)} nodes from {REANIM_FILE}")
            except Exception as e:
                logging.warning(f"⚠️ Failed to load {REANIM_FILE}: {e}")

    def save_reanim(self):
        """Persist registry state for restart recovery."""
        try:
            with open(REANIM_FILE, 'w', encoding='utf-8') as f:
                json.dump({'nodes': self.nodes, 'saved_at': _now_iso()}, f, indent=2)
        except Exception as e:
            logging.error(f"❌ Failed to save {REANIM_FILE}: {e}")

    def load_inventory(self):
        """Load nodes from config inline_nodes and optional nodes_file."""
        inv = self.config.get('inventory', {})
        nodes_file = inv.get('nodes_file', '')
        merge = inv.get('merge_with_inline_nodes', True)
        inline = inv.get('inline_nodes', [])
        default_transport = inv.get('default_transport', 'ssh')

        file_nodes = []
        if nodes_file and os.path.exists(nodes_file):
            try:
                with open(nodes_file, 'r', encoding='utf-8') as f:
                    if nodes_file.endswith('.json'):
                        file_nodes = json.load(f)
                    else:
                        file_nodes = yaml.safe_load(f) or []
                logging.info(f"📂 Loaded {len(file_nodes)} nodes from {nodes_file}")
            except Exception as e:
                logging.error(f"❌ Failed to load nodes file {nodes_file}: {e}")

        all_nodes = []
        if merge:
            all_nodes = file_nodes + inline
        elif file_nodes:
            all_nodes = file_nodes
        else:
            all_nodes = inline

        with self._lock:
            for node_def in all_nodes:
                node_id = node_def.get('id') or node_def.get('host', '')
                if not node_id:
                    continue
                if node_id not in self.nodes:
                    self.nodes[node_id] = {
                        'id': node_id,
                        'host': node_def.get('host', node_id),
                        'port': node_def.get('port'),
                        'transport': node_def.get('transport', default_transport),
                        'tags': node_def.get('tags', []),
                        'roles': node_def.get('roles', []),
                        'state': STATE_UNKNOWN,
                        'prev_state': None,
                        'consecutive_failures': 0,
                        'last_seen': None,
                        'last_probe': None,
                        'capabilities': {},
                        'capabilities_updated_at': None,
                        'banners': {},
                    }
                else:
                    # Merge tags/roles from inventory
                    existing = self.nodes[node_id]
                    for tag in node_def.get('tags', []):
                        if tag not in existing.get('tags', []):
                            existing.setdefault('tags', []).append(tag)
                    for role in node_def.get('roles', []):
                        if role not in existing.get('roles', []):
                            existing.setdefault('roles', []).append(role)

        logging.info(f"📋 Registry contains {len(self.nodes)} total nodes")

    def probe_node(self, node_id: str) -> Optional[str]:
        """
        Run configured probes against a single node. Returns new state.
        Appends events to pending list on state transitions.
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return None
            node_copy = copy.deepcopy(node)

        host = node_copy['host']
        probes_cfg = self.config.get('probes', {})
        heartbeat_cfg = self.config.get('heartbeat', {})
        timeout = heartbeat_cfg.get('timeout_sec', 5)
        offline_threshold = heartbeat_cfg.get('offline_after_failures', 3)

        passed = []
        failed = []

        # Ping probe
        if probes_cfg.get('ping_enabled', True):
            if probe_ping(host, timeout):
                passed.append('ping')
            else:
                failed.append('ping')

        # TCP connectivity probe
        if probes_cfg.get('tcp_connect_enabled', True):
            port = node_copy.get('port')
            transport = node_copy.get('transport', 'ssh')
            if not port:
                port = 22 if transport == 'ssh' else 5985
            tcp_result = probe_tcp(host, port, timeout, probes_cfg.get('collect_banners', True))
            if tcp_result['reachable']:
                passed.append('tcp')
                if tcp_result.get('banner'):
                    node_copy['banners'][str(port)] = tcp_result['banner']
            else:
                failed.append('tcp')

        # SSH probe
        if probes_cfg.get('ssh_probe_enabled', True):
            if probe_ssh(host, timeout_sec=timeout):
                passed.append('ssh')
            else:
                failed.append('ssh')

        # WinRM probe
        if probes_cfg.get('winrm_probe_enabled', True):
            if probe_winrm(host, timeout):
                passed.append('winrm')
            else:
                failed.append('winrm')

        # HTTP probe
        if probes_cfg.get('http_probe_enabled', False):
            http_paths = probes_cfg.get('http_paths', ['/'])
            http_result = probe_http(host, http_paths, timeout)
            if http_result['reachable']:
                passed.append('http')
            else:
                failed.append('http')

        # Determine new state
        now_iso = _now_iso()
        if not passed and failed:
            node_copy['consecutive_failures'] = node_copy.get('consecutive_failures', 0) + 1
            if node_copy['consecutive_failures'] >= offline_threshold:
                new_state = STATE_OFFLINE
            else:
                new_state = STATE_DEGRADED
        elif passed and failed:
            node_copy['consecutive_failures'] = 0
            new_state = STATE_DEGRADED
        elif passed:
            node_copy['consecutive_failures'] = 0
            node_copy['last_seen'] = now_iso
            new_state = STATE_ONLINE
        else:
            new_state = STATE_UNKNOWN

        old_state = node_copy.get('state', STATE_UNKNOWN)
        node_copy['prev_state'] = old_state
        node_copy['state'] = new_state
        node_copy['last_probe'] = now_iso

        # Detect state transition
        events = []
        if old_state != new_state:
            event_type = {
                STATE_ONLINE: EVENT_NODE_ONLINE,
                STATE_OFFLINE: EVENT_NODE_OFFLINE,
                STATE_DEGRADED: EVENT_NODE_DEGRADED,
            }.get(new_state, f"NODE_{new_state}")
            events.append({
                'timestamp': now_iso,
                'node_id': node_id,
                'event': event_type,
                'old_state': old_state,
                'new_state': new_state,
                'probes_passed': passed,
                'probes_failed': failed,
            })
            logging.info(f"🔄 Node '{node_id}' state: {old_state} → {new_state}")

        # Capability detection
        cap_cfg = self.config.get('capabilities', {})
        cache_ttl = cap_cfg.get('cache_ttl_sec', 300)
        last_cap_update = node_copy.get('capabilities_updated_at')
        should_check_caps = False
        if not last_cap_update:
            should_check_caps = True
        else:
            try:
                last_dt = datetime.fromisoformat(last_cap_update.replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if age >= cache_ttl:
                    should_check_caps = True
            except Exception:
                should_check_caps = True

        if should_check_caps and new_state in (STATE_ONLINE, STATE_DEGRADED):
            old_caps = copy.deepcopy(node_copy.get('capabilities', {}))
            new_caps = detect_capabilities(node_copy, self.config)
            node_copy['capabilities'] = new_caps
            node_copy['capabilities_updated_at'] = now_iso
            if old_caps and old_caps != new_caps:
                events.append({
                    'timestamp': now_iso,
                    'node_id': node_id,
                    'event': EVENT_NODE_CAPABILITIES_CHANGED,
                    'old_capabilities': old_caps,
                    'new_capabilities': new_caps,
                })
                logging.info(f"🔧 Node '{node_id}' capabilities changed")

        # Update registry
        with self._lock:
            self.nodes[node_id] = node_copy
            self._pending_events.extend(events)

        return new_state

    def flush_events(self) -> List[dict]:
        """Return and clear pending events."""
        with self._lock:
            events = self._pending_events[:]
            self._pending_events.clear()
        return events

    def write_events_log(self, events: List[dict]):
        """Append events to the JSONL events log."""
        if not events:
            return
        events_path = os.path.join(self.registry_dir, self.events_file)
        try:
            with open(events_path, 'a', encoding='utf-8') as f:
                for ev in events:
                    f.write(json.dumps(ev, default=str) + '\n')
        except Exception as e:
            logging.error(f"❌ Failed to write events log: {e}")

    def export_snapshot(self):
        """Export full registry snapshot as JSON."""
        snapshot_path = os.path.join(self.registry_dir, self.snapshot_file)
        try:
            with self._lock:
                data = {
                    'exported_at': _now_iso(),
                    'node_count': len(self.nodes),
                    'nodes': copy.deepcopy(self.nodes)
                }
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"❌ Failed to export snapshot: {e}")

    def export_selected_nodes(self):
        """Export filtered selected-node manifest based on selection criteria."""
        sel = self.config.get('selection', {})
        if not sel.get('export_selected_nodes', True):
            return

        require_online = sel.get('require_online', True)
        include_tags = set(sel.get('include_tags', []))
        exclude_tags = set(sel.get('exclude_tags', []))
        include_roles = set(sel.get('include_roles', []))
        os_types = set(sel.get('os_types', []))
        transports = set(sel.get('transports', []))

        selected = []
        with self._lock:
            for node_id, node in self.nodes.items():
                if require_online and node.get('state') != STATE_ONLINE:
                    continue
                node_tags = set(node.get('tags', []))
                if include_tags and not include_tags.intersection(node_tags):
                    continue
                if exclude_tags and exclude_tags.intersection(node_tags):
                    continue
                node_roles = set(node.get('roles', []))
                if include_roles and not include_roles.intersection(node_roles):
                    continue
                if os_types:
                    node_os = node.get('capabilities', {}).get('os_family', '')
                    if node_os not in os_types:
                        continue
                if transports and node.get('transport', '') not in transports:
                    continue
                selected.append(copy.deepcopy(node))

        sel_path = os.path.join(self.registry_dir, self.selected_nodes_file)
        try:
            with open(sel_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'exported_at': _now_iso(),
                    'selected_count': len(selected),
                    'nodes': selected,
                }, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"❌ Failed to export selected nodes: {e}")

    def export_per_node_files(self):
        """Write individual per-node manifest files."""
        if not self.write_per_node:
            return
        per_node_dir = os.path.join(self.registry_dir, 'nodes')
        os.makedirs(per_node_dir, exist_ok=True)
        with self._lock:
            for node_id, node in self.nodes.items():
                safe_id = node_id.replace('/', '_').replace('\\', '_').replace(':', '_')
                node_path = os.path.join(per_node_dir, f"{safe_id}.json")
                try:
                    with open(node_path, 'w', encoding='utf-8') as f:
                        json.dump(node, f, indent=2, default=str)
                except Exception as e:
                    logging.error(f"❌ Failed to write per-node file for {node_id}: {e}")

    def cleanup_old_events(self):
        """Remove events older than keep_days from the events log."""
        events_path = os.path.join(self.registry_dir, self.events_file)
        if not os.path.exists(events_path):
            return
        cutoff = datetime.now(timezone.utc).timestamp() - (self.keep_days * 86400)
        try:
            kept = []
            with open(events_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        ts = ev.get('timestamp', '')
                        ev_time = datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                        if ev_time >= cutoff:
                            kept.append(line)
                    except Exception:
                        kept.append(line)
            with open(events_path, 'w', encoding='utf-8') as f:
                for line in kept:
                    f.write(line + '\n')
        except Exception as e:
            logging.error(f"❌ Failed to clean up old events: {e}")

    def get_node_ids(self) -> list:
        with self._lock:
            return list(self.nodes.keys())


# ========================================
# HELPERS
# ========================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def should_trigger(event_type: str, config: dict) -> bool:
    """Check if an event type should trigger downstream agents."""
    triggers = config.get('triggers', {})
    if not triggers.get('enabled', True):
        return False
    allowed = triggers.get('trigger_events', [])
    return event_type in allowed


# ========================================
# MAIN
# ========================================

def main():
    config = load_config()
    write_pid_file()

    try:
        target_agents = config.get('target_agents', [])
        heartbeat_cfg = config.get('heartbeat', {})
        poll_interval = heartbeat_cfg.get('poll_interval', 30)
        debounce_sec = heartbeat_cfg.get('debounce_sec', 20)
        max_parallel = heartbeat_cfg.get('max_parallel_probes', 10)
        runtime_cfg = config.get('runtime', {})
        idle_sleep_ms = runtime_cfg.get('idle_sleep_ms', 250)
        logging.info("🖧 NODE MANAGER AGENT STARTED")
        logging.info(f"🔗 Target agents: {target_agents}")
        logging.info(f"⏱️ Poll interval: {poll_interval}s | Debounce: {debounce_sec}s")

        # Initialize registry
        registry = NodeRegistry(config)
        registry.load_reanim()
        registry.load_inventory()

        # Discovery (V1 - disabled by default)
        disc = config.get('discovery', {})
        if disc.get('enabled', False):
            logging.info("🔍 Discovery is enabled but V1 only supports static inventory.")
            # Future: implement hostname/CIDR scanning here

        logging.info(f"📡 Monitoring {len(registry.get_node_ids())} nodes...")

        # Main polling loop
        last_cleanup = time.time()
        shutdown_requested = False

        while not shutdown_requested:
            cycle_start = time.time()

            # Probe all nodes (with parallelism via threads)
            node_ids = registry.get_node_ids()
            if node_ids:
                if max_parallel > 1 and len(node_ids) > 1:
                    batch_size = min(max_parallel, len(node_ids))
                    threads = []
                    for node_id in node_ids:
                        t = threading.Thread(target=registry.probe_node, args=(node_id,), daemon=True)
                        threads.append(t)
                        t.start()
                        if len(threads) >= batch_size:
                            for tt in threads:
                                tt.join(timeout=30)
                            threads.clear()
                    for tt in threads:
                        tt.join(timeout=30)
                else:
                    for node_id in node_ids:
                        registry.probe_node(node_id)

            # Flush and process events
            events = registry.flush_events()
            if events:
                registry.write_events_log(events)
                for ev in events:
                    logging.info(f"📝 Event: {ev.get('event')} for node {ev.get('node_id')}")

                # Trigger downstream agents on configured events
                trigger_needed = False
                for ev in events:
                    if should_trigger(ev.get('event', ''), config):
                        trigger_needed = True
                        break

                if trigger_needed and target_agents:
                    logging.info(f"🚀 Triggering {len(target_agents)} downstream agents due to node events...")
                    wait_for_agents_to_stop(target_agents)
                    for target in target_agents:
                        start_agent(target)

            # Export artifacts
            registry.export_snapshot()
            registry.export_selected_nodes()
            registry.export_per_node_files()

            # Persist reanim state
            registry.save_reanim()

            # Periodic cleanup (once per hour)
            if time.time() - last_cleanup > 3600:
                registry.cleanup_old_events()
                last_cleanup = time.time()

            # Sleep until next poll
            elapsed = time.time() - cycle_start
            sleep_time = max(poll_interval - elapsed, idle_sleep_ms / 1000.0)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logging.info("⛔ Shutdown requested via keyboard interrupt.")
    except Exception as e:
        logging.error(f"❌ NodeManager fatal error: {e}")
    finally:
        logging.info("🏁 NodeManager agent shutting down.")
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
