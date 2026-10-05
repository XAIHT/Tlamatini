# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Real model, scheduling, branching and cancellation through Prompt Flow UI."""
import json
import time

from playwright.sync_api import expect


def run_prompt_runtime_checks(page, out, checkpoint):
    page.bring_to_front()
    events = []

    def received(payload):
        try:
            events.append(json.loads(payload))
        except (ValueError, TypeError):
            pass

    def socket_opened(socket):
        if '/ws/prompt-flow-panel/' in socket.url:
            socket.on('framereceived', received)

    page.on('websocket', socket_opened)
    page.reload()
    expect(page.locator('#pmt-play')).to_be_enabled(timeout=60000)

    def node(key, kind, text='', **config):
        if kind in ('prompt', 'programmed_prompt'):
            config.update(multi_turn=False, acpx=False)
        if kind == 'programmed_prompt':
            config.setdefault('scheduled_at', '')
        if kind == 'decision':
            config.setdefault('case_sensitive', False)
        return dict(id=key, type=kind, label=key, x=70 + 230 * len(key), y=80,
                    config=dict(text=text, **config))

    def edge(source, target, branch='next'):
        return dict(id=source + '-' + branch, source=source, target=target, branch=branch)

    def open_flow(name, nodes, edges=(), max_steps=20):
        for index, item in enumerate(nodes):
            item.update(x=80 + (index % 3) * 320, y=100 + (index // 3) * 240)
        path = out / (name + '.fpmt')
        path.write_text(json.dumps(dict(format='tlamatini-prompting-flow', version=2,
            name=name, start=nodes[0]['id'], max_steps=max_steps, nodes=nodes, edges=list(edges))), encoding='utf-8')
        page.get_by_role('button', name='File', exact=True).click()
        with page.expect_file_chooser() as chooser:
            page.locator('[data-action=open]').click()
        chooser.value.set_files(str(path))
        page.wait_for_function('''name => document.getElementById('filename').textContent === name
            || !!document.querySelector('.tlmpop-overlay')''', arg=path.name)
        confirm = page.locator('.tlmpop-overlay button').filter(has_text='Continue')
        if confirm.is_visible():
            confirm.click()
        expect(page.locator('#filename')).to_have_text(path.name)
        expect(page.locator('.pmt-node')).to_have_count(len(nodes))
        page.locator('[data-action=fit]').click()
        page.locator('#pmt-validate').click()
        validation = page.locator('.tlmpop-overlay')
        expect(validation).to_contain_text('The flow is ready to play.')
        validation.get_by_role('button', name='OK', exact=True).click()
        events.clear()
        page.locator('#pmt-play').click()

    def wait_event(predicate, timeout=180):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            match = next((event for event in events if predicate(event)), None)
            if match:
                return match
            failures = [event for event in events if event.get('event') == 'state'
                        and event.get('status') == 'failed']
            assert not failures, failures
            page.wait_for_timeout(500)
        raise AssertionError('Expected runtime event did not arrive: ' + repr(events[-8:]))

    def save_events(name):
        (out / (name + '-events.json')).write_text(json.dumps(events, indent=2), encoding='utf-8')

    # The two actual inference requests use the application's configured model.
    # The campaign pins every Ollama field to nemotron-3-ultra:cloud beforehand.
    open_flow('live-prompt-schedule', [
        node('prompt', 'prompt', 'Reply with exactly RELEASE_OK and no other text.'),
        node('branch', 'decision', comparison='contains', value='RELEASE_OK'),
        node('scheduled', 'programmed_prompt', 'Reply with exactly SCHEDULED_OK and no other text.', delay_seconds=8),
        node('flush', 'flush_embeddings'), node('clean', 'clean_history'),
    ], [edge('prompt', 'branch'), edge('branch', 'scheduled', 'yes'),
        edge('branch', 'clean', 'no'),
        edge('scheduled', 'flush'), edge('flush', 'clean')])
    answer = wait_event(lambda event: event.get('event') == 'output' and event.get('node_id') == 'prompt')
    assert 'RELEASE_OK' in answer['text'], answer
    wait_event(lambda event: event.get('event') == 'waiting' and event.get('node_id') == 'scheduled')
    page.locator('#pmt-pause').click()
    expect(page.locator('#pmt-run-state')).to_have_text('paused')
    page.wait_for_timeout(3000)
    assert not any(event.get('event') == 'output' and event.get('node_id') == 'scheduled' for event in events)
    checkpoint('prompt-runtime-01-real-model-and-paused-schedule', page)
    page.locator('#pmt-pause').click()
    expect(page.locator('#pmt-run-state')).to_have_text('completed', timeout=180000)
    scheduled = [event for event in events if event.get('event') == 'output' and event.get('node_id') == 'scheduled']
    assert len(scheduled) == 1 and 'SCHEDULED_OK' in scheduled[0]['text'], scheduled
    completed = {event.get('node_id') for event in events
                 if event.get('event') == 'node' and event.get('status') == 'completed'}
    assert completed == {'prompt', 'branch', 'scheduled', 'flush', 'clean'}, completed
    save_events('live-prompt-schedule')
    checkpoint('prompt-runtime-02-resume-branch-flush-and-clean-complete', page)

    open_flow('cancel-scheduled', [node('later', 'programmed_prompt', 'Reply with NEVER_RUN.', delay_seconds=600)])
    wait_event(lambda event: event.get('event') == 'waiting')
    page.locator('#pmt-stop').click()
    expect(page.locator('#pmt-run-state')).to_have_text('stopped', timeout=30000)
    assert not any(event.get('event') == 'output' for event in events)
    save_events('cancel-scheduled')
    checkpoint('prompt-runtime-03-stop-before-scheduled-inference', page)

    open_flow('bounded-loop', [node('loop', 'clean_history')], [edge('loop', 'loop')], max_steps=3)
    expect(page.locator('#pmt-run-state')).to_have_text('failed', timeout=30000)
    expect(page.locator('#pmt-run-log')).to_contain_text('Step limit reached')
    assert len([event for event in events if event.get('event') == 'node' and event.get('status') == 'completed']) == 3
    save_events('bounded-loop')
    checkpoint('prompt-runtime-04-loop-limit-is-a-visible-failure', page)

    open_flow('embedding-capability', [
        node('feed', 'feed_embeddings', 'Release validation scratch context: turquoise orchard.'),
        node('after-feed', 'clean_history'),
    ], [edge('feed', 'after-feed')])
    deadline = time.monotonic() + 180
    while page.locator('#pmt-run-state').inner_text() not in ('completed', 'failed'):
        assert time.monotonic() < deadline, 'Embedding capability did not resolve within 180 seconds'
        page.wait_for_timeout(500)
    terminal = page.locator('#pmt-run-state').inner_text()
    if terminal == 'failed':
        expect(page.locator('#pmt-run-log')).to_contain_text('Embedding setup failed')
        assert not any(event.get('event') == 'node' and event.get('node_id') == 'after-feed' for event in events)
        result = dict(embedding_execution='BLOCKED', failure_handling='PASS',
                      reason='The exclusively authorized model did not initialize embeddings; no fallback model was used.')
        checkpoint('prompt-runtime-05-embedding-failure-stops-before-next-operation', page)
    else:
        result = dict(embedding_execution='PASS', failure_handling='NOT_APPLICABLE')
        checkpoint('prompt-runtime-05-real-embedding-and-next-operation', page)
    (out / 'embedding-capability.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    save_events('embedding-capability')
    page.remove_listener('websocket', socket_opened)
