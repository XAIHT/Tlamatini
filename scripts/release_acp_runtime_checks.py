# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Start, pause, resume and stop a real harmless ACP workflow through its UI."""
import json
import re

from playwright.sync_api import expect


def run_acp_runtime_checks(page, out, checkpoint):
    page.bring_to_front()
    previous = page.locator('.canvas-item').evaluate_all('nodes => nodes.map(node => node.outerHTML)')
    page.get_by_role('button', name='File', exact=True).click()
    page.locator('#file-close-button').click()
    page.wait_for_function('''() => document.querySelectorAll('.canvas-item').length === 0 ||
        [...document.querySelectorAll('[role="dialog"] button')].some(button =>
            button.textContent.trim() === 'Continue' && button.getClientRects().length)''')
    confirmation = page.get_by_role('dialog', name='Unsaved changes', exact=True)
    if confirmation.is_visible():
        confirmation.get_by_role('button', name='Cancel', exact=True).click()
        assert page.locator('.canvas-item').evaluate_all('nodes => nodes.map(node => node.outerHTML)') == previous
        page.get_by_role('button', name='File', exact=True).click()
        page.locator('#file-close-button').click()
        confirmation.get_by_role('button', name='Continue', exact=True).click()
    expect(page.locator('.canvas-item')).to_have_count(0)
    page.locator('#acp-example').click()
    expect(page.locator('.canvas-item')).to_have_count(3, timeout=30000)
    expect(page.locator('#acp-flow-settings')).to_be_enabled(timeout=30000)
    page.locator('#sleeper-1').click()
    page.locator('#acp-configure').click()
    properties = page.get_by_role('dialog', name='Properties: sleeper-1', exact=True)
    properties.locator('[data-key=duration_ms]').fill('180000')
    properties.get_by_role('button', name='Save', exact=True).click()
    expect(page.locator('#deployment-result-dialog')).to_be_visible()
    page.keyboard.press('Escape')
    page.locator('#btn-validate').click()
    validation = page.get_by_role('dialog', name=re.compile('Flow Validation: Passed'))
    expect(validation).to_be_visible(timeout=60000)
    validation.get_by_role('button', name='Continue!', exact=True).click()
    checkpoint('runtime-01-real-flow-validation', page)
    with page.expect_response(lambda r: '/execute_starter_agent/starter-1/' in r.url) as start:
        page.locator('#btn-start').click()
    started = start.value.json()
    assert started.get('success'), started
    headers = start.value.request.all_headers()
    session_headers = {k: v for k, v in headers.items() if k.lower() == 'x-agent-session-id'}
    assert session_headers, 'The runtime audit must use the same ACP session as Start'
    expect(page.locator('#starter-execution-title')).to_have_text('Startup Complete', timeout=60000)
    page.locator('.ui-dialog:visible').get_by_role('button', name='Continue!', exact=True).click()
    expect(page.locator('#btn-pause')).to_be_enabled()
    for control in ('configure', 'duplicate', 'delete', 'undo', 'flow-settings'):
        expect(page.locator('#acp-' + control)).to_be_disabled()
    checkpoint('runtime-02-running-edit-lock', page)
    with page.expect_response(lambda r: '/get_session_running_processes/' in r.url) as running:
        page.locator('#btn-pause').click()
    before_pause = running.value.json()
    assert before_pause.get('success') and before_pause.get('processes'), before_pause
    expect(page.locator('#btn-pause')).to_have_class(re.compile(r'.*\bpaused\b.*'), timeout=60000)
    expect(page.locator('#acp-configure')).to_be_disabled()
    checkpoint('runtime-03-paused-with-real-workers-recorded', page)
    with page.expect_response(lambda r: '/reanimate_agents/' in r.url) as resumed:
        page.locator('#btn-pause').click()
    resumed_result = resumed.value.json()
    assert resumed_result.get('success') and resumed_result.get('reanimated'), resumed_result
    expect(page.locator('#btn-pause')).not_to_have_class(re.compile(r'.*\bpaused\b.*'), timeout=60000)
    expect(page.locator('#btn-stop')).to_be_enabled()
    checkpoint('runtime-04-resumed-agent-execution', page)
    page.locator('#btn-stop').click()
    expect(page.locator('#btn-start')).to_be_enabled(timeout=60000)
    expect(page.locator('#btn-stop')).to_be_disabled()
    dialog = page.locator('.ui-dialog:visible')
    if dialog.count():
        dialog.get_by_role('button', name='Continue!', exact=True).click()
    expect(page.locator('#acp-flow-settings')).to_be_enabled()
    result = page.request.get(page.url.split('/agent/')[0] + '/agent/get_session_running_processes/', headers=session_headers).json()
    assert result.get('success') and not result.get('processes'), result
    (out / 'actual-acp-runtime.json').write_text(json.dumps(dict(
        started=started, before_pause=before_pause, resumed=resumed_result,
        after_stop=result), indent=2), encoding='utf-8')
    checkpoint('runtime-05-stopped-and-no-session-workers', page)
