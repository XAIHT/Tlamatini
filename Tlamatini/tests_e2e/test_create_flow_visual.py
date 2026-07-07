#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
"""
Visible (HEADED) Playwright end-to-end suite for the 2026-07-06 Create-Flow
overhaul. Drives a real Chromium on Angela's desktop against the running
Tlamatini server and validates, over the LIVE WebSocket wire:

  REQ 1 — the whole-answer SUCCESS/FAILURE classifier is GONE:
          the final `agent_message` frame carries NO `answer_success` key.
  REQ 2 — the "Create Flow" button appears whenever Multi-Turn ran with
          >=1 SUCCESSFUL agent (no verdict gate), and the downloaded `.flw`
          contains ONLY the successfully-executed agents (failed executions
          are dropped). For pure-Q&A answers (no tools) the button is ABSENT.
  REQ 3 — the "Exec report" checkbox is enabled ONLY while Multi-Turn is
          checked (disabled + greyed otherwise), mirroring "Ask Execs".

Run it (from the repo, with the server already up):

    set TLAMATINI_USER=angela
    set TLAMATINI_PASS=********
    python Tlamatini/tests_e2e/test_create_flow_visual.py

Config via environment:
    BASE_URL          default http://127.0.0.1:8000
    TLAMATINI_USER    login username (required)
    TLAMATINI_PASS    login password (required)
    NUM_QUESTIONS     how many of the 100-question bank to run (default 100)
    HEADLESS          "1" to run headless (default 0 == VISIBLE, as Angela wants)
    ANSWER_TIMEOUT_S  per-question wait for the answer (default 180)
    DOWNLOAD_SAMPLE   how many button-bearing answers to actually click +
                      download + validate the .flw for (default 12; 0 = none,
                      -1 = every one). Every downloaded flow is checked for the
                      "only successful agents" invariant.
    REPORT_DIR        where to write the dated report (default <repo>/Temp)

This suite is DELIBERATELY headed so Angela can watch it. Only SAFE agents
are exercised (Executer echo, File-Creator into Temp, Grepper/Globber reads).
"""

import json
import os
import re
import sys
import time
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:  # pragma: no cover
    print("playwright is not installed in this Python. `pip install playwright` "
          "and `playwright install chromium`.", file=sys.stderr)
    raise


# ── Config ───────────────────────────────────────────────────────────
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("TLAMATINI_USER", "")
PASS = os.environ.get("TLAMATINI_PASS", "")
NUM_QUESTIONS = int(os.environ.get("NUM_QUESTIONS", "100"))
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
ANSWER_TIMEOUT_S = int(os.environ.get("ANSWER_TIMEOUT_S", "180"))
DOWNLOAD_SAMPLE = int(os.environ.get("DOWNLOAD_SAMPLE", "12"))
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = os.environ.get("REPORT_DIR") or os.path.join(_REPO_ROOT, "Temp")

# Display-name → canonical DB name, mirroring _DISPLAY_TO_CANONICAL in
# agent_page_chat.js so we can compare the downloaded flow's node text to the
# successful tool calls captured off the wire.
_DISPLAY_TO_CANONICAL = {
    "Send Email": "Emailer",
    "Summarize Text": "Summarizer",
    "Move File": "Mover",
    "Kyber Deciph": "Kyber-DeCipher",
    "Kyber Keygen": "Kyber-KeyGen",
    "Kyber Cipher": "Kyber-Cipher",
}


def _canonical(display):
    return _DISPLAY_TO_CANONICAL.get(display, display)


def _derive_display(entry):
    """Reproduce the frontend's display-name derivation for a tool-call entry."""
    dn = entry.get("agent_display_name")
    if dn:
        return dn
    raw = (entry.get("tool_name") or "Unknown").replace("_", " ")
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), raw)


