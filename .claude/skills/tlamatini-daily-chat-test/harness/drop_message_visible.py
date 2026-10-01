# Tlamatini Author Banner - do not remove
r"""
THE DROP BUTTON - VISIBLE END-TO-END TEST (Angela Lopez Mendoza, 2026-09-30)
============================================================================

"Create a new button with the label 'Drop' with a dialog of confirmation ...
the user must be able to delete messages from the history chat, and erase them
from the history chain processed by the llm too ... as if the deleted messages
have never been existed and previous messages and posterior messages to the
deleted one must stay there untouched, AND FOR BOTH TYPE OF MESSAGES".

HEADED real Chrome, the real chat GUI, the SOURCE server on :8001 (never the
installed Tlamatini on :8000). Every step is photographed by Shoter (whole
desktop). The run:

  0. Clean History, so no earlier run can leak the secret into this one.
  1. Tell her three facts, one per message: a colour (BEFORE), a secret code
     word (the one we will DROP), a pet's name (AFTER).
  2. Drop button on a card: the themed dialog explains what the LLM will do,
     asks "Are you sure", has a red Drop and a focused Cancel.
     Cancel keeps the card; Escape keeps the card.
  3. DROP the user's code-word message   (type 1: a USER message)
  4. DROP Tlamatini's answer to it       (type 2: a TLAMATINI message)
     THE CONTEXT RING, before and after each drop: the ring beside the
     message box must be recalculated. After EACH drop a new at-rest frame
     tagged "message dropped" arrives with Ollama's REAL token count - the
     same prompt_eval_count the server logged for that request - and after
     both drops the count is LOWER than it was before the first one.
  5. DROP a live status line (never saved) - only the screen changes.
  6. Ask what she remembers. GROUND TRUTH from the server log: the history
     the model received has the colour and the pet, and NOT the code word.
     Her answer names the colour and the pet, and not the code word.
  7. No reconnect happened: same page, same socket, no new connection.
  8. Reload: the dropped messages do not come back; the others do.

Exit codes: 0 all passed, 1 a check failed, 4 the environment could not be
established (named reason, no traceback).
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import time
import traceback

os.environ.setdefault("TLAMATINI_BASE_URL", "http://127.0.0.1:8001")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C                               # noqa: E402
from preflight import ensure_ready, stop_server  # noqa: E402
from shoter_shot import take_shot                # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
STAMP = time.strftime("%Y%m%d_%H%M%S")
OUT = os.path.join(REPO, "Temp", "drop_message", "visible_run")
RUN_LOG = os.path.join(REPO, "Temp", "drop_message", "e2e_%s.log" % STAMP)
SERVER_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
DB_PATH = os.path.join(REPO, "Tlamatini", "db.sqlite3")
os.makedirs(OUT, exist_ok=True)

CODE = "PAPAYA-%04d" % random.randint(1000, 9999)
COLOUR = "teal"
PET = "Luna"
# "without using any tool": measured 2026-09-30, with the External MCP "memory"
# server active she copied every fact into Angela's REAL long-term memory graph
# (%LOCALAPPDATA%\Tlamatini\memory\memory.json, shared by every install). The
# test is about the CHAT history, so it must neither write there nor read the
# answer back from there. memory_guard() below proves it and cleans up if not.
NO_TOOLS = " Reply in one short sentence, without using any tool?"
M1 = "Can you remember that my favourite colour is %s?%s" % (COLOUR, NO_TOOLS)
M2 = "Can you remember that my secret code word is %s?%s" % (CODE, NO_TOOLS)
M3 = "Can you remember that my cat is called %s?%s" % (PET, NO_TOOLS)
Q = ("What is my favourite colour, what is my cat called, and what secret code word "
     "did I give you? If I never gave you a code word, write exactly NO CODE WORD for it. "
     "Answer from this conversation only, without using any tool?")
MEMORY_JSON = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tlamatini", "memory", "memory.json")
MEMORY_WRITES = ("ext__memory__create_entities", "ext__memory__add_observations",
                 "ext__memory__create_relations")

RESULTS = []
PHOTOS = []
SENT_FRAMES = []


def say(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:400]))
    say(("[PASS] " if ok else "[FAIL] ") + name + (("   -> " + str(detail)[:240]) if detail else ""))
    return bool(ok)


def shot(page, name):
    """Photograph the WHOLE desktop with Shoter - the browser in front first."""
    try:
        page.bring_to_front()
        time.sleep(0.6)
        focused = page.evaluate("document.hasFocus()")
    except Exception:                               # noqa: BLE001
        focused = False
    if not focused:
        say("   (the page reports no focus - photographing anyway, flagged)")
    path = take_shot(OUT, "%s.png" % name)
    PHOTOS.append((name, path, focused))
    say("   PHOTO %s -> %s" % (name, path))
    return path


# ---------------------------------------------------------------- the page
CARDS_JS = """() => Array.from(document.querySelectorAll('#chat-log .message')).map(e => ({
  id: e.dataset.messageId || '',
  bot: e.classList.contains('bot-message'),
  text: ((e.querySelector('.automated-message') || e.querySelector('.message-content') || e).innerText || '').trim(),
  hasDrop: !!e.querySelector('.message-drop-btn')
}))"""

IDLE_JS = """() => { const i = document.querySelector('#chat-message-input');
  return !!i && !i.readOnly && !document.getElementById('wait-spinner'); }"""

DIALOG_JS = """() => { const o = document.querySelector('.tlmpop-overlay');
  if (!o || o.style.display === 'none') return null;
  const t = s => { const n = o.querySelector(s); return n ? n.textContent : ''; };
  return { title: t('.tlmpop-title'), primary: t('.tlmpop-msg'), secondary: t('.tlmpop-sub'),
           buttons: Array.from(o.querySelectorAll('.tlmpop-foot button')).map(b => ({
               label: b.textContent.trim(), danger: b.classList.contains('tlmpop-btn-danger'),
               background: getComputedStyle(b).backgroundColor })),
           focused: document.activeElement ? document.activeElement.textContent.trim() : '' }; }"""


def cards(page):
    return page.evaluate(CARDS_JS) or []


def card_sel(message_id):
    return '#chat-log .message[data-message-id="%s"]' % message_id


def wait_idle(page, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(IDLE_JS):
            return True
        time.sleep(0.5)
    return False


def ask(page, text, label, timeout=480):
    """Send one prompt; return (user_card, answer_card), both WITH a saved id."""
    for attempt in range(1, 7):
        known = {c["id"] for c in cards(page) if c["id"]}
        n_before = len(cards(page))
        page.fill(C.SEL["chat_input"], text)
        page.click(C.SEL["chat_submit"])
        say("   sent (%s, attempt %d): %s" % (label, attempt, text[:90]))
        deadline = time.time() + timeout
        user_card, not_ready, last_note = None, False, time.time()
        while time.time() < deadline:
            now = cards(page)
            fresh = [c for c in now if c["id"] and c["id"] not in known]
            if user_card is None:
                for c in fresh:
                    if not c["bot"] and text[:40] in c["text"]:
                        user_card = c
                if user_card is None and any(
                        m in c["text"] for c in now[n_before:] if c["bot"] for m in C.NOT_READY_MARKERS):
                    not_ready = True
                    break
            else:
                answers = [c for c in fresh if c["bot"]]
                if answers and page.evaluate(IDLE_JS):
                    time.sleep(1.0)
                    answers = [c for c in cards(page) if c["id"] and c["id"] not in known and c["bot"]]
                    say("   answer (%s) id=%s: %s" % (label, answers[-1]["id"], answers[-1]["text"][:160]))
                    return user_card, answers[-1]
            if time.time() - last_note > 15:
                say("   ... waiting for %s (user card %s)" % (label, "saved" if user_card else "not yet"))
                last_note = time.time()
            time.sleep(1.0)
        if not_ready:
            say("   the agent was not ready yet - waiting 10 s and sending again")
            time.sleep(10)
            wait_idle(page, 120)
            continue
        return user_card, None
    return None, None


def open_drop_dialog(page, selector):
    page.locator(selector + " .message-drop-btn").first.click()
    page.wait_for_selector(".tlmpop-overlay", state="visible", timeout=8000)
    time.sleep(0.4)                     # focus is applied on the next tick
    return page.evaluate(DIALOG_JS)


def dialog_gone(page, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(DIALOG_JS) is None:
            return True
        time.sleep(0.2)
    return False


def card_gone(page, selector, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.locator(selector).count() == 0:
            return True
        time.sleep(0.3)
    return False


# ------------------------------------------------------- the context ring
# Every gauge frame is stored WITH the ring exactly as the gauge drew it for
# that frame. The gauge renders synchronously inside dispatchEvent and the
# next frame can replace it within a second, so polling the ring would lose
# that race - the same technique context_gauge_real_lab.py uses.
RING_JS = """function () {
  var el = document.getElementById('context-gauge-row');
  if (!el) return null;
  var t = function (s) { var n = el.querySelector(s); return n ? (n.textContent || '').trim() : ''; };
  return {tokens: t('.ctxg-tokens'), sub: t('.ctxg-title-sub'), bytes: t('.ctxg-bytes')};
}"""

COLLECT = """
window.__gauge = [];
(function () {
  var readRing = %s;
  var original = EventTarget.prototype.dispatchEvent;
  EventTarget.prototype.dispatchEvent = function (event) {
    var result = original.apply(this, arguments);
    try {
      if (event && event.type === 'tlm:context-gauge') {
        var frame = JSON.parse(JSON.stringify(event.detail || {}));
        frame.__ring = readRing();
        window.__gauge.push(frame);
      }
    } catch (_) {}
    return result;
  };
})();
""" % RING_JS

READ_RING = "() => (%s)()" % RING_JS


def gauge_frames(page):
    try:
        return page.evaluate("window.__gauge || []")
    except Exception:                               # noqa: BLE001
        return []


def wait_rest_real(page, start, reason, timeout):
    """The newest AT-REST frame tagged `reason` that carries Ollama's REAL
    count and was produced after every live frame seen since `start` (so an
    older request's late frame can never be mistaken for this one)."""
    deadline = time.time() + timeout
    last_note = time.time()
    while time.time() < deadline:
        new = gauge_frames(page)[start:]
        live_max = max([int(f.get("seq") or 0) for f in new if f.get("kind") == "live"] or [0])
        found = [f for f in new if f.get("kind") == "rest" and f.get("ratio_is_real") is True
                 and reason in str(f.get("label", "")) and int(f.get("seq") or 0) > live_max]
        if found:
            return found[-1]
        if time.time() - last_note > 10:
            ring = page.evaluate(READ_RING) or {}
            say("   ... waiting for the ring (%s) | ring now: %s | %s"
                % (reason, ring.get("tokens"), ring.get("sub")))
            last_note = time.time()
        time.sleep(0.5)
    return None


def logged_real(seq, wait=5.0):
    """Ollama's prompt_eval_count for request `seq`, as the SERVER logged it."""
    pattern = re.compile(r"\[CONTEXT-REAL\][^\n]*?seq=%d [^\n]*?prompt_eval_count=(\d+)" % seq)
    deadline = time.time() + wait
    while True:
        try:
            hits = pattern.findall(server_log_from(0))
        except OSError:
            hits = []
        if hits or time.time() >= deadline:
            return int(hits[-1]) if hits else None
        time.sleep(0.25)


def ring_digits(text):
    return re.sub(r"\D", "", (text or "").split("tokens")[0])


def check_ring(step, frame):
    """Did the ring get a new at-rest frame, and is it Ollama's REAL count -
    the very number the server logged for that request?"""
    if not check("%s: a new at-rest frame reached the ring" % step, frame is not None,
                 "" if frame is not None else "none within the timeout"):
        return None
    ring = frame.get("__ring") or {}
    real = frame.get("tokens_real")
    logged = logged_real(int(frame.get("seq") or 0))
    say("   RING %s: %s | %s | seq %s, history %s B"
        % (step, ring.get("tokens"), frame.get("label"), frame.get("seq"), frame.get("bytes_history")))
    check("%s: the ring shows Ollama's count as REAL" % step,
          "REAL" in (ring.get("tokens") or "") and ring_digits(ring.get("tokens")) == str(real),
          "ring=%r frame=%s" % (ring.get("tokens"), real))
    check("%s: it is the prompt_eval_count the server logged for that request" % step,
          logged is not None and logged == real, "log=%s frame=%s" % (logged, real))
    return frame


# ------------------------------------------------------------- the truth
def db_ids(ids):
    """Which of these AgentMessage ids still exist (read-only connection)."""
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH.replace("\\", "/"), uri=True, timeout=10)
    try:
        marks = ",".join("?" * len(ids))
        rows = con.execute("SELECT id FROM agent_agentmessage WHERE id IN (%s)" % marks,
                           [int(i) for i in ids]).fetchall()
        return {str(r[0]) for r in rows}
    finally:
        con.close()


