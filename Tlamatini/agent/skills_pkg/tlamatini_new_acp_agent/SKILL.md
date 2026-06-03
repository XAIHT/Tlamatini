---
name: tlamatini-new-acp-agent
description: Scaffold a new Tlamatini visual agent end-to-end across the 8 places the agent contract requires (script + config.yaml, view + url, migration, CSS gradient, 4 JS files, agentic_skill.md, README.md, lint).
metadata:
  openclaw:
    emoji: "🧱"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator","chat_agent_executer","chat_agent_pythonxer"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 30
      max_seconds: 600
      max_tokens: 80000
    permissions:
      filesystem:
        read:  ["Tlamatini/agent/**/*"]
        write:
          - "Tlamatini/agent/agents/${input.agent_name}/**/*"
          - "Tlamatini/agent/views.py"
          - "Tlamatini/agent/urls.py"
          - "Tlamatini/agent/static/agent/css/agentic_control_panel.css"
          - "Tlamatini/agent/static/agent/js/acp-*.js"
          - "Tlamatini/agent/migrations/*.py"
          - "Tlamatini/agent/agents/flowcreator/agentic_skill.md"
          - "README.md"
      shell:
        - "python -m ruff check Tlamatini/agent"
        - "npm run lint"
      network: deny
      db:      ["read", "write-via-migrations-only"]
    inputs:
      - { name: agent_name, type: string, required: true,
          description: "snake_case folder name; display name derived as title-case" }
      - { name: category,   type: enum,
          values: ["control","routing","gates","action","crypto","utility","terminal"],
          required: true }
      - { name: gradient,   type: string, required: false,
          description: "4 hex colors comma-separated (#aabbcc,...)" }
    outputs:
      - { name: files_changed, type: array, required: true }
      - { name: migration_id,  type: string, required: true }
      - { name: lint_summary,  type: string, required: true }
    triggers:
      keywords: ["new agent","add agent","scaffold agent","create acp agent"]
      file_globs: ["Tlamatini/agent/agents/**/*"]
---

# New ACP agent

Read `Tlamatini/.agents/workflows/create_new_agent.md` first. It is the
ground truth for the 8-step contract. This skill drives that procedure
end-to-end.

## Steps

1. Validate `agent_name` is snake_case ASCII; reject collisions with
   existing agents in `Tlamatini/agent/agents/`.
2. Copy `shoter.py` boilerplate into the new directory; rename references.
   **Temp/Templates policy (2026-06-02):** if the agent creates temp files, add
   the module-top `if (os.environ.get('TLAMATINI_TEMP') or '').strip(): …
   tempfile.tempdir = …` guard (verbatim from `executer.py` — an `if`-block, not
   a `def`, so ruff E402 stays clean); if it scaffolds a project/template dir
   (firmware/engine style), default the parent to `<app>/Templates`
   (`TLAMATINI_TEMPLATES`). See `prompt.pmt` Rules 15/16 + `agent/path_guard.py`.
3. Add a Django view + URL pair for the connection-update endpoint.
4. Create the migration that seeds an `Agent` row with the display name.
5. Add the CSS gradient block in `agentic_control_panel.css` and the
   hover variant.
6. Update the four JS files: connector, classMap (6 locations), undo/redo,
   .flw load.
7. Update `agentic_skill.md` and `README.md` (agent count, table,
   classification, glossary, changelog, API table).
8. Run `python -m ruff check` and `npm run lint`. Stop on any error and
   report.

## Output

Return:
```json
{
  "files_changed": ["..."],
  "migration_id": "00NN_add_<agent_name>",
  "lint_summary": "ruff: 0 errors; eslint: 0 errors"
}
```
