# -*- coding: utf-8 -*-
"""
Tlamatini — VISIBLE (headed Chrome) end-to-end test of the NEW catalog prompt
"FLOWCREATOR END-TO-END WIZARD" (prompt #108, Agents & Flows).

It proves the whole story of the sample prompt, on Angela's real desktop:

  PART A (chat, Step-by-Step): log in, tick Multi-Turn + Step-by-Step, send the
    exact catalog prompt, and PLAY THE USER — reply READY step by step, and SKIP
    the opt-in live-Telegram step (no real message is ever sent). Step 1 drives
    chat_agent_flowcreator, which writes a REAL .flw to disk; we capture its path.

  PART B (canvas): open /agent/agentic_control_panel/, drive File -> Open to load
    the .flw that Step 1 just created, and screenshot the 7-node flow rendered on
    the canvas (Starter -> Monitor-Log -> Raiser -> Summarizer -> Parametrizer ->
    Telegrammer -> Ender). Then double-click the Telegrammer node to reveal the
    config dialog the wizard tells the user to fill.

Every turn is captured with a FULL-DESKTOP screenshot (taskbar clock visible).
No lying: a step that does not complete is recorded as such. Nothing destructive
runs and no Telegram is sent (the live-test gate is answered SKIP).
"""
import os
import re
import sys
import time
import json
import html
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import run_test as R        # noqa: E402
from step_by_step_catalog import send_and_wait, set_toggles, grab   # noqa: E402

from PIL import ImageGrab   # noqa: E402  (kept for parity; grab() uses it)
from playwright.sync_api import sync_playwright   # noqa: E402

RUN_TAG = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
RUN_DIR = os.path.join(HERE, "reports", "fcwizard_%s" % RUN_TAG)
SHOTS = os.path.join(RUN_DIR, "shots")
os.makedirs(SHOTS, exist_ok=True)
SUMMARY = os.path.join(RUN_DIR, "SUMMARY.html")

PROMPT_ID = int(os.environ.get("FCW_PROMPT_ID", "108"))
SRC_DB = r"C:\Development\Tlamatini\Tlamatini\db.sqlite3"
PER_TURN_TIMEOUT_S = int(os.environ.get("FCW_TIMEOUT", "300"))
MAX_TURNS = int(os.environ.get("FCW_MAX_TURNS", "12"))
CONTROL_PANEL = C.BASE_URL + "/agent/agentic_control_panel/"


# --------------------------------------------------------------- prompt text
def load_prompt_text():
    import sqlite3
    c = sqlite3.connect(SRC_DB)
    row = c.execute("select promptContent from agent_prompt where idPrompt=?", (PROMPT_ID,)).fetchone()
    c.close()
    if not row:
        raise SystemExit("prompt #%d not found in %s" % (PROMPT_ID, SRC_DB))
    return row[0]


# --------------------------------------------------------------- reply logic
def next_reply(ans):
    """What the automated 'user' sends back. SKIP the opt-in live-Telegram gate;
    otherwise advance with READY / READY N; stop when the wizard stops asking."""
    low = (ans or "").lower()
    if "testnow" in low or ("skip" in low and "live" in low) or ("skip" in low and "test" in low):
        return "SKIP", "skip-live-test"
    m = re.search(r"ready\s*(\d+)", low)
    if m:
        return "READY %s" % m.group(1), "ready-n"
    if re.search(r"reply\s+(?:exactly\s*)?['\"]?ready", low) or (
        "ready" in low and re.search(r"\b(reply|wait|when you)\b", low)
    ):
        return "READY", "ready"
    return None, "no-ask(done-or-stall)"


_FLW_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|)\]]+?\.flw", re.I)


def find_flw_path(text):
    hits = _FLW_RE.findall(text or "")
    if not hits:
        return None
    p = hits[-1].strip().rstrip(".,;)")
    return os.path.normpath(p)


def looks_final(ans):
    low = (ans or "").lower()
    return any(m in low for m in ("what we built", "wrap up", "how to stop", "re-open and tweak"))


