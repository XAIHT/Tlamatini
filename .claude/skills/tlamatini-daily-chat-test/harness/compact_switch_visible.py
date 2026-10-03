#!/usr/bin/env python
# Tlamatini Author Banner - do not remove
"""VISIBLE proof: the COMPACT MODE checkbox (Angela, 2026-10-02).

Angela: *"make 100% visible tests to make sure that each and all of your
implementations works 100% OK!"*

Headed real Chrome, the real login, the real chat page, the app's own log,
a Shoter photo of every step.  Two phases:

PHASE A - the SMALL model the installed app uses (local qwen2.5:latest):
  A1  log in; the chat page is ready.
  A2  the box switches ON by itself and is LOCKED (greyed, 🔒); the dialog
      opens on its own and explains it.
  A3  OK closes it; a click on the locked box re-opens it; Escape closes it.
  A4  the gauge legend reads CONTEXT-WINDOW.
  A5  Configure MCPs: ONLY Current-Time is ticked, System-Metrics and
      Files-Search are on, every row shows its cost, a budget line is shown.
  A6  Configure Agents: every agent unticked; ticking ESPHomer raises the
      budget; Continue - "no restart needed" and its tool was chained.
  A7  Configure MCPs: ESPHomer's tool and the run companions are ticked;
      System-Metrics is switched OFF by the user.
  A8  the next request really carries ESPHomer (the gauge's verdict).
  A9  a one-shot question is answered.
  A10 ticking EVERY agent pushes the request PAST the window: the budget line
      warns before Continue, and the gauge says so after it.
  A11 a question asked now is answered WITH the CONTEXT-WINDOW warning.
  A12 back to ESPHomer only; the app log shows the switch and no Traceback.
PHASE B - a BIG model (free cloud model, NO question asked, probes OFF):
  B1  after a restart the box is still ON (keep compact) and UNLOCKED, and the
      agent choices survived the restart (ESPHomer on, the others off).
  B2  unticking it ticks EVERY row again.
  B3  ticking it unticks them again (Current-Time only).
  B4  unticking it leaves the dev database as it was found.
The dev config.json is restored byte for byte.

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

PORT = 8023
os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUN_DIR = os.path.join(REPO, "Temp", "compact_switch_visible")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
REAL_CONFIG = os.path.join(REPO, "Tlamatini", "agent", "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
INSTALLED_CONFIG = r"C:\Tlamatini\config.json"
MODEL_KEYS = ("embeding-model", "chained-model", "access_aimed_prompt_model",
              "unified_agent_model", "mcp_files_search_model", "internet_classifier_model",
              "web_summarizer_model", "ollama_base_url", "unified_agent_base_url")
BIG_MODEL = "nemotron-3-ultra:cloud"     # in Angela's FREE weekly allowance

RESULTS: list = []
PHOTOS: list = []


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


def write_config(update):
    with open(BACKUP, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    config.update(update)
    with open(REAL_CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ page helpers
IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
BOT_TEXTS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message.bot-message'))
  .map(m => { const b = m.querySelector('.automated-message-body') || m; return b.innerText || ''; })"""
LAST_BOT_HAS_CUT_WARNING_JS = """() => { const m = document.querySelectorAll('#chat-log .message.bot-message');
  return m.length ? !!m[m.length - 1].querySelector('.tlm-cut-warning') : false; }"""
BOX_JS = """() => { const b = document.getElementById('compact-mode-enabled');
  const l = document.getElementById('compact-mode-toggle');
  return b ? {checked: b.checked, disabled: b.disabled,
              label: l ? l.innerText.trim() : '', title: l ? (l.getAttribute('title') || '') : ''} : null; }"""
GAUGE_JS = """() => { const r = document.getElementById('context-gauge-row');
  const q = s => { const e = r ? r.querySelector(s) : null; return e ? e.textContent.trim() : ''; };
  return {title: q('.ctxg-title-main'), pct: q('.ctxg-ring-pct'), tokens: q('.ctxg-tokens'),
          zone: q('.ctxg-zone-word'), over: r ? r.getAttribute('data-over') : null,
          cut: r ? r.getAttribute('data-cut') : null}; }"""
