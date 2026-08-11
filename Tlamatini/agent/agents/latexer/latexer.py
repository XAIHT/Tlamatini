# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# LaTeXer Agent - Tlamatini's LaTeX TYPESETTING agent (author + compile .tex -> PDF).
# Action: Triggered by upstream -> resolve a MiKTeX (or TeX Live / MacTeX) installation ->
#         run ONE capability (selected by `action`) as a direct subprocess -> parse the
#         LaTeX log into human-readable diagnostics -> emit INI_SECTION_LATEXER ->
#         ALWAYS trigger downstream (success OR failure OR fail-safe refusal).
#
# WHY AN AGENT AND NOT AN EXTERNAL MCP
# ------------------------------------
# LaTeXer embeds — natively, in this one file — the COMPLETE capability surface of the
# `mcp-latex-server` MCP (create_latex_file / create_from_template / edit_latex_file /
# read_latex_file / list_latex_files / validate_latex / get_latex_structure /
# compile_latex) and goes well beyond it: whole-PROJECT compilation of a SET of .tex
# files, BibTeX/Biber + makeindex + makeglossaries driven by a REAL convergence loop,
# latexmk pass-through, LaTeX-log diagnostics a human can actually read, and a
# MiKTeX-first distribution resolver. There is NO MCP server to install, NO FastMCP,
# NO pydantic, NO uv, NO stdio child to babysit, and NO catalogue entry to activate:
# the moment Tlamatini is installed, LaTeXer is present and wired into the canvas,
# Multi-Turn, Parametrizer, the Exec Report and Ask-Execs.
#
# Like Kalier / Nmapper / Discoverer / ESP32er it invokes the CLI DIRECTLY and is fully
# self-contained (stdlib only: subprocess + shutil + glob + re + urllib), so it runs
# identically in source and frozen builds and NEVER imports agent.* (a pool subprocess
# has no sys.path back into the Django app).
#
# THE ONE PREREQUISITE: MiKTeX  (https://miktex.org/download)
# ----------------------------------------------------------
# Tlamatini does NOT bundle a TeX distribution — a full TeX install is several GB and the
# release must stay under 2 GB. The user installs **MiKTeX** once; after that LaTeXer is
# fully functional forever. MiKTeX is STRONGLY preferred over TeX Live because of its
# on-demand package installer (`--enable-installer`): a document requiring a .sty the
# user has never installed STILL BUILDS, because MiKTeX fetches it mid-compile. TeX Live
# and MacTeX are detected and used when present, but cannot self-heal a missing package.
# With no distribution at all LaTeXer REFUSES gracefully (status='refused') with exact
# MiKTeX guidance — it never crashes and never claims a PDF it did not produce.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core, inherited by every spawned
# agent via get_agent_env's os.environ.copy()) so every temp file this agent writes —
# the downloaded MiKTeX installer, staged .tex sources, scratch build dirs — lands
# under <app>/Temp, never C:\Temp / %TEMP% / the OS default. Fail-open when unset.
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
import time
import yaml
import shutil
import logging
import subprocess
import json
import base64
import urllib.request

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
# HELPER FUNCTIONS (copied verbatim from the shared pool-agent boilerplate)
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
    """Extract the leading integer from anything. NEVER raises.

    The wrapped Multi-Turn parser can hand us ``"5 passes"`` where the canvas hands
    us ``5`` — the same class of bug that bit Recorder's ``record_seconds``. Only
    scalars are coercible: without the isinstance guard an arbitrary object falls
    through to str(raw) and its repr's hex address yields a digit run, so junk would
    silently become 0 (e.g. max_passes=0 -> never compile at all).
    """
    try:
        if isinstance(raw, bool):
            return default
        if not isinstance(raw, (str, int, float)):
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


def _as_list(raw) -> list:
    """Accept a real list OR a comma/newline separated string (the wrapped parser
    cannot express a YAML list, so ``packages='amsmath, graphicx'`` must work)."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [part.strip() for part in re.split(r"[,\n]", str(raw)) if part.strip()]


def _as_tribool(raw, default: str = "auto") -> str:
    """use_latexmk is a THREE-state knob: 'auto' | True | False. A plain _as_bool
    would silently collapse 'auto' to False and disable latexmk for everyone."""
    if isinstance(raw, bool):
        return "true" if raw else "false"
    s = str(raw or "").strip().lower()
    if s in ("auto", ""):
        return default
    if s in ("true", "1", "yes", "on"):
        return "true"
    if s in ("false", "0", "no", "off"):
        return "false"
    return default


# ========================================
# CONTRACT: actions, engines, templates
# ========================================

_ENV_ACTIONS = {"validate", "install"}
_AUTHOR_ACTIONS = {
    "create_file", "create_from_template", "edit_file", "read_file",
    "list_files", "validate_tex", "structure",
}
_BUILD_ACTIONS = {"compile", "compile_project", "clean", "scaffold_compile"}
_ALL_ACTIONS = _ENV_ACTIONS | _AUTHOR_ACTIONS | _BUILD_ACTIONS

# Actions that must end up with a real LaTeX engine on this machine.
_NEED_ENGINE = {"compile", "compile_project", "scaffold_compile"}

_ENGINES = ("pdflatex", "xelatex", "lualatex")

_EDIT_MODES = ("replace", "insert_before", "insert_after", "append", "prepend")

# Auxiliary artifacts a LaTeX build leaves behind. `clean` removes exactly these —
# never a .tex and never a .pdf. Anything not on this list is left untouched.
_AUX_EXTENSIONS = (
    ".aux", ".log", ".toc", ".lof", ".lot", ".out", ".bbl", ".blg", ".bcf",
    ".run.xml", ".idx", ".ind", ".ilg", ".glo", ".gls", ".glg", ".ist",
    ".nav", ".snm", ".vrb", ".synctex.gz", ".fls", ".fdb_latexmk", ".xdv",
    ".acn", ".acr", ".alg", ".brf", ".loa", ".thm", ".dvi",
)

# The LaTeX engine says these when the cross-references have NOT settled yet.
_RERUN_MARKERS = (
    "rerun to get",
    "label(s) may have changed",
    "please rerun",
    "rerun latex",
    "citation(s) may have changed",
    "there were undefined references",
    "please (re)run biber",
    "run latex again",
)

_MIKTEX_PROGRAM_GLOBS = [
    r"C:\Program Files\MiKTeX\miktex\bin\x64",
    r"C:\Program Files\MiKTeX\miktex\bin",
    r"C:\Program Files (x86)\MiKTeX\miktex\bin\x64",
    r"C:\Program Files (x86)\MiKTeX\miktex\bin",
    r"C:\Program Files\MiKTeX*\miktex\bin\x64",
    r"C:\Program Files (x86)\MiKTeX*\miktex\bin",
]
_TEXLIVE_GLOBS = [
    r"C:\texlive\*\bin\windows",
    r"C:\texlive\*\bin\win32",
    r"C:\texlive\*\bin\x86_64-*",
]
_POSIX_TEX_DIRS = [
    "/Library/TeX/texbin",                       # MacTeX
    "/usr/local/texlive/2026/bin/universal-darwin",
    "/usr/local/bin", "/usr/bin", "/opt/texbin",
]


# ========================================
# BOUNDED COMMAND RUNNER
# ========================================
# Two absolutes, both of which exist to stop a LaTeX build from HANGING FOREVER:
#   1. every engine invocation carries -interaction=nonstopmode, so LaTeX never stops
#      at an error to interactively ask the user what to do (the classic TeX hang), and
#   2. stdin is DEVNULL, so if a tool ignores rule 1 it reads EOF instantly instead of
#      blocking on a console that a background agent does not even have.
# Together they make a LaTeX build safe to run unattended. argv is always a LIST with
# shell=False, so the command watchdog (which scopes to console interpreters) never
# sees a shell to reap.

def _run_cmd(cmd: list, env: dict = None, cwd: str = None, timeout: float = 600.0):
    """Run a subprocess and capture (returncode, stdout, stderr). NEVER raises;
    maps a missing executable to rc 127 and a timeout to rc 124 (partial output kept)."""
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL, shell=False,
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
# PATHS
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


def _temp_root() -> str:
    temp = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    return temp if temp else os.path.join(_app_root(), "Temp")


def _templates_root() -> str:
    """Tlamatini's Templates policy (Rule 16): deliverable project trees live under
    <app>/Templates, NEVER under Temp — a LaTeX project is a document the user keeps."""
    tpl = (os.environ.get("TLAMATINI_TEMPLATES") or "").strip()
    return tpl if tpl else os.path.join(_app_root(), "Templates")


def _projects_dir(config: dict) -> str:
    explicit = str(_cfg(config, "projects_dir")).strip()
    if explicit:
        return explicit
    return os.path.join(_templates_root(), "LaTeXer")


def _work_base(config: dict) -> str:
    """The directory `list_files` / `clean` operate on: project_dir, else the folder that
    holds tex_path.

    Returns "" when NEITHER is set — deliberately, and this matters: the obvious
    ``os.path.dirname(os.path.abspath(""))`` fallback silently resolves to the PARENT OF
    THE AGENT'S OWN WORKING DIRECTORY, so a `clean` run with an empty config would go
    hunting for .aux/.log files inside the live agent pool. Returning "" makes the
    caller refuse instead.
    """
    project_dir = str(_cfg(config, "project_dir")).strip()
    if project_dir:
        return os.path.abspath(project_dir)
    tex_path = str(_cfg(config, "tex_path")).strip()
    if tex_path:
        return os.path.dirname(os.path.abspath(tex_path))
    return ""


def _documents_dir() -> str:
    """The Windows Documents KNOWN FOLDER (localized, redirected, OneDrive-aware) via
    SHGetKnownFolderPath — the same resolution PDFer / Camcorder use. Falls back to
    ~/Documents everywhere else and on any failure."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            _FOLDERID_Documents = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            guid = GUID()
            if ctypes.windll.ole32.CLSIDFromString(_FOLDERID_Documents, ctypes.byref(guid)) == 0:
                path_ptr = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(guid), 0, None, ctypes.byref(path_ptr)) == 0:
                    value = path_ptr.value
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                    if value:
                        return value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _default_output_dir(config: dict) -> str:
    explicit = str(_cfg(config, "output_dir")).strip()
    if explicit:
        return explicit
    return os.path.join(_documents_dir(), "TlamatiniLaTeX")


def _safe_basename(name: str, fallback_ext: str = ".pdf") -> str:
    """basename() + strip anything that could escape the destination folder. A caller
    (or the LLM) passing ``../../etc/passwd`` must land INSIDE output_dir, always."""
    base = os.path.basename(str(name or "").strip().replace("\\", "/"))
    base = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base).strip(". ")
    if not base:
        return ""
    if not os.path.splitext(base)[1]:
        base += fallback_ext
    return base


def _timestamped_name(ext: str = ".pdf") -> str:
    now = time.localtime()
    ms = int((time.time() % 1) * 1000)
    return "latexer_%s_%s_%03d%s" % (time.strftime("%Y%m%d", now), time.strftime("%H%M%S", now), ms, ext)


def _unique_path(path: str, overwrite: bool) -> str:
    """Never clobber unless explicitly told to: a colliding name gets _2, _3, ..."""
    if overwrite or not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    for n in range(2, 1000):
        candidate = f"{stem}_{n}{ext}"
        if not os.path.exists(candidate):
            return candidate
    return f"{stem}_{int(time.time())}{ext}"


# ========================================
# DISTRIBUTION + ENGINE RESOLUTION  (MiKTeX FIRST — always)
# ========================================

def _candidate_bin_dirs() -> list:
    """Every directory that might hold a TeX binary, MiKTeX FIRST so a machine carrying
    both distributions uses MiKTeX (the only one that can auto-install a missing
    package mid-compile, which is exactly what makes LaTeXer work out of the box)."""
    dirs = []
    if os.name == "nt":
        for pattern in _MIKTEX_PROGRAM_GLOBS:
            dirs.extend(sorted(glob.glob(pattern), reverse=True))
        # A per-user MiKTeX install ("just for me") is extremely common and lands here.
        local = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        for pattern in (
            os.path.join(local, "Programs", "MiKTeX", "miktex", "bin", "x64"),
            os.path.join(local, "Programs", "MiKTeX", "miktex", "bin"),
            os.path.join(local, "Programs", "MiKTeX*", "miktex", "bin", "x64"),
        ):
            dirs.extend(sorted(glob.glob(pattern), reverse=True))
        for pattern in _TEXLIVE_GLOBS:
            dirs.extend(sorted(glob.glob(pattern), reverse=True))
    else:
        dirs.extend(_POSIX_TEX_DIRS)
    seen, ordered = set(), []
    for d in dirs:
        key = os.path.normcase(os.path.normpath(d))
        if key not in seen and os.path.isdir(d):
            seen.add(key)
            ordered.append(d)
    return ordered


def _which(name: str, env: dict) -> str:
    """Resolve a TeX tool. Standard install locations are searched BEFORE PATH so a
    real MiKTeX beats a stray shim, then PATH as the catch-all."""
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _candidate_bin_dirs():
        cand = os.path.join(d, exe)
        if os.path.isfile(cand):
            return cand
    found = shutil.which(name, path=(env or os.environ).get("PATH"))
    return found or ""


def _identify_distribution(latex_exe: str, env: dict) -> tuple:
    """Ask the engine who it is. Returns (distribution, version_line).

    MiKTeX prints  'MiKTeX-pdfTeX 4.x (MiKTeX 24.1)';
    TeX Live prints 'pdfTeX 3.141592653-2.6-1.40.25 (TeX Live 2023)'.
    """
    if not latex_exe:
        return "none", ""
    rc, out, err = _run_cmd([latex_exe, "--version"], env=env, timeout=60)
    blob = (out + "\n" + err).strip()
    first = blob.splitlines()[0].strip() if blob else ""
    low = blob.lower()
    if "miktex" in low:
        return "miktex", first
    if "tex live" in low or "texlive" in low:
        return "texlive", first
    if "mactex" in low:
        return "mactex", first
    if rc == 0 and blob:
        return "unknown", first
    return "none", first


def _latexmk_usable(exe: str, env: dict) -> bool:
    """Does latexmk actually RUN on this machine? Existence on disk proves NOTHING.

    ⚠️ THE WINDOWS LANDMINE THIS EXISTS FOR: `latexmk.exe` ships with EVERY MiKTeX
    installation, so shutil.which() always finds it — but it is only a thin launcher for
    a PERL SCRIPT. On a machine without Perl (which is most Windows machines: MiKTeX does
    NOT bundle one) it dies instantly with

        MiKTeX could not find the script engine 'perl' which is required to execute 'latexmk'

    and produces no PDF. Trusting `which('latexmk')` therefore breaks the DEFAULT build
    path on a stock MiKTeX box. We probe it once, cheaply, and treat an unusable latexmk
    as absent — LaTeXer's own convergence loop then does the job with no Perl at all.
    Fails CLOSED (returns False on any doubt): a false negative merely uses our own loop,
    while a false positive fails the user's build.
    """
    if not exe:
        return False
    rc, out, err = _run_cmd([exe, "-v"], env=env, timeout=60)
    blob = ((out or "") + " " + (err or "")).lower()
    if "script engine" in blob or "did not succeed" in blob or "perl" in blob:
        return False
    return rc == 0 and "latexmk" in blob


def _resolve_toolchain(config: dict, env: dict) -> dict:
    """Resolve every executable LaTeXer might need, plus which distribution we are on."""
    engine = str(_cfg(config, "engine", "pdflatex")).strip().lower() or "pdflatex"
    if engine not in _ENGINES:
        engine = "pdflatex"

    explicit = str(_cfg(config, "latex_executable")).strip()
    latex_exe = explicit if (explicit and os.path.isfile(explicit)) else _which(engine, env)

    distribution, version_line = _identify_distribution(latex_exe, env)

    def _pick(cfg_key: str, tool: str) -> str:
        given = str(_cfg(config, cfg_key)).strip()
        if given and os.path.isfile(given):
            return given
        return _which(tool, env)

    latexmk_exe = _pick("latexmk_executable", "latexmk")
    return {
        "engine": engine,
        "latex": latex_exe,
        "latexmk": latexmk_exe,
        "latexmk_usable": _latexmk_usable(latexmk_exe, env),
        "biber": _pick("biber_executable", "biber"),
        "bibtex": _pick("bibtex_executable", "bibtex"),
        "makeindex": _pick("makeindex_executable", "makeindex"),
        "makeglossaries": _which("makeglossaries", env),
        "distribution": distribution,
        "version_line": version_line,
    }


def _miktex_hint(distribution: str) -> str:
    """The single sentence every refusal ends with. MiKTeX, every time."""
    if distribution == "miktex":
        return ""
    if distribution in ("texlive", "mactex", "unknown"):
        return ("NOTE: this machine has %s, not MiKTeX. It works, but it CANNOT install a "
                "missing package on demand — if a build fails with \"File 'xxx.sty' not "
                "found\" you must install that package yourself. MiKTeX "
                "(https://miktex.org/download) does it automatically." % distribution)
    return ("LaTeXer needs a TeX distribution and Tlamatini does not bundle one (a full TeX "
            "install is several GB). Install **MiKTeX** once — https://miktex.org/download — "
            "and LaTeXer works forever after, including automatic on-demand installation of "
            "any package your documents need. Or run this agent with action='install' and "
            "Tlamatini will download and launch the official MiKTeX installer for you.")


# ========================================
# CONSENTED OFFICIAL MiKTeX INSTALLER FETCH (USE, NOT REDISTRIBUTION)
# ========================================

def _download_file(url: str) -> tuple:
    """Download url into <app>/Temp. Returns (path, error). Never raises."""
    import urllib.request
    import tempfile
    try:
        logging.info(f"⬇️  Downloading the OFFICIAL MiKTeX installer: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Tlamatini-LaTeXer"})
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = resp.read()
        suffix = "_" + (os.path.basename(url) or "basic-miktex.exe")
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path, ""
    except Exception as e:
        return "", str(e)


def _run_miktex_installer(config: dict) -> tuple:
    """USE, NOT REDISTRIBUTION: download the OFFICIAL MiKTeX installer to the user's
    machine and launch it. Tlamatini never bundles MiKTeX (it would blow the 2 GB
    release budget); the user consents to and completes the install themselves —
    exactly the model Nmapper uses for nmap. Returns (ok, report)."""
    url = str(_cfg(config, "miktex_install_url",
                   "https://miktex.org/download/win/basic-miktex-x64.exe")).strip()
    if os.name != "nt":
        return False, (
            "Automatic install is Windows-only. Install a TeX distribution with your package "
            "manager (macOS: MacTeX from https://tug.org/mactex/ — Linux: texlive-full), then "
            "re-run. On Windows, MiKTeX (https://miktex.org/download) is the recommended one.")
    path, err = _download_file(url)
    if not path:
        return False, (
            f"Could not download the MiKTeX installer from {url}: {err}\n"
            f"Download MiKTeX yourself from https://miktex.org/download and install it, "
            f"then re-run — no further configuration is needed.")
    lines = [f"Official MiKTeX installer downloaded from {url}", f"  saved to: {path}"]
    try:
        os.startfile(path)  # noqa: S606 - launches the installer; the USER completes the wizard
        lines += [
            "  Launched the installer — accept the UAC prompt and complete the wizard.",
            "  Recommended during setup: leave \"Install missing packages on-the-fly\" = Yes.",
            "    That is what lets LaTeXer build ANY document without you hunting packages.",
            "  When it finishes, re-run LaTeXer — it will find MiKTeX automatically.",
        ]
        return True, "\n".join(lines)
    except Exception as e:
        lines.append(f"  Could not auto-launch ({e}). Run it yourself: {path}")
        return False, "\n".join(lines)


# ========================================
# LaTeX SOURCE ANALYSIS
# ========================================

