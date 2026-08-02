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
HARD-CANCEL REGRESSION TEST  —  visible, headed, on Angela's real desktop.

THE BUG BEING PROVEN DEAD (2026-07-14):
    Cancel a Multi-Turn run -> a few seconds later Tlamatini resumed BY HERSELF,
    the Send button flipped back to "Cancel", and it repeated FOREVER. Every
    Cancel click just fed the loop.

RULES HONOURED (Angela's, non-negotiable):
  * HEADED real Chrome (headless is FORBIDDEN). Drives the REAL chat GUI.
  * FULL-SCREEN desktop screenshots (whole desktop, taskbar clock visible).
  * NEVER records a stale / transient / timed-out answer as a pass.
  * The password is typed by Angela into THIS console (getpass) — never stored,
    never passed on a command line, never seen by the assistant.

Usage (from a VISIBLE foreground PowerShell window):
    python cancel_regression.py --base http://127.0.0.1:8100
"""

from __future__ import annotations

import argparse
import datetime as _dt
import getpass
import json
import os
import re
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


# ── DOM contract (from harness/config.py — one place to fix on a UI change) ──
SEL = {
    "login_user": "#id_username",
    "login_pass": "#id_password",
    "login_submit": "form button[type=submit]",
    "chat_input": "#chat-message-input",
    "chat_submit": "#chat-message-submit",
    "chat_log": "#chat-log",
    "bot_message": "#chat-log .message.bot-message",
    "spinner": "#wait-spinner",
    "t_multi_turn": "#multi-turn-enabled",
    "t_acpx": "#acpx-enabled",
    "t_exec_report": "#exec-report-enabled",
    "t_ask_execs": "#ask-execs-enabled",
    "t_internet": "#internetEnabled",
    "clean_history": "#clean-history",
    "dialog_continue": '.ui-dialog-buttonpane button:has-text("Continue")',
    "create_flow": "button.create-flow, .create-flow",
    "exec_table": "table.exec-report-table",
    "exec_perm_dialog": "#exec-permission-dialog-message",
}

FROZEN_LOG = r"C:\Tlamatini\tlamatini.log"

RESULTS: list[dict] = []
SHOTS: list[str] = []
OUT: Path


def stamp() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{stamp()}] {msg}", flush=True)


_PAGE = None   # set in main(); lets shot() raise Chrome before grabbing


def shot(name: str) -> str:
    """FULL DESKTOP screenshot — the whole screen, taskbar clock visible.

    Chrome is RAISED TO THE FRONT first. Without this the grab captures whatever
    window happens to be on top (an editor, a chat client) and the 'evidence' is
    worthless — a photo that does not show the thing under test proves nothing.
    """
    if _PAGE is not None:
        try:
            _PAGE.bring_to_front()
            time.sleep(0.35)
        except Exception:
            pass
    path = OUT / f"{len(SHOTS):02d}_{name}.png"
    if ImageGrab is not None:
        try:
            ImageGrab.grab(all_screens=True).save(path)
        except Exception as exc:  # pragma: no cover
            log(f"(screenshot failed: {exc})")
    SHOTS.append(path.name)
    return str(path)


def record(test: str, passed: bool, detail: str) -> None:
    RESULTS.append({"test": test, "pass": bool(passed), "detail": detail})
    log(("   ✅ PASS  " if passed else "   ❌ FAIL  ") + test + " — " + detail)


# ── page helpers ────────────────────────────────────────────────────────────
def btn_text(page) -> str:
    try:
        return (page.inner_text(SEL["chat_submit"]) or "").strip()
    except Exception:
        return "?"


def is_busy(page) -> bool:
    try:
        ro = page.eval_on_selector(SEL["chat_input"], "el => el.readOnly")
        sp = page.query_selector(SEL["spinner"]) is not None
        return bool(ro) or bool(sp)
    except Exception:
        return False


def bot_texts(page) -> list[str]:
    try:
        return [t.strip() for t in page.eval_on_selector_all(
            SEL["bot_message"], "els => els.map(e => e.innerText)") if t and t.strip()]
    except Exception:
        return []


_TACTIC_RE = re.compile(r"^[^A-Za-z]*Tactic\s*[#']")


def tactic_lines(page) -> list[str]:
    """Live self-healing status frames — the frames that used to re-arm the
    Cancel button. Anchored exactly like isSelfHealingStatusMessage()."""
    out = []
    for t in bot_texts(page):
        first = t.strip().splitlines()[0] if t.strip() else ""
        if _TACTIC_RE.match(first):
            out.append(first[:90])
    return out


def set_toggle(page, key: str, want: bool) -> None:
    sel = SEL[key]
    try:
        page.wait_for_selector(sel, timeout=15_000)
        if page.is_disabled(sel):
            return
        if page.is_checked(sel) != want:
            page.click(sel)
        assert page.is_checked(sel) == want, f"{key} did not take the value {want}"
    except Exception as exc:
        log(f"(toggle {key} -> {want} failed: {exc})")


def send(page, text: str) -> None:
    page.fill(SEL["chat_input"], text)
    page.click(SEL["chat_submit"])


def confirm_dialog(page, timeout=10_000) -> bool:
    """The Cancel confirmation ('Are you sure you want to cancel now?') → Continue."""
    try:
        page.wait_for_selector(SEL["dialog_continue"], timeout=timeout)
        page.click(SEL["dialog_continue"])
        return True
    except Exception as exc:
        log(f"(confirm dialog not found: {exc})")
        return False


def click_cancel(page) -> bool:
    """Press the Send/Cancel button while it reads 'Cancel', then confirm."""
    if btn_text(page).lower() != "cancel":
        log(f"(button is '{btn_text(page)}', not 'Cancel' — cannot cancel)")
        return False
    page.click(SEL["chat_submit"])
    return confirm_dialog(page)


def wait_busy(page, timeout=40) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if btn_text(page).lower() == "cancel" or is_busy(page):
            return True
        time.sleep(0.2)
    return False


def wait_idle(page, timeout=300) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if btn_text(page).lower() == "send" and not is_busy(page):
            return True
        time.sleep(0.3)
    return False


def log_tail(marker_from: float | None = None) -> str:
    try:
        with open(FROZEN_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()[-400_000:]
    except Exception:
        return ""


# The line tools._launch_wrapped_chat_agent prints the moment a wrapped agent is
# ACTUALLY launched. Cancelling before this fires only ever tests a model-step
# cancel — the run would have ZERO tool calls, so "the work already done is
# preserved" would be vacuous. We wait for a REAL tool to be in flight.
LAUNCH_MARK = "===== LAUNCH START ====="


def launch_count() -> int:
    return log_tail().count(LAUNCH_MARK)


def wait_for_tool_launch(baseline: int, timeout: int = 240) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if launch_count() > baseline:
            log(f"   (a tool really launched after {time.time() - t0:.0f}s — it is now mid-flight)")
            return True
        time.sleep(0.5)
    return False


# ── THE WATCH — the heart of this test ──────────────────────────────────────
def watch_after_cancel(page, seconds: int, label: str) -> dict:
    """After a Cancel, the UI must STAY calm. For `seconds`:
         * the button must NEVER read 'Cancel' again by itself
         * the input must never go read-only again
         * NO new '🔁 Tactic #…' status frame may appear
    (The dying run's final answer MAY still arrive — that is allowed and
     expected; it re-enables, it does not re-disable.)"""
    base_tactics = len(tactic_lines(page))
    t0 = time.time()
    relapses: list[str] = []
    new_tactics: list[str] = []
    marks = {30: False, 90: False, seconds: False}

    while True:
        el = time.time() - t0
        if el >= seconds:
            break
        bt = btn_text(page).lower()
        busy = is_busy(page)
        if bt == "cancel" or busy:
            relapses.append(f"t+{el:.1f}s button='{btn_text(page)}' busy={busy}")
        tl = tactic_lines(page)
        if len(tl) > base_tactics:
            for line in tl[base_tactics:]:
                if line not in new_tactics:
                    new_tactics.append(line)
            base_tactics = len(tl)
        for at in sorted(marks):
            if not marks[at] and el >= at:
                marks[at] = True
                shot(f"{label}_watch_t{int(at)}s")
                log(f"   … t+{int(at)}s  button='{btn_text(page)}'  busy={busy}  "
                    f"relapses={len(relapses)}  new-tactic-frames={len(new_tactics)}")
        time.sleep(0.25)

    return {"relapses": relapses, "new_tactics": new_tactics}


# ── the tests ───────────────────────────────────────────────────────────────
LONG_CHAIN = (
    "Run EXACTLY these three tools, one after another, in this order, and nothing else. "
    "1) chat_agent_executer with script='ping -n 30 127.0.0.1'  "
    "2) chat_agent_globber with pattern='**/*.md' and path='C:\\Development\\Tlamatini\\docs'  "
    "3) chat_agent_grepper with pattern='cancel' and path='C:\\Development\\Tlamatini\\docs' and glob='*.md'  "
    "Then give a one-line summary. END-RESPONSE"
)


def test_1_cancel_during_long_tool_chain(page) -> None:
    log("TEST 1 — Cancel during a long tool chain, then watch for 3 minutes.")
    base_launches = launch_count()
    send(page, LONG_CHAIN)
    if not wait_busy(page):
        record("T1 run started", False, "the run never went busy — cannot test a cancel")
        return
    # Wait for a tool to be REALLY running before we cancel — otherwise we would
    # only be testing a model-step cancel (zero tool calls) and the "work is
    # preserved" checks below would be meaningless.
    if not wait_for_tool_launch(base_launches, timeout=240):
        record("T1 a tool is genuinely mid-flight before we cancel", False,
               "no wrapped agent launched within 240 s — cannot test a mid-tool cancel")
        return
    record("T1 a tool is genuinely mid-flight before we cancel", True,
           "chat_agent_executer launched (the 30 s ping is running)")
    time.sleep(6)                        # be well INSIDE the ping
    shot("T1_mid_run")

    if not click_cancel(page):
        record("T1 cancel clicked", False, "could not click/confirm Cancel")
        return
    t_cancel = time.time()
    record("T1 cancel clicked", True, "Cancel + Continue confirmed")
    time.sleep(1.0)
    shot("T1_just_after_cancel")

    # (a) the controls must come back straight away
    back = btn_text(page).lower() == "send"
    record("T1 button returns to 'Send' immediately", back,
           f"button = '{btn_text(page)}' one second after the cancel")

    # (b) THE BUG: it must not come back to life
    w = watch_after_cancel(page, 180, "T1")
    record("T1 button NEVER flips back to 'Cancel' (180 s watch)",
           not w["relapses"],
           "no relapse in 3 minutes" if not w["relapses"]
           else f"RELAPSED {len(w['relapses'])}×: {w['relapses'][:3]}")
    record("T1 NO new '🔁 Tactic #…' frame after the cancel",
           not w["new_tactics"],
           "zero tactic frames" if not w["new_tactics"]
           else f"{len(w['new_tactics'])} tactic frames: {w['new_tactics'][:3]}")

    # (c) the backend really stopped, and did NOT start the next tools
    tail = log_tail()
    stopped = "USER CANCELLED" in tail
    record("T1 backend logged the cancel stop", stopped,
           "'MultiTurnToolAgentExecutor: USER CANCELLED' found in tlamatini.log"
           if stopped else "no USER CANCELLED line in the frozen log")

    page_text = "\n".join(bot_texts(page)).lower()
    no_more = ("globber" not in page_text) and ("grepper" not in page_text)
    record("T1 the tools AFTER the cancel never ran", no_more,
           "no Globber/Grepper rows in the answer" if no_more
           else "Globber/Grepper appear — a tool ran AFTER the cancel")

    # (d) the work already done is preserved
    has_table = page.query_selector(SEL["exec_table"]) is not None
    has_flow = page.query_selector(SEL["create_flow"]) is not None
    record("T1 work already done is preserved (Exec report)", has_table,
           "Exec report table present" if has_table else "no Exec report table")
    record("T1 Create Flow button still offered", has_flow,
           "Create Flow present" if has_flow else "no Create Flow button")
    shot("T1_final_state")
    log(f"   (cancel→settled: {time.time() - t_cancel:.0f}s)")


def test_2_next_request_works(page) -> None:
    log("TEST 2 — the NEXT request after a cancel must work normally.")
    send(page, "Use chat_agent_globber with pattern='*.md' and path='C:\\Development\\Tlamatini\\docs' "
               "and tell me how many files matched. END-RESPONSE")
    started = wait_busy(page)
    record("T2 the new run re-arms the busy UI", started,
           "button went to 'Cancel' — the cancel latch did NOT leak into the new run"
           if started else "the new run never went busy (the latch LEAKED — regression!)")
    done = wait_idle(page, timeout=240)
    record("T2 the new run completes", done,
           "answer arrived and the controls returned" if done else "timed out")
    shot("T2_next_request")


def test_3_cancel_during_a_model_step(page) -> None:
    log("TEST 3 — Cancel during a MODEL step (no tools yet): must be truthful.")
    before = set(bot_texts(page))
    send(page, "Explain in three paragraphs what Tlamatini is and how her Multi-Turn mode works. END-RESPONSE")
    if not wait_busy(page):
        record("T3 run started", False, "never went busy")
        return
    time.sleep(3)
    if not click_cancel(page):
        record("T3 cancel clicked", False, "could not cancel")
        return
    record("T3 cancel clicked", True, "cancelled while she was thinking")
    time.sleep(6)
    new = [t for t in bot_texts(page) if t not in before]
    blob = "\n".join(new).lower()
    lied = "transient network" in blob or "backend is currently unavailable" in blob
    record("T3 no LYING 'transient network error' fallback", not lied,
           "no fabricated outage message" if not lied
           else "she still claims a transient network error after a user cancel")
    w = watch_after_cancel(page, 60, "T3")
    record("T3 no relapse after a model-step cancel", not w["relapses"] and not w["new_tactics"],
           "calm for 60 s" if not w["relapses"] and not w["new_tactics"]
           else f"relapses={len(w['relapses'])} tactics={len(w['new_tactics'])}")
    shot("T3_model_step_cancel")


def test_4_three_cancels_in_a_row(page) -> None:
    log("TEST 4 — three cancels in a row (Angela's 'no matter how many times').")
    ok = True
    for i in (1, 2, 3):
        base = launch_count()
        send(page, "Run chat_agent_executer with script='ping -n 25 127.0.0.1'. END-RESPONSE")
        if not wait_busy(page):
            record(f"T4 cancel #{i}", False, "run never started")
            ok = False
            break
        if not wait_for_tool_launch(base, timeout=240):
            record(f"T4 cancel #{i}", False, "no tool launched — nothing to cancel mid-flight")
            ok = False
            break
        time.sleep(4)
        if not click_cancel(page):
            record(f"T4 cancel #{i}", False, "could not cancel")
            ok = False
            break
        w = watch_after_cancel(page, 40, f"T4_{i}")
        good = not w["relapses"] and not w["new_tactics"]
        record(f"T4 cancel #{i} stays cancelled (40 s watch)", good,
               "calm" if good else f"relapses={len(w['relapses'])} tactics={len(w['new_tactics'])}")
        ok = ok and good
        wait_idle(page, timeout=90)
    shot("T4_three_cancels")
    record("T4 every cancel behaved identically", ok,
           "3/3 cancels stuck" if ok else "at least one cancel misbehaved")


def test_5_ask_execs_cancel(page) -> None:
    log("TEST 5 — Cancel while the Ask-Execs Proceed/Deny modal is open.")
    set_toggle(page, "t_ask_execs", True)
    send(page, "Run chat_agent_executer with script='echo hard-cancel-ask-execs'. END-RESPONSE")
    try:
        page.wait_for_selector(SEL["exec_perm_dialog"], state="visible", timeout=60_000)
    except Exception:
        record("T5 permission modal appeared", False, "no Ask-Execs modal within 60 s")
        set_toggle(page, "t_ask_execs", False)
        return
    record("T5 permission modal appeared", True, "Proceed/Deny prompt is open")
    shot("T5_permission_modal")

    t0 = time.time()
    cancelled = click_cancel(page)
    if not cancelled:
        # while the modal is open the submit button may be covered — force it
        page.eval_on_selector(SEL["chat_submit"], "el => el.click()")
        confirm_dialog(page)
    freed = wait_idle(page, timeout=60)
    record("T5 the worker is NOT left frozen (returns to 'Send')", freed,
           f"controls returned in {time.time() - t0:.0f}s" if freed
           else "STUCK on 'Cancel' — the worker parked on the permission prompt")
    set_toggle(page, "t_ask_execs", False)
    shot("T5_after_ask_execs_cancel")


# ── report ──────────────────────────────────────────────────────────────────
def write_report(base_url: str) -> None:
    passed = sum(1 for r in RESULTS if r["pass"])
    total = len(RESULTS)
    (OUT / "results.json").write_text(
        json.dumps({"base_url": base_url, "passed": passed, "total": total,
                    "results": RESULTS, "shots": SHOTS,
                    "finished_at": _dt.datetime.now().isoformat()}, indent=2),
        encoding="utf-8")

    rows = "\n".join(
        f"<tr class='{'p' if r['pass'] else 'f'}'><td>{'PASS' if r['pass'] else 'FAIL'}</td>"
        f"<td>{r['test']}</td><td>{r['detail']}</td></tr>" for r in RESULTS)
    imgs = "\n".join(f"<figure><img src='{s}'><figcaption>{s}</figcaption></figure>" for s in SHOTS)
    (OUT / "SUMMARY.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>Hard Cancel — regression</title>
<style>body{{font:15px system-ui;background:#15161a;color:#eee;padding:24px}}
h1{{color:#55BBAA}} table{{border-collapse:collapse;width:100%}}
td{{padding:7px 10px;border-bottom:1px solid #333;vertical-align:top}}
tr.p td:first-child{{color:#4ade80;font-weight:700}} tr.f td:first-child{{color:#f87171;font-weight:700}}
figure{{margin:18px 0}} img{{max-width:100%;border:1px solid #333;border-radius:6px}}
figcaption{{color:#888;font-size:12px}}</style>
<h1>Hard Cancel — {passed}/{total} passed</h1>
<p>{base_url} · frozen Tlamatini · {_dt.datetime.now():%Y-%m-%d %H:%M}</p>
<table>{rows}</table><h2>Full-desktop evidence</h2>{imgs}""", encoding="utf-8")


