# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
#
# pptxer_render.py — PPTXer LOOKS AT ITS OWN SLIDES.
#
# Angela's requirement, verbatim: *"THE AGENT MUST BE ABLE TO VISUALIZE ITS OWN
# SLIDES, SO IT MUST [BE] SOMETHING SIMILAR TO SHOTER BUT IN THE POWER POINT
# FILE CONTEXT TO VERIFY THAT [IT] DOES NOT OVERLAP CONTENT OR WRITE TEXT
# OUTSIDE ITS MARGINS AND SPACE DESIGNATED."*
#
# ⚠️ This module is SELF-CONTAINED by design. It does NOT call the Shoter agent
# and does NOT import it. Angela: *"THIS NEW AGENT MUST BE INDEPENDENT FROM
# OTHER AGENTS, SO IF YOU NEED TO USE A CAPACITY SIMILAR TO OTHER AGENTS LIKE
# SHOTER GENERATE THE CODE AND EMBED [IT] INTO THE SAME pptxer.py."* The
# screen-capture idea is borrowed; the code is PPTXer's own.
#
# Sibling module of pptxer.py. Stdlib + Pillow; PyMuPDF and pywin32 are used
# LAZILY when present. Imports nothing from agent.*.
#
# ═════════════════════════════════════════════════════════════════════════════
#  THE FOUR-TIER LADDER  (best evidence first, always something at the bottom)
# ═════════════════════════════════════════════════════════════════════════════
#
#   TIER 1 · POWERPOINT COM          ← TRUE PIXELS. What the audience will see.
#            Drives the installed PowerPoint through `Presentation.Export`.
#            Requires PowerPoint + pywin32. This is ground truth: it is
#            PowerPoint's own renderer, PowerPoint's own line-breaking, and
#            PowerPoint's own font substitution.
#
#   TIER 2 · LIBREOFFICE HEADLESS    ← real rendering, no Microsoft Office.
#            `soffice --convert-to pdf` then rasterise with PyMuPDF. Not
#            identical to PowerPoint (different text engine) but a genuine
#            independent layout, which makes it a useful second opinion.
#
#   TIER 3 · GEOMETRIC PREVIEW       ← ALWAYS AVAILABLE, zero dependencies.
#            Paints the slide from the shape tree with Pillow: real fonts, real
#            EMU positions, real colours. Not pixel-identical to PowerPoint, but
#            it shows composition, balance and collisions truthfully — and it
#            works on a machine with no Office at all.
#
#   TIER 0 · THE GEOMETRIC AUDIT     ← runs regardless, needs no image.
#            Lives in pptxer_audit; listed here because it is what makes the
#            other three OPTIONAL rather than load-bearing.
#
# ═════════════════════════════════════════════════════════════════════════════
#  CONTRACTS (do NOT weaken)
# ═════════════════════════════════════════════════════════════════════════════
#  1. ⚠️ A TIER THAT IS UNAVAILABLE IS REPORTED AS UNAVAILABLE — NEVER AS
#     "no problems found". This is the ACPX `--version` lie in a new costume:
#     a probe that cannot run has NO opinion, and reporting `ready: null`
#     rather than `ready: true` is the whole difference between an honest
#     agent and a plausible one.
#  2. COM IS DRIVEN INVISIBLY AND ALWAYS TORN DOWN. PowerPoint is opened with
#     no window, the presentation is closed in a `finally`, and the app is quit
#     even when the export raised — a leaked POWERPNT.EXE holding a file handle
#     is a genuinely destructive failure mode.
#  3. COM NEVER TOUCHES THE USER'S ORIGINAL. The deck is copied into <app>/Temp
#     first and PowerPoint opens the COPY read-only, so an automation glitch
#     cannot modify or lock the deliverable.
#  4. FAIL-OPEN EVERYWHERE. Every tier returns a result object; none raises
#     into the caller. Rendering is diagnostics — it must never cost the deck.

import os
import shutil
import subprocess
import sys
import time

__all__ = [
    "RenderResult", "render_slides", "probe_renderers",
    "TIER_POWERPOINT", "TIER_LIBREOFFICE", "TIER_PREVIEW",
]

TIER_POWERPOINT = "powerpoint_com"
TIER_LIBREOFFICE = "libreoffice"
TIER_PREVIEW = "geometric_preview"


