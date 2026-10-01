# Tlamatini Author Banner - do not remove
"""VISIBLE walkthrough of the regenerated project dossier (PDF + PPTX).

Run it AFTER ``refresh_project_docs.py`` has passed. It draws nothing itself.
In a headed, real Chrome on the desktop it shows:

1. the real PDF in Chrome's own viewer, at the pages you name, and
2. every PDF page and every slide exactly as the dossier verifier rendered
   them (PyMuPDF for the PDF, PowerPoint's own export for the slides),
   scrolled one by one at a pace a person can watch.

Shoter, Tlamatini's own agent, photographs the WHOLE desktop at each
checkpoint, and only after confirming that the foreground window is this
walkthrough: a photo of the wrong window is refused, never taken.

Usage (in a visible console):
    python scripts/dossier_visual_walkthrough_visible.py --pdf-pages 1,17,74 --slides 15,93

Exit codes: 0 pass; 2 preflight (missing, stale or uncounted renders, or the
verifier did not report clean); 3 an image failed to load in the browser;
4 the browser could not be opened.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PDF = REPO / "tlamatini_app_summary.pdf"
PPTX = REPO / "Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx"
RENDERS = REPO / "build" / "documentation_refresh" / "renders"
REPORT = REPO / "build" / "documentation_refresh" / "dossier_verification.json"
OUT = REPO / "Temp" / "dossier_walkthrough"
HARNESS = REPO / ".claude" / "skills" / "tlamatini-daily-chat-test" / "harness"
TITLE = "Tlamatini dossier walkthrough"
STEP_SECONDS = 0.45
LOG_LINES: list[str] = []


def say(message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    LOG_LINES.append(line)
    (OUT / "walkthrough.log").write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")


def numbers(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip().isdigit()]


def preflight() -> tuple[list[Path], list[Path]]:
    """Refuse with a NAMED reason instead of walking stale or partial evidence."""
    problems = []
    for path in (PDF, PPTX, REPORT):
        if not path.is_file():
            problems.append(f"missing {path}")
    if problems:
        return fail(problems)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if not report.get("clean"):
        problems.append(f"the verifier did not report clean ({report.get('problem_count')} problems)")
    if REPORT.stat().st_mtime < max(PDF.stat().st_mtime, PPTX.stat().st_mtime):
        problems.append("the verification report is older than the documents; rerun refresh_project_docs.py")
    pages = sorted((RENDERS / "pdf").glob("p*.png"))
    slides = sorted((RENDERS / "ppt").glob("s*.png"))
    if len(pages) != report.get("pdf", {}).get("pages"):
        problems.append(f"{len(pages)} PDF renders for {report.get('pdf', {}).get('pages')} pages")
    if len(slides) != report.get("pptx", {}).get("slides"):
        problems.append(f"{len(slides)} slide renders for {report.get('pptx', {}).get('slides')} slides")
    oldest = min((p.stat().st_mtime for p in pages + slides), default=0)
    if oldest < PDF.stat().st_mtime:
        problems.append("some renders are older than the PDF; rerun refresh_project_docs.py")
    if problems:
        return fail(problems)
    say(f"PREFLIGHT OK: verifier clean, {len(pages)} PDF pages, {len(slides)} slides, renders fresh")
    return pages, slides


def fail(problems: list[str]):
    for problem in problems:
        say(f"PREFLIGHT REFUSED: {problem}")
    say("VERDICT walkthrough exit=2 (preflight)")
    sys.exit(2)


def gallery(pages: list[Path], slides: list[Path]) -> tuple[Path, list[str]]:
    labels = [f"PDF page {i}" for i in range(1, len(pages) + 1)]
    labels += [f"Slide {i}" for i in range(1, len(slides) + 1)]
    figures = []
    for index, (label, image) in enumerate(zip(labels, pages + slides)):
        figures.append(
            f'<figure id="item{index}" data-label="{html.escape(label)}">'
            f'<img src="{image.as_uri()}" alt="{html.escape(label)}">'
            f"<figcaption>{html.escape(label)}</figcaption></figure>")
    document = f"""<!doctype html><html><head><meta charset="utf-8"><title>{TITLE}</title>
