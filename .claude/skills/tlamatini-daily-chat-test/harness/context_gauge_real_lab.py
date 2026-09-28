# Tlamatini Author Banner - do not remove
r"""
THE REAL CONTEXT GAUGE - VISIBLE LABORATORY (Angela, 2026-09-28)
================================================================

"Make a real analysis and make a laboratory of measuring with real values,
according each point of considerable change ... get the real real real real
real values from ollama API and make that gauge counter to be real, NOT FAKE."

What this does, in a HEADED real Chrome on the real desktop, against the
SOURCE server on :8001 (never the installed Tlamatini on :8000):

  1. page opened / agent ready  -> the ring shows the NEXT request, REAL
  2. Clear history              -> back to the empty-history baseline
  3. Multi-Turn ON              -> the bound tool surface changes
  4. a question                 -> live frames, then REAL; history grows
  5. Set file as context        -> a real file through the real file picker
  6. a question about the file  -> the live request carries the context
  7. Clear context              -> the context bytes leave the request
  8. Clear history              -> the ring returns to step 3's value
  9. Multi-Turn OFF             -> recalculated; equal to step 8 when the
                                   whole tool surface fits both modes
 10. a message the one-shot     -> no model call, so NO live reading is
     shape check refuses           invented; the answer's totals say 0 calls
 11. a real Multi-Turn OFF      -> the live request is the at-rest one PLUS
     question                      the question's own bytes, nothing else

At EVERY step the number the ring shows as REAL is checked against the
``prompt_eval_count`` Ollama returned, as written in tlamatini.log by the
server - the GUI must show Ollama's own number, digit for digit.

Photos: Shoter (whole desktop). Exit codes: 0 all passed, 1 a check failed,
4 the environment could not be established (named reason, no traceback).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

os.environ.setdefault("TLAMATINI_BASE_URL", "http://127.0.0.1:8001")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C                          # noqa: E402
from preflight import ensure_ready          # noqa: E402
from shoter_shot import take_shot           # noqa: E402

from playwright.sync_api import sync_playwright   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, "Temp", "context_gauge_lab", "visible_run")
LOG_PATH = os.path.join(REPO, "Tlamatini", "tlamatini.log")
SAMPLE = os.path.join(REPO, "Temp", "context_gauge_lab", "lab_context_sample.py")
os.makedirs(OUT, exist_ok=True)

Q1 = "Reply with the single word OK and nothing else."
Q2 = ("In one short sentence: which class does the loaded file define, and "
      "what does its total() method return? Do not use any tool.")
# Passes ask_rag's local prompt-shape check (it starts with "what"), so with
# Multi-Turn OFF it reaches the main model - unlike Q1, which that check
# refuses when Multi-Turn is off (step 10 relies on exactly that).
Q3 = "What is 2 plus 2? Reply with only the number."

RESULTS = []
READINGS = []

RING_JS = """function () {
  var el = document.getElementById('context-gauge-row');
  if (!el) return null;
  var t = function (s) { var n = el.querySelector(s); return n ? (n.textContent || '').trim() : ''; };
  var ti = function (s) { var n = el.querySelector(s); return n ? (n.title || '') : ''; };
  return {tokens: t('.ctxg-tokens'), tokensTitle: ti('.ctxg-tokens'),
          sub: t('.ctxg-title-sub'), subTitle: ti('.ctxg-title-sub'),
          bytes: t('.ctxg-bytes'), streams: t('.ctxg-streams-label'),
          pct: t('.ctxg-ring-pct'), zone: el.getAttribute('data-zone') || ''};
}"""

# Every frame is stored WITH the ring exactly as the gauge drew it for that
# frame. The event does not bubble and the gauge renders synchronously inside
# dispatchEvent, so wrapping dispatchEvent reads the ring the instant after the
# render - before the next frame can replace it. (A 0.5 s poll lost that race:
# the at-rest frame follows the answer's live frame within a second.)
COLLECT = """
window.__gauge = [];
(function () {
  var readRing = %s;
  var original = EventTarget.prototype.dispatchEvent;
  EventTarget.prototype.dispatchEvent = function (event) {
    var result = original.apply(this, arguments);
    try {
      if (event && event.type === 'tlm:context-gauge') {
        var frame = JSON.parse(JSON.stringify(event.detail || {}));
        frame.__ring = readRing();
        window.__gauge.push(frame);
      }
    } catch (_) {}
    return result;
  };
})();
""" % RING_JS

READ_RING = "() => (%s)()" % RING_JS


def say(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:300]))
    say(("[PASS] " if ok else "[FAIL] ") + name + (("   -> " + str(detail)[:200]) if detail else ""))
    return bool(ok)


def frames(page):
    try:
        return page.evaluate("window.__gauge || []")
    except Exception:                               # noqa: BLE001
        return []


def wait_frame(page, start, pred, timeout, what):
    deadline = time.time() + timeout
    last_note = 0.0
    while time.time() < deadline:
        found = [f for f in frames(page)[start:] if pred(f)]
        if found:
            return found[-1]
        if time.time() - last_note > 10:
            ring = page.evaluate(READ_RING) or {}
            say("   ... waiting for %s | ring now: %s | %s" % (what, ring.get("tokens"), ring.get("sub")))
            last_note = time.time()
        time.sleep(0.5)
    return None


def is_rest_real(reason):
    return lambda f: (f.get("kind") == "rest" and f.get("ratio_is_real") is True
                      and reason in str(f.get("label", "")))


def log_real_for(seq):
    """Ollama's prompt_eval_count for request `seq`, as the SERVER logged it."""
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    hits = re.findall(r"\[CONTEXT-REAL\][^\n]*?seq=%d [^\n]*?prompt_eval_count=(\d+)" % seq, text)
    return int(hits[-1]) if hits else None


