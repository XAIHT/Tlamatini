# Blenderer Agent — drives Blender via the OFFICIAL Blender MCP add-on's TCP
# socket protocol (localhost:9876 by default; https://www.blender.org/lab/mcp-server/).
# Self-contained — does NOT import from agent.acpx or any Tlamatini-internal
# package, because pool subprocesses run as separate Python interpreters with no
# path back into the Django app. The BlenderConnection mirrors the official
# ``blmcp`` socket client inline.
#
# IMPORTANT — the Blender MCP wire protocol is FUNDAMENTALLY a code-execution
# protocol, NOT a verb-dispatch protocol like Unreal's. Every request is:
#     {"type": "execute", "code": "<python>", "strict_json": <bool>}  + "\0"
# (null-byte framed). The add-on runs that Python inside Blender and returns:
#     {"status": "ok"|"error", "result": {...}, "message": "<err>",
#      "stdout": "...", "stderr": "..."}  (also null-byte framed).
# The executed code MUST assign a ``result`` dict. So this agent exposes a RICH
# ACTION CATALOG: ``execute_code`` forwards raw Python verbatim, while the baked
# verbs (scene_info / get_objects / get_object_detail / blendfile_summary /
# create_object / delete_object / set_material / screenshot / render) generate
# safe, ``result``-setting Python from their params — Tlamatini IS the client,
# so we skip blender.org's ``blmcp`` bridge and talk to the add-on directly.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# -- Temp directory policy (2026-06-02): keep any scratch under <app>/Temp -----
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    import tempfile as _tlt_tempfile
    _tlt_tempfile.tempdir = os.environ['TLAMATINI_TEMP'].strip()

import json
import socket
import time
import yaml
import logging
import subprocess
import datetime

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
    """Resolve the Python home used to spawn pool-agent subprocesses.

    FROZEN: ALWAYS prefer the Python interpreter CARRIED INSIDE Tlamatini's
    installation (``<install_dir>/python``) so pool agents NEVER depend on a
    system Python or a user-set ``PYTHON_HOME``. The carried interpreter is
    pinned to Python 3.12.10 (shipped by the installer). Only when the carried
    interpreter is somehow absent (e.g. running from source) does this fall
    back to the registry / environment ``PYTHON_HOME``.
    """
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
# OUTPUT-PATH DEFAULTING (Temp policy)
# ========================================

def _default_temp_output_dir() -> str:
    """Resolve the scratch directory for screenshots/renders the user didn't path.

    Honors ``TLAMATINI_TEMP`` (the parent exports it); falls back to the agent
    directory so a standalone run still writes somewhere sane. NEVER returns a
    system-temp / C:\\Temp / %TEMP% path (2026-06-02 directory policy).
    """
    temp_root = (os.environ.get('TLAMATINI_TEMP') or '').strip()
    if not temp_root:
        temp_root = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(temp_root, 'TlamatiniBlenderer')
    try:
        os.makedirs(out, exist_ok=True)
    except Exception:
        out = os.path.dirname(os.path.abspath(__file__))
    return out


_output_seq = 0


def _default_output_path(ext: str) -> str:
    # Full microseconds + a per-process counter make the name collision-proof
    # even for two defaults produced in the same run (e.g. screenshot + render).
    global _output_seq
    _output_seq += 1
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return os.path.join(_default_temp_output_dir(), f"blenderer_{stamp}_{_output_seq}.{ext}")


# ========================================
# ACTION CATALOG → Blender Python (the "rich verbs" over execute)
# ========================================
#
# Each baked verb returns a Python program (a string) that assigns a ``result``
# dict — the add-on requires it. ``execute_code`` forwards raw user Python
# verbatim. Params are injected as a JSON blob the generated code parses into
# ``_p`` so there is never a brace-format / quoting hazard with arbitrary
# string values.

# Commands handled as raw passthrough (the universal escape hatch).
_PASSTHROUGH_COMMANDS = frozenset({'execute_code', 'execute', 'execute_blender_code'})

# Baked read/inspection verbs (READ-ONLY — they only return ``result``).
_READ_COMMANDS = frozenset({
    'scene_info', 'get_objects', 'get_object_detail', 'blendfile_summary', 'ping',
})

# Baked mutating / output verbs.
_WRITE_COMMANDS = frozenset({
    'create_object', 'delete_object', 'set_material', 'screenshot', 'render',
})

KNOWN_COMMANDS = _PASSTHROUGH_COMMANDS | _READ_COMMANDS | _WRITE_COMMANDS

