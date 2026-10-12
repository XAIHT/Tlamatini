# Tlamatini Author Banner — Angela López Mendoza
"""Markdown canvas acceptance on the real source page, in visible Chrome only.

Launch from a verified foreground PowerShell -NoExit console. Never headless.
Uses an isolated database in Temp/markdown-canvas-visible; no model requests.
Shoter captures the entire desktop at every checkpoint. Inspect browser-waiting.png
before creating browser-visible-confirmed. Results and Chrome stay open for review.
Create rerun.confirmed to repeat after a repair, or close.confirmed to end the run.
"""
import asyncio
import html
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/markdown-canvas-visible'
BASE = 'http://127.0.0.1:8875'


def visible_console():
    import ctypes
    import win32api
    import win32con
    import win32gui
    import win32process
    kernel = ctypes.windll.kernel32
    title_buffer = ctypes.create_unicode_buffer(32768)
    if not kernel.GetConsoleTitleW(title_buffer, len(title_buffer)):
        raise RuntimeError('This workload has no identifiable console. No workload will run.')
    console_title = title_buffer.value
    if not console_title.startswith('Tlamatini'):
        raise RuntimeError('Start this workload in its named Tlamatini development console.')
    windows = []
    win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd) if (
        console_title in win32gui.GetWindowText(hwnd)
        and win32gui.IsWindowVisible(hwnd)) else None, None)
    if not windows:
        raise RuntimeError('No verified visible development console. No workload will run.')
    # Prefer the console actually hosting this workload when several visible
    # development consoles are open.
    console = kernel.GetConsoleWindow()
    if console in windows:
        hwnd = console
    elif len(windows) == 1:
        hwnd = windows[0]
    else:
        raise RuntimeError('Multiple consoles have this workload title; give them distinct titles before running.')
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    other, _ = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
    own = win32api.GetCurrentThreadId()
    try:
        if own != other:
            win32process.AttachThreadInput(own, other, True)
        if win32gui.GetForegroundWindow() != hwnd:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        win32gui.SetForegroundWindow(hwnd)
    finally:
        if own != other:
            win32process.AttachThreadInput(own, other, False)
    cloaked = ctypes.c_int()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 14, ctypes.byref(cloaked), 4)
    if win32gui.GetForegroundWindow() != hwnd or cloaked.value or win32gui.IsIconic(hwnd):
        raise RuntimeError('Development console is not visible in the foreground. Refusing execution.')
    # Selecting console text must not silently suspend a long validation run.
    mode = ctypes.c_ulong()
    kernel = ctypes.windll.kernel32
    kernel.GetStdHandle.restype = ctypes.c_void_p
    handle = kernel.GetStdHandle(-10)
    if kernel.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)):
        kernel.SetConsoleMode(ctypes.c_void_p(handle), (mode.value | 0x80) & ~0x40)
    print('VISIBLE CONSOLE VERIFIED:', win32gui.GetWindowText(hwnd), win32gui.GetWindowRect(hwnd), flush=True)


SAMPLE = '''# Markdown in Tlamatini

The same familiar canvas, with **bold**, *italic*, ~~strikethrough~~ and `inline code`.
Español: áéíóú, ñ, Angela. 日本語. 🦋

[Jump to code](#code-and-escaping) · [Reference link][docs]

## Tables and alignment

| Feature | Status | Count |
| :--- | :---: | ---: |
| **Rich text** | Ready | 12 |
| Lists and tables | Ready | 24 |

## Lists and tasks

1. Open a Markdown file.
   - Preview the full document.
   - Keep **nested formatting**.
2. Save the original source.

- [x] Render the document
- [ ] Review the source

> A quote can contain **formatting**.
>
> - And a nested list.

## Code and escaping

```python
def greet(name):
    return f"Hello, {name}!"
```

```html
<script>window.markdownExecuted = true;</script>
```

    indented code <literal>

Escaped: \\*literal asterisks\\*, &amp;, <https://example.com>.

### Third-level heading
#### Fourth-level heading
##### Fifth-level heading
###### Sixth-level heading

Setext heading
--------------

---

<details><summary>Expandable details</summary>

Full details with **Markdown** inside.

</details>

![Local illustration](images/illustration.svg)

[docs]: https://example.com/docs "Reference documentation"

## Final section

END OF DOCUMENT — complete content.
'''


