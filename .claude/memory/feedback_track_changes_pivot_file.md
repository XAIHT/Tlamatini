---
name: feedback-track-changes-pivot-file
description: "Keep a pivot/changelog file recording the verbatim request + complete before/after of every change, so precise rollbacks never depend on git or on recalling a prior session"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9643457f-4a5c-4ebe-9aa5-a9b1914478f2
---

When I make changes for the user — **especially edits to `prompt.pmt`, the wrapped chat-agent wrapper (`tools.py` / `chat_agent_registry.py`), and agent `config.yaml` defaults** — I must keep a running record so a later "roll back just that last change" is exact and self-contained.

What to record per change: the user's **verbatim request**, the **files touched**, and the **complete before/after** of each edited block (not just a summary — enough to reconstruct the prior state byte-for-byte). A dated pivot/changelog file in the repo (e.g. extend `docs/claude/recent-fixes.md`, or a dedicated changes log) is the right home.

**Why:** Memory does NOT persist a prior session's actual diffs, and the user forbids destructive git for rollbacks because other valid uncommitted edits coexist in the working tree (see [[feedback_user_owns_git]], [[project_secret_leak_recovery]]). When the user later asked to "roll back the very last prompt.pmt + wrapper change," I had no record of what it was and couldn't reconstruct it from current files alone — the user had to fix it themselves. They said: "next time may not be as easy."

**How to apply:** Before/after each substantive change, append an entry to the pivot file capturing request + full before/after. Then a targeted manual revert (Edit tool, no git) is always possible without touching the user's other valid changes. Ties into [[feedback_main_branch_only]] (no branches) and [[feedback_user_owns_git]] (read-only git only unless explicitly asked).
