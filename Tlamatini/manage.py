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
    """Duplicates writes to the original console stream and a log file.

    Both sinks are written defensively: if the console window is closed
    (or its handle otherwise becomes invalid), writing to ``self._original``
    can raise OSError. We MUST swallow that — an exception escaping a
    logging call on a background thread can wedge that thread and make the
    server appear hung even though the console is merely gone. The log
    file is the durable record either way.
    """

    def __init__(self, original, log_file):
        self._original = original
        self._log_file = log_file

    def write(self, data):
        try:
            self._original.write(data)
        except Exception:
            pass
        try:
            self._log_file.write(data)
            self._log_file.flush()
        except Exception:
            pass
        return len(data) if isinstance(data, str) else None

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
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


def _enforce_app_temp_dir():
    """Pin ALL temporary files to ``<application-root>/Temp`` — never elsewhere.

    Tlamatini's policy is that every transient artefact (the core process, every
    pool agent it spawns, the STM32 MCP server, external coding-agent CLIs, and
    any third-party library) lives under one ``Temp`` directory at the app root,
    so a single wipe cleans everything and nothing leaks to ``C:\\Temp`` /
    ``%TEMP%``.  We set this BEFORE Django (and before anything imports
    ``tempfile``) so the very first temp allocation already lands correctly, and
    we export the env vars so EVERY child process inherits the same directory
    (``get_agent_env`` in the pool agents does ``os.environ.copy()``).

    Resolution mirrors ``agent/path_guard.py::_get_application_root`` exactly:
      * frozen → directory of the executable (e.g. ``C:\\Tlamatini\\Temp``)
      * source → repo root, two levels above this file's own directory
                 (``manage.py`` sits in the Django project dir, inside the repo
                 root) — e.g. ``D:\\devenv\\source\\Tlamatini\\Temp``.
    Self-contained (no Django / agent import) and fail-open.
    """
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_root = os.path.join(base, 'Temp')
        os.makedirs(temp_root, exist_ok=True)
        for var in ('TMP', 'TEMP', 'TMPDIR'):
            os.environ[var] = temp_root
        os.environ['TLAMATINI_TEMP'] = temp_root
        import tempfile
        tempfile.tempdir = temp_root
        print(f"--- [TEMP] Temporary files pinned to: {temp_root}")
        # Templates: the DEFAULT parent for the template-projects the firmware /
        # engine agents (STM32er / ESP32er / Arduiner / Unrealer) scaffold, unless
        # the user names another path. Exported so spawned agents inherit it.
        templates_root = os.path.join(base, 'Templates')
        os.makedirs(templates_root, exist_ok=True)
        os.environ['TLAMATINI_TEMPLATES'] = templates_root
        print(f"--- [TEMPLATES] Template projects default to: {templates_root}")
    except Exception as exc:
        print(f"--- [TEMP] Could not pin temp/templates directories (non-fatal): {exc}")


def _pin_playwright_browsers():
    """Point Playwright at the browsers CARRIED inside the install (frozen only).

    Playwright keeps its browser binaries OUTSIDE site-packages (normally in
    ``%LOCALAPPDATA%/ms-playwright``), which does not exist on a machine that
    never ran ``playwright install``. The build ships them to
    ``<install_dir>/ms-playwright`` (build.py::bundle_playwright_browsers), so
    here — before Django and before any agent spawns — we export
    ``PLAYWRIGHT_BROWSERS_PATH`` to that directory. Every child process inherits
    it (pool agents do ``os.environ.copy()``), so BOTH the in-process Googler
    tool and the Playwrighter pool agent find chromium/firefox/webkit without a
    system Python or a prior ``playwright install``. Source mode is left alone
    (dev uses the default cache). Fail-open.
    """
    try:
        if not getattr(sys, 'frozen', False):
            return
        browsers = os.path.join(os.path.dirname(sys.executable), 'ms-playwright')
        if os.path.isdir(browsers):
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers
            print(f"--- [PLAYWRIGHT] Browsers pinned to: {browsers}")
        else:
            print(f"--- [PLAYWRIGHT] Carried browsers not found at {browsers} "
                  "(Playwrighter/Googler may be unavailable).")
    except Exception as exc:
        print(f"--- [PLAYWRIGHT] Could not pin browser path (non-fatal): {exc}")


