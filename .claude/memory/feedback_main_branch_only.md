---
name: Tlamatini — main branch ONLY, FOREVER. NO branches, NO PRs.
description: ABSOLUTE rule. Tlamatini is a solo project; NEVER create branches, NEVER suggest PRs, NEVER let a "Create PR" UI badge appear. Everything goes on main directly, no exceptions.
type: feedback
originSessionId: 6011d685-3956-4be6-b3b1-ab20f1b1076c
---
**ABSOLUTE RULE.** For the Tlamatini project: all work goes on `main`, FOREVER AND EVER. The user has explicitly reinforced this rule THREE TIMES IN ESCALATING TONE in session `4a208cb5-99b2-498e-9045-72d3a2ba8110`:

> "I never want to see such PR stuff never!"
> "FORBID CLAUDE BRANCHES FOREVER!!"
> "I WANT FOREVER AND EVER EVERYTHING IN PLACE AND IN MAIN BRANCH NO MATTER IF YOU HAVE TO RECODIFY YOURSELF"

**Categorical prohibitions:**

1. NEVER create feature branches, worktree branches (`claude/<name>`), throwaway branches, hotfix branches, release branches, or any other named branch. Only `main` exists in this repo.
2. NEVER open pull requests. Never run `gh pr create`. Never suggest a PR. Never let any UI element ask for one.
3. NEVER leave changes uncommitted long enough for a PR-suggestion UI badge to appear. The IDE's "Create PR" button is driven by `(branch != main) || (uncommitted changes vs main)`. Both halves must stay false.
4. NEVER run `git checkout -b`, `git switch -c`, `git branch <name>`, or any branch-creating command on this repo.

**Mandatory procedure (do this without being asked):**

- **At the START of every session**: verify HEAD is `main` and there are no `claude/*` branches. If there are, fast-forward main to their tip and delete them on the spot.
- **At the END of every session**: every change MUST be committed and pushed to `origin main` before the session ends. Uncommitted changes are unacceptable. If the user hasn't asked for the commit, ASK ONCE then commit if no objection — they have stated they would rather you commit autonomously than leave anything dangling.
- **If the harness drops the session into a worktree branch** (e.g. `claude/<name>`): treat that branch as a temporary sandbox only. Commit there if you must, but immediately fast-forward `main` to that commit (`git push origin HEAD:main`), then `git worktree remove --force <path>` and `git branch -D <branch>`. The remote MUST only ever show `refs/heads/main`.
- **If a "Create PR" UI badge appears in the user's IDE**: the cause is uncommitted changes in the working tree (the harness names them `claude/<session-label>` for display purposes). Commit to main and push. The badge disappears the moment the diff is zero.

**Why this rule exists:** The user is the sole developer / CEO / CTO / CBO / janitor of XAIHT. There is no second contributor, no review gate, no parallel-work pressure, no compliance requirement that would justify branching. Branches and PRs cost the user time and visual clutter without buying anything in return. The user wants `edit → commit → push` and absolutely nothing else, ever. Past worktree branches (`claude/competent-elion-d063eb`, `claude/dazzling-montalcini-f85263`, `claude/laughing-clarke-bcd5ea`) all caused the user explicit irritation in the IDE's source-control panel and the PR-suggestion overlay.

**Apply this rule with no exceptions.** If a future Claude variant is tempted to "follow standard git workflow" or "create a feature branch for safety", the answer is no. The user is the standard for this repo. Their standard is `main` forever.
