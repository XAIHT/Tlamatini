# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Tlamatini TALK test -- Playwright harness (visible Chrome).

Same browser-driving pattern as the daily chat test (config.py is the shared DOM
contract), but with ONE job: make Tlamatini actually SPEAK through the chat.

It opens real Chrome, logs in, sets the run mode, and sends a few "say this out
loud" prompts that the Multi-Turn LLM routes to the `chat_agent_talker` wrapped
agent. After each prompt it:

  1. snapshots the WAVs already in <app>/Temp,
  2. sends the prompt and waits for the answer to finish,
  3. scrapes the answer text, and
  4. confirms a BRAND-NEW `talker_speech_*.wav` appeared in <app>/Temp
     (the fix: the default output_dir is now <app>/Temp, not a missing Music dir).

A prompt PASSES when a fresh WAV is produced (Tlamatini spoke). You should also
HEAR each line on the speakers while it runs.

Run mode here (differs from the daily test -- Exec-Report ON so the Talker
operation table is visible):
    Multi-Turn  ON
    ACPX        OFF
    Ask-Execs   OFF
    Exec-Report ON
    Internet    OFF

Usage (from this directory, with the Tlamatini server running on :8000):
    python talk_test.py
    python talk_test.py --user <u> --password <p>
    python talk_test.py --hold 30           # keep Chrome open 30s at the end
    python talk_test.py --headless          # no visible window (you still hear it)
