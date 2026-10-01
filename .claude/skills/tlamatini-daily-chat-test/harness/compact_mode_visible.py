#!/usr/bin/env python
# Tlamatini Author Banner - do not remove
"""VISIBLE proof: COMPACT MODE - one-shot questions work on the SMALL model the
installed Tlamatini is configured with (Angela, 2026-10-01).

Angela: *"make 100% visual tests to make sure with the actual model configured
in Tlamatini installed, so all the one-shot invocations must visually work!"*

The model is NOT chosen here: it is read from the INSTALLED app's
C:\\Tlamatini\\config.json (on 2026-10-01: qwen2.5:latest on the local Ollama,
whose real window is 16,384 tokens per request). The dev config is pointed at
exactly those models for the run and restored byte for byte afterwards.

Steps (headed Chrome, real login, real model, every step photographed by Shoter):
  0. Back up the dev config; copy the installed app's model + Ollama URL keys
     into it; start the SOURCE server on :8019 in a visible console.
  1. Log in; the chat page is ready.
  2. The Compact-mode dialog opens on its own and says the right things.
  3. "Continue in Compact mode": the badge shows, ACPX is locked off and a
     click cannot turn it on.
  4. The badge re-opens the dialog; Escape closes it (dialog policy).
  5. ONE-SHOT questions on the small model, each judged on what it must contain:
     live CPU/memory/disk, the time, who created Tlamatini, code, an HTML table,
     a follow-up that needs the history, and an honest "not available".
  6. The same small model with Multi-Turn ON.
  7. tlamatini.log: every request was COMPACT, none was cut by Ollama (or, if
     one was, it was re-fitted and sent again), no Traceback.
  8. The dev config is back byte for byte.

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import ast
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback

PORT = 8019
os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUN_DIR = os.path.join(REPO, "Temp", "compact_mode_visible")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
REAL_CONFIG = os.path.join(REPO, "Tlamatini", "agent", "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
INSTALLED_CONFIG = r"C:\Tlamatini\config.json"
MODEL_KEYS = ("embeding-model", "chained-model", "access_aimed_prompt_model",
              "unified_agent_model", "mcp_files_search_model", "internet_classifier_model",
              "web_summarizer_model", "ollama_base_url", "unified_agent_base_url")
DESKTOP_PROBE = os.path.join(os.path.expanduser("~"), "Desktop", "compact_test.txt")

RESULTS: list = []
PHOTOS: list = []
ALERTS: list = []


# ------------------------------------------------------------------ output
def say(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:500]))
    say(("[PASS] " if ok else "[FAIL] ") + name + (("   -> " + str(detail)[:400]) if detail else ""))
    return bool(ok)


def shot(page, name):
    try:
        page.bring_to_front()
        page.wait_for_timeout(700)
    except Exception:                               # noqa: BLE001
        pass
    path = take_shot(PHOTOS_DIR, "%s.png" % name, runtime_base=RUN_DIR)
    PHOTOS.append((name, path))
    say("   PHOTO %s -> %s" % (name, path))
    return path


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


_RESTORED = {"done": False}


def restore_config():
    if _RESTORED["done"] or not os.path.isfile(BACKUP):
        return
    shutil.copyfile(BACKUP, REAL_CONFIG)
    _RESTORED["done"] = True
    say("dev config.json restored from %s" % BACKUP)


def server_log():
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# ------------------------------------------------------------------ page helpers
IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
BOT_TEXTS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message.bot-message'))
  .map(m => { const b = m.querySelector('.automated-message-body') || m; return b.innerText || ''; })"""
LAST_BOT_HAS_TABLE_JS = """() => { const m = document.querySelectorAll('#chat-log .message.bot-message');
  return m.length ? !!m[m.length - 1].querySelector('table') : false; }"""
