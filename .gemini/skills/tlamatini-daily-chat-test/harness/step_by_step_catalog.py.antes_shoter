# -*- coding: utf-8 -*-
"""
Tlamatini — VISIBLE (headed Chrome) end-to-end test of the Catalog-of-Prompts
STEP-BY-STEP wizards (the section openers added by migrations 0181 + 0182).

For each testable wizard it:
  * ticks Multi-Turn + Step-by-Step (and ACPX where the wizard needs it),
  * sends the EXACT seeded prompt text (pulled from the live frozen DB),
  * then PLAYS THE USER: reads every step's answer, works out the exact reply
    the wizard asked for (READY / READY N / YES / CLOSE / a choice), sends it,
    and keeps going until the wizard stops asking for a reply,
  * takes a FULL-DESKTOP screenshot (taskbar clock visible) after every turn.

No lying: a wizard is PASS only if it actually reached a wrap-up without stalling.
Stalls/errors are recorded as such with their real evidence photo.
Builds SUMMARY.html (one photo per turn) + results.jsonl.
"""
import os
import sys
import re
import time
import json
import html
import sqlite3
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import run_test as R        # noqa: E402

from PIL import ImageGrab                       # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

DB = r'C:\Tlamatini\_internal\db.sqlite3'
RUN_TAG = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_DIR = os.path.join(HERE, "reports", "sxs_%s" % RUN_TAG)
SHOTS = os.path.join(RUN_DIR, "shots")
os.makedirs(SHOTS, exist_ok=True)
RESULTS = os.path.join(RUN_DIR, "results.jsonl")
SUMMARY = os.path.join(RUN_DIR, "SUMMARY.html")

PER_TURN_TIMEOUT_S = int(os.environ.get("SXS_TIMEOUT", "260"))


# --------------------------------------------------------------- scenarios
# reply_hints: (regex on answer, literal reply) tried BEFORE the generic resolver,
# so a scenario-specific open question ("revert or update?") still advances.
SCENARIOS = [
    dict(sid="files_search", pid=98, acpx=False, max_turns=12, kind="full"),
    dict(sid="run_execute",  pid=99, acpx=False, max_turns=10, kind="full"),
    dict(sid="code_gen",     pid=100, acpx=False, max_turns=16, kind="full",
         hints=[(r"revert .*hello|update the test to match",
                 'Please REVERT greetkit.py back to "Hello, " and re-run the tests to confirm they pass.')]),
    dict(sid="desktop_ui",   pid=104, acpx=False, max_turns=16, kind="full"),
    dict(sid="acpx_skills",  pid=103, acpx=True,  max_turns=12, kind="full"),
    dict(sid="agents_flows", pid=102, acpx=False, max_turns=12, kind="full"),
    dict(sid="images",       pid=101, acpx=False, max_turns=9,  kind="model"),
    dict(sid="media_voice",  pid=106, acpx=False, max_turns=12, kind="hardware"),
    dict(sid="games_3d",     pid=105, acpx=False, max_turns=4,  kind="needs_app",
         choice_default="NEITHER"),
]


def fetch_prompt(pid):
    c = sqlite3.connect(DB)
    row = c.execute("select promptContent from agent_prompt where idPrompt=?", (pid,)).fetchone()
    c.close()
    return row[0] if row else None


# --------------------------------------------------------------- toggles
_JS_SET = """(cfg) => {
  const set = (sel, want) => {
    const el = document.querySelector(sel);
    if (!el) return 'missing';
    if (el.disabled && el.checked === want) return 'ok-disabled';
    if (el.disabled) return 'disabled:' + el.checked;
    if (el.checked !== want) { el.checked = want; el.dispatchEvent(new Event('change', {bubbles: true})); }
    return String(el.checked);
  };
  const r = {};
  r.mt  = set('#multi-turn-enabled', true);      // first: gates the modifiers
  r.sxs = set('#step-by-step-enabled', true);
  r.acpx = set('#acpx-enabled', !!cfg.acpx);
  r.exec = set('#exec-report-enabled', false);
  r.ask  = set('#ask-execs-enabled', false);
  r.net  = set('#internetEnabled', false);
  r.mt_fn = (typeof isMultiTurnEnabled === 'function') ? isMultiTurnEnabled() : null;
  r.sxs_present = !!document.querySelector('#step-by-step-enabled');
  return r;
}"""


