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
     .private_targets.json, else the tracked EMPTY .private_targets.template.json).
     No targets + private-data markers in the tree  -> REFUSE (see below).
     No targets + a clean tree                      -> NO-TARGETS MODE.
  1. BACK UP touched files (restored in `finally`).
  2. regen_secrets.py --mode push-able  -> config secrets become placeholders.
     (build.py repeats this itself and PROVES it, so a bare build is safe too.)
  3. sanitize external_mcps.json (ship an empty catalog) + SCRUB the working tree.
  4. build.py --no-self-modify           -> freeze app + pkg.zip (build.py deletes dist/).
     DEFAULT: NO source tree and NO Tlamatini.md, keeping ~15.7k tokens out of
     the system prompt per request; pass --self-modify here to bundle both.
  5. VERIFY: extract pkg.zip and audit it.
       with targets    -> check_private_data.py; any of YOUR data present -> ABORT.
       NO-TARGETS MODE -> verify_shipped_config_surface(); any live secret /
                          e-mail / phone in the config Tlamatini ships -> ABORT.
  6. build_uninstaller.py + build_installer.py -> dist/Tlamatini_Release_v<ver>/.
  7. zip -> dist/..._PUBLIC_CLEAN_win11x64.zip
  8. ALWAYS restore the working tree (finally).

.private_targets.json is OPTIONAL (Angela, 2026-08-30)
------------------------------------------------------
It is gitignored, so it exists only on a machine where someone declared private
data. A fresh clone, a public contributor, and Tlamatini rebuilding herself from
TlamatiniSourceCode/ all lack it -- and used to hit a hard REFUSAL that no
documentation could resolve, because the schema lived only in an error message.
Now:

  * .private_targets.template.json is TRACKED, always present, and always EMPTY.
    It documents the schema and resolves to ZERO targets.
  * Zero targets is allowed ONLY when the tree shows no private-data markers
    (data.keys, contacts.private.json, a non-empty contacts.json). With markers
    present the builder REFUSES, because "no targets" then means the file went
    MISSING and every scrub would be a silent no-op -- an unscrubbed release.
    --no-private-data is the explicit override for that case.
  * NOTHING at runtime reads this file. It is build/audit-time only, so a missing
    .private_targets.json can never stop an installed Tlamatini from starting.
    Pinned by Tlamatini/agent/test_public_release_targets_optional.py.
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
import unicodedata
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
# TRACKED, always-present, ALWAYS-EMPTY schema template. It is the LAST resort of
# targets discovery, and it deliberately yields ZERO targets: finding it means
# "nobody declared any private data on this machine", which is the correct and
# expected state for a fresh clone, a public contributor, and Tlamatini rebuilding
# herself from TlamatiniSourceCode/ (copy_source_assets.py drops the real
# .private_targets.json but ships this template). Its "_README" key is a COMMENT
# key -- check_private_data.load_targets skips "_"-prefixed keys, so the prose
# inside it can never become a scrub target.
TEMPLATE_TARGETS_FILE = REPO_ROOT / ".private_targets.template.json"

PLACEHOLDER = "<REDACTED>"

# Angela's NAME and her GitHub handle are NEVER scrubbed -- in the public OR the
# private build. Her authorship stays everywhere, always, by her explicit
# instruction: her display name "Angela Lopez Mendoza" in ANY case / accent /
# spacing variant (Angela, Ángela, Lopez, López, Mendoza, the full name) AND her
# GitHub handle @angelahack1 are kept. Only her OTHER private data is masked --
# emails, her PHONE, the "Ana*" legal-name variants, and secrets. Her phone in
# particular must NEVER appear in the repo: it lives ONLY in data.keys (which is
# gitignored and in SCRUB_SKIP_FILES, so it is never scrubbed OR published).
# Kept values are dropped from the scrub set before any redaction runs.
KEEP_NAME_TOKENS = {"angela", "lopez", "mendoza"}   # accent-stripped, lowercased
KEEP_HANDLES = {"angelahack1"}                      # with or without a leading @


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value or "")
                   if not unicodedata.combining(c))


def _is_kept_name(value: str) -> bool:
    """True for Angela's name (ANY accent / case / spacing variant) and her GitHub
    handle -- these are kept in EVERY build. Her emails, phone and the "Ana*" legal
    variants are NOT kept (they carry an @domain, digits, or non-name tokens)."""
    norm = _strip_accents(value).strip().lower()
    if not norm:
        return False
    if norm.lstrip("@") in KEEP_HANDLES:
        return True
    # Kept only when EVERY token is one of her name tokens, so "Angela",
    # "Angela Lopez Mendoza" and "Ángela López Mendoza" are all kept, but
    # "<REDACTED>" or "<REDACTED>" (a token that isn't a bare name) are not.
    tokens = [t for t in re.split(r"[\s.]+", norm) if t]
    return bool(tokens) and all(t in KEEP_NAME_TOKENS for t in tokens)

