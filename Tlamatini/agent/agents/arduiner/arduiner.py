# Arduiner Agent - Arduino CLI (`arduino-cli`) bridge (firmware scaffold/build/upload/monitor)
# Action: Triggered by upstream -> resolve the `arduino-cli` executable (auto-bootstrapping
#         the official Go binary when absent) -> run ONE capability (selected by `action`)
#         as a direct `arduino-cli` subprocess -> capture stdout/stderr -> emit
#         INI_SECTION_ARDUINER -> ALWAYS trigger downstream (success OR failure).
#
# Arduiner is Tlamatini's integration of the Arduino CLI (https://arduino.github.io/arduino-cli/).
# It is the THIRD member of the microcontroller-agent family and deliberately shares the
# ESP32er scheme: arduino-cli — like PlatformIO's `pio` — is a COMPLETE standalone CLI
# (board/library managers, sketch builder, board detection, compiler, uploader, serial
# monitor), so Arduiner needs NO MCP server (unlike STM32er, which wraps an MCP because
# STM32CubeIDE has no unified CLI). It invokes `arduino-cli` subcommands DIRECTLY (the
# Kalier / Executer / ESP32er pattern). It is fully self-contained (stdlib only:
# subprocess + urllib + zipfile + tarfile + json + threading) so it works identically in
# source and frozen builds and never imports from agent.* (the agent pool runs as
# standalone Python subprocesses with no path back into the Django app).
#
# ZERO-CONFIG: with no on-disk `arduino_cli_executable` and `auto_bootstrap: true`,
# Arduiner DOWNLOADS the arduino-cli binary itself — it fetches the platform-correct
# release archive from downloads.arduino.cc, unzips it into a per-user dir, then runs
# `config init` + `core update-index` — so the end user installs only the board USB
# driver + Tlamatini and nothing else. (arduino-cli is a Go binary; there is no pip
# package, so the bootstrap is a binary download, NOT a pip install like ESP32er.)
#
# UNIFORM TEMPLATE-PROJECT SCHEME: Arduiner ships its own `ArduinoTemplateProject/`
# (bundled beside this script), the Arduino-family analog of STM32er's STM32 Template
# Project and ESP32er's `pio project init` scaffold. `create_project` copies that
# template, renames the .ino to match the destination folder (arduino-cli requires the
# sketch's primary .ino basename == folder name), and stamps the board identity into the
# template's `sketch.yaml` profile (the Arduino-native peer of platformio.ini) so the
# scaffolded project carries its FQBN + port the same way ESP32er's project carries its
# board and STM32er's template carries its target.
#
# `arduino-cli monitor` is interactive; the bounded `monitor` / `monitor_session` actions
# Popen the monitor, drain its stdout for `monitor_seconds` and then terminate it, so a
# continuous stream is usable end-to-end in one run.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core and inherited by every
# spawned agent via get_agent_env's os.environ.copy()) so every temp file this
# agent writes — including the downloaded arduino-cli release archive — lands
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
import shutil
import logging
import platform
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
# HELPER FUNCTIONS (from esp32er.py / stm32er.py / shoter.py boilerplate — copy verbatim)
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
# ACTION CONTRACT  (each action maps to ONE `arduino-cli` subcommand, or a stdlib op)
# ========================================

# Meta actions handled by Arduiner ITSELF (install / validate the arduino-cli env).
_META_ACTIONS = {"bootstrap", "validate"}

# Read-only informational actions — need `arduino-cli` but NO board / no sketch.
_INFO_ACTIONS = {
    "system_info", "boards", "device_list", "core_list", "core_search",
    "lib_list", "lib_search", "list_artifacts",
}

# Index / package / core management — need `arduino-cli`, touch GLOBAL state, no board.
_MANAGE_ACTIONS = {
    "core_update_index", "core_install", "core_uninstall",
    "lib_update_index", "lib_install",
}

# Pure-stdlib project file ops (no `arduino-cli` invocation, no board).
_FILE_ACTIONS = {"write_source", "read_source", "list_sources"}

# Build-class actions: need `arduino-cli` + a sketch + an FQBN, but NO hardware.
_BUILD_ACTIONS = {"build", "clean", "create_project"}

# Upload actions: ALSO require a connected serial port. Most Arduino-family boards
# (Uno/Nano/Mega/Leonardo/ESP/SAMD) flash over USB-serial — NO external probe needed;
# a `programmer` is only required for raw-ISP / bare-AVR / burn-bootloader paths.
_UPLOAD_ACTIONS = {"upload", "build_and_upload"}

# Monitor actions: bounded `arduino-cli monitor` — ALSO require a serial port.
_MONITOR_ACTIONS = {"monitor", "monitor_session"}

# Anything that touches a physically connected board.
_HARDWARE_ACTIONS = _UPLOAD_ACTIONS | _MONITOR_ACTIONS

