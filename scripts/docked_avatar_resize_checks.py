# Tlamatini Author Banner — Angela López Mendoza
"""Docked portrait regression checks, called only by the headed source harness."""
import json
import win32api
import win32con


def run_checks(page, out, capture, results):
    page.native_window.activate()
    page.native_window.verify()
    page.wait_for_function('window.TlamatiniAvatarSize && window.TlamatiniPresence')
    page.evaluate('document.fonts.ready')
    page.evaluate("document.getElementById('dictation-status').hidden = true")
    draft = 'Keep this draft while resizing the docked portrait.'
    page.locator('#chat-message-input').fill(draft)
    divider = page.locator('#vertical-drag-divider')
    side = page.locator('#drag-divider')
    handle = page.locator('#tlm-avatar-resize')

    def geometry():
        page.native_window.activate()
        page.wait_for_timeout(350)
        page.native_window.verify()
        return page.evaluate('''() => {
            const r = selector => { const b = document.querySelector(selector).getBoundingClientRect();
                return {x:b.x,y:b.y,w:b.width,h:b.height,right:b.right,bottom:b.bottom}; };
            return {avatar:r('#tlm-avatar-dock'),face:r('#tlm-face-outer'),form:r('#chat-form'),
                actions:r('.chat-composer-actions'),input:r('#chat-message-input'),
                panel:r('#tools-chat-form-container'),log:r('#chat-log'),sub:r('#subchat-container'),
                floating:document.querySelector('#tlm-avatar-dock').classList.contains('tlm-floating'),
                draft:document.querySelector('#chat-message-input').value};
        }''')

    def contained(g):
        assert not g['floating'], g
        assert g['draft'] == draft, g
        a = g['avatar']
        assert a['w'] >= 120 and abs(a['w'] - a['h']) < 1, g
        assert a['w'] <= max(120, g['form']['w'] * .25) + 1, g
        assert a['y'] >= g['form']['y'] and a['right'] <= g['form']['right'] + 1, g
        assert a['bottom'] <= g['actions']['y'] - 17, g
        assert a['x'] >= g['input']['right'], g
        assert g['actions']['bottom'] <= g['panel']['bottom'] + 1, g
        assert g['face']['w'] >= 106 and abs(g['face']['w'] - g['face']['h']) < 1, g

    def passed(name, photo=None):
        g = geometry()
        contained(g)
        results.append({'name': name, 'ok': True, 'geometry': g})
        print('DOCKED PASS:', name, json.dumps(g['avatar']), flush=True)
        (out / 'docked-checkpoints.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        if photo:
            capture(photo + '.png')
        return g

    def drag_to(y, cancel=False):
        box = divider.bounding_box()
        x = box['x'] + box['width'] * .4
        page.mouse.move(x, box['y'] + box['height'] / 2)
        page.mouse.down()
        page.mouse.move(x, y, steps=14)
        if cancel:
            page.keyboard.press('Escape')
        else:
            page.mouse.up()

    initial = passed('Initial dock keeps its natural quarter-width portrait', 'docked-01-initial')
    assert initial['avatar']['w'] > 160, initial
    divider.press('End')
    g = passed('Tall composer caps a square portrait at the original quarter-width')
    for target in [200, 160, 120]:
        box = divider.bounding_box()
        # Lower the seam by the spare vertical room above a target-size portrait.
        dy = g['form']['h'] - (target + g['actions']['h'] + 20)
        drag_to(box['y'] + max(0, dy))
        g = passed('Pointer drag shrinks docked portrait to ' + str(target) + ' px')
        assert abs(g['avatar']['w'] - target) <= 2, (target, g)
    assert g['panel']['h'] < initial['panel']['h'] - 30, g
    assert g['log']['h'] > initial['log']['h'] + 30, g
    capture('docked-02-minimum.png')

    divider.press('Home')
    minimum = passed('Home reaches the 120 px portrait floor')
    assert 120 <= minimum['avatar']['w'] <= 121, minimum
    divider.press('ArrowUp')
    one = geometry()
    divider.press('Shift+ArrowUp')
    five = passed('Arrows and Shift grow the portrait with the composer')
    assert one['avatar']['w'] > minimum['avatar']['w'] + 2, one
    assert five['avatar']['w'] > one['avatar']['w'] + 20, five
    divider.dblclick()
    assert geometry()['avatar']['w'] <= 121
    passed('Double-click returns the dock to its minimum')

    divider.press('End')
    side.press('Home')
    narrow = passed('Side divider still shrinks the dock without covering input')
    side.press('End')
    wider = passed('Side divider grows the portrait again when height is available')
    assert wider['avatar']['w'] > narrow['avatar']['w'] + 30, (narrow, wider)
    divider.press('Home')
    side.press('Home')
    side.press('End')
    assert geometry()['avatar']['w'] <= 121
    passed('Widening chat preserves the compact height instead of re-inflating the avatar')

    box = divider.bounding_box()
    drag_to(box['y'] - 65, cancel=True)
    cancelled = geometry()
    page.mouse.move(box['x'] + 150, box['y'] - 160, steps=8)
    page.mouse.up()
    assert abs(geometry()['avatar']['w'] - cancelled['avatar']['w']) < 1
    passed('Escape ends a docked resize without a stuck drag')

    handle.press('ArrowUp')
    floating = geometry()
    assert floating['floating'] and abs(floating['avatar']['w'] - 140) < 1, floating
    divider.press('Home')
    divider.press('End')
    assert abs(geometry()['avatar']['w'] - 140) < 1
    handle.press('Home')
    passed('Floating size stays independent; docking restores the fitted square')
    divider.press('Home')
    assert geometry()['avatar']['w'] <= 121
    passed('Redocked portrait can immediately shrink to 120 px again')

    page.native_window.resize(1100, 620)
    side.press('End')
    divider.press('Home')
    passed('Narrow window retains the portrait floor and accessible controls', 'docked-03-narrow')
    before = geometry()['panel']['h']
    page.evaluate('''() => {
        const chips = document.querySelector('#chat-image-chips');
        chips.classList.add('has-content');
        const item = document.createElement('div'); item.className = 'chat-img-chip';
        item.textContent = 'Attachment layout fixture'; item.style.height = '68px'; chips.appendChild(item);
        document.querySelector('#dictation-status').hidden = false;
        document.querySelector('#dictation-label').textContent = 'Voice layout fixture';
        document.querySelector('#dictation-detail').textContent = 'No recording takes place.';
    }''')
    rows = passed('Attachment and dictation rows leave the 120 px portrait and buttons intact')
    assert rows['panel']['h'] > before + 80, rows
    page.evaluate('''() => {
        const chips = document.querySelector('#chat-image-chips'); chips.replaceChildren();
        chips.classList.remove('has-content'); document.querySelector('#dictation-status').hidden = true;
    }''')
    assert abs(geometry()['panel']['h'] - before) < 1
    passed('Removing transient rows releases their space without changing the portrait')

    # Native Chrome zoom; never substitute viewport emulation or CSS zoom.
    def native_zoom_key(vk):
        page.native_window.activate()
        page.native_window.verify()
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        page.wait_for_timeout(350)

    native_zoom_key(0x30)
    baseline_dpr = page.evaluate('devicePixelRatio')
    try:
        native_zoom_key(0x6B)
        native_zoom_key(0x6B)
        zoom = page.evaluate('devicePixelRatio') / baseline_dpr
        assert abs(zoom - 1.25) < .01, zoom
        divider.press('Home')
        passed('Native 125 percent browser zoom keeps the fitted dock usable', 'docked-04-zoom')
    finally:
        native_zoom_key(0x30)
    page.native_window.resize(1440, 900)
    divider.press('Home')
    first = geometry()
    page.wait_for_timeout(1200)
    stable = geometry()
    assert abs(stable['avatar']['w'] - first['avatar']['w']) < .1
    assert abs(stable['panel']['h'] - first['panel']['h']) < .1
    passed('ResizeObserver settles without geometry oscillation')
