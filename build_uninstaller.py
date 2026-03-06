# build_uninstaller.py — Tlamatini Uninstaller Build Script
#
# Run this script to produce a single-file Uninstaller.exe that bundles the
# uninstall.py GUI.  The resulting executable is copied to the project root
# so that build_installer.py can include it in the release package.
#
# Workflow:
#   1. python build.py                 → produces pkg.zip
#   2. python build_uninstaller.py     → produces Uninstaller.exe at project root
#   3. python build_installer.py       → produces release with Installer + Uninstaller

import os
import stat
import subprocess
import sys
import time
from pathlib import Path
import shutil


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
        pass


def clean_directory(path):
    """Remove a directory tree if it exists (handles locked files on Windows)."""
    p = Path(path)
    if p.exists():
        shutil.rmtree(p, onerror=_on_rmtree_error)
        print(f"Removed: {p}")


def _gather_search_dirs():
    """Build an ordered, deduplicated list of directories to search for DLLs."""
    dirs: list[Path] = []

    dirs.append(Path(sys.base_prefix))
    dirs.append(Path(sys.prefix))
    dirs.append(Path(sys.executable).parent)

    dirs.append(Path(sys.base_prefix) / "DLLs")
    dirs.append(Path(sys.executable).parent / "DLLs")

    sdk_base = Path("C:/Program Files (x86)/Windows Kits/10/Redist")
    if sdk_base.is_dir():
        dirs.append(sdk_base / "ucrt/DLLs/x64")
        for ver_dir in sdk_base.iterdir():
            if ver_dir.is_dir():
                dirs.append(ver_dir / "ucrt/DLLs/x64")

    dirs.append(Path("C:/Windows/System32"))

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
    """Find all DLLs required by the embedded Python so the bootloader
    can load python3XX.dll without errors.

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

    # python3XX.dll (versioned)
    found = _find_first_dll(dll_name, search_dirs)
    if found:
        binaries.append(f"--add-binary={found};.")
        print(f"Bundling Python DLL: {found}")
    else:
        print(f"WARNING: Could not locate {dll_name}")

    # python3.dll (stable ABI)
    found = _find_first_dll("python3.dll", search_dirs)
    if found:
        binaries.append(f"--add-binary={found};.")
        print(f"Bundling stable ABI DLL: {found}")

    # VC runtime DLLs
    for vc_name in ["vcruntime140.dll", "vcruntime140_1.dll"]:
        found = _find_first_dll(vc_name, search_dirs)
        if found:
            binaries.append(f"--add-binary={found};.")
            print(f"Bundling VC runtime: {found}")

    # Universal CRT
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

    return binaries


# ── Main build routine ────────────────────────────────────────────────────────

def main():
    build_start = time.time()
    print("=" * 60)
    print("  Tlamatini Uninstaller Build Script")
    print("=" * 60)

    root = Path(__file__).parent

    # ── 0) Verify prerequisites ───────────────────────────────────────
    print("\n--- Verifying prerequisites ---")
    uninstall_script = root / "uninstall.py"
    if not uninstall_script.exists():
        print(f"ERROR: uninstall.py not found at {uninstall_script}")
        sys.exit(1)
    print("Found uninstall.py")

    # ── 1) Clean previous Uninstaller build artifacts ─────────────────
    run_step("Cleaning previous Uninstaller build artifacts", lambda: [
        clean_directory(root / "build" / "Uninstaller"),
    ])

    old_exe = root / "dist" / "Uninstaller.exe"
    if old_exe.exists():
        old_exe.unlink()
        print(f"Removed old: {old_exe}")

    old_root_exe = root / "Uninstaller.exe"
    if old_root_exe.exists():
        old_root_exe.unlink()
        print(f"Removed old: {old_root_exe}")

    old_spec = root / "Uninstaller.spec"
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
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
        )
        if result.returncode != 0:
            print("ERROR: Failed to install PyInstaller. Aborting build.")
            sys.exit(1)

    # ── 3) Locate Tcl/Tk data files for tkinter GUI ──────────────────
    py_prefix = Path(sys.prefix)
    base_prefix = Path(sys.base_prefix)
    tcl_candidates = [
        (py_prefix   / "tcl"     / "tcl8.6", py_prefix   / "tcl"     / "tk8.6"),
        (base_prefix / "tcl"     / "tcl8.6", base_prefix / "tcl"     / "tk8.6"),
        (py_prefix   / "lib"     / "tcl8.6", py_prefix   / "lib"     / "tk8.6"),
        (base_prefix / "lib"     / "tcl8.6", base_prefix / "lib"     / "tk8.6"),
        (py_prefix   / "Lib"     / "tcl8.6", py_prefix   / "Lib"     / "tk8.6"),
        (py_prefix   / "Library" / "lib" / "tcl8.6",
         py_prefix   / "Library" / "lib" / "tk8.6"),
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

    # ── 4) Collect Python DLL binaries ────────────────────────────────
    dll_args = run_step("Collecting Python DLL binaries",
                        collect_python_dll_binaries)

    # ── 5) Write an application manifest (asInvoker) ──────────────────
    manifest_path = root / "Uninstaller.manifest"
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

    # ── 6) Run PyInstaller (--onefile for a single portable exe) ──────
    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--noupx",
        "--name", "Uninstaller",
        f"--manifest={manifest_path}",
        "--hidden-import=_tkinter",
        "--collect-all", "tkinter",
        *dll_args,
        str(uninstall_script),
    ]

    print("\n--- Starting PyInstaller build ---")
    result = subprocess.run(command, cwd=str(root))

    if result.returncode != 0:
        elapsed = time.time() - build_start
        print(f"\n--- PyInstaller build FAILED after {elapsed:.0f}s ---")
        sys.exit(1)

    # ── 7) Verify output ──────────────────────────────────────────────
    print("\n--- Verifying output ---")
    uninstaller_exe = root / "dist" / "Uninstaller.exe"
    if not uninstaller_exe.exists():
        print(f"ERROR: Expected output not found: {uninstaller_exe}")
        sys.exit(1)
    out_mb = uninstaller_exe.stat().st_size / (1024 * 1024)
    print(f"Uninstaller.exe created successfully ({out_mb:.1f} MB)")

    # ── 8) Copy Uninstaller.exe to project root ──────────────────────
    dest = root / "Uninstaller.exe"
    shutil.copy2(uninstaller_exe, dest)
    dest_mb = dest.stat().st_size / (1024 * 1024)
    print(f"\nCopied Uninstaller.exe to project root: {dest} ({dest_mb:.1f} MB)")

    # ── 9) Clean up intermediate build artifacts ──────────────────────
    print("\n--- Cleaning up build artifacts ---")
    clean_directory(root / "build" / "Uninstaller")

    # Clean build/ if empty
    build_dir = root / "build"
    if build_dir.exists() and not list(build_dir.iterdir()):
        build_dir.rmdir()
        print(f"Removed empty: {build_dir}")

    for cleanup_file in [
        root / "Uninstaller.spec",
        manifest_path,
    ]:
        if cleanup_file.exists():
            cleanup_file.unlink()
            print(f"Removed: {cleanup_file}")

    # Remove dist/Uninstaller.exe (canonical copy is at project root)
    if uninstaller_exe.exists():
        uninstaller_exe.unlink()
        print(f"Removed: {uninstaller_exe}")

    # Clean dist/ if empty
    dist_dir = root / "dist"
    if dist_dir.exists() and not list(dist_dir.iterdir()):
        dist_dir.rmdir()
        print(f"Removed empty: {dist_dir}")

    elapsed = time.time() - build_start
    print(f"\n{'=' * 60}")
    print(f"  Uninstaller build completed successfully in {elapsed:.0f}s")
    print(f"  Uninstaller.exe is at: {dest}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
