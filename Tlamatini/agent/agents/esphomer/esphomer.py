# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# ESPHomer Agent - ESPHome (esphome CLI) bridge (device YAML author/validate/compile/upload/observe)
# Action: Triggered by upstream -> resolve the `esphome` executable (auto-bootstrapping
#         ESPHome via pip when absent) -> run ONE capability (selected by `action`)
#         as a direct `esphome` subprocess (or a stdlib op) -> capture stdout/stderr ->
#         emit INI_SECTION_ESPHOMER -> ALWAYS trigger downstream (success OR failure).
#
# ESPHomer is Tlamatini's integration of ESPHome (https://esphome.io) — the system
# that turns ESP32 / ESP8266 / RP2040 / BK72xx boards into smart-home devices from a
# SIMPLE YAML config (NO C++). Like ESP32er (PlatformIO) and Arduiner (arduino-cli),
# and UNLIKE STM32er (which needs a separate MCP server), ESPHome ships a complete
# command-line interface (`esphome`) covering config validation, compile, upload (over
# USB-serial OR OTA), log streaming and clean. So ESPHomer needs NO MCP server: it
# invokes `esphome` subcommands DIRECTLY (the ESP32er / Kalier / Executer pattern),
# capturing each command's stdout/stderr. It is fully self-contained (stdlib only:
# subprocess + urllib + json + threading + glob) — exactly like ESP32er / Kalier — so
# it works identically in source and frozen builds and never imports from agent.* (the
# agent pool runs as standalone Python subprocesses with no path back into Django).
#
# ZERO-CONFIG: with no on-disk `esphome_executable` and `auto_bootstrap: true`,
# ESPHomer INSTALLS ESPHome itself (`pip install --target`) into a per-user library
# dir OUTSIDE the install tree (%LOCALAPPDATA%/Tlamatini/esphome-lib), run via
# `python -m esphome` with that dir on PYTHONPATH — the same per-user pattern as
# ESP32er (PlatformIO core dir) / Arduiner (arduino-cli dir), so it SURVIVES a
# self-update (which replaces the carried Python) and works even in a read-only
# install. The end user installs only the board USB driver + Tlamatini.
# (ESPHome itself vendors PlatformIO + the toolchains it needs at first compile.)
#
# ESPHome's `run`/`logs` stream serial/OTA output interactively; the bounded `logs`
# action Popens the log stream, drains its stdout for `monitor_seconds` and then
# terminates it, so a continuous stream is usable end-to-end in one run. Because the
# interactive `wizard` cannot run headless, ESPHomer ships a built-in `new_config`
# generator that writes a minimal, valid device YAML from a few parameters.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core and inherited by every
# spawned agent via get_agent_env's os.environ.copy()) so every temp file this
# agent writes — including the downloaded installer, if any — lands under
# <app>/Temp, never C:\Temp / %TEMP% / the OS default. Fail-open: when the handle
# is unset (agent launched fully standalone) Python's default is used.
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
import glob
import json
import time
import yaml
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
# HELPER FUNCTIONS (from esp32er.py / kalier.py / shoter.py boilerplate — copy verbatim)
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


# NOTE: the parameters below are intentionally named ``raw`` (not ``value``) so the
# wrapped-runtime's static "required config key" analyzer does not treat a generic
# ``if not value`` as evidence that a config key named ``value`` is mandatory.
def _as_int(raw, default: int) -> int:
    try:
        if isinstance(raw, bool):
            return default
        return int(str(raw).strip())
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
# ACTION CONTRACT  (each action maps to ONE `esphome` subcommand, or a stdlib op)
# ========================================

# Meta actions handled by ESPHomer ITSELF (install / validate the ESPHome env).
_META_ACTIONS = {"bootstrap", "validate", "version"}

# Pure-stdlib config-file ops (no `esphome` invocation, no board).
_FILE_ACTIONS = {"write_config", "read_config", "new_config", "list_artifacts"}

# Build-class actions: need `esphome` + a device YAML, but NO hardware.
# ``scaffold_compile_upload`` is the one-call lifecycle COMPOSITE (new/write ->
# validate -> compile -> upload-if-port -> optional logs). It lives in
# _BUILD_ACTIONS — not _HARDWARE_ACTIONS — on purpose: it can create the config
# itself (so it must NOT be refused for "no config") and it gates the upload leg
# INTERNALLY on a port probe (so a missing board does not refuse the whole
# scaffold+compile). One Multi-Turn tool call replaces the multi-round chain.
_BUILD_ACTIONS = {"config", "compile", "clean", "scaffold_compile_upload"}

# Upload actions: ALSO require a connected serial port (or an OTA host in `port`).
_UPLOAD_ACTIONS = {"upload", "run"}

# Log actions: bounded `esphome logs` — ALSO require a serial port / OTA host.
_LOG_ACTIONS = {"logs"}

