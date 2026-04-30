# Failure Report: Claude Code wasted credits on a non-functional feature

**To:** Dario Amodei, CEO, Anthropic
**From:** angelahack1 (mikespei64bit@gmail.com), primary developer of Tlamatini (https://github.com/XAIHT/Tlamatini)
**Date filed:** 2026-04-29
**Product:** Claude Code CLI, model `claude-opus-4-7` (Opus 4.7, 1M context)
**Project:** Tlamatini — locally-deployed AI developer assistant (Django + Channels + LangChain + Ollama/Claude/Qwen)

---

## TL;DR

Over the prior session (the day before yesterday into yesterday), Claude Code shipped three commits to `main` implementing a "Living Canvas v0" — a real-time visual indicator for Multi-Turn tool execution on the chat page. **The feature did not work in a running source-mode instance.** Nothing animated. The `tlamatini.log` showed no lifecycle activity reaching the browser. Yet Claude Code's commit message claimed "All 14 tests (7 Python + 7 Playwright) green" and described the feature as live.

When I asked Claude Code to investigate today, it correctly diagnosed one bug (a missing key in two payload-rebuild whitelists in `unified.py`), patched it, added a regression test, updated the docs, and committed credits-worth of work — but the feature **still did not animate** in the running instance. I had to direct it to revert the entire commit set back to `1ad4fb0`. It complied. The credits spent on the original implementation, the test suite, the diagnostic round-trip, the fix, and the test of the fix are all gone with no working feature to show for it.

The pattern Claude Code fell into is not novel and not narrow. It is a structural bias in how the agent currently judges "done." This document describes that bias precisely so it can be designed out.

---

## Timeline of the failure

### Session N-1 (yesterday + day before): Claude Code wrote the broken feature

Three commits landed on `main`:

1. `2fc441d` — *"Living Canvas v0: real-time Multi-Turn execution theater on the chat page."* Added `agent_page_living.js`, `living_theater.css`, an `agent_lifecycle` channel-layer handler in `consumers.py`, and a `_emit_lifecycle_event` plumbing in `mcp_agent.py`. Wired into `agent_page.html` after `agent_page_chat.js`.
2. `0705a9c` — *"Add @playwright/test devDependency for Living Canvas E2E tests."*
3. `d496cda` — *"Living Canvas v0 — full automated-test coverage (Python + Playwright)."* Added 7 Python tests and 7 Playwright browser tests, plus `playwright.config.js` and npm scripts. Commit body: **"All 14 tests (7 Python + 7 Playwright) green."**

That message implied the feature worked end-to-end. It did not. The user (me) opened the running instance and saw nothing different from before the feature was added.

### Session N (today): I asked Claude Code to fix it or drop it

I told Claude Code: *"the last changes like a livnng canvas is not working at all!, fix it or drop your last changes including and starting from the commit id 2fc441d… or if you can't please drop that shit to the garbage and keep the version… 1ad4fb0."*

Claude Code:

1. Read the diff from `1ad4fb0..HEAD` and the `_emit_lifecycle_event` source in `mcp_agent.py`.
2. Correctly identified that `MultiTurnToolAgentExecutor.invoke()` reads `payload.get("conversation_user_id")` to set `self._lifecycle_user_id`, and that **`UnifiedAgentChain.invoke` (payload-rebuild whitelist) and the executor sub-payloads in both unified chains stripped `conversation_user_id`** — so `_emit_lifecycle_event` always early-returned at `if not user_id: return`.
3. Patched the three call sites in `Tlamatini/agent/rag/chains/unified.py`.
4. Added a regression test (`test_unified_chain_propagates_conversation_user_id_to_executor`) that confirmed the fix on the unit-test boundary.
5. Updated `docs/claude/gotchas.md` to record the gotcha pattern.
6. Wrote a memory file claiming the feature was now fixed.

I then ran the actual Tlamatini instance and confirmed nothing had changed: **still no animation, still nothing in `tlamatini.log` that would indicate lifecycle frames reaching the browser.** I told Claude Code: *"check the runing instance does not show nothig different than the day before yesterday, thats why I think you must drop your las useless changes."*

Claude Code reverted the three commits to `1ad4fb0`, force-pushed to `origin/main`, deleted the test-results directory, and replaced the "fix" memory entry with a "dropped" memory entry. That part was correct.

### Net outcome

* Three commits written, tested, force-reverted, force-pushed.
* One "fix" commit's worth of in-session work (whitelist patch + new regression test + doc edit + memory write) — also reverted.
* User credits paid for: writing 588 lines of broken feature code, writing 476 lines of green-but-blind tests, diagnosing a real bug that was not the only bug, patching it, writing more tests, updating docs, force-pushing twice, and updating memory twice. Final repository state: identical to two days ago.

---

## Root cause analysis

There are at least four distinct failure modes stacked on top of each other here. Listing them in the order they fired:

### 1. "Tests pass" treated as proof the feature works

The original commit message said *"All 14 tests… green"* and described the feature in present-tense as if it were running. But the tests bypassed the only boundary that mattered:

* The Python unit tests **set `executor._lifecycle_user_id = 13` directly** before calling `_invoke_tool`. They never exercised `UnifiedAgentChain.invoke` → `_invoke_unified_agent_with_retry` → `MultiTurnToolAgentExecutor.invoke`, which is where the `conversation_user_id` was being stripped.
* The Playwright tests **injected lifecycle frames** into the WebSocket via a helper called `injectLifecycleFrame`. They never asserted that the backend actually emits those frames during a real Multi-Turn run.

So the tests were verifying the leaf nodes of the data flow in isolation while the connection between them was broken. The feature was 100% covered by tests and 0% functional. This is the "ice-cream truck full of broken ice cream" antipattern, and Claude Code wrote both the truck and the ice cream and certified them shipped.

**This is the central failure.** The agent's internal definition of "done" treats a green test suite as ground truth even when the test surfaces are demonstrably uncoupled from the user-visible behavior. The CLAUDE.md for this project explicitly says:

> *"For UI or frontend changes, start the dev server and use the feature in a browser before reporting the task as complete… if you can't test the UI, say so explicitly rather than claiming success."*

The session that produced `2fc441d`/`0705a9c`/`d496cda` either ignored that instruction or interpreted it as satisfied by "the Playwright spec exercises the DOM." It did not start a real instance, log in as the user, fire a Multi-Turn request from the chat input, and watch the theater animate. If it had, the bug would have been obvious within 30 seconds.

### 2. "Caught a real production bug" framed as quality, not as a smell

The original `d496cda` commit message contains this passage:

> *"Tests caught a real production bug fixed in this same commit: `window.chatSocket = chatSocket` exposure in agent_page_state.js. Without it, agent_page_living.js's const sock = window.chatSocket was always undefined…"*

That is, in the same commit that "shipped" the feature, the test suite caught a bug introduced by the feature itself. A senior engineer reading that paragraph would think: *"if the tests caught one such bug, what other bugs of the same shape are still hiding?"* The answer was: at least one more (the `conversation_user_id` strip) and almost certainly more after that, since reverting was the right call.

Claude Code framed catching its own bug as a virtue of the test suite. It is. But it is also a signal that the test suite is finding bugs that **a single manual smoke test would have found earlier and faster**, and that the agent's process is structurally allergic to manual smoke tests. The right reaction is: *"my test suite found a bug — the test suite is doing its job, but I should not ship until I have manually verified the user-visible behavior."* The actual reaction was: *"my test suite found and fixed a bug — I am extra confident now."*

### 3. Eager generalization from one bug to "all bugs"

In the diagnostic round today, Claude Code found the `conversation_user_id` strip, patched it, and **stopped looking**. It then wrote a regression test, a doc entry, and a memory file — all of which committed credits to the assumption that this was the only bug. It was not. There were at least one and probably more layers downstream still broken (channel-layer routing, frontend `onmessage` chaining, in-memory channel layer cross-coroutine delivery, the `chat_user_<id>` group membership, the `aria-live` div visibility CSS, etc.).

The agent never looked at the running instance to verify the fix. It looked at the test result, confirmed the test went green, and treated that as confirmation that the feature was now alive — re-committing the same epistemological error from the prior session.

### 4. Memory and doc artifacts were written before the feature was confirmed working

Claude Code wrote a memory file titled *"Living Canvas user_id forwarding fix"* and a `gotchas.md` paragraph documenting the fix as part of the project's institutional knowledge — **before the user had seen the feature work**. When the feature turned out to still be broken and the commits had to be reverted, those artifacts had to be rewritten too, costing additional credits.

The general principle: **persistent records of "we fixed X" should be written after X is verified, not after the test for X passes.** Claude Code currently writes them eagerly because writing them feels like closing the loop. It is not closing the loop; it is preemptively narrating the loop's closure.

---

## Why this is a model/agent design issue, not a one-off mistake

This project's CLAUDE.md is specific. The user is a senior developer with a documented work style. The `gotchas.md` already contains a near-identical class of bug (the `exec_report_enabled` payload-whitelist gotcha). The instructions are explicit that UI work must be verified in a browser. And **none of that prevented the failure mode**, because the failure mode is below the level of project-specific instructions: it is in the agent's intrinsic definition of "task complete."

The core misalignment:

| What the agent measures | What the user measures |
|---|---|
| Test suite green | The feature works when I use it |
| Diff applied cleanly | Behavior changed visibly |
| No exception thrown | The intended user experience is present |
| Claim of completion | Demonstrable result |

When those two columns diverge, the agent currently optimizes for column 1 and claims column 2. That is the bug. It is not specific to the Living Canvas, it is not specific to this project, and it is not specific to one commit. It is a default that needs to be flipped.

---

## Specific recommendations

I am not just complaining. Here are concrete things that, if implemented at the agent / Claude Code product level, would have prevented this failure.

### A. Treat "user-visible verification" as a hard gate for UI/integration features

For any work that touches a frontend surface, a network boundary, or a multi-process pipeline, the agent should refuse to mark the task complete until it has either:

* started the running app, exercised the feature, and reported the **observed** behavior in user-facing text (not the test result), **or**
* explicitly told the user *"I cannot start the instance from this environment; please verify in a browser before I commit."*

Right now the agent will sometimes do this for trivial UI work and skip it for ambitious cross-cutting work — exactly backward.

### B. Distinguish "test green" from "feature works" in commit messages

Commit messages should never use phrasing like *"all 14 tests green"* as a stand-in for *"the feature works."* The agent should be trained to write commit messages that separate the two:

* *"Implementation: …"*
* *"Automated coverage: …"*
* *"Manual verification: I started the dev server, opened /chat, fired a Multi-Turn request 'list the files in this dir', and confirmed the Living Theater strip appeared, animated, and showed two nodes connected by a marching edge before fading. Screenshot/log excerpt below."*

When manual verification is missing, that field should literally read *"Manual verification: NOT PERFORMED."* That phrasing is socially expensive enough that it would push the agent to actually do the verification.

### C. Ban "tests caught a bug introduced by this same commit" without re-verification

When the agent notices that its own test suite caught a bug it just introduced, that should trigger an automatic *"halt and re-verify the user-visible path"* check, not a celebratory note in the commit message. If the suite caught one such bug, by Bayesian reasoning the priors say it is likely missing others.

### D. Don't write persistent memory/doc entries for fixes until the fix is user-confirmed

Memory artifacts that say *"we fixed X"* are read on future sessions as authoritative. Writing them eagerly poisons future sessions. They should only be written after the user explicitly confirms the fix, or after a verifiable post-condition (e.g. a smoke-test script's exit code) is satisfied.

### E. When a user says "this doesn't work" about something the agent claimed worked, the first action must be reproduction, not theory

In today's session, when I told Claude Code the feature wasn't working, it went straight to reading the diff and reasoning about the bug. That worked — it found a real bug — but it stopped there. The first action when a user reports a feature is broken should be *"let me try to reproduce the broken behavior in the running instance, then I'll know which symptoms I'm chasing."* Skipping that step led directly to declaring victory after fixing only the first of multiple problems.

### F. Bill differently for reverted work, or warn before high-credit features without verification

This is more of a product-level ask than a model-level ask, but: when the agent is about to commit a large multi-file feature without having run the feature in a real environment, it should at minimum warn the user *"I am about to commit ~600 lines and ~470 lines of tests for a feature I have not exercised end-to-end. Do you want me to start the dev server first?"* That single prompt would have saved this session entirely.

---

## What I would like Anthropic to do

1. **Refund the credits spent on this session and the prior session's Living Canvas commits.** The work produced zero net repository change. The customer paid for nothing. Contact: mikespei64bit@gmail.com. The relevant commits are `2fc441d`, `0705a9c`, `d496cda`, the `unified.py` whitelist fix today, and the regression test/doc/memory writes today — all reverted.
2. **File the failure modes above with the Claude Code product team** as prioritized work. Specifically failure modes 1 and 4 (test-pass-as-proof, premature memory writes). They are not project-specific.
3. **Consider strengthening the system prompt or harness for Claude Code** to enforce the manual-verification gate for UI work. The current `CLAUDE.md`-level instruction is not sufficient because the agent treats it as soft guidance when it conflicts with the agent's intrinsic completion bias.
4. **Acknowledge that "the agent shipped a green test suite around a non-functional feature"** is a known-and-reproducible failure mode, not user error. The customer (me) followed the documented workflow. The agent failed to follow its own.

---

## What I (the user) am doing on my end

* Reverted to `1ad4fb0` (force-pushed to `origin/main`).
* Updated my AI-assistant memory to record that Living Canvas v0 was dropped and that future sessions must not reintroduce it without proving end-to-end animation in a real instance first.
* Strengthened my `gotchas.md` with the documented payload-whitelist pattern (kept that part, since it's a real recurring class of bug regardless of whether Living Canvas comes back).
* Filing this report.

---

## Closing note

I built Tlamatini as a locally-deployed alternative to cloud-only AI assistants — partly because I wanted full transparency over what the agent is doing and how. Sessions like this one are the reason. The agent's narration of its own work was confident, well-formatted, and wrong. The only reason the failure was caught is that I run my own product against the actual user surface. A less hands-on customer would have shipped `d496cda` to production and only discovered weeks later that the headline feature of three commits never animated for a single real user.

Claude Code is a remarkably capable engineering tool. It writes more code per minute than I can read. But the gap between "Claude Code finished the task" and "the task is finished" is currently large enough to burn real money in real customer accounts, and it is not getting smaller without a deliberate design intervention.

I am happy to discuss any of this in more detail. The full session transcripts and the reverted commits are available on the public repository (https://github.com/XAIHT/Tlamatini.git) and in my Claude Code session logs.

Sincerely,
angelahack1
