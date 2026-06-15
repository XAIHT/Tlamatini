#!/usr/bin/env python3
"""
sweep_self_update.py -- deterministic auditor for Tlamatini's self-update pipeline.

Backs the `tlamatini-self-update-inclusion` skill. Parses the three files that own
the pipeline and checks the four invariants so no asset is silently dropped from a
release or wrongly wiped/kept by the update swap:

  build.py                       -- assembles the release (the 6 carrier mechanisms)
  Tlamatini/agent/self_update.py -- in-app updater (docstring preserve list)
  apply_update.ps1               -- the executed file-swapper ($Preserve array)

Checks (each prints [PASS] or [FINDING]):
  1. PRESERVE PARITY    apply_update.ps1 $Preserve  ==  self_update.py docstring list
  2. PRESERVE CORRECT   $Preserve  ==  build.py empty_dirs(top-level) + {config.json}
  3. APP-DIR REPLACED   no known app-code dir is in $Preserve
  4. ROOT .ps1 CENSUS   every repo-root *.ps1 is in build.py support_files
  5. UPDATER SHIPPED    apply_update.ps1 is in build.py support_files
  6. SWAP SANITY        apply_update.ps1 validates Tlamatini.exe + does the agents swap
  7. DB DELIVERY        report migrations since last tag + flag preserve/migrate coherence

Pure stdlib, fail-soft (a parse miss is reported, never crashed). Exit code is the
number of findings (0 == clean), so it can gate a release.

Usage:
    python .claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py
    python .../sweep_self_update.py --repo-root /path/to/Tlamatini
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Known APP-CODE top-level entries that live at the install root and MUST be
# replaced on update (never preserved). 'agents' is special -- it's replaced via
# the agents->agents_backup swap, so it must ALSO be absent from $Preserve.
APP_CODE_TOPLEVEL = {
    "agents", "python", "jre", "git", "ms-playwright", "staticfiles",
    "images", "skills_pkg", "Tlamatini.exe", "cat_art.py",
}

# Findings accumulator.
_FINDINGS: list[str] = []
_NOTES: list[str] = []


def finding(msg: str) -> None:
    _FINDINGS.append(msg)
    print(f"  [FINDING] {msg}")


def ok(msg: str) -> None:
    print(f"  [PASS]    {msg}")


def note(msg: str) -> None:
    _NOTES.append(msg)
    print(f"  [note]    {msg}")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        finding(f"cannot read {path}: {exc}")
        return None


# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_ps1_preserve(text: str) -> set[str] | None:
    """Extract the $Preserve = @( '...', '...' ) array from apply_update.ps1."""
    m = re.search(r"\$Preserve\s*=\s*@\((.*?)\)", text, re.DOTALL)
    if not m:
        return None
    # Strip PS1 `#` comments first: a comment such as "delete the user's
    # uninstaller" contains an apostrophe that otherwise breaks the '...'
    # single-quote token pairing and yields a bogus / missing entry.
    body = re.sub(r"#[^\n]*", "", m.group(1))
    return set(re.findall(r"'([^']+)'", body))


def parse_self_update_preserve(text: str) -> set[str] | None:
    """Extract the docstring 'Preserved across the swap' token list.

    The block looks like (indented, prose, two lines)::

        Preserved across the swap (everything else is replaced)::

            config.json  DB  application  applications  content_generated
            Temp  context_files  doc_generated  documentation  Templates
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "Preserved across the swap" in ln:
            start = i + 1
            break
    if start is None:
        return None
    tokens: set[str] = set()
    seen_any = False
    for ln in lines[start:]:
        s = ln.strip()
        if not s:
            if seen_any:
                break          # blank line ends the block once tokens started
            continue
        if "`" in s or "::" in s or s.startswith("#"):
            if seen_any:
                break
            continue
        # token-only line: words / dots / spaces
        if re.fullmatch(r"[\w.\- ]+", s):
            tokens.update(t for t in s.split() if t)
            seen_any = True
        elif seen_any:
            break
    return tokens or None


