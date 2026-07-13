<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — Companion-App Discovery Contract

A stable lookup surface that lets XAIHT **companion apps** (e.g. **Tlamatini-FlowPills**)
find Tlamatini's agent-template catalog **without importing Python, running Tlamatini,
or scanning drives**. This is the Tlamatini side of `Tlamatini-FlowPills-Lookup.md`
§15 — PROP-001 … PROP-004 — plus the second-sprint hardening in
`Tlamatini-FlowPills-Lookup-2nd-Sprint.md`.

## What Tlamatini publishes

### 1. Registry key — `HKCU\Software\XAIHT\Tlamatini` (PROP-001)

Per-user, **no admin**. Values (all `REG_SZ`):

| Value | Meaning |
|---|---|
| `InstallLocation` | Base dir: the folder containing `Tlamatini.exe` when frozen; in **source** mode `agent_paths.get_app_base_dir()` (currently the Django **agent app** directory, `<repo>\Tlamatini\agent`). Diagnostic only — a companion app must use `AgentsRoot` as the exact path and must NOT derive correctness from source-mode `InstallLocation`. |
| `AgentsRoot` | The **exact** agents root — read this FIRST |
| `SourceAgentsRoot` | Source-style agents root (empty when frozen) |
| `AgentManifestPath` | Full path to the agents manifest (below) |
| `Version` | Tlamatini SemVer (`agent/version.py`) |
| `AgentCatalogVersion` | `<count>-<sha8>` — a NAME-SET id that changes only when the agent SET changes (diagnostic) |

**ALL SIX values are (re)written on every successful registration** — an empty string
when a value is unknown — so no stale `Version` / `AgentCatalogVersion` from a previous
install or source root can ever survive (REQ-S2-REG-001). Written by `install.py` at
install time (in its OWN fail-open method, independent of the ARP entry), and refreshed
by `agent_manifest.publish_discovery()` on **every app launch** — so a source checkout
that has merely been run once is discoverable too.

### 2. Agents manifest — `<agents_root>\_tlamatini_agents_manifest.json` (PROP-002)

Machine-readable catalog: `product`, `manifest_version`, `agent_catalog_version`,
`agent_count`, `agents_root_kind` (`installed` | `source` | `preserved`), `version`,
`generated_at`, and `agents[]` — each `{ type, script, config, sha256:{script,config} }`.
Only **complete** templates (`<type>.py` **and** `config.yaml`) are listed; `pools` and
`__pycache__` are excluded (mirrors FlowPills REQ-VAL-003). Generated at build time
(`build.py`, shipped inside the install) and refreshed on launch — **every complete agent
file body is hashed on each background check**, and the manifest is **rewritten only when
meaningful content differs** (the volatile `generated_at` alone never rewrites). So an
edit to ANY agent file refreshes its `sha256`, yet a healthy manifest is never churned and
the per-launch self-heal never stalls startup. `read_manifest()` reads with `utf-8-sig`, so
a manifest written WITH a BOM still parses. `agent_catalog_version` stays a NAME-SET id;
the per-file `sha256` values represent CONTENT.

> Filesystem is authoritative (FlowPills REQ-VAL-008): the manifest is discovery/diagnostic
> evidence only. A stale, missing, or count-mismatched manifest can neither make an
> incomplete root pass nor make a filesystem-valid root fail. Tlamatini's job is only to keep
> the manifest *accurate*.

### 3. Preserved-agents marker — `<install>\agents\.tlamatini-preserved-agents.json` (PROP-003)

Left by `uninstall.py` when it preserves `agents/`: `original_install_path`,
`uninstalled_at`, `version`, `agent_count`, `agent_catalog_version`, `manifest_path`,
**`manifest_sha256`** (a SHA-256 of the manifest computed AFTER it is re-stamped
`preserved`), and a human `note`. The manifest's `agents_root_kind` is re-stamped to
`preserved`. An agents-**preserving** uninstall intentionally **KEEPS the discovery
registry key** (its `AgentsRoot` still points at the preserved agents), so a companion app
keeps finding them after uninstall (FlowPills AC-002). Only an explicit FULL removal would
call `unregister_discovery_entry()`.

## Recommended companion-app lookup sequence (PROP-004)

1. Read `HKCU\Software\XAIHT\Tlamatini\AgentsRoot`.
2. Validate `_tlamatini_agents_manifest.json` there (`agent_count` ≥ your threshold;
   optionally verify the `sha256` entries) — but count complete templates from the
   filesystem as the authority.
3. Fall back to HKCU Installed-Apps (`…\Uninstall\Tlamatini\InstallLocation`) and the
   `.flw` association keys.
4. Fall back to a source checkout and preserved-agent probes.

The current **Tlamatini-FlowPills** already CONSUMES this contract: it reads
`HKCU\Software\XAIHT\Tlamatini` and the root-local manifest metadata **before** its legacy
Installed-Apps / `.flw`-association / executable-relative fallbacks — while FILESYSTEM
counting stays the startup authority. So these surfaces make the registry path first-class
(discovery is fast and unambiguous when Tlamatini is present), and every earlier fallback
still works when it isn't.

## Contract (do NOT weaken)

- **HKCU only, never admin.** Every writer is **fail-open**: a registry or filesystem
  hiccup must never crash Django startup, the installer, or the uninstaller.
- **Read-only w.r.t. Tlamatini** except our OWN manifest file and our OWN registry key —
  never touch Tlamatini agents, other files, or other registry keys.
- **No full-drive scans.** The per-launch self-heal hashes only the small agent files (off
  the hot path) and rewrites the manifest solely when content changed.
- **Import-independent, idempotent publication.** Launch-time discovery is scheduled FIRST
  in `AgentConfig.ready()`, before any optional runtime subsystem is imported, on its own
  daemon thread with a dedicated idempotency gate (separate from `mcp_server_running`), so
  an MCP / models / ACPX / skills import or startup failure can never prevent publication.
- **Six values always written** (empty when unknown) — no stale metadata survives.

## Files

| Concern | Code |
|---|---|
| Manifest + `publish_discovery` + freshness | `Tlamatini/agent/agent_manifest.py` |
| Registry key writer / remover (six values) | `Tlamatini/agent/windows_app_registration.py` — `register_discovery_entry` / `unregister_discovery_entry` |
| Launch-time publish (all modes, import-independent) | `Tlamatini/agent/apps.py` — `_schedule_companion_discovery` (called FIRST in `AgentConfig.ready()`) + the `_discovery_publish_eligible` predicate + the `_DISCOVERY_GATE_LOCK` / `_discovery_thread_started` gate |
| Install-time key (independent of ARP) | `install.py` — `_register_companion_discovery` |
| Uninstall preserved marker (+ `manifest_sha256`) | `uninstall.py` — `_write_preserved_agents_marker` |
| Build-time manifest | `build.py` — right after the `agents` copy |
| Tests | `Tlamatini/agent/test_agent_manifest.py` |

> Requirement sources of truth: `Tlamatini-FlowPills-Lookup.md` and
> `Tlamatini-FlowPills-Lookup-2nd-Sprint.md` (both under
> `C:\Users\angel\source\repos\Tlamatini-FlowPills\`).
