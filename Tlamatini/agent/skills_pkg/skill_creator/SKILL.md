---
name: skill-creator
description: Create, edit, validate, and package new Tlamatini skills (SKILL.md packages).
metadata:
  openclaw:
    emoji: "🛠"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator", "chat_agent_executer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 8
      max_seconds: 120
      max_tokens: 16000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/skills_pkg/**/*"]
        write: ["Tlamatini/agent/skills_pkg/${input.skill_name}/**/*"]
      shell:   ["python Tlamatini/agent/skills_pkg/_meta/lint.py"]
      network: deny
      db:      deny
    inputs:
      - { name: skill_name, type: string, required: true,
          description: "kebab-case directory name and frontmatter name" }
      - { name: description, type: string, required: true }
      - { name: runtime, type: enum, values: ["in-process", "acpx"], required: true }
      - { name: acpx_agent, type: string, required: false }
    outputs:
      - { name: skill_dir, type: string, required: true }
      - { name: lint_status, type: string, required: true }
    triggers:
      keywords: ["new skill", "author skill", "create skill", "skill bootstrap"]
      file_globs: ["Tlamatini/agent/skills_pkg/**/SKILL.md"]
---

# Skill Creator

Use this skill to bootstrap a new skill correctly the first time.

## Procedure

1. Validate the inputs:
   - `skill_name` must be kebab-case, all lowercase, ASCII letters/numbers/dashes only.
   - `runtime` must be `in-process` or `acpx`. If `acpx`, `acpx_agent` is required.

2. Create the directory `Tlamatini/agent/skills_pkg/${input.skill_name}/`.

3. Author `SKILL.md` with this minimal scaffold:

```markdown
---
name: ${input.skill_name}
description: ${input.description}
metadata:
  tlamatini:
    runtime: ${input.runtime}
    acpx_agent: ${input.acpx_agent}     # only if runtime=acpx
    requires_tools: []
    requires_mcps:  []
    budget:
      max_iterations: 8
      max_seconds: 120
      max_tokens: 16000
    permissions:
      filesystem: { read: [], write: [] }
      shell:     []
      network:   deny
      db:        deny
    inputs:  []
    outputs: []
    triggers:
      keywords:   []
      file_globs: []
---

# ${input.skill_name}

Describe the skill. Be concise. Body must stay under 8 KiB.
```

4. Run the linter:

   ```bash
   python Tlamatini/agent/skills_pkg/_meta/lint.py
   ```

5. Return `{ "skill_dir": "<path>", "lint_status": "<linter stdout last line>" }`.

## Constraints

- Do NOT write outside `Tlamatini/agent/skills_pkg/<skill_name>/`.
- Do NOT add a skill whose name collides with an existing one — the registry
  rejects duplicates. The lint step catches this.
- Body length cap is 8 KiB. Long playbooks belong in `references/<file>.md`
  inside the skill directory and should be referenced from the body, not
  inlined.
- Skills with `runtime: acpx` MUST set `acpx_agent` to a registered agent_id
  (see `list_acp_agents`).