# Anything that touches a physically connected board (or OTA target).
_HARDWARE_ACTIONS = _UPLOAD_ACTIONS | _LOG_ACTIONS

_ALL_ACTIONS = (
    _META_ACTIONS | _FILE_ACTIONS | _BUILD_ACTIONS | _UPLOAD_ACTIONS | _LOG_ACTIONS
)

# USB Vendor IDs commonly seen on ESP / ESPHome dev boards (CP210x / CH34x / FTDI /
# native USB-Serial-JTAG). Used by the preflight to upgrade a generic "a port
# exists" into a confident "an ESP-style adapter is present" — a miss only
# DOWNGRADES to a warning, never refuses, because plenty of boards use other bridges.
_ESP_USB_VIDS = ("10C4", "1A86", "0403", "303A", "067B", "1A86")


def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 1200.0):
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


# ========================================
# ESPHOME RESOLUTION + AUTO-BOOTSTRAP (zero-config installer)
# ========================================

def _esphome_version(esphome_cmd: list, env: dict) -> tuple:
    """Return (ok, version_text). `esphome version` rc 0 means ESPHome is usable."""
    rc, out, err = _run_cmd(list(esphome_cmd) + ["version"], env=env, timeout=120)
    text = (out or err or "").strip()
    return rc == 0, text


