# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Visible component integration checks using the real dialog, poller and styles.

Launch in a verified foreground PowerShell -NoExit console. No application data,
model service, or Git command is used. Headless execution is refused.
"""
import ctypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import panel_search_title_visible as visible

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/strict-vision-visible/browser'
ASSETS = '/Tlamatini/agent/static/agent/'
EVENTS = []
RESULTS = []


def require_visible(title):
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user.IsIconic.argtypes = [ctypes.c_void_p]
    user.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    handle = user.GetForegroundWindow()
    text = ctypes.create_unicode_buffer(2048)
    user.GetWindowTextW(handle, text, len(text))
    if not user.IsWindowVisible(handle) or user.IsIconic(handle) or title not in text.value:
        raise RuntimeError('Browser is not visibly in the foreground; workload refused: ' + text.value)
    print('VERIFIED VISIBLE FOREGROUND BROWSER: ' + text.value, flush=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{}')

    def do_GET(self):
        if self.path.startswith('/agent/check_chat_runtimes_status/'):
            payload = {'success': True, 'runtimes': {'video_test': {
                'is_running': True, 'notification': {'kind': 'fatal_visual_error', 'errors': EVENTS[:]}}}}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
            return
        if self.path.startswith('/dialog-test'):
            skin = 'agentic_control_panel' if 'acp' in self.path else 'agent_page'
            title = 'Visible Tlamatini Fatal Dialog - ' + skin
            html = f'''<!doctype html><html><head><title>{title}</title>
<link rel="stylesheet" href="{ASSETS}vendor/frontend/bootstrap/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="{ASSETS}css/{skin}.css">
<link rel="stylesheet" href="{ASSETS}css/dialog_theme.css">
<link rel="stylesheet" href="{ASSETS}vendor/frontend/nunito/400.css">
</head><body><h1>Visible Tlamatini error-dialog verification</h1>
<button id="continue-work" style="position:fixed;left:12px;top:100px">Continue work</button>
<output id="progress" style="position:fixed;left:12px;top:150px"></output>
<script>window.work=0; window.ticks=0;
document.getElementById('continue-work').onclick=()=>window.work++;
setInterval(()=>{{window.ticks++; document.getElementById('progress').textContent='Recovery remains active: '+window.ticks;}},100);
</script>
<script src="{ASSETS}vendor/frontend/jquery/dist/jquery.min.js"></script>
<script src="{ASSETS}vendor/frontend/jquery-ui/jquery-ui.min.js"></script>
<script src="{ASSETS}js/dialog_policy.js"></script>
<script src="{ASSETS}js/shared-runtime-dialogs.js"></script>
<script src="{ASSETS}js/chat_page_runtime_poller.js"></script>
</body></html>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
            return
        super().do_GET()


def check(name, value):
    RESULTS.append({'name': name, 'passed': bool(value)})
    print(('PASS ' if value else 'FAIL ') + name, flush=True)
    (OUT / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    if not value:
        raise AssertionError(name)


def verify(page, skin):
    EVENTS.clear()
    page.goto(BASE + '/dialog-test?' + skin)
    page.bring_to_front()
    page.wait_for_timeout(800)
    require_visible(page.title())
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    EVENTS.append({'id': skin + '-1', 'source_agent': 'Image-Interpreter',
                   'message': 'Configured model timed out. Tlamatini is trying its next recovery tactic.'})
    page.wait_for_selector('#tlm-visual-fatal-errors:visible')
    dialog = page.locator('#tlm-visual-fatal-errors')
    check(skin + ': runtime failure visibly opens dialog', dialog.is_visible())
    check(skin + ': fatal title', page.locator('.ui-dialog-title').inner_text() == 'Fatal analysis errors (1)')
    check(skin + ': no blocking modal overlay', page.locator('.ui-widget-overlay').count() == 0)
    close = page.locator('.notification-error .ui-dialog-titlebar-close')
    check(skin + ': titlebar X stays 32 pixels wide', close.bounding_box()['width'] == 32)
    check(skin + ': close label cannot overlap its icon', close.evaluate('e=>getComputedStyle(e).fontSize') == '0px')
    check(skin + ': titlebar X has an accessible name', close.get_attribute('title') == 'Dismiss')
    footer = page.locator('.notification-error .ui-dialog-buttonpane button')
    check(skin + ': footer Dismiss label remains readable', footer.inner_text() == 'Dismiss' and
          footer.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)') > 0)
    check(skin + ': footer button has no close icon', footer.evaluate('e=>getComputedStyle(e).backgroundImage') == 'none')
    page.locator('#continue-work').click()
    check(skin + ': background controls remain usable', page.evaluate('window.work') == 1)
    ticks = page.evaluate('window.ticks')
    page.wait_for_timeout(400)
    check(skin + ': recovery work continues with dialog open', page.evaluate('window.ticks') > ticks)
    page.evaluate("$('<div id=baseline>Ordinary Tlamatini dialog</div>').appendTo('body').dialog({autoOpen:false})")
    styles = page.evaluate('''() => {
        const fatal = $('#tlm-visual-fatal-errors').dialog('widget')[0];
        const ordinary = $('#baseline').dialog('widget')[0];
        const props=['backgroundColor','borderRadius','borderTopColor','boxShadow','fontFamily'];
        return props.map(p=>[p,getComputedStyle(fatal)[p]===getComputedStyle(ordinary)[p]]);
    }''')
    for prop, matches in styles:
        check(skin + ': shared theme ' + prop, matches)
    EVENTS.extend({'id': skin + '-' + str(i), 'source_agent': 'Video-Analyzer',
                   'message': f'Tactic {i}: configured observer failed. <img src=x onerror="window.injected=true">'}
                  for i in range(2, 13))
    page.evaluate('ChatRuntimePoller.pollOnce()')
    page.wait_for_function("document.querySelectorAll('#tlm-visual-fatal-errors li').length===12")
    check(skin + ': errors accumulate in one dialog', page.locator('#tlm-visual-fatal-errors').count() == 1)
    check(skin + ': all attempts retained', dialog.locator('li').count() == 12)
    check(skin + ': error text cannot inject HTML', dialog.locator('img').count() == 0 and not page.evaluate('!!window.injected'))
    page.evaluate('ChatRuntimePoller.pollOnce()')
    page.wait_for_timeout(250)
    check(skin + ': repeat polling does not duplicate errors', dialog.locator('li').count() == 12)
    page.locator('.notification-error .ui-dialog-buttonpane button').click()
    check(skin + ': dismiss works', not dialog.is_visible())
    page.evaluate('ChatRuntimePoller.pollOnce()')
    page.wait_for_timeout(250)
    check(skin + ': old errors do not reopen dismissed dialog', not dialog.is_visible())
    EVENTS.append({'id': skin + '-13', 'source_agent': 'Video-Analyzer', 'message': 'New failed attempt after dismiss'})
    page.evaluate('ChatRuntimePoller.pollOnce()')
    page.wait_for_selector('#tlm-visual-fatal-errors:visible')
    check(skin + ': new failure reopens accumulated history', dialog.locator('li').count() == 13)
    check(skin + ': original error remains', 'timed out' in dialog.inner_text())
    check(skin + ': content scrolls instead of covering desktop', dialog.evaluate('e=>e.getBoundingClientRect().height') <= 600)
    page.locator('#continue-work').click()
    check(skin + ': repeated errors still do not block controls', page.evaluate('window.work') == 2)
    close.click()
    check(skin + ': titlebar X dismisses without losing history', not dialog.is_visible() and dialog.locator('li').count() == 13)
    page.evaluate("SharedRuntimeDialogs.renderFatalError({id:'close-check',message:'A new failed attempt after titlebar dismissal'})")
    check(skin + ': new error reopens after titlebar dismissal', dialog.is_visible() and dialog.locator('li').count() == 14)
    page.keyboard.press('Escape')
    check(skin + ': Escape follows shared dismissal policy', not dialog.is_visible())
    page.evaluate("SharedRuntimeDialogs.renderFatalError({id:'escape-check',message:'A new failed attempt after Escape'})")
    check(skin + ': new error reopens after Escape with history intact', dialog.is_visible() and dialog.locator('li').count() == 15)
    check(skin + ': no browser script errors', not errors)
    require_visible(page.title())
    visible.OUT = OUT
    visible.photograph('fatal-dialog-' + skin)


if __name__ == '__main__':
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('Headless execution is forbidden.')
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    BASE = f'http://127.0.0.1:{server.server_port}'
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False, args=['--start-maximized'])
        page = browser.new_page(no_viewport=True)
        try:
            for skin in ('chat', 'acp'):
                verify(page, skin)
            print(f'VISIBLE BROWSER RESULT: {len(RESULTS)} checks passed. Holding open for inspection.', flush=True)
            for _ in range(6):
                page.wait_for_timeout(5000)
                print('Visible browser remains open for inspection.', flush=True)
        finally:
            browser.close()
            server.shutdown()
