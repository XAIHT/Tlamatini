# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
r"""
THE AVATAR PRESENCE REGRESSION — VISIBLE, PERMANENT, AND HARD TO FOOL.
======================================================================

    From the repository root:
        .\python\python.exe Tests\test_avatar_presence_visible.py
    or, for the one-command visible launch:
        powershell -ExecutionPolicy Bypass -File Tests\run_presence_tests.ps1

ANGELA'S RULES THIS OBEYS (2026-07-07 / 2026-08-02 / 2026-09-11)
    • HEADLESS IS FORBIDDEN. Chrome opens on her real desktop, headed, and she
      watches every step. `--headless` is not accepted by this file at all.
    • EVERY SCREENSHOT IS TAKEN BY SHOTER, Tlamatini's own agent, capturing the
      WHOLE desktop. `PIL.ImageGrab` is never imported here. If Shoter cannot
      run we SAY SO and carry on — we never fall back to Pillow, because a test
      that lies about who took the photo is worse than one with no photo.
    • NEVER RECORD A STALE OR TIMED-OUT RESULT AS A PASS.

WHY THESE PARTICULAR ASSERTIONS
    The defect this suite exists to prevent is not "the avatar is missing" —
    it is "the avatar is PRESENT and looks alive while being driven by a timer
    that never listens to the speech". A test that only checks the canvas
    exists would have passed against the old 150 ms metronome. So the suite is
    built to be hard to fool:

      · It reads REAL CANVAS PIXELS and proves they change between frames.
      · It samples the mouth at frame rate and proves the values are
        CONTINUOUS (a metronome produces exactly two), and that they
        CORRELATE with the phonetic openness of the text being spoken.
      · It runs the whole suite a SECOND time with `prefers-reduced-motion:
        reduce` emulated, because Angela instructed that she must animate
        anyway, and that is exactly the kind of rule a future refactor
        silently reverts.
      · It runs a pass with the GPU DISABLED and the CPU THROTTLED 6×, because
        the target machine is the President's office PC: a good computer with
        no graphics card.

EXIT CODE is 0 only when every check passed. Any failure is non-zero and is
listed in the console and in the generated SUMMARY.html.
"""
from __future__ import annotations

import json
import os
from collections import Counter
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / ".claude" / "skills" / "tlamatini-daily-chat-test" / "harness"
OUT = ROOT / "Temp" / "avatar_presence"
BASE_URL = os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("TLAMATINI_USER", "user")
PASSWORD = os.environ.get("TLAMATINI_PASS", "changeme")
CHAT_PATH = "/agent/agent/"

# The phrase the lip-sync checks are driven with. Deliberately Spanish, with
# sealed consonants (m/b/p) next to wide vowels (a/o) so a mouth that is
# genuinely following the text produces a very different curve from a timer.
PHRASE = "Buenas tardes, señora Presidenta. Soy Tlamatini, mucho gusto."

# ── Shoter ───────────────────────────────────────────────────────────────────
# Reuse Tlamatini's OWN screenshot launcher rather than growing a second one.
# ⚠️ The harness copy pins TEMPLATE to C:\Development\Tlamatini\... which is not
# where this repository lives, so we re-point it at the real agent template. The
# launcher itself (config.yaml + `python shoter.py`) is untouched — using the
# agent IS the test of the agent.
sys.path.insert(0, str(HARNESS))
try:
    import shoter_shot  # type: ignore
    shoter_shot.TEMPLATE = str(ROOT / "Tlamatini" / "agent" / "agents" / "shoter")
    _SHOTER = True
except Exception as _exc:                                   # noqa: BLE001
    print("!! Shoter launcher unavailable (%s). Photos will be skipped; "
          "Pillow is NEVER used as a fallback." % str(_exc)[:120])
    _SHOTER = False

_PHOTOS: list[tuple[str, str]] = []


def photo(name: str, caption: str) -> None:
    """Full-desktop photograph, taken by Shoter. Never by anything else."""
    if not _SHOTER:
        print("   (no photo: Shoter unavailable) %s" % caption)
        return
    fn = "%s.png" % name
    path = shoter_shot.take_shot(str(OUT / "photos"), fn, runtime_base=str(OUT))
    if path:
        _PHOTOS.append((os.path.basename(path), caption))
        print("   photo: %s" % path)


# ── result bookkeeping ───────────────────────────────────────────────────────
class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, group: str, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"group": group, "name": name, "ok": bool(ok), "detail": detail})
        print("   %s  %-52s %s" % ("PASS" if ok else "FAIL", name, detail))
        return bool(ok)

    def failed(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]

    @property
    def total(self) -> int:
        return len(self.rows)


