#!/usr/bin/env python
# ══════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Tlamatini Author Banner — do not remove
# ══════════════════════════════════════════════════════════════════════
"""100+ REAL prompts in a VISIBLE Chrome, watching the context gauge move.

Angela, 2026-09-21: *"run the full suite VISIBLE with the browser, at least
100 prompts, you watching during the tests the measurement"*.

It alternates ONE-SHOT and MULTI-TURN deliberately, because the bug being
proved fixed is that One-Shot never measured at all: the sink was registered
only for Multi-Turn, so a One-Shot question left the ring frozen on whatever
the last Multi-Turn request had put there.

WHAT IT PROVES, per prompt, from the live DOM:
  * the gauge is VISIBLE and carries the legend ("CONTEXT" + which call)
  * the reading MOVES - the byte count is not the same number every time
  * ONE-SHOT really reports (source == 'one-shot'), which it never did
  * MULTI-TURN still reports (source == 'multi-turn')
  * the Send button stays on screen with the row shown (the layout trap)

HONESTY (Angela's rule - never record a stale or transient state as a pass):
  * a prompt whose answer never lands is recorded as a TIMEOUT, never a pass,
    and the run says so in the summary;
  * a gauge reading identical to the previous one is NOT counted as a refresh;
  * exit 3 means the app answering :8000 has no gauge at all (wrong target -
    a frozen install is serving), which is a wrong-target result, not a pass.

Every photo is taken by Tlamatini's Shoter agent, whole desktop.
"""

import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C                       # noqa: E402
import questions as Q                    # noqa: E402
from preflight import ensure_ready       # noqa: E402
from shoter_shot import take_shot        # noqa: E402

from playwright.sync_api import sync_playwright   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "reports", "context_gauge_100")
os.makedirs(OUT, exist_ok=True)

TOTAL = int(os.environ.get("GAUGE_PROMPTS", "100"))
# Per-prompt cap. Generous enough for a real answer, short enough that 100
# prompts finish; a prompt that exceeds it is CANCELLED and recorded as a
# timeout rather than silently skewing the run.
ANSWER_TIMEOUT_S = float(os.environ.get("GAUGE_ANSWER_TIMEOUT", "75"))
GAUGE_WAIT_S = 45.0
SHOT_EVERY = 20

READ_GAUGE = """
() => {
  const el = document.getElementById('context-gauge-row');
  if (!el) return null;
  const t = (s) => { const n = el.querySelector(s); return n ? (n.textContent||'').trim() : ''; };
  return {
    visible: el.offsetHeight > 0 && el.classList.contains('ctxg-visible'),
    height: el.offsetHeight,
    zone: el.getAttribute('data-zone') || '',
    title: t('.ctxg-title-main'),
    sub: t('.ctxg-title-sub'),
    bytes: t('.ctxg-bytes'),
    tokens: t('.ctxg-tokens'),
    streams: t('.ctxg-streams-label')
  };
}
"""

BUSY = """
() => {
  const i = document.getElementById('chat-message-input');
  const s = document.getElementById('wait-spinner');
  return {busy: (i && i.readOnly) || !!s};
}
"""

SEND_ON_SCREEN = """
() => {
  const b = document.getElementById('chat-message-submit');
  if (!b) return {found:false};
  const r = b.getBoundingClientRect();
  return {found:true, onScreen: r.bottom <= window.innerHeight + 1};
}
"""


def _question_text(item, bucket):
    """Normalise one pool entry into a real question string.

    Every bank in questions.py stores (text, expected_keywords) tuples, and the
    AGENTS bank stores an agent NAME rather than a question - so both have to
    be unwrapped here.  Handing the raw tuple to Playwright is what killed the
    first 200-prompt attempt with "Page.fill: expected string, got object"
    before a single prompt was ever sent.
    """
    text = item[0] if isinstance(item, (tuple, list)) and item else item
    text = str(text).strip()
    if bucket == "agents":
        return "In one short paragraph, what does Tlamatini's %s agent do?" % text
    return text


def build_prompts(n):
    """A real mix, short first so the run keeps moving."""
    pool = ([_question_text(q, "qa") for q in Q.GENERAL_QA]
            + [_question_text(q, "qa") for q in Q.SYSTEM_KNOWLEDGE]
            + [_question_text(q, "qa") for q in Q.SELF_KNOWLEDGE]
            + [_question_text(a, "agents") for a in Q.AGENTS])
    pool = [p for p in pool if p]
    out = []
    i = 0
    while len(out) < n:
        out.append(pool[i % len(pool)])
        i += 1
    return out[:n]


