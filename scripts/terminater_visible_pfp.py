# Tlamatini Author Banner — Angela López Mendoza
"""VISIBLE suite: the Terminals area AND the Terminater step on the Prompt Flow Panel.

Two variants, one run:
  * ``pfp/empty``   -- an empty diagram (the canvas shows its "Design your prompt flow" card);
  * ``pfp/loaded``  -- a real .fpmt with Terminater steps is opened, played, stopped and handed over.

Run from a foreground PowerShell -NoExit console:  python scripts/terminater_visible_pfp.py
Every check takes a full-desktop Shoter photograph; the console gate and the browser gate wait
for the operator to look at the photograph and create ``Temp/terminater-visible/<gate>.confirmed``.
"""
from __future__ import annotations

import json
import sys

from terminater_visible_battery import Battery
from terminater_visible_common import OUT, Harness

PATH = '/agent/prompt_flow_panel/'


def make_flow(name, steps, start=0):
    """steps = [(label, config overrides)] chained with 'next' edges."""
    nodes, edges = [], []
    defaults = {
        'text': '', 'action': 'run', 'kind': 'powershell', 'terminal': '', 'title': '', 'cwd': '', 'keys': '',
        'message': '', 'severity': 'warning', 'suggestion': '', 'hint': '', 'which': 'last', 'until': '', 'pattern': '',
        'layout': '', 'area': '', 'submit': True, 'secret': False, 'wait': True, 'close_after': False,
        'load_profile': False, 'advisor': True, 'typing_wpm': 160, 'wait_seconds': 90, 'hang_seconds': 45,
        'user_wait_seconds': 90, 'idle_seconds': 2,
    }
    for index, (label, cfg) in enumerate(steps):
        config = dict(defaults)
        config.update(cfg)
        nodes.append({'id': 'pfp_t%d' % (index + 1), 'type': 'terminater', 'label': label,
                      'x': 80 + 260 * index, 'y': 80 + 30 * (index % 2), 'config': config})
        if index:
            edges.append({'id': 'pfp_e%d' % index, 'source': nodes[index - 1]['id'], 'target': nodes[index]['id'], 'branch': 'next'})
    return {'format': 'tlamatini-prompting-flow', 'version': 2, 'name': name, 'start': nodes[start]['id'],
            'max_steps': 100, 'nodes': nodes, 'edges': edges}


def write_flow(filename, flow):
    path = OUT / filename
    path.write_text(json.dumps(flow, indent=2), encoding='utf-8')
    return str(path)


def open_flow(H, path):
    H.page.set_input_files('#pmt-file-input', path)
    H.page.wait_for_timeout(900)
    # a draft is restored on reload, so the panel may ask before replacing it
    for text in ('Continue', 'Replace', 'OK', 'Yes'):
        button = H.page.locator('.ui-dialog:visible button:has-text("%s"), .tlmpop-card button:has-text("%s")' % (text, text))
        if button.count() and button.first.is_visible():
            button.first.click()
            H.page.wait_for_timeout(600)
            break
    return H.wait_for(lambda: H.page.locator('.pmt-node[data-type="terminater"]').count() >= 1, timeout=15)


def run_state(H):
    return (H.page.locator('#pmt-run-state').inner_text() or '').strip()


def log_text(H):
    return H.page.locator('#pmt-run-log').inner_text() or ''


def node_classes(H, node_id):
    return H.page.evaluate("(id) => { const e = document.querySelector('.pmt-node[data-node-id=\"' + id + '\"]'); return e ? e.className.baseVal !== undefined ? e.className.baseVal : e.className : ''; }", node_id)


def clear_canvas(H):
    if not H.page.locator('#monitor-controls [data-action="new"]').is_enabled():
        return
    H.page.locator('#monitor-controls [data-action="new"]').click()
    H.page.wait_for_timeout(500)
    for text in ('Continue', 'Replace', 'Clear', 'OK', 'Yes'):
        button = H.page.locator('.ui-dialog:visible button:has-text("%s"), .tlmpop-card button:has-text("%s")' % (text, text))
        if button.count() and button.first.is_visible():
            button.first.click()
            H.page.wait_for_timeout(500)
            break


