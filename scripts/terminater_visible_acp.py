# Tlamatini Author Banner — Angela López Mendoza
"""VISIBLE suite: the Terminals area AND the Terminater agent on the Agentic Control Panel.

Two variants, one run:
  * ``acp/empty``   -- an empty canvas (the "Try an example" card is showing);
  * ``acp/loaded``  -- a real .flw (Starter -> Terminater -> Ender) is loaded, validated and STARTED:
                       the Terminater pool agent types its command in the dock like a person.

Run from a foreground PowerShell -NoExit console:  python scripts/terminater_visible_acp.py
Every check takes a full-desktop Shoter photograph; the console gate and the browser gate wait
for the operator to look at the photograph and create ``Temp/terminater-visible/<gate>.confirmed``.
"""
from __future__ import annotations

import glob
import sys

from terminater_visible_battery import Battery
from terminater_visible_common import RUNTIME, Harness

PATH = '/agent/agentic_control_panel/'
TILE = '#agents-list .agent-tool-item[data-content="Terminater"]'
ITEM = '#canvas-content .canvas-item.terminater-agent'


def flow(name_text, extra=None):
    cfg = {
        'action': 'run', 'kind': 'powershell', 'text': name_text, 'typing_wpm': 160, 'wait': True,
        'wait_seconds': 90, 'hang_seconds': 45, 'load_profile': False, 'mode': 'auto',
    }
    cfg.update(extra or {})
    return {
        'schemaVersion': 2,
        'nodes': [
            {'id': 'starter-1', 'text': 'Starter', 'left': '60px', 'top': '60px', 'agentPurpose': 'Entry point, launches first agents'},
            {'id': 'terminater-1', 'text': 'Terminater', 'left': '300px', 'top': '60px', 'agentPurpose': '', 'configData': cfg},
            {'id': 'ender-1', 'text': 'Ender', 'left': '540px', 'top': '60px', 'agentPurpose': 'Terminates all agents'},
        ],
        'connections': [
            {'sourceIndex': 0, 'targetIndex': 1, 'sourceId': 'starter-1', 'targetId': 'terminater-1', 'inputSlot': 0, 'outputSlot': 0},
            {'sourceIndex': 1, 'targetIndex': 2, 'sourceId': 'terminater-1', 'targetId': 'ender-1', 'inputSlot': 0, 'outputSlot': 0},
        ],
        'artifacts': {},
    }


def dialogs(H):
    return H.page.locator('.ui-dialog:visible')


def press_in_dialog(H, label):
    button = H.page.locator('.ui-dialog:visible .ui-dialog-buttonpane button:has-text("%s")' % label)
    if button.count():
        button.first.click()
        H.page.wait_for_timeout(600)
        return True
    return False


def close_dialogs(H, rounds=6):
    for _ in range(rounds):
        if not dialogs(H).count():
            return
        H.page.keyboard.press('Escape')
        H.page.wait_for_timeout(450)


def clear_canvas(H):
    """Clear is disabled on an empty canvas; when it is enabled it asks before it clears."""
    if not H.page.locator('#btn-clear').is_enabled():
        return False
    H.page.locator('#btn-clear').click()
    H.page.wait_for_timeout(500)
    press_in_dialog(H, 'Yes') or press_in_dialog(H, 'Continue') or press_in_dialog(H, 'OK')
    close_dialogs(H)
    return True