<style>
body {{ margin: 0; background: #0b1316; color: #efe7d6; font: 15px 'Segoe UI', sans-serif; }}
#bar {{ position: fixed; top: 0; left: 0; right: 0; z-index: 9; padding: 10px 18px;
        background: #12241f; border-bottom: 2px solid #c8834f; font-weight: 600; }}
main {{ padding: 64px 0 40vh; display: flex; flex-direction: column; align-items: center; gap: 28px; }}
figure {{ margin: 0; padding: 10px; border: 2px solid transparent; border-radius: 8px; }}
figure.current {{ border-color: #3cc296; box-shadow: 0 0 22px #3cc29666; }}
img {{ display: block; max-width: min(1150px, 92vw); max-height: 78vh; }}
figcaption {{ text-align: center; padding-top: 6px; color: #c8834f; }}
</style></head><body><div id="bar">{TITLE}: loading</div><main>{''.join(figures)}</main>
<script>
const N = {len(labels)};
window.__go = (i) => {{
  const el = document.getElementById('item' + i);
  document.querySelectorAll('.current').forEach(e => e.classList.remove('current'));
  el.classList.add('current');
  el.scrollIntoView({{block: 'center'}});
  const text = el.dataset.label + '  (' + (i + 1) + '/' + N + ')';
  document.getElementById('bar').textContent = '{TITLE}: ' + text;
  document.title = '{TITLE} - ' + text;
}};
</script></body></html>"""
    target = OUT / "gallery.html"
    target.write_text(document, encoding="utf-8")
    return target, labels


def foreground_title() -> str:
    try:
        import win32gui
        return win32gui.GetWindowText(win32gui.GetForegroundWindow())
    except Exception:  # noqa: BLE001 - a missing title only refuses the photo
        return ""


def pdf_window_title() -> str:
    """Chrome titles a PDF tab with the document's own title, else with its file name."""
    try:
        import fitz
        return (fitz.open(str(PDF)).metadata or {}).get("title") or PDF.name
    except Exception:  # noqa: BLE001 - fall back to the file name
        return PDF.name


def photo(page, take_shot, name: str, must_contain: str, shots: list[dict]) -> None:
    page.bring_to_front()
    time.sleep(0.8)
    title = foreground_title()
    if must_contain.lower() not in title.lower():
        say(f"PHOTO REFUSED {name}: foreground is {title!r}, not the walkthrough")
        shots.append({"name": name, "path": None, "foreground": title})
        return
    path = take_shot(str(OUT / "shots"), name, runtime_base=str(OUT))
    say(f"PHOTO {name}: {path or 'Shoter left no photo'}")
    shots.append({"name": name, "path": path, "foreground": title})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-pages", default="1")
    parser.add_argument("--slides", default="1")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shots").mkdir(exist_ok=True)
    say("VISIBLE dossier walkthrough starting (headed Chrome, Shoter photographs)")
    pages, slides = preflight()
    target, labels = gallery(pages, slides)
    sys.path.insert(0, str(HARNESS))
    from shoter_shot import take_shot
    from playwright.sync_api import sync_playwright

    shots: list[dict] = []
    pdf_focus = [n for n in numbers(args.pdf_pages) if 1 <= n <= len(pages)]
    slide_focus = [n for n in numbers(args.slides) if 1 <= n <= len(slides)]
    pdf_title = pdf_window_title()
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=False, args=["--start-maximized"])
        except Exception as exc:  # noqa: BLE001 - named refusal, not a stack trace
            say(f"BROWSER REFUSED: real Chrome could not open headed: {exc}")
            say("VERDICT walkthrough exit=4")
            return 4
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        for number in pdf_focus:
            try:
                # Leave the PDF first: changing only the #page= fragment of an open PDF does
                # not move Chrome's viewer, so the photo would show the previous page.
                page.goto("about:blank")
                page.goto(f"{PDF.as_uri()}#page={number}", timeout=20000)
                time.sleep(2.5)
                photo(page, take_shot, f"pdf_viewer_p{number:03d}.png", pdf_title, shots)
            except Exception as exc:  # noqa: BLE001 - the gallery still shows every page
                say(f"PDF viewer could not show page {number}: {str(exc)[:160]}")
        page.goto(target.as_uri())
        page.wait_for_function("Array.from(document.images).every(i => i.complete)", timeout=120000)
        broken = page.evaluate(
            "Array.from(document.images).filter(i => !(i.complete && i.naturalWidth > 0)).map(i => i.alt)")
        say(f"GALLERY loaded: {len(labels)} images, {len(broken)} failed to load {broken[:10]}")
        focus = {f"PDF page {n}" for n in pdf_focus} | {f"Slide {n}" for n in slide_focus}
        for index, label in enumerate(labels):
            page.evaluate(f"window.__go({index})")
            time.sleep(STEP_SECONDS)
            if index % 20 == 0:
                say(f"walking: {label} ({index + 1}/{len(labels)})")
            if label in focus:
                time.sleep(0.6)
                photo(page, take_shot, f"walk_{label.lower().replace(' ', '_')}.png", TITLE, shots)
        say(f"walked all {len(labels)} pages and slides")
        browser.close()
    refused = [s["name"] for s in shots if not s["path"]]
    verdict = 3 if broken else 0
    results = {"pages": len(pages), "slides": len(slides), "broken_images": broken,
               "photos": shots, "photos_refused": refused, "exit": verdict}
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    rows = "".join(
        f"<tr><td>{html.escape(s['name'])}</td><td>{html.escape(str(s['path']))}</td>"
        f"<td>{html.escape(s['foreground'])}</td></tr>" for s in shots)
    (OUT / "SUMMARY.html").write_text(
        f"<!doctype html><meta charset='utf-8'><title>Dossier walkthrough summary</title>"
        f"<h1>Dossier walkthrough: exit {verdict}</h1><p>{len(pages)} PDF pages, {len(slides)} slides, "
        f"{len(broken)} images failed to load, {len(refused)} photos refused.</p>"
        f"<table border=1 cellpadding=4><tr><th>Photo</th><th>File</th><th>Foreground</th></tr>{rows}</table>",
        encoding="utf-8")
    say(f"VERDICT walkthrough exit={verdict} (photos taken {len(shots) - len(refused)}, refused {len(refused)})")
    return verdict


if __name__ == "__main__":
    sys.exit(main())
