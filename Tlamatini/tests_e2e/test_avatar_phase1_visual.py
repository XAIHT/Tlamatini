#!/usr/bin/env python3
# ===================================================================
#   T L A M A T I N I  -  "one who knows"
#   Created by  Angela Lopez Mendoza  -  @angelahack1
#   Author banner - do not remove (Angela's name is kept in every build)
# ===================================================================
"""
Visible (HEADED) Playwright test for the chat AVATAR (Phase 1).

Drives real Chrome on Angela's desktop against the running frozen Tlamatini
(:8000), logs in through the REAL GUI, and verifies the avatar panel that
lives in the input footer next to Send:

  A0  the page exposes the real login username (#user_username)
  A1  the avatar panel (#tlm-avatar-dock) exists and is VISIBLE
  A2  it is a RECTANGLE, not a circle (border-radius small, not 50%)
  A3  it has a SOLID (opaque) background - not transparent
  A4  the portrait uses object-fit:contain - no deformation
  A5  it does NOT overlap / cover the Send button (Send stays usable)
  A6  it is fully inside the viewport - never cut off
  A7  the portrait image actually loaded (naturalWidth > 0)
  A8  clicking it shows a bubble greeting using the REAL login username
      (read live from #user_username), not a hardcoded name
  A9  clicking it fires speechSynthesis.speak() with that greeting (voice)
  A10 when the app is "working" (Send->Cancel / input disabled) the avatar
      enters the working state and speaks a WORKING phrase, not an idle one
  A11 served HTML: the avatar script reads #user_username and contains NO
      hardcoded "Hi Angela," greeting

Every milestone is a FULL-DESKTOP screenshot (whole screen incl. the taskbar
clock) per Angela's visible-tests rule. HEADED real Chrome only - never
headless. Run (server already up):

    python Tlamatini/tests_e2e/test_avatar_phase1_visual.py
"""
import json
import os
import sys
import time
from datetime import datetime


def _load_creds():
    """Load login creds from .creds.env so the password never leaves the file."""
    cands = [
        os.environ.get("TLAMATINI_CREDS"),
        r"C:\Development\Tlamatini\.claude\skills\tlamatini-daily-chat-test\harness\.creds.env",
    ]
    for p in cands:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return p
    return None


_CREDS_SRC = _load_creds()

from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

try:
    from PIL import ImageGrab  # noqa: E402
except Exception:  # noqa: BLE001
    ImageGrab = None

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("TLAMATINI_USER", "")
PASS = os.environ.get("TLAMATINI_PASS", "")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = os.path.join(_REPO_ROOT, "Temp", "avatar_test_" + STAMP)
RESULTS = []


