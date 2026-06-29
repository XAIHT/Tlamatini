# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# ESP32er Agent - PlatformIO Core (pio CLI) bridge (firmware scaffold/build/upload/monitor)
# Action: Triggered by upstream -> resolve the `pio` executable (auto-bootstrapping
#         PlatformIO Core when absent) -> run ONE capability (selected by `action`)
#         as a direct `pio` subprocess -> capture stdout/stderr -> emit
#         INI_SECTION_ESP32ER -> ALWAYS trigger downstream (success OR failure).
#
# ESP32er is Tlamatini's integration of PlatformIO Core (https://platformio.org).
# Unlike STM32er — which drives a separate FastMCP stdio server because STM32CubeIDE
# has no unified CLI — PlatformIO already SHIPS a complete command-line interface
# (`pio` / `platformio`) covering build, upload, serial monitor, debug, the board
# database, the package manager and static analysis. So ESP32er needs NO MCP server:
# it invokes `pio` subcommands DIRECTLY (the Kalier / Executer pattern), capturing
# each command's stdout/stderr. It is fully self-contained (stdlib only: subprocess
# + urllib + json + threading) — exactly like Kalier / ACPXer — so it works
# identically in source and frozen builds and never imports from agent.* (the agent
# pool runs as standalone Python subprocesses with no path back into the Django app).
#
# ZERO-CONFIG: with no on-disk `pio_executable` and `auto_bootstrap: true`, ESP32er
# DOWNLOADS PlatformIO Core itself — it fetches the official get-platformio.py
# installer and runs it into a per-user virtualenv (PLATFORMIO_CORE_DIR), with a
# `pip install platformio` fallback — so the end user installs only the board USB
# driver + Tlamatini and nothing else.
#
# `pio device monitor` and `pio debug` are interactive; the bounded `monitor` /
# `monitor_session` actions Popen the monitor, drain its stdout for `monitor_seconds`
# and then terminate it, so a continuous stream is usable end-to-end in one run.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core and inherited by every
# spawned agent via get_agent_env's os.environ.copy()) so every temp file this
# agent writes — including the downloaded get-platformio.py installer — lands
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
# HELPER FUNCTIONS (from stm32er.py / kalier.py / shoter.py boilerplate — copy verbatim)
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
# ACTION CONTRACT  (each action maps to ONE `pio` subcommand, or a stdlib op)
# ========================================

# Meta actions handled by ESP32er ITSELF (install / validate the PlatformIO env).
_META_ACTIONS = {"bootstrap", "validate"}

# Read-only informational actions — need `pio` but NO board / no platformio.ini.
_INFO_ACTIONS = {"system_info", "boards", "device_list", "pkg_list", "list_artifacts"}

# Pure-stdlib project file ops (no `pio` invocation, no board).
_FILE_ACTIONS = {"write_source", "read_source", "list_sources"}

# Build-class actions: need `pio` + a project (platformio.ini), but NO hardware.
# (The compiler toolchain auto-installs on the first `pio run`.)
# ``scaffold_build_upload`` is the one-call lifecycle COMPOSITE (create -> write ->
# build -> upload-if-board -> optional monitor). It lives here — not in
# _HARDWARE_ACTIONS — on purpose: it creates the project itself (so it must NOT be
# refused for "no platformio.ini") and it gates the upload leg INTERNALLY on a
# serial probe (so a missing board does not refuse the whole scaffold+build). This
# lets a single Multi-Turn tool call replace the 4-round-trip chain.
_BUILD_ACTIONS = {"build", "clean", "check", "test", "create_project", "pkg_install",
                  "pkg_update", "scaffold_build_upload"}

# Upload actions: ALSO require a connected serial port (esptool over USB — ESP32
# flashes over its onboard USB-serial bootloader, so NO external JTAG probe needed).
_UPLOAD_ACTIONS = {"upload", "build_and_upload"}

# Monitor actions: bounded `pio device monitor` — ALSO require a serial port.
_MONITOR_ACTIONS = {"monitor", "monitor_session"}

