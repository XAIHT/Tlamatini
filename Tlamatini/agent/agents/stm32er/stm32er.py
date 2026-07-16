# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# STM32er Agent - STM32 Template Project MCP-server bridge (firmware scaffold/build/flash/observe)
# Action: Triggered by upstream -> spawn the STM32 MCP stdio server -> MCP
#         initialize handshake -> call ONE tool (selected by `action`) via
#         JSON-RPC tools/call -> capture the result -> emit INI_SECTION_STM32ER
#         -> ALWAYS trigger downstream (success OR failure).
#
# STM32er is Tlamatini's integration of the STM32 Template Project MCP
# (https://github.com/XAIHT/STM32TemplateProjectMCP). The upstream project ships
# a FastMCP **stdio** server (mcp/stm32_mcp_server.py) exposing 23 tools that
# scaffold -> author -> build -> flash -> observe STM32F4 firmware using the
# toolchain bundled inside STM32CubeIDE (no IDE GUI). STM32er drives that server
# directly over the MCP stdio protocol (newline-delimited JSON-RPC) using ONLY
# the Python standard library (subprocess + json + threading) — exactly like the
# Kalier / ACPXer agents — so it works identically in source and frozen builds
# and never imports from agent.* or the `mcp` package itself (only the SERVER
# needs `mcp`; STM32er is a raw protocol client). The agent pool runs as
# standalone Python subprocesses with no path back into the Django app, so this
# file is fully self-contained.
#
# The MCP server keeps serial connections (serial_*) and live-memory streaming
# sessions (live_memory_*) in-process, so they only survive while the server
# process is alive. STM32er spawns ONE server per run, so the two composite
# actions `serial_session` and `live_monitor` chain those stateful tools within
# the single server lifetime to make them usable end-to-end in one run.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core and inherited by every
# spawned agent via get_agent_env's os.environ.copy()) so every temp file this
# agent writes — including the downloaded MCP zip and its extraction dir — lands
# under <app>/Temp, never C:\Temp / %TEMP% / the OS default. Fail-open: when the
# handle is unset (agent launched fully standalone) Python's default is used.
if (os.environ.get('TLAMATINI_TEMP') or '').strip():
    try:
        import tempfile as _tlt_tempfile
        _tlt_temp_root = os.environ['TLAMATINI_TEMP'].strip()
        os.makedirs(_tlt_temp_root, exist_ok=True)
        _tlt_tempfile.tempdir = _tlt_temp_root
        os.environ['TEMP'] = _tlt_temp_root
        os.environ['TMP'] = _tlt_temp_root
    except Exception:
        pass

import re
import json
import time
import yaml
import queue
import logging
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
# HELPER FUNCTIONS (from kalier.py / shoter.py boilerplate — copy verbatim)
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


# PID Management
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
# CONFIG VALUE COERCION (wrapped Multi-Turn passes everything as strings)
# ========================================

def _cfg(config: dict, key: str, default=""):
    """Fetch a config value, coercing None to the default (yaml empties parse as None)."""
    val = config.get(key, default)
    return default if val is None else val


# NOTE: the parameters below are intentionally named ``raw`` (not ``value``).
# The wrapped-runtime's static "required config key" analyzer (tools.py
# _ConfigRequirementAnalyzer) treats any ``if <name> is None`` / ``if not <name>``
# as evidence that the config key ``<name>`` is mandatory. A parameter named
# ``value`` here would collide with this agent's ``value`` config field (used only
# by write_memory) and falsely block EVERY non-write_memory call. Keep these
# generic names clear of any config-key name.
def _as_int(raw, default: int) -> int:
    try:
        if isinstance(raw, bool):
            return default
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _as_float(raw, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _as_bool(raw, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off", ""):
        return False
    return default


# ========================================
# STM32 MCP TOOL CONTRACT
# (argument shapes mirror mcp/stm32_mcp_server.py tool signatures verbatim)
# ========================================

# Direct 1:1 actions -> MCP tool names (all 23 server tools).
_DIRECT_TOOLS = {
    "get_config", "discover_toolchain_tool",
    "create_project", "write_source", "read_source", "list_sources", "clean",
    "build", "list_artifacts", "flash", "build_and_flash", "erase", "reset",
    "serial_list_ports", "serial_connect", "serial_send", "serial_read", "serial_disconnect",
    "read_memory", "write_memory",
    "live_memory_start", "live_memory_read", "live_memory_stop",
}

# Composite actions that chain stateful tools within one server lifetime.
_COMPOSITE_ACTIONS = {"serial_session", "live_monitor"}

# Meta actions handled by STM32er ITSELF before (or instead of) any MCP tool
# call. ``bootstrap`` downloads + installs + validates the STM32 MCP server so
# the user only needs STM32CubeIDE + Tlamatini and nothing else; ``validate`` runs
# the full environment preflight (compiler / CubeIDE / build tools / programmer /
# ST-LINK driver + probe / device family) and reports without building or flashing.
_META_ACTIONS = {"bootstrap", "validate"}

_ALL_ACTIONS = _DIRECT_TOOLS | _COMPOSITE_ACTIONS | _META_ACTIONS

# ── Action classification for the SAFETY PREFLIGHT (critical-mission gating) ──
# Hardware actions touch a physical board: they REQUIRE a connected ST-LINK probe
# (and its USB driver). Compile-only actions deliberately do NOT — a user who only
# wants to BUILD firmware never needs a board attached.
_HARDWARE_ACTIONS = {
    "flash", "build_and_flash", "erase", "reset",
    "serial_connect", "serial_send", "serial_read", "serial_disconnect", "serial_session",
    "read_memory", "write_memory",
    "live_memory_start", "live_memory_read", "live_memory_stop", "live_monitor",
}
# Build actions compile + link firmware: they REQUIRE the arm-none-eabi-gcc
# toolchain, a build tool (make/cmake), and a SUPPORTED target device — but no
# hardware. ``build_and_flash`` is in BOTH sets (it builds AND flashes).
_BUILD_ACTIONS = {"build", "build_and_flash", "clean", "list_artifacts"}

# ── ST 32-bit MCU family map (Phase 0 — Blue Pill → STM32N6) ─────────────────
# The FULL family prefix list, ordered MOST-SPECIFIC FIRST so 'STM32WBA' matches
# before 'STM32WB'. `_device_family` maps a part (e.g. 'STM32F407VG') to its family
# ('STM32F4'). This de-welds the old STM32F-only gate: STM32er now RECOGNISES every
# ST family, and the backend dispatcher ROUTES each to a backend that can build it
# (the template MCP is F407-only; the PlatformIO backend covers the mainstream line;
# the newest silicon awaits the ST-native CubeCLT backend — Phase 2/3).
_STM32_FAMILY_PREFIXES = (
    "STM32C0",
    "STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", "STM32F7",
    "STM32G0", "STM32G4",
    "STM32H5", "STM32H7",
    "STM32L0", "STM32L1", "STM32L4", "STM32L5",
    "STM32U0", "STM32U5",
    "STM32WBA", "STM32WB", "STM32WL",
    "STM32N6",
)

# Legacy alias kept for back-compat with the template-MCP preflight (which is
# genuinely F407-only) and any existing references / tests.
_STM32F_FAMILIES = ("STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", "STM32F7")

# Families the PlatformIO `ststm32` backend builds today (Phase 1) — the mainstream
# ST line, incl. the Blue Pill (F1) and the current F407.
_PIO_SUPPORTED_FAMILIES = frozenset({
    "STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", "STM32F7",
    "STM32G0", "STM32G4", "STM32H7",
    "STM32L0", "STM32L1", "STM32L4", "STM32WB",
})
# Families PlatformIO ststm32 supports only PARTIALLY — attempt, but WARN so a build
# failure is understood (the ST-native CubeCLT backend, Phase 2/3, is the sure path).
_PIO_CAVEAT_FAMILIES = frozenset({"STM32L5", "STM32U5", "STM32WL"})
# Families NOT in the maintained ststm32 platform yet — the pio backend REFUSES them
# cleanly (fail-safe) and points at the future ST-native CubeCLT backend (Phase 2/3),
# rather than mis-building. STM32N6 additionally needs external-flash boot + signing.
_PIO_UNSUPPORTED_FAMILIES = frozenset({
    "STM32C0", "STM32H5", "STM32U0", "STM32WBA", "STM32N6",
})

# STMicroelectronics ST-LINK USB Vendor ID — how STM32 boards enumerate their debug
# probe / VCP (Nucleo & Discovery expose an ST-LINK VCP with this VID).
_STLINK_USB_VID = "0483"


def _build_arguments(action: str, config: dict) -> dict:
    """Build the JSON `arguments` object for a single direct tool call, including
    ONLY the keys that tool declares so FastMCP's schema validation accepts it and
    the server applies its own defaults for everything omitted."""
    if action == "get_config":
        return {}

    if action == "discover_toolchain_tool":
        args = {}
        if _cfg(config, "discover_ide_root"):
            args["ide_root"] = str(_cfg(config, "discover_ide_root"))
        return args

    if action == "create_project":
        _dest_parent = str(_cfg(config, "dest_parent")).strip()
        if not _dest_parent:
            # Tlamatini policy: default the scaffold parent to <app>/Templates
            # (exported as TLAMATINI_TEMPLATES by the core) unless dest_parent was
            # set explicitly. Gated on the env var so a fully-standalone run with
            # neither keeps the MCP server's own default (and unit tests that pass
            # no env var see unchanged behavior).
            _dest_parent = (os.environ.get("TLAMATINI_TEMPLATES") or "").strip()
        return {
            "name": str(_cfg(config, "name")),
            "dest_parent": _dest_parent,
            "overwrite": _as_bool(_cfg(config, "overwrite", False), False),
        }

    if action == "write_source":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "rel_path": str(_cfg(config, "rel_path")),
            "content": str(_cfg(config, "content")),
        }

    if action == "read_source":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "rel_path": str(_cfg(config, "rel_path")),
        }

    if action == "list_sources":
        return {"project_dir": str(_cfg(config, "project_dir"))}

    if action == "clean":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "system": str(_cfg(config, "system", "make") or "make"),
        }

    if action == "build":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "system": str(_cfg(config, "system", "make") or "make"),
            "jobs": _as_int(_cfg(config, "jobs", 8), 8),
            "clean_first": _as_bool(_cfg(config, "clean_first", False), False),
        }

    if action == "list_artifacts":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "system": str(_cfg(config, "system", "make") or "make"),
        }

    if action == "flash":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "system": str(_cfg(config, "system", "make") or "make"),
            "binary": str(_cfg(config, "binary", "bin") or "bin"),
        }

    if action == "build_and_flash":
        return {
            "project_dir": str(_cfg(config, "project_dir")),
            "system": str(_cfg(config, "system", "make") or "make"),
            "jobs": _as_int(_cfg(config, "jobs", 8), 8),
        }

    if action in ("erase", "reset"):
        return {"project_dir": str(_cfg(config, "project_dir"))}

    if action == "serial_list_ports":
        return {}

    if action == "serial_connect":
        return {
            "port": str(_cfg(config, "port")),
            "baud": _as_int(_cfg(config, "baud", 0), 0),
        }

    if action == "serial_send":
        args = {
            "port": str(_cfg(config, "port")),
            "data": str(_cfg(config, "data")),
            "read_response": _as_bool(_cfg(config, "read_response", True), True),
            "read_timeout": _as_float(_cfg(config, "read_timeout", 2.0), 2.0),
        }
        if _cfg(config, "line_ending"):
            args["line_ending"] = str(_cfg(config, "line_ending"))
        return args

    if action == "serial_read":
        return {
            "port": str(_cfg(config, "port")),
            "timeout": _as_float(_cfg(config, "serial_timeout", 2.0), 2.0),
            "max_bytes": _as_int(_cfg(config, "max_bytes", 4096), 4096),
        }

    if action == "serial_disconnect":
        return {"port": str(_cfg(config, "port"))}

    if action == "read_memory":
        args = {
            "system": str(_cfg(config, "system", "make") or "make"),
            "count": _as_int(_cfg(config, "count", 1), 1),
            "width": _as_int(_cfg(config, "width", 32), 32),
        }
        for key in ("address", "symbol", "project_dir", "elf"):
            if _cfg(config, key):
                args[key] = str(_cfg(config, key))
        return args

    if action == "write_memory":
        args = {
            "value": str(_cfg(config, "value")),
            "system": str(_cfg(config, "system", "make") or "make"),
            "width": _as_int(_cfg(config, "width", 32), 32),
        }
        for key in ("address", "symbol", "project_dir", "elf"):
            if _cfg(config, key):
                args[key] = str(_cfg(config, key))
        return args

    if action == "live_memory_start":
        args = {
            "variables": str(_cfg(config, "variables")),
            "system": str(_cfg(config, "system", "make") or "make"),
            "interval_ms": _as_int(_cfg(config, "interval_ms", 500), 500),
        }
        for key in ("elf", "project_dir", "output_path"):
            if _cfg(config, key):
                args[key] = str(_cfg(config, key))
        return args

    if action == "live_memory_read":
        return {
            "session_id": str(_cfg(config, "session_id")),
            "last_n": _as_int(_cfg(config, "last_n", 10), 10),
        }

    if action == "live_memory_stop":
        return {"session_id": str(_cfg(config, "session_id"))}

    return {}


