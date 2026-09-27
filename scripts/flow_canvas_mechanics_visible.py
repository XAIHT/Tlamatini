# Tlamatini Author Banner — Angela López Mendoza
"""Shared editor checks, invoked only by the verified visible Chrome harness.

No browser is launched here. The caller must use headless=False, verify the
foreground desktop window, and capture every checkpoint with Shoter.
"""
import re

from playwright.sync_api import expect


def check_node_activation(page, prompt, checkpoint):
    nodes = page.locator('.pmt-node' if prompt else '.canvas-item')
    for node in nodes.all():
        identity = node.get_attribute('data-node-id' if prompt else 'id')
        # Real click events, including child labels/shapes; never dispatch dblclick.
        node.dblclick(delay=90)
        dialog = page.locator('.ui-dialog:visible')
        expect(dialog).to_have_count(1)
        if prompt:
            assert 'Configure' in dialog.inner_text()
        else:
            expect(dialog.locator('.ui-dialog-title')).to_have_text('Properties: ' + identity)
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
    # Pins keep their connection gesture and must not open a node form.
    for selector in ('.input-triangle', '.output-triangle'):
        port = nodes.first.locator(selector).first
        if port.count():
            port.dblclick(delay=90)
            expect(page.locator('.ui-dialog:visible')).to_have_count(0)
            page.keyboard.press('Escape')
    if prompt and page.locator('.pmt-wire-hit').count():
        point = page.locator('.pmt-wire-hit').first.evaluate('''path => {
            const p=path.getPointAtLength(path.getTotalLength()/2);
            const q=new DOMPoint(p.x,p.y).matrixTransform(path.getScreenCTM());
            return [q.x,q.y];
        }''')
        page.mouse.dblclick(*point,delay=90)
        expect(page.get_by_role('dialog',name='Configure connection',exact=True)).to_be_visible()
        page.keyboard.press('Escape')
    checkpoint(('prompt' if prompt else 'agentic') + '-native-double-click-every-loaded-node-and-port')


def check_precise_copy(page, prompt, checkpoint, center):
    prefix = 'prompt' if prompt else 'agentic'
    nodes = page.locator('.pmt-node' if prompt else '.canvas-item')
    source = nodes.first if prompt else page.locator('#sleeper-1')
    count = nodes.count()
    source.dblclick(delay=90)
    field = page.locator('#pmt-field-text' if prompt else '#canvas-item-list [data-key="duration_ms"]')
    original_value = 'Distinct settings — líneas\\n{{last_output}}' if prompt else '2345'
    field.fill(original_value)
    page.locator('.ui-dialog:visible').get_by_role('button', name='Save', exact=True).click()
    if not prompt:
        expect(page.locator('#deployment-result-dialog')).to_be_visible()
        page.keyboard.press('Escape')
    expect(page.locator('.ui-dialog:visible')).to_have_count(0)
    position = 'el => [parseFloat(el.style.left),parseFloat(el.style.top)]'
    initial = source.evaluate(position)
    identity = source.get_attribute('data-node-id' if prompt else 'id')
    label = source.inner_text()
    x,y = center(source)
    page.keyboard.down('Control')
    page.mouse.move(x,y)
    page.mouse.down()
    page.mouse.move(x+1,y+1)
    page.mouse.move(x+2,y+2)
    assert source.evaluate(position) == initial, 'Original moved before drag threshold'
    page.mouse.move(x+240,y+72,steps=12)
    page.keyboard.up('Control')  # intent must survive modifier release before mouse-up
    page.mouse.up()
    expect(nodes).to_have_count(count+1)
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    copy = page.locator('.pmt-node.selected' if prompt else '.canvas-item.selected')
    expect(copy).to_have_count(1)
    copied_id = copy.get_attribute('data-node-id' if prompt else 'id')
    assert copied_id != identity and copy.inner_text() != label
    assert source.evaluate(position) == initial
    actual = copy.evaluate(position)
    assert abs(actual[0]-initial[0]-240)<.1 and abs(actual[1]-initial[1]-72)<.1, (initial,actual)
    copy.dblclick(delay=90)
    expect(field).to_have_value(original_value)
    field.fill('Independent copy' if prompt else '6789')
    page.locator('.ui-dialog:visible').get_by_role('button', name='Save', exact=True).click()
    if not prompt:
        expect(page.locator('#deployment-result-dialog')).to_be_visible()
        page.keyboard.press('Escape')
    source.dblclick(delay=90)
    expect(field).to_have_value(original_value)
    page.keyboard.press('Escape')
    checkpoint(prefix + '-slow-control-drag-preserves-original-parameters-and-unique-identity')

    # Cancel a second copy after crossing the threshold: no added history/node.
    source.click()
    x,y = center(source)
    page.keyboard.down('Control')
    page.mouse.move(x,y)
    page.mouse.down()
    page.mouse.move(x+110,y+70,steps=8)
    page.keyboard.press('Escape')
    page.mouse.up()
    page.keyboard.up('Control')
    expect(nodes).to_have_count(count+1)
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    assert source.evaluate(position) == initial
    checkpoint(prefix + '-escape-rolls-back-copy-drag')
    # Remove the intentionally edited copy through the UI.
    page.locator(('[data-node-id="' if prompt else '[id="') + copied_id + '"]').click()
    page.keyboard.press('Delete')
    expect(nodes).to_have_count(count)
    source.click()


