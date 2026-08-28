# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Googler Agent - resilient indexed-web search agent with content extraction
# Action: Triggered by upstream -> Search the engine chain -> Fetch top N results ->
#         Extract readable text -> Save results to file -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import random
import logging
import subprocess
import urllib.parse
import urllib.request
import base64
import html
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


##############################################################################
# THE SEARCH-ENGINE CHAIN
#
# WHY THIS EXISTS (measured 2026-08-23): the old two-engine path returned ZERO
# results for EVERY query — including a plain keyword control with no operators
# at all. Google timed out waiting for its result container and DuckDuckGo's
# JS app answered "Unexpected error. Please try again." The SAME dork run
# through a HEADED real-Chrome window returned 10 real EPUB URLs immediately.
#
# So the two failure modes were: (a) a headless JS app being refused, and
# (b) having only ONE fallback, which happened to be down.
#
# The redesign attacks both:
#   1. JS-FREE HTML ENDPOINTS COME FIRST. `html.duckduckgo.com/html/`,
#      `lite.duckduckgo.com/lite/` and Mojeek render plain server-side HTML with
#      no JavaScript app to fail, no consent dialog and no result-container race.
#      They are the most reliable thing in this whole file, so they are tried
#      before the heavyweight JS engines rather than as a last resort.
#   2. SEVEN ENGINE ROUTES, not two. Google, Bing, DuckDuckGo, Startpage,
#      Brave and Mojeek do not fail at the same moment, and Mojeek runs its OWN
#      index rather than reselling someone else's.
#   3. Every engine is reached by DIRECT RESULT URL, never by typing into a box
#      and pressing Enter — one navigation instead of a form interaction that
#      can race, and no dependence on the search box's markup.
#
# NOTE ON OPERATOR SUPPORT: `site:` and `filetype:` work on all of these.
# Google alone honours the full set — `before:`/`after:`/`AROUND()`/numeric
# ranges are Google-only, so a dork that falls through to another engine may
# return broader results. The engine that actually answered is always logged.
##############################################################################

_SEARCH_ENGINES = [
    {
        'name': 'duckduckgo-html',
        'url': 'https://html.duckduckgo.com/html/?q={q}',
        'wait': 'div.result, div.web-result, a.result__a',
        'selectors': ['a.result__a', 'h2.result__title a', 'div.result a[href^="http"]'],
        'skip': {'duckduckgo.com'},
        'js_free': True,
    },
    {
        'name': 'duckduckgo-lite',
        'url': 'https://lite.duckduckgo.com/lite/?q={q}',
        'wait': 'table, a.result-link',
        'selectors': ['a.result-link', 'a[href^="http"]'],
        'skip': {'duckduckgo.com'},
        'js_free': True,
    },
    {
        'name': 'mojeek',
        'url': 'https://www.mojeek.com/search?q={q}',
        'wait': 'ul.results-standard, a.title, li',
        'selectors': ['a.title', 'ul.results-standard a[href^="http"]'],
        'skip': {'mojeek.com'},
        'js_free': True,
    },
    {
        'name': 'bing',
        'url': 'https://www.bing.com/search?q={q}&count=30&setlang=en',
        'wait': '#b_results, li.b_algo',
        'selectors': ['li.b_algo h2 a', '#b_results a[href^="http"]'],
        'skip': {'bing.com', 'microsoft.com', 'msn.com'},
        'js_free': False,
    },
    {
        'name': 'google',
        'url': 'https://www.google.com/search?q={q}&num=30&hl=en',
        'wait': '#rso, #search, div.g, #main',
        'selectors': _GOOGLE_RESULT_SELECTORS,
        'skip': None,
        'js_free': False,
    },
    {
        'name': 'brave',
        'url': 'https://search.brave.com/search?q={q}',
        'wait': '#results, .snippet',
        'selectors': ['#results a[href^="http"]', '.snippet a[href^="http"]'],
        'skip': {'brave.com'},
        'js_free': False,
    },
    {
        'name': 'startpage',
        'url': 'https://www.startpage.com/sp/search?query={q}',
        'wait': '.w-gl__result, .result',
        'selectors': ['.w-gl__result a[href^="http"]', '.result a[href^="http"]'],
        'skip': {'startpage.com'},
        'js_free': False,
    },
]


