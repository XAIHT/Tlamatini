# Tlamatini Author Banner — Angela López Mendoza
"""Exercise the real Prompt Flow Panel file format in visible Chrome on port 8001.

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
OUT = ROOT / 'Temp/fpmt-extension-visible'
BASE = visible.BASE
visible.OUT = OUT
visible.RUNTIME = ROOT / 'Temp/panel-search-title-visible/runtime'
ASSETS = [
    'agent/templates/agent/prompt_flow_panel.html',
    'agent/static/agent/js/prompt-flow-panel.js',
    'agent/static/agent/js/prompt-flow-panel-model.js',
    'agent/static/agent/js/agent_page_canvas.js',
    'agent/services/prompt_flow_panel.py',
    'agent/prompt_flow_panel_consumer.py',
    'agent/management/commands/check_prompt_flow_panel.py',
    'agent/rag/binary_guard.py', 'tlamatini/settings.py',
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
            page.goto(BASE + '/agent/prompt_flow_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type=submit]').click()
                page.goto(BASE + '/agent/prompt_flow_panel/')
            credentials.clear()
            page.on('dialog', lambda dialog: dialog.accept())

            def checkpoint(name):
                page.bring_to_front()
                page.wait_for_timeout(1800)
                visible.photograph(name)
                results.append({'name': name, 'screenshot': name + '.png'})
                (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, flush=True)

            def menu(action):
                page.get_by_role('button', name='File', exact=True).click()
                page.locator('[data-action="' + action + '"]').first.click()

            def open_file(path):
                page.get_by_role('button', name='File', exact=True).click()
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="open"]').click()
                chooser.value.set_files(str(path))

            def save_file(name=None, expected=None):
                menu('save')
                field = page.locator('#pmt-field-filename')
                if name is not None:
                    field.fill(name)
                with page.expect_download() as downloaded:
                    page.get_by_role('button', name='Download .fpmt', exact=True).click()
                download = downloaded.value
                assert download.suggested_filename == expected, download.suggested_filename
                path = OUT / expected
                download.save_as(path)
                expect(page.locator('#filename')).to_have_text(expected)
                page.wait_for_function('!document.title.startsWith("•")')
                return path

            def reject_file(path, message, checkpoint_name):
                previous = page.locator('#filename').inner_text()
                node_count = page.locator('.pmt-node').count()
                open_file(path)
                expect(page.locator('.tlmpop-overlay')).to_be_visible()
                expect(page.locator('.tlmpop-overlay')).to_contain_text(message)
                expect(page.locator('#filename')).to_have_text(previous)
                expect(page.locator('.pmt-node')).to_have_count(node_count)
                checkpoint(checkpoint_name)
                page.keyboard.press('Escape')
                expect(page.locator('.tlmpop-overlay')).to_have_count(0)

            expect(page.locator('#filename')).to_have_text('Untitled.fpmt')
            expect(page.locator('#pmt-file-input')).to_have_attribute('accept', '.fpmt')
            page.get_by_role('button', name='File', exact=True).click()
            expect(page.locator('[data-action="open"]')).to_contain_text('Open .fpmt')
            expect(page.locator('[data-action="save"]')).to_contain_text('Save as .fpmt')
            checkpoint('01-menus-and-file-filter')
            page.keyboard.press('Escape')
            blank = save_file(expected='Untitled.fpmt')
            assert json.loads(blank.read_text(encoding='utf-8'))['nodes'] == []
            checkpoint('02-default-download')

            page.locator('.agent-tool-item[data-type="user_input"]').click()
            expect(page.locator('.pmt-node')).to_have_count(1)
            portable = save_file('roundtrip', 'roundtrip.fpmt')
            snapshot = json.loads(portable.read_text(encoding='utf-8'))
            assert snapshot['format'] == 'tlamatini-prompting-flow' and len(snapshot['nodes']) == 1
            checkpoint('03-save-appends-fpmt')
            converted = save_file('previous-name.pmt', 'previous-name.fpmt')
            assert json.loads(converted.read_text(encoding='utf-8')) == snapshot
            checkpoint('04-legacy-save-name-converted')

            uppercase = OUT / 'Unicode-ñ.FPMT'
            uppercase.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8-sig')
            open_file(uppercase)
            expect(page.locator('#filename')).to_have_text(uppercase.name)
            expect(page.locator('.pmt-node')).to_have_count(1)
            save_file(expected=uppercase.name)
            checkpoint('05-uppercase-bom-and-unicode')
            open_file(portable)
            expect(page.locator('#filename')).to_have_text('roundtrip.fpmt')
            expect(page.locator('#pmt-play')).to_be_enabled()
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            page.locator('#pmt-field-reply').fill('Real .fpmt playback: ñ ✓')
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            expect(page.locator('#pmt-run-log')).to_contain_text('Real .fpmt playback: ñ ✓')
            checkpoint('06-reopened-file-real-playback')

            sample = ROOT / 'docs/examples/prompting-kickoff.fpmt'
            open_file(sample)
            expect(page.locator('.pmt-node')).to_have_count(8)
            expect(page.locator('#filename')).to_have_text(sample.name)
            checkpoint('07-bundled-example-opens')
            invalid = OUT / 'invalid.fpmt'
            invalid.write_text('{bad JSON', encoding='utf-8')
            reject_file(invalid, 'Could not open invalid.fpmt', '08-invalid-json-preserves-flow')
            old = OUT / 'old-flow.pmt'
            old.write_text(json.dumps(snapshot), encoding='utf-8')
            reject_file(old, 'Choose a .fpmt Prompt Flow Panel file.', '09-old-extension-rejected')
            reject_file(ROOT / 'Tlamatini/agent/prompt.pmt', 'Choose a .fpmt Prompt Flow Panel file.', '10-system-prompt-remains-separate')
            wrong = OUT / 'wrong-version.fpmt'
            wrong.write_text(json.dumps({**snapshot, 'version': 99}), encoding='utf-8')
            reject_file(wrong, 'Unsupported .fpmt version.', '11-version-error-uses-fpmt')
            oversized = OUT / 'oversized.fpmt'
            oversized.write_text(' ' * (5 * 1024 * 1024 + 1), encoding='utf-8')
            reject_file(oversized, 'The .fpmt file must be smaller than 5 MiB.', '12-size-error-uses-fpmt')

            menu('new')
            expect(page.locator('#filename')).to_have_text('Untitled.fpmt')
            expect(page.locator('#pmt-empty')).to_be_visible()
            page.locator('#pmt-empty [data-action="example"]').click()
            expect(page.locator('#filename')).to_have_text('Prompting kickoff.fpmt •')
            expect(page.locator('.pmt-node')).to_have_count(4)
            checkpoint('13-new-and-generated-example')
            page.wait_for_timeout(500)
            page.reload()
            expect(page.locator('#filename')).to_have_text('Prompting kickoff.fpmt •')
            expect(page.locator('#pmt-status')).to_contain_text('Save a .fpmt file')
            expect(page.locator('.pmt-node')).to_have_count(4)
            checkpoint('14-recovered-draft')
            # The same pure filename function migrates existing draft names.
            assert page.evaluate("window.PromptFlowPanelModel.flowFilename('Recovered.pmt')") == 'Recovered.fpmt'
            page.locator('[data-action="help"]').click()
            expect(page.locator('.tlmpop-overlay')).to_contain_text('Save downloads a versioned .fpmt diagram.')
            expect(page.locator('.tlmpop-overlay')).to_contain_text('prompt.pmt text files remain separate')
            checkpoint('15-help-distinguishes-formats')
            page.keyboard.press('Escape')
            assert not errors, errors
            print('ALL FPMT EXTENSION VISUAL CHECKS PASSED.', flush=True)
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
        print('FPMT EXTENSION EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
