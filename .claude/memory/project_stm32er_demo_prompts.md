---
name: project_stm32er_demo_prompts
description: STM32er Catalog-of-Prompts demos — migration 0103 seeds 3 tiered STM32F firmware prompts at slots 63/64/65
metadata: 
  node_type: memory
  type: project
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---

2026-05-26: Added `agent/migrations/0103_add_stm32er_demo_prompts.py` seeding 3 tiered STM32F-programming demos for the STM32er agent ([[project_stm32er_agent]]) into the Catalog of prompts (the `Prompt` model; the "Catalog of prompts" button in agent_page.html opens it). All drive the wrapped **chat_agent_stm32er** Multi-Turn tool, Multi-Turn-only (NOT behind ACPX).

- **63 STM32 FORGE** (basic): discover_toolchain_tool → create_project → build → list_artifacts (find arm-none-eabi-gcc → scaffold → compile+link .elf → .hex/.bin; no board).
- **64 STM32 BLINKY** (medium): get_config → create_project → write_source (HAL GPIO blink main.c) → build → list_artifacts → build_and_flash (flash is board-optional soft-fail).
- **65 STM32 HIL OBSERVATORY** (hard): discover → create_project → write_source (counter+UART fw) → build → build_and_flash → serial_session (read VCP boot banner) → live_monitor (sample g_blink_count over SWD, confirm rising) → reset. Adds a status scoreboard of chips.

Style mirrors 0100 (Unrealer) exactly: gradient `_BANNER_OPEN` div (ST-blue palette `#061029→#1E63FF→#22D3EE` matching `.canvas-item.stm32er-agent`, + text-shadow for white-text legibility), step-by-step, exec-report-table, verdict banner, END-RESPONSE. "Board-absent flash/HIL = expected ok=false, record verbatim & continue" honesty note (0100's meshless-spawn convention). LLM authors the actual main.c at runtime (content='''...''' triple-quoted).

Contiguity contract (dropdown breaks at first gap): catalog was gap-free 1-62; appended 63-65, dep on 0102, no renumber. Verified: ruff clean, round-trips clean (reverse→62, reapply→65 no gaps). Not committed (user owns git writes). Docs (README demo-prompts catalog, etc.) NOT updated — consistent with STM32er docs being DEFERRED per user.
