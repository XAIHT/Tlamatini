"""The SELF-MODIFY box - VISIBLE end-to-end test (Angela Lopez Mendoza, 2026-10-03).

Headed real Chrome on Angela's desktop, the real chat GUI, the dev source
server on port 8023 (dev mode is ALWAYS like --self-modify, so the box must be
there), Shoter full-screen photos.  No question is sent to any model.

PHASE A - the installed app's SMALL local model (qwen2.5:latest):
  A1  logged in, the page is ready, no template comment shows.
  A2  the Self-modify box IS on the page (dev mode = --self-modify).
  A3  it is unticked, greyed and shows a padlock: the model cannot hold the
      ~28K-token self-knowledge.
  A4  a click on it explains why (themed popup), Escape closes it.
  A5  a FORGED tick is refused by the server, and the box stays locked.
  A6  tlamatini.log says so ([SELF-MODIFY] ... locked OFF).
PHASE B - a big model in Angela's FREE allowance, gauge probes OFF:
  B1  the box is unlocked and ticked (ON by default).
  B2  unticking it says "Self-modify is OFF" and the request at rest really
      shrinks by the whole self-knowledge (>100,000 bytes).
  B3  ticking it again says "Self-modify is ON" and the bytes come back.
  B4  tlamatini.log records both switches, and no Traceback.
The dev database rows, the Self-modify choice and config.json are restored.

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

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
RUN_DIR = os.path.join(REPO, "Temp", "self_modify_visible")
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

FRAMES_INIT = """
window.__tlmFrames = [];
document.addEventListener('tlm:context-gauge', function (e) {
  try { window.__tlmFrames.push(JSON.parse(JSON.stringify(e.detail))); } catch (x) {}
});
"""
IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
BOT_TEXTS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message.bot-message'))
  .map(m => { const b = m.querySelector('.automated-message-body') || m; return b.innerText || ''; })"""
BOX_JS = """() => { const b = document.getElementById('self-modify-enabled');
  const l = document.getElementById('self-modify-toggle');
  return b ? {checked: b.checked, disabled: b.disabled,
              label: l ? l.innerText.trim() : '', title: l ? (l.getAttribute('title') || '') : '',
              attr: document.documentElement.getAttribute('data-tlm-self-modify')} : null; }"""
REST_FRAMES_JS = """() => (window.__tlmFrames || []).filter(f => f && f.kind === 'rest' && f.capacity
  && f.capacity.self_modify).map(f => ({bytes: Number(f.bytes_total) || 0,
  hist: Number(f.bytes_history) || 0,
  fixed: (Number(f.bytes_total) || 0) - (Number(f.bytes_history) || 0),
  tools: Number(f.capacity.tools_total) || 0,
  active: !!f.capacity.self_modify.active, locked: !!f.capacity.self_modify.locked,
  tokens: Number(f.capacity.self_modify.tokens) || 0, mode: f.capacity.mode}))"""
POPUP_TEXT_JS = """() => { const p = Array.from(document.querySelectorAll('.tlmpop-overlay'))
  .filter(e => e.id !== 'tlm-compact-overlay'); return p.length ? p[p.length - 1].innerText : null; }"""


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
def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        page.wait_for_timeout(500)
    return False


def close_compact_dialog(page):
    if page.locator("#tlm-compact-overlay").count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)


def wait_box(page, *, checked, disabled, timeout):
    deadline = time.time() + timeout
    box = None
    while time.time() < deadline:
        box = page.evaluate(BOX_JS)
        if box and box["checked"] == checked and box["disabled"] == disabled:
            return box
        page.wait_for_timeout(1000)
    return box