##############################################################################
# TIER 0 — PLAIN-HTTP ENGINES (no browser at all)
#
# MEASURED 2026-08-23, and it changed the design. A bare `urllib` request with
# ordinary browser headers got:
#     html.duckduckgo.com  -> 200, real results, 3 gutenberg.org URLs
#     www.bing.com         -> 200, real results, 23 gutenberg.org URLs
# while the SAME endpoints returned nothing through Playwright, because the
# CSS selectors had gone stale (DuckDuckGo now renders `web-result` /
# `result__title`, not `a.result__a`).
#
# The lesson is the useful one: for a server-rendered results page a browser is
# not an advantage, it is the liability. There is no automation flag to leak, no
# `navigator.webdriver`, no headless fingerprint, no consent dialog and no
# selector to go stale — just HTML and a regex. So these run FIRST and the
# browser tier is the fallback, which is the exact inverse of the old design.
##############################################################################

_HTTP_ENGINES = [
    {'name': 'duckduckgo-html', 'url': 'https://html.duckduckgo.com/html/?q={q}',
     'skip': ('duckduckgo.com',)},
    {'name': 'bing-http', 'url': 'https://www.bing.com/search?q={q}&count=30&setlang=en',
     'skip': ('bing.com', 'microsoft.com', 'msn.com', 'go.microsoft')},
    {'name': 'duckduckgo-lite', 'url': 'https://lite.duckduckgo.com/lite/?q={q}',
     'skip': ('duckduckgo.com',)},
    {'name': 'mojeek-http', 'url': 'https://www.mojeek.com/search?q={q}',
     'skip': ('mojeek.com', 'mastodon.social/@mojeek', 'buttondown.email/mojeek')},
]

_HTTP_HEADERS = {
    'User-Agent': _USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
    'Connection': 'close',
}

_HREF_RE = re.compile(r'href=["\'](.*?)["\']', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')


def _http_search(engine: Dict, query: str, number_of_results: int,
                 skip_domains=None, allow_same_domain: bool = False,
                 timeout: float = 20.0) -> List[Dict]:
    """Fetch one server-rendered results page and harvest its outbound links.

    Deliberately regex-based rather than DOM-based: a results page's CLASS NAMES
    change (that is exactly what silently broke the browser path), but an
    `href` to an off-site URL is the one thing a search result cannot stop
    being."""
    url = engine['url'].format(q=urllib.parse.quote_plus(query))
    request = urllib.request.Request(url, headers=dict(_HTTP_HEADERS))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1_500_000).decode('utf-8', 'replace')
    except Exception as exc:
        logging.debug("   (%s) http fetch failed: %s", engine['name'], exc)
        return []

    own = tuple(engine.get('skip') or ())
    links: List[Dict] = []
    for href in _HREF_RE.findall(body):
        target = _unwrap_redirect(href)
        if not target.startswith('http'):
            continue
        low = target.lower()
        if any(bad in low for bad in own):
            continue
        if any(bad in low for bad in ('google.com/', 'gstatic.com', 'w3.org',
                                      'schema.org', 'javascript:')):
            continue
        links.append({'url': target, 'title': ''})

    hits = _dedup_links(links, skip_domains=skip_domains,
                        allow_same_domain=allow_same_domain)
    return hits[:number_of_results]


def _unwrap_redirect(url: str) -> str:
    """Return the real destination behind a search engine's redirector.

    DuckDuckGo's HTML endpoint hands back ``//duckduckgo.com/l/?uddg=<encoded>``
    and Google sometimes uses ``/url?q=<encoded>``. Left unwrapped these are
    useless as file URLs — the whole point of a `filetype:` hunt is the direct
    link — and they all collapse to one domain, which the de-duplicator would
    then throw away as repeats of a single host."""
    raw = html.unescape(str(url or ''))
    if not raw:
        return raw
    low = raw.lower()
    try:
        parsed = urllib.parse.urlsplit(raw if '//' not in raw[:2] else 'https:' + raw)
        params = urllib.parse.parse_qs(parsed.query or '')
        # Bing wraps every organic result in bing.com/ck/a?...&u=a1<base64url>
        # (its ampersands HTML-escaped as &amp;, which is why raw is html.unescape'd
        # above). Left unwrapped the link stays on bing.com and is then dropped by
        # the engine's own-domain skip, so every real Bing result silently vanished
        # and the HTTP tier fell through to whatever junk the next engine returned.
        if 'bing.com/ck/a' in low:
            token = (params.get('u') or [''])[0]
            if token[:2].lower() in ('a1', 'a2'):
                token = token[2:]
            if token:
                try:
                    decoded = base64.urlsafe_b64decode(
                        token + '=' * (-len(token) % 4)).decode('utf-8', 'replace')
                    if decoded.startswith('http'):
                        return decoded
                except Exception:
                    pass
        for key in ('uddg', 'q', 'u', 'url'):
            candidate = (params.get(key) or [''])[0]
            if candidate.startswith('http'):
                return urllib.parse.unquote(candidate)
    except Exception:
        pass
    return raw