def check_editor(page, prompt, checkpoint, center):
    check_node_activation(page, prompt, checkpoint)
    check_precise_copy(page, prompt, checkpoint, center)
    check_group_copy(page, prompt, checkpoint, center)
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


def check_group_copy(page, prompt, checkpoint, center):
    prefix = 'prompt' if prompt else 'agentic'
    nodes = page.locator('.pmt-node' if prompt else '.canvas-item')
    wires = page.locator('.pmt-edge' if prompt else '.connection-group:not(.connection-preview)')
    count, links = nodes.count(), wires.count()
    read_nodes = """els => els.map(el => ({id:el.dataset.nodeId || el.id,
        label:el.querySelector('.pmt-node-label strong')?.textContent || el.textContent,
        x:parseFloat(el.style.left),y:parseFloat(el.style.top)}))"""
    before = nodes.evaluate_all(read_nodes)
    page.locator('#submonitor-container').focus()
    page.keyboard.press('Control+a')
    x,y = center(nodes.first)
    page.keyboard.down('Control')
    page.mouse.move(x,y)
    page.mouse.down()
    page.mouse.move(x+1,y+1)
    page.mouse.move(x+60,y+45,steps=10)
    page.mouse.up()
    page.keyboard.up('Control')
    expect(nodes).to_have_count(count*2)
    expect(wires).to_have_count(links*2)
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    after = nodes.evaluate_all(read_nodes)
    assert after[:count] == before, 'Group copying mutated originals'
    assert len({n['id'] for n in after}) == count*2
    copied = after[count:]
    assert not ({n['label'] for n in before} & {n['label'] for n in copied})
    for old,new in zip(before,copied):
        assert abs(new['x']-old['x']-60)<.1 and abs(new['y']-old['y']-45)<.1
    page.keyboard.press('Control+z')
    expect(nodes).to_have_count(count)
    expect(wires).to_have_count(links)
    expect(page.locator('[data-action="redo"]' if prompt else '#acp-redo')).to_be_enabled()
    page.keyboard.press('Control+Shift+z')
    expect(nodes).to_have_count(count*2)
    expect(wires).to_have_count(links*2)
    assert nodes.evaluate_all(read_nodes) == after
    expect(page.locator('[data-action="undo"]' if prompt else '#acp-undo')).to_be_enabled()
    page.keyboard.press('Control+z')
    expect(nodes).to_have_count(count)
    expect(wires).to_have_count(links)
    expect(page.locator('[data-action="redo"]' if prompt else '#acp-redo')).to_be_enabled()
    checkpoint(prefix + '-group-copy-internal-wires-unique-names-one-undo-redo')


def check_agent_catalog(page, checkpoint, foreground):
    palette = page.locator('#agents-list .agent-tool-item')
    expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)
    names = palette.evaluate_all('els => els.map(el => el.dataset.content)')
    assert len(names) >= 89
    initial = page.locator('.canvas-item').count()
    for index, name in enumerate(names, 1):
        foreground(page)
        expect(page.locator('#acp-flow-settings')).to_be_enabled()
        page.locator('#acp-agent-search').fill(name)
        tool = palette.filter(has_text=re.compile('^' + re.escape(name) + '$'))
        try:
            with page.expect_response(lambda response: '/deploy_agent_template/' in response.url) as deployed:
                # Keep clear of the empty-state example button above the canvas.
                tool.drag_to(page.locator('#submonitor-container'), target_position={'x': 250, 'y': 200})
        except Exception:
            checkpoint('catalog-drop-failure-' + str(index))
            raise
        assert deployed.value.ok, name
        nodes = page.locator('.canvas-item')
        expect(nodes).to_have_count(initial + 1)
        node = nodes.last
        identity = node.get_attribute('id')
        node.dblclick(delay=100)
        if name.lower() == 'parametrizer':
            # Its documented mapping editor requires a supported source and a
            # target. An unconnected node correctly opens validation instead.
            error = page.locator('#parametrizer-error-overlay')
            expect(error).to_be_visible()
            expect(error).to_contain_text('No source agent connected')
            page.keyboard.press('Escape')
            expect(error).to_have_count(0)
            check_parametrizer_wiring(page, page.locator('[id="' + identity + '"]'), checkpoint, foreground)
            node = page.locator('[id="' + identity + '"]')
        else:
            dialog = page.locator('.ui-dialog:visible')
            expect(dialog).to_have_count(1)
            title = dialog.locator('.ui-dialog-title').inner_text()
            assert identity in title, (name, title)
            page.keyboard.press('Escape')
            expect(dialog).to_have_count(0)
        node.click()
        page.keyboard.press('Delete')
        expect(nodes).to_have_count(initial)
        expect(page.locator('#acp-flow-settings')).to_be_enabled()
        print('CATALOG DOUBLE-CLICK:', index, '/', len(names), name, 'PASS', flush=True)
        if index % 10 == 0:
            checkpoint('agentic-catalog-double-click-' + str(index))
    page.locator('#acp-agent-search').fill('')
    checkpoint('agentic-catalog-all-' + str(len(names)) + '-node-dialogs')


