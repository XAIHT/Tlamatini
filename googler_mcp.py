import json
import logging
from typing import List
from urllib.parse import urlparse
from mcp.server.fastmcp import FastMCP
from playwright.sync_api import sync_playwright

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("googler")

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

_GOOGLE_RESULT_SELECTORS = [
    '#rso a:has(h3)',
    '#search a:has(h3)',
    'div.g a[href^="http"]',
    '#rso a[href^="http"]',
    'div#search a[href^="http"]',
]

_DDG_RESULT_SELECTORS = [
    'article[data-testid="result"] a[data-testid="result-title-a"]',
    'a.result__a',
    'h2 a[href^="http"]',
]

_BINARY_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.exe', '.dmg',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
}

_BINARY_CONTENT_TYPES = {
    'application/pdf', 'application/octet-stream',
    'application/zip', 'application/gzip',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument',
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
                logger.info("Dismissed Google consent banner.")
                return
        except Exception:
            continue


def _extract_links(page, selectors, skip_domains=None) -> List[str]:
    """Try each selector in order; return first non-empty list of unique URLs."""
    if skip_domains is None:
        skip_domains = {'google.com', 'google.co', 'accounts.google', 'support.google',
                        'maps.google', 'policies.google'}
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        if not elements:
            continue

        urls, seen = [], set()
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
            logger.info(f"Selector '{selector}' matched {len(urls)} link(s).")
            return urls
    return []


def _is_binary_url(url: str) -> bool:
    path = urlparse(url).path.lower().split('?')[0]
    return any(path.endswith(ext) for ext in _BINARY_EXTENSIONS)


def _is_binary_content_type(content_type: str) -> bool:
    ct = content_type.lower().split(';')[0].strip()
    if ct in _BINARY_CONTENT_TYPES:
        return True
    if ct.startswith(('image/', 'audio/', 'video/')):
        return True
    if 'officedocument' in ct:
        return True
    return False


def _fetch_page_text(page, url: str) -> dict:
    """Navigate Playwright page to URL and extract rendered visible text.
    Skips binary content (PDFs, images, etc.)."""
    if _is_binary_url(url):
        return {"url": url, "error": "Binary file detected from URL extension, skipped"}

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return {"url": url, "error": str(e)}

    if not response:
        return {"url": url, "error": "No response received"}

    status = response.status
    content_type = response.headers.get('content-type', '')
    if _is_binary_content_type(content_type):
        return {"url": url, "status_code": status,
                "error": f"Binary content-type ({content_type}), skipped"}

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    try:
        text = page.inner_text('body')
    except Exception:
        text = ""

    if text:
        lines = text.splitlines()
        cleaned, blank_count = [], 0
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

    text = text[:500000]
    return {"url": url, "status_code": status,
            "content_length": len(text), "body": text}


@mcp.tool()
def googler(topic: str, number_of_sites: int = 5) -> str:
    """
    Searches Google for the given topic, fetches the top N sites' rendered text content.
    Falls back to DuckDuckGo if Google returns no results.
    Automatically skips binary content (PDFs, images, etc.).

    Args:
        topic: Search query or phrase to enter in Google.
        number_of_sites: Number of top sites to fetch (default 5).
    """
    if number_of_sites > 10:
        number_of_sites = 10

    outcomes = []

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
            # --- Google search ---
            page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
            _dismiss_google_consent(page)

            search_box = page.wait_for_selector(
                'textarea[name="q"], input[name="q"]', timeout=10000
            )
            search_box.fill(topic)
            search_box.press("Enter")

            try:
                page.wait_for_selector('#rso, #search, div.g', timeout=15000)
            except Exception:
                logger.warning("Timed out waiting for Google results container.")
            page.wait_for_timeout(2000)

            top_links = _extract_links(page, _GOOGLE_RESULT_SELECTORS)

            # --- DuckDuckGo fallback ---
            if not top_links:
                logger.warning(f"Google returned 0 results for '{topic}'; trying DuckDuckGo.")
                page.goto(
                    f"https://duckduckgo.com/?q={topic.replace(' ', '+')}&t=h_&ia=web",
                    wait_until="domcontentloaded", timeout=30000
                )
                try:
                    page.wait_for_selector(
                        'article[data-testid="result"], a.result__a, h2 a', timeout=15000
                    )
                except Exception:
                    pass
                page.wait_for_timeout(2000)
                top_links = _extract_links(page, _DDG_RESULT_SELECTORS, skip_domains={'duckduckgo.com'})

            top_links = top_links[:number_of_sites]
            logger.info(f"Found {len(top_links)} top links for '{topic}'")

            # Fetch content using Playwright (handles JS-rendered pages)
            for url in top_links:
                result = _fetch_page_text(page, url)
                outcomes.append(result)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Error during search: {str(e)}"
        finally:
            browser.close()

    output = f"googler mcp {len(outcomes)} outcomes:\n"
    for i, outcome in enumerate(outcomes, 1):
        output += f"outcome-{i} {{\n"
        output += json.dumps(outcome, indent=2, ensure_ascii=False) + "\n"
        output += "}\n"

    return output

if __name__ == "__main__":
    mcp.run()
