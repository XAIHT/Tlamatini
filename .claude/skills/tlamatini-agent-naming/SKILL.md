---
name: tlamatini-agent-naming
description: The authoritative Tlamatini agent NAMING CONVENTION — invoke before adding, renaming, casing, displaying, or auditing any workflow agent (STM32er, Node Manager, ACPXer, Kalier, ...). Use whenever you touch agentDescription, a pool/agent directory, a CSS .canvas-item class, a JS connection handler, agents_descriptions.md, or any place an agent name is shown. Prevents mis-casing display names (e.g. STM32er must never become STM32Er/STM32ER/Stm32Er).
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Tlamatini Agent Naming Convention

The **single source of truth** for an agent's name is the **`agentDescription`** field on its
`Agent` DB row (seeded by the agent's migration, e.g. `0101_add_stm32er`). The canvas
`agentic_control_panel.html` renders that string **verbatim** as the sidebar/canvas label
(via `consumers.AgentConsumer.agent_establishment(agentName, agentDescription, agentContent)`
→ the JS palette). So the display name must carry the exact intended casing.

## The per-context transform table — memorize and apply

| Context | Casing | `STM32er` | `Node Manager` |
|---|---|---|---|
| **Display** — DB `agentDescription`, sidebar/canvas label, `agentic_control_panel.html`, tooltips, `agents_descriptions.md` row header `\| **Name** \|`, `chat_agent_registry.display_name`, docs prose, the agent's own `"<Name> AGENT STARTED"` log | **exact, as designed** | `STM32er` | `Node Manager` |
| Pool dir / agent dir / `<name>.py` / pool name `<name>_N` | lowercase | `agents/stm32er/stm32er.py`, `stm32er_1` | `agents/node_manager/`, `node_manager_1` |
| CSS class `.canvas-item.<x>-agent` + JS classMap key + connection checks `name.toLowerCase()` | lowercase / dash | `stm32er-agent`, `'stm32er'` | `node-manager-agent`, `'node manager'` |
| JS connector symbol `update<Name>Connection` | PascalCase-ish identifier (NOT a label) | `updateStm32erConnection` | `updateNodeManagerConnection` |
| `INI_SECTION_<TYPE>` / `END_SECTION_<TYPE>` protocol tokens + FlowHypervisor `<TYPE> SPECIAL NOTES:` headers | **ALL-CAPS** (separate convention) | `INI_SECTION_STM32ER`, `STM32ER SPECIAL NOTES` | `INI_SECTION_NODE_MANAGER` |

## Hard rules

1. **Display name = exact case.** For STM32er that is precisely `S` `T` `M` `3` `2` `e` `r` → **`STM32er`**. NEVER write `STM32Er`, `STM32ER`, `Stm32Er`, or `Stm32er` as the display / `agentDescription` (the user is emphatic — they program mission-critical robots and have corrected this repeatedly).
2. **Lowercase everything else** by `name.toLowerCase().replace(/\s+/g,'-')` for CSS/classMap, `name.toLowerCase()` for connection checks, and the bare lowercased token for the directory / pool name.
3. **Do NOT "fix" the ALL-CAPS protocol tokens** (`INI_SECTION_*` / `END_SECTION_*`) or the FlowHypervisor `* SPECIAL NOTES:` headers to mixed case — those are an intentional, separate convention shared by every agent.
4. When **adding or renaming** an agent: set `agentDescription` to the exact display casing in the migration, then derive every other surface by lowercasing. Follow `Tlamatini/.agents/workflows/create_new_agent.md` and update `agents_descriptions.md`, `agentic_skill.md`, `README.md` in the same pass. **Sibling convention:** the same pass must honor the **Temp/Templates directory policy** — an agent that writes temp files routes them under `<app>/Temp` (`TLAMATINI_TEMP`); a firmware/engine agent that scaffolds projects defaults to `<app>/Templates` (`TLAMATINI_TEMPLATES`). See `prompt.pmt` Rules 15/16, `agent/path_guard.py`, and `docs/claude/recent-fixes.md` (2026-06-02).
5. When **auditing** casing: the ONLY surfaces allowed to differ from the display name are the lowercase identifiers (rule 2) and the ALL-CAPS protocol tokens (rule 3). Anything else showing a different casing of the name is a bug — fix it.

## Quick check command

```bash
# Any wrong-cased STM32er DISPLAY occurrences (excludes the legit lowercase
# identifiers and the ALL-CAPS INI_SECTION protocol tokens):
grep -rnE "Stm32Er|STM32Er" --include=*.py --include=*.md --include=*.pmt --include=*.html .
```
