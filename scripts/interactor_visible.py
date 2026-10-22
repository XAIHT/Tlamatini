# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Visible Interactor acceptance. Run only in a verified foreground console.

Uses an isolated database and actual authenticated editor WebSockets. The normal
chat socket is captured for deterministic UI checks; this is not a real-model
quality benchmark. Shoter photos document the actual desktop. Never headless.
Inspect browser-waiting.png, create browser-visible-confirmed, watch live.log,
then close with close.confirmed. A rerun.confirmed repeats checks visibly.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import subprocess
import threading
import time
import traceback

import canvas_editing_visible as canvas_test
from canvas_editing_visible import configure_visible_window, dismiss_owned_dialogs, owned_dialogs, verify_dialog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/interactor-visible'
PORT = 8883
BASE = f'http://127.0.0.1:{PORT}'
canvas_test.OUT = OUT
LiveTranscript = canvas_test.LiveTranscript


def checks(page, context, window, capture, sent, errors, attempt):
    if (OUT / "rebuild.confirmed").exists():
        window.verify()
        subprocess.run(["node", "scripts/build_canvas_editor.mjs"], cwd=ROOT, check=True)
        from django.core.management import call_command
        call_command("collectstatic", interactive=False, verbosity=0)
        from django.template import engines
        for backend in engines.all():
            for loader in backend.engine.template_loaders:
                loader.reset()
        (OUT / "rebuild.confirmed").unlink()
    if (OUT / 'model-only.confirmed').exists():
        return model_checks(page, context, window, capture, sent, errors, attempt)
    from agent.cancellation import begin_llm_run, reset_for_tests
    from agent.interactor.context import Request, current
    from agent.interactor.hub import hub
    from agent.interactor.tool import perform
    from canvas_refresh_visible import native_open, write_pdf
    run = OUT / f'run-{attempt}'
    run.mkdir(parents=True, exist_ok=True)
    results = []
    if not getattr(page, '_interactor_dialog_handler', None):
        page._interactor_dialog_handler = lambda dialog: dialog.accept() if dialog.type == 'beforeunload' else dialog.dismiss()
        page.on('dialog', page._interactor_dialog_handler)
    page.goto(BASE + '/agent/agent/', wait_until='load')
    page.wait_for_function('window.TlamatiniInteractor?.clientId')
    page.bring_to_front()
    probe = context.new_page()
    probe.set_content('<title>Real visibility preflight</title><h1>Checking real tab visibility before editor tests</h1>')
    probe.bring_to_front()
    try:
        print('VISIBILITY PREFLIGHT:', page.evaluate('({hidden:document.hidden,state:document.visibilityState,override:!!Object.getOwnPropertyDescriptor(document,"hidden")})'), flush=True)
        page.wait_for_function('document.hidden', polling=100, timeout=5000)
    finally:
        probe.close()
        page.bring_to_front()
    page.evaluate('enableControlsAfterOperation()')
    page.evaluate('''() => {
        window.interactorDebug = [];
        for (const name of ['tlm:editor-state', 'tlm:editor-takeover', 'keydown', 'pointerdown']) {
            window.addEventListener(name, event => {
                window.interactorDebug.push({event:name, detail:event.detail, key:event.key,
                    selection:window.TlamatiniTextEditor?.inspect().selection});
                if (window.interactorDebug.length > 30) window.interactorDebug.shift();
            });
        }
    }''')
    window.activate()
    divider = page.locator('#drag-divider').bounding_box()
    page.mouse.move(divider['x'] + divider['width'] / 2, divider['y'] + 150)
    page.mouse.down()
    page.mouse.move(page.evaluate('innerWidth') / 2, divider['y'] + 150, steps=12)
    page.mouse.up()
    editor = page.locator('#editor-container .cm-content')
    client_id = page.evaluate('TlamatiniInteractor.clientId')
    owner = hub.clients[client_id].owner
    user_id = int(owner[0])
    reset_for_tests(user_id)
    req = None

    def turn():
        nonlocal req
        page.evaluate('TlamatiniInteractor.beforeChat()')
        req = Request(owner, page.evaluate('TlamatiniInteractor.clientId'), user_id, begin_llm_run(user_id))

    def checkpoint(name, **details):
        window.activate()
        page.mouse.move(20, 10)
        page.wait_for_timeout(180)
        window.verify()
        assert not errors, errors
        photo, metadata = capture(f'run-{attempt}/{len(results) + 1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name, 'details': details,
                        'foreground': metadata.get('foreground_title', '')})
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Interactor visible acceptance</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}pre{white-space:pre-wrap}</style>'
            + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2>'
                      f'<pre>{html.escape(json.dumps(row["details"], ensure_ascii=False))}</pre>'
                      f'<img src="{html.escape(row["photo"])}">' for i, row in enumerate(results)), encoding='utf-8')
        print(f'PASS {len(results)}: {name}', flush=True)

    def value():
        return page.evaluate('TlamatiniTextEditor.getText()')

    def invoke(**args):
        token = current.set(req)
        try:
            return json.loads(perform(**args))
        finally:
            current.reset(token)

    with ThreadPoolExecutor(max_workers=1) as pool:
        def call(action, expect_ok=True, during=None, **args):
            future = pool.submit(invoke, action=action, **args)
            if during:
                during()
            deadline = time.monotonic() + 90
            while not future.done() and time.monotonic() < deadline:
                page.wait_for_timeout(40)
            assert future.done(), f'Action stuck: {action}'
            result = future.result()
            if result.get('ok') is not expect_ok:
                print('EDITOR EVENT TRACE:', page.evaluate('window.interactorDebug'), flush=True)
            assert result.get('ok') is expect_ok, (action, result)
            return result

        def read():
            return call('read')

        def edit(action, **args):
            state = read()
            return call(action, document_id=state['document_id'], revision=state['revision'], **args)

        def save():
            result = edit('save')
            assert result['status'] == 'saved'
            return result

        def new_file(name):
            state = read()
            return call('new', document_id=state['document_id'], revision=state['revision'], filename=name)

        turn()
        blank = read()
        assert blank['text'] == '' and not blank['active']
        checkpoint('connected-live-editor-with-no-file')
        created = new_file('Dockerfile')
        target = Path(created['path'])
        assert target.name == 'Dockerfile' and target.is_relative_to(ROOT / 'Temp/interactor')
        assert target.read_bytes() == b''
        assert read()['language'] == 'Dockerfile'
        checkpoint('empty-Dockerfile-created-in-Temp', path=str(target))

        observations = []
        def watch_typing():
            page.wait_for_function('TlamatiniTextEditor.getText().length > 0')
            observations.append(value())
            checkpoint('visible-character-by-character-typing', observed_prefix=observations[-1])
        edit('type', text='# Java servlet application\nFROM ', typing_wpm=160, during=watch_typing)
        assert len(observations[0]) < len(value())
        assert target.read_bytes() == b''
        typed_step = value()
        page.keyboard.press('Control+z')
        assert value() == '', 'One Undo must undo the whole AI teaching segment.'
        page.keyboard.press('Control+y')
        assert value() == typed_step
        checkpoint('AI-segment-is-one-undoable-step')
        state = read()
        edit('guide', label='Servlet runtime image', hint='Choose the Java and servlet versions your application requires. Tomcat 10 uses Jakarta; older javax.servlet code needs migration or a compatible runtime.',
             choices=[{'text': 'tomcat:10.1-jdk21-temurin', 'detail': 'Jakarta Servlet with Java 21'},
                      {'text': 'tomcat:9-jdk17-temurin', 'detail': 'Older javax.servlet applications with Java 17'}])
        assert value() == state['text'], 'A guide must not insert the learner value.'
        checkpoint('handoff-explains-field-without-filling-it')
        blocked = call('type', expect_ok=False, text='unwanted')
        assert blocked['status'] == 'operator_required'
        editor.click()
        page.keyboard.press('Control+End')
        started = time.perf_counter()
        page.keyboard.type('tomcat:10', delay=90)
        page.locator('.tlm-interactor-ghost').wait_for()
        assert value().endswith('tomcat:10') and 'jdk21' not in value()
        checkpoint('local-ghost-is-not-document-content', elapsed_including_deliberate_keyboard_delays=time.perf_counter()-started)
        page.keyboard.press('Escape')
        assert page.locator('.tlm-interactor-ghost').count() == 0
        checkpoint('escape-dismisses-completion')
        page.keyboard.press('Backspace')
        page.keyboard.type('0')
        page.keyboard.press('Tab')
        assert value().endswith('tomcat:10.1-jdk21-temurin')
        checkpoint('tab-accepts-exact-expected-field')
        page.keyboard.press('Control+z')
        assert value().endswith('tomcat:10')
        page.keyboard.press('Control+y')
        assert value().endswith('tomcat:10.1-jdk21-temurin')
        checkpoint('completion-undo-redo-keeps-user-prefix')
        turn()
        live = read()
        assert live['dirty'] and live['text'] == value() and target.read_bytes() == b''
        checkpoint('tool-reads-exact-unsaved-learner-content', source=live['source'])
        save()
        assert target.read_text(encoding='utf-8') == value()
        checkpoint('model-save-persists-live-buffer-outside-Downloads')

        old = read()
        editor.click()
        page.keyboard.press('Control+End')
        page.keyboard.press('Enter')
        page.keyboard.type('# learner edit')
        conflict = call('type', expect_ok=False, document_id=old['document_id'], revision=old['revision'], text='stale')
        assert conflict['status'] == 'conflict' and value().endswith('# learner edit')
        checkpoint('stale-model-edit-refused-with-user-work-kept')
        turn()
        dirty_new = edit('new', expect_ok=False, filename='NeverCreated.txt')
        assert dirty_new['status'] == 'unsaved_changes'
        save()

        def take_over():
            before = len(value())
            page.wait_for_function('(n) => TlamatiniTextEditor.getText().length > n', arg=before)
            page.keyboard.type('USER', delay=30)
        state = read()
        result = call('type', expect_ok=False, document_id=state['document_id'], revision=state['revision'],
                      text='\n# this long explanation should stop when the learner takes over', typing_wpm=160, during=take_over)
        assert result['status'] == 'aborted' and 'USER' in value()
        kept = value()
        page.wait_for_timeout(350)
        assert value() == kept
        checkpoint('learner-typing-immediately-stops-AI')
        turn()
        save()

        before_stop = value()
        def press_stop():
            page.wait_for_function('(text) => TlamatiniTextEditor.getText() !== text', arg=before_stop)
            page.locator('#interactor-stop').click()
        edit('type', text='\n# Stop tutor must interrupt this teaching segment', typing_wpm=160,
             expect_ok=False, during=press_stop)
        stopped = value()
        page.wait_for_timeout(350)
        assert value() == stopped and stopped != before_stop
        checkpoint('Stop-tutor-keeps-only-typed-prefix')
        turn()
        save()

        # A real foreground Chrome window with a SECOND tab reproduces the
        # installed failure. No headless browser or synthetic visibility flag.
        away = context.new_page()
        away.set_content('<title>Interactor visibility regression</title><body style="background:#202632;color:#eee;font:24px system-ui;padding:50px">'
                         '<h1>Interactor pause / resume check</h1><p>The chat is in the other tab. Its pending edit must wait and then resume exactly once.</p></body>')
        def hide_chat():
            away.bring_to_front()
            page.wait_for_function('document.hidden', polling=100)

        def wait_paused():
            page.wait_for_function('document.querySelector("#interactor-status").textContent.startsWith("Editing paused")', polling=100)

        def return_to_chat():
            page.bring_to_front()
            page.wait_for_function('!document.hidden', polling=100)

        hide_chat()
        def resume_new():
            wait_paused()
            checkpoint('new-file-waits-for-visible-tab')
            return_to_chat()
        state = read()
        created = call('new', document_id=state['document_id'], revision=state['revision'],
                       filename='Service-Port.yaml', during=resume_new)
        assert value() == '' and Path(created['path']).read_bytes() == b''
        checkpoint('new-file-resumes-without-another-chat-request')

        hide_chat()
        def resume_first_segment():
            wait_paused()
            assert value() == ''
            checkpoint('kind-segment-paused-before-first-character')
            # Longer than the old 20-second typing overhead: a normal temporary
            # absence must not consume the original execution deadline.
            for remaining in (30, 20, 10):
                print(f'VISIBILITY CHECK: {remaining}s remaining in deliberate tab absence.', flush=True)
                window.verify()
                page.wait_for_timeout(10000)
            assert value() == ''
            return_to_chat()
        result = edit('type', text='kind: ', typing_wpm=160, during=resume_first_segment)
        assert result['verified'] and value() == 'kind: '
        page.keyboard.press('Control+z')
        assert value() == ''
        page.keyboard.press('Control+y')
        assert value() == 'kind: '
        checkpoint('kind-segment-resumes-once-after-30s-and-undoes-as-one-step')

        before_pause = value()
        def pause_mid_step():
            page.wait_for_function('(text) => TlamatiniTextEditor.getText() !== text', arg=before_pause)
            hide_chat()
            wait_paused()
            prefix = value()
            page.wait_for_timeout(1300)
            assert value() == prefix and len(prefix) < len(before_pause + 'Service\nmetadata:\n  name: ')
            checkpoint('mid-segment-tab-switch-pauses-with-prefix-intact', prefix=prefix)
            return_to_chat()
        edit('type', text='Service\nmetadata:\n  name: ', typing_wpm=100, during=pause_mid_step)
        assert value() == before_pause + 'Service\nmetadata:\n  name: '
        page.keyboard.press('Control+z')
        assert value() == before_pause
        page.keyboard.press('Control+y')
        checkpoint('mid-segment-resume-preserves-exact-text-and-single-undo')

        hide_chat()
        def resume_guide():
            wait_paused()
            return_to_chat()
        edit('guide', label='Service name', hint='Choose the service name.',
             choices=[{'text': 'web', 'detail': 'Web application'}], during=resume_guide)
        assert page.locator('#interactor-card').is_visible()
        checkpoint('guide-resumes-after-tab-switch')
        turn()
        hidden_before_cancel = value()
        hide_chat()
        def cancel_wait():
            wait_paused()
            page.evaluate('TlamatiniInteractor.cancel()')
            return_to_chat()
        result = edit('type', text='never inserted', expect_ok=False, during=cancel_wait)
        assert result['status'] == 'aborted'
        page.wait_for_timeout(300)
        assert value() == hidden_before_cancel
        checkpoint('cancel-while-paused-never-resumes-or-inserts')
        turn()
        hide_chat()
        def change_document():
            wait_paused()
            page.evaluate('TlamatiniTextEditor.setDocument("learner-owned content", "replacement.yaml")')
            return_to_chat()
        result = edit('type', text='outdated edit', expect_ok=False, during=change_document)
        assert result['status'] == 'aborted' and value() == 'learner-owned content'
        checkpoint('document-replacement-while-paused-cancels-stale-edit')
        away.close()
        turn()
        save()

        samples = [
            ('lesson.py', 'print("café 😀")\n', 'Python'),
            ('lesson.json', '{"learner":"日本語 🦋"}\n', 'JSON'),
            ('Servlet.java', 'class Servlet {}\n', 'Java'),
            ('index.html', '<h1>Hello</h1>\n', 'HTML'),
            ('main.rs', 'fn main() {}\n', 'Rust'),
            ('README.md', '# Guided lesson\n\n**Your choice**\n', 'Markdown'),
        ]
        for name, content, language in samples:
            opened = new_file(name)
            edit('type', text=content, typing_wpm=160)
            assert read()['language'] == language
            assert read()['text'] == content
            save()
            assert Path(opened['path']).read_text(encoding='utf-8') == content
            checkpoint('typed-read-saved-' + name.replace('.', '-'))
        page.locator('#markdown-preview-button').click()
        assert page.locator('#markdown-canvas-document h1').inner_text() == 'Guided lesson'
        checkpoint('Markdown-preview-renders-same-source')
        edit('type', text='Next: ', typing_wpm=160)
        assert editor.is_visible()
        checkpoint('AI-edit-switches-Markdown-to-source')
        before_preview = value()
        def switch_preview():
            page.wait_for_function('(text) => TlamatiniTextEditor.getText() !== text', arg=before_preview)
            page.locator('#markdown-preview-button').click()
        edit('type', text='this step stops when Source is hidden', typing_wpm=160,
             expect_ok=False, during=switch_preview)
        hidden_text = value()
        page.wait_for_timeout(350)
        assert value() == hidden_text and not editor.is_visible()
        checkpoint('switching-away-from-source-stops-visible-typing')
        turn()
        page.locator('#markdown-source-button').click()
        edit('type', text='', expect_ok=False)
        edit('type', text='\nNext: ', typing_wpm=160)
        edit('guide', label='Next topic', hint='Choose your next topic or enter your own.',
             choices=[{'text': 'Docker deployment', 'detail': 'Package and run'}, {'text': 'Docker testing', 'detail': 'Check the image'}])
        page.keyboard.type('D')
        page.keyboard.press('Control+ArrowRight')
        assert value().endswith('Docker ')
        checkpoint('partial-word-acceptance')
        page.locator('#interactor-choices button').first.click()
        assert value().endswith('Docker deployment')
        checkpoint('suggestion-button-accepts-its-field-value')
        page.keyboard.press('Control+z')
        assert value().endswith('Docker ')
        page.locator('#interactor-suggestions').uncheck()
        assert page.locator('.tlm-interactor-ghost').count() == 0
        editor.click()
        page.keyboard.press('Control+End')
        page.keyboard.type('my own topic')
        assert value().endswith('Docker my own topic')
        checkpoint('optional-suggestions-allow-custom-answer')

        window.resize(1060, 760)
        geometry = page.evaluate('''() => [...document.querySelectorAll('#interactor-bar button, #interactor-bar label')]
            .filter(e=>e.getClientRects().length).map(e=>({text:e.textContent,r:e.getBoundingClientRect().toJSON()}))''')
        assert len(geometry) >= 3, 'Toolbar geometry check did not find the controls.'
        for index, item in enumerate(geometry):
            for other in geometry[index+1:]:
                a, b = item['r'], other['r']
                assert min(a['right'], b['right'])-max(a['left'], b['left']) <= 1 or min(a['bottom'],b['bottom'])-max(a['top'],b['top']) <= 1
        checkpoint('narrow-tutoring-controls-remain-usable')
        window.resize(1440, 900)

        page.locator('#chat-message-input').fill('My existing draft')
        page.locator('#interactor-ask').click()
        assert page.locator('#chat-message-input').input_value() == 'My existing draft'
        assert 'draft is kept' in page.locator('#interactor-status').inner_text()
        checkpoint('hint-preserves-existing-chat-draft')
        page.locator('#chat-message-input').fill('')
        page.locator('#multi-turn-enabled').check()
        sent.clear()
        page.locator('#interactor-continue').click()
        page.wait_for_timeout(200)
        packets = [json.loads(item) for item in sent if isinstance(item, str)]
        chat = [item for item in packets if item.get('interactor_client_id')]
        assert chat and chat[-1]['interactor_client_id'] == req.client_id
        assert 'fresh unsaved' in json.dumps(chat[-1])
        assert page.locator('#interactor-card').is_hidden()
        checkpoint('Continue-sends-normal-chat-with-originating-editor')
        page.evaluate('enableControlsAfterOperation()')
        editor.click()
        page.keyboard.press('Control+Home')
        page.keyboard.press('Control+Shift+ArrowRight')
        selected = page.evaluate('TlamatiniTextEditor.inspect().selection')
        assert selected['to'] > selected['from']
        sent.clear()
        page.locator('#interactor-explain').click()
        page.wait_for_timeout(150)
        explanation = [json.loads(item) for item in sent if isinstance(item, str)]
        assert any(item.get('interactor_client_id') == req.client_id and 'explain my selection' in json.dumps(item) for item in explanation)
        checkpoint('Explain-selection-uses-normal-chat-and-keeps-range')
        page.evaluate('enableControlsAfterOperation()')
        turn()
        save()
        page.locator('#interactor-access').uncheck()
        page.wait_for_timeout(150)
        assert not call('read', expect_ok=False)['ok']
        checkpoint('user-can-pause-live-editor-access')
        page.locator('#interactor-access').check()
        page.wait_for_timeout(150)
        turn()
        assert read()['text'] == value()

        # Reload proves unsaved text is not silently treated as a disk snapshot;
        # the old originating-tab identity becomes unusable.
        old_id = req.client_id
        page.reload(wait_until='load')
        page.wait_for_function('window.TlamatiniInteractor?.clientId')
        assert page.evaluate('TlamatiniInteractor.clientId') != old_id
        assert not call('read', expect_ok=False)['ok']
        checkpoint('reloaded-tab-invalidates-old-request-identity')
        page.evaluate('enableControlsAfterOperation()')
        pdf = run / 'read-only.pdf'
        write_pdf(pdf, 'Read-only PDF remains a viewer', pages=1)
        native_open(page, window, pdf)
        page.wait_for_function('window.TlamatiniPdfCanvas?.active')
        turn()
        current_pdf = read()
        assert not current_pdf['active']
        assert not edit('type', text='never in PDF', expect_ok=False)['ok']
        checkpoint('PDF-refuses-typing-and-keeps-viewer')
    reset_for_tests(user_id)
    if (OUT / 'include-model.confirmed').exists():
        results.extend(model_checks(page, context, window, capture, sent, errors, attempt))
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Interactor acceptance</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}pre{white-space:pre-wrap}</style>'
            + ''.join(f'<h2>{i+1}. {html.escape(row["name"])}</h2>'
                      f'<pre>{html.escape(json.dumps(row["details"], ensure_ascii=False))}</pre>'
                      f'<img src="{html.escape(row["photo"])}">' for i, row in enumerate(results)), encoding='utf-8')
    return results


