---
name: project-unity-mcp-declined
description: 2026-05-17 — Uniter agent (Unity MCP analogue of Unrealer) was analyzed but explicitly NOT built; functionality too limited to justify
metadata: 
  node_type: memory
  type: project
  originSessionId: d193b695-d7fe-4b71-922d-23fdd6e12d4a
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

User declined to implement a Uniter agent (Unity-MCP counterpart of Unrealer) on 2026-05-17 after I delivered the full analysis/proposal.

**Why:** Unity MCP is much weaker than Unreal MCP for a Tlamatini-style integration:
- Relay binary (`%USERPROFILE%\.unity\relay\relay_win.exe --mcp`) is **closed-source**, so we can't pre-bake `arguments:` defaults in `config.yaml` the way Unrealer's YAML lists ~30 known param keys mirroring the upstream UE5 plugin's open C++ source.
- Unity does **not publish JSON schemas** for `Unity_*` tools; docs only name `Unity_ManageScene` / `Unity_ManageGameObject` / `Unity_ReadConsole` as examples with no argument specs.
- First connection from any new MCP client triggers a manual **Pending Connection** approval inside `Edit → Project Settings → AI → Unity MCP`, hurting Tlamatini's unattended-flow story.
- Requires Unity 6 (6000.0+) with the `com.unity.ai.assistant 2.0` package — a much narrower install base than UE5.
- Transport is stdio MCP JSON-RPC (would have required either a self-contained inline stdio client in `uniter.py` like `acpxer.py` mirrors the ACPX runtime, OR a `unity` entry in `agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS` — both viable, neither hard, but the payoff is low given the gaps above).

**How to apply:** Do NOT re-propose a Uniter / Unity MCP integration in future sessions unless the user explicitly asks again OR Unity ships (a) public JSON schemas for the `Unity_*` tool surface, (b) a way to bypass the per-client Pending Connection gate for trusted local clients, and (c) an open-source relay so we can bake sensible `arguments:` defaults. The analysis turn this decision came out of also drafted the full 21-file integration plan (mirroring the `[[project_acpxer_added]]` / Unrealer commit `0bea21d` pattern) — if the situation ever changes, the plan can be reconstructed quickly from this memory + the Unrealer files.
