<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# 2026-10-03 — Prompt Flow documentation and process cleanup

## Request, verbatim

```text
Ok, now update all all all all all all all, all the related hundreds of documents, all the mardown documents that apply!, go!, **AND PLEASE STOP ALL YOUR BACKGROUND PROCESSES, GO
```

## Scope

Audited all **204 Markdown files** present at the start of this follow-up, including hidden assistant instructions, skills and memories. Generated files under Temp, Git internals, dependencies and build outputs were excluded. Updated **27 applicable Markdown documents** (including this record and one new project memory); unrelated documents and dated release/test facts were preserved. The original refactor already passed its implementation checks; this follow-up changes documentation only.

Current descriptions now cover seven executable operations and a separate static User Commentary asset; the notched User Input figure with unchanged reply/cancellation behavior; inline commentary writing, palette/font/style/size controls, automatic full-text containment without internal scrollbars, resizing/Undo/Redo and portable/draft persistence; no annotation ports/Start/history/model/step effects; version 2 saves and version 1 executable-commentary migration; the compatible browser-draft key; limits, cache suffix, source/update carriage and visible verification/cleanup instructions.

Historical entries retain the old executable User Commentary name and version 1 format as dated facts; the current 2026-10-03 contract supersedes their behavior. No release tag/version, installer, executable, database backup/restore mechanic, or Git history was changed. Prior source changes and unrelated local edits are preserved.

## Updated files

- `.claude/memory/MEMORY.md`
- `.claude/memory/project_prompt_flow_commentary_input.md`
- `.claude/skills/tlamatini-daily-chat-test/SKILL.md`
- `.claude/skills/tlamatini-self-modify-inclusion/SKILL.md`
- `.claude/skills/tlamatini-self-update-inclusion/SKILL.md`
- `.gemini/skills/tlamatini-daily-chat-test/SKILL.md`
- `.gemini/skills/tlamatini-self-modify-inclusion/SKILL.md`
- `.gemini/skills/tlamatini-self-update-inclusion/SKILL.md`
- `ACPX.md`
- `AGENTS.md`
- `BookOfTlamatini.md`
- `CLAUDE.md`
- `GEMINI.md`
- `KIMI.md`
- `PIVOT_CHANGES.md`
- `README.md`
- `Tlamatini/agent/Tlamatini.md`
- `Tlamatini/agent/skills_pkg/tlamatini_static_version_bumper/SKILL.md`
- `docs/changes/2026-10-03-prompt-commentary-input.md`
- `docs/changes/2026-10-03-prompt-flow-documentation.md`
- `docs/claude/INDEX.md`
- `docs/claude/architecture.md`
- `docs/claude/frontend.md`
- `docs/claude/gotchas.md`
- `docs/claude/multi-turn.md`
- `docs/claude/recent-fixes.md`
- `docs/prompting-flow-designer.md`

## Verification and cleanup

The Markdown inventory/reference search and final verification ran in forked consoles whose actual visible/non-minimized/foreground HWND was checked before the workload. Documentation checks inspect changed relative links, active contracts, mirrored Claude/Gemini maintenance sections, source constants and the generated follow-up patch, followed by `git diff --check`. Final results are retained in `Temp/prompt-docs-verify.log` and `Temp/prompt-docs-verification.json`. The completed check passed: 27 updated Markdown files, 17 changed relative links checked, matching maintenance mirrors/current source constants, no missed applicable files in the audited inventory, and `git diff --check` exit 0. The final owned-background-process count and remaining test-listener count were both zero. Implementation evidence remains the earlier 61 backend/packaging tests and nine real foreground Chrome checkpoints; those product tests were not rerun for prose-only edits.

The owned browser harness closed Chrome and its isolated test server through `Temp/prompt-commentary-visible/close.confirmed`. Remaining task-owned verification workers/consoles were terminated, preserving unrelated user applications. The final process audit checks exact task script/profile command lines and test listeners on ports 8001, 8766, 50051 and 50052. Temporary documentation consoles close after finishing their visible checks; no polling loop or background worker is retained.

## Precise rollback

[The adjacent follow-up patch](2026-10-03-prompt-flow-documentation.patch) captures changed blocks against each file immediately before this documentation request, including the already-accepted implementation documentation. It does not replace or regenerate [the original refactor patch](2026-10-03-prompt-commentary-input.patch). Inspect the affected blocks manually before reversal so later edits remain intact; do not reset the working tree or rewrite Git history. Newly created documents have `/dev/null` before-images. The private before-copies under `Temp/prompt-docs-before/` support this capture and are not release assets.
