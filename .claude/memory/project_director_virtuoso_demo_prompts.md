---
name: project_director_virtuoso_demo_prompts
description: "2026-05-21 added two ADVANCED multi-agent demo prompts (slots 55/56) via migration 0096; catalog now runs 1-56, next free slot is 57"
metadata: 
  node_type: memory
  type: project
  originSessionId: f483c755-1dd5-423b-8d4c-5897213a26a3
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-21: Added two **advanced, more-visual** demo prompts to the Catalog of Prompts, beyond the basic/medium 0095 set. Migration `Tlamatini/agent/migrations/0096_add_director_virtuoso_demo_prompts.py`, APPENDED at the tail (slots 55-56, NO renumber — catalog stays contiguous 1-56):

- **55 DESKTOP DIRECTOR** — conducts the whole desktop-UI trio in one flow: `chat_agent_executer`(launch Notepad) → `chat_agent_windower`(move_resize stage center) → `chat_agent_mouser`(movement_type='click_at_window' to place the caret) → `chat_agent_keyboarder`(types a multi-line Nahuatl-themed message, stride_delay=70 so keystrokes are visible) → six Windower moves dance the text-filled window (arrange left/right/top-right, maximize, restore, topmost) → list → exec-report "Desktop Director Trace" table → close (+alt+n discard). Windower-advanced blue gradient banner (#0B1E3A→#1E6FB8→#22D3EE→#A7F3D0).
- **56 BROWSER VIRTUOSO** — `chat_agent_playwrighter` (headless=false, hold_open_seconds=12) drives Wikipedia like a touch-typist: 14-step steps_json = visible per-key `type` (delay:140) → screenshot typed query → `press` Enter to submit → wait_for → extract_text title+lead → `extract_attr` link[rel=canonical] href → assert_text/assert_visible → screenshot article → `press` End (keyboard scroll) → wait → full-page screenshot. Renders STEP SCOREBOARD chips + "Browser Virtuoso Result" exec-report table + lead-paragraph blockquote. Playwrighter 4-stop gradient (#3D1766→#D90368→#0FA3B1→#6EE7B7).

Both drive the wrapped `chat_agent_*` tools → **Multi-Turn ONLY, NOT ACPX** (same contract as 0095, unlike the 0090 skill demos). All params validated against `chat_agent_registry.py` purposes + the agents' `config.yaml`; the embedded steps_json parses to 14 valid steps. Avoided single quotes inside steps_json so the wrapped-tool flat key=value splitter's single-quote protection isn't tripped.

Verified: forward+reverse migrate round-trips clean (54↔56, always contiguous), `makemigrations --check` no drift, ruff clean. Updated 0002_populate_db.py docstring map with the 0096 NOTE (the established convention — see [[project-reviewer-analyzer-demo-prompts]]). **Next free demo-prompt slot is 57** — to insert before an existing slot you must shift later prompts' idPrompt+promptName to preserve contiguity (the dropdown `tools_dialog.js::loadPrompts` breaks at the first gap); appending at the tail needs no shift. No agent-doc update needed (Windower/Playwrighter already shipped). Related: [[project-windower-agent]], [[project_playwrighter_agent]], [[project_playwrighter_hold_open]].
