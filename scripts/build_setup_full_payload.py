# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Build the current complete payload in a disposable, private source snapshot.

Run from a verified visible foreground PowerShell -NoExit console. This is a
local validation artifact, never a publication command. No Git writes occur.
"""
from pathlib import Path
import os
import argparse
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Temp/setup-release-validation"
SOURCE = OUT / "source"


def main():
    from markdown_canvas_visible import visible_console
    visible_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if SOURCE.exists() and not args.resume:
        raise RuntimeError(f"Snapshot already exists; inspect it before resuming: {SOURCE}")
    SOURCE.mkdir(parents=True, exist_ok=args.resume)
    trees = {"Tlamatini", "python", "scripts", "docs", "security", "pyinstaller_hooks",
             "Templates", "demo_flows"}
    skipped = {".git", "Temp", "temp", "__pycache__", "node_modules", "pools",
               ".tlamatini", "security_logs", "staticfiles", "TlamatiniSourceCode"}

    def ignore(_directory, names):
        return [name for name in names if name in skipped or name.endswith(
            (".pyc", ".pyo", ".log", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))]

    copied = 0
    def copy_file(source, destination):
        nonlocal copied
        source, destination = Path(source), Path(destination)
        if not (destination.is_file() and source.stat().st_size == destination.stat().st_size
                and source.stat().st_mtime_ns == destination.stat().st_mtime_ns):
            shutil.copy2(source, destination)
        copied += 1
        if copied % 1000 == 0:
            print(f"Snapshot files checked: {copied:,}", flush=True)
        return str(destination)
    for item in ROOT.iterdir():
        if item.is_file() and item.suffix.lower() in {
                ".py", ".ps1", ".json", ".txt", ".md", ".ico", ".keys"}:
            copy_file(item, SOURCE / item.name)
    for name in sorted(trees):
        print(f"Copying current build input: {name}", flush=True)
        shutil.copytree(ROOT / name, SOURCE / name, ignore=ignore,
                        dirs_exist_ok=args.resume, copy_function=copy_file)
    sys.path.insert(0, str(ROOT))
    from versioning import resolve_build_version
    version = resolve_build_version()
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    print(f"Building NEW complete payload v{version} from current uncommitted sources: {SOURCE}", flush=True)
    subprocess.run([sys.executable, "-u", str(SOURCE / "build.py"),
                    "--version", version, "--no-self-modify"], cwd=SOURCE, env=env, check=True)
    from build_runtime_assets import verify_package
    verify_package(SOURCE / "pkg.zip")
    shutil.copy2(SOURCE / "pkg.zip", OUT / "pkg.zip")
    print(f"NEW FULL PAYLOAD VERIFIED: {OUT / 'pkg.zip'}", flush=True)


if __name__ == "__main__":
    main()
