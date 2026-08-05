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

> ### ⛔ CORRECTED 2026-07-26 — the migration is NOT the source of truth
>
> `agent/apps.py::AgentConfig.ready()` runs **`Agent.objects.all().delete()` on EVERY server
> start** and re-seeds the table from the `agents/` folder listing. A migration's
> `agentDescription` — and any manual DB edit — is **overwritten on the next launch**.
> The boot resolver `_canonical_agent_display_name()` reads
> **`agent/services/agent_paths.py::display_name_from_agent_type`**, so **THAT `overrides` map
> is the real single source of truth.** Add every new/renamed agent there or `str.title()`
> names it and it ships mangled — this is precisely how PDFer shipped as **"Pdfer"**
> (plus Sqler / Ssher / Pser / Scper / Acpxer / Esp32Er / Esphomer / Videoplayer /
> Audioplayer / Flowcreator / Teletlamatini …, 22 of 86 agents). The newest case is
> **LaTeXer** (agent #87): `str.title()` renders `"Latexer"`, so `agents/latexer` carries an
> explicit override. Its display name is LaTeX's own capitalisation plus the Tlamatini
> `-er` suffix — `L` `a` `T` `e` `X` `e` `r` → **`LaTeXer`**, never `Latexer` / `LaTexer` /
> `LATEXER`. Pinned by `test_agent_display_names.py::test_latexer_is_exactly_LaTeXer`.
>
> **HYPHEN vs SPACE IS FUNCTIONAL.** `acp-canvas-core.js` compares
> `targetAgentName.toLowerCase()` **without collapsing whitespace**, and for eleven agents it
> tests ONLY the hyphenated literal: `Kyber-KeyGen`, `Kyber-Cipher`, `Kyber-DeCipher`,
> `J-Decompiler`, `Video-Analyzer`, `De-Compresser`, `File-Creator`, `File-Extractor`,
> `File-Interpreter`, `Image-Interpreter`, `Monitor-Log`. A spaced name matches nothing and
> the canvas connection is **silently never saved**. (`Node Manager` / `Monitor Netstat` /
> `MCP Doctor` stay SPACED — the JS accepts both forms for those.)
>
> **CHANGE BOTH SIDES IN ONE PASS.** `chat_agent_registry.display_name` keys the per-agent
> enable gate `agent_<display>_status`, which **fails open** — so renaming only `agent_paths`
> silently breaks the *Configure Agents* checkbox instead of erroring.
>
> **TWO MORE SURFACES carry the display name verbatim** (found by the post-rename
> sweep, both now pinned by tests): `agentic_control_panel.css`
> `.agent-tool-item[data-content="<Display>"]` (CSS attribute values are
> CASE-SENSITIVE) and `agent_page_chat.js::_agentPurpose`'s `{'<Display>': …}` map.
> After editing either, run `collectstatic` — the collected `staticfiles/` copies are
> what actually get served.
>
> Verify with `python manage.py test agent.test_agent_display_names`. Full story:
> `docs/claude/recent-fixes.md` (2026-07-26).

The **display name** an agent shows is resolved at boot from
`agent_paths.display_name_from_agent_type` into the **`agentDescription`** field of its
`Agent` DB row (a migration such as `0101_add_stm32er` should seed the same exact string —
it is what a fresh DB shows before the first boot). The canvas
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
4. When **adding or renaming** an agent: **FIRST** add `"<agent_dir>": "<Exact Display Name>"` to the `overrides` map in `agent/services/agent_paths.py::display_name_from_agent_type` (the boot repopulate reads it and overwrites the DB), **then** set the same exact string as `agentDescription` in the migration and as `chat_agent_registry.display_name`, then derive every other surface by lowercasing. Follow `Tlamatini/.agents/workflows/create_new_agent.md` and update `agents_descriptions.md`, `agentic_skill.md`, `README.md` in the same pass. **Sibling convention:** the same pass must honor the **Temp/Templates directory policy** — an agent that writes temp files routes them under `<app>/Temp` (`TLAMATINI_TEMP`); a firmware/engine agent that scaffolds projects defaults to `<app>/Templates` (`TLAMATINI_TEMPLATES`). See `prompt.pmt` Rules 15/16, `agent/path_guard.py`, and `docs/claude/recent-fixes.md` (2026-06-02).
5. When **auditing** casing: the ONLY surfaces allowed to differ from the display name are the lowercase identifiers (rule 2) and the ALL-CAPS protocol tokens (rule 3). Anything else showing a different casing of the name is a bug — fix it.

## Quick check command

```bash
# Any wrong-cased STM32er DISPLAY occurrences (excludes the legit lowercase
# identifiers and the ALL-CAPS INI_SECTION protocol tokens):
grep -rnE "Stm32Er|STM32Er" --include=*.py --include=*.md --include=*.pmt --include=*.html .
```
