# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Lint and compile every owned Python source file from a visible console.

Run from the repository's foreground development console:
    python scripts/check_python_quality.py

Uses Git's tracked/unignored source inventory, including skill mirrors. Never
imports application modules, writes bytecode, or opens the application database.
"""
from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import sys
import warnings


ROOT = Path(__file__).resolve().parents[1]


def require_visible_console():
    """Refuse an invisible Windows development run before launching checks."""
    if os.name != "nt":
        if not sys.stdout.isatty():
            raise SystemExit("A visible foreground development terminal is required.")
        return
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [ctypes.c_void_p]
    window = kernel32.GetConsoleWindow()
    # In Windows Terminal (Windows 11's default console) GetConsoleWindow()
    # returns a 'PseudoConsoleWindow' that is never the foreground window: the
    # terminal that OWNS it is (measured 2026-10-18: CASCADIA_HOSTING_WINDOW_CLASS
    # as GA_ROOTOWNER and GetForegroundWindow). Accept the console or its owner.
    shown = [hwnd for hwnd in (window, user32.GetAncestor(window, 3) if window else None)
             if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd)]
    if not (window and shown and user32.GetForegroundWindow() in shown):
        raise SystemExit("A verified visible foreground console is required.")


def main():
    require_visible_console()
    if (ROOT / ".git").exists():
        inventory = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        ).decode("utf-8").split("\0")
    else:
        # Shipped self-modify snapshots deliberately do not contain .git.
        inventory = []
        for directory, subdirectories, names in os.walk(ROOT, followlinks=False):
            subdirectories[:] = [name for name in subdirectories if name not in {
                ".git", "Temp", "dist", "build", "node_modules", "python", "__pycache__",
            }]
            inventory.extend(str((Path(directory) / name).relative_to(ROOT))
                             for name in names if name.endswith(".py"))
    files = sorted({
        name for name in inventory
        if name.endswith(".py") and (ROOT / name).is_file()
        and not set(Path(name).parts) & {
            "Temp", "dist", "build", "node_modules", "python", "__pycache__",
        }
    })
    if not files:
        raise SystemExit("No owned Python files found; refusing an empty quality gate.")
    bundled_ruff = ROOT / "python/Scripts/ruff.exe"
    if not bundled_ruff.is_file():
        bundled_ruff = Path(sys.executable).parent / "Scripts/ruff.exe"
    ruff = str(bundled_ruff) if bundled_ruff.is_file() else shutil.which("ruff")
    if not ruff:
        raise SystemExit("Ruff is required; install the repository's development dependencies.")

    failed = False
    for name in files:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", SyntaxWarning)
                compile((ROOT / name).read_bytes(), name, "exec")
        except (SyntaxError, SyntaxWarning, ValueError) as error:
            failed = True
            print(f"COMPILE FAIL: {name}: {error}", flush=True)
    print(f"Compiled {len(files)} owned Python sources.", flush=True)
    for label, options in (
        ("Ruff default rules", []),
        ("Undefined names including suppressed diagnostics",
         ["--ignore-noqa", "--select", "E9,F821,F822,F823"]),
    ):
        print(label, flush=True)
        # Bound Windows command length without omitting hidden skill directories.
        for start in range(0, len(files), 40):
            result = subprocess.run(
                [ruff, "check", *options, *files[start:start + 40]], cwd=ROOT,
                check=False,
            )
            failed |= result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
