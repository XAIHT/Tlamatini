"""Tkinter-free native file/folder pickers for the Tlamatini server.

Why this exists
---------------
The Set-DB / Backup-DB "Browse" buttons need a real, absolute filesystem
path from the machine running the server (the browser sandbox cannot
provide one). The previous implementation drove a hidden ``tkinter`` Tk
root + ``filedialog`` — which forced the frozen build to bundle the entire
Tcl/Tk data tree (``init.tcl`` etc.). That bundling was fragile and
repeatedly failed with *"Can't find a usable init.tcl"*, leaving the
picker dead in frozen builds.

This module replaces tkinter with the Win32 common dialogs accessed
directly through ``ctypes``:

  * **File picker**  -> ``comdlg32.GetOpenFileNameW``
  * **Folder picker** -> ``shell32.SHBrowseForFolderW`` + ``SHGetPathFromIDListW``

``comdlg32.dll`` and ``shell32.dll`` ship with **every** Windows install,
so there is nothing to bundle and nothing to go missing — the server no
longer depends on Tcl/Tk at all. On non-Windows hosts these helpers raise
``NativeDialogUnavailable`` so the caller can fall back to manual path
entry (Tlamatini is Windows-primary).

The dialogs are modal and block the calling thread until the user picks
or cancels; callers run them on a dedicated thread (see
``views._run_native_picker``).
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple


class NativeDialogUnavailable(RuntimeError):
    """Raised when no native dialog can be shown on this host."""


def is_supported() -> bool:
    """True when native Win32 dialogs are available (Windows only)."""
    return os.name == "nt"


# --------------------------------------------------------------------------- #
# ctypes structure builders (lazy — ctypes.wintypes is Windows-only)
# --------------------------------------------------------------------------- #
def _openfilenamew_cls():
    """Return the ``OPENFILENAMEW`` ctypes.Structure class.

    Defined lazily because ``ctypes.wintypes`` only imports on Windows.
    Field order/types mirror the Win32 ``OPENFILENAMEW`` struct exactly;
    ``test_native_dialogs`` pins ``ctypes.sizeof`` so a layout mistake is
    caught without opening a dialog.
    """
    import ctypes
    from ctypes import wintypes

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    return OPENFILENAMEW


def _browseinfow_cls():
    """Return the ``BROWSEINFOW`` ctypes.Structure class (lazy)."""
    import ctypes
    from ctypes import wintypes

    class BROWSEINFOW(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", ctypes.c_void_p),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
        ]

    return BROWSEINFOW


def _struct_sizes() -> dict:
    """Diagnostic/test hook: ctypes.sizeof of each dialog struct.

    Windows-only (the structs use ``ctypes.wintypes``). On a 64-bit build
    the expected sizes are OPENFILENAMEW=152, BROWSEINFOW=64.
    """
    if os.name != "nt":
        raise NativeDialogUnavailable("Win32 structs are Windows-only")
    import ctypes
    return {
        "OPENFILENAMEW": ctypes.sizeof(_openfilenamew_cls()),
        "BROWSEINFOW": ctypes.sizeof(_browseinfow_cls()),
    }


# --------------------------------------------------------------------------- #
# COM init helpers (folder browser needs an STA; file dialog benefits from it)
# --------------------------------------------------------------------------- #
def _co_initialize() -> bool:
    """CoInitialize the current thread as an STA. Returns True if we
    initialized it (and therefore own the matching ``CoUninitialize``).

    ``RPC_E_CHANGED_MODE`` (0x80010106) means the thread was already
    initialized with a different model — harmless; we just don't undo it.
    """
    import ctypes
    try:
        hr = ctypes.windll.ole32.CoInitialize(None)
    except Exception:  # noqa: BLE001 — ole32 should always be present
        return False
    # S_OK (0) or S_FALSE (1) -> we initialized; we own the matching uninit.
    return hr in (0, 1)


def _co_uninitialize(owned: bool) -> None:
    if not owned:
        return
    import ctypes
    try:
        ctypes.windll.ole32.CoUninitialize()
    except Exception:  # noqa: BLE001
        pass


def _force_window_foreground(hwnd) -> None:
    """Drag *hwnd* to the foreground from our background (server) process.

    A window created by a process that is NOT the foreground process is
    normally denied activation by Windows — it just blinks in the taskbar.
    That is exactly the "folder picker hides in the taskbar without the
    user noticing" report. We:

      1. make the window **topmost** (a pure z-order change that needs no
         foreground rights, so the dialog is *visible above the browser*
         even when step 2 is refused), then
      2. use the documented ``AttachThreadInput`` dance to bypass the
         foreground lock and actually give it focus.

    Every call is best-effort and never raises — failing to grab focus
    must not break the picker.
    """
    if not hwnd:
        return
    import ctypes
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        HWND_TOPMOST = -1
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        SW_SHOW = 5

        user32.ShowWindow(hwnd, SW_SHOW)
        # 1) Visibility — works cross-thread/process without focus rights.
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW,
        )

        # 2) Focus — attach our input queue to the current foreground
        #    thread so SetForegroundWindow is permitted.
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        our_tid = kernel32.GetCurrentThreadId()
        attached = False
        if fg_tid and fg_tid != our_tid:
            attached = bool(user32.AttachThreadInput(fg_tid, our_tid, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_tid, our_tid, False)
    except Exception:  # noqa: BLE001 — focus help must never break the picker
        pass


# --------------------------------------------------------------------------- #
# File picker — comdlg32.GetOpenFileNameW
# --------------------------------------------------------------------------- #
def pick_open_file(
    title: str,
    filter_pairs: Optional[List[Tuple[str, str]]] = None,
    initial_dir: str = "",
) -> str:
    """Show the native "Open File" dialog.

    Args:
        title: dialog caption.
        filter_pairs: list of ``(label, pattern)`` tuples, e.g.
            ``[("SQLite database (db.sqlite3)", "db.sqlite3"), ("All files", "*.*")]``.
        initial_dir: starting directory (optional).

    Returns:
        The chosen absolute path, or ``""`` if the user canceled.

    Raises:
        NativeDialogUnavailable: not on Windows.
        RuntimeError: the dialog reported an error (CommDlgExtendedError).
    """
    if os.name != "nt":
        raise NativeDialogUnavailable("native file dialog requires Windows")

    import ctypes
    from ctypes import wintypes

    comdlg32 = ctypes.windll.comdlg32
    OPENFILENAMEW = _openfilenamew_cls()

    OFN_HIDEREADONLY = 0x00000004
    OFN_NOCHANGEDIR = 0x00000008
    OFN_PATHMUSTEXIST = 0x00000800
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_EXPLORER = 0x00080000

    if not filter_pairs:
        filter_pairs = [("All files (*.*)", "*.*")]
    # comdlg32 wants a double-NUL-terminated "label\0pattern\0...\0\0" block.
    filter_str = ""
    for label, pattern in filter_pairs:
        filter_str += f"{label}\0{pattern}\0"
    filter_str += "\0"
    filter_buf = ctypes.create_unicode_buffer(filter_str)

    buf_len = 4096
    file_buf = ctypes.create_unicode_buffer(buf_len)  # zero-initialized

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = None
    ofn.lpstrFilter = ctypes.cast(filter_buf, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(file_buf, wintypes.LPWSTR)
    ofn.nMaxFile = buf_len
    ofn.lpstrTitle = title or None
    ofn.lpstrInitialDir = initial_dir or None
    ofn.Flags = (
        OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST
        | OFN_HIDEREADONLY | OFN_EXPLORER | OFN_NOCHANGEDIR
    )

    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetOpenFileNameW.restype = wintypes.BOOL

    # GetOpenFileName has no init callback (without a hook proc), so a tiny
    # watcher thread finds the dialog window — the only visible top-level
    # window owned by THIS thread once the dialog is up — and pulls it to
    # the foreground, mirroring the folder browser's behavior.
    import threading
    import time as _time

    picker_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    _stop = {"done": False}

    def _raise_dialog_when_shown():
        user32 = ctypes.windll.user32
        EnumThreadWndProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        deadline = _time.time() + 5.0
        while not _stop["done"] and _time.time() < deadline:
            hits = []

            def _collect(hwnd, lparam):
                try:
                    if user32.IsWindowVisible(hwnd):
                        hits.append(hwnd)
                except Exception:  # noqa: BLE001
                    pass
                return True

            try:
                user32.EnumThreadWindows(picker_tid, EnumThreadWndProc(_collect), 0)
            except Exception:  # noqa: BLE001
                pass
            if hits:
                _force_window_foreground(hits[0])
                return
            _time.sleep(0.05)

    watcher = threading.Thread(
        target=_raise_dialog_when_shown,
        name="tlamatini-picker-foreground", daemon=True,
    )
    watcher.start()

    owned = _co_initialize()
    try:
        ok = comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    finally:
        _stop["done"] = True
        _co_uninitialize(owned)

    if not ok:
        # 0 -> user canceled (CommDlgExtendedError() == 0) OR a real error.
        ext_err = 0
        try:
            ext_err = int(comdlg32.CommDlgExtendedError())
        except Exception:  # noqa: BLE001
            ext_err = 0
        if ext_err:
            raise RuntimeError(
                f"GetOpenFileName failed (CommDlgExtendedError=0x{ext_err:04X})"
            )
        return ""  # user canceled — not an error
    return file_buf.value or ""


# --------------------------------------------------------------------------- #
# Folder picker — shell32.SHBrowseForFolderW
# --------------------------------------------------------------------------- #
def pick_folder(title: str) -> str:
    """Show the native folder-browser dialog.

    Returns the chosen absolute directory, or ``""`` if canceled.

    Raises:
        NativeDialogUnavailable: not on Windows.
        RuntimeError: the shell could not resolve the chosen item to a path.
    """
    if os.name != "nt":
        raise NativeDialogUnavailable("native folder dialog requires Windows")

    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    BROWSEINFOW = _browseinfow_cls()

    BIF_RETURNONLYFSDIRS = 0x00000001
    BIF_EDITBOX = 0x00000010
    BIF_NEWDIALOGSTYLE = 0x00000040  # resizable, "Make New Folder" button
    BFFM_INITIALIZED = 1

    # The folder browser opens behind the browser and only blinks in the
    # taskbar unless we pull it forward when it initializes. SHBrowseForFolder
    # hands us the dialog HWND in this callback, which is the clean hook.
    BrowseCallbackProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HWND, wintypes.UINT,
        wintypes.LPARAM, wintypes.LPARAM,
    )

    def _bff_callback(hwnd, msg, lparam, lpdata):
        if msg == BFFM_INITIALIZED:
            _force_window_foreground(hwnd)
        return 0

    _callback = BrowseCallbackProc(_bff_callback)  # keep a ref alive

    owned = _co_initialize()
    try:
        display_buf = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFOW()
        bi.hwndOwner = None
        bi.pidlRoot = None
        bi.pszDisplayName = ctypes.cast(display_buf, wintypes.LPWSTR)
        bi.lpszTitle = title or None
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_EDITBOX | BIF_NEWDIALOGSTYLE
        bi.lpfn = ctypes.cast(_callback, ctypes.c_void_p)
        bi.lParam = 0
        bi.iImage = 0

        shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
        shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return ""  # user canceled

        try:
            path_buf = ctypes.create_unicode_buffer(4096)
            shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR]
            shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
            got = shell32.SHGetPathFromIDListW(
                pidl, ctypes.cast(path_buf, wintypes.LPWSTR)
            )
            if not got:
                raise RuntimeError(
                    "SHGetPathFromIDList could not resolve the selection to a "
                    "filesystem path (a virtual/special folder was chosen)."
                )
            return path_buf.value or ""
        finally:
            # Free the PIDL the shell allocated for us.
            try:
                ole32.CoTaskMemFree(pidl)
            except Exception:  # noqa: BLE001
                pass
    finally:
        _co_uninitialize(owned)
