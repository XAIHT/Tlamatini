# Crawler Agent - Web page crawler with LLM analysis
# Action: Triggered by upstream -> Fetch URL -> Strip HTML -> Save to file -> Query LLM -> Log response -> Trigger downstream

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import json
import logging
import subprocess
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
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
# HTML Stripping
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
# URL Fetching
# ============================================================

def fetch_page(url: str) -> str:
    """Fetch a web page via HTTP GET and return its raw HTML content."""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
        }
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        charset = resp.headers.get_content_charset() or 'utf-8'
        return resp.read().decode(charset, errors='replace')


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
# LLM Query
# ============================================================

def query_ollama(host: str, model: str, system_prompt: str, context: str) -> str:
    """
    Send a prompt to an Ollama LLM with a system prompt and context,
    and return the full response text.
    """
    url = f"{host.rstrip('/')}/api/generate"
    full_prompt = f"{system_prompt}\n\n--- BEGIN CONTEXT ---\n{context}\n--- END CONTEXT ---"

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
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
# Core Crawl Logic
# ============================================================

def save_crawled_content(text: str, crawl_type: str, timestamp: str) -> str:
    """Save crawled text content to a local file and return the file path."""
    filename = f"crawled_{crawl_type}_{timestamp}.txt"
    filepath = os.path.join(script_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text)
    return filepath


def process_url_with_llm(page_url: str, host: str, model: str, system_prompt: str,
                         crawl_type: str, timestamp: str) -> None:
    """Fetch a URL, strip HTML, save content, query LLM, and log the response."""
    logging.info(f"Fetching: {page_url}")

    try:
        html = fetch_page(page_url)
    except Exception as e:
        logging.error(f"Failed to fetch {page_url}: {e}")
        return

    plain_text = strip_html(html)
    logging.info(f"Extracted {len(plain_text)} chars of text from {page_url}")

    if not plain_text.strip():
        logging.warning(f"No text content found at {page_url}, skipping LLM query.")
        return

    filepath = save_crawled_content(plain_text, crawl_type, timestamp)
    logging.info(f"Saved crawled content to: {filepath}")

    try:
        response_text = query_ollama(host, model, system_prompt, plain_text)
    except RuntimeError as e:
        logging.error(f"LLM query failed for {page_url}: {e}")
        return

    # Log response in the format specific to the crawl type
    type_label = crawl_type.replace('-range', '')
    upper_label = type_label.upper()
    logging.info(
        f"INI_RESPONSE_{upper_label}<<<\n"
        f"--------------------LLM Response (model: {model}, url: {page_url}, "
        f"crawl_type: {{{type_label}}})------------------"
        f" {{\n{response_text}\n}}\n"
        f">>>END_RESPONSE_{upper_label}"
    )


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()

    try:
        url = config.get('url', '')
        system_prompt = config.get('system_prompt', '')
        crawl_type = config.get('crawl_type', 'small-range')
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://localhost:11434')
        model = llm_config.get('model', 'llama3.1:8b')
        target_agents = config.get('target_agents', [])

        logging.info("CRAWLER AGENT STARTED")
        logging.info(f"URL: {url}")
        logging.info(f"Crawl type: {crawl_type}")
        logging.info(f"Model: {model} @ {host}")
        logging.info(f"Targets: {target_agents}")
        logging.info("=" * 60)

        if not url.strip():
            logging.error("No URL configured. Set the 'url' field in config.yaml.")
            return

        if not system_prompt.strip():
            logging.error("No system_prompt configured. Set the 'system_prompt' field in config.yaml.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        if crawl_type == 'small-range':
            # Process only the given URL
            process_url_with_llm(url, host, model, system_prompt, 'small', timestamp)

        elif crawl_type == 'medium-range':
            # Process the main page first
            logging.info("Medium-range crawl: fetching same-domain links...")
            try:
                main_html = fetch_page(url)
            except Exception as e:
                logging.error(f"Failed to fetch main page {url}: {e}")
                return

            all_links = extract_links(main_html, url)
            same_domain_links = filter_same_domain(all_links, url)
            logging.info(f"Found {len(same_domain_links)} same-domain links")

            for i, link in enumerate(same_domain_links):
                link_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                logging.info(f"Processing link {i + 1}/{len(same_domain_links)}: {link}")
                process_url_with_llm(link, host, model, system_prompt, 'medium', link_ts)

        elif crawl_type == 'large-range':
            # Process all links regardless of domain
            logging.info("Large-range crawl: fetching ALL links...")
            try:
                main_html = fetch_page(url)
            except Exception as e:
                logging.error(f"Failed to fetch main page {url}: {e}")
                return

            all_links = extract_links(main_html, url)
            logging.info(f"Found {len(all_links)} total links")

            for i, link in enumerate(all_links):
                link_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                logging.info(f"Processing link {i + 1}/{len(all_links)}: {link}")
                process_url_with_llm(link, host, model, system_prompt, 'large', link_ts)

        else:
            logging.error(f"Unknown crawl_type: {crawl_type}. Use small-range, medium-range, or large-range.")
            return

        logging.info("Crawl processing complete.")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            logging.info(f"Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"Crawler agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    except Exception as e:
        logging.error(f"Crawler agent error: {e}")
    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
