"""Run PyInstaller so a Tlamatini release build cannot die on the build machine's clutter.

Angela, 2026-10-21: "make building process for public and private:
INVULNERABLE MUST ALWAYS BUILD".

A public build ran for 20 minutes and then died in PyInstaller's COLLECT step:

    PermissionError: [Errno 13] Permission denied:
    'C:\\Users\\angel\\AppData\\Roaming\\jupyter\\runtime\\jpserver-11572-open.html'

Nothing in Tlamatini uses Jupyter. ``thinc.tests.test_examples`` imports
``nbconvert``, nbconvert imports ``notebook``, and the contributed
``hook-notebook.py`` then bundles every folder
``jupyter_core.paths.jupyter_path()`` names - including the builder's own
``%APPDATA%\\jupyter``: the files of a RUNNING Jupyter server (locked), its
tokens, ``jupyter_cookie_secret`` and ``notebook_secret``. So the build failed
whenever Jupyter was open, and carried the builder's Jupyter secrets whenever
it was not.

build.py now excludes the Jupyter family from the frozen graph. This runner is
the second and third line of defence, for EVERY PyInstaller build of a release
(build.py, build_uninstaller.py, build_installer.py), public and private alike:

1. HERMETIC PROFILE - before PyInstaller is even imported, the Jupyter and
   IPython profile variables point at an empty folder under ``build/``, so no
   hook can reach the builder's own profile.
2. LOCKED-FILE GUARD - a file another program holds is retried for about 12
   seconds. If it is still locked and it does not belong to Tlamatini or to
   Python (it lies outside the repository, every interpreter prefix, every
   site-packages folder and the Windows folder), it is SKIPPED and named on
   the screen: such a file belongs to another program on this machine and is
   never part of the app. A locked file that IS part of the build still fails
   the build, with its path and what to do - never a silent half-build.

Stdlib only. Importing this module changes nothing; only ``main()`` patches.
"""
from __future__ import annotations

import errno
import os
import shutil
import site
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
HERMETIC_PROFILE = REPO_ROOT / "build" / "pyinstaller-hermetic-profile"

#: Folders Jupyter / IPython read for the USER's own profile.
PROFILE_DIR_VARS = ("JUPYTER_DATA_DIR", "JUPYTER_CONFIG_DIR", "JUPYTER_RUNTIME_DIR", "IPYTHONDIR")
#: Search paths that could add more of the user's folders.
PROFILE_PATH_VARS = ("JUPYTER_PATH", "JUPYTER_CONFIG_PATH")

#: Windows errors meaning "another program holds this file":
#: access denied, sharing violation, lock violation.
_LOCK_WINERRORS = frozenset({5, 32, 33})
_LOCK_ERRNOS = frozenset({errno.EACCES, errno.EBUSY, errno.EPERM})
#: 0.25 + 0.5 + 1 + 2 + 4 + 4 seconds of waiting between seven attempts.
LOCK_RETRIES = 7

_ORIGINAL_COPYFILE = shutil.copyfile
_skipped: list[tuple[str, str, str]] = []  # (source, destination, reason)
_trusted: tuple[str, ...] | None = None


def pyinstaller_command() -> list[str]:
    """The argv prefix that replaces ``[sys.executable, '-m', 'PyInstaller']``."""
    return [sys.executable, str(Path(__file__).resolve())]


def apply_hermetic_profile(env=None, profile_root=HERMETIC_PROFILE) -> Path:
    """Point every Jupyter / IPython profile variable at an EMPTY folder."""
    env = os.environ if env is None else env
    root = Path(profile_root)
    shutil.rmtree(root, ignore_errors=True)
    for var in PROFILE_DIR_VARS:
        folder = root / var.lower()
        folder.mkdir(parents=True, exist_ok=True)
        env[var] = str(folder)
    for var in PROFILE_PATH_VARS:
        env.pop(var, None)
    env["JUPYTER_NO_CONFIG"] = "1"
    return root


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def trusted_roots() -> tuple[str, ...]:
    """Folders whose files the app may really need: never skipped, only failed."""
    global _trusted
    if _trusted is None:
        roots = {str(REPO_ROOT), sys.prefix, sys.base_prefix, sys.exec_prefix,
                 os.environ.get("SystemRoot", ""), os.environ.get("WINDIR", "")}
        try:
            roots.update(site.getsitepackages())
        except Exception:
            pass
        try:
            roots.add(site.getuserbase())
            roots.add(site.getusersitepackages())
        except Exception:
            pass
        roots.update(entry for entry in sys.path if entry and os.path.isdir(entry))
        _trusted = tuple(sorted({_norm(root) for root in roots if root}))
    return _trusted


def belongs_to_build(path) -> bool:
    """True when ``path`` lies under the repository, Python, or Windows."""
    target = _norm(path)
    for root in trusted_roots():
        try:
            if os.path.commonpath([target, root]) == root:
                return True
        except ValueError:  # another drive
            continue
    return False


def is_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in _LOCK_WINERRORS or exc.errno in _LOCK_ERRNOS


def guarded_copyfile(src, dst, *args, **kwargs):
    """``shutil.copyfile`` that waits out a lock, then skips foreign clutter."""
    delay = 0.25
    failure: OSError | None = None
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            return _ORIGINAL_COPYFILE(src, dst, *args, **kwargs)
        except OSError as exc:
            if not is_lock_error(exc):
                raise
            failure = exc
        if attempt < LOCK_RETRIES:
            time.sleep(delay)
            delay = min(delay * 2, 4.0)
    if not belongs_to_build(src):
        _skipped.append((os.fspath(src), os.fspath(dst), str(failure)))
        print("WARNING [BUILD-GUARD] skipped a locked file that is not part of "
              f"Tlamatini or Python:\n    {src}\n    ({failure})", flush=True)
        # An empty stand-in lets PyInstaller finish its own bookkeeping
        # (it chmods what it copied); remove_placeholders() deletes it.
        try:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            Path(dst).touch()
        except OSError:
            pass
        return dst
    raise PermissionError(
        f"[BUILD-GUARD] {src} is part of the build, but another program keeps it "
        f"locked (tried {LOCK_RETRIES} times over about 12 seconds). Close that "
        "program - or a Tlamatini still running from dist\\ - and build again. "
        f"Destination: {dst}"
    ) from failure


def remove_placeholders() -> None:
    for _src, dst, _why in _skipped:
        try:
            if os.path.isfile(dst) and os.path.getsize(dst) == 0:
                os.remove(dst)
        except OSError:
            pass


def report() -> None:
    if not _skipped:
        return
    print("\n" + "=" * 74)
    print(f"[BUILD-GUARD] {len(_skipped)} locked file(s) outside Tlamatini and Python "
          "were NOT bundled:")
    for src, _dst, _why in _skipped:
        print(f"   - {src}")
    print("They belong to other programs on this machine; the build does not need them.")
    print("=" * 74, flush=True)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    profile = apply_hermetic_profile()
    print(f"--- [BUILD-GUARD] Jupyter/IPython profile isolated in {profile}", flush=True)
    print("--- [BUILD-GUARD] locked files are retried; a locked file outside "
          "Tlamatini and Python is skipped and named", flush=True)
    shutil.copyfile = guarded_copyfile
    try:
        from PyInstaller.__main__ import run
        run(args)
    except SystemExit as exc:  # PyInstaller reports its own errors this way
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        print(exc.code, file=sys.stderr, flush=True)
        return 1
    finally:
        shutil.copyfile = _ORIGINAL_COPYFILE
        remove_placeholders()
        report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
