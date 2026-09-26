# Tlamatini Author Banner — Angela López Mendoza
"""Live menu checks in the real application, through visible Chrome.

Run in a verified foreground console. Uses the configured server, its actual
database, normal login, HTTP, WebSocket and model. No transport interception,
rendered-template substitute, account-role override, or simulated busy event.
The operator verifies Shoter's all-display image before releasing the browser.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback

import psutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/menu-live-tests'


def main():
    if any('headless' in arg for arg in sys.argv[1:]):
        raise SystemExit('Headless execution is forbidden.')
    from run_menu_state_checks import shoter
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / 'Tlamatini/agent/config.json').read_text(encoding='utf-8-sig'))
    port = int(config.get('django_port', 8000))
    base = f'http://127.0.0.1:{port}'
    print('LIVE APPLICATION:', base, flush=True)
    server_running = False
    for connection in psutil.net_connections(kind='tcp'):
        if connection.status == 'LISTEN' and connection.laddr.port == port and connection.pid:
            server_running = True
            process = psutil.Process(connection.pid)
            print('SERVER PROCESS:', json.dumps({'pid': process.pid, 'exe': process.exe(),
                  'command': process.cmdline()}, ensure_ascii=False), flush=True)
    if not server_running:
        raise RuntimeError(
            'Start the normal Tlamatini application in a visible console before running live checks. '
            'This runner does not create databases, accounts, or substitute servers.')
    credentials = json.loads((OUT / 'login.json').read_text(encoding='utf-8'))
    history = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(OUT / 'chrome-profile'), channel='chrome', headless=False,
            no_viewport=True, chromium_sandbox=True, slow_mo=200,
            args=['--start-maximized'])
        page = context.pages[0] if context.pages else context.new_page()
        window_control = context.new_cdp_session(page)
        window_id = window_control.send('Browser.getWindowForTarget')['windowId']
        window_control.send('Browser.setWindowBounds', {
            'windowId': window_id, 'bounds': {'windowState': 'maximized'}})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = page.goto(base, wait_until='domcontentloaded', timeout=60000)
        print('REAL PAGE HTTP STATUS:', response.status if response else None, flush=True)
        page.bring_to_front()
        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        shoter('live-browser-waiting.png')
        print('LIVE BROWSER WAITING: verify the all-display Shoter image, then release the browser gate.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(500)

        def observe(label):
            state = page.evaluate('''() => ({url: location.href, title: document.title,
                account: document.getElementById('user_username')?.textContent,
                navbar: document.getElementById('menu-editor')?.innerText,
                admin: [...document.querySelectorAll('#open-admin')].map(e => ({text:e.textContent.trim(),href:e.href,parent:e.closest('ul')?.getAttribute('aria-labelledby')})),
                spinner: !!document.querySelector('#wait-spinner'),
                inputReadonly: document.getElementById('chat-message-input')?.readOnly,
                submit: document.getElementById('chat-message-submit')?.textContent,
                visibleDialogs: [...document.querySelectorAll('.ui-dialog')].filter(e=>e.getClientRects().length).map(e=>e.innerText)
            })''')
            state.update(label=label, errors=list(errors))
            history.append(state)
            (OUT / 'observations.json').write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding='utf-8')
            print('LIVE OBSERVATION:', json.dumps(state, ensure_ascii=False), flush=True)
            page.bring_to_front()
            shoter('live-' + label + '.png')
            return state

        if page.locator('#id_username').count():
            page.locator('#id_username').fill(credentials['username'])
            page.locator('#id_password').fill(credentials['password'])
            page.locator('button[type="submit"], input[type="submit"]').first.click()
            page.wait_for_load_state('domcontentloaded')
        print('LOGIN ACCOUNT:', credentials['username'], flush=True)
        credentials.clear()
        if page.locator('#go-to-chat').count():
            page.locator('#go-to-chat').click()
        elif page.get_by_role('link', name='Go to Chat', exact=True).count():
            page.get_by_role('link', name='Go to Chat', exact=True).click()
        observe('logged-in')
        request_path = OUT / 'command.json'
        last_request = None
        print('LIVE CONSOLE READY: browser remains visible for real UI steps.', flush=True)
        while True:
            page.wait_for_timeout(500)
            if not request_path.exists():
                continue
            command = json.loads(request_path.read_text(encoding='utf-8'))
            if command.get('id') == last_request:
                continue
            last_request = command.get('id')
            action = command.get('action')
            try:
                if action == 'reload':
                    page.reload(wait_until='domcontentloaded')
                elif action == 'click':
                    page.locator(command['selector']).click()
                elif action == 'fill':
                    page.locator(command['selector']).fill(command['text'])
                elif action == 'press':
                    page.keyboard.press(command['key'])
                elif action == 'open-admin':
                    with page.expect_popup() as opening:
                        page.locator('#open-admin').click()
                    admin = opening.value
                    admin.wait_for_load_state('domcontentloaded')
                    print('DJANGO ADMIN REAL PAGE:', admin.url, admin.title(), flush=True)
                    admin.bring_to_front()
                    shoter('live-admin-destination.png')
                    (OUT / 'admin-destination.json').write_text(json.dumps({
                        'url': admin.url, 'title': admin.title(),
                        'siteHeader': admin.locator('#site-name').inner_text() if admin.locator('#site-name').count() else None,
                        'bodyHeading': admin.locator('h1').all_text_contents()}, indent=2), encoding='utf-8')
                elif action == 'finish':
                    observe('complete')
                    print('LIVE CHECKS FINISHED; visible console remains open.', flush=True)
                    context.close()
                    return 0
                elif action != 'observe':
                    raise ValueError('Unknown live UI command: ' + str(action))
                observe(str(last_request))
                (OUT / 'last-command.json').write_text(json.dumps({'id':last_request,'success':True}), encoding='utf-8')
            except Exception as error:
                traceback.print_exc()
                (OUT / 'last-command.json').write_text(json.dumps({'id':last_request,'success':False,'error':str(error)}), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
