# Tlamatini Author Banner — Angela López Mendoza
"""Shared harness for the VISIBLE Terminater suites (chat, ACP, Prompt Flow Panel).

Everything here is deliberately visible: a headed Chrome window on the real desktop,
launched from a foreground console, with a full-desktop Shoter photograph per check.
There is NO headless fallback and no mocked transport: the dock talks to a real
Django server (a separate source installation on its own port and database) that
hosts real ConPTY shells.

Launch a suite from a verified foreground PowerShell -NoExit console, e.g.

    python scripts/terminater_visible_chat.py

Protocol (same as the other visible suites in this repository):
  * the console gate and the browser gate each take a Shoter photograph and then
    WAIT for the operator to create ``Temp/terminater-visible/<gate>.confirmed``
    after looking at that photograph;
  * every check records PASS/FAIL with a photograph; a failure never aborts the run,
    so one run reports every problem;
  * nothing is ever recorded as a pass that was not actually observed.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import winreg
from pathlib import Path

import psutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/terminater-visible'
RUNTIME = OUT / 'runtime'
PORT = 8003
MCP_PORT = 8767
GRPC_PORT = 50053
BASE = f'http://127.0.0.1:{PORT}'
DISCOVERY = r'Software\XAIHT\Tlamatini'
REG_NAMES = ('InstallLocation', 'AgentsRoot', 'SourceAgentsRoot',
             'AgentManifestPath', 'Version', 'AgentCatalogVersion')
IGNORED_DIRS = {'__pycache__', '.ruff_cache', '.pytest_cache', 'staticfiles', 'pools', 'Temp', 'DB',
                'node_modules', '.venv', 'venv', 'TlamatiniSourceCode'}
IGNORED_SUFFIXES = ('.pyc', '.log', '.pid')
SYNC_DIRS = ('agent', 'tlamatini')


# ── photographs and gates ────────────────────────────────────────────────────

def photograph(name: str) -> Path:
    """One full-desktop photograph, taken by Tlamatini's own Shoter agent."""
    destination = OUT / 'shoter-runtime'
    if not destination.exists():
        shutil.copytree(ROOT / 'Tlamatini/agent/agents/shoter', destination,
                        ignore=shutil.ignore_patterns('__pycache__', '*.log', '*.pid'))
    (destination / 'config.yaml').write_text(
        f'output_dir: {OUT.as_posix()}\nfilename: {name}.png\nall_screens: true\ntarget_agents: []\n',
        encoding='utf-8')
    subprocess.run([sys.executable, '-u', str(destination / 'shoter.py')], cwd=destination,
                   check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   encoding='utf-8')
    path = OUT / (name + '.png')
    if not path.is_file():
        raise RuntimeError('Shoter did not produce ' + name)
    return path


def visibility_gate(name: str, page=None) -> None:
    gate = OUT / (name + '.confirmed')
    if gate.exists() and '--keep-gates' in sys.argv:
        return
    gate.unlink(missing_ok=True)
    print('WAITING FOR VISIBLE ' + name.upper() + ' VERIFICATION', flush=True)
    photograph(name + '-waiting')
    deadline = time.monotonic() + 900
    while not gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Visibility was not verified: ' + name)
        if page:
            page.wait_for_timeout(500)
        else:
            time.sleep(.5)


def raise_window(hwnd):
    """Bring a window to the front the way Windows allows a background program to: borrow the input
    queue of the current foreground thread for a moment.  (Another program - this very assistant's
    own window - can take the foreground between two checks, and a test must never photograph that.)"""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    for name in ('ShowWindow', 'SetForegroundWindow', 'IsIconic', 'GetWindowThreadProcessId', 'BringWindowToTop'):
        getattr(user32, name).argtypes = [ctypes.c_void_p] + ([ctypes.c_int] if name == 'ShowWindow' else [ctypes.c_void_p] if name == 'GetWindowThreadProcessId' else [])
    foreground = user32.GetForegroundWindow()
    current = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(other and other != current and user32.AttachThreadInput(other, current, True))
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(other, current, False)


def foreground_info():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    window = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(1024)
    klass = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(window, title, len(title))
    user32.GetClassNameW(window, klass, len(klass))
    return window, title.value, klass.value, bool(user32.IsWindowVisible(window)) and not user32.IsIconic(window)


# ── installation, discovery registry, server ─────────────────────────────────

def read_discovery():
    result = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISCOVERY) as key:
            for name in REG_NAMES:
                try:
                    result[name] = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    return result


