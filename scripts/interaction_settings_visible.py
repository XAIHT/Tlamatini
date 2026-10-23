# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Actual UI, editor and ConPTY acceptance. Run in a verified foreground console.

Chrome is explicitly headed. Inspect browser-waiting.png, then create
browser-visible-confirmed. Inspect final evidence before creating close.confirmed.
Uses a disposable database and the existing file-based runtime test driver.
"""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/interaction-settings-visible'


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    from markdown_canvas_visible import visible_console
    visible_console()
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('stop-server', 'reply.json', 'command.json', 'browser-visible-confirmed', 'close.confirmed'):
        (OUT / name).unlink(missing_ok=True)
    import canvas_editing_visible as shared
    shared.OUT = OUT
    sys.stdout = shared.LiveTranscript(sys.stdout)
    sys.stderr = shared.LiveTranscript(sys.stderr)
    driver = ROOT / 'scripts/interactor_runtime_server.py'
    expression = f'exec(compile(open({str(driver)!r}, encoding="utf-8").read(), {str(driver)!r}, "exec"))'
    base = 'http://127.0.0.1:8887'
    env = dict(os.environ, TLAMATINI_INTERACTOR_TEST_DIR=str(OUT), TLAMATINI_INTERACTOR_TEST_PORT='8887', TLAMATINI_NO_AUDIO='1')
    process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'Tlamatini/manage.py'), 'shell', '-c', expression], cwd=ROOT, env=env)
    result = {'checks': [], 'passed': False}
    try:
        for attempt in range(120):
            if process.poll() is not None:
                raise RuntimeError('Isolated test server exited during startup.')
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except Exception:
                if attempt % 10 == 0:
                    print('Waiting for isolated runtime...', flush=True)
                time.sleep(1)
        else:
            raise RuntimeError('Server startup timeout.')
        os.environ['NODE_OPTIONS'] = (os.environ.get('NODE_OPTIONS', '') + f' --require="{(ROOT / "scripts/playwright_real_visibility.cjs").as_posix()}"').strip()
        from playwright.sync_api import sync_playwright
        from chat_composer_visible_window import VisibleWindow
        import drag_divider_look_visible as photos
        import win32api
        import win32con
        import win32gui

        class Window(VisibleWindow):
            def verify(self):
                self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
                return super().verify()

        def rpc(frame):
            staged = OUT / 'command.tmp'
            staged.write_text(json.dumps(frame), encoding='utf-8')
            staged.replace(OUT / 'command.json')
            deadline = time.monotonic() + 200
            while not (OUT / 'reply.json').exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Runtime did not return a receipt.')
                time.sleep(.03)
            reply = json.loads((OUT / 'reply.json').read_text(encoding='utf-8'))
            (OUT / 'reply.json').unlink()
            assert 'error' not in reply, reply
            return reply['value']

        with sync_playwright() as playwright, ThreadPoolExecutor(max_workers=1) as pool:
            browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=50)
            context = browser.new_context(no_viewport=True)
            context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept() if dialog.type == 'beforeunload' else dialog.dismiss())
            window = Window(page, context)
            shared.configure_visible_window(page, window)
            window.resize(1440, 1000)
            window.activate()
            console = ctypes.windll.kernel32.GetConsoleWindow()
            win32gui.SetWindowPos(console, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            page.goto(base, wait_until='load')
            photos.OUT = OUT

            def capture(name):
                window.verify()
                return photos.shoter(name)

            capture('browser-waiting.png')
            print('BROWSER WAITING:', OUT / 'browser-waiting.png', flush=True)
            while not (OUT / 'browser-visible-confirmed').exists():
                page.wait_for_timeout(250)
            credentials = json.loads((OUT / 'credentials.json').read_text(encoding='utf-8'))
            page.locator('#id_username').fill(credentials['username'])
            page.locator('#id_password').fill(credentials['password'])
            page.locator('button[type="submit"]').click()
            page.wait_for_load_state('load')
            credentials = None
            page.goto(base + '/agent/agent/', wait_until='load')
            page.wait_for_function('window.TlamatiniInteractor?.clientId')
            page.evaluate('TlamatiniInteractionSettings.ready')

            def check(name, **details):
                window.activate()
                assert not errors, errors
                photo, _ = capture(f'{len(result["checks"]) + 1:02d}-{name}.png')
                result['checks'].append({'name': name, 'details': details, 'photo': photo.name})
                (OUT / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                print('PASS', name, details, flush=True)

            def call(frame, during=None):
                future = pool.submit(rpc, frame)
                if during:
                    during()
                while not future.done():
                    page.wait_for_timeout(40)
                return future.result()

            def turn():
                page.evaluate('TlamatiniInteractor.beforeChat()')
                call({'method': 'turn', 'client': page.evaluate('TlamatiniInteractor.clientId')})

            def edit(action, **kwargs):
                state = call({'method': 'call', 'args': {'action': 'read'}})
                during = kwargs.pop('during', None)
                return call({'method': 'call', 'args': {'action': action, 'document_id': state.get('document_id'), 'revision': state.get('revision'), **kwargs}}, during)

            def settings(values=None, tab='editor', save=True):
                page.evaluate('(tab) => TlamatiniInteractionSettings.open(tab)', tab)
                page.wait_for_function('!document.getElementById("interaction-settings-save").disabled')
                for key, value in (values or {}).items():
                    field = page.locator('#interaction-' + key)
                    # Activate the actual tab and advanced section containing this control.
                    owner = field.evaluate('el => el.closest("[role=tabpanel]").id.replace("interaction-panel-", "")')
                    page.locator('#interaction-tab-' + owner).click()
                    field.evaluate('el => { const details=el.closest("details"); if(details) details.open=true; }')
                    if isinstance(value, bool):
                        field.set_checked(value)
                    elif field.evaluate('el => el.tagName') == 'SELECT':
                        field.select_option(str(value))
                    else:
                        field.fill(str(value))
                if save:
                    page.locator('#interaction-settings-save').click()
                    page.locator('#interaction-settings-overlay').wait_for(state='hidden')

            settings(save=False)
            page.locator('#interaction-preset').select_option('standard')
            page.locator('#interaction-settings-save').click()
            page.locator('#interaction-settings-overlay').wait_for(state='hidden')
            settings({'editor_wpm': 60, 'segment_pause': 1, 'teaching_detail': 'detailed', 'suggestions': False,
                      'follow_typing': False, 'editor_font': 18, 'line_numbers': False, 'wrap': True})
            page.reload(wait_until='load')
            page.wait_for_function('window.TlamatiniInteractor?.clientId')
            page.evaluate('TlamatiniInteractionSettings.ready')
            assert page.evaluate('TlamatiniInteractionSettings.snapshot().editor_wpm') == 60
            check('saved-settings-survive-reload')
            settings({'editor_wpm': 150}, save=False)
            page.keyboard.press('Escape')
            assert page.locator('#interaction-settings-overlay').is_hidden()
            assert page.evaluate('TlamatiniInteractionSettings.snapshot().editor_wpm') == 60
            check('Escape-discards-draft')
            turn()
            assert edit('new', filename='interaction-settings.py')['ok']
            start = time.monotonic()
            reply = edit('type', text='# demo', typing_wpm=160)
            elapsed = time.monotonic() - start
            assert reply['ok'] and elapsed >= 2, (reply, elapsed)
            assert page.evaluate('TlamatiniTextEditor.getText()') == '# demo'
            assert page.locator('.cm-lineNumbers').evaluate('el => getComputedStyle(el).display') == 'none', page.evaluate('({preferences:TlamatiniInteractionSettings.snapshot(), gutter:document.querySelector(".cm-lineNumbers").outerHTML})')
            assert page.locator('.cm-editor').evaluate('el => getComputedStyle(el).fontSize') == '18px'
            assert page.locator('.cm-content').evaluate('el => getComputedStyle(el).whiteSpace') in ('pre-wrap', 'break-spaces')
            check('real-editor-speed-pause-and-appearance', elapsed=round(elapsed, 2))
            guide = edit('guide', label='Example', hint='Choose a value', choices=[{'text': 'example', 'detail': 'test'}])
            assert guide['ok']
            check('guide-with-suggestions-disabled')
            settings({'suggestions': True, 'suggestion_display': 'choices', 'segment_pause': 0, 'editor_wpm': 160})
            turn()
            edit('guide', label='Example', hint='Choose a value', choices=[{'text': 'example', 'detail': 'test'}])
            page.locator('#editor-container .cm-content').click()
            page.keyboard.press('Control+End')
            page.keyboard.type('e')
            assert page.locator('.tlm-interactor-ghost').count() == 0
            check('choices-without-ghost-text')
            settings({'terminal_wpm': 160, 'shell': 'cmd', 'execution': 'manual', 'advisor': False,
                      'hang_seconds': 60, 'user_wait_seconds': 120, 'wait_seconds': 10,
                      'terminal_font': 17, 'cursor_style': 'bar', 'cursor_blink': False, 'terminal_layout': 'tile-v'})
            opened = call({'method': 'terminal', 'action': 'open', 'params': {'title': 'Settings acceptance', 'use_my_defaults': True}})
            assert opened['ok'], opened
            tid = opened['terminal_id']
            page.wait_for_function('id => TlamatiniTerminals.state().terminals.some(t => t.id === id && t.state === "prompt" && t.cols > 0)', arg=tid)
            page.wait_for_timeout(1200)  # Let initial xterm fitting/ConPTY resize settle.
            check('configured-terminal-opened', state=page.evaluate('TlamatiniTerminals.state()'))
            assert page.evaluate('TlamatiniTerminals.state().layout') == 'tile-v'
            typed = call({'method': 'terminal', 'action': 'run', 'params': {'terminal': tid, 'text': 'echo SETTINGS_OK', 'submit': True, 'use_my_defaults': True}})
            capture('terminal-typed.png')
            assert typed['status'] == 'typed' and not typed['enter_pressed'], typed
            actual = call({'method': 'terminal_settings', 'terminal': tid})
            assert actual == {'hang_seconds': 60, 'user_wait_seconds': 120, 'advisor': False, 'kind': 'cmd'}, actual
            check('real-CMD-manual-Enter-and-server-preferences', receipt=typed, settings=actual)
            page.locator('.xterm-helper-textarea').last.focus()
            page.keyboard.press('Enter')
            completed = call({'method': 'terminal', 'action': 'wait', 'params': {'terminal': tid, 'wait_seconds': 10}})
            assert completed['status'] == 'completed' and 'SETTINGS_OK' in completed.get('output', ''), completed
            check('user-Enter-executes-command', receipt=completed)
            settings({'narrate_terminal': True, 'narrate_editor': True, 'narration_content': 'both', 'narration_when': 'before', 'narration_wait': True})
            # Real OS synthesis. Instrument completion without replacing the speech engine.
            page.evaluate('''() => {
                TLM_VOICE.saveSettings({...TLM_VOICE.loadSettings(), mode:'all'});
                window.voiceReceipts=[];
                const real=TLM_VOICE.speak;
                TLM_VOICE.speak=async (...args)=>{ const status=await real(...args); voiceReceipts.push(status); return status; };
            }''')
            settings(tab='voice', save=False)
            page.locator('#interaction-preview-button').click()
            page.wait_for_function('voiceReceipts.length > 0', timeout=110000)
            speech = page.evaluate('voiceReceipts')
            check('real-OS-voice-preview', receipts=speech)
            page.locator('#interaction-settings-cancel').click()
            page.evaluate("TLM_VOICE.setSilent(true)")
            turn()
            reply = edit('type', text=' muted', explanation='This should remain silent.')
            assert reply['ok'], reply
            assert page.evaluate('voiceReceipts.at(-1)') == 'muted'
            check('global-mute-overrides-narration')
            # Explicit fault injection verifies cancellation UI, separate from real audio above.
            page.evaluate("window.realVoiceSpeak=TLM_VOICE.speak; TLM_VOICE.speak=async()=> 'unavailable'; TLM_VOICE.setSilent(false)")
            turn()
            old = page.evaluate('TlamatiniTextEditor.getText()')
            def stop_narration():
                page.get_by_role('button', name='Stop this step', exact=True).click()
            reply = edit('type', text=' MUST_NOT_TYPE', during=stop_narration)
            assert not reply['ok'] and page.evaluate('TlamatiniTextEditor.getText()') == old, reply
            page.evaluate('TLM_VOICE.speak=realVoiceSpeak; TLM_VOICE.setSilent(true)')
            check('unavailable-voice-Stop-prevents-editor-mutation')
            settings(tab='terminal', save=False)
            window.resize(1060, 760)
            bounds = page.locator('#interaction-settings-form').bounding_box()
            viewport = page.evaluate('({width:innerWidth,height:innerHeight})')
            assert bounds['x'] >= 0 and bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= viewport['height']
            assert page.locator('#interaction-settings-save').is_visible()
            check('narrow-dialog-contained-with-visible-actions', bounds=bounds)
            page.locator('#interaction-settings-cancel').click()
            window.resize(1440, 1000)
            # An actual terminal narration receipt must precede its first key.
            settings({'narration_content': 'explanation', 'execution': 'manual', 'announce_outcomes': 'off'})
            page.evaluate('voiceReceipts=[]; TLM_VOICE.setSilent(false)')
            def before_first_key():
                page.wait_for_function('speechSynthesis.speaking', timeout=10000)
                assert 'VOICE_OK' not in page.evaluate('(id)=>TlamatiniTerminals.textOf(id)', tid)
            narrated = call({'method': 'terminal', 'action': 'run', 'params': {'terminal': tid, 'text': 'echo VOICE_OK',
                             'explanation': 'I will prepare a short command. You can read it before pressing Enter.', 'use_my_defaults': True}}, before_first_key)
            assert narrated['status'] == 'typed' and not narrated['enter_pressed'], narrated
            assert 'spoken' in page.evaluate('voiceReceipts')
            check('terminal-waits-for-real-voice-before-first-key', receipt=narrated)
            page.locator('.xterm-helper-textarea').last.focus()
            page.keyboard.press('Enter')
            call({'method': 'terminal', 'action': 'wait', 'params': {'terminal': tid, 'wait_seconds': 10}})
            page.evaluate("TLM_VOICE.setSilent(true)")
            settings({'editor_wpm': 999}, save=False)
            page.locator('#interaction-tab-voice').click()
            page.locator('#interaction-settings-save').click()
            assert page.locator('#interaction-tab-editor').get_attribute('aria-selected') == 'true'
            assert page.locator('#interaction-settings-overlay').is_visible()
            page.locator('#interaction-settings-reset').click()
            assert page.locator('#interaction-editor_wpm').input_value() == '100'
            page.locator('#interaction-preset').select_option('guided')
            assert page.locator('#interaction-editor_wpm').input_value() == '60'
            page.locator('#interaction-settings-cancel').click()
            check('validation-reveals-tab-and-presets-remain-drafts')
            call({'method': 'terminal', 'action': 'kill', 'params': {'terminal': tid}})
            page.locator('#config-menu-button').click()
            page.locator('#config-interaction').click()
            page.locator('#interaction-editor_wpm').wait_for()
            check('main-Config-menu-opens-dialog')
            page.locator('#interaction-settings-cancel').click()
            for panel in ('agentic_control_panel', 'prompt_flow_panel'):
                page.goto(base + '/agent/' + panel + '/', wait_until='load')
                page.evaluate('TlamatiniInteractionSettings.ready')
                settings(tab='voice', save=False)
                assert page.locator('#interaction-toggle-mute').is_visible()
                check(panel + '-shares-settings-and-voice')
                page.locator('#interaction-settings-cancel').click()
            result['passed'] = True
            (OUT / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print('FINAL PASS:', len(result['checks']), 'checks. Browser stays open until close.confirmed.', flush=True)
            while not (OUT / 'close.confirmed').exists():
                page.wait_for_timeout(250)
            window.release()
            browser.close()
    except Exception:
        result['error'] = traceback.format_exc()
        (OUT / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        traceback.print_exc()
        raise
    finally:
        (OUT / 'stop-server').touch()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)
        (OUT / 'credentials.json').unlink(missing_ok=True)
        print('Isolated runtime stopped:', process.returncode, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