# ── The 100-question bank ────────────────────────────────────────────
# Each item: (prompt, expect_button)
#   expect_button True  → the answer must show "Create Flow" (>=1 agent ran OK)
#   expect_button False → pure Q&A, no tool ran, so the button must be ABSENT
def _build_question_bank():
    q = []
    tmp = os.path.join(_REPO_ROOT, "Temp").replace("\\", "/")

    # 1) Single safe Executer echo (expect button, one Executer node)
    for i in range(30):
        q.append((
            f"Using ONLY the Executer, run this exact shell command and report its "
            f"output: echo flowtest-echo-{i:03d}. Do nothing else. End with END-RESPONSE.",
            True,
        ))
    # 2) File-Creator into Temp (expect button)
    for i in range(20):
        q.append((
            f"Using ONLY the File Creator, create the file {tmp}/flowtest_{i:03d}.txt "
            f"with the content 'hello flowtest {i:03d}'. End with END-RESPONSE.",
            True,
        ))
    # 3) Grepper read-only over this very file (expect button)
    for i in range(12):
        q.append((
            f"Using ONLY the Grepper, search for the regex 'REQ {(i % 3) + 1}' inside the "
            f"file {os.path.abspath(__file__).replace(chr(92), '/')} and report the matches. "
            f"End with END-RESPONSE.",
            True,
        ))
    # 4) Globber read-only (expect button)
    for i in range(8):
        q.append((
            f"Using ONLY the Globber, list the *.py files under "
            f"{_REPO_ROOT.replace(chr(92), '/')}/tests_e2e (run #{i:02d}). End with END-RESPONSE.",
            True,
        ))
    # 5) Two safe agents in one request (expect button, >=2 nodes)
    for i in range(10):
        q.append((
            f"Do BOTH, in order, using ONLY Tlamatini agents: (1) with the Executer run "
            f"'echo two-step-{i:02d}', then (2) with the File Creator create "
            f"{tmp}/flowtest_two_{i:02d}.txt containing 'two {i:02d}'. End with END-RESPONSE.",
            True,
        ))
    # 6) Mixed success + FAILURE — the failed call must be dropped from the flow.
    for i in range(10):
        q.append((
            f"Using ONLY the Executer, first run 'echo good-{i:02d}' (this succeeds), then "
            f"run 'flowtest_nonexistent_command_{i:02d}' (this will FAIL). Report both. "
            f"End with END-RESPONSE.",
            True,
        ))
    # 7) Pure Q&A — NO tool should run, so NO Create-Flow button.
    qa = [
        "What is the capital of France? Answer in one sentence. End with END-RESPONSE.",
        "Explain in two sentences what a hash map is. End with END-RESPONSE.",
        "What does the acronym HTTP stand for? End with END-RESPONSE.",
        "Give me a one-line definition of recursion. End with END-RESPONSE.",
        "What is 17 multiplied by 3? Just the number. End with END-RESPONSE.",
        "Name three primary colors. End with END-RESPONSE.",
        "In one sentence, what is the boiling point of water at sea level? End with END-RESPONSE.",
        "What is the plural of 'cactus'? End with END-RESPONSE.",
        "Define 'idempotent' in one short sentence. End with END-RESPONSE.",
        "What year did the first moon landing happen? End with END-RESPONSE.",
    ]
    for text in qa:
        q.append((text, False))

    # Scale to NUM_QUESTIONS by cycling the safe base bank. Each item is an
    # INDEPENDENT chat request, so repeats are harmless; we stamp a per-cycle
    # marker so every run is a distinct operation. Supports the 1000-question
    # visible flow-generation soak (and the self-healing under real load).
    if NUM_QUESTIONS <= len(q):
        return q[:NUM_QUESTIONS]
    out = []
    n = 0
    while len(out) < NUM_QUESTIONS:
        prompt, expect = q[n % len(q)]
        cyc = n // len(q)
        if cyc > 0 and "END-RESPONSE." in prompt:
            prompt = prompt.replace("END-RESPONSE.", f"(pass {cyc:03d}) END-RESPONSE.", 1)
        out.append((prompt, expect))
        n += 1
    return out


# ── Small DOM helpers ────────────────────────────────────────────────
def _set_checkbox(page, selector, want):
    """Tick/untick a checkbox if enabled; returns (changed, disabled)."""
    el = page.query_selector(selector)
    if el is None:
        return (False, True)
    disabled = el.is_disabled()
    if disabled:
        return (False, True)
    checked = el.is_checked()
    if checked != want:
        el.click()
    return (checked != want, False)


