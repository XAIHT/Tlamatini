"""
Django-side ACPX service — registers the runtime at startup and mirrors
disk state into the AcpAgent table.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def boot_acpx() -> None:
    """
    Called from agent.apps.AgentConfig.ready(). Constructs the runtime
    singleton, runs the initial probe, and best-effort mirrors the agent
    registry into the database. Never blocks Django startup; logs
    exceptions and continues.

    Also ensures the user-editable `config.json` has an `acpx` block —
    appending the documented defaults to legacy files so an upgrade is
    self-healing in both source and frozen modes.
    """
    try:
        from .config import ensure_acpx_block_in_config_json
        rewrote = ensure_acpx_block_in_config_json()
        if rewrote:
            logger.info("[ACPX] backfilled documented 'acpx' block in config.json")
    except Exception:
        logger.exception("[ACPX] config.json backfill failed (non-fatal)")
    try:
        from .runtime import get_acpx_runtime
        runtime = get_acpx_runtime()
        runtime.probe_availability()
        try:
            from agent.models import AcpAgent
            existing = {a.agent_id: a for a in AcpAgent.objects.all()}
            seen: set[str] = set()
            for entry in runtime.list_agents():
                seen.add(entry["agent_id"])
                row, created = AcpAgent.objects.get_or_create(
                    agent_id=entry["agent_id"],
                    defaults={
                        "command": entry["command"],
                        "description": entry["description"],
                        "enabled": True,
                        "healthy": entry["resolvable"],
                    },
                )
                row.command = entry["command"]
                row.description = entry["description"]
                row.healthy = entry["resolvable"]
                row.save()
            for agent_id, row in existing.items():
                if agent_id not in seen:
                    row.delete()
            logger.info("[ACPX] mirrored %d agents into AcpAgent table",
                        len(seen))
        except Exception:
            logger.exception("[ACPX] AcpAgent mirroring failed (non-fatal)")
    except Exception:
        logger.exception("[ACPX] boot failed (non-fatal)")


def boot_skills() -> None:
    """
    Build the skill registry and mirror it into the Skill table.
    Never blocks Django startup.
    """
    try:
        from agent.skills.registry import skill_registry
        skill_registry.reload()
        try:
            from agent.models import Skill as SkillRow
            existing = {s.name: s for s in SkillRow.objects.all()}
            seen: set[str] = set()
            for skill in skill_registry.all():
                seen.add(skill.name)
                row, _ = SkillRow.objects.get_or_create(
                    name=skill.name,
                    defaults={
                        "description": skill.description,
                        "runtime": skill.runtime,
                        "acpx_agent": skill.acpx_agent or "",
                        "enabled": True,
                        "frontmatter_json": skill.frontmatter_json,
                        "body_sha256": skill.body_sha256,
                    },
                )
                row.description = skill.description
                row.runtime = skill.runtime
                row.acpx_agent = skill.acpx_agent or ""
                row.frontmatter_json = skill.frontmatter_json
                row.body_sha256 = skill.body_sha256
                row.save()
            for name, row in existing.items():
                if name not in seen:
                    row.delete()
            logger.info("[ACPX] mirrored %d skills into Skill table",
                        len(seen))
        except Exception:
            logger.exception("[ACPX] Skill mirroring failed (non-fatal)")
    except Exception:
        logger.exception("[ACPX] skill registry boot failed (non-fatal)")
