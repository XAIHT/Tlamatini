# docs/claude/ — Tlamatini AI-Assistant Docs Index

This directory holds the specialized onboarding documents that back the root `CLAUDE.md`. The root file imports each of these via `@docs/claude/<name>.md` so that every assistant session loads the full set automatically.

One-line descriptions:

- **architecture.md** — Configuration, system prompt & identity, the Five Layers of the system, application log (`tlamatini.log`), doc generation pipeline, database models.
- **multi-turn.md** — Multi-Turn mode, short follow-up message scoring, "Create Flow" pipeline, unified section format used by Parametrizer.
- **exec-report.md** — The Exec Report feature end-to-end: scope map, capture/render pipeline, strict ordering contract, styling, how to add a new state-changing agent to the report.
- **agents.md** — 8-step guide for creating a new workflow agent, naming convention transforms, agent lifecycle, connection fields, catalog of all 57 agent types, FlowCreator AI skill, FlowHypervisor monitoring.
- **mcp-tools.md** — How to add a new MCP-backed context provider or a unified-agent tool, plus the hardcoded-assumption warnings around `factory.py` and the MCP UI.
- **frontend.md** — Chat interface modules, ACP workflow designer modules, the **ACP Canvas DOM Contract** (`#submonitor-container` vs `#canvas-content`), shared modules.
- **gotchas.md** — Claude API client, build/packaging/linting commands, known hardcoded assumptions, recent fixes to remember, roadmap of recommended new agents, work-style preferences for AI assistants.

Read order when joining the project cold: root `CLAUDE.md` → `architecture.md` → `multi-turn.md` → `exec-report.md` → `agents.md` → `mcp-tools.md` → `frontend.md` → `gotchas.md`.