def parse_build_list(text: str, name: str) -> set[str] | None:
    """Extract a python list/tuple literal `name = [ ... ]` / `( ... )` of quoted strings.

    Bracket-depth aware so it does NOT stop early on a `)`/`]` that appears inside a
    `# comment` or a string literal (build.py's support_files has a comment that reads
    `(About ... updates)` -- a naive non-greedy regex truncates the list right there).
    """
    m = re.search(rf"{re.escape(name)}\s*=\s*([\[(])", text)
    if not m:
        return None
    i = m.end()
    depth = 1
    buf: list[str] = []
    n = len(text)
    while i < n and depth > 0:
        ch = text[i]
        if ch == "#":                                   # skip to end of line comment
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch in ("'", '"'):                            # skip a quoted string verbatim
            quote = ch
            buf.append(ch)
            i += 1
            while i < n and text[i] != quote:
                buf.append(text[i])
                i += 1
            if i < n:
                buf.append(text[i])
                i += 1
            continue
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
            if depth == 0:
                break
        buf.append(ch)
        i += 1
    return set(re.findall(r"""['"]([^'"]+)['"]""", "".join(buf)))


def top_level(names: set[str]) -> set[str]:
    """Reduce 'DB/ToLoad' -> 'DB'; strip 'Tlamatini/cat_art.py' -> 'cat_art.py' is NOT done here."""
    return {n.split("/")[0].split("\\")[0] for n in names}


