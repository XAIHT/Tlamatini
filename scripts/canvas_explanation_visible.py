# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Visible source regression: real editor/button, captured chat transport,
production consumer/model delivery, isolated account and database.

Run in a verified foreground PowerShell -NoExit console. Inspect the full desktop
Shoter photo in Temp/canvas-explanation-visible/browser-waiting.png, then create
browser-visible-confirmed there. Monitor live.log; close.confirmed closes only
the owned browser/server. No headless option; no installed application changes.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import html
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import interactor_visible as harness

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/canvas-explanation-visible'
BASE = 'http://127.0.0.1:8893'
FLAGS = ['multi-turn-enabled', 'exec-report-enabled', 'acpx-enabled', 'ask-execs-enabled',
         'step-by-step-enabled', 'compact-mode-enabled', 'self-modify-enabled', 'internetEnabled']


def checks(page, context, window, capture, sent, errors, attempt):
    from agent.interactor.explanation import validate
    from agent.interactor.hub import hub
    from agent.consumers import AgentConsumer
    from django.contrib.auth import get_user_model
    from agent.global_state import global_state

    run = OUT / f'run-{attempt}'
    run.mkdir(parents=True, exist_ok=True)
    results = []
    # A maximized Windows frame includes invisible resize borders outside the
    # monitor. Restore only our owned test window before the strict visibility
    # check, including if it was maximized during a long checkbox sweep.
    if not hasattr(window, '_explanation_verify'):
        window._explanation_verify = window.verify

    def verify():
        import ctypes
        import win32con
        import win32gui
        if ctypes.windll.user32.IsZoomed(ctypes.c_void_p(window.hwnd)):
            win32gui.ShowWindow(window.hwnd, win32con.SW_RESTORE)
            window.resize(1440, 900)
        return window._explanation_verify()

    window.verify = verify
    if not getattr(page, '_explanation_dialog_handler', None):
        page._explanation_dialog_handler = lambda dialog: dialog.accept() if dialog.type == 'beforeunload' else dialog.dismiss()
        page.on('dialog', page._explanation_dialog_handler)
    page.goto(BASE + '/agent/agent/', wait_until='load')
    page.locator('#interactor-access').check()
    page.wait_for_function('window.TlamatiniInteractor?.clientId && window.TlamatiniChat')
    client = page.evaluate('TlamatiniInteractor.clientId')
    owner = hub.clients[client].owner
    with ThreadPoolExecutor(max_workers=1) as pool:
        user = pool.submit(lambda: get_user_model().objects.get(pk=int(owner[0]))).result()
    window.activate()
    page.evaluate('enableControlsAfterOperation()')

    def checkpoint(name, **details):
        window.activate()
        window.verify()
        assert not errors, errors
        photo, metadata = capture(f'run-{attempt}/{len(results)+1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name, 'details': details,
                        'foreground': metadata.get('foreground_title', '')})
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Canvas explanation verification</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}pre{white-space:pre-wrap}</style>'
            + ''.join(f'<h2>{html.escape(row["name"])}</h2><pre>{html.escape(str(row["details"]))}</pre>'
                      f'<img src="{row["photo"]}">' for row in results), encoding='utf-8')
        print(f'PASS {len(results)}: {name} {details}', flush=True)

    # Use the real file-drop routing and CodeMirror, then type an unsaved edit.
    fixture = '// unrelated file content\n' * 2000 + 'static const UINT kDefWidth = 1280;'
    fixture_path = run / 'main.cpp'
    fixture_path.write_text(fixture, encoding='utf-8')
    page.evaluate('''text => {
        const dt = new DataTransfer();
        dt.items.add(new File([text], 'main.cpp', {type:'text/plain'}));
        document.getElementById('editor-container').dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt}));
    }''', fixture)
    page.wait_for_function('TlamatiniTextEditor.filename === "main.cpp"')
    editor = page.locator('#editor-container .cm-content')
    editor.click()
    page.keyboard.press('Control+End')
    page.keyboard.press('Home')
    page.keyboard.press('Shift+End')
    live = 'static const UINT kDefWidth = 1536; // unsaved 🌎'
    page.keyboard.insert_text(live)
    page.keyboard.press('Home')
    page.keyboard.press('Shift+End')
    selected = page.evaluate('TlamatiniTextEditor.explanationSnapshot()')
    assert selected['excerpts'][0]['text'] == live
    assert selected['document_length'] > 46855
    page.locator('#chat-message-input').fill('Keep my unfinished draft exactly.')
    page.locator('#interactor-access').uncheck()

    for mask in range(1 << len(FLAGS)):
        window.verify()
        page.evaluate('''({ids,mask}) => {
            enableControlsAfterOperation();
            ids.forEach((id,i) => { document.getElementById(id).checked = !!(mask & (1 << i)); });
            window.dispatchEvent(new CustomEvent('tlm:editor-state'));
        }''', {'ids': FLAGS, 'mask': mask})
        sent.clear()
        page.locator('#interactor-explain').click()
        page.wait_for_function('inLongOperation')
        page.wait_for_timeout(30)
        frames = [json.loads(item) for item in sent if isinstance(item, str)]
        frames = [item for item in frames if item.get('type') == 'canvas-explain']
        assert len(frames) == 1, (mask, frames)
        value = validate(frames[0]['canvas_explanation'])
        assert value['excerpts'][0]['text'] == live and value['dirty']
        assert len(json.dumps(frames[0])) < 1500
        assert page.locator('#chat-message-input').input_value() == 'Keep my unfinished draft exactly.'
        assert page.evaluate('ids => ids.map(id => document.getElementById(id).checked)', FLAGS) == [bool(mask & (1 << i)) for i in range(len(FLAGS))]
        assert page.locator('#interactor-explain').is_disabled()
        if mask % 32 == 31:
            checkpoint(f'checkbox-combinations-{mask-30}-{mask+1}', live_editor=False, exact_unsaved_selection=True)
    packet = frames[0]
    assert fixture_path.read_text(encoding='utf-8') == fixture
    checkpoint('all-256-checkbox-combinations-preserve-draft-selection-and-file')

    # Send the actual captured button packet through the production consumer,
    # then deliver its real configured-model answer to the ordinary renderer.
    async def model_roundtrip():
        consumer = AgentConsumer()
        consumer.scope = {'user': user, 'session': SimpleNamespace(session_key=owner[1])}
        consumer.room_group_name = 'canvas-explanation-visible'
        consumer.rag_chain = None
        consumer._say = lambda text: text.replace('{name}', 'Reviewer')
        consumer.load_recent_chat_history = AsyncMock(return_value=[])
        consumer._schedule_context_gauge_refresh = Mock()
        messages = []

        async def deliver(room, event):
            messages.append(event)

        consumer.channel_layer = SimpleNamespace(group_send=deliver)
        jobs = []
        create_task = asyncio.create_task

        def track(coro):
            task = create_task(coro)
            jobs.append(task)
            return task

        ready = global_state.get_state('rag_chain_ready')
        global_state.set_state('rag_chain_ready', False)
        try:
            with patch('agent.consumers.asyncio.create_task', side_effect=track), patch('agent.host_voice.answer_finished'):
                await consumer.receive(json.dumps(packet))
                await asyncio.gather(*jobs)
        finally:
            global_state.set_state('rag_chain_ready', ready)
        return messages

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: asyncio.run(model_roundtrip()))
        started = time.monotonic()
        while not future.done():
            window.verify()
            page.wait_for_timeout(1000)
            if int(time.monotonic() - started) % 10 == 0:
                print(f'Configured model explanation running: {time.monotonic()-started:.0f}s', flush=True)
        delivered = future.result()
    answers = [event for event in delivered if event.get('username') == 'Tlamatini' and event.get('message_id')]
    assert answers, delivered
    answer = answers[-1]['message']
    assert '1536' in answer and '1280' not in answer, answer
    assert 'context_limit' not in answer and 'Enable Multi-Turn' not in answer, answer
    page.evaluate('frames => frames.filter(frame => frame.type === "agent_message").forEach(frame => chatSocket.onmessage({data:JSON.stringify(frame)}))', delivered)
    page.wait_for_function('!inLongOperation')
    page.wait_for_function('!document.getElementById("interactor-status").textContent.includes("Explaining your selected text")')
    assert page.locator('#chat-message-input').input_value() == 'Keep my unfinished draft exactly.'
    assert page.evaluate('TlamatiniTextEditor.explanationSnapshot()') == selected
    (run / 'model-answer.json').write_text(json.dumps({'packet': packet, 'answer': answer}, ensure_ascii=False, indent=2), encoding='utf-8')
    checkpoint('configured-model-explains-unsaved-1536-with-no-tools-and-rag-not-ready')

    page.evaluate('TlamatiniTextEditor.interactor.select(0,0)')
    sent.clear()
    page.locator('#interactor-explain').click()
    page.wait_for_timeout(100)
    whole = [json.loads(item) for item in sent if isinstance(item, str) and json.loads(item).get('type') == 'canvas-explain'][-1]
    assert validate(whole['canvas_explanation'])['scope'] == 'document'
    assert len(whole['canvas_explanation']['excerpts'][0]['text']) > 46855
    page.evaluate('enableControlsAfterOperation()')
    checkpoint('no-selection-sends-complete-current-file')
    return results


if __name__ == '__main__':
    harness.OUT = OUT
    harness.canvas_test.OUT = OUT
    harness.PORT = 8893
    harness.BASE = BASE
    # The shared runner reloads checks by this path for an explicit rerun.
    harness.__file__ = __file__
    raise SystemExit(harness.main())
