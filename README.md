<p align="center">
  <img src="Tlamatini.jpg" alt="Tlamatini Logo" width="180" height="180" />
</p>

<h1 align="center">Tlamatini</h1>

<p align="center"><em>"one who knows" — a locally-deployed AI developer assistant</em></p>

<p align="center">
  <a href="https://github.com/XAIHT/Tlamatini/releases/tag/v1.5.0"><img src="https://img.shields.io/badge/VERSION-v1.5.0-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="Version v1.5.0" /></a>
  <a href="https://www.python.org/downloads/release/python-31210/"><img src="https://img.shields.io/badge/PYTHON-3.12.10-3776AB?style=for-the-badge&labelColor=2D2D2D&logo=python&logoColor=white" alt="Python 3.12.10" /></a>
  <a href="https://www.djangoproject.com/"><img src="https://img.shields.io/badge/DJANGO-5.2.4-092E20?style=for-the-badge&labelColor=2D2D2D&logo=django&logoColor=white" alt="Django 5.2.4" /></a>
  <a href="#7-building-a-frozen-distribution"><img src="https://img.shields.io/badge/PLATFORM-WIN%2010%20%7C%2011-0078D6?style=for-the-badge&labelColor=2D2D2D&logo=windows&logoColor=white" alt="Platform Windows 10 | 11" /></a>
  <a href="#95-agent-catalog-the-65-types-by-family"><img src="https://img.shields.io/badge/AGENTS-65-8A2BE2?style=for-the-badge&labelColor=2D2D2D" alt="65 Agents" /></a>
  <a href="#35-tutorial-the-multi-turn-toggle"><img src="https://img.shields.io/badge/TOOLS-72-16A34A?style=for-the-badge&labelColor=2D2D2D" alt="72 Multi-Turn Tools" /></a>
  <a href="#5-acpx--external-coding-agent-clis-as-tools"><img src="https://img.shields.io/badge/ACPX-12%20TOOLS-FF8C00?style=for-the-badge&labelColor=2D2D2D" alt="ACPX 12 Tools" /></a>
  <a href="#311-the-acpx-skills-menu--browse-configure-diagnostics-reload"><img src="https://img.shields.io/badge/SKILLS-23-DB2777?style=for-the-badge&labelColor=2D2D2D" alt="23 Skills" /></a>
  <a href="#10-embedding-memory-pre-flight-guard-gpu-hosts"><img src="https://img.shields.io/badge/RAG-FAISS%20%2B%20BM25-009688?style=for-the-badge&labelColor=2D2D2D" alt="Hybrid RAG" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/LICENSE-GPLV3-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="License GPLv3" /></a>
</p>

