# Googler Agent - Google search agent with content extraction
# Action: Triggered by upstream -> Search Google for query -> Fetch top N results ->
#         Extract readable text -> Save results to file -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess
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
    """Read PYTHON_HOME exclusively from USER environment variables (Windows registry)."""
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


def _extract_links_with_selectors(page, selectors, skip_domains=None) -> List[str]:
    """Try each selector in order; return first non-empty list of unique URLs."""
    if skip_domains is None:
        skip_domains = {'google.com', 'google.co', 'accounts.google', 'support.google',
                        'maps.google', 'policies.google'}
    from urllib.parse import urlparse

    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        if not elements:
            continue

        urls = []
        seen = set()
        for elem in elements:
            href = elem.get_attribute("href")
            if not href or not href.startswith("http"):
                continue
            try:
                domain = urlparse(href).netloc.lower()
            except Exception:
                continue
            if any(sd in domain for sd in skip_domains):
                continue
            if domain in seen:
                continue
            seen.add(domain)
            urls.append(href)

        if urls:
            logging.info(f"Selector '{selector}' matched {len(urls)} link(s).")
            return urls

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


def _search_google_playwright(page, query: str, number_of_results: int) -> List[str]:
    """Perform a Google search using Playwright and return result URLs."""
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

    urls = _extract_links_with_selectors(page, _GOOGLE_RESULT_SELECTORS)
    return urls[:number_of_results]


def _search_ddg_playwright(page, query: str, number_of_results: int) -> List[str]:
    """Fallback: perform a DuckDuckGo search using Playwright and return result URLs."""
    logging.info("Falling back to DuckDuckGo search...")
    page.goto(f"https://duckduckgo.com/?q={query.replace(' ', '+')}&t=h_&ia=web",
              wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector('article[data-testid="result"], a.result__a, h2 a', timeout=15000)
    except Exception:
        logging.warning("Timed out waiting for DuckDuckGo results; proceeding anyway.")

    page.wait_for_timeout(2000)

    urls = _extract_links_with_selectors(page, _DDG_RESULT_SELECTORS, skip_domains={'duckduckgo.com'})
    return urls[:number_of_results]


# ============================================================
# Core Googler Logic
# ============================================================

def googler_search(query: str, number_of_results: int = 5,
                   content_mode: str = "text") -> List[Dict]:
    """
    Search Google for the query, fetch the top N result pages using Playwright
    (handles JS-rendered sites), and extract readable text from each.

    Falls back to DuckDuckGo if Google returns no results.
    Automatically skips binary content (PDFs, images, etc.).

    content_mode:
      - "text": Extract rendered visible text (default)
      - "raw":  Return raw page HTML

    Returns a list of result dicts with url, status_code, and content.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
        return []

    if number_of_results > 10:
        number_of_results = 10

    results = []

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
                urls = _search_google_playwright(page, query, number_of_results)

                if not urls:
                    logging.warning(f"Google returned 0 results for '{query}'; trying DuckDuckGo.")
                    urls = _search_ddg_playwright(page, query, number_of_results)

                if not urls:
                    try:
                        debug_path = os.path.join(script_dir, "debug_no_results.png")
                        page.screenshot(path=debug_path, full_page=True)
                        logging.warning(f"No results from any engine. Debug screenshot: {debug_path}")
                    except Exception as ss_err:
                        logging.warning(f"Could not save debug screenshot: {ss_err}")

                logging.info(f"Found {len(urls)} top links for '{query}'")

                # --- Fetch phase: reuse the same browser for JS rendering ---
                for i, url in enumerate(urls, 1):
                    logging.info(f"Fetching result {i}/{len(urls)}: {url}")

                    if content_mode == "raw":
                        try:
                            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            status = resp.status if resp else 0
                            html = page.content()[:500000]
                            results.append({
                                "index": i, "url": url,
                                "status_code": status,
                                "content_length": len(html),
                                "content": html,
                            })
                        except Exception as e:
                            results.append({"index": i, "url": url, "error": str(e)})
                    else:
                        result = _fetch_page_text(page, url)
                        result["index"] = i
                        results.append(result)

                    logging.info(
                        f"Fetched result {i}: {url} "
                        f"({result.get('status_code', 'N/A')}, "
                        f"{result.get('content_length', 0)} chars)"
                        if 'error' not in results[-1]
                        else f"Result {i}: {url} -> {results[-1].get('error', 'unknown error')}"
                    )

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
            f.write(f"--- Result {result.get('index', '?')} ---\n")
            f.write(f"URL: {result.get('url', 'N/A')}\n")

            if 'error' in result:
                f.write(f"ERROR: {result['error']}\n")
            else:
                f.write(f"Status: {result.get('status_code', 'N/A')}\n")
                f.write(f"Content Length: {result.get('content_length', 0)} chars\n")
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
        query = config.get('query', '')
        number_of_results = config.get('number_of_results', 5)
        content_mode = config.get('content_mode', 'text')
        output_file = config.get('output_file', 'googler_results.txt')
        target_agents = config.get('target_agents', [])

        logging.info("GOOGLER AGENT STARTED")
        logging.info(f"Query: {query}")
        logging.info(f"Number of results: {number_of_results}")
        logging.info(f"Content mode: {content_mode}")
        logging.info(f"Output file: {output_file}")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        if not query.strip():
            logging.error("No query configured. Set the 'query' field in config.yaml.")
        else:
            if content_mode not in ('text', 'raw'):
                logging.error(f"Invalid content_mode: {content_mode}. Use 'text' or 'raw'.")
            else:
                # Perform Google search and fetch results
                results = googler_search(query, number_of_results, content_mode)

                if results:
                    saved_path = save_results(results, output_file, query)
                    logging.info(f"Results saved to: {saved_path}")
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
