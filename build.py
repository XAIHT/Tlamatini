# build.py — Tlamatini Build Script

import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
import importlib.util
import shutil
import zipfile

# Versioning: SemVer 2.0.0 with git-tag-derived version.  See VERSIONING.md.
from versioning import (
    emit_build_artifacts,
    extract_cli_version,
    resolve_build_version,
)


def find_package_data_paths(pypi_name, import_name):
    """Finds paths for a package's code and metadata."""
    paths_to_add = []
    try:
        spec = importlib.util.find_spec(import_name)
        if not spec or not spec.origin:
            print(f"WARNING: Could not find code for '{import_name}'.")
            return []

        code_path = Path(os.path.dirname(spec.origin))
        paths_to_add.append(f'--add-data={code_path};{import_name}')
        print(f"Found '{import_name}' code at: {code_path}")

        dist_info_name_base = pypi_name.replace('-', '_')
        dist_info_path = None
        for path in sys.path:
            if Path(path).is_dir() and 'site-packages' in str(path):
                for item in Path(path).iterdir():
                    if item.is_dir() and item.name.startswith(dist_info_name_base) and item.name.endswith('.dist-info'):
                        dist_info_path = item
                        break
            if dist_info_path:
                break

        if dist_info_path:
            paths_to_add.append(f'--add-data={dist_info_path};{dist_info_path.name}')
            print(f"Found '{pypi_name}' metadata at: {dist_info_path}")
        else:
            print(f"WARNING: Could not find .dist-info for '{pypi_name}'.")
        return paths_to_add
    except Exception as e:
        print(f"Error finding package {pypi_name}/{import_name}: {e}")
        return []


def find_package_code_path(package_name):
    """Finds the full path to an installed package's code directory."""
    try:
        spec = importlib.util.find_spec(package_name)
        return Path(os.path.dirname(spec.origin)) if spec and spec.origin else None
    except Exception:
        return None


def _gather_search_dirs():
    """Build an ordered, deduplicated list of directories to search for DLLs.

    Resolution order (first match wins):
      1. sys.base_prefix / sys.prefix / executable dir  — the running Python
      2. PYTHON_HOME env var entries
      3. PATH env var entries that contain a python*.dll
      4. DLLs sub-folders (standard + MS Store layout)
      5. C:/Windows/System32  (VC runtime fallback)
    """
    dirs: list[Path] = []

    # ── 1) The Python that is actually executing this script ──────────
    dirs.append(Path(sys.base_prefix))
    dirs.append(Path(sys.prefix))
    dirs.append(Path(sys.executable).parent)

    # ── 2) DLLs sub-folders (standard installer + MS Store on Win11) ──
    dirs.append(Path(sys.base_prefix) / "DLLs")
    dirs.append(Path(sys.executable).parent / "DLLs")

    # ── 3) Windows 10/11 SDK UCRT Redistributables ─────────────────────
    # This prevents PyInstaller from crashing on fresh Windows endpoints 
    # without requiring contributors to have a specific hardcoded SDK path.
    sdk_base = Path("C:/Program Files (x86)/Windows Kits/10/Redist")
    if sdk_base.is_dir():
        dirs.append(sdk_base / "ucrt/DLLs/x64")
        for ver_dir in sdk_base.iterdir():
            if ver_dir.is_dir():
                dirs.append(ver_dir / "ucrt/DLLs/x64")

    # ── 4) System32 as last-resort for VC runtimes ────────────────────
    dirs.append(Path("C:/Windows/System32"))

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for d in dirs:
        try:
            resolved = d.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _find_first_dll(name: str, search_dirs: list[Path]) -> Path | None:
    """Return the first existing path for *name* across *search_dirs*."""
    for d in search_dirs:
        candidate = d / name
        if candidate.exists():
            return candidate
    return None


