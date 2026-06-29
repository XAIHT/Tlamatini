# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Googler Agent - Google search agent with content extraction
# Action: Triggered by upstream -> Search Google for query -> Fetch top N results ->
#         Extract readable text -> Save results to file -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
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
from datetime import datetime
from typing import Dict, List

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
# Playwright-based Search & Content Extraction
# ============================================================

_BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Selectors tried in order for organic Google result links
_GOOGLE_RESULT_SELECTORS = [
    '#rso a:has(h3)',
    '#search a:has(h3)',
    'div.g a[href^="http"]',
    '#rso a[href^="http"]',
    'div#search a[href^="http"]',
]

# Selectors tried in order for organic DuckDuckGo result links
_DDG_RESULT_SELECTORS = [
    'article[data-testid="result"] a[data-testid="result-title-a"]',
    'a.result__a',
    'h2 a[href^="http"]',
]

# Content-Types that indicate binary / non-readable content
_BINARY_CONTENT_TYPES = {
    'application/pdf', 'application/octet-stream',
    'application/zip', 'application/gzip',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument',
}

# URL path suffixes that indicate binary files
_BINARY_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.exe', '.dmg',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
}


def _dismiss_google_consent(page) -> None:
    """Try to dismiss Google's cookie consent banner if present."""
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Accept")',
        'button:has-text("Acepto")',
        'button:has-text("Aceptar todo")',
        'button:has-text("Tout accepter")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Accetta tutto")',
        'button#L2AGLb',
        'button[aria-label="Accept all"]',
        'div[role="dialog"] button:first-of-type',
    ]
    for selector in consent_selectors:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1000)
                logging.info("Dismissed Google consent banner.")
                return
        except Exception:
            continue


_DEFAULT_SKIP_DOMAINS = {'google.com', 'google.co', 'accounts.google', 'support.google',
                         'maps.google', 'policies.google'}


def _dedup_links(links: List[Dict], skip_domains=None,
                 allow_same_domain: bool = False) -> List[Dict]:
    """Filter junk / skip-domain links and de-duplicate a list of {url, title} dicts.

    De-dup key:
      - allow_same_domain=False (legacy): de-dup by DOMAIN -> at most one result per host.
      - allow_same_domain=True:           de-dup by full URL -> keep many results per host.

    The second mode is what makes ``site:`` / ``filetype:`` dork enumeration usable: a
    single-site dork legitimately returns dozens of distinct URLs on ONE domain, and the
    legacy by-domain collapse would discard all but the first (Blocker #1).
    """
    if skip_domains is None:
        skip_domains = set(_DEFAULT_SKIP_DOMAINS)
    from urllib.parse import urlparse

    out: List[Dict] = []
    seen = set()
    for item in links:
        href = (item.get('url') or '').strip()
        if not href or not href.startswith('http'):
            continue
        try:
            domain = urlparse(href).netloc.lower()
        except Exception:
            continue
        if not domain:
            continue
        if any(sd in domain for sd in skip_domains):
            continue
        key = href if allow_same_domain else domain
        if key in seen:
            continue
        seen.add(key)
        out.append({'url': href, 'title': (item.get('title') or '').strip()})
    return out


def _extract_link_title(elem) -> str:
    """Best-effort title for a result anchor: prefer an inner <h3>, else the anchor's
    first visible text line. Never raises."""
    try:
        h3 = elem.query_selector('h3')
        if h3:
            text = (h3.inner_text() or '').strip()
            if text:
                return text
    except Exception:
        pass
    try:
        text = (elem.inner_text() or '').strip()
        if text:
            return text.splitlines()[0].strip()
    except Exception:
        pass
    return ''