def _subject_for(action: str, config: dict) -> str:
    """The human-facing subject of this run, used in the section header / log lines."""
    if action == "create_project":
        return f"{_cfg(config, 'name')} -> {_cfg(config, 'dest_parent')}"
    if action in ("write_source", "read_source"):
        return str(_cfg(config, "rel_path"))
    if action in ("build", "build_and_flash", "flash", "list_artifacts", "clean",
                  "list_sources", "erase", "reset"):
        return str(_cfg(config, "project_dir")) or "(connected target)"
    if action in ("serial_connect", "serial_send", "serial_read", "serial_disconnect",
                  "serial_session"):
        return str(_cfg(config, "port")) or "(serial)"
    if action in ("read_memory", "write_memory"):
        return str(_cfg(config, "symbol")) or str(_cfg(config, "address")) or "(memory)"
    if action in ("live_memory_start", "live_monitor"):
        return str(_cfg(config, "variables")) or "(live memory)"
    if action in ("live_memory_read", "live_memory_stop"):
        return str(_cfg(config, "session_id")) or "(session)"
    if action == "discover_toolchain_tool":
        return str(_cfg(config, "discover_ide_root")) or "(auto-discover)"
    return "(environment)"


# ========================================
# MINIMAL MCP STDIO CLIENT (newline-delimited JSON-RPC over the server's stdio)
# (raw protocol client — does NOT import the `mcp` package; only the SERVER needs it)
# ========================================

class _McpStdioClient:
    """Spawn the STM32 MCP server, perform the MCP initialize handshake, and call
    its tools over newline-delimited JSON-RPC. A daemon reader thread drains the
    server's stdout into a queue (Windows pipe reads cannot be interrupted, so the
    thread + queue is the cross-platform way to read with a timeout); stderr is
    drained into a buffer for diagnostics. Never raises into the caller — every
    method returns a result dict or raises a single contained RuntimeError that
    main() converts into a clean error section."""

    def __init__(self, python_cmd: list, server_script: str, env: dict, cwd: str,
                 startup_timeout: float, call_timeout: float):
        self.python_cmd = python_cmd
        self.server_script = server_script
        self.env = env
        self.cwd = cwd
        self.startup_timeout = startup_timeout
        self.call_timeout = call_timeout
        self.proc = None
        self._out_q: "queue.Queue" = queue.Queue()
        self._stderr_buf: list = []
        self._reader = None
        self._stderr_reader = None
        self._next_id = 0

    # ---- lifecycle ----
    def start(self) -> None:
        cmd = list(self.python_cmd) + [self.server_script]
        logging.info(f"🛰️  Spawning STM32 MCP server: {cmd}")
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"Cannot launch MCP server python {cmd}: {e}")

        self._reader = threading.Thread(target=self._read_stdout, daemon=True, name="stm32-mcp-stdout")
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True, name="stm32-mcp-stderr")
        self._stderr_reader.start()

    def _read_stdout(self) -> None:
        try:
            for line in self.proc.stdout:
                if line:
                    self._out_q.put(line)
        except Exception:
            pass
        finally:
            self._out_q.put(None)  # EOF sentinel

    def _read_stderr(self) -> None:
        try:
            for line in self.proc.stderr:
                if line:
                    self._stderr_buf.append(line.rstrip("\n"))
                    if len(self._stderr_buf) > 400:
                        del self._stderr_buf[:200]
        except Exception:
            pass

    def stderr_text(self, limit: int = 2000) -> str:
        return "\n".join(self._stderr_buf)[-limit:]

    def close(self) -> None:
        if not self.proc:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    # ---- JSON-RPC plumbing ----
    def _send(self, message: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("MCP server stdin not available.")
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"MCP server stdin write failed (server gone?): {e}")

    def _read_response(self, expected_id: int, timeout: float) -> dict:
        """Drain the stdout queue until a JSON-RPC response with `expected_id`
        arrives, swallowing server-originated notifications (and answering a
        ping request if the server sends one). Raises on EOF / timeout."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"Timed out after {timeout:.0f}s waiting for MCP response id={expected_id}. "
                    f"stderr tail: {self.stderr_text(600)}"
                )
            try:
                line = self._out_q.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError(
                        f"MCP server exited (code {self.proc.returncode}) before responding. "
                        f"stderr tail: {self.stderr_text(1200)}"
                    )
                continue
            if line is None:
                raise RuntimeError(
                    f"MCP server closed stdout before responding (code {self.proc.poll()}). "
                    f"stderr tail: {self.stderr_text(1200)}"
                )
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # Not a JSON-RPC frame (stray print) — ignore.
                continue
            if not isinstance(msg, dict):
                continue
            mid = msg.get("id")
            if mid == expected_id:
                return msg
            # Server -> client request (e.g. ping): answer minimally so it proceeds.
            if msg.get("method") == "ping" and mid is not None:
                try:
                    self._send({"jsonrpc": "2.0", "id": mid, "result": {}})
                except Exception:
                    pass
            # Otherwise it's a notification or an unrelated id — keep draining.

    def _request(self, method: str, params: dict, timeout: float) -> dict:
        self._next_id += 1
        req_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return self._read_response(req_id, timeout)

    def initialize(self) -> dict:
        resp = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tlamatini-stm32er", "version": "1.0.0"},
            },
            self.startup_timeout,
        )
        if "error" in resp:
            raise RuntimeError(f"MCP initialize failed: {resp['error']}")
        # initialized notification (no id, no response expected)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        server_info = (resp.get("result") or {}).get("serverInfo", {})
        logging.info(
            f"🤝 MCP handshake OK — server: {server_info.get('name', '?')} "
            f"v{server_info.get('version', '?')}"
        )
        return resp.get("result") or {}

    def call_tool(self, name: str, arguments: dict) -> dict:
        resp = self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            self.call_timeout,
        )
        if "error" in resp:
            err = resp["error"]
            return {"ok": False, "error": f"JSON-RPC error from {name}: "
                    f"{err.get('message', err)}", "_rpc_error": err}
        return self._parse_call_result(resp.get("result"))

    @staticmethod
    def _parse_call_result(result_obj) -> dict:
        """Extract the tool's own return dict from a CallToolResult. FastMCP emits
        BOTH a text content block carrying the JSON-serialized return AND (on newer
        SDKs) a structuredContent mirror — prefer the text JSON, fall back to
        structuredContent (unwrapping a sole {'result': ...} envelope)."""
        if not isinstance(result_obj, dict):
            return {"ok": False, "error": f"Malformed tool result: {result_obj!r}"}
        is_error = bool(result_obj.get("isError"))
        parsed = None

        content = result_obj.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    txt = block["text"]
                    try:
                        parsed = json.loads(txt)
                    except (json.JSONDecodeError, TypeError):
                        parsed = {"text": txt}
                    break

        if parsed is None:
            sc = result_obj.get("structuredContent")
            if isinstance(sc, dict):
                if set(sc.keys()) == {"result"}:
                    parsed = sc["result"]
                else:
                    parsed = sc

        if parsed is None:
            parsed = {}
        if isinstance(parsed, dict) and is_error and "ok" not in parsed:
            parsed["ok"] = False
        return parsed if isinstance(parsed, dict) else {"value": parsed}


# ========================================
# ACTION EXECUTION (direct + composite)
# ========================================

def _tool_ok(result: dict) -> bool:
    """Decide whether a tool result represents success. Most STM32 MCP tools
    return an explicit ``ok`` boolean, but a few read-only ones (get_config,
    discover_toolchain_tool) return a plain dict with NO ``ok`` key — for those a
    non-error result counts as success."""
    if not isinstance(result, dict):
        return False
    if "ok" in result:
        return bool(result["ok"])
    if "error" in result or "_rpc_error" in result:
        return False
    return True


def _run_action(client: _McpStdioClient, action: str, config: dict) -> dict:
    """Execute the selected action against the live MCP session. Returns a
    normalized envelope: {ok, tool, result, results?, session_id, project_dir}."""
    if action in _DIRECT_TOOLS:
        args = _build_arguments(action, config)
        logging.info(f"🔧 tools/call {action} args={_safe_args(action, args)}")
        result = client.call_tool(action, args)
        return {
            "ok": _tool_ok(result),
            "tool": action,
            "result": result,
        }

    if action == "serial_session":
        return _composite_serial_session(client, config)

    if action == "live_monitor":
        return _composite_live_monitor(client, config)

    valid = ", ".join(sorted(_ALL_ACTIONS))
    return {
        "ok": False,
        "tool": action,
        "result": {"ok": False, "error": f"Unknown action {action!r}. Valid actions: {valid}."},
    }


def _safe_args(action: str, args: dict) -> dict:
    """Mask large/sensitive fields in logged arguments."""
    masked = dict(args)
    if "content" in masked and masked["content"]:
        masked["content"] = f"<{len(str(masked['content']))} chars>"
    return masked


def _composite_serial_session(client: _McpStdioClient, config: dict) -> dict:
    """connect -> (send+read | read) -> disconnect, all in one server lifetime."""
    port = str(_cfg(config, "port"))
    results = {}
    overall_ok = True

    connect = client.call_tool("serial_connect", _build_arguments("serial_connect", config))
    results["serial_connect"] = connect
    if not _tool_ok(connect):
        return {"ok": False, "tool": "serial_session", "result": connect, "results": results}

    data = str(_cfg(config, "data"))
    if data:
        step = client.call_tool("serial_send", _build_arguments("serial_send", config))
        results["serial_send"] = step
    else:
        step = client.call_tool("serial_read", _build_arguments("serial_read", config))
        results["serial_read"] = step
    overall_ok = _tool_ok(step)

    disconnect = client.call_tool("serial_disconnect", {"port": port})
    results["serial_disconnect"] = disconnect

    return {"ok": overall_ok, "tool": "serial_session", "result": step, "results": results}


def _composite_live_monitor(client: _McpStdioClient, config: dict) -> dict:
    """start -> stream for monitor_seconds -> read last_n -> stop, in one lifetime."""
    results = {}
    start = client.call_tool("live_memory_start", _build_arguments("live_memory_start", config))
    results["live_memory_start"] = start
    if not _tool_ok(start):
        return {"ok": False, "tool": "live_monitor", "result": start, "results": results}

    session_id = str(start.get("session_id", ""))
    monitor_seconds = max(0, _as_int(_cfg(config, "monitor_seconds", 5), 5))
    last_n = _as_int(_cfg(config, "last_n", 10), 10)
    logging.info(f"📡 Streaming session {session_id} for {monitor_seconds}s...")
    time.sleep(monitor_seconds)

    read = client.call_tool("live_memory_read", {"session_id": session_id, "last_n": last_n})
    results["live_memory_read"] = read

    stop = client.call_tool("live_memory_stop", {"session_id": session_id})
    results["live_memory_stop"] = stop

    return {
        "ok": _tool_ok(read),
        "tool": "live_monitor",
        "result": read,
        "results": results,
        "session_id": session_id,
    }


# ========================================
# STRUCTURED OUTPUT (Parametrizer / KV-promotion contract)
# ========================================

def _result_body(action: str, result: dict, results: dict | None) -> str:
    """Build the human-readable section body. Prefer stdout/stderr for build/flash
    /memory CLI tools; otherwise pretty-print the tool's JSON return. For composites
    include every sub-step result so the whole chain is visible/parametrizable."""
    def one(res: dict) -> str:
        if not isinstance(res, dict):
            return str(res)
        parts = []
        if res.get("error"):
            parts.append(f"[error] {res['error']}")
        if res.get("stdout"):
            parts.append(str(res["stdout"]))
        if res.get("stderr"):
            parts.append(f"[stderr]\n{res['stderr']}")
        if parts:
            return "\n".join(parts)
        try:
            return json.dumps(res, indent=2, default=str)
        except Exception:
            return str(res)

    if results:
        chunks = []
        for step_name, res in results.items():
            chunks.append(f"===== {step_name} =====\n{one(res)}")
        return "\n\n".join(chunks)[:60000]
    return one(result)[:60000]


def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_STM32ER<<< block atomically (single logging.info call).

    Mirrors the Kalier / Apirer / ACPXer convention so this agent's structured
    output is consumable by the Multi-Turn LLM (via the wrapped chat-agent
    run-result KV promotion) AND the Parametrizer canvas pipeline (registered in
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['stm32er'] and
    parametrizer.SECTION_AGENT_TYPES). The KV header field names below MUST stay
    aligned with that registration."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_STM32ER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_STM32ER")


# ========================================
# MCP AUTO-BOOTSTRAP (zero-config installer)
#
# So the end user only installs STM32CubeIDE + Tlamatini, STM32er can &mdash; based
# purely on its config &mdash; DOWNLOAD the STM32 Template Project MCP from its git
# repo (or a zip fallback when git is absent), pip-INSTALL the server's Python deps
# (mcp + pyserial), VALIDATE the install, and only THEN spawn the stdio server and
# run the requested action. Everything here is stdlib-only (subprocess + urllib +
# zipfile) and NEVER raises into main(): each helper returns a result dict so a
# failed bootstrap degrades into a clean error section the user can read.
# ========================================

_DEFAULT_MCP_REPO_URL = "https://github.com/XAIHT/STM32TemplateProjectMCP.git"
_DEPS_SENTINEL = ".tlamatini_deps_ok"


def _default_install_dir() -> str:
    """A per-user, writable cache dir for the cloned MCP. Works in source AND in a
    frozen 'Program Files' install (where the app dir may be read-only)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "STM32TemplateProjectMCP")


