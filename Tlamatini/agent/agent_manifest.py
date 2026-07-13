# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Companion-app discovery: the agents manifest + the HKCU discovery key.

This is the Tlamatini side of the **Tlamatini-FlowPills** lookup contract
(PROP-001, PROP-002, PROP-004 of ``Tlamatini-FlowPills-Lookup.md``). It lets XAIHT
companion apps find Tlamatini's agent-template catalog without importing Python,
running Tlamatini, or scanning drives:

  * ``_tlamatini_agents_manifest.json`` — a machine-readable list of the complete
    agent templates (``<type>.py`` + ``config.yaml``) written next to the agents.
  * ``HKCU\\Software\\XAIHT\\Tlamatini`` — a per-user registry key pointing at the
    agents root + manifest (written by ``windows_app_registration``).

CONTRACT (do NOT weaken):
  * Read-only with respect to Tlamatini EXCEPT our own manifest file and our own
    registry key — never touch Tlamatini agents, other Tlamatini files, or other
    registry keys.
  * HKCU only, never admin. Every public function is **fail-open** (never raises).
  * Content-aware freshness (REQ-S2-MAN-002): ``ensure_manifest`` re-hashes EVERY
    complete agent file body (``<type>.py`` + ``config.yaml``) on each background
    check and REWRITES the manifest only when meaningful content differs (the
    volatile ``generated_at`` alone never triggers a rewrite). The files are small
    and this runs off the hot path, so the per-launch self-heal does not stall
    startup.
  * No Django dependency — safe to import from ``build.py`` and early startup.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "_tlamatini_agents_manifest.json"
PRESERVED_MARKER_FILENAME = ".tlamatini-preserved-agents.json"
MANIFEST_VERSION = 1
PRODUCT = "Tlamatini"

# Directories that live under an agents root but are NOT agent templates and must
# never be counted (mirrors FlowPills REQ-VAL-003).
_NON_AGENT_DIRS = {"pools", "__pycache__"}


def iter_complete_agents(agents_root: str) -> Iterator[Tuple[str, str, str]]:
    """Yield ``(agent_type, script_name, config_name)`` for every COMPLETE template.

    A template is complete when both ``<type>.py`` and ``config.yaml`` exist as
    direct children of ``<agents_root>/<type>/``. ``pools`` / ``__pycache__`` are
    skipped. Yielded in sorted order for a deterministic manifest.
    """
    try:
        entries = sorted(os.listdir(agents_root))
    except OSError:
        return
    for name in entries:
        if name in _NON_AGENT_DIRS:
            continue
        sub = os.path.join(agents_root, name)
        if not os.path.isdir(sub):
            continue
        script = name + ".py"
        has_script = os.path.isfile(os.path.join(sub, script))
        has_config = os.path.isfile(os.path.join(sub, "config.yaml"))
        if has_script and has_config:
            yield name, script, "config.yaml"


def count_complete_agents(agents_root: str) -> int:
    """Number of complete agent templates directly under ``agents_root``."""
    return sum(1 for _ in iter_complete_agents(agents_root))


def compute_agent_catalog_version(agents_root: str) -> str:
    """A stable, content-derived catalog id: ``<count>-<sha8-of-sorted-types>``.

    Changes only when the SET of complete agent types changes, so a companion app
    can cheaply detect catalog drift without hashing file bodies. It is a NAME-SET
    identifier only — per-file ``sha256`` values in the manifest represent file
    CONTENT, and ``ensure_manifest`` re-hashes those on every check (REQ-S2-MAN-002).
    """
    types = [t for t, _, _ in iter_complete_agents(agents_root)]
    if not types:
        return "0-00000000"
    digest = hashlib.sha256("\n".join(types).encode("utf-8")).hexdigest()[:8]
    return f"{len(types)}-{digest}"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(
    agents_root: str,
    *,
    kind: str = "installed",
    version: str = "",
    with_sha256: bool = True,
) -> dict:
    """Build the manifest dict for ``agents_root`` (does not write anything)."""
    agents = []
    for agent_type, script, config in iter_complete_agents(agents_root):
        entry: dict = {"type": agent_type, "script": script, "config": config}
        if with_sha256:
            try:
                entry["sha256"] = {
                    "script": _sha256_file(os.path.join(agents_root, agent_type, script)),
                    "config": _sha256_file(os.path.join(agents_root, agent_type, config)),
                }
            except OSError:
                pass
        agents.append(entry)
    return {
        "product": PRODUCT,
        "manifest_version": MANIFEST_VERSION,
        "agent_catalog_version": compute_agent_catalog_version(agents_root),
        "agent_count": len(agents),
        "agents_root_kind": kind,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agents": agents,
    }