def check_parametrizer_wiring(page, node, checkpoint, foreground):
    """Book chapter 25: Apirer -> Parametrizer -> Kyber-Cipher, never executed."""
    peers = []
    for name, x, y in [('Apirer', 80, 70), ('Kyber-Cipher', 500, 70)]:
        foreground(page)
        page.locator('#acp-agent-search').fill(name)
        tool = page.locator('#agents-list .agent-tool-item').filter(has_text=re.compile('^' + re.escape(name) + '$'))
        with page.expect_response(lambda response: '/deploy_agent_template/' in response.url) as deployed:
            tool.drag_to(page.locator('#submonitor-container'), target_position={'x': x, 'y': y})
        assert deployed.value.ok
        peers.append(page.locator('.canvas-item').last.get_attribute('id'))
    source, target = [page.locator('[id="' + identity + '"]') for identity in peers]

    def connect(output, input_port):
        foreground(page)
        a, b = output.bounding_box(), input_port.bounding_box()
        with page.expect_response(lambda response: '/update_parametrizer_connection/' in response.url) as updated:
            page.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2)
            page.mouse.down()
            page.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2, steps=12)
            page.mouse.up()
        assert updated.value.ok

    connect(source.locator('.output-triangle').first, node.locator('.input-triangle').first)
    connect(node.locator('.output-triangle').first, target.locator('.input-triangle').first)
    node.dblclick(delay=100)
    mapping = page.locator('#parametrizer-dialog-overlay')
    expect(mapping).to_be_visible()
    expect(mapping.locator('.parametrizer-source-item[data-field="response_body"]')).to_be_visible()
    expect(mapping.locator('.parametrizer-target-item[data-param="buffer"]')).to_be_visible()
    mapping.locator('.parametrizer-source-item[data-field="response_body"]').click()
    mapping.locator('.parametrizer-target-item[data-param="buffer"]').click()
    expect(mapping.locator('svg path')).to_have_count(1)
    with page.expect_response(lambda response: '/save_parametrizer_scheme/' in response.url) as saved:
        mapping.get_by_role('button', name='Save Mappings', exact=True).click()
    assert saved.value.ok
    expect(mapping).to_have_count(0)
    node.dblclick(delay=100)
    expect(mapping.locator('svg path')).to_have_count(1)
    checkpoint('parametrizer-connected-native-dialog-and-saved-mapping')
    page.keyboard.press('Escape')

    # Copy the whole connected chain; the mapping CSV and its node references
    # must survive independently of config.yaml and a complete undo/redo cycle.
    originals = set(page.locator('.canvas-item').evaluate_all('els => els.map(el => el.id)'))
    node.click()
    source.click(modifiers=['Control'])
    target.click(modifiers=['Control'])
    box = node.bounding_box()
    foreground(page)
    page.keyboard.down('Control')
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2 + 300, steps=20)
    page.mouse.up()
    page.keyboard.up('Control')
    expect(page.locator('#acp-flow-settings')).to_be_enabled(timeout=30000)
    expect(page.locator('.canvas-item')).to_have_count(len(originals) + 3)
    copies = set(page.locator('.canvas-item').evaluate_all('els => els.map(el => el.id)')) - originals
    copy_id = next(identity for identity in copies if identity.startswith('parametrizer-'))

    def check_copy_mapping():
        page.locator('[id="' + copy_id + '"]').dblclick(delay=100)
        expect(mapping.locator('svg path')).to_have_count(1)
        for identity in copies - {copy_id}:
            expect(mapping).to_contain_text(identity.replace('-', '_'))
        page.keyboard.press('Escape')

    check_copy_mapping()
    page.locator('#acp-undo').click()
    expect(page.locator('.canvas-item')).to_have_count(len(originals))
    expect(page.locator('#acp-redo')).to_be_enabled(timeout=30000)
    page.locator('#acp-redo').click()
    expect(page.locator('#acp-undo')).to_be_enabled(timeout=30000)
    expect(page.locator('.canvas-item')).to_have_count(len(originals) + 3)
    check_copy_mapping()
    checkpoint('parametrizer-group-copy-mapping-artifact-and-undo-redo')
    page.locator('#acp-undo').click()
    expect(page.locator('#acp-redo')).to_be_enabled(timeout=30000)
    expect(page.locator('.canvas-item')).to_have_count(len(originals))
    for identity in peers:
        page.locator('[id="' + identity + '"]').click()
        page.keyboard.press('Delete')
        expect(page.locator('[id="' + identity + '"]')).to_have_count(0)
        expect(page.locator('#acp-flow-settings')).to_be_enabled(timeout=30000)
