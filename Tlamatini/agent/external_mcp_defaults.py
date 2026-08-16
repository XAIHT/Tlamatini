# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Default External MCP servers — shipped with EVERY installation, INACTIVE.

WHAT AND WHY
------------
Two servers from the official ``@modelcontextprotocol`` reference suite are now
part of Tlamatini out of the box (Angela's directive, 2026-08-15):

  * ``memory``               — a persistent knowledge-graph store (9 tools).
                               Gives Tlamatini durable, cross-session memory of
                               entities, relations and observations.
  * ``sequential-thinking``  — structured step-by-step reasoning with branching
                               and revision (1 tool).

Both are declared here, in CODE, rather than only in the shipped
``external_mcps.json``. That is deliberate and load-bearing:

  * ``external_mcps.json`` is USER STATE — ``apply_update.ps1`` PRESERVES it
    across a self-update. A user who updates from an older build keeps their own
    catalog file, so a new default written only into the shipped JSON would
    reach fresh installs and NOBODY ELSE. Seeding from code at every boot
    reaches everyone, forever.
  * The catalog holds provider secrets, so ``build.py`` deliberately never ships
    the dev machine's copy. Code is the only carrier that is both universal and
    safe.

BOTH ARE SEEDED **INACTIVE**. ``seed_defaults`` never touches the ``active``
list: activating a server spawns a child process and consumes one of the five
slots, and that is the user's decision, never ours.

THE TOMBSTONE CONTRACT (do NOT weaken)
--------------------------------------
If the user DELETES a default server, it must STAY deleted. A seeder that
re-adds it on the next launch is not "helpful", it is a bug that makes the
Remove button look broken. So ``remove_servers`` records the key in
``_removed_defaults`` and the seeder skips anything listed there. Re-importing
the server explicitly (the dialog, ``external_mcp_import``) clears its
tombstone, because that is an unambiguous "I want it back".

Equally, a default the user has EDITED is never overwritten: the seeder only
ever ADDS a key that is absent. Their edit is the truth.
"""

import copy
import os
import sys
from typing import Any, Dict, List, Tuple

#: Catalog key that records defaults the user deliberately removed.
TOMBSTONE_KEY = "_removed_defaults"

#: Marker stamped on a seeded server so the UI can badge it and so tests can
#: tell a shipped default from a user's own entry.
DEFAULT_MARKER = "_tlamatini_default"


def memory_store_path() -> str:
    """Where the ``memory`` server keeps its knowledge graph.

    Under ``%LOCALAPPDATA%\\Tlamatini\\memory`` — NOT the install directory,
    because a self-update replaces that wholesale and Angela's memories must
    outlive every update, every reinstall, and an install under Program Files
    that a non-admin user cannot write to.
    """
    override = (os.environ.get("TLAMATINI_MEMORY_FILE") or "").strip()
    if override:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(override)))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "memory", "memory.json")


def _ensure_memory_dir() -> None:
    try:
        os.makedirs(os.path.dirname(memory_store_path()), exist_ok=True)
    except Exception:
        pass


def default_servers() -> Dict[str, Dict[str, Any]]:
    """The catalog entries to seed, with runtime-resolved paths filled in.

    ``command`` is the BARE manager name on purpose. ``_StdioMcpClient`` routes
    every spawn through ``runtime_provisioner.resolve_spawn``, which rewrites
    ``npx`` to ``node.exe <npx-cli.js>`` from Tlamatini's private runtime (or
    the user's own Node when they have one). Hard-coding a path here would
    freeze one machine's layout into the catalog and break on the next update.
    """
    return {
        "memory": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"MEMORY_FILE_PATH": memory_store_path()},
            "transport": "stdio",
            "description": (
                "Persistent knowledge graph — durable, cross-session memory of entities, "
                "relations and observations. Official @modelcontextprotocol reference server. "
                "Needs Node (Tlamatini provisions it automatically)."
            ),
            DEFAULT_MARKER: True,
        },
        "sequential-thinking": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
            "env": {},
            "transport": "stdio",
            "description": (
                "Structured step-by-step reasoning with branching and revision. Official "
                "@modelcontextprotocol reference server. Needs Node (Tlamatini provisions "
                "it automatically)."
            ),
            DEFAULT_MARKER: True,
        },
    }


def default_keys() -> List[str]:
    return sorted(default_servers().keys())


def _tombstones(catalog: Dict[str, Any]) -> List[str]:
    raw = catalog.get(TOMBSTONE_KEY)
    return [str(k) for k in raw] if isinstance(raw, list) else []


def seed_defaults(catalog: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Merge the defaults into ``catalog`` in place. Returns ``(catalog, added)``.

    Rules, in order:
      * a key the user REMOVED (tombstoned) is skipped — it stays removed;
      * a key that already EXISTS is left untouched — their edit wins;
      * anything else is added, INACTIVE.

    Totally defensive: a malformed catalog is repaired rather than rejected, and
    nothing here may raise into the caller.
    """
    added: List[str] = []
    try:
        if not isinstance(catalog, dict):
            catalog = {}
        servers = catalog.get("mcpServers")
        if not isinstance(servers, dict):
            servers = {}
            catalog["mcpServers"] = servers
        if not isinstance(catalog.get("active"), list):
            catalog["active"] = []

        removed = set(_tombstones(catalog))
        for key, spec in default_servers().items():
            if key in servers or key in removed:
                continue
            servers[key] = copy.deepcopy(spec)
            added.append(key)
        if added and "memory" in added:
            _ensure_memory_dir()
    except Exception:
        return catalog if isinstance(catalog, dict) else {}, []
    return catalog, added


def record_removal(catalog: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """Tombstone any DEFAULT key the user just removed, so it is not re-seeded."""
    try:
        defaults = set(default_servers().keys())
        touched = [str(k) for k in (keys or []) if str(k) in defaults]
        if not touched:
            return catalog
        existing = _tombstones(catalog)
        catalog[TOMBSTONE_KEY] = sorted(set(existing) | set(touched))
    except Exception:
        pass
    return catalog


def clear_tombstones(catalog: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """Forget the tombstones for ``keys`` — an explicit re-import means the user
    wants that server back, and it must survive the next boot's seeding pass."""
    try:
        existing = set(_tombstones(catalog))
        if not existing:
            return catalog
        remaining = sorted(existing - {str(k) for k in (keys or [])})
        if remaining:
            catalog[TOMBSTONE_KEY] = remaining
        else:
            catalog.pop(TOMBSTONE_KEY, None)
    except Exception:
        pass
    return catalog


def is_default(key: str) -> bool:
    return str(key) in default_servers()


def shipped_catalog_document() -> Dict[str, Any]:
    """The exact JSON ``build.py`` writes into a fresh install.

    Kept HERE so the shipped file and the boot-time seeder can never drift into
    disagreeing about what a default is. ``build.py`` imports this.
    """
    servers = default_servers()
    # A fresh install must not bake THIS machine's LOCALAPPDATA into the file:
    # leave the memory path as an expandable token that the seeder/env resolve
    # per-user at first use.
    servers["memory"]["env"]["MEMORY_FILE_PATH"] = os.path.join(
        "%LOCALAPPDATA%" if os.name == "nt" else "$HOME/.local/share",
        "Tlamatini", "memory", "memory.json",
    )
    return {
        "_README": (
            "Tlamatini External MCP catalog. Add servers in the standard `mcpServers` "
            "shape (the same JSON a Claude Code .mcp.json uses), then tick up to 5 of "
            "them in External > MCPs to activate. The two servers below ship with every "
            "installation and start INACTIVE — tick one to switch it on. Tlamatini "
            "provisions Node/npx (and uv/uvx) automatically the first time one is "
            "needed, so no manual install is required. This file is USER STATE: it "
            "lives next to config.json and is preserved across updates AND reinstalls. "
            "It holds provider secrets in its `env` blocks, so it is never shipped with "
            "a maintainer's servers in it and must never be committed to a public repo."
        ),
        "mcpServers": servers,
        "active": [],
    }


def main() -> int:
    """``python -m agent.external_mcp_defaults`` — print what would be seeded."""
    import json
    print(json.dumps(shipped_catalog_document(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