def _search_http_tier(query: str, number_of_results: int,
                      allow_same_domain: bool = False) -> List[Dict]:
    """TIER 0 — try every plain-HTTP engine before any browser is launched.

    Deliberately SEPARATE from `_search_with_fallback`, which stays pure
    browser-chain logic: one function, one job. The practical payoff is that a
    successful HTTP answer means no browser is started at all — faster, lighter,
    and with no automation surface to detect in the first place."""
    for engine in _HTTP_ENGINES:
        try:
            hits = _http_search(engine, query, number_of_results,
                                allow_same_domain=allow_same_domain)
        except Exception as exc:
            logging.debug("   (%s) http tier error: %s", engine['name'], exc)
            continue
        if hits:
            logging.info("🔎 ENGINE '%s' answered with %d result(s) "
                         "(plain HTTP; browser not used for search)",
                         engine['name'], len(hits))
            return hits
    logging.info("   no plain-HTTP engine answered; falling back to the browser")
    return []


def _search_one_engine(page, engine: Dict, query: str, number_of_results: int,
                       allow_same_domain: bool = False) -> List[Dict]:
    """Run ONE engine by navigating straight to its result URL."""
    url = engine['url'].format(q=urllib.parse.quote_plus(query))
    page.goto(url, wait_until='domcontentloaded', timeout=30000)

    if not engine.get('js_free'):
        _dismiss_google_consent(page)

    try:
        page.wait_for_selector(engine['wait'], timeout=12000)
    except Exception:
        logging.debug("   (%s) result container did not appear; reading anyway",
                      engine['name'])

    # A JS-free page is already complete; a JS app needs a beat to render.
    page.wait_for_timeout(400 if engine.get('js_free') else 1500)

    hits = _extract_links_with_selectors(
        page, engine['selectors'], skip_domains=engine.get('skip'),
        allow_same_domain=allow_same_domain,
    )
    for hit in hits:
        hit['url'] = _unwrap_redirect(hit.get('url', ''))
    hits = [h for h in hits if str(h.get('url', '')).startswith('http')]
    return hits[:number_of_results]


def _search_with_fallback(page, query: str, number_of_results: int,
                          allow_same_domain: bool = False,
                          engine_order=None, attempts_per_engine: int = 2) -> List[Dict]:
    """Walk the browser-engine chain until one answers.

    Contract: this returns the first NON-EMPTY result set and logs which engine
    produced it, so a report can never imply Google answered when Mojeek did.
    Returning nothing means every engine was tried and every one came back
    empty — which is a real 'the network/engines refused us' signal, not a
    silent shrug."""
    names = [n.strip().lower() for n in (engine_order or []) if str(n).strip()]
    chain = ([e for n in names for e in _SEARCH_ENGINES if e['name'] == n]
             or list(_SEARCH_ENGINES))

    tried = []
    for engine in chain:
        for attempt in range(1, max(1, attempts_per_engine) + 1):
            try:
                hits = _search_one_engine(page, engine, query, number_of_results,
                                          allow_same_domain)
                if hits:
                    logging.info("🔎 ENGINE '%s' answered with %d result(s)%s",
                                 engine['name'], len(hits),
                                 '' if engine is chain[0] else ' (after fallback)')
                    return hits
                tried.append(f"{engine['name']}#{attempt}:empty")
            except Exception as exc:
                tried.append(f"{engine['name']}#{attempt}:{type(exc).__name__}")
            # polite, jittered backoff — hammering a refusing engine gets you
            # refused harder, and a moment's pause often clears a transient error
            time.sleep(min(4.0, 0.8 * attempt) + random.uniform(0.2, 0.9))
        logging.warning("   engine '%s' produced nothing; trying the next one",
                        engine['name'])

    logging.warning("⚠️ every engine returned empty: %s", ', '.join(tried) or 'none tried')
    return []


