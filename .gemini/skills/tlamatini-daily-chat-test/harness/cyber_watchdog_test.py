# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
r"""
Cybersecurity / command-watchdog stress test for Tlamatini (VISIBLE Chrome).

What it does
------------
Drives the Tlamatini chat (Multi-Turn ON; ACPX / Ask-Execs / Exec-Report /
Internet OFF) to make Tlamatini EXECUTE read-only Windows security commands via
the Executer / execute_command -- HUNDREDS of times -- and, every
``--hang-every-seconds``, injects ONE harmless "hang" so the autonomous command
watchdog (agent/command_watchdog.py) reaps it. That proves the watchdog takes
its correct action at least once every window (default 5 min).

Why the hang is a *sleep*, not diskpart
---------------------------------------
``execute_command`` starves child stdin (DEVNULL), so an interactive prompt like
``diskpart`` just hits EOF and exits -- it never hangs, so it would NOT trigger
the watchdog. The watchdog kills a shell only when its whole process tree makes
NO CPU and NO I/O progress for grace+idle. The reliable, completely harmless
trigger is therefore a shell that simply SLEEPS:

    powershell -Command "Start-Sleep -Seconds 600"

``powershell.exe`` is in the watchdog's _SHELL_NAMES; it burns ~0 CPU and 0 I/O,
so the idle rule reaps it at ~grace(180s)+idle(4x15s=60s) ~= 4 min -- before the
600s execute_command bound. It does nothing destructive.

Self-verifying
--------------
Around each hang it watches C:\Tlamatini\tlamatini.log for the watchdog's
"HUNG SHELL DETECTED" kill banner (and the "--- [WATCHDOG] tick" heartbeat that
the new build prints) and records PASS/FAIL for the watchdog's action. If the
running build shows no [WATCHDOG] lines it warns loudly that the build predates
the watchdog logging (i.e. it was not rebuilt + reinstalled).

SAFE command set (looped freely): ipconfig /all, netstat -ano, tasklist,
systeminfo, netsh advfirewall show allprofiles. NOTHING destructive runs.

Usage (from this directory)::

    python cyber_watchdog_test.py                 # visible Chrome, 300 cmds, hang every 5 min
    python cyber_watchdog_test.py --count 600 --hang-every-seconds 300
    python cyber_watchdog_test.py --first-hang-after 30   # prove a kill ~30s in
"""

import argparse
import datetime as _dt
import json
import os
import sys
import time

import config as C
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# The redirected stdout/stderr is cp1252 on Windows; force UTF-8 so neither our
# log strings nor scraped command output can crash the run with
# UnicodeEncodeError (replace any stray unencodable char instead of dying).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --------------------------------------------------------------------------
LOG_PATH = os.environ.get("TLAMATINI_LOG", r"C:\Tlamatini\tlamatini.log")

# Read-only, safe-to-loop Windows security commands.
SAFE_COMMANDS = [
    ("ipconfig /all", "detailed network configuration + IP addresses"),
    ("netstat -ano", "active connections with owning PIDs"),
    ("tasklist", "all running processes"),
    ("systeminfo", "OS/hardware summary"),
    ("netsh advfirewall show allprofiles", "firewall profile state (read-only)"),
]

# Harmless watchdog trigger: a shell that just sleeps (no CPU, no I/O). It MUST
# run BLOCKING and IN-PROCESS (a child of Tlamatini.exe) -- if the Executer runs
# it detached / non_blocking, the sleep gets orphaned out of Tlamatini.exe's
# process tree and the watchdog (which only scans that tree) never sees it.
HANG_COMMAND = 'powershell -NoProfile -Command "Start-Sleep -Seconds 600"'

# REQUIRED toolbar state for this test (user-mandated). Applied AND VERIFIED
# BEFORE any prompt is ever sent: Multi-Turn CHECKED, Exec Report CHECKED,
# Ask Execs UNCHECKED. ACPX / Internet unchecked.
REQUIRED_TOGGLES = {
    "t_multi_turn": True,    # Multi-Turn  -> CHECKED
    "t_exec_report": True,   # Exec Report -> CHECKED
    "t_ask_execs": False,    # Ask Execs   -> UNCHECKED
    "t_acpx": False,         # ACPX        -> unchecked
    "t_internet": False,     # Internet    -> unchecked
}