def digits(text):
    return re.sub(r"\D", "", (text or "").split("tokens")[0])


def record(page, step, frame, shot):
    # The ring AS DRAWN FOR THIS FRAME (captured inside dispatchEvent), not
    # whatever a later frame has painted over it by the time we look.
    ring = frame.get("__ring") or page.evaluate(READ_RING) or {}
    real = frame.get("tokens_real")
    logged = log_real_for(int(frame.get("seq") or 0))
    row = {
        "step": step, "kind": frame.get("kind"), "label": frame.get("label"),
        "seq": frame.get("seq"), "tokens_real": real,
        "tokens_estimated": frame.get("tokens_estimated"),
        "estimate_error_pct": frame.get("estimate_error_pct"),
        "bytes_total": frame.get("bytes_total"), "bytes_context": frame.get("bytes_context"),
        "bytes_prefix": frame.get("bytes_prefix"), "bytes_history": frame.get("bytes_history"),
        "bytes_plan": frame.get("bytes_plan"), "bytes_loop": frame.get("bytes_loop"),
        "ceiling": frame.get("ceiling_tokens"), "ceiling_source": frame.get("ceiling_source"),
        "ratio": frame.get("ratio"), "model": frame.get("real_model") or frame.get("model"),
        "ring_text": ring.get("tokens"), "ring_sub": ring.get("sub"),
        "note": frame.get("note", ""), "log_prompt_eval_count": logged, "photo": shot,
    }
    READINGS.append(row)
    say("   READING %-28s REAL=%s est=%s err=%s%% bytes=%s ctx=%s ceiling=%s (%s)"
        % (step, real, row["tokens_estimated"], row["estimate_error_pct"], row["bytes_total"],
           row["bytes_context"], row["ceiling"], row["ceiling_source"]))
    check("%s: the ring shows Ollama's number as REAL" % step,
          "REAL" in (ring.get("tokens") or "") and digits(ring.get("tokens")) == str(real),
          "ring=%r frame=%s" % (ring.get("tokens"), real))
    check("%s: it equals the prompt_eval_count the server logged" % step,
          logged is not None and logged == real, "log=%s frame=%s" % (logged, real))
    return row