def load_flow(H, data, filename='terminater-test.flw'):
    """Open a flow exactly like the Open button does.  When the canvas holds unsaved changes the
    page asks "Replace this diagram?" first, so the question is answered the way a person would."""
    H.page.evaluate("""([data, name]) => { window.__tlmLoad = 'pending';
        loadDiagram(data, name).then(r => { window.__tlmLoad = r === false ? 'declined' : 'loaded'; }).catch(e => { window.__tlmLoad = 'error: ' + e.message; }); }""", [data, filename])
    deadline = 60
    result = 'pending'
    while deadline > 0 and result == 'pending':
        H.page.wait_for_timeout(500)
        deadline -= 0.5
        if dialogs(H).count() and 'Replace' in (dialogs(H).first.inner_text() or ''):
            (press_in_dialog(H, 'Continue') or press_in_dialog(H, 'Yes') or press_in_dialog(H, 'Replace') or press_in_dialog(H, 'OK'))
        result = H.page.evaluate("() => window.__tlmLoad")
    H.page.wait_for_timeout(1400)
    return result


def canvas_state(H):
    return H.page.evaluate("""() => ({
        items: [...document.querySelectorAll('#canvas-content .canvas-item')].map(e => ({id: e.id, name: e.dataset.agentName, cls: e.className, text: e.textContent.trim()})),
        connections: (window.ACP && ACP.connections) ? ACP.connections.length : -1,
        zoom: window.ACP ? ACP.zoom : null })""")


def pool_log(name):
    paths = glob.glob(str(RUNTIME / ('Tlamatini/agent/agents/pools/*/%s/%s.log' % (name, name))))
    if not paths:
        return ''
    try:
        return open(paths[0], encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


def agent_config(page, agent_id):
    """What the ACP page itself reads back.  The pool belongs to the session named in the
    X-Agent-Session-ID header the pages send (getHeaders()); a bare fetch would read the 'default' pool."""
    return page.evaluate("""async (id) => { const r = await fetch('/agent/load_agent_config/' + id + '/', {headers: getHeaders(), credentials: 'same-origin', cache: 'no-store'}); return r.ok ? r.json() : null; }""", agent_id)


def pool_config(name):
    """The config.yaml the pool agent will really read (straight from disk)."""
    import yaml
    paths = glob.glob(str(RUNTIME / ('Tlamatini/agent/agents/pools/*/%s/config.yaml' % name)))
    if not paths:
        return {}
    try:
        with open(paths[0], encoding='utf-8') as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, ValueError):
        return {}


class AcpBattery(Battery):
    pass


# ----------------------------------------------------------------------------- empty canvas
def sidebar_checks(H, B):
    page = H.page
    H.wait_for(lambda: page.locator(TILE).count() == 1, timeout=60)
    tile = page.locator(TILE)
    B.chk('the sidebar lists Terminater', tile.count() == 1, 'count=%s' % tile.count())
    names = page.evaluate("() => [...document.querySelectorAll('#agents-list .agent-tool-item')].map(e => e.dataset.content)")
    B.chk('its display name has the exact intended casing', 'Terminater' in names and 'Terminator' not in names and 'TerminaterAgent' not in names, str([n for n in names if 'ermin' in n.lower()]))
    B.chk('the catalog now holds 85 or more agents', len(names) >= 85, 'agents=%s' % len(names))
    purpose = tile.get_attribute('data-agent-purpose') or ''
    B.chk('the tile carries a purpose text for its tooltip', len(purpose) > 20, purpose)
    B.chk('the purpose mentions the visible terminals', 'terminal' in purpose.lower(), purpose)
    icon = page.evaluate("() => { const i = document.querySelector('#agents-list .agent-tool-item[data-content=\"Terminater\"] .agent-tool-icon'); return i ? getComputedStyle(i).backgroundImage : ''; }")
    B.chk('its icon shows the Terminater gradient (inherited from the canvas CSS)', 'gradient' in icon, icon[:120])
    others = page.evaluate("() => { const f = n => { const i = document.querySelector('#agents-list .agent-tool-item[data-content=\"' + n + '\"] .agent-tool-icon'); return i ? getComputedStyle(i).backgroundImage : ''; }; return [f('Terminater'), f('Shoter'), f('Executer')]; }")
    B.chk('that gradient is different from its neighbours\'', others[0] != others[1] and others[0] != others[2], str([o[:50] for o in others]))
    B.chk('the tile is draggable', tile.get_attribute('draggable') == 'true')
    search = page.locator('#acp-agent-search')
    search.fill('termin')
    page.wait_for_timeout(500)
    visible = page.evaluate("() => [...document.querySelectorAll('#agents-list .agent-tool-item:not([hidden])')].map(e => e.dataset.content)")
    B.chk('searching "termin" finds Terminater', 'Terminater' in visible, str(visible))
    search.fill('zzzz-nothing')
    page.wait_for_timeout(400)
    B.chk('a search with no match shows the empty message', page.locator('#acp-agent-search-empty').is_visible())
    search.fill('')
    page.wait_for_timeout(400)
    B.chk('clearing the search shows the whole catalog again', page.locator('#agents-list .agent-tool-item:not([hidden])').count() >= 85)
    tile.hover()
    page.wait_for_timeout(900)
    tip = page.evaluate("() => { const t = [...document.querySelectorAll('[class*=\"tooltip\"], [role=\"tooltip\"]')].find(e => e.offsetParent !== null && /terminal/i.test(e.textContent)); return t ? t.textContent.trim().slice(0, 120) : ''; }")
    B.chk('hovering the tile shows its purpose tooltip', bool(tip), tip)
    page.mouse.move(5, 5)


