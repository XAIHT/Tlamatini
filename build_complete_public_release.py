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
build_complete_public_release.py -- PUBLIC release builder (scrubbed + verified).

Builds a CLEAN Tlamatini release safe to distribute: secrets become placeholders
and your private data is scrubbed BEFORE the build, then the package is re-audited
by check_private_data.py. The build BLOCKS only if YOUR personal data actually
survives into the package (the thousands of structural matches on bundled
third-party binaries are reported as informational, not blockers).

Twin of build_complete_private_release.py (the keyed build for your own machine).

ABSOLUTE RULE (CLAUDE.md PRIVATE DATA GUARD): never rewrites git history. It makes
FORWARD, in-place edits to a temporary scrub of the WORKING TREE, then RESTORES the
tree byte-for-byte afterwards.

Pipeline
--------
  0. SAFETY: refuse the carried interpreter; load leak targets (auto from
     .private_targets.json when not given).
  1. BACK UP touched files (restored in `finally`).
  2. regen_secrets.py --mode push-able  -> config secrets become placeholders.
  3. sanitize external_mcps.json (ship an empty catalog) + SCRUB the working tree.
  4. build.py [--self-modify]            -> freeze app + pkg.zip (build.py deletes dist/).
  5. VERIFY: extract pkg.zip and run check_private_data.py over it.
       any of YOUR personal data present -> ABORT, tree restored.
  6. build_uninstaller.py + build_installer.py -> dist/Tlamatini_Release_v<ver>/.
  7. zip -> dist/..._PUBLIC_CLEAN_win11x64.zip
  8. ALWAYS restore the working tree (finally).
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent
DIST = REPO_ROOT / "dist"
DIST_MANAGE = DIST / "manage"
PKG_ZIP = REPO_ROOT / "pkg.zip"            # build.py's real artifact (it deletes dist/)
VERIFY_EXTRACT = REPO_ROOT / "Temp" / "public_verify_extract"
EXTERNAL_MCPS = REPO_ROOT / "Tlamatini" / "agent" / "external_mcps.json"  # user state
REGEN = REPO_ROOT / "regen_secrets.py"
BUILD = REPO_ROOT / "build.py"
BUILD_UNINST = REPO_ROOT / "build_uninstaller.py"
BUILD_INST = REPO_ROOT / "build_installer.py"
CHECKER = REPO_ROOT / "check_private_data.py"

# Auto-discovered local targets file (gitignored) used when no --targets-file /
# --target / env CHECK_PRIVATE_DATA_TARGETS is given. Values are read at run
# time -- never hardcoded.
DEFAULT_TARGETS_FILES = [REPO_ROOT / ".private_targets.json",
                         REPO_ROOT / "private_targets.json"]

PLACEHOLDER = "<REDACTED>"

# Angela's NAME is NEVER scrubbed -- in the public OR the private build. Her authorship
# stays everywhere, always, by her explicit instruction. Only her OTHER private data
# (emails / phones / the "Ana*" legal-name variants / handles / secrets) is masked.
# These values are dropped from the scrub set before any redaction runs.
KEEP_NAMES = {"angela"}  # matched case-insensitively


def _is_kept_name(value: str) -> bool:
    return (value or "").strip().lower() in KEEP_NAMES

REGEN_TOUCHED = [
    REPO_ROOT / "Tlamatini" / "agent" / "config.json",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "telegrammer" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "whatsapper" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "teletlamatini" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "emailer" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "recmailer" / "config.yaml",
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist",
             "build", ".mypy_cache", ".ruff_cache", ".pytest_cache",
             "staticfiles", "Temp", "python", "ms-playwright", "jre", "git"}
TEXT_EXT = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".env",
            ".cfg", ".ini", ".toml", ".html", ".css", ".csv", ".pmt", ".keys"}
# NEVER scrub the sources of truth: the keys vault and the targets file. Scrubbing
# .private_targets.json turns your real values into "<REDACTED>" inside it, which
# then makes the verifier hunt for the literal text "<REDACTED>" and "find" it in
# every scrubbed file (the 737-false-positive bug). data.keys must stay intact too.
SCRUB_SKIP_FILES = {"data.keys", ".private_targets.json", "private_targets.json"}

