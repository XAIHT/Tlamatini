# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Crawler Agent - Web page crawler with RAW content capture and LLM analysis
# Action: Triggered by upstream -> Fetch URL -> Capture RAW HTTP response (headers + full body)
#         -> Extract resource inventory -> Save raw + structured content -> Query LLM -> Log response -> Trigger downstream
# Developer-oriented: preserves ALL HTML, JavaScript, CSS, inline scripts, meta tags, data attributes, etc.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import json
import html as _html_lib
import zlib
import threading
import logging
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
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from datetime import datetime
from typing import Dict, List, Tuple, Optional

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


def _load_config_file(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


def load_config(*args, **kwargs):
    """Apply Config -> Models choices while retaining explicit agent overrides."""
    import importlib.util as _model_import
    from pathlib import Path as _ModelPath
    config = _load_config_file(*args, **kwargs)
    here = _ModelPath(__file__).resolve()
    candidates = [here.parent / 'model_settings.py']
    candidates += [p / 'model_settings.py' for p in here.parents if p.name == 'agents']
    for shared in candidates:
        if shared.is_file():
            spec = _model_import.spec_from_file_location('tlamatini_model_settings', shared)
            module = _model_import.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.resolve_agent_models('crawler', config, agent_file=__file__)
    return config


def get_python_command() -> list:
    """
    Get the command to run a Python script.
    - In Dev: Use current sys.executable (handles venvs).
    - In Frozen (Windows): Check for bundled python.exe, else fallback to 'python'.
    - In Frozen (Unix): Fallback to 'python3'.
    """
    if not getattr(sys, 'frozen', False):
        return [sys.executable]

    # Prefer PYTHON_HOME from USER environment variables
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
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()

    # Reset PyInstaller's DLL search path alteration on Windows
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes
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
    """Get the pool directory path where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Check if deployed in session: pools/<session_id>/<agent_dir>
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
                f"WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0

        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)

    if not os.path.exists(script_path):
        logging.error(f"Agent script not found: {script_path}")
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
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")

        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ============================================================
# HTML Text Extraction (legacy text mode)
# ============================================================

class HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping all markup.

    Only elements that can CONTAIN text are skipped. ``meta`` and ``link`` used
    to be in the skip list, but they are VOID elements: HTML5 writes them with
    no end tag, so the skip region they opened never closed and every modern
    page (Wikipedia, MkDocs, ...) came back with ZERO characters - the Crawler
    then dropped the page as "no text content" (seen live on 2026-09-28).
    ``head`` may be left open in HTML5 too, so it ends at the first element
    that cannot live inside a head. The page ``<title>`` becomes the first line.
    """

    SKIP_TAGS = {'script', 'style', 'noscript', 'template', 'svg', 'head'}
    #: The only elements allowed inside <head>; any other one means the body began.
    HEAD_TAGS = {'title', 'meta', 'link', 'style', 'script', 'noscript', 'base', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._pieces: List[str] = []
        self._skip: List[str] = []
        self._in_title = False
        self.title = ''

    def _leave_head(self, tag: str) -> None:
        if 'head' in self._skip and tag not in self.HEAD_TAGS:
            self._skip = [open_tag for open_tag in self._skip if open_tag != 'head']

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._in_title and tag != 'title':
            self._in_title = False          # a <title> never contains elements
        self._leave_head(tag)
        if tag == 'title':
            self._in_title = not self.title and 'svg' not in self._skip
        elif tag in self.SKIP_TAGS:
            self._skip.append(tag)

    def handle_startendtag(self, tag, attrs):
        # <x/> opens and closes at once: it can never start a skipped region.
        self._leave_head(tag.lower())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'title':
            self._in_title = False
        elif tag in self._skip:
            while self._skip and self._skip.pop() != tag:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if not self._skip:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self) -> str:
        title = ' '.join(self.title.split())
        body = '\n'.join(self._pieces)
        if title and not body.startswith(title):
            return f"{title}\n{body}" if body else title
        return body


#: Elements whose content is never visible text, for the plain fallback below.
_FALLBACK_OPEN_RE = re.compile(r'<(script|style|noscript|template|svg)\b', re.IGNORECASE)
_FALLBACK_BREAK_RE = re.compile(
    r'<(?:br|/p|/div|/li|/tr|/h[1-6]|/section|/article|/blockquote|/pre|/dd|/dt)\b[^>]*>',
    re.IGNORECASE)
_FALLBACK_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_FALLBACK_TAG_RE = re.compile(r'<[^>]*>')
#: A parse that keeps less than this share of the plain text has lost the page...
FALLBACK_MIN_SHARE = 0.25
#: ...once the page holds at least this much plain text at all.
FALLBACK_MIN_CHARS = 200


def plain_text_fallback(html_content: str) -> str:
    """Visible text by plain tag-stripping: no parser state that can get stuck.

    Script/style/noscript/template/svg blocks are dropped only when they are
    CLOSED. An unclosed one keeps everything after it, because a region that
    never closes is exactly the failure this fallback exists to survive.
    """
    markup = _FALLBACK_COMMENT_RE.sub(' ', html_content or '')
    lower = markup.lower()
    pieces, pos, never_closed = [], 0, set()
    for match in _FALLBACK_OPEN_RE.finditer(markup):
        tag = match.group(1).lower()
        if match.start() < pos or tag in never_closed:
            continue
        gt = lower.find('>', match.end())
        if gt > 0 and markup[gt - 1] == '/':
            continue                   # <svg/> opens nothing
        end = lower.find('</' + tag, match.end())
        if end < 0:
            never_closed.add(tag)      # every later one is unclosed too: never rescan
            continue
        close = lower.find('>', end)
        pieces.append(markup[pos:match.start()])
        pos = len(markup) if close < 0 else close + 1
    pieces.append(markup[pos:])
    text = _FALLBACK_BREAK_RE.sub('\n', ' '.join(pieces))
    text = _html_lib.unescape(_FALLBACK_TAG_RE.sub(' ', text))
    lines = (' '.join(line.split()) for line in text.splitlines())
    return '\n'.join(line for line in lines if line)


def strip_html(html_content: str) -> str:
    """Remove all HTML markup and return plain text.

    Two layers. The parser above does the real work; the plain tag-strip is the
    safety net. If the parser kept less than a quarter of the text the plain
    strip finds, a parser state got stuck - exactly how every page lost ALL its
    text to the void <meta>/<link> bug (2026-09-28) - so the plain text is used
    instead and the log says so. A page can never silently lose its text again.
    """
    extractor = HTMLTextExtractor()
    try:
        extractor.feed(html_content or '')
        extractor.close()
    except Exception as exc:
        logging.warning(f"The HTML parser failed ({exc}); using the plain-text fallback")
        return plain_text_fallback(html_content)
    text = extractor.get_text()
    fallback = plain_text_fallback(html_content)
    if len(fallback) >= FALLBACK_MIN_CHARS and len(text) < len(fallback) * FALLBACK_MIN_SHARE:
        logging.warning(f"The HTML parser kept only {len(text)} of {len(fallback)} characters of "
                        f"visible text; using the plain-text fallback so no text is lost")
        return fallback
    return text


# ============================================================
# Resource Extractor - Catalogs all page resources for developers
# ============================================================

class ResourceExtractor(HTMLParser):
    """
    Developer-oriented HTML parser that extracts a structured inventory of all
    page resources: inline scripts, inline styles, external scripts, stylesheets,
    meta tags, forms, APIs/endpoints, images, iframes, data attributes, etc.
    """

    def __init__(self, base_url: str):
        super().__init__()
        self._base_url = base_url
        self.inline_scripts: List[str] = []
        self.inline_styles: List[str] = []
        self.external_scripts: List[str] = []
        self.stylesheets: List[str] = []
        self.meta_tags: List[Dict[str, str]] = []
        self.images: List[Dict[str, str]] = []
        self.links: List[Dict[str, str]] = []
        self.forms: List[Dict[str, str]] = []
        self.iframes: List[str] = []
        self.data_attributes: List[Dict[str, str]] = []
        self.json_ld: List[str] = []
        self.preloads: List[Dict[str, str]] = []
        self._current_tag: Optional[str] = None
        self._current_attrs: Dict[str, str] = {}
        self._capture_buffer: List[str] = []
        self._capture_tags = {'script', 'style'}

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attrs_dict = dict(attrs)

        if tag_lower in self._capture_tags:
            self._current_tag = tag_lower
            self._current_attrs = attrs_dict
            self._capture_buffer = []

        if tag_lower == 'script' and 'src' in attrs_dict:
            src = urljoin(self._base_url, attrs_dict['src'])
            self.external_scripts.append(src)

        elif tag_lower == 'link':
            rel = attrs_dict.get('rel', '').lower()
            href = attrs_dict.get('href', '')
            if href:
                abs_href = urljoin(self._base_url, href)
                if 'stylesheet' in rel:
                    self.stylesheets.append(abs_href)
                elif 'preload' in rel or 'prefetch' in rel or 'modulepreload' in rel:
                    self.preloads.append({'rel': rel, 'href': abs_href, 'as': attrs_dict.get('as', '')})
                self.links.append({'rel': rel, 'href': abs_href, 'type': attrs_dict.get('type', '')})

        elif tag_lower == 'meta':
            meta_entry = {}
            for key in ('name', 'property', 'http-equiv', 'charset', 'content'):
                if key in attrs_dict:
                    meta_entry[key] = attrs_dict[key]
            if meta_entry:
                self.meta_tags.append(meta_entry)

        elif tag_lower == 'img':
            img_entry = {'src': urljoin(self._base_url, attrs_dict.get('src', ''))}
            if 'alt' in attrs_dict:
                img_entry['alt'] = attrs_dict['alt']
            if 'srcset' in attrs_dict:
                img_entry['srcset'] = attrs_dict['srcset']
            if 'loading' in attrs_dict:
                img_entry['loading'] = attrs_dict['loading']
            self.images.append(img_entry)

        elif tag_lower == 'form':
            form_entry = {
                'action': urljoin(self._base_url, attrs_dict.get('action', '')),
                'method': attrs_dict.get('method', 'GET').upper(),
            }
            if 'id' in attrs_dict:
                form_entry['id'] = attrs_dict['id']
            if 'name' in attrs_dict:
                form_entry['name'] = attrs_dict['name']
            self.forms.append(form_entry)

        elif tag_lower == 'iframe':
            src = attrs_dict.get('src', '')
            if src:
                self.iframes.append(urljoin(self._base_url, src))

        # Capture data-* attributes from any tag
        data_attrs = {k: v for k, v in attrs_dict.items() if k.startswith('data-')}
        if data_attrs:
            self.data_attributes.append({
                'tag': tag_lower,
                'id': attrs_dict.get('id', ''),
                'attrs': data_attrs
            })

    def handle_data(self, data):
        if self._current_tag in self._capture_tags:
            self._capture_buffer.append(data)

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == self._current_tag:
            content = ''.join(self._capture_buffer).strip()
            if content:
                if tag_lower == 'script':
                    script_type = self._current_attrs.get('type', '').lower()
                    if script_type == 'application/ld+json':
                        self.json_ld.append(content)
                    else:
                        self.inline_scripts.append(content)
                elif tag_lower == 'style':
                    self.inline_styles.append(content)
            self._current_tag = None
            self._current_attrs = {}
            self._capture_buffer = []

    def get_resource_summary(self) -> str:
        """Build a structured text summary of all discovered resources."""
        sections = []

        if self.meta_tags:
            lines = ["=== META TAGS ==="]
            for m in self.meta_tags:
                parts = [f"{k}={v}" for k, v in m.items()]
                lines.append(f"  {' | '.join(parts)}")
            sections.append('\n'.join(lines))

        if self.external_scripts:
            lines = ["=== EXTERNAL SCRIPTS ==="]
            for s in self.external_scripts:
                lines.append(f"  {s}")
            sections.append('\n'.join(lines))

        if self.inline_scripts:
            lines = [f"=== INLINE SCRIPTS ({len(self.inline_scripts)} blocks) ==="]
            for i, s in enumerate(self.inline_scripts):
                lines.append(f"--- inline script #{i + 1} ({len(s)} chars) ---")
                lines.append(s)
            sections.append('\n'.join(lines))

        if self.stylesheets:
            lines = ["=== EXTERNAL STYLESHEETS ==="]
            for s in self.stylesheets:
                lines.append(f"  {s}")
            sections.append('\n'.join(lines))

        if self.inline_styles:
            lines = [f"=== INLINE STYLES ({len(self.inline_styles)} blocks) ==="]
            for i, s in enumerate(self.inline_styles):
                lines.append(f"--- inline style #{i + 1} ({len(s)} chars) ---")
                lines.append(s)
            sections.append('\n'.join(lines))

        if self.forms:
            lines = ["=== FORMS ==="]
            for f in self.forms:
                parts = [f"{k}={v}" for k, v in f.items()]
                lines.append(f"  {' | '.join(parts)}")
            sections.append('\n'.join(lines))

        if self.images:
            lines = [f"=== IMAGES ({len(self.images)}) ==="]
            for img in self.images[:50]:
                lines.append(f"  {img.get('src', '')} alt=\"{img.get('alt', '')}\"")
            if len(self.images) > 50:
                lines.append(f"  ... and {len(self.images) - 50} more")
            sections.append('\n'.join(lines))

        if self.iframes:
            lines = ["=== IFRAMES ==="]
            for iframe in self.iframes:
                lines.append(f"  {iframe}")
            sections.append('\n'.join(lines))

        if self.json_ld:
            lines = ["=== JSON-LD STRUCTURED DATA ==="]
            for j in self.json_ld:
                lines.append(j)
            sections.append('\n'.join(lines))

        if self.preloads:
            lines = ["=== PRELOADS / PREFETCHES ==="]
            for p in self.preloads:
                lines.append(f"  {p['rel']} -> {p['href']} (as={p['as']})")
            sections.append('\n'.join(lines))

        if self.data_attributes:
            lines = [f"=== DATA ATTRIBUTES ({len(self.data_attributes)} elements) ==="]
            for d in self.data_attributes[:30]:
                tag_id = f" id={d['id']}" if d['id'] else ""
                attrs_str = ' '.join(f"{k}=\"{v}\"" for k, v in d['attrs'].items())
                lines.append(f"  <{d['tag']}{tag_id}> {attrs_str}")
            if len(self.data_attributes) > 30:
                lines.append(f"  ... and {len(self.data_attributes) - 30} more")
            sections.append('\n'.join(lines))

        return '\n\n'.join(sections)


def extract_api_endpoints(html_content: str) -> List[str]:
    """
    Scan raw HTML/JS content for patterns that look like API endpoints,
    fetch URLs, WebSocket URLs, or REST paths. Developer gold.
    """
    patterns = [
        # fetch/axios/XMLHttpRequest URL strings
        r'''(?:fetch|axios\.(?:get|post|put|delete|patch)|\.open)\s*\(\s*[`'"](https?://[^`'"]+)[`'"]''',
        # URL string assignments
        r'''(?:url|endpoint|api_url|apiUrl|baseUrl|BASE_URL|API_BASE)\s*[:=]\s*[`'"](https?://[^`'"]+)[`'"]''',
        # Relative API paths  /api/... or /v1/... or /v2/...
        r'''[`'"](/(?:api|v[0-9]+|graphql|rest|ws)/[^`'"]*)[`'"]''',
        # WebSocket URLs
        r'''[`'"](wss?://[^`'"]+)[`'"]''',
    ]
    endpoints = set()
    for pat in patterns:
        for match in re.finditer(pat, html_content, re.IGNORECASE):
            endpoints.add(match.group(1))
    return sorted(endpoints)


# ============================================================
# Recon / Safety helpers (seed list, page budget, robots,
# binary guard, recon extraction)
# ============================================================

_CRAWLER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)