def _read_text(path: str) -> str:
    """Read a .tex tolerantly: LaTeX sources in the wild are UTF-8, latin-1 or cp1252."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception as e:
            raise e
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _strip_comments(source: str) -> str:
    """Drop LaTeX comments so analysis never trips over a commented-out \\begin{...}.
    An escaped \\% is NOT a comment — that distinction is the whole point."""
    out = []
    for line in source.splitlines():
        idx, cut = 0, None
        while idx < len(line):
            ch = line[idx]
            if ch == "\\":
                idx += 2
                continue
            if ch == "%":
                cut = idx
                break
            idx += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def _is_full_document(source: str) -> bool:
    clean = _strip_comments(source)
    return bool(re.search(r"\\documentclass", clean)) and bool(re.search(r"\\begin\s*\{document\}", clean))


def _find_main_tex(project_dir: str, explicit: str, recursive: bool) -> tuple:
    """Pick the MASTER .tex of a project. Returns (path, note).

    A folder of .tex files has exactly one file you are supposed to compile — the one
    with BOTH \\documentclass and \\begin{document}. Children pulled in by \\input have
    neither, so they are excluded automatically. Conventional names break a tie.
    """
    if explicit:
        cand = explicit if os.path.isabs(explicit) else os.path.join(project_dir, explicit)
        if not os.path.splitext(cand)[1]:
            cand += ".tex"
        if os.path.isfile(cand):
            return cand, f"main file given explicitly: {os.path.basename(cand)}"
        return "", f"main_file {explicit!r} does not exist under {project_dir}"

    pattern = os.path.join(project_dir, "**", "*.tex") if recursive else os.path.join(project_dir, "*.tex")
    files = sorted(glob.glob(pattern, recursive=recursive))
    if not files:
        return "", f"no .tex files found under {project_dir}"

    masters = []
    for path in files:
        try:
            if _is_full_document(_read_text(path)):
                masters.append(path)
        except Exception:
            continue
    if not masters:
        return "", (f"found {len(files)} .tex file(s) under {project_dir} but NONE contains both "
                    f"\\documentclass and \\begin{{document}} — none of them is a compilable master "
                    f"document. Name the master with main_file, or add a preamble.")
    if len(masters) == 1:
        return masters[0], f"auto-detected the only master document: {os.path.basename(masters[0])}"

    preferred = ("main.tex", "document.tex", "thesis.tex", "report.tex", "paper.tex", "root.tex")
    shallow = sorted(masters, key=lambda p: (p.count(os.sep), len(p)))
    for name in preferred:
        for path in shallow:
            if os.path.basename(path).lower() == name:
                return path, (f"{len(masters)} master documents found; picked the conventional "
                              f"{name} (name another with main_file)")
    pick = shallow[0]
    return pick, (f"{len(masters)} master documents found; picked the shallowest, "
                  f"{os.path.basename(pick)} (name another with main_file)")


def _collect_children(main_tex: str) -> list:
    """Resolve \\input / \\include / \\subfile children (one level deep is enough to
    report the SET of files that make up the document)."""
    children = []
    try:
        source = _strip_comments(_read_text(main_tex))
    except Exception:
        return children
    base = os.path.dirname(os.path.abspath(main_tex))
    for m in re.finditer(r"\\(?:input|include|subfile)\s*\{([^}]+)\}", source):
        ref = m.group(1).strip()
        if not ref:
            continue
        cand = ref if os.path.isabs(ref) else os.path.join(base, ref)
        if not os.path.splitext(cand)[1]:
            cand += ".tex"
        if os.path.isfile(cand) and cand not in children:
            children.append(cand)
    return children


def _analyze_source(source: str) -> dict:
    """What extra tools does this document need? Drives the convergence loop."""
    clean = _strip_comments(source)
    uses_biblatex = bool(re.search(r"\\usepackage(\[[^\]]*\])?\s*\{[^}]*biblatex", clean)) or \
        bool(re.search(r"\\addbibresource", clean))
    uses_bibtex = bool(re.search(r"\\bibliography\s*\{", clean)) or \
        bool(re.search(r"\\bibliographystyle\s*\{", clean))
    return {
        "biblatex": uses_biblatex,
        "bibtex": uses_bibtex and not uses_biblatex,
        "index": bool(re.search(r"\\makeindex", clean)),
        "glossaries": bool(re.search(r"\\makeglossaries", clean)),
        "documentclass": (re.search(r"\\documentclass(?:\[[^\]]*\])?\s*\{([^}]+)\}", clean).group(1)
                          if re.search(r"\\documentclass(?:\[[^\]]*\])?\s*\{([^}]+)\}", clean) else ""),
    }


def _document_structure(source: str) -> dict:
    """The get_latex_structure capability: class, title, author, packages, sections, labels."""
    clean = _strip_comments(source)

    def _one(pattern):
        # ⚠️ re.MULTILINE IS LOAD-BEARING — do NOT drop it (Angela, 2026-08-05).
        # The title/author patterns end in `\}\s*$`. Without MULTILINE, `$` matches
        # only the end of the WHOLE source, so `\title{...}` — which lives in the
        # preamble of literally every real document — never matched, and `structure`
        # reported an EMPTY title and author for every file anyone ever passed it.
        # Silent, because a blank string is a perfectly valid-looking answer.
        # The `$` anchor itself is what lets a braced title (`\title{A \textbf{Bold}
        # One}`) capture in full: only the LAST `}` on the line sits at end-of-line.
        m = re.search(pattern, clean, re.MULTILINE)
        return m.group(1).strip() if m else ""

    packages = []
    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\s*\{([^}]+)\}", clean):
        for name in m.group(1).split(","):
            name = name.strip()
            if name and name not in packages:
                packages.append(name)

    sections = []
    for m in re.finditer(
            r"\\(part|chapter|section|subsection|subsubsection|paragraph)\*?\s*\{([^}]*)\}", clean):
        sections.append({"level": m.group(1), "title": m.group(2).strip()})

    labels = re.findall(r"\\label\s*\{([^}]+)\}", clean)
    refs = re.findall(r"\\(?:ref|eqref|pageref|autoref|cref|Cref)\s*\{([^}]+)\}", clean)
    citations = re.findall(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{([^}]+)\}", clean)
    cites = []
    for group in citations:
        for key in group.split(","):
            key = key.strip()
            if key and key not in cites:
                cites.append(key)

    return {
        "documentclass": _one(r"\\documentclass(?:\[[^\]]*\])?\s*\{([^}]+)\}"),
        "class_options": _one(r"\\documentclass\[([^\]]*)\]"),
        "title": _one(r"\\title\s*\{(.+?)\}\s*$"),
        "author": _one(r"\\author\s*\{(.+?)\}\s*$"),
        "packages": packages,
        "sections": sections,
        "labels": labels,
        "references": sorted(set(refs)),
        "citations": cites,
    }


def _validate_source(source: str) -> dict:
    """The validate_latex capability: brace balance, environment matching, ref sanity.
    This is a STATIC check — it needs no TeX distribution at all, so a user can lint a
    document before MiKTeX is even installed."""
    clean = _strip_comments(source)
    errors, warnings = [], []

    depth, line_no = 0, 1
    opened_at = []
    idx = 0
    while idx < len(clean):
        ch = clean[idx]
        if ch == "\n":
            line_no += 1
        elif ch == "\\":
            idx += 2
            continue
        elif ch == "{":
            depth += 1
            opened_at.append(line_no)
        elif ch == "}":
            depth -= 1
            if opened_at:
                opened_at.pop()
            if depth < 0:
                errors.append(f"line {line_no}: unmatched closing brace '}}'")
                depth = 0
        idx += 1
    if depth > 0:
        where = ", ".join(str(n) for n in opened_at[:5])
        errors.append(f"{depth} unclosed brace(s) '{{' — opened at line(s) {where}")

    stack = []
    for m in re.finditer(r"\\(begin|end)\s*\{([^}]+)\}", clean):
        kind, name = m.group(1), m.group(2).strip()
        line = clean.count("\n", 0, m.start()) + 1
        if kind == "begin":
            stack.append((name, line))
        else:
            if not stack:
                errors.append(f"line {line}: \\end{{{name}}} with no matching \\begin")
            elif stack[-1][0] != name:
                open_name, open_line = stack[-1]
                errors.append(
                    f"line {line}: \\end{{{name}}} closes \\begin{{{open_name}}} from line {open_line}")
                stack.pop()
            else:
                stack.pop()
    for name, line in stack:
        errors.append(f"line {line}: \\begin{{{name}}} is never closed")

    if not re.search(r"\\documentclass", clean):
        warnings.append("no \\documentclass — this is a fragment, not a compilable document")
    if not re.search(r"\\begin\s*\{document\}", clean):
        warnings.append("no \\begin{document} — this is a fragment, not a compilable document")

    labels = set(re.findall(r"\\label\s*\{([^}]+)\}", clean))
    for ref in sorted(set(re.findall(r"\\(?:ref|eqref|pageref|autoref)\s*\{([^}]+)\}", clean))):
        if ref not in labels:
            warnings.append(f"\\ref{{{ref}}} has no matching \\label in this file")
    seen = set()
    for lbl in re.findall(r"\\label\s*\{([^}]+)\}", clean):
        if lbl in seen:
            warnings.append(f"duplicate \\label{{{lbl}}}")
        seen.add(lbl)

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ========================================
# LaTeX LOG PARSING — turn 3000 lines of noise into an answer
# ========================================

def _parse_latex_log(log_text: str) -> dict:
    """Extract what actually matters from a LaTeX .log.

    A LaTeX log is thousands of lines of font-loading chatter with the ONE line that
    explains the failure buried in the middle. -file-line-error gives us
    'file.tex:12: message', which is what every editor and every human wants.
    """
    errors, warnings, missing_packages, missing_files = [], [], [], []
    boxes = 0
    pages, out_file, out_bytes = 0, "", 0

    lines = log_text.splitlines()
    for i, raw in enumerate(lines):
        line = raw.rstrip()

        # ⚠️ MISSING-FILE EXTRACTION MUST COME FIRST — before either `continue` below.
        # In a real LaTeX log the message
        #     ! LaTeX Error: File `biblatex.sty' not found.
        # ALWAYS arrives on a line that is ALSO an error line (it starts with "! ", or
        # with "file.tex:5: " under -file-line-error). Running this extraction after
        # those branches means it never executes at all, and the single most actionable
        # diagnostic we produce — WHICH PACKAGE IS MISSING, the whole point of MiKTeX's
        # on-demand installer — silently reports nothing. Found by
        # test_missing_package_is_isolated_from_a_missing_data_file.
        mp = re.search(r"File\s+[`'\"]([^'\"]+\.(?:sty|cls|def))'?\s+not found", line)
        if mp and mp.group(1) not in missing_packages:
            missing_packages.append(mp.group(1))
        mf = re.search(r"File\s+[`'\"]([^'\"]+)'?\s+not found", line)
        if mf and not mf.group(1).endswith((".sty", ".cls", ".def")) and mf.group(1) not in missing_files:
            missing_files.append(mf.group(1))

        m = re.match(r"^(.+?\.\w+):(\d+):\s*(.+)$", line)
        if m and not line.startswith("("):
            errors.append(f"{os.path.basename(m.group(1))}:{m.group(2)}: {m.group(3).strip()}")
            continue

        if line.startswith("! "):
            detail = line[2:].strip()
            follow = ""
            for nxt in lines[i + 1:i + 4]:
                if nxt.startswith("l.") or nxt.startswith("<"):
                    follow = " " + nxt.strip()
                    break
            errors.append((detail + follow).strip())
            continue

        if re.match(r"^(LaTeX|Package\s+\S+|Class\s+\S+)\s+Warning:", line):
            text = line.strip()
            if text not in warnings:
                warnings.append(text)
        if "Overfull " in line or "Underfull " in line:
            boxes += 1

        mo = re.search(r"Output written on\s+(.+?)\s+\((\d+)\s+pages?,\s*(\d+)\s+bytes\)", line)
        if mo:
            out_file, pages, out_bytes = mo.group(1).strip(), int(mo.group(2)), int(mo.group(3))

    if not out_file:
        mo = re.search(r"Output written on\s+(.+?)\s+\((\d+)\s+pages?", log_text)
        if mo:
            out_file, pages = mo.group(1).strip(), int(mo.group(2))

    low = log_text.lower()
    needs_rerun = any(marker in low for marker in _RERUN_MARKERS)

    def _dedupe(seq):
        out = []
        for item in seq:
            if item not in out:
                out.append(item)
        return out

    return {
        "errors": _dedupe(errors),
        "warnings": _dedupe(warnings),
        "missing_packages": missing_packages,
        "missing_files": missing_files,
        "boxes": boxes,
        "pages": pages,
        "output_file": out_file,
        "output_bytes": out_bytes,
        "needs_rerun": needs_rerun,
    }


def _format_diagnostics(diag: dict, distribution: str, auto_install: bool, limit: int) -> str:
    lines = []
    if diag["errors"]:
        lines.append("ERRORS (%d):" % len(diag["errors"]))
        lines += ["  ✗ " + e for e in diag["errors"][:40]]
        if len(diag["errors"]) > 40:
            lines.append("  ... and %d more" % (len(diag["errors"]) - 40))
    if diag["missing_packages"]:
        lines.append("")
        lines.append("MISSING PACKAGES (%d): %s" % (len(diag["missing_packages"]),
                                                    ", ".join(diag["missing_packages"])))
        if distribution == "miktex":
            lines.append("  MiKTeX can install these automatically — keep auto_install_packages: true,")
            lines.append("  and make sure MiKTeX's own \"install missing packages on-the-fly\" is not")
            lines.append("  set to 'Never' (MiKTeX Console -> Settings).")
        else:
            lines.append("  This distribution cannot self-install packages. MiKTeX")
            lines.append("  (https://miktex.org/download) installs them on demand, mid-compile.")
    if diag["missing_files"]:
        lines.append("")
        lines.append("MISSING FILES: " + ", ".join(diag["missing_files"][:15]))
    if diag["warnings"]:
        lines.append("")
        lines.append("WARNINGS (%d):" % len(diag["warnings"]))
        lines += ["  • " + w for w in diag["warnings"][:20]]
        if len(diag["warnings"]) > 20:
            lines.append("  ... and %d more" % (len(diag["warnings"]) - 20))
    if diag["boxes"]:
        lines.append("")
        lines.append("TYPOGRAPHY: %d overfull/underfull box(es) — cosmetic, not an error." % diag["boxes"])
    text = "\n".join(lines)
    if limit > 0 and len(text) > limit:
        text = text[:limit] + "\n... [diagnostics truncated]"
    return text


# ========================================
# TEMPLATES  (token replacement — NEVER str.format: LaTeX is made of braces)
# ========================================

_TPL_ARTICLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{%%TITLE%%}
\author{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}
\maketitle

\section{Introduction}
%%CONTENT%%

\end{document}
"""

_TPL_REPORT = r"""\documentclass[11pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{%%TITLE%%}
\author{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}
\maketitle
\tableofcontents

\chapter{Introduction}
%%CONTENT%%

\end{document}
"""

_TPL_BOOK = r"""\documentclass[11pt,a4paper,twoside]{book}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{%%TITLE%%}
\author{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}
\frontmatter
\maketitle
\tableofcontents

\mainmatter
\chapter{Introduction}
%%CONTENT%%

\end{document}
"""

_TPL_BEAMER = r"""\documentclass[aspectratio=169]{beamer}
\usetheme{Madrid}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage{graphicx}

\title{%%TITLE%%}
\author{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}

\frame{\titlepage}

\begin{frame}{Overview}
%%CONTENT%%
\end{frame}

\end{document}
"""

_TPL_LETTER = r"""\documentclass[11pt,a4paper]{letter}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2.5cm]{geometry}

\signature{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}
\begin{letter}{}

\opening{Dear Sir or Madam,}

%%CONTENT%%

\closing{Sincerely,}

\end{letter}
\end{document}
"""

_TPL_CV = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2cm]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage[hidelinks]{hyperref}

\titleformat{\section}{\large\bfseries}{}{0pt}{}[\titlerule]
\pagestyle{empty}

\begin{document}

\begin{center}
  {\Huge\bfseries %%AUTHOR%%}\\[4pt]
  {\large %%TITLE%%}
\end{center}

\section{Experience}
%%CONTENT%%

\section{Education}
\begin{itemize}[leftmargin=*]
  \item Degree --- Institution --- Year
\end{itemize}

\section{Skills}
\begin{itemize}[leftmargin=*]
  \item Skill one \textperiodcentered{} Skill two \textperiodcentered{} Skill three
\end{itemize}

\end{document}
"""

_TPL_HOMEWORK = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
%%BABEL%%\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{enumitem}
\usepackage{fancyhdr}

\pagestyle{fancy}
\lhead{%%AUTHOR%%}
\rhead{%%TITLE%%}

\begin{document}

\begin{center}
  {\Large\bfseries %%TITLE%%}\\[2pt]
  %%AUTHOR%% \hfill %%DATE%%
\end{center}

\begin{enumerate}[label=\textbf{Problem \arabic*.}, leftmargin=*]
  \item %%CONTENT%%

  \textit{Solution.} Write the solution here, e.g.
  \[
    \int_{0}^{\infty} e^{-x^{2}}\,\mathrm{d}x = \frac{\sqrt{\pi}}{2}.
  \]
\end{enumerate}

\end{document}
"""

_TPL_SPANISH = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[spanish,mexico]{babel}
\usepackage[margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{%%TITLE%%}
\author{%%AUTHOR%%}
\date{%%DATE%%}

\begin{document}
\maketitle

\section{Introducción}
%%CONTENT%%

\end{document}
"""

_TEMPLATES = {
    "article": _TPL_ARTICLE,
    "report": _TPL_REPORT,
    "book": _TPL_BOOK,
    "beamer": _TPL_BEAMER,
    "letter": _TPL_LETTER,
    "cv": _TPL_CV,
    "homework": _TPL_HOMEWORK,
    "spanish-article": _TPL_SPANISH,
}


def _babel_line(language: str) -> str:
    """Spanish documents need babel or accents/hyphenation come out wrong. English is
    LaTeX's default, so it needs no package at all."""
    if str(language or "").strip().lower().startswith("es"):
        return "\\usepackage[spanish,mexico]{babel}\n"
    return ""


def _render_template(name: str, config: dict) -> str:
    tpl = _TEMPLATES.get(str(name or "article").strip().lower(), _TPL_ARTICLE)
    language = str(_cfg(config, "document_language", "en"))
    title = str(_cfg(config, "title")).strip() or "Untitled Document"
    author = str(_cfg(config, "author")).strip() or "Tlamatini"
    date = str(_cfg(config, "date")).strip() or r"\today"
    content = str(_cfg(config, "content")).strip() or \
        "Replace this paragraph with your own text."
    # Token replacement, never str.format(): a LaTeX template is ALL braces and
    # .format() would explode on the very first \begin{document}.
    out = tpl.replace("%%BABEL%%", "" if name == "spanish-article" else _babel_line(language))
    out = out.replace("%%TITLE%%", title)
    out = out.replace("%%AUTHOR%%", author)
    out = out.replace("%%DATE%%", date)
    out = out.replace("%%CONTENT%%", content)
    return out


# Packages the GENERATED preamble always carries, mirroring what every on-disk
# template (_TPL_ARTICLE and friends) already carried.
#
# ⚠️ DO NOT TRIM THIS LIST. Without amsmath a bare fragment using \eqref, align,
# \text or \boxed dies with "Undefined control sequence" -- and it dies AFTER
# pdflatex has already written a PDF, so the user is handed a silently
# mis-typeset document. That is exactly the Step-3 wizard failure of 2026-08-05
# (status=compiled_with_errors, "latexer_wizard_step3.tex:13: Undefined control
# sequence"): auto_preamble promises "pass a fragment and get a real PDF", so the
# generated preamble MUST be as capable as the templates it stands in for.
#
# hyperref is deliberately NOT here -- it is appended LAST (see below), because it
# patches other packages' internals and must be loaded after them.
_DEFAULT_PREAMBLE_PACKAGES = ("amsmath", "amssymb", "graphicx")


def _declared_packages(*texts) -> set:
    """Lowercased set of every package already named in a \\usepackage{a,b} call."""
    found = set()
    for text in texts:
        for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\s*\{([^}]+)\}", str(text or "")):
            found.update(p.strip().lower() for p in m.group(1).split(",") if p.strip())
    return found


def _build_document(config: dict) -> str:
    """create_file: assemble a .tex from discrete parameters."""
    cls = str(_cfg(config, "documentclass", "article")).strip() or "article"
    opts = str(_cfg(config, "class_options")).strip()
    head = "\\documentclass[%s]{%s}\n" % (opts, cls) if opts else "\\documentclass{%s}\n" % cls

    lines = [head, "\\usepackage[utf8]{inputenc}\n", "\\usepackage[T1]{fontenc}\n"]
    lines.append(_babel_line(str(_cfg(config, "document_language", "en"))))

    geometry = str(_cfg(config, "geometry", "margin=2.5cm")).strip()
    if geometry:
        lines.append("\\usepackage[%s]{geometry}\n" % geometry)

    # What the caller already asked for -- explicitly via `packages`, or implicitly
    # by writing their own \usepackage inside `content`. Never load one twice: a
    # duplicate \usepackage with different options is a hard "Option clash" error.
    requested = [str(p).strip() for p in _as_list(_cfg(config, "packages", [])) if str(p).strip()]
    have = _declared_packages(str(_cfg(config, "content", "")))
    for spec in requested:
        have.update(p.strip().lower() for p in spec.split(",") if p.strip())

    for pkg in _DEFAULT_PREAMBLE_PACKAGES:
        if pkg.lower() not in have:
            lines.append("\\usepackage{%s}\n" % pkg)
            have.add(pkg.lower())
    for pkg in requested:
        lines.append("\\usepackage{%s}\n" % pkg)
    # hyperref LAST -- it redefines internals of packages loaded before it.
    if "hyperref" not in have:
        lines.append("\\usepackage[hidelinks]{hyperref}\n")

    title = str(_cfg(config, "title")).strip()
    author = str(_cfg(config, "author")).strip()
    date = str(_cfg(config, "date")).strip()
    if title:
        lines.append("\n\\title{%s}\n" % title)
        lines.append("\\author{%s}\n" % (author or "Tlamatini"))
        lines.append("\\date{%s}\n" % (date or r"\today"))

    lines.append("\n\\begin{document}\n")
    if title:
        lines.append("\\maketitle\n\n")
    lines.append(str(_cfg(config, "content")).strip() or "Replace this text with your content.")
    lines.append("\n\n\\end{document}\n")
    return "".join(lines)


def _wrap_fragment(fragment: str, config: dict) -> str:
    """auto_preamble: let the user (or the LLM) pass a bare fragment — even a single
    formula — and still get a real PDF. This is what makes 'Tlamatini, typeset
    $E=mc^2$' a ONE-CALL operation."""
    body = dict(config)
    body["content"] = fragment
    if not str(_cfg(config, "title")).strip():
        body["title"] = ""
    return _build_document(body)


# ========================================
# THE COMPILER
# ========================================

def _engine_argv(tools: dict, config: dict, tex_name: str) -> list:
    """Build the engine command line.

    -interaction=nonstopmode is NON-NEGOTIABLE: without it LaTeX stops at the first
    error and waits for keyboard input forever, which for an unattended agent means a
    hung process. -file-line-error is what makes the diagnostics readable.
    """
    argv = [tools["latex"], "-interaction=nonstopmode", "-file-line-error"]
    if tools["distribution"] == "miktex":
        # ⚠️ BOTH BRANCHES ARE REQUIRED. Omitting the flag does NOT disable the
        # installer -- it just lets MiKTeX's own global AutoInstall setting
        # decide, which on a typical install is "yes". So `auto_install_packages:
        # false` silently did nothing at all, and packages were still fetched
        # behind the user's back. Passing --disable-installer explicitly is what
        # makes the option mean what it says (and what makes rung 5 reachable,
        # since otherwise MiKTeX always wins the race to fix a missing package).
        if _as_bool(_cfg(config, "auto_install_packages", True), True):
            argv.append("--enable-installer")
        else:
            argv.append("--disable-installer")
    if _as_bool(_cfg(config, "shell_escape", False), False):
        argv.append("-shell-escape")
    argv.append(tex_name)
    return argv


def _latexmk_argv(tools: dict, config: dict, tex_name: str) -> list:
    engine_flag = {"pdflatex": "-pdf", "xelatex": "-pdfxe", "lualatex": "-pdflua"}[tools["engine"]]
    argv = [tools["latexmk"], engine_flag, "-interaction=nonstopmode", "-file-line-error", "-halt-on-error"]
    if _as_bool(_cfg(config, "shell_escape", False), False):
        argv.append("-shell-escape")
    argv.append(tex_name)
    return argv


def _read_build_log(work_dir: str, jobname: str) -> str:
    for name in (jobname + ".log", jobname + ".blg"):
        path = os.path.join(work_dir, name)
        if os.path.isfile(path):
            try:
                return _read_text(path)
            except Exception:
                continue
    return ""


