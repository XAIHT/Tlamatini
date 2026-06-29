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
Skill registry — discovers, parses, and caches all SKILL.md packages.

Discovery rules
---------------
- The registry scans agent/skills_pkg/<dir>/SKILL.md by default.
- Subdirectories are allowed; the SKILL.md filename is exact.
- A skill's `name` must match its directory's leaf name OR be specified
  explicitly in the frontmatter (the frontmatter's name wins).
- Dirs whose SKILL.md fails to parse are skipped with a warning, not an
  exception — we never block startup over a bad skill.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .frontmatter import (
    SkillParseError,
    find_skill_files,
    hash_body,
    parse_skill_md,
)

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A loaded skill — frontmatter + body + path metadata."""
    name: str
    description: str
    runtime: str
    acpx_agent: str
    requires_tools: List[str]
    requires_mcps: List[str]
    max_iterations: int
    max_seconds: float
    max_tokens: int
    permissions: Dict[str, Any]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    triggers_keywords: List[str]
    triggers_file_globs: List[str]
    body: str
    body_sha256: str
    skill_dir: Path
    skill_md_path: Path
    frontmatter_json: str
    last_loaded_at: float

    def summary(self) -> Dict[str, Any]:
        """Tier-1 surface: name + description + runtime."""
        return {
            "name": self.name,
            "description": self.description,
            "runtime": self.runtime,
            "acpx_agent": self.acpx_agent or None,
        }

    def planner_record(self) -> Dict[str, Any]:
        """Tier-2 surface: frontmatter + first 200 chars of body."""
        return {
            **self.summary(),
            "triggers_keywords": list(self.triggers_keywords),
            "triggers_file_globs": list(self.triggers_file_globs),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "body_preview": self.body[:200],
        }


class SkillRegistry:
    def __init__(self, roots: Optional[List[Path]] = None,
                 stale_seconds: float = 30.0):
        self._roots: List[Path] = roots or self._default_roots()
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.Lock()
        self._loaded_once = False
        self._last_load_at: float = 0.0
        self._stale_seconds = stale_seconds

    @staticmethod
    def _default_roots() -> List[Path]:
        # The skill *content* lives in agent/skills_pkg/ (note: distinct from
        # this runtime package, which is agent/skills/). Keeping them apart
        # avoids a name collision between the python package and the
        # skill-content directory.
        #
        # Three possible locations, tried in order (first existing wins):
        #
        #   1. <install-dir>/agent/skills_pkg/   — frozen post-build copy
        #      (build.py optional_dir_copies). User-editable.
        #   2. <bundle>/agent/skills_pkg/        — frozen PyInstaller bundle
        #      (build.py --add-data). Read-only fallback.
        #   3. <source>/Tlamatini/agent/skills_pkg/  — source mode.
        #
        # Returning all three lets the registry merge them (if both exist,
        # the install-dir copy shadows the bundled one because directory
        # iteration order tends to put it first; duplicate names resolve
        # by the SkillRegistry's "later wins" map insertion).
        import sys
        roots: List[Path] = []
        here = Path(__file__).resolve().parent
        # Source mode (development) — agent/skills/ -> agent/skills_pkg/
        source_root = here.parent / "skills_pkg"
        # Frozen post-build install dir
        if getattr(sys, "frozen", False):
            install_root = Path(sys.executable).parent / "agent" / "skills_pkg"
            if install_root.exists():
                roots.append(install_root)
            # PyInstaller's _MEIPASS bundles _add-data_ payloads here.
            mei = getattr(sys, "_MEIPASS", None)
            if mei:
                bundled = Path(mei) / "agent" / "skills_pkg"
                if bundled.exists():
                    roots.append(bundled)
        if source_root.exists():
            roots.append(source_root)
        # Always include the canonical source path as a final fallback so
        # tests and tooling that import this module from a sibling tree
        # still find the catalog.
        if not roots:
            roots.append(source_root)
        return roots

    # ── Loading ─────────────────────────────────────────────────────
    def reload(self) -> None:
        with self._lock:
            self._reload_locked()

    def reload_if_stale(self) -> None:
        if not self._loaded_once:
            self.reload()
            return
        if time.time() - self._last_load_at > self._stale_seconds:
            self.reload()

    def _reload_locked(self) -> None:
        new_skills: Dict[str, Skill] = {}
        for root in self._roots:
            for path in find_skill_files(root):
                try:
                    text = path.read_text(encoding="utf-8")
                    fm, body = parse_skill_md(text, source_label=str(path))
                    skill = Skill(
                        name=fm.name,
                        description=fm.description,
                        runtime=fm.runtime,
                        acpx_agent=fm.acpx_agent,
                        requires_tools=fm.requires_tools,
                        requires_mcps=fm.requires_mcps,
                        max_iterations=fm.max_iterations,
                        max_seconds=fm.max_seconds,
                        max_tokens=fm.max_tokens,
                        permissions=fm.permissions,
                        inputs=fm.inputs,
                        outputs=fm.outputs,
                        triggers_keywords=fm.triggers_keywords,
                        triggers_file_globs=fm.triggers_file_globs,
                        body=body,
                        body_sha256=hash_body(body),
                        skill_dir=path.parent,
                        skill_md_path=path,
                        frontmatter_json=json.dumps(fm.raw, ensure_ascii=False),
                        last_loaded_at=time.time(),
                    )
                    new_skills[skill.name] = skill
                except SkillParseError as e:
                    logger.warning("[skills] skipping malformed %s: %s", path, e)
                except Exception as e:
                    logger.warning("[skills] error loading %s: %s", path, e)
        self._skills = new_skills
        self._loaded_once = True
        self._last_load_at = time.time()
        logger.info("[skills] reload: %d skills loaded", len(new_skills))

    # ── Query ───────────────────────────────────────────────────────
    def all(self) -> List[Skill]:
        self.reload_if_stale()
        return list(self._skills.values())

    def get(self, name: str) -> Optional[Skill]:
        self.reload_if_stale()
        return self._skills.get(name)

    def list(self, filter_keywords: str = "") -> List[Dict[str, Any]]:
        self.reload_if_stale()
        kw = [k.strip().lower() for k in (filter_keywords or "").split() if k.strip()]
        out: List[Dict[str, Any]] = []
        for s in self._skills.values():
            if not kw:
                out.append(s.summary())
                continue
            hay = (s.name + " " + s.description + " " +
                   " ".join(s.triggers_keywords)).lower()
            if all(k in hay for k in kw):
                out.append(s.summary())
        return out

    def planner_records(self) -> List[Dict[str, Any]]:
        """Used by global_execution_planner to score skills against a request."""
        self.reload_if_stale()
        return [s.planner_record() for s in self._skills.values()]


# Singleton — imported as `from agent.skills.registry import skill_registry`
skill_registry = SkillRegistry()