_ALL_ACTIONS = (
    _META_ACTIONS | _INFO_ACTIONS | _MANAGE_ACTIONS | _FILE_ACTIONS
    | _BUILD_ACTIONS | _UPLOAD_ACTIONS | _MONITOR_ACTIONS
)

# USB Vendor IDs commonly seen on Arduino-compatible dev boards (Arduino LLC / FTDI /
# CH34x / CP210x / WCH / SiLabs / native USB). Used by the preflight to upgrade a
# generic "a port exists" into a confident "an Arduino-style adapter is present" — a
# miss only DOWNGRADES to a warning, never refuses, because plenty of boards use other
# bridges (clones especially).
_ARDUINO_USB_VIDS = ("2341", "2A03", "0403", "1A86", "10C4", "303A", "239A", "1B4F")

# The bundled template project (Arduino-family analog of STM32 Template Project / the
# PlatformIO scaffold). Ships beside this script and travels with the agent pool copy.
_TEMPLATE_DIR_NAME = "ArduinoTemplateProject"


def _release_archive_name() -> str:
    """Pick the correct arduino-cli release archive for this OS/arch.
    See https://arduino.github.io/arduino-cli/latest/installation/ (download names)."""
    system = platform.system().lower()
    machine = (platform.machine() or "").lower()
    if system.startswith("win"):
        arch = "32bit" if (machine in ("x86", "i386", "i686") or "32" in machine) else "64bit"
        return f"arduino-cli_latest_Windows_{arch}.zip"
    if system == "darwin":
        arch = "ARM64" if ("arm" in machine or "aarch64" in machine) else "64bit"
        return f"arduino-cli_latest_macOS_{arch}.tar.gz"
    # Linux / other POSIX
    if "aarch64" in machine or "arm64" in machine:
        arch = "ARM64"
    elif "arm" in machine:
        arch = "ARMv7"
    elif machine in ("i386", "i686", "x86"):
        arch = "32bit"
    else:
        arch = "64bit"
    return f"arduino-cli_latest_Linux_{arch}.tar.gz"


def _installer_url() -> str:
    return "https://downloads.arduino.cc/arduino-cli/" + _release_archive_name()


def _cli_binary_name() -> str:
    return "arduino-cli.exe" if os.name == "nt" else "arduino-cli"


