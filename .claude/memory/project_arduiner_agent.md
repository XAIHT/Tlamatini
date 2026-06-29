---
name: project_arduiner_agent
description: "Arduiner (#70) Arduino CLI bridge agent — built 2026-06-02, full canvas + Multi-Turn, ships ArduinoTemplateProject; not committed"
metadata: 
  node_type: memory
  type: project
  originSessionId: dfa6871a-7c64-4368-89f6-19f592070c15
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-02: Added **Arduiner** (agent #70), Tlamatini's bridge to the **Arduino CLI** (`arduino-cli`), on BOTH canvas + Multi-Turn (`chat_agent_arduiner`). Built per the user's explicit request, modeled on STM32er + ESP32er.

**Architecture**: DIRECT-CLI sibling of [[project_esp32er_agent]] — `arduino-cli` is a complete CLI like PlatformIO's `pio`, so NO MCP server (unlike STM32er). Self-contained stdlib-only `agent/agents/arduiner/arduiner.py` (`subprocess`+`urllib`+`zipfile`/`tarfile`+`json`+`threading`), never imports `agent.*`.

**Key divergences from ESP32er**: (1) bootstrap = download the arduino-cli **Go binary** from downloads.arduino.cc + unzip (NOT pip — there is no pip package); sets ARDUINO_DIRECTORIES_DATA/CONFIG to a per-user LOCALAPPDATA dir for read-only-frozen safety. (2) **auto-core-install** (`_ensure_core_installed`): arduino-cli does NOT auto-install platforms on compile (PlatformIO does), so before build/upload it derives the FQBN's `packager:arch` and runs `core update-index` + `core install` when missing (config `auto_core_install`, default true; honors `additional_urls` for ESP32/STM32/RP2040). (3) MCU selected by **`fqbn`** (e.g. `arduino:avr:uno`); baud via `monitor --config baudrate=`. User chose auto-install.

**ArduinoTemplateProject** (user asked for it so all 3 microcontroller agents share one template-project scheme): bundled at `agents/arduiner/ArduinoTemplateProject/` (`.ino` + `src/Heartbeat.{h,cpp}` + `sketch.yaml` profile = peer of platformio.ini + README). `create_project` copies it, renames `.ino` to the folder name (arduino-cli requirement), stamps fqbn/port into sketch.yaml. Ships locally via build.py's `agents/` copytree (offline-safe, better than STM32's network clone).

**Output**: `INI_SECTION_ARDUINER` (action/tool/ok/returncode/success/fqbn/port/sketch_path/stage + body); always triggers `target_agents`. Color = Arduino-teal 4-ramp (#00363A→#008184→#00C4CC→#C8F2F0).

**Wiring** (mirrors ESP32er at every point): migrations 0109 (Agent) / 0110 (chat_agent tool) / 0111 (3 demo prompts at slots 70-72 GENESIS/BLINKY/HIL); chat_agent_registry spec; mcp_agent `_EXEC_REPORT_TOOLS` + shell label; parametrizer SECTION_AGENT_TYPES; agent_contracts `_PARAMETRIZER_OUTPUT_FIELDS`; agent_paths display name; urls + views connection view; tools `_seed_global_agent_defaults`; config.json `arduino_cli_executable`/`arduino_cli_install_dir`; JS connectors/canvas-core(×4)/canvas-undo(×2)/file-io/agent_page_chat + 3 `/* global */` decls; CSS gradient + exec-report. Docs: agents_descriptions.md, agentic_skill.md (#69, FlowCreator→#70), docs/claude/agents.md (70), CLAUDE.md, README.md (counts 69→70).

**Tests**: `agent/test_arduiner_agent.py` 39 tests (fake `arduino-cli` stub drives real `_cli`/`_run_action`/`_preflight`/`_ensure_core_installed`/`_create_project`/`_bounded_monitor`) — all green. build-scripts test method added. ruff clean; `npm run lint` 0 errors; `manage.py check` clean; `makemigrations --check` no changes; STM32er+ESP32er regression 153 green.

**NOT committed** ([[feedback_user_owns_git]], [[feedback_main_branch_only]]). Frozen build needs `python build.py` to ship the agent (tools.py + agents/ tree are baked into the exe/PYZ). Naming per [[feedback_agent_naming_conventions]]: display **Arduiner**, dir/pool/CSS/JS = `arduiner`, INI_SECTION_ARDUINER all-caps.