# --------------------------------------------------------------- toggles
_JS_SET_SXS = """() => {
  const set = (sel, want) => { const el=document.querySelector(sel);
    if(!el) return 'missing'; if(el.disabled&&el.checked===want) return 'ok-disabled';
    if(el.disabled) return 'disabled'; if(el.checked!==want){el.checked=want;
    el.dispatchEvent(new Event('change',{bubbles:true}));} return String(el.checked); };
  const r={};
  r.mt=set('#multi-turn-enabled',true); r.sxs=set('#step-by-step-enabled',true);
  r.acpx=set('#acpx-enabled',false); r.exec=set('#exec-report-enabled',false);
  r.ask=set('#ask-execs-enabled',false); r.net=set('#internetEnabled',false);
  r.mt_fn=(typeof isMultiTurnEnabled==='function')?isMultiTurnEnabled():null;
  r.sxs_present=!!document.querySelector('#step-by-step-enabled');
  return r;
}"""


# --------------------------------------------------------------- canvas load
_JS_LOAD_DIAGRAM = """async (flwText) => {
  try {
    const data = JSON.parse(flwText);
    if (typeof loadDiagram !== 'function') return 'no-loadDiagram-fn';
    await loadDiagram(data);
    return 'loaded';
  } catch (e) { return 'error:' + (e && e.message); }
}"""


def canvas_item_count(page):
    try:
        return page.evaluate("() => document.querySelectorAll('.canvas-item').length")
    except Exception:
        return -1


def load_flw_on_canvas(page, flw_path):
    """Primary: drive File -> Open with a real file chooser. Fallback: call the
    page's own loadDiagram() with the .flw JSON. Returns (method, node_count)."""
    # open the File dropdown so the Open item is live
    try:
        page.click("#file-dropdown", timeout=8000)
        page.wait_for_timeout(400)
    except Exception:
        pass
    method = "file-chooser"
    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.click("#file-open-button", timeout=8000)
        fc_info.value.set_files(flw_path)
    except Exception as e:
        method = "loadDiagram-fallback (%s)" % type(e).__name__
    # wait for nodes to render (Open triggers async deploy)
    deadline = time.time() + 40
    while time.time() < deadline:
        if canvas_item_count(page) >= 7:
            return method, canvas_item_count(page)
        time.sleep(1.0)
    # fallback: inject via loadDiagram()
    try:
        with open(flw_path, "r", encoding="utf-8") as fh:
            flw_text = fh.read()
        res = page.evaluate(_JS_LOAD_DIAGRAM, flw_text)
        method = "loadDiagram(%s)" % res
        deadline = time.time() + 40
        while time.time() < deadline:
            if canvas_item_count(page) >= 7:
                break
            time.sleep(1.0)
    except Exception as e:
        method += " + inject-failed:%s" % e
    return method, canvas_item_count(page)


def open_telegrammer_dialog(page):
    """Double-click the Telegrammer node to reveal its config dialog."""
    try:
        handle = page.evaluate_handle(
            """() => Array.from(document.querySelectorAll('.canvas-item'))
                    .find(el => (el.innerText||'').toLowerCase().includes('telegrammer'))"""
        )
        el = handle.as_element()
        if not el:
            return False
        el.scroll_into_view_if_needed()
        el.dblclick()
        page.wait_for_timeout(1500)
        return True
    except Exception:
        return False


# --------------------------------------------------------------- summary
_BADGE = {"PASS": "#1e8e3e", "PARTIAL": "#b06000", "FAIL": "#c5221f"}


