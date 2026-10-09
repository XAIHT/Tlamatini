# Tlamatini Author Banner - do not remove
r"""
TWO CHAT PAGES, TWO MODELS - THE COMPACT-MODE VERDICT MUST NOT PING-PONG
=========================================================================
(Angela Lopez Mendoza, 2026-10-08)

WHAT HAPPENED IN THE INSTALLED TLAMATINI
    Two chat pages were open at once (angela on glm-5.3:cloud, dodoati on
    glm-5.2:cloud). Compact mode keeps ONE shared note of "the current model".
    Every time a page re-measured its request it wrote ITS model into that
    note; a changed note told EVERY page to re-send all its Configure rows and
    re-measure; that re-measure wrote the OTHER model back ... forever. Each
    round printed ~900 lines; tlamatini.log reached 61,779 lines in one evening
    and the console dropped 1,000-2,500 lines at a time.

WHAT THIS TEST DOES (headed Chrome, Shoter photos, the server's own log)
    1. Dev server with gauge PROBES OFF (no prompt is ever sent to Ollama).
    2. Page A signs in as 'user' while the chat models are glm-5.3:cloud.
    3. The chat models are switched to glm-5.2:cloud; page B signs in as a
       throw-away account (made before the server starts, deleted after).
    4. Both pages sit IDLE for 60 seconds. Nobody clicks anything.
    5. PASS only if, while idle, the rows were not re-sent and the shared
       capacity note did not flip back and forth.

    Run it BEFORE the fix to see the loop (it must FAIL), and after (PASS).

    ⚠️ manage.py TRUNCATES tlamatini.log on every run of any command, so the
    throw-away account is made before the server starts and deleted after it
    stops. The dev config.json is written atomically and restored at the end.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback

PORT = 8026
os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RUN_DIR = os.path.join(REPO, "Temp", "compact_pingpong_visible")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
MANAGE_DIR = os.path.join(REPO, "Tlamatini")
SERVER_LOG = os.path.join(MANAGE_DIR, "tlamatini.log")
REAL_CONFIG = os.path.join(MANAGE_DIR, "agent", "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
MODEL_A = "glm-5.3:cloud"
MODEL_B = "glm-5.2:cloud"
MODEL_KEYS = ("chained-model", "unified_agent_model")
SECOND_USER = "pdftest2"
SECOND_PASS = "changeme-pdftest2"
SETTLE_SECONDS = 20
IDLE_SECONDS = 60
ROWS_MARK = "Sending establishment of agent: agent-1..."
NOTE_MARK = "--- [COMPACT] "

RESULTS: list = []

READY_JS = """() => {
  const i = document.querySelector('#chat-message-input');
  let open = true, ctx = true, busy = false;
  try { open = openEnabled; ctx = contextEnabled; busy = inLongOperation; } catch (e) { /* fail open */ }
  return !!i && !i.readOnly && !document.getElementById('wait-spinner') && open === true && ctx === true && !busy;
}"""


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


def foreground_title():
    """Title of the window REALLY in front. Windows will not let a background
    program steal the focus while Angela is working in another window, so
    bring_to_front() can silently fail - a photo must never claim otherwise."""
    try:
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 512)
        return buf.value
    except Exception:                               # noqa: BLE001
        return ""


def shot(page, name):
    try:
        page.bring_to_front()
        page.wait_for_timeout(600)
    except Exception:                               # noqa: BLE001
        pass
    front = foreground_title()
    path = take_shot(PHOTOS_DIR, "%s.png" % name, runtime_base=RUN_DIR)
    note = "" if ("Chrome" in front or "Chromium" in front) else (
        "   (the window in front was %r - this photo does NOT show the test page)" % front)
    say("   PHOTO %s -> %s%s" % (name, path, note))
    return path


def server_log():
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# ── config.json: ALWAYS atomic (a half-written config once emptied it) ──────
def _valid(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return isinstance(json.load(fh), dict)
    except (OSError, ValueError):
        return False


def _atomic_write(path, text):
    tmp = path + ".harness-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def backup_config():
    if not _valid(REAL_CONFIG):
        return False
    with open(REAL_CONFIG, "r", encoding="utf-8", newline="") as fh:
        _atomic_write(BACKUP, fh.read())
    return _valid(BACKUP)


def write_config(model):
    with open(BACKUP, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    for key in MODEL_KEYS:
        data[key] = model
    data["context_gauge_probe_enable"] = False        # never send a prompt to Ollama
    data["context_gauge_probe_after_answer"] = False
    _atomic_write(REAL_CONFIG, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def restore_config():
    if not _valid(BACKUP):
        say("!! the backup is not valid JSON - config.json left as it is")
        return False
    with open(BACKUP, "r", encoding="utf-8", newline="") as fh:
        _atomic_write(REAL_CONFIG, fh.read())
    return _valid(REAL_CONFIG)


def manage_shell(code):
    """ONLY while the server is stopped - manage.py truncates tlamatini.log."""
    out = subprocess.run([sys.executable, "manage.py", "shell", "-c", code], cwd=MANAGE_DIR,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    return out.returncode, (out.stdout or "") + (out.stderr or "")


def login_chat(page, username, password):
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.fill(C.SEL["login_user"], username)
    page.fill(C.SEL["login_pass"], password)
    page.click(C.SEL["login_submit"])
    page.wait_for_load_state("networkidle")
    page.goto(C.BASE_URL + C.CHAT_PATH)
    page.wait_for_selector(C.SEL["chat_input"])
    page.bring_to_front()


def wait_ready(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if page.evaluate(READY_JS):
                return True
        except Exception:                           # noqa: BLE001
            pass
        page.wait_for_timeout(500)
    return False


def close_overlays(page):
    for _ in range(2):
        if page.locator("#tlm-compact-overlay").count():
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)


def new_page(pw_browser):
    ctx = pw_browser.new_context(no_viewport=True)   # its OWN cookie jar = another browser
    page = ctx.new_page()
    page.set_default_timeout(C.NAV_TIMEOUT_MS)
    page.on("dialog", lambda d: d.accept())
    return page


def count(text, mark):
    return sum(1 for line in text.splitlines() if mark in line)


def run(pw):
    try:
        browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
    except Exception as exc:                        # noqa: BLE001
        say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
        browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
    try:
        page_a = new_page(browser)
        login_chat(page_a, C.USERNAME, C.PASSWORD)
        close_overlays(page_a)
        check("1 page A (user) is ready on %s" % MODEL_A, wait_ready(page_a, 300))

        write_config(MODEL_B)
        say("   chat models switched to %s for the NEXT connection" % MODEL_B)
        page_b = new_page(browser)
        login_chat(page_b, SECOND_USER, SECOND_PASS)
        close_overlays(page_b)
        check("2 page B (%s) is ready on %s" % (SECOND_USER, MODEL_B), wait_ready(page_b, 300))

        text = server_log()
        both = MODEL_A in text and MODEL_B in text
        check("3 the server really measured BOTH models", both,
              "notes: %s" % [ln.strip()[:110] for ln in text.splitlines() if NOTE_MARK in ln][-4:])

        say("   letting the pages settle for %d s ..." % SETTLE_SECONDS)
        time.sleep(SETTLE_SECONDS)
        start_len = len(server_log())
        say("   IDLE: nobody touches anything for %d s - watching the server log ..." % IDLE_SECONDS)
        for second in range(0, IDLE_SECONDS, 10):
            time.sleep(10)
            tail = server_log()[start_len:]
            say("      +%2ds: rows re-sent %d time(s), capacity notes %d, log grew %d lines"
                % (second + 10, count(tail, ROWS_MARK), count(tail, NOTE_MARK),
                   tail.count("\n")))
        tail = server_log()[start_len:]
        resent, notes = count(tail, ROWS_MARK), count(tail, NOTE_MARK)
        check("4 while idle, no page re-sent its Configure rows", resent == 0,
              "%d re-send(s) in %d s" % (resent, IDLE_SECONDS))
        check("5 while idle, the shared capacity note did not flip back and forth", notes <= 1,
              "%d note(s) in %d s" % (notes, IDLE_SECONDS))
        check("6 while idle, the log stayed quiet", tail.count("\n") < 200,
              "%d new lines in %d s" % (tail.count("\n"), IDLE_SECONDS))
        shot(page_a, "page_A_after_idle")
        shot(page_b, "page_B_after_idle")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass


def main():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        os.remove(RUN_LOG)
    except OSError:
        pass
    say("=" * 78)
    say("TWO PAGES, TWO MODELS - NO PING-PONG   (Angela Lopez Mendoza)")
    say("=" * 78)
    if stop_server(PORT):
        time.sleep(2.0)
    if not backup_config():
        say("!! config.json is not valid JSON - refusing to touch it")
        return 4
    code = 1
    try:
        _rc, out = manage_shell(
            "from django.contrib.auth import get_user_model as g; U=g(); "
            "u,_=U.objects.get_or_create(username='%s'); u.set_password('%s'); u.is_active=True; "
            "u.save(); print('SECOND_READY', u.pk)" % (SECOND_USER, SECOND_PASS))
        if not check("0 a throw-away second account exists", "SECOND_READY" in out, out.strip()[-200:]):
            return 4
        write_config(MODEL_A)
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
        if not state.get("ok"):
            say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
            return 4
        with sync_playwright() as pw:
            try:
                run(pw)
            except Exception:                       # noqa: BLE001
                check("the run itself crashed", False, traceback.format_exc()[-900:])
        try:
            shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_dev.log"))
        except OSError:
            pass
        failed = [name for name, ok, _ in RESULTS if not ok]
        code = 1 if failed else 0
    finally:
        stop_server(PORT)
        time.sleep(2.0)
        say("config.json restored: %s" % restore_config())
        manage_shell("from django.contrib.auth import get_user_model as g; "
                     "g().objects.filter(username='%s').delete()" % SECOND_USER)
        say("the throw-away account %s was deleted" % SECOND_USER)
    say("=" * 78)
    failed = [name for name, ok, _ in RESULTS if not ok]
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
    else:
        say("VERDICT: ALL %d CHECKS PASSED" % len(RESULTS))
    say("=" * 78)
    return code


if __name__ == "__main__":
    try:
        rc = main()
    except Exception:                               # noqa: BLE001
        say("!! the harness crashed before it could finish:")
        say(traceback.format_exc())
        rc = 1
    shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(rc)