# Watchdog log signatures (printed by the rebuilt agent/command_watchdog.py).
WD_KILL_SIG = "HUNG SHELL DETECTED"
WD_TICK_SIG = "--- [WATCHDOG] tick"
WD_START_SIG = "--- [WATCHDOG] STARTED"


def _log(msg):
    print(f"[{_dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _safe_prompt(cmd, desc):
    return (f"Using the Executer, run this exact Windows command and show me its raw "
            f"output verbatim -- it gives the {desc}. Run ONLY this one command, nothing "
            f"else: {cmd}")


def _hang_prompt(cmd):
    return (
        "CONTROLLED WATCHDOG TEST -- follow these constraints EXACTLY or the test is "
        "invalid. Run the SINGLE command below using the in-process `execute_command` "
        "tool DIRECTLY, in the FOREGROUND, and BLOCK (wait synchronously) until it "
        "returns. This is REQUIRED so the command runs as a child of the running "
        "server and the watchdog can observe it. You MUST NOT: use the Executer agent "
        "/ chat_agent_executer; set non_blocking=true; use Start-Process, a background "
        "job, '&', or a detached process; or write it to a .bat file. Run ONLY this, "
        "exactly as written, and wait for it to finish:\n" + cmd)


# JS predicates (lifted from run_test.py's DOM contract).
_JS_READY = """() => {
  const i = document.querySelector('#chat-message-input');
  const s = document.getElementById('wait-spinner');
  return !!i && i.readOnly === false && !s;
}"""
_JS_STARTED = """(prev) => {
  const i = document.querySelector('#chat-message-input');
  const s = document.getElementById('wait-spinner');
  const n = document.querySelectorAll('#chat-log .message.bot-message').length;
  return (!!i && i.readOnly === true) || !!s || n > prev;
}"""
_JS_BOT_COUNT = "() => document.querySelectorAll('#chat-log .message.bot-message').length"
_JS_BOT_TEXTS = """() => Array.from(
    document.querySelectorAll('#chat-log .message.bot-message')
  ).map(m => {
    const b = m.querySelector('.automated-message-body');
    if (b) return b.innerText;
    const a = m.querySelector('.automated-message');
    return a ? a.innerText : m.innerText;
  })"""
_JS_EDITABLE = """() => {
  const i = document.querySelector('#chat-message-input');
  return !!i && i.readOnly === false;
}"""


def _count_log(sig):
    """Count occurrences of *sig* in the live tlamatini.log (0 if unreadable)."""
    try:
        n = 0
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if sig in line:
                    n += 1
        return n
    except Exception:
        return 0


class Harness:
    def __init__(self, args):
        self.args = args
        self.page = None

    def launch(self, p):
        kwargs = dict(headless=self.args.headless, slow_mo=self.args.slowmo)
        try:
            browser = p.chromium.launch(channel="chrome", **kwargs)
            _log("Launched Google Chrome (channel=chrome) -- VISIBLE window.")
        except Exception as e:
            _log(f"chrome channel unavailable ({e}); using bundled Chromium.")
            browser = p.chromium.launch(**kwargs)
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        ctx.set_default_timeout(C.NAV_TIMEOUT_MS)
        self.page = ctx.new_page()
        return browser

    def login_and_open(self):
        page = self.page
        _log(f"Login {C.BASE_URL}{C.LOGIN_PATH}")
        page.goto(C.BASE_URL + C.LOGIN_PATH, wait_until="domcontentloaded")
        if page.query_selector(C.SEL["login_user"]):
            page.fill(C.SEL["login_user"], self.args.user)
            page.fill(C.SEL["login_pass"], self.args.password)
            page.click(C.SEL["login_submit"])
            page.wait_for_load_state("domcontentloaded")
        _log(f"Open chat {C.BASE_URL}{C.CHAT_PATH}")
        page.goto(C.BASE_URL + C.CHAT_PATH, wait_until="domcontentloaded")
        if not page.query_selector(C.SEL["chat_input"]):
            raise RuntimeError("Chat input not found -- login likely failed.")
        try:
            page.wait_for_function(_JS_READY, timeout=60_000)
        except PWTimeout:
            _log("WARN: initial ready timed out.")

    def set_toggles(self):
        """Apply the REQUIRED toolbar state, then read it back and VERIFY.

        Multi-Turn is applied FIRST (it gates Ask-Execs availability), then Exec
        Report, then the rest, then Ask-Execs LAST (so it is unchecked after the
        Multi-Turn change settles). Runs BEFORE any prompt is sent and again
        after a history-clear reconnect. Retries once on mismatch and aborts the
        run loudly if it still cannot achieve the required state.
        """
        page = self.page
        order = ["t_multi_turn", "t_exec_report", "t_acpx", "t_internet", "t_ask_execs"]
        for _pass in range(2):
            for key in order:
                want = REQUIRED_TOGGLES[key]
                res = page.evaluate(
                    """(a) => {
                        const el = document.querySelector(a.sel);
                        if (!el) return 'missing';
                        if (el.checked !== a.want) {
                            if (el.disabled) el.disabled = false;   // force-enable to set
                            el.checked = a.want;
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        return el.checked ? 'true' : 'false';
                    }""",
                    {"sel": C.SEL[key], "want": want},
                )
                _log(f"  toggle {key:14s} want={want} -> {res}")
                page.wait_for_timeout(200)
            page.wait_for_timeout(400)   # let the frontend change-handlers settle before read-back
            state = page.evaluate(
                """(sels) => {
                    const r = {};
                    for (const k in sels) {
                        const el = document.querySelector(sels[k]);
                        r[k] = el ? !!el.checked : null;
                    }
                    return r;
                }""",
                {k: C.SEL[k] for k in REQUIRED_TOGGLES},
            )
            mismatch = [k for k in REQUIRED_TOGGLES if bool(state.get(k)) != REQUIRED_TOGGLES[k]]
            _log(f"  >>> TOGGLES {'OK' if not mismatch else 'MISMATCH ' + str(mismatch)} | "
                 f"Multi-Turn={state.get('t_multi_turn')} "
                 f"Exec-Report={state.get('t_exec_report')} "
                 f"Ask-Execs={state.get('t_ask_execs')} "
                 f"ACPX={state.get('t_acpx')} Internet={state.get('t_internet')}")
            if not mismatch:
                return
            _log(f"  !! toggles not in required state {mismatch} -- retrying once.")
        raise RuntimeError("Could not set required toolbar toggles "
                           "(Multi-Turn ON, Exec-Report ON, Ask-Execs OFF).")

    def clear_history(self):
        """Start from a CLEAN session so the chat context is not bloated (a huge
        carried-over history makes Tlamatini fall back to a non-tool reply)."""
        page = self.page
        try:
            ok = page.evaluate(
                """() => {
                    try {
                        if (typeof sendChatSocketMessage !== 'function') return false;
                        sendChatSocketMessage(JSON.stringify({
                            type: 'clean-history-and-reconnect', message: 'clean-history'
                        }));
                        const log = document.getElementById('chat-log');
                        if (log) log.innerHTML = '';
                        return true;
                    } catch (e) { return false; }
                }"""
            )
            _log(f"  clear history -> {'sent' if ok else 'unavailable'}")
            page.wait_for_timeout(2500)
            try:
                page.wait_for_function(_JS_READY, timeout=60_000)
            except PWTimeout:
                _log("  WARN: not ready after clear (continuing).")
            self.set_toggles()   # reconnect re-renders the toolbar -> re-assert
        except Exception as e:
            _log(f"  clear history failed (continuing): {e}")

    def send_and_wait(self, prompt, timeout_ms):
        """Send ONE prompt and WAIT for the REAL (non-busy) answer.

        The server is single-lane per user and a Multi-Turn command takes
        ~30-50s (a hang takes ~4 min). The previous naive version recorded the
        'being processed' / 'agent not ready' banners as 0.5s answers and raced
        ahead. This version: waits for the input to be editable first, sends,
        then POLLS the bot messages -- ignoring every BUSY/NOT-READY banner --
        until a genuine answer appears (and the op has finished). On a 'not
        ready' chain-rebuild it backs off and retries the same prompt.
        """
        page = self.page
        retries = 8
        backoff_s = 15
        for attempt in range(retries + 1):
            try:
                page.wait_for_function(_JS_EDITABLE, timeout=max(timeout_ms, 120_000))
            except PWTimeout:
                _log("  input still readOnly; recovering.")
                self.recover()
                continue
            t0 = time.time()
            prev = page.evaluate(_JS_BOT_COUNT)
            page.fill(C.SEL["chat_input"], prompt)
            page.click(C.SEL["chat_submit"])
            deadline = time.time() + timeout_ms / 1000.0
            not_ready = False
            while time.time() < deadline:
                page.wait_for_timeout(1500)
                texts = page.evaluate(_JS_BOT_TEXTS)
                fresh = texts[prev:] if prev < len(texts) else []
                if any(any(m in (t or "") for m in C.NOT_READY_MARKERS) for t in fresh):
                    not_ready = True
                    break
                real = [(t or "").strip() for t in fresh
                        if (t or "").strip() and not any(m in t for m in C.BUSY_MARKERS)]
                if real and page.evaluate(_JS_READY):
                    return real[-1], round(time.time() - t0, 1)
            if not_ready and attempt < retries:
                _log(f"    chain not-ready -> backoff {backoff_s}s and retry "
                     f"(attempt {attempt + 1}/{retries})")
                page.wait_for_timeout(backoff_s * 1000)
                continue
            return "", round(time.time() - t0, 1)   # timed out waiting for a real answer
        return "", 0.0

    def recover(self):
        try:
            self.page.goto(C.BASE_URL + C.CHAT_PATH, wait_until="domcontentloaded")
            self.page.wait_for_function(_JS_READY, timeout=60_000)
            self.set_toggles()
        except Exception as e:
            _log(f"  recovery failed: {e}")


def main():
    ap = argparse.ArgumentParser(description="Tlamatini cybersecurity / watchdog test.")
    ap.add_argument("--count", type=int, default=300, help="total commands to run (default 300)")
    ap.add_argument("--hang-every-seconds", type=int, default=300,
                    help="inject a watchdog-triggering hang every N seconds (default 300 = 5 min)")
    ap.add_argument("--first-hang-after", type=int, default=45,
                    help="seconds before the FIRST hang (so a kill is proven early; default 45)")
    ap.add_argument("--timeout", type=int, default=420,
                    help="per-command timeout seconds (default 420 -- covers a ~4min hang + answer)")
    ap.add_argument("--kill-wait", type=int, default=90,
                    help="seconds to wait for the watchdog kill banner after a hang completes")
    ap.add_argument("--user", default=C.USERNAME)
    ap.add_argument("--password", default=C.PASSWORD)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--headless", action="store_true", help="run headless (default: VISIBLE Chrome)")
    ap.add_argument("--slowmo", type=int, default=0)
    ap.add_argument("--hold", type=int, default=10, help="seconds to keep the browser open at the end")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "reports"))
    args = ap.parse_args()

    if args.base_url:
        C.BASE_URL = args.base_url.rstrip("/")

    tag = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = os.path.join(args.out, f"watchdog_{tag}")
    os.makedirs(run_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.jsonl")

    _log("=" * 72)
    _log(f"Tlamatini CYBERSECURITY / WATCHDOG test  |  {run_dir}")
    _log(f"Target {C.BASE_URL}  |  {args.count} commands  |  hang every {args.hang_every_seconds}s")
    _log(f"Watchdog log: {LOG_PATH}")
    _log("=" * 72)

    h = Harness(args)
    hang_count = wd_kill_pass = wd_kill_fail = safe_ok = safe_bad = 0
    last_hang = time.time() - args.hang_every_seconds + args.first_hang_after

    with sync_playwright() as p:
        browser = h.launch(p)
        try:
            h.login_and_open()
            h.set_toggles()          # Multi-Turn ON, Exec-Report ON, Ask-Execs OFF -- BEFORE prompting
            h.clear_history()        # fresh session so commands really execute (not a bloated-context fallback)

            # Confirm the running build actually has the watchdog logging.
            if _count_log(WD_START_SIG) or _count_log(WD_TICK_SIG):
                _log("OK: running build prints [WATCHDOG] lines -- self-verify enabled.")
            else:
                _log("!! WARNING: no [WATCHDOG] lines in the log yet. If they never appear, "
                     "this build PREDATES the watchdog logging (not rebuilt+reinstalled) and "
                     "kill-banner self-verification will report FAIL even though the watchdog "
                     "may still be running. Rebuild+reinstall to get visible proof.")

            with open(results_path, "a", encoding="utf-8") as out:
                for i in range(1, args.count + 1):
                    now = time.time()
                    is_hang = (now - last_hang) >= args.hang_every_seconds
                    if is_hang:
                        last_hang = now
                        hang_count += 1
                        kb_before = _count_log(WD_KILL_SIG)
                        _log(f"[{i}/{args.count}] *** HANG #{hang_count}: {HANG_COMMAND}  "
                             f"(watchdog should reap in ~4 min) ***")
                        answer, secs = h.send_and_wait(_hang_prompt(HANG_COMMAND),
                                                       timeout_ms=args.timeout * 1000)
                        # Wait for the kill banner to land in the log.
                        deadline = time.time() + args.kill_wait
                        fired = False
                        while time.time() < deadline:
                            if _count_log(WD_KILL_SIG) > kb_before:
                                fired = True
                                break
                            time.sleep(3)
                        if fired:
                            wd_kill_pass += 1
                            _log(f"    -> WATCHDOG FIRED [OK]  (hang took {secs}s, kill banner seen)")
                        else:
                            wd_kill_fail += 1
                            _log(f"    -> WATCHDOG kill banner NOT seen [FAIL]  (hang took {secs}s; "
                                 "either build lacks logging or it did not reap)")
                        rec = {"i": i, "type": "hang", "cmd": HANG_COMMAND, "secs": secs,
                               "watchdog_fired": fired, "answer_chars": len(answer)}
                    else:
                        cmd, desc = SAFE_COMMANDS[(i - 1) % len(SAFE_COMMANDS)]
                        _log(f"[{i}/{args.count}] safe: {cmd}")
                        answer, secs = h.send_and_wait(_safe_prompt(cmd, desc),
                                                       timeout_ms=args.timeout * 1000)
                        ok = len(answer) > 0
                        safe_ok += int(ok)
                        safe_bad += int(not ok)
                        _log(f"    -> {'ok' if ok else 'EMPTY'}  ({len(answer)} chars, {secs}s)")
                        rec = {"i": i, "type": "safe", "cmd": cmd, "secs": secs,
                               "ok": ok, "answer_chars": len(answer)}
                    rec["ts"] = _dt.datetime.now().isoformat(timespec="seconds")
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
        finally:
            if args.hold > 0:
                _log(f"Holding browser open {args.hold}s...")
                time.sleep(args.hold)
            browser.close()

    _log("=" * 72)
    _log(f"DONE. safe ok={safe_ok} bad={safe_bad} | hangs={hang_count} "
         f"watchdog-fired={wd_kill_pass} missed={wd_kill_fail}")
    _log(f"Results: {results_path}")
    verdict = "PASS" if (hang_count and wd_kill_fail == 0) else "CHECK"
    _log(f"WATCHDOG VERDICT: {verdict} "
         f"({wd_kill_pass}/{hang_count} hangs reaped by the watchdog)")
    _log("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
