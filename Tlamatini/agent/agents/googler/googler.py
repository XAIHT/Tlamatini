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
import json
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

# The resilience core travels as a FLAT SIBLING of this script (in the template
# folder and in every pool copy). Its folder is put on sys.path explicitly
# because the test-suite loads this file through importlib, where it is not.
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import googler_engines as E

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

# `window_mode: offscreen` (2026-09-28): a REAL, headed Chrome, the fingerprint
# search engines trust, placed off the visible desktop and told not to
# throttle itself for being "occluded". Headless is what engines refuse first;
# this keeps the trusted fingerprint without putting a window in the way.
_OFFSCREEN_ARGS = [
    '--window-position=-32000,-32000',
    '--window-size=1280,900',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    '--disable-features=CalculateNativeWinOcclusion',
]

_USER_AGENT = E.CHROME_UA

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


_DEFAULT_SKIP_DOMAINS = set(E.DEFAULT_SKIP_DOMAINS)


def _dedup_links(links: List[Dict], skip_domains=None,
                 allow_same_domain: bool = False) -> List[Dict]:
    """Filter junk / skip-domain links and de-duplicate a list of {url, title} dicts.

    De-dup key:
      - allow_same_domain=False (legacy): de-dup by DOMAIN -> at most one result per host.
      - allow_same_domain=True:           de-dup by full URL -> keep many results per host.

    The second mode is what makes ``site:`` / ``filetype:`` dork enumeration usable: a
    single-site dork legitimately returns dozens of distinct URLs on ONE domain, and the
    legacy by-domain collapse would discard all but the first (Blocker #1).

    ONE definition for both tiers: this delegates to ``googler_engines.dedup_links``.
    """
    if skip_domains is None:
        skip_domains = set(_DEFAULT_SKIP_DOMAINS)
    return E.dedup_links(links, skip_domains=skip_domains, allow_same_domain=allow_same_domain)


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


# The visible text of the result block around an anchor. It is what lets the
# relevance check recognise a CORRECT answer whose link text does not repeat
# the query (Brave's "pg15.epub" is Moby Dick, titled only "Project Gutenberg").
_SNIPPET_JS = (
    "e => { const box = e.closest('li, article, [data-testid=\"result\"], .g, .b_algo, "
    ".algo, .result, .snippet, .web-result'); "
    "return box ? (box.innerText || '').slice(0, 600) : ''; }"
)

_HARVEST_JS = """() => Array.from(document.querySelectorAll('a[href]')).slice(0, 500).map(a => {
  const box = a.closest('li, article, [data-testid="result"], .g, .b_algo, .algo, .result, .snippet, .web-result');
  return [a.href || '', (a.innerText || '').trim().slice(0, 200),
          box ? (box.innerText || '').trim().slice(0, 600) : ''];
})"""


def _extract_link_snippet(elem) -> str:
    try:
        text = elem.evaluate(_SNIPPET_JS)
    except Exception:
        return ''
    return E.clean_text(text)[:400] if isinstance(text, str) else ''


def _extract_links_with_selectors(page, selectors, skip_domains=None,
                                  allow_same_domain: bool = False) -> List[Dict]:
    """Try each selector in order; return the first non-empty list of result dicts
    ({url, title, snippet}), filtered + de-duplicated by ``_dedup_links``.

    Redirectors are unwrapped BEFORE filtering (2026-09-28). DuckDuckGo's
    ``//duckduckgo.com/l/?uddg=...`` and Yahoo's ``r.search.yahoo.com/...RU=``
    links used to be dropped here as "not http" / "the engine's own domain",
    so a route could answer perfectly and still hand back nothing."""
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        if not elements:
            continue

        raw: List[Dict] = []
        for elem in elements:
            try:
                href = elem.get_attribute("href")
            except Exception:
                continue
            if not href:
                continue
            raw.append({'url': E.unwrap_redirect(href),
                        'title': _extract_link_title(elem),
                        'snippet': _extract_link_snippet(elem)})

        deduped = _dedup_links(raw, skip_domains, allow_same_domain)
        if deduped:
            logging.info(f"Selector '{selector}' matched {len(deduped)} link(s).")
            return deduped

    return []


def _harvest_page_anchors(page, engine: Dict, allow_same_domain: bool = False) -> List[Dict]:
    """Selector-free fallback: every outbound anchor of the page, with its text.

    CSS class names are what go stale; an off-site href is what a result cannot
    stop being. Relevance is judged afterwards, so a page of junk links never
    becomes an answer."""
    try:
        rows = page.evaluate(_HARVEST_JS)
    except Exception:
        return []
    own = tuple(str(s).lower() for s in (engine.get('skip') or ()))
    raw: List[Dict] = []
    for row in rows or []:
        try:
            href, title, snippet = row[0], row[1], row[2]
        except Exception:
            continue
        target = E.unwrap_redirect(href)
        if not target.startswith('http'):
            continue
        low = target.lower()
        if any(o and o in low for o in own) or any(j in low for j in E.GLOBAL_JUNK):
            continue
        raw.append({'url': target, 'title': E.clean_text(title),
                    'snippet': E.clean_text(snippet)[:400]})
    return _dedup_links(raw, None, allow_same_domain)


def _is_binary_url(url: str) -> bool:
    """Check if the URL path ends with a known binary file extension."""
    return E.is_binary_url(url)


def _is_binary_content_type(content_type: str) -> bool:
    """Check if Content-Type indicates binary / non-readable content."""
    return E.is_binary_content_type(content_type)


