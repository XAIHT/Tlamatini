# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
r"""
ASK-EXECS REGRESSION SUITE — the Proceed/Deny permission scheme, end to end.
===========================================================================

WHY THIS FILE EXISTS
--------------------
Angela, 2026-07-14, live on the frozen build:

    "I had to push in Deny, 'cause the denial was already done."

She cancelled a Multi-Turn run while a Proceed/Deny prompt was open. The backend
denied it and stopped the run correctly — but the MODAL STAYED ON HER SCREEN and
she was forced to answer a question that had already been answered. The dialog is
`modal:true`, `closeOnEscape:false`, and its titlebar X is hidden, so clicking a
button was her ONLY way out. An ORPHAN MODAL.

Fixing that exposed two more:
  * a Cancel was reported (and SAVED to chat history) as "⛔ You denied the Tool…"
    — a decision she never made;
  * closing the tab while a prompt was open parked the executor thread FOREVER.

This suite locks all of that down, and is written to be READ AND EDITED BY ANGELA.


HOW TO RUN (visible, headed — headless is forbidden in this project)
--------------------------------------------------------------------
    python ask_execs_regression.py --base http://127.0.0.1:8100
    python ask_execs_regression.py --only S3            # just one scenario
    python ask_execs_regression.py --only S1,S3,S6      # a few
    python ask_execs_regression.py --list               # show the matrix and exit

It asks for the password in the console (getpass) — it is never stored, never put
on a command line, never printed.


HOW TO ADD A SCENARIO (this is the part you'll want)
----------------------------------------------------
1. Write a function `def s10_my_thing(page): ...`
2. Use the helpers: `send`, `wait_prompt`, `click_proceed`, `click_deny`,
   `cancel_run`, `prompt_open`, `wait_idle`, `answer_text`, `shot`, `check`.
3. Register it in SCENARIOS below with an id and a one-line description.
That's it — `--only` and the report pick it up automatically.


WHAT ACTUALLY PROMPTS  (read this before writing a scenario!)
-------------------------------------------------------------
Ask-Execs prompts only for the tools in `mcp_agent.py::_ASK_EXECS_REQUIRED_TOOLS`.
Angela's policy (2026-07-14) — she chose tiers A + B + D, and deliberately NOT C:

  PROMPTS (ask first):
    * command / script runners — Executer, Pythonxer, SSHer, Kalier, Dockerer,
      Kuberneter, SQLer, Mongoxer, Gitter, Jenkinser, PSer, J-Decompiler
    * A  destroys/overwrites data — Deleter, Mover, File-Creator, Editor,
         De-Compresser, unzip_file
    * B  reaches real people      — Emailer, Whatsapper, Telegrammer, Zavuerer
    * D  remote systems / network — SCPer, Apirer, Nmapper, Discoverer, Crawler

  NEVER PROMPTS (on purpose):
    * C  desktop UI + hardware — Keyboarder, Mouser, Windower, Playwrighter,
         STM32er, ESP32er, Arduiner, ESPHomer, Blenderer, Unrealer.
         Angela: "I need the AI moves fast and they are operations of visible
         proceding" — you SEE them happen, so a prompt buys nothing.
    * read-only / observational tools, the management-polling helpers, crypto,
      and invoke_skill.

==> The scenarios below drive `chat_agent_executer` because it is the simplest
    gated tool with a checkable side effect (an echo).
==> If you write a scenario for a TIER-C agent, NO PROMPT WILL EVER APPEAR and it
    will hang — that is correct behaviour, not a bug.
==> The gate itself is pinned by `agent/test_ask_execs_allowlist.py`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import getpass
import json
import os
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:  # pragma: no cover
    print(f"!!! Playwright is required: {exc}")
    sys.exit(2)

try:
    from PIL import ImageGrab
except Exception:  # pragma: no cover
    ImageGrab = None


# ── The page contract. If the UI changes, fix it HERE and nowhere else. ──────
SEL = {
    "login_user": "#id_username",
    "login_pass": "#id_password",
    "login_submit": "form button[type=submit]",
    "chat_input": "#chat-message-input",
    "chat_submit": "#chat-message-submit",           # doubles as the Cancel button
    "bot_message": "#chat-log .message.bot-message",
    "spinner": "#wait-spinner",
    "clean_history": "#clean-history",
    "t_multi_turn": "#multi-turn-enabled",
    "t_exec_report": "#exec-report-enabled",
    "t_ask_execs": "#ask-execs-enabled",
    "t_acpx": "#acpx-enabled",
    "t_internet": "#internetEnabled",
    # The Ask-Execs Proceed/Deny prompt (jQuery-UI dialog)
    "perm_dialog": "#exec-permission-dialog-message",
    "perm_proceed": '.exec-permission-dialog-wrapper .ui-dialog-buttonpane button:has-text("Proceed")',
    "perm_deny": '.exec-permission-dialog-wrapper .ui-dialog-buttonpane button:has-text("Deny")',
    # The generic confirmation dialog (used by Cancel and Clean-history)
    "confirm_continue": '.ui-dialog-buttonpane button:has-text("Continue")',
    # Results
    "exec_table": "table.exec-report-table",
    "denied_banner": ".exec-denied-title, .exec-denied-sub",
}

# The frozen install's log. Some assertions are made against the SERVER's own words,
# not the browser — a UI that lies cannot fool them.
FROZEN_LOG = r"C:\Tlamatini\tlamatini.log"

RESULTS: list[dict] = []
SHOTS: list[str] = []
OUT: Path
_PAGE = None


# ── plumbing ────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    print(f"[{_dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def shot(name: str) -> None:
    """Full-DESKTOP screenshot (taskbar clock visible), with Chrome raised first —
    a photo that does not show the thing under test proves nothing."""
    if _PAGE is not None:
        try:
            _PAGE.bring_to_front()
            time.sleep(0.35)
        except Exception:
            pass
    p = OUT / f"{len(SHOTS):02d}_{name}.png"
    if ImageGrab is not None:
        try:
            ImageGrab.grab(all_screens=True).save(p)
        except Exception as exc:
            log(f"(screenshot failed: {exc})")
    SHOTS.append(p.name)


def check(scenario: str, name: str, passed: bool, detail: str) -> None:
    RESULTS.append({"scenario": scenario, "check": name, "pass": bool(passed), "detail": detail})
    log(("   PASS  " if passed else "   FAIL  ") + f"[{scenario}] {name} — {detail}")


def read_log() -> str:
    try:
        with open(FROZEN_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def log_since(offset: int) -> str:
    """Only the log written AFTER `offset` bytes — so a scenario never reads
    another scenario's evidence. Always take `mark = log_size()` before acting."""
    try:
        with open(FROZEN_LOG, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0)
            return fh.read()[offset:]
    except Exception:
        return ""


