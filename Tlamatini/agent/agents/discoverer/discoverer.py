# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Discoverer Agent - ProjectDiscovery suite bridge (subfinder/httpx/naabu/katana/nuclei/cvemap)
# Action: Triggered by upstream -> resolve the requested PD tool (auto-bootstrapping a
#         PRIVATE Go compiler into <install_dir>/Go and `go install`-ing the tool into
#         <install_dir>/Go/bin-tools when absent) -> run ONE tool (selected by `tool`)
#         as a direct subprocess -> capture stdout + JSON output -> emit
#         INI_SECTION_DISCOVERER -> ALWAYS trigger downstream (success OR failure).
#
# Discoverer integrates the ProjectDiscovery suite (https://github.com/projectdiscovery).
# Like ESP32er / Arduiner / Kalier it invokes the tools' own CLIs DIRECTLY (no MCP
# server) and is fully self-contained (stdlib only: subprocess + urllib + zipfile +
# tarfile + shutil + json + threading) so it works identically in source and frozen
# builds and never imports from agent.* (pool agents are standalone subprocesses).
#
# ZERO-CONFIG PRIVATE GO TOOLCHAIN: with the tool not yet installed and go_bootstrap
# true, Discoverer DOWNLOADS the official Go release zip from https://go.dev/dl/ into
# <install_dir>/Go (GOROOT) and `go install`s the requested ProjectDiscovery tool into
# <install_dir>/Go/bin-tools (GOBIN). No system Go, no PATH mutation — the user
# installs only Tlamatini. AUTHORIZED TARGETS ONLY.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core, inherited by every spawned
# agent via get_agent_env's os.environ.copy()) so every temp file this agent writes
# — including the downloaded Go release archive — lands under <app>/Temp, never
# C:\Temp / %TEMP% / the OS default. Fail-open when the handle is unset.
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
import shlex
import shutil
import logging
import platform
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
# HELPER FUNCTIONS (copied verbatim from esp32er.py / kalier.py boilerplate)
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


def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 1800.0):
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
# CONTRACT: tools, meta actions, go-install module paths
# ========================================

# ProjectDiscovery `go install` module paths (compiled by the private Go toolchain).
# cvemap is now shipped as `vulnx`; the historical cvemap module path is kept and can
# be overridden via extra_args / a future config key if ProjectDiscovery moves it.
_TOOL_MODULES = {
    "subfinder": "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
    "httpx":     "github.com/projectdiscovery/httpx/cmd/httpx@latest",
    "naabu":     "github.com/projectdiscovery/naabu/v2/cmd/naabu@latest",
    "katana":    "github.com/projectdiscovery/katana/cmd/katana@latest",
    "nuclei":    "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
    "cvemap":    "github.com/projectdiscovery/cvemap/cmd/cvemap@latest",
}

_SCAN_TOOLS = set(_TOOL_MODULES.keys())
_META_ACTIONS = {"bootstrap", "validate", "update_templates", "list_tools"}
_ALL_SELECTIONS = _SCAN_TOOLS | _META_ACTIONS

# Tools that REQUIRE a target (subdomain/host/url). cvemap searches the CVE DB instead.
_NEED_TARGET = {"subfinder", "httpx", "naabu", "katana", "nuclei"}

# httpx probe csv -> flag mapping.
_HTTPX_PROBE_FLAGS = {
    "status_code": "-sc", "title": "-title", "tech_detect": "-td", "server": "-server",
    "web_server": "-server", "content_length": "-cl", "content_type": "-ct",
    "location": "-location", "cdn": "-cdn", "ip": "-ip", "method": "-method",
    "response_time": "-rt", "favicon": "-favicon", "jarm": "-jarm",
}


# ========================================
# PATH RESOLUTION (<install_dir>/Go and friends)
# ========================================

def _app_root() -> str:
    """The Tlamatini app/install root. The core exports TLAMATINI_TEMP as <app>/Temp,
    so the parent of that is <install_dir> — exactly where the Go toolchain goes."""
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if temp:
        return os.path.dirname(os.path.normpath(temp))
    # Standalone fallback: a per-user, writable location.
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini")


def _default_go_dir(config: dict) -> str:
    explicit = str(_cfg(config, "go_dir")).strip()
    return explicit or os.path.join(_app_root(), "Go")