def _fetch_page_text(page, url: str, timeout_ms: int = 30000) -> Dict:
    """
    Navigate a Playwright page to a URL and extract rendered readable text.

    A BINARY hit is NOT an error, it is the answer: a ``filetype:`` hunt
    returns PDFs/EPUBs by construction, and what the caller wants is the
    download URL. So it comes back as a ``kind: "file"`` record.
    Returns a dict with url, status_code, content_length, content (or error).
    """
    if _is_binary_url(url):
        logging.info(f"Located a downloadable file (not fetched as text): {url}")
        return {"url": url, "kind": "file", "filetype": E.url_extension(url),
                "note": "downloadable file located (not fetched as text)"}

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as e:
        return {"url": url, "error": str(e)}

    if not response:
        return {"url": url, "error": "No response received"}

    status = response.status

    # Check Content-Type header for binary content
    content_type = response.headers.get('content-type', '')
    if _is_binary_content_type(content_type):
        logging.info(f"Located a downloadable file ({content_type}): {url}")
        return {"url": url, "kind": "file", "status_code": status,
                "content_type": content_type, "filetype": E.url_extension(url),
                "note": "downloadable file located (not fetched as text)"}

    # Wait for JS rendering to complete (bounded: a page that never goes idle
    # must not eat the search budget)
    try:
        page.wait_for_load_state("networkidle", timeout=max(1000, min(5000, timeout_ms // 3)))
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
        "fetched_by": "browser",
    }


##############################################################################
# THE SEARCH-ROUTE CHAIN  (rebuilt 2026-09-28 after a second measured total
# failure; the first was 2026-08-23)
#
# What Angela's machine measured on 2026-09-28, route by route:
#   plain HTTP  : DuckDuckGo html/lite -> 202 "bots use DuckDuckGo too";
#                 Brave -> 429 captcha; Mojeek -> captcha, then 403; Yahoo ->
#                 bot verification; Startpage -> /errors/; Google -> "Your
#                 browser isn't supported any more"; Bing -> 200 with POISONED
#                 results (Poki games for "Humanity's Last Exam").
#   real Chrome : Google -> /sorry/ CAPTCHA; DuckDuckGo -> anomaly page;
#                 Mojeek -> 403; Bing -> captcha; BRAVE and YAHOO -> correct.
#
# Nothing about that is stable: the same route that answers today refuses
# tomorrow, and the answer differs per machine and per network. So the chain is
# no longer a fixed order to walk blindly, it is a CANDIDATE LIST that the
# health ledger (googler_engines.EngineHealth) re-orders on every run: a route
# that answered recently goes first, a route that just refused is skipped while
# it cools down, and every route that refuses is never asked twice in one run.
#
# NOTE ON OPERATOR SUPPORT: `site:` and `filetype:` work on all of these.
# Google alone honours the full set: `before:`/`after:`/`AROUND()`/numeric
# ranges are Google-only, so a dork that falls through to another engine may
# return broader results. The route that actually answered is always logged.
##############################################################################

_SEARCH_ENGINES = [
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
        'url': 'https://search.brave.com/search?q={q}&source=web',
        'wait': '#results, .snippet',
        'selectors': ['#results .snippet a[href^="http"]', '.snippet a[href^="http"]',
                      '#results a[href^="http"]'],
        'skip': {'brave.com', 'torproject.org'},
        'js_free': False,
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
        'name': 'duckduckgo-html',
        'url': 'https://html.duckduckgo.com/html/?q={q}',
        'wait': 'div.result, div.web-result, a.result__a',
        'selectors': ['a.result__a', 'h2.result__title a', 'div.result a[href]'],
        'skip': {'duckduckgo.com'},
        'js_free': True,
    },
    {
        'name': 'yahoo',
        'url': 'https://search.yahoo.com/search?p={q}&n=30',
        'wait': '#web, #main',
        'selectors': ['#web h3 a', 'div.algo h3 a', '#web a[href]'],
        'skip': {'yahoo.com', 'yahoo.net', 'yimg.com'},
        'js_free': False,
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
        'name': 'startpage',
        'url': 'https://www.startpage.com/sp/search?query={q}',
        'wait': '.w-gl__result, .result',
        'selectors': ['.w-gl__result a[href^="http"]', '.result a[href^="http"]'],
        'skip': {'startpage.com'},
        'js_free': False,
    },
]


##############################################################################
# TIER 0: PLAIN-HTTP ENGINES (no browser at all)
#
# Measured 2026-08-23: a bare `urllib` request with ordinary browser headers
# got real results from html.duckduckgo.com and www.bing.com while the SAME
# endpoints returned nothing through Playwright (stale CSS selectors). For a
# server-rendered results page a browser is not an advantage, it is the
# liability: no automation flag to leak, no fingerprint, no consent dialog.
#
# Measured 2026-09-28: on a network the engines have flagged, the same tier is
# refused almost everywhere, and Bing POISONS its answer instead of refusing.
# So the tier now runs HEDGED (a slow route cannot stall the others), every
# result set is RELEVANCE-CHECKED before it is believed, and every refusal is
# remembered so the next search does not provoke the same engine again.
# The implementation lives in googler_engines (http_tier_search).
##############################################################################

_HTTP_ENGINES = [dict(engine) for engine in E.HTTP_ENGINES]


def _unwrap_redirect(url: str) -> str:
    """Return the real destination behind a search engine's redirector.

    ONE definition for both tiers: delegates to ``googler_engines.unwrap_redirect``
    (DuckDuckGo ``uddg=``, Google ``/url?q=``, Yahoo ``/RU=``, Bing ``ck/a?u=a1``)."""
    return E.unwrap_redirect(url)


def _search_http_tier(query: str, number_of_results: int,
                      allow_same_domain: bool = False, *, deadline=None,
                      health=None, attempts=None, terms=None) -> List[Dict]:
    """TIER 0: try the plain-HTTP engines, hedged, before any browser is launched.

    Deliberately SEPARATE from `_search_with_fallback`, which stays pure
    browser-chain logic: one function, one job. A successful HTTP answer means
    no browser is started at all: faster, lighter, and nothing to detect."""
    deadline = deadline if deadline is not None else E.Deadline(20)
    health = health if health is not None else E.EngineHealth()
    terms = terms if terms is not None else E.parse_query_terms(query)
    hits, winner, tier_attempts = E.http_tier_search(
        query, number_of_results, terms=terms, deadline=deadline, health=health,
        allow_same_domain=allow_same_domain)
    if attempts is not None:
        attempts.extend(tier_attempts)
    for attempt in tier_attempts:
        if attempt.get('verdict') not in ('ok', 'abandoned'):
            logging.info("   (http) %-16s %-10s %s", attempt.get('engine'),
                         attempt.get('verdict'), attempt.get('detail', ''))
    if winner:
        logging.info("🔎 ENGINE '%s' answered with %d result(s) "
                     "(plain HTTP; browser not used for search)", winner.get('engine'), len(hits))
        return hits
    logging.info("   no plain-HTTP engine answered; moving on")
    return []


def _page_state(page, response):
    """(status_code, final_url, html) of the page, defensively."""
    status = 0
    try:
        status = int(getattr(response, 'status', 0) or 0) if response is not None else 0
    except Exception:
        status = 0
    final_url = ''
    try:
        final_url = str(getattr(page, 'url', '') or '')
    except Exception:
        final_url = ''
    body = ''
    try:
        body = page.content() or ''
    except Exception:
        body = ''
    return status, final_url, body


def _judge_engine_page(page, response, engine: Dict, query: str, number_of_results: int,
                       allow_same_domain: bool, terms):
    """Harvest a results page and decide what it IS: an answer, a refusal, a
    poisoned page, or an honest "no results". Returns (hits, verdict, detail)."""
    hits = _extract_links_with_selectors(
        page, engine['selectors'], skip_domains=engine.get('skip'),
        allow_same_domain=allow_same_domain,
    )
    if not hits:
        hits = _harvest_page_anchors(page, engine, allow_same_domain)
    hits = [h for h in hits if str(h.get('url', '')).startswith('http')]
    hits_verdict, ordered, _relevant = E.assess_hits(hits, terms)
    status, final_url, body = _page_state(page, response)
    verdict, detail = E.classify_response(status_code=status, final_url=final_url,
                                          body=body, hits_verdict=hits_verdict)
    return (ordered[:number_of_results] if verdict == 'ok' else []), verdict, detail


def _wait_for_human_captcha(page, engine: Dict, query: str, number_of_results: int,
                            allow_same_domain: bool, terms, wait_seconds: float, deadline):
    """VISIBLE mode only: give a human the chance to solve the CAPTCHA.

    A search engine that has flagged a network will not un-flag it for a
    script, but it will for a person. The persistent Chrome profile then keeps
    the clearance cookie, so the NEXT searches work too."""
    limit = float(wait_seconds or 0)
    if deadline is not None:
        limit = min(limit, deadline.remaining() - 2.0)
    if limit < 3.0:
        return [], 'blocked', 'captcha (no time left to wait for a human)'
    logging.warning("🧩 %s is showing a CAPTCHA. Solve it in the Googler Chrome window; "
                    "waiting up to %ds...", engine['name'], int(limit))
    end = time.monotonic() + limit
    while time.monotonic() < end:
        try:
            page.wait_for_timeout(1500)
        except Exception:
            break
        hits, verdict, _detail = _judge_engine_page(page, None, engine, query, number_of_results,
                                                    allow_same_domain, terms)
        if verdict == 'ok':
            logging.info("🧩 CAPTCHA solved: '%s' answered", engine['name'])
            return hits, 'ok', 'answered after a human solved the CAPTCHA'
    return [], 'blocked', 'captcha (not solved in time)'


def _search_one_engine(page, engine: Dict, query: str, number_of_results: int,
                       allow_same_domain: bool = False, report=None, *, terms=None,
                       deadline=None, captcha_wait_seconds: float = 0) -> List[Dict]:
    """Run ONE engine by navigating straight to its result URL.

    ``report`` (optional dict) receives ``verdict`` / ``detail`` / ``ms`` so the
    caller can tell a refusal from an empty page and never retry a CAPTCHA."""
    report = report if report is not None else {}
    started = time.monotonic()
    terms = terms if terms is not None else E.parse_query_terms(query)
    url = engine['url'].format(q=urllib.parse.quote_plus(query))
    goto_ms = 30000
    wait_ms = 12000
    if deadline is not None:
        goto_ms = int(max(3.0, min(20.0, deadline.remaining() - 1.0)) * 1000)
        wait_ms = int(max(1.0, min(6.0, deadline.remaining() - 1.0)) * 1000)
    response = page.goto(url, wait_until='domcontentloaded', timeout=goto_ms)

    if not engine.get('js_free'):
        _dismiss_google_consent(page)

    try:
        page.wait_for_selector(engine['wait'], timeout=wait_ms)
    except Exception:
        logging.debug("   (%s) result container did not appear; reading anyway",
                      engine['name'])

    # A JS-free page is already complete; a JS app needs a beat to render.
    page.wait_for_timeout(400 if engine.get('js_free') else 1200)

    hits, verdict, detail = _judge_engine_page(page, response, engine, query, number_of_results,
                                               allow_same_domain, terms)
    if verdict == 'blocked' and captcha_wait_seconds and captcha_wait_seconds > 0:
        hits, verdict, detail = _wait_for_human_captcha(page, engine, query, number_of_results,
                                                        allow_same_domain, terms,
                                                        captcha_wait_seconds, deadline)
    report.update(verdict=verdict, detail=detail, ms=int((time.monotonic() - started) * 1000))
    return hits


def _search_with_fallback(page, query: str, number_of_results: int,
                          allow_same_domain: bool = False,
                          engine_order=None, attempts_per_engine: int = 2, *,
                          deadline=None, health=None, attempts=None, terms=None,
                          captcha_wait_seconds: float = 0) -> List[Dict]:
    """Walk the browser-route chain until one answers.

    Contract: this returns the first NON-EMPTY, RELEVANT result set and logs
    which engine produced it, so a report can never imply Google answered when
    Brave did. A route that REFUSED (CAPTCHA, anomaly page, poisoned results)
    is never retried in the same run: asking again only makes the block last
    longer. With a ``health`` ledger and no explicit ``engine_order``, routes
    that answered recently go first and routes still cooling down are skipped.
    Returning nothing means every route was tried (or had no time left)."""
    names = [n.strip().lower() for n in (engine_order or []) if str(n).strip()]
    chain = ([e for n in names for e in _SEARCH_ENGINES if e['name'] == n]
             or list(_SEARCH_ENGINES))
    if health is not None and not names:
        by_key = {'browser:%s' % e['name']: e for e in chain}
        runnable, skipped = health.plan(list(by_key))
        for key in skipped:
            left = int(health.cooling_left(key))
            logging.info("   ⏭️ %s skipped: cooling down %ds after it refused this machine",
                         by_key[key]['name'], left)
            if attempts is not None:
                attempts.append(E.attempt_record(by_key[key]['name'], 'browser', 'skipped',
                                                 'cooling down %ds' % left))
        chain = [by_key[key] for key in runnable]
    terms = terms if terms is not None else E.parse_query_terms(query)

    tried = []
    for engine in chain:
        if deadline is not None and deadline.remaining() < 4.0:
            logging.warning("   ⏱️ no time left in the search budget for '%s'", engine['name'])
            break
        for attempt in range(1, max(1, attempts_per_engine) + 1):
            report: Dict = {}
            try:
                hits = _search_one_engine(page, engine, query, number_of_results,
                                          allow_same_domain, report=report, terms=terms,
                                          deadline=deadline,
                                          captcha_wait_seconds=captcha_wait_seconds)
                verdict = report.get('verdict') or ('ok' if hits else 'empty')
            except Exception as exc:
                hits, verdict = [], 'error'
                first_line = str(exc).splitlines()[0] if str(exc) else ''
                report['detail'] = f"{type(exc).__name__}: {first_line[:160]}"
            detail = report.get('detail', '')
            if attempts is not None:
                attempts.append(E.attempt_record(engine['name'], 'browser', verdict, detail,
                                                 report.get('ms', 0), attempt=attempt))
            if health is not None:
                health.record('browser:%s' % engine['name'], verdict, detail)
            if hits and verdict == 'ok':
                logging.info("🔎 ENGINE '%s' answered with %d result(s)%s",
                             engine['name'], len(hits),
                             '' if engine is chain[0] else ' (after fallback)')
                return hits
            tried.append(f"{engine['name']}#{attempt}:{verdict}")
            if verdict in ('blocked', 'poisoned', 'no_matches'):
                logging.warning("   engine '%s' %s (%s); not asking it again this run",
                                engine['name'], verdict, detail)
                break
            if deadline is not None and deadline.remaining() < 6.0:
                break
            # polite, jittered backoff: a moment's pause often clears a
            # transient error, and hammering is what gets a network flagged
            time.sleep(min(4.0, 0.8 * attempt) + random.uniform(0.2, 0.9))
        logging.warning("   engine '%s' produced nothing; trying the next one",
                        engine['name'])

    logging.warning("⚠️ every browser route came back without an answer: %s",
                    ', '.join(tried) or 'none tried')
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


##############################################################################
# THE SEARCH ORCHESTRATOR  (2026-09-28)
#
# One wall-clock budget (``deadline_seconds``) covers the WHOLE search:
#   TIER 0  plain-HTTP engines, hedged, health-ordered     (no browser)
#   TIER 1  real Chrome (persistent profile), health-ordered routes
#   TIER 2  open knowledge sources: Wikipedia, arXiv, Hacker News, GitHub,
#           OpenAlex, the Internet Archive (and Gutenberg for book hunts)
#   FETCH   the result pages, in parallel, over plain HTTP first; a page that
#           comes back as a thin JavaScript shell is re-rendered by the browser
#           when there is time left
# Every stage checks the budget before it starts and bounds itself by it, so a
# search ALWAYS ends on time, and its report says exactly what happened:
# which route answered, which refused (and why), and which are cooling down.
##############################################################################

_DEFAULT_DEADLINE_SECONDS = 120.0
#: Seconds kept back for Tier 2 so a slow browser tier can never starve it.
_OPEN_SOURCES_RESERVE = 8.0
#: Seconds kept back for fetching result pages in text/raw mode.
_FETCH_RESERVE = 15.0
_WINDOW_MODES = ('visible', 'offscreen', 'headless')


def _as_float(value, default: float, lo: float, hi: float) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _resolve_window_mode(value, headless: bool) -> str:
    """``window_mode`` wins; otherwise the legacy ``headless`` flag decides."""
    mode = str(value or '').strip().lower()
    if mode in _WINDOW_MODES:
        return mode
    return 'headless' if headless else 'visible'


def _resolve_profile_dir(value) -> str:
    """'' / None -> Googler's own persistent Chrome profile; 'none' -> ephemeral."""
    text = str(value or '').strip()
    if text.lower() in ('none', 'off', 'false', 'ephemeral', 'no'):
        return ''
    return text or E.default_profile_dir()


class _BrowserSession:
    """One lazily started browser for the whole search.

    Real Chrome first (the fingerprint engines trust), bundled Chromium as the
    fallback. A PERSISTENT profile when possible, so consent choices and CAPTCHA
    clearances survive between searches like a returning visitor's; an
    ephemeral context when that profile is busy (another Googler is using it)."""

    def __init__(self, window_mode: str = 'visible', profile_dir: str = ''):
        self.window_mode = window_mode
        self.profile_dir = profile_dir
        self.page = None
        self.description = ''
        self._manager = None
        self._browser = None
        self._context = None

    def start(self):
        from playwright.sync_api import sync_playwright  # ImportError is the caller's signal
        self._manager = sync_playwright()
        playwright = self._manager.__enter__()
        headless = self.window_mode == 'headless'
        args = list(_BROWSER_ARGS) + (list(_OFFSCREEN_ARGS) if self.window_mode == 'offscreen' else [])
        context_options = {
            'user_agent': _USER_AGENT,
            'viewport': {'width': 1920, 'height': 1080},
            'locale': 'en-US',
            'timezone_id': 'America/Mexico_City',
            'java_script_enabled': True,
            'extra_http_headers': {
                # A browser that asks for HTML but sends no Accept-Language
                # or Accept header reads as a script to every CDN in front of
                # a search engine. These are simply what Chrome itself sends.
                'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
                'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
                           'image/avif,image/webp,*/*;q=0.8'),
                'Upgrade-Insecure-Requests': '1',
            },
        }
        chromium = playwright.chromium
        if self.profile_dir and hasattr(chromium, 'launch_persistent_context'):
            try:
                os.makedirs(self.profile_dir, exist_ok=True)
                self._context = chromium.launch_persistent_context(
                    self.profile_dir, channel='chrome', headless=headless, args=args,
                    **context_options)
                self.description = 'real Chrome, persistent profile'
            except Exception as exc:
                first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                logging.info("   persistent Chrome profile unavailable (%s); using a fresh context",
                             first_line[:160])
                self._context = None
        if self._context is None:
            # REAL CHROME FIRST. Measured 2026-08-23: the bundled headless
            # Chromium got ZERO results for every query while a real headed
            # Chrome answered immediately.
            try:
                self._browser = chromium.launch(channel='chrome', headless=headless, args=args)
                self.description = 'real Chrome'
            except Exception:
                self._browser = chromium.launch(headless=headless, args=args)
                self.description = 'bundled Chromium (Chrome not installed)'
            self._context = self._browser.new_context(**context_options)
        try:
            self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception:
            pass
        try:
            pages = list(getattr(self._context, 'pages', None) or [])
        except Exception:
            pages = []
        self.page = pages[0] if pages else self._context.new_page()
        logging.info("🌐 browser: %s (%s)", self.description,
                     {'headless': 'headless', 'offscreen': 'real window, off-screen',
                      'visible': 'VISIBLE window'}.get(self.window_mode, self.window_mode))
        return self.page

    def close(self):
        for closer in (getattr(self._context, 'close', None), getattr(self._browser, 'close', None)):
            if closer is None:
                continue
            try:
                closer()
            except Exception:
                pass
        if self._manager is not None:
            try:
                self._manager.__exit__(None, None, None)
            except Exception:
                pass
        self._manager = None


