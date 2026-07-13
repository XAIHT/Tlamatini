# Tlamatini — Modifications for Tlamatini-FlowPills (companion-app discovery)

**Audience:** Codex (and any future reviewer) — a precise, byte-accurate record of exactly what
was changed on the **Tlamatini** side to satisfy the companion-app discovery contract that the
**Tlamatini-FlowPills** app consumes.

**Date:** 2026-07-12
**Tlamatini version at time of change:** `1.39.5` (git tag `v1.39.5`)
**Source contract:** `C:\Users\angel\source\repos\Tlamatini-FlowPills\Tlamatini-FlowPills-Lookup.md`
— specifically §4 (Source Evidence), §7 REQ-DISC-003, §8 REQ-VAL-007/008/009, and §15 PROP-001…004.

> **Git status:** NOTHING in this work has been committed or pushed. Every change below is
> uncommitted in the working tree, awaiting Angela's explicit OK. History was not rewritten.

> **Second sprint (2026-07-12):** §2 below describes sprint-1. It was hardened in a second
> sprint per `Tlamatini-FlowPills-Lookup-2nd-Sprint.md` — see **§7. Second-Sprint Amendments**
> at the end, which supersedes any sprint-1 detail it revises (import-independent scheduling
> with a dedicated gate, an INDEPENDENT installer method, always-six-values, and `utf-8-sig`
> reads). Go by SYMBOL NAME, not the §2 line numbers, which are now stale.

---

## 1. What FlowPills needs, and what Tlamatini now publishes

FlowPills must locate Tlamatini's agent-template catalog at startup **without importing Python,
running Tlamatini, or scanning drives**. To make that possible, Tlamatini now publishes three
read-only, **HKCU-only, fail-open** surfaces plus a docs contract:

| # | Surface | Path / key | FlowPills req |
|---|---|---|---|
| 1 | Discovery registry key | `HKCU\Software\XAIHT\Tlamatini` (6 REG_SZ values) | PROP-001 / REQ-DISC-003 |
| 2 | Agents manifest | `<agents_root>\_tlamatini_agents_manifest.json` | PROP-002 / REQ-VAL-007 |
| 3 | Preserved marker | `<install>\agents\.tlamatini-preserved-agents.json` | PROP-003 |
| 4 | Lookup-sequence docs | `docs/companion-app-discovery.md` | PROP-004 |

### Non-negotiable invariants (do NOT weaken)
- **HKCU only, never admin.** Every writer fails open — on any exception it logs and returns,
  never raising into its caller (a Django boot / an installer / an uninstaller must never crash
  because discovery failed).
- **Tlamatini stays read-only w.r.t. itself**, EXCEPT for the two artifacts it owns: its own
  manifest file and its own registry key.
- **The filesystem is authoritative.** The manifest is discovery/diagnostic evidence only; a
  stale/missing/mismatched manifest must never make an agents root pass or fail (REQ-VAL-008).
  Tlamatini's job is only to keep the manifest *accurate*.

---

## 2. Files changed (new + edited), with exact symbols

### 2.1 NEW — `Tlamatini/agent/agent_manifest.py`  (the engine)

Self-contained manifest + discovery engine. Public constants and functions (line numbers as of
this writing):

- Constants:
  - `MANIFEST_FILENAME = "_tlamatini_agents_manifest.json"` (L43)
  - `PRESERVED_MARKER_FILENAME = ".tlamatini-preserved-agents.json"` (L44)
  - `MANIFEST_VERSION = 1` (L45)
  - `PRODUCT = "Tlamatini"` (L46)
  - `_NON_AGENT_DIRS = {"pools", "__pycache__"}` (L50) — matches FlowPills REQ-VAL-003 exclusions.
- Enumeration / counting:
  - `iter_complete_agents(agents_root)` (L53) — yields `(type, script, config)` only for a
    direct child dir that has BOTH `<type>.py` and `config.yaml` (REQ-VAL-002).
  - `count_complete_agents(agents_root)` (L77)
  - `compute_agent_catalog_version(agents_root)` (L82) — returns `f"{count}-{sha8}"` where sha8
    is the first 8 hex of a sha256 over the sorted complete-type names (content-derived, stable).
- Build / read / write:
  - `_sha256_file(path)` (L96)
  - `build_manifest(agents_root, *, kind="installed", version="")` (L104) — returns the manifest
    dict (see schema in §4).
  - `_write_manifest_dict(manifest, path)` (L136) — atomic-ish write, fail-open.
  - `write_manifest(agents_root, *, kind, version)` (L149)
  - `read_manifest(agents_root)` (L173) — utf-8-sig tolerant.