def _compile(tex_path: str, config: dict, tools: dict, env: dict) -> dict:
    """Typeset ONE master document to PDF, running as many passes as it takes.

    The build always runs IN the document's own directory, exactly the way a human
    would run it: that is what makes \\input, \\include, \\graphicspath, relative
    image paths and BibTeX's .bib lookup resolve correctly. Aux files land beside the
    source and are tidied afterwards on success (kept on failure, so the user can look).
    """
    work_dir = os.path.dirname(os.path.abspath(tex_path))
    tex_name = os.path.basename(tex_path)
    jobname = os.path.splitext(tex_name)[0]
    timeout = float(_as_int(_cfg(config, "command_timeout", 600), 600))
    max_passes = max(1, min(_as_int(_cfg(config, "max_passes", 5), 5), 10))

    try:
        source = _read_text(tex_path)
    except Exception as e:
        return {"ok": False, "passes": 0, "report": f"could not read {tex_path}: {e}",
                "diag": _parse_latex_log(""), "pdf": "", "steps": []}

    needs = _analyze_source(source)
    bib_mode = str(_cfg(config, "bibliography", "auto")).strip().lower() or "auto"
    if bib_mode == "auto":
        bib_mode = "biber" if needs["biblatex"] else ("bibtex" if needs["bibtex"] else "none")

    steps, passes = [], 0
    combined_log = ""
    rc = 0
    use_latexmk = _as_tribool(_cfg(config, "use_latexmk", "auto"), "auto")
    # NOTE: usable, not merely present — see _latexmk_usable (the no-Perl landmine).
    latexmk_available = bool(tools.get("latexmk_usable"))
    ran_latexmk = False

    # ── Path A: latexmk — the reference implementation of "rebuild until stable" ──
    if latexmk_available and use_latexmk in ("true", "auto"):
        argv = _latexmk_argv(tools, config, tex_name)
        logging.info("🛠️  latexmk: " + " ".join(argv))
        rc, out, err = _run_cmd(argv, env=env, cwd=work_dir, timeout=timeout)
        passes = 1
        combined_log = _read_build_log(work_dir, jobname) or (out + "\n" + err)
        steps.append(f"latexmk ({tools['engine']}) -> rc={rc}")
        ran_latexmk = True
        _probe_pdf = os.path.join(work_dir, jobname + ".pdf")
        if not (os.path.isfile(_probe_pdf) and os.path.getsize(_probe_pdf) > 0):
            # latexmk is a CONVENIENCE, never a dependency. When it dies without emitting
            # anything the cause is almost always latexmk ITSELF (missing Perl, a broken
            # ~/.latexmkrc, an unsupported flag) rather than the user's document — so
            # retry with our own loop instead of handing back a failure they cannot act
            # on. The document gets built; the user is simply told the helper was skipped.
            steps.append("latexmk produced NO PDF -> falling back to LaTeXer's built-in "
                         "convergence loop (latexmk is a convenience, not a dependency)")
            logging.warning("⚠️ latexmk produced no PDF — falling back to the built-in loop.")
            ran_latexmk = False
            passes = 0
            combined_log = ""

    if not ran_latexmk:
        # ── Path B: LaTeXer's own convergence loop ──
        # This is what latexmk does, implemented explicitly so LaTeXer never DEPENDS
        # on latexmk being installed: pass -> bibliography -> index -> glossaries ->
        # keep re-running while the log still says the references have not settled.
        argv = _engine_argv(tools, config, tex_name)
        logging.info("🛠️  %s (pass 1): %s" % (tools["engine"], " ".join(argv)))
        rc, out, err = _run_cmd(argv, env=env, cwd=work_dir, timeout=timeout)
        passes = 1
        combined_log = _read_build_log(work_dir, jobname) or (out + "\n" + err)
        steps.append(f"{tools['engine']} pass 1 -> rc={rc}")

        aux_ran = False
        if bib_mode == "biber" and tools["biber"]:
            brc, bout, berr = _run_cmd([tools["biber"], jobname], env=env, cwd=work_dir, timeout=timeout)
            steps.append(f"biber -> rc={brc}")
            combined_log += "\n[biber]\n" + (bout + berr)[-4000:]
            aux_ran = True
        elif bib_mode == "biber" and not tools["biber"]:
            steps.append("biber NOT FOUND — biblatex bibliography will be empty")
        elif bib_mode == "bibtex" and tools["bibtex"]:
            brc, bout, berr = _run_cmd([tools["bibtex"], jobname], env=env, cwd=work_dir, timeout=timeout)
            steps.append(f"bibtex -> rc={brc}")
            combined_log += "\n[bibtex]\n" + (bout + berr)[-4000:]
            aux_ran = True
        elif bib_mode == "bibtex" and not tools["bibtex"]:
            steps.append("bibtex NOT FOUND — bibliography will be empty")

        if needs["index"] and _as_bool(_cfg(config, "build_index", True), True) and tools["makeindex"]:
            irc, _o, _e = _run_cmd([tools["makeindex"], jobname], env=env, cwd=work_dir, timeout=timeout)
            steps.append(f"makeindex -> rc={irc}")
            aux_ran = True
        if needs["glossaries"] and _as_bool(_cfg(config, "build_glossaries", True), True) \
                and tools["makeglossaries"]:
            grc, _o, _e = _run_cmd([tools["makeglossaries"], jobname], env=env, cwd=work_dir, timeout=timeout)
            steps.append(f"makeglossaries -> rc={grc}")
            aux_ran = True

        while passes < max_passes:
            diag = _parse_latex_log(combined_log)
            if not (diag["needs_rerun"] or aux_ran):
                break
            aux_ran = False
            passes += 1
            logging.info("🔁 %s (pass %d): resolving cross-references" % (tools["engine"], passes))
            rc, out, err = _run_cmd(argv, env=env, cwd=work_dir, timeout=timeout)
            combined_log = _read_build_log(work_dir, jobname) or (out + "\n" + err)
            steps.append(f"{tools['engine']} pass {passes} -> rc={rc}")

    diag = _parse_latex_log(combined_log)
    pdf_path = os.path.join(work_dir, jobname + ".pdf")
    produced = os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0

    # A LaTeX engine can exit non-zero and STILL emit a usable PDF, and can exit zero
    # having emitted nothing. The FILE is the truth; rc is only a hint.
    ok = produced and not diag["errors"]
    return {
        "ok": ok, "produced": produced, "passes": passes, "pdf": pdf_path if produced else "",
        "diag": diag, "steps": steps, "log": combined_log, "returncode": rc,
        "bibliography": bib_mode, "needs": needs, "work_dir": work_dir, "jobname": jobname,
    }


def _clean_aux(work_dir: str, jobname: str = "", keep_log: bool = False) -> list:
    """Remove LaTeX auxiliary artifacts. NEVER touches a .tex, a .bib or a .pdf."""
    removed = []
    if not os.path.isdir(work_dir):
        return removed
    for entry in sorted(os.listdir(work_dir)):
        path = os.path.join(work_dir, entry)
        if not os.path.isfile(path):
            continue
        lower = entry.lower()
        if not lower.endswith(_AUX_EXTENSIONS):
            continue
        if keep_log and lower.endswith(".log"):
            continue
        if jobname and not lower.startswith(jobname.lower()):
            continue
        try:
            os.remove(path)
            removed.append(entry)
        except Exception:
            pass
    return removed


def _deliver_pdf(built_pdf: str, config: dict) -> tuple:
    """Copy the freshly-typeset PDF into the delivery folder with a collision-proof
    name. Returns (final_path, note)."""
    out_dir = os.path.normpath(_default_output_dir(config))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return built_pdf, f"could not create output_dir ({out_dir}): {e} — the PDF stays at {built_pdf}"
    name = _safe_basename(_cfg(config, "filename"), ".pdf") or _timestamped_name(".pdf")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    # normpath: an output_dir written with forward slashes (perfectly legal in YAML, and
    # what an LLM tends to emit) would otherwise produce a mixed-separator path like
    # C:/x/y\report.pdf in the very line we ask the user to click.
    target = _unique_path(os.path.normpath(os.path.join(out_dir, name)),
                          _as_bool(_cfg(config, "overwrite", False), False))
    try:
        shutil.copy2(built_pdf, target)
        return target, f"delivered to {target}"
    except Exception as e:
        return built_pdf, f"could not copy to {target}: {e} — the PDF stays at {built_pdf}"


# ========================================
# FAIL-SAFE PREFLIGHT — REFUSE rather than mis-typeset
# ========================================

def _preflight(action: str, config: dict, tools: dict) -> dict:
    """Validate BEFORE doing anything. Returns {ok, fatals, warnings}.

    Same contract as PDFer / STM32er / Nmapper: a refusal is the agent working as
    DESIGNED (a routable `status: refused` section), never a crash and never a
    silently-wrong PDF.
    """
    fatals, warnings = [], []

    if action not in _ALL_ACTIONS:
        fatals.append("Unknown action %r. Valid: %s." % (action, ", ".join(sorted(_ALL_ACTIONS))))
        return {"ok": False, "fatals": fatals, "warnings": warnings}

    if action in ("validate", "install"):
        return {"ok": True, "fatals": [], "warnings": warnings}

    # ---- a real TeX distribution, for the actions that typeset -------------
    if action in _NEED_ENGINE and not tools["latex"]:
        fatals.append(
            "No LaTeX engine (%s) found on this machine. %s"
            % (tools["engine"], _miktex_hint(tools["distribution"])))
    elif action in _NEED_ENGINE and tools["distribution"] not in ("miktex",):
        hint = _miktex_hint(tools["distribution"])
        if hint:
            warnings.append(hint)

    if _as_bool(_cfg(config, "shell_escape", False), False):
        warnings.append(
            "shell_escape is ON: this document may execute arbitrary commands on this "
            "machine via \\write18. Only do this for a document you fully trust.")

    if _as_tribool(_cfg(config, "use_latexmk", "auto"), "auto") == "true" \
            and not tools.get("latexmk_usable"):
        if tools.get("latexmk"):
            fatals.append(
                "use_latexmk is true, but the latexmk at %s cannot run on this machine — "
                "it is a Perl script and no Perl interpreter was found (MiKTeX does not "
                "bundle one). Either install Perl (e.g. Strawberry Perl) or set "
                "use_latexmk: auto, which uses LaTeXer's own convergence loop and needs "
                "no Perl at all." % tools["latexmk"])
        else:
            fatals.append("use_latexmk is true but latexmk was not found. Set use_latexmk: "
                          "auto to use LaTeXer's own convergence loop instead.")

    # ---- per-action inputs -------------------------------------------------
    tex_path = str(_cfg(config, "tex_path")).strip()
    project_dir = str(_cfg(config, "project_dir")).strip()
    input_text = str(_cfg(config, "input_text")).strip()

    if action in ("read_file", "validate_tex", "structure"):
        if not tex_path and not input_text:
            fatals.append("action '%s' needs tex_path (an existing .tex) or input_text." % action)
        elif tex_path and not os.path.isfile(tex_path):
            fatals.append("tex_path does not exist: %s" % tex_path)

    if action == "edit_file":
        if not tex_path:
            fatals.append("action 'edit_file' needs tex_path pointing at the .tex to modify.")
        elif not os.path.isfile(tex_path):
            fatals.append("tex_path does not exist: %s" % tex_path)
        mode = str(_cfg(config, "edit_mode", "replace")).strip().lower()
        if mode not in _EDIT_MODES:
            fatals.append("unknown edit_mode %r. Valid: %s." % (mode, ", ".join(_EDIT_MODES)))
        elif mode in ("replace", "insert_before", "insert_after") and not str(_cfg(config, "find_text")):
            fatals.append("edit_mode '%s' needs find_text (the anchor to locate)." % mode)
        if mode in ("append", "prepend") and not str(_cfg(config, "replace_text")):
            fatals.append("edit_mode '%s' needs replace_text (the text to add)." % mode)

    if action in ("list_files", "clean"):
        target = _work_base(config)
        if not target:
            fatals.append("action '%s' needs project_dir (the folder to work on)." % action)
        elif not os.path.isdir(target):
            fatals.append("project_dir is not a directory: %s" % target)

    if action == "compile_project":
        if not project_dir:
            fatals.append("action 'compile_project' needs project_dir (the folder holding the .tex set).")
        elif not os.path.isdir(project_dir):
            fatals.append("project_dir is not a directory: %s" % project_dir)

    if action == "compile" and not (tex_path or project_dir or input_text):
        fatals.append(
            "action 'compile' needs a source: tex_path (a .tex file), project_dir (a folder of "
            ".tex files) or input_text (raw LaTeX). Refusing to compile nothing.")
    if action == "compile" and tex_path and not os.path.isfile(tex_path):
        fatals.append("tex_path does not exist: %s" % tex_path)

    if action == "create_from_template":
        tpl = str(_cfg(config, "template", "article")).strip().lower()
        if tpl not in _TEMPLATES:
            fatals.append("unknown template %r. Available: %s." % (tpl, ", ".join(sorted(_TEMPLATES))))

    # ---- destination writability ------------------------------------------
    if action in ("compile", "compile_project", "scaffold_compile"):
        out_dir = _default_output_dir(config)
        try:
            os.makedirs(out_dir, exist_ok=True)
            probe = os.path.join(out_dir, ".latexer_write_probe_%d" % os.getpid())
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
        except Exception as e:
            fatals.append("output_dir is not writable (%s): %s" % (out_dir, e))

    return {"ok": not fatals, "fatals": fatals, "warnings": warnings}


def _format_preflight_report(pf: dict) -> str:
    lines = []
    if pf.get("fatals"):
        lines.append("BLOCKERS:")
        lines += ["  • " + item for item in pf["fatals"]]
    if pf.get("warnings"):
        lines.append("WARNINGS:")
        lines += ["  • " + item for item in pf["warnings"]]
    return "\n".join(lines) or "(no findings)"


# ========================================
# STRUCTURED OUTPUT (Parametrizer source)
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_LATEXER<<< block atomically (a SINGLE logging.info call).

    KV header field names MUST stay aligned with
    ``agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['latexer']``,
    ``views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['latexer']`` and
    ``parametrizer.SECTION_AGENT_TYPES``.
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_LATEXER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_LATEXER")


# ========================================
# ACTION HANDLERS
# ========================================

def _resolve_compile_source(config: dict, outcome: dict) -> tuple:
    """Resolve what to compile, in priority order. Returns (tex_path, note, error)."""
    tex_path = str(_cfg(config, "tex_path")).strip()
    if tex_path:
        return os.path.abspath(tex_path), "compiling the given file", ""

    project_dir = str(_cfg(config, "project_dir")).strip()
    if project_dir:
        main, note = _find_main_tex(
            os.path.abspath(project_dir), str(_cfg(config, "main_file")).strip(),
            _as_bool(_cfg(config, "recursive", True), True))
        if not main:
            return "", "", note
        return main, note, ""

    source = str(_cfg(config, "input_text"))
    if source.strip():
        if not _is_full_document(source):
            if not _as_bool(_cfg(config, "auto_preamble", True), True):
                return "", "", ("input_text has no \\documentclass/\\begin{document} and "
                                "auto_preamble is off — it is a fragment, not a document.")
            source = _wrap_fragment(source, config)
            note = "input_text was a fragment — wrapped in a generated preamble"
        else:
            note = "compiling the supplied LaTeX source"
        stem = os.path.splitext(_safe_basename(_cfg(config, "filename"), ".tex"))[0] or \
            os.path.splitext(_timestamped_name(".tex"))[0]
        proj = os.path.join(_projects_dir(config), stem)
        os.makedirs(proj, exist_ok=True)
        path = os.path.join(proj, stem + ".tex")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        outcome["project_dir"] = proj
        return path, note + f"; staged at {path}", ""

    return "", "", "no source: set tex_path, project_dir or input_text."


def _build(tex_path: str, config: dict, tools: dict, env: dict) -> dict:
    """The ONE entry point every compiling action goes through.

    With ``repair`` on (the default) this is the eight-rung repair ladder, so a
    document that would merely have failed is repaired, or -- at worst -- built
    with the offending block quarantined and named.  Set ``repair: false`` to
    get the bare single-shot compile back, byte for byte.
    """
    if _as_bool(_cfg(config, "repair", True), True):
        return _compile_with_ladder(tex_path, config, tools, env)
    return _compile(tex_path, config, tools, env)


def _finish_compile(result: dict, config: dict, tools: dict, outcome: dict, notes: list) -> bool:
    """Shared tail for compile / compile_project / scaffold_compile."""
    diag = result["diag"]
    # ---- Repair-ladder accounting, before anything else is decided ----------
    # These fields exist on EVERY build (empty when the ladder did not run), so
    # a downstream Forker can branch on {repairs} / {quarantined} unconditionally.
    outcome["repairs"] = len([r for r in (result.get("ladder") or []) if r.get("applied")])
    outcome["quarantined"] = len(result.get("quarantined") or [])
    outcome["engine"] = result.get("engine_used") or tools.get("engine", "")
    outcome["passes"] = result["passes"]
    outcome["errors"] = len(diag["errors"])
    outcome["warnings"] = len(diag["warnings"])
    outcome["bibliography"] = result.get("bibliography", "none")
    notes.extend("  " + s for s in result["steps"])

    if result.get("produced"):
        final, note = _deliver_pdf(result["pdf"], config)
        outcome.update({
            "output_path": final,
            "output_dir": os.path.dirname(final),
            "filename": os.path.basename(final),
            "page_count": diag["pages"],
            "bytes": os.path.getsize(final) if os.path.isfile(final) else diag["output_bytes"],
        })
        notes.append(note)
        if not _as_bool(_cfg(config, "keep_aux", False), False) and result["ok"]:
            removed = _clean_aux(result["work_dir"], result["jobname"], keep_log=True)
            if removed:
                notes.append("tidied %d auxiliary file(s) (the .log is kept)" % len(removed))
        if _as_bool(_cfg(config, "open_pdf", False), False) and os.name == "nt":
            try:
                os.startfile(final)  # noqa: S606 - user asked for the PDF to be opened
            except Exception:
                pass

    detail = _format_diagnostics(diag, tools["distribution"],
                                _as_bool(_cfg(config, "auto_install_packages", True), True),
                                _as_int(_cfg(config, "max_log_chars", 20000), 20000))
    if not result.get("produced") and not diag["errors"]:
        # NEVER print "errors: 0" beside "no PDF was produced" with nothing to act on —
        # that is a report that tells the user precisely nothing. When the log parser
        # finds no LaTeX-shaped error, the failure came from OUTSIDE LaTeX (a helper that
        # could not start, a timeout, a permission problem), so quote the raw output.
        raw = (result.get("log") or "").strip()
        detail = ((detail + "\n\n") if detail else "") + (
            "RAW TOOL OUTPUT (no LaTeX-shaped error was found, so the failure came from "
            "outside LaTeX itself):\n"
            + (raw[-4000:] if raw else "(the tool produced no output at all)"))
    if detail:
        notes.append("")
        notes.append(detail)

    # The ladder's audit trail goes into the body whenever it did anything, so
    # every automatic edit is visible and reviewable rather than invisible magic.
    if result.get("ladder"):
        notes.append("")
        notes.append(_format_ladder_report(result))

    if result.get("degraded") or result.get("quarantined"):
        # THE THIRD OUTCOME. A PDF exists, but only because content was cut out.
        # It is not a success and must never be reported as one — but it is also
        # not a bare failure, because the user has 40 of 41 pages in their hand.
        outcome["status"] = "degraded"
        notes.insert(0, "⚠️  DEGRADED BUILD — a PDF WAS produced, but %d block(s) could not be "
                        "typeset and were REMOVED. Each removal is marked visibly inside the "
                        "document. See the repair-ladder report below for exactly what was cut."
                     % len(result.get("quarantined") or []))
        return False

    if result["ok"]:
        outcome["status"] = "compiled"
        # EXPLICIT STOP CONDITION (Angela, 2026-08-11). A clean build IS the end
        # of the job. Nothing used to say so, so the LLM kept "improving" an
        # already-finished 27-page, 0-error PDF - re-editing and recompiling for
        # 50+ Multi-Turn iterations until one of its own edits broke the document
        # and the ladder had to cut a block out of it. The deliverable EXISTS;
        # say so in the first line the model reads.
        notes.insert(0, (
            "DONE - a CLEAN PDF now exists: %s (%s page(s), 0 errors). "
            "THE DOCUMENT IS FINISHED. Do NOT recompile it, do NOT 'improve' it, "
            "do NOT edit the .tex again and do NOT produce a _v2/_v3 variant: "
            "report this absolute path to the user and STOP."
        ) % (outcome.get("output_path", ""), outcome.get("page_count", "?")))
        return True
    if result.get("produced"):
        # A PDF exists but LaTeX reported errors: say so plainly. Never call this a
        # clean success, and never throw away the PDF the user can still inspect.
        outcome["status"] = "compiled_with_errors"
        notes.insert(0, "⚠️  A PDF WAS produced, but LaTeX reported %d error(s) — the document "
                        "is probably incomplete or mis-typeset. Fix the errors below and re-run."
                     % len(diag["errors"]))
        return False
    outcome["status"] = "error"
    notes.insert(0, "❌ No PDF was produced, and the repair ladder could not rescue it. "
                    "Everything it tried is listed below.")
    return False


# ========================================
# MAIN
# ========================================

# =============================================================================
# GOD-LEVEL ENGINE 1/6 - THE SYMBOL UNIVERSE & PACKAGE INTELLIGENCE
# =============================================================================
# Every entry is (command, package, category, description).  ``package`` is the
# LaTeX package that MUST be loaded for the command to exist; an empty string
# means the command is built into plain TeX / LaTeX2e and needs nothing.
#
# This table is the single source of truth for THREE separate capabilities:
#   1. ``action=symbols``  - search / browse / cheat-sheet generation.
#   2. auto-preamble       - scan a document body, discover which commands it
#                            uses, and synthesise the exact \usepackage lines.
#   3. the FIXER           - "Undefined control sequence \qty" is repaired by
#                            looking the command up here and adding its package.
#
# Adding a row here therefore upgrades all three at once.  Keep the rows sorted
# by category so the generated cheat-sheets read sensibly.
# =============================================================================