def _login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    # Already authenticated? The login form has #id_username.
    if page.query_selector("#id_username"):
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("button[type=submit]")
        page.wait_for_load_state("domcontentloaded")
    # NOTE: agent.urls is mounted under the "agent/" prefix in the project
    # router, and agent/urls.py maps the chat view at path('agent/', ...), so
    # the chat page is /agent/agent/. Plain /agent/ is the login page.
    page.goto(BASE_URL + "/agent/agent/", wait_until="domcontentloaded")
    page.wait_for_selector("#chat-message-input", timeout=30000)


def _wait_for_answer(page, prior_bot_count):
    """Wait until the multi-turn/one-shot run has FULLY finished.

    A Multi-Turn answer arrives as TWO assistant WebSocket frames: an
    intermediate one (message+username only) and the FINAL one that carries
    ``multi_turn_used`` + ``tool_calls_log`` (the data the Create-Flow button
    needs). The chat input stays disabled until that final frame lands, so the
    reliable completion signal is "a NEW bot message rendered AND the input is
    re-enabled" — then a settle so the final frame + the button's async agent
    validation resolve. (The old version broke on the intermediate frame /
    stale history and checked the button before it existed.)"""
    deadline = time.time() + ANSWER_TIMEOUT_S
    while time.time() < deadline:
        count = page.eval_on_selector_all(".message.bot-message", "els => els.length")
        enabled = not page.eval_on_selector("#chat-message-input", "el => el.disabled")
        if count > prior_bot_count and enabled:
            time.sleep(3.0)  # let the FINAL frame + Create-Flow validation resolve
            if not page.eval_on_selector("#chat-message-input", "el => el.disabled"):
                return True
        time.sleep(0.4)
    return False


def _latest_bot_has_create_flow(page):
    return page.eval_on_selector_all(
        ".message.bot-message",
        "els => { const last = els[els.length-1]; "
        "return !!(last && last.querySelector('.create-flow')); }",
    )