def log_size() -> int:
    return len(read_log())


# ── page helpers (use these when you write your own scenario) ────────────────
def btn(page) -> str:
    try:
        return (page.inner_text(SEL["chat_submit"]) or "").strip()
    except Exception:
        return "?"


def is_busy(page) -> bool:
    try:
        return bool(page.eval_on_selector(SEL["chat_input"], "el => el.readOnly")) \
            or page.query_selector(SEL["spinner"]) is not None
    except Exception:
        return False


def wait_idle(page, timeout=240) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if btn(page).lower() == "send" and not is_busy(page):
            return True
        time.sleep(0.3)
    return False


# The app REJECTS a message if the RAG chain is still (re)building — the reply is
# "Agent is not ready. Please try again later." This happens on a slow boot (e.g. the
# External MCPs connecting) or right after a chain rebuild. We must WAIT for real
# readiness and RE-SEND, or every scenario waits forever for a prompt that never comes.
NOT_READY_MARKERS = (
    "agent is not ready",
    "still loading",
    "please wait a moment and try again",
)
READY_MARKER = "your agent is ready"


def agent_not_ready(page) -> bool:
    txts = bot_texts(page)
    if not txts:
        return False
    last = txts[-1].lower()
    return any(m in last for m in NOT_READY_MARKERS)