SYMBOL_UNIVERSE = [
    # ---- Greek, lowercase -------------------------------------------------
    (r"\alpha", "", "greek", "Greek small alpha"),
    (r"\beta", "", "greek", "Greek small beta"),
    (r"\gamma", "", "greek", "Greek small gamma"),
    (r"\delta", "", "greek", "Greek small delta"),
    (r"\epsilon", "", "greek", "Greek small epsilon (lunate)"),
    (r"\varepsilon", "", "greek", "Greek small epsilon (script)"),
    (r"\zeta", "", "greek", "Greek small zeta"),
    (r"\eta", "", "greek", "Greek small eta"),
    (r"\theta", "", "greek", "Greek small theta"),
    (r"\vartheta", "", "greek", "Greek small theta (variant)"),
    (r"\iota", "", "greek", "Greek small iota"),
    (r"\kappa", "", "greek", "Greek small kappa"),
    (r"\varkappa", "amssymb", "greek", "Greek small kappa (variant)"),
    (r"\lambda", "", "greek", "Greek small lambda"),
    (r"\mu", "", "greek", "Greek small mu"),
    (r"\nu", "", "greek", "Greek small nu"),
    (r"\xi", "", "greek", "Greek small xi"),
    (r"\pi", "", "greek", "Greek small pi"),
    (r"\varpi", "", "greek", "Greek small pi (variant)"),
    (r"\rho", "", "greek", "Greek small rho"),
    (r"\varrho", "", "greek", "Greek small rho (variant)"),
    (r"\sigma", "", "greek", "Greek small sigma"),
    (r"\varsigma", "", "greek", "Greek small final sigma"),
    (r"\tau", "", "greek", "Greek small tau"),
    (r"\upsilon", "", "greek", "Greek small upsilon"),
    (r"\phi", "", "greek", "Greek small phi"),
    (r"\varphi", "", "greek", "Greek small phi (variant)"),
    (r"\chi", "", "greek", "Greek small chi"),
    (r"\psi", "", "greek", "Greek small psi"),
    (r"\omega", "", "greek", "Greek small omega"),
    (r"\digamma", "amssymb", "greek", "Greek small digamma"),
    # ---- Greek, uppercase -------------------------------------------------
    (r"\Gamma", "", "greek", "Greek capital Gamma"),
    (r"\Delta", "", "greek", "Greek capital Delta (also Laplacian)"),
    (r"\Theta", "", "greek", "Greek capital Theta"),
    (r"\Lambda", "", "greek", "Greek capital Lambda"),
    (r"\Xi", "", "greek", "Greek capital Xi"),
    (r"\Pi", "", "greek", "Greek capital Pi (also product)"),
    (r"\Sigma", "", "greek", "Greek capital Sigma (also sum)"),
    (r"\Upsilon", "", "greek", "Greek capital Upsilon"),
    (r"\Phi", "", "greek", "Greek capital Phi"),
    (r"\Psi", "", "greek", "Greek capital Psi"),
    (r"\Omega", "", "greek", "Greek capital Omega (also ohm)"),
    (r"\varGamma", "amsmath", "greek", "Italic capital Gamma"),
    (r"\varDelta", "amsmath", "greek", "Italic capital Delta"),
    (r"\varTheta", "amsmath", "greek", "Italic capital Theta"),
    (r"\varLambda", "amsmath", "greek", "Italic capital Lambda"),
    (r"\varSigma", "amsmath", "greek", "Italic capital Sigma"),
    (r"\varPhi", "amsmath", "greek", "Italic capital Phi"),
    (r"\varPsi", "amsmath", "greek", "Italic capital Psi"),
    (r"\varOmega", "amsmath", "greek", "Italic capital Omega"),
    # ---- Binary operators -------------------------------------------------
    (r"\pm", "", "operators", "Plus-minus"),
    (r"\mp", "", "operators", "Minus-plus"),
    (r"\times", "", "operators", "Multiplication cross"),
    (r"\div", "", "operators", "Division sign"),
    (r"\cdot", "", "operators", "Centred dot product"),
    (r"\ast", "", "operators", "Asterisk operator"),
    (r"\star", "", "operators", "Star operator"),
    (r"\circ", "", "operators", "Composition ring"),
    (r"\bullet", "", "operators", "Bullet"),
    (r"\oplus", "", "operators", "Direct sum"),
    (r"\ominus", "", "operators", "Circled minus"),
    (r"\otimes", "", "operators", "Tensor product"),
    (r"\oslash", "", "operators", "Circled slash"),
    (r"\odot", "", "operators", "Circled dot (Hadamard)"),
    (r"\dagger", "", "operators", "Dagger (Hermitian adjoint)"),
    (r"\ddagger", "", "operators", "Double dagger"),
    (r"\amalg", "", "operators", "Amalgamation / coproduct"),
    (r"\wedge", "", "operators", "Logical and / wedge product"),
    (r"\vee", "", "operators", "Logical or / join"),
    (r"\cap", "", "operators", "Set intersection"),
    (r"\cup", "", "operators", "Set union"),
    (r"\sqcap", "", "operators", "Square intersection (meet)"),
    (r"\sqcup", "", "operators", "Square union (join)"),
    (r"\uplus", "", "operators", "Multiset union"),
    (r"\setminus", "", "operators", "Set difference"),
    (r"\boxplus", "amssymb", "operators", "Boxed plus"),
    (r"\boxtimes", "amssymb", "operators", "Boxed times"),
    (r"\boxdot", "amssymb", "operators", "Boxed dot"),
    (r"\ltimes", "amssymb", "operators", "Left semidirect product"),
    (r"\rtimes", "amssymb", "operators", "Right semidirect product"),
    (r"\divideontimes", "amssymb", "operators", "Divide on times"),
    (r"\intercal", "amssymb", "operators", "Intercal (transpose)"),
    (r"\smallsetminus", "amssymb", "operators", "Small set minus"),
    (r"\curlywedge", "amssymb", "operators", "Curly wedge"),
    (r"\curlyvee", "amssymb", "operators", "Curly vee"),
    (r"\circledast", "amssymb", "operators", "Circled asterisk (convolution)"),
    (r"\circledcirc", "amssymb", "operators", "Circled ring"),
    (r"\circleddash", "amssymb", "operators", "Circled dash"),
    (r"\dotplus", "amssymb", "operators", "Dotted plus"),
    (r"\barwedge", "amssymb", "operators", "Barred wedge (NAND)"),
    (r"\veebar", "amssymb", "operators", "Vee bar (XOR)"),
    # ---- Big operators ----------------------------------------------------
    (r"\sum", "", "bigops", "Summation"),
    (r"\prod", "", "bigops", "Product"),
    (r"\coprod", "", "bigops", "Coproduct"),
    (r"\int", "", "bigops", "Integral"),
    (r"\iint", "amsmath", "bigops", "Double integral"),
    (r"\iiint", "amsmath", "bigops", "Triple integral"),
    (r"\iiiint", "amsmath", "bigops", "Quadruple integral"),
    (r"\idotsint", "amsmath", "bigops", "Integral with dots"),
    (r"\oint", "", "bigops", "Contour integral"),
    (r"\oiint", "esint", "bigops", "Closed surface integral"),
    (r"\oiiint", "esint", "bigops", "Closed volume integral"),
    (r"\bigcap", "", "bigops", "Big intersection"),
    (r"\bigcup", "", "bigops", "Big union"),
    (r"\bigsqcup", "", "bigops", "Big square union"),
    (r"\bigvee", "", "bigops", "Big vee"),
    (r"\bigwedge", "", "bigops", "Big wedge"),
    (r"\bigoplus", "", "bigops", "Big direct sum"),
    (r"\bigotimes", "", "bigops", "Big tensor product"),
    (r"\bigodot", "", "bigops", "Big circled dot"),
    (r"\biguplus", "", "bigops", "Big multiset union"),
    # ---- Relations --------------------------------------------------------
    (r"\leq", "", "relations", "Less than or equal"),
    (r"\geq", "", "relations", "Greater than or equal"),
    (r"\ll", "", "relations", "Much less than"),
    (r"\gg", "", "relations", "Much greater than"),
    (r"\lll", "amssymb", "relations", "Very much less than"),
    (r"\ggg", "amssymb", "relations", "Very much greater than"),
    (r"\leqslant", "amssymb", "relations", "Slanted less-or-equal"),
    (r"\geqslant", "amssymb", "relations", "Slanted greater-or-equal"),
    (r"\neq", "", "relations", "Not equal"),
    (r"\equiv", "", "relations", "Equivalent / congruent mod"),
    (r"\sim", "", "relations", "Similar / distributed as"),
    (r"\simeq", "", "relations", "Similar or equal"),
    (r"\approx", "", "relations", "Approximately equal"),
    (r"\approxeq", "amssymb", "relations", "Approximately equal to"),
    (r"\cong", "", "relations", "Congruent / isomorphic"),
    (r"\propto", "", "relations", "Proportional to"),
    (r"\asymp", "", "relations", "Asymptotically equal"),
    (r"\doteq", "", "relations", "Dot equal"),
    (r"\triangleq", "amssymb", "relations", "Defined as (triangle equal)"),
    (r"\subset", "", "relations", "Subset"),
    (r"\supset", "", "relations", "Superset"),
    (r"\subseteq", "", "relations", "Subset or equal"),
    (r"\supseteq", "", "relations", "Superset or equal"),
    (r"\subsetneq", "amssymb", "relations", "Proper subset"),
    (r"\supsetneq", "amssymb", "relations", "Proper superset"),
    (r"\sqsubseteq", "", "relations", "Square subset or equal"),
    (r"\sqsupseteq", "", "relations", "Square superset or equal"),
    (r"\in", "", "relations", "Element of"),
    (r"\ni", "", "relations", "Contains as member"),
    (r"\notin", "", "relations", "Not an element of"),
    (r"\perp", "", "relations", "Perpendicular / orthogonal"),
    (r"\parallel", "", "relations", "Parallel"),
    (r"\mid", "", "relations", "Divides / conditional bar"),
    (r"\nmid", "amssymb", "relations", "Does not divide"),
    (r"\vdash", "", "relations", "Proves / turnstile"),
    (r"\dashv", "", "relations", "Reverse turnstile"),
    (r"\models", "", "relations", "Models / entails"),
    (r"\vDash", "amssymb", "relations", "Double turnstile"),
    (r"\Vdash", "amssymb", "relations", "Forces"),
    (r"\prec", "", "relations", "Precedes"),
    (r"\succ", "", "relations", "Succeeds"),
    (r"\preceq", "", "relations", "Precedes or equal"),
    (r"\succeq", "", "relations", "Succeeds or equal"),
    (r"\lesssim", "amssymb", "relations", "Less than or similar"),
    (r"\gtrsim", "amssymb", "relations", "Greater than or similar"),
    (r"\bowtie", "", "relations", "Bowtie (natural join)"),
    (r"\smile", "", "relations", "Smile"),
    (r"\frown", "", "relations", "Frown"),
    (r"\between", "amssymb", "relations", "Between"),
    (r"\pitchfork", "amssymb", "relations", "Pitchfork (transversal)"),
    (r"\therefore", "amssymb", "relations", "Therefore"),
    (r"\because", "amssymb", "relations", "Because"),
    # ---- Negated relations ------------------------------------------------
    (r"\nless", "amssymb", "negations", "Not less than"),
    (r"\ngtr", "amssymb", "negations", "Not greater than"),
    (r"\nleq", "amssymb", "negations", "Not less or equal"),
    (r"\ngeq", "amssymb", "negations", "Not greater or equal"),
    (r"\nsim", "amssymb", "negations", "Not similar"),
    (r"\ncong", "amssymb", "negations", "Not congruent"),
    (r"\nsubseteq", "amssymb", "negations", "Not a subset"),
    (r"\nsupseteq", "amssymb", "negations", "Not a superset"),
    (r"\nparallel", "amssymb", "negations", "Not parallel"),
    (r"\nvdash", "amssymb", "negations", "Does not prove"),
    (r"\nvDash", "amssymb", "negations", "Does not entail"),
    (r"\nrightarrow", "amssymb", "negations", "Does not map to"),
    (r"\nleftarrow", "amssymb", "negations", "Not left arrow"),
    (r"\nleftrightarrow", "amssymb", "negations", "Not both ways"),
    (r"\nRightarrow", "amssymb", "negations", "Does not imply"),
    (r"\nLeftrightarrow", "amssymb", "negations", "Not equivalent"),
    # ---- Arrows -----------------------------------------------------------
    (r"\leftarrow", "", "arrows", "Left arrow"),
    (r"\rightarrow", "", "arrows", "Right arrow (maps to)"),
    (r"\to", "", "arrows", "Right arrow (short form)"),
    (r"\leftrightarrow", "", "arrows", "Left-right arrow"),
    (r"\Leftarrow", "", "arrows", "Double left arrow (implied by)"),
    (r"\Rightarrow", "", "arrows", "Double right arrow (implies)"),
    (r"\Leftrightarrow", "", "arrows", "Double left-right (iff)"),
    (r"\iff", "", "arrows", "If and only if (spaced)"),
    (r"\implies", "amsmath", "arrows", "Implies (spaced)"),
    (r"\impliedby", "amsmath", "arrows", "Implied by (spaced)"),
    (r"\mapsto", "", "arrows", "Maps to"),
    (r"\longmapsto", "", "arrows", "Long maps to"),
    (r"\hookleftarrow", "", "arrows", "Hook left arrow"),
    (r"\hookrightarrow", "", "arrows", "Hook right arrow (injection)"),
    (r"\twoheadrightarrow", "amssymb", "arrows", "Two-headed arrow (surjection)"),
    (r"\rightarrowtail", "amssymb", "arrows", "Arrow with tail (injection)"),
    (r"\leftharpoonup", "", "arrows", "Left harpoon up"),
    (r"\rightharpoonup", "", "arrows", "Right harpoon up"),
    (r"\rightleftharpoons", "", "arrows", "Equilibrium arrows"),
    (r"\leftrightharpoons", "amssymb", "arrows", "Reverse equilibrium"),
    (r"\uparrow", "", "arrows", "Up arrow"),
    (r"\downarrow", "", "arrows", "Down arrow"),
    (r"\updownarrow", "", "arrows", "Up-down arrow"),
    (r"\Uparrow", "", "arrows", "Double up arrow"),
    (r"\Downarrow", "", "arrows", "Double down arrow"),
    (r"\nearrow", "", "arrows", "North-east arrow"),
    (r"\searrow", "", "arrows", "South-east arrow"),
    (r"\swarrow", "", "arrows", "South-west arrow"),
    (r"\nwarrow", "", "arrows", "North-west arrow"),
    (r"\rightsquigarrow", "amssymb", "arrows", "Squiggly arrow (rewrites to)"),
    (r"\leadsto", "amssymb", "arrows", "Leads to"),
    (r"\circlearrowleft", "amssymb", "arrows", "Anticlockwise circle arrow"),
    (r"\circlearrowright", "amssymb", "arrows", "Clockwise circle arrow"),
    (r"\rightrightarrows", "amssymb", "arrows", "Parallel right arrows"),
    (r"\leftleftarrows", "amssymb", "arrows", "Parallel left arrows"),
    (r"\rightleftarrows", "amssymb", "arrows", "Opposed arrows"),
    (r"\xrightarrow", "amsmath", "arrows", "Extensible right arrow with label"),
    (r"\xleftarrow", "amsmath", "arrows", "Extensible left arrow with label"),
    (r"\xrightleftharpoons", "mathtools", "arrows", "Extensible equilibrium"),
    # ---- Set theory & logic ----------------------------------------------
    (r"\emptyset", "", "logic", "Empty set"),
    (r"\varnothing", "amssymb", "logic", "Empty set (preferred glyph)"),
    (r"\forall", "", "logic", "Universal quantifier"),
    (r"\exists", "", "logic", "Existential quantifier"),
    (r"\nexists", "amssymb", "logic", "Does not exist"),
    (r"\neg", "", "logic", "Logical negation"),
    (r"\lnot", "", "logic", "Logical not (alias)"),
    (r"\land", "", "logic", "Logical and"),
    (r"\lor", "", "logic", "Logical or"),
    (r"\top", "", "logic", "Top / true"),
    (r"\bot", "", "logic", "Bottom / false / perp"),
    (r"\aleph", "", "logic", "Aleph (cardinal)"),
    (r"\beth", "amssymb", "logic", "Beth number"),
    (r"\gimel", "amssymb", "logic", "Gimel number"),
    (r"\daleth", "amssymb", "logic", "Daleth number"),
    (r"\complement", "amssymb", "logic", "Set complement"),
    (r"\mathbb{N}", "amssymb", "logic", "Natural numbers"),
    (r"\mathbb{Z}", "amssymb", "logic", "Integers"),
    (r"\mathbb{Q}", "amssymb", "logic", "Rationals"),
    (r"\mathbb{R}", "amssymb", "logic", "Reals"),
    (r"\mathbb{C}", "amssymb", "logic", "Complex numbers"),
    (r"\mathbb{H}", "amssymb", "logic", "Quaternions"),
    (r"\mathbb{F}", "amssymb", "logic", "Field"),
    (r"\mathbb{P}", "amssymb", "logic", "Probability measure"),
    (r"\mathbb{E}", "amssymb", "logic", "Expectation operator"),
    # ---- Calculus & analysis ---------------------------------------------
    (r"\partial", "", "calculus", "Partial derivative"),
    (r"\nabla", "", "calculus", "Nabla / del / gradient"),
    (r"\infty", "", "calculus", "Infinity"),
    (r"\lim", "", "calculus", "Limit operator"),
    (r"\limsup", "", "calculus", "Limit superior"),
    (r"\liminf", "", "calculus", "Limit inferior"),
    (r"\varliminf", "amsmath", "calculus", "Underlined lim (variant)"),
    (r"\varlimsup", "amsmath", "calculus", "Overlined lim (variant)"),
    (r"\sup", "", "calculus", "Supremum"),
    (r"\inf", "", "calculus", "Infimum"),
    (r"\max", "", "calculus", "Maximum"),
    (r"\min", "", "calculus", "Minimum"),
    (r"\arg", "", "calculus", "Argument"),
    (r"\det", "", "calculus", "Determinant"),
    (r"\dim", "", "calculus", "Dimension"),
    (r"\ker", "", "calculus", "Kernel"),
    (r"\deg", "", "calculus", "Degree"),
    (r"\gcd", "", "calculus", "Greatest common divisor"),
    (r"\exp", "", "calculus", "Exponential"),
    (r"\log", "", "calculus", "Logarithm"),
    (r"\ln", "", "calculus", "Natural logarithm"),
    (r"\sin", "", "calculus", "Sine"),
    (r"\cos", "", "calculus", "Cosine"),
    (r"\tan", "", "calculus", "Tangent"),
    (r"\sinh", "", "calculus", "Hyperbolic sine"),
    (r"\cosh", "", "calculus", "Hyperbolic cosine"),
    (r"\tanh", "", "calculus", "Hyperbolic tangent"),
    (r"\operatorname", "amsmath", "calculus", "Declare an upright operator"),
    (r"\DeclareMathOperator", "amsmath", "calculus", "Define a new operator"),
    (r"\dd", "physics", "calculus", "Upright differential d"),
    (r"\dv", "physics", "calculus", "Total derivative d/dx"),
    (r"\pdv", "physics", "calculus", "Partial derivative"),
    (r"\grad", "physics", "calculus", "Gradient"),
    (r"\divergence", "physics", "calculus", "Divergence"),
    (r"\curl", "physics", "calculus", "Curl"),
    (r"\laplacian", "physics", "calculus", "Laplacian"),
    # ---- Quantum mechanics ------------------------------------------------
    (r"\ket", "braket", "quantum", "Dirac ket |psi>"),
    (r"\bra", "braket", "quantum", "Dirac bra <psi|"),
    (r"\braket", "braket", "quantum", "Inner product <a|b>"),
    (r"\ketbra", "braket", "quantum", "Outer product |a><b|"),
    (r"\Ket", "braket", "quantum", "Auto-sized ket"),
    (r"\Bra", "braket", "quantum", "Auto-sized bra"),
    (r"\Braket", "braket", "quantum", "Auto-sized inner product"),
    (r"\expval", "physics", "quantum", "Expectation value <A>"),
    (r"\ev", "physics", "quantum", "Expectation value (short)"),
    (r"\matrixel", "physics", "quantum", "Matrix element <a|A|b>"),
    (r"\mel", "physics", "quantum", "Matrix element (short)"),
    (r"\comm", "physics", "quantum", "Commutator [A,B]"),
    (r"\acomm", "physics", "quantum", "Anticommutator {A,B}"),
    (r"\poissonbracket", "physics", "quantum", "Poisson bracket"),
    (r"\hbar", "", "quantum", "Reduced Planck constant"),
    (r"\hslash", "amssymb", "quantum", "Reduced Planck (variant)"),
    (r"\dagger", "", "quantum", "Hermitian conjugate"),
    (r"\otimes", "", "quantum", "Tensor product of states"),
    (r"\Tr", "physics", "quantum", "Trace operator"),
    (r"\tr", "physics", "quantum", "Trace (lowercase)"),
    # NOTE: \qty is deliberately NOT listed here even though the physics package
    # defines it.  siunitx v3 also defines \qty, the two genuinely clash, and
    # \qty{5}{\meter} (siunitx) is overwhelmingly the more common usage -- so the
    # units section below owns the mapping and PACKAGE_CONFLICTS records the clash.
    (r"\eval", "physics", "quantum", "Evaluation bar"),
    (r"\order", "physics", "quantum", "Order-of notation"),
    (r"\slashed", "slashed", "quantum", "Feynman slash notation"),
    (r"\qtysingle", "physics", "quantum", "Single quantity"),
    # ---- Tensors & index notation ----------------------------------------
    (r"\tensor", "tensor", "tensors", "Tensor with staggered indices"),
    (r"\indices", "tensor", "tensors", "Index specification"),
    (r"\prescript", "mathtools", "tensors", "Pre-superscript/subscript"),
    (r"\overline", "", "tensors", "Overline (conjugate)"),
    (r"\underline", "", "tensors", "Underline"),
    (r"\widehat", "", "tensors", "Wide hat (operator)"),
    (r"\widetilde", "", "tensors", "Wide tilde"),
    (r"\overrightarrow", "", "tensors", "Vector arrow over"),
    (r"\vec", "", "tensors", "Vector arrow"),
    (r"\bm", "bm", "tensors", "Bold math (vectors/tensors)"),
    (r"\boldsymbol", "amsmath", "tensors", "Bold symbol"),
    (r"\mathbf", "", "tensors", "Upright bold"),
    (r"\mathrm", "", "tensors", "Upright roman"),
    (r"\mathcal", "", "tensors", "Calligraphic"),
    (r"\mathscr", "mathrsfs", "tensors", "Script (Ralph Smith)"),
    (r"\mathfrak", "amssymb", "tensors", "Fraktur"),
    (r"\mathbb", "amssymb", "tensors", "Blackboard bold"),
    # ---- Category theory --------------------------------------------------
    (r"\xrightarrow", "amsmath", "category", "Labelled morphism arrow"),
    (r"\rightrightarrows", "amssymb", "category", "Parallel morphisms"),
    (r"\hookrightarrow", "", "category", "Monomorphism"),
    (r"\twoheadrightarrow", "amssymb", "category", "Epimorphism"),
    (r"\dashrightarrow", "amssymb", "category", "Dashed (unique) arrow"),
    (r"\Longrightarrow", "", "category", "Long double arrow"),
    (r"\circ", "", "category", "Composition"),
    (r"\cong", "", "category", "Natural isomorphism"),
    (r"\simeq", "", "category", "Equivalence of categories"),
    # ---- Delimiters -------------------------------------------------------
    (r"\left", "", "delimiters", "Open auto-sized delimiter"),
    (r"\right", "", "delimiters", "Close auto-sized delimiter"),
    (r"\big", "", "delimiters", "Manually enlarged delimiter"),
    (r"\Big", "", "delimiters", "Larger delimiter"),
    (r"\bigg", "", "delimiters", "Even larger delimiter"),
    (r"\Bigg", "", "delimiters", "Largest standard delimiter"),
    (r"\langle", "", "delimiters", "Left angle bracket"),
    (r"\rangle", "", "delimiters", "Right angle bracket"),
    (r"\lceil", "", "delimiters", "Left ceiling"),
    (r"\rceil", "", "delimiters", "Right ceiling"),
    (r"\lfloor", "", "delimiters", "Left floor"),
    (r"\rfloor", "", "delimiters", "Right floor"),
    (r"\lVert", "amsmath", "delimiters", "Left double bar (norm)"),
    (r"\rVert", "amsmath", "delimiters", "Right double bar (norm)"),
    (r"\lvert", "amsmath", "delimiters", "Left single bar"),
    (r"\rvert", "amsmath", "delimiters", "Right single bar"),
    (r"\llbracket", "stmaryrd", "delimiters", "Left double square bracket"),
    (r"\rrbracket", "stmaryrd", "delimiters", "Right double square bracket"),
    (r"\DeclarePairedDelimiter", "mathtools", "delimiters", "Define a delimiter pair"),
    # ---- Math structures --------------------------------------------------
    (r"\frac", "", "structures", "Fraction"),
    (r"\dfrac", "amsmath", "structures", "Display-style fraction"),
    (r"\tfrac", "amsmath", "structures", "Text-style fraction"),
    (r"\cfrac", "amsmath", "structures", "Continued fraction"),
    (r"\binom", "amsmath", "structures", "Binomial coefficient"),
    (r"\dbinom", "amsmath", "structures", "Display binomial"),
    (r"\sqrt", "", "structures", "Square / nth root"),
    (r"\substack", "amsmath", "structures", "Multi-line subscript"),
    (r"\overbrace", "", "structures", "Overbrace"),
    (r"\underbrace", "", "structures", "Underbrace"),
    (r"\overset", "amsmath", "structures", "Symbol above"),
    (r"\underset", "amsmath", "structures", "Symbol below"),
    (r"\stackrel", "", "structures", "Stack relation"),
    (r"\text", "amsmath", "structures", "Upright text inside math"),
    (r"\intertext", "amsmath", "structures", "Text between aligned lines"),
    (r"\shortintertext", "mathtools", "structures", "Tight text between lines"),
    (r"\tag", "amsmath", "structures", "Manual equation tag"),
    (r"\notag", "amsmath", "structures", "Suppress equation number"),
    (r"\numberwithin", "amsmath", "structures", "Number equations per section"),
    (r"\eqref", "amsmath", "structures", "Reference with parentheses"),
    (r"\cref", "cleveref", "structures", "Clever reference (auto type)"),
    (r"\Cref", "cleveref", "structures", "Clever reference capitalised"),
    (r"\phantom", "", "structures", "Invisible spacing box"),
    (r"\mathclap", "mathtools", "structures", "Clap a limit horizontally"),
    (r"\coloneqq", "mathtools", "structures", "Definition := symbol"),
    (r"\eqqcolon", "mathtools", "structures", "Reverse definition =:"),
    # ---- Chemistry & units ------------------------------------------------
    (r"\ce", "mhchem", "chemistry", "Chemical equation / formula"),
    (r"\chemfig", "chemfig", "chemistry", "Structural molecule diagram"),
    (r"\SI", "siunitx", "units", "Number with unit (legacy)"),
    (r"\qty", "siunitx", "units", "Number with unit (siunitx v3)"),
    (r"\si", "siunitx", "units", "Unit alone (legacy)"),
    (r"\unit", "siunitx", "units", "Unit alone (siunitx v3)"),
    (r"\num", "siunitx", "units", "Formatted number"),
    (r"\numrange", "siunitx", "units", "Formatted number range"),
    (r"\ang", "siunitx", "units", "Angle in degrees"),
    (r"\SIrange", "siunitx", "units", "Quantity range (legacy)"),
    # ---- Typography & layout ---------------------------------------------
    (r"\textbf", "", "typography", "Bold text"),
    (r"\textit", "", "typography", "Italic text"),
    (r"\texttt", "", "typography", "Monospace text"),
    (r"\textsc", "", "typography", "Small capitals"),
    (r"\emph", "", "typography", "Emphasis"),
    (r"\includegraphics", "graphicx", "typography", "Insert an image"),
    (r"\resizebox", "graphicx", "typography", "Scale a box"),
    (r"\rotatebox", "graphicx", "typography", "Rotate a box"),
    (r"\toprule", "booktabs", "typography", "Professional table top rule"),
    (r"\midrule", "booktabs", "typography", "Professional table mid rule"),
    (r"\bottomrule", "booktabs", "typography", "Professional table bottom rule"),
    (r"\cmidrule", "booktabs", "typography", "Partial rule"),
    (r"\multirow", "multirow", "typography", "Cell spanning rows"),
    (r"\multicolumn", "", "typography", "Cell spanning columns"),
    (r"\href", "hyperref", "typography", "Hyperlink with text"),
    (r"\url", "hyperref", "typography", "Bare URL"),
    (r"\hyperref", "hyperref", "typography", "Internal hyperlink"),
    (r"\lstinputlisting", "listings", "typography", "Include source file"),
    (r"\lstset", "listings", "typography", "Configure code listings"),
    (r"\mintinline", "minted", "typography", "Inline highlighted code"),
    (r"\definecolor", "xcolor", "typography", "Define a colour"),
    (r"\textcolor", "xcolor", "typography", "Coloured text"),
    (r"\colorbox", "xcolor", "typography", "Coloured background box"),
    (r"\fcolorbox", "xcolor", "typography", "Framed coloured box"),
    (r"\geometry", "geometry", "typography", "Page geometry setup"),
    (r"\setlist", "enumitem", "typography", "Configure list spacing"),
    (r"\captionsetup", "caption", "typography", "Configure captions"),
    (r"\subcaptionbox", "subcaption", "typography", "Sub-figure with caption"),
    (r"\FloatBarrier", "placeins", "typography", "Barrier for floats"),
    (r"\microtypesetup", "microtype", "typography", "Micro-typography tuning"),
    (r"\SetWatermarkText", "draftwatermark", "typography", "Draft watermark"),
    (r"\todo", "todonotes", "typography", "Margin TODO note"),
    (r"\newtcolorbox", "tcolorbox", "typography", "Define a coloured box"),
    (r"\qrcode", "qrcode", "typography", "QR code"),
    # ---- Theorem & proof --------------------------------------------------
    (r"\newtheorem", "amsthm", "theorems", "Declare a theorem environment"),
    (r"\theoremstyle", "amsthm", "theorems", "Select theorem style"),
    (r"\qedhere", "amsthm", "theorems", "Place the QED box inline"),
    (r"\blacksquare", "amssymb", "theorems", "QED filled square"),
    (r"\square", "amssymb", "theorems", "Open square"),
    (r"\declaretheorem", "thmtools", "theorems", "Advanced theorem declaration"),
    # ---- Bibliography -----------------------------------------------------
    (r"\cite", "", "bibliography", "Citation"),
    (r"\citep", "natbib", "bibliography", "Parenthetical citation"),
    (r"\citet", "natbib", "bibliography", "Textual citation"),
    (r"\parencite", "biblatex", "bibliography", "Parenthetical citation"),
    (r"\textcite", "biblatex", "bibliography", "Textual citation"),
    (r"\autocite", "biblatex", "bibliography", "Automatic citation"),
    (r"\addbibresource", "biblatex", "bibliography", "Declare a .bib file"),
    (r"\printbibliography", "biblatex", "bibliography", "Print the bibliography"),
    (r"\bibliography", "", "bibliography", "BibTeX bibliography"),
    (r"\bibliographystyle", "", "bibliography", "BibTeX style"),
    # ---- Diagrams ---------------------------------------------------------
    (r"\begin{tikzpicture}", "tikz", "diagrams", "TikZ drawing canvas"),
    (r"\tikz", "tikz", "diagrams", "Inline TikZ"),
    (r"\node", "tikz", "diagrams", "TikZ node"),
    (r"\draw", "tikz", "diagrams", "TikZ path"),
    (r"\usetikzlibrary", "tikz", "diagrams", "Load a TikZ library"),
    (r"\begin{axis}", "pgfplots", "diagrams", "PGFPlots axis"),
    (r"\addplot", "pgfplots", "diagrams", "PGFPlots data series"),
    (r"\addplot3", "pgfplots", "diagrams", "PGFPlots 3D series"),
    (r"\pgfplotsset", "pgfplots", "diagrams", "PGFPlots configuration"),
    (r"\begin{circuitikz}", "circuitikz", "diagrams", "Circuit diagram canvas"),
    (r"\begin{quantikz}", "quantikz", "diagrams", "Quantum circuit canvas"),
    (r"\lstick", "quantikz", "diagrams", "Quantum wire label (left)"),
    (r"\rstick", "quantikz", "diagrams", "Quantum wire label (right)"),
    (r"\gate", "quantikz", "diagrams", "Quantum gate box"),
    (r"\ctrl", "quantikz", "diagrams", "Control node"),
    (r"\targ", "quantikz", "diagrams", "CNOT target"),
    # NOTE: quantikz also defines \meter (the measurement gate), but \meter is
    # FAR more often siunitx's unit -- \qty{5}{\meter}. Mapping it to quantikz
    # made LaTeXer add \usepackage{quantikz} to documents about rope lengths.
    # A name this generic is not safe to own, so quantikz claims only its
    # unambiguous commands (\gate, \ctrl, \targ, \qw, \lstick, \rstick).
    (r"\qw", "quantikz", "diagrams", "Quantum wire"),
    (r"\begin{tikzcd}", "tikz-cd", "diagrams", "Commutative diagram"),
    (r"\arrow", "tikz-cd", "diagrams", "Commutative diagram arrow"),
    (r"\feynmandiagram", "tikz-feynman", "diagrams", "Feynman diagram"),
    (r"\begin{forest}", "forest", "diagrams", "Tree diagram"),
    (r"\begin{ganttchart}", "pgfgantt", "diagrams", "Gantt chart"),
    (r"\begin{sequencediagram}", "pgf-umlsd", "diagrams", "UML sequence diagram"),
    (r"\begin{venndiagram3sets}", "venndiagram", "diagrams", "Venn diagram"),
    (r"\smartdiagram", "smartdiagram", "diagrams", "Preset smart diagram"),
]

