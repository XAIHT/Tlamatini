<!-- Tlamatini Author Banner — Angela López Mendoza -->
# Terminater — visible, user-supervised terminals

> **Status: on `main`, not yet released.** The latest released version is
> **[v1.87.0](changes/2026-10-18-v1.87.0.md)**; Terminater is work done after it
> (see [the change record](changes/2026-10-19-terminater.md)). Dated evidence
> below keeps its original date.

Terminater is the 86th workflow agent and the first one whose result you can
*watch*. **Executer** runs a command and hands back text. **Terminater** raises a
real `cmd.exe` / PowerShell terminal inside Tlamatini's **Terminals** area
(**Views ▸ Terminals**, or <kbd>Ctrl</kbd>+<kbd>`</kbd>), types the command into it
*like a person*, waits for the command itself, and reads the answer back. The user
can read along, interrupt, answer a question the command asks, or finish a line
Tlamatini only started.

Use Executer when nobody needs to watch. Use Terminater when the user wants to see,
learn from or supervise the commands: a walk-through, Step-by-Step mode, an installer
that asks questions (`ssh`, a Python REPL, `winget`, `npm init`), CMD next to
PowerShell, or a parameter or secret that only the user can supply.

## The five rules the engine enforces

Each one is a user requirement; none may be weakened.

1. **Tlamatini types.** There is no code path that writes a command into a terminal
   in one go. `TerminalSession.type_text` feeds one key at a time through
   `terminater_text.plan_typing`: a log-normal rhythm around `typing_wpm`
   (default **50**, allowed **20–160**), extra cost for shifted keys and word
   boundaries, an occasional short pause, and a hard floor of **30 ms** between keys.
   No paste, no "instant" switch. A 60-character command takes about 15 s on purpose.
   (`TEST_TIME_SCALE` exists only as a module global for the test suites; the API,
   `config.yaml` and the model cannot reach it.)
2. **Output is returned in full.** Each command keeps up to 400,000 characters and
   reports an honest `truncated` flag; nothing is cut silently.
3. **A hung command is detected, not guessed.** No output for `hang_seconds`
   (default **45**) flags it `hung`. `abort` presses Ctrl+C, again, then kills the
   command's child processes; the terminal survives. `kill` closes a terminal
   gracefully; `force_kill` kills the shell and its whole tree (a Windows job object
   with *kill on close*; psutil/taskkill is the fallback).
4. **The user always wins.** A key the user presses is never lost; **Esc** (or
   Ctrl+C) stops Tlamatini's typing at once; a line Tlamatini only half-typed can be
   handed over to be finished.
5. **Everything the user types is observable** (`watch_user`) and a deterministic
   advisor (`advise_line`) warns about dangerous or mistyped commands while they are
   typed, with no model round trip.

## Actions

One action per run. Terminals persist in the hub between runs, so a flow can open a
terminal in one step, type in the next and close it in a third.

| Group | Actions |
| --- | --- |
| Run | `run` (default: open-or-reuse, type, wait, read), `open`, `type`, `send_key`, `wait` |
| Read | `read` (`which`: `last`, a command number, `screen`, `all`), `commands`, `list`, `status` |
| Stop | `abort`, `kill`, `force_kill`, `kill_all` |
| Arrange | `focus`, `rename`, `layout` (`tabs`, `tile`, `tile-h`, `tile-v`, `grid`; area `dock` or `full`), `clear` |
| The user | `watch_user`, `warn_user` (severity `info`, `hint`, `warning`, `danger`), `handover` |

**Hand-over.** `<<USER:hint>>` inside the text gives the keyboard to the user at that
point: `ping <<USER:host to ping>> -n 2` types `ping `, waits for the user to type the
host and press Enter, then types ` -n 2`. `secret: true` keeps that part out of every log
and result. If the user does not finish within `user_wait_seconds` (default **300**), the
status is `operator_required`, never a guess.

**Shells.** `kind` is `cmd`, `powershell` (default) or `pwsh`. PowerShell reports exit
codes; CMD cannot report an empty one and says so. Shell prompts are recognised through
OSC 133 markers, with a prompt-regex fallback after a 6 s grace period.

**Limits and switches** (all in `config.json`, all optional). The number of open terminals
is sized from the machine, never from the core count alone: 4 to 12 by core count, capped at
6 below 10 GiB of RAM and at 4 below 6 GiB; `terminater_max_terminals` fixes it explicitly
and is obeyed exactly. `terminater_hang_seconds` sets the hub's hang threshold.
`terminater_enabled: false` switches the feature off: the WebSocket closes with code 4404,
the API answers that Terminater is switched off, and the state view reports `enabled: false`.

## Results and verdicts

Every run emits one atomic `INI_SECTION_TERMINATER` block whose fields are registered
for Parametrizer (`agent_contracts._PARAMETRIZER_OUTPUT_FIELDS['terminater']`):
`action`, `status`, `success`, `terminal_id`, `kind`, `title`, `terminal_state`,
`command`, `exit_code`, `duration_seconds`, `output_chars`, `truncated`, `hung`,
`aborted_by`, `typed`, `user_part`, `user_line`, `user_keys`, `cursor`,
`watch_reason`, `wait_reason`, `layout`, `area`, `terminals`, `hub`, `message`,
`response_body`. `typed` is exactly what Tlamatini typed and `user_part` exactly what
the user typed, so a result can always say who did what.

The status words join the closed vocabulary of `agent_verdict.py`:

| Token | Set | Colour |
| --- | --- | --- |
| `completed`, `opened`, `typed`, `killed`, `focused`, `warned` | work completed | green |
| `command_failed`, `hung` | work degraded: the terminal worked, the requested work did not | red |
| `operator_required` | work degraded: parked until a person finishes a hand-over, so the work has not happened | red |
| `aborted` | work not done: typing or the command was stopped (Ctrl+C or the user took over) | red |

A command that exits non-zero is therefore a **red** row even though the terminal did
its job. Downstream agents always start (success or not), so a Forker can branch on
`{status}` or `{exit_code}`.

## Where the terminals live

```
browser pages (chat, Agentic Control Panel, Prompt Flow Panel)
        │  ws/terminals/  (session-authenticated, same-origin)
        ▼
terminal_consumer.TerminalConsumer ──►  TerminalHub  (terminater_engine.py, in the Django process)
                                              ▲   ▲
pool agent (agents/terminater/terminater.py)  │   │  Prompt Flow Panel runner (in-process)
   POST /agent/terminater/api/  ──────────────┘   └── terminal_hub.run_action(...)
   loopback only + X-Terminater-Token
```

* **The hub owns the shells; the page is only a window.** Closing or reloading a page
  never kills a terminal, and every tab of the same user sees the same terminals.
  Tlamatini can raise, type into and kill terminals whether or not a page is open.
* **The loopback API** (`terminal_views.terminater_api_view`) accepts only
  `127.0.0.1` / `::1` and a per-run token compared in constant time. The token reaches a
  pool agent through `TLAMATINI_TERMINATER_TOKEN` / `TLAMATINI_TERMINATER_URL` and
  through the rendezvous file `<app>/Temp/.terminater_hub.json`. It is scrubbed from the
  environment of the shells themselves and is never logged. The authenticated read-only
  `GET /agent/terminater/state/` lets a page redraw its tabs.
* **`mode`** (agent config): `auto` uses the hub when reachable and otherwise runs
  standalone (its own terminals, which die with the agent); `hub` refuses without a hub;
  `standalone` never uses one.
* **Engine files load by path.** `terminal_hub.load_engine()` reads
  `agents/terminater/terminater_engine.py` from the agents tree (`get_agents_root()`), so
  the web process, the pool copy and the test suites share one definition. The engine
  and its two siblings (`terminater_conpty.py`, `terminater_text.py`) are standard-library
  only, because the same files run in the web process and under the carried Python.
* **ConPTY, through `ctypes`.** `CreatePseudoConsole` needs Windows 10 1809 or newer.
  Importing the module never raises on an older machine; constructing a `ConPty` does,
  with a human sentence. Every Win32 prototype declares `argtypes`/`restype`
  (handles are pointer-sized), and `ClosePseudoConsole` runs on its own thread so it
  cannot deadlock a drain.
* **Reapers leave the terminals alone.** `command_watchdog` and `orphan_reaper` ask
  `terminal_hub.live_pids()` (which never creates the hub) so a shell parked at its prompt
  is not mistaken for a hung one. The shutdown sweep and the hub's `atexit` hook still
  remove every shell tree when Tlamatini exits.

## The Terminals area

`terminater_dock.js` (with `terminater_dock.css` and a locally vendored **xterm.js 5.5.0**,
`xterm-addon-fit` 0.10.0 and `xterm-addon-web-links` 0.11.0 — integrity-pinned by
`scripts/vendor_frontend.py`, no CDN, source maps omitted) is mounted by three pages
through `data-tlm-terminals-host="chat|acp|pfp"`:

* **Chat** — **Views ▸ Terminals**. With the canvas hidden the terminals can still show
  (`tlm-terminals-on`).
* **Agentic Control Panel** and **Prompt Flow Panel** — a new **View** menu with the same
  check item.

The dock has a tab strip, a type bar (CMD / PowerShell), tiling (`tabs`, `tile`,
`tile-h`, `tile-v`, `grid`), a `dock`/`full` area, and overlays for hand-over, hung
commands and warnings. Terminal states are `starting`, `prompt`, `typing`,
`awaiting_user`, `running`, `exited`, `closed`. Keystrokes the user types are sent in
order and never swallowed by the page; the server drops them only while Tlamatini is
typing, and says how to take over (Esc). Hiding the dock keeps every shell alive; every
failure is fail-open and shows a message in the dock, never breaking the host page.
When a terminal needs the user, the dock dispatches `tlm:terminals-handover` and the
Agentic Control Panel closes its Start dialog by itself so the terminal holds the keyboard
without a click.

## In chat, canvas and flows

* **Multi-Turn** — `chat_agent_terminater` (the 67th wrapped agent). Its description tells
  the model to prefer it for anything the user should see, to let long commands type slowly,
  and never to shorten a command to save time. It is on the **Ask Execs** allowlist as a
  command runner (visible does not mean harmless); the permission dialog previews exactly
  what will be typed and in which shell ("TERMINATER COMMAND TO TYPE"). The Exec Report row
  uses the generic fallback with the native **Phosphor Console** caption.
* **Agentic Control Panel** — Terminater is an ordinary active agent: a wire *from* its node
  adds the downstream agent to `target_agents` (`update_terminater_connection_view`).
* **Prompt Flow Panel** — `terminater` is the 8th executable operation (a parallelogram;
  the palette now has nine assets with the static commentary note). Actions run in the
  user's own terminals; `run`, `type` and `handover` take the node's text. Output feeds
  `{{last_output}}`. A failed, hung or timed-out command is still a delivered result a
  Decision can branch on; only a hub refusal stops the flow. **Stop** aborts typing and the
  running command. Python and the JavaScript model validate the same action table, kinds and
  numeric ranges.
* **Catalog of Prompts** — three SAFE cards in *Run & Execute*: **127 FIRST LOOK**,
  **128 HAND-OVER** (`ping <<USER:...>>`) and **129 GUIDED TOUR** (CMD and PowerShell tiled,
  then `watch_user`; a Step-by-Step card).
* **FlowCreator and FlowHypervisor** — FlowCreator's reference and `flow_catalog.json` list
  Terminater; the watchdog prompt has a *TERMINATER SPECIAL NOTES* block: a quiet stretch
  while a person types or a hand-over waits for a human is normal for up to
  `wait_seconds + user_wait_seconds`.

## Release carriage

* **Migrations** `0215` (Agent row `Terminater`), `0216` (`Chat-Agent-Terminater` Tool row —
  required, or the wrapper is invisible while Compact mode is on), `0217` (prompts 127–129).
  The display name is pinned in `services/agent_paths.py::display_name_from_agent_type`.
* **Frozen build** — `agent.terminal_hub`, `agent.terminal_consumer`, `agent.terminal_views`
  and `agent.management.commands.check_terminater` are hidden imports and
  `_FROZEN_TERMINATER_MODULES` (so `verify_frozen_agent_modules()` proves they shipped). The
  agent folder ships **loose** beside the executable; the pool agent runs under the carried
  Python. `build.py` runs `check_terminater` inside the freshly frozen app, right after the
  Prompt Flow Panel gate, and **refuses to package** if it fails. The gate drives a real
  PowerShell, a real `cmd.exe`, the shipped pool agent under the carried Python and a real
  WebSocket round trip (with the host and origin headers the same-origin check requires).
* **Inventories** — `build_runtime_assets.py` (`REQUIRED_STATIC`) and
  `copy_source_assets.py` (`REQUIRED_SNAPSHOT_FILES`) name every file, including the vendored
  renderer and the six visible scripts.

## Verification

Run everything from a visible foreground console.

```bash
python Tlamatini/manage.py check_terminater
python Tlamatini/manage.py test agent.test_terminater_text agent.test_terminater_engine agent.test_terminater_hub_api agent.test_terminater_pfp agent.test_terminater_agent agent.test_terminater_integration
python scripts/terminater_visible_all.py
```

The six test modules run against **real** `cmd.exe` and `powershell.exe` processes (with
typing time scaled down by the test hook). The visible scripts drive headed Chrome and
photograph each step with Shoter: `terminater_visible_chat.py`, `_acp.py` (including the
hand-over inside a running flow), `_pfp.py`, `_battery.py` and `_all.py`.

Recorded evidence is in [the change record](changes/2026-10-19-terminater.md). It describes
the tested environment (Windows 11, source mode and a frozen interpreter), not every
machine.

## Honest limits

* Windows only (ConPTY, Win32 job objects). On another system the feature reports that it is
  unavailable instead of failing.
* Typing is slow by design; a model asked for speed must not split or shorten commands.
* `input_sent`-style delivery is not proof an application accepted the input; read the
  output. A command that asks a question nobody answers ends as `operator_required`.
* The advisor is a deterministic safety net, not a sandbox: it warns, it does not block.
* Terminals belong to the Tlamatini process. They end when it exits.