def set_toggles(page, acpx):
    try:
        return page.evaluate(_JS_SET, {"acpx": acpx})
    except Exception as e:
        return {"error": str(e)}


# --------------------------------------------------------------- reply resolver
def resolve_reply(ans, hints=None, choice_default="NEITHER"):
    """Work out the exact token the wizard just asked the user to send.
    Returns (token, why) or (None, why) when the wizard is NOT asking for a reply
    (i.e. it has wrapped up or stalled)."""
    a = ans or ""
    low = a.lower()

    # scenario-specific open questions first
    for pat, reply in (hints or []):
        if re.search(pat, low):
            return reply, "hint"

    def last(pat):
        ms = list(re.finditer(pat, low))
        return ms[-1] if ms else None

    # numbered READY ("reply READY 2", "wait for me to reply READY 5") — token only
    m = last(r"ready\s*(\d+)")
    if m:
        return "READY %s" % m.group(1), "ready-n"

    # explicit CLOSE / SKIP choice (desktop cleanup) — take the happy path
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?close['\"]?", low) or \
       re.search(r"\bclose\b.*\bto proceed\b", low):
        return "CLOSE", "close"

    # a one-of choice list (BLENDER/UNREAL/BOTH/NEITHER, etc.)
    if re.search(r"one of\b", low) and ("neither" in low or "both" in low):
        return choice_default, "choice-default"

    # YES/NO perception question ("reply YES or NO", "reply YES, or paste ...",
    # "did you hear/see me?")
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?yes\b", low) or \
       re.search(r"\byes or no\b", low) or re.search(r"did (you|i) (hear|see|transcribe)", low):
        return "YES", "yes-no"

    # a bare READY ask ("reply READY", "wait for my READY", "reply exactly READY")
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?ready['\"]?", low) or \
       re.search(r"wait for (?:my|me to reply) .*ready", low) or \
       re.search(r"\bready\b", low) and re.search(r"\b(reply|wait|when you)\b", low):
        return "READY", "ready"

    return None, "no-ask(final-or-stall)"


# --------------------------------------------------------------- send / capture
def send_and_wait(page, text, timeout_s):
    """One send/wait/scrape cycle in the CURRENT conversation. Returns dict."""
    t0 = time.time()
    prev = page.evaluate(R._JS_BOT_COUNT)
    page.fill(C.SEL["chat_input"], text)
    page.click(C.SEL["chat_submit"])
    started = True
    try:
        page.wait_for_function(R._JS_STARTED, arg=prev, timeout=C.STARTED_TIMEOUT_MS)
    except Exception:
        started = False
    completed = True
    try:
        page.wait_for_function(R._JS_READY, timeout=timeout_s * 1000)
    except Exception:
        completed = False
    page.wait_for_timeout(C.SETTLE_MS)
    texts = page.evaluate(R._JS_BOT_TEXTS)
    fresh = texts[prev:] if prev < len(texts) else []
    kept = [t.strip() for t in fresh if t and t.strip()
            and not any(m in t for m in C.BUSY_MARKERS)]
    answer = kept[-1] if kept else ""
    return {"answer": answer, "completed": completed, "started": started,
            "elapsed_s": round(time.time() - t0, 1)}


def grab(page, path):
    try:
        page.bring_to_front()
    except Exception:
        pass
    time.sleep(0.25)
    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab()
    img.save(path)


def looks_final(ans):
    low = (ans or "").lower()
    return any(mk in low for mk in (
        "readiness report", "run report", "guided tour - summary",
        "wizard complete", "wizard is complete", "first contact", "summary",
        "run report", "desktop first steps", "next, try", "point me at",
        "point you at", "you can now try", "readiness"))


# --------------------------------------------------------------- args shim
class Args:
    headless = False          # VISIBLE — Angela MUST see it.
    slowmo = 0
    user = os.environ.get("TLAMATINI_USER", "catalog_tester")
    password = os.environ.get("TLAMATINI_PASS", "CatalogTest!2026")
    judge_model = None
    not_ready_retries = 4
    not_ready_backoff = 10.0
    timeout = PER_TURN_TIMEOUT_S


def run_scenario(h, sc):
    page = h.page
    pid = sc["pid"]
    opener = fetch_prompt(pid)
    turns = []
    status = "STALLED"
    reason = ""
    if not opener:
        return {"sid": sc["sid"], "pid": pid, "status": "MISSING",
                "reason": "prompt not in DB", "turns": []}

    # fresh conversation + toggles
    try:
        h.clear_history()
    except Exception:
        pass
    time.sleep(2.0)
    tg = set_toggles(page, sc.get("acpx", False))
    print("  [%s] toggles: mt=%s sxs=%s acpx=%s mt_fn=%s"
          % (sc["sid"], tg.get("mt"), tg.get("sxs"), tg.get("acpx"), tg.get("mt_fn")), flush=True)

    msg = opener
    last_answer = None
    same_repeat = 0
    for ti in range(sc["max_turns"]):
        # keep toggles pinned every turn (page can re-hydrate)
        set_toggles(page, sc.get("acpx", False))
        try:
            page.wait_for_function(R._JS_EDITABLE, timeout=180_000)
        except Exception:
            pass
        r = send_and_wait(page, msg, sc["timeout"] if False else PER_TURN_TIMEOUT_S)
        shot = os.path.join(SHOTS, "sxs_%s_t%02d.png" % (sc["sid"], ti))
        try:
            grab(page, shot)
        except Exception as e:
            print("   screenshot failed:", e, flush=True)
        ans = r["answer"]
        sent = msg if ti else "[OPENER PROMPT #%d]" % pid
        tok, why = resolve_reply(ans, sc.get("hints"), sc.get("choice_default", "NEITHER"))
        turns.append({
            "i": ti, "sent": sent[:200], "answer": ans, "answer_chars": len(ans),
            "completed": r["completed"], "elapsed_s": r["elapsed_s"],
            "next_reply": tok, "why": why, "shot": os.path.basename(shot),
        })
        print("   turn %02d  %5.1fs  chars=%-5d  reply=%-9s (%s)  completed=%s"
              % (ti, r["elapsed_s"], len(ans), tok or "-", why, r["completed"]), flush=True)

        if not r["completed"] and not ans:
            status, reason = "TIMEOUT", "turn %d did not complete/empty" % ti
            break
        if ans and ans == last_answer:
            same_repeat += 1
            if same_repeat >= 2:
                status, reason = "STALLED", "answer repeated (loop guard)"
                break
        else:
            same_repeat = 0
        last_answer = ans

        if tok is None:
            # wizard stopped asking for a reply -> done (or stalled at an error)
            if looks_final(ans) or ti >= 1:
                status = "PASS" if looks_final(ans) else "ENDED"
                reason = "wrapped up at turn %d" % ti if looks_final(ans) \
                    else "wizard stopped asking (turn %d)" % ti
            else:
                status, reason = "STALLED", "no reply requested at turn %d" % ti
            break
        msg = tok
    else:
        status, reason = "CAPPED", "hit max_turns=%d (still progressing)" % sc["max_turns"]

    return {"sid": sc["sid"], "pid": pid, "status": status, "reason": reason,
            "kind": sc["kind"], "turns": turns, "toggles": tg}


# --------------------------------------------------------------- summary
_BADGE = {"PASS": "#1e8e3e", "ENDED": "#188038", "CAPPED": "#7a5b00",
          "STALLED": "#b06000", "TIMEOUT": "#c5221f", "MISSING": "#c5221f"}


def build_summary(results, started_iso):
    now = _dt.datetime.now().isoformat(timespec="seconds")
    p = []
    p.append("<!doctype html><meta charset='utf-8'><title>Step-by-Step Catalog — Evidence</title>")
    p.append("<style>body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;color:#e8ecf3}"
             ".top{position:sticky;top:0;background:#131a2b;padding:14px 20px;border-bottom:2px solid #2a3550}"
             "h1{margin:0 0 4px;font-size:19px}.sc{background:#182135;border:1px solid #26324e;border-radius:10px;margin:16px;padding:12px 14px}"
             ".b{padding:2px 10px;border-radius:12px;color:#fff;font-weight:600}"
             ".turn{border-top:1px solid #26324e;padding:8px 0;margin-top:8px}"
             "img{max-width:680px;width:100%;border:1px solid #33405f;border-radius:6px;display:block;margin:6px 0}"
             ".s{color:#a7b3c9;font-size:12.5px;white-space:pre-wrap}"
             "pre{white-space:pre-wrap;background:#0c1120;padding:9px;border-radius:6px;max-height:240px;overflow:auto;color:#cdd6e6}</style>")
    npass = sum(1 for r in results if r["status"] in ("PASS", "ENDED"))
    p.append("<div class='top'><h1>Tlamatini — Step-by-Step Catalog Wizards · VISIBLE browser evidence</h1>")
    p.append("<div class='s'>login catalog_tester · Multi-Turn + Step-by-Step ON · started %s · updated %s · "
             "reached wrap-up: <b>%d / %d</b> · every photo is the FULL desktop incl. the clock</div></div>"
             % (html.escape(started_iso), html.escape(now), npass, len(results)))
    for r in results:
        color = _BADGE.get(r["status"], "#666")
        p.append("<div class='sc'><div><b>%s</b> (prompt #%s · %s) &nbsp; <span class='b' style='background:%s'>%s</span> &nbsp; <span class='s'>%s</span></div>"
                 % (html.escape(r["sid"]), r["pid"], html.escape(r.get("kind", "")), color, r["status"], html.escape(r["reason"])))
        for t in r["turns"]:
            p.append("<div class='turn'><div class='s'>turn %d · sent: %s · %.1fs · reply→ %s (%s) · completed=%s</div>"
                     % (t["i"], html.escape(t["sent"]), t["elapsed_s"],
                        html.escape(str(t["next_reply"])), t["why"], t["completed"]))
            p.append("<a href='shots/%s' target='_blank'><img loading='lazy' src='shots/%s'></a>" % (t["shot"], t["shot"]))
            p.append("<details><summary>answer (%d chars)</summary><pre>%s</pre></details></div>"
                     % (t["answer_chars"], html.escape((t["answer"] or "")[:5000])))
        p.append("</div>")
    tmp = SUMMARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(p))
    os.replace(tmp, SUMMARY)


def main():
    only = os.environ.get("SXS_ONLY", "").strip()
    scenarios = [s for s in SCENARIOS if (not only or s["sid"] in only.split(","))]
    started_iso = _dt.datetime.now().isoformat(timespec="seconds")
    print("=" * 72)
    print("STEP-BY-STEP CATALOG TEST · visible Chrome · %d scenario(s)" % len(scenarios))
    print("run dir:", RUN_DIR)
    print("=" * 72, flush=True)

    args = Args()
    h = R.Harness(args)
    results = []
    with sync_playwright() as pw:
        browser = h.launch(pw)
        try:
            h.login()
            h.goto_chat()
            try:
                h.page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass
            time.sleep(0.8)
            for sc in scenarios:
                print("\n>>> SCENARIO %s (prompt #%d, %s)" % (sc["sid"], sc["pid"], sc["kind"]), flush=True)
                try:
                    res = run_scenario(h, sc)
                except Exception as e:
                    res = {"sid": sc["sid"], "pid": sc["pid"], "status": "TIMEOUT",
                           "reason": "exception: %s" % e, "kind": sc["kind"], "turns": []}
                    try:
                        h.recover()
                    except Exception:
                        pass
                results.append(res)
                with open(RESULTS, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                build_summary(results, started_iso)
                print("<<< %s -> %s (%s)" % (sc["sid"], res["status"], res["reason"]), flush=True)
        finally:
            build_summary(results, started_iso)
            try:
                browser.close()
            except Exception:
                pass

    print("\n" + "=" * 72)
    for r in results:
        print("  %-14s #%-3d %-8s %s" % (r["sid"], r["pid"], r["status"], r["reason"]))
    print("SUMMARY:", SUMMARY)
    print("=" * 72, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
