---
name: setup-new-acpx-key
description: Configure the API key (or other credential) for a registered ACPX agent_id (claude/codex/cursor/gemini/qwen/copilot/pi/droid/iflow/kilocode/kimi/kiro/opencode/tlamatini) end-to-end across data.keys, config.json (top-level + acpx.agents.<id>.env), regen_secrets.py, and verification via acp_doctor.
metadata:
  openclaw:
    emoji: "🔑"
  tlamatini:
    runtime: in-process
    requires_tools: ["chat_agent_file_creator", "chat_agent_executer", "acp_doctor"]
    requires_mcps: ["Files-Search"]
    budget:
      max_iterations: 10
      max_seconds: 180
      max_tokens: 16000
    permissions:
      filesystem:
        read:
          - "Tlamatini/agent/config.json"
          - "Tlamatini/agent/acpx/agent_registry.py"
          - "data.keys"
          - "regen_secrets.py"
          - "README.md"
        write:
          - "Tlamatini/agent/config.json"
          - "data.keys"
          - "regen_secrets.py"
      shell:
        - "python regen_secrets.py --mode keyed --dry-run"
        - "python regen_secrets.py --mode keyed"
      network: deny
      db: deny
    inputs:
      - { name: agent_id,    type: enum, required: true,
          values: ["claude","codex","cursor","gemini","qwen","copilot","pi","droid","iflow","kilocode","kimi","kiro","opencode","tlamatini"],
          description: "The ACPX registry key from DEFAULT_ACP_AGENTS." }
      - { name: api_key,     type: string, required: true,
          description: "The credential value (e.g. sk-ant-api03-..., AIza..., sk-proj-...). Treated as a secret." }
      - { name: command_override, type: string, required: false,
          description: "Absolute path to the CLI binary if it is not on PATH (becomes acpx.agents.<id>.command)." }
    outputs:
      - { name: files_changed, type: array,  required: true }
      - { name: doctor_ok,     type: boolean, required: true }
    triggers:
      keywords: ["acpx key","api key","claude key","gemini key","codex key","qwen key","setup acpx","configure acpx credential"]
      file_globs: ["Tlamatini/agent/config.json","data.keys"]
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

# Set Up a New ACPX Agent Key

Configures the credential for ONE `agent_id` from the ACPX registry so
that `acp_spawn(agent_id=...)` launches the child CLI authenticated. The
ACPX runtime never asks the LLM for a key — each child reads its own
canonical env var, which Tlamatini injects via
`subprocess.Popen(env={**os.environ, **spec.env})` in
`agent/acpx/runtime.py::AcpSession.spawn_child()` (and the mirrored
`_oneshot_send_turn` path).

## Canonical env-var map (single source of truth)

| `agent_id` | Env var the CLI reads | Top-level config.json key? |
|------------|-----------------------|----------------------------|
| `claude`   | `ANTHROPIC_API_KEY`   | **YES** — also read by `agent/imaging/image_interpreter.py:153` and `agent/opus_client/claude_opus_client.py:349`. |
| `gemini`   | `GEMINI_API_KEY` (+ `GOOGLE_API_KEY` alias) | **YES** — per the `_section_gemini` comment in config.json. |
| `codex`    | `OPENAI_API_KEY`      | NO. |
| `qwen`     | `DASHSCOPE_API_KEY`   | NO. |
| `cursor`   | none (uses own login) | NO. |
| `copilot`  | none (`gh auth login`)| NO. |
| `pi`, `droid`, `iflow`, `kilocode`, `kimi`, `kiro`, `opencode` | per upstream — check each CLI's docs | NO. |
| `tlamatini`| n/a (self-host)       | NO. |

If unsure, check `Tlamatini/agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS`.

## Procedure

### 1. Verify the CLI is resolvable

The runtime calls `windows_spawn.resolve_command(spec.command)` at spawn
time and surfaces `AGENT_NOT_FOUND` if it cannot find the binary.

```bash
where ${cli_command}        # Windows
which ${cli_command}        # POSIX
```

If absent: install the CLI per its upstream docs, or pass
`command_override` and add it to the agent block in step 3.

### 2. Add the secret to `data.keys` (gitignored vault)

Open `data.keys` at the repo root and add — or update — a line
`KEY=VALUE`. Use the canonical name from the table:

```ini
ANTHROPIC_API_KEY=sk-ant-api03-...           # claude
GEMINI_API_KEY=AIzaSy...                     # gemini
GOOGLE_API_KEY=AIzaSy...                     # gemini alias (keep in sync)
OPENAI_API_KEY=sk-proj-...                   # codex
DASHSCOPE_API_KEY=sk-...                     # qwen
```

`data.keys` is in `.gitignore` (line 265). Never commit it.

### 3. Update `Tlamatini/agent/config.json`

Two layers, applied based on the table above:

**Layer A — top-level key (claude / gemini only):**

```json
{
  "ANTHROPIC_API_KEY": "<paste real value>",
  "GEMINI_API_KEY":    "<paste real value>"
}
```

**Layer B — per-agent env injection (every agent_id that needs a key):**

```json
{
  "acpx": {
    "agents": {
      "${agent_id}": {
        "command": "<optional absolute path; omit when CLI is on PATH>",
        "env": { "<CANONICAL_ENV_NAME>": "<paste real value>" }
      }
    }
  }
}
```

Real worked examples (mirror these exactly):

