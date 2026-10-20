# Tlamatini Author Banner — Angela López Mendoza
"""VISIBLE suite: the Terminals area on the chat page (agent_page.html).

Two variants, one run:
  * ``chat/canvas``     -- the canvas is shown: the dock sits in the LOWER part of the canvas
                           column, initially as tall as the message box;
  * ``chat/no-canvas``  -- Views > Canvas is OFF: the dock must cover the WHOLE canvas area.

Run from a foreground PowerShell -NoExit console:  python scripts/terminater_visible_chat.py
Every check takes a full-desktop Shoter photograph; the console gate and the browser gate wait
for the operator to look at the photograph and create ``Temp/terminater-visible/<gate>.confirmed``.
"""
from __future__ import annotations

import sys

from terminater_visible_battery import Battery, near
from terminater_visible_common import Harness


def views_menu(H):
    H.page.locator('#views-menu-button').click()
    H.page.wait_for_timeout(300)


def menu_item(H, selector):
    views_menu(H)
    H.page.locator(selector).click()
    H.page.wait_for_timeout(700)
    H.page.keyboard.press('Escape')


def set_canvas(H, visible):
    now = H.page.evaluate("() => !document.querySelector('.chat-page').classList.contains('tlm-canvas-hidden')")
    if now != visible:
        menu_item(H, '#views-canvas-toggle')
    return H.wait_for(lambda: H.page.evaluate("() => !document.querySelector('.chat-page').classList.contains('tlm-canvas-hidden')") == visible, timeout=10)


class ChatBattery(Battery):
    """The generic battery with the geometry rules of a hidden canvas."""

    def __init__(self, H, prefix, canvas_hidden=False):
        super().__init__(H, prefix, 'chat')
        self.canvas_hidden = canvas_hidden

    def show_checks(self):
        if not self.canvas_hidden:
            return super().show_checks()
        self.set_visible(True)
        st = self.st()
        self.chk('Views > Terminals shows the dock while the canvas is hidden', st.get('visible') is True)
        self.H.wait_for(lambda: len(self.terminals()) >= 1, timeout=40)
        self.H.wait_for(lambda: 'PS ' in self.H.term_text() or '>' in self.H.term_text(), timeout=40)
        dock, area = self.box('#tlm-terminals'), self.box('#canvas-container')
        self.chk('the canvas column is visible (it hosts the dock)', bool(area) and area['w'] > 100 and area['display'] != 'none', str(area))
        self.chk('the dock is as wide as the canvas area', bool(dock and area) and near(dock['w'], area['w'], 6), 'dock=%s area=%s' % (dock and dock['w'], area and area['w']))
        self.chk('the dock covers the whole height of the canvas area', bool(dock and area) and dock['h'] >= area['h'] - 12, 'dock=%s area=%s' % (dock and dock['h'], area and area['h']))
        self.chk('the dock starts at the top of the canvas area', bool(dock and area) and near(dock['y'], area['y'], 10), 'dock.y=%s area.y=%s' % (dock and dock['y'], area and area['y']))
        self.chk('the dock reaches the bottom of the canvas area', bool(dock and area) and near(dock['b'], area['b'], 10))
        hidden = self.page.evaluate("""() => [...document.querySelectorAll('#canvas-container > *')]
            .filter(c => !c.matches('[data-tlm-terminals-host]')).map(c => getComputedStyle(c).display).filter(d => d !== 'none').length""")
        self.chk('the rest of the (hidden) canvas stays out of the way', hidden == 0, 'visible children=%s' % hidden)
        self.chk('the page carries both the hidden-canvas and the terminals classes',
                 self.page.evaluate("() => { const c = document.querySelector('.chat-page').classList; return c.contains('tlm-canvas-hidden') && c.contains('tlm-terminals-on'); }"))
        self.chk('the type bar is visible', self.page.locator('#tlm-terminals .tlm-term-bar').first.is_visible())
        self.chk('the tabs are visible', self.page.locator('#tlm-terminals .tlm-term-tabs').first.is_visible())

    def area_checks(self):
        if not self.canvas_hidden:
            return super().area_checks()
        self.page.locator('#tlm-terminals [data-area="full"]').first.click()
        self.page.wait_for_timeout(700)
        dock, area = self.box('#tlm-terminals'), self.box('#canvas-container')
        self.chk('Full while the canvas is hidden still covers the area', bool(dock and area) and near(dock['w'], area['w'], 6) and dock['h'] >= area['h'] - 12)
        self.page.locator('#tlm-terminals [data-area="dock"]').first.click()
        self.page.wait_for_timeout(700)
        dock, area = self.box('#tlm-terminals'), self.box('#canvas-container')
        self.chk('Dock while the canvas is hidden still covers the area (nothing else to show)', bool(dock and area) and dock['h'] >= area['h'] - 12)
        self.H.type_as_user('echo typed-while-canvas-hidden')
        self.chk('typing works in the hidden-canvas dock', bool(self.wait_text('typed-while-canvas-hidden', ignore_echo='echo typed-while')))

    def splitter_checks(self):
        if not self.canvas_hidden:
            return super().splitter_checks()
        visible = self.page.locator('#tlm-terminals .tlm-term-splitter').first.is_visible()
        box = self.page.locator('#tlm-terminals .tlm-term-splitter').first.bounding_box() if visible else None
        self.chk('the splitter has nothing to separate, so it is hidden', not visible or not box or box['height'] < 2, str(box))


