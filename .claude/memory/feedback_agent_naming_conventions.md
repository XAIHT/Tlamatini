---
name: feedback_agent_naming_conventions
description: CRITICAL — Tlamatini agent naming convention. Display name keeps exact case (STM32er); dirs/pool/CSS/JS-symbols are lowercase (stm32er). Never mis-case a display name.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---

The single source of truth for an agent's name is the **`agentDescription`** column on the `Agent` DB row (seeded by the agent's migration). The canvas sidebar/`agentic_control_panel.html` renders that string **verbatim** (via `consumers.agent_establishment(agentName, agentDescription, agentContent)` → JS palette label), so the display name MUST carry the exact intended casing.

**Per-context transforms (memorize):**
- **Display name** (DB `agentDescription`, sidebar/canvas label, `agentic_control_panel.html`, tooltips, `agents_descriptions.md` row header `**Name**`, `chat_agent_registry` `display_name`, docs prose, the agent's own `"<Name> AGENT STARTED"` log): **exact case, as designed** — e.g. `STM32er`, `Node Manager`, `ACPXer`, `Kalier`, `J-Decompiler`, `TeleTlamatini`.
- **Pool dir / agent dir / `<name>.py` / pool name `<name>_N`**: **lowercase** — e.g. `agents/stm32er/stm32er.py`, `stm32er_1`.
- **CSS class** (`.canvas-item.<x>-agent`) + **JS classMap key** + **connection-handler checks** (`name.toLowerCase()`): **lowercase / dash** — e.g. `stm32er-agent`, `'stm32er'`, `=== 'stm32er'`.
- **JS connector function symbol**: PascalCase-ish `update<Name>Connection` — e.g. `updateStm32erConnection` (a code identifier, NOT a display label — leave as the established pattern).
- **`INI_SECTION_<TYPE>` / `END_SECTION_<TYPE>` protocol tokens** + the FlowHypervisor `<TYPE> SPECIAL NOTES:` headers: **ALL-CAPS** (`INI_SECTION_STM32ER`, `STM32ER SPECIAL NOTES`) — a separate house convention; do NOT "fix" these to mixed case.

**STM32er is the live example the user is emphatic about:** display = exactly `S T M 3 2 e r` (`STM32er`). NEVER write `STM32Er`, `STM32ER`, `Stm32Er`, or `Stm32er` as the display/agentDescription. (A dev DB once carried `Stm32Er` at idAgent 59 — wrong; corrected to `STM32er`. Migration `0101` already seeds `STM32er`.)

**Why:** the user runs Tlamatini for mission-critical robot firmware (STM32er); a mis-cased name in the panel is unacceptable to them and they have corrected it repeatedly.

**ROOT-CAUSE GOTCHA (2026-05-26):** the canvas sidebar label is NOT the migration's `agentDescription` — `agent/apps.py::AgentConfig.ready()` **DELETES all Agent rows and RE-SEEDS them on every server start** (guarded to `runserver`/`startserver`/`daphne`/`asgi` in argv), deriving `agentDescription` from the lowercase pool-dir name via Python `str.title()`. `'stm32er'.title()` → `'Stm32Er'` (title-cases the letter after the digit). So the migration row AND any manual DB edit get clobbered on the next `runserver`. The REAL fix for a mis-cased canvas name is an explicit override in that apps.py `.title()` block (it already special-cases AND/OR/Monitor Log/RecMailer); added `elif display_name.lower()=='stm32er': display_name='STM32er'`. `manage.py shell`/`test` do NOT trigger the re-seed (guard), so verify the name by actually running `runserver` then querying. Other agents are still `.title()`-mangled in the sidebar (Acpxer/De Compresser/Flowcreator/Ssher/Teletlamatini/...) — only stm32er was fixed per the user's demand; the rest await a request (sources disagree: agents_descriptions.md has 'Ssher'/'NodeManager', chat_agent_registry has the proper casings).

**How to apply:** when adding/renaming an agent, set `agentDescription` to the exact display casing in the migration AND add an override in `apps.py` ready() if `.title()` would mangle it; derive everything else by lowercasing. When auditing, only the lowercase identifiers + the ALL-CAPS protocol tokens may differ from the display name. See the project skill `tlamatini-agent-naming` and `Tlamatini/.agents/workflows/create_new_agent.md`. Related: [[project_stm32er_agent]], [[project_stm32er_bootstrap_preflight]], [[feedback_update_agent_docs]].
