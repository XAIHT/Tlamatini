# build_installer.py — Tlamatini Installer Build Script
#
# Run this script after build.py has finished to produce a single-file
# Installer.exe that bundles pkg.zip (which already contains all support
# scripts such as CreateShortcut.ps1 and register_flw.ps1).
#
# A splash screen image is generated and embedded via PyInstaller's --splash
# flag so that the bootloader can display it immediately on double-click,
# before the ~1 GB bundle is even extracted.  This prevents users from
# thinking the installer is unresponsive and clicking it multiple times.

import hashlib
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
import shutil


# ── Splash image parameters (matches installer colour palette) ────────────────
_SPLASH_FILE = "splash_installer.png"
_SPLASH_W    = 480
_SPLASH_H    = 160
_BG          = (0x0f, 0x0f, 0x1a)   # dark background
_ACCENT      = (0x00, 0xd4, 0xff)   # cyan accent
_FG_PRIMARY  = (0xe0, 0xe0, 0xff)   # light text
_FG_SECONDARY= (0x88, 0x88, 0xaa)   # dim text


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
        pass  # Will be caught by the retry loop in clean_directory


def clean_directory(path, max_retries: int = 3, delay: float = 2.0):
    """Remove a directory tree with retry logic for Windows locked files.

    Strategy:
      1. Try shutil.rmtree up to *max_retries* times with a *delay* between.
      2. On each attempt, force-strip read-only flags via _on_rmtree_error.
      3. If the directory STILL exists after all retries, rename it out of
         the way (e.g. ``dist/Installer`` → ``dist/Installer_stale_<pid>``)
         so that PyInstaller can write to a clean directory instead of
         crashing on locked DLLs.
    """
    p = Path(path)
    if not p.exists():
        return

    for attempt in range(1, max_retries + 1):
        try:
            shutil.rmtree(p, onerror=_on_rmtree_error)
        except Exception as e:
            print(f"  rmtree attempt {attempt}/{max_retries} failed: {e}")

        if not p.exists():
            print(f"Removed: {p}")
            return

        if attempt < max_retries:
            print(f"  Retrying in {delay}s (locked files in {p.name})...")
            time.sleep(delay)

    # ── Last resort: rename the stubborn directory out of the way ──────
    stale_name = f"{p.name}_stale_{os.getpid()}"
    stale_path = p.parent / stale_name
    try:
        p.rename(stale_path)
        print(f"WARNING: Could not fully remove {p.name} — renamed to {stale_name}")
        print(f"  You can manually delete '{stale_path}' later.")
    except OSError as e:
        print(f"ERROR: Could not remove or rename {p}: {e}")
        print("  Please close any programs accessing this directory and re-run.")


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


# Splash generation removed due to Tcl/Tk crashes and extraction delays.
# Installer now launches instantly because pkg.zip is kept external.


# ── Main build routine ────────────────────────────────────────────────────────

