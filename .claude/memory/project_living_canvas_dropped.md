---
name: Living Canvas v0 dropped
description: 2026-04-29 — Living Canvas v0 commits (2fc441d, 0705a9c, d496cda) were force-reverted; feature was non-functional in production despite passing tests, do not re-attempt without an end-to-end manual smoke test
type: project
originSessionId: c4ba907a-c91d-4c2c-8f86-5b38594aaca7
---
The Living Canvas v0 commit set (`2fc441d`, `0705a9c`, `d496cda`) was force-reverted to `1ad4fb0` on 2026-04-29 and force-pushed to `origin/main`.

**Symptom:** Running instance showed nothing different than two days prior — the "Living Theater" strip never animated despite the Multi-Turn execution running normally. tlamatini.log confirmed lifecycle frames never reached the browser.

**Root cause attempted-fix in this same session:** `MultiTurnToolAgentExecutor._lifecycle_user_id` was always `None` because both `UnifiedAgentChain.invoke` (payload-rebuild whitelist) and the executor sub-payloads in both unified chains stripped `conversation_user_id`. Same gotcha class as the documented `exec_report_enabled` whitelist bug.

**Why the fix wasn't enough:** Even after wiring user_id through, the user reported the running instance still behaved exactly like the day before — likely additional broken layers (channel-layer routing, frontend chaining onto `chatSocket.onmessage`, in-memory channel layer not actually delivering cross-coroutine messages, etc.). Rather than spelunking further, the user chose to drop the entire feature.

**How to apply:**
- Do NOT reintroduce `agent_page_living.js`, `living_theater.css`, the `agent_lifecycle` consumer handler, or the `_emit_lifecycle_event` plumbing in `mcp_agent.py` without first proving the full path works in a running source-mode instance — load the chat page, fire a Multi-Turn request, and visually confirm the theater animates BEFORE writing tests or claiming success.
- "Tests pass" is not equivalent to "feature works" when the tests bypass the chain → executor boundary by mocking `_lifecycle_user_id` directly. Any future revival of this feature MUST include an integration test that drives `UnifiedAgentChain.invoke` end-to-end with a fake executor and asserts `conversation_user_id` survives every payload rewrite — and a manual smoke-test step in the commit message.
- The user is rightly skeptical of feature work that ships without a real demo. Default to a single shorter visible-result commit over a sweeping multi-commit "v0 + tests" series.