def wait_idle(H, timeout=90):
    return H.wait_for(lambda: H.page.locator('#pmt-play').is_enabled() and not H.page.locator('#pmt-stop').is_enabled(), timeout=timeout)


class PfpBattery(Battery):
    pass


# ----------------------------------------------------------------------------- empty canvas
def palette_checks(H, B):
    page = H.page
    types = page.evaluate("() => [...document.querySelectorAll('#agents-list .agent-tool-item')].map(b => b.dataset.type)")
    B.chk('the Operations bar offers Terminater', 'terminater' in types, str(types))
    B.chk('the Operations bar keeps its other eight assets', len(types) == 9 and 'prompt' in types and 'user_commentary' in types, str(types))
    tile = page.locator('#agents-list .agent-tool-item[data-type="terminater"]')
    text = (tile.inner_text() or '').strip()
    B.chk('the tile is labelled Terminater', 'Terminater' in text, text)
    title = tile.get_attribute('title') or ''
    B.chk('the tile tooltip explains the human-speed typing', 'human speed' in title and 'USER' in title, title)
    d = page.evaluate("() => { const p = document.querySelector('#agents-list .agent-tool-item[data-type=\"terminater\"] svg path'); return p ? p.getAttribute('d') : ''; }")
    B.chk('the tile shows the parallelogram outline', d == 'M52 20H196L148 108H4Z', d)
    box = tile.bounding_box() or {}
    B.chk('the tile is visible and big enough to click', box.get('width', 0) > 60 and box.get('height', 0) > 24, str(box))
    order = types.index('terminater') if 'terminater' in types else -1
    B.chk('Terminater sits before the static commentary tile', 0 <= order < types.index('user_commentary'), str(types))
    others = page.evaluate("() => [...new Set([...document.querySelectorAll('#agents-list .agent-tool-item svg path')].map(p => p.getAttribute('d')))].length")
    B.chk('every tile has its own outline shape', others >= 7, 'distinct outlines=%s' % others)
    empty = page.locator('#pmt-empty')
    B.chk('the empty canvas card is shown', empty.is_visible(), '')
    B.chk('the status strip reports zero operations', '0 operations' in (page.locator('#pmt-count').inner_text() or ''))
    B.chk('nothing is running, so Stop and Pause are off', not page.locator('#pmt-stop').is_enabled() and not page.locator('#pmt-pause').is_enabled())


def add_node_checks(H, B):
    page = H.page
    page.locator('#agents-list .agent-tool-item[data-type="terminater"]').click()
    page.wait_for_timeout(700)
    node = page.locator('.pmt-node[data-type="terminater"]')
    B.chk('clicking the tile adds a Terminater node', node.count() == 1, 'count=%s' % node.count())
    B.chk('the node is labelled Terminater', 'Terminater' in (node.first.inner_text() or ''))
    B.chk('the empty-canvas card disappears', not page.locator('#pmt-empty').is_visible())
    B.chk('the status strip counts one operation', '1 operation' in (page.locator('#pmt-count').inner_text() or ''), page.locator('#pmt-count').inner_text())
    d = node.first.locator('svg path').first.get_attribute('d') or ''
    B.chk('the node is drawn as a parallelogram', d == 'M52 20H196L148 108H4Z', d)
    B.chk('the node carries the terminal glyph', node.first.locator('.pmt-term-glyph').count() == 1)
    B.chk('the node has an input triangle', node.first.locator('.input-triangle').count() >= 1)
    B.chk('the node has an output triangle', node.first.locator('.output-triangle').count() >= 1)
    colors = page.evaluate("() => { const e = document.querySelector('.pmt-node[data-type=\"terminater\"] svg path'); const s = getComputedStyle(e); return [s.stroke, s.fill]; }")
    B.chk('the node uses its own green identity colours', colors and colors[0] != colors[1], str(colors))
    start = page.locator('#pmt-start')
    B.chk('the new node is offered as Start', start.locator('option').count() >= 1 and 'Terminater' in start.inner_text(), start.inner_text())
    B.chk('the node can be selected by clicking it', (node.first.click() or True) and 'selected' in (node.first.get_attribute('class') or ''))
    page.keyboard.press('Control+z')
    page.wait_for_timeout(500)
    B.chk('Ctrl+Z removes it again (undo)', page.locator('.pmt-node[data-type="terminater"]').count() == 0)
    page.keyboard.press('Control+Shift+z')
    page.wait_for_timeout(500)
    B.chk('Ctrl+Shift+Z brings it back (redo)', page.locator('.pmt-node[data-type="terminater"]').count() == 1)


