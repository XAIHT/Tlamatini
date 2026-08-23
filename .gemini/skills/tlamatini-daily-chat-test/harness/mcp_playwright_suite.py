# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tlamatini — 10-MCP Playwright suite (visible Chrome).

Drives the LIVE Tlamatini chat UI through TEN different external MCP servers,
each one **completely runnable by Tlamatini herself** (no API key — Docker
`mcp/*` images she launches, or an already-catalogued server). Every test
exercises MULTIPLE agents: the External-MCP tool family (import → set_active →
wait → list_tools → call) PLUS File-Creator to persist a one-line result (a few
also lean on the MCP's own multi-tool surface).

It reuses the daily-chat-test harness verbatim (login / toggle / clear / ask /
recover / report in run_test.py + config.py), with the toggles pinned to the
operator-test convention: Multi-Turn ON, Exec-Report ON, Ask-Execs OFF, ACPX
OFF, Internet OFF — and a fresh history clear before the loop.

Run it later (from this directory):
    python mcp_playwright_suite.py                 # all 10, visible Chrome
    python mcp_playwright_suite.py --headless      # no window
    python mcp_playwright_suite.py --count 3        # first 3 only
    python mcp_playwright_suite.py --select memory,sqlite,fetch
Reports land in ./reports/run_<timestamp>/ (results.jsonl + report.md + summary.json).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import traceback
from types import SimpleNamespace

import config as C
from run_test import Harness, write_reports, _log, _now_tag

from playwright.sync_api import sync_playwright

# Make logging unicode-safe even when stdout/stderr are REDIRECTED to a file:
# Windows defaults those to cp1252, which raises UnicodeEncodeError on arrows /
# emoji / box glyphs — that crashed the run mid-suite once and closed the
# browser. errors='replace' so a stray glyph can never kill the run again.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# Operator-test toggles (overrides config.py's defaults): Exec-Report ON too.
C.TOGGLE_STATE.update({
    "t_multi_turn": True,
    "t_acpx": False,
    "t_exec_report": True,
    "t_ask_execs": False,
    "t_internet": False,
})


def _t(key: str, name: str, config: dict, task: str) -> dict:
    """Build one MCP test prompt. `config` is the mcpServers JSON to import."""
    cfg = json.dumps(config, ensure_ascii=False)
    text = (
        f"Tlamatini, add and test the **{name} MCP** end to end, using ONLY the External MCP "
        f"tools and the resulting ext__{key}__* tools — NO shell, NO Executer, NO Docker "
        f"commands of your own (the MCP launches its own process).\n\n"
        f"1. Call external_mcp_import with this exact config: {cfg}\n"
        f"2. Call external_mcp_set_active('{key}').\n"
        f"3. Confirm it is connected: call external_mcp_wait('{key}', 150) if you have that tool, "
        f"otherwise external_mcp_status — BE PATIENT, a first-run Docker image pull is slow, do NOT give up.\n"
        f"4. Call external_mcp_list_tools to learn the exact tool names/args for '{key}'.\n"
        f"5. {task}\n"
        f"6. Then use chat_agent_file_creator to save a ONE-LINE summary of the result to a file named "
        f"'mcp_suite_{key}.txt' in your Temp directory.\n"
        f"7. Report what each MCP tool returned in one compact HTML table (class 'exec-report-table') "
        f"titled '{name} MCP — Verified'.\n"
        f"End with END-RESPONSE."
    )
    return {"id": f"MCP-{key}", "category": f"mcp:{key}", "key": key, "display": name, "text": text}


MCP_TESTS = [
    _t("memory", "Memory / Knowledge-Graph",
       {"mcpServers": {"memory": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/memory"]}}},
       "Create 2 entities (Tlamatini=System, Angela=Person) with one observation each, relate them "
       "Angela —CREATED→ Tlamatini, then read_graph and report the entity + relation counts."),
    _t("sqlite", "SQLite",
       {"mcpServers": {"sqlite": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/sqlite", "--db-path", "/tmp/suite.db"]}}},
       "Create a table parts(id INTEGER PRIMARY KEY, name TEXT, qty INTEGER), insert 3 rows, then run "
       "SELECT SUM(qty) and report the total."),
    _t("redis", "Redis",
       {"mcpServers": {"redis": {"command": "docker", "args": ["run", "-i", "--rm", "--network", "redis-mcp-net", "-e", "REDIS_HOST=redis-server", "-e", "REDIS_PORT=6379", "mcp/redis"]}}},
       "SET suite:greeting='hello from the suite' with a 120s TTL, GET it back, and report the value + its remaining TTL."),
    _t("fetch", "Fetch (web to markdown)",
       {"mcpServers": {"fetch": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/fetch"]}}},
       "Fetch https://example.com and report the page's main heading / title text."),
    _t("time", "Time / Timezones",
       {"mcpServers": {"time": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/time"]}}},
       "Get the current time in UTC and convert it to Asia/Tokyo; report both."),
    _t("everything", "Everything (reference server)",
       {"mcpServers": {"everything": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/everything"]}}},
       "Call the server's 'echo' tool with 'ping from Tlamatini' and its 'add' tool with a=21,b=21; report both results."),
    _t("sequentialthinking", "Sequential-Thinking",
       {"mcpServers": {"sequentialthinking": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/sequentialthinking"]}}},
       "Use the sequential-thinking tool to reason in 2-3 steps: a train covers 60 km in 45 minutes — what is its speed in km/h? Report the final answer."),
    _t("filesystem", "Filesystem (sandboxed /tmp)",
       {"mcpServers": {"filesystem": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/filesystem", "/tmp"]}}},
       "Write a file /tmp/hello.txt containing 'Tlamatini was here' via the MCP, read it back, then list /tmp; report the file's contents and the count of entries in /tmp."),
    _t("git", "Git",
       {"mcpServers": {"git": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/git"]}}},
       "List the git tools the server exposes and report their names (this server is best-effort — if it needs a repository path, report that clearly instead)."),
    _t("puppeteer", "Puppeteer (headless browser)",
       {"mcpServers": {"puppeteer": {"command": "docker", "args": ["run", "-i", "--rm", "mcp/puppeteer"]}}},
       "Navigate to https://example.com via the MCP and report the page title (best-effort — if a screenshot/navigate tool is unavailable, report the tool list instead)."),
]


def _build_args(ns) -> SimpleNamespace:
    return SimpleNamespace(
        headless=ns.headless, slowmo=0, judge_model=None,
        user=C.USERNAME, password=C.PASSWORD,
        not_ready_retries=6, not_ready_backoff=20.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Tlamatini 10-MCP Playwright suite.")
    ap.add_argument("--headless", action="store_true", help="run without a visible window")
    ap.add_argument("--count", type=int, default=len(MCP_TESTS), help="run only the first N tests")
    ap.add_argument("--select", default=None, help="comma-separated keys to run (e.g. memory,sqlite)")
    ap.add_argument("--timeout", type=int, default=420, help="per-test timeout seconds (default 420)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--hold", type=int, default=8, help="seconds to keep the browser open at the end")
    ap.add_argument("--out", default=C.DEFAULT_OUT_DIR)
    a = ap.parse_args()
    if a.base_url:
        C.BASE_URL = a.base_url.rstrip("/")

    tests = MCP_TESTS
    if a.select:
        keys = {k.strip().lower() for k in a.select.split(",") if k.strip()}
        tests = [t for t in MCP_TESTS if t["key"] in keys]
    tests = tests[: a.count]
    if not tests:
        _log("No tests selected.")
        return 2

    tag = _now_tag()
    run_dir = os.path.join(a.out, f"run_mcp_{tag}")
    os.makedirs(run_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.jsonl")

    run_mode = "Multi-Turn ON, Exec-Report ON, ACPX OFF, Ask-Execs OFF, Internet OFF"
    _log("=" * 72)
    _log(f"Tlamatini 10-MCP suite | run dir: {run_dir}")
    _log(f"Target {C.BASE_URL} | tests: {len(tests)} ({', '.join(t['key'] for t in tests)})")
    _log(f"Run mode: {run_mode}")
    _log("NOTE: drives your LIVE chat + clears history first. First-run Docker pulls are slow.")
    _log("=" * 72)

    h = Harness(_build_args(a))
    existing: dict = {}
    with sync_playwright() as p:
        browser = h.launch(p)
        try:
            h.login()
            h.goto_chat()
            h.set_toggles()
            h.clear_history()
            with open(results_path, "a", encoding="utf-8") as out:
                for idx, q in enumerate(tests, 1):
                    _log(f"[{idx}/{len(tests)}] {q['id']} — {q['display']}")
                    try:
                        rec = h.ask_one(q, timeout_ms=a.timeout * 1000)
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
        finally:
            if a.hold > 0:
                time.sleep(a.hold)
            browser.close()

    meta = {"tag": "mcp_" + tag, "run_mode": run_mode, "judge_available": False,
            "judge_reason": "judge skipped for the MCP suite", "order": "sequential",
            "shuffle_seed": None}
    report_path = write_reports(run_dir, tests, existing, meta)
    passed = sum(1 for r in existing.values() if r["heuristic"]["status"] in ("PASS", "PASS*"))
    _log("=" * 72)
    _log(f"DONE. {passed}/{len(tests)} PASS (heuristic). Report: {report_path}")
    _log("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
