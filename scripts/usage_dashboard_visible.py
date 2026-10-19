# Tlamatini Author Banner — Angela López Mendoza
"""Real source app + isolated database, in a verified visible foreground console.

Chrome is explicitly headed. A read-only foreground check gates browser work;
Shoter captures the entire desktop for inspection. The browser and
console remain open for review. No production database or configuration is edited.
"""
import asyncio
from datetime import datetime, timezone
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
OUT = ROOT / 'Temp/usage-visible'


def await_browser_foreground(page, seconds=120):
    """Observe ownership/visibility only; never activate windows through Win32."""
    import ctypes
    import psutil
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    deadline = time.monotonic() + seconds
    reported = 0
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError('Validation browser closed before the checkpoint.')
        owned = {p.pid for p in psutil.Process().children(recursive=True) if p.name().lower() == 'chrome.exe'}
        window = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value in owned and user32.IsWindowVisible(window) and not user32.IsIconic(window):
            print('Verified foreground validation Chrome:', pid.value, flush=True)
            return
        if time.monotonic() - reported >= 10:
            print('WAITING: validation Chrome must be visible and foreground; no browser actions running.', flush=True)
            reported = time.monotonic()
        page.wait_for_timeout(250)
    raise RuntimeError('STOPPED: validation Chrome was not verified in the foreground.')


def shoter(name):
    old_cwd = Path.cwd()
    os.environ['AGENT_REANIMATED'] = '1'
    spec = importlib.util.spec_from_file_location('usage_shoter', ROOT / 'Tlamatini/agent/agents/shoter/shoter.py')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.capture_screenshot(str(OUT), all_screens=True, filename=name)
    finally:
        os.chdir(old_cwd)


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN. Use a verified visible console.')
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    import tlamatini.settings as project_settings
    project_settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    project_settings.STATIC_ROOT = OUT / 'collected-static'
    import django
    django.setup()
    from django.core.management import call_command
    print('REAL SOURCE APP: applying migrations only to Temp/usage-visible/isolated-browser.sqlite3', flush=True)
    call_command('migrate', interactive=False, verbosity=1)
    call_command('makemigrations', 'agent', check=True, dry_run=True, verbosity=1)
    call_command('collectstatic', interactive=False, verbosity=1)
    from django.contrib.auth import get_user_model
    username = 'usage-review'
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.set_password(password)
    user.save()
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1', port=8869, log_level='info', loop='asyncio'))
    thread = threading.Thread(target=server.run, name='UsageSourceServer', daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('The isolated source server did not start.')
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from usage_dashboard_browser_checks import run_checks
    from usage_dashboard_fixture_checks import run_fixtures
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False,
                                             chromium_sandbox=True, slow_mo=180)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()
        display = page.evaluate('({width:screen.availWidth,height:screen.availHeight})')
        session = context.new_cdp_session(page)
        window_id = session.send('Browser.getWindowForTarget')['windowId']
        session.send('Browser.setWindowBounds', {'windowId': window_id, 'bounds': {
            'left': round(display['width'] * .33), 'top': 0,
            'width': round(display['width'] * .67), 'height': display['height'] - 30}})
        page.goto('http://127.0.0.1:8869/', wait_until='domcontentloaded', timeout=60000)
        page.bring_to_front()
        await_browser_foreground(page)
        shoter('browser-waiting.png')
        if page.locator('#id_username').count():
            page.locator('#id_username').fill(username)
            page.locator('#id_password').fill(password)
            page.locator('button[type="submit"],input[type="submit"]').first.click()
            page.wait_for_load_state('domcontentloaded')
        password = None
        if page.locator('#go-to-chat').count():
            page.locator('#go-to-chat').click()
        if not page.locator('#usage-button').count():
            page.goto('http://127.0.0.1:8869/agent/agent/', wait_until='domcontentloaded')
        results = []
        def capture(name):
            await_browser_foreground(page)
            shoter(name)
        try:
            await_browser_foreground(page)
            run_checks(page, context, user.pk, OUT, capture, results)
            run_fixtures(page, context, user.pk, OUT, capture, results)
        except Exception:
            traceback.print_exc()
            shoter('failure.png')
            results.append({'name': 'browser campaign', 'ok': False, 'error': traceback.format_exc()})
        summary = {'at': datetime.now(timezone.utc).isoformat(), 'checks': results,
                   'passed': all(r['ok'] for r in results), 'frozen_runtime_tested': False}
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print('BROWSER RESULTS:', json.dumps(summary, indent=2), flush=True)
        print('BROWSER REMAINS OPEN. Place a task check script at next-check.py to run more visible checks, or create close.confirmed.', flush=True)
        close = OUT / 'close.confirmed'
        close.unlink(missing_ok=True)
        command = OUT / 'next-check.py'
        while not close.exists() and not page.is_closed() and browser.is_connected():
            try:
                page.wait_for_timeout(500)
            except Exception:
                if page.is_closed() or not browser.is_connected():
                    break
                raise
            if command.exists():
                code = command.read_text(encoding='utf-8')
                command.unlink()
                try:
                    exec(compile(code, str(command), 'exec'), {**globals(), **locals()})
                    print('EXTRA CHECKS FINISHED', flush=True)
                except Exception:
                    traceback.print_exc()
                    shoter('extra-check-failure.png')
        if browser.is_connected():
            context.close()
            browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