class RenderResult:
    """The outcome of a render attempt — including 'it could not run'."""

    __slots__ = ("tier", "images", "ok", "error", "seconds", "available",
                 "note", "width", "height")

    def __init__(self, tier="", images=None, ok=False, error="", seconds=0.0,
                 available=None, note="", width=0, height=0):
        self.tier = tier
        self.images = list(images or [])
        self.ok = bool(ok)
        self.error = error
        self.seconds = float(seconds)
        # None = "we never got to find out", which is NOT the same as False.
        self.available = available
        self.note = note
        self.width = int(width)
        self.height = int(height)

    @property
    def count(self) -> int:
        return len(self.images)

    @property
    def is_ground_truth(self) -> bool:
        """Only PowerPoint's own renderer settles what PowerPoint will draw."""
        return self.ok and self.tier == TIER_POWERPOINT

    def as_dict(self) -> dict:
        return {
            "tier": self.tier, "ok": self.ok, "images": self.count,
            "error": self.error, "seconds": round(self.seconds, 2),
            "available": self.available, "note": self.note,
            "width": self.width, "height": self.height,
        }

    def __repr__(self) -> str:
        if self.ok:
            return (f"RenderResult({self.tier}: {self.count} slides "
                    f"in {self.seconds:.1f}s)")
        return f"RenderResult({self.tier}: FAILED {self.error[:60]})"


def _temp_dir(subdir="render") -> str:
    root = (os.environ.get("TLAMATINI_TEMP") or "").strip() or os.getcwd()
    target = os.path.join(root, "PPTXer", subdir)
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:                                             # noqa: BLE001
        return root


# ─────────────────────────────────────────────────────────────────────────────
# Availability probes — honest about what they do and do not know
# ─────────────────────────────────────────────────────────────────────────────

def _powerpoint_available() -> tuple:
    """(available, detail). Checks pywin32 AND that PowerPoint is registered."""
    if not sys.platform.startswith("win"):
        return (False, "PowerPoint automation is Windows-only")
    try:
        import win32com.client  # noqa: F401
    except Exception as exc:                                      # noqa: BLE001
        return (False, f"pywin32 is not installed ({exc})")

    # Registration is the real question: pywin32 can be present on a machine
    # with no Office at all.
    try:
        import winreg
        for hive in (winreg.HKEY_CLASSES_ROOT,):
            try:
                with winreg.OpenKey(hive, r"PowerPoint.Application\CurVer"):
                    return (True, "PowerPoint is registered for automation")
            except FileNotFoundError:
                continue
    except Exception:                                             # noqa: BLE001
        pass

    for candidate in (
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office15\POWERPNT.EXE",
    ):
        if os.path.isfile(candidate):
            return (True, f"found {candidate}")

    return (False, "PowerPoint does not appear to be installed")


def _powerpoint_pids() -> set:
    """PIDs of every running POWERPNT.EXE. Empty set when psutil is absent."""
    try:
        import psutil
    except Exception:                                             # noqa: BLE001
        return set()
    found = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            name = (proc.info.get("name") or "").upper()
            if name == "POWERPNT.EXE":
                found.add(int(proc.info["pid"]))
    except Exception:                                             # noqa: BLE001
        return set()
    return found


def _reap_orphan_powerpoint(pre_existing, grace=6.0) -> list:
    """Terminate ONLY the PowerPoint this render started, and only if it hung.

    ⚠️ THE SAFETY RULE THAT MAKES THIS ACCEPTABLE: a PID present BEFORE the
    render is never touched. Angela may have PowerPoint open with unsaved work;
    an agent that kills by process NAME would destroy it. Only a process that
    (a) did not exist before we began and (b) is still alive after Quit() plus
    a grace period is considered ours and orphaned.

    Returns the PIDs actually terminated, so the caller can report them rather
    than silently killing things.
    """
    if not sys.platform.startswith("win"):
        return []
    try:
        import psutil
    except Exception:                                             # noqa: BLE001
        return []

    before = set(pre_existing or ())
    deadline = time.time() + float(grace)
    killed = []

    # Give PowerPoint a fair chance to exit on its own first. It usually does,
    # a second or two after the last COM reference is released.
    while time.time() < deadline:
        strays = _powerpoint_pids() - before
        if not strays:
            return []
        time.sleep(0.4)

    for pid in (_powerpoint_pids() - before):
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:                                     # noqa: BLE001
                proc.kill()
            killed.append(pid)
        except Exception:                                         # noqa: BLE001
            continue
    return killed


