---
name: tlamatini-allowed-hosts-tighten
description: Tighten Django ALLOWED_HOSTS from the wide-open '*' default to a specific list, with a backup of settings.py.
metadata:
  openclaw:
    emoji: "🔒"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 4
      max_seconds: 60
      max_tokens: 6000
    permissions:
      filesystem:
        read:  ["Tlamatini/tlamatini/settings.py"]
        write: ["Tlamatini/tlamatini/settings.py","Tlamatini/tlamatini/settings.py.bak"]
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: hosts, type: array, required: true,
          description: "Whitelist of hostnames, e.g. ['127.0.0.1','localhost','tlamatini.local']" }
    outputs:
      - { name: settings_path, type: string,  required: true }
      - { name: backup_path,   type: string,  required: true }
      - { name: changed,       type: boolean, required: true }
    triggers:
      keywords: ["ALLOWED_HOSTS","tighten allowed hosts","django security"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Tighten ALLOWED_HOSTS

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

The Tlamatini security report flagged the default `ALLOWED_HOSTS=['*']`
in `Tlamatini/tlamatini/settings.py` as one of the Tlamatini-specific
debts. This skill replaces it with a user-supplied whitelist and writes
a `.bak` backup next to the file.

## Procedure

1. Read `Tlamatini/tlamatini/settings.py`.
2. Locate the line `ALLOWED_HOSTS = [...]` (any list literal).
3. Backup the current file as `settings.py.bak`.
4. Rewrite `ALLOWED_HOSTS` with `${input.hosts}` rendered as a Python list.
5. Return `{settings_path, backup_path, changed}`.

## Rollback

If the new list is incorrect, restore `settings.py.bak` over `settings.py`
manually.