# Anything that touches a physically connected board.
_HARDWARE_ACTIONS = _UPLOAD_ACTIONS | _MONITOR_ACTIONS

_ALL_ACTIONS = (
    _META_ACTIONS | _INFO_ACTIONS | _FILE_ACTIONS
    | _BUILD_ACTIONS | _UPLOAD_ACTIONS | _MONITOR_ACTIONS
)

# USB Vendor IDs commonly seen on ESP32 dev boards (CP210x / CH34x / FTDI / native
# USB-Serial-JTAG). Used by the preflight to upgrade a generic "a port exists" into
# a confident "an ESP32-style adapter is present" — a miss only DOWNGRADES to a
# warning, never refuses, because plenty of boards use other bridges.
_ESP32_USB_VIDS = ("10C4", "1A86", "0403", "303A", "1A86", "067B")


def _installer_url() -> str:
    return "https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py"


def _default_core_dir() -> str:
    """A per-user, writable PlatformIO core dir (holds penv + toolchains). Works in
    source AND in a frozen 'Program Files' install (where the app dir is read-only)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "platformio")


def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 900.0):
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
# PLATFORMIO RESOLUTION + AUTO-BOOTSTRAP (zero-config installer)
# ========================================

def _penv_pio_path(core_dir: str) -> str:
    """Path to the `pio` executable inside a PlatformIO core_dir/penv."""
    if os.name == "nt":
        return os.path.join(core_dir, "penv", "Scripts", "pio.exe")
    return os.path.join(core_dir, "penv", "bin", "pio")


def _pio_version(pio_cmd: list, env: dict) -> tuple:
    """Return (ok, version_text). `pio --version` rc 0 means PlatformIO is usable."""
    rc, out, err = _run_cmd(list(pio_cmd) + ["--version"], env=env, timeout=60)
    text = (out or err or "").strip()
    return rc == 0, text


def _resolve_pio_cmd(config: dict, env: dict, core_dir: str, python_cmd: list) -> list:
    """Best-effort resolution of an invocable `pio` command WITHOUT installing:
       1. explicit config `pio_executable` if it exists,
       2. the bootstrapped penv pio.exe under core_dir,
       3. bare `pio` on PATH,
       4. `<python> -m platformio` (works when PlatformIO was pip-installed).
    Returns the first candidate whose `--version` succeeds, else []."""
    candidates = []
    explicit = str(_cfg(config, "pio_executable")).strip()
    if explicit:
        candidates.append([explicit])
    penv = _penv_pio_path(core_dir)
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


def _download_installer(env: dict) -> tuple:
    """Download get-platformio.py to a temp file. Returns (path, error)."""
    import urllib.request
    import tempfile
    url = _installer_url()
    try:
        logging.info(f"⬇️  Downloading PlatformIO installer: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-ESP32er"})
        with urllib.request.urlopen(request, timeout=120) as resp:
            data = resp.read()
        fd, path = tempfile.mkstemp(suffix="_get-platformio.py")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _bootstrap_pio(config: dict, env: dict, core_dir: str, python_cmd: list) -> tuple:
    """Ensure an invocable `pio` exists, installing PlatformIO Core if needed.
    Returns (pio_cmd, report, ok). Never raises into main()."""
    report = {"steps": [], "core_dir": core_dir}
    try:
        method = str(_cfg(config, "pio_install_method", "script") or "script").strip().lower()
        do_update = _as_bool(_cfg(config, "auto_update", False), False)
        do_pip = _as_bool(_cfg(config, "pip_install", True), True)

        # Already usable? (and not asked to refresh)
        existing = _resolve_pio_cmd(config, env, core_dir, python_cmd)
        if existing and not do_update:
            ok, ver = _pio_version(existing, env)
            report["steps"].append(("resolve", {"ok": ok, "action": "present", "pio": existing, "version": ver}))
            report["ok"] = ok
            return existing, report, ok

        # ── Install path 1: the official installer script ──
        if method == "script":
            installer, dl_err = _download_installer(env)
            if installer:
                inst_env = dict(env)
                inst_env["PLATFORMIO_CORE_DIR"] = core_dir
                rc, out, err = _run_cmd(list(python_cmd) + [installer], env=inst_env, timeout=900)
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

        # ── Install path 2 / fallback: pip install ──
        resolved = _resolve_pio_cmd(config, env, core_dir, python_cmd)
        if not resolved and do_pip:
            pip_cmd = list(python_cmd) + ["-m", "pip", "install", "--disable-pip-version-check"]
            pip_cmd += (["-U", "platformio"] if do_update else ["platformio"])
            logging.info(f"📦 Installing PlatformIO via pip: {pip_cmd}")
            rc, out, err = _run_cmd(pip_cmd, env=env, timeout=900)
            report["steps"].append(("pip-install",
                                    {"ok": rc == 0, "action": "pip", "returncode": rc,
                                     "stderr": (err or "")[-800:]}))
            resolved = _resolve_pio_cmd(config, env, core_dir, python_cmd)

        # ── Optional explicit upgrade of an already-present install ──
        if resolved and do_update and method != "pip":
            _run_cmd(list(resolved) + ["upgrade"], env=env, timeout=600)

        ok, ver = (_pio_version(resolved, env) if resolved else (False, ""))
        report["steps"].append(("validate", {"ok": ok, "version": ver, "pio": resolved}))
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
        f"core_dir : {report.get('core_dir', '')}",
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
                         if name in ("installer-script", "pip-install")), {})
    action = last_install.get("action", "present")
    return f"[bootstrap: {action} · ready={'yes' if ok else 'NO'}]\n\n"


# ========================================
# SAFETY PREFLIGHT (fail-safe environment gate)
# ========================================

def _platformio_ini(project_dir: str) -> str:
    return os.path.join(project_dir, "platformio.ini") if project_dir else ""


def _ini_platform(project_dir: str) -> str:
    """Best-effort read of the `platform =` value from a project's platformio.ini."""
    ini = _platformio_ini(project_dir)
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