# --- Derived indices ------------------------------------------------------
# Built lazily so importing the module stays cheap; every consumer goes through
# the accessors below rather than touching the raw list.
_SYMBOL_BY_COMMAND = {}
_SYMBOLS_BY_CATEGORY = {}
_COMMAND_TO_PACKAGE = {}


def _build_symbol_indices() -> None:
    """Populate the three derived lookup structures exactly once."""
    if _SYMBOL_BY_COMMAND:
        return
    for command, package, category, description in SYMBOL_UNIVERSE:
        bare = command.split("{")[0]
        _SYMBOL_BY_COMMAND.setdefault(bare, (command, package, category, description))
        _SYMBOLS_BY_CATEGORY.setdefault(category, []).append(
            (command, package, category, description)
        )
        # ⚠️ ENVIRONMENT ROWS MUST NOT ENTER THE COMMAND MAP.
        # ``\begin{tikzpicture}`` splits on '{' to the bare token ``\begin`` --
        # so registering it here would make EVERY \begin in EVERY document infer
        # tikz, and LaTeXer would silently inject \usepackage{tikz} into a plain
        # letter. Environments are resolved by ENVIRONMENT_TO_PACKAGE instead,
        # which matches the environment NAME. Caught by the ladder's own trace
        # printing "added tikz (tikz needed by \begin)" on 11 unrelated cases.
        if package and not command.startswith("\\begin{"):
            # First package wins: the table is ordered so the canonical
            # provider (amsmath before mathtools, siunitx for \qty) is listed
            # first for any command with several providers.
            _COMMAND_TO_PACKAGE.setdefault(bare, package)


def symbol_categories() -> list:
    """Sorted list of every category name in the universe."""
    _build_symbol_indices()
    return sorted(_SYMBOLS_BY_CATEGORY.keys())


def symbol_count() -> int:
    """Total number of catalogued symbols."""
    return len(SYMBOL_UNIVERSE)


def lookup_symbol(command: str):
    """Return the universe row for ``command`` (leading backslash optional)."""
    _build_symbol_indices()
    name = command.strip()
    if name and not name.startswith("\\"):
        name = "\\" + name
    return _SYMBOL_BY_COMMAND.get(name.split("{")[0])


def search_symbols(query: str, category: str = "", limit: int = 60) -> list:
    """Fuzzy search over command names AND descriptions.

    An empty ``query`` with a ``category`` lists that whole category, which is
    what powers the generated cheat-sheets.
    """
    _build_symbol_indices()
    needle = (query or "").strip().lower().lstrip("\\")
    wanted = (category or "").strip().lower()
    hits = []
    for row in SYMBOL_UNIVERSE:
        command, package, cat, description = row
        if wanted and cat != wanted:
            continue
        if not needle:
            hits.append(row)
        elif needle in command.lower() or needle in description.lower():
            hits.append(row)
        if len(hits) >= max(1, limit):
            break
    return hits


# --- Package intelligence -------------------------------------------------
# Environments are matched separately from commands because ``\begin{align}``
# is the trigger, not a control sequence of its own.
ENVIRONMENT_TO_PACKAGE = {
    "align": "amsmath",
    "align*": "amsmath",
    "alignat": "amsmath",
    "alignat*": "amsmath",
    "gather": "amsmath",
    "gather*": "amsmath",
    "multline": "amsmath",
    "multline*": "amsmath",
    "split": "amsmath",
    "cases": "amsmath",
    "dcases": "mathtools",
    "rcases": "mathtools",
    "matrix": "amsmath",
    "pmatrix": "amsmath",
    "bmatrix": "amsmath",
    "Bmatrix": "amsmath",
    "vmatrix": "amsmath",
    "Vmatrix": "amsmath",
    "smallmatrix": "amsmath",
    "psmallmatrix": "mathtools",
    "subequations": "amsmath",
    "equation": "",
    "equation*": "amsmath",
    "theorem": "amsthm",
    "proof": "amsthm",
    "lemma": "amsthm",
    "corollary": "amsthm",
    "definition": "amsthm",
    "remark": "amsthm",
    "example": "amsthm",
    "tikzpicture": "tikz",
    "axis": "pgfplots",
    "semilogxaxis": "pgfplots",
    "semilogyaxis": "pgfplots",
    "loglogaxis": "pgfplots",
    "groupplot": "pgfplots",
    "circuitikz": "circuitikz",
    "quantikz": "quantikz",
    "tikzcd": "tikz-cd",
    "forest": "forest",
    "ganttchart": "pgfgantt",
    "algorithm": "algorithm",
    "algorithmic": "algpseudocode",
    "algorithmize": "algorithm2e",
    "lstlisting": "listings",
    "minted": "minted",
    "tcolorbox": "tcolorbox",
    "subfigure": "subcaption",
    "longtable": "longtable",
    "tabularx": "tabularx",
    "tabulary": "tabulary",
    "wrapfigure": "wrapfig",
    "adjustwidth": "changepage",
    "multicols": "multicol",
    "landscape": "pdflscape",
    "frame": "",
    "columns": "",
    "venndiagram3sets": "venndiagram",
    "sequencediagram": "pgf-umlsd",
    "chemfig": "chemfig",
}

# Packages that MUST NOT be loaded together, with the reason and the winner.
PACKAGE_CONFLICTS = [
    ("subfig", "subcaption", "Both define \\subfloat/\\subcaption machinery", "subcaption"),
    ("natbib", "biblatex", "Two incompatible citation back ends", "biblatex"),
    ("cite", "natbib", "Both patch the citation mechanism", "natbib"),
    ("cite", "biblatex", "Both patch the citation mechanism", "biblatex"),
    ("times", "newtxtext", "Two competing Times font packages", "newtxtext"),
    ("mathptmx", "newtxmath", "Two competing Times math font packages", "newtxmath"),
    ("physics", "siunitx", "Both define \\qty -- a real, well-known clash", "siunitx"),
    ("minted", "listings", "Both may claim the same listing environment names", "minted"),
    ("caption2", "caption", "caption2 is obsolete", "caption"),
    ("epsfig", "graphicx", "epsfig is obsolete", "graphicx"),
    ("psfig", "graphicx", "psfig is obsolete", "graphicx"),
    ("doublespace", "setspace", "doublespace is obsolete", "setspace"),
    ("fancyheadings", "fancyhdr", "fancyheadings is obsolete", "fancyhdr"),
]

# Packages that must be loaded LAST (or nearly last), in this relative order.
# hyperref is famously order-sensitive; cleveref must follow it.
PACKAGE_LOAD_ORDER_TAIL = ["hyperref", "cleveref", "glossaries", "bookmark"]

# Packages that must be loaded EARLY, before anything that reads the font setup.
PACKAGE_LOAD_ORDER_HEAD = [
    "inputenc",
    "fontenc",
    "babel",
    "polyglossia",
    "geometry",
]

# Obsolete or discouraged commands, mapped to the modern replacement.  Used by
# the FIXER (``action=fix``) and reported by the analyzer as style findings.
DEPRECATED_COMMANDS = {
    r"\bf": (r"\textbf{...}", "Old font switch; use \\textbf or \\bfseries"),
    r"\it": (r"\textit{...}", "Old font switch; use \\textit or \\itshape"),
    r"\rm": (r"\textrm{...}", "Old font switch; use \\textrm or \\rmfamily"),
    r"\sf": (r"\textsf{...}", "Old font switch; use \\textsf or \\sffamily"),
    r"\tt": (r"\texttt{...}", "Old font switch; use \\texttt or \\ttfamily"),
    r"\sc": (r"\textsc{...}", "Old font switch; use \\textsc or \\scshape"),
    r"\centerline": (r"\begin{center}", "Use the center environment"),
    r"\over": (r"\frac{a}{b}", "Plain-TeX primitive; use \\frac"),
    r"\atop": (r"\substack", "Plain-TeX primitive; use \\substack or \\binom"),
    r"$$": (r"\[ ... \]", "$$ is plain TeX; use \\[ \\] or the equation env"),
}

DEPRECATED_ENVIRONMENTS = {
    "eqnarray": ("align", "eqnarray has broken spacing; amsmath align is correct"),
    "eqnarray*": ("align*", "eqnarray* has broken spacing; use align*"),
}


def package_for_command(command: str) -> str:
    """Package that provides ``command``, or '' when it is built in/unknown."""
    _build_symbol_indices()
    name = command if command.startswith("\\") else "\\" + command
    return _COMMAND_TO_PACKAGE.get(name.split("{")[0], "")


def scan_required_packages(source: str) -> dict:
    """Work out which packages ``source`` needs but has not loaded.

    Returns ``{"needed": [...], "declared": [...], "missing": [...],
    "triggers": {package: [command, ...]}}`` so a caller can both fix the
    preamble AND explain to the user exactly which command forced each
    package.  This is what makes the auto-preamble trustworthy rather than
    magical.
    """
    _build_symbol_indices()
    text = _strip_comments(source or "")
    declared = set()
    for match in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", text):
        for name in match.group(1).split(","):
            cleaned = name.strip()
            if cleaned:
                declared.add(cleaned)
    triggers = {}
    for match in re.finditer(r"\\([A-Za-z@]+)", text):
        command = "\\" + match.group(1)
        package = _COMMAND_TO_PACKAGE.get(command, "")
        if package:
            triggers.setdefault(package, [])
            if command not in triggers[package]:
                triggers[package].append(command)
    for match in re.finditer(r"\\begin\s*\{([^}*]*\*?)\}", text):
        env = match.group(1).strip()
        package = ENVIRONMENT_TO_PACKAGE.get(env, "")
        if package:
            token = "environment " + env
            triggers.setdefault(package, [])
            if token not in triggers[package]:
                triggers[package].append(token)
    needed = sorted(triggers.keys())
    missing = [p for p in needed if p not in declared]
    return {
        "needed": needed,
        "declared": sorted(declared),
        "missing": missing,
        "triggers": triggers,
    }


def detect_package_conflicts(declared) -> list:
    """Return [(a, b, reason, winner)] for every conflicting pair present."""
    present = set(declared or [])
    found = []
    for left, right, reason, winner in PACKAGE_CONFLICTS:
        if left in present and right in present:
            found.append((left, right, reason, winner))
    return found


def order_packages(packages) -> list:
    """Sort ``packages`` into a load order LaTeX will actually accept.

    Head packages first (encoding/language/geometry), then everything else
    alphabetically, then the order-sensitive tail (hyperref, cleveref, ...).
    Getting this wrong is one of the most common causes of a mystifying
    "Option clash" or a silently broken \\autoref, so the agent never emits an
    arbitrary order.
    """
    remaining = [p for p in dict.fromkeys(packages) if p]
    head = [p for p in PACKAGE_LOAD_ORDER_HEAD if p in remaining]
    tail = [p for p in PACKAGE_LOAD_ORDER_TAIL if p in remaining]
    middle = sorted(p for p in remaining if p not in head and p not in tail)
    return head + middle + tail


def render_package_lines(packages, options=None) -> str:
    """Render ordered ``\\usepackage`` lines, applying known good options."""
    defaults = {
        "inputenc": "utf8",
        "fontenc": "T1",
        "geometry": "margin=2.5cm",
        "hyperref": "colorlinks=true,linkcolor=blue,citecolor=blue,urlcolor=blue",
        "siunitx": "detect-all",
        "caption": "font=small,labelfont=bf",
        "listings": "",
    }
    if options:
        defaults.update(options)
    lines = []
    for package in order_packages(packages):
        opt = defaults.get(package, "")
        if opt:
            lines.append("\\usepackage[%s]{%s}" % (opt, package))
        else:
            lines.append("\\usepackage{%s}" % package)
    return "\n".join(lines)


def tikz_libraries_for(source: str) -> list:
    """Infer the \\usetikzlibrary list a TikZ body needs.

    A missing library is the #1 reason a perfectly good TikZ picture fails to
    build, and the error message ("Unknown key /tikz/...") never names it.
    """
    text = source or ""
    wanted = []
    probes = [
        ("arrows.meta", ("Stealth", "Latex", "->,", "-{", "arrows.meta")),
        ("positioning", ("right=of", "left=of", "above=of", "below=of")),
        ("calc", ("($", "let \\p", "$(")),
        ("shapes.geometric", ("ellipse", "diamond", "trapezium", "regular polygon")),
        ("shapes.misc", ("rounded rectangle", "cross out", "strike out")),
        ("decorations.pathmorphing", ("snake", "coil", "zigzag", "random steps")),
        ("decorations.markings", ("postaction", "decoration={markings")),
        ("decorations.pathreplacing", ("brace",)),
        ("patterns", ("pattern=", "pattern color")),
        ("fit", ("fit=",)),
        ("backgrounds", ("on background layer", "show background rectangle")),
        ("automata", ("state,", "initial]", "accepting", "[state")),
        ("matrix", ("matrix of", "\\matrix")),
        ("trees", ("child", "level distance")),
        ("mindmap", ("mindmap", "concept")),
        ("3d", ("canvas is", "plane origin")),
        ("intersections", ("name path", "name intersections")),
        ("through", ("through=",)),
        ("quotes", ('edge node["',)),
        ("angles", ("angle=", "pic {angle")),
        ("babel", ("\\usepackage{babel}",)),
        ("shadows", ("drop shadow",)),
        ("chains", ("start chain", "on chain")),
        ("petri", ("place,", "transition")),
        ("circuits.ee.IEC", ("circuit ee IEC",)),
    ]
    for library, needles in probes:
        for needle in needles:
            if needle in text:
                wanted.append(library)
                break
    return list(dict.fromkeys(wanted))