def confirm_cancel(page, seconds=6.0):
    """Answer Tlamatini's 'Are you sure you want to cancel now?' dialog.

    Clicking Cancel does NOT cancel: it raises a themed confirmation popup
    (.tlmpop-overlay) whose primary button is 'Continue'. Leaving that popup
    on screen keeps the chat box readonly FOREVER, so every later prompt is
    skipped with 'input never unlocked' - which is exactly how a healthy
    200-prompt run turned into a wall of SKIPPED rows.

    Returns True when a dialog was found AND answered.
    """
    end = time.time() + seconds
    while time.time() < end:
        try:
            overlay = page.locator(".tlmpop-overlay")
            if overlay.count() and overlay.first.is_visible():
                btn = page.locator(".tlmpop-overlay .tlmpop-btn-primary")
                if btn.count():
                    btn.first.click(timeout=3000)
                    time.sleep(0.4)
                    return True
        except Exception:                                  # noqa: BLE001
            pass
        time.sleep(0.2)
    return False


def cancel_run(page):
    """Press Cancel and see the confirmation through, so the box unlocks."""
    try:
        page.click(C.SEL["chat_submit"], timeout=3000)
    except Exception:                                      # noqa: BLE001
        pass
    confirmed = confirm_cancel(page)
    time.sleep(0.6)
    return confirmed


def wait_editable(page, seconds=25.0):
    """Wait until the chat box will actually ACCEPT typing.

    Tlamatini makes #chat-message-input `readonly` while a request is in
    flight.  A fill() issued while it is locked does NOT fail fast: Playwright
    retries "element is not editable" for its whole 30 s timeout and then
    raises, which killed the first 200-prompt run stone dead at prompt 2 after
    Ollama hung for 1m51s and answered 502.

    So: wait for the box, and when it never unlocks, say so and keep going.
    One slow answer must never end the run.
    """
    sel = C.SEL["chat_input"]
    end = time.time() + seconds
    while time.time() < end:
        try:
            if page.locator(sel).is_editable():
                return True
        except Exception:                                  # noqa: BLE001
            pass
        time.sleep(0.25)
    return False


def set_toggle(page, key, want):
    sel = C.SEL.get(key)
    if not sel or page.locator(sel).count() == 0:
        return
    try:
        if page.is_checked(sel) != want:
            page.click(sel, force=True)
            time.sleep(0.12)
    except Exception:                                  # noqa: BLE001
        pass



# ── live feed to the graphical panel (window-test-screen.py) ───────────────
# The panel is Angela's live view of the run.  Feeding it must never be able to
# disturb the test: every call is wrapped and a closed panel costs nothing.
_WTS = None
_WTS_OK = True
_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


def _as_bytes(text):
    """'118.4 KB' -> 121241.  Returns None rather than guessing."""
    try:
        t = str(text).replace(",", "").strip()
        for unit in ("GB", "MB", "KB", "B"):
            if t.upper().endswith(unit):
                return int(float(t[:-len(unit)].strip()) * _UNITS[unit])
        return int(float(t))
    except Exception:
        return None


def _as_int(text):
    try:
        return int(float(str(text).replace(",", "").replace("tok", "").strip()))
    except Exception:
        return None


def _wts(frame):
    """Push one frame to the panel.  Never raises, never blocks the run."""
    global _WTS, _WTS_OK
    if not _WTS_OK:
        return
    try:
        if _WTS is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "wts", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "window-test-screen.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _WTS = mod
        _WTS.send(frame, timeout=1.5)
    except Exception:
        _WTS_OK = False          # panel is gone; stop trying, keep testing


