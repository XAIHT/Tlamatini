#!/usr/bin/env python3
# ===================================================================
#   T L A M A T I N I  -  "one who knows"
#   Created by  Angela Lopez Mendoza  -  @angelahack1
#   Author banner - do not remove (Angela's name is kept in every build)
# ===================================================================
"""
Visible (HEADED) Playwright test for the VOICE feature (Config -> Voice).

Drives real Chrome on Angela's desktop against the running frozen Tlamatini,
logs in through the real GUI, and verifies:

  B1  Config dropdown has a "Voice" item (#config-voice)
  B2  clicking it opens the Voice dialog (overlay visible)
  B3  exactly 3 mode radios, one exclusive group (speak / notify / silent)
  B4  the voice list is FEMALE-ONLY (no male voice names offered)
  B5  mode 'Notify answer complete' -> on a completed answer she speaks
      exactly "I have completed your request!"
  B6  mode 'Automatically speak answers' -> she speaks the answer PROSE only
      (the .automated-message-body text, NOT the timestamp / Copy / Create-Flow)
  B7  mode 'Silent' -> nothing is spoken on a completed answer
  B8  the input footer is taller now (min-height ~30%)

The 3 modes are exercised DETERMINISTICALLY by injecting a fake answer message
and toggling the chat input disabled->enabled (the same "answer complete" signal
the feature listens on) - so no dependency on the cloud LLM. HEADED real Chrome
only; full-desktop screenshots per Angela's visible-tests rule.
"""
import json
import os
import sys
import time
from datetime import datetime


def _load_creds():
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

from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402,F401
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
OUT_DIR = os.path.join(_REPO_ROOT, "Temp", "voice_test_" + STAMP)
RESULTS = []
MALE_RE = "david|mark|guy|ryan|george|james|william|brian|eric|roger|paul|richard|zac|leo|christopher|thomas|hans|stefan|liam|oliver| male"


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

_SIMULATE_JS = r"""
(txt) => {
  const log = document.getElementById('chat-log');
  const m = document.createElement('div'); m.className = 'message bot-message';
  const mc = document.createElement('div'); mc.className = 'message-content';
  const un = document.createElement('div'); un.className = 'username';
  un.textContent = 'Tlamatini (2026/07/16 00:00:00.000) Copy Create Flow';
  const am = document.createElement('div'); am.className = 'automated-message';
  const body = document.createElement('div'); body.className = 'automated-message-body';
  body.textContent = txt;
  am.appendChild(body); mc.appendChild(un); mc.appendChild(am); m.appendChild(mc);
  log.appendChild(m);
  const inp = document.getElementById('chat-message-input');
  inp.disabled = true;
  setTimeout(function(){ inp.disabled = false; }, 60);
}
"""


