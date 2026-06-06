---
name: project-reviewer-committed-secrets-falsepos
description: "2026-05-20 fix — Reviewer agent + code-review skill falsely reported working-tree API keys as \"committed\"; taught both commit-state precision + the regen_secrets scrub convention"
metadata: 
  node_type: memory
  type: project
  originSessionId: f6deb605-896b-4e17-8a8f-9483ac7f8cc7
---

2026-05-20: The Reviewer agent and `code-review` skill were falsely reporting "API keys and passwords are committed."

**Root cause:** committed HEAD of `agent/config.json` and `agent/agents/*/config.yaml` carries scrubbed `<NAME goes here>` placeholders, but the developer's WORKING TREE holds real keys (the local "keyed" mode from `regen_secrets.py` + gitignored `data.keys`). The Reviewer runs `git diff` (empty `diff_ref` => `git diff HEAD` + `--staged`, i.e. UNCOMMITTED changes) and `build_review_prompt` never told the LLM the commit-state, so the model defaulted to alarming "committed to source" language for keys that are not in any commit.

**Fix (both surfaces):**
- `agent/agents/reviewer/reviewer.py::build_review_prompt(...)` now takes `diff_ref` and prepends (a) a COMMIT-STATE block — for empty diff_ref it forbids the words "committed"/"pushed" (working-tree/staged only); for a real ref it says committed is valid — and (b) a SECRET-HANDLING CONVENTION block describing the `regen_secrets.py --mode push-able` scrub workflow so managed-config real values in an uncommitted diff are NOT reported as committed secrets (placeholders/empty never flagged; genuine secrets in source code or outside the managed set or in real history STILL hard-flagged). Call site passes `diff_ref`.
- `agent/skills_pkg/code_review/SKILL.md`: reworded the Security axis ("secrets committed to source" -> "hard-coded secrets"), added commit-state precision to the resolve-diff step, and added a "## Secret findings — read before flagging credentials" section with the same two rules.

**Deployment:** the report came from the FROZEN install at `C:\Tlamatini` (has `Tlamatini.exe`; pool agents at top-level `C:\Tlamatini\agents\reviewer\reviewer.py`; skills at `C:\Tlamatini\agent\skills_pkg\...` AND `C:\Tlamatini\_internal\agent\skills_pkg\...`). Source fix alone doesn't reach a frozen install, so I copied the fixed `reviewer.py` (verified identical-minus-fix first) and SKILL.md into all three install paths. To pick up the skill change in a RUNNING app: ACPX-Skills -> Reload Registry (or restart). Reviewer agent change takes effect on the next flow Start (template re-copied into a fresh pool). Verified: py_compile + ruff clean, prompt renders correctly for both commit-states, SKILL.md frontmatter parses. See [[project_reviewer_analyzer_agents]] and [[project_reviewer_analyzer_demo_prompts]].

NOTE TO SELF: the working tree genuinely holds real keys in tracked files (config.json: Anthropic/Gemini/OpenAI; agent config.yaml: api_id/api_hash) — not committed (HEAD scrubbed), but a `git commit -a` without scrubbing would leak them. Always remind the user to run `regen_secrets.py --mode push-able` before committing.
