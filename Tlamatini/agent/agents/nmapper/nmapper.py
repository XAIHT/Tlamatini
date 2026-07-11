# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Nmapper Agent - LOCAL, USE-ONLY nmap bridge for pentesters / CTF recon.
# Action: Triggered by upstream -> resolve an ALREADY-INSTALLED nmap (never bundled/
#         redistributed) -> run ONE capability (selected by `action`) as a direct
#         subprocess -> parse -oX XML + capture -oN report -> emit INI_SECTION_NMAPPER
#         -> ALWAYS trigger downstream (success OR failure OR fail-safe refusal).
#
# USE-ONLY: nmap's NPSL forbids embedding nmap inside a redistributed product without a
# paid OEM licence, so Nmapper NEVER ships nmap. It resolves an nmap the user installed
# themselves (PATH -> Program Files -> %LOCALAPPDATA%\Tlamatini\nmap) and, only on
# explicit consent (`install` action / auto_install), downloads + launches the OFFICIAL
# FREE nmap self-installer from nmap.org — the USER's own download + admin install
# (which also brings Npcap). Like Discoverer / Kalier it invokes the CLI DIRECTLY (no
# MCP server) and is fully self-contained (stdlib only: subprocess + shutil + urllib +
# xml.etree) so it runs identically in source and frozen builds and never imports agent.*.
#
# DEFAULT = an UNPRIVILEGED TCP CONNECT SCAN (-sT): no Npcap, no admin, works the moment
# nmap is present. Raw-packet features (SYN -sS / -O / -sU) degrade gracefully on Windows
# without Npcap (auto-downgrade + warn, never crash). AUTHORIZED TARGETS ONLY.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core, inherited by every spawned
# agent via get_agent_env's os.environ.copy()) so every temp file this agent writes
# — including the downloaded nmap installer and scan output — lands under <app>/Temp,
# never C:\Temp / %TEMP% / the OS default. Fail-open when the handle is unset.
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
import time
import yaml
import shlex
import shutil
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
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


# ========================================
# HELPER FUNCTIONS (copied verbatim from discoverer.py / kalier.py boilerplate)
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


PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for _attempt in range(5):
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
    val = config.get(key, default)
    return default if val is None else val


def _as_int(raw, default: int) -> int:
    try:
        if isinstance(raw, bool):
            return default
        m = re.search(r"-?\d+", str(raw))
        return int(m.group(0)) if m else default
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


def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 900.0):
    """Run a subprocess and capture (returncode, stdout, stderr). Never raises;
    maps a missing executable to rc 127 and a timeout to rc 124."""
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL,
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
    except Exception as e:
        return 1, "", str(e)


# ========================================
# CONTRACT: actions
# ========================================

# Scan actions run nmap against a target; meta actions never scan.
_SCAN_ACTIONS = {"quick", "full", "top_ports", "version", "scripts", "host_discovery", "udp", "custom"}
_META_ACTIONS = {"validate", "install"}
_ALL_ACTIONS = _SCAN_ACTIONS | _META_ACTIONS
# Every scan action needs at least one target (or targets_file).
_NEED_TARGET = set(_SCAN_ACTIONS)

# Standard interactive-install locations for an nmap the USER installed.
_STANDARD_NMAP_PATHS = [
    r"C:\Program Files (x86)\Nmap\nmap.exe",
    r"C:\Program Files\Nmap\nmap.exe",
]

# Rejected from custom_args (argv is a list, not a shell — this is defence in depth).
_SHELL_METACHARS = set(";|&`$<>\n\r")


# ========================================
# PATH RESOLUTION + nmap / Npcap DISCOVERY (USE-ONLY — never downloads nmap for a scan)
# ========================================

def _app_root() -> str:
    """The Tlamatini app/install root. The core exports TLAMATINI_TEMP as <app>/Temp, so
    the parent of that is <install_dir>. Standalone fallback: a per-user writable dir."""
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if temp:
        return os.path.dirname(os.path.normpath(temp))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini")