def fixtures():
    folder = OUT / 'fixtures'
    (folder / 'images').mkdir(parents=True, exist_ok=True)
    (folder / 'Showcase.MD').write_bytes(b'\xef\xbb\xbf' + SAMPLE.replace('\n', '\r\n').encode())
    (folder / 'images/illustration.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="180" viewBox="0 0 720 180">'
        '<rect width="720" height="180" rx="16" fill="#242c38"/>'
        '<circle cx="90" cy="90" r="45" fill="#55bbaa"/>'
        '<text x="170" y="103" font-family="sans-serif" font-size="30" fill="#edf2f7">Markdown · Tlamatini</text></svg>', encoding='utf-8')
    (folder / 'empty.md').write_text('', encoding='utf-8')
    (folder / 'Guía de Angela.md').write_text('# Contexto completo\n\n**Texto original** con ñ.', encoding='utf-8')
    (folder / 'linked.md').write_text('# Linked document\n\n![Same image](images/illustration.svg)\n\n[Next](nested/next.md)', encoding='utf-8')
    (folder / 'nested').mkdir(exist_ok=True)
    (folder / 'nested/next.md').write_text('# Nested document\n\n![Relative image](../images/illustration.svg)\n\n[Back](../linked.md)', encoding='utf-8')
    (folder / 'plain.txt').write_text('# This stays literal\n**source text**', encoding='utf-8')
    (folder / 'sample.py').write_text('def greet(name):\n    return name\n', encoding='utf-8')
    (folder / 'long.markdown').write_text('# Complete long file\n\n' + '\n\n'.join(
        f'## Section {i}\n\nParagraph {i}: readable text, **bold** and Unicode ñ.' for i in range(1, 501))
        + '\n\nLONG_DOCUMENT_END', encoding='utf-8')
    (folder / 'hostile.md').write_text('''# Safe document

<script>window.markdownExecuted = true</script>
<img src="javascript:alert(1)" onerror="window.markdownExecuted=true">
<svg onload="window.markdownExecuted=true"><script>alert(1)</script></svg>
<iframe srcdoc="<script>alert(1)</script>"></iframe>
<style>body{display:none}</style>
<form id="chat-form"><input name="action" autofocus></form>
<div class="ui-widget-overlay" style="position:fixed;inset:0">Visible safe text</div>
[Unsafe](javascript:alert(1))
<a href="jav&#x61;script:alert(1)">Entity attack</a>
<a href="/agent/logout/">Local route must not run</a>
<h2 id="chat-message-input">Scoped ID</h2>

SAFE_END
''', encoding='utf-8')
    import fitz
    pdf = fitz.open()
    pdf.new_page().insert_text((60, 80), 'PDF canvas regression: still rendered.')
    pdf.save(folder / 'sample.pdf')
    pdf.close()
    return folder


