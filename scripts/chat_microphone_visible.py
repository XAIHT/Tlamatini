# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Visible real-template dictation checks with deterministic transport fixtures.

Run in a verified foreground PowerShell -NoExit console. Chrome is explicitly
headed. Shoter photographs all displays. Inspect browser-waiting.png and create
browser-visible-confirmed before tests; inspect the results before finish.
No production chat, microphone, account or model is used by these UI fixtures.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Temp/chat-microphone-checks"

TRANSPORT = r"""
window.__voiceHarness = {sockets: [], sent: [], spoken: []};
const h = window.__voiceHarness;
class FixtureWebSocket {
  static CONNECTING=0; static OPEN=1; static CLOSING=2; static CLOSED=3;
  constructor(url) { this.url=String(url); this.readyState=1; this.listeners={};
    h.sockets.push(this); setTimeout(()=>this.fire('open', {}),0); }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  removeEventListener(name, fn) { this.listeners[name]=(this.listeners[name]||[]).filter(f=>f!==fn); }
  fire(name, event) { this['on'+name]?.(event); (this.listeners[name]||[]).forEach(fn=>fn(event)); }
  send(text) { if(this.readyState!==1)throw Error('closed'); h.sent.push({url:this.url, data:JSON.parse(text)}); }
  close() { this.readyState=3; this.fire('close', {code:1006}); }
}
window.WebSocket=FixtureWebSocket;
h.voice=()=>h.sockets.filter(s=>s.url.endsWith('/ws/chat-voice/')).at(-1);
h.emit=(data)=>h.voice().fire('message',{data:JSON.stringify(data)});
h.prompts=()=>h.sent.filter(x=>Object.hasOwn(x.data,'multi_turn_enabled')).map(x=>x.data);
h.lastRun=()=>h.sent.filter(x=>x.data.action==='start').at(-1).data.run_id;
sessionStorage.clear(); localStorage.clear();
localStorage.setItem('tlm_voice_settings',JSON.stringify({mode:'notify'}));
window.speechSynthesis.speak=(utterance)=>h.spoken.push(utterance.text);
window.speechSynthesis.cancel=()=>{};
"""


