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
     .private_targets.json when not given) -- see "Targets are OPTIONAL" below.
  1. BACK UP touched files (restored in `finally`).
  2. regen_secrets.py --mode push-able  -> config secrets become placeholders.
  3. sanitize external_mcps.json (ship an empty catalog) + SCRUB the working tree.
  4. build.py --no-self-modify           -> freeze app + pkg.zip (build.py deletes dist/).
     DEFAULT: NO source tree and NO Tlamatini.md, keeping ~15.7k tokens out of
     the system prompt per request; pass --self-modify here to bundle both.
  5. VERIFY: extract pkg.zip and run check_private_data.py over it.
       any of YOUR personal data present -> ABORT, tree restored.
  6. build_uninstaller.py + build_installer.py -> dist/Tlamatini_Release_v<ver>/.
  7. zip -> dist/..._PUBLIC_CLEAN_win11x64.zip
  8. ALWAYS restore the working tree (finally).

Targets are OPTIONAL, never ASSUMED  (2026-08-30)
-------------------------------------------------
`.private_targets.json` is gitignored, so a FRESH CLONE never has one -- and this
builder used to REFUSE to run at all without it. It is now OPTIONAL. The refusal
was not simply deleted, because "no targets list" means two OPPOSITE things:

  * a PRISTINE clone -- there is no private data in the tree, so there is nothing
    to scrub. Refusing here is pure friction: it blocks a public build for no gain.
  * Angela's OWN tree with the file deleted / renamed / typo'd -- there IS private
    data and we have just lost the list of it. Proceeding here would publish her
    phone number. Refusing is the only safe act.

A target-INDEPENDENT PRIVACY PRE-FLIGHT (`privacy_preflight()`) tells the two
apart by looking for EVIDENCE that THIS tree can actually leak: `data.keys`, a
keyed `config.json` or agent `config.yaml`, a contacts book, a keyed External-MCP
catalog, root `*.key` files. Then:

  evidence found -> REFUSE, naming the exact evidence and the four ways to fix it.
  no evidence    -> build in CLEAN-TREE mode.