REGEN_TOUCHED = [
    REPO_ROOT / "Tlamatini" / "agent" / "config.json",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "telegrammer" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "whatsapper" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "teletlamatini" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "emailer" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "recmailer" / "config.yaml",
    # Zavuerer + Discoverer joined regen_secrets.py's rule set later and were
    # never mirrored here, so a public build rewrote them WITHOUT a byte-for-byte
    # backup. The `finally:` re-key papered over it only because data.keys happened
    # to exist; on a machine without the vault those two YAMLs stayed redacted.
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "zavuerer" / "config.yaml",
    REPO_ROOT / "Tlamatini" / "agent" / "agents" / "discoverer" / "config.yaml",
]

SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist",
             "build", ".mypy_cache", ".ruff_cache", ".pytest_cache",
             "staticfiles", "Temp", "python", "ms-playwright", "jre", "git",
             # Gitignored local runtimes / scratch / snapshots — never published,
             # so never scrubbed. The self-provisioned Go toolchain in particular
             # holds READ-ONLY module-cache files (crash write_text with
             # PermissionError), and it plus the pool scratch is huge. Mirrors the
             # SKIP_DIRS in check_private_data.py.
             "Go", "go-build", "Templates", "TlamatiniSourceCode",
             "pools", "mcp_agent_runs",
             # Blue-hat toolkit runtime EVIDENCE (gitignored): alerts.log,
             # monitor.log and the visible asset-test artifacts. Never published
             # (build.py ignores it), so a release build must never rewrite it.
             # Mirrors the SKIP_DIRS in check_private_data.py.
             "security_logs"}
TEXT_EXT = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".env",
            ".cfg", ".ini", ".toml", ".html", ".css", ".csv", ".pmt", ".keys"}
# NEVER scrub the sources of truth: the keys vault and the targets file. Scrubbing
# .private_targets.json turns your real values into "<REDACTED>" inside it, which
# then makes the verifier hunt for the literal text "<REDACTED>" and "find" it in
# every scrubbed file (the 737-false-positive bug). data.keys must stay intact too.
SCRUB_SKIP_FILES = {"data.keys", ".private_targets.json", "private_targets.json",
                    ".private_targets.template.json", "contacts.private.json"}

SECRET_KEY_RE = re.compile(
    r'(?i)("(?:api[_-]?key|api[_-]?secret|token|access[_-]?token|auth[_-]?token|'
    r'password|passwd|secret|client[_-]?secret|session[_-]?string|bearer)"\s*:\s*")'
    r'([^"]+)(")'
)


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
        f'  & "C:/Program Files/Python312/python.exe" .\\build_complete_public_release.py'
    )


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
    # PUBLIC build ALWAYS ships an EMPTY contacts.json -- never a real book, even
    # if the ambient shell exported TLAMATINI_BUNDLE_CONTACTS. build.py ships the
    # empty placeholder whenever this is unset.
    env.pop("TLAMATINI_BUNDLE_CONTACTS", None)
    # PUBLIC build ALWAYS ships ONLY the External MCP servers Tlamatini herself
    # implements (memory, sequential-thinking) -- never the maintainer's catalog,
    # even if the ambient shell exported TLAMATINI_BUNDLE_EXTERNAL_MCPS. build.py
    # generates that two-server catalog from external_mcp_defaults whenever this
    # is unset, and hard-ABORTS the build if a live secret ever reaches it.
    env.pop("TLAMATINI_BUNDLE_EXTERNAL_MCPS", None)
    # PUBLIC build is NEVER keyed. build.py forces push-able secrets and proves it;
    # clearing this here means an ambient TLAMATINI_KEYED_BUILD=1 left over from a
    # private build in the same shell cannot silently disable that guarantee.
    env.pop("TLAMATINI_KEYED_BUILD", None)
    return env


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd), env=_utf8_env()).returncode


def default_targets_file() -> Path | None:
    """The real, gitignored targets file -- or the tracked EMPTY template.

    Returning the template is not a fallback that hides a problem: it is how a
    tree with nothing to declare says so explicitly, and it keeps the schema
    discoverable on every machine. It yields zero targets, which hands the
    decision to ``decide_targets_mode`` below.
    """
    for cand in DEFAULT_TARGETS_FILES:
        if cand.is_file():
            return cand
    if TEMPLATE_TARGETS_FILE.is_file():
        return TEMPLATE_TARGETS_FILE
    return None


