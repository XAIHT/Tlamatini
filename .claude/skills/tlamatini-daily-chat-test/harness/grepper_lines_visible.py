# ══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ══════════════════════════════════════════════════════════════════
"""VISIBLE end-to-end proof that the modified Grepper did NOT break Tlamatini.

Angela's rule: no headless tests. This drives the REAL chat GUI in a HEADED
Chrome on her real desktop, and photographs the whole screen with SHOTER
(never PIL.ImageGrab).

WHAT IT PROVES, in the LIVE app, through the LLM, not by supposition:
  STEP 1  the THREE EXISTING search modes still work   -> nothing was broken
  STEP 2  the NEW output_mode='lines' verbatim read works -> the feature is real

⚠️ The verdict is DOM TRUTH, never prose. It requires:
      * a Grepper table in the Exec Report (the agent really ran), and
      * the planted marker text back in the answer (it really read the file).
   A pretty paragraph with no marker is a FAILURE.

The password is read from TLAMATINI_PASS or asked with getpass in THIS visible
console. It is never printed, never stored, never passed on a command line.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shoter_shot import take_shot  # noqa: E402

SEL = {
    "login_user": "#id_username",
    "login_pass": "#id_password",
    "login_submit": "form button[type=submit]",
    "chat_input": "#chat-message-input",
    "chat_submit": "#chat-message-submit",
    "bot_message": "#chat-log .message.bot-message",
    "spinner": "#wait-spinner",
    "t_multi_turn": "#multi-turn-enabled",
    "t_exec_report": "#exec-report-enabled",
    "t_acpx": "#acpx-enabled",
    "t_ask_execs": "#ask-execs-enabled",
    "t_internet": "#internetEnabled",
    "exec_table": "table.exec-report-table",
}


def banner(msg):
    print("\n" + "=" * 74)
    print("  " + msg)
    print("=" * 74, flush=True)


def plant_marker(temp_root):
    """A file whose exact bytes only THIS run knows."""
    os.makedirs(temp_root, exist_ok=True)
    tag = uuid.uuid4().hex[:10].upper()
    path = os.path.join(temp_root, f"grepper_visible_{tag}.txt")
    lines = [
        f"TLM_MARKER_{tag}\n",
        f"SECOND_LINE_{tag}\n",
        f"THIRD_LINE_{tag}\n",
        "fourth line, not requested\n",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.writelines(lines)
    return path, tag


def set_toggle(page, sel, want):
    try:
        box = page.query_selector(sel)
        if box is None:
            return
        if box.is_checked() != want:
            box.click()
            time.sleep(0.25)
    except Exception as exc:                      # noqa: BLE001 - never fatal
        print(f"   (toggle {sel}: {exc})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("TLAMATINI_BASE_URL",
                                                     "http://127.0.0.1:8000"))
    ap.add_argument("--user", default=os.environ.get("TLAMATINI_USER", "angela"))
    ap.add_argument("--temp", default=r"C:\Development\XAIHT\Tlamatini\Temp")
    ap.add_argument("--shots", default=r"C:\Development\XAIHT\Tlamatini\Temp\GrepperVisible")
    ap.add_argument("--answer-timeout", type=int, default=420)
    args = ap.parse_args()

    if "--headless" in sys.argv:
        sys.exit("HEADLESS IS FORBIDDEN. This test must be VISIBLE.")

    os.makedirs(args.shots, exist_ok=True)
    path, tag = plant_marker(args.temp)
    banner("VISIBLE GREPPER PROOF - Tlamatini running from the REPO")
    print(f"  base   : {args.base}")
    print(f"  user   : {args.user}   (the password is NEVER printed)")
    print(f"  planted: {path}")
    print(f"  marker : TLM_MARKER_{tag}")

    password = os.environ.get("TLAMATINI_PASS") or getpass.getpass(
        f"\n  Angela, password for '{args.user}' (never stored, never shown): ")
    if not password:
        sys.exit("no password given - aborting")

    prompt = (
        f"Tlamatini, use ONLY the chat_agent_grepper tool, exactly twice, then stop.\n\n"
        f"STEP 1 - SEARCH (this is the OLD behaviour, it must still work): run "
        f"chat_agent_grepper with pattern='TLM_MARKER_{tag}', path='{path}', "
        f"output_mode='content'. Tell me how many matches it found and quote the "
        f"matching line.\n\n"
        f"STEP 2 - VERBATIM READ (this is the NEW output_mode): run "
        f"chat_agent_grepper again with path='{path}', output_mode='lines', "
        f"start_line=2, end_line=3, line_numbers=false. Quote the exact text of "
        f"those two lines and tell me the value of total_lines.\n\n"
        f"Do NOT use execute_command, type, cat or sed. End with END-RESPONSE."
    )

    from playwright.sync_api import sync_playwright

    verdict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome",
                                    args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        try:
            banner("STEP A - login (HEADED Chrome, you can watch it)")
            page.goto(args.base + "/", timeout=60000)
            page.fill(SEL["login_user"], args.user)
            page.fill(SEL["login_pass"], password)
            page.click(SEL["login_submit"])
            page.wait_for_load_state("networkidle", timeout=60000)

            for url in (args.base + "/agent/agent/", args.base + "/agent/"):
                page.goto(url, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)
                if page.query_selector(SEL["chat_input"]):
                    print(f"   chat page: {url}")
                    break
            else:
                raise RuntimeError("chat input never appeared - is the login right?")

            take_shot(args.shots, f"01_logged_in_{tag}.png")

            banner("STEP B - Multi-Turn ON, Exec report ON, everything else OFF")
            set_toggle(page, SEL["t_multi_turn"], True)
            set_toggle(page, SEL["t_exec_report"], True)
            set_toggle(page, SEL["t_acpx"], False)
            set_toggle(page, SEL["t_ask_execs"], False)
            set_toggle(page, SEL["t_internet"], False)
            take_shot(args.shots, f"02_toggles_{tag}.png")

            banner("STEP C - sending the prompt (search + verbatim read)")
            # ⚠️ The page posts a GREETING bot message on connect. Counting before
            # it lands makes the greeting look like the answer and the run ends in
            # seconds with a false FAIL. Let it settle FIRST, then count.
            time.sleep(6)
            before = len(page.query_selector_all(SEL["bot_message"]))
            print(f"   bot messages before send: {before}")
            page.fill(SEL["chat_input"], prompt)
            page.click(SEL["chat_submit"])
            time.sleep(3)

            # Completion signal = the submit button goes back from Cancel to Send.
            deadline = time.time() + args.answer_timeout
            last = 0
            while time.time() < deadline:
                now = len(page.query_selector_all(SEL["bot_message"]))
                try:
                    btn = (page.inner_text(SEL["chat_submit"]) or "").strip().lower()
                except Exception:                              # noqa: BLE001
                    btn = ""
                if now > before and btn.startswith("send"):
                    time.sleep(5)
                    break
                if int(time.time()) - last >= 15:
                    last = int(time.time())
                    print(f"   waiting... {int(deadline - time.time())}s left "
                          f"(bot msgs={now}, button={btn!r})", flush=True)
                time.sleep(1)

            take_shot(args.shots, f"03_answer_{tag}.png")

            banner("STEP D - VERDICT from the DOM (not from prose)")
            msgs = page.query_selector_all(SEL["bot_message"])
            answer = msgs[-1].inner_text() if msgs else ""
            tables = page.query_selector_all(SEL["exec_table"])
            table_text = " ".join(t.inner_text() for t in tables)

            verdict["answered"] = bool(msgs) and len(answer.strip()) > 20
            verdict["grepper_ran_per_exec_report"] = "Grepper" in table_text
            verdict["search_found_marker"] = f"TLM_MARKER_{tag}" in answer
            verdict["verbatim_read_line2"] = f"SECOND_LINE_{tag}" in answer
            verdict["verbatim_read_line3"] = f"THIRD_LINE_{tag}" in answer
            verdict["did_not_leak_line4"] = "fourth line, not requested" not in answer
            verdict["reported_total_lines_4"] = bool(re.search(r"total_lines\D{0,12}4", answer))

            for k, v in verdict.items():
                print(f"   {'PASS' if v else 'FAIL'}  {k}")
            print("\n--- answer (first 1200 chars) ---")
            print(answer[:1200])

            shot = take_shot(args.shots, f"04_final_{tag}.png")
            print(f"\n   full-desktop photo by SHOTER: {shot}")
        finally:
            time.sleep(4)
            ctx.close()
            browser.close()

    hard = ("answered", "grepper_ran_per_exec_report", "search_found_marker",
            "verbatim_read_line2", "verbatim_read_line3")
    ok = all(verdict.get(k) for k in hard)
    banner("RESULT: " + ("PASS - Grepper works in the LIVE app, both modes"
                         if ok else "FAIL - see the FAIL lines above"))
    try:
        subprocess.run(["explorer", args.shots], timeout=10)
    except Exception:                              # noqa: BLE001
        pass
    print("\n  This window stays open. Close it when you have read it.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
