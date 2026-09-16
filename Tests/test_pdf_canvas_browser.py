# Tlamatini Author Banner — Angela López Mendoza
"""Real Chromium PDF canvas regression, isolated from RAG, accounts and databases.

Run: python -m pytest Tests/test_pdf_canvas_browser.py -q
Set PDF_CANVAS_HEADED=1 to watch; PDF_CANVAS_SCREENSHOT names an optional PNG.
The harness uses the actual canvas markup, CSS and application JS, with only
the chat/socket globals stubbed. PDF parsing, workers and rendering are real.
"""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import threading
import time
import sys
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "Tlamatini/agent/static"
TEMPLATE = ROOT / "Tlamatini/agent/templates/agent/agent_page.html"
BOOTSTRAP = """
let contextEnabled = true, openEnabled = true, canvasSettedAsContext = false;
let contextButtonClicked = false, canvasLoaded = false, inLongOperation = false;
let clearContextEnabled = false, actualContextDir = null;
let titleBusyPrefix = '';
const filenameSpan = document.getElementById('filename');
const contextButton = document.getElementById('context-button');
const cleanCanvasButton = document.getElementById('clean-canvas-button');
const reopenOpenCanvasButton = document.getElementById('reopen-canvas-button');
const copyCanvasButton = document.getElementById('copy-canvas-button');
const saveAsButton = document.getElementById('save-as');
const lineNumbers = document.getElementById('line-numbers');
const textEditorPre = document.querySelector('#text-editor pre');
let textEditorCode = document.querySelector('#text-editor code');
const contextDataSpan = document.getElementById('context-data');
const contextInfoDiv = contextDataSpan.parentElement;
const clearContextButton = document.getElementById('clear-context');
const contextMobile = null, viewContextDirInCanvasMenu = null, openInDropdownItem = null;
const maximalTheoricTokens = 10000000;
const hljs = { highlightElement() {} };
const sentMessages = [];
function sendChatSocketMessage(value) {
    sentMessages.push(typeof value === 'string' ? JSON.parse(value) : value);
    return true;
}
function updateOpenInMenuState() {}
function getCsrfToken() { return 'test-token'; }
document.getElementById('open').addEventListener('click', () => openCanvas());
cleanCanvasButton.addEventListener('click', () => cleanCanvas());
reopenOpenCanvasButton.addEventListener('click', () => reopenCanvas());
window.addEventListener('DOMContentLoaded', () => rotateTitle());
"""


