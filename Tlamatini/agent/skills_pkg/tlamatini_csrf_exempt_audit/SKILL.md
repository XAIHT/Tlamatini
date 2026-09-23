---
name: tlamatini-csrf-exempt-audit
description: Enumerate every @csrf_exempt-decorated view in Tlamatini/agent/views.py and classify whether each one really needs the exemption.
metadata:
  openclaw:
    emoji: "🛡"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_executer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 4
      max_seconds: 60
      max_tokens: 12000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/views.py","Tlamatini/agent/urls.py"]
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs: []
    outputs:
      - { name: total,            type: integer, required: true }
      - { name: classifications,  type: array,   required: true }
      - { name: recommendations,  type: array,   required: true }
    triggers:
      keywords: ["csrf","csrf_exempt","csrf audit"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# CSRF-exempt audit

> **HEADLESS IS FORBIDDEN. VISIBLE FOREGROUND EXECUTION ONLY.** Every command, automated test, diagnostic, script, build, agent and browser must run in a visible foreground window on Angela's real desktop. Use forked CMD/PowerShell windows, `execute_forked_window: true`, and `headless: false`. Monitor live; if visibility cannot be confirmed, do not run. Read the [mandatory execution policy](../../../../TestsVisiblesAndVisibleExecutionFromClaude2Codex.md).

Inventory every `@csrf_exempt` in `Tlamatini/agent/views.py` and classify each
one against the protection the server actually applies. **Read-only** unless
remediation is separately requested.

## ⚠️ Find the RIGHT function

`@csrf_exempt` decorates the function that **FOLLOWS** it. Inspecting the view
above a decorator audits the wrong endpoint. Anchor on the `def` immediately
beneath the decorator stack.

## ⚠️ "Called by our own JavaScript" IS NOT A CLASSIFICATION

Two labels were previously handed out on the caller's identity alone:

* *safe-because-internal-tool* — but CSRF is precisely the attack where a
  **third-party page** issues the request while the victim's cookies ride
  along. That our own JS also calls the endpoint says nothing about who else
  can.
* *safe-because-websocket* — the WebSocket consumer is a different transport
  with a different origin check. It does not protect the HTTP view that
  happens to sit near it.

Neither establishes anything. Delete them.

## What actually decides it — inspect the view body

For each exempt endpoint record, with a line reference:

1. **Authentication** — `@login_required` / an explicit `request.user`
   check / none.
2. **Allowed methods** — `@require_POST` and friends, or an unguarded handler.
3. **State change** — does it write a file, a DB row, config, or spawn a
   process? A read-only endpoint has a different risk profile from one that
   writes `config.json`.
4. **Credential mechanism** — session cookie (CSRF-relevant) vs a bearer
   token or signature in the body (usually not).
5. **Origin / token protection** — an explicit `Origin`/`Referer` check, an
   HMAC, a shared secret, or nothing.
6. **Reachability** — is it bound to loopback, or served on every interface
   the `django_port` listens on?

## The four verdicts (nothing else)

| verdict | meaning |
|---|---|
| `justified_exemption` | the endpoint does not rely on cookie auth (e.g. a signed webhook), so CSRF does not apply — cite the mechanism. |
| `protected_by_other_means` | cookie-authenticated, but an origin/token/HMAC check is present — cite the line. |
| `protection_missing` | cookie-authenticated, state-changing, no compensating check. Report it; do not fix it here. |
| `insufficient_evidence` | you could not establish one of the six facts above. **Leave it unresolved.** |

Every verdict must cite the SERVER-SIDE check that supports it. A caller's
name is never a citation.

Return `{ endpoints: [{name, line, verdict, evidence, state_changing}],
summary }`.
