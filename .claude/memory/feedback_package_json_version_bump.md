---
name: feedback-package-json-version-bump
description: "On release version bumps, also bump package.json \"version\" — user wants it tracked despite the git-tag-only contract"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7430c470-cf56-4aa8-ad56-69e521bf07f3
---

When doing a release version-bump pass across the docs, ALSO bump the `"version"` field in repo-root `package.json` to the pushed version.

**Why:** On 2026-05-20 (v1.4.1 doc bump) I flagged that package.json was at the npm-default `1.0.0` and was NOT part of Tlamatini's version system — `VERSIONING.md` says the version lives only in git tags and is "never hand-edited in source files," and package.json isn't in its file-by-file list. I recommended leaving it; the user explicitly chose **Bump to 1.4.1**. So the standing preference is: package.json's version should mirror the release for surface-level consistency, even though it's a hand-edited string outside the git-tag resolver.

**How to apply:** Each release, edit `package.json` `"version"` to the new bare version (e.g. `1.4.2`) alongside the markdown current-version surfaces (README badge, [[project_versioning_2026_05_15]] examples in VERSIONING.md / BookOfTlamatini §48 / README §13). The git-tag-derived runtime resolver still ignores it — this is purely a manifest-consistency bump.

**On historical changelog entries — ASK each time; the answer has flip-flopped, so do NOT assume:** v1.4.1 bump → user PINNED historical, moved only current-state. **v1.4.2 bump (2026-05-20)** → user said "change it everywhere!" and chose **rewrite everything including historical/dated entries**. **v1.5.0 bump (commit 172df1e)** → PINNED historical again ("shipped in v1.4.2" attributions left pinned). **v1.6.0 bump (2026-05-21)** → when asked, user explicitly chose **"Current surfaces only"** — bump badge/package.json/VERSIONING+README+Book runtime&release EXAMPLES + the doc-gen "current release state" line, but PIN historical "shipped in vX" attributions (e.g. the 5 "Playwrighter is the 65th agent in v1.5.0" lines in `complete_project_docs.py`) and dated changelog entries to their real shipping versions. So 3 of the last 4 bumps pinned historical; the lean is toward PIN, but it HAS flipped — surface the question with a clear two-option choice (current-surfaces-only vs everything) and the factual-accuracy caveat. Third-party dep pins (`odfpy==1.4.1`, `natural-compare@1.4.0`) are excluded regardless — changing them breaks the build. Scope each bump to the current `MAJOR.MINOR` line; never touch older lines.

**Doc-gen PDF/PPTX note:** `Tlamatini/agent/doc_generation/complete_project_docs.py` derives the cover/version surfaces dynamically via `agent.version.get_version_info()` (line ~483) and the agent count via `context["workflow_agent_count"]` — so the committed binaries (`tlamatini_app_summary.pdf`, `test_output.pdf`, the `.pptx`) are stale SNAPSHOTS that pick up the new version + count automatically when regenerated AFTER the git tag is cut. The only hardcoded current-state version string in that file is the "newer `vX.Y.Z` release state" line (~656); everything else is either dynamic or a pinned Playwrighter-shipped-in-v1.5.0 historical narrative. Don't binary-edit the PDFs/PPTX; regenerate from source post-tag (and ideally refresh the Playwrighter→Windower headline narrative for a true 1.6.0 deck).