def drop_checks(H, B):
    page = H.page
    tile = page.locator(TILE)
    # the canvas content layer grows by itself, so Playwright never sees it "stable": drop onto the
    # viewport that holds it (the drop lands on the layer under the pointer all the same)
    tile.drag_to(page.locator('#submonitor-container'), target_position={'x': 260, 'y': 140}, force=True)
    page.wait_for_timeout(1500)
    B.chk('dropping the tile opens no dialog (the template is deployed silently)', dialogs(H).count() == 0, dialogs(H).first.inner_text()[:120] if dialogs(H).count() else '')
    items = page.locator(ITEM)
    B.chk('dropping the tile creates a Terminater on the canvas', items.count() == 1, 'count=%s' % items.count())
    B.chk('the item is named Terminater (1)', 'Terminater (1)' in (items.first.inner_text() or ''), items.first.inner_text())
    B.chk('its identity is terminater-1', items.first.get_attribute('id') == 'terminater-1', items.first.get_attribute('id'))
    B.chk('its agent name keeps the exact casing', items.first.get_attribute('data-agent-name') == 'Terminater', items.first.get_attribute('data-agent-name'))
    B.chk('it has an input triangle', items.first.locator('.input-triangle').count() >= 1)
    B.chk('it has an output triangle', items.first.locator('.output-triangle').count() >= 1)
    B.chk('it carries the LED status indicator (idle)', items.first.locator('.canvas-item-led.led-idle').count() == 1)
    bg = page.evaluate("() => getComputedStyle(document.querySelector('%s')).backgroundImage" % ITEM)
    B.chk('it is painted with the Terminater gradient', 'gradient' in bg, bg[:100])
    B.chk('the empty-canvas card is gone', not page.locator('#acp-empty').is_visible())
    cfg = H.wait_for(lambda: agent_config(page, 'terminater-1'), timeout=20)
    B.chk('its configuration was deployed from the template', bool(cfg) and cfg.get('action') == 'run' and cfg.get('typing_wpm') == 50, str(cfg)[:200])
    B.chk('the deployed template has no connections yet', bool(cfg) and cfg.get('target_agents') == [] and cfg.get('source_agents') == [], str(cfg)[-120:])
    B.chk('the deployed template keeps hub mode on auto', bool(cfg) and cfg.get('mode') == 'auto', str(cfg)[:120])
    pos = items.first.bounding_box()
    page.mouse.move(pos['x'] + 20, pos['y'] + 20)
    page.mouse.down()
    page.mouse.move(pos['x'] + 140, pos['y'] + 50, steps=8)
    page.mouse.up()
    page.wait_for_timeout(600)
    moved = items.first.bounding_box()
    B.chk('the item can be dragged around', moved and abs(moved['x'] - pos['x']) > 40, '%s -> %s' % (pos['x'], moved and moved['x']))
    items.first.click()
    page.wait_for_timeout(300)
    B.chk('clicking selects it', 'selected' in (items.first.get_attribute('class') or ''))