# ── Main ─────────────────────────────────────────────────────────────
def main():
    if not USER or not PASS:
        print("ERROR: set TLAMATINI_USER and TLAMATINI_PASS in the environment.",
              file=sys.stderr)
        return 2

    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"create_flow_visual_report_{stamp}.md")
    downloads_dir = os.path.join(REPORT_DIR, f"create_flow_downloads_{stamp}")
    os.makedirs(downloads_dir, exist_ok=True)

    bank = _build_question_bank()
    results = []          # per-question dicts
    gating = {}           # REQ 3 results
    downloaded = 0

    # Capture the final agent_message frame per turn off the WebSocket so we can
    # (a) assert no answer_success key (REQ 1) and (b) know the successful agents
    # to compare against the downloaded .flw (REQ 2).
    ws_frames = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 40)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        def _on_ws(ws):
            ws.on("framereceived", lambda payload: ws_frames.append(payload))
        page.on("websocket", _on_ws)

        # window.prompt (filename) → auto-accept with a deterministic name.
        page.on("dialog", lambda d: d.accept("flowtest"))

        _login(page)
        # Let the page finish initializing (applyStoredMultiTurnState hydrates
        # the toolbar checkboxes from sessionStorage). Toggling BEFORE that
        # settle lets a late hydration silently reset the checkbox we just set.
        time.sleep(1.5)

        # ── REQ 3: Exec-report checkbox gating (frontend only) ──
        # Multi-Turn OFF at load → exec-report disabled.
        mt = page.query_selector("#multi-turn-enabled")
        if mt.is_checked():
            mt.click()
        time.sleep(0.3)
        gating["exec_report_disabled_when_multiturn_off"] = \
            page.eval_on_selector("#exec-report-enabled", "el => el.disabled")
        # Tick Multi-Turn → exec-report enabled.
        page.click("#multi-turn-enabled")
        time.sleep(0.3)
        gating["exec_report_enabled_when_multiturn_on"] = \
            (not page.eval_on_selector("#exec-report-enabled", "el => el.disabled"))
        # Untick Multi-Turn → exec-report disabled again.
        page.click("#multi-turn-enabled")
        time.sleep(0.3)
        gating["exec_report_disabled_again_when_multiturn_off"] = \
            page.eval_on_selector("#exec-report-enabled", "el => el.disabled")
        page.screenshot(path=os.path.join(downloads_dir, "req3_checkbox_gating.png"))

        # Turn Multi-Turn back ON (+ Exec Report ON) for the question run.
        page.click("#multi-turn-enabled")
        time.sleep(0.2)
        _set_checkbox(page, "#exec-report-enabled", True)

        # ── REQ 1 & 2: the 100-question run ──
        for idx, (prompt, expect_button) in enumerate(bank):
            prior = page.eval_on_selector_all(".message.bot-message", "els => els.length")
            frame_hi = len(ws_frames)
            page.fill("#chat-message-input", prompt)
            page.click("#chat-message-submit")
            ok = _wait_for_answer(page, prior)

            rec = {"i": idx, "prompt": prompt[:90], "expect_button": expect_button,
                   "answered": ok, "button": None, "answer_success_absent": None,
                   "flow_ok": None, "note": ""}

            if not ok:
                rec["note"] = "TIMEOUT waiting for answer"
                results.append(rec)
                continue

            # Find the final Tlamatini frame produced after we submitted.
            final = None
            for raw in ws_frames[frame_hi:]:
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                if d.get("username") == "Tlamatini" and d.get("multi_turn_used"):
                    final = d
            if final is not None:
                rec["answer_success_absent"] = ("answer_success" not in final)  # REQ 1

            # REAL contract oracle: an agent actually ran successfully this turn
            # IFF the final frame carries >=1 successful tool call. The LLM is
            # NOT deterministic about whether it invokes the agent for a given
            # prompt, so we validate button-present == agent-actually-ran rather
            # than the hardcoded expect_button (kept only as a report hint).
            successful = [_canonical(_derive_display(e))
                          for e in ((final or {}).get("tool_calls_log") or [])
                          if e.get("success")]
            agent_ran_ok = len(successful) >= 1
            rec["agent_ran_ok"] = agent_ran_ok

            # Detect the Create-Flow button among THIS turn's NEW bot messages.
            # A transient "…is being processed…please wait" placeholder can be
            # the LAST bot message, so checking only the last one misses the
            # button, which lives on the actual answer message.
            has_button = page.evaluate(
                """(prior) => {
                    const els = Array.from(document.querySelectorAll('.message.bot-message'));
                    return els.slice(prior).some(e => !!e.querySelector('.create-flow'));
                }""", prior)
            rec["button"] = has_button

            # REQ 2: the button must be present IFF an agent ran successfully.
            if agent_ran_ok and not has_button:
                rec["note"] = "agent ran OK but NO Create-Flow button shown"
            elif (not agent_ran_ok) and has_button:
                rec["note"] = "Create-Flow button shown but NO agent ran successfully"
            elif expect_button and not agent_ran_ok:
                rec["note"] = "LLM did not invoke the agent this turn (non-deterministic; contract still OK)"

            # Optionally download + validate the .flw (only successful agents).
            want_dl = has_button and (DOWNLOAD_SAMPLE < 0 or downloaded < DOWNLOAD_SAMPLE)
            if want_dl and final is not None:
                try:
                    with page.expect_download(timeout=20000) as di:
                        page.evaluate(
                            """(prior) => {
                                const els = Array.from(document.querySelectorAll('.message.bot-message'));
                                const m = els.slice(prior).find(e => e.querySelector('.create-flow'));
                                if (m) m.querySelector('.create-flow').click();
                            }""", prior)
                    dl = di.value
                    fpath = os.path.join(downloads_dir, f"q{idx:03d}.flw")
                    dl.save_as(fpath)
                    with open(fpath, "r", encoding="utf-8") as fh:
                        flow = json.load(fh)
                    nodes = [n.get("text") for n in flow.get("nodes", [])]
                    middle = [n for n in nodes if n not in ("Starter", "Ender")]
                    # Invariant: the flow's middle nodes are EXACTLY the successful
                    # agents (order-preserving) — failed executions never appear.
                    rec["flow_ok"] = (middle == successful) and len(middle) >= 1
                    rec["note"] += (f" | flow_nodes={middle} successful={successful}"
                                    if not rec["flow_ok"] else "")
                    downloaded += 1
                except PWTimeout:
                    rec["flow_ok"] = False
                    rec["note"] += " | download timed out"
                except Exception as exc:  # noqa: BLE001
                    rec["flow_ok"] = False
                    rec["note"] += f" | download/validate error: {exc}"

            results.append(rec)
            print(f"[{idx+1}/{len(bank)}] answered={ok} button={rec['button']} "
                  f"as_absent={rec['answer_success_absent']} flow_ok={rec['flow_ok']} "
                  f"{rec['note']}")

        page.screenshot(path=os.path.join(downloads_dir, "final_state.png"))
        context.close()
        browser.close()

    _write_report(report_path, gating, results, downloaded)
    print(f"\nReport → {report_path}")
    # Exit non-zero if any hard assertion failed.
    hard_fail = _count_failures(gating, results)
    return 0 if hard_fail == 0 else 1