def _default_gobin(config: dict, go_dir: str) -> str:
    explicit = str(_cfg(config, "tools_bin")).strip()
    return explicit or os.path.join(go_dir, "bin-tools")


def _default_output_dir(config: dict) -> str:
    explicit = str(_cfg(config, "output_dir")).strip()
    if explicit:
        return explicit
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    base = temp if temp else os.path.join(_app_root(), "Temp")
    return os.path.join(base, "Discoverer")


def _exe_suffix() -> str:
    return ".exe" if os.name == "nt" else ""


def _go_exe_path(go_dir: str) -> str:
    return os.path.join(go_dir, "bin", "go" + _exe_suffix())


def _tool_exe_path(gobin: str, tool: str) -> str:
    # cvemap's binary may be named `cvemap` (historical) — keep the tool key as the name.
    return os.path.join(gobin, tool + _exe_suffix())


# ========================================
# GO TOOLCHAIN BOOTSTRAP (download + extract the official Go release)
# ========================================

def _go_os() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _go_arch() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64", "x64"):
        return "amd64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86", "i386", "i686"):
        return "386"
    return "amd64"


def _go_archive_name(version: str, goos: str, arch: str) -> str:
    ext = "zip" if goos == "windows" else "tar.gz"
    return f"go{version}.{goos}-{arch}.{ext}"


def _go_version(go_cmd: list, env: dict) -> tuple:
    rc, out, err = _run_cmd(list(go_cmd) + ["version"], env=env, timeout=60)
    return rc == 0, (out or err or "").strip()


def _download_file(url: str) -> tuple:
    """Download url to a temp file. Returns (path, error)."""
    import urllib.request
    import tempfile
    try:
        logging.info(f"⬇️  Downloading: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-Discoverer"})
        with urllib.request.urlopen(request, timeout=600) as resp:
            data = resp.read()
        suffix = "_" + os.path.basename(url)
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _extract_go(archive_path: str, go_dir: str) -> tuple:
    """Extract the Go release (top-level `go/`) and place it AT go_dir. (ok, error)."""
    import tempfile
    import zipfile
    import tarfile
    staging = tempfile.mkdtemp(prefix="go-extract-")
    try:
        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as z:
                z.extractall(staging)
        else:
            with tarfile.open(archive_path, "r:gz") as t:
                t.extractall(staging)
        inner = os.path.join(staging, "go")
        if not os.path.isdir(inner):
            return False, "archive did not contain a top-level 'go' directory"
        if os.path.isdir(go_dir):
            shutil.rmtree(go_dir, ignore_errors=True)
        os.makedirs(os.path.dirname(go_dir) or ".", exist_ok=True)
        shutil.move(inner, go_dir)
        return True, ""
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _bootstrap_go(config: dict, go_dir: str, env: dict) -> tuple:
    """Ensure a private Go compiler exists at go_dir. Returns (go_exe, report, ok)."""
    report = {"steps": [], "go_dir": go_dir}
    version = str(_cfg(config, "go_version", "1.24.5")).strip() or "1.24.5"
    do_update = _as_bool(_cfg(config, "auto_update", False), False)
    go_exe = _go_exe_path(go_dir)
    try:
        if os.path.isfile(go_exe) and not do_update:
            ok, ver = _go_version([go_exe], env)
            report["steps"].append(("resolve", {"ok": ok, "action": "present", "version": ver}))
            report["ok"] = ok
            return (go_exe if ok else ""), report, ok

        goos, arch = _go_os(), _go_arch()
        archive = _go_archive_name(version, goos, arch)
        url = "https://go.dev/dl/" + archive
        path, dl_err = _download_file(url)
        if not path:
            report["steps"].append(("download", {"ok": False, "action": archive, "error": dl_err, "url": url}))
            report["ok"] = False
            return "", report, False
        report["steps"].append(("download", {"ok": True, "action": archive}))

        ok_x, x_err = _extract_go(path, go_dir)
        try:
            os.remove(path)
        except Exception:
            pass
        if not ok_x:
            report["steps"].append(("extract", {"ok": False, "error": x_err}))
            report["ok"] = False
            return "", report, False
        report["steps"].append(("extract", {"ok": True, "action": go_dir}))

        ok_v, ver = _go_version([go_exe], env)
        report["steps"].append(("validate", {"ok": ok_v, "version": ver}))
        report["ok"] = ok_v
        return (go_exe if ok_v else ""), report, ok_v
    except Exception as e:  # bootstrap must NEVER raise into main()
        logging.error(f"❌ Go bootstrap crashed: {e}")
        report["ok"] = False
        report["error"] = str(e)
        return "", report, False