def shot(name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    if ImageGrab is not None:
        try:
            ImageGrab.grab(all_screens=True).save(path)
            return path
        except Exception:  # noqa: BLE001
            return None
    return None


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": str(detail)[:400]})
    print(("PASS" if passed else "FAIL") + "  " + name + "  " + str(detail))


def _login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    if page.query_selector("#id_username"):
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("button[type=submit]")
        page.wait_for_load_state("domcontentloaded")
    page.goto(BASE_URL + "/agent/agent/", wait_until="domcontentloaded")
    page.wait_for_selector("#chat-message-input", timeout=45000)


_GEOM_JS = r"""
() => {
  const d = document.getElementById('tlm-avatar-dock');
  const s = document.getElementById('chat-message-submit');
  const img = d ? d.querySelector('img') : null;
  if (!d || !s) return {ok:false};
  const dc = getComputedStyle(d), ic = img ? getComputedStyle(img) : {};
  const a = d.getBoundingClientRect(), sb = s.getBoundingClientRect();
  const minside = Math.min(a.width, a.height);
  const br = parseFloat(dc.borderTopLeftRadius) || 0;
  const overlap = !(a.right <= sb.left || a.left >= sb.right || a.bottom <= sb.top || a.top >= sb.bottom);
  return {
    ok:true, radiusPx: br, minside: minside, bg: dc.backgroundColor,
    objectFit: ic.objectFit || '',
    a:{x:a.left,y:a.top,w:a.width,h:a.height,right:a.right,bottom:a.bottom},
    s:{top:sb.top, w:sb.width, h:sb.height},
    overlap: overlap, sendVisible: sb.width>1 && sb.height>1,
    imgLoaded: !!(img && img.complete && img.naturalWidth>0),
    vw: window.innerWidth, vh: window.innerHeight
  };
}
"""

_SPY_JS = r"""
() => {
  window.__spoken = [];
  try {
    const ss = window.speechSynthesis;
    if (ss && !ss.__spied) {
      const orig = ss.speak.bind(ss);
      ss.speak = function(u){ try{ window.__spoken.push(u && u.text); }catch(e){} return orig(u); };
      ss.__spied = true;
    }
  } catch(e){}
}
"""

_WORK_ON_JS = r"""
() => { const s=document.getElementById('chat-message-submit'); const i=document.getElementById('chat-message-input');
        window.__origSend=s.textContent; s.textContent='Cancel'; i.disabled=true; }
"""

_WORK_OFF_JS = r"""
() => { const s=document.getElementById('chat-message-submit'); const i=document.getElementById('chat-message-input');
        s.textContent=(window.__origSend||'Send'); i.disabled=false; }
"""


def main():
    if not USER or not PASS:
        print("ERROR: no credentials (TLAMATINI_USER/TLAMATINI_PASS or .creds.env)", file=sys.stderr)
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=HEADLESS, channel="chrome",
                                        args=["--start-maximized"], slow_mo=60)
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(headless=HEADLESS, args=["--start-maximized"], slow_mo=60)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        _login(page)
        time.sleep(1.5)
        shot("01_after_login.png")

        username = page.evaluate(
            "() => { try { return JSON.parse(document.getElementById('user_username').textContent); }"
            " catch(e){ return ''; } }")
        exp_name = (username[:1].upper() + username[1:]) if username else ""
        check("A0 login username exposed (#user_username)", bool(username),
              "username=" + repr(username) + " -> greeting name=" + repr(exp_name))

        dock = page.query_selector("#tlm-avatar-dock")
        visible = bool(dock) and page.is_visible("#tlm-avatar-dock")
        check("A1 avatar panel exists and is visible", visible)

        info = page.evaluate(_GEOM_JS)
        if info.get("ok"):
            is_rect = info["radiusPx"] < max(24, info["minside"] * 0.25)
            check("A2 rectangle, not a circle", is_rect,
                  "borderRadius=%spx minSide=%spx" % (info["radiusPx"], round(info["minside"])))
            bg = info["bg"].replace(" ", "")
            solid = bg.startswith("rgb(") or (bg.startswith("rgba(") and not bg.endswith(",0)"))
            check("A3 solid (opaque) background", solid, "background-color=" + info["bg"])
            check("A4 object-fit: contain (no deformation)", info["objectFit"] == "contain",
                  "object-fit=" + str(info["objectFit"]))
            above = info["a"]["bottom"] <= info["s"]["top"] + 1
            a5 = (not info["overlap"]) and info["sendVisible"] and above
            check("A5 does NOT cover the Send button", a5,
                  "overlap=%s sendVisible=%s avatarBottom=%s sendTop=%s"
                  % (info["overlap"], info["sendVisible"], round(info["a"]["bottom"]), round(info["s"]["top"])))
            a = info["a"]
            inv = a["y"] >= -2 and a["bottom"] <= info["vh"] + 2 and a["x"] >= -2 and a["right"] <= info["vw"] + 2
            check("A6 fully inside the viewport (not cut off)", inv,
                  "rect=(%s,%s,%sx%s) viewport=%sx%s"
                  % (round(a["x"]), round(a["y"]), round(a["w"]), round(a["h"]), info["vw"], info["vh"]))
            check("A7 portrait image loaded", info["imgLoaded"], "complete+naturalWidth>0=" + str(info["imgLoaded"]))
            check("A12 usable size (>= 48px tall, not a sliver)", info["a"]["h"] >= 48,
                  "height=%spx" % round(info["a"]["h"]))
        else:
            for nm in ("A2 rectangle, not a circle", "A3 solid (opaque) background",
                       "A4 object-fit: contain (no deformation)", "A5 does NOT cover the Send button",
                       "A6 fully inside the viewport (not cut off)", "A7 portrait image loaded",
                       "A12 usable size (>= 48px tall, not a sliver)"):
                check(nm, False, "avatar or Send button missing")

        page.evaluate(_SPY_JS)

        idle_texts = []
        name_hit = None
        if visible:
            for _ in range(12):
                try:
                    page.click("#tlm-avatar-dock")
                    page.wait_for_selector("#tlm-avatar-bubble.tlm-show", timeout=3000)
                    t = (page.eval_on_selector("#tlm-avatar-bubble", "el => el.textContent") or "").strip()
                    if t and t not in idle_texts:
                        idle_texts.append(t)
                    if exp_name and len(exp_name) >= 2 and exp_name in t:
                        name_hit = t
                        break
                    time.sleep(0.35)
                except PWTimeout:
                    time.sleep(0.2)
            shot("02_idle_bubble.png")
            check("A8 greeting uses the REAL login name", bool(name_hit),
                  "expected " + repr(exp_name) + " in a greeting; saw: " + str(name_hit or idle_texts))
            spoken = page.evaluate("() => window.__spoken || []")
            spoken_ok = bool(spoken) and any((str(s).strip() in idle_texts) for s in spoken)
            check("A9 speechSynthesis.speak fired with the greeting (voice)", spoken_ok,
                  "spoken[-3:]=" + str(spoken[-3:] if spoken else []))
        else:
            check("A8 greeting uses the REAL login name", False, "avatar not visible")
            check("A9 speechSynthesis.speak fired with the greeting (voice)", False, "avatar not visible")

        working_ok = False
        wdetail = ""
        if visible:
            page.evaluate(_WORK_ON_JS)
            time.sleep(0.5)
            has_working = page.eval_on_selector("#tlm-avatar-dock", "el => el.classList.contains('tlm-working')")
            wtext = ""
            try:
                page.click("#tlm-avatar-dock")
                page.wait_for_selector("#tlm-avatar-bubble.tlm-show", timeout=3000)
                wtext = (page.eval_on_selector("#tlm-avatar-bubble", "el => el.textContent") or "").strip()
            except PWTimeout:
                pass
            shot("03_working_bubble.png")
            idle_set = {"Ready when you are.", "All set - ask me anything.", "I'm listening."}
            if exp_name:
                idle_set.add("Hi %s, I'm here whenever you need me." % exp_name)
                idle_set.add("Standing by, %s." % exp_name)
            working_ok = bool(has_working) and bool(wtext) and (wtext not in idle_set)
            wdetail = "tlm-working=%s phrase=%s" % (has_working, repr(wtext))
            page.evaluate(_WORK_OFF_JS)
        check("A10 reacts to 'working' state (working phrase + tlm-working class)", working_ok, wdetail)

        html = page.content()
        reads_user = ("getElementById('user_username')" in html) or ('getElementById("user_username")' in html)
        concat = ('"Hi "+NAME+"' in html)
        hardcoded = ("Hi Angela, I'm here whenever you need me." in html)
        check("A11 greeting is DYNAMIC in served HTML (reads login, not hardcoded)",
              reads_user and concat and (not hardcoded),
              "reads_user=%s concat=%s hardcoded=%s" % (reads_user, concat, hardcoded))

        shot("04_final.png")
        try:
            page.locator("#tools-chat-form-container").screenshot(
                path=os.path.join(OUT_DIR, "05_avatar_closeup.png"))
        except Exception:  # noqa: BLE001
            pass
        context.close()
        browser.close()

    passed = sum(1 for r in RESULTS if r["passed"])
    total = len(RESULTS)
    all_green = (passed == total) and total > 0
    report_md = os.path.join(OUT_DIR, "REPORT.md")
    with open(report_md, "w", encoding="utf-8") as fh:
        fh.write("# Avatar Phase-1 visible E2E - " + datetime.now().isoformat(timespec="seconds") + "\n\n")
        fh.write("Base: %s | user: %s | creds: %s\n\n" % (BASE_URL, USER, _CREDS_SRC))
        fh.write("## RESULT: %d/%d - %s\n\n" % (passed, total, "ALL GREEN" if all_green else "FAILURES"))
        fh.write("| # | check | result | detail |\n|---|---|---|---|\n")
        for i, r in enumerate(RESULTS, 1):
            fh.write("| %d | %s | %s | %s |\n" % (i, r["name"], "PASS" if r["passed"] else "FAIL", r["detail"]))
    with open(os.path.join(OUT_DIR, "DONE.json"), "w", encoding="utf-8") as fh:
        json.dump({"passed": all_green, "score": "%d/%d" % (passed, total),
                   "report": report_md, "out_dir": OUT_DIR, "results": RESULTS}, fh, indent=2)
    print("\nRESULT %d/%d - %s" % (passed, total, "ALL GREEN" if all_green else "FAILURES"))
    print("Report: " + report_md)
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
