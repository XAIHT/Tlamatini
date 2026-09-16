"""Checked Windows keyboard input without changing the clipboard."""

import ctypes
from ctypes import wintypes
import time


class _MouseInput(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD),
                ('wParamH', wintypes.WORD)]


class _InputUnion(ctypes.Union):
    _fields_ = [('mi', _MouseInput), ('ki', _KeyboardInput), ('hi', _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('data', _InputUnion)]


def _user32():
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    api.SendInput.restype = wintypes.UINT
    return api


def _send(events):
    records = (_Input * len(events))(*events)
    sent = _user32().SendInput(len(records), records, ctypes.sizeof(_Input))
    if sent != len(records):
        raise RuntimeError(f'SendInput inserted {sent}/{len(records)} events; input may be blocked')


def _event(vk=0, scan=0, flags=0):
    return _Input(type=1, data=_InputUnion(ki=_KeyboardInput(vk, scan, flags, 0, 0)))


_KEYS = {
    'backspace': 0x08, 'tab': 0x09, 'enter': 0x0D, 'shift': 0x10,
    'ctrl': 0x11, 'alt': 0x12, 'pause': 0x13, 'capslock': 0x14,
    'esc': 0x1B, 'space': 0x20, 'pageup': 0x21, 'pagedown': 0x22,
    'end': 0x23, 'home': 0x24, 'left': 0x25, 'up': 0x26,
    'right': 0x27, 'down': 0x28, 'printscreen': 0x2C, 'insert': 0x2D,
    'delete': 0x2E, 'win': 0x5B, 'winleft': 0x5B, 'winright': 0x5C,
    'apps': 0x5D, 'numlock': 0x90, 'scrolllock': 0x91,
    'shiftleft': 0xA0, 'shiftright': 0xA1, 'ctrlleft': 0xA2,
    'ctrlright': 0xA3, 'altleft': 0xA4, 'altright': 0xA5,
}
_KEYS.update({chr(c).lower(): c for c in range(ord('A'), ord('Z') + 1)})
_KEYS.update({str(n): ord(str(n)) for n in range(10)})
_KEYS.update({f'f{n}': 0x6F + n for n in range(1, 25)})
_MODIFIERS = {'shift', 'ctrl', 'alt', 'win', 'shiftleft', 'shiftright',
              'ctrlleft', 'ctrlright', 'altleft', 'altright', 'winleft', 'winright'}
_EXTENDED = {'pageup', 'pagedown', 'end', 'home', 'left', 'right', 'up', 'down',
             'insert', 'delete', 'win', 'winleft', 'winright', 'apps',
             'ctrlright', 'altright', 'numlock', 'printscreen'}


def validate_keys(keys):
    for key in keys:
        if key not in _KEYS:
            raise ValueError(f'Unsupported Windows key: {key}')


def send_keys(keys, guard):
    """Hold modifiers and tap each nonmodifier, releasing owned keys on errors."""
    validate_keys(keys)
    held = []
    try:
        for key in keys:
            guard()
            flags = 1 if key in _EXTENDED else 0
            # Track before send: a failed call may still have inserted key-down.
            held.append((key, flags))
            _send([_event(vk=_KEYS[key], flags=flags)])
            if key not in _MODIFIERS:
                _send([_event(vk=_KEYS[key], flags=flags | 2)])
                held.pop()
    finally:
        release_error = None
        for key, flags in reversed(held):
            try:
                _send([_event(vk=_KEYS[key], flags=flags | 2)])
            except Exception as exc:
                release_error = exc
        if release_error is not None:
            raise release_error


def send_character(char, guard):
    guard()
    if char in ('\n', '\r', '\t'):
        send_keys(['tab' if char == '\t' else 'enter'], guard)
        return
    data = char.encode('utf-16-le')
    units = [int.from_bytes(data[i:i + 2], 'little') for i in range(0, len(data), 2)]
    events = []
    for unit in units:
        events.extend([_event(scan=unit, flags=4), _event(scan=unit, flags=6)])
    try:
        _send(events)
    except Exception:
        # A short insertion could leave VK_PACKET down. Release all owned units.
        for unit in units:
            try:
                _send([_event(scan=unit, flags=6)])
            except Exception:
                pass
        raise


def bind_target(config):
    """Select once, then pin HWND/PID; never silently switch to a new window."""
    import win32con
    import win32gui
    import win32process

    title = str(config.get('window_title') or '').strip().casefold()
    raw = config.get('window_handle', 0)
    hwnd = int(str(raw), 0) if isinstance(raw, str) else int(raw or 0)
    if not hwnd and title:
        matches = []

        def collect(handle, _):
            if win32gui.IsWindowVisible(handle) and title in win32gui.GetWindowText(handle).casefold():
                matches.append(handle)
            return True

        win32gui.EnumWindows(collect, None)
        index = int(config.get('window_match_index', -1))
        if index < 0:
            if len(matches) != 1:
                raise ValueError(f'Expected one target window; found {len(matches)}')
            hwnd = matches[0]
        elif index >= len(matches):
            raise ValueError('window_match_index is outside the matched window list')
        else:
            hwnd = matches[index]
    if not hwnd:
        hwnd = win32gui.GetForegroundWindow()
    if not hwnd or not win32gui.IsWindow(hwnd):
        raise ValueError('No valid target window exists')
    if title and title not in win32gui.GetWindowText(hwnd).casefold():
        raise ValueError('window_handle does not match window_title')
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        deadline = time.monotonic() + 2.0
        while win32gui.GetForegroundWindow() != hwnd:
            if time.monotonic() >= deadline:
                raise RuntimeError('Windows did not grant focus to the requested window')
            time.sleep(0.05)
    return hwnd, win32process.GetWindowThreadProcessId(hwnd)[1]


def verify_target(target):
    import win32gui
    import win32process

    hwnd, pid = target
    if (not win32gui.IsWindow(hwnd) or win32gui.GetForegroundWindow() != hwnd or
            win32process.GetWindowThreadProcessId(hwnd)[1] != pid):
        raise RuntimeError('Target window lost focus or was replaced; remaining input cancelled')


def ensure_modifiers_released():
    api = _user32()
    for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
        if api.GetAsyncKeyState(vk) & 0x8000:
            raise RuntimeError('A modifier is already held; refusing to mix with user input')