def wait_agent_ready(page, timeout=300) -> bool:
    """Idle button AND the last bot line is NOT a 'not ready' banner."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if btn(page).lower() == "send" and not is_busy(page) and not agent_not_ready(page):
            return True
        time.sleep(0.5)
    return False


def send(page, text: str, retries: int = 4) -> None:
    """Send a prompt, and RE-SEND if the app rejects it with 'Agent is not ready'."""
    for _ in range(retries):
        wait_agent_ready(page, timeout=300)
        page.fill(SEL["chat_input"], text)
        page.click(SEL["chat_submit"])
        # Give the server a moment to either accept (button -> Cancel / busy) or
        # reject (a 'not ready' banner appears while the button stays 'Send').
        time.sleep(3)
        if agent_not_ready(page):
            log("   (agent was not ready — waiting for it to finish loading, then re-sending)")
            wait_agent_ready(page, timeout=300)
            continue
        return
    log("   !! agent stayed 'not ready' after several retries — sending anyway")


def prompt_open(page) -> bool:
    """Is the Proceed/Deny modal currently VISIBLE?"""
    try:
        el = page.query_selector(SEL["perm_dialog"])
        return bool(el and el.is_visible())
    except Exception:
        return False


def wait_prompt(page, timeout=120) -> bool:
    """Block until the Ask-Execs Proceed/Deny modal appears."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if prompt_open(page):
            return True
        time.sleep(0.25)
    return False


def wait_prompt_gone(page, timeout=20) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not prompt_open(page):
            return True
        time.sleep(0.25)
    return False


def click_proceed(page) -> None:
    page.click(SEL["perm_proceed"])


def click_deny(page) -> None:
    page.click(SEL["perm_deny"])


def cancel_run(page) -> bool:
    """Press the chat button while it reads 'Cancel', then confirm 'Continue'.

    NOTE: while the permission modal is open, the jQuery-UI overlay can swallow a
    real mouse click on the chat button. We therefore dispatch the click directly on
    the element — which is exactly what a user achieves when the overlay is absent
    (this app loads jquery-ui.js WITHOUT its theme CSS, so today no real overlay is
    painted). If you ever add the jQuery-UI theme, the user would be TRAPPED in the
    prompt with no way to cancel — that is a real hazard worth its own scenario.
    """
    if btn(page).lower() != "cancel":
        return False
    try:
        page.eval_on_selector(SEL["chat_submit"], "el => el.click()")
    except Exception:
        page.click(SEL["chat_submit"])
    try:
        page.wait_for_selector(SEL["confirm_continue"], timeout=10_000)
        page.click(SEL["confirm_continue"])
        return True
    except Exception:
        return False


def toggle(page, key: str, want: bool) -> None:
    sel = SEL[key]
    try:
        page.wait_for_selector(sel, timeout=15_000)
        if page.is_disabled(sel):
            return
        if page.is_checked(sel) != want:
            page.click(sel)
    except Exception as exc:
        log(f"(toggle {key}->{want} failed: {exc})")


def bot_texts(page) -> list[str]:
    try:
        return [t for t in page.eval_on_selector_all(
            SEL["bot_message"], "els => els.map(e => e.innerText)") if t]
    except Exception:
        return []


def answer_text(page) -> str:
    """Everything Tlamatini has said, lowercased — for content assertions."""
    return "\n".join(bot_texts(page)).lower()