def _default_install_dir() -> str:
    """A per-user, writable dir holding the arduino-cli binary + its data/config.
    Works in source AND in a frozen 'Program Files' install (where the app dir is
    read-only)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "arduino-cli")


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
# ARDUINO-CLI RESOLUTION + AUTO-BOOTSTRAP (zero-config installer)
# ========================================

def _cli_data_env(env: dict, install_dir: str) -> dict:
    """Point arduino-cli's data / sketchbook / config at a per-user writable location
    under install_dir so a frozen 'Program Files' install stays read-only-safe."""
    out = dict(env)
    out["ARDUINO_DIRECTORIES_DATA"] = os.path.join(install_dir, "data")
    out["ARDUINO_DIRECTORIES_USER"] = os.path.join(install_dir, "user")
    out["ARDUINO_DIRECTORIES_DOWNLOADS"] = os.path.join(install_dir, "downloads")
    out["ARDUINO_CONFIG_FILE"] = os.path.join(install_dir, "arduino-cli.yaml")
    return out


def _cli_version(cli_cmd: list, env: dict) -> tuple:
    """Return (ok, version_text). `arduino-cli version` rc 0 means it is usable."""
    rc, out, err = _run_cmd(list(cli_cmd) + ["version"], env=env, timeout=60)
    text = (out or err or "").strip()
    return rc == 0, text


def _resolve_cli_cmd(config: dict, env: dict, install_dir: str) -> list:
    """Best-effort resolution of an invocable `arduino-cli` WITHOUT installing:
       1. explicit config `arduino_cli_executable` if it exists,
       2. the bootstrapped binary under install_dir,
       3. bare `arduino-cli` on PATH.
    Returns the first candidate whose `version` succeeds, else []."""
    candidates = []
    explicit = str(_cfg(config, "arduino_cli_executable")).strip()
    if explicit:
        candidates.append([explicit])
    bundled = os.path.join(install_dir, _cli_binary_name())
    if os.path.exists(bundled):
        candidates.append([bundled])
    candidates.append(["arduino-cli"])
    for cand in candidates:
        ok, _ver = _cli_version(cand, env)
        if ok:
            return cand
    return []


def _download_archive(env: dict) -> tuple:
    """Download the arduino-cli release archive to a temp file. Returns (path, error)."""
    import urllib.request
    import tempfile
    url = _installer_url()
    try:
        logging.info(f"⬇️  Downloading arduino-cli: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-Arduiner"})
        with urllib.request.urlopen(request, timeout=180) as resp:
            data = resp.read()
        suffix = ".zip" if url.endswith(".zip") else ".tar.gz"
        fd, path = tempfile.mkstemp(suffix="_arduino-cli" + suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _extract_cli(archive_path: str, install_dir: str) -> tuple:
    """Extract the arduino-cli binary from the downloaded archive into install_dir.
    Returns (binary_path, error)."""
    import zipfile
    import tarfile
    binary = _cli_binary_name()
    try:
        os.makedirs(install_dir, exist_ok=True)
        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zf:
                zf.extractall(install_dir)
        else:
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(install_dir)
        # Locate the extracted binary (archives put it at the root, but be defensive).
        target = os.path.join(install_dir, binary)
        if not os.path.exists(target):
            for dirpath, _dirs, files in os.walk(install_dir):
                if binary in files:
                    found = os.path.join(dirpath, binary)
                    if found != target:
                        shutil.move(found, target)
                    break
        if not os.path.exists(target):
            return "", f"arduino-cli binary not found in the extracted archive ({install_dir})"
        if os.name != "nt":
            try:
                os.chmod(target, 0o755)
            except Exception:
                pass
        return target, ""
    except Exception as e:
        return "", str(e)


def _bootstrap_cli(config: dict, env: dict, install_dir: str) -> tuple:
    """Ensure an invocable `arduino-cli` exists, downloading the binary if needed.
    Returns (cli_cmd, report, ok). Never raises into main()."""
    report = {"steps": [], "install_dir": install_dir}
    try:
        do_update = _as_bool(_cfg(config, "auto_update", False), False)

        # Already usable? (and not asked to refresh)
        existing = _resolve_cli_cmd(config, env, install_dir)
        if existing and not do_update:
            ok, ver = _cli_version(existing, env)
            report["steps"].append(("resolve", {"ok": ok, "action": "present", "cli": existing, "version": ver}))
            report["ok"] = ok
            return existing, report, ok

        # ── Download + extract the release binary ──
        archive, dl_err = _download_archive(env)
        if archive:
            binary, ex_err = _extract_cli(archive, install_dir)
            try:
                os.remove(archive)
            except Exception:
                pass
            report["steps"].append(("download-extract",
                                    {"ok": bool(binary and not ex_err), "action": _release_archive_name(),
                                     "error": ex_err, "binary": binary}))
        else:
            report["steps"].append(("download-extract",
                                    {"ok": False, "action": "download-failed", "error": dl_err}))

        resolved = _resolve_cli_cmd(config, env, install_dir)

        # ── First-run prep: config init + core update-index so the first build isn't cold ──
        if resolved:
            init_env = _cli_data_env(env, install_dir)
            _run_cmd(list(resolved) + ["config", "init", "--overwrite"], env=init_env, timeout=120)
            ai = _additional_urls_args(config)
            rc, out, err = _run_cmd(list(resolved) + ["core", "update-index"] + ai, env=init_env, timeout=300)
            report["steps"].append(("core-update-index", {"ok": rc == 0, "action": "update-index",
                                                           "returncode": rc, "stderr": (err or "")[-400:]}))

        ok, ver = (_cli_version(resolved, env) if resolved else (False, ""))
        report["steps"].append(("validate", {"ok": ok, "version": ver, "cli": resolved}))
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
        f"install_dir : {report.get('install_dir', '')}",
        f"overall     : {'OK' if report.get('ok') else 'FAILED'}",
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
                         if name == "download-extract"), {})
    action = last_install.get("action", "present")
    return f"[bootstrap: {action} · ready={'yes' if ok else 'NO'}]\n\n"


# ========================================
# FQBN / CORE helpers
# ========================================

_FQBN_RE = re.compile(r"^[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+(?::.+)?$")


def _fqbn_platform_id(fqbn: str) -> str:
    """packager:arch:board[:opts] -> packager:arch (the core/platform id to install)."""
    parts = (fqbn or "").split(":")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}:{parts[1]}"
    return ""


def _fqbn_looks_valid(fqbn: str) -> bool:
    return bool(_FQBN_RE.match((fqbn or "").strip()))


def _additional_urls_args(config: dict) -> list:
    """`--additional-urls <a> <b> ...` for third-party cores (ESP32/STM32/RP2040/...).
    arduino-cli accepts a comma-separated list to a single --additional-urls flag."""
    raw = str(_cfg(config, "additional_urls")).strip()
    if not raw:
        return []
    urls = [u for u in re.split(r"[\s,]+", raw) if u]
    return ["--additional-urls", ",".join(urls)] if urls else []


def _installed_platform_ids(cli_cmd: list, env: dict) -> list:
    """Return the list of installed core/platform ids via `core list --json`."""
    rc, out, _err = _run_cmd(list(cli_cmd) + ["core", "list", "--json"], env=env, timeout=60)
    if rc != 0:
        return []
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, TypeError):
        return []
    # arduino-cli >=1.0 wraps the list under "platforms"; older emits a bare list.
    rows = data.get("platforms", data) if isinstance(data, dict) else data
    ids = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            pid = row.get("id") or row.get("ID") or ""
            if pid:
                ids.append(pid)
    return ids


def _ensure_core_installed(config: dict, cli_cmd: list, env: dict, timeout: float) -> dict:
    """If the FQBN's platform/core is not installed, install it (auto_core_install).
    Returns {ensured, installed_now, platform_id, detail}. arduino-cli — unlike
    PlatformIO — does NOT auto-install platforms on compile, so a build for an
    un-installed board fails; this closes that gap for the zero-config experience."""
    fqbn = str(_cfg(config, "fqbn")).strip()
    platform_id = _fqbn_platform_id(fqbn)
    result = {"ensured": False, "installed_now": False, "platform_id": platform_id, "detail": ""}
    if not platform_id:
        result["detail"] = "no FQBN -> cannot derive a core id"
        return result
    installed = _installed_platform_ids(cli_cmd, env)
    if any(pid.lower() == platform_id.lower() for pid in installed):
        result["ensured"] = True
        result["detail"] = f"core '{platform_id}' already installed"
        return result
    if not _as_bool(_cfg(config, "auto_core_install", True), True):
        result["detail"] = (f"core '{platform_id}' NOT installed and auto_core_install is off — "
                            f"run action='core_install' with core_spec='{platform_id}' first.")
        return result
    # Refresh the index (with any third-party URLs) then install the core.
    ai = _additional_urls_args(config)
    logging.info(f"🧩 Auto-installing missing core '{platform_id}' (with index refresh)...")
    _run_cmd(list(cli_cmd) + ["core", "update-index"] + ai, env=env, timeout=min(timeout, 300))
    rc, out, err = _run_cmd(list(cli_cmd) + ["core", "install", platform_id] + ai, env=env, timeout=timeout)
    result["ensured"] = rc == 0
    result["installed_now"] = rc == 0
    result["detail"] = (f"installed core '{platform_id}'" if rc == 0
                        else f"core install '{platform_id}' failed (rc={rc}): {(err or out)[-300:]}")
    return result


# ========================================
# SAFETY PREFLIGHT (fail-safe environment gate)
# ========================================

def _sketch_ino(sketch_path: str) -> str:
    """Return the primary .ino path for a sketch folder (folder/<folder>.ino preferred)."""
    if not sketch_path or not os.path.isdir(sketch_path):
        return ""
    base = os.path.basename(os.path.normpath(sketch_path))
    preferred = os.path.join(sketch_path, base + ".ino")
    if os.path.exists(preferred):
        return preferred
    for name in sorted(os.listdir(sketch_path)):
        if name.endswith(".ino"):
            return os.path.join(sketch_path, name)
    return ""


def _probe_serial(cli_cmd: list, env: dict) -> dict:
    """Probe for a connected serial port via `arduino-cli board list --json`.
    Distinguishes: a port present (and whether it looks like an Arduino adapter, plus
    any FQBN arduino-cli matched to it), no port, and the CLI itself unusable."""
    result = {"present": False, "arduino_like": False, "cli_ok": False, "ports": [],
              "matched_fqbns": [], "detail": ""}
    if not cli_cmd:
        result["detail"] = "arduino-cli not resolvable — cannot enumerate serial ports."
        return result
    rc, out, err = _run_cmd(list(cli_cmd) + ["board", "list", "--json"], env=env, timeout=60)
    result["cli_ok"] = rc == 0
    if rc != 0:
        result["detail"] = (err or out)[-400:]
        return result
    try:
        data = json.loads(out or "{}")
    except (json.JSONDecodeError, TypeError):
        data = {}
    # arduino-cli >=1.0 wraps under "detected_ports"; older emits a bare list.
    rows = data.get("detected_ports", data) if isinstance(data, dict) else data
    ports, fqbns = [], []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        port_info = row.get("port", row)
        address = port_info.get("address") if isinstance(port_info, dict) else None
        props = port_info.get("properties", {}) if isinstance(port_info, dict) else {}
        vid = str((props or {}).get("vid", "")).upper().replace("0X", "")
        if address:
            ports.append(address)
            if vid and vid in _ARDUINO_USB_VIDS:
                result["arduino_like"] = True
        for mb in row.get("matching_boards", []) or []:
            if isinstance(mb, dict) and mb.get("fqbn"):
                fqbns.append(mb["fqbn"])
    result["ports"] = ports
    result["matched_fqbns"] = fqbns
    result["present"] = bool(ports)
    result["detail"] = (f"{len(ports)} port(s): {', '.join(ports)}"
                        + (f"  matched FQBN(s): {', '.join(fqbns)}" if fqbns else "")
                        if ports else "no serial ports enumerated")
    return result


def _preflight(action: str, config: dict, cli_cmd: list, env: dict) -> dict:
    """Validate the environment for ``action`` and REFUSE (fail-safe) rather than
    run a build/upload that cannot succeed. report['ok'] is False on any FATAL."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True}
    checks = report["checks"]

    cli_ok = bool(cli_cmd)
    checks["arduino_cli_resolvable"] = cli_ok

    sketch_path = str(_cfg(config, "sketch_path")).strip()
    fqbn = str(_cfg(config, "fqbn")).strip()

    needs_sketch = action in {"build", "clean", "list_artifacts"} | _HARDWARE_ACTIONS
    ino = _sketch_ino(sketch_path) if sketch_path else ""
    has_sketch = bool(ino)
    if needs_sketch:
        checks["sketch_present"] = has_sketch

    needs_fqbn = action in {"build", "clean"} | _UPLOAD_ACTIONS
    if needs_fqbn:
        checks["fqbn_set"] = bool(fqbn)
        if fqbn and not _fqbn_looks_valid(fqbn):
            report["warnings"].append(
                f"fqbn '{fqbn}' does not match VENDOR:ARCH:BOARD[:opts] — verify it "
                f"(use action='boards' / 'device_list' to discover the right FQBN).")

    needs_hardware = action in _HARDWARE_ACTIONS
    report["requires_hardware"] = needs_hardware
    if (needs_hardware or action == "validate") and cli_ok:
        serial = _probe_serial(cli_cmd, env)
        report["serial"] = serial
        checks["serial_cli_ok"] = serial["cli_ok"]
        checks["serial_port_present"] = serial["present"]
        if serial["present"] and not serial["arduino_like"]:
            report["warnings"].append(
                f"A serial port was found but none matched a known Arduino USB vendor id. "
                f"Ports: {', '.join(serial['ports'])}. (Clones often use CH340/CP210x — this is "
                f"informational, not a refusal.)")

    # ── FATAL gating ──
    fatals = report["fatals"]
    if action != "bootstrap" and not cli_ok:
        fatals.append(
            "arduino-cli is NOT resolvable. Leave arduino_cli_executable blank with "
            "auto_bootstrap: true so Arduiner downloads it, or set arduino_cli_executable "
            "to an existing arduino-cli binary.")
    if needs_sketch and not has_sketch:
        if not sketch_path:
            fatals.append(
                f"action '{action}' needs a sketch — set sketch_path to a folder containing a "
                f".ino (use action='create_project' first).")
        else:
            fatals.append(
                f"No .ino found in {sketch_path!r} — not an Arduino sketch. "
                f"Run action='create_project' there first.")
    if needs_fqbn and not fqbn:
        fatals.append(
            f"action '{action}' needs an FQBN (e.g. fqbn='arduino:avr:uno'). "
            f"Use action='device_list' to read the FQBN of the connected board.")
    if needs_hardware and cli_ok:
        serial = report.get("serial", {})
        if not serial.get("cli_ok"):
            fatals.append("`arduino-cli board list` failed — cannot confirm a connected board.")
        elif not serial.get("present"):
            fatals.append(
                "No serial port detected — connect the board over USB (check the cable / driver) "
                "before an upload/monitor. (Compile-only actions like 'build' do NOT need a board.)")

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
        lines.append(f"  serial          : present={s.get('present')} arduino_like={s.get('arduino_like')} "
                     f"cli_ok={s.get('cli_ok')} ({s.get('detail', '')})")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ========================================