SECRET_KEY_RE = re.compile(
    r'(?i)("(?:api[_-]?key|api[_-]?secret|token|access[_-]?token|auth[_-]?token|'
    r'password|passwd|secret|client[_-]?secret|session[_-]?string|bearer)"\s*:\s*")'
    r'([^"]+)(")'
)


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
        f'  & "C:/Program Files/Python312/python.exe" .\\build_complete_public_release.py'
    )


def _utf8_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd), env=_utf8_env()).returncode


def default_targets_file() -> Path | None:
    for cand in DEFAULT_TARGETS_FILES:
        if cand.is_file():
            return cand
    return None


def load_targets_values(args) -> list[str]:
    """Reuse check_private_data.load_targets (NEVER hardcode private data)."""
    sys.path.insert(0, str(REPO_ROOT))
    import check_private_data as cpd  # noqa: E402
    ns = SimpleNamespace(targets_file=args.targets_file, target=args.target)
    targets = cpd.load_targets(ns)
    # NEVER scrub Angela's name -- keep her authorship everywhere, in every build.
    vals = [t["value"] for t in targets
            if t.get("value", "").strip() and not _is_kept_name(t["value"])]
    return sorted(set(vals), key=len, reverse=True)


class Backup:
    """Byte-for-byte backup + guaranteed restore of every file we mutate."""

    def __init__(self, root: Path):
        self.dir = root / "Temp" / f"public_build_backup_{time.strftime('%Y%m%d_%H%M%S')}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.saved: dict[Path, Path] = {}

    def save(self, path: Path) -> None:
        path = path.resolve()
        if path in self.saved or not path.exists():
            return
        rel = path.relative_to(REPO_ROOT) if str(path).startswith(str(REPO_ROOT)) else Path(path.name)
        dst = self.dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        self.saved[path] = dst

    def restore_all(self) -> None:
        for orig, bak in self.saved.items():
            try:
                shutil.copy2(bak, orig)
            except Exception as e:  # pragma: no cover
                print(f"  [!] restore FAILED for {orig}: {e}", file=sys.stderr)
        print(f"  restored {len(self.saved)} file(s) to their original bytes.")


def scrub_file(path: Path, values: list[str], extra: list[str], backup: Backup) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0
    original = text
    for v in values + extra:
        if v and v in text:
            text = text.replace(v, PLACEHOLDER)
    text = SECRET_KEY_RE.sub(lambda m: m.group(1) + PLACEHOLDER + m.group(3), text)
    if text != original:
        backup.save(path)
        path.write_text(text, encoding="utf-8")
        return 1
    return 0


def scrub_tree(values: list[str], extra: list[str], backup: Backup) -> int:
    changed = 0
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            if name in SCRUB_SKIP_FILES:
                continue
            changed += scrub_file(Path(dirpath) / name, values, extra, backup)
    return changed


def newest_release_dir() -> Path | None:
    cands = sorted(glob.glob(str(DIST / "Tlamatini_Release_v*")),
                   key=lambda p: os.path.getmtime(p), reverse=True)
    for c in cands:
        if Path(c).is_dir():
            return Path(c)
    return None


def resolve_verify_root() -> Path:
    """What STEP 5 scans. build.py creates pkg.zip then DELETES dist/, so the real
    artifact is pkg.zip -- extract it and scan that. Fall back to dist/manage when
    an older build.py still leaves it in place."""
    if DIST_MANAGE.exists():
        return DIST_MANAGE
    if PKG_ZIP.exists():
        if VERIFY_EXTRACT.exists():
            shutil.rmtree(VERIFY_EXTRACT, ignore_errors=True)
        VERIFY_EXTRACT.mkdir(parents=True, exist_ok=True)
        print(f"  build.py removed dist/; extracting {PKG_ZIP.name} to verify...", flush=True)
        with zipfile.ZipFile(PKG_ZIP) as zf:
            zf.extractall(VERIFY_EXTRACT)
        return VERIFY_EXTRACT
    sys.exit("ERROR: neither dist/manage nor pkg.zip exists after build.py.")