def clean_history(page) -> None:
    try:
        page.click(SEL["clean_history"])
        page.wait_for_selector(SEL["confirm_continue"], timeout=8000)
        page.click(SEL["confirm_continue"])
        time.sleep(2)
        # Clean-history triggers a chain REBUILD; wait for real readiness so the next
        # scenario's send() isn't rejected with 'Agent is not ready'.
        wait_agent_ready(page, timeout=300)
    except Exception as exc:
        log(f"(clean history skipped: {exc})")


# ═══════════════════════════════════════════════════════════════════════════
#  THE SCENARIOS.  One function each. Edit freely.
# ═══════════════════════════════════════════════════════════════════════════

def s1_proceed_runs_the_tool(page) -> None:
    """S1 — PROCEED must actually run the tool.

    The happy path. If this breaks, Ask-Execs is useless: the user says yes and
    nothing happens.
    """
    clean_history(page)
    send(page, "Run chat_agent_executer with script='echo TLM_S1_OK'. END-RESPONSE")
    if not wait_prompt(page):
        check("S1", "the Proceed/Deny prompt appears", False, "no modal within 120 s")
        return
    check("S1", "the Proceed/Deny prompt appears", True, "modal is open")
    shot("S1_prompt")
    click_proceed(page)
    check("S1", "the modal closes on Proceed", wait_prompt_gone(page), "prompt dismissed")
    done = wait_idle(page, timeout=240)
    txt = answer_text(page)
    check("S1", "the run completes", done, "controls returned to 'Send'")
    check("S1", "the tool REALLY ran", "tlm_s1_ok" in txt,
          "the echo output is in the answer" if "tlm_s1_ok" in txt else "TLM_S1_OK not found")
    check("S1", "no red 'Execution interrupted' banner",
          page.query_selector(SEL["denied_banner"]) is None, "no denial banner on a Proceed")
    shot("S1_done")


def s2_deny_halts_the_chain(page) -> None:
    """S2 — DENY must halt the whole chain and show the red banner.

    A denial is not a skip: nothing further may run, and the user must be told,
    permanently (the banner survives a page reload).
    """
    clean_history(page)
    send(page, "Run chat_agent_executer with script='echo TLM_S2_A', then run "
               "chat_agent_executer with script='echo TLM_S2_B'. END-RESPONSE")
    if not wait_prompt(page):
        check("S2", "the prompt appears", False, "no modal within 120 s")
        return
    shot("S2_prompt")
    click_deny(page)
    wait_prompt_gone(page)
    done = wait_idle(page, timeout=240)
    txt = answer_text(page)
    check("S2", "the run ends", done, "controls returned")
    check("S2", "the denied tool did NOT run", "tlm_s2_a" not in txt,
          "no echo output" if "tlm_s2_a" not in txt else "THE DENIED TOOL RAN — critical")
    check("S2", "the SECOND tool never ran either (chain halted)", "tlm_s2_b" not in txt,
          "chain stopped at the denial" if "tlm_s2_b" not in txt else "the chain continued past a DENY")
    banner = page.query_selector(SEL["denied_banner"]) is not None
    check("S2", "the red 'Execution interrupted' banner is shown", banner,
          "banner present" if banner else "no banner — the user is not told")
    check("S2", "no second prompt appeared", not prompt_open(page), "only one decision was asked")
    shot("S2_denied")


