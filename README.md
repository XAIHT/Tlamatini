<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
<p align="center">
  <img src="Tlamatini.jpg" alt="Tlamatini" width="180" height="180" />
</p>

<h1 align="center">Tlamatini</h1>

<p align="center">
  <b>The local-first AI developer assistant with a visual workflow designer — and the reach to touch hardware, 3D engines, and any external tool.</b><br/>
  <i>"one who knows" — it doesn't just edit code. It flashes your board, drives your engine, and orchestrates whole agent workflows on a canvas. On your machine.</i>
</p>

<p align="center">
  <b>💰 About $200 a YEAR — not $200 a MONTH.</b><br/>
  Frontier plans like GPT-5.4 or Claude Opus cost about <b>$200 per month</b>. <b>Tlamatini is free and open-source</b> — your only bill is <b>Ollama Pro (~$200 a <i>year</i>, paid to Ollama, not us)</b>, and on top of it she stacks <b>82 agent types and 75+ tools</b>: comparable power for about <b>one twelfth</b> the price, all on your own machine.
</p>

<p align="center">
  <a href="https://discord.gg/WFQsrskgc"><img src="https://img.shields.io/badge/DISCORD-JOIN%20US-5865F2?style=for-the-badge&labelColor=2D2D2D&logo=discord&logoColor=white" alt="Join our Discord"/></a>
  <a href="https://github.com/XAIHT/Tlamatini/releases/tag/v1.32.0"><img src="https://img.shields.io/badge/VERSION-v1.32.0-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="Version"/></a>
  <a href="https://www.python.org/downloads/release/python-31210/"><img src="https://img.shields.io/badge/PYTHON-3.12.10-3776AB?style=for-the-badge&labelColor=2D2D2D&logo=python&logoColor=white" alt="Python"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/PLATFORM-WIN%2010%20%7C%2011-0078D6?style=for-the-badge&labelColor=2D2D2D&logo=windows&logoColor=white" alt="Platform"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/AGENT%20TYPES-82-8A2BE2?style=for-the-badge&labelColor=2D2D2D" alt="82 agent types"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/TOOLS-75-16A34A?style=for-the-badge&labelColor=2D2D2D" alt="75 tools"/></a>
  <a href="https://github.com/XAIHT/Tlamatini/blob/main/LICENSE"><img src="https://img.shields.io/badge/LICENSE-MIT-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="License"/></a>
</p>

<p align="center">
  <a href="https://xaiht.org">🌐 Website</a> ·
  <a href="https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s">▶️ One-minute teaser</a> ·
  <a href="https://github.com/XAIHT/Tlamatini/blob/main/BookOfTlamatini.md">📖 Full docs</a> ·
  <a href="https://discord.gg/WFQsrskgc">💬 Discord</a>
</p>

<p align="center">
  <b>💬 <a href="https://discord.gg/WFQsrskgc">Join the Tlamatini community on Discord</a></b> — get help, show what you build, report bugs, and shape the roadmap.
</p>

---

## 🚀 Get started — 5 steps to a cloud-powered Tlamatini

The whole idea in one line: **don't pay $200 a month for a frontier model.** **Tlamatini is free** — your only cost is **Ollama Pro (~$200 a year, paid to Ollama, not us)**; point Tlamatini at it and drive **82 agent types and 75+ tools** from your own machine. Here's the full setup.

### 1 · Install Tlamatini

Pick **one** of two paths. **Tlamatini itself is free** — you never pay us; the only cost is Ollama (Step 3).

#### 🟢 Option A — Release installer (recommended · no Python needed)

Best for most people. The installer bundles its own **Python 3.12.10** and every dependency, so you install nothing else.