# ============================================================
# Core Googler Logic
# ============================================================

##############################################################################
# GOOGLE DORK VOCABULARY
#
# Google's documented search operators, in the form the builder emits them.
# Reference: https://support.google.com/websearch/answer/2466433 and
# https://developers.google.com/search/docs/crawling-indexing/indexable-file-types
#
# The SYNTAX RULES below are enforced mechanically by the builder rather than
# left to the caller, because every one of them silently degrades a query into
# an ordinary keyword search when broken:
#   * NO space after an operator colon  (`filetype: pdf` searches for the WORD
#     "filetype" and the word "pdf" -- it does not filter anything at all)
#   * exact titles go in DOUBLE QUOTES
#   * `OR` must be UPPERCASE (lowercase `or` is treated as a stop word)
#   * alternatives must be PARENTHESISED to bind correctly
#   * unwanted terms are prefixed with `-` and take NO space after the hyphen
##############################################################################

#: Convenience aliases so a caller can ask for a CLASS of file rather than
#: enumerating extensions. Google indexes all of these natively.
_FILETYPE_ALIASES = {
    'ebook':  ('epub', 'pdf', 'mobi', 'azw3'),
    'book':   ('epub', 'pdf'),
    'doc':    ('doc', 'docx'),
    'docs':   ('doc', 'docx', 'pdf'),
    'slides': ('ppt', 'pptx'),
    'sheet':  ('xls', 'xlsx', 'csv'),
    'sheets': ('xls', 'xlsx', 'csv'),
    'text':   ('txt', 'rtf'),
    'code':   ('py', 'js', 'java', 'c', 'cpp', 'go', 'rs'),
    'data':   ('csv', 'json', 'xml', 'sql'),
}

#: Libraries that publish PUBLIC-DOMAIN or openly-licensed full works. These are
#: the right default when someone wants a whole book: the work is lawfully
#: downloadable there, which a random file-locker result is not.
_TRUSTED_BOOK_SITES = ('gutenberg.org', 'standardebooks.org', 'archive.org',
                       'openlibrary.org', 'wikisource.org', 'doabooks.org',
                       'manybooks.net')

#: Open-access / institutional sources for papers and reports.
_TRUSTED_PAPER_SITES = ('.edu', '.gov', 'arxiv.org', 'ncbi.nlm.nih.gov',
                        'doaj.org', 'core.ac.uk', 'zenodo.org')

#: Terms that mark a page ABOUT a work rather than the work itself.
_NOISE_TERMS = ('review', 'summary', 'preview', 'excerpt', 'quotes')

#: Aggregators that answer almost every book query with a paywalled stub.
_NOISE_SITES = ('scribd.com', 'pinterest.com', 'slideshare.net', 'coursehero.com')

#: One-shot intents. Each expands into the operator fields below, and anything
#: the caller sets EXPLICITLY still wins (the preset only fills what is empty).
_PRESETS = {
    # the canonical "find me this actual book" query
    'book':        {'filetypes': ('epub', 'pdf'),
                    'exclude': _NOISE_TERMS,
                    'exclude_sites': _NOISE_SITES},
    # same, restricted to libraries that lawfully host complete works
    'book_public': {'filetypes': ('epub', 'pdf'),
                    'sites': _TRUSTED_BOOK_SITES},
    'paper':       {'filetypes': ('pdf',),
                    'sites': _TRUSTED_PAPER_SITES,
                    'exclude': ('slides', 'syllabus', 'worksheet')},
    'manual':      {'filetypes': ('pdf',), 'inurl': 'manual'},
    'docs':        {'filetypes': ('doc', 'docx', 'pdf')},
    'slides':      {'filetypes': ('ppt', 'pptx')},
    'sheets':      {'filetypes': ('xls', 'xlsx', 'csv')},
    # classic open-directory listing
    'directory':   {'intitle': 'index of'},
}


