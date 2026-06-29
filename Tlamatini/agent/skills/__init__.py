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
Tlamatini skills package — runtime side.

Skill *content* (the SKILL.md packages) lives under:
    agent/skills_pkg/<skill_dir>/SKILL.md
                                 [optional scripts/, references/, assets/]

This package contains the *runtime*: parser, registry, harness, output
contract validator, and audit log.
"""
from .registry import skill_registry, Skill
from .harness import SkillHarness, SkillRuntimeError, BudgetExceeded

__all__ = [
    "skill_registry",
    "Skill",
    "SkillHarness",
    "SkillRuntimeError",
    "BudgetExceeded",
]