def _localappdata_cache() -> str:
    """%LOCALAPPDATA%\\Tlamatini\\nmap — a portable nmap the user opted into (user-writable
    even under a frozen Program Files install)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "nmap")


def _default_output_dir(config: dict) -> str:
    explicit = str(_cfg(config, "output_dir")).strip()
    if explicit:
        return explicit
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    base = temp if temp else os.path.join(_app_root(), "Temp")
    return os.path.join(base, "Nmapper")


def _nmap_ok(exe: str, env: dict) -> bool:
    if not exe or not os.path.isfile(exe):
        return False
    rc, out, err = _run_cmd([exe, "--version"], env=env, timeout=30)
    return rc == 0 and "nmap" in (out + err).lower()


def _resolve_nmap(config: dict, env: dict) -> tuple:
    """Find an nmap the USER installed. USE-ONLY: never downloads/bundles the binary for a
    scan. Order: explicit config -> PATH -> Program Files -> %LOCALAPPDATA% cache.
    Returns (exe, source, ok)."""
    explicit = str(_cfg(config, "nmap_executable")).strip()
    if explicit and _nmap_ok(explicit, env):
        return explicit, "config", True
    which = shutil.which("nmap", path=env.get("PATH"))
    if which and _nmap_ok(which, env):
        return which, "path", True
    for p in _STANDARD_NMAP_PATHS:
        if _nmap_ok(p, env):
            return p, "program_files", True
    cache_root = _localappdata_cache()
    cand = os.path.join(cache_root, "nmap.exe")
    if _nmap_ok(cand, env):
        return cand, "localappdata", True
    # portable-zip layout: %LOCALAPPDATA%\Tlamatini\nmap\nmap-<ver>\nmap.exe
    if os.path.isdir(cache_root):
        try:
            for name in sorted(os.listdir(cache_root)):
                sub = os.path.join(cache_root, name, "nmap.exe")
                if _nmap_ok(sub, env):
                    return sub, "localappdata", True
        except Exception:
            pass
    return "", "none", False


def _npcap_present() -> bool:
    """Detect the Npcap raw-packet driver (needed for SYN / -O / raw UDP). On POSIX raw
    sockets are available to root, so treat as present."""
    if os.name != "nt":
        return True
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    for p in (
        os.path.join(sysroot, "System32", "Npcap", "wpcap.dll"),
        os.path.join(sysroot, "System32", "wpcap.dll"),
        os.path.join(sysroot, "SysWOW64", "Npcap", "wpcap.dll"),
    ):
        if os.path.isfile(p):
            return True
    return os.path.isdir(os.path.join(sysroot, "System32", "Npcap"))


# ========================================
# CONSENTED OFFICIAL-INSTALLER FETCH (USE, NOT REDISTRIBUTION)
# ========================================

def _install_url(config: dict) -> str:
    url = str(_cfg(config, "nmap_install_url")).strip()
    if url:
        return url
    ver = str(_cfg(config, "nmap_version", "7.99")).strip() or "7.99"
    return f"https://nmap.org/dist/nmap-{ver}-setup.exe"


def _download_file(url: str) -> tuple:
    """Download url to a temp file (under <app>/Temp). Returns (path, error)."""
    import urllib.request
    import tempfile
    try:
        logging.info(f"⬇️  Downloading the OFFICIAL nmap installer: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-Nmapper"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = resp.read()
        suffix = "_" + (os.path.basename(url) or "nmap-setup.exe")
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _run_installer(config: dict) -> dict:
    """USE, NOT REDISTRIBUTION: download the OFFICIAL FREE nmap self-installer to the
    user's machine and launch it (interactive, UAC-elevated — it also installs Npcap).
    Tlamatini never bundles nmap; the user consents to and completes the install."""
    url = _install_url(config)
    path, err = _download_file(url)
    if not path:
        return {"ok": False, "returncode": 1,
                "stdout": f"Could not download the nmap installer from {url}: {err}\n"
                          f"Install nmap yourself from https://nmap.org/download.html and re-run."}
    launched = False
    launch_err = ""
    try:
        if os.name == "nt":
            os.startfile(path)  # launch the installer: triggers UAC; the user completes the wizard (installs Npcap too)
            launched = True
        else:
            launch_err = "Automatic install is Windows-only; run the downloaded file manually."
    except Exception as e:
        launch_err = str(e)
    lines = [f"Official nmap installer downloaded from {url}", f"  saved to: {path}"]
    if launched:
        lines.append("  Launched the installer — accept the UAC prompt and complete the wizard.")
        lines.append("  This installs nmap AND Npcap (unlocking SYN / -O / raw UDP).")
        lines.append("  Re-run your scan once the installer finishes.")
    else:
        lines.append(f"  Could not auto-launch ({launch_err}). Run it yourself: {path}")
    return {"ok": launched, "returncode": 0 if launched else 1, "stdout": "\n".join(lines)}


# ========================================
# SAFETY PREFLIGHT (fail-safe gate; REFUSE, never crash)
# ========================================

def _reject_custom_args(custom: str) -> str:
    bad = sorted({c for c in custom if c in _SHELL_METACHARS})
    return " ".join(repr(c) for c in bad)


def _wide_cidr_note(target: str) -> str:
    m = re.match(r"^\s*\d{1,3}(?:\.\d{1,3}){3}\s*/\s*(\d{1,2})\s*$", target or "")
    if m:
        prefix = int(m.group(1))
        if prefix < 16:
            return (f"target is a very wide range (/{prefix}) — the scan may be slow AND may exceed your "
                    f"authorization. Confirm EVERY host in that range is in scope before scanning.")
    return ""


def _preflight(action: str, config: dict, nmap_exe: str, npcap: bool) -> dict:
    """Validate the environment for the selected action and REFUSE (fail-safe) on a fatal.
    Raw-packet features degrade gracefully on Windows without Npcap (warn + downgrade)."""
    report = {"action": action, "checks": {}, "warnings": [], "fatals": [], "ok": True, "downgrade": {}}
    checks = report["checks"]

    checks["nmap_resolvable"] = bool(nmap_exe)
    checks["npcap_present"] = npcap

    target = str(_cfg(config, "target")).strip()
    tfile = str(_cfg(config, "targets_file")).strip()
    needs_target = action in _NEED_TARGET
    if needs_target:
        checks["target_present"] = bool(target or tfile)
    if tfile:
        checks["targets_file_exists"] = os.path.isfile(tfile)

    technique = str(_cfg(config, "scan_technique", "connect")).strip().lower()
    os_detect = _as_bool(_cfg(config, "os_detect", False), False)

    # Raw-packet features need Npcap + admin on Windows; downgrade gracefully.
    if os.name == "nt" and not npcap:
        if technique in ("syn", "s", "-ss") and action not in ("udp", "host_discovery"):
            report["warnings"].append(
                "SYN scan (-sS) needs Npcap + admin — downgrading to a TCP connect scan (-sT). "
                "For real SYN stealth run action='install' (installs Npcap; needs admin).")
            report["downgrade"]["technique"] = "connect"
        if os_detect:
            report["warnings"].append(
                "OS detection (-O) needs Npcap + admin — dropping it. Run action='install' to enable it.")
            report["downgrade"]["os_detect"] = False

    fatals = report["fatals"]
    if not nmap_exe:
        fatals.append(
            "nmap is not installed on this machine. Nmapper NEVER bundles nmap (licence). Run "
            "action='install' (or set auto_install: true) to fetch + launch the official FREE nmap "
            "installer, OR install nmap yourself from https://nmap.org/download.html, then re-run.")
    if needs_target and not (target or tfile):
        fatals.append(f"action '{action}' needs a target — set `target` (host/ip/cidr/hostname) or `targets_file`.")
    if tfile and not os.path.isfile(tfile):
        fatals.append(f"targets_file not found: {tfile!r}")
    if action == "udp" and os.name == "nt" and not npcap:
        fatals.append(
            "UDP scan (-sU) needs raw packets (Npcap) + admin and has NO connect-scan fallback. "
            "Run action='install' (installs Npcap; needs admin) first.")
    if action == "custom":
        bad = _reject_custom_args(str(_cfg(config, "custom_args")).strip())
        if bad:
            fatals.append(f"custom_args contains disallowed shell metacharacter(s): {bad}")

    cidr_note = _wide_cidr_note(target)
    if cidr_note:
        report["warnings"].append(cidr_note)

    report["ok"] = not fatals
    return report


def _format_preflight_report(report: dict) -> str:
    if not report:
        return "No preflight was performed."
    lines = [
        f"action  : {report.get('action', '')}",
        f"overall : {'READY' if report.get('ok') else 'REFUSED (fail-safe)'}",
        "",
        "checks:",
    ]
    for name, value in report.get("checks", {}).items():
        lines.append(f"  [{'OK' if value else 'XX'}] {name}: {value}")
    for warning in report.get("warnings", []):
        lines.append(f"  [!] WARNING: {warning}")
    for fatal in report.get("fatals", []):
        lines.append(f"  [X] FATAL  : {fatal}")
    return "\n".join(lines)


# ========================================
# ARGV BUILDER + OUTPUT PARSING
# ========================================

def _timing_flag(config: dict) -> str:
    t = str(_cfg(config, "timing", "T4")).strip().upper().lstrip("-")
    if not t.startswith("T"):
        t = "T" + t
    return "-" + t if t in ("T0", "T1", "T2", "T3", "T4", "T5") else "-T4"


def _port_args(action: str, ports: str, top_ports: int) -> list:
    if ports:
        return ["-p", ports]
    if action == "full":
        return ["-p-"]
    if action in ("quick", "top_ports", "udp"):
        return ["--top-ports", str(top_ports)]
    return []  # version / scripts / custom with no ports -> nmap's default 1000


def _output_paths(config: dict) -> tuple:
    out_dir = _default_output_dir(config)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    subject = str(_cfg(config, "target")).strip() or "scan"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", subject)[:50] or "scan"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = os.path.join(out_dir, f"nmapper_{safe}_{stamp}")
    return base + ".xml", base + ".nmap"


def _build_argv(action: str, exe: str, config: dict, xml_path: str, normal_path: str, downgrade: dict) -> list:
    technique = downgrade.get("technique") or str(_cfg(config, "scan_technique", "connect")).strip().lower()
    os_detect = downgrade.get("os_detect", _as_bool(_cfg(config, "os_detect", False), False))
    version_detect = _as_bool(_cfg(config, "version_detect", True), True)
    default_scripts = _as_bool(_cfg(config, "default_scripts", True), True)
    skip_disco = _as_bool(_cfg(config, "skip_host_discovery", True), True)
    ports = str(_cfg(config, "ports")).strip()
    top_ports = _as_int(_cfg(config, "top_ports", 1000), 1000)
    nse = str(_cfg(config, "nse_scripts")).strip()
    min_rate = _as_int(_cfg(config, "min_rate", 0), 0)
    tfile = str(_cfg(config, "targets_file")).strip()
    target = str(_cfg(config, "target")).strip()

    a = [exe]

    # scan technique
    if action == "host_discovery":
        a.append("-sn")
    elif action == "udp":
        a.append("-sU")
    else:
        a.append("-sS" if technique in ("syn", "s", "-ss") else "-sT")

    # version / scripts
    if version_detect and action in ("quick", "full", "version", "custom"):
        a.append("-sV")
    if default_scripts and action in ("quick", "full"):
        a.append("-sC")
    if action == "scripts":
        a += ["--script", nse or "default"]

    # ports (not for host_discovery)
    if action != "host_discovery":
        a += _port_args(action, ports, top_ports)

    # OS detection
    if os_detect and action != "host_discovery":
        a.append("-O")

    # skip host discovery (-Pn)
    if skip_disco and action != "host_discovery":
        a.append("-Pn")

    # timing
    a.append(_timing_flag(config))
    if min_rate > 0:
        a += ["--min-rate", str(min_rate)]

    # structured + human output
    a += ["-oX", xml_path, "-oN", normal_path]

    # target(s)
    if tfile:
        a += ["-iL", tfile]
    elif target:
        a.append(target)

    # custom escape hatch (already validated in preflight)
    if action == "custom":
        extra = str(_cfg(config, "custom_args")).strip()
        if extra:
            try:
                a += shlex.split(extra, posix=False)
            except Exception:
                a += extra.split()
    return a


def _parse_xml(xml_path: str) -> tuple:
    """Parse nmap -oX output into (hosts_up, [open_port_labels])."""
    hosts_up = 0
    open_ports = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        for host in root.findall("host"):
            status = host.find("status")
            if status is not None and status.get("state") == "up":
                hosts_up += 1
            addr = ""
            addr_el = host.find("address")
            if addr_el is not None:
                addr = addr_el.get("addr", "")
            ports_el = host.find("ports")
            if ports_el is None:
                continue
            for port in ports_el.findall("port"):
                state = port.find("state")
                if state is None or state.get("state") != "open":
                    continue
                pid = port.get("portid", "")
                proto = port.get("protocol", "")
                svc_el = port.find("service")
                svc = svc_el.get("name", "") if svc_el is not None else ""
                ver = ""
                if svc_el is not None:
                    ver = " ".join(x for x in (svc_el.get("product", ""), svc_el.get("version", "")) if x).strip()
                label = f"{addr + ':' if addr else ''}{pid}/{proto}"
                if svc:
                    label += f" {svc}"
                if ver:
                    label += f" ({ver})"
                open_ports.append(label)
    except Exception:
        pass
    return hosts_up, open_ports


# ========================================
# STRUCTURED OUTPUT
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_NMAPPER<<< block atomically (single logging.info call). KV
    header field names MUST stay aligned with agent_contracts._PARAMETRIZER_OUTPUT_FIELDS
    ['nmapper'] and parametrizer.SECTION_AGENT_TYPES."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_NMAPPER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_NMAPPER")


def _ports_label(action: str, config: dict) -> str:
    ports = str(_cfg(config, "ports")).strip()
    if ports:
        return ports
    if action == "full":
        return "1-65535"
    if action in ("quick", "top_ports", "udp"):
        return "top-" + str(_as_int(_cfg(config, "top_ports", 1000), 1000))
    return "default"


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
        action = str(_cfg(config, 'action', 'quick') or 'quick').strip().lower()

        logging.info("🛰️ NMAPPER AGENT STARTED (local use-only nmap bridge)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets (downstream): {target_agents}")

        env = get_agent_env()
        timeout = float(_as_int(_cfg(config, "command_timeout", 900), 900))
        nmap_exe, source, resolved = _resolve_nmap(config, env)
        npcap = _npcap_present()
        logging.info(f"nmap: {nmap_exe or '(NOT installed)'} [source={source}]  npcap={npcap}")

        outcome = {
            "action": action, "target": "", "scan_technique": "", "ports": "",
            "return_code": "", "success": "false", "hosts_up": "", "open_ports": "",
            "npcap_present": "true" if npcap else "false", "xml_path": "",
            "output_path": "", "stage": "run",
        }
        outcome["target"] = str(_cfg(config, "target") or _cfg(config, "targets_file") or "").strip()
        outcome["scan_technique"] = str(_cfg(config, "scan_technique", "connect")).strip().lower()
        body = ""
        ok = False

        if action not in _ALL_ACTIONS:
            body = f"Unknown action {action!r}. Valid: {', '.join(sorted(_ALL_ACTIONS))}."
            outcome["stage"] = "error"
            logging.error("❌ " + body)

        elif action == "validate":
            lines = [
                f"nmap resolved : {nmap_exe or '(NOT installed)'}   [source: {source}]",
                f"npcap present : {npcap}  ({'raw scans available (SYN/-O/UDP)' if npcap else 'connect scans only (-sT)'})",
                f"output_dir    : {_default_output_dir(config)}",
                "install       : run action='install' (or set auto_install) to fetch + launch the "
                "official free nmap installer (admin/UAC; brings Npcap).",
            ]
            if nmap_exe:
                rc, out, err = _run_cmd([nmap_exe, "--version"], env=env, timeout=30)
                lines += ["", (out or err).strip()]
                ok = rc == 0
            else:
                lines += ["", "nmap is NOT installed — Nmapper never bundles it (licence)."]
                ok = False
            body = "\n".join(lines)
            outcome.update({"return_code": 0 if ok else 1, "stage": "validate"})

        elif action == "install":
            res = _run_installer(config)
            ok = res["ok"]
            body = res["stdout"]
            outcome.update({"return_code": res["returncode"], "stage": "install"})

        else:
            # ── a scan action: preflight (fail-safe) -> run nmap -> parse ──
            do_preflight = _as_bool(_cfg(config, "preflight", True), True)
            pf = _preflight(action, config, nmap_exe, npcap) if do_preflight else {"ok": True, "warnings": [], "downgrade": {}}

            if do_preflight and not pf["ok"]:
                if not nmap_exe and _as_bool(_cfg(config, "auto_install", False), False):
                    inst = _run_installer(config)
                    body = ("nmap was missing; auto_install attempted the official installer:\n\n"
                            + inst["stdout"] + "\n\n(Re-run the scan once the installer finishes.)")
                    outcome.update({"return_code": 1, "stage": "install"})
                    logging.warning("⚠️ nmap missing — launched the official installer (auto_install).")
                else:
                    body = "PREFLIGHT REFUSED (fail-safe):\n\n" + _format_preflight_report(pf)
                    outcome.update({"return_code": 1, "stage": "preflight"})
                    logging.error(f"❌ Preflight refused {action}: {pf['fatals']}")
            else:
                downgrade = pf.get("downgrade", {})
                xml_path, normal_path = _output_paths(config)
                argv = _build_argv(action, nmap_exe, config, xml_path, normal_path, downgrade)
                logging.info("🔎 nmap: " + " ".join(argv))
                rc, out, err = _run_cmd(argv, env=env, timeout=timeout)
                hosts_up, open_ports = _parse_xml(xml_path)
                ok = rc == 0

                warn = ""
                if pf.get("warnings"):
                    warn = "[preflight: " + " | ".join(pf["warnings"]) + "]\n\n"
                body_parts = []
                if os.path.isfile(normal_path):
                    try:
                        with open(normal_path, "r", encoding="utf-8", errors="replace") as f:
                            txt = f.read().strip()
                        if txt:
                            body_parts.append(txt)
                    except Exception:
                        pass
                if not body_parts and out.strip():
                    body_parts.append(out.strip())
                if err.strip():
                    body_parts.append("[stderr]\n" + err.strip())
                body = (warn + "\n\n".join(body_parts))[:60000] or "(no output)"

                eff_tech = downgrade.get("technique") or outcome["scan_technique"]
                if action == "udp":
                    eff_tech = "udp"
                elif action == "host_discovery":
                    eff_tech = "ping"
                outcome.update({
                    "return_code": rc,
                    "scan_technique": eff_tech,
                    "ports": _ports_label(action, config),
                    "hosts_up": hosts_up,
                    "open_ports": "; ".join(open_ports[:40]) if open_ports else "(none)",
                    "xml_path": xml_path,
                    "output_path": normal_path,
                    "stage": "run",
                })

        outcome["success"] = "true" if ok else "false"
        _emit_section(outcome, body or "(no output)")

        if ok:
            logging.info(f"🏁 Nmapper {action} complete: success=true")
        else:
            logging.warning(f"⚠️ Nmapper {action} did not succeed (stage={outcome['stage']}).")

        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Nmapper agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
