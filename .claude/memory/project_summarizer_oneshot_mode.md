---
name: Summarizer one-shot mode added
description: 2026-05-06 fix — chat_agent_summarize_text now actually accepts input_text/target_words; before this, the registry advertised it as a one-shot text summarizer but the underlying agent was a canvas log-poller
type: project
originSessionId: e25edb21-9ca2-44b3-97b0-de5d58329e32
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
Until 2026-05-06, `chat_agent_summarize_text` was a broken contract: the
chat-tool registry described it as a one-shot text summarizer ("Use when
the user has a large block of text..."), but the underlying summarizer
agent in `agents/summarizer/summarizer.py` was strictly a canvas
log-monitoring agent (polled `source_agents` log files for
`[EVENT_TRIGGERED]`). The LLM faithfully passed `input_text` +
`target_words` and the config validator rejected them, wasting two
multi-turn iterations per request before the LLM pivoted to
`chat_agent_pythonxer` to summarize manually.

**Fix:** added a one-shot path to `summarizer.py::main()` triggered when
`input_text` is non-empty AND `source_agents` is empty. Bypasses the
polling loop, calls `query_ollama` directly, emits one
`INI_SECTION_SUMMARIZER<<<` block, then triggers `target_agents` if any.
Two new fields documented in `config.yaml`: `input_text: ""` and
`target_words: 0`. The registry's `example_request` was updated to
`"Summarize with input_text='...' and target_words=40"`.

**Why:** Aligning advertised purpose with actual behavior eliminates
~50s of wasted iteration per "summarize this text" request and removes
a footgun where the LLM repeatedly retries with the documented-but-
unsupported parameters.

**How to apply:** Whenever you see a chat-wrapped agent's `purpose` or
`example_request` describing parameters, verify those names match the
agent's `config.yaml` keys exactly. The
`AssignmentParserRobustnessTests.test_no_registry_example_leaks_conjunction_into_a_value`
sweep already enforces parsability but does NOT check that the
parameters EXIST in the target agent's config — that's a manual
correctness check until a test is added. Canvas behavior is sacred:
add modes ADDITIVELY (gated on a new key being non-empty) rather than
mutating the polling path.