def main() -> int:
    global OUT, _PAGE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8100"))
    ap.add_argument("--user", default=os.environ.get("TLAMATINI_USER", "angela"))
    args = ap.parse_args()
    base = args.base.rstrip("/")

    OUT = Path(__file__).parent / "reports" / f"cancel_{_dt.datetime.now():%Y%m%d_%H%M%S}"
    OUT.mkdir(parents=True, exist_ok=True)

    print("=" * 74)
    print("  HARD CANCEL — regression test against the FROZEN Tlamatini")
    print(f"  target : {base}")
    print(f"  user   : {args.user}")
    print(f"  report : {OUT}")
    print("=" * 74)
    password = os.environ.get("TLAMATINI_PASS") or getpass.getpass(
        f"Angela, type the password for '{args.user}' (it is never stored or shown): ")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, channel="chrome",
                                        args=["--start-maximized"])
        except Exception:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        _PAGE = page   # so every shot() raises Chrome before grabbing the desktop

        log(f"Logging in at {base} …")
        page.goto(base + "/", wait_until="domcontentloaded")
        page.fill(SEL["login_user"], args.user)
        page.fill(SEL["login_pass"], password)
        page.click(SEL["login_submit"])
        page.wait_for_load_state("domcontentloaded")
        page.goto(base + "/agent/agent/", wait_until="domcontentloaded")
        page.wait_for_selector(SEL["chat_input"], timeout=60_000)
        log("Waiting for the agent to finish loading …")
        wait_idle(page, timeout=300)

        log("Clearing chat history …")
        try:
            page.click(SEL["clean_history"])
            confirm_dialog(page)
            time.sleep(3)
            wait_idle(page, timeout=300)
        except Exception as exc:
            log(f"(clean history skipped: {exc})")

        log("Setting toggles: Multi-Turn ON, Exec report ON, ACPX/Ask-Execs/Internet OFF")
        set_toggle(page, "t_multi_turn", True)
        set_toggle(page, "t_exec_report", True)
        set_toggle(page, "t_acpx", False)
        set_toggle(page, "t_ask_execs", False)
        set_toggle(page, "t_internet", False)
        shot("00_toggles_ready")

        try:
            test_1_cancel_during_long_tool_chain(page)
            wait_idle(page, timeout=120)
            test_2_next_request_works(page)
            test_3_cancel_during_a_model_step(page)
            wait_idle(page, timeout=120)
            test_4_three_cancels_in_a_row(page)
            test_5_ask_execs_cancel(page)
        except Exception as exc:
            record("HARNESS", False, f"exception: {exc}")
            shot("99_exception")

        write_report(base)
        passed = sum(1 for r in RESULTS if r["pass"])
        print("=" * 74)
        print(f"  RESULT: {passed}/{len(RESULTS)} passed")
        for r in RESULTS:
            print(("  PASS  " if r["pass"] else "  FAIL  ") + r["test"])
        print(f"  Report: {OUT / 'SUMMARY.html'}")
        print("=" * 74)
        print("  The browser stays open so you can look. Close this window when done.")
        try:
            input("  Press ENTER to close the browser… ")
        except Exception:
            pass
        ctx.close()
        browser.close()
    return 0 if all(r["pass"] for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