# The LOWEST text/background contrast among the last answer table's cells
# (WCAG formula).  A table that renders white-on-white passed the check above
# on 2026-10-01 while nobody could read it - this is the check that sees it.
LAST_TABLE_MIN_CONTRAST_JS = """() => {
  const m = document.querySelectorAll('#chat-log .message.bot-message');
  const t = m.length ? m[m.length - 1].querySelector('table') : null;
  if (!t) return 0;
  const rgb = v => { const x = /rgba?\\(([^)]+)\\)/.exec(v || ''); if (!x) return null;
    const p = x[1].split(',').map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  // A gradient/image background cannot be measured: that cell is SKIPPED
  // (nemotron's dark-gradient header read as white-on-white without this).
  const bg = el => { for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const s = getComputedStyle(n); if (s.backgroundImage && s.backgroundImage !== 'none') return null;
    const c = rgb(s.backgroundColor); if (c && c.a >= 0.5) return c; } return null; };
  let worst = 99;
  t.querySelectorAll('td, th').forEach(cell => {
    if (!(cell.innerText || '').trim()) return;
    const f = rgb(getComputedStyle(cell).color), b = bg(cell); if (!f || !b) return;
    const x = lum(f), y = lum(b); worst = Math.min(worst, (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)); });
  return Math.round(worst * 100) / 100; }"""


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        page.wait_for_timeout(500)
    return False


def set_toggle(page, selector, wanted):
    if page.locator(selector).count() and page.is_checked(selector) != wanted:
        page.click(selector, force=True)
        page.wait_for_timeout(300)


def is_busy_text(text):
    low = text.strip().lower()
    return any(marker.lower() in low for marker in C.BUSY_MARKERS) or not low


def ask(page, question, label, timeout=360):
    """Send one question; return (finished, answer_text, seconds)."""
    before = len(page.evaluate(BOT_TEXTS_JS))
    started = time.time()
    page.fill(C.SEL["chat_input"], question)
    page.click(C.SEL["chat_submit"])
    # The page locks only when the server echoes the question, and the server
    # may still be finishing the previous answer's cleanup (the Tier-2 reaper
    # took ~2 s on 2026-10-01): a fixed 1.5 s wait once read that gap as
    # "answered, 0 chars".  Wait until the page is really BUSY first.
    busy_deadline = time.time() + 45
    while time.time() < busy_deadline and page.evaluate(IDLE_JS):
        page.wait_for_timeout(250)
    finished = wait_idle(page, timeout)
    page.wait_for_timeout(800)
    texts = page.evaluate(BOT_TEXTS_JS)[before:]
    answer = "\n".join(t for t in texts if not is_busy_text(t)).strip()
    seconds = time.time() - started
    say("   ANSWER (%.1fs, %d chars): %s" % (seconds, len(answer), answer.replace("\n", " | ")[:420]))
    shot(page, label)
    return finished, answer, seconds


def last_metrics(log_text):
    found = re.findall(r"Actual system metrics: (\{[^}]*\})", log_text)
    if not found:
        return {}
    try:
        return ast.literal_eval(found[-1])
    except Exception:                               # noqa: BLE001
        return {}


def mentions_any_metric(answer, metrics):
    for value in metrics.values():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        for form in ("%.1f" % v, "%d" % round(v), "%.2f" % v):
            if form in answer:
                return True
    return False


