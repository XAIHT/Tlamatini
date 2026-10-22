# Tlamatini Author Banner — Angela López Mendoza
"""Real canvas editing and native saving, in verified visible Chrome only.

Run from a verified foreground PowerShell -NoExit console titled Tlamatini.
The source application uses an isolated database; fixtures and native Save As
destinations stay below Temp/canvas-editing-visible, outside Downloads. Inspect
the full-desktop Shoter browser-waiting.png, then create
browser-visible-confirmed. Monitor live.log every 5–15 seconds. Chrome remains
open for inspection: rerun.confirmed retries; close.confirmed ends the run.
Create handles-only.confirmed before rerun.confirmed to run only the original
browser-file-handle Save and its real Chrome write-permission dialog.
remaining-only.confirmed runs the timing, failed-load, toolbar, PDF and browser
handle cases after previously verified filetype and basic Save cases.
tail-only.confirmed runs failed-load, toolbar, PDF and browser handle cases
after creating a fresh native destination with the same UTF-16 fixture.

File opens and Save As use the actual Windows dialogs. Edits use the keyboard,
and success is checked against disk bytes. Only the model WebSocket is captured;
this does not certify model ingestion, frozen packaging, or installed releases.
No headless flag, synthetic save endpoint, or screenshot substitute is accepted.
"""
import asyncio
import html
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/canvas-editing-visible'
PORT = 8882
BASE = f'http://127.0.0.1:{PORT}'
FILE_WRITE_BUTTON_NAMES = {'save changes', 'edit file', 'guardar cambios', 'editar archivo'}


class LiveTranscript:
    """Retain live output without concealing it from the development console."""

    def __init__(self, stream):
        self.stream = stream
        self.canvas_editing_transcript = True

    def write(self, value):
        self.stream.write(value)
        self.stream.flush()
        with (OUT / 'live.log').open('a', encoding='utf-8') as log:
            log.write(value)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def owned_dialogs(window):
    """Only this harness/server/browser's visible native dialogs are eligible."""
    import psutil
    import win32con
    import win32gui
    import win32process
    owned = {os.getpid()} | {p.pid for p in psutil.Process().children(recursive=True)}
    dialogs = []
    win32gui.EnumWindows(lambda hwnd, _: dialogs.append(hwnd) if (
        win32gui.GetClassName(hwnd) == '#32770' and win32gui.IsWindowVisible(hwnd)
        and (win32process.GetWindowThreadProcessId(hwnd)[1] in owned
             or win32gui.GetWindow(hwnd, win32con.GW_OWNER) == window.hwnd
             or win32gui.GetAncestor(hwnd, win32con.GA_ROOTOWNER) == window.hwnd)
    ) else None, None)
    return dialogs