def _extract_links_with_selectors(page, selectors, skip_domains=None,
                                  allow_same_domain: bool = False) -> List[Dict]:
    """Try each selector in order; return the first non-empty list of result dicts
    ({url, title}), filtered + de-duplicated by ``_dedup_links``."""
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        if not elements:
            continue

        raw: List[Dict] = []
        for elem in elements:
            href = elem.get_attribute("href")
            if not href:
                continue
            raw.append({'url': href, 'title': _extract_link_title(elem)})

        deduped = _dedup_links(raw, skip_domains, allow_same_domain)
        if deduped:
            logging.info(f"Selector '{selector}' matched {len(deduped)} link(s).")
            return deduped

    return []


def _is_binary_url(url: str) -> bool:
    """Check if the URL path ends with a known binary file extension."""
    from urllib.parse import urlparse
    path = urlparse(url).path.lower().split('?')[0]
    return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)


def _is_binary_content_type(content_type: str) -> bool:
    """Check if Content-Type indicates binary / non-readable content."""
    ct = content_type.lower().split(';')[0].strip()
    if ct in _BINARY_CONTENT_TYPES:
        return True
    if ct.startswith(('image/', 'audio/', 'video/')):
        return True
    if 'officedocument' in ct:
        return True
    return False


def _fetch_page_text(page, url: str) -> Dict:
    """
    Navigate a Playwright page to a URL and extract rendered readable text.
    Detects and skips binary content (PDFs, images, etc.).
    Returns a dict with url, status_code, content_length, content (or error).
    """
    if _is_binary_url(url):
        logging.info(f"Skipping binary URL: {url}")
        return {"url": url, "skipped": True,
                "error": "Binary file detected from URL extension, skipped"}

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return {"url": url, "error": str(e)}

    if not response:
        return {"url": url, "error": "No response received"}

    status = response.status

    # Check Content-Type header for binary content
    content_type = response.headers.get('content-type', '')
    if _is_binary_content_type(content_type):
        logging.info(f"Skipping binary content-type '{content_type}' for: {url}")
        return {"url": url, "status_code": status, "skipped": True,
                "error": f"Binary content-type ({content_type}), skipped"}

    # Wait for JS rendering to complete
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass  # best-effort; domcontentloaded already loaded

    # Extract visible rendered text via Playwright (handles JS-rendered SPAs)
    try:
        text = page.inner_text('body')
    except Exception:
        text = ""

    # Clean up whitespace: collapse runs of blank lines
    if text:
        lines = text.splitlines()
        cleaned = []
        blank_count = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_count += 1
                if blank_count <= 1:
                    cleaned.append('')
            else:
                blank_count = 0
                cleaned.append(stripped)
        text = '\n'.join(cleaned).strip()

    text = text[:200000]  # limit to 200KB

    return {
        "url": url,
        "status_code": status,
        "content_length": len(text),
        "content": text,
    }


def _search_google_playwright(page, query: str, number_of_results: int,
                              allow_same_domain: bool = False) -> List[Dict]:
    """Perform a Google search using Playwright and return result dicts ({url, title})."""
    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
    _dismiss_google_consent(page)

    search_box = page.wait_for_selector(
        'textarea[name="q"], input[name="q"]', timeout=10000
    )
    search_box.fill(query)
    search_box.press("Enter")

    try:
        page.wait_for_selector('#rso, #search, div.g', timeout=15000)
    except Exception:
        logging.warning("Timed out waiting for Google result container; proceeding anyway.")

    page.wait_for_timeout(2000)

    hits = _extract_links_with_selectors(
        page, _GOOGLE_RESULT_SELECTORS, allow_same_domain=allow_same_domain
    )
    return hits[:number_of_results]


