# Tlamatini Author Banner — Angela López Mendoza
"""Interactive source UI audit, from a verified visible PowerShell -NoExit console.

Chrome is always headed. Shoter captures the whole desktop before the fresh
visibility gate is released. Commands and results stay visible; the browser stays
open for review. Only the isolated database under Temp/ui-sweep is used. Provider
WebSockets are disconnected: this is a layout/interaction audit, not inference.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/ui-sweep'


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN. Use a verified visible console.')
    import ctypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    console = kernel32.GetConsoleWindow()
    if not console or not user32.IsWindowVisible(console) or user32.IsIconic(console) or user32.GetForegroundWindow() != console:
        raise SystemExit('A verified visible foreground console is required; refusing execution.')
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    os.environ['PYTHONUNBUFFERED'] = '1'
    import tlamatini.settings as project_settings
    project_settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    project_settings.STATIC_ROOT = OUT / 'collected-static'
    import django
    django.setup()
    from django.core.management import call_command
    print('Migrating isolated UI audit database only.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    username = 'ui-review'
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username=username)
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.save()
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    base = 'http://127.0.0.1:8874'
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1',
                                           port=8874, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, name='VisibleUISourceServer', daemon=True)
    thread.start()
    for _ in range(150):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Isolated source server failed to start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    import drag_divider_look_visible as photos
    photos.OUT = OUT
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=70)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: None))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: (errors.append(str(error)), print('BROWSER ERROR:', error, flush=True)))
        window = VisibleWindow(page, context)
        print('VISIBLE CHROME:', window.resize(1440, 900), flush=True)
        page.goto(base + '/', wait_until='load')

        def capture(name):
            window.verify()
            path, metadata = photos.shoter(name)
            window.verify()
            return path, metadata

        capture('browser-waiting.png')
        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        print('BROWSER WAITING: inspect browser-waiting.png before releasing the gate.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(500)
        page.locator('#id_username').fill(username)
        page.locator('#id_password').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state('load')
        password = None
        print('READY: numbered browser-001.py commands run in this visible browser.', flush=True)
        results = []
        scope = {**globals(), **locals()}
        index = 1
        close = OUT / 'close.confirmed'
        close.unlink(missing_ok=True)
        try:
            while not close.exists() and not page.is_closed():
                command = OUT / f'browser-{index:03d}.py'
                if command.exists():
                    print('BROWSER RUN:', command.name, flush=True)
                    try:
                        window.activate()
                        window.verify()
                        exec(compile(command.read_text(encoding='utf-8-sig'), str(command), 'exec'), scope)
                        (OUT / f'{command.name}.result').write_text('PASS', encoding='utf-8')
                    except Exception:
                        traceback.print_exc()
                        (OUT / f'{command.name}.result').write_text(traceback.format_exc(), encoding='utf-8')
                        capture(f'browser-{index:03d}-failure.png')
                    (OUT / 'browser-errors.json').write_text(json.dumps(errors, indent=2), encoding='utf-8')
                    print('BROWSER FINISHED:', command.name, flush=True)
                    index += 1
                page.wait_for_timeout(500)
        finally:
            window.release()
            context.close()
            browser.close()
            server.should_exit = True
            thread.join(timeout=10)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