def _as_bool(value, default: bool = False) -> bool:
    """Tolerant truthiness for a YAML/wrapped-parser value.

    A wrapped chat-agent can hand a boolean through as the STRING "false", which
    is truthy in Python — so a naive bool() would silently turn `headless: false`
    into a headless run and re-create the exact blindness this file just fixed."""
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else '').strip().lower()
    if text in ('true', 'yes', '1', 'on'):
        return True
    if text in ('false', 'no', '0', 'off'):
        return False
    return default


def _as_terms(value) -> List[str]:
    """Accept a list/tuple OR a comma/space-separated string -> list of terms."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = re.split(r'[,\s]+', str(value))
    return [str(t).strip() for t in items if str(t).strip()]


def _strip_operator_prefix(value: str, *prefixes: str) -> str:
    """``filetype:pdf`` / ``ext:pdf`` / ``pdf`` all normalize to ``pdf`` so the
    prefix is never doubled when the caller already typed it."""
    v = str(value or '').strip()
    low = v.lower()
    for prefix in prefixes:
        if low.startswith(prefix.lower()):
            return v[len(prefix):].strip()
    return v


def _or_group(operator: str, values, *strip_prefixes: str) -> str:
    """Build ``(op:a OR op:b)`` — parenthesised, with OR UPPERCASE.

    A single value needs no group (``op:a``); an empty list contributes nothing.
    Without the parentheses Google binds the OR to only the adjacent term, which
    is the difference between "epub or pdf" and "epub, or anything at all"."""
    terms = []
    for raw in _as_terms(values):
        v = _strip_operator_prefix(raw, *(strip_prefixes or (operator + ':',)))
        if v and v not in terms:
            terms.append(v)
    if not terms:
        return ''
    if len(terms) == 1:
        return f'{operator}:{terms[0]}'
    return '(' + ' OR '.join(f'{operator}:{t}' for t in terms) + ')'


def _expand_filetypes(values) -> List[str]:
    """Resolve class aliases (``ebook`` -> epub/pdf/mobi/azw3) and bare/prefixed
    extensions into a de-duplicated extension list."""
    out: List[str] = []
    for raw in _as_terms(values):
        ext = _strip_operator_prefix(raw, 'filetype:', 'ext:').lstrip('.').lower()
        for resolved in _FILETYPE_ALIASES.get(ext, (ext,)):
            if resolved and resolved not in out:
                out.append(resolved)
    return out


def _apply_preset(config: Dict) -> Dict:
    """Merge a named preset UNDER the caller's own fields.

    Explicit configuration always wins: the preset only fills a field the caller
    left empty, so `preset: book` + `filetypes: epub` searches epub only."""
    name = str(config.get('preset', '') or '').strip().lower()
    if not name or name in ('none', 'off'):
        return dict(config)
    preset = _PRESETS.get(name)
    if preset is None:
        logging.warning("⚠️ unknown preset '%s' — ignoring it (known: %s)",
                        name, ', '.join(sorted(_PRESETS)))
        return dict(config)
    merged = dict(config)
    for key, value in preset.items():
        existing = merged.get(key)
        if existing in (None, '', [], (), {}):
            merged[key] = list(value) if isinstance(value, (list, tuple)) else value
    logging.info("🔎 preset '%s' applied", name)
    return merged


def _query_has_site_operator(query: str) -> bool:
    """True if the query already contains a ``site:`` operator (case-insensitive).

    NOTE the leading ``(`` in the character class: an OR-group is emitted as
    ``(site:a OR site:b)``, and without it a multi-site dork would NOT be
    recognised as site-restricted, so same-domain de-dup would silently throw
    away every hit but the first from each host."""
    return bool(re.search(r'(?:^|\s|\()site:\S', query or '', re.IGNORECASE))


def _resolve_allow_same_domain(config: Dict, effective_query: str) -> bool:
    """Same-domain de-dup is ON when explicitly configured (``allow_same_domain: true``)
    OR when the effective query carries a ``site:`` operator (single-site dork)."""
    return _as_bool(config.get('allow_same_domain', False), False) or \
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
    config = _apply_preset(config)
    parts: List[str] = []

    # 1) the exact phrase leads, because Google weights leading terms most
    exact = str(config.get('exact', '') or '').strip().strip('"')
    if exact:
        parts.append(f'"{exact}"')

    # 2) the caller's freeform query is preserved VERBATIM — an existing dork
    #    typed by hand keeps working unchanged
    raw = str(config.get('query', '') or '').strip()
    if raw:
        parts.append(raw)

    # 3) author is a convenience for book hunts: a quoted phrase, not an operator
    author = str(config.get('author', '') or '').strip().strip('"')
    if author:
        parts.append(f'"{author}"')

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

    # 4) single-value operators. `all*` variants apply to EVERY following word,
    #    so they are emitted once and never quoted.
    for field_name, operator, quote in (
        ('intitle', 'intitle', True),
        ('allintitle', 'allintitle', False),
        ('inurl', 'inurl', False),
        ('allinurl', 'allinurl', False),
        ('intext', 'intext', True),
        ('allintext', 'allintext', False),
        ('inanchor', 'inanchor', True),
        ('allinanchor', 'allinanchor', False),
        ('related', 'related', False),
        ('cache', 'cache', False),
        ('define', 'define', False),
        ('source', 'source', False),
        ('before', 'before', False),
        ('after', 'after', False),
    ):
        built = _operator(config.get(field_name), operator, quote)
        if built:
            parts.append(built)

    # 5) SITES — `sites` (plural) becomes an OR-group; `site` (singular) is kept
    #    for back-compat and merged in, so both spellings work together.
    site_values = _as_terms(config.get('sites')) + _as_terms(config.get('site'))
    site_clause = _or_group('site', site_values)
    if site_clause:
        parts.append(site_clause)

    # 6) FILETYPES — the headline capability. Aliases expand (`ebook` ->
    #    epub/pdf/mobi/azw3) and several types become a parenthesised OR-group,
    #    which is what makes ONE query catch a work in whichever format exists.
    filetype_values = _expand_filetypes(
        _as_terms(config.get('filetypes')) + _as_terms(config.get('filetype')))
    filetype_clause = _or_group('filetype', filetype_values)
    if filetype_clause:
        parts.append(filetype_clause)

    # 7) alternatives: (a OR b OR c)
    or_terms = _as_terms(config.get('or_terms'))
    if len(or_terms) == 1:
        parts.append(or_terms[0])
    elif or_terms:
        parts.append('(' + ' OR '.join(or_terms) + ')')

    # 8) proximity: x AROUND(n) y  — n is the max words BETWEEN the two terms
    around = _as_terms(config.get('around_terms'))
    if len(around) >= 2:
        try:
            distance = int(str(config.get('around_distance', 5)).strip() or 5)
        except (TypeError, ValueError):
            distance = 5
        parts.append(f'{around[0]} AROUND({max(1, distance)}) {around[1]}')

    # 9) numeric range: 2020..2026  (prices, years, model numbers)
    numeric_range = str(config.get('numeric_range', '') or '').strip()
    if numeric_range:
        parts.append(numeric_range if '..' in numeric_range
                     else numeric_range.replace('-', '..', 1))

    # 10) EXCLUSIONS — `-term`, no space after the hyphen or Google ignores it
    for term in _as_terms(config.get('exclude')):
        parts.append(term if term.startswith('-') else f'-{term}')

    # 11) excluded sites — `-site:x`, the fastest way to kill paywalled stubs
    for host in _as_terms(config.get('exclude_sites')):
        host = _strip_operator_prefix(host.lstrip('-'), 'site:')
        if host:
            parts.append(f'-site:{host}')

    final = ' '.join(p for p in parts if p).strip()
    final = re.sub(r'\s{2,}', ' ', final)
    if final != raw:
        logging.info("🔍 DORK: %s", final)
    return final


def googler_search(query: str, number_of_results: int = 5,
                   content_mode: str = "text",
                   allow_same_domain: bool = False,
                   headless: bool = False,
                   engines=None,
                   attempts_per_engine: int = 2) -> List[Dict]:
    """
    Search the resilient two-tier route chain, then either (a) list result links,
    or (b) fetch the top N result pages with Playwright and extract their content.

    With no explicit engine pin, Tier 0 tries four server-rendered routes through
    plain HTTP before Playwright is imported or a browser is launched. If all are
    empty, Tier 1 walks seven browser routes with bounded retries. A `links_only`
    Tier-0 success returns without launching a browser; text/raw mode may still use
    one to fetch result bodies. Full advanced-operator semantics are Google-specific;
    fallback routes may return broader results and are named in logs.
    Automatically skips binary content (PDFs, images, etc.) in the fetch modes.

    content_mode:
      - "text":        Extract rendered visible text from each result page (default)
      - "raw":         Return raw page HTML from each result page
      - "links_only":  Do NOT fetch result pages — return just the SERP hit list
                       (url + title). Ideal for dork enumeration / recon and far faster;
                       the URLs can flow through Parametrizer into Apirer for an
                       authorized download, then File-Extractor/File-Interpreter.

    allow_same_domain:
      When True (auto-enabled by main() when the query contains a ``site:`` operator),
      result de-duplication is by full URL instead of by domain, so a single-site dork
      can return many distinct URLs from the same host (Blocker #1 fix).

    Returns a list of result dicts.
    """
    # links_only is cheap (no page fetch) so it may enumerate more hits per run.
    max_cap = 50 if content_mode == "links_only" else 10
    if number_of_results > max_cap:
        number_of_results = max_cap
    if number_of_results < 1:
        number_of_results = 1

    results: List[Dict] = []
    requested_engines = [
        str(name).strip().lower()
        for name in (engines or [])
        if str(name).strip()
    ]

    # Tier 0 must run before Playwright is even imported. Besides making the
    # ordering real rather than aspirational, this lets a links-only search
    # succeed on a machine whose browser runtime is temporarily unavailable.
    hits = []
    if not requested_engines:
        hits = _search_http_tier(query, number_of_results, allow_same_domain)

    if hits and content_mode == "links_only":
        for i, hit in enumerate(hits, 1):
            results.append({
                "index": i,
                "url": hit.get("url", ""),
                "title": hit.get("title", ""),
                "status_code": "listed",
                "content_length": 0,
            })
        return results

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
        return []

    try:
        with sync_playwright() as p:
            # REAL CHROME FIRST. A measured 2026-08-23 comparison: the bundled
            # headless Chromium got ZERO results for every query while a real
            # headed Chrome answered immediately. `channel="chrome"` uses the
            # browser actually installed on the machine — same engine version,
            # same fonts, same TLS profile as the user's own browsing — and
            # falls back to bundled Chromium when Chrome is absent.
            launch_kwargs = {'headless': headless, 'args': _BROWSER_ARGS}
            try:
                browser = p.chromium.launch(channel='chrome', **launch_kwargs)
                logging.info("🌐 browser: real Chrome (%s)",
                             'headless' if headless else 'HEADED/visible')
            except Exception:
                browser = p.chromium.launch(**launch_kwargs)
                logging.info("🌐 browser: bundled Chromium (%s) — Chrome not installed",
                             'headless' if headless else 'HEADED/visible')

            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/Mexico_City',
                java_script_enabled=True,
                extra_http_headers={
                    # A browser that asks for HTML but sends no Accept-Language
                    # or Accept header reads as a script to every CDN in front of
                    # a search engine. These are simply what Chrome itself sends.
                    'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
                    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
                               'image/avif,image/webp,*/*;q=0.8'),
                    'Upgrade-Insecure-Requests': '1',
                },
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            try:
                # Tier 0 may already have supplied hits. Otherwise walk the
                # browser chain; explicit engine pins arrive here directly.
                if not hits:
                    hits = _search_with_fallback(
                        page, query, number_of_results, allow_same_domain,
                        engine_order=requested_engines,
                        attempts_per_engine=attempts_per_engine,
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

        # HEADED BY DEFAULT (2026-08-23). Measured that day: bundled headless
        # Chromium returned ZERO results for every query — including a plain
        # keyword control with no operators — while a headed real Chrome
        # answered immediately. Headless is therefore opt-in and documented as
        # the degraded path, not the default.
        headless = _as_bool(config.get('headless', False), False)
        engines = config.get('engines') or []
        if isinstance(engines, str):
            engines = [e for e in re.split(r'[,\s]+', engines) if e]
        try:
            attempts_per_engine = max(1, int(config.get('attempts_per_engine', 2)))
        except (TypeError, ValueError):
            attempts_per_engine = 2

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
                                     content_mode, allow_same_domain,
                                     headless=headless, engines=engines,
                                     attempts_per_engine=attempts_per_engine)

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
