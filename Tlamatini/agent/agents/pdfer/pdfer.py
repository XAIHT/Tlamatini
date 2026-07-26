# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# PDFer Agent - Tlamatini's DOCUMENT COMPOSER (the WRITE side of the document family).
# Action: Triggered by upstream -> resolve the content (Tlamatini's own answer, Markdown,
#         HTML, plain text, images, existing PDFs) -> optionally polish it through Ollama
#         -> render ONE styled PDF -> emit INI_SECTION_PDFER -> ALWAYS trigger downstream
#         (success OR failure OR fail-safe refusal).
#
# PDFer AUTHORS documents; File-Extractor / File-Interpreter READ them. It needs ZERO new
# dependencies: markdown + xhtml2pdf + pymupdf(fitz) + reportlab + pillow + pypdf already
# ship with Tlamatini and are already used by agent/doc_generation. The Markdown -> HTML ->
# PDF pipeline (and DEFAULT_CSS) is ported INLINE from agent/doc_generation/mardown_to_pdf.py
# because a pool subprocess has no sys.path back into the Django app and must NEVER import
# agent.* — exactly like acpxer.py ports the ACPX runtime inline.
#
# Every backend is imported LAZILY inside the function that needs it, so a machine missing
# one library degrades to a clear "engine_unavailable" report instead of crashing at import.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# ── Tlamatini Temp policy: temporary files ONLY under <app>/Temp ─────────
# Honor TLAMATINI_TEMP (exported by the Tlamatini core, inherited by every spawned
# agent via get_agent_env's os.environ.copy()) so every intermediate file this agent
# writes — normalized/downscaled images, the staged HTML — lands under <app>/Temp,
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
import html
import json
import time
import yaml
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

    The wrapped Multi-Turn parser can hand us ``"18 mm margins"`` where the canvas
    hands us ``18`` — the same class of bug that bit Recorder's ``record_seconds``.
    """
    try:
        if isinstance(raw, bool):
            return default
        # Only scalars are coercible. Without this guard an arbitrary object falls
        # through to str(raw) and its repr's hex address ("<object at 0x00...>")
        # yields a digit run, so a junk value would silently become 0 — e.g. a
        # margin of 0 mm instead of the intended default.
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
    """Accept a real list, a comma/semicolon/newline-separated string, or a single path.

    The canvas writes a YAML list; the wrapped chat tool usually writes one string
    (``images="a.png, b.png"``). Both must work, and neither may raise.
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip().strip('"').strip("'") for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    # Strip a bracketed literal the parser may have handed us verbatim: "[a, b]"
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = re.split(r"[,;\n]+", text)
    return [p.strip().strip('"').strip("'") for p in parts if p.strip().strip('"').strip("'")]


# ========================================
# DEFAULT STYLESHEET
# Ported INLINE from agent/doc_generation/mardown_to_pdf.py (a pool subprocess cannot
# import agent.*). Keep the two in visual sync: this is the same look Tlamatini's own
# generated project docs have, so a PDFer report feels native next to them.
# ========================================

DEFAULT_CSS = """
body {
  font-family: Helvetica, Arial, sans-serif;
  line-height: 1.35;
  font-size: 11pt;
  color: #111111;
}

h1, h2, h3 { margin: 0.6em 0 0.3em; color: #7F1D1D; }
h1 { font-size: 20pt; border-bottom: 2px solid #C1272D; padding-bottom: 4px; }
h2 { font-size: 15pt; }
h3 { font-size: 12.5pt; }
p { margin: 0.35em 0; }

a { color: #C1272D; text-decoration: none; }

code, pre {
  font-family: Courier, monospace;
  font-size: 9.5pt;
}

pre {
  padding: 10px;
  border: 1px solid #ddd;
  background-color: #FDF6E3;
  white-space: pre-wrap;
}

blockquote {
  border-left: 3px solid #E8A33D;
  margin: 0.5em 0;
  padding-left: 10px;
  color: #444444;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.6em 0;
}
th, td {
  border: 1px solid #ddd;
  padding: 6px;
  vertical-align: top;
}
th { background-color: #F3E9D2; }

img { max-width: 100%; }

.tlm-cover-title {
  font-size: 30pt;
  color: #7F1D1D;
  margin-top: 55mm;
  text-align: center;
  font-weight: bold;
}
.tlm-cover-subtitle {
  font-size: 14pt;
  color: #555555;
  text-align: center;
  margin-top: 6mm;
}
.tlm-cover-rule {
  border-top: 3px solid #C1272D;
  width: 45%;
  margin: 8mm auto;
}
.tlm-figure { text-align: center; margin: 6mm 0; }
.tlm-caption { font-size: 9pt; color: #666666; margin-top: 2mm; }
.tlm-footer { font-size: 8.5pt; color: #888888; text-align: center; }
"""