def main():
    if any("headless" in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit("Headless execution is forbidden.")
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "Tlamatini"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
    os.environ["TLAMATINI_NO_AUDIO"] = "1"
    import django
    django.setup()
    from django.http import HttpRequest
    from django.template.loader import render_to_string
    from django.conf import settings
    from menu_browser_checks import MenuBrowserChecks
    import run_menu_state_checks as shared
    shared.OUT = OUT
    request = HttpRequest()
    request.user = SimpleNamespace(pk=1, username="Voice preview", is_authenticated=True, is_staff=False)
    request.session = {}
    html = render_to_string("agent/agent_page.html", {
        "initial_messages": [], "ollama_base_url": "http://tlamatini.test/fixture",
        "version": "development", "STATIC_VERSION": settings.STATIC_VERSION,
    }, request=request)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False,
                                             args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        context.add_init_script(TRANSPORT)
        fixture = MenuBrowserChecks()
        fixture.html, fixture.panel_html = html, ""
        fixture.errors, fixture.requests = [], []
        fixture.fail_config_save = fixture.defer_config_load = False
        fixture.pending_config_route = None
        context.route("**/*", fixture.route)
        page = context.new_page()
        page.on("pageerror", lambda error: fixture.errors.append(str(error)))
        page.set_content("<h1>Tlamatini · Microphone verification</h1><p>Visible Chrome. Waiting for desktop verification before tests.</p>")
        page.bring_to_front()
        cdp = context.new_cdp_session(page)
        window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "maximized"}})
        page.wait_for_timeout(1500)
        gate = OUT / "browser-visible-confirmed"
        gate.unlink(missing_ok=True)
        shared.shoter("browser-waiting.png")
        print("BROWSER WAITING: inspect the Shoter desktop, then create browser-visible-confirmed.", flush=True)
        while not gate.exists():
            page.wait_for_timeout(500)
        results = []

        def check(name, condition):
            if not condition:
                raise AssertionError(name)
            results.append(name)
            print("PASS:", name, flush=True)
            (OUT / "results.json").write_text(json.dumps({"passed": results, "errors": fixture.errors}, indent=2), encoding="utf-8")

        def emit(event, **kwargs):
            page.evaluate("(d)=>__voiceHarness.emit(d)", {"event": event, **kwargs})

        def start():
            page.locator("#chat-microphone").click()
            return page.evaluate("__voiceHarness.lastRun()")

        def count():
            return page.evaluate("__voiceHarness.prompts().length")

        def capture(name):
            page.wait_for_timeout(150)
            if name in {"01-ready", "02-listening", "03-silence-gate", "05-narrow", "06-final-design"}:
                check(name + ": microphone and Send fit the visible viewport", page.evaluate("""()=>
                  ["chat-microphone","chat-message-submit"].every(id=>{
                    const r=document.getElementById(id).getBoundingClientRect();
                    return r.top>=0 && r.bottom<=innerHeight && r.left>=0 && r.right<=innerWidth;
                  })"""))
            page.bring_to_front()
            shared.shoter(name + ".png")

        def chat_message(text):
            page.evaluate("(text)=>chatSocket.fire('message',{data:JSON.stringify({username:'Tlamatini',message:text})})", text)

        def reset_chat():
            page.evaluate("()=>{inLongOperation=false;lapseLoadingContext=false;restoreConnectedSocketUi();}")

        page.goto("http://tlamatini.test/agent/agent/", wait_until="load")
        page.wait_for_function("!!window.TLM_DICTATION")
        reset_chat()
        check("No microphone starts on page load", page.evaluate("__voiceHarness.sent.every(x=>x.data.action!=='start')"))
        check("Preparing is not recording", page.locator("#chat-microphone").get_attribute("data-state") == "preparing")
        emit("ready")
        check("Ready microphone is enabled", page.locator("#chat-microphone").is_enabled())
        capture("01-ready")
        page.locator("#multi-turn-enabled").check()
        page.locator("#acpx-enabled").check()
        page.locator("#exec-report-enabled").check()
        page.locator("#chat-message-input").fill("Existing draft")
        run_id = start()
        check("Click directly sends a start, not a chat prompt", count() == 0)
        check("Starting is honestly labelled", page.locator("#dictation-label").inner_text() == "Opening microphone…")
        check("Send is locked while listening", page.locator("#chat-message-submit").is_disabled())
        page.evaluate("document.getElementById('chat-form').dispatchEvent(new Event('submit'))")
        check("Submit cannot race recording", count() == 0)
        emit("recording", run_id=run_id, elapsed=2.4, level=.45, silence=0, silence_timeout=3.5)
        check("Real samples illuminate Listening", page.locator("#dictation-label").inner_text() == "Listening")
        capture("02-listening")
        emit("recording", run_id=run_id, elapsed=5, level=.005, silence=2.1, silence_timeout=3.5)
        check("Silence countdown is live", "1.4s" in page.locator("#dictation-detail").inner_text())
        capture("03-silence-gate")
        emit("transcribing", run_id=run_id, stop_reason="silence")
        check("Gate completion shows transcription", page.locator("#chat-microphone").get_attribute("data-state") == "transcribing")
        emit("result", run_id=run_id, text="Create a beautiful application.", timings={"transcription_ms": 123})
        page.wait_for_function("__voiceHarness.prompts().length===1")
        prompt = page.evaluate("__voiceHarness.prompts()[0]")
        check("Transcript automatically uses normal Send and preserves draft", prompt["message"] == "Existing draft\nCreate a beautiful application.")
        check("Current chat options survive voice handoff", all(prompt[k] for k in ("multi_turn_enabled", "acpx_enabled", "exec_report_enabled")))
        ack = "Your request is being processed by Tlamatini. Please wait a moment."
        page.wait_for_function("(text)=>__voiceHarness.spoken.filter(s=>s===text).length===1", arg=ack)
        check("Avatar acknowledges dispatch", page.evaluate("(text)=>__voiceHarness.spoken.filter(s=>s===text).length", ack) == 1)
        page.wait_for_timeout(1600)
        chat_message(ack)
        page.wait_for_timeout(250)
        check("Server acknowledgment does not speak twice", page.evaluate("(text)=>__voiceHarness.spoken.filter(s=>s===text).length", ack) == 1)
        emit("result", run_id=run_id, text="Duplicate must not run")
        check("Duplicate result never sends twice", count() == 1)
        reset_chat()

        page.locator("#chat-message-input").fill("Keep this draft")
        run_id = start()
        emit("recording", run_id=run_id, elapsed=.2, level=.3, silence=0, silence_timeout=3.5)
        page.keyboard.press("Escape")
        emit("result", run_id=run_id, text="Cancelled words must not run")
        check("Escape suppresses late transcription", count() == 1 and page.locator("#chat-message-input").input_value() == "Keep this draft")
        run_id = start()
        emit("empty", run_id=run_id, message="No speech detected. Your draft is unchanged.")
        check("Silence-only audio preserves the draft", count() == 1 and page.locator("#chat-message-input").input_value() == "Keep this draft")
        run_id = start()
        emit("error", run_id=run_id, message="Microphone unavailable. Your draft is unchanged.")
        check("Device error restores controls", page.locator("#chat-message-submit").is_enabled() and page.locator("#chat-microphone").is_enabled())
        capture("04-recoverable-error")

        run_id = start()
        page.evaluate("__voiceHarness.voice().close()")
        emit("result", run_id=run_id, text="Disconnected words must not run")
        check("Disconnected voice job cannot submit", count() == 1)
        page.locator("#chat-microphone").click()
        emit("ready")
        page.wait_for_function("document.getElementById('chat-microphone').dataset.state==='starting'")
        run_id = page.evaluate("__voiceHarness.lastRun()")
        emit("cancelled", run_id=run_id)
        check("Reconnect creates a fresh direct voice session", page.locator("#chat-microphone").is_enabled())

        run_id = start()
        emit("recording", run_id=run_id, elapsed=.2, level=.2, silence=0, silence_timeout=3.5)
        page.evaluate("chatSocket.close()")
        emit("cancelled", run_id=run_id)
        check("Chat disconnect releases the dictation edit lock", not page.locator("#chat-message-input").evaluate("(el)=>el.readOnly"))
        page.evaluate("()=>{chatSocket.readyState=1;chatSocket.fire('open',{});}")
        reset_chat()
        check("Chat reconnect restores an editable composer", page.locator("#chat-message-input").is_editable())

        original_style = page.locator("#main-chat-container").evaluate("(el)=>({width:el.style.width,flex:el.style.flex})")
        page.locator("#main-chat-container").evaluate("(el)=>{el.style.width='340px';el.style.flex='0 0 340px';}")
        page.wait_for_timeout(200)
        mic = page.locator("#chat-microphone").bounding_box()
        send = page.locator("#chat-message-submit").bounding_box()
        input_box = page.locator("#chat-message-input").bounding_box()
        check("Microphone is beside Send with no overlap at narrow width", mic["x"] + mic["width"] <= send["x"] and input_box["x"] + input_box["width"] <= mic["x"])
        check("Narrow composer keeps usable input and hit target", input_box["width"] >= 100 and mic["width"] >= 44)
        capture("05-narrow")
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("!document.getElementById('chat-microphone').disabled")
        page.keyboard.press("Tab")
        page.locator("#chat-microphone").focus()
        check("Keyboard focus is visible", page.locator("#chat-microphone").evaluate("(el)=>getComputedStyle(el).outlineStyle") != "none")
        check("Reduced motion retains a static microphone", page.locator("#chat-microphone").evaluate("(el)=>getComputedStyle(el,'::before').animationName") == "none")
        check("No browser JavaScript exceptions", fixture.errors == [])
        check("Updated static marker is served", page.locator("script[src*='chat_dictation.js']").get_attribute("src").endswith("-direct-whisperer-microphone-1"))
        page.locator("#main-chat-container").evaluate("(el,style)=>{el.style.width=style.width;el.style.flex=style.flex;}", original_style)
        page.emulate_media(reduced_motion="no-preference")
        reset_chat()
        emit("ready")
        page.locator("#chat-microphone").blur()
        page.wait_for_timeout(400)
        capture("06-final-design")
        (OUT / "results.json").write_text(json.dumps({"passed": results, "errors": fixture.errors, "exit_code": 0}, indent=2), encoding="utf-8")
        print(f"ALL {len(results)} VISIBLE UI CHECKS PASSED. Inspect results; create finish to end.", flush=True)
        finish = OUT / "finish"
        finish.unlink(missing_ok=True)
        while not finish.exists():
            page.wait_for_timeout(500)
        browser.close()


if __name__ == "__main__":
    main()