def _probe_serial(pio_cmd: list, env: dict) -> dict:
    """Probe for a connected serial port via `pio device list --json-output`.
    Distinguishes: a port present (and whether it looks like an ESP32 adapter), no
    port, and the CLI itself unusable."""
    result = {"present": False, "esp_like": False, "cli_ok": False, "ports": [], "detail": ""}
    if not pio_cmd:
        result["detail"] = "pio not resolvable — cannot enumerate serial ports."
        return result
    rc, out, err = _run_cmd(list(pio_cmd) + ["device", "list", "--json-output"], env=env, timeout=60)
    result["cli_ok"] = rc == 0
    if rc != 0:
        result["detail"] = (err or out)[-400:]
        return result
    try:
        devices = json.loads(out or "[]")
    except (json.JSONDecodeError, TypeError):
        devices = []
    ports = []
    for dev in devices if isinstance(devices, list) else []:
        port = dev.get("port") if isinstance(dev, dict) else None
        hwid = (dev.get("hwid") or "") if isinstance(dev, dict) else ""
        if port:
            ports.append(port)
            if re.search(r"VID:PID=([0-9A-Fa-f]{4})", hwid):
                vid = re.search(r"VID:PID=([0-9A-Fa-f]{4})", hwid).group(1).upper()
                if vid in _ESP32_USB_VIDS:
                    result["esp_like"] = True
    result["ports"] = ports
    result["present"] = bool(ports)
    result["detail"] = f"{len(ports)} port(s): {', '.join(ports)}" if ports else "no serial ports enumerated"
    return result