def model_checks(page, browser_context, window, capture, sent, errors, attempt):
    """Real configured model + production executor/tool + actual editor socket.

    Other tools are deliberately unavailable. The chat transport remains captured;
    answers use the normal chat renderer. This certifies model planning/application,
    not the application's full RAG startup or external MCP services.
    """
    from agent.cancellation import begin_llm_run, reset_for_tests
    from agent.interactor.context import Request, current
    from agent.interactor.hub import hub
    from agent.interactor.tool import build_tool
    from agent.mcp_agent import MultiTurnToolAgentExecutor, _build_system_prompt, _ensure_chat_tool_model
    from agent.rag.config import default_application_path, load_config_and_prompt
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_ollama.llms import OllamaLLM
    page.goto(BASE + '/agent/agent/', wait_until='load')
    page.wait_for_function('window.TlamatiniInteractor?.clientId')
    page.evaluate('enableControlsAfterOperation()')
    window.activate()
    window.verify()
    divider = page.locator("#drag-divider").bounding_box()
    page.mouse.move(divider["x"] + divider["width"] / 2, divider["y"] + 150)
    page.mouse.down()
    page.mouse.move(page.evaluate("innerWidth") / 2, divider["y"] + 150, steps=12)
    page.mouse.up()
    client_id = page.evaluate('TlamatiniInteractor.clientId')
    owner = hub.clients[client_id].owner
    user_id = int(owner[0])
    reset_for_tests(user_id)
    run = OUT / f'run-{attempt}'
    run.mkdir(parents=True, exist_ok=True)
    config, prompt, _ = load_config_and_prompt(default_application_path())
    model = config.get('unified_agent_model') or config.get('model')
    assert model, 'No configured model; live-model validation cannot run.'
    results, history, actions = [], [], []
    tool = build_tool()
    original = tool.func

    def tracked(**args):
        result = original(**args)
        actions.append({'action': args.get('action'), 'args': args, 'result': json.loads(result)})
        print('REAL MODEL EDITOR ACTION:', args.get('action'), json.loads(result).get('status'), flush=True)
        return result
    tool.func = tracked
    holder = {}

    def invoke(request, question):
        token = current.set(request)
        try:
            if 'executor' not in holder:
                llm = _ensure_chat_tool_model(OllamaLLM(model=model))
                holder['executor'] = MultiTurnToolAgentExecutor(
                    llm, _build_system_prompt(prompt, [tool], self_knowledge=False), [tool], max_iterations=14)
            return holder['executor'].invoke({'input': question, 'chat_history': list(history),
                'ask_execs_user_id': user_id, 'cancel_run_epoch': request.run_epoch,
                'ask_execs_enabled': False, 'exec_report_enabled': False})
        finally:
            current.reset(token)

    def checkpoint(name, **details):
        window.activate()
        page.mouse.move(20, 10)
        page.wait_for_timeout(180)
        window.verify()
        assert not errors, errors
        photo, metadata = capture(f'run-{attempt}/{len(results)+1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name, 'details': details,
                        'foreground': metadata.get('foreground_title', '')})
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f'PASS {len(results)}: {name}', flush=True)

    with ThreadPoolExecutor(max_workers=1) as pool:
        def question(text):
            page.evaluate('TlamatiniInteractor.beforeChat()')
            req = Request(owner, client_id, user_id, begin_llm_run(user_id))
            page.evaluate('(text) => appendChatMessage("interactor-review", text)', text)
            future = pool.submit(invoke, req, text)
            last_report = time.monotonic()
            while not future.done():
                page.wait_for_timeout(100)
                if time.monotonic() - last_report > 10:
                    window.verify()
                    print('REAL MODEL: waiting; completed editor actions:', len(actions), flush=True)
                    last_report = time.monotonic()
            output = future.result()
            answer = str(output.get('output', ''))
            assert answer.strip(), output
            page.evaluate('(text) => appendChatMessage("Tlamatini", text)', answer)
            history.extend([HumanMessage(content=text), AIMessage(content=answer)])
            (run / 'model-evidence.json').write_text(json.dumps({'model': model, 'actions': actions,
                'answers': [m.content for m in history]}, ensure_ascii=False, indent=2,
                default=lambda value: value.model_dump() if hasattr(value, 'model_dump') else str(value)), encoding='utf-8')
            return answer

        question('Help me create a Dockerfile for a Java application with a servlet and a landing page, using your text editor. No path is provided. Teach one small step at a time. Type the first known segment, then stop at the first field I must choose. Give recommendations in chat and optional completions in the editor. Do not finish, save, or run the file for me.')
        state = page.evaluate('TlamatiniTextEditor.inspect()')
        assert state['filename'] == 'Dockerfile', state
        assert state['text'] and state['guide'], state
        assert state['guide']['choices'], 'The model did not prepare field completions.'
        assert not any(item['action'] == 'save' for item in actions)
        assert {'read', 'new', 'type', 'guide'} <= {item['action'] for item in actions}
        checkpoint('real-model-creates-types-and-hands-off-Dockerfile', model=model, actions=[item['action'] for item in actions])
        value = state['guide']['choices'][0]['text']
        page.locator('#editor-container .cm-content').click()
        page.keyboard.press('Control+End')
        page.keyboard.type(value[:2], delay=150)
        page.locator('.tlm-interactor-ghost').wait_for()
        checkpoint('real-model-expected-field-completes-locally', chosen=value)
        page.keyboard.press('Tab')
        filled = page.evaluate('TlamatiniTextEditor.getText()')
        assert value in filled
        start = len(actions)
        question('I filled the field in your editor. Read my fresh UNSAVED text, explain what my choice means, and stop without changing the file this turn.')
        reads = [item['result'] for item in actions[start:] if item['action'] == 'read']
        assert reads and reads[0]['text'] == filled
        assert page.evaluate('TlamatiniTextEditor.getText()') == filled
        checkpoint('real-model-reads-and-explains-unsaved-learner-answer', read_matches=True)
    reset_for_tests(user_id)
    return results