# ── Main sweep ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Tlamatini's self-update inclusion pipeline.")
    parser.add_argument("--repo-root", default=None,
                        help="Repo root (default: auto-detect from this script's location).")
    args = parser.parse_args(argv)

    try:                                  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # Resolve repo root: this script lives at <root>/.claude/skills/<skill>/scripts/.
    if args.repo_root:
        root = Path(args.repo_root).resolve()
    else:
        here = Path(__file__).resolve()
        root = here.parents[4] if len(here.parents) >= 5 else Path.cwd()

    build_py = root / "build.py"
    self_update = root / "Tlamatini" / "agent" / "self_update.py"
    apply_ps1 = root / "apply_update.ps1"

    print(f"Repo root: {root}\n")
    for p in (build_py, self_update, apply_ps1):
        if not p.is_file():
            finding(f"required pipeline file missing: {p.relative_to(root) if p.is_relative_to(root) else p}")
    if _FINDINGS:
        print("\nAborting: pipeline files missing.")
        return len(_FINDINGS)

    build_txt = _read(build_py) or ""
    su_txt = _read(self_update) or ""
    ps1_txt = _read(apply_ps1) or ""

    ps1_preserve = parse_ps1_preserve(ps1_txt)
    su_preserve = parse_self_update_preserve(su_txt)
    empty_dirs = parse_build_list(build_txt, "empty_dirs")
    support_files = parse_build_list(build_txt, "support_files")

    # ── Check 1: preserve parity ─────────────────────────────────────────────
    print("\n[1] PRESERVE PARITY -- apply_update.ps1 $Preserve == self_update.py docstring")
    if ps1_preserve is None:
        finding("could not parse $Preserve from apply_update.ps1")
    elif su_preserve is None:
        finding("could not parse the 'Preserved across the swap' list from self_update.py")
    else:
        only_ps1 = ps1_preserve - su_preserve
        only_su = su_preserve - ps1_preserve
        if not only_ps1 and not only_su:
            ok(f"both lists identical ({len(ps1_preserve)} entries): {sorted(ps1_preserve)}")
        else:
            if only_ps1:
                finding(f"in apply_update.ps1 but NOT documented in self_update.py: {sorted(only_ps1)}")
            if only_su:
                finding(f"documented in self_update.py but NOT in apply_update.ps1 $Preserve: {sorted(only_su)}")

    # ── Check 2: preserve correctness vs build.py empty_dirs ──────────────────
    print("\n[2] PRESERVE CORRECTNESS -- $Preserve == empty_dirs(top-level) + {config.json}")
    if ps1_preserve is None or empty_dirs is None:
        finding("cannot compare (failed to parse $Preserve or build.py empty_dirs)")
    else:
        expected = top_level(empty_dirs) | {"config.json"}
        wiped = expected - ps1_preserve          # state dir that will be DELETED on update
        extra = ps1_preserve - expected          # preserved but not a known state dir
        if not wiped:
            ok(f"every runtime-state dir is preserved ({sorted(expected)})")
        for w in sorted(wiped):
            finding(f"runtime-state dir '{w}' is in build.py empty_dirs but NOT preserved "
                    f"-> it will be WIPED on every update (silent user-data loss). "
                    f"Add it to $Preserve AND the self_update.py docstring.")
        # 'extra' is only suspicious if it's an app-code dir (handled in check 3);
        # config.json/DB legitimately appear here, so just note non-app extras.
        benign = {"config.json", "DB"}
        for e in sorted(extra - benign - APP_CODE_TOPLEVEL):
            note(f"$Preserve has '{e}' which is not in empty_dirs -- confirm it is genuine "
                 f"user state (intended) and not stale app code.")

    # ── Check 3: app-code dirs must NOT be preserved ─────────────────────────
    print("\n[3] APP-CODE REPLACED -- no app-code top-level entry is preserved")
    if ps1_preserve is None:
        finding("cannot check (failed to parse $Preserve)")
    else:
        bad = ps1_preserve & APP_CODE_TOPLEVEL
        if not bad:
            ok("no app-code directory is preserved (all app code is replaced on update)")
        for b in sorted(bad):
            finding(f"app-code entry '{b}' is in $Preserve -> users would be stuck on STALE "
                    f"'{b}' forever. Remove it ('agents' is replaced via the agents_backup swap).")

    # ── Check 4: root .ps1 census ────────────────────────────────────────────
    print("\n[4] ROOT .ps1 CENSUS -- every repo-root *.ps1 is shipped by build.py support_files")
    root_ps1 = sorted(p.name for p in root.glob("*.ps1"))
    if support_files is None:
        finding("could not parse support_files from build.py")
    elif not root_ps1:
        note("no *.ps1 at repo root")
    else:
        shipped = {Path(s).name for s in support_files}
        for name in root_ps1:
            if name in shipped:
                ok(f"{name} is in support_files")
            else:
                finding(f"repo-root '{name}' is NOT in build.py support_files "
                        f"-> it will NOT ship next to the exe. Add it.")

    # ── Check 5: the updater itself ships ────────────────────────────────────
    print("\n[5] UPDATER SHIPPED -- apply_update.ps1 is carried into the release")
    if support_files and any(Path(s).name == "apply_update.ps1" for s in support_files):
        ok("apply_update.ps1 is in build.py support_files (self-hosting updater)")
    else:
        finding("apply_update.ps1 is NOT in build.py support_files -> a self-updated install "
                "would lose its updater and could never update again.")

    # ── Check 6: swap sanity ─────────────────────────────────────────────────
    print("\n[6] SWAP SANITY -- apply_update.ps1 validates the exe and swaps agents")
    if re.search(r"Tlamatini\.exe", ps1_txt) and re.search(r"Test-Path", ps1_txt):
        ok("apply_update.ps1 validates a staged Tlamatini.exe before touching the install")
    else:
        finding("apply_update.ps1 does not appear to validate a staged Tlamatini.exe first")
    if re.search(r"agents_backup", ps1_txt):
        ok("apply_update.ps1 performs the agents -> agents_backup swap")
    else:
        finding("apply_update.ps1 has no agents_backup swap -> new agents may not replace old ones")

    # ── Check 7: DB delivery coherence ───────────────────────────────────────
    print("\n[7] DB DELIVERY -- migrations reach users; preserve/migrate coherence")
    mig_dir = root / "Tlamatini" / "agent" / "migrations"
    db_preserved = bool(ps1_preserve and ("db.sqlite3" in ps1_preserve))
    startup_migrate = _has_startup_migrate(root)
    new_migs = _migrations_since_last_tag(root, mig_dir)
    if new_migs is None:
        note("could not compute migrations since last tag (no git / no tag)")
    elif new_migs:
        note(f"{len(new_migs)} migration(s) added since last release: {new_migs} "
             f"-- their seeded rows reach users only via the shipped db.sqlite3.")
    else:
        note("no new migrations since last release tag")
    db_capture_migrate = _db_capture_and_migrate(root, ps1_txt)
    if db_preserved and not startup_migrate:
        finding("db.sqlite3 IS preserved but no first-run 'migrate' was found -> new migrations "
                "will NEVER apply to existing users. Add a startup migrate or stop preserving the DB.")
    elif db_preserved:
        ok("db.sqlite3 preserved AND a first-run migrate exists -- new migrations apply, data kept.")
    elif db_capture_migrate:
        ok("db.sqlite3 is captured into DB/ToLoad on update and migrated on next launch -- the "
           "user's chat history + toggles are kept and new migrations are applied.")
    else:
        note("db.sqlite3 is REPLACED on update (current design): new rows arrive, but the user's "
             "chat history + custom toggles reset each update. Keep the self_update.py docstring honest.")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if _FINDINGS:
        print(f"RESULT: {len(_FINDINGS)} FINDING(S) -- fix before shipping a release:")
        for f in _FINDINGS:
            print(f"  - {f}")
    else:
        print("RESULT: CLEAN -- self-update inclusion invariants hold.")
    if _NOTES:
        print(f"\n({len(_NOTES)} advisory note(s) above -- review, not blocking.)")
    print("=" * 70)
    return len(_FINDINGS)


