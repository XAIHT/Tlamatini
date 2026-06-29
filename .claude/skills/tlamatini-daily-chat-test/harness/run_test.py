# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Tlamatini daily chat test -- Playwright harness (visible Chrome).

Opens a real Chrome window, logs into Tlamatini, sets the pinned run mode
(Multi-Turn ON, ACPX/Ask-Execs/Exec-Report/Internet OFF), then asks up to 1000
curated questions one at a time -- typing each into the chat, sending it, waiting
for the answer to finish rendering, scraping it, and qualifying it (heuristic +
LLM judge on the failures). Writes an incremental JSONL log plus a final
Markdown report and JSON summary.

Run mode contract & DOM/answer-complete signal: see config.py.
Question bank (exactly 1000, safe-to-execute): see questions.py.
Qualification (heuristic + Anthropic judge on failures): see qualify.py.

Usage (from this directory):
    python run_test.py                      # full 1000, visible Chrome
    python run_test.py --count 10           # quick smoke run
    python run_test.py --count 5 --headless # CI-style
    python run_test.py --resume reports/run_2026-06-05_22-00-00
"""

import argparse
import datetime as _dt
import json
import os
import random
import sys
import time
import traceback
from typing import Any, Dict, List

import config as C
from questions import build_questions, category_counts
from qualify import heuristic_qualify, LLMJudge

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


# ---------------------------------------------------------------- utilities
def _now_tag() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _log(msg: str) -> None:
    print(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# JS predicates (kept as strings so they run in the page)
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

# input present AND editable (not readOnly) -- safe to type into
_JS_EDITABLE = """() => {
  const i = document.querySelector('#chat-message-input');
  return !!i && i.readOnly === false;
}"""


# --select aliases: friendly names -> the canonical token they should match.
# Lets the user say "emailer" for the send_email wrapped agent, etc.
_SELECT_ALIASES = {
    "emailer": "send_email",
    "email": "send_email",
    "mailer": "send_email",
    "sendmail": "send_email",
    "send-email": "send_email",
    "receive_email": "recmailer",
    "receivemail": "recmailer",
    "imap": "recmailer",
    "telegram": "telegrammer",
    "whatsapp": "whatsapper",
}


def _question_haystack(q: Dict[str, Any]) -> List[str]:
    """Lowercased strings a --select token may match against, for one question."""
    hay = [str(q.get(k, "")) for k in ("id", "category", "key", "display")]
    cat = str(q.get("category", "")).lower()
    if ":" in cat:                       # 'wrapped:send_email' -> also match 'send_email'
        hay.append(cat.split(":", 1)[1])
    return [h.lower() for h in hay if h]


def _matches_select(q: Dict[str, Any], tokens: List[str]) -> bool:
    """True if any --select token matches this question (id / category / key / display)."""
    hay = _question_haystack(q)
    for raw in tokens:
        t = raw.strip().lower()
        if not t:
            continue
        t = _SELECT_ALIASES.get(t, t)
        if any(t == h or t in h for h in hay):
            return True
    return False


def _fresh_texts(texts: List[str], prev_count: int) -> List[str]:
    return texts[prev_count:] if prev_count < len(texts) else []


def _contains_not_ready(texts: List[str], prev_count: int) -> bool:
    """True if the fresh bot messages are a server 'agent busy/not ready' banner."""
    for t in _fresh_texts(texts, prev_count):
        tt = (t or "").strip()
        if tt and any(m in tt for m in C.NOT_READY_MARKERS):
            return True
    return False


def _filter_answer(texts: List[str], prev_count: int) -> str:
    """Pick the real answer from bot messages appended after prev_count."""
    fresh = texts[prev_count:] if prev_count < len(texts) else []
    kept = []
    for t in fresh:
        tt = (t or "").strip()
        if not tt:
            continue
        if any(marker in tt for marker in C.BUSY_MARKERS):
            continue
        kept.append(tt)
    if kept:
        return kept[-1]
    # fall back to the very last bot message if everything got filtered
    for t in reversed(texts):
        tt = (t or "").strip()
        if tt and not any(marker in tt for marker in C.BUSY_MARKERS):
            return tt
    return ""


# ----------------------------------------------------------- browser driver
class Harness:
    def __init__(self, args):
        self.args = args
        self.page = None
        self.judge = LLMJudge(model=args.judge_model)

    # -- lifecycle --
    def launch(self, p):
        launch_kwargs = dict(headless=self.args.headless, slow_mo=self.args.slowmo)
        # Prefer real Google Chrome; fall back to bundled Chromium.
        try:
            browser = p.chromium.launch(channel="chrome", **launch_kwargs)
            _log("Launched Google Chrome (channel=chrome).")
        except Exception as e:
            _log(f"chrome channel unavailable ({e}); using bundled Chromium.")
            browser = p.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        ctx.set_default_timeout(C.NAV_TIMEOUT_MS)
        self.page = ctx.new_page()
        return browser

    def login(self):
        page = self.page
        _log(f"Navigating to login {C.BASE_URL}{C.LOGIN_PATH}")
        page.goto(C.BASE_URL + C.LOGIN_PATH, wait_until="domcontentloaded")
        # Already authenticated? login_view redirects authenticated GET '/'? No --
        # '/' always renders login; so fill + submit.
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
            raise RuntimeError(
                "Chat input not found -- login likely failed (check credentials)."
            )
        self.wait_ready(timeout_ms=60_000, label="initial page ready")

    def wait_ready(self, timeout_ms: int, label: str = "ready"):
        try:
            self.page.wait_for_function(_JS_READY, timeout=timeout_ms)
        except PWTimeout:
            _log(f"WARN: timed out waiting for {label} ({timeout_ms} ms).")

    # -- configuration --
    def set_toggles(self):
        page = self.page
        # Multi-Turn first (it gates Ask-Execs availability), then the rest.
        order = ["t_multi_turn", "t_acpx", "t_exec_report", "t_internet", "t_ask_execs"]
        for key in order:
            sel = C.SEL[key]
            want = C.TOGGLE_STATE[key]
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
        """Clear chat history via the same WS frame the Clear button sends."""
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
            # the frame reconnects the socket; give it a moment then re-arm
            self.page.wait_for_timeout(1500)
            self.wait_ready(timeout_ms=60_000, label="ready after clear")
            self.set_toggles()
        except Exception as e:
            _log(f"  clear history failed (continuing): {e}")

    # -- one question --
    def _wait_editable(self, timeout_ms: int) -> bool:
        """Wait until the chat input is editable (prior op may still be running)."""
        try:
            self.page.wait_for_function(_JS_EDITABLE, timeout=timeout_ms)
            return True
        except PWTimeout:
            return False

    def _send_and_capture(self, q: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        """One send/wait/scrape cycle. Returns a record dict + a `not_ready` flag."""
        page = self.page
        started_ok = True
        completed = True
        t0 = time.time()

        prev_count = page.evaluate(_JS_BOT_COUNT)
        page.fill(C.SEL["chat_input"], q["text"])
        page.click(C.SEL["chat_submit"])

        try:
            page.wait_for_function(_JS_STARTED, arg=prev_count, timeout=C.STARTED_TIMEOUT_MS)
        except PWTimeout:
            started_ok = False

        try:
            page.wait_for_function(_JS_READY, timeout=timeout_ms)
        except PWTimeout:
            completed = False

        page.wait_for_timeout(C.SETTLE_MS)
        texts = page.evaluate(_JS_BOT_TEXTS)
        not_ready = _contains_not_ready(texts, prev_count)
        answer = _filter_answer(texts, prev_count)   # excludes busy + not-ready banners
        elapsed = round(time.time() - t0, 2)

        rec = {
            "id": q["id"], "category": q["category"], "question": q["text"],
            "answer": answer, "answer_chars": len(answer), "elapsed_s": elapsed,
            "started_observed": started_ok, "completed": completed,
            "heuristic": heuristic_qualify(q, answer, completed),
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        return {"rec": rec, "not_ready": not_ready}

    def ask_one(self, q: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        """Ask one question, transparently waiting out 'agent not ready' states.

        The per-user chain is single-lane: a previous slow request can leave the
        server replying 'Agent is not ready...' to the next sends. We never record
        that as the answer -- we wait for the input to be editable, then (on a
        not-ready reply) back off and retry the SAME question, escalating to a hard
        page recovery, before finally recording a FAIL.
        """
        page = self.page
        retries = max(0, self.args.not_ready_retries)
        backoff_ms = max(1000, int(self.args.not_ready_backoff * 1000))

        for attempt in range(retries + 1):
            # make sure the box is editable before typing (prior op may run on)
            if not self._wait_editable(timeout_ms=max(timeout_ms, 90_000)):
                _log("    input still readOnly (prior op running) -> recovering")
                self.recover()
                continue

            out = self._send_and_capture(q, timeout_ms)
            if not out["not_ready"]:
                if attempt:
                    out["rec"].setdefault("notes", []).append(f"recovered after {attempt} retr(y/ies)")
                return out["rec"]

            # server said "not ready" (global rag_chain_ready is False -- a prior
            # in-flight request is still finishing / the chain is rebuilding).
            # The ONLY cure is to WAIT: do NOT reload here (a reconnect re-triggers
            # a rebuild and resets the wait). Just back off and resend.
            if attempt < retries:
                wait_s = round(backoff_ms / 1000, 1)
                _log(f"    agent-not-ready (rag_chain rebuilding) -> waiting {wait_s}s "
                     f"and retrying (attempt {attempt + 1}/{retries})")
                page.wait_for_timeout(backoff_ms)

        # exhausted: record a clean FAIL (not the junk banner)
        rec = out["rec"]
        rec["answer"] = ""
        rec["answer_chars"] = 0
        rec["heuristic"] = {"status": "FAIL",
                            "reasons": [f"agent-not-ready-after-{retries}-retries"], "chars": 0}
        return rec

    def recover(self):
        """Best-effort reset after a per-question exception."""
        try:
            self.page.goto(C.BASE_URL + C.CHAT_PATH, wait_until="domcontentloaded")
            self.wait_ready(timeout_ms=60_000, label="ready after recovery")
            self.set_toggles()
        except Exception as e:
            _log(f"  recovery failed: {e}")


# ------------------------------------------------------------------- report
def _load_existing(results_path: str) -> Dict[str, Dict[str, Any]]:
    done: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    done[rec["id"]] = rec
                except Exception:
                    continue
    return done


def _final_status(rec: Dict[str, Any]) -> str:
    """Combine heuristic + (optional) judge into a single final status."""
    h = rec["heuristic"]["status"]
    judge = rec.get("judge")
    if h == "PASS":
        return "PASS"
    if judge and judge.get("verdict") == "pass":
        return "PASS*"      # rescued by the judge
    if judge and judge.get("verdict") == "fail":
        return "FAIL"
    # no judge ran (skip / disabled): WEAK stays WEAK, FAIL stays FAIL
    return h


def write_reports(run_dir: str, questions: List[Dict[str, Any]],
                  results: Dict[str, Dict[str, Any]], meta: Dict[str, Any]) -> str:
    recs = [results[q["id"]] for q in questions if q["id"] in results]
    total = len(recs)

    final = {r["id"]: _final_status(r) for r in recs}
    n_pass = sum(1 for s in final.values() if s in ("PASS", "PASS*"))
    n_weak = sum(1 for s in final.values() if s == "WEAK")
    n_fail = sum(1 for s in final.values() if s == "FAIL")
    n_rescued = sum(1 for s in final.values() if s == "PASS*")
    avg_elapsed = round(sum(r["elapsed_s"] for r in recs) / total, 2) if total else 0
    avg_chars = round(sum(r["answer_chars"] for r in recs) / total, 1) if total else 0

    # per-category breakdown
    cat: Dict[str, Dict[str, int]] = {}
    for r in recs:
        c = cat.setdefault(r["category"], {"pass": 0, "weak": 0, "fail": 0})
        s = final[r["id"]]
        if s in ("PASS", "PASS*"):
            c["pass"] += 1
        elif s == "WEAK":
            c["weak"] += 1
        else:
            c["fail"] += 1

    summary = {
        "run_dir": run_dir,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": C.BASE_URL,
        "run_mode": meta.get("run_mode"),
        "order": meta.get("order"),
        "shuffle_seed": meta.get("shuffle_seed"),
        "judge_available": meta.get("judge_available"),
        "judge_reason": meta.get("judge_reason"),
        "totals": {
            "asked": total,
            "pass": n_pass,
            "pass_rescued_by_judge": n_rescued,
            "weak": n_weak,
            "fail": n_fail,
            "pass_rate_pct": round(100.0 * n_pass / total, 1) if total else 0,
        },
        "avg_elapsed_s": avg_elapsed,
        "avg_answer_chars": avg_chars,
        "by_category": cat,
    }
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    # Markdown report
    md: List[str] = []
    md.append(f"# Tlamatini Daily Chat Test - {meta.get('tag')}")
    md.append("")
    md.append(f"- **When:** {summary['generated_at']}")
    md.append(f"- **Target:** {C.BASE_URL}")
    md.append(f"- **Run mode:** {meta.get('run_mode')}")
    if meta.get("order") == "randomized":
        md.append(f"- **Question order:** randomized (seed `{meta.get('shuffle_seed')}` — "
                  f"reproduce with `--seed {meta.get('shuffle_seed')}`)")
    else:
        md.append("- **Question order:** sequential")
    md.append(f"- **Questions asked:** {total}")
    md.append(f"- **LLM judge:** {'available' if meta.get('judge_available') else 'unavailable -- ' + str(meta.get('judge_reason'))}")
    md.append("")
    md.append("## Results")
    md.append("")
    md.append("| Outcome | Count | % |")
    md.append("|---|---:|---:|")
    md.append(f"| PASS (incl. {n_rescued} rescued by judge) | {n_pass} | {summary['totals']['pass_rate_pct']}% |")
    md.append(f"| WEAK | {n_weak} | {round(100.0*n_weak/total,1) if total else 0}% |")
    md.append(f"| FAIL | {n_fail} | {round(100.0*n_fail/total,1) if total else 0}% |")
    md.append("")
    md.append(f"- Average response time: **{avg_elapsed}s**")
    md.append(f"- Average answer length: **{avg_chars} chars**")
    md.append("")
    md.append("## By category")
    md.append("")
    md.append("| Category | Pass | Weak | Fail |")
    md.append("|---|---:|---:|---:|")
    for c in sorted(cat):
        v = cat[c]
        md.append(f"| {c} | {v['pass']} | {v['weak']} | {v['fail']} |")
    md.append("")

    failures = [r for r in recs if final[r["id"]] in ("WEAK", "FAIL")]
    md.append(f"## Failures & weak answers ({len(failures)})")
    md.append("")
    if not failures:
        md.append("_None -- every answer passed._")
    for r in failures:
        md.append(f"### {r['id']} [{final[r['id']]}] - {r['category']}")
        md.append(f"**Q:** {r['question']}")
        why = ", ".join(r["heuristic"].get("reasons", [])) or "n/a"
        md.append(f"- heuristic: {r['heuristic']['status']} ({why})")
        if r.get("judge"):
            j = r["judge"]
            md.append(f"- judge: {j.get('verdict')} (score={j.get('score')}) - {j.get('reason')}")
        ans = (r["answer"] or "").replace("\n", " ")
        md.append(f"- answer ({r['answer_chars']} chars): {ans[:300]}")
        md.append("")

    report_path = os.path.join(run_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    return report_path


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Tlamatini daily chat test (Playwright).")
    ap.add_argument("--bank", choices=["full", "wrapped"], default="full",
                    help="'full' = the 1000-question bank; 'wrapped' = one functional "
                         "question per wrapped chat-agent, plus an email-attachment "
                         "scenario (50)")
    ap.add_argument("--count", type=int, default=1000, help="number of questions (default 1000)")
    ap.add_argument("--start", type=int, default=0, help="0-based offset into the bank")
    ap.add_argument("--sample", type=int, default=0,
                    help="pick N questions EVENLY SPACED across the full bank "
                         "(cross-category representative); overrides --start/--count")
    ap.add_argument("--select", default=None,
                    help="Run ONLY the questions matching these comma-separated tokens. "
                         "A token matches a question's id, category, wrapped-agent key, or "
                         "display name (case-insensitive, substring; with aliases such as "
                         "'emailer'->send_email). E.g. --select emailer  (or send_email / W041). "
                         "Overrides --start/--count/--sample.")
    ap.add_argument("--list", action="store_true",
                    help="List every question in the chosen --bank (id / category / key / text) "
                         "and exit, so you can discover --select tokens.")
    ap.add_argument("--no-shuffle", action="store_true",
                    help="ask questions in the bank's fixed order (default: RANDOMIZED "
                         "execution order each run, so order-dependent bugs surface)")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed for the randomized question order (default: a fresh random "
                         "seed, logged so a failing run can be reproduced with --seed)")
    ap.add_argument("--timeout", type=int, default=360,
                    help="per-question timeout in seconds (default 360)")
    ap.add_argument("--not-ready-retries", type=int, default=8,
                    help="times to wait+retry a question when the server says 'agent not ready'")
    ap.add_argument("--not-ready-backoff", type=float, default=20.0,
                    help="seconds to wait between 'agent not ready' retries")
    ap.add_argument("--abort-after-consecutive-fails", type=int, default=12,
                    help="abort the run if this many questions FAIL in a row (server wedged)")
    ap.add_argument("--base-url", default=None, help="override base URL")
    ap.add_argument("--user", default=C.USERNAME)
    ap.add_argument("--password", default=C.PASSWORD)
    ap.add_argument("--headless", action="store_true", help="run headless (default: visible Chrome)")
    ap.add_argument("--slowmo", type=int, default=0, help="Playwright slow_mo ms")
    ap.add_argument("--clear-every", type=int, default=0,
                    help="clear chat history every N questions (0=never; a fresh clear runs at start)")
    ap.add_argument("--no-fresh-start", action="store_true", help="do NOT clear history before the loop")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM judge on failures")
    ap.add_argument("--judge-model", default=None, help="Anthropic model id for the judge")
    ap.add_argument("--out", default=C.DEFAULT_OUT_DIR, help="reports directory")
    ap.add_argument("--resume", default=None, help="resume a run dir (skip already-answered ids)")
    ap.add_argument("--hold", type=int, default=0, help="seconds to keep the browser open at the end")
    args = ap.parse_args()

    if args.base_url:
        C.BASE_URL = args.base_url.rstrip("/")

    if args.bank == "wrapped":
        from wrapped_questions import build_wrapped_questions
        questions = build_wrapped_questions()
    else:
        questions = build_questions()

    # --list: print the chosen bank and exit (discover --select tokens).
    if args.list:
        print(f"Bank '{args.bank}' -- {len(questions)} questions:")
        for q in questions:
            key = q.get("key", "")
            keytxt = f" key={key}" if key else ""
            print(f"  {q['id']}  {q['category']:24s}{keytxt}  {q['text'][:70]}")
        return 0

    if args.select:
        tokens = [t for t in args.select.split(",") if t.strip()]
        subset = [q for q in questions if _matches_select(q, tokens)]
        if not subset:
            _log(f"!! --select '{args.select}' matched 0 questions in bank '{args.bank}'. "
                 f"Run with --list to see valid tokens.")
            return 2
        _log(f"--select '{args.select}' matched {len(subset)} question(s): "
             f"{', '.join(q['id'] + '=' + q['category'] for q in subset)}")
    elif args.sample and args.sample > 0:
        step = max(1, len(questions) // args.sample)
        subset = questions[::step][:args.sample]
    else:
        subset = questions[args.start: args.start + args.count]

    # Randomize the EXECUTION ORDER of the selected subset. Selection semantics
    # (--start/--count/--sample, incl. --sample's cross-category spacing) are
    # preserved -- only the order in which the same set of questions is asked is
    # shuffled, so order-dependent / state-leakage bugs surface instead of being
    # masked by an always-identical sequence. The seed is logged so a failing run
    # can be replayed deterministically with --seed <N> (and --resume).
    if args.no_shuffle:
        shuffle_seed = None
    else:
        shuffle_seed = args.seed if args.seed is not None else random.randrange(1, 2**31 - 1)
        random.Random(shuffle_seed).shuffle(subset)

    # run dir
    tag = _now_tag()
    if args.resume:
        run_dir = args.resume
        tag = os.path.basename(run_dir.rstrip("/\\")).replace("run_", "")
    else:
        run_dir = os.path.join(args.out, f"run_{tag}")
    os.makedirs(run_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.jsonl")
    existing = _load_existing(results_path)

    run_mode = "Multi-Turn ON, ACPX OFF, Ask-Execs OFF, Exec-Report OFF, Internet OFF"
    _log("=" * 70)
    _log(f"Tlamatini daily chat test  |  run dir: {run_dir}")
    _log(f"Target {C.BASE_URL}  |  questions {len(subset)} (start={args.start})")
    _log(f"Run mode: {run_mode}")
    if shuffle_seed is None:
        _log("Question order: SEQUENTIAL (--no-shuffle)")
    else:
        _log(f"Question order: RANDOMIZED  |  seed={shuffle_seed}  "
             f"(reproduce this exact order with: --seed {shuffle_seed})")
    _log(f"Already answered (resume): {len(existing)}")
    for c, n in sorted(category_counts(subset).items()):
        _log(f"  category {c:18s} {n}")
    _log("=" * 70)

    h = Harness(args)
    pending = [q for q in subset if q["id"] not in existing]

    with sync_playwright() as p:
        browser = h.launch(p)
        try:
            h.login()
            h.goto_chat()
            h.set_toggles()
            if not args.no_fresh_start:
                h.clear_history()

            consecutive_fail = 0
            aborted = False
            with open(results_path, "a", encoding="utf-8") as out:
                for idx, q in enumerate(pending, 1):
                    label = f"[{idx}/{len(pending)}] {q['id']} ({q['category']})"
                    _log(f"{label}: {q['text'][:80]}")
                    try:
                        rec = h.ask_one(q, timeout_ms=args.timeout * 1000)
                    except Exception as e:
                        _log(f"  EXCEPTION: {e}")
                        traceback.print_exc()
                        rec = {
                            "id": q["id"], "category": q["category"], "question": q["text"],
                            "answer": "", "answer_chars": 0, "elapsed_s": 0,
                            "started_observed": False, "completed": False,
                            "heuristic": {"status": "FAIL", "reasons": [f"exception:{e}"], "chars": 0},
                            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                        }
                        h.recover()
                    existing[q["id"]] = rec
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    st = rec["heuristic"]["status"]
                    _log(f"  -> {st}  ({rec['answer_chars']} chars, {rec['elapsed_s']}s)")

                    # circuit breaker: stop logging garbage if the server is wedged
                    consecutive_fail = consecutive_fail + 1 if st == "FAIL" else 0
                    if consecutive_fail >= args.abort_after_consecutive_fails:
                        _log(f"!! ABORTING: {consecutive_fail} consecutive FAILs -- the server "
                             f"appears wedged. Re-run with --resume {run_dir} once it recovers.")
                        aborted = True
                        break

                    if args.clear_every and idx % args.clear_every == 0:
                        h.clear_history()
            if aborted:
                _log("Run aborted early (circuit breaker). Partial results saved.")
        finally:
            if args.hold > 0:
                _log(f"Holding browser open for {args.hold}s...")
                time.sleep(args.hold)
            browser.close()

    # -- LLM judge on the failures/weak --
    judge_available = False
    judge_reason = "disabled (--no-judge)"
    if not args.no_judge:
        to_judge = [r for r in existing.values()
                    if r["heuristic"]["status"] in ("WEAK", "FAIL")
                    and r.get("answer")]   # nothing to judge if truly empty
        if to_judge:
            _log(f"Judging {len(to_judge)} weak/failed answers with the LLM judge...")
            for r in to_judge:
                v = h.judge.judge(r["question"], r["answer"])
                r["judge"] = v
            judge_available = h.judge.available
            judge_reason = "" if h.judge.available else h.judge.reason_unavailable
            # rewrite results.jsonl with judge verdicts merged in
            with open(results_path, "w", encoding="utf-8") as out:
                for q in subset:
                    if q["id"] in existing:
                        out.write(json.dumps(existing[q["id"]], ensure_ascii=False) + "\n")
        else:
            judge_available = True
            judge_reason = "no weak/failed answers to judge"

    meta = {
        "tag": tag, "run_mode": run_mode,
        "judge_available": judge_available, "judge_reason": judge_reason,
        "order": "sequential" if shuffle_seed is None else "randomized",
        "shuffle_seed": shuffle_seed,
    }
    report_path = write_reports(run_dir, subset, existing, meta)

    # console summary
    with open(os.path.join(run_dir, "summary.json"), "r", encoding="utf-8") as fh:
        s = json.load(fh)
    t = s["totals"]
    _log("=" * 70)
    _log(f"DONE. asked={t['asked']} pass={t['pass']} weak={t['weak']} fail={t['fail']} "
         f"({t['pass_rate_pct']}% pass)")
    _log(f"Report : {report_path}")
    _log(f"Summary: {os.path.join(run_dir, 'summary.json')}")
    _log("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