def format_symbol_report(rows, title: str = "Symbols") -> str:
    """Human-readable table of universe rows for the agent log."""
    if not rows:
        return "No symbols matched."
    width = max(len(r[0]) for r in rows)
    width = min(max(width, 12), 32)
    lines = [title, "=" * len(title), ""]
    lines.append("%-*s  %-14s  %-12s  %s" % (width, "COMMAND", "PACKAGE", "CATEGORY", "MEANING"))
    lines.append("%-*s  %-14s  %-12s  %s" % (width, "-" * width, "-" * 14, "-" * 12, "-" * 30))
    for command, package, category, description in rows:
        lines.append(
            "%-*s  %-14s  %-12s  %s"
            % (width, command, package or "(built in)", category, description)
        )
    return "\n".join(lines)


def build_cheatsheet_tex(category: str = "", query: str = "", limit: int = 400) -> str:
    """Generate a compilable LaTeX cheat-sheet body rendering each symbol.

    Every row shows the symbol typeset next to its command, so the produced PDF
    is a genuine reference card rather than a code listing.
    """
    rows = search_symbols(query, category, limit)
    grouped = {}
    for row in rows:
        grouped.setdefault(row[2], []).append(row)
    parts = []
    for cat in sorted(grouped.keys()):
        parts.append("\\section*{%s}" % cat.replace("_", " ").title())
        parts.append("\\begin{multicols}{2}")
        parts.append("\\begin{description}[leftmargin=!,labelwidth=3.2cm,itemsep=1pt]")
        for command, package, _cat, description in grouped[cat]:
            sample = command
            if command.startswith("\\begin{"):
                sample = "\\texttt{%s}" % _tex_escape_text(command)
            elif command in (r"\left", r"\right", r"\big", r"\Big", r"\bigg", r"\Bigg"):
                sample = "\\texttt{%s}" % _tex_escape_text(command)
            elif command in (r"\frac", r"\dfrac", r"\tfrac"):
                sample = "$%s{a}{b}$" % command
            elif command == r"\sqrt":
                sample = "$\\sqrt{x}$"
            elif command == r"\binom":
                sample = "$\\binom{n}{k}$"
            elif "{" in command:
                sample = "$%s$" % command
            elif command in (r"\ket", r"\bra"):
                sample = "\\texttt{%s\\{psi\\}}" % _tex_escape_text(command)
            elif re.match(r"^\\[A-Za-z]+$", command):
                sample = "$%s$" % command
            else:
                sample = "\\texttt{%s}" % _tex_escape_text(command)
            note = description
            if package:
                note += " \\textit{(%s)}" % _tex_escape_text(package)
            parts.append(
                "\\item[%s] \\texttt{%s} --- %s"
                % (sample, _tex_escape_text(command), _tex_escape_text(note))
            )
        parts.append("\\end{description}")
        parts.append("\\end{multicols}")
        parts.append("")
    return "\n".join(parts)


def _tex_escape_text(raw: str) -> str:
    """Escape a plain string so it survives being typeset as literal text."""
    out = []
    for char in raw or "":
        if char == "\\":
            out.append("\\textbackslash{}")
        elif char in "&%$#_{}":
            out.append("\\" + char)
        elif char == "~":
            out.append("\\textasciitilde{}")
        elif char == "^":
            out.append("\\textasciicircum{}")
        else:
            out.append(char)
    return "".join(out)


# =============================================================================
# LAYER 05 - THE REPAIR LADDER  ("LaTeXer must never fail")
# =============================================================================
# A LaTeX build has exactly three honest outcomes, and today's agent can only
# produce two of them:
#
#     COMPILED   - a PDF, and LaTeX reported no errors.
#     FAILED     - no PDF, here is the log.            <- unacceptable as a final answer
#     DEGRADED   - a PDF, with named parts removed.    <- did not exist until now
#
# The ladder turns the second into the first wherever a machine possibly can,
# and into the third wherever it cannot.  It NEVER returns silence, and it
# NEVER claims success it did not achieve.
#
# EIGHT RUNGS, tried strictly in order.  A rung only runs when the rung before
# it did not produce a PDF.  The order is the entire design: the first five
# rungs are deterministic and cost milliseconds, so a language model - slow,
# non-reproducible, and capable of inventing plausible nonsense - is the LAST
# thing consulted, not the first.
#
#   1 lint          static structural repair, before any compiler runs
#   2 preamble      infer \usepackage from the commands actually used
#   3 rules         deterministic rewrites of known-bad constructs
#   4 log_directed  compile, read the error, fix THAT line
#   5 acquire       install a genuinely missing package
#   6 engine_swap   retry under xelatex / lualatex
#   7 model         ask an LLM, then re-enter the ladder at rung 1
#   8 bisect        quarantine the bad block and build the rest  <- TRUE last resort
#
# ⚠️ WHY THE MODEL IS RUNG 7 AND BISECT IS RUNG 8 (reordered 2026-08-05).
# The first ordering put bisect at 7 and the model at 8, on the reasoning that
# deterministic beats probabilistic. That was WRONG, because it ranked the
# rungs by only one axis. Bisect is deterministic, yes -- and it is also the
# ONLY rung that DELETES THE AUTHOR'S CONTENT. Reaching it first meant a
# document that a model could have repaired completely was instead shipped with
# a paragraph cut out of it, and the model rung became unreachable in practice
# (bisect almost always "succeeds" at producing something). Losing the user's
# work is the worst outcome available, so the rung that can lose it is now
# strictly last, and the model's answer is still gated by lint + a truncation
# check + it must actually compile. Deterministic-first still holds for rungs
# 1-6; destructiveness breaks the tie at the end.
#
# SAFETY CONTRACT (do NOT weaken any of these):
#   * Every repair is applied to a COPY and re-linted.  A "repair" that makes
#     the static lint worse is REVERTED and recorded as rejected.  A fixer that
#     can damage a document is worse than no fixer.
#   * The user's original file on disk is never overwritten by the ladder
#     unless ``repair_write_back`` is explicitly enabled; the ladder builds
#     from a repaired copy in the work directory.
#   * Every rung that fires is recorded in the trace with what it changed and
#     whether it helped, so the final report can be audited line by line.
#   * A quarantined block is reported by name and line number.  Silently
#     dropping content would make the agent a liar.
# =============================================================================

LADDER_RUNGS = (
    "lint",
    "preamble",
    "rules",
    "log_directed",
    "acquire",
    "engine_swap",
    "model",
    "bisect",
)

# Rungs 6-8 reach outside the process (another engine, a package server, a
# model), so they are opt-out separately from the cheap deterministic ones.
_DEFAULT_ENABLED_RUNGS = LADDER_RUNGS

# Engines tried by rung 6, in order of increasing tolerance.  xelatex and
# lualatex both accept UTF-8 and system fonts natively, which is why a document
# that dies under pdflatex with "Unicode character not set up for use with
# LaTeX" frequently builds unchanged under either of them.
_ENGINE_FALLBACK_ORDER = ("pdflatex", "xelatex", "lualatex")


def _repair_record(rung: str, action: str, detail: str, applied: bool = True) -> dict:
    """One auditable line of the ladder trace."""
    return {"rung": rung, "action": action, "detail": detail, "applied": bool(applied)}


def _lint_score(source: str) -> tuple:
    """Cheap comparable measure of how broken a source is.

    Returns ``(errors, warnings)`` so two candidate sources can be ordered.
    Lower is better; the tuple compares errors first, which is what makes
    "did this repair help?" answerable without a compiler.
    """
    try:
        report = _validate_source(source)
    except Exception:
        # A linter that throws must never take the build with it.
        return (10 ** 6, 10 ** 6)
    return (len(report.get("errors") or []), len(report.get("warnings") or []))


def _accept_if_not_worse(before: str, after: str, rung: str, action: str,
                         detail: str, trace: list) -> str:
    """Apply ``after`` only when it does not lint worse than ``before``.

    This single function is what makes the whole ladder safe to run
    unattended: every transformation below is speculative, and this is the
    gate that stops a speculative transformation from destroying a document.
    """
    if after == before:
        return before
    score_before = _lint_score(before)
    score_after = _lint_score(after)
    if score_after <= score_before:
        trace.append(_repair_record(rung, action, detail, True))
        return after
    trace.append(_repair_record(
        rung, action,
        "%s -- REJECTED: lint got worse (%d->%d errors)" % (
            detail, score_before[0], score_after[0]),
        False))
    return before


# =============================================================================
# RUNG 1 - LINT: structural repair with no compiler involved
# =============================================================================

def _close_unclosed_environments(source: str, trace: list) -> str:
    """Insert the missing ``\\end{...}`` for every environment left open.

    Ordering matters: environments nest, so the missing ends are emitted in
    reverse order of opening.  They are placed immediately before
    ``\\end{document}`` (or at end of file for a fragment), which is the only
    position that cannot break a correctly-nested neighbour.
    """
    clean = _strip_comments(source)
    stack = []
    for match in re.finditer(r"\\(begin|end)\s*\{([^}]+)\}", clean):
        kind, name = match.group(1), match.group(2).strip()
        if name == "document":
            continue
        if kind == "begin":
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
        elif name in stack:
            # Crossed nesting: unwind to it rather than guessing.
            while stack and stack[-1] != name:
                stack.pop()
            if stack:
                stack.pop()
    if not stack:
        return source
    closing = "\n".join("\\end{%s}" % name for name in reversed(stack))
    marker = "\\end{document}"
    index = source.rfind(marker)
    if index >= 0:
        candidate = source[:index] + closing + "\n" + source[index:]
    else:
        candidate = source.rstrip() + "\n" + closing + "\n"
    return _accept_if_not_worse(
        source, candidate, "lint", "close-environments",
        "closed %d unclosed environment(s): %s" % (len(stack), ", ".join(reversed(stack))),
        trace)


def _balance_braces(source: str, trace: list) -> str:
    """Append the missing ``}`` for unclosed groups.

    Deliberately conservative: it only ever ADDS closing braces at the end of
    the body, and only when the imbalance is small.  A large imbalance almost
    always means the real problem is something else (a stray verbatim, a
    mis-parsed catcode), and blindly appending 40 braces would bury it.
    """
    # ⚠️ SCAN THE ORIGINAL SOURCE, NOT A COMMENT-STRIPPED COPY.
    # Positions must index into the text we are going to EDIT. Scanning
    # _strip_comments(source) and then returning that copy silently deletes
    # every '%' comment the author wrote -- data loss dressed up as a repair.
    # Comments are skipped inline instead, so positions stay true.
    open_positions = []
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "%":
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline + 1
            continue
        if char == "{":
            open_positions.append(index)
        elif char == "}":
            if open_positions:
                open_positions.pop()
        index += 1
    depth = len(open_positions)
    if depth <= 0 or depth > 8:
        if depth > 8:
            trace.append(_repair_record(
                "lint", "balance-braces",
                "%d unclosed braces -- too many to repair safely; reporting instead" % depth,
                False))
        return source

    # ⚠️ CLOSE AT THE END OF THE OPENING LINE, not at the end of the document.
    # Dumping every '}' before \end{document} balances the count but not the
    # SEMANTICS: most LaTeX commands are not \long, so a blank line inside the
    # argument gives "Paragraph ended before \textbf was complete" and the
    # document still will not build. Closing on the opening line is both
    # balanced and almost always what the author meant. (Cases 02/03 of the
    # ladder proof used to end up quarantined for exactly this reason.)
    candidate = source
    for position in sorted(open_positions, reverse=True):
        line_end = candidate.find("\n", position)
        if line_end < 0:
            line_end = len(candidate)
        candidate = candidate[:line_end] + "}" + candidate[line_end:]
    return _accept_if_not_worse(
        source, candidate, "lint", "balance-braces",
        "closed %d unclosed group(s) at the end of the line each was opened on" % depth,
        trace)


def _balance_inline_math(source: str, trace: list) -> str:
    """Close an odd number of inline ``$`` delimiters.

    An unbalanced ``$`` is the classic cause of "Missing $ inserted" followed
    by a cascade of nonsense errors hundreds of lines later, so catching it
    statically saves the user from a log that points at the wrong place
    entirely.
    """
    # Scanned over the ORIGINAL source (comments skipped inline, never stripped)
    # so the insertion position is real and the author's '%' comments survive.
    # ``\$`` is covered by the generic escape skip; ``$$`` is stepped over as a
    # pair so display math never upsets inline parity.
    open_at = -1
    inside = False
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "%":
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline + 1
            continue
        if char == "$":
            if source[index:index + 2] == "$$":
                index += 2
                continue
            inside = not inside
            if inside:
                open_at = index
        index += 1
    if not inside or open_at < 0:
        return source

    # Same reasoning as the brace repair: inline math cannot span a blank line
    # ("Missing $ inserted"), so the closing '$' belongs at the end of the line
    # that opened it -- not at the end of the document.
    line_end = source.find("\n", open_at)
    if line_end < 0:
        line_end = len(source)
    candidate = source[:line_end] + "$" + source[line_end:]
    return _accept_if_not_worse(
        source, candidate, "lint", "balance-math",
        "odd number of '$' delimiters -- closed the open inline math at the end of its line",
        trace)


def _repair_static_structure(source: str, trace: list) -> str:
    """RUNG 1 in full: the three structural repairs, cheapest first."""
    working = _close_unclosed_environments(source, trace)
    working = _balance_braces(working, trace)
    working = _balance_inline_math(working, trace)
    return working


# =============================================================================
# RUNG 2 - PREAMBLE: infer the packages the body actually needs
# =============================================================================

def _inject_packages(source: str, packages, trace: list, reason: str = "") -> str:
    """Insert ``\\usepackage`` lines in an order LaTeX will accept.

    Placement rule: immediately after the LAST existing \\usepackage, else
    right after \\documentclass.  Load ORDER then comes from
    ``order_packages`` -- hyperref and cleveref are forced to the tail, which
    is the difference between a working \\autoref and an afternoon lost to a
    baffling "Option clash" or a silently dead cross-reference.
    """
    wanted = [p for p in dict.fromkeys(packages or []) if p]
    if not wanted:
        return source
    tail = [p for p in wanted if p in PACKAGE_LOAD_ORDER_TAIL]
    head = [p for p in wanted if p not in PACKAGE_LOAD_ORDER_TAIL]

    lines = render_package_lines(head) if head else ""
    tail_lines = render_package_lines(tail) if tail else ""

    anchor = None
    for match in re.finditer(r"^[^%\n]*\\usepackage.*$", source, re.MULTILINE):
        anchor = match
    if anchor is None:
        anchor = re.search(r"^[^%\n]*\\documentclass.*$", source, re.MULTILINE)
    if anchor is None:
        return source

    insert_at = anchor.end()
    block = ""
    if lines:
        block += "\n" + lines
    if tail_lines:
        # Tail packages still go after everything else already present, and
        # after the head block we just wrote.
        block += "\n" + tail_lines
    candidate = source[:insert_at] + block + source[insert_at:]
    detail = "added %s" % ", ".join(wanted)
    if reason:
        detail += " (%s)" % reason
    return _accept_if_not_worse(source, candidate, "preamble", "inject-packages", detail, trace)


def _repair_preamble(source: str, trace: list) -> str:
    """RUNG 2: scan the body, add every package it uses but never loaded."""
    if not re.search(r"\\documentclass", _strip_comments(source)):
        return source
    try:
        scan = scan_required_packages(source)
    except Exception as exc:
        trace.append(_repair_record("preamble", "scan", "scan failed: %s" % exc, False))
        return source
    missing = scan.get("missing") or []
    if not missing:
        return source
    triggers = scan.get("triggers") or {}
    reason = "; ".join(
        "%s needed by %s" % (pkg, ", ".join(triggers.get(pkg, [])[:3]))
        for pkg in missing[:4]
    )
    return _inject_packages(source, missing, trace, reason)


def _repair_package_conflicts(source: str, trace: list) -> str:
    """Drop the losing half of a known-incompatible package pair."""
    try:
        scan = scan_required_packages(source)
        conflicts = detect_package_conflicts(scan.get("declared") or [])
    except Exception:
        return source
    working = source
    for left, right, why, winner in conflicts:
        loser = right if winner == left else left
        pattern = re.compile(
            r"^[ \t]*\\usepackage\s*(?:\[[^\]]*\])?\s*\{\s*%s\s*\}[ \t]*\n?" % re.escape(loser),
            re.MULTILINE)
        candidate = pattern.sub("", working)
        working = _accept_if_not_worse(
            working, candidate, "rules", "resolve-conflict",
            "removed \\usepackage{%s}: clashes with %s (%s)" % (loser, winner, why), trace)
    return working


# =============================================================================
# RUNG 3 - RULES: deterministic rewrites of constructs known to be wrong
# =============================================================================

_SMART_CHARACTER_MAP = (
    ("\u201c", "``"),
    ("\u201d", "''"),
    ("\u2018", "`"),
    ("\u2019", "'"),
    ("\u2013", "--"),
    ("\u2014", "---"),
    ("\u2026", "\\ldots{}"),
    ("\u00a0", "~"),
    ("\u2212", "-"),
    ("\u00d7", "\\times{}"),
    ("\u2264", "\\leq{}"),
    ("\u2265", "\\geq{}"),
    ("\u2260", "\\neq{}"),
)


def _repair_smart_characters(source: str, trace: list) -> str:
    """Replace word-processor characters pdflatex cannot encode.

    Only meaningful for pdflatex with inputenc; xelatex and lualatex accept
    these natively.  Doing it unconditionally is still correct -- the ASCII
    forms typeset identically -- and it removes an entire class of
    "Unicode character not set up" failures before they happen.
    """
    working = source
    replaced = []
    for glyph, ascii_form in _SMART_CHARACTER_MAP:
        if glyph in working:
            count = working.count(glyph)
            working = working.replace(glyph, ascii_form)
            replaced.append("%s x%d" % (repr(glyph), count))
    if not replaced:
        return source
    return _accept_if_not_worse(
        source, working, "rules", "ascii-fold",
        "replaced non-ASCII typographic characters: " + ", ".join(replaced[:6]), trace)


def _repair_deprecated_environments(source: str, trace: list) -> str:
    """``eqnarray`` -> ``align``: not cosmetic, it fixes real spacing bugs."""
    working = source
    for old, (new, why) in DEPRECATED_ENVIRONMENTS.items():
        if ("\\begin{%s}" % old) not in working:
            continue
        candidate = working.replace("\\begin{%s}" % old, "\\begin{%s}" % new)
        candidate = candidate.replace("\\end{%s}" % old, "\\end{%s}" % new)
        working = _accept_if_not_worse(
            working, candidate, "rules", "modernise-environment",
            "%s -> %s (%s)" % (old, new, why), trace)
    if working is not source and "\\begin{align" in working:
        working = _inject_packages(working, ["amsmath"], trace, "align requires amsmath")
    return working


def _repair_deprecated_font_switches(source: str, trace: list) -> str:
    """``{\\bf x}`` -> ``{\\bfseries x}``.

    The declaration form is used rather than ``\\textbf{x}`` because it is a
    purely local substitution that cannot mis-scope: turning a switch into a
    command would require finding the end of its group, and getting that wrong
    silently re-bolds half a page.
    """
    working = source
    changed = []
    switches = {"bf": "bfseries", "it": "itshape", "rm": "rmfamily",
                "sf": "sffamily", "tt": "ttfamily", "sc": "scshape"}
    for old, new in switches.items():
        pattern = re.compile(r"\\%s(?![A-Za-z])" % old)
        if not pattern.search(working):
            continue
        working = pattern.sub("\\\\" + new, working)
        changed.append("\\%s -> \\%s" % (old, new))
    if not changed:
        return source
    return _accept_if_not_worse(
        source, working, "rules", "modernise-fonts",
        "; ".join(changed), trace)