- **Freshness (Codex #1):**
  - `_manifest_content_equal(a, b)` (L184) — compares everything EXCEPT the `generated_at`
    timestamp.
  - `ensure_manifest(agents_root, *, kind="installed", version="")` (L191) — **rebuilds the
    manifest every call** and compares content; rewrites only when content actually differs
    (so `generated_at` does not churn on a no-op, but ANY content change — an edited agent
    script/config, a new/removed agent, a version bump, a kind change — refreshes the file and
    its per-agent sha256).
- Orchestration:
  - `publish_discovery(version="")` (L223) — resolves the live agents root via
    `.services.agent_paths`, calls `ensure_manifest`, then calls
    `windows_app_registration.register_discovery_entry(...)`. Fail-open end to end.

### 2.2 EDITED — `Tlamatini/agent/windows_app_registration.py`

Added the discovery-key writer/remover (the existing `register_uninstall_entry` /
`unregister_uninstall_entry` Installed-Apps code is untouched):

- `XAIHT_DISCOVERY_KEY = r"Software\XAIHT\Tlamatini"` (L199)
- `XAIHT_PARENT_KEY = r"Software\XAIHT"` (L200)
- `register_discovery_entry(*, install_location, agents_root, source_agents_root,
  agent_manifest_path, version, agent_catalog_version)` (L203) — creates
  `HKCU\Software\XAIHT\Tlamatini` and writes exactly these six `REG_SZ` values:
  `InstallLocation`, `AgentsRoot`, `SourceAgentsRoot`, `AgentManifestPath`, `Version`,
  `AgentCatalogVersion` (REQ-DISC-003 names, byte-exact).
- `unregister_discovery_entry()` (L239) — deletes the key and prunes the `XAIHT` **parent only
  if it has no remaining subkeys/values** (never clobbers a sibling XAIHT product).

### 2.3 EDITED — `Tlamatini/agent/apps.py`  (Codex #2 — decoupled from ACPX/MCP)

Discovery publication is now an **INDEPENDENT daemon thread**, launched right after the
`should_start` gate (L51) and the reloader `RUN_MAIN` gate (L72), **before** the MCP-server /
ACPX boot. It no longer rides inside the ACPX boot path, so a failure or slowness in MCP/ACPX
init cannot prevent the key from being published (and vice-versa):

- `_run_discovery_publish()` (L84) → `agent_manifest.publish_discovery(version=get_version())` (L88)
- `threading.Thread(target=_run_discovery_publish, name="DiscoveryPublish", daemon=True).start()`
  (L91–L92), wrapped in try/except so even the *thread launch* is fail-open.

Proven live: a source `runserver` whose MCP init AND DB both errored still published the key with
all six values.

### 2.4 EDITED — `install.py`

> **Superseded by §7 (FIND-S2-002).** In the second sprint the companion-discovery write was
> moved OUT of `_register_programs_entry` into its own independent method
> `_register_companion_discovery(target_dir)`, called separately from the install flow. The
> installer performs its OWN `winreg` writes — it is a standalone frozen exe and cannot import
> `agent.*`, so it never calls `register_discovery_entry`. It reads the **shipped**
> `_tlamatini_agents_manifest.json` (via `utf-8-sig`) to source `AgentCatalogVersion` and writes
> all six values (empty when unknown). Independent of the ARP entry / Uninstaller.exe. Fail-open;
> HKCU-only; no admin.

### 2.5 EDITED — `uninstall.py`  (Codex #3 — preserved-marker checksum)

Class `FancyUninstaller`. When the uninstall **preserves** the top-level `agents/` directory it
now also leaves the machine-readable preserved marker:

- `_write_preserved_agents_marker(self, agents_dir, original_install)` (L659), called from the
  agents-preserve branch (L626).
- It **re-stamps** the root-local manifest's `agents_root_kind` → `"preserved"` (L683–L684) so a
  companion app can tell a preserved root from a live one.
- **Codex #3 fix:** it computes `manifest_sha256` (streamed sha256 of the re-stamped manifest,
  L697–L708) and includes it in the marker dict (L722), satisfying PROP-003's
  "manifest path/checksum" field.
- Marker file written to `<agents_dir>\.tlamatini-preserved-agents.json` (L725). Fields: original
  install path, uninstall timestamp, version, agent count (`_count_complete_agents` staticmethod,
  L732), manifest path + `manifest_sha256`, and a note that binaries were removed but agents
  preserved.
- The discovery **registry key is intentionally KEPT** (not deleted) on an agents-preserving
  uninstall, so companion apps still resolve the preserved agents. `unregister_discovery_entry`
  is only for a full removal.

### 2.6 EDITED — `build.py`