**Tlamatini** (Nahuatl for *"one who knows"*) is a locally-deployed AI developer assistant that pairs a hybrid [RAG pipeline](#82-rag) (FAISS + BM25, metadata extraction, context budgeting) with a [Multi-Turn](#35-tutorial-the-multi-turn-toggle) tool-orchestration layer, [ACPX](#5-acpx--external-coding-agent-clis-as-tools) delegation to external coding-agent CLIs ([Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview), [Cursor](https://cursor.com), [Codex](https://github.com/openai/codex), [Gemini](https://github.com/google-gemini/gemini-cli), [Qwen](https://github.com/QwenLM/qwen-code), …), and a [visual workflow designer](#4-visual-workflow-designer-agentic_control_panel) with **65 drag-and-drop agents**.

> **Local-first by default**: the full RAG pipeline, the Multi-Turn execution loop, and every workflow agent run on your machine — embeddings and chat are driven by your local [Ollama](https://ollama.com/) install. Cloud LLMs (Claude API, Ollama Pro/Max) and ACPX delegation to cloud CLIs are opt-in per-request, never the default. Sensitive code never leaves the box unless you explicitly route it out.

<p align="center">
  <a href="https://xaiht.org"><strong>🌐 Website</strong></a> &nbsp;·&nbsp;
  <a href="https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s"><strong>▶️ One-minute teaser</strong></a> &nbsp;·&nbsp;
  <a href="BookOfTlamatini.md"><strong>📖 Long-form docs</strong></a> &nbsp;·&nbsp;
  <a href="VERSIONING.md"><strong>🏷️ Versioning</strong></a> &nbsp;·&nbsp;
  <a href="#13-demo-videos"><strong>🎬 More demos</strong></a>
</p>

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
  - [2.4. Cloud models require an Ollama Pro/Max plan](#24-cloud-models-require-an-ollama-promax-plan)
  - [2.5. Clone, install, migrate](#25-clone-install-migrate)
  - [2.6. Run the server (not-frozen)](#26-run-the-server-not-frozen)
  - [2.7. Log in for the first time](#27-log-in-for-the-first-time)
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
  - [3.10. The **DB** menu — Backup, Set DB, and the start-up swap-in](#310-the-db-menu--backup-set-db-and-the-start-up-swap-in)
  - [3.11. The **ACPX-Skills** menu — Browse, Configure, Diagnostics, Reload](#311-the-acpx-skills-menu--browse-configure-diagnostics-reload)
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
- [6. Unreal MCP — Driving Unreal Engine 5 from Tlamatini](#6-unreal-mcp--driving-unreal-engine-5-from-tlamatini)
  - [6.1. What Unreal MCP is](#61-what-unreal-mcp-is)
  - [6.2. Upstream plugin (the **MCP git location**)](#62-upstream-plugin-the-mcp-git-location)
  - [6.3. Installing and enabling the plugin inside your UE5 project](#63-installing-and-enabling-the-plugin-inside-your-ue5-project)
  - [6.4. The 28 commands across 5 categories](#64-the-28-commands-across-5-categories)
  - [6.5. Using Unreal MCP from the chat (`chat_agent_unrealer`)](#65-using-unreal-mcp-from-the-chat-chat_agent_unrealer)
  - [6.6. Using Unreal MCP on the canvas (the visual **Unrealer** node)](#66-using-unreal-mcp-on-the-canvas-the-visual-unrealer-node)
  - [6.7. What the agent actually does, end-to-end](#67-what-the-agent-actually-does-end-to-end)
  - [6.8. Exec Report integration](#68-exec-report-integration)
  - [6.9. Bullet-proof checklist for Unreal Engine users](#69-bullet-proof-checklist-for-unreal-engine-users)
  - [6.10. Troubleshooting Unreal MCP](#610-troubleshooting-unreal-mcp)
- [7. Building a Frozen Distribution](#7-building-a-frozen-distribution)
  - [7.1. Three-step pipeline](#71-three-step-pipeline)
  - [7.2. Step 1 — `build.py`](#72-step-1--buildpy)
  - [7.3. Step 2 — `build_uninstaller.py`](#73-step-2--build_uninstallerpy)
  - [7.4. Step 3 — `build_installer.py`](#74-step-3--build_installerpy)
  - [7.5. What the installer does on the end-user box](#75-what-the-installer-does-on-the-end-user-box)
  - [7.6. Source mode vs Frozen mode: why flows still work](#76-source-mode-vs-frozen-mode-why-flows-still-work)
- [8. Configuration (`Tlamatini/agent/config.json`)](#8-configuration-tlamatiniagentconfigjson)
  - [8.1. LLM and unified-agent](#81-llm-and-unified-agent)
  - [8.2. RAG](#82-rag)
  - [8.3. ACPX](#83-acpx)
  - [8.4. MCP services and other knobs](#84-mcp-services-and-other-knobs)
- [9. Architecture at a Glance](#9-architecture-at-a-glance)
  - [9.1. Big picture](#91-big-picture)
  - [9.2. The five layers](#92-the-five-layers)
  - [9.3. Multi-Turn execution pipeline](#93-multi-turn-execution-pipeline)
  - [9.4. Agent contracts and the Flow Compiler](#94-agent-contracts-and-the-flow-compiler)
  - [9.5. Agent catalog (the 65 types, by family)](#95-agent-catalog-the-65-types-by-family)
- [10. Embedding-Memory Pre-Flight Guard (GPU hosts)](#10-embedding-memory-pre-flight-guard-gpu-hosts)
  - [10.1. Why this exists](#101-why-this-exists)
  - [10.2. How the check fires (the hook point)](#102-how-the-check-fires-the-hook-point)
  - [10.3. GPU detection and no-GPU behavior](#103-gpu-detection-and-no-gpu-behavior)
  - [10.4. Three-tier VRAM prediction](#104-three-tier-vram-prediction)
  - [10.5. The 80% threshold and the chat-bubble warning](#105-the-80-threshold-and-the-chat-bubble-warning)
  - [10.6. Tuning, overrides, and what the guard does NOT do](#106-tuning-overrides-and-what-the-guard-does-not-do)
  - [10.7. Test coverage](#107-test-coverage)
- [11. Orphan-Process Cleanup (`conhost.exe` reaper)](#11-orphan-process-cleanup-conhostexe-reaper)
  - [11.1. The problem this solves](#111-the-problem-this-solves)
  - [11.2. The three tiers](#112-the-three-tiers)
  - [11.3. What gets reaped (and what does not)](#113-what-gets-reaped-and-what-does-not)
  - [11.4. The user-visible follow-up message](#114-the-user-visible-follow-up-message)
- [12. Troubleshooting](#12-troubleshooting)
  - [12.1. Ollama / models](#121-ollama--models)
  - [12.2. RAG / context](#122-rag--context)
  - [12.3. Multi-Turn / planner](#123-multi-turn--planner)
  - [12.4. Chat-created flows and ACP validation](#124-chat-created-flows-and-acp-validation)
  - [12.5. ACPX / external CLIs](#125-acpx--external-clis)
  - [12.6. Frozen build / installer](#126-frozen-build--installer)
  - [12.7. Logs to consult first](#127-logs-to-consult-first)
- [13. Versioning](#13-versioning)
  - [13.1. The bump rules](#131-the-bump-rules)
  - [13.2. Cutting a release](#132-cutting-a-release)
  - [13.3. Where you can see the running version](#133-where-you-can-see-the-running-version)
  - [13.4. Building without tagging (development)](#134-building-without-tagging-development)
  - [13.5. Overriding the resolved version](#135-overriding-the-resolved-version)
- [14. Contributing & License](#14-contributing--license)
  - [14.1. Contributing](#141-contributing)
  - [14.2. Acknowledgments](#142-acknowledgments)
  - [14.3. License](#143-license)

---

## 1. Overview

### 1.1. What Tlamatini is

**Tlamatini** (Nahuatl for *"one who knows"*) is a Django/Channels app you run on your own machine. It packages a hybrid RAG pipeline, a Multi-Turn tool-calling LLM loop, an ACPX runtime that spawns external coding-agent CLIs as child processes, an **Unreal MCP** client that drives Unreal Engine 5 from chat or canvas, and a drag-and-drop workflow designer with 65 agent types — into one local install. Backends: **Ollama** (local), **Anthropic Claude** (cloud), **Qwen vision** (Ollama).

License: **GPL-3.0** · Repo: <https://github.com/XAIHT/Tlamatini.git> · Platform tested: Windows 11 (cross-platform for source mode).

### 1.2. What it gives you that a plain chatbox does not

1. **Real RAG over your code** — FAISS + BM25 hybrid retrieval, code-aware metadata extraction, Reciprocal Rank Fusion, context budgeting, OOM fallback.
2. **Multi-Turn mode** — the LLM becomes an *operator*: shell, Python, APIs, SQL, file ops, screenshots, keyboard/mouse automation, email, Telegram, WhatsApp — chained in one conversation.
3. **ACPX** — delegate sub-tasks to external CLIs (`claude`, `cursor-agent`, `codex`, `gemini`, `qwen-code`, plus 8 more) and relay output between them.
4. **Visual workflow designer** — design `.flw` flows once, run them unattended, schedule with Croner, watch them with FlowHypervisor.

Everything runs locally. The whole app packages into a one-click Windows `.exe` distribution (Part [§7](#7-building-a-frozen-distribution)).

### 1.3. Demo videos

- [First system-usage walkthrough](https://www.youtube.com/watch?v=CkvDPSd_c-g)
- [Loading a complete project and summarizing its source code](https://www.youtube.com/watch?v=Lrpbt_dPIXw)
- [Installing OpenCV end-to-end in Multi-Turn](https://www.youtube.com/watch?v=bBlqbZVK-Wk)
- [Uninstalling Poco — Exec Report and matching flow](https://www.youtube.com/watch?v=E5vi0q5FxXQ)
- [Implementing a FlowCreator-aided agentic flow](https://www.youtube.com/watch?v=3Pno6s4xVsE)
- [A complete Cybersec enhancement with Tlamatini!!!](https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s)


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
ollama pull Nomic-Embed-Text:latest
ollama pull glm-5:cloud
ollama pull qwen3.5:cloud
ollama pull gpt-oss:120b-cloud
ollama pull qwen3.5:397b-cloud
ollama pull llama3.2-vision:11b
```

| Tag | Used for |
|---|---|
| `Nomic-Embed-Text:latest` | RAG embeddings (default — small VRAM footprint, ~600 MB resident) |
| `glm-5:cloud` | Default chat + Multi-Turn unified-agent + MCP file-search |
| `qwen3.5:cloud` | Default vision (Image-Interpreter) |
| `gpt-oss:120b-cloud` | Several workflow-agent templates (Monitor-Log, Notifier, Prompter, Summarizer, …) |
| `qwen3.5:397b-cloud` | Default FlowCreator |
| `llama3.2-vision:11b` | Local vision fallback |

You can substitute any tag — just edit `Tlamatini/agent/config.json` (see [§8.1](#81-llm-and-unified-agent)) or the relevant agent's `config.yaml`.

> **Optional: swap to a higher-detail embedding model.** If your retrieval quality on dense, technical corpora is not good enough with the default, you can switch to `qwen3-embedding:8b` from the **Config → Models** menu inside the app (or by editing `embeding-model` in `config.json` and reconnecting). **Use with caution**: `qwen3-embedding:8b` is roughly **10× heavier in VRAM** than `Nomic-Embed-Text:latest` (~6.24 GB resident vs ~600 MB on a Q4_K_M quant) and will trip the embedding-memory pre-flight guard (see [§10](#10-embedding-memory-pre-flight-guard-gpu-hosts)) on 8 GB consumer GPUs. Pull it first with `ollama pull qwen3-embedding:8b`.

### 2.4. Cloud models require an Ollama Pro/Max plan

Four of the six default model tags in [§2.3](#23-pull-the-default-models) carry the `:cloud` suffix — `glm-5:cloud`, `qwen3.5:cloud`, `gpt-oss:120b-cloud`, and `qwen3.5:397b-cloud`. Those are **Ollama Cloud** models: they live on Ollama's servers, not on your machine, and `ollama pull` only registers a stub that proxies inference to the cloud. Reaching that cloud requires a logged-in Ollama account and a subscription tier that allows the workload you intend to run.

The plan structure (prices are deliberately omitted from this README because they change — check **<https://ollama.com/pricing>** for the current numbers):

![Ollama plan structure — Free / Pro / Max](OllamaPricing.png)

| Plan | Cloud-model access | Why it matters for Tlamatini |
|---|---|---|
| **Free** | 1 cloud model concurrently, light usage. Local open-weights models are unlimited. | Enough to *try* a single cloud model for a one-shot chat. **Not enough** for Tlamatini's default config, which pins different cloud models for chat (`glm-5:cloud`), FlowCreator (`qwen3.5:397b-cloud`), several workflow agents (`gpt-oss:120b-cloud`), and vision (`qwen3.5:cloud`) — so a real Multi-Turn run typically needs 2–3 cloud models loaded at once. |
| **Pro** | 3 concurrent cloud models, ~50× the Free monthly quota, access to the larger cloud-only models, ability to upload / share private models. | The realistic minimum for running Tlamatini out-of-the-box with its shipped cloud-model defaults — Multi-Turn + Exec Report + occasional Image-Interpreter calls. |
| **Max** | 10 concurrent cloud models, ~5× the Pro quota, designed for sustained heavy agentic workloads. | Recommended for long-running ACPX relays, FlowHypervisor-supervised flows, and Croner-driven unattended runs that chain many cloud calls per hour. |

**If you do not want to subscribe**, you can run Tlamatini entirely on local open-weights models. Edit `Tlamatini/agent/config.json` (`chained-model`, `unified_agent_model`, `mcp_file_search_model`, `flow_creator_model`, `image_interpreter_model`) and every agent `config.yaml` that names a `:cloud` tag, and swap them for a model you have pulled locally (for example, `llama3.1:8b`, `qwen2.5-coder:14b`, `mistral-nemo:12b`). Performance and quality will scale with your GPU/CPU — Multi-Turn and ACPX both work fine on a sufficiently large local model.

**API keys are separate.** This subscription only governs `*:cloud` Ollama models. The ACPX runtime can additionally spawn external coding-agent CLIs that bring their own credentials (Anthropic API key for `claude`, OpenAI key for `codex`, Google key for `gemini`, etc.) — those are configured in `Tlamatini/agent/config.json` under `acpx.agents.<id>.env` and are unaffected by your Ollama plan. See [§5.6](#56-api-key-setup-the-easy-button) for the easy-button setup. (Unreal MCP is *not* part of ACPX — it's its own MCP surface, documented in [§6](#6-unreal-mcp--driving-unreal-engine-5-from-tlamatini).)

### 2.5. Clone, install, migrate

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

### 2.6. Run the server (not-frozen)

```bash
python Tlamatini/manage.py runserver --noreload
```

`--noreload` is important: Daphne's auto-reloader does not coexist well with the wrapped-runtime subprocess pool.

The console title becomes `Tlamatini` and stdout/stderr are tee'd into `Tlamatini/tlamatini.log` (truncated on every start). When debugging, `tlamatini.log` is the first thing to read.

### 2.7. Log in for the first time

Open `http://127.0.0.1:8000/` and log in with the superuser you just created. Then:

- `/agent/` — the chat (Part [§3](#3-using-the-chat-agent))
- `/agentic_control_panel/` — the visual designer (Part [§4](#4-visual-workflow-designer-agentic_control_panel))
- `/admin/` — Django admin (change passwords, manage users)

> If you used the **installer** (Part [§7](#7-building-a-frozen-distribution)) instead of cloning, the default credentials are `user` / `changeme`. Change them at first login via `/admin/`.

---

## 3. Using the Chat (`/agent/`)

### 3.1. Chat layout in 30 seconds

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ Tlamatini  [Context ▼] [Open in… ▼] [MCPs ▼] [Tools ▼] [Agents ▼] [Config ▼] [DB ▼] │ ← top nav
├───────────────────────────────────────────────────────────────────────────────┤
│  Multi-Turn ☐   Exec Report ☐   ACPX ☐   internet ☐    Clear ⌫               │ ← four toggles
├───────────────────────────────────────────────────────────────────────────────┤
│  ┌──── chat ────────────────┐   ┌──── code canvas ────────────────┐          │
│  │  conversation history    │   │  syntax-highlighted, with copy  │          │
│  └──────────────────────────┘   └─────────────────────────────────┘          │
├───────────────────────────────────────────────────────────────────────────────┤
│  Type your prompt here…                                              [Send]   │
└───────────────────────────────────────────────────────────────────────────────┘
```

The **four toolbar toggles** are independent. Tick whatever combination fits the task — each one is its own tutorial section below.

Newer builds also expose a **Config** dropdown in the same navbar. `Config -> Models` edits the most common model-name fields, and `Config -> URLs` edits the Ollama / unified-agent / MCP endpoint values through validated dialogs instead of hand-editing JSON. The chat/canvas divider was also tightened so resizing the right-hand canvas feels more predictable during long editing sessions.

The newest entry in that navbar is the **DB** dropdown: `DB -> Backup database` snapshots the live SQLite file to a directory you pick, and `DB -> Set DB` stages a `db.sqlite3` file of your choice for the **next session** — Tlamatini swaps it in before Django opens the database, archives the previous one under `DB/Older/<timestamp>/`, then continues normal start-up. Full walkthrough in [§3.10](#310-the-db-menu--backup-set-db-and-the-start-up-swap-in).

### 3.2. Setting code as context

Click **Context** in the top nav:

| Menu entry | What it does |
|---|---|
| **Set directory as context** | Loads a folder. Tlamatini reads every text file, splits, embeds, builds FAISS+BM25, grounds answers in your code. |
| **Set file as context** | Single-file scope. |
| **Set canvas as context** | Use the code currently shown in the canvas (handy for iterative editing). |
| **Clear context** | Drops the loaded context. |

A green banner at the top shows the current context path. If embedding runs out of memory, Tlamatini packs the source files as a fallback context — retrieval quality drops, access to your code does not.

If you refresh the browser and Tlamatini restores a saved context automatically, the input now stays disabled until the contextual RAG chain has actually finished rebuilding. That closes the old "restored banner arrived before the context was really ready" race on the first load stage.

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

- The planner picks the relevant subset of Tlamatini's **72 Multi-Turn tools** — 20 core Python tools (`execute_command`, `agent_starter`, `googler`, the image-analysis pair, the `chat_agent_run_*` lifecycle helpers, …), 40 wrapped chat-agent tools, and 12 ACPX/Skill tools — binding at most `max_selected_tools` per request (default cap: **20**).
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

### 3.10. The **DB** menu — Backup, Set DB, and the start-up swap-in

The whole of Tlamatini — chat history, agents, Tool/MCP toggles, sessions, your user — lives in a single SQLite file. The **DB** dropdown gives you a safe, GUI-first way to handle that file: a read-only **Backup** path, a destructive-but-deferred **Set DB** path, and a built-in audit trail under `DB/Older/`.

#### `DB -> Backup database`

Opens a dialog with one input — the **target directory**. The path is live-validated (350 ms debounce): the page asks `GET /agent/check_backup_directory/?path=…` as you type and colors the status line green / amber / red:

| State | Status | Meaning |
|---|---|---|
| 🟢 | `Directory exists. db.sqlite3 will be saved here.` | Ready to back up. |
| 🟠 | `A filename was specified — please specify the directory only.` | You typed a file path; the output is **always** named `db.sqlite3` so it can be loaded back later. |
| 🔴 | `Directory does not exist.` | Missing on disk. |

Click **Backup** → Tlamatini calls `POST /agent/backup_db/`, resolves the live database path via `settings.DATABASES['default']['NAME']` (so source / frozen behave identically), and `shutil.copy2`s it to `<your-dir>/db.sqlite3`. The live database stays open and unchanged.

#### `DB -> Set DB`

The opposite direction: replace the database on the **next start-up**. Same dialog idiom, stricter validation. The input is the **full path to a `db.sqlite3` file**; the page asks `GET /agent/check_set_db_file/?path=…` as you type:

| State | Status | Meaning |
|---|---|---|
| 🟢 | `File exists. It will be loaded on the next start-up.` | Real `db.sqlite3` with a valid SQLite header. |
| 🟠 | `File found, but its name is not "db.sqlite3". Tlamatini will still stage it as db.sqlite3.` | Snapshot-style names (`db_2026-05-14.sqlite3`) work — the staging step renames. |
| 🟠 | `Specify the full path to a db.sqlite3 file, not a directory.` | You typed a directory; Set DB needs a file. |
| 🔴 | `The selected file does not look like a SQLite database.` | First 16 bytes don't match the `SQLite format 3\x00` magic. |
| 🔴 | `File does not exist.` | Missing on disk. |

Click **Set** → `POST /agent/set_db/` copies your file into `<base>/DB/ToLoad/db.sqlite3` (where `<base>` is the executable directory in frozen mode, the inner Django project directory in source mode). The live database is **not** touched — SQLite is held open by Django, so the actual replacement must wait for a process restart.

Immediately after staging succeeds, the dialog is replaced by a **yellow ⚠ warning panel** with a single **OK** button:

> *The selected database will be loaded the next time Tlamatini starts. If you want it loaded immediately, you must restart Tlamatini completely so the swap-in can run BEFORE Django opens the live database.*

If you click **Cancel** instead of **Set**, the staging dialog closes and nothing is written.

#### The start-up swap-in (the third, invisible leg)

The actual replacement lives at the very top of `Tlamatini/manage.py`, in `_apply_pending_db_swap()`. It runs **before any Django import** so Django's SQLite connection pool is never holding a stale file descriptor at the moment of the swap:

```
manage.py main()
    │
    ▼
_apply_pending_db_swap()
    │
    ▼
[ DB/ToLoad/db.sqlite3 exists? ]
    │
    ├─ NO  ──► return (no-op, normal start-up continues)
    │
    └─ YES ──► [1] mkdir DB/Older/<YYYY-MM-DD_HHMMSS>/
               [2] shutil.move(live db.sqlite3 → Older/<timestamp>/db.sqlite3)
               [3] shutil.move(DB/ToLoad/db.sqlite3 → live db.sqlite3)
               [4] return
    │
    ▼
from django.core.management import execute_from_command_line   ← only NOW Django wakes up
```

Three guarantees:

1. **A Reconnect from the navbar is NOT enough.** The swap window is only open *before* the Django process opens its SQLite pool. You must **fully restart Tlamatini** (close the console / kill the exe, then launch again).
2. **Atomic moves, no copies.** Both legs use `shutil.move` (filesystem rename when possible, copy+delete across mounts). A second launch with `DB/ToLoad/` empty is automatically a no-op — no "stuck flag" to clear.
3. **Mode-correct path resolution.** Frozen mode reads `<exe_dir>/DB/ToLoad/db.sqlite3` (where you can browse to it in Explorer); source mode reads `<repo>/Tlamatini/DB/ToLoad/db.sqlite3` (next to `manage.py`). The live `db.sqlite3` path is computed the same way Django does — `_MEIPASS/db.sqlite3` under PyInstaller, `<manage.py dir>/db.sqlite3` in source — so the swap-in always writes to exactly the path Django will open.

If anything fails inside the swap-in (locked file on Windows, corrupt source, permission error), the function catches the exception, prints `--- [DB SWAP] Skipped due to error: …` to `tlamatini.log`, and lets Tlamatini start normally with the previous database. **A bad ToLoad file must never lock you out of your own database.**

#### The Older audit trail

Every successful swap-in leaves a complete record under `<base>/DB/Older/<YYYY-MM-DD_HHMMSS>/db.sqlite3`. Because Set DB *moves* (not copies) the prior live database, this archive is the only built-in recovery path:

```
DB/
├─ ToLoad/                 ← empty most of the time; momentary home of next-session pick
│   └─ README.md
└─ Older/
    ├─ 2026-05-14_153022/db.sqlite3   ← was live before swap #1
    ├─ 2026-05-14_164410/db.sqlite3   ← was live before swap #2
    └─ README.md
```

To roll back, drop the archived `db.sqlite3` back into `ToLoad/` and restart — the swap-in will archive the **current** live database under a fresh timestamp and promote your roll-back pick. Tlamatini never auto-deletes anything from `Older/`; prune by hand when the tree gets noisy, but remember each file is a full snapshot of chat history + agents + sessions + your user.

#### Where the tree comes from

Both directories must exist on day one (the swap-in opens them with `os.makedirs(exist_ok=True)`, but having them pre-seeded with docs prevents user confusion):

- **Source / dev mode**: `Tlamatini/Tlamatini/DB/{ToLoad,Older}/README.md` are checked into the repo. The README files are the "git keepers" — without them, git would silently drop the empty directories.
- **Frozen mode**: `build.py` extends its `empty_dirs` tuple with `"DB/ToLoad"` and `"DB/Older"`. The PyInstaller post-build step creates both under `dist/manage/`, the `pkg.zip` packager preserves them via explicit zip entries, and end-users get the tree from the very first launch.

### 3.11. The **ACPX-Skills** menu — Browse, Configure, Diagnostics, Reload

Tlamatini ships with **23 skills** — markdown SKILL.md packages under `agent/skills_pkg/` that the LLM can invoke through `invoke_skill('<name>', '{...args...}')`. They cover everything from the canonical `acp-router` (pick the right external CLI for an intent) and `summarize` (compress text faithfully) to `setup-new-acpx-key`, `skill-creator`, `code-review` (senior-engineer git-diff review with an APPROVE/REQUEST_CHANGES verdict) and `security-audit` (multi-scanner SAST/secret/dependency sweep), the `tlamatini_*` audit/lint/refactor helpers, and integration stubs for GitHub / Notion / Slack / Gmail / Jira / Todoist / Trello / Weather.

Before 2026-05-17 the only way to interact with them was through the LLM (`list_skills` to enumerate, `invoke_skill` to run). The **ACPX-Skills** navbar dropdown — added next to **Agents** and **Config** in the chat toolbar — gives you an operator-grade admin surface that does NOT require the LLM. Four entries:

#### `ACPX-Skills -> Browse Skills`

Opens a two-pane modal: a left-side list of all 23 skills (with a green/red dot for enabled / disabled and a runtime tag) and a right-side detail pane that shows the selected skill's full identity — description, runtime (in-process / acpx), `acpx_agent` if any, budgets (max_iterations · max_seconds · max_tokens), trigger keywords, `requires_tools` and `requires_mcps`, inputs and outputs (with required-field markers), and the full markdown body. A search box at the top filters by name or description as you type. Pure read — nothing is written back.

Backed by `GET /agent/skills/` (list payload) and `GET /agent/skills/<name>/` (deep detail). Use it when you want to know what a skill *actually does* before you ask the LLM to call it, or when you've just authored a new SKILL.md and want to confirm it parsed correctly.

#### `ACPX-Skills -> Configure Skills`

A checkbox grid — one row per skill — that mirrors the existing **MCPs** and **Agents** dialogs exactly. Toggle a checkbox off, click **Continue**, and the row's `Skill.enabled` flips to `false`. Two consequences immediately:

- `list_skills` (the LLM's enumeration tool) filters that skill out of its returned array.
- `invoke_skill('<name>', ...)` returns `{"ok": false, "code": "SKILL_DISABLED"}` instead of running.

Toggling back to enabled restores the skill. This is the right knob when (a) you want to hide an unfinished skill from the planner, (b) you don't have the API key for an integration skill (e.g. `notion` without `NOTION_TOKEN`) and don't want the LLM to keep trying, or (c) you're running a demo and want a minimal tool surface.

The toggle goes over the same WebSocket channel as `set-mcps` / `set-tools` / `set-agents` — payload encoding `name=description=true/false,name=description=true/false,...`. Backend handler is in `consumers.py::receive` and calls `save_skill(name, enabled)` which touches only the `enabled` column.

#### `ACPX-Skills -> Diagnostics`

A cross-check report that catches drift between the skill catalog and the rest of the system. Sections:

- **Missing tool dependencies** — for each skill whose `requires_tools` lists a tool that's currently **disabled** in the Tools dialog, lists the skill + the unmet tools. (A disabled tool means the skill *would* fail at runtime — Diagnostics surfaces it before the LLM tries.)
- **Missing MCP dependencies** — same idea against disabled `Mcp` rows.
- **Unknown ACPX agents** — for skills with `runtime: acpx`, flags any `acpx_agent` value that isn't in the `AcpAgent` table (typo, removed CLI, etc.).
- **Orphan DB rows** — `Skill` rows whose SKILL.md file no longer exists on disk. Usually a sign that someone deleted a skill directory without running Reload.

Each section is collapsed when clean (✓ green) and expanded with red ⚠ counts when something's wrong. Run it after editing SKILL.md files or after toggling tools/MCPs to confirm nothing is silently broken. Backed by `GET /agent/skills/_/diagnostics/` — pure read, no writes.

#### `ACPX-Skills -> Reload Registry`

A single-click button that re-runs the registry boot pipeline: rescan `agent/skills_pkg/`, refresh every `Skill` DB row's metadata (description, runtime, frontmatter_json, body_sha256), prune any DB row whose SKILL.md is gone. The user-toggled `enabled` field is preserved across reload.

Use this after you've authored or edited a SKILL.md on disk — no server restart needed. The success toast tells you the new skill count.

#### What the DB stores — and what it does NOT

By design, the `Skill` DB table stays at "enumeration + enable/disable" only, exactly the way the `Tool` and `Mcp` tables work. Per-skill **permissions** (filesystem read/write globs, allowed shell commands, network deny/allow), **budgets** (max_iterations / max_seconds / max_tokens), and the skill's **body** all live in the SKILL.md frontmatter on disk and are the only source of truth. The admin UI deliberately does NOT let you override them from the browser — if you want to change a permission, edit the SKILL.md and click Reload. This keeps `git diff` honest: every behavioural change to a skill shows up in a file, not in a database row that the next backup would silently archive.

#### Where to look

- HTTP endpoints: `agent/views.py` (`list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`) — wired in `agent/urls.py`.
- WebSocket toggle: `agent/consumers.py::receive` (`set-skills` branch) → `save_skill(name, enabled)`. The connect path also calls `skill_establishment()` for every row so the frontend's `skills = []` cache hydrates on session start, mirroring how `tools[]` and `agents[]` hydrate.
- Tool-surface gating: `agent/acpx/tools.py::_disabled_skill_names()` — fails open on DB exception so a broken admin layer never silently hides skills.
- Frontend dialogs: `agent/static/agent/js/skills_dialog.js` (the Configure / Browse / Diagnostics / Reload dialogs) + `agent/static/agent/css/skills_dialog.css`.
- Coverage: 14 tests in `agent/tests.py` (`SkillsAdminEndpointTests`, `SkillsToolSurfaceGatingTests`, `SkillsNavbarTemplateContractTests`).

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

Another important nuance: if you opened an agent dialog and manually edited wiring-sensitive fields such as `source_agents` or an Ender kill list, those dialog edits now survive compilation. Canvas edges still contribute their live connections, but a deliberate dialog override is no longer silently discarded by Validate or Start.

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

Stop is also safer in mixed flows now: the ACP cleanup path is better at terminating leftover session processes before the next run begins, so partially mixed ACP sessions are less likely to leave orphaned agents behind.

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

23 source agents support this format: Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen/Cipher/DeCipher, Gatewayer, Gateway-Relayer, Googler, **Playwrighter**, **ACPXer**, Shoter, Mouser, **Unrealer**, **Reviewer**, **Analyzer**.

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

23 seed skills live under `agent/skills_pkg/` (acp-router, summarize, setup-new-acpx-key, skill-creator, code-review, security-audit, 8× tlamatini-* maintenance helpers, plus OpenClaw-format ports for github / gmail / slack / jira / notion / todoist / trello / weather).

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

## 6. Unreal MCP — Driving Unreal Engine 5 from Tlamatini

The **Unrealer** agent (#62 in the catalog) lets Tlamatini drive a live Unreal Engine 5 editor through the **Unreal MCP** plugin's TCP socket protocol. You spawn a `chat_agent_unrealer` call from Multi-Turn or drop an **Unrealer** node on the visual canvas; Tlamatini opens a TCP connection to `127.0.0.1:55557`, sends one JSON command (`{"type": <verb>, "params": {...}}`), captures the engine's JSON response into an `INI_SECTION_UNREALER<<<` block, and triggers downstream agents. The full 28-command surface of the upstream Unreal MCP plugin is exposed — actor manipulation, Blueprint creation and graph wiring, input mappings, and UMG widget building — without you ever leaving the chat or the canvas.

### 6.1. What Unreal MCP is

**Unreal MCP** is an open-source UE5 plugin (Model Context Protocol over a TCP socket) that runs **inside the Unreal Editor process** and accepts one JSON command per TCP connection. Each command names a verb (`spawn_actor`, `create_blueprint`, `compile_blueprint`, `add_widget_to_viewport`, …) and a dictionary of parameters; the plugin schedules the work onto UE5's game thread, executes it, and writes a JSON response back over the same socket before closing it. The wire shape is small — `{"type": <command>, "params": {...}}` going in, `{"status": "ok"|"error", "result": {...}}` (or `{"success": false, "error": "..."}`) coming back — and is identical across every documented command.

**Tlamatini does not embed or compile the plugin.** It is a *client* of whatever UE5 instance the user has already started. The engine must be open, the plugin must be enabled, and its in-engine listener must be bound to `127.0.0.1:55557` (the default — configurable per-call via `host` / `port`). Tlamatini contributes the calling side: one wrapped Multi-Turn tool, one visual canvas node, one Agent Contract entry, one Exec Report row family, and one Parametrizer source mapping — all built around the same `UnrealConnection` adapter at `agent/agents/unrealer/unrealer.py`.

### 6.2. Upstream plugin (the **MCP git location**)

The canonical reference implementation Tlamatini's `UnrealConnection` adapter mirrors verbatim is:

- **Repository:** `https://github.com/chongdashu/unreal-mcp`
- **License:** MIT
- **Supported UE versions:** Unreal Engine 5.5+
- **Plugin folder name:** `UnrealMCP`
- **Default plugin TCP port:** `55557`

Two equivalent community forks ship the same wire protocol on the same port; either works with Tlamatini's Unrealer with **no client changes**:

- `https://github.com/CrispyW0nton/Unreal-MCP-Ghost`
- `https://github.com/gingerol/vhcilab-unreal-engine-mcp`

Pick the upstream that matches your UE5 version and your team's licensing comfort. If you fork the plugin to add a new command verb, your fork is automatically usable from Tlamatini — there is no client-side allow-list of verbs (the wrapped tool forwards any `command` + `params` pair verbatim).

### 6.3. Installing and enabling the plugin inside your UE5 project

The plugin is a per-project install (not engine-wide). Steps:

1. **Clone or download** the upstream plugin (only the `MCPGameProject/Plugins/UnrealMCP` folder matters — different forks may name the folder slightly differently; rename to `UnrealMCP` if needed).
2. **Drop the folder** into your project's `Plugins/` directory so the final path is `<YourProject>/Plugins/UnrealMCP/UnrealMCP.uplugin`. Create the `Plugins/` folder at the project root if it does not exist.
3. **Open the project in UE5.** The editor will detect the new plugin and offer to rebuild it for your engine version — accept. If you opened a Blueprint-only project, you will be prompted to install Visual Studio Build Tools / Xcode command-line tools first, since the plugin is C++.
4. **Enable the plugin** via `Edit → Plugins → search "UnrealMCP" → tick Enabled`. Restart the editor.
5. **Confirm the listener is bound.** With the editor running, open the **Output Log** (`Window → Developer Tools → Output Log`) and look for a line such as `LogTemp: UnrealMCP listening on 127.0.0.1:55557`. That line is your green light: the plugin is now waiting for JSON commands on the loopback interface.

> **You do not need to press Play (PIE).** The plugin listens at *editor* level — actor manipulation, Blueprint creation, widget construction, etc. all work against the open project even when PIE is stopped. Some UMG operations (`add_widget_to_viewport`) physically render only after the user enters PIE, but the build steps are queued correctly either way.

### 6.4. The 28 commands across 5 categories

The Unrealer agent forwards whatever `command` + `params` you pass it, so the exact catalog is whatever the upstream plugin exposes. As of the canonical chongdashu/unreal-mcp release, that is **28 commands across 5 categories**:

| Category | Commands |
|---|---|
| **editor** | `get_actors_in_level`, `find_actors_by_name`, `spawn_actor`, `delete_actor`, `set_actor_transform`, `get_actor_properties`, `set_actor_property`, `spawn_blueprint_actor` |
| **blueprint** | `create_blueprint`, `add_component_to_blueprint`, `set_static_mesh_properties`, `set_component_property`, `set_physics_properties`, `compile_blueprint`, `set_blueprint_property` |
| **node** | `add_blueprint_event_node`, `add_blueprint_input_action_node`, `add_blueprint_function_node`, `connect_blueprint_nodes`, `add_blueprint_variable`, `add_blueprint_get_self_component_reference`, `add_blueprint_self_reference` |
| **project** | `create_input_mapping` |
| **umg** | `create_umg_widget_blueprint`, `add_text_block_to_widget`, `add_button_to_widget`, `bind_widget_event`, `add_widget_to_viewport`, `set_text_block_binding` |

Param shapes vary per command (e.g. `spawn_actor` wants `name` + `type` + `location` + `rotation`; `create_blueprint` wants `name` + `parent_class`; `add_text_block_to_widget` wants `widget_name` + `text_block_name` + `text` + `position` + `size` + `font_size` + `color`). The Unrealer agent does not validate them — it forwards them as-is. The plugin will reply with `{"status": "error", "error": "<reason>"}` if a param is missing or malformed, and that error lands verbatim in the `INI_SECTION_UNREALER` block so Multi-Turn / Parametrizer can branch on it.

### 6.5. Using Unreal MCP from the chat (`chat_agent_unrealer`)

The wrapped Multi-Turn tool `chat_agent_unrealer` is the easiest way in. Tick **Multi-Turn** in the toolbar, leave **Exec Report** ticked too (the Unreal calls get their own table in the answer), and send a prompt like:

> "Run Unreal command with command='spawn_actor' and params.name='MyCube' and params.type='StaticMeshActor' and params.location=[0,0,150]."

The planner picks `chat_agent_unrealer`, the wrapped runtime spawns one short-lived `unrealer.py` child under `agent/agents/pools/_chat_runs_/unrealer_<seq>_<id>/`, the child opens a TCP socket to `127.0.0.1:55557`, sends the JSON command, captures the response, emits the `INI_SECTION_UNREALER` block to its log, and exits. The Multi-Turn loop reads the run's log excerpt, parses the section, and returns the full Unreal response JSON to the LLM. The LLM then sees the engine's reply and either reports it to you, branches on it, or fires the next call.

The tool accepts the same overrides documented in `config.yaml`:

- `host='10.0.0.5'` and `port=55557` to target a remote UE instance (rare; the plugin binds to loopback by default and you would need to change the bind address inside the plugin or tunnel it).
- `connect_timeout=5` and `read_timeout=10` to widen the budgets for slow operations (e.g. `compile_blueprint` on a complex graph).

**Built-in end-to-end demo prompt.** Migration `0087_add_unrealer_demo_prompt.py` seeds a one-click demo into the Prompts table (`idPrompt=32`). Open the chat, click the **Prompts** dropdown, pick *Unreal MCP End-to-End Editor Drive*, and Tlamatini will execute ten guided steps spanning every command category — sanity-probe (`get_actors_in_level`), spawn a `StaticMeshActor` (`spawn_actor`), verify it (`find_actors_by_name`), scaffold a Blueprint (`create_blueprint`), add a `StaticMeshComponent` (`add_component_to_blueprint`), compile (`compile_blueprint`), spawn an instance (`spawn_blueprint_actor`), build a UMG HUD widget (`create_umg_widget_blueprint` → `add_text_block_to_widget` → `add_button_to_widget` → `add_widget_to_viewport`) — and render the result as a per-step HTML report table at the bottom of the answer. Use it as your smoke test the first time you wire the plugin up.

### 6.6. Using Unreal MCP on the canvas (the visual **Unrealer** node)

For unattended `.flw` workflows, drop the **Unrealer** sidebar agent onto the canvas. Each node sends exactly one Unreal command when its turn arrives. The node's `config.yaml` is the same one shipped under `agent/agents/unrealer/config.yaml`:

```yaml
host: 127.0.0.1
port: 55557
command: get_actors_in_level
params:
  name: ''
  type: ''
  location: []
  # ... (placeholders for the most common commands; the agent forwards
  #     whatever you put under params: verbatim, so add or remove keys
  #     to match the command verb you picked)
connect_timeout: 5
read_timeout: 10
source_agents: []
target_agents: []
```

The agent emits an `INI_SECTION_UNREALER<<<` block to its log, which means **Parametrizer can chain Unreal calls together**. Registered source fields (`agent/services/agent_contracts.py`): `host`, `port`, `command`, `status`, `error`, `response_body`. Canonical multi-step canvas pattern — create a Blueprint, compile it, spawn an instance:

```
Starter → Unrealer(create_blueprint) → Parametrizer → Unrealer(compile_blueprint)
       → Parametrizer → Unrealer(spawn_blueprint_actor) → Ender
```

Each Parametrizer copies the previous Unrealer's `response_body` (or a specific JSON field within it, via the Parametrizer dialog's interconnection-mapping UI) into the next Unrealer's `params` block. Branching on `status` (`ok` vs `error`) via a Raiser between Unrealer and the next Parametrizer gives you per-step exception handling — e.g., abort to a Notifier if `compile_blueprint` returns `status: error`.

### 6.7. What the agent actually does, end-to-end

The `unrealer.py` script (~120 lines of business logic, plus the standard pool-agent boilerplate) is **self-contained**: it does NOT import from `agent.acpx`, `agent.services`, or any other Tlamatini-internal package. Pool subprocesses run as separate Python interpreters with no `sys.path` back into the Django app, so the inline `UnrealConnection` adapter is a verbatim mirror of the upstream Unreal MCP Python client (with the FastMCP plumbing stripped out). Per execution:

1. **Load `config.yaml`**, read `host`, `port`, `command`, `params`, timeouts, and `target_agents`.
2. **Write `agent.pid`** so the orphan-process reaper (chapter 11) can track the run.
3. **Open a fresh TCP socket** to `host:port` with `TCP_NODELAY`, `SO_KEEPALIVE`, and 64 KB send/recv buffers. The Unreal MCP plugin closes the socket after each command, so the agent opens a new one per turn.
4. **Send** `json.dumps({"type": command, "params": params})` (no trailing newline) and call `recv()` until a complete JSON document has been assembled (validated by attempting `json.loads()` on the accumulated bytes after each chunk).
5. **Normalize** the response shape — `{"success": false, ...}` from older plugin builds is rewritten into `{"status": "error", "error": ...}` so downstream Parametrizer / Multi-Turn code can rely on a single shape.
6. **Emit one atomic `logging.info()` call** with the `INI_SECTION_UNREALER<<<` block (header: `host`, `port`, `command`, `status`, `error`; body: pretty-printed Unreal JSON response, capped at 64 KiB). Single-call emission is mandatory for the parser at `agent/agents/parametrizer/parametrizer.py`.
7. **Trigger `target_agents` even on error**, so the canvas can route on the `status` field instead of relying on agent-level fail-stops.
8. **Remove `agent.pid`** and exit.

Failure modes the adapter handles gracefully (each turns into `{"status": "error", "error": "<reason>"}` plus a non-fatal log line, never an uncaught exception):

- **Connection refused** — the plugin's TCP listener is not bound (editor not running, plugin not enabled, port mismatched).
- **Socket timeout during receive** — UE5's game thread is busy (e.g. `compile_blueprint` on a heavy graph) and exceeded `read_timeout`. Raise `read_timeout` in `config.yaml` or in the wrapped tool call.
- **Malformed JSON** — the plugin closed mid-write; logged as an `error` status and downstream agents still fire.

### 6.8. Exec Report integration

`chat_agent_unrealer` is registered in `_EXEC_REPORT_TOOLS` (`agent/mcp_agent.py`) under `agent_key="unrealer"` and `agent_display="Unrealer"`. When **Exec Report** is ticked alongside **Multi-Turn**, every Unreal call shows up as one row in a dedicated **List of Unrealer Operations** table at the bottom of the answer. Columns: command (left-bordered with the Unrealer caption gradient), success (`SUCCESS` / `FAILURE` derived from the underlying tool-call verdict — the same verdict Multi-Turn already uses for dedup and `tool_calls_log`). The table styling lives in `agent/static/agent/css/agent_page.css` (caption gradient mirrors `.canvas-item.unrealer-agent` in `agentic_control_panel.css`).

### 6.9. Bullet-proof checklist for Unreal Engine users

A short pre-flight you can copy into a sticky note before any session:

| Check | How |
|---|---|
| UE5 5.5+ open with a project loaded | `File → Project → <YourProject>` — and leave the editor focused, not minimized to the system tray |
| Plugin enabled | `Edit → Plugins → UnrealMCP → Enabled = ✓`, restart of editor confirmed |
| Listener bound | Output Log shows `UnrealMCP listening on 127.0.0.1:55557` (or your configured port) |
| Port not blocked | `Test-NetConnection -ComputerName 127.0.0.1 -Port 55557` returns `TcpTestSucceeded: True` (PowerShell) |
| Tlamatini server up | `python Tlamatini/manage.py runserver --noreload` shows the startup banner |
| **Multi-Turn** ticked | The toolbar checkbox to the left of **Exec Report** |
| Tool enabled | `Tools` dialog in chat shows `Chat-Agent-Unrealer` ticked (it ships ticked by default after migration `0086_add_chat_agent_unrealer_tool` runs) |

Then run the seeded **Unreal MCP End-to-End Editor Drive** demo prompt (idPrompt 32) as your smoke test. A clean run leaves three artifacts in your project: actor `TlamatiniProbe_Cube`, Blueprint `BP_TlamatiniProbe` with one spawned instance `TlamatiniProbe_Spawned`, and widget `/Game/UI/WBP_TlamatiniProbeHUD`. Delete them via right-click in the Content Browser when you are done.

### 6.10. Troubleshooting Unreal MCP

- **`acp_doctor` is not relevant here.** Unreal MCP is a *workflow-agent* surface, not the *ACPX* surface — the `acp_*` tools talk to external coding-agent CLIs (claude, gemini, …), not to UE5. The corresponding "is the channel alive?" probe for Unrealer is to call `chat_agent_unrealer` with `command='get_actors_in_level'` and check that `status == 'ok'`.
- **`status: error` / `Failed to connect to Unreal at 127.0.0.1:55557`.** The plugin is not listening. Check the UE5 Output Log for the `UnrealMCP listening on …` line. If the line is absent, the plugin is either disabled or failed to build (re-open the project; UE5 will re-prompt to rebuild). If the line is present but the connection still fails, your firewall is blocking loopback (rare on Windows, but `Restart-Service mpssvc` and re-test if you have aggressive endpoint security).
- **`Timeout receiving Unreal response`.** UE5's game thread is busy. Either widen `read_timeout` (`config.yaml` or the wrapped-tool call), or split the work into smaller commands (e.g. spawn 10 actors with 10 separate calls instead of one `spawn_n_actors` macro the plugin does not actually expose).
- **`status: error` from a Blueprint command, but the verb seems valid.** Capitalize the `parent_class` exactly as UE5 expects (`Actor`, `Pawn`, `Character`, `UserWidget`, …). The plugin does not auto-resolve `actor` → `Actor`.
- **Widget appears in the Content Browser but is invisible in PIE.** `add_widget_to_viewport` queues the widget at editor level; you still need to press **Play** in the editor (or call `add_widget_to_viewport` from within a running PIE session) to make it render. This is an Unreal MCP plugin behavior, not a Tlamatini bug.
- **The Output Log shows the plugin received the command but nothing happened in the level.** Most often: an actor spawn at a coordinate **inside** another object's collision volume. UE5 silently fails the spawn. Raise `params.location` by `[0, 0, 150]` and retry.
- **A second instance of UE5 is bound to the same port.** Only one UnrealMCP listener can bind to `127.0.0.1:55557` per host. Close the second editor instance, or configure each instance to bind to a different port and pass `port=<n>` per Unrealer call.

For the full debugging trail: pool-agent log lives at `<pool>/unrealer_<n>/unrealer_<n>.log`; chat-wrapped runs land under `agent/agents/pools/_chat_runs_/unrealer_<seq>_<id>/unrealer_<seq>_<id>.log`. Both contain the outbound JSON command and the inbound Unreal response verbatim.

---

## 7. Building a Frozen Distribution

For shipping a one-click Windows installer to end users.

### 7.1. Three-step pipeline

```
build.py  ──►  build_uninstaller.py  ──►  build_installer.py
   │                   │                         │
   ▼                   ▼                         ▼
pkg.zip          Uninstaller.exe        dist/Tlamatini_Release/
```

### 7.2. Step 1 — `build.py`

```bash
python build.py
```

Installs deps, runs `collectstatic`, executes PyInstaller, copies required payloads (including `README.md` and bundled `jd-cli/`), runs migrations, creates the default user (`user`/`changeme`), renames the exe to `Tlamatini.exe`, copies all 65 agent templates, bundles support scripts (`register_flw.ps1`, `CreateShortcut.ps1`, `Tlamatini.ps1`, `Tlamatini.ico`), and zips it all into **`pkg.zip`**.

`build.py` is strict: missing `README.md`, missing `jd-cli/`, or missing `jd-cli.bat` causes a non-zero exit.

### 7.3. Step 2 — `build_uninstaller.py`

```bash
python build_uninstaller.py
```

Builds `uninstall.py` into a single `--onefile` Tkinter exe. Output: `Uninstaller.exe` at the project root.

### 7.4. Step 3 — `build_installer.py`

```bash
python build_installer.py
```

Requires `pkg.zip` and `Uninstaller.exe`. Builds `install.py` with `--onedir --windowed` and a splash screen, copies `pkg.zip` and `Uninstaller.exe` into `dist/Installer/`, and assembles `dist/Tlamatini_Release/` with SHA-256 verification.

The final distributable is `dist/Tlamatini_Release/` — zip the folder, share it.

### 7.5. What the installer does on the end-user box

1. Tkinter GUI to choose installation directory (no admin needed).
2. Extracts `pkg.zip` into `<install_path>/Tlamatini/`.
3. Locks agent venv permissions.
4. Writes `config.json`.
5. Copies `Uninstaller.exe`.
6. Creates desktop and Start Menu shortcuts (`Tlamatini.lnk` — falls back to user-scoped paths under restrictive Group Policies).
7. Registers `.flw` to open with Tlamatini.
8. Cleans the PyInstaller bundle path from helper subprocess environments.

Frozen mode resolves `config.json` from the executable directory (or `CONFIG_PATH` env var). Template-agent discovery uses `<install_dir>/agents` in frozen mode and `Tlamatini/agent/agents/` in source mode. `_resolve_python_executable()` tries `PYTHON_HOME` → bundled `python.exe` → PATH.

### 7.6. Source mode vs Frozen mode: why flows still work

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

## 8. Configuration (`Tlamatini/agent/config.json`)

| Mode | Resolution order |
|---|---|
| Source | `Tlamatini/agent/config.json` |
| Frozen | `<install-dir>/config.json` next to the executable |
| Both | `CONFIG_PATH` env var wins over both |

### 8.1. LLM and unified-agent

```json
{
  "embeding-model": "Nomic-Embed-Text:latest",
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

### 8.2. RAG

Key knobs: `chunk_size` (3000), `chunk_overlap` (800), `k_vector` / `k_bm25` (100 each), `k_fused` (150), `enable_bm25`, `rrf_k` (60), `max_doc_chars` (150000), `max_context_chars` (250000), and a `context_budget_allocation` map (`high_relevance: 0.60, architecture: 0.20, related: 0.15, documentation: 0.05`). See `BookOfTlamatini.md` Part VII for the full schema.

### 8.3. ACPX

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

### 8.4. MCP services and other knobs

- `mcp_system_server_port` (8765), `mcp_files_search_server_port` (50051) — MCP daemons.
- `internet_classifier_model`, `web_summarizer_model`, `web_context_max_chars` — internet toggle.
- `image_interpreter_model`, `image_interpreter_base_url` — vision.
- `history_summary_*`, `keep_last_turns` — chat-history compression.

You no longer need to hand-edit all of those values. On `/agent/`, open `Config -> Models` or `Config -> URLs` to edit the most common runtime knobs in-place. The browser validates model strings / URLs / hosts / ports, the backend validates again, and `config_loader.save_config_updates()` atomically merges only the changed keys into the active `config.json`. The same loader path is used in source mode and frozen builds, so the chat UI and the executable stop drifting onto different config copies.

---

## 9. Architecture at a Glance

### 9.1. Big picture

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

### 9.2. The five layers

| Layer | Responsibility | Where |
|---|---|---|
| 1. Persisted toggles | DB rows for `Mcp` / `Tool` / `Agent` (UI enable/disable). | `agent/models.py` |
| 2. Runtime MCP services | System-Metrics (WebSocket) + Files-Search (gRPC) daemons. | `agent/mcp_*` |
| 3. Context fetcher chains | LCEL sidecars that inject system / files context. | `agent/chain_*_lcel.py` |
| 4. Main answer chains | Basic / History-aware / Unified. `factory.py` monkey-patches `invoke()`. | `agent/rag/chains/` |
| 5. Unified-agent tools | **72** synchronous `@tool` functions (20 core Python + 40 wrapped chat-agent + 12 ACPX/Skill). Active only in Multi-Turn. | `agent/tools.py` + `agent/chat_agent_registry.py` + `agent/acpx/` |

### 9.3. Multi-Turn execution pipeline

```
Frontend (toggles) → WebSocket → AgentConsumer → ask_rag() (skips prompt-shape validator)
  → UnifiedAgentChain.invoke() → filter_acpx_tools(tools, acpx_enabled)
    → planner picks ≤20 tools (capability scoring + history-aware boost)
      → MultiTurnToolAgentExecutor: 1..100 iterations of (LLM call → tool calls → ToolMessage)
        → Exec Report HTML appended (if exec_report_enabled, BEFORE save_message)
          → broadcast → frontend renders, shows Create Flow if all 4 gates pass
```

### 9.4. Agent contracts and the Flow Compiler

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

### 9.5. Agent catalog (the 65 types, by family)

| Family | Members |
|---|---|
| **Control** | Starter, Ender, Stopper, Cleaner, Sleeper, Croner |
| **Routing** | Raiser, Forker, Asker, Counter |
| **Logic gates** | OR, AND, Barrier |
| **Action** | Executer, Pythonxer, Prompter, Summarizer, Crawler, Googler, **Playwrighter**, Apirer, Gitter, Ssher, Scper, Dockerer, Kuberneter, Pser, Jenkinser, Sqler, Mongoxer, Mover, Deleter, Shoter, Mouser, Keyboarder, File-Creator, File-Interpreter, File-Extractor, Image-Interpreter, J-Decompiler, De-Compresser, Telegramer, TeleTlamatini, WhatsTlamatini, ACPXer, **Unrealer**, **Reviewer**, **Analyzer** |
| **Cryptography** | Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher (CRYSTALS-Kyber post-quantum) |
| **Utility** | Parametrizer, FlowBacker, Gatewayer, Gateway-Relayer, Node-Manager |
| **Terminal / monitoring** | Monitor-Log, Monitor-Netstat, Emailer, RecMailer, Notifier, Whatsapper, TelegramRX, FlowHypervisor |
| **AI / design** | FlowCreator |

Per-agent details (config knobs, lifecycle, naming convention, log markers): see `BookOfTlamatini.md` Part IV — *The Tlamatini Bestiary*. To add a new agent, follow `Tlamatini/.agents/workflows/create_new_agent.md` (8-step checklist).

---

## 10. Embedding-Memory Pre-Flight Guard (GPU hosts)

When you click **Set directory as context** in the Context menu, Tlamatini walks the directory, splits each file into chunks, and pushes every chunk through Ollama's embedding API to build a FAISS index. On a laptop / consumer GPU a heavy embedding model can occupy 75–95% of total VRAM by itself — and once a chat model is also resident the combined footprint exceeds available memory and the daemon thrashes RAM↔VRAM swap on every embed batch. A 30-second context-load turns into a multi-hour stall.

The **embedding-memory pre-flight guard** (`Tlamatini/agent/embedding_memory_guard.py`) catches this before the embed burst starts. It runs only when an NVIDIA GPU is detected; on CPU-only / AMD / Apple Silicon hosts it is a silent no-op and the legacy load path is unchanged.

### 10.1. Why this exists

The trigger case is the dev box this codebase is calibrated on: an **NVIDIA GeForce RTX 4070 Laptop GPU with 8 188 MiB** of VRAM. The previously-configured embedding model `qwen3-embedding:8b` (7.6 B parameters, Q4_K_M quantization) sits at **~6.24 GB resident** — 77.9% of total VRAM. Add the chat model and the daemon evicts something on every embed batch. The fix is either: switch to a smaller model (e.g. `nomic-embed-text:v1.5` at ~0.60 GB resident, 7% saturation) or accept the slow path knowingly. The guard surfaces the choice **before** the heavy work starts, so you can abort, swap the model in `config.json`, and restart Ollama — saving an hour of debugging "why is context loading frozen?".

### 10.2. How the check fires (the hook point)

The guard is wired into `agent/consumers.py::setup_contextual_rag_chain` at exactly one point: **after** the "loading context" banner is broadcast to the chat, **before** the heavy `asyncio.to_thread(setup_llm_with_context, …)` call that drives the embedding burst. The flow is:

```
WebSocket "set-directory-as-context"
    ↓
consumers.py:setup_contextual_rag_chain(path_only)
    ↓
broadcast MSG_AGENT_LOADING_CONTEXT chat bubble
    ↓
► embedding_memory_guard.check_embedding_memory_for_directory(...)
    │
    ├─► returns None (no GPU / under threshold / probe failed)
    │       → proceed silently
    │
    └─► returns warning dict
            → broadcast HTML warning chat bubble
            → proceed anyway (informational, non-blocking)
    ↓
asyncio.to_thread(setup_llm_with_context, ...)
    └─► OllamaEmbeddings + FAISS.from_documents(...)   ← VRAM burst
```

The check runs inside `asyncio.to_thread` so a slow `nvidia-smi` or cold `/api/show` call never blocks the Channels event loop. The whole block is wrapped in `try/except Exception` so any unhandled probe error prints a one-line `[EMBED-MEM] Pre-flight check skipped (fail-open)` to `tlamatini.log` and the load continues — **a diagnostic must never block the user**.

### 10.3. GPU detection and no-GPU behavior

The guard reuses the **already-cached** `nvidia-smi -L` probe from `agent/gpu_perf.py::_has_nvidia_gpu()` (introduced for the model-pinning hook). The probe runs at most once per process; subsequent calls hit the in-module cache. On CPU-only Linux/Windows, AMD GPUs, and Apple Silicon the probe returns `False` once at server start and **every subsequent call to the guard returns `None` immediately** — no subprocesses spawned, no HTTP calls made, no overhead.

This is the **portability guarantee**: a fresh `git pull` on a no-GPU box behaves *exactly* as before the guard existed. The 28 dedicated no-GPU compatibility tests (see 10.7) lock the contract in place.

### 10.4. Three-tier VRAM prediction

When the GPU gate passes, the guard predicts the embedding model's resident VRAM in priority order:

| Tier | Source | Trigger | Accuracy |
|---|---|---|---|
| **A** | `GET /api/ps` `size_vram` | Model already resident in Ollama | **Exact** — verbatim daemon value |
| **B** | `POST /api/show` → `parameter_count × bits_per_weight × overhead` | Model pulled but unloaded | ±5% on calibrated models |
| **C** | (any probe failure) | Ollama down, model not pulled, cloud model (`:cloud` suffix) | Returns `None` → fail-open |

Tier B uses a standard llama.cpp / GGUF bits-per-weight table:

| Quant | Bits/weight | Quant | Bits/weight |
|---|---|---|---|
| `F32` | 32.0 | `Q4_K_M` | 4.83 |
| `F16` / `BF16` | 16.0 | `Q4_K_S` | 4.58 |
| `Q8_0` | 8.5 | `Q4_0` | 4.55 |
| `Q6_K` | 6.56 | `Q3_K_M` | 3.91 |
| `Q5_K_M` | 5.69 | `Q2_K` | 2.96 |

Unknown quants fall back to a conservative `5.0` bits/weight. The overhead multiplier accounts for KV cache + activation buffers + GGML allocator slack:

- **`× 1.40`** for models with **≥ 1 B parameters** (large-model regime)
- **`× 2.20`** for **sub-1 B** models (proportionally larger KV/buffer overhead)

Calibration against live measurements on the RTX 4070 Laptop:

| Model | Params × bits/8 (raw) | Predicted (× overhead) | Measured resident | Error |
|---|---|---|---|---|
| `qwen3-embedding:8b` (Q4_K_M) | 4.54 GB | **6.36 GB** (× 1.40) | 6.24 GB | +1.9% |
| `Nomic-Embed-Text:latest` (F16) | 274 MB | **603 MB** (× 2.20) | 600 MB | +0.5% |

Tier B also pulls the **embedding dimension** from `/api/show` via any architecture-prefixed `*.embedding_length` key (e.g. `qwen3.embedding_length=4096`, `nomic-bert.embedding_length=768`). Combined with a directory pre-scan that mirrors the exclusion rules of `agent/rag/factory.py::CustomTextLoader`, it reports a **projected FAISS-index RAM size** (`num_chunks × embedding_dim × 4` bytes, float32). This is RAM, not VRAM, but useful to surface on directories with hundreds of thousands of chunks.

### 10.5. The 80% threshold and the chat-bubble warning

The guard fires when **predicted_vram ≥ 0.80 × smallest-GPU total VRAM**. Why the smallest GPU (rather than the sum or the largest)? Because Ollama loads each model into a **single device** — using the max would silently under-report the constraint on heterogeneous multi-GPU rigs.

When the threshold is crossed, the guard returns a structured dict the consumer renders as an HTML chat bubble. A real example from this dev box (artificially threshold-lowered to 70% so qwen3-embed:8b trips):

```
⚠️ Embedding-memory warning
Embedding model qwen3-embedding:8b needs ~6,378 MiB of VRAM
(currently resident in VRAM), which is 77.9% of the smallest
GPU's total (8,188 MiB) — above the safety threshold of 70%.
Projected FAISS vector store (RAM, not VRAM): ~28 MiB across
1,847 chunks at dim 4096.
Context loading will continue, but expect slow embedding
throughput or RAM↔VRAM swap. To eliminate the pressure, switch
embeding-model in config.json to a smaller model
(e.g. nomic-embed-text:v1.5) and restart.
```

The message is **informational and non-blocking** — context loading proceeds. The user picks whether to wait it out, hit Cancel, or change models. The phrasing names the exact `config.json` key (`embeding-model`, with the spelling preserved from the existing codebase) and a concrete alternative.

### 10.6. Tuning, overrides, and what the guard does NOT do

| Knob | Where | Default | When to change |
|---|---|---|---|
| Trigger threshold | `check_embedding_memory_for_directory(..., threshold=)` | `0.80` | Pass `0.70` on smaller GPUs (6 GB cards) where 80% is already too tight. |
| Large-model overhead | `_OVERHEAD_LARGE` constant | `1.40` | If a new model family proves the calibration off by > 10%, recalibrate against `/api/ps` and bump the constant. |
| Small-model overhead | `_OVERHEAD_SMALL` constant | `2.20` | Same calibration story for sub-1B models. |
| Bits/weight table | `_QUANT_BITS` dict | `Q4_K_M=4.83` (etc.) | Add new entries when a future GGUF quant ships. |

What the guard **does NOT** do, by deliberate choice:

- It does **not** abort context loading. The warning is informational. (If you want abort-on-warning behavior, wire a confirm/cancel WebSocket round-trip — the surface is described in `agent_page_init.js` near `set-dir-context`.)
- It does **not** estimate the **chat** model's VRAM. Only the embedding model is checked, because that is the model the directory-load path forces into VRAM. The chat model is handled by `gpu_perf.pin_ollama_model` separately.
- It does **not** persist warnings. Each context-load runs an independent check.
- It does **not** call `nvidia-smi` on CPU-only hosts. Both gates (`_has_nvidia_gpu_cached` and the `_gpu_total_memory_bytes` query) short-circuit before any subprocess spawn.
- It does **not** add new dependencies. `subprocess`, `urllib.request`, and `os.walk` are the only stdlib touchpoints — the same surface `agent/gpu_perf.py` already uses.

### 10.7. Test coverage

The guard ships with **49 automated tests** in `Tlamatini/agent/test_embedding_memory_guard.py`, split into seven `SimpleTestCase` classes:

| Test class | Count | What it pins |
|---|---|---|
| `QuantTableTests` | 2 | Known quants resolve to standard bits/weight; unknown quants fall back to the conservative default. |
| `PredictFromShowTests` | 3 | Tier-B prediction lands within calibrated bounds for both 7.6 B and 137 M reference models. |
| `EmbeddingDimExtractionTests` | 2 | The dim key is found regardless of architecture prefix (`qwen3.`, `nomic-bert.`, future archs). |
| `ChunkEstimatorTests` | 4 | Directory walk honors default + user omissions, respects `max_chunks_per_file`, and handles single-file mode. |
| `GuardEntryPointTests` | 8 | All entry-point branches: no-GPU, cloud, threshold gate, Tier A `/api/ps`, Tier B `/api/show`, probe failure. |
| `FormatMessageTests` | 2 | HTML renders the model name, percent, threshold, and chunk count. |
| **`NoGpuCompatibilityTests`** | **28** | **Every no-GPU failure mode — see breakdown below.** |

The `NoGpuCompatibilityTests` class is the portability proof. Its coverage matrix:

| Failure mode | Tests |
|---|---|
| Module import on no-GPU host has no side effects | `test_module_imports_without_side_effects` |
| `nvidia-smi` binary missing entirely | `test_run_cmd_returns_127_for_real_missing_binary`, `test_total_vram_returns_none_when_nvidia_smi_missing` |
| `nvidia-smi` exists but driver unloaded | `test_total_vram_returns_none_when_driver_unloaded` |
| `nvidia-smi` times out / crashes | `test_run_cmd_absorbs_timeout` / `..._permission_error` / `..._generic_oserror` |
| `nvidia-smi` returns empty or garbage output | `test_total_vram_returns_none_on_empty_output` / `..._on_unparseable_output` |
| Heterogeneous multi-GPU rig | `test_total_vram_picks_smallest_gpu_in_heterogeneous_rig` |
| `gpu_perf` module missing / its probe raises | `test_has_nvidia_gpu_falls_back_when_gpu_perf_unimportable`, `test_has_nvidia_gpu_returns_false_when_gpu_perf_probe_raises` |
| Ollama daemon offline (closed port) | `test_ollama_show_returns_none_against_closed_port`, `test_ollama_ps_returns_none_against_closed_port` |
| Malformed Ollama URLs / empty args | `test_ollama_show_returns_none_for_garbage_url` |
| Model not in `/api/ps` | `test_ollama_loaded_vram_returns_none_when_model_not_in_ps`, `..._when_ps_fails` |
| Entry on a CPU-only host | `test_check_returns_none_on_cpu_only_host` |
| GPU detected but `--query-gpu` fails | `test_check_returns_none_when_nvidia_smi_query_fails` |
| GPU detected but Ollama offline | `test_check_returns_none_when_ollama_offline` |
| Pathological 0 MiB GPU reading | `test_check_returns_none_when_gpu_zero_total` |
| Empty `ollama_base_url` in config | `test_check_returns_none_for_empty_base_url` |
| Deleted / nonexistent / empty path | 3× `test_chunk_estimator_*` + `test_check_with_nonexistent_path_does_not_crash` |
| Unreadable file inside the walked tree | `test_chunk_estimator_with_unreadable_file_skips_it` |
| Partial warning dict (missing optional keys) | `test_format_warning_message_handles_missing_optional_keys` |
| **Live portability proof (real subprocess + real urllib)** | **`test_real_entry_point_call_never_raises`** |

`test_real_entry_point_call_never_raises` is the CI gate: it makes the *actual* `subprocess.run(["nvidia-smi", ...])` and `urlopen("http://127.0.0.1:11434/...")` calls against whatever the runner offers, and asserts the return is **either** `None` **or** a well-formed warning dict — never an exception. The same test passes on this RTX 4070 dev box (returns `None` because qwen3-embed sits at 77.9%, under the 80% gate) and on a CPU-only CI image (returns `None` because the GPU gate fails fast).

Run them yourself:

```bash
cd Tlamatini
python manage.py test agent.test_embedding_memory_guard --verbosity=2
# 49 tests in ~2.3 s, no DB setup, no GPU required.
```

---

## 11. Orphan-Process Cleanup (`conhost.exe` reaper)

Tlamatini now ships a three-tier reaper (`Tlamatini/agent/orphan_reaper.py`) that cleans up the console-host children every console subprocess on Windows drags behind it. Without this pass, users were occasionally seeing `conhost.exe` processes lingering in Task Manager **with the Tlamatini icon** — the icon is inherited from the parent EXE that spawned the console — and reasonably concluding that Tlamatini was leaking processes.

### 11.1. The problem this solves

On Windows, when a tool (`execute_command`, `chat_agent_executer`, an ACPX CLI child, an agent-pool Python subprocess, …) spawns a console child, Windows allocates a `conhost.exe` companion to host that console. If the immediate parent dies before the OS reaps the console pair, that `conhost.exe` outlives Tlamatini. Two compounding causes were closed at once:

- **The reaper itself** sweeps zombies and orphaned console hosts at three lifecycle points (below).
- **Spawn sites were hardened** — `views.py::execute_starter_agent_view`, `execute_ender_agent_view`, `restart_agent_view`, `execute_flowcreator_view`, every ACPX child in `acpx/runtime.py`, and a `subprocess.Popen.__init__` guard at the top of `agents/ender/ender.py` (mirrored across every other pool agent) now spawn with `CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` and stdio piped to `DEVNULL`. No console is allocated in the first place, so no `conhost.exe` companion exists to orphan.

### 11.2. The three tiers

| Tier | When it runs | Scope | Visibility |
|---|---|---|---|
| **Tier 1** | After every Multi-Turn tool call that may have spawned a child (`execute_command`, `execute_file`, `unzip_file`, `decompile_java`, `googler`, `agent_starter/stopper/parametrizer`, every `chat_agent_*`, every `acp_*`). Driven by `MultiTurnToolAgentExecutor._reap_after_tool()` in `agent/mcp_agent.py`. Also fires on the tool-exception path so a crashed tool still gets cleaned up. | Dead/zombie descendants of the current PID, plus orphaned `conhost.exe` whose parent is gone. Pool-cmdline scan is skipped here (cheap path). | Silent. Survivors accumulate on the executor for Tier 2 to surface. |
| **Tier 2** | Once, right after the final answer is broadcast to the user. Driven by `AgentConsumer._tier2_orphan_sweep()` in `agent/consumers.py`. Runs in a thread (so it doesn't block the WebSocket loop) and merges its survivors with Tier 1's leftovers (de-duped by PID). | Same as Tier 1 plus the **agent-pool cmdline scan** (kills processes whose `cmdline` references `agents/pools/...` but are not tracked by `AgentProcess` / `ChatAgentRun` anymore). | If anything survives BOTH tiers, the consumer sends a **second chat message** listing every surviving `name + PID` pair so the user can end them manually from Task Manager. |
| **Tier 3** | At Tlamatini.exe shutdown — `AgentConfig.ready()` registers it on the same `atexit` / SIGINT / SIGBREAK path that already cleans up pools. | Full sweep (self-tree + pool cmdline + console-host orphans). | Logs `--- [Tier-3 reaper] killed=… survivors=… errors=…` to `tlamatini.log`. Survivors are listed by `name (PID)` so a post-mortem reader can audit what refused to die. |

### 11.3. What gets reaped (and what does not)

A process is considered a "Tlamatini orphan" if **any** of the following hold:

- It is a descendant of the current Tlamatini PID and its status is `ZOMBIE` / `DEAD`.
- It is a `conhost.exe` / `openconsole.exe` whose parent PID is in our process tree, OR whose parent PID no longer exists.
- Its `cmdline` references the agent-pool directory (`agents/pools/...` or `agents/pools/_chat_runs_/...`) but it is no longer tracked.

Each candidate is escalated `terminate → wait 1 s → kill` via `psutil`; an "unable-to-kill" outcome surfaces as a survivor, never as an exception. The reaper **never raises into the caller** — a cleanup that crashes the chat path would be worse than the orphans it tries to kill.

Out of scope on purpose: console hosts spawned by unrelated processes (a different IDE, your shell, another app's child) — the parentage check keeps the sweep narrow.

### 11.4. The user-visible follow-up message

When Tier 2 detects survivors, the user sees a second chat bubble immediately after the main answer:

```
⚠ Heads-up: Tlamatini tried to clean up after this request but the following
process(es) refused to terminate. They are most likely harmless leftovers from
a tool you ran, but if you do not recognize them please end them manually from
Task Manager so no Tlamatini-spawned child outlives the app:
  • conhost.exe — PID 18244
  • python.exe — PID 19108
```

The rendering helper is `orphan_reaper.format_survivors_message()`; it returns `None` (so no extra message is sent) when the survivor list is empty, which is the common case after the spawn-site hardening landed.

---

## 12. Troubleshooting

### 12.1. Ollama / models

- "connection refused" → `ollama serve` in a dedicated terminal. Check `ollama_base_url`.
- Model not found → `ollama list` to see what's pulled. Pull the missing tag.
- Remote Ollama → set `ollama_token` for bearer auth.

### 12.2. RAG / context

- Set-Context shows no green banner → check file permissions, ensure files are text not binary.
- "Out of memory" during embedding → fallback mode kicks in; retrieval quality drops, files still accessible. Switch to a smaller embedding model. **See chapter 10 — the embedding-memory pre-flight guard now warns you about this *before* the embed burst starts on GPU hosts.**
- Hit `max_doc_chars` → bump it.
- Session says it was restored after a refresh, but the input stays disabled briefly → that is expected while the contextual RAG chain rebuilds. Wait for the ready state / spinner to clear before sending the next prompt.

### 12.3. Multi-Turn / planner

- Did you tick **Multi-Turn**? Is `enable_unified_agent: true`?
- "Tool X is not available" → the planner did not bind X. Check `[Planner._select]` console lines, add matching keywords to your prompt, or raise `max_selected_tools`.
- 100 iterations exhausted → likely a busy-poll loop. Use `chat_agent_sleeper` / `chat_agent_run_wait` instead.

### 12.4. Chat-created flows and ACP validation

- **Create Flow downloads a `.flw`, but it looks simpler than the chat transcript.** That is normal. The file stores the flow structure, node config, connections, and artifacts. It does not store the entire conversation.
- **Create Flow fails from the chat.** The browser first asks `/agent/flow_from_tool_calls/` to normalize the draft. If that endpoint fails, the frontend falls back to the older browser-only export so you do not lose the flow draft.
- **A TeleTlamatini or WhatsTlamatini flow is missing passwords or tokens after export.** That is intentional. Known secret fields are redacted when the chat exports a flow. Re-enter secrets in the agent config before running the flow.
- **Validate shows stale connections.** Validate now asks `/agent/compile_flow/` for a dry-run compile of the live canvas instead of trusting whatever is already in the pool. If the canvas still looks wrong, save the `.flw`, reload it, and check the browser console for a compile error.
- **Start runs an older version of the flow.** Start now compiles the visible canvas in write mode before launching. If you still see old behavior, clear the pool from the ACP close/clear controls, load the `.flw` again, and run Validate once before Start.
- **A value I set in an agent dialog disappears after Validate or Start.** Current builds preserve explicit dialog edits and merge canvas-derived wiring on top of them. If something still looks wrong, reopen the dialog, save once more, then run Validate and inspect the compile warnings.
- **Parametrizer mappings disappear after reload.** Save the flow after creating mappings. New `.flw` files store mappings under `artifacts.parametrizerMappings`, and the loader restores them into each Parametrizer node.

### 12.5. ACPX / external CLIs

- `acp_doctor` says agent not resolvable → CLI not on `PATH`, or set `acpx.agents.<id>.command` to the absolute path.
- Transcript only shows outbound prompts on Windows → your build is older than May 2026. Update — fix is `transport="oneshot-prompt"` for claude/gemini/cursor/qwen/codex.
- API key not picked up → per-agent `acpx.agents.<id>.env` wins over exported shell vars; check both.
- Session left running → always end with `acp_kill`. If a request times out, manually `acp_list_sessions` + `acp_kill`.

### 12.6. Frozen build / installer

- Wrong config used → place `config.json` next to the exe, or set `CONFIG_PATH`.
- Missing templates → verify `agents/` exists in the install. Rebuild if `README.md`, `jd-cli/`, or template directories are missing.
- Restrictive Group Policy blocks shortcuts → `CreateShortcut.ps1` falls back to user-scoped Desktop / Start Menu paths.

### 12.7. Logs to consult first

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

## 13. Versioning

Tlamatini follows [Semantic Versioning 2.0.0](https://semver.org/) — `MAJOR.MINOR.PATCH` — with **git tags as the single source of truth**. You never hand-edit a version string anywhere in the codebase; you tag, then you build, and the three build scripts bake the resolved value into every artefact.

### 13.1. The bump rules

| Component | Bump when… | Example |
|---|---|---|
| **MAJOR** | A change breaks something users already shipped — `.flw` schema, Agent Contract, public endpoint URL, LLM tool name. | `1.x.x` → `2.0.0` |
| **MINOR** | You add a backward-compatible feature — a new agent type, toolbar checkbox, SKILL package, endpoint, optional API field. | `1.2.0` → `1.3.0` |
| **PATCH** | You ship a backward-compatible bug fix — regression closed, contract intact. | `1.2.0` → `1.2.1` |

Pre-releases use the standard SemVer suffixes — `2.0.0-alpha.1`, `2.0.0-beta.1`, `2.0.0-rc.1` — and sort **before** the final release.

### 13.2. Cutting a release

```powershell
git tag -a v1.5.0 -m "Release 1.5.0: <one-line summary>"
git push origin v1.5.0
python build.py
python build_uninstaller.py
python build_installer.py
```

All three build scripts pick the tag up from `git describe --tags` automatically. The artefact lands in `dist/Tlamatini_Release_v1.5.0/`.

### 13.3. Where you can see the running version

| Surface | Example |
|---|---|
| About dialog | `Tlamatini v1.5.0` |
| Startup banner (console + `tlamatini.log`) | `--- [VERSION] Tlamatini 1.5.0` |
| HTTP endpoint (open, usable as a health-check) | `GET /agent/version/` → `{"version":"1.5.0","commit":"abc1234", …}` |
| Win32 properties on `Tlamatini.exe` / `Installer.exe` / `Uninstaller.exe` | Right-click → Properties → Details → ProductVersion |

All four are computed from the same `Tlamatini/agent/_version.py` that `build.py` writes (gitignored, regenerated on every build).

### 13.4. Building without tagging (development)

The build never fails for "no version" — and the version surface is always a clean SemVer like `1.1.1`. The resolver returns the **bare base tag** reachable from HEAD; distance / commit / dirty state are deliberately stripped:

| Situation | Version baked in |
|---|---|
| HEAD exactly on `v1.2.0` | `1.2.0` |
| 17 commits past `v1.2.0`, clean tree | `1.2.0` |
| 17 commits past `v1.2.0`, uncommitted edits | `1.2.0` |
| No tags at all | `0.0.0` |
| Not a git repo | `0.0.0+unknown` |

No `.devN`, no `+gSHA`, no `.dirty` ever appears in the version string — those concerns stay in git (`git status`, `git describe --long --dirty`).

### 13.5. Overriding the resolved version

| # | Source | Use case |
|---|---|---|
| 1 (highest) | `python build.py --version 2.0.0-rc.1` | Local RC build before tagging |
| 2 | `$env:TLAMATINI_VERSION = "1.5.0"; python build.py` | CI pipelines |
| 3 | `git tag -a v1.5.0 …` (then build) | The normal release path |
| 4 (lowest) | _(none — sentinel `0.0.0+unknown`)_ | Running from a download zip with no git |

`build.py` exports `$env:TLAMATINI_VERSION` after resolving, so `build_installer.py` and `build_uninstaller.py` in the same shell see the same value — the three artefacts cannot disagree.

The full contract — release recovery, runtime resolver internals, file-by-file integration map, FAQ — lives in [`VERSIONING.md`](VERSIONING.md).

---

## 14. Contributing & License

### 14.1. Contributing

1. Fork; create a feature branch.
2. Follow PEP 8. Run `python -m ruff check` and `npm run lint` before pushing.
3. Add tests in `Tlamatini/agent/tests.py` (the suite has 266+ tests; the bar is "zero regressions, ruff clean").
4. Update docs when API or behavior changes — this README, `docs/claude/*.md`, and `agent/agents/flowcreator/agentic_skill.md` for new agents.
5. Open a PR with a clear description.

When adding a new agent, follow the 8-step checklist in `Tlamatini/.agents/workflows/create_new_agent.md` (backend script + view + migration + CSS gradient + 4 JS files + agentic_skill.md + README + lint).

### 14.2. Acknowledgments

[Django](https://www.djangoproject.com/) · [LangChain](https://github.com/langchain-ai/langchain) · [LangGraph](https://github.com/langchain-ai/langgraph) · [Ollama](https://ollama.ai/) · [FAISS](https://github.com/facebookresearch/faiss) · [Anthropic](https://www.anthropic.com/) · [Bootstrap](https://getbootstrap.com/) · [TextMeBot](https://textmebot.com/) · [Ruff](https://github.com/astral-sh/ruff) · [PyAutoGUI](https://github.com/asweigart/pyautogui) · [JD-CLI](https://github.com/intoolswetrust/jd-cli)

### 14.3. License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

---

*For the long-form, narrative documentation (full agent bestiary, complete WebSocket / HTTP API reference, glossary, full changelog, architecture deep dives), see [`BookOfTlamatini.md`](BookOfTlamatini.md). For support, open an issue on GitHub.*