# ------------------------------------------------------------------ main
def main():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    for old in os.listdir(PHOTOS_DIR):
        if old.lower().endswith(".png"):
            try:
                os.remove(os.path.join(PHOTOS_DIR, old))
            except OSError:
                pass
    try:
        os.remove(RUN_LOG)
    except OSError:
        pass

    say("=" * 78)
    say("COMPACT MODE ON THE INSTALLED APP'S SMALL MODEL - VISIBLE E2E   (Angela Lopez Mendoza)")
    say("=" * 78)

    # 0. the environment ------------------------------------------------
    if not os.path.isfile(INSTALLED_CONFIG):
        say("!! the installed app's config is missing: %s" % INSTALLED_CONFIG)
        return 4
    with open(INSTALLED_CONFIG, "r", encoding="utf-8-sig") as fh:
        installed = json.load(fh)
    model = str(installed.get("unified_agent_model") or installed.get("chained-model") or "")
    say("the INSTALLED Tlamatini is configured with: %s (on %s)"
        % (model, installed.get("ollama_base_url")))
    shutil.copyfile(REAL_CONFIG, BACKUP)
    sha_before = sha256(REAL_CONFIG)
    say("dev config.json backed up (sha256 %s...)" % sha_before[:16])
    with open(REAL_CONFIG, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    for key in MODEL_KEYS:
        if key in installed:
            config[key] = installed[key]
    config["context_compact_mode"] = "auto"
    if "context_ceiling_tokens" in config:
        config["context_ceiling_tokens"] = 0
    with open(REAL_CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    say("dev config now uses the installed app's models: %s"
        % {k: config.get(k) for k in MODEL_KEYS if k in installed})
    if os.path.exists(DESKTOP_PROBE):
        os.remove(DESKTOP_PROBE)

    if stop_server(PORT):
        time.sleep(2.0)
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return finish(None, sha_before, code_if_ok=4)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as exc:                    # noqa: BLE001
            say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)

        def on_alert(dialog):
            ALERTS.append(dialog.message)
            say("   NATIVE ALERT shown: %s" % dialog.message.replace("\n", " | ")[:300])
            dialog.accept()

        page.on("dialog", on_alert)

        try:
            # 1. log in -----------------------------------------------------
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
                return finish(browser, sha_before)
            shot(page, "01_chat_ready")

            # 2. the dialog opens on its own --------------------------------
            appeared = False
            deadline = time.time() + 240
            while time.time() < deadline:
                if page.locator("#tlm-compact-overlay").count():
                    appeared = True
                    break
                page.wait_for_timeout(1000)
            check("2a the Compact-mode dialog opened on its own", appeared)
            if appeared:
                text = page.inner_text("#tlm-compact-overlay")
                say("   DIALOG: %s" % text.replace("\n", " | ")[:700])
                check("2b it names the installed model", model in text, model)
                for need in ("System-Metrics", "Files-Search", "Current-Time", "ACPX",
                             "External MCPs", "Config"):
                    check("2c it explains '%s'" % need, need in text)
                check("2d it shows the model's window in tokens", bool(re.search(r"reads [\d,]+ tokens", text)))
                shot(page, "02_compact_dialog")

                # 3. continue -------------------------------------------------
                page.click("#tlm-compact-overlay .tlmcap-ok")
                page.wait_for_timeout(600)
            check("3a the dialog closed", page.locator("#tlm-compact-overlay").count() == 0)
            badge = page.locator("#compact-mode-badge")
            check("3b the Compact-mode badge is visible",
                  badge.count() and badge.is_visible(), badge.inner_text() if badge.count() else "")
            check("3c ACPX is locked off",
                  page.is_disabled(C.SEL["t_acpx"]) and not page.is_checked(C.SEL["t_acpx"]))
            page.click("#acpx-toggle", force=True)
            page.wait_for_timeout(1200)
            check("3d clicking ACPX cannot turn it on", not page.is_checked(C.SEL["t_acpx"]))
            shot(page, "03_badge_and_acpx_locked")

            # 4. badge -> dialog, Escape -> closed --------------------------
            badge.click()
            page.wait_for_timeout(600)
            check("4a the badge re-opens the dialog", page.locator("#tlm-compact-overlay").count() == 1)
            shot(page, "04_dialog_from_badge")
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            check("4b Escape closes it", page.locator("#tlm-compact-overlay").count() == 0)

            # 5. one-shot questions on the small model ----------------------
            page.click(C.SEL["clean_history"])
            page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last.click()
            page.wait_for_timeout(2500)
            wait_idle(page, 240)
            for key in ("t_multi_turn", "t_ask_execs", "t_internet", "t_exec_report"):
                set_toggle(page, C.SEL[key], False)

            fin, ans, _ = ask(page, "What is the actual CPU usage, memory usage and disk space?",
                              "05a_metrics")
            metrics = last_metrics(server_log())
            check("5a the metrics answer finished", fin)
            check("5a it reports the LIVE metrics (from System-Metrics)",
                  mentions_any_metric(ans, metrics) and "%" in ans,
                  "metrics %s" % metrics)

            fin, ans, _ = ask(page, "What time is it right now?", "05b_time")
            now = datetime.datetime.now()
            check("5b the time answer finished", fin)
            check("5b it gives today's date or the current hour",
                  any(s in ans for s in (str(now.year), now.strftime("%H:"), now.strftime("%B"),
                                         now.strftime("%Y-%m-%d"))), now.isoformat(timespec="minutes"))

            fin, ans, _ = ask(page, "Who created you?", "05c_identity")
            check("5c the identity answer finished", fin)
            check("5c it knows Angela created Tlamatini", "Angela" in ans)

            links = page.locator("#chat-log a:has-text('Load in canvas')")
            links_before = links.count()
            fin, ans, _ = ask(page, "Write a Python function factorial(n) that returns n factorial.",
                              "05d_code")
            check("5d the code answer finished", fin)
            check("5d it produced Python code",
                  links.count() > links_before or "def factorial" in ans,
                  "Load-in-canvas links %d -> %d" % (links_before, links.count()))

            fin, ans, _ = ask(page, "Show me an HTML table of three planets and their diameters in km.",
                              "05e_table")
            check("5e the table answer finished", fin)
            check("5e it rendered an HTML table", page.evaluate(LAST_BOT_HAS_TABLE_JS))
            worst = page.evaluate(LAST_TABLE_MIN_CONTRAST_JS)
            check("5e its text is readable (lowest cell contrast %s, need >= 3)" % worst, worst >= 3)

            # The model reads the last 8 messages in EVERY mode
            # (DBChatHistoryLoader.load(limit=8)), so "my FIRST question" is
            # out of reach for any model after five exchanges - ask about the
            # previous one, which a Compact request must still carry.
            fin, ans, _ = ask(page, "What did I ask you in my previous message, just before this one?",
                              "05f_history")
            check("5f the follow-up answer finished", fin)
            check("5f it remembers the history (the planets table)",
                  any(w in ans.lower() for w in ("table", "planet", "diamet", "tabla", "planeta")),
                  ans[:200])

            fin, ans, _ = ask(page, "Create a file named compact_test.txt on my Desktop containing the word hello.",
                              "05g_unavailable")
            check("5g the capability answer finished", fin)
            check("5g no file was created (no agents in Compact mode)", not os.path.exists(DESKTOP_PROBE))
            check("5g it says honestly that it cannot do it now",
                  bool(re.search(r"can.?t|cannot|not available|unavailable|unable|compact|larger model"
                                 r"|no (?:tengo|puedo)|not able", ans, re.IGNORECASE)), ans[:240])

            # 6. Multi-Turn on the same small model ---------------------------
            set_toggle(page, C.SEL["t_multi_turn"], True)
            fin, ans, _ = ask(page, "What is today's date?", "06_multi_turn_date")
            check("6 Multi-Turn on the small model answers too", fin and str(now.year) in ans, ans[:200])
            set_toggle(page, C.SEL["t_multi_turn"], False)

            badge_text = badge.inner_text() if badge.count() else ""
            say("   badge at the end: %s" % badge_text)
            shot(page, "07_final")
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-700:])
            shot(page, "99_crash")
        return finish(browser, sha_before)


