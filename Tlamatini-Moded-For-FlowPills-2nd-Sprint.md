# Tlamatini — Modifications for Tlamatini-FlowPills · SECOND SPRINT

**Audience:** Codex (and any reviewer) — a precise, byte-accurate record of exactly what the
**second sprint** changed on the **Tlamatini** side, so Codex can align with the current code.

**Date:** 2026-07-12
**Tlamatini version:** `1.39.5` (git tag `v1.39.5`)
**Spec implemented:** `C:\Users\angel\source\repos\Tlamatini-FlowPills\Tlamatini-FlowPills-Lookup-2nd-Sprint.md`
(FIND-S2-001 … FIND-S2-007; REQ-S2-PUB / INSTALL / REG / MAN / DOC / TEST; AC-S2-001 … AC-S2-008).
**Sprint-1 companion doc:** `Tlamatini-Moded-For-Flowpills.md` (this file supersedes any sprint-1
detail it revises; sprint-1 §2 line numbers are stale — go by SYMBOL NAME).

> **Git status:** NOTHING committed or pushed. All changes are uncommitted in the working tree,
> awaiting Angela's explicit OK. Git history was not rewritten.

> **How this sprint was built + verified:** entirely with Tlamatini's OWN agents (Editor,
> Pythonxer, Executer, Grepper, File-Creator) — dogfooding. Line numbers below were re-extracted
> from the FINAL files with Grepper after all edits.

---

## 0. TL;DR — what changed

| Finding | Severity | One-line fix |
|---|---|---|
| FIND-S2-001 | High | Discovery is scheduled FIRST in `ready()`, stdlib-only, with a dedicated idempotency gate separate from `mcp_server_running` — import-independent. |
| FIND-S2-002 | High | Installer companion registration moved into its OWN method with its own `try`, called independently of ARP / `Uninstaller.exe`. |
| FIND-S2-003 | Med | `register_discovery_entry` (runtime) + installer write ALL SIX registry values every call (empty when unknown) — no stale value survives. |
| FIND-S2-004 | Med | `read_manifest` (+ installer read) use `utf-8-sig` (BOM-tolerant). |
| FIND-S2-005 | Med | Docs corrected (freshness wording, `manifest_sha256`, uninstall-keeps-key, `InstallLocation` semantics, installer-does-own-writes). |
| FIND-S2-006 | Med | 5 new wiring tests added (scheduling order/idempotency, stale-value clear, BOM, installer independence). |
| FIND-S2-007 | Med | Focused suite is Django-free / runs via `python -m unittest`; verified to change 0 tracked config files. |

---

## 1. Files changed (with exact symbols + current line numbers)

### 1.1 `Tlamatini/agent/apps.py`  — FIND-S2-001 / REQ-S2-PUB-001…004

Added a module-level, stdlib-only scheduler and gate, and call it FIRST in `ready()`:

- `import threading as _threading` (module top).
- `_DISCOVERY_GATE_LOCK = _threading.Lock()` (**L20**) and `_discovery_thread_started = False`
  (**L21**) — the **dedicated** idempotency gate, DELIBERATELY separate from
  `mcp_server_running` (REQ-S2-PUB-003).
- `def _discovery_publish_eligible(argv_str, run_main)` (**L24**) — a PURE predicate: true for
  `runserver` / `startserver` / `daphne` / `asgi` (REQ-S2-PUB-004); under the `runserver`
  autoreloader only the worker child (`RUN_MAIN == 'true'`) is eligible, never the watcher.
- `def _schedule_companion_discovery()` (**L45**) — imports only `sys` / `os` / `logging`,
  checks the predicate, takes `_DISCOVERY_GATE_LOCK` (**L66**), sets `_discovery_thread_started`
  (**L69**), and starts the `DiscoveryPublish` daemon thread whose target does
  `from . import agent_manifest; agent_manifest.publish_discovery(version=get_version())`.
  Fail-open; returns `True` iff it started the thread.
- `AgentConfig.ready()` now calls `_schedule_companion_discovery()` as its **FIRST statement**
  (**L109**) — BEFORE the `try:` that imports `global_state`, `mcp_system_server`,
  `mcp_files_search_server`, `models`, and before the ACPX/skills boot. So an import or startup
  failure in any optional subsystem can NEVER prevent publication (REQ-S2-PUB-001/002).
- The old inline discovery block (sprint-1) that sat AFTER the heavy imports + the
  `mcp_server_running` early-return was **removed**.

### 1.2 `Tlamatini/agent/windows_app_registration.py`  — FIND-S2-003 / REQ-S2-REG-001

- `def register_discovery_entry(...)` (**L205**) now writes **all six** `REG_SZ` values
  unconditionally — `Version` (**L236**, `version or ""`) and `AgentCatalogVersion` (**L237**,
  `agent_catalog_version or ""`) are no longer behind `if version:` / `if agent_catalog_version:`.
  A re-registration therefore OVERWRITES any pre-existing value with an empty string when unknown,
  so no stale metadata from a previous install/source root can survive.