def private_data_risk_markers() -> list[str]:
    """Evidence that THIS working tree holds maintainer private data.

    Why this exists: "no targets" has two completely different causes, and only
    one of them is safe.

      SAFE     a clean clone / a public contributor / Tlamatini rebuilding
               herself from the snapshot. There is genuinely no maintainer PII
               in the tree, so there is nothing to scrub and the build must
               proceed rather than dead-end on a file nobody was given.

      UNSAFE   the maintainer's own machine where .private_targets.json was
               deleted, renamed, or lost in a reinstall. Proceeding would ship
               an UNSCRUBBED public release -- SILENTLY, because an empty target
               set makes every scrub a no-op and leaves the verifier nothing to
               report. Silence is exactly the failure mode to design against.

    Nothing here reads a private VALUE; it only asks whether the private-data
    CONTAINERS exist. Each marker is a gitignored artefact that exists only on a
    machine that actually has real values.
    """
    markers: list[str] = []

    vault = REPO_ROOT / "data.keys"
    if vault.is_file():
        markers.append(f"{vault.name} exists (real secrets vault -> keyed maintainer tree)")

    priv_contacts = REPO_ROOT / "contacts.private.json"
    if priv_contacts.is_file():
        markers.append(f"{priv_contacts.name} exists (real phone numbers / handles)")

    dev_contacts = REPO_ROOT / "Tlamatini" / "agent" / "contacts.json"
    if dev_contacts.is_file():
        try:
            import json as _json
            doc = _json.loads(dev_contacts.read_text(encoding="utf-8-sig"))
            entries = doc.get("contacts") if isinstance(doc, dict) else doc
            if isinstance(entries, list) and entries:
                markers.append(
                    f"Tlamatini/agent/contacts.json holds {len(entries)} contact(s)")
        except Exception:
            # Unreadable / not JSON -> we cannot PROVE it is empty. FAIL TOWARD
            # SAFETY: treat an unparseable contacts book as if it held real people.
            markers.append("Tlamatini/agent/contacts.json is unreadable (assumed non-empty)")

    return markers


def decide_targets_mode(values: list[str], args) -> bool:
    """Run WITH targets, WITHOUT them, or refuse. Returns True for NO-TARGETS MODE.

    Never returns "maybe": either the build continues on a decision printed in
    full, or the process exits naming the exact evidence and the exact fix.
    """
    if values:
        return False

    markers = private_data_risk_markers()

    if markers and not args.no_private_data:
        listed = "\n".join(f"      - {m}" for m in markers)
        sys.exit(
            "\nREFUSING: no leak targets, but this tree looks like it HOLDS private data.\n"
            f"{listed}\n\n"
            "    An empty target set makes every scrub a silent no-op, so continuing\n"
            "    would publish an UNSCRUBBED release. Do ONE of these:\n\n"
            f"      1. Restore your targets file:  {DEFAULT_TARGETS_FILES[0].name}\n"
            f"         Start from the tracked template: {TEMPLATE_TARGETS_FILE.name}\n"
            '         (schema: {"names": [], "phones": [], "handles": [], "emails": []})\n'
            "      2. Pass them inline:            --targets-file <path> / --target <value>\n"
            "      3. Or export env               CHECK_PRIVATE_DATA_TARGETS\n"
            "      4. If you are CERTAIN this tree carries none of your private data,\n"
            "         say so explicitly with --no-private-data.\n\n"
            "    (Private data is NEVER hardcoded in this repository.)"
        )

    banner("NO-TARGETS MODE -- no private data declared for this tree")
    if markers:
        print("  --no-private-data given; proceeding DESPITE these markers:")
        for m in markers:
            print(f"      - {m}")
    else:
        print("  No private-data markers found (no data.keys, no private contacts book).")
        print("  This is the expected state for a fresh clone, for a public contributor,")
        print("  and for Tlamatini rebuilding herself from TlamatiniSourceCode/.")
    print("  STILL ENFORCED in this mode:")
    print("      * regen_secrets.py --mode push-able (every secret becomes a placeholder)")
    print("      * key-shaped JSON values redacted tree-wide (SECRET_KEY_RE)")
    print("      * empty contacts.json + defaults-only external_mcps.json")
    print("      * build.py's live-MCP-secret seatbelt (hard abort)")
    print("      * STEP 4 audits the SHIPPED CONFIG SURFACE of the built package")
    print("  NOT possible in this mode: matching personal values -- none were declared.")
    return True


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
        try:
            backup.save(path)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            # A read-only / locked file we don't own (e.g. a bundled runtime's
            # module cache) must NEVER abort the release. SKIP_DIRS already excludes
            # the known runtime trees; this is the belt-and-suspenders backstop.
            print(f"  [skip] cannot scrub {path}: {exc}")
            return 0
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


