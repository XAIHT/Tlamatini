---
name: Always update agent docs when modifying agents
description: When adding or modifying workflow agents in Tlamatini, also update the agent documentation files
type: feedback
originSessionId: b8a2266e-dd47-49d9-8f3f-a4e91da6f11b
---
When any workflow agent (in `Tlamatini/agent/agents/<name>/`) is added, renamed, or has its behavior/connection semantics changed, update the documentation files in the same commit:

- `Tlamatini/.agents/workflows/create_new_agent.md` — the step-by-step agent creation guide
- `Tlamatini/agent/agents/flowcreator/agentic_skill.md` — the FlowCreator AI reference so the LLM can design flows using the agent
- `README.md` — agent count, project structure, classification, workflow table, glossary, changelog, API table
- Any other `*.md` that catalogues agents

**Why:** the LLM-driven FlowCreator agent relies on `agentic_skill.md` to know what agents exist and how to wire them. Undocumented agents silently become unreachable to the planner. The user values robustness and uniformity — drift between code and docs breaks both.

**How to apply:** treat the doc updates as part of the agent change itself, not a follow-up task. If the user's request is a pure agent modification, do the docs in the same pass without being asked.
