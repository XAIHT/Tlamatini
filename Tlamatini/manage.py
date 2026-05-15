#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
# This must be set BEFORE importing any packages that use MKL (NumPy, SciPy, etc.)
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'


def _set_app_user_model_id():
    """Set the explicit AppUserModelID for taskbar identity.

    Must be called BEFORE any window is created.  This ensures that:
    - The running window groups with the pinned desktop shortcut
    - "Pin to taskbar" from the running instance preserves the Tlamatini icon
    - The process is identified distinctly even when hosted by Windows Terminal

    The ID follows Microsoft's recommended CompanyName.ProductName.SubProduct
    pattern.  Failures are silent — identity is cosmetic.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "XAIHT.Tlamatini.Server"
        )
    except Exception:
        pass


_set_app_user_model_id()


def _brand_console_window():
    """Set the console window's title and icon as early as possible.

    - SetConsoleTitleW: honored by BOTH conhost AND Windows Terminal. So even
      when WT is the host, the tab title becomes "Tlamatini" instead of the
      cmd path.
    - WM_SETICON + LoadImageW: honored by conhost (and respected by every
      icon-displaying surface that reads the window's icon). WT ignores it,
      but it costs nothing and reinforces the icon under conhost.

    Failures here are silent — branding is cosmetic and must never block
    server start-up.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        # 1. Window title — works under any host (conhost / WT / future).
        kernel32.SetConsoleTitleW("Tlamatini")

        # 2. Window icon — locate Tlamatini.ico next to the .exe (frozen) or
        # at the project root (source mode).
        if getattr(sys, 'frozen', False):
            install_dir = os.path.dirname(sys.executable)
        else:
            install_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        ico_path = os.path.join(install_dir, 'Tlamatini.ico')
        if not os.path.isfile(ico_path):
            return

        IMAGE_ICON     = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE  = 0x00000040
        WM_SETICON     = 0x0080
        ICON_SMALL     = 0
        ICON_BIG       = 1

        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR,
            wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SendMessageW.restype = ctypes.c_long
        user32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        kernel32.GetConsoleWindow.restype = wintypes.HWND

        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        # Two LoadImageW calls — one large, one small — so both the title
        # bar (small) and Alt-Tab / taskbar (large) get crisp renderings.
        hicon_small = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 16, 16,
            LR_LOADFROMFILE,
        )
        hicon_big = user32.LoadImageW(
            None, ico_path, IMAGE_ICON, 32, 32,
            LR_LOADFROMFILE,
        )
        if not hicon_big:
            hicon_big = user32.LoadImageW(
                None, ico_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
    except Exception:
        pass


_brand_console_window()


class _TeeStream:
    """Duplicates writes to the original console stream and a log file."""

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, data):
        self._original.write(data)
        try:
            self._log_file.write(data)
            self._log_file.flush()
        except Exception:
            pass
        return len(data) if isinstance(data, str) else None

    def flush(self):
        self._original.flush()
        try:
            self._log_file.flush()
        except Exception:
            pass

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def __getattr__(self, name):
        return getattr(self._original, name)


def _setup_log_tee():
    """Redirect stdout and stderr to both the console and tlamatini.log."""
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))

    log_path = os.path.join(log_dir, 'tlamatini.log')
    try:
        log_file = open(log_path, 'w', encoding='utf-8')  # noqa: SIM115
    except OSError:
        return

    sys.stdout = _TeeStream(sys.stdout, log_file)
    sys.stderr = _TeeStream(sys.stderr, log_file)


_setup_log_tee()


def _print_version_banner():
    """Print the running Tlamatini version on every startup.

    Lands in both stdout AND ``tlamatini.log`` (the tee is already
    installed by the time we run).  Cheap, never raises, and gives oncall
    a one-line answer to "what's actually deployed here?" without having
    to hit ``/agent/version/``.  See VERSIONING.md.
    """
    try:
        from agent.version import get_version
        version = get_version()
    except Exception:
        version = "0.0.0+unknown"
    print(f"--- [VERSION] Tlamatini {version}")


_print_version_banner()


