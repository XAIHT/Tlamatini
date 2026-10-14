# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
r"""
FILE DROP ROUTER - VISIBLE END-TO-END TEST (Angela, 2026-10-14)
===============================================================

"make Tlamatini very smart to detect and proceed accordingly to different
mechanisms completely different when distinct types of files will be dropped in
the entire areas of every one of her pages".

HEADED real Chrome, the real GUI of the SOURCE server on :8001 (never the
installed Tlamatini on :8000). Real File objects (JSON, UTF-16 JSON, image,
PDF, .flw, .fpmt, zip, exe) are dropped through the browser's real drag events
onto EVERY area of every page; every step is photographed by Shoter (whole
desktop). Every MCP server this run adds is removed again at the end.

  CHAT        overlay tells the truth - MCP json on the INPUT, the HISTORY, the
              CANVAS and INSIDE the PDF viewer iframe is imported (and is never
              opened as text); plain JSON / code / Markdown open in the canvas;
              a PNG is attached; an archive and an exe are explained; a .fpmt
              and a .flw open their own editor tab.
  AGENTIC     MCP json on canvas / sidebar / page body imports (page never
  CONTROL     navigates away); a .flw loads into the canvas; a .fpmt opens its
  PANEL       tab; dragging an agent from the sidebar still works.
  PROMPT FLOW .fpmt loads in place; .flw opens its tab; MCP json imports;
  PANEL       dragging an operation from the palette still works.
  WELCOME     MCP json imports; Enter still goes to the chat.
  LOGIN       a dropped file never navigates away and asks to sign in.
  ADMIN       a dropped MCP json is caught (never navigates away).

Exit codes: 0 all passed, 1 a check failed, 4 the environment could not be
established (named reason, no traceback).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import traceback

os.environ.setdefault("TLAMATINI_BASE_URL", "http://127.0.0.1:8001")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C                                # noqa: E402
from preflight import ensure_ready, stop_server   # noqa: E402
from shoter_shot import take_shot                 # noqa: E402

from playwright.sync_api import sync_playwright   # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
STAMP = time.strftime("%Y%m%d_%H%M%S")
OUT = os.path.join(REPO, "Temp", "file_drop", "visible_run_" + STAMP)
RUN_LOG = os.path.join(REPO, "Temp", "file_drop", "e2e_%s.log" % STAMP)
os.makedirs(OUT, exist_ok=True)

RESULTS = []
PHOTOS = []
KEYS = {n: "zz_filedrop_%s_%s" % (STAMP, n) for n in "abcdefg"}


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
    """Photograph the WHOLE desktop with Shoter - the page in front first."""
    try:
        page.bring_to_front()
        time.sleep(0.6)
    except Exception:                                # noqa: BLE001
        pass
    path = take_shot(OUT, "%s.png" % name)
    PHOTOS.append((name, path))
    say("   PHOTO %s -> %s" % (name, path))
    return path


# ───────────────────────────────────────────────────────────── the fixtures
def mcp_json(key):
    return json.dumps({"mcpServers": {key: {"command": "cmd", "args": ["/c", "echo", "tlamatini-file-drop-test"]}}},
                      indent=2)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
PDF_MIN = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
           b"trailer<</Root 1 0 R/Size 4>>\n%%EOF\n")
KICKOFF = os.path.join(REPO, "docs", "examples", "prompting-kickoff.fpmt")

FILES = {  # name -> (file name, mime type, bytes)
    "mcp_a": ("claude_desktop_config.json", "application/json", mcp_json(KEYS["a"]).encode("utf-8")),
    "mcp_b_utf16": ("mcp_powershell.json", "application/json",
                    b"\xff\xfe" + mcp_json(KEYS["b"]).encode("utf-16-le")),
    "mcp_c": ("mcp_for_canvas.json", "application/json", mcp_json(KEYS["c"]).encode("utf-8")),
    "mcp_d": ("mcp_for_pdf_frame.json", "application/json", mcp_json(KEYS["d"]).encode("utf-8")),
    "mcp_e": ("mcp_for_acp.json", "application/json", mcp_json(KEYS["e"]).encode("utf-8")),
    "mcp_f": ("mcp_for_prompt_panel.json", "application/json", mcp_json(KEYS["f"]).encode("utf-8")),
    "mcp_g": ("mcp_for_welcome.json", "application/json", mcp_json(KEYS["g"]).encode("utf-8")),
    "package": ("package.json", "application/json", b'{"name": "demo", "version": "1.0.0"}'),
    "code": ("hello.py", "text/x-python", b"print('hello from a dropped file')\n"),
    "markdown": ("notes.md", "", b"# Dropped notes\n\nThis Markdown file was dropped on the canvas.\n"),
    "png": ("screenshot.png", "image/png", PNG_1X1),
    "pdf": ("sample.pdf", "application/pdf", PDF_MIN),
    "flw": ("empty_flow.flw", "", b'{"nodes": [], "connections": []}'),
    "fpmt": ("prompting-kickoff.fpmt", "", open(KICKOFF, "rb").read() if os.path.exists(KICKOFF) else b"{}"),
    "zip": ("archive.zip", "application/zip", b"PK\x03\x04" + b"\x00" * 60),
    "exe": ("tool.exe", "", b"MZ" + b"\x00" * 126),
}

# ─────────────────────────────────────────────────────────── page-side helpers
DROP_JS = """({ sel, files, frame, hold }) => {
    const hostDoc = frame ? document.querySelector(frame).contentDocument : document;
    const win = hostDoc.defaultView;
    const target = sel ? hostDoc.querySelector(sel) : hostDoc.body;
    if (!target) return { error: 'no target ' + sel };
    const dt = new win.DataTransfer();
    for (const f of files) {
        const bin = atob(f.b64);
        const bytes = new win.Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
        dt.items.add(new win.File([bytes], f.name, { type: f.type || '' }));
    }
    const rect = target.getBoundingClientRect();
    const init = { bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
        clientX: Math.round(rect.left + rect.width / 2), clientY: Math.round(rect.top + rect.height / 2) };
    const fire = (type) => target.dispatchEvent(new win.DragEvent(type, init));
    fire('dragenter');
    const overClaimed = !fire('dragover');
    const overlay = hostDoc.getElementById('tlm-file-drop-overlay');
    const shown = !!(overlay && overlay.classList.contains('show'));
    const text = overlay ? overlay.innerText : '';
    if (hold) return { overClaimed, shown, text };
    const dropClaimed = !fire('drop');
    return { overClaimed, dropClaimed, shown, text };
}"""

POPUP_JS = """() => { const o = document.querySelector('.tlmpop-overlay');
  if (!o || o.style.display === 'none') return null;
  const t = s => { const n = o.querySelector(s); return n ? n.textContent : ''; };
  return { title: t('.tlmpop-title'), primary: t('.tlmpop-msg'), secondary: t('.tlmpop-sub'),
           buttons: Array.from(o.querySelectorAll('.tlmpop-foot button')).map(b => b.textContent.trim()) }; }"""

TOAST_JS = """() => { const t = document.getElementById('tlm-file-drop-toast');
  return t && t.classList.contains('show') ? t.textContent : ''; }"""

CATALOG_JS = """async () => { const r = await fetch('/agent/external_mcps/', { credentials: 'same-origin' });
  const d = await r.json(); return (d.servers || []).map(s => s.key); }"""

REMOVE_JS = """async (keys) => { const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  const r = await fetch('/agent/external_mcps/remove/', { method: 'POST', credentials: 'same-origin',
    headers: { 'X-CSRFToken': m ? decodeURIComponent(m[1]) : '', 'Content-Type': 'application/json' },
    body: JSON.stringify({ keys }) });
  return r.ok; }"""


def drop(page, selector, names, frame=None, hold=False):
    files = [dict(name=FILES[n][0], type=FILES[n][1], b64=base64.b64encode(FILES[n][2]).decode("ascii"))
             for n in names]
    result = page.evaluate(DROP_JS, dict(sel=selector, files=files, frame=frame, hold=hold))
    if result and result.get("error"):
        say("   (drop helper) " + result["error"])
    return result or {}


def popup(page, timeout=15000):
    try:
        page.wait_for_function("() => { const o = document.querySelector('.tlmpop-overlay');"
                               " return !!o && o.style.display !== 'none'; }", timeout=timeout)
    except Exception:                                # noqa: BLE001
        return None
    return page.evaluate(POPUP_JS)


def click_popup(page, label):
    page.locator(".tlmpop-foot button", has_text=label).first.click()
    try:
        page.wait_for_function("() => !document.querySelector('.tlmpop-overlay')", timeout=8000)
    except Exception:                                # noqa: BLE001
        pass


def popup_titled(page, title, timeout=15000):
    try:
        page.wait_for_function("(t) => { const n = document.querySelector('.tlmpop-title');"
                               " return !!n && n.textContent.indexOf(t) !== -1; }", arg=title, timeout=timeout)
    except Exception:                                # noqa: BLE001
        return None
    return page.evaluate(POPUP_JS)


def toast(page, needle, timeout=8000):
    try:
        page.wait_for_function("(n) => { const t = document.getElementById('tlm-file-drop-toast');"
                               " return !!t && t.classList.contains('show') && t.textContent.indexOf(n) !== -1; }",
                               arg=needle, timeout=timeout)
    except Exception:                                # noqa: BLE001
        pass
    return page.evaluate(TOAST_JS)


def catalog(page):
    return page.evaluate(CATALOG_JS)


def scenario(title):
    def wrap(fn):
        def run(*args, **kwargs):
            say("")
            say("== " + title)
            try:
                return fn(*args, **kwargs)
            except Exception as exc:                 # noqa: BLE001
                check(title + " (ran to completion)", False, "%s: %s" % (type(exc).__name__, exc))
                say(traceback.format_exc())
        return run
    return wrap


def login(page):
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.fill(C.SEL["login_user"], C.USERNAME)
    page.fill(C.SEL["login_pass"], C.PASSWORD)
    page.click(C.SEL["login_submit"])
    page.wait_for_load_state("domcontentloaded")


def open_chat(page):
    page.goto(C.BASE_URL + C.CHAT_PATH)
    page.wait_for_selector("#chat-message-input", timeout=30000)
    page.wait_for_function("() => !!window.TlamatiniFileDrop", timeout=15000)
    time.sleep(1.5)


# ──────────────────────────────────────────────────────────────── scenarios
@scenario("CHAT 1-2: MCP .json dropped on the message INPUT")
def chat_input_import(page):
    held = drop(page, "#chat-message-input", ["mcp_a"], hold=True)
    check("the drag is claimed (the browser can never navigate to the file)", held.get("overClaimed"), held)
    check("the overlay is shown and announces the MCP import", held.get("shown") and "MCP server config" in held.get("text", ""), held.get("text"))
    check("the overlay also announces what other JSON does here", "Any other JSON" in held.get("text", ""), held.get("text"))
    shot(page, "01_chat_overlay_over_input")
    done = drop(page, "#chat-message-input", ["mcp_a"])
    check("the drop is claimed", done.get("dropClaimed"), done)
    info = popup(page)
    check("a themed confirm asks before importing", bool(info) and info["title"] == "Import MCP servers", info)
    check("it names the server and warns that it can launch programs",
          bool(info) and KEYS["a"] in info["secondary"] and "launch programs" in info["secondary"], info)
    check("the input did NOT receive an error chip about images", "Only image" not in page.inner_text("#chat-image-chips"))
    shot(page, "02_chat_import_confirm")
    click_popup(page, "Continue")
    done = popup_titled(page, "Import complete")
    check("the result is reported, with an offer to activate", bool(done) and any("Open External" in b for b in done["buttons"]), done)
    shot(page, "03_chat_import_complete")
    click_popup(page, "Open External")
    try:
        page.wait_for_selector('.emx-row[data-key="%s"]' % KEYS["a"], timeout=15000)
        check("External > MCPs opens and lists the imported server", True)
    except Exception as exc:                         # noqa: BLE001
        check("External > MCPs opens and lists the imported server", False, exc)
    shot(page, "04_chat_external_mcps_lists_it")
    page.keyboard.press("Escape")
    time.sleep(0.5)
    check("the server is in the catalog", KEYS["a"] in catalog(page))


@scenario("CHAT 3: UTF-16 MCP .json (Windows PowerShell Out-File) dropped on the HISTORY")
def chat_history_utf16(page):
    drop(page, "#chat-log", ["mcp_b_utf16"])
    info = popup(page)
    check("a UTF-16 file is recognised by its content", bool(info) and KEYS["b"] in info["secondary"], info)
    shot(page, "05_chat_history_utf16_confirm")
    click_popup(page, "Continue")
    popup_titled(page, "Import complete")
    click_popup(page, "Later")
    check("it landed in the catalog", KEYS["b"] in catalog(page))


@scenario("CHAT 4: MCP .json dropped on the CANVAS is NOT opened as text")
def chat_canvas_mcp(page):
    before = page.inner_text("#filename")
    drop(page, "#canvas-container", ["mcp_c"])
    info = popup(page)
    check("the canvas drop becomes an import confirm (not a document)", bool(info) and KEYS["c"] in info["secondary"], info)
    shot(page, "06_chat_canvas_mcp_confirm")
    click_popup(page, "Cancel")
    check("the canvas still shows its old title", page.inner_text("#filename") == before, page.inner_text("#filename"))
    check("the .json was not put into the editor", "mcpServers" not in page.inner_text("#text-editor"))
    check("Cancel imported nothing", KEYS["c"] not in catalog(page))


@scenario("CHAT 5-6: plain JSON, code and Markdown still open in the canvas")
def chat_canvas_documents(page):
    drop(page, "#canvas-container", ["package"])
    page.wait_for_function("() => document.getElementById('filename').textContent.indexOf('package.json') !== -1", timeout=10000)
    check("plain JSON (not an MCP config) opens in the canvas", "demo" in page.inner_text("#text-editor"))
    shot(page, "07_chat_canvas_plain_json")
    drop(page, "#chat-log", ["code"])
    page.wait_for_function("() => document.getElementById('filename').textContent.indexOf('hello.py') !== -1", timeout=10000)
    check("a code file dropped on the HISTORY opens in the canvas", "hello from a dropped file" in page.inner_text("#text-editor"))
    drop(page, "#chat-message-input", ["markdown"])
    page.wait_for_function("() => document.getElementById('filename').textContent.indexOf('notes.md') !== -1", timeout=10000)
    shot(page, "08_chat_canvas_markdown")
    check("Markdown dropped on the INPUT opens as a page", "Dropped notes" in page.inner_text("#canvas-container"))


@scenario("CHAT 7: an image dropped on the message input is attached")
def chat_image(page):
    drop(page, "#chat-message-input", ["png"])
    try:
        page.wait_for_selector("#chat-image-chips .chat-img-chip-thumb", timeout=15000)
        ok = True
    except Exception:                                # noqa: BLE001
        ok = False
    value = page.input_value("#chat-message-input")
    check("a thumbnail chip appears", ok)
    check("its saved path is spliced into the message", bool(re.search(r"image_\d{8}_\d{6}_\d+\.jpg", value)), value)
    check("no 'only images' error was shown", "Only image" not in page.inner_text("#chat-image-chips"))
    shot(page, "09_chat_image_attached")


@scenario("CHAT 8: a PDF opens, and an MCP .json dropped INSIDE the PDF viewer reaches the page")
def chat_pdf_and_frame(page):
    drop(page, "#canvas-container", ["pdf"])
    page.wait_for_selector("#pdf-canvas-host:not([hidden]) iframe", timeout=20000)
    page.wait_for_function("() => { const f = document.querySelector('#pdf-canvas-host iframe');"
                           " return !!(f && f.contentWindow && f.contentWindow.TlamatiniFileDrop); }", timeout=20000)
    check("the PDF viewer frame carries its own router", True)
    shot(page, "10_chat_pdf_open")
    drop(page, "body", ["mcp_d"], frame="#pdf-canvas-host iframe")
    info = popup(page)
    check("a drop INSIDE the iframe is relayed to the page and confirmed there",
          bool(info) and KEYS["d"] in info["secondary"], info)
    shot(page, "11_chat_pdf_frame_drop_relayed")
    click_popup(page, "Cancel")
    check("Cancel imported nothing", KEYS["d"] not in catalog(page))


@scenario("CHAT 9: an archive and an exe are explained, never opened as garbage")
def chat_unsupported(page):
    url = page.url
    result = drop(page, "#chat-log", ["zip", "exe"])
    text = toast(page, "Skipped")
    check("the drop is claimed", result.get("dropClaimed"), result)
    check("the toast names both files and their kinds", "archive.zip (archive)" in text and "tool.exe (binary file)" in text, text)
    check("it says what this page does accept", "This page accepts" in text, text)
    check("the page did not navigate", page.url == url)
    shot(page, "12_chat_unsupported_explained")


@scenario("CHAT 10-11: a .fpmt and a .flw each open their own editor tab")
def chat_flow_tabs(page, ctx):
    with ctx.expect_page(timeout=20000) as opened:
        drop(page, "#chat-message-input", ["fpmt"])
    tab = opened.value
    tab.wait_for_load_state("domcontentloaded", timeout=20000)
    try:
        tab.wait_for_url(re.compile(r"prompt_flow_panel"), timeout=20000)
    except Exception:                                # noqa: BLE001
        pass
    check("a .fpmt opens the Prompt Flow Panel in a new tab", "prompt_flow_panel" in tab.url, tab.url)
    shot(tab, "13_chat_fpmt_new_tab")
    tab.close()
    with ctx.expect_page(timeout=20000) as opened:
        drop(page, "#chat-log", ["flw"])
    tab = opened.value
    tab.wait_for_load_state("domcontentloaded", timeout=20000)
    try:
        tab.wait_for_url(re.compile(r"agentic_control_panel"), timeout=20000)
    except Exception:                                # noqa: BLE001
        pass
    check("a .flw opens the Agentic Control Panel in a new tab", "agentic_control_panel" in tab.url, tab.url)
    shot(tab, "14_chat_flw_new_tab")
    tab.close()
    page.bring_to_front()


@scenario("AGENTIC CONTROL PANEL: every area")
def acp_page(page, ctx):
    page.goto(C.BASE_URL + "/agent/agentic_control_panel/")
    page.wait_for_selector("#submonitor-container", timeout=30000)
    page.wait_for_function("() => !!window.TlamatiniFileDrop && document.querySelectorAll('#agents-list .agent-tool-item').length > 0", timeout=30000)
    time.sleep(1.0)
    page.evaluate("window.__still_here = 1")
    url = page.url
    for index, selector in enumerate(("#submonitor-container", "#agents-list", "body")):
        result = drop(page, selector, ["mcp_e"])
        info = popup(page)
        check("MCP .json on %s is claimed and confirmed" % selector,
              bool(result.get("dropClaimed")) and bool(info) and KEYS["e"] in info["secondary"], info)
        if index == 0:
            shot(page, "15_acp_canvas_mcp_confirm")
        click_popup(page, "Cancel")
        check("the page did not navigate away (%s)" % selector, page.url == url and page.evaluate("window.__still_here") == 1)
    check("Cancel imported nothing", KEYS["e"] not in catalog(page))
    with page.expect_response(lambda r: "flow_files/validate" in r.url, timeout=20000) as seen:
        drop(page, "#submonitor-container", ["flw"])
    check("a .flw dropped on the canvas goes through the diagram loader", seen.value.ok, seen.value.status)
    time.sleep(1.0)
    shot(page, "16_acp_flw_loaded")
    with ctx.expect_page(timeout=20000) as opened:
        drop(page, "#agents-list", ["fpmt"])
    tab = opened.value
    try:
        tab.wait_for_url(re.compile(r"prompt_flow_panel"), timeout=20000)
    except Exception:                                # noqa: BLE001
        pass
    check("a .fpmt dropped on the sidebar opens the Prompt Flow Panel tab", "prompt_flow_panel" in tab.url, tab.url)
    tab.close()
    page.bring_to_front()
    before = page.locator(".canvas-item").count()
    page.drag_and_drop("#agents-list .agent-tool-item >> nth=0", "#submonitor-container",
                       target_position={"x": 420, "y": 260})
    time.sleep(1.0)
    after = page.locator(".canvas-item").count()
    check("dragging an agent from the sidebar to the canvas STILL works", after == before + 1, "%d -> %d" % (before, after))
    shot(page, "17_acp_agent_drag_still_works")


@scenario("PROMPT FLOW PANEL: every area")
def prompt_panel(page, ctx):
    page.goto(C.BASE_URL + "/agent/prompt_flow_panel/")
    page.wait_for_selector("#submonitor-container", timeout=30000)
    page.wait_for_function("() => !!window.TlamatiniFileDrop && !!window.PromptFlowPanelModel", timeout=30000)
    time.sleep(1.0)
    url = page.url
    # An earlier tab in this run saved a draft in this browser's storage and the panel restores it on
    # open: clear it so the page starts empty and the drop below is the ONLY thing that can fill it.
    page.evaluate("() => Object.keys(localStorage).filter(k => k.indexOf('tlamatini.prompting-flow.') === 0)"
                  ".forEach(k => localStorage.removeItem(k))")
    page.reload()
    page.wait_for_function("() => !!window.TlamatiniFileDrop && !!window.PromptFlowPanelModel", timeout=30000)
    time.sleep(1.0)
    check("a fresh panel starts empty", page.locator(".pmt-node").count() == 0, page.locator(".pmt-node").count())
    drop(page, "#submonitor-container", ["fpmt"])
    try:
        page.wait_for_function("() => document.querySelectorAll('.pmt-node').length > 0", timeout=15000)
        ok = True
    except Exception:                                # noqa: BLE001
        ok = False
    check("a .fpmt dropped on the canvas loads as the diagram",
          ok and page.locator(".pmt-node").count() == 8 and "prompting-kickoff.fpmt" in page.inner_text("body"),
          page.locator(".pmt-node").count())
    shot(page, "18_prompt_fpmt_loaded")
    # Unsaved work on the canvas: the same .fpmt must now ASK before replacing it (the page's own consent).
    page.drag_and_drop(".agent-tool-item[data-type] >> nth=0", "#submonitor-container", target_position={"x": 560, "y": 560})
    time.sleep(0.8)
    dirty_count = page.locator(".pmt-node").count()
    drop(page, "#submonitor-container", ["fpmt"])
    info = popup(page)
    check("with unsaved work on the canvas the .fpmt asks before replacing it",
          bool(info) and "Replace the current diagram" in info["primary"], info)
    shot(page, "18b_prompt_replace_confirm")
    click_popup(page, "Cancel")
    check("Cancel keeps the unsaved diagram", page.locator(".pmt-node").count() == dirty_count, page.locator(".pmt-node").count())
    with ctx.expect_page(timeout=20000) as opened:
        drop(page, "#submonitor-container", ["flw"])
    tab = opened.value
    try:
        tab.wait_for_url(re.compile(r"agentic_control_panel"), timeout=20000)
    except Exception:                                # noqa: BLE001
        pass
    check("a .flw dropped here opens the Agentic Control Panel tab", "agentic_control_panel" in tab.url, tab.url)
    tab.close()
    page.bring_to_front()
    drop(page, "body", ["mcp_f"])
    info = popup(page)
    check("an MCP .json is confirmed here too", bool(info) and KEYS["f"] in info["secondary"], info)
    shot(page, "19_prompt_mcp_confirm")
    click_popup(page, "Cancel")
    check("the page did not navigate away", page.url == url)
    before = page.locator(".pmt-node").count()
    page.drag_and_drop(".agent-tool-item[data-type] >> nth=0", "#submonitor-container", target_position={"x": 500, "y": 420})
    time.sleep(1.0)
    after = page.locator(".pmt-node").count()
    check("dragging an operation from the palette STILL works", after == before + 1, "%d -> %d" % (before, after))
    shot(page, "20_prompt_palette_drag_still_works")


@scenario("WELCOME PAGE")
def welcome_page(page):
    page.goto(C.BASE_URL + "/agent/welcome/")
    page.wait_for_selector("#go-to-chat", timeout=20000)
    page.wait_for_function("() => !!window.TlamatiniFileDrop", timeout=15000)
    url = page.url
    drop(page, "body", ["mcp_g"])
    info = popup(page)
    check("an MCP .json dropped on the welcome page is confirmed (themed)", bool(info) and KEYS["g"] in info["secondary"], info)
    shot(page, "21_welcome_mcp_confirm")
    click_popup(page, "Cancel")
    check("the page did not navigate away", page.url == url)
    page.goto(C.BASE_URL + "/agent/welcome/")
    page.wait_for_selector("#go-to-chat", timeout=20000)
    time.sleep(0.8)
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"/agent/agent/"), timeout=20000)
    check("Enter still takes you straight to the chat", "/agent/agent/" in page.url, page.url)


@scenario("LOGIN PAGE (signed out)")
def login_page(browser):
    ctx = browser.new_context(no_viewport=True)
    page = ctx.new_page()
    page.goto(C.BASE_URL + C.LOGIN_PATH)
    page.wait_for_selector(C.SEL["login_user"], timeout=20000)
    page.wait_for_function("() => !!window.TlamatiniFileDrop", timeout=15000)
    url = page.url
    result = drop(page, "body", ["mcp_a"])
    text = toast(page, "Sign in first")
    check("the drop is claimed", result.get("dropClaimed"), result)
    check("the page asks the user to sign in", "Sign in first" in text, text)
    check("the page did not navigate away", page.url == url)
    shot(page, "22_login_sign_in_first")
    ctx.close()


@scenario("DJANGO ADMIN")
def admin_page(page):
    page.goto(C.BASE_URL + "/admin/")
    page.wait_for_function("() => !!window.TlamatiniFileDrop", timeout=20000)
    url = page.url
    seen = []
    page.once("dialog", lambda d: (seen.append(d.message), d.dismiss()))
    drop(page, "body", ["mcp_a"])
    page.wait_for_timeout(2500)  # NOT time.sleep: only Playwright calls pump the dialog event
    check("an MCP .json dropped on the admin is caught and confirmed", bool(seen) and "MCP server" in seen[0], seen)
    check("the page did not navigate away", page.url == url)
    shot(page, "23_admin_drop_caught")


def main():
    say("FILE DROP ROUTER visible test - base %s - photos in %s" % (C.BASE_URL, OUT))
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
        except Exception:                            # noqa: BLE001
            browser = pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.on("pageerror", lambda e: say("   [pageerror] %s" % e))
        try:
            login(page)
            open_chat(page)
            chat_input_import(page)
            chat_history_utf16(page)
            chat_canvas_mcp(page)
            chat_canvas_documents(page)
            chat_image(page)
            chat_pdf_and_frame(page)
            chat_unsupported(page)
            chat_flow_tabs(page, ctx)
            acp_page(page, ctx)
            prompt_panel(page, ctx)
            welcome_page(page)
            admin_page(page)
            login_page(browser)
        finally:
            try:
                page.goto(C.BASE_URL + C.CHAT_PATH)
                page.wait_for_selector("#chat-message-input", timeout=20000)
                page.evaluate(REMOVE_JS, list(KEYS.values()))
                left = [k for k in catalog(page) if k in KEYS.values()]
                check("cleanup: every test MCP server was removed from the catalog", not left, left)
            except Exception as exc:                 # noqa: BLE001
                check("cleanup: every test MCP server was removed from the catalog", False, exc)
            time.sleep(1.0)
            browser.close()
    failed = [r for r in RESULTS if not r[1]]
    say("")
    say("SUMMARY: %d checks, %d passed, %d FAILED, %d photos" % (len(RESULTS), len(RESULTS) - len(failed), len(failed), len(PHOTOS)))
    for name, ok, detail in failed:
        say("   FAILED: %s   -> %s" % (name, detail))
    with open(os.path.join(OUT, "RESULT.json"), "w", encoding="utf-8") as fh:
        json.dump({"results": RESULTS, "photos": PHOTOS}, fh, indent=2)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:                         # noqa: BLE001
        say("ENVIRONMENT ERROR: %s: %s" % (type(exc).__name__, exc))
        say(traceback.format_exc())
        code = 4
    say("EXIT %d" % code)
    sys.exit(code)