# ACTION EXECUTION
# ========================================

def _bounded_monitor(cli_cmd: list, config: dict, env: dict) -> dict:
    """Run `arduino-cli monitor` for monitor_seconds, draining its stdout, then
    terminate it — making a normally-interactive stream usable in one run."""
    seconds = max(1, _as_int(_cfg(config, "monitor_seconds", 10), 10))
    port = str(_cfg(config, "port")).strip()
    baud = _as_int(_cfg(config, "baud", 115200), 115200)
    fqbn = str(_cfg(config, "fqbn")).strip()
    args = list(cli_cmd) + ["monitor", "--config", f"baudrate={baud}", "--quiet"]
    if port:
        args += ["-p", port]
    if fqbn:
        args += ["-b", fqbn]

    logging.info(f"📟 Monitoring for {seconds}s: {args}")
    collected: list = []
    proc = None
    try:
        proc = subprocess.Popen(
            args, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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

    reader = threading.Thread(target=_drain, daemon=True, name="arduino-monitor")
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
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    rel_path = str(_cfg(config, "rel_path")).strip()
    content = str(_cfg(config, "content"))
    if not sketch_path or not rel_path:
        return {"ok": False, "error": "write_source needs sketch_path and rel_path."}
    # Contain the write strictly under sketch_path.
    target = os.path.normpath(os.path.join(sketch_path, rel_path))
    root = os.path.normpath(sketch_path)
    if not target.startswith(root + os.sep) and target != root:
        return {"ok": False, "error": f"rel_path escapes sketch_path: {rel_path!r}"}
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "returncode": 0, "path": target,
                "stdout": f"Wrote {len(content)} chars to {target}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": target}


