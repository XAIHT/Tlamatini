"""Physical desktop coordinates for Mouser (also copied to isolated runs)."""

import ctypes
import math
import os
import time


def configure_dpi_awareness():
    """Set per-monitor awareness before importing PyAutoGUI or reading geometry."""
    if os.name != 'nt':
        return
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    # Thread awareness also works when a host already set process awareness.
    try:
        setter = user32.SetThreadDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
        if setter(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except AttributeError:
        pass
    try:
        setter = ctypes.WinDLL('shcore').SetProcessDpiAwareness
        setter.argtypes = [ctypes.c_int]
        setter.restype = ctypes.c_long
        if setter(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    raise RuntimeError('Cannot establish physical, per-monitor desktop coordinates')


def desktop_geometry():
    """Return physical monitor rectangles, including negative origins and gaps."""
    import win32api

    rectangles = [tuple(map(int, rect)) for _, _, rect in win32api.EnumDisplayMonitors()]
    if not rectangles:
        raise RuntimeError('No interactive monitors are available')
    left = min(r[0] for r in rectangles)
    top = min(r[1] for r in rectangles)
    right = max(r[2] for r in rectangles)
    bottom = max(r[3] for r in rectangles)
    return {'left': left, 'top': top, 'width': right - left,
            'height': bottom - top, 'monitors': rectangles}


def checked_point(x, y, geometry):
    """Reject off-screen and monitor-gap coordinates; never silently clamp."""
    x, y = round(float(x)), round(float(y))
    if not any(left <= x < r and t <= y < b for left, t, r, b in geometry['monitors']):
        raise ValueError(f'Point ({x}, {y}) does not lie on an attached monitor')
    return x, y


def select_window(config):
    """Resolve a unique visible application window, or an explicit HWND/index."""
    import win32gui

    handle = config.get('window_handle', 0)
    handle = int(str(handle), 0) if isinstance(handle, str) else int(handle or 0)
    title = str(config.get('window_title') or '').strip().casefold()
    if handle:
        if not win32gui.IsWindow(handle):
            raise ValueError('window_handle no longer exists')
        if title and title not in win32gui.GetWindowText(handle).casefold():
            raise ValueError('window_handle does not match window_title')
        return handle
    if not title:
        raise ValueError('A window_title or window_handle is required')
    matches = []

    def collect(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and title in win32gui.GetWindowText(hwnd).casefold():
            matches.append(hwnd)
        return True

    win32gui.EnumWindows(collect, None)
    index = int(config.get('window_match_index', -1))
    if not matches:
        raise ValueError('No window matches window_title')
    if index < 0:
        if len(matches) != 1:
            raise ValueError(f'Ambiguous window_title: {len(matches)} matches; specify window_handle')
        return matches[0]
    if index >= len(matches):
        raise ValueError('window_match_index is outside the matched window list')
    return matches[index]


def focus_window(hwnd, timeout=2.0):
    import win32con
    import win32gui

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass  # Only the observed foreground handle establishes success.
    deadline = time.monotonic() + timeout
    while win32gui.GetForegroundWindow() != hwnd:
        if time.monotonic() >= deadline:
            raise RuntimeError('Windows did not grant foreground focus to the target')
        time.sleep(0.05)


def window_rectangle(hwnd, area='client'):
    import win32gui

    if area == 'window':
        left, t, r, b = win32gui.GetWindowRect(hwnd)
    elif area == 'client':
        left, t, r, b = win32gui.GetClientRect(hwnd)
        left, t = win32gui.ClientToScreen(hwnd, (left, t))
        r, b = win32gui.ClientToScreen(hwnd, (r, b))
    else:
        raise ValueError('window_area must be client or window')
    if r <= left or b <= t:
        raise ValueError('Target window has no usable rectangle')
    return left, t, r - left, b - t


def resolve_point(x, y, config, geometry, window_rect=None):
    """Convert an explicitly named coordinate space into physical screen pixels.

    Screenshot mapping requires the physical capture rectangle. It must describe
    the actual image (including cropping); it is never inferred from the current
    desktop, which might have changed since capture.
    """
    x, y = float(x), float(y)
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError('Coordinates must be finite numbers')
    space = str(config.get('coordinate_space', 'screen')).lower()
    if space == 'screen':
        return checked_point(x, y, geometry)
    if space in ('desktop', 'normalized'):
        left, t, w, h = (geometry[k] for k in ('left', 'top', 'width', 'height'))
    elif space in ('window', 'window_normalized'):
        if window_rect is None:
            raise ValueError('Window coordinates require a resolved window rectangle')
        left, t, w, h = window_rect
    elif space == 'screenshot':
        values = [config.get(k) for k in ('capture_left', 'capture_top', 'capture_width', 'capture_height')]
        if any(v is None for v in values):
            raise ValueError('Screenshot coordinates require the physical capture rectangle')
        left, t, w, h = map(float, values)
        iw, ih = float(config.get('image_width', 0)), float(config.get('image_height', 0))
        if not all(math.isfinite(v) for v in (left, t, w, h, iw, ih)) or min(w, h, iw, ih) <= 0:
            raise ValueError('Capture and image dimensions must be finite and positive')
        if not (0 <= x < iw and 0 <= y < ih):
            raise ValueError('Point is outside the analyzed image')
        # x/y are pixel coordinates in the image actually seen by the model.
        return checked_point(left + min(round(x * w / iw), w - 1),
                             t + min(round(y * h / ih), h - 1), geometry)
    else:
        raise ValueError(f'Unknown coordinate_space: {space}')
    if space in ('normalized', 'window_normalized'):
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError('Normalized coordinates must be in [0, 1]')
        x, y = x * (w - 1), y * (h - 1)
    elif not (0 <= x < w and 0 <= y < h):
        raise ValueError('Point is outside its coordinate rectangle')
    return checked_point(left + min(round(x), w - 1), t + min(round(y), h - 1), geometry)


def verify_window_point(hwnd, point):
    """Refuse a click when focus changed or another window covers the point."""
    import win32gui

    if win32gui.GetForegroundWindow() != hwnd:
        raise RuntimeError('Target lost foreground focus before the mouse action')
    hit = win32gui.WindowFromPoint(point)
    if hit != hwnd and not win32gui.IsChild(hwnd, hit):
        raise RuntimeError('Target point is covered by a different window')