def _resolve_db_folder_root():
    """Directory that hosts the user-facing ``DB/ToLoad`` and ``DB/Older``
    trees.  In frozen mode this lives next to ``Tlamatini.exe`` (the
    installation root the user can browse to); in source mode it sits next
    to ``manage.py``.  Kept in sync with the user-spec:

      Frozen:   <Drive>:\\<InstallationDir>\\Tlamatini\\DB\\ToLoad\\
      Source:   <Drive>:\\<DevelopmentOptionalDir>\\Tlamatini\\Tlamatini\\DB\\ToLoad\\
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'DB')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'DB')


def _resolve_live_db_path():
    """Absolute path of the live ``db.sqlite3`` file Django will open.

    Mirrors ``settings.py``'s ``BASE_DIR / 'db.sqlite3'`` computation
    without importing Django (this runs BEFORE Django is touched):

      * Source: ``<manage.py dir>/db.sqlite3``
      * Frozen: ``<_MEIPASS>/db.sqlite3`` — same place Django will resolve
        ``BASE_DIR`` to, because ``BASE_DIR`` is derived from the bundled
        ``tlamatini/settings.py``'s ``__file__``, which lives inside
        ``_MEIPASS``.  Falls back to the executable directory when
        ``_MEIPASS`` is not set.
    """
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return os.path.join(meipass, 'db.sqlite3')
        return os.path.join(os.path.dirname(sys.executable), 'db.sqlite3')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.sqlite3')


def _apply_pending_db_swap():
    """Replace the live ``db.sqlite3`` with the one in ``DB/ToLoad`` (if any).

    Executed BEFORE any Django import so Django opens the swapped file from
    the very first connection.  Sequence (only if ``DB/ToLoad/db.sqlite3``
    exists):

      1. ``DB/Older/<timestamp>/`` is created.
      2. The current live ``db.sqlite3`` (if any) is *moved* into that
         timestamped directory so the user keeps an audit trail.
      3. ``DB/ToLoad/db.sqlite3`` is *moved* on top of the live path.

    Both moves use :func:`shutil.move` (rename-where-possible, copy+delete
    across filesystems) so the source files are removed once the swap
    completes — a re-launch with the same files in place is a no-op.

    Failures are caught and logged: a corrupt/locked DB must not stop
    Tlamatini from starting up at all.
    """
    import shutil  # local — avoid earliest-startup cost when no swap pending
    import datetime

    try:
        db_root = _resolve_db_folder_root()
        to_load_path = os.path.join(db_root, 'ToLoad', 'db.sqlite3')
        older_root = os.path.join(db_root, 'Older')

        if not os.path.isfile(to_load_path):
            return  # nothing to swap; common case

        live_db_path = _resolve_live_db_path()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        archive_dir = os.path.join(older_root, timestamp)
        os.makedirs(archive_dir, exist_ok=True)

        if os.path.isfile(live_db_path):
            archived_target = os.path.join(archive_dir, 'db.sqlite3')
            shutil.move(live_db_path, archived_target)
            print(f"--- [DB SWAP] Archived previous db.sqlite3 -> {archived_target}")
        else:
            print(f"--- [DB SWAP] No previous db.sqlite3 found at {live_db_path}")

        live_parent = os.path.dirname(live_db_path)
        if live_parent:
            os.makedirs(live_parent, exist_ok=True)
        shutil.move(to_load_path, live_db_path)
        print(f"--- [DB SWAP] Loaded DB/ToLoad/db.sqlite3 -> {live_db_path}")
    except Exception as exc:
        print(f"--- [DB SWAP] Skipped due to error: {exc}")


_apply_pending_db_swap()


def _schedule_browser_open(url: str, delay_seconds: float = 10.0) -> None:
    """Open the default browser at *url* after *delay_seconds*.

    Used when the desktop/taskbar shortcut launches Tlamatini.exe directly
    (no PowerShell wrapper) so users still get the auto-open behavior the
    legacy Tlamatini.ps1 wrapper provided.
    """
    import threading
    import webbrowser

    def _open():
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"--- [BROWSER] Failed to open {url}: {e}")

    timer = threading.Timer(delay_seconds, _open)
    timer.daemon = True
    timer.start()
    print(f"--- [BROWSER] {url} will open in {int(delay_seconds)} seconds...")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tlamatini.settings')

    # --- .FLW File Association Support ---
    # When running as a frozen executable (PyInstaller) and the sole argument
    # is a .flw file path (e.g. from double-clicking in Explorer), we:
    #   1. Store the file path in an environment variable for Django views
    #   2. Rewrite sys.argv so Django starts the web server
    # If running frozen WITHOUT a .flw argument, clear any stale env var
    # left over from a previous run so no file auto-opens.
    if getattr(sys, 'frozen', False):
        # Pin the working directory to the install folder. Previously this
        # was done by Tlamatini.ps1 via Set-Location; now that the desktop
        # shortcut launches Tlamatini.exe directly (so the console window
        # picks up the embedded icon instead of inheriting cmd/WT's), we
        # have to pin it here ourselves.
        try:
            os.chdir(os.path.dirname(sys.executable))
        except OSError:
            pass

        if len(sys.argv) == 2:
            candidate = sys.argv[1]
            if candidate.lower().endswith('.flw') and not candidate.startswith('-'):
                # Normalize and store the .flw file path
                flw_path = os.path.abspath(candidate)
                os.environ['SYSTEMAGENT_FLW_FILE'] = flw_path
                print(f"--- [FLW] Flow file detected: {flw_path}")
                print("--- [FLW] Rewriting argv to start server...")
                # Replace argv so Django starts the server instead of
                # interpreting the .flw path as a management command
                sys.argv = [sys.argv[0], 'runserver', '--noreload', '0.0.0.0:8000']
            else:
                # Argument is not a .flw file — clear any stale env var
                os.environ.pop('SYSTEMAGENT_FLW_FILE', None)
        elif len(sys.argv) == 1:
            # Bare double-click on the shortcut: no args at all. Behave
            # identically to the old Tlamatini.ps1 wrapper by injecting
            # `runserver --noreload` so the user gets a working server.
            os.environ.pop('SYSTEMAGENT_FLW_FILE', None)
            sys.argv = [sys.argv[0], 'runserver', '--noreload']
        else:
            # No .flw argument provided — clear any stale env var
            os.environ.pop('SYSTEMAGENT_FLW_FILE', None)

        # Auto-open the browser ~10s after the server starts, mirroring the
        # behavior the legacy Tlamatini.ps1 wrapper provided. Only fires
        # when the resolved command is `runserver`; covers both the bare
        # double-click and the .flw-association paths above.
        if len(sys.argv) >= 2 and sys.argv[1] == 'runserver':
            _schedule_browser_open('http://localhost:8000/', delay_seconds=10.0)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHON_HOME environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