# Commands whose effective socket read-timeout is raised to a floor because the
# add-on runs a synchronous operation that a sub-second default cannot bound:
# a full render compiles + renders on Blender's main thread; execute_code is
# arbitrary; a screenshot needs a window redraw.
_SLOW_COMMAND_TIMEOUT_FLOORS = {
    'render': 600.0,
    'execute_code': 300.0,
    'execute': 300.0,
    'execute_blender_code': 300.0,
    'screenshot': 60.0,
}


def _bodies(command: str, params: dict) -> str:
    """Return the per-command Python body (uses the pre-declared ``_p`` dict)."""
    if command == 'ping':
        return (
            "import bpy\n"
            "result = {'ok': True, 'blender_version': list(bpy.app.version), "
            "'blender_version_string': bpy.app.version_string, 'scene': bpy.context.scene.name}\n"
        )
    if command == 'scene_info':
        return (
            "import bpy\n"
            "sc = bpy.context.scene\n"
            "av = bpy.context.view_layer.objects.active\n"
            "result = {'scene': sc.name, 'frame_current': sc.frame_current, "
            "'frame_start': sc.frame_start, 'frame_end': sc.frame_end, "
            "'render_engine': sc.render.engine, 'object_count': len(bpy.data.objects), "
            "'objects': [o.name for o in bpy.data.objects], "
            "'active_object': (av.name if av else None)}\n"
        )
    if command == 'get_objects':
        return (
            "import bpy\n"
            "def _o(o):\n"
            "    return {'name': o.name, 'type': o.type, 'location': list(o.location), "
            "'parent': (o.parent.name if o.parent else None), 'visible': o.visible_get(), "
            "'dimensions': list(o.dimensions)}\n"
            "result = {'scene': bpy.context.scene.name, "
            "'objects': [_o(o) for o in bpy.data.objects], "
            "'collections': [c.name for c in bpy.data.collections], "
            "'meshes': [m.name for m in bpy.data.meshes], "
            "'materials': [m.name for m in bpy.data.materials]}\n"
        )
    if command == 'get_object_detail':
        return (
            "import bpy\n"
            "name = _p.get('object_name') or _p.get('name') or ''\n"
            "o = bpy.data.objects.get(name)\n"
            "if o is None:\n"
            "    result = {'status': 'not_found', 'object': name, "
            "'available': [x.name for x in bpy.data.objects]}\n"
            "else:\n"
            "    result = {'name': o.name, 'type': o.type, 'location': list(o.location), "
            "'rotation_euler': list(o.rotation_euler), 'scale': list(o.scale), "
            "'dimensions': list(o.dimensions), "
            "'materials': ([m.name for m in o.data.materials] if getattr(o.data, 'materials', None) else []), "
            "'modifiers': [m.name for m in o.modifiers], "
            "'vertex_count': (len(o.data.vertices) if o.type == 'MESH' else None)}\n"
        )
    if command == 'blendfile_summary':
        return (
            "import bpy\n"
            "result = {'filepath': bpy.data.filepath, 'objects': len(bpy.data.objects), "
            "'meshes': len(bpy.data.meshes), 'materials': len(bpy.data.materials), "
            "'textures': len(bpy.data.textures), 'images': len(bpy.data.images), "
            "'cameras': len(bpy.data.cameras), 'lights': len(bpy.data.lights), "
            "'collections': len(bpy.data.collections), "
            "'scenes': [s.name for s in bpy.data.scenes]}\n"
        )
    if command == 'create_object':
        return (
            "import bpy\n"
            "prim = (_p.get('type') or 'cube').lower()\n"
            "loc = _p.get('location') or [0, 0, 0]\n"
            "ops = {'cube': bpy.ops.mesh.primitive_cube_add, "
            "'sphere': bpy.ops.mesh.primitive_uv_sphere_add, "
            "'cylinder': bpy.ops.mesh.primitive_cylinder_add, "
            "'cone': bpy.ops.mesh.primitive_cone_add, "
            "'plane': bpy.ops.mesh.primitive_plane_add, "
            "'monkey': bpy.ops.mesh.primitive_monkey_add, "
            "'torus': bpy.ops.mesh.primitive_torus_add}\n"
            "fn = ops.get(prim, bpy.ops.mesh.primitive_cube_add)\n"
            "fn(location=tuple(loc))\n"
            "obj = bpy.context.active_object\n"
            "nm = _p.get('name')\n"
            "if nm:\n"
            "    obj.name = nm\n"
            "result = {'created': obj.name, 'type': prim, 'location': list(obj.location)}\n"
        )
    if command == 'delete_object':
        return (
            "import bpy\n"
            "name = _p.get('object_name') or _p.get('name') or ''\n"
            "o = bpy.data.objects.get(name)\n"
            "if o is None:\n"
            "    result = {'status': 'not_found', 'object': name}\n"
            "else:\n"
            "    bpy.data.objects.remove(o, do_unlink=True)\n"
            "    result = {'deleted': name}\n"
        )
    if command == 'set_material':
        return (
            "import bpy\n"
            "oname = _p.get('object_name') or _p.get('name') or ''\n"
            "o = bpy.data.objects.get(oname)\n"
            "if o is None:\n"
            "    result = {'status': 'not_found', 'object': oname}\n"
            "else:\n"
            "    col = list(_p.get('color') or [0.8, 0.8, 0.8])\n"
            "    if len(col) == 3:\n"
            "        col = col + [1.0]\n"
            "    mname = _p.get('material') or _p.get('material_name') or (oname + '_mat')\n"
            "    mat = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)\n"
            "    mat.use_nodes = True\n"
            "    bsdf = mat.node_tree.nodes.get('Principled BSDF')\n"
            "    if bsdf is not None:\n"
            "        bsdf.inputs['Base Color'].default_value = tuple(col)\n"
            "    if o.data.materials:\n"
            "        o.data.materials[0] = mat\n"
            "    else:\n"
            "        o.data.materials.append(mat)\n"
            "    result = {'object': oname, 'material': mname, 'color': col}\n"
        )
    if command == 'screenshot':
        return (
            "import bpy, os\n"
            "path = _p.get('output_path') or ''\n"
            "bpy.ops.screen.screenshot(filepath=path)\n"
            "result = {'saved': path, 'exists': os.path.exists(path)}\n"
        )
    if command == 'render':
        return (
            "import bpy, os\n"
            "path = _p.get('output_path') or ''\n"
            "bpy.context.scene.render.filepath = path\n"
            "bpy.ops.render.render(write_still=True)\n"
            "result = {'rendered': bpy.context.scene.render.filepath, 'exists': os.path.exists(path)}\n"
        )
    return ""