CHECKED_JS = """(listId) => Array.from(document.querySelectorAll('#' + listId + ' input[type=checkbox]'))
  .filter(b => b.checked).map(b => { const l = document.querySelector('label[for="' + CSS.escape(b.id) + '"]');
  return l ? (l.getAttribute('data-tlm-name') || l.textContent).trim() : b.id; })"""
ALL_ROWS_JS = """(listId) => document.querySelectorAll('#' + listId + ' input[type=checkbox]').length"""
TICK_JS = """([listId, name, wanted]) => { const lab = Array.from(document.querySelectorAll('#' + listId + ' label'))
  .find(l => (l.getAttribute('data-tlm-name') || l.textContent).trim() === name);
  if (!lab) return null; const b = document.getElementById(lab.htmlFor);
  if (b.checked !== wanted) b.click(); return b.checked; }"""
TICK_FIRST_JS = """([listId, n]) => { let done = 0;
  for (const b of document.querySelectorAll('#' + listId + ' input[type=checkbox]')) {
    if (done >= n) break; if (!b.checked) b.click(); done++; } return done; }"""
UNTICK_ALL_JS = """(listId) => { for (const b of document.querySelectorAll('#' + listId + ' input[type=checkbox]'))
  { if (b.checked) b.click(); } return true; }"""
BUDGET_JS = """(id) => { const e = document.getElementById(id); return e ? e.textContent : ''; }"""
COSTS_JS = """(listId) => document.querySelectorAll('#' + listId + ' .tlm-cost').length"""
CAPACITY_JS = """() => (window.TlmModelCapacity && window.TlmModelCapacity.capacity()) || null"""


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        page.wait_for_timeout(500)
    return False


def set_toggle(page, selector, wanted):
    if page.locator(selector).count() and not page.is_disabled(selector) \
            and page.is_checked(selector) != wanted:
        page.click(selector, force=True)
        page.wait_for_timeout(300)


def is_busy_text(text):
    low = text.strip().lower()
    return any(marker.lower() in low for marker in C.BUSY_MARKERS) or not low


def ask(page, question, label, timeout=600):
    before = len(page.evaluate(BOT_TEXTS_JS))
    started = time.time()
    page.fill(C.SEL["chat_input"], question)
    page.click(C.SEL["chat_submit"])
    busy_deadline = time.time() + 45
    while time.time() < busy_deadline and page.evaluate(IDLE_JS):
        page.wait_for_timeout(250)
    finished = wait_idle(page, timeout)
    page.wait_for_timeout(800)
    texts = page.evaluate(BOT_TEXTS_JS)[before:]
    answer = "\n".join(t for t in texts if not is_busy_text(t)).strip()
    say("   ANSWER (%.1fs, %d chars): %s" % (time.time() - started, len(answer),
                                             answer.replace("\n", " | ")[:420]))
    shot(page, label)
    return finished, answer