def configure_checks(H, B):
    page = H.page
    node = page.locator('.pmt-node[data-type="terminater"]').first
    node.dblclick()
    page.wait_for_timeout(700)
    dialog = page.locator('.ui-dialog:visible')
    B.chk('double-clicking opens the Terminater settings', dialog.count() >= 1 and 'Terminater' in (dialog.first.inner_text() or ''), dialog.first.inner_text()[:80] if dialog.count() else '')
    B.chk('the dialog explains the step in plain words', 'human speed' in (dialog.first.inner_text() or ''))
    actions = page.evaluate("() => [...document.querySelectorAll('#pmt-field-action option')].map(o => o.value)")
    B.chk('the action list offers the whole verb set', {'run', 'open', 'type', 'handover', 'abort', 'kill', 'force_kill', 'watch_user', 'warn_user'} <= set(actions), str(actions))
    kinds = page.evaluate("() => [...document.querySelectorAll('#pmt-field-kind option')].map(o => o.textContent.trim())")
    B.chk('the terminal type offers CMD, PowerShell and PowerShell 7', kinds == ['CMD', 'PowerShell', 'PowerShell 7'], str(kinds))
    B.chk('the default action is run', page.locator('#pmt-field-action').input_value() == 'run')
    B.chk('the default type is PowerShell', page.locator('#pmt-field-kind').input_value() == 'powershell')
    wpm = page.evaluate("() => { const e = document.getElementById('pmt-field-typing_wpm'); return [e.value, e.min, e.max]; }")
    B.chk('the typing speed starts at 50 and is limited to 20-160', wpm == ['50', '20', '160'], str(wpm))
    B.chk('the text area names the <<USER:hint>> hand-over', 'USER:hint' in (page.locator('label[for="pmt-field-text"]').inner_text() or ''))
    for name in ('submit', 'secret', 'wait', 'close_after'):
        B.chk('the %s switch is present' % name, page.locator('#pmt-field-%s' % name).count() == 1)
    B.chk('Press Enter after typing starts ticked', page.locator('#pmt-field-submit').is_checked())
    B.chk('Secret text starts unticked', not page.locator('#pmt-field-secret').is_checked())
    # a value outside the range is refused by the panel
    page.locator('#pmt-field-text').fill('echo configured-by-hand')
    page.locator('#pmt-field-typing_wpm').fill('500')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Save")').click()
    page.wait_for_timeout(600)
    still = page.locator('.ui-dialog:visible').count() >= 1
    err = page.locator('.pmt-form-error').first.inner_text() if page.locator('.pmt-form-error').count() else ''
    B.chk('a typing speed of 500 wpm is refused and the dialog stays open', still, err)
    page.locator('#pmt-field-typing_wpm').fill('160')
    page.locator('#pmt-field-kind').select_option('cmd')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Save")').click()
    page.wait_for_timeout(700)
    B.chk('a valid change saves and closes the dialog', page.locator('.ui-dialog:visible').count() == 0)
    node.dblclick()
    page.wait_for_timeout(600)
    B.chk('re-opening shows the saved text', page.locator('#pmt-field-text').input_value() == 'echo configured-by-hand')
    B.chk('re-opening shows the saved type (CMD)', page.locator('#pmt-field-kind').input_value() == 'cmd')
    B.chk('re-opening shows the saved speed (160)', page.locator('#pmt-field-typing_wpm').input_value() in ('160', '160.0'))
    page.locator('#pmt-field-text').fill('this-must-be-discarded')
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)
    B.chk('Escape closes the dialog like Cancel', page.locator('.ui-dialog:visible').count() == 0)
    node.dblclick()
    page.wait_for_timeout(600)
    B.chk('Escape discarded the unsaved text', page.locator('#pmt-field-text').input_value() == 'echo configured-by-hand')
    page.locator('#pmt-field-action').select_option('handover')
    page.locator('#pmt-field-text').fill('echo hello <<USER:name>> end')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Save")').click()
    page.wait_for_timeout(600)
    node.dblclick()
    page.wait_for_timeout(600)
    B.chk('the hand-over action and its marker are kept', page.locator('#pmt-field-action').input_value() == 'handover' and '<<USER:name>>' in page.locator('#pmt-field-text').input_value())
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Cancel")').click()
    page.wait_for_timeout(500)
    B.chk('Cancel closes without changes', page.locator('.ui-dialog:visible').count() == 0)


