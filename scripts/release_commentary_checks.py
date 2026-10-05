# Tlamatini Author Banner — Angela López Mendoza
"""Shared real-UI rich-commentary acceptance for source and frozen runs."""
import json
from pathlib import Path

from playwright.sync_api import expect
import panel_search_title_visible as visible
from prompt_flow_connections_visible import require_browser_foreground

ROOT = Path(__file__).resolve().parents[1]


def run_commentary_checks(page, OUT, BASE, checkpoint, errors):
    def menu(action):
        page.get_by_role('button', name='File', exact=True).click()
        target = page.locator('.dropdown-menu [data-action="' + action + '"]').first
        if not target.is_visible():
            print('Menu diagnostics:', page.locator('.nav-item.dropdown').evaluate('(el) => ({html: el.outerHTML, style: getComputedStyle(el.querySelector(".dropdown-menu")).display})'), errors, flush=True)
            visible.photograph('file-menu-diagnostic')
        target.click()
        accept = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
        if accept.is_visible():
            accept.click()

    def save(name):
        menu('save')
        page.locator('#pmt-field-filename').fill(name)
        with page.expect_download() as downloaded:
            page.get_by_role('button', name='Download .fpmt', exact=True).click()
        path = OUT / name
        downloaded.value.save_as(path)
        return path, json.loads(path.read_text(encoding='utf-8'))

    def open_file(path):
        page.get_by_role('button', name='File', exact=True).click()
        with page.expect_file_chooser() as chooser:
            page.locator('[data-action="open"]').click()
        chooser.value.set_files(str(path))
        accept = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
        if accept.is_visible():
            accept.click()

    def center(locator):
        require_browser_foreground(page)
        box = locator.bounding_box()
        return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2

    menu('new')
    divider = page.locator('#pmt-output-divider')
    divider.focus()
    divider.press('Home')
    for _ in range(3):
        divider.press('Shift+ArrowUp')
    expect(page.locator('.pmt-node')).to_have_count(0)
    page.locator('[data-action="fit"]').click()
    expect(page.locator('.agent-tool-item')).to_have_count(8)
    css = page.locator('link[href*="prompt_flow_panel.css"]').get_attribute('href')
    assert '?v=' in css, 'The stylesheet must carry its current cache version'
    assert page.request.get(BASE + css).body() == (ROOT / 'Tlamatini/agent/static/agent/css/prompt_flow_panel.css').read_bytes()
    page.locator('.agent-tool-item[data-type="user_commentary"]').click()
    comment = page.locator('.pmt-node[data-type="user_commentary"]')
    toolbar = page.get_by_role('region', name='Comment formatting')
    expect(toolbar).to_be_visible()
    expect(toolbar).to_have_css('position', 'fixed')
    expect(comment.locator('.pmt-comment-handle')).to_have_count(8)
    expect(comment.locator('.pmt-port')).to_have_count(0)
    expect(page.locator('#pmt-play')).to_be_disabled()
    expect(page.locator('#pmt-start option')).to_have_count(1)
    expect(page.locator('#pmt-field-width, #pmt-field-height')).to_have_count(0)
    checkpoint('01-floating-toolbar-and-eight-border-handles')
    paragraph = ('Review paragraph: ñ <script> literal {{last_output}}. This note stays on the canvas.\n\n' * 60).rstrip()
    comment.dblclick(position={'x': 70, 'y': 55})
    editor = page.get_by_role('textbox', name='Static User Commentary text')
    expect(editor).to_be_visible()
    editor.fill(paragraph)
    editor.press('Control+a')
    assert editor.evaluate('(el) => el.scrollHeight <= el.clientHeight + 2'), 'Editor must grow while typing'
    expect(editor).to_have_css('overflow-y', 'hidden')
    toolbar.get_by_role('combobox', name='Comment font').select_option('Georgia')
    toolbar.get_by_role('combobox', name='Comment text size').select_option('20')
    toolbar.get_by_role('button', name='Blue comment', exact=True).click()
    toolbar.get_by_role('button', name='Bold', exact=True).click()
    toolbar.get_by_role('button', name='Italic', exact=True).click()
    toolbar.get_by_role('button', name='Align right', exact=True).click()
    toolbar.locator('summary[aria-label="Text color"]').click()
    toolbar.get_by_role('button', name='Blue text', exact=True).click()
    expect(editor).to_have_css('font-size', '20px')
    expect(editor).to_have_css('font-style', 'italic')
    expect(editor).to_have_css('font-weight', '700')
    expect(editor).to_have_css('text-align', 'right')
    expect(editor).to_have_css('color', 'rgb(29, 78, 216)')
    expect(comment.locator('.pmt-shape')).to_have_css('fill', 'rgb(219, 234, 254)')
    assert editor.evaluate('(el) => el.scrollHeight <= el.clientHeight + 2'), 'Formatting must reflow the whole note'
    toolbar.get_by_role('button', name='Done', exact=True).click()
    expect(comment.locator('.pmt-comment-text')).to_have_text(paragraph)
    assert comment.locator('.pmt-comment-text script').count() == 0
    assert comment.locator('.pmt-comment-text').evaluate('(el) => el.scrollHeight <= el.clientHeight')
    checkpoint('02-live-floating-formatting-and-long-text-containment')
    # Configure now edits on the canvas; it must never create a dialog.
    page.locator('[data-action="configure"]').click()
    expect(editor).to_be_visible()
    expect(page.locator('.ui-dialog:visible')).to_have_count(0)
    editor.fill('Cancelled replacement')
    toolbar.get_by_role('button', name='Pink comment', exact=True).click()
    toolbar.get_by_role('combobox', name='Comment text size').select_option('48')
    toolbar.get_by_role('button', name='Cancel comment changes').click()
    expect(comment.locator('.pmt-comment-text')).to_have_text(paragraph)
    expect(comment.locator('.pmt-comment-text')).to_have_css('font-size', '20px')
    expect(comment.locator('.pmt-shape')).to_have_css('fill', 'rgb(219, 234, 254)')
    checkpoint('03-no-configuration-dialog-and-transactional-cancel')
    paragraph = 'A note for the next review\n\nKeep the explanation clear and give this decision a little more room. This comment belongs to the canvas; the flow continues independently.'
    toolbar.get_by_role('button', name='Edit comment text').click()
    editor.fill(paragraph)
    editor.press('Control+a')
    toolbar.get_by_role('combobox', name='Comment text size').select_option('16')
    toolbar.get_by_role('button', name='Bold', exact=True).click()
    toolbar.get_by_role('button', name='Italic', exact=True).click()
    toolbar.get_by_role('button', name='Align left', exact=True).click()
    toolbar.get_by_role('button', name='Done', exact=True).click()
    page.locator('[data-action="zoom-out"]').click()

    def drag_border(direction, dx, dy, cancel=False):
        require_browser_foreground(page)
        box = comment.bounding_box()
        # Hit the figure's border itself, not just its small visible grip.
        body_bottom = box['y'] + box['height'] - 18 * .9
        x = box['x'] + (box['width'] if 'e' in direction else 0) if ('e' in direction or 'w' in direction) else box['x'] + box['width'] / 2
        y = (box['y'] if 'n' in direction else body_bottom) if ('n' in direction or 's' in direction) else (box['y'] + body_bottom) / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + dx, y + dy, steps=10)
        if cancel:
            page.keyboard.press('Escape')
        page.mouse.up()
        return box, comment.bounding_box()

    for direction in ('e', 's', 'w', 'n', 'ne', 'nw', 'se', 'sw'):
        dx = -36 if 'w' in direction else 36 if 'e' in direction else 0
        dy = -27 if 'n' in direction else 27 if 's' in direction else 0
        old, new = drag_border(direction, dx, dy)
        if dx:
            assert abs(new['width'] - old['width'] - 36) < 2, (direction, old, new)
        if dy:
            assert abs(new['height'] - old['height'] - 27) < 2, (direction, old, new)
        if 'w' in direction:
            assert abs(new['x'] + new['width'] - old['x'] - old['width']) < 2
        if 'n' in direction:
            assert abs(new['y'] + new['height'] - old['y'] - old['height']) < 2
        page.locator('[data-action="undo"]').click()
        restored = comment.bounding_box()
        assert all(abs(restored[k] - old[k]) < 2 for k in ('x', 'y', 'width', 'height'))
        checkpoint('04-' + direction + '-border-resize-and-undo')
    old, new = drag_border('se', 45, 36, cancel=True)
    assert all(abs(new[k] - old[k]) < 2 for k in ('x', 'y', 'width', 'height'))
    old, new = drag_border('se', 90, 72)
    page.locator('[data-action="undo"]').click()
    page.locator('[data-action="redo"]').click()
    assert abs(comment.bounding_box()['width'] - new['width']) < 2
    # Resize remains available while writing, without losing the editor/caret.
    toolbar.get_by_role('button', name='Edit comment text').click()
    old, new = drag_border('e', 45, 0)
    expect(editor).to_have_text(paragraph)
    assert editor.evaluate('(el) => el.scrollHeight <= el.clientHeight + 2')
    toolbar.get_by_role('button', name='Cancel comment changes').click()
    assert abs(comment.bounding_box()['width'] - old['width']) < 2
    toolbar.get_by_role('button', name='Fit bubble to text').click()
    assert comment.locator('.pmt-comment-text').evaluate('(el) => el.scrollHeight <= el.clientHeight')
    checkpoint('05-resize-cancel-redo-and-live-edit-fit')
    page.locator('[data-action="duplicate"]').click()
    expect(comment).to_have_count(2)
    page.locator('#submonitor-container').focus()
    page.keyboard.press('ArrowDown')
    page.keyboard.press('Shift+ArrowDown')
    page.keyboard.press('Shift+ArrowDown')
    page.keyboard.press('Shift+ArrowDown')
    page.keyboard.press('Shift+ArrowDown')
    page.keyboard.press('Shift+ArrowDown')
    page.locator('[data-action="fit"]').click()
    portable, payload = save('commentaries.fpmt')
    assert payload['version'] == 2 and payload['start'] is None and payload['edges'] == []
    assert len(payload['nodes']) == 2
    assert all(n['config']['text'] == paragraph and n['config']['font_family'] == 'Georgia' and n['config']['text_color'] == '#1d4ed8' for n in payload['nodes'])
    open_file(portable)
    expect(comment).to_have_count(2)
    page.wait_for_timeout(500)
    page.reload()
    expect(comment).to_have_count(2)
    checkpoint('06-multiple-notes-file-and-draft-roundtrip')
    # Keep the static notes, then add real input/history-clear operations.
    page.locator('.agent-tool-item[data-type="user_input"]').click()
    page.locator('#submonitor-container').focus()
    for _ in range(18):
        page.keyboard.press('Shift+ArrowRight')
    page.locator('.agent-tool-item[data-type="clean_history"]').click()
    page.locator('#submonitor-container').focus()
    for _ in range(26):
        page.keyboard.press('Shift+ArrowRight')
    page.locator('[data-action="fit"]').click()
    input_node = page.locator('.pmt-node[data-type="user_input"]')
    clear_node = page.locator('.pmt-node[data-type="clean_history"]')
    source = input_node.locator('.output-triangle')
    target = clear_node.locator('.input-triangle')
    page.mouse.move(*center(source))
    page.mouse.down()
    page.mouse.move(*center(target), steps=8)
    page.mouse.up()
    expect(page.locator('.pmt-edge')).to_have_count(1)
    expect(page.locator('#pmt-start option')).to_have_count(2)
    page.locator('#pmt-play').click()
    expect(page.locator('#pmt-field-reply')).to_be_visible()
    expect(toolbar).to_be_hidden()
    expect(comment.locator('.pmt-comment-handle:enabled')).to_have_count(0)
    expect(page.locator('.ui-dialog-title')).to_have_text('User Input')
    page.locator('#pmt-field-reply').fill('Same runtime reply: ñ ✓')
    page.get_by_role('button', name='Continue flow', exact=True).click()
    expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
    expect(page.locator('#pmt-run-log')).to_contain_text('Same runtime reply: ñ ✓')
    expect(comment.locator('.pmt-node-status')).to_have_count(0)
    checkpoint('07-real-user-input-playback-with-static-notes')
    page.locator('#pmt-play').click()
    expect(page.locator('#pmt-field-reply')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#pmt-run-state')).to_have_text('stopped', timeout=30000)
    checkpoint('08-user-input-escape-stops-flow')
    legacy = {'format': 'tlamatini-prompting-flow', 'version': 1, 'name': 'Legacy reply flow',
              'start': 'old', 'max_steps': 20, 'nodes': [
                  {'id': 'old', 'type': 'user_commentary', 'label': 'User Commentary', 'x': 70, 'y': 60, 'config': {'text': 'Legacy request'}},
              ], 'edges': []}
    legacy_path = OUT / 'legacy.fpmt'
    legacy_path.write_text(json.dumps(legacy), encoding='utf-8')
    open_file(legacy_path)
    expect(input_node).to_have_count(1)
    expect(comment).to_have_count(0)
    expect(input_node.locator('.pmt-node-label')).to_have_text('User Input')
    page.locator('#pmt-play').click()
    expect(page.locator('#pmt-field-reply')).to_be_visible()
    page.locator('#pmt-field-reply').fill('Legacy mechanism preserved')
    page.get_by_role('button', name='Continue flow', exact=True).click()
    expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=30000)
    _, migrated = save('migrated.fpmt')
    assert migrated['version'] == 2 and migrated['nodes'][0]['type'] == 'user_input'
    checkpoint('09-legacy-input-migration-and-playback')
    open_file(ROOT / 'docs/examples/prompting-kickoff.fpmt')
    expect(page.locator('.pmt-node')).to_have_count(8)
    page.locator('[data-action="fit"]').click()
    checkpoint('10-bundled-eight-asset-example')
    # Finish with the actual redesigned surface, not the tiny all-operation tour.
    menu('new')
    page.locator('[data-action="fit"]').click()
    samples = [
        ('Review the decision\n\nKeep the question focused. Give the reader enough context to choose the next step with confidence.', 'Georgia', 'Blue', 100, 220),
        ('A little context helps\n\nUse this space for a reminder, an explanation, or feedback for the next person working on the flow.', 'Nunito', 'Yellow', 620, 220),
        ('Design notes · ñ 👩🏽‍💻\n\nDifferent ideas deserve different emphasis.\n\nLiteral <script> & {{last_output}} stay safely on the canvas.', 'Arial', 'Green', 1140, 220),
    ]
    for text, font, color, target_x, target_y in samples:
        page.locator('.agent-tool-item[data-type="user_commentary"]').click()
        note = comment.last
        note.dblclick(position={'x': 70, 'y': 55})
        editor.fill(text)
        editor.press('Control+a')
        toolbar.get_by_role('combobox', name='Comment font').select_option(font)
        toolbar.get_by_role('button', name=color + ' comment', exact=True).click()
        # Select an actual phrase with the keyboard; each note has mixed styles.
        editor.press('Control+Home')
        editor.press('Shift+End')
        toolbar.get_by_role('combobox', name='Comment font').select_option('Verdana')
        toolbar.get_by_role('combobox', name='Comment text size').select_option('28')
        toolbar.get_by_role('button', name='Bold', exact=True).click()
        toolbar.locator('summary[aria-label="Text color"]').click()
        toolbar.get_by_role('button', name='Blue text', exact=True).click()
        expect(editor.locator('[data-comment-run]').first).to_have_css('font-family', 'Verdana')
        expect(editor.locator('[data-comment-run]').first).to_have_css('font-size', '28px')
        expect(editor.locator('[data-comment-run]').last).to_have_css('font-family', font)
        # Collapsed-caret formatting styles only the newly typed ending.
        editor.press('Control+End')
        toolbar.get_by_role('combobox', name='Comment font').select_option('Arial')
        toolbar.get_by_role('combobox', name='Comment text size').select_option('12')
        toolbar.get_by_role('button', name='Italic', exact=True).click()
        toolbar.get_by_role('button', name='Underline', exact=True).click()
        editor.press('End')
        page.keyboard.insert_text(' — ready for review')
        expect(editor.locator('[data-comment-run]').last).to_have_css('font-style', 'italic')
        expect(editor.locator('[data-comment-run]').last).to_have_css('text-decoration-line', 'underline')
        editor.press('Control+z')
        expect(editor).to_have_text(text)
        editor.press('Control+y')
        expect(editor).to_have_text(text + ' — ready for review')
        toolbar.get_by_role('button', name='Done', exact=True).click()
        origin = note.bounding_box()
        canvas_box = page.locator('#pmt-world').bounding_box()
        page.mouse.move(origin['x'] + 80, origin['y'] + 20)
        page.mouse.down()
        page.mouse.move(canvas_box['x'] + target_x + 80, canvas_box['y'] + target_y + 20, steps=10)
        page.mouse.up()
    page.locator('[data-action="fit"]').click()
    comment.first.click(position={'x': 80, 'y': 20})
    expect(toolbar).to_be_visible()
    expect(comment.first.locator('.pmt-shape')).to_have_css('stroke', 'rgb(121, 218, 205)')
    box, bubble = toolbar.bounding_box(), comment.first.bounding_box()
    assert box['x'] + box['width'] <= page.evaluate('window.innerWidth')
    assert box['y'] + box['height'] <= page.evaluate('window.innerHeight')
    assert box['x'] >= bubble['x'] + bubble['width'] or box['x'] + box['width'] <= bubble['x'] or box['y'] >= bubble['y'] + bubble['height'] or box['y'] + box['height'] <= bubble['y'], 'Floating tools must leave this note unobstructed'
    checkpoint('11-mixed-fonts-ranges-and-caret-formatting-in-three-comments')
    # Border handles are reachable by keyboard as well as by mouse.
    handle = comment.first.locator('[data-resize="e"]')
    original_width = float(comment.first.evaluate('(el) => parseFloat(el.style.width)'))
    handle.focus()
    handle.press('ArrowRight')
    assert float(comment.first.evaluate('(el) => parseFloat(el.style.width)')) == original_width + 10
    page.locator('[data-action="undo"]').click()
    assert float(comment.first.evaluate('(el) => parseFloat(el.style.width)')) == original_width
    comment.first.click(position={'x': 80, 'y': 20})
    checkpoint('12-keyboard-resize-and-restored-final-layout')
    # Compare rendered line boxes, geometry, typography and SVG paths across real downloads/opens.
    def rendering():
        page.evaluate('document.fonts.ready')
        return comment.evaluate_all('''els => els.map(el => {
            const scale = el.getBoundingClientRect().width / el.offsetWidth;
            const box = el.getBoundingClientRect();
            const round = x => Math.round(x * 100) / 100;
            return { id: el.dataset.nodeId, x: el.style.left, y: el.style.top, width: el.style.width, height: el.style.height,
                path: el.querySelector('.pmt-shape').getAttribute('d'), fill: getComputedStyle(el.querySelector('.pmt-shape')).fill,
                runs: [...el.querySelectorAll('[data-comment-run]')].map(span => {
                    const style = getComputedStyle(span), range = document.createRange(); range.selectNodeContents(span);
                    return { text: span.textContent, font: style.fontFamily, size: style.fontSize, color: style.color,
                        bold: style.fontWeight, italic: style.fontStyle, underline: style.textDecorationLine,
                        lines: [...range.getClientRects()].map(r => [round((r.x - box.x) / scale), round((r.y - box.y) / scale), round(r.width / scale), round(r.height / scale)]) };
                }) };
        })''')

    page.locator('[data-action="fit"]').click()
    original_render = rendering()
    original_file, original_payload = save('mixed-commentaries.fpmt')
    assert len(original_payload['nodes']) == 3
    assert all(len(n['config']['runs']) >= 3 for n in original_payload['nodes'])
    assert all(''.join(run['text'] for run in n['config']['runs']) == n['config']['text'] for n in original_payload['nodes'])
    for cycle in range(3):
        menu('new')
        expect(comment).to_have_count(0)
        open_file(original_file)
        expect(comment).to_have_count(3)
        page.locator('[data-action="fit"]').click()
        assert rendering() == original_render, 'Rendering changed on file reload ' + str(cycle)
        original_file, reloaded_payload = save('mixed-commentaries.fpmt')
        assert reloaded_payload == original_payload, 'Saved document changed after reopening'
    page.wait_for_timeout(500)
    page.reload()
    expect(comment).to_have_count(3)
    page.locator('[data-action="fit"]').click()
    assert rendering() == original_render, 'Draft recovery changed rich text rendering'
    (OUT / 'rich-rendering.json').write_text(json.dumps(original_render, ensure_ascii=False, indent=2), encoding='utf-8')
    comment.first.click(position={'x': 80, 'y': 20})
    checkpoint('13-three-file-save-open-cycles-and-draft-render-identically')
    # Duplicating preserves every run; deleting and undoing restores the rendered note.
    page.locator('[data-action="duplicate"]').click()
    expect(comment).to_have_count(4)
    _, duplicated = save('mixed-commentaries-duplicate.fpmt')
    assert duplicated['nodes'][-1]['config'] == duplicated['nodes'][0]['config']
    page.locator('[data-action="delete"]').click()
    expect(comment).to_have_count(3)
    page.locator('[data-action="undo"]').click()
    expect(comment).to_have_count(4)
    page.locator('[data-action="redo"]').click()
    expect(comment).to_have_count(3)
    page.locator('[data-action="fit"]').click()
    assert rendering() == original_render
    comment.first.click(position={'x': 80, 'y': 20})
    checkpoint('14-rich-comment-duplicate-delete-undo-redo')
    # Rich copy/paste and native Enter/delete operate inside the same graphical editor.
    toolbar.get_by_role('button', name='Edit comment text').click()
    before_text = original_payload['nodes'][0]['config']['text']
    editor.press('Control+a')
    editor.press('Control+c')
    editor.press('Control+End')
    editor.press('Enter')
    page.keyboard.insert_text('👩🏽‍💻')
    editor.press('Backspace')
    expect(editor).to_have_text(before_text + '\n')
    editor.press('Control+v')
    expect(editor).to_have_text(before_text + '\n' + before_text)
    expect(editor.locator('[data-comment-run]').last).to_have_css('font-style', 'italic')
    assert editor.locator('[data-comment-run]').count() >= 6
    editor.press('Control+z')
    expect(editor).to_have_text(before_text + '\n')
    toolbar.get_by_role('button', name='Cancel comment changes').click()
    assert rendering() == original_render
    checkpoint('15-rich-clipboard-enter-grapheme-delete-and-cancel')
    # Zoom-triggered draft writes must not leak an uncommitted rich edit.
    toolbar.get_by_role('button', name='Edit comment text').click()
    editor.fill('This cancelled text must never replace the saved draft')
    page.locator('[data-action="zoom-out"]').click()
    page.wait_for_timeout(350)
    draft_text = page.evaluate('JSON.parse(localStorage.getItem("tlamatini.prompting-flow.draft.v1." + document.body.dataset.userId)).flow.nodes[0].config.text')
    assert draft_text == before_text
    toolbar.get_by_role('button', name='Cancel comment changes').click()
    expect(comment.first).to_have_css('outline-style', 'none')
    page.reload()
    page.locator('[data-action="fit"]').click()
    assert rendering() == original_render
    comment.first.click(position={'x': 80, 'y': 20})
    checkpoint('16-cancelled-rich-edit-never-leaks-into-draft')