# Files Tlamatini AUTHORS herself and ships inside the package. These are the only
# places a maintainer secret / address / phone can realistically survive a public
# build, so they are exactly what NO-TARGETS MODE audits -- narrowly, and
# BLOCKINGLY. (Running the full target-matching auditor with zero targets would be
# an expensive no-op: every target layer matches nothing, and the structural layer
# is informational by design, so it could never block anything.)
SHIPPED_CONFIG_NAMES = {"config.json", "contacts.json", "external_mcps.json",
                        "config.yaml", "data.keys"}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_SECRET_NAME_RE = re.compile(
    r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|bot[_-]?token|"
    r"client[_-]?secret|session[_-]?string|api[_-]?hash|app[_-]?password|"
    r"\btoken\b|\bsecret\b|\bpassword\b|\bpasswd\b|phone[_-]?number[_-]?id)")
_ASSIGN_RE = re.compile(r"""["']?([A-Za-z0-9_.-]*?)["']?\s*[:=]\s*["']?([^"',#]+)""")
# Values that are obviously NOT a live secret (placeholders, booleans, defaults).
_INERT_RE = re.compile(
    r"^\s*(|<[^>]*>|\{\{[^}]*\}\}|null|none|true|false|0|changeme|user|"
    r"your[_-].*|example.*|\*+|x+)\s*$", re.IGNORECASE)
_SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "domain.com",
                       "yourdomain.com", "gmail.com>", "email.com")


def _is_inert(value: str) -> bool:
    return bool(_INERT_RE.match(value or ""))