def _open_browser_session(window_mode: str, profile_dir):
    """Start a browser, or explain in the log why there is none. Never raises."""
    session = _BrowserSession(window_mode=window_mode, profile_dir=_resolve_profile_dir(profile_dir))
    try:
        session.start()
        return session
    except ImportError:
        logging.error("Playwright is not installed. Install with: pip install playwright && "
                      "playwright install chromium")
    except Exception as e:
        logging.error(f"Playwright launch failed: {e}")
    session.close()
    return None


def _listed_results(hits: List[Dict]) -> List[Dict]:
    results = []
    for i, hit in enumerate(hits, 1):
        entry = {
            "index": i,
            "url": hit.get("url", ""),
            "title": hit.get("title", ""),
            "status_code": "listed",
            "content_length": 0,
        }
        if hit.get("snippet"):
            entry["snippet"] = hit["snippet"]
        if hit.get("source"):
            entry["source"] = hit["source"]
        results.append(entry)
        logging.info(f"Listed result {i}: {entry['url']} (title: {entry['title']!r})")
    return results


def _log_fetch_outcome(i: int, url: str, result: Dict) -> None:
    if 'error' in result:
        logging.info(f"Result {i}: {url} -> {result.get('error', 'unknown error')}")
    elif result.get('kind') == 'file':
        logging.info(f"Result {i}: {url} -> downloadable {result.get('filetype') or 'file'}")
    else:
        logging.info(f"Fetched result {i}: {url} ({result.get('status_code', 'N/A')}, "
                     f"{result.get('content_length', 0)} chars, via {result.get('fetched_by', '?')})")


