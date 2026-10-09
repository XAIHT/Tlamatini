"""TOO MANY STOP SEQUENCES - VISIBLE end-to-end test (Angela Lopez Mendoza, 2026-10-03).

The bug: a Multi-Turn prompt sent right after a long answer died before any
work was done with "too many stop sequences; maximum is 4 (status code: 400)".
The chat LLM carried NINE stop sequences; Ollama's cloud models refuse five or
more, and the first call made with that LLM was the chat-history summary.

Headed real Chrome, the real chat GUI, the dev source server on port 8024,
Shoter full-screen photos. ONLY the models Angela allowed:
  PHASE 0  the stop list rag/factory.py really sends, straight to Ollama:
           glm-5.2:cloud and qwen2.5:latest accept it; glm-5.2:cloud still
           refuses the OLD nine (so this test exercises the real limit).
  PHASE A  glm-5.2:cloud: her CPU question, then her book-search prompt
           (Lumen Book Reader + Memory, read only), then a torrent-search-mcp
           prompt for a legal file - each one after a long answer, so the
           history summary runs every time.
  PHASE B  qwen2.5:latest locked in COMPACT mode: the same kind of sequence.
  PHASE C  glm-5.2:cloud with Self-modify UNTICKED by a click for her two
           prompts, then ticked again for a follow-up (both states).
Run one part only with --phases C (or 0AB, ...).
For every answer: it arrives, it is not an error, it carries no runaway turn.
tlamatini.log: "[LLM-STOP] <model>: 4 stop sequences", the history summary
ran and never failed, every Multi-Turn request reached the agent, no 400.
config.json, the dev database and Angela's Memory graph are restored/checked.

Exit codes: 0 = all checks passed, 1 = a check failed, 4 = environment.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

PORT = 8024
os.environ["TLAMATINI_BASE_URL"] = "http://127.0.0.1:%d" % PORT
os.environ.pop("CONFIG_PATH", None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
AGENT = os.path.join(REPO, "Tlamatini", "agent")
RUN_DIR = os.path.join(REPO, "Temp", "stop_sequence_visible")
PHOTOS_DIR = os.path.join(RUN_DIR, "photos")
RUN_LOG = os.path.join(RUN_DIR, "run.log")
REAL_CONFIG = os.path.join(AGENT, "config.json")
BACKUP = os.path.join(RUN_DIR, "config.backup.json")
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
MEMORY_GRAPH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tlamatini", "memory", "memory.json")
MEMORY_BACKUP = os.path.join(RUN_DIR, "memory.backup.json")
OLLAMA = "http://127.0.0.1:11434"
GLM = "glm-5.2:cloud"          # the ONLY cloud model Angela allowed for this test
QWEN = "qwen2.5:latest"        # local, locked in Compact mode
OLD_NINE = ["<|endoftext|>", "<|im_start|>", "<|im_end|>", "\nHuman:", "\nUser:",
            "\nAssistant:", "\nSystem:", "\nAI:", "\nEND-RESPONSE\n"]

Q_CPU = "What is te actual CPU usage, memory usage, and disk space?, please."
Q_BOOKS = ("Tlamatini, using Lumen Book Reader mcp, search thoroughly my catalog for up to 10 books "
           "related to the following topics: 'Complex Analysis' or 'Complex Variables', and list each "
           "one with its title and author, following all the rules and recommendations that apply from "
           "Memory external mcp (only READ the Memory external mcp - do not create, change or delete "
           "anything in it), go!.")
Q_TORRENT = ("Tlamatini, using torrent-search-mcp, search for the official Ubuntu 24.04 LTS desktop ISO "
             "torrent and give me its complete magnet link, following the rules and recommendations that "
             "apply from Memory external mcp (only READ it - do not change it), go!.")
Q_FOLLOW = "Tlamatini, which of the values in your earlier answer is the highest? Answer in one short sentence."

FAIL_MARKERS = ("too many stop sequences", "Your agent cannot process your requests",
                "Error detail:", "status code: 400",
                # Tlamatini's first-person forms (2026-10-09, agent/constants.py).
                "I can't process your requests", "This is the error I ran into:")
RUNAWAY = re.compile(r"(^|\n)\s*(Human|User):|<\|im_start\|>|<\|endoftext\|>")

RESULTS: list = []
PHOTOS: list = []

IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""
BOT_TEXTS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message.bot-message'))
  .map(m => { const b = m.querySelector('.automated-message-body') || m; return b.innerText || ''; })"""
