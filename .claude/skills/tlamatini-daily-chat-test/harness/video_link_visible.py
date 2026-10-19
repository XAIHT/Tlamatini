# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner - do not remove
r"""
VIDEO LINK TRANSCRIPTION - VISIBLE TEST (Angela Lopez Mendoza, 2026-10-11)
=========================================================================

WHY THIS EXISTS
    On the installed build a user asked: "starting from the transcription of
    this video: 'https://www.youtube.com/watch?v=NdlzdPs0QBQ' ...". Video-Analyzer
    failed THREE times ("Parameter 'v' was not found", robotics mode on an empty
    path, "No video resolved from 'https://youtu.be/...'"), and the chat then
    spent seven tool calls installing yt-dlp by hand before Whisperer could run.

WHAT IT PROVES (headed Chrome, Shoter photos, the server's own log)
    The SAME kind of request, in plain words, through the real chat GUI with
    Multi-Turn ON:
      * the model calls chat_agent_video_analyzer (with the link),
      * no "Parameter 'v' was not found", no hand-installed yt-dlp / pip,
      * Video-Analyzer downloads the link itself and ends TLM_ANALYSIS::TRANSCRIBED
        with source_title "Me at the zoo",
      * the answer the user reads quotes what is said in the video.
    ONE question only: a full Multi-Turn request is ~100K tokens of cloud model.

    manage.py TRUNCATES tlamatini.log whenever it runs, so nothing else may run
    manage.py while this test reads the server log.

USAGE
    python video_link_visible.py            # the dev source server on :8026
"""
from __future__ import annotations

import glob
import os
import shutil
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
RUN_DIR = os.path.join(REPO, "Temp", "video_link_visible")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
POOL_GLOBS = (os.path.join(REPO, "Tlamatini", "agent", "agents", "pools", "_chat_runs_", "video_analyzer_*"),
              os.path.join(REPO, "Tlamatini", "agents", "pools", "_chat_runs_", "video_analyzer_*"))
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
QUESTION = ("Tlamatini, I need the full transcription of this video, word by word: '%s'. "
            "Tell me exactly what the person says in it." % URL)
ANSWER_TIMEOUT = 900
# The generic "Are you sure?" dialog that Clean history opens.
CONFIRM_CONTINUE = '.ui-dialog-buttonpane button:has-text("Continue")'

RESULTS: list = []
PHOTOS: list = []

IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
CARDS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message')).map(e => ({
  id: e.dataset.messageId || '',
  bot: e.classList.contains('bot-message'),
  text: ((e.querySelector('.automated-message') || e.querySelector('.message-content') || e).innerText || '').trim()
}))"""
TOGGLES = (("#multi-turn-enabled", True), ("#acpx-enabled", False), ("#ask-execs-enabled", False),
           ("#exec-report-enabled", True), ("#internetEnabled", False))


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


def login_chat(page):
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.fill(C.SEL["login_user"], C.USERNAME)
    page.fill(C.SEL["login_pass"], C.PASSWORD)
    page.click(C.SEL["login_submit"])
    page.wait_for_load_state("networkidle")
    page.goto(C.BASE_URL + C.CHAT_PATH)
    page.wait_for_selector(C.SEL["chat_input"])
    page.bring_to_front()


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if page.evaluate(IDLE_JS):
                return True
        except Exception:                           # noqa: BLE001
            pass
        time.sleep(0.5)
    return False


def close_overlays(page):
    for _ in range(2):
        if page.locator("#tlm-compact-overlay").count():
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)


def set_toggles(page):
    for selector, wanted in TOGGLES:
        box = page.locator(selector)
        if not box.count():
            continue
        for _ in range(3):
            if box.is_checked() == wanted or box.is_disabled():
                break
            box.click()
            page.wait_for_timeout(300)
    state = {sel: page.locator(sel).is_checked() for sel, _ in TOGGLES if page.locator(sel).count()}
    return state


def cards(page):
    return page.evaluate(CARDS_JS) or []


def ask(page, text, timeout):
    for attempt in range(1, 4):
        known = {c["id"] for c in cards(page) if c["id"]}
        n_before = len(cards(page))
        page.fill(C.SEL["chat_input"], text)
        page.click(C.SEL["chat_submit"])
        say("   sent (attempt %d): %s" % (attempt, text[:120]))
        deadline, last_note, not_ready = time.time() + timeout, time.time(), False
        while time.time() < deadline:
            now = cards(page)
            fresh = [c for c in now if c["id"] and c["id"] not in known]
            if any(m in c["text"] for c in now[n_before:] if c["bot"] for m in C.NOT_READY_MARKERS) \
                    and not any(not c["bot"] for c in fresh):
                not_ready = True
                break
            answers = [c for c in fresh if c["bot"]
                       and not any(m in c["text"] for m in C.BUSY_MARKERS)]
            if answers and any(not c["bot"] for c in fresh) and page.evaluate(IDLE_JS):
                time.sleep(1.5)
                answers = [c for c in cards(page) if c["id"] and c["id"] not in known and c["bot"]
                           and not any(m in c["text"] for m in C.BUSY_MARKERS)]
                return answers[-1]
            if time.time() - last_note > 15:
                tail = server_log()[-4000:]
                if "TLM_ANALYSIS::" in tail:
                    stage = "transcript ready - model writing the answer"
                elif "Invoking WRAPPED CHAT AGENT tool: chat_agent_video_analyzer" in tail:
                    stage = "downloading/transcribing"
                else:
                    stage = "model thinking"
                say("   ... waiting for the answer (%s, %ds)" % (stage, int(timeout - (deadline - time.time()))))
                last_note = time.time()
            time.sleep(1.0)
        if not_ready:
            say("   the agent was not ready yet - waiting 10 s and sending again")
            time.sleep(10)
            wait_idle(page, 120)
            continue
        return None
    return None


def newest_video_analyzer_logs(since):
    logs = []
    for pattern in POOL_GLOBS:
        for folder in glob.glob(pattern):
            for log in glob.glob(os.path.join(folder, "*.log")):
                if os.path.getmtime(log) >= since:
                    logs.append(log)
    return sorted(logs, key=os.path.getmtime)


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def finish():
    say("=" * 78)
    say("photos: %s" % PHOTOS_DIR)
    failed = [name for name, ok, _ in RESULTS if not ok]
    if failed:
        say("VERDICT: FAILED - %d of %d checks failed:" % (len(failed), len(RESULTS)))
        for name in failed:
            say("   - " + name)
        say("=" * 78)
        return 1
    say("VERDICT: ALL %d CHECKS PASSED" % len(RESULTS))
    say("=" * 78)
    return 0


def main():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(PHOTOS_DIR, "*.png")):
        try:
            os.remove(old)
        except OSError:
            pass
    try:
        os.remove(RUN_LOG)
    except OSError:
        pass
    say("=" * 78)
    say("VIDEO LINK TRANSCRIPTION - VISIBLE TEST at %s   (Angela Lopez Mendoza)" % C.BASE_URL)
    say("=" * 78)
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return 4
    started = time.time()
    with sync_playwright() as pw:
        browser, ctx, page = launch(pw)
        try:
            login_chat(page)
            close_overlays(page)
            check("0a logged in as %s and the chat page is ready" % C.USERNAME, wait_idle(page, 300))
            # Clean history asks "Are you sure?" - the run must press Continue,
            # wait for the page to be ready again, and only THEN say it is clean.
            try:
                page.click(C.SEL["clean_history"])
                page.wait_for_selector(CONFIRM_CONTINUE, timeout=10_000)
                page.click(CONFIRM_CONTINUE)
                page.wait_for_selector(CONFIRM_CONTINUE, state="hidden", timeout=10_000)
                time.sleep(2)
                wait_idle(page, 300)
                saved = [c for c in cards(page) if c["id"]]
                if saved:
                    say("   !! history still shows %d saved card(s) - only NEW cards are read" % len(saved))
                else:
                    say("   chat history cleared and confirmed (no saved card left on the page)")
            except Exception as exc:                # noqa: BLE001
                say("   (Clean history not confirmed: %s - continuing; only NEW saved cards are read)" % exc)
            toggles = set_toggles(page)
            check("0b Multi-Turn ON, ACPX / Ask-Execs / Internet OFF, Exec report ON",
                  toggles.get("#multi-turn-enabled") is True and toggles.get("#acpx-enabled") is False
                  and toggles.get("#ask-execs-enabled") is False, toggles)
            open_dialogs = page.locator(".ui-dialog:visible").count()
            check("0c no dialog is left open over the chat", open_dialogs == 0, open_dialogs)
            shot(page, "01_ready_multi_turn_on")
            log_before = len(server_log())
            answer = ask(page, QUESTION, ANSWER_TIMEOUT)
            open_dialogs = page.locator(".ui-dialog:visible").count()
            check("0d no dialog covers the answer in the photo", open_dialogs == 0, open_dialogs)
            shot(page, "02_answer")
            text = (answer or {}).get("text", "")
            check("1 an answer arrived within %d s" % ANSWER_TIMEOUT, bool(answer), text[:300])
            tail = server_log()[log_before:]
            invocations = [ln for ln in tail.splitlines() if "Invoking WRAPPED CHAT AGENT tool:" in ln]
            say("   tool calls: %s" % [ln.split("tool:", 1)[1].split(" with args")[0].strip() for ln in invocations])
            check("2 the model called chat_agent_video_analyzer",
                  any("chat_agent_video_analyzer" in ln for ln in invocations), invocations[:3])
            check("3 no 'Parameter 'v' was not found' (a link's ?v= is never a setting)",
                  "Parameter 'v' was not found" not in tail)
            hand_installs = [ln for ln in invocations if ("chat_agent_executer" in ln or "chat_agent_pythonxer" in ln)
                             and any(word in ln.lower() for word in ("yt-dlp", "yt_dlp", "pip install"))]
            check("4 no hand-installed yt-dlp / pip through Executer or Pythonxer", not hand_installs, hand_installs[:2])
            run_logs = newest_video_analyzer_logs(started)
            run_text = "\n".join(read(path) for path in run_logs)
            say("   Video-Analyzer run logs: %s" % run_logs)
            check("5 Video-Analyzer downloaded the link and transcribed it (TLM_ANALYSIS::TRANSCRIBED)",
                  "TLM_ANALYSIS::TRANSCRIBED" in run_text and "Web video ready" in run_text,
                  [ln for ln in run_text.splitlines() if "VIDEO-FETCH" in ln or "Web video ready" in ln][:4])
            check("6 the result names the source page (source_title: Me at the zoo)",
                  "source_title: Me at the zoo" in run_text)
            check("7 the answer quotes what is said in the video (elephants / trunks)",
                  "elephant" in text.lower() and ("trunk" in text.lower() or "punk" in text.lower()), text[:400])
            check("8 the Exec report lists the Video-Analyzer run", "Video-Analyzer" in text, text[-300:])
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
        shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_dev.log"))
        say("server log saved: %s" % os.path.join(RUN_DIR, "tlamatini_dev.log"))
    except OSError:
        pass
    stop_server(PORT)
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