def _fetch_with_browser(page, hits: List[Dict], content_mode: str, deadline) -> List[Dict]:
    """Fetch phase when the browser answered the search: it is already open, and
    it renders JavaScript pages. Every page is bounded by the search budget."""
    results: List[Dict] = []
    for i, hit in enumerate(hits, 1):
        url = hit.get("url", "")
        title = hit.get("title", "")
        remaining = deadline.remaining()
        if remaining < 3.0:
            results.append({"index": i, "url": url, "title": title,
                            "error": "not fetched: the search time budget ran out"})
            continue
        timeout_ms = int(min(30.0, remaining - 1.0) * 1000)
        logging.info(f"Fetching result {i}/{len(hits)}: {url}")
        if content_mode == "raw":
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                status = resp.status if resp else 0
                html_text = page.content()[:500000]
                results.append({
                    "index": i, "url": url, "title": title,
                    "status_code": status,
                    "content_length": len(html_text),
                    "content": html_text,
                })
            except Exception as e:
                results.append({"index": i, "url": url, "title": title, "error": str(e)})
        else:
            result = _fetch_page_text(page, url, timeout_ms=timeout_ms)
            result["index"] = i
            result["title"] = title
            results.append(result)
        if hit.get("snippet") and "snippet" not in results[-1]:
            results[-1]["snippet"] = hit["snippet"]
        _log_fetch_outcome(i, url, results[-1])
    return results


