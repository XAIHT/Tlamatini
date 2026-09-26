# Tlamatini Author Banner — Angela López Mendoza
"""Verify ACP/Prompt Flow connector parity in VISIBLE Chrome on port 8001.

Launch in a verified foreground PowerShell -NoExit console. Every checkpoint
uses Shoter (all_screens=True). The browser waits for actual visibility review
before interaction. No headless fallback, transport mocks or injected app state.
Reuses the separate normal installation created by panel_search_title_visible.
"""
import ctypes
import json
import re
import shutil
import sys
import time
import traceback
import urllib.request

from playwright.sync_api import expect, sync_playwright
import panel_search_title_visible as visible
from flow_canvas_mechanics_visible import check_editor

ROOT = visible.ROOT
OUT = ROOT / 'Temp/prompt-connections-visible'
BASE = visible.BASE
visible.OUT = OUT
visible.RUNTIME = ROOT / 'Temp/panel-search-title-visible/runtime'
ASSETS = (
    'agent/static/agent/js/contextual_menus.js',
    'agent/static/agent/css/flow_canvas.css',
    'agent/static/agent/js/flow-canvas-interactions.js',
    'agent/static/agent/js/acp-canvas-core.js',
    'agent/static/agent/js/acp-canvas-undo.js',
    'agent/static/agent/js/acp-editor-tools.js',
    'agent/static/agent/js/acp-layout.js',
    'agent/templates/agent/agentic_control_panel.html',
    'agent/static/agent/css/agentic_control_panel.css',
    'agent/static/agent/css/prompt_flow_panel.css',
    'agent/static/agent/js/prompt-flow-panel.js',
    'agent/static/agent/js/prompt-flow-panel-model.js',
    'agent/templates/agent/prompt_flow_panel.html',
    'tlamatini/settings.py',
)
PROFILE = None
TEST_BROWSER_WINDOW = None


def require_browser_foreground(page):
    """Pause when another desktop window covers Chrome; never claim it was watched."""
    global TEST_BROWSER_WINDOW
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    title = ctypes.create_unicode_buffer(1024)
    # The ACP deliberately scrolls its title. Identify the verified window once,
    # then keep checking its actual handle instead of comparing an animated title.
    expected = page.title() if TEST_BROWSER_WINDOW is None else None
    deadline = time.monotonic() + 300
    last_notice = 0
    while time.monotonic() < deadline:
        window = user32.GetForegroundWindow()
        user32.GetWindowTextW(window, title, len(title))
        if user32.IsWindowVisible(window) and not user32.IsIconic(window):
            if TEST_BROWSER_WINDOW is None and title.value.startswith(expected) and 'Google Chrome' in title.value:
                TEST_BROWSER_WINDOW = window
            if window == TEST_BROWSER_WINDOW:
                return
        if time.monotonic() - last_notice > 10:
            print('PAUSED: restore the visible test Chrome window before continuing.', flush=True)
            last_notice = time.monotonic()
        time.sleep(.25)
    raise RuntimeError('Browser foreground visibility was not restored; verification refused.')


