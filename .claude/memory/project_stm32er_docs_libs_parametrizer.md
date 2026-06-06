---
name: project_stm32er_docs_libs_parametrizer
description: "STM32er v1.9.0 alignment — docs/skills/prompt.pmt swept for bootstrap+preflight, parametrizer server_script field, requirements lib sweep (PyPDF2 added), session-start skills hook"
metadata: 
  node_type: memory
  type: project
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---

2026-05-26 (v1.9.0 release prep, not committed): broad alignment pass after the STM32er zero-config bootstrap + preflight work ([[project_stm32er_bootstrap_preflight]]).

**Docs/skills aligned with STM32er bootstrap/preflight/validate/zero-config:** prompt.pmt (STM32er rule), agentic_skill.md (#67 entry + table row — fixed stale server_script default, added bootstrap/validate actions + new config keys), agents_descriptions.md (row), flowhypervisor/monitoring-prompt.pmt (bootstrap/preflight notes + STM32er→STM32er log-line casing), Tlamatini.md (67→68 agents + firmware capability), README.md + KIMI.md + BookOfTlamatini.md + CLAUDE.md body + docs/claude/{agents,architecture,mcp-tools,recent-fixes}.md (via 3 parallel subagents). Catalog count 67→68 everywhere. Demo prompts migration 0103 rewritten: 63 STM32 GENESIS / 64 STM32 BLINKY / 65 STM32 HIL OBSERVATORY (3rd uses real hardware).

**Version:** package.json 1.8.0→1.9.0; README badge + versioning EXAMPLES → v1.9.0 (historical changelog entries left pinned per [[feedback_package_json_version_bump]]).

**Naming convention enshrined** ([[feedback_agent_naming_conventions]]): created `.claude/skills/tlamatini-agent-naming/SKILL.md` + a feedback memory + CLAUDE.md CRITICAL callout. Display=exact `STM32er`; dirs/pool/CSS/JS=lowercase `stm32er`; INI_SECTION_STM32ER all-caps. Fixed dev-DB row idAgent 59 `Stm32Er`→`STM32er` (migration 0101 already correct for fresh installs).

**Session-start notification:** `.claude/settings.json` SessionStart hook runs `.claude/hooks/announce_skills.py` (ASCII-only, fail-open) listing Claude Code + Tlamatini skills each session. New settings.json → needs `/hooks` or restart to load first time.

**Parametrizer full coverage for STM32er:** added `server_script` to `agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['stm32er']` (it was emitted+parsed but not registered, so the canvas dialog didn't offer it). STM32er fully wired as source (SECTION_AGENT_TYPES/OUTPUT_PARSERS/NEXT_OUTPUT_PARSERS/views) AND target (output_field_by_slot {0:target_agents}).

**Lib sweep (frozen+not-frozen):** AST-swept all Tlamatini + bootstrapped STM MCP imports (catches try/except optional imports). Everything covered EXCEPT PyPDF2 (3rd-tier PDF fallback in file_extractor/file_interpreter) → added `PyPDF2==3.0.1` to requirements.txt + pip-installed. pydub NOT imported (not added). KEY: build.py line 426 `pip install --user -r requirements.txt` into BOTH the build Python AND the PYTHON_HOME frozen-agent Python (lines 386/393) — so requirements.txt IS the build.py mechanism for both modes; no separate build.py edit needed. build.py line 629 bundles the agents/ tree (STM32er ships frozen). Frozen exe does NOT import mcp/pyserial (only the external MCP server does, under the bootstrap-pip'd PYTHON_HOME python). 122 tests green, ruff clean.

ADDED a build.py fail-loud verification step (1b-post, after the requirements install, inside the per-target-python loop): imports 22 critical agent/MCP libs (mcp, serial, PyPDF2, pypdf, fitz, odf, ebooklib, openpyxl, xlrd, striprtf, docx, pptx, bs4, requests, py7zr, yaml, pyautogui, playwright, telethon, pymongo, pyodbc, win32gui) in EACH target python and `sys.exit(1)` aborts the build if any is missing/broken — so a frozen install can never ship with incomplete pool-agent/MCP-server assets (pinning in requirements.txt alone wasn't a guarantee the install took). Verified all 22 import in the dev env.