- The stale comment "Removed by `uninstall.py`" was corrected (**L198**): an agents-PRESERVING
  uninstall **KEEPS** the key; only an explicit FULL removal calls `unregister_discovery_entry()`
  (**L244**). Docstring updated to state the six-values-always contract.

### 1.3 `Tlamatini/agent/agent_manifest.py`  — FIND-S2-004 / REQ-S2-MAN-001 + DOC-001

- `def read_manifest(...)` (**L177**) opens the manifest with `encoding="utf-8-sig"` (**L183**,
  comment **L181**) — a manifest written WITH a BOM now parses; plain UTF-8 is a strict subset,
  so BOM-less files are unaffected.
- Module docstring + `compute_agent_catalog_version` docstring corrected to the ACTUAL freshness
  behavior: `ensure_manifest` (**L197**) re-hashes EVERY complete agent file body on each
  background check and rewrites only when meaningful content differs (the volatile `generated_at`
  alone never rewrites). `agent_catalog_version` is a NAME-SET id; per-file `sha256` = CONTENT.
  (Behavioral code of `ensure_manifest` was already correct in sprint-1 — only the docstrings and
  the module contract text were wrong.)

### 1.4 `install.py`  — FIND-S2-002 / REQ-S2-INSTALL-001…004

- New independent method `def _register_companion_discovery(self, target_dir)` (**L761**) with
  its OWN fail-open `try`. It resolves `<install>\agents` + the shipped manifest, reads
  `agent_catalog_version` via `utf-8-sig`, and writes all six `REG_SZ` values including
  `Version` (**L801**, `self.version or ""`) and `AgentCatalogVersion` (**L802**) — empty when
  unknown. The installer is a standalone frozen exe and cannot import `agent.*`, so it does its
  OWN `winreg` writes and never calls `register_discovery_entry`.
- Called from the install flow at **L594** (`self._register_companion_discovery(target)`),
  right AFTER `self._register_programs_entry(target)` and NOT nested inside it. So a missing
  `Uninstaller.exe` (which early-returns `_register_programs_entry`) or an ARP exception no longer
  skips companion registration.
- The old inline companion block INSIDE `_register_programs_entry` was removed (that method is now
  ARP-only, ending in its own `except`).

### 1.5 `Tlamatini/agent/test_agent_manifest.py`  — FIND-S2-006/007

Grew from **10 → 17** tests. Existing 10 preserved (REQ-S2-TEST-006). New:

- `ManifestGenerationTests.test_read_manifest_accepts_utf8_bom` (**L97**) — REQ-S2-TEST-005 (BOM).
- `DiscoveryRegistryLiveTests.test_empty_optional_values_clear_stale` (**L217**) —
  REQ-S2-TEST-004 (prepopulate `Version`/`AgentCatalogVersion`, register with empty, assert both
  are now empty `REG_SZ`). Runs under the existing HKCU backup/restore.
- `class DiscoverySchedulingTests` (**L287**), 3 tests — REQ-S2-TEST-001/002:
  `test_eligibility_predicate_modes` (**L299**), `test_schedules_import_independently_and_idempotently`
  (**L313**, patches `publish_discovery`/`get_version`/`sys.argv`; asserts ONE publish, gate blocks
  the 2nd), `test_scheduled_before_heavy_imports_in_ready` (**L336**, source-order guard: the call
  precedes `mcp_system_server` / `global_state` / `from .models import`).
- `class InstallerCompanionRegistrationTests` (**L347**, Windows-only, HKCU backup/restore), 2 tests
  — REQ-S2-TEST-003: `test_registers_with_manifest_and_no_uninstaller` (**L378**, no `Uninstaller.exe`
  present), `test_registers_all_six_when_manifest_absent` (**L396**, all six present, optional ones
  empty).

Module docstring documents the SECRET-SAFE run path (REQ-S2-TEST-007).

### 1.6 Docs — FIND-S2-005 / REQ-S2-DOC-001…006

- `docs/companion-app-discovery.md` — rewritten: freshness wording, `manifest_sha256` in the
  marker schema (computed after the `preserved` re-stamp), a positive "FlowPills consumes the key +
  manifest before legacy fallbacks" statement, uninstall-KEEPS-the-key, accurate `InstallLocation`
  source-mode semantics (`agent_paths.get_app_base_dir()` = the Django agent app dir; use
  `AgentsRoot` as the exact path), six-values-always, and the import-independent/idempotent
  publication invariant. Files table points at `_register_companion_discovery` and the new apps.py
  symbols.
- `docs/claude/architecture.md` — the manifest bullet's freshness line corrected + `utf-8-sig` note.
- `Tlamatini-Moded-For-Flowpills.md` (sprint-1 report) — top pointer added; §2.4 corrected (no
  longer claims the installer reuses `register_discovery_entry`); new **§7 Second-Sprint Amendments**
  describes the current code.

---

## 2. Requirement → evidence map (acceptance criteria)

