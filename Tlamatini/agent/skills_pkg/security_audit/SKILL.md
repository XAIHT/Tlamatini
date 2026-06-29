---
name: security-audit
description: Run whichever SAST, secret-scanning, and dependency-audit tools are installed (bandit, semgrep, ruff, eslint, gitleaks, pip-audit) over a path, then return aggregated findings, severity counts, and a prioritised remediation summary.
metadata:
  openclaw:
    emoji: "🛡️"
    requires:
      bins: ["python"]
    install:
      - { id: "bandit",    kind: "pip", package: "bandit" }
      - { id: "semgrep",   kind: "pip", package: "semgrep" }
      - { id: "pip-audit", kind: "pip", package: "pip-audit" }
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: []
    budget:
      max_iterations: 10
      max_seconds: 300
      max_tokens: 30000
    permissions:
      filesystem:
        read:  ["${input.path}", "**/*"]
        write: []
      shell:
        - "bandit *"
        - "semgrep *"
        - "ruff *"
        - "eslint *"
        - "npx eslint *"
        - "gitleaks *"
        - "pip-audit *"
        - "trufflehog *"
        - "where *"
        - "which *"
      # Some scanners (semgrep --config auto, pip-audit) fetch rule/advisory
      # data from the network. Local-rule runs still work offline.
      network: allow
      db:      deny
    inputs:
      - { name: path,         type: string, required: true,
          description: "File or directory to scan." }
      - { name: tools,        type: array,  required: false,
          description: "Subset of scanners to run, e.g. ['bandit','gitleaks']. Default: every scanner found on PATH that fits the file types present." }
      - { name: min_severity, type: string, required: false, default: "low",
          description: "Drop findings below this severity: low | medium | high | critical." }
    outputs:
      - { name: findings,        type: array,  required: true,
          description: "List of {tool, file, line, severity, rule_id, message}." }
      - { name: severity_counts, type: object, required: true,
          description: "{critical, high, medium, low} totals after the min_severity filter." }
      - { name: summary,         type: string, required: true }
    triggers:
      keywords: ["security audit", "sast", "vulnerability scan", "secrets scan", "bandit", "semgrep", "gitleaks", "dependency audit", "pip-audit"]
      file_globs: ["**/requirements*.txt", "**/package.json", "**/*.py", "**/*.js"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Security Audit

Run a defensive, read-only security sweep over `${input.path}`. This skill is
for authorized auditing of code you own or are permitted to test. Never use it
to evade detection or attack third-party systems.

## Procedure

1. **Detect available scanners.** Probe PATH (`where <tool>` on Windows,
   `which <tool>` elsewhere) for each candidate. If `${input.tools}` is set,
   restrict to that subset. Skip any tool that is not installed — note it in the
   summary rather than failing.
2. **Pick scanners by content.** Run only what fits the target:
   - **Python** present → `bandit -r "${input.path}" -f json` (SAST) and, for
     dependency files, `pip-audit -r <requirements file>` or
     `pip-audit` in a project dir.
   - **JS/TS** present → `npx eslint "${input.path}" -f json` if an eslint
     config exists.
   - **Any language** → `semgrep --config auto --json "${input.path}"` when
     semgrep is installed (falls back to `--config p/ci` offline).
   - **Secrets** → `gitleaks detect --source "${input.path}" --report-format json`
     (or `trufflehog filesystem`) to catch committed credentials/keys.
   - Always run `ruff check "${input.path}" --output-format json` when Python is
     present — its security-adjacent lint rules (S-prefixed) are cheap signal.
3. **Run each scanner via `chat_agent_executer`.** Capture stdout even on a
   non-zero exit code — most of these tools exit non-zero precisely *because*
   they found issues. Truncate any single tool's raw output to ~16000 chars
   before parsing.
4. **Normalise findings** into one shape: `{tool, file, line, severity,
   rule_id, message}`. Map each tool's native severity onto
   `critical | high | medium | low`. Treat any committed secret/credential as
   `critical`.
5. **Filter & count.** Drop findings below `${input.min_severity}`. Produce
   `severity_counts = {critical, high, medium, low}`.
6. **Summarise for action.** Lead with the count of critical/high issues, name
   the top 3 things to fix first, and list which scanners were unavailable so the
   reader knows the coverage gaps.

## Output

Return `{ findings, severity_counts, summary }`. Order `findings` by severity
(critical first). Do not modify any file, do not attempt remediation, and do not
exfiltrate scan output anywhere — this skill only reports.
