#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
build_complete_private_release.py -- KEYED (private) release builder.

Builds a Tlamatini release for YOUR OWN machine: config secrets are real (keyed),
so the artifact CONTAINS YOUR PRIVATE DATA and must NOT be published. It is the
deliberate twin of build_complete_public_release.py (the scrubbed, leak-verified
build that is safe to distribute). Both reuse regen_secrets.py.

This script does NOT scrub the tree and does NOT run the leak auditor -- a keyed
build is meant to keep your real values. It ensures the tree is keyed, freezes,
packages the installer, and zips.

Pipeline
--------
  0. SAFETY: refuse the carried interpreter (build with the SYSTEM python).
  1. regen_secrets.py --mode keyed   -> real secrets in the config files.
  2. build.py [--self-modify]        -> freeze app + pkg.zip.
  3. build_uninstaller.py            -> Uninstaller.exe.
  4. build_installer.py              -> dist/Tlamatini_Release_v<ver>/.
  5. zip -> dist/Tlamatini_Release_v<ver>_PRIVATE_KEYED_win11x64.zip
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DIST = REPO_ROOT / "dist"
REGEN = REPO_ROOT / "regen_secrets.py"
BUILD = REPO_ROOT / "build.py"
BUILD_UNINST = REPO_ROOT / "build_uninstaller.py"
BUILD_INST = REPO_ROOT / "build_installer.py"


def banner(msg: str) -> None:
    print("\n" + "=" * 74, flush=True)
    print(f"== {msg}", flush=True)
    print("=" * 74, flush=True)


def assert_system_python(py: str) -> None:
    try:
        resolved = Path(py).resolve()
    except Exception:
        return
    carried = (REPO_ROOT / "python").resolve()
    try:
        resolved.relative_to(carried)
    except ValueError:
        return
    sys.exit(
        f"REFUSING: '{py}' is the CARRIED python under {carried}.\n"
        f"Build with the SYSTEM python, e.g.:\n"
        f'  & "C:/Program Files/Python312/python.exe" .\\build_complete_private_release.py'
    )


def _utf8_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd), env=_utf8_env()).returncode


def newest_release_dir() -> Path | None:
    cands = sorted(glob.glob(str(DIST / "Tlamatini_Release_v*")),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    for c in cands:
        if Path(c).is_dir():
            return Path(c)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a PRIVATE (keyed, contains your real data) Tlamatini release.")
    ap.add_argument("--keys-file", default=str(REPO_ROOT / "data.keys"),
                    help="KEY=VALUE secrets file (default: data.keys next to script).")
    ap.add_argument("--version", default="", help="explicit version (default: git-tag derived)")
    ap.add_argument("--python", default=sys.executable, help="system python to drive the build")
    ap.add_argument("--no-self-modify", action="store_true",
                    help="do NOT bundle the TlamatiniSourceCode self-modify tree "
                         "(default: it IS bundled).")
    args = ap.parse_args(argv)

    py = args.python
    assert_system_python(py)
    self_modify = not args.no_self_modify

    banner("PRIVATE RELEASE BUILD  (KEYED -- contains your real data; DO NOT publish)")
    print(f"repo        : {REPO_ROOT}")
    print(f"python      : {py}")
    print(f"keys file   : {args.keys_file}")
    print(f"self-modify : {'YES' if self_modify else 'no'}")

    banner("STEP 1/5  regen_secrets.py --mode keyed")
    if run([py, str(REGEN), "--mode", "keyed", "--keys-file", args.keys_file]) != 0:
        sys.exit("regen_secrets keyed failed.")

    banner("STEP 2/5  build.py")
    build_cmd = [py, str(BUILD)]
    if self_modify:
        build_cmd.append("--self-modify")
    if args.version:
        build_cmd.append(args.version)
    if run(build_cmd) != 0:
        sys.exit("build.py failed.")

    banner("STEP 3/5  build_uninstaller.py")
    if run([py, str(BUILD_UNINST)] + ([args.version] if args.version else [])) != 0:
        sys.exit("build_uninstaller.py failed.")

    banner("STEP 4/5  build_installer.py")
    if run([py, str(BUILD_INST)] + ([args.version] if args.version else [])) != 0:
        sys.exit("build_installer.py failed.")

    rel = newest_release_dir()
    if rel is None:
        sys.exit("ERROR: no dist/Tlamatini_Release_v* folder was produced.")

    banner("STEP 5/5  packaging PRIVATE KEYED zip")
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_base = DIST / f"{rel.name}_PRIVATE_KEYED_win11x64_{ts}"
    archive = shutil.make_archive(str(out_base), "zip", root_dir=str(DIST), base_dir=rel.name)

    banner("PRIVATE RELEASE COMPLETE -- KEYED (DO NOT PUBLISH)")
    print(f"  release folder : {rel}")
    print(f"  private zip    : {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