def build_code(command: str, params: dict) -> tuple:
    """Resolve (code, params) for a command.

    Returns ``(code_string, effective_params)``. For passthrough commands the
    raw ``params['code']`` is returned verbatim. For baked verbs the params are
    injected as a JSON blob the generated code parses into ``_p``; output-path
    verbs get a Temp default when the caller omitted ``output_path``.
    """
    params = dict(params or {})
    if command in _PASSTHROUGH_COMMANDS:
        return str(params.get('code') or ''), params

    # Default an output path under <app>/Temp for the file-producing verbs.
    if command == 'screenshot' and not (params.get('output_path') or '').strip():
        params['output_path'] = _default_output_path('png')
    if command == 'render' and not (params.get('output_path') or '').strip():
        params['output_path'] = _default_output_path('png')

    body = _bodies(command, params)
    if not body:
        return "", params
    prelude = (
        "import json as _json\n"
        f"_p = _json.loads({json.dumps(json.dumps(params, default=str))})\n"
        "result = {}\n"
    )
    return prelude + body, params


# ========================================
# BLENDER CONNECTION (inline mirror of the official blmcp socket client)
# ========================================
#
# The Blender MCP add-on listens on localhost:9876 (configurable). Each turn
# opens a fresh socket, sends ``{"type":"execute","code":...,"strict_json":...}``
# followed by a single NUL byte, then reads the JSON response up to the next NUL
# byte. This is a verbatim port of the official ``send_code`` helper minus the
# MCP plumbing, so the agent talks to the add-on exactly like blender.org's own
# client does.

class BlenderConnection:
    def __init__(self, host: str = "localhost", port: int = 9876,
                 connect_timeout: float = 10.0, read_timeout: float = 120.0):
        self.host = host
        self.port = int(port)
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)

    def send(self, code: str, strict_json: bool) -> dict:
        request = json.dumps({
            "type": "execute",
            "code": code,
            "strict_json": bool(strict_json),
        }) + "\0"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.connect_timeout)
                logging.info(f"🔌 Connecting to Blender at {self.host}:{self.port}...")
                sock.connect((self.host, self.port))
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                logging.info("✅ Connected to Blender")
                sock.settimeout(self.read_timeout)
                sock.sendall(request.encode("utf-8"))

                buf = bytearray()
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if b"\0" in buf:
                        break
        except ConnectionRefusedError:
            return {
                "status": "error",
                "error": (
                    f"Cannot connect to Blender at {self.host}:{self.port}. Ensure Blender "
                    "is running with the MCP add-on enabled, 'Online access' turned on in "
                    "System Preferences, and the MCP server started in the add-on preferences."
                ),
            }
        except socket.timeout:
            return {
                "status": "error",
                "error": (
                    f"Blender did not reply within {self.read_timeout:g}s. It accepted the "
                    "code but the operation is still running (raise read_timeout) or its main "
                    "thread is parked on a modal dialog / blocking operator."
                ),
            }
        except OSError as ex:
            return {"status": "error",
                    "error": f"Socket error talking to Blender at {self.host}:{self.port}: {ex}"}

        if not buf:
            return {"status": "error", "error": "Empty response from Blender"}

        line, _sep, _rest = buf.partition(b"\0")
        try:
            response = json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as ex:
            return {"status": "error",
                    "error": f"Invalid response from Blender: {ex}"}
        logging.info(f"📨 Blender response status={response.get('status')}")
        # Normalize to a single shape: success → status ok; anything else → error.
        if response.get("status") == "error" and "error" not in response:
            response["error"] = response.get("message", "Unknown Blender error")
        return response