def main():
    build_start = time.time()
    print("=" * 60)
    print("  Tlamatini Installer Build Script")
    print("=" * 60)

    root = Path(__file__).parent

    # ── 0) Verify prerequisites ───────────────────────────────────────
    print("\n--- Verifying prerequisites ---")
    pkg_zip = root / "pkg.zip"
    if not pkg_zip.exists():
        print("ERROR: pkg.zip not found. Run build.py first to generate it.")
        sys.exit(1)
    size_mb = pkg_zip.stat().st_size / (1024 * 1024)
    print(f"Found pkg.zip ({size_mb:.1f} MB)")

    install_script = root / "install.py"
    if not install_script.exists():
        print(f"ERROR: install.py not found at {install_script}")
        sys.exit(1)
    print("Found install.py")

    # ── 1) Clean previous Installer build artifacts ───────────────────
    run_step("Cleaning previous Installer build artifacts", lambda: [
        clean_directory(root / "build" / "Installer"),
        clean_directory(root / "dist" / "Installer"),
    ])

    old_exe = root / "dist" / "Installer.exe"
    if old_exe.exists():
        old_exe.unlink()
        print(f"Removed old: {old_exe}")

    old_spec = root / "Installer.spec"
    if old_spec.exists():
        old_spec.unlink()
        print(f"Removed old: {old_spec}")

    # ── 2) Ensure PyInstaller is available ────────────────────────────
    print("\n--- Checking PyInstaller ---")
    try:
        import PyInstaller  # noqa: F401
        print("PyInstaller is available.")
    except ImportError:
        print("PyInstaller not found — installing...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        if result.returncode != 0:
            print("ERROR: Failed to install PyInstaller. Aborting build.")
            sys.exit(1)

    # ── 3) Check Pyinstaller ──────────────────────────────────────────

    # ── 4) Run PyInstaller ────────────────────────────────────────────
    # pkg.zip is NO LONGER bundled into the .exe. 
    # This prevents the 10-20 second silent bootloader extraction delay 
    # and prevents users from spam-clicking Installer.exe and locking DLLs.
    
    # Ensure PyInstaller can locate Tcl/Tk data files for the GUI.
    py_prefix = Path(sys.prefix)
    base_prefix = Path(sys.base_prefix)
    tcl_candidates = [
        (py_prefix  / "tcl"     / "tcl8.6", py_prefix  / "tcl"     / "tk8.6"),
        (base_prefix / "tcl"    / "tcl8.6", base_prefix / "tcl"    / "tk8.6"),
        (py_prefix  / "lib"     / "tcl8.6", py_prefix  / "lib"     / "tk8.6"),
        (base_prefix / "lib"    / "tcl8.6", base_prefix / "lib"    / "tk8.6"),
        (py_prefix  / "Lib"     / "tcl8.6", py_prefix  / "Lib"     / "tk8.6"),
        (py_prefix  / "Library" / "lib" / "tcl8.6", py_prefix / "Library" / "lib" / "tk8.6"),
    ]
    for tcl_dir, tk_dir in tcl_candidates:
        if tcl_dir.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_dir)
            os.environ["TK_LIBRARY"]  = str(tk_dir)
            print(f"Set TCL_LIBRARY={tcl_dir}")
            print(f"Set TK_LIBRARY={tk_dir}")
            break
    else:
        print("WARNING: Could not locate Tcl/Tk data directories.")

    # Check if tkinter is available
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("WARNING: tkinter not installed — GUI may fail to launch.")

    # ── 3b) Locate Python DLL and VC runtime for bundling ────────────
    dll_args = run_step("Collecting Python DLL binaries",
                        collect_python_dll_binaries)

    # ── 3c) Write an application manifest that declares asInvoker ──
    manifest_path = root / "Installer.manifest"
    manifest_path.write_text(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n'
        '  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">\n'
        '    <security>\n'
        '      <requestedPrivileges>\n'
        '        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>\n'
        '      </requestedPrivileges>\n'
        '    </security>\n'
        '  </trustInfo>\n'
        '</assembly>\n',
        encoding="utf-8",
    )
    print(f"Created asInvoker manifest: {manifest_path}")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--noupx",               
        "--name", "Installer",
        f"--manifest={manifest_path}",
        "--hidden-import=_tkinter",
        "--collect-all", "tkinter",
        *dll_args,
        str(install_script),
    ]

    print("\n--- Starting PyInstaller build ---")
    result = subprocess.run(command, cwd=str(root))

    if result.returncode != 0:
        elapsed = time.time() - build_start
        print(f"\n--- PyInstaller build FAILED after {elapsed:.0f}s ---")
        sys.exit(1)

    # ── 5) Verify output ──────────────────────────────────────────────
    print("\n--- Verifying output ---")
    # --onedir produces dist/Installer/ containing Installer.exe + _internal/
    installer_dir = root / "dist" / "Installer"
    installer_exe = installer_dir / "Installer.exe"
    if not installer_exe.exists():
        print(f"ERROR: Expected output not found: {installer_exe}")
        sys.exit(1)
    out_mb = installer_exe.stat().st_size / (1024 * 1024)
    print(f"Installer.exe created successfully ({out_mb:.1f} MB)")
    print(f"Location: {installer_exe}")

    # ── 6) Clean up intermediate build artifacts ──────────────────────
    print("\n--- Cleaning up build artifacts ---")
    clean_directory(root / "build" / "Installer")
    for cleanup_file in [
        root / "Installer.spec",
        manifest_path,
    ]:
        if cleanup_file.exists():
            cleanup_file.unlink()
            print(f"Removed: {cleanup_file}")

    # ── 7) Copy pkg.zip into dist/Installer (next to the .exe) ───────
    # install.py expects pkg.zip sitting right next to Installer.exe.
    # We use verified copy with SHA-256 hash + size check and retry.
    print("\n--- Copying pkg.zip to dist/Installer ---")
    _verified_copy(pkg_zip, installer_dir / "pkg.zip")

    # ── 8) Setup Release Folder ──────────────────────────────────────
    # Copy the entire --onedir output (which now includes pkg.zip from
    # step 7) into the release directory.
    print("\n--- Packaging Release ---")
    release_dir = root / "dist" / "Tlamatini_Release"
    if release_dir.exists():
        shutil.rmtree(release_dir, onerror=_on_rmtree_error)

    # Copy the full --onedir folder as the release directory
    shutil.copytree(installer_dir, release_dir, dirs_exist_ok=True)

    # Verify pkg.zip also ended up in the release directory
    release_pkg = release_dir / "pkg.zip"
    if not release_pkg.exists():
        # copytree should have carried it, but if not, copy explicitly
        print("WARNING: pkg.zip missing from release dir after copytree — copying explicitly")
        _verified_copy(pkg_zip, release_pkg)
    else:
        # Verify the copytree'd file matches the source
        src_hash = _sha256(pkg_zip)
        dst_hash = _sha256(release_pkg)
        if src_hash != dst_hash:
            print("WARNING: pkg.zip in release dir has mismatched hash — re-copying")
            release_pkg.unlink()
            _verified_copy(pkg_zip, release_pkg)
        else:
            dst_size = release_pkg.stat().st_size
            print(f"VERIFIED: pkg.zip in release dir OK "
                  f"(SHA-256={src_hash[:12]}…, {dst_size / (1024*1024):.1f} MB)")

    print(f"\nCOPIED: Installer bundle and pkg.zip into {release_dir}\n")
    print("*" * 60)
    print("DISTRIBUTION INSTRUCTIONS:")
    print("Zip the 'dist/Tlamatini_Release' folder and distribute it to users.")
    print("When users double-click Installer.exe, it will launch instantly")
    print("with NO temp extraction or DLL locking issues.")
    print("*" * 60)

    elapsed = time.time() - build_start
    print(f"\n{'=' * 60}")
    print(f"  Installer build completed successfully in {elapsed:.0f}s")
    print(f"{'=' * 60}")


