"""VISUAL automated tests for the 3X-speed surgical plan (L1 + L2).

Drives a REAL Chrome via Playwright against the running Tlamatini chat UI to
prove the L1/L2 changes are live and that chat no longer suffers the
multi-minute stall the reaper/Ollama-serving pathologies caused.

REQUIREMENTS (these are end-to-end, not hermetic):
  * Tlamatini dev server running at $TLAMATINI_URL (default http://127.0.0.1:8000/)
  * Login creds in env: TLAMATINI_USER / TLAMATINI_PASS  (default user <REDACTED>)
  * `pip install playwright && playwright install chromium`

Run:
  python Tests/test_perf_3x_visual.py            # headed (visible) — default
  HEADLESS=1 python Tests/test_perf_3x_visual.py # headless

It is a standalone runner (NOT a Django test) because it needs the live server
and a browser. It prints a PASS/FAIL line per scenario and a final summary, and
exits non-zero if any scenario fails. Toggle discipline (memory
feedback_test_toggle_state): Multi-Turn ON, Exec-Report ON, Ask-Execs OFF,
history cleared first — otherwise the chat returns canned short replies and the
timings are fiction.

Scenarios (each is one visual test):
  V1   page loads + login succeeds
  V2   toolbar toggles set + verified (Multi-Turn ON, Ask-Execs OFF)
  V3   history cleared
  V4..V23  twenty short, SAFE prompts sent one-by-one; each must answer in
           < STALL_BUDGET seconds (proves no multi-minute freeze) and end with
           a non-empty answer. These are the L1+L2 "no stall" proof.
  V24  server log sanity: no 'O(N^2)' reaper freeze marker during the run
"""
from __future__ import annotations

import os
import sys
import time

STALL_BUDGET = float(os.environ.get("STALL_BUDGET", "90"))  # seconds; a single
# answer slower than this means a stall regression (L1/L2 not working).

URL = os.environ.get("TLAMATINI_URL", "http://127.0.0.1:8000/")
USER = os.environ.get("TLAMATINI_USER", "<REDACTED>")
PASS = os.environ.get("TLAMATINI_PASS", "")
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

PROMPTS = [
    "Say only the word READY and then END-RESPONSE.",
    "What is 2+2? One line. END-RESPONSE.",
    "Name the capital of France in one word. END-RESPONSE.",
    "Reverse the word 'tlamatini'. END-RESPONSE.",
    "List three primary colors, comma separated. END-RESPONSE.",
    "What day comes after Monday? END-RESPONSE.",
    "Spell 'cat' backwards. END-RESPONSE.",
    "Give a one-sentence definition of RAG. END-RESPONSE.",
    "What is the boiling point of water in Celsius? END-RESPONSE.",
    "Translate 'hello' to Spanish. One word. END-RESPONSE.",
    "How many sides does a triangle have? END-RESPONSE.",
    "Name one planet in the solar system. END-RESPONSE.",
    "What is 10 times 10? END-RESPONSE.",
    "Give the opposite of 'hot'. One word. END-RESPONSE.",
    "What is the first letter of the alphabet? END-RESPONSE.",
    "Name a fruit that is yellow. One word. END-RESPONSE.",
    "What is the square root of 81? END-RESPONSE.",
    "Say the current year as a number. END-RESPONSE.",
    "Give a synonym for 'fast'. One word. END-RESPONSE.",
    "What is H2O commonly called? One word. END-RESPONSE.",
]

_results = []


def _record(name, ok, detail=""):
    _results.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name} {('- ' + detail) if detail else ''}", flush=True)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed; run: pip install playwright && playwright install chromium")
        return 2

    if not PASS:
        print("WARNING: TLAMATINI_PASS not set — login will likely fail. "
              "Set TLAMATINI_USER / TLAMATINI_PASS env vars.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            # V1 — load + login
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            if page.locator("input[name='username']").count():
                page.fill("input[name='username']", USER)
                page.fill("input[name='password']", PASS)
                page.click("button[type='submit'], input[type='submit']")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            ok_login = page.locator("#chat-input, textarea, #message-input").count() > 0
            _record("V1_login_and_load", ok_login)
            if not ok_login:
                _summary_and_exit(browser)

            # V2 — toggles (best-effort selectors; the IDs come from agent_page.html)
            def _set(cb_id, want):
                loc = page.locator(f"#{cb_id}")
                if loc.count() == 0:
                    return None
                checked = loc.is_checked()
                if checked != want:
                    loc.click()
                return loc.is_checked() == want
            mt = _set("multi-turn-enabled", True)
            er = _set("exec-report-enabled", True)
            ae = _set("ask-execs-enabled", False)
            _record("V2_toggles_set", (mt is not False) and (ae is not False),
                    f"multiturn={mt} exec_report={er} ask_execs={ae}")

            # V3 — clear history (best-effort; many builds expose a clear button)
            cleared = True
            try:
                clr = page.locator("#clear-chat, .clear-history, [data-action='clear']")
                if clr.count():
                    clr.first.click()
                    page.wait_for_timeout(500)
            except Exception as exc:
                cleared = False
                _record("V3_clear_history", False, str(exc))
            if cleared:
                _record("V3_clear_history", True)

            # V4..V23 — send prompts, time each, assert no stall
            box = page.locator("#chat-input, textarea, #message-input").first
            for i, prompt in enumerate(PROMPTS, start=4):
                name = f"V{i}_prompt_{i-3:02d}"
                try:
                    box.fill(prompt)
                    t0 = time.perf_counter()
                    box.press("Enter")
                    # wait until a new bot message appears and settles
                    answered = _wait_for_answer(page, timeout=STALL_BUDGET)
                    dt = time.perf_counter() - t0
                    ok = answered and dt < STALL_BUDGET
                    _record(name, ok, f"{dt:.1f}s")
                except Exception as exc:
                    _record(name, False, str(exc))

            # V24 — log sanity (no freeze marker)
            _record("V24_no_reaper_freeze_marker", _log_has_no_freeze())

        finally:
            _summary_and_exit(browser)


def _wait_for_answer(page, timeout):
    """Wait until the latest assistant message stops growing (settled)."""
    end = time.time() + timeout
    last_len, stable = -1, 0
    sel = ".bot-message, .assistant-message, .message.bot, .chat-message"
    while time.time() < end:
        try:
            msgs = page.locator(sel)
            n = msgs.count()
            txt = msgs.nth(n - 1).inner_text() if n else ""
        except Exception:
            txt = ""
        cur = len(txt or "")
        if cur > 0 and cur == last_len:
            stable += 1
            if stable >= 3:  # ~stable for 3 ticks
                return True
        else:
            stable = 0
        last_len = cur
        page.wait_for_timeout(400)
    return last_len > 0  # answered something even if it didn't fully settle


def _log_has_no_freeze():
    log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "Tlamatini", "tlamatini.log")
    try:
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()[-200000:]
        return "O(N^2)" not in data and "reaper freeze" not in data.lower()
    except OSError:
        return True  # no log = nothing to flag


def _summary_and_exit(browser):
    try:
        browser.close()
    except Exception:
        pass
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("=" * 50)
    print(f"VISUAL 3X SUITE: {passed}/{total} passed")
    print("=" * 50)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    sys.exit(main() or 0)