def checks(page, context, window, capture, sent, errors, folder, attempt):
    # Refresh assets after an in-place repair before any browser assertions.
    visible_console()
    from django.core.management import call_command
    from build_runtime_assets import verify_collected_static
    import py_compile
    import subprocess
    call_command('collectstatic', interactive=False, verbosity=0)
    verify_collected_static(ROOT)
    subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
    for name in ('scripts/markdown_canvas_visible.py', 'scripts/vendor_frontend.py',
                 'build_runtime_assets.py', 'copy_source_assets.py'):
        py_compile.compile(str(ROOT / name), doraise=True)
    print('Diff whitespace and Python syntax: PASS', flush=True)
    window.activate()
    report = OUT / f'run-{attempt}'
    report.mkdir(exist_ok=True)
    results = []
    doc = page.locator('#markdown-canvas-document')

    def checkpoint(name, assertion):
        assertion()
        window.verify()
        photo, _ = capture(f'run-{attempt}-{len(results) + 1:02d}.png')
        results.append({'name': name, 'photo': photo.name, 'passed': True})
        print(f'PASS {len(results):02d}: {name}', flush=True)
        (report / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        rows = ''.join(f'<li><strong>PASS · {html.escape(r["name"])}</strong><br>'
                       f'<a href="../{r["photo"]}"><img src="../{r["photo"]}"></a></li>' for r in results)
        (report / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Markdown canvas visual verification</title>'
            '<style>body{background:#191e27;color:#edf2f7;font:16px Segoe UI;margin:32px}'
            'li{margin:24px 0}img{max-width:100%;max-height:420px}a{color:#79d8c7}</style>'
            f'<h1>Markdown canvas — {len(results)} passing checkpoints</h1>'
            '<p>Real source UI, isolated test account, headed Chrome. Full desktop photos by Shoter. '
            'Context transport is captured without invoking a model.</p><ol>' + rows + '</ol>', encoding='utf-8')
        page.wait_for_timeout(650)

    def require(condition, message='Assertion failed'):
        if not condition:
            raise AssertionError(message)

    def open_file(name, button='#open-button'):
        window.activate()
        with page.expect_file_chooser() as chooser:
            page.locator(button).click()
        chooser.value.set_files(folder / name)
        page.wait_for_timeout(500)

    page.goto(BASE + '/agent/agent/', wait_until='load')
    window.resize(1440, 900)
    page.keyboard.press('Control+0')
    page.wait_for_timeout(800)
    open_file('Showcase.MD')
    checkpoint('Open uppercase .MD with UTF-8 BOM; rendered preview and shared theme', lambda: require(
        doc.locator('h1').inner_text() == 'Markdown in Tlamatini'
        and page.locator('#markdown-canvas-host').is_visible()
        and not page.locator('#editor-container').is_visible()
        and page.locator('#markdown-preview-button').get_attribute('aria-pressed') == 'true'))
    checkpoint('Headings, inline formatting, Unicode and reference links', lambda: require(
        all(doc.locator(tag).count() for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del'])
        and '日本語' in doc.inner_text()
        and doc.get_by_text('Reference link', exact=True).get_attribute('href') == 'https://example.com/docs'))
    doc.locator('table').scroll_into_view_if_needed()
    checkpoint('GFM table alignment and readable cells', lambda: require(
        doc.locator('tbody tr').count() == 2
        and doc.locator('th').nth(2).evaluate('(e)=>getComputedStyle(e).textAlign') == 'right'))
    doc.get_by_text('Lists and tasks', exact=True).scroll_into_view_if_needed()
    checkpoint('Nested ordered/unordered lists, disabled task checkboxes and blockquotes', lambda: require(
        doc.locator('ol > li > ul').count() == 1 and doc.locator('blockquote ul').count() == 1
        and doc.locator('input[disabled][type=checkbox]').count() == 2
        and doc.locator('input:checked').count() == 1))
    doc.get_by_text('Jump to code', exact=True).click()
    checkpoint('Heading links scroll inside canvas; highlighted code stays literal', lambda: require(
        doc.locator('pre .hljs-keyword').count() > 0
        and '<script>window.markdownExecuted = true;</script>' in doc.locator('pre').nth(1).inner_text()
        and not page.evaluate('Boolean(window.markdownExecuted)')))
    doc.locator('summary').click()
    checkpoint('Expandable HTML details and explicit local-image placeholder', lambda: require(
        doc.locator('details').get_attribute('open') is not None
        and doc.locator('.markdown-missing-image').count() == 1))
    with page.expect_file_chooser() as chooser:
        page.locator('#markdown-folder-button').click()
    chooser.value.set_files(folder)
    doc.locator('img').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#markdown-canvas-document img')?.naturalWidth > 0")
    checkpoint('Choose folder resolves local illustration without uploading it', lambda: require(
        doc.locator('img').get_attribute('src').startswith('blob:')
        and doc.locator('.markdown-missing-image').count() == 0))
    # Use the real splitter to review the full-width reading layout as well.
    page.locator('#drag-divider').focus()
    page.keyboard.press('End')
    for _ in range(4):
        page.keyboard.press('Shift+ArrowLeft')
    doc.locator('h1').scroll_into_view_if_needed()
    checkpoint('Wider canvas uses the existing splitter and shared reading theme', lambda: require(
        page.locator('#canvas-container').bounding_box()['width'] > 600
        and doc.evaluate('(e)=>getComputedStyle(e).fontFamily').lower().find('nunito') >= 0))
    page.locator('#markdown-source-button').focus()
    page.keyboard.press('Enter')
    checkpoint('Keyboard Source toggle preserves all raw Markdown and line numbers', lambda: require(
        page.locator('#editor-container').is_visible()
        and page.locator('#text-editor code').text_content() == SAMPLE.replace('\n', '\r\n')
        and page.locator('#line-numbers').input_value().endswith(str(len(SAMPLE.split('\n'))))))
    page.locator('#markdown-preview-button').click()
    context.grant_permissions(['clipboard-read', 'clipboard-write'], origin=BASE)
    page.locator('#copy-canvas-button').click()
    page.wait_for_timeout(300)
    copied = page.evaluate('navigator.clipboard.readText()')
    checkpoint('Copy returns original Markdown rather than rendered text', lambda: require(
        copied.replace('\r\n', '\n') == SAMPLE))
    def accept_save(dialog):
        dialog.accept('markdown-roundtrip.md')
    page.once('dialog', accept_save)
    with page.expect_download() as downloaded:
        page.locator('#save-as-button').click()
    path = report / 'markdown-roundtrip.md'
    downloaded.value.save_as(path)
    page.locator('#markdown-preview-button').click()
    checkpoint('Save preserves original bytes, including BOM and CRLF', lambda: require(
        path.read_bytes() == (folder / 'Showcase.MD').read_bytes()))
    open_file('long.markdown', '#reopen-canvas-button')
    doc.get_by_text('LONG_DOCUMENT_END', exact=True).scroll_into_view_if_needed()
    checkpoint('Reopen .markdown renders all 500 sections with no truncation', lambda: require(
        doc.locator('h2').count() == 500 and doc.inner_text().endswith('LONG_DOCUMENT_END')))
    open_file('empty.md')
    checkpoint('Empty Markdown has a clear empty state and available Source', lambda: require(
        'empty' in page.locator('#markdown-canvas-status').inner_text()
        and not page.locator('#markdown-source-button').is_disabled()))
    # A real browser DataTransfer exercises the canvas drop listener.
    drop = page.evaluate_handle("(text)=>{const d=new DataTransfer();d.items.add(new File([text],'dropped.md',{type:'text/markdown'}));return d}", '# Dropped Markdown\n\n**Drop works**')
    page.locator('#canvas-container').dispatch_event('drop', {'dataTransfer': drop})
    page.wait_for_timeout(300)
    checkpoint('Drag/drop routes Markdown into the preview', lambda: require(doc.locator('h1').inner_text() == 'Dropped Markdown'))
    open_file('hostile.md')
    checkpoint('Unsafe HTML, event handlers, styles, URLs and app IDs stay inert', lambda: require(
        not page.evaluate('Boolean(window.markdownExecuted)')
        and doc.locator('script,iframe,svg,style,form,[onerror],[onload],[style],.ui-widget-overlay').count() == 0
        and page.locator('#chat-message-input').count() == 1
        and doc.locator('a[href^="javascript:"],a[href^="/agent/"]').count() == 0
        and 'SAFE_END' in doc.inner_text()))
    open_file('plain.txt')
    checkpoint('Text files still display literal source; Markdown toolbar closes', lambda: require(
        page.locator('#editor-container').is_visible() and not page.locator('#markdown-canvas-toolbar').is_visible()
        and page.locator('#text-editor code').text_content() == '# This stays literal\n**source text**'))
    open_file('sample.py')
    checkpoint('Existing source-code highlighting remains intact', lambda: require(page.locator('#text-editor .hljs-keyword').count() > 0))
    open_file('sample.pdf')
    pdf = page.frame_locator('#pdf-canvas-host iframe')
    pdf.locator('.page canvas').first.wait_for(state='visible', timeout=30000)
    checkpoint('PDF still renders in its dedicated viewer', lambda: require(page.locator('#pdf-canvas-host').is_visible()))
    open_file('Showcase.MD')
    checkpoint('Switching PDF to Markdown removes the PDF frame', lambda: require(
        page.locator('#pdf-canvas-host iframe').count() == 0 and doc.locator('h1').count() == 1))
    page.locator('#clean-canvas-button').click()
    checkpoint('Clear removes Markdown, resources, toolbar and filename', lambda: require(
        not page.evaluate('window.TlamatiniMarkdownCanvas.active')
        and doc.inner_text() == '' and not page.locator('#markdown-canvas-toolbar').is_visible()))
    # Test stale async reads without replacing the production implementation.
    page.evaluate("""() => {
      window.finishSlowRead = null;
      const old = new File(['old'], 'old.md');
      old.text = () => new Promise(resolve => { window.finishSlowRead = resolve; });
      void loadSelectedCanvasFile(old);
    }""")
    open_file('Showcase.MD')
    page.evaluate("window.finishSlowRead('# Stale content')")
    page.wait_for_timeout(300)
    checkpoint('Late file reads cannot replace a newer Markdown document', lambda: require(doc.locator('h1').inner_text() == 'Markdown in Tlamatini'))
    open_file('linked.md')
    with page.expect_file_chooser() as chooser:
        page.locator('#markdown-folder-button').click()
    chooser.value.set_files(folder)
    doc.get_by_text('Next', exact=True).click()
    page.wait_for_function("document.querySelector('#markdown-canvas-document img')?.naturalWidth > 0")
    checkpoint('Linked Markdown retains its folder and resolves parent-relative images', lambda: require(
        doc.locator('h1').inner_text() == 'Nested document'
        and doc.locator('img').get_attribute('src').startswith('blob:')))
    doc.get_by_text('Back', exact=True).click()
    checkpoint('Local Markdown links can navigate back within the selected folder', lambda: require(
        doc.locator('h1').inner_text() == 'Linked document'))
    page.evaluate("loadCanvas('Generated guide.md')")
    page.wait_for_function("document.querySelector('#markdown-canvas-document h1')?.textContent === 'Generated Markdown'")
    checkpoint('Generated Markdown fetched from the real server route renders in canvas', lambda: require(
        doc.locator('strong').inner_text() == 'Stored source'
        and page.locator('#filename').inner_text() == '<<< Generated guide.md >>>'))
    open_file('Showcase.MD')
    # Reload to exercise the existing automatic narrow-pane sizing too.
    page.reload(wait_until='load')
    open_file('Showcase.MD')
    window.resize(900, 700)
    doc.locator('table').scroll_into_view_if_needed()
    print('NARROW LAYOUT:', page.evaluate("""() => {
      const host=document.querySelector('#markdown-canvas-host');
      const right=host.getBoundingClientRect().right;
      return {width:host.clientWidth, scroll:host.scrollWidth,
        overflow:[...host.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>right+1)
          .slice(0,15).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width}))};
    }"""), flush=True)
    checkpoint('Narrow native window: toolbar wraps and canvas contains content', lambda: require(page.evaluate("""() => {
      const host=document.querySelector('#markdown-canvas-host');
      const canvas=document.querySelector('#canvas-container').getBoundingClientRect();
      return host.scrollWidth <= host.clientWidth + 1 &&
        [...document.querySelectorAll('#markdown-canvas-toolbar button:not([hidden])')].every(b=>{
          const r=b.getBoundingClientRect();return r.left>=canvas.left && r.right<=canvas.right+1;
        });
    }""")))
    page.locator('#drag-divider').focus()
    page.keyboard.press('End')
    for _ in range(4):
        page.keyboard.press('Shift+ArrowLeft')
    doc.locator('table').scroll_into_view_if_needed()
    checkpoint('Narrow window with resized canvas keeps table scrolling inside its frame', lambda: require(
        doc.locator('.markdown-table-scroll').evaluate('(e)=>e.scrollWidth >= e.clientWidth')
        and page.locator('#markdown-canvas-host').evaluate('(e)=>e.scrollWidth <= e.clientWidth + 1')))
    window.resize(1440, 900)
    import win32api
    import win32con

    def native_control_key(key):
        window.activate()
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(key, 0, 0, 0)
        win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        page.wait_for_timeout(500)

    initial_dpr = page.evaluate('devicePixelRatio')
    native_control_key(win32con.VK_ADD)
    native_control_key(win32con.VK_ADD)
    zoomed_dpr = page.evaluate('devicePixelRatio')
    print('NATIVE CHROME ZOOM:', initial_dpr, '->', zoomed_dpr, flush=True)
    checkpoint('Native browser zoom retains scrollable document and controls', lambda: require(
        zoomed_dpr > initial_dpr
        and page.locator('#markdown-preview-button').is_visible() and doc.locator('table').is_visible()))
    native_control_key(ord('0'))
    require(abs(page.evaluate('devicePixelRatio') - initial_dpr) < .01, 'Browser zoom failed to reset')
    # The context send is the real UI path, with only the model transport replaced.
    sent.clear()
    page.locator('#context-button').click()
    page.wait_for_timeout(500)
    payloads = [json.loads(m) for m in sent if isinstance(m, str) and m.startswith('{')]
    checkpoint('Use as context sends full Markdown with its original filename', lambda: require(any(
        m.get('type') == 'set-canvas-as-context' and m.get('message') == 'Showcase.MD'
        and m.get('content') == SAMPLE.replace('\n', '\r\n') for m in payloads)))
    page.reload(wait_until='load')
    sent.clear()
    page.locator('#context-menu-button').click()
    open_file('Guía de Angela.md', '#set-file-context')
    payloads = [json.loads(m) for m in sent if isinstance(m, str) and m.startswith('{')]
    checkpoint('Context menu accepts Markdown filenames with spaces and Unicode', lambda: require(any(
        m.get('type') == 'set-canvas-as-context' and m.get('message') == 'Guía de Angela.md'
        and m.get('content') == (folder / 'Guía de Angela.md').read_bytes().decode('utf-8') for m in payloads)))
    checkpoint('No browser JavaScript errors', lambda: require(not errors, repr(errors)))
    page.goto(BASE + '/agent/agent/', wait_until='load')
    open_file('Showcase.MD')
    page.locator('#drag-divider').focus()
    page.keyboard.press('End')
    for _ in range(4):
        page.keyboard.press('Shift+ArrowLeft')
    print(f'RESULT: {len(results)}/{len(results)} visual checkpoints PASS', flush=True)
    print('REVIEW REPORT:', report / 'SUMMARY.html', flush=True)
    return results


def main():
    if any('headless' in arg.lower() for arg in sys.argv[1:]):
        raise SystemExit('HEADLESS IS FORBIDDEN.')
    visible_console()
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    OUT.mkdir(parents=True, exist_ok=True)
    folder = fixtures()
    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    import tlamatini.settings as settings
    settings.DATABASES['default']['NAME'] = OUT / 'isolated-browser.sqlite3'
    import django
    django.setup()
    from django.core.management import call_command
    print('Migrating isolated test database and collecting runtime static assets.', flush=True)
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0)
    sys.path.insert(0, str(ROOT))
    from build_runtime_assets import verify_collected_static
    verify_collected_static(ROOT)
    from django.contrib.auth import get_user_model
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username='markdown-review')
    user.set_password(password)
    user.save()
    from agent.models import LLMProgram
    LLMProgram.objects.update_or_create(idProgram=98765, defaults={
        'programName': 'Generated guide.md', 'programLanguage': 'markdown',
        'programContent': '# Generated Markdown\n\n**Stored source**',
    })
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from tlamatini.asgi import application
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(ASGIStaticFilesHandler(application), host='127.0.0.1',
                                         port=8875, log_level='warning', loop='asyncio'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.1)
    if not server.started:
        raise RuntimeError('Isolated server failed to start.')
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    from playwright.sync_api import sync_playwright
    from chat_composer_visible_window import VisibleWindow
    import drag_divider_look_visible as photos
    photos.OUT = OUT
    success = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False, slow_mo=100)
        context = browser.new_context(no_viewport=True)
        context.add_init_script("localStorage.setItem('tlm_voice_settings', JSON.stringify({mode:'silent'}));")
        sent, errors = [], []
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: sent.append(message)))
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        window = VisibleWindow(page, context)
        window.resize(1440, 900)
        page.goto(BASE + '/', wait_until='load')

        def capture(name):
            window.verify()
            photo = photos.shoter(name)
            window.verify()
            return photo

        gate = OUT / 'browser-visible-confirmed'
        gate.unlink(missing_ok=True)
        capture('browser-waiting.png')
        print('BROWSER WAITING: inspect browser-waiting.png, then create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            page.wait_for_timeout(300)
        page.locator('#id_username').fill('markdown-review')
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
                import importlib.util
                spec = importlib.util.spec_from_file_location('markdown_checks', __file__)
                latest = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(latest)
                results = latest.checks(page, context, window, capture, sent, errors, folder, attempt)
                success = True
                (OUT / 'final-result.json').write_text(json.dumps({'passed': True, 'checks': len(results), 'attempt': attempt}), encoding='utf-8')
            except Exception:
                success = False
                traceback.print_exc()
                capture(f'run-{attempt}-failure.png')
                (OUT / 'final-result.json').write_text(json.dumps({'passed': False, 'attempt': attempt, 'error': traceback.format_exc()}), encoding='utf-8')
            print('BROWSER STAYS OPEN. Review live; rerun.confirmed repeats, close.confirmed ends.', flush=True)
            while not close.exists() and not rerun.exists() and not page.is_closed():
                page.wait_for_timeout(500)
            if rerun.exists():
                rerun.unlink()
        window.release()
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