| Requirement | Where satisfied | Evidence |
|---|---|---|
| REQ-S2-PUB-001/002 (import-independent, scheduled first) | `apps.py` L45/L109 | `test_scheduled_before_heavy_imports_in_ready`, `test_schedules_import_independently_and_idempotently` |
| REQ-S2-PUB-003 (dedicated idempotency gate) | `apps.py` L20/L21/L66-69 | idempotency test (one publish, 2nd blocked) |
| REQ-S2-PUB-004 (run modes) | `_discovery_publish_eligible` | `test_eligibility_predicate_modes` |
| REQ-S2-INSTALL-001/002/003 (independent of ARP/Uninstaller) | `install.py` L594/L761 | `test_registers_with_manifest_and_no_uninstaller` |
| REQ-S2-INSTALL-004 / REQ-S2-REG-001 (six values, empty when unknown) | `install.py` L801/802, `windows_app_registration.py` L236/237 | `test_empty_optional_values_clear_stale`, `test_registers_all_six_when_manifest_absent` |
| REQ-S2-REG-002/003 (HKCU/fail-open, preserve-on-uninstall) | unchanged HKCU-only + comment L198 | `DiscoveryRegistryFailOpenTests` |
| REQ-S2-MAN-001 (utf-8-sig) | `agent_manifest.py` L183 | `test_read_manifest_accepts_utf8_bom` |
| REQ-S2-MAN-002/003 (freshness, atomic) | `ensure_manifest` / `_write_manifest_dict` | existing freshness tests (content edit / no-churn / version+kind) |
| REQ-S2-DOC-001…006 | 4 docs | AC-S2-006 repo sweep = clean |
| REQ-S2-TEST-001…006 | 17 tests | see §3 |
| REQ-S2-TEST-007 / AC-S2-008 (secret-safe) | Django-free suite | see §3 |

---

## 3. Verification evidence (all green this session)

- `python -m unittest agent.test_agent_manifest` → **Ran 17 tests … OK**. `git status --porcelain`
  **identical** before/after (`fc: no differences`) — no secret hydration (REQ-S2-TEST-007).
- `python manage.py test agent.test_agent_manifest` → **returncode 0, 17 OK**; a content-SHA-256
  guard over **86 config files** (`agent/config.json` + every `agents/*/config.yaml`) reported
  **0 changed** by the run (AC-S2-007 + AC-S2-008).
- `python -m py_compile` + `python -m ruff check` → **clean** on all 5 changed `.py` files
  (`apps.py`, `windows_app_registration.py`, `agent_manifest.py`, `install.py`,
  `test_agent_manifest.py`).
- AC-S2-006 repo sweep (`*.md`) → no remaining "hashed only when the set changes" / "does not
  consume" / "uninstall removes the key" / "marker lacks manifest_sha256" / stale-`InstallLocation`
  claims (the only "calls the same" hits left are the unrelated Multi-Turn dedup guard in
  `BookOfTlamatini.md` / `GEMINI.md`).
- FlowPills side (from sprint-1, unchanged): `MSBuild Debug|x64` = 0 warnings / 0 errors; it reads
  `HKCU\Software\XAIHT\Tlamatini` before legacy fallbacks.

---

## 4. Invariants Codex should keep (do NOT weaken)

1. **Discovery scheduling stays FIRST in `ready()`**, stdlib-only, before the heavy imports. Do not
   move it back below `global_state` / MCP / `models` / ACPX imports, and do not gate it on
   `mcp_server_running`.
2. **The dedicated gate** (`_DISCOVERY_GATE_LOCK` + `_discovery_thread_started`) is the ONLY
   idempotency mechanism for discovery — keep it separate from the MCP flag.
3. **Six registry values, always** (empty when unknown) — never re-introduce the `if version:` /
   `if agent_catalog_version:` conditionals.
4. **`utf-8-sig`** for every manifest read (runtime + installer).
5. **Installer companion registration stays an independent method** with its own `try`, called
   outside `_register_programs_entry`; it never imports `agent.*`.
6. **Filesystem is authoritative** — the manifest is diagnostic only; keep it accurate but never let
   it gate a root pass/fail.
7. **HKCU only, never admin; every writer fail-open.** Read-only w.r.t. Tlamatini except our own
   manifest file + our own registry key.
8. **The focused test suite stays Django-free** (plain `unittest.TestCase`, no config-stack boot) so
   it never hydrates secrets; keep the HKCU backup/restore in the live registry tests.

---

## 5. Scope guard — what was NOT changed

- No change to FlowPills' own lookup, `.flw` rendering, or deployment (Tlamatini side only).
- No HKLM writes, no admin requirement, no drive scans.
- No change to agent execution, flow compilation, or the existing installer/uninstaller behavior
  beyond the (fail-open) discovery writes.
- The self-update preserve lists were untouched; discovery republishes on every launch via
  `apps.py`, so a self-updated install re-publishes automatically.

*End of Tlamatini-Moded-For-FlowPills-2nd-Sprint.md*