def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN. No workload ran.')
    from markdown_canvas_visible import visible_console
    visible_console()
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('stdout', 'stderr'):
        if not getattr(getattr(sys, name), 'canvas_editing_transcript', False):
            setattr(sys, name, LiveTranscript(getattr(sys, name)))
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    os.environ['TLAMATINI_NO_AUDIO'] = '1'
    import tlamatini.settings as settings
    settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    import django
    django.setup()
    from django.core.management import call_command
    print('Preparing isolated database and collecting source static files.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    sys.path.insert(0, str(ROOT))
    from build_runtime_assets import verify_collected_static
    verify_collected_static(ROOT)
    from django.contrib.auth import get_user_model
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username='interactor-review')
    user.set_password(password)
    user.save()
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application),
                                         host='127.0.0.1', port=PORT,
                                         log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Isolated source server failed to start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # A separate CDP session cannot undo Playwright's session-owned forced focus.
    # Disable it in this harness's driver only; never alter installed packages.
    preload = ROOT / 'scripts/playwright_real_visibility.cjs'
    os.environ['NODE_OPTIONS'] = (os.environ.get('NODE_OPTIONS', '') + f' --require="{preload.as_posix()}"').strip()
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    from canvas_refresh_visible import activate_browser
    import drag_divider_look_visible as photos
    success = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=80)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        sent, errors = [], []
        context.route_web_socket(re.compile(r'.*/ws/(?!interactor/)'), lambda socket: socket.on_message(lambda message: sent.append(message)))
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))

        class EditingWindow(VisibleWindow):
            def activate(self):
                activate_browser(self)

            def verify(self):
                import win32api
                self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
                return super().verify()

        window = EditingWindow(page, context)
        configure_visible_window(page, window)
        window.resize(1440, 900)
        page.goto(BASE + '/', wait_until='load')

        def capture(name, native=None):
            import win32gui
            if native is None:
                window.verify()
            else:
                verify_dialog(native)
            photos.OUT = OUT / Path(name).parent
            photos.OUT.mkdir(parents=True, exist_ok=True)
            photo, metadata = photos.shoter(Path(name).name)
            metadata['foreground_title'] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            if native is None:
                window.verify()
            else:
                verify_dialog(native)
            return photo, metadata

        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        capture('browser-waiting.png')
        print('BROWSER WAITING: inspect browser-waiting.png, then create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(300)
        page.locator('#id_username').fill('interactor-review')
        page.locator('#id_password').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state('load')
        password = None
        attempt = sum(path.is_dir() for path in OUT.glob('run-*'))
        close, rerun = OUT / 'close.confirmed', OUT / 'rerun.confirmed'
        close.unlink(missing_ok=True)
        rerun.unlink(missing_ok=True)
        while not close.exists() and not page.is_closed():
            attempt += 1
            try:
                errors.clear()
                spec = importlib.util.spec_from_file_location('editing_checks', __file__)
                latest = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(latest)
                results = latest.checks(page, context, window, capture, sent, errors, attempt)
                success = True
                result = {'passed': True, 'checks': len(results), 'attempt': attempt}
            except Exception:
                success = False
                traceback.print_exc()
                result = {'passed': False, 'attempt': attempt, 'error': traceback.format_exc()}
                try:
                    dialogs = owned_dialogs(window)
                    if dialogs:
                        capture(f'run-{attempt}-failure.png', native=dialogs[-1])
                    else:
                        window.activate()
                        capture(f'run-{attempt}-failure.png')
                except Exception as error:
                    print('Failure capture unavailable:', error, flush=True)
            (OUT / 'final-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print('BROWSER STAYS OPEN. rerun.confirmed repeats; close.confirmed ends.', flush=True)
            while not close.exists() and not rerun.exists() and not page.is_closed():
                page.wait_for_timeout(500)
            if rerun.exists():
                rerun.unlink()
        dismiss_owned_dialogs(page, window)
        window.release()
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    print('FINAL:', 'PASS' if success else 'FAIL', 'exit', 0 if success else 1, flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
