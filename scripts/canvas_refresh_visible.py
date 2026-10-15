# Tlamatini Author Banner — Angela López Mendoza
"""Canvas Refresh acceptance, on the real source page in visible Chrome only.

Launch from a verified foreground PowerShell -NoExit console. Inspect the Shoter
browser-waiting.png and create browser-visible-confirmed before tests proceed.
Uses an isolated database and fixture files under Temp/canvas-refresh-visible.
No live model calls: only the model WebSocket transport is captured. The native
Open dialog grants a REAL local FileSystemFileHandle; subsequent disk edits and
Refresh clicks use that handle without opening another picker. Chrome stays open
for review. rerun.confirmed retries; close.confirmed finishes with the exit code.
"""
import asyncio
import html
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/canvas-refresh-visible'
BASE = 'http://127.0.0.1:8876'


class LiveTranscript:
    """Keep output on the visible console AND readable during long native runs."""
    def __init__(self, stream):
        self.stream = stream
        self.canvas_transcript = True

    def write(self, value):
        self.stream.write(value)
        self.stream.flush()
        with (OUT / 'live.log').open('a', encoding='utf-8') as log:
            log.write(value)

    def flush(self):
        self.stream.flush()


def native_open(page, window, path):
    """Drive the actual Chrome file picker on the visible Windows desktop."""
    import win32con
    import win32gui
    import win32process
    import psutil
    owned = {process.pid for process in psutil.Process().children(recursive=True)}
    window.activate()
    window.verify()
    generation = page.evaluate('canvasLoadGeneration')
    page.locator('#open-button').click()
    dialog = None
    for _ in range(80):
        candidates = []
        win32gui.EnumWindows(lambda hwnd, _: candidates.append(hwnd) if (
            win32gui.GetClassName(hwnd) == '#32770' and win32gui.IsWindowVisible(hwnd)
            and (win32process.GetWindowThreadProcessId(hwnd)[1] in owned
                 or win32gui.GetWindow(hwnd, win32con.GW_OWNER) == window.hwnd
                 or win32gui.GetAncestor(hwnd, win32con.GA_ROOTOWNER) == window.hwnd)) else None, None)
        if candidates:
            dialog = candidates[-1]
            break
        page.wait_for_timeout(100)
    if not dialog:
        found = []
        win32gui.EnumWindows(lambda hwnd, _: found.append((hwnd, win32gui.GetWindowText(hwnd), win32process.GetWindowThreadProcessId(hwnd)[1]))
                            if win32gui.GetClassName(hwnd) == '#32770' and win32gui.IsWindowVisible(hwnd) else None, None)
        print('Native picker diagnostics:', found, 'owned pids:', sorted(owned), flush=True)
        raise AssertionError('The native file picker did not appear.')
    assert win32gui.GetForegroundWindow() == dialog, 'Native picker is not foreground.'
    controls = []
    win32gui.EnumChildWindows(dialog, lambda hwnd, _: controls.append(hwnd), None)
    edits = [hwnd for hwnd in controls if win32gui.GetClassName(hwnd) == 'Edit'
             and win32gui.IsWindowVisible(hwnd)]
    filename = [hwnd for hwnd in edits if win32gui.GetDlgCtrlID(hwnd) == 1148]
    if not filename:
        filename = [hwnd for hwnd in edits if win32gui.GetClassName(win32gui.GetParent(hwnd)) == 'ComboBox']
    assert filename, [(win32gui.GetClassName(h), win32gui.GetDlgCtrlID(h)) for h in edits]
    win32gui.SendMessage(filename[0], win32con.WM_SETTEXT, 0, str(path))
    button = win32gui.GetDlgItem(dialog, 1)
    win32gui.PostMessage(button, win32con.BM_CLICK, 0, 0)
    page.wait_for_function('''({name, generation}) => canvasLoaded && canvasSource?.name === name
        && canvasSource.read && canvasLoadGeneration > generation && !TlamatiniCanvasRefresh.busy''',
        arg={'name': path.name, 'generation': generation})
    window.activate()
    window.verify()


def write_pdf(path, text, pages=2):
    import fitz
    doc = fitz.open()
    for number in range(pages):
        doc.new_page().insert_text((50, 60), f'{text} - page {number + 1}')
    path.write_bytes(doc.tobytes())
    doc.close()


