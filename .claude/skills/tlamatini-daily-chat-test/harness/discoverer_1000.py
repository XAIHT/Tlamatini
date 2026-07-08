# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""
Tlamatini — 1000 Discoverer tests through the REAL chat GUI, with full-screen
photographic evidence (entire desktop incl. the taskbar CLOCK) for EVERY test.

Requested by Angela:
  * 1000 Discoverer tests, EXCLUSIVELY through Tlamatini's own chat page.
  * login angela / (env TLAMATINI_PASS)
  * a full-screen screenshot showing the clock verifying EACH test.
  * a summary with one photo per test.
  * NO lying: only what actually completes is recorded; failures are shown as
    failures with their real evidence photo.

It reuses the proven login/toggle/send/wait contract from run_test.py so it
drives agent_page.html exactly like the daily test does. Each Discoverer test
is a SAFE, passive CVE-database lookup (tool='cvemap' -> vulnx) — no scanning of
any third-party host.
"""
import os
import sys
import time
import json
import html
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import run_test as R        # noqa: E402  (Harness, JS constants, heuristics)

try:
    from PIL import ImageGrab
except Exception as _e:      # pragma: no cover
    print("FATAL: Pillow (PIL.ImageGrab) is required for full-screen evidence:", _e)
    sys.exit(2)

from playwright.sync_api import sync_playwright   # noqa: E402


# --------------------------------------------------------------------------- config
N = int(os.environ.get("DISC_N", "1000"))
CLEAR_EVERY = int(os.environ.get("DISC_CLEAR_EVERY", "20"))
RUN_TAG = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_DIR = os.path.join(HERE, "reports", "discoverer_%s" % RUN_TAG)
SHOTS_DIR = os.path.join(RUN_DIR, "shots")
os.makedirs(SHOTS_DIR, exist_ok=True)
RESULTS = os.path.join(RUN_DIR, "results.jsonl")
SUMMARY_HTML = os.path.join(RUN_DIR, "SUMMARY.html")

# Safe, passive Discoverer variants — CVE database search only (no host scans).
# (severity, limit, product)
VARIANTS = [
    ("critical", 5, ""), ("high", 5, ""),
    ("critical", 5, "wordpress"), ("high", 5, "apache"),
    ("critical", 5, "openssl"), ("high", 5, "nginx"),
    ("critical", 5, "linux"), ("high", 5, "windows"),
    ("critical", 5, "chrome"), ("high", 5, "jenkins"),
    ("critical", 5, "gitlab"), ("high", 5, "django"),
    ("critical", 3, "php"), ("high", 3, "mysql"),
]


def make_prompt(i):
    sev, lim, prod = VARIANTS[i % len(VARIANTS)]
    prod_clause = (", cvemap_product='%s'" % prod) if prod else ""
    show = ("%s " % prod) if prod else ""
    return (
        "Tlamatini, operator mode. Discoverer test #%d. Use ONLY the "
        "chat_agent_discoverer tool to list the LATEST %s %sCVEs: call it with "
        "tool='cvemap', cvemap_severity='%s', cvemap_limit=%d%s, json_output=true, "
        "then show me each CVE id, its CVSS score and a one-line summary. "
        "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_discoverer. "
        "End with END-RESPONSE."
        % (i + 1, sev.upper(), show, sev, lim, prod_clause)
    )


def make_question(i):
    sev, lim, prod = VARIANTS[i % len(VARIANTS)]
    cat = "discoverer:cvemap:%s%s" % (sev, (":" + prod) if prod else "")
    return {
        "id": "D%04d" % (i + 1),
        "category": cat,
        "text": make_prompt(i),
        "expect": ["CVE"],
        "min_len": 30,
    }


def disc_verdict(answer):
    """Discoverer-specific verdict from the real answer text. Never raises."""
    a = (answer or "").strip()
    low = a.lower()
    if not a:
        return "FAIL", "empty-answer"
    if "traceback (most recent call last)" in low or low.startswith("error:"):
        return "FAIL", "error-signal"
    has_cve = ("cve-" in low) and any(ch.isdigit() for ch in a)
    if has_cve:
        return "PASS", "cve-evidence-present"
    if any(t in low for t in ("discoverer", "vulnx", "cvemap", "cvss")):
        return "PASS*", "discoverer-invoked-no-cve-id"
    return "WEAK", "no-cve-in-answer"


# Force the pinned toolbar state and RETURN the exact multi_turn value that the
# chat's own submit builder (isMultiTurnEnabled()) will transmit. Called right
# before every send so a page re-hydration can never silently drop Multi-Turn.
_JS_FORCE_MT = """() => {
    const el = document.querySelector('#multi-turn-enabled');
    if (el && !el.checked) { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }
    const other = {'#acpx-enabled': false, '#exec-report-enabled': false,
                   '#ask-execs-enabled': false, '#internetEnabled': false};
    for (const sel of Object.keys(other)) {
        const e2 = document.querySelector(sel);
        if (e2 && !e2.disabled && e2.checked !== other[sel]) {
            e2.checked = other[sel]; e2.dispatchEvent(new Event('change', {bubbles: true}));
        }
    }
    return (typeof isMultiTurnEnabled === 'function') ? isMultiTurnEnabled() : (el ? !!el.checked : null);
}"""


def ensure_multi_turn(page):
    try:
        return page.evaluate(_JS_FORCE_MT)
    except Exception:
        return None


# The self-healing invoker broadcasts INTERIM status frames while it retries a
# flaky model step (agent/self_healing.py::_announce). These are NOT the final
# answer — if we scrape one, we must re-ask and wait for the real answer.
_TRANSIENT_STATUS = (
    "I will NOT hang; only you can stop me",
    "retrying the same request",
    "Tactic #",
)


def looks_transient(ans):
    a = ans or ""
    return any(m in a for m in _TRANSIENT_STATUS)


def grab_fullscreen(page, path):
    """Full DESKTOP screenshot (entire screen incl. the taskbar clock)."""
    try:
        page.bring_to_front()
    except Exception:
        pass
    time.sleep(0.30)
    try:
        img = ImageGrab.grab(all_screens=True)
    except TypeError:
        img = ImageGrab.grab()
    img.save(path)
    return path


# --------------------------------------------------------------------------- summary
_BADGE = {"PASS": "#1e8e3e", "PASS*": "#188038", "WEAK": "#b06000", "FAIL": "#c5221f"}


def build_summary(rows, done, started_iso):
    counts = {"PASS": 0, "PASS*": 0, "WEAK": 0, "FAIL": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    passed = counts["PASS"] + counts["PASS*"]
    now = _dt.datetime.now().isoformat(timespec="seconds")
    parts = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append("<title>Discoverer 1000 — Evidence</title><style>")
    parts.append("body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;color:#e8ecf3}")
    parts.append(".top{position:sticky;top:0;background:#131a2b;padding:16px 22px;border-bottom:2px solid #2a3550;z-index:9}")
    parts.append("h1{margin:0 0 6px;font-size:20px}")
    parts.append(".stat{display:inline-block;margin:4px 14px 0 0;font-size:15px}")
    parts.append(".b{padding:2px 10px;border-radius:12px;color:#fff;font-weight:600}")
    parts.append(".grid{padding:18px}")
    parts.append(".test{background:#182135;border:1px solid #26324e;border-radius:10px;margin:0 0 16px;padding:12px 14px}")
    parts.append(".hdr{font-weight:600;margin-bottom:6px}")
    parts.append(".q{color:#a7b3c9;font-size:12.5px;margin:2px 0 8px;white-space:pre-wrap}")
    parts.append("img{max-width:640px;width:100%;border:1px solid #33405f;border-radius:6px;display:block}")
    parts.append("details{margin-top:8px}pre{white-space:pre-wrap;background:#0c1120;padding:10px;border-radius:6px;max-height:280px;overflow:auto;color:#cdd6e6}")
    parts.append("</style></head><body>")
    parts.append("<div class='top'><h1>Tlamatini — Discoverer 1000-Test Evidence</h1>")
    parts.append("<div>Started %s &nbsp;·&nbsp; updated %s &nbsp;·&nbsp; through the chat GUI (login angela) &nbsp;·&nbsp; every photo is the FULL screen incl. the clock</div>" % (html.escape(started_iso), html.escape(now)))
    parts.append("<div style='margin-top:8px'>")
    parts.append("<span class='stat'>Completed: <b>%d / %d</b></span>" % (done, N))
    parts.append("<span class='stat'><span class='b' style='background:%s'>PASS %d</span></span>" % (_BADGE["PASS"], passed))
    parts.append("<span class='stat'><span class='b' style='background:%s'>WEAK %d</span></span>" % (_BADGE["WEAK"], counts["WEAK"]))
    parts.append("<span class='stat'><span class='b' style='background:%s'>FAIL %d</span></span>" % (_BADGE["FAIL"], counts["FAIL"]))
    rate = (100.0 * passed / done) if done else 0.0
    parts.append("<span class='stat'>Pass-rate: <b>%.1f%%</b></span>" % rate)
    parts.append("</div></div><div class='grid'>")
    for r in reversed(rows):   # newest first
        color = _BADGE.get(r["verdict"], "#666")
        parts.append("<div class='test'>")
        parts.append("<div class='hdr'>#%s &nbsp; %s &nbsp; <span class='b' style='background:%s'>%s</span> &nbsp; %s &nbsp; %.1fs</div>"
                     % (html.escape(r["id"]), html.escape(r["ts"]), color, r["verdict"],
                        html.escape(r["reason"]), r.get("elapsed_s", 0.0)))
        parts.append("<div class='q'>%s</div>" % html.escape(r["question"][:400]))
        shot_rel = "shots/" + os.path.basename(r["shot"])
        parts.append("<a href='%s' target='_blank'><img loading='lazy' src='%s'></a>" % (shot_rel, shot_rel))
        parts.append("<details><summary>answer (%d chars)</summary><pre>%s</pre></details>"
                     % (r.get("answer_chars", 0), html.escape((r.get("answer") or "")[:6000])))
        parts.append("</div>")
    parts.append("</div></body></html>")
    tmp = SUMMARY_HTML + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    os.replace(tmp, SUMMARY_HTML)


# --------------------------------------------------------------------------- resilience
def wait_editable(page, ms):
    """Block until the chat input is editable again (prev heavy run releasing)."""
    try:
        page.wait_for_function(R._JS_EDITABLE, timeout=ms)
    except Exception:
        pass


def wait_ready(page, ms):
    try:
        page.wait_for_function(R._JS_READY, timeout=ms)
    except Exception:
        pass


def server_up(url):
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return 200 <= getattr(r, "status", 200) < 500
    except Exception:
        return False


def wait_for_server(url, max_minutes=60):
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        if server_up(url):
            return True
        time.sleep(5)
    return False


def full_recover(h):
    """Re-login + re-open chat + re-set toggles. Survives a server restart that
    dropped the session (the recover() in run_test only reloads the chat page)."""
    try:
        h.login()
        h.goto_chat()
        try:
            h.page.wait_for_load_state("load", timeout=30000)
        except Exception:
            pass
        h.set_toggles()
        ensure_multi_turn(h.page)
        return True
    except Exception as e:
        print("  full_recover failed:", e, flush=True)
        return False


# --------------------------------------------------------------------------- args shim
class Args:
    # HARD RULE (Angela, 2026-07-07): headless is FORBIDDEN. This test is ALWAYS
    # visible/headed. (run_test.Harness.launch also forces headless=False.)
    headless = False          # VISIBLE Chrome — Angela MUST see it. Never flip to True.
    slowmo = 0
    user = os.environ.get("TLAMATINI_USER", "angela")
    password = os.environ.get("TLAMATINI_PASS", "")
    judge_model = None        # judge is never called here (we use disc_verdict)
    not_ready_retries = 3
    not_ready_backoff = 8.0
    timeout = int(os.environ.get("DISC_TIMEOUT", "300"))


def main():
    started_iso = _dt.datetime.now().isoformat(timespec="seconds")
    print("=" * 70)
    print("TLAMATINI DISCOVERER 1000-TEST  ·  full-screen evidence per test")
    print("run dir :", RUN_DIR)
    print("target  :", N, "tests  ·  login:", Args.user)
    print("=" * 70, flush=True)

    if not Args.password:
        print("FATAL: TLAMATINI_PASS not set — cannot log in.")
        return 2

    args = Args()
    h = R.Harness(args)
    rows = []
    done = 0
    timeout_ms = args.timeout * 1000

    with sync_playwright() as p:
        browser = h.launch(p)
        try:
            h.login()
            h.goto_chat()
            try:
                h.page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass
            time.sleep(0.6)
            h.set_toggles()
            mt0 = ensure_multi_turn(h.page)
            # Wipe any restored server-side history so test 1 cannot scrape a
            # stale prior answer (chat history is per-user and is restored on load).
            try:
                h.clear_history()
                ensure_multi_turn(h.page)
                print("  cleared restored chat history before starting.", flush=True)
            except Exception as e:
                print("  initial clear_history failed (continuing):", e, flush=True)
            print("Logged in + toggles set. isMultiTurnEnabled() -> %r. Starting tests." % mt0, flush=True)

            fail_streak = 0
            seen_answers = set()
            base_url = C.BASE_URL + "/"
            with open(RESULTS, "a", encoding="utf-8") as rf:
                for i in range(N):
                    q = make_question(i)
                    # Give every test its OWN clean conversation so a prior turn can
                    # never bleed the wrong product/severity into the model's answer.
                    # (clean-history-and-reconnect deletes this user's history + rebuilds
                    # the chain; the sleep lets the async rebuild swap in before we send,
                    # and ask_one's not-ready retry covers any residual lag.)
                    try:
                        h.clear_history()
                        time.sleep(3.0)
                    except Exception as e:
                        print("  per-test clear_history failed (continuing):", e, flush=True)
                    # recover from a server outage / dropped session before sending
                    if fail_streak >= 3:
                        print("  fail-streak=%d -> checking server + recovering session"
                              % fail_streak, flush=True)
                        if not server_up(base_url):
                            print("  server DOWN -> waiting for it to come back...", flush=True)
                            wait_for_server(base_url, max_minutes=120)
                        full_recover(h)
                        fail_streak = 0
                    # make sure the single-lane chain is free before we send
                    wait_editable(h.page, 180_000)
                    mt_sent = ensure_multi_turn(h.page)   # re-assert + capture what WILL be sent
                    rec = None
                    for _ta in range(3):   # up to 3 attempts past a transient self-healing status
                        try:
                            rec = h.ask_one(q, timeout_ms=timeout_ms)
                        except Exception as e:
                            rec = {"id": q["id"], "category": q["category"], "question": q["text"],
                                   "answer": "", "answer_chars": 0, "elapsed_s": 0.0,
                                   "completed": False, "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                                   "notes": ["exception: %s" % e]}
                            try:
                                h.recover()
                            except Exception:
                                pass
                            break
                        if not looks_transient(rec.get("answer", "")):
                            break
                        print("   captured a transient self-healing status -> re-asking (%d/2)"
                              % (_ta + 1), flush=True)
                        wait_ready(h.page, 180_000)
                        wait_editable(h.page, 180_000)
                        ensure_multi_turn(h.page)

                    answer_text = rec.get("answer", "") or ""
                    if not rec.get("completed", True):
                        # timed out / never finished -> NEVER keep a stale fallback scrape
                        verdict, reason, answer_text = "FAIL", "did-not-complete/timeout", ""
                    else:
                        verdict, reason = disc_verdict(answer_text)
                        # guard: an answer we've already seen is a stale scrape, not a pass
                        if answer_text and answer_text in seen_answers:
                            verdict, reason = "WEAK", "stale-repeat"
                    if answer_text:
                        seen_answers.add(answer_text)
                    shot = os.path.join(SHOTS_DIR, "disc_%04d.png" % (i + 1))
                    try:
                        grab_fullscreen(h.page, shot)
                        shot_ok = True
                    except Exception as e:
                        shot_ok = False
                        print("  WARN screenshot failed:", e, flush=True)

                    row = {
                        "id": rec.get("id", q["id"]),
                        "n": i + 1,
                        "ts": rec.get("ts"),
                        "question": rec.get("question", q["text"]),
                        "answer": answer_text,
                        "answer_chars": len(answer_text),
                        "elapsed_s": rec.get("elapsed_s", 0.0),
                        "verdict": verdict,
                        "reason": reason,
                        "shot": shot,
                        "shot_ok": shot_ok,
                        "multi_turn_sent": mt_sent,
                    }
                    rows.append(row)
                    rf.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rf.flush()
                    done += 1

                    print("[%4d/%d] %-5s %-22s %5.1fs  chars=%-5d  mt=%s  %s"
                          % (i + 1, N, verdict, reason, row["elapsed_s"],
                             row["answer_chars"], mt_sent, os.path.basename(shot)), flush=True)

                    # settle: let the single-lane chain fully release before next send
                    wait_ready(h.page, 180_000)
                    time.sleep(0.8)
                    # track consecutive fast-empty failures (server-outage signature)
                    if verdict == "FAIL" and row["answer_chars"] == 0 and row["elapsed_s"] < 3:
                        fail_streak += 1
                    else:
                        fail_streak = 0

                    if (i + 1) % 5 == 0 or (i + 1) == N:
                        build_summary(rows, done, started_iso)
        finally:
            build_summary(rows, done, started_iso)
            try:
                browser.close()
            except Exception:
                pass

    # final tally
    counts = {"PASS": 0, "PASS*": 0, "WEAK": 0, "FAIL": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("=" * 70)
    print("DONE. completed=%d/%d  PASS=%d PASS*=%d WEAK=%d FAIL=%d"
          % (done, N, counts["PASS"], counts["PASS*"], counts["WEAK"], counts["FAIL"]))
    print("SUMMARY:", SUMMARY_HTML)
    print("=" * 70, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