def chat_specific_with_canvas(H, B):
    page = H.page
    B.set_visible(True)
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    B.api('open', kind='powershell', title='Chat one', load_profile=False)
    B.wait_tabs(1)
    # the Views menu itself
    views_menu(H)
    items = page.evaluate("() => [...document.querySelectorAll('#views-menu-button + ul .menu-entry')].map(e => e.textContent.replace(/[\\u2713\\s]+/g,' ').trim())")
    B.chk('the Views menu lists Canvas, Terminals and Reset layout', any('Canvas' in i for i in items) and any('Terminals' in i for i in items) and any('Reset' in i for i in items), str(items))
    order = [i for i in items if i]
    B.chk('Terminals sits between Canvas and Reset layout', order.index(next(i for i in order if 'Terminals' in i)) == order.index(next(i for i in order if 'Canvas' in i)) + 1, str(order))
    B.chk('the Terminals entry shows a check mark while the dock is open', page.locator('#views-terminals-toggle').get_attribute('aria-checked') == 'true')
    B.chk('the Canvas entry is checked while the canvas is shown', page.locator('#views-canvas-toggle').get_attribute('aria-checked') == 'true')
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    # chat column is untouched by the dock
    chat = B.box('#main-chat-container')
    composer = B.box('#tools-chat-form-container')
    B.chk('the chat column stays visible next to the dock', bool(chat) and chat['w'] > 200, str(chat))
    B.chk('the message box stays visible', bool(composer) and composer['h'] > 40, str(composer))
    dock = B.box('#tlm-terminals')
    B.chk('the dock lies to the right of the chat column', bool(chat and dock) and dock['x'] >= chat['r'] - 8, 'chat.r=%s dock.x=%s' % (chat and chat['r'], dock and dock['x']))
    B.chk('the dock bottom is level with the message box bottom', bool(composer and dock) and near(dock['b'], composer['b'], 14), 'composer.b=%s dock.b=%s' % (composer and composer['b'], dock and dock['b']))
    # follow the composer divider (automatic height)
    st = B.st()
    divider = page.locator('#vertical-drag-divider')
    if divider.count() and st.get('userResized') is False:
        before = B.st().get('dockHeight')
        box = divider.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] - 90, steps=10)
            page.mouse.up()
            page.wait_for_timeout(900)
        after = B.st().get('dockHeight')
        B.chk('while the dock is on automatic height it follows the message box divider', after is not None and before is not None and after > before + 30, '%s -> %s' % (before, after))
        B.chk('the dock still matches the message box height afterwards', near(B.st().get('dockHeight'), B.st().get('composerHeight'), 14), '%s vs %s' % (B.st().get('dockHeight'), B.st().get('composerHeight')))
        page.evaluate("() => window.dispatchEvent(new Event('tlm:reset-chat-layout'))")
        page.wait_for_timeout(500)
    # narrowing the canvas column makes the bar icon-only (container query)
    side = page.locator('#drag-divider')
    if side.count():
        box = side.bounding_box()
        if box:
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 200)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] / 2 + 520, box['y'] + 200, steps=14)
            page.mouse.up()
            page.wait_for_timeout(900)
        narrow = B.box('#tlm-terminals')
        labels = page.evaluate("() => [...document.querySelectorAll('#tlm-terminals .tlm-term-bar .tlm-term-btn:not(.tlm-term-new) .lb')].filter(e => getComputedStyle(e).display !== 'none').length")
        B.chk('a narrow canvas column turns the bar icon-only', (narrow and narrow['w'] < 900) and labels == 0, 'width=%s visible labels=%s' % (narrow and narrow['w'], labels))
        bar = B.box('#tlm-terminals .tlm-term-bar')
        B.chk('the bar wraps onto at most two rows when narrow', bool(bar) and bar['h'] < 90, str(bar))
        clipped = page.evaluate("""() => { const bar = document.querySelector('#tlm-terminals .tlm-term-bar'); const r = bar.getBoundingClientRect();
            return [...bar.querySelectorAll('button, select, label')].filter(e => e.offsetParent !== null).filter(e => { const b = e.getBoundingClientRect(); return b.right > r.right + 1 || b.left < r.left - 1; }).length; }""")
        B.chk('no control of the bar is cut off when narrow', clipped == 0, 'clipped=%s' % clipped)
        B.chk('the New button keeps its label when narrow', page.locator('#tlm-terminals .tlm-term-new .lb').first.is_visible())
        box = side.bounding_box() or box
        page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 200)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width'] / 2 - 760, box['y'] + 200, steps=14)
        page.mouse.up()
        page.wait_for_timeout(900)
        wide = B.box('#tlm-terminals')
        labels = page.evaluate("() => [...document.querySelectorAll('#tlm-terminals .tlm-term-bar .tlm-term-btn:not(.tlm-term-new) .lb')].filter(e => getComputedStyle(e).display !== 'none').length")
        B.chk('a wide canvas column shows the labels again', bool(wide) and wide['w'] > 700 and labels >= 5, 'width=%s labels=%s' % (wide and wide['w'], labels))
    B.chk('the Terminals dock keeps working next to the chat', B.st().get('visible') is True)


