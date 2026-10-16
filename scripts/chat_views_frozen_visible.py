# Tlamatini Author Banner — Angela López Mendoza
"""Focused Views acceptance against a real frozen test instance on port 8878.

Run in a verified visible foreground console. Chrome is explicitly headed;
Shoter records the desktop. Requires Temp/views-frozen/frozen-runtime-proof.json
and credentials.json from the isolated compiled server. No network responses,
WebSockets, authentication or canvas state are mocked. This is a frontend
compatibility check, not a clean-install or complete release acceptance run.
Inspect browser-waiting.png before creating browser-visible-confirmed. The
browser stays open until close.confirmed, and rerun.confirmed retries checks.
"""
import hashlib
import html
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/views-frozen'
BASE = 'http://127.0.0.1:8878'


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    from markdown_canvas_visible import visible_console
    visible_console()
    proof = json.loads((OUT / 'frozen-runtime-proof.json').read_text(encoding='utf-8'))
    assert proof['frozen'] is True
    import canvas_refresh_visible as shared
    shared.OUT = OUT

    class Transcript(shared.LiveTranscript):
        def __getattr__(self, name):
            return getattr(self.stream, name)

    sys.stdout = Transcript(sys.stdout)
    sys.stderr = Transcript(sys.stderr)
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    import drag_divider_look_visible as photos

    class Window(VisibleWindow):
        checking_focus = False

        def activate(self):
            shared.activate_browser(self)

        def verify(self):
            import win32api
            import win32gui
            if win32gui.GetForegroundWindow() != self.hwnd and not self.checking_focus:
                self.checking_focus = True
                try:
                    self.activate()
                finally:
                    self.checking_focus = False
            self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
            return super().verify()

    passed = False
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(OUT / 'browser-profile'),
            channel='chrome', headless=False, slow_mo=100, no_viewport=True)
        page = context.pages[0]
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        window = Window(page, context)
        window.resize(1440, 900)

        def photo(name):
            window.activate()
            window.verify()
            photos.OUT = OUT / Path(name).parent
            photos.OUT.mkdir(parents=True, exist_ok=True)
            result, _ = photos.shoter(Path(name).name)
            window.activate()
            window.verify()
            return result

        page.goto(BASE + '/', wait_until='load')
        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        photo('browser-waiting.png')
        print('FROZEN BROWSER WAITING: inspect browser-waiting.png and create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(300)
        if page.locator('#id_username').count():
            credentials = json.loads((OUT / 'credentials.json').read_text(encoding='utf-8'))
            page.locator('#id_username').fill(credentials['username'])
            page.locator('#id_password').fill(credentials['password'])
            page.locator('button[type="submit"]').click()
            page.wait_for_load_state('load')
            credentials = None
        close, rerun = OUT / 'close.confirmed', OUT / 'rerun.confirmed'
        close.unlink(missing_ok=True)
        rerun.unlink(missing_ok=True)
        attempt = sum(path.is_dir() for path in OUT.glob('browser-run-*'))
        while not close.exists():
            attempt += 1
            rows = []
            run = OUT / f'browser-run-{attempt}'
            run.mkdir(exist_ok=True)

            def checkpoint(name):
                page.wait_for_timeout(300)
                assert not errors, errors
                capture = photo(f'browser-run-{attempt}/{len(rows)+1:02d}-{name}.png')
                rows.append({'name': name, 'photo': capture.name})
                (run / 'results.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
                (run / 'SUMMARY.html').write_text('<!doctype html><meta charset="utf-8"><title>Frozen Views</title>'
                    '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}</style>'
                    + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2><img src="{row["photo"]}">'
                              for i, row in enumerate(rows)), encoding='utf-8')
                print(f'FROZEN PASS {len(rows)}: {name}', flush=True)

            def menu():
                window.activate()
                window.verify()
                if page.locator('#views-menu-button').get_attribute('aria-expanded') != 'true':
                    page.locator('#views-menu-button').click()

            def toggle():
                menu()
                page.locator('#views-canvas-toggle').click()
                page.wait_for_timeout(350)

            def state(shown):
                assert page.locator('#canvas-container').is_visible() == shown
                assert page.locator('#drag-divider').is_visible() == shown
                assert page.locator('#views-canvas-toggle').get_attribute('aria-checked') == str(shown).lower()
                if not shown:
                    assert not page.locator('#copy-canvas-button').is_visible()
                    assert not page.locator('#tlm-avatar-resize').is_visible()
                    assert page.evaluate('TlamatiniAvatarSize.get()') == 0
                    assert page.evaluate('''() => Math.abs(document.getElementById('chat-workspace').getBoundingClientRect().width
                        - document.getElementById('main-chat-container').getBoundingClientRect().width) < 1''')

            try:
                errors.clear()
                page.goto(BASE + '/agent/agent/', wait_until='load')
                page.wait_for_function('window.TlamatiniViews && window.TlamatiniAvatarSize')
                page.wait_for_timeout(900)
                menu()
                page.locator('#views-reset-layout').click()
                state(True)
                checkpoint('real-frozen-page-has-views-and-reset')
                for name in ['agent_page_layout.js', 'avatar_size.js', 'agent_page_canvas.js', 'agent_page_init.js']:
                    response = context.request.get(BASE + '/static/agent/js/' + name)
                    assert response.ok
                    assert hashlib.sha256(response.body()).digest() == hashlib.sha256(
                        (ROOT / 'Tlamatini/agent/static/agent/js' / name).read_bytes()).digest()
                checkpoint('compiled-server-serves-current-javascript-bytes')
                draft = 'Keep this draft while I change the frozen layout.'
                page.locator('#chat-message-input').fill(draft)
                history = page.locator('#chat-log').inner_text()
                toggle()
                state(False)
                assert page.locator('#chat-message-input').input_value() == draft
                assert page.locator('#chat-log').inner_text() == history
                checkpoint('full-width-chat-docked-avatar-draft-and-history-preserved')
                page.reload(wait_until='load')
                page.wait_for_timeout(700)
                state(False)
                checkpoint('hidden-preference-survives-frozen-page-reload')
                page.locator('#chat-log a').filter(has_text='Views frozen.md').first.click()
                page.wait_for_function('canvasSource?.name === "Views frozen.md"')
                state(True)
                assert page.locator('#markdown-canvas-document h1').inner_text() == 'Frozen Views document'
                menu()
                assert page.locator('#views-canvas-check').is_visible()
                checkpoint('stored-answer-link-reveals-canvas-and-check-mark')
                page.keyboard.press('Escape')
                page.locator('#markdown-source-button').click()
                source = page.locator('#editor-container').inner_text()
                toggle()
                toggle()
                assert page.locator('#editor-container').is_visible()
                assert page.locator('#editor-container').inner_text() == source
                page.locator('#reopen-canvas-button').click()
                page.wait_for_function('!TlamatiniCanvasRefresh.busy && document.getElementById("reopen-canvas-button").dataset.state === "unchanged"')
                checkpoint('source-mode-and-refresh-listener-survive')
                page.locator('#tlm-avatar-resize').press('ArrowUp')
                assert page.evaluate('TlamatiniAvatarSize.get()') > 0
                toggle()
                state(False)
                checkpoint('hiding-floated-avatar-docks-and-locks-it')
                menu()
                page.locator('#views-canvas-toggle').focus()
                page.keyboard.press('Space')
                state(True)
                checkpoint('keyboard-shows-canvas-and-unlocks-avatar')
                page.locator('#chat-message-input').fill(draft)
                page.locator('#drag-divider').press('Home')
                page.locator('#vertical-drag-divider').press('End')
                page.locator('#tlm-avatar-resize').press('ArrowUp')
                menu()
                page.locator('#views-reset-layout').click()
                state(True)
                assert page.evaluate('TlamatiniAvatarSize.get()') == 0
                assert page.locator('#chat-message-input').input_value() == draft
                assert page.locator('#editor-container').inner_text() == source
                checkpoint('reset-restores-panes-and-dock-with-content-intact')
                toggle()
                local_file = OUT / 'opened-in-frozen.md'
                local_file.write_text('# Opened in frozen mode\n\nA normal file picker.', encoding='utf-8')
                shared.native_open(page, window, local_file)
                page.wait_for_function('canvasSource?.name === "opened-in-frozen.md"')
                state(True)
                checkpoint('normal-file-picker-reveals-canvas')
                toggle()
                window.resize(600, 720)
                state(False)
                assert page.evaluate('document.getElementById("chat-workspace").clientWidth <= innerWidth')
                checkpoint('narrow-frozen-chat-has-no-empty-canvas-width')
                window.resize(1440, 900)
                for shown in [False, True]:
                    if page.evaluate('TlamatiniViews.isCanvasVisible()') != shown:
                        toggle()
                    window.release()
                    context.close()
                    context = playwright.chromium.launch_persistent_context(str(OUT / 'browser-profile'),
                        channel='chrome', headless=False, slow_mo=100, no_viewport=True)
                    page = context.pages[0]
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    window = Window(page, context)
                    window.resize(1440, 900)
                    page.goto(BASE + '/agent/agent/', wait_until='load')
                    page.wait_for_timeout(700)
                    state(shown)
                    checkpoint('browser-restart-preserves-' + ('visible' if shown else 'hidden'))
                passed = True
                result = {'passed': True, 'checks': len(rows), 'attempt': attempt, 'runtime': proof,
                          'mode': 'actual frozen executable with refreshed frontend; no rebuild'}
            except Exception:
                passed = False
                traceback.print_exc()
                photo(f'browser-run-{attempt}/failure.png')
                result = {'passed': False, 'attempt': attempt, 'error': traceback.format_exc()}
            (OUT / 'browser-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print('FROZEN BROWSER STAYS OPEN: close.confirmed ends; rerun.confirmed retries.', flush=True)
            while not close.exists() and not rerun.exists():
                page.wait_for_timeout(500)
            rerun.unlink(missing_ok=True)
        window.release()
        context.close()
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
