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
  2. build.py --no-self-modify      -> freeze app + pkg.zip (DEFAULT: NO source
     tree and NO Tlamatini.md, so the system prompt stays ~15.7k tokens smaller
     per request; pass --self-modify to this script to bundle both instead).
  3. build_uninstaller.py            -> Uninstaller.exe.
  4. build_installer.py              -> dist/Tlamatini_Release_v<ver>/.
  5. zip -> dist/Tlamatini_Release_v<ver>_PRIVATE_KEYED_win11x64.zip
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DIST = REPO_ROOT / "dist"
REGEN = REPO_ROOT / "regen_secrets.py"
BUILD = REPO_ROOT / "build.py"
BUILD_UNINST = REPO_ROOT / "build_uninstaller.py"
BUILD_INST = REPO_ROOT / "build_installer.py"
PKG_ZIP = REPO_ROOT / "pkg.zip"            # build.py's real artifact (it deletes dist/)
# Gitignored PRIVATE contacts book. When present, the keyed build bundles it as
# contacts.json (build.py reads TLAMATINI_BUNDLE_CONTACTS). Absent -> empty book.
CONTACTS_PRIVATE = REPO_ROOT / "contacts.private.json"
# Dev-tree contacts.json (what Angela edits through the UI in source/dev mode).
# This is the PRIMARY sync source — contacts.private.json is auto-synced from it
# (and from the running frozen install, if on the same machine) before every build
# so the private release always ships the LATEST contacts, never a stale snapshot.
CONTACTS_DEV_TREE = REPO_ROOT / "Tlamatini" / "agent" / "contacts.json"
# Running frozen Tlamatini contacts.json (secondary sync source, same-machine install).
# Tried via env var TLAMATINI_INSTALL, then common install roots.
_CONTACTS_RUNNING_CANDIDATES = [
    Path(os.environ.get("TLAMATINI_INSTALL", "")) / "contacts.json",
    Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "Tlamatini" / "contacts.json",
    Path(r"C:\Tlamatini") / "contacts.json",
]
# The DEV External-MCP catalog. It is TRACKED (with `<... goes here>` placeholders)
# and `regen_secrets.py --mode keyed` — which this builder runs first — restores the
# real tokens into it. The keyed build then ships EVERY server in it PLUS the two
# defaults (memory, sequential-thinking), via build.py's TLAMATINI_BUNDLE_EXTERNAL_MCPS.
# The PUBLIC builder clears that variable and ships the two defaults only.
EXTERNAL_MCPS_DEV = REPO_ROOT / "Tlamatini" / "agent" / "external_mcps.json"


def banner(msg: str) -> None:
    print("\n" + "=" * 74, flush=True)
    print(f"== {msg}", flush=True)
    print("=" * 74, flush=True)


def assert_self_modify_payload(expect_self_modify: bool) -> None:
    """PROVE the built package matches the flag — never merely claim it.

    Tlamatini's own source tree (``TlamatiniSourceCode/``) and her self-knowledge
    file (``Tlamatini.md``) ship TOGETHER, or not at all. A build that silently
    kept ``Tlamatini.md`` would put her entire self-description back into the
    system prompt of EVERY request (~63k characters, ~15.7k tokens) — exactly
    what the default not-self-able-modify mode exists to avoid. So we open the
    artifact and LOOK, and we fail loud on a mismatch in either direction.
    """
    if not PKG_ZIP.is_file():
        print(f"  NOTE: {PKG_ZIP.name} not found — skipping self-modify payload check.")
        return
    with zipfile.ZipFile(PKG_ZIP) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
    tree = any("TlamatiniSourceCode/" in n for n in names)
    self_md = any(n.rsplit("/", 1)[-1] == "Tlamatini.md" for n in names)
    print(f"  package payload: TlamatiniSourceCode={'PRESENT' if tree else 'absent'}, "
          f"Tlamatini.md={'PRESENT' if self_md else 'absent'}")
    if expect_self_modify and not (tree and self_md):
        sys.exit("ABORT: --self-modify was requested but the package is missing "
                 "TlamatiniSourceCode/ and/or Tlamatini.md — she could not modify herself.")
    if not expect_self_modify and (tree or self_md):
        sys.exit("ABORT: this is a not-self-able-modify build, yet the package still "
                 "contains TlamatiniSourceCode/ and/or Tlamatini.md — the per-request "
                 "prompt savings would be silently lost.")


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