_PAGE_SIZES = {"a4": "A4", "letter": "letter", "legal": "legal"}

# The three source shapes PDFer accepts, and every mode it can run.
_RENDER_MODES = ("markdown", "html", "text", "images", "mixed", "merge")
_META_MODES = ("auto", "info", "validate")
_ALL_MODES = _RENDER_MODES + _META_MODES

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")


# ========================================
# BACKEND PROBES (every import is lazy + guarded)
# ========================================

def _probe_backends() -> dict:
    """Report which PDF backends import cleanly. Never raises."""
    found = {}
    for label, module in (
        ("markdown", "markdown"),
        ("xhtml2pdf", "xhtml2pdf"),
        ("pymupdf", "fitz"),
        ("reportlab", "reportlab"),
        ("pillow", "PIL"),
        ("pypdf", "pypdf"),
    ):
        try:
            __import__(module)
            found[label] = True
        except Exception:
            found[label] = False
    return found


# ========================================
# OUTPUT LOCATION (Documents known-folder aware, collision-proof)
# ========================================

def _documents_dir() -> str:
    """The user's real Documents folder, localized. Falls back to ~/Documents.

    Mirrors Camcorder's Pictures / Recorder's Music known-folder resolution so a
    PDF lands where a Windows user actually looks for documents, even when the
    folder has been redirected or is named "Documentos".
    """
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
                    resolved = path_ptr.value
                    ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                    if resolved:
                        return resolved
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _default_output_dir(config: dict) -> str:
    explicit = str(_cfg(config, "output_dir", "")).strip().strip('"').strip("'")
    if explicit:
        return os.path.abspath(explicit)
    return os.path.join(_documents_dir(), "TlamatiniPDF")


def _temp_root() -> str:
    """<app>/Temp (Rule 15). Falls back to the agent dir so we never write outside."""
    handle = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if handle:
        try:
            os.makedirs(handle, exist_ok=True)
            return handle
        except Exception:
            pass
    return os.path.dirname(os.path.abspath(__file__))


def _resolve_output_path(config: dict) -> str:
    """Absolute, collision-proof destination path. Creates the directory."""
    out_dir = _default_output_dir(config)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        logging.error(f"⚠️ Could not create output dir {out_dir}: {e}")
    name = str(_cfg(config, "filename", "")).strip().strip('"').strip("'")
    if not name:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1000)
        name = f"pdfer_{stamp}_{millis:03d}.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    # Never allow a filename to escape the chosen directory.
    name = os.path.basename(name)
    path = os.path.join(out_dir, name)
    if _as_bool(_cfg(config, "overwrite", False), False):
        return path
    stem, ext = os.path.splitext(path)
    counter = 2
    while os.path.exists(path) and counter < 1000:
        path = f"{stem}_{counter}{ext}"
        counter += 1
    return path


# ========================================
# CONTENT RESOLUTION + AUTO-MODE SNIFFING
# ========================================

_HTML_HINT = re.compile(
    r"<\s*(html|body|table|div|p|h[1-6]|ul|ol|br|span|strong|em|thead|tbody|tr|td)\b[^>]*>",
    re.IGNORECASE,
)


def _looks_like_html(text: str) -> bool:
    """Tlamatini's own answers emit HTML tables (prompt.pmt Rule 6), so this is the
    signal that makes "turn your last answer into a PDF" work with mode=auto."""
    if not text:
        return False
    return len(_HTML_HINT.findall(text)) >= 2


def _read_input_file(path: str) -> tuple:
    """Return (text, kind) where kind is 'markdown' | 'html' | 'text' | ''. Never raises."""
    if not path or not os.path.isfile(path):
        return "", ""
    ext = os.path.splitext(path)[1].lower()
    kind = {".md": "markdown", ".markdown": "markdown", ".htm": "html",
            ".html": "html"}.get(ext, "text")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), kind
    except Exception as e:
        logging.error(f"⚠️ Could not read input_file {path}: {e}")
        return "", ""


def _resolve_content(config: dict) -> tuple:
    """Return (text, source_type, file_kind). source_type ∈ text|file|images|pdfs|none."""
    text = str(_cfg(config, "input_text", "") or "")
    in_file = str(_cfg(config, "input_file", "")).strip().strip('"').strip("'")
    file_kind = ""
    source_type = "none"
    if text.strip():
        source_type = "text"
    elif in_file:
        text, file_kind = _read_input_file(in_file)
        source_type = "file" if text.strip() else "none"
    return text, source_type, file_kind


