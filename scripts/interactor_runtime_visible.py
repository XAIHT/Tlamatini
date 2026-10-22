# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Focused source / existing frozen Interactor acceptance, never headless.

Launch from a verified visible console. Uses normal login and unmodified chat,
editor WebSockets and native Save views. A file-based test driver invokes the
real tool inside the tested process; it does not certify model planning. Never
point --frozen at a personal install: use an extracted disposable package.
Inspect browser-waiting.png before creating browser-visible-confirmed. Results
stay on screen until close.confirmed. No executable is rebuilt or patched.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', type=Path)
    args = parser.parse_args()
    from markdown_canvas_visible import visible_console
    visible_console()
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    mode = 'frozen' if args.frozen else 'source'
    out = ROOT / 'Temp/interactor-modes' / mode
    out.mkdir(parents=True, exist_ok=True)
    for name in ('stop-server', 'reply.json', 'command.json', 'browser-visible-confirmed', 'close.confirmed', 'runtime.json'):
        (out / name).unlink(missing_ok=True)
    import canvas_editing_visible as shared
    shared.OUT = out
    sys.stdout = shared.LiveTranscript(sys.stdout)
    sys.stderr = shared.LiveTranscript(sys.stderr)
    port = 8885 if args.frozen else 8884
    base = f'http://127.0.0.1:{port}'
    runtime = args.frozen.resolve() if args.frozen else ROOT
    if args.frozen and not runtime.is_relative_to(ROOT / 'Temp/interactor-modes'):
        raise SystemExit('Use only a disposable runtime below Temp/interactor-modes.')
    driver = ROOT / 'scripts/interactor_runtime_server.py'
    expression = f'exec(compile(open({str(driver)!r}, encoding="utf-8").read(), {str(driver)!r}, "exec"))'
    command = [str(runtime / 'Tlamatini.exe')] if args.frozen else [sys.executable, '-u', str(ROOT / 'Tlamatini/manage.py')]
    env = dict(os.environ, TLAMATINI_INTERACTOR_TEST_DIR=str(out), TLAMATINI_INTERACTOR_TEST_PORT=str(port), TLAMATINI_NO_AUDIO='1')
    # Start before importing Shoter: inherit this verified visible console.
    process = subprocess.Popen([*command, 'shell', '-c', expression], cwd=runtime, env=env)
    result = {'mode': mode, 'checks': [], 'failures': []}
    try:
        for attempt in range(120):
            if process.poll() is not None:
                raise RuntimeError(f'Runtime exited during startup: {process.returncode}')
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except Exception:
                if attempt % 10 == 0:
                    print('Waiting for actual', mode, 'server...', flush=True)
                time.sleep(1)
        else:
            raise RuntimeError('Runtime did not start within 120 seconds.')
        proof = json.loads((out / 'runtime.json').read_text(encoding='utf-8'))
        assert proof['frozen'] == bool(args.frozen), proof
        if args.frozen:
            assert proof['tool_loader'] == 'PyiFrozenLoader', proof
        result['runtime'] = proof
        preload = ROOT / 'scripts/playwright_real_visibility.cjs'
        os.environ['NODE_OPTIONS'] = (os.environ.get('NODE_OPTIONS', '') + f' --require="{preload.as_posix()}"').strip()
        from playwright.sync_api import sync_playwright
        from chat_composer_visible_window import VisibleWindow
        from canvas_refresh_visible import native_open, write_pdf
        import drag_divider_look_visible as photos
        import win32con
        import win32gui
        import win32api

        class Window(VisibleWindow):
            def verify(self):
                self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
                return super().verify()

        def rpc(frame):
            staged = out / 'command.tmp'
            staged.write_text(json.dumps(frame), encoding='utf-8')
            staged.replace(out / 'command.json')
            deadline = time.monotonic() + 200
            while not (out / 'reply.json').exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Test runtime failed to return a tool receipt.')
                time.sleep(.03)
            reply = json.loads((out / 'reply.json').read_text(encoding='utf-8'))
            (out / 'reply.json').unlink()
            assert 'error' not in reply, reply
            return reply['value']

        with sync_playwright() as playwright, ThreadPoolExecutor(max_workers=1) as pool:
            browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=70)
            context = browser.new_context(no_viewport=True)
            context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept() if dialog.type == 'beforeunload' else dialog.dismiss())
            window = Window(page, context)
            shared.configure_visible_window(page, window)
            window.resize(1440, 900)
            window.activate()
            # The console's initial TOPMOST verification aid must not obscure
            # native dialogs owned by the separate frozen server process.
            console = ctypes.windll.kernel32.GetConsoleWindow()
            win32gui.SetWindowPos(console, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            page.goto(base, wait_until='load')

            def capture(name, native=None):
                if native:
                    shared.verify_dialog(native)
                else:
                    window.verify()
                photos.OUT = out
                photo, metadata = photos.shoter(name)
                metadata['foreground_title'] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                return photo, metadata

            capture('browser-waiting.png')
            print('BROWSER WAITING:', out / 'browser-waiting.png', flush=True)
            while not (out / 'browser-visible-confirmed').exists():
                page.wait_for_timeout(250)
            credentials = json.loads((out / 'credentials.json').read_text(encoding='utf-8'))
            page.locator('#id_username').fill(credentials['username'])
            page.locator('#id_password').fill(credentials['password'])
            page.locator('button[type="submit"]').click()
            page.wait_for_load_state('load')
            credentials = None
            page.goto(base + '/agent/agent/', wait_until='load')
            page.wait_for_function('window.TlamatiniInteractor?.clientId')
            editor = page.locator('#editor-container .cm-content')

            def checkpoint(name, passed=True, **details):
                window.activate()
                page.wait_for_timeout(250)
                assert not errors, errors
                photo, metadata = capture(f'{len(result["checks"])+1:02d}-{name}.png')
                row = {'name': name, 'passed': passed, 'photo': photo.name, 'details': details, 'foreground': metadata['foreground_title']}
                result['checks'].append(row)
                if not passed:
                    result['failures'].append(name)
                (out / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                (out / 'SUMMARY.html').write_text('<!doctype html><meta charset="utf-8"><title>Interactor runtime validation</title>'
                    '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}pre{white-space:pre-wrap}</style>'
                    + ''.join(f'<h2>{"PASS" if r["passed"] else "FAIL"}: {html.escape(r["name"])}</h2>'
                              f'<pre>{html.escape(json.dumps(r["details"], ensure_ascii=False))}</pre><img src="{r["photo"]}">'
                              for r in result['checks']), encoding='utf-8')
                print('PASS' if passed else 'FAIL', len(result['checks']), name, details, flush=True)

            def turn():
                page.evaluate('TlamatiniInteractor.beforeChat()')
                rpc({'method': 'turn', 'client': page.evaluate('TlamatiniInteractor.clientId')})

            def call(action, expect=True, during=None, **kwargs):
                future = pool.submit(rpc, {'method': 'call', 'args': dict(action=action, **kwargs)})
                if during:
                    during()
                while not future.done():
                    page.wait_for_timeout(40)
                reply = future.result()
                if expect is not None:
                    assert reply.get('ok') is expect, reply
                return reply

            def value():
                return page.evaluate('TlamatiniTextEditor.getText()')

            def edit(action, **kwargs):
                state = call('read')
                return call(action, document_id=state['document_id'], revision=state['revision'], **kwargs)

            turn()
            checkpoint('authenticated-live-editor', **proof)
            assets = {}
            for relative in ('interactor/bridge.js', 'vendor/canvas-editor/editor.js', 'js/agent_page_editing.js',
                             'js/agent_page_layout.js', 'css/canvas_editor.css'):
                response = context.request.get(base + '/static/agent/' + relative)
                assert response.ok, (relative, response.status)
                expected = (runtime / '_internal/staticfiles/agent' if args.frozen else ROOT / 'Tlamatini/agent/static/agent') / relative
                assert hashlib.sha256(response.body()).digest() == hashlib.sha256(expected.read_bytes()).digest()
                assets[relative] = hashlib.sha256(response.body()).hexdigest()
            checkpoint('served-assets-match-tested-runtime', hashes=assets)
            created = edit('new', filename='Dockerfile')
            target = Path(created['path'])
            assert target.is_relative_to(Path(proof['app_temp'])) and target.read_bytes() == b''
            edit('type', text='FROM ', typing_wpm=160)
            assert value() == 'FROM ' and target.read_bytes() == b''
            page.keyboard.press('Control+z')
            assert value() == ''
            page.keyboard.press('Control+y')
            assert value() == 'FROM '
            checkpoint('temp-file-visible-typing-and-single-undo')
            edit('guide', label='Java runtime image', hint='Choose the runtime image for your Java version.',
                 choices=[{'text': 'tomcat:10.1-jdk21-temurin', 'detail': 'Java 21 / Jakarta Servlet'}])
            editor.click()
            page.keyboard.press('Control+End')
            page.keyboard.type('tomcat:10', delay=100)
            page.locator('.tlm-interactor-ghost').wait_for()
            assert value() == 'FROM tomcat:10'
            page.keyboard.press('Tab')
            assert value() == 'FROM tomcat:10.1-jdk21-temurin'
            turn()
            fresh = call('read')
            assert fresh['text'] == value() and fresh['dirty'] and target.read_bytes() == b''
            checkpoint('local-completion-and-exact-unsaved-read')
            edit('save')
            assert target.read_text(encoding='utf-8') == value()
            checkpoint('tool-save-outside-Downloads')
            old = call('read')
            page.keyboard.type('\n# learner', delay=40)
            refusal = call('type', expect=False, text='stale', document_id=old['document_id'], revision=old['revision'])
            assert refusal['status'] == 'conflict' and value().endswith('# learner')
            turn()
            edit('save')
            checkpoint('stale-model-edit-preserves-learner-work')
            for filename, text, language in [('lesson.py', 'print("café 😀")\n', 'Python'),
                    ('lesson.json', '{"name":"日本語"}\n', 'JSON'), ('Servlet.java', 'class Servlet {}\n', 'Java'),
                    ('index.html', '<h1>Hello</h1>\n', 'HTML'), ('main.rs', 'fn main() {}\n', 'Rust'),
                    ('README.md', '# A lesson\n\n**Your choice**\n', 'Markdown')]:
                created = edit('new', filename=filename)
                edit('type', text=text, typing_wpm=160)
                live = call('read')
                assert live['text'] == text and live['language'] == language
                edit('save')
                assert Path(created['path']).read_text(encoding='utf-8') == text
                checkpoint('edit-read-save-' + language)
            page.locator('#markdown-preview-button').click()
            assert page.locator('#markdown-canvas-document h1').inner_text() == 'A lesson'
            edit('type', text='Next: ', typing_wpm=160)
            assert editor.is_visible() and value().endswith('Next: ')
            edit('save')
            checkpoint('Markdown-preview-and-AI-source-switch')
            destination = out / 'saved-outside-downloads.md'
            destination.unlink(missing_ok=True)
            win32gui.SetWindowPos(window.hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            page.locator('#canvas-save-as-button').click()
            shared.choose_native_save(page, window, destination, capture, 'native-save-dialog.png', suggested_name='README.md')
            page.wait_for_function('!TlamatiniCanvasEditing.busy')
            assert destination.read_text(encoding='utf-8') == value()
            window.activate()
            editor.click()
            page.keyboard.press('Control+End')
            page.keyboard.type('user field')
            menu_destination = out / 'menu-saved-outside-downloads.md'
            menu_destination.unlink(missing_ok=True)
            window.release()
            page.locator('#save-as-button').click()
            shared.choose_native_save(page, window, menu_destination, capture, 'menu-save-dialog.png',
                                      suggested_name=destination.name)
            page.wait_for_function('!TlamatiniCanvasEditing.dirty && !TlamatiniCanvasEditing.busy')
            destination = menu_destination
            assert destination.read_text(encoding='utf-8') == value()
            window.activate()
            editor.click()
            page.keyboard.press('Control+End')
            page.keyboard.type(' updated')
            page.keyboard.press('Control+s')
            page.wait_for_function('!TlamatiniCanvasEditing.dirty && !TlamatiniCanvasEditing.busy')
            assert destination.read_text(encoding='utf-8') == value()
            checkpoint('native-Save-As-menu-Save-and-Ctrl-S-persist-fresh-buffer')
            turn()
            before = value()
            def stop_typing():
                page.wait_for_function('(old) => TlamatiniTextEditor.getText() !== old', arg=before)
                page.locator('#interactor-stop').click()
            reply = edit('type', text='\n# Stop this long teaching segment immediately.', typing_wpm=100, expect=False, during=stop_typing)
            assert reply['status'] == 'aborted'
            stopped = value()
            page.wait_for_timeout(500)
            assert value() == stopped
            checkpoint('Stop-keeps-only-typed-prefix')
            turn()
            edit('save')
            edit('new', filename='service.yaml')
            away = context.new_page()
            away.set_content('<title>Interactor visibility test</title><h1>Checking editor pause/resume in the other tab</h1>')
            away.bring_to_front()
            page.wait_for_function('document.hidden', polling=100)
            assert not page.evaluate('!!Object.getOwnPropertyDescriptor(document,"hidden")')
            def return_after_absence():
                for remaining in (30, 20, 10):
                    print('REAL TAB ABSENCE:', remaining, 'seconds remaining', flush=True)
                    window.verify()
                    page.wait_for_timeout(10000)
                    assert value() == '', 'Typing must pause while the actual chat tab is hidden.'
                page.bring_to_front()
            reply = edit('type', text='kind: ', typing_wpm=160, expect=None, during=return_after_absence)
            checkpoint('temporary-tab-absence-resumes-exactly-once',
                       passed=reply.get('ok') is True and value() == 'kind: ', receipt=reply, actual=value())
            away.close()
            turn()
            if not value():
                edit('type', text='kind: ', typing_wpm=160)
            edit('save')
            window.resize(1060, 760)
            page.wait_for_timeout(500)
            geometry = page.evaluate('''() => {
                const canvas = document.getElementById('canvas-container').getBoundingClientRect();
                const editor = document.querySelector('#editor-container .cm-editor').getBoundingClientRect();
                const controls = ['canvas-save-button', 'interactor-access', 'clean-canvas-button', 'context-button']
                    .map(id => document.getElementById(id)).filter(Boolean).map(el => {
                        const r = el.getBoundingClientRect();
                        return {id: el.id, contained: r.left >= canvas.left && r.right <= canvas.right
                            && r.top >= canvas.top && r.bottom <= canvas.bottom};
                    });
                return {canvasWidth: canvas.width, editorHeight: editor.height, controls};
            }''')
            checkpoint('narrow-editor-controls-visible',
                       passed=geometry['canvasWidth'] >= 319 and geometry['editorHeight'] >= 120
                           and len(geometry['controls']) == 4 and all(c['contained'] for c in geometry['controls']),
                       geometry=geometry)
            page.locator('#drag-divider').focus()
            page.keyboard.press('ArrowLeft')
            chosen_split = page.locator('#canvas-container').evaluate('el => el.style.width')
            window.resize(1440, 900)
            page.wait_for_timeout(500)
            assert page.locator('#canvas-container').evaluate('el => el.style.width') == chosen_split
            checkpoint('manual-divider-choice-survives-resize', canvas_width=chosen_split)
            pdf = out / 'read-only.pdf'
            write_pdf(pdf, 'Read-only PDF is not a text document.', pages=1)
            native_open(page, window, pdf)
            page.wait_for_function('window.TlamatiniPdfCanvas?.active')
            turn()
            assert not call('read')['active']
            assert not edit('type', text='no', expect=False)['ok']
            checkpoint('PDF-remains-read-only-viewer')
            result['passed'] = not result['failures']
            print('FINAL RESULT:', mode, 'PASS' if result['passed'] else 'FAIL', len(result['checks']), 'checks', flush=True)
            print('BROWSER STAYS OPEN. Create close.confirmed to finish.', flush=True)
            (out / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            while not (out / 'close.confirmed').exists():
                page.wait_for_timeout(250)
            shared.dismiss_owned_dialogs(page, window)
            window.release()
            browser.close()
    except Exception:
        result['error'] = traceback.format_exc()
        result['passed'] = False
        traceback.print_exc()
        (out / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        raise
    finally:
        (out / 'stop-server').touch()
        import psutil
        try:
            owned_children = psutil.Process(process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            owned_children = []
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
        survivors = []
        for child in owned_children:
            try:
                if child.is_running():
                    child.terminate()
                    survivors.append(child)
            except psutil.NoSuchProcess:
                pass
        _, survivors = psutil.wait_procs(survivors, timeout=5)
        for child in survivors:
            child.kill()
        _, survivors = psutil.wait_procs(survivors, timeout=5)
        assert not survivors, 'A test-owned runtime child did not exit.'
        for path in (runtime / 'tlamatini.log', runtime / 'Tlamatini/tlamatini.log'):
            if path.exists():
                (out / 'application.log').write_bytes(path.read_bytes())
        (out / 'credentials.json').unlink(missing_ok=True)
        print('Owned runtime stopped; exit', process.returncode, flush=True)
    return 0 if result.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
