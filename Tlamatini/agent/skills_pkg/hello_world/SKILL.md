---
name: hello-world
description: Smoke-test skill that echoes its inputs and confirms the SkillHarness wiring is alive end-to-end.
metadata:
  openclaw:
    emoji: "👋"
  tlamatini:
    runtime: in-process
    requires_tools: []
    requires_mcps: []
    budget:
      max_iterations: 2
      max_seconds: 10
      max_tokens: 2000
    permissions:
      filesystem:
        read:  []
        write: []
      shell:   []
      network: deny
      db:      deny
    inputs:
      - { name: who, type: string, required: false, default: "world" }
    outputs:
      - { name: greeting, type: string, required: true }
    triggers:
      keywords: ["hello", "smoke test", "ping", "acpx ready"]
---

# Hello World

This skill exists to prove the SkillHarness pipeline is wired correctly.
It must:

1. Accept an optional `who` input (default: "world").
2. Return `{"greeting": "hello, <who>"}` exactly.

There are no side effects. There is no shell. There is no file IO.

If this skill cannot be invoked end-to-end, the SkillHarness is broken
and no other skill should be trusted. Treat that as the smoke-test gate.