def configure_checks(H, B):
    page = H.page
    page.locator(ITEM).first.dblclick()
    page.wait_for_timeout(1200)
    dialog = page.locator('#canvas-item-dialog-message')
    B.chk('double-clicking opens the settings dialog', dialog.is_visible() and dialogs(H).count() >= 1)
    keys = page.evaluate("() => [...document.querySelectorAll('#canvas-item-dialog-message [data-key]')].map(e => e.dataset.key)")
    wanted = {'action', 'kind', 'text', 'typing_wpm', 'wait_seconds', 'hang_seconds', 'user_wait_seconds', 'submit', 'secret', 'advisor', 'mode', 'terminal', 'cwd'}
    B.chk('the dialog offers every Terminater setting', wanted <= set(keys), 'missing=%s' % sorted(wanted - set(keys)))
    shown = page.locator('#canvas-item-dialog-message [data-key="typing_wpm"]').input_value()
    B.chk('the typing speed starts at 50', shown in ('50', '50.0'), shown)
    page.locator('#canvas-item-dialog-message [data-key="text"]').fill('echo configured-on-the-acp')
    page.locator('#canvas-item-dialog-message [data-key="kind"]').fill('cmd')
    page.locator('#canvas-item-dialog-message [data-key="typing_wpm"]').fill('160')
    saved = press_in_dialog(H, 'Save')
    deployed = H.wait_for(lambda: dialogs(H).count() >= 1 and 'Deployment' in dialogs(H).first.inner_text(), timeout=20)
    shown = dialogs(H).first.inner_text() if dialogs(H).count() else ''
    B.chk('Save deploys the configuration and says so', bool(saved and deployed) and 'terminater-1' in shown and 'Successful' in shown, shown[:200])
    B.chk('the deployment report names the pool folder terminater_1', 'terminater_1' in shown, shown[:300])
    press_in_dialog(H, 'OK')
    close_dialogs(H)
    B.chk('answering the report leaves no dialog open', not dialogs(H).count(), '')
    cfg = agent_config(page, 'terminater-1') or {}
    B.chk('the saved text reached the pool configuration', cfg.get('text') == 'echo configured-on-the-acp', str(cfg)[:200])
    B.chk('the saved terminal type reached the pool configuration', cfg.get('kind') == 'cmd', cfg.get('kind'))
    B.chk('the saved speed is a number', cfg.get('typing_wpm') == 160, repr(cfg.get('typing_wpm')))
    B.chk('the unsaved-changes marker shows in the page title', (page.title() or '').lstrip().startswith('•') or '•' in (page.title() or ''), page.title())
    page.locator(ITEM).first.dblclick()
    page.wait_for_timeout(900)
    B.chk('re-opening shows the saved text', page.locator('#canvas-item-dialog-message [data-key="text"]').input_value() == 'echo configured-on-the-acp')
    page.locator('#canvas-item-dialog-message [data-key="text"]').fill('discard me')
    page.keyboard.press('Escape')
    page.wait_for_timeout(600)
    B.chk('Escape closes the dialog without saving', not dialogs(H).count())
    cfg = agent_config(page, 'terminater-1') or {}
    B.chk('the discarded text never reached the configuration', cfg.get('text') == 'echo configured-on-the-acp', cfg.get('text'))
    page.locator(ITEM).first.click()
    page.locator('#acp-configure, [data-acp-tool="configure"], button:has-text("Configure")').first.click()
    page.wait_for_timeout(900)
    B.chk('the toolbar Configure opens the same dialog', dialogs(H).count() >= 1 and page.locator('#canvas-item-dialog-message').is_visible())
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)


