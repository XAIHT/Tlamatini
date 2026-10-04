# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Re-open the finished dossier files and prove they are whole.

PDF: every glyph lies inside the page, no two text lines collide, and the
file tree printed in Appendix A rebuilds to exactly the paths Git tracks.

PPTX: the deck opens, its tree appendix rebuilds to the same paths, and — when
Microsoft PowerPoint is installed — PowerPoint itself reports the bounds of
every text box, so text that would spill out of its box or off the slide is
caught by the application that will display it. Every page and slide is also
rendered to PNG for visual inspection.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import time

import fitz
from pptx import Presentation

from complete_project_docs import BUILD_DIR, parse_tree

RENDER_DIR = BUILD_DIR / "renders"
PAGE_MARGIN = 9.0          # points: glyphs must stay at least this far from the page edge
TOLERANCE = 1.0            # points of slack for PowerPoint's own rounding
FOREGROUND_WAIT_SECONDS = 300  # how long to keep asking Windows to bring PowerPoint forward


def _rebuild(lines: list[str]) -> list[str]:
    """Join '»' continuation lines back onto their parent before parsing the tree."""
    joined: list[str] = []
    for line in lines:
        stripped = line.lstrip("│ ")
        if stripped.startswith("» ") and joined:
            joined[-1] += stripped[2:]
        else:
            joined.append(line.rstrip("\n"))
    return joined


def _parity(expected: list[str], found: list[str]) -> dict:
    exp, got = Counter(expected), Counter(found)
    missing = sorted((exp - got).elements())
    extra = sorted((got - exp).elements())
    return {"expected": len(expected), "found": len(found), "missing": missing[:25], "extra": extra[:25],
            "exact": not missing and not extra}


# ── PDF ─────────────────────────────────────────────────────────────
def verify_pdf(facts: dict, path: Path) -> dict:
    doc = fitz.open(str(path))
    problems: list[str] = []
    tree_lines: list[str] = []
    out = RENDER_DIR / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    for index, page in enumerate(doc):
        number = index + 1
        rect = page.rect
        raw = page.get_text("rawdict")
        bands = []
        mono_lines = []
        for block in raw["blocks"]:
            for line in block.get("lines", []):
                chars = [ch for span in line["spans"] for ch in span["chars"]]
                visible = [ch for ch in chars if ch["c"].strip()]
                if not visible:
                    continue
                for ch in visible:
                    x0, y0, x1, y1 = ch["bbox"]
                    if x0 < PAGE_MARGIN or y0 < PAGE_MARGIN or x1 > rect.width - PAGE_MARGIN \
                            or y1 > rect.height - PAGE_MARGIN:
                        problems.append(f"page {number}: glyph {ch['c']!r} outside the safe area at "
                                        f"({x0:.0f},{y0:.0f})")
                        break
                x0 = min(ch["bbox"][0] for ch in visible)
                x1 = max(ch["bbox"][2] for ch in visible)
                y0 = min(ch["bbox"][1] for ch in visible)
                y1 = max(ch["bbox"][3] for ch in visible)
                sizes = [span["size"] for span in line["spans"] if span["chars"]]
                baseline = max(ch["origin"][1] for ch in visible)
                bands.append((x0, baseline, x1, min(sizes), "".join(ch["c"] for ch in visible)[:40]))
                fonts = {span["font"] for span in line["spans"]}
                if any("Consolas" in font or "DMono" in font for font in fonts) and \
                        all(abs(span["size"] - 6.3) < 0.2 for span in line["spans"] if span["chars"]):
                    mono_lines.append((line["spans"][0]["origin"], visible))
        for i, a in enumerate(bands):
            for b in bands[i + 1:]:
                # Two lines that share horizontal space must keep their baselines at least 80% of
                # the smaller font size apart; closer than that, their glyphs collide.
                if min(a[2], b[2]) - max(a[0], b[0]) > 0.5 and abs(a[1] - b[1]) < 0.8 * min(a[3], b[3]):
                    problems.append(f"page {number}: text lines collide: {a[4]!r} / {b[4]!r}")
        if mono_lines:
            mid = rect.width / 2
            advance = fitz.Font(fontfile=r"C:\Windows\Fonts\consola.ttf").text_length("M", 6.3)
            columns = {0: [], 1: []}
            for origin, visible in mono_lines:
                columns[0 if origin[0] < mid else 1].append((origin, visible))
            from dossier_pdf import FRAME_W, ML

            bases = (ML, ML + (FRAME_W - 18) / 2 + 18)   # exact column origins used by TreeColumns
            for col in (0, 1):
                entries = sorted(columns[col], key=lambda item: item[0][1])
                if not entries:
                    continue
                base = bases[col]
                for _, visible in entries:
                    slots: dict[int, str] = {}
                    for ch in visible:
                        slots[round((ch["origin"][0] - base) / advance)] = ch["c"]
                    width = max(slots) + 1
                    tree_lines.append("".join(slots.get(k, " ") for k in range(width)))
        page.get_pixmap(dpi=70).save(str(out / f"p{number:03d}.png"))
    found = parse_tree(["Tlamatini/"] + _rebuild(tree_lines[1:])) if tree_lines else []
    parity = _parity(facts["tracked"], found)
    if not parity["exact"]:
        problems.append(f"PDF tree parity failed: {parity['found']} of {parity['expected']} paths")
    return {"pages": doc.page_count, "problems": problems, "tree_parity": parity}