def _sniff_mode(config: dict, text: str, file_kind: str, images: list, pdfs: list) -> str:
    """Decide the render mode for mode=auto. Deterministic and explainable."""
    has_text = bool(text.strip())
    if pdfs:
        return "merge"
    if has_text and images:
        return "mixed"
    if images and not has_text:
        return "images"
    if not has_text:
        return "images" if images else "markdown"
    if file_kind == "html" or _looks_like_html(text):
        return "html"
    if file_kind == "markdown":
        return "markdown"
    return "markdown"


# ========================================
# OPTIONAL OLLAMA POLISH (stdlib urllib — never imports agent.*)
# ========================================

_POLISH_PROMPT = (
    "You are a technical editor. Rewrite the CONTENT below as clean, well-structured "
    "GitHub-flavored Markdown suitable for a printed PDF report. Rules: keep EVERY fact "
    "and every number exactly as given — never invent, never drop information; add a short "
    "'# ' title line at the top; use '## ' section headings, bullet lists and Markdown "
    "tables where they help; keep code inside fenced blocks. Output ONLY the Markdown, with "
    "no preamble and no closing commentary.\n\nCONTENT:\n"
)


def _ollama_polish(text: str, config: dict) -> tuple:
    """Ask an Ollama model to restructure *text* into clean Markdown.

    Returns (polished_text, note). NEVER raises and NEVER loses the document: any
    failure returns the ORIGINAL text plus an explanatory note, exactly like
    Whisperer's optional ollama_cleanup.
    """
    import urllib.error
    import urllib.request

    base = str(_cfg(config, "ollama_url", "http://localhost:11434")).strip().rstrip("/")
    model = str(_cfg(config, "ollama_model", "glm-5.2:cloud")).strip()
    token = str(_cfg(config, "ollama_token", "")).strip()
    timeout = float(_as_int(_cfg(config, "ollama_timeout", 180), 180))
    custom = str(_cfg(config, "ollama_prompt", "")).strip()
    if not base or not model:
        return text, "ollama polish skipped (no url/model configured)"

    prompt = (custom + "\n\n" + text) if custom else (_POLISH_PROMPT + text)
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/generate", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        polished = (json.loads(body).get("response") or "").strip()
        if not polished:
            return text, "ollama polish returned nothing — kept the raw content"
        logging.info(f"🧠 Ollama polish applied ({model}): {len(text)} -> {len(polished)} chars")
        return polished, f"ollama polish applied via {model}"
    except urllib.error.URLError as e:
        logging.warning(f"⚠️ Ollama polish unreachable ({e}) — keeping the raw content")
        return text, f"ollama polish failed ({e}) — kept the raw content"
    except Exception as e:
        logging.warning(f"⚠️ Ollama polish failed ({e}) — keeping the raw content")
        return text, f"ollama polish failed ({e}) — kept the raw content"


# ========================================
# HTML DOCUMENT ASSEMBLY (the xhtml2pdf path)
# ========================================

def _page_css(config: dict) -> str:
    size = _PAGE_SIZES.get(str(_cfg(config, "page_size", "A4")).strip().lower(), "A4")
    orientation = str(_cfg(config, "orientation", "portrait")).strip().lower()
    if orientation not in ("portrait", "landscape"):
        orientation = "portrait"
    margin = max(0, _as_int(_cfg(config, "margins_mm", 18), 18))
    numbers = _as_bool(_cfg(config, "page_numbers", True), True)
    footer_frame = ""
    if numbers:
        footer_frame = (
            "  @frame tlm_footer_frame {\n"
            "    -pdf-frame-content: tlmFooterContent;\n"
            f"    bottom: {max(4, margin // 2)}mm; height: 8mm;\n"
            f"    left: {margin}mm; right: {margin}mm;\n"
            "  }\n"
        )
    return (
        "@page {\n"
        f"  size: {size} {orientation};\n"
        f"  margin: {margin}mm;\n"
        f"{footer_frame}"
        "}\n"
    )


def _markdown_to_html_body(md_text: str, want_toc: bool) -> str:
    """Markdown -> HTML body. Ported from mardown_to_pdf.markdown_text_to_pdf."""
    from markdown import markdown as _markdown
    extensions = ["fenced_code", "tables", "toc"]
    body = _markdown(md_text, extensions=extensions, output_format="html5")
    if want_toc:
        # The `toc` extension exposes [TOC]; render it explicitly when asked so the
        # caller does not have to embed the marker themselves.
        body = _markdown("[TOC]\n\n" + md_text, extensions=extensions, output_format="html5")
    return body


