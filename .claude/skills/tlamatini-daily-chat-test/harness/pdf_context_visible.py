# Tlamatini Author Banner - do not remove
r"""
PDF AS CONTEXT - VISIBLE TEST (Angela Lopez Mendoza, 2026-10-08)
=================================================================

WHY THIS EXISTS
    The installed Tlamatini refused a PDF with "This PDF context is unavailable"
    and then left the header stuck on "pending context: tutorial_6.pdf", even
    after Clear canvas. Its log showed TWO accounts signed in from one browser:
    the second sign-in replaced the session cookie, so the tab's upload went
    out as the second account while its chat connection was still the first
    one, and the server (rightly) refused another account's file - with a
    message that explained nothing and left no trace in the log.

WHAT IT PROVES (headed Chrome, Shoter photos, the server's own log)
    PHASE A  ONE account: open the PDF, Use as context, Continue -> the context
             loads, the header shows the PDF's context, nothing is refused, and
             the page is usable again afterwards.
    PHASE B  (dev only) A SECOND account signs in from the same browser - a
             throw-away account made for this test and deleted afterwards.
             The same tab tries again -> refused WITH a message that names the
             cause and the fix, the header goes back to what it was (never
             stuck on "pending"), the page stays usable, Clear canvas does not
             bring "pending" back, and the server log records the refusal.
             Then the tab is reloaded exactly as the message says, and the
             same PDF loads.

    ⚠️ manage.py TRUNCATES tlamatini.log every time it runs - ANY command, not
    only runserver. So the throw-away account is made BEFORE the server starts
    and deleted AFTER it stops, never while the test reads the server's log.

USAGE
    python pdf_context_visible.py            # the dev source server on :8026
    python pdf_context_visible.py --frozen   # the installed build on :8000 (PHASE A only)
"""
from __future__ import annotations

import os
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
RUN_DIR = os.path.join(REPO, "Temp", "pdf_context_visible_" + MODE)
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
SOURCE_PDF = os.path.join(REPO, "Temp", "pdf_context_visible", "input")
PDF = os.path.join(RUN_DIR, "tutorial_6.pdf")
SERVER_LOG = r"C:\Tlamatini\tlamatini.log" if FROZEN else os.path.join(REPO, "Tlamatini", "tlamatini.log")
MANAGE_DIR = os.path.join(REPO, "Tlamatini")
SECOND_USER = "pdftest2"
SECOND_PASS = "changeme-pdftest2"
LOAD_TIMEOUT = 900       # embedding a whole PDF into the context can take minutes

RESULTS: list = []
PHOTOS: list = []

DIALOG_JS = """() => { const d = document.getElementById('pdf-context-progress');
  const m = document.getElementById('pdf-context-progress-message');
  return { open: !!(d && d.open), message: m ? m.textContent.trim() : '' }; }"""
HEADER_JS = """() => (document.getElementById('contextData') || {}).textContent || ''"""
# The page's own switches. openEnabled/contextEnabled are top-level `let`s of
# agent_page_state.js, so they are reachable by name from evaluated code.
READY_JS = """() => {
  const i = document.querySelector('#chat-message-input');
  let open = true, ctx = true, busy = false;
  try { open = openEnabled; ctx = contextEnabled; busy = inLongOperation; } catch (e) { /* fail open */ }
  return !!i && !i.readOnly && !document.getElementById('wait-spinner') && open === true && ctx === true && !busy;
}"""
PDF_READY_JS = """() => {
  const f = (document.getElementById('filename') || {}).textContent || '';
  const b = document.getElementById('context-button');
  return f.includes('tutorial_6.pdf') && !!window.TlamatiniPdfCanvas && window.TlamatiniPdfCanvas.active
         && !!b && !b.disabled;
}"""
FAILURE_WORDS = ("unavailable", "different Tlamatini account", "failed", "lost", "incorrect",
                 "not a readable", "Reconnect")


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
    PHOTOS.append((name, path))
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


def login_only(page, username, password):
    """Sign in and stop on the welcome page - that alone replaces the cookie."""
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.fill(C.SEL["login_user"], username)
    page.fill(C.SEL["login_pass"], password)
    page.click(C.SEL["login_submit"])
    page.wait_for_url("**/welcome/**", timeout=60000)


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
    return browser, ctx, page


