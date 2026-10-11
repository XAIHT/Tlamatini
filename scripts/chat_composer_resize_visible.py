# Tlamatini Author Banner — Angela López Mendoza
"""Composer geometry regression on the real source page and an isolated database.

Inference and microphone WebSockets are isolated; status rows are labelled layout
fixtures. This verifies layout, not model inference or audio capture. Run only in
a verified visible foreground console.

Chrome is explicitly headed. Shoter captures the entire desktop; inspect its
browser-waiting.png before creating browser-visible-confirmed. The browser and
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
OUT = ROOT / 'Temp/composer-resize-browser'
_shoter_module = None


def shoter(name):
    global _shoter_module
    old_cwd = Path.cwd()
    os.environ['AGENT_REANIMATED'] = '1'
    try:
        if _shoter_module is None:
            spec = importlib.util.spec_from_file_location('composer_shoter', ROOT / 'Tlamatini/agent/agents/shoter/shoter.py')
            _shoter_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_shoter_module)
        _shoter_module.capture_screenshot(str(OUT), all_screens=True, filename=name)
    finally:
        os.chdir(old_cwd)


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN. Use a verified visible console.')
    # Compare Win32 physical pixels with Chromium CSS pixels * devicePixelRatio.
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    import tlamatini.settings as project_settings
    project_settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    project_settings.STATIC_ROOT = OUT / 'collected-static'
    import django
    django.setup()
    from django.core.management import call_command
    print('REAL SOURCE APP: applying migrations only to Temp/composer-resize-browser/isolated-browser.sqlite3', flush=True)
    call_command('migrate', interactive=False, verbosity=1)
    call_command('collectstatic', interactive=False, verbosity=1)
    from django.contrib.auth import get_user_model
    username = 'composer-review'
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.set_password(password)
    user.save()
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1', port=8871, log_level='info', loop='asyncio'))
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
    from chat_composer_resize_checks import run_checks
    from chat_viewport_visible_checks import run_viewport_checks
    from chat_composer_visible_window import VisibleWindow
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False,
                                             chromium_sandbox=True, slow_mo=180)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        # Layout fixtures isolate inference and microphone capture; no model job or recording.
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: None))
        page = context.new_page()
        native_window = VisibleWindow(page, context)
        print('REAL UNCLIPPED WINDOW:', native_window.resize(1440, 900), flush=True)
        page.native_window = native_window
        def capture(name):
            native_window.verify()
            shoter(name)
            native_window.verify()
        page.goto('http://127.0.0.1:8871/', wait_until='domcontentloaded', timeout=60000)
        page.bring_to_front()
        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        capture('browser-waiting.png')
        print('BROWSER WAITING: inspect browser-waiting.png, then create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(500)
        if page.locator('#id_username').count():
            page.locator('#id_username').fill(username)
            page.locator('#id_password').fill(password)
            page.locator('button[type="submit"],input[type="submit"]').first.click()
            page.wait_for_load_state('domcontentloaded')
        password = None
        if page.locator('#go-to-chat').count():
            page.locator('#go-to-chat').click()
        if not page.locator('#usage-button').count():
            page.goto('http://127.0.0.1:8871/agent/agent/', wait_until='domcontentloaded')
        results = []
        try:
            run_checks(page, context, user.pk, OUT, capture, results)
            results.extend(run_viewport_checks(page, context, OUT, capture))
        except Exception:
            traceback.print_exc()
            shoter('failure.png')
            results.append({'name': 'browser campaign', 'ok': False, 'error': traceback.format_exc()})
        summary = {'at': datetime.now(timezone.utc).isoformat(), 'checks': results,
                   'passed': all(r['ok'] for r in results), 'frozen_runtime_tested': False}
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print('BROWSER RESULTS:', json.dumps(summary, indent=2), flush=True)
        native_window.release()
        print('BROWSER REMAINS OPEN. Place a task check script at next-check.py to run more visible checks, or create close.confirmed.', flush=True)
        close = OUT / 'close.confirmed'
        close.unlink(missing_ok=True)
        command = OUT / 'next-check.py'
        while not close.exists():
            page.wait_for_timeout(500)
            if command.exists():
                code = command.read_text(encoding='utf-8')
                command.unlink()
                try:
                    exec(compile(code, str(command), 'exec'), {**globals(), **locals()})
                    print('EXTRA CHECKS FINISHED', flush=True)
                except Exception:
                    traceback.print_exc()
                    shoter('extra-check-failure.png')
        context.close()
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
