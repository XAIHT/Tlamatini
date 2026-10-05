# Tlamatini Author Banner — Angela López Mendoza
"""Static commentary / unchanged user-input regression in real visible Chrome.

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
OUT = ROOT / 'Temp/prompt-commentary-redesign-visible'
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

            from release_commentary_checks import run_commentary_checks
            run_commentary_checks(page, OUT, BASE, checkpoint, errors)
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
