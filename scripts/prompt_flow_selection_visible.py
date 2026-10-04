# Tlamatini Author Banner — Angela López Mendoza
"""Exercise Prompt Flow Panel selection and status colors in visible Chrome on port 8001.

Launch from a verified foreground PowerShell -NoExit console. Shoter records
the whole desktop. Uses the dedicated normal installation from the earlier
panel checks, with current source assets; never intercepts app traffic or
injects application state. The user's port-8000 process is left running.
"""
import json
import re
import shutil
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible

ROOT = visible.ROOT
OUT = ROOT / 'Temp/prompt-selection-docs-visible'
BASE = visible.BASE
visible.OUT = OUT
visible.RUNTIME = ROOT / 'Temp/panel-search-title-visible/runtime'
ASSETS = [
    'agent/static/agent/css/prompt_flow_panel.css',
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
                str(OUT / 'chrome-profile'), channel='chrome',
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

            def gold(node, status_color=None):
                expect(node).to_have_class(re.compile(r'\bselected\b'))
                expect(node.locator('.pmt-shape')).to_have_css('stroke', status_color or 'rgb(255, 204, 0)')
                expect(node.locator('svg')).to_have_css('filter', 'drop-shadow(rgba(255, 204, 0, 0.7) 0px 0px 5px)')

            # Use an ordinary file-open action, with all eight shapes from the shipped example.
            page.get_by_role('button', name='File', exact=True).click()
            with page.expect_file_chooser() as chooser:
                page.locator('[data-action="open"]').click()
            chooser.value.set_files(str(ROOT / 'docs/examples/prompting-kickoff.fpmt'))
            confirm = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
            if confirm.is_visible():
                confirm.click()
            expect(page.locator('.pmt-node')).to_have_count(8)
            page.locator('[data-action="fit"]').click()
            page.wait_for_function('!document.title.startsWith("•")')
            css_url = page.locator('link[href*="/css/prompt_flow_panel.css"]').get_attribute('href')
            assert '-prompt-commentary-input-1' in css_url, css_url
            delivered = page.request.get(BASE + css_url)
            assert delivered.ok and delivered.body() == (ROOT / 'Tlamatini/agent/static/agent/css/prompt_flow_panel.css').read_bytes()
            positions = page.locator('.pmt-node').evaluate_all('(nodes) => nodes.map(n => [n.dataset.nodeId, n.style.left, n.style.top])')
            for number, kind in enumerate(('prompt', 'programmed_prompt', 'decision', 'feed_embeddings', 'flush_embeddings', 'clean_history', 'user_input', 'user_commentary'), 1):
                node = page.locator('.pmt-node[data-type="' + kind + '"]')
                node.click(position={'x': 100, 'y': 64})
                expect(page.locator('.pmt-node.selected')).to_have_count(1)
                gold(node)
                checkpoint(f'{number:02d}-selected-{kind}')

            page.locator('.pmt-node[data-type="decision"]').click(modifiers=['Control'])
            expect(page.locator('.pmt-node.selected')).to_have_count(2)
            for node in page.locator('.pmt-node.selected').all():
                gold(node)
            checkpoint('08-ctrl-click-multiple')
            page.keyboard.press('Control+a')
            expect(page.locator('.pmt-node.selected')).to_have_count(8)
            for node in page.locator('.pmt-node.selected').all():
                gold(node)
            checkpoint('09-select-all-eight-shapes')
            page.locator('[data-action="zoom-in"]').click()
            for node in page.locator('.pmt-node.selected').all():
                gold(node)
            checkpoint('10-selected-after-zoom')
            page.keyboard.press('Escape')
            expect(page.locator('.pmt-node.selected')).to_have_count(0)
            for node in page.locator('.pmt-node').all():
                expect(node.locator('svg')).to_have_css('filter', 'drop-shadow(rgba(0, 0, 0, 0.533) 0px 4px 4px)')
            checkpoint('11-selection-cleared')
            page.locator('[data-action="fit"]').click()
            edge = page.locator('.pmt-edge[data-edge-id="subject_explain"]')
            midpoint = edge.locator('.pmt-wire').evaluate('(path) => { const p = path.getPointAtLength(path.getTotalLength()/2); const q = new DOMPoint(p.x,p.y).matrixTransform(path.getScreenCTM()); return {x:q.x,y:q.y}; }')
            page.mouse.click(midpoint['x'], midpoint['y'])
            expect(edge).to_have_class(re.compile(r'\bselected\b'))
            expect(edge.locator('.pmt-wire')).to_have_css('stroke', 'rgb(255, 204, 0)')
            expect(edge.locator('.pmt-wire')).to_have_css('filter', 'drop-shadow(rgba(255, 204, 0, 0.8) 0px 0px 4px)')
            checkpoint('12-selected-connection')
            assert positions == page.locator('.pmt-node').evaluate_all('(nodes) => nodes.map(n => [n.dataset.nodeId, n.style.left, n.style.top])')
            assert not page.title().startswith('•'), 'Selecting and zooming must not dirty the flow.'

            # Real model-free playback verifies that selection does not erase status colors.
            menu('new')
            expect(page.locator('.pmt-node')).to_have_count(0)
            page.locator('.agent-tool-item[data-type="user_input"]').click()
            node = page.locator('.pmt-node')
            gold(node)
            expect(page.locator('#pmt-play')).to_be_enabled()
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            gold(node, 'rgb(250, 204, 21)')
            page.locator('#pmt-field-reply').fill('Selection glow verified through real playback.')
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            gold(node, 'rgb(74, 222, 128)')
            checkpoint('13-completed-status-with-selection-glow')
            page.keyboard.press('Escape')
            expect(page.locator('.pmt-node.selected')).to_have_count(0)
            expect(node.locator('.pmt-shape')).to_have_css('stroke', 'rgb(74, 222, 128)')
            checkpoint('14-completed-status-without-selection')
            assert not errors, errors
            print('ALL PROMPT FLOW SELECTION VISUAL CHECKS PASSED.', flush=True)
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
        print('PROMPT FLOW SELECTION EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