def _install_tool(tool: str, go_exe: str, gobin: str, env: dict, timeout: float) -> dict:
    """`go install` one ProjectDiscovery tool into GOBIN. Returns a normalized dict."""
    module = _TOOL_MODULES.get(tool)
    if not module:
        return {"ok": False, "returncode": 1, "error": f"no go-install module known for {tool!r}"}
    logging.info(f"🧰 go install {module}  ->  {gobin}")
    rc, out, err = _run_cmd([go_exe, "install", module], env=env, timeout=timeout)
    return {"ok": rc == 0, "returncode": rc, "stdout": out, "stderr": err, "module": module}


def _go_env(base_env: dict, go_dir: str, gobin: str, config: dict) -> dict:
    """Build the environment for go install + tool runs: private GOROOT/GOPATH/GOBIN,
    GOCACHE under Temp, plus the optional PDCP key and subfinder provider config."""
    env = dict(base_env)
    gopath = os.path.join(go_dir, "gopath")
    env["GOROOT"] = go_dir
    env["GOPATH"] = gopath
    env["GOBIN"] = gobin
    env["GOMODCACHE"] = os.path.join(gopath, "pkg", "mod")
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    env["GOCACHE"] = os.path.join(temp, "go-build") if temp else os.path.join(go_dir, "gocache")
    env["GOTELEMETRY"] = "off"
    goroot_bin = os.path.join(go_dir, "bin")
    env["PATH"] = goroot_bin + os.pathsep + gobin + os.pathsep + env.get("PATH", "")
    for d in (gopath, gobin, env["GOMODCACHE"], env["GOCACHE"]):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
    key = str(_cfg(config, "pdcp_api_key")).strip()
    if key:
        env["PDCP_API_KEY"] = key
    pc = str(_cfg(config, "subfinder_provider_config")).strip()
    if pc:
        env["SUBFINDER_PROVIDER_CONFIG"] = pc
    return env


def _resolve_tool(tool: str, gobin: str, env: dict) -> str:
    """Find an invocable tool binary: private GOBIN -> pdtm bin -> PATH. '' if none."""
    cand = _tool_exe_path(gobin, tool)
    if os.path.isfile(cand):
        return cand
    pdtm = os.path.join(os.path.expanduser("~"), ".pdtm", "go", "bin", tool + _exe_suffix())
    if os.path.isfile(pdtm):
        return pdtm
    which = shutil.which(tool, path=env.get("PATH"))
    return which or ""


def _ensure_tool(tool: str, config: dict, go_dir: str, gobin: str, env: dict, timeout: float) -> tuple:
    """Resolve the tool, bootstrapping the Go toolchain + `go install`-ing it if absent.
    Returns (tool_exe, report, ok)."""
    report = {"steps": [], "tool": tool}
    do_update = _as_bool(_cfg(config, "auto_update", False), False)

    existing = _resolve_tool(tool, gobin, env)
    if existing and not do_update:
        report["steps"].append(("resolve", {"ok": True, "action": "present", "path": existing}))
        report["ok"] = True
        return existing, report, True

    if not _as_bool(_cfg(config, "go_bootstrap", True), True):
        report["steps"].append(("resolve", {"ok": bool(existing), "action": "no-bootstrap", "path": existing}))
        report["ok"] = bool(existing)
        return existing, report, bool(existing)

    go_exe, go_report, go_ok = _bootstrap_go(config, go_dir, env)
    report["go"] = go_report
    if not go_ok:
        report["ok"] = False
        return "", report, False

    inst = _install_tool(tool, go_exe, gobin, env, timeout)
    report["steps"].append(("go-install", {
        "ok": inst["ok"], "module": inst.get("module", ""),
        "returncode": inst.get("returncode"), "stderr": (inst.get("stderr") or "")[-800:],
    }))
    resolved = _resolve_tool(tool, gobin, env)
    report["ok"] = bool(resolved)
    return resolved, report, bool(resolved)


