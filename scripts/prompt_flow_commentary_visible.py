# Tlamatini Author Banner — Angela López Mendoza
"""Static commentary / unchanged user-input regression in real visible Chrome.

Launch from a verified foreground PowerShell -NoExit console. Uses a separate
normal source installation, real login/HTTP/WebSocket, and Shoter desktop photos.
No headless mode, transport interception or injected editor state. The browser
visibility photo must be reviewed before creating browser.confirmed. Successful
checks leave Chrome and the test server open for inspection until close.confirmed.

Launch it in a classic console (conhost.exe): inside Windows Terminal the console
handle is a hidden pseudo-console window, so the foreground gate below refuses.
Chrome itself can crash at the checkpoint 5 download (2026-10-03: three Crashpad
dumps in the test profile, one per failed run); a run without the crash passed
9/9. Treat that crash as inconclusive and re-run; never count it as a pass.
"""
from __future__ import annotations

import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible
from prompt_flow_connections_visible import require_browser_foreground

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/prompt-commentary-visible'
visible.OUT = OUT
visible.RUNTIME = OUT / 'runtime'
BASE = visible.BASE


def main():
    if any('headless' in arg for arg in sys.argv[1:]):
        raise SystemExit('Headless execution is forbidden.')
    OUT.mkdir(parents=True, exist_ok=True)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    console = kernel32.GetConsoleWindow()
    if not console or not user32.IsWindowVisible(console) or user32.IsIconic(console) or user32.GetForegroundWindow() != console:
        raise SystemExit('A visible foreground development console is required; refusing execution.')
    visible.photograph('console-visible')
    before = visible.listeners()
    if any(port in before for port in (8001, 8766, 50052)):
        raise SystemExit('Test ports occupied; refusing to replace an existing server.')
    original = visible.read_discovery()
    (OUT / 'login.json').write_text(json.dumps({'username': 'user', 'password': 'changeme'}), encoding='utf-8')
    server = None
    results = []
    outcome = 1
    try:
        env, credentials = visible.prepare_runtime()
        # Refresh only this isolated test installation on a repeat run.
        for path in ('agent/services/prompt_flow_panel.py', 'agent/test_prompt_flow_panel.py',
                     'agent/test_prompt_flow_panel_websocket.py', 'agent/management/commands/check_prompt_flow_panel.py',
                     'agent/static/agent/js/prompt-flow-panel-model.js', 'agent/static/agent/js/prompt-flow-panel.js',
                     'agent/static/agent/css/prompt_flow_panel.css', 'agent/templates/agent/prompt_flow_panel.html',
                     'tlamatini/settings.py'):
            shutil.copy2(ROOT / 'Tlamatini' / path, visible.RUNTIME / 'Tlamatini' / path)
        for path in ('docs/examples/prompting-kickoff.fpmt', 'docs/prompting-flow-designer.md'):
            dest = visible.RUNTIME / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, dest)
        for command in (
            ['test', 'agent.test_prompt_flow_panel_runtime', 'agent.test_prompt_flow_panel_websocket', 'agent.test_chain_readiness', '--noinput'],
            ['check_prompt_flow_panel'], ['collectstatic', '--noinput'],
        ):
            if '--resume' in sys.argv and command[0] != 'collectstatic':
                continue
            print('VISIBLE CHECK:', ' '.join(command), flush=True)
            subprocess.run([sys.executable, '-u', 'Tlamatini/manage.py', *command], cwd=visible.RUNTIME, env=env, check=True)
        server = visible.start_server(env)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError('Test server exited: ' + str(server.returncode))
            try:
                with urllib.request.urlopen(BASE, timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError):
                time.sleep(1)
        else:
            raise TimeoutError('Test server did not become ready.')
        visible.restore_discovery(original)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(OUT / 'chrome-profile-containment'), channel='chrome', headless=False,
                chromium_sandbox=True, no_viewport=True, slow_mo=100,
                accept_downloads=True, args=['--start-maximized'])
            page = context.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())
            page.on('close', lambda: print('Visible test page closed.', flush=True))
            page.goto(BASE)
            page.bring_to_front()
            visible.visibility_gate('browser', page)
            require_browser_foreground(page)
            page.goto(BASE + '/agent/prompt_flow_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type=submit], input[type=submit]').first.click()
                page.goto(BASE + '/agent/prompt_flow_panel/')
            credentials.clear()
            expect(page.locator('.agent-tool-item')).to_have_count(8)

            def checkpoint(name):
                require_browser_foreground(page)
                visible.photograph(name)
                results.append(name)
                (OUT / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, flush=True)

            def menu(action):
                page.get_by_role('button', name='File', exact=True).click()
                page.locator('.dropdown-menu [data-action="' + action + '"]').first.click()
                accept = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
                if accept.is_visible():
                    accept.click()

            def save(name):
                menu('save')
                page.locator('#pmt-field-filename').fill(name)
                with page.expect_download() as downloaded:
                    page.get_by_role('button', name='Download .fpmt', exact=True).click()
                path = OUT / name
                downloaded.value.save_as(path)
                return path, json.loads(path.read_text(encoding='utf-8'))

            def open_file(path):
                page.get_by_role('button', name='File', exact=True).click()
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="open"]').click()
                chooser.value.set_files(str(path))
                accept = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
                if accept.is_visible():
                    accept.click()

            def center(locator):
                require_browser_foreground(page)
                box = locator.bounding_box()
                return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2

            menu('new')
            page.locator('[data-action="fit"]').click()
            expect(page.locator('.agent-tool-item')).to_have_count(8)
            expect(page.locator('.agent-tool-item[data-type="user_input"]')).to_have_text('User Input')
            expect(page.locator('.agent-tool-item[data-type="user_commentary"]')).to_have_text('User Commentary')
            css = page.locator('link[href*="prompt_flow_panel.css"]').get_attribute('href')
            assert '-prompt-commentary-input-1' in css
            assert page.request.get(BASE + css).body() == (ROOT / 'Tlamatini/agent/static/agent/css/prompt_flow_panel.css').read_bytes()
            checkpoint('01-palette-and-served-assets')
            page.locator('.agent-tool-item[data-type="user_commentary"]').click()
            comment = page.locator('.pmt-node[data-type="user_commentary"]')
            expect(comment.locator('.pmt-port')).to_have_count(0)
            expect(page.locator('#pmt-play')).to_be_disabled()
            expect(page.locator('#pmt-start option')).to_have_count(1)
            paragraph = ('Review paragraph: ñ <script> literal {{last_output}}. This note stays on the canvas.\n\n' * 60).rstrip()
            comment.dblclick(position={'x': 70, 'y': 55})
            editor = page.get_by_role('textbox', name='Static User Commentary text')
            expect(editor).to_be_visible()
            editor.fill(paragraph)
            assert editor.evaluate('(el) => el.scrollHeight <= el.clientHeight + 2'), 'Editor must grow while typing'
            expect(editor).to_have_css('overflow-y', 'hidden')
            editor.press('Control+Enter')
            expect(comment.locator('.pmt-comment-text')).to_have_text(paragraph)
            assert comment.locator('.pmt-comment-text script').count() == 0
            assert comment.locator('.pmt-comment-text').evaluate('(el) => el.scrollHeight <= el.clientHeight'), 'Long note must fit without scrolling'
            assert float(comment.get_attribute('style').split('height: ')[1].split('px')[0]) > 200
            checkpoint('02-in-place-long-literal-note')
            comment.focus()
            comment.press('Enter')
            editor.fill('Cancelled replacement')
            editor.press('Escape')
            expect(comment.locator('.pmt-comment-text')).to_have_text(paragraph)
            # A compact review note lets the whole manually resized bubble be inspected.
            paragraph = 'Review note: Keep the runtime User Input separate from this static commentary.\n\nThe bubble contains the complete text and grows when the font or content needs more room.'
            comment.focus()
            comment.press('Enter')
            editor.fill(paragraph)
            editor.press('Control+Enter')
            page.locator('[data-action="configure"]').click()
            page.locator('#pmt-field-color').select_option('#dbeafe')
            page.locator('#pmt-field-font_family').select_option('Georgia')
            page.locator('#pmt-field-font_size').fill('21')
            page.locator('#pmt-field-width').fill('500')
            page.locator('#pmt-field-height').fill('320')
            page.locator('#pmt-field-bold').check()
            page.locator('#pmt-field-italic').check()
            page.locator('#pmt-field-align').select_option('right')
            page.get_by_role('button', name='Save', exact=True).click()
            expect(comment).to_have_css('width', '500px')
            expect(comment.locator('.pmt-comment-text')).to_have_css('font-size', '21px')
            expect(comment.locator('.pmt-comment-text')).to_have_css('font-style', 'italic')
            expect(comment.locator('.pmt-shape')).to_have_css('fill', 'rgb(219, 234, 254)')
            expect(comment.locator('.pmt-comment-text')).to_have_css('overflow-y', 'hidden')
            assert comment.locator('.pmt-comment-text').evaluate('(el) => el.scrollHeight <= el.clientHeight')
            checkpoint('03-font-color-size-and-cancel')
            page.locator('[data-action="zoom-out"]').click()
            handle = comment.locator('.pmt-comment-resize')
            x, y = center(handle)
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 90, y + 72, steps=8)
            page.mouse.up()
            expect(comment).to_have_css('width', '600px')
            expect(comment).to_have_css('height', '400px')
            page.locator('[data-action="undo"]').click()
            expect(comment).to_have_css('width', '500px')
            page.locator('[data-action="redo"]').click()
            expect(comment).to_have_css('width', '600px')
            checkpoint('04-zoom-aware-resize-undo-redo')
            page.locator('[data-action="duplicate"]').click()
            expect(comment).to_have_count(2)
            page.locator('#submonitor-container').focus()
            page.keyboard.press('ArrowDown')
            page.keyboard.press('Shift+ArrowDown')
            page.keyboard.press('Shift+ArrowDown')
            page.keyboard.press('Shift+ArrowDown')
            page.keyboard.press('Shift+ArrowDown')
            page.keyboard.press('Shift+ArrowDown')
            page.locator('[data-action="fit"]').click()
            portable, payload = save('commentaries.fpmt')
            assert payload['version'] == 2 and payload['start'] is None and payload['edges'] == []
            assert len(payload['nodes']) == 2
            assert all(n['config']['text'] == paragraph and n['config']['font_family'] == 'Georgia' for n in payload['nodes'])
            open_file(portable)
            expect(comment).to_have_count(2)
            page.wait_for_timeout(500)
            page.reload()
            expect(comment).to_have_count(2)
            checkpoint('05-multiple-notes-file-and-draft-roundtrip')
            # Keep the static notes, then add real input/history-clear operations.
            page.locator('.agent-tool-item[data-type="user_input"]').click()
            page.locator('#submonitor-container').focus()
            for _ in range(18):
                page.keyboard.press('Shift+ArrowRight')
            page.locator('.agent-tool-item[data-type="clean_history"]').click()
            page.locator('#submonitor-container').focus()
            for _ in range(26):
                page.keyboard.press('Shift+ArrowRight')
            page.locator('[data-action="fit"]').click()
            input_node = page.locator('.pmt-node[data-type="user_input"]')
            clear_node = page.locator('.pmt-node[data-type="clean_history"]')
            source = input_node.locator('.output-triangle')
            target = clear_node.locator('.input-triangle')
            page.mouse.move(*center(source))
            page.mouse.down()
            page.mouse.move(*center(target), steps=8)
            page.mouse.up()
            expect(page.locator('.pmt-edge')).to_have_count(1)
            expect(page.locator('#pmt-start option')).to_have_count(2)
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            expect(page.locator('.ui-dialog-title')).to_have_text('User Input')
            page.locator('#pmt-field-reply').fill('Same runtime reply: ñ ✓')
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            expect(page.locator('#pmt-run-log')).to_contain_text('Same runtime reply: ñ ✓')
            expect(comment.locator('.pmt-node-status')).to_have_count(0)
            checkpoint('06-real-user-input-playback-with-static-notes')
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('#pmt-run-state')).to_have_text('stopped', timeout=30000)
            checkpoint('07-user-input-escape-stops-flow')
            legacy = {'format': 'tlamatini-prompting-flow', 'version': 1, 'name': 'Legacy reply flow',
                      'start': 'old', 'max_steps': 20, 'nodes': [
                          {'id': 'old', 'type': 'user_commentary', 'label': 'User Commentary', 'x': 70, 'y': 60, 'config': {'text': 'Legacy request'}},
                      ], 'edges': []}
            legacy_path = OUT / 'legacy.fpmt'
            legacy_path.write_text(json.dumps(legacy), encoding='utf-8')
            open_file(legacy_path)
            expect(input_node).to_have_count(1)
            expect(comment).to_have_count(0)
            expect(input_node.locator('.pmt-node-label')).to_have_text('User Input')
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            page.locator('#pmt-field-reply').fill('Legacy mechanism preserved')
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            _, migrated = save('migrated.fpmt')
            assert migrated['version'] == 2 and migrated['nodes'][0]['type'] == 'user_input'
            checkpoint('08-legacy-input-migration-and-playback')
            open_file(ROOT / 'docs/examples/prompting-kickoff.fpmt')
            expect(page.locator('.pmt-node')).to_have_count(8)
            page.locator('[data-action="fit"]').click()
            checkpoint('09-bundled-eight-asset-example')
            assert not errors, errors
            outcome = 0
            (OUT / 'summary.json').write_text(json.dumps({'exit_code': 0, 'checks': results,
                'mocked_transports': False, 'model_called': False, 'browser_visible': True}, indent=2), encoding='utf-8')
            print('ALL COMMENTARY CHECKS PASSED. EXIT_CODE=0. Chrome stays open for inspection.', flush=True)
            print('Create close.confirmed to close this test session when finished inspecting.', flush=True)
            while not (OUT / 'close.confirmed').exists():
                page.wait_for_timeout(1000)
            context.close()
    except Exception:
        traceback.print_exc()
        try:
            visible.photograph('failure')
        except Exception:
            traceback.print_exc()
    finally:
        visible.stop_server(server)
        visible.restore_discovery(original)
        if outcome:
            (OUT / 'summary.json').write_text(json.dumps({'exit_code': outcome, 'checks': results}, indent=2), encoding='utf-8')
        print('COMMENTARY TEST EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
