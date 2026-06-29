---
name: project_prompt_catalog_mode_badges
description: Prompt catalog cards now show mode badges (One-Shot / Multi-turn / ACPX) and auto-set the Multi-Turn + ACPX toolbar checkboxes when a prompt is selected; tools_dialog.js + tools_dialog.css only
metadata: 
  node_type: memory
  type: project
  originSessionId: 1a71dd21-db6d-4b82-90fd-ae1bb71f8f48
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-30: Added per-prompt MODE INDICATOR BADGES + auto-checkbox-setting to the "Pre-established prompts" catalog (the `#prompts-catalog` "Catalog of prompts" modal). User wants each catalog card to show little square badges telling which toolbar checkboxes the prompt needs (**One-Shot** / **Multi-turn** / **ACPX**, a prompt can carry MORE THAN ONE), and selecting a card must SET those checkboxes (e.g. first/one-shot prompt → uncheck BOTH Multi-Turn & ACPX; "Skill Catalog Carnival" → check BOTH). Reference image: `c:\Development\Tlamatini\image.png` (BROWSER WIZARD shown with a teal "Multi-turn" pill).

**Where it lives (frontend ONLY — no model/migration/backend/endpoint change):**
- `agent/static/agent/js/tools_dialog.js` — the whole catalog renderer. Cards are built by `loadPrompt(promptName,index)`; prompts fetched one-by-one from `GET /agent/load_prompt/prompt-<i>/` (plain text = promptContent) in `loadPrompts()`; clicking a `.prompt-card` sets `#chat-message-input` and closes. Title comes from `extractPromptTitle` ("run the <Title> demo").
  - NEW top-level: `PROMPT_MODE_META` (label+css+tooltip per mode), `classifyPromptModes(content)`, `buildPromptModeBadges(modes)`, `setToolbarToggle(id,desired)`, `applyPromptModesToToggles(modes)`.
  - `loadPrompt` now computes `modes=classifyPromptModes(content)`, stores `card.dataset.modes`, and appends `buildPromptModeBadges(modes)` to `.prompt-card-header`.
  - click handler now also reads `dataset.modes` and calls `applyPromptModesToToggles(modes)`.
- `agent/static/agent/css/tools_dialog.css` — `.prompt-card-modes` + `.prompt-mode-badge` + `-multiturn`(teal, mirrors image) / `-acpx`(fire-orange→violet) / `-oneshot`(slate).

**Checkbox wiring (reused, do NOT bypass):** ids `#multi-turn-enabled` and `#acpx-enabled` (template `agent_page.html` ~L177/186). `setToolbarToggle` sets `.checked` then `dispatchEvent(new Event('change',{bubbles:true}))` so the EXISTING `agent_page_init.js` change handlers run (persistMultiTurnState/persistAcpxState + syncAskExecsAvailability) — same as a manual click. ACPX always implies Multi-Turn; classifier guarantees acpx⇒multiturn so ACPX is never set alone. Multi-Turn set first so Ask-Execs availability re-syncs against final MT state. Exec Report / Ask Execs deliberately untouched.

**Classifier (no DB mode field exists — Prompt model is only idPrompt/promptName/promptContent), VERIFIED 0/65 mismatches vs the real seeded prompts (frozen DB `C:\Tlamatini\_internal\db.sqlite3`, both a Python port AND the actual JS run in node):**
- **ACPX** ⇔ prompt CALLS an `acp_*`/skill tool (`acp_doctor|acp_spawn|acp_send|acp_send_and_wait|acp_relay|acp_kill|acp_transcript|acp_session_status|acp_list_sessions|list_acp_agents|invoke_skill|list_skills`) OR drives a named Skill (`code-review`/`security-audit` near "Skill"). **CRITICAL: scrub `do NOT use <…>` / `never use …` / `not use …` clauses FIRST** — 3 prompts (25 Unreal, 60 Unreal Snapshot, 63 STM32 Genesis) say "do NOT use acp_spawn"; a naive token match falsely flagged them ACPX. Scrub regex: `/(?:do\s+not|don['’]?t|never|not)\s+use\b[^.;]*[.;]?/gi`.
- **Multi-turn** ⇔ ACPX, OR `chat_agent_\w+`, OR the word `multi-?turn`.
- **One-Shot** ⇔ neither. Returns `['oneshot'] | ['multiturn'] | ['multiturn','acpx']`.
- Expected mapping of the 65-prompt catalog: 1-24 ONE-SHOT, 25 MT, 26-27 ACPX+MT (code-review/security-audit Skills), 28-30 MT, 31-50 ACPX+MT (real acp_*/skill demos), 51-65 MT (window/browser/desktop/kali/unreal/stm32 wrapped chat_agent demos). BROWSER WIZARD (p54)=MT-only matches the image.

**Verified:** classifier 0/65 (py+js); a DOM-stub test of `applyPromptModesToToggles` PASSES all 4 cases (start both-on → One-Shot clears both; MT→MT-only; ACPX+MT→both; back-to-One-Shot clears). eslint clean.

**Deploy:** frozen serves PLAIN static from `C:\Tlamatini\_internal\staticfiles\` (DEBUG-branch `CompressedStaticFilesStorage`, `WHITENOISE_AUTOREFRESH=True`, no manifest; `STATIC_VERSION`=startup timestamp). **Hot-deployed** both files into `_internal\staticfiles\agent\{js,css}\` + the `_internal\agent\static\agent\…` mirror → testable after app RESTART (new ?v) or hard-refresh, no full rebuild needed for the static part. A final `build.py --self-modify` was run anyway to fold this + the [[project_execute_file_foreground_fix]] compiled fix into one clean installer (the earlier execute_file-only build PREDATED these edits — installing that stale pkg.zip would overwrite the hot-deployed catalog). Not committed.

Future prompts auto-classify via the same heuristic (incl. the negation scrub); if a new prompt is misjudged, the fix is the regex in `classifyPromptModes` (single source of truth) — there is intentionally no DB column.
