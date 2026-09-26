# Tlamatini Author Banner — Angela López Mendoza
"""Exercise the real ACP editor in visible Chrome on port 8001.

Launch from a verified foreground PowerShell -NoExit console. Shoter records
the whole desktop. Uses the dedicated normal installation from the earlier
panel checks, with current source assets; never intercepts app traffic or
injects application state. The user's port-8000 process is left running.
"""
import json
import shutil
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible

ROOT = visible.ROOT
OUT = ROOT / 'Temp/acp-toolbar-visible'
BASE = visible.BASE
visible.OUT = OUT
visible.RUNTIME = ROOT / 'Temp/panel-search-title-visible/runtime'
ASSETS = [
    'agent/templates/agent/agentic_control_panel.html',
    'agent/static/agent/css/agentic_control_panel.css',
    *['agent/static/agent/js/' + name for name in (
        'acp-globals.js', 'acp-canvas-core.js', 'acp-canvas-undo.js',
        'acp-undo-manager.js', 'acp-running-state.js', 'acp-file-io.js', 'acp-editor-tools.js')],
    'tlamatini/settings.py',
]


def main():
    if any('headless' in arg for arg in sys.argv):
        raise SystemExit('Headless execution is forbidden.')
    if not (OUT / 'console.confirmed').exists():
        raise SystemExit('First verify the foreground work console with Shoter.')
    before = visible.listeners()
    if 8001 in before:
        raise SystemExit('Port 8001 is occupied; refusing to replace an existing server.')
    original = visible.read_discovery()
    server = None
    results = []
    outcome = 1
    try:
        for asset in ASSETS:
            shutil.copy2(ROOT / 'Tlamatini' / asset, visible.RUNTIME / 'Tlamatini' / asset)
        sys.argv.append('--resume')
        env, credentials = visible.prepare_runtime()
        server = visible.start_server(env)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(BASE, timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError):
                time.sleep(1)
        else:
            raise TimeoutError('The test server did not become ready.')
        visible.restore_discovery(original)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(OUT / ('chrome-' + str(time.time_ns()))), channel='chrome',
                headless=False, chromium_sandbox=True, no_viewport=True, slow_mo=250,
                accept_downloads=True, args=['--start-maximized'])
            page = context.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.bring_to_front()
            visible.visibility_gate('browser', page)
            page.goto(BASE + '/agent/agentic_control_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type=submit]').click()
                page.goto(BASE + '/agent/agentic_control_panel/')
            credentials.clear()
            expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)

            def checkpoint(name):
                page.bring_to_front()
                page.wait_for_timeout(1800)
                visible.photograph(name)
                results.append({'name': name, 'title': page.title(), 'screenshot': name + '.png'})
                (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, flush=True)

            def click(selector):
                page.locator(selector).click()

            def count(number):
                expect(page.locator('.canvas-item')).to_have_count(number)
                expect(page.locator('#acp-flow-settings')).to_be_enabled()

            def configure(agent, value=None):
                click('#' + agent)
                click('#acp-configure')
                field = page.locator('#canvas-item-list [data-key="duration_ms"]')
                expect(field).to_be_visible()
                if value is None:
                    return field
                field.fill(str(value))
                page.get_by_role('dialog', name='Properties: ' + agent, exact=True).get_by_role('button', name='Save', exact=True).click()
                expect(page.locator('#deployment-result-dialog')).to_be_visible()
                page.keyboard.press('Escape')

            expect(page.locator('#acp-empty')).to_be_visible()
            for control in ('undo', 'redo', 'configure', 'duplicate', 'delete'):
                expect(page.locator('#acp-' + control)).to_be_disabled()
            assert 'radial-gradient' in page.locator('#canvas-content').evaluate('e => getComputedStyle(e).backgroundImage')
            checkpoint('01-empty-dotted-canvas')
            click('#acp-help')
            expect(page.get_by_role('dialog', name='Agentic Control Panel — Help')).to_be_visible()
            checkpoint('02-help')
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog', name='Agentic Control Panel — Help')).to_have_count(0)

            click('#acp-flow-settings')
            page.locator('#acp-setting-grid').uncheck()
            page.locator('#acp-setting-zoom').select_option('1.2')
            page.get_by_role('button', name='Apply', exact=True).click()
            expect(page.locator('#acp-zoom-label')).to_have_text('120%')
            assert page.locator('#canvas-content').evaluate('e => getComputedStyle(e).backgroundImage') == 'none'
            assert not page.title().startswith('•')
            checkpoint('03-canvas-preferences')
            click('#acp-flow-settings')
            page.locator('#acp-setting-grid').check()
            page.locator('#acp-setting-zoom').select_option('1')
            page.get_by_role('button', name='Apply', exact=True).click()

            click('#acp-example')
            count(3)
            expect(page.locator('.connection-group')).to_have_count(2)
            expect(page.locator('#acp-empty')).to_be_hidden()
            expect(page.locator('#acp-starter-select option')).to_have_count(2)
            checkpoint('04-connected-example')
            configure('sleeper-1', 2000)
            checkpoint('05-agent-configured')
            click('#acp-duplicate')
            count(4)
            expect(configure('sleeper-2')).to_have_value('2000')
            page.keyboard.press('Escape')
            checkpoint('06-duplicate-retains-config')
            click('#acp-undo')
            count(3)
            click('#acp-redo')
            count(4)
            click('#sleeper-2')
            click('#acp-delete')
            count(3)
            click('#acp-undo')
            count(4)
            expect(configure('sleeper-2')).to_have_value('2000')
            page.keyboard.press('Escape')
            click('#acp-redo')
            count(3)
            checkpoint('07-undo-redo-delete')

            click('#starter-1')
            page.locator('#sleeper-1').click(modifiers=['Control'])
            click('#acp-duplicate')
            count(5)
            expect(page.locator('.connection-group')).to_have_count(3)
            checkpoint('08-duplicate-connected-selection')
            click('#acp-undo')
            count(3)
            click('#acp-redo')
            count(5)
            click('#acp-undo')
            count(3)

            click('#acp-zoom-in')
            click('#acp-zoom-in')
            expect(page.locator('#acp-zoom-label')).to_have_text('120%')
            node = page.locator('#sleeper-1')
            old_left = node.evaluate('e => e.offsetLeft')
            box = node.bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2 + 120, box['y'] + box['height'] / 2 + 60, steps=12)
            page.mouse.up()
            assert abs(node.evaluate('e => e.offsetLeft') - old_left - 100) <= 2
            checkpoint('09-drag-at-120-percent')
            click('#acp-undo')
            assert abs(node.evaluate('e => e.offsetLeft') - old_left) <= 1
            click('#acp-redo')
            assert abs(node.evaluate('e => e.offsetLeft') - old_left - 100) <= 2
            click('#acp-fit')
            expect(page.locator('#acp-zoom-label')).to_have_text('100%')
            page.locator('#acp-starter-select').select_option('starter-1')
            expect(page.locator('#starter-1')).to_have_class(__import__('re').compile(r'.*\bselected\b.*'))
            checkpoint('10-fit-and-starter-selector')

            click('#acp-zoom-in')
            search = page.locator('#acp-agent-search')
            search.fill('sleeper')
            viewport = page.locator('#submonitor-container')
            page.locator('#agents-list .agent-tool-item:visible').drag_to(viewport, target_position={'x': 380, 'y': 360})
            count(4)
            new_node = page.locator('.canvas-item.sleeper-agent').last
            # Draw a new real edge with the mouse at the scaled connector centers.
            source = page.locator('#starter-1 .output-triangle').bounding_box()
            target = new_node.locator('.input-triangle').bounding_box()
            page.mouse.move(source['x'] + source['width'] / 2, source['y'] + source['height'] / 2)
            page.mouse.down()
            page.mouse.move(target['x'] + target['width'] / 2, target['y'] + target['height'] / 2, steps=12)
            page.mouse.up()
            expect(page.locator('.connection-group')).to_have_count(3)
            checkpoint('11-drop-and-connect-while-zoomed')

            page.get_by_role('button', name='File', exact=True).click()
            page.once('dialog', lambda dialog: dialog.accept('acp-editor-check.flw'))
            with page.expect_download() as download:
                click('#save-as-button')
            saved = OUT / 'acp-editor-check.flw'
            download.value.save_as(saved)
            snapshot = json.loads(saved.read_text(encoding='utf-8'))
            assert len(snapshot['nodes']) == 4 and len(snapshot['connections']) == 3
            page.wait_for_function('!document.title.startsWith("•")')
            checkpoint('12-saved-original-coordinates')
            click('#acp-zoom-out')
            page.get_by_role('button', name='File', exact=True).click()
            with page.expect_file_chooser() as chooser:
                click('#file-open-button')
            chooser.value.set_files(str(saved))
            count(4)
            page.wait_for_function('!document.title.startsWith("•")')
            expect(page.locator('#acp-undo')).to_be_disabled()
            checkpoint('13-opened-flow')
            page.get_by_role('button', name='File', exact=True).click()
            click('#file-close-button')
            count(0)
            expect(page.locator('#acp-empty')).to_be_visible()
            expect(page.locator('#acp-undo')).to_be_disabled()
            checkpoint('14-close-restores-welcome')
            click('#acp-example')
            count(3)
            click('#acp-undo')
            count(0)
            expect(page.locator('#acp-empty')).to_be_visible()
            click('#acp-redo')
            count(3)
            expect(page.locator('.connection-group')).to_have_count(2)
            checkpoint('15-undo-redo-example')
            click('#acp-flow-settings')
            page.get_by_role('button', name='Configure Starter (1)', exact=True).click()
            expect(page.get_by_role('dialog', name='Properties: starter-1', exact=True)).to_be_visible()
            page.keyboard.press('Escape')
            checkpoint('16-orchestration-settings')
            search.fill('flowhypervisor')
            page.locator('#agents-list .agent-tool-item:visible').drag_to(viewport, target_position={'x': 330, 'y': 360})
            count(4)
            click('#flowhypervisor')
            expect(page.locator('#acp-duplicate')).to_be_disabled()
            checkpoint('17-singleton-duplicate-guard')
            click('#acp-undo')
            count(3)
            # Search keyboard input must never trigger a canvas command.
            search.fill('sleeper')
            search.press('Control+z')
            count(3)
            search.fill('')
            assert not errors, errors
            print('ALL ACP EDITOR VISUAL CHECKS PASSED.', flush=True)
            page.wait_for_timeout(10000)
            context.close()
        outcome = 0
    except Exception:
        traceback.print_exc()
        visible.photograph('failure')
    finally:
        visible.stop_server(server)
        visible.restore_discovery(original)
        after = visible.listeners()
        if after.get(8000) != before.get(8000):
            outcome = 1
            print('Port-8000 process changed during the run.', flush=True)
        (OUT / 'summary.json').write_text(json.dumps({
            'exit_code': outcome, 'checks': results, 'before_ports': before,
            'after_ports': after, 'account': 'user', 'mocked_transports': False,
            'mode': 'normal source installation on port 8001'
        }, indent=2), encoding='utf-8')
        print('ACP EDITOR EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