def verify_shipped_config_surface(verify_root: Path) -> int:
    """NO-TARGETS MODE verification. Returns the BLOCKING finding count.

    Deliberately narrow and deterministic: it does not try to guess what a
    stranger's private data looks like. It asserts the invariant a public
    Tlamatini package must satisfy either way -- the configuration SHE ships
    carries no live secret, no e-mail address and no phone number.
    """
    findings: list[str] = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(verify_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name not in SHIPPED_CONFIG_NAMES:
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(verify_root)
            if name == "data.keys":
                findings.append(f"{rel}: the SECRETS VAULT must never be inside a package")
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue  # a YAML comment documents the shape; it is not a value
                m = _ASSIGN_RE.search(line)
                if m and _SECRET_NAME_RE.search(m.group(1) or ""):
                    val = (m.group(2) or "").strip()
                    if not _is_inert(val) and len(val) >= 8:
                        findings.append(
                            f"{rel}:{lineno}: live-looking secret in '{m.group(1)}'")
                for em in _EMAIL_RE.findall(line):
                    if em.lower().endswith(_SAFE_EMAIL_DOMAINS):
                        continue
                    findings.append(f"{rel}:{lineno}: e-mail address '{em}'")
                if name == "contacts.json":
                    for ph in _PHONE_RE.findall(line):
                        if sum(c.isdigit() for c in ph) >= 7:
                            findings.append(f"{rel}:{lineno}: phone-shaped value")

    print(f"  audited {scanned} shipped config file(s) under {verify_root.name}/")
    if findings:
        print("  BLOCKING findings:")
        for f in findings[:40]:
            print(f"      ! {f}")
        if len(findings) > 40:
            print(f"      ... and {len(findings) - 40} more")
    return len(findings)


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
        # BLOCK only on genuinely-unique PII: emails (contain '@') and phone
        # numbers (>=7 digits). Bare common names ("Angela", "Ana") are NOT
        # blocked -- they appear all over bundled third-party libraries (django,
        # nltk, emoji, ...) and Angela wants her name left everywhere by design.
        # Angela's OWN kept name / handle (@angelahack1) is never a leak, even
        # though the handle contains '@' -- so it never blocks the build.
        v = value or ""
        if _is_kept_name(v):
            return False
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
    ap.add_argument("--no-private-data", action="store_true",
                    help="assert this tree carries NONE of your private data, so the "
                         "build may proceed with an empty target set even when "
                         "private-data markers (data.keys, a private contacts book) "
                         "are present. Without it, markers + no targets = REFUSE.")
    ap.add_argument("--extra-redact", action="append", default=[],
                    help="extra literal string to scrub (e.g. a leaked apikey); repeatable")
    ap.add_argument("--version", default="", help="explicit version (default: git-tag derived)")
    ap.add_argument("--python", default=sys.executable, help="system python to drive the build")
    # DEFAULT IS OFF: a public release ships NEITHER the TlamatiniSourceCode
    # tree NOR Tlamatini.md (her self-knowledge) — the two travel together, and
    # dropping both keeps ~15.7k tokens out of the system prompt on EVERY
    # request. --no-self-modify is accepted as the explicit form of the default.
    ap.add_argument("--self-modify", action="store_true",
                    help="also bundle the (scrubbed) TlamatiniSourceCode tree AND "
                         "Tlamatini.md (default: NEITHER is bundled).")
    ap.add_argument("--no-self-modify", action="store_true",
                    help="explicit form of the DEFAULT; overrides --self-modify.")
    ap.add_argument("--verify-llm", action="store_true",
                    help="let the auditor also run its LLM deep-review layer (slower, deeper)")
    ap.add_argument("--keep-scrubbed", action="store_true",
                    help="DANGEROUS: do not restore the working tree afterwards")
    args = ap.parse_args(argv)
    # --no-self-modify is the explicit form of the DEFAULT and always wins, so a
    # wrapper (or muscle memory) can force the small-prompt build unambiguously.
    if args.no_self_modify:
        args.self_modify = False

    py = args.python
    assert_system_python(py)

    # If no targets were given, auto-load the local gitignored targets file so the
    # bare command just works. When that file is absent we fall through to the
    # TRACKED, EMPTY template -- which resolves to zero targets and hands the
    # decision to decide_targets_mode(). Values are read from a file at run time,
    # never hardcoded.
    if (not args.targets_file and not args.target
            and not os.environ.get("CHECK_PRIVATE_DATA_TARGETS")):
        auto = default_targets_file()
        if auto:
            args.targets_file = str(auto)
            if auto == TEMPLATE_TARGETS_FILE:
                print(f"targets file : no {DEFAULT_TARGETS_FILES[0].name} on this machine; "
                      f"read the tracked EMPTY template {auto.name}")
            else:
                print(f"targets file : auto-loaded {auto.name} (no --targets-file given)")
        else:
            print("targets file : none found (not even the tracked template)")

    values = load_targets_values(args)
    no_targets = decide_targets_mode(values, args)

    banner("PUBLIC RELEASE BUILD  (SCRUBBED + LEAK-VERIFIED -- safe to distribute)")
    print(f"repo         : {REPO_ROOT}")
    print(f"python       : {py}")
    print("targets      : "
          + ("NONE declared -- NO-TARGETS MODE (secret scrub + config-surface audit only)"
             if no_targets else f"{len(values)} value(s) to scrub + verify"))
    print(f"self-modify  : {'YES (scrubbed snapshot) — source tree + Tlamatini.md bundled' if args.self_modify else 'no (DEFAULT) — no source tree, no self-knowledge, smaller prompt'}")

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
        # Pass the decision EXPLICITLY either way, so the intent is recorded in
        # the build log and a stray "--self-modify" in the ambient argv cannot
        # flip it. DEFAULT (no flag on this script) = not-self-able-modify.
        build_cmd.append("--self-modify" if args.self_modify else "--no-self-modify")
        if args.version:
            build_cmd.append(args.version)
        if run(build_cmd) != 0:
            sys.exit("build.py failed.")
        assert_self_modify_payload(args.self_modify)

        # build.py creates pkg.zip then removes dist/, so scan the package
        # (extracted) instead of the deleted dist/manage.
        banner("STEP 4/6  VERIFY the built package is clean (check_private_data.py)")
        verify_root = resolve_verify_root()
        if no_targets:
            # Zero declared targets, so the target-matching auditor would refuse
            # with rc=2 and dead-end the build. Audit what CAN be audited without
            # targets instead -- and make it BLOCKING, so no-targets mode is a
            # narrower gate, never an absent one.
            print("  NO-TARGETS MODE: auditing the shipped config surface "
                  "(secrets / e-mails / phones) instead of matching personal values.")
            leaks = verify_shipped_config_surface(verify_root)
        else:
            leaks = verify_clean(py, verify_root, args.targets_file, args.target,
                                 args.verify_llm)
        if VERIFY_EXTRACT.exists():
            shutil.rmtree(VERIFY_EXTRACT, ignore_errors=True)
        if leaks:
            sys.exit(f"\n!!! ABORT: {leaks} finding(s) in the build. No public artifact "
                     f"produced. (Working tree will be restored.)")
        print("  VERIFIED CLEAN: 0 blocking findings.")

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
