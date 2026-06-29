---
name: User owns git write operations; read-only is allowed
description: Read-only git commands (status/log/diff/show/blame) are always allowed. Any git command that mutates state (commit/push/stash/checkout-/reset/etc.) requires an explicit current-turn user request.
type: feedback
originSessionId: c4ba907a-c91d-4c2c-8f86-5b38594aaca7
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
The user is the only person authorized to execute git operations that change state on the Tlamatini repository. Read-only inspection is fine; writes require an explicit ask.

ALLOWED without asking (read-only, never mutate state):
- `git status`, `git status --short`
- `git log`, `git log --oneline`, `git log <range>`
- `git diff`, `git diff HEAD`, `git diff --stat`, `git diff <range>`
- `git show <ref>`
- `git blame <file>`
- `git branch -v` (listing only — never `-D`/`-d`)

FORBIDDEN without an explicit current-turn request:
- `git stash`, `git stash pop`, `git stash apply`
- `git checkout -- <file>`, `git restore`, `git reset` (any flavor)
- `git clean -fd`, `git rm`, `git mv`
- `git commit`, `git add`, `git push`, `git pull`, `git fetch`
- `git rebase`, `git cherry-pick`, `git revert`
- `git config`, `git tag`, `git branch -D`
- ANY other state-mutating `git <subcommand>` not on the allowed list.

**Why:** Tlamatini is the user's solo repo and the user wants control over state-changing git operations. Read-only inspection is genuinely useful (verifying which files I touched, seeing what's pre-existing, etc.) and the user has now clarified that the boundary is **mutate vs. inspect**, not "any git command at all." An earlier overly-broad reading of this rule would have prevented harmless verification work.

**How to apply:**
- "commit X", "push X", "stash X" — explicit ask, run the command.
- "ship X", "land X", "save X" — confirm whether they want a commit before running.
- For my own debugging ("is this failure pre-existing?", "what files did I modify?"), use the read-only commands above freely.
- The "work on main only" rule (feedback_main_branch_only) is still in force for any state-mutating op.