def chat_specific_without_canvas(H, B):
    page = H.page
    B.set_visible(True)
    chat = B.box('#main-chat-container')
    B.chk('with the canvas hidden the chat column is wide', bool(chat) and chat['w'] > 300, str(chat))
    B.chk('the Canvas entry is unchecked', page.locator('#views-canvas-toggle').get_attribute('aria-checked') == 'false')
    B.chk('the Terminals entry is still checked', page.locator('#views-terminals-toggle').get_attribute('aria-checked') == 'true')
    B.chk('Reset layout is available', page.locator('#views-reset-layout').count() == 1)
    B.set_visible(False)
    area = B.box('#canvas-container')
    B.chk('hiding the dock with the canvas hidden leaves no canvas column', not area or area['display'] == 'none' or area['w'] < 5, str(area))
    chat = B.box('#main-chat-container')
    B.chk('the chat column takes the whole width again', bool(chat) and chat['w'] > 600, str(chat))
    B.set_visible(True)
    dock, area = B.box('#tlm-terminals'), B.box('#canvas-container')
    B.chk('showing the dock brings the canvas column back for the terminals', bool(dock and area) and area['w'] > 100 and near(dock['w'], area['w'], 8))
    B.chk('the dock covers the whole canvas column', bool(dock and area) and dock['h'] >= area['h'] - 12)
    # back to the normal layout
    set_canvas(H, True)
    page.wait_for_timeout(700)
    dock, area = B.box('#tlm-terminals'), B.box('#canvas-container')
    B.chk('showing the canvas again puts the dock back in the LOWER part', bool(dock and area) and dock['h'] < area['h'] - 60, 'dock.h=%s area.h=%s' % (dock and dock['h'], area and area['h']))
    B.chk('the dock is bottom-aligned again', bool(dock and area) and near(dock['b'], area['b'], 8))
    B.chk('the canvas is visible above the dock', (B.box('#canvas-container') or {'h': 0})['h'] > 150)
    set_canvas(H, False)
    page.wait_for_timeout(700)
    dock, area = B.box('#tlm-terminals'), B.box('#canvas-container')
    B.chk('hiding the canvas again makes the dock cover the area again', bool(dock and area) and dock['h'] >= area['h'] - 12)
    menu_item(H, '#views-reset-layout')
    page.wait_for_timeout(900)
    B.chk('Reset layout shows the canvas again', H.page.evaluate("() => !document.querySelector('.chat-page').classList.contains('tlm-canvas-hidden')"))
    dock, area = B.box('#tlm-terminals'), B.box('#canvas-container')
    B.chk('after Reset layout the dock is back in the lower part', bool(dock and area) and dock['h'] < area['h'] - 60)
    B.chk('Reset layout never kills a terminal', len(B.terminals()) >= 1)


def run(H: Harness):
    # ---------------- variant 1: the canvas is shown ----------------
    with_canvas = ChatBattery(H, 'chat/canvas', canvas_hidden=False)
    with_canvas.run_all()
    with_canvas.group('chat page specifics', chat_specific_with_canvas, H, with_canvas)
    with_canvas.reset_dock()   # the second variant starts from the same clean point as the first
    # ---------------- variant 2: the canvas is hidden ----------------
    H.page.reload()
    H.page.wait_for_timeout(2500)
    H.page.keyboard.press('Escape')
    H.wait_dock_ready()
    set_canvas(H, False)
    without = ChatBattery(H, 'chat/no-canvas', canvas_hidden=True)
    # the terminals are already visible from the first variant (state is remembered)
    without.run_all()
    without.group('hidden-canvas specifics', chat_specific_without_canvas, H, without)
    total = len(H.results)
    failed = len([r for r in H.results if not r['ok']])
    print('chat suite: %d checks recorded, %d failed' % (total, failed), flush=True)


def main():
    with Harness('chat', '/agent/agent/') as H:
        run(H)
    sys.exit(getattr(H, 'exit_code', 1))


if __name__ == '__main__':
    main()
