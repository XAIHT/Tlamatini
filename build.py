# build.py — Tlamatini Build Script

import os
import stat
import subprocess
import sys
import time
from pathlib import Path
import importlib.util
import shutil
import zipfile


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

    command = [
        sys.executable, '-m', 'PyInstaller', '--name', 'manage', '--console', '--noconfirm',
        *dll_args,
        f'--add-data=Tlamatini/agent/templates{separator}agent/templates',
        f'--add-data=Tlamatini/agent/static{separator}agent/static',
        f'--add-data=Tlamatini/staticfiles{separator}staticfiles',
        f'--add-data=Tlamatini/agent/config.json{separator}agent',
        f'--add-data=Tlamatini/agent/prompt.pmt{separator}agent',
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
        '--hidden-import=unstructured',
        '--hidden-import=filesearch_pb2',
        '--hidden-import=filesearch_pb2_grpc',
        '--collect-all', 'django_bootstrap5',
        '--collect-all', 'autobahn',
        '--collect-all', 'filesearch_pb2',
        '--collect-all', 'filesearch_pb2_grpc',
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

        # Individual files from Tlamatini/agent/
        for fname in ("config.json", "prompt.pmt"):
            src = Path("Tlamatini") / "agent" / fname
            dst = dist_manage / fname
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"Copied {src} -> {dst}")
            else:
                print(f"WARNING: {src} not found; skipping copy.")

        # Full directory trees
        dir_copies = {
            Path("Tlamatini") / "agent" / "images": dist_manage / "images",
            Path("Tlamatini") / "agent" / "agents": dist_manage / "agents",
        }
        for src_dir, dst_dir in dir_copies.items():
            if src_dir.exists():
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(src_dir, dst_dir)
                print(f"Copied directory: {src_dir} -> {dst_dir}")
            else:
                print(f"WARNING: Source directory not found: {src_dir}")

        # Required empty directories (must survive in pkg.zip)
        empty_dirs = (
            "application", "applications", "documentation",
            "context_files", "content_generated", "doc_generated",
        )
        for d in empty_dirs:
            target_dir = dist_manage / d
            target_dir.mkdir(parents=True, exist_ok=True)
            print(f"Ensured empty directory: {target_dir}")

    except Exception as e:
        print(f"Post-build step error: {e}")

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
            env.setdefault('DJANGO_SUPERUSER_USERNAME', 'tlamatini')
            env.setdefault('DJANGO_SUPERUSER_EMAIL', 'tlamatini@xaiht.com)
            env.setdefault('DJANGO_SUPERUSER_PASSWORD', 'tlamatini')
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
                "Tlamatini.ps1",
                "Tlamatini.ico",
                "CreateShortcut.ps1",
                "CreateShortcut.json",
                "Tlamatini/cat_art.py",
                "Tlamatini/chainer.py"
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

    elapsed = time.time() - build_start
    print(f"\n{'=' * 60}")
    print(f"  Build completed successfully in {elapsed:.0f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()