def s3_cancel_while_prompt_open(page) -> None:
    """S3 — ⭐ THE REGRESSION ANGELA HIT ⭐

    Cancel the run WHILE the Proceed/Deny prompt is open.

    Required behaviour:
      (a) the modal DISMISSES ITSELF — she is never asked to decide something the
          backend already decided (this is the orphan-modal bug);
      (b) the tool NEVER runs (fail-safe: a cancel resolves the prompt to deny);
      (c) she is NOT told "you denied it" — she CANCELLED, she did not deny;
      (d) the button returns to 'Send' and never flips back.
    """
    clean_history(page)
    mark = log_size()
    send(page, "Run chat_agent_executer with script='echo TLM_S3_SHOULD_NOT_RUN'. END-RESPONSE")
    if not wait_prompt(page):
        check("S3", "the prompt appears", False, "no modal within 120 s")
        return
    check("S3", "the prompt appears", True, "modal is open — now cancelling WITHOUT touching it")
    shot("S3_prompt_open")

    if not cancel_run(page):
        check("S3", "cancel accepted", False, "could not press Cancel/Continue")
        return
    check("S3", "cancel accepted", True, "Cancel + Continue")

    gone = wait_prompt_gone(page, timeout=15)
    check("S3", "★ the orphan modal DISMISSES ITSELF", gone,
          "the prompt closed on its own — no double decision"
          if gone else "THE MODAL IS STILL UP — Angela would have to answer a dead question")
    shot("S3_after_cancel")

    wait_idle(page, timeout=120)
    txt = answer_text(page)
    check("S3", "the tool NEVER ran", "tlm_s3_should_not_run" not in txt,
          "no echo output" if "tlm_s3_should_not_run" not in txt
          else "THE TOOL RAN AFTER A CANCEL — critical safety failure")
    lied = "you denied" in txt
    check("S3", "she does NOT claim 'you denied' (the user CANCELLED)", not lied,
          "truthful cancel message" if not lied else "she says the user denied it — a lie")
    tail = log_since(mark)
    denied_ok = "cancel detected; denying" in tail or "USER CANCELLED" in tail
    check("S3", "the server honoured the cancel", denied_ok,
          "log shows the cancel resolved the prompt" if denied_ok else "no cancel evidence in the log")
    check("S3", "the button is back to 'Send'", btn(page).lower() == "send", f"button = {btn(page)!r}")


def s4_runtime_relax_auto_proceeds(page) -> None:
    """S4 — Unchecking "Ask Execs" MID-RUN must release the pending prompt.

    This is the escape hatch when the user gets tired of confirming: uncheck the box
    while a prompt is up → it auto-PROCEEDS (not denies) and the run continues.
    (Distinct from S3, where the answer must be deny.)
    """
    clean_history(page)
    send(page, "Run chat_agent_executer with script='echo TLM_S4_RELAXED'. END-RESPONSE")
    if not wait_prompt(page):
        check("S4", "the prompt appears", False, "no modal within 120 s")
        return
    shot("S4_prompt")
    toggle(page, "t_ask_execs", False)        # uncheck MID-RUN — do not touch the modal
    gone = wait_prompt_gone(page, timeout=15)
    check("S4", "the prompt closes when Ask-Execs is unchecked mid-run", gone,
          "modal auto-closed" if gone else "modal still up after the relax")
    done = wait_idle(page, timeout=240)
    txt = answer_text(page)
    check("S4", "the run CONTINUES (auto-proceed, not deny)", "tlm_s4_relaxed" in txt,
          "the tool ran" if "tlm_s4_relaxed" in txt else "the tool did NOT run — the relax denied instead of proceeding")
    check("S4", "the run completes", done, "controls returned")
    toggle(page, "t_ask_execs", True)         # put it back for the next scenario
    shot("S4_relaxed")