# ── PPTX ────────────────────────────────────────────────────────────
def verify_pptx_structure(facts: dict, path: Path) -> dict:
    prs = Presentation(str(path))
    lines: list[str] = []
    for slide in prs.slides:
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
        if not notes.startswith("Appendix A: the complete tracked file tree"):
            continue
        columns = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            paras = shape.text_frame.paragraphs
            first = next((r for p in paras for r in p.runs), None)
            if first is None or first.font.name != "Consolas" or len(paras) < 3:
                continue
            columns.append((shape.left, [p.text for p in paras]))
        for _, text_lines in sorted(columns):
            lines.extend(text_lines)
    found = parse_tree(["Tlamatini/"] + _rebuild(lines[1:])) if lines else []
    parity = _parity(facts["tracked"], found)
    problems = [] if parity["exact"] else [f"PPTX tree parity failed: {parity['found']} of "
                                           f"{parity['expected']} paths"]
    return {"slides": len(prs.slides), "problems": problems, "tree_parity": parity}


def verify_pptx_native(path: Path) -> dict:
    try:
        import pythoncom
        import win32api
        import win32com.client
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return {"available": False, "problems": [], "note": "pywin32 not installed; native check skipped"}
    pythoncom.CoInitialize()
    out = RENDER_DIR / "ppt"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    problems: list[str] = []
    checked = 0
    app = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
    except Exception as exc:  # PowerPoint not installed or not startable
        return {"available": False, "problems": [], "note": f"PowerPoint unavailable: {exc}"}
    # Developer verification must be visible; this is not a product-service window.
    app.Visible = True
    deck = next((item for item in app.Presentations
                 if Path(item.FullName).resolve() == path.resolve()), None)
    if deck is None:
        deck = app.Presentations.Open(str(path), True, False, True)
    window = deck.Windows(1)
    window.Activate()
    # PowerPoint does not expose Excel\'s Application.Hwnd COM property.
    # Match the actual document frame after activating this exact presentation.
    frames: list[int] = []
    win32gui.EnumWindows(
        lambda handle, _: frames.append(handle)
        if (win32gui.GetClassName(handle) == "PPTFrameClass"
            and path.stem.casefold() in win32gui.GetWindowText(handle).casefold()) else None,
        None,
    )
    if len(frames) != 1:
        raise RuntimeError(f"Expected one PowerPoint dossier frame, found {len(frames)}.")
    hwnd = frames[0]
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    def activate(tap_alt: bool) -> None:
        foreground = win32gui.GetForegroundWindow()
        foreground_thread, _ = win32process.GetWindowThreadProcessId(foreground)
        calling_thread = win32api.GetCurrentThreadId()
        attached = False
        try:
            if calling_thread != foreground_thread:
                win32process.AttachThreadInput(calling_thread, foreground_thread, True)
                attached = True
            if tap_alt:  # an ALT tap lets SetForegroundWindow succeed; only on the first tries,
                # so a person working in another window is not sent ALT every half second
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # The verification below refuses to run unless activation actually worked.
        finally:
            if attached:
                win32process.AttachThreadInput(calling_thread, foreground_thread, False)

    def in_front() -> bool:
        return bool(win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd)
                    and win32gui.GetForegroundWindow() == hwnd)

    # Windows refuses to hand over the foreground while someone is using another window.
    # Keep asking, and say so, instead of failing at the first refusal; never measure a
    # PowerPoint window that is not in front.
    deadline = time.monotonic() + FOREGROUND_WAIT_SECONDS
    last_notice = 0.0
    attempts = 0
    while True:
        activate(tap_alt=attempts < 3)
        attempts += 1
        if in_front():
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Native dossier verification requires visible foreground PowerPoint.")
        if time.monotonic() - last_notice > 10:
            print("PAUSED: bring the PowerPoint dossier window to the front to continue.", flush=True)
            last_notice = time.monotonic()
        time.sleep(0.5)
    print("VISIBLE VERIFIED: native PowerPoint dossier verification.", flush=True)
    try:
        width, height = deck.PageSetup.SlideWidth, deck.PageSetup.SlideHeight
        for s_index in range(1, deck.Slides.Count + 1):
            slide = deck.Slides(s_index)
            window.View.GotoSlide(s_index)
            if s_index == 1 or s_index % 10 == 0 or s_index == deck.Slides.Count:
                print(f"PowerPoint: measuring/rendering slide {s_index}/{deck.Slides.Count}", flush=True)
            for shape in _iter_shapes(slide.Shapes):
                left, top, w, h = shape.Left, shape.Top, shape.Width, shape.Height
                if left < -TOLERANCE or top < -TOLERANCE or left + w > width + TOLERANCE \
                        or top + h > height + TOLERANCE:
                    problems.append(f"slide {s_index}: shape '{shape.Name}' leaves the slide")
                if not shape.HasTextFrame or not shape.TextFrame2.HasText:
                    continue
                tr = shape.TextFrame2.TextRange
                checked += 1
                bl, bt, bw, bh = tr.BoundLeft, tr.BoundTop, tr.BoundWidth, tr.BoundHeight
                sample = tr.Text[:48].replace("\r", " ")
                if bt < top - TOLERANCE or bt + bh > top + h + TOLERANCE:
                    problems.append(f"slide {s_index}: text overflows vertically "
                                    f"({bh:.1f}pt in {h:.1f}pt): {sample!r}")
                if bl < left - TOLERANCE or bl + bw > left + w + TOLERANCE:
                    problems.append(f"slide {s_index}: text overflows horizontally "
                                    f"({bw:.1f}pt in {w:.1f}pt): {sample!r}")
            slide.Export(str(out / f"s{s_index:03d}.png"), "PNG", 1600, 900)
    finally:
        # Leave this visible document available for developer inspection.
        print("PowerPoint remains open for inspection.", flush=True)
    return {"available": True, "text_boxes_checked": checked, "problems": problems}


def _iter_shapes(shapes):
    for index in range(1, shapes.Count + 1):
        shape = shapes(index)
        if shape.Type == 6:  # msoGroup
            yield from _iter_shapes(shape.GroupItems)
        else:
            yield shape


def verify_all(facts: dict, pdf_path: Path, ppt_path: Path) -> dict:
    pdf = verify_pdf(facts, pdf_path)
    structure = verify_pptx_structure(facts, ppt_path)
    native = verify_pptx_native(ppt_path)
    problems = pdf["problems"] + structure["problems"] + native["problems"]
    for problem in problems[:60]:
        print("  PROBLEM:", problem)
    print(f"PDF: {pdf['pages']} pages, tree parity {pdf['tree_parity']['found']}/{pdf['tree_parity']['expected']}")
    print(f"PPTX: {structure['slides']} slides, tree parity "
          f"{structure['tree_parity']['found']}/{structure['tree_parity']['expected']}, "
          f"native text boxes checked: {native.get('text_boxes_checked', 0)}")
    return {"clean": not problems, "problem_count": len(problems), "pdf": pdf, "pptx": structure,
            "pptx_native": native}
