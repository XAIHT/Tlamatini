---
name: project-reviewer-analyzer-demo-prompts
description: 2026-05-20 added two fancy seeded demo prompts for Reviewer/Analyzer (idPrompt 26/27) via migration 0090; documents the prompts-catalog contiguity contract
metadata: 
  node_type: memory
  type: project
  originSessionId: f6deb605-896b-4e17-8a8f-9483ac7f8cc7
---

2026-05-20: Added two "fancy" seeded demo prompts that showcase the Reviewer (code-review skill) and Analyzer (security-audit skill) agents, placed BEFORE the Multi-Turn sample prompts. Migration `Tlamatini/agent/migrations/0090_add_reviewer_analyzer_demo_prompts.py`. Slot 26 = CODE REVIEW SPOTLIGHT (`invoke_skill('code-review', {repo_path, diff_ref:'HEAD~1', focus})`), slot 27 = SECURITY AUDIT FLOODLIGHT (`invoke_skill('security-audit', {path, min_severity})`). Both use the agent's native canvas gradient for the banner (Reviewer teal→violet `#0E7490→#7C3AED`; Analyzer red→yellow `#7F1D1D→#FACC15`) and render banner + verdict-chip/severity-scoreboard + `exec-report-table` + closing banner. Both note the user must tick Multi-Turn AND ACPX (invoke_skill is behind the ACPX/Skill surface).

**Why the renumber:** the prompts-catalog dropdown JS (`static/agent/js/tools_dialog.js::loadPrompts`) iterates `prompt-1, prompt-2, ...` and **BREAKS at the first missing `prompt-N`**. So the catalog MUST stay a contiguous, gap-free `prompt-1..N`, and **display order = the numeric suffix in `promptName`, not the idPrompt PK** (though they're kept equal by convention). `load_prompt_view` fetches by `promptName`. Slots 1-25 were full (Unrealer owns 25), so 0090 shifts every Prompt with idPrompt>=26 UP by +2 — renumbering BOTH `idPrompt` and `promptName`, in collision-safe order (descending for +2, ascending for the -2 reverse). No model FKs `Prompt` (PK is a plain IntegerField), so `.update()` PK reassignment is safe. Post-shift: Multi-Turn demos 26-28→28-30, ACPX demos 29-48→31-50.

**How to apply:** to insert a prompt before an existing slot, you must shift the suffix of all later prompts (idPrompt + promptName) to preserve contiguity — never leave a gap or the dropdown silently truncates. Verified: forward+reverse migrate round-trips cleanly (50↔48, contiguous, names consistent), ruff clean, `makemigrations --check` shows no drift. Updated 0002's docstring (the authoritative idPrompt-range map) with a forward-pointer to 0090. See [[project_reviewer_analyzer_agents]]. NOTE: README.md line ~1034 already mislabels the Unrealer demo as "idPrompt 32" (it's 25) — pre-existing, unaffected by this change, left untouched.
