---
name: project_esp32er_agent
description: "ESP32er agent (#69) — PlatformIO pio CLI bridge, the direct-CLI sibling of STM32er"
metadata: 
  node_type: memory
  type: project
  originSessionId: d10fc99b-f057-44ea-b079-a9260231f357
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-31: Added **ESP32er** (#69) — ESP32/Espressif firmware agent on BOTH canvas + Multi-Turn (`chat_agent_esp32er`), modeled on [[project_stm32er_agent]].

**Key architectural difference from STM32er (user chose this):** PlatformIO ships a complete `pio` CLI, so ESP32er has **NO MCP server** — it invokes `pio` subcommands DIRECTLY (Kalier/Executer pattern), stdlib-only `subprocess`+`urllib` in `agent/agents/esp32er/esp32er.py`. (STM32er needed an MCP server only because STM32CubeIDE has no unified CLI.) Decided via AskUserQuestion: "Direct pio CLI" + "compile+upload+monitor core" cut; **headless debug (`pio debug -x gdb_script`) deferred as fast-follow** (needs JTAG/USB-JTAG).

**Actions** (one per run): bootstrap/validate/system_info/boards · create_project/write_source/read_source/list_sources/clean · build/upload/build_and_upload/list_artifacts · device_list/monitor/monitor_session · pkg_install/pkg_list/pkg_update/check/test. **Zero-config bootstrap** = download get-platformio.py installer (pip fallback) into %LOCALAPPDATA%/Tlamatini/platformio. **Safety preflight**: pio resolvable + platformio.ini exists; upload/monitor ALSO need a connected serial port (ESP32 flashes over onboard USB-serial — NO JTAG probe for upload, only debug). Non-espressif platform = WARN not refuse (multi-target, no shared-linker risk). Emits INI_SECTION_ESP32ER; ALWAYS triggers target_agents.

**Footprint** (mirrors STM32er at every reg point): migrations 0105 (Agent row) + 0106 (Tool row, "Chat-Agent-ESP32er"); views.update_esp32er_connection_view + urls; chat_agent_registry spec (long_running, poll 180); mcp_agent _EXEC_REPORT_TOOLS + _infer_execution_shell; agent_contracts _PARAMETRIZER_OUTPUT_FIELDS; parametrizer SECTION_AGENT_TYPES; agent_paths display "ESP32er"; tools._seed_global_agent_defaults (pio_executable/pio_core_dir globals) + config.json `_section_esp32`. Frontend: CSS gradient (charcoal→Espressif-red, distinct from STM32er blue) in agentic_control_panel.css + agent_page.css exec-report; 4 JS files (connectors/canvas-core×4/undo×2/file-io) + agent_page_chat flow-gen branch. Docs: agents_descriptions.md, agentic_skill.md (#68, FlowCreator→#69), docs/claude/agents.md (69 types), README §3.17 + counts (76 tools/69 agents), CLAUDE.md.

**Tests**: `agent/test_esp32er_agent.py` = 31 tests (fake `pio` python script driven by real _pio/_run_action/_preflight). 162 green across esp32er+stm32er+ExecReport. ruff clean, eslint 0 errors, migrate run.

**NOT committed** (user owns git). Frozen build needs no special flag, but a rebuild ships the new agent template. **Naming**: display=ESP32er (exact case), dirs/pool/CSS/JS=esp32er, INI_SECTION_ESP32ER all-caps — see [[feedback_agent_naming_conventions]].

**2026-05-31 follow-ups (this session, NOT committed):**
- **ESP32TemplateProject scaffold** at `C:\Development\ESP32TemplateProject` — an INDEPENDENT PlatformIO repo (NOT part of Tlamatini's build), the ESP32 counterpart of STM32TemplateProjectMCP. esp32dev/arduino blink (GPIO 2 + Serial), MIT LICENSE, README/CHANGELOG, `.github/workflows/build.yml` CI, `scripts/create_github_repo.ps1`/`.sh` (gh-CLI publish helpers). Intended GitHub home `github.com/XAIHT/ESP32TemplateProject`. VERIFIED builds clean with PlatformIO Core 6.1.19 (firmware.bin+elf). Documented in BookOfTlamatini.md **bonus chapter §58** + glossary row + changelog entry.
- **3 demo prompts** via **migration 0107_add_esp32er_demo_prompts** at catalog slots **66/67/68** (ESP32 GENESIS basic / ESP32 BLINKY medium / ESP32 HIL OBSERVATORY hard — #68 does a REAL build_and_upload + serial monitor). Mirrors STM32 0103 pattern; Espressif-red banner; drive ONLY chat_agent_esp32er, Multi-Turn-only. Catalog now contiguous 1–68. Reversible+idempotent.
- **Frozen vs not-frozen verified**: agent ships frozen via build.py's `agent/agents/` copytree (added `test_esp32er_agent_ships_complete` to `test_build_scripts.py`, mirroring stm32er); demo prompts seed at frozen FIRST-RUN (build.py erases db.sqlite3 → migrations rebuild it — same path STM32 demos shipped). esp32er.py is frozen-aware (sys.frozen/_MEIPASS, get_python_command/get_agent_env) + 0 `agent.*` imports (stdlib+yaml only). RAN the agent live not-frozen → build SUCCESS, correct INI_SECTION_ESP32ER fields, exit 0. test_build_scripts 29 OK, test_esp32er_agent 31 OK, ruff clean.
- **FYI (not changed)**: `config.json` `pio_executable` is a machine-specific path with a leading space (`" C:/Users/angel/.platformio/penv/Scripts/pio.exe"`) — works on this box both modes (agent `.strip()`s it); a DISTRIBUTED frozen build to another machine won't find it but falls back to zero-config auto-bootstrap (GENESIS/BLINKY/HIL demos start with bootstrap/validate precisely for this). Set to `""` for a truly turnkey distributable, at the cost of re-downloading PlatformIO on this dev box's first run.