R = Results()


# ── in-page helpers ──────────────────────────────────────────────────────────
# Sampling happens INSIDE the page on requestAnimationFrame. Polling from
# Python over the CDP wire would alias badly against a 30-60 fps animation and
# could not prove continuity.
COLLECTOR = """
(ms) => new Promise((resolve) => {
  const out = { mouth: [], eye: [], t: [], hashes: [], quiet: [] };
  const c = document.getElementById('tlm-canvas');
  const g = c && c.getContext && c.getContext('2d', { willReadFrequently: true });
  const t0 = performance.now();
  function tick() {
    const s = window.TlamatiniPresence.stats();
    out.mouth.push(s.mouth);
    out.eye.push(s.eye);
    out.t.push(performance.now() - t0);
    if (g) {
      try {
        // A small central patch is enough to prove the picture is moving, and
        // cheap enough not to disturb what we are measuring.
        const w = Math.max(1, Math.floor(c.width / 2));
        const h = Math.max(1, Math.floor(c.height / 2));
        const d = g.getImageData(Math.max(0, w - 8), Math.max(0, h - 8), 16, 16).data;
        let acc = 0;
        for (let i = 0; i < d.length; i += 4) { acc = (acc * 31 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) % 2147483647; }
        out.hashes.push(acc);
        // A frame is "quiet" only when NOTHING about her face is changing:
        // eyes fully open, mouth fully shut. Those are the frames that must be
        // pixel-identical to each other, because nothing on screen has any
        // business moving in them.
        out.quiet.push(s.eye >= 0.999 && s.mouth <= 0.001);
      } catch (e) { /* tainted or unsupported - the other proofs still stand */ }
    }
    if (performance.now() - t0 < ms) { requestAnimationFrame(tick); } else { resolve(out); }
  }
  requestAnimationFrame(tick);
})
"""


def expected_track(page, phrase: str) -> list[float]:
    return page.evaluate(
        "(s) => Array.from(s).map(ch => window.TlamatiniPresence.opennessOf(ch))", phrase)