def main():
    if not USER or not PASS:
        print("ERROR: no credentials (TLAMATINI_USER/TLAMATINI_PASS or .creds.env)", file=sys.stderr)
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=HEADLESS, channel="chrome",
                                        args=["--start-maximized"], slow_mo=50)
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(headless=HEADLESS, args=["--start-maximized"], slow_mo=50)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        _login(page)
        time.sleep(1.5)
        page.evaluate(_SPY_JS)

        # B1 - Config has a Voice item
        item = page.query_selector("#config-voice")
        check("B1 Config dropdown has a Voice item", bool(item),
              "text=" + (item.inner_text() if item else "<missing>"))

        # B2 - open the dialog
        opened = False
        try:
            page.evaluate("() => window.OpenVoiceDialog && window.OpenVoiceDialog()")
            page.wait_for_selector("#tlm-voice-overlay", state="visible", timeout=4000)
            opened = page.eval_on_selector("#tlm-voice-overlay", "el => getComputedStyle(el).display !== 'none'")
        except Exception as exc:  # noqa: BLE001
            opened = False
            check("B2 clicking Voice opens the dialog", False, "err=" + repr(exc))
        if opened:
            check("B2 clicking Voice opens the dialog", True)
        time.sleep(1.2)  # let async voices load + populate
        shot("01_voice_dialog.png")

        # B3 - three exclusive mode radios
        radios = page.evaluate(
            "() => Array.from(document.querySelectorAll('input[name=\"tlm-voice-mode\"]'))"
            ".map(r => r.value)")
        names_same = page.evaluate(
            "() => { const rs = Array.from(document.querySelectorAll('input[type=radio][name=\"tlm-voice-mode\"]'));"
            " return rs.length>0 && rs.every(r => r.name==='tlm-voice-mode'); }")
        want = {"speak", "notify", "silent"}
        check("B3 three exclusive mode radios (speak/notify/silent)",
              set(radios) == want and len(radios) == 3 and names_same,
              "values=" + str(radios) + " sameGroup=" + str(names_same))

        # B4 - female-only voice list
        opts = page.evaluate(
            "() => Array.from(document.querySelectorAll('#tlm-voice-select option')).map(o => o.textContent)")
        import re as _re
        male_hits = [o for o in opts if _re.search(MALE_RE, o, _re.I)]
        check("B4 voice list is FEMALE-ONLY (no male voices)", len(male_hits) == 0,
              "options=%d male_hits=%s" % (len(opts), male_hits))

        # exclusivity proof: check 'silent', then only one is checked
        page.check("input[name=\"tlm-voice-mode\"][value=\"silent\"]")
        checked = page.evaluate(
            "() => Array.from(document.querySelectorAll('input[name=\"tlm-voice-mode\"]:checked')).map(r=>r.value)")
        check("B3b radios are mutually exclusive (only one checked)", checked == ["silent"], "checked=" + str(checked))

        # ---- B5: notify mode ----
        page.check("input[name=\"tlm-voice-mode\"][value=\"notify\"]")
        n0 = len(page.evaluate("() => window.__spoken || []"))
        page.evaluate(_SIMULATE_JS, "ANSWER ALPHA one two three")
        time.sleep(1.4)
        spoken = page.evaluate("() => window.__spoken || []")
        b5 = len(spoken) > n0 and (spoken[-1] or "").strip() == "I have completed your request!"
        check("B5 Notify mode speaks the completion phrase", b5, "last=" + repr(spoken[-1] if spoken else None))

        # ---- B6: speak mode -> answer prose only ----
        page.check("input[name=\"tlm-voice-mode\"][value=\"speak\"]")
        n1 = len(page.evaluate("() => window.__spoken || []"))
        page.evaluate(_SIMULATE_JS, "This is the answer body two")
        time.sleep(1.4)
        spoken = page.evaluate("() => window.__spoken || []")
        last = (spoken[-1] or "").strip() if spoken else ""
        b6 = len(spoken) > n1 and last == "This is the answer body two" and ("Copy" not in last) and ("2026/07/16" not in last)
        check("B6 Speak mode speaks the answer prose only (no timestamp/buttons)", b6, "last=" + repr(last))

        # ---- B7: silent mode -> nothing ----
        page.check("input[name=\"tlm-voice-mode\"][value=\"silent\"]")
        n2 = len(page.evaluate("() => window.__spoken || []"))
        page.evaluate(_SIMULATE_JS, "This must NOT be spoken")
        time.sleep(1.4)
        spoken = page.evaluate("() => window.__spoken || []")
        check("B7 Silent mode speaks nothing", len(spoken) == n2, "before=%d after=%d" % (n2, len(spoken)))

        # ---- B8: footer taller (min-height ~30%) ----
        dims = page.evaluate(
            "() => { const f=document.getElementById('tools-chat-form-container');"
            " const s=document.getElementById('subchat-container');"
            " return {form: f?f.getBoundingClientRect().height:0, sub: s?s.getBoundingClientRect().height:0}; }")
        ratio = (dims["form"] / dims["sub"]) if dims["sub"] else 0
        check("B8 footer is taller (min-height ~30%)", ratio >= 0.25,
              "form=%dpx sub=%dpx ratio=%.2f" % (round(dims["form"]), round(dims["sub"]), ratio))

        # ---- B9: REAL LLM answer end-to-end (the honest test, no simulation) ----
        page.check("input[name=\"tlm-voice-mode\"][value=\"notify\"]")
        page.evaluate("() => { const o=document.getElementById('tlm-voice-overlay'); if(o) o.style.display='none'; }")
        try:
            mt = page.query_selector("#multi-turn-enabled")
            if mt and mt.is_checked():
                mt.click()
        except Exception:  # noqa: BLE001
            pass
        nb = len(page.evaluate("() => window.__spoken || []"))
        bb = page.eval_on_selector_all("#chat-log .message.bot-message", "els => els.length")
        page.fill("#chat-message-input", "Reply with exactly: hello there. End with END-RESPONSE.")
        page.click("#chat-message-submit")
        real_ok = False
        rdl = time.time() + 90
        while time.time() < rdl:
            spk = page.evaluate("() => window.__spoken || []")
            bots = page.eval_on_selector_all("#chat-log .message.bot-message", "els => els.length")
            if bots > bb and any((str(s).strip() == "I have completed your request!") for s in spk[nb:]):
                real_ok = True
                break
            time.sleep(1.0)
        check("B9 REAL LLM answer triggers auto-speak (notify)", real_ok,
              "bots %d->%d spoken_added=%d" % (bb, page.eval_on_selector_all("#chat-log .message.bot-message", "els => els.length"), len(page.evaluate("() => window.__spoken || []")) - nb))
        shot("03_real_answer.png")

        # ---- B10: REAL answer in SPEAK mode -> she reads the PROSE aloud ----
        page.evaluate("() => { const o=document.getElementById('tlm-voice-overlay'); if(o){o.style.display='flex';} }")
        page.check("input[name=\"tlm-voice-mode\"][value=\"speak\"]")
        page.evaluate("() => { const o=document.getElementById('tlm-voice-overlay'); if(o){o.style.display='none';} }")
        nb2 = len(page.evaluate("() => window.__spoken || []"))
        bb2 = page.eval_on_selector_all("#chat-log .message.bot-message", "els => els.length")
        page.fill("#chat-message-input",
                  "In one short sentence, what color is the sky on a clear day? End with END-RESPONSE.")
        page.click("#chat-message-submit")
        _read_ans = ("() => { const ms=document.querySelectorAll('#chat-log .message.bot-message');"
                     " const m=ms[ms.length-1]; if(!m) return '';"
                     " const el=m.querySelector('.automated-message-body')||m.querySelector('.automated-message');"
                     " const c=(el||m).cloneNode(true);"
                     " c.querySelectorAll('.automated-message-execreport,button,.username').forEach(x=>x.remove());"
                     " return (c.innerText||c.textContent||'').trim(); }")
        speak_ok = False
        detail = ""
        rdl2 = time.time() + 90
        while time.time() < rdl2:
            bots = page.eval_on_selector_all("#chat-log .message.bot-message", "els => els.length")
            if bots > bb2:
                time.sleep(2.5)  # let the answer render + debounce + speakLong fire
                ans = " ".join(page.evaluate(_read_ans).split())
                spk = page.evaluate("() => window.__spoken || []")
                joined = " ".join(" ".join(str(s).split()) for s in spk[nb2:]).lower().strip()
                key = ans[:25].lower().strip()
                speak_ok = bool(key) and (key in joined) and ("i have completed your request" not in joined)
                detail = "answer=%r spoke=%r" % (ans[:70], joined[:90])
                break
            time.sleep(1.0)
        check("B10 REAL answer in SPEAK mode reads the ACTUAL answer aloud", speak_ok, detail)
        shot("04_speak_answer.png")

        shot("02_final.png")
        context.close()
        browser.close()

    passed = sum(1 for r in RESULTS if r["passed"])
    total = len(RESULTS)
    all_green = (passed == total) and total > 0
    report_md = os.path.join(OUT_DIR, "REPORT.md")
    with open(report_md, "w", encoding="utf-8") as fh:
        fh.write("# Voice feature visible E2E - " + datetime.now().isoformat(timespec="seconds") + "\n\n")
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
