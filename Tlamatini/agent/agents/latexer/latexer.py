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
    if tools["distribution"] == "miktex" and _as_bool(_cfg(config, "auto_install_packages", True), True):
        argv.append("--enable-installer")
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


def _finish_compile(result: dict, config: dict, tools: dict, outcome: dict, notes: list) -> bool:
    """Shared tail for compile / compile_project / scaffold_compile."""
    diag = result["diag"]
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

    if result["ok"]:
        outcome["status"] = "compiled"
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
    notes.insert(0, "❌ No PDF was produced.")
    return False


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
                    result = _compile(path, config, tools, env)
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
                    ok = report["ok"]
                    outcome["status"] = "validated" if ok else "invalid"
                    outcome["success"] = ok
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
                    result = _compile(tex_path, config, tools, env)
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
    # EVERY run look like SUCCESS -- a `refused`, an `invalid` lint, or a
    # `compiled_with_errors` build (a PDF that IS mis-typeset) was reported to the
    # user as a clean typeset. Downstream `target_agents` are already triggered
    # ABOVE this line, so a non-zero code never breaks the always-trigger contract.
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