COMPACT_JS = """() => { const b = document.getElementById('compact-mode-enabled');
  return b ? {checked: b.checked, disabled: b.disabled} : null; }"""


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
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""


def server_log():
    try:
        with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


_RESTORED = {"done": False}


def restore_config():
    if _RESTORED["done"] or not os.path.isfile(BACKUP):
        return
    shutil.copyfile(BACKUP, REAL_CONFIG)
    _RESTORED["done"] = True
    say("dev config.json restored from %s" % BACKUP)


def write_config(chat_model):
    with open(BACKUP, "r", encoding="utf-8-sig") as fh:
        config = json.load(fh)
    for key, value in list(config.items()):        # every cloud model -> glm-5.2:cloud ONLY
        if isinstance(value, str) and re.search(r"[:\-]cloud$", value.strip()):
            config[key] = GLM
    config.update({"chained-model": chat_model, "unified_agent_model": chat_model,
                   "ollama_base_url": OLLAMA, "unified_agent_base_url": OLLAMA,
                   "context_compact_mode": "auto", "context_ceiling_tokens": 0,
                   "context_gauge_probe_enable": False, "context_gauge_probe_after_answer": False,
                   # Angela's own summary settings: the summary runs after any real answer.
                   "history_summary_enable": True, "history_summary_trigger_tokens": 150,
                   "history_keep_last_turns": 3})
    with open(REAL_CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------ PHASE 0
def _module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def factory_stop_list():
    """The list rag/factory.py sends, fitted by ollama_stop.py - read from the
    real source, not copied into this test."""
    stop_mod = _module_from(os.path.join(AGENT, "ollama_stop.py"), "tlm_ollama_stop")
    with open(os.path.join(AGENT, "rag", "factory.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    raw = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_CHAT_STOP_TOKENS" for t in node.targets):
            raw = list(ast.literal_eval(node.value))
    return stop_mod.fit_stop_sequences(raw or [], GLM), raw


def ollama_generate(model, stops):
    body = json.dumps({"model": model, "prompt": "Reply with the single word OK.", "stream": False,
                       "options": {"stop": stops, "num_predict": 24, "temperature": 0}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            return 200, str(data.get("response", ""))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:240]
    except Exception as exc:                        # noqa: BLE001
        return 0, str(exc)[:240]


def phase_0():
    stops, raw = factory_stop_list()
    say("   factory list (%d): %r -> fitted %r" % (len(raw or []), raw, stops))
    check("0a rag/factory.py sends at most 4 stop sequences", 0 < len(stops) <= 4, stops)
    code, text = ollama_generate(GLM, stops)
    check("0b %s ACCEPTS the list Tlamatini sends" % GLM, code == 200, "HTTP %s %s" % (code, text[:120]))
    code, text = ollama_generate(GLM, OLD_NINE)
    check("0c %s still REFUSES the old nine (the test exercises the real limit)" % GLM,
          code == 400 and "stop sequences" in text, "HTTP %s %s" % (code, text[:160]))
    code, text = ollama_generate(QWEN, stops)
    check("0d %s ACCEPTS the list and answers" % QWEN, code == 200 and text.strip(),
          "HTTP %s %r" % (code, text[:120]))


# ------------------------------------------------------------------ page helpers
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


def is_busy_text(text):
    low = text.strip().lower()
    return any(marker.lower() in low for marker in C.BUSY_MARKERS) or not low


def ask(page, question, label, timeout):
    before = len(page.evaluate(BOT_TEXTS_JS))
    started = time.time()
    say(">> ASK %s: %s" % (label, question[:160]))
    page.fill(C.SEL["chat_input"], question)
    page.click(C.SEL["chat_submit"])
    busy_deadline = time.time() + 45
    while time.time() < busy_deadline and page.evaluate(IDLE_JS):
        page.wait_for_timeout(250)
    finished = False
    deadline = time.time() + timeout
    last_report = 0.0
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            finished = True
            break
        if time.time() - last_report > 15:          # live progress, never silent
            last_report = time.time()
            texts = page.evaluate(BOT_TEXTS_JS)[before:]
            say("   ... %s still working (%.0fs), %d new card(s): %s" % (
                label, time.time() - started, len(texts),
                (texts[-1].replace("\n", " | ")[:140] if texts else "-")))
        page.wait_for_timeout(1000)
    page.wait_for_timeout(1000)
    texts = page.evaluate(BOT_TEXTS_JS)[before:]
    answer = "\n".join(t for t in texts if not is_busy_text(t)).strip()
    seconds = time.time() - started
    say("   ANSWER %s (%.1fs, %d chars): %s" % (label, seconds, len(answer), answer.replace("\n", " | ")[:500]))
    shot(page, label)
    return finished, answer


def judge(label, finished, answer):
    check("%s the answer arrived (the page is free again)" % label, finished)
    check("%s the answer is not empty" % label, len(answer) > 20, "%d chars" % len(answer))
    bad = [m for m in FAIL_MARKERS if m.lower() in answer.lower()]
    check("%s it is NOT the stop-sequence error" % label, not bad, bad)
    check("%s no runaway turn in the answer (Human:/User:/<|im_start|>)" % label,
          not RUNAWAY.search(answer), (RUNAWAY.search(answer) or [""])[0])


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


def log_checks(tag, model, text, expect_requests):
    check("%s tlamatini.log: [LLM-STOP] %s sends 4 stop sequences" % (tag, model),
          "[LLM-STOP] %s: 4 stop sequences" % model in text)
    check("%s tlamatini.log: no 'too many stop sequences' anywhere" % tag, "too many stop sequences" not in text)
    summaries = text.count("[HISTORY-SUMMARY] chat history summarized")
    check("%s tlamatini.log: the chat-history summary RAN on %s (%d time(s))" % (tag, model, summaries),
          summaries >= 1)
    check("%s tlamatini.log: the summary never failed" % tag,
          "[HISTORY-SUMMARY] the chat-history summary failed" not in text)
    started = text.count("UnifiedAgentChain: Processing request with tool-enabled agent")
    reached = text.count("UnifiedAgentChain: Invoking unified agent with input length")
    check("%s tlamatini.log: every Multi-Turn request reached the agent (%d of %d)" % (tag, reached, started),
          started >= expect_requests and reached == started)
    check("%s tlamatini.log: no '!!! ERROR in queue_llm_retrieval'" % tag,
          "!!! ERROR in queue_llm_retrieval" not in text)


# ------------------------------------------------------------------ PHASES A / B
def run_phase(pw, tag, model, questions, compact):
    browser, page = launch(pw)
    try:
        login(page)
        check("%s1 logged in and the chat page is ready" % tag, wait_idle(page, 300))
        if compact:
            deadline = time.time() + 240
            box = None
            while time.time() < deadline:
                box = page.evaluate(COMPACT_JS)
                if box and box["checked"] and box["disabled"]:
                    break
                page.wait_for_timeout(1000)
            close_compact_dialog(page)
            check("%s1b Compact mode is ON and locked for %s" % (tag, model),
                  bool(box) and box["checked"] and box["disabled"], box)
        close_compact_dialog(page)
        set_toggle(page, "#multi-turn-enabled", True)
        set_toggle(page, "#exec-report-enabled", True)
        set_toggle(page, "#acpx-enabled", False)
        check("%s1c Multi-Turn is ON" % tag, page.is_checked("#multi-turn-enabled"))
        shot(page, "%s1_ready_%s" % (tag, re.sub(r"\W+", "_", model)))
        for n, (question, timeout) in enumerate(questions, start=2):
            label = "%s%d" % (tag, n)
            finished, answer = ask(page, question, label, timeout)
            judge(label, finished, answer)
            close_compact_dialog(page)
    except Exception:                               # noqa: BLE001
        check("phase %s itself crashed" % tag, False, traceback.format_exc()[-800:])
        shot(page, "%s99_crash" % tag)
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    text = server_log()
    log_checks(tag, model, text, len(questions))
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_%s.log" % tag))


SELF_BOX_JS = """() => { const b = document.getElementById('self-modify-enabled');
  return b ? {checked: b.checked, disabled: b.disabled} : null; }"""


def click_self_modify(page, want_on, label):
    """Click the Self-modify box like a user and wait for the server's answer."""
    before = len(page.evaluate(BOT_TEXTS_JS))
    page.click("#self-modify-enabled")
    needle = "Self-modify is ON" if want_on else "Self-modify is OFF"
    deadline = time.time() + 30
    said = ""
    while time.time() < deadline:
        said = next((t for t in page.evaluate(BOT_TEXTS_JS)[before:] if needle in t), "")
        if said:
            break
        page.wait_for_timeout(400)
    box = page.evaluate(SELF_BOX_JS)
    check("%s the chat says '%s'" % (label, needle), bool(said), said[:160])
    check("%s the box is %s" % (label, "ticked" if want_on else "UNticked"),
          bool(box) and box["checked"] == want_on and not box["disabled"], box)
    shot(page, "%s_self_modify_%s" % (label, "on" if want_on else "off"))


def run_phase_c(pw):
    """glm-5.2:cloud with Self-modify UNTICKED by a click for her two prompts,
    then ticked again for a follow-up: both states and both transitions."""
    tag = "C"
    browser, page = launch(pw)
    try:
        login(page)
        check("C1 logged in and the chat page is ready", wait_idle(page, 300))
        close_compact_dialog(page)
        deadline = time.time() + 120
        box = None
        while time.time() < deadline:
            box = page.evaluate(SELF_BOX_JS)
            if box and box["checked"] and not box["disabled"]:
                break
            page.wait_for_timeout(1000)
        check("C1b the Self-modify box is there, ticked and unlocked on %s" % GLM,
              bool(box) and box["checked"] and not box["disabled"], box)
        set_toggle(page, "#multi-turn-enabled", True)
        set_toggle(page, "#exec-report-enabled", True)
        set_toggle(page, "#acpx-enabled", False)
        click_self_modify(page, False, "C1c")
        finished, answer = ask(page, Q_CPU, "C2", 420)
        judge("C2 (Self-modify OFF)", finished, answer)
        finished, answer = ask(page, Q_BOOKS, "C3", 1200)
        judge("C3 (Self-modify OFF, after a long answer)", finished, answer)
        click_self_modify(page, True, "C4a")
        finished, answer = ask(page, Q_FOLLOW, "C4", 600)
        judge("C4 (Self-modify ON again)", finished, answer)
    except Exception:                               # noqa: BLE001
        check("phase C itself crashed", False, traceback.format_exc()[-800:])
        shot(page, "C99_crash")
    finally:
        try:
            browser.close()
        except Exception:                           # noqa: BLE001
            pass
    text = server_log()
    log_checks(tag, GLM, text, 3)
    check("C tlamatini.log: the user switched Self-modify OFF", "[SELF-MODIFY] Self-modify OFF (user" in text)
    check("C tlamatini.log: the user switched Self-modify ON again", "[SELF-MODIFY] Self-modify ON (user" in text)
    check("C tlamatini.log: requests really ran with Self-modify OFF", "| self-modify OFF" in text)
    tracebacks = [ln for ln in text.splitlines() if "Traceback" in ln]
    check("C tlamatini.log: no Traceback", not tracebacks, tracebacks[:3])
    shutil.copyfile(SERVER_LOG, os.path.join(RUN_DIR, "tlamatini_phase_C.log"))


RESET_CODE = """
from agent import compact_mode as cm
from agent.models import AgentMessage, CompactState
row = CompactState.objects.filter(pk=1).first()
if row and row.active:
    cm.leave_compact(%r, force=True)
CompactState.objects.filter(pk=1).update(self_modify=True)
n = AgentMessage.objects.filter(conversation_user__username=%r).delete()[0]
print('RESET done: Compact mode OFF, every row ON, Self-modify ON, %%d test messages cleared' %% n)
"""


def reset_state(why):
    """Every row ON, Compact OFF, Self-modify ON and an empty chat for the test
    user. Runs with the server STOPPED (manage.py truncates the log)."""
    try:
        out = subprocess.run([sys.executable, "manage.py", "shell", "-c", RESET_CODE % (why, C.USERNAME)],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=240)
        line = next((ln for ln in out.stdout.splitlines() if ln.startswith("RESET")),
                    "RESET gave no answer: " + (out.stderr or "")[-300:])
    except Exception as exc:                        # noqa: BLE001
        line = "RESET failed: %s" % exc
    say("   " + line)
    return line.startswith("RESET done")


def finish(sha_before, memory_sha, code_if_ok=0):
    stop_server(PORT)
    time.sleep(3.0)
    check("C the dev database is back (every row ON, Compact OFF)", reset_state("visible test: leave every row ON"))
    restore_config()
    check("C the dev config.json is back byte for byte", sha256(REAL_CONFIG) == sha_before)
    if memory_sha:
        same = sha256(MEMORY_GRAPH) == memory_sha
        if not same and os.path.isfile(MEMORY_BACKUP):
            shutil.copyfile(MEMORY_BACKUP, MEMORY_GRAPH)
            say("   the Memory graph CHANGED during the test - restored from %s" % MEMORY_BACKUP)
        check("C Angela's Memory graph was not changed by the test", same)
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
    say("TOO MANY STOP SEQUENCES - VISIBLE E2E on %s and %s (Compact)   (Angela Lopez Mendoza)" % (GLM, QWEN))
    say("=" * 78)
    shutil.copyfile(REAL_CONFIG, BACKUP)
    sha_before = sha256(REAL_CONFIG)
    memory_sha = sha256(MEMORY_GRAPH)
    if memory_sha:
        shutil.copyfile(MEMORY_GRAPH, MEMORY_BACKUP)
        say("Memory graph backed up (%s)" % MEMORY_GRAPH)

    phases = "0ABC"
    if "--phases" in sys.argv:
        phases = sys.argv[sys.argv.index("--phases") + 1].upper()
    say("phases: %s" % phases)
    if "0" in phases:
        say("PHASE 0 - the stop list Tlamatini really sends, straight to Ollama")
        phase_0()

    with sync_playwright() as pw:
        if stop_server(PORT):
            time.sleep(2.0)
        out = subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                             cwd=os.path.join(REPO, "Tlamatini"), capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=600)
        say("   migrate: exit %s" % out.returncode)

        if "A" in phases:
            say("PHASE A - %s, Self-modify ticked, the same kind of conversation that failed" % GLM)
            reset_state("visible test: phase A")
            write_config(GLM)
            state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
            if not state.get("ok"):
                say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
                return finish(sha_before, memory_sha, 4)
            run_phase(pw, "A", GLM, [(Q_CPU, 420), (Q_BOOKS, 1200), (Q_TORRENT, 1200)], compact=False)
            stop_server(PORT)
            time.sleep(3.0)

        if "B" in phases:
            say("PHASE B - %s locked in COMPACT mode (Self-modify locked OFF)" % QWEN)
            reset_state("visible test: phase B")
            write_config(QWEN)
            state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
            if not state.get("ok"):
                say("!! ENVIRONMENT NOT READY for phase B: %s" % state.get("reason"))
                return finish(sha_before, memory_sha, 4)
            run_phase(pw, "B", QWEN, [(Q_CPU, 600), (Q_BOOKS, 900), (Q_FOLLOW, 600)], compact=True)
            stop_server(PORT)
            time.sleep(3.0)

        if "C" in phases:
            say("PHASE C - %s, Self-modify UNTICKED by a click, then ticked again" % GLM)
            reset_state("visible test: phase C")
            write_config(GLM)
            state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
            if not state.get("ok"):
                say("!! ENVIRONMENT NOT READY for phase C: %s" % state.get("reason"))
                return finish(sha_before, memory_sha, 4)
            run_phase_c(pw)
    return finish(sha_before, memory_sha)


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