def finish(browser, sha_before, code_if_ok=0):
    if browser is not None:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    stop_server(PORT)

    # 7. the app's own log ------------------------------------------------
    text = server_log()
    lines = text.splitlines()
    fits = [ln for ln in lines if "[CONTEXT-FIT]" in ln and "COMPACT -" in ln]
    cuts = [i for i, ln in enumerate(lines) if "[CONTEXT-WINDOW]" in ln and "CUT" in ln]
    refits = [ln for ln in lines if "re-fitting" in ln]
    tracebacks = [ln for ln in lines if "Traceback" in ln]
    reals = [int(m) for m in re.findall(r"\[CONTEXT-REAL\][^\n]*prompt_eval_count=(\d+)", text)]
    for ln in fits[:3]:
        say("   log: %s" % ln.strip()[:300])
    for i in cuts[:4]:
        say("   log: %s" % lines[i].strip()[:300])
    say("   REAL prompt_eval_counts on this run: %s" % reals[-20:])
    check("7a every request was fitted in COMPACT mode (%d fits logged)" % len(fits), len(fits) >= 8)
    check("7b no request was answered from a cut prompt",
          not cuts or len(refits) >= len(cuts),
          "%d cut(s) detected, %d re-fit(s)" % (len(cuts), len(refits)))
    check("7c tlamatini.log has no Traceback (%d lines read)" % len(lines), not tracebacks,
          tracebacks[:3])

    # 8. the dev config comes back exactly --------------------------------
    restore_config()
    check("8 the dev config.json is back byte for byte", sha256(REAL_CONFIG) == sha_before)

    failed = [name for name, ok, _ in RESULTS if not ok]
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    if code_if_ok:
        return code_if_ok
    say("VERDICT: ALL %d CHECKS PASSED" % len(RESULTS))
    say("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:                               # noqa: BLE001
        say("!! the harness crashed before it could finish:")
        say(traceback.format_exc())
        code = 1
    restore_config()
    shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(code)