def exact_accounting(step, rest, live, question, multi_turn):
    """EVERY byte between the at-rest prediction and the live request.

    Angela, 2026-09-28: "the context counter gauge must work very exact, in
    both not multi-turn and multi-turn". The at-rest frame is the next request
    minus what cannot exist before its question; so the live request must be
    that prediction PLUS the question's own bytes (history bucket) PLUS, in
    Multi-Turn only, the planner's per-question plan (prefix bucket) - and
    nothing else, byte for byte.
    """
    n = lambda row, key: int(row.get(key) or 0)          # noqa: E731
    q_bytes = len(question.encode("utf-8"))              # plain ASCII: no JSON escapes
    d_hist = n(live, "bytes_history") - n(rest, "bytes_history")
    d_prefix = n(live, "bytes_prefix") - n(rest, "bytes_prefix")
    plan = n(live, "bytes_plan")
    check("%s history: live = prediction + the question's own %d bytes, nothing else" % (step, q_bytes),
          d_hist == q_bytes, "history %+d B (question %d B)" % (d_hist, q_bytes))
    if multi_turn:
        check("%s prefix: live = prediction + exactly the planner's per-question plan" % step,
              plan > 0 and d_prefix == plan and n(rest, "bytes_plan") == 0,
              "prefix %+d B, plan %d B" % (d_prefix, plan))
    else:
        check("%s prefix: identical to the prediction (one-shot sends no plan)" % step,
              d_prefix == 0 and plan == 0, "prefix %+d B, plan %d B" % (d_prefix, plan))
    check("%s the whole request is accounted for, byte for byte" % step,
          n(live, "bytes_total") - n(rest, "bytes_total") == q_bytes + (plan if multi_turn else 0)
          and n(live, "bytes_loop") == n(rest, "bytes_loop") == 0,
          "total %s -> %s" % (n(rest, "bytes_total"), n(live, "bytes_total")))


def click_continue(page):
    try:
        btn = page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last
        btn.wait_for(state="visible", timeout=6000)
        btn.click()
        return True
    except Exception:                               # noqa: BLE001
        return False


def set_toggle(page, sel, want):
    if page.is_checked(sel) != want:
        page.click(sel, force=True)
        time.sleep(0.3)
    return page.is_checked(sel) == want


def ask(page, text, step, timeout=420):
    start = len(frames(page))
    page.fill(C.SEL["chat_input"], text)
    page.click(C.SEL["chat_submit"])
    say("   sent: %s" % text[:80])
    live = wait_frame(page, start, lambda f: f.get("kind") == "live" and f.get("ratio_is_real") is True,
                      timeout, "the first REAL live frame of '%s'" % step)
    shot_live = take_shot(OUT, "%s_live.png" % step)
    rest = wait_frame(page, start, is_rest_real("answer finished"), timeout,
                      "the at-rest frame after '%s'" % step)
    return live, rest, shot_live