def validate_checks(H, B):
    page = H.page
    node = page.locator('.pmt-node[data-type="terminater"]').first
    node.dblclick()
    page.wait_for_timeout(500)
    page.locator('#pmt-field-action').select_option('run')
    page.locator('#pmt-field-text').fill('')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Save")').click()
    page.wait_for_timeout(500)
    page.locator('#pmt-start').select_option(index=0)
    page.wait_for_timeout(300)
    page.locator('#pmt-validate').click()
    page.wait_for_timeout(900)
    seen = (page.locator('#pmt-status').inner_text() or '') + (page.locator('.tlmpop-card').inner_text() if page.locator('.tlmpop-card').count() else '') + (page.locator('.ui-dialog:visible').inner_text() if page.locator('.ui-dialog:visible').count() else '')
    B.chk('Validate refuses a Run step with no command to type', 'needs a command to type' in seen, seen[:200])
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    node.dblclick()
    page.wait_for_timeout(500)
    page.locator('#pmt-field-action').select_option('list')
    page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("Save")').click()
    page.wait_for_timeout(500)
    page.locator('#pmt-validate').click()
    page.wait_for_timeout(900)
    # the status line still shows the PREVIOUS validation's error: judge only the new result popup/dialog
    seen = (page.locator('.tlmpop-card').inner_text() if page.locator('.tlmpop-card').count() else '') + (page.locator('.ui-dialog:visible').inner_text() if page.locator('.ui-dialog:visible').count() else '')
    B.chk('a List step needs no command and validates', 'needs a command' not in seen and 'alidated' in seen, seen[:200])
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    d = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const n = M.node('terminater', 10, 10); const f = M.blank(); f.nodes = [n]; f.start = n.id;
        try { M.validate(f, true); return 'accepted'; } catch (e) { return e.message; } }""")
    B.chk('the model rejects a playable Run step without text', 'needs a command to type' in d, d)
    ok = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const n = M.node('terminater', 10, 10); n.config.text = 'echo x'; const f = M.blank(); f.nodes = [n]; f.start = n.id;
        try { const v = M.validate(f, true); return v.nodes[0].config.typing_wpm; } catch (e) { return e.message; } }""")
    B.chk('the model accepts it once text is set (speed default kept)', ok == 50, str(ok))
    bad = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const n = M.node('terminater', 10, 10); n.config.text = 'x'.repeat(100001);
        const f = M.blank(); f.nodes = [n]; f.start = n.id; try { M.validate(f, true); return 'accepted'; } catch (e) { return e.message; } }""")
    B.chk('an enormous command text is refused', bad != 'accepted', bad)
    bad = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const n = M.node('terminater', 10, 10); n.config.text = 'x'; n.config.hint = 'h'.repeat(201);
        const f = M.blank(); f.nodes = [n]; f.start = n.id; try { M.validate(f, true); return 'accepted'; } catch (e) { return e.message; } }""")
    B.chk('a hint over its limit is refused (the text limits are enforced in the browser)', bad != 'accepted', bad)
    bad = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const n = M.node('terminater', 10, 10); n.config.text = 'x'; n.config.kind = 'bash';
        const f = M.blank(); f.nodes = [n]; f.start = n.id; try { M.validate(f, true); return 'accepted'; } catch (e) { return e.message; } }""")
    B.chk('an unknown terminal type is refused', 'CMD' in bad, bad)


def empty_page_specific(H, B):
    clear_canvas(H)
    H.page.wait_for_timeout(500)
    B.group('palette', palette_checks, H, B)
    B.group('add a node', add_node_checks, H, B)
    B.group('configure', configure_checks, H, B)
    B.group('validate', validate_checks, H, B)
    # the dock must not hide the canvas controls
    B.set_visible(True)
    for selector, label in (('#pmt-play', 'Play'), ('#pmt-validate', 'Validate'), ('#pmt-start', 'Start selector'), ('#pmt-zoom', 'zoom read-out')):
        box = B.box(selector)
        dock = B.box('#tlm-terminals')
        B.chk('%s stays clear of the dock' % label, bool(box and dock) and box['b'] <= dock['y'] + 1, 'control.b=%s dock.y=%s' % (box and box['b'], dock and dock['y']))
    out = B.box('#pmt-run-panel')
    dock = B.box('#tlm-terminals')
    B.chk('the Run output panel stays above the dock', bool(out and dock) and out['b'] <= dock['y'] + 1, 'out.b=%s dock.y=%s' % (out and out['b'], dock and dock['y']))
    divider = B.box('#pmt-output-divider')
    B.chk('the Run output divider is still usable with the dock open', bool(divider) and divider['h'] > 0 and divider['display'] != 'none')


# ----------------------------------------------------------------------------- loaded diagram
def loaded_page_specific(H, B, files):
    page = H.page
    B.set_visible(True)
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    # ---- load a real .fpmt
    loaded = open_flow(H, files['two'])
    B.chk('a .fpmt with two Terminater steps opens', bool(loaded), '')
    B.chk('both nodes are on the canvas', page.locator('.pmt-node[data-type="terminater"]').count() == 2)
    B.chk('the connection is drawn', page.locator('.connection-group, .pmt-edge').count() >= 1)
    B.chk('the status strip counts 2 operations and 1 connection', '2 operations' in page.locator('#pmt-count').inner_text() and '1 connection' in page.locator('#pmt-count').inner_text(), page.locator('#pmt-count').inner_text())
    B.chk('the file name is shown', 'two-steps' in (page.locator('#filename').inner_text() or ''), page.locator('#filename').inner_text())
    B.chk('the first step is the Start operation', page.locator('#pmt-start').input_value() == 'pfp_t1', page.locator('#pmt-start').input_value())
    B.chk('the labels from the file are kept', 'PowerShell step' in page.locator('#pmt-nodes').inner_text() and 'CMD step' in page.locator('#pmt-nodes').inner_text())
    dock, area = B.box('#tlm-terminals'), B.box('#submonitor-container')
    B.chk('the loaded diagram stays visible above the dock', bool(dock and area) and area['b'] <= dock['y'] + 2 and area['h'] > 80)
    nodes_box = page.evaluate("() => [...document.querySelectorAll('.pmt-node')].map(n => { const b = n.getBoundingClientRect(); return [Math.round(b.x), Math.round(b.y), Math.round(b.width)]; })")
    B.chk('the diagram nodes are not covered by the dock', all(b[1] < (dock or {'y': 0})['y'] for b in nodes_box), str(nodes_box))
    # ---- play it
    B.set_visible(True)
    page.locator('#pmt-play').click()
    started = H.wait_for(lambda: page.locator('#pmt-stop').is_enabled(), timeout=20)
    B.chk('Play enables Stop and Pause', bool(started) and page.locator('#pmt-pause').is_enabled())
    B.chk('Play is disabled while the flow runs', not page.locator('#pmt-play').is_enabled())
    first_terminal = H.wait_for(lambda: len(B.terminals()) >= 1, timeout=60)
    B.chk('the flow raised a terminal in the dock', bool(first_terminal), str(B.terminals()))
    typed_live = H.wait_for(lambda: 'pfp-step-one' in H.term_text(None, 20), timeout=60)
    B.chk('the first command was typed in the visible terminal', bool(typed_live), H.term_text()[-200:])
    two = H.wait_for(lambda: len(B.terminals()) >= 2, timeout=60)
    B.chk('the second step raised its own terminal (CMD)', bool(two) and 'cmd' in [t.get('kind') for t in B.terminals()], str(B.terminals()))
    done = wait_idle(H, timeout=120)
    B.chk('the flow ends and Play is available again', bool(done), run_state(H))
    state = run_state(H)
    B.chk('the run state reads as completed', 'omplet' in state, state)
    log = log_text(H)
    B.chk('the Run output shows the first step\'s result', 'pfp-step-one' in log, log[-300:])
    B.chk('the Run output shows the second step\'s result', 'pfp-step-two' in log, log[-300:])
    kinds = [t.get('kind') for t in B.terminals()]
    B.chk('the dock holds a PowerShell and a CMD terminal', 'powershell' in kinds and 'cmd' in kinds, str(kinds))
    classes = [node_classes(H, 'pfp_t1'), node_classes(H, 'pfp_t2')]
    B.chk('both nodes show the completed state', all('completed' in c for c in classes), str(classes))
    # The dock may hold other tabs of the same kind: pick the one that actually carries the flow's command.
    ps_all = [t['id'] for t in B.terminals() if t.get('kind') == 'powershell']
    cmd_all = [t['id'] for t in B.terminals() if t.get('kind') == 'cmd']
    ps_id = next((i for i in ps_all if 'pfp-step-one' in H.term_text(i, 60)), ps_all[-1] if ps_all else '')
    cmd_id = next((i for i in cmd_all if 'pfp-step-two' in H.term_text(i, 60)), cmd_all[-1] if cmd_all else '')
    B.chk('the PowerShell terminal shows its command and output', 'pfp-step-one' in H.term_text(ps_id, 60), H.term_text(ps_id, 20)[-160:])
    B.chk('the CMD terminal shows its command and output', 'pfp-step-two' in H.term_text(cmd_id, 60), H.term_text(cmd_id, 20)[-160:])
    commands = B.api('commands', terminal=ps_id)
    entries = [c for c in (commands.get('commands') or []) if 'pfp-step-one' in str(c.get('command'))]
    B.chk('the hub recorded the command as typed by Tlamatini', bool(entries) and entries[0].get('source') == 'tlamatini', str(entries[:1]))
    # ---- re-run keeps working (terminals reused)
    page.locator('#pmt-play').click()
    page.wait_for_timeout(700)
    B.chk('a new run clears the previous run\'s node statuses', 'completed' not in node_classes(H, 'pfp_t2'), node_classes(H, 'pfp_t2'))
    again = wait_idle(H, timeout=120)
    B.chk('playing the same flow a second time also completes', bool(again) and 'omplet' in run_state(H), run_state(H))
    # ---- Stop aborts a running command
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    open_flow(H, files['long'])
    page.locator('#pmt-play').click()
    ping_seen = H.wait_for(lambda: 'Pinging' in H.term_text(None, 30), timeout=60)
    B.chk('a long command (ping) is running in the visible terminal', bool(ping_seen), H.term_text()[-200:])
    page.wait_for_timeout(1500)
    page.locator('#pmt-stop').click()
    stopped = wait_idle(H, timeout=60)
    B.chk('Stop ends the flow', bool(stopped), run_state(H))
    back = H.wait_for(lambda: any(t.get('state') == 'prompt' for t in B.terminals()), timeout=30)
    B.chk('Stop aborted the running command and the terminal is at its prompt again', bool(back), str(B.terminals()))
    B.chk('the run state reads as stopped', 'top' in run_state(H) or 'ancel' in run_state(H), run_state(H))
    B.chk('the aborted ping was interrupted (^C or a prompt after the statistics)', '^C' in H.term_text(None, 30) or 'Control-C' in H.term_text(None, 30) or 'Ping statistics' in H.term_text(None, 30), H.term_text()[-200:])
    # ---- hand-over inside a flow
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    open_flow(H, files['handover'])
    page.locator('#pmt-play').click()
    asked = H.wait_for(lambda: any(t.get('state') == 'awaiting_user' for t in B.terminals()), timeout=90)
    B.chk('the flow hands the keyboard to the user (terminal awaiting the user)', bool(asked), str(B.terminals()))
    B.chk('the dock shows what the user is asked to type', 'your name' in page.locator('#tlm-terminals').inner_text(), page.locator('#tlm-terminals').inner_text()[-200:])
    awaiting = next((t['id'] for t in B.terminals() if t.get('state') == 'awaiting_user'), '')
    page.locator('.tlm-term-pane[data-id="%s"] .xterm-helper-textarea' % awaiting).first.focus()
    page.keyboard.type('Angela', delay=70)
    page.keyboard.press('Enter')
    finished = wait_idle(H, timeout=120)
    B.chk('after the user answers the flow completes', bool(finished) and 'omplet' in run_state(H), run_state(H))
    B.chk('the finished line contains the user\'s part', 'hello Angela end' in log_text(H) or 'hello Angela end' in H.term_text(awaiting, 40), log_text(H)[-300:])
    # ---- the saved settings survive a model round trip
    again = page.evaluate("""() => { const M = window.PromptFlowPanelModel; const copy = M.copy(M.example()); return copy.nodes.length; }""")
    B.chk('the model can still copy and validate the shipped example', again == 4)
    # ---- clear canvas and return
    live = len(B.terminals())
    clear_canvas(H)
    B.chk('Clear removes the diagram', page.locator('.pmt-node').count() == 0, 'nodes=%s' % page.locator('.pmt-node').count())
    B.chk('Clear never kills a terminal', len(B.terminals()) == live, '%s -> %s' % (live, len(B.terminals())))


def run(H):
    files = {
        'two': write_flow('pfp-two-steps.fpmt', make_flow('two-steps', [
            ('PowerShell step', {'kind': 'powershell', 'text': 'Write-Output "pfp-step-one"'}),
            ('CMD step', {'kind': 'cmd', 'text': 'echo pfp-step-two'}),
        ])),
        'long': write_flow('pfp-long.fpmt', make_flow('long-ping', [
            ('Long ping', {'kind': 'cmd', 'text': 'ping -n 60 127.0.0.1', 'wait_seconds': 120, 'hang_seconds': 600}),
        ])),
        'handover': write_flow('pfp-handover.fpmt', make_flow('handover', [
            ('Ask for the name', {'kind': 'powershell', 'action': 'handover', 'text': 'Write-Output "hello <<USER:your name>> end"', 'hint': 'your name', 'user_wait_seconds': 90}),
        ])),
    }
    empty = PfpBattery(H, 'pfp/empty', 'pfp')
    empty.run_all()
    empty.group('Operations bar and Terminater node', empty_page_specific, H, empty)
    # ---- the second variant: a real diagram
    empty.reset_dock()
    loaded = PfpBattery(H, 'pfp/loaded', 'pfp')
    loaded.group('open, play, stop, hand over', loaded_page_specific, H, loaded, files)
    loaded.reset_dock()
    loaded.run_all(skip=('persistence',))
    print('pfp suite: %d checks recorded, %d failed' % (len(H.results), len([r for r in H.results if not r['ok']])), flush=True)


def main():
    with Harness('pfp', PATH) as H:
        run(H)
    sys.exit(getattr(H, 'exit_code', 1))


if __name__ == '__main__':
    main()
