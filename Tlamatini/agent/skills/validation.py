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
The ONE validator for a SKILL.md package.

WHY THIS EXISTS
---------------
Three surfaces used to disagree about what a valid skill is:

* ``_meta/lint.py``        — parsed, then applied an **8 KiB** body cap it
                             measured with ``len(str)``, i.e. CHARACTERS,
                             while printing the word "bytes". A body of
                             8,158 characters / 8,466 bytes passed a check
                             whose stated unit it exceeded.
* ``skill_creator/scripts/quick_validate.py``
                           — did not parse YAML at all (despite saying so),
                             substring-matched ``name:`` / ``description:``,
                             and applied a different **12,288-character**
                             whole-file ceiling.
* ``SkillRegistry``        — enforced neither cap, so a skill the linter
                             rejected still loaded and ran.

Three answers to one question is worse than any single wrong answer: a
package could pass the quick check, fail the catalog lint, and run fine in
production. Everything now routes through :func:`validate_skill_file`.

THE POLICY (explicit, per the R05 acceptance criteria)
------------------------------------------------------
Findings carry a severity, and severity maps to a defined consequence:

    ``error``    the package is INVALID. The registry refuses it (a
                 ``SkillParseError`` is exactly this), the linter exits 1,
                 and quick validation exits 1.
    ``warning``  the package LOADS and RUNS, but something should be fixed.
                 The linter reports it and still exits 0.

Size is measured in **UTF-8 BYTES**, because the contract is stated in KiB.
Two thresholds, both deliberate:

    ``BODY_WARN_BYTES``  (8 KiB)  — above this, move detail into
                                    ``references/``; the harness lists them
                                    with absolute paths and the caller can
                                    retrieve them. A warning, not a failure:
                                    the registry never rejected these and
                                    pretending otherwise is the inconsistency
                                    this module exists to remove.
    ``BODY_MAX_BYTES``  (16 KiB)  — a hard error. Above it a body stops being
                                    a procedure and becomes a document.

Stdlib-only; imports nothing outside ``agent.skills`` so it behaves
identically in source mode, in a frozen build, and when ``lint.py`` is run
standalone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .frontmatter import SkillParseError, parse_skill_md

#: Above this the body should be split into ``references/`` — warning only.
BODY_WARN_BYTES = 8 * 1024
#: Above this the package is rejected outright.
BODY_MAX_BYTES = 16 * 1024

#: Budget ranges, mirroring ``_meta/schema.json``. Kept here as the runtime
#: authority so a validator never needs a JSON-Schema dependency.
BUDGET_RANGES: Dict[str, tuple] = {
    "max_iterations": (1, 256),
    "max_seconds": (1, 7200),
    "max_tokens": (1, 1_000_000),
}

_VALID_RUNTIMES = ("in-process", "acpx")
_VALID_NETWORK = ("allow", "deny")
_VALID_DB = ("allow", "deny", "read")

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass
class Finding:
    severity: str
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"[{self.severity}] {self.code}: {self.message}"


@dataclass
class SkillValidation:
    path: Path
    name: str = ""
    runtime: str = ""
    body_chars: int = 0
    body_bytes: int = 0
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    @property
    def ok(self) -> bool:
        """True when nothing would make the registry refuse this package."""
        return not self.errors

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(Finding(severity, code, message))


