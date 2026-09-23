---
name: tlamatini-static-version-bumper
description: Bump STATIC_VERSION in tlamatini/settings.py so the chat / ACP frontend re-fetches CSS+JS bundles after a frontend change.
metadata:
  openclaw:
    emoji: "📦"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator"]
    requires_mcps: []
    budget:
      max_iterations: 2
      max_seconds: 15
      max_tokens: 3000
    permissions:
      filesystem:
        read:  ["Tlamatini/tlamatini/settings.py"]
        write: ["Tlamatini/tlamatini/settings.py"]
      shell:   []
      network: deny
      db:      deny
    inputs: []
    outputs:
      - { name: old_version, type: string,  required: true }
      - { name: new_version, type: string,  required: true }
      - { name: changed,     type: boolean, required: true }
    triggers:
      keywords: ["static version","bump static","cache bust","STATIC_VERSION"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Static-version bumper

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Refreshes the `?v={{ STATIC_VERSION }}` query string that ends every static
asset URL, so browsers refetch changed JavaScript, CSS and templates.

Run this after **every** JavaScript, CSS or template change — including
`dialog_theme.css`, `dialog_policy.js`, `release_notes_renderer.js`, the
External-MCP runtime strip and long-operation menu behavior.

## ⚠️ STATIC_VERSION IS NOT AN INTEGER — do not replace the expression

`Tlamatini/tlamatini/settings.py` computes it at import time:

```python
STATIC_VERSION = (os.environ.get('STATIC_VERSION') or str(int(time.time()))) + '-ctxspinner-1'
```

So it is **an environment override OR the process start timestamp**, plus a
build suffix. There is no `STATIC_VERSION = '7'` literal to increment, and
**writing one would BREAK the mechanism** — it would pin every future run to a
single value and stop cache-busting entirely. Do not "rotate semver" here
either: this is an asset-cache stamp, completely separate from the product
release resolved from Git/build metadata (see `VERSIONING.md`). Never
substitute one for the other, and never hardcode a release number you read
somewhere — the current release is whatever `git describe` says today.

## How a refresh actually happens

| situation | what refreshes the stamp |
|---|---|
| source dev run | **Restart the server.** The timestamp is evaluated once at import, so a running process keeps its stamp until it restarts. |
| deployment with a pinned stamp | Set the `STATIC_VERSION` env var to a NEW value and restart. |
| a permanent marker for one change | Edit only the **suffix** literal (`-ctxspinner-1` → `-ctxspinner-2`). Keep the `os.environ.get(...) or str(int(time.time()))` head intact. |

## Procedure

1. Read the `STATIC_VERSION = (...)` expression from settings.py and report it
   verbatim. If it does not match the documented shape, **stop and report the
   mismatch** rather than guessing a replacement.
2. Decide the mechanism from the table above. Default to a **restart** in
   source mode; only touch the suffix when the change needs a marker that
   survives across restarts.
3. If you edited the suffix, leave the head of the expression byte-identical.
4. **Run `python Tlamatini/manage.py collectstatic --noinput`.** A frozen build
   (`DEBUG=False`) serves the COLLECTED `staticfiles/` tree through WhiteNoise,
   not your source file — an uncollected fix is invisible there while the source
   looks correct.
5. Restart the server so the new stamp is evaluated.
6. **Verify the served asset**, not the source: open the page in a **VISIBLE,
   HEADED real Chrome on Angela's desktop** (Playwright `headless=False`, or
   just look at the browser) and confirm the `?v=` value changed AND that the
   change is actually present in the delivered file. ⛔ **HEADLESS IS
   FORBIDDEN** — Angela's hard rule; a cache-busting fix you cannot see is a
   fix you cannot claim. Launch any script that drives it from a VISIBLE
   FOREGROUND console, never `run_in_background`.

Return `{old_version, new_version, changed, mechanism}` where `mechanism` is
one of `restart` | `env_override` | `suffix_edit`. If the expression cannot be
found, return `{changed: false, old_version: '', new_version: '',
mechanism: 'not_found'}` so the user knows.
