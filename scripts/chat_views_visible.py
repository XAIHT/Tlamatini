# Tlamatini Author Banner — Angela López Mendoza
"""Views acceptance on source/dev artifacts, never a rebuild or installed app.

Run from a verified visible Tlamatini PowerShell -NoExit console:
    python scripts/chat_views_visible.py
Chrome is explicitly headed, with native window visibility checked before work.
Inspect Temp/chat-views-visible/browser-waiting.png, then create
browser-visible-confirmed there. Shoter photographs every checkpoint. The real
Django templates, auth, static assets and saved-content endpoint use an isolated
database. The model WebSocket is captured; no paid model requests are made.
Chrome stays open after checks; rerun.confirmed repeats, close.confirmed ends.
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
OUT = ROOT / 'Temp/chat-views-visible'
BASE = 'http://127.0.0.1:8877'


def checks(page, context, window, capture, sent, errors, attempt):
    results = []
    run = OUT / f'run-{attempt}'
    run.mkdir(exist_ok=True)

    def settle():
        page.wait_for_timeout(350)
        window.activate()
        window.verify()

    def checkpoint(name):
        settle()
        assert not errors, errors
        photo = capture(f'run-{attempt}/{len(results)+1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name})
        print(f'PASS {len(results)}: {name}', flush=True)
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text('<!doctype html><meta charset="utf-8"><title>Tlamatini Views</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}</style>'
            + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2><img src="{row["photo"]}">'
                      for i, row in enumerate(results)), encoding='utf-8')

    def menu():
        window.activate()
        window.verify()
        if page.locator('#views-menu-button').get_attribute('aria-expanded') != 'true':
            page.locator('#views-menu-button').click()

    def toggle():
        menu()
        page.locator('#views-canvas-toggle').click()
        settle()

    def hidden():
        assert not page.locator('#canvas-container').is_visible()
        assert not page.locator('#copy-canvas-button').is_visible()
        assert not page.locator('#reopen-canvas-button').is_visible()
        assert not page.locator('#drag-divider').is_visible()
        assert not page.locator('#tlm-avatar-resize').is_visible()
        assert page.locator('#views-canvas-toggle').get_attribute('aria-checked') == 'false'
        assert page.evaluate('''() => {
            const r = id => document.getElementById(id).getBoundingClientRect();
            return Math.abs(r('main-chat-container').width-r('chat-workspace').width) < 1
                && !document.getElementById('tlm-avatar-dock').classList.contains('tlm-floating');
        }''')

    def shown():
        assert page.locator('#canvas-container').is_visible()
        assert page.locator('#drag-divider').is_visible()
        assert page.locator('#tlm-avatar-resize').is_visible()
        assert page.locator('#views-canvas-toggle').get_attribute('aria-checked') == 'true'

    def geometry():
        return page.evaluate('''() => Object.fromEntries(['main-chat-container','canvas-container',
            'chat-log','tools-chat-form-container','tlm-avatar-dock'].map(id => {
                const r=document.getElementById(id).getBoundingClientRect();
                return [id,{x:r.x,y:r.y,width:r.width,height:r.height}];
            }))''')

    window.activate()
    window.resize(1440, 900)
    page.goto(BASE + '/agent/agent/', wait_until='load')
    page.wait_for_function('window.TlamatiniViews && window.TlamatiniAvatarSize')
    page.evaluate('''() => {
        localStorage.removeItem('tlamatini.chat.views.v1.'+document.body.dataset.layoutUser);
        TlamatiniAvatarSize.set(0);
    }''')
    page.reload(wait_until='load')
    page.evaluate('document.fonts.ready')
    page.wait_for_timeout(800)
    page.evaluate('enableControlsAfterOperation()')
    shown()
    initial = geometry()
    menu()
    assert page.locator('#views-canvas-check').is_visible()
    checkpoint('default-visible-and-checked')
    page.keyboard.press('Escape')

    draft = 'Keep my draft, selected context and chat history while changing Views.'
    page.locator('#chat-message-input').fill(draft)
    page.evaluate('''() => {
        loadCanvasWithThisContent('Retained canvas content');
        setContextButton();
        applyContextUiState('Views fixture.txt', 'file', 'Views fixture.txt');
        window.viewsOriginalCode=textEditorCode;
        window.viewsOriginalSource=canvasSource;
        window.viewsOriginalGeneration=canvasLoadGeneration;
        window.viewsOriginalHistory=document.getElementById('chat-log').innerHTML;
    }''')
    page.wait_for_timeout(350)
    before_sent = len(sent)
    toggle()
    hidden()
    assert page.locator('#chat-message-input').input_value() == draft
    assert page.evaluate('''viewsOriginalCode === textEditorCode && viewsOriginalSource === canvasSource
        && viewsOriginalGeneration === canvasLoadGeneration && canvasSettedAsContext
        && viewsOriginalHistory === document.getElementById('chat-log').innerHTML''')
    assert len(sent) == before_sent
    checkpoint('hide-full-width-preserves-dom-context-draft-history-and-socket')

    page.evaluate('TlamatiniAvatarSize.set(520); TlamatiniAvatarSize.cycle()')
    hidden()
    assert page.evaluate('TlamatiniAvatarSize.get()') == 0
    checkpoint('hidden-avatar-cannot-undock-even-through-api')
    page.reload(wait_until='load')
    settle()
    hidden()
    checkpoint('hidden-choice-survives-page-reopen')

    menu()
    page.locator('#views-canvas-toggle').focus()
    page.keyboard.press('Space')
    settle()
    shown()
    checkpoint('keyboard-toggle-shows-canvas')
    page.locator('#tlm-avatar-resize').press('ArrowUp')
    assert page.evaluate('TlamatiniAvatarSize.get()') > 0
    toggle()
    hidden()
    checkpoint('hiding-floating-avatar-docks-it-and-removes-resize-tab-stop')

    page.evaluate('''() => {
        enableControlsAfterOperation();
        const link=buildSafeLoadCanvasLink(`<a onclick='loadCanvas("Views generated.md");'>Load in canvas: Views generated.md</a>`);
        const row=document.createElement('div'); row.id='views-generated-answer';
        row.appendChild(link); document.getElementById('chat-log').appendChild(row);
    }''')
    page.locator('#views-generated-answer .chat-load-canvas-link').click()
    page.wait_for_function('canvasSource?.name === "Views generated.md"')
    shown()
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'Views generated document'
    menu()
    assert page.locator('#views-canvas-check').is_visible()
    checkpoint('real-generated-link-loads-and-rechecks-menu')
    page.keyboard.press('Escape')

    page.locator('#markdown-source-button').click()
    page.locator('#chat-message-input').fill(draft)
    toggle()
    toggle()
    assert page.locator('#editor-container').is_visible()
    assert page.locator('#chat-message-input').input_value() == draft
    assert page.locator('#reopen-canvas-button').is_enabled()
    checkpoint('markdown-source-and-refresh-listeners-survive-hide-show')
    page.locator('#reopen-canvas-button').click()
    page.wait_for_function('!TlamatiniCanvasRefresh.busy && document.getElementById("reopen-canvas-button").dataset.state === "unchanged"')
    checkpoint('retained-generated-document-still-refreshes')

    toggle()
    page.evaluate('disableControlsDuringOperation()')
    assert page.locator('#views-menu-button').is_enabled()
    toggle()
    shown()
    assert page.locator('#reopen-canvas-button').is_disabled()
    toggle()
    menu()
    page.locator('#views-reset-layout').click()
    settle()
    shown()
    assert page.locator('#reopen-canvas-button').is_disabled()
    assert page.locator('#chat-message-input').input_value() == draft
    page.evaluate('enableControlsAfterOperation()')
    checkpoint('views-and-reset-work-during-answer-with-operation-locks-intact')

    page.locator('#drag-divider').press('Home')
    page.locator('#vertical-drag-divider').press('End')
    page.locator('#tlm-avatar-resize').press('ArrowUp')
    before = page.evaluate('({text:textEditorCode.textContent,generation:canvasLoadGeneration})')
    menu()
    page.locator('#views-reset-layout').click()
    settle()
    shown()
    reset_geometry = geometry()
    for identifier in initial:
        for dimension in ['width', 'height']:
            assert abs(initial[identifier][dimension]-reset_geometry[identifier][dimension]) < 2, (initial, reset_geometry)
    assert page.evaluate('({text:textEditorCode.textContent,generation:canvasLoadGeneration})') == before
    assert page.locator('#chat-message-input').input_value() == draft
    checkpoint('reset-restores-initial-divider-and-avatar-geometry-without-reload')
    page.reload(wait_until='load')
    settle()
    shown()
    checkpoint('reset-visible-choice-persists')

    # Open a selected local PDF through the same entry point the picker/drop uses.
    page.evaluate('enableControlsAfterOperation()')
    pdf = OUT / 'views.pdf'
    from canvas_refresh_visible import write_pdf
    write_pdf(pdf, 'Views keeps the PDF frame alive', pages=3)
    pdf_bytes = list(pdf.read_bytes())
    page.evaluate('''async bytes => {
        await loadSelectedCanvasFile(new File([new Uint8Array(bytes)],'views.pdf',{type:'application/pdf'}));
    }''', pdf_bytes)
    frame = page.frame_locator('#pdf-canvas-host iframe')
    frame.locator('#pdf-page').fill('2')
    frame.locator('#pdf-page').press('Enter')
    frame.locator('#pdf-zoom').select_option('1.5')
    page.evaluate('window.viewsPdfFrame=document.querySelector("#pdf-canvas-host iframe")')
    toggle()
    toggle()
    assert page.evaluate('viewsPdfFrame === document.querySelector("#pdf-canvas-host iframe")')
    assert frame.locator('#pdf-page').input_value() == '2'
    assert frame.locator('#pdf-zoom').input_value() == '1.5'
    checkpoint('pdf-frame-page-and-zoom-survive-hide-show')

    toggle()
    page.evaluate('''async () => {
        await loadSelectedCanvasFile(new File(['# Opened while hidden'], 'opened.md',{type:'text/markdown'}));
    }''')
    shown()
    assert page.locator('#markdown-canvas-document h1').inner_text() == 'Opened while hidden'
    checkpoint('opening-document-automatically-reveals-canvas')

    toggle()
    drop = OUT / 'dropped.txt'
    drop.write_text('Real file drop onto the full-width chat.', encoding='utf-8')
    session = context.new_cdp_session(page)
    box = page.locator('#chat-log').bounding_box()
    event = {'x': box['x']+100, 'y': box['y']+100,
             'data': {'items': [], 'files': [str(drop)], 'dragOperationsMask': 1}}
    for kind in ['dragEnter','dragOver','drop']:
        session.send('Input.dispatchDragEvent', {'type': kind, **event})
    page.wait_for_function('canvasSource?.name === "dropped.txt"')
    shown()
    assert page.evaluate('textEditorCode.textContent') == drop.read_text(encoding='utf-8')
    checkpoint('real-file-drop-on-full-width-chat-reveals-canvas')

    toggle()
    window.resize(600, 720)
    hidden()
    assert page.evaluate('document.getElementById("chat-workspace").clientWidth <= innerWidth')
    assert page.locator('#chat-message-submit').is_visible()
    assert page.locator('#tlm-avatar-dock').is_visible()
    checkpoint('narrow-chat-only-fills-viewport-without-empty-canvas-width')
    window.resize(1440, 900)
    page.evaluate('TlamatiniViews.resetLayout()')

    page.evaluate('''() => {
        window.viewsRealSetItem=Storage.prototype.setItem;
        Storage.prototype.setItem=function(){throw new DOMException('Blocked','SecurityError');};
    }''')
    toggle()
    hidden()
    toggle()
    shown()
    page.evaluate('() => { Storage.prototype.setItem=viewsRealSetItem; }')
    checkpoint('blocked-storage-still-allows-hide-and-show')

    # Same-account tabs follow the preference, without replacing their content.
    peer = context.new_page()
    peer.goto(BASE + '/agent/agent/', wait_until='load')
    peer.wait_for_function('window.TlamatiniViews')
    peer.locator('#views-menu-button').click()
    peer.locator('#views-canvas-toggle').click()
    page.bring_to_front()
    settle()
    hidden()
    peer.close()
    checkpoint('same-account-tab-synchronizes-canvas-visibility')
    page.evaluate('''() => localStorage.setItem('tlamatini.chat.views.v1.another-account','visible')''')
    hidden()
    checkpoint('other-account-preference-does-not-change-this-chat')
    page.evaluate('TlamatiniViews.resetLayout()')

    # Normal form listener remains connected after repeated view changes.
    page.evaluate('enableControlsAfterOperation()')
    page.locator('#chat-message-input').fill('Views regression: ordinary chat still submits.')
    start = len(sent)
    page.locator('#chat-message-submit').click()
    page.wait_for_timeout(500)
    assert any('Views regression: ordinary chat still submits.' in value for value in sent[start:]), sent[start:]
    checkpoint('normal-chat-submit-listener-survives-view-changes')
    page.evaluate('enableControlsAfterOperation(); TlamatiniViews.resetLayout()')
    return results


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    from markdown_canvas_visible import visible_console
    visible_console()
    OUT.mkdir(parents=True, exist_ok=True)
    # A log flushes every write while the same output remains on the console.
    import canvas_refresh_visible as shared
    shared.OUT = OUT
    class Transcript(shared.LiveTranscript):
        def __getattr__(self, name):
            return getattr(self.stream, name)
    sys.stdout = Transcript(sys.stdout)
    sys.stderr = Transcript(sys.stderr)
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    os.environ['TLAMATINI_NO_AUDIO'] = '1'
    import tlamatini.settings as settings
    settings.DATABASES['default']['NAME'] = OUT / 'Tlamatini-dev.sqlite3'
    settings.STATIC_ROOT = OUT / 'staticfiles'
    import django
    django.setup()
    from django.core.management import call_command
    print('Tlamatini-dev: isolated database; live source templates; fresh static assets. NO BUILD.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    print('Isolated migrations complete. Collecting dev static assets.', flush=True)
    call_command('collectstatic', interactive=False, verbosity=0)
    print('Dev static assets ready. Starting the isolated server.', flush=True)
    from django.contrib.auth import get_user_model
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username='views-review')
    user.set_password(password)
    user.save()
    from agent.models import LLMProgram
    LLMProgram.objects.update_or_create(idProgram=98767, defaults={
        'programName':'Views generated.md', 'programLanguage':'markdown',
        'programContent':'# Views generated document\n\nRetain this document while changing Views.\n'})
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1',
        port=8877, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Tlamatini-dev server did not start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    from canvas_refresh_visible import activate_browser
    import drag_divider_look_visible as photos
    success = False
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(OUT / 'browser-profile'),
            channel='chrome', headless=False, slow_mo=90, no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        sent, errors = [], []
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda value: sent.append(value)))
        page = context.pages[0]
        page.on('pageerror', lambda error: errors.append(str(error)))

        class ViewsWindow(VisibleWindow):
            checking_focus = False

            def activate(self):
                activate_browser(self)

            def verify(self):
                import win32api
                import win32gui
                # A desktop user can switch apps between checkpoints. Reacquire
                # once, then measure actual foreground/visibility; never infer it
                # from a successful activation request. Guard failure recursion.
                if win32gui.GetForegroundWindow() != self.hwnd and not self.checking_focus:
                    self.checking_focus = True
                    try:
                        self.activate()
                    finally:
                        self.checking_focus = False
                self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
                return super().verify()

        window = ViewsWindow(page, context)
        window.resize(1440, 900)
        page.goto(BASE + '/', wait_until='load')

        def capture(name):
            window.verify()
            photos.OUT = OUT / Path(name).parent
            photos.OUT.mkdir(parents=True, exist_ok=True)
            result, _ = photos.shoter(Path(name).name)
            window.verify()
            return result

        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        capture('browser-waiting.png')
        print('BROWSER WAITING: inspect browser-waiting.png, then create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(300)
        page.locator('#id_username').fill('views-review')
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
                spec = importlib.util.spec_from_file_location('views_checks', __file__)
                latest = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(latest)
                results = latest.checks(page, context, window, capture, sent, errors, attempt)
                # Close Chrome completely twice. Reopen the SAME disk profile:
                # this proves localStorage persistence beyond a reload/new tab.
                for expected_visible in [False, True]:
                    page.evaluate('(show) => TlamatiniViews.setCanvasVisible(show)', expected_visible)
                    window.release()
                    context.close()
                    context = playwright.chromium.launch_persistent_context(str(OUT / 'browser-profile'),
                        channel='chrome', headless=False, slow_mo=90, no_viewport=True)
                    context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda value: sent.append(value)))
                    page = context.pages[0]
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    window = ViewsWindow(page, context)
                    window.resize(1440, 900)
                    page.goto(BASE + '/agent/agent/', wait_until='load')
                    page.wait_for_function('window.TlamatiniViews')
                    page.wait_for_timeout(400)
                    window.verify()
                    assert page.evaluate('TlamatiniViews.isCanvasVisible()') == expected_visible
                    assert page.locator('#canvas-container').is_visible() == expected_visible
                    assert not errors, errors
                    name = 'browser-restart-preserves-' + ('visible' if expected_visible else 'hidden')
                    photo = capture(f'run-{attempt}/{len(results)+1:02d}-{name}.png')
                    results.append({'name':name,'photo':photo.name})
                    print(f'PASS {len(results)}: {name}', flush=True)
                run = OUT / f'run-{attempt}'
                (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                (run / 'SUMMARY.html').write_text('<!doctype html><meta charset="utf-8"><title>Tlamatini Views</title>'
                    '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}</style>'
                    + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2><img src="{row["photo"]}">'
                              for i,row in enumerate(results)), encoding='utf-8')
                success = True
                result = {'passed':True,'checks':len(results),'attempt':attempt,'mode':'source/dev; no rebuild'}
            except Exception:
                success = False
                traceback.print_exc()
                window.activate()
                capture(f'run-{attempt}-failure.png')
                result = {'passed':False,'attempt':attempt,'error':traceback.format_exc()}
            (OUT / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print('BROWSER STAYS OPEN: rerun.confirmed retries; close.confirmed ends.', flush=True)
            while not close.exists() and not rerun.exists() and not page.is_closed():
                page.wait_for_timeout(500)
            rerun.unlink(missing_ok=True)
        window.release()
        context.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