# Content-Types / extensions that must NOT be decoded-as-text and fed to the LLM.
_BINARY_CONTENT_TYPES = {
    'application/pdf', 'application/octet-stream',
    'application/zip', 'application/gzip',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument',
}
_BINARY_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.exe', '.dmg',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
}


def _is_binary_for_llm(content_type: str, url: str) -> bool:
    """True when the response is binary (image/pdf/archive/...) and should be skipped
    rather than decoded-as-text and shoved into the LLM context."""
    ct = (content_type or '').lower().split(';')[0].strip()
    if ct in _BINARY_CONTENT_TYPES or 'officedocument' in ct:
        return True
    if ct.startswith(('image/', 'audio/', 'video/')):
        return True
    path = urlparse(url or '').path.lower().split('?')[0]
    return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)


def _collect_seed_urls(config: Dict) -> List[str]:
    """Merge the single ``url`` plus an optional ``urls`` list (or comma/space-separated
    string) into an ordered, de-duplicated list of http(s) seeds. Lets a Googler dork
    hit-list flow straight into the Crawler via the Parametrizer."""
    seeds: List[str] = []
    seen = set()

    def _add(value):
        u = str(value or '').strip()
        if not u or not u.lower().startswith(('http://', 'https://')):
            return
        if u in seen:
            return
        seen.add(u)
        seeds.append(u)

    _add(config.get('url', ''))
    extra = config.get('urls', [])
    if isinstance(extra, str):
        extra = [t for t in re.split(r'[,\s]+', extra) if t]
    if isinstance(extra, (list, tuple)):
        for value in extra:
            _add(value)
    return seeds


