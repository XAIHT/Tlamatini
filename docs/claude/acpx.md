<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — ACPX (Agent Communication Protocol eXtension)

This file is the authoritative reference for what **ACPX** means in Tlamatini, the mechanics it implements, and the contract every part of the system (LLM, planner, tools, frontend) honors. Whenever the user mentions "ACPX", "ACPX mechanics", "ACP child", "use ACPX to ...", "spawn an external CLI", "leg A → leg B", "multi-CLI relay", "hand off transcript", or anything semantically equivalent, route them through this surface — do not paraphrase, do not invent a workaround.

---

## Definition

**ACPX = Agent Communication Protocol eXtension.**

It is Tlamatini's runtime for spawning **external coding-agent CLIs** as out-of-process child processes, talking to them over stdin/stdout, persisting the conversation as an NDJSON transcript, and brokering the whole thing to the LLM as Tlamatini tools.

ACPX is a **Python port of OpenClaw's ACPX plugin** (`extensions/acpx/`). The surface is API-compatible: `agent_id` mapping, `permissionMode` vocabulary, and the `SKILL.md` frontmatter contract all match verbatim, so any acp-router skill written for OpenClaw runs unmodified on Tlamatini and vice versa.

### ACPX toolbar toggle (per-request enable/disable)

The chat toolbar exposes three checkboxes: **Multi-Turn**, **Exec Report**, and **ACPX**. The ACPX checkbox (`#acpx-enabled` in `agent/templates/agent/agent_page.html`) **defaults to unchecked** — both visually (the JS hydration in `agent_page_state.js::applyStoredAcpxState` falls back to `false` when sessionStorage has no prior value) and on the backend (every read site — `interface.py::ask_rag`, `factory.py`, `chains/unified.py` payload-rebuild whitelist, `mcp_agent.py::CapabilityAwareToolAgentExecutor.invoke`, `consumers.py::receive` and the `queue_llm_retrieval` signature — defaults `acpx_enabled` to `False`). The checkbox sends an `acpx_enabled` boolean on every WebSocket request, the planner / executor call `agent.acpx.filter_acpx_tools(tools, acpx_enabled)` to strip the entire ACPX/Skill tool surface (the 12 names listed below) from the bound tool list whenever the flag is `False`, and the result is that **the default request behaves exactly like the legacy pre-ACPX Multi-Turn flow** — no `acp_*` / `*_skill` tools are even visible to the planner. `bypass_prompt_validation` is computed as `multi_turn_enabled OR acpx_enabled`, so the system still skips prompt-shape validation when only ACPX is checked (which is the right behavior because ACPX flows are LLM-operator flows, not Q&A).

The 12 ACPX/Skill tool names live in `agent.acpx.ACPX_TOOL_NAMES` (a `frozenset`) and are also registered in `_EXEC_REPORT_TOOLS` (in `agent/mcp_agent.py`) under `agent_key="acpx"` for the spawn/send/wait/kill family and `agent_key="skill"` for `invoke_skill`, so the Exec Report still merges all spawn/send/wait/kill rows into one "List of ACPx Operations" table when the user re-enables ACPX. Adding a 13th LLM-facing ACPX tool requires updating BOTH `ACPX_TOOL_NAMES` AND the executor whitelist in `unified.py` — the same drop-on-rebuild bug class that bit `exec_report_enabled` once already.

