# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Freeze the current setup clients and attach the newly built full payload.

Run in a verified visible foreground PowerShell -NoExit console. No Git writes.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_runtime_assets import verify_package, file_record
from versioning import render_versioninfo_for, resolve_build_version
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Temp/setup-release-validation"


def main():
    from markdown_canvas_visible import visible_console
    visible_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    version = resolve_build_version()
    if not args.package_only:
        for name, script, layout in (("Installer", "install.py", "--onedir"), ("Uninstaller", "uninstall.py", "--onefile")):
            version_file = render_versioninfo_for(version, OUT / f"{name}.version.txt",
                                            product_name=f"Tlamatini {name}", original_filename=f"{name}.exe")
            command = [sys.executable, "-m", "PyInstaller", layout, "--windowed", "--noconfirm", "--noupx",
                       "--name", name, "--distpath", str(OUT / "bin"), "--workpath", str(OUT / "build"),
                       "--specpath", str(OUT), "--version-file", str(version_file),
                       "--icon", str(ROOT / "Tlamatini.ico"), "--hidden-import", "_tkinter",
                       "--add-data", str(ROOT / "Tlamatini.ico") + ";.",
                       "--collect-all", "tkinter", str(ROOT / script)]
            print(f"BUILDING {name} into {OUT / 'bin'}", flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
    if args.freeze_only:
        print("CURRENT SETUP EXECUTABLES FROZEN; full package validation remains.", flush=True)
        return
    verify_package(OUT / "pkg.zip")
    release = OUT / "bin/Installer"
    shutil.copy2(OUT / "bin/Uninstaller.exe", release / "Uninstaller.exe")
    # A hardlink saves several GB while retaining a real pkg.zip beside the EXE.
    if not (release / "pkg.zip").exists():
        (release / "pkg.zip").hardlink_to(OUT / "pkg.zip")
    records = {name: file_record(release / name) for name in ("Installer.exe", "Uninstaller.exe", "pkg.zip")}
    records["source"] = {name: file_record(ROOT / name) for name in (
        "install.py", "uninstall.py", "setup_wizard.py", "setup_windows.py", "setup_recovery.py", "setup_logging.py", "CreateShortcut.ps1")}
    (OUT / "artifacts.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"COMPILED CLIENTS READY: {release}\nOriginal release and development database untouched.", flush=True)


if __name__ == "__main__":
    main()