def verify_dialog(hwnd):
    import ctypes
    import win32con
    import win32gui
    assert win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd)
    assert win32gui.GetForegroundWindow() == hwnd, 'Native dialog is not foreground.'
    cloaked = ctypes.c_int()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd), 14, ctypes.byref(cloaked), 4)
    assert not cloaked.value, 'Native dialog is on another desktop.'
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    front = win32gui.WindowFromPoint(((left + right) // 2, (top + bottom) // 2))
    assert win32gui.GetAncestor(front, win32con.GA_ROOT) == hwnd, (
        'Native dialog is obscured by another window despite owning foreground.',
        win32gui.GetWindowText(front), (left, top, right, bottom))


def dismiss_owned_dialogs(page, window):
    """Cancel only dialogs belonging to this harness before its server exits."""
    import win32con
    import win32gui
    for dialog in owned_dialogs(window):
        print('Closing owned native dialog:', win32gui.GetWindowText(dialog), flush=True)
        win32gui.PostMessage(dialog, win32con.WM_CLOSE, 0, 0)
    deadline = time.monotonic() + 5
    while owned_dialogs(window) and time.monotonic() < deadline:
        if page.is_closed():
            time.sleep(.1)
        else:
            page.wait_for_timeout(100)
    assert not owned_dialogs(window), 'An owned native dialog did not acknowledge cancellation.'


def configure_visible_window(page, window):
    """Raise the test browser above our visible console and prove real exposure."""
    from canvas_refresh_visible import activate_browser
    import win32con
    import win32gui
    if not hasattr(window, '_editing_base_verify'):
        window._editing_base_verify = window.verify

    def activate():
        activate_browser(window)
        win32gui.SetWindowPos(window.hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        page.wait_for_timeout(300)

    def verify():
        proof = window._editing_base_verify()
        left, top = win32gui.ClientToScreen(window.hwnd, (0, 0))
        _, _, width, height = win32gui.GetClientRect(window.hwnd)
        for x in (.05, .5, .95):
            for y in (.1, .5, .9):
                point = (left + int(width * x), top + int(height * y))
                front = win32gui.WindowFromPoint(point)
                assert win32gui.GetAncestor(front, win32con.GA_ROOT) == window.hwnd, (
                    'The visible development console or another window covers test Chrome.',
                    point, win32gui.GetWindowText(front))
        return proof

    window.activate = activate
    window.verify = verify


def chrome_accessibility_controls(hwnd):
    """Read this Chrome window through Windows UI Automation, without packages.

    The ABI slots are the published IUIAutomation/IUIAutomationElement vtables
    in Microsoft's UIAutomationClient.h. This helper only reads native UI; it
    cannot grant a browser permission or invoke an unobserved control.
    """
    import ctypes as ct
    from ctypes import wintypes
    import uuid
    ole32, oleaut32 = ct.WinDLL('ole32'), ct.WinDLL('oleaut32')
    ole32.CoInitializeEx.argtypes = [ct.c_void_p, ct.c_ulong]
    ole32.CoInitializeEx.restype = ct.c_long
    ole32.CoCreateInstance.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_ulong,
                                     ct.c_void_p, ct.POINTER(ct.c_void_p)]
    ole32.CoCreateInstance.restype = ct.c_long
    oleaut32.SysFreeString.argtypes = [ct.c_void_p]
    oleaut32.SysFreeString.restype = None
    initialized = ole32.CoInitializeEx(None, 2)
    automation, root, condition, elements = (ct.c_void_p() for _ in range(4))

    def invoke(pointer, slot, types, *args):
        table = ct.cast(pointer, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        call = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *types)(table[slot])
        result = call(pointer, *args)
        if result < 0:
            raise OSError(f'UI Automation slot {slot} failed: 0x{result & 0xffffffff:08x}')

    def scalar(element, slot):
        result = ct.c_int()
        invoke(element, slot, [ct.POINTER(ct.c_int)], ct.byref(result))
        return result.value

    def name(element):
        result = ct.c_void_p()
        invoke(element, 23, [ct.POINTER(ct.c_void_p)], ct.byref(result))
        try:
            return ct.wstring_at(result) if result.value else ''
        finally:
            oleaut32.SysFreeString(result)

    try:
        clsid = (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID('ff48dba4-60ef-4201-aa87-54103eef594e').bytes_le)
        iid = (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID('30cbe57d-d9d0-452a-ab13-7ac5ac4825ee').bytes_le)
        result = ole32.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(automation))
        if result < 0:
            raise OSError(f'UI Automation unavailable: 0x{result & 0xffffffff:08x}')
        invoke(automation, 6, [wintypes.HWND, ct.POINTER(ct.c_void_p)], hwnd, ct.byref(root))
        invoke(automation, 21, [ct.POINTER(ct.c_void_p)], ct.byref(condition))
        invoke(root, 6, [ct.c_int, ct.c_void_p, ct.POINTER(ct.c_void_p)],
               4, condition, ct.byref(elements))  # TreeScope_Descendants, owned Chrome only.
        count = scalar(elements, 3)
        assert count <= 3000, f'Unexpectedly large Chrome accessibility tree: {count}'
        controls = []
        for index in range(count):
            element = ct.c_void_p()
            invoke(elements, 4, [ct.c_int, ct.POINTER(ct.c_void_p)], index, ct.byref(element))
            try:
                title = name(element)
                if not title or scalar(element, 38):
                    continue
                rect = wintypes.RECT()
                invoke(element, 43, [ct.POINTER(wintypes.RECT)], ct.byref(rect))
                controls.append({'name': title, 'type': scalar(element, 21),
                                 'enabled': bool(scalar(element, 28)),
                                 'rect': [rect.left, rect.top, rect.right, rect.bottom]})
            finally:
                invoke(element, 2, [])
        return controls
    finally:
        for pointer in (elements, condition, root, automation):
            if pointer.value:
                invoke(pointer, 2, [])
        if initialized >= 0:
            ole32.CoUninitialize()


def grant_visible_file_write(page, window, capture, shot_name, filename):
    """Click the real Chrome permission button after accessibility and photo proof."""
    import win32api
    import win32con
    import win32gui
    deadline = time.monotonic() + 12
    controls, candidates = [], []
    while time.monotonic() < deadline:
        window.verify()
        controls = chrome_accessibility_controls(window.hwnd)
        candidates = [item for item in controls if item['type'] == 50000 and item['enabled']
                      and item['name'].strip().lower() in FILE_WRITE_BUTTON_NAMES]
        if candidates:
            break
        page.wait_for_timeout(200)
    diagnostic = OUT / Path(shot_name).with_suffix('.uia.json')
    diagnostic.write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding='utf-8')
    assert len(candidates) == 1, ('Chrome write permission button was not identified uniquely.', candidates)
    text = '\n'.join(item['name'] for item in controls)
    assert filename in text and '127.0.0.1' in text, 'Permission UI did not identify this test file and site.'
    button = candidates[0]
    # Chrome intentionally rejects immediate input on a newly presented file
    # permission dialog. Wait past its input-protection interval, then re-read
    # the observed button instead of invoking an accessibility permission API.
    page.wait_for_timeout(900)
    window.verify()
    stable = [item for item in chrome_accessibility_controls(window.hwnd)
              if item['type'] == 50000 and item['enabled'] and item['name'] == button['name']]
    assert len(stable) == 1, ('Chrome permission button changed while stabilizing.', stable)
    button = stable[0]
    left, top, right, bottom = button['rect']
    assert right > left and bottom > top, button
    point = ((left + right) // 2, (top + bottom) // 2)
    assert win32gui.GetAncestor(win32gui.WindowFromPoint(point), win32con.GA_ROOT) == window.hwnd, (
        'Chrome permission button is obscured.', button)
    capture(shot_name)
    window.verify()
    print('CHROME FILE PERMISSION:', json.dumps(button, ensure_ascii=False), flush=True)
    win32api.SetCursorPos(point)
    page.wait_for_timeout(150)
    assert win32api.GetCursorPos() == point, ('Native pointer did not reach the observed permission button.', point)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    page.wait_for_timeout(120)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def dismiss_previous_file_permission(page, window, capture, attempt):
    """Cancel only our recognized file-write prompt before a requested rerun."""
    pending = page.evaluate('''() => window.TlamatiniCanvasEditing?.busy
        && typeof canvasSource !== 'undefined' && canvasSource?.name === 'browser-handle-original.txt' ''')
    if not pending:
        return
    import win32api
    import win32con
    controls = chrome_accessibility_controls(window.hwnd)
    candidates = [item for item in controls if item['type'] == 50000 and item['enabled']
                  and item['name'].strip().lower() in FILE_WRITE_BUTTON_NAMES]
    text = '\n'.join(item['name'] for item in controls)
    assert len(candidates) == 1 and 'browser-handle-original.txt' in text and '127.0.0.1' in text, (
        'Previous Save is pending but its owned permission dialog was not identified; no key sent.')
    window.verify()
    capture(f'run-{attempt}/previous-browser-permission-cancel.png')
    win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
    page.wait_for_timeout(100)
    win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
    page.wait_for_function('!TlamatiniCanvasEditing.busy')
    print('Cancelled previous test file permission dialog before rerun.', flush=True)


def native_visibility_diagnostic(name, dialog, reason):
    """Photograph a refused visibility gate, without performing any UI input.

    This is diagnostic evidence of failure, never a passing screenshot or
    authorization to continue a hidden workload.
    """
    import win32con
    import win32gui
    import win32process
    import drag_divider_look_visible as photos
    target = OUT / Path(name).parent
    target.mkdir(parents=True, exist_ok=True)
    photos.OUT = target
    photo, metadata = photos.shoter(Path(name).stem + '-visibility-refused.png')
    windows = []
    win32gui.EnumWindows(lambda hwnd, _: windows.append({
        'hwnd': hwnd, 'title': win32gui.GetWindowText(hwnd),
        'class': win32gui.GetClassName(hwnd),
        'pid': win32process.GetWindowThreadProcessId(hwnd)[1],
        'owner': win32gui.GetWindow(hwnd, win32con.GW_OWNER),
        'rect': win32gui.GetWindowRect(hwnd),
        'topmost': bool(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST),
    }) if win32gui.IsWindowVisible(hwnd) else None, None)
    bounds = win32gui.GetWindowRect(dialog)
    foreground = win32gui.GetForegroundWindow()
    windows = [item for item in windows if item['hwnd'] in (dialog, foreground) or (
        item['topmost']
        and min(item['rect'][2], bounds[2]) > max(item['rect'][0], bounds[0])
        and min(item['rect'][3], bounds[3]) > max(item['rect'][1], bounds[1]))]
    details = {'diagnostic_only': True, 'reason': reason, 'dialog': dialog,
               'foreground': foreground, 'relevant_z_order': windows,
               'screenshot': str(photo), 'metadata': metadata}
    (target / (Path(name).stem + '-visibility-refused.json')).write_text(
        json.dumps(details, indent=2, default=str), encoding='utf-8')
    print('VISIBILITY REFUSED; diagnostic desktop photo:', photo, flush=True)
    print('DIALOG LAYERS:', json.dumps(windows, ensure_ascii=False), flush=True)


def native_control_text(hwnd):
    """Read an Edit field across processes; GetWindowText only reads captions there."""
    import ctypes as ct
    from ctypes import wintypes
    user32 = ct.WinDLL('user32', use_last_error=True)
    read = user32.SendMessageTimeoutW
    read.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                     wintypes.UINT, wintypes.UINT, ct.POINTER(ct.c_size_t)]
    read.restype = ct.c_ssize_t
    text = ct.create_unicode_buffer(32768)
    result = ct.c_size_t()
    ct.set_last_error(0)
    # WM_GETTEXT is marshalled by Windows for foreign-process controls. The
    # bounded call refuses a hung dialog instead of hanging the visible test.
    if not read(hwnd, 0x000D, len(text), ct.cast(text, ct.c_void_p).value,
                0x0001 | 0x0002, 1000, ct.byref(result)):
        raise OSError(ct.get_last_error(), 'Native filename text read failed or timed out.')
    return text.value