After the `optional_dir_copies` loop that copies `agent/agents` into the frozen dist, the build
**generates the manifest into the dist's agents root** (`kind="installed"`). It loads
`agent_manifest.py` via `importlib.util` (by file path) rather than importing the Django `agent`
package, so the build does not pull Django at packaging time. This is what ships the manifest to
end users; the launch-time `ensure_manifest` (via `apps.py`) then keeps it fresh.

### 2.7 EDITED — `.gitignore`

Added `Tlamatini/agent/agents/_tlamatini_agents_manifest.json` — the **source-mode** manifest is
generated at runtime and must not be tracked (the frozen build regenerates its own).

### 2.8 NEW — `Tlamatini/agent/test_agent_manifest.py`  (Codex #5 — coverage)

10 Django tests, all passing:
- `ManifestGenerationTests` — complete/incomplete detection, `pools`/`__pycache__` exclusion,
  per-agent sha256 shape, catalog-version format.
- `ManifestFreshnessTests` — **`test_content_edit_refreshes_sha256`** (the #1 regression: editing
  an agent file changes the manifest sha256), `test_version_and_kind_changes_refresh`,
  `test_no_change_does_not_churn_generated_at`.
- `DiscoveryRegistryFailOpenTests` — writer never raises on bad input.
- `DiscoveryRegistryLiveTests` — real HKCU round-trip that **backs up and restores** any existing
  real key so the suite never clobbers Angela's live discovery key.
- `PreservedMarkerTests` — imports `uninstall.py`, asserts the marker carries a 64-hex
  `manifest_sha256` and that the manifest kind was re-stamped to `preserved`.

### 2.9 NEW — `docs/companion-app-discovery.md`  (PROP-004)

The documented, stable companion-app lookup sequence + the full Tlamatini-side contract.

### 2.10 EDITED — docs: `CLAUDE.md`, `docs/claude/architecture.md`

A short "Companion-App Discovery" note so future sessions know the surfaces exist and the
invariants that must hold (HKCU-only, fail-open, read-only-except-our-own-artifacts).

---

## 3. Codex review findings — resolution map

| Codex finding | Severity | Resolution | Evidence |
|---|---|---|---|
| Manifest hashes go stale | High | `ensure_manifest` rebuilds + content-compares every call (§2.1) | `test_content_edit_refreshes_sha256` passes |
| Registry publication coupled to ACPX/MCP startup | High | Moved to an independent `DiscoveryPublish` daemon thread before MCP/ACPX boot (§2.3) | Live: key published despite MCP + DB errors |
| Preserved metadata lacks manifest checksum | Medium | `manifest_sha256` added to the preserved marker, computed after the kind re-stamp (§2.5) | `PreservedMarkerTests` passes |
| FlowPills doesn't consume the contract | Medium | Already consumed in current FlowPills source (`TlamatiniLookup.cpp` reads the key before legacy fallbacks); Codex audited an older snapshot | FlowPills `MSBuild Debug|x64` = 0 warnings / 0 errors |
| No automated coverage | Medium | New `test_agent_manifest.py`, 10 tests (§2.8) | All 10 pass |

---

## 4. Manifest schema (verified against the file on disk)

Top-level keys (source-mode file, live):
`product`, `manifest_version`, `version`, `agent_catalog_version`, `agent_count`,
`agents_root_kind`, `agents`, `generated_at`.

