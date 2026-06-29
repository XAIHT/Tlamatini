---
name: project_secret_leak_recovery
description: "How Tlamatini commits can leak API keys, and the recovery recipe when it happens"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8e2656f3-42fc-4f2b-af9e-8650b72533dc
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

The user occasionally commits real secrets because `config.json` and several agent `config.yaml` files (emailer/recmailer/telegramer/telegramrx/teletlamatini, plus acpx codex/gemini env keys) carry **injected live keys** during local dev. `regen_secrets.py` must be run to swap them back to push-able placeholders BEFORE committing — when skipped, the commit ships `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` etc. in cleartext.

**2026-05-22 incident:** two local Kalier commits (`356fb96` had the keys, `e2af41d` reverted configs to placeholders). Never pushed — `origin/main` was at `d697e7e`.

**Recovery recipe (when the leaky commits are LOCAL-ONLY / not pushed):**
1. Confirm not pushed: `git status -sb` shows "ahead of origin/main by N", and `git log origin/main` lacks them.
2. Confirm working tree already has placeholders: `git diff origin/main -- Tlamatini/agent/config.json` is empty.
3. `git reset --soft origin/main` — drops the bad commits, keeps ALL work staged, loses nothing.
4. Verify: `git grep -nE '<leaked-key-prefixes>'` returns clean; `git branch --contains <bad-sha>` is empty.
5. Old commits survive only in reflog (local). Offer (don't auto-run) `git reflog expire --expire=now --all && git gc --prune=now` to fully purge.

**Why:** local-only leaks mean rotation is optional (keys never left the machine); pushing changes the calculus entirely (then keys ARE exposed and must be rotated + history rewritten on remote).
**How to apply:** if the leaky commits were already PUSHED, this recipe is insufficient — keys are public, must rotate immediately and force-push rewritten history. Always check push-state first. See [[feedback_user_owns_git]] — state-mutating git needs explicit user request (the user gave it here).