def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 120.0):
    """Run a subprocess and capture (returncode, stdout, stderr). Never raises;
    maps a missing executable to rc 127 and a timeout to rc 124 so callers branch."""
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f}s"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", str(e)


def _git_available(env: dict) -> bool:
    rc, _o, _e = _run_cmd(["git", "--version"], env=env, timeout=30)
    return rc == 0


def _server_script_in(install_dir: str) -> str:
    return os.path.join(install_dir, "mcp", "stm32_mcp_server.py")


def _zip_urls_for(repo_url: str, ref: str) -> list:
    """Candidate GitHub codeload zip URLs for a repo URL (git or https). Tries the
    requested ref first, then 'main', then 'master'."""
    base = repo_url.strip()
    if base.endswith(".git"):
        base = base[:-4]
    base = base.rstrip("/")
    urls, seen = [], set()
    for candidate in (ref, "main", "master"):
        if candidate and candidate not in seen:
            seen.add(candidate)
            urls.append(f"{base}/archive/refs/heads/{candidate}.zip")
    return urls


def _download_zip_fallback(repo_url: str, install_dir: str, ref: str) -> dict:
    """git-less fallback: download the repo as a zip from GitHub codeload and
    extract it INTO install_dir, flattening the top-level '<repo>-<ref>/' folder."""
    import urllib.request
    import zipfile
    import tempfile
    import shutil

    last_err = ""
    for url in _zip_urls_for(repo_url, ref):
        try:
            logging.info(f"⬇️  Downloading MCP zip: {url}")
            tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
            os.close(tmp_fd)
            request = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-STM32er"})
            with urllib.request.urlopen(request, timeout=120) as resp, open(tmp_zip, "wb") as out:
                shutil.copyfileobj(resp, out)
            extract_root = tempfile.mkdtemp(prefix="stm32mcp_zip_")
            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(extract_root)
            entries = [os.path.join(extract_root, name) for name in os.listdir(extract_root)]
            top = next((p for p in entries if os.path.isdir(p)), extract_root)
            os.makedirs(install_dir, exist_ok=True)
            for name in os.listdir(top):
                src = os.path.join(top, name)
                dst = os.path.join(install_dir, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
            try:
                os.remove(tmp_zip)
                shutil.rmtree(extract_root, ignore_errors=True)
            except Exception:
                pass
            if os.path.exists(_server_script_in(install_dir)):
                return {"ok": True, "action": "downloaded-zip", "method": "zip", "url": url}
            last_err = f"zip extracted but {_server_script_in(install_dir)} is missing"
        except Exception as e:
            last_err = f"{url}: {e}"
            logging.warning(f"⚠️ zip download failed: {last_err}")
    return {"ok": False, "action": "zip-failed", "method": "zip", "error": last_err}


def _clone_or_update_repo(repo_url: str, install_dir: str, ref: str, do_update: bool, env: dict) -> dict:
    """Ensure install_dir holds the MCP repo. Clones with git (shallow) when
    available, git-pulls when already present and do_update is set, and falls back
    to a zip download when git is missing or the clone fails."""
    git_dir = os.path.join(install_dir, ".git")
    have_server = os.path.exists(_server_script_in(install_dir))

    if os.path.isdir(git_dir):
        if not do_update:
            return {"ok": have_server, "action": "present", "method": "git", "path": install_dir}
        rc, out, err = _run_cmd(["git", "-C", install_dir, "pull", "--ff-only"], env=env, timeout=180)
        if ref:
            _run_cmd(["git", "-C", install_dir, "checkout", ref], env=env, timeout=60)
        return {"ok": os.path.exists(_server_script_in(install_dir)), "action": "updated",
                "method": "git", "returncode": rc, "detail": (err or out)[-400:]}

    if have_server:
        # A non-git copy is already present (e.g. from a prior zip download).
        return {"ok": True, "action": "present", "method": "copy", "path": install_dir}

    try:
        os.makedirs(os.path.dirname(install_dir) or ".", exist_ok=True)
    except Exception:
        pass

    if _git_available(env):
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [repo_url, install_dir]
        rc, out, err = _run_cmd(cmd, env=env, timeout=300)
        if rc == 0 and os.path.exists(_server_script_in(install_dir)):
            return {"ok": True, "action": "cloned", "method": "git"}
        logging.warning(f"⚠️ git clone failed (rc={rc}); falling back to zip. {err[-300:]}")

    return _download_zip_fallback(repo_url, install_dir, ref)


def _imports_ok(python_cmd: list, env: dict) -> dict:
    """Probe whether ``mcp`` (and ``serial``) import in the interpreter that will
    RUN the server (which may differ from this agent's interpreter via mcp_python)."""
    probe = {}
    for module in ("mcp", "serial"):
        rc, _o, _e = _run_cmd(list(python_cmd) + ["-c", f"import {module}"], env=env, timeout=40)
        probe[module] = rc == 0
    return probe


def _ensure_python_deps(python_cmd: list, install_dir: str, env: dict, do_pip: bool) -> dict:
    """Make sure ``mcp`` (+ pyserial) are importable by python_cmd. Skips pip when
    they already import; otherwise pip-installs the server's requirements.txt (or
    mcp/pyserial directly) and re-probes. Writes a sentinel on success."""
    have = _imports_ok(python_cmd, env)
    if have.get("mcp"):
        try:
            open(os.path.join(install_dir, _DEPS_SENTINEL), "w").close()
        except Exception:
            pass
        return {"ok": True, "action": "already-installed", "have": have}
    if not do_pip:
        return {"ok": False, "action": "missing-pip-disabled", "have": have}

    requirements = os.path.join(install_dir, "mcp", "requirements.txt")
    if os.path.exists(requirements):
        cmd = list(python_cmd) + ["-m", "pip", "install", "--disable-pip-version-check", "-r", requirements]
    else:
        cmd = list(python_cmd) + ["-m", "pip", "install", "--disable-pip-version-check",
                                  "mcp>=1.2.0", "pyserial>=3.5"]
    logging.info(f"📦 Installing MCP server deps: {cmd}")
    rc, out, err = _run_cmd(cmd, env=env, timeout=600)
    have_after = _imports_ok(python_cmd, env)
    installed = bool(have_after.get("mcp"))
    if installed:
        try:
            open(os.path.join(install_dir, _DEPS_SENTINEL), "w").close()
        except Exception:
            pass
    return {"ok": installed, "action": "pip-install", "returncode": rc, "have": have_after,
            "stdout": out[-1500:], "stderr": err[-1500:]}


def _validate_install(python_cmd: list, server_script: str, env: dict) -> dict:
    """Validate that everything needed to run the server is in place."""
    checks = {"server_script_exists": os.path.exists(server_script)}
    probe = _imports_ok(python_cmd, env)
    checks["mcp_importable"] = bool(probe.get("mcp"))
    checks["pyserial_importable"] = bool(probe.get("serial"))
    validated = checks["server_script_exists"] and checks["mcp_importable"]
    return {"ok": validated, "checks": checks}


def _bootstrap_mcp(config: dict, python_cmd: list, env: dict):
    """Orchestrate the full zero-config install: download/update the repo, ensure
    the Python deps, validate. Returns (resolved_server_script, report, ok)."""
    report = {"steps": []}
    try:
        repo_url = str(_cfg(config, "mcp_repo_url", _DEFAULT_MCP_REPO_URL) or _DEFAULT_MCP_REPO_URL).strip()
        ref = str(_cfg(config, "mcp_ref")).strip()
        configured_dir = str(_cfg(config, "mcp_install_dir")).strip()
        install_dir = configured_dir or _default_install_dir()
        do_update = _as_bool(_cfg(config, "auto_update", False), False)
        do_pip = _as_bool(_cfg(config, "pip_install", True), True)

        report["repo_url"] = repo_url
        report["install_dir"] = install_dir

        repo_res = _clone_or_update_repo(repo_url, install_dir, ref, do_update, env)
        report["steps"].append(("download", repo_res))

        server_script = _server_script_in(install_dir)
        report["server_script"] = server_script

        if not repo_res.get("ok"):
            report["ok"] = False
            return server_script, report, False

        deps_res = _ensure_python_deps(python_cmd, install_dir, env, do_pip)
        report["steps"].append(("deps", deps_res))

        val_res = _validate_install(python_cmd, server_script, env)
        report["steps"].append(("validate", val_res))

        bootstrap_ok = bool(repo_res.get("ok") and deps_res.get("ok") and val_res.get("ok"))
        report["ok"] = bootstrap_ok
        return server_script, report, bootstrap_ok
    except Exception as e:  # pragma: no cover - bootstrap must NEVER raise into main()
        logging.error(f"❌ bootstrap crashed: {e}")
        fallback_dir = str(_cfg(config, "mcp_install_dir")).strip() or _default_install_dir()
        report["ok"] = False
        report["error"] = str(e)
        return _server_script_in(fallback_dir), report, False


def _format_bootstrap_report(report: dict) -> str:
    """Human-readable bootstrap report for the section body."""
    if not report:
        return "No bootstrap was performed."
    lines = [
        f"repo_url    : {report.get('repo_url', '')}",
        f"install_dir : {report.get('install_dir', '')}",
        f"server      : {report.get('server_script', '')}",
        f"overall     : {'OK' if report.get('ok') else 'FAILED'}",
        "",
    ]
    for name, res in report.get("steps", []):
        step_ok = res.get("ok")
        head = f"[{'OK' if step_ok else 'XX'}] {name}: action={res.get('action', '')}"
        if "returncode" in res:
            head += f" rc={res.get('returncode')}"
        lines.append(head)
        if name == "validate":
            for check_name, check_val in (res.get("checks") or {}).items():
                lines.append(f"        - {check_name}: {check_val}")
        if not step_ok and res.get("error"):
            lines.append(f"        error: {res['error']}")
        if not step_ok and res.get("stderr"):
            lines.append(f"        stderr: {res['stderr'][-400:]}")
    if report.get("error"):
        lines.append(f"\nbootstrap error: {report['error']}")
    return "\n".join(lines)


def _bootstrap_note(report: dict, bootstrap_ok: bool) -> str:
    """One-line prefix appended to a tool-run body when the installer ran this turn."""
    if not report:
        return ""
    download = next((res for name, res in report.get("steps", []) if name == "download"), {})
    deps = next((res for name, res in report.get("steps", []) if name == "deps"), {})
    return (
        f"[bootstrap: {download.get('action', '?')} via {download.get('method', '?')} · "
        f"deps={deps.get('action', '?')} · ready={'yes' if bootstrap_ok else 'NO'}]\n\n"
    )


# ========================================
# SAFETY PREFLIGHT (critical-mission environment validation + fail-safe gate)
#
# Before STM32er COMPILES or FLASHES anything it proves the environment is what it
# claims to be, and REFUSES the operation (rather than guessing) when a guarantee
# cannot be made. The cardinal rule for a system that programs mission-critical
# robots: never silently produce or upload mis-targeted firmware.
#
#   • compile-only actions (build / list_artifacts / clean / create_project / ...)
#     require the arm-none-eabi-gcc toolchain + a build tool + a SUPPORTED device,
#     but NEVER a board.
#   • hardware actions (flash / erase / reset / serial_* / SWD / live_*) ALSO
#     require the STM32_Programmer_CLI, a working ST-LINK USB driver, AND a
#     physically connected ST-LINK probe — positively confirmed, or we refuse.
# ========================================


def _device_family(device: str) -> str:
    """Map an STM32 part (e.g. 'STM32F407VG' → 'STM32F4', 'STM32H750VB' → 'STM32H7',
    'STM32N657X0' → 'STM32N6') to its family. Spans the WHOLE ST 32-bit line; empty
    string when it is not a recognised STM32 part."""
    d = (device or "").strip().upper()
    for fam in _STM32_FAMILY_PREFIXES:
        if d.startswith(fam):
            return fam
    # Fallback: any STM32<letter><digit> token (covers future value-line parts).
    m = re.match(r"STM32([A-Z]\d)", d)
    return ("STM32" + m.group(1)) if m else ""


def _probe_stlink(programmer_cli: str, env: dict) -> dict:
    """Non-invasively probe for a connected ST-LINK using STM32_Programmer_CLI's
    probe-list (does NOT connect to / reset the target). Distinguishes three states
    that matter for a fail-safe gate: probe present, no probe (driver fine, just no
    board), and the CLI itself unusable (driver/programmer missing)."""
    result = {"present": False, "driver_ok": False, "rc": None, "detail": ""}
    if not programmer_cli or not os.path.exists(programmer_cli):
        result["detail"] = "STM32_Programmer_CLI not found (cannot probe ST-LINK)."
        return result
    rc, out, err = _run_cmd([programmer_cli, "--list"], env=env, timeout=40)
    text = (out or "") + "\n" + (err or "")
    result["rc"] = rc
    result["detail"] = text[-800:]
    # A connected probe prints an "ST-LINK SN" / "ST-Link Probe N" line. Require a
    # POSITIVE match — a parse miss errs toward "absent" so we refuse rather than
    # flash blind (a false negative is annoying; a false positive is dangerous).
    if re.search(r"ST-?LINK\s+SN", text, re.I) or re.search(r"ST-?Link\s+Probe\s*\d", text, re.I):
        result["present"] = True
        result["driver_ok"] = True
    elif re.search(r"no\s+(st-?link|debug\s+probe).*(detect|found)", text, re.I) \
            or re.search(r"no\s+stlink", text, re.I):
        # The CLI ran and enumerated nothing → driver is fine, the board is absent.
        result["driver_ok"] = True
    elif rc == 127:
        result["driver_ok"] = False
    else:
        # Could not positively confirm a probe; treat as absent but driver usable.
        result["driver_ok"] = rc != 127
    return result


def _preflight(client: "_McpStdioClient", action: str, config: dict, env: dict) -> dict:
    """Validate the environment for ``action`` against the live MCP (single source
    of truth for the toolchain via get_config) plus OS-level ST-LINK probing.
    Returns a report dict; report['ok'] is False when any FATAL gate trips."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True}

    try:
        cfg_res = client.call_tool("get_config", {})
    except Exception as e:
        cfg_res = {"ok": False, "error": str(e)}
    if not isinstance(cfg_res, dict):
        cfg_res = {}

    toolchain = cfg_res.get("discovered_toolchain") or {}
    if not isinstance(toolchain, dict):
        toolchain = {}
    server_config = cfg_res.get("config") if isinstance(cfg_res.get("config"), dict) else {}
    mcu = server_config.get("mcu") if isinstance(server_config.get("mcu"), dict) else {}

    gcc_bin = toolchain.get("gcc_bin")
    make_bin = toolchain.get("make_bin")
    cmake_bin = toolchain.get("cmake_bin")
    programmer = toolchain.get("programmer_cli")
    ide_root = toolchain.get("ide_root") or ""

    checks = report["checks"]
    checks["arm_none_eabi_gcc"] = bool(gcc_bin)
    checks["stm32cubeide"] = bool(ide_root and os.path.isdir(ide_root))
    checks["make"] = bool(make_bin)
    checks["cmake"] = bool(cmake_bin)
    checks["programmer_cli"] = bool(programmer)
    report["discovered"] = {
        "ide_root": ide_root, "gcc_bin": gcc_bin, "make_bin": make_bin,
        "cmake_bin": cmake_bin, "programmer_cli": programmer,
    }

    system = str(_cfg(config, "system", "make") or "make")
    build_tool_present = checks["cmake"] if system == "cmake" else checks["make"]

    # ── Device family: requested (config override) vs the template's device ──
    template_device = str(mcu.get("device", "")) if isinstance(mcu, dict) else ""
    requested_device = str(_cfg(config, "device")).strip() or template_device
    requested_family = _device_family(requested_device)
    template_family = _device_family(template_device)
    report["device"] = {
        "requested": requested_device, "template": template_device,
        "requested_family": requested_family, "template_family": template_family,
    }
    family_supported = True
    if requested_device and template_device:
        if requested_family and template_family and requested_family != template_family:
            family_supported = False
        elif requested_device.upper() != template_device.upper():
            report["warnings"].append(
                f"Requested device {requested_device} differs from the template's {template_device} "
                f"(same {template_family} family). The linker script (flash/RAM map) and startup file "
                f"are for {template_device} — verify they match {requested_device} BEFORE flashing."
            )
    checks["device_family_supported"] = family_supported

    # ── Hardware (ST-LINK) — probed for hardware actions (a FATAL gate) AND for
    #    the 'validate' diagnostic (informational, never fatal there) ──
    needs_hardware = action in _HARDWARE_ACTIONS
    report["requires_hardware"] = needs_hardware
    if needs_hardware or action == "validate":
        stlink = _probe_stlink(programmer, env)
        report["stlink"] = stlink
        checks["stlink_driver"] = stlink["driver_ok"]
        checks["stlink_connected"] = stlink["present"]

    # ── FATAL gating (fail-safe: refuse rather than mis-build / mis-flash) ──
    fatals = report["fatals"]
    is_compile = action in _BUILD_ACTIONS or action == "validate"
    if action in _BUILD_ACTIONS:
        if not checks["arm_none_eabi_gcc"]:
            fatals.append(
                "arm-none-eabi-gcc compiler NOT found. Install STM32CubeIDE (it bundles the GNU Arm "
                "toolchain), or set the STM32_IDE_ROOT / stm32_ide_root config so the MCP can discover it.")
        if not build_tool_present:
            fatals.append(
                f"'{system}' build tool NOT found in the STM32CubeIDE install — cannot compile.")
        if not family_supported:
            fatals.append(
                f"Target device {requested_device} (family {requested_family}) is NOT supported by the "
                f"template-MCP backend, which is configured for {template_device} ({template_family}). "
                f"REFUSING to build mis-targeted firmware. Use the PlatformIO backend instead — set "
                f"stm32_backend='platformio' (or pass a `board`, e.g. board='bluepill_f103c8'); under the "
                f"default stm32_backend='auto' a non-STM32F4 device already routes to PlatformIO "
                f"automatically. (STM32C0/H5/U0/WBA/N6 await the ST-native CubeCLT backend — Phase 2/3.)")
    if needs_hardware:
        if not checks["programmer_cli"]:
            fatals.append(
                "STM32_Programmer_CLI NOT found — cannot flash/erase/reset or access SWD. Install "
                "STM32CubeProgrammer (bundled with STM32CubeIDE).")
        elif not report["stlink"]["present"]:
            if not report["stlink"]["driver_ok"]:
                fatals.append(
                    "No ST-LINK detected AND the ST-LINK USB driver appears MISSING. Install the ST-LINK "
                    "driver (bundled with STM32CubeIDE / STM32CubeProgrammer) and reconnect the board.")
            else:
                fatals.append(
                    "No ST-LINK probe detected — connect the board's ST-LINK (check the USB cable) before "
                    "a flash/erase/reset/serial/SWD operation. (Compile-only actions do NOT need a board.)")

    report["is_compile"] = is_compile
    report["ok"] = not fatals
    return report


def _format_preflight_report(report: dict) -> str:
    """Human-readable preflight report for the section body."""
    if not report:
        return "No preflight was performed."
    device = report.get("device", {})
    disc = report.get("discovered", {})
    lines = [
        f"action            : {report.get('action', '')}",
        f"requires_hardware : {report.get('requires_hardware', False)}",
        f"overall           : {'READY' if report.get('ok') else 'REFUSED (fail-safe)'}",
        "",
        f"target device     : requested={device.get('requested', '') or '(template default)'!r} "
        f"template={device.get('template', '')!r}",
        f"STM32CubeIDE root : {disc.get('ide_root', '') or '(not found)'}",
        f"arm-none-eabi-gcc : {disc.get('gcc_bin', '') or '(NOT FOUND)'}",
        f"programmer (CLI)  : {disc.get('programmer_cli', '') or '(NOT FOUND)'}",
        "",
        "checks:",
    ]
    for name, value in report.get("checks", {}).items():
        lines.append(f"  [{'OK' if value else 'XX'}] {name}: {value}")
    if report.get("stlink"):
        s = report["stlink"]
        lines.append(f"  st-link probe   : present={s.get('present')} driver_ok={s.get('driver_ok')} "
                     f"rc={s.get('rc')}")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ========================================
# PLATFORMIO BACKEND  (Phase 1 — Blue Pill → STM32F7 / G / L / H7 / U5 …)
#
# The template-MCP backend above is welded to ONE device (STM32F407VG). To span the
# WHOLE ST 32-bit line, STM32er ALSO drives PlatformIO Core's `ststm32` platform
# DIRECTLY — the exact pattern ESP32er uses for espressif32. `pio` is a complete CLI
# (build / upload / monitor / board db / package manager), so there is NO second MCP
# server, and `pio` already knows every board's memory map / linker / startup, so one
# backend builds & flashes ~1000 STM32 boards. Self-contained: it reuses this file's
# stdlib boilerplate (_cfg / _as_* / get_python_command / get_agent_env / _probe_stlink)
# and NEVER imports agent.*.
#
# Zero-config: with no on-disk `pio_executable` and auto_bootstrap true, it installs
# PlatformIO Core into the SHARED per-user core dir (Tlamatini/platformio — the SAME
# one ESP32er uses, so a single PlatformIO install serves both firmware agents).
#
# Fail-safe preflight (mission-critical): it REFUSES a family PlatformIO cannot build
# (routing it to the future ST-native CubeCLT backend) and never mis-targets firmware.
# STM32 boards flash over the ST-LINK/SWD probe (NOT a USB-serial bootloader like the
# ESP32), so the upload gate probes the ST-LINK — and, because a bare ST-LINK v2 dongle
# has no enumerable VCP, it only WARNS on an inconclusive miss (never a false refusal),
# hard-refusing only when the ST-LINK CLI confidently reports no probe.
# ========================================

_STM32_BACKENDS = ("auto", "template_mcp", "platformio")

# Actions ONLY the PlatformIO backend implements — under `auto` these force the pio
# backend even with no board/device set. They are purely additive (the MCP path has
# no such actions), so routing them to pio never changes existing behavior.
_PIO_ONLY_ACTIONS = {
    "list_boards", "boards", "device_list", "system_info",
    "scaffold_build_upload", "scaffold_build_flash", "monitor_session",
    "pkg_install", "pkg_list", "pkg_update", "check", "test",
}

# ── PlatformIO action contract (each → one `pio` subcommand or a stdlib op) ──
_PIO_META = {"bootstrap", "validate"}
_PIO_INFO = {"system_info", "boards", "list_boards", "device_list", "pkg_list", "list_artifacts"}
_PIO_FILE = {"write_source", "read_source", "list_sources"}
_PIO_BUILD = {"build", "clean", "check", "test", "create_project", "pkg_install",
              "pkg_update", "scaffold_build_upload", "scaffold_build_flash"}
# STM32-native verbs `flash` / `build_and_flash` are accepted as aliases of pio's
# upload verbs so the LLM/user can speak either vocabulary.
_PIO_UPLOAD = {"upload", "build_and_upload", "flash", "build_and_flash"}
_PIO_MONITOR = {"monitor", "monitor_session"}
_PIO_HARDWARE = _PIO_UPLOAD | _PIO_MONITOR
_PIO_ALL = _PIO_META | _PIO_INFO | _PIO_FILE | _PIO_BUILD | _PIO_UPLOAD | _PIO_MONITOR

# Friendly board aliases → PlatformIO `ststm32` board ids. A raw pio board id passed
# in `board` is used as-is; this table just lets the user say "blue pill".
_STM32_BOARD_ALIASES = {
    "bluepill": "bluepill_f103c8", "blue pill": "bluepill_f103c8",
    "bluepill_f103c8": "bluepill_f103c8", "bluepill_f103c8_128k": "bluepill_f103c8_128k",
    "blackpill": "blackpill_f411ce", "black pill": "blackpill_f411ce",
    "blackpill_f411ce": "blackpill_f411ce", "blackpill_f401cc": "blackpill_f401cc",
    "disco_f407vg": "disco_f407vg", "discovery_f407": "disco_f407vg",
    "stm32f4discovery": "disco_f407vg", "f4discovery": "disco_f407vg",
    "nucleo_f401re": "nucleo_f401re", "nucleo_f411re": "nucleo_f411re",
    "nucleo_f446re": "nucleo_f446re", "nucleo_f103rb": "nucleo_f103rb",
    "nucleo_g071rb": "nucleo_g071rb", "nucleo_g474re": "nucleo_g474re",
    "nucleo_l476rg": "nucleo_l476rg", "nucleo_l432kc": "nucleo_l432kc",
    "nucleo_h743zi": "nucleo_h743zi", "nucleo_h723zg": "nucleo_h723zg",
    "nucleo_f746zg": "nucleo_f746zg", "nucleo_f767zi": "nucleo_f767zi",
    "nucleo_wb55rg_p": "nucleo_wb55rg_p",
}

# Best-effort STM32 part → representative pio board id (used when `board` is blank but
# `device` names a part). Not exhaustive — pass `board` for anything not here.
_STM32_DEVICE_TO_BOARD = {
    "STM32F103C8": "bluepill_f103c8", "STM32F103C8T6": "bluepill_f103c8",
    "STM32F103CB": "bluepill_f103c8_128k", "STM32F103RB": "nucleo_f103rb",
    "STM32F401CC": "blackpill_f401cc", "STM32F401RE": "nucleo_f401re",
    "STM32F411CE": "blackpill_f411ce", "STM32F411RE": "nucleo_f411re",
    "STM32F407VG": "disco_f407vg", "STM32F446RE": "nucleo_f446re",
    "STM32F746ZG": "nucleo_f746zg", "STM32F767ZI": "nucleo_f767zi",
    "STM32G071RB": "nucleo_g071rb", "STM32G474RE": "nucleo_g474re",
    "STM32L432KC": "nucleo_l432kc", "STM32L476RG": "nucleo_l476rg",
    "STM32H743ZI": "nucleo_h743zi", "STM32H723ZG": "nucleo_h723zg",
    "STM32WB55RG": "nucleo_wb55rg_p",
}


def _resolve_board_id(config: dict) -> str:
    """Resolve the PlatformIO board id from `board` (alias or raw id) or, failing
    that, from `device` via the best-effort part→board table. '' when unknown."""
    raw = str(_cfg(config, "board")).strip()
    if raw:
        return _STM32_BOARD_ALIASES.get(raw.lower(), raw)
    device = str(_cfg(config, "device")).strip().upper()
    if device:
        return _STM32_DEVICE_TO_BOARD.get(device, "")
    return ""


def _family_from_board(board: str) -> str:
    """Best-effort STM32 family from a pio board id (e.g. 'bluepill_f103c8' → STM32F1,
    'nucleo_h743zi' → STM32H7). '' when it cannot be derived — the caller then does
    not gate on family (pio still uses the board's own linker, so a wrong guess never
    mis-targets)."""
    b = (board or "").upper()
    for fam in _STM32_FAMILY_PREFIXES:  # ordered specific-first (WBA before WB)
        code = fam[len("STM32"):]       # e.g. 'F1', 'H7', 'WBA', 'N6'
        if re.search(rf"(?:^|[_-]){code}[0-9A-Z]", b):
            return fam
    return ""


def _resolve_stm32_backend(config: dict, action: str) -> str:
    """Decide which build backend runs this call. An explicit `stm32_backend` wins;
    'auto' (the default) routes to PlatformIO whenever a `board` is given, the action
    is PlatformIO-only, OR a `device` of a NON-STM32F4 family is requested — so the
    Blue Pill and every modern part reach the pio backend — else the legacy template
    MCP (blank / STM32F4, no board → today's EXACT flow, zero regression)."""
    chosen = str(_cfg(config, "stm32_backend", "auto") or "auto").strip().lower()
    if chosen in ("platformio", "pio"):
        return "platformio"
    if chosen in ("template_mcp", "mcp", "template"):
        return "template_mcp"
    # auto:
    if action in _PIO_ONLY_ACTIONS:
        return "platformio"
    if str(_cfg(config, "board")).strip():
        return "platformio"
    device = str(_cfg(config, "device")).strip()
    fam = _device_family(device)
    if device and fam and fam != "STM32F4":
        return "platformio"
    return "template_mcp"


# ── PlatformIO resolution + zero-config bootstrap (shared install with ESP32er) ──

def _pio_default_core_dir() -> str:
    """The SHARED per-user PlatformIO core dir (penv + toolchains). Identical to
    ESP32er's so one PlatformIO install serves both firmware agents."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "platformio")


def _pio_run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 900.0):
    """Run a subprocess, capturing (returncode, stdout, stderr); captures PARTIAL
    output on a timeout (a long first `pio run` downloads the toolchain). Never
    raises; maps a missing exe to rc 127 and a timeout to rc 124."""
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired as e:
        partial = ""
        try:
            partial = (e.stdout or "") + (e.stderr or "")
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
        except Exception:
            partial = ""
        return 124, partial, f"timed out after {timeout:.0f}s"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", str(e)


def _pio_penv_path(core_dir: str) -> str:
    if os.name == "nt":
        return os.path.join(core_dir, "penv", "Scripts", "pio.exe")
    return os.path.join(core_dir, "penv", "bin", "pio")


def _pio_version(pio_cmd: list, env: dict) -> tuple:
    rc, out, err = _pio_run_cmd(list(pio_cmd) + ["--version"], env=env, timeout=60)
    return rc == 0, (out or err or "").strip()


def _pio_resolve_cmd(config: dict, env: dict, core_dir: str, python_cmd: list) -> list:
    """First invocable `pio` among: explicit `pio_executable`, the bootstrapped penv
    pio, bare `pio`/`platformio` on PATH, or `<python> -m platformio`. [] if none."""
    candidates = []
    explicit = str(_cfg(config, "pio_executable")).strip()
    if explicit:
        candidates.append([explicit])
    penv = _pio_penv_path(core_dir)
    if os.path.exists(penv):
        candidates.append([penv])
    candidates.append(["pio"])
    candidates.append(["platformio"])
    candidates.append(list(python_cmd) + ["-m", "platformio"])
    for cand in candidates:
        ok, _ver = _pio_version(cand, env)
        if ok:
            return cand
    return []


def _pio_download_installer(env: dict) -> tuple:
    import urllib.request
    import tempfile
    url = "https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py"
    try:
        logging.info(f"⬇️  Downloading PlatformIO installer: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-STM32er"})
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = resp.read()
        fd, path = tempfile.mkstemp(suffix="_get-platformio.py")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _pio_bootstrap(config: dict, env: dict, core_dir: str, python_cmd: list) -> tuple:
    """Ensure an invocable `pio` exists, installing PlatformIO Core if needed.
    Returns (pio_cmd, report, ok). Never raises into main()."""
    report = {"steps": [], "core_dir": core_dir}
    try:
        method = str(_cfg(config, "pio_install_method", "script") or "script").strip().lower()
        do_update = _as_bool(_cfg(config, "auto_update", False), False)
        do_pip = _as_bool(_cfg(config, "pip_install", True), True)

        existing = _pio_resolve_cmd(config, env, core_dir, python_cmd)
        if existing and not do_update:
            ok, ver = _pio_version(existing, env)
            report["steps"].append(("resolve", {"ok": ok, "action": "present", "pio": existing, "version": ver}))
            report["ok"] = ok
            return existing, report, ok

        if method == "script":
            installer, dl_err = _pio_download_installer(env)
            if installer:
                inst_env = dict(env)
                inst_env["PLATFORMIO_CORE_DIR"] = core_dir
                rc, out, err = _pio_run_cmd(list(python_cmd) + [installer], env=inst_env, timeout=900)
                try:
                    os.remove(installer)
                except Exception:
                    pass
                report["steps"].append(("installer-script",
                                        {"ok": rc == 0, "action": "get-platformio.py",
                                         "returncode": rc, "stderr": (err or "")[-800:]}))
            else:
                report["steps"].append(("installer-script",
                                        {"ok": False, "action": "download-failed", "error": dl_err}))

        resolved = _pio_resolve_cmd(config, env, core_dir, python_cmd)
        if not resolved and do_pip:
            pip_cmd = list(python_cmd) + ["-m", "pip", "install", "--disable-pip-version-check"]
            pip_cmd += (["-U", "platformio"] if do_update else ["platformio"])
            logging.info(f"📦 Installing PlatformIO via pip: {pip_cmd}")
            rc, out, err = _pio_run_cmd(pip_cmd, env=env, timeout=900)
            report["steps"].append(("pip-install",
                                    {"ok": rc == 0, "action": "pip", "returncode": rc,
                                     "stderr": (err or "")[-800:]}))
            resolved = _pio_resolve_cmd(config, env, core_dir, python_cmd)

        if resolved and do_update and method != "pip":
            _pio_run_cmd(list(resolved) + ["upgrade"], env=env, timeout=600)

        ok, ver = (_pio_version(resolved, env) if resolved else (False, ""))
        report["steps"].append(("validate", {"ok": ok, "version": ver, "pio": resolved}))
        report["ok"] = ok
        return resolved, report, ok
    except Exception as e:  # pragma: no cover - bootstrap must NEVER raise into main()
        logging.error(f"❌ pio bootstrap crashed: {e}")
        report["ok"] = False
        report["error"] = str(e)
        return [], report, False


def _pio_format_bootstrap_report(report: dict) -> str:
    if not report:
        return "No bootstrap was performed."
    lines = [f"core_dir : {report.get('core_dir', '')}",
             f"overall  : {'OK' if report.get('ok') else 'FAILED'}", ""]
    for name, res in report.get("steps", []):
        head = f"[{'OK' if res.get('ok') else 'XX'}] {name}: action={res.get('action', '')}"
        if "returncode" in res:
            head += f" rc={res.get('returncode')}"
        if res.get("version"):
            head += f" ({res['version']})"
        lines.append(head)
        if not res.get("ok") and res.get("error"):
            lines.append(f"        error: {res['error']}")
        if not res.get("ok") and res.get("stderr"):
            lines.append(f"        stderr: {res['stderr'][-400:]}")
    if report.get("error"):
        lines.append(f"\nbootstrap error: {report['error']}")
    return "\n".join(lines)


def _pio_bootstrap_note(report: dict, ok: bool) -> str:
    if not report:
        return ""
    last = next((res for name, res in report.get("steps", [])
                 if name in ("installer-script", "pip-install")), {})
    return f"[bootstrap: {last.get('action', 'present')} · pio ready={'yes' if ok else 'NO'}]\n\n"


# ── PlatformIO safety preflight (fail-safe environment gate) ──

def _pio_platformio_ini(project_dir: str) -> str:
    return os.path.join(project_dir, "platformio.ini") if project_dir else ""


def _pio_ini_platform(project_dir: str) -> str:
    ini = _pio_platformio_ini(project_dir)
    if not ini or not os.path.exists(ini):
        return ""
    try:
        with open(ini, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"\s*platform\s*=\s*(\S+)", line)
                if m:
                    return m.group(1).strip()
    except Exception:
        return ""
    return ""


def _pio_resolve_programmer_cli(config: dict) -> str:
    """Best-effort resolution of STM32_Programmer_CLI (the strongest ST-LINK probe
    signal). Empty when not installed — the preflight then falls back to `pio device
    list` and only WARNS, so a missing CubeProgrammer never false-refuses."""
    import shutil
    import glob
    explicit = str(_cfg(config, "programmer_cli")).strip()
    if explicit and os.path.exists(explicit):
        return explicit
    for name in ("STM32_Programmer_CLI", "STM32_Programmer_CLI.exe"):
        hit = shutil.which(name)
        if hit:
            return hit
    for pattern in (
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
        r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
    ):
        for hit in glob.glob(pattern):
            if os.path.exists(hit):
                return hit
    return ""


def _pio_probe_stlink(config: dict, env: dict, pio_cmd: list) -> dict:
    """Probe for a connected ST-LINK (how STM32 boards flash — SWD, not a USB-serial
    bootloader). Two signals: STM32_Programmer_CLI --list (strongest; a positive line
    → present, an explicit 'no ST-LINK' → CONFIDENT absence), then `pio device list`
    for an ST-LINK VCP (VID 0483 — present on Nucleo/Disco; a bare ST-LINK v2 dongle
    has no VCP, so a miss there is inconclusive). Only a confident absence lets the
    upload gate refuse; otherwise it WARNS, never a false refusal."""
    result = {"present": False, "confident_absent": False, "method": "", "detail": ""}
    prog = _pio_resolve_programmer_cli(config)
    if prog:
        st = _probe_stlink(prog, env)
        result["method"] = "STM32_Programmer_CLI"
        result["detail"] = st.get("detail", "")
        if st.get("present"):
            result["present"] = True
            return result
        detail = st.get("detail", "") or ""
        if re.search(r"no\s+(st-?link|debug\s+probe).*(detect|found)", detail, re.I) \
                or re.search(r"no\s+stlink", detail, re.I):
            result["confident_absent"] = True
            return result
    if pio_cmd:
        rc, out, _err = _pio_run_cmd(list(pio_cmd) + ["device", "list", "--json-output"], env=env, timeout=60)
        if rc == 0:
            try:
                devices = json.loads(out or "[]")
            except (json.JSONDecodeError, TypeError):
                devices = []
            for dev in devices if isinstance(devices, list) else []:
                hwid = (dev.get("hwid") or "") if isinstance(dev, dict) else ""
                m = re.search(r"VID:PID=([0-9A-Fa-f]{4})", hwid)
                if m and m.group(1).upper() == _STLINK_USB_VID:
                    result["present"] = True
                    result["method"] = result["method"] or "pio device list"
                    result["detail"] = (result["detail"] + f" | pio: ST-LINK VCP {hwid}").strip(" |")
                    return result
    return result


def _pio_probe_serial(pio_cmd: list, env: dict) -> dict:
    """Enumerate serial ports via `pio device list --json-output` (a Nucleo/Disco VCP
    for `monitor`). A Blue Pill has no built-in VCP — monitor needs a USB-UART adapter."""
    result = {"present": False, "cli_ok": False, "ports": [], "detail": ""}
    if not pio_cmd:
        result["detail"] = "pio not resolvable — cannot enumerate serial ports."
        return result
    rc, out, err = _pio_run_cmd(list(pio_cmd) + ["device", "list", "--json-output"], env=env, timeout=60)
    result["cli_ok"] = rc == 0
    if rc != 0:
        result["detail"] = (err or out)[-400:]
        return result
    try:
        devices = json.loads(out or "[]")
    except (json.JSONDecodeError, TypeError):
        devices = []
    ports = [dev.get("port") for dev in (devices if isinstance(devices, list) else [])
             if isinstance(dev, dict) and dev.get("port")]
    result["ports"] = ports
    result["present"] = bool(ports)
    result["detail"] = f"{len(ports)} port(s): {', '.join(ports)}" if ports else "no serial ports enumerated"
    return result


def _pio_preflight(action: str, config: dict, pio_cmd: list, env: dict) -> dict:
    """Validate the PlatformIO environment for ``action`` and REFUSE (fail-safe)
    rather than mis-build. report['ok'] is False on any FATAL."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True}
    checks = report["checks"]

    pio_ok = bool(pio_cmd)
    checks["pio_resolvable"] = pio_ok

    board = _resolve_board_id(config)
    fam = _device_family(str(_cfg(config, "device")).strip()) or _family_from_board(board)
    report["board"] = board
    report["family"] = fam

    # ── Family support gate — the Phase-0 routing made real (fail-safe) ──
    if fam in _PIO_UNSUPPORTED_FAMILIES:
        report["fatals"].append(
            f"{fam} is not in the PlatformIO ststm32 platform yet — it needs the ST-native STM32CubeCLT "
            f"backend (Phase 2/3, not yet implemented). Refusing rather than mis-building. "
            f"{'(STM32N6 also boots from external flash and needs a signed FSBL.)' if fam == 'STM32N6' else ''}".strip())
    elif fam in _PIO_CAVEAT_FAMILIES:
        report["warnings"].append(
            f"{fam} has only PARTIAL PlatformIO ststm32 support — the build may fail; if it does, the "
            f"ST-native CubeCLT backend (Phase 2/3) is the intended path for this family.")
    checks["family_supported"] = fam not in _PIO_UNSUPPORTED_FAMILIES

    project_dir = str(_cfg(config, "project_dir")).strip()
    needs_project = action in {"build", "clean", "check", "test", "list_artifacts",
                               "pkg_list", "pkg_install", "pkg_update"} | _PIO_HARDWARE
    has_ini = bool(project_dir) and os.path.exists(_pio_platformio_ini(project_dir))
    if needs_project:
        checks["platformio_ini"] = has_ini

    needs_board = action in {"create_project", "scaffold_build_upload", "scaffold_build_flash"}
    if needs_board:
        checks["board_resolved"] = bool(board)

    needs_hardware = action in _PIO_HARDWARE
    report["requires_hardware"] = needs_hardware
    if needs_hardware or action == "validate":
        if action in _PIO_UPLOAD or action == "validate":
            stlink = _pio_probe_stlink(config, env, pio_cmd)
            report["stlink"] = stlink
            checks["stlink_present"] = stlink["present"]
        if action in _PIO_MONITOR or action == "validate":
            serial = _pio_probe_serial(pio_cmd, env)
            report["serial"] = serial
            checks["serial_port_present"] = serial["present"]

    # ── FATAL gating ──
    fatals = report["fatals"]
    if action != "bootstrap" and not pio_ok:
        fatals.append(
            "PlatformIO Core (`pio`) is NOT resolvable. Leave pio_executable blank with auto_bootstrap: "
            "true so STM32er installs it, or set pio_executable to an existing pio.")
    if needs_project and not has_ini:
        if not project_dir:
            fatals.append(
                f"action '{action}' needs a project — set project_dir to a folder containing "
                f"platformio.ini (use action='create_project' or 'scaffold_build_upload' first).")
        else:
            fatals.append(
                f"No platformio.ini in {project_dir!r} — not a PlatformIO project. "
                f"Run action='create_project' there first.")
    if needs_board and not board:
        fatals.append(
            "No board resolved — pass `board` (e.g. board='bluepill_f103c8'; run action='list_boards' to "
            "find one) or a known `device`. The board fixes the memory map / linker, so it is required.")
    if action in _PIO_UPLOAD and pio_ok:
        st = report.get("stlink", {})
        if st.get("confident_absent"):
            fatals.append(
                "No ST-LINK detected (STM32_Programmer_CLI reported none) — connect the board's ST-LINK "
                "(check the USB cable / driver) before a flash. (Compile-only actions do NOT need a board.)")
        elif not st.get("present"):
            report["warnings"].append(
                "No ST-LINK positively detected — a flash will FAIL if none is connected. (A bare ST-LINK "
                "v2 dongle has no VCP to enumerate, so this may be a false alarm; the upload will confirm.)")
    if action in _PIO_MONITOR and pio_ok:
        serial = report.get("serial", {})
        if not serial.get("present"):
            fatals.append(
                "No serial port detected — connect a VCP/USB-UART (a Nucleo/Disco has an ST-LINK VCP; a "
                "bare Blue Pill needs a USB-UART adapter) before monitoring.")

    report["ok"] = not fatals
    return report


def _pio_format_preflight_report(report: dict) -> str:
    if not report:
        return "No preflight was performed."
    lines = [
        f"action            : {report.get('action', '')}",
        f"board             : {report.get('board', '') or '(unresolved)'}",
        f"family            : {report.get('family', '') or '(unknown)'}",
        f"requires_hardware : {report.get('requires_hardware', False)}",
        f"overall           : {'READY' if report.get('ok') else 'REFUSED (fail-safe)'}",
        "",
        "checks:",
    ]
    for name, value in report.get("checks", {}).items():
        lines.append(f"  [{'OK' if value else 'XX'}] {name}: {value}")
    if report.get("stlink"):
        s = report["stlink"]
        lines.append(f"  st-link probe   : present={s.get('present')} confident_absent={s.get('confident_absent')} "
                     f"via={s.get('method') or '-'}")
    if report.get("serial"):
        s = report["serial"]
        lines.append(f"  serial          : present={s.get('present')} ({s.get('detail', '')})")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ── PlatformIO action execution ──

def _pio_env_args(config: dict) -> list:
    environment = str(_cfg(config, "environment")).strip()
    return ["-e", environment] if environment else []


def _pio_project_args(config: dict) -> list:
    project_dir = str(_cfg(config, "project_dir")).strip()
    return ["-d", project_dir] if project_dir else []


def _pio_terminate_proc(proc) -> None:
    if proc is None:
        return
    try:
        import psutil
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                try:
                    child.terminate()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _pio_bounded_monitor(pio_cmd: list, config: dict, env: dict) -> dict:
    """Run `pio device monitor` for monitor_seconds, draining stdout, then terminate
    — making an interactive stream usable in one run (Nucleo/Disco VCP HIL)."""
    seconds = max(1, _as_int(_cfg(config, "monitor_seconds", 10), 10))
    port = str(_cfg(config, "port")).strip()
    baud = _as_int(_cfg(config, "baud", 115200), 115200) or 115200
    args = list(pio_cmd) + ["device", "monitor", "-b", str(baud)]
    if port:
        args += ["-p", port]
    args += _pio_project_args(config) + ["--quiet"]
    logging.info(f"📟 Monitoring for {seconds}s: {args}")
    collected: list = []
    try:
        proc = subprocess.Popen(
            args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except Exception as e:
        return {"ok": False, "error": f"could not start monitor: {e}", "returncode": 127}

    def _drain():
        try:
            for line in proc.stdout:
                if line:
                    collected.append(line.rstrip("\n"))
                    if len(collected) > 5000:
                        del collected[:2500]
        except Exception:
            pass

    reader = threading.Thread(target=_drain, daemon=True, name="stm32-pio-monitor")
    reader.start()
    time.sleep(seconds)
    _pio_terminate_proc(proc)
    reader.join(timeout=2)
    return {"ok": True, "returncode": 0, "port": port or "(auto)", "monitor_seconds": seconds,
            "stdout": "\n".join(collected) or "(no serial output captured during the window)"}


def _pio_write_source(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    rel_path = str(_cfg(config, "rel_path")).strip()
    content = str(_cfg(config, "content"))
    if not project_dir or not rel_path:
        return {"ok": False, "error": "write_source needs project_dir and rel_path."}
    target = os.path.normpath(os.path.join(project_dir, rel_path))
    root = os.path.normpath(project_dir)
    if not target.startswith(root + os.sep) and target != root:
        return {"ok": False, "error": f"rel_path escapes project_dir: {rel_path!r}"}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "returncode": 0, "path": target,
                "stdout": f"Wrote {len(content)} chars to {target}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": target}


def _pio_read_source(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    rel_path = str(_cfg(config, "rel_path")).strip()
    if not project_dir or not rel_path:
        return {"ok": False, "error": "read_source needs project_dir and rel_path."}
    target = os.path.normpath(os.path.join(project_dir, rel_path))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return {"ok": True, "returncode": 0, "path": target, "stdout": f.read()}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": target}


def _pio_list_sources(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    if not project_dir or not os.path.isdir(project_dir):
        return {"ok": False, "error": "list_sources needs an existing project_dir."}
    found = []
    for sub in ("src", "include", "lib", "test", "Core"):
        root = os.path.join(project_dir, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                found.append(os.path.relpath(os.path.join(dirpath, name), project_dir).replace(os.sep, "/"))
    if os.path.exists(_pio_platformio_ini(project_dir)):
        found.insert(0, "platformio.ini")
    return {"ok": True, "returncode": 0, "stdout": "\n".join(found) or "(no source files found)"}


def _pio_ensure_framework(ini_path: str, framework: str) -> None:
    """Set/insert `framework = <framework>` under each [env:...] section."""
    if not os.path.exists(ini_path):
        return
    with open(ini_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    out, in_env, wrote = [], False, False
    for line in lines:
        if re.match(r"\s*\[env:", line):
            if in_env and not wrote:
                out.append(f"framework = {framework}\n")
            in_env, wrote = True, False
            out.append(line)
            continue
        if in_env and re.match(r"\s*framework\s*=", line):
            out.append(f"framework = {framework}\n")
            wrote = True
            continue
        out.append(line)
    if in_env and not wrote:
        out.append(f"framework = {framework}\n")
    with open(ini_path, "w", encoding="utf-8") as f:
        f.writelines(out)


def _pio_create_project(config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """`pio project init -b <board>` (pio generates the linker/startup/HAL for the
    board). Framework defaults to `arduino` (stm32duino — a board-agnostic blink works
    across the whole line); override with `framework: stm32cube|cmsis|mbed|libopencm3`."""
    project_dir = str(_cfg(config, "project_dir")).strip()
    board = _resolve_board_id(config)
    framework = str(_cfg(config, "framework")).strip() or "arduino"
    if not project_dir or not board:
        return {"ok": False, "error": "create_project needs project_dir and a resolvable board "
                                       "(board='bluepill_f103c8' or a known device)."}
    os.makedirs(project_dir, exist_ok=True)
    rc, out, err = _pio_run_cmd(list(pio_cmd) + ["project", "init", "-d", project_dir, "-b", board],
                                env=env, timeout=timeout)
    result = {"ok": rc == 0, "returncode": rc, "project_dir": project_dir, "board": board,
              "stdout": out, "stderr": err}
    if rc == 0 and framework:
        try:
            _pio_ensure_framework(_pio_platformio_ini(project_dir), framework)
            result["stdout"] = (out + f"\n[stm32er] framework='{framework}' set in platformio.ini").strip()
        except Exception as e:
            result["stderr"] = (err + f"\n[stm32er] could not set framework: {e}").strip()
    return result


def _pio_list_artifacts(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    build_root = os.path.join(project_dir, ".pio", "build")
    if not os.path.isdir(build_root):
        return {"ok": False, "error": f"No build output at {build_root} — run action='build' first."}
    artifacts = []
    for dirpath, _dirs, files in os.walk(build_root):
        for name in files:
            if name.startswith("firmware.") or name.endswith((".elf", ".bin", ".hex")):
                artifacts.append(os.path.join(dirpath, name))
    return {"ok": bool(artifacts), "returncode": 0 if artifacts else 1, "project_dir": project_dir,
            "stdout": "\n".join(artifacts) or "(no firmware artifacts found)"}


def _pio_cmd(args: list, pio_cmd: list, env: dict, timeout: float) -> dict:
    rc, out, err = _pio_run_cmd(list(pio_cmd) + list(args), env=env, timeout=timeout)
    return {"ok": rc == 0, "returncode": rc, "stdout": out, "stderr": err}


def _pio_run(extra: list, config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """`pio run` with -d/-e and any extra target args, plus optional --upload-port."""
    args = ["run"] + _pio_project_args(config) + _pio_env_args(config) + list(extra)
    upload_port = str(_cfg(config, "port")).strip()
    if "-t" in extra and "upload" in extra and upload_port:
        args += ["--upload-port", upload_port]
    return _pio_cmd(args, pio_cmd, env, timeout)


def _pio_ok(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if "ok" in result:
        return bool(result["ok"])
    return "error" not in result


def _pio_wrap(tool: str, result: dict) -> dict:
    return {"ok": _pio_ok(result), "tool": tool, "result": result}


def _pio_scaffold(config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """One-call lifecycle: create_project (if needed) → write_source (if `content`) →
    build → flash over ST-LINK (attempted unless the ST-LINK is CONFIDENTLY absent) →
    optional monitor. Collapses a 4-round-trip Multi-Turn chain into one run; fail-safe
    — a confidently-missing board still leaves a compiled project ('built OK')."""
    project_dir = str(_cfg(config, "project_dir")).strip()
    board = _resolve_board_id(config)
    stage_logs: list = []

    def _section(title: str, res: dict) -> None:
        out = (res.get("stdout") or "") if isinstance(res, dict) else ""
        err = (res.get("stderr") or "") if isinstance(res, dict) else ""
        joined = "\n".join(p for p in (out, err) if p).strip()
        stage_logs.append(f"===== {title} =====\n{joined or '(no output)'}")

    def _envelope(tool: str, ok: bool, stage: str, rc, extra: dict = None) -> dict:
        result = {"ok": ok, "returncode": rc, "stage": stage, "project_dir": project_dir,
                  "board": board, "stdout": "\n\n".join(stage_logs)}
        if extra:
            result.update(extra)
        return {"ok": ok, "tool": tool, "result": result}

    if not (project_dir and os.path.exists(_pio_platformio_ini(project_dir))):
        cp = _pio_create_project(config, pio_cmd, env, timeout)
        _section("create_project", cp)
        if not _pio_ok(cp):
            return _envelope("scaffold_build_flash", False, "create_project", cp.get("returncode", 1))
    else:
        stage_logs.append(f"===== create_project =====\n(skipped — platformio.ini already in {project_dir})")

    if str(_cfg(config, "content")).strip():
        if not str(_cfg(config, "rel_path")).strip():
            config["rel_path"] = "src/main.cpp"
        ws = _pio_write_source(config)
        _section("write_source", ws)
        if not _pio_ok(ws):
            return _envelope("scaffold_build_flash", False, "write_source", ws.get("returncode", 1))

    st = _pio_probe_stlink(config, env, pio_cmd)
    if st.get("confident_absent"):
        bd = _pio_run([], config, pio_cmd, env, timeout)
        _section("build", bd)
        if not _pio_ok(bd):
            return _envelope("scaffold_build_flash", False, "build", bd.get("returncode", 1))
        stage_logs.append("===== flash =====\nSKIPPED — no ST-LINK detected. The project compiled "
                          "successfully; connect the board's ST-LINK and run action='flash' to upload it.")
        return _envelope("scaffold_build_flash (flash skipped: no ST-LINK)", True, "flash_skipped", 0)

    up = _pio_run(["-t", "upload"], config, pio_cmd, env, timeout)
    _section("build+flash", up)
    if not _pio_ok(up):
        return _envelope("scaffold_build_flash", False, "flash", up.get("returncode", 1))
    if _as_int(_cfg(config, "monitor_seconds", 0), 0) > 0:
        _section("monitor", _pio_bounded_monitor(pio_cmd, config, env))
    return _envelope("scaffold→build→flash", True, "flash", up.get("returncode", 0))


def _pio_run_action(action: str, config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """Execute one PlatformIO action (STM32-native `flash`/`build_and_flash` verbs are
    accepted as aliases of pio's upload verbs). Returns {ok, tool, result}."""
    if action in ("scaffold_build_upload", "scaffold_build_flash"):
        return _pio_scaffold(config, pio_cmd, env, timeout)
    if action == "write_source":
        return _pio_wrap("write_source", _pio_write_source(config))
    if action == "read_source":
        return _pio_wrap("read_source", _pio_read_source(config))
    if action == "list_sources":
        return _pio_wrap("list_sources", _pio_list_sources(config))
    if action == "list_artifacts":
        return _pio_wrap("list_artifacts", _pio_list_artifacts(config))
    if action == "create_project":
        return _pio_wrap("project init", _pio_create_project(config, pio_cmd, env, timeout))
    if action == "monitor":
        return _pio_wrap("device monitor", _pio_bounded_monitor(pio_cmd, config, env))
    if action == "monitor_session":
        up = _pio_run(["-t", "upload"], config, pio_cmd, env, timeout)
        if not _pio_ok(up):
            return _pio_wrap("upload", up)
        mon = _pio_bounded_monitor(pio_cmd, config, env)
        mon["upload_returncode"] = up.get("returncode")
        return _pio_wrap("upload+monitor", mon)
    if action == "system_info":
        return _pio_wrap("system info", _pio_cmd(["system", "info"], pio_cmd, env, timeout))
    if action in ("boards", "list_boards"):
        query = str(_cfg(config, "boards_query") or _cfg(config, "board")).strip()
        args = ["boards", "--json-output"] + ([query] if query else ["stm32"])
        return _pio_wrap("boards", _pio_cmd(args, pio_cmd, env, 120))
    if action == "device_list":
        return _pio_wrap("device list", _pio_cmd(["device", "list", "--json-output"], pio_cmd, env, 60))
    if action == "build":
        return _pio_wrap("run", _pio_run([], config, pio_cmd, env, timeout))
    if action == "clean":
        return _pio_wrap("run -t clean", _pio_run(["-t", "clean"], config, pio_cmd, env, timeout))
    if action in ("upload", "build_and_upload", "flash", "build_and_flash"):
        return _pio_wrap("run -t upload", _pio_run(["-t", "upload"], config, pio_cmd, env, timeout))
    if action == "check":
        return _pio_wrap("check", _pio_cmd(["check"] + _pio_project_args(config) + _pio_env_args(config), pio_cmd, env, timeout))
    if action == "test":
        return _pio_wrap("test", _pio_cmd(["test"] + _pio_project_args(config) + _pio_env_args(config), pio_cmd, env, timeout))
    if action == "pkg_list":
        return _pio_wrap("pkg list", _pio_cmd(["pkg", "list"] + _pio_project_args(config), pio_cmd, env, 120))
    if action == "pkg_update":
        return _pio_wrap("pkg update", _pio_cmd(["pkg", "update"] + _pio_project_args(config), pio_cmd, env, 300))
    if action == "pkg_install":
        spec = str(_cfg(config, "pkg_spec")).strip()
        if not spec:
            return _pio_wrap("pkg install", {"ok": False, "error": "pkg_install needs pkg_spec (a library spec)."})
        return _pio_wrap("pkg install", _pio_cmd(["pkg", "install"] + _pio_project_args(config) + ["-l", spec], pio_cmd, env, 300))
    valid = ", ".join(sorted(_PIO_ALL))
    return _pio_wrap(action, {"ok": False, "error": f"Unknown PlatformIO action {action!r}. Valid: {valid}."})


def _pio_result_body(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)
    parts = []
    if result.get("error"):
        parts.append(f"[error] {result['error']}")
    if result.get("stdout"):
        parts.append(str(result["stdout"]))
    if result.get("stderr"):
        parts.append(f"[stderr]\n{result['stderr']}")
    if parts:
        return "\n".join(parts)[:60000]
    try:
        return json.dumps(result, indent=2, default=str)[:60000]
    except Exception:
        return str(result)[:60000]


def _run_platformio_backend(action: str, config: dict) -> tuple:
    """Run the PlatformIO backend end-to-end and return (envelope, body). Mirrors the
    template-MCP path's shape so main() can hand off to the shared emit+trigger tail."""
    python_cmd = get_python_command()
    env = get_agent_env()
    core_dir = str(_cfg(config, "pio_core_dir")).strip() or _pio_default_core_dir()
    env["PLATFORMIO_CORE_DIR"] = core_dir
    timeout = float(_as_int(_cfg(config, "command_timeout", 900), 900))
    auto_bootstrap = _as_bool(_cfg(config, "auto_bootstrap", True), True)

    bootstrap_report = None
    boot_ok = True
    if action == "bootstrap":
        pio_cmd, bootstrap_report, boot_ok = _pio_bootstrap(config, env, core_dir, python_cmd)
    else:
        pio_cmd = _pio_resolve_cmd(config, env, core_dir, python_cmd)
        if not pio_cmd and auto_bootstrap:
            logging.info("🧰 Auto-bootstrap: PlatformIO Core not found — installing (shared with ESP32er)...")
            pio_cmd, bootstrap_report, boot_ok = _pio_bootstrap(config, env, core_dir, python_cmd)

    if action == "bootstrap":
        body = _pio_format_bootstrap_report(bootstrap_report)
        return ({"ok": bool(boot_ok), "tool": "bootstrap",
                 "result": {"ok": bool(boot_ok), "stage": "bootstrap",
                            "returncode": 0 if boot_ok else 1, "board": _resolve_board_id(config)}}, body)

    if action not in _PIO_ALL:
        valid = ", ".join(sorted(_PIO_ALL))
        body = f"Unknown PlatformIO action {action!r}. Valid actions: {valid}."
        logging.error(f"❌ {body}")
        return ({"ok": False, "tool": action, "result": {"ok": False, "error": body}}, body)

    if action == "validate":
        pf = _pio_preflight("validate", config, pio_cmd, env)
        body = _pio_format_preflight_report(pf)
        if bootstrap_report is not None:
            body = _pio_format_bootstrap_report(bootstrap_report) + "\n\n" + body
        return ({"ok": bool(pf["ok"]), "tool": "validate",
                 "result": {"ok": bool(pf["ok"]), "stage": "validate", "returncode": 0 if pf["ok"] else 1,
                            "board": pf.get("board", "")}}, body)

    preflight = None
    if _as_bool(_cfg(config, "preflight", True), True) and action not in _PIO_FILE:
        preflight = _pio_preflight(action, config, pio_cmd, env)
    if preflight is not None and not preflight["ok"]:
        body = ("PREFLIGHT REFUSED this operation (fail-safe — the environment could not be guaranteed "
                "correct):\n\n" + _pio_format_preflight_report(preflight))
        logging.error(f"❌ PlatformIO preflight refused {action}: {preflight['fatals']}")
        envelope = {"ok": False, "tool": action,
                    "result": {"ok": False, "error": "preflight refused", "stage": "preflight",
                               "board": preflight.get("board", "")}}
    else:
        logging.info(f"🔧 PlatformIO {action} board={_resolve_board_id(config) or '(none)'}")
        envelope = _pio_run_action(action, config, pio_cmd, env, timeout)
        body = _pio_result_body(envelope.get("result", {}))
        if preflight is not None and preflight.get("warnings"):
            body = ("[preflight OK — warnings: " + " | ".join(preflight["warnings"]) + "]\n\n") + body

    if bootstrap_report is not None:
        body = _pio_bootstrap_note(bootstrap_report, boot_ok) + body
    return (envelope, body)


# ========================================
# SHARED EMIT + DOWNSTREAM TRIGGER (both backends)
# ========================================

def _emit_and_trigger(action: str, envelope: dict, body: str, resolved_server: str,
                      config: dict, target_agents: list, backend: str) -> None:
    """Shared tail for BOTH backends: build the FIXED-schema KV header (keep aligned
    with agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['stm32er']), emit the
    INI_SECTION_STM32ER block, then ALWAYS trigger downstream agents (success OR
    failure) so a Forker/Raiser can branch on {success}/{returncode}."""
    result = envelope.get("result", {}) if isinstance(envelope.get("result"), dict) else {}
    project_dir = str(result.get("project_dir", "")) or str(_cfg(config, "project_dir", ""))
    session_id = (
        str(envelope.get("session_id", "")) or str(result.get("session_id", ""))
        or str(_cfg(config, "session_id", ""))
    )
    board = str(result.get("board", "")) or _resolve_board_id(config) or str(_cfg(config, "device", ""))
    port = str(result.get("port", "")) or str(_cfg(config, "port", ""))
    outcome = {
        "action": action,
        "tool": envelope.get("tool", action),
        "ok": "true" if envelope.get("ok") else "false",
        "returncode": result.get("returncode", ""),
        "success": "true" if envelope.get("ok") else "false",
        "backend": backend,
        "project_dir": project_dir,
        "board": board,
        "port": port,
        "session_id": session_id,
        "stage": result.get("stage", ""),
        "server_script": resolved_server,
    }
    _emit_section(outcome, body or "(no output)")

    if envelope.get("ok"):
        logging.info(f"🏁 STM32er {action} complete (backend={backend}): success=true")
    else:
        logging.warning(f"⚠️ STM32er {action} did not succeed (backend={backend}). {result.get('error', '')}")

    total_triggered = 0
    if target_agents:
        wait_for_agents_to_stop(target_agents)
        logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
        for target in target_agents:
            if start_agent(target):
                total_triggered += 1
    logging.info(f"🏁 STM32er agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")


# ========================================
# MAIN
# ========================================


def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    client = None
    try:
        target_agents = config.get('target_agents', []) or []
        action = str(_cfg(config, 'action', 'get_config') or 'get_config').strip()
        explicit_server = str(_cfg(config, 'server_script')).strip()
        auto_bootstrap = _as_bool(_cfg(config, 'auto_bootstrap', True), True)

        logging.info("⚡ STM32er AGENT STARTED (dual backend: template MCP + PlatformIO)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets: {target_agents}")

        # ── Backend dispatch (Phase 0/1) ──────────────────────────────────────
        # Route to the PlatformIO backend for the Blue Pill and every non-F407 part
        # (spanning the mainstream ST line); the legacy template-MCP path below
        # handles F407 / blank EXACTLY as before (zero regression). The PlatformIO
        # backend is fully self-contained and shares the emit + downstream-trigger
        # tail via _emit_and_trigger, so it needs none of the MCP resolution below.
        backend = _resolve_stm32_backend(config, action)
        logging.info(f"Backend: {backend}")
        if backend == "platformio":
            pio_envelope, pio_body = _run_platformio_backend(action, config)
            _emit_and_trigger(action, pio_envelope, pio_body, "", config, target_agents, "platformio")
            return

        # ── Build the server launch command + environment up front: BOTH the
        #    bootstrap installer (git/pip) and the MCP client need them. ──
        mcp_python = str(_cfg(config, "mcp_python")).strip()
        python_cmd = [mcp_python] if mcp_python else get_python_command()
        env = get_agent_env()
        env_template_dir = str(_cfg(config, "template_dir")).strip()
        env_ide_root = str(_cfg(config, "ide_root")).strip()
        if env_template_dir:
            env["STM32_TEMPLATE_DIR"] = env_template_dir
        if env_ide_root:
            env["STM32_IDE_ROOT"] = env_ide_root

        # ── Resolve the MCP server script, AUTO-BOOTSTRAPPING the STM32 MCP
        #    project (download/update + pip deps + validate) when needed, so the
        #    end user only installs STM32CubeIDE + Tlamatini and nothing else. An
        #    explicit, on-disk server_script still wins (and skips bootstrap)
        #    unless the action IS 'bootstrap' (an explicit re-install/update). ──
        bootstrap_report = None
        boot_ok = True
        resolved_server = ""
        if explicit_server and os.path.exists(explicit_server) and action != "bootstrap":
            resolved_server = explicit_server
            logging.info(f"Using configured server_script: {resolved_server}")
        elif auto_bootstrap or action == "bootstrap":
            logging.info("🧰 Auto-bootstrap: ensuring the STM32 MCP server is downloaded + installed...")
            resolved_server, bootstrap_report, boot_ok = _bootstrap_mcp(config, python_cmd, env)
        else:
            resolved_server = explicit_server

        # Resolve the body/outcome up front so EVERY exit path emits a section.
        envelope: dict = {"ok": False, "tool": action, "result": {}}
        body = ""

        if action == "bootstrap":
            # Setup-only run: report what the installer did; no MCP tool call.
            body = _format_bootstrap_report(bootstrap_report)
            envelope = {
                "ok": bool(boot_ok), "tool": "bootstrap",
                "result": {
                    "ok": bool(boot_ok), "stage": "bootstrap",
                    "returncode": 0 if boot_ok else 1,
                    "install_dir": (bootstrap_report or {}).get("install_dir", ""),
                },
            }
        elif action not in _ALL_ACTIONS:
            valid = ", ".join(sorted(_ALL_ACTIONS))
            body = f"Unknown action {action!r}. Valid actions: {valid}."
            logging.error(f"❌ {body}")
            envelope["result"] = {"ok": False, "error": body}
        elif not resolved_server or not os.path.exists(resolved_server):
            if bootstrap_report is not None and not boot_ok:
                body = ("STM32 MCP server could not be auto-installed.\n\n"
                        + _format_bootstrap_report(bootstrap_report))
            else:
                body = (
                    f"MCP server script not found: {resolved_server!r}. Either set `server_script` "
                    f"to STM32TemplateProjectMCP/mcp/stm32_mcp_server.py, or leave it blank with "
                    f"`auto_bootstrap: true` so STM32er downloads it from "
                    f"{str(_cfg(config, 'mcp_repo_url', _DEFAULT_MCP_REPO_URL))} automatically."
                )
            logging.error(f"❌ {body}")
            envelope["result"] = {"ok": False, "error": body, "stage": "bootstrap"}
        elif bootstrap_report is not None and not boot_ok:
            body = ("STM32 MCP environment is not ready (the server exists but its Python deps "
                    "are missing). Bootstrap report:\n\n" + _format_bootstrap_report(bootstrap_report))
            logging.error(f"❌ {body}")
            envelope["result"] = {"ok": False, "error": "bootstrap incomplete", "stage": "bootstrap"}
        else:
            subject = _subject_for(action, config)
            logging.info(f"Subject: {subject!r}")
            server_cwd = os.path.dirname(os.path.abspath(resolved_server))
            startup_timeout = _as_float(_cfg(config, "startup_timeout", 30), 30.0)
            call_timeout = _as_float(_cfg(config, "call_timeout", 600), 600.0)

            client = _McpStdioClient(
                python_cmd=python_cmd, server_script=resolved_server, env=env, cwd=server_cwd,
                startup_timeout=startup_timeout, call_timeout=call_timeout,
            )
            try:
                client.start()
                client.initialize()
                if action == "validate":
                    # Diagnostic-only: full environment preflight, no build/flash.
                    pf = _preflight(client, "validate", config, env)
                    body = _format_preflight_report(pf)
                    envelope = {
                        "ok": bool(pf["ok"]), "tool": "validate",
                        "result": {"ok": bool(pf["ok"]), "stage": "validate",
                                   "returncode": 0 if pf["ok"] else 1},
                    }
                else:
                    preflight = None
                    if _as_bool(_cfg(config, "preflight", True), True):
                        preflight = _preflight(client, action, config, env)
                    if preflight is not None and not preflight["ok"]:
                        # FAIL-SAFE: do NOT run the operation; report exactly why.
                        body = ("PREFLIGHT REFUSED this operation (fail-safe — the environment could "
                                "not be guaranteed correct):\n\n" + _format_preflight_report(preflight))
                        logging.error(f"❌ Preflight refused {action}: {preflight['fatals']}")
                        envelope = {"ok": False, "tool": action,
                                    "result": {"ok": False, "error": "preflight refused", "stage": "preflight"}}
                    else:
                        envelope = _run_action(client, action, config)
                        result = envelope.get("result", {})
                        body = _result_body(action, result, envelope.get("results"))
                        if preflight is not None and preflight.get("warnings"):
                            body = ("[preflight OK — warnings: "
                                    + " | ".join(preflight["warnings"]) + "]\n\n") + body
            except RuntimeError as e:
                body = str(e)
                logging.error(f"❌ {body}")
                envelope = {"ok": False, "tool": action, "result": {"ok": False, "error": body}}

            # Prepend a one-line bootstrap note when the installer ran this turn.
            if bootstrap_report is not None:
                body = _bootstrap_note(bootstrap_report, boot_ok) + body

        # ── Emit the section + ALWAYS trigger downstream (shared with the pio path) ──
        _emit_and_trigger(action, envelope, body, resolved_server, config, target_agents, "template_mcp")
    finally:
        if client is not None:
            client.close()
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