def _libreoffice_binary():
    """Path to soffice, or ''."""
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice", "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if os.path.isfile(candidate):
            return candidate
    return ""


def _pymupdf_available() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except Exception:                                             # noqa: BLE001
        return False


def probe_renderers() -> dict:
    """What can this machine actually do? Reported verbatim by the agent."""
    ppt_ok, ppt_detail = _powerpoint_available()
    lo = _libreoffice_binary()
    try:
        from PIL import Image  # noqa: F401
        pillow = True
    except Exception:                                             # noqa: BLE001
        pillow = False

    return {
        TIER_POWERPOINT: {
            "available": ppt_ok, "detail": ppt_detail,
            "quality": "ground truth — PowerPoint's own renderer",
        },
        TIER_LIBREOFFICE: {
            "available": bool(lo) and _pymupdf_available(),
            "detail": (f"soffice at {lo}" if lo else "soffice not found")
                      + ("" if _pymupdf_available() else "; PyMuPDF missing"),
            "quality": "independent real rendering (not PowerPoint's engine)",
        },
        TIER_PREVIEW: {
            "available": pillow, "detail": "Pillow" if pillow else "Pillow missing",
            "quality": "geometric preview — composition is truthful, "
                       "pixels are approximate",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — PowerPoint COM
# ─────────────────────────────────────────────────────────────────────────────

def render_with_powerpoint(pptx_path, out_dir=None, width=1600,
                           timeout=180) -> RenderResult:
    """Export every slide as a PNG using the installed PowerPoint.

    This is the only tier that answers "what will the audience actually see?",
    because it is PowerPoint doing the drawing: its own text layout, its own
    font substitution, its own autofit.
    """
    available, detail = _powerpoint_available()
    if not available:
        # Contract 1 — an unavailable tier has NO opinion.
        return RenderResult(tier=TIER_POWERPOINT, ok=False, available=False,
                            error=detail,
                            note="this tier was not run, so it reports nothing "
                                 "about the deck's correctness")

    started = time.time()
    dest = out_dir or _temp_dir("shots")
    try:
        os.makedirs(dest, exist_ok=True)
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_POWERPOINT, ok=False, available=True,
                            error=f"could not create the output directory: {exc}")

    # Contract 3 — never open the deliverable itself.
    work = os.path.join(_temp_dir("work"),
                        f"render_{os.getpid()}_{int(time.time())}.pptx")
    try:
        shutil.copy2(pptx_path, work)
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_POWERPOINT, ok=False, available=True,
                            error=f"could not copy the deck for rendering: {exc}")

    app = None
    presentation = None
    images = []
    error = ""
    # ⚠️ Record the PowerPoint processes that existed BEFORE we start, so the
    # teardown can tell OUR child from a presentation Angela has open herself.
    # Killing by name would close her unsaved work — never acceptable.
    pre_existing = _powerpoint_pids()
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        app = win32com.client.DispatchEx("PowerPoint.Application")

        # PowerPoint refuses WindowState changes while hidden on some builds,
        # and setting Visible=False outright raises on others. Try to stay
        # invisible, but never let the attempt kill the render.
        try:
            app.Visible = False
        except Exception:                                         # noqa: BLE001
            try:
                app.WindowState = 2       # ppWindowMinimized
            except Exception:                                     # noqa: BLE001
                pass
        try:
            app.DisplayAlerts = 0         # ppAlertsNone
        except Exception:                                         # noqa: BLE001
            pass

        presentation = app.Presentations.Open(
            work, ReadOnly=True, Untitled=False, WithWindow=False)

        slide_w = float(presentation.PageSetup.SlideWidth or 960.0)
        slide_h = float(presentation.PageSetup.SlideHeight or 540.0)
        px_w = int(width)
        px_h = int(round(px_w * slide_h / slide_w)) if slide_w else int(width * 0.5625)

        count = int(presentation.Slides.Count)
        deadline = started + float(timeout)
        for i in range(1, count + 1):
            if time.time() > deadline:
                error = (f"the export timed out after {timeout}s at slide {i} "
                         f"of {count}")
                break
            target = os.path.join(dest, f"slide_{i:03d}.png")
            try:
                presentation.Slides(i).Export(target, "PNG", px_w, px_h)
                if os.path.isfile(target):
                    images.append(target)
            except Exception as exc:                              # noqa: BLE001
                error = f"slide {i} failed to export: {exc}"
                break

        return RenderResult(
            tier=TIER_POWERPOINT, images=images, ok=bool(images) and not error,
            error=error, seconds=time.time() - started, available=True,
            width=px_w, height=px_h,
            note=(f"exported {len(images)} of {count} slides with the installed "
                  f"PowerPoint at {px_w}x{px_h}px"),
        )

    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_POWERPOINT, ok=False, available=True,
                            images=images, seconds=time.time() - started,
                            error=f"PowerPoint automation failed: {exc}")
    finally:
        # Contract 2 — ALWAYS tear down, in this exact order.
        #
        # ⚠️ MEASURED 2026-09-14: `app.Quit()` alone is NOT enough. A live
        # POWERPNT.EXE (pid 10316) survived a clean Quit() in testing, because
        # the COM proxies still held references and PowerPoint will not exit
        # while an automation client is attached. The fix is three-part:
        # drop the references, collect them, and only THEN verify.
        try:
            if presentation is not None:
                presentation.Close()
        except Exception:                                         # noqa: BLE001
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:                                         # noqa: BLE001
            pass

        # Release the COM proxies BEFORE CoUninitialize, then force a collect:
        # CPython may otherwise hold the last reference until the next GC, and
        # PowerPoint stays alive exactly that long.
        presentation = None
        app = None
        try:
            import gc
            gc.collect()
        except Exception:                                         # noqa: BLE001
            pass

        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:                                         # noqa: BLE001
            pass

        _reap_orphan_powerpoint(pre_existing)

        try:
            if os.path.isfile(work):
                os.remove(work)
        except Exception:                                         # noqa: BLE001
            pass


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — LibreOffice headless → PDF → PyMuPDF
# ─────────────────────────────────────────────────────────────────────────────