def pearson(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 8:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / ((va ** 0.5) * (vb ** 0.5))


def login_and_open(page) -> None:
    """Log in and land on the chat page, or say precisely why we could not.

    A vague timeout here used to abort the whole run and leave an empty report,
    which is the one thing a permanent regression must never do: a test that
    cannot say what went wrong is indistinguishable from a test nobody ran.
    """
    page.goto(BASE_URL + "/", timeout=45000)
    if page.query_selector("#id_username"):
        page.fill("#id_username", USER)
        page.fill("#id_password", PASSWORD)
        page.click("form button[type=submit]")
        page.wait_for_load_state("domcontentloaded", timeout=45000)
        if page.query_selector("#id_username"):
            raise RuntimeError(
                "Login was rejected for user '%s'. Set the real credentials and run again:\n"
                "    $env:TLAMATINI_USER='angela'; $env:TLAMATINI_PASS='...'" % USER)
    page.goto(BASE_URL + CHAT_PATH, timeout=45000)
    if page.query_selector("#id_username"):
        raise RuntimeError("%s bounced back to the login page - the session did not stick."
                           % CHAT_PATH)
    try:
        page.wait_for_selector("#tlm-avatar-dock", timeout=30000)
    except Exception as exc:                                 # noqa: BLE001
        raise RuntimeError("The avatar dock never appeared on %s (%s). Is this the chat page?"
                           % (CHAT_PATH, type(exc).__name__)) from exc


def wait_ready(page, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.evaluate("() => !!(window.TlamatiniPresence && window.TlamatiniPresence.isReady())"):
                return True
        except Exception:                                    # noqa: BLE001
            pass
        time.sleep(0.25)
    return False


# ═════════════════════════════════════════════════════════════════════════════
#  THE SUITE
# ═════════════════════════════════════════════════════════════════════════════
def suite(page, label: str, expect_reduced: bool) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    print("\n== %s ==" % label)
    login_and_open(page)

    # ── A · the engine is live ───────────────────────────────────────────────
    R.check(label, "A1 presence engine object exists",
            page.evaluate("() => !!window.TlamatiniPresence"))
    R.check(label, "A2 sizing module exists",
            page.evaluate("() => !!window.TlamatiniAvatarSize"))
    ready = wait_ready(page)
    R.check(label, "A3 engine reports ready", ready)
    if not ready:
        photo("%s_not_ready" % label, "%s: the presence engine never became ready" % label)
        return

    st = page.evaluate("() => window.TlamatiniPresence.stats()")
    R.check(label, "A4 canvas has real pixels",
            st["width"] > 0 and st["height"] > 0, "%dx%d css px" % (st["width"], st["height"]))
    R.check(label, "A5 all four portraits pre-scaled", st["layers"] == 4,
            "layers=%s" % st["layers"])
    R.check(label, "A6 <img> fallback stack retired while canvas is live",
            page.evaluate("() => document.getElementById('tlm-face')"
                          ".classList.contains('tlm-canvas-live')"))
    R.check(label, "A7 fallback <img> elements still present in the DOM",
            page.evaluate("() => document.querySelectorAll('#tlm-face img').length") == 4)
    photo("%s_01_idle" % label, "%s · idle, engine live at %dx%d"
          % (label, st["width"], st["height"]))

    # ── B · she is genuinely animating ───────────────────────────────────────
    s1 = page.evaluate("() => window.TlamatiniPresence.stats().frames")
    data = page.evaluate(COLLECTOR, 2500)
    s2 = page.evaluate("() => window.TlamatiniPresence.stats()")
    R.check(label, "B1 frames advanced over 2.5 s", s2["frames"] > s1 + 20,
            "%d -> %d" % (s1, s2["frames"]))
    R.check(label, "B2 measured fps is usable", s2["fps"] >= 10, "fps=%s" % s2["fps"])
    # ⚠️ THE IDLE PORTRAIT MUST BE ROCK-STEADY. Angela, 2026-09-11, after
    # watching the first run: "the complete image of her moves in offset that
    # look uncomfortable, weird!, make her image do not displace inside the
    # little frame!" So the assertion is INVERTED from what you might expect:
    # while she is idle and not mid-blink, consecutive frames must be
    # PIXEL-IDENTICAL. Any per-frame breath, sway or jitter shows up here
    # immediately as a collapse in this percentage.
    quiet_hashes = [h for h, q in zip(data["hashes"], data["quiet"]) if q]
    share = (Counter(quiet_hashes).most_common(1)[0][1] / len(quiet_hashes)) if quiet_hashes else 0.0
    R.check(label, "B3 HER PORTRAIT DOES NOT DRIFT in the frame", share >= 0.95,
            "%.0f%% of the %d quiet frames are pixel-identical"
            % (share * 100, len(quiet_hashes)))

    # ── C · Angela's rule: she animates even under reduced-motion ────────────
    if expect_reduced:
        R.check(label, "C1 reduced-motion is actually emulated",
                page.evaluate("() => window.matchMedia('(prefers-reduced-motion: reduce)').matches"))
        R.check(label, "C2 SHE STILL ANIMATES under reduced-motion",
                s2["frames"] > s1 + 20 and s2["fps"] >= 10,
                "%d frames, %s fps - Angela 2026-09-11: normal behaviour, not an a11y feature"
                % (s2["frames"] - s1, s2["fps"]))

    # ── D · blinking, and blinking CONTINUOUSLY ──────────────────────────────
    eyes = [v for v in data["eye"]]
    mid_eye = [v for v in eyes if 0.05 < v < 0.95]
    b1 = page.evaluate("() => window.TlamatiniPresence.stats().blinks")
    long_sample = page.evaluate(COLLECTOR, 14000)
    b2 = page.evaluate("() => window.TlamatiniPresence.stats().blinks")
    R.check(label, "D1 she blinks on a human schedule", b2 > b1,
            "%d blinks in 14 s (12-20/min expected)" % (b2 - b1))
    mid_eye += [v for v in long_sample["eye"] if 0.05 < v < 0.95]
    R.check(label, "D2 blinks are CONTINUOUS, not a two-frame cut", len(mid_eye) >= 3,
            "%d intermediate eyelid values captured" % len(mid_eye))
    # The portrait is static by instruction, so the ONLY thing that may repaint
    # the canvas while she is silent is her eyelids. Proving the pixels change
    # here proves the blink is real on screen, not just a number in `stats()`.
    R.check(label, "D3 the canvas really repaints when she blinks",
            len(set(long_sample["hashes"])) >= 2,
            "%d distinct canvas frames across 14 s" % len(set(long_sample["hashes"])))
    photo("%s_02_blink" % label, "%s · %d blinks observed in 14 s" % (label, b2 - b1))

    # ── E · lip sync: the anti-metronome proof ───────────────────────────────
    R.check(label, "E1 phonetic table is sane (a wider than m)",
            page.evaluate("() => window.TlamatiniPresence.opennessOf('a') > "
                          "window.TlamatiniPresence.opennessOf('m')"))
    dur = 4200
    page.evaluate("([t, d]) => window.TlamatiniPresence.simulateSpeech(t, d)", [PHRASE, dur])
    spoke = page.evaluate(COLLECTOR, dur + 300)
    mouth = spoke["mouth"]
    R.check(label, "E2 the mouth really opens", max(mouth) > 0.5, "peak=%.3f" % max(mouth))
    R.check(label, "E3 the mouth really closes", min(mouth) < 0.15, "floor=%.3f" % min(mouth))
    distinct = len(set(round(v, 3) for v in mouth))
    R.check(label, "E4 MOUTH IS CONTINUOUS (a metronome yields 2 values)", distinct > 25,
            "%d distinct mouth values" % distinct)

    # Does the curve actually follow the SENTENCE? Resample the expected
    # per-character openness onto the sample times and correlate.
    track = expected_track(page, PHRASE)
    exp: list[float] = []
    for t in spoke["t"]:
        idx = int(min(len(track) - 1, max(0, (t / dur) * (len(track) - 1))))
        lo, hi = max(0, idx - 1), min(len(track) - 1, idx + 1)
        exp.append(track[lo] * 0.25 + track[idx] * 0.5 + track[hi] * 0.25)
    r = pearson(mouth, exp)
    R.check(label, "E5 MOUTH FOLLOWS THE TEXT (correlation with the phrase)", r > 0.45,
            "pearson r = %.3f against the phonetic track" % r)
    photo("%s_03_speaking" % label, "%s · lip sync, r=%.2f, %d distinct mouth values"
          % (label, r, distinct))

    page.evaluate("() => window.TlamatiniPresence.endSimulation()")
    time.sleep(0.6)
    R.check(label, "E6 mouth closes when the speech ends",
            page.evaluate("() => window.TlamatiniPresence.stats().mouth") < 0.06)

    R.check(label, "E7 speechSynthesis.speak is instrumented, not replaced",
            page.evaluate("() => !!(window.speechSynthesis && window.speechSynthesis.__tlmPatched)"))
    R.check(label, "E8 the canvas really repaints while she speaks",
            len(set(spoke["hashes"])) >= 8,
            "%d distinct canvas frames while speaking" % len(set(spoke["hashes"])))

    # ── F · sizing, Angela's 120 px floor ────────────────────────────────────
    R.check(label, "F1 minimum size is exactly 120 px",
            page.evaluate("() => window.TlamatiniAvatarSize.min()") == 120)
    page.evaluate("() => window.TlamatiniAvatarSize.set(50)")
    time.sleep(0.4)
    w_small = page.evaluate("() => Math.round(document.getElementById("
                            "'tlm-avatar-dock').getBoundingClientRect().width)")
    R.check(label, "F2 a smaller request is CLAMPED to the floor", w_small >= 119,
            "asked 50 px, got %d px" % w_small)

    page.evaluate("() => window.TlamatiniAvatarSize.set(120)")
    time.sleep(0.5)
    small = page.evaluate("() => window.TlamatiniPresence.stats()")
    R.check(label, "F3 she runs at the 120 px minimum", small["width"] > 0 and small["layers"] == 4,
            "%dx%d" % (small["width"], small["height"]))
    photo("%s_04_size120" % label, "%s · at the 120 px minimum" % label)

    page.evaluate("() => window.TlamatiniAvatarSize.set(360)")
    time.sleep(0.7)
    big = page.evaluate("() => window.TlamatiniPresence.stats()")
    R.check(label, "F4 she scales up to presentation size", big["width"] > small["width"] + 100,
            "%d px -> %d px" % (small["width"], big["width"]))
    R.check(label, "F5 the portraits are RE-SCALED, not stretched",
            page.evaluate("() => document.getElementById('tlm-canvas').width") >
            int(small["width"]), "canvas backing store grew with her")
    R.check(label, "F6 she floats free of the chat form when enlarged",
            page.evaluate("() => document.getElementById('tlm-avatar-dock')"
                          ".classList.contains('tlm-floating')"))
    photo("%s_05_size360" % label, "%s · presentation size, 360 px" % label)

    R.check(label, "F7 the resize handle exists and is reachable by keyboard",
            page.evaluate("() => { const h=document.getElementById('tlm-avatar-resize');"
                          " return !!h && h.getAttribute('tabindex')==='0'; }"))
    before = page.evaluate("() => window.TlamatiniAvatarSize.get()")
    page.focus("#tlm-avatar-resize")
    page.keyboard.press("ArrowUp")
    time.sleep(0.35)
    after = page.evaluate("() => window.TlamatiniAvatarSize.get()")
    R.check(label, "F8 arrow keys resize her", after > before, "%d -> %d px" % (before, after))

    # Persistence across a reload is what makes the setting hers, not the tab's.
    page.evaluate("() => window.TlamatiniAvatarSize.set(240)")
    time.sleep(0.4)
    page.reload(timeout=45000)
    page.wait_for_selector("#tlm-avatar-dock", timeout=30000)
    wait_ready(page)
    time.sleep(0.6)
    restored = page.evaluate("() => window.TlamatiniAvatarSize.get()")
    R.check(label, "F9 her size survives a reload", abs(restored - 240) <= 4,
            "restored %d px" % restored)

    R.check(label, "F10 clicking the handle does not make her talk",
            not page.evaluate("""() => { const b=document.getElementById('tlm-avatar-bubble');
                const before=b?b.className:''; document.getElementById('tlm-avatar-resize').click();
                return b ? b.classList.contains('tlm-show') && before.indexOf('tlm-show')<0 : false; }"""))

    page.evaluate("() => window.TlamatiniAvatarSize.set(0)")
    time.sleep(0.4)
    R.check(label, "F11 she returns to the docked layout",
            not page.evaluate("() => document.getElementById('tlm-avatar-dock')"
                              ".classList.contains('tlm-floating')"))

    # ── G · the machine in Palacio Nacional: no GPU, ordinary CPU ────────────
    costs = page.evaluate("() => window.TlamatiniPresence.stats().frameCostMs")
    R.check(label, "G1 a frame costs almost nothing", costs < 6.0,
            "%.3f ms per composited frame" % costs)

    client = page.context.new_cdp_session(page)
    client.send("Emulation.setCPUThrottlingRate", {"rate": 6})
    time.sleep(2.5)
    # Make her TALK while the CPU is crippled. A silent avatar on a static
    # portrait would repaint identical pixels and prove nothing; the honest
    # question is whether the lip sync survives the machine she has to run on.
    page.evaluate("([t, d]) => window.TlamatiniPresence.simulateSpeech(t, d)", [PHRASE, 3000])
    thr = page.evaluate(COLLECTOR, 3000)
    st_thr = page.evaluate("() => window.TlamatiniPresence.stats()")
    R.check(label, "G2 SHE SURVIVES A 6x SLOWER CPU", st_thr["fps"] >= 8,
            "fps=%s, target=%s" % (st_thr["fps"], st_thr["targetFps"]))
    R.check(label, "G3 still painting under throttle", len(set(thr["hashes"])) >= 2,
            "%d distinct canvas frames" % len(set(thr["hashes"])))
    photo("%s_06_throttled" % label, "%s · CPU throttled 6x, still %s fps"
          % (label, st_thr["fps"]))
    client.send("Emulation.setCPUThrottlingRate", {"rate": 1})
    time.sleep(1.5)

    # ── H · nothing broke ────────────────────────────────────────────────────
    R.check(label, "H1 no uncaught JavaScript errors on the page",
            not errors, "; ".join(errors[:2]) if errors else "clean")


# ═════════════════════════════════════════════════════════════════════════════
def write_summary() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = R.failed()
    groups: dict[str, list[dict]] = {}
    for row in R.rows:
        groups.setdefault(row["group"], []).append(row)
    parts = ["<!doctype html><meta charset='utf-8'><title>Avatar presence report</title>",
             "<style>body{background:#0b0e12;color:#e3ece8;font:14px/1.6 system-ui,sans-serif;"
             "margin:0;padding:32px}h1{font-size:26px;margin:0 0 4px}"
             ".sub{color:#8fa39d;margin-bottom:26px}h2{font-size:15px;text-transform:uppercase;"
             "letter-spacing:.12em;color:#35b98c;margin:28px 0 10px}"
             "table{border-collapse:collapse;width:100%;max-width:1100px}"
             "td{padding:7px 10px;border-bottom:1px solid #1d2a2e;vertical-align:top}"
             ".ok{color:#35b98c;font-weight:700}.no{color:#e0563c;font-weight:700}"
             ".d{color:#8fa39d;font-family:ui-monospace,monospace;font-size:12px}"
             "img{max-width:560px;border:1px solid #223237;border-radius:6px;margin:8px 12px 8px 0}"
             ".v{font-size:20px;padding:12px 16px;border-radius:6px;display:inline-block}"
             "</style>",
             "<h1>Tlamatini · avatar presence regression</h1>",
             "<div class='sub'>%s &middot; %s &middot; %d checks</div>"
             % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), BASE_URL, R.total)]
    verdict = ("<div class='v' style='background:#123;color:#35b98c'>ALL %d CHECKS PASSED</div>"
               % R.total) if not failed else (
        "<div class='v' style='background:#2a1210;color:#e0563c'>%d of %d CHECKS FAILED</div>"
        % (len(failed), R.total))
    parts.append(verdict)
    for gname, rows in groups.items():
        parts.append("<h2>%s</h2><table>" % gname)
        for row in rows:
            parts.append("<tr><td class='%s'>%s</td><td>%s</td><td class='d'>%s</td></tr>"
                         % ("ok" if row["ok"] else "no", "PASS" if row["ok"] else "FAIL",
                            row["name"], row["detail"]))
        parts.append("</table>")
    if _PHOTOS:
        parts.append("<h2>Photographs (taken by Shoter, whole desktop)</h2>")
        for fn, cap in _PHOTOS:
            parts.append("<div><img src='photos/%s' alt='%s'><div class='d'>%s</div></div>"
                         % (fn, cap, cap))
    path = OUT / "SUMMARY.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    (OUT / "results.json").write_text(json.dumps(R.rows, indent=2), encoding="utf-8")
    return path