# ── Bulletproof file copy with SHA-256 verification and retry ─────────────────

def _sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file, reading in 8 MB chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _verified_copy(src: Path, dst: Path, max_retries: int = 3):
    """Copy *src* to *dst* with SHA-256 + size verification and retry.

    On each attempt the function:
      1. Computes the SHA-256 hash of the source file.
      2. Copies the file using shutil.copy2 (preserves metadata).
      3. Verifies the destination exists.
      4. Checks the file size matches the source.
      5. Computes the SHA-256 hash of the destination and compares.

    If any check fails the destination is removed and the copy is retried
    up to *max_retries* times with a 1-second pause between attempts.
    """
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    src_size = src.stat().st_size
    src_hash = _sha256(src)
    print(f"Source: {src}")
    print(f"  Size   : {src_size / (1024*1024):.1f} MB")
    print(f"  SHA-256: {src_hash[:16]}…")

    for attempt in range(1, max_retries + 1):
        print(f"Copy attempt {attempt}/{max_retries} → {dst}")

        # Ensure destination directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale destination if present
        if dst.exists():
            try:
                dst.unlink()
            except OSError as e:
                print(f"  WARNING: Could not remove stale dest: {e}")

        # Perform the copy
        try:
            shutil.copy2(src, dst)
        except Exception as e:
            print(f"  FAILED: shutil.copy2 raised {type(e).__name__}: {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise RuntimeError(
                f"Failed to copy {src.name} after {max_retries} attempts"
            ) from e

        # ── Verification ──────────────────────────────────────────────
        # 1. File must exist
        if not dst.exists():
            print("  FAILED: destination file does not exist after copy")
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise RuntimeError(
                f"{dst} does not exist after copy (attempt {attempt})"
            )

        # 2. Size must match
        dst_size = dst.stat().st_size
        if dst_size != src_size:
            print(f"  FAILED: size mismatch — src={src_size}, dst={dst_size}")
            try:
                dst.unlink()
            except OSError:
                pass
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise RuntimeError(
                f"Size mismatch after {max_retries} attempts: "
                f"src={src_size}, dst={dst_size}"
            )

        # 3. SHA-256 hash must match
        dst_hash = _sha256(dst)
        if dst_hash != src_hash:
            print(f"  FAILED: hash mismatch — src={src_hash[:16]}…, "
                  f"dst={dst_hash[:16]}…")
            try:
                dst.unlink()
            except OSError:
                pass
            if attempt < max_retries:
                time.sleep(1)
                continue
            raise RuntimeError(
                f"SHA-256 mismatch after {max_retries} attempts: "
                f"src={src_hash}, dst={dst_hash}"
            )

        # All checks passed
        print(f"  OK: copy verified (SHA-256={dst_hash[:12]}…, "
              f"{dst_size / (1024*1024):.1f} MB)")
        return

    # Should not reach here, but just in case
    raise RuntimeError(f"Failed to copy {src.name} after {max_retries} attempts")


if __name__ == "__main__":
    main()
