# Tlamatini Author Banner — Angela López Mendoza
"""Run output splitter regression in real visible Chrome.

Launch from a verified foreground PowerShell -NoExit console. Uses a separate
normal source installation, real login/HTTP/WebSocket, and Shoter desktop photos.
No headless mode, transport interception or injected editor state. The foreground window gate verifies real Chrome visibility. Successful
checks leave Chrome and the test server open for inspection until close.confirmed.

Launch it in a classic console (conhost.exe): inside Windows Terminal the console
handle is a hidden pseudo-console window, so the foreground gate below refuses.
"""
from __future__ import annotations

import ctypes
import json
import secrets
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
OUT = ROOT / 'Temp/run-output-resize-visible'
visible.OUT = OUT
visible.RUNTIME = ROOT / 'Temp/prompt-commentary-visible/runtime'
BASE = visible.BASE


def main():
    if any('headless' in arg for arg in sys.argv[1:]):
        raise SystemExit('Headless execution is forbidden.')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'close.confirmed').unlink(missing_ok=True)
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
    (OUT / 'login.json').write_text(json.dumps({'username': 'user', 'password': secrets.token_urlsafe(32)}), encoding='utf-8')
    server = None
    results = []
    (OUT / 'checks.json').write_text('[]', encoding='utf-8')
    outcome = 1
    try:
        env, credentials = visible.prepare_runtime()
        if '--resume' in sys.argv:
            # Rotate only the isolated test account, avoiding Chrome's breached-password modal.
            subprocess.run([sys.executable, '-u', 'Tlamatini/manage.py', 'shell', '-c',
                'import os; from django.contrib.auth import get_user_model; '
                'u = get_user_model().objects.get(username="user"); '
                'u.set_password(os.environ["TLAMATINI_COMMENT_TEST_PASSWORD"]); u.save(update_fields=["password"])'],
                cwd=visible.RUNTIME, env={**env, 'TLAMATINI_COMMENT_TEST_PASSWORD': credentials['password']}, check=True)
        # Refresh only this isolated test installation on a repeat run.
        for path in ('agent/services/prompt_flow_panel.py', 'agent/test_prompt_flow_panel.py',
                     'agent/test_prompt_flow_panel_websocket.py', 'agent/management/commands/check_prompt_flow_panel.py',
                     'agent/static/agent/js/flow-canvas-interactions.js', 'agent/static/agent/js/prompt-flow-panel-model.js', 'agent/static/agent/js/prompt-flow-panel.js',
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
        # This isolated profile must not cover the actual controls with Chrome's password bubble.
        profile = OUT / ('chrome-profile-' + str(time.time_ns()))
        preferences = profile / 'Default/Preferences'
        preferences.parent.mkdir(parents=True, exist_ok=True)
        prefs = json.loads(preferences.read_text(encoding='utf-8')) if preferences.exists() else {}
        prefs['credentials_enable_service'] = False
        prefs.setdefault('profile', {})['password_manager_enabled'] = False
        preferences.write_text(json.dumps(prefs), encoding='utf-8')
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile), channel='chrome', headless=False,
                chromium_sandbox=True, no_viewport=True, slow_mo=100,
                accept_downloads=True, args=['--start-maximized'])
            page = context.pages[0]
            errors = []
            def page_error(error):
                errors.append(str(error))
                print('BROWSER SCRIPT ERROR:', error, flush=True)
            page.on('pageerror', page_error)
            page.on('dialog', lambda dialog: dialog.accept())
            page.on('close', lambda: print('Visible test page closed.', flush=True))
            page.goto(BASE)
            page.bring_to_front()
            require_browser_foreground(page)
            visible.photograph('browser-visible')
            page.goto(BASE + '/agent/prompt_flow_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type=submit], input[type=submit]').first.click()
                page.goto(BASE + '/agent/prompt_flow_panel/')
            credentials.clear()
            expect(page.locator('.agent-tool-item')).to_have_count(8)
            expect(page.locator('[data-action="reconnect"]')).to_be_disabled()
            page.wait_for_load_state('networkidle')
            page.bring_to_front()
            require_browser_foreground(page)
            visible.photograph('panel-ready')


            def checkpoint(name):
                require_browser_foreground(page)
                visible.photograph(name)
                results.append(name)
                (OUT / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, flush=True)

            def open_file(path):
                page.get_by_role('button', name='File', exact=True).click()
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="open"]').click()
                chooser.value.set_files(str(path))

            fixture = json.loads((ROOT / 'docs/examples/prompting-kickoff.fpmt').read_text(encoding='utf-8'))
            fixture.update(name='Run output resizing demonstration', start='input', max_steps=10)
            fixture['nodes'] = [
                {'id': 'input', 'type': 'user_input', 'label': 'Review notes', 'x': 80, 'y': 80,
                 'config': {'text': 'Enter review notes to demonstrate the scrollable output.'}},
                {'id': 'clean', 'type': 'clean_history', 'label': 'Finish review', 'x': 540, 'y': 80, 'config': {'text': ''}},
            ]
            fixture['edges'] = [{'id': 'next', 'source': 'input', 'target': 'clean', 'branch': 'next'}]
            original_note = json.loads((ROOT / 'docs/examples/prompting-kickoff.fpmt').read_text(encoding='utf-8'))['nodes'][-1]
            for index, (x, y, color) in enumerate(((80, 320, '#fef3c7'), (850, 320, '#dbeafe'), (80, 1100, '#dcfce7'))):
                note = json.loads(json.dumps(original_note))
                note.update(id='note-' + str(index), x=x, y=y)
                note['config'].update(color=color)
                fixture['nodes'].append(note)
            fixture_path = OUT / 'resize-demo.fpmt'
            fixture_path.write_text(json.dumps(fixture, ensure_ascii=False), encoding='utf-8')
            open_file(fixture_path)
            expect(page.locator('.pmt-node')).to_have_count(5)
            page.locator('#pmt-play').click()
            reply = '\n'.join('Review line %02d — Keep text readable at every pane height.' % i for i in range(1, 81))
            page.locator('#pmt-field-reply').fill(reply)
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            expect(page.locator('#pmt-run-log')).to_contain_text('Review line 80')
            divider = page.locator('#pmt-output-divider')
            canvas = page.locator('#submonitor-container')
            output = page.locator('#pmt-run-log')
            panel = page.locator('#pmt-run-panel')

            def dimensions():
                return page.evaluate('''() => {
                    const byId = id => document.getElementById(id), c = byId('submonitor-container'), p = byId('pmt-run-panel'), l = byId('pmt-run-log');
                    return {canvas: c.getBoundingClientRect().height, output: p.getBoundingClientRect().height,
                        percent: Number(byId('pmt-output-divider').getAttribute('aria-valuenow')),
                        canvasScroll: c.scrollTop, outputScroll: l.scrollTop,
                        canvasWidth: c.clientWidth, canvasHeight: c.clientHeight,
                        canvasScrollWidth: c.scrollWidth, canvasScrollHeight: c.scrollHeight,
                        outputHeight: l.clientHeight, outputScrollHeight: l.scrollHeight,
                        zoom: byId('pmt-zoom').textContent, transform: byId('pmt-world').style.transform,
                        outputText: l.textContent, outputFont: getComputedStyle(l).fontSize,
                        nodes: [...document.querySelectorAll('.pmt-node')].map(n => ({id: n.dataset.nodeId, left: n.style.left, top: n.style.top,
                            width: n.getBoundingClientRect().width, height: n.getBoundingClientRect().height,
                            runs: [...n.querySelectorAll('[data-comment-run]')].map(r => [r.textContent, getComputedStyle(r).fontFamily, getComputedStyle(r).fontSize])}))};
                }''')

            baseline = dimensions()
            def unchanged():
                actual = dimensions()
                for key in ('zoom', 'transform', 'outputText', 'outputFont', 'nodes'):
                    assert actual[key] == baseline[key], ('Resizing changed content', key)
                expect(page.locator('[data-action="undo"]')).to_be_disabled()
                return actual

            def ratio(expected):
                current = unchanged()
                actual = current['output'] / (current['canvas'] + current['output']) * 100
                assert abs(actual - expected) < .15, (expected, actual, current)
                assert current['percent'] == expected
                return current

            def drag_to(percent):
                require_browser_foreground(page)
                rect = divider.bounding_box()
                box = page.locator('#pmt-workspace').bounding_box()
                current = dimensions()
                target_y = box['y'] + box['height'] - (current['canvas'] + current['output']) * percent / 100 - rect['height'] / 2
                x = rect['x'] + rect['width'] / 2
                print('DEMONSTRATING: drag Run output to', percent, 'percent', flush=True)
                page.mouse.move(x, rect['y'] + rect['height'] / 2)
                page.mouse.down()
                page.mouse.move(x, max(1, min(page.evaluate('innerHeight') - 1, target_y)), steps=30)
                page.mouse.up()
                page.wait_for_timeout(1200)

            css_url = page.locator('link[href*="prompt_flow_panel.css"]').get_attribute('href')
            assert '-prompt-run-output-resize-1' in css_url
            for asset, filename in (('link[href*="prompt_flow_panel.css"]', 'css/prompt_flow_panel.css'),
                                    ('script[src*="flow-canvas-interactions.js"]', 'js/flow-canvas-interactions.js'),
                                    ('script[src*="prompt-flow-panel.js"]', 'js/prompt-flow-panel.js')):
                locator = page.locator(asset)
                url = locator.get_attribute('href') or locator.get_attribute('src')
                assert page.request.get(BASE + url).body() == (ROOT / 'Tlamatini/agent/static/agent' / filename).read_bytes()
            ratio(20)
            checkpoint('01-real-playback-default-layout-and-served-assets')
            drag_to(50)
            ratio(50)
            checkpoint('02-drag-half-height-preserves-content')
            drag_to(95)
            ratio(95)
            checkpoint('03-drag-95-percent-output')
            drag_to(110)
            ratio(95)
            checkpoint('04-upper-limit-clamped')
            drag_to(5)
            ratio(5)
            checkpoint('05-drag-5-percent-output')
            drag_to(-15)
            ratio(5)
            checkpoint('06-lower-limit-clamped')
            drag_to(50)
            ratio(50)
            # Scroll the actual panes with real mouse wheel input; no injected scroll positions.
            c = canvas.bounding_box()
            page.mouse.move(c['x'] + c['width'] - 45, c['y'] + c['height'] / 2)
            before_scroll = dimensions()
            page.mouse.wheel(0, 640)
            page.wait_for_timeout(500)
            after_scroll = unchanged()
            assert after_scroll['canvasScroll'] > before_scroll['canvasScroll']
            assert after_scroll['outputScroll'] == before_scroll['outputScroll']
            page.mouse.wheel(0, -2000)
            log_box = output.bounding_box()
            page.mouse.move(log_box['x'] + log_box['width'] / 2, log_box['y'] + log_box['height'] / 2)
            before_scroll = dimensions()
            page.mouse.wheel(0, -1200)
            page.wait_for_timeout(500)
            after_scroll = unchanged()
            assert after_scroll['outputScroll'] < before_scroll['outputScroll'], (before_scroll, after_scroll)
            assert after_scroll['canvasScroll'] == before_scroll['canvasScroll']
            assert after_scroll['canvasScrollWidth'] > after_scroll['canvasWidth']
            assert after_scroll['outputScrollHeight'] > after_scroll['outputHeight']
            checkpoint('07-independent-canvas-and-output-scrolling')
            divider.focus()
            divider.press('Home')
            ratio(5)
            divider.press('ArrowUp')
            ratio(6)
            divider.press('Shift+ArrowUp')
            ratio(11)
            divider.press('ArrowDown')
            ratio(10)
            divider.press('End')
            ratio(95)
            checkpoint('08-keyboard-arrows-shift-home-end')
            drag_to(50)
            panel.locator('summary').click()
            expect(output).not_to_be_visible()
            expect(divider).not_to_be_visible()
            unchanged()
            panel.locator('summary').click()
            expect(divider).to_be_visible()
            ratio(50)
            checkpoint('09-collapse-and-reopen-preserve-height')
            # Escape releases the captured pointer; subsequent movement cannot resize.
            box = divider.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + 5
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x, y - 80, steps=10)
            page.keyboard.press('Escape')
            after_escape = dimensions()['output']
            page.mouse.move(x, y + 100, steps=10)
            page.mouse.up()
            assert abs(dimensions()['output'] - after_escape) < 1
            assert 'resizing-vertical' not in page.locator('body').get_attribute('class')
            unchanged()
            checkpoint('10-escape-releases-resize-gesture')
            drag_to(50)
            side = page.locator('#drag-divider')
            sidebar_before = page.locator('#main-agents-container').bounding_box()['width']
            side.focus()
            side.press('ArrowRight')
            assert page.locator('#main-agents-container').bounding_box()['width'] > sidebar_before
            side.press('ArrowLeft')
            ratio(50)
            checkpoint('11-operations-divider-still-resizes')
            # Browser zoom is unchanged; a real window restore tests responsive pane percentages.
            require_browser_foreground(page)
            browser_window = user32.GetForegroundWindow()
            user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.ShowWindow(browser_window, 9)
            user32.SetWindowPos(browser_window, None, 80, 60, 1400, 1000, 4)
            page.wait_for_timeout(600)
            ratio(50)
            checkpoint('12a-real-window-resize-keeps-ratio')
            user32.ShowWindow(browser_window, 3)
            page.wait_for_timeout(600)
            ratio(50)
            # Preserve only layout in localStorage, outside the portable diagram and its Undo history.
            page.wait_for_timeout(400)
            stored = page.evaluate('JSON.parse(localStorage.getItem("tlamatini.prompting-flow.layout.v1." + document.body.dataset.userId))')
            assert abs(stored['outputPercent'] - 50) < .1
            page.reload()
            expect(page.locator('.pmt-node')).to_have_count(5)
            expect(divider).to_have_attribute('aria-valuenow', '50')
            reloaded = dimensions()
            assert abs(reloaded['output'] / (reloaded['canvas'] + reloaded['output']) * 100 - 50) < .15
            assert reloaded['nodes'] == baseline['nodes']
            assert reloaded['zoom'] == baseline['zoom']
            checkpoint('12-height-restored-without-changing-diagram')
            # Leave real output on screen for inspection after the reload.
            page.locator('#pmt-play').click()
            page.locator('#pmt-field-reply').fill(reply)
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            log_box = output.bounding_box()
            page.mouse.move(log_box['x'] + 100, log_box['y'] + 80)
            page.mouse.wheel(0, -10000)
            page.wait_for_timeout(500)
            checkpoint('13-final-half-height-demonstration')
            assert not errors, errors
            outcome = 0
            (OUT / 'summary.json').write_text(json.dumps({'exit_code': 0, 'checks': results,
                'mocked_transports': False, 'model_called': False, 'browser_visible': True}, indent=2), encoding='utf-8')
            print('ALL RUN OUTPUT CHECKS PASSED. EXIT_CODE=0. Chrome stays open for inspection.', flush=True)
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
        print('RUN OUTPUT TEST EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
