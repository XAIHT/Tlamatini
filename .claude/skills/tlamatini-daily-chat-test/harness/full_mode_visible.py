"""FULL MODE on a big cloud model - VISIBLE E2E (Angela Lopez Mendoza, 2026-10-01).

The mirror of ``compact_mode_visible.py``.  With a model whose window holds
Tlamatini's COMPLETE request (default ``nemotron-3-ultra:cloud``, 262,144
tokens) she must send the complete request - the whole prompt, every enabled
tool, ACPX free to tick - show NO Compact-mode dialog or badge, and answer the
same one-shot questions, plus one Multi-Turn question.

Run it VISIBLE (headed Chrome, Shoter photos), never headless:

    python full_mode_visible.py [--model nemotron-3-ultra:cloud]

COST - a complete request is ~100K+ prompt tokens of the user's cloud usage.
So the run (a) points EVERY cloud model key at the model under test (a key
left on a paid model would fail without credits), (b) switches the at-rest
gauge probes OFF (each probe re-sends the whole request), and (c) asks only
six questions.  The dev config.json comes back byte for byte at the end.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compact_mode_visible as cmv               # noqa: E402  (shared page/photo helpers)

from playwright.sync_api import sync_playwright  # noqa: E402

C = cmv.C
RUN_DIR = os.path.join(cmv.REPO, "Temp", "full_mode_visible")
# The shared helpers read these module globals at call time.
cmv.RUN_DIR = RUN_DIR
cmv.PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
cmv.RUN_LOG = os.path.join(RUN_DIR, "run.log")
cmv.BACKUP = os.path.join(RUN_DIR, "config.backup.json")

say, check, shot, ask = cmv.say, cmv.check, cmv.shot, cmv.ask
wait_idle, set_toggle = cmv.wait_idle, cmv.set_toggle

#: The chat path's own model keys (they may hold a LOCAL model).
CHAT_KEYS = ("chained-model", "access_aimed_prompt_model", "unified_agent_model",
             "mcp_files_search_model", "internet_classifier_model", "web_summarizer_model",
             "summarizer_model")


def is_cloud_model(value) -> bool:
    return isinstance(value, str) and bool(re.search(r"[:\-]cloud$", value.strip()))


def prepare_config(model: str) -> str:
    os.makedirs(RUN_DIR, exist_ok=True)
    shutil.copyfile(cmv.REAL_CONFIG, cmv.BACKUP)
    sha_before = cmv.sha256(cmv.REAL_CONFIG)
    say("dev config.json backed up (sha256 %s...)" % sha_before[:16])
    with open(cmv.REAL_CONFIG, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    changed = []
    for key, value in list(config.items()):
        if key in CHAT_KEYS or is_cloud_model(value):
            if value != model:
                changed.append(key)
            config[key] = model
    config["ollama_base_url"] = "http://127.0.0.1:11434"
    config["unified_agent_base_url"] = "http://127.0.0.1:11434"
    config["context_compact_mode"] = "auto"
    config["context_gauge_probe_enable"] = False
    config["context_gauge_probe_after_answer"] = False
    if "context_ceiling_tokens" in config:
        config["context_ceiling_tokens"] = 0
    with open(cmv.REAL_CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    say("dev config now points %d model key(s) at %s; gauge probes OFF (they would "
        "re-send the whole request): %s" % (len(changed), model, ", ".join(changed)))
    return sha_before


def finish(browser, sha_before, model: str) -> int:
    if browser is not None:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    cmv.stop_server(cmv.PORT)

    text = cmv.server_log()
    lines = text.splitlines()
    full = [ln for ln in lines if "[CONTEXT-FIT]" in ln and model in ln and "FULL -" in ln]
    compact = [ln for ln in lines if "[CONTEXT-FIT]" in ln and model in ln and "COMPACT -" in ln]
    cuts = [ln for ln in lines if "[CONTEXT-WINDOW]" in ln and "CUT" in ln]
    tracebacks = [ln for ln in lines if "Traceback" in ln]
    reals = [int(m) for m in re.findall(r"\[CONTEXT-REAL\][^\n]*prompt_eval_count=(\d+)", text)]
    for ln in full[:2]:
        say("   log: %s" % ln.strip()[:300])
    say("   REAL prompt_eval_counts on this run: %s" % reals[-20:])
    check("7a the requests were sent COMPLETE (%d FULL fits, %d compact)" % (len(full), len(compact)),
          len(full) >= 5 and not compact)
    check("7b Ollama really read the complete request (largest REAL prompt %s tokens)"
          % (max(reals) if reals else "n/a"), bool(reals) and max(reals) >= 50000)
    check("7c no request was cut", not cuts, cuts[:2])
    check("7d tlamatini.log has no Traceback (%d lines read)" % len(lines), not tracebacks,
          tracebacks[:3])

    cmv.restore_config()
    check("8 the dev config.json is back byte for byte", cmv.sha256(cmv.REAL_CONFIG) == sha_before)

    failed = [name for name, ok, _ in cmv.RESULTS if not ok]
    say("=" * 78)
    say("photos: %s" % cmv.PHOTOS_DIR)
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(cmv.RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    say("VERDICT: PASSED - all %d checks" % len(cmv.RESULTS))
    say("=" * 78)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nemotron-3-ultra:cloud")
    model = parser.parse_args().model

    os.makedirs(cmv.PHOTOS_DIR, exist_ok=True)
    for old in os.listdir(cmv.PHOTOS_DIR):
        if old.lower().endswith(".png"):
            try:
                os.remove(os.path.join(cmv.PHOTOS_DIR, old))
            except OSError:
                pass
    try:
        os.remove(cmv.RUN_LOG)
    except OSError:
        pass

    say("=" * 78)
    say("FULL MODE ON %s - VISIBLE E2E   (Angela Lopez Mendoza)" % model)
    say("=" * 78)
    sha_before = prepare_config(model)

    if cmv.stop_server(cmv.PORT):
        time.sleep(2.0)
    state = cmv.ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        cmv.restore_config()
        return 4

    browser = None
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as exc:                    # noqa: BLE001
            say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_context(no_viewport=True).new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)
        page.on("dialog", lambda d: (say("   NATIVE ALERT: %s" % d.message[:200]), d.accept()))
        try:
            # 1. log in --------------------------------------------------------
            page.goto(C.BASE_URL + C.LOGIN_PATH)
            page.fill(C.SEL["login_user"], C.USERNAME)
            page.fill(C.SEL["login_pass"], C.PASSWORD)
            page.click(C.SEL["login_submit"])
            page.wait_for_load_state("networkidle")
            page.goto(C.BASE_URL + C.CHAT_PATH)
            page.wait_for_selector(C.SEL["chat_input"])
            page.bring_to_front()
            if not check("1 logged in and the chat page is ready", wait_idle(page, 300)):
                shot(page, "01_not_ready")
                return finish(browser, sha_before, model)
            # give the at-rest fit time to reach the page
            page.wait_for_timeout(15000)
            shot(page, "01_chat_ready")

            # 2. a big model: no Compact mode anywhere --------------------------
            check("2a no Compact-mode dialog", page.locator("#tlm-compact-overlay").count() == 0)
            badge = page.locator("#compact-mode-badge")
            check("2b no Compact-mode badge", not (badge.count() and badge.is_visible()))
            check("2c ACPX can be ticked", not page.is_disabled(C.SEL["t_acpx"]))

            # 3. one-shot questions with the COMPLETE request ---------------------
            page.click(C.SEL["clean_history"])
            page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last.click()
            page.wait_for_timeout(2500)
            wait_idle(page, 240)
            for key in ("t_multi_turn", "t_ask_execs", "t_internet", "t_exec_report", "t_acpx"):
                set_toggle(page, C.SEL[key], False)

            fin, ans, _ = ask(page, "What is the actual CPU usage, memory usage and disk space?",
                              "03a_metrics")
            metrics = cmv.last_metrics(cmv.server_log())
            check("3a the metrics answer finished", fin)
            check("3a it reports the LIVE metrics (from System-Metrics)",
                  cmv.mentions_any_metric(ans, metrics) and "%" in ans, "metrics %s" % metrics)

            fin, ans, _ = ask(page, "What time is it right now?", "03b_time")
            now = datetime.datetime.now()
            check("3b the time answer finished", fin)
            check("3b it gives today's date or the current hour",
                  any(s in ans for s in (str(now.year), now.strftime("%H:"), now.strftime("%B"),
                                         now.strftime("%Y-%m-%d"))), ans[:200])

            fin, ans, _ = ask(page, "Who created you?", "03c_identity")
            check("3c the identity answer finished", fin)
            check("3c it knows Angela created Tlamatini", "Angela" in ans, ans[:200])

            fin, ans, _ = ask(page, "Show me an HTML table of three planets and their diameters in km.",
                              "03d_table")
            check("3d the table answer finished", fin)
            check("3d it rendered an HTML table", page.evaluate(cmv.LAST_BOT_HAS_TABLE_JS))
            worst = page.evaluate(cmv.LAST_TABLE_MIN_CONTRAST_JS)
            check("3d its text is readable (lowest cell contrast %s, need >= 3)" % worst, worst >= 3)

            fin, ans, _ = ask(page, "What did I ask you in my previous message, just before this one?",
                              "03e_history")
            check("3e the follow-up answer finished", fin)
            check("3e it remembers the history (the planets table)",
                  any(w in ans.lower() for w in ("table", "planet", "diamet", "tabla", "planeta")),
                  ans[:200])

            # 4. Multi-Turn on the same model -----------------------------------
            set_toggle(page, C.SEL["t_multi_turn"], True)
            fin, ans, _ = ask(page, "What is today's date?", "04_multi_turn_date")
            check("4 Multi-Turn answers too", fin and str(now.year) in ans, ans[:200])
            set_toggle(page, C.SEL["t_multi_turn"], False)
            shot(page, "05_final")
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-700:])
            shot(page, "99_crash")
        return finish(browser, sha_before, model)


if __name__ == "__main__":
    try:
        code = main()
    finally:
        cmv.restore_config()
        shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(code)