def s5_next_request_is_not_blocked(page) -> None:
    """S5 — after a cancelled prompt, the NEXT request must work normally.

    Two ways this could break:
      * a leftover modal overlay swallowing clicks on the chat input;
      * the permanent cancel latch leaking into the new (higher-epoch) run.
    """
    clean_history(page)
    send(page, "Run chat_agent_executer with script='echo TLM_S5_FIRST'. END-RESPONSE")
    if not wait_prompt(page):
        check("S5", "first prompt appears", False, "no modal")
        return
    cancel_run(page)
    wait_prompt_gone(page, timeout=15)
    wait_idle(page, timeout=120)

    # …and now, WITHOUT reloading the page, a fresh request:
    send(page, "Run chat_agent_executer with script='echo TLM_S5_SECOND'. END-RESPONSE")
    got = wait_prompt(page, timeout=120)
    check("S5", "the NEXT request still prompts (nothing is stuck)", got,
          "a fresh prompt appeared" if got else "no prompt — the dead run poisoned the next one")
    if not got:
        return
    click_proceed(page)
    wait_idle(page, timeout=240)
    txt = answer_text(page)
    check("S5", "the NEXT request's tool runs", "tlm_s5_second" in txt,
          "the second tool ran" if "tlm_s5_second" in txt else "the second tool did not run")
    check("S5", "the cancelled tool still never ran", "tlm_s5_first" not in txt,
          "first tool stayed dead" if "tlm_s5_first" not in txt else "the CANCELLED tool ran later — critical")
    shot("S5_next_request")


def s6_button_never_sticks_on_cancel(page) -> None:
    """S6 — the button must never STICK on 'Cancel' (the opposite of Angela's bug).

    If a cancel leaves the worker parked on a permission prompt, the UI would stay
    busy forever. Watch it for 30 s.
    """
    clean_history(page)
    send(page, "Run chat_agent_executer with script='echo TLM_S6'. END-RESPONSE")
    if not wait_prompt(page):
        check("S6", "the prompt appears", False, "no modal")
        return
    cancel_run(page)
    relapses = []
    t0 = time.time()
    while time.time() - t0 < 30:
        if btn(page).lower() == "cancel":
            relapses.append(f"t+{time.time()-t0:.1f}s")
        time.sleep(0.25)
    check("S6", "the button never sticks/relapses to 'Cancel' (30 s watch)", not relapses,
          "stayed on 'Send'" if not relapses else f"relapsed at {relapses[:3]}")
    shot("S6_watch")


SCENARIOS = {
    "S1": ("Proceed runs the tool", s1_proceed_runs_the_tool),
    "S2": ("Deny halts the chain + red banner", s2_deny_halts_the_chain),
    "S3": ("★ Cancel while the prompt is open (Angela's bug)", s3_cancel_while_prompt_open),
    "S4": ("Uncheck Ask-Execs mid-run → auto-proceed", s4_runtime_relax_auto_proceeds),
    "S5": ("The next request is not blocked", s5_next_request_is_not_blocked),
    "S6": ("The button never sticks on 'Cancel'", s6_button_never_sticks_on_cancel),
}