def editor_checks(H, B):
    page = H.page
    page.locator(ITEM).first.click()
    page.locator('button:has-text("Duplicate")').first.click()
    page.wait_for_timeout(2200)
    close_dialogs(H)   # an agent that is (re)deployed reports it in a dialog
    B.chk('Duplicate makes a second Terminater', page.locator(ITEM).count() == 2, 'count=%s' % page.locator(ITEM).count())
    ids = page.evaluate("() => [...document.querySelectorAll('%s')].map(e => e.id)" % ITEM)
    new = [i for i in ids if i != 'terminater-1']
    cfg = agent_config(page, new[0]) if new else None
    B.chk('the copy keeps the original\'s settings', bool(cfg) and cfg.get('text') == 'echo configured-on-the-acp' and cfg.get('kind') == 'cmd', str(cfg)[:160])
    page.keyboard.press('Control+z')
    page.wait_for_timeout(1500)
    B.chk('Ctrl+Z undoes the duplicate', page.locator(ITEM).count() == 1, 'count=%s' % page.locator(ITEM).count())
    page.keyboard.press('Control+y')
    page.wait_for_timeout(2200)
    close_dialogs(H)   # an agent that is (re)deployed reports it in a dialog
    B.chk('Ctrl+Y redoes it', page.locator(ITEM).count() == 2, 'count=%s' % page.locator(ITEM).count())
    victim = page.locator(ITEM).nth(1)
    victim_id = victim.get_attribute('id')
    victim.click()
    page.keyboard.press('Delete')
    page.wait_for_timeout(1200)
    B.chk('Delete removes the selected Terminater', page.locator(ITEM).count() == 1, 'count=%s' % page.locator(ITEM).count())
    page.keyboard.press('Control+z')
    page.wait_for_timeout(2200)
    close_dialogs(H)   # an agent that is (re)deployed reports it in a dialog
    B.chk('Undo brings the deleted Terminater back', page.locator(ITEM).count() == 2, 'count=%s' % page.locator(ITEM).count())
    cfg = agent_config(page, victim_id)
    B.chk('the restored item has its settings back, not the template\'s', bool(cfg) and cfg.get('text') == 'echo configured-on-the-acp', str(cfg)[:160])
    B.set_visible(True)
    zoom_before = canvas_state(H)['zoom']
    page.locator('button[aria-label="Zoom out"], button:has-text("−")').first.click()
    page.wait_for_timeout(500)
    B.chk('zooming out works while the dock is open', canvas_state(H)['zoom'] < zoom_before, '%s -> %s' % (zoom_before, canvas_state(H)['zoom']))
    page.locator('button:has-text("Fit")').first.click()
    page.wait_for_timeout(700)
    dock = B.box('#tlm-terminals')
    items = page.evaluate("() => [...document.querySelectorAll('#canvas-content .canvas-item')].map(e => e.getBoundingClientRect().bottom)")
    B.chk('Fit keeps the agents above the dock', all(b <= (dock or {'y': 9999})['y'] + 2 for b in items), 'bottoms=%s dock.y=%s' % (items, dock and dock['y']))
    page.locator('button:has-text("Fit")').first.click()
    B.chk('the editor toolbar stays clear of the dock', (B.box('#acp-editor-toolbar') or {'b': 9999})['b'] <= (dock or {'y': 0})['y'])
    for selector, label in (('#btn-start', 'Start'), ('#btn-validate', 'Validate'), ('#btn-clear', 'Clear')):
        box = B.box(selector)
        B.chk('%s stays clear of the dock' % label, bool(box and dock) and box['b'] <= dock['y'] + 1)
    page.keyboard.press('Control+z')
    page.wait_for_timeout(300)