def _preflight(action: str, config: dict, pio_cmd: list, env: dict) -> dict:
    """Validate the environment for ``action`` and REFUSE (fail-safe) rather than
    run a build/upload that cannot succeed. report['ok'] is False on any FATAL."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True}
    checks = report["checks"]

    pio_ok = bool(pio_cmd)
    checks["pio_resolvable"] = pio_ok

    project_dir = str(_cfg(config, "project_dir")).strip()
    needs_project = action in {"build", "clean", "check", "test", "list_artifacts",
                               "pkg_list", "pkg_install", "pkg_update"} | _HARDWARE_ACTIONS
    has_ini = bool(project_dir) and os.path.exists(_platformio_ini(project_dir))
    if needs_project:
        checks["platformio_ini"] = has_ini

    # Board / platform sanity — ESP32er is ESP32-branded (warn, never refuse, since
    # PlatformIO is multi-target and there is no shared-linker-script risk).
    platform = _ini_platform(project_dir)
    board = str(_cfg(config, "board")).strip()
    if platform and "espressif32" not in platform.lower():
        report["warnings"].append(
            f"platformio.ini platform is '{platform}', not espressif32 — ESP32er is ESP32-focused; "
            f"verify this is intentional.")
    if board and "esp32" not in board.lower() and not platform:
        report["warnings"].append(
            f"board '{board}' does not look like an ESP32 board — ESP32er targets espressif32.")

    needs_hardware = action in _HARDWARE_ACTIONS
    report["requires_hardware"] = needs_hardware
    if (needs_hardware or action == "validate") and pio_ok:
        serial = _probe_serial(pio_cmd, env)
        report["serial"] = serial
        checks["serial_cli_ok"] = serial["cli_ok"]
        checks["serial_port_present"] = serial["present"]
        if serial["present"] and not serial["esp_like"]:
            report["warnings"].append(
                f"A serial port was found but none matched a known ESP32 USB bridge "
                f"(CP210x/CH34x/FTDI/native). Ports: {', '.join(serial['ports'])}.")

    # ── FATAL gating ──
    fatals = report["fatals"]
    if action != "bootstrap" and not pio_ok:
        fatals.append(
            "PlatformIO Core (`pio`) is NOT resolvable. Leave pio_executable blank with "
            "auto_bootstrap: true so ESP32er installs it, or set pio_executable to an existing pio.")
    if needs_project and not has_ini:
        if not project_dir:
            fatals.append(
                f"action '{action}' needs a project — set project_dir to a folder containing "
                f"platformio.ini (use action='create_project' first).")
        else:
            fatals.append(
                f"No platformio.ini found in {project_dir!r} — not a PlatformIO project. "
                f"Run action='create_project' there first.")
    if needs_hardware and pio_ok:
        serial = report.get("serial", {})
        if not serial.get("cli_ok"):
            fatals.append("`pio device list` failed — cannot confirm a connected board.")
        elif not serial.get("present"):
            fatals.append(
                "No serial port detected — connect the ESP32 over USB (check the cable / driver) before "
                "an upload/monitor. (Compile-only actions like 'build' do NOT need a board.)")

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
        lines.append(f"  serial          : present={s.get('present')} esp_like={s.get('esp_like')} "
                     f"cli_ok={s.get('cli_ok')} ({s.get('detail', '')})")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ========================================
# ACTION EXECUTION
# ========================================

def _env_args(config: dict) -> list:
    """The `-e <environment>` argument (empty when no environment is configured)."""
    environment = str(_cfg(config, "environment")).strip()
    return ["-e", environment] if environment else []


def _project_args(config: dict) -> list:
    """The `-d <project_dir>` argument (empty when no project_dir is configured)."""
    project_dir = str(_cfg(config, "project_dir")).strip()
    return ["-d", project_dir] if project_dir else []


def _bounded_monitor(pio_cmd: list, config: dict, env: dict) -> dict:
    """Run `pio device monitor` for monitor_seconds, draining its stdout, then
    terminate it — making a normally-interactive stream usable in one run."""
    seconds = max(1, _as_int(_cfg(config, "monitor_seconds", 10), 10))
    port = str(_cfg(config, "port")).strip()
    baud = _as_int(_cfg(config, "baud", 115200), 115200)
    args = list(pio_cmd) + ["device", "monitor", "-b", str(baud)]
    if port:
        args += ["-p", port]
    args += _project_args(config)
    # --no-reconnect / quiet keep the bounded read clean where supported.
    args += ["--quiet"]

    logging.info(f"📟 Monitoring for {seconds}s: {args}")
    collected: list = []
    proc = None
    try:
        proc = subprocess.Popen(
            args, cwd=os.path.dirname(args[0]) if os.path.sep in str(args[0]) else None,
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
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

    reader = threading.Thread(target=_drain, daemon=True, name="esp32-monitor")
    reader.start()
    time.sleep(seconds)
    _terminate_proc(proc)
    reader.join(timeout=2)

    text = "\n".join(collected)
    return {
        "ok": True, "returncode": 0, "port": port or "(auto)", "monitor_seconds": seconds,
        "stdout": text or "(no serial output captured during the window)",
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


def _write_source(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    rel_path = str(_cfg(config, "rel_path")).strip()
    content = str(_cfg(config, "content"))
    if not project_dir or not rel_path:
        return {"ok": False, "error": "write_source needs project_dir and rel_path."}
    # Contain the write strictly under project_dir.
    target = os.path.normpath(os.path.join(project_dir, rel_path))
    if not target.startswith(os.path.normpath(project_dir) + os.sep) and target != os.path.normpath(project_dir):
        return {"ok": False, "error": f"rel_path escapes project_dir: {rel_path!r}"}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "returncode": 0, "path": target,
                "stdout": f"Wrote {len(content)} chars to {target}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": target}


def _read_source(config: dict) -> dict:
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


def _list_sources(config: dict) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    if not project_dir or not os.path.isdir(project_dir):
        return {"ok": False, "error": "list_sources needs an existing project_dir."}
    found = []
    for sub in ("src", "include", "lib", "test"):
        root = os.path.join(project_dir, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), project_dir)
                found.append(rel.replace(os.sep, "/"))
    ini = _platformio_ini(project_dir)
    if os.path.exists(ini):
        found.insert(0, "platformio.ini")
    return {"ok": True, "returncode": 0, "stdout": "\n".join(found) or "(no source files found)"}


def _create_project(config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    project_dir = str(_cfg(config, "project_dir")).strip()
    board = str(_cfg(config, "board")).strip()
    framework = str(_cfg(config, "framework")).strip()
    if not project_dir or not board:
        return {"ok": False, "error": "create_project needs project_dir and board (e.g. board='esp32dev')."}
    os.makedirs(project_dir, exist_ok=True)
    args = list(pio_cmd) + ["project", "init", "-d", project_dir, "-b", board]
    rc, out, err = _run_cmd(args, env=env, timeout=timeout)
    result = {"ok": rc == 0, "returncode": rc, "project_dir": project_dir,
              "stdout": out, "stderr": err}
    # Apply a non-default framework by patching platformio.ini (pio project init
    # uses the board's default framework; ESP-IDF / a specific framework is set here).
    if rc == 0 and framework:
        try:
            _ensure_framework(_platformio_ini(project_dir), framework)
            result["stdout"] = (out + f"\n[esp32er] framework set to '{framework}' in platformio.ini").strip()
        except Exception as e:
            result["stderr"] = (err + f"\n[esp32er] could not set framework: {e}").strip()
    return result


def _ensure_framework(ini_path: str, framework: str) -> None:
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


def _list_artifacts(config: dict) -> dict:
    """Enumerate firmware artifacts under .pio/build/<env>/ (firmware.elf/.bin/.hex)."""
    project_dir = str(_cfg(config, "project_dir")).strip()
    build_root = os.path.join(project_dir, ".pio", "build")
    if not os.path.isdir(build_root):
        return {"ok": False, "error": f"No build output at {build_root} — run action='build' first."}
    artifacts = []
    for dirpath, _dirs, files in os.walk(build_root):
        for name in files:
            if name.startswith("firmware.") or name.endswith((".elf", ".bin", ".hex")):
                artifacts.append(os.path.join(dirpath, name))
    return {"ok": bool(artifacts), "returncode": 0 if artifacts else 1,
            "stdout": "\n".join(artifacts) or "(no firmware artifacts found)"}


def _scaffold_build_upload(config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """One-call firmware lifecycle: create_project (if needed) -> write_source
    (if `content` given) -> build -> upload (only when a board is present) ->
    optional monitor (when monitor_seconds > 0).

    This collapses what is otherwise a 4+ round-trip Multi-Turn chain into a SINGLE
    agent run. It is fail-safe: a missing board does NOT abort — the project is
    still scaffolded and compiled, and the result reports "built OK, upload
    skipped" so a downstream Forker can branch on {success}. Any failing stage
    short-circuits and is reported with its `stage`.
    """
    project_dir = str(_cfg(config, "project_dir")).strip()
    stage_logs: list = []

    def _section(title: str, res: dict) -> None:
        out = (res.get("stdout") or "") if isinstance(res, dict) else ""
        err = (res.get("stderr") or "") if isinstance(res, dict) else ""
        body = "\n".join(p for p in (out, err) if p).strip()
        stage_logs.append(f"===== {title} =====\n{body or '(no output)'}")

    def _envelope(tool: str, ok: bool, stage: str, rc, extra: dict = None) -> dict:
        result = {"ok": ok, "returncode": rc, "stage": stage,
                  "project_dir": project_dir, "stdout": "\n\n".join(stage_logs)}
        if extra:
            result.update(extra)
        return {"ok": ok, "tool": tool, "result": result}

    # 1. Ensure a PlatformIO project exists (skip when platformio.ini already there).
    if not (project_dir and os.path.exists(_platformio_ini(project_dir))):
        cp = _create_project(config, pio_cmd, env, timeout)
        _section("create_project", cp)
        if not _ok(cp):
            return _envelope("scaffold_build_upload", False, "create_project", cp.get("returncode", 1))
    else:
        stage_logs.append(f"===== create_project =====\n(skipped — platformio.ini already present in {project_dir})")

    # 2. Write the sketch when content was supplied (default to src/main.cpp).
    if str(_cfg(config, "content")).strip():
        if not str(_cfg(config, "rel_path")).strip():
            config["rel_path"] = "src/main.cpp"
        ws = _write_source(config)
        _section("write_source", ws)
        if not _ok(ws):
            return _envelope("scaffold_build_upload", False, "write_source", ws.get("returncode", 1))

    # 3. Probe the board ONCE, then do the fewest `pio` runs possible:
    #    * board present -> `pio run -t upload` compiles AND flashes in a SINGLE
    #      invocation (build is implicit), avoiding a redundant separate compile pass.
    #    * no board     -> `pio run` compiles only, to verify the sketch builds, and
    #      the upload leg is skipped (fail-safe partial success — still "built OK").
    serial = _probe_serial(pio_cmd, env)
    if not serial.get("present"):
        bd = _pio_run([], config, pio_cmd, env, timeout)
        _section("build", bd)
        if not _ok(bd):
            return _envelope("scaffold_build_upload", False, "build", bd.get("returncode", 1))
        stage_logs.append(
            "===== upload =====\nSKIPPED — no serial port detected. The project compiled "
            "successfully; connect the ESP32 over USB and run action='upload' to flash it.")
        return _envelope("scaffold_build_upload (upload skipped: no board)", True, "upload_skipped", 0)

    up = _pio_run(["-t", "upload"], config, pio_cmd, env, timeout)
    _section("build+upload", up)
    port = serial.get("ports", [""])[0] if serial.get("ports") else str(_cfg(config, "port"))
    if not _ok(up):
        return _envelope("scaffold_build_upload", False, "upload", up.get("returncode", 1), {"port": port})

    # 4. Optional bounded monitor to prove it runs (HIL) when monitor_seconds > 0.
    if _as_int(_cfg(config, "monitor_seconds", 0), 0) > 0:
        mon = _bounded_monitor(pio_cmd, config, env)
        _section("monitor", mon)

    return _envelope("scaffold->build->upload", True, "upload", up.get("returncode", 0), {"port": port})


def _run_action(action: str, config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """Execute one action. Returns a normalized envelope {ok, tool, result}."""
    # ── one-call lifecycle composite (create -> write -> build -> upload -> monitor) ──
    if action == "scaffold_build_upload":
        return _scaffold_build_upload(config, pio_cmd, env, timeout)

    # ── stdlib-only project file ops ──
    if action == "write_source":
        return _wrap(action, _write_source(config))
    if action == "read_source":
        return _wrap(action, _read_source(config))
    if action == "list_sources":
        return _wrap(action, _list_sources(config))
    if action == "list_artifacts":
        return _wrap(action, _list_artifacts(config))
    if action == "create_project":
        return _wrap("project init", _create_project(config, pio_cmd, env, timeout))

    # ── bounded monitor (interactive command made one-shot) ──
    if action == "monitor":
        return _wrap("device monitor", _bounded_monitor(pio_cmd, config, env))
    if action == "monitor_session":
        up = _pio_run(["-t", "upload"], config, pio_cmd, env, timeout)
        if not _ok(up):
            return _wrap("upload", up)
        mon = _bounded_monitor(pio_cmd, config, env)
        mon["upload_returncode"] = up.get("returncode")
        return _wrap("upload+monitor", mon)

    # ── direct `pio` subcommands ──
    if action == "system_info":
        return _wrap("system info", _pio(["system", "info"], pio_cmd, env, timeout))
    if action == "boards":
        query = str(_cfg(config, "boards_query") or _cfg(config, "board")).strip()
        args = ["boards", "--json-output"] + ([query] if query else ["espressif32"])
        return _wrap("boards", _pio(args, pio_cmd, env, 120))
    if action == "device_list":
        return _wrap("device list", _pio(["device", "list", "--json-output"], pio_cmd, env, 60))
    if action == "build":
        return _wrap("run", _pio_run([], config, pio_cmd, env, timeout))
    if action == "clean":
        return _wrap("run -t clean", _pio_run(["-t", "clean"], config, pio_cmd, env, timeout))
    if action in ("upload", "build_and_upload"):
        return _wrap("run -t upload", _pio_run(["-t", "upload"], config, pio_cmd, env, timeout))
    if action == "check":
        return _wrap("check", _pio(["check"] + _project_args(config) + _env_args(config), pio_cmd, env, timeout))
    if action == "test":
        return _wrap("test", _pio(["test"] + _project_args(config) + _env_args(config), pio_cmd, env, timeout))
    if action == "pkg_list":
        return _wrap("pkg list", _pio(["pkg", "list"] + _project_args(config), pio_cmd, env, 120))
    if action == "pkg_update":
        return _wrap("pkg update", _pio(["pkg", "update"] + _project_args(config), pio_cmd, env, 300))
    if action == "pkg_install":
        spec = str(_cfg(config, "pkg_spec")).strip()
        if not spec:
            return _wrap("pkg install", {"ok": False, "error": "pkg_install needs pkg_spec (a library spec)."})
        args = ["pkg", "install"] + _project_args(config) + ["-l", spec]
        return _wrap("pkg install", _pio(args, pio_cmd, env, 300))

    valid = ", ".join(sorted(_ALL_ACTIONS))
    return _wrap(action, {"ok": False, "error": f"Unknown action {action!r}. Valid actions: {valid}."})


def _pio(args: list, pio_cmd: list, env: dict, timeout: float) -> dict:
    """Run `pio <args>` and normalize to {ok, returncode, stdout, stderr}."""
    rc, out, err = _run_cmd(list(pio_cmd) + list(args), env=env, timeout=timeout)
    return {"ok": rc == 0, "returncode": rc, "stdout": out, "stderr": err}


def _pio_run(extra: list, config: dict, pio_cmd: list, env: dict, timeout: float) -> dict:
    """`pio run` with -d/-e and any extra target args, plus optional --upload-port."""
    args = ["run"] + _project_args(config) + _env_args(config) + list(extra)
    upload_port = str(_cfg(config, "port")).strip()
    if "-t" in extra and "upload" in extra and upload_port:
        args += ["--upload-port", upload_port]
    return _pio(args, pio_cmd, env, timeout)


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
    """Emit an INI_SECTION_ESP32ER<<< block atomically (single logging.info call).

    Mirrors the STM32er / Kalier / Apirer convention so this agent's structured
    output is consumable by the Multi-Turn LLM (wrapped chat-agent run-result KV
    promotion) AND the Parametrizer canvas pipeline (registered in
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['esp32er'] and
    parametrizer.SECTION_AGENT_TYPES). The KV header field names MUST stay aligned
    with that registration."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_ESP32ER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_ESP32ER")


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

        logging.info("⚡ ESP32er AGENT STARTED (PlatformIO Core / pio CLI bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets: {target_agents}")

        python_cmd = get_python_command()
        env = get_agent_env()
        core_dir = str(_cfg(config, "pio_core_dir")).strip() or _default_core_dir()
        env["PLATFORMIO_CORE_DIR"] = core_dir
        timeout = float(_as_int(_cfg(config, "command_timeout", 900), 900))
        auto_bootstrap = _as_bool(_cfg(config, "auto_bootstrap", True), True)

        # ── Resolve `pio`, AUTO-BOOTSTRAPPING PlatformIO Core when needed ──
        bootstrap_report = None
        boot_ok = True
        if action == "bootstrap":
            pio_cmd, bootstrap_report, boot_ok = _bootstrap_pio(config, env, core_dir, python_cmd)
        else:
            pio_cmd = _resolve_pio_cmd(config, env, core_dir, python_cmd)
            if not pio_cmd and auto_bootstrap:
                logging.info("🧰 Auto-bootstrap: PlatformIO Core not found — installing...")
                pio_cmd, bootstrap_report, boot_ok = _bootstrap_pio(config, env, core_dir, python_cmd)

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
            pf = _preflight("validate", config, pio_cmd, env)
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
                preflight = _preflight(action, config, pio_cmd, env)
            if preflight is not None and not preflight["ok"]:
                body = ("PREFLIGHT REFUSED this operation (fail-safe — the environment could not be "
                        "guaranteed correct):\n\n" + _format_preflight_report(preflight))
                logging.error(f"❌ Preflight refused {action}: {preflight['fatals']}")
                envelope = {"ok": False, "tool": action,
                            "result": {"ok": False, "error": "preflight refused", "stage": "preflight"}}
            else:
                subject = str(_cfg(config, "project_dir") or _cfg(config, "board") or "(environment)")
                logging.info(f"Subject: {subject!r}")
                envelope = _run_action(action, config, pio_cmd, env, timeout)
                body = _result_body(envelope.get("result", {}))
                if preflight is not None and preflight.get("warnings"):
                    body = ("[preflight OK — warnings: " + " | ".join(preflight["warnings"]) + "]\n\n") + body

            if bootstrap_report is not None:
                body = _bootstrap_note(bootstrap_report, boot_ok) + body

        # ── Build the KV header (FIXED schema — keep aligned with _PARAMETRIZER_OUTPUT_FIELDS) ──
        result = envelope.get("result", {}) if isinstance(envelope.get("result"), dict) else {}
        project_dir = str(result.get("project_dir", "")) or str(_cfg(config, "project_dir", ""))
        port = str(result.get("port", "")) or str(_cfg(config, "port", ""))
        environment = str(_cfg(config, "environment", ""))
        outcome = {
            "action": action,
            "tool": envelope.get("tool", action),
            "ok": "true" if envelope.get("ok") else "false",
            "returncode": result.get("returncode", ""),
            "success": "true" if envelope.get("ok") else "false",
            "project_dir": project_dir,
            "port": port,
            "environment": environment,
            "stage": result.get("stage", ""),
        }
        _emit_section(outcome, body or "(no output)")

        if envelope.get("ok"):
            logging.info(f"🏁 ESP32er {action} complete: success=true")
        else:
            logging.warning(f"⚠️ ESP32er {action} did not succeed. {result.get('error', '')}")

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
            f"🏁 ESP32er agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