def _text_to_html_body(text: str) -> str:
    """Plain text -> a faithful <pre> block (escaped, wraps, never re-interpreted)."""
    return "<pre>" + html.escape(text) + "</pre>"


def _cover_html(config: dict) -> str:
    title = str(_cfg(config, "title", "")).strip()
    if not title:
        return ""
    subtitle = str(_cfg(config, "subtitle", "")).strip()
    parts = [f'<div class="tlm-cover-title">{html.escape(title)}</div>',
             '<div class="tlm-cover-rule"></div>']
    if subtitle:
        parts.append(f'<div class="tlm-cover-subtitle">{html.escape(subtitle)}</div>')
    parts.append('<div style="page-break-after: always;"></div>')
    return "\n".join(parts)


def _figures_html(images: list, config: dict) -> str:
    """<img> blocks for the mixed mode. Paths are made absolute + file:/// safe."""
    if not images:
        return ""
    caption = _as_bool(_cfg(config, "image_caption", True), True)
    layout = str(_cfg(config, "image_layout", "one-per-page")).strip().lower()
    chunks = []
    for path in images:
        abs_path = os.path.abspath(path)
        if not os.path.isfile(abs_path):
            logging.warning(f"⚠️ Skipping missing image: {path}")
            continue
        src = abs_path.replace("\\", "/")
        block = ['<div class="tlm-figure">', f'<img src="{html.escape(src)}" />']
        if caption:
            block.append(f'<div class="tlm-caption">{html.escape(os.path.basename(abs_path))}</div>')
        block.append("</div>")
        if layout == "one-per-page":
            block.append('<div style="page-break-after: always;"></div>')
        chunks.append("\n".join(block))
    return "\n".join(chunks)


def _build_html_document(body: str, config: dict, figures: str = "") -> str:
    css_override = str(_cfg(config, "css", "")).strip()
    css_text = css_override if css_override else DEFAULT_CSS
    footer = ""
    if _as_bool(_cfg(config, "page_numbers", True), True):
        footer = ('<div id="tlmFooterContent" class="tlm-footer">'
                  'page <pdf:pagenumber> of <pdf:pagecount></div>')
    title = str(_cfg(config, "title", "")).strip() or "Document"
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <style>
{_page_css(config)}
{css_text}
    </style>
  </head>
  <body>
{footer}
{_cover_html(config)}
{body}
{figures}
  </body>