def _repair_display_math(source: str, trace: list) -> str:
    """``$$ ... $$`` -> ``\\[ ... \\]``.

    ``$$`` is plain TeX; under LaTeX it produces wrong vertical spacing and
    breaks with amsmath's ``fleqn``.  Pairs are replaced strictly two at a
    time so an odd count can never corrupt the document.
    """
    if "$$" not in source:
        return source
    parts = source.split("$$")
    if len(parts) % 2 == 0:
        trace.append(_repair_record(
            "rules", "display-math",
            "odd number of '$$' delimiters -- left untouched (unsafe to pair)", False))
        return source
    rebuilt = []
    for index, chunk in enumerate(parts):
        rebuilt.append(chunk)
        if index < len(parts) - 1:
            rebuilt.append("\\[" if index % 2 == 0 else "\\]")
    candidate = "".join(rebuilt)
    return _accept_if_not_worse(
        source, candidate, "rules", "display-math",
        "converted %d plain-TeX $$...$$ block(s) to \\[...\\]" % ((len(parts) - 1) // 2), trace)


def _repair_duplicate_labels(source: str, trace: list) -> str:
    """Rename duplicate ``\\label`` keys and re-point their references.

    Duplicates make every \\ref to that key resolve to whichever came last,
    silently producing a document whose cross-references are wrong but which
    compiles perfectly.  That is worse than a build failure, so it is fixed
    rather than merely reported.
    """
    labels = re.findall(r"\\label\s*\{([^}]+)\}", _strip_comments(source))
    seen, duplicates = set(), []
    for label in labels:
        if label in seen and label not in duplicates:
            duplicates.append(label)
        seen.add(label)
    if not duplicates:
        return source
    working = source
    for label in duplicates:
        occurrence = {"n": 0}

        def _rename(match, _label=label, _state=occurrence):
            _state["n"] += 1
            if _state["n"] == 1:
                return match.group(0)
            return "\\label{%s-dup%d}" % (_label, _state["n"])

        working = re.sub(r"\\label\s*\{%s\}" % re.escape(label), _rename, working)
    return _accept_if_not_worse(
        source, working, "rules", "dedupe-labels",
        "renamed duplicate label(s): " + ", ".join(duplicates[:5]), trace)


def _repair_rules(source: str, trace: list) -> str:
    """RUNG 3 in full."""
    working = _repair_smart_characters(source, trace)
    working = _repair_deprecated_environments(working, trace)
    working = _repair_deprecated_font_switches(working, trace)
    working = _repair_display_math(working, trace)
    working = _repair_duplicate_labels(working, trace)
    working = _repair_package_conflicts(working, trace)
    return working


# =============================================================================
# RUNG 4 - LOG-DIRECTED: read the actual error, fix that exact thing
# =============================================================================

_UNDEFINED_CS = re.compile(r"Undefined control sequence.*?\\([A-Za-z@]+)", re.DOTALL)
_UNDEFINED_ENV = re.compile(r"Environment\s+([A-Za-z@*]+)\s+undefined")
_OPTION_CLASH = re.compile(r"Option clash for package\s+([A-Za-z0-9@\-]+)")


def _commands_from_diagnostics(diag: dict) -> list:
    """Every undefined control sequence LaTeX complained about."""
    found = []
    for message in (diag.get("errors") or []):
        for match in _UNDEFINED_CS.finditer(message):
            name = "\\" + match.group(1)
            if name not in found:
                found.append(name)
    return found


def _environments_from_diagnostics(diag: dict) -> list:
    found = []
    for message in (diag.get("errors") or []):
        for match in _UNDEFINED_ENV.finditer(message):
            name = match.group(1)
            if name not in found:
                found.append(name)
    return found


def _repair_from_log(source: str, diag: dict, trace: list) -> str:
    """RUNG 4: turn each diagnostic into a targeted, justified edit.

    This is where the symbol universe pays for itself: "Undefined control
    sequence \\qty" is not a guess, it is a LOOKUP that answers "siunitx".
    """
    working = source
    wanted = []
    explained = []

    for command in _commands_from_diagnostics(diag):
        package = package_for_command(command)
        if package:
            wanted.append(package)
            explained.append("%s -> %s" % (command, package))
        else:
            trace.append(_repair_record(
                "log_directed", "unknown-command",
                "%s is undefined and is not in the symbol universe -- cannot infer a "
                "package for it" % command, False))

    for environment in _environments_from_diagnostics(diag):
        package = ENVIRONMENT_TO_PACKAGE.get(environment, "")
        if package:
            wanted.append(package)
            explained.append("environment %s -> %s" % (environment, package))

    if wanted:
        working = _inject_packages(working, wanted, trace, "; ".join(explained[:5]))

    for message in (diag.get("errors") or []):
        clash = _OPTION_CLASH.search(message)
        if not clash:
            continue
        package = clash.group(1)
        # Keep the FIRST load (it usually carries the options the document
        # actually wants) and drop the later bare one.
        pattern = re.compile(
            r"(\\usepackage\s*(?:\[[^\]]*\])?\s*\{\s*%s\s*\}[ \t]*\n?)" % re.escape(package))
        occurrences = pattern.findall(working)
        if len(occurrences) > 1:
            first = pattern.search(working)
            head = working[:first.end()]
            tail = pattern.sub("", working[first.end():])
            working = _accept_if_not_worse(
                working, head + tail, "log_directed", "resolve-option-clash",
                "package %s was loaded %d times -- kept the first" % (package, len(occurrences)),
                trace)

    return working


# =============================================================================
# RUNG 5 - ACQUIRE: install a package that is genuinely absent
# =============================================================================

def _acquire_packages(missing, tools: dict, config: dict, env: dict, trace: list) -> bool:
    """Ask the distribution to install the missing ``.sty`` files.

    MiKTeX normally does this itself mid-compile via --enable-installer, so
    reaching this rung means either that was disabled or the automatic attempt
    failed.  Returns True when at least one install reported success, which is
    the signal to retry the build.
    """
    # Keep BOTH forms: the manager installs a PACKAGE id, but the only thing
    # that proves the repair worked is whether the FILE now resolves.
    targets = []
    for item in missing or []:
        filename = os.path.basename(str(item)).strip()
        package = filename
        for suffix in (".sty", ".cls", ".def"):
            if package.lower().endswith(suffix):
                package = package[: -len(suffix)]
                break
        if package and (package, filename) not in targets:
            targets.append((package, filename))
    if not targets:
        return False

    distribution = tools.get("distribution", "")
    timeout = float(_as_int(_cfg(config, "command_timeout", 600), 600))
    verified_any = False
    attempted = False

    for package, filename in targets[:8]:
        argv = []
        if distribution == "miktex":
            miktex = _which("miktex", env) or _which("mpm", env)
            if miktex and miktex.lower().endswith("mpm.exe"):
                argv = [miktex, "--install=%s" % package]
            elif miktex:
                argv = [miktex, "packages", "install", package]
        elif distribution in ("texlive", "mactex"):
            tlmgr = _which("tlmgr", env)
            if tlmgr:
                argv = [tlmgr, "install", package]
        if not argv:
            trace.append(_repair_record(
                "acquire", "install",
                "no package manager available for distribution '%s' -- cannot install %s"
                % (distribution or "unknown", package), False))
            continue

        attempted = True
        code, out, err = _run_cmd(argv, env=env, timeout=timeout)

        # ⚠️ A ZERO EXIT CODE IS NOT PROOF, and reporting it as one is a LIE.
        # Live proof, 2026-08-05: `miktex packages install crossword` returned
        # rc=0 and the ladder announced "installed crossword" -- but the
        # crossword package ships no crossword.sty, so the build still failed
        # with the very same missing-file error. The only honest test is
        # whether the FILE resolves now, so kpsewhich is asked directly.
        _refresh_filename_database(distribution, env, timeout)
        resolved = _file_resolves(filename, env, timeout)
        verified_any = verified_any or resolved

        if resolved:
            detail = "installed %s and VERIFIED %s now resolves" % (package, filename)
        elif code == 0:
            detail = ("package manager reported success for %s (rc=0) but %s STILL does not "
                      "resolve -- that package does not provide this file, so the build "
                      "will fail for the same reason" % (package, filename))
        else:
            detail = "FAILED to install %s (rc=%s): %s" % (
                package, code, (err or out or "").strip()[:160] or "no output")
        trace.append(_repair_record("acquire", "install", detail, resolved))

    if attempted and not verified_any:
        trace.append(_repair_record(
            "acquire", "verify",
            "no missing file was actually resolved -- escalating rather than retrying "
            "a build that would fail identically", False))
    return verified_any


def _refresh_filename_database(distribution: str, env: dict, timeout: float) -> None:
    """Rebuild the distribution's file-name database after an install.

    kpsewhich (and the engine) answer from a cached index, so a freshly
    installed .sty can remain invisible until the index is rebuilt. Best
    effort only -- never allowed to raise into the ladder.
    """
    try:
        if distribution == "miktex":
            miktex = _which("miktex", env)
            if miktex:
                _run_cmd([miktex, "fndb", "refresh"], env=env, timeout=min(timeout, 180.0))
        elif distribution in ("texlive", "mactex"):
            mktexlsr = _which("mktexlsr", env)
            if mktexlsr:
                _run_cmd([mktexlsr], env=env, timeout=min(timeout, 180.0))
    except Exception:
        return


def _file_resolves(filename: str, env: dict, timeout: float) -> bool:
    """True when TeX can actually find ``filename`` right now."""
    kpsewhich = _which("kpsewhich", env)
    if not kpsewhich:
        # Cannot verify -> must NOT claim success. Fail closed here, because the
        # whole point of this check is to stop an unverified claim.
        return False
    try:
        code, out, _err = _run_cmd([kpsewhich, filename], env=env, timeout=min(timeout, 120.0))
    except Exception:
        return False
    return code == 0 and bool((out or "").strip())


# =============================================================================
# RUNG 6 - ENGINE SWAP
# =============================================================================

def _next_engine(current: str, tried, env: dict) -> str:
    """Next resolvable engine after ``current`` that has not been tried."""
    for candidate in _ENGINE_FALLBACK_ORDER:
        if candidate == current or candidate in (tried or ()):
            continue
        if _which(candidate, env):
            return candidate
    return ""


def _toolchain_for_engine(engine: str, config: dict, env: dict) -> dict:
    """Re-resolve the toolchain pinned to ``engine``.

    ``latex_executable`` is cleared deliberately: an explicit path is by
    definition a path to the CURRENT engine, and honouring it here would make
    the swap a no-op that silently reruns the same failing binary.
    """
    swapped = dict(config)
    swapped["engine"] = engine
    swapped["latex_executable"] = ""
    return _resolve_toolchain(swapped, env)


# =============================================================================
# RUNG 8 - BISECT: isolate the offending block and build everything else.
#                  THE TRUE LAST RESORT -- the only rung that deletes the
#                  author's content, which is why it runs after `model`.
# =============================================================================

def _split_body_blocks(source: str) -> tuple:
    """Split a document into (head, blocks, tail) at blank-line boundaries.

    Blocks are only ever cut at TOP-LEVEL blank lines -- never inside an
    environment -- so quarantining one can never orphan a \\begin from its
    \\end.  That invariant is what makes bisection safe on real documents.
    """
    begin = re.search(r"\\begin\s*\{document\}", source)
    end = source.rfind("\\end{document}")
    if not begin or end < 0 or end <= begin.end():
        return ("", [], "")
    head = source[: begin.end()]
    body = source[begin.end(): end]
    tail = source[end:]

    blocks = []
    current = []
    depth = 0
    for line in body.splitlines(True):
        probe = _strip_comments(line)
        depth += len(re.findall(r"\\begin\s*\{", probe))
        depth -= len(re.findall(r"\\end\s*\{", probe))
        depth = max(0, depth)
        if line.strip() == "" and depth == 0 and current:
            blocks.append("".join(current))
            current = []
        else:
            current.append(line)
    if current:
        blocks.append("".join(current))
    return (head, blocks, tail)


def _assemble(head: str, blocks, tail: str, keep) -> str:
    """Rebuild a PROBE document from the blocks whose indices are in ``keep``.

    ⚠️ The ``\\mbox{}`` is load-bearing, not decoration. A document with an empty
    body makes LaTeX report "No pages of output" and emit NO PDF -- which the
    probe would read as "this combination fails", so the very first probe (the
    preamble alone, with zero blocks) always failed and bisection aborted with
    "the fault is above \\begin{document}" on documents whose preamble was
    perfectly fine. The placeholder guarantees every probe produces at least
    one page, so a probe failure means what it is supposed to mean: the BLOCKS
    are at fault. Only probes are assembled here; the delivered document is
    built separately and never contains this box.
    """
    parts = [head, "\\mbox{}\n"]
    for index, block in enumerate(blocks):
        if index in keep:
            parts.append(block)
            parts.append("\n\n")
    parts.append(tail)
    return "".join(parts)


def _quarantine_note(block: str, index: int) -> str:
    """A VISIBLE placeholder for a removed block.

    The removal is printed into the PDF itself, not merely into the log.  A
    reader must never receive a document that is quietly missing a paragraph.
    """
    preview = " ".join(_strip_comments(block).split())[:110]
    return (
        "\n\\par\\medskip\\noindent\\fbox{\\begin{minipage}{0.95\\linewidth}\n"
        "\\textbf{[LaTeXer: block %d could not be typeset and was quarantined]}\\\\\n"
        "\\texttt{\\footnotesize %s}\n"
        "\\end{minipage}}\\par\\medskip\n" % (index + 1, _tex_escape_text(preview))
    )


def _bisect_failing_blocks(source: str, tex_path: str, config: dict, tools: dict,
                           env: dict, trace: list) -> dict:
    """RUNG 7: binary-search for the blocks that break the build.

    Strategy: confirm the head alone compiles (if it does not, the fault is in
    the preamble and bisection cannot help), then bisect the block list.  Each
    probe is a real compile, so the cost is O(log n) builds rather than O(n).
    """
    head, blocks, tail = _split_body_blocks(source)
    if not blocks or len(blocks) < 2:
        trace.append(_repair_record(
            "bisect", "split",
            "document has %d top-level block(s) -- nothing to bisect" % len(blocks), False))
        return {"ok": False, "source": source, "quarantined": []}

    probe_dir = os.path.dirname(os.path.abspath(tex_path))
    probe_name = "_latexer_bisect_" + os.path.basename(tex_path)
    probe_path = os.path.join(probe_dir, probe_name)
    probe_budget = max(4, min(_as_int(_cfg(config, "repair_bisect_max_probes", 14), 14), 40))
    probes = {"n": 0}

    def _probe(keep) -> bool:
        if probes["n"] >= probe_budget:
            return False
        probes["n"] += 1
        candidate = _assemble(head, blocks, tail, keep)
        try:
            with open(probe_path, "w", encoding="utf-8") as handle:
                handle.write(candidate)
        except Exception:
            return False
        outcome = _compile(probe_path, config, tools, env)
        return bool(outcome.get("produced")) and not outcome.get("diag", {}).get("errors")

    if not _probe(set()):
        trace.append(_repair_record(
            "bisect", "preamble-probe",
            "the preamble alone does not compile -- the fault is above \\begin{document}, "
            "so bisecting the body cannot help", False))
        _safe_remove(probe_path)
        return {"ok": False, "source": source, "quarantined": []}

    good = set()
    bad = []
    for index in range(len(blocks)):
        # Greedy forward scan: keep everything known-good plus this block.
        # Simpler than a strict bisection and, crucially, it finds EVERY bad
        # block rather than only the first one.
        if _probe(good | {index}):
            good.add(index)
        else:
            bad.append(index)
        if probes["n"] >= probe_budget:
            # Out of budget: assume the rest are fine rather than discarding
            # content we have not actually tested.
            for rest in range(index + 1, len(blocks)):
                good.add(rest)
            trace.append(_repair_record(
                "bisect", "budget",
                "probe budget (%d) exhausted -- remaining %d block(s) kept untested"
                % (probe_budget, len(blocks) - index - 1), False))
            break

    _safe_remove(probe_path)
    if not bad:
        trace.append(_repair_record(
            "bisect", "search", "no single block reproduces the failure", False))
        return {"ok": False, "source": source, "quarantined": []}

    parts = [head]
    for index, block in enumerate(blocks):
        if index in bad:
            parts.append(_quarantine_note(block, index))
        else:
            parts.append(block)
            parts.append("\n\n")
    parts.append(tail)
    repaired = "".join(parts)
    trace.append(_repair_record(
        "bisect", "quarantine",
        "quarantined %d of %d block(s) after %d probe(s): block(s) %s"
        % (len(bad), len(blocks), probes["n"], ", ".join(str(i + 1) for i in bad)), True))
    return {"ok": True, "source": repaired, "quarantined": [i + 1 for i in bad]}


def _safe_remove(path: str) -> None:
    """Delete a scratch file and its aux siblings; never raise."""
    base = os.path.splitext(path)[0]
    for suffix in ("", ".aux", ".log", ".out", ".pdf", ".toc", ".fls", ".fdb_latexmk"):
        try:
            target = path if suffix == "" else base + suffix
            if os.path.isfile(target):
                os.remove(target)
        except Exception:
            continue


# =============================================================================
# RUNG 7 - MODEL: the last NON-DESTRUCTIVE resort, held to the same standard
#                 as everything else.  (Defined after bisect in this file only
#                 for layout; LADDER_RUNGS is the authoritative order and runs
#                 model BEFORE bisect -- see the 2026-08-05 reorder note.)
# =============================================================================

def _ollama_repair(source: str, diag: dict, config: dict, trace: list) -> str:
    """Ask an Ollama model to repair the source. Stdlib only, fails open.

    Three rules make this safe to have at all:
      * it is the last NON-DESTRUCTIVE rung, so it only ever sees documents the
        six deterministic rungs before it could not fix (only `bisect`, which
        deletes content, comes after it);
      * its answer re-enters the ladder at rung 1 and must pass the same lint
        gate as any other repair;
      * a reply that is not a complete document, or that is wildly shorter than
        the input, is discarded -- truncation is the characteristic failure of
        an LLM asked to echo a long document, and silently accepting it would
        delete the user's work.
    """
    url = str(_cfg(config, "ollama_url", "http://localhost:11434")).strip().rstrip("/")
    model = str(_cfg(config, "repair_model", "")).strip()
    if not model:
        trace.append(_repair_record(
            "model", "skip", "no repair_model configured -- model rung disabled", False))
        return source

    errors = "\n".join((diag.get("errors") or [])[:12]) or "(no explicit LaTeX error)"
    prompt = (
        "You are repairing a LaTeX document that fails to compile.\n"
        "Return ONLY the corrected, COMPLETE LaTeX document. No commentary, no "
        "markdown fences. Preserve every sentence of the author's content exactly; "
        "change only what is required to make it compile.\n\n"
        "COMPILER ERRORS:\n%s\n\nDOCUMENT:\n%s\n" % (errors, source)
    )
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode("utf-8")

    try:
        request = urllib.request.Request(
            url + "/api/generate", data=payload,
            headers={"Content-Type": "application/json"})
        token = str(_cfg(config, "ollama_token", "")).strip()
        if token:
            request.add_header("Authorization", "Bearer " + token)
        timeout = float(_as_int(_cfg(config, "repair_model_timeout", 180), 180))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
        answer = str(body.get("response") or "")
    except Exception as exc:
        trace.append(_repair_record(
            "model", "request", "Ollama call failed: %s" % exc, False))
        return source

    answer = re.sub(r"^\s*```(?:latex|tex)?\s*", "", answer)
    answer = re.sub(r"```\s*$", "", answer).strip()
    if "\\documentclass" not in answer or "\\end{document}" not in answer:
        trace.append(_repair_record(
            "model", "validate",
            "model reply is not a complete document -- discarded", False))
        return source
    if len(answer) < len(source) * 0.6:
        trace.append(_repair_record(
            "model", "validate",
            "model reply is %d chars vs %d original -- looks truncated, discarded"
            % (len(answer), len(source)), False))
        return source
    return _accept_if_not_worse(
        source, answer, "model", "llm-repair",
        "model '%s' rewrote the document (%d -> %d chars)" % (model, len(source), len(answer)),
        trace)


# =============================================================================
# THE LADDER ITSELF
# =============================================================================

def _enabled_rungs(config: dict) -> tuple:
    """Which rungs are active, honouring config and keeping ladder order."""
    raw = _as_list(_cfg(config, "repair_rungs", []))
    if not raw:
        return tuple(_DEFAULT_ENABLED_RUNGS)
    wanted = {str(item).strip().lower() for item in raw if str(item).strip()}
    if "all" in wanted:
        return tuple(LADDER_RUNGS)
    return tuple(rung for rung in LADDER_RUNGS if rung in wanted)


def _write_working_copy(tex_path: str, source: str, config: dict) -> str:
    """Persist the repaired source for the build.

    By default the ladder builds from a sibling ``*.latexer-fixed.tex`` and
    leaves the author's file untouched, because an agent that silently
    rewrites source files is an agent nobody can trust.  Set
    ``repair_write_back: true`` to edit in place.
    """
    if _as_bool(_cfg(config, "repair_write_back", False), False):
        target = tex_path
    else:
        base, ext = os.path.splitext(tex_path)
        target = base + ".latexer-fixed" + (ext or ".tex")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(source)
    return target


def _compile_with_ladder(tex_path: str, config: dict, tools: dict, env: dict) -> dict:
    """Build ``tex_path``, escalating through the repair ladder until it works.

    Returns the usual ``_compile`` result dict, enriched with:
        ``ladder``       - the full audit trace, rung by rung
        ``rungs_used``   - which rungs actually fired
        ``degraded``     - True when a PDF exists only because content was cut
        ``quarantined``  - the block numbers that were removed
        ``build_path``   - the file the successful build actually used
        ``engine_used``  - the engine that finally produced the PDF
    """
    trace = []
    rungs = _enabled_rungs(config)
    active_tools = tools
    engines_tried = [tools.get("engine", "pdflatex")]
    quarantined = []

    try:
        source = _read_text(tex_path)
    except Exception as exc:
        return {"ok": False, "produced": False, "passes": 0, "pdf": "", "steps": [],
                "diag": _parse_latex_log(""), "log": "", "returncode": 1,
                "ladder": [_repair_record("lint", "read", "cannot read %s: %s" % (tex_path, exc), False)],
                "rungs_used": [], "degraded": False, "quarantined": [],
                "build_path": tex_path, "engine_used": tools.get("engine", "")}

    original = source
    build_path = tex_path

    # ---- Rungs 1-3 run BEFORE the first compile: they are static and cheap,
    # and fixing a brace here saves a 3000-line log that points somewhere else.
    if "lint" in rungs:
        source = _repair_static_structure(source, trace)
    if "preamble" in rungs:
        source = _repair_preamble(source, trace)
    if "rules" in rungs:
        source = _repair_rules(source, trace)

    if source != original:
        build_path = _write_working_copy(tex_path, source, config)
        logging.info("🔧 Repair ladder applied %d pre-compile fix(es); building %s",
                     len([r for r in trace if r["applied"]]), os.path.basename(build_path))

    result = _compile(build_path, config, active_tools, env)
    if result.get("ok"):
        return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                active_tools, degraded=False)

    # ---- Rung 4: read the real error and fix exactly that.
    if "log_directed" in rungs:
        repaired = _repair_from_log(source, result.get("diag") or {}, trace)
        if repaired != source:
            source = repaired
            build_path = _write_working_copy(tex_path, source, config)
            result = _compile(build_path, config, active_tools, env)
            if result.get("ok"):
                return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                        active_tools, degraded=False)

    # ---- Rung 5: a package really is absent -- acquire it and retry.
    if "acquire" in rungs:
        missing = (result.get("diag") or {}).get("missing_packages") or []
        if missing:
            # 5a. THE RELIABLE PATH FIRST. MiKTeX maintains the authoritative
            # file -> package map (xy.sty lives in "xypic", tikz.sty in "pgf" --
            # the stem is NOT the package id), and --enable-installer makes it
            # resolve and fetch mid-compile. Guessing package names from file
            # names, as 5b must, gets those wrong. So when the user has turned
            # the auto-installer off, rung 5 turns it on for ONE retry and says
            # so, rather than guessing.
            installer_on = _as_bool(_cfg(config, "auto_install_packages", True), True)
            if not installer_on and active_tools.get("distribution") == "miktex":
                trace.append(_repair_record(
                    "acquire", "enable-installer",
                    "missing %s -- re-running once with MiKTeX's on-demand installer "
                    "enabled, which knows which package provides each file"
                    % ", ".join(missing[:3]), True))
                forced = dict(config)
                forced["auto_install_packages"] = True
                result = _compile(build_path, forced, active_tools, env)
                if result.get("ok"):
                    return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                            active_tools, degraded=False)
                missing = (result.get("diag") or {}).get("missing_packages") or missing

            # 5b. Fall back to an explicit, VERIFIED package-manager install.
            if missing and _acquire_packages(missing, active_tools, config, env, trace):
                result = _compile(build_path, config, active_tools, env)
                if result.get("ok"):
                    return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                            active_tools, degraded=False)

    # ---- Rung 6: try a more tolerant engine.
    if "engine_swap" in rungs:
        while True:
            candidate = _next_engine(active_tools.get("engine", ""), engines_tried, env)
            if not candidate:
                break
            engines_tried.append(candidate)
            trace.append(_repair_record(
                "engine_swap", "retry",
                "retrying under %s (previous engine: %s)" % (candidate, active_tools.get("engine")),
                True))
            swapped = _toolchain_for_engine(candidate, config, env)
            if not swapped.get("latex"):
                continue
            active_tools = swapped
            result = _compile(build_path, config, active_tools, env)
            if result.get("ok"):
                return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                        active_tools, degraded=False)

    # ---- Rung 7: the model. Deliberately BEFORE bisect, because it can repair
    # the document without deleting any of it. Its answer is not trusted: it
    # re-enters the static gate (rungs 1-2) and must actually compile.
    if "model" in rungs:
        rewritten = _ollama_repair(source, result.get("diag") or {}, config, trace)
        if rewritten != source:
            model_source = _repair_static_structure(rewritten, trace)
            model_source = _repair_preamble(model_source, trace)
            model_path = _write_working_copy(tex_path, model_source, config)
            model_result = _compile(model_path, config, active_tools, env)
            if model_result.get("ok"):
                return _finalise_ladder(model_result, trace, rungs, quarantined,
                                        model_path, active_tools, degraded=False)
            # ⚠️ The rewrite is DISCARDED when it does not build. Carrying it
            # forward would mean bisecting the MODEL'S GUESS and quarantining
            # blocks out of a document the author never wrote -- content loss
            # caused by a hallucination. Bisect continues from the real source.
            trace.append(_repair_record(
                "model", "verify",
                "the model's rewrite still does not compile -- discarded, continuing "
                "from the author's own source", False))
            _safe_remove(model_path)

    # ---- Rung 8: TRUE LAST RESORT. Cut out what cannot be typeset, keep the rest.
    #
    # ⚠️ NEVER destroy the author's content because the INFRASTRUCTURE hiccuped
    # (Angela, 2026-08-11). Rung 7 (model) is the last NON-destructive repair.
    # When its call merely TIMED OUT or the endpoint was unreachable, the ladder
    # has not actually exhausted its safe options - and cutting a block then
    # means the author loses a paragraph over a network blip. That is exactly
    # what happened to Angela's OpenMP guide: `model` timed out, `bisect`
    # quarantined block 10, and a 27-page CLEAN pdf became a 26-page DEGRADED
    # one. Losing the user's work is the worst outcome available, so we refuse
    # to cut and report honestly instead.
    if "bisect" in rungs and _model_rung_never_answered(trace):
        trace.append(_repair_record(
            "bisect", "skipped",
            "NOT cutting any content: the model rung could not be reached "
            "(timeout / unreachable), so the non-destructive repairs were never "
            "really exhausted. Fix the model connection (or raise "
            "repair_model_timeout) and re-run; the document is left intact.",
            False))
    elif "bisect" in rungs:
        outcome = _bisect_failing_blocks(source, build_path, config, active_tools, env, trace)
        if outcome.get("ok"):
            source = outcome["source"]
            quarantined = outcome.get("quarantined") or []
            build_path = _write_working_copy(tex_path, source, config)
            result = _compile(build_path, config, active_tools, env)
            if result.get("produced"):
                return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                                        active_tools, degraded=True)

    # Everything was tried.  Report honestly -- including a PDF that exists but
    # carries errors, which is still more useful to the user than nothing.
    return _finalise_ladder(result, trace, rungs, quarantined, build_path,
                            active_tools, degraded=bool(quarantined))