def build_summary(chat_turns, flw_path, canvas, started_iso, verdict, reason):
    now = _dt.datetime.now().isoformat(timespec="seconds")
    p = []
    p.append("<!doctype html><meta charset='utf-8'><title>FlowCreator End-to-End Wizard — Evidence</title>")
    p.append("<style>body{font:14px/1.5 Segoe UI,Arial,sans-serif;margin:0;background:#0f1420;color:#e8ecf3}"
             ".top{position:sticky;top:0;background:#131a2b;padding:14px 20px;border-bottom:2px solid #2a3550}"
             "h1{margin:0 0 4px;font-size:19px}.b{padding:2px 10px;border-radius:12px;color:#fff;font-weight:600}"
             ".card{background:#182135;border:1px solid #26324e;border-radius:10px;margin:16px;padding:12px 14px}"
             "img{max-width:720px;width:100%;border:1px solid #33405f;border-radius:6px;display:block;margin:6px 0}"
             ".s{color:#a7b3c9;font-size:12.5px;white-space:pre-wrap}"
             "pre{white-space:pre-wrap;background:#0c1120;padding:9px;border-radius:6px;max-height:260px;overflow:auto;color:#cdd6e6}</style>")
    color = _BADGE.get(verdict, "#666")
    p.append("<div class='top'><h1>Tlamatini — FLOWCREATOR END-TO-END WIZARD (catalog prompt #%d) · VISIBLE test</h1>" % PROMPT_ID)
    p.append("<div class='s'>login catalog_tester · Multi-Turn + Step-by-Step ON · started %s · updated %s · "
             "<span class='b' style='background:%s'>%s</span> %s</div>" %
             (html.escape(started_iso), html.escape(now), color, verdict, html.escape(reason)))
    p.append("<div class='s'>.flw created: <b>%s</b></div></div>" % html.escape(str(flw_path)))
    # canvas card first (the headline proof)
    if canvas:
        p.append("<div class='card'><b>PART B — the created .flw opened on the Agentic Control Panel canvas</b>")
        p.append("<div class='s'>load method: %s · nodes on canvas: %s</div>" %
                 (html.escape(str(canvas.get('method'))), canvas.get('nodes')))
        for shot in canvas.get("shots", []):
            p.append("<a href='shots/%s' target='_blank'><img src='shots/%s'></a>" % (shot, shot))
        p.append("</div>")
    # chat turns
    p.append("<div class='card'><b>PART A — the Step-by-Step wizard in chat (I played the user)</b>")
    for t in chat_turns:
        p.append("<div class='s'>turn %d · sent: %s · %.1fs · reply&rarr; %s (%s) · completed=%s</div>" %
                 (t["i"], html.escape(t["sent"]), t["elapsed_s"], html.escape(str(t["next_reply"])),
                  t["why"], t["completed"]))
        p.append("<a href='shots/%s' target='_blank'><img src='shots/%s'></a>" % (t["shot"], t["shot"]))
        p.append("<details><summary>answer (%d chars)</summary><pre>%s</pre></details>" %
                 (len(t["answer"] or ""), html.escape((t["answer"] or "")[:6000])))
    p.append("</div>")
    tmp = SUMMARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("".join(p))
    os.replace(tmp, SUMMARY)


# --------------------------------------------------------------- args shim
class Args:
    headless = False
    slowmo = 0
    user = os.environ.get("TLAMATINI_USER", "catalog_tester")
    password = os.environ.get("TLAMATINI_PASS", "CatalogTest!2026")
    judge_model = None
    not_ready_retries = 4
    not_ready_backoff = 10.0
    timeout = PER_TURN_TIMEOUT_S