# ========================================
# MAIN
# ========================================

def _format_response_for_section(response: dict) -> str:
    try:
        text = json.dumps(response, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = repr(response)
    if len(text) > 64 * 1024:
        text = text[:64 * 1024] + "\n...[truncated]"
    return text


def emit_parametrizer_section(host, port, command, status, error_msg, body):
    """Emit the atomic INI_SECTION_BLENDERER block (one logging.info call)."""
    logging.info(
        "INI_SECTION_BLENDERER<<<\n"
        f"host: {host}\n"
        f"port: {port}\n"
        f"command: {command}\n"
        f"status: {status}\n"
        f"error: {error_msg}\n"
        f"\n"
        f"{body}\n"
        ">>>END_SECTION_BLENDERER"
    )


def _effective_read_timeout(command: str, configured_timeout: float) -> float:
    try:
        configured = float(configured_timeout)
    except (TypeError, ValueError):
        configured = 120.0
    return max(configured, _SLOW_COMMAND_TIMEOUT_FLOORS.get(command, 0.0))


def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        host = str(config.get('host', 'localhost'))
        port = int(config.get('port', 9876))
        command = str(config.get('command', '') or '').strip()
        params = config.get('params') or {}
        if not isinstance(params, dict):
            logging.warning(f"⚠️ params is not a dict ({type(params).__name__}); coercing to empty")
            params = {}
        strict_json = bool(config.get('strict_json', False))
        connect_timeout = float(config.get('connect_timeout', 10))
        read_timeout = float(config.get('read_timeout', 120))
        target_agents = config.get('target_agents', []) or []

        logging.info("🎨 BLENDERER AGENT STARTED")
        logging.info(f"🌐 Blender endpoint: {host}:{port}")
        logging.info(f"🛠️  Command: {command}")
        logging.info(f"🎯 Targets: {target_agents}")

        if not command:
            err_msg = "No 'command' configured in config.yaml"
            logging.error(f"❌ {err_msg}")
            emit_parametrizer_section(host, port, "", "error", err_msg, err_msg)
        elif command not in KNOWN_COMMANDS:
            err_msg = (
                f"Unknown command '{command}'. Known commands: "
                f"{', '.join(sorted(KNOWN_COMMANDS))}. Use 'execute_code' with "
                "params.code for anything not covered by a baked verb."
            )
            logging.error(f"❌ {err_msg}")
            emit_parametrizer_section(host, port, command, "error", err_msg, err_msg)
        else:
            code, eff_params = build_code(command, params)
            if not code.strip():
                err_msg = (
                    f"Command '{command}' produced no code to run "
                    "(execute_code requires a non-empty params.code)."
                )
                logging.error(f"❌ {err_msg}")
                emit_parametrizer_section(host, port, command, "error", err_msg, err_msg)
            else:
                effective_read_timeout = _effective_read_timeout(command, read_timeout)
                if effective_read_timeout > read_timeout:
                    logging.info(
                        f"   ↳ '{command}' is a known slow operation; raising read_timeout "
                        f"{read_timeout:g}s → {effective_read_timeout:g}s for this run."
                    )
                logging.info(f"📤 Sending {len(code)} chars of code (strict_json={strict_json})")
                conn = BlenderConnection(host=host, port=port,
                                         connect_timeout=connect_timeout,
                                         read_timeout=effective_read_timeout)
                response = conn.send(code, strict_json)
                status = "error" if response.get("status") == "error" else "ok"
                error_msg = response.get("error", "") if status == "error" else ""
                body = _format_response_for_section(response)
                emit_parametrizer_section(host, port, command, status, error_msg, body)
                if status == "error":
                    logging.warning(f"⚠️ Blender returned error: {error_msg}")
                else:
                    logging.info("✅ Blender command completed successfully")

        # Always trigger downstream agents (success OR error) so flows can route
        # on the section's status field via Parametrizer.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Blenderer agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