def _pin_bundled_tools():
    """Put the CARRIED external runtimes (Java, Git) on JAVA_HOME / PATH (frozen).

    The build carries a JDK/JRE into ``<install_dir>/jre`` and Git into
    ``<install_dir>/git`` (build.py::bundle_java_runtime / bundle_git). Here —
    before Django and before any agent spawns — we export ``JAVA_HOME`` and
    prepend the bundled ``jre/bin`` and ``git/cmd`` (+ mingw64/usr bins) to PATH.
    Every child process inherits this (pool agents do ``os.environ.copy()``), so
    J-Decompiler (java -jar jd-cli.jar), Gitter (bare ``git``), and the STM32er
    MCP git-clone bootstrap all work on a machine with no system Java/Git.
    Source mode is left alone. Fail-open.
    """
    try:
        if not getattr(sys, 'frozen', False):
            return
        base = os.path.dirname(sys.executable)
        extra_path = []
        jre = os.path.join(base, 'jre')
        if os.path.isdir(jre):
            os.environ['JAVA_HOME'] = jre
            jre_bin = os.path.join(jre, 'bin')
            if os.path.isdir(jre_bin):
                extra_path.append(jre_bin)
            print(f"--- [JAVA] JAVA_HOME pinned to carried JRE: {jre}")
        git = os.path.join(base, 'git')
        if os.path.isdir(git):
            for sub in ('cmd', os.path.join('mingw64', 'bin'), os.path.join('usr', 'bin')):
                d = os.path.join(git, sub)
                if os.path.isdir(d):
                    extra_path.append(d)
            print(f"--- [GIT] Carried Git on PATH: {os.path.join(git, 'cmd')}")
        if extra_path:
            os.environ['PATH'] = os.pathsep.join(extra_path) + os.pathsep + os.environ.get('PATH', '')
    except Exception as exc:
        print(f"--- [TOOLS] Could not pin carried Java/Git (non-fatal): {exc}")


_enforce_app_temp_dir()
_pin_playwright_browsers()
_pin_bundled_tools()


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


def _post_update_migrate_flag_path():
    """Path of the marker the updater drops to request a post-update migrate.

    Lives in the PRESERVED ``DB`` folder so it survives the self-update file
    swap (``apply_update.ps1`` preserves ``DB``).
    """
    return os.path.join(_resolve_db_folder_root(), 'post_update_migrate.flag')


def _run_post_update_migrate_if_flagged():
    """Migrate the user's database after a self-update, preserving their data.

    The updater (``apply_update.ps1``) copies the user's live ``db.sqlite3`` into
    ``DB/ToLoad`` and drops ``DB/post_update_migrate.flag``. On the next launch
    ``_apply_pending_db_swap()`` (above) restores that database over the freshly
    shipped one, then this applies Django ``migrate`` so new migrations -- new
    agents / ``chat_agent_*`` tools / demo prompts -- are added to the user's
    data WITHOUT wiping their chat history or custom Tool/Mcp/Agent toggles.

    ``migrate`` runs in a CHILD process: ``agent.apps.AgentConfig.ready()`` only
    starts the MCP servers for ``runserver``/``startserver``/``daphne``/``asgi``
    commands, so a child ``migrate`` starts no servers and cannot recurse. It is
    invoked ONLY from the server-launch path (never from the child), and is
    fail-safe -- a migrate error is logged but never blocks startup, and the
    flag is always cleared afterwards so a launch can never loop.
    """
    import subprocess
    try:
        flag = _post_update_migrate_flag_path()
        if not os.path.isfile(flag):
            return
    except Exception:
        return
    print("--- [DB MIGRATE] Post-update migration flagged; bringing your database "
          "to the current version (your history + toggles are kept)...")
    try:
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, 'migrate', '--noinput']
        else:
            cmd = [sys.executable, os.path.abspath(__file__), 'migrate', '--noinput']
        result = subprocess.run(cmd)
        if result.returncode == 0:
            print("--- [DB MIGRATE] Database migrated to the current version.")
        else:
            print(f"--- [DB MIGRATE] migrate exited with code {result.returncode}; continuing startup.")
    except Exception as exc:
        print(f"--- [DB MIGRATE] Skipped due to error: {exc}")
    finally:
        try:
            os.remove(_post_update_migrate_flag_path())
        except OSError:
            pass


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

    # Post-update database migration: bring the user's just-restored DB to the
    # current schema BEFORE the server starts. Gated on the launch command so
    # the child ``migrate`` it spawns (whose argv is ``migrate``) can never
    # re-enter this branch and recurse.
    if len(sys.argv) >= 2 and sys.argv[1] in ('runserver', 'startserver'):
        _run_post_update_migrate_if_flagged()

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
