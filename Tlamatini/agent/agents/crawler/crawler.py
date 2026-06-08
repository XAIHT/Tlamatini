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
import gzip
import zlib
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


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


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
    """Extract visible text from HTML, stripping all markup."""

    SKIP_TAGS = {'script', 'style', 'head', 'meta', 'link', 'noscript'}

    def __init__(self):
        super().__init__()
        self._pieces: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self) -> str:
        return '\n'.join(self._pieces)


def strip_html(html_content: str) -> str:
    """Remove all HTML markup and return plain text."""
    extractor = HTMLTextExtractor()
    extractor.feed(html_content)
    return extractor.get_text()


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
    an inter-request ``delay_seconds``, and optional ``robots.txt`` enforcement
    (per-host, cached, fail-open). Without these, ``large-range`` crawling is unbounded."""

    def __init__(self, max_pages=0, delay_seconds=0, respect_robots=False,
                 user_agent: str = _CRAWLER_UA):
        try:
            self.max_pages = max(0, int(max_pages or 0))
        except (TypeError, ValueError):
            self.max_pages = 0
        try:
            self.delay_seconds = max(0.0, float(delay_seconds or 0))
        except (TypeError, ValueError):
            self.delay_seconds = 0.0
        self.respect_robots = bool(respect_robots)
        self.user_agent = user_agent or _CRAWLER_UA
        self.processed = 0
        self._robots_cache: Dict[str, Optional[RobotFileParser]] = {}

    def remaining(self) -> Optional[int]:
        if self.max_pages == 0:
            return None  # unlimited
        return max(0, self.max_pages - self.processed)

    def exhausted(self) -> bool:
        return self.max_pages != 0 and self.processed >= self.max_pages

    def note_processed(self) -> None:
        self.processed += 1

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

def fetch_page_raw(url: str, include_headers: bool = True,
                   timeout: int = 60) -> Tuple[str, Dict[str, str], int]:
    """
    Fetch a web page via HTTP GET and return:
      - raw_body: the complete decoded response body (HTML/JS/CSS/JSON/everything)
      - headers: dict of HTTP response headers
      - status_code: HTTP status code

    Handles gzip/deflate encoding transparently.
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

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status_code = resp.getcode()
        headers_dict = {}
        if include_headers:
            for key in resp.headers:
                headers_dict[key] = resp.headers[key]

        raw_bytes = resp.read()

        # Handle compressed responses
        content_encoding = resp.headers.get('Content-Encoding', '').lower()
        if content_encoding == 'gzip':
            raw_bytes = gzip.decompress(raw_bytes)
        elif content_encoding == 'deflate':
            raw_bytes = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)

        charset = resp.headers.get_content_charset() or 'utf-8'
        raw_body = raw_bytes.decode(charset, errors='replace')

        return raw_body, headers_dict, status_code


def fetch_page(url: str) -> str:
    """Legacy: Fetch a web page and return its raw HTML content."""
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


