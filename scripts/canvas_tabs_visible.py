# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Multi-document Canvas acceptance in real, visible Chrome.

Uses the actual source page, isolated Django database, authenticated Interactor
WebSocket, native file dialogs and exact disk-byte assertions. Normal chat
transport is captured: context payload/selection checks do not claim a model
ingestion benchmark. Explicitly labelled delay injection exercises stale work.
Run from a verified foreground Tlamatini PowerShell console. Inspect the
browser-waiting.png photograph before creating browser-visible-confirmed.
The browser remains open until close.confirmed; rerun.confirmed repeats checks.
All temporary data remains under this repository's Temp directory.
"""
from concurrent.futures import ThreadPoolExecutor
import html
import json
import os
from pathlib import Path
import time

import interactor_visible as harness

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/canvas-tabs-visible'
PORT = 8895 if ROOT.name.endswith('-Spanish') else 8894
BASE = f'http://127.0.0.1:{PORT}'


def native_shortcut_checks(page, context, window, capture, attempt):
    """Exercise Windows keys through Chrome's accelerator, not CDP key dispatch."""
    import win32api
    import win32con

    documents = page.evaluate('TlamatiniCanvasTabs.list()')
    first = next(item['document_id'] for item in documents if item['kind'] != 'pdf')
    assert len(documents) > 1

    def select_first():
        page.bring_to_front()
        window.activate()
        page.locator(f'#canvas-tabs [role="tab"][data-document-id="{first}"]').click()

    def press_native(*keys):
        window.activate()
        window.verify()
        pressed = []
        try:
            for key in keys:
                extended = win32con.KEYEVENTF_EXTENDEDKEY if key in (win32con.VK_PRIOR, win32con.VK_NEXT) else 0
                win32api.keybd_event(key, win32api.MapVirtualKey(key, 0), extended, 0)
                pressed.append((key, extended))
                time.sleep(.045)
        finally:
            for key, extended in reversed(pressed):
                win32api.keybd_event(key, win32api.MapVirtualKey(key, 0), extended | win32con.KEYEVENTF_KEYUP, 0)
        page.wait_for_timeout(350)

    probe = context.new_page()
    probe.set_content('<title>Native Ctrl+Tab browser test</title><h1>Chrome switched browser tabs</h1>'
                      '<p>This is the second owned tab used to verify native Windows keyboard behavior.</p>')
    try:
        select_first()
        page.locator('#chat-message-input').click()
        press_native(win32con.VK_CONTROL, win32con.VK_TAB)
        outside = {'canvas': page.evaluate('TlamatiniCanvasTabs.activeId()'),
                   'app_hidden': page.evaluate('document.hidden'),
                   'browser_tab_visible': probe.evaluate('!document.hidden')}
        assert outside['canvas'] == first and outside['app_hidden'] and outside['browser_tab_visible'], outside
        capture(f'run-{attempt}/native-control-tab-outside-canvas.png')

        select_first()
        source = page.locator('#markdown-source-button')
        if source.is_visible():
            source.click()
        page.locator('#editor-container .cm-content').click()
        press_native(win32con.VK_CONTROL, win32con.VK_TAB)
        inside = {'canvas_switched': page.evaluate('TlamatiniCanvasTabs.activeId()') != first,
                  'browser_switched': page.evaluate('document.hidden') and probe.evaluate('!document.hidden')}
        assert inside['canvas_switched'] != inside['browser_switched'], inside
        capture(f'run-{attempt}/native-control-tab-inside-canvas.png')

        select_first()
        page.locator('#editor-container .cm-content').click()
        press_native(win32con.VK_MENU, win32con.VK_NEXT)
        page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() !== id', arg=first)
        alternate_target = page.evaluate('TlamatiniCanvasTabs.activeId()')
        assert not page.evaluate('document.hidden')
        press_native(win32con.VK_MENU, win32con.VK_PRIOR)
        page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() === id', arg=first)
        page.locator('#chat-message-input').click()
        press_native(win32con.VK_MENU, win32con.VK_NEXT)
        assert page.evaluate('TlamatiniCanvasTabs.activeId()') == first
        details = {'outside_canvas': outside, 'inside_canvas': inside,
                   'native_alt_page_target': alternate_target,
                   'input': 'Windows keybd_event with verified owned foreground Chrome; modifiers released in finally.'}
        print('NATIVE SHORTCUTS:', json.dumps(details), flush=True)
        return details
    finally:
        probe.close()
        page.bring_to_front()
        window.activate()


