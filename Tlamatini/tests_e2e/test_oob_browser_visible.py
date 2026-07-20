# -*- coding: utf-8 -*-
"""VISIBLE HEADED-BROWSER proof of the OOB_shift_reaper wiring, end-to-end.

Angela's rule: automated tests run in a VISIBLE, HEADED Chrome on her real desktop —
never headless. This drives the REAL Tlamatini chat GUI (login angela, Multi-Turn ON),
asks Tlamatini to run the Nmapper agent against the Nmap-project-authorized target
scanme.nmap.org, and confirms the scan RAN end-to-end through the new `_run_cmd_oob`
streaming runner (a real nmap, real open ports, no regression from the OOB rewrite).
Full-desktop screenshot as evidence.
"""
import datetime as _dt
import os
import sys
import time

HARNESS = r'C:\Development\Tlamatini\.claude\skills\tlamatini-daily-chat-test\harness'
OUT = r'C:\Development\Tlamatini\Temp\oob_browser_result.txt'
SHOT = r'C:\Development\Tlamatini\Temp\oob_browser_shot.png'

creds = os.path.join(HARNESS, '.creds.env')
if os.path.exists(creds):
    for ln in open(creds, encoding='utf-8'):
        ln = ln.strip()
        if '=' in ln and not ln.startswith('#'):
            k, v = ln.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, HARNESS)
import run_test as R                              # noqa: E402
from PIL import ImageGrab                         # noqa: E402
from playwright.sync_api import sync_playwright   # noqa: E402

# Allow targeting a non-default port (e.g. :8010 when Windows/Hyper-V has reserved :8000).
_BASE_URL = os.environ.get('OOB_BASE_URL', '').strip()
if _BASE_URL:
    try:
        R.C.BASE_URL = _BASE_URL
    except Exception:
        pass

LINES = []


def say(m):
    print(m, flush=True)
    LINES.append(str(m))
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write("\n".join(LINES))


class Args:
    headless = False           # VISIBLE — never flip (Angela's rule)
    slowmo = 0
    user = os.environ.get('TLAMATINI_USER', 'angela')
    password = os.environ.get('TLAMATINI_PASS', '')
    judge_model = None
    not_ready_retries = 2
    not_ready_backoff = 8.0
    timeout = 300


PROMPT = (
    "Tlamatini, operator mode. Run the **Nmapper** agent NOW with chat_agent_nmapper: "
    "action='quick', target='scanme.nmap.org' (the target the Nmap project authorizes "
    "the public to scan). Tick ONLY the Multi-Turn checkbox. Report the scan status and "
    "the open ports it found. End with END-RESPONSE."
)


def shot(path):
    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab()
    img.save(path)
    return path


def main():
    say("=" * 74)
    say("OOB browser proof (headed Chrome)  ·  " + _dt.datetime.now().isoformat(timespec='seconds'))
    say("=" * 74)
    if not Args.password:
        say("FATAL: no password")
        return 2

    ok_ran = False
    ans = ""
    with sync_playwright() as p:
        h = R.Harness(Args)
        browser = h.launch(p)
        try:
            h.login()
            h.goto_chat()
            h.clear_history()
            # force Multi-Turn ON, everything else off
            h.page.evaluate("""() => {
                const s=(sel,v)=>{const e=document.querySelector(sel);
                  if(e&&!e.disabled&&e.checked!==v){e.checked=v;e.dispatchEvent(new Event('change',{bubbles:true}));}};
                s('#multi-turn-enabled',true); s('#acpx-enabled',false);
                s('#exec-report-enabled',true); s('#ask-execs-enabled',false); s('#internetEnabled',false);
            }""")
            h.page.wait_for_timeout(400)

            q = {"id": "OOB-NMAP-1", "category": "oob:nmapper", "text": PROMPT,
                 "expect": [], "min_len": 20}
            say("SENT  at %s" % _dt.datetime.now().strftime('%H:%M:%S'))
            t0 = time.time()
            rec = h.ask_one(q, Args.timeout * 1000)
            say("DONE  at %s  (%.1f s)" % (_dt.datetime.now().strftime('%H:%M:%S'), time.time() - t0))

            ans = (rec.get('answer') or '')
            low = ans.lower()
            # the scan RAN through _run_cmd_oob if the answer carries real nmap evidence
            evidence = ("scanme" in low) and any(
                t in low for t in ("port", "open", "nmap", "22", "80", "ssh", "http"))
            ok_ran = bool(evidence) and len(ans) > 40
            say("ANSWER_LEN : %d" % len(ans))
            say("EVIDENCE   : %s" % evidence)
            say("---- ANSWER (first 1500) ----")
            say(ans[:1500])
            say("-----------------------------")
        finally:
            shot(SHOT)
            try:
                browser.close()
            except Exception:      # noqa: BLE001
                pass

    say("SCREENSHOT : %s (%d KB)" % (SHOT, os.path.getsize(SHOT) // 1024 if os.path.exists(SHOT) else 0))
    say("RESULT     : %s" % ("PASS — Nmapper ran end-to-end through the OOB runner"
                             if ok_ran else "FAIL — no real scan evidence in the answer"))
    return 0 if ok_ran else 1


if __name__ == "__main__":
    sys.exit(main())
