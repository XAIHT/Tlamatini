# Tlamatini Author Banner — Angela López Mendoza
"""Open a real Markdown file in the source canvas, visibly and without changing it.

From a verified foreground PowerShell -NoExit console, run:
python -u scripts/canvas_text_decoding_visible.py --file C:\\project\\README.md

Uses an isolated database, Chrome profile and fixtures below the repository's
Temp/canvas-text-decoding-visible. No model calls or production DB changes.
Chrome must be visible and foreground before checks proceed. Full-desktop Shoter
photos and results.json retain the evidence. Chrome stays open until the operator
closes it or creates close.confirmed in the evidence directory.
"""
import argparse
import asyncio
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/canvas-text-decoding-visible'


def foreground_console():
    import win32gui
    ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    console = ctypes.windll.kernel32.GetConsoleWindow()
    if not (console and win32gui.IsWindowVisible(console)
            and not win32gui.IsIconic(console)
            and win32gui.GetForegroundWindow() == console):
        raise RuntimeError('Run from a visible foreground conhost PowerShell -NoExit console.')


class BrowserWindow:
    """Observe visibility; never attach input threads or pin a topmost window."""

    def __init__(self, page):
        import psutil
        import win32gui
        import win32process
        self.page = page
        owned = {p.pid for p in psutil.Process().children(recursive=True)}
        windows = []
        win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd) if (
            win32gui.GetClassName(hwnd).startswith('Chrome_WidgetWin')
            and win32process.GetWindowThreadProcessId(hwnd)[1] in owned
            and win32gui.IsWindowVisible(hwnd)) else None, None)
        if len(windows) != 1:
            raise RuntimeError(f'Expected one visible test Chrome window; found {len(windows)}.')
        self.hwnd = windows[0]

    def verify(self):
        import win32gui
        assert win32gui.IsWindowVisible(self.hwnd) and not win32gui.IsIconic(self.hwnd)
        assert win32gui.GetForegroundWindow() == self.hwnd, 'Test Chrome is not foreground.'
        cloaked = ctypes.c_int()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(self.hwnd), 14,
                                                ctypes.byref(cloaked), 4)
        assert not cloaked.value, 'Test Chrome is on another desktop.'

    def activate(self):
        self.page.bring_to_front()
        deadline = time.monotonic() + 30
        while True:
            try:
                self.verify()
                return
            except AssertionError:
                if time.monotonic() >= deadline:
                    raise
                self.page.wait_for_timeout(200)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    foreground_console()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').unlink(missing_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(OUT)
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    fixture = OUT / 'README.md'
    fixture.write_text('# README\n\nReadable paths: \a' + 'ssets/ and \b' +
                       'enchmarks/.\n' + 'Markdown stays editable.\n' * 5, encoding='utf-8')
    actual = (args.file or fixture).resolve(strict=True)
    original = actual.read_bytes()
    raw = original.decode('utf-8-sig')
    expected = raw.replace('\r\n', '\n').replace('\r', '\n')
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    import tlamatini.settings as settings
    settings.DATABASES['default']['NAME'] = OUT / 'isolated.sqlite3'
    settings.DEBUG = True
    import django
    django.setup()
    from django.core.management import call_command
    print('Preparing isolated source application.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    from django.test import Client
    user, _ = get_user_model().objects.get_or_create(username='canvas-text-review')
    client = Client()
    client.force_login(user)
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application),
        host='127.0.0.1', port=8886, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Source test server failed to start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from canvas_refresh_visible import native_open
    import drag_divider_look_visible as photos
    photos.OUT = OUT
    results = []
    success = False
    close = OUT / 'close.confirmed'
    close.unlink(missing_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(OUT / 'chrome-profile'),
            channel='chrome', headless=False, no_viewport=True, slow_mo=150,
            downloads_path=str(OUT / 'saved-copies'), args=['--start-maximized'])
        context.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
            'value': client.cookies[settings.SESSION_COOKIE_NAME].value,
            'url': 'http://127.0.0.1:8886'}])
        # Only model transport is isolated; file reads, decoding and rendering are real.
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda _: None))
        page = context.pages[0]
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8886/agent/agent/', wait_until='load')
        page.wait_for_function('window.TlamatiniCanvasEditing && window.TlamatiniMarkdownCanvas')
        window = BrowserWindow(page)
        window.activate()
        photos.shoter('browser-visible.png')
        print('BROWSER VISIBLE: native Open, Preview, Source and Refresh checks starting.', flush=True)

        def checkpoint(name):
            window.verify()
            assert not errors, errors
            photos.shoter(f'{len(results) + 1:02d}.png')
            results.append(name)
            print('PASS:', name, flush=True)
            page.wait_for_timeout(800)

        try:
            if not page.locator('#open-button').is_visible():
                page.locator('.navbar-toggler').click()
            native_open(page, window, actual)
            assert page.locator('#markdown-canvas-document h1').count() == 1
            assert page.locator('#markdown-canvas-host').is_visible()
            checkpoint('Actual README opens through the native Open dialog in Markdown Preview')
            page.locator('#markdown-source-button').click()
            assert page.evaluate('TlamatiniCanvasEditing.text') == expected
            assert page.locator('.cm-editor').is_visible()
            checkpoint('Source retains the complete text, including its control characters')
            page.locator('#reopen-canvas-button').click()
            page.wait_for_function("document.querySelector('#reopen-canvas-button').dataset.state === 'unchanged'")
            assert page.evaluate('TlamatiniCanvasEditing.text') == expected
            checkpoint('Refresh rereads the real disk file without a binary rejection')
            page.locator('#clean-canvas-button').click()
            page.evaluate('''({bytes, name}) => {
                const drop = new DataTransfer();
                drop.items.add(new File([new Uint8Array(bytes)], name));
                document.querySelector('#editor-container').dispatchEvent(
                    new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: drop}));
            }''', {'bytes': list(original), 'name': actual.name})
            page.wait_for_function('canvasLoaded && TlamatiniMarkdownCanvas.active')
            assert page.evaluate('TlamatiniCanvasEditing.text') == expected
            checkpoint('Automated file drop uses the same decoder and opens Markdown')
            alerts = []
            def accept_alert(dialog):
                alerts.append(dialog.message)
                dialog.accept()
            page.on('dialog', accept_alert)
            for payload in ([0, 1, 2], [1, 2, 3, 4], [195, 40]):
                window.verify()
                page.evaluate('bytes => loadSelectedCanvasFile(new File([new Uint8Array(bytes)], "binary.md"))', payload)
                assert page.evaluate('TlamatiniCanvasEditing.text') == expected
            assert len(alerts) == 3 and all('Unable to load binary.md' in text for text in alerts)
            checkpoint('Binary and malformed data are refused while the current document is preserved')
            utf16 = OUT / 'UTF16-README.md'
            utf16.write_bytes(b'\xff\xfe' + raw.encode('utf-16le'))
            native_open(page, window, utf16)
            assert page.evaluate('TlamatiniCanvasEditing.text') == expected
            assert 'UTF-16LE' in page.locator('#canvas-edit-status').inner_text()
            checkpoint('The same Markdown also opens correctly as BOM-marked UTF-16')
            native_open(page, window, actual)
            assert actual.read_bytes() == original
            checkpoint('Original README remains byte-for-byte unchanged; Preview left open')
            success = True
        except Exception:
            traceback.print_exc()
            photos.shoter('failure.png')
        finally:
            (OUT / 'results.json').write_text(json.dumps({
                'passed': success, 'checks': results, 'file': str(actual),
                'sha256': hashlib.sha256(original).hexdigest(), 'javascript_errors': errors,
                'original_unchanged': actual.read_bytes() == original,
            }, indent=2), encoding='utf-8')
            print('RESULT:', success, 'CHECKS:', len(results), flush=True)
            print('Chrome stays open for review. Close it or create close.confirmed to finish.', flush=True)
        while not close.exists() and not page.is_closed():
            page.wait_for_timeout(500)
        context.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