def pdf_visual_audit(page, window, capture, attempt):
    """Measure actual rendered ink and scroll geometry before adjusting review."""
    run = OUT / f'run-{attempt}'
    run.mkdir(exist_ok=True)
    window.activate()
    window.verify()
    frame = page.locator('#pdf-canvas-host iframe:visible').content_frame
    read_state = '''() => {
        const container = document.querySelector('#pdf-viewer-container');
        const bounds = element => {
            const r = element.getBoundingClientRect();
            return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
        };
        const clip = bounds(container), number = Number(document.querySelector('#pdf-page').value);
        const sheet = document.querySelector(`.page[data-page-number="${number}"]`);
        const canvas = sheet?.querySelector('canvas');
        const text = [...(sheet?.querySelectorAll('.textLayer span') || [])]
            .filter(span=>span.textContent.trim()).map(span=>({text:span.textContent,rect:bounds(span)}));
        let ink = null;
        if (canvas && canvas.width && canvas.height) {
            const rect = bounds(canvas), data = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
            let count=0, visible=0, minX=canvas.width,minY=canvas.height,maxX=-1,maxY=-1;
            for(let index=0;index<data.length;index+=4) {
                if(data[index+3]<200 || Math.min(data[index],data[index+1],data[index+2])>230)continue;
                const pixel=index/4, x=pixel%canvas.width,y=Math.floor(pixel/canvas.width);
                count++; minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y);
                const screenX=rect.left+x/canvas.width*rect.width,screenY=rect.top+y/canvas.height*rect.height;
                if(screenX>=clip.left && screenX<clip.right && screenY>=clip.top && screenY<clip.bottom)visible++;
            }
            ink={pixels:count,visible_pixels:visible,canvas_width:canvas.width,canvas_height:canvas.height,
                pixel_bounds:{minX,minY,maxX,maxY},canvas_rect:rect};
        }
        return {page:number,zoom:document.querySelector('#pdf-zoom').value,mode:document.querySelector('#pdf-scroll-mode').value,
            scroll_top:container.scrollTop,scroll_left:container.scrollLeft,scroll_height:container.scrollHeight,
            container_rect:clip,page_rect:sheet?bounds(sheet):null,text,ink,status:document.querySelector('#pdf-status').textContent};
    }'''
    before = frame.locator('body').evaluate(read_state)
    before_photo, _ = capture(f'run-{attempt}/pdf-render-audit-before.png')
    frame.locator('#pdf-page').fill('1')
    frame.locator('#pdf-page').press('Tab')
    frame.locator('#pdf-viewer-container').click(position={'x': 20, 'y': 20})
    frame.locator('#pdf-viewer-container').press('Control+Home')
    deadline = time.monotonic() + 10
    while True:
        page.wait_for_timeout(200)
        after = frame.locator('body').evaluate(read_state)
        if after['ink'] and after['ink']['visible_pixels'] > 50:
            break
        if time.monotonic() >= deadline:
            break
    after_photo, _ = capture(f'run-{attempt}/pdf-render-audit-page-one-top.png')
    report = {'before': before, 'after': after, 'before_photo': before_photo.name, 'after_photo': after_photo.name}
    (run / 'pdf-render-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PDF RENDER AUDIT:', json.dumps(report), flush=True)
    assert after['page'] == 1 and after['scroll_top'] <= 1, after
    assert after['ink'] and after['ink']['visible_pixels'] > 50, after
    assert any('reference' in item['text'].lower() for item in after['text']), after
    result = [{'name': 'actual-pdf-painted-ink-visible-on-page-one', 'details': report, 'photo': after_photo.name}]
    (run / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def checks(page, context, window, capture, sent, errors, attempt):
    visual_audit = (OUT / 'pdf-visual-audit-only.confirmed').exists()
    if visual_audit and page.locator('#pdf-canvas-host iframe:visible').count():
        return pdf_visual_audit(page, window, capture, attempt)
    focused_keyboard = (OUT / 'native-keyboard-only.confirmed').exists()
    focused_pdf = (OUT / 'pdf-context-refresh-only.confirmed').exists()
    focused_pdf_open = (OUT / 'pdf-interactor-open-only.confirmed').exists()
    from playwright.sync_api import Error as PlaywrightError
    from canvas_refresh_visible import native_open, write_pdf
    from canvas_editing_visible import choose_native_save
    from agent.cancellation import begin_llm_run, reset_for_tests
    from agent.interactor.context import Request, current
    from agent.interactor.hub import hub
    from agent.interactor.tool import perform

    run = OUT / f'run-{attempt}'
    fixtures, saved = run / 'fixtures', run / 'saved'
    fixtures.mkdir(parents=True, exist_ok=True)
    saved.mkdir(exist_ok=True)
    results = []
    page.set_default_timeout(20000)

    def permit_old_run(dialog):
        assert dialog.type == 'beforeunload', dialog.type
        dialog.accept()

    if not focused_keyboard:
        page.on('dialog', permit_old_run)
        try:
            page.goto(BASE + '/agent/agent/', wait_until='load')
        finally:
            page.remove_listener('dialog', permit_old_run)
    page.wait_for_function('window.TlamatiniCanvasTabs && window.TlamatiniInteractor?.clientId')
    page.evaluate('enableControlsAfterOperation()')
    window.activate()
    window.verify()
    divider = page.locator('#drag-divider').bounding_box()
    page.mouse.move(divider['x'] + divider['width'] / 2, divider['y'] + 100)
    page.mouse.down()
    page.mouse.move(page.evaluate('innerWidth') * .40, divider['y'] + 100, steps=12)
    page.mouse.up()

    def active():
        return page.evaluate('TlamatiniCanvasTabs.activeId()')

    def state():
        return page.evaluate('TlamatiniTextEditor.inspect()')

    def text():
        return page.evaluate('TlamatiniTextEditor.getText()')

    def tab(identifier):
        return page.locator(f'#canvas-tabs [role="tab"][data-document-id="{identifier}"]')

    def activate(identifier):
        window.activate()
        tab(identifier).click()
        page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() === id', arg=identifier)

    def source_view():
        source = page.locator('#markdown-source-button')
        if source.is_visible():
            source.click()
        return page.locator('#editor-container .cm-content')

    def append(value):
        source_view().click()
        page.keyboard.press('Control+End')
        for index, line in enumerate(value.split('\n')):
            if index:
                page.keyboard.press('Enter')
            if line:
                page.keyboard.insert_text(line)

    def checkpoint(name, **details):
        window.activate()
        page.wait_for_timeout(180)
        window.verify()
        assert not errors, errors
        photograph, metadata = capture(f'run-{attempt}/{len(results) + 1:02d}-{name}.png')
        results.append({'name': name, 'photo': photograph.name, 'details': details,
                        'foreground': metadata.get('foreground_title', '')})
        (run / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Canvas tabs acceptance</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}img{width:95%}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            + ''.join(f'<h2>{i + 1}. {html.escape(row["name"])}</h2>'
                      f'<pre>{html.escape(json.dumps(row["details"], ensure_ascii=False))}</pre>'
                      f'<img src="{html.escape(row["photo"])}">' for i, row in enumerate(results)), encoding='utf-8')
        print(f'PASS {len(results)}: {name}', flush=True)

    def context_frames(start=0):
        frames = []
        for value in sent[start:]:
            if isinstance(value, str):
                try:
                    frame = json.loads(value)
                except ValueError:
                    continue
                if 'context' in frame.get('type', ''):
                    frames.append(frame)
        return frames

    def deliver_chat_frame(frame):
        # Explicit protocol injection: the real handler processes captured-chat
        # acknowledgements. No model/embedding completion is claimed.
        page.evaluate('(frame) => chatSocket.onmessage({data:JSON.stringify(frame)})', frame)

    def start_context():
        start = len(sent)
        page.locator('#context-button').click()
        page.wait_for_function('TlamatiniCanvasTabs.contextPending')
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            frames = [frame for frame in context_frames(start)
                      if frame.get('type') == 'set-canvas-documents-as-context']
            if frames:
                assert len(frames) == 1, frames
                return frames[0]
            page.wait_for_timeout(50)
        raise AssertionError('Context selection did not send its request.')

    def complete_context(payload):
        documents = [{key: item[key] for key in ('document_id', 'filename', 'revision')}
                     for item in payload['documents']]
        captured = run / 'captured-context-transport.txt'
        captured.write_text('\n\n'.join(item['filename'] + '\n' + item.get('content', '[PDF context token]')
                                       for item in payload['documents']), encoding='utf-8')
        deliver_chat_frame({'type': 'context-path-set', 'context_path': str(captured),
                            'context_type': 'file', 'context_filename': captured.name,
                            'canvas_documents': documents})
        deliver_chat_frame({'type': 'canvas-documents-context-result', 'request_id': payload['request_id'],
                            'success': True, 'documents': documents})
        assert not page.evaluate('TlamatiniCanvasTabs.contextPending')
        assert str(captured) in page.evaluate('contextDataSpan.textContent')

    def select_context():
        """Actual click/payload; explicit completion for captured chat WS."""
        payload = start_context()
        complete_context(payload)
        return payload

    def prepare_review_workspace():
        window.activate()
        divider = page.locator('#drag-divider').bounding_box()
        page.mouse.move(divider['x'] + divider['width'] / 2, divider['y'] + 100)
        page.mouse.down()
        page.mouse.move(page.evaluate('innerWidth') * .35, divider['y'] + 100, steps=16)
        page.mouse.up()
        inventory = page.evaluate('TlamatiniCanvasTabs.list()')
        text_documents = [item for item in inventory if item['kind'] != 'pdf']
        for document in text_documents[:2]:
            activate(document['document_id'])
            if not document['context'] or document['stale']:
                select_context()
        review_pdf = next(item['document_id'] for item in inventory if item['kind'] == 'pdf')
        activate(review_pdf)
        expected = {item['document_id'] for item in text_documents[:2]}
        assert set(page.evaluate('TlamatiniCanvasTabs.list().filter(item=>item.context).map(item=>item.document_id)')) == expected
        assert not page.evaluate('canvasSettedAsContext')
        assert page.locator('#canvas-tabs [role="tab"]').count() == 4
        panel_width = page.locator('#canvas-container').bounding_box()['width']
        assert panel_width >= page.evaluate('innerWidth') * .55, panel_width
        return {'selected_context': [item['filename'] for item in text_documents[:2]],
                'unselected_pdf': True, 'canvas_width': panel_width,
                'transport': 'Explicit captured-chat acknowledgement; visual context selection, no model result.'}

    def verify_pdf_context_refresh(pdf_path, identifier):
        """Real authenticated text-only extraction, followed by captured-chat ack."""
        activate(identifier)
        expected_text_ids = set(page.evaluate('TlamatiniCanvasTabs.list().filter(item=>item.context).map(item=>item.document_id)'))
        assert identifier not in expected_text_ids

        def prepare_and_accept():
            start = len(sent)
            page.locator('#context-button').click()
            page.locator('#pdf-context-progress').wait_for(state='visible')
            assert not page.locator('#pdf-context-process-images').is_checked()
            page.locator('#pdf-context-continue').click()
            deadline = time.monotonic() + 60
            payload = None
            while time.monotonic() < deadline:
                frames = [frame for frame in context_frames(start)
                          if frame.get('type') == 'set-canvas-documents-as-context']
                if frames:
                    assert len(frames) == 1
                    payload = frames[0]
                    break
                page.wait_for_timeout(100)
            assert payload, {'pdf_progress': page.locator('#pdf-context-progress-message').inner_text(),
                             'pending': page.evaluate('TlamatiniCanvasTabs.contextPending')}
            pdf_document = next(item for item in payload['documents'] if item['document_id'] == identifier)
            token = pdf_document.get('context_token')
            assert isinstance(token, str) and len(token) > 16 and 'content' not in pdf_document
            complete_context(payload)
            page.locator('#pdf-context-progress').wait_for(state='hidden')
            meta = page.evaluate('(id)=>TlamatiniCanvasTabs.list().find(item=>item.document_id===id)', identifier)
            assert meta['context'] and not meta['stale'], meta
            return token, meta['revision']

        first_token, revision_before = prepare_and_accept()
        checkpoint('real-pdf-text-extraction-produces-context-token-and-progress-finishes',
                   extraction='Real local authenticated upload and status polling, images disabled.',
                   acknowledgement='Captured chat protocol only; no model/embedding execution.')
        write_pdf(pdf_path, 'Updated PDF reference for multi-document context revision', pages=4)
        page.locator('#reopen-canvas-button').click()
        page.wait_for_function('''({id,revision}) => !TlamatiniCanvasRefresh.busy && TlamatiniPdfCanvas.ready &&
            TlamatiniCanvasTabs.activeId()===id && TlamatiniCanvasTabs.list().find(item=>item.document_id===id).revision>revision''',
                               arg={'id': identifier, 'revision': revision_before})
        stale = page.evaluate('(id)=>TlamatiniCanvasTabs.list().find(item=>item.document_id===id)', identifier)
        assert stale['context'] and stale['stale'], stale
        checkpoint('refreshed-pdf-keeps-tab-identity-and-marks-old-context-snapshot-stale',
                   revision_before=revision_before, revision_after=stale['revision'])
        next_token, updated_revision = prepare_and_accept()
        assert next_token != first_token, 'Changed PDF reused the old prepared capability.'
        removed = select_context()
        assert {item['document_id'] for item in removed['documents']} == expected_text_ids
        assert set(page.evaluate('TlamatiniCanvasTabs.list().filter(item=>item.context).map(item=>item.document_id)')) == expected_text_ids
        checkpoint('explicit-pdf-context-update-refreshes-token-and-removal-retains-text-selections',
                   updated_revision=updated_revision, selected_text_documents=len(expected_text_ids))

    def verify_interactor_open_from_pdf(identifier, path):
        activate(identifier)
        before = page.evaluate('TlamatiniCanvasTabs.list()')
        before_ids = {item['document_id'] for item in before}
        before_context = {item['document_id'] for item in before if item['context']}
        page.evaluate('window.pdfOpenProofFrame = document.querySelector("#pdf-canvas-host iframe:not([hidden])")')
        page.locator('#interactor-access').check()
        client_id = page.evaluate('TlamatiniInteractor.clientId')
        owner = hub.clients[client_id].owner
        user_id = int(owner[0])
        reset_for_tests(user_id)
        page.evaluate('TlamatiniInteractor.beforeChat()')
        request = Request(owner, client_id, user_id, begin_llm_run(user_id))

        def invoke_pdf(**arguments):
            token = current.set(request)
            try:
                return json.loads(perform(**arguments))
            finally:
                current.reset(token)

        with ThreadPoolExecutor(max_workers=1) as pool:
            def call_pdf(action, **arguments):
                future = pool.submit(invoke_pdf, action=action, **arguments)
                deadline = time.monotonic() + 45
                while not future.done() and time.monotonic() < deadline:
                    page.wait_for_timeout(35)
                assert future.done(), f'Interactor from-PDF action timed out: {action}'
                return future.result()

            read = call_pdf('read')
            assert read['ok'] and read['document_id'] == identifier, read
            opened = call_pdf('open', path=str(path))
            assert opened['ok'] and opened['snapshot']['document_id'] not in before_ids, opened
            new_id = opened['snapshot']['document_id']
            assert active() == new_id and text() == path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
            after = page.evaluate('TlamatiniCanvasTabs.list()')
            assert {item['document_id'] for item in after} == before_ids | {new_id}
            assert {item['document_id'] for item in after if item['context']} == before_context
            assert not next(item['dirty'] for item in after if item['document_id'] == new_id)
            assert page.evaluate('pdfOpenProofFrame.isConnected && pdfOpenProofFrame.hidden')
            checkpoint('real-interactor-opens-existing-file-from-active-pdf-with-other-tabs-preserved',
                       previous_tabs=len(before), resulting_tabs=len(after), opened_file=path.name)
        page.locator(f'#canvas-tabs .canvas-document-tab[data-document-id="{new_id}"] .canvas-tab-close').click()
        page.wait_for_function('(id)=>!TlamatiniCanvasTabs.get(id)', arg=new_id)
        activate(identifier)
        assert page.evaluate('document.querySelector("#pdf-canvas-host iframe:not([hidden])") === pdfOpenProofFrame')
        assert {item['document_id'] for item in page.evaluate('TlamatiniCanvasTabs.list()')} == before_ids
        reset_for_tests(user_id)

    if focused_keyboard:
        details = native_shortcut_checks(page, context, window, capture, attempt)
        checkpoint('native-windows-shortcuts-focused-followup', **details)
        checkpoint('four-document-context-review-presentation', **prepare_review_workspace())
        return results

    a, b, c, pdf = (fixtures / name for name in ('alpha.py', 'beta.md', 'gamma.txt', 'reference.pdf'))
    a.write_bytes('# Alpha — áéíóú 🦋\r\nvalue = 1\r\n'.encode('utf-8-sig'))
    b.write_text('# Beta\n\nIndependent Markdown document.\n', encoding='utf-8')
    c.write_text('Gamma remains outside chat context.\n', encoding='utf-8')
    write_pdf(pdf, 'Reference for multi-document Canvas', pages=4)

    if visual_audit:
        for path in (a, b, c, pdf):
            native_open(page, window, path)
        prepare_review_workspace()
        return pdf_visual_audit(page, window, capture, attempt)

    if focused_pdf:
        for path in (a, b, c, pdf):
            native_open(page, window, path)
        prepare_review_workspace()
        verify_pdf_context_refresh(pdf, active())
        checkpoint('four-document-context-review-presentation', **prepare_review_workspace())
        return results

    if focused_pdf_open:
        for path in (a, b, c, pdf):
            native_open(page, window, path)
        prepare_review_workspace()
        verify_interactor_open_from_pdf(active(), a)
        checkpoint('four-document-context-review-presentation', **prepare_review_workspace())
        return results

    generated = 'Generated in memory; not yet stored in a file.\n'
    page.evaluate('(content) => loadCanvasWithThisContent(content)', generated)
    draft_id = active()
    assert draft_id and page.evaluate('TlamatiniCanvasTabs.anyUnsaved()')
    assert '*' in tab(draft_id).inner_text(), 'An unchanged in-memory draft was incorrectly treated as persistent.'
    page.evaluate('(id) => { window.draftClose = TlamatiniCanvasTabs.close(id); }', draft_id)
    page.locator('#tlm-popup-host').wait_for()
    page.keyboard.press('Escape')
    assert not page.evaluate('window.draftClose')
    assert text() == generated
    draft_destination = saved / 'generated.txt'
    page.locator('#canvas-save-as-button').click()
    choose_native_save(page, window, draft_destination, capture, f'run-{attempt}/native-save-generated.png')
    page.wait_for_function('!TlamatiniCanvasEditing.busy && !TlamatiniCanvasEditing.dirty')
    assert draft_destination.read_bytes() == generated.encode('utf-8')
    assert not page.evaluate('TlamatiniCanvasTabs.anyUnsaved()')
    checkpoint('unchanged-generated-draft-is-unsaved-until-real-native-save', saved=str(draft_destination))
    assert page.evaluate('(id) => TlamatiniCanvasTabs.close(id)', draft_id)
    assert page.locator('#canvas-tabs [role="tab"]').count() == 0

    native_open(page, window, a)
    a_id = active()
    assert state()['document_id'] == a_id
    original_a = text()
    append('# unsaved Alpha')
    edited_a = text()
    assert edited_a == original_a + '# unsaved Alpha'
    assert page.evaluate('TlamatiniCanvasTabs.anyUnsaved()')
    assert '*' in tab(a_id).inner_text()
    page.keyboard.press('Home')
    page.keyboard.press('Shift+End')
    a_selection = state()['selection']
    checkpoint('first-document-dirty-and-selection-visible')

    native_open(page, window, b)
    b_id = active()
    assert b_id != a_id
    assert page.locator('#canvas-tabs [role="tab"]').count() == 2
    assert page.locator('#tlm-popup-host').count() == 0, 'Opening another document must not ask to discard Alpha.'
    append('Beta edit')
    edited_b = text()
    activate(a_id)
    assert text() == edited_a and state()['selection'] == a_selection
    source_view().click()
    page.keyboard.press('Control+z')
    assert text() == original_a
    page.keyboard.press('Control+y')
    assert text() == edited_a
    activate(b_id)
    assert text() == edited_b
    checkpoint('independent-buffers-undo-and-selection')

    activate(a_id)
    start = len(sent)
    selected_a = select_context()
    assert [item['document_id'] for item in selected_a['documents']] == [a_id], selected_a
    assert selected_a['documents'][0]['content'] == edited_a
    frames = context_frames(start)
    native_open(page, window, c)
    c_id = active()
    assert c_id not in {a_id, b_id}
    assert page.locator('#canvas-tabs .canvas-tab-context:visible').count() >= 1
    assert not page.evaluate('canvasSettedAsContext'), 'An open, unselected document inherited context.'
    assert len(context_frames(start)) == len(frames), 'Opening a tab silently replaced chat context.'
    checkpoint('context-selection-survives-opening-another-document', selected='alpha.py', unselected=['beta.md', 'gamma.txt'])

    activate(b_id)
    selected_ab = select_context()
    assert {item['document_id'] for item in selected_ab['documents']} == {a_id, b_id}
    assert next(item['content'] for item in selected_ab['documents'] if item['document_id'] == b_id) == edited_b
    activate(c_id)
    assert not page.evaluate('canvasSettedAsContext')
    assert page.locator('#canvas-tabs .canvas-tab-context:visible').count() == 2
    checkpoint('explicit-A-and-B-context-selections-exclude-C', selected=['alpha.py', 'beta.md'],
               transport='Actual context button/payload; deterministic acknowledgement, no model claim.')

    activate(a_id)
    append(' changed after context')
    edited_a = text()
    assert page.evaluate('(id) => TlamatiniCanvasTabs.list().find(item => item.document_id === id).stale', a_id)
    activate(b_id)
    assert next(item['content'] for item in selected_ab['documents'] if item['document_id'] == a_id) != edited_a
    activate(a_id)
    updated_ab = select_context()
    assert next(item['content'] for item in updated_ab['documents'] if item['document_id'] == a_id) == edited_a
    assert {item['document_id'] for item in updated_ab['documents']} == {a_id, b_id}
    assert not page.evaluate('(id) => TlamatiniCanvasTabs.list().find(item => item.document_id === id).stale', a_id)
    activate(c_id)
    checkpoint('edited-context-is-stale-until-explicit-update-with-other-selection-retained')

    # A rejected proposed selection cannot replace the last confirmed A+B set.
    header_before_rejection = page.evaluate('contextDataSpan.textContent')
    rejected_context = start_context()
    request_count = len(context_frames())
    assert page.locator('#context-button').is_disabled()
    assert not page.evaluate('TlamatiniCanvasTabs.changeContext()')
    page.wait_for_timeout(150)
    assert len(context_frames()) == request_count, 'Duplicate context request escaped the pending guard.'
    deliver_chat_frame({'type': 'canvas-documents-context-result', 'request_id': 'unrelated-request',
                        'success': True, 'documents': []})
    assert page.evaluate('TlamatiniCanvasTabs.contextPending'), 'An unrelated acknowledgement cleared the real operation.'
    assert page.locator('#context-button').is_disabled(), 'An unrelated acknowledgement re-enabled an in-flight context request.'
    deliver_chat_frame({'type': 'canvas-documents-context-result', 'request_id': rejected_context['request_id'],
                        'success': False, 'message': 'Acceptance test: server refused the proposed context.'})
    page.locator('#tlm-popup-host').wait_for()
    page.keyboard.press('Escape')
    assert not page.evaluate('TlamatiniCanvasTabs.contextPending')
    assert page.evaluate('contextDataSpan.textContent') == header_before_rejection
    assert set(page.evaluate('TlamatiniCanvasTabs.list().filter(item=>item.context).map(item=>item.document_id)')) == {a_id, b_id}
    checkpoint('rejected-context-preserves-confirmed-set-and-duplicate-requests-are-blocked',
               transport='Captured chat: explicit unrelated/success and matching/rejection frames; no model execution.')

    # A clean active document cannot hide dirty buffers in the departure guard.
    observed = []

    def cancel_departure(dialog):
        observed.append(dialog.type)
        assert dialog.type == 'beforeunload', dialog.type
        dialog.dismiss()

    page.on('dialog', cancel_departure)
    try:
        try:
            page.reload(timeout=2500)
        except PlaywrightError:
            assert observed, 'Navigation failed without the required unsaved warning.'
    finally:
        page.remove_listener('dialog', cancel_departure)
    assert observed == ['beforeunload'], observed
    assert active() == c_id
    activate(a_id)
    assert text() == edited_a
    checkpoint('real-browser-departure-warning-for-inactive-unsaved-document')

    # The themed tab-close warning is canceled by Escape, leaving the document.
    page.evaluate('(id) => { window.canvasCloseAttempt = TlamatiniCanvasTabs.close(id); }', a_id)
    page.locator('#tlm-popup-host').wait_for()
    page.keyboard.press('Escape')
    assert page.evaluate('window.canvasCloseAttempt.then(result => !result)')
    assert tab(a_id).count() == 1 and text() == edited_a
    checkpoint('cancel-close-keeps-unsaved-document')

    # Real native Save As writes the Alpha buffer with its original BOM/CRLF.
    destination = saved / 'alpha-saved.py'
    page.locator('#canvas-save-as-button').click()
    choose_native_save(page, window, destination, capture, f'run-{attempt}/native-save-alpha.png')
    page.wait_for_function('!TlamatiniCanvasEditing.busy && !TlamatiniCanvasEditing.dirty')
    assert destination.read_bytes() == edited_a.replace('\n', '\r\n').encode('utf-8-sig')
    assert '*' not in tab(a_id).inner_text()
    assert '*' in tab(b_id).inner_text()
    checkpoint('native-save-persists-only-its-tab-with-original-encoding', saved=str(destination))

    activate(b_id)
    b_destination = saved / 'beta-saved.md'
    page.locator('#canvas-save-as-button').click()
    choose_native_save(page, window, b_destination, capture, f'run-{attempt}/native-save-beta.png')
    page.wait_for_function('!TlamatiniCanvasEditing.busy && !TlamatiniCanvasEditing.dirty')
    assert b_destination.read_text(encoding='utf-8') == edited_b
    assert not page.evaluate('TlamatiniCanvasTabs.anyUnsaved()')
    checkpoint('both-documents-saved-independently')

    # The real endpoint writes its snapshot; withhold only delivery of its HTTP
    # response while the user types more and attempts to switch documents.
    activate(a_id)
    append('\n# snapshot requested')
    save_snapshot = text()
    delayed_saves = []

    def delay_save_response(route):
        response = route.fetch()
        assert response.ok, response.status
        assert destination.read_bytes() == save_snapshot.replace('\n', '\r\n').encode('utf-8-sig')
        assert page.evaluate('TlamatiniCanvasTabs.hasSaving()')
        append('\n# typed while saving')
        page.evaluate('(id) => { window.pendingSaveSwitch = TlamatiniCanvasTabs.activate(id); }', b_id)
        page.locator('#tlm-popup-host').wait_for()
        page.keyboard.press('Escape')
        assert not page.evaluate('window.pendingSaveSwitch')
        assert active() == a_id
        delayed_saves.append(text())
        route.fulfill(response=response)

    page.route('**/agent/canvas/save/', delay_save_response, times=1)
    try:
        with page.expect_response(lambda response: '/agent/canvas/save/' in response.url):
            page.locator('#canvas-save-button').click()
        page.wait_for_function('!TlamatiniCanvasEditing.busy')
    finally:
        page.unroute('**/agent/canvas/save/', delay_save_response)
    assert len(delayed_saves) == 1 and page.evaluate('TlamatiniCanvasEditing.dirty')
    assert text() == delayed_saves[0]
    edited_a = text()
    assert destination.read_bytes() == save_snapshot.replace('\n', '\r\n').encode('utf-8-sig')
    checkpoint('delayed-save-keeps-newer-edits-and-blocks-wrong-tab-adoption',
               fault_injection='Real save response held after disk write; real keyboard edit and tab-switch attempt.')
    page.locator('#canvas-save-button').click()
    page.wait_for_function('!TlamatiniCanvasEditing.busy && !TlamatiniCanvasEditing.dirty')
    assert destination.read_bytes() == edited_a.replace('\n', '\r\n').encode('utf-8-sig')

    old_bytes = destination.read_bytes()
    destination.write_bytes('External version for delayed refresh\r\n'.encode('utf-8-sig'))
    page.evaluate('''() => {
        const source = canvasSource, read = source.read;
        window.canvasLateRead = {source, read, waiting:false};
        source.read = async signal => {
            const file = await read(signal);
            return new Promise(resolve => {
                canvasLateRead.release = () => resolve(file);
                canvasLateRead.waiting = true;
            });
        };
    }''')
    try:
        page.locator('#reopen-canvas-button').click()
        page.wait_for_function('canvasLateRead.waiting && TlamatiniCanvasRefresh.busy')
        activate(b_id)
        page.evaluate('canvasLateRead.release()')
        page.wait_for_timeout(300)
        assert active() == b_id and text() == edited_b
        activate(a_id)
        assert text() == edited_a
    finally:
        page.evaluate('canvasLateRead.source.read = canvasLateRead.read')
        destination.write_bytes(old_bytes)
    checkpoint('late-refresh-cannot-overwrite-another-tab',
               fault_injection='Real file read held after completion and delivered after a tab switch.')

    native_open(page, window, pdf)
    pdf_id = active()
    frame = page.locator('#pdf-canvas-host iframe:visible').content_frame
    frame.locator('#pdf-zoom').select_option('1.5')
    frame.locator('#pdf-rotate').click()
    frame.locator('#pdf-scroll-mode').select_option('3')
    # Rotation changes page geometry in continuous mode. Establish the intended
    # final page after changing view controls, and verify this precondition.
    frame.locator('#pdf-page').fill('3')
    frame.locator('#pdf-page').press('Tab')
    page.wait_for_timeout(300)
    pdf_state_script = '''() => ({page:document.querySelector('#pdf-page').value,
        zoom:document.querySelector('#pdf-zoom').value,mode:document.querySelector('#pdf-scroll-mode').value,
        scroll:document.querySelector('#pdf-viewer-container').scrollTop})'''
    pdf_state_before = frame.locator('body').evaluate(pdf_state_script)
    assert pdf_state_before['page'] == '3', pdf_state_before
    assert pdf_state_before['zoom'] == '1.5', pdf_state_before
    assert pdf_state_before['mode'] == '3', pdf_state_before
    pdf_frame_url = frame.locator('body').evaluate('() => location.href')
    page.evaluate('window.retainedPdfFrame = document.querySelector("#pdf-canvas-host iframe")')
    activate(a_id)
    assert not page.locator('#pdf-canvas-host').is_visible()
    assert text() == edited_a
    activate(pdf_id)
    frame = page.locator('#pdf-canvas-host iframe:visible').content_frame
    page.wait_for_timeout(300)
    pdf_state_after = frame.locator('body').evaluate(pdf_state_script)
    assert pdf_state_after == pdf_state_before, {'before': pdf_state_before, 'after': pdf_state_after}
    assert frame.locator('body').evaluate('() => location.href') == pdf_frame_url
    assert page.evaluate('document.querySelector("#pdf-canvas-host iframe") === window.retainedPdfFrame')
    assert not page.locator('#editor-container').is_visible()
    checkpoint('pdf-view-page-zoom-and-mode-preserved-across-tabs',
               before=pdf_state_before, after=pdf_state_after)

    pdf_context_start = len(context_frames())
    page.locator('#context-button').click()
    page.locator('#pdf-context-progress').wait_for(state='visible')
    assert page.evaluate('TlamatiniCanvasTabs.contextPending')
    assert not page.evaluate('TlamatiniCanvasTabs.changeContext()')
    page.keyboard.press('Escape')
    page.wait_for_function('!TlamatiniCanvasTabs.contextPending')
    assert not page.locator('#pdf-context-progress').is_visible()
    assert len(context_frames()) == pdf_context_start, 'Canceled PDF preparation published a context selection.'
    assert set(page.evaluate('TlamatiniCanvasTabs.list().filter(item=>item.context).map(item=>item.document_id)')) == {a_id, b_id}
    checkpoint('cancelled-real-pdf-preparation-keeps-confirmed-context-and-releases-pending-state')

    verify_pdf_context_refresh(pdf, pdf_id)

    frame.locator('#pdf-viewer-container').click()
    frame.locator('#pdf-viewer-container').press('Alt+PageDown')
    page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() !== id', arg=pdf_id)
    assert active() == a_id
    # Negative protocol case: a hidden owned iframe must not navigate tabs.
    page.locator('#pdf-canvas-host iframe').content_frame.locator('body').evaluate('''() => {
        parent.postMessage({channel:'tlamatini-pdf-canvas',type:'canvas-document-cycle',direction:1},location.origin);
    }''')
    page.wait_for_timeout(200)
    assert active() == a_id
    activate(pdf_id)
    frame = page.locator('#pdf-canvas-host iframe:visible').content_frame
    checkpoint('focused-pdf-keyboard-cycle-and-hidden-iframe-isolation')

    window.resize(960, 760)
    page.wait_for_timeout(250)
    dimensions = page.evaluate('''() => {
        const bar = document.querySelector('#canvas-tabs').getBoundingClientRect();
        const panel = document.querySelector('#canvas-container').getBoundingClientRect();
        return {bar: {left:bar.left,right:bar.right,width:bar.width},
            panel: {left:panel.left,right:panel.right}, width:innerWidth};
    }''')
    assert dimensions['bar']['left'] >= dimensions['panel']['left'] - 2
    assert dimensions['bar']['right'] <= dimensions['width'] + 2
    assert tab(pdf_id).is_visible()
    checkpoint('narrow-window-keeps-active-tab-and-pdf-toolbar-accessible', dimensions=dimensions)
    window.resize(1440, 900)

    # The reliable Canvas-only shortcut is tested with real keyboard events.
    activate(a_id)
    source_view().click()
    page.keyboard.press('Alt+PageDown')
    page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() !== id', arg=a_id)
    keyboard_target = active()
    page.keyboard.press('Alt+PageUp')
    page.wait_for_function('(id) => TlamatiniCanvasTabs.activeId() === id', arg=a_id)
    page.locator('#chat-message-input').click()
    page.keyboard.press('Alt+PageDown')
    assert active() == a_id, 'Canvas shortcut escaped its focus boundary.'
    checkpoint('canvas-only-keyboard-navigation-leaves-chat-alone', forward=keyboard_target)

    shortcut_details = native_shortcut_checks(page, context, window, capture, attempt)
    checkpoint('native-windows-control-tab-and-canvas-only-fallback', **shortcut_details)

    # Exercise the actual authenticated Interactor socket, not a mocked command.
    activate(a_id)
    page.locator('#interactor-access').check()
    client_id = page.evaluate('TlamatiniInteractor.clientId')
    owner = hub.clients[client_id].owner
    user_id = int(owner[0])
    reset_for_tests(user_id)
    page.evaluate('TlamatiniInteractor.beforeChat()')
    request = Request(owner, client_id, user_id, begin_llm_run(user_id))

    def invoke(**arguments):
        token = current.set(request)
        try:
            return json.loads(perform(**arguments))
        finally:
            current.reset(token)

    with ThreadPoolExecutor(max_workers=1) as pool:
        def call(action, **arguments):
            future = pool.submit(invoke, action=action, **arguments)
            deadline = time.monotonic() + 45
            while not future.done() and time.monotonic() < deadline:
                page.wait_for_timeout(35)
            assert future.done(), f'Interactor action timed out: {action}'
            return future.result()

        first = call('read')
        assert first['ok'] and first['document_id'] == a_id, first
        listing = call('documents')
        assert listing['ok'] and listing['multi_document'], listing
        assert {item['document_id'] for item in listing['documents']} == {a_id, b_id, c_id, pdf_id}
        assert all('text' not in item and 'path' not in item and 'native' not in item
                   for item in listing['documents'])
        switched = call('activate', target_document_id=b_id)
        assert switched['ok'] and switched['verified'] and switched['snapshot']['document_id'] == b_id, switched
        assert active() == b_id and text() == edited_b
        before_a = destination.read_bytes()
        inserted = call('type', text='\n# Live explanation targets Beta', typing_wpm=250)
        assert inserted['ok'], inserted
        assert 'Live explanation targets Beta' in text()
        assert destination.read_bytes() == before_a
        stale = call('type', document_id=a_id, revision=first['revision'], text='WRONG DOCUMENT')
        assert not stale['ok'] and 'WRONG DOCUMENT' not in text(), stale
        checkpoint('live-interactor-lists-switches-and-edits-only-target-document')

    # Do not leave test edits unsaved; persistence remains visible and exact.
    final_b = text()
    page.locator('#canvas-save-button').click()
    page.wait_for_function('!TlamatiniCanvasEditing.busy && !TlamatiniCanvasEditing.dirty')
    assert b_destination.read_text(encoding='utf-8') == final_b
    assert not page.evaluate('TlamatiniCanvasTabs.anyUnsaved() || TlamatiniCanvasTabs.hasSaving()')
    checkpoint('all-opened-documents-persistent-no-pending-save')

    verify_interactor_open_from_pdf(pdf_id, a)

    # Close the actual captured chat WebSocket with an update still outstanding.
    # The following clean reload reconnects; the authenticated Interactor socket
    # is independent. A deliberately late acknowledgement must remain ignored.
    activate(c_id)
    interrupted_context = start_context()
    documents_before_disconnect = page.evaluate('TlamatiniCanvasTabs.list()')
    page.evaluate('chatSocket.close(1000, "Canvas context disconnect acceptance")')
    page.wait_for_function('chatSocket.readyState === WebSocket.CLOSED && !TlamatiniCanvasTabs.contextPending')
    assert page.locator('#chat-message-input').is_disabled()
    assert page.locator('#canvas-tabs .canvas-tab-context:visible').count() == 0
    assert page.locator('#canvas-context-documents [role="status"]').is_visible()
    deliver_chat_frame({'type': 'canvas-documents-context-result', 'request_id': interrupted_context['request_id'],
                        'success': True, 'documents': interrupted_context['documents']})
    documents_after_disconnect = page.evaluate('TlamatiniCanvasTabs.list()')
    assert page.locator('#chat-message-input').is_disabled()
    assert {item['document_id'] for item in documents_after_disconnect} == {item['document_id'] for item in documents_before_disconnect}
    assert all(not item['context'] and not item['dirty'] for item in documents_after_disconnect)
    assert text() == c.read_text(encoding='utf-8')
    checkpoint('real-chat-disconnect-keeps-documents-and-ignores-late-context-acknowledgement',
               transport='Actual WebSocket close; explicit late acknowledgement injection; source files remain unchanged.')

    # Real navigation now succeeds without a browser warning.
    clean_dialogs = []

    def unexpected_dialog(dialog):
        clean_dialogs.append(dialog.type)
        dialog.dismiss()

    page.on('dialog', unexpected_dialog)
    try:
        page.reload(wait_until='load')
    finally:
        page.remove_listener('dialog', unexpected_dialog)
    assert not clean_dialogs, clean_dialogs
    page.wait_for_function('window.TlamatiniCanvasTabs')
    checkpoint('clean-browser-navigation-is-not-blocked')

    # Leave the real four-document workspace open for Angela to inspect.
    page.evaluate('enableControlsAfterOperation()')
    for path in (destination, b_destination, c, pdf):
        native_open(page, window, path)
    assert page.locator('#canvas-tabs [role="tab"]').count() == 4

    duplicate_a, duplicate_b = fixtures / 'one/duplicate.txt', fixtures / 'two/duplicate.txt'
    for path, value in ((duplicate_a, 'First same-name document'), (duplicate_b, 'Second same-name document')):
        path.parent.mkdir(exist_ok=True)
        path.write_text(value, encoding='utf-8')
    native_open(page, window, duplicate_a)
    duplicate_a_id = active()
    native_open(page, window, duplicate_b)
    duplicate_b_id = active()
    assert duplicate_a_id != duplicate_b_id
    activate(duplicate_a_id)
    assert text() == 'First same-name document'
    activate(duplicate_b_id)
    assert text() == 'Second same-name document'
    checkpoint('identical-basenames-have-distinct-document-identities')
    assert page.evaluate('(id) => TlamatiniCanvasTabs.close(id)', duplicate_b_id)
    assert page.evaluate('(id) => TlamatiniCanvasTabs.close(id)', duplicate_a_id)
    assert page.locator('#canvas-tabs [role="tab"]').count() == 4
    checkpoint('final-four-document-workspace-ready-for-review', **prepare_review_workspace())
    return results


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(OUT)
    harness.OUT, harness.PORT, harness.BASE = OUT, PORT, BASE
    harness.canvas_test.OUT = OUT
    harness.__file__ = __file__
    return harness.main()


if __name__ == '__main__':
    raise SystemExit(main())
