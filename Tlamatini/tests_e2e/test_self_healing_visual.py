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
VISIBLE self-healing soak (Angela, 2026-07-06).

This is NOT a happy-path test. With env fault-injection ON, Tlamatini's model
steps are deliberately made to FAIL for real (hangs the watchdog must abandon +
transient errors), so we can SEE her:
  • announce each new tactic and retry (⚠️ / 🔁 / ⏱️ abandoning / ✅ recovered),
  • NEVER hang and NEVER discard work, and
  • still finish and still generate a flow from the agents that succeeded.

Prompts are RANDOM and of MIXED difficulty (easy ↔ hard, shuffled — including
the exact Monitor-Log chain that originally broke).

Server must be launched with, e.g.:
    set TLAMATINI_SELF_HEAL_FAULT_RATE=0.6
    set TLAMATINI_SELF_HEAL_FAULT_MODE=mix
    set TLAMATINI_LLM_STEP_TIMEOUT=6

Env knobs here: NUM_QUESTIONS (default 1000), HEADLESS (default 0 = visible),
SEED, ANSWER_TIMEOUT_S (default 300), DOWNLOAD_SAMPLE (default 30), BASE_URL,
TLAMATINI_USER, TLAMATINI_PASS.
"""

import json
import os
import random
import sys
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except Exception:  # noqa: BLE001
    print("playwright not installed. pip install playwright && playwright install chromium",
          file=sys.stderr)
    raise

import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.environ.get("TLAMATINI_USER", "")
PASS = os.environ.get("TLAMATINI_PASS", "")
NUM_QUESTIONS = int(os.environ.get("NUM_QUESTIONS", "1000"))
HEADLESS = os.environ.get("HEADLESS", "0") == "1"
SEED = int(os.environ.get("SEED", "1337"))
ANSWER_TIMEOUT_S = int(os.environ.get("ANSWER_TIMEOUT_S", "300"))
DOWNLOAD_SAMPLE = int(os.environ.get("DOWNLOAD_SAMPLE", "30"))
REPORT_DIR = os.environ.get("REPORT_DIR") or os.path.join(_REPO_ROOT, "Temp")

# Markers Tlamatini emits from the self-healing recovery ladder.
_HEAL_MARKERS = ("transient network error", "switching to a different tactic",
                 "Tactic #", "abandoning", "was taking too long", "🔁", "⏱️",
                 "recovered", "Recovered", "🛟", "leaner request", "MINIMAL request")
# The OLD lying failure text that must NEVER appear when agents actually ran.
_LIE_MARKERS = ("tool-calling backend is currently unavailable",
                "no tools were actually invoked", "No tools were actually invoked")


def _tmp():
    return os.path.join(_REPO_ROOT, "Temp").replace("\\", "/")


def _make_question(idx, rng):
    """Return (prompt, expect_agent, tier). Difficulty is RANDOM per question."""
    tmp = _tmp()
    tier = rng.choices(["easy", "medium", "hard"], weights=[5, 3, 2])[0]
    if tier == "easy":
        kind = rng.choice(["echo", "file", "grep", "glob", "qa"])
        if kind == "echo":
            return (f"Using ONLY the Executer, run this exact command and report its output: "
                    f"echo heal-{idx}. Do nothing else. End with END-RESPONSE.", True, tier)
        if kind == "file":
            return (f"Using ONLY the File Creator, create the file {tmp}/heal_{idx}.txt with the "
                    f"content 'healing test {idx}'. End with END-RESPONSE.", True, tier)
        if kind == "grep":
            here = os.path.abspath(__file__).replace(chr(92), "/")
            return (f"Using ONLY the Grepper, search for the regex 'Tlamatini' in the file "
                    f"{here} and report the matches. End with END-RESPONSE.", True, tier)
        if kind == "glob":
            return (f"Using ONLY the Globber, list the *.py files under "
                    f"{_REPO_ROOT.replace(chr(92), '/')}/tests_e2e. End with END-RESPONSE.", True, tier)
        return (rng.choice([
            "What is 17 times 4? Just the number. End with END-RESPONSE.",
            "In one sentence, what is a mutex? End with END-RESPONSE.",
            "Name three noble gases. End with END-RESPONSE.",
        ]), False, tier)
    if tier == "medium":
        if rng.random() < 0.5:
            return (f"Do BOTH, in order, using ONLY Tlamatini agents: (1) with the Executer run "
                    f"'echo two-{idx}', then (2) with the File Creator create {tmp}/two_{idx}.txt "
                    f"containing 'two {idx}'. End with END-RESPONSE.", True, tier)
        return (f"Using Tlamatini agents: first with the File Creator create {tmp}/find_{idx}.txt "
                f"with the content 'needle-{idx} in a haystack', then with the Grepper search for "
                f"'needle-{idx}' inside that same file. End with END-RESPONSE.", True, tier)
    # hard — multi-agent chains, including the exact Monitor-Log scenario.
    if rng.random() < 0.5:
        return (f"Run a multi-turn monitoring flow with Tlamatini agents: first use File Creator to "
                f"initialize {tmp}/mon_{idx}.log with a starting line, then start Monitor Log on that "
                f"file watching for 'ERROR,FATAL', then use Pythonxer to append several log lines to "
                f"the same file including one line containing the word 'ERROR', then check the monitor "
                f"once with chat_agent_run_status and chat_agent_run_log, then stop it with "
                f"chat_agent_run_stop and summarize what happened. End with END-RESPONSE.", True, "hard")
    return (f"Using Tlamatini agents, create three files {tmp}/h_{idx}_a.txt, {tmp}/h_{idx}_b.txt and "
            f"{tmp}/h_{idx}_c.txt each containing 'batch {idx}', then use the Grepper to search for "
            f"'batch {idx}' across the {tmp} directory. End with END-RESPONSE.", True, "hard")


def _login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    if page.query_selector("#id_username"):
        page.fill("#id_username", USER)
        page.fill("#id_password", PASS)
        page.click("button[type=submit]")
        page.wait_for_load_state("domcontentloaded")
    page.goto(BASE_URL + "/agent/agent/", wait_until="domcontentloaded")
    page.wait_for_selector("#chat-message-input", timeout=30000)
    time.sleep(1.5)
    page.evaluate("""() => {
      const mt = document.querySelector('#multi-turn-enabled'); if (mt && !mt.checked) mt.click();
      const er = document.querySelector('#exec-report-enabled'); if (er && !er.disabled && !er.checked) er.click();
    }""")
    time.sleep(0.4)


def _wait_done(page, prior):
    """Wait for the run to FULLY finish: a new bot message AND input re-enabled,
    then a settle so the final multi_turn_used frame lands. Generous timeout
    because injected faults add real recovery time."""
    deadline = time.time() + ANSWER_TIMEOUT_S
    while time.time() < deadline:
        count = page.eval_on_selector_all(".message.bot-message", "els => els.length")
        enabled = not page.eval_on_selector("#chat-message-input", "el => el.disabled")
        if count > prior and enabled:
            time.sleep(3.0)
            if not page.eval_on_selector("#chat-message-input", "el => el.disabled"):
                return True
        time.sleep(0.4)
    return False


def main():
    if not USER or not PASS:
        print("ERROR: set TLAMATINI_USER and TLAMATINI_PASS", file=sys.stderr)
        return 2
    rng = random.Random(SEED)
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"self_healing_visual_report_{stamp}.md")
    downloads_dir = os.path.join(REPORT_DIR, f"self_healing_downloads_{stamp}")
    os.makedirs(downloads_dir, exist_ok=True)

    bank = [_make_question(i, rng) for i in range(NUM_QUESTIONS)]
    rng.shuffle(bank)
    frames = []
    results = []
    downloaded = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 25)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        page.on("websocket", lambda ws: ws.on("framereceived", lambda pl: frames.append(pl)))
        page.on("dialog", lambda d: d.accept("healflow"))
        _login(page)

        for idx, (prompt, expect_agent, tier) in enumerate(bank):
            prior = page.eval_on_selector_all(".message.bot-message", "els => els.length")
            fh = len(frames)
            page.fill("#chat-message-input", prompt)
            page.click("#chat-message-submit")
            ok = _wait_done(page, prior)

            # Scan the WS frames produced by THIS turn.
            heal_msgs, final, lie = [], None, False
            for raw in frames[fh:]:
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                if d.get("username") != "Tlamatini":
                    continue
                msg = str(d.get("message", ""))
                if d.get("multi_turn_used"):
                    final = d
                if any(m in msg for m in _HEAL_MARKERS):
                    heal_msgs.append(msg[:120])
                if any(m in msg for m in _LIE_MARKERS):
                    lie = True

            successful = []
            if final is not None:
                successful = [e for e in (final.get("tool_calls_log") or []) if e.get("success")]
            agent_ran = len(successful) >= 1
            self_healed = len(heal_msgs) > 0

            has_button = page.evaluate(
                """(prior) => {
                    const els = Array.from(document.querySelectorAll('.message.bot-message'));
                    return els.slice(prior).some(e => !!e.querySelector('.create-flow'));
                }""", prior)

            rec = {"i": idx, "tier": tier, "answered": ok, "self_healed": self_healed,
                   "heal_count": len(heal_msgs), "agent_ran": agent_ran,
                   "button": has_button, "lie": lie, "flow_ok": None, "note": ""}

            # ── Hard-failure checks ──
            if not ok:
                rec["note"] = "NEVER FINISHED (hung / timed out) — self-healing failed to recover"
            if lie and agent_ran:
                rec["note"] = "LIED: claimed no tools invoked while agents actually ran"
            if agent_ran and not has_button:
                rec["note"] = "agent ran OK but NO Create-Flow button"
            if not agent_ran and has_button:
                rec["note"] = "button present but no agent ran"

            # Prove flow generation still works despite the injected faults.
            if has_button and final is not None and (DOWNLOAD_SAMPLE < 0 or downloaded < DOWNLOAD_SAMPLE):
                try:
                    with page.expect_download(timeout=25000) as di:
                        page.evaluate(
                            """(prior) => {
                                const els = Array.from(document.querySelectorAll('.message.bot-message'));
                                const m = els.slice(prior).find(e => e.querySelector('.create-flow'));
                                if (m) m.querySelector('.create-flow').click();
                            }""", prior)
                    fpath = os.path.join(downloads_dir, f"q{idx:04d}.flw")
                    di.value.save_as(fpath)
                    with open(fpath, "r", encoding="utf-8") as fh2:
                        flow = json.load(fh2)
                    mids = [n.get("text") for n in flow.get("nodes", []) if n.get("text") not in ("Starter", "Ender")]
                    rec["flow_ok"] = len(mids) >= 1
                    downloaded += 1
                except PWTimeout:
                    rec["flow_ok"] = False
                    rec["note"] += " | download timed out"
                except Exception as exc:  # noqa: BLE001
                    rec["flow_ok"] = False
                    rec["note"] += f" | download err: {exc}"

            results.append(rec)
            print(f"[{idx+1}/{len(bank)}] {tier:<6} answered={ok} healed={self_healed}({rec['heal_count']}) "
                  f"agent_ran={agent_ran} button={has_button} flow_ok={rec['flow_ok']} "
                  f"{rec['note']}", flush=True)

        page.screenshot(path=os.path.join(downloads_dir, "final_state.png"))
        ctx.close()
        browser.close()

    _write_report(report_path, results, downloaded)
    print(f"\nReport → {report_path}", flush=True)
    return 0 if _count_fail(results) == 0 else 1


def _count_fail(results):
    f = 0
    for r in results:
        if not r["answered"]:
            f += 1
        if r["lie"] and r["agent_ran"]:
            f += 1
        if r["agent_ran"] and not r["button"]:
            f += 1
        if (not r["agent_ran"]) and r["button"]:
            f += 1
        if r["flow_ok"] is False:
            f += 1
    return f


def _write_report(path, results, downloaded):
    n = len(results)
    answered = sum(1 for r in results if r["answered"])
    healed = sum(1 for r in results if r["self_healed"])
    healed_recovered = sum(1 for r in results if r["self_healed"] and r["answered"] and (r["agent_ran"] or not _expect(r)))
    lies = sum(1 for r in results if r["lie"] and r["agent_ran"])
    agent_ran = sum(1 for r in results if r["agent_ran"])
    btn_ok = sum(1 for r in results if r["answered"] and (r["button"] == r["agent_ran"]))
    flow_ok = sum(1 for r in results if r["flow_ok"] is True)
    flow_ck = sum(1 for r in results if r["flow_ok"] is not None)
    fails = _count_fail(results)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Self-healing VISIBLE soak — {datetime.now().isoformat(timespec='seconds')}\n\n")
        fh.write(f"- Questions: **{n}**, answered (never hung): **{answered}/{n}**\n")
        fh.write(f"- Triggered self-healing (real injected faults): **{healed}/{n}**\n")
        fh.write(f"- Of those, recovered & finished: **{healed_recovered}/{healed}**\n")
        fh.write(f"- LIES ('no tools invoked' while tools ran): **{lies}** (MUST be 0)\n")
        fh.write(f"- Turns an agent actually ran: **{agent_ran}/{n}**\n")
        fh.write(f"- Create-Flow button correct (present iff agent ran): **{btn_ok}/{answered}**\n")
        fh.write(f"- Flows downloaded + validated: **{flow_ok}/{flow_ck}**\n")
        fh.write(f"\n## HARD FAILURES: **{fails}** → {'✅ ALL GREEN' if fails == 0 else '❌ SEE BELOW'}\n\n")
        fh.write("| # | tier | answered | healed(#) | agent_ran | button | lie | flow_ok | note |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            fh.write(f"| {r['i']} | {r['tier']} | {r['answered']} | {r['self_healed']}({r['heal_count']}) | "
                     f"{r['agent_ran']} | {r['button']} | {r['lie']} | {r['flow_ok']} | {r['note'].strip()} |\n")


def _expect(_r):
    return True


if __name__ == "__main__":
    sys.exit(main())