def activate_browser(window):
    """Request focus without attaching to a potentially elevated broker thread."""
    import win32api
    import win32con
    import win32gui
    for _ in range(10):
        if win32gui.GetForegroundWindow() == window.hwnd:
            assert win32gui.IsWindowVisible(window.hwnd) and not win32gui.IsIconic(window.hwnd)
            return
        if win32gui.IsIconic(window.hwnd):
            win32gui.ShowWindow(window.hwnd, win32con.SW_RESTORE)
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        try:
            win32gui.SetForegroundWindow(window.hwnd)
        except Exception:
            pass
        window.page.wait_for_timeout(100)
    window.verify()  # A focus request alone never authorizes the workload.


def checks(page, context, window, capture, sent, errors, attempt):
    for name in ('stdout', 'stderr'):
        if not getattr(getattr(sys, name), 'canvas_transcript', False):
            setattr(sys, name, LiveTranscript(getattr(sys, name)))
    # A failed native-picker assertion can leave its owned dialog open. Dismiss
    # only this test browser's dialog before retrying, never another app's UI.
    import win32con
    import win32gui
    import win32process
    import psutil
    owned = {process.pid for process in psutil.Process().children(recursive=True)}
    dialogs = []
    win32gui.EnumWindows(lambda hwnd, _: dialogs.append(hwnd) if (
        win32gui.GetClassName(hwnd) == '#32770' and win32gui.IsWindowVisible(hwnd)
        and (win32process.GetWindowThreadProcessId(hwnd)[1] in owned
             or win32gui.GetWindow(hwnd, win32con.GW_OWNER) == window.hwnd
             or win32gui.GetAncestor(hwnd, win32con.GA_ROOTOWNER) == window.hwnd)) else None, None)
    for dialog in dialogs:
        win32gui.PostMessage(dialog, win32con.WM_CLOSE, 0, 0)
    page.wait_for_timeout(300)
    window.activate()
    folder = OUT / 'files'
    folder.mkdir(exist_ok=True)
    run = OUT / f'run-{attempt}'
    run.mkdir(exist_ok=True)
    results = []
    page.goto(BASE + '/agent/agent/', wait_until='load')
    page.wait_for_function('typeof refreshCanvas === "function"')
    page.evaluate('''() => {
        window.realPicker = window.showOpenFilePicker;
        window.pickerCalls = 0;
        window.showOpenFilePicker = async options => {
            window.pickerCalls++;
            const handles = await window.realPicker(options);
            window.testHandle = handles[0];
            return handles;
        };
        enableControlsAfterOperation();
    }''')
    refresh = page.locator('#reopen-canvas-button')

    def checkpoint(name):
        window.activate()
        window.verify()
        assert not errors, errors
        photo, _ = capture(f'run-{attempt}/{len(results)+1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name})
        print(f'PASS {len(results)}: {name}', flush=True)
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text('<!doctype html><meta charset="utf-8"><title>Canvas Refresh</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}</style>'
            + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2><img src="{row["photo"]}">'
                      for i, row in enumerate(results)), encoding='utf-8')

    def refreshed(state='updated'):
        window.activate()
        window.verify()
        refresh.click()
        page.wait_for_function('(state) => !TlamatiniCanvasRefresh.busy && document.querySelector("#reopen-canvas-button").dataset.state === state', arg=state)

    assert refresh.is_disabled()
    assert refresh.inner_text() == 'Refresh'
    checkpoint('empty-disabled-explained')

    text = folder / 'refresh.txt'
    text.write_text('First file version\n', encoding='utf-8')
    native_open(page, window, text)
    assert page.evaluate('textEditorCode.textContent') == 'First file version\n'
    assert refresh.is_enabled()
    checkpoint('native-open-retains-real-file-handle')

    page.evaluate('window.originalCode = textEditorCode')
    refreshed('unchanged')
    assert page.evaluate('originalCode === textEditorCode')
    assert page.evaluate('pickerCalls') == 1
    checkpoint('unchanged-is-a-noop-and-remains-checkable')

    # Same length and original modification time: content comparison must not
    # rely on metadata. This also exercises the browser's actual disk access.
    stamp = text.stat()
    text.write_text('Other file version\n', encoding='utf-8')
    os.utime(text, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    refreshed()
    assert page.evaluate('textEditorCode.textContent') == 'Other file version\n'
    assert page.evaluate('pickerCalls') == 1
    checkpoint('same-size-same-timestamp-real-disk-change')

    replacement = folder / 'replacement.txt'
    replacement.write_text('Atomically replaced\n', encoding='utf-8')
    os.replace(replacement, text)
    refreshed()
    assert page.evaluate('textEditorCode.textContent') == 'Atomically replaced\n'
    text.write_text('', encoding='utf-8')
    refreshed()
    assert page.evaluate('canvasLoaded && textEditorCode.textContent === ""')
    checkpoint('atomic-save-and-empty-file')

    text.write_text('Keep this visible', encoding='utf-8')
    refreshed()
    text.unlink()
    refreshed('error')
    assert page.evaluate('textEditorCode.textContent') == 'Keep this visible'
    text.write_text('Restored file', encoding='utf-8')
    refreshed()
    checkpoint('deleted-file-keeps-content-and-retries')

    page.evaluate('''() => {
        window.realGetFile = testHandle.getFile.bind(testHandle);
        testHandle.getFile = () => Promise.reject(new DOMException('Denied', 'NotAllowedError'));
        testHandle.requestPermission = async () => { testHandle.getFile = realGetFile; return 'granted'; };
    }''')
    refreshed('permission')
    assert refresh.inner_text() == 'Allow refresh'
    refreshed('unchanged')
    checkpoint('permission-recovery-never-opens-picker')

    page.evaluate('''() => {
        testHandle.getFile = () => new Promise(resolve => { window.releaseRead = resolve; });
        window.reads = 0;
        const read = testHandle.getFile;
        testHandle.getFile = () => { reads++; return read(); };
    }''')
    refresh.click()
    assert refresh.is_disabled()
    assert refresh.get_attribute('aria-busy') == 'true'
    page.evaluate('refreshCanvas()')
    assert page.evaluate('reads') == 1
    page.locator('#canvas-refresh-cancel').click()
    page.evaluate('releaseRead(new File(["late content"], "refresh.txt"))')
    page.wait_for_timeout(150)
    assert page.evaluate('textEditorCode.textContent') == 'Restored file'
    checkpoint('single-flight-cancel-discards-late-read')

    refresh.click()
    page.locator('#clean-canvas-button').click()
    page.evaluate('releaseRead(new File(["must not return"], "refresh.txt"))')
    page.wait_for_timeout(150)
    assert refresh.is_disabled() and page.evaluate('!canvasLoaded')
    checkpoint('clear-discards-inflight-refresh')

    md = folder / 'guide.md'
    md.write_text('# First heading\n\n**Original**\n', encoding='utf-8')
    native_open(page, window, md)
    page.locator('#markdown-source-button').click()
    md.write_text('# Refreshed heading\n\n**Latest**\n<script>window.canvasInjected = true</script>', encoding='utf-8')
    refreshed()
    assert page.locator('#editor-container').is_visible()
    page.locator('#markdown-preview-button').click()
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'Refreshed heading'
    assert not page.evaluate('Boolean(window.canvasInjected)')
    checkpoint('markdown-source-preview-and-sanitizer-refresh')

    page.evaluate('setContextButton()')
    md.write_text('# Context updated\n', encoding='utf-8')
    count = len(sent)
    refresh.click()
    page.wait_for_function('!TlamatiniCanvasRefresh.busy')
    payloads = [json.loads(value) for value in sent[count:]]
    assert [value['type'] for value in payloads] == ['set-canvas-as-context'], payloads
    assert payloads[0]['content'] == md.read_bytes().decode('utf-8'), payloads
    page.evaluate('enableControlsAfterOperation()')
    refreshed('unchanged')
    assert len(sent) == count + 1
    checkpoint('changed-context-replaced-once-unchanged-never-rebuilt')

    page.evaluate('''() => {
        window.realContextSend = sendChatSocketMessage;
        sendChatSocketMessage = () => false;
    }''')
    md.write_text('# Context connection retry\n', encoding='utf-8')
    refreshed('error')
    assert page.evaluate('canvasSource.contextPending && !canvasSettedAsContext')
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'Context connection retry'
    page.evaluate('sendChatSocketMessage = realContextSend')
    count = len(sent)
    refresh.click()
    page.wait_for_function('!TlamatiniCanvasRefresh.busy')
    assert json.loads(sent[-1])['content'] == md.read_bytes().decode('utf-8')
    assert len(sent) == count + 1
    page.evaluate('enableControlsAfterOperation()')
    refreshed('unchanged')
    assert len(sent) == count + 1
    checkpoint('failed-context-send-keeps-content-and-retries-once')

    page.evaluate('disableControlsDuringOperation()')
    assert refresh.is_disabled()
    page.evaluate('enableControlsAfterOperation()')
    assert refresh.is_enabled()
    checkpoint('chat-busy-lock-and-recovery')

    # Real dropped FileSystem entries, generated by Chrome from the fixture path.
    page.evaluate('canvasSettedAsContext = false')
    dropfile = folder / 'dropped.json'
    dropfile.write_text('{"version":1}', encoding='utf-8')
    session = context.new_cdp_session(page)
    bounds = page.locator('#canvas-container').bounding_box()
    drag = {'x': bounds['x'] + 100, 'y': bounds['y'] + 130,
            'data': {'items': [], 'files': [str(dropfile)], 'dragOperationsMask': 1}}
    for kind in ('dragEnter', 'dragOver', 'drop'):
        session.send('Input.dispatchDragEvent', {'type': kind, **drag})
    page.wait_for_function('canvasSource?.name === "dropped.json" && Boolean(canvasSource.read)')
    dropfile.write_text('{"version":2}', encoding='utf-8')
    refreshed()
    assert page.evaluate('textEditorCode.textContent') == '{"version":2}'
    checkpoint('real-drop-retains-read-access-through-json-classification')

    pdf = folder / 'review.pdf'
    write_pdf(pdf, 'Original PDF', pages=3)
    native_open(page, window, pdf)
    frame = page.frame_locator('#pdf-canvas-host iframe')
    frame.locator('#pdf-page').fill('3')
    frame.locator('#pdf-page').press('Enter')
    frame.locator('#pdf-zoom').select_option('1.5')
    write_pdf(pdf, 'New PDF', pages=2)
    refreshed()
    frame = page.frame_locator('#pdf-canvas-host iframe')
    assert frame.locator('#pdf-page-count').inner_text() == 'of 2'
    assert frame.locator('#pdf-page').input_value() == '2'
    assert frame.locator('#pdf-zoom').input_value() == '1.5'
    assert 'New PDF' in page.evaluate('TlamatiniPdfCanvas.getText()')
    checkpoint('pdf-complete-new-document-page-clamped-zoom-kept')

    page.evaluate('window.previousPdfFrame = document.querySelector("#pdf-canvas-host iframe")')
    pdf.write_bytes(b'%PDF-1.7\ninvalid truncated PDF')
    refreshed('error')
    assert page.evaluate('document.querySelector("#pdf-canvas-host iframe") === previousPdfFrame')
    assert frame.locator('#pdf-page-count').inner_text() == 'of 2'
    write_pdf(pdf, 'Recovered PDF', pages=1)
    refreshed()
    assert 'Recovered PDF' in page.evaluate('TlamatiniPdfCanvas.getText()')
    checkpoint('invalid-pdf-preserves-previous-viewer-and-recovers')

    # Isolate a connection loss AFTER a PDF context package is ready. Its
    # progress dialog must leave Loading, while the fresh PDF stays visible.
    page.evaluate('''() => {
        setContextButton();
        window.realPrepareContext = TlamatiniPdfCanvas.prepareContext;
        window.realPdfFail = TlamatiniPdfProgress.fail;
        window.realContextSend = sendChatSocketMessage;
        TlamatiniPdfCanvas.prepareContext = async () => ({token: 'isolated-refresh-test', analysis_warnings: []});
        TlamatiniPdfProgress.fail = message => { window.pdfFailure = message; realPdfFail(message); };
        sendChatSocketMessage = () => false;
    }''')
    write_pdf(pdf, 'Context send failed PDF', pages=1)
    refreshed('error')
    assert 'connection is unavailable' in page.evaluate('pdfFailure')
    assert page.evaluate('canvasSource.contextPending && !canvasSettedAsContext')
    assert 'Context send failed PDF' in page.evaluate('TlamatiniPdfCanvas.getText()')
    page.evaluate('''() => {
        TlamatiniPdfCanvas.prepareContext = realPrepareContext;
        TlamatiniPdfProgress.fail = realPdfFail;
        sendChatSocketMessage = realContextSend;
    }''')
    checkpoint('pdf-context-connection-failure-finishes-progress')

    # Stored generated text has its own authenticated source, never a guessed
    # local disk path. Exercise the real endpoint and a refused refresh.
    from agent.models import LLMProgram
    # Playwright's sync bridge owns an asyncio loop on this thread. Use a short
    # joined thread for Django's synchronous ORM, against this isolated DB only.
    update_errors = []

    def update_stored_source(content):
        from django.db import connections
        try:
            LLMProgram.objects.filter(programName='Refresh generated.md').update(programContent=content)
        except Exception as error:
            update_errors.append(error)
        finally:
            connections.close_all()

    def store_source(content):
        updater = threading.Thread(target=update_stored_source, args=(content,))
        updater.start()
        updater.join(timeout=10)
        assert not updater.is_alive() and not update_errors, update_errors

    store_source('# Original stored source\n')
    page.evaluate('loadCanvas("Refresh generated.md")')
    page.wait_for_function('canvasSource?.name === "Refresh generated.md"')
    store_source('# New stored source\n')
    refreshed()
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'New stored source'
    page.route('**/agent/load_canvas/**', lambda route: route.fulfill(status=403, body='Forbidden'))
    refreshed('error')
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'New stored source'
    page.unroute('**/agent/load_canvas/**')
    checkpoint('stored-source-no-cache-and-session-error-preservation')

    page.evaluate('window.showOpenFilePicker = undefined')
    with page.expect_file_chooser() as chooser:
        page.locator('#open-button').click()
    chooser.value.set_files(str(text))
    page.wait_for_function('canvasSource?.name === "refresh.txt"')
    assert refresh.is_disabled()
    assert 'without access' in page.locator('#canvas-refresh-status').inner_text()
    page.evaluate('enableControlsAfterOperation()')
    assert refresh.is_disabled()
    checkpoint('snapshot-only-browser-explains-disabled-refresh')

    page.evaluate('loadCanvasWithThisContent("Context tree")')
    assert refresh.is_disabled()
    assert 'summary' in page.locator('#canvas-refresh-status').inner_text()
    page.locator('#clean-canvas-button').click()
    assert refresh.is_disabled()
    checkpoint('summary-and-clear-reset-source')
    return results


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    from markdown_canvas_visible import visible_console
    visible_console()
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    os.environ['TLAMATINI_NO_AUDIO'] = '1'
    import tlamatini.settings as settings
    settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    import django
    django.setup()
    from django.core.management import call_command
    print('Preparing isolated database and collecting static files.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    sys.path.insert(0, str(ROOT))
    from build_runtime_assets import verify_collected_static
    verify_collected_static(ROOT)
    from django.contrib.auth import get_user_model
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username='canvas-refresh-review')
    user.set_password(password)
    user.save()
    from agent.models import LLMProgram
    LLMProgram.objects.update_or_create(idProgram=98766, defaults={
        'programName': 'Refresh generated.md', 'programLanguage': 'markdown',
        'programContent': '# Original stored source\n',
    })
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1',
                                         port=8876, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Isolated server failed to start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    import drag_divider_look_visible as photos
    photos.OUT = OUT
    success = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=80)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        sent, errors = [], []
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: sent.append(message)))
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        class RefreshWindow(VisibleWindow):
            def activate(self):
                activate_browser(self)

            def verify(self):
                import win32api
                self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
                return super().verify()

        window = RefreshWindow(page, context)
        window.resize(1440, 900)
        page.goto(BASE + '/', wait_until='load')

        def capture(name):
            window.verify()
            photos.OUT = OUT / Path(name).parent
            photos.OUT.mkdir(parents=True, exist_ok=True)
            photo = photos.shoter(Path(name).name)
            window.verify()
            return photo

        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        capture('browser-waiting.png')
        print('BROWSER WAITING: inspect browser-waiting.png before creating browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(300)
        page.locator('#id_username').fill('canvas-refresh-review')
        page.locator('#id_password').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state('load')
        password = None
        attempt = sum(path.is_dir() for path in OUT.glob('run-*'))
        close, rerun = OUT / 'close.confirmed', OUT / 'rerun.confirmed'
        close.unlink(missing_ok=True)
        rerun.unlink(missing_ok=True)
        while not close.exists() and not page.is_closed():
            attempt += 1
            try:
                errors.clear()
                spec = importlib.util.spec_from_file_location('refresh_checks', __file__)
                latest = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(latest)
                results = latest.checks(page, context, window, capture, sent, errors, attempt)
                success = True
                (OUT / 'final-result.json').write_text(json.dumps({'passed': True, 'checks': len(results), 'attempt': attempt}), encoding='utf-8')
            except Exception:
                success = False
                traceback.print_exc()
                window.activate()
                capture(f'run-{attempt}-failure.png')
                (OUT / 'final-result.json').write_text(json.dumps({'passed': False, 'attempt': attempt, 'error': traceback.format_exc()}), encoding='utf-8')
            print('BROWSER STAYS OPEN. rerun.confirmed repeats; close.confirmed ends.', flush=True)
            while not close.exists() and not rerun.exists() and not page.is_closed():
                page.wait_for_timeout(500)
            if rerun.exists():
                rerun.unlink()
        window.release()
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