def _normalize_name(name: str) -> str:
    """Case- and accent-insensitive name key (matches contacts.py resolver)."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()


def _load_contacts_from_file(path: Path) -> list[dict]:
    """Load contacts from a JSON file, handling BOTH formats:
    - Object: {"_README": "...", "contacts": [...]}
    - Bare array: [{...}, {...}]
    Returns [] on any error or if the file is missing.
    """
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict) and c.get("name")]
        if isinstance(data, dict) and isinstance(data.get("contacts"), list):
            return [c for c in data["contacts"] if isinstance(c, dict) and c.get("name")]
    except Exception as exc:
        print(f"  WARNING: could not read {path} ({exc})")
    return []


def _merge_contact(existing: dict, incoming: dict) -> dict:
    """Merge two contact dicts — union aliases, keep non-empty field values."""
    merged = dict(existing)
    for key in ("name", "telegram", "whatsapp", "email", "note"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    existing_aliases = set(merged.get("aliases") or [])
    incoming_aliases = set(incoming.get("aliases") or [])
    union_aliases = sorted(existing_aliases | incoming_aliases, key=str.lower)
    if union_aliases:
        merged["aliases"] = union_aliases
    return merged


def sync_contacts_private() -> None:
    """Auto-sync contacts.private.json from the dev tree and running install.

    Ensures the gitignored contacts.private.json — the file build.py bundles as
    contacts.json into every private/keyed release — always reflects the LATEST
    contacts Angela configured, never a stale snapshot.  Sources checked in order:
      1. The dev-tree contacts.json  (Tlamatini/agent/contacts.json — what the UI
         writes in source/dev mode).
      2. The running frozen Tlamatini contacts.json  (same-machine install, probed
         via TLAMATINI_INSTALL env, %LOCALAPPDATA%, and C:/Tlamatini).
    Contacts are merged by normalized name (case/accent-insensitive); aliases are
    unioned and non-empty field values are preserved.  The _README is kept.
    """
    # Collect the current contacts.private.json as the baseline.
    private_contacts = _load_contacts_from_file(CONTACTS_PRIVATE)
    merged: dict[str, dict] = {}
    for contact in private_contacts:
        merged[_normalize_name(contact["name"])] = dict(contact)

    sources_checked: list[str] = []
    new_count = 0

    # Source 1: dev-tree contacts.json.
    if CONTACTS_DEV_TREE.is_file():
        sources_checked.append(str(CONTACTS_DEV_TREE))
        for contact in _load_contacts_from_file(CONTACTS_DEV_TREE):
            key = _normalize_name(contact["name"])
            if key not in merged:
                merged[key] = dict(contact)
                new_count += 1
                print(f"  + {contact['name']}  (from dev tree)")
            else:
                merged[key] = _merge_contact(merged[key], contact)

    # Source 2: running frozen Tlamatini contacts.json (same-machine install).
    for candidate in _CONTACTS_RUNNING_CANDIDATES:
        if candidate.is_file() and str(candidate) not in sources_checked:
            sources_checked.append(str(candidate))
            for contact in _load_contacts_from_file(candidate):
                key = _normalize_name(contact["name"])
                if key not in merged:
                    merged[key] = dict(contact)
                    new_count += 1
                    print(f"  + {contact['name']}  (from running install)")
                else:
                    merged[key] = _merge_contact(merged[key], contact)
            break  # use the first matching candidate only

    # If nothing changed, do not rewrite the file.
    current_names = {_normalize_name(c["name"]) for c in private_contacts}
    merged_names = set(merged.keys())
    if merged_names == current_names and new_count == 0:
        print(f"  contacts.private.json already up-to-date ({len(merged)} contact(s)).")
        return

    # Build the output document, preserving the _README from the existing file.
    doc: dict = {}
    if CONTACTS_PRIVATE.is_file():
        try:
            with open(CONTACTS_PRIVATE, "r", encoding="utf-8-sig") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict) and raw.get("_README"):
                doc["_README"] = raw["_README"]
        except Exception:
            pass
    if "_README" not in doc:
        doc["_README"] = (
            "PRIVATE contacts book. GITIGNORED. Shipped ONLY by "
            "build_complete_private_release.py. Auto-synced from dev tree and "
            "running install before every private build."
        )
    doc["contacts"] = list(merged.values())

    tmp = str(CONTACTS_PRIVATE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, str(CONTACTS_PRIVATE))
    print(f"  contacts.private.json synced: {len(merged)} contact(s) "
          f"({new_count} new from {len(sources_checked)} source(s)).")


def _utf8_env() -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Silence pip's "A new release of pip is available" nag in EVERY child of
    # this wrapper (build.py / build_uninstaller.py / build_installer.py) and in
    # every pip THEY spawn. It is pure noise, and upgrading pip does not fix it:
    # the build Python is normally the SYSTEM one under Program Files, whose pip
    # sits in a READ-ONLY prefix (upgrading the carried <repo>/python's pip
    # instead changes nothing there). Full rationale in build.py.
    # Pinned by Tlamatini/agent/test_build_pip_quiet.py.
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    # PRIVATE / keyed build: ship the REAL contacts book when the gitignored
    # contacts.private.json is present (build.py reads TLAMATINI_BUNDLE_CONTACTS
    # and bundles it as contacts.json). Absent -> build.py ships the empty book.
    if CONTACTS_PRIVATE.is_file():
        env["TLAMATINI_BUNDLE_CONTACTS"] = str(CONTACTS_PRIVATE)
    else:
        env.pop("TLAMATINI_BUNDLE_CONTACTS", None)
    # PRIVATE / keyed build: ship the FULL dev External-MCP catalog (every server
    # this machine has) PLUS the two defaults, which build.py merges in. This runs
    # AFTER `regen_secrets.py --mode keyed`, so the catalog on disk already holds
    # real tokens rather than `<... goes here>` placeholders.
    if EXTERNAL_MCPS_DEV.is_file():
        env["TLAMATINI_BUNDLE_EXTERNAL_MCPS"] = str(EXTERNAL_MCPS_DEV)
    else:
        env.pop("TLAMATINI_BUNDLE_EXTERNAL_MCPS", None)
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
    # DEFAULT IS OFF (2026-08-08, Angela's directive): a build_complete_* run
    # behaves as if --no-self-modify were set, so the release ships NEITHER the
    # TlamatiniSourceCode tree NOR Tlamatini.md (her self-knowledge) — the two
    # travel together. Opt IN with --self-modify. --no-self-modify is kept as an
    # accepted no-op so older commands and muscle memory still work.
    ap.add_argument("--self-modify", action="store_true",
                    help="bundle the TlamatiniSourceCode self-modify tree AND "
                         "Tlamatini.md (default: NEITHER is bundled).")
    ap.add_argument("--no-self-modify", action="store_true",
                    help="explicit form of the DEFAULT (no source tree, no "
                         "self-knowledge); overrides --self-modify if both given.")
    args = ap.parse_args(argv)

    py = args.python
    assert_system_python(py)
    self_modify = args.self_modify and not args.no_self_modify

    banner("PRIVATE RELEASE BUILD  (KEYED -- contains your real data; DO NOT publish)")
    print(f"repo        : {REPO_ROOT}")
    print(f"python      : {py}")
    print(f"keys file   : {args.keys_file}")
    print(f"self-modify : {'YES — source tree + Tlamatini.md bundled' if self_modify else 'no (DEFAULT) — no source tree, no self-knowledge, smaller prompt'}")
    print(f"contacts    : {'COMPLETE (contacts.private.json)' if CONTACTS_PRIVATE.is_file() else 'EMPTY (contacts.private.json not found)'}")

    banner("STEP 0/5  sync contacts.private.json from live sources")
    sync_contacts_private()
    # Re-report the contacts status AFTER the sync so the count is accurate.
    _synced_contacts = _load_contacts_from_file(CONTACTS_PRIVATE)
    print(f"contacts    : {len(_synced_contacts)} contact(s) ready for bundling")

    banner("STEP 1/5  regen_secrets.py --mode keyed")
    if run([py, str(REGEN), "--mode", "keyed", "--keys-file", args.keys_file]) != 0:
        sys.exit("regen_secrets keyed failed.")

    banner("STEP 2/5  build.py")
    build_cmd = [py, str(BUILD)]
    # Pass the decision EXPLICITLY either way, so the intent is recorded in the
    # build log and a stray "--self-modify" in the ambient argv cannot flip it.
    build_cmd.append("--self-modify" if self_modify else "--no-self-modify")
    if args.version:
        build_cmd.append(args.version)
    if run(build_cmd) != 0:
        sys.exit("build.py failed.")
    assert_self_modify_payload(self_modify)

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
