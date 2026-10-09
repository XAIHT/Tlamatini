# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""MODEL BRAIN - VISIBLE end-to-end test (Angela Lopez Mendoza, 2026-10-08).

Headed real Chrome, the REAL chat GUI, user/changeme, Shoter full-screen photos.

  PHASE A  Config > Models > Save opens the AUTO-TUNING dialog: every configured model
           is tuned for real (Ollama /api/show, the vendor's formal profile or research,
           the sampling, the thinking + reasoning policy). Every card must finish; the
           brain models must show the vendor's values and their sources; Escape closes.
  PHASE B  A real Multi-Turn tool task on the brain model (file_creator, then grepper):
           the file must be right on disk, tlamatini.log must show the brain's formal
           settings actually SENT ([MODEL-BRAIN] + [LLM-PARAMS]), the reasoning returned
           inside the tool loop, and the gauge's REAL counts with their estimate error.

  --frozen [URL]  run against the INSTALLED (frozen) Tlamatini instead of the dev source
                  server (default URL http://127.0.0.1:8000); its log is read from
                  C:\\Tlamatini\\tlamatini.log.

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

FROZEN = "--frozen" in sys.argv
PORT = 8026
if FROZEN:
    idx = sys.argv.index("--frozen")
    BASE = sys.argv[idx + 1] if len(sys.argv) > idx + 1 and sys.argv[idx + 1].startswith("http") else "http://127.0.0.1:8000"
    os.environ["TLAMATINI_BASE_URL"] = BASE.rstrip("/")
else:
    os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
MODE = "frozen" if FROZEN else "dev"
RUN_DIR = os.path.join(REPO, "Temp", "model_brain_visible_" + MODE)
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
REAL_CONFIG = r"C:\Tlamatini\config.json" if FROZEN else os.path.join(REPO, "Tlamatini", "agent", "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
SERVER_LOG = r"C:\Tlamatini\tlamatini.log" if FROZEN else os.path.join(REPO, "Tlamatini", "tlamatini.log")
TASK_FILE = os.path.join(REPO, "Temp", "model_brain_visible", "brain_%s.txt" % MODE)

RESULTS: list = []
PHOTOS: list = []

IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
BOT_TEXTS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message.bot-message'))
  .map(m => { const b = m.querySelector('.automated-message-body') || m; return b.innerText || ''; })"""
TUNING_JS = """() => { const o = document.getElementById('tlm-tuning-overlay');
  if (!o) return null;
  const t = o.querySelector('#tlmtune-title'); const p = o.querySelector('.tlmtune-progress-text');
  return { title: t ? t.innerText.trim() : '', progress: p ? p.innerText.trim() : '',
    done: !!o.querySelector('.tlmtune-card.tlmtune-done'),
    cards: Array.from(o.querySelectorAll('.tlmtune-model')).map(c => ({
      model: c.getAttribute('data-model'), cls: c.className,
      chip: (c.querySelector('.tlmtune-chip') || {}).innerText || '',
      stages: Array.from(c.querySelectorAll('.tlmtune-stage')).map(s => s.className + ' :: ' + s.innerText.replace(/\\n/g, ' | ')),
      result: (c.querySelector('.tlmtune-result') || {}).innerText || '',
      sources: Array.from(c.querySelectorAll('.tlmtune-sources a')).map(a => a.href) })) }; }"""
GAUGE_JS = """() => { const r = document.getElementById('context-gauge-row');
  return r ? r.innerText.replace(/\\s+/g, ' ').trim() : ''; }"""


def say(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:600]))
    say(("[PASS] " if ok else "[FAIL] ") + name + (("   -> " + str(detail)[:500]) if detail else ""))
    return bool(ok)


def shot(page, name):
    try:
        page.bring_to_front()
        page.wait_for_timeout(600)
    except Exception:                               # noqa: BLE001
        pass
    path = take_shot(PHOTOS_DIR, "%s.png" % name, runtime_base=RUN_DIR)
    PHOTOS.append((name, path))
    say("   PHOTO %s -> %s" % (name, path))
    return path


def server_log():
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


_RESTORED = {"done": False}


def restore_config():
    if _RESTORED["done"] or not config_is_valid(BACKUP):
        return
    tmp = REAL_CONFIG + ".harness-tmp"         # atomic, like write_config
    shutil.copyfile(BACKUP, tmp)
    os.replace(tmp, REAL_CONFIG)
    _RESTORED["done"] = True
    say("config.json restored from %s" % BACKUP)


def write_config():
    """Keep every setting; only the gauge's at-rest probes off (each re-sends the whole request)."""
    with open(BACKUP, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    config.update({"context_gauge_probe_enable": False, "context_gauge_probe_after_answer": False})
    # ATOMIC (2026-10-08): opening config.json with "w" EMPTIES it first, and a
    # run killed in that instant (its window closed) left Angela a 0-byte
    # config.json. Write a sibling file, then swap it in with one os.replace.
    tmp = REAL_CONFIG + ".harness-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, REAL_CONFIG)
    return config


def config_is_valid(path):
    """True when ``path`` is a non-empty JSON object (a config worth backing up)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return isinstance(data, dict) and len(data) > 10
    except (OSError, ValueError):
        return False


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        page.wait_for_timeout(500)
    return False


def set_toggle(page, selector, wanted):
    if page.locator(selector).count() and not page.is_disabled(selector) and page.is_checked(selector) != wanted:
        page.click(selector, force=True)
        page.wait_for_timeout(400)


def close_compact_dialog(page):
    if page.locator("#tlm-compact-overlay").count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)


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
def phase_a(page, config):
    say("PHASE A - Config > Models > Save -> the Auto-tuning dialog")
    close_compact_dialog(page)
    page.click("#config-menu-button")
    page.wait_for_timeout(400)
    page.click("#config-models")
    page.wait_for_selector("#config-models-dialog-message", state="visible", timeout=20000)
    page.wait_for_timeout(1500)
    shot(page, "A1_models_dialog")
    page.locator(".ui-dialog:visible .ui-dialog-buttonpane button:has-text('Save')").last.click()
    try:
        page.wait_for_selector("#tlm-tuning-overlay", state="visible", timeout=20000)
        appeared = True
    except Exception:                               # noqa: BLE001
        appeared = False
    check("A2 Save opened the Auto-tuning dialog", appeared)
    if not appeared:
        shot(page, "A2_no_dialog")
        return
    page.wait_for_timeout(1800)
    shot(page, "A2_tuning_in_progress")
    started = time.time()
    state, last = None, ""
    while time.time() - started < 420:
        state = page.evaluate(TUNING_JS)
        if state and state["progress"] != last:
            last = state["progress"]
            say("   ... %s" % last.replace("\n", " "))
        if state and state["done"]:
            break
        page.wait_for_timeout(1000)
    check("A3 the dialog finished tuning (%.0fs)" % (time.time() - started), bool(state and state["done"]),
          state and state["title"])
    cards = (state or {}).get("cards") or []
    say("   %d model card(s):" % len(cards))
    for card in cards:
        say("     %-32s %-24s %s | %s" % (card["model"], card["chip"], card["cls"].replace("tlmtune-model", "").strip(),
                                         card["result"].replace("\n", " ")[:160]))
    check("A4 every configured model has a card", len(cards) >= 2, len(cards))
    unfinished = [c["model"] for c in cards if "is-running" in c["cls"]
                  or not any(k in c["cls"] for k in ("is-done", "is-warn", "is-skip"))]
    check("A5 no card is left unfinished", not unfinished, unfinished)
    brain_model = str(config.get("unified_agent_model") or "")
    brain = next((c for c in cards if c["model"] == brain_model), None)
    check("A6 the brain model (%s) is marked APPLIED TO THE BRAIN" % brain_model,
          bool(brain) and "APPLIED" in brain["chip"], brain and brain["chip"])
    if brain:
        check("A7 its card shows the vendor-published values and the thinking policy",
              "temperature" in brain["result"] and "reasoning in tool loops" in brain["result"], brain["result"])
        check("A8 its card links the formal sources", any("huggingface.co" in s or "z.ai" in s or "github.com" in s
                                                          for s in brain["sources"]), brain["sources"])
    page.evaluate("() => { const b = document.querySelector('#tlm-tuning-overlay .tlmpop-body'); if (b) b.scrollTop = 0; }")
    shot(page, "A9_tuning_done")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    check("A10 Escape closed the dialog (dialog_policy)", page.locator("#tlm-tuning-overlay").count() == 0)
    page.wait_for_timeout(800)
    if page.locator(".ui-dialog:visible").count():
        say("   a follow-up dialog is open (Reconnect notice) - closing it")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)


# ------------------------------------------------------------------ PHASE B
def phase_b(page, config):
    say("PHASE B - a real Multi-Turn tool task on the brain model")
    os.makedirs(os.path.dirname(TASK_FILE), exist_ok=True)
    try:
        os.remove(TASK_FILE)
    except OSError:
        pass
    # A CLEAN conversation (Angela's rule: clear chat history per test). Without
    # it the model reads the previous runs' answers ("file created...") and
    # spends extra steps reconciling them - measured 2026-10-08: 9 steps instead of 3.
    page.click(C.SEL["clean_history"])
    page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last.click()
    time.sleep(3.0)
    idle = wait_idle(page, 240)
    stale = [t[:80] for t in page.evaluate(BOT_TEXTS_JS) if "alpha" in t or "brain_" in t]
    check("B0 Clean History: no earlier run's answer is left in the chat", idle and not stale, stale)
    log_before = len(server_log())
    set_toggle(page, "#multi-turn-enabled", True)
    set_toggle(page, "#exec-report-enabled", True)
    set_toggle(page, "#acpx-enabled", False)
    path = TASK_FILE.replace("\\", "/")
    question = ("Tlamatini, use chat_agent_file_creator to create the file %s containing exactly three lines: "
                "alpha, bravo and charlie, each on its own line. Then use chat_agent_grepper with "
                "output_mode='lines' to read that file back, and tell me how many lines it has." % path)
    before = len(page.evaluate(BOT_TEXTS_JS))
    started = time.time()
    say(">> ASK B1: " + question)
    page.fill(C.SEL["chat_input"], question)
    page.click(C.SEL["chat_submit"])
    page.wait_for_timeout(1500)
    finished, last_report = False, 0.0
    while time.time() - started < 900:
        if page.evaluate(IDLE_JS):
            finished = True
            break
        if time.time() - last_report > 15:
            last_report = time.time()
            tail = server_log()[log_before:]
            brain_lines = [ln for ln in tail.splitlines() if "[MODEL-BRAIN]" in ln or "[CONTEXT-REAL]" in ln]
            say("   ... working %.0fs | gauge: %s | %s" % (time.time() - started, page.evaluate(GAUGE_JS)[:90],
                                                         (brain_lines[-1][-150:] if brain_lines else "-")))
        page.wait_for_timeout(1000)
    page.wait_for_timeout(1500)
    texts = page.evaluate(BOT_TEXTS_JS)[before:]
    answer = texts[-1] if texts else ""
    say("   ANSWER (%.0fs): %s" % (time.time() - started, answer.replace("\n", " | ")[:500]))
    shot(page, "B1_answer")
    check("B1 the answer arrived", finished)
    content = ""
    if os.path.isfile(TASK_FILE):
        with open(TASK_FILE, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    check("B2 the file on disk holds exactly alpha, bravo, charlie", lines == ["alpha", "bravo", "charlie"], lines)
    check("B3 the answer reports 3 lines", re.search(r"\b(3|three)\b", answer, re.I) is not None, answer[:200])

    whole = server_log()                     # the chat model is built at CONNECT, before this phase
    tail = whole[log_before:]
    model = str(config.get("unified_agent_model") or "")
    brain_lines = [ln for ln in whole.splitlines()
                   if "[MODEL-BRAIN] model=%s" % model in ln and "formal profile" in ln]
    say("   " + (brain_lines[-1][-260:] if brain_lines else "no [MODEL-BRAIN] line"))
    check("B4 tlamatini.log: the brain planned %s from its formal profile" % model,
          bool(brain_lines), brain_lines[-1:])
    params = [ln for ln in whole.splitlines() if "[LLM-PARAMS] model=%s" % model in ln]
    say("   " + (params[-1][-260:] if params else "no [LLM-PARAMS] line"))
    wanted = re.search(r"temperature=([0-9.]+)", brain_lines[-1]).group(1) if brain_lines else "?"
    check("B5 the temperature really SENT is the brain's (%s), not the old fixed 0.0" % wanted,
          bool(params) and "temperature=%s " % wanted in params[-1] + " ", params[-1:])
    returned = [ln for ln in tail.splitlines() if "returned the reasoning of" in ln]
    say("   reasoning returned in %d later step(s)%s" % (len(returned), (": " + returned[-1][-120:]) if returned else ""))
    check("B6 the model's reasoning was returned inside the tool loop", bool(returned), len(returned))
    reals = [ln for ln in tail.splitlines() if "[CONTEXT-REAL]" in ln and "prompt_eval_count=" in ln]
    errors = [float(m.group(1)) for m in (re.search(r"estimate \d+ \(([+-][0-9.]+)%\)", ln) for ln in reals) if m]
    for ln in reals:
        say("   " + ln[ln.find("[CONTEXT-REAL]"):][:230])
    check("B7 the gauge got Ollama's REAL count for every step (%d)" % len(reals), len(reals) >= 2, len(reals))
    if errors:
        say("   gauge estimate error per step: %s" % ", ".join("%+.1f%%" % e for e in errors))
    check("B7b the gauge's estimate stays within 10%% of Ollama's REAL count, reasoning included (%s)"
          % ", ".join("%+.1f%%" % e for e in errors), bool(errors) and all(abs(e) <= 10.0 for e in errors))
    tracebacks = [ln for ln in tail.splitlines() if "Traceback" in ln]
    check("B8 tlamatini.log: no Traceback during the task", not tracebacks, tracebacks[:3])


# ------------------------------------------------------------------ phase C
def _server_console_index():
    """Position of the SERVER's own console among the windows titled exactly
    "Tlamatini" (manage.py brands its console with that title), found by
    PROCESS, never by guessing: the window's pid must be the listening server,
    one of its ancestors, or a child of one (conhost). (-1, why) if not found.
    """
    try:
        import psutil
        port = int(C.BASE_URL.rsplit(":", 1)[1].split("/")[0])
        server_pid = next((c.pid for c in psutil.net_connections(kind="tcp")
                           if c.laddr and c.laddr.port == port
                           and c.status == psutil.CONN_LISTEN), None)
        if not server_pid:
            return -1, "nothing listens on :%d" % port
        family = {server_pid} | {p.pid for p in psutil.Process(server_pid).parents()}
    except Exception as exc:                        # noqa: BLE001
        return -1, "could not read the server's processes: %s" % exc
    exact = _tlamatini_windows()
    # 1) classic conhost: the window's pid IS the server or one of its ancestors.
    for idx, (hwnd, pid) in enumerate(exact):
        try:
            parent = psutil.Process(pid).ppid()
        except Exception:                           # noqa: BLE001
            parent = None
        if pid in family or parent in family:
            return idx, "conhost window pid %d belongs to the server (pid %d)" % (pid, server_pid)
    # 2) Windows Terminal (Angela's DEFAULT console): every tab is owned by
    #    WindowsTerminal.exe, so a pid proves nothing. The server's window is the
    #    one titled "Tlamatini" that did NOT exist before the server started.
    fresh = [idx for idx, (hwnd, pid) in enumerate(exact) if hwnd not in PRE_HWNDS]
    if len(fresh) == 1:
        return fresh[0], ("Windows Terminal window 0x%X appeared when the server started "
                          "(server pid %d)" % (exact[fresh[0]][0], server_pid))
    return -1, ("could not single out the server's console (server pid %d, windows titled "
                "'Tlamatini': %s, new since start: %d)" % (server_pid, exact, len(fresh)))


PRE_HWNDS: set = set()


def _tlamatini_windows():
    """(hwnd, pid) of every window titled EXACTLY "Tlamatini", via Windower."""
    import windower_focus as W
    found = []
    for line in W.list_windows("Tlamatini", RUN_DIR).splitlines():
        m = re.match(r"\[\d+\] '(.*)' \|.*hwnd=0x([0-9A-Fa-f]+) pid=(\d+)", line.strip())
        if m and m.group(1) == "Tlamatini":
            found.append((int(m.group(2), 16), int(m.group(3))))
    return found


def phase_c():
    """CONSOLE COLOURS: the server WINDOW is painted by level; tlamatini.log stays plain."""
    import urllib.request
    import windower_focus as W
    say("-" * 78)
    say("PHASE C - the console is painted by level, the log file is not")
    # A harmless 404 makes Django log a WARNING line, so yellow is on screen too.
    try:
        urllib.request.urlopen(C.BASE_URL + "/agent/no-such-page-for-the-colour-test/", timeout=20)
    except Exception:                               # noqa: BLE001 - a 404 raises; that is the point
        pass
    time.sleep(2.0)
    log = server_log()
    lines = log.splitlines()
    host_lines = [ln for ln in lines if "--- [CONSOLE] host:" in ln]
    check("C0 Tlamatini measured and announced which console draws her window",
          bool(host_lines), host_lines[-1:])
    colour_lines = [ln for ln in lines if "[CONSOLE-COLORS]" in ln]
    check("C1 the server console renders colours ([CONSOLE-COLORS] ON)",
          any("[CONSOLE-COLORS] ON" in ln for ln in colour_lines), colour_lines[-2:])
    check("C2 tlamatini.log is plain text: not one colour code in it",
          "\x1b" not in log, "%d ESC character(s)" % log.count("\x1b"))
    warning = [ln for ln in lines if "WARNING" in ln and "no-such-page-for-the-colour-test" in ln]
    check("C3 the 404 reached the log as a WARNING line (painted yellow on screen)",
          bool(warning), warning[-1:])
    access = [ln for ln in lines if "django.channels.server" in ln and "HTTP " in ln]
    check("C4 Django's coloured access lines reach the log WITHOUT their codes",
          bool(access) and all("\x1b" not in ln for ln in access), access[-1:])
    idx, why = _server_console_index()
    focused = idx >= 0 and W.focus("Tlamatini", RUN_DIR, match_mode="exact", match_index=idx)
    check("C5 Windower brought the SERVER's own console to the front", focused, why)
    if not focused:
        say("   no photo of the console: it could not be identified, so none is presented as evidence")
        return
    pinned = W._run(RUN_DIR, {"action": "topmost", "window_title": "Tlamatini",
                              "match_mode": "exact", "match_index": idx})
    try:
        time.sleep(1.5)
        path = take_shot(PHOTOS_DIR, "C_console_colors.png", runtime_base=RUN_DIR)
        PHOTOS.append(("C_console_colors", path))
        say("   PHOTO C_console_colors -> %s" % path)
    finally:
        if pinned is not None:
            W._run(RUN_DIR, {"action": "untopmost", "window_title": "Tlamatini",
                             "match_mode": "exact", "match_index": idx})


# ------------------------------------------------------------------ main
def finish(code_if_ok=0):
    if not FROZEN:
        stop_server(PORT)
        time.sleep(2.0)
    restore_config()
    failed = [name for name, ok, _ in RESULTS if not ok]
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    if failed:
        say("VERDICT (%s): FAILED - %d of %d checks failed:" % (MODE, len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    if code_if_ok:
        return code_if_ok
    say("VERDICT (%s): ALL %d CHECKS PASSED" % (MODE, len(RESULTS)))
    say("=" * 78)
    return 0


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
    say("MODEL BRAIN - VISIBLE E2E (%s) at %s   (Angela Lopez Mendoza)" % (MODE.upper(), C.BASE_URL))
    say("=" * 78)
    # NEVER back up a broken config: that would make the "restore" at the end
    # put the broken file back. Stop with a named reason instead.
    if not config_is_valid(REAL_CONFIG):
        say("!! %s is empty or not valid JSON - refusing to back it up or touch it." % REAL_CONFIG)
        if os.path.isfile(BACKUP) and config_is_valid(BACKUP):
            say("   a valid backup exists: %s - restore it first." % BACKUP)
        return 4
    backup_tmp = BACKUP + ".tmp"
    shutil.copyfile(REAL_CONFIG, backup_tmp)
    os.replace(backup_tmp, BACKUP)
    config = write_config()
    if FROZEN:
        say("FROZEN mode: the installed Tlamatini must already be running at %s" % C.BASE_URL)
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD, autostart=False)
    else:
        if stop_server(PORT):
            time.sleep(2.0)
        out = subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=600)
        say("   migrate: exit %s" % out.returncode)
        # Remember the "Tlamatini" windows that exist BEFORE the server starts, so
        # Phase C can single out the server's own console under Windows Terminal.
        # AFTER migrate: manage.py titles THIS harness window "Tlamatini" too.
        PRE_HWNDS.update(hwnd for hwnd, _pid in _tlamatini_windows())
        say("   windows titled 'Tlamatini' before the server starts: %d" % len(PRE_HWNDS))
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return finish(4)
    with sync_playwright() as pw:
        browser, page = launch(pw)
        try:
            login(page)
            check("0 logged in as %s and the chat page is ready" % C.USERNAME, wait_idle(page, 300))
            close_compact_dialog(page)
            shot(page, "0_ready")
            phase_a(page, config)
            phase_b(page, config)
            phase_c()
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-900:])
            shot(page, "99_crash")
        finally:
            try:
                browser.close()
            except Exception:                       # noqa: BLE001
                pass
    try:
        shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_%s.log" % MODE))
    except OSError:
        pass
    return finish()


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