def collect_python_dll_binaries():
    """Find **all** DLLs required by the embedded Python so the bootloader
    can load ``python3XX.dll`` without errors.

    In addition to the versioned DLL itself, the following are bundled:
      - ``python3.dll``          – stable ABI DLL the bootloader may need
      - ``vcruntime140.dll``     – VC runtime
      - ``vcruntime140_1.dll``   – VC runtime (additional)
      - ``ucrtbase.dll``         – Universal CRT base
      - ``api-ms-win-crt-*.dll`` – Universal CRT API-set forwarders

    Without these, Windows will report "The specified module could not be
    found" even though the main DLL is present, because *its* transitive
    dependencies are missing from the temporary extraction directory.

    Returns a list of ``--add-binary=<src>;<dest>`` arguments.
    """
    binaries: list[str] = []
    ver = sys.version_info
    dll_name = f"python{ver.major}{ver.minor}.dll"

    search_dirs = _gather_search_dirs()

    print(f"Python executable : {sys.executable}")
    print(f"Python version    : {ver.major}.{ver.minor}.{ver.micro}")
    print(f"Looking for       : {dll_name}")
    print(f"Search directories: {len(search_dirs)}")

    # ── 1) python3XX.dll (versioned) ─────────────────────────────────
    found = _find_first_dll(dll_name, search_dirs)
    if found:
        binaries.append(f"--add-binary={found};.")
        print(f"Bundling Python DLL: {found}")
    else:
        print(f"WARNING: Could not locate {dll_name} — the exe may fail to start.")

    # ── 2) python3.dll (stable ABI – bootloader may require it) ──────
    found = _find_first_dll("python3.dll", search_dirs)
    if found:
        binaries.append(f"--add-binary={found};.")
        print(f"Bundling stable ABI DLL: {found}")
    else:
        print("WARNING: Could not locate python3.dll")

    # ── 3) VC runtime DLLs ───────────────────────────────────────────
    for vc_name in ["vcruntime140.dll", "vcruntime140_1.dll"]:
        found = _find_first_dll(vc_name, search_dirs)
        if found:
            binaries.append(f"--add-binary={found};.")
            print(f"Bundling VC runtime: {found}")
        else:
            print(f"WARNING: Could not locate {vc_name}")

    # ── 4) Universal CRT (ucrtbase + api-ms-win-crt forwarders) ──────
    ucrt_found = _find_first_dll("ucrtbase.dll", search_dirs)
    if ucrt_found:
        binaries.append(f"--add-binary={ucrt_found};.")
        print(f"Bundling UCRT base: {ucrt_found}")

    ucrt_forwarders_bundled = 0
    seen_names: set[str] = set()
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            lname = f.name.lower()
            if lname.startswith("api-ms-win-crt-") and lname.endswith(".dll"):
                if lname not in seen_names:
                    seen_names.add(lname)
                    binaries.append(f"--add-binary={f};.")
                    ucrt_forwarders_bundled += 1
    if ucrt_forwarders_bundled:
        print(f"Bundling {ucrt_forwarders_bundled} UCRT forwarder DLLs")
    else:
        print("WARNING: Could not locate any api-ms-win-crt-*.dll forwarders")

    return binaries


_NUMPY_DIST_INFO_RE = re.compile(r'^numpy[-_].+\.(dist-info|egg-info)$', re.IGNORECASE)
_NUMPY_WHEEL_RE = re.compile(r'^numpy-.+\.whl$', re.IGNORECASE)


def _purge_numpy_environment(python_exe):
    """Wipe every numpy trace from a target Python's site-packages.

    Repeated or partial numpy installs leave multiple ``numpy-*.dist-info``
    directories side-by-side. When that happens, ``importlib.metadata``
    returns whichever dist-info sorts first (often the stale older one),
    PyInstaller's numpy hook branches on that wrong version number, and
    ``collect_dynamic_libs("numpy")`` walks a file list that no longer
    matches what's on disk — returning zero binaries and letting PyInstaller
    pick up ``numpy/core/`` duplicate ``.pyd`` files via the module graph
    instead, which trips numpy 2.x's one-init-per-process guard at runtime.

    To get a clean slate, uninstall numpy repeatedly (pip removes one
    install at a time when duplicates are present) and then sweep away any
    orphan ``numpy/`` tree, ``numpy.libs/`` tree, ``numpy-*.dist-info``
    directory, or ``numpy-*.whl`` wheel file left behind across every
    site-packages directory the target Python knows about. The subsequent
    ``pip install -r requirements.txt`` reinstalls numpy fresh against the
    pinned version.
    """
    print(f"\n--- Purging numpy environment for: {python_exe} ---")

    # Enumerate every site-packages directory (system + user) for this Python.
    probe = (
        "import site, json, sys; "
        "dirs = list(site.getsitepackages()); "
        "u = site.getusersitepackages(); "
        "dirs.append(u) if u else None; "
        "print(json.dumps(dirs))"
    )
    try:
        raw = subprocess.check_output([python_exe, "-c", probe], text=True).strip()
        site_dirs = [Path(p) for p in json.loads(raw)]
    except Exception as e:
        print(f"WARNING: Could not enumerate site-packages for {python_exe}: {e}")
        site_dirs = []

    # Repeatedly ``pip uninstall`` — each call removes one dist-info, so we
    # loop until pip reports nothing left.
    for _ in range(5):
        result = subprocess.run(
            [python_exe, "-m", "pip", "uninstall", "-y", "numpy"],
            capture_output=True, text=True,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 or "not installed" in combined.lower():
            break

    # Sweep residual files. pip uninstall only removes what its manifest
    # tracks; orphan ``.whl`` files and dist-info dirs from aborted installs
    # must be removed manually.
    removed = 0
    for sp in site_dirs:
        if not sp.is_dir():
            continue
        for item in sp.iterdir():
            name = item.name
            should_remove = False
            if name.lower() in ('numpy', 'numpy.libs'):
                should_remove = True
            elif _NUMPY_DIST_INFO_RE.match(name):
                should_remove = True
            elif _NUMPY_WHEEL_RE.match(name):
                should_remove = True
            if not should_remove:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item, onerror=_on_rmtree_error)
                else:
                    item.unlink()
                print(f"Removed numpy residual: {item}")
                removed += 1
            except Exception as e:
                print(f"WARNING: Could not remove {item}: {e}")

    if removed == 0:
        print("No numpy residuals found.")
    else:
        print(f"Cleared {removed} numpy residual entries.")