def _esphome_lib_dir() -> str:
    """Per-user, writable dir that holds the pip-installed ESPHome + its deps.

    Lives OUTSIDE the Tlamatini install tree — exactly like ESP32er's PlatformIO
    core dir and Arduiner's arduino-cli dir — at %LOCALAPPDATA%/Tlamatini/esphome-lib
    on Windows. Two reasons this matters in a FROZEN build:
      * the install tree may be read-only (e.g. Program Files), so pip-installing
        into the CARRIED Python (<install>/python) would fail — this dir is always
        user-writable;
      * self-update replaces <install>/python wholesale, so anything installed INTO
        the carried Python is wiped on every update — this dir SURVIVES.
    ESPHome is invoked as `<python> -m esphome` with this dir on PYTHONPATH."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "esphome-lib")


def _env_with_esphome_lib(env: dict) -> dict:
    """Return a copy of *env* with the ESPHome lib dir PREPENDED to PYTHONPATH so
    `<python> -m esphome` (and the PlatformIO it shells out to) resolves the
    --target-installed ESPHome + deps ahead of the carried site-packages."""
    e = dict(env)
    lib = _esphome_lib_dir()
    existing = e.get("PYTHONPATH", "")
    e["PYTHONPATH"] = lib + (os.pathsep + existing if existing else "")
    return e


def _resolve_esphome_cmd(config: dict, env: dict, python_cmd: list) -> list:
    """Best-effort resolution of an invocable `esphome` command WITHOUT installing:
       1. explicit config `esphome_executable` if it exists,
       2. bare `esphome` on PATH,
       3. `<python> -m esphome` (works when ESPHome was pip-installed).
    Returns the first candidate whose `version` succeeds, else []."""
    candidates = []
    explicit = str(_cfg(config, "esphome_executable")).strip()
    if explicit:
        candidates.append([explicit])
    candidates.append(["esphome"])
    candidates.append(list(python_cmd) + ["-m", "esphome"])
    for cand in candidates:
        ok, _ver = _esphome_version(cand, env)
        if ok:
            return cand
    return []


def _bootstrap_esphome(config: dict, env: dict, python_cmd: list) -> tuple:
    """Ensure an invocable `esphome` exists, installing ESPHome (pip) if needed.
    Returns (esphome_cmd, report, ok). Never raises into main()."""
    report = {"steps": []}
    try:
        do_update = _as_bool(_cfg(config, "auto_update", False), False)
        do_pip = _as_bool(_cfg(config, "pip_install", True), True)

        # Already usable? (and not asked to refresh)
        existing = _resolve_esphome_cmd(config, env, python_cmd)
        if existing and not do_update:
            ok, ver = _esphome_version(existing, env)
            report["steps"].append(("resolve", {"ok": ok, "action": "present", "esphome": existing, "version": ver}))
            report["ok"] = ok
            return existing, report, ok

        # ── Install / upgrade path: pip install esphome ──
        if do_pip:
            # Install into a per-user lib dir OUTSIDE the install tree (survives
            # self-update + works in a read-only install) — NOT into the carried
            # Python. Resolved later via `<python> -m esphome` with that dir on
            # PYTHONPATH (the env passed in already carries it). See _esphome_lib_dir.
            lib_dir = _esphome_lib_dir()
            os.makedirs(lib_dir, exist_ok=True)
            pip_cmd = list(python_cmd) + ["-m", "pip", "install",
                                          "--disable-pip-version-check",
                                          "--target", lib_dir]
            pip_cmd += (["--upgrade", "esphome"] if do_update else ["esphome"])
            logging.info(f"📦 Installing ESPHome via pip into {lib_dir}: {pip_cmd}")
            rc, out, err = _run_cmd(pip_cmd, env=env, timeout=1800)
            report["steps"].append(("pip-install",
                                    {"ok": rc == 0, "action": "pip", "returncode": rc,
                                     "stderr": (err or "")[-800:]}))
        else:
            report["steps"].append(("pip-install",
                                    {"ok": False, "action": "disabled",
                                     "error": "pip_install is false and esphome is not resolvable."}))

        resolved = _resolve_esphome_cmd(config, env, python_cmd)
        ok, ver = (_esphome_version(resolved, env) if resolved else (False, ""))
        report["steps"].append(("validate", {"ok": ok, "version": ver, "esphome": resolved}))
        report["ok"] = ok
        return resolved, report, ok
    except Exception as e:  # pragma: no cover - bootstrap must NEVER raise into main()
        logging.error(f"❌ bootstrap crashed: {e}")
        report["ok"] = False
        report["error"] = str(e)
        return [], report, False


def _format_bootstrap_report(report: dict) -> str:
    if not report:
        return "No bootstrap was performed."
    lines = [
        f"overall  : {'OK' if report.get('ok') else 'FAILED'}",
        "",
    ]
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


def _bootstrap_note(report: dict, ok: bool) -> str:
    if not report:
        return ""
    last_install = next((res for name, res in report.get("steps", [])
                         if name in ("pip-install",)), {})
    action = last_install.get("action", "present")
    return f"[bootstrap: {action} · ready={'yes' if ok else 'NO'}]\n\n"


# ========================================
# SAFETY PREFLIGHT (fail-safe environment gate)
# ========================================

def _config_dir(config_path: str) -> str:
    return os.path.dirname(os.path.abspath(config_path)) if config_path else ""


def _is_ota_target(port: str) -> bool:
    """A `port` that looks like a hostname / IP (contains a dot or colon, and is not
    a COM/tty device) is treated as an OTA upload target — no serial port needed."""
    p = (port or "").strip()
    if not p:
        return False
    low = p.lower()
    if low.startswith("com") or low.startswith("/dev/"):
        return False
    return ("." in p) or (":" in p)


def _enumerate_serial_ports() -> list:
    """Stdlib-only serial-port enumeration (no pyserial dependency):
       - Windows: HKLM\\HARDWARE\\DEVICEMAP\\SERIALCOMM,
       - POSIX:   /dev/ttyUSB* + /dev/ttyACM* (+ /dev/cu.* on macOS)."""
    ports = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                i = 0
                while True:
                    try:
                        _name, value, _type = winreg.EnumValue(key, i)
                        if value:
                            ports.append(str(value))
                        i += 1
                    except OSError:
                        break
        except (FileNotFoundError, OSError):
            pass
    else:
        for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/cu.*", "/dev/tty.usb*"):
            ports.extend(sorted(glob.glob(pattern)))
    return ports


def _probe_serial(config: dict) -> dict:
    """Probe for a connected serial port (stdlib enumeration). Distinguishes: a port
    present, no port, and an OTA target supplied via `port`. ESP-style VID matching
    is best-effort (Windows hides the VID here) so it only ever DOWNGRADES to a hint."""
    result = {"present": False, "esp_like": False, "ota": False, "ports": [], "detail": ""}
    port = str(_cfg(config, "port")).strip()
    if _is_ota_target(port):
        result["ota"] = True
        result["present"] = True
        result["detail"] = f"OTA target '{port}' (over-the-air upload — no USB serial needed)."
        return result
    ports = _enumerate_serial_ports()
    result["ports"] = ports
    result["present"] = bool(ports)
    result["detail"] = f"{len(ports)} port(s): {', '.join(ports)}" if ports else "no serial ports enumerated"
    return result


def _config_node_platform(config_path: str) -> str:
    """Best-effort read of the target platform (esp32 / esp8266 / rp2040 / bk72xx)
    from a device YAML — used to WARN, never refuse."""
    if not config_path or not os.path.exists(config_path):
        return ""
    try:
        with open(config_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return ""
    for plat in ("esp32", "esp8266", "rp2040", "bk72xx", "rtl87xx", "nrf52", "host"):
        if re.search(rf"(?m)^\s*{plat}\s*:", text):
            return plat
    return ""


def _preflight(action: str, config: dict, esphome_cmd: list) -> dict:
    """Validate the environment for ``action`` and REFUSE (fail-safe) rather than run
    a compile/upload that cannot succeed. report['ok'] is False on any FATAL."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True}
    checks = report["checks"]

    esphome_ok = bool(esphome_cmd)
    checks["esphome_resolvable"] = esphome_ok

    config_path = str(_cfg(config, "config_path")).strip()
    needs_config = action in {"config", "compile", "clean", "list_artifacts"} | _HARDWARE_ACTIONS
    has_config = bool(config_path) and os.path.exists(config_path)
    if needs_config:
        checks["device_yaml"] = has_config

    platform = _config_node_platform(config_path)
    if platform == "host":
        report["warnings"].append(
            "device YAML targets the 'host' platform (desktop) — no microcontroller will be flashed.")

    needs_hardware = action in _HARDWARE_ACTIONS
    report["requires_hardware"] = needs_hardware
    if (needs_hardware or action == "validate"):
        serial = _probe_serial(config)
        report["serial"] = serial
        checks["serial_port_present"] = serial["present"]

    # ── FATAL gating ──
    fatals = report["fatals"]
    if action not in ("bootstrap", "version") and not esphome_ok:
        fatals.append(
            "ESPHome (`esphome`) is NOT resolvable. Leave esphome_executable blank with "
            "auto_bootstrap: true so ESPHomer pip-installs it, or set esphome_executable to an existing esphome.")
    if needs_config and not has_config:
        if not config_path:
            fatals.append(
                f"action '{action}' needs a device YAML — set config_path to an ESPHome .yaml "
                f"(use action='new_config' or 'write_config' first).")
        else:
            fatals.append(
                f"No device YAML found at {config_path!r}. Run action='new_config' or 'write_config' there first.")
    if needs_hardware and esphome_ok:
        serial = report.get("serial", {})
        if not serial.get("present"):
            fatals.append(
                "No serial port detected and no OTA host given — connect the board over USB "
                "(check the cable / driver) or pass port='<device-ip>' for an OTA upload. "
                "(Compile-only actions like 'compile' do NOT need a board.)")

    report["ok"] = not fatals
    return report