def verify_clean(py: str, verify_root: Path, targets_file: str,
                 target: list[str], use_llm: bool) -> int:
    """Run the auditor over the built package. Returns the number of files that
    contain YOUR personal data (the BLOCKING count). Structural/binary pattern
    matches (kyber keyword, certs, high-entropy, PEM) are reported but never block."""
    report = REPO_ROOT / "public_release_verify_report.json"
    cmd = [py, str(CHECKER), "--local", "--repo", str(verify_root),
           "--output", str(report)]
    if targets_file:
        cmd += ["--targets-file", targets_file]
    for t in target or []:
        cmd += ["--target", t]
    if not use_llm:
        cmd += ["--no-llm"]
    rc = run(cmd)
    if rc == 2:
        sys.exit("VERIFY ERROR: auditor got no targets. Pass --targets-file/--target.")
    import json
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        return 1 if rc else 0
    findings = []
    for scan in data.get("scans", []):
        findings += scan.get("result", {}).get("findings", [])

    def _is_sensitive(value: str) -> bool:
        # BLOCK only on genuinely-unique PII: emails / handles (contain '@') and
        # phone numbers (>=7 digits). Bare common names ("<REDACTED>", "Ana") are NOT
        # blocked -- they appear all over bundled third-party libraries (django,
        # nltk, emoji, ...) and <REDACTED> wants her name left everywhere by design.
        v = value or ""
        return ("@" in v) or (sum(c.isdigit() for c in v) >= 7)

    personal = 0
    name_only = 0
    struct = 0
    for f in findings:
        ms = f.get("matches", [])
        pii = [m for m in ms
               if (m.get("layer", "").startswith("bytes:") or m.get("layer") == "fuzzy-regex")]
        if any(_is_sensitive(m.get("target", "")) for m in pii):
            personal += 1
        elif pii:
            name_only += 1
        struct += sum(1 for m in ms if m.get("layer", "").startswith(("struct:", "steg:")))
    print(f"  sensitive PII leak files (BLOCKING: emails/handles/phones): {personal}")
    print(f"  name-only matches (NOT blocking; common names left as-is): {name_only}")
    print(f"  structural/binary false-positive matches (informational only): {struct}")
    return personal


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a PUBLIC (scrubbed, leak-verified) Tlamatini release.")
    ap.add_argument("--targets-file", help="JSON {names,phones,handles} or newline list of private values")
    ap.add_argument("--target", action="append", help="one private value to scrub/verify (repeatable)")
    ap.add_argument("--extra-redact", action="append", default=[],
                    help="extra literal string to scrub (e.g. a leaked apikey); repeatable")
    ap.add_argument("--version", default="", help="explicit version (default: git-tag derived)")
    ap.add_argument("--python", default=sys.executable, help="system python to drive the build")
    ap.add_argument("--self-modify", action="store_true",
                    help="also bundle the (scrubbed) TlamatiniSourceCode tree")
    ap.add_argument("--verify-llm", action="store_true",
                    help="let the auditor also run its LLM deep-review layer (slower, deeper)")
    ap.add_argument("--keep-scrubbed", action="store_true",
                    help="DANGEROUS: do not restore the working tree afterwards")
    args = ap.parse_args(argv)

    py = args.python
    assert_system_python(py)

    # If no targets given, auto-load the local gitignored targets file so the bare
    # command just works. Values are read from that file -- never hardcoded.
    if (not args.targets_file and not args.target
            and not os.environ.get("CHECK_PRIVATE_DATA_TARGETS")):
        auto = default_targets_file()
        if auto:
            args.targets_file = str(auto)
            print(f"targets file : auto-loaded {auto.name} (no --targets-file given)")

    values = load_targets_values(args)
    if not values:
        sys.exit("REFUSING: no leak targets supplied. Create .private_targets.json at "
                 "the repo root (JSON {\"names\":[],\"phones\":[],\"handles\":[],"
                 "\"emails\":[]}), or pass --targets-file / --target / env "
                 "CHECK_PRIVATE_DATA_TARGETS (private data is NEVER hardcoded).")

    banner("PUBLIC RELEASE BUILD  (SCRUBBED + LEAK-VERIFIED -- safe to distribute)")
    print(f"repo         : {REPO_ROOT}")
    print(f"python       : {py}")
    print(f"targets      : {len(values)} value(s) to scrub + verify")
    print(f"self-modify  : {'YES (scrubbed snapshot)' if args.self_modify else 'no'}")

    backup = Backup(REPO_ROOT)
    ok = False
    try:
        banner("STEP 1/6  regen_secrets.py --mode push-able")
        for f in REGEN_TOUCHED:
            backup.save(f)
        if run([py, str(REGEN), "--mode", "push-able"]) != 0:
            sys.exit("regen_secrets push-able failed.")

        # Ship a CLEAN External-MCP catalog in the PUBLIC build (user state).
        if EXTERNAL_MCPS.exists():
            backup.save(EXTERNAL_MCPS)
            EXTERNAL_MCPS.write_text('{\n  "mcpServers": {},\n  "active": []\n}\n',
                                     encoding="utf-8")
            print("  sanitized external_mcps.json (empty catalog for public build).")

        banner("STEP 2/6  scrubbing private data from the working tree")
        n = scrub_tree(values, args.extra_redact, backup)
        print(f"  scrubbed {n} file(s).")

        banner("STEP 3/6  build.py (reads the scrubbed tree)")
        build_cmd = [py, str(BUILD)]
        if args.self_modify:
            build_cmd.append("--self-modify")
        if args.version:
            build_cmd.append(args.version)
        if run(build_cmd) != 0:
            sys.exit("build.py failed.")

        # build.py creates pkg.zip then removes dist/, so scan the package
        # (extracted) instead of the deleted dist/manage.
        banner("STEP 4/6  VERIFY the built package is clean (check_private_data.py)")
        verify_root = resolve_verify_root()
        leaks = verify_clean(py, verify_root, args.targets_file, args.target, args.verify_llm)
        if VERIFY_EXTRACT.exists():
            shutil.rmtree(VERIFY_EXTRACT, ignore_errors=True)
        if leaks:
            sys.exit(f"\n!!! ABORT: {leaks} file(s) in the build STILL contain your personal "
                     f"data. No public artifact produced. See public_release_verify_report.json. "
                     f"(Working tree will be restored.)")
        print("  VERIFIED CLEAN: 0 files with your personal data.")

        banner("STEP 5/6  build_uninstaller.py + build_installer.py")
        if run([py, str(BUILD_UNINST)] + ([args.version] if args.version else [])) != 0:
            sys.exit("build_uninstaller.py failed.")
        if run([py, str(BUILD_INST)] + ([args.version] if args.version else [])) != 0:
            sys.exit("build_installer.py failed.")

        rel = newest_release_dir()
        if rel is None:
            sys.exit("ERROR: no dist/Tlamatini_Release_v* folder was produced.")

        banner("STEP 6/6  packaging PUBLIC CLEAN zip")
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_base = DIST / f"{rel.name}_PUBLIC_CLEAN_win11x64_{ts}"
        archive = shutil.make_archive(str(out_base), "zip", root_dir=str(DIST), base_dir=rel.name)

        ok = True
        banner("PUBLIC RELEASE COMPLETE -- VERIFIED CLEAN")
        print(f"  release folder : {rel}")
        print(f"  public zip     : {archive}")
        print(f"  verify report  : {REPO_ROOT / 'public_release_verify_report.json'}")
        return 0
    finally:
        banner("RESTORING WORKING TREE (no git history was touched)")
        if args.keep_scrubbed:
            print("  --keep-scrubbed set: tree LEFT scrubbed (remember to restore it!).")
        else:
            backup.restore_all()
            if Path(REPO_ROOT / "data.keys").exists():
                run([py, str(REGEN), "--mode", "keyed"])
        if not ok:
            print("  (build did not complete; see messages above.)")


if __name__ == "__main__":
    raise SystemExit(main())