def close_overlays(page):
    for _ in range(2):
        if page.locator("#tlm-compact-overlay").count():
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)


def wait_ready(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if page.evaluate(READY_JS):
                return True
        except Exception:                           # noqa: BLE001 - a reload in flight
            pass
        page.wait_for_timeout(500)
    return False


def open_pdf(page):
    """Open -> choose the PDF -> wait until the PDF viewer says it is ready."""
    with page.expect_file_chooser(timeout=60000) as chooser:
        page.click("#open-button")
    chooser.value.set_files(PDF)
    page.wait_for_function(PDF_READY_JS, timeout=120000)


def use_as_context(page, timeout=LOAD_TIMEOUT):
    """Use as context -> Continue, then follow the dialog to its end."""
    page.click("#context-button")
    page.wait_for_selector("#pdf-context-progress[open]", timeout=60000)
    page.click("#pdf-context-continue")
    started, last = time.time(), ""
    while time.time() - started < timeout:
        state = page.evaluate(DIALOG_JS)
        if not state["open"]:
            return "loaded", last, time.time() - started
        last = state["message"]
        if any(word in last for word in FAILURE_WORDS):
            return "refused", last, time.time() - started
        page.wait_for_timeout(1000)
    return "timeout", last, time.time() - started


def load_and_check(page, tag):
    """Use the open PDF as context and prove it really loaded."""
    log_before = len(server_log())
    outcome, message, seconds = use_as_context(page)
    header = page.evaluate(HEADER_JS)
    check("%s the PDF context LOADED (%.0fs)" % (tag, seconds), outcome == "loaded", message or outcome)
    check("%s the header shows the PDF's context, not 'pending'" % tag,
          "pdf_canvas" in header and "document.txt" in header and "pending" not in header, header)
    tail = server_log()[log_before:]
    check("%s the server refused nothing" % tag, "[PDF-CONTEXT] refused" not in tail)
    check("%s the page is usable again (Open and Use as context work)" % tag, wait_ready(page, 600))
    return header


def phase_a(page):
    say("-" * 78)
    say("PHASE A - ONE account: the PDF loads as context")
    open_pdf(page)
    check("A1 the PDF opened in the canvas", True)
    shot(page, "A1_pdf_open")
    header = load_and_check(page, "A2")
    shot(page, "A2_pdf_loaded")
    return header


def phase_b(ctx, page):
    say("-" * 78)
    say("PHASE B - a SECOND account signs in from the same browser")
    other = ctx.new_page()
    other.set_default_timeout(C.NAV_TIMEOUT_MS)
    ctx.clear_cookies()                       # what a second sign-in does to every tab
    login_only(other, SECOND_USER, SECOND_PASS)
    check("B1 the second account signed in from the same browser", "welcome" in other.url, other.url)
    shot(other, "B1_second_account_signed_in")

    page.bring_to_front()
    page.click("#clean-canvas-button")
    check("B2 after Clear canvas the page is ready again", wait_ready(page, 600))
    open_pdf(page)
    header_before = page.evaluate(HEADER_JS)
    log_before = len(server_log())
    outcome, message, _seconds = use_as_context(page, timeout=600)
    check("B3 the PDF from the first account's chat is REFUSED", outcome == "refused", outcome)
    check("B4 the message names the cause and the fix",
          "different Tlamatini account" in message and "Reload this page" in message, message)
    shot(page, "B4_refused_with_reason")

    page.click("#pdf-context-progress-action")
    page.wait_for_function("() => !document.getElementById('pdf-context-progress').open", timeout=15000)
    header = page.evaluate(HEADER_JS)
    check("B5 the header went back to what it was, not stuck on 'pending'",
          "pending" not in header and header.strip() == header_before.strip(),
          "before=%r after=%r" % (header_before, header))
    usable = wait_ready(page, 60) and page.evaluate(
        "() => !document.getElementById('context-button').disabled")
    check("B6 the page is still usable (Open and Use as context work)", usable)
    page.click("#clean-canvas-button")
    page.wait_for_timeout(1000)
    header = page.evaluate(HEADER_JS)
    check("B7 Clear canvas does not bring 'pending' back", "pending" not in header, header)
    shot(page, "B7_header_after_clear_canvas")
    tail = server_log()[log_before:]
    refused = [ln for ln in tail.splitlines() if "[PDF-CONTEXT] refused" in ln]
    check("B8 the server log records the refusal and its reason",
          bool(refused) and "different Tlamatini account" in refused[-1], refused[-1:])
    try:
        other.close()
    except Exception:                               # noqa: BLE001
        pass

    say("-" * 78)
    say("PHASE B, the remedy - reload the page as the message says, then load the PDF again")
    page.reload()
    page.wait_for_selector(C.SEL["chat_input"], timeout=120000)
    close_overlays(page)
    check("B9 after the reload the page is ready", wait_ready(page, 600))
    open_pdf(page)
    load_and_check(page, "B10")
    shot(page, "B10_loaded_after_reload")


def make_second_account():
    code, output = manage_shell(
        "from django.contrib.auth import get_user_model as g; U=g(); "
        "u,_=U.objects.get_or_create(username='%s'); u.set_password('%s'); u.is_active=True; "
        "u.save(); print('SECOND_READY', u.pk)" % (SECOND_USER, SECOND_PASS))
    return "SECOND_READY" in output, output.strip()[-300:]


def finish():
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    failed = [name for name, ok, _ in RESULTS if not ok]
    if failed:
        say("VERDICT (%s): FAILED - %d of %d checks failed:" % (MODE, len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
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
    say("PDF AS CONTEXT - VISIBLE TEST (%s) at %s   (Angela Lopez Mendoza)" % (MODE.upper(), C.BASE_URL))
    say("=" * 78)
    if not os.path.isfile(SOURCE_PDF):
        say("!! the test PDF is missing: %s" % SOURCE_PDF)
        return 4
    shutil.copyfile(SOURCE_PDF, PDF)
    say("test PDF: %s (%d bytes)" % (PDF, os.path.getsize(PDF)))
    if FROZEN:
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD, autostart=False)
    else:
        if stop_server(PORT):
            time.sleep(2.0)
        ok, detail = make_second_account()      # server stopped: the log is not being read yet
        if not ok:
            # A FRESH database (build.py erases the dev one): let preflight
            # migrate it first, then stop its server and try once more.
            say("   the second account could not be made yet - letting preflight prepare the database")
            state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
            if state.get("ok") and stop_server(PORT):
                time.sleep(2.0)
            ok, detail = make_second_account()
        check("0a a throw-away second account exists (%s)" % SECOND_USER, ok, detail)
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return 4
    with sync_playwright() as pw:
        browser, ctx, page = launch(pw)
        try:
            login_chat(page, C.USERNAME, C.PASSWORD)
            close_overlays(page)
            check("0b logged in as %s and the chat page is ready" % C.USERNAME, wait_ready(page, 300))
            phase_a(page)
            if not FROZEN:
                phase_b(ctx, page)
        except Exception:                           # noqa: BLE001
            check("the run itself crashed", False, traceback.format_exc()[-900:])
            try:
                shot(page, "99_crash")
            except Exception:                       # noqa: BLE001
                pass
        finally:
            try:
                browser.close()
            except Exception:                       # noqa: BLE001
                pass
    try:
        shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_%s.log" % MODE))
        say("server log saved: %s" % os.path.join(RUN_DIR, "tlamatini_%s.log" % MODE))
    except OSError:
        pass
    if not FROZEN:
        stop_server(PORT)
        time.sleep(2.0)
        manage_shell("from django.contrib.auth import get_user_model as g; "
                     "g().objects.filter(username='%s').delete()" % SECOND_USER)
        say("the throw-away account %s was deleted" % SECOND_USER)
    return finish()


if __name__ == "__main__":
    try:
        code = main()
    except Exception:                               # noqa: BLE001
        say("!! the harness crashed before it could finish:")
        say(traceback.format_exc())
        code = 1
    shutil.rmtree(os.path.join(RUN_DIR, "_shoter_runtime"), ignore_errors=True)
    sys.exit(code)