def _format_preflight_report(report: dict) -> str:
    if not report:
        return "No preflight was performed."
    lines = [
        f"action            : {report.get('action', '')}",
        f"requires_hardware : {report.get('requires_hardware', False)}",
        f"overall           : {'READY' if report.get('ok') else 'REFUSED (fail-safe)'}",
        "",
        "checks:",
    ]
    for name, value in report.get("checks", {}).items():
        lines.append(f"  [{'OK' if value else 'XX'}] {name}: {value}")
    if report.get("serial"):
        s = report["serial"]
        lines.append(f"  serial          : present={s.get('present')} ota={s.get('ota')} "
                     f"({s.get('detail', '')})")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ========================================
# ACTION EXECUTION
# ========================================

# A minimal, valid ESPHome device YAML template. {placeholders} are filled by
# _new_config. It exposes a single GPIO light + the API/OTA/logger blocks so a
# freshly generated device is immediately controllable from a smart-home hub.
_DEVICE_YAML_TEMPLATE = """\
esphome:
  name: {name}

{platform_block}

logger:

# Native API — lets a smart-home hub (e.g. Home Assistant) discover and control this device.
api:

# Over-the-air updates — push new firmware over WiFi after the first USB flash.
ota:
  - platform: esphome

wifi:
  ssid: "{wifi_ssid}"
  password: "{wifi_password}"

# A switchable light on {led_pin}. Toggle it from your phone via the hub.
output:
  - platform: gpio
    pin: {led_pin}
    id: light_output

light:
  - platform: binary
    name: "{friendly} Light"
    output: light_output
"""

_PLATFORM_BLOCKS = {
    "esp32": "esp32:\n  board: {board}\n  framework:\n    type: arduino",
    "esp8266": "esp8266:\n  board: {board}",
    "rp2040": "rp2040:\n  board: {board}",
    "bk72xx": "bk72xx:\n  board: {board}",
}

_PLATFORM_DEFAULT_BOARDS = {
    "esp32": "esp32dev",
    "esp8266": "d1_mini",
    "rp2040": "rpipicow",
    "bk72xx": "generic-bk7231n-qfn32-tuya",
}

_PLATFORM_DEFAULT_LED = {
    "esp32": "GPIO2",
    "esp8266": "GPIO2",
    "rp2040": "GPIO25",
    "bk72xx": "P26",
}


def _slug(text: str) -> str:
    """ESPHome node names must be lowercase a-z0-9 and hyphens."""
    s = re.sub(r"[^a-z0-9\-]+", "-", (text or "").strip().lower()).strip("-")
    return s or "tlamatini-device"


