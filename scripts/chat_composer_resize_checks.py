# Tlamatini Author Banner — Angela López Mendoza
"""Headed real-page layout checks. Status/attachment rows are explicit fixtures."""
import json
from pathlib import Path


def run_checks(page, context, user_id, out, capture, results):
    from playwright.sync_api import expect
    import win32gui

    page.native_window.activate()
    page.native_window.verify()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.evaluate("""() => {
        window.composerLayoutErrors = [];
        window.addEventListener('error', e => composerLayoutErrors.push(e.message));
    }""")
    page.wait_for_function('window.TlamatiniAvatarSize && window.TlamatiniPresence')
    page.evaluate('document.fonts.ready')
    # The source template and all production styles/scripts stay real. No audio
    # or inference is requested; status rows below are labelled layout fixtures.
    page.evaluate("document.getElementById('dictation-status').hidden = true")
    page.locator('#chat-message-input').fill('Resize this composer while keeping this draft intact.')
    divider = page.locator('#vertical-drag-divider')
    handle = page.locator('#tlm-avatar-resize')

    def settle():
        page.native_window.activate()
        page.wait_for_timeout(500)
        page.native_window.verify()

    def geometry():
        settle()
        return page.evaluate("""() => {
            const rect = s => { const r = document.querySelector(s).getBoundingClientRect();
                return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}; };
            return {panel:rect('#tools-chat-form-container'),form:rect('#chat-form'),
                actions:rect('.chat-composer-actions'),input:rect('#chat-message-input'),
                avatar:rect('#tlm-avatar-dock'),log:rect('#chat-log'),tools:rect('#tools-div'),
                gauge:rect('#context-gauge-row'),
                divider:rect('#vertical-drag-divider'),sub:rect('#subchat-container'),
                floating:document.querySelector('#tlm-avatar-dock').classList.contains('tlm-floating'),
                viewport:{w:innerWidth,h:innerHeight},
                value:document.querySelector('#chat-message-input').value};
        }""")

    def contained(g, docked=False):
        for name in ['actions', 'input']:
            item = g[name]
            assert item['bottom'] <= g['panel']['bottom'] + 1, (name, g)
            assert item['y'] >= g['form']['y'] - 1, (name, g)
            assert item['right'] <= g['panel']['right'] + 1, (name, g)
        assert g['panel']['bottom'] <= g['viewport']['h'] + 1, g
        assert g['input']['h'] >= g['actions']['h'], g
        if page.locator('#context-gauge-row .ctxg-ring').count() and page.locator('#context-gauge-row').is_visible():
            ring = page.locator('#context-gauge-row .ctxg-ring').bounding_box()
            assert ring['y'] >= g['gauge']['y'] - 1, g
            assert ring['y'] + ring['height'] <= g['gauge']['bottom'] + 1, g
        assert g['value'] == 'Resize this composer while keeping this draft intact.', g
        if docked:
            assert not g['floating'], g
            assert g['avatar']['h'] >= max(120, g['avatar']['w']) - 1, g
            assert g['avatar']['bottom'] < g['actions']['y'], g
            assert g['avatar']['y'] >= g['form']['y'], g

    def compact(g):
        contained(g)
        assert g['floating'], g
        assert 5 <= g['form']['h'] - g['actions']['h'] <= 8, g

    def passed(name, photo=None):
        page.native_window.activate()
        page.native_window.verify()
        foreground = win32gui.GetForegroundWindow()
        visible = win32gui.IsWindowVisible(foreground) and not win32gui.IsIconic(foreground)
        assert visible and win32gui.GetClassName(foreground).startswith('Chrome_WidgetWin'), 'Chrome must be visible and foreground'
        record = {'name': name, 'ok': True, 'geometry': geometry(),
                  'foreground_title': win32gui.GetWindowText(foreground)}
        results.append(record)
        print('PASS:', name, flush=True)
        (out / 'checkpoints.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        if photo:
            capture(photo + '.png')

    docked_initial = geometry()
    contained(docked_initial, docked=True)
    passed('Docked portrait fits above the controls', '01-docked')

    handle.press('ArrowUp')
    expect(handle).to_be_focused()
    divider.press('Home')
    initial = geometry()
    compact(initial)
    assert abs(initial['panel']['w'] - docked_initial['panel']['w']) < 1, initial
    passed('Undock with avatar handle; Home fits to actions plus 6px guard', '02-undocked-compact')

    # Real pointer drag to enlarge, then shrink right to the lower edge.
    def drag_to(y):
        box = divider.bounding_box()
        x = box['x'] + box['width'] * .4
        page.mouse.move(x, box['y'] + box['height'] / 2)
        page.mouse.down()
        page.mouse.move(x, y, steps=16)
        page.mouse.up()
        settle()

    sub = geometry()['sub']
    drag_to(sub['y'] + sub['h'] * .55)
    expanded = geometry()
    assert expanded['form']['h'] > initial['form']['h'] + 80, expanded
    contained(expanded)
    passed('Pointer drag freely enlarges the undocked composer')
    drag_to(sub['bottom'] - 2)
    compact(geometry())
    passed('Pointer drag reaches the content minimum; no 30% floor', '03-drag-minimum')

    before = geometry()['form']['h']
    divider.press('ArrowUp')
    assert geometry()['form']['h'] > before + 2
    divider.press('Shift+ArrowUp')
    assert geometry()['form']['h'] > before + 25
    divider.dblclick()
    compact(geometry())
    expect(divider).to_have_attribute('role', 'separator')
    assert divider.get_attribute('aria-valuetext').startswith('Message composer ')
    passed('Arrow/Shift controls move immediately; double-click fits; accessible values update')

    # The public keyboard control docks when reduced below the 120px floor.
    handle.press('ArrowDown')  # 140 -> 120
    handle.press('ArrowDown')  # 120 -> docked
    expect(handle).to_be_focused()
    contained(geometry(), docked=True)
    assert geometry()['panel']['h'] > initial['panel']['h'] + 100
    passed('Docking automatically restores room for the portrait', '04-redocked')
    handle.press('ArrowUp')
    compact(geometry())
    passed('Undocking restores the compact preference without another drag')

    # Increase the avatar through her ordinary presets; her floating size must
    # not become a minimum for the chat composer.
    handle.dblclick()
    handle.dblclick()
    assert geometry()['avatar']['w'] >= 240
    compact(geometry())
    passed('A larger floating avatar does not enlarge the composer')

    divider.press('End')
    g = geometry()
    assert 79 <= g['log']['h'] <= 81, g
    contained(g)
    divider.press('Home')
    compact(geometry())
    passed('End expands while preserving chat history; Home returns to minimum')

    box = divider.bounding_box()
    page.mouse.move(box['x'] + 120, box['y'] + 4)
    page.mouse.down()
    page.mouse.move(box['x'] + 120, box['y'] - 100, steps=8)
    page.keyboard.press('Escape')
    height = geometry()['panel']['h']
    page.mouse.move(box['x'] + 120, box['y'] - 220, steps=8)
    page.mouse.up()
    assert abs(geometry()['panel']['h'] - height) < 1
    assert not page.locator('body').evaluate("e=>e.classList.contains('resizing-vertical')")
    divider.press('Home')
    passed('Escape releases pointer capture and stops the resize')

    # Viewport and panel width changes use the real responsive toolbar.
    page.native_window.resize(1100, 740)
    settle()
    horizontal = page.locator('#drag-divider').bounding_box()
    page.mouse.move(horizontal['x'] + 4, horizontal['y'] + 100)
    page.mouse.down()
    page.mouse.move(550, horizontal['y'] + 100, steps=14)
    page.mouse.up()
    divider.press('Home')
    g = geometry()
    compact(g)
    assert g['tools']['h'] > initial['tools']['h'], g
    passed('Narrow chat wraps tools and still fits input/actions', '05-wrapped-toolbar')

    page.evaluate("""() => {
        const gauge = document.getElementById('context-gauge-row');
        gauge.style.cssText = 'display:flex;flex:none;height:44px;align-items:center';
        gauge.textContent = 'CONTEXT-WINDOW — layout fixture, no model request';
        const chips = document.getElementById('chat-image-chips');
        chips.classList.add('has-content');
        const chip = document.createElement('div'); chip.className = 'chat-img-chip';
        chip.textContent = 'Attachment layout fixture'; chip.style.height = '68px';
        chips.appendChild(chip);
        const status = document.getElementById('dictation-status'); status.hidden = false;
        document.getElementById('dictation-label').textContent = 'Voice status layout fixture';
        document.getElementById('dictation-detail').textContent = 'No recording is taking place.';
    }""")
    g = geometry()
    compact(g)
    assert g['panel']['h'] > initial['panel']['h'] + 120, g
    passed('Gauge, attachment and voice fixtures expand the minimum without clipping', '06-status-fixtures')
    page.evaluate("""() => {
        document.getElementById('context-gauge-row').style.display = 'none';
        const chips = document.getElementById('chat-image-chips');
        chips.replaceChildren(); chips.classList.remove('has-content');
        document.getElementById('dictation-status').hidden = true;
    }""")
    compact(geometry())
    passed('Removing transient rows automatically gives room back to the chat')

    page.native_window.resize(1440, 900)
    settle()
    # Text scaling is tested separately from the native browser zoom campaign.
    page.evaluate("document.documentElement.style.fontSize = '20px'")
    divider.press('Home')
    compact(geometry())
    passed('Larger text still fits the controls and all toolbar rows')
    page.evaluate("document.documentElement.style.fontSize = ''")
    page.evaluate('TlamatiniAvatarSize.set(0)')
    contained(geometry(), docked=True)
    page.native_window.resize(1100, 620)
    contained(geometry(), docked=True)
    passed('Docked avatar adapts to window changes without covering Send', '07-docked-smaller-window')

    page.native_window.resize(1100, 330)
    settle()
    panel = page.locator('#tools-chat-form-container')
    assert panel.evaluate('e=>e.scrollHeight > e.clientHeight && getComputedStyle(e).overflowY === "auto"')
    page.locator('#chat-message-submit').scroll_into_view_if_needed()
    g = geometry()
    assert g['panel']['bottom'] <= g['viewport']['h'] + 1, g
    assert g['actions']['bottom'] <= g['viewport']['h'] + 1, g
    assert 79 <= g['log']['h'] <= 81, g
    passed('Very short window keeps history and scrolls the composer to reachable controls', '07b-short-window')
    page.native_window.resize(1100, 620)
    panel.evaluate('e=>e.scrollTop=0')

    page.evaluate('TlamatiniAvatarSize.set(160)')
    divider.press('Home')
    compact(geometry())
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('window.TlamatiniAvatarSize && TlamatiniAvatarSize.get() === 160')
    page.evaluate("document.getElementById('dictation-status').hidden = true")
    page.locator('#chat-message-input').fill('Resize this composer while keeping this draft intact.')
    divider.press('Home')
    compact(geometry())
    passed('Reload restores the saved floating avatar and compact resizing')

    # Asset parity proves the visible browser exercised these source edits.
    root = Path(__file__).resolve().parents[1]
    for asset in ['js/agent_page_layout.js', 'css/agent_page.css', 'css/avatar.css', 'css/context_gauge.css', 'js/avatar_size.js', 'js/dialog_policy.js', 'css/dialog_theme.css', 'css/usage_dashboard.css']:
        response = context.request.get(page.url.split('/agent/')[0] + '/static/agent/' + asset)
        assert response.ok
        assert response.body() == (root / 'Tlamatini/agent/static/agent' / asset).read_bytes(), asset
    assert page.locator('script[src*="agent_page_layout.js"]').get_attribute('src').endswith('-ui-sweep-1')
    assert not errors, errors
    assert not page.evaluate('window.composerLayoutErrors || []')
    passed('Source asset parity, new cache suffix, and no browser JavaScript errors')

    page.native_window.resize(1440, 900)
    divider.press('Home')
    page.locator('#chat-message-input').fill('')
    settle()
    capture('08-final-compact.png')
    print('Composer visible campaign complete; source browser stays open for review.', flush=True)
