# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
SKILL.md frontmatter parser.

The SKILL.md format is OpenClaw-compatible:

    ---
    name: skill-name
    description: One-line description.
    metadata:
      openclaw: { ... }
      tlamatini:
        runtime: in-process | acpx
        acpx_agent: claude        # required when runtime=acpx
        requires_tools: ["chat_agent_executer", ...]
        requires_mcps:  ["Files-Search"]
        budget:
          max_iterations: 12
          max_seconds: 180
          max_tokens: 30000
        permissions:
          filesystem: { read: [...], write: [...] }
          shell:      ["allowed-shell-commands ..."]
          network:    "deny" | "allow"
          db:         "deny" | "read" | ["read", "write-via-migrations-only"]
        inputs:
          - { name: ..., type: string|number|enum, required: true|false, ... }
        outputs:
          - { name: ..., type: ..., required: true|false }
        triggers:
          keywords:   [...]
          file_globs: [...]
    ---

    # Skill body (markdown, becomes the system prompt for the in-process
    # scoped Multi-Turn loop, or the task body for an ACPX child).

The parser is permissive: missing fields are filled with safe defaults;
malformed YAML is rejected with a clear message.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)


@dataclass
class SkillFrontmatter:
    name: str
    description: str
    runtime: str = "in-process"
    acpx_agent: str = ""
    requires_tools: List[str] = field(default_factory=list)
    requires_mcps: List[str] = field(default_factory=list)
    max_iterations: int = 12
    max_seconds: float = 180.0
    max_tokens: int = 30_000
    permissions: Dict[str, Any] = field(default_factory=dict)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    triggers_keywords: List[str] = field(default_factory=list)
    triggers_file_globs: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


class SkillParseError(Exception):
    pass


def _coerce_str_list(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    return []


def parse_skill_md(text: str, *, source_label: str = "<skill>") -> tuple[SkillFrontmatter, str]:
    """
    Parse a SKILL.md text and return (frontmatter, body).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SkillParseError(f"{source_label}: missing YAML frontmatter")
    try:
        fm_dict = yaml.safe_load(m.group("fm")) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"{source_label}: invalid YAML — {e}")
    if not isinstance(fm_dict, dict):
        raise SkillParseError(f"{source_label}: frontmatter must be a mapping")

    name = fm_dict.get("name")
    description = fm_dict.get("description", "")
    if not isinstance(name, str) or not name.strip():
        raise SkillParseError(f"{source_label}: 'name' is required")
    if not isinstance(description, str):
        description = str(description)

    metadata = fm_dict.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    tla = metadata.get("tlamatini") or {}
    if not isinstance(tla, dict):
        tla = {}

    runtime = tla.get("runtime") or "in-process"
    if runtime not in ("in-process", "acpx"):
        raise SkillParseError(
            f"{source_label}: tlamatini.runtime must be 'in-process' or 'acpx'"
        )
    acpx_agent = str(tla.get("acpx_agent") or "")
    if runtime == "acpx" and not acpx_agent:
        raise SkillParseError(
            f"{source_label}: runtime=acpx requires tlamatini.acpx_agent"
        )

    budget = tla.get("budget") or {}
    if not isinstance(budget, dict):
        budget = {}

    triggers = tla.get("triggers") or {}
    if not isinstance(triggers, dict):
        triggers = {}

    permissions = tla.get("permissions") or {}
    if not isinstance(permissions, dict):
        permissions = {}

    inputs = tla.get("inputs") or []
    if not isinstance(inputs, list):
        inputs = []
    outputs = tla.get("outputs") or []
    if not isinstance(outputs, list):
        outputs = []

    fm = SkillFrontmatter(
        name=name.strip(),
        description=description.strip(),
        runtime=runtime,
        acpx_agent=acpx_agent,
        requires_tools=_coerce_str_list(tla.get("requires_tools")),
        requires_mcps=_coerce_str_list(tla.get("requires_mcps")),
        max_iterations=int(budget.get("max_iterations", 12) or 12),
        max_seconds=float(budget.get("max_seconds", 180) or 180),
        max_tokens=int(budget.get("max_tokens", 30_000) or 30_000),
        permissions=permissions,
        inputs=[d for d in inputs if isinstance(d, dict)],
        outputs=[d for d in outputs if isinstance(d, dict)],
        triggers_keywords=_coerce_str_list(triggers.get("keywords")),
        triggers_file_globs=_coerce_str_list(triggers.get("file_globs")),
        raw=fm_dict,
    )
    body = m.group("body").strip()
    return fm, body


def hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def find_skill_files(root: Path) -> List[Path]:
    """Find every SKILL.md under `root`."""
    if not root.exists():
        return []
    return sorted(root.rglob("SKILL.md"))
