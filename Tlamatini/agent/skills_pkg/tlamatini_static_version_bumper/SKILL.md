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

# Static-version bumper

Increments `STATIC_VERSION` in `Tlamatini/tlamatini/settings.py` so the
`?v={{ STATIC_VERSION }}` query string at the end of every static asset
URL changes, forcing browsers to refetch.

## Procedure

1. Read `STATIC_VERSION = '<n>'` from settings.py.
2. Replace with the next integer (or rotate semver).
3. Save the file. Return `{old_version, new_version, changed}`.

If `STATIC_VERSION` is missing, return `{changed: false, old_version: '',
new_version: ''}` so the user knows.
