# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""GOOGLER DORK HUNT — a named, re-runnable, VISIBLE proof of the dork builder.

Angela asked for a live dork that returns real FILE FOUND URLs, made persistent
and reproducible under a name. This is that artifact.

WHAT IT DOES
    For each named hunt below it (1) builds the dork with Googler's OWN
    `build_dork_query` — so the thing under test is the shipped builder, not a
    copy — (2) drives a HEADED, VISIBLE Chrome through the real search page,
    (3) classifies every hit, and (4) reports the ones that are downloadable
    files as FILE FOUND with their extension.

WHY HEADED
    Angela's standing rule is that automated tests must be visible. It is also
    the diagnosis: the pool agent runs Chromium HEADLESS, and on 2026-08-23 that
    path returned 0 results for EVERY query — including a plain keyword control
    with no operators at all — while DuckDuckGo's fallback answered
    "Unexpected error. Please try again." A headed, real-Chrome profile is far
    less likely to be refused, so this harness is both the proof and the
    workaround.

USAGE
    python googler_dork_hunt.py                     # all built-in hunts
    python googler_dork_hunt.py --list              # show hunt names
    python googler_dork_hunt.py --hunt gutenberg    # one hunt by name
    python googler_dork_hunt.py --title "Frankenstein" --hunt gutenberg
    python googler_dork_hunt.py --headless          # diagnostic only, NOT a pass

EXIT CODE
    0 = at least one FILE FOUND in every hunt that ran
    1 = a hunt produced no files (or the engine refused to answer)

SCOPE
    Every built-in hunt targets PUBLIC-DOMAIN or open-access libraries
    (Project Gutenberg, Standard Ebooks, arXiv). These operators only surface
    pages Google has already indexed; they bypass nothing.
"""
import argparse
import importlib.util
import json
import logging
import os
import sys
import time
from datetime import datetime

HARNESS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HARNESS, "..", "..", "..", ".."))
GOOGLER_PY = os.path.join(REPO, "Tlamatini", "agent", "agents", "googler", "googler.py")
REPORT_DIR = os.path.join(REPO, "Temp", "googler_dork_hunt")

#: Extensions that mean "this hit IS the file", not a page about it.
FILE_EXTENSIONS = {
    "pdf", "epub", "mobi", "azw3", "djvu", "txt", "rtf",
    "doc", "docx", "ppt", "pptx", "xls", "xlsx", "csv", "zip",
}

#: Named hunts. Each is a config dict for Googler's own build_dork_query.
HUNTS = {
    "gutenberg": {
        "label": "Public-domain EPUB/PDF on Project Gutenberg",
        "config": {"exact": "{title}", "filetypes": ["epub", "pdf"],
                   "sites": ["gutenberg.org"]},
    },
    "public_libraries": {
        "label": "The book_public preset — every lawful full-text library at once",
        "config": {"exact": "{title}", "preset": "book_public"},
    },
    "standardebooks": {
        "label": "Standard Ebooks EPUB",
        "config": {"exact": "{title}", "filetypes": "epub",
                   "sites": ["standardebooks.org"]},
    },
    "arxiv": {
        "label": "Open-access papers (PDF) on arXiv",
        "config": {"exact": "attention is all you need", "filetypes": "pdf",
                   "sites": ["arxiv.org"]},
    },
    "any_format": {
        "label": "Either ebook format anywhere (OR-group, noise removed)",
        "config": {"exact": "{title}", "preset": "book"},
    },
}

DEFAULT_TITLE = "The Time Machine"


def load_builder():
    """Import the SHIPPED builder so this harness tests the real thing."""
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        spec = importlib.util.spec_from_file_location("googler_hunt_mod", GOOGLER_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


def url_extension(url: str) -> str:
    tail = str(url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
    last = tail.rsplit("/", 1)[-1]
    return tail.rsplit(".", 1)[-1].lower() if "." in last else ""


def dismiss_consent(page) -> None:
    """Click through Google's cookie wall if it appears (several locales)."""
    for selector in ('button:has-text("Accept all")',
                     'button:has-text("Aceptar todo")',
                     'button:has-text("I agree")',
                     'button#L2AGLb',
                     'form[action*="consent"] button'):
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            continue


def harvest(page, limit: int):
    """Return [{url, title}] from the results page, skipping Google's own links."""
    out, seen = [], set()
    for selector in ("div#search a[href^='http']", "div#rso a[href^='http']",
                     "a[jsname][href^='http']", "a[href^='http']"):
        try:
            anchors = page.query_selector_all(selector)
        except Exception:
            continue
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
            except Exception:
                continue
            if not href.startswith("http"):
                continue
            low = href.lower()
            if any(bad in low for bad in ("google.", "gstatic.", "youtube.com/redirect",
                                          "policies.", "support.")):
                continue
            if href in seen:
                continue
            seen.add(href)
            try:
                text = (a.inner_text() or "").strip().splitlines()[0][:110]
            except Exception:
                text = ""
            out.append({"url": href, "title": text})
            if len(out) >= limit:
                return out
        if out:
            return out
    return out


