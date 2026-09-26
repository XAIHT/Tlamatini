# Tlamatini Author Banner — Angela López Mendoza
"""Shared editor checks, invoked only by the verified visible Chrome harness.

No browser is launched here. The caller must use headless=False, verify the
foreground desktop window, and capture every checkpoint with Shoter.
"""
from playwright.sync_api import expect


def check_editor(page, prompt, checkpoint, center):
    prefix = 'prompt' if prompt else 'agentic'
    nodes = page.locator('.pmt-node' if prompt else '.canvas-item')
    wires = page.locator('.pmt-edge' if prompt else '.connection-group:not(.connection-preview)')
    first = nodes.first
    count, links = nodes.count(), wires.count()
    position = 'el => [parseFloat(el.style.left), parseFloat(el.style.top)]'
    initial = first.evaluate(position)
    first.click()
    x, y = center(first)
    page.keyboard.down('Control')
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 83, y + 47, steps=10)
    # Releasing before configuration I/O finishes must still produce one undo.
    page.mouse.up()
    page.keyboard.up('Control')
    expect(nodes).to_have_count(count + 1)
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    assert first.evaluate(position) == initial
    copies = nodes.all()[-1].evaluate(position)
    page.keyboard.press('Control+z')
    expect(nodes).to_have_count(count)
    page.keyboard.press('Control+Shift+z')
    expect(nodes).to_have_count(count + 1)
    assert nodes.all()[-1].evaluate(position) == copies
    page.keyboard.press('Control+z')
    expect(nodes).to_have_count(count)
    checkpoint(prefix + '-copy-drag-one-step-undo-redo')

    first.click()
    x, y = center(first)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 13, y + 17, steps=6)
    page.mouse.up()
    after = first.evaluate(position)
    assert abs(after[0] - initial[0] - 13) < .1, (initial, after)
    assert abs(after[1] - initial[1] - 17) < .1, (initial, after)
    page.keyboard.press('Control+z')
    assert first.evaluate(position) == initial
    checkpoint(prefix + '-free-drag-without-grid-jumps')

    page.mouse.move(*center(page.locator('#submonitor-container')))
    label = page.locator('#pmt-zoom' if prompt else '#acp-zoom-label')
    page.keyboard.down('Control')
    page.mouse.wheel(0, -120)
    page.keyboard.up('Control')
    expect(label).to_have_text('110%')
    page.locator('[data-action="fit"]' if prompt else '#acp-fit').click()
    expect(label).to_have_text('100%')
    checkpoint(prefix + '-wheel-zoom-and-identical-fit')

    page.keyboard.press('Escape')
    boxes = [node.bounding_box() for node in nodes.all()]
    left = min(box['x'] for box in boxes) - 20
    top = min(box['y'] for box in boxes) - 20
    right = max(box['x'] + box['width'] for box in boxes) + 20
    bottom = max(box['y'] + box['height'] for box in boxes) + 20
    page.mouse.move(left, top)
    page.mouse.down()
    page.mouse.move(right, bottom, steps=14)
    marquee = page.locator('#pmt-marquee' if prompt else '#selection-box')
    expect(marquee).to_be_visible()
    expect(marquee).to_have_css('border-top-color', 'rgba(0, 120, 215, 0.7)')
    expect(marquee).to_have_css('background-color', 'rgba(0, 120, 215, 0.2)')
    expect(page.locator('.pmt-node.selected' if prompt else '.canvas-item.selected')).to_have_count(count)
    expect(page.locator('.connection-group.selected')).to_have_count(links)
    checkpoint(prefix + '-live-marquee-selects-blocks-and-wires')
    page.mouse.up()
    page.keyboard.press('Escape')
    expect(page.locator('.connection-group.selected')).to_have_count(0)

    first.click(button='right')
    menu = page.locator('#agent-context-menu')
    expect(menu).to_be_visible()
    menu.locator('.context-menu-item').filter(has_text='Duplicate').click()
    expect(nodes).to_have_count(count + 1)
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    page.keyboard.press('Control+z')
    expect(nodes).to_have_count(count)
    first.click()
    page.keyboard.press('Enter')
    expect(page.get_by_role('dialog').last).to_be_visible()
    page.keyboard.press('Escape')
    checkpoint(prefix + '-context-duplicate-and-enter-configure')

    divider = page.locator('#drag-divider')
    before = page.locator('#main-agents-container').bounding_box()['width']
    divider.focus()
    page.keyboard.press('ArrowRight')
    after = page.locator('#main-agents-container').bounding_box()['width']
    expected = page.locator('#agents-container').bounding_box()['width'] / 100
    assert abs(after - before - expected) < 1, (before, after, expected)
    page.keyboard.press('ArrowLeft')
    page.locator('#submonitor-container').focus()
    checkpoint(prefix + '-matching-divider-keyboard-step')
