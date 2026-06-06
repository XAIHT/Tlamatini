---
name: project_stm32er_tests
description: "STM32er agent test suite — agent/test_stm32er_agent.py, 85 tests covering compiler-find/compile/link/hex via a fake MCP stdio server"
metadata: 
  node_type: memory
  type: project
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---

2026-05-26: Added `Tlamatini/agent/test_stm32er_agent.py` (85 tests, ruff clean, all green) for the STM32er agent ([[project_stm32er_agent]]). Modeled on `test_kalier_agent.py` conventions (importlib loader with cwd + log-handler save/restore).

Key design: STM32er.py is only a thin MCP **stdio** JSON-RPC bridge — the real compiling/linking happens in the STM32TemplateProjectMCP server, which isn't present in CI. So the "be sure at finding the compiler / compiling / linking elf / hex generation" coverage the user asked for is done by a **fake stdlib MCP stdio server** written to a temp `.py` and spawned by the REAL `_McpStdioClient` (subprocess). The fake answers `initialize` + `tools/call` with realistic responses: `discover_toolchain_tool`→arm-none-eabi-gcc paths, `build`→link+objcopy stdout with firmware.elf, `list_artifacts`→elf/hex/bin, `flash`, plus env-flag scenarios (`STM32_FAKE_BUILD_OK=0` compile-fail routability, `STM32_FAKE_HANG` call_timeout backstop, `STM32_FAKE_EXIT_EARLY`, `STM32_FAKE_INIT_ERROR`). Also emits a non-JSON banner + an unrelated notification to prove the client swallows them.

Gotchas baked in: the fake-server source is a `r'''...'''` raw string (so `\n` survives into the file and is parsed as a newline by the fake server's own Python; inner strings use `"""`-free `"\n".join([...])` to avoid nested-triple-quote collisions). Do NOT patch the module `time` in the real-client/main() tests — `_McpStdioClient._read_response` needs real `time.monotonic`; just accept the ~0.4s end-of-main sleep. Composite actions (serial_session/live_monitor) tested with an in-memory `_StubClient` and `monitor_seconds=0`.

Run: `python Tlamatini/manage.py test agent.test_stm32er_agent`. Not committed (user owns git writes).