_MODEL_UNREACHABLE_MARKERS = (
    "timed out", "timeout", "unreachable", "connection", "refused",
    "call failed", "not configured", "no response",
)


def _model_rung_never_answered(trace) -> bool:
    """True when rung 7 got NO answer from the model at all.

    Distinguishes "the model looked at it and could not help" (a real, exhausted
    repair - bisect may proceed) from "we never reached the model" (an
    infrastructure failure - bisect must NOT destroy content over it).
    FAIL-SAFE: on any doubt it returns True, i.e. it protects the document.
    """
    try:
        for record in reversed(trace or []):
            if (record or {}).get("rung") != "model":
                continue
            detail = str((record or {}).get("detail") or "").lower()
            return any(marker in detail for marker in _MODEL_UNREACHABLE_MARKERS)
        return False          # rung 7 disabled / never ran -> normal behaviour
    except Exception:
        return True           # protect the author's text when unsure


def _finalise_ladder(result: dict, trace: list, rungs, quarantined, build_path: str,
                     tools: dict, degraded: bool) -> dict:
    """Attach the audit trail to a compile result."""
    enriched = dict(result)
    enriched["ladder"] = trace
    enriched["rungs_used"] = sorted({record["rung"] for record in trace if record["applied"]},
                                    key=lambda name: LADDER_RUNGS.index(name))
    enriched["rungs_enabled"] = list(rungs)
    enriched["quarantined"] = list(quarantined or [])
    enriched["degraded"] = bool(degraded or quarantined)
    enriched["build_path"] = build_path
    enriched["engine_used"] = tools.get("engine", "")
    if enriched["degraded"]:
        # A degraded build is NOT a success and must never be reported as one.
        enriched["ok"] = False
    return enriched


def _format_ladder_report(result: dict) -> str:
    """Human-readable account of everything the ladder did.

    Printed even on total success (as a single line), because "nothing needed
    repairing" is itself information the user wants.
    """
    trace = result.get("ladder") or []
    if not trace:
        return "Repair ladder: not needed -- the document compiled as written."

    lines = ["REPAIR LADDER", "=" * 13, ""]
    applied = [record for record in trace if record["applied"]]
    rejected = [record for record in trace if not record["applied"]]

    current = None
    for record in trace:
        if record["rung"] != current:
            current = record["rung"]
            lines.append("")
            lines.append("  [%d] %s" % (LADDER_RUNGS.index(current) + 1, current.upper()))
        mark = "+" if record["applied"] else "-"
        lines.append("      %s %s: %s" % (mark, record["action"], record["detail"]))

    lines.append("")
    lines.append("  %d repair(s) applied, %d rejected or skipped."
                 % (len(applied), len(rejected)))
    if result.get("quarantined"):
        lines.append("")
        lines.append("  DEGRADED BUILD -- block(s) %s could not be typeset and were "
                     "REMOVED from the PDF." % ", ".join(str(n) for n in result["quarantined"]))
        lines.append("  Each removal is marked visibly in the document itself.")
    if result.get("engine_used"):
        lines.append("  Final engine: %s" % result["engine_used"])
    if result.get("build_path"):
        lines.append("  Built from: %s" % result["build_path"])
    return "\n".join(lines)


_B64_FIELDS = ("input_text", "content", "find_text", "replace_text")


def _decode_b64_fields(config: dict) -> None:
    """Decode the parser-immune ``<field>_b64`` channels IN PLACE.

    LaTeX is backslash soup and every table row / line break is ``\\``. The chat
    request parser is tuned for shell/SQL payloads, so it collapsed ``\\`` to a
    single ``\`` and glued the trailing ``', filename='...'`` into the body —
    a document that could never compile, and the reason Angela's OpenMP report
    produced no .tex and no PDF at all (2026-08-10). base64 has no backslash,
    quote, comma or newline in its alphabet, so a ``*_b64`` value reaches this
    agent EXACTLY as the caller built it.

    FAIL-OPEN: a malformed or absent b64 value leaves the plain field untouched
    and is only logged — decoding must never stop a compile.
    """
    if not isinstance(config, dict):
        return
    for field_name in _B64_FIELDS:
        raw = config.get("%s_b64" % field_name)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            decoded = base64.b64decode(raw.strip()).decode("utf-8")
        except Exception as exc:
            logging.warning(
                "%s_b64 could not be decoded (%s) - keeping plain %s",
                field_name, exc, field_name,
            )
            continue
        config[field_name] = decoded
        logging.info(
            "%s taken from %s_b64 (%d chars, byte-exact)",
            field_name, field_name, len(decoded),
        )


def main():
    config = load_config()
    _decode_b64_fields(config)
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        target_agents = config.get('target_agents', []) or []
        action = str(_cfg(config, 'action', 'compile') or 'compile').strip().lower()

        logging.info("📐 LATEXER AGENT STARTED (LaTeX typesetting)")
        logging.info(f"Action: {action}")
        logging.info(f"Targets (downstream): {target_agents}")

        env = get_agent_env()
        tools = _resolve_toolchain(config, env)
        logging.info("Distribution: %s%s" % (
            tools["distribution"],
            (" — " + tools["version_line"]) if tools["version_line"] else ""))
        logging.info("Engine: %s -> %s" % (tools["engine"], tools["latex"] or "NOT FOUND"))

        outcome = {
            "action": action,
            "engine": tools["engine"],
            "distribution": tools["distribution"],
            "tex_path": "",
            "project_dir": str(_cfg(config, "project_dir")).strip(),
            "output_path": "",
            "output_dir": "",
            "filename": "",
            "page_count": 0,
            "bytes": 0,
            "passes": 0,
            "bibliography": "none",
            "errors": 0,
            "warnings": 0,
            "success": False,
            "status": "error",
        }
        notes = []
        ok = False

        do_preflight = _as_bool(_cfg(config, "preflight", True), True)
        pf = (_preflight(action, config, tools) if do_preflight
              else {"ok": True, "fatals": [], "warnings": []})

        if do_preflight and not pf["ok"]:
            notes.append("PREFLIGHT REFUSED (fail-safe):\n\n" + _format_preflight_report(pf))
            outcome["status"] = "refused"
            logging.error("❌ Preflight refused action=%s: %s" % (action, pf["fatals"]))

        else:
            if pf.get("warnings"):
                notes.append("[preflight] " + " | ".join(pf["warnings"]))
                notes.append("")

            # ───────────────────────── ENVIRONMENT ─────────────────────────
            if action == "validate":
                found = {
                    "engine (%s)" % tools["engine"]: tools["latex"],
                    "latexmk": tools["latexmk"], "biber": tools["biber"],
                    "bibtex": tools["bibtex"], "makeindex": tools["makeindex"],
                    "makeglossaries": tools["makeglossaries"],
                }
                lines = ["LaTeXer environment report (nothing was written):", "",
                         "  distribution : %s" % tools["distribution"],
                         "  version      : %s" % (tools["version_line"] or "(unknown)"), ""]
                for name, path in found.items():
                    note = ""
                    if name == "latexmk" and path and not tools.get("latexmk_usable"):
                        note = "   ⚠️ present but NOT USABLE (needs Perl) — LaTeXer will " \
                               "use its own convergence loop instead, which needs no Perl"
                    lines.append("  %-16s: %s%s" % (name, path or "NOT FOUND", note))
                lines += ["",
                          "  output_dir   : %s" % _default_output_dir(config),
                          "  projects_dir : %s" % _projects_dir(config),
                          "  templates    : %s" % ", ".join(sorted(_TEMPLATES)), ""]
                hint = _miktex_hint(tools["distribution"])
                if hint:
                    lines.append(hint)
                else:
                    lines.append("MiKTeX detected — LaTeXer is fully operational, and MiKTeX will "
                                 "install any missing package on demand while a document builds.")
                notes.append("\n".join(lines))
                ok = bool(tools["latex"])
                outcome["status"] = "validated" if ok else "engine_unavailable"
                outcome["success"] = ok

            elif action == "install":
                ok, report = _run_miktex_installer(config)
                notes.append(report)
                outcome["status"] = "installer_launched" if ok else "error"
                outcome["success"] = ok

            # ───────────────────────── AUTHORING ──────────────────────────
            elif action in ("create_file", "create_from_template", "scaffold_compile"):
                if action == "create_file":
                    source = _build_document(config)
                    kind = "documentclass=%s" % str(_cfg(config, "documentclass", "article"))
                else:
                    tpl = str(_cfg(config, "template", "article")).strip().lower()
                    source = _render_template(tpl, config)
                    kind = "template=%s" % tpl

                target = str(_cfg(config, "tex_path")).strip()
                if target:
                    path = os.path.abspath(target)
                    if not path.lower().endswith(".tex"):
                        path += ".tex"
                    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                else:
                    stem = os.path.splitext(_safe_basename(_cfg(config, "filename"), ".tex"))[0] or \
                        os.path.splitext(_timestamped_name(".tex"))[0]
                    proj = os.path.join(_projects_dir(config), stem)
                    os.makedirs(proj, exist_ok=True)
                    path = os.path.join(proj, stem + ".tex")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(source)
                outcome["tex_path"] = path
                outcome["project_dir"] = os.path.dirname(path)
                notes.append("WROTE %s (%s, %d chars)" % (path, kind, len(source)))
                logging.info("✅ .tex written: %s" % path)

                if action == "scaffold_compile":
                    result = _build(path, config, tools, env)
                    outcome["tex_path"] = path
                    ok = _finish_compile(result, config, tools, outcome, notes)
                    outcome["success"] = ok
                else:
                    ok = True
                    outcome["status"] = "created"
                    outcome["success"] = True

            elif action == "edit_file":
                path = os.path.abspath(str(_cfg(config, "tex_path")).strip())
                original = _read_text(path)
                mode = str(_cfg(config, "edit_mode", "replace")).strip().lower()
                find = str(_cfg(config, "find_text"))
                payload = str(_cfg(config, "replace_text"))
                count = original.count(find) if find else 0

                if mode in ("replace", "insert_before", "insert_after") and count == 0:
                    notes.append("find_text was not found in %s — nothing was changed." % path)
                    outcome["status"] = "not_found"
                elif mode == "replace" and count > 1 and \
                        not _as_bool(_cfg(config, "replace_all", False), False):
                    notes.append("find_text occurs %d times in %s. Refusing an ambiguous edit — "
                                 "give more surrounding context, or set replace_all: true."
                                 % (count, path))
                    outcome["status"] = "not_unique"
                else:
                    if mode == "replace":
                        updated = original.replace(find, payload) if \
                            _as_bool(_cfg(config, "replace_all", False), False) else \
                            original.replace(find, payload, 1)
                    elif mode == "insert_before":
                        updated = original.replace(find, payload + find, 1)
                    elif mode == "insert_after":
                        updated = original.replace(find, find + payload, 1)
                    elif mode == "append":
                        updated = original + ("" if original.endswith("\n") else "\n") + payload
                    else:  # prepend
                        updated = payload + ("" if payload.endswith("\n") else "\n") + original
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(updated)
                    outcome["tex_path"] = path
                    outcome["project_dir"] = os.path.dirname(path)
                    notes.append("EDITED %s (%s): %d -> %d chars" %
                                 (path, mode, len(original), len(updated)))
                    ok = True
                    outcome["status"] = "edited"
                    outcome["success"] = True

            elif action == "read_file":
                path = os.path.abspath(str(_cfg(config, "tex_path")).strip())
                text = _read_text(path) if path and os.path.isfile(path) else str(_cfg(config, "input_text"))
                limit = _as_int(_cfg(config, "max_log_chars", 20000), 20000)
                outcome["tex_path"] = path if os.path.isfile(path) else ""
                notes.append(text if (limit <= 0 or len(text) <= limit)
                             else text[:limit] + "\n... [truncated at max_log_chars]")
                ok = True
                outcome["status"] = "read"
                outcome["success"] = True

            elif action == "list_files":
                base = _work_base(config)
                recursive = _as_bool(_cfg(config, "recursive", True), True)
                pattern = os.path.join(base, "**", "*.tex") if recursive else os.path.join(base, "*.tex")
                files = sorted(glob.glob(pattern, recursive=recursive))
                lines = ["%d .tex file(s) under %s:" % (len(files), base), ""]
                for path in files:
                    try:
                        master = " [MASTER]" if _is_full_document(_read_text(path)) else ""
                    except Exception:
                        master = ""
                    lines.append("  %s (%d bytes)%s" % (os.path.relpath(path, base),
                                                        os.path.getsize(path), master))
                notes.append("\n".join(lines))
                outcome["project_dir"] = base
                ok = True
                outcome["status"] = "listed"
                outcome["success"] = True

            elif action in ("validate_tex", "structure"):
                path = os.path.abspath(str(_cfg(config, "tex_path")).strip())
                source = _read_text(path) if (path and os.path.isfile(path)) \
                    else str(_cfg(config, "input_text"))
                outcome["tex_path"] = path if os.path.isfile(path) else ""

                if action == "validate_tex":
                    report = _validate_source(source)
                    outcome["errors"] = len(report["errors"])
                    outcome["warnings"] = len(report["warnings"])
                    lines = ["LaTeX syntax check (static — no TeX distribution needed):", ""]
                    if report["errors"]:
                        lines.append("ERRORS (%d):" % len(report["errors"]))
                        lines += ["  ✗ " + e for e in report["errors"]]
                    if report["warnings"]:
                        lines.append("")
                        lines.append("WARNINGS (%d):" % len(report["warnings"]))
                        lines += ["  • " + w for w in report["warnings"]]
                    if not report["errors"] and not report["warnings"]:
                        lines.append("✅ No problems found: braces balanced, environments matched, "
                                     "every \\ref has a \\label.")
                    notes.append("\n".join(lines))
                    # AGENT success is NOT the DOCUMENT verdict (do NOT re-tie them).
                    # validate_tex is a READ-ONLY LINTER: finding a problem in the
                    # user's source IS the tool doing its job -- exactly like Grepper
                    # finding matches, or Analyzer reporting `findings`. Tying `ok` to
                    # report["ok"] made a lint that CORRECTLY caught an unclosed
                    # itemize environment exit 1, so the wrapped runtime marked the run
                    # `failed` and the Exec Report printed a red FAILURE over a run that
                    # had worked perfectly (Angela, 2026-08-06 -- LaTeXer wizard STEP 4).
                    # The document verdict stays FULLY truthful in `status`
                    # (validated / invalid) and in `errors` / `warnings` -- that is what
                    # a downstream Forker branches on. Its read-only siblings
                    # (`structure`, `read_file`, `list_files`) already report this way.
                    ok = True
                    outcome["status"] = "validated" if report["ok"] else "invalid"
                    outcome["success"] = True
                else:
                    st = _document_structure(source)
                    lines = ["Document structure:", "",
                             "  class      : %s%s" % (st["documentclass"] or "(none)",
                                                      (" [%s]" % st["class_options"])
                                                      if st["class_options"] else ""),
                             "  title      : %s" % (st["title"] or "(none)"),
                             "  author     : %s" % (st["author"] or "(none)"),
                             "  packages   : %s" % (", ".join(st["packages"]) or "(none)"),
                             "  labels     : %d    references: %d    citations: %d"
                             % (len(st["labels"]), len(st["references"]), len(st["citations"])),
                             "", "  outline (%d heading(s)):" % len(st["sections"])]
                    indent = {"part": 0, "chapter": 1, "section": 2,
                              "subsection": 3, "subsubsection": 4, "paragraph": 5}
                    for sec in st["sections"]:
                        lines.append("    " + "  " * indent.get(sec["level"], 2) +
                                     "%s: %s" % (sec["level"], sec["title"]))
                    notes.append("\n".join(lines))
                    ok = True
                    outcome["status"] = "analyzed"
                    outcome["success"] = True

            elif action == "clean":
                base = _work_base(config)
                removed = _clean_aux(base) if base else []
                outcome["project_dir"] = base
                notes.append("Removed %d auxiliary file(s) from %s%s" %
                             (len(removed), base,
                              (":\n  " + "\n  ".join(removed)) if removed else " (nothing to clean)"))
                notes.append("(.tex, .bib and .pdf files are never touched.)")
                ok = True
                outcome["status"] = "cleaned"
                outcome["success"] = True

            # ───────────────────────── BUILD ──────────────────────────────
            elif action in ("compile", "compile_project"):
                if action == "compile_project":
                    project_dir = os.path.abspath(str(_cfg(config, "project_dir")).strip())
                    tex_path, note = _find_main_tex(
                        project_dir, str(_cfg(config, "main_file")).strip(),
                        _as_bool(_cfg(config, "recursive", True), True))
                    err = "" if tex_path else note
                    outcome["project_dir"] = project_dir
                else:
                    tex_path, note, err = _resolve_compile_source(config, outcome)

                if err:
                    notes.append("Cannot compile: " + err)
                    outcome["status"] = "refused"
                else:
                    outcome["tex_path"] = tex_path
                    if not outcome["project_dir"]:
                        outcome["project_dir"] = os.path.dirname(tex_path)
                    notes.append(note)
                    children = _collect_children(tex_path)
                    if children:
                        notes.append("document set: %s + %d included file(s): %s" % (
                            os.path.basename(tex_path), len(children),
                            ", ".join(os.path.basename(c) for c in children)))
                    logging.info("📐 Typesetting %s with %s" % (tex_path, tools["engine"]))
                    result = _build(tex_path, config, tools, env)
                    ok = _finish_compile(result, config, tools, outcome, notes)
                    outcome["success"] = ok

        body = "\n".join(str(n) for n in notes if n is not None).strip()
        _emit_section(outcome, body or "(no output)")

        if ok:
            logging.info("🏁 LaTeXer %s complete: status=%s" % (action, outcome["status"]))
        else:
            logging.warning("⚠️ LaTeXer %s did not succeed (status=%s)." % (action, outcome["status"]))

        # ALWAYS trigger downstream — success, failure OR fail-safe refusal — so a
        # Forker can branch on {status} / {success} / {errors}.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info("🏁 LaTeXer agent finished. Triggered %d/%d agents."
                     % (total_triggered, len(target_agents)))
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    # TRUTHFUL EXIT CODE (do NOT revert to a bare sys.exit(0)).
    # The wrapped chat-agent runtime derives its completed/failed verdict from this
    # code, and the Exec Report renders that verdict. Exiting 0 unconditionally made
    # EVERY run look like SUCCESS -- a `refused`, or a `compiled_with_errors` build
    # (a PDF that IS mis-typeset) was reported to the user as a clean typeset.
    # Downstream `target_agents` are already triggered ABOVE this line, so a non-zero
    # code never breaks the always-trigger contract.
    #
    # SCOPE CORRECTION (2026-08-06): `ok` means "the AGENT did the job it was asked
    # to do", NOT "the user's document is clean". An `invalid` verdict from the
    # READ-ONLY `validate_tex` linter is therefore a SUCCESSFUL run -- see the note
    # at the validate_tex branch. Only actions that FAILED TO DO THE REQUESTED WORK
    # (refused / not_found / not_unique / engine_unavailable / a build that produced
    # no PDF or a mis-typeset one) may exit non-zero.
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