def _has_startup_migrate(root: Path) -> bool:
    """True if anything on the startup path calls migrate (apps.ready / manage / DB swap)."""
    candidates = [
        root / "Tlamatini" / "agent" / "apps.py",
        root / "Tlamatini" / "manage.py",
        root / "Tlamatini" / "agent" / "management" / "commands" / "startserver.py",
    ]
    for c in candidates:
        try:
            t = c.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"call_command\(\s*['\"]migrate['\"]", t) or "_apply_pending_db_swap" in t:
            # _apply_pending_db_swap is the DB/ToLoad mechanism -- a valid delivery path.
            if "migrate" in t or "_apply_pending_db_swap" in t:
                return True
    return False


def _db_capture_and_migrate(root: Path, ps1_txt: str) -> bool:
    """True if the updater captures the user's DB into DB/ToLoad + flags a
    post-update migrate, AND manage.py consumes that flag to run migrate.

    This is the data-preserving DB delivery path: rather than replacing the
    user's db.sqlite3 (which would lose their chat history + toggles), the
    updater stages it through DB/ToLoad and the next launch migrates it to the
    current schema -- so new migrations apply while user data is kept.
    """
    ps1_ok = ("ToLoad" in ps1_txt) and ("post_update_migrate" in ps1_txt)
    manage = root / "Tlamatini" / "manage.py"
    try:
        mtxt = manage.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    manage_ok = ("post_update_migrate" in mtxt) and ("migrate" in mtxt)
    return ps1_ok and manage_ok


def _migrations_since_last_tag(root: Path, mig_dir: Path) -> list[str] | None:
    try:
        tag = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if tag.returncode != 0 or not tag.stdout.strip():
            return None
        diff = subprocess.run(
            ["git", "diff", "--name-only", f"{tag.stdout.strip()}..HEAD",
             "--", "Tlamatini/agent/migrations"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if diff.returncode != 0:
            return None
        return sorted(
            Path(p).name for p in diff.stdout.splitlines()
            if p.endswith(".py") and "__init__" not in p
        )
    except (OSError, subprocess.SubprocessError):
        return None


if __name__ == "__main__":
    sys.exit(main())