1. Open the **[Releases page](https://github.com/XAIHT/Tlamatini/releases)** and download the latest installer (`.exe`).
2. Run it and follow the wizard.
3. Launch **Tlamatini** from the Start-menu shortcut.
4. Your browser opens at **`http://127.0.0.1:8000/`** — log in with **user / changeme**.

> 🔄 Updating later is one click: **About ▸ Check for updates** inside the app — it keeps your config, database, and keys.

#### 🔵 Option B — From source (for developers)

Best if you want to read, modify, or contribute to the code. Requires **Python 3.12.10** and **git** already installed.

```bash
git clone https://github.com/XAIHT/Tlamatini.git
cd Tlamatini
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python Tlamatini/manage.py migrate
python Tlamatini/manage.py runserver --noreload
# then open http://127.0.0.1:8000/   (default login: user / changeme)
```

### 2 · Install Ollama

Install **[Ollama](https://ollama.com/download)** for Windows. Ollama is the engine that serves every model to Tlamatini — the local embedding model **and** the cloud chat models.

### 3 · Subscribe to Ollama Pro (~$200 / year)

Go to **[ollama.com](https://ollama.com)**, sign in, and take the **Ollama Pro** plan (about **$200 per year**). Pro unlocks the **`:cloud` models** — frontier-class models that run on Ollama's servers — for a *yearly* price close to what one frontier subscription costs in a *single month*. Then connect your machine:

```bash
ollama signin
```

### 4 · Download the models

Pull the small local embedding model, plus the cloud chat models Tlamatini will use:

```bash
# Local embedding model (small, runs on your own GPU/CPU)
ollama pull nomic-embed-text

# Cloud models (served by Ollama Pro) — pull, or just sign in to use
ollama pull kimi-k2.7-code:cloud
ollama pull qwen3.5:cloud
```

Any cloud model works — these are the exact ones shown in the screenshots below.

### 5 · Point Tlamatini at the models

In the Tlamatini navbar, open the **Config** menu:

<p align="center"><img src="Tlamatini/agent/images/MenuConfig.jpg" alt="Config menu — Models, URLs, Access Keys Wizard" width="420"/></p>

**a) Config ▸ Models** — set the Ollama model for each subsystem (each one must already exist in your Ollama catalog), then click **Save**:

<p align="center"><img src="Tlamatini/agent/images/ConfigureModels.jpg" alt="Configure Models dialog" width="480"/></p>

**b) Config ▸ Access Keys Wizard** — whether you need an **Ollama token** depends on *where* Ollama runs:

> - 🖥️ **Ollama on your own machine (localhost)?** Leave the token **blank** — a local Ollama needs no auth.
> - ☁️ **Ollama on a remote server (e.g. [Vast.ai](https://vast.ai))?** Paste the **Ollama token** so Tlamatini can reach it.

Add any cloud-CLI keys here too. Blank fields keep what's already configured; click **Save**:

<p align="center"><img src="Tlamatini/agent/images/ACPXKeysConfigureWizard.jpg" alt="Access Keys Wizard" width="640"/></p>

Done — tick **Multi-Turn** in the chat toolbar and put Tlamatini to work.

---

> **📹 [ Drop a 15-second GIF here ]** — flashing a board from a prompt, or wiring agent types on the canvas and hitting Start. One real GIF up top sells this faster than anything written below.

---

## 💎 The jewels — what nothing else can do

Claude Code, Codex, Cursor, Gemini — they edit text files. Tlamatini does that **and** reaches into the physical and creative world, then lets you *wire it all together visually*:

| | Capability | Why it's rare |
|---|---|---|
| 🎮 | **Unreal Engine control** | Drive the engine/editor from chat — no other coding agent touches it. |
| 🎬 | **Blender control** | Scene, object, render, and code execution over the official Blender MCP socket. |
| 🔌 | **Universal External-MCP handling** | Connect to **any** external MCP server (stdio · streamable-http · sse · websocket), up to 5 at once, and use its tools instantly. One client for the whole MCP ecosystem. |
| 🛠️ | **Modify entire software projects** | Read, grep, refactor, edit, and rebuild whole codebases — not just single files — with hybrid RAG grounding. |
| 🛡️ | **Security assessments** | Authorized Kali Linux / pentest runbooks + code security-audit skills, driven from chat. |
| 📟 | **STM32 · ESP32 · Arduino firmware** | Scaffold → build → **flash a real connected board** → read serial, with a safety preflight that refuses mis-targeted firmware. |
| 🧩 | **A VISUAL WORKFLOW DESIGNER** | **82 drag-and-drop agent types** on a canvas you wire into runnable, savable `.flw` flows. *No other coding agent — Claude Code, Codex, none of them — gives you this.* This is the crown jewel. |

> **The headline no competitor can copy:** Tlamatini is the only local-first AI dev assistant where you *design the agent workflow visually*, then have it flash firmware, drive Unreal/Blender, run security tools, and command any external MCP — all from one machine.

---

## 🔒 And it's yours alone

Embeddings and chat run on your local [Ollama](https://ollama.com) install. Cloud models (Claude API, Ollama Pro/Max) and delegation to cloud CLIs are **opt-in, per request, never the default.** Your code and firmware never leave the box unless you route them out yourself.

## ⚠️ Agent-directory disclaimer: user jurisdiction and responsibility

The workflow agents in `Tlamatini/agent/agents/` are plain-Python programs on purpose: they are readable, editable, auditable operating code under the user's control. When you enable, configure, modify, chain, or run those agents, their actions fall under **your jurisdiction**. The prompts, config files, secrets, credentials, files, folders, network targets, browsers, shells, APIs, external MCP servers, hardware devices, and downstream systems they touch are selected and authorized by you.

Tlamatini provides orchestration, documentation, and guardrails, but it cannot guarantee that every user-edited agent, workflow, external service, credential scope, target machine, or local environment is safe. **Any security breach, data exposure, unauthorized action, credential leak, unsafe automation, policy violation, device damage, or other harm caused by running agents or agent workflows is the responsibility of the user who runs them.** Audit agents before use, restrict credentials and permissions, and operate them only on systems where you have explicit authorization.

---

## 📋 The full capability list

Everything Tlamatini can do, grouped:

**🧩 Orchestration & design**
- **Visual Workflow Designer (ACP)** — 82 drag-and-drop agent types wired into runnable flows; save/load `.flw` files; Flow Compiler validates the canvas into `config.yaml`.
- **Multi-Turn orchestration** — a tool-calling loop with **75 tools** and a global execution planner; **Step-by-Step** mode paces hands-on setup one action at a time.
- **FlowCreator / FlowHypervisor** — let an LLM design a flow; a watchdog monitors flow health.
- **Parametrizer / Gatewayer / Gateway-Relayer / Node Manager** — chain agent outputs into the next agent's config; trigger flows from webhooks, folder-drops, or GitHub/GitLab.
- **ACPX** — spawn external coding-agent CLIs (Claude Code, Codex, Cursor, Gemini, Qwen, and more) as tools and relay between them.

**📟 Firmware & hardware**
- **STM32er** — zero-config STM32 build/flash/observe with a critical-mission safety preflight.
- **ESP32er** — direct PlatformIO build/flash/monitor, zero-config bootstrap.
- **Arduiner** — direct `arduino-cli`, auto-installs binary + core, build/upload.
- **ESPHomer** — ESPHome smart-home device configs (YAML, no C++), zero-config.

**🎬 3D & creative engines**
- **Unrealer** — Unreal Engine control from chat.
- **Blenderer** — Blender scene/object/render/code over the official MCP socket.

**🛠️ Code & projects**
- **Editor / Grepper / Globber** — surgical find-and-replace, regex content search, filename glob (Claude-Edit/Grep/Glob equivalents).
- **File-Creator / Mover / Deleter / File-Interpreter / File-Extractor** — create, move, delete, read-and-interpret, extract from PDF/DOCX.
- **Executer / Pythonxer** — run shell commands and gated Python.
- **Gitter** — full git control. **Googler** — web search + extract.
- **Hybrid RAG** — FAISS + BM25 retrieval, metadata extraction, context budgeting, grounded in your codebase.
- **Skills** — `SKILL.md` packages: code-review, security-audit, kali-pentest, flow-making, skill-creator, summarize, audit/lint/refactor helpers, and integration stubs (GitHub, Gmail, Slack, Jira, Notion, Todoist, Trello, Weather).

**🛡️ Security**
- **Kalier** — authorized Kali Linux / MCP-Kali-Server offensive-security assessments.
- **Discoverer** — ProjectDiscovery recon suite (subfinder/httpx/naabu/katana/nuclei/cvemap) via a self-installing private Go toolchain in <install_dir>/Go; authorized recon, attack-surface mapping & vulnerability discovery.
- **security-audit / kali-pentest** skills.

**🔌 External integration**
- **Universal External-MCP client** — connect to any MCP server over 4 transports, up to 5 active, with 8 supervisor tools and an **MCP Doctor** agent that triages a server before you wire it.

**🖥️ Desktop & browser automation**
- **Playwrighter** — scripted browser automation.
- **Windower** — Win32 window manager (focus/move/resize/tile/close).
- **Shoter / Mouser / Keyboarder** — screenshots, mouse, keyboard.

**🎙️ Audio, video & speech**
- **Talker (TTS)** — text-to-speech via Ollama. **Whisperer (STT)** — speech-to-text (faster-whisper local + cloud fallback).
- **Recorder / Camcorder** — microphone and webcam capture.
- **AudioPlayer / VideoPlayer** — audio and video playback with volume/loop control.

**📨 Messaging, bridges & platform**
- **Telegrammer** — Telegram send/receive that can send under **two identities**, picked per message with `provider`: **as the bot** (`provider=bot`, Bot API + a `@BotFather` token) or **as your own account** (`provider=user`, official Telegram user session). Plain English works — say *"send it as me"* (→ your account) or *"as the bot"*. `auto` (the default) uses your account for private `@usernames`/`+phone` and the bot for numeric ids/channels. Sending as you needs a one-time login; human configs stay readable as `@username`.
- **Whatsapper** — WhatsApp send/receive with a `provider` switch for **which number sends**: **`cloud`** (default, the official Meta WhatsApp Cloud API — business number, templates, System User) or **`web`** (say *"send it as me"* / *"from my own WhatsApp"*) which sends from **your own personal number** by automating WhatsApp Web after a one-time QR login — no templates, no System User. The `web` path is unofficial (it drives WhatsApp Web) and carries Meta-ban risk; the `cloud` path remains the official, supported route.
- **Instant Messaging Doctor** — automatically diagnoses Telegrammer/Whatsapper failures and can be called directly before critical sends; validates official tokens, contacts, readable `@username` routing, Meta templates/webhooks, and emits Parametrizer-ready repair actions.
- **TeleTlamatini** — Telegram bridge into the full chat.
- **Multi-model** — Ollama (local), Anthropic Claude (cloud), Qwen (vision).
- **Self-knowledge & self-modification** — can read, modify, and rebuild her own source.
- **PyInstaller packaging** — ships as a standalone Windows `.exe`.

---

## See it work

- ▶️ **[One-minute teaser](https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s)** · 🎬 more demos on **[xaiht.org](https://xaiht.org)**.

---

## Installation

See **[the full docs](https://github.com/XAIHT/Tlamatini/blob/main/BookOfTlamatini.md)** for complete setup — cloud models (Ollama Pro/Max, Claude API), the visual workflow designer, and building a frozen Windows distribution with PyInstaller. In short: install Ollama → clone, venv, `pip install -r requirements.txt`, `migrate` → `runserver --noreload` → open `http://127.0.0.1:8000/`.

---

## Tech stack

Python 3.12 · Django 5.2.4 · Django Channels (Daphne ASGI) · LangChain / LangGraph · FAISS + rank-bm25 · Ollama / Anthropic Claude / Qwen vision · SQLite · PyInstaller. **Platform: Windows 10/11.**

---

## Contributing

Tested it on your board, in your engine, or on the canvas? **[Open an issue](https://github.com/XAIHT/Tlamatini/issues)** and tell me what worked and what didn't — that feedback is the most useful thing right now. PRs welcome.

---

## License

[MIT](https://github.com/XAIHT/Tlamatini/blob/main/LICENSE) · Built by [@XAIHT](https://github.com/XAIHT) · [xaiht.org](https://xaiht.org)