def restore_discovery(original):
    current = read_discovery()
    if str(RUNTIME).lower() not in str(current.get('InstallLocation', ('',))[0]).lower():
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DISCOVERY, 0, winreg.KEY_SET_VALUE) as key:
        for name in REG_NAMES:
            if name in original:
                value, value_type = original[name]
                winreg.SetValueEx(key, name, 0, value_type, value)
            elif name in current:
                winreg.DeleteValue(key, name)
    print('Restored the existing application discovery registration.', flush=True)


def listeners():
    ports = (PORT, MCP_PORT, GRPC_PORT)
    return {c.laddr.port: c.pid for c in psutil.net_connections(kind='tcp')
            if c.status == 'LISTEN' and c.laddr.port in ports}


def _sync_tree(src: Path, dst: Path) -> int:
    changed = 0
    for current, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        rel = Path(current).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name.endswith(IGNORED_SUFFIXES) or name.startswith('db.sqlite3'):
                continue
            source = Path(current) / name
            target = target_dir / name
            try:
                s = source.stat()
                if target.exists():
                    t = target.stat()
                    if t.st_size == s.st_size and int(t.st_mtime) >= int(s.st_mtime):
                        continue
                shutil.copy2(source, target)
                changed += 1
            except OSError:
                continue
    return changed


def prepare_runtime():
    """A separate normal source installation + database on port 8003 (never the real one)."""
    OUT.mkdir(parents=True, exist_ok=True)
    first = not RUNTIME.exists()
    (RUNTIME / 'Tlamatini').mkdir(parents=True, exist_ok=True)
    print('Preparing the separate source installation (first run copies everything).', flush=True)
    changed = 0
    for sub in SYNC_DIRS:
        changed += _sync_tree(ROOT / 'Tlamatini' / sub, RUNTIME / 'Tlamatini' / sub)
    for name in ('manage.py',):
        shutil.copy2(ROOT / 'Tlamatini' / name, RUNTIME / 'Tlamatini' / name)
    for name in ('VERSION', 'version.txt', 'public_version.json'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, RUNTIME / name)
    print(f'Synchronised {changed} changed file(s) into the test installation.', flush=True)
    config_path = RUNTIME / 'Tlamatini/agent/config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    config.update(django_port=PORT, mcp_system_server_port=MCP_PORT,
                  mcp_files_search_server_port=GRPC_PORT,
                  mcp_system_client_uri=f'ws://127.0.0.1:{MCP_PORT}',
                  mcp_files_search_client_uri=f'ws://127.0.0.1:{GRPC_PORT}')
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    login_path = OUT / 'login.json'
    if not login_path.exists():
        login_path.write_text(json.dumps({'username': 'tester', 'password': secrets.token_urlsafe(14)}),
                              encoding='utf-8')
    credentials = json.loads(login_path.read_text(encoding='utf-8'))
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    env.pop('NO_COLOR', None)
    manage = [sys.executable, '-u', 'Tlamatini/manage.py']
    subprocess.run(manage + ['migrate', '--noinput'], cwd=RUNTIME, env=env, check=True,
                   stdout=subprocess.DEVNULL)
    if first or not (RUNTIME / 'Tlamatini/db.sqlite3').exists() or True:
        account_env = {**env, 'DJANGO_SUPERUSER_USERNAME': credentials['username'],
                       'DJANGO_SUPERUSER_PASSWORD': credentials['password'],
                       'DJANGO_SUPERUSER_EMAIL': 'tester@example.invalid'}
        # Fails harmlessly when the account already exists.
        subprocess.run(manage + ['createsuperuser', '--noinput'], cwd=RUNTIME, env=account_env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return env, credentials


def start_server(env):
    server = subprocess.Popen(
        [sys.executable, '-u', 'Tlamatini/manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'],
        cwd=RUNTIME, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace')
    (OUT / 'owned-server.json').write_text(json.dumps({'pid': server.pid,
        'created': psutil.Process(server.pid).create_time(), 'port': PORT}), encoding='utf-8')

    def forward():
        with (OUT / 'server.log').open('w', encoding='utf-8') as logfile:
            for line in server.stdout:
                logfile.write(line)
                logfile.flush()
    threading.Thread(target=forward, daemon=True).start()
    return server


def stop_server(server):
    if not server or server.poll() is not None:
        return
    parent = psutil.Process(server.pid)
    children = parent.children(recursive=True)
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    parent.terminate()
    _, remaining = psutil.wait_procs(children + [parent], timeout=10)
    for process in remaining:
        process.kill()
    server.wait(timeout=10)
    print('Stopped the test server and its descendants.', flush=True)


# ── the Tlamatini-side API (what a pool agent / the wrapped tool uses) ───────

def hub_credentials():
    path = RUNTIME / 'Temp/.terminater_hub.json'
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('url') and data.get('token'):
                    return data
            except (OSError, ValueError):
                pass
        time.sleep(.3)
    raise RuntimeError('The terminal hub rendezvous file did not appear: ' + str(path))


def api(action, timeout=120, **params):
    """Call the loopback Terminater API exactly as the pool agent does."""
    cred = hub_credentials()
    body = json.dumps({'action': action, 'params': params, 'wait_for_job': True}).encode('utf-8')
    request = urllib.request.Request(cred['url'] + '/agent/terminater/api/', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'X-Terminater-Token': cred['token']})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode('utf-8'))
        except ValueError:
            return {'ok': False, 'status': 'http_%s' % exc.code}


