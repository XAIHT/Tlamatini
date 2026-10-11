# Tlamatini Author Banner — Angela López Mendoza
"""Native Windows browser sizing: no viewport emulation or off-screen evidence."""
import ctypes
import os

import psutil
import win32api
import win32con
import win32gui
import win32process


class VisibleWindow:
    def __init__(self, page, context):
        self.page = page
        self.session = context.new_cdp_session(page)
        self.session.send('Network.enable')
        self.session.send('Network.setCacheDisabled', {'cacheDisabled': True})
        pids = {p.pid for p in psutil.Process(os.getpid()).children(recursive=True)}
        windows = []
        win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd) if (
            win32gui.GetClassName(hwnd).startswith('Chrome_WidgetWin')
            and win32process.GetWindowThreadProcessId(hwnd)[1] in pids
            and win32gui.IsWindowVisible(hwnd)) else None, None)
        if not windows:
            raise RuntimeError('No visible owned Chrome window; no tests will run.')
        self.hwnd = max(windows, key=lambda h: win32gui.GetWindowRect(h)[2] - win32gui.GetWindowRect(h)[0])
        self.work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))['Work']
        self.activate()

    def activate(self):
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        current = win32api.GetCurrentThreadId()
        foreground = win32gui.GetForegroundWindow()
        other, _ = win32process.GetWindowThreadProcessId(foreground)
        try:
            if current != other:
                win32process.AttachThreadInput(current, other, True)
            if foreground != self.hwnd:
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            win32gui.SetForegroundWindow(self.hwnd)
        finally:
            if current != other:
                win32process.AttachThreadInput(current, other, False)

    def verify(self):
        assert win32gui.IsWindowVisible(self.hwnd) and not win32gui.IsIconic(self.hwnd)
        assert win32gui.GetForegroundWindow() == self.hwnd, 'Test Chrome lost foreground; stop the test.'
        cloaked = ctypes.c_int()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(self.hwnd), 14, ctypes.byref(cloaked), 4)
        assert cloaked.value == 0, 'Chrome is cloaked on a different desktop.'
        r = win32gui.GetWindowRect(self.hwnd)
        left, top, right, bottom = self.work
        assert left <= r[0] < r[2] <= right and top <= r[1] < r[3] <= bottom, (r, self.work)
        g = self.page.evaluate('({w:innerWidth,h:innerHeight,ow:outerWidth,oh:outerHeight,dpr:devicePixelRatio,x:scrollX,y:scrollY})')
        # Native browser zoom changes dpr and innerWidth together. A fixed
        # emulated viewport cannot pass this real client-width comparison.
        client = win32gui.GetClientRect(self.hwnd)
        assert abs(g['w'] * g['dpr'] - client[2]) <= 4, (g, client)
        return {'window': r, 'work_area': self.work, 'client': client, 'page': g}

    def resize(self, width, height):
        self.activate()
        g = self.page.evaluate('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio})')
        r = win32gui.GetWindowRect(self.hwnd)
        chrome_w = (r[2] - r[0]) - g['w'] * g['dpr']
        chrome_h = (r[3] - r[1]) - g['h'] * g['dpr']
        left, top, right, bottom = self.work
        w = min(right - left - 40, round(width * g['dpr'] + chrome_w))
        h = min(bottom - top - 40, round(height * g['dpr'] + chrome_h))
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, left + 20, top + 20, w, h,
                             win32con.SWP_SHOWWINDOW)
        self.page.wait_for_timeout(700)
        return self.verify()

    def release(self):
        if win32gui.IsWindow(self.hwnd):
            win32gui.SetWindowPos(self.hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                 win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
