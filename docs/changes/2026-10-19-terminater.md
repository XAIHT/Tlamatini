<!-- Tlamatini — Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove -->
# 2026-10-19 — Terminater: visible, user-supervised terminals

**Status: released in [v1.88.0](2026-10-20-v1.88.0.md)** (tagged 2026-10-20), carried in [v1.91.1](2026-10-27-v1.91.1.md). This record covers the work done after [v1.87.0](2026-10-18-v1.87.0.md):
the 86th workflow agent, the **Terminals** area on three pages, the 8th Prompt Flow
Panel operation and the build gate that proves it works in a frozen app. The
design and every operating rule are in [docs/terminater.md](../terminater.md).

## What it is, in one paragraph

Executer runs a command and returns text. Terminater raises a real `cmd.exe` or
PowerShell in a terminal the user can see (**Views ▸ Terminals**, or Ctrl+`), types the
command into it one key at a time like a person, waits for the command, and reads the
answer back. The user can watch, interrupt (Esc), answer a question the command asks,
or finish a line Tlamatini only started (`<<USER:hint>>`). A command that hangs is
detected and can be aborted; the terminals outlive any page and die with Tlamatini.

## What changed

| Area | Files | Size |
| --- | --- | --- |
| Engine (stdlib-only, loaded by path) | `agents/terminater/terminater_engine.py`, `terminater_conpty.py`, `terminater_text.py` | 1,621 + 658 + 923 lines |
| Pool agent | `agents/terminater/terminater.py`, `config.yaml` | 686 lines |
| Hub, WebSocket, loopback API | `terminal_hub.py`, `terminal_consumer.py`, `terminal_views.py` | 338 + 266 + 69 lines |
| Terminals area | `static/agent/js/terminater_dock.js`, `css/terminater_dock.css`, vendored `xterm` 5.5.0, `xterm-addon-fit` 0.10.0, `xterm-addon-web-links` 0.11.0 | 892 + 269 lines, 7 vendored files |
| Pages | `agent_page.html` (Views ▸ Terminals), `agentic_control_panel.html` and `prompt_flow_panel.html` (new **View** menu) | one host element and three scripts each |
| Registration | `chat_agent_registry.py` (the 67th wrapped agent), `services/agent_contracts.py` (27 output fields), `services/agent_paths.py` (display name), `agent_verdict.py` (status words), `views.py` + `urls.py` (connection view, API, state), `routing.py` (`ws/terminals/`), `apps.py` and `tools.py` (hub token before any pool agent starts), `mcp_agent.py` (Ask Execs allowlist, preview text) | |
| Safety nets | `command_watchdog.py`, `orphan_reaper.py` consult `terminal_hub.live_pids()` | |
| Prompt Flow Panel | `services/prompt_flow_panel.py`, `prompt_flow_panel_runtime.py`, `prompt-flow-panel-model.js`, `prompt-flow-panel.js`: the `terminater` operation | |
| Migrations | `0215_add_terminater`, `0216_add_chat_agent_terminater_tool`, `0217_add_terminater_demo_prompts` (prompts 127-129) | |
| Build and carriage | `build.py` (`_FROZEN_TERMINATER_MODULES`, hidden imports, gate), `build_runtime_assets.py`, `copy_source_assets.py`, `scripts/vendor_frontend.py`, `management/commands/check_terminater.py` (new), `check_prompt_flow_panel.py` | |
| Documentation | `docs/terminater.md` (new), `agents_descriptions.md`, FlowCreator's `agentic_skill.md`, FlowHypervisor's `monitoring-prompt.pmt`, `docs/agent-coverage.md` (generated), the assistant guides | |
| Tests | six `test_terminater_*.py` modules (627 tests), `terminater_testkit.py`, six `scripts/terminater_visible_*.py` (about 2,400 lines) | |

Counts in v1.88.0: **86 workflow agents, 67 wrapped chat agents, 109
built-in tools, 51 structured-output producers, 217 migrations, 60 JS modules, 27
stylesheets.** The static suffix for that release was
`-agent-catalog-1-quality-cleanup-1-usage-status-2-terminater-1`.

## Defects found and fixed while validating it

* **The dock reported a stale line.** The dock reports what the user is typing, read
  from xterm's own screen, but a shell echoes the keys a moment after they are sent, so
  the line could be read before the echo and `watch_user` and the advisor saw an old
  one. The dock now re-reads the line when output arrives within 2.5 s of a keystroke.
* **Hiding the dock was not told to the hub.** A user who hid the area left the server
  believing it was visible; `setVisible` now reports the change.
* **A hand-over inside a running flow was unreachable.** The Agentic Control Panel's
  Start dialog is a modal that traps the keyboard, so a terminal asking for the user's
  input could not receive it. The dock dispatches `tlm:terminals-handover` and the panel
  closes the dialog by itself (also when a terminal is already waiting).
* **Tooltip.** The canvas tooltip text comes from `agents_descriptions.md`; Terminater
  had no row, so its tile had no purpose text. The row is added and verified at the data
  layer (`_load_agent_purpose_map()` now returns 86 entries, Terminater included, with
  the word "terminal").
* **The build gate refused the kickoff example.** `check_prompt_flow_panel` required the
  shipped example to contain every operation; Terminater needs a real terminal and is not
  in the example. The gate now holds the example to the seven prompting operations and
  validates a Terminater step separately.
* **The private-data guard test** flagged base64 inside vendored files as tokens; the
  token pattern is now boundary-aware and excludes vendored folders.
* **Frozen mode was unproven.** A source run proves nothing about the frozen layout, so
  `check_terminater` became a permanent gate run inside the frozen app (see below).

## Evidence (all on 2026-10-19, Windows 11)

| Check | Result |
| --- | --- |
| Unit suites: the six Terminater modules (627 tests, against real `cmd.exe` and `powershell.exe`) plus the registration guards (display names, status vocabulary, verdict engine, Ask Execs allowlist, catalog contiguity) | **774 tests, OK, 224.5 s** (`Temp/terminater-visible/docs-unit-all.log`, 23:10-23:15) |
| `manage.py check_terminater` (source) | PowerShell, `cmd.exe` and the pool agent completed; the WebSocket answered `hello` and `opened`; 6 assets resolved; 3 pages carry the dock |
| Frozen layout probe, run inside the frozen interpreter | **30 checks, 0 failed**: engine loaded by path from the shipped agents tree, sibling modules imported, static files collected, three pages, API/state/WebSocket routes, real PowerShell and `cmd.exe`, an authenticated socket, no shell left alive |
| The shipped pool agent under the carried Python, in the frozen layout | completed; wrote its `INI_SECTION_TERMINATER` and quoted the output |
| Prompt Flow Panel visible suite (headed Chrome, Shoter photographs) | **514 / 514** (20:23) |
| Agentic Control Panel hand-over inside a running flow | **33 / 33** (20:46) |
| Both inclusion sweeps (self-modify, self-update) | RESULT: CLEAN (a real rebuild and a real update were **not** executed) |
| Documentation pass (same day) | 533 relative links in the 41 edited or new Markdown files, **0 broken**; the Gemini skill mirror 5 / 5 in sync; `skill_inventory.py --check` OK; the FlowCreator catalog regenerated and verified (86 agent types); the architecture atlas rebuilt with LaTeXer (every tracked file present); the dossier PDF and deck regenerated with a clean verifier (no overflow, no clipping, tree parity for every tracked file); a by-value scan found no live secret in any generated or edited document |

What this does **not** establish: the chat-page and canvas suites were last saved at
19:30 (430 of 434 checks) and 20:10 (500 of 503); their failures were harness state left
over from earlier runs and the missing tooltip row above, all fixed afterwards, and they
were **not re-run as one clean pass**. The frozen probe was run inside the frozen
interpreter, not through a browser driven in the foreground (an earlier foreground
attempt was polluted by another window). No installer build was made. PowerPoint's own
native check of the dossier deck **did not run**: starting `PowerPoint.Application`
through COM failed twice with *Server execution failed* in that session, so only the
structural check of the deck (python-pptx geometry) backs it. To make the generators see
the new files, the 34 untracked ones were recorded with `git add -N` (intent to add)
while the pass ran; the whole work was committed afterwards as `6e129563`.

## For the next person

* Angela's rule for tests stands: headed browsers, a visible console, Shoter for every
  photograph. `scripts/terminater_visible_all.py` runs the three pages in one browser and
  waits at a console gate and a browser gate until the operator confirms what the
  photograph shows.
* The engine files must stay flat, stdlib-only siblings; do not turn them into a package
  and do not add a paste path.
* The hub is never created by a reaper; `live_pids()` must stay fail-open.
* Add a new action to **all four** places: the engine, `config.yaml`, the PFP action table
  in both Python and JavaScript, and `docs/terminater.md`.
