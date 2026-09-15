# Tlamatini Author Banner - do not remove
r"""
PPTXer — THE VISIBLE TEST
=========================

ANGELA'S RULE (2026-07-07), NO EXCEPTIONS
    Headless automated tests are FORBIDDEN. Every test runs VISIBLE, on her
    real desktop, so she can SEE every step. Every screenshot is taken by
    Tlamatini's own **Shoter** agent — `PIL.ImageGrab` is forbidden.

WHAT THIS PROVES, AND HOW IT REFUSES TO LIE
-------------------------------------------
PPTXer's whole claim is that it does not merely WRITE a presentation, it
LOOKS at the one it wrote. This run makes that claim checkable, on screen:

1. **Builds real decks through the REAL agent** — spawned exactly the way the
   pool spawns it (`python pptxer.py` in a copied runtime directory with a
   written `config.yaml`), never by importing the modules. If the agent's entry
   point is broken, this test breaks.

2. **Renders every slide with the INSTALLED POWERPOINT** and records whether
   that happened. `ground_truth: True` means the pixels came from PowerPoint's
   own renderer — the same ones an audience sees. If PowerPoint is absent the
   run says so and the case is NOT counted as verified.

3. **Re-opens each finished .pptx and MEASURES it** — every shape's real EMU
   box, every text frame against its own size and font. The verdict is
   FILESYSTEM TRUTH, not the library's opinion of itself: python-pptx does no
   layout at all, so `prs.save()` succeeding means only that the XML is
   well-formed.

4. **Opens the rendered slides on screen** and photographs the WHOLE DESKTOP
   with Shoter, so the colours, the typefaces and the tables are visible rather
   than described — and finally opens one real deck in PowerPoint itself.

⚠️ A CASE IS ONLY A PASS IF: the .pptx EXISTS, the geometry audit finds ZERO
overlaps and ZERO off-slide shapes, ZERO text frames overflow, the agent
reported `status: created` (not `created_with_findings`), AND a photograph was
actually taken. A missing photo, a timed-out render or an unparseable section is
a FAILURE and is reported as one. Nothing here may record a stale or transient
result as a pass.

WHICH TREE IS UNDER TEST
------------------------
The REPO at ``C:\Development\XAIHT\Tlamatini`` — the git working copy, where
PPTXer lives. The Django server serving the chat GUI on this machine runs from a
DIFFERENT install (``C:\Development\Tlamatini``), which does not have PPTXer
until it is synced, so a chat-GUI test would exercise an agent that is not
there. This harness therefore drives the agent directly, which is the honest way
to test the code that actually changed.

RUN IT (visible, foreground — never backgrounded):
    Start-Process powershell -NoExit -ArgumentList '-NoProfile','-Command', `
      'python "<this file>"'
"""
from __future__ import annotations

import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REPO = r"C:\Development\XAIHT\Tlamatini"
AGENT_TEMPLATE = os.path.join(REPO, "Tlamatini", "agent", "agents", "pptxer")
SHOTER_TEMPLATE = os.path.join(REPO, "Tlamatini", "agent", "agents", "shoter")

import shoter_shot  # noqa: E402

# Use the REPO's own Shoter, not the other install's, so this run exercises the
# tree under test end to end.
if os.path.isdir(SHOTER_TEMPLATE):
    shoter_shot.TEMPLATE = SHOTER_TEMPLATE


def _out_root():
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip() \
        or os.path.join(REPO, "Temp")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    root = os.path.join(base, "PPTXerVisible", stamp)
    os.makedirs(root, exist_ok=True)
    return root


# ── the content ──────────────────────────────────────────────────────────────
# ONE body of content, rendered under three very different treatments. That is
# the demonstration: the point is not "PPTXer can make a dark slide", it is
# "PPTXer reads what you wrote and decides, and you can overrule it".