> **Not ACPX — the External MCP supervisor tools.** The 8 External-MCP tools (`external_mcp_status` / `external_mcp_reconnect` / `external_mcp_doctor` / `external_mcp_list_tools` / `external_mcp_call` / `external_mcp_import` / `external_mcp_set_active` / `external_mcp_wait`) and the lazily-bound `ext__<server>__<tool>` remote tools are a **SEPARATE surface** (Tlamatini's universal MCP *client* — see `docs/claude/architecture.md` → *External MCPs*). They are **NOT** part of ACPX: not in `ACPX_TOOL_NAMES`, **not** stripped by `filter_acpx_tools`, and gated **only by Multi-Turn** (the ACPX checkbox has no effect on them). Do not confuse the External MCP client with ACPX's external-CLI spawning — they are unrelated subsystems.

---

## Supported external coding agents (the `agent_id` registry)

Defined in `agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS`. Each agent has a transport profile that controls how the runtime drives the child:

| `agent_id` | Default command | Transport | Prompt argv form | Default budgets (timeout / idle / grace) |
|---|---|---|---|---|
| `claude` | `claude` | `oneshot-prompt` | `claude -p "<task>"` | 180 s / 10 s / 2 s |
| `codex` | `codex` | `oneshot-prompt` | `codex exec "<task>"` | 180 s / 10 s / 2 s |
| `cursor` | `cursor-agent` | `oneshot-prompt` | `cursor-agent -p "<task>"` | 180 s / 10 s / 2 s |
| `gemini` | `gemini` | `oneshot-prompt` | `gemini -p "<task>"` | 180 s / 10 s / 2 s |
| `qwen` | `qwen-code` | `oneshot-prompt` | `qwen-code -p "<task>"` | 180 s / 10 s / 2 s |
| `tlamatini` | `python -m agent.acpx.self_acp_server` | `json-acp` | (stdin envelope) | 45 s / 6 s / 12 s |
| `kiro` | `kiro` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `kimi` | `kimi` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `iflow` | `iflow` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `kilocode` | `kilocode` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `opencode` | `opencode` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `pi` | `pi` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `droid` | `droid` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |
| `copilot` | `copilot` | `tui-repl` | (stdin) | 8 s / 2 s / 3 s |

### Transport modes

- **`oneshot-prompt`** — Each turn re-spawns the CLI with the prompt as a CLI argument behind `prompt_arg_flag` (or `prompt_subcommand_args` for codex), closes stdin, and captures stdout to EOF. This is the **only** transport that reliably captures responses from TUI agents (claude / gemini / cursor / qwen) on Windows: TUI CLIs detect the piped stdout and refuse to flush, so a long-lived stdin-fed child captures the outbound prompt only — never the answer. The fix is to call them in their own `-p`/`--print` mode where they print the answer to stdout and exit. There is no inter-turn session state inside the child process; conversation continuity must be carried in the next prompt by the caller.
- **`json-acp`** — Child speaks one JSON envelope per turn ending with `{"done": true}`. Strict ACP contract; the `tlamatini` self-host server uses it.
- **`tui-repl`** — Long-lived interactive REPL over stdin/stdout with the transport-aware idle rule. Used for CLIs whose one-shot flag is unknown to us yet — override per-agent in `config.json.acpx.agents.<id>` (set `transport: oneshot-prompt`, `prompt_arg_flag: "-p"`) once you confirm one.
- **`one-shot`** — Single-task-per-process via stdin (`python script.py < task`). Stdin closes after the first write; runtime waits for child exit.

User overrides go in `config.json`, and since v1.51.2 they can retune **the whole spec**, not just the command:

```json
{
  "acpx": {
    "agents": {
      "claude":  { "command": "C:/Users/me/AppData/Roaming/npm/claude.cmd" },
      "cursor":  { "command": "/usr/local/bin/cursor-agent" },

      "copilot": { "transport": "oneshot-prompt",
                   "prompt_arg_flag": "-p",
                   "args": ["--allow-all-tools"],
                   "spawn_returns_immediately": false },

      "opencode": { "transport": "oneshot-prompt",
                    "prompt_subcommand_args": ["run"],
                    "prompt_arg_flag": null },

      "qwen":    { "command": "qwen", "args": ["--yolo"] }
    }
  }
}
```

Overridable per agent: **`command`**, **`env`**, **`args`** (extra argv BEFORE the prompt — this is how you grant a child its tools), **`transport`**, **`prompt_arg_flag`** (`null` = the CLI takes the prompt positionally), **`prompt_subcommand_args`**, **`default_idle_seconds`**, **`default_startup_grace_seconds`**, **`default_timeout_seconds`**, **`spawn_returns_immediately`**, **`description`** — the set is `agent_registry.OVERRIDABLE_SPEC_FIELDS`, kept in step with `config._coerce_agents_spec` by a drift test.

**Why this matters:** before v1.51.2 only `command` and `env` were overridable, so a wrong transport or a missing CLI flag could ONLY be fixed by editing `agent_registry.py` and **rebuilding the app**. Five installed peers sat broken on Angela's machine while every one of them was one flag away from working. Now that repair is a text edit. Resolution is **fail-open**: a malformed value, an unknown key, or a `transport` the runtime does not implement is dropped and the built-in default survives — a typo can never stop the runtime from starting, and can never produce a spec that hangs every spawn.

Custom `agent_id`s declared via overrides default to `tui-repl` with the fast-path defaults, then any spec fields you declared are applied on top.

---

## The 12 ACPX/Skill tools (LLM-facing surface)

All tools return a JSON envelope. The LLM never raises — every error is `{"ok": false, "reason": "...", "code": "..."}`.

### Health & enumeration
- `acp_doctor(deep=False, deep_timeout_seconds=60.0)` — health probe + per-agent enumeration.
  - Returns `{ok, message, details:[{agent_id, command, description, transport, resolvable, cli_version, readiness?}], probe:{agent_id, stdout, stderr}}`.
  - **Always call first** when an ACPX flow starts so the LLM knows which `agent_id`s are resolvable on this host.
  - ⚠️ **`resolvable` is NOT health — it only means the binary exists.** On 2026-09-07 all eight installed CLIs answered `--version` with exit 0 while FOUR were dead (gemini could not authenticate, codex refused its own `config.toml`, claude had no credit, copilot printed nothing), and the doctor greenlit every one of them.
  - **`deep=True` sends each `oneshot-prompt` agent a real one-line prompt** and adds a per-agent `readiness` block: `{ready: true|false|null, code, reason, evidence}`. `ready: null` means the transport cannot be probed without opening a session (tui-repl / json-acp) — an honest "unknown", not a failure. A false `ready` always carries a NAMED `code` (see *The delivery verdict* below). It **costs real model quota**, so it is off by default and cached for 10 minutes — use it when a spawn failed unexpectedly, when the user asks which agents actually work, or before committing a long relay to a particular leg.
- `list_acp_agents()` — same enumeration without the version probe (cheaper).

### Session lifecycle
- `acp_spawn(agent_id, task, cwd="", mode="session", session_label="", timeout_seconds=0, idle_seconds=0, startup_grace_seconds=0, max_event_chars=0)`
  - Spawns a child for `agent_id`, dispatches `task`.
  - For TUI agents: returns sub-second with `spawned_immediately:true` and an empty `events` array. The drain happens on the next call.
  - For JSON-ACP agents: drains until `done:true` or the configured timeout.
  - Returns `{session_id, agent_id, transport, transcript_path, events, events_total, spawned_immediately}`.
- `acp_send(session_id, text, timeout_seconds=0, idle_seconds=0, startup_grace_seconds=0, max_event_chars=0)`
  - Send a follow-up turn to an existing session.
- `acp_send_and_wait(session_id, text, until_idle_seconds=10, max_wait_seconds=180, max_event_chars=0)`
  - Same as `acp_send` but blocks until the child settles (idle rule fires).
  - Returns `{events, events_total, settled}` — `settled=True` means the drain ended on the idle rule (clean), not the timeout backstop.
  - **Prefer this for "wait for the full answer" / "complete answer" / "settle" prompts.**
- `acp_kill(session_id)` — terminate the child process. Returns `{killed, transcript_path, agent_id, pid}`.

### Reads
- `acp_transcript(session_id, max_chars=8000, direction="all")` — read the on-disk transcript (`{events, text, total_size, truncated, transcript_path}`). `direction` ∈ `"all" | "in" | "out"`.
- `acp_session_status(session_id)` — `{alive, pid, transcript_size, last_event_at, closed}`.
- `acp_list_sessions()` — enumerate all live sessions in the runtime.

### Hand-off
- `acp_relay(session_id_src, session_id_dst, transform="last_assistant_text", prefix="", suffix="", until_idle_seconds=10, max_wait_seconds=180, max_event_chars=0)`
  - Single-call hand-off: reads the source transcript, extracts the assistant text (or `transform="full_transcript"`), wraps with optional `prefix`/`suffix`, sends to the destination session, waits for it to settle.
  - **One tool call replaces a 3-step dance** (`acp_transcript` → string-manipulate → `acp_send`). Always prefer it on relay/hand-off prompts.

### Skills
- `list_skills(filter_keywords="")` — list registered SKILL.md packages.
- `invoke_skill(skill_name, args_json)` — run a skill inside the SkillHarness. The skill `acp-router` is the canonical companion: it picks the best `agent_id` for an intent.

---

## Canonical ACPX flows the LLM must recognize

### 1. Spawn-and-go (single agent)
```
acp_doctor
  → acp_spawn(agent_id, initial_task)
    → acp_send_and_wait(session_id, follow_up_question)
      → acp_kill(session_id)
```

### 2. Multi-CLI relay (leg A → leg B)
```
acp_doctor
  → acp_spawn(leg_a_id, task_a)
    → acp_send_and_wait(session_a, ...)         # let A produce its answer
      → acp_spawn(leg_b_id, prompt_template_b)  # B's prompt template
        → acp_relay(session_a, session_b)       # ONE call: hand off A's text to B
          → acp_kill(session_a)
            → acp_kill(session_b)
```

A single `acp_relay` replaces the otherwise-required `acp_transcript` → string-manipulate → `acp_send` sequence.

### 3. Harvest transcript & report
```
... do the work via acp_spawn / acp_send_and_wait ...
  → acp_transcript(session_id)
    → invoke_skill('summarize', {text, target_words})   # compress
      → chat_agent_file_creator(filepath, content)      # write report
        → chat_agent_notifier(title, message)           # signal done
          → acp_kill(session_id)
```

### 4. Skill-driven agent routing
```
list_skills
  → invoke_skill('acp-router', {intent: '...', prefer: 'gemini'})
    → acp_spawn(<returned agent_id>, task)
      → ...
```

---

## Required behavior (contract the LLM honors)

1. **Always call `acp_doctor` first** on an ACPX flow so the LLM knows which `agent_id`s are resolvable. Branch on `details[].resolvable` — but remember that `resolvable` only proves the binary exists. When the flow matters (a long relay, a research leg you will build on), call `acp_doctor(deep=True)` and branch on `details[].readiness.ready` instead.
1b. **Never treat `ok: true` as the only success check, and never ignore `ok: false` from `acp_spawn`/`acp_send`.** A child that refused, could not authenticate or printed nothing now returns `ok: false` with a named `code` — see *The delivery verdict* below. Read the `reason`, tell the user which leg died and why, and either repair it or route around it. Do NOT build later tool calls on a leg that did not deliver.
2. **Capture `session_id` on every `acp_spawn`** — every follow-up tool call needs it.
3. **Always call `acp_kill` at the end of each session you spawned.** Sessions left alive count against the runtime's session cap.
4. **Use the dedicated ACPX tool, never an `execute_command` workaround.** Reading a transcript via `type` / `cat` is wrong — use `acp_transcript`.
5. **Honor named `agent_id`s.** If the user says "pin leg A to gemini", pass exactly `agent_id="gemini"`. If gemini isn't resolvable, announce the fallback in one short line and pick another resolvable id.
6. **For "complete answer" / "wait for full answer" / slow REPL prompts**: prefer `acp_send_and_wait` with `until_idle_seconds=15, max_wait_seconds=180`, or pass `timeout_seconds=120, idle_seconds=15` to `acp_send`. The default TUI 8 s timeout is tuned for "session stays alive cheaply", not "produce a full essay".
7. **For relay/hand-off prompts**: always `acp_relay`, never the manual transcript-and-send dance.
8. **Operational siblings** of every ACPX flow:
   - `chat_agent_file_creator` — write the report.
   - `chat_agent_notifier` — signal completion.
   - `invoke_skill` — for `summarize` / `acp-router` skills.

---

## Runtime mechanics (what happens inside the box)

### `oneshot-prompt` (claude / gemini / cursor / qwen / codex)

`agent/acpx/runtime.py::AcpSession._oneshot_send_turn` runs each turn as a fresh process invocation:

1. **Persist outbound prompt** to the NDJSON transcript with `direction:"out"` and `transport:"oneshot-prompt"` so a crash before the spawn still leaves evidence.
2. **Resolve command** via `windows_spawn.resolve_command`. If unresolvable, yield an `error` event + `command_not_found` synthetic done.
3. **Build argv**: `[exe, *extra_args, *spec.args, *spec.prompt_subcommand_args, spec.prompt_arg_flag, "<task>"]` (the flag is omitted when None/empty so codex's `["exec", "<task>"]` works).
4. **Spawn** with stdin=PIPE, stdout=PIPE, stderr=PIPE; `text=True, encoding=utf-8`; `shell=resolved.use_shell` (Windows .cmd/.bat).
5. **Close stdin immediately** — most non-interactive CLIs need EOF to start producing output.
6. **`proc.communicate(timeout=deadline)`** captures stdout and stderr to EOF; on `TimeoutExpired` the child is killed and a final `communicate(timeout=5)` collects whatever was buffered.
7. **Persist captured output** as one transcript line per non-empty channel (`stdout`, `stderr`).
8. **Yield events**: one `assistant_message` event with `role:"assistant"` and the captured stdout in `text` (so `extract_last_assistant_text` picks it up verbatim and `trim_event_payload` can cap it for the LLM payload), one `log` event with `channel:"stderr"` if stderr was non-empty, then a synthetic `done` (`child_exited` or `timeout`) carrying `exit_code` and `elapsed_seconds`.

### `json-acp` / `tui-repl` / `one-shot` (long-lived child)

`agent/acpx/runtime.py::AcpSession.send_turn` is the heart. Per turn:

1. **Write `{"task":"...","mode":"session"}\n` to child stdin** (and `close()` for `transport="one-shot"`).
2. **Daemon reader thread** drains child stdout into a `queue.Queue` line-by-line. Cross-platform; needed because Windows `readline()` on a pipe cannot be interrupted.
3. **Drain loop** wakes every 100 ms (queue `get(timeout=0.1)`) and checks four completion conditions, in order:
   1. The child emits a JSON line with `"done": true` (strict ACP).
   2. The child closes stdout (process exit) — reader pushes a `None` sentinel.
   3. `timeout_seconds` elapsed (hard backstop) — yields `{done:true, _synthetic:"timeout", events_seen, transport}`.
   4. **Idle rule** fires — yields `{done:true, _synthetic:"idle", idle_seconds, events_seen, transport}`. The transport-aware variant of this rule is the real fix for slow ACPX execution:
      - `transport="json-acp"`: idle rule arms only after `event_count > 0` AND `now - last_event_at >= idle_seconds` AND `now - started_at >= startup_grace_seconds`. (A JSON-ACP child contractually emits at least one event per turn.)
      - `transport="tui-repl"` / `"one-shot"`: idle rule arms after `now - started_at >= startup_grace_seconds + idle_seconds` **even with zero events**. A silent TUI is, by definition, finished; the previous code waited the full timeout because it required `event_count > 0`.

4. **Every line received and the outbound task itself are appended to the per-session NDJSON transcript** at `<state_dir>/<session_id>.transcript.ndjson`. The transcript is what `acp_transcript` and `acp_relay` read from.

`acp_spawn` honors `spawn_returns_immediately`: for TUI agents it returns the `session_id` sub-second without draining; the drain happens on the next `acp_send` / `acp_send_and_wait` / `acp_transcript`. The LLM can override with `timeout_seconds>0` to force a drain on spawn.

---

> ⚠️ **TWO ACPX IMPLEMENTATIONS EXIST.** Everything in this file describes `Tlamatini/agent/acpx/`, which powers the Django chat. **`tlamatini_acpx.py`** (repo ROOT) is a deliberately separate, Django-free implementation backing the root stdio MCP server (`tlamatini_mcp_server.py`) for external MCP clients such as Claude Code or Kimi. It has its own registry, its own drain and its own `AcpxManager`. **A fix in one does NOT reach the other — check both.**
>
> As of v1.51.2 all three repairs below are ported to BOTH surfaces, and they deliberately **share one definition**: `tlamatini_acpx.py` loads `agent/acpx/child_health.py` **by file path** (it is stdlib-only and imports nothing from `agent.*`, so it loads outside Django) rather than keeping a second copy, because a duplicated verdict vocabulary drifts and a drifted copy mis-classifies silently. That load is fail-open — if it ever fails, classification degrades to the old "everything delivered" behaviour and `doctor()` **says so in its message** instead of hiding it. The stdio surface also reads the SAME `acpx.agents` block from `config.json`, so one config edit repairs a peer on both. > ### ⚠️ NEVER SPAWN AN ACP CHILD THROUGH THE SHELL — cmd.exe truncates the prompt
>
> Measured 2026-09-07 while closing a `.cmd` gap on the stdio side: **cmd.exe stops reading its command line at the first newline.** A 2,205-character multi-line research prompt reached the child as **40 characters**, cut at the first line break, silently — and the child answered the fragment as if it were the whole task. Re-measured on a real npm-shaped shim: 40 of 2,647 bytes. `shell=True` and an explicit `cmd.exe /d /s /c` fail identically; the limit is cmd.exe, not Python's quoting. ACPX prompts are long and multi-line by nature, so **the shell is not an acceptable channel for them**.
>
> The stdio surface therefore **de-shims** instead: `tlamatini_acpx._deshim()` parses the npm/pnpm wrapper (`"%_prog%" "%dp0%\node_modules\<pkg>\bin\<tool>.js" %*`) and spawns `node.exe <script.js>` directly with `shell=False` — the same trick `runtime_provisioner.resolve_spawn()` already uses for `npx`. Verified byte-exact: 2,647 of 2,647 characters. It also prefers a real `.exe` over a shim. When a shim cannot be rewritten the shell is a last resort, and a multi-line prompt on that path emits a loud `acpx` log event rather than being silently cut.
>
> **BOTH surfaces carry `_deshim`.** On the Django side it lives in `agent/acpx/windows_spawn.py` and the rewritten argv is returned in **`ResolvedSpawn.extra_args`** — the slot every caller already splats as `[executable, *extra_args, *spec.args, …]`, so bypassing the shim required **no change at any call site**. ⚠️ Keep `*resolved.extra_args` in the two `--version` probes (`probe_availability`, `_capture_cli_version`); dropping it probes a bare `node --version` and learns nothing about the agent (pinned by a source test). Both npm (`"%dp0%\…"`) and pnpm (`"%~dp0\…"`) wrappers are recognised. Measured across the nine installed peers: **7 spawn with no shell**; `kilocode` and `opencode` use a shim shape `_deshim` does not recognise and take the fail-open shell path, where a multi-line prompt raises the loud warning. Coverage: `tests.py::WindowsShimDeShimTests`.

## The delivery verdict — an exit code is ONE BIT, and it lies (v1.51.2)

`agent/acpx/child_health.py` is the ONE definition of *"did this child actually deliver the work?"*, consumed by both `runtime._oneshot_send_turn` (which stamps the verdict onto the `done` event) and `runtime.readiness_probe` (which powers `acp_doctor(deep=True)`). It is stdlib-only and imports nothing from `agent.*` — the same discipline as `agent_verdict.py`.

**Why it exists.** Measured 2026-09-07 on the installed build:

```
$ claude -p "Use WebSearch to find ..."
Angela, the web search was blocked — permission wasn't granted, so I
can't look up the current Python version.
$ echo $?
0
```

ACPX returned `ok: true`, the Exec Report row went **GREEN**, and the orchestrating LLM spent six further tool calls building on research that did not exist. Same silent-plausible-WRONG class as the PDFer missing-images bug and the LaTeXer linter verdict.

**The closed vocabulary of non-delivery** — every code means *the requested work did NOT happen*:

| code | what it means |
|---|---|
| `PERMISSION_BLOCKED` | the child stopped at its own permission prompt |
| `WORKSPACE_NOT_TRUSTED` | its cwd is untrusted, so its permission file was ignored |
| `NO_CREDIT` | the account behind the CLI has no credit |
| `USAGE_LIMIT` | a plan / session / rate limit was hit |
| `AUTH_FAILED` | the CLI could not authenticate |
| `CONFIG_INVALID` | the CLI refused its own config file |
| `UPSTREAM_ERROR` | the model provider returned a server-side error |
| `NO_OUTPUT` | nothing legible came back (a silent TUI, or pure chrome) |
| `CHILD_ERROR` | exited non-zero with no usable answer |
| `DELIVERED` | real work |

`tools._ok_unless_blocked()` turns a non-delivery into `{"ok": false, "code": ..., "reason": ..., "evidence": ...}` on `acp_spawn` / `acp_send` / `acp_send_and_wait`. **The full payload is preserved on the failure envelope** (session_id, transcript_path, events) because the LLM still has to read the transcript and kill the session.

### CONTRACTS — do NOT weaken

1. **A long, real answer is NEVER reclassified as a failure.** Only short, empty or letter-less output is scanned for refusal markers, and markers are read from the HEAD of the output only. A 3 KB briefing that merely *mentions* "rate limit" stays a success.
2. **SHORT IS NOT EMPTY.** The first draft tested the letter count alone and flagged a perfectly good 7-character `PEER_OK` as `NO_OUTPUT` — the exact false-failure class this module exists to prevent. "Chrome" requires BOTH `len >= DECORATIVE_MIN_CHARS` **and** `alnum < MIN_ALNUM_CHARS`.
3. **FAIL-OPEN.** Anything unrecognised is DELIVERED. `classify_child_output` never raises.
4. **`acp_doctor(deep=True)` stays opt-in.** A readiness probe sends a real prompt and spends the user's money; the result is cached 10 minutes. `ready: null` is an honest "this transport cannot be probed without a session", never an invented verdict.
5. Do NOT soften `_ok_unless_blocked` back into an unconditional `_ok`.

Coverage: `agent/acpx/tests.py::ChildHealthClassifierTests` — every string in it was copied verbatim from the transcripts of the run that failed.

---

## Permission model

`agent/acpx/permissions.py::PermissionGate` enforces three modes (matching OpenClaw's vocabulary verbatim):

- `approve-reads` (default) — read actions are auto-approved; write actions go through the gate.
- `approve-all` — flagged dangerous; auto-approves everything.
- `deny-all` — blocks all spawns. `acp_spawn` raises `PERMISSION_DENIED`.

`non_interactive` policy is `deny | fail` for unattended runs.

---

## ACPXer — the visual canvas counterpart

The 12 tools above are the **LLM-facing** ACPX surface. **ACPXer** is the **canvas-facing** counterpart: a workflow agent (one of the 71 in the visual ACP designer) that drives ONE ACPX session lifecycle from a drag-and-drop node.

- **Lives at**: `agent/agents/acpxer/acpxer.py` + `config.yaml`. Self-contained — does NOT import `agent.acpx.runtime`, so it works identically in source and frozen builds (the agent pool runs as separate Python subprocesses with no path back into the Django app). It mirrors the runtime's transport-aware drain rule and `agent_id` registry inline.
- **What it does, in order**: read `config.yaml` → resolve `agent_id` → command + transport + budgets via the registry mirror → spawn the child via `subprocess.Popen` → write task envelope (`{"task":..., "mode":"session"}\n` for `json-acp`, raw `task\n` for `tui-repl`) → drain stdout via daemon reader thread + 100-ms tick + 4-rule completion (json `done:true` / child exit / hard timeout / transport-aware idle) → extract last-assistant text → kill child → emit `INI_SECTION_ACPXER<<<` block → trigger `target_agents`.
- **Transcript format**: writes `<agent_dir>/transcript.ndjson` with the SAME `{"direction": "in"|"out", "text", "raw", "ts"}` lines that the in-process runtime writes — the two formats are interchangeable, so a future tool could read an ACPXer transcript via the existing `read_transcript` helper without modification.
- **Output contract** (consumed by Parametrizer, registered in `views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS['acpxer']`): KV header `agent_id`, `session_id`, `transport`, `settle`, `transcript_path`; body = `response_body` (= last-assistant text). This means the canonical visual relay flow is:
  ```
  Starter → ACPXer(claude) → Parametrizer → ACPXer(gemini) → Parametrizer → ACPXer(cursor) → File-Creator → Ender
  ```
  Each Parametrizer copies the previous ACPXer's `response_body` into the next ACPXer's `task` — three different LLMs argue back and forth in a fully visual, fully unattended pipeline.
- **Relationship to the 12 tools**: same `agent_id` registry (claude / cursor / gemini / qwen / codex = `oneshot-prompt`; tlamatini = `json-acp`; kiro / kimi / iflow / kilocode / opencode / pi / droid / copilot = `tui-repl`); same transport-aware drain rule for legacy paths; same fresh-process-per-turn capture path for `oneshot-prompt`; same NDJSON transcript format; same default budgets per transport. **The two surfaces produce interchangeable artefacts**.
- **When to use which**:
  - LLM operator in this chat ("spawn claude and relay to gemini") → use the 12 tools (`acp_spawn` / `acp_send_and_wait` / `acp_relay` / `acp_kill`).
  - Visual / .flw / Croner-scheduled / unattended flows → use ACPXer nodes on the canvas. FlowCreator (the AI flow designer) knows the patterns.
- **CSS gradient (Aurora Conduit)**: `.canvas-item.acpxer-agent { linear-gradient(135deg, #0B1F3A 0%, #5A1FB8 33%, #EC4899 66%, #22D3EE 100%) }` — cosmic-navy → electric-violet → luminous-magenta → cyan-radiance. Distinct from `.acpx-agent` (the LLM-driven exec-report row, fire-orange) so the user can tell at a glance which surface is in play.

---

## Files involved

- `agent/acpx/agent_registry.py` — `DEFAULT_ACP_AGENTS`, `AcpAgentSpec` (transport, defaults, `spawn_returns_immediately`), `build_agent_registry(overrides, env_overrides, spec_overrides)`, `OVERRIDABLE_SPEC_FIELDS`, `VALID_TRANSPORTS`, `_respec` (fail-open override application).
- **`agent/acpx/child_health.py`** — the ONE definition of "did the child deliver?": `classify_child_output` + the closed non-delivery vocabulary + `summarize_for_doctor`. Stdlib-only, imports nothing from `agent.*`. See *The delivery verdict* above.
- `agent/acpx/runtime.py` — `AcpxRuntime`, `AcpSession`, daemon reader thread, transport-aware idle rule, doctor (`deep=` readiness), `readiness_probe`, list_sessions, session_status, read_transcript, kill (returns record), event trimming, last-assistant extraction. `_oneshot_send_turn` stamps the delivery verdict onto the `done` event.
- `agent/acpx/tools.py` — the 12 LangChain `@tool` functions, plus `_delivery_verdict` / `_ok_unless_blocked` so a refusal is never reported as a success.
- `agent/acpx/session_store.py` — `FileSessionStore`, reset-aware semantics.
- `agent/acpx/permissions.py` — permission gate.
- `agent/acpx/config.py` — config schema mirror of OpenClaw's plugin.json.
- `agent/acpx/windows_spawn.py` — Windows-aware command resolution.
- `agent/acpx/tests.py` — **92** unit tests covering every tool, the redesigned drain, the child-health classifier (pinned against the real 2026-09-07 failure output), the config-driven spec overrides, and the blocked-child-is-not-a-success envelope.
- `agent/capability_registry.py` — `_EXTRA_HINTS_BY_TOOL_NAME` ACPX entries, `_ACPX_SIGNAL_TOKENS` boost, `ACPX_CO_SELECTION_RULES` (sibling auto-injection).
- `agent/global_execution_planner.py` — applies `ACPX_CO_SELECTION_RULES` so e.g. selecting `acp_spawn` auto-co-selects `acp_doctor` + `acp_kill`.
- `agent/mcp_agent.py` — `_EXEC_REPORT_TOOLS` registers ACPX rows under `agent_key="acpx"` so spawn / send / send_and_wait / kill / relay merge into one Exec Report table.
- `agent/prompt.pmt` rule 12 — the LLM-facing version of this contract.
- `agent/agents/acpxer/acpxer.py` + `config.yaml` — the **visual ACPXer** workflow agent (canvas counterpart of the 12 tools). Self-contained subprocess that mirrors the runtime's transport-aware drain in ~120 lines, writes interchangeable NDJSON transcripts, emits Parametrizer-compatible `INI_SECTION_ACPXER<<<` blocks.
- `agent/agents/parametrizer/parametrizer.py` — `SECTION_AGENT_TYPES` includes `'acpxer'` so Parametrizer can pipe ACPXer output into a downstream node's config.
- `agent/views.py` — `PARAMETRIZER_SOURCE_OUTPUT_FIELDS['acpxer']` lists the 6 fields downstream agents can address: `agent_id`, `session_id`, `transport`, `settle`, `transcript_path`, `response_body`.
- `agent/agents/flowcreator/agentic_skill.md` — entry #58 documents ACPXer for the AI flow-designer (FlowCreator); it includes the four canonical flow patterns (single-shot CLI run, visual multi-CLI relay, scheduled audit, branching on CLI failure).
- `agent/agents/flowhypervisor/monitoring-prompt.pmt` — `ACPXER SPECIAL NOTES` block tells the watchdog to NOT flag long-running drains, NOT flag a `settle=timeout` line as an error, and NOT flag content of `INI_SECTION_ACPXER<<<` blocks; it DOES flag `Command not resolvable on PATH` as a real error.

---

## ACPX-Skills admin menu (chat navbar dropdown)

Added 2026-05-17. The chat navbar has a fourth dropdown — **ACPX-Skills** — that admins every SKILL.md package under `agent/skills_pkg/`. Position is between **Agents** and **Config** in `agent/templates/agent/agent_page.html`.

Four entries:

| Entry | Backing | What it does |
|---|---|---|
| **Browse Skills** | `GET /agent/skills/` (list) + `GET /agent/skills/<name>/` (detail) | Search-filterable list pane + detail pane showing frontmatter, requires, inputs/outputs, permissions, body. Pure read; no DB writes. |
| **Configure Skills** | WebSocket `set-skills` channel (mirrors `set-mcps` / `set-agents` exactly) | Checkbox grid toggling `Skill.enabled` per row. Payload encoding: comma-separated `name=description=true/false`. |
| **Diagnostics** | `GET /agent/skills/_/diagnostics/` | Cross-checks every skill's `requires_tools` / `requires_mcps` against disabled `Tool` / `Mcp` rows; flags `runtime:acpx` skills whose `acpx_agent` isn't in the registry; surfaces orphan DB rows (Skill row exists, SKILL.md gone). |
| **Reload Registry** | `POST /agent/skills/_/reload/` | Re-runs `agent/acpx/service.py::boot_skills()` — rescans `agent/skills_pkg/`, refreshes Skill rows, prunes deleted ones. No server restart needed. |

### Persistence shape (DB stays at "enumeration + enable/disable" only)

The `Skill` model was pre-existing from migration `0071_acpx_skills.py` and is auto-seeded by `boot_skills()` from `apps.AgentConfig.ready()` on a background thread. The admin UI **only ever writes `Skill.enabled`** via `consumers.AgentConsumer.save_skill(name, enabled)`. The cached fields (`description`, `runtime`, `acpx_agent`, `frontmatter_json`, `body_sha256`) are owned by `boot_skills()` and refreshed from SKILL.md on every reload — the disk is the only source of truth for permissions, budgets, body. Browse / Diagnostics read fresh from `skill_registry`, not from those cached columns.

### Tool-surface gating

When `Skill.enabled = False`:
- `list_skills` (`agent/acpx/tools.py`) filters the row out of its return value.
- `invoke_skill` returns `{"ok": false, "code": "SKILL_DISABLED"}`.

Implemented via `_disabled_skill_names()` in `agent/acpx/tools.py` — **fails open** (empty set on any DB exception) so a broken admin layer never silently hides skills from the LLM. The ACPX toolbar checkbox is the orthogonal global gate; both must allow the skill for the LLM to see it.

### WebSocket wiring (mirrors Mcps/Agents/Tools verbatim)

- `consumers.skill_establishment(name, description, enabled)` sends one `type:'skill'` system message per Skill row on connect (both the rebuild path and the session-restore path).
- Frontend `agent_page_chat.js` catches those and pushes into the module-level `skills = []` array (declared in `agent_page_state.js`).
- The Configure dialog (`skills_dialog.js::preRenderSkillsConfigureDialog`) reads from that array; Continue dispatches `set-skills` via `sendChatSocketMessage`.
- Backend `set-skills` handler in `consumers.receive()` parses the payload and calls `save_skill(name, enabled)` — touches only `Skill.enabled`.

### Naming convention (no `<prefix>-N` shim for Skills)

`Skill` rows are keyed on `name` (the SKILL.md frontmatter `name`, e.g. `acp-router`) directly. There is NO `skill-N` ID-prefix transformation like the `mcp-N` / `tool-N` / `agent-N` pattern uses — the SKILL.md `name` is already unique. The `_normalize_toggle_record_name('skill', ...)` helper in `consumers.py` does NOT apply.

### Files

- Backend: `agent/views.py` (`list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`); `agent/urls.py` (4 routes); `agent/consumers.py` (`skill_establishment`, `get_all_skills`, `save_skill`, `set-skills` handler, establishment loops in both rebuild paths); `agent/acpx/tools.py` (`_disabled_skill_names()` + gating in `list_skills` / `invoke_skill`).
- Frontend: `agent/templates/agent/agent_page.html` (navbar dropdown + 3 dialog containers + asset includes); `agent/static/agent/js/skills_dialog.js` (jQuery-UI dialogs for all 4 entries); `agent/static/agent/js/agent_page_init.js` (`OpenSkillsXyzDialog` + `ReloadSkillRegistry` entry points); `agent/static/agent/js/agent_page_chat.js` (`type:'skill'` system-message handler); `agent/static/agent/js/agent_page_state.js` (`let skills = []` global); `agent/static/agent/css/skills_dialog.css` (styling).
- Lint: `eslint.config.mjs` (11 new globals: `skills`, `computeCheckboxGridLayout`, `OpenSkills*Dialog`/`preRender`/`render`/`open`/`reload` family).
- Coverage: 14 tests in `agent/tests.py` — `SkillsAdminEndpointTests` (7), `SkillsToolSurfaceGatingTests` (3), `SkillsNavbarTemplateContractTests` (4). The template-contract class pins the dropdown HTML so a careless edit doesn't silently drop the menu.

---

## When the user says "ACPX" (decision matrix)

| User says... | You do... |
|---|---|
| "Use ACPX to ..." / "ACPX mechanics" / "ACP child" | Recognize as an ACPX request. Run a canonical flow per the prompt's steps. |
| "Spawn a child" / "external coding agent" | `acp_doctor` → `acp_spawn`. |
| "Wait for the full answer" / "complete answer" | `acp_send_and_wait` with longer `until_idle_seconds`. |
| "Harvest the transcript" / "cite the transcript" | `acp_transcript`. |
| "Hand off" / "leg A → leg B" / "relay" / "multi-CLI" | `acp_relay`. |
| "Pin leg A to gemini" | `agent_id="gemini"` exactly. Fallback only if not resolvable. |
| "Is the session alive?" / "session status" | `acp_session_status`. |
| "List sessions" / "what's running" | `acp_list_sessions`. |
| "Kill the session" / "terminate" / "graceful kill" | `acp_kill`. |
| "Pick the best agent for ..." | `invoke_skill('acp-router', {intent, prefer})`. |
| "Summarize the transcript" | `acp_transcript` → `invoke_skill('summarize', {...})`. |
| "Build a visual flow that uses ACPX" / "Draw a multi-CLI relay" / ".flw with ACPX" / "scheduled multi-CLI" / "Croner-driven ACPX" | This is the **ACPXer canvas surface**, not the 12 tools. Hand the request to FlowCreator (or describe the canvas wiring): `Starter → ACPXer(<id>) → Parametrizer → ACPXer(<id>) → ... → Ender`. Do NOT use `acp_spawn` here. |
| Anything not in this table but mentioning ACPX | Run `acp_doctor` first to ground yourself, then pick the closest flow. |
