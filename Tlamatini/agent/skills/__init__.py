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