def wait_bot_text(page, needle, before, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        texts = page.evaluate(BOT_TEXTS_JS)[before:]
        hit = next((t for t in texts if needle in t), None)
        if hit:
            return hit
        page.wait_for_timeout(400)
    return ""


def close_compact_dialog(page):
    """The Compact-mode dialog opens by itself (once per model) and covers the
    page: close it with Escape, as a user would, before clicking anything."""
    if page.locator("#tlm-compact-overlay").count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return True
    return False


def open_config_dialog(page, item_id, dialog_id, list_id):
    close_compact_dialog(page)
    page.click("#config-menu-button")
    page.wait_for_timeout(400)
    page.click("#" + item_id)
    page.wait_for_selector("#" + dialog_id, state="visible", timeout=15000)
    # The row states come from the server one by one (loadTools/loadAgents)
    # and the prices from /agent/compact_mode/costs/: wait until both settle.
    last, stable = None, 0
    for _ in range(40):
        page.wait_for_timeout(400)
        now = (page.evaluate(CHECKED_JS, list_id), page.evaluate(COSTS_JS, list_id))
        stable = stable + 1 if now == last else 0
        last = now
        if stable >= 3:
            break


def press_dialog_button(page, text):
    page.locator(".ui-dialog:visible .ui-dialog-buttonpane button:has-text('%s')" % text).last.click()
    page.wait_for_timeout(800)


def budget_tokens(text):
    found = re.search(r"≈([\d,]+)", text or "")
    return int(found.group(1).replace(",", "")) if found else -1


def wait_box(page, *, checked, disabled, timeout):
    deadline = time.time() + timeout
    box = None
    while time.time() < deadline:
        box = page.evaluate(BOX_JS)
        if box and box["checked"] == checked and box["disabled"] == disabled:
            return box
        page.wait_for_timeout(1000)
    return box


def login(page):
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.fill(C.SEL["login_user"], C.USERNAME)
    page.fill(C.SEL["login_pass"], C.PASSWORD)
    page.click(C.SEL["login_submit"])
    page.wait_for_load_state("networkidle")
    page.goto(C.BASE_URL + C.CHAT_PATH)
    page.wait_for_selector(C.SEL["chat_input"])
    page.bring_to_front()


def launch(pw):
    try:
        browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
    except Exception as exc:                        # noqa: BLE001
        say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
        browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
    ctx = browser.new_context(no_viewport=True)
    page = ctx.new_page()
    page.set_default_timeout(C.NAV_TIMEOUT_MS)
    page.on("dialog", lambda d: d.accept())
    return browser, page


# ------------------------------------------------------------------ PHASE A
def phase_a(pw, model):
    browser, page = launch(pw)
    try:
        login(page)
        if not check("A1 logged in and the chat page is ready", wait_idle(page, 300)):
            shot(page, "A1_not_ready")
            return
        # Angela saw a template comment printed on the page: none may show.
        body = page.inner_text("body")
        check("A1b no template comment shows on the page", "{#" not in body and "#}" not in body,
              body[body.find("{#"):body.find("{#") + 120] if "{#" in body else "")
        page.click(C.SEL["clean_history"])
        press_dialog_button(page, "Continue")
        wait_idle(page, 240)
        for key in ("t_multi_turn", "t_ask_execs", "t_internet", "t_exec_report", "t_acpx"):
            set_toggle(page, C.SEL[key], False)
        shot(page, "A1_chat_ready")

        # A2 - switched ON by itself and LOCKED -------------------------------
        box = wait_box(page, checked=True, disabled=True, timeout=300)
        check("A2a the Compact mode box switched ON by itself and is locked", box and box["checked"]
              and box["disabled"], box)
        check("A2b the locked box shows a padlock", box and "🔒" in box["label"], box and box["label"])
        appeared = False
        for _ in range(60):
            if page.locator("#tlm-compact-overlay").count():
                appeared = True
                break
            page.wait_for_timeout(1000)
        check("A2c the dialog opened on its own", appeared)
        if appeared:
            text = page.inner_text("#tlm-compact-overlay")
            say("   DIALOG: %s" % text.replace("\n", " | ")[:800])
            for need in (model, "locked ON", "System-Metrics", "Configure Agents", "CONTEXT-WINDOW"):
                check("A2d the dialog explains '%s'" % need, need in text)
            shot(page, "A2_locked_and_dialog")
            page.click("#tlm-compact-overlay .tlmcap-ok")
            page.wait_for_timeout(600)

        # A3 - the locked box explains itself ---------------------------------
        check("A3a OK closed the dialog", page.locator("#tlm-compact-overlay").count() == 0)
        page.click("#compact-mode-toggle", force=True)
        page.wait_for_timeout(800)
        check("A3b a click on the locked box opens the explanation",
              page.locator("#tlm-compact-overlay").count() == 1)
        shot(page, "A3_locked_click_explains")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        check("A3c Escape closes it", page.locator("#tlm-compact-overlay").count() == 0)
        box = page.evaluate(BOX_JS)
        check("A3d the box is still ON and locked", box["checked"] and box["disabled"], box)

        # A4 - the gauge legend -------------------------------------------------
        gauge = page.evaluate(GAUGE_JS)
        check("A4 the gauge legend reads CONTEXT-WINDOW", gauge["title"] == "CONTEXT-WINDOW", gauge)
        shot(page, "A4_gauge_context_window")

        # A5 - Configure MCPs: only Current-Time --------------------------------
        open_config_dialog(page, "enable-mcps", "mcps-dialog-message", "tool-mcps-list")
        ticked = page.evaluate(CHECKED_JS, "tool-mcps-list")
        rows = page.evaluate(ALL_ROWS_JS, "tool-mcps-list")
        check("A5a only Current-Time is ticked (of %d tool rows)" % rows, ticked == ["Current-Time"], ticked)
        check("A5b System-Metrics and Files-Search are on",
              page.is_checked("#mcp-1") and page.is_checked("#mcp-2"))
        costs = page.evaluate(COSTS_JS, "tool-mcps-list")
        check("A5c every row shows its cost (%d labels)" % costs, costs >= rows - 2)
        budget = page.evaluate(BUDGET_JS, "tlm-budget-tools")
        say("   BUDGET: %s" % budget)
        check("A5d a budget line is shown", "Your selection" in budget or "ticked" in budget, budget)
        shot(page, "A5_mcps_current_time_only")
        press_dialog_button(page, "Cancel")

        # A6 - Configure Agents: tick ESPHomer -----------------------------------
        open_config_dialog(page, "enable-agents", "agents-dialog-message", "agents-list")
        on = page.evaluate(CHECKED_JS, "agents-list")
        check("A6a every agent is unticked", on == [], on)
        before_budget = budget_tokens(page.evaluate(BUDGET_JS, "tlm-budget-agents"))
        ticked = page.evaluate(TICK_JS, ["agents-list", "ESPHomer", True])
        after_text, after_budget = "", -1
        for _ in range(30):                          # up to 15 s for the line to move
            page.wait_for_timeout(500)
            after_text = page.evaluate(BUDGET_JS, "tlm-budget-agents")
            after_budget = budget_tokens(after_text)
            if after_budget > before_budget:
                break
        say("   BUDGET before %s -> after %s (%s)" % (before_budget, after_budget, after_text))
        check("A6b ticking ESPHomer raises the budget", ticked and after_budget > before_budget,
              (before_budget, after_budget))
        shot(page, "A6_agents_esphomer_ticked")
        n_before = len(page.evaluate(BOT_TEXTS_JS))
        press_dialog_button(page, "Continue")
        msg = wait_bot_text(page, "Agents activation saved", n_before)
        say("   CHAT: %s" % msg.replace("\n", " | ")[:400])
        check("A6c saving needs no restart", "no restart needed" in msg, msg[:200])
        check("A6d its tool was chained with it", "chat-agent-esphomer" in msg.lower(), msg[:300])
        shot(page, "A6_saved_no_restart")

        # A7 - the chained rows; System-Metrics OFF ------------------------------
        open_config_dialog(page, "enable-mcps", "mcps-dialog-message", "tool-mcps-list")
        ticked = page.evaluate(CHECKED_JS, "tool-mcps-list")
        say("   TICKED TOOLS: %s" % ticked)
        for need in ("Current-Time", "Chat-Agent-ESPHomer", "Chat-Agent-Run-Wait", "Chat-Agent-Run-Status"):
            check("A7a '%s' is ticked" % need, need in ticked)
        if page.is_checked("#mcp-1"):
            page.click("#mcp-1")
        check("A7b the user switched System-Metrics OFF", not page.is_checked("#mcp-1"))
        shot(page, "A7_mcps_chained_metrics_off")
        n_before = len(page.evaluate(BOT_TEXTS_JS))
        press_dialog_button(page, "Continue")
        msg = wait_bot_text(page, "MCPs activation saved", n_before)
        check("A7c MCPs saved at once", "no restart needed" in msg, msg[:200])

        # A8 - the next request carries ESPHomer ---------------------------------
        cap = None
        for _ in range(120):
            cap = page.evaluate(CAPACITY_JS)
            if cap and "chat_agent_esphomer" in (cap.get("tools_kept") or []):
                break
            page.wait_for_timeout(1000)
        check("A8 the next request carries ESPHomer and Current-Time",
              cap and "chat_agent_esphomer" in (cap.get("tools_kept") or [])
              and "get_current_time" in (cap.get("tools_kept") or []), cap and cap.get("tools_kept"))
        shot(page, "A8_gauge_with_esphomer")

        # A9 - a one-shot question ------------------------------------------------
        fin, ans = ask(page, "What time is it right now?", "A9_one_shot_time")
        now = datetime.datetime.now()
        check("A9 the one-shot question is answered", fin and any(
            s in ans for s in (str(now.year), now.strftime("%H:"), now.strftime("%B"))), ans[:200])

        # A10 - past the window -----------------------------------------------------
        open_config_dialog(page, "enable-agents", "agents-dialog-message", "agents-list")
        page.evaluate(TICK_FIRST_JS, ["agents-list", 999])
        budget = ""
        for _ in range(60):                          # up to 30 s, as a person would wait
            page.wait_for_timeout(500)
            budget = page.evaluate(BUDGET_JS, "tlm-budget-agents")
            if "does NOT fit" in budget:
                break
        say("   BUDGET with every agent: %s" % budget)
        check("A10a the budget line warns it does NOT fit", "does NOT fit" in budget, budget)
        shot(page, "A10_budget_does_not_fit")
        press_dialog_button(page, "Continue")
        gauge = None
        for _ in range(240):
            gauge = page.evaluate(GAUGE_JS)
            if gauge["over"] == "true" or gauge["cut"] == "true":
                break
            page.wait_for_timeout(1000)
        say("   GAUGE: %s" % gauge)
        pct = int(re.sub(r"\D", "", gauge["pct"] or "0") or 0)
        check("A10b the gauge shows the request PAST the window (%s)" % gauge["pct"],
              (gauge["over"] == "true" or gauge["cut"] == "true") and pct > 100, gauge)
        check("A10c the zone word says OVER or CUT", gauge["zone"] in ("OVER", "CUT"), gauge["zone"])
        shot(page, "A10_gauge_past_the_window")

        # A11 - an answer from a CUT request carries the warning --------------------
        fin, ans = ask(page, "What time is it right now?", "A11_answer_with_warning", timeout=900)
        check("A11a the question is still answered", fin and len(ans) > 20, ans[:200])
        warned = page.evaluate(LAST_BOT_HAS_CUT_WARNING_JS)
        check("A11b the answer carries the CONTEXT-WINDOW warning", warned and
              "CONTEXT-WINDOW exceeded" in ans, ans[:300])

        # A12 - back to ESPHomer only ------------------------------------------------
        open_config_dialog(page, "enable-agents", "agents-dialog-message", "agents-list")
        page.evaluate(UNTICK_ALL_JS, "agents-list")
        page.evaluate(TICK_JS, ["agents-list", "ESPHomer", True])
        page.wait_for_timeout(500)
        check("A12a only ESPHomer is ticked", page.evaluate(CHECKED_JS, "agents-list") == ["ESPHomer"])
        press_dialog_button(page, "Continue")
        page.wait_for_timeout(2000)
        shot(page, "A12_back_to_esphomer")
    except Exception:                               # noqa: BLE001
        check("phase A itself crashed", False, traceback.format_exc()[-800:])
        shot(page, "A99_crash")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass

    text = server_log()
    lines = text.splitlines()
    check("A12b the app log shows the automatic switch",
          any("[COMPACT] Compact mode ON (automatic" in ln for ln in lines))
    check("A12c the app log shows the STRICT verdict",
          any("STRICT - Compact mode is locked ON" in ln for ln in lines))
    check("A12d the app log shows rows applied without a restart",
          any("[TOGGLES] Configure rows applied at once" in ln for ln in lines))
    check("A12e the app log shows the warned, cut answer",
          any("this answer came from a CUT request" in ln for ln in lines))
    tracebacks = [ln for ln in lines if "Traceback" in ln]
    check("A12f tlamatini.log has no Traceback (%d lines)" % len(lines), not tracebacks, tracebacks[:3])
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_A.log"))


# ------------------------------------------------------------------ PHASE B
def phase_b(pw):
    browser, page = launch(pw)
    try:
        login(page)
        check("B1a logged in on the big model", wait_idle(page, 300))
        box = wait_box(page, checked=True, disabled=False, timeout=300)
        check("B1b the box is still ON (keep compact) and UNLOCKED", box and box["checked"]
              and not box["disabled"], box)
        check("B1c no padlock on a big model", box and "🔒" not in box["label"], box and box["label"])
        shot(page, "B1_big_model_unlocked")
        open_config_dialog(page, "enable-agents", "agents-dialog-message", "agents-list")
        on = page.evaluate(CHECKED_JS, "agents-list")
        check("B1d the agent choices survived the restart (ESPHomer only)", on == ["ESPHomer"], on)
        shot(page, "B1_choices_survived_restart")
        press_dialog_button(page, "Cancel")

        # B2 - untick: EVERYTHING back ----------------------------------------------
        n_before = len(page.evaluate(BOT_TEXTS_JS))
        close_compact_dialog(page)
        page.click("#compact-mode-enabled")
        msg = wait_bot_text(page, "Compact mode is OFF", n_before, timeout=30)
        check("B2a unticking says Compact mode is OFF", bool(msg), msg[:200])
        box = wait_box(page, checked=False, disabled=False, timeout=30)
        check("B2b the box is unticked", box and not box["checked"], box)
        open_config_dialog(page, "enable-agents", "agents-dialog-message", "agents-list")
        rows = page.evaluate(ALL_ROWS_JS, "agents-list")
        on = page.evaluate(CHECKED_JS, "agents-list")
        check("B2c EVERY agent is ticked again (%d of %d)" % (len(on), rows), len(on) == rows and rows > 50)
        shot(page, "B2_all_agents_back")
        press_dialog_button(page, "Cancel")
        open_config_dialog(page, "enable-mcps", "mcps-dialog-message", "tool-mcps-list")
        rows = page.evaluate(ALL_ROWS_JS, "tool-mcps-list")
        on = page.evaluate(CHECKED_JS, "tool-mcps-list")
        check("B2d EVERY tool is ticked again (%d of %d)" % (len(on), rows), len(on) == rows)
        check("B2e System-Metrics is back on", page.is_checked("#mcp-1") and page.is_checked("#mcp-2"))
        shot(page, "B2_all_tools_back")
        press_dialog_button(page, "Cancel")

        # B3 - tick: unticked again ---------------------------------------------------
        n_before = len(page.evaluate(BOT_TEXTS_JS))
        close_compact_dialog(page)
        page.click("#compact-mode-enabled")
        msg = wait_bot_text(page, "Compact mode is ON", n_before, timeout=30)
        check("B3a ticking says Compact mode is ON", bool(msg), msg[:200])
        open_config_dialog(page, "enable-mcps", "mcps-dialog-message", "tool-mcps-list")
        ticked = page.evaluate(CHECKED_JS, "tool-mcps-list")
        check("B3b only Current-Time is ticked again", ticked == ["Current-Time"], ticked)
        shot(page, "B3_compact_on_again")
        press_dialog_button(page, "Cancel")

        # B4 - untick: the dev database as it was found -------------------------------
        n_before = len(page.evaluate(BOT_TEXTS_JS))
        close_compact_dialog(page)
        page.click("#compact-mode-enabled")
        msg = wait_bot_text(page, "Compact mode is OFF", n_before, timeout=30)
        check("B4 unticked again - every row is back", bool(msg), msg[:200])
        shot(page, "B4_final_full")
    except Exception:                               # noqa: BLE001
        check("phase B itself crashed", False, traceback.format_exc()[-800:])
        shot(page, "B99_crash")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    text = server_log()
    tracebacks = [ln for ln in text.splitlines() if "Traceback" in ln]
    check("B5 tlamatini.log has no Traceback", not tracebacks, tracebacks[:3])
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_B.log"))


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
    say("COMPACT MODE CHECKBOX - VISIBLE E2E   (Angela Lopez Mendoza)")
    say("=" * 78)
    if not os.path.isfile(INSTALLED_CONFIG):
        say("!! the installed app's config is missing: %s" % INSTALLED_CONFIG)
        return 4
    with open(INSTALLED_CONFIG, "r", encoding="utf-8-sig") as fh:
        installed = json.load(fh)
    model = str(installed.get("unified_agent_model") or installed.get("chained-model") or "")
    say("PHASE A model (the installed app's): %s on %s" % (model, installed.get("ollama_base_url")))
    shutil.copyfile(REAL_CONFIG, BACKUP)
    sha_before = sha256(REAL_CONFIG)
    write_config({**{k: installed[k] for k in MODEL_KEYS if k in installed},
                  "context_compact_mode": "auto", "context_ceiling_tokens": 0})

    with sync_playwright() as pw:
        if stop_server(PORT):
            time.sleep(2.0)
        if os.path.isfile(os.path.join(REPO, "Tlamatini", "db.sqlite3")):
            reset_rows("visible test: start from every row ON")
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
        if not state.get("ok"):
            say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
            return finish(sha_before, 4)
        phase_a(pw, model)
        stop_server(PORT)
        time.sleep(3.0)

        say("PHASE B model (big, free allowance, probes OFF, no question asked): %s" % BIG_MODEL)
        with open(BACKUP, "r", encoding="utf-8-sig") as fh:
            base = json.load(fh)
        update = {k: BIG_MODEL for k, v in base.items()
                  if k in ("chained-model", "unified_agent_model") or
                  (isinstance(v, str) and re.search(r"[:\-]cloud$", v.strip()))}
        update.update({"ollama_base_url": "http://127.0.0.1:11434",
                       "unified_agent_base_url": "http://127.0.0.1:11434",
                       "context_compact_mode": "auto", "context_ceiling_tokens": 0,
                       "context_gauge_probe_enable": False,
                       "context_gauge_probe_after_answer": False})
        write_config(update)
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
        if not state.get("ok"):
            say("!! ENVIRONMENT NOT READY for phase B: %s" % state.get("reason"))
            return finish(sha_before, 4)
        phase_b(pw)
    return finish(sha_before)


RESET_CODE = """
from agent import compact_mode as cm
from agent.models import CompactState
row = CompactState.objects.filter(pk=1).first()
if row and row.active:
    r = cm.leave_compact(%r, force=True)
    print('RESET Compact mode OFF:', r.get('ok'), r.get('changed'))
else:
    print('RESET not needed: Compact mode is already OFF')
"""


def reset_rows(why):
    """Start - and end - from EVERY row ON with Compact mode OFF, the state a
    fresh install has.  A run that crashed earlier left Compact mode ON (rows
    unticked, the dev External MCPs paused); it must not leak into this one.
    Runs with the server STOPPED (manage.py also truncates tlamatini.log)."""
    try:
        out = subprocess.run([sys.executable, "manage.py", "shell", "-c", RESET_CODE % why],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=240)
        line = next((ln for ln in out.stdout.splitlines() if ln.startswith("RESET")),
                    "RESET gave no answer: " + (out.stderr or "")[-300:])
    except Exception as exc:                        # noqa: BLE001
        line = "RESET failed: %s" % exc
    say("   " + line)
    return line.startswith("RESET") and "failed" not in line and "no answer" not in line


def finish(sha_before, code_if_ok=0):
    stop_server(PORT)
    time.sleep(2.0)
    check("C every row is back ON and the dev External MCPs restored",
          reset_rows("visible test: leave every row ON"))
    restore_config()
    check("C the dev config.json is back byte for byte", sha256(REAL_CONFIG) == sha_before)
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