def render_with_libreoffice(pptx_path, out_dir=None, width=1600,
                            timeout=180) -> RenderResult:
    """Convert to PDF with LibreOffice, then rasterise with PyMuPDF."""
    soffice = _libreoffice_binary()
    if not soffice:
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=False,
                            error="LibreOffice (soffice) is not installed",
                            note="this tier was not run, so it reports nothing "
                                 "about the deck's correctness")
    if not _pymupdf_available():
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=False,
                            error="PyMuPDF is not available to rasterise the PDF",
                            note="this tier was not run")

    started = time.time()
    dest = out_dir or _temp_dir("shots_lo")
    staging = _temp_dir("lo_pdf")
    try:
        os.makedirs(dest, exist_ok=True)
        os.makedirs(staging, exist_ok=True)
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=True,
                            error=f"could not create output directories: {exc}")

    try:
        # stdin=DEVNULL is not optional: a headless soffice that decides to ask
        # a question blocks for the FULL timeout otherwise (the watchdog's
        # zero-CPU-zero-IO hang class).
        proc = subprocess.run(
            [soffice, "--headless", "--norestore", "--invisible",
             "--convert-to", "pdf", "--outdir", staging, str(pptx_path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=True,
                            seconds=time.time() - started,
                            error=f"LibreOffice did not finish within {timeout}s")
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=True,
                            error=f"could not run LibreOffice: {exc}")

    base = os.path.splitext(os.path.basename(str(pptx_path)))[0]
    pdf_path = os.path.join(staging, base + ".pdf")
    if not os.path.isfile(pdf_path):
        tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-240:]
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=True,
                            seconds=time.time() - started,
                            error=f"LibreOffice produced no PDF. {tail}".strip())

    images = []
    try:
        import fitz
        doc = fitz.open(pdf_path)
        try:
            for i, page in enumerate(doc, start=1):
                zoom = float(width) / max(1.0, page.rect.width)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                target = os.path.join(dest, f"slide_{i:03d}.png")
                pix.save(target)
                if os.path.isfile(target):
                    images.append(target)
        finally:
            doc.close()
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_LIBREOFFICE, ok=False, available=True,
                            images=images, seconds=time.time() - started,
                            error=f"the PDF could not be rasterised: {exc}")
    finally:
        try:
            os.remove(pdf_path)
        except Exception:                                         # noqa: BLE001
            pass

    return RenderResult(
        tier=TIER_LIBREOFFICE, images=images, ok=bool(images),
        seconds=time.time() - started, available=True, width=int(width),
        note=(f"rendered {len(images)} slides through LibreOffice — an "
              f"independent engine, so small differences from PowerPoint are "
              f"expected and are not necessarily defects"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TIER 3 — the geometric preview. ALWAYS available.
# ─────────────────────────────────────────────────────────────────────────────

def render_preview(slide_specs, out_dir=None, width=1600,
                   slide_w_emu=12192000, slide_h_emu=6858000) -> RenderResult:
    """Paint slides from PPTXer's OWN shape records, with Pillow.

    `slide_specs` is a list of dicts the builder produced while placing shapes:
        {"index": 1, "background": "<png path>|#RRGGBB",
         "shapes": [{"kind": "rect|text|image|line",
                     "box": {left, top, width, height},
                     "fill": "#RRGGBB", "line": "#RRGGBB",
                     "text": "...", "lines": [...], "size_pt": 24,
                     "font_path": "...", "color": "#RRGGBB",
                     "align": "left|center|right"}]}
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_PREVIEW, ok=False, available=False,
                            error=f"Pillow is not available: {exc}")

    started = time.time()
    dest = out_dir or _temp_dir("preview")
    try:
        os.makedirs(dest, exist_ok=True)
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_PREVIEW, ok=False, available=True,
                            error=f"could not create the output directory: {exc}")

    px_w = max(320, int(width))
    px_h = max(180, int(round(px_w * slide_h_emu / float(slide_w_emu or 1))))
    scale = px_w / float(slide_w_emu or 1)
    images = []
    font_cache = {}

    def _emu(v):
        return int(round(float(v) * scale))

    def _col(value, default=(0, 0, 0, 255)):
        try:
            s = str(value or "").strip().lstrip("#")
            if len(s) == 6:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
            if len(s) == 8:
                return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16),
                        int(s[6:8], 16))
        except Exception:                                         # noqa: BLE001
            pass
        return default

    def _font(path, size_pt):
        px = max(6, int(round(float(size_pt) * scale * 12700)))
        key = (path, px)
        if key in font_cache:
            return font_cache[key]
        f = None
        if path and os.path.isfile(path):
            try:
                f = ImageFont.truetype(path, px)
            except Exception:                                     # noqa: BLE001
                f = None
        if f is None:
            try:
                f = ImageFont.load_default(px)
            except Exception:                                     # noqa: BLE001
                f = ImageFont.load_default()
        font_cache[key] = f
        return f

    try:
        for spec in (slide_specs or []):
            idx = int(spec.get("index", len(images) + 1))
            bg = spec.get("background")
            if bg and isinstance(bg, str) and os.path.isfile(bg):
                try:
                    img = Image.open(bg).convert("RGB").resize(
                        (px_w, px_h), Image.LANCZOS)
                except Exception:                                 # noqa: BLE001
                    img = Image.new("RGB", (px_w, px_h), _col(bg, (16, 16, 20))[:3])
            else:
                img = Image.new("RGB", (px_w, px_h), _col(bg, (16, 16, 20))[:3])

            draw = ImageDraw.Draw(img, "RGBA")

            for shape in spec.get("shapes", []):
                box = shape.get("box") or {}
                x0 = _emu(box.get("left", 0))
                y0 = _emu(box.get("top", 0))
                x1 = x0 + _emu(box.get("width", 0))
                y1 = y0 + _emu(box.get("height", 0))
                kind = (shape.get("kind") or "rect").lower()

                if kind == "image":
                    src = shape.get("path")
                    if src and os.path.isfile(src):
                        try:
                            pic = Image.open(src).convert("RGBA")
                            pic = pic.resize((max(1, x1 - x0), max(1, y1 - y0)),
                                             Image.LANCZOS)
                            img.paste(pic, (x0, y0), pic)
                            continue
                        except Exception:                         # noqa: BLE001
                            pass
                    draw.rectangle([x0, y0, x1, y1], outline=(150, 150, 150, 200),
                                   width=2)
                    continue

                if kind == "line":
                    draw.line([x0, y0, x1, y1],
                              fill=_col(shape.get("line"), (200, 200, 200, 255)),
                              width=max(1, _emu(shape.get("weight", 12700))))
                    continue

                if kind in ("rect", "panel", "shape"):
                    fill = shape.get("fill")
                    outline = shape.get("line")
                    draw.rectangle(
                        [x0, y0, x1, y1],
                        fill=_col(fill, None) if fill else None,
                        outline=_col(outline) if outline else None,
                        width=max(1, _emu(shape.get("weight", 12700))) if outline else 0,
                    )
                    continue

                if kind == "text":
                    lines = shape.get("lines") or [shape.get("text", "")]
                    size_pt = float(shape.get("size_pt", 18))
                    fnt = _font(shape.get("font_path"), size_pt)
                    colour = _col(shape.get("color"), (245, 245, 245, 255))
                    spacing = float(shape.get("line_spacing", 1.18))
                    lh = size_pt * spacing * scale * 12700
                    align = (shape.get("align") or "left").lower()
                    ty = y0
                    for line in lines:
                        if not line:
                            ty += lh
                            continue
                        try:
                            bbox = draw.textbbox((0, 0), line, font=fnt)
                            tw = bbox[2] - bbox[0]
                        except Exception:                         # noqa: BLE001
                            tw = 0
                        if align == "center":
                            tx = x0 + ((x1 - x0) - tw) // 2
                        elif align == "right":
                            tx = x1 - tw
                        else:
                            tx = x0
                        draw.text((tx, ty), line, font=fnt, fill=colour)
                        ty += lh
                    continue

            target = os.path.join(dest, f"slide_{idx:03d}.png")
            img.save(target, "PNG")
            if os.path.isfile(target):
                images.append(target)

        return RenderResult(
            tier=TIER_PREVIEW, images=images, ok=bool(images),
            seconds=time.time() - started, available=True,
            width=px_w, height=px_h,
            note=("geometric preview drawn from PPTXer's own shape records — "
                  "composition and collisions are truthful; exact glyph "
                  "positions are approximate because PowerPoint's text engine "
                  "is not being used"),
        )
    except Exception as exc:                                      # noqa: BLE001
        return RenderResult(tier=TIER_PREVIEW, ok=False, available=True,
                            images=images, seconds=time.time() - started,
                            error=f"the preview render failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# The ladder
# ─────────────────────────────────────────────────────────────────────────────

def render_slides(pptx_path, out_dir=None, width=1600, prefer="auto",
                  slide_specs=None, slide_size=None, timeout=180) -> dict:
    """Render the deck with the best tier available. Returns the full story.

    `prefer` ∈ auto | powerpoint | libreoffice | preview | none.
    'auto' walks the ladder top-down and stops at the first tier that WORKS.

    The return value always carries `attempts`, so a caller can say exactly
    which tiers ran, which were unavailable, and which failed — and never has
    to pretend an unavailable tier was a clean bill of health.
    """
    pref = (prefer or "auto").strip().lower()
    attempts = []

    if pref == "none":
        return {"ok": False, "tier": "", "images": [], "attempts": [],
                "note": "rendering was disabled by configuration",
                "ground_truth": False}

    order = []
    if pref in ("auto", "powerpoint"):
        order.append(TIER_POWERPOINT)
    if pref in ("auto", "libreoffice"):
        order.append(TIER_LIBREOFFICE)
    if pref in ("auto", "preview"):
        order.append(TIER_PREVIEW)
    if not order:
        order = [TIER_PREVIEW]

    for tier in order:
        if tier == TIER_POWERPOINT:
            res = render_with_powerpoint(pptx_path, out_dir, width, timeout)
        elif tier == TIER_LIBREOFFICE:
            res = render_with_libreoffice(pptx_path, out_dir, width, timeout)
        else:
            sw, sh = (slide_size or (12192000, 6858000))
            res = render_preview(slide_specs or [], out_dir, width, sw, sh)

        attempts.append(res.as_dict())
        if res.ok:
            return {
                "ok": True, "tier": res.tier, "images": res.images,
                "count": res.count, "seconds": round(res.seconds, 2),
                "attempts": attempts, "note": res.note,
                "width": res.width, "height": res.height,
                # Only PowerPoint settles what PowerPoint draws. Everything else
                # is an informed second opinion, and the audit must know which
                # it is holding.
                "ground_truth": res.is_ground_truth,
            }

    return {
        "ok": False, "tier": "", "images": [], "count": 0,
        "attempts": attempts, "ground_truth": False,
        "note": ("no renderer produced images — the geometric audit still ran "
                 "and is the authority on overlaps and off-slide content"),
    }