# ── report ──────────────────────────────────────────────────────────────────
def write_report(base: str) -> None:
    passed = sum(1 for r in RESULTS if r["pass"])
    (OUT / "results.json").write_text(json.dumps(
        {"base": base, "passed": passed, "total": len(RESULTS), "results": RESULTS,
         "shots": SHOTS, "finished_at": _dt.datetime.now().isoformat()},
        indent=2), encoding="utf-8")
    rows = "\n".join(
        f"<tr class='{'p' if r['pass'] else 'f'}'><td>{'PASS' if r['pass'] else 'FAIL'}</td>"
        f"<td>{r['scenario']}</td><td>{r['check']}</td><td>{r['detail']}</td></tr>"
        for r in RESULTS)
    imgs = "\n".join(f"<figure><img src='{s}'><figcaption>{s}</figcaption></figure>" for s in SHOTS)
    (OUT / "SUMMARY.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>Ask-Execs regression</title>
<style>body{{font:15px system-ui;background:#15161a;color:#eee;padding:24px}}
h1{{color:#55BBAA}} table{{border-collapse:collapse;width:100%}}
td{{padding:7px 10px;border-bottom:1px solid #333;vertical-align:top}}
tr.p td:first-child{{color:#4ade80;font-weight:700}}
tr.f td:first-child{{color:#f87171;font-weight:700}}
img{{max-width:100%;border:1px solid #333;border-radius:6px}}
figcaption{{color:#888;font-size:12px}}</style>
<h1>Ask-Execs — {passed}/{len(RESULTS)} checks passed</h1>
<p>{base} · {_dt.datetime.now():%Y-%m-%d %H:%M}</p>
<table>{rows}</table><h2>Evidence</h2>{imgs}""", encoding="utf-8")


def main() -> int:
    global OUT, _PAGE
    ap = argparse.ArgumentParser(description="Ask-Execs Proceed/Deny regression suite")
    ap.add_argument("--base", default=os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8100"))
    ap.add_argument("--user", default=os.environ.get("TLAMATINI_USER", "angela"))
    ap.add_argument("--only", default="", help="comma-separated scenario ids, e.g. S3 or S1,S3")
    ap.add_argument("--list", action="store_true", help="print the scenario matrix and exit")
    args = ap.parse_args()

    if args.list:
        print("\nAsk-Execs scenarios:\n")
        for sid, (desc, _) in SCENARIOS.items():
            print(f"  {sid}  {desc}")
        print("\nRun one with:  python ask_execs_regression.py --only S3\n")
        return 0

    picked = [s.strip().upper() for s in args.only.split(",") if s.strip()] or list(SCENARIOS)
    unknown = [s for s in picked if s not in SCENARIOS]
    if unknown:
        print(f"!!! unknown scenario(s): {unknown}. Try --list")
        return 2

    base = args.base.rstrip("/")
    OUT = Path(__file__).parent / "reports" / f"askexecs_{_dt.datetime.now():%Y%m%d_%H%M%S}"
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 74)
    print("  ASK-EXECS regression  —  Proceed / Deny / Cancel")
    print(f"  target    : {base}")
    print(f"  scenarios : {', '.join(picked)}")
    print(f"  report    : {OUT}")
    print("=" * 74)
    password = os.environ.get("TLAMATINI_PASS") or getpass.getpass(
        f"Angela, password for '{args.user}' (never stored, never shown): ")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        _PAGE = page

        log("Logging in …")
        page.goto(base + "/", wait_until="domcontentloaded")
        page.fill(SEL["login_user"], args.user)
        page.fill(SEL["login_pass"], password)
        page.click(SEL["login_submit"])
        page.wait_for_load_state("domcontentloaded")
        page.goto(base + "/agent/agent/", wait_until="domcontentloaded")
        page.wait_for_selector(SEL["chat_input"], timeout=60_000)
        log("Waiting for the agent to be READY (chain build + External MCPs) …")
        if not wait_agent_ready(page, timeout=420):
            log("   !! agent never reported ready within 7 min — proceeding, scenarios will retry")

        # The pinned configuration for EVERY Ask-Execs scenario.
        log("Toggles: Multi-Turn ON, Exec report ON, Ask Execs ON, ACPX/Internet OFF")
        toggle(page, "t_multi_turn", True)
        toggle(page, "t_exec_report", True)
        toggle(page, "t_ask_execs", True)
        toggle(page, "t_acpx", False)
        toggle(page, "t_internet", False)
        shot("00_toggles")

        for sid in picked:
            desc, fn = SCENARIOS[sid]
            log(f"───── {sid}: {desc}")
            try:
                fn(page)
            except Exception as exc:
                check(sid, "harness", False, f"exception: {exc}")
                shot(f"{sid}_exception")
            wait_idle(page, timeout=120)

        write_report(base)
        passed = sum(1 for r in RESULTS if r["pass"])
        print("=" * 74)
        print(f"  RESULT: {passed}/{len(RESULTS)} checks passed")
        for r in RESULTS:
            print(("  PASS  " if r["pass"] else "  FAIL  ") + f"[{r['scenario']}] {r['check']}")
        print(f"  Report: {OUT / 'SUMMARY.html'}")
        print("=" * 74)
        try:
            input("  Press ENTER to close the browser… ")
        except Exception:
            pass
        ctx.close()
        browser.close()
    return 0 if all(r["pass"] for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