def _templates_root() -> str:
    """Default scaffold parent for a generated device YAML: ``<app>/Templates``.

    Resolved from ``TLAMATINI_TEMPLATES`` — exported by the Tlamatini core and
    inherited by every spawned agent via ``get_agent_env``'s ``os.environ.copy()``
    (the same handle ESP32er / Arduiner scaffolds live under). This keeps a
    generated device — and the ``.esphome/build`` tree ESPHome writes beside it —
    in the one predictable deliverable location in BOTH source and frozen runs,
    instead of deep inside the (possibly read-only) install tree at ``os.getcwd()``.
    Fail-open to the cwd when the handle is unset (agent launched fully standalone)."""
    root = (os.environ.get("TLAMATINI_TEMPLATES") or "").strip()
    if root:
        try:
            os.makedirs(root, exist_ok=True)
            return root
        except Exception:
            pass
    return os.getcwd()


def _new_config(config: dict) -> dict:
    """Generate a minimal, valid ESPHome device YAML from a few parameters (the
    headless replacement for the interactive `esphome wizard`)."""
    config_path = str(_cfg(config, "config_path")).strip()
    name = _slug(str(_cfg(config, "name")) or "tlamatini-light")
    platform = str(_cfg(config, "platform", "esp32")).strip().lower() or "esp32"
    if platform not in _PLATFORM_BLOCKS:
        return {"ok": False, "error": f"platform {platform!r} not supported. "
                f"Use one of: {', '.join(sorted(_PLATFORM_BLOCKS))}."}
    board = str(_cfg(config, "board")).strip() or _PLATFORM_DEFAULT_BOARDS[platform]
    led_pin = str(_cfg(config, "led_pin")).strip() or _PLATFORM_DEFAULT_LED[platform]
    wifi_ssid = str(_cfg(config, "wifi_ssid")).strip() or "YOUR_WIFI_SSID"
    wifi_password = str(_cfg(config, "wifi_password")).strip() or "YOUR_WIFI_PASSWORD"
    friendly = name.replace("-", " ").title()

    platform_block = _PLATFORM_BLOCKS[platform].format(board=board)
    body = _DEVICE_YAML_TEMPLATE.format(
        name=name, platform_block=platform_block, wifi_ssid=wifi_ssid,
        wifi_password=wifi_password, led_pin=led_pin, friendly=friendly,
    )

    if not config_path:
        # No explicit path: scaffold under <app>/Templates/<node>/ (the deliverable
        # location) rather than os.getcwd() — the pool dir, which sits inside the
        # possibly read-only install tree in a frozen build. See _templates_root().
        config_path = os.path.join(_templates_root(), name, f"{name}.yaml")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(body)
        return {"ok": True, "returncode": 0, "config_path": config_path, "name": name,
                "stdout": f"Generated ESPHome device YAML ({platform}/{board}) at {config_path}\n\n{body}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "config_path": config_path}


def _write_config(config: dict) -> dict:
    config_path = str(_cfg(config, "config_path")).strip()
    content = str(_cfg(config, "content"))
    if not config_path:
        return {"ok": False, "error": "write_config needs config_path (a path to the device .yaml)."}
    if not content.strip():
        return {"ok": False, "error": "write_config needs content (the full device YAML)."}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "returncode": 0, "config_path": config_path,
                "stdout": f"Wrote {len(content)} chars to {config_path}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "config_path": config_path}


def _read_config(config: dict) -> dict:
    config_path = str(_cfg(config, "config_path")).strip()
    if not config_path:
        return {"ok": False, "error": "read_config needs config_path."}
    try:
        with open(config_path, "r", encoding="utf-8", errors="replace") as f:
            return {"ok": True, "returncode": 0, "config_path": config_path, "stdout": f.read()}
    except Exception as e:
        return {"ok": False, "error": str(e), "config_path": config_path}


def _list_artifacts(config: dict) -> dict:
    """Enumerate firmware artifacts under <config_dir>/.esphome/build/<node>/ (ESPHome
    writes firmware.bin/.elf into a PlatformIO build tree below .esphome)."""
    config_path = str(_cfg(config, "config_path")).strip()
    build_root = os.path.join(_config_dir(config_path), ".esphome", "build")
    if not os.path.isdir(build_root):
        return {"ok": False, "error": f"No build output at {build_root} — run action='compile' first."}
    artifacts = []
    for dirpath, _dirs, files in os.walk(build_root):
        for name in files:
            if name.startswith("firmware.") or name.endswith((".elf", ".bin", ".factory.bin")):
                artifacts.append(os.path.join(dirpath, name))
    return {"ok": bool(artifacts), "returncode": 0 if artifacts else 1,
            "stdout": "\n".join(artifacts) or "(no firmware artifacts found)"}


def _device_args(config: dict) -> list:
    """The `--device <port|host>` argument for upload/logs/run ('' = esphome auto)."""
    port = str(_cfg(config, "port")).strip()
    return ["--device", port] if port else []


def _esphome(args: list, esphome_cmd: list, env: dict, timeout: float, cwd: str = None) -> dict:
    """Run `esphome <args>` and normalize to {ok, returncode, stdout, stderr}."""
    rc, out, err = _run_cmd(list(esphome_cmd) + list(args), env=env, timeout=timeout, cwd=cwd)
    return {"ok": rc == 0, "returncode": rc, "stdout": out, "stderr": err}


def _bounded_logs(esphome_cmd: list, config: dict, env: dict) -> dict:
    """Run `esphome logs <config>` for monitor_seconds, draining its stdout, then
    terminate it — making a normally-interactive stream usable in one run."""
    seconds = max(1, _as_int(_cfg(config, "monitor_seconds", 10), 10))
    config_path = str(_cfg(config, "config_path")).strip()
    args = list(esphome_cmd) + ["logs", config_path] + _device_args(config)

    logging.info(f"📟 Streaming logs for {seconds}s: {args}")
    collected: list = []
    proc = None
    try:
        proc = subprocess.Popen(
            args, cwd=_config_dir(config_path) or None,
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except Exception as e:
        return {"ok": False, "error": f"could not start logs: {e}", "returncode": 127}

    def _drain():
        try:
            for line in proc.stdout:
                if line:
                    collected.append(line.rstrip("\n"))
                    if len(collected) > 5000:
                        del collected[:2500]
        except Exception:
            pass

    reader = threading.Thread(target=_drain, daemon=True, name="esphome-logs")
    reader.start()
    time.sleep(seconds)
    _terminate_proc(proc)
    reader.join(timeout=2)

    text = "\n".join(collected)
    port = str(_cfg(config, "port")).strip()
    return {
        "ok": True, "returncode": 0, "port": port or "(auto)", "monitor_seconds": seconds,
        "stdout": text or "(no log output captured during the window)",
    }


def _terminate_proc(proc) -> None:
    """Terminate a process (and its tree if psutil is available), then kill."""
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


def _scaffold_compile_upload(config: dict, esphome_cmd: list, env: dict, timeout: float) -> dict:
    """One-call device lifecycle: new_config/write_config (author the YAML) ->
    config (validate) -> compile -> upload (only when a port/OTA host is present) ->
    optional bounded logs (when monitor_seconds > 0).

    Collapses what is otherwise a multi-round Multi-Turn chain into a SINGLE run.
    Fail-safe: a missing board does NOT abort — the YAML is authored, validated and
    compiled, and the result reports "compiled OK, upload skipped" so a downstream
    Forker can branch on {success}. Any failing stage short-circuits with its `stage`.
    """
    config_path = str(_cfg(config, "config_path")).strip()
    stage_logs: list = []

    def _section(title: str, res: dict) -> None:
        out = (res.get("stdout") or "") if isinstance(res, dict) else ""
        err = (res.get("stderr") or "") if isinstance(res, dict) else ""
        body = "\n".join(p for p in (out, err) if p).strip()
        stage_logs.append(f"===== {title} =====\n{body or '(no output)'}")

    def _envelope(tool: str, ok: bool, stage: str, rc, extra: dict = None) -> dict:
        result = {"ok": ok, "returncode": rc, "stage": stage,
                  "config_path": config_path, "stdout": "\n\n".join(stage_logs)}
        if extra:
            result.update(extra)
        return {"ok": ok, "tool": tool, "result": result}

    # 1. Ensure a device YAML exists: prefer explicit `content` (write_config),
    #    else generate one (new_config). Skip when config_path already exists.
    if config_path and os.path.exists(config_path) and not str(_cfg(config, "content")).strip():
        stage_logs.append(f"===== author =====\n(skipped — device YAML already present at {config_path})")
    elif str(_cfg(config, "content")).strip():
        ws = _write_config(config)
        _section("write_config", ws)
        if not _ok(ws):
            return _envelope("scaffold_compile_upload", False, "write_config", ws.get("returncode", 1))
        config_path = ws.get("config_path", config_path)
    else:
        nc = _new_config(config)
        _section("new_config", nc)
        if not _ok(nc):
            return _envelope("scaffold_compile_upload", False, "new_config", nc.get("returncode", 1))
        config_path = nc.get("config_path", config_path)
        config["config_path"] = config_path

    # 2. Validate the config.
    cf = _esphome(["config", config_path], esphome_cmd, env, timeout, cwd=_config_dir(config_path))
    _section("config", cf)
    if not _ok(cf):
        return _envelope("scaffold_compile_upload", False, "config", cf.get("returncode", 1))

    # 3. Compile.
    cm = _esphome(["compile", config_path], esphome_cmd, env, timeout, cwd=_config_dir(config_path))
    _section("compile", cm)
    if not _ok(cm):
        return _envelope("scaffold_compile_upload", False, "compile", cm.get("returncode", 1))

    # 4. Upload only when a board / OTA target is present (fail-safe partial success).
    serial = _probe_serial(config)
    if not serial.get("present"):
        stage_logs.append(
            "===== upload =====\nSKIPPED — no serial port detected and no OTA host given. The "
            "config compiled successfully; connect the board over USB and run action='upload', or "
            "pass port='<device-ip>' for an OTA upload.")
        return _envelope("scaffold_compile_upload (upload skipped: no board)", True, "upload_skipped", 0)

    up = _esphome(["upload", config_path] + _device_args(config), esphome_cmd, env, timeout,
                  cwd=_config_dir(config_path))
    _section("upload", up)
    port = serial.get("ports", [""])[0] if serial.get("ports") else str(_cfg(config, "port"))
    if not _ok(up):
        return _envelope("scaffold_compile_upload", False, "upload", up.get("returncode", 1), {"port": port})

    # 5. Optional bounded logs to prove it runs (HIL) when monitor_seconds > 0.
    if _as_int(_cfg(config, "monitor_seconds", 0), 0) > 0:
        lg = _bounded_logs(esphome_cmd, config, env)
        _section("logs", lg)

    return _envelope("scaffold->config->compile->upload", True, "upload", up.get("returncode", 0), {"port": port})


def _run_action(action: str, config: dict, esphome_cmd: list, env: dict, timeout: float) -> dict:
    """Execute one action. Returns a normalized envelope {ok, tool, result}."""
    config_path = str(_cfg(config, "config_path")).strip()
    cwd = _config_dir(config_path) or None

    # ── one-call lifecycle composite (author -> validate -> compile -> upload -> logs) ──
    if action == "scaffold_compile_upload":
        return _scaffold_compile_upload(config, esphome_cmd, env, timeout)

    # ── stdlib-only config file ops ──
    if action == "new_config":
        return _wrap("new_config", _new_config(config))
    if action == "write_config":
        return _wrap("write_config", _write_config(config))
    if action == "read_config":
        return _wrap("read_config", _read_config(config))
    if action == "list_artifacts":
        return _wrap("list_artifacts", _list_artifacts(config))

    # ── bounded logs (interactive command made one-shot) ──
    if action == "logs":
        return _wrap("logs", _bounded_logs(esphome_cmd, config, env))

    # ── direct `esphome` subcommands ──
    if action == "version":
        return _wrap("version", _esphome(["version"], esphome_cmd, env, 120))
    if action == "config":
        return _wrap("config", _esphome(["config", config_path], esphome_cmd, env, timeout, cwd=cwd))
    if action == "compile":
        return _wrap("compile", _esphome(["compile", config_path], esphome_cmd, env, timeout, cwd=cwd))
    if action == "clean":
        return _wrap("clean", _esphome(["clean", config_path], esphome_cmd, env, timeout, cwd=cwd))
    if action == "upload":
        return _wrap("upload", _esphome(["upload", config_path] + _device_args(config),
                                        esphome_cmd, env, timeout, cwd=cwd))
    if action == "run":
        # `esphome run` compiles + uploads; it then tails logs interactively, so bound
        # the tail when monitor_seconds > 0 by doing upload first then a bounded logs read.
        up = _esphome(["upload", config_path] + _device_args(config), esphome_cmd, env, timeout, cwd=cwd)
        if not _ok(up) or _as_int(_cfg(config, "monitor_seconds", 0), 0) <= 0:
            return _wrap("run (upload)", up)
        lg = _bounded_logs(esphome_cmd, config, env)
        lg["upload_returncode"] = up.get("returncode")
        return _wrap("run (upload+logs)", lg)

    valid = ", ".join(sorted(_ALL_ACTIONS))
    return _wrap(action, {"ok": False, "error": f"Unknown action {action!r}. Valid actions: {valid}."})


def _wrap(tool: str, result: dict) -> dict:
    return {"ok": _ok(result), "tool": tool, "result": result}


def _ok(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if "ok" in result:
        return bool(result["ok"])
    return "error" not in result


# ========================================
# STRUCTURED OUTPUT (Parametrizer / KV-promotion contract)
# ========================================

def _result_body(result: dict) -> str:
    """Human-readable section body — prefer stdout/stderr, else pretty JSON."""
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


def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_ESPHOMER<<< block atomically (single logging.info call).

    Mirrors the ESP32er / STM32er / Kalier convention so this agent's structured
    output is consumable by the Multi-Turn LLM (wrapped chat-agent run-result KV
    promotion) AND the Parametrizer canvas pipeline (registered in
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['esphomer'] and
    parametrizer.SECTION_AGENT_TYPES). The KV header field names MUST stay aligned
    with that registration."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_ESPHOMER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_ESPHOMER")


# ========================================
# MAIN
# ========================================

def main():
    config = load_config()

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        action = str(_cfg(config, 'action', 'validate') or 'validate').strip()

        logging.info("🏠 ESPHomer AGENT STARTED (ESPHome / esphome CLI bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets: {target_agents}")

        python_cmd = get_python_command()
        # Put the per-user ESPHome lib dir on PYTHONPATH for EVERY esphome call
        # (resolve / version / config / compile / upload / logs), so `python -m
        # esphome` finds the --target-installed package. See _esphome_lib_dir.
        env = _env_with_esphome_lib(get_agent_env())
        timeout = float(_as_int(_cfg(config, "command_timeout", 1200), 1200))
        auto_bootstrap = _as_bool(_cfg(config, "auto_bootstrap", True), True)

        # ── Resolve `esphome`, AUTO-BOOTSTRAPPING ESPHome (pip) when needed ──
        bootstrap_report = None
        boot_ok = True
        if action == "bootstrap":
            esphome_cmd, bootstrap_report, boot_ok = _bootstrap_esphome(config, env, python_cmd)
        else:
            esphome_cmd = _resolve_esphome_cmd(config, env, python_cmd)
            # The pure-stdlib config-file ops never need the CLI; everything else may.
            if not esphome_cmd and auto_bootstrap and action not in _FILE_ACTIONS:
                logging.info("🧰 Auto-bootstrap: ESPHome not found — installing...")
                esphome_cmd, bootstrap_report, boot_ok = _bootstrap_esphome(config, env, python_cmd)

        envelope: dict = {"ok": False, "tool": action, "result": {}}
        body = ""

        if action == "bootstrap":
            body = _format_bootstrap_report(bootstrap_report)
            envelope = {"ok": bool(boot_ok), "tool": "bootstrap",
                        "result": {"ok": bool(boot_ok), "stage": "bootstrap",
                                   "returncode": 0 if boot_ok else 1}}
        elif action not in _ALL_ACTIONS:
            valid = ", ".join(sorted(_ALL_ACTIONS))
            body = f"Unknown action {action!r}. Valid actions: {valid}."
            logging.error(f"❌ {body}")
            envelope["result"] = {"ok": False, "error": body}
        elif action == "validate":
            pf = _preflight("validate", config, esphome_cmd)
            body = _format_preflight_report(pf)
            if bootstrap_report is not None:
                body = _format_bootstrap_report(bootstrap_report) + "\n\n" + body
            envelope = {"ok": bool(pf["ok"]), "tool": "validate",
                        "result": {"ok": bool(pf["ok"]), "stage": "validate",
                                   "returncode": 0 if pf["ok"] else 1}}
        else:
            # ── Safety preflight gate (skips the pure-stdlib file ops) ──
            preflight = None
            if _as_bool(_cfg(config, "preflight", True), True) and action not in _FILE_ACTIONS:
                preflight = _preflight(action, config, esphome_cmd)
            if preflight is not None and not preflight["ok"]:
                body = ("PREFLIGHT REFUSED this operation (fail-safe — the environment could not be "
                        "guaranteed correct):\n\n" + _format_preflight_report(preflight))
                logging.error(f"❌ Preflight refused {action}: {preflight['fatals']}")
                envelope = {"ok": False, "tool": action,
                            "result": {"ok": False, "error": "preflight refused", "stage": "preflight"}}
            else:
                subject = str(_cfg(config, "config_path") or _cfg(config, "name") or "(environment)")
                logging.info(f"Subject: {subject!r}")
                envelope = _run_action(action, config, esphome_cmd, env, timeout)
                body = _result_body(envelope.get("result", {}))
                if preflight is not None and preflight.get("warnings"):
                    body = ("[preflight OK — warnings: " + " | ".join(preflight["warnings"]) + "]\n\n") + body

            if bootstrap_report is not None:
                body = _bootstrap_note(bootstrap_report, boot_ok) + body

        # ── Build the KV header (FIXED schema — keep aligned with _PARAMETRIZER_OUTPUT_FIELDS) ──
        result = envelope.get("result", {}) if isinstance(envelope.get("result"), dict) else {}
        config_path = str(result.get("config_path", "")) or str(_cfg(config, "config_path", ""))
        name = str(result.get("name", "")) or str(_cfg(config, "name", ""))
        port = str(result.get("port", "")) or str(_cfg(config, "port", ""))
        outcome = {
            "action": action,
            "tool": envelope.get("tool", action),
            "ok": "true" if envelope.get("ok") else "false",
            "returncode": result.get("returncode", ""),
            "success": "true" if envelope.get("ok") else "false",
            "config_path": config_path,
            "name": name,
            "port": port,
            "stage": result.get("stage", ""),
        }
        _emit_section(outcome, body or "(no output)")

        if envelope.get("ok"):
            logging.info(f"🏁 ESPHomer {action} complete: success=true")
        else:
            logging.warning(f"⚠️ ESPHomer {action} did not succeed. {result.get('error', '')}")

        # Always trigger downstream agents regardless of success or failure, so a
        # downstream Forker / Raiser can branch on {success} / {returncode}.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 ESPHomer agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