def empty_page_specific(H, B):
    page = H.page
    clear_canvas(H)
    B.group('sidebar', sidebar_checks, H, B)
    B.chk('the canvas is empty before the test starts', len(canvas_state(H)['items']) == 0, str(canvas_state(H)))
    B.chk('the "Try an example" card is showing', page.locator('#acp-empty').is_visible())
    B.group('drop onto the canvas', drop_checks, H, B)
    B.group('configure', configure_checks, H, B)
    B.group('editor tools', editor_checks, H, B)


# ----------------------------------------------------------------------------- loaded flow
def loaded_page_specific(H, B):
    page = H.page
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    result = load_flow(H, flow('Write-Output "acp-flow-typed-this"'))
    B.chk('a real .flw (Starter, Terminater, Ender) loads', result == 'loaded', result)
    state = canvas_state(H)
    names = [i['name'] for i in state['items']]
    B.chk('the three agents are on the canvas', names == ['Starter', 'Terminater', 'Ender'], str(names))
    B.chk('both connections were restored', state['connections'] == 2, str(state['connections']))
    B.chk('the Terminater keeps the exact casing after loading', any(i['text'].startswith('Terminater (') for i in state['items']), str([i['text'] for i in state['items']]))
    served = agent_config(page, 'terminater-1') or {}
    starter = agent_config(page, 'starter-1') or {}
    disk = pool_config('terminater_1')
    client = page.evaluate("() => { const c = ACP.nodeConfigs.get('terminater-1'); return c ? {text: c.text, typing_wpm: c.typing_wpm} : null; }")
    why = 'served=%s | disk=%s | client=%s' % (str(served)[:160], str(disk)[:160], client)
    B.chk('its saved configuration is held by the canvas', bool(client) and client.get('text') == 'Write-Output "acp-flow-typed-this"' and client.get('typing_wpm') == 160, why)
    B.chk('its saved configuration was deployed to the pool', served.get('text') == 'Write-Output "acp-flow-typed-this"' and served.get('typing_wpm') == 160, why)
    B.chk('the Starter now points at the Terminater', 'terminater_1' in (starter.get('target_agents') or []), str(starter))
    ender = agent_config(page, 'ender-1') or {}
    B.chk('the Ender records the Terminater as its source (a wire into an Ender is drawn, not launched)', 'terminater_1' in (ender.get('source_agents') or []), str(ender))
    B.set_visible(True)
    dock = B.box('#tlm-terminals')
    nodes = page.evaluate("() => [...document.querySelectorAll('#canvas-content .canvas-item')].map(e => e.getBoundingClientRect().bottom)")
    B.chk('the loaded agents are not covered by the dock', all(b <= dock['y'] + 2 for b in nodes), 'bottoms=%s dock.y=%s' % (nodes, dock['y']))
    # ---- validate
    page.locator('#btn-validate').click()
    H.wait_for(lambda: dialogs(H).count() >= 1, timeout=60)
    shown = dialogs(H).first.inner_text() if dialogs(H).count() else ''
    B.chk('Validate shows its report', bool(shown), shown[:160])
    B.chk('the report does not flag the Terminater as unknown', 'unknown agent' not in shown.lower() and 'terminater' not in shown.lower().split('error')[-1], shown[:300])
    close_dialogs(H)
    # ---- start: the pool agent types in the dock
    page.locator('#btn-start').click()
    page.wait_for_timeout(900)
    press_in_dialog(H, 'Run')
    started = H.wait_for(lambda: page.locator('#btn-stop').is_enabled(), timeout=60)
    B.chk('Start enables Stop (the flow is running)', bool(started))
    raised = H.wait_for(lambda: len(B.terminals()) >= 1, timeout=90)
    B.chk('the Terminater agent raised a terminal in the dock', bool(raised), str(B.terminals()))
    typed = H.wait_for(lambda: 'acp-flow-typed-this' in H.term_text(None, 30), timeout=90)
    B.chk('its command was typed in the visible terminal', bool(typed), H.term_text()[-200:])
    state_seen = H.wait_for(lambda: page.locator('%s .canvas-item-led:not(.led-idle)' % ITEM).count() == 1, timeout=60)
    B.chk('the Terminater LED left the idle state while the flow ran', bool(state_seen))
    log = H.wait_for(lambda: 'INI_SECTION_TERMINATER' in pool_log('terminater_1'), timeout=120)
    B.chk('the pool agent wrote its INI_SECTION_TERMINATER report', bool(log), pool_log('terminater_1')[-300:])
    text = pool_log('terminater_1')
    B.chk('the report says the command completed', 'status: completed' in text, text[-300:])
    B.chk('the report quotes the typed command', 'acp-flow-typed-this' in text, text[-300:])
    B.chk('the report carries the terminal id and kind', 'terminal_id:' in text and 'kind: powershell' in text, text[-300:])
    ender = H.wait_for(lambda: pool_log('ender_1') != '', timeout=120)
    B.chk('the Ender agent ran after the Terminater (the chain continued)', bool(ender), pool_log('ender_1')[-200:])
    ps = [t for t in B.terminals() if t.get('kind') == 'powershell']
    B.chk('the terminal the flow used is a PowerShell tab in the dock', bool(ps), str(B.terminals()))
    if ps:
        # The dock may hold other PowerShell tabs (the one it auto-opened); pick the one the flow typed into.
        used = next((t for t in ps if 'acp-flow-typed-this' in H.term_text(t['id'], 60)), None)
        B.chk('the dock shows the command AND its output', used is not None, ' | '.join(H.term_text(t['id'], 8)[-80:] for t in ps))
        picked = used or ps[-1]
        commands = B.api('commands', terminal=picked['id']).get('commands') or []
        flow_cmds = [c for c in commands if 'acp-flow-typed-this' in str(c.get('command'))]
        B.chk('the hub recorded it as typed by Tlamatini', bool(flow_cmds) and flow_cmds[0].get('source') == 'tlamatini', str(commands[:2]))
    page.wait_for_timeout(4000)
    close_dialogs(H)
    stopped = H.wait_for(lambda: page.locator('#btn-start').is_enabled() or not page.locator('#btn-stop').is_enabled(), timeout=120)
    B.chk('after the chain ends the controls return to idle', bool(stopped))
    # ---- hand-over inside a flow, then Stop mid-command
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    close_dialogs(H)
    clear_canvas(H)
    result = load_flow(H, flow('Write-Output "hello <<USER:your name>> end"', {'action': 'handover', 'hint': 'your name', 'user_wait_seconds': 90}), 'terminater-handover.flw')
    B.chk('a hand-over flow loads', result == 'loaded', result)
    page.locator('#btn-start').click()
    page.wait_for_timeout(900)
    press_in_dialog(H, 'Run')
    asked = H.wait_for(lambda: any(t.get('state') == 'awaiting_user' for t in B.terminals()), timeout=120)
    B.chk('the flow hands the keyboard to the user', bool(asked), str(B.terminals()))
    awaiting = next((t['id'] for t in B.terminals() if t.get('state') == 'awaiting_user'), '')
    # The panel's own "Startup Complete" dialog is modal (overlay + focus trap). The hand-over must step it
    # aside BY ITSELF - nothing is clicked or focused here, exactly as for a user who just starts typing.
    dialog_gone = H.wait_for(lambda: page.evaluate("""() => { const d = document.getElementById('starter-execution-dialog');
        const w = d && d.closest('.ui-dialog'); return !w || getComputedStyle(w).display === 'none'; }"""), timeout=20)
    B.chk('the hand-over dismisses the modal Startup dialog by itself', bool(dialog_gone))
    B.chk('no modal overlay or scroll lock is left behind',
          page.locator('.ui-widget-overlay:visible').count() == 0 and page.evaluate("() => document.body.style.overflow !== 'hidden'"),
          'overlays=%s overflow=%s' % (page.locator('.ui-widget-overlay:visible').count(), page.evaluate("() => document.body.style.overflow")))
    focus_ok = H.wait_for(lambda: page.evaluate("""(id) => { const a = document.activeElement;
        return Boolean(a && a.classList.contains('xterm-helper-textarea') && a.closest('.tlm-term-pane') && a.closest('.tlm-term-pane').dataset.id === id); }""", awaiting), timeout=10)
    B.chk('the waiting terminal holds the keyboard without a click', bool(focus_ok),
          page.evaluate("() => document.activeElement ? document.activeElement.tagName + '.' + document.activeElement.className : 'none'"))
    if awaiting:
        page.keyboard.type('Angela', delay=70)   # real key events to whatever holds the focus
        page.keyboard.press('Enter')
    done = H.wait_for(lambda: 'hello Angela end' in pool_log('terminater_1'), timeout=120)
    B.chk('after the user answers, the agent reports the finished line', bool(done), pool_log('terminater_1')[-300:])
    close_dialogs(H)
    B.api('kill_all')
    H.wait_for(lambda: len(B.terminals()) == 0, timeout=20)
    clear_canvas(H)
    result = load_flow(H, flow('ping -n 60 127.0.0.1', {'kind': 'cmd', 'wait_seconds': 120, 'hang_seconds': 600}), 'terminater-long.flw')
    page.locator('#btn-start').click()
    page.wait_for_timeout(900)
    press_in_dialog(H, 'Run')
    ping = H.wait_for(lambda: 'Pinging' in H.term_text(None, 30), timeout=120)
    B.chk('a long command from the flow is running in the visible terminal', bool(ping), H.term_text()[-200:])
    page.wait_for_timeout(1500)
    close_dialogs(H)
    page.locator('#btn-stop').click()
    page.wait_for_timeout(1500)
    press_in_dialog(H, 'Yes') or press_in_dialog(H, 'Stop') or press_in_dialog(H, 'Continue') or press_in_dialog(H, 'OK')
    ended = H.wait_for(lambda: not page.locator('#btn-stop').is_enabled(), timeout=120)
    B.chk('Stop ends the running flow', bool(ended))
    close_dialogs(H)
    page.wait_for_timeout(1000)
    listing = B.api('list')
    B.chk('stopping the flow never leaves the hub in a broken state', listing.get('ok') is not False, str(listing)[:200])


