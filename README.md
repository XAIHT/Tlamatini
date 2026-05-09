# Tlamatini

![Project Logo](Tlamatini.jpg)

> A locally-deployed AI developer assistant: hybrid RAG (FAISS + BM25), Multi-Turn tool orchestration, ACPX delegation to external coding-agent CLIs (Claude Code, Cursor, Codex, Gemini, Qwen, …), and a visual workflow designer with **60 drag-and-drop agents**.
>
> Site: **<https://xaiht.org>** · One-minute teaser: **<https://youtu.be/a51miZ1JIe0>**
>
> Looking for the long-form, narrative version of this documentation? See [`BookOfTlamatini.md`](BookOfTlamatini.md).

---

## Table of Contents

- [1. Overview](#1-overview)
  - [1.1. What Tlamatini is](#11-what-tlamatini-is)
  - [1.2. What it gives you that a plain chatbox does not](#12-what-it-gives-you-that-a-plain-chatbox-does-not)
  - [1.3. Demo videos](#13-demo-videos)
- [2. Quickstart (source mode)](#2-quickstart-source-mode)
  - [2.1. Prerequisites](#21-prerequisites)
  - [2.2. Install Ollama (no admin rights)](#22-install-ollama-no-admin-rights)
  - [2.3. Pull the default models](#23-pull-the-default-models)
  - [2.4. Clone, install, migrate](#24-clone-install-migrate)
  - [2.5. Run the server (not-frozen)](#25-run-the-server-not-frozen)
  - [2.6. Log in for the first time](#26-log-in-for-the-first-time)
- [3. Using the Chat (`/agent/`)](#3-using-the-chat-agent)
  - [3.1. Chat layout in 30 seconds](#31-chat-layout-in-30-seconds)
  - [3.2. Setting code as context](#32-setting-code-as-context)
  - [3.3. Tutorial: a one-shot question (no toggles)](#33-tutorial-a-one-shot-question-no-toggles)
  - [3.4. Tutorial: the **internet** toggle](#34-tutorial-the-internet-toggle)
  - [3.5. Tutorial: the **Multi-Turn** toggle](#35-tutorial-the-multi-turn-toggle)
  - [3.6. Tutorial: the **Exec Report** toggle](#36-tutorial-the-exec-report-toggle)
  - [3.7. Tutorial: the **ACPX** toggle](#37-tutorial-the-acpx-toggle)
  - [3.8. From chat to flow: the **Create Flow** button](#38-from-chat-to-flow-the-create-flow-button)
  - [3.9. Why Chat-created flows are safer now](#39-why-chat-created-flows-are-safer-now)
- [4. Visual Workflow Designer (`/agentic_control_panel/`)](#4-visual-workflow-designer-agentic_control_panel)
  - [4.1. Canvas anatomy](#41-canvas-anatomy)
  - [4.2. Tutorial: your first flow (3 agents)](#42-tutorial-your-first-flow-3-agents)
  - [4.3. Saving and loading `.flw` files](#43-saving-and-loading-flw-files)
  - [4.4. Validate and Start now compile the live canvas](#44-validate-and-start-now-compile-the-live-canvas)
  - [4.5. Pause, Resume, Stop](#45-pause-resume-stop)
  - [4.6. FlowHypervisor (watchdog)](#46-flowhypervisor-watchdog)
  - [4.7. FlowCreator (let an LLM design the flow)](#47-flowcreator-let-an-llm-design-the-flow)
  - [4.8. Parametrizer (chain outputs into the next agent's config)](#48-parametrizer-chain-outputs-into-the-next-agents-config)
  - [4.9. Gatewayer (external triggers)](#49-gatewayer-external-triggers)
- [5. ACPX — External Coding-Agent CLIs as Tools](#5-acpx--external-coding-agent-clis-as-tools)
  - [5.1. What ACPX is](#51-what-acpx-is)
  - [5.2. Supported `agent_id`s and transports](#52-supported-agent_ids-and-transports)
  - [5.3. The 12 ACPX/Skill tools](#53-the-12-acpxskill-tools)
  - [5.4. Tutorial: spawn-and-go (single agent)](#54-tutorial-spawn-and-go-single-agent)
  - [5.5. Tutorial: multi-CLI relay with `acp_relay`](#55-tutorial-multi-cli-relay-with-acp_relay)
  - [5.6. API key setup (the easy button)](#56-api-key-setup-the-easy-button)
  - [5.7. ACPXer — the visual canvas counterpart](#57-acpxer--the-visual-canvas-counterpart)
- [6. Building a Frozen Distribution](#6-building-a-frozen-distribution)
  - [6.1. Three-step pipeline](#61-three-step-pipeline)
  - [6.2. Step 1 — `build.py`](#62-step-1--buildpy)
  - [6.3. Step 2 — `build_uninstaller.py`](#63-step-2--build_uninstallerpy)
  - [6.4. Step 3 — `build_installer.py`](#64-step-3--build_installerpy)
  - [6.5. What the installer does on the end-user box](#65-what-the-installer-does-on-the-end-user-box)
  - [6.6. Source mode vs Frozen mode: why flows still work](#66-source-mode-vs-frozen-mode-why-flows-still-work)
- [7. Configuration (`Tlamatini/agent/config.json`)](#7-configuration-tlamatiniagentconfigjson)
  - [7.1. LLM and unified-agent](#71-llm-and-unified-agent)
  - [7.2. RAG](#72-rag)
  - [7.3. ACPX](#73-acpx)
  - [7.4. MCP services and other knobs](#74-mcp-services-and-other-knobs)
- [8. Architecture at a Glance](#8-architecture-at-a-glance)
  - [8.1. Big picture](#81-big-picture)
  - [8.2. The five layers](#82-the-five-layers)
  - [8.3. Multi-Turn execution pipeline](#83-multi-turn-execution-pipeline)
  - [8.4. Agent contracts and the Flow Compiler](#84-agent-contracts-and-the-flow-compiler)
  - [8.5. Agent catalog (the 60 types, by family)](#85-agent-catalog-the-60-types-by-family)
- [9. Troubleshooting](#9-troubleshooting)
  - [9.1. Ollama / models](#91-ollama--models)
  - [9.2. RAG / context](#92-rag--context)
  - [9.3. Multi-Turn / planner](#93-multi-turn--planner)
  - [9.4. Chat-created flows and ACP validation](#94-chat-created-flows-and-acp-validation)
  - [9.5. ACPX / external CLIs](#95-acpx--external-clis)
  - [9.6. Frozen build / installer](#96-frozen-build--installer)
  - [9.7. Logs to consult first](#97-logs-to-consult-first)
- [10. Contributing & License](#10-contributing--license)
  - [10.1. Contributing](#101-contributing)
  - [10.2. Acknowledgments](#102-acknowledgments)
  - [10.3. License](#103-license)

---

## 1. Overview

### 1.1. What Tlamatini is

**Tlamatini** (Nahuatl for *"one who knows"*) is a Django/Channels app you run on your own machine. It packages a hybrid RAG pipeline, a Multi-Turn tool-calling LLM loop, an ACPX runtime that spawns external coding-agent CLIs as child processes, and a drag-and-drop workflow designer with 60 agent types — into one local install. Backends: **Ollama** (local), **Anthropic Claude** (cloud), **Qwen vision** (Ollama).

License: **GPL-3.0** · Repo: <https://github.com/XAIHT/Tlamatini.git> · Platform tested: Windows 11 (cross-platform for source mode).

### 1.2. What it gives you that a plain chatbox does not

1. **Real RAG over your code** — FAISS + BM25 hybrid retrieval, code-aware metadata extraction, Reciprocal Rank Fusion, context budgeting, OOM fallback.
2. **Multi-Turn mode** — the LLM becomes an *operator*: shell, Python, APIs, SQL, file ops, screenshots, keyboard/mouse automation, email, Telegram, WhatsApp — chained in one conversation.
3. **ACPX** — delegate sub-tasks to external CLIs (`claude`, `cursor-agent`, `codex`, `gemini`, `qwen-code`, plus 8 more) and relay output between them.
4. **Visual workflow designer** — design `.flw` flows once, run them unattended, schedule with Croner, watch them with FlowHypervisor.

Everything runs locally. The whole app packages into a one-click Windows `.exe` distribution (Part [§6](#6-building-a-frozen-distribution)).

### 1.3. Demo videos

- [First system-usage walkthrough](https://www.youtube.com/watch?v=CkvDPSd_c-g)
- [Loading a complete project and summarizing its source code](https://www.youtube.com/watch?v=Lrpbt_dPIXw)
- [Installing OpenCV end-to-end in Multi-Turn](https://www.youtube.com/watch?v=bBlqbZVK-Wk)
- [Uninstalling Poco — Exec Report and matching flow](https://www.youtube.com/watch?v=E5vi0q5FxXQ)
- [Designing a flow with FlowCreator's help](https://www.youtube.com/watch?v=Tgoa7Tmoo0o)

---

## 2. Quickstart (source mode)

This is the fastest way to be productive: clone, install, run. No installer, no admin, no frozen build. Five minutes.

### 2.1. Prerequisites

| Requirement | Recommended | Notes |
|---|---|---|
| Python | **3.12.10** | The only version Tlamatini is fully tested on. |
| OS | Windows 11 | Linux/macOS work for chat + designer; Mouser/Keyboarder are Windows-leaning. |
| RAM | 16 GB+ | 32 GB comfortable for bigger embedding models. |
| Disk | ~10 GB | Most is local LLM models. |
| LLM server | **Ollama** | Default. Cloud Claude/Gemini also supported. |

You do **not** need administrator rights for any of the steps below.

### 2.2. Install Ollama (no admin rights)

Open PowerShell **normally** (do not Run as Administrator), then:

```powershell
$env:OLLAMA_INSTALL_DIR = "$env:LOCALAPPDATA\Programs\Ollama"
irm https://ollama.com/install.ps1 | iex
```

Close the window, open a fresh PowerShell, and verify:

```powershell
ollama --version
ollama serve     # leave running in its own window if it's not already up
Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing
```

Tlamatini expects Ollama at `http://127.0.0.1:11434`.

### 2.3. Pull the default models

```powershell
ollama pull qwen3-embedding:8b
ollama pull glm-5:cloud
ollama pull qwen3.5:cloud
ollama pull gpt-oss:120b-cloud
ollama pull qwen3.5:397b-cloud
ollama pull llama3.2-vision:11b
```

| Tag | Used for |
|---|---|
| `qwen3-embedding:8b` | RAG embeddings |
| `glm-5:cloud` | Default chat + Multi-Turn unified-agent + MCP file-search |
| `qwen3.5:cloud` | Default vision (Image-Interpreter) |
| `gpt-oss:120b-cloud` | Several workflow-agent templates (Monitor-Log, Notifier, Prompter, Summarizer, …) |
| `qwen3.5:397b-cloud` | Default FlowCreator |
| `llama3.2-vision:11b` | Local vision fallback |

You can substitute any tag — just edit `Tlamatini/agent/config.json` (see [§7.1](#71-llm-and-unified-agent)) or the relevant agent's `config.yaml`.

### 2.4. Clone, install, migrate

```bash
git clone https://github.com/XAIHT/Tlamatini.git
cd Tlamatini

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt

python Tlamatini/manage.py migrate
python Tlamatini/manage.py createsuperuser
python Tlamatini/manage.py collectstatic --noinput
```

### 2.5. Run the server (not-frozen)

```bash
python Tlamatini/manage.py runserver --noreload
```

`--noreload` is important: Daphne's auto-reloader does not coexist well with the wrapped-runtime subprocess pool.

The console title becomes `Tlamatini` and stdout/stderr are tee'd into `Tlamatini/tlamatini.log` (truncated on every start). When debugging, `tlamatini.log` is the first thing to read.

### 2.6. Log in for the first time

Open `http://127.0.0.1:8000/` and log in with the superuser you just created. Then:

- `/agent/` — the chat (Part [§3](#3-using-the-chat-agent))
- `/agentic_control_panel/` — the visual designer (Part [§4](#4-visual-workflow-designer-agentic_control_panel))
- `/admin/` — Django admin (change passwords, manage users)

> If you used the **installer** (Part [§6](#6-building-a-frozen-distribution)) instead of cloning, the default credentials are `user` / `changeme`. Change them at first login via `/admin/`.

---

## 3. Using the Chat (`/agent/`)

### 3.1. Chat layout in 30 seconds

```
┌───────────────────────────────────────────────────────────────────────┐
│ Tlamatini  [Context ▼] [Open in… ▼] [MCPs ▼] [Tools ▼] [Agents ▼]    │ ← top nav
├───────────────────────────────────────────────────────────────────────┤
│  Multi-Turn ☐   Exec Report ☐   ACPX ☐   internet ☐    Clear ⌫       │ ← four toggles
├───────────────────────────────────────────────────────────────────────┤
│  ┌──── chat ────────────────┐   ┌──── code canvas ────────────────┐  │
│  │  conversation history    │   │  syntax-highlighted, with copy  │  │
│  └──────────────────────────┘   └─────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────────────┤
│  Type your prompt here…                                      [Send]   │
└───────────────────────────────────────────────────────────────────────┘
```

The **four toolbar toggles** are independent. Tick whatever combination fits the task — each one is its own tutorial section below.

### 3.2. Setting code as context

Click **Context** in the top nav:

| Menu entry | What it does |
|---|---|
| **Set directory as context** | Loads a folder. Tlamatini reads every text file, splits, embeds, builds FAISS+BM25, grounds answers in your code. |
| **Set file as context** | Single-file scope. |
| **Set canvas as context** | Use the code currently shown in the canvas (handy for iterative editing). |
| **Clear context** | Drops the loaded context. |

A green banner at the top shows the current context path. If embedding runs out of memory, Tlamatini packs the source files as a fallback context — retrieval quality drops, access to your code does not.

### 3.3. Tutorial: a one-shot question (no toggles)

Leave every checkbox unticked. Type:

> "Write a Python function that validates an email address with a regex. Just the function."

The bot answers in one shot. Code lands in the right-hand canvas with copy/save buttons. This is the legacy chat path — fast, no tools, no internet.

### 3.4. Tutorial: the **internet** toggle

Tick **internet** when the question genuinely needs fresh web data:

> "What is the latest stable version of FastAPI right now?"

Tlamatini classifies the prompt with a small LLM call ("does this need the web?"), then DuckDuckGo-searches, summarizes the top results, and inlines the summary into the LLM's context. Leave it **unticked** for everything else (the round-trip adds latency).

### 3.5. Tutorial: the **Multi-Turn** toggle

This is the big one. Multi-Turn turns Tlamatini from *answerer* into **operator**:

- The planner picks the relevant subset of 36+ wrapped chat-agent tools, the 12 ACPX tools, and the core Python tools (default cap: 20 tools per request).
- The unified-agent loop runs **up to 100 iterations** — call tool, see result, decide next, chain.
- Wrapped sub-agents run in headless background runtimes (no console pop-ups).

**Try this:** tick **Multi-Turn**, send

> "Take a screenshot of my desktop and save it to `C:\Tlamatini-test\shot.png`."

Watch the chat. The LLM picks `chat_agent_shoter`, calls it with the right args, reads the JSON result, and replies "Done — saved to C:\Tlamatini-test\shot.png." Open the file. The screenshot is there.

| Symptom | Fix |
|---|---|
| LLM says "Tool X is not available" | The planner did not bind it. Check `[Planner._select]` console lines; add matching keywords to your prompt or raise `max_selected_tools`. |
| Same tool fired twice with identical args | Suppressed by the dedup guard — the second call returns "skipped — duplicate". |
| 100 iterations exhausted | You probably hit a polling loop. Use `chat_agent_sleeper` instead of busy-polling. |

Multi-Turn stacks with Set-Context: the LLM reasons over your code *and* runs tools on the result.

### 3.6. Tutorial: the **Exec Report** toggle

Below the prose answer, Tlamatini appends **per-agent execution tables** — one HTML table per *kind* of state-changing agent that fired. Each row = one real tool call + ✓/✗.

Tick **Multi-Turn + Exec Report** and send:

> "Create `C:\test\hello.txt` with `Hi from Tlamatini`, then read it back and tell me its size."

After the prose, you see:

```
─── List of File Creator Operations ───
 #  │ Command                                        │ ✓/✗
 1  │ filepath='C:\test\hello.txt' content='Hi …'    │  ✓
─── List of Executer Operations ───
 #  │ Command                                        │ ✓/✗
 1  │ type C:\test\hello.txt                         │  ✓
```

What gets a table: state-changing tools only (`execute_command`, `execute_file`, `unzip_file`, `decompile_java`, every `chat_agent_*` that touches the system, all five `acp_*` lifecycle tools — merged into one "List of ACPx Operations" — and `invoke_skill`). Read-only tools (Crawler, Googler, Prompter, Summarizer, File-Interpreter/Extractor, Image-Interpreter, Shoter, Sleeper, monitor_*, run_*, `window_present`) are intentionally absent. **Tables persist into chat history** — reload the page and they are still there.

### 3.7. Tutorial: the **ACPX** toggle

ACPX lets the chat **delegate** to external coding-agent CLIs running on your box. Picture it:

```
You ─► Tlamatini chat ─► acp_doctor → acp_spawn(claude) → acp_send_and_wait
                                  │
                                  ▼ subprocess.Popen
                                claude CLI / gemini / cursor / codex / qwen / …
```

When **ACPX is ticked**, the planner sees the 12 ACPX/Skill tools. When **unticked**, those tools are filtered out — the chat behaves like legacy Multi-Turn. (Implemented in `agent/acpx/__init__.py::filter_acpx_tools()`.)

**Prereq:** at least one external CLI on `PATH`. The simplest:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

Then drop your key in `Tlamatini/agent/config.json` (or use the [`setup-new-acpx-key` skill](#56-api-key-setup-the-easy-button) — much easier).

Tick **Multi-Turn + ACPX + Exec Report** and send:

> "Use ACPX to spawn the claude CLI in `C:/Development/Tlamatini`, ask it to summarize CLAUDE.md in 5 bullet points, harvest the answer, and kill the session."

You see: `acp_doctor` (always first) → `acp_spawn(agent_id="claude", task=…)` → `acp_send_and_wait` → `acp_kill`. The 5 bullets land in the prose, and the Exec Report shows a "List of ACPx Operations" table with all four rows.

ACPX deep dive in Part [§5](#5-acpx--external-coding-agent-clis-as-tools).

### 3.8. From chat to flow: the **Create Flow** button

When a Multi-Turn run **succeeds** and used at least one state-changing tool, Tlamatini renders a **Create Flow** button on the message header. Click → download a `.flw` JSON file mirroring the exact tool sequence, laid out left-to-right, ready to load in the visual designer:

```
Starter ─► Crawler ─► File Creator ─► Ender
```

You can re-open it in `/agentic_control_panel/` and run it as an unattended workflow. The LLM is no longer in the loop.

The button gates on four conditions: Multi-Turn was on, ≥1 mappable tool succeeded, an LLM-based classifier marked the answer SUCCESS (fails open on internal error), and the user is logged in.

### 3.9. Why Chat-created flows are safer now

Older Chat-created `.flw` files were generated almost entirely in the browser. That worked for simple chains, but it meant the browser had to remember many backend facts:

- what each agent is called on disk;
- which config field means "my input";
- which config field means "my output";
- which agents are special, like Ender or Parametrizer;
- which values are safe to save into a portable `.flw` file.

That is a lot of responsibility for a button.

Now the browser still builds the first draft, but the backend normalizes it through the **Agent Contract Registry** before the file is downloaded. In plain English: Tlamatini checks the flow against the same agent rules that ACP uses to run it.

What this means for you:

1. Repeated tools stay repeated. If Multi-Turn ran Executer five times, the flow contains five Executer nodes, not one overwritten node.
2. Agent names are normalized. Names like `Kyber-KeyGen`, `kyber_keygen`, and `Kyber Keygen` are resolved to the right template.
3. Secrets are protected where the contract knows about them. Remote chat super-agents such as TeleTlamatini and WhatsTlamatini have credential-like fields redacted on export.
4. The `.flw` file stays portable. It does not store `C:/Development/...` or the installed app path beside `Tlamatini.exe`.

If backend normalization is temporarily unavailable, the old browser generator remains as a fallback so the button does not become useless.

---

## 4. Visual Workflow Designer (`/agentic_control_panel/`)

The chat is great for one-off tasks. The designer is for jobs you want **scheduled**, **unattended**, or **identically reproducible**.

### 4.1. Canvas anatomy

```
┌────────────────────────────────────────────────────────────────────────┐
│ ▶ Start  ⏸ Pause  ⏹ Stop  ⚠ Hypervisor  💾 Save  📂 Load  ✓ Validate │
├──────────────────┬─────────────────────────────────────────────────────┤
│ Sidebar          │                                                     │
│ ─ Control        │                                                     │
│   Starter, Ender │            CANVAS (#canvas-content)                 │
│ ─ Routing        │       (draggable agents, typed connections,         │
│   Forker, Asker  │        green-running / red-down / yellow-paused     │
│ ─ Logic Gates    │        LEDs)                                        │
│   AND OR Barrier │                                                     │
│ ─ Action / etc.  │                                                     │
└──────────────────┴─────────────────────────────────────────────────────┘
```

- The canvas **scrolls**: viewport is `#submonitor-container`, content layer is `#canvas-content`. New canvas-level features should be children of `#canvas-content`.
- **Connections are typed**: green = "start the target after this finishes" (`target_agents`), blue = "monitor this source's log" (`source_agents`).
- **Double-click** an agent to edit its config. **Right-click** for description / log / explore-dir / open-cmd / restart.

### 4.2. Tutorial: your first flow (3 agents)

Goal: run a shell command, take a screenshot, end.

1. Drag **Starter** onto the canvas (top-left).
2. Drag **Executer** to its right.
3. Drag **Shoter** further right.
4. Drag **Ender** at the far right.
5. Connect: Starter → Executer → Shoter → Ender (drag from the right edge of one to the left edge of the next).
6. Double-click **Executer**, set `command` to `dir C:\` (or `ls /tmp`).
7. Double-click **Shoter**, set `output_dir` to a writable folder.
8. Leave **Ender** wiring to Tlamatini. Validate/Start will calculate Ender's `target_agents` kill list from the arrows.
9. Click **✓ Validate** — Tlamatini compiles the visible canvas, then runs structural checks (no orphans, no self-connections, terminal agents reachable).
10. Click **▶ Start**. LEDs go green, then gray. Open `output_dir` — there's a screenshot.

### 4.3. Saving and loading `.flw` files

**💾 Save** — pick a name. You get a JSON file with positions, configs, and connections. Distribute to colleagues; they **📂 Load** the same file and run the same flow. `.flw` is also what the chat's **Create Flow** button emits.

A `.flw` file is meant to describe the **idea of the flow**, not the exact machine it was created on. A good `.flw` says:

- "There is a Starter here."
- "There is an Executer there."
- "Starter connects to Executer."
- "Executer uses this script."

It should **not** say:

- "This flow only works from `C:/Development/Tlamatini/...`."
- "This flow only works from the install folder on Angel's PC."
- "This Parametrizer mapping exists somewhere in a temporary pool directory, good luck."

Saved flows now carry a small `schemaVersion` plus an `artifacts` section. The most important artifact today is Parametrizer mappings. When you save a flow with a Parametrizer, Tlamatini keeps the mapping in the `.flw`. When you load the flow later, Tlamatini recreates `interconnection-scheme.csv` for that Parametrizer in the current session pool.

For a beginner, the practical rule is simple: **if you configured Parametrizer with the mapping dialog, Save/Load should remember that mapping.**

### 4.4. Validate and Start now compile the live canvas

This is the most important reliability change in the visual designer.

Before, Validate mostly read whatever agent configs already existed in the pool directory. That could become stale:

1. You drag nodes around.
2. You load a `.flw`.
3. You edit a config.
4. You reconnect an edge.
5. The pool directory still contains an older `config.yaml`.
6. Validate or Start reads that older file and acts confused.

Now ACP takes a fresh **snapshot of the canvas** before validation and start. The snapshot includes:

- every visible node;
- each node's position;
- every connection;
- input and output slot numbers;
- current in-browser config;
- Parametrizer mappings.

The backend then compiles that snapshot into real pool `config.yaml` files using the Agent Contract Registry. In beginner terms: **the picture on the screen becomes the source of truth.**

What happens when you click **✓ Validate**:

1. Browser captures the live canvas.
2. Backend compiles it in dry-run mode.
3. Frontend validates the compiled configs.
4. Nothing is written to disk just for validation.

What happens when you click **▶ Start**:

1. Browser captures the live canvas.
2. Backend compiles it in write mode.
3. Pool folders/configs are updated.
4. Logs are cleared.
5. Starter agents launch.

This removes a whole class of "I swear I connected it correctly, why is it running the old thing?" problems.

### 4.5. Pause, Resume, Stop

| Button | What happens |
|---|---|
| **⏸ Pause** | Saves running agents into `paused_agents.reanim`, kills them, leaves logs and `reanim*` state files intact. LEDs go yellow. |
| **▶ Resume** (after pause) | Reanimates each saved agent with `AGENT_REANIMATED=1`. Each agent reads its `reanim*` files and continues from where it stopped. |
| **⏹ Stop** | Hard stop. Ender runs termination logic; reanimation files are cleared. |

This is why long-running workflows (Crawler scraping 10k URLs, Parametrizer iterating segments) survive pauses.

### 4.6. FlowHypervisor (watchdog)

Click **⚠ Hypervisor** — a system FlowHypervisor agent starts watching every running agent. It is an LLM that reads each agent's log, builds an NxN connection matrix from the canvas wiring, and emits exactly **`OK`** or **`ATTENTION NEEDED { explanation }`**. If it raises, the browser pops an alert. Add custom rules to `user_instructions` in its config.

### 4.7. FlowCreator (let an LLM design the flow)

Drag **FlowCreator**, double-click, and type a natural-language objective:

> "Every hour, crawl our status page; if it shows ERROR, email the on-call engineer."

Click **Generate**. FlowCreator reads `agentic_skill.md` (its design playbook), produces a JSON flow description, and renders agents + connections onto the canvas. Tweak and run.

### 4.8. Parametrizer (chain outputs into the next agent's config)

Tlamatini agents communicate through **log files** and **`config.yaml`**. Parametrizer is the bridge: it reads structured segments from a source agent's log, injects mapped values into a target agent's `config.yaml`, runs the target, restores the config, advances the cursor, repeats.

The unified output format every Parametrizer-friendly agent emits:

```
INI_SECTION_<AGENT_TYPE><<<
key1: value1
key2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

17 source agents support this format: Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen/Cipher/DeCipher, Gatewayer, Gateway-Relayer, Googler, **ACPXer**.

Canonical example:

```
Apirer ─► Parametrizer ─► Kyber-Cipher
```

Apirer hits 3 endpoints → 3 `INI_SECTION_APIRER<<<` blocks → Parametrizer maps `response_body → buffer` → Kyber-Cipher runs 3 times, encrypting each body. No manual config editing. Pause-safe. Single-lane queue.

The mapping dialog is now part of normal flow persistence:

1. Connect exactly one source into Parametrizer.
2. Connect Parametrizer to exactly one target.
3. Double-click Parametrizer.
4. Click a source field on the left.
5. Click a target config field or target marker on the right.
6. Save mappings.
7. Save the `.flw`.

When the `.flw` is loaded later, Tlamatini restores the mappings and writes the Parametrizer's `interconnection-scheme.csv` again. You do not need to remember which pool directory had the CSV.

One limitation is intentional: one Parametrizer is a **single-lane queue** from one source to one target. If one API response must feed Emailer and File-Creator, use two Parametrizers.

### 4.9. Gatewayer (external triggers)

Two trigger modes:

| Mode | When |
|---|---|
| **HTTP webhook** | CI server, SaaS callback, cron, curl, internal portal — anything that POSTs. Auth: `bearer` / `hmac` / `none`. Validates → dedups → queues → starts `target_agents`. |
| **Folder-drop watcher** | Industrial / IoT — sensor writes JSON to a shared folder. Gatewayer polls, archives, fires. |

Pending events survive crashes via `reanim_queue.json`. To accept GitHub-style webhooks (which sign only the body), put the bundled **Gateway-Relayer** in front.

---

## 5. ACPX — External Coding-Agent CLIs as Tools

### 5.1. What ACPX is

**ACPX = Agent Communication Protocol eXtension.** It spawns external coding-agent CLIs as out-of-process child processes, talks to them over stdin/stdout, persists the conversation as NDJSON transcripts, and brokers them to the chat LLM as 12 native tools. It is a Python port of OpenClaw's ACPX plugin — `agent_id` mapping, `permissionMode` vocabulary, and `SKILL.md` frontmatter all match verbatim.

### 5.2. Supported `agent_id`s and transports

Defined in `agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS`. User overrides go in `config.json` under `acpx.agents.<id>`.

| `agent_id` | Default command | Transport | Prompt form |
|---|---|---|---|
| `claude` | `claude` | `oneshot-prompt` | `claude -p "<task>"` |
| `codex` | `codex` | `oneshot-prompt` | `codex exec "<task>"` |
| `cursor` | `cursor-agent` | `oneshot-prompt` | `cursor-agent -p "<task>"` |
| `gemini` | `gemini` | `oneshot-prompt` | `gemini -p "<task>"` |
| `qwen` | `qwen-code` | `oneshot-prompt` | `qwen-code -p "<task>"` |
| `tlamatini` | `python -m agent.acpx.self_acp_server` | `json-acp` | stdin envelope |
| `kiro / kimi / iflow / kilocode / opencode / pi / droid / copilot` | (own command) | `tui-repl` | stdin |

**Transport modes:**

- **`oneshot-prompt`** — fresh process per turn; prompt is a CLI arg; stdin closes; stdout captured to EOF. The **only** transport that reliably captures TUI agents on Windows (TUI CLIs detect a piped stdout and refuse to flush in long-lived mode).
- **`json-acp`** — child speaks one JSON envelope per turn, ends with `{"done": true}`.
- **`tui-repl`** — long-lived REPL; transport-aware idle rule fires after `startup_grace + idle_seconds` even with zero events (a silent TUI is, by definition, finished).

### 5.3. The 12 ACPX/Skill tools

All return JSON envelopes. Failures: `{"ok": false, "reason": "...", "code": "..."}`.

| Tool | What it does |
|---|---|
| `acp_doctor()` | Health probe + per-agent enumeration with `resolvable` and `cli_version`. **Always call first.** |
| `list_acp_agents()` | Cheap enumeration without the version probe. |
| `acp_spawn(agent_id, task, …)` | Spawn child. Returns `session_id`, `transport`, `transcript_path`, `events`. TUI agents return sub-second. |
| `acp_send(session_id, text, …)` | Send a follow-up turn. |
| `acp_send_and_wait(session_id, text, until_idle_seconds=10, max_wait_seconds=180)` | Send and **block until child settles**. Prefer this for "wait for the full answer". |
| `acp_kill(session_id)` | Terminate. Returns `transcript_path` so Exec Report can cite it. |
| `acp_transcript(session_id, max_chars, direction)` | Read the on-disk NDJSON transcript. |
| `acp_session_status(session_id)` | `{alive, pid, transcript_size, last_event_at, closed}`. |
| `acp_list_sessions()` | Enumerate live sessions. |
| `acp_relay(session_id_src, session_id_dst, …)` | **Single-call hand-off** — replaces transcript→string→send. |
| `invoke_skill(skill_name, args_json)` | Run a `SKILL.md` package inside `SkillHarness`. |
| `list_skills(filter_keywords)` | List registered skills. |

21 seed skills live under `agent/skills_pkg/` (acp-router, summarize, setup-new-acpx-key, skill-creator, 8× tlamatini-* maintenance helpers, plus OpenClaw-format ports for github / gmail / slack / jira / notion / todoist / trello / weather).

### 5.4. Tutorial: spawn-and-go (single agent)

Tick **Multi-Turn + ACPX + Exec Report** and send:

> "Spawn claude in `C:/Development/Tlamatini`, ask it to list the top-level files, harvest the answer, and kill the session."

Expected tool sequence:

```
acp_doctor
  → acp_spawn(agent_id="claude", task="list top-level files")
    → acp_send_and_wait(session_id, "...")
      → acp_kill(session_id)
```

### 5.5. Tutorial: multi-CLI relay with `acp_relay`

> "Spawn claude in this dir, ask it to draft a refactor of `worker.py`. Spawn gemini, relay claude's answer to it, ask gemini to critique. Kill both."

Expected sequence:

```
acp_doctor
  → acp_spawn(claude, draft_task)
    → acp_send_and_wait(session_a, …)
      → acp_spawn(gemini, critique_template)
        → acp_relay(session_a, session_b)     # ONE call — transform=last_assistant_text
          → acp_kill(session_a)
            → acp_kill(session_b)
```

Without `acp_relay`, that hand-off is three calls (`acp_transcript` → string-manipulate → `acp_send`). Always prefer the dedicated tool.

### 5.6. API key setup (the easy button)

Two layers exist in `config.json`:

```json
{
  "ANTHROPIC_API_KEY": "sk-ant-...",     // Layer 1: Tlamatini's own cloud calls
  "GEMINI_API_KEY": "AIza...",
  "acpx": {
    "agents": {
      "claude": { "env": { "ANTHROPIC_API_KEY": "sk-ant-..." } },   // Layer 2: spawned child env
      "gemini": { "env": { "GEMINI_API_KEY": "AIza...", "GOOGLE_API_KEY": "AIza..." } },
      "codex":  { "env": { "OPENAI_API_KEY":  "sk-..." } },
      "qwen":   { "env": { "DASHSCOPE_API_KEY": "sk-..." } }
    }
  }
}
```

Merge order at spawn: `{**os.environ, **spec.env}` — explicit per-agent `env` wins over an exported shell variable.

**Easier path** — invoke the `setup-new-acpx-key` skill from chat (Multi-Turn + ACPX ticked):

> "Use `invoke_skill` with `setup-new-acpx-key` to register my Anthropic key for the `claude` agent_id." (paste the key)

The skill writes `data.keys`, patches both `config.json` layers, optionally extends `regen_secrets.py`, and verifies via `acp_doctor`.

> **Security:** `config.json` is git-tracked. Use `python regen_secrets.py --mode push-able` to swap real keys for placeholders before commit; `--mode keyed` restores from `data.keys` (gitignored). Never commit `data.keys`.

### 5.7. ACPXer — the visual canvas counterpart

**ACPXer** is the canvas-facing version of the 12 LLM-facing tools. One ACPXer node = one full ACPX session lifecycle. It is **self-contained** — does NOT import `agent.acpx` — because pool subprocesses can't import `agent.*`. Mirrors the runtime's transport-aware drain inline (~120 lines), writes byte-identical NDJSON transcripts, and emits Parametrizer-compatible `INI_SECTION_ACPXER<<<` blocks.

Canonical visual relay flow:

```
Starter → ACPXer(claude) → Parametrizer → ACPXer(gemini) → Parametrizer → ACPXer(cursor) → File-Creator → Ender
```

Three different LLMs argue back and forth, fully visual, fully unattended.

---

## 6. Building a Frozen Distribution

For shipping a one-click Windows installer to end users.

### 6.1. Three-step pipeline

```
build.py  ──►  build_uninstaller.py  ──►  build_installer.py
   │                   │                         │
   ▼                   ▼                         ▼
pkg.zip          Uninstaller.exe        dist/Tlamatini_Release/
```

### 6.2. Step 1 — `build.py`

```bash
python build.py
```

Installs deps, runs `collectstatic`, executes PyInstaller, copies required payloads (including `README.md` and bundled `jd-cli/`), runs migrations, creates the default user (`user`/`changeme`), renames the exe to `Tlamatini.exe`, copies all 60 agent templates, bundles support scripts (`register_flw.ps1`, `CreateShortcut.ps1`, `Tlamatini.ps1`, `Tlamatini.ico`), and zips it all into **`pkg.zip`**.

`build.py` is strict: missing `README.md`, missing `jd-cli/`, or missing `jd-cli.bat` causes a non-zero exit.

### 6.3. Step 2 — `build_uninstaller.py`

```bash
python build_uninstaller.py
```

Builds `uninstall.py` into a single `--onefile` Tkinter exe. Output: `Uninstaller.exe` at the project root.

### 6.4. Step 3 — `build_installer.py`

```bash
python build_installer.py
```

Requires `pkg.zip` and `Uninstaller.exe`. Builds `install.py` with `--onedir --windowed` and a splash screen, copies `pkg.zip` and `Uninstaller.exe` into `dist/Installer/`, and assembles `dist/Tlamatini_Release/` with SHA-256 verification.

The final distributable is `dist/Tlamatini_Release/` — zip the folder, share it.

### 6.5. What the installer does on the end-user box

1. Tkinter GUI to choose installation directory (no admin needed).
2. Extracts `pkg.zip` into `<install_path>/Tlamatini/`.
3. Locks agent venv permissions.
4. Writes `config.json`.
5. Copies `Uninstaller.exe`.
6. Creates desktop and Start Menu shortcuts (`Tlamatini.lnk` — falls back to user-scoped paths under restrictive Group Policies).
7. Registers `.flw` to open with Tlamatini.
8. Cleans the PyInstaller bundle path from helper subprocess environments.

Frozen mode resolves `config.json` from the executable directory (or `CONFIG_PATH` env var). Template-agent discovery uses `<install_dir>/agents` in frozen mode and `Tlamatini/agent/agents/` in source mode. `_resolve_python_executable()` tries `PYTHON_HOME` → bundled `python.exe` → PATH.

### 6.6. Source mode vs Frozen mode: why flows still work

Tlamatini has two operational modes:

| Mode | What it means | Where agent templates live |
|---|---|---|
| **Source / Not-Frozen** | You run `python Tlamatini/manage.py runserver --noreload` from a cloned repo. | `Tlamatini/agent/agents/` |
| **Frozen / Installed** | You run the packaged `Tlamatini.exe` from the installer. | `<install_dir>/agents/` |

The new Flow Compiler was built to respect both modes. It does **not** assume your repo is at `C:/Development/Tlamatini`, and it does **not** assume the installed app lives in a specific Program Files folder.

The compiler asks Tlamatini at runtime:

1. "Am I frozen?"
2. "Where are the agent templates?"
3. "Where is this user's session pool?"
4. "Which agent contract applies to this node?"

Then it writes only into the current pool:

```text
agents/pools/<session_id>/<agent_name_n>/config.yaml
```

That path exists in both modes. In source mode it is under the repo's `Tlamatini/agent/agents/pools/`. In frozen mode it is under the installed app's `agents/pools/`.

For users, the takeaway is simpler: **a `.flw` saved in source mode should load in an installed build, and a `.flw` saved in an installed build should load back in source mode.**

---

## 7. Configuration (`Tlamatini/agent/config.json`)

| Mode | Resolution order |
|---|---|
| Source | `Tlamatini/agent/config.json` |
| Frozen | `<install-dir>/config.json` next to the executable |
| Both | `CONFIG_PATH` env var wins over both |

### 7.1. LLM and unified-agent

```json
{
  "embeding-model": "qwen3-embedding:8b",
  "chained-model": "glm-5:cloud",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_token": "",
  "ANTHROPIC_API_KEY": "<ANTHROPIC_API_KEY goes here>",
  "GEMINI_API_KEY": "<GEMINI_API_KEY goes here>",
  "enable_unified_agent": true,
  "unified_agent_model": "glm-5:cloud",
  "unified_agent_base_url": "http://127.0.0.1:11434",
  "unified_agent_temperature": 0.0,
  "unified_agent_max_iterations": 100,
  "chat_agent_limit_runs": 100
}
```

`unified_agent_max_iterations` caps the Multi-Turn tool loop (default 100). `enable_unified_agent` is the master switch for tool-calling.

### 7.2. RAG

Key knobs: `chunk_size` (3000), `chunk_overlap` (800), `k_vector` / `k_bm25` (100 each), `k_fused` (150), `enable_bm25`, `rrf_k` (60), `max_doc_chars` (150000), `max_context_chars` (250000), and a `context_budget_allocation` map (`high_relevance: 0.60, architecture: 0.20, related: 0.15, documentation: 0.05`). See `BookOfTlamatini.md` Part VII for the full schema.

### 7.3. ACPX

```json
{
  "acpx": {
    "cwd": "C:/Development/Tlamatini",
    "stateDir": "C:/Users/<you>/.tlamatini/acpx-state",
    "probeAgent": "gemini",
    "permissionMode": "approve-reads",
    "nonInteractivePermissions": "deny",
    "timeoutSeconds": 180,
    "agents": {
      "claude": { "command": "C:/Users/<you>/AppData/Roaming/npm/claude.cmd",
                  "env": { "ANTHROPIC_API_KEY": "sk-ant-..." } }
    }
  }
}
```

`permissionMode` ∈ `approve-reads` (default) / `approve-all` (DANGEROUS) / `deny-all`. The whole `acpx` block is optional; on first boot of an upgrade build, `boot_acpx()` appends the documented default block atomically.

### 7.4. MCP services and other knobs

- `mcp_system_server_port` (8765), `mcp_files_search_server_port` (50051) — MCP daemons.
- `internet_classifier_model`, `web_summarizer_model`, `web_context_max_chars` — internet toggle.
- `image_interpreter_model`, `image_interpreter_base_url` — vision.
- `history_summary_*`, `keep_last_turns` — chat-history compression.

---

## 8. Architecture at a Glance

### 8.1. Big picture

```
Browser (Chat / ACP Designer)
    │ WebSocket
    ▼
Django Channels (Daphne ASGI) → AgentConsumer
    │
    ├── RAG Pipeline (FAISS + BM25, RRF, context budgeting, OOM fallback)
    ├── Unified Agent (Multi-Turn loop, planner, wrapped runtimes)
    └── MCP Services (System-Metrics WS, Files-Search gRPC)
    │
    ▼
LLM Backends: Ollama | Claude API | Qwen vision     +     ACPX Runtime → external CLIs
```

### 8.2. The five layers

| Layer | Responsibility | Where |
|---|---|---|
| 1. Persisted toggles | DB rows for `Mcp` / `Tool` / `Agent` (UI enable/disable). | `agent/models.py` |
| 2. Runtime MCP services | System-Metrics (WebSocket) + Files-Search (gRPC) daemons. | `agent/mcp_*` |
| 3. Context fetcher chains | LCEL sidecars that inject system / files context. | `agent/chain_*_lcel.py` |
| 4. Main answer chains | Basic / History-aware / Unified. `factory.py` monkey-patches `invoke()`. | `agent/rag/chains/` |
| 5. Unified-agent tools | Synchronous `@tool` functions. Active only in Multi-Turn. | `agent/tools.py` |

### 8.3. Multi-Turn execution pipeline

```
Frontend (toggles) → WebSocket → AgentConsumer → ask_rag() (skips prompt-shape validator)
  → UnifiedAgentChain.invoke() → filter_acpx_tools(tools, acpx_enabled)
    → planner picks ≤20 tools (capability scoring + history-aware boost)
      → MultiTurnToolAgentExecutor: 1..100 iterations of (LLM call → tool calls → ToolMessage)
        → Exec Report HTML appended (if exec_report_enabled, BEFORE save_message)
          → broadcast → frontend renders, shows Create Flow if all 4 gates pass
```

### 8.4. Agent contracts and the Flow Compiler

Tlamatini has two ways to create flows:

1. The chat can infer a flow from Multi-Turn tool calls.
2. The ACP canvas can build a flow by dragging agents and drawing arrows.

Those two paths now meet at the same backend contract layer. This is important because flow files are not just pictures. A flow must eventually become a set of real agent folders, and every folder needs a correct `config.yaml`.

The contract layer is intentionally small:

| File | What it does |
|---|---|
| `agent/services/agent_paths.py` | Finds the correct `agents/` and `agents/pools/` folders in both source mode and frozen mode. It also normalizes names like `TeleTlamatini`, `tele-tlamatini`, and `teletlamatini` into the same agent type. |
| `agent/services/agent_contracts.py` | Describes what each agent needs: which config fields hold incoming agents, which fields hold outgoing agents, which agents are singletons, which agents are long-running, which agents should be hidden from validation, which Parametrizer fields can be mapped, and which secrets must be redacted before export. |
| `agent/services/flow_spec.py` | Converts old and new `.flw` shapes into one clean `FlowSpec`. It accepts legacy `sourceIndex` / `targetIndex` links and newer stable `sourceId` / `targetId` links. |
| `agent/services/flow_compiler.py` | Converts a `FlowSpec` into the actual pool configs. In dry-run mode it returns the configs for validation. In write mode it updates the current session pool before Start runs. |

For beginners, the rule is: **the canvas or chat creates a flow idea, then the Flow Compiler turns that idea into executable agent folders.**

The compiler does a few quiet but important safety jobs:

- It starts from each agent template's `config.yaml`, then merges only the node's custom settings.
- It clears and rebuilds managed connection fields, so stale arrows from an old pool do not survive by accident.
- It understands special agent wiring such as `AND`, `OR`, `Asker`, `Forker`, `Counter`, `Ender`, `Stopper`, and `Cleaner`.
- It writes `interconnection-scheme.csv` for Parametrizer nodes when mappings are saved in the `.flw`.
- It keeps FlowCreator and FlowHypervisor out of runtime validation because they are helper/control agents, not normal flow workers.
- It redacts known secrets for remote chat ingress agents such as **TeleTlamatini** and **WhatsTlamatini** when chat-created flows are exported.

This is the Pareto improvement: a small shared backend layer makes both major features safer. Chat-created flows and ACP-created flows now speak the same format before they touch the runtime.

### 8.5. Agent catalog (the 60 types, by family)

| Family | Members |
|---|---|
| **Control** | Starter, Ender, Stopper, Cleaner, Sleeper, Croner |
| **Routing** | Raiser, Forker, Asker, Counter |
| **Logic gates** | OR, AND, Barrier |
| **Action** | Executer, Pythonxer, Prompter, Summarizer, Crawler, Googler, Apirer, Gitter, Ssher, Scper, Dockerer, Kuberneter, Pser, Jenkinser, Sqler, Mongoxer, Mover, Deleter, Shoter, Mouser, Keyboarder, File-Creator, File-Interpreter, File-Extractor, Image-Interpreter, J-Decompiler, Telegramer, **TeleTlamatini**, **WhatsTlamatini**, **ACPXer** |
| **Cryptography** | Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher (CRYSTALS-Kyber post-quantum) |
| **Utility** | Parametrizer, FlowBacker, Gatewayer, Gateway-Relayer, Node-Manager |
| **Terminal / monitoring** | Monitor-Log, Monitor-Netstat, Emailer, RecMailer, Notifier, Whatsapper, TelegramRX, FlowHypervisor |
| **AI / design** | FlowCreator |

Per-agent details (config knobs, lifecycle, naming convention, log markers): see `BookOfTlamatini.md` Part IV — *The Tlamatini Bestiary*. To add a new agent, follow `Tlamatini/.agents/workflows/create_new_agent.md` (8-step checklist).

---

## 9. Troubleshooting

### 9.1. Ollama / models

- "connection refused" → `ollama serve` in a dedicated terminal. Check `ollama_base_url`.
- Model not found → `ollama list` to see what's pulled. Pull the missing tag.
- Remote Ollama → set `ollama_token` for bearer auth.

### 9.2. RAG / context

- Set-Context shows no green banner → check file permissions, ensure files are text not binary.
- "Out of memory" during embedding → fallback mode kicks in; retrieval quality drops, files still accessible. Switch to a smaller embedding model.
- Hit `max_doc_chars` → bump it.

### 9.3. Multi-Turn / planner

- Did you tick **Multi-Turn**? Is `enable_unified_agent: true`?
- "Tool X is not available" → the planner did not bind X. Check `[Planner._select]` console lines, add matching keywords to your prompt, or raise `max_selected_tools`.
- 100 iterations exhausted → likely a busy-poll loop. Use `chat_agent_sleeper` / `chat_agent_run_wait` instead.

### 9.4. Chat-created flows and ACP validation

- **Create Flow downloads a `.flw`, but it looks simpler than the chat transcript.** That is normal. The file stores the flow structure, node config, connections, and artifacts. It does not store the entire conversation.
- **Create Flow fails from the chat.** The browser first asks `/agent/flow_from_tool_calls/` to normalize the draft. If that endpoint fails, the frontend falls back to the older browser-only export so you do not lose the flow draft.
- **A TeleTlamatini or WhatsTlamatini flow is missing passwords or tokens after export.** That is intentional. Known secret fields are redacted when the chat exports a flow. Re-enter secrets in the agent config before running the flow.
- **Validate shows stale connections.** Validate now asks `/agent/compile_flow/` for a dry-run compile of the live canvas instead of trusting whatever is already in the pool. If the canvas still looks wrong, save the `.flw`, reload it, and check the browser console for a compile error.
- **Start runs an older version of the flow.** Start now compiles the visible canvas in write mode before launching. If you still see old behavior, clear the pool from the ACP close/clear controls, load the `.flw` again, and run Validate once before Start.
- **Parametrizer mappings disappear after reload.** Save the flow after creating mappings. New `.flw` files store mappings under `artifacts.parametrizerMappings`, and the loader restores them into each Parametrizer node.

### 9.5. ACPX / external CLIs

- `acp_doctor` says agent not resolvable → CLI not on `PATH`, or set `acpx.agents.<id>.command` to the absolute path.
- Transcript only shows outbound prompts on Windows → your build is older than May 2026. Update — fix is `transport="oneshot-prompt"` for claude/gemini/cursor/qwen/codex.
- API key not picked up → per-agent `acpx.agents.<id>.env` wins over exported shell vars; check both.
- Session left running → always end with `acp_kill`. If a request times out, manually `acp_list_sessions` + `acp_kill`.

### 9.6. Frozen build / installer

- Wrong config used → place `config.json` next to the exe, or set `CONFIG_PATH`.
- Missing templates → verify `agents/` exists in the install. Rebuild if `README.md`, `jd-cli/`, or template directories are missing.
- Restrictive Group Policy blocks shortcuts → `CreateShortcut.ps1` falls back to user-scoped Desktop / Start Menu paths.

### 9.7. Logs to consult first

| What | Where |
|---|---|
| **Application-wide** (everything) | `Tlamatini/tlamatini.log` (truncated on every start, no rotation) |
| ACP workflow agents | `<pool_directory>/<agent_name>/<agent_name>.log` |
| Wrapped chat-agents | `agent/agents/pools/_chat_runs_/<agent>_<seq>_<id>/<agent>_<seq>_<id>.log` (failed runs preserved) |
| ACPX transcripts | `<acpx.stateDir>/<session_id>.transcript.ndjson` |
| Skill audits | `~/.tlamatini/skill-audit/<YYYY-MM>/<epoch>_<skill>_<id8>.ndjson` |

`tlamatini.log` silences successful `GET / 200/304` polling lines but keeps non-2xx/3xx GETs visible.

INFO loggers worth knowing: `agent.chat_agent_runtime`, `agent.tools`, `agent.mcp_agent`, `agent.global_execution_planner`, `agent.capability_registry`.

---

## 10. Contributing & License

### 10.1. Contributing

1. Fork; create a feature branch.
2. Follow PEP 8. Run `python -m ruff check` and `npm run lint` before pushing.
3. Add tests in `Tlamatini/agent/tests.py` (the suite has 266+ tests; the bar is "zero regressions, ruff clean").
4. Update docs when API or behavior changes — this README, `docs/claude/*.md`, and `agent/agents/flowcreator/agentic_skill.md` for new agents.
5. Open a PR with a clear description.

When adding a new agent, follow the 8-step checklist in `Tlamatini/.agents/workflows/create_new_agent.md` (backend script + view + migration + CSS gradient + 4 JS files + agentic_skill.md + README + lint).

### 10.2. Acknowledgments

[Django](https://www.djangoproject.com/) · [LangChain](https://github.com/langchain-ai/langchain) · [LangGraph](https://github.com/langchain-ai/langgraph) · [Ollama](https://ollama.ai/) · [FAISS](https://github.com/facebookresearch/faiss) · [Anthropic](https://www.anthropic.com/) · [Bootstrap](https://getbootstrap.com/) · [TextMeBot](https://textmebot.com/) · [Ruff](https://github.com/astral-sh/ruff) · [PyAutoGUI](https://github.com/asweigart/pyautogui) · [JD-CLI](https://github.com/intoolswetrust/jd-cli)

### 10.3. License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

---

*For the long-form, narrative documentation (full agent bestiary, complete WebSocket / HTTP API reference, glossary, full changelog, architecture deep dives), see [`BookOfTlamatini.md`](BookOfTlamatini.md). For support, open an issue on GitHub.*