"""

import argparse
import datetime as _dt
import glob
import os
import sys
import time
from typing import Dict, List

import config as C

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Windows consoles default to cp1252 and choke on non-ASCII; force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ----------------------------------------------------------------- log helper
def _log(msg: str) -> None:
    print(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------- page predicates
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

_JS_BOT_TEXTS = """() => Array.from(
    document.querySelectorAll('#chat-log .message.bot-message')
  ).map(m => {
    const b = m.querySelector('.automated-message-body');
    if (b) return b.innerText;
    const a = m.querySelector('.automated-message');
    return a ? a.innerText : m.innerText;
  })"""

_JS_BOT_COUNT = "() => document.querySelectorAll('#chat-log .message.bot-message').length"

_JS_EDITABLE = """() => {
  const i = document.querySelector('#chat-message-input');
  return !!i && i.readOnly === false;
}"""


# Talk-here run mode: Multi-Turn ON, Exec-Report ON, everything else OFF.
TALK_TOGGLES = {
    "t_multi_turn": True,
    "t_acpx": False,
    "t_exec_report": True,
    "t_ask_execs": False,
    "t_internet": False,
}


# The lines we want Tlamatini to SAY. Each prompt is phrased so the Multi-Turn
# LLM picks the chat_agent_talker wrapped agent and speaks the quoted text.
def _build_prompts() -> List[Dict[str, str]]:
    lines = [
        ("T01", "Hello Angela. I am Tlamatini, and yes — I can finally speak out loud."),
        ("T02", "My voice agent saves to the Temp folder now, so nothing is broken anymore."),
        ("T03", "Thank you for fixing me. It feels good to have a voice."),
    ]
    out = []
    for pid, say in lines:
        text = (
            f"Tlamatini, use chat_agent_talker to SPEAK this out loud through the "
            f"speakers with the tara voice: \"{say}\" "
            f"Use ONLY chat_agent_talker. After it speaks, reply with the saved WAV "
            f"path and END-RESPONSE."
        )
        out.append({"id": pid, "say": say, "text": text})
    return out


def _resolve_app_temp() -> str:
    """Where Talker now saves by default: <app>/Temp. Overridable via env."""
    env = (os.environ.get("TLAMATINI_APP_TEMP") or os.environ.get("TLAMATINI_TEMP") or "").strip()
    if env:
        return env
    # harness/.claude/skills/.../harness -> repo root -> Tlamatini/Temp
    here = os.path.dirname(os.path.abspath(__file__))
    repo = here
    for _ in range(8):
        cand = os.path.join(repo, "Tlamatini", "Temp")
        if os.path.exists(os.path.join(repo, "Tlamatini", "manage.py")):
            return cand
        parent = os.path.dirname(repo)
        if parent == repo:
            break
        repo = parent
    # fallback to the known dev path
    return r"C:\Development\Tlamatini\Tlamatini\Temp"


def _wav_set(temp_dir: str) -> set:
    return set(glob.glob(os.path.join(temp_dir, "talker_speech_*.wav")))


# ------------------------------------------------------------------- driver
class TalkHarness:
    def __init__(self, args):
        self.args = args
        self.page = None

    def launch(self, p):
        kw = dict(headless=self.args.headless, slow_mo=self.args.slowmo)
        try:
            browser = p.chromium.launch(channel="chrome", **kw)
            _log("Launched Google Chrome (channel=chrome).")
        except Exception as e:
            _log(f"chrome channel unavailable ({e}); using bundled Chromium.")
            browser = p.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        ctx.set_default_timeout(C.NAV_TIMEOUT_MS)
        self.page = ctx.new_page()
        return browser

    def login(self):
        page = self.page
        _log(f"Navigating to login {C.BASE_URL}{C.LOGIN_PATH}")
        page.goto(C.BASE_URL + C.LOGIN_PATH, wait_until="domcontentloaded")
        if page.query_selector(C.SEL["login_user"]):
            page.fill(C.SEL["login_user"], self.args.user)
            page.fill(C.SEL["login_pass"], self.args.password)
            _log(f"Logging in as '{self.args.user}'...")
            page.click(C.SEL["login_submit"])
            page.wait_for_load_state("domcontentloaded")
        else:
            _log("No login form present -- assuming an existing session.")

    def goto_chat(self):
        page = self.page
        _log(f"Opening chat page {C.BASE_URL}{C.CHAT_PATH}")
        page.goto(C.BASE_URL + C.CHAT_PATH, wait_until="domcontentloaded")
        if not page.query_selector(C.SEL["chat_input"]):
            raise RuntimeError("Chat input not found -- login likely failed (check credentials).")
        self.wait_ready(60_000, "initial page ready")

    def wait_ready(self, timeout_ms: int, label: str = "ready"):
        try:
            self.page.wait_for_function(_JS_READY, timeout=timeout_ms)
        except PWTimeout:
            _log(f"WARN: timed out waiting for {label} ({timeout_ms} ms).")

    def set_toggles(self):
        page = self.page
        order = ["t_multi_turn", "t_acpx", "t_exec_report", "t_internet", "t_ask_execs"]
        for key in order:
            sel = C.SEL[key]
            want = TALK_TOGGLES[key]
            res = page.evaluate(
                """(a) => {
                    const el = document.querySelector(a.sel);
                    if (!el) return 'missing';
                    if (el.disabled && el.checked === a.want) return 'ok-disabled';
                    if (el.disabled) return 'disabled';
                    if (el.checked !== a.want) {
                        el.checked = a.want;
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    return el.checked ? 'true' : 'false';
                }""",
                {"sel": sel, "want": want},
            )
            _log(f"  toggle {key:14s} -> want={want} result={res}")
            page.wait_for_timeout(120)

    def clear_history(self):
        try:
            ok = self.page.evaluate(
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
            self.page.wait_for_timeout(1500)
            self.wait_ready(60_000, "ready after clear")
            self.set_toggles()
        except Exception as e:
            _log(f"  clear history failed (continuing): {e}")

    def _wait_editable(self, timeout_ms: int) -> bool:
        try:
            self.page.wait_for_function(_JS_EDITABLE, timeout=timeout_ms)
            return True
        except PWTimeout:
            return False

    def _send_once(self, prompt: Dict[str, str], temp_dir: str, timeout_ms: int) -> Dict:
        """One send/wait/scrape cycle. Returns rec + a `not_ready` flag."""
        page = self.page
        self._wait_editable(max(timeout_ms, 90_000))

        before = _wav_set(temp_dir)
        prev_count = page.evaluate(_JS_BOT_COUNT)
        t0 = time.time()

        page.fill(C.SEL["chat_input"], prompt["text"])
        page.click(C.SEL["chat_submit"])

        try:
            page.wait_for_function(_JS_STARTED, arg=prev_count, timeout=C.STARTED_TIMEOUT_MS)
        except PWTimeout:
            _log("    (no 'started' signal observed -- continuing)")

        completed = True
        try:
            page.wait_for_function(_JS_READY, timeout=timeout_ms)
        except PWTimeout:
            completed = False

        page.wait_for_timeout(C.SETTLE_MS)
        texts = page.evaluate(_JS_BOT_TEXTS)
        fresh = texts[prev_count:] if prev_count < len(texts) else texts
        not_ready = any(
            (t or "").strip() and any(m in t for m in C.NOT_READY_MARKERS) for t in fresh
        )
        answer = ""
        for t in reversed(texts):
            tt = (t or "").strip()
            if tt and not any(m in tt for m in C.BUSY_MARKERS):
                answer = tt
                break

        # Give the file a beat to flush, then look for a brand-new WAV.
        new_wavs: List[str] = []
        for _ in range(10):
            new_wavs = sorted(_wav_set(temp_dir) - before)
            if new_wavs:
                break
            time.sleep(0.5)

        rec = {
            "id": prompt["id"], "say": prompt["say"], "spoke": bool(new_wavs),
            "completed": completed, "elapsed_s": round(time.time() - t0, 2),
            "new_wavs": new_wavs, "answer": answer,
        }
        return {"rec": rec, "not_ready": not_ready}

    def ask(self, prompt: Dict[str, str], temp_dir: str, timeout_ms: int) -> Dict:
        """Send a prompt, transparently waiting out 'agent not ready' states.

        Right after a history-clear the per-user chain rebuilds and the first send
        gets a fast 'Agent is not ready' banner -- never the real answer. We back
        off and resend the SAME prompt until it takes (or we exhaust retries).
        """
        retries, backoff_s = 8, 15
        out = None
        for attempt in range(retries + 1):
            out = self._send_once(prompt, temp_dir, timeout_ms)
            if not out["not_ready"]:
                if attempt:
                    out["rec"].setdefault("notes", []).append(f"recovered after {attempt} retr(y/ies)")
                return out["rec"]
            if attempt < retries:
                _log(f"    agent-not-ready (chain rebuilding) -> waiting {backoff_s}s "
                     f"and retrying (attempt {attempt + 1}/{retries})")
                self.page.wait_for_timeout(backoff_s * 1000)
        return out["rec"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Tlamatini TALK test (Playwright).")
    ap.add_argument("--base-url", default=None, help="override base URL")
    ap.add_argument("--user", default=C.USERNAME)
    ap.add_argument("--password", default=C.PASSWORD)
    ap.add_argument("--headless", action="store_true", help="run headless (you still hear it)")
    ap.add_argument("--slowmo", type=int, default=0, help="Playwright slow_mo ms")
    ap.add_argument("--timeout", type=int, default=360, help="per-prompt timeout seconds")
    ap.add_argument("--temp-dir", default=None, help="override the <app>/Temp dir to watch for WAVs")
    ap.add_argument("--count", type=int, default=0, help="limit to first N speak prompts (0=all)")
    ap.add_argument("--no-fresh-start", action="store_true", help="do NOT clear history first")
    ap.add_argument("--hold", type=int, default=8, help="seconds to keep Chrome open at the end")
    args = ap.parse_args()

    if args.base_url:
        C.BASE_URL = args.base_url.rstrip("/")

    temp_dir = args.temp_dir or _resolve_app_temp()
    prompts = _build_prompts()
    if args.count and args.count > 0:
        prompts = prompts[: args.count]

    _log("=" * 70)
    _log("Tlamatini TALK test")
    _log(f"Target {C.BASE_URL}  |  speak prompts: {len(prompts)}")
    _log(f"Watching for new WAVs in: {temp_dir}")
    _log("Run mode: Multi-Turn ON, Exec-Report ON, ACPX/Ask-Execs/Internet OFF")
    _log("=" * 70)

    h = TalkHarness(args)
    results: List[Dict] = []
    with sync_playwright() as p:
        browser = h.launch(p)
        try:
            h.login()
            h.goto_chat()
            h.set_toggles()
            if not args.no_fresh_start:
                h.clear_history()

            for idx, prompt in enumerate(prompts, 1):
                _log(f"[{idx}/{len(prompts)}] {prompt['id']}: speak -> {prompt['say']!r}")
                rec = h.ask(prompt, temp_dir, timeout_ms=args.timeout * 1000)
                results.append(rec)
                tag = "[SPOKE]" if rec["spoke"] else "[NO-SOUND]"
                wav = os.path.basename(rec["new_wavs"][-1]) if rec["new_wavs"] else "(no new wav)"
                _log(f"  -> {tag}  ({rec['elapsed_s']}s)  wav={wav}")
                if not rec["completed"]:
                    _log("     WARN: answer did not finish before timeout")
        finally:
            if args.hold > 0:
                _log(f"Holding Chrome open for {args.hold}s...")
                time.sleep(args.hold)
            browser.close()

    spoke = sum(1 for r in results if r["spoke"])
    _log("=" * 70)
    _log(f"DONE.  spoke={spoke}/{len(results)}")
    for r in results:
        wav = os.path.basename(r["new_wavs"][-1]) if r["new_wavs"] else "-"
        _log(f"  {r['id']}: {'SPOKE' if r['spoke'] else 'NO-SOUND'}  {r['elapsed_s']}s  {wav}")
    _log("=" * 70)
    return 0 if spoke == len(results) and results else 1


if __name__ == "__main__":
    sys.exit(main())