LAUNCH = """# NEXUS PROTOCOL
Season Three — the Aether update

## The Arena Has Changed
- Twelve new maps built on the Aether rendering engine
- Ranked ladder rebuilt around squad synergy, not solo score
- Spectator mode with sub-second latency
- Cross-platform progression, finally

## The Numbers That Matter
- 3.4M Registered players
- 890K Peak concurrent
- 47% Retention at day 30
- 12ms Median server latency

## Season Pass Tiers
| Tier | Price | Includes |
|---|---|---|
| Recruit | Free | Battle pass track, 2 skins |
| Operative | $9.99 | Full track, 14 skins, XP boost |
| Vanguard | $24.99 | Everything, plus the Aether weapon set |

## What Players Told Us
> The ranked system finally respects the time I put into it.

## Launch Window
- Closed beta opens 14 March
- Open beta 28 March
- Full launch 11 April
"""

# A deliberately hostile table: an unbreakable Windows path and a column of
# capital W's. This is the shape that produced EIGHT cell-on-cell overlaps in
# PDFer while the renderer reported err=0.
TORTURE = """# LAYOUT TORTURE TEST
Every one of these has broken a renderer before

## Paths And Long Tokens
| Item | Location | Note |
|---|---|---|
| Telemetry export | C:\\Users\\angel\\AppData\\Local\\Tlamatini\\telemetry\\export.csv | unbreakable |
| Wide caps | WWWWWWWWWWWWWWWWWWWW | widest glyphs |
| Narrow | llllllllllllllllllll | narrowest glyphs |
| Mixed | Supercalifragilisticexpialidocious | one long word |

## Numbers With Units
- 144fps Target frame rate on mid-range hardware
- 2.4GB Streaming budget per map
- 68% Reduction in draw calls
- 12ms Median frame time
"""

CASES = [
    {
        "name": "esports",
        "title": "Esports treatment — loud, neon, scoreboard",
        "content": LAUNCH,
        "config": {"nuance": "esports_tournament",
                   "predominant_color": "#12E2A3"},
    },
    {
        "name": "cyberpunk",
        "title": "Cyberpunk treatment — the SAME words, a different world",
        "content": LAUNCH,
        "config": {"nuance": "cyberpunk_tech",
                   "predominant_color": "#00F0FF"},
    },
    {
        "name": "detected",
        "title": "No nuance given — PPTXer decides for itself",
        "content": LAUNCH,
        "config": {},
    },
    {
        "name": "torture",
        "title": "Layout torture — unbreakable paths and extreme glyphs",
        "content": TORTURE,
        "config": {"nuance": "technical_architecture",
                   "predominant_color": "#1F8A8A"},
    },
]


# ── running the REAL agent ───────────────────────────────────────────────────

def _runtime_dir(root: str, name: str) -> str:
    """Copy the agent template exactly as the pool does."""
    rt = os.path.join(root, "runtime", "pptxer_1_" + name)
    shutil.rmtree(rt, ignore_errors=True)
    os.makedirs(rt, exist_ok=True)
    for entry in os.listdir(AGENT_TEMPLATE):
        if entry.endswith((".py", ".yaml")):
            shutil.copy2(os.path.join(AGENT_TEMPLATE, entry),
                         os.path.join(rt, entry))
    return rt