def query_ollama(host: str, model: str, system_prompt: str, context: str) -> str:
    """
    Send a prompt to an Ollama LLM with a system prompt and context,
    and return the full response text.
    Uses the 'system' field so the LLM treats the prompt with proper priority,
    separate from the content/context which goes in 'prompt'.
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

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e


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


def process_url_with_llm(page_url: str, host: str, model: str, system_prompt: str,
                         crawl_type: str, timestamp: str,
                         content_mode: str = "raw",
                         include_headers: bool = True,
                         extract_recon: bool = False) -> None:
    """
    Fetch a URL, capture content, save it, query LLM with automatic chunking.

    The chunk size is determined automatically by querying the Ollama API for the
    model's actual context window. NO content is ever dropped or ignored — if the
    page is too big for one request, it is split into as many chunks as needed.

    content_mode:
      - "raw"  : send the FULL raw HTML/JS/CSS body + headers + resource inventory to the LLM
      - "text" : legacy mode — strip HTML and send only visible text
    """
    logging.info(f"Fetching [{content_mode}]: {page_url}")

    try:
        raw_html, headers, status_code = fetch_page_raw(
            page_url, include_headers=include_headers
        )
    except Exception as e:
        logging.error(f"Failed to fetch {page_url}: {e}")
        return

    logging.info(f"Received {len(raw_html)} chars, HTTP {status_code} from {page_url}")
    content_type = headers.get('Content-Type', 'unknown')
    logging.info(f"Content-Type: {content_type}")

    if not raw_html.strip():
        logging.warning(f"Empty response body from {page_url}, skipping LLM query.")
        return

    # Binary guard: never decode-as-text + feed a PDF/image/archive to the LLM.
    if _is_binary_for_llm(content_type, page_url):
        logging.info(f"Skipping binary content for LLM ({content_type}) at {page_url}")
        return

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

        # Build ALL content as one flat string — chunking handled by query_ollama_chunked
        full_content = build_full_content(
            page_url, raw_html, headers, status_code,
            resource_summary, api_endpoints
        )

        if recon_block:
            full_content = f"{recon_block}\n\n{full_content}"

        # User's prompt goes FIRST — it is THE task. Dev preamble is secondary context.
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

        # Query LLM — auto-chunks based on model's real context window
        try:
            response_text = query_ollama_chunked(
                host, model, full_system_prompt, full_content, page_url
            )
        except RuntimeError as e:
            logging.error(f"LLM query failed for {page_url}: {e}")
            return

    else:
        # --- TEXT MODE ---
        plain_text = strip_html(raw_html)
        logging.info(f"Extracted {len(plain_text)} chars of text from {page_url}")

        if not plain_text.strip():
            logging.warning(f"No text content found at {page_url}, skipping LLM query.")
            return

        if recon_block:
            plain_text = f"{recon_block}\n\n{plain_text}"

        filepath = save_crawled_content(plain_text, crawl_type, timestamp)
        logging.info(f"Saved crawled content to: {filepath}")

        # Query LLM — auto-chunks based on model's real context window
        try:
            response_text = query_ollama_chunked(
                host, model, system_prompt, plain_text, page_url
            )
        except RuntimeError as e:
            logging.error(f"LLM query failed for {page_url}: {e}")
            return

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
        f"\n"
        f"{response_text}\n"
        f">>>END_SECTION_CRAWLER"
    )


# ============================================================
# Crawl orchestration (multi-seed, bounded, polite)
# ============================================================


def _process_link_list(links, label, budget, visited, host, model, system_prompt, proc_kwargs):
    """Process a flat list of links with the page budget, visited-set de-dup, optional
    robots.txt check, and inter-request delay."""
    total = len(links)
    for i, link in enumerate(links):
        if budget.exhausted():
            logging.info(f"Page budget reached ({budget.processed}/{budget.max_pages}); stopping.")
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
        process_url_with_llm(link, host, model, system_prompt, label, link_ts, **proc_kwargs)
        budget.note_processed()


def _crawl_recursive(urls_to_process, current_depth, max_depth, budget, visited,
                     host, model, system_prompt, proc_kwargs):
    """large-range: process links at the current depth, then recurse into the links they
    contain, up to max_depth — bounded by the shared budget and visited set."""
    if current_depth > max_depth:
        return
    total = len(urls_to_process)
    next_level = []
    for i, link in enumerate(urls_to_process):
        if budget.exhausted():
            logging.info(f"Page budget reached ({budget.processed}/{budget.max_pages}); stopping.")
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
        process_url_with_llm(link, host, model, system_prompt, 'large', link_ts, **proc_kwargs)
        budget.note_processed()

        if current_depth < max_depth:
            try:
                link_html = fetch_page(link)
                next_level.extend(extract_links(link_html, link))
            except Exception as e:
                logging.error(f"Failed to fetch {link} for deeper crawl: {e}")

    if next_level and current_depth < max_depth and not budget.exhausted():
        logging.info(f"Recursing to depth {current_depth + 1}: {len(next_level)} candidate links")
        _crawl_recursive(next_level, current_depth + 1, max_depth, budget, visited,
                         host, model, system_prompt, proc_kwargs)


def crawl(config: Dict, host: str, model: str, system_prompt: str) -> int:
    """Drive the crawl across ALL seed URLs with a shared page budget + visited set.
    Returns the number of pages processed. With a single ``url`` and default flags the
    behavior is identical to the legacy single-seed crawl."""
    seeds = _collect_seed_urls(config)
    if not seeds:
        logging.error("No URL configured. Set the 'url' or 'urls' field in config.yaml.")
        return 0

    crawl_type = config.get('crawl_type', 'small-range')
    if crawl_type not in ('small-range', 'medium-range', 'large-range'):
        logging.error(f"Unknown crawl_type: {crawl_type}. Use small-range, medium-range, or large-range.")
        return 0

    budget = CrawlBudget(
        max_pages=config.get('max_pages', 0),
        delay_seconds=config.get('request_delay_seconds', 0),
        respect_robots=bool(config.get('respect_robots', False)),
    )
    proc_kwargs = {
        'content_mode': config.get('content_mode', 'raw'),
        'include_headers': config.get('include_headers', True),
        'extract_recon': bool(config.get('extract_recon', False)),
    }

    depth = config.get('depth', 1)
    if crawl_type == 'large-range' and (not isinstance(depth, int) or depth < 1):
        logging.warning(f"Invalid depth value: {depth}. Defaulting to 1.")
        depth = 1

    visited = set()

    for seed in seeds:
        if budget.exhausted():
            logging.info(f"Page budget ({budget.max_pages}) reached; stopping before seed {seed}.")
            break

        logging.info(f"=== Crawling seed: {seed} (type={crawl_type}) ===")
        try:
            main_html = fetch_page(seed)
        except Exception as e:
            logging.error(f"Failed to fetch seed {seed}: {e}")
            continue

        all_links = extract_links(main_html, seed)

        if crawl_type == 'small-range':
            links = filter_same_domain(all_links, seed)
            logging.info(f"Found {len(links)} same-domain links")
            _process_link_list(links, 'small', budget, visited, host, model, system_prompt, proc_kwargs)
        elif crawl_type == 'medium-range':
            logging.info(f"Found {len(all_links)} total links (cross-domain)")
            _process_link_list(all_links, 'medium', budget, visited, host, model, system_prompt, proc_kwargs)
        else:  # large-range
            visited.add(seed)  # don't revisit the seed itself
            logging.info(f"Found {len(all_links)} links from seed (recursive depth={depth})")
            _crawl_recursive(all_links, 1, depth, budget, visited, host, model, system_prompt, proc_kwargs)

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
        crawl_type = config.get('crawl_type', 'small-range')
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
        logging.info(f"Content mode: {content_mode}")
        logging.info(f"Include headers: {include_headers}")
        logging.info(f"Seed URLs: {len(_collect_seed_urls(config))}")
        logging.info(f"Max pages: {config.get('max_pages', 0)} (0 = unlimited)")
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
        elif not seeds:
            logging.error("No URL configured. Set the 'url' (or 'urls') field in config.yaml.")
        elif not system_prompt.strip():
            logging.error("No system_prompt configured. Set the 'system_prompt' field in config.yaml.")
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