def server_log_from(offset):
    with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        return fh.read()


def history_lines(text):
    """The lines chat_history_loader prints for every message it hands the model."""
    return [ln for ln in text.splitlines() if "message to chat history:" in ln]


OLLAMA_DOWN = "Failed to connect to Ollama"


def ollama_unreachable(offset, wait):
    """True when the SERVER's own log says, since `offset`, that it could not
    reach Ollama. Waits up to `wait` s for the ring's refresh to report (a
    probe line means Ollama answered). The log is the authority: it is the
    server's real connection, wherever its config points Ollama."""
    deadline = time.time() + wait
    while True:
        text = server_log_from(offset)
        if OLLAMA_DOWN in text:
            return True
        if "[CONTEXT-PROBE]" in text or "[CONTEXT-REAL]" in text or time.time() >= deadline:
            return False
        time.sleep(1.0)


def memory_lines():
    try:
        with open(MEMORY_JSON, "r", encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return None


def memory_guard(before, log_offset):
    """Angela's REAL memory graph must come out of this test untouched.

    Returns (ok, detail). If the model wrote a test fact anyway, remove ONLY
    the lines this run added that carry one of its three test facts, and say
    so - a pass must never hide that her memory had to be repaired.
    """
    writes = [ln.strip() for ln in server_log_from(log_offset).splitlines()
              if "Tool calls requested" in ln and any(w in ln for w in MEMORY_WRITES)]
    after = memory_lines()
    if before is None or after is None:
        return not writes, "memory.json not readable; memory-tool writes seen: %d" % len(writes)
    old = set(before)
    added = [ln for ln in after if ln not in old]
    leaked = [ln for ln in added if CODE in ln or PET in ln or COLOUR in ln]
    if leaked:
        kept = [ln for ln in after if ln not in set(leaked)]
        with open(MEMORY_JSON, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(kept) + "\n")
        say("   !! the model wrote %d test fact(s) into the memory graph - REMOVED them again" % len(leaked))
    return (not writes and not leaked,
            "memory-tool writes: %d, test lines added to memory.json: %d (removed)" % (len(writes), len(leaked)))


# ------------------------------------------------------------------ main
def main():
    say("=" * 78)
    say("THE DROP BUTTON - VISIBLE E2E   (Angela Lopez Mendoza)   code word %s" % CODE)
    say("target %s   server log %s" % (C.BASE_URL, SERVER_LOG))
    say("=" * 78)
    if ":8000" in C.BASE_URL:
        say("!! refusing to run against :8000 - that is the INSTALLED Tlamatini, not this code")
        return 4
    for old in os.listdir(OUT):
        if old.lower().endswith(".png"):
            try:
                os.remove(os.path.join(OUT, old))
            except OSError:
                pass
    # A server that is already running serves the OLD code: start a fresh one.
    port = int(C.BASE_URL.rsplit(":", 1)[1])
    if stop_server(port):
        time.sleep(2.0)
    state = ensure_ready(C.BASE_URL, C.USERNAME, C.PASSWORD)
    if not state.get("ok"):
        say("!! ENVIRONMENT NOT READY: %s" % state.get("reason"))
        return 4

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=False, channel="chrome", args=["--start-maximized"])
        except Exception as exc:                    # noqa: BLE001
            say("real Chrome unavailable (%s) - bundled Chromium, STILL HEADED" % exc)
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        ctx.add_init_script(COLLECT)            # read the context ring frame by frame
        page = ctx.new_page()
        page.set_default_timeout(C.NAV_TIMEOUT_MS)
        page.on("websocket", lambda ws: ws.on(
            "framesent", lambda payload: SENT_FRAMES.append(str(payload))))

        page.goto(C.BASE_URL + C.LOGIN_PATH)
        page.fill(C.SEL["login_user"], C.USERNAME)
        page.fill(C.SEL["login_pass"], C.PASSWORD)
        page.click(C.SEL["login_submit"])
        page.wait_for_load_state("networkidle")
        page.goto(C.BASE_URL + C.CHAT_PATH)
        page.wait_for_selector(C.SEL["chat_input"])
        page.bring_to_front()
        if not wait_idle(page, 240):
            say("!! the chat never became ready")
            shot(page, "00_not_ready")
            browser.close()
            return 4
        for key in ("t_multi_turn", "t_acpx", "t_ask_execs", "t_internet", "t_exec_report"):
            if page.locator(C.SEL[key]).count() and page.is_checked(C.SEL[key]):
                page.click(C.SEL[key], force=True)
                time.sleep(0.3)

        # 0. a clean conversation ----------------------------------------
        clean_offset = os.path.getsize(SERVER_LOG)
        page.click(C.SEL["clean_history"])
        page.locator(".ui-dialog-buttonpane button:has-text('Continue')").last.click()
        time.sleep(3.0)
        wait_idle(page, 240)
        check("0 Clean History: the chat starts empty", len([c for c in cards(page) if c["id"]]) == 0,
              "%d saved cards left" % len([c for c in cards(page) if c["id"]]))
        shot(page, "00_clean_start")
        # Without Ollama nothing here can be proven: the model never answers and
        # the ring never gets a REAL count. Clean History refreshes the ring, and
        # the server logs at once whether Ollama answered - stop on a NAMED
        # reason instead of timing out ten minutes later (2026-09-30).
        if ollama_unreachable(clean_offset, 30):
            say("!! ENVIRONMENT NOT READY: the server cannot reach Ollama (its log says '%s')."
                % OLLAMA_DOWN)
            say("   Start Ollama and run this test again: without it there is no answer and no REAL count.")
            browser.close()
            return 4

        # 1. three facts ---------------------------------------------------
        memory_before = memory_lines()
        run_offset = os.path.getsize(SERVER_LOG)
        u1, a1 = ask(page, M1, "colour")
        u2, a2 = ask(page, M2, "code word")
        gauge_start = len(gauge_frames(page))
        u3, a3 = ask(page, M3, "pet")
        if not all((u1, a1, u2, a2, u3, a3)):
            check("1 the three facts were answered", False, "u/a: %s" % [bool(x) for x in (u1, a1, u2, a2, u3, a3)])
            shot(page, "01_facts_failed")
            browser.close()
            return finish(1)
        every = [u1["id"], a1["id"], u2["id"], a2["id"], u3["id"], a3["id"]]
        check("1 every saved card (user AND Tlamatini) carries its id and a Drop button",
              all(c["hasDrop"] for c in cards(page)) and len(set(every)) == 6, every)
        check("1 the six rows exist in the database", db_ids(every) == set(every))
        # 1b. the ring BEFORE any drop: Ollama's REAL count for the next request
        base = check_ring("1b ring before any drop",
                          wait_rest_real(page, gauge_start, "answer finished", 240))
        shot(page, "01_three_facts")

        # 2. the dialog: text, buttons, Cancel and Escape keep the card ---
        info = open_drop_dialog(page, card_sel(u2["id"]))
        shot(page, "02_dialog_user_message")
        say("   dialog: %s | %s" % (info and info["primary"], info and info["secondary"][:300]))
        sec = (info or {}).get("secondary", "")
        check("2 dialog title is 'Drop message'", info and info["title"] == "Drop message", info and info["title"])
        check("2 dialog explains how the LLM behaves afterwards",
              "she answers as if it had never existed" in sec
              and "She will forget you ever sent this message" in sec
              and "stays exactly as it is" in sec and "No reconnection is needed" in sec, sec[:200])
        check("2 dialog asks whether she is sure", "Are you sure you want to drop it?" in sec)
        check("2 dialog is honest that a memory-tool note is separate",
              "A note she saved with her memory tool" in sec)
        labels = [b["label"] for b in (info or {}).get("buttons", [])]
        check("2 buttons are Cancel and a RED Drop", labels == ["Cancel", "Drop"]
              and info["buttons"][1]["danger"], info and info["buttons"])
        check("2 Cancel is focused, so Enter can never drop", (info or {}).get("focused") == "Cancel",
              (info or {}).get("focused"))
        page.locator(".tlmpop-foot button:has-text('Cancel')").click()
        check("2 Cancel closes the dialog and KEEPS the card",
              dialog_gone(page) and page.locator(card_sel(u2["id"])).count() == 1
              and db_ids([u2["id"]]) == {u2["id"]})
        open_drop_dialog(page, card_sel(u2["id"]))
        page.keyboard.press("Escape")
        check("2 Escape closes the dialog and KEEPS the card",
              dialog_gone(page) and page.locator(card_sel(u2["id"])).count() == 1
              and db_ids([u2["id"]]) == {u2["id"]})

        marker = page.evaluate("() => { window.__dropNoReload = 'alive-' + Date.now(); return window.__dropNoReload; }")
        connects_before = server_log_from(0).count("WebSocket connect initiated")

        # 3. DROP the user's message --------------------------------------
        open_drop_dialog(page, card_sel(u2["id"]))
        gauge_start = len(gauge_frames(page))
        page.locator(".tlmpop-btn-danger").click()
        check("3 USER message: the card disappears", card_gone(page, card_sel(u2["id"])))
        check("3 USER message: its row is gone from the database", db_ids([u2["id"]]) == set())
        first = check_ring("3b ring after dropping the USER message",
                           wait_rest_real(page, gauge_start, "message dropped", 180))
        if base and first:
            check("3b the ring was recalculated from the new history (history part changed)",
                  first.get("bytes_history") != base.get("bytes_history"),
                  "history %s B -> %s B" % (base.get("bytes_history"), first.get("bytes_history")))
        shot(page, "03_user_message_dropped")

        # 4. DROP Tlamatini's answer --------------------------------------
        info = open_drop_dialog(page, card_sel(a2["id"]))
        check("4 Tlamatini's answer gets its own wording",
              "Drop this answer from Tlamatini?" == (info or {}).get("primary")
              and "She will forget she ever wrote this answer" in (info or {}).get("secondary", ""),
              (info or {}).get("primary"))
        shot(page, "04_dialog_tlamatini_answer")
        gauge_start = len(gauge_frames(page))
        page.locator(".tlmpop-btn-danger").click()
        check("4 TLAMATINI answer: the card disappears", card_gone(page, card_sel(a2["id"])))
        check("4 TLAMATINI answer: its row is gone from the database", db_ids([a2["id"]]) == set())
        check("4 the messages BEFORE and AFTER are untouched (screen + database)",
              all(page.locator(card_sel(i)).count() == 1 for i in (u1["id"], a1["id"], u3["id"], a3["id"]))
              and db_ids([u1["id"], a1["id"], u3["id"], a3["id"]]) == {u1["id"], a1["id"], u3["id"], a3["id"]})
        drop_frames = [f for f in SENT_FRAMES if '"drop-message"' in f]
        check("4 exactly two drop-message frames went to the server", len(drop_frames) == 2, drop_frames)
        second = check_ring("4b ring after dropping Tlamatini's answer",
                            wait_rest_real(page, gauge_start, "message dropped", 180))
        if base and second:
            check("4b after both drops Ollama's REAL count is LOWER than before the first drop",
                  int(second.get("tokens_real") or 0) < int(base.get("tokens_real") or 0),
                  "%s -> %s tokens" % (base.get("tokens_real"), second.get("tokens_real")))
            check("4b after both drops the history part of the request is smaller",
                  int(second.get("bytes_history") or 0) < int(base.get("bytes_history") or 0),
                  "history %s B -> %s B" % (base.get("bytes_history"), second.get("bytes_history")))
        shot(page, "05_both_dropped")

        # 5. a live status line (never saved) -----------------------------
        status = page.locator("#chat-log .message.bot-message:not([data-message-id])")
        if status.count():
            before = status.count()
            status.last.locator(".message-drop-btn").click()
            page.wait_for_selector(".tlmpop-overlay", state="visible", timeout=8000)
            info = page.evaluate(DIALOG_JS)
            check("5 a status line says it was never in the history",
                  (info or {}).get("primary") == "Remove this status line from the chat?"
                  and "never saved in the history" in (info or {}).get("secondary", ""),
                  (info or {}).get("primary"))
            shot(page, "06_dialog_status_line")
            page.locator(".tlmpop-btn-danger").click()
            time.sleep(1.0)
            check("5 the status line leaves the screen and NO frame is sent",
                  status.count() == before - 1
                  and len([f for f in SENT_FRAMES if '"drop-message"' in f]) == 2)
        else:
            check("5 a status line was on screen to drop", False, "none found")

        # 6. what does she remember? --------------------------------------
        time.sleep(3.0)
        log_offset = os.path.getsize(SERVER_LOG)
        uq, aq = ask(page, Q, "memory question")
        answer = (aq or {}).get("text", "")
        tail = server_log_from(log_offset)
        hist = history_lines(tail)
        say("   history the model received (%d lines):" % len(hist))
        for ln in hist:
            say("      " + ln.strip()[:150])
        check("6 GROUND TRUTH: the history sent to the model has NO trace of the code word",
              hist and not any(CODE in ln for ln in hist), "%d lines" % len(hist))
        check("6 GROUND TRUTH: the message BEFORE (colour) is still in it",
              any(COLOUR in ln for ln in hist))
        check("6 GROUND TRUTH: the message AFTER (pet) is still in it",
              any(PET in ln for ln in hist))
        check("6 her answer does NOT know the code word", aq and CODE not in answer, answer[:300])
        check("6 her answer remembers the colour and the cat",
              aq and COLOUR in answer.lower() and PET.lower() in answer.lower(), answer[:300])
        shot(page, "07_memory_answer")
        ok, detail = memory_guard(memory_before, run_offset)
        check("6 no tool wrote into Angela's real memory graph (the answer came from the chat only)",
              ok, detail)

        # 7. no reconnect ---------------------------------------------------
        still = page.evaluate("() => window.__dropNoReload || ''")
        connects_after = server_log_from(0).count("WebSocket connect initiated")
        check("7 NO reconnect: same page, and the server saw no new socket",
              still == marker and connects_after == connects_before,
              "marker %s->%s, connects %d->%d" % (marker, still, connects_before, connects_after))
        log_all = server_log_from(0)
        check("7 the server logged both drops",
              ("[DROP] message id=%s" % u2["id"]) in log_all and ("[DROP] message id=%s" % a2["id"]) in log_all)

        # 8. reload: the dropped messages stay gone -----------------------
        page.reload()
        page.wait_for_selector(C.SEL["chat_input"])
        time.sleep(2.0)
        after = cards(page)
        texts = " ".join(c["text"] for c in after)
        check("8 after a reload the dropped messages do NOT come back", CODE not in texts)
        check("8 after a reload every saved card still has its Drop button",
              all(c["hasDrop"] for c in after if c["id"]) and len([c for c in after if c["id"]]) >= 6)
        shot(page, "08_after_reload")
        time.sleep(2.0)
        browser.close()
    return finish(0 if all(ok for _, ok, _ in RESULTS) else 1)


