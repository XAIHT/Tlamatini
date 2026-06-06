---
name: Planner follow-up scoring fix
description: Fixed planner losing tool context on short follow-up messages, plus 5 other fixes from MXNet installation log analysis
type: project
originSessionId: dcafd649-e5a5-45e2-bebd-f267bccc46c9
---
On 2026-04-16, analyzed tlamatini.log from an MXNet installation session that required 5+ user attempts over ~50 minutes. Identified and fixed 5 root causes:

1. **Planner statelessness**: Short follow-ups ("continue") scored near-zero for all tools because scoring was based only on current message. Fixed by adding chat-history-aware scoring boost in `global_execution_planner.py` and `factory.py`.

2. **Cancel/rebuild race condition**: After cancel-current, httpx client destroyed but MSG_LLM_REESTABLISHED sent before rebuild finished. Fixed by awaiting `setup_rag_chain()` before confirming.

3. **Googler Playwright crash**: `sync_playwright()` fails inside Django Channels async event loop with NotImplementedError. Fixed by running in ThreadPoolExecutor.

4. **Duplicate wrapped-agent launches**: LLM launched same crawler twice with identical args. Added dedup tracking in `mcp_agent.py` MultiTurnToolAgentExecutor.

5. **Max tool cap**: Lowered default from 50 to 20 to prevent keyword inflation from selecting all tools.

**Why:** The multi-turn agent loop is the flagship feature; these bugs made it unreliable for real tasks.
**How to apply:** When touching planner, executor, or cancel logic, verify these fixes still hold.