# ── the harness ──────────────────────────────────────────────────────────────

class _Tee:
    """Console output is also written to a file so a run can be followed live."""

    def __init__(self, stream, path):
        self.stream = stream
        self.file = open(path, 'w', encoding='utf-8', buffering=1)

    def write(self, text):
        try:
            self.stream.write(text)
        except Exception:
            pass
        try:
            self.file.write(text)
        except Exception:
            pass
        return len(text)

    def flush(self):
        for target in (self.stream, self.file):
            try:
                target.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


class Harness:
    """Server + headed Chrome + checks.  Use as a context manager."""

    def __init__(self, suite: str, start_path: str):
        if any('headless' in arg for arg in sys.argv[1:]):
            raise SystemExit('Headless execution is forbidden.')
        OUT.mkdir(parents=True, exist_ok=True)
        if not isinstance(sys.stdout, _Tee):
            sys.stdout = _Tee(sys.stdout, OUT / (suite + '-console.log'))
        self.suite = suite
        self.start_path = start_path
        self.results = []
        self.counter = 0
        self.server = None
        self.original_discovery = {}
        self.playwright = None
        self.context = None
        self.page = None
        self.browser_window = None
        self.errors = []
        self.user_id = None

    # lifecycle ----------------------------------------------------------------
    def __enter__(self):
        OUT.mkdir(parents=True, exist_ok=True)
        visibility_gate('console')
        occupied = listeners()
        if occupied:
            raise SystemExit('Test ports are occupied; refusing to replace a server: %s' % occupied)
        self.original_discovery = read_discovery()
        env, self.credentials = prepare_runtime()
        self.server = start_server(env)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if self.server.poll() is not None:
                raise RuntimeError('Test server exited: ' + str(self.server.returncode))
            try:
                with urllib.request.urlopen(BASE, timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError, urllib.error.URLError):
                time.sleep(1)
        else:
            raise TimeoutError('Test server did not become ready.')
        restore_discovery(self.original_discovery)
        profile = OUT / 'chrome-profile'
        preferences = profile / 'Default' / 'Preferences'
        if not preferences.exists():
            preferences.parent.mkdir(parents=True, exist_ok=True)
            preferences.write_text(json.dumps({'credentials_enable_service': False,
                'profile': {'password_manager_enabled': False}}), encoding='utf-8')
        try:   # a previous run that was stopped leaves "Chrome didn't shut down correctly" on screen
            prefs = json.loads(preferences.read_text(encoding='utf-8'))
            prefs.setdefault('profile', {})['exit_type'] = 'Normal'
            prefs['profile']['exited_cleanly'] = True
            preferences.write_text(json.dumps(prefs), encoding='utf-8')
        except (OSError, ValueError):
            pass
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            str(profile), channel='chrome', headless=False, chromium_sandbox=True, no_viewport=True,
            slow_mo=40, accept_downloads=True, args=['--start-maximized'])
        self.context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=BASE)
        self.page = self.context.pages[0]
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda m: self.errors.append('console.error: ' + m.text) if m.type == 'error' else None)
        self.page.goto(BASE)
        self.page.bring_to_front()
        self.page.wait_for_timeout(1500)
        visibility_gate('browser', self.page)
        self.foreground()
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            print('SUITE ABORTED:', ''.join(traceback.format_exception(exc_type, exc, tb)), flush=True)
            self.fail('suite-aborted', 'The suite stopped early: %s' % exc, photo=False)
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        finally:
            stop_server(self.server)
            try:
                restore_discovery(self.original_discovery)
            except Exception:
                pass
        self.write_results()
        failed = [r for r in self.results if not r['ok']]
        print('=' * 78, flush=True)
        print('%s: %d checks, %d passed, %d FAILED' % (self.suite, len(self.results),
              len(self.results) - len(failed), len(failed)), flush=True)
        for item in failed:
            print('  FAIL:', item['name'], '-', item['detail'], flush=True)
        print('=' * 78, flush=True)
        self.exit_code = 1 if failed or exc else 0
        return True

    # helpers ------------------------------------------------------------------
    def foreground(self):
        """Pause (never fake) when another window covers the test Chrome."""
        deadline = time.monotonic() + 300
        last = 0
        while time.monotonic() < deadline:
            window, title, klass, visible = foreground_info()
            if self.browser_window is None and klass == 'Chrome_WidgetWin_1' and 'Chrome' in title and visible:
                self.browser_window = window
            if visible and window == self.browser_window:
                return
            if time.monotonic() - last > 10:
                print('PAUSED: restore the visible test Chrome window before continuing.', flush=True)
                last = time.monotonic()
            try:
                self.page.bring_to_front()
                if self.browser_window:
                    raise_window(self.browser_window)
            except Exception:
                pass
            time.sleep(.3)
        raise RuntimeError('Browser foreground visibility was not restored; verification refused.')

    def login(self):
        # A test ESTABLISHES its environment.  The dock remembers its visibility, layout and size per
        # user in the browser, the profile is reused between runs, and a page that finds "visible" in
        # that memory raises a terminal on the hub (which then remembers it too).  So the memory is
        # cleared on the login page (same origin, no dock) BEFORE any page that has a dock is opened.
        self.page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('tlamatini.terminals.')).forEach(k => localStorage.removeItem(k))")
        self.page.goto(BASE + self.start_path)
        if self.page.locator('#id_username').count():
            self.page.locator('#id_username').fill(self.credentials['username'])
            self.page.locator('#id_password').fill(self.credentials['password'])
            self.page.locator('button[type=submit]').click()
            self.page.wait_for_timeout(1500)
            self.page.goto(BASE + self.start_path)
        self.credentials = {}
        self.page.wait_for_timeout(1500)
        self.page.keyboard.press('Escape')
        try:
            self.user_id = str(self.page.evaluate(
                "() => document.body.dataset.layoutUser || document.body.dataset.tlmUser || ''"))
        except Exception:
            self.user_id = ''

    def goto(self, path):
        self.page.goto(BASE + path)
        self.page.wait_for_timeout(1200)
        self.page.keyboard.press('Escape')

    def snap(self, label):
        self.page.bring_to_front()
        self.page.wait_for_timeout(250)
        self.foreground()
        self.counter += 1
        name = '%s-%03d-%s' % (self.suite, self.counter, re.sub(r'[^A-Za-z0-9]+', '-', label).strip('-')[:60])
        photograph(name)
        return name + '.png'

    def check(self, name, ok, detail='', photo=True):
        shot = ''
        if photo:
            try:
                shot = self.snap(name)
            except Exception as exc:  # a failed photograph is a failed check, never a silent pass
                ok = False
                detail = (detail + ' | ' if detail else '') + 'photograph failed: %s' % exc
        ok = bool(ok)
        self.results.append({'name': name, 'ok': ok, 'detail': str(detail), 'screenshot': shot})
        print(('PASS: ' if ok else 'FAIL: ') + name + ((' — ' + str(detail)) if detail and not ok else ''), flush=True)
        self.write_results()
        return ok

    def fail(self, name, detail, photo=True):
        return self.check(name, False, detail, photo)

    def write_results(self):
        (OUT / (self.suite + '-results.json')).write_text(json.dumps(self.results, indent=2), encoding='utf-8')

    # dock helpers --------------------------------------------------------------
    def dock(self):
        return self.page.evaluate("() => window.TlamatiniTerminals ? window.TlamatiniTerminals.state() : null")

    def wait_dock_ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.dock()
            if state and state.get('hello'):
                return state
            self.page.wait_for_timeout(250)
        return self.dock()

    def wait_for(self, predicate, timeout=40, interval=250):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = predicate()
            except Exception:
                value = None
            if value:
                return value
            self.page.wait_for_timeout(interval)
        return None

    def term_text(self, terminal=None, lines=80):
        return self.page.evaluate("([id, n]) => window.TlamatiniTerminals.textOf(id || '', n)", [terminal or '', lines]) or ''

    def active_terminal(self):
        state = self.dock() or {}
        for item in state.get('terminals', []):
            if item.get('active'):
                return item
        return None

    def type_as_user(self, text, delay=35, enter=True):
        """Type into the focused terminal like a person (real key events)."""
        self.page.locator('.tlm-term-pane[data-active="true"] .xterm-helper-textarea').first.focus()
        self.page.keyboard.type(text, delay=delay)
        if enter:
            self.page.keyboard.press('Enter')