def _read_source(config: dict) -> dict:
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    rel_path = str(_cfg(config, "rel_path")).strip()
    if not sketch_path or not rel_path:
        return {"ok": False, "error": "read_source needs sketch_path and rel_path."}
    target = os.path.normpath(os.path.join(sketch_path, rel_path))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return {"ok": True, "returncode": 0, "path": target, "stdout": f.read()}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": target}


def _list_sources(config: dict) -> dict:
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    if not sketch_path or not os.path.isdir(sketch_path):
        return {"ok": False, "error": "list_sources needs an existing sketch_path."}
    found = []
    for dirpath, _dirs, files in os.walk(sketch_path):
        if os.path.basename(dirpath) == "build":  # skip compiled output
            continue
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), sketch_path)
            found.append(rel.replace(os.sep, "/"))
    return {"ok": True, "returncode": 0, "stdout": "\n".join(sorted(found)) or "(no source files found)"}


def _template_source_dir() -> str:
    """The bundled ArduinoTemplateProject directory (beside this script)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _TEMPLATE_DIR_NAME)


def _stamp_sketch_yaml(sketch_path: str, fqbn: str, port: str) -> None:
    """Stamp default_fqbn / default_port into the scaffold's sketch.yaml profile.
    The Arduino-native sketch.yaml is the peer of platformio.ini — it lets the
    scaffolded project carry its board identity. Best-effort, never raises."""
    yaml_path = os.path.join(sketch_path, "sketch.yaml")
    try:
        data = {}
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8", errors="replace") as f:
                data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            data = {}
        if fqbn:
            data["default_fqbn"] = fqbn
        if port:
            data["default_port"] = port
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception as e:
        logging.warning(f"⚠️ could not stamp sketch.yaml: {e}")


def _create_project(config: dict, cli_cmd: list, env: dict, timeout: float) -> dict:
    """Scaffold a sketch from the bundled ArduinoTemplateProject (uniform template-project
    scheme), falling back to `arduino-cli sketch new` if the template is unavailable.
    arduino-cli requires the primary .ino basename to equal the folder name, so the
    copied .ino is renamed accordingly."""
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    fqbn = str(_cfg(config, "fqbn")).strip()
    port = str(_cfg(config, "port")).strip()
    if not sketch_path:
        return {"ok": False, "error": "create_project needs sketch_path (the destination sketch folder)."}

    folder_name = os.path.basename(os.path.normpath(sketch_path))
    template = _template_source_dir()

    if os.path.isdir(sketch_path) and _sketch_ino(sketch_path):
        return {"ok": True, "returncode": 0, "sketch_path": sketch_path,
                "stdout": f"Sketch already exists at {sketch_path} (left untouched)."}

    if os.path.isdir(template):
        try:
            os.makedirs(sketch_path, exist_ok=True)
            # Copy every template entry, renaming the primary .ino to <folder>.ino.
            for name in os.listdir(template):
                src = os.path.join(template, name)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(sketch_path, name), dirs_exist_ok=True)
                    continue
                dst_name = name
                if name.endswith(".ino"):
                    dst_name = folder_name + ".ino"
                shutil.copy2(src, os.path.join(sketch_path, dst_name))
            _stamp_sketch_yaml(sketch_path, fqbn, port)
            return {"ok": True, "returncode": 0, "sketch_path": sketch_path,
                    "stdout": f"Scaffolded '{folder_name}' from ArduinoTemplateProject at {sketch_path}"
                              + (f" (default_fqbn={fqbn})" if fqbn else "")}
        except Exception as e:
            return {"ok": False, "error": f"template copy failed: {e}", "sketch_path": sketch_path}

    # Fallback: arduino-cli's own minimal scaffold.
    rc, out, err = _run_cmd(list(cli_cmd) + ["sketch", "new", sketch_path], env=env, timeout=timeout)
    if rc == 0:
        _stamp_sketch_yaml(sketch_path, fqbn, port)
    return {"ok": rc == 0, "returncode": rc, "sketch_path": sketch_path,
            "stdout": out + "\n[arduiner] (ArduinoTemplateProject not found — used `sketch new`)",
            "stderr": err}


def _build_dir(sketch_path: str) -> str:
    return os.path.join(sketch_path, "build")


def _list_artifacts(config: dict) -> dict:
    """Enumerate firmware artifacts under <sketch>/build/ (.hex/.bin/.elf), produced when
    a compile is run with --export-binaries (the build action sets it)."""
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    build_root = _build_dir(sketch_path)
    if not os.path.isdir(build_root):
        return {"ok": False, "error": f"No build output at {build_root} — run action='build' first."}
    artifacts = []
    for dirpath, _dirs, files in os.walk(build_root):
        for name in files:
            if name.endswith((".elf", ".bin", ".hex", ".eep", ".uf2")):
                artifacts.append(os.path.join(dirpath, name))
    return {"ok": bool(artifacts), "returncode": 0 if artifacts else 1,
            "stdout": "\n".join(sorted(artifacts)) or "(no firmware artifacts found)"}


def _run_action(action: str, config: dict, cli_cmd: list, env: dict, timeout: float) -> dict:
    """Execute one action. Returns a normalized envelope {ok, tool, result}."""
    port = str(_cfg(config, "port")).strip()
    programmer = str(_cfg(config, "programmer")).strip()
    ai = _additional_urls_args(config)

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
        return _wrap("sketch new", _create_project(config, cli_cmd, env, timeout))

    # ── bounded monitor (interactive command made one-shot) ──
    if action == "monitor":
        return _wrap("monitor", _bounded_monitor(cli_cmd, config, env))
    if action == "monitor_session":
        up = _compile(["-u"], config, cli_cmd, env, timeout)
        if not _ok(up):
            return _wrap("compile -u", up)
        mon = _bounded_monitor(cli_cmd, config, env)
        mon["upload_returncode"] = up.get("returncode")
        return _wrap("upload+monitor", mon)

    # ── informational `arduino-cli` subcommands ──
    if action == "system_info":
        return _wrap("version", _cli(["version", "--json"], cli_cmd, env, 60))
    if action == "boards":
        query = str(_cfg(config, "boards_query") or _cfg(config, "fqbn")).strip()
        args = ["board", "search", "--json"] + ([query] if query else [])
        return _wrap("board search", _cli(args + ai, cli_cmd, env, 120))
    if action == "device_list":
        return _wrap("board list", _cli(["board", "list", "--json"], cli_cmd, env, 60))
    if action == "core_list":
        return _wrap("core list", _cli(["core", "list", "--json"], cli_cmd, env, 60))
    if action == "core_search":
        query = str(_cfg(config, "core_spec") or _cfg(config, "boards_query")).strip()
        return _wrap("core search", _cli(["core", "search", "--json"] + ([query] if query else []) + ai, cli_cmd, env, 120))
    if action == "lib_list":
        return _wrap("lib list", _cli(["lib", "list", "--json"], cli_cmd, env, 60))
    if action == "lib_search":
        query = str(_cfg(config, "lib_spec") or _cfg(config, "boards_query")).strip()
        return _wrap("lib search", _cli(["lib", "search", "--json"] + ([query] if query else []), cli_cmd, env, 120))

    # ── index / package / core management (global state) ──
    if action == "core_update_index":
        return _wrap("core update-index", _cli(["core", "update-index"] + ai, cli_cmd, env, 300))
    if action == "lib_update_index":
        return _wrap("lib update-index", _cli(["lib", "update-index"], cli_cmd, env, 300))
    if action == "core_install":
        spec = str(_cfg(config, "core_spec")).strip()
        if not spec:
            return _wrap("core install", {"ok": False, "error": "core_install needs core_spec (e.g. 'arduino:avr' or 'esp32:esp32')."})
        return _wrap("core install", _cli(["core", "install", spec] + ai, cli_cmd, env, timeout))
    if action == "core_uninstall":
        spec = str(_cfg(config, "core_spec")).strip()
        if not spec:
            return _wrap("core uninstall", {"ok": False, "error": "core_uninstall needs core_spec."})
        return _wrap("core uninstall", _cli(["core", "uninstall", spec], cli_cmd, env, timeout))
    if action == "lib_install":
        spec = str(_cfg(config, "lib_spec")).strip()
        if not spec:
            return _wrap("lib install", {"ok": False, "error": "lib_install needs lib_spec (e.g. 'ArduinoJson' or 'ArduinoJson@7.0.4')."})
        return _wrap("lib install", _cli(["lib", "install", spec], cli_cmd, env, timeout))

    # ── build / flash (auto-install the core for the FQBN first) ──
    if action in ("build", "clean", "upload", "build_and_upload"):
        core = _ensure_core_installed(config, cli_cmd, env, timeout)
        if not core["ensured"]:
            return _wrap(action, {"ok": False, "returncode": 1,
                                  "error": f"core not ready: {core['detail']}",
                                  "stage": "core_install"})
        note = (f"[core: {core['detail']}]\n" if core.get("installed_now") else "")

        if action == "clean":
            res = _compile(["--clean"], config, cli_cmd, env, timeout)
        elif action in ("upload", "build_and_upload"):
            extra = ["-u"]
            if port:
                extra += ["-p", port]
            if programmer:
                extra += ["-P", programmer]
            res = _compile(extra, config, cli_cmd, env, timeout)
        else:  # build
            res = _compile(["--export-binaries"], config, cli_cmd, env, timeout)
        if note and isinstance(res, dict):
            res["stdout"] = note + str(res.get("stdout", ""))
        return _wrap("compile", res)

    valid = ", ".join(sorted(_ALL_ACTIONS))
    return _wrap(action, {"ok": False, "error": f"Unknown action {action!r}. Valid actions: {valid}."})


def _cli(args: list, cli_cmd: list, env: dict, timeout: float) -> dict:
    """Run `arduino-cli <args>` and normalize to {ok, returncode, stdout, stderr}."""
    rc, out, err = _run_cmd(list(cli_cmd) + list(args), env=env, timeout=timeout)
    return {"ok": rc == 0, "returncode": rc, "stdout": out, "stderr": err}


def _compile(extra: list, config: dict, cli_cmd: list, env: dict, timeout: float) -> dict:
    """`arduino-cli compile --fqbn <fqbn> <sketch_path>` plus any extra flags
    (-u/--clean/--export-binaries/-p/-P). Warnings level + build properties applied."""
    fqbn = str(_cfg(config, "fqbn")).strip()
    sketch_path = str(_cfg(config, "sketch_path")).strip()
    warnings = str(_cfg(config, "warnings", "none")).strip() or "none"
    args = ["compile", "--fqbn", fqbn, "--warnings", warnings]
    build_property = str(_cfg(config, "build_property")).strip()
    if build_property:
        for prop in re.split(r"\s*;\s*", build_property):
            if prop:
                args += ["--build-property", prop]
    extra_args = str(_cfg(config, "extra_compile_args")).strip()
    if extra_args:
        args += extra_args.split()
    args += list(extra)
    args += [sketch_path]
    return _cli(args, cli_cmd, env, timeout)


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
    """Emit an INI_SECTION_ARDUINER<<< block atomically (single logging.info call).

    Mirrors the ESP32er / STM32er / Kalier / Apirer convention so this agent's
    structured output is consumable by the Multi-Turn LLM (wrapped chat-agent
    run-result KV promotion) AND the Parametrizer canvas pipeline (registered in
    agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['arduiner'] and
    parametrizer.SECTION_AGENT_TYPES). The KV header field names MUST stay aligned
    with that registration."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_ARDUINER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_ARDUINER")


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

        logging.info("🔌 Arduiner AGENT STARTED (Arduino CLI / arduino-cli bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets: {target_agents}")

        env = get_agent_env()
        install_dir = str(_cfg(config, "arduino_cli_install_dir")).strip() or _default_install_dir()
        env = _cli_data_env(env, install_dir)
        timeout = float(_as_int(_cfg(config, "command_timeout", 900), 900))
        auto_bootstrap = _as_bool(_cfg(config, "auto_bootstrap", True), True)

        # ── Resolve `arduino-cli`, AUTO-BOOTSTRAPPING the binary when needed ──
        bootstrap_report = None
        boot_ok = True
        if action == "bootstrap":
            cli_cmd, bootstrap_report, boot_ok = _bootstrap_cli(config, env, install_dir)
        else:
            cli_cmd = _resolve_cli_cmd(config, env, install_dir)
            if not cli_cmd and auto_bootstrap:
                logging.info("🧰 Auto-bootstrap: arduino-cli not found — downloading...")
                cli_cmd, bootstrap_report, boot_ok = _bootstrap_cli(config, env, install_dir)

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
            pf = _preflight("validate", config, cli_cmd, env)
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
                preflight = _preflight(action, config, cli_cmd, env)
            if preflight is not None and not preflight["ok"]:
                body = ("PREFLIGHT REFUSED this operation (fail-safe — the environment could not be "
                        "guaranteed correct):\n\n" + _format_preflight_report(preflight))
                logging.error(f"❌ Preflight refused {action}: {preflight['fatals']}")
                envelope = {"ok": False, "tool": action,
                            "result": {"ok": False, "error": "preflight refused", "stage": "preflight"}}
            else:
                subject = str(_cfg(config, "sketch_path") or _cfg(config, "fqbn") or "(environment)")
                logging.info(f"Subject: {subject!r}")
                envelope = _run_action(action, config, cli_cmd, env, timeout)
                body = _result_body(envelope.get("result", {}))
                if preflight is not None and preflight.get("warnings"):
                    body = ("[preflight OK — warnings: " + " | ".join(preflight["warnings"]) + "]\n\n") + body

            if bootstrap_report is not None:
                body = _bootstrap_note(bootstrap_report, boot_ok) + body

        # ── Build the KV header (FIXED schema — keep aligned with _PARAMETRIZER_OUTPUT_FIELDS) ──
        result = envelope.get("result", {}) if isinstance(envelope.get("result"), dict) else {}
        sketch_path = str(result.get("sketch_path", "")) or str(_cfg(config, "sketch_path", ""))
        port = str(result.get("port", "")) or str(_cfg(config, "port", ""))
        fqbn = str(_cfg(config, "fqbn", ""))
        outcome = {
            "action": action,
            "tool": envelope.get("tool", action),
            "ok": "true" if envelope.get("ok") else "false",
            "returncode": result.get("returncode", ""),
            "success": "true" if envelope.get("ok") else "false",
            "fqbn": fqbn,
            "port": port,
            "sketch_path": sketch_path,
            "stage": result.get("stage", ""),
        }
        _emit_section(outcome, body or "(no output)")

        if envelope.get("ok"):
            logging.info(f"🏁 Arduiner {action} complete: success=true")
        else:
            logging.warning(f"⚠️ Arduiner {action} did not succeed. {result.get('error', '')}")

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
            f"🏁 Arduiner agent finished. Triggered {total_triggered}/{len(target_agents)} agents."
        )
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