</html>
"""


def _render_html_to_pdf(html_doc: str, output_path: str) -> tuple:
    """pisa.CreatePDF — the exact call agent/doc_generation already trusts.

    Returns (ok, message). xhtml2pdf reports soft errors via ``pisa_status.err``;
    a non-zero count with a readable file on disk is still surfaced as a warning
    rather than thrown away.
    """
    from xhtml2pdf import pisa
    with open(output_path, "w+b") as pdf_file:
        status = pisa.CreatePDF(html_doc, dest=pdf_file, encoding="utf-8")
    if status.err:
        return False, f"xhtml2pdf reported {status.err} error(s) during conversion"
    return True, "rendered via xhtml2pdf"


# ========================================
# IMAGE COMPOSITION (the PyMuPDF path)
# ========================================

def _normalize_image(path: str, max_px: int) -> str:
    """Downscale/convert an image into <app>/Temp when needed. Returns a usable path.

    Guarded end-to-end: if Pillow is missing or the image is unreadable the ORIGINAL
    path is returned so PyMuPDF still gets its chance.
    """
    if max_px <= 0:
        return path
    try:
        from PIL import Image
    except Exception:
        return path
    try:
        with Image.open(path) as im:
            if max(im.size) <= max_px and im.mode in ("RGB", "L"):
                return path
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            staged_dir = os.path.join(_temp_root(), "PDFer")
            os.makedirs(staged_dir, exist_ok=True)
            stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(path))
            staged = os.path.join(staged_dir, f"norm_{int(time.time() * 1000)}_{stem}.jpg")
            im.save(staged, "JPEG", quality=88)
            return staged
    except Exception as e:
        logging.warning(f"⚠️ Could not normalize image {path}: {e}")
        return path


def _page_dimensions(config: dict) -> tuple:
    """(width, height) in PDF points for the configured page size + orientation."""
    sizes = {"a4": (595.28, 841.89), "letter": (612.0, 792.0), "legal": (612.0, 1008.0)}
    key = str(_cfg(config, "page_size", "A4")).strip().lower()
    width, height = sizes.get(key, sizes["a4"])
    if str(_cfg(config, "orientation", "portrait")).strip().lower() == "landscape":
        width, height = height, width
    return width, height


def _render_images_to_pdf(images: list, output_path: str, config: dict) -> tuple:
    """Compose images into a PDF with PyMuPDF. Returns (ok, message, used_count)."""
    import fitz

    layout = str(_cfg(config, "image_layout", "one-per-page")).strip().lower()
    if layout not in ("one-per-page", "fit", "grid"):
        layout = "one-per-page"
    max_px = max(0, _as_int(_cfg(config, "max_image_px", 1600), 1600))
    margin_mm = max(0, _as_int(_cfg(config, "margins_mm", 18), 18))
    margin = margin_mm * 72.0 / 25.4          # mm -> PDF points
    page_w, page_h = _page_dimensions(config)
    columns = max(1, _as_int(_cfg(config, "grid_columns", 2), 2))

    usable = [p for p in images if os.path.isfile(p)]
    missing = [p for p in images if not os.path.isfile(p)]
    for gone in missing:
        logging.warning(f"⚠️ Skipping missing image: {gone}")
    if not usable:
        return False, "none of the supplied image paths exist", 0

    doc = fitz.open()
    try:
        if layout == "grid":
            per_page = columns * max(1, int((page_h - 2 * margin) //
                                            ((page_w - 2 * margin) / columns)))
            cell_w = (page_w - 2 * margin) / columns
            rows = max(1, per_page // columns)
            cell_h = (page_h - 2 * margin) / rows
            for index in range(0, len(usable), per_page):
                page = doc.new_page(width=page_w, height=page_h)
                for slot, img_path in enumerate(usable[index:index + per_page]):
                    row, col = divmod(slot, columns)
                    x0 = margin + col * cell_w
                    y0 = margin + row * cell_h
                    rect = fitz.Rect(x0 + 4, y0 + 4, x0 + cell_w - 4, y0 + cell_h - 4)
                    page.insert_image(rect, filename=_normalize_image(img_path, max_px),
                                      keep_proportion=True)
        elif layout == "fit":
            # Each page takes the IMAGE's own aspect ratio — no letterboxing at all.
            # The page is sized from the image's real pixel dimensions (read through
            # Pillow by _image_size, which falls back to A4 when unreadable) rather
            # than by opening it as a fitz Document: fitz.open() on a raster file does
            # NOT yield a page whose .rect is meaningful, so that path would have
            # silently produced A4-shaped pages for every image.
            for img_path in usable:
                staged = _normalize_image(img_path, max_px)
                img_w, img_h = _image_size(staged)
                page = doc.new_page(width=img_w, height=img_h)
                page.insert_image(page.rect, filename=staged, keep_proportion=True)
        else:  # one-per-page
            for img_path in usable:
                page = doc.new_page(width=page_w, height=page_h)
                rect = fitz.Rect(margin, margin, page_w - margin, page_h - margin)
                page.insert_image(rect, filename=_normalize_image(img_path, max_px),
                                  keep_proportion=True)
        doc.save(output_path)
    finally:
        doc.close()
    note = f"composed {len(usable)} image(s) via PyMuPDF ({layout})"
    if missing:
        note += f"; {len(missing)} missing path(s) skipped"
    return True, note, len(usable)


def _image_size(path: str) -> tuple:
    """(w, h) in points for an image file, defaulting to A4 when unknown."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return float(im.size[0]), float(im.size[1])
    except Exception:
        return 595.28, 841.89


# ========================================
# MERGE / INFO / METADATA
# ========================================

def _merge_pdfs(sources: list, output_path: str) -> tuple:
    """Append every readable PDF in *sources* into one file. Returns (ok, message)."""
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    merged, skipped = 0, []
    for path in sources:
        if not os.path.isfile(path):
            skipped.append(os.path.basename(path) + " (missing)")
            continue
        try:
            for page in PdfReader(path).pages:
                writer.add_page(page)
            merged += 1
        except Exception as e:
            skipped.append(f"{os.path.basename(path)} ({e})")
    if not merged:
        return False, "no readable PDF among: " + (", ".join(skipped) or "(empty list)")
    with open(output_path, "wb") as f:
        writer.write(f)
    note = f"merged {merged} PDF(s)"
    if skipped:
        note += "; skipped " + ", ".join(skipped)
    return True, note