def _fetch_with_http(hits: List[Dict], content_mode: str, deadline, max_chars: int) -> List[Dict]:
    """Fetch phase without a browser: every page in parallel, all bounded."""
    urls = [hit.get("url", "") for hit in hits]
    per_page = max(3.0, min(12.0, deadline.remaining() - 1.0))
    fetched = E.fetch_pages(urls, deadline=deadline, mode="raw" if content_mode == "raw" else "text",
                            max_chars=max_chars, per_page_timeout=per_page)
    results: List[Dict] = []
    for i, (hit, result) in enumerate(zip(hits, fetched), 1):
        entry = dict(result)
        entry["index"] = i
        entry["title"] = hit.get("title", "")
        for key in ("snippet", "source"):
            if hit.get(key):
                entry[key] = hit[key]
        results.append(entry)
        _log_fetch_outcome(i, entry.get("url", ""), entry)
    return results


def _rerender_thin_pages(results: List[Dict], holder: Dict, window_mode: str, profile_dir,
                         deadline) -> List[Dict]:
    """A page that came back as a thin JavaScript shell (or a bot challenge) is
    rendered by the browser, but only while the budget allows it."""
    thin = [r for r in results if r.get("thin") and not r.get("kind")]
    if not thin or deadline.remaining() < 12.0:
        return results
    session = holder.get("session")
    if session is None:
        session = _open_browser_session(window_mode, profile_dir)
        holder["session"] = session
    if session is None or session.page is None:
        return results
    for result in thin:
        if deadline.remaining() < 6.0:
            break
        rendered = _fetch_page_text(session.page, result.get("url", ""),
                                    timeout_ms=int(min(20.0, deadline.remaining() - 2.0) * 1000))
        if rendered.get("content") and len(rendered["content"]) > len(result.get("content") or ""):
            result.update(rendered)
            result.pop("error", None)
            result["thin"] = False
            logging.info("   re-rendered with the browser: %s (%d chars)",
                         result.get("url"), result.get("content_length", 0))
    return results