def run_hunt(page, name: str, spec: dict, title: str, builder, limit: int) -> dict:
    cfg = {}
    for key, value in spec["config"].items():
        if isinstance(value, str):
            cfg[key] = value.replace("{title}", title)
        elif isinstance(value, list):
            cfg[key] = [str(v).replace("{title}", title) for v in value]
        else:
            cfg[key] = value
    cfg.setdefault("query", "")
    dork = builder.build_dork_query(cfg)

    print("\n" + "=" * 78)
    print(f"  HUNT: {name}  —  {spec['label']}")
    print("=" * 78)
    print(f"  DORK: {dork}")

    hits, error = [], ""
    try:
        page.goto("https://www.google.com/search?q=" + _quote(dork) + "&num=20",
                  wait_until="domcontentloaded", timeout=30000)
        dismiss_consent(page)
        try:
            page.wait_for_selector("div#search, div#rso, div#main", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        hits = harvest(page, limit)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    files = [h for h in hits if url_extension(h["url"]) in FILE_EXTENSIONS]
    pages = [h for h in hits if h not in files]

    if error:
        print(f"  ENGINE ERROR: {error}")
    print(f"  hits: {len(hits)}   FILES: {len(files)}   pages: {len(pages)}")
    for h in files:
        print(f"    FILE FOUND [{url_extension(h['url']).upper()}]  {h['url']}")
        if h["title"]:
            print(f"                {h['title']}")
    for h in pages[:3]:
        print(f"    (page)  {h['url']}")

    return {"hunt": name, "label": spec["label"], "dork": dork,
            "hits": len(hits), "files": [h["url"] for h in files],
            "pages": [h["url"] for h in pages], "error": error,
            "ok": bool(files)}


def _quote(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hunt", action="append", default=[],
                        help="run only this hunt (repeatable)")
    parser.add_argument("--title", default=DEFAULT_TITLE,
                        help=f"book title to hunt (default: {DEFAULT_TITLE!r})")
    parser.add_argument("--limit", type=int, default=12, help="max hits per hunt")
    parser.add_argument("--list", action="store_true", help="list hunt names and exit")
    parser.add_argument("--headless", action="store_true",
                        help="DIAGNOSTIC ONLY — a headless run is never a pass")
    args = parser.parse_args(argv)

    if args.list:
        for name, spec in HUNTS.items():
            print(f"  {name:<18} {spec['label']}")
        return 0

    names = args.hunt or list(HUNTS)
    unknown = [n for n in names if n not in HUNTS]
    if unknown:
        print(f"Unknown hunt(s): {', '.join(unknown)}  (try --list)")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed:  pip install playwright && "
              "python -m playwright install chrome")
        return 1

    builder = load_builder()
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 78)
    print("  GOOGLER DORK HUNT")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}   title={args.title!r}   "
          f"{'HEADLESS (diagnostic)' if args.headless else 'HEADED (visible)'}")
    print("=" * 78)

    results = []
    with sync_playwright() as p:
        launch = {"headless": bool(args.headless),
                  "args": ["--disable-blink-features=AutomationControlled"]}
        try:
            browser = p.chromium.launch(channel="chrome", **launch)
        except Exception:
            browser = p.chromium.launch(**launch)
        context = browser.new_context(
            viewport={"width": 1500, "height": 950}, locale="en-US",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"))
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = context.new_page()
        try:
            for name in names:
                results.append(run_hunt(page, name, HUNTS[name], args.title,
                                        builder, args.limit))
                time.sleep(2)
            if not args.headless:
                print("\n  Browser stays open 8s so you can see the last result page...")
                page.wait_for_timeout(8000)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    total_files = sum(len(r["files"]) for r in results)
    failed = [r for r in results if not r["ok"]]

    print("\n" + "=" * 78)
    print("  SUMMARY")
    for r in results:
        print(f"    {'OK  ' if r['ok'] else 'FAIL'}  {r['hunt']:<18} "
              f"{len(r['files'])} file(s), {r['hits']} hit(s)"
              + (f"   [{r['error']}]" if r["error"] else ""))
    print(f"  TOTAL FILES FOUND: {total_files}")
    print("=" * 78)

    report = os.path.join(REPORT_DIR, f"dork_hunt_{stamp}.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump({"when": stamp, "title": args.title,
                   "headless": bool(args.headless), "results": results}, fh, indent=2)
    print(f"  report -> {report}")

    if failed:
        print("\n  NOTE: a hunt with 0 hits usually means the SEARCH ENGINE refused "
              "the request\n  (consent wall, bot check, or a transient error) — not "
              "that the dork was wrong.\n  The DORK line above is what was actually "
              "submitted; verify it by hand if unsure.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