```json
"claude": {
  "command": "C:/Users/<user>/AppData/Roaming/npm/claude.cmd",
  "env": { "ANTHROPIC_API_KEY": "sk-ant-api03-..." }
},
"gemini": {
  "command": "C:/Users/<user>/AppData/Roaming/npm/gemini.cmd",
  "env": {
    "GEMINI_API_KEY": "AIzaSy...",
    "GOOGLE_API_KEY": "AIzaSy..."
  }
},
"codex":  { "command": "codex",     "env": { "OPENAI_API_KEY":    "sk-proj-..." } },
"qwen":   { "command": "qwen-code", "env": { "DASHSCOPE_API_KEY": "sk-..." } }
```

How the merge resolves at spawn (read once, never wonder again):

1. `agent/acpx/config.py::_coerce_agents_env()` plucks each `env` dict
   out of `acpx.agents.<id>` into `AcpxConfig.agents_env`.
2. `agent/acpx/agent_registry.py::build_agent_registry()` merges that
   dict on top of `DEFAULT_ACP_AGENTS[<id>].env` (override wins).
3. `AcpSession.spawn_child()` builds the child env as
   `{**os.environ, **self.spec.env}` — explicit `acpx.agents.<id>.env`
   wins over an exported shell variable.

### 4. Wire `regen_secrets.py` (only when introducing a brand-new key)

`regen_secrets.py` is the toggle between "push-able" placeholders and
real "keyed" values. If you added a `data.keys` entry that the script
does not already handle, extend it.

Patch `patch_config_json()` in `regen_secrets.py` (around lines
128-134):

```python
# Top-level (claude / gemini only — skip for everything else)
set_top("<TOP_KEY>",  "<DATA_KEYS_KEY>")

# Per-agent env injection — required for every agent that needs a key
set_acpx_env("<agent_id>", "<CANONICAL_ENV_NAME>", "<DATA_KEYS_KEY>")
```

Also list the new key in the docstring at the top of `regen_secrets.py`
(lines 12-16) so the file's own self-documentation stays accurate.

Existing wired keys (do NOT duplicate):
- `ANTHROPIC_API_KEY` — top + `acpx.agents.claude.env`
- `GEMINI_API_KEY`, `GOOGLE_API_KEY` — top (GEMINI only) + `acpx.agents.gemini.env` (both)
- `OLLAMA_TOKEN` — top only

### 5. Apply the changes

If you edited config.json directly (Layer A + Layer B), you are done.

If you only edited `data.keys` (and updated `regen_secrets.py` in step 4
when needed), run the regen script to splat the values into config.json:

```bash
python regen_secrets.py --mode keyed --dry-run    # preview
python regen_secrets.py --mode keyed              # apply
```

Always verify with `git diff Tlamatini/agent/config.json` that no
unexpected keys flipped to placeholders or vice versa.

### 6. Restart Django

`config.json` is read at startup by `agent/config_loader.py` and the
ACPX runtime caches the resolved registry. The new key does NOT take
effect until the server restarts. Stop and restart `manage.py runserver
--noreload` (or relaunch `Tlamatini.exe`).

### 7. Verify

In the Tlamatini chat with **Multi-Turn enabled**, ask the LLM to:

1. Call `acp_doctor` and confirm the row for `${agent_id}` shows
   `resolvable: true`.
2. Call `acp_spawn(agent_id="${agent_id}", task="...")` and confirm the
   spawn returns a `session_id` (no `AGENT_NOT_FOUND`).
3. Call `acp_send_and_wait(session_id, "Reply with the literal token
   ALIVE.")`. The transcript at `<acpx-state>/<session>.transcript.ndjson`
   must contain a non-empty assistant turn — proves the key was
   injected and the CLI authenticated. Empty transcript = key not
   reaching the child.
4. Call `acp_kill(session_id)`.

Or run the seeded **GEMINI LIVE REASONING SHOWCASE** prompt (idPrompt 31
from migration `0073_acpx_demo_gemini_uplift.py`) for an end-to-end
reasoning round-trip when `agent_id=gemini`.

## Common pitfalls

- **Top-level vs per-agent:** the top-level `ANTHROPIC_API_KEY` /
  `GEMINI_API_KEY` is read by Tlamatini's own internal callers
  (`image_interpreter.py`, `opus_client.py`); the per-agent
  `acpx.agents.<id>.env` is read by the spawned child. Setting only ONE
  half breaks the other half. For claude/gemini, set BOTH.
- **Forgetting the alias:** Gemini CLI versions vary; some only read
  `GEMINI_API_KEY`, others only `GOOGLE_API_KEY`. Always inject BOTH
  under `acpx.agents.gemini.env` to avoid the fragility.
- **Empty `env` dict survives merge:** `_coerce_agents_env()` skips
  entries where `env` is missing or empty, so the dict shape
  `"agents": { "claude": {} }` does NOT inject anything. Make sure the
  `env` key actually contains the env vars.
- **Stale process env:** if you exported the key in your shell BEFORE
  starting Django and now want config.json to win, remember the merge
  order: explicit `acpx.agents.<id>.env` always wins over `os.environ`.
- **CLI not on PATH:** symptom is `AGENT_NOT_FOUND` from `acp_doctor`,
  not an auth error. Fix the `command` field, not the `env` field.
- **Pushing keys:** before `git push`, run
  `python regen_secrets.py --mode push-able`, push, then
  `python regen_secrets.py --mode keyed` to restore. Never commit real
  values into config.json.

## Output

```json
{
  "files_changed": [
    "data.keys",
    "Tlamatini/agent/config.json",
    "regen_secrets.py"
  ],
  "doctor_ok": true
}
```

`regen_secrets.py` is included only when step 4 added a brand-new
`set_top` / `set_acpx_env` rule.