def _write_manifest_dict(manifest: dict, path: str) -> Optional[str]:
    """Atomically write a manifest dict to ``path``. Fail-open (``None`` on error)."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        os.replace(tmp, path)
        return path
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[agent_manifest] manifest write failed: %s", exc)
        return None


def write_manifest(
    agents_root: str,
    *,
    kind: str = "installed",
    version: str = "",
    with_sha256: bool = True,
) -> Optional[str]:
    """Build + write ``_tlamatini_agents_manifest.json`` into ``agents_root`` (atomic).

    Returns the manifest path on success, ``None`` on any failure (fail-open — a
    read-only agents root simply yields ``None``). Writes ONLY our own manifest.
    """
    try:
        if not os.path.isdir(agents_root):
            return None
        manifest = build_manifest(
            agents_root, kind=kind, version=version, with_sha256=with_sha256
        )
        return _write_manifest_dict(manifest, os.path.join(agents_root, MANIFEST_FILENAME))
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[agent_manifest] write_manifest failed: %s", exc)
        return None


def read_manifest(agents_root: str) -> Optional[dict]:
    """Load an existing manifest dict, or ``None`` if absent/unreadable."""
    try:
        path = os.path.join(agents_root, MANIFEST_FILENAME)
        # utf-8-sig so a manifest written WITH a BOM still parses (REQ-S2-MAN-001);
        # plain UTF-8 is a strict subset, so BOM-less files are unaffected.
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _manifest_content_equal(a: dict, b: dict) -> bool:
    """True if two manifests are equal ignoring the volatile ``generated_at`` field."""
    return {k: v for k, v in a.items() if k != "generated_at"} == {
        k: v for k, v in b.items() if k != "generated_at"
    }


def ensure_manifest(
    agents_root: str, *, kind: str = "installed", version: str = ""
) -> Optional[str]:
    """Ensure the manifest reflects the CURRENT agent files — their CONTENTS, count,
    kind, and version — not merely the SET of agent names.

    Rebuilds (re-hashes every ``<type>.py`` + ``config.yaml``) on each call; the agent
    files are small and this runs on a background thread, so the cost is negligible.
    It only REWRITES the file when the rebuilt manifest differs from the on-disk one
    (ignoring the volatile ``generated_at``), so a healthy manifest is never churned.
    This catches the staleness cases a name-set-only check misses: an edit to an
    existing agent file (its ``sha256`` changes), a Tlamatini version bump, and a
    change of ``agents_root_kind``. Returns the manifest path or ``None`` (fail-open).
    """
    try:
        if not os.path.isdir(agents_root):
            return None
        path = os.path.join(agents_root, MANIFEST_FILENAME)
        fresh = build_manifest(agents_root, kind=kind, version=version)
        existing = read_manifest(agents_root)
        if (
            existing is not None
            and os.path.isfile(path)
            and _manifest_content_equal(existing, fresh)
        ):
            return path
        return _write_manifest_dict(fresh, path)
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[agent_manifest] ensure_manifest failed: %s", exc)
        return None


def publish_discovery(version: str = "") -> Optional[str]:
    """Ensure the agents manifest AND publish the ``HKCU\\Software\\XAIHT\\Tlamatini``
    discovery key for the current runtime mode (installed vs source).

    Called from ``apps.AgentConfig.ready()`` on a background thread, so it works for
    a normal install AND for a source checkout that has merely been run once — either
    way a companion app (Tlamatini-FlowPills) can then find the agents via the
    registry. Fail-open; returns the manifest path (or ``None``).
    """
    try:
        from .services import agent_paths

        agents_root = str(agent_paths.get_agents_root())
        if not os.path.isdir(agents_root):
            return None
        frozen = agent_paths.is_frozen_mode()
        kind = "installed" if frozen else "source"
        manifest_path = ensure_manifest(agents_root, kind=kind, version=version) or ""
        try:
            from . import windows_app_registration

            windows_app_registration.register_discovery_entry(
                install_location=str(agent_paths.get_app_base_dir()),
                agents_root=agents_root,
                source_agents_root="" if frozen else agents_root,
                agent_manifest_path=manifest_path,
                version=version,
                agent_catalog_version=compute_agent_catalog_version(agents_root),
            )
        except Exception as exc:  # noqa: BLE001 — fail-open
            logger.warning("[agent_manifest] discovery registry write failed: %s", exc)
        return manifest_path or None
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("[agent_manifest] publish_discovery failed: %s", exc)
        return None


__all__ = [
    "MANIFEST_FILENAME",
    "PRESERVED_MARKER_FILENAME",
    "iter_complete_agents",
    "count_complete_agents",
    "compute_agent_catalog_version",
    "build_manifest",
    "write_manifest",
    "read_manifest",
    "ensure_manifest",
    "publish_discovery",
]
