---
name: ACPXer agent — visual canvas counterpart of ACPX LLM tools
description: 2026-05-03 added ACPXer (#59) — a workflow agent that drives one ACPX session lifecycle from the canvas; it deliberately mirrors the runtime mechanics inline because pool subprocesses cannot import agent.acpx
type: project
originSessionId: 6515ec65-d71d-42cf-bda9-6514184e2998
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
ACPXer is the **visual workflow** counterpart of the 12 LLM-facing ACPX tools (`acp_spawn` / `acp_send_and_wait` / `acp_relay` / `acp_kill` / etc.). One ACPXer node on the ACP canvas = one full ACPX session lifecycle (spawn external coding-agent CLI → dispatch task → drain → harvest last-assistant text → kill → trigger `target_agents`).

**Why:** The 12 tools require the user to drive ACPX from chat (LLM operator turns). Visual / scheduled / .flw-saved / Croner-driven ACPX flows had no canvas representation before. ACPXer adds that representation — and via Parametrizer chaining (`Starter → ACPXer(claude) → Parametrizer → ACPXer(gemini) → ... → Ender`), it enables fully unattended visual multi-CLI relay flows with zero LLM operator turns.

**How to apply:**
- When the user asks for a visual / drawn / scheduled / unattended ACPX flow → use ACPXer nodes; do NOT propose the 12 chat tools.
- When the user asks for an interactive Multi-Turn ACPX flow in chat → use the 12 tools; do NOT propose ACPXer.
- The agent is at `Tlamatini/agent/agents/acpxer/acpxer.py` + `config.yaml`. **Self-contained** — does NOT import `agent.acpx.*`. Pool subprocesses run with no sys.path back into the Django app (frozen builds break otherwise), so the runtime mechanics (4-rule transport-aware drain, NDJSON transcript writer, last-assistant extractor, `agent_id` registry) are mirrored inline in ~120 lines. The transcript NDJSON format is byte-compatible with `agent.acpx.runtime.AcpSession.send_turn`. Don't try to "DRY this up" by importing from `agent.acpx` — that would silently break the frozen-build agent pool.
- Output contract: emits `INI_SECTION_ACPXER<<<` blocks with KV header `agent_id` / `session_id` / `transport` / `settle` / `transcript_path` and body = `response_body` (= last-assistant text). Registered in `parametrizer.SECTION_AGENT_TYPES` and `views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['acpxer']`.
- Migration: `0076_add_acpxer.py` (idAgent 72 in DB).
- CSS gradient: `.canvas-item.acpxer-agent` — Aurora Conduit (`#0B1F3A → #5A1FB8 → #EC4899 → #22D3EE`). Distinct from `.acpx-agent` (LLM-driven exec-report row, fire-orange) so the two surfaces don't visually collide.
- Pool naming: `acpxer_<n>` (underscores; the canvas form is `acpxer-<n>`).

**Reusable lesson** (added as pitfall #10 in `Tlamatini/.agents/workflows/create_new_agent.md`): any future workflow agent that needs to reproduce in-process Tlamatini runtime mechanics must port the logic inline rather than `from agent.* import ...` — the agent pool runs as separate Python subprocesses with no path back into the Django app. Use ACPXer's acpxer.py as the reference implementation for this pattern.
