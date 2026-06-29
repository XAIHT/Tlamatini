<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini Agents — MCP connector

Exposes **every wrapped Tlamatini pool agent (all 57)** as MCP tools so an MCP
client (Claude Code, etc.) can drive them directly — Executer, Pythonxer, Croner,
ACPXer, STM32er, ESP32er, Arduiner, Shoter, Playwrighter, Kalier, MCP Doctor, …
plus 5 run-management tools (**62 tools** total).

## Files

| File | Role |
|---|---|
| `tlamatini_mcp_server.py` | The stdio MCP server. Self-contained (needs only `mcp` + `pyyaml`; `psutil` used for tree-kill if present). Does **not** import Django. |
| `.mcp.json` | Project-scoped registration so Claude Code shows it under `/mcp`. |

It resolves `Tlamatini/agent/agents/` relative to its own location, so the
client's working directory doesn't matter.

## Activate it

1. Reload Claude Code in this folder (`C:\Development\Tlamatini`). A project
   `.mcp.json` server must be **approved on first use** — run `/mcp`, pick
   `tlamatini`, approve it (or restart the session).
2. Verify offline anytime: `python tlamatini_mcp_server.py --list`
3. The tools then appear to Claude as `mcp__tlamatini__<agent>` (e.g.
   `mcp__tlamatini__executer`).

## How it runs an agent (per call)

The exact Tlamatini "launcher dance" — no shortcuts:

1. copy `agent/agents/<name>/` → `Temp/mcp_agent_runs/<name>__<runid>/` (gitignored)
2. deep-merge your args onto that copy's `config.yaml` (empty values are
   dropped, so template defaults survive)
3. run `python <name>.py` in the copied dir
4. read `<name>__<runid>.log` (where the agent writes its result) and return it

## Calling agents

Each agent tool's parameters are **auto-derived from its `config.yaml`**, plus
three universal options:

- `wait` (bool) — wait for completion and return the full log. Default `true`,
  except known **long-running** agents (croner, flowhypervisor, teletlamatini,
  gatewayer, gateway_relayer, recmailer,
  monitor_log, monitor_netstat, node_manager) default `false`.
- `timeout_seconds` (int, default 180) — if the agent hasn't finished by then,
  it's left running in the background and a `run_id` is returned.
- `config` (object) — free-form overrides for nested/uncommon keys, or to set
  `source_agents`/`target_agents` wiring.

### Examples (conceptual args)

| Agent | Args |
|---|---|
| `executer` | `{ "script": "echo hello" }` |
| `pythonxer` | `{ "script": "print(sum(range(10)))" }` |
| `shoter` | `{}` (screenshot; renders on the real desktop) |
| `stm32er` | `{ "action": "bootstrap" }` then `{ "action": "validate" }` |
| `esp32er` | `{ "action": "scaffold_build_upload", "board": "esp32dev" }` |
| `arduiner` | `{ "action": "boards" }` (FQBN picks the MCU) |
| `acpxer` | `{ "agent_id": "claude", "task": "summarize README" }` |
| `croner` | `{ "trigger_time": "14:30" }` → returns a `run_id` (background) |

### Run-management tools

- `tlamatini_list_agents()` — every agent + its parameters.
- `tlamatini_run_log(run_id, max_chars?)` — read a run's log.
- `tlamatini_run_status(run_id)` — alive / finished + return code.
- `tlamatini_run_stop(run_id)` — terminate a background run (process tree).
- `tlamatini_list_runs()` — all runs this session.

Typical long-running pattern: call the agent (gets `run_id`) →
`tlamatini_run_log(run_id)` to watch → `tlamatini_run_stop(run_id)` to end it.

## Notes

- **Python**: `.mcp.json` points at `C:\Program Files\Python312\python.exe`
  (the interpreter that already has `mcp` + `pyyaml`). Change it if you move
  to a venv.
- **Visible/desktop agents** (Shoter, Mouser, Keyboarder, headed Playwrighter,
  Executer with `execute_forked_window: true`) render on your real desktop —
  the MCP server runs as a normal user process, not sandboxed.
- **Temp**: runtime copies live under the gitignored repo-root `Temp/` per the
  2026-06-02 temp policy.
- This connector is **separate** from Tlamatini's own running app — it drives
  the agent templates straight from disk and needs neither the Django server
  nor a browser.