def main():
    say("=" * 76)
    say("THE REAL CONTEXT GAUGE - VISIBLE LABORATORY   (Angela Lopez Mendoza)")
    say("target %s   log %s" % (C.BASE_URL, LOG_PATH))
    say("=" * 76)
    if ":8000" in C.BASE_URL:
        say("!! refusing to run against :8000 - that is the INSTALLED Tlamatini, not this code")
        return 4
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return 4

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as exc:                    # noqa: BLE001
            say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        ctx.add_init_script(COLLECT)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        page.set_default_timeout(C.NAV_TIMEOUT_MS)

        page.goto(C.BASE_URL + C.LOGIN_PATH)
        page.fill(C.SEL["login_user"], C.USERNAME)
        page.fill(C.SEL["login_pass"], C.PASSWORD)
        page.click(C.SEL["login_submit"])
        page.wait_for_load_state("networkidle")
        page.goto(C.BASE_URL + C.CHAT_PATH)
        page.wait_for_selector(C.SEL["chat_input"])
        page.bring_to_front()
        if page.evaluate(READ_RING) is None:
            take_shot(OUT, "00_wrong_target.png")
            say("!! WRONG TARGET: no #context-gauge-row on %s" % C.BASE_URL)
            browser.close()
            return 4
        for key in ("t_acpx", "t_ask_execs", "t_internet", "t_exec_report"):
            if page.locator(C.SEL[key]).count():
                set_toggle(page, C.SEL[key], False)
        set_toggle(page, C.SEL["t_multi_turn"], False)

        # 1. page opened -------------------------------------------------------
        f1 = wait_frame(page, 0, lambda f: f.get("kind") == "rest" and f.get("ratio_is_real") is True,
                        240, "the first REAL at-rest frame")
        if not check("1 page opened: a REAL at-rest frame arrives with no message sent", f1):
            take_shot(OUT, "01_no_real_frame.png")
            browser.close()
            return finish(1)
        record(page, "1_page_opened", f1, take_shot(OUT, "01_page_opened.png"))

        # 2. Clear history -> the empty-history baseline ----------------------
        start = len(frames(page))
        page.click(C.SEL["clean_history"])
        click_continue(page)
        f2 = wait_frame(page, start, is_rest_real("history cleared"), 240, "'history cleared'")
        if check("2 Clear history: the ring is recalculated (REAL)", f2):
            record(page, "2_history_cleared", f2, take_shot(OUT, "02_history_cleared.png"))

        # 3. Multi-Turn ON ----------------------------------------------------
        start = len(frames(page))
        set_toggle(page, C.SEL["t_multi_turn"], True)
        f3 = wait_frame(page, start, is_rest_real("Multi-Turn on"), 180, "'Multi-Turn on'")
        r3 = record(page, "3_multi_turn_on", f3, take_shot(OUT, "03_multi_turn_on.png")) if \
            check("3 Multi-Turn ON: the ring is recalculated (REAL)", f3) else None

        # 4. a question -> live frames, then the history grows ----------------
        live4, f4, shot4 = ask(page, Q1, "4_question")
        if check("4 the question's live request is shown REAL", live4):
            r4_live = record(page, "4_question_live", live4, shot4)
            check("4 the ring names the mode it is really in", live4.get("source") == "multi-turn",
                  "source=%r" % live4.get("source"))
            if r3:
                exact_accounting("4", r3, r4_live, Q1, multi_turn=True)
        r4 = record(page, "4_after_answer", f4, take_shot(OUT, "04_after_answer.png")) if \
            check("4 after the answer the ring shows the NEXT request (REAL)", f4) else None
        if r3 and r4:
            check("4 the history grew, so the next request is BIGGER",
                  r4["tokens_real"] > r3["tokens_real"], "%s -> %s" % (r3["tokens_real"], r4["tokens_real"]))
            turn = (f4 or {}).get("turn") or {}
            check("4 the answer's REAL totals are attached (main chain only)",
                  int(turn.get("calls") or 0) >= 1, json.dumps(turn)[:200])

        # 5. Set file as context (the real file picker) -----------------------
        start = len(frames(page))
        page.click("#context-menu-button")
        with page.expect_file_chooser() as chooser:
            page.click("#set-file-context")
        chooser.value.set_files(SAMPLE)
        f5 = wait_frame(page, start, is_rest_real("context loaded"), 300, "'context loaded'")
        r5 = record(page, "5_context_loaded", f5, take_shot(OUT, "05_context_loaded.png")) if \
            check("5 Set file as context: the ring is recalculated (REAL)", f5) else None
        if r5:
            check("5 the at-rest frame says honestly what depends on the next question",
                  "not included yet" in (r5.get("note") or ""), (r5.get("note") or "")[:200])

        # 6. a question about the file -> the context travels -----------------
        live6, f6, shot6 = ask(page, Q2, "6_question_on_context")
        r6_live = None
        if check("6 the question's live request is shown REAL", live6):
            r6_live = record(page, "6_question_live", live6, shot6)
            check("6 the live request CARRIES the loaded context (context bytes > 0)",
                  int(live6.get("bytes_context") or 0) > 0, "bytes_context=%s" % live6.get("bytes_context"))
        if f6:
            record(page, "6_after_answer", f6, take_shot(OUT, "06_after_answer.png"))

        # 7. Clear context -----------------------------------------------------
        start = len(frames(page))
        page.click("#context-menu-button")
        page.locator("#clear-context").wait_for(state="visible", timeout=20000)
        page.click("#clear-context")
        click_continue(page)
        f7 = wait_frame(page, start, is_rest_real("context cleared"), 240, "'context cleared'")
        if check("7 Clear context: the ring is recalculated (REAL)", f7):
            r7 = record(page, "7_context_cleared", f7, take_shot(OUT, "07_context_cleared.png"))
            check("7 no context bytes remain in the request", int(r7["bytes_context"] or 0) == 0,
                  "bytes_context=%s" % r7["bytes_context"])
            if r6_live:
                check("7 the request is smaller than the one that carried the context",
                      r7["tokens_real"] < r6_live["tokens_real"],
                      "%s -> %s" % (r6_live["tokens_real"], r7["tokens_real"]))

        # 8. Clear history -> the ring returns to its initial value -----------
        start = len(frames(page))
        page.click(C.SEL["clean_history"])
        click_continue(page)
        f8 = wait_frame(page, start, is_rest_real("history cleared"), 240, "'history cleared' again")
        r8 = None
        if check("8 Clear history again: the ring is recalculated (REAL)", f8):
            r8 = record(page, "8_history_cleared_again", f8, take_shot(OUT, "08_history_cleared_again.png"))
            if r3:
                check("8 it returns EXACTLY to the Multi-Turn empty-history value of step 3",
                      r8["tokens_real"] == r3["tokens_real"], "%s vs %s" % (r8["tokens_real"], r3["tokens_real"]))

        # 9. Multi-Turn OFF ----------------------------------------------------
        # Compared with step 8, never step 2: External-MCP servers may finish
        # connecting in between (2026-09-28: lumen-book-reader added 7 tools,
        # 383.4 KB -> 393.2 KB of prefix), so step 2 is a different request.
        start = len(frames(page))
        set_toggle(page, C.SEL["t_multi_turn"], False)
        f9 = wait_frame(page, start, is_rest_real("Multi-Turn off"), 180, "'Multi-Turn off'")
        r9 = None
        if check("9 Multi-Turn OFF: the ring is recalculated (REAL)", f9):
            r9 = record(page, "9_multi_turn_off", f9, take_shot(OUT, "09_multi_turn_off.png"))
            if r8:
                # Multi-Turn only changes the request when the budgeter has
                # to DROP tools. When the whole surface fits, both modes bind
                # every tool, the request is identical - and so is the count.
                d_bytes = int(r9["bytes_total"] or 0) - int(r8["bytes_total"] or 0)
                d_tokens = int(r9["tokens_real"] or 0) - int(r8["tokens_real"] or 0)
                if d_bytes == 0:
                    check("9 same request as step 8 (the whole tool surface fits both modes) "
                          "=> the same REAL count", d_tokens == 0,
                          "bytes %s = %s, REAL %s vs %s" % (r9["bytes_total"], r8["bytes_total"],
                                                          r9["tokens_real"], r8["tokens_real"]))
                else:
                    check("9 the request changed size and Ollama's count moved the same way",
                          (d_bytes > 0) == (d_tokens > 0) and d_tokens != 0,
                          "bytes %+d, REAL %+d" % (d_bytes, d_tokens))

        # 10. a message the one-shot path REFUSES -> no model call, no fake --
        # With Multi-Turn off, ask_rag's local prompt-shape check refuses a
        # message that is not a question or command ("Please rephrase ...")
        # and the main model is NEVER called. The gauge must say exactly
        # that: no live reading is invented, the answer's totals are 0
        # calls, and the ring moves on to the next request (the refusal is
        # now part of the history).
        start = len(frames(page))
        page.fill(C.SEL["chat_input"], Q1)
        page.click(C.SEL["chat_submit"])
        say("   sent (expected to be refused by the shape check): %s" % Q1)
        f10 = wait_frame(page, start, is_rest_real("answer finished"), 240,
                         "the at-rest frame after the refused message")
        r10 = None
        if check("10 a refused message: the ring moves on to the next request (REAL)", f10):
            r10 = record(page, "10_refused_message", f10, take_shot(OUT, "10_refused_message.png"))
            fake_live = [f for f in frames(page)[start:] if f.get("kind") == "live"]
            check("10 no live reading is invented when the model is never called",
                  not fake_live, "%d live frame(s)" % len(fake_live))
            turn = (f10 or {}).get("turn") or {}
            check("10 the answer's REAL totals say 0 Ollama calls",
                  turn.get("calls") in (0, None) and int(turn.get("prompt_tokens") or 0) == 0,
                  json.dumps(turn)[:200])
            if r9:
                check("10 the refusal is now history, so the next request is BIGGER",
                      r10["tokens_real"] > r9["tokens_real"],
                      "%s -> %s" % (r9["tokens_real"], r10["tokens_real"]))

        # 11. a real Multi-Turn OFF question -> proves the at-rest prediction -
        # Between step 10's at-rest frame and this request the ONLY change is
        # the question itself, so the live request must be the at-rest one
        # PLUS the question's own bytes, and Ollama must count only a few
        # tokens more. This is the direct proof that the ring predicted the
        # next message exactly - history, tools, system prompt and all.
        live11, f11, shot11 = ask(page, Q3, "11_one_shot_question")
        if check("11 the one-shot question's live request is shown REAL", live11):
            r11 = record(page, "11_one_shot_live", live11, shot11)
            check("11 the ring names the mode it is really in", live11.get("source") == "one-shot",
                  "source=%r" % live11.get("source"))
            if r10:
                exact_accounting("11", r10, r11, Q3, multi_turn=False)
                d_tokens = int(r11["tokens_real"] or 0) - int(r10["tokens_real"] or 0)
                check("11 Ollama counts only the question more (0 < +N <= 40 tokens)",
                      0 < d_tokens <= 40,
                      "REAL %s -> %s (%+d)" % (r10["tokens_real"], r11["tokens_real"], d_tokens))
        if f11:
            record(page, "11_after_answer", f11, take_shot(OUT, "11_after_answer.png"))

        browser.close()
    return finish(0)