def _search_ddg_playwright(page, query: str, number_of_results: int,
                           allow_same_domain: bool = False) -> List[Dict]:
    """Fallback: perform a DuckDuckGo search using Playwright and return result dicts.

    NOTE: DuckDuckGo honors only a SUBSET of Google dork operators (site:, filetype:,
    intitle:, inurl:); operators like before:/after:/numrange: are ignored there, so a
    dork that falls back to DDG may return broader results than the same Google dork."""
    logging.info("Falling back to DuckDuckGo search...")
    page.goto(f"https://duckduckgo.com/?q={query.replace(' ', '+')}&t=h_&ia=web",
              wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector('article[data-testid="result"], a.result__a, h2 a', timeout=15000)
    except Exception:
        logging.warning("Timed out waiting for DuckDuckGo results; proceeding anyway.")

    page.wait_for_timeout(2000)

    hits = _extract_links_with_selectors(
        page, _DDG_RESULT_SELECTORS, skip_domains={'duckduckgo.com'},
        allow_same_domain=allow_same_domain,
    )
    return hits[:number_of_results]


# ============================================================
# Core Googler Logic
# ============================================================

def _query_has_site_operator(query: str) -> bool:
    """True if the query already contains a ``site:`` operator (case-insensitive)."""
    return bool(re.search(r'(?:^|\s)site:\S', query or '', re.IGNORECASE))


def _resolve_allow_same_domain(config: Dict, effective_query: str) -> bool:
    """Same-domain de-dup is ON when explicitly configured (``allow_same_domain: true``)
    OR when the effective query carries a ``site:`` operator (single-site dork)."""
    return bool(config.get('allow_same_domain', False)) or \
        _query_has_site_operator(effective_query)


def build_dork_query(config: Dict) -> str:
    """Compose a final Google search string from a freeform ``query`` PLUS optional
    structured Google-dork operator fields.

    The raw ``query`` is preserved verbatim (so an existing freeform dork keeps working
    unchanged); the structured fields are APPENDED. Supported fields:

        exact     -> "phrase"          intitle  -> intitle:...
        query     -> <as-is>           inurl    -> inurl:...
        site      -> site:...          intext   -> intext:...
        filetype  -> filetype:...      before   -> before:YYYY-MM-DD
        exclude   -> -term (each)      after    -> after:YYYY-MM-DD

    ``filetype`` accepts ``pdf``, ``filetype:pdf`` or ``ext:pdf`` interchangeably.
    ``exclude`` accepts a list OR a comma/space-separated string.
    An operator value already carrying its own prefix (e.g. ``site:example.com``) is
    normalized so the prefix is never doubled.
    """
    parts: List[str] = []

    exact = str(config.get('exact', '') or '').strip().strip('"')
    if exact:
        parts.append(f'"{exact}"')

    raw = str(config.get('query', '') or '').strip()
    if raw:
        parts.append(raw)

    def _operator(value, operator: str, quote_if_spaces: bool = False):
        v = str(value or '').strip()
        if not v:
            return None
        if v.lower().startswith(operator.lower() + ':'):
            v = v[len(operator) + 1:].strip()
        if not v:
            return None
        if quote_if_spaces and ' ' in v:
            v = '"{}"'.format(v.strip('"'))
        return f'{operator}:{v}'

    for field_name, operator, quote in (
        ('intitle', 'intitle', True),
        ('inurl', 'inurl', False),
        ('intext', 'intext', True),
        ('site', 'site', False),
        ('before', 'before', False),
        ('after', 'after', False),
    ):
        built = _operator(config.get(field_name), operator, quote)
        if built:
            parts.append(built)

    # filetype accepts bare ``pdf``, ``filetype:pdf`` or ``ext:pdf``
    filetype = str(config.get('filetype', '') or '').strip()
    if filetype:
        low = filetype.lower()
        for prefix in ('filetype:', 'ext:'):
            if low.startswith(prefix):
                filetype = filetype[len(prefix):].strip()
                break
        if filetype:
            parts.append(f'filetype:{filetype}')

    # exclusions: list OR comma/space-separated string -> each becomes -term
    exclude = config.get('exclude', [])
    if isinstance(exclude, str):
        exclude = [t for t in re.split(r'[,\s]+', exclude) if t]
    if isinstance(exclude, (list, tuple)):
        for term in exclude:
            t = str(term or '').strip()
            if not t:
                continue
            parts.append(t if t.startswith('-') else f'-{t}')

    return ' '.join(parts).strip()


def googler_search(query: str, number_of_results: int = 5,
                   content_mode: str = "text",
                   allow_same_domain: bool = False) -> List[Dict]:
    """
    Search Google for the query, then either (a) list the result links, or (b) fetch the
    top N result pages with Playwright (JS-rendered) and extract their content.

    Falls back to DuckDuckGo if Google returns no results.
    Automatically skips binary content (PDFs, images, etc.) in the fetch modes.

    content_mode:
      - "text":        Extract rendered visible text from each result page (default)
      - "raw":         Return raw page HTML from each result page
      - "links_only":  Do NOT fetch result pages — return just the SERP hit list
                       (url + title). Ideal for dork enumeration / recon and far faster;
                       the URLs flow straight into a downstream Crawler / Kalier via the
                       Parametrizer.

    allow_same_domain:
      When True (auto-enabled by main() when the query contains a ``site:`` operator),
      result de-duplication is by full URL instead of by domain, so a single-site dork
      can return many distinct URLs from the same host (Blocker #1 fix).

    Returns a list of result dicts.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
        return []

    # links_only is cheap (no page fetch) so it may enumerate more hits per run.
    max_cap = 50 if content_mode == "links_only" else 10
    if number_of_results > max_cap:
        number_of_results = max_cap
    if number_of_results < 1:
        number_of_results = 1

    results: List[Dict] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=_BROWSER_ARGS)
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            try:
                # --- Search phase ---
                hits = _search_google_playwright(
                    page, query, number_of_results, allow_same_domain
                )

                if not hits:
                    logging.warning(f"Google returned 0 results for '{query}'; trying DuckDuckGo.")
                    hits = _search_ddg_playwright(
                        page, query, number_of_results, allow_same_domain
                    )

                if not hits:
                    try:
                        debug_path = os.path.join(script_dir, "debug_no_results.png")
                        page.screenshot(path=debug_path, full_page=True)
                        logging.warning(f"No results from any engine. Debug screenshot: {debug_path}")
                    except Exception as ss_err:
                        logging.warning(f"Could not save debug screenshot: {ss_err}")

                logging.info(f"Found {len(hits)} top links for '{query}'")

                # --- links_only: emit the hit list, do NOT fetch the pages ---
                if content_mode == "links_only":
                    for i, hit in enumerate(hits, 1):
                        results.append({
                            "index": i,
                            "url": hit.get("url", ""),
                            "title": hit.get("title", ""),
                            "status_code": "listed",
                            "content_length": 0,
                        })
                        logging.info(
                            f"Listed result {i}: {hit.get('url', '')} "
                            f"(title: {hit.get('title', '')!r})"
                        )
                    return results

                # --- Fetch phase: reuse the same browser for JS rendering ---
                for i, hit in enumerate(hits, 1):
                    url = hit.get("url", "")
                    title = hit.get("title", "")
                    logging.info(f"Fetching result {i}/{len(hits)}: {url}")

                    if content_mode == "raw":
                        try:
                            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            status = resp.status if resp else 0
                            html = page.content()[:500000]
                            results.append({
                                "index": i, "url": url, "title": title,
                                "status_code": status,
                                "content_length": len(html),
                                "content": html,
                            })
                        except Exception as e:
                            results.append({"index": i, "url": url, "title": title, "error": str(e)})
                    else:
                        result = _fetch_page_text(page, url)
                        result["index"] = i
                        result["title"] = title
                        results.append(result)

                    last = results[-1]
                    if 'error' not in last:
                        logging.info(
                            f"Fetched result {i}: {url} "
                            f"({last.get('status_code', 'N/A')}, "
                            f"{last.get('content_length', 0)} chars)"
                        )
                    else:
                        logging.info(f"Result {i}: {url} -> {last.get('error', 'unknown error')}")

            except Exception as e:
                logging.error(f"Search failed: {e}")
            finally:
                browser.close()

    except Exception as e:
        logging.error(f"Playwright launch failed: {e}")

    return results


def save_results(results: List[Dict], output_file: str, query: str) -> str:
    """Save search results to a file. Returns the absolute file path."""
    if not os.path.isabs(output_file):
        output_file = os.path.join(script_dir, output_file)

    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=== GOOGLER SEARCH RESULTS ===\n")
        f.write(f"Query: {query}\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Results: {len(results)}\n")
        f.write("=" * 60 + "\n\n")

        for result in results:
            f.write(f"=== HTTP RESPONSE METADATA (Result {result.get('index', '?')}) ===\n")
            f.write(f"URL: {result.get('url', 'N/A')}\n")
            if result.get('title'):
                f.write(f"Title: {result.get('title')}\n")
            f.write(f"Status: {result.get('status_code', 'N/A')}\n")
            f.write(f"Content Length: {result.get('content_length', 0)} chars\n")

            if 'error' in result:
                f.write(f"ERROR: {result['error']}\n")
            elif result.get('content'):
                f.write(f"\n{result.get('content', '')}\n")

            f.write("\n" + "=" * 60 + "\n\n")

    return os.path.abspath(output_file)


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"REANIMATED {CURRENT_DIR_NAME} (resuming from pause)")
        logging.info("=" * 60)

    try:
        raw_query = config.get('query', '')
        effective_query = build_dork_query(config)
        number_of_results = config.get('number_of_results', 5)
        content_mode = config.get('content_mode', 'text')
        output_file = config.get('output_file', 'googler_results.txt')
        target_agents = config.get('target_agents', [])

        # A ``site:`` dork needs same-domain de-dup OFF (keep many URLs per host).
        allow_same_domain = _resolve_allow_same_domain(config, effective_query)

        logging.info("GOOGLER AGENT STARTED")
        logging.info(f"Raw query: {raw_query}")
        logging.info(f"Effective query (with dork operators): {effective_query}")
        logging.info(f"Number of results: {number_of_results}")
        logging.info(f"Content mode: {content_mode}")
        logging.info(f"Allow same domain: {allow_same_domain}")
        logging.info(f"Output file: {output_file}")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        if not effective_query.strip():
            logging.error("No query configured. Set the 'query' field (or a dork operator "
                          "such as 'site' / 'filetype' / 'intitle') in config.yaml.")
        elif content_mode not in ('text', 'raw', 'links_only'):
            logging.error(f"Invalid content_mode: {content_mode}. Use 'text', 'raw', or 'links_only'.")
        else:
            # Perform Google search (+ optional content fetch)
            results = googler_search(effective_query, number_of_results,
                                     content_mode, allow_same_domain)

            if results:
                saved_path = save_results(results, output_file, effective_query)
                logging.info(f"Results saved to: {saved_path}")

                # Emit structured sections to the log for Parametrizer consumption
                for result in results:
                    r_url = result.get('url', 'N/A')
                    r_title = result.get('title', '')
                    r_status = result.get('status_code', 'N/A')
                    r_length = result.get('content_length', 0)
                    if 'error' in result:
                        r_body = f"ERROR: {result['error']}"
                    else:
                        r_body = result.get('content', '') or r_title
                    logging.info(
                        f"INI_SECTION_GOOGLER<<<\n"
                        f"url: {r_url}\n"
                        f"title: {r_title}\n"
                        f"status: {r_status}\n"
                        f"content_length: {r_length}\n"
                        f"\n"
                        f"{r_body}\n"
                        f">>>END_SECTION_GOOGLER"
                    )
            else:
                logging.warning("No results obtained from Google search.")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Googler agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"Googler agent error: {e}")
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
