---
name: code-review
description: Review a git diff (or working-tree changes) like a senior engineer — correctness, security, performance, readability — and return a verdict plus structured, line-anchored findings.
metadata:
  openclaw:
    emoji: "🔍"
    requires:
      bins: ["git"]
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer", "chat_agent_gitter"]
    requires_mcps: []
    budget:
      max_iterations: 8
      max_seconds: 180
      max_tokens: 30000
    permissions:
      filesystem:
        read:  ["${input.repo_path}", "**/*"]
        write: []
      shell:
        - "git diff *"
        - "git log *"
        - "git show *"
        - "git status *"
        - "git rev-parse *"
      network: deny
      db:      deny
    inputs:
      - { name: repo_path, type: string,  required: false, default: ".",
          description: "Path to the git repository to review." }
      - { name: diff_ref,  type: string,  required: false, default: "HEAD~1",
          description: "Git ref to diff against (e.g. HEAD~1, origin/main, a tag). Use an empty string to review uncommitted working-tree + staged changes instead." }
      - { name: focus,     type: string,  required: false,
          description: "Optional reviewer guidance, e.g. 'focus on the auth path' or 'we care most about SQL injection'." }
    outputs:
      - { name: verdict,  type: string,  required: true,
          description: "APPROVE | REQUEST_CHANGES | COMMENT" }
      - { name: findings, type: array,   required: true,
          description: "List of {file, line, severity, category, message, suggestion}." }
      - { name: summary,  type: string,  required: true }
    triggers:
      keywords: ["code review", "review diff", "review changes", "review pr", "review my code", "review this branch"]
      file_globs: ["**/*.diff", "**/*.patch"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Code Review

Act as a rigorous, fair senior engineer reviewing a change set. Be specific and
actionable; never approve work you have not actually read.

## Procedure

1. **Resolve the diff.** Run, via `chat_agent_gitter` (preferred) or
   `chat_agent_executer`, from `${input.repo_path}`:
   - If `${input.diff_ref}` is non-empty: `git diff ${input.diff_ref} -- .`
     (also run `git diff ${input.diff_ref} --stat` for a file overview).
   - If `${input.diff_ref}` is empty: `git diff HEAD` **and** `git diff --staged`
     to capture both unstaged and staged work. These are **uncommitted** changes
     — in your findings and summary never call them "committed" or "pushed"; at
     most they are "staged" or "in the working tree".
   - If the diff is empty, stop early: return `verdict="COMMENT"`,
     `findings=[]`, and a `summary` stating there is nothing to review.
2. **Read every hunk.** Do not skim. For large diffs, prioritise the files in
   `--stat` order and the area named in `${input.focus}` if given.
3. **Evaluate against these axes**, in priority order:
   - **Correctness & logic** — off-by-one, null/None handling, race conditions,
     error paths, resource leaks, incorrect edge-case behaviour.
   - **Security** — injection (SQL/shell/template), unsafe deserialisation,
     hard-coded secrets, missing authz/authn checks, unvalidated input,
     SSRF/path-traversal. Flag anything that touches credentials or `eval`-like
     execution. **Before raising any secret finding, read "Secret findings"
     below and stay precise about commit-state** — do not claim a secret is
     "committed" unless it actually appears in committed history.
   - **Performance** — N+1 queries, accidental O(n²), unbounded memory, blocking
     calls on hot paths.
   - **Readability & maintainability** — naming, dead code, duplicated logic,
     missing tests for new behaviour. Match the surrounding file's style.
4. **Anchor every finding** to a `file` and `line` from the diff. Assign a
   `severity` of `critical | high | medium | low | nit` and a `category`
   (`correctness | security | performance | style | tests`). Give a concrete
   `suggestion`, not just a complaint.
5. **Decide the verdict:**
   - Any `critical` or `high` finding → `REQUEST_CHANGES`.
   - Only `medium`/`low`/`nit` → `COMMENT`.
   - No substantive findings → `APPROVE`.

## Secret findings — read before flagging credentials

Two rules keep secret findings accurate and avoid the common false alarm of
reporting a developer's *local* keys as leaked or committed:

1. **Commit-state precision.** A working-tree/staged diff (empty `diff_ref`) is
   **uncommitted**. Never describe values in it as "committed to source" or
   "pushed". Only a non-empty `diff_ref` that names committed history can be
   called "committed".
2. **This repo's scrub convention (Tlamatini).** The files `agent/config.json`
   and `agent/agents/*/config.yaml` hold local credentials in the working copy
   (the "keyed" mode) and are scrubbed to `<NAME goes here>` placeholders by
   `regen_secrets.py --mode push-able` before any commit/push; the real values
   live only in `data.keys`, which is gitignored. So the committed/pushed copies
   of those files contain **only placeholders**. Therefore:
   - A `<...goes here>` placeholder or an empty string is **not** a secret —
     never flag it.
   - Real-looking credentials in those managed files inside an **uncommitted**
     diff are the expected local state, not a leak, and are not committed. Do not
     report them as "API keys/passwords committed to source"; at most add one
     low-severity note to run `regen_secrets.py --mode push-able` before
     committing.
   - Still hard-flag genuine secrets hard-coded into **source code**, secrets in
     any file outside that managed config set, and any secret that truly appears
     in committed history.

## Output

Return `{ verdict, findings, summary }` where `summary` is a 2–4 sentence
plain-language overview a busy author can read first. Order `findings` by
severity (critical first). Do **not** invent files or lines that are not in the
diff, and do **not** comment on code outside the change set unless a change
directly breaks it.