def finish(code):
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    total = len(RESULTS)
    with open(os.path.join(OUT, "readings.json"), "w", encoding="utf-8") as fh:
        json.dump({"results": RESULTS, "readings": READINGS}, fh, indent=2, default=str)
    rows = "".join(
        "<tr><td>%s</td><td style='color:%s;font-weight:700'>%s</td><td><code>%s</code></td></tr>"
        % (n, "#2e7d32" if ok else "#c62828", "PASS" if ok else "FAIL", d) for n, ok, d in RESULTS)
    reads = "".join(
        "<tr><td>%s</td><td>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (r["step"], r["kind"], r["tokens_real"], r["log_prompt_eval_count"], r["tokens_estimated"],
           r["estimate_error_pct"], r["bytes_context"], r["ceiling_source"]) for r in READINGS)
    with open(os.path.join(OUT, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Real context gauge lab</title>"
                 "<body style='font:14px system-ui;margin:24px'>"
                 "<h2>The REAL context gauge &mdash; visible laboratory</h2>"
                 "<p>Tlamatini &middot; Angela L&oacute;pez Mendoza &middot; %s &middot; %s</p>"
                 "<p><b>%d/%d checks passed.</b> Photos by Shoter (whole desktop).</p>"
                 "<h3>Readings (REAL = Ollama prompt_eval_count)</h3>"
                 "<table border=1 cellpadding=6 cellspacing=0><tr><th>step</th><th>kind</th>"
                 "<th>ring REAL</th><th>server log</th><th>chars/4 est.</th><th>est. error %%</th>"
                 "<th>context bytes</th><th>ceiling source</th></tr>%s</table>"
                 "<h3>Checks</h3><table border=1 cellpadding=6 cellspacing=0>%s</table></body>"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), C.BASE_URL, passed, total, reads, rows))
    say("-" * 76)
    say("RESULT: %d/%d checks passed   (readings.json + SUMMARY.html in %s)" % (passed, total, OUT))
    if code:
        return code
    return 0 if passed == total and total else 1


if __name__ == "__main__":
    sys.exit(main())