def _log_last_page(page) -> None:
    """Name the last page the browser saw. The per-route verdicts above it in
    the log (captcha, anomaly, poisoned, ...) are the real diagnosis."""
    try:
        title = page.title() if hasattr(page, 'title') else ''
    except Exception:
        title = ''
    logging.warning("No results from any browser route. Last page: %s %r",
                    getattr(page, 'url', '') or '?', str(title or '')[:120])


def googler_search(query: str, number_of_results: int = 5,
                   content_mode: str = "text",
                   allow_same_domain: bool = False,
                   headless: bool = False,
                   engines=None,
                   attempts_per_engine: int = 2, *,
                   deadline_seconds=None,
                   window_mode=None,
                   open_sources: bool = True,
                   captcha_wait_seconds: float = 0,
                   profile_dir=None,
                   render_thin_pages: bool = True,
                   max_chars: int = 200000,
                   report=None,
                   health=None) -> List[Dict]:
    """
    Search, then either (a) list result links, or (b) fetch the top N result
    pages and extract their content, all within ONE wall-clock budget.

    With no explicit engine pin: Tier 0 (plain-HTTP routes, hedged, before
    Playwright is even imported), then Tier 1 (real Chrome routes), then Tier 2
    (open knowledge sources), each skipped routes that refused this machine
    recently. An explicit ``engines`` list pins Tier 1 to those routes only.
    Full advanced-operator semantics are Google-specific; fallback routes may
    return broader results and are named in logs and in ``report``.

    content_mode:
      - "text":        Extract readable text from each result page (default)
      - "raw":         Return raw page HTML from each result page
      - "links_only":  Do NOT fetch result pages; return just the hit list
                       (url + title [+ snippet]). Ideal for dork enumeration /
                       file hunting; the URLs can flow through Parametrizer
                       into Apirer, then File-Extractor/File-Interpreter.

    allow_same_domain:
      When True (auto-enabled by main() when the query contains a ``site:`` operator),
      result de-duplication is by full URL instead of by domain, so a single-site dork
      can return many distinct URLs from the same host (Blocker #1 fix).

    ``report`` (optional dict) receives ``search_status`` (ok / no_matches /
    blocked / unreachable / timeout / error), ``engine``, ``tier``, ``attempts``,
    ``refused``, ``cooling`` and ``elapsed_seconds``. Returns a list of result dicts.
    """
    report = report if report is not None else {}
    # links_only is cheap (no page fetch) so it may enumerate more hits per run.
    max_cap = 50 if content_mode == "links_only" else 10
    try:
        number_of_results = int(number_of_results)
    except (TypeError, ValueError):
        number_of_results = 5
    number_of_results = max(1, min(number_of_results, max_cap))

    requested_engines = [
        str(name).strip().lower()
        for name in (engines or [])
        if str(name).strip()
    ]
    deadline = E.Deadline(deadline_seconds or _DEFAULT_DEADLINE_SECONDS)
    fetch_reserve = 0.0 if content_mode == "links_only" else min(_FETCH_RESERVE, deadline.remaining() / 3.0)
    search_deadline = deadline.child(reserve=fetch_reserve)
    use_open_sources = bool(open_sources) and not requested_engines
    open_reserve = _OPEN_SOURCES_RESERVE if use_open_sources else 0.0
    terms = E.parse_query_terms(query)
    health = health if health is not None else E.EngineHealth()
    mode = window_mode if window_mode in _WINDOW_MODES else ('headless' if headless else 'visible')

    attempts: List[Dict] = []
    results: List[Dict] = []
    hits: List[Dict] = []
    tier = ''
    holder: Dict = {"session": None}

    try:
        # TIER 0 must run before Playwright is even imported. Besides making the
        # ordering real rather than aspirational, this lets a links-only search
        # succeed on a machine whose browser runtime is unavailable.
        if not requested_engines:
            hits = _search_http_tier(query, number_of_results, allow_same_domain,
                                     deadline=search_deadline.child(15.0, reserve=open_reserve),
                                     health=health, attempts=attempts, terms=terms)
            if hits:
                tier = 'http'

        if hits and content_mode == "links_only":
            results = _listed_results(hits)
            return results

        # TIER 1: the browser. Explicit engine pins arrive here directly.
        if not hits:
            browser_deadline = search_deadline.child(reserve=open_reserve)
            if browser_deadline.remaining() >= 6.0:
                session = _open_browser_session(mode, profile_dir)
                holder["session"] = session
                if session is not None:
                    try:
                        hits = _search_with_fallback(
                            session.page, query, number_of_results, allow_same_domain,
                            engine_order=requested_engines,
                            attempts_per_engine=attempts_per_engine,
                            deadline=browser_deadline, health=health, attempts=attempts,
                            terms=terms,
                            captcha_wait_seconds=captcha_wait_seconds if mode == 'visible' else 0,
                        )
                    except Exception as e:
                        logging.error(f"Search failed: {e}")
                        hits = []
                    if hits:
                        tier = 'browser'
                    else:
                        _log_last_page(session.page)
            else:
                logging.warning("⏱️ not enough of the search budget left for the browser tier")

        # TIER 2: open knowledge sources, when every web route came back empty.
        if not hits and use_open_sources and search_deadline.remaining() > 1.0:
            open_hits, open_attempts = E.open_sources_search(terms, number_of_results,
                                                             deadline=search_deadline)
            attempts.extend(open_attempts)
            if open_hits:
                hits = open_hits
                tier = 'open_sources'
                logging.info("📚 open knowledge sources answered with %d result(s): %s",
                             len(hits), ', '.join(sorted({h.get('source', '?') for h in hits})))

        logging.info(f"Found {len(hits)} top links for '{query}'")
        if not hits:
            return results

        # --- links_only: emit the hit list, do NOT fetch the pages ---
        if content_mode == "links_only":
            results = _listed_results(hits)
            return results

        # --- Fetch phase ---
        session = holder.get("session")
        if tier == 'browser' and session is not None and session.page is not None:
            results = _fetch_with_browser(session.page, hits, content_mode, deadline)
        else:
            results = _fetch_with_http(hits, content_mode, deadline, max_chars)
            if render_thin_pages and content_mode == "text":
                results = _rerender_thin_pages(results, holder, mode, profile_dir, deadline)
        return results
    finally:
        session = holder.get("session")
        if session is not None:
            session.close()
        health.save()
        winner = next((a for a in reversed(attempts) if a.get('verdict') == 'ok'), None)
        if tier == 'open_sources':
            engine_name = '+'.join(sorted({h.get('source', '') for h in hits if h.get('source')}))
        else:
            engine_name = (winner or {}).get('engine', '') if hits else ''
        report.update({
            'search_status': E.overall_status(attempts, found=bool(hits), deadline=search_deadline),
            'engine': engine_name,
            'tier': tier,
            'elapsed_seconds': round(deadline.elapsed(), 2),
            'attempts': attempts,
            'refused': E.describe_refusals(attempts),
            'cooling': health.cooling_summary(),
            'browser': session.description if session is not None else '',
            'result_count': len(results),
        })