def _format_bootstrap_report(report: dict) -> str:
    if not report:
        return "No bootstrap was performed."
    lines = []
    go_rep = report.get("go")
    if go_rep:
        lines.append(f"Go toolchain @ {go_rep.get('go_dir', '')}  ({'OK' if go_rep.get('ok') else 'FAILED'})")
        for name, res in go_rep.get("steps", []):
            head = f"  [{'OK' if res.get('ok') else 'XX'}] go.{name}: {res.get('action', '')}"
            if res.get("version"):
                head += f" ({res['version']})"
            if not res.get("ok") and res.get("error"):
                head += f" — {res['error']}"
            lines.append(head)
    lines.append(f"Tool '{report.get('tool', '')}'  ({'OK' if report.get('ok') else 'FAILED'})")
    for name, res in report.get("steps", []):
        head = f"  [{'OK' if res.get('ok') else 'XX'}] {name}: {res.get('action', res.get('module', ''))}"
        if "returncode" in res and res.get("returncode") is not None:
            head += f" rc={res.get('returncode')}"
        if res.get("path"):
            head += f" -> {res['path']}"
        lines.append(head)
        if not res.get("ok") and res.get("stderr"):
            lines.append(f"        stderr: {res['stderr'][-400:]}")
    if report.get("error"):
        lines.append(f"\nbootstrap error: {report['error']}")
    return "\n".join(lines)


# ========================================
# SAFETY PREFLIGHT (fail-safe gate)
# ========================================

def _chrome_present() -> bool:
    if shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium"):
        return True
    for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome", "/usr/bin/chromium",
    ):
        if os.path.isfile(p):
            return True
    return False


def _preflight(tool: str, config: dict, tool_exe: str) -> dict:
    """Validate the environment for the selected tool and REFUSE (fail-safe) on a fatal."""
    report = {"tool": tool, "checks": {}, "warnings": [], "fatals": [], "ok": True}
    checks = report["checks"]

    tool_ok = bool(tool_exe)
    go_bootstrap = _as_bool(_cfg(config, "go_bootstrap", True), True)
    checks["tool_resolvable"] = tool_ok
    checks["go_bootstrap_enabled"] = go_bootstrap

    target = str(_cfg(config, "target")).strip()
    tfile = str(_cfg(config, "targets_file")).strip()
    needs_target = tool in _NEED_TARGET
    if needs_target:
        checks["target_present"] = bool(target or tfile)
    if tfile:
        checks["targets_file_exists"] = os.path.isfile(tfile)

    if tool == "naabu":
        scan_type = str(_cfg(config, "naabu_scan_type") or "c").strip().lower()
        if scan_type in ("s", "syn") and os.name == "nt":
            report["warnings"].append(
                "naabu SYN scan (scan_type 's') needs Npcap + admin on Windows; if it fails, "
                "use scan_type 'c' (connect-scan, the default — no Npcap required).")
    if tool in ("katana", "nuclei"):
        headless = _as_bool(_cfg(config, "katana_headless", False), False)
        if tool == "katana" and headless and not _chrome_present():
            report["warnings"].append(
                "katana headless mode (katana_headless) needs a local Chrome — none found on PATH.")

    fatals = report["fatals"]
    if not tool_ok and not go_bootstrap:
        fatals.append(
            f"The '{tool}' binary is not installed and go_bootstrap is off. Enable go_bootstrap so "
            f"Discoverer installs a private Go toolchain and compiles it, or install {tool} yourself.")
    if needs_target and not (target or tfile):
        fatals.append(
            f"tool '{tool}' needs a target — set `target` (domain/url/host/ip/cidr) or `targets_file`.")
    if tfile and not os.path.isfile(tfile):
        fatals.append(f"targets_file not found: {tfile!r}")

    report["ok"] = not fatals
    return report