def _count_failures(gating, results):
    fails = 0
    if not gating.get("exec_report_disabled_when_multiturn_off"):
        fails += 1
    if not gating.get("exec_report_enabled_when_multiturn_on"):
        fails += 1
    if not gating.get("exec_report_disabled_again_when_multiturn_off"):
        fails += 1
    for r in results:
        if not r["answered"]:
            fails += 1
            continue
        if r["answer_success_absent"] is False:  # REQ 1 violated
            fails += 1
        # REQ 2 real contract: button present IFF an agent actually ran OK.
        if r.get("agent_ran_ok") and not r["button"]:
            fails += 1
        if (not r.get("agent_ran_ok")) and r["button"]:
            fails += 1
        if r["flow_ok"] is False:
            fails += 1
    return fails


def _write_report(path, gating, results, downloaded):
    answered = sum(1 for r in results if r["answered"])
    btn_ok = sum(1 for r in results
                 if r["answered"] and (r["button"] == bool(r.get("agent_ran_ok"))))
    agent_runs = sum(1 for r in results if r["answered"] and r.get("agent_ran_ok"))
    as_absent = sum(1 for r in results if r["answer_success_absent"] is True)
    flow_checked = sum(1 for r in results if r["flow_ok"] is not None)
    flow_ok = sum(1 for r in results if r["flow_ok"] is True)
    fails = _count_failures(gating, results)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Create-Flow visible E2E report — {datetime.now().isoformat(timespec='seconds')}\n\n")
        fh.write(f"- Questions run: **{len(results)}**, answered: **{answered}**\n")
        fh.write("\n## REQ 3 — Exec-report checkbox gated on Multi-Turn\n")
        for k, v in gating.items():
            fh.write(f"- `{k}`: {'PASS' if v else 'FAIL'}\n")
        fh.write("\n## REQ 1 — no answer_success on the wire\n")
        fh.write(f"- final frames with NO `answer_success`: **{as_absent}/{answered}**\n")
        fh.write("\n## REQ 2 — Create-Flow button gate + successful-only flow\n")
        fh.write(f"- button present == an agent actually ran OK: **{btn_ok}/{answered}** "
                 f"(the REAL contract)\n")
        fh.write(f"- turns where the LLM actually invoked an agent: **{agent_runs}/{answered}** "
                 f"(informational — model non-determinism, not pass/fail)\n")
        fh.write(f"- flows downloaded + validated (successful-only invariant): "
                 f"**{flow_ok}/{flow_checked}**\n")
        fh.write(f"\n## HARD FAILURES: **{fails}**  →  {'✅ ALL GREEN' if fails == 0 else '❌ SEE BELOW'}\n\n")
        fh.write("| # | expect_btn | answered | agent_ran | button | as_absent | flow_ok | note |\n")
        fh.write("|---|---|---|---|---|---|---|---|\n")
        for r in results:
            fh.write(f"| {r['i']} | {r['expect_button']} | {r['answered']} | "
                     f"{r.get('agent_ran_ok')} | {r['button']} | {r['answer_success_absent']} | "
                     f"{r['flow_ok']} | {r['note'].strip()} |\n")


if __name__ == "__main__":
    sys.exit(main())