def _log_search_summary(report: Dict) -> None:
    search_status = report.get('search_status', 'error')
    elapsed = report.get('elapsed_seconds', 0.0)
    if search_status == 'ok':
        logging.info("✅ SEARCH OK: answered by %s (%s) in %.1fs",
                     report.get('engine') or '?', report.get('tier') or '?', elapsed)
    elif search_status == 'no_matches':
        logging.warning("🔍 NO MATCHES: the engines answered but found nothing (%.1fs)", elapsed)
    else:
        logging.warning("⛔ SEARCH %s after %.1fs. Refused by: %s", search_status.upper(), elapsed,
                        '; '.join(report.get('refused') or []) or 'every route')
    if report.get('refused') and search_status == 'ok':
        logging.info("   routes that refused this machine: %s", '; '.join(report['refused']))
    if report.get('cooling'):
        logging.info("   cooling down (skipped until then): %s", '; '.join(report['cooling']))


def save_results(results: List[Dict], output_file: str, query: str, report=None) -> str:
    """Save search results to a file. Returns the absolute file path."""
    if not os.path.isabs(output_file):
        output_file = os.path.join(script_dir, output_file)

    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)

    report = report or {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=== GOOGLER SEARCH RESULTS ===\n")
        f.write(f"Query: {query}\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Results: {len(results)}\n")
        if report:
            f.write(f"Search status: {report.get('search_status', '')}\n")
            f.write(f"Answered by: {report.get('engine', '')} ({report.get('tier', '')})\n")
            if report.get('refused'):
                f.write(f"Refused by: {'; '.join(report['refused'])}\n")
        f.write("=" * 60 + "\n\n")

        for result in results:
            f.write(f"=== HTTP RESPONSE METADATA (Result {result.get('index', '?')}) ===\n")
            f.write(f"URL: {result.get('url', 'N/A')}\n")
            if result.get('title'):
                f.write(f"Title: {result.get('title')}\n")
            if result.get('source'):
                f.write(f"Source: {result.get('source')}\n")
            f.write(f"Status: {result.get('status_code', 'N/A')}\n")
            f.write(f"Content Length: {result.get('content_length', 0)} chars\n")
            if result.get('snippet'):
                f.write(f"Snippet: {result.get('snippet')}\n")

            if 'error' in result:
                f.write(f"ERROR: {result['error']}\n")
            elif result.get('kind') == 'file':
                f.write(f"FILE: {result.get('filetype') or 'binary'} (the URL above is the download)\n")
            elif result.get('content'):
                f.write(f"\n{result.get('content', '')}\n")

            f.write("\n" + "=" * 60 + "\n\n")

    return os.path.abspath(output_file)


def _write_result_json(path: str, raw_query: str, effective_query: str, results: List[Dict],
                       report: Dict) -> str:
    """Machine-readable outcome for callers such as the chat's `googler` tool.

    Written atomically: a reader never sees half a file."""
    if not os.path.isabs(path):
        path = os.path.join(script_dir, path)
    payload = {
        "format": "tlamatini-googler-result",
        "version": 1,
        "query": raw_query,
        "effective_query": effective_query,
        "search_status": report.get("search_status", "error"),
        "engine": report.get("engine", ""),
        "tier": report.get("tier", ""),
        "elapsed_seconds": report.get("elapsed_seconds", 0.0),
        "browser": report.get("browser", ""),
        "refused": report.get("refused", []),
        "cooling": report.get("cooling", []),
        "attempts": report.get("attempts", []),
        "results": results,
    }
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp_path, path)
    return path


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"REANIMATED {CURRENT_DIR_NAME} (resuming from pause)")
        logging.info("=" * 60)

    report: Dict = {}
    results: List[Dict] = []
    raw_query = ''
    effective_query = ''
    result_json = ''
    try:
        raw_query = config.get('query', '')
        effective_query = build_dork_query(config)
        number_of_results = config.get('number_of_results', 5)
        content_mode = config.get('content_mode', 'text')
        output_file = config.get('output_file', 'googler_results.txt')
        target_agents = config.get('target_agents', [])
        result_json = str(config.get('result_json', '') or '').strip()

        # A ``site:`` dork needs same-domain de-dup OFF (keep many URLs per host).
        allow_same_domain = _resolve_allow_same_domain(config, effective_query)

        # HEADED BY DEFAULT (2026-08-23). Measured that day: bundled headless
        # Chromium returned ZERO results for every query, including a plain
        # keyword control with no operators, while a headed real Chrome
        # answered immediately. Headless is therefore opt-in and documented as
        # the degraded path, not the default. `window_mode` (2026-09-28) adds
        # `offscreen`: the same real, headed Chrome, placed off the desktop.
        headless = _as_bool(config.get('headless', False), False)
        window_mode = _resolve_window_mode(config.get('window_mode', ''), headless)
        engines = config.get('engines') or []
        if isinstance(engines, str):
            engines = [e for e in re.split(r'[,\s]+', engines) if e]
        try:
            attempts_per_engine = max(1, int(config.get('attempts_per_engine', 2)))
        except (TypeError, ValueError):
            attempts_per_engine = 2
        deadline_seconds = _as_float(config.get('deadline_seconds', _DEFAULT_DEADLINE_SECONDS),
                                     _DEFAULT_DEADLINE_SECONDS, 10.0, 900.0)
        open_sources = _as_bool(config.get('open_sources', True), True)
        captcha_wait_seconds = _as_float(config.get('captcha_wait_seconds', 0), 0.0, 0.0, 600.0)
        profile_dir = config.get('browser_profile_dir', '')
        render_thin_pages = _as_bool(config.get('render_thin_pages', True), True)
        max_chars = int(_as_float(config.get('max_chars_per_result', 200000), 200000.0,
                                  1000.0, 2000000.0))

        logging.info("GOOGLER AGENT STARTED")
        logging.info(f"Raw query: {raw_query}")
        logging.info(f"Effective query (with dork operators): {effective_query}")
        logging.info(f"Number of results: {number_of_results}")
        logging.info(f"Content mode: {content_mode}")
        logging.info(f"Allow same domain: {allow_same_domain}")
        logging.info(f"Time budget: {deadline_seconds:.0f}s | window: {window_mode} | "
                     f"open sources: {open_sources}")
        logging.info(f"Output file: {output_file}")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        if not effective_query.strip():
            logging.error("No query configured. Set the 'query' field (or a dork operator "
                          "such as 'site' / 'filetype' / 'intitle') in config.yaml.")
            report['search_status'] = 'error'
        elif content_mode not in ('text', 'raw', 'links_only'):
            logging.error(f"Invalid content_mode: {content_mode}. Use 'text', 'raw', or 'links_only'.")
            report['search_status'] = 'error'
        else:
            # Search (+ optional content fetch), bounded by the time budget
            results = googler_search(effective_query, number_of_results,
                                     content_mode, allow_same_domain,
                                     headless=headless, engines=engines,
                                     attempts_per_engine=attempts_per_engine,
                                     deadline_seconds=deadline_seconds,
                                     window_mode=window_mode,
                                     open_sources=open_sources,
                                     captcha_wait_seconds=captcha_wait_seconds,
                                     profile_dir=profile_dir,
                                     render_thin_pages=render_thin_pages,
                                     max_chars=max_chars,
                                     report=report)
            _log_search_summary(report)

            if results:
                saved_path = save_results(results, output_file, effective_query, report)
                logging.info(f"Results saved to: {saved_path}")

                engine_name = report.get('engine', '')
                tier = report.get('tier', '')
                search_status = report.get('search_status', '')
                # Emit structured sections to the log for Parametrizer consumption
                for result in results:
                    r_url = result.get('url', 'N/A')
                    r_title = result.get('title', '')
                    r_status = result.get('status_code', 'N/A')
                    r_length = result.get('content_length', 0)
                    if 'error' in result:
                        r_body = f"ERROR: {result['error']}"
                    elif result.get('kind') == 'file':
                        r_body = f"FILE: {result.get('filetype') or 'binary'} at {r_url}"
                    else:
                        r_body = result.get('content', '') or result.get('snippet', '') or r_title
                    logging.info(
                        f"INI_SECTION_GOOGLER<<<\n"
                        f"url: {r_url}\n"
                        f"title: {r_title}\n"
                        f"status: {r_status}\n"
                        f"content_length: {r_length}\n"
                        f"engine: {engine_name}\n"
                        f"tier: {tier}\n"
                        f"search_status: {search_status}\n"
                        f"\n"
                        f"{r_body}\n"
                        f">>>END_SECTION_GOOGLER"
                    )
            else:
                logging.warning("No results obtained from any search route.")

        if result_json:
            try:
                written = _write_result_json(result_json, raw_query, effective_query, results, report)
                logging.info(f"Result JSON written to: {written}")
            except Exception as json_err:
                logging.error(f"Could not write the result JSON: {json_err}")

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
        if result_json:
            try:
                report.setdefault('search_status', 'error')
                report.setdefault('refused', [])
                report['error'] = str(e)
                _write_result_json(result_json, raw_query, effective_query, results, report)
            except Exception:
                pass
    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