def _format_preflight_report(report: dict) -> str:
    if not report:
        return "No preflight was performed."
    lines = [
        f"tool    : {report.get('tool', '')}",
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
# ARGV BUILDERS + RUN
# ========================================

def _output_path(tool: str, config: dict) -> str:
    out_dir = _default_output_dir(config)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    subject = (str(_cfg(config, "target")).strip() or str(_cfg(config, "cvemap_id")).strip()
               or str(_cfg(config, "cvemap_product")).strip() or "scan")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", subject)[:60] or "scan"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    ext = "jsonl" if tool in ("nuclei", "katana") else "json" if _as_bool(_cfg(config, "json_output", True), True) else "txt"
    return os.path.join(out_dir, f"{tool}_{safe}_{stamp}.{ext}")


def _build_argv(tool: str, exe: str, config: dict, out_path: str) -> list:
    target = str(_cfg(config, "target")).strip()
    tfile = str(_cfg(config, "targets_file")).strip()
    json_out = _as_bool(_cfg(config, "json_output", True), True)
    rl = _as_int(_cfg(config, "rate_limit", 0), 0)
    cc = _as_int(_cfg(config, "concurrency", 0), 0)
    extra = str(_cfg(config, "extra_args")).strip()
    a = [exe]

    if tool == "subfinder":
        a += (["-dL", tfile] if tfile else (["-d", target] if target else []))
        if json_out:
            a += ["-oJ"]
        if out_path:
            a += ["-o", out_path]
        if _as_bool(_cfg(config, "subfinder_all_sources", False), False):
            a += ["-all"]
        sources = str(_cfg(config, "subfinder_sources")).strip()
        if sources:
            a += ["-s", sources]
        if _as_bool(_cfg(config, "subfinder_include_ip", False), False):
            a += ["-oI"]
        if rl:
            a += ["-rl", str(rl)]
        if cc:
            a += ["-t", str(cc)]
        a += ["-silent"]

    elif tool == "httpx":
        a += (["-l", tfile] if tfile else (["-u", target] if target else []))
        if json_out:
            a += ["-json"]
        if out_path:
            a += ["-o", out_path]
        probes = str(_cfg(config, "httpx_probes")).strip()
        for p in [x.strip() for x in probes.split(",") if x.strip()]:
            flag = _HTTPX_PROBE_FLAGS.get(p)
            if flag and flag not in a:
                a.append(flag)
        if _as_bool(_cfg(config, "httpx_follow_redirects", False), False):
            a += ["-fr"]
        if rl:
            a += ["-rl", str(rl)]
        if cc:
            a += ["-t", str(cc)]

    elif tool == "naabu":
        a += (["-l", tfile] if tfile else (["-host", target] if target else []))
        if json_out:
            a += ["-json"]
        if out_path:
            a += ["-o", out_path]
        ports = str(_cfg(config, "naabu_ports")).strip()
        if ports:
            a += ["-p", ports]
        else:
            a += ["-top-ports", str(_cfg(config, "naabu_top_ports") or "100").strip()]
        a += ["-s", str(_cfg(config, "naabu_scan_type") or "c").strip()]
        if rl:
            a += ["-rate", str(rl)]
        if cc:
            a += ["-c", str(cc)]

    elif tool == "katana":
        a += (["-list", tfile] if tfile else (["-u", target] if target else []))
        if json_out:
            a += ["-jsonl"]
        if out_path:
            a += ["-o", out_path]
        a += ["-d", str(_as_int(_cfg(config, "katana_depth", 3), 3))]
        if _as_bool(_cfg(config, "katana_js_crawl", True), True):
            a += ["-jc"]
        if _as_bool(_cfg(config, "katana_headless", False), False):
            a += ["-hl"]
        if rl:
            a += ["-rl", str(rl)]
        if cc:
            a += ["-c", str(cc)]

    elif tool == "nuclei":
        a += (["-l", tfile] if tfile else (["-u", target] if target else []))
        if json_out:
            a += ["-jsonl"]
        if out_path:
            a += ["-o", out_path]
        templates = str(_cfg(config, "nuclei_templates")).strip()
        if templates:
            a += ["-t", templates]
        severity = str(_cfg(config, "nuclei_severity")).strip()
        if severity:
            a += ["-s", severity]
        tags = str(_cfg(config, "nuclei_tags")).strip()
        if tags:
            a += ["-tags", tags]
        ids = str(_cfg(config, "nuclei_template_ids")).strip()
        if ids:
            a += ["-id", ids]
        if _as_bool(_cfg(config, "nuclei_automatic_scan", False), False):
            a += ["-as"]
        if rl:
            a += ["-rl", str(rl)]
        if cc:
            a += ["-c", str(cc)]
        if _as_bool(_cfg(config, "cloud_upload", False), False):
            a += ["-pd"]
        a += ["-duc", "-nc"]

    elif tool == "cvemap":
        cid = str(_cfg(config, "cvemap_id")).strip()
        prod = str(_cfg(config, "cvemap_product")).strip()
        sev = str(_cfg(config, "cvemap_severity")).strip()
        if cid:
            a += ["-id", cid]
        if prod:
            a += ["-product", prod]
        if sev:
            a += ["-severity", sev]
        if json_out:
            a += ["-json"]
        if out_path:
            a += ["-o", out_path]

    if extra:
        try:
            a += shlex.split(extra, posix=False)
        except Exception:
            a += extra.split()
    return a


def _findings_count(out_path: str, stdout: str) -> int:
    """Count result lines: JSONL file lines, or JSON array length, or stdout lines."""
    try:
        if out_path and os.path.isfile(out_path):
            with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read().strip()
            if not text:
                return 0
            if text[0] == "[":
                try:
                    data = json.loads(text)
                    return len(data) if isinstance(data, list) else 1
                except Exception:
                    pass
            return sum(1 for ln in text.splitlines() if ln.strip())
    except Exception:
        pass
    return sum(1 for ln in (stdout or "").splitlines() if ln.strip())


def _run_scan(tool: str, tool_exe: str, config: dict, env: dict, timeout: float) -> dict:
    out_path = _output_path(tool, config)
    argv = _build_argv(tool, tool_exe, config, out_path)
    logging.info(f"🔎 {tool}: {' '.join(argv)}")
    rc, out, err = _run_cmd(argv, env=env, timeout=timeout)
    body_parts = []
    if out.strip():
        body_parts.append(out.strip())
    if err.strip():
        body_parts.append("[stderr]\n" + err.strip())
    if out_path and os.path.isfile(out_path):
        try:
            with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                file_text = f.read().strip()
            if file_text:
                body_parts.append(f"[results: {out_path}]\n{file_text}")
        except Exception:
            pass
    return {
        "ok": rc == 0, "returncode": rc, "json_path": out_path,
        "findings_count": _findings_count(out_path, out),
        "stdout": ("\n\n".join(body_parts))[:60000] or "(no output)",
    }


def _list_installed_tools(gobin: str, env: dict) -> dict:
    found = []
    for tool in sorted(_SCAN_TOOLS):
        path = _resolve_tool(tool, gobin, env)
        found.append(f"  [{'OK' if path else '  '}] {tool}: {path or '(not installed)'}")
    return {"ok": True, "returncode": 0, "stdout": "Private GOBIN: " + gobin + "\n" + "\n".join(found)}


# ========================================
# STRUCTURED OUTPUT
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_DISCOVERER<<< block atomically (single logging.info call).
    KV header field names MUST stay aligned with agent_contracts._PARAMETRIZER_OUTPUT_FIELDS
    ['discoverer'] and parametrizer.SECTION_AGENT_TYPES."""
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_DISCOVERER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_DISCOVERER")


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
        selection = str(_cfg(config, 'tool', 'subfinder') or 'subfinder').strip().lower()

        logging.info("🛰️ DISCOVERER AGENT STARTED (ProjectDiscovery suite bridge)")
        logging.info(f"Tool/action: {selection}")
        logging.info(f"Targets: {target_agents}")

        go_dir = _default_go_dir(config)
        gobin = _default_gobin(config, go_dir)
        env = _go_env(get_agent_env(), go_dir, gobin, config)
        timeout = float(_as_int(_cfg(config, "command_timeout", 1800), 1800))

        outcome = {"tool": selection, "target": "", "returncode": "", "success": "false",
                   "findings_count": "", "json_path": "", "pdcp_used": "false", "stage": "run"}
        outcome["pdcp_used"] = "true" if str(_cfg(config, "pdcp_api_key")).strip() else "false"
        outcome["target"] = str(_cfg(config, "target") or _cfg(config, "cvemap_id")
                                 or _cfg(config, "cvemap_product") or "").strip()
        body = ""
        ok = False

        if selection not in _ALL_SELECTIONS:
            valid = ", ".join(sorted(_ALL_SELECTIONS))
            body = f"Unknown tool/action {selection!r}. Valid: {valid}."
            outcome["stage"] = "error"
            logging.error("❌ " + body)

        elif selection == "list_tools":
            res = _list_installed_tools(gobin, env)
            ok, body = res["ok"], res["stdout"]
            outcome.update({"returncode": res["returncode"], "stage": "list_tools"})

        elif selection == "bootstrap":
            # Install the Go toolchain, then compile EVERY PD tool (explicit one-time setup).
            go_exe, go_report, go_ok = _bootstrap_go(config, go_dir, env)
            lines = [_format_bootstrap_report({"go": go_report, "tool": "(toolchain)", "ok": go_ok, "steps": []})]
            if go_ok:
                for tool in sorted(_SCAN_TOOLS):
                    inst = _install_tool(tool, go_exe, gobin, env, timeout)
                    lines.append(f"[{'OK' if inst['ok'] else 'XX'}] go install {tool} rc={inst.get('returncode')}")
                    if not inst["ok"]:
                        lines.append("      " + (inst.get("stderr") or "")[-300:])
            ok = go_ok
            body = "\n".join(lines)
            outcome.update({"returncode": 0 if go_ok else 1, "stage": "bootstrap"})

        elif selection == "validate":
            tool_exe = _resolve_tool("nuclei", gobin, env) or _resolve_tool("subfinder", gobin, env)
            go_present = os.path.isfile(_go_exe_path(go_dir))
            pf_lines = [
                f"app_root        : {_app_root()}",
                f"go_dir (GOROOT) : {go_dir}  ({'present' if go_present else 'NOT installed'})",
                f"tools_bin(GOBIN): {gobin}",
                f"output_dir      : {_default_output_dir(config)}",
                f"pdcp_api_key    : {'set' if str(_cfg(config, 'pdcp_api_key')).strip() else '(none — optional)'}",
                "",
                "installed tools:",
                _list_installed_tools(gobin, env)["stdout"],
            ]
            body = "\n".join(pf_lines)
            ok = True
            outcome.update({"returncode": 0, "stage": "validate"})

        elif selection == "update_templates":
            tool_exe, ensure_report, ensure_ok = _ensure_tool("nuclei", config, go_dir, gobin, env, timeout)
            if not ensure_ok:
                body = "Could not install nuclei.\n\n" + _format_bootstrap_report(ensure_report)
                outcome.update({"returncode": 1, "stage": "bootstrap"})
            else:
                rc, out, err = _run_cmd([tool_exe, "-update-templates", "-duc"], env=env, timeout=timeout)
                ok = rc == 0
                body = (out or "") + (("\n[stderr]\n" + err) if err.strip() else "")
                outcome.update({"returncode": rc, "stage": "update_templates"})

        else:
            # ── a scan tool: ensure (bootstrap Go + go install) -> preflight -> run ──
            tool_exe, ensure_report, ensure_ok = _ensure_tool(selection, config, go_dir, gobin, env, timeout)
            boot_note = ""
            if ensure_report.get("steps") and any(s[0] == "go-install" for s in ensure_report["steps"]):
                boot_note = _format_bootstrap_report(ensure_report) + "\n\n"

            do_preflight = _as_bool(_cfg(config, "preflight", True), True)
            preflight = _preflight(selection, config, tool_exe) if do_preflight else None
            if preflight is not None and not preflight["ok"]:
                body = boot_note + "PREFLIGHT REFUSED (fail-safe):\n\n" + _format_preflight_report(preflight)
                outcome.update({"returncode": 1, "stage": "preflight"})
                logging.error(f"❌ Preflight refused {selection}: {preflight['fatals']}")
            elif not tool_exe:
                body = boot_note + "Tool could not be installed.\n\n" + _format_bootstrap_report(ensure_report)
                outcome.update({"returncode": 1, "stage": "bootstrap"})
            else:
                res = _run_scan(selection, tool_exe, config, env, timeout)
                ok = res["ok"]
                warn = ""
                if preflight is not None and preflight.get("warnings"):
                    warn = "[preflight warnings: " + " | ".join(preflight["warnings"]) + "]\n\n"
                body = boot_note + warn + res["stdout"]
                outcome.update({
                    "returncode": res["returncode"], "findings_count": res["findings_count"],
                    "json_path": res["json_path"], "stage": "run",
                })

        outcome["success"] = "true" if ok else "false"
        _emit_section(outcome, body or "(no output)")

        if ok:
            logging.info(f"🏁 Discoverer {selection} complete: success=true")
        else:
            logging.warning(f"⚠️ Discoverer {selection} did not succeed (stage={outcome['stage']}).")

        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Discoverer agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