def finish(code):
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    say("=" * 78)
    say("RESULT: %d / %d checks passed  -> %s" % (passed, len(RESULTS), "ALL PASSED" if passed == len(RESULTS) else "FAILURES"))
    for name, ok, detail in RESULTS:
        if not ok:
            say("   FAILED: %s   %s" % (name, detail))
    summary = {"stamp": STAMP, "code_word": CODE, "passed": passed, "total": len(RESULTS),
               "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in RESULTS],
               "photos": [{"name": n, "path": p, "page_focused": f} for n, p, f in PHOTOS]}
    with open(os.path.join(OUT, "SUMMARY.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    rows = "".join("<tr><td>%s</td><td style='color:%s'>%s</td><td>%s</td></tr>"
                   % (n, "#2e7d32" if o else "#c62828", "PASS" if o else "FAIL",
                      re.sub(r"[<>&]", "", d)) for n, o, d in RESULTS)
    pics = "".join("<figure><figcaption>%s</figcaption><img src='%s' style='max-width:100%%'></figure>"
                   % (n, os.path.basename(p or "")) for n, p, _ in PHOTOS)
    with open(os.path.join(OUT, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write("<html><body style='font-family:sans-serif'><h1>Drop button - visible E2E %s</h1>"
                 "<h2>%d / %d passed</h2><table border=1 cellpadding=4>%s</table>%s</body></html>"
                 % (STAMP, passed, len(RESULTS), rows, pics))
    say("summary: %s" % os.path.join(OUT, "SUMMARY.html"))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                               # noqa: BLE001
        say("!! the run crashed:\n" + traceback.format_exc())
        sys.exit(finish(1))