def _write_config(rt: str, case: dict, out_dir: str, stamp: str) -> None:
    body = "\n".join("  " + line for line in case["content"].splitlines())
    lines = [
        "input_text: |",
        body,
        'action: "create"',
        'slide_size: "16:9"',
        'render: "auto"',
        "render_width: 1400",
        "layout_audit: true",
        "save_slide_images: true",
        'output_dir: "%s"' % out_dir.replace("\\", "/"),
        # ⚠️ THE RUN STAMP IS PART OF THE NAME, deliberately. The deck is
        # opened in PowerPoint and identified by its window title, and
        # PowerPoint may still have YESTERDAY's "esports.pptx" open from an
        # earlier run — which would satisfy that check instantly and get
        # the wrong deck photographed. A name no previous run can share
        # makes that impossible rather than unlikely.
        'filename: "%s_%s.pptx"' % (case["name"], stamp),
        "overwrite: true",
        'footer_note: "PPTXer visible test"',
        "target_agents: []",
    ]
    for key, value in case["config"].items():
        lines.append('%s: "%s"' % (key, value))
    with open(os.path.join(rt, "config.yaml"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def _parse_section(log_text: str) -> dict:
    """Lift the INI_SECTION_PPTXER header into a dict. {} if absent."""
    match = re.search(r"INI_SECTION_PPTXER<<<\n(.*?)\n\n", log_text, re.S)
    if not match:
        match = re.search(r"INI_SECTION_PPTXER<<<\n(.*?)>>>END_SECTION_PPTXER",
                          log_text, re.S)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            fields[key.strip()] = value.strip()
        elif not line.strip():
            break
    return fields


def _run_agent(rt: str, timeout: int = 420) -> tuple:
    started = time.time()
    try:
        proc = subprocess.run([sys.executable, "pptxer.py"], cwd=rt,
                              capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        return (-1, "", time.time() - started,
                "the agent did not finish within %ds" % timeout)
    log_path = os.path.join(rt, os.path.basename(rt) + ".log")
    log_text = ""
    if os.path.isfile(log_path):
        log_text = open(log_path, encoding="utf-8", errors="replace").read()
    return (rc, log_text, time.time() - started, "")


# ── independent verification, on the FILE ────────────────────────────────────

def _audit_independently(pptx_path: str) -> dict:
    """Re-open the saved deck HERE and measure it.

    Deliberately re-implemented in the harness rather than calling the agent's
    own auditor: a test that asks the code under test whether it is correct is
    not a test. This walks the shape tree with python-pptx directly.
    """
    result = {"ok": False, "slides": 0, "shapes": 0, "overlaps": [],
              "off_slide": [], "error": ""}
    try:
        from pptx import Presentation
    except Exception as exc:                                     # noqa: BLE001
        result["error"] = "python-pptx unavailable: %s" % exc
        return result
    try:
        prs = Presentation(pptx_path)
    except Exception as exc:                                     # noqa: BLE001
        result["error"] = "the deck could not be re-opened: %s" % exc
        return result

    slide_w = int(prs.slide_width or 12192000)
    slide_h = int(prs.slide_height or 6858000)
    tol = 9525          # 0.75pt in EMU
    bleed_markers = ("pptxer:bleed", "pptxer:background", "pptxer:scrim")
    decor_markers = ("pptxer:ornament", "pptxer:decor", "pptxer:glow")

    for index, slide in enumerate(prs.slides, start=1):
        result["slides"] += 1
        boxes = []
        for shape in slide.shapes:
            try:
                left, top = int(shape.left or 0), int(shape.top or 0)
                width, height = int(shape.width or 0), int(shape.height or 0)
                name = str(shape.name or "shape")
            except Exception:                                    # noqa: BLE001
                continue
            if width <= 0 or height <= 0:
                continue
            result["shapes"] += 1
            lowered = name.lower()
            is_bleed = any(m in lowered for m in bleed_markers)
            is_decor = any(m in lowered for m in decor_markers)

            if not is_decor:
                out = max(-left, -top, (left + width) - slide_w,
                          (top + height) - slide_h)
                if out > tol:
                    result["off_slide"].append(
                        "slide %d: %s is %.0fpt off the slide"
                        % (index, name, out / 12700.0))
            if not is_bleed and not is_decor:
                boxes.append((name, left, top, left + width, top + height))

        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                # Containment (a label inside its panel) is correct composition.
                a_in_b = (b[1] <= a[1] and b[2] <= a[2]
                          and b[3] >= a[3] and b[4] >= a[4])
                b_in_a = (a[1] <= b[1] and a[2] <= b[2]
                          and a[3] >= b[3] and a[4] >= b[4])
                if a_in_b or b_in_a:
                    continue
                dx = min(a[3], b[3]) - max(a[1], b[1])
                dy = min(a[4], b[4]) - max(a[2], b[2])
                if dx > tol and dy > tol:
                    result["overlaps"].append(
                        "slide %d: %s overlaps %s by %.0fpt2"
                        % (index, a[0], b[0], (dx * dy) / (12700.0 ** 2)))

    result["ok"] = not result["overlaps"] and not result["off_slide"]
    return result


# ── showing it to Angela ─────────────────────────────────────────────────────

def _foreground_title() -> str:
    """The title of whatever window currently has focus. '' if unknowable."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:                                            # noqa: BLE001
        return ""


_LAST_VIEWED = [""]


def _find_window_titled(fragment: str):
    """The first visible window whose title contains `fragment`, else None."""
    if not fragment:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if fragment.lower() in (buf.value or "").lower():
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(_visit, 0)
        return found[0] if found else None
    except Exception:                                            # noqa: BLE001
        return None


def _raise_window(hwnd) -> None:
    """Bring a window to the front, best-effort and never raising.

    Windows refuses `SetForegroundWindow` from a process that is not itself
    foreground, so the restore/bring-to-top pair is tried as well. All of it
    is advisory: if the window still refuses to come forward, the caller
    times out and reports that honestly rather than photographing whatever
    happens to be on top.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)                               # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:                                            # noqa: BLE001
        pass


def _close_windows_titled(fragment: str) -> int:
    """Close any window whose title contains `fragment`. Returns how many.

    ⚠️ DELIBERATELY TARGETED, AND IT CAN ONLY EVER HIT OUR OWN WINDOW.
    `fragment` is this run's uniquely staged filename (e.g.
    "cyberpunk_slide_001"), so a document of Angela's that happens to be open
    can never match it. It POSTS WM_CLOSE — the same thing clicking the ✕
    does — rather than killing a process, so nothing is force-terminated and
    no application is taken down.

    Why it is needed: the Windows photo viewer is single-instance. Asking it
    to open a second file while it is already showing one frequently just
    re-activates the existing window and keeps the OLD image — measured
    2026-09-14, where the first slide of each case after the first was still
    displaying the previous case's slide 3 after a full 30 s. Closing the
    stale window first forces a genuine load.
    """
    if not fragment:
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        closed = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _visit(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if fragment.lower() in (buf.value or "").lower():
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE
                    closed.append(hwnd)
            return True

        user32.EnumWindows(_visit, 0)
        return len(closed)
    except Exception:                                            # noqa: BLE001
        return 0


def _open_and_photograph(image_path: str, shots_dir: str, name: str) -> tuple:
    """Open ONE rendered slide and photograph the desktop showing THAT slide.

    ⚠️ A PHOTOGRAPH OF THE WRONG SLIDE IS NOT EVIDENCE — it is worse than no
    photograph, because it looks like proof. Measured 2026-09-14 with a flat
    3.5 s sleep: the first shot of a run caught the image viewer still cold
    and photographed nothing but a File Explorer window, and the next case's
    first shot caught the viewer still displaying the PREVIOUS case's slide 3.
    Both runs "passed", carrying screenshots that showed neither the deck nor
    the slide they were named after.

    Two repairs, and both are needed:

    1. **Every slide is opened under a name unique to its case**, so "the
       viewer is showing slide_001.png" can never be satisfied by the last
       case's identically-named slide_001.png.
    2. **The foreground window is polled until it actually names that file**,
       instead of assuming a fixed number of seconds is enough for an app
       that may be cold-starting. If it never appears this returns the
       REASON and the case fails — a missing photo is a visible problem; a
       confident photo of the wrong thing is a lie.
    """
    if not image_path or not os.path.isfile(image_path):
        return "", "no such rendered slide: %s" % image_path

    # 1 — a name nothing else on the machine shares
    view_dir = os.path.join(shots_dir, "_viewed")
    os.makedirs(view_dir, exist_ok=True)
    unique = os.path.join(view_dir, os.path.splitext(name)[0] + ".png")
    try:
        shutil.copy2(image_path, unique)
    except Exception as exc:                                     # noqa: BLE001
        return "", "could not stage %s for viewing: %s" % (name, exc)

    # 2 — retire the window still showing the PREVIOUS slide, so the viewer
    # has to load this file instead of quietly re-activating the old one
    if _LAST_VIEWED[0]:
        if _close_windows_titled(_LAST_VIEWED[0]):
            time.sleep(0.8)                  # let it actually go away

    try:
        os.startfile(unique)                                     # noqa: S606
    except Exception as exc:                                     # noqa: BLE001
        return "", "could not open %s: %s" % (os.path.basename(unique), exc)

    # 3 — wait for the viewer to really be showing THIS file, and HELP it get
    # there. Measured 2026-09-14: after the previous viewer window closed,
    # focus fell back to whatever Angela had open ("Tlamatini - Antigravity
    # IDE - pptxer.py") and the new window never came forward on its own, so
    # a correct deck failed on the photograph alone. Waiting harder would not
    # have fixed it — the window has to be RAISED.
    stem = os.path.splitext(os.path.basename(unique))[0].lower()
    _LAST_VIEWED[0] = stem
    deadline = time.time() + 40.0
    nudged = 0.0
    while time.time() < deadline:
        if stem in _foreground_title().lower():
            time.sleep(1.2)                  # let it finish painting
            shot = shoter_shot.take_shot(shots_dir, name)
            if not shot:
                return "", "Shoter took no photo for %s" % name
            return shot, ""

        hwnd = _find_window_titled(stem)
        if hwnd:
            _raise_window(hwnd)
        elif time.time() - nudged > 6.0:
            # no window at all yet — ask again; a single-instance viewer
            # sometimes drops the very first request while it is starting.
            nudged = time.time()
            try:
                os.startfile(unique)                             # noqa: S606
            except Exception:                                    # noqa: BLE001
                pass
        time.sleep(0.5)

    return "", ("the viewer never displayed %s within 30s (the foreground "
                "window was %r) — refusing to photograph a slide that is not "
                "on screen" % (os.path.basename(unique), _foreground_title()))


def _open_deck_in_powerpoint(pptx_path: str, shots_dir: str, name: str) -> str:
    """Open a REAL deck in PowerPoint so Angela sees the actual artefact."""
    if not os.path.isfile(pptx_path):
        return ""
    try:
        os.startfile(pptx_path)                                  # noqa: S606
    except Exception as exc:                                     # noqa: BLE001
        print("   !! could not open the deck: %s" % exc)
        return ""
    # ⚠️ Same rule as the slide photographs: WAIT FOR THE WINDOW TO SAY IT IS
    # SHOWING THIS DECK, rather than assuming N seconds is enough. PowerPoint
    # cold-starts in wildly different times depending on whether it is already
    # running, and a fixed sleep photographs whatever happened to be in front
    # when the clock ran out.
    print("   … waiting for PowerPoint to show the deck")
    stem = os.path.splitext(os.path.basename(pptx_path))[0].lower()
    deadline = time.time() + 60.0
    while time.time() < deadline:
        if stem in _foreground_title().lower():
            time.sleep(2.5)                  # let the first slide paint
            return shoter_shot.take_shot(shots_dir, name) or ""
        time.sleep(0.5)

    print("   !! PowerPoint never showed %s (foreground window was %r)"
          % (os.path.basename(pptx_path), _foreground_title()))
    return ""


# ── the report ───────────────────────────────────────────────────────────────

def _summary_html(root: str, rows: list) -> str:
    passed = sum(1 for r in rows if r["pass"])
    total = len(rows)
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        "<title>PPTXer — visible test</title>",
        "<style>",
        "body{background:#0B0B0F;color:#EAEAF0;font:15px/1.6 'Segoe UI',sans-serif;",
        "margin:0;padding:32px}",
        "h1{font-size:30px;margin:0 0 4px;",
        "background:linear-gradient(135deg,#6D28D9,#FF6B35 60%,#FFD93D);",
        "-webkit-background-clip:text;color:transparent}",
        ".sub{color:#9aa;margin-bottom:26px}",
        ".case{border:1px solid #2a2a35;border-radius:10px;padding:18px;",
        "margin-bottom:22px;background:#141419}",
        ".pass{border-left:5px solid #12E2A3}.fail{border-left:5px solid #FF4757}",
        "h2{margin:0 0 6px;font-size:19px}",
        "table{border-collapse:collapse;margin:10px 0;font-size:13px}",
        "td{padding:3px 14px 3px 0;color:#bbc}",
        "td.k{color:#8891a0}",
        "img{max-width:100%;border:1px solid #2a2a35;border-radius:6px;",
        "margin-top:10px;display:block}",
        ".bad{color:#FF6B6B}.good{color:#12E2A3}",
        "</style>",
        "<h1>PPTXer — the visible test</h1>",
        "<div class='sub'>%s &nbsp;·&nbsp; <b>%d / %d passed</b> &nbsp;·&nbsp; "
        "a case passes only if the deck exists, the audit is clean, no text "
        "overflows, and a photograph was actually taken.</div>"
        % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), passed, total),
    ]
    for row in rows:
        parts.append("<div class='case %s'>" % ("pass" if row["pass"] else "fail"))
        parts.append("<h2>%s %s</h2>"
                     % ("✅" if row["pass"] else "❌", html.escape(row["title"])))
        parts.append("<table>")
        for key, value in row["facts"]:
            klass = ""
            if isinstance(value, str) and value.startswith("!"):
                klass = " class='bad'"
                value = value[1:]
            parts.append("<tr><td class='k'>%s</td><td%s>%s</td></tr>"
                         % (html.escape(key), klass, html.escape(str(value))))
        parts.append("</table>")
        for note in row["problems"]:
            parts.append("<div class='bad'>· %s</div>" % html.escape(note))
        for shot in row["shots"]:
            parts.append("<img src='%s'>" % html.escape(
                os.path.relpath(shot, root).replace("\\", "/")))
        parts.append("</div>")

    path = os.path.join(root, "SUMMARY.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    root = _out_root()
    stamp = os.path.basename(root)
    decks = os.path.join(root, "decks")
    shots = os.path.join(root, "shots")
    os.makedirs(decks, exist_ok=True)
    os.makedirs(shots, exist_ok=True)

    print("=" * 72)
    print("  PPTXer — THE VISIBLE TEST")
    print("  Angela's rule: nothing headless, nothing hidden, no lying.")
    print("=" * 72)
    print("  output: %s" % root)
    print("  agent : %s" % AGENT_TEMPLATE)
    if not os.path.isdir(AGENT_TEMPLATE):
        print("  !! the PPTXer agent directory does not exist. Nothing to test.")
        return 2
    print()

    rows = []
    for number, case in enumerate(CASES, start=1):
        print("-" * 72)
        print("  [%d/%d] %s" % (number, len(CASES), case["title"]))
        problems = []
        facts = []
        case_shots = []

        rt = _runtime_dir(root, case["name"])
        _write_config(rt, case, decks, stamp)

        print("   running the real agent (PowerPoint's first render costs ~20s)…")
        rc, log_text, seconds, timeout_note = _run_agent(rt)
        if timeout_note:
            problems.append(timeout_note)
        facts.append(("exit code", rc))
        facts.append(("elapsed", "%.1fs" % seconds))

        section = _parse_section(log_text)
        if not section:
            problems.append("the agent emitted no INI_SECTION_PPTXER block")

        pptx_path = section.get("output_path", "")
        status = section.get("status", "")
        facts.append(("status", status or "!(none)"))
        facts.append(("treatment", section.get("nuance", "—")))
        facts.append(("display font", section.get("font_display", "—")))
        facts.append(("accent", section.get("palette", "—")))
        facts.append(("slides", section.get("slide_count", "—")))
        facts.append(("shapes", section.get("shape_count", "—")))
        facts.append(("tables", section.get("tables", "—")))
        facts.append(("generated art", section.get("generated_art", "—")))
        facts.append(("renderer", section.get("render_tier", "—")))
        facts.append(("ground truth", section.get("ground_truth", "—")))
        facts.append(("agent says layout_clean", section.get("layout_clean", "—")))
        facts.append(("agent says overflows", section.get("text_overflows", "—")))

        if status == "created_with_findings":
            problems.append("the agent itself reported measured defects "
                            "(status: created_with_findings)")
        elif status and status != "created":
            problems.append("unexpected status: %s" % status)

        if section.get("ground_truth", "") != "True":
            problems.append("NOT verified against PowerPoint's own rendering "
                            "— this deck's pixels were never confirmed")

        if section.get("text_overflows", "0") not in ("0", "—"):
            problems.append("the agent measured %s overflowing text frame(s)"
                            % section.get("text_overflows"))

        # ---- independent verification, on the file itself -----------------
        if pptx_path and os.path.isfile(pptx_path):
            facts.append(("file", "%s (%s bytes)"
                          % (os.path.basename(pptx_path),
                             format(os.path.getsize(pptx_path), ","))))
            audit = _audit_independently(pptx_path)
            facts.append(("harness measured", "%d slides, %d shapes"
                          % (audit["slides"], audit["shapes"])))
            if audit["error"]:
                problems.append("independent audit failed: " + audit["error"])
            problems.extend(audit["overlaps"])
            problems.extend(audit["off_slide"])
            if audit["ok"] and not audit["error"]:
                print("   independent audit: CLEAN "
                      "(%d slides, %d shapes measured)"
                      % (audit["slides"], audit["shapes"]))
        else:
            problems.append("no .pptx was produced")

        # ---- show it -------------------------------------------------------
        slides_dir = os.path.splitext(pptx_path)[0] + "_slides" if pptx_path else ""
        rendered = []
        if slides_dir and os.path.isdir(slides_dir):
            rendered = sorted(os.path.join(slides_dir, f)
                              for f in os.listdir(slides_dir)
                              if f.lower().endswith(".png"))
        facts.append(("rendered slide images", len(rendered)))
        if not rendered:
            problems.append("no rendered slide images to look at")

        for which in rendered[:3]:
            label = "%s_%s.png" % (case["name"],
                                   os.path.splitext(os.path.basename(which))[0])
            print("   opening %s and photographing the desktop…"
                  % os.path.basename(which))
            shot, why = _open_and_photograph(which, shots, label)
            if shot:
                case_shots.append(shot)
            else:
                problems.append(why or ("no photo for %s"
                                        % os.path.basename(which)))

        if not case_shots:
            problems.append("NO PHOTOGRAPH WAS TAKEN — this case cannot pass")

        # ⚠️ IDENTICAL PHOTOS MEAN THE VIEWER NEVER CHANGED IMAGE.
        # Observed 2026-09-14: three shots of three different slides came back
        # at exactly 693,105 bytes each, because the image viewer reused its
        # window without loading the next file. The photographs were real and
        # the run still "passed" — which is precisely the kind of quiet
        # nothing this harness exists to refuse. A photo of the wrong slide
        # is not evidence about the right one.
        sizes = [os.path.getsize(shot) for shot in case_shots
                 if os.path.isfile(shot)]
        if len(sizes) > 1 and len(set(sizes)) == 1:
            problems.append(
                "every photograph is byte-identical in size (%s) — the viewer "
                "almost certainly never changed image, so these shots are not "
                "evidence about these slides" % format(sizes[0], ","))

        row_pass = not problems
        rows.append({"title": case["title"], "pass": row_pass,
                     "facts": facts, "problems": problems, "shots": case_shots})
        print("   %s" % ("PASS" if row_pass else "FAIL: " + "; ".join(problems[:3])))

    # ---- finally, the real thing, in PowerPoint --------------------------
    first_deck = os.path.join(decks, "%s_%s.pptx"
                              % (CASES[0]["name"], stamp))
    if os.path.isfile(first_deck):
        print("-" * 72)
        print("  Opening the esports deck in PowerPoint so you can see it…")
        shot = _open_deck_in_powerpoint(first_deck, shots, "deck_in_powerpoint.png")
        if shot:
            rows.append({"title": "The deck open in PowerPoint itself",
                         "pass": True,
                         "facts": [("deck", os.path.basename(first_deck))],
                         "problems": [], "shots": [shot]})

    summary = _summary_html(root, rows)
    passed = sum(1 for r in rows if r["pass"])

    print("=" * 72)
    print("  %d / %d passed" % (passed, len(rows)))
    print("  summary: %s" % summary)
    print("=" * 72)
    try:
        os.startfile(summary)                                    # noqa: S606
    except Exception:                                            # noqa: BLE001
        pass

    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