def _stamp_metadata(output_path: str, config: dict) -> None:
    """Write Title/Author/Producer into the PDF. Best-effort; never raises."""
    try:
        from pypdf import PdfReader, PdfWriter
        title = str(_cfg(config, "title", "")).strip() or os.path.basename(output_path)
        author = str(_cfg(config, "author", "")).strip() or "Tlamatini"
        reader = PdfReader(output_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.add_metadata({
            "/Title": title,
            "/Author": author,
            "/Producer": "Tlamatini PDFer",
            "/Creator": "Tlamatini PDFer",
        })
        staged = output_path + ".meta.tmp"
        with open(staged, "wb") as f:
            writer.write(f)
        os.replace(staged, output_path)
    except Exception as e:
        logging.warning(f"⚠️ Could not stamp PDF metadata: {e}")


def _pdf_page_count(path: str) -> int:
    """Page count via pypdf, then PyMuPDF. Returns 0 when neither can read it."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        pass
    try:
        import fitz
        with fitz.open(path) as doc:
            return doc.page_count
    except Exception:
        return 0


def _pdf_info(path: str) -> tuple:
    """Human-readable report about an existing PDF. Returns (ok, body)."""
    if not os.path.isfile(path):
        return False, f"No such PDF: {path}"
    lines = [f"file       : {path}",
             f"bytes      : {os.path.getsize(path)}",
             f"pages      : {_pdf_page_count(path)}"]
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        lines.append(f"encrypted  : {bool(getattr(reader, 'is_encrypted', False))}")
        meta = reader.metadata or {}
        for key in ("/Title", "/Author", "/Subject", "/Producer", "/Creator", "/CreationDate"):
            value = meta.get(key)
            if value:
                lines.append(f"{key[1:]:<11}: {value}")
    except Exception as e:
        lines.append(f"(metadata unavailable: {e})")
    return True, "\n".join(lines)


# ========================================
# FAIL-SAFE PREFLIGHT — REFUSE rather than write a wrong/empty document
# ========================================

def _preflight(mode: str, config: dict, text: str, images: list, pdfs: list,
               backends: dict) -> dict:
    """Validate BEFORE writing anything. Returns {ok, fatals, warnings}.

    Same contract as STM32er / ESP32er / Nmapper: a refusal is the agent working as
    DESIGNED (a routable `status: refused` section), never a crash and never a
    silently-empty PDF.
    """
    fatals, warnings = [], []

    if mode not in _ALL_MODES:
        fatals.append(f"Unknown mode {mode!r}. Valid: {', '.join(sorted(_ALL_MODES))}.")
        return {"ok": False, "fatals": fatals, "warnings": warnings}

    if mode == "validate":
        return {"ok": True, "fatals": [], "warnings": warnings}

    if mode == "info":
        target = str(_cfg(config, "input_file", "")).strip()
        if not target:
            fatals.append("mode='info' needs input_file pointing at an existing .pdf.")
        elif not os.path.isfile(target):
            fatals.append(f"mode='info': no such file: {target}")
        return {"ok": not fatals, "fatals": fatals, "warnings": warnings}

    # ---- content presence -------------------------------------------------
    if mode in ("markdown", "html", "text") and not text.strip():
        fatals.append(
            f"mode='{mode}' needs content — set input_text (Tlamatini's answer / Markdown / "
            "HTML) or input_file (a .md / .txt / .html path). Refusing to write an empty PDF."
        )
    if mode == "images" and not images:
        fatals.append("mode='images' needs at least one path in `images`.")
    if mode == "mixed" and not text.strip() and not images:
        fatals.append("mode='mixed' needs input_text and/or images.")
    if mode == "merge" and not pdfs:
        fatals.append("mode='merge' needs at least one path in `input_pdfs`.")

    # ---- backend availability --------------------------------------------
    if mode in ("markdown", "html", "text", "mixed"):
        if not backends.get("xhtml2pdf"):
            fatals.append("xhtml2pdf is not importable — the HTML->PDF renderer is unavailable.")
        if mode == "markdown" and not backends.get("markdown"):
            fatals.append("the `markdown` library is not importable — cannot render Markdown.")
    if mode in ("images",) or (mode == "mixed" and images):
        if mode == "images" and not backends.get("pymupdf"):
            fatals.append("PyMuPDF (fitz) is not importable — cannot compose images into a PDF.")
        if not backends.get("pillow"):
            warnings.append("Pillow missing — images are embedded without downscaling.")
    if mode == "merge" and not backends.get("pypdf"):
        fatals.append("pypdf is not importable — cannot merge PDFs.")

    # ---- referenced paths -------------------------------------------------
    for path in images:
        if not os.path.isfile(path):
            warnings.append(f"image not found (skipped): {path}")
    for path in pdfs:
        if not os.path.isfile(path):
            warnings.append(f"PDF not found (skipped): {path}")
    in_file = str(_cfg(config, "input_file", "")).strip()
    if in_file and not os.path.isfile(in_file) and not text.strip():
        fatals.append(f"input_file does not exist: {in_file}")

    # ---- destination writability -----------------------------------------
    out_dir = _default_output_dir(config)
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe = os.path.join(out_dir, f".pdfer_write_probe_{os.getpid()}")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except Exception as e:
        fatals.append(f"output_dir is not writable ({out_dir}): {e}")

    if str(_cfg(config, "page_size", "A4")).strip().lower() not in _PAGE_SIZES:
        warnings.append(
            f"unknown page_size {_cfg(config, 'page_size')!r} — falling back to A4.")

    return {"ok": not fatals, "fatals": fatals, "warnings": warnings}


def _format_preflight_report(pf: dict) -> str:
    lines = []
    if pf.get("fatals"):
        lines.append("BLOCKERS:")
        lines += [f"  • {item}" for item in pf["fatals"]]
    if pf.get("warnings"):
        lines.append("WARNINGS:")
        lines += [f"  • {item}" for item in pf["warnings"]]
    return "\n".join(lines) or "(no findings)"


# ========================================
# STRUCTURED OUTPUT (Parametrizer source)
# ========================================

def _emit_section(fields: dict, body: str) -> None:
    """Emit an INI_SECTION_PDFER<<< block atomically (a SINGLE logging.info call).

    KV header field names MUST stay aligned with
    ``agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['pdfer']``,
    ``views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['pdfer']`` and
    ``parametrizer.SECTION_AGENT_TYPES``.
    """
    header = "\n".join(f"{key}: {value}" for key, value in fields.items())
    logging.info("INI_SECTION_PDFER<<<\n" + header + "\n\n" + body + "\n>>>END_SECTION_PDFER")


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
        requested_mode = str(_cfg(config, 'mode', 'auto') or 'auto').strip().lower()

        logging.info("📕 PDFER AGENT STARTED (document composer)")
        logging.info(f"Mode (requested): {requested_mode}")
        logging.info(f"Targets (downstream): {target_agents}")

        backends = _probe_backends()
        logging.info("Backends: " + ", ".join(
            f"{name}={'ok' if ok else 'MISSING'}" for name, ok in backends.items()))

        images = _as_list(_cfg(config, "images", []))
        pdfs = _as_list(_cfg(config, "input_pdfs", []))
        text, source_type, file_kind = _resolve_content(config)

        mode = requested_mode
        if mode == "auto":
            mode = _sniff_mode(config, text, file_kind, images, pdfs)
            logging.info(f"🔎 mode=auto resolved to '{mode}' "
                         f"(text={len(text)} chars, images={len(images)}, pdfs={len(pdfs)})")
        if source_type == "none" and images:
            source_type = "images"
        elif source_type == "none" and pdfs:
            source_type = "pdfs"

        outcome = {
            "mode": mode,
            "source_type": source_type,
            "output_path": "",
            "output_dir": "",
            "filename": "",
            "page_count": 0,
            "bytes": 0,
            "images_used": 0,
            "engine": "",
            "status": "error",
        }
        body = ""
        ok = False

        # ── fail-safe preflight ───────────────────────────────────────────
        do_preflight = _as_bool(_cfg(config, "preflight", True), True)
        pf = (_preflight(mode, config, text, images, pdfs, backends)
              if do_preflight else {"ok": True, "fatals": [], "warnings": []})

        if do_preflight and not pf["ok"]:
            body = "PREFLIGHT REFUSED (fail-safe):\n\n" + _format_preflight_report(pf)
            outcome["status"] = "refused"
            logging.error(f"❌ Preflight refused mode={mode}: {pf['fatals']}")

        elif mode == "validate":
            lines = ["PDFer backend report (no file written):", ""]
            for name, present in backends.items():
                lines.append(f"  {name:<10}: {'available' if present else 'MISSING'}")
            lines += [
                "",
                f"output_dir : {_default_output_dir(config)}",
                f"temp root  : {os.path.join(_temp_root(), 'PDFer')}",
                "",
                "markdown + xhtml2pdf render text/Markdown/HTML; pymupdf composes images;",
                "pypdf merges + stamps metadata; pillow downscales before embedding.",
            ]
            body = "\n".join(lines)
            ok = all(backends.values())
            outcome["status"] = "validated" if ok else "engine_unavailable"
            outcome["engine"] = "probe"

        elif mode == "info":
            ok, body = _pdf_info(str(_cfg(config, "input_file", "")).strip())
            target = str(_cfg(config, "input_file", "")).strip()
            outcome.update({
                "status": "inspected" if ok else "error",
                "engine": "pypdf",
                "output_path": target,
                "output_dir": os.path.dirname(os.path.abspath(target)) if target else "",
                "filename": os.path.basename(target),
                "page_count": _pdf_page_count(target) if ok else 0,
                "bytes": os.path.getsize(target) if ok and os.path.isfile(target) else 0,
            })

        else:
            # ── a render mode: optional polish -> render -> stamp -> measure ──
            notes = []
            if pf.get("warnings"):
                notes.append("[preflight] " + " | ".join(pf["warnings"]))

            if text.strip() and _as_bool(_cfg(config, "ollama_polish", False), False):
                text, polish_note = _ollama_polish(text, config)
                notes.append("[polish] " + polish_note)
                # A polished document is Markdown by contract, so an HTML-sniffed
                # source becomes Markdown once the model has restructured it.
                if mode == "html":
                    mode = "markdown"
                    outcome["mode"] = mode

            output_path = _resolve_output_path(config)
            logging.info(f"📄 Rendering {mode} -> {output_path}")

            try:
                if mode == "merge":
                    ok, message = _merge_pdfs(pdfs, output_path)
                    outcome["engine"] = "pypdf"
                elif mode == "images":
                    ok, message, used = _render_images_to_pdf(images, output_path, config)
                    outcome["engine"] = "pymupdf"
                    outcome["images_used"] = used
                else:
                    if mode == "html":
                        html_body = text
                    elif mode == "text":
                        html_body = _text_to_html_body(text)
                    else:  # markdown | mixed
                        html_body = (_markdown_to_html_body(
                            text, _as_bool(_cfg(config, "toc", False), False))
                            if text.strip() else "")
                    figures = _figures_html(images, config) if mode == "mixed" else ""
                    if mode == "mixed":
                        outcome["images_used"] = sum(
                            1 for p in images if os.path.isfile(p))
                    html_doc = _build_html_document(html_body, config, figures)
                    ok, message = _render_html_to_pdf(html_doc, output_path)
                    outcome["engine"] = "xhtml2pdf"
                notes.append(message)
            except ImportError as e:
                ok = False
                outcome["status"] = "engine_unavailable"
                notes.append(f"a required PDF backend is not installed: {e}")
                logging.error(f"❌ Backend missing while rendering {mode}: {e}")
            except Exception as e:
                ok = False
                notes.append(f"render failed: {e}")
                logging.error(f"❌ Render failed ({mode}): {e}")

            if ok and os.path.isfile(output_path):
                _stamp_metadata(output_path, config)
                outcome.update({
                    "output_path": output_path,
                    "output_dir": os.path.dirname(output_path),
                    "filename": os.path.basename(output_path),
                    "page_count": _pdf_page_count(output_path),
                    "bytes": os.path.getsize(output_path),
                    "status": "created",
                })
                notes.append(
                    f"WROTE {output_path} "
                    f"({outcome['page_count']} page(s), {outcome['bytes']} bytes)")
                logging.info(f"✅ PDF written: {output_path} "
                             f"({outcome['page_count']} pages, {outcome['bytes']} bytes)")
            elif outcome["status"] not in ("engine_unavailable",):
                outcome["status"] = "error"
                # A half-written file is worse than none: remove it so a downstream
                # agent never picks up a corrupt PDF.
                try:
                    if os.path.isfile(output_path) and os.path.getsize(output_path) == 0:
                        os.remove(output_path)
                except Exception:
                    pass
            body = "\n".join(n for n in notes if n)

        _emit_section(outcome, body or "(no output)")

        if ok:
            logging.info(f"🏁 PDFer {mode} complete: status={outcome['status']}")
        else:
            logging.warning(f"⚠️ PDFer {mode} did not succeed (status={outcome['status']}).")

        # ALWAYS trigger downstream — success, failure OR fail-safe refusal — so a
        # Forker can branch on {status} / {page_count}.
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(
            f"🏁 PDFer agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")
    finally:
        time.sleep(0.4)  # Keep LED green briefly
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