def main():
    started_iso = _dt.datetime.now().isoformat(timespec="seconds")
    print("=" * 72)
    print("FLOWCREATOR END-TO-END WIZARD TEST · visible Chrome · prompt #%d" % PROMPT_ID)
    print("run dir:", RUN_DIR)
    print("=" * 72, flush=True)

    opener = load_prompt_text()
    args = Args()
    h = R.Harness(args)
    chat_turns = []
    flw_path = None
    canvas = None
    verdict, reason = "FAIL", "did not start"

    with sync_playwright() as pw:
        browser = h.launch(pw)
        try:
            h.login()
            h.goto_chat()
            try:
                h.page.wait_for_load_state("load", timeout=30000)
            except Exception:
                pass
            time.sleep(0.8)
            page = h.page

            # fresh conversation + toggles
            try:
                h.clear_history()
            except Exception:
                pass
            time.sleep(2.0)
            tg = page.evaluate(_JS_SET_SXS)
            print("  toggles:", tg, flush=True)

            # -------- PART A: run the wizard, playing the user --------
            msg = opener
            last = None
            for ti in range(MAX_TURNS):
                page.evaluate(_JS_SET_SXS)  # re-pin every turn
                try:
                    page.wait_for_function(R._JS_EDITABLE, timeout=180000)
                except Exception:
                    pass
                r = send_and_wait(page, msg, PER_TURN_TIMEOUT_S)
                shot = "fcw_A_t%02d.png" % ti
                try:
                    grab(page, os.path.join(SHOTS, shot))
                except Exception as e:
                    print("   screenshot failed:", e, flush=True)
                ans = r["answer"]
                if flw_path is None:
                    fp = find_flw_path(ans)
                    if fp:
                        flw_path = fp
                        print("   captured flw_path:", flw_path, flush=True)
                tok, why = next_reply(ans)
                sent = msg if ti else "[CATALOG PROMPT #%d]" % PROMPT_ID
                chat_turns.append({"i": ti, "sent": sent[:180], "answer": ans,
                                   "completed": r["completed"], "elapsed_s": r["elapsed_s"],
                                   "next_reply": tok, "why": why, "shot": shot})
                print("   A turn %02d  %5.1fs chars=%-5d reply=%-9s (%s) completed=%s"
                      % (ti, r["elapsed_s"], len(ans or ""), tok or "-", why, r["completed"]), flush=True)
                build_summary(chat_turns, flw_path, canvas, started_iso, "PARTIAL", "chat in progress")
                if not r["completed"] and not ans:
                    break
                if ans and ans == last and tok:
                    print("   repeated answer -> stopping", flush=True)
                    break
                last = ans
                if tok is None:
                    break
                msg = tok

            # -------- PART B: load the .flw on the Control Panel canvas --------
            if flw_path and os.path.exists(flw_path):
                print("  opening Control Panel and loading:", flw_path, flush=True)
                canvas = {"shots": [], "method": None, "nodes": 0}
                try:
                    page.goto(CONTROL_PANEL, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    method, nodes = load_flw_on_canvas(page, flw_path)
                    canvas["method"] = method
                    canvas["nodes"] = nodes
                    page.wait_for_timeout(1200)
                    s1 = "fcw_B_canvas.png"
                    grab(page, os.path.join(SHOTS, s1))
                    canvas["shots"].append(s1)
                    print("   canvas loaded via %s, nodes=%s" % (method, nodes), flush=True)
                    # reveal the Telegrammer config dialog
                    if open_telegrammer_dialog(page):
                        s2 = "fcw_B_telegrammer_dialog.png"
                        grab(page, os.path.join(SHOTS, s2))
                        canvas["shots"].append(s2)
                        print("   opened Telegrammer dialog", flush=True)
                except Exception as e:
                    print("   canvas load error:", e, flush=True)
                    if canvas.get("method") is None:
                        canvas["method"] = "error:%s" % e
            else:
                print("  NO .flw path captured (or file missing) — canvas part skipped", flush=True)

            # -------- verdict --------
            created = bool(flw_path and os.path.exists(flw_path))
            walked = len(chat_turns) >= 3 and any(t["completed"] for t in chat_turns)
            opened = bool(canvas and canvas.get("nodes", 0) >= 7)
            if created and opened and walked:
                verdict, reason = "PASS", "flow created, wizard walked step-by-step, .flw opened on the canvas (%d nodes)" % canvas["nodes"]
            elif created and walked:
                verdict, reason = "PARTIAL", "flow created + wizard walked; canvas load = %s" % (canvas and canvas.get("method"))
            elif created:
                verdict, reason = "PARTIAL", "flow created but wizard walk was short"
            else:
                verdict, reason = "FAIL", "FlowCreator did not produce a .flw"
        finally:
            build_summary(chat_turns, flw_path, canvas, started_iso, verdict, reason)
            try:
                browser.close()
            except Exception:
                pass

    print("\n" + "=" * 72)
    print("VERDICT:", verdict, "-", reason)
    print(".flw:", flw_path)
    print("SUMMARY:", SUMMARY)
    print("=" * 72, flush=True)
    return 0 if verdict in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
