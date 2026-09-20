#!/usr/bin/env python
# ══════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Tlamatini Author Banner — do not remove
# ══════════════════════════════════════════════════════════════════════
"""VISIBLE proof that the context gauge moves on a REAL request.

Context Governor, step 1 (measurement only). Headed real Chrome on Angela's
own desktop, the real chat GUI, a real Multi-Turn request. Every photo is
taken by Tlamatini's **Shoter** agent — never PIL.

What it proves, in order:

  1. Before anything is sent the row EXISTS but is INVISIBLE at zero height
     ("no gauge data ⇒ no gauge" — the page is what it always was).
  2. On a real request the ring APPEARS, coloured by zone.
  3. The legend tells the truth: the byte figure carries NO qualifier, the
     token figure says "est.", and the exact integer is on the hover title.
  4. The ring MOVES — a second, different measurement arrives as the
     Multi-Turn loop grows.
  5. The Send button is STILL on screen (the Fig-21 layout trap: counting
     the new row in computeFormMinHeight AND the ResizeObserver).
  6. tlamatini.log really carries the `--- [CONTEXT]` lines.

HONESTY GUARDS (Angela's rule — never record a stale or transient state as
a pass):
  * exit 3 if the app answering :8000 has no gauge row at all — that means
    the FROZEN install is serving and the code under test is in the SOURCE
    tree. That is a WRONG-TARGET result, not a failure of the feature.
  * "the ring moved" requires two measurements that genuinely DIFFER.
  * if the model never answers, that is reported as its own line; it is
    never dressed up as a pass of something else.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C                       # noqa: E402
from shoter_shot import take_shot        # noqa: E402

from playwright.sync_api import sync_playwright   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "reports", "context_gauge")
os.makedirs(OUT, exist_ok=True)

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "..", "..", "Tlamatini", "tlamatini.log")
LOG_PATH = os.path.abspath(LOG_PATH)

# A SAFE, read-only task that needs a real tool call, so the loop runs more
# than one model step and the ring has something to move for.
PROMPT = ("Use chat_agent_globber to list the .py files directly inside "
          "agent/rag and then tell me how many there are. Do not change "
          "any file.")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:200]))
    print(("  [PASS] " if ok else "  [FAIL] ") + name
          + (("   -> " + str(detail)[:140]) if detail else ""))
    return bool(ok)


READ_GAUGE = """
() => {
  const el = document.getElementById('context-gauge-row');
  if (!el) return null;
  const t = (sel) => { const n = el.querySelector(sel); return n ? (n.textContent || '').trim() : ''; };
  const ttl = (sel) => { const n = el.querySelector(sel); return n ? (n.title || '') : ''; };
  const line = el.querySelector('.ctxg-spark-line');
  return {
    height: el.offsetHeight,
    visible: el.offsetHeight > 0 && el.classList.contains('ctxg-visible'),
    zone: el.getAttribute('data-zone') || '',
    bytes: t('.ctxg-bytes'),
    bytesTitle: ttl('.ctxg-bytes'),
    tokens: t('.ctxg-tokens'),
    tokensTitle: ttl('.ctxg-tokens'),
    zoneWord: t('.ctxg-zone-word'),
    streams: t('.ctxg-streams-label'),
    points: line ? (line.getAttribute('points') || '') : ''
  };
}
"""

SEND_ON_SCREEN = """
() => {
  const b = document.getElementById('chat-message-submit');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  return {found: true, bottom: Math.round(r.bottom),
          viewport: window.innerHeight, onScreen: r.bottom <= window.innerHeight + 1};
}
"""


def wait_for(page, predicate, timeout_s, poll=0.25):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = page.evaluate(READ_GAUGE)
        if predicate(last):
            return last, True
        time.sleep(poll)
    return last, False


def main():
    print("=" * 74)
    print("CONTEXT GAUGE - VISIBLE PROOF ON A REAL REQUEST")
    print("Angela Lopez Mendoza  -  Tlamatini Context Governor, step 1")
    print("=" * 74)
    print("target : %s%s" % (C.BASE_URL, C.CHAT_PATH))
    print("log    : %s" % LOG_PATH)
    print("prompt : %s" % PROMPT)
    print("-" * 74)

    log_before = 0
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
            log_before = fh.read().count("--- [CONTEXT]")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome",
                                         args=["--start-maximized"])
        except Exception as exc:                       # noqa: BLE001
            print("real Chrome unavailable (%s) - using bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_context(no_viewport=True).new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)

        # ---------- login ------------------------------------------------
        page.goto(C.BASE_URL + C.LOGIN_PATH)
        page.fill(C.SEL["login_user"], C.USERNAME)
        page.fill(C.SEL["login_pass"], C.PASSWORD)
        page.click(C.SEL["login_submit"])
        page.wait_for_load_state("networkidle")
        page.goto(C.BASE_URL + C.CHAT_PATH)
        page.wait_for_selector(C.SEL["chat_input"], timeout=C.NAV_TIMEOUT_MS)
        page.bring_to_front()
        time.sleep(1.0)

        if not check("logged in and the chat page is open",
                     page.locator(C.SEL["chat_input"]).count() == 1):
            browser.close()
            return 2

        # ---------- honesty guard: is this even the build under test? ----
        pre = page.evaluate(READ_GAUGE)
        if pre is None:
            print("")
            print("!! WRONG TARGET: the app answering %s has NO #context-gauge-row." % C.BASE_URL)
            print("!! The Context Governor lives in the SOURCE tree; a frozen")
            print("!! install is probably serving this port. Nothing was tested.")
            take_shot(OUT, "00_wrong_target.png")
            browser.close()
            return 3

        # ---------- 1. no data => no gauge --------------------------------
        check("BEFORE any request the row is present but INVISIBLE (0 px)",
              (not pre["visible"]) and pre["height"] == 0,
              "height=%s visible=%s" % (pre["height"], pre["visible"]))
        take_shot(OUT, "01_before_no_gauge.png")

        # ---------- toggles: Multi-Turn ON, everything else OFF -----------
        for key, want in C.TOGGLE_STATE.items():
            sel = C.SEL[key]
            if page.locator(sel).count() == 0:
                continue
            if page.is_checked(sel) != want:
                page.click(sel, force=True)
                time.sleep(0.15)
        check("Multi-Turn is ON (the gauge only measures the Multi-Turn loop)",
              page.is_checked(C.SEL["t_multi_turn"]))

        # ---------- 2. send a real request --------------------------------
        page.fill(C.SEL["chat_input"], PROMPT)
        take_shot(OUT, "02_prompt_typed.png")
        t0 = time.time()
        page.click(C.SEL["chat_submit"])
        print("\n  ... request sent, waiting for the first measurement ...")

        first, appeared = wait_for(page, lambda g: g and g["visible"], 150)
        check("the ring APPEARS on a real request", appeared,
              "after %.1fs -> %s" % (time.time() - t0, (first or {}).get("bytes")))
        if not appeared:
            take_shot(OUT, "03_ring_never_appeared.png")
            browser.close()
            return 1

        print("     first reading : %s | %s | zone=%s | %s"
              % (first["bytes"], first["tokens"], first["zone"], first["streams"]))
        take_shot(OUT, "03_ring_visible.png")

        # ---------- 3. the legend tells the truth -------------------------
        check("the BYTE figure carries no qualifier (it is measured)",
              "est" not in first["bytes"].lower(), first["bytes"])
        check("the TOKEN figure is labelled 'est.' (it is estimated)",
              "est." in first["tokens"].lower(), first["tokens"])
        check("the exact integer is on the hover title, with separators",
              bool(re.search(r"\d[\d,. ]*\s*bytes exactly", first["bytesTitle"])),
              first["bytesTitle"][:90])
        check("the zone word is shown, so colour is not the only signal",
              first["zoneWord"] in ("GREEN", "AMBER", "RED", "FLOOR"),
              first["zoneWord"])
        check("the three streams are broken out",
              "loop" in first["streams"].lower(), first["streams"])

        # ---------- 4. the Fig-21 layout trap -----------------------------
        send = page.evaluate(SEND_ON_SCREEN)
        check("the Send button is STILL on screen with the row shown",
              send.get("found") and send.get("onScreen"),
              "bottom=%s viewport=%s" % (send.get("bottom"), send.get("viewport")))

        # ---------- 5. does it MOVE? --------------------------------------
        print("  ... waiting for a SECOND, different measurement ...")

        def moved(g):
            if not g or not g["visible"]:
                return False
            return (g["bytes"] != first["bytes"]) or (g["points"] != first["points"])

        second, did_move = wait_for(page, moved, 150)
        check("the ring MOVES - a second, DIFFERENT measurement arrives", did_move,
              "%s -> %s" % (first["bytes"], (second or {}).get("bytes")))
        if did_move:
            print("     second reading: %s | %s | zone=%s | %s"
                  % (second["bytes"], second["tokens"], second["zone"], second["streams"]))
            take_shot(OUT, "04_ring_moved.png")
        else:
            take_shot(OUT, "04_ring_did_not_move.png")

        # ---------- stop the run so no further model calls are spent ------
        try:
            page.click(C.SEL["chat_submit"], timeout=3000)
            time.sleep(1.0)
            print("  ... run cancelled (no further model calls spent)")
        except Exception:                               # noqa: BLE001
            pass
        take_shot(OUT, "05_final_state.png")

        browser.close()

    # ---------- 6. the log really carries the lines -----------------------
    lines = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip() for ln in fh if "--- [CONTEXT]" in ln]
    check("tlamatini.log gained new --- [CONTEXT] lines",
          len(lines) > log_before, "%d before -> %d now" % (log_before, len(lines)))
    for ln in lines[-3:]:
        print("     " + ln[:160])

    # ---------- verdict ---------------------------------------------------
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    total = len(RESULTS)
    print("-" * 74)
    print("RESULT: %d/%d checks passed" % (passed, total))
    print("photos: %s   (taken by Shoter, whole desktop)" % OUT)

    rows = "".join(
        "<tr><td>%s</td><td style='color:%s;font-weight:700'>%s</td><td><code>%s</code></td></tr>"
        % (n, "#2e7d32" if ok else "#c62828", "PASS" if ok else "FAIL", d)
        for n, ok, d in RESULTS)
    with open(os.path.join(OUT, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8>"
                 "<title>Context gauge - visible proof</title>"
                 "<body style='font:14px system-ui;margin:24px'>"
                 "<h2>Context gauge &mdash; visible proof on a real request</h2>"
                 "<p>Tlamatini &middot; Angela L&oacute;pez Mendoza &middot; %s</p>"
                 "<p><b>%d/%d checks passed.</b> Photos by Shoter (whole desktop).</p>"
                 "<table border=1 cellpadding=6 cellspacing=0>%s</table></body>"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), passed, total, rows))

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