def main() -> int:
    if "--headless" in sys.argv:
        print("HEADLESS IS FORBIDDEN. This test always runs visibly, on Angela's real "
              "desktop, so every step can be seen. Remove --headless and run it again.")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright for Python is not installed in this interpreter.\n"
              "    pip install playwright && python -m playwright install chromium")
        return 3

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "photos").mkdir(parents=True, exist_ok=True)
    print("Tlamatini avatar presence regression — VISIBLE (never headless).")
    print("Target: %s   user: %s" % (BASE_URL, USER))

    # No GPU. Deliberately. The target machine is the President's office PC and
    # every claim in this suite has to hold there, not on Angela's workstation.
    args = ["--disable-gpu", "--disable-software-rasterizer",
            "--use-gl=swiftshader", "--start-maximized"]

    with sync_playwright() as p:
        launched = None
        for channel in ("chrome", "msedge", None):
            try:
                launched = p.chromium.launch(headless=False, channel=channel, args=args)
                print("Browser: %s (headed, GPU disabled)" % (channel or "bundled chromium"))
                break
            except Exception:                                # noqa: BLE001
                continue
        if launched is None:
            print("Could not launch a visible browser. Install Chrome, or run "
                  "python -m playwright install chromium")
            return 4

        try:
            # PASS 1 — ordinary conditions.
            ctx = launched.new_context(no_viewport=True)
            page = ctx.new_page()
            try:
                suite(page, "normal", expect_reduced=False)
            except Exception as exc:                         # noqa: BLE001
                R.check("normal", "SUITE ABORTED", False, str(exc).replace("\n", " ")[:220])
                traceback.print_exc()
            finally:
                ctx.close()

            # PASS 2 — the same suite with reduced-motion forced on, because
            # Angela's instruction is exactly the kind of rule a later
            # "accessibility cleanup" quietly puts back.
            ctx2 = launched.new_context(no_viewport=True, reduced_motion="reduce")
            page2 = ctx2.new_page()
            try:
                suite(page2, "reduced-motion", expect_reduced=True)
            except Exception as exc:                         # noqa: BLE001
                R.check("reduced-motion", "SUITE ABORTED", False,
                        str(exc).replace("\n", " ")[:220])
                traceback.print_exc()
            finally:
                ctx2.close()
        finally:
            summary = write_summary()
            try:
                launched.close()
            except Exception:                                # noqa: BLE001
                pass

    failed = R.failed()
    print("\n" + "=" * 68)
    if failed:
        print("FAILED: %d of %d checks" % (len(failed), R.total))
        for row in failed:
            print("   - [%s] %s  %s" % (row["group"], row["name"], row["detail"]))
    else:
        print("ALL %d CHECKS PASSED." % R.total)
    print("Report: %s" % summary)
    print("=" * 68)
    try:
        os.startfile(str(summary))                           # noqa: S606 - show her the report
    except Exception:                                        # noqa: BLE001
        pass
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:                                        # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(1)