CLEAN-TREE mode is not "unprotected": every target-INDEPENDENT defence still runs
(regen_secrets --mode push-able, the SECRET_KEY_RE tree scrub, an empty contacts
book, the code-seeded MCP catalog, and build.py's live-MCP-secret abort). Only the
PII pass -- which needs a list of PII to look for -- is absent, and the banner,
the audit line and the final summary all say so out loud rather than implying a
verification that did not happen.

The pre-flight FAILS TOWARD REFUSAL: any error reading any probe counts AS
evidence. This is the deliberate opposite of Tlamatini's usual fail-open rule,
for the same reason LaTeXer's bisect guard fails safe -- publishing Angela's
private data is far worse than a build that stops and asks.

`private_targets.example.json` is a TRACKED, INERT template (shape only, no real
values). It is deliberately NOT in DEFAULT_TARGETS_FILES and its placeholder
values are stripped from the scrub set, because a template that could make the
target list merely non-empty would SILENCE the refusal above and produce a build
that reports "verified" having scrubbed nothing real -- strictly worse than the
refusal it replaced.

RUNTIME: none of this is ever read by the running application. `.private_targets.json`
is a BUILD-TIME-ONLY artifact -- no module under `Tlamatini/agent/` opens it, and
neither `build.py` nor `install.py` ships or references it -- so a missing file can
never affect Tlamatini's first run or any later one. Pinned by
`Tlamatini/agent/test_public_release_targets.py`.
"""

from __future__ import annotations

import argparse
import glob
import json
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
# WARNING: NEVER add the tracked template to this list. Auto-loading placeholder
# values would make the target set merely non-empty and so SILENCE the refusal in
# main() -- yielding a build that prints "VERIFIED CLEAN" having scrubbed nothing
# real. A template is documentation; only a real private file is data.
DEFAULT_TARGETS_FILES = [REPO_ROOT / ".private_targets.json",
                         REPO_ROOT / "private_targets.json"]

#: Tracked, INERT, shape-only template a cloner copies to .private_targets.json.
#: Never auto-loaded (see above); its values are stripped by _is_placeholder().
TARGETS_TEMPLATE = REPO_ROOT / "private_targets.example.json"

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

#: Managed config files that `regen_secrets.py` REWRITES, so STEP 1 can back every
#: one of them up byte-for-byte BEFORE running it.
#:
#: WARNING: DERIVED, never hand-typed. The hand-written list carried only 5 of the
#: 7 agent config.yaml files regen actually edits -- `zavuerer` and `discoverer`
#: were missing. On a machine WITHOUT data.keys the `finally` re-key is skipped, so
#: those two were scrubbed to placeholders with NO backup to restore from: silent
#: loss of the operator's own keys. Reading the paths out of regen_secrets itself
#: means the NEXT managed config file is covered the day it is added there.
#: Pinned by Tlamatini/agent/test_public_release_targets.py.
_REGEN_MANAGED_BASENAMES = ("config.json", "config.yaml", "external_mcps.json")
_REGEN_TOUCHED_FALLBACK = [
    REPO_ROOT / "Tlamatini" / "agent" / "config.json",
    REPO_ROOT / "Tlamatini" / "agent" / "external_mcps.json",
] + [REPO_ROOT / "Tlamatini" / "agent" / "agents" / _a / "config.yaml"
     for _a in ("telegrammer", "whatsapper", "teletlamatini", "emailer",
                "recmailer", "zavuerer", "discoverer")]


def _regen_touched_files() -> list[Path]:
    """Every path regen_secrets.py can rewrite, read from regen_secrets itself.

    Fails toward BACKING UP MORE: if the import yields fewer paths than the
    explicit fallback (a renamed constant, a syntax error, a partial read), the
    fallback wins. Backing up a file we did not need costs a file copy; missing
    one costs the operator their credentials.
    """
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("_tlm_regen_paths", REGEN)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        found = sorted({v for name, v in vars(mod).items()
                        if name.isupper() and isinstance(v, Path)
                        and v.name in _REGEN_MANAGED_BASENAMES})
        if len(found) >= len(_REGEN_TOUCHED_FALLBACK):
            return found
        print(f"  NOTE: regen_secrets exposed {len(found)} managed path(s); using "
              f"the {len(_REGEN_TOUCHED_FALLBACK)}-path fallback (backing up more).")
    except Exception as exc:
        print(f"  NOTE: could not read regen_secrets paths ({exc}); using the "
              f"explicit fallback list.")
    return list(_REGEN_TOUCHED_FALLBACK)


REGEN_TOUCHED = _regen_touched_files()

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
                    "contacts.private.json"}

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
    return env


def run(cmd: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd), env=_utf8_env()).returncode


def default_targets_file() -> Path | None:
    for cand in DEFAULT_TARGETS_FILES:
        if cand.is_file():
            return cand
    return None


#: Obvious TEMPLATE stand-ins, not real private data. Stripped from the scrub set
#: so that copying private_targets.example.json to .private_targets.json and
#: forgetting to fill it in behaves like "no targets given" (-> the pre-flight
#: decides) instead of like "targets given" (-> a build that reports VERIFIED
#: CLEAN having scrubbed the literal text "<your phone number>").
#
# NOTE ON THE PREFIX GROUP: it matches with NO word boundary, because the real
# placeholders in this repo are glued: `YourStrongPassword` (sqler/config.yaml),
# `YOUR_EMAIL_HERE`, `ChangeMeNow`. A `\b` after the keyword misses every one of
# them -- `\b` needs a non-word char, and `S`/`_` are word chars. The prefixes are
# therefore chosen to be ones no real name or value starts with; in particular
# `my` is DELIBERATELY ABSENT, because it would swallow real names like "Myriam".
_PLACEHOLDER_RE = re.compile(
    r"""(?ix)
    ^\s*(?:
        <[^>]*>                                            # <your email>, <REDACTED>
      | (?:your|example|sample|dummy|placeholder|changeme|change[_\- ]me
          |replace[_\- ]?me|fill[_\- ]?me|todo|tbd|xxx+).*  # glued, no \b
      | (?:none|n/?a)\b.*                                  # short: boundary needed
      | [^@\s]*@(?:example|sample|test|invalid|localhost)\.[a-z.]+   # RFC 2606
      | \+?[\s\-()]*0[\d\s\-()]*                           # +000000000, 000-000-0000
    )\s*$""")


def _is_placeholder(value: str) -> bool:
    """True for a template stand-in.

    Deliberately CONSERVATIVE. A false "yes" here DROPS a real value from the
    scrub set, which is the single mistake that publishes private data -- so only
    unmistakable template shapes match, and anything ambiguous is treated as real.
    """
    return bool(_PLACEHOLDER_RE.match(value or ""))


def load_targets_values(args) -> list[str]:
    """Reuse check_private_data.load_targets (NEVER hardcode private data)."""
    sys.path.insert(0, str(REPO_ROOT))
    import check_private_data as cpd  # noqa: E402
    ns = SimpleNamespace(targets_file=args.targets_file, target=args.target)
    targets = cpd.load_targets(ns)
    # NEVER scrub Angela's name -- keep her authorship everywhere, in every build.
    #
    # Two further exclusions, both there to stop an UNFILLED template from passing
    # itself off as a real target list (which would silence the pre-flight and
    # produce a build that prints VERIFIED CLEAN having scrubbed nothing):
    #   * `_`-prefixed JSON keys are DOCUMENTATION, not data. cpd.load_targets
    #     turns every dict key into a `category` and every value into a target, so
    #     without this a `_README` string becomes a "private value" to hunt for.
    #     Same `_`-prefix convention external_mcps.json already uses.
    #   * placeholder-shaped values are dropped -- see _is_placeholder.
    vals = [t["value"] for t in targets
            if t.get("value", "").strip()
            and not str(t.get("category", "")).startswith("_")
            and not _is_kept_name(t["value"])
            and not _is_placeholder(t["value"])]
    return sorted(set(vals), key=len, reverse=True)


# =============================================================================
# PRIVACY PRE-FLIGHT  --  "could THIS tree leak anything at all?"
#
# Answers, with NO private-data list in hand, the only question that matters when
# no targets were supplied:
#
#     a PRISTINE clone            -> nothing to scrub  -> building is safe
#     a working tree that LOST    -> everything to scrub, and we no longer know
#     its targets file               what to look for  -> refusing is the only
#                                     safe act
#
# EVERY probe FAILS TOWARD REFUSAL: an unreadable, malformed or surprising file
# counts AS evidence. That is the deliberate INVERSE of Tlamatini's usual
# fail-open rule, for the same reason LaTeXer's bisect rung fails safe: the cost
# of a wrong "clean" verdict is publishing Angela's private data, and no amount of
# build convenience outweighs that.
# =============================================================================

#: Credential-shaped config keys. Anchored on purpose -- a bare `token` substring
#: would match `max_tokens: 4096` in talker/config.yaml and make EVERY tree look
#: keyed, which would permanently refuse the very clone this feature exists for.
_SECRET_NAME_RE = re.compile(
    r"(?i)(?:^|[_.\-])(?:api[_-]?key|apikey|api[_-]?secret|access[_-]?token"
    r"|auth[_-]?token|bearer[_-]?token|client[_-]?secret|session[_-]?string"
    r"|password|passwd|secret)(?:$|[_.\-])"
    r"|(?:^|[_.\-])(?:token|key)$")

#: A value that cannot be a live credential OR a piece of PII. `[\d.]+` covers
#: BOTH plain numbers (`max_body_bytes: 1048576`) and dotted-numeric addresses
#: (`host: 127.0.0.1`, `webhook_host: 0.0.0.0`) -- committed defaults that a
#: naive phone-shape test happily reads as a phone number. `tlamatini` is the
#: product's own name, shipped as the default `verify_token` in whatsapper and
#: instant_messaging_doctor; it is a documented default, never a credential.
_INERT_VALUE_RE = re.compile(
    r"(?i)^\s*(?:|<[^>]*>|none|null|false|true|changeme|tlamatini|\d+|[\d.]+)\s*$")

#: PII SHAPES -- recognisable without knowing Angela's actual values.
_EMAIL_SHAPE_RE = re.compile(r"[^@\s<>\"']+@[^@\s<>\"']+\.[A-Za-z]{2,}")

#: A written phone number carries a `+` or a separator. Requiring one (and
#: excluding `.` from the class entirely) is what stops `1048576` and `127.0.0.1`
#: from reading as phone numbers -- the exact false positives that made a fresh
#: clone unbuildable when this was first written.
_PHONE_SHAPE_RE = re.compile(r"^\+?[\d\s\-()]{7,24}$")
_PHONE_SEPARATORS = ("+", " ", "-", "(")

#: A live credential is at least this long. Short values are settings
#: (`sort_key: mtime`, `key: id`), not secrets, and treating them as secrets would
#: make a pristine clone unbuildable.
_MIN_SECRET_LEN = 8


def _is_live_secret(name, value) -> bool:
    if not isinstance(value, str) or not _SECRET_NAME_RE.search(str(name)):
        return False
    v = value.strip().strip("'\"")
    if len(v) < _MIN_SECRET_LEN or _INERT_VALUE_RE.match(v) or _is_placeholder(v):
        return False
    return "goes here" not in v.lower()


def _looks_like_pii(value: str) -> bool:
    """An email address or a WRITTEN phone number, judged by shape alone.

    The inert test runs FIRST and is what keeps committed defaults out: byte
    counts (`1048576`) and bind addresses (`127.0.0.1`, `0.0.0.0`) are numbers,
    not people. A phone must additionally carry a `+` or a separator and hold
    7-15 digits, so a bare integer can never qualify.
    """
    v = (value or "").strip()
    if not v or _INERT_VALUE_RE.match(v) or _is_placeholder(v):
        return False
    if _EMAIL_SHAPE_RE.search(v):
        return True
    return bool(_PHONE_SHAPE_RE.match(v)
                and any(sep in v for sep in _PHONE_SEPARATORS)
                and 7 <= sum(c.isdigit() for c in v) <= 15)


def _json_secret_hits(path: Path) -> list[str]:
    """Credential-shaped keys holding a non-placeholder value, at any depth."""
    hits: list[str] = []

    def walk(node, trail: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                where = f"{trail}.{k}" if trail else str(k)
                if _is_live_secret(k, v):
                    hits.append(where)
                else:
                    walk(v, where)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{trail}[{i}]")

    walk(json.loads(path.read_text(encoding="utf-8-sig")), "")
    return sorted(set(hits))


def _yaml_scan(path: Path) -> tuple[list[str], list[str]]:
    """(credential keys, PII-shaped keys) in one agent config.yaml.

    Line-oriented, exactly like regen_secrets' own YAML patcher (which edits line
    by line to preserve comments) -- so no yaml dependency and no reformatting.
    """
    secrets: list[str] = []
    pii: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0]
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip().strip("'\"")
        if not key or not val:
            continue
        if _is_live_secret(key, val):
            secrets.append(key)
        elif _looks_like_pii(val):
            pii.append(key)
    return sorted(set(secrets)), sorted(set(pii))


def privacy_preflight() -> list[str]:
    """Evidence that this working tree holds scrubbable private material.

    Returns human-readable evidence lines; an EMPTY list means "pristine".
    """
    evidence: list[str] = []

    def probe(label: str, fn) -> None:
        """Run one probe. ANY exception becomes evidence -- never a silent pass."""
        try:
            found = fn()
        except Exception as exc:
            evidence.append(
                f"{label}: UNREADABLE ({exc}) -- counted AS private data, because "
                f"a file that could not be checked must never be called clean")
            return
        if found:
            evidence.append(f"{label}: {found}")

    agent_dir = REPO_ROOT / "Tlamatini" / "agent"

    def _vault() -> str:
        vault = REPO_ROOT / "data.keys"
        if not vault.is_file():
            return ""
        n = sum(1 for ln in vault.read_text(encoding="utf-8",
                                            errors="replace").splitlines()
                if "=" in ln and not ln.lstrip().startswith("#"))
        return f"present, {n} key(s) -- this is a KEYED maintainer tree" if n else ""

    probe("data.keys (the live secrets vault)", _vault)

    for cfg in (agent_dir / "config.json", agent_dir / "external_mcps.json"):
        def _json_probe(p=cfg) -> str:
            return ", ".join(_json_secret_hits(p)) if p.is_file() else ""
        probe(f"{cfg.name} holds live secret(s)", _json_probe)

    for yml in sorted(agent_dir.glob("agents/*/config.yaml")):
        def _yaml_probe(p=yml) -> str:
            secrets, pii = _yaml_scan(p)
            parts = []
            if secrets:
                parts.append("live secret(s): " + ", ".join(secrets))
            if pii:
                parts.append("real email/phone in: " + ", ".join(pii))
            return "; ".join(parts)
        probe(f"agents/{yml.parent.name}/config.yaml", _yaml_probe)

    for book in (agent_dir / "contacts.json", agent_dir / "contacts.private.json",
                 REPO_ROOT / "contacts.json", REPO_ROOT / "contacts.private.json"):
        def _book_probe(p=book) -> str:
            if not p.is_file():
                return ""
            data = json.loads(p.read_text(encoding="utf-8-sig") or "null")
            n = len(data) if isinstance(data, (list, dict)) else 0
            return f"{n} real contact(s)" if n else ""
        probe(f"{book.name} (a real people's contact book)", _book_probe)

    probe("private key file(s) at the repo root",
          lambda: ", ".join(sorted(p.name for p in REPO_ROOT.glob("*.key"))))

    return evidence


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


#: Passed to the auditor in CLEAN-TREE mode. check_private_data.py exits 2 with no
#: targets at all, which would abort the build -- but skipping the audit outright
#: would silently drop the ONLY post-build inspection. A value that cannot occur in
#: any artifact satisfies its precondition, so every STRUCTURAL layer (PEM blocks,
#: certificates, high-entropy blobs, Kyber material, steganography) still runs and
#: the PII count is truthfully zero because no PII was ever searched for.
STRUCTURAL_ONLY_SENTINEL = "TLAMATINI-NO-PII-TARGETS-SENTINEL-8f3c1d47a9b24e60"


def verify_clean(py: str, verify_root: Path, targets_file: str,
                 target: list[str], use_llm: bool,
                 structural_only: bool = False) -> int:
    """Run the auditor over the built package. Returns the number of files that
    contain YOUR personal data (the BLOCKING count). Structural/binary pattern
    matches (kyber keyword, certs, high-entropy, PEM) are reported but never block.

    ``structural_only`` is CLEAN-TREE mode: no PII list exists, so the structural
    layers run alone and the report says so instead of implying a personal-data
    verification that never happened.
    """
    report = REPO_ROOT / "public_release_verify_report.json"
    cmd = [py, str(CHECKER), "--local", "--repo", str(verify_root),
           "--output", str(report)]
    if structural_only:
        cmd += ["--target", STRUCTURAL_ONLY_SENTINEL]
    else:
        if targets_file:
            cmd += ["--targets-file", targets_file]
        for t in target or []:
            cmd += ["--target", t]
    if not use_llm:
        cmd += ["--no-llm"]
    rc = run(cmd)
    if rc == 2:
        sys.exit("VERIFY ERROR: auditor got no targets. Pass --targets-file/--target.")
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
    if structural_only:
        # NO LYING: say exactly what was and was not checked. Reporting
        # "0 PII leaks" without this line would imply a personal-data
        # verification that was never performed.
        print("  MODE: STRUCTURAL-ONLY -- no PII targets were supplied, so NO "
              "personal-data matching was performed (0 is by construction, not "
              "by inspection).")
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
    ap.add_argument("--assume-clean-tree", action="store_true",
                    help="DANGEROUS: build with NO targets even though the privacy "
                         "pre-flight found private material in this tree. You are "
                         "asserting every reported item is safe to publish.")
    args = ap.parse_args(argv)
    # --no-self-modify is the explicit form of the DEFAULT and always wins, so a
    # wrapper (or muscle memory) can force the small-prompt build unambiguously.
    if args.no_self_modify:
        args.self_modify = False

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

    # ── No usable targets? That means one of two OPPOSITE things. Ask the TREE. ──
    # A missing targets file is not an error by itself: it is the normal state of
    # a fresh clone, which has nothing to scrub. It is only an error when this
    # tree actually holds private material -- so the pre-flight decides, and it
    # fails toward REFUSAL. (Full contract in the module docstring.)
    clean_tree = False
    if not values:
        banner("PRIVACY PRE-FLIGHT  (no leak targets supplied -- inspecting the tree)")
        evidence = privacy_preflight()
        for line in evidence:
            print(f"  [EVIDENCE] {line}")
        if evidence and not args.assume_clean_tree:
            sys.exit(
                f"\nREFUSING: this working tree holds private material "
                f"({len(evidence)} item(s) above) but NO list of what to scrub, so a "
                f"public build would ship it.\n\n"
                f"Fix it in whichever way suits you:\n"
                f"  1. copy {TARGETS_TEMPLATE.name} -> .private_targets.json and fill "
                f"in YOUR real values\n"
                f"     (that filename is gitignored, so it never leaves your machine)\n"
                f"  2. --targets-file <path>\n"
                f"  3. --target \"value\"          (repeatable)\n"
                f"  4. env CHECK_PRIVATE_DATA_TARGETS\n"
                f"  5. DANGEROUS, only if you are certain every item above is safe to "
                f"publish: --assume-clean-tree\n\n"
                f"(Private data is NEVER hardcoded in this repository -- that is why "
                f"the list has to come from you.)")
        if evidence:
            print("\n  !!! --assume-clean-tree GIVEN: proceeding despite the evidence "
                  "above.")
            print("  !!! NO personal-data scrub and NO personal-data verification will "
                  "run.")
            print("  !!! You are asserting every item above is safe to publish.")
        else:
            print("  no private material found -- this is a pristine clone, so there "
                  "is nothing to scrub.")
        clean_tree = True

    banner("PUBLIC RELEASE BUILD  (SCRUBBED + LEAK-VERIFIED -- safe to distribute)")
    print(f"repo         : {REPO_ROOT}")
    print(f"python       : {py}")
    if clean_tree:
        print("targets      : NONE -- CLEAN-TREE MODE (no PII scrub, no PII verify)")
        print("               STILL ACTIVE: regen_secrets --mode push-able; the "
              "secret-key regex")
        print("               scrub; an EMPTY contacts book; the code-seeded MCP "
              "catalog; and")
        print("               build.py's hard abort on a live MCP secret.")
    else:
        print(f"targets      : {len(values)} value(s) to scrub + verify")
    print(f"self-modify  : {'YES (scrubbed snapshot) — source tree + Tlamatini.md bundled' if args.self_modify else 'no (DEFAULT) — no source tree, no self-knowledge, smaller prompt'}")

    backup = Backup(REPO_ROOT)
    ok = False
    try:
        # AUTOMATIC: you never have to run regen_secrets.py yourself before this
        # builder. Every managed config is backed up byte-for-byte FIRST (the list
        # is derived from regen_secrets itself), rewritten to placeholders here,
        # and restored -- plus re-keyed from data.keys -- in the `finally`.
        banner(f"STEP 1/6  regen_secrets.py --mode push-able  (AUTOMATIC; "
               f"{len(REGEN_TOUCHED)} managed file(s) backed up first)")
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

        banner("STEP 2/6  scrubbing private data from the working tree"
               + ("  [CLEAN-TREE: secret-key regex only]" if clean_tree else ""))
        n = scrub_tree(values, args.extra_redact, backup)
        print(f"  scrubbed {n} file(s).")
        if clean_tree:
            print("  (no PII value list, so this pass applied the secret-key regex"
                  + (" and --extra-redact" if args.extra_redact else "")
                  + " only.)")

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
        leaks = verify_clean(py, verify_root, args.targets_file, args.target,
                             args.verify_llm, structural_only=clean_tree)
        if VERIFY_EXTRACT.exists():
            shutil.rmtree(VERIFY_EXTRACT, ignore_errors=True)
        if leaks:
            sys.exit(f"\n!!! ABORT: {leaks} file(s) in the build STILL contain your personal "
                     f"data. No public artifact produced. See public_release_verify_report.json. "
                     f"(Working tree will be restored.)")
        if clean_tree:
            print("  STRUCTURAL AUDIT PASSED. Personal-data matching was NOT "
                  "performed (no targets were supplied and the pre-flight found "
                  "no private material to supply targets for).")
        else:
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
        banner("PUBLIC RELEASE COMPLETE -- "
               + ("STRUCTURALLY AUDITED (CLEAN-TREE MODE, no PII pass)"
                  if clean_tree else "VERIFIED CLEAN"))
        if clean_tree:
            print("  mode           : CLEAN-TREE -- no PII targets existed, so no "
                  "personal-data")
            print("                   scrub or verification ran. Secrets were still "
                  "made push-able,")
            print("                   contacts shipped empty, and the MCP catalog "
                  "was code-seeded.")
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