Sample values on disk right now:
- `product = "Tlamatini"`
- `manifest_version = 1`
- `version = "1.39.5"`   ← REQ-VAL-007 reads BOTH `version` and `agent_catalog_version`; both present
- `agent_catalog_version = "85-ae39eb35"`   ← `<count>-<sha8>`, diagnostic-only (format is not
  constrained by REQ-VAL-008; richer than the doc's date example)
- `agent_count = 85`
- `agents_root_kind = "source"`   ← one of `installed | source | preserved`

Each `agents[]` entry:
```json
{ "type": "acpxer", "script": "acpxer.py", "config": "config.yaml",
  "sha256": { "script": "48b7…", "config": "ad91…" } }
```

FlowPills' REQ-VAL-007 recognized-schema gate
(`product==Tlamatini` && `manifest_version>=1` && `agent_count>0`) evaluates **True**.

---

## 5. Verification evidence (this session)

- Manifest on disk: 85 agents, both version fields present, per-agent sha256 pair — verified by
  loading the JSON (Tlamatini's Pythonxer).
- HKCU key: all 6 values published live (`InstallLocation`, `AgentsRoot`,
  `SourceAgentsRoot`, `AgentManifestPath`, `Version=1.39.5`, `AgentCatalogVersion=85-ae39eb35`).
- Decoupling proven: key still published when a source server's MCP init and DB both failed.
- `test_agent_manifest.py`: 10/10 pass. `ruff check` + `py_compile` clean on every changed .py.
- FlowPills builds clean and reads the key before legacy fallbacks.

---

## 6. Scope guard — what was deliberately NOT changed

- No change to FlowPills' own `.flw` rendering, deployment, or lookup fallbacks — this is the
  Tlamatini side only.
- No new admin requirement, no HKLM writes, no drive scans.
- No change to how agents run, how flows compile, or any existing installer/uninstaller behavior
  beyond adding the (fail-open) discovery writes.
- The self-update preserve lists were NOT altered by this work; discovery is republished on every
  launch by `apps.py`, so a self-updated install re-publishes automatically.

## 7. Second-Sprint Amendments (Tlamatini-FlowPills-Lookup-2nd-Sprint.md)

Codex's second-sprint review found gaps in the sprint-1 code in §2. All are now fixed; this
section describes the code as it ACTUALLY exists and **supersedes** any sprint-1 detail it
revises (REQ-S2-DOC-006). §2 line numbers are stale — go by symbol name.

**FIND-S2-001 — import-independent, idempotent launch publication (REQ-S2-PUB-001…004).**
`agent/apps.py` now schedules discovery via a module-level `_schedule_companion_discovery()`
called as the FIRST statement of `AgentConfig.ready()` — before `global_state`, the two MCP
servers, `models`, ACPX, and skills are imported — so an import/startup failure in any of them
can never prevent publication. It uses ONLY stdlib imports, a pure
`_discovery_publish_eligible(argv_str, run_main)` predicate for the run-mode + reloader gate,
and a DEDICATED idempotency gate (`_DISCOVERY_GATE_LOCK` + `_discovery_thread_started`) that is
separate from `mcp_server_running`, so a duplicate `ready()` can never start two publisher
threads. The old inline block that sat after the RUN_MAIN gate was removed.

**FIND-S2-002 — installer registration INDEPENDENT of ARP (REQ-S2-INSTALL-001…004).**
`install.py` now has a separate `_register_companion_discovery(target_dir)` method with its own
fail-open `try`, called from the install flow right AFTER `_register_programs_entry(target)` and
NOT nested inside it. A missing `Uninstaller.exe` (which early-returns the ARP method) or an ARP
exception no longer skips companion registration.

**FIND-S2-003 — six values, always (REQ-S2-REG-001 / REQ-S2-INSTALL-004).** Both
`register_discovery_entry()` (runtime) and the installer method write ALL SIX values on every
call — empty string when unknown — instead of writing `Version` / `AgentCatalogVersion` only
when non-empty, so no stale value from a previous install/source root can survive.

**FIND-S2-004 — `utf-8-sig` reads (REQ-S2-MAN-001).** `agent_manifest.read_manifest()` and the
installer's manifest read now use `encoding="utf-8-sig"`, so a BOM-prefixed manifest parses.

**FIND-S2-005 — docs corrected (REQ-S2-DOC-001…006).** Freshness wording now states that every
complete agent file body is hashed on each check and the manifest is rewritten only when content
differs (module docstring, `docs/companion-app-discovery.md`, `docs/claude/architecture.md`, and
this file). The preserved-marker schema documents `manifest_sha256`. The "Removed by
uninstall.py" registry comment is corrected to "an agents-preserving uninstall KEEPS the key".
`InstallLocation` source-mode semantics are documented as `agent_paths.get_app_base_dir()` (the
Django agent app dir), with the note that companion apps must use `AgentsRoot` as the exact path.
This file no longer claims the installer reuses `register_discovery_entry` — it performs its own
writes.

**FIND-S2-006/007 — coverage + secret-safe verification (REQ-S2-TEST-001…007).**
`agent/test_agent_manifest.py` grew from 10 to 17 tests: scheduling eligibility + import-
independent idempotency + a source-order guard (`DiscoverySchedulingTests`), stale-optional-value
clearing, UTF-8-BOM reading, and installer independence with all six values incl. the
manifest-absent case (`InstallerCompanionRegistrationTests`, HKCU backup/restore). Every test is a
plain `unittest.TestCase` importing only Django-FREE modules, so the focused suite runs
secret-safely:

- `python -m unittest agent.test_agent_manifest` → 17 OK; tracked git status identical
  before/after (no secret hydration).
- `python manage.py test agent.test_agent_manifest` → 17 OK; a content-hash guard over 86 config
  files (`config.json` + every agent `config.yaml`) confirmed **0 changed** by the run.

`ruff check` and `py_compile` pass on every changed `.py`.

*End of Tlamatini-Moded-For-Flowpills.md*
