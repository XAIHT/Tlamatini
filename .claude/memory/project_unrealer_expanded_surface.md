---
name: project_unrealer_expanded_surface
description: Unrealer agent expanded from 28→53 Unreal-MCP commands (System/Level/Asset/Material); cross-repo fork relationship + forwarder hardening
metadata: 
  node_type: memory
  type: project
  originSessionId: 0fadc47e-d29b-4b36-a8e2-4791d94f8829
---

2026-05-24: Expanded the **Unrealer** agent to track the improved Unreal MCP fork.

**Cross-repo relationship (not derivable from Tlamatini code alone):** Unrealer's command
surface mirrors the fork developed at `C:\Development\unreal-mcp`. **As of 2026-05-24 that fork
has a public canonical home: `https://github.com/XAIHT/XaihtUnrealEngineMCP.git`** — "the Unreal
Engine MCP modified specifically for Tlamatini" — built on upstream `chongdashu/unreal-mcp`.
The Tlamatini docs now name THIS repo as the recommended/canonical "MCP git location" (README §6.2
heading renamed "Upstream plugin"→"The MCP plugin source" + TOC anchor moved in lock-step;
BookOfTlamatini §57.1/§57.2/§57.5/glossary + new Recent-Updates entry; agents_descriptions.md;
docs/claude/agents.md; agentic_skill.md #60; KIMI.md; recent-fixes.md entry). Doc-reference pass
only — no code/agent/migration changes. Authoritative TCP command surface = the C++ dispatch in
`MCPGameProject/.../UnrealMCPBridge.cpp::ExecuteCommand` (NOT the Python FastMCP tools).
Post-improvement: **53 commands across 9 categories** reachable over the raw TCP socket —
base 28 (editor/blueprint/node/project/umg) + P1 **system** (execute_python,
execute_console_command, get_class_info, list_assets) + P2 **level/asset/material** + new
verbs take_screenshot/focus_viewport/create_actor, set_pawn_properties, find_blueprint_nodes.

**KEY GOTCHA:** the P3 automation tools (`build_project`/`run_automation_tests`/`run_macro`
in `Python/tools/automation_tools.py`) are **NOT bridge commands** — they shell out to
UnrealEditor-Cmd / loop send_command in Python, so Unrealer (raw TCP) cannot reach them. Do
NOT advertise them. Canvas equivalent of run_macro = chain Unrealer nodes via Parametrizer.

**Why config.yaml param placeholders matter:** the wrapped-tool / Flow-Compiler dotted
override mechanism (`_resolve_config_path` in tools.py) only writes `params.X` overrides when
`X` **already exists** as a YAML leaf — otherwise it errors/drops. So every new command's
params MUST be a placeholder in `agent/agents/unrealer/config.yaml`, or the command is
unreachable from chat/canvas. [[project_kalier_agent]] pattern.

**unrealer.py forwarder hardening added** (it's a generic forwarder; agent code didn't strictly
need changes, but these are robustness wins): `_CONTENT_PATH_PARAM_KEYS` extended with
destination_path/source/destination/parent_material/material (disk paths source_file/filepath
deliberately NOT normalized); `_remap_console_command` maps `params.console_command`→wire
`params.command` (execute_console_command's param collides with the top-level `command:`
selector — bare `command=` would go ambiguous); `_prune_unset_params` drops ''/[]/{}/None
placeholders before send (keeps 0/False) so the big placeholder catalog doesn't flood every
command. recursive defaults true + slot defaults 0 (always-sent typed defaults).

Surfaces updated: chat_agent_registry purpose/aliases/security_hints, agents_descriptions.md,
agentic_skill.md #60 + catalog line, README §6 (table + counts + **fixed stale idPrompt 32→25**),
docs/claude/agents.md, doc_generation/complete_project_docs.py. New `test_unrealer_agent.py`
(29 tests, importlib loader mirroring [[project_kalier_agent]]). ruff clean.

**Demo prompts (migration 0100, follow-up request):** existing idPrompt 25 (0087) only covers
base editor/blueprint/node/umg. Added 3 tiered demos at slots **60/61/62** exercising the NEW
surface — 60 Unreal Snapshot (basic: get_current_level→spawn→take_screenshot→save), 61 Unreal
Scene Forge (medium: list_assets→create_folder→create_material(+instance/set_param/assign)→
spawn→assign_material→take_screenshot→save_all; honest that set_material_parameter on a blank
material soft-fails), 62 Unreal Python & Introspection (hard: execute_console_command via
console_command remap→get_class_info→list_assets→execute_python as TRIPLE-QUOTED params.code→
take_screenshot). Append-only, contiguous (catalog now 1-62, next free 63), update_or_create,
depends on 0099. NL assignment parser carries multi-line code via `'''...'''` (triple-quote
aware in _split_assignment_segments/_coerce_assignment_value). **migrate run** (dev DB now at
0100; it was behind at 0092).

**Full doc propagation (2026-05-24 follow-up):** also updated CLAUDE.md (migration-latest pointer
0098→0100), KIMI.md (Unrealer line 28→53/9), BookOfTlamatini.md (catalog row + §57 chapter:
§57.5 added the 4 new category bullets, §57.7 added the 3-demo paragraph, fixed idPrompt 32→25
in §57 AND the pinned 2026-05-16 changelog entry, added a new 2026-05-24 "Recent Updates" entry
at top), flowhypervisor/monitoring-prompt.pmt ("28-command surface"→count-agnostic), and prepended
a dated entry to docs/claude/recent-fixes.md. Skills (skills_pkg/*/SKILL.md) have ZERO Unrealer
mentions — nothing to change there. Intentionally LEFT as-is: README "base 28-command" reference
framing + the BookOfTlamatini 2026-05-16 historical entry's "28-command/five categories" (pinned
as accurate-at-the-time per the changelog-pinning convention). PDF/PPTX untouched per request.
NOT committed (user owns git writes).

**Per-command read-timeout floors (2026-05-24 follow-up, from log+image diagnosis):** Two "Scene
Forge" runs partially failed — `create_material` timed out at the flat `read_timeout: 10`, then
create_material_instance/set_material_parameter/assign_material all cascaded into "not found".
Root cause confirmed in upstream C++ `HandleCreateMaterial` → `IAssetTools::CreateAsset` compiles
the new material's shaders SYNCHRONOUSLY on the game thread; the FIRST material in a fresh editor
session (cold shader DDC) needs 15-40 s, so 10 s aborted a valid op. Fix is in `unrealer.py` (NOT
config.yaml, so it applies regardless of how per-run config is generated): `_SLOW_COMMAND_TIMEOUT_FLOORS`
map (create_material 60s, create_material_instance/set_material_parameter/new_level 45s,
compile_blueprint/execute_python/open_level 60s, import_asset 90s) + `_effective_read_timeout =
max(configured, floor)` (never lowers an operator's explicit value; unknown commands unchanged) +
`_COMPILE_SLOW_COMMANDS` set so the timeout diagnostic appends a shader-compile remedy distinct from
the existing modal-Save-dialog one. **save_* deliberately NOT floored** (a hung save is parked on an
unclearable modal — short timeout = faster actionable error). Patched BOTH source and frozen
`C:\Tlamatini\agents\unrealer\{unrealer.py,config.yaml}` in place. Tests: 37→46 (EffectiveReadTimeoutTests
6 + 3 new DiagnoseNoResponseTests + a guard that every floored command is modal-prone and/or
compile-slow). ruff clean. Recent-fixes.md entry prepended. NOT committed.