def run(H):
    empty = AcpBattery(H, 'acp/empty', 'acp')
    empty.run_all()
    empty.group('sidebar, drop, configure, editor', empty_page_specific, H, empty)
    empty.reset_dock()
    loaded = AcpBattery(H, 'acp/loaded', 'acp')
    loaded.group('load, validate, start, hand over, stop', loaded_page_specific, H, loaded)
    loaded.reset_dock()
    loaded.run_all(skip=('persistence',))
    print('acp suite: %d checks recorded, %d failed' % (len(H.results), len([r for r in H.results if not r['ok']])), flush=True)


def run_loaded_flow_only(H):
    """Only the flow group (load, validate, start, hand over, stop): the quick proof of the hand-over path."""
    loaded = AcpBattery(H, 'acp/loaded', 'acp')
    loaded.group('load, validate, start, hand over, stop', loaded_page_specific, H, loaded)
    print('acp flow group: %d checks recorded, %d failed' % (len(H.results), len([r for r in H.results if not r['ok']])), flush=True)


def main():
    only_flow = '--flow-group-only' in sys.argv
    with Harness('acp-flow' if only_flow else 'acp', PATH) as H:
        if only_flow:
            run_loaded_flow_only(H)
        else:
            run(H)
    sys.exit(getattr(H, 'exit_code', 1))


if __name__ == '__main__':
    main()
