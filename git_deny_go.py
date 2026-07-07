# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""git_deny_go.py — autonomously guarantee the Go toolchain NEVER appears in git.

Discoverer self-provisions a private Go toolchain (the ~150 MB Go compiler + the module
cache + the ProjectDiscovery tool binaries) on first use. It now installs OUTSIDE the
repo (``%LOCALAPPDATA%/Tlamatini/Go``), but this script is the belt-and-suspenders that
makes git DENY Go's existence no matter what — so it can NEVER reappear in Source Control:

  1. Ensures every Go-toolchain pattern is present in ``.gitignore`` (idempotent).
  2. Untracks any Go-toolchain path that somehow got tracked (``git rm --cached``).
  3. Installs a ``pre-commit`` hook that ABORTS a commit if any Go-toolchain path is
     staged (even via ``git add -f``) — without clobbering an existing hook.
  4. Verifies ``git`` can no longer see any Go path and prints a clear report.

Idempotent and safe to run repeatedly:   python git_deny_go.py
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
GITIGNORE = REPO_ROOT / ".gitignore"

# Every path shape the self-provisioned Go toolchain can take — denied anywhere.
GO_PATTERNS = (
    "/Go/",
    "Tlamatini/Go/",
    "**/Go/",
    "**/bin-tools/",
    "**/go-build/",
    "**/pkg/mod/",
    "go[0-9]*.windows-*.zip",
    "go[0-9]*.*.tar.gz",
)

_BLOCK_HEADER = "# >>> GO-DENY (auto-added by git_deny_go.py) >>>"
_BLOCK_FOOTER = "# <<< GO-DENY <<<"

_HOOK_MARKER = "# GO-DENY pre-commit (managed by git_deny_go.py)"
_HOOK_BODY = r"""# GO-DENY pre-commit (managed by git_deny_go.py)
# Block the Go toolchain from EVER being committed (even a forced `git add -f`).
_goblocked=$(git diff --cached --name-only | grep -Ei '(^|/)Go/|(^|/)bin-tools/|(^|/)go-build/|pkg/mod/|^go[0-9].*\.(zip|tar\.gz)$')
if [ -n "$_goblocked" ]; then
  echo "=============================================================="
  echo " COMMIT BLOCKED: Go toolchain files must NEVER be committed."
  echo " They live in %LOCALAPPDATA%/Tlamatini/Go (outside the repo)."
  echo "--------------------------------------------------------------"
  echo "$_goblocked"
  echo "--------------------------------------------------------------"
  echo " Unstage them, then run:  python git_deny_go.py"
  echo "=============================================================="
  exit 1
fi
"""


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, check=False,
    )


def ensure_gitignore() -> bool:
    """Make sure every GO_PATTERN is in .gitignore. Returns True if it added any."""
    text = GITIGNORE.read_text(encoding="utf-8") if GITIGNORE.exists() else ""
    lines = set(text.splitlines())
    missing = [p for p in GO_PATTERNS if p not in lines]
    if not missing:
        return False
    block = "\n".join([_BLOCK_HEADER, *missing, _BLOCK_FOOTER, ""])
    if text and not text.endswith("\n"):
        text += "\n"
    GITIGNORE.write_text(text + "\n" + block, encoding="utf-8")
    return True


def untrack_go() -> list[str]:
    """Untrack any Go-toolchain path that is currently tracked (no-op if none)."""
    removed: list[str] = []
    for spec in ("Go", "Tlamatini/Go"):
        r = _git("rm", "-r", "--cached", "--ignore-unmatch", spec)
        removed += [ln for ln in r.stdout.splitlines() if ln.startswith("rm '")]
    return removed


def install_precommit_hook() -> str:
    hooks_dir = REPO_ROOT / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return "skipped (no .git/hooks — not a git working copy?)"
    hook = hooks_dir / "pre-commit"
    if hook.exists():
        existing = hook.read_text(encoding="utf-8", errors="replace")
        if _HOOK_MARKER in existing:
            return "already installed"
        # Preserve the existing hook: keep its shebang first, inject our guard next.
        if existing.startswith("#!"):
            first, _, rest = existing.partition("\n")
            merged = first + "\n\n" + _HOOK_BODY + "\n" + rest
        else:
            merged = "#!/bin/sh\n\n" + _HOOK_BODY + "\n" + existing
        hook.write_text(merged, encoding="utf-8", newline="\n")
        _make_executable(hook)
        return "merged into existing pre-commit hook"
    hook.write_text("#!/bin/sh\n\n" + _HOOK_BODY + "\nexit 0\n", encoding="utf-8", newline="\n")
    _make_executable(hook)
    return "installed"


def _make_executable(path: Path) -> None:
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass


def verify() -> bool:
    """Assert git can no longer see any Go-toolchain path. Returns True if clean."""
    # Probe a path INSIDE Go/ so the directory-only rule (`/Go/`) matches even when the
    # Go dir isn't on disk right now (git can't classify a bare, missing path as a dir).
    ci = _git("check-ignore", "-v", "Go/_probe")
    ignored = bool(ci.stdout.strip())
    st = _git("status", "--porcelain", "--", "Go", "Tlamatini/Go")
    clean = not st.stdout.strip()
    print(f"  Go/* ignored by rule   : {ci.stdout.strip() or '!!! NOTHING — NOT IGNORED'}")
    print(f"  Go paths in git status : {st.stdout.strip() or '(none)'}")
    return ignored and clean


def main() -> int:
    print("== git_deny_go.py — making git deny the Go toolchain's existence ==")
    added = ensure_gitignore()
    print(f"[1/4] .gitignore patterns : {'added missing' if added else 'already complete'}")
    removed = untrack_go()
    print(f"[2/4] untracked Go paths  : {len(removed)} removed")
    for r in removed[:20]:
        print("        " + r)
    print(f"[3/4] pre-commit hook     : {install_precommit_hook()}")
    ok = verify()
    print(f"[4/4] verify              : {'GO IS INVISIBLE TO GIT' if ok else 'STILL VISIBLE — CHECK ABOVE'}")
    print("== done ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