def _check_budget(tla: Dict[str, Any], result: SkillValidation) -> None:
    budget = tla.get("budget")
    if budget is None:
        return
    if not isinstance(budget, dict):
        result.add(SEVERITY_ERROR, "budget_shape",
                   "metadata.tlamatini.budget must be a mapping")
        return
    for key, (low, high) in BUDGET_RANGES.items():
        if key not in budget:
            continue
        value = budget[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            result.add(SEVERITY_ERROR, "budget_type",
                       f"budget.{key} must be a number, got "
                       f"{type(value).__name__}")
            continue
        if key != "max_seconds" and float(value) != int(value):
            result.add(SEVERITY_ERROR, "budget_type",
                       f"budget.{key} must be an integer, got {value!r}")
            continue
        if not (low <= value <= high):
            result.add(SEVERITY_ERROR, "budget_range",
                       f"budget.{key}={value} is outside {low}..{high}")
    for key in budget:
        if key not in BUDGET_RANGES:
            result.add(SEVERITY_WARNING, "budget_unknown_key",
                       f"budget.{key} is not a recognised budget field")


def _check_permissions(tla: Dict[str, Any], result: SkillValidation) -> None:
    perms = tla.get("permissions")
    if perms is None:
        return
    if not isinstance(perms, dict):
        result.add(SEVERITY_ERROR, "permissions_shape",
                   "metadata.tlamatini.permissions must be a mapping")
        return
    network = perms.get("network")
    if network is not None and not isinstance(network, list) \
            and network not in _VALID_NETWORK:
        result.add(SEVERITY_ERROR, "permissions_network",
                   f"permissions.network must be one of {_VALID_NETWORK} "
                   f"or a list, got {network!r}")
    db = perms.get("db")
    if db is not None and not isinstance(db, list) and db not in _VALID_DB:
        result.add(SEVERITY_ERROR, "permissions_db",
                   f"permissions.db must be one of {_VALID_DB} or a list, "
                   f"got {db!r}")
    fs = perms.get("filesystem")
    if fs is not None and not isinstance(fs, dict):
        result.add(SEVERITY_ERROR, "permissions_filesystem",
                   "permissions.filesystem must be a mapping")


def _check_io(decls: Any, kind: str, result: SkillValidation) -> None:
    if not decls:
        return
    if not isinstance(decls, list):
        result.add(SEVERITY_ERROR, f"{kind}_shape",
                   f"metadata.tlamatini.{kind} must be a list")
        return
    seen: set = set()
    for decl in decls:
        if not isinstance(decl, dict):
            result.add(SEVERITY_ERROR, f"{kind}_item",
                       f"{kind} entries must be mappings, got "
                       f"{type(decl).__name__}")
            continue
        name = decl.get("name")
        if not isinstance(name, str) or not name.strip():
            result.add(SEVERITY_ERROR, f"{kind}_name",
                       f"{kind} entry is missing a non-empty 'name'")
            continue
        if name in seen:
            result.add(SEVERITY_ERROR, f"{kind}_duplicate",
                       f"{kind} declares '{name}' more than once")
        seen.add(name)
        if "type" not in decl:
            result.add(SEVERITY_ERROR, f"{kind}_type",
                       f"{kind}.{name} is missing 'type'")
        dtype = str(decl.get("type") or "").lower()
        if dtype == "enum" and not (decl.get("values") or decl.get("choices")):
            result.add(SEVERITY_ERROR, f"{kind}_enum",
                       f"{kind}.{name} is an enum with no 'values'/'choices'")
        sensitive = decl.get("sensitive")
        if sensitive is not None and not isinstance(sensitive, bool):
            result.add(SEVERITY_ERROR, f"{kind}_sensitive",
                       f"{kind}.{name}.sensitive must be a boolean")


def _check_dependencies(tla: Dict[str, Any], result: SkillValidation) -> None:
    for key in ("requires_tools", "requires_mcps"):
        value = tla.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            continue  # the parser coerces a bare string to a 1-item list
        if not isinstance(value, list):
            result.add(SEVERITY_ERROR, "requires_shape",
                       f"metadata.tlamatini.{key} must be a list of strings")
            continue
        for item in value:
            if not isinstance(item, str) or not item.strip():
                result.add(SEVERITY_ERROR, "requires_item",
                           f"{key} contains a non-string entry: {item!r}")


def validate_skill_text(text: str, *, source_label: str = "<skill>",
                        path: Optional[Path] = None) -> SkillValidation:
    """Validate one SKILL.md's TEXT. Never raises."""
    result = SkillValidation(path=path or Path(source_label))
    try:
        fm, body = parse_skill_md(text, source_label=source_label)
    except SkillParseError as e:
        result.add(SEVERITY_ERROR, "parse", str(e))
        return result
    except Exception as e:  # pragma: no cover - defensive
        result.add(SEVERITY_ERROR, "parse", f"{type(e).__name__}: {e}")
        return result

    result.name = fm.name
    result.runtime = fm.runtime
    result.body_chars = len(body)
    #: ⚠️ BYTES, not characters. The old check measured ``len(str)`` while
    #: printing "bytes", so an 8,158-character / 8,466-byte body passed a
    #: stated 8 KiB cap it actually exceeded.
    result.body_bytes = len(body.encode("utf-8"))

    if not body:
        result.add(SEVERITY_ERROR, "empty_body", "the skill body is empty")
    if not fm.description.strip():
        result.add(SEVERITY_WARNING, "no_description",
                   "description is empty; the planner and list_skills use it")
    if fm.runtime not in _VALID_RUNTIMES:  # pragma: no cover - parser guards
        result.add(SEVERITY_ERROR, "runtime",
                   f"runtime must be one of {_VALID_RUNTIMES}")

    if result.body_bytes > BODY_MAX_BYTES:
        result.add(SEVERITY_ERROR, "body_too_large",
                   f"body is {result.body_bytes} bytes, over the "
                   f"{BODY_MAX_BYTES}-byte ({BODY_MAX_BYTES // 1024} KiB) cap")
    elif result.body_bytes > BODY_WARN_BYTES:
        result.add(SEVERITY_WARNING, "body_large",
                   f"body is {result.body_bytes} bytes, over the "
                   f"{BODY_WARN_BYTES // 1024} KiB guideline — move detail "
                   f"into references/ (the harness lists them by absolute "
                   f"path so they stay retrievable)")

    metadata = fm.raw.get("metadata") if isinstance(fm.raw, dict) else None
    tla = {}
    if isinstance(metadata, dict):
        candidate = metadata.get("tlamatini")
        if isinstance(candidate, dict):
            tla = candidate
    _check_budget(tla, result)
    _check_permissions(tla, result)
    _check_dependencies(tla, result)
    _check_io(tla.get("inputs"), "inputs", result)
    _check_io(tla.get("outputs"), "outputs", result)
    return result


def validate_skill_file(path: Path) -> SkillValidation:
    """Validate one SKILL.md on disk. Never raises."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        result = SkillValidation(path=path)
        result.add(SEVERITY_ERROR, "unreadable", f"{type(e).__name__}: {e}")
        return result
    return validate_skill_text(text, source_label=str(path), path=path)


def validate_skill_dir(skill_dir: Path) -> SkillValidation:
    """Validate a package DIRECTORY (expects ``<dir>/SKILL.md``)."""
    skill_dir = Path(skill_dir)
    md = skill_dir / "SKILL.md"
    if not md.exists():
        result = SkillValidation(path=md)
        result.add(SEVERITY_ERROR, "missing", f"{md} does not exist")
        return result
    return validate_skill_file(md)


def check_duplicate_names(results: Iterable[SkillValidation]
                          ) -> List[Finding]:
    """
    Collision findings across a set of validated packages.

    ⚠️ A duplicate name is only a defect WITHIN one root. Across roots it is
    an intentional override (the user-editable install copy shadowing the
    bundled one) — see ``SkillRegistry._default_roots``. Callers that scan a
    single tree should treat these as errors; a cross-root loader must not.
    """
    findings: List[Finding] = []
    seen: Dict[str, Path] = {}
    for r in results:
        if not r.name:
            continue
        prior = seen.get(r.name)
        if prior is not None:
            findings.append(Finding(
                SEVERITY_ERROR, "duplicate_name",
                f"skill name '{r.name}' appears in both {prior} and {r.path}",
            ))
            continue
        seen[r.name] = r.path
    return findings