def main():
    if any('headless' in arg for arg in sys.argv):
        raise SystemExit('Headless execution is forbidden.')
    OUT.mkdir(parents=True, exist_ok=True)
    visible.visibility_gate('console')
    before = visible.listeners()
    if any(port in before for port in (8001, 8766, 50052)):
        raise SystemExit('Test ports are occupied; refusing to replace a server.')
    original = visible.read_discovery()
    server = None
    results = []
    outcome = 1
    try:
        for asset in ASSETS:
            shutil.copy2(ROOT / 'Tlamatini' / asset, visible.RUNTIME / 'Tlamatini' / asset)
        shutil.copy2(ROOT / 'Temp/panel-search-title-visible/login.json', OUT / 'login.json')
        sys.argv.append('--resume')
        env, credentials = visible.prepare_runtime()
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
        profile = PROFILE or OUT / 'chrome-profile'
        preferences = profile / 'Default' / 'Preferences'
        if not preferences.exists():
            preferences.parent.mkdir(parents=True, exist_ok=True)
            preferences.write_text(json.dumps({'credentials_enable_service': False,
                'profile': {'password_manager_enabled': False}}), encoding='utf-8')
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile), channel='chrome', headless=False,
                chromium_sandbox=True, no_viewport=True, slow_mo=120,
                accept_downloads=True, args=['--start-maximized'])
            page = context.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE)
            page.bring_to_front()
            page.wait_for_timeout(1500)
            visible.visibility_gate('browser', page)
            require_browser_foreground(page)
            page.goto(BASE + '/agent/agentic_control_panel/')
            if page.locator('#id_username').is_visible():
                page.locator('#id_username').fill(credentials['username'])
                page.locator('#id_password').fill(credentials['password'])
                page.locator('button[type=submit]').click()
                page.goto(BASE + '/agent/agentic_control_panel/')
            credentials.clear()
            page.wait_for_timeout(1500)
            page.keyboard.press('Escape')

            def checkpoint(name):
                page.bring_to_front()
                page.wait_for_timeout(600)
                require_browser_foreground(page)
                visible.photograph(name)
                results.append({'name': name, 'screenshot': name + '.png'})
                (OUT / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                print('PASS:', name, flush=True)

            def center(locator):
                require_browser_foreground(page)
                box = locator.bounding_box()
                assert box, 'Element has no visible bounds'
                return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2

            def drag(source, target):
                page.mouse.move(*center(source))
                page.mouse.down()
                page.mouse.move(*center(target), steps=12)
                page.mouse.up()

            style = """el => {
                const s = getComputedStyle(el);
                return Object.fromEntries(['borderTopWidth', 'borderBottomWidth',
                    'borderLeftWidth', 'borderTopColor', 'borderBottomColor',
                    'borderLeftColor', 'borderRadius', 'backgroundColor', 'filter', 'outlineWidth', 'cursor'].map(k => [k,s[k]]));
            }"""
            expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)
            page.locator('#acp-example').click()
            try:
                expect(page.locator('.canvas-item')).to_have_count(3, timeout=15000)
            except Exception:
                visible.photograph('example-before-error')
                print('VISIBLE ALERTS:', page.locator('.tlmpop-overlay, .ui-dialog:visible').all_text_contents(), flush=True)
                raise
            expect(page.locator('#acp-flow-settings')).to_be_enabled()
            expect(page.locator('.connection-group')).to_have_count(2)
            acp_source = page.locator('#starter-1 .output-triangle')
            acp_target = page.locator('#ender-1 .input-triangle')
            acp_source.hover()
            acp_hover = acp_source.evaluate(style)
            page.mouse.down()
            page.mouse.move(*center(acp_target), steps=12)
            acp_source_active = acp_source.evaluate(style)
            acp_target_active = acp_target.evaluate(style)
            expect(acp_source).to_have_class(re.compile('connecting-source'))
            expect(acp_target).to_have_class(re.compile('connecting-target'))
            checkpoint('01a-agentic-drag-source-and-target-glow')
            page.keyboard.press('Escape')
            page.mouse.up()
            expect(page.locator('.connection-preview, .connecting-source, .connecting-target')).to_have_count(0)
            expect(page.locator('.connection-group')).to_have_count(2)
            drag(acp_source, acp_target)
            expect(page.locator('.connection-group')).to_have_count(3)
            page.mouse.move(30, 100)
            acp_input = page.locator('.canvas-item .input-triangle').first.evaluate(style)
            acp_output = page.locator('.canvas-item .output-triangle').first.evaluate(style)
            acp_wire = page.locator('.connection-path').first.evaluate(
                'el => ({stroke:getComputedStyle(el).stroke,width:getComputedStyle(el).strokeWidth})')
            checkpoint('01-agentic-reference-drag-and-triangles')

            wire_style = 'el => ({stroke:getComputedStyle(el).stroke,width:getComputedStyle(el).strokeWidth,filter:getComputedStyle(el).filter})'
            def wire_point(locator):
                return locator.evaluate('''el => {
                    const p=el.getPointAtLength(el.getTotalLength() / 2);
                    const q=new DOMPoint(p.x,p.y).matrixTransform(el.getScreenCTM());
                    return [q.x,q.y];
                }''')
            page.mouse.move(*wire_point(page.locator('.connection-hit-area').first))
            acp_wire_hover = page.locator('.connection-group:hover .connection-path').last.evaluate(wire_style)
            page.mouse.down(); page.mouse.up()
            acp_wire_selected = page.locator('.connection-group.selected .connection-path').evaluate(wire_style)
            checkpoint('01b-agentic-hover-and-selected-wire-glow')
            page.keyboard.press('Escape')
            page.locator('#starter-1').click()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#starter-1')).to_have_css('left', '110px')
            page.keyboard.press('Control+z')
            expect(page.locator('#starter-1')).to_have_css('left', '100px')
            page.keyboard.press('Control+d')
            expect(page.locator('.canvas-item')).to_have_count(4)
            expect(page.locator('#acp-undo')).to_be_enabled()
            page.keyboard.press('Control+z')
            expect(page.locator('.canvas-item')).to_have_count(3)
            checkpoint('01c-agentic-keyboard-move-duplicate-and-undo')
            page.locator('#starter-1').click(button='right')
            expect(page.locator('#agent-context-menu')).to_be_visible()
            expect(page.locator('#ctx-menu-duplicate')).to_be_visible()
            page.keyboard.press('Escape')

            check_editor(page, False, checkpoint, center)
            page.locator('#acp-agent-search').fill('Asker')
            page.locator('#agents-list .agent-tool-item:visible').drag_to(page.locator('#submonitor-container'), target_position={'x': 430, 'y': 360})
            expect(page.locator('.canvas-item')).to_have_count(4)
            second = page.locator('#asker-1 .output-2')
            page.mouse.move(*center(second)); page.mouse.down()
            page.mouse.move(*center(page.locator('#ender-1 .input-triangle')), steps=10)
            geometry = page.locator('.connection-preview .connection-path').evaluate('''el => {
                const p=el.getPointAtLength(0), q=new DOMPoint(p.x,p.y).matrixTransform(el.getScreenCTM());
                return [q.x,q.y];
            }''')
            anchor = center(second)
            assert all(abs(a-b) < .1 for a,b in zip(geometry, anchor)), (geometry,anchor)
            checkpoint('agentic-second-output-preview-uses-correct-triangle')
            page.keyboard.press('Escape'); page.mouse.up()
            second.focus(); page.keyboard.press('Enter')
            page.locator('#ender-1 .input-triangle').focus(); page.keyboard.press('Enter')
            expect(page.locator('.connection-group')).to_have_count(4)
            page.keyboard.press('Control+z')
            expect(page.locator('.connection-group')).to_have_count(3)
            page.locator('#asker-1').click(); page.keyboard.press('Delete')
            expect(page.locator('.canvas-item')).to_have_count(3)
            page.locator('#acp-agent-search').fill('')
            checkpoint('agentic-keyboard-connect-and-undo')

            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(BASE + '/agent/prompt_flow_panel/')
            page.bring_to_front()
            require_browser_foreground(page)
            expect(page.locator('.agent-tool-item')).to_have_count(7)
            expect(page.locator('.agent-tool-item[data-type="connection"]')).to_have_count(0)
            for asset in (asset for asset in ASSETS if "/static/" in asset):
                url = '/static/' + asset.split('/static/', 1)[1]
                assert page.request.get(BASE + url).body() == (ROOT / 'Tlamatini' / asset).read_bytes()
            assert '-prompt-flow-panel-11-shared-mechanics' in page.locator('script[src*="prompt-flow-panel.js"]').get_attribute('src')

            kinds = ['prompt', 'programmed_prompt', 'decision', 'feed_embeddings',
                     'flush_embeddings', 'clean_history', 'user_commentary']
            nodes = []
            for i, kind in enumerate(kinds):
                config = {'text': 'Connection check'}
                if 'prompt' in kind:
                    config.update(multi_turn=False, acpx=False)
                if kind == 'programmed_prompt':
                    config.update(delay_seconds=0, scheduled_at='')
                if kind == 'decision':
                    config.update(comparison='user', value='', case_sensitive=False)
                nodes.append({'id': kind, 'type': kind, 'label': kind.replace('_', ' ').title(),
                              'x': 70 + (i % 3) * 390, 'y': 50 + (i // 3) * 210, 'config': config})
            fixture = {'format': 'tlamatini-prompting-flow', 'version': 1,
                       'name': 'Connector parity', 'start': 'prompt', 'max_steps': 20,
                       'nodes': nodes, 'edges': []}
            fixture_path = OUT / 'connections.fpmt'
            fixture_path.write_text(json.dumps(fixture), encoding='utf-8')

            def open_file(path):
                toggle = page.locator('.navbar-toggler')
                if toggle.is_visible() and toggle.get_attribute('aria-expanded') != 'true':
                    toggle.click()
                page.get_by_role('button', name='File', exact=True).click()
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="open"]').click()
                chooser.value.set_files(str(path))
                confirm = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
                if confirm.is_visible():
                    confirm.click()
                expect(page.locator('.pmt-node')).to_have_count(7)

            open_file(fixture_path)
            page.locator('[data-action="fit"]').click()
            page.mouse.move(30, 100)
            for port in page.locator('.pmt-port').all():
                actual = port.evaluate(style)
                reference = acp_input if 'input' in port.get_attribute('class').split() else acp_output
                assert actual == reference, {'port': port.get_attribute('class'), 'actual': actual, 'reference': reference}
            expect(page.locator('.pmt-port.input')).to_have_count(7)
            expect(page.locator('.pmt-port.output')).to_have_count(8)
            checkpoint('02-seven-operations-exact-agentic-port-styles')

            def node(kind):
                return page.locator(f'.pmt-node[data-node-id="{kind}"]')

            def port(kind, name='next'):
                return node(kind).locator(f'[data-port="{name}"]')

            def edges(count):
                expect(page.locator('.pmt-edge')).to_have_count(count)

            source, target = port('prompt'), port('programmed_prompt', 'input')
            page.mouse.move(*center(source))
            assert source.evaluate(style) == acp_hover
            page.mouse.down()
            page.mouse.move(*center(target), steps=15)
            expect(page.locator('.pmt-connection-preview')).to_have_count(1)
            expect(source).to_have_class(re.compile('connecting-source'))
            expect(target).to_have_class(re.compile('connecting-target'))
            expect(target).to_have_css('border-left-color', 'rgb(255, 204, 0)')
            assert source.evaluate(style) == acp_source_active
            assert target.evaluate(style) == acp_target_active
            edges(0)
            checkpoint('03-live-drag-preview-and-port-highlights')
            page.mouse.up()
            edges(1)
            expect(page.locator('.pmt-connection-preview, .connecting-source, .connecting-target')).to_have_count(0)
            page.mouse.move(30, 100)
            assert page.locator('.pmt-wire').evaluate(
                'el => ({stroke:getComputedStyle(el).stroke,width:getComputedStyle(el).strokeWidth})') == acp_wire
            expect(page.locator('#connections-layer marker, [marker-end]')).to_have_count(0)
            checkpoint('04-release-commits-agentic-wire')
            page.mouse.move(*wire_point(page.locator('.pmt-wire-hit').first))
            assert page.locator('.connection-group:hover .connection-path').evaluate(wire_style) == acp_wire_hover
            page.mouse.down(); page.mouse.up()
            assert page.locator('.connection-group.selected .connection-path').evaluate(wire_style) == acp_wire_selected
            checkpoint('04a-identical-hover-selection-and-glow')
            page.keyboard.press('Escape')
            node('prompt').click(button='right')
            expect(page.locator('#agent-context-menu')).to_be_visible()
            expect(page.locator('#agent-context-menu .context-menu-item')).to_have_count(4)
            page.keyboard.press('Escape')
            node('prompt').click()
            page.keyboard.press('ArrowRight')
            expect(node('prompt')).to_have_css('left', '80px')
            page.keyboard.press('Control+z')
            expect(node('prompt')).to_have_css('left', '70px')
            page.keyboard.press('Control+d')
            expect(page.locator('.pmt-node')).to_have_count(8)
            page.keyboard.press('Control+z')
            expect(page.locator('.pmt-node')).to_have_count(7)
            checkpoint('04b-matching-context-menu-keyboard-move-duplicate-and-undo')

            check_editor(page, True, checkpoint, center)

            for cancel in ('empty', 'body', 'escape', 'pointercancel', 'blur'):
                require_browser_foreground(page)
                page.mouse.move(*center(source))
                page.mouse.down()
                page.mouse.move(*center(node('programmed_prompt')), steps=8)
                if cancel == 'empty':
                    page.mouse.move(center(node('prompt'))[0], center(node('prompt'))[1] + 90)
                elif cancel == 'escape':
                    page.keyboard.press('Escape')
                elif cancel == 'pointercancel':
                    # Browser cancellation is not synthesizable via a physical mouse.
                    page.locator('#submonitor-container').dispatch_event('pointercancel')
                elif cancel == 'blur':
                    other = context.pages[0]
                    other.bring_to_front()
                    page.wait_for_timeout(300)
                    page.bring_to_front()
                page.mouse.up()
                edges(1)
                expect(page.locator('.pmt-connection-preview, .connecting-source, .connecting-target')).to_have_count(0)
            source.click()
            target.click()
            edges(1)
            checkpoint('05-cancel-invalid-drops-and-no-click-mode')

            drag(source, port('decision', 'input'))
            edges(1)
            page.keyboard.press('Control+z')
            edges(1)
            page.keyboard.press('Control+Shift+z')
            edges(1)
            drag(port('decision', 'yes'), port('feed_embeddings', 'input'))
            drag(port('decision', 'no'), port('flush_embeddings', 'input'))
            edges(3)
            # The N preview must originate at N, not the first (Y) output.
            page.mouse.move(*center(port('decision', 'no')))
            page.mouse.down()
            page.mouse.move(*center(port('clean_history', 'input')), steps=8)
            checkpoint('06-decision-two-right-outputs-and-correct-no-preview')
            page.mouse.up()
            edges(3)

            def assert_anchors():
                for wire in page.locator('.pmt-wire').all():
                    geometry = wire.evaluate('''path => {
                        const d = path.getAttribute('d').match(/-?[\\d.]+/g).map(Number);
                        const inverse = path.getScreenCTM().inverse();
                        const ports = [...document.querySelectorAll('.pmt-port')].map(el => {
                            const b=el.getBoundingClientRect();
                            const p=new DOMPoint(b.x+b.width/2,b.y+b.height/2).matrixTransform(inverse);
                            return {x:p.x,y:p.y};
                        });
                        return {d,ports};
                    }''')
                    d, anchors = geometry['d'], geometry['ports']
                    assert len(d) == 8, d
                    for x, y in ((d[0], d[1]), (d[6], d[7])):
                        assert any(abs(a['x']-x) < .1 and abs(a['y']-y) < .1 for a in anchors), geometry
                    half = abs(d[6]-d[0]) / 2
                    assert abs(d[2]-d[0]-half) < .01 and d[3] == d[1]
                    assert abs(d[4]-d[6]+half) < .01 and d[5] == d[7]

            assert_anchors()
            page.locator('[data-action="zoom-in"]').click()
            drag(port('feed_embeddings'), port('user_commentary', 'input'))
            edges(4)
            assert_anchors()
            page.mouse.move(*center(node('feed_embeddings')))
            page.mouse.down()
            p = center(node('feed_embeddings'))
            page.mouse.move(p[0] + 45, p[1] + 30, steps=8)
            page.mouse.up()
            assert_anchors()
            page.keyboard.press('Control+z')
            assert_anchors()
            checkpoint('07-zoom-drag-move-and-undo-keep-wire-anchors')

            # Keyboard connector activation is separate from pointer click-to-connect.
            port('flush_embeddings').focus()
            page.keyboard.press('Enter')
            page.locator('#drag-divider').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('.pmt-connection-preview, .connecting-source, .connecting-target')).to_have_count(0)
            port('flush_embeddings').focus()
            page.keyboard.press('Enter')
            port('user_commentary', 'input').focus()
            page.keyboard.press('Enter')
            edges(5)
            assert_anchors()
            checkpoint('08-keyboard-connection')

            page.keyboard.press('Control+s')
            page.locator('#pmt-field-filename').fill('verified-connections.fpmt')
            with page.expect_download() as download:
                page.get_by_role('button', name='Download .fpmt', exact=True).click()
            saved = OUT / 'verified-connections.fpmt'
            try:
                download.value.save_as(str(saved))
            except Exception:
                visible.photograph('download-before-error')
                print('DOWNLOAD DIAGNOSTIC:', {'page_closed': page.is_closed(), 'filename': download.value.suggested_filename}, flush=True)
                raise
            graph = json.loads(saved.read_text(encoding='utf-8'))
            assert {(e['source'], e['target'], e['branch']) for e in graph['edges']} == {
                ('prompt', 'decision', 'next'), ('decision', 'feed_embeddings', 'yes'),
                ('decision', 'clean_history', 'no'), ('feed_embeddings', 'user_commentary', 'next'),
                ('flush_embeddings', 'user_commentary', 'next')}
            open_file(saved)
            edges(5)
            assert_anchors()
            assert not page.title().startswith('•')
            checkpoint('09-save-reopen-preserves-connections-and-branches')

            # Real model-free playback verifies editing locks and status highlighting.
            page.get_by_role('button', name='File', exact=True).click()
            page.locator('[data-action="new"]').first.click()
            page.locator('.agent-tool-item[data-type="user_commentary"]').click()
            page.locator('.agent-tool-item[data-type="clean_history"]').click()
            cleaner = page.locator('.pmt-node[data-type="clean_history"]')
            x, y = center(cleaner)
            page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+350,y,steps=10); page.mouse.up()
            commentary = page.locator('.pmt-node[data-type="user_commentary"]')
            drag(commentary.locator('.output-triangle'), cleaner.locator('.input-triangle'))
            commentary.click()
            page.locator('#pmt-play').click()
            expect(page.locator('#pmt-field-reply')).to_be_visible()
            for button in page.locator('.pmt-port').all():
                expect(button).to_be_disabled()
            expect(page.locator('.pmt-node.selected .pmt-shape')).to_have_css('stroke', 'rgb(250, 204, 21)')
            page.locator('#pmt-field-reply').fill('Visible connection parity verified.')
            page.get_by_role('button', name='Continue flow', exact=True).click()
            expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
            expect(page.locator('.pmt-node.selected .pmt-shape')).to_have_css('stroke', 'rgb(74, 222, 128)')
            checkpoint('10-real-playback-edit-lock-and-selection-colors')
            expect(page.locator('.pmt-edge.traversed')).to_have_count(1)
            page.mouse.move(*wire_point(page.locator('.pmt-wire-hit')))
            assert page.locator('.pmt-wire').evaluate(wire_style) == acp_wire_hover
            page.mouse.down(); page.mouse.up()
            assert page.locator('.pmt-wire').evaluate(wire_style) == acp_wire_selected
            checkpoint('11-traversed-wire-retains-identical-hover-selection-glow')
            assert not errors, errors
            print('ALL PROMPT FLOW CONNECTION CHECKS PASSED.', flush=True)
            page.wait_for_timeout(10000)
            context.close()
        outcome = 0
    except Exception:
        print('BROWSER ERRORS:', locals().get('errors', []), flush=True)
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
            'after_ports': after, 'mocked_transports': False,
        }, indent=2), encoding='utf-8')
        print('PROMPT FLOW CONNECTION EXIT CODE:', outcome, flush=True)
    return outcome


if __name__ == '__main__':
    raise SystemExit(main())