def wait_bot_text(page, needle, before, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        texts = page.evaluate(BOT_TEXTS_JS)[before:]
        hit = next((t for t in texts if needle in t), None)
        if hit:
            return hit
        page.wait_for_timeout(400)
    return ""


def wait_rest_frame(page, *, active, after, timeout=90):
    """The newest at-rest gauge frame with this Self-modify verdict, among
    the frames that arrived after index ``after``."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        frames = page.evaluate(REST_FRAMES_JS)[after:]
        hits = [f for f in frames if f["active"] == active]
        if hits:
            page.wait_for_timeout(1500)            # let a duplicate refresh settle
            frames = page.evaluate(REST_FRAMES_JS)[after:]
            hits = [f for f in frames if f["active"] == active]
            return hits[-1]
        page.wait_for_timeout(1000)
    return None


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
    ctx.add_init_script(FRAMES_INIT)
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
        body = page.inner_text("body")
        check("A1b no template comment shows on the page", "{#" not in body and "#}" not in body)
        check("A2 the Self-modify box IS on the page (dev mode = --self-modify)",
              page.locator("#self-modify-toggle").count() == 1)
        box = wait_box(page, checked=False, disabled=True, timeout=300)
        close_compact_dialog(page)
        check("A3a the box is unticked and greyed on %s" % model,
              box and not box["checked"] and box["disabled"], box)
        check("A3b it shows a padlock", box and "\U0001F512" in box["label"], box and box["label"])
        check("A3c the page knows it is locked", box and box["attr"] == "locked", box and box["attr"])
        frames = page.evaluate(REST_FRAMES_JS)
        last = frames[-1] if frames else {}
        check("A3d the gauge frame says the self-knowledge does not fit",
              bool(last) and last["locked"] and not last["active"] and last["tokens"] > 20000, last)
        shot(page, "A3_locked_off")

        page.click("#self-modify-toggle", force=True)
        page.wait_for_timeout(900)
        text = page.evaluate(POPUP_TEXT_JS) or ""
        say("   POPUP: %s" % text.replace("\n", " | ")[:600])
        check("A4a a click on the locked box explains why",
              "locked OFF" in text and model.split(":")[0] in text and "Config" in text, text[:300])
        shot(page, "A4_locked_click_explains")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        check("A4b Escape closes the explanation", not page.evaluate(POPUP_TEXT_JS))

        before = len(page.evaluate(BOT_TEXTS_JS))
        page.evaluate("""() => window.sendChatSocketMessage({type: 'set-self-modify',
            message: 'set-self-modify', enabled: true})""")
        msg = wait_bot_text(page, "Self-modify stays OFF", before, timeout=30)
        check("A5a a FORGED tick is refused by the server", bool(msg), msg[:240])
        box = page.evaluate(BOX_JS)
        check("A5b the box is still unticked and locked", box and not box["checked"] and box["disabled"], box)
        shot(page, "A5_forged_tick_refused")
    except Exception:                               # noqa: BLE001
        check("phase A itself crashed", False, traceback.format_exc()[-800:])
        shot(page, "A99_crash")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    text = server_log()
    check("A6a tlamatini.log: the self-knowledge does NOT fit - locked OFF",
          "does NOT fit - Self-modify is locked OFF" in text)
    check("A6b tlamatini.log: the fit line names it", "self-modify locked OFF" in text)
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_A.log"))


# ------------------------------------------------------------------ PHASE B
def phase_b(pw):
    browser, page = launch(pw)
    try:
        login(page)
        check("B1a logged in on the big model", wait_idle(page, 300))
        box = wait_box(page, checked=True, disabled=False, timeout=300)
        close_compact_dialog(page)
        check("B1b the box is ticked and unlocked (ON by default)",
              box and box["checked"] and not box["disabled"], box)
        check("B1c no padlock on a big model", box and "\U0001F512" not in box["label"], box and box["label"])
        on = wait_rest_frame(page, active=True, after=0)
        check("B1d the request at rest carries the self-knowledge", bool(on), on)
        shot(page, "B1_big_model_self_modify_on")

        # B2 - untick: the request really shrinks ----------------------------------
        n_frames = len(page.evaluate(REST_FRAMES_JS))
        before = len(page.evaluate(BOT_TEXTS_JS))
        page.click("#self-modify-enabled")
        msg = wait_bot_text(page, "Self-modify is OFF", before, timeout=30)
        check("B2a unticking says Self-modify is OFF", bool(msg), msg[:200])
        box = wait_box(page, checked=False, disabled=False, timeout=30)
        check("B2b the box is unticked and still unlocked", box and not box["checked"] and not box["disabled"], box)
        off = wait_rest_frame(page, active=False, after=n_frames)
        # Compared WITHOUT the chat history: the "Self-modify is ON/OFF" lines
        # join the history and slide older messages out of its 8-message window.
        saved = (on["fixed"] - off["fixed"]) if (on and off) else 0
        say("   BYTES at rest without history: ON %s -> OFF %s (saved %s); with history %s -> %s"
            % (on and on["fixed"], off and off["fixed"], saved, on and on["bytes"], off and off["bytes"]))
        check("B2c the request at rest shrank by the whole self-knowledge (>100,000 bytes)",
              saved > 100_000, "saved %d bytes" % saved)
        shot(page, "B2_self_modify_off")

        # B3 - tick: the bytes come back --------------------------------------------
        n_frames = len(page.evaluate(REST_FRAMES_JS))
        before = len(page.evaluate(BOT_TEXTS_JS))
        page.click("#self-modify-enabled")
        msg = wait_bot_text(page, "Self-modify is ON", before, timeout=30)
        check("B3a ticking says Self-modify is ON", bool(msg), msg[:200])
        again = wait_rest_frame(page, active=True, after=n_frames)
        # Compared with the OFF frame just before it: External MCP servers keep
        # connecting in the background and add tools between frames, so the
        # FIRST ON frame may carry fewer tools than these two.
        back = (again["fixed"] - off["fixed"]) if (again and off) else 0
        say("   BYTES at rest without history: OFF %s (%s tools) -> ON again %s (%s tools)"
            % (off and off["fixed"], off and off["tools"], again and again["fixed"], again and again["tools"]))
        check("B3b ticking brings the whole self-knowledge back (>100,000 bytes)", back > 100_000,
              "ON again - OFF = %d bytes" % back)
        box = page.evaluate(BOX_JS)
        check("B3c the box is ticked again", box and box["checked"] and not box["disabled"], box)
        shot(page, "B3_self_modify_on_again")
    except Exception:                               # noqa: BLE001
        check("phase B itself crashed", False, traceback.format_exc()[-800:])
        shot(page, "B99_crash")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    text = server_log()
    check("B4a tlamatini.log records Self-modify OFF by the user", "[SELF-MODIFY] Self-modify OFF (user" in text)
    check("B4b tlamatini.log records Self-modify ON by the user", "[SELF-MODIFY] Self-modify ON (user" in text)
    tracebacks = [ln for ln in text.splitlines() if "Traceback" in ln]
    check("B4c tlamatini.log has no Traceback", not tracebacks, tracebacks[:3])
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_B.log"))


# ------------------------------------------------------------------ main
RESET_CODE = """
from agent import compact_mode as cm
from agent.models import CompactState
row = CompactState.objects.filter(pk=1).first()
if row and row.active:
    cm.leave_compact(%r, force=True)
CompactState.objects.filter(pk=1).update(self_modify=True)
print('RESET done: Compact mode OFF, every row ON, Self-modify ON')
"""


def reset_state(why):
    """Every row ON, Compact mode OFF, Self-modify ON - the state a fresh
    install has.  Runs with the server STOPPED (manage.py truncates the log)."""
    try:
        out = subprocess.run([sys.executable, "manage.py", "shell", "-c", RESET_CODE % why],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=240)
        line = next((ln for ln in out.stdout.splitlines() if ln.startswith("RESET")),
                    "RESET gave no answer: " + (out.stderr or "")[-300:])
    except Exception as exc:                        # noqa: BLE001
        line = "RESET failed: %s" % exc
    say("   " + line)
    return line.startswith("RESET done")


def finish(sha_before, code_if_ok=0):
    stop_server(PORT)
    time.sleep(2.0)
    check("C the dev database is back (every row ON, Self-modify ON)",
          reset_state("visible test: leave every row ON"))
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
    say("SELF-MODIFY BOX - VISIBLE E2E   (Angela Lopez Mendoza)")
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
        # The new column (migration 0212) must exist before the reset writes it.
        out = subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=600)
        say("   migrate: exit %s %s" % (out.returncode, (out.stdout or "").strip().splitlines()[-1:]))
        reset_state("visible test: start from every row ON")
        state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
        if not state.get("ok"):
            say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
            return finish(sha_before, 4)
        phase_a(pw, model)
        stop_server(PORT)
        time.sleep(3.0)
        reset_state("visible test: phase B starts with Compact mode OFF")

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