def main():
    prompts = build_prompts(TOTAL)
    rows = []
    print("=" * 78)
    print("CONTEXT GAUGE - %d REAL PROMPTS, VISIBLE CHROME" % TOTAL)
    print("Angela Lopez Mendoza  -  watching the measurement live")
    print("=" * 78)
    print("target : %s%s" % (C.BASE_URL, C.CHAT_PATH))
    print("mix    : odd prompts = ONE-SHOT, every 3rd = MULTI-TURN")

    # ── ESTABLISH the environment, never assume it (Angela, 2026-09-21) ──
    # Every earlier run of this died at the EDGES - server down, empty dev
    # database, a login that could never succeed - and each time Playwright
    # reported a selector timeout that said nothing about the real cause.
    # Preflight repairs what it can and names what it cannot, BEFORE Chrome
    # is ever opened.
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state["ok"]:
        print("\n!! ENVIRONMENT NOT READY - nothing was tested.")
        print("!! %s" % state["reason"])
        if state["repairs"]:
            print("!! repairs attempted: %s" % "; ".join(state["repairs"]))
        return state["exit_code"]
    env_repairs = state["repairs"]

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome",
                                         args=["--start-maximized"])
        except Exception as exc:                        # noqa: BLE001
            print("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_context(no_viewport=True).new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)

        page.goto(C.BASE_URL + C.LOGIN_PATH)
        page.fill(C.SEL["login_user"], C.USERNAME)
        page.fill(C.SEL["login_pass"], C.PASSWORD)
        page.click(C.SEL["login_submit"])
        page.wait_for_load_state("networkidle")
        page.goto(C.BASE_URL + C.CHAT_PATH)
        page.wait_for_selector(C.SEL["chat_input"], timeout=C.NAV_TIMEOUT_MS)
        page.bring_to_front()
        time.sleep(1.0)

        if page.evaluate(READ_GAUGE) is None:
            print("\n!! WRONG TARGET: no #context-gauge-row on %s" % C.BASE_URL)
            print("!! A frozen install is probably serving this port. Nothing tested.")
            take_shot(OUT, "00_wrong_target.png")
            browser.close()
            return 3

        set_toggle(page, "t_acpx", False)
        set_toggle(page, "t_ask_execs", False)
        set_toggle(page, "t_exec_report", False)
        set_toggle(page, "t_internet", False)
        take_shot(OUT, "00_start.png")

        prev_bytes = None
        refreshes = 0
        timeouts = 0
        locked = 0
        errors = 0
        sources = {}
        t_run = time.time()

        for idx, prompt in enumerate(prompts, 1):
            multi = (idx % 3 == 0)          # a third Multi-Turn, the rest One-Shot

            # ── the box must be editable BEFORE we type into it ────────────
            if not wait_editable(page, 20.0):
                cancel_run(page)            # still busy: Cancel + confirm
                if not wait_editable(page, 30.0):
                    locked += 1
                    rows.append({
                        "n": idx, "mode": "multi-turn" if multi else "one-shot",
                        "gauge_source": "", "bytes": "", "tokens": "", "zone": "",
                        "title": "", "sub": "", "moved": False, "answered": False,
                        "seconds": 0.0, "status": "INPUT_LOCKED",
                    })
                    print("  [%3d/%d] %-10s | input never unlocked - SKIPPED"
                          % (idx, TOTAL, "MULTI" if multi else "one-shot"))
                    _wts({"k": "test", "n": idx, "total": TOTAL,
                          "mode": "multi-turn" if multi else "one-shot",
                          "zone": "red", "moved": False,
                          "note": "INPUT LOCKED - skipped"})
                    continue

            set_toggle(page, "t_multi_turn", multi)

            try:
                page.fill(C.SEL["chat_input"], prompt, timeout=10000)
                page.click(C.SEL["chat_submit"], timeout=10000)
            except Exception as exc:                        # noqa: BLE001
                errors += 1
                rows.append({
                    "n": idx, "mode": "multi-turn" if multi else "one-shot",
                    "gauge_source": "", "bytes": "", "tokens": "", "zone": "",
                    "title": "", "sub": "", "moved": False, "answered": False,
                    "seconds": 0.0, "status": "SEND_FAILED",
                })
                print("  [%3d/%d] %-10s | send failed: %s"
                      % (idx, TOTAL, "MULTI" if multi else "one-shot",
                         str(exc).splitlines()[0][:70]))
                _wts({"k": "test", "n": idx, "total": TOTAL,
                      "mode": "multi-turn" if multi else "one-shot",
                      "zone": "red", "moved": False, "note": "SEND FAILED"})
                continue
            t0 = time.time()

            # The gauge fires when the REQUEST is built, well before the answer.
            reading = None
            deadline = time.time() + GAUGE_WAIT_S
            while time.time() < deadline:
                g = page.evaluate(READ_GAUGE)
                # Since 2026-09-21 the row is on screen from page load in an
                # IDLE state that prints "--" rather than a fabricated zero.
                # That placeholder is NOT a measurement and must never be
                # recorded as one, nor counted as the ring "moving".
                if (g and g["visible"] and g["bytes"]
                        and str(g["bytes"]).strip() not in ("--", "-", "")
                        and g["bytes"] != prev_bytes):
                    reading = g
                    break
                time.sleep(0.2)
            if reading is None:
                reading = page.evaluate(READ_GAUGE) or {}

            raw_bytes = str(reading.get("bytes") or "").strip()
            real = raw_bytes not in ("--", "-", "")
            moved = bool(real and reading.get("bytes") != prev_bytes)
            if moved:
                refreshes += 1
            if real:
                prev_bytes = reading.get("bytes")
            src = (reading.get("sub") or "").split("·")[0].strip() or "?"
            sources[src] = sources.get(src, 0) + 1

            # Let the answer land, but never hang the run on one prompt.
            done = False
            while time.time() - t0 < ANSWER_TIMEOUT_S:
                if not page.evaluate(BUSY)["busy"]:
                    done = True
                    break
                time.sleep(0.4)
            if not done:
                timeouts += 1
                cancel_run(page)           # Cancel AND confirm, or the box
                wait_editable(page, 20.0)  # stays readonly for the whole run

            rows.append({
                "n": idx,
                "mode": "multi-turn" if multi else "one-shot",
                "gauge_source": src,
                "bytes": reading.get("bytes", ""),
                "tokens": reading.get("tokens", ""),
                "zone": reading.get("zone", ""),
                "title": reading.get("title", ""),
                "sub": reading.get("sub", ""),
                "moved": moved,
                "answered": done,
                "seconds": round(time.time() - t0, 1),
                "status": "OK" if done else "ANSWER_TIMEOUT",
            })
            print("  [%3d/%d] %-10s | %-22s | %-9s | %s%s"
                  % (idx, TOTAL, "MULTI" if multi else "one-shot",
                     (reading.get("sub") or "-")[:22],
                     reading.get("bytes") or "-",
                     "moved" if moved else "SAME",
                     "" if done else "  <TIMEOUT>"))

            _wts({"k": "test", "n": idx, "total": TOTAL,
                  "mode": "multi-turn" if multi else "one-shot",
                  "bytes": _as_bytes(reading.get("bytes")),
                  "tokens": _as_int(reading.get("tokens")),
                  "zone": reading.get("zone") or "",
                  "moved": moved,
                  "note": ("" if done else "ANSWER TIMEOUT") or src})

            if idx == 1 or idx % SHOT_EVERY == 0 or idx == TOTAL:
                take_shot(OUT, "%03d_prompt.png" % idx)

        send = page.evaluate(SEND_ON_SCREEN)
        final = page.evaluate(READ_GAUGE) or {}
        take_shot(OUT, "zz_final.png")
        browser.close()

    elapsed = time.time() - t_run
    if not rows:                       # nothing measured - say so, never crash
        print("\n!! no prompt produced a reading - nothing to report")
        return 4
    with open(os.path.join(OUT, "readings.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    one_shot_reported = sum(1 for r in rows if r["gauge_source"] == "one-shot")
    multi_reported = sum(1 for r in rows if r["gauge_source"] == "multi-turn")
    distinct = len({r["bytes"] for r in rows if r["bytes"]})

    checks = [
        ("100+ real prompts were sent", len(rows) >= 100, len(rows)),
        ("the legend is on the row", (final.get("title") or "") == "CONTEXT",
         final.get("title")),
        ("ONE-SHOT really reports now", one_shot_reported > 0, one_shot_reported),
        ("MULTI-TURN still reports", multi_reported > 0, multi_reported),
        ("the reading MOVES, it is not frozen", refreshes > 0,
         "%d/%d refreshed" % (refreshes, len(rows))),
        ("many distinct readings, not one stuck value", distinct > 5, distinct),
        ("Send button still on screen", bool(send.get("onScreen")), send),
    ]

    print("-" * 78)
    ok = True
    for name, passed, detail in checks:
        ok = ok and passed
        print(("  [PASS] " if passed else "  [FAIL] ") + name + "   -> %s" % (detail,))
    print("-" * 78)
    print("  prompts        : %d   (answer timeouts: %d, input locked: %d, "
          "send failed: %d)" % (len(rows), timeouts, locked, errors))
    print("  gauge sources  : %s" % sources)
    print("  distinct bytes : %d" % distinct)
    print("  elapsed        : %.1f min" % (elapsed / 60.0))
    print("  photos + csv   : %s" % OUT)

    rws = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
        "<td>%s</td></tr>"
        % (r["n"], r["mode"], r["gauge_source"], r["bytes"], r["zone"],
           "yes" if r["moved"] else "-", "yes" if r["answered"] else "TIMEOUT")
        for r in rows)
    chk = "".join(
        "<tr><td>%s</td><td style='color:%s;font-weight:700'>%s</td><td>%s</td></tr>"
        % (n, "#2e7d32" if p else "#c62828", "PASS" if p else "FAIL", d)
        for n, p, d in checks)
    with open(os.path.join(OUT, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Context gauge - %d prompts</title>"
                 "<body style='font:14px system-ui;margin:24px'>"
                 "<h2>Context gauge &mdash; %d real prompts, visible Chrome</h2>"
                 "<p>Tlamatini &middot; Angela L&oacute;pez Mendoza &middot; %s &middot; "
                 "%.1f min &middot; timeouts: %d</p>"
                 "<table border=1 cellpadding=6 cellspacing=0>%s</table>"
                 "<h3>Every reading</h3>"
                 "<table border=1 cellpadding=4 cellspacing=0>"
                 "<tr><th>#</th><th>mode</th><th>gauge source</th><th>bytes</th>"
                 "<th>zone</th><th>moved</th><th>answered</th></tr>%s</table></body>"
                 % (len(rows), len(rows), time.strftime("%Y-%m-%d %H:%M:%S"),
                    elapsed / 60.0, timeouts, chk, rws))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
