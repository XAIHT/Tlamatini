# Tlamatini Author Banner — Angela López Mendoza
"""Real panel UI checks in visible Chrome and a verified foreground console.

Uses a separate normal source installation on port 8001, ordinary migrations
and installer-default login. No HTTP/WebSocket interception, injected canvas
state, or authentication bypass. Shoter captures every visual checkpoint.
The console must be launched with PowerShell -NoExit and kept visible.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import winreg

import psutil
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/panel-search-title-visible'
RUNTIME = OUT / 'runtime'
BASE = 'http://127.0.0.1:8001'
DISCOVERY = r'Software\XAIHT\Tlamatini'
REG_NAMES = ('InstallLocation', 'AgentsRoot', 'SourceAgentsRoot',
             'AgentManifestPath', 'Version', 'AgentCatalogVersion')


def photograph(name):
    destination = OUT / 'shoter-runtime'
    if not destination.exists():
        shutil.copytree(ROOT / 'Tlamatini/agent/agents/shoter', destination,
                        ignore=shutil.ignore_patterns('__pycache__', '*.log', '*.pid'))
    (destination / 'config.yaml').write_text(
        f'output_dir: {OUT.as_posix()}\nfilename: {name}.png\nall_screens: true\n'
        'target_agents: []\n', encoding='utf-8')
    subprocess.run([sys.executable, '-u', str(destination / 'shoter.py')],
                   cwd=destination, check=True, timeout=60)
    if not (OUT / (name + '.png')).is_file():
        raise RuntimeError('Shoter did not produce ' + name)


def visibility_gate(name, page=None):
    gate = OUT / (name + '.confirmed')
    gate.unlink(missing_ok=True)
    print('WAITING FOR VISIBLE ' + name.upper() + ' VERIFICATION', flush=True)
    photograph(name + '-waiting')
    deadline = time.monotonic() + 600
    while not gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Visibility was not verified: ' + name)
        if page:
            page.wait_for_timeout(500)
        else:
            time.sleep(.5)


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
    # Restore only registration written by THIS test instance. Never overwrite
    # a user application that registered itself after our startup.
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
    return {c.laddr.port: c.pid for c in psutil.net_connections(kind='tcp')
            if c.status == 'LISTEN' and c.laddr.port in (8000, 8001, 8766, 50052)}


def prepare_runtime():
    if RUNTIME.exists():
        if '--resume' not in sys.argv:
            raise RuntimeError('Use --resume for this existing test installation: ' + str(RUNTIME))
        config_path = RUNTIME / 'Tlamatini/agent/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if config.get('django_port') != 8001:
            raise RuntimeError('Resume is restricted to the port-8001 test installation.')
        credentials = json.loads((OUT / 'login.json').read_text(encoding='utf-8'))
        env = os.environ.copy()
        env.update(CONFIG_PATH=str(config_path), PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        print('Resuming the existing port-8001 installation and normal login session.', flush=True)
        return env, credentials
    ignored = shutil.ignore_patterns('__pycache__', '.ruff_cache', '.pytest_cache',
                                     'staticfiles', 'pools', 'Temp', 'DB', 'node_modules',
                                     '.venv', 'venv', '*.pyc', '*.log', '*.pid', 'db.sqlite3*')
    print('Preparing a separate normal source installation and database.', flush=True)
    shutil.copytree(ROOT / 'Tlamatini', RUNTIME / 'Tlamatini', ignore=ignored)
    for name in ('VERSION', 'version.txt', 'public_version.json'):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, RUNTIME / name)
    config_path = RUNTIME / 'Tlamatini/agent/config.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    config.update(django_port=8001, mcp_system_server_port=8766,
                  mcp_files_search_server_port=50052)
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    credentials = json.loads((OUT / 'login.json').read_text(encoding='utf-8'))
    env = os.environ.copy()
    env.update(CONFIG_PATH=str(config_path), PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    manage = [sys.executable, '-u', 'Tlamatini/manage.py']
    subprocess.run(manage + ['migrate', '--noinput'], cwd=RUNTIME, env=env, check=True)
    account_env = {**env, 'DJANGO_SUPERUSER_USERNAME': credentials['username'],
                   'DJANGO_SUPERUSER_PASSWORD': credentials['password'],
                   'DJANGO_SUPERUSER_EMAIL': 'user@xaiht.com'}
    subprocess.run(manage + ['createsuperuser', '--noinput'], cwd=RUNTIME,
                   env=account_env, check=True)
    return env, credentials


def start_server(env):
    server = subprocess.Popen(
        [sys.executable, '-u', 'Tlamatini/manage.py', 'runserver', '127.0.0.1:8001', '--noreload'],
        cwd=RUNTIME, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace')
    (OUT / 'owned-server.json').write_text(json.dumps({'pid': server.pid,
        'created': psutil.Process(server.pid).create_time(), 'port': 8001}), encoding='utf-8')

    def forward():
        with (OUT / 'server.log').open('w', encoding='utf-8') as logfile:
            for line in server.stdout:
                logfile.write(line)
                logfile.flush()
                print('[8001] ' + line, end='', flush=True)

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


def main():
    if any('headless' in argument for argument in sys.argv[1:]):
        raise SystemExit('Headless execution is forbidden.')
    OUT.mkdir(parents=True, exist_ok=True)
    visibility_gate('console')
    before = listeners()
    if any(port in before for port in (8001, 8766, 50052)):
        raise RuntimeError('A test port is already occupied: ' + str(before))
    print('Existing instance on port 8000:', before.get(8000), flush=True)
    original_discovery = read_discovery()
    (OUT / 'discovery-before.json').write_text(json.dumps(original_discovery), encoding='utf-8')
    server = None
    results = []
    outcome = 1
    try:
        # Lint the actual edited source in this same visible console.
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:
            raise RuntimeError('npm is unavailable for the required frontend lint.')
        if '--resume' not in sys.argv:
            subprocess.run([npm, 'run', 'lint'], cwd=ROOT, check=True)
        env, credentials = prepare_runtime()
        server = start_server(env)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if server.poll() is not None:
                raise RuntimeError('Port-8001 server exited: ' + str(server.returncode))
            try:
                with urllib.request.urlopen(BASE, timeout=2) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        else:
            raise TimeoutError('Port-8001 server did not become ready.')
        restore_discovery(original_discovery)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(OUT / 'chrome-profile'), channel='chrome', headless=False,
                no_viewport=True, chromium_sandbox=True, slow_mo=250,
                accept_downloads=True, args=['--start-maximized'])
            page = context.pages[0] if context.pages else context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.bring_to_front()
            visibility_gate('browser', page)
            # Angela may already have signed in while verifying visibility.
            # Visiting the protected panel lets Django decide whether login is needed.
            page.goto(BASE + '/agent/agentic_control_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type="submit"], input[type="submit"]').first.click()
                page.goto(BASE + '/agent/agentic_control_panel/')
            page.locator('#acp-agent-search').wait_for()
            print('Normal authenticated panel available for:', credentials['username'], flush=True)
            credentials.clear()

            def checkpoint(name):
                page.bring_to_front()
                page.wait_for_timeout(1800)
                photograph(name)
                results.append({'name': name, 'status': 'passed', 'title': page.title(),
                                'url': page.url, 'screenshot': name + '.png'})
                (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, '| title:', page.title(), flush=True)

            def title_dirty(dirty):
                page.wait_for_function('dirty => document.title.startsWith("• ") === dirty', arg=dirty)

            page.goto(BASE + '/agent/agentic_control_panel/')
            search = page.locator('#acp-agent-search')
            search.fill('sTm32')
            expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)
            all_names = page.locator('#agents-list .agent-tool-item').all_text_contents()
            shown = page.locator('#agents-list .agent-tool-item:visible')
            assert len(all_names) > 20, 'The normal catalog did not load.'
            expect(shown).to_have_text(['STM32er'])
            title_dirty(False)
            checkpoint('01-agent-search-during-catalog-load')
            search.fill('  file  ')
            expected = [name for name in all_names if 'file' in name.lower()]
            assert expected
            expect(shown).to_have_text(expected)
            checkpoint('02-agent-search-substring')
            search.fill('no-such-agent-visual-check')
            expect(shown).to_have_count(0)
            expect(page.locator('#acp-agent-search-empty')).to_be_visible()
            checkpoint('03-agent-search-no-match')
            search.fill('')
            expect(shown).to_have_text(all_names)
            expect(page.locator('#acp-agent-search-empty')).to_be_hidden()
            title_dirty(False)
            checkpoint('04-agent-search-cleared')

            search.fill('sleeper')
            page.locator('#agents-list .agent-tool-item:visible').drag_to(
                page.locator('#submonitor-container'), target_position={'x': 350, 'y': 190})
            expect(page.locator('.canvas-item')).to_have_count(1)
            title_dirty(True)
            checkpoint('05-acp-unsaved-title')
            page.get_by_role('button', name='File', exact=True).click()
            page.once('dialog', lambda dialog: dialog.accept('acp-title-check.flw'))
            with page.expect_download() as downloaded:
                page.locator('#save-as-button').click()
            flw = OUT / 'acp-title-check.flw'
            downloaded.value.save_as(flw)
            assert json.loads(flw.read_text(encoding='utf-8'))['nodes']
            title_dirty(False)
            checkpoint('06-acp-saved-title')
            search.fill('sleeper')
            search.press('Control+A')
            search.press('Backspace')
            expect(page.locator('.canvas-item')).to_have_count(1)
            title_dirty(False)
            box = page.locator('.canvas-item').bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2 + 100, box['y'] + box['height'] / 2 + 40, steps=15)
            page.mouse.up()
            title_dirty(True)
            checkpoint('07-acp-edited-title')
            page.get_by_role('button', name='File', exact=True).click()
            with page.expect_file_chooser() as chooser:
                page.locator('#file-open-button').click()
            chooser.value.set_files(str(flw))
            title_dirty(False)
            checkpoint('08-acp-opened-title')

            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE + '/agent/prompt_flow_panel/')
            expect(page.locator('#pmt-search, #acp-agent-search')).to_have_count(0)
            title_dirty(False)
            checkpoint('09-pmt-clean-title')
            page.locator('.agent-tool-item[data-type="user_commentary"]').click()
            title_dirty(True)
            checkpoint('10-pmt-unsaved-title')
            page.get_by_role('button', name='File', exact=True).click()
            page.locator('[data-action="save"]').click()
            page.locator('#pmt-field-filename').fill('pmt-title-check.fpmt')
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='Download .fpmt', exact=True).click()
            pmt = OUT / 'pmt-title-check.fpmt'
            downloaded.value.save_as(pmt)
            assert json.loads(pmt.read_text(encoding='utf-8'))['nodes']
            title_dirty(False)
            checkpoint('11-pmt-saved-title')
            page.locator('#submonitor-container').focus()
            page.keyboard.press('ArrowRight')
            title_dirty(True)
            checkpoint('12-pmt-edited-title')
            page.keyboard.press('Control+z')
            title_dirty(False)
            checkpoint('13-pmt-undo-to-saved-title')
            page.get_by_role('button', name='File', exact=True).click()
            with page.expect_file_chooser() as chooser:
                page.locator('[data-action="open"]').click()
            chooser.value.set_files(str(pmt))
            title_dirty(False)
            checkpoint('14-pmt-opened-title')
            assert not errors, errors
            print('ALL 14 VISUAL CHECKPOINTS PASSED. Holding the visible browser for inspection.', flush=True)
            page.wait_for_timeout(15000)
            context.close()
        outcome = 0
    except Exception:
        traceback.print_exc()
        try:
            photograph('failure')
        except Exception:
            traceback.print_exc()
    finally:
        stop_server(server)
        restore_discovery(original_discovery)
        after = listeners()
        if after.get(8000) != before.get(8000):
            print('Port 8000 changed while testing; inspect before attributing the change.', flush=True)
            outcome = 1
        summary = {'exit_code': outcome, 'checks': results, 'before_ports': before,
                   'after_ports': after, 'mode': 'normal source installation on port 8001',
                   'account': 'user', 'mocked_transports': False}
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print('VISUAL TEST EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