def choose_native_save(page, window, path, capture, shot_name, cancel=False,
                       kind='Save', suggested_name=None):
    """Drive a real file dialog; never send a path directly to the save API."""
    import win32con
    import win32gui
    deadline = time.monotonic() + 20
    dialog = None
    while time.monotonic() < deadline:
        candidates = owned_dialogs(window)
        foreground = win32gui.GetForegroundWindow()
        if foreground in candidates:
            dialog = foreground
            break
        page.wait_for_timeout(100)
    assert dialog is not None, f'No visible, foreground native {kind} dialog appeared.'
    # WM_INITDIALOG can expose the HWND before Windows finishes placing it
    # above the initiating browser. Do no input until visibility passes on
    # three consecutive observations, and refuse after a bounded three seconds.
    visibility_deadline = time.monotonic() + 3
    visible_observations = 0
    last_visibility_error = None
    while time.monotonic() < visibility_deadline:
        try:
            verify_dialog(dialog)
            visible_observations += 1
        except AssertionError as error:
            visible_observations = 0
            last_visibility_error = str(error)
        if visible_observations >= 3:
            break
        page.wait_for_timeout(100)
    if visible_observations < 3:
        native_visibility_diagnostic(shot_name, dialog, last_visibility_error)
        raise AssertionError((
            f'Native {kind} dialog never became stably visible; no file input was sent.',
            last_visibility_error))
    # HWND visibility precedes completion of the dialog's filename setup. Wait
    # for the intended field and its suggested name to stabilize before typing.
    filename, edits, previous, stable = None, [], None, 0
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        controls = []
        win32gui.EnumChildWindows(dialog, lambda hwnd, _: controls.append(hwnd), None)
        edits = [hwnd for hwnd in controls if win32gui.GetClassName(hwnd) == 'Edit'
                 and win32gui.IsWindowVisible(hwnd)]
        matches = [hwnd for hwnd in edits
                   if suggested_name and native_control_text(hwnd) == suggested_name]
        if not matches:
            matches = [hwnd for hwnd in edits
                       if win32gui.GetDlgCtrlID(hwnd) in (1148, 1152)
                       or win32gui.GetDlgCtrlID(win32gui.GetParent(hwnd)) == 1148]
        if len(matches) == 1:
            candidate = matches[0]
            initial = native_control_text(candidate)
            button = win32gui.GetDlgItem(dialog, 2 if cancel else 1)
            ready = button and win32gui.IsWindowVisible(button) and win32gui.IsWindowEnabled(button)
            ready = ready and (not suggested_name or initial == suggested_name)
            observed = (candidate, initial)
            stable = stable + 1 if ready and observed == previous else 0
            previous = observed
            if stable >= 4:
                filename = candidate
                break
        page.wait_for_timeout(100)
    diagnostics = [{'class': win32gui.GetClassName(hwnd), 'id': win32gui.GetDlgCtrlID(hwnd),
                    'parent_class': win32gui.GetClassName(win32gui.GetParent(hwnd)),
                    'parent_id': win32gui.GetDlgCtrlID(win32gui.GetParent(hwnd)),
                    'text': native_control_text(hwnd)} for hwnd in edits]
    print(f'NATIVE {kind} controls:', json.dumps(diagnostics, ensure_ascii=False), flush=True)
    assert filename, ('The native filename field did not become ready.', suggested_name, diagnostics)
    verify_dialog(dialog)
    if kind != 'Open':
        win32gui.SendMessage(dialog, win32con.WM_NEXTDLGCTL, filename, 1)
    win32gui.SendMessage(filename, win32con.WM_SETTEXT, 0, str(path))
    for _ in range(4):
        page.wait_for_timeout(100)
        if not win32gui.IsWindow(filename) or native_control_text(filename) != str(path):
            # Chrome's modern Open dialog may replace its inner Edit window.
            # Re-identify only a visible filename field carrying our exact path.
            controls = []
            win32gui.EnumChildWindows(dialog, lambda hwnd, _: controls.append(hwnd), None)
            matches = [hwnd for hwnd in controls if win32gui.GetClassName(hwnd) == 'Edit'
                       and win32gui.IsWindowVisible(hwnd)
                       and (win32gui.GetDlgCtrlID(hwnd) in (1148, 1152)
                            or win32gui.GetDlgCtrlID(win32gui.GetParent(hwnd)) == 1148)
                       and native_control_text(hwnd) == str(path)]
            if len(matches) == 1:
                filename = matches[0]
        actual_path = native_control_text(filename) if win32gui.IsWindow(filename) else '<destroyed HWND>'
        assert actual_path == str(path), (
            'Native filename text was replaced during initialization.', kind,
            repr(str(path)), repr(actual_path))
    left, top, right, bottom = win32gui.GetWindowRect(filename)
    front = win32gui.WindowFromPoint(((left + right) // 2, (top + bottom) // 2))
    assert front == filename or win32gui.IsChild(filename, front), 'Native filename field is obscured.'
    print(f'NATIVE {kind} selected:', native_control_text(filename), flush=True)
    capture(shot_name, native=dialog)
    verify_dialog(dialog)
    assert native_control_text(filename) == str(path)
    button = win32gui.GetDlgItem(dialog, 2 if cancel else 1)
    assert button, 'Native Save/Cancel button was not found.'
    win32gui.PostMessage(button, win32con.BM_CLICK, 0, 0)


def text_bytes(text, codec='utf-8', bom=b'', newline='\n'):
    return bom + text.replace('\n', newline).encode(codec)


def checks(page, context, window, capture, sent, errors, attempt):
    from canvas_refresh_visible import native_open, write_pdf
    dismiss_owned_dialogs(page, window)
    configure_visible_window(page, window)
    window.activate()
    window.verify()
    dismiss_previous_file_permission(page, window, capture, attempt)
    run = OUT / f'run-{attempt}'
    fixtures = run / 'fixtures'
    saved = run / 'saved-outside-downloads'
    fixtures.mkdir(parents=True, exist_ok=True)
    saved.mkdir(exist_ok=True)
    results = []
    def allow_fixture_reload(dialog):
        assert dialog.type == 'beforeunload', f'Unexpected browser dialog: {dialog.type}'
        dialog.accept()

    # A requested rerun may replace the previous failed run's unsaved fixture.
    page.on('dialog', allow_fixture_reload)
    try:
        page.goto(BASE + '/agent/agent/', wait_until='load')
    finally:
        page.remove_listener('dialog', allow_fixture_reload)
    page.wait_for_function('window.TlamatiniTextEditor && window.TlamatiniCanvasRefresh')
    page.evaluate('enableControlsAfterOperation()')
    divider = page.locator('#drag-divider').bounding_box()
    viewport_width = page.evaluate('innerWidth')
    page.mouse.move(divider['x'] + divider['width'] / 2,
                    divider['y'] + min(divider['height'] / 2, 200))
    page.mouse.down()
    page.mouse.move(viewport_width / 2,
                    divider['y'] + min(divider['height'] / 2, 200), steps=15)
    page.mouse.up()
    editor = page.locator('#editor-container .cm-content')
    save = page.locator('#canvas-save-button')
    save_as = page.locator('#canvas-save-as-button')
    status = page.locator('#canvas-edit-status')

    def checkpoint(name, **details):
        window.activate()
        page.wait_for_timeout(300)  # Let DWM complete the foreground transition before Shoter.
        window.verify()
        assert not errors, errors
        photo, metadata = capture(f'run-{attempt}/{len(results) + 1:02d}-{name}.png')
        results.append({'name': name, 'photo': photo.name, 'details': details,
                        'foreground': metadata.get('foreground_title', '')})
        print(f'PASS {len(results)}: {name}', flush=True)
        (run / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        (run / 'SUMMARY.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Canvas editing acceptance</title>'
            '<style>body{font:16px system-ui;background:#202632;color:#eee}'
            'img{width:95%}pre{white-space:pre-wrap}</style>'
            + ''.join(f'<h2>{i + 1}. {html.escape(row["name"])}</h2>'
                      f'<pre>{html.escape(json.dumps(row["details"], ensure_ascii=False))}</pre>'
                      f'<img src="{html.escape(row["photo"])}">'
                      for i, row in enumerate(results)), encoding='utf-8')

    def value():
        return page.evaluate('TlamatiniTextEditor.getText()')

    def replace_text(text):
        window.activate()
        window.verify()
        editor.click()
        page.keyboard.press('Control+A')
        if text:
            page.keyboard.insert_text(text)
        else:
            page.keyboard.press('Backspace')
        page.wait_for_function('(expected) => TlamatiniTextEditor.getText() === expected', arg=text)

    def append_text(text):
        window.activate()
        window.verify()
        before = value()
        editor.click()
        page.keyboard.press('Control+End')
        # Chrome insertText may coalesce a leading newline at the contenteditable
        # boundary. Real Enter keys exercise the user's multiline editing path.
        for index, line in enumerate(text.split('\n')):
            if index:
                page.keyboard.press('Enter')
            if line:
                page.keyboard.insert_text(line)
        actual = value()
        assert actual == before + text, (
            'Keyboard append did not produce the intended editor document.',
            repr(before), repr(text), repr(actual))

    def native_save(target, label, cancel=False, menu=False):
        window.activate()
        window.verify()
        # VisibleWindow.resize uses TOPMOST to establish test geometry. Release
        # that testing aid before opening an independent server-native dialog;
        # an ordinary browser must not cover its foreground Save dialog.
        window.release()
        suggested = page.locator('#filename').inner_text().strip('<> ')
        with page.expect_response(lambda response: '/agent/canvas/save/' in response.url,
                                  timeout=120000) as response_info:
            (page.locator('#save-as-button') if menu else save_as).click()
            choose_native_save(page, window, target, capture,
                               f'run-{attempt}/native-{label}.png', cancel=cancel,
                               suggested_name=suggested)
        response = response_info.value
        assert response.ok, (response.status, response.text())
        page.wait_for_function('!document.querySelector("#canvas-save-as-button").disabled')
        window.activate()
        window.verify()
        result = response.json()
        print('NATIVE SAVE RESULT:', json.dumps({key: item for key, item in result.items()
                                               if key != 'token'}, ensure_ascii=False), flush=True)
        if cancel:
            assert not result.get('saved'), result
        else:
            assert result.get('saved'), result
            assert Path(result.get('path', '')).resolve() == target.resolve(), (
                'Native Save selected an unexpected destination.', result.get('path'), str(target))
            assert target.is_file(), f'Native Save reported success but did not create {target}.'
        return result

    def direct_save(expected, target, shortcut=False):
        window.activate()
        window.verify()
        with page.expect_response(lambda response: '/agent/canvas/save/' in response.url,
                                  timeout=30000) as response_info:
            if shortcut:
                editor.click()
                page.keyboard.press('Control+s')
            else:
                save.click()
        response = response_info.value
        assert response.ok, (response.status, response.text())
        page.wait_for_function('!document.querySelector("#canvas-save-as-button").disabled')
        assert not owned_dialogs(window), 'Saving an authorized destination reopened a native dialog.'
        assert target.read_bytes() == expected, f'Save wrote incorrect bytes to {target.name}.'

    def cancel_dirty_action(selector):
        before = value()
        page.locator(selector).click()
        dialog = page.get_by_role('dialog').filter(has_text='Unsaved changes').last
        dialog.wait_for(state='visible')
        dialog.get_by_role('button', name='Cancel', exact=True).click()
        dialog.wait_for(state='hidden')
        assert value() == before, 'Cancelling the action discarded edited content.'
        assert not owned_dialogs(window), 'Cancelling opened a native picker.'

    def browser_handle_case():
        # Ordinary Open retains a browser-granted handle. Exercise primary Save on
        # that original file, including Chrome's actual write-permission surface,
        # after the other cases so unsupported native UI cannot hide their result.
        browser_source = fixtures / 'browser-handle-original.txt'
        browser_original = 'Original browser-opened file\nEspañol 日本語\n'
        browser_edited = 'Saved through the original browser handle\nEspañol 日本語 🦋\n'
        browser_source.write_bytes(text_bytes(browser_original, newline='\r\n'))
        native_open(page, window, browser_source)
        permission_before = page.evaluate('''async () => {
            if (!canvasSource?.handle?.createWritable) throw new Error('Open did not retain a writable browser file handle.');
            window.originalCanvasBrowserHandle = canvasSource.handle;
            return canvasSource.handle.queryPermission({mode:'readwrite'});
        }''')
        assert permission_before in ('prompt', 'granted'), permission_before
        replace_text(browser_edited)
        browser_save_requests = []

        def record_browser_save_request(request):
            if '/agent/canvas/save/' in request.url:
                browser_save_requests.append(request.url)

        page.on('request', record_browser_save_request)
        try:
            save.click()
            if permission_before == 'prompt':
                grant_visible_file_write(page, window, capture,
                                         f'run-{attempt}/browser-write-permission.png', browser_source.name)
            page.wait_for_function('!TlamatiniCanvasEditing.busy && '
                                   'document.querySelector("#canvas-edit-status").dataset.state === "saved"')
            assert browser_source.read_bytes() == text_bytes(browser_edited, newline='\r\n')
            assert page.evaluate('canvasSource.handle === window.originalCanvasBrowserHandle && !canvasSource.native')
            assert page.evaluate("canvasSource.handle.queryPermission({mode:'readwrite'})") == 'granted'
            append_text('Ctrl+S keeps the same original file\n')
            browser_edited += 'Ctrl+S keeps the same original file\n'
            page.keyboard.press('Control+s')
            page.wait_for_function('!TlamatiniCanvasEditing.busy && '
                                   'document.querySelector("#canvas-edit-status").dataset.state === "saved"')
            assert browser_source.read_bytes() == text_bytes(browser_edited, newline='\r\n')
            assert not browser_save_requests, 'Browser-handle Save unexpectedly used the native server endpoint.'
            assert not owned_dialogs(window), 'Browser-handle Save opened another file chooser.'
        finally:
            page.remove_listener('request', record_browser_save_request)
        checkpoint('primary-save-and-control-s-write-original-browser-handle',
                   original_file=str(browser_source), permission_before=permission_before,
                   real_permission_prompt=permission_before == 'prompt',
                   byte_count=browser_source.stat().st_size)

    handles_only = OUT / 'handles-only.confirmed'
    if handles_only.exists():
        handles_only.unlink()
        browser_handle_case()
        return results

    remaining_only = OUT / 'remaining-only.confirmed'
    tail_marker = OUT / 'tail-only.confirmed'
    tail_only = tail_marker.exists()
    tail_marker.unlink(missing_ok=True)
    if remaining_only.exists() or tail_only:
        remaining_only.unlink(missing_ok=True)
        print('Focused remainder: timing, failed loads, controls, PDF, browser-handle Save.', flush=True)
    else:
        assert save.is_disabled() and save_as.is_disabled()
        checkpoint('empty-canvas-disables-save')

        cases = [
            ('rust', 'hello.rs', 'fn main() {\n    println!("Before");\n}\n',
             'fn main() {\n    println!("Edited Rust");\n}\n', 'utf-8', b'', '\n'),
            ('python', 'greeting.py', 'def greet():\n    return "before"\n',
             'def greet(name):\n    return f"Hola, {name}!"\n', 'utf-8', b'', '\n'),
            ('json', 'settings.json', '{"message": "before"}\n',
             '{\n  "message": "Después",\n  "enabled": true\n}\n', 'utf-8', b'', '\n'),
            ('html-source', 'page.html', '<h1>Before</h1>\n',
             '<h1>Edited source</h1>\n<script>window.canvasEditingExecuted = true;</script>\n',
             'utf-8', b'', '\n'),
            ('unicode-crlf', 'Guía de Angela.txt', 'Primera línea\n日本語 🦋\n',
             'Última línea: áéíóú ñ\n日本語 🦋\n', 'utf-8', b'', '\r\n'),
            ('utf8-bom', 'with-bom.txt', 'BOM before\n', 'BOM después 🦋\n',
             'utf-8', b'\xef\xbb\xbf', '\r\n'),
            ('utf16-le', 'unicode-le.txt', 'UTF-16 before\n', 'UTF-16 después 日本語\n',
             'utf-16-le', b'\xff\xfe', '\r\n'),
            ('utf16-be', 'unicode-be.txt', 'UTF-16 before\n', 'UTF-16 después 日本語\n',
             'utf-16-be', b'\xfe\xff', '\n'),
            ('unknown-text', 'notes.customtext', 'Plain before\n', 'Plain edited\n',
             'utf-8', b'', '\n'),
            ('empty-text', 'empty.txt', '', 'First content\n', 'utf-8', b'', '\n'),
            ('save-empty', 'erase.txt', 'Erase this file content\n', '', 'utf-8', b'', '\n'),
            ('markdown', 'README.md', '# Before\n\nOriginal text.\n',
             '# Edited heading\n\n**Bold edited source** and ñ 🦋.\n\n'
             '<img src="x" onerror="window.canvasEditingExecuted = true">\n',
             'utf-8', b'\xef\xbb\xbf', '\r\n'),
        ]
        for label, filename, original, edited, codec, bom, newline in cases:
            print(f'CASE: {label} — native Open, keyboard edit, native Save As, disk verification.', flush=True)
            source, target = fixtures / filename, saved / filename
            original_bytes = text_bytes(original, codec, bom, newline)
            source.write_bytes(original_bytes)
            native_open(page, window, source)
            if label == 'markdown':
                assert page.locator('#markdown-canvas-host').is_visible()
                page.locator('#markdown-source-button').click()
            editor.wait_for(state='visible')
            assert editor.get_attribute('contenteditable') == 'true'
            assert value() == original, (label, repr(value()), repr(original))
            replace_text(edited)
            assert save.is_enabled(), f'{label}: Save did not enable after editing.'
            assert status.inner_text().strip(), f'{label}: edited status is blank.'
            if label in {'html-source', 'markdown'}:
                assert not page.evaluate('window.canvasEditingExecuted === true')
            if label == 'markdown':
                page.locator('#markdown-preview-button').click()
                page.wait_for_function('document.querySelector("#markdown-canvas-document h1")?.textContent === "Edited heading"')
                assert page.locator('#markdown-canvas-document strong').inner_text() == 'Bold edited source'
                assert page.locator('#markdown-canvas-document [onerror]').count() == 0
                assert not page.evaluate('window.canvasEditingExecuted === true')
                checkpoint('markdown-live-preview-is-sanitized')
                page.locator('#markdown-source-button').click()
                assert value() == edited, ('Markdown Source differs after Preview.', repr(value()), repr(edited))
            native_save(target, label, menu=label == 'rust')
            assert target.read_bytes() == text_bytes(edited, codec, bom, newline), label
            assert source.read_bytes() == original_bytes, 'Save As changed the source file.'
            checkpoint(f'{label}-editable-and-saved-outside-downloads',
                       destination=str(target), byte_count=target.stat().st_size,
                       encoding=codec, bom=bool(bom), newline=repr(newline))

        # The saved Markdown destination now belongs to the editor. Normal Save and
        # Ctrl+S must update that same file without another native dialog.
        edited += '\nSaved again.\n'
        append_text('\nSaved again.\n')
        direct_save(text_bytes(edited, codec, bom, newline), target)
        edited += 'Keyboard save.\n'
        append_text('Keyboard save.\n')
        direct_save(text_bytes(edited, codec, bom, newline), target, shortcut=True)
        checkpoint('save-and-control-s-update-authorized-file')

        page.wait_for_timeout(800)  # A separate user edit must form its own undo event.
        append_text('Unsaved change to undo.')
        changed = value()
        page.locator('#canvas-undo-button').click()
        assert value() == edited, ('Undo did not restore saved text.', repr(value()), repr(edited))
        assert status.get_attribute('data-state') == 'saved', ('Undo status:', status.inner_text(), status.get_attribute('data-state'))
        page.locator('#canvas-redo-button').click()
        assert value() == changed, ('Redo did not restore edited text.', repr(value()), repr(changed))
        assert status.get_attribute('data-state') == 'dirty', ('Redo status:', status.inner_text(), status.get_attribute('data-state'))
        for selector in ('#clean-canvas-button', '#reopen-canvas-button', '#open-button'):
            cancel_dirty_action(selector)
        checkpoint('undo-redo-and-cancel-dirty-clear-refresh-open')

        cancelled = saved / 'cancelled.md'
        native_save(cancelled, 'cancelled', cancel=True)
        assert not cancelled.exists(), 'Cancel created a file.'
        assert value() == changed, ('Native Cancel changed editor text.', repr(value()), repr(changed))
        assert status.get_attribute('data-state') == 'dirty', ('Native Cancel status:', status.inner_text(), status.get_attribute('data-state'))
        assert target.read_bytes() == text_bytes(edited, codec, bom, newline)
        checkpoint('native-save-cancellation-retains-edits-and-destination')

        # An external editor changes the saved file. Save must leave that change
        # intact, report the conflict, and keep our unsaved version available.
        external = text_bytes('# External edit\n', codec, bom, newline)
        target.write_bytes(external)
        with page.expect_response(lambda response: '/agent/canvas/save/' in response.url) as response_info:
            save.click()
        response = response_info.value
        assert response.status == 409, (response.status, response.text())
        assert target.read_bytes() == external
        assert value() == changed, ('Conflict changed editor text.', repr(value()), repr(changed))
        assert status.inner_text().strip(), 'Conflict left the editor status blank.'
        checkpoint('external-change-conflict-preserves-both-versions')
        native_save(saved / 'conflict-recovered.md', 'conflict-recovered')
        assert (saved / 'conflict-recovered.md').read_bytes() == text_bytes(changed, codec, bom, newline)

    if tail_only:
        encoding_source = fixtures / 'encoding-only.txt'
        encoding_target = saved / 'encoding-only.txt'
        same_text = 'Same text: Español 日本語\n'
        expected_encoding = text_bytes(same_text + 'Saved after encoding-only Refresh\n',
                                       'utf-16-le', b'\xff\xfe')
        encoding_source.write_bytes(expected_encoding)
        native_open(page, window, encoding_source)
        native_save(encoding_target, 'tail-destination')
    else:
        # Explicit timing fault injection: the real backend commits the requested
        # snapshot, but its HTTP response is withheld while the user types again.
        # There is no fabricated success body and no editor API mutation.
        race_source, race_target = fixtures / 'race.txt', saved / 'race.txt'
        race_source.write_bytes(b'Before save\n')
        native_open(page, window, race_source)
        native_save(race_target, 'race-destination')
        snapshot = 'Snapshot requested for Save\n'
        replace_text(snapshot)
        save_race = []

        def delay_save_response(route):
            response = route.fetch()
            assert response.ok, (response.status, response.text())
            assert race_target.read_bytes() == snapshot.encode(), 'The backend did not save the requested snapshot.'
            assert status.get_attribute('data-state') == 'saving', ('Pending Save status:', status.inner_text(), status.get_attribute('data-state'))
            append_text('Typed while Save was pending\n')
            save_race.append(value())
            route.fulfill(response=response)

        page.route('**/agent/canvas/save/', delay_save_response, times=1)
        try:
            with page.expect_response(lambda response: '/agent/canvas/save/' in response.url):
                save.click()
            page.wait_for_function('!TlamatiniCanvasEditing.busy')
        finally:
            page.unroute('**/agent/canvas/save/', delay_save_response)
        assert len(save_race) == 1, 'The delayed-response save scenario was not reached.'
        assert value() == snapshot + 'Typed while Save was pending\n', ('Save lost newer edits:', repr(value()))
        assert status.get_attribute('data-state') == 'dirty', ('Save race status:', status.inner_text(), status.get_attribute('data-state'))
        assert race_target.read_bytes() == snapshot.encode()
        checkpoint('typing-during-delayed-save-keeps-newer-edits-unsaved',
                   fault_injection='Actual backend response delivery withheld during a keyboard edit.')
        newest = value()
        direct_save(newest.encode(), race_target)

        # Hold the real backend File after reading, deliberately ignoring its abort
        # signal. This proves the late-data guard even if cancellation is too late.
        race_target.write_bytes(b'External disk content for delayed Refresh\n')
        page.evaluate('''() => {
            const source = canvasSource;
            const read = source.read;
            window.pendingEditRead = {source, read, waiting: false};
            source.read = async signal => {
                const file = await read(signal);
                return new Promise(resolve => {
                    pendingEditRead.release = () => resolve(file);
                    pendingEditRead.waiting = true;
                });
            };
        }''')
        try:
            page.locator('#reopen-canvas-button').click()
            page.wait_for_function('pendingEditRead.waiting && TlamatiniCanvasRefresh.busy')
            append_text('Typed while Refresh was pending\n')
        finally:
            page.evaluate('''() => {
                const pending = window.pendingEditRead;
                if (pending) {
                    pending.source.read = pending.read;
                    pending.release?.();
                    delete window.pendingEditRead;
                }
            }''')
        page.wait_for_function('!TlamatiniCanvasRefresh.busy && TlamatiniCanvasEditing.dirty')
        assert value() == newest + 'Typed while Refresh was pending\n', ('Refresh lost newer edits:', repr(value()))
        assert status.get_attribute('data-state') == 'dirty', ('Refresh race status:', status.inner_text(), status.get_attribute('data-state'))
        assert race_target.read_bytes() == b'External disk content for delayed Refresh\n'
        checkpoint('typing-during-delayed-refresh-rejects-late-disk-content',
                   fault_injection='Real backend File held during a keyboard edit; cancellation ignored by the test reader.')
        native_save(saved / 'race-recovered.txt', 'race-recovered')

        # Explicit delayed-reader injection: obtain the real File from the backend,
        # then hold its resolution beyond Save As. Deliberately ignore cancellation
        # in this test wrapper so the late completion actually reaches the guard.
        # A new destination must keep the visible snapshot, never the old disk read.
        before_pending_save = value()
        (saved / 'race-recovered.txt').write_bytes(b'External content pending Refresh\n')
        page.evaluate('''() => {
            const source = canvasSource;
            const read = source.read;
            window.pendingSaveRead = {source, read, waiting: false};
            source.read = async signal => {
                const file = await read(signal);
                return new Promise(resolve => {
                    pendingSaveRead.release = () => resolve(file);
                    pendingSaveRead.waiting = true;
                });
            };
        }''')
        save_during_refresh = saved / 'save-during-refresh.txt'
        try:
            page.locator('#reopen-canvas-button').click()
            page.wait_for_function('pendingSaveRead.waiting && TlamatiniCanvasRefresh.busy')
            native_save(save_during_refresh, 'save-during-refresh')
            assert save_during_refresh.read_bytes() == before_pending_save.encode()
        finally:
            page.evaluate('''() => {
                const pending = window.pendingSaveRead;
                if (pending) {
                    pending.source.read = pending.read;
                    pending.release?.();
                    delete window.pendingSaveRead;
                }
            }''')
        page.wait_for_function('!TlamatiniCanvasRefresh.busy && !TlamatiniCanvasEditing.busy')
        assert value() == before_pending_save, ('Late Refresh replaced saved text:', repr(value()), repr(before_pending_save))
        assert 'save-during-refresh.txt' in page.locator('#filename').inner_text()
        assert save_during_refresh.read_bytes() == before_pending_save.encode()
        checkpoint('save-as-during-pending-refresh-rejects-late-old-source',
                   fault_injection='Real backend File delivery held past Save As; cancellation ignored by the test reader.')

        # The visible text stays identical while another editor changes only its
        # encoding. Refresh must adopt the new bytes, BOM, and revision for Save.
        encoding_source = fixtures / 'encoding-only.txt'
        encoding_target = saved / 'encoding-only.txt'
        same_text = 'Same text: Español 日本語\n'
        encoding_source.write_bytes(same_text.encode())
        native_open(page, window, encoding_source)
        native_save(encoding_target, 'encoding-original')
        encoding_target.write_bytes(text_bytes(same_text, 'utf-16-le', b'\xff\xfe'))
        page.locator('#reopen-canvas-button').click()
        page.wait_for_function('!TlamatiniCanvasRefresh.busy && '
                               'document.querySelector("#reopen-canvas-button").dataset.state === "unchanged"')
        assert value() == same_text, ('Encoding-only Refresh changed text:', repr(value()), repr(same_text))
        assert 'UTF-16' in status.inner_text(), ('Encoding-only Refresh status:', status.inner_text(), status.get_attribute('data-state'))
        append_text('Saved after encoding-only Refresh\n')
        expected_encoding = text_bytes(same_text + 'Saved after encoding-only Refresh\n',
                                       'utf-16-le', b'\xff\xfe')
        direct_save(expected_encoding, encoding_target)
        checkpoint('encoding-only-refresh-updates-bom-format-and-save-revision')

    # Invalid new input must fail before the current document is discarded.
    # Observe whichever real alert surface the app uses; do not mock parsing.
    for label, rejected_bytes in (
            ('malformed-utf8', b'Invalid UTF-8: \xc3('),
            ('binary-as-text', b'Binary\x00\x01\x02content')):
        rejected = fixtures / f'{label}.txt'
        rejected.write_bytes(rejected_bytes)
        before_text = value()
        before_name = page.locator('#filename').inner_text()
        alerts = []

        def record_alert(dialog):
            assert dialog.type == 'alert', f'Unexpected browser dialog: {dialog.type}'
            alerts.append(dialog.message)
            dialog.accept()

        page.on('dialog', record_alert)
        try:
            window.activate()
            window.verify()
            page.locator('#open-button').click()
            choose_native_save(page, window, rejected, capture,
                               f'run-{attempt}/native-{label}-open.png', kind='Open')
            deadline = time.monotonic() + 15
            while not alerts and time.monotonic() < deadline:
                dialog = page.get_by_role('dialog').filter(has_text='Unable to')
                if dialog.count() and dialog.last.is_visible():
                    alerts.append(dialog.last.inner_text())
                    dialog.last.get_by_role('button', name='OK', exact=True).click()
                    break
                page.wait_for_timeout(100)
        finally:
            page.remove_listener('dialog', record_alert)
        assert alerts and ('Unable to' in alerts[0]), (label, alerts)
        assert value() == before_text, f'{label} destroyed the previous document.'
        assert page.locator('#filename').inner_text() == before_name
        assert encoding_target.read_bytes() == expected_encoding
        checkpoint(f'{label}-open-keeps-current-document', message=alerts[0])

    # Generated-document links share loadCanvas. Even when the user agrees to
    # replace a dirty document, failure while preparing the replacement must
    # keep the edited document and its working native Save destination.
    append_text('Keep these edits after a failed generated-file load\n')
    retained_text = value()
    retained_name = page.locator('#filename').inner_text()

    def generated_failure(filename, expected_status):
        with page.expect_response(lambda response: f'/agent/load_canvas/{filename}/' in response.url) as response_info:
            page.evaluate('''name => {
                window.generatedFailureDone = false;
                loadCanvas(name).then(result => {
                    window.generatedFailureResult = result;
                    window.generatedFailureDone = true;
                });
            }''', filename)
            warning = page.get_by_role('dialog').filter(has_text='Unsaved changes').last
            warning.wait_for(state='visible')
            warning.get_by_role('button', name='Continue', exact=True).click()
        assert response_info.value.status == expected_status
        alert = page.get_by_role('dialog').filter(has_text='Open file').last
        alert.wait_for(state='visible')
        message = alert.inner_text()
        assert 'existing canvas content was kept' in message
        alert.get_by_role('button', name='OK', exact=True).click()
        page.wait_for_function('window.generatedFailureDone')
        assert page.evaluate('window.generatedFailureResult') is False
        assert value() == retained_text, ('Failed generated load lost edits:', filename, repr(value()), repr(retained_text))
        assert page.locator('#filename').inner_text() == retained_name
        assert status.get_attribute('data-state') == 'dirty', ('Failed generated load status:', filename, status.inner_text(), status.get_attribute('data-state'))
        return message

    message = generated_failure(f'missing-generated-{attempt}.py', 404)
    checkpoint('missing-generated-document-keeps-unsaved-file-and-destination', message=message)
    refused_name = 'session-refused-generated.py'

    def refuse_generated_session(route):
        route.fulfill(status=401, content_type='application/json',
                      body='{"error":"Session refused for this injected case."}')

    page.route(f'**/agent/load_canvas/{refused_name}/', refuse_generated_session, times=1)
    try:
        message = generated_failure(refused_name, 401)
    finally:
        page.unroute(f'**/agent/load_canvas/{refused_name}/', refuse_generated_session)
    assert 'session expired' in message
    expected_retained = text_bytes(retained_text, 'utf-16-le', b'\xff\xfe')
    direct_save(expected_retained, encoding_target)
    checkpoint('generated-session-refusal-keeps-editable-source-and-working-save',
               fault_injection='HTTP 401 for one generated-document request; actual login remains intact.')

    # Editor controls stay usable in a real resized browser, including the
    # search panel, long-line wrapping, and toolbar rows without overlap.
    plain = fixtures / 'long-line.txt'
    plain.write_text('Needle ' + 'long text ' * 80 + '\n', encoding='utf-8')
    native_open(page, window, plain)
    page.locator('#canvas-find-button').click()
    search = page.locator('.cm-search input[name="search"]')
    search.wait_for(state='visible')
    search.fill('Needle')
    page.keyboard.press('Escape')
    wrap = page.locator('#canvas-wrap-button')
    before = wrap.get_attribute('aria-pressed')
    wrap.click()
    assert wrap.get_attribute('aria-pressed') != before
    window.resize(1060, 760)
    geometry = page.evaluate('''() => {
        const parent = document.querySelector('#filename-div').getBoundingClientRect();
        const buttons = [...document.querySelectorAll('#filename-div button')]
            .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
            .map(el => ({id:el.id, r:el.getBoundingClientRect().toJSON()}));
        return {parent:parent.toJSON(), buttons};
    }''')
    for index, item in enumerate(geometry['buttons']):
        rect = item['r']
        assert rect['left'] >= geometry['parent']['left'] - 1
        assert rect['right'] <= geometry['parent']['right'] + 1, item
        for other in geometry['buttons'][index + 1:]:
            r2 = other['r']
            overlap_x = min(rect['right'], r2['right']) - max(rect['left'], r2['left'])
            overlap_y = min(rect['bottom'], r2['bottom']) - max(rect['top'], r2['top'])
            assert overlap_x <= 1 or overlap_y <= 1, (item, other)
    checkpoint('find-wrap-and-narrow-toolbar-without-overlap')
    window.resize(1440, 900)

    pdf = fixtures / 'read-only.pdf'
    write_pdf(pdf, 'Canvas PDF remains a PDF', pages=2)
    native_open(page, window, pdf)
    page.wait_for_function('window.TlamatiniPdfCanvas?.active')
    assert not editor.is_visible()
    assert page.locator('#canvas-undo-button').is_disabled()
    assert page.locator('#canvas-redo-button').is_disabled()
    pdf_target = saved / 'read-only-copy.pdf'
    native_save(pdf_target, 'pdf-original-bytes')
    assert pdf_target.read_bytes() == pdf.read_bytes(), 'PDF Save As did not preserve PDF bytes.'
    checkpoint('pdf-remains-viewer-and-saves-original-bytes')

    browser_handle_case()
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
    user, _ = get_user_model().objects.get_or_create(username='canvas-editing-review')
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
        context.route_web_socket('**/ws/**', lambda socket: socket.on_message(lambda message: sent.append(message)))
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
        page.locator('#id_username').fill('canvas-editing-review')
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