def run_step(label, func, *args, **kwargs):
    """Execute a build step with consistent logging and error handling."""
    print(f"\n--- {label} ---")
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"ERROR during '{label}': {e}")
        raise


def _on_rmtree_error(func, path, exc_info):
    """Handle Windows file-locking / read-only errors during shutil.rmtree."""
    try:
        os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
        func(path)
    except Exception:
        print(f"WARNING: Could not remove locked file: {path}")


def clean_directory(path):
    """Remove a directory tree if it exists (handles locked files on Windows)."""
    p = Path(path)
    if p.exists():
        shutil.rmtree(p, onerror=_on_rmtree_error)
        print(f"Removed: {p}")


def main():
    """Runs the PyInstaller command with correctly resolved paths."""
    build_start = time.time()
    print("=" * 60)
    print("  Tlamatini Build Script")
    print("=" * 60)

    # ── Resolve and emit version artefacts FIRST ─────────────────────
    # Precedence: --version CLI flag > $TLAMATINI_VERSION > git describe.
    # See VERSIONING.md for the full contract.
    cli_version = extract_cli_version(sys.argv)
    tlamatini_version = resolve_build_version(cli_version)
    version_file_path = emit_build_artifacts(
        tlamatini_version,
        product_name="Tlamatini",
        original_filename="Tlamatini.exe",
    )
    print(f"Tlamatini version : {tlamatini_version}")
    print(f"VERSIONINFO file  : {version_file_path}")

    # ── Self-modify packaging flag ───────────────────────────────────
    # When --self-modify is passed, the build ships Tlamatini's own source tree
    # (Tlamatini/agent/TlamatiniSourceCode) next to the executable, making the
    # running app a "self-able-modify" version that can read and modify its own
    # code. WITHOUT the flag the directory is omitted from the package entirely
    # (a "not-self-able-modify" build). See Tlamatini.md §9 / prompt.pmt.
    self_modify = "--self-modify" in sys.argv
    print(
        "Self-modify build : "
        + ("YES — bundling TlamatiniSourceCode" if self_modify
           else "no — source tree omitted")
    )

    separator = ';'
    dist_manage = Path("dist") / "manage"

    # ── 0) Clean previous build artifacts ────────────────────────────
    run_step("Cleaning previous build artifacts", lambda: [
        clean_directory("build"),
        clean_directory("dist"),
    ])

    # Remove old pkg.zip
    old_zip = Path("pkg.zip")
    if old_zip.exists():
        old_zip.unlink()
        print(f"Removed old: {old_zip}")

    # ── 1) Install dependencies ──────────────────────────────────────
    # Use PYTHON_HOME env var if set (target Python for frozen-mode agents),
    # otherwise fall back to the Python running this build script.
    python_path_raw = os.environ.get("PYTHON_HOME", "").strip()
    build_python = sys.executable

    # PYTHON_HOME may point to a directory or directly to python.exe
    frozen_python = None
    if python_path_raw:
        p = Path(python_path_raw)
        if p.is_file():
            frozen_python = str(p)
        elif p.is_dir():
            # Resolve to python.exe inside the directory
            exe = p / "python.exe"
            if exe.is_file():
                frozen_python = str(exe)
            else:
                print(f"WARNING: PYTHON_HOME dir '{p}' has no python.exe inside. Ignoring.")

    if frozen_python:
        print(f"PYTHON_HOME detected: {frozen_python}")
        print("Dependencies will be installed into BOTH build Python and PYTHON_HOME Python.")
    else:
        if python_path_raw:
            print(f"WARNING: PYTHON_HOME is set to '{python_path_raw}' but could not resolve to a python executable. Ignoring.")
        print(f"Using build Python only: {build_python}")

    # Collect the list of Python executables to install into
    install_pythons = [build_python]
    if frozen_python and Path(frozen_python).resolve() != Path(build_python).resolve():
        install_pythons.append(frozen_python)

    req_file = Path(__file__).with_name('requirements.txt')

    for target_python in install_pythons:
        print(f"\n--- Installing dependencies into: {target_python} ---")

        # 1a-pre) Clean numpy residuals so pip reinstalls numpy fresh.
        # Prevents stale dist-info/wheel fragments from tripping PyInstaller's
        # numpy hook (wrong version branch, empty collect_dynamic_libs, and the
        # downstream "cannot load module more than once per process" crash).
        run_step(
            f"Purging numpy residuals in {target_python}",
            _purge_numpy_environment,
            target_python,
        )

        # 1a) Install torch CPU-only FIRST to avoid CUDA DLL issues (WinError 1114)
        # --user ensures install works without admin privileges
        print(f"  -> Installing torch (CPU-only) for {target_python} ...")
        torch_cmd = [
            target_python, "-m", "pip", "install", "--user", "torch",
            "--index-url", "https://download.pytorch.org/whl/cpu",
        ]
        torch_result = subprocess.run(torch_cmd)
        if torch_result.returncode != 0:
            print(f"WARNING: torch CPU install failed for {target_python}. Continuing anyway.")

        # 1b) Install remaining dependencies from requirements.txt
        # --user ensures install works without admin privileges
        if req_file.exists():
            pip_cmd = [target_python, "-m", "pip", "install", "--user", "-r", str(req_file)]
            pip_result = subprocess.run(pip_cmd)
            if pip_result.returncode != 0:
                print(f"ERROR: pip install -r requirements.txt failed for {target_python}. Aborting build.")
                sys.exit(1)
        else:
            print("WARNING: requirements.txt not found next to build.py. Skipping pip install.")

        # 1b-post) VERIFY the agent / MCP-server third-party libs actually IMPORT in
        # this target Python — fail the build loudly if any is missing.
        # Frozen-mode pool agents (shoter/playwrighter/windower/sqler/...) AND the
        # STM32 Template Project MCP server that STM32er spawns run UNDER this
        # interpreter (via get_python_command / PYTHON_HOME), NOT inside the
        # PyInstaller bundle — so every library they import must be present HERE or
        # the frozen assets are incomplete and the agents crash at runtime. Pinning
        # them in requirements.txt is not enough on its own; this asserts the install
        # truly took (catches a broken wheel / missing native dep too).
        _agent_libs = [
            "mcp", "serial",                       # STM32 MCP server (STM32er)
            "PyPDF2", "pypdf", "fitz", "odf",       # PDF / ODF file backends
            "ebooklib", "openpyxl", "xlrd", "striprtf", "docx", "pptx",  # file-format backends
            "bs4", "requests", "py7zr", "yaml",     # crawler / http / archive / config
            "pyautogui", "playwright", "telethon",  # desktop / browser / telegram agents
            "pymongo", "pyodbc", "win32gui",        # db / windows agents
            "sounddevice",                          # microphone capture (Recorder) — native PortAudio
            "soundfile",                            # audio playback (AudioPlayer) — native libsndfile
            "ffpyplayer",                           # video+audio playback (VideoPlayer) — bundled ffmpeg+SDL
        ]
        verify_src = "\n".join([
            "import importlib",
            "mods = " + repr(_agent_libs),
            "miss = []",
            "for _m in mods:",
            "    try:",
            "        importlib.import_module(_m)",
            "    except Exception as _e:",
            "        miss.append(_m + ' (' + type(_e).__name__ + ')')",
            "print('MISSING:' + '; '.join(miss) if miss else 'ALL_AGENT_LIBS_OK')",
            "raise SystemExit(3 if miss else 0)",
        ])
        print(f"  -> Verifying agent/MCP libs import in {target_python} ...")
        verify = subprocess.run([target_python, "-c", verify_src], capture_output=True, text=True)
        print("     " + ((verify.stdout or "") + (verify.stderr or "")).strip())
        if verify.returncode != 0:
            print(f"ERROR: required agent/MCP libraries are missing/broken in {target_python}. "
                  f"Add them to requirements.txt so the frozen assets are complete. Aborting build.")
            sys.exit(1)

        # 1b-post-2) VERIFY Ruff is runnable via `-m ruff` in this target Python.
        # Pythonxer's STRICT correctness gate shells out to
        # `<get_python_command()> -m ruff check <script>` before it runs ANY script;
        # if Ruff is absent the gate silently fails OPEN (degrades to the compile()
        # syntax floor only). Ruff is pinned in requirements.txt, but a broken/partial
        # wheel can still pass an `import` check yet fail `-m ruff`, so assert the
        # EXACT invocation the agent uses. This loop runs for BOTH the build Python
        # AND the PYTHON_HOME (frozen-mode agent) Python, so a green build guarantees
        # Ruff is present in frozen AND non-frozen modes. Abort loudly if it isn't.
        print(f"  -> Verifying Ruff (`-m ruff --version`) in {target_python} ...")
        ruff_check = subprocess.run(
            [target_python, "-m", "ruff", "--version"],
            capture_output=True, text=True,
        )
        print("     " + ((ruff_check.stdout or "") + (ruff_check.stderr or "")).strip())
        if ruff_check.returncode != 0:
            print(f"ERROR: Ruff is NOT runnable via `-m ruff` in {target_python}. "
                  "Pythonxer's strict syntax/lint gate REQUIRES it. Confirm "
                  "'ruff==0.14.5' in requirements.txt installed correctly into this "
                  "Python. Aborting build.")
            sys.exit(1)

        # 1c) Install Playwright browsers
        print(f"  -> Installing Playwright browsers for {target_python} ...")
        pw_result = subprocess.run([target_python, "-m", "playwright", "install"])
        if pw_result.returncode != 0:
            print(f"WARNING: playwright install failed for {target_python}. Continuing anyway.")

    # Ensure PyInstaller is available
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("\n--- Installing PyInstaller ---")
        ensure_pyinstaller = subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pyinstaller"])
        if ensure_pyinstaller.returncode != 0:
            print("ERROR: Failed to install PyInstaller. Aborting build.")
            sys.exit(1)

    # ── 2) Erase database before building ────────────────────────────
    print("\n--- Erasing database before building ---")
    try:
        db_path = Path("Tlamatini") / "db.sqlite3"
        if db_path.exists():
            db_path.unlink()
            print(f"Removed old database file: {db_path}")
        else:
            print(f"No database file found at {db_path}, skipping removal.")
    except Exception as e:
        print(f"WARNING: Could not remove database file: {e}")

    # ── 3) Collect static files before packaging ─────────────────────
    print("\n--- Running collectstatic ---")
    collectstatic_result = subprocess.run([sys.executable, 'Tlamatini/manage.py', 'collectstatic', '--noinput'])
    if collectstatic_result.returncode != 0:
        print("ERROR: collectstatic failed. Aborting build.")
        sys.exit(1)

    # ── 4) Build PyInstaller command ─────────────────────────────────
    dll_args = run_step("Collecting Python DLL binaries",
                        collect_python_dll_binaries)

    # NOTE: the server has NO tkinter/Tcl-Tk dependency. The Set-DB /
    # Backup-DB "Browse" buttons use the Win32 common dialogs directly via
    # ctypes (agent/native_dialogs.py -> comdlg32/shell32), so there is no
    # Tcl/Tk data tree to bundle and the old "Can't find a usable init.tcl"
    # failure cannot occur. tkinter is explicitly excluded below so a
    # transitive importer can never drag the fragile Tcl/Tk runtime back in.
    # (The Installer/Uninstaller GUIs are SEPARATE executables built by
    # build_installer.py / build_uninstaller.py — those still use tkinter
    # and bundle their own Tcl/Tk; this build script does not.)

    # Point PyInstaller at our local hooks directory so our custom
    # hook-numpy.py (priority 2) shadows PyInstaller's stock one (priority 1).
    # See pyinstaller_hooks/hook-numpy.py for the numpy/core/ duplicate-pyd
    # filter rationale.
    hooks_dir = Path(__file__).with_name('pyinstaller_hooks')

    icon_path = Path(__file__).with_name('Tlamatini.ico')
    icon_args: list[str] = []
    if icon_path.exists():
        icon_args.append(f'--icon={icon_path}')
        print(f"Embedding application icon: {icon_path}")
    else:
        print(f"WARNING: {icon_path} not found — Tlamatini.exe will have no embedded icon.")

    command = [
        sys.executable, '-m', 'PyInstaller', '--name', 'manage', '--console', '--noconfirm',
        f'--additional-hooks-dir={hooks_dir}',
        f'--version-file={version_file_path}',
        *icon_args,
        *dll_args,
        f'--add-data=Tlamatini/agent/templates{separator}agent/templates',
        f'--add-data=Tlamatini/agent/static{separator}agent/static',
        f'--add-data=Tlamatini/staticfiles{separator}staticfiles',
        f'--add-data=Tlamatini/agent/config.json{separator}agent',
        f'--add-data=Tlamatini/agent/prompt.pmt{separator}agent',
        f'--add-data=Tlamatini/agent/Tlamatini.md{separator}agent',
        # ACPX skill catalog — every SKILL.md package + its scripts/ + _meta/.
        # The skill registry (agent/skills/registry.py) discovers SKILL.md
        # under this tree at runtime; without this --add-data line, frozen
        # builds would have an empty skill catalog.
        f'--add-data=Tlamatini/agent/skills_pkg{separator}agent/skills_pkg',
        '--hidden-import=agent._version',
        '--hidden-import=daphne.server', '--hidden-import=channels',
        '--hidden-import=whitenoise.middleware', '--hidden-import=whitenoise.storage',
        '--hidden-import=django_bootstrap5',
        '--hidden-import=django.contrib.admin.apps',
        '--hidden-import=django.db.models.sql.compiler',
        '--hidden-import=django.contrib.auth',
        '--hidden-import=django.contrib.sessions',
        '--hidden-import=django.contrib.messages',
        '--hidden-import=django.db.backends.sqlite3',
        '--hidden-import=tlamatini.asgi',
        '--hidden-import=tlamatini.middleware',
        '--hidden-import=tlamatini.context_processors',
        '--hidden-import=tlamatini.logging_filters',
        '--hidden-import=unstructured',
        '--hidden-import=filesearch_pb2',
        '--hidden-import=filesearch_pb2_grpc',
        # Server uses Win32 ctypes dialogs, NOT tkinter — exclude Tcl/Tk so it
        # can never be dragged in transitively (no init.tcl bundling headaches).
        '--exclude-module=tkinter',
        '--exclude-module=_tkinter',
        '--collect-all', 'django_bootstrap5',
        '--collect-all', 'autobahn',
        '--collect-all', 'filesearch_pb2',
        '--collect-all', 'filesearch_pb2_grpc',
        # VideoPlayer audio+video: ffpyplayer ships compiled extensions + bundled
        # ffmpeg/SDL DLLs inside its package dir; --collect-all pulls those
        # binaries (PyInstaller's module-graph alone misses the .dll payload),
        # so the frozen build plays video WITH audio and no external ffmpeg.
        '--collect-all', 'ffpyplayer',
        'Tlamatini/manage.py'
    ]

    # Ensure django_bootstrap5 code and its dist-info metadata are bundled
    command.extend(find_package_data_paths(pypi_name='django-bootstrap5', import_name='django_bootstrap5'))
    command.extend(find_package_data_paths(pypi_name='django', import_name='django'))

    # Bundle unstructured NLP data
    unstructured_path = find_package_code_path('unstructured')
    if unstructured_path:
        unstructured_data_file = unstructured_path / "nlp" / "english-words.txt"
        if unstructured_data_file.exists():
            print(f"Found unstructured data file: {unstructured_data_file}")
            command.append(f'--add-data={unstructured_data_file};unstructured/nlp')
        else:
            print("WARNING: Could not find 'english-words.txt' in unstructured package.")
    else:
        print("WARNING: Could not find unstructured package path.")

    # Ensure Autobahn CFFI sources are available at runtime
    try:
        autobahn_path = find_package_code_path('autobahn')
        if autobahn_path is not None:
            nvx_dir = autobahn_path / 'nvx'
            for c_name in ['_utf8validator.c', '_xormasker.c']:
                c_file = nvx_dir / c_name
                if c_file.exists():
                    command.append(f'--add-data={c_file};autobahn/nvx')
                else:
                    print(f"WARNING: Autobahn NVX source not found: {c_file}")
        else:
            print("WARNING: Could not resolve Autobahn package path to include NVX sources.")
    except Exception as e:
        print(f"WARNING: Failed to add Autobahn NVX sources: {e}")

    # ── 5) Run PyInstaller ───────────────────────────────────────────
    print("\n--- Starting PyInstaller build ---")
    result = subprocess.run(command)

    if result.returncode != 0:
        elapsed = time.time() - build_start
        print(f"\n--- PyInstaller build FAILED after {elapsed:.0f}s ---")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════
    # Post-build steps (only reached on successful PyInstaller build)
    # ══════════════════════════════════════════════════════════════════

    # ── 6) Copy application files & create directories ───────────────
    print("\n--- Post-build: copying files and directories ---")
    try:
        dist_manage.mkdir(parents=True, exist_ok=True)

        # Optional files copied to the installed application root
        optional_file_copies = {
            Path("Tlamatini") / "agent" / "config.json": dist_manage / "config.json",
            Path("Tlamatini") / "agent" / "prompt.pmt": dist_manage / "prompt.pmt",
            # Tlamatini.md is the LLM's self-knowledge file, referenced by
            # prompt.pmt. It is read from the application directory (next to the
            # executable in frozen mode) exactly like prompt.pmt / config.json,
            # so it must land at the install root — not only inside the bundle.
            Path("Tlamatini") / "agent" / "Tlamatini.md": dist_manage / "Tlamatini.md",
        }
        for src, dst in optional_file_copies.items():
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"Copied {src} -> {dst}")
            else:
                print(f"WARNING: {src} not found; skipping copy.")

        # Required root-level assets for the installed application.
        # ``agents_descriptions.md`` is the authoritative source for the
        # workflow-agent sidebar tooltips and the canvas Description dialog
        # — it must ship next to the executable so ``agent.views`` can
        # resolve it in frozen mode just like in source mode.
        required_file_copies = {
            Path("README.md"): dist_manage / "README.md",
            Path("agents_descriptions.md"): dist_manage / "agents_descriptions.md",
        }
        for src, dst in required_file_copies.items():
            if not src.exists():
                raise FileNotFoundError(f"Required file not found: {src}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"Copied required file: {src} -> {dst}")

        # Optional directory trees
        optional_dir_copies = {
            Path("Tlamatini") / "agent" / "images": dist_manage / "images",
            Path("Tlamatini") / "agent" / "agents": dist_manage / "agents",
            # ACPX skill catalog also copied next to the executable, so users
            # opening the install dir can browse/author skills without
            # needing to peek inside the PyInstaller bundle. The registry
            # prefers this directory when present.
            Path("Tlamatini") / "agent" / "skills_pkg": dist_manage / "agent" / "skills_pkg",
        }
        for src_dir, dst_dir in optional_dir_copies.items():
            if src_dir.exists():
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)
                print(f"Copied directory: {src_dir} -> {dst_dir}")
            else:
                print(f"WARNING: Source directory not found: {src_dir}")

        # Optional: Tlamatini's own source tree — included recursively ONLY when
        # the build was invoked with --self-modify. It lands at the install root
        # (the frozen-mode application_path, next to the executable), so the
        # running app resolves it exactly like prompt.pmt / config.json /
        # Tlamatini.md, and it flows into pkg.zip via the os.walk(dist_manage)
        # archive step. Omitting it produces a "not-self-able-modify" build.
        if self_modify:
            self_src = Path("Tlamatini") / "agent" / "TlamatiniSourceCode"
            self_dst = dist_manage / "TlamatiniSourceCode"
            if self_src.exists():
                if self_dst.exists():
                    shutil.rmtree(self_dst)
                shutil.copytree(self_src, self_dst)
                file_total = sum(1 for p in self_dst.rglob("*") if p.is_file())
                print(f"Copied self-modify source tree: {self_src} -> {self_dst} ({file_total} files)")
            else:
                print(f"WARNING: --self-modify set but source tree not found: {self_src}; skipping.")
        else:
            print("Self-modify source tree omitted (not-self-able-modify build).")

        # Required directory trees
        required_dir_copies = {
            Path("Tlamatini") / "jd-cli": dist_manage / "jd-cli",
        }
        for src_dir, dst_dir in required_dir_copies.items():
            if not src_dir.exists():
                raise FileNotFoundError(f"Required directory not found: {src_dir}")
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            print(f"Copied required directory: {src_dir} -> {dst_dir}")

        jd_cli_bat = dist_manage / "jd-cli" / "jd-cli.bat"
        if not jd_cli_bat.exists():
            raise FileNotFoundError(
                f"Required jd-cli payload is incomplete. Missing launcher: {jd_cli_bat}"
            )
        print(f"Verified jd-cli payload at: {jd_cli_bat.parent}")

        # Required empty directories (must survive in pkg.zip)
        # ``DB/ToLoad`` and ``DB/Older`` back the "Set DB" mechanic in
        # manage.py::_apply_pending_db_swap: at start-up Tlamatini moves any
        # ``DB/ToLoad/db.sqlite3`` into place after archiving the current one
        # under ``DB/Older/<timestamp>/``. Ship both directories empty so the
        # swap-in can write to them on first run without raising an OSError.
        #
        # ``Temp`` is Tlamatini's SOLE temporary directory: manage.py /
        # settings.py pin TEMP/TMP/TMPDIR + Python's tempfile to <app>/Temp and
        # every pool agent honors TLAMATINI_TEMP (see agent/path_guard.py
        # ::enforce_app_temp_dir and prompt.pmt Rule 15). It MUST exist next to
        # the executable, empty, on first run — get_app_temp_root() self-creates
        # it, but shipping it empty makes the install layout explicit and avoids
        # a first-write race before the directory is created.
        # ``Templates`` is the DEFAULT parent for the template-projects the
        # firmware/engine agents (STM32er/ESP32er/Arduiner/Unrealer) scaffold
        # when the user gives no path (exported as TLAMATINI_TEMPLATES; see
        # agent/path_guard.py::enforce_app_templates_dir + prompt.pmt Rule 16).
        # Ship it empty next to the executable so the first create_project lands
        # in a predictable place inside Tlamatini.
        empty_dirs = (
            "application", "applications", "documentation",
            "context_files", "content_generated", "doc_generated",
            "DB/ToLoad", "DB/Older",
            "Temp", "Templates",
        )
        for d in empty_dirs:
            target_dir = dist_manage / d
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"Ensured empty directory: {target_dir}")

    except Exception as e:
        print(f"Post-build step error: {e}")
        sys.exit(1)

    # ── 7) Remove PyInstaller spec file ──────────────────────────────
    try:
        spec_file = Path("manage.spec")
        if spec_file.exists():
            spec_file.unlink()
            print(f"Removed spec file: {spec_file}")
    except Exception as e:
        print(f"WARNING: Could not remove spec file: {e}")

    # ── 8) Run Django setup commands via built executable ─────────────
    try:
        print("\n--- Running post-build Django setup (dist/manage/manage.exe) ---")
        manage_exe = dist_manage / ("manage.exe" if os.name == "nt" else "manage")
        if not manage_exe.exists():
            print(f"WARNING: {manage_exe} not found; skipping Django setup.")
        else:
            def run_cmd(args, **kwargs):
                cmd_display = " ".join(args)
                print(f"-> Running: {manage_exe.name} {cmd_display}")
                return subprocess.run([str(manage_exe), *args], **kwargs)

            # 8a) migrate
            res = run_cmd(["migrate"])
            if res.returncode != 0:
                print("WARNING: 'migrate' failed.")

            # 8b) createsuperuser (non-interactive)
            env = os.environ.copy()
            env.setdefault('DJANGO_SUPERUSER_USERNAME', 'user')
            env.setdefault('DJANGO_SUPERUSER_EMAIL', 'user@xaiht.com')
            env.setdefault('DJANGO_SUPERUSER_PASSWORD', 'changeme')
            res = run_cmd(["createsuperuser", "--noinput"], env=env)
            if res.returncode != 0:
                print("WARNING: 'createsuperuser' failed or user may already exist.")

            # 8c) collectstatic
            res = run_cmd(["collectstatic", "--noinput"])
            if res.returncode != 0:
                print("WARNING: 'collectstatic' (post-build) failed.")

            # 8d) Rename executable manage -> Tlamatini
            try:
                target_name = manage_exe.with_name("Tlamatini.exe" if os.name == "nt" else "Tlamatini")
                if target_name.exists():
                    target_name.unlink()
                manage_exe.rename(target_name)
                print(f"Renamed {manage_exe.name} -> {target_name.name}")
            except Exception as e:
                print(f"WARNING: Could not rename executable: {e}")

            # 8e) Copy support scripts, samples and icon
            support_files = [
                "register_flw.ps1",
                "unregister_flw.ps1",
                "Tlamatini.ps1",
                "Tlamatini.ico",
                "CreateShortcut.ps1",
                "RemoveShortcut.ps1",
                "CreateShortcut.json",
                "Tlamatini/cat_art.py"
            ]
            for fname in support_files:
                try:
                    src = Path(fname)
                    dst = dist_manage / src.name
                    if src.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        print(f"Copied {src} -> {dst}")
                    else:
                        print(f"WARNING: {src} not found; skipping copy.")
                except Exception as e:
                    print(f"WARNING: Could not copy {fname}: {e}")

            # ── 9) Generate pkg.zip from dist/manage ─────────────────
            try:
                pkg_zip_path = Path("pkg.zip")

                # Remove old pkg.zip if it exists
                if pkg_zip_path.exists():
                    pkg_zip_path.unlink()
                    print(f"Removed old {pkg_zip_path}")

                print(f"\n--- Creating {pkg_zip_path} from {dist_manage} ---")
                with zipfile.ZipFile(pkg_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    file_count = 0
                    for root, dirs, files in os.walk(dist_manage):
                        # Add empty directories as explicit entries so they survive extraction
                        if not files and not dirs:
                            dir_arcname = str(Path(root).relative_to(dist_manage)) + '/'
                            zf.write(root, dir_arcname)
                        for file in files:
                            full_path = Path(root) / file
                            arcname = full_path.relative_to(dist_manage)
                            zf.write(full_path, arcname)
                            file_count += 1
                    print(f"Added {file_count} files to {pkg_zip_path}")
                size_mb = pkg_zip_path.stat().st_size / (1024 * 1024)
                print(f"pkg.zip created successfully ({size_mb:.1f} MB)")

                # ── 10) Clean up build and dist directories ──────────
                for cleanup_dir in ("build", "dist"):
                    clean_directory(cleanup_dir)

            except Exception as e:
                print(f"WARNING: Could not create pkg.zip: {e}")
    except Exception as e:
        print(f"WARNING: Post-build Django setup encountered an error: {e}")

    # Clean up the transient VERSIONINFO .txt file once PyInstaller has
    # finished embedding it.  Keep ``Tlamatini/agent/_version.py`` so the
    # frozen application can import it.
    try:
        if version_file_path.exists():
            version_file_path.unlink()
            print(f"Removed transient: {version_file_path}")
    except Exception as e:
        print(f"WARNING: Could not remove {version_file_path}: {e}")

    elapsed = time.time() - build_start
    print(f"\n{'=' * 60}")
    print(f"  Build completed successfully in {elapsed:.0f}s")
    print(f"  Version : {tlamatini_version}")
    print(f"{'=' * 60}")


# ── Concurrency guard ────────────────────────────────────────────────────
# Two builds in this directory at once is fatal: they share the PyInstaller
# work dir (build/manage) and the dist/ tree, and whichever finishes first runs
# the "Cleaning previous build artifacts" rmtree (and the end-of-run cleanup),
# deleting the OTHER build's work dir mid-flight — the loser then dies with
# `FileNotFoundError: build/manage/warn-manage.txt`. This lock makes a second
# build refuse to start instead of silently clobbering the first.
_BUILD_LOCK = Path(".build.lock")


def _pid_alive(pid):
    """True if `pid` is a currently-running process. Errs on the side of
    'alive' on unknown so we never clobber a possibly-running build."""
    if not pid or pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:
            return True
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False
    except Exception:
        return True


def _acquire_build_lock():
    """Refuse to start if another build is genuinely running; otherwise (no lock
    or a stale lock from a crashed build) take ownership. Fail-open on any I/O
    error so it never blocks a legitimate single build."""
    if _BUILD_LOCK.exists():
        try:
            other = int((_BUILD_LOCK.read_text(encoding="utf-8").strip() or "0"))
        except Exception:
            other = 0
        if other and other != os.getpid() and _pid_alive(other):
            print("=" * 60)
            print(f"  ABORT: another Tlamatini build is already running (PID {other}).")
            print("  Concurrent builds share the build/ and dist/ work dirs and")
            print("  clobber each other (the loser dies writing")
            print("  build/manage/warn-manage.txt). Let it finish, or kill that")
            print(f"  process and delete {_BUILD_LOCK} if the lock is stale.")
            print("=" * 60)
            sys.exit(2)
        print(f"Reclaiming stale build lock (PID {other} not running).")
    try:
        _BUILD_LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        print(f"WARNING: could not write build lock ({e}); proceeding without it.")


def _release_build_lock():
    """Remove the lock, but only if it is still ours (never delete another
    run's lock). Best-effort — runs even when main() exits via sys.exit()."""
    try:
        if _BUILD_LOCK.exists():
            try:
                owner = int((_BUILD_LOCK.read_text(encoding="utf-8").strip() or "0"))
            except Exception:
                owner = os.getpid()
            if owner == os.getpid():
                _BUILD_LOCK.unlink()
    except Exception:
        pass


if __name__ == "__main__":
    _acquire_build_lock()
    try:
        main()
    finally:
        _release_build_lock()
