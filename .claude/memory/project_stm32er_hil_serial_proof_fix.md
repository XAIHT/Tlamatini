---
name: project_stm32er_hil_serial_proof_fix
description: "STM32er HIL demo (#65) fix — F4-Discovery ST-LINK VCP is NOT routed to the MCU USART, so live-SWD-memory is the real HIL proof, not serial"
metadata: 
  node_type: memory
  type: project
  originSessionId: b58ee550-b07a-4a82-92db-222bb77e415f
---

2026-05-27: Live frozen run (C:\Tlamatini) of catalog prompt **#65 "STM32 HIL OBSERVATORY"** (the last STM32er demo, seeded by migration 0103) thrashed: the LLM made **21 chat_agent_stm32er calls**, 8 of them serial retries (serial_session ×6 with escalating 5/6/8/10/12s timeouts + injected `data='\n'`, plus serial_connect/serial_read + a stray reset), every read returning `bytes=0`.

**Root cause = a board hardware fact, not an agent bug:** on the **STM32F4-Discovery family (incl. STM32F407G-DISC1)** the on-board ST-LINK does **NOT** bridge its Virtual COM Port to the MCU's USART pins — unlike ST **Nucleo** boards, which route VCP↔USART2 (PA2/PA3). So firmware transmitting on USART2 produces **nothing** on the VCP regardless of baud/timeout. Demo #65 wrongly made the serial VCP read a PRIMARY proof gate and gave the model no "empty is expected, don't retry" guidance. Meanwhile `build_and_flash` succeeded (green LED) and `live_monitor` over **SWD** read `g_blink_count` rising 30→32 — the genuinely reliable, board-agnostic HIL proof, which worked perfectly.

**Fix** (new migration **`0104_fix_stm32er_hil_serial_proof.py`**, rewrites prompt #65 only via `update_or_create`; reverse restores 0103 text via `importlib`): live-SWD-memory is now the PRIMARY proof (Step 6), serial VCP is best-effort / board-aware / **AT-MOST-ONCE no-retry** (Step 7), and the "✅ SILICON VERIFIED" verdict is keyed on build+flash+live_memory (serial = bonus chip, amber `#d97706` when expected-empty). Stated the VCP-not-routed fact up front.

**Applied two places:** (1) source migration 0104 (latest is now 0104; `migrate --plan` clean, ruff clean, py_compile OK); (2) **directly patched the running frozen DB** `C:\Tlamatini\_internal\db.sqlite3` `agent_prompt` row idPrompt=65 (6741→8583 chars) since the frozen exe won't pick up a new source migration without a rebuild. `views.load_prompt_view` reads promptContent fresh from the DB per catalog selection → **no server restart needed**, just re-pick #65. Source `Tlamatini/db.sqlite3` left to the user's normal `manage.py migrate`. **Docs:** added the VCP-bridging nuance to README.md (§3 STM32er callout) + BookOfTlamatini.md (agent-catalog row + a dated "Recent Updates" entry) — to read the serial banner on a Discovery board you must wire an external USB-TTL adapter (RX←PA2, TX→PA3, GND↔GND) since the on-board ST-LINK VCP isn't routed to USART2; Nucleo routes it natively. NOT committed. Related: [[project_stm32er_demo_prompts]], [[project_stm32er_agent]], [[project_stm32er_bootstrap_preflight]].