def make_pdf(path, pages=4, padding=0):
    """Valid vector/text PDF, optionally sparse and much larger than RAM reads."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        ("<< /Type /Pages /Count %d /Kids [%s] >>" % (
            pages, " ".join(f"{4 + number * 2} 0 R" for number in range(pages))
        )).encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for number in range(pages):
        stream = (
            "0.2 0.65 0.55 rg 40 200 300 180 re f "
            f"0 0 0 rg BT /F1 24 Tf 50 700 Td (PDF page {number + 1}) Tj ET"
        ).encode()
        rotation = 90 if number == 1 else 0
        objects.extend([
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Rotate {rotation} "
             f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + number * 2} 0 R >>").encode(),
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        ])
    if padding:
        objects.append(None)  # Valid, unreferenced large embedded stream.
    with path.open("wb") as output:
        output.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for number, obj in enumerate(objects, 1):
            offsets.append(output.tell())
            if obj is None:
                output.write(f"{number} 0 obj\n<< /Length {padding} >>\nstream\n".encode())
                output.seek(padding, 1)
                output.write(b"\nendstream\nendobj\n")
            else:
                output.write(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = output.tell()
        output.write(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            output.write(f"{offset:010} 00000 n \n".encode())
        output.write((f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                      f"startxref\n{xref}\n%%EOF\n").encode())


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from django.conf import settings
    if not settings.configured:
        settings.configure(SECRET_KEY="isolated-pdf-canvas-browser-tests", DEFAULT_CHARSET="utf-8")
        from django.core import mail
        mail.outbox = []
    sys.path.insert(0, str(ROOT / "Tlamatini"))
    from agent import pdf_context
    from agent import pdf_image_analysis
    from agent.pdf_context_views import prepare_pdf_context_view, pdf_context_status_view, cancel_pdf_context_view
    from django.core.handlers.wsgi import WSGIRequest
    package_root = tmp_path_factory.mktemp("pdf-context-packages")
    patcher = pytest.MonkeyPatch()
    patcher.setattr(pdf_context, 'get_runtime_agent_root', lambda: str(package_root))
    patcher.setattr(pdf_image_analysis, 'create_pdf_image_analyzer',
                    lambda: lambda path: (f'Visual analysis for {path.name}: green diagram.', 'merged'))
    template = TEMPLATE.read_text(encoding="utf-8")
    markup = template[template.index('    <div class="col-8 px-0" id="canvas-container">'):]
    markup = markup[:markup.index('  <div id="confirmation-dialog-message"')]
    markup = re.sub(r"{% static '([^']+)' %}", r"/\1", markup)
    markup = markup.replace("{{ STATIC_VERSION }}", "test")
    scripts = ["agent_page_ui", "agent_page_layout", "pdf_context_progress", "agent_page_pdf", "agent_page_canvas", "agent_page_context"]
    html = ("<!doctype html><meta charset='utf-8'><link rel='stylesheet' href='/agent/css/agent_page.css'>"
            "<link rel='stylesheet' href='/agent/css/pdf_context_progress.css'>"
            "<link rel='stylesheet' href='/test.css'><button id='open'>Open</button>"
            "<button id='save-as'>Save As</button><button id='clear-context'>Clear context</button>"
            "<div><span id='context-data'>&lt;&lt;&lt;...&gt;&gt;&gt;</span></div>"
            + markup + "<script src='/test.js'></script>"
            + "".join(f"<script src='/agent/js/{name}.js'></script>" for name in scripts))
    # Add both real divider elements and the real layout module around the
    # canvas; only the chat contents/services are replaced by a small fixture.
    layout_prefix = (
        '<div id="chat-container"><div id="main-chat-container">'
        '<div id="subchat-container"><div id="chat-log">Chat history</div>'
        '<div id="vertical-drag-divider" tabindex="0"></div>'
        '<div id="tools-chat-form-container"><div id="tools-div">Chat tools</div>'
        '<textarea aria-label="Chat message"></textarea></div></div></div>'
        '<div id="drag-divider" tabindex="0"></div>'
    )
    layout_html = html.replace(markup, layout_prefix + markup).replace(
        "href='/test.css'", "href='/layout.css'")

    class Handler(SimpleHTTPRequestHandler):
        # Match the app's explicit Django/WhiteNoise MIME configuration, including
        # Windows hosts whose registry associates .mjs with text/plain.
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                          '.mjs': 'text/javascript', '.wasm': 'application/wasm'}

        def do_POST(self):
            # Exercise real multipart parsing, disk extraction and signed context
            # preparation; isolate only authentication from the live user database.
            request = WSGIRequest({
                'REQUEST_METHOD': 'POST', 'PATH_INFO': self.path,
                'CONTENT_TYPE': self.headers['Content-Type'],
                'CONTENT_LENGTH': self.headers['Content-Length'],
                'wsgi.input': self.rfile, 'wsgi.url_scheme': 'http',
                'SERVER_NAME': '127.0.0.1', 'SERVER_PORT': str(self.server.server_port),
            })
            request.user = SimpleNamespace(pk=7, is_authenticated=True)
            response = (cancel_pdf_context_view(request) if self.path == '/agent/cancel_pdf_context/'
                        else prepare_pdf_context_view(request))
            self.send_response(response.status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response.content)
            request.close()

        def do_GET(self):
            if self.path.startswith('/agent/pdf_context_status/'):
                from django.test import RequestFactory
                request = RequestFactory().get(self.path)
                request.user = SimpleNamespace(pk=7)
                response = pdf_context_status_view(request)
                self.send_response(response.status_code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response.content)
                return
            payloads = {
                "/": ("text/html", html), "/test.js": ("text/javascript", BOOTSTRAP),
                "/layout": ("text/html", layout_html),
                "/test.css": ("text/css", "body{height:100vh;margin:0}.row{display:flex}#canvas-container{height:88vh;width:100%}"),
                "/layout.css": ("text/css", "body{height:100vh;margin:0}.row{display:flex}#chat-container{height:90vh}#main-chat-container{width:45%}#canvas-container{width:55%}"),
            }
            if self.path in payloads:
                content_type, text = payloads[self.path]
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(text.encode())
            else:
                super().do_GET()

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=STATIC))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()
    thread.join()
    patcher.undo()


@pytest.fixture
def browser_page(server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=os.environ.get("PDF_CANVAS_HEADED") != "1")
        context = browser.new_context(viewport={"width": 1280, "height": 960},
                                      permissions=["clipboard-read", "clipboard-write"])
        # Count genuine byte reads inside the viewer; reject external dependencies.
        context.add_init_script("""
            window.pdfRangeReads = [];
            const read = Blob.prototype.arrayBuffer;
            Blob.prototype.arrayBuffer = function() {
                window.pdfRangeReads.push(this.size);
                return read.call(this);
            };
        """)
        external = []
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(server)
                      else (external.append(route.request.url), route.abort()))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(server)
        yield page
        assert not errors, errors
        assert not external, external
        browser.close()


def choose(page, path, button="Open"):
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name=button, exact=True).click()
    assert ".pdf" in chooser.value.element.get_attribute("accept")
    chooser.value.set_files(str(path))


def pdf_frame(page):
    return page.frame_locator("#pdf-canvas-host iframe")


def rendered(page, number):
    frame = pdf_frame(page)
    expect(frame.locator(f'.page[data-page-number="{number}"] canvas').first).to_be_visible(timeout=60000)
    expect(frame.locator(f'.page[data-page-number="{number}"]')).to_have_attribute("data-loaded", "true", timeout=60000)
    expect(frame.locator(f'.page[data-page-number="{number}"]')).not_to_have_class(re.compile(r"\bloading\b"), timeout=60000)


def jump(page, number):
    field = pdf_frame(page).get_by_role("spinbutton", name="Page")
    field.fill(str(number))
    field.press("Tab")
    rendered(page, number)


def continue_context(page, process_images=False):
    expect(page.locator('#pdf-context-progress')).to_be_visible()
    expect(page.get_by_label('Process images', exact=True)).not_to_be_checked()
    if process_images:
        page.get_by_label('Process images', exact=True).check()
    page.get_by_role('button', name='Continue', exact=True).click()


def prepare_payload(page, process_images=False):
    page.evaluate('''() => {
        window.testPdfPayload = getCanvasContextPayload();
        window.testPdfPayload.catch(() => {});
    }''')
    continue_context(page, process_images)
    return page.evaluate('window.testPdfPayload')


def finish_context(page, token):
    # The consumer completion message is tested separately with the real receive
    # method; isolate the browser from the user's configured RAG model services.
    expect(page.locator('#pdf-context-progress')).to_be_visible()
    expect(page.locator('[data-pdf-stage="rag"]')).to_have_attribute('data-state', 'active')
    expect(page).to_have_title(re.compile('^⏳ '))
    # Normal chat messages must not prematurely clear the PDF activity marker.
    page.evaluate('setTitleBusy(false)')
    expect(page).to_have_title(re.compile('^⏳ '))
    page.evaluate("TlamatiniPdfProgress.finish('stale-job-token', true)")
    expect(page.locator('#pdf-context-progress')).to_be_visible()
    page.evaluate("token => TlamatiniPdfProgress.finish(token, true)", token)
    expect(page.locator('#pdf-context-progress-message')).to_contain_text('context is ready')
    expect(page.locator('#pdf-context-progress')).not_to_be_visible()
    expect(page).not_to_have_title(re.compile('^⏳ '))


def test_divider_releases_drag_over_pdf_frame(browser_page, server, tmp_path):
    page = browser_page
    page.set_viewport_size({'width': 1600, 'height': 1000})
    page.goto(server + '/layout')
    pdf = tmp_path / 'resizing.pdf'
    make_pdf(pdf, pages=2)
    choose(page, pdf)
    rendered(page, 1)
    handle = page.locator('#drag-divider')
    bounds = handle.bounding_box()
    y = bounds['y'] + bounds['height'] / 2
    initial_width = page.locator('#main-chat-container').bounding_box()['width']
    page.mouse.move(bounds['x'] + 4, y)
    page.mouse.down()
    # Jump directly over the embedded document, where parent-window mouse
    # move/up listeners used to lose the stream and leave resizing latched.
    page.mouse.move(1400, y)
    page.mouse.up()
    expect(page.locator('body')).not_to_have_class(re.compile(r'\bresizing\b'))
    assert page.locator('#main-chat-container').bounding_box()['width'] > initial_width + 200
    bounds = handle.bounding_box()
    page.mouse.move(bounds['x'] + 4, y)
    page.mouse.down()
    page.mouse.move(480, y)
    page.mouse.up()
    width = page.locator('#main-chat-container').bounding_box()['width']
    assert abs(width - 480) < 2
    page.mouse.move(1200, y)
    assert page.locator('#main-chat-container').bounding_box()['width'] == width
    # Normal PDF interaction must resume immediately after releasing the handle.
    jump(page, 1)
    pdf_frame(page).get_by_role('button', name='Next page', exact=True).click()
    rendered(page, 2)


def test_dividers_recover_from_focus_loss_and_touch_cancel(browser_page, server, tmp_path):
    page = browser_page
    page.set_viewport_size({'width': 1600, 'height': 1000})
    page.goto(server + '/layout')
    pdf = tmp_path / 'interrupted-resize.pdf'
    make_pdf(pdf, pages=2)
    choose(page, pdf)
    rendered(page, 1)
    touch = page.context.new_cdp_session(page)
    for selector, dragging, key in [('#drag-divider', 'resizing', 'ArrowLeft'),
                                   ('#vertical-drag-divider', 'resizing-vertical', 'ArrowUp')]:
        handle = page.locator(selector)
        bounds = handle.bounding_box()
        x, y = bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 10, y + 10)
        expect(page.locator('body')).to_have_class(re.compile(dragging))
        page.evaluate("window.dispatchEvent(new Event('blur'))")
        expect(page.locator('body')).not_to_have_class(re.compile(dragging))
        page.mouse.up()
        # Exercise real Chromium touch/pointer cancellation, not synthetic mouse
        # events. Both handles must release their capture and iframe shielding.
        bounds = handle.bounding_box()
        x, y = bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2
        touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
        touch.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': 1300, 'y': 400}]})
        expect(page.locator('body')).to_have_class(re.compile(dragging))
        touch.send('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []})
        expect(page.locator('body')).not_to_have_class(re.compile(dragging))
        assert page.locator('#pdf-canvas-host iframe').evaluate("el => getComputedStyle(el).pointerEvents") == 'auto'
        # Keep the established keyboard adjustment working after interruptions.
        previous = page.locator('#main-chat-container' if selector == '#drag-divider' else '#chat-log').bounding_box()
        handle.press(key)
        current = page.locator('#main-chat-container' if selector == '#drag-divider' else '#chat-log').bounding_box()
        assert current != previous
    jump(page, 1)
    pdf_frame(page).get_by_role('button', name='Next page', exact=True).click()
    rendered(page, 2)
    touch.detach()


def test_complete_pdf_navigation_text_save_and_switching(browser_page, tmp_path):
    page = browser_page
    pdf = tmp_path / "Complete report.PDF"
    make_pdf(pdf, pages=24)
    choose(page, pdf)
    rendered(page, 1)
    expect(page.locator("#filename")).to_have_text("<<< Complete report.PDF >>>")
    expect(pdf_frame(page).locator("#pdf-page-count")).to_have_text("of 24")
    for number in [2, 12, 24, 1]:
        jump(page, number)
    pdf_frame(page).get_by_label("Zoom").select_option("2")
    pdf_frame(page).get_by_role("button", name="Rotate", exact=True).click()
    page.set_viewport_size({"width": 850, "height": 760})
    pdf_frame(page).get_by_label("Zoom").select_option("page-width")
    text = page.evaluate("getCanvasText()")
    assert "PDF page 1" in text and "PDF page 24" in text
    page.locator("#copy-canvas-button").click()
    expect(page.locator("#copy-canvas-button")).to_have_text("Copied!")
    assert "PDF page 24" in page.evaluate("navigator.clipboard.readText()")
    page.locator("#context-button").click()
    continue_context(page, process_images=True)
    page.wait_for_function("sentMessages.some(m => m.type === 'set-pdf-canvas-as-context')")
    from agent.pdf_context import resolve_pdf_context
    package, filename = resolve_pdf_context(page.evaluate("sentMessages.at(-1).context_token"), 7)
    assert "PDF page 24" in (package / filename).read_text(encoding="utf-8")
    assert len(list((package / 'images').glob('page_*.png'))) == 24
    assert page.evaluate("sentMessages.at(-1).message") == "Complete report.PDF"
    finish_context(page, page.evaluate("sentMessages.at(-1).context_token"))
    page.evaluate("contextEnabled = true; openEnabled = true")
    # Chat completion resets this flag. PDF synchronization must restore the
    # existing unset-context toggle, including after subsequent chat turns.
    page.evaluate('contextButtonClicked = false; TlamatiniPdfCanvas.syncButtons()')
    page.locator('#context-button').click()
    assert page.evaluate('sentMessages.at(-1).type') == 'unset-canvas-as-context'
    assert page.evaluate('sentMessages.at(-1).message') == 'document.txt'
    page.locator('#context-button').click()
    continue_context(page, process_images=True)
    page.wait_for_function("sentMessages.at(-1).type === 'set-pdf-canvas-as-context'")
    finish_context(page, page.evaluate('sentMessages.at(-1).context_token'))
    page.evaluate('contextEnabled = true; openEnabled = true; TlamatiniPdfCanvas.syncButtons()')
    page.once("dialog", lambda dialog: dialog.accept("saved-report.pdf"))
    with page.expect_download() as download:
        page.get_by_role("button", name="Save As", exact=True).click()
    assert Path(download.value.path()).read_bytes() == pdf.read_bytes()
    if os.environ.get("PDF_CANVAS_SCREENSHOT"):
        page.screenshot(path=os.environ["PDF_CANVAS_SCREENSHOT"])
    txt = tmp_path / "source.py"
    txt.write_text("print('text restored')\n", encoding="utf-8")
    choose(page, txt, "Reopen")
    expect(page.locator("#text-editor code")).to_have_text("print('text restored')")
    expect(page.locator("#pdf-canvas-host iframe")).to_have_count(0)
    page.wait_for_function("sentMessages.at(-1).type === 'set-canvas-as-context'")
    page.evaluate('contextEnabled = true; openEnabled = true')
    choose(page, pdf, "Reopen")
    rendered(page, 1)
    continue_context(page, process_images=True)
    page.wait_for_function("sentMessages.at(-1).type === 'set-pdf-canvas-as-context'")
    finish_context(page, page.evaluate("sentMessages.at(-1).context_token"))
    page.evaluate("contextEnabled = true; openEnabled = true")
    page.get_by_role("button", name="Clear canvas", exact=True).click()
    expect(page.locator("#filename")).to_have_text("<<<...>>>")
    expect(page.locator("#pdf-canvas-host iframe")).to_have_count(0)


def test_large_file_reads_ranges_instead_of_whole_file(browser_page, tmp_path):
    pdf = tmp_path / "large.pdf"
    make_pdf(pdf, pages=3, padding=256 * 1024 * 1024)
    choose(browser_page, pdf)
    rendered(browser_page, 1)
    jump(browser_page, 3)
    reads = browser_page.frames[1].evaluate("pdfRangeReads")
    assert reads and max(reads) <= 1024 * 1024, reads
    assert sum(reads) < 8 * 1024 * 1024, reads


def test_image_option_waits_for_continue_and_caches_modes_separately(browser_page, tmp_path, monkeypatch):
    from agent import pdf_image_analysis
    from agent.pdf_context import resolve_pdf_context

    page = browser_page
    calls, requests = [], []
    def analyze(path):
        calls.append(path.name)
        return 'Visual content described.', 'merged'
    monkeypatch.setattr(pdf_image_analysis, 'create_pdf_image_analyzer', lambda: analyze)
    page.on('request', lambda request: requests.append(request.url) if 'pdf_context' in request.url else None)
    pdf = tmp_path / 'Choose processing.pdf'
    make_pdf(pdf, pages=3)
    choose(page, pdf)
    rendered(page, 1)
    for dismissal in ('cancel', 'escape', 'close'):
        page.locator('#context-button').click()
        option = page.get_by_label('Process images', exact=True)
        expect(option).not_to_be_checked()
        expect(page.get_by_role('button', name='Continue', exact=True)).to_be_visible()
        expect(page).not_to_have_title(re.compile('^⏳ '))
        expect(page.locator('#pdf-context-progress-elapsed')).to_have_text('0:00')
        if os.environ.get('PDF_OPTIONS_SCREENSHOT') and dismissal == 'cancel':
            page.screenshot(path=os.environ['PDF_OPTIONS_SCREENSHOT'])
        option.check()
        assert not calls and not requests
        if dismissal == 'cancel':
            page.locator('#pdf-context-progress-action').click()
        elif dismissal == 'escape':
            page.keyboard.press('Escape')
        else:
            page.locator('#pdf-context-progress').evaluate('dialog => dialog.close()')
        expect(page.locator('#pdf-context-progress')).not_to_be_visible()
        expect(page.locator('#context-button')).to_be_enabled()
        assert not requests  # Dismissing the choice needs no backend job, even a cancellation job.
        assert not page.evaluate('sentMessages.length')

    text_payload = prepare_payload(page)
    package, filename = resolve_pdf_context(text_payload['context_token'], 7)
    assert 'PDF page 3' in (package / filename).read_text(encoding='utf-8')
    assert not (package / 'images').exists()
    assert not calls
    expect(page.locator('[data-pdf-stage="analyze"] output')).to_have_text('Skipped')
    finish_context(page, text_payload['context_token'])

    image_payload = prepare_payload(page, process_images=True)
    assert image_payload['context_token'] != text_payload['context_token']
    package, filename = resolve_pdf_context(image_payload['context_token'], 7)
    assert 'Visual content described.' in (package / filename).read_text(encoding='utf-8')
    assert len(calls) == 3
    finish_context(page, image_payload['context_token'])
    # Returning to unchecked/text-only must reuse only that mode's prepared file.
    cached_text = prepare_payload(page)
    assert cached_text['context_token'] == text_payload['context_token']
    assert len([url for url in requests if '/prepare_pdf_context/' in url]) == 2
    finish_context(page, cached_text['context_token'])


def test_progress_cancel_and_retry_with_image_warning(browser_page, tmp_path, monkeypatch):
    from agent import pdf_image_analysis
    from agent.pdf_context_jobs import job_status

    page = browser_page
    entered, release = threading.Event(), threading.Event()
    def analyze(path):
        entered.set()
        release.wait(15)
        return 'Only one vision model was available.', 'partial_interpreter_1_only'
    monkeypatch.setattr(pdf_image_analysis, 'create_pdf_image_analyzer', lambda: analyze)
    pdf = tmp_path / 'Illustrated report.pdf'
    make_pdf(pdf, pages=2)
    choose(page, pdf)
    rendered(page, 1)
    try:
        with page.expect_response('**/agent/prepare_pdf_context/') as uploaded:
            page.locator('#context-button').click()
            continue_context(page, process_images=True)
        token = uploaded.value.json()['job']
        assert entered.wait(5)
        expect(page).to_have_title(re.compile('^⏳ '))
        expect(page.locator('#pdf-context-progress')).to_be_visible()
        expect(page.locator('#pdf-context-progress-file')).to_have_text(pdf.name)
        expect(page.locator('[data-pdf-stage="analyze"]')).to_have_attribute('data-state', 'active')
        expect(page.locator('[data-pdf-stage="extract"] output')).to_have_text('Done')
        expect(page.locator('#pdf-context-progress-elapsed')).not_to_have_text('0:00', timeout=5000)
        if os.environ.get('PDF_PROGRESS_SCREENSHOT'):
            page.screenshot(path=os.environ['PDF_PROGRESS_SCREENSHOT'])
        page.set_viewport_size({'width': 420, 'height': 760})
        bounds = page.locator('#pdf-context-progress').bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= 420
        page.evaluate('setTitleBusy(true)')
        with page.expect_response('**/agent/cancel_pdf_context/'):
            page.locator('#pdf-context-progress-action').click()
        expect(page.locator('#pdf-context-progress')).not_to_be_visible()
        # Cancelling PDF work must not erase an independent chat busy state.
        expect(page).to_have_title(re.compile('^⏳ '))
        page.evaluate('setTitleBusy(false)')
        expect(page).not_to_have_title(re.compile('^⏳ '))
        expect(page.locator('#context-button')).to_be_enabled()
        assert not page.evaluate("sentMessages.some(m => m.type === 'set-pdf-canvas-as-context')")
        rendered(page, 1)
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while job_status(token, 7)['status'] == 'pending' and time.monotonic() < deadline:
        time.sleep(0.01)
    assert job_status(token, 7)['status'] == 'cancelled'
    # Retry the same open PDF; the previous cancellation must not affect it.
    page.locator('#context-button').click()
    continue_context(page, process_images=True)
    page.wait_for_function("sentMessages.some(m => m.type === 'set-pdf-canvas-as-context')")
    expect(page.locator('#pdf-context-progress-message')).to_contain_text('2 image analyses were incomplete')
    finish_context(page, page.evaluate('sentMessages.at(-1).context_token'))


def test_preparation_failure_stays_visible_without_changing_context(browser_page, tmp_path, monkeypatch):
    from agent import pdf_image_analysis

    def unavailable_config():
        raise ValueError('Image-Interpreter configuration is unavailable.')
    monkeypatch.setattr(pdf_image_analysis, 'create_pdf_image_analyzer', unavailable_config)
    pdf = tmp_path / 'report.pdf'
    make_pdf(pdf, pages=1)
    choose(browser_page, pdf)
    rendered(browser_page, 1)
    browser_page.locator('#context-button').click()
    continue_context(browser_page, process_images=True)
    expect(browser_page.locator('#pdf-context-progress-message')).to_contain_text('configuration is unavailable')
    expect(browser_page.locator('#pdf-context-progress-action')).to_have_text('Close')
    expect(browser_page).not_to_have_title(re.compile('^⏳ '))
    assert not browser_page.evaluate("sentMessages.some(m => m.type === 'set-pdf-canvas-as-context')")
    browser_page.locator('#pdf-context-progress-action').click()
    expect(browser_page.locator('#context-button')).to_be_enabled()
    rendered(browser_page, 1)


def test_progress_close_and_failures_keep_correct_title_state(browser_page, tmp_path):
    page = browser_page
    pdf = tmp_path / 'lifecycle.pdf'
    make_pdf(pdf, pages=1)
    choose(page, pdf)
    rendered(page, 1)
    payload = prepare_payload(page)
    page.locator('#pdf-context-progress-action').click()
    expect(page.locator('#pdf-context-progress')).not_to_be_visible()
    expect(page).to_have_title(re.compile('^⏳ '))
    page.evaluate('token => TlamatiniPdfProgress.finish(token, true)', payload['context_token'])
    expect(page).not_to_have_title(re.compile('^⏳ '))
    # A failed RAG setup remains readable; successful completion alone auto-closes.
    payload = prepare_payload(page)
    page.evaluate('token => TlamatiniPdfProgress.finish(token, false)', payload['context_token'])
    expect(page.locator('#pdf-context-progress')).to_be_visible()
    expect(page.locator('#pdf-context-progress-message')).to_contain_text('context loading failed')
    expect(page).not_to_have_title(re.compile('^⏳ '))
    page.locator('#pdf-context-progress-action').click()
    payload = prepare_payload(page)
    page.evaluate('TlamatiniPdfProgress.connectionLost()')
    expect(page.locator('#pdf-context-progress-message')).to_contain_text('connection was lost')
    expect(page).not_to_have_title(re.compile('^⏳ '))
    page.locator('#pdf-context-progress-action').click()


def test_every_page_of_very_long_document_is_reachable(browser_page, tmp_path):
    pdf = tmp_path / "10001-pages.pdf"
    make_pdf(pdf, pages=10001)
    choose(browser_page, pdf)
    rendered(browser_page, 1)
    expect(pdf_frame(browser_page).locator("#pdf-page-count")).to_have_text("of 10001")
    jump(browser_page, 10001)
    expect(pdf_frame(browser_page).locator('.page[data-page-number="10001"] .textLayer')).to_contain_text("PDF page 10001")
    jump(browser_page, 5000)
    jump(browser_page, 1)
    assert pdf_frame(browser_page).locator("canvas").count() <= 12


def test_corrupt_password_and_cancelled_load(browser_page, tmp_path):
    import pymupdf

    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"This is not a PDF")
    choose(browser_page, bad)
    expect(pdf_frame(browser_page).locator("#pdf-status")).to_contain_text("Unable to open PDF", timeout=60000)
    expect(browser_page.locator("#context-button")).to_be_disabled()
    browser_page.evaluate("enableCanvasButtons()")
    expect(browser_page.locator("#context-button")).to_be_disabled()
    plain = tmp_path / "plain.pdf"
    protected = tmp_path / "protected.pdf"
    make_pdf(plain)
    with pymupdf.open(plain) as document:
        document.save(protected, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                      owner_pw="owner", user_pw="secret")
    choose(browser_page, protected, "Reopen")
    frame = pdf_frame(browser_page)
    expect(frame.locator("#pdf-password-form")).to_be_visible(timeout=60000)
    frame.locator("#pdf-password").fill("wrong")
    frame.get_by_role("button", name="Unlock").click()
    expect(frame.locator("#pdf-password-label")).to_contain_text("Incorrect")
    frame.locator("#pdf-password").fill("secret")
    frame.get_by_role("button", name="Unlock").click()
    rendered(browser_page, 1)
    payload = prepare_payload(browser_page)
    assert payload['type'] == 'set-pdf-canvas-as-context'
    finish_context(browser_page, payload['context_token'])
    choose(browser_page, protected, "Reopen")
    expect(pdf_frame(browser_page).locator("#pdf-password-form")).to_be_visible(timeout=60000)
    browser_page.get_by_role("button", name="Clear canvas", exact=True).click()
    expect(browser_page.locator("#pdf-canvas-host iframe")).to_have_count(0)
    choose(browser_page, plain)
    rendered(browser_page, 1)


def test_scanned_page_and_stale_text_read(browser_page, tmp_path):
    import pymupdf

    vector = tmp_path / "vector.pdf"
    scanned = tmp_path / "scanned.pdf"
    make_pdf(vector, pages=1)
    with pymupdf.open(vector) as source, pymupdf.open() as document:
        image = source[0].get_pixmap().tobytes("png")
        page = document.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=image)
        document.save(scanned)
    # A previous asynchronous text read must not overwrite a later PDF selection.
    browser_page.evaluate("""() => {
        const file = new File(['late text'], 'old.txt');
        file.text = () => new Promise(resolve => { window.finishOldRead = resolve; });
        void loadSelectedCanvasFile(file);
    }""")
    choose(browser_page, scanned)
    rendered(browser_page, 1)
    browser_page.evaluate("finishOldRead('late text')")
    expect(browser_page.locator("#filename")).to_have_text("<<< scanned.pdf >>>")
    # Inspect actual raster pixels, not just the presence of a canvas element.
    pixels = pdf_frame(browser_page).locator("canvas").first.evaluate("""canvas => {
        const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        let green = 0;
        for (let i = 0; i < pixels.length; i += 4) {
            if (pixels[i + 1] > pixels[i] + 50 && pixels[i + 3] > 0) green++;
        }
        return green;
    }""")
    assert pixels > 1000
    message = browser_page.evaluate("getCanvasText().catch(error => error.message)")
    assert "OCR" in message
    expect(pdf_frame(browser_page).locator("canvas").first).to_be_visible()
    # Text-only mode cannot silently produce an empty context from scanned pages.
    browser_page.locator('#context-button').click()
    continue_context(browser_page)
    expect(browser_page.locator('#pdf-context-progress-message')).to_contain_text('Enable Process images')
    browser_page.locator('#pdf-context-progress-action').click()
    # Scanned PDFs can still be used as context: all their visual artifacts are
    # passed to RAG for the normal Image-Interpreter/tool workflow.
    payload = prepare_payload(browser_page, process_images=True)
    from agent.pdf_context import resolve_pdf_context
    package, filename = resolve_pdf_context(payload['context_token'], 7)
    context = (package / filename).read_text(encoding="utf-8")
    assert "Page image:" in context and "Embedded image:" in context