def _fetch_robots_txt(base_url: str, timeout: int = 10) -> Optional[str]:
    """Fetch ``<scheme>://<host>/robots.txt``. Returns its text, or None on any failure
    (caller fails OPEN: no robots == allowed)."""
    robots_url = base_url.rstrip('/') + '/robots.txt'
    try:
        req = urllib.request.Request(robots_url, headers={'User-Agent': _CRAWLER_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.getcode() != 200:
                return None
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None


class CrawlBudget:
    """Bounds and politeness for a crawl run: a hard ``max_pages`` cap (0 = unlimited),
    a whole-crawl ``deadline_seconds`` (0 = none), an inter-request ``delay_seconds``,
    and optional ``robots.txt`` enforcement (per-host, cached, fail-open). Without
    these, ``large-range`` crawling is unbounded.

    It also RECORDS what happened to every page (``ok``, ``blocked``, ``timeout``,
    ``unreachable``, ``not_found``, ``error`` or ``skipped``), so a crawl that
    delivered nothing says exactly why instead of ending in silence."""

    def __init__(self, max_pages=0, delay_seconds=0, respect_robots=False,
                 user_agent: str = _CRAWLER_UA, deadline_seconds=0):
        try:
            self.max_pages = max(0, int(max_pages or 0))
        except (TypeError, ValueError):
            self.max_pages = 0
        try:
            self.delay_seconds = max(0.0, float(delay_seconds or 0))
        except (TypeError, ValueError):
            self.delay_seconds = 0.0
        try:
            self.deadline_seconds = max(0.0, float(deadline_seconds or 0))
        except (TypeError, ValueError):
            self.deadline_seconds = 0.0
        self.deadline_at = (time.monotonic() + self.deadline_seconds
                            if self.deadline_seconds > 0 else None)
        self.respect_robots = bool(respect_robots)
        self.user_agent = user_agent or _CRAWLER_UA
        self.processed = 0
        self.outcomes: List[Tuple[str, str, str]] = []
        self._deadline_announced = False
        self._robots_cache: Dict[str, Optional[RobotFileParser]] = {}

    def remaining(self) -> Optional[int]:
        if self.max_pages == 0:
            return None  # unlimited
        return max(0, self.max_pages - self.processed)

    def time_left(self) -> Optional[float]:
        """Seconds until the crawl deadline, or None when there is none."""
        if self.deadline_at is None:
            return None
        return self.deadline_at - time.monotonic()

    def deadline_passed(self) -> bool:
        left = self.time_left()
        return left is not None and left <= 0

    def exhausted(self) -> bool:
        if self.deadline_passed():
            if not self._deadline_announced:
                self._deadline_announced = True
                logging.warning(f"Crawl deadline ({self.deadline_seconds:.0f}s) reached after "
                                f"{self.processed} page(s); stopping cleanly.")
            return True
        return self.max_pages != 0 and self.processed >= self.max_pages

    def stop_reason(self) -> str:
        if self.deadline_passed():
            return f"crawl deadline of {self.deadline_seconds:.0f}s reached"
        return f"page budget reached ({self.processed}/{self.max_pages})"

    def page_timeout(self, configured: float) -> float:
        """``configured`` seconds EXACTLY, never past the deadline (a page begun near it still gets 5 s)."""
        left = self.time_left()
        if left is None:
            return configured
        return min(configured, max(5.0, left))

    def note_processed(self) -> None:
        self.processed += 1

    def record(self, url: str, result) -> None:
        """Remember one page's outcome. A caller that returns nothing (``None``)
        counts as ``ok``, so older callers keep working."""
        if isinstance(result, tuple) and result:
            outcome = str(result[0] or 'ok')
            detail = str(result[1]) if len(result) > 1 else url
        else:
            outcome, detail = 'ok', url
        self.outcomes.append((url, outcome, detail))

    def count(self, outcome: str) -> int:
        return sum(1 for _url, got, _detail in self.outcomes if got == outcome)

    def wait(self) -> None:
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

    def robots_allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if not netloc:
            return True
        if netloc not in self._robots_cache:
            base = f"{parsed.scheme}://{parsed.netloc}"
            text = _fetch_robots_txt(base)
            parser = None
            if text is not None:
                parser = RobotFileParser()
                parser.parse(text.splitlines())
            self._robots_cache[netloc] = parser
        parser = self._robots_cache[netloc]
        if parser is None:
            return True  # fail-open: couldn't fetch robots.txt
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True


# --- Recon extraction (emails, HTML comments, secrets, source-map refs) ------

_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_COMMENT_RE = re.compile(r'<!--(.*?)-->', re.DOTALL)
_SOURCEMAP_RE = re.compile(
    r'(?://[#@]\s*sourceMappingURL=\s*(\S+))|(\S+\.js\.map)', re.IGNORECASE
)
_SECRET_PATTERNS = (
    ('aws_access_key_id', re.compile(r'AKIA[0-9A-Z]{16}')),
    ('google_api_key', re.compile(r'AIza[0-9A-Za-z_\-]{35}')),
    ('slack_token', re.compile(r'xox[baprs]-[0-9A-Za-z\-]{10,}')),
    ('github_token', re.compile(r'gh[pousr]_[0-9A-Za-z]{20,}')),
    ('private_key', re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----')),
    ('bearer_token', re.compile(r'(?i)bearer\s+[A-Za-z0-9._\-]{20,}')),
    ('generic_secret_assignment', re.compile(
        r'(?i)(?:api[_-]?key|secret|passwd|password|token)["\']?\s*[:=]\s*["\']([^"\']{8,})["\']'
    )),
)


def extract_recon_findings(content: str) -> Dict[str, List[str]]:
    """Scan raw page/JS source for recon-relevant artifacts: email addresses, HTML
    comments, source-map references, and likely secrets / API keys. Each category is
    de-duplicated and capped. Pure function — no I/O — so it is trivially testable."""
    content = content or ''

    emails = sorted(set(_EMAIL_RE.findall(content)))

    comments: List[str] = []
    seen_comments = set()
    for match in _COMMENT_RE.findall(content):
        normalized = ' '.join(match.split()).strip()
        if normalized and normalized not in seen_comments:
            seen_comments.add(normalized)
            comments.append(normalized)

    source_maps = sorted({
        (g1 or g2) for g1, g2 in _SOURCEMAP_RE.findall(content) if (g1 or g2)
    })

    secrets: List[str] = []
    seen_secrets = set()
    for name, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(content):
            value = match.group(0)
            key = f"{name}|{value}"
            if key in seen_secrets:
                continue
            seen_secrets.add(key)
            secrets.append(f"{name}: {value}")

    return {
        'emails': emails[:100],
        'comments': comments[:50],
        'source_maps': source_maps[:50],
        'secrets': secrets[:50],
    }


def format_recon_summary(findings: Dict[str, List[str]]) -> str:
    """Render recon findings as a labeled text block (empty categories omitted).
    Returns '' when nothing was found."""
    sections = []
    order = (
        ('secrets', 'POTENTIAL SECRETS / API KEYS'),
        ('emails', 'EMAIL ADDRESSES'),
        ('source_maps', 'SOURCE MAP REFERENCES'),
        ('comments', 'HTML COMMENTS'),
    )
    for key, title in order:
        items = findings.get(key) or []
        if not items:
            continue
        lines = [f"=== RECON: {title} ({len(items)}) ==="]
        lines.extend(f"  {item}" for item in items)
        sections.append('\n'.join(lines))
    return '\n\n'.join(sections)


# ============================================================
# URL Fetching - Enhanced with full HTTP response capture
# ============================================================

#: Wall-clock budget for ONE page: connect + headers + body. A per-socket
#: timeout alone bounds nothing (a server that dribbles a byte every few seconds
#: resets it forever), so the whole fetch runs on a worker thread that is
#: abandoned at this limit.
PAGE_TIMEOUT_SECONDS = 45.0
#: The most bytes read from one page; the rest is cut off, and that is logged.
MAX_PAGE_BYTES = 8 * 1024 * 1024


class FetchError(RuntimeError):
    """A fetch that produced no usable page: a timeout, a network error, or an HTTP
    status >= 400. It keeps what the server DID say (status, headers, a body
    excerpt), so the caller can tell a bot wall from a dead link."""

    def __init__(self, message: str, status_code: int = 0, body: str = '',
                 headers: Optional[Dict[str, str]] = None, timed_out: bool = False,
                 network: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.timed_out = timed_out
        self.network = network


def _header_value(headers: Dict[str, str], name: str, default: str = '') -> str:
    """HTTP header names are case-insensitive; a plain dict lookup is not.
    Wikipedia sends ``content-type`` in lower case, so ``headers.get('Content-Type')``
    answered "unknown" and the binary guard went blind (2026-09-28)."""
    wanted = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == wanted:
            return value
    return default


def _decode_body(raw: bytes, content_encoding: str, charset: Optional[str]) -> str:
    """Decompress (a truncated stream still yields what arrived) and decode."""
    encoding = (content_encoding or '').lower()
    try:
        if encoding == 'gzip':
            raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
        elif encoding == 'deflate':
            try:
                raw = zlib.decompressobj().decompress(raw)
            except zlib.error:
                raw = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw)
    except zlib.error:
        pass
    try:
        return raw.decode(charset or 'utf-8', errors='replace')
    except LookupError:
        return raw.decode('utf-8', errors='replace')


def _fetch_worker(req, socket_timeout: float, max_bytes: int, box: Dict) -> None:
    """Runs on a daemon thread and writes everything it learns into ``box``."""
    try:
        with urllib.request.urlopen(req, timeout=socket_timeout) as resp:
            box['status_code'] = resp.getcode()
            box['headers'] = dict(resp.headers.items())
            box['encoding'] = resp.headers.get('Content-Encoding', '')
            box['charset'] = resp.headers.get_content_charset()
            read_some = getattr(resp, 'read1', None) or resp.read
            chunks, total = [], 0
            while total < max_bytes and not box.get('abandoned'):
                chunk = read_some(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            box['truncated'] = total >= max_bytes
            box['raw'] = b''.join(chunks)[:max_bytes]
    except urllib.error.HTTPError as e:
        headers = e.headers
        box['status_code'] = e.code
        box['headers'] = dict(headers.items()) if headers else {}
        box['encoding'] = headers.get('Content-Encoding', '') if headers else ''
        box['charset'] = headers.get_content_charset() if headers else None
        try:
            box['raw'] = e.read(256 * 1024) or b''
        except Exception:
            box['raw'] = b''
        box['http_error'] = f"HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        box['error'] = f"cannot reach the site: {e.reason}"
        box['timed_out'] = isinstance(e.reason, TimeoutError)
        box['network'] = True
    except TimeoutError as e:
        box['error'] = f"the server stopped answering ({e})"
        box['timed_out'] = True
    except OSError as e:
        box['error'] = f"{type(e).__name__}: {e}"
        box['network'] = True
    except Exception as e:
        box['error'] = f"{type(e).__name__}: {e}"


def fetch_page_raw(url: str, include_headers: bool = True, timeout: int = 60, *,
                   page_timeout: Optional[float] = None,
                   max_bytes: int = MAX_PAGE_BYTES) -> Tuple[str, Dict[str, str], int]:
    """
    Fetch a web page via HTTP GET and return:
      - raw_body: the complete decoded response body (HTML/JS/CSS/JSON/everything)
      - headers: dict of HTTP response headers
      - status_code: HTTP status code

    Handles gzip/deflate encoding transparently. It NEVER hangs: the whole fetch
    is bounded by ``page_timeout`` (default PAGE_TIMEOUT_SECONDS) and at most
    ``max_bytes`` are read. Raises FetchError on a timeout, a network error or
    an HTTP status >= 400.
    """
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': _CRAWLER_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
                      'application/json,text/javascript,text/css,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, identity',
        }
    )
    limit = max(1.0, float(PAGE_TIMEOUT_SECONDS if page_timeout is None else page_timeout))
    box: Dict = {}
    worker = threading.Thread(target=_fetch_worker,
                              args=(req, min(float(timeout), limit), int(max_bytes), box),
                              daemon=True)
    worker.start()
    worker.join(limit)
    if worker.is_alive():
        box['abandoned'] = True
        raise FetchError(f"no complete page after {limit:.0f}s (the server kept the "
                         f"connection open without finishing)", timed_out=True)
    if box.get('error'):
        raise FetchError(box['error'], timed_out=bool(box.get('timed_out')),
                         network=bool(box.get('network')))
    headers = box.get('headers') or {}
    body = _decode_body(box.get('raw') or b'', box.get('encoding', ''), box.get('charset'))
    status_code = int(box.get('status_code') or 0)
    if box.get('http_error'):
        raise FetchError(box['http_error'], status_code=status_code, body=body,
                         headers=headers)
    if box.get('truncated'):
        logging.warning(f"Page larger than {int(max_bytes)} bytes; analyzing only the "
                        f"first {int(max_bytes)} bytes of {url}")
    return body, (headers if include_headers else {}), status_code


#: Words that mark a bot wall / challenge page instead of the page asked for.
#: Checked ONLY on short pages: a real article may well mention "captcha".
_BLOCK_MARKERS = (
    ('just a moment...', 'Cloudflare browser check'),
    ('attention required! | cloudflare', 'Cloudflare block page'),
    ('cf-chl', 'Cloudflare challenge'),
    ('checking your browser', 'browser check'),
    ('verify you are human', 'human verification'),
    ('are you a robot', 'bot check'),
    ('pardon our interruption', 'bot check'),
    ('unusual traffic', 'unusual-traffic block'),
    ('captcha', 'CAPTCHA'),
    ('access denied', 'access denied'),
    ('enable javascript and cookies to continue', 'JavaScript/cookie wall'),
    ('ddos protection by', 'DDoS-protection wall'),
    ('request unsuccessful. incapsula', 'Incapsula block'),
)
#: A challenge page is small; above this much visible text it is real content.
_BLOCK_TEXT_LIMIT = 1500


def detect_block(status_code: int, body: str, text: Optional[str] = None) -> Optional[str]:
    """Why this response is a REFUSAL rather than the page, or None.

    401 / 403 / 429 always are. Any other page counts only when it is short AND
    carries a bot-wall marker, so an article that merely mentions "captcha" is
    never thrown away."""
    if status_code in (401, 403):
        return f"HTTP {status_code}: the site refused this request"
    if status_code == 429:
        return "HTTP 429: rate limited (too many requests)"
    visible = strip_html(body or '') if text is None else text
    if len(visible) > _BLOCK_TEXT_LIMIT:
        return None
    sample = (visible + '\n' + (body or '')[:8000]).lower()
    for marker, reason in _BLOCK_MARKERS:
        if marker in sample:
            prefix = f"HTTP {status_code}: " if status_code and status_code >= 400 else ''
            return f"{prefix}{reason} page instead of the content"
    return None


def _retry_after_seconds(value) -> Optional[float]:
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def _fetch_with_retry(url: str, page_timeout: Optional[float], max_bytes: int):
    """Fetch once; when the server answers 429/503 with a short ``Retry-After``,
    wait exactly that long and try ONE more time - never a hammering loop."""
    try:
        return fetch_page_raw(url, include_headers=True, page_timeout=page_timeout,
                              max_bytes=max_bytes)
    except FetchError as e:
        if e.status_code not in (429, 503):
            raise
        wait = _retry_after_seconds(_header_value(e.headers, 'Retry-After'))
        if wait is None or wait > 20 or _crawl_time_left() < wait + 10:
            raise
        logging.info(f"HTTP {e.status_code} from {url}; waiting {wait:.0f}s as the server "
                     f"asked, then ONE retry")
        time.sleep(wait)
        return fetch_page_raw(url, include_headers=True, page_timeout=page_timeout,
                              max_bytes=max_bytes)


#: The HTML of the page analyzed last, kept for ONE reuse: a *-range crawl reads
#: its seed's links right after analyzing the seed, without downloading it twice.
_PAGE_CACHE: Dict[str, str] = {}


def fetch_page(url: str) -> str:
    """Legacy: Fetch a web page and return its raw HTML content."""
    cached = _PAGE_CACHE.pop(url, None)
    if cached is not None:
        return cached
    body, _, _ = fetch_page_raw(url, include_headers=False)
    return body


def extract_links(html_content: str, base_url: str) -> List[str]:
    """Extract all href links from HTML content and resolve them to absolute URLs."""
    pattern = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\']', re.IGNORECASE)
    links = set()
    for match in pattern.finditer(html_content):
        href = match.group(1).strip()
        if href.startswith(('mailto:', 'javascript:', 'tel:')):
            continue
        absolute = urljoin(base_url, href)
        links.add(absolute)
    return sorted(links)


def filter_same_domain(links: List[str], base_url: str) -> List[str]:
    """Filter links to only include those in the same domain as the base URL."""
    base_domain = urlparse(base_url).netloc.lower()
    return [link for link in links if urlparse(link).netloc.lower() == base_domain]


# ============================================================
# LLM Query — with automatic context window detection
# ============================================================

# Cache for model context size (avoids repeated API calls)
_model_ctx_cache: Dict[str, int] = {}


def get_model_context_size(host: str, model: str) -> int:
    """
    Query Ollama's /api/show endpoint to get the model's actual context window
    size (num_ctx) in tokens. Returns the number of tokens the model supports.
    Falls back to 8192 if the API call fails.
    """
    cache_key = f"{host}|{model}"
    if cache_key in _model_ctx_cache:
        return _model_ctx_cache[cache_key]

    url = f"{host.rstrip('/')}/api/show"
    payload = json.dumps({"name": model}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    fallback = 8192
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Ollama returns model info with parameters or model_info
        # Try model_info first (newer Ollama versions)
        model_info = data.get("model_info", {})
        for key, value in model_info.items():
            if "context_length" in key.lower():
                ctx = int(value)
                _model_ctx_cache[cache_key] = ctx
                logging.info(f"Model '{model}' context window: {ctx} tokens (from model_info)")
                return ctx

        # Try parsing from parameters string (older Ollama)
        params_str = data.get("parameters", "")
        if params_str:
            for line in params_str.split('\n'):
                line = line.strip()
                if line.startswith("num_ctx"):
                    parts = line.split()
                    if len(parts) >= 2:
                        ctx = int(parts[-1])
                        _model_ctx_cache[cache_key] = ctx
                        logging.info(f"Model '{model}' context window: {ctx} tokens (from parameters)")
                        return ctx

        # Try template/details for context hints
        details = data.get("details", {})
        family = details.get("family", "").lower()

        # Known defaults for common model families
        family_defaults = {
            "llama": 131072, "qwen": 131072, "qwen2": 131072,
            "gemma": 8192, "mistral": 32768, "mixtral": 32768,
            "phi": 131072, "command-r": 131072, "deepseek": 65536,
        }
        for fam_name, fam_ctx in family_defaults.items():
            if fam_name in family:
                _model_ctx_cache[cache_key] = fam_ctx
                logging.info(f"Model '{model}' context window: {fam_ctx} tokens (family default for '{family}')")
                return fam_ctx

        logging.warning(f"Could not determine context size for '{model}', using fallback {fallback}")
        _model_ctx_cache[cache_key] = fallback
        return fallback

    except Exception as e:
        logging.warning(f"Failed to query model info for '{model}': {e}. Using fallback {fallback}")
        _model_ctx_cache[cache_key] = fallback
        return fallback


def tokens_to_chars(num_tokens: int) -> int:
    """Convert token count to approximate character count. ~3.5 chars per token is conservative."""
    return int(num_tokens * 3.5)


#: time.monotonic() instant by which the whole crawl must end, or None. Set by
#: crawl(); no LLM call waits much past it and no retry sleeps past it.
_CRAWL_DEADLINE: Optional[float] = None
#: Longest a single LLM call may take when no crawl deadline is closer.
LLM_TIMEOUT_SECONDS = 300.0


def _crawl_time_left() -> float:
    if _CRAWL_DEADLINE is None:
        return float('inf')
    return _CRAWL_DEADLINE - time.monotonic()


def _llm_timeout() -> float:
    """300 s per call, but never much past the crawl deadline (30 s of grace)."""
    return max(20.0, min(LLM_TIMEOUT_SECONDS, _crawl_time_left() + 30.0))


def query_ollama(host: str, model: str, system_prompt: str, context: str) -> str:
    """
    Send a prompt to an Ollama LLM with a system prompt and context,
    and return the full response text.
    Uses the 'system' field so the LLM treats the prompt with proper priority,
    separate from the content/context which goes in 'prompt'.

    Every failure is raised as RuntimeError - including a timeout, which used to
    escape as a bare socket error and abort the WHOLE crawl.
    """
    url = f"{host.rstrip('/')}/api/generate"

    payload = json.dumps({
        "model": model,
        "system": system_prompt,
        "prompt": f"--- BEGIN CONTENT ---\n{context}\n--- END CONTENT ---",
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    timeout = _llm_timeout()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e
    except TimeoutError as e:
        raise RuntimeError(f"Ollama did not answer within {timeout:.0f}s") from e
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Ollama call failed: {type(e).__name__}: {e}") from e


# ============================================================
# Developer-oriented LLM context builder
# ============================================================

DEV_RAW_PREAMBLE = (
    "You are a Tlamatini web analysis agent analyzing RAW web page content captured for a DEVELOPER audience. "
    "The content below contains the COMPLETE HTTP response including full HTML markup, "
    "inline JavaScript, CSS styles, meta tags, data attributes, JSON-LD structured data, "
    "and all other source code exactly as served by the web server.\n\n"
    "IMPORTANT: This is a developer tool. Analyze EVERYTHING — do not skip code sections. "
    "Pay special attention to:\n"
    "- JavaScript logic, API calls, fetch/XHR endpoints, WebSocket connections\n"
    "- HTML structure, semantic elements, accessibility attributes, forms and their actions\n"
    "- CSS classes, custom properties, responsive breakpoints, animations\n"
    "- Meta tags (SEO, Open Graph, Twitter cards, viewport, CSP headers)\n"
    "- Data attributes (data-*) that may drive frontend behavior\n"
    "- JSON-LD structured data and schema.org markup\n"
    "- Third-party scripts, tracking pixels, analytics integrations\n"
    "- Security-relevant patterns: CSP, CORS, cookie attributes, auth flows\n"
    "- Framework signatures (React, Vue, Angular, Next.js, etc.)\n"
    "- Build tool artifacts (webpack chunks, source maps references)\n\n"
)

DEV_RESOURCE_PREAMBLE = (
    "Additionally, a RESOURCE INVENTORY has been extracted listing all external scripts, "
    "stylesheets, images, forms, iframes, API endpoints discovered in the source, and "
    "data-* attributes. Use this inventory for a complete picture of the page's dependencies "
    "and integrations.\n\n"
)


def chunk_content(content: str, chunk_size: int) -> List[str]:
    """
    Split content into chunks of at most chunk_size characters.
    Tries to break at newline boundaries to avoid splitting mid-tag/mid-line.
    """
    if chunk_size <= 0 or len(content) <= chunk_size:
        return [content]

    chunks = []
    start = 0
    total = len(content)

    while start < total:
        end = start + chunk_size

        if end >= total:
            chunks.append(content[start:])
            break

        # Try to find a newline near the end to break cleanly
        search_start = max(start, end - chunk_size // 5)
        last_newline = content.rfind('\n', search_start, end)

        if last_newline > start:
            end = last_newline + 1

        chunks.append(content[start:end])
        start = end

    return chunks


def build_full_content(page_url: str, raw_html: str, headers: Dict[str, str],
                       status_code: int, resource_summary: str,
                       api_endpoints: List[str]) -> str:
    """
    Build one single flat string with ALL the page content:
    metadata + resource inventory + raw HTML.
    This is the full content that will be chunked.
    """
    sections = []

    sections.append(f"=== HTTP RESPONSE METADATA ===\nURL: {page_url}\nStatus: {status_code}")

    if headers:
        header_lines = [f"  {k}: {v}" for k, v in headers.items()]
        sections.append("=== HTTP RESPONSE HEADERS ===\n" + '\n'.join(header_lines))

    if api_endpoints:
        ep_lines = ["=== DISCOVERED API ENDPOINTS ==="]
        for ep in api_endpoints:
            ep_lines.append(f"  {ep}")
        sections.append('\n'.join(ep_lines))

    if resource_summary:
        sections.append(resource_summary)

    sections.append(f"=== RAW HTML SOURCE ({len(raw_html)} chars) ===\n{raw_html}")

    return '\n\n'.join(sections)


# ============================================================
# Core Crawl Logic
# ============================================================

def save_crawled_content(text: str, crawl_type: str, timestamp: str,
                         suffix: str = "") -> str:
    """Save crawled content to a local file and return the file path."""
    tag = f"_{suffix}" if suffix else ""
    filename = f"crawled_{crawl_type}_{timestamp}{tag}.txt"
    filepath = os.path.join(script_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text)
    return filepath


def query_ollama_chunked(host: str, model: str, system_prompt: str,
                         full_content: str, page_url: str) -> str:
    """
    Automatically chunk content based on the model's real context window.

    1. Queries Ollama /api/show to get the model's num_ctx (context tokens).
    2. Calculates max chars per request = (num_ctx * 3.5) - system_prompt_chars - safety_margin.
    3. If content fits in one request, sends it directly.
    4. If not, splits into N chunks, sends each with a per-chunk instruction,
       then runs a final synthesis query to merge all partial responses.

    NEVER drops or ignores any content — every character is processed.
    """
    # Step 1: Get the model's real context window from Ollama
    ctx_tokens = get_model_context_size(host, model)
    ctx_chars = tokens_to_chars(ctx_tokens)

    # Reserve space for: system prompt + chunk header + response generation
    # Use 75% of context for input (prompt + context), leave 25% for response
    input_budget_chars = int(ctx_chars * 0.75)
    system_prompt_chars = len(system_prompt)
    # Extra overhead for chunk instructions + delimiters
    overhead_chars = 500
    content_budget = input_budget_chars - system_prompt_chars - overhead_chars

    if content_budget < 1000:
        logging.warning(
            f"Model context ({ctx_tokens} tokens / ~{ctx_chars} chars) is very small. "
            f"System prompt uses {system_prompt_chars} chars. Content budget: {content_budget} chars."
        )
        content_budget = max(1000, ctx_chars // 2)

    logging.info(
        f"Model context: {ctx_tokens} tokens (~{ctx_chars} chars), "
        f"content budget per chunk: {content_budget} chars"
    )

    # Step 2: Check if content fits in a single request
    if len(full_content) <= content_budget:
        logging.info(f"Content fits in one request ({len(full_content)} <= {content_budget} chars)")
        return query_ollama(host, model, system_prompt, full_content)

    # Step 3: Split into chunks
    content_chunks = chunk_content(full_content, content_budget)
    total_chunks = len(content_chunks)
    logging.info(
        f"Content ({len(full_content)} chars) split into {total_chunks} chunks "
        f"(budget: {content_budget} chars/chunk, model ctx: {ctx_tokens} tokens)"
    )

    # Step 4: Send each chunk — user's prompt is the PRIMARY instruction
    partial_responses = []

    for i, chunk in enumerate(content_chunks):
        chunk_num = i + 1
        logging.info(
            f"Sending chunk {chunk_num}/{total_chunks} to LLM "
            f"({len(chunk)} chars) for {page_url}"
        )

        # User's prompt goes FIRST and is the main task.
        # Chunk note is minimal and secondary.
        chunk_system_prompt = (
            f"{system_prompt}\n\n"
            f"[Chunked input: this is part {chunk_num}/{total_chunks} of {page_url}. "
            f"Apply the task above to THIS part.]"
        )

        try:
            partial = query_ollama(host, model, chunk_system_prompt, chunk)
            partial_responses.append(
                f"--- Part {chunk_num}/{total_chunks} ---\n{partial}"
            )
            logging.info(f"Chunk {chunk_num}/{total_chunks} OK ({len(partial)} chars response)")
        except RuntimeError as e:
            logging.error(f"LLM failed for chunk {chunk_num}/{total_chunks}: {e}")
            partial_responses.append(
                f"--- Part {chunk_num}/{total_chunks} ---\n[ERROR: {e}]"
            )

    # Step 5: Synthesize — user's prompt remains the PRIMARY task
    logging.info(f"Synthesizing {len(partial_responses)} chunk responses for {page_url}")

    synthesis_context = "\n\n".join(partial_responses)

    # The synthesis itself might also exceed context — chunk recursively if needed
    if len(synthesis_context) > content_budget:
        logging.info(
            f"Synthesis context ({len(synthesis_context)} chars) exceeds budget, "
            f"using recursive chunked synthesis"
        )
        synthesis_prompt = (
            f"{system_prompt}\n\n"
            f"The results above are partial outputs from processing {page_url} in parts. "
            f"Merge them into one final answer for the task above. Keep ALL details, remove duplicates."
        )
        return query_ollama_chunked(
            host, model, synthesis_prompt, synthesis_context, page_url
        )

    # User's prompt is FIRST — it's the task. Merge instruction is secondary.
    synthesis_prompt = (
        f"{system_prompt}\n\n"
        f"The content below contains {total_chunks} partial results from analyzing {page_url} in parts. "
        f"Merge ALL partial results into ONE final, comprehensive answer for the task described above. "
        f"Keep every detail, remove duplicates, organize clearly."
    )

    try:
        return query_ollama(host, model, synthesis_prompt, synthesis_context)
    except RuntimeError as e:
        logging.error(f"Synthesis query failed: {e}. Returning concatenated partial responses.")
        return synthesis_context


def _outcome_of(result) -> str:
    """The outcome word of a process_url_with_llm() result (None means ok)."""
    if isinstance(result, tuple) and result:
        return str(result[0] or 'ok')
    return 'ok'


def _classify_fetch_error(page_url: str, error: FetchError) -> Tuple[str, str]:
    """Name what went wrong: a refusal is BLOCKED, never "no content"."""
    if error.timed_out:
        return 'timeout', f"{page_url}: {error}"
    reason = detect_block(error.status_code, error.body) if error.status_code else None
    if reason:
        return 'blocked', f"{page_url}: {reason}"
    if error.status_code in (404, 410):
        return 'not_found', f"{page_url}: HTTP {error.status_code} (the page does not exist)"
    if error.network:
        return 'unreachable', f"{page_url}: {error}"
    return 'error', f"{page_url}: {error}"


def process_url_with_llm(page_url: str, host: str, model: str, system_prompt: str,
                         crawl_type: str, timestamp: str,
                         content_mode: str = "raw",
                         include_headers: bool = True,
                         extract_recon: bool = False,
                         page_timeout: Optional[float] = None,
                         max_page_bytes: int = MAX_PAGE_BYTES) -> Tuple[str, str]:
    """
    Fetch a URL, capture content, save it, query LLM with automatic chunking.

    The chunk size is determined automatically by querying the Ollama API for the
    model's actual context window. NO content is ever dropped or ignored - if the
    page is too big for one request, it is split into as many chunks as needed.

    content_mode:
      - "raw"  : send the FULL raw HTML/JS/CSS body + headers + resource inventory to the LLM
      - "text" : legacy mode - strip HTML and send only visible text

    Returns ``(outcome, detail)``. ``ok`` means the page was analyzed and its
    INI_SECTION_CRAWLER logged. Anything else (``blocked``, ``timeout``,
    ``unreachable``, ``not_found``, ``error``, ``skipped``) means it was NOT, and
    a bot wall's words never reach the LLM dressed up as the page.
    """
    logging.info(f"Fetching [{content_mode}]: {page_url}")

    try:
        raw_html, headers, status_code = _fetch_with_retry(page_url, page_timeout, max_page_bytes)
    except FetchError as e:
        outcome, detail = _classify_fetch_error(page_url, e)
        logging.error(f"{outcome.upper()}: {detail}")
        return outcome, detail
    except Exception as e:
        logging.error(f"Failed to fetch {page_url}: {e}")
        return 'error', f"{page_url}: {e}"

    _PAGE_CACHE.clear()
    _PAGE_CACHE[page_url] = raw_html
    logging.info(f"Received {len(raw_html)} chars, HTTP {status_code} from {page_url}")
    content_type = _header_value(headers, 'Content-Type', 'unknown')
    logging.info(f"Content-Type: {content_type}")

    if not raw_html.strip():
        logging.warning(f"Empty response body from {page_url}, skipping LLM query.")
        return 'skipped', f"{page_url}: the server returned an empty page"

    # Binary guard: never decode-as-text + feed a PDF/image/archive to the LLM.
    if _is_binary_for_llm(content_type, page_url):
        logging.info(f"Skipping binary content for LLM ({content_type}) at {page_url}")
        return 'skipped', f"{page_url}: a binary file ({content_type}), not analyzed"

    visible_text = strip_html(raw_html)
    block = detect_block(status_code, raw_html, visible_text)
    if block:
        logging.error(f"BLOCKED: {page_url}: {block} - not analyzed, never reported as content")
        return 'blocked', f"{page_url}: {block}"

    # Recon pass (runs on the RAW source in both modes; saved + injected into context).
    recon_block = ''
    if extract_recon:
        findings = extract_recon_findings(raw_html)
        recon_block = format_recon_summary(findings)
        if recon_block:
            save_crawled_content(recon_block, crawl_type, timestamp, "recon")
            logging.info(
                f"Recon for {page_url}: {len(findings['secrets'])} secret(s), "
                f"{len(findings['emails'])} email(s), "
                f"{len(findings['source_maps'])} source-map(s), "
                f"{len(findings['comments'])} comment(s)"
            )

    if content_mode == "raw":
        # --- RAW MODE: Full developer context ---
        extractor = ResourceExtractor(page_url)
        extractor.feed(raw_html)
        resource_summary = extractor.get_resource_summary()

        api_endpoints = extract_api_endpoints(raw_html)
        if api_endpoints:
            logging.info(f"Discovered {len(api_endpoints)} API endpoints in source")

        # Build ALL content as one flat string - chunking handled by query_ollama_chunked
        full_content = build_full_content(
            page_url, raw_html, headers if include_headers else {}, status_code,
            resource_summary, api_endpoints
        )

        if recon_block:
            full_content = f"{recon_block}\n\n{full_content}"

        # User's prompt goes FIRST - it is THE task. Dev preamble is secondary context.
        full_system_prompt = (
            f"YOUR PRIMARY TASK:\n{system_prompt}\n\n"
            f"CONTEXT ABOUT THE INPUT:\n{DEV_RAW_PREAMBLE}{DEV_RESOURCE_PREAMBLE}"
        )

        # Save raw content
        filepath_raw = save_crawled_content(raw_html, crawl_type, timestamp, "raw")
        logging.info(f"Saved raw HTML to: {filepath_raw}")

        if resource_summary:
            filepath_res = save_crawled_content(
                resource_summary, crawl_type, timestamp, "resources"
            )
            logging.info(f"Saved resource inventory to: {filepath_res}")

        # Query LLM - auto-chunks based on model's real context window
        try:
            response_text = query_ollama_chunked(
                host, model, full_system_prompt, full_content, page_url
            )
        except RuntimeError as e:
            logging.error(f"LLM query failed for {page_url}: {e}")
            return 'error', f"{page_url}: the LLM did not answer ({e})"

    else:
        # --- TEXT MODE ---
        plain_text = visible_text
        logging.info(f"Extracted {len(plain_text)} chars of text from {page_url}")

        if not plain_text.strip():
            logging.warning(f"No text content found at {page_url} (the page is probably built "
                            f"by JavaScript; Playwrighter can render it), skipping LLM query.")
            return 'skipped', (f"{page_url}: no readable text (the page is probably built "
                               f"by JavaScript)")

        if recon_block:
            plain_text = f"{recon_block}\n\n{plain_text}"

        filepath = save_crawled_content(plain_text, crawl_type, timestamp)
        logging.info(f"Saved crawled content to: {filepath}")

        # Query LLM - auto-chunks based on model's real context window
        try:
            response_text = query_ollama_chunked(
                host, model, system_prompt, plain_text, page_url
            )
        except RuntimeError as e:
            logging.error(f"LLM query failed for {page_url}: {e}")
            return 'error', f"{page_url}: the LLM did not answer ({e})"

    if not str(response_text or '').strip():
        logging.error(f"The LLM returned an EMPTY answer for {page_url}; not reported as a result.")
        return 'error', f"{page_url}: the LLM returned an empty answer"

    # Log response
    type_label = crawl_type.replace('-range', '')
    upper_label = type_label.upper()
    logging.info(
        f"INI_SECTION_CRAWLER<<<\n"
        f"label: {upper_label}\n"
        f"model: {model}\n"
        f"url: {page_url}\n"
        f"crawl_type: {type_label}\n"
        f"content_mode: {content_mode}\n"
        f"status: ok\n"
        f"http_status: {status_code}\n"
        f"\n"
        f"{response_text}\n"
        f">>>END_SECTION_CRAWLER"
    )
    return 'ok', page_url


# ============================================================
# Crawl orchestration (multi-seed, bounded, polite)
# ============================================================


def _page_kwargs(budget: CrawlBudget, proc_kwargs: Dict) -> Dict:
    """proc_kwargs with this page's timeout clipped to the crawl deadline."""
    kwargs = dict(proc_kwargs)
    kwargs['page_timeout'] = budget.page_timeout(
        float(proc_kwargs.get('page_timeout') or PAGE_TIMEOUT_SECONDS))
    return kwargs


def _process_link_list(links, label, budget, visited, host, model, system_prompt, proc_kwargs):
    """Process a flat list of links with the page budget, visited-set de-dup, optional
    robots.txt check, and inter-request delay."""
    total = len(links)
    for i, link in enumerate(links):
        if budget.exhausted():
            logging.info(f"Stopping: {budget.stop_reason()}.")
            break
        if link in visited:
            continue
        if not budget.robots_allowed(link):
            logging.info(f"robots.txt disallows {link}; skipping.")
            continue
        visited.add(link)
        budget.wait()
        link_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        logging.info(f"Processing link {i + 1}/{total}: {link}")
        result = process_url_with_llm(link, host, model, system_prompt, label, link_ts,
                                      **_page_kwargs(budget, proc_kwargs))
        budget.record(link, result)
        budget.note_processed()


def _crawl_recursive(urls_to_process, current_depth, max_depth, budget, visited,
                     host, model, system_prompt, proc_kwargs):
    """large-range: process links at the current depth, then recurse into the links they
    contain, up to max_depth - bounded by the shared budget and visited set."""
    if current_depth > max_depth:
        return
    total = len(urls_to_process)
    next_level = []
    for i, link in enumerate(urls_to_process):
        if budget.exhausted():
            logging.info(f"Stopping: {budget.stop_reason()}.")
            return
        if link in visited:
            continue
        if not budget.robots_allowed(link):
            logging.info(f"robots.txt disallows {link}; skipping.")
            continue
        visited.add(link)
        budget.wait()
        link_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        logging.info(f"[depth={current_depth}/{max_depth}] Processing link {i + 1}/{total}: {link}")
        result = process_url_with_llm(link, host, model, system_prompt, 'large', link_ts,
                                      **_page_kwargs(budget, proc_kwargs))
        budget.record(link, result)
        budget.note_processed()

        # Only a page that answered is worth reading for deeper links.
        if current_depth < max_depth and _outcome_of(result) == 'ok':
            try:
                link_html = fetch_page(link)
                next_level.extend(extract_links(link_html, link))
            except Exception as e:
                logging.error(f"Failed to fetch {link} for deeper crawl: {e}")

    if next_level and current_depth < max_depth and not budget.exhausted():
        logging.info(f"Recursing to depth {current_depth + 1}: {len(next_level)} candidate links")
        _crawl_recursive(next_level, current_depth + 1, max_depth, budget, visited,
                         host, model, system_prompt, proc_kwargs)


#: Every crawl type, and the spellings people use for "just this page".
CRAWL_TYPES = ('page', 'small-range', 'medium-range', 'large-range')
_CRAWL_TYPE_ALIASES = {'single': 'page', 'single-page': 'page', 'page-only': 'page',
                       'one': 'page', 'seed': 'page'}
#: When NOTHING was delivered, the section names the most telling failure.
_FAILURE_PRIORITY = ('blocked', 'timeout', 'unreachable', 'not_found', 'error', 'skipped')
#: The budget of the last crawl(); main() and the tests read its outcomes.
LAST_BUDGET: Optional[CrawlBudget] = None


def _normalize_crawl_type(value) -> str:
    text = str(value if value is not None else 'page').strip().lower() or 'page'
    return _CRAWL_TYPE_ALIASES.get(text, text)


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else '').strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off'):
        return False
    return default


def _as_number(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _analyze_seed(seed, label, budget, visited, host, model, system_prompt, proc_kwargs):
    """Analyze the seed page ITSELF - the page the user actually asked about."""
    if seed in visited:
        return
    if not budget.robots_allowed(seed):
        logging.info(f"robots.txt disallows {seed}; skipping.")
        budget.record(seed, ('skipped', f"{seed}: robots.txt disallows this page"))
        return
    visited.add(seed)
    budget.wait()
    seed_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logging.info(f"Analyzing the page itself: {seed}")
    result = process_url_with_llm(seed, host, model, system_prompt, label, seed_ts,
                                  **_page_kwargs(budget, proc_kwargs))
    budget.record(seed, result)
    budget.note_processed()


def _emit_failure_section(url: str, crawl_type: str, content_mode: str, model: str,
                          status: str, body: str) -> None:
    """ONE truthful INI_SECTION_CRAWLER for a crawl that delivered NOTHING, so a
    flow or the chat reads a named failure instead of an empty success."""
    label = str(crawl_type).replace('-range', '')
    logging.info(
        f"INI_SECTION_CRAWLER<<<\n"
        f"label: {label.upper()}\n"
        f"model: {model}\n"
        f"url: {url}\n"
        f"crawl_type: {label}\n"
        f"content_mode: {content_mode}\n"
        f"status: {status}\n"
        f"http_status: \n"
        f"\n"
        f"{body}\n"
        f">>>END_SECTION_CRAWLER"
    )


def _report_outcome(budget: CrawlBudget, seeds: List[str], crawl_type: str,
                    content_mode: str, model: str) -> None:
    """Say what the crawl achieved: always a summary line, and when NOTHING was
    analyzed, one failure section naming why - a crawl never ends in silence."""
    counts = {word: budget.count(word) for word in ('ok',) + _FAILURE_PRIORITY}
    parts = [f"{number} {word}" for word, number in counts.items() if number]
    logging.info("Crawl summary: " + (", ".join(parts) if parts else "no page was processed"))
    if counts['ok']:
        return
    failures = [(url, outcome, detail) for url, outcome, detail in budget.outcomes
                if outcome != 'ok']
    if failures:
        status = next((word for word in _FAILURE_PRIORITY if counts.get(word)), 'error')
    elif budget.deadline_passed():
        status = 'timeout'
    else:
        status = 'error'
    lines = ["NOTHING WAS ANALYZED. Do not present any page content for this crawl."]
    for _url, outcome, detail in failures[:20]:
        lines.append(f"- {outcome}: {detail}")
    if len(failures) > 20:
        lines.append(f"- ... and {len(failures) - 20} more")
    if not failures:
        lines.append("- " + (budget.stop_reason() if budget.deadline_passed()
                             else "no page could be processed"))
    if status == 'blocked':
        lines.append("The site answered with a refusal (bot wall, CAPTCHA, 401/403/429). "
                     "Try again later; open it in a real browser (Playwrighter) only if the "
                     "user is entitled to access it. Never try to get around a CAPTCHA.")
    elif status == 'skipped':
        lines.append("The pages had no readable text (built by JavaScript, empty, or a "
                     "binary file). For a JavaScript page use Playwrighter; for a file use "
                     "Apirer and File-Extractor.")
    _emit_failure_section(seeds[0] if seeds else '', crawl_type, content_mode, model,
                          status, "\n".join(lines))


def crawl(config: Dict, host: str, model: str, system_prompt: str) -> int:
    """Drive the crawl across ALL seed URLs with a shared page budget + visited set.
    Returns the number of pages processed.

    ``crawl_type: page`` (the default) analyzes exactly the seed URL(s). The
    ``*-range`` types analyze each seed ITSELF first (``include_seed``, default
    true; false restores the old links-only behaviour) and then its links. The
    whole run is bounded by ``max_pages`` and ``deadline_seconds``, and it always
    ends with a truthful summary."""
    global LAST_BUDGET, _CRAWL_DEADLINE
    seeds = _collect_seed_urls(config)
    if not seeds:
        logging.error("No URL configured. Set the 'url' or 'urls' field in config.yaml.")
        return 0

    content_mode = config.get('content_mode', 'raw')
    crawl_type = _normalize_crawl_type(config.get('crawl_type', 'page'))
    if crawl_type not in CRAWL_TYPES:
        logging.error(f"Unknown crawl_type: {crawl_type}. Use page, small-range, "
                      f"medium-range, or large-range.")
        _emit_failure_section(seeds[0], crawl_type, content_mode, model, 'error',
                              f"Unknown crawl_type '{crawl_type}'. Use page, small-range, "
                              f"medium-range, or large-range.")
        return 0

    budget = CrawlBudget(
        max_pages=config.get('max_pages', 0),
        delay_seconds=config.get('request_delay_seconds', 0),
        respect_robots=bool(config.get('respect_robots', False)),
        deadline_seconds=config.get('deadline_seconds', 0),
    )
    LAST_BUDGET = budget
    _CRAWL_DEADLINE = budget.deadline_at
    proc_kwargs = {
        'content_mode': content_mode,
        'include_headers': config.get('include_headers', True),
        'extract_recon': bool(config.get('extract_recon', False)),
        'page_timeout': _as_number(config.get('page_timeout_seconds'), PAGE_TIMEOUT_SECONDS),
        'max_page_bytes': int(_as_number(config.get('max_page_bytes'), MAX_PAGE_BYTES)),
    }
    include_seed = _as_bool(config.get('include_seed', True), True)

    depth = config.get('depth', 1)
    if crawl_type == 'large-range' and (not isinstance(depth, int) or depth < 1):
        logging.warning(f"Invalid depth value: {depth}. Defaulting to 1.")
        depth = 1

    visited = set()
    label = crawl_type.replace('-range', '')

    try:
        for seed in seeds:
            if budget.exhausted():
                logging.info(f"Stopping before seed {seed}: {budget.stop_reason()}.")
                break

            logging.info(f"=== Crawling seed: {seed} (type={crawl_type}) ===")
            if crawl_type == 'page' or include_seed:
                _analyze_seed(seed, label, budget, visited, host, model, system_prompt,
                              proc_kwargs)
            if crawl_type == 'page' or budget.exhausted():
                continue

            try:
                main_html = fetch_page(seed)
            except Exception as e:
                logging.error(f"Failed to fetch seed {seed}: {e}")
                if not include_seed:
                    outcome = (_classify_fetch_error(seed, e) if isinstance(e, FetchError)
                               else ('error', f"{seed}: {e}"))
                    budget.record(seed, outcome)
                continue

            all_links = extract_links(main_html, seed)

            if crawl_type == 'small-range':
                links = filter_same_domain(all_links, seed)
                logging.info(f"Found {len(links)} same-domain links")
                _process_link_list(links, label, budget, visited, host, model, system_prompt,
                                   proc_kwargs)
            elif crawl_type == 'medium-range':
                logging.info(f"Found {len(all_links)} total links (cross-domain)")
                _process_link_list(all_links, label, budget, visited, host, model,
                                   system_prompt, proc_kwargs)
            else:  # large-range
                visited.add(seed)  # don't revisit the seed itself
                logging.info(f"Found {len(all_links)} links from seed (recursive depth={depth})")
                _crawl_recursive(all_links, 1, depth, budget, visited, host, model,
                                 system_prompt, proc_kwargs)
    finally:
        _CRAWL_DEADLINE = None

    _report_outcome(budget, seeds, crawl_type, content_mode, model)
    return budget.processed


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        url = config.get('url', '')
        system_prompt = config.get('system_prompt', '')
        crawl_type = _normalize_crawl_type(config.get('crawl_type', 'page'))
        content_mode = config.get('content_mode', 'raw')
        include_headers = config.get('include_headers', True)
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'llama3.1:8b')
        target_agents = config.get('target_agents', [])

        logging.info("CRAWLER AGENT STARTED")
        logging.info(f"URL: {url}")
        logging.info(f"Crawl type: {crawl_type}")
        if crawl_type == 'large-range':
            depth = config.get('depth', 1)
            logging.info(f"Recursive depth: {depth}")
        if crawl_type != 'page':
            logging.info(f"Analyze the seed page itself: "
                         f"{_as_bool(config.get('include_seed', True), True)}")
        logging.info(f"Content mode: {content_mode}")
        logging.info(f"Include headers: {include_headers}")
        logging.info(f"Seed URLs: {len(_collect_seed_urls(config))}")
        logging.info(f"Max pages: {config.get('max_pages', 0)} (0 = unlimited)")
        logging.info(f"Crawl deadline (s): {config.get('deadline_seconds', 0)} (0 = none)")
        logging.info(f"Page timeout (s): "
                     f"{_as_number(config.get('page_timeout_seconds'), PAGE_TIMEOUT_SECONDS):.0f}")
        logging.info(f"Request delay (s): {config.get('request_delay_seconds', 0)}")
        logging.info(f"Respect robots.txt: {bool(config.get('respect_robots', False))}")
        logging.info(f"Extract recon: {bool(config.get('extract_recon', False))}")
        logging.info(f"Model: {model} @ {host}")
        logging.info(f"Targets: {target_agents}")

        # Query model context size early so it's logged and cached
        ctx_tokens = get_model_context_size(host, model)
        logging.info(f"Model context window: {ctx_tokens} tokens (~{tokens_to_chars(ctx_tokens)} chars)")
        logging.info("=" * 60)

        seeds = _collect_seed_urls(config)

        if content_mode not in ('raw', 'text'):
            logging.error(f"Invalid content_mode: {content_mode}. Use 'raw' or 'text'.")
            _emit_failure_section(url, crawl_type, str(content_mode), model, 'error',
                                  f"Invalid content_mode '{content_mode}'. Use 'raw' or 'text'.")
        elif not seeds:
            logging.error("No URL configured. Set the 'url' (or 'urls') field in config.yaml.")
            _emit_failure_section(url, crawl_type, content_mode, model, 'error',
                                  "No URL configured. Set 'url' (or 'urls').")
        elif not system_prompt.strip():
            logging.error("No system_prompt configured. Set the 'system_prompt' field in config.yaml.")
            _emit_failure_section(url, crawl_type, content_mode, model, 'error',
                                  "No system_prompt configured: say what to extract from the page.")
        else:
            pages = crawl(config, host, model, system_prompt)
            logging.info(f"Crawl processed {pages} page(s).")

        logging.info("Crawl processing complete.")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Crawler agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"Crawler agent error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
