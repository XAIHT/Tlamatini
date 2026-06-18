<p align="center">
  <img src="Tlamatini.jpg" alt="Tlamatini" width="180" height="180" />
</p>

<h1 align="center">Tlamatini</h1>

<p align="center">
  <b>The local-first AI developer assistant with a visual workflow designer — and the reach to touch hardware, 3D engines, and any external tool.</b><br/>
  <i>"one who knows" — it doesn't just edit code. It flashes your board, drives your engine, and orchestrates whole agent workflows on a canvas. On your machine.</i>
</p>

<p align="center">
  <a href="https://github.com/XAIHT/Tlamatini/releases/tag/v1.26.0"><img src="https://img.shields.io/badge/VERSION-v1.26.0-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="Version"/></a>
  <a href="https://www.python.org/downloads/release/python-31210/"><img src="https://img.shields.io/badge/PYTHON-3.12.10-3776AB?style=for-the-badge&labelColor=2D2D2D&logo=python&logoColor=white" alt="Python"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/PLATFORM-WIN%2010%20%7C%2011-0078D6?style=for-the-badge&labelColor=2D2D2D&logo=windows&logoColor=white" alt="Platform"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/AGENTS-78-8A2BE2?style=for-the-badge&labelColor=2D2D2D" alt="78 agents"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/TOOLS-75-16A34A?style=for-the-badge&labelColor=2D2D2D" alt="75 tools"/></a>
  <a href="https://github.com/XAIHT/Tlamatini/blob/main/LICENSE"><img src="https://img.shields.io/badge/LICENSE-GPLV3-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="License"/></a>
</p>

<p align="center">
  <a href="https://xaiht.org">🌐 Website</a> ·
  <a href="https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s">▶️ One-minute teaser</a> ·
  <a href="https://github.com/XAIHT/Tlamatini/blob/main/BookOfTlamatini.md">📖 Full docs</a>
</p>

---

> **📹 [ Drop a 15-second GIF here ]** — flashing a board from a prompt, or wiring agents on the canvas and hitting Start. One real GIF up top sells this faster than anything written below.

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
| 🧩 | **A VISUAL WORKFLOW DESIGNER** | **78 drag-and-drop agents** on a canvas you wire into runnable, savable `.flw` flows. *No other coding agent — Claude Code, Codex, none of them — gives you this.* This is the crown jewel. |

> **The headline no competitor can copy:** Tlamatini is the only local-first AI dev assistant where you *design the agent workflow visually*, then have it flash firmware, drive Unreal/Blender, run security tools, and command any external MCP — all from one machine.

---

## 🔒 And it's yours alone

Embeddings and chat run on your local [Ollama](https://ollama.com) install. Cloud models (Claude API, Ollama Pro/Max) and delegation to cloud CLIs are **opt-in, per request, never the default.** Your code and firmware never leave the box unless you route them out yourself.

---

## 📋 The full capability list

Everything Tlamatini can do, grouped:

**🧩 Orchestration & design**
- **Visual Workflow Designer (ACP)** — 78 drag-and-drop agents wired into runnable flows; save/load `.flw` files; Flow Compiler validates the canvas into `config.yaml`.
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

**📨 Bridges & platform**
- **TeleTlamatini / WhatsTlamatini** — Telegram and WhatsApp bridges into the full chat.
- **Multi-model** — Ollama (local), Anthropic Claude (cloud), Qwen (vision).
- **Self-knowledge & self-modification** — can read, modify, and rebuild her own source.
- **PyInstaller packaging** — ships as a standalone Windows `.exe`.

---

## ⚡ Quickstart — flash your first board in 5 minutes

**You need:** Windows 10/11 · Python 3.12 · [Ollama](https://ollama.com) · the toolchain for your target (e.g. [STM32CubeIDE](https://www.st.com/en/development-tools/stm32cubeide.html); ESP32/Arduino bootstrap themselves).

```bash
# 1. Get Ollama and a local model
ollama pull qwen2.5-coder

# 2. Clone and install
git clone https://github.com/XAIHT/Tlamatini.git
cd Tlamatini
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python Tlamatini/manage.py migrate

# 3. Run
python Tlamatini/manage.py runserver --noreload
#    open http://127.0.0.1:8000/  (default login: user / changeme)
```

**Then, in the chat box** (Multi-Turn on), plug in your board and type:

```
Scaffold a blinky for my STM32, build it, and flash the connected board.
```

Scaffold → build → preflight → flash → read serial. Swap "STM32" for "ESP32" or "Arduino". Or open the **Visual Workflow Designer** at `/agentic_control_panel/` and wire your first flow.

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

[GPL-3.0](https://github.com/XAIHT/Tlamatini/blob/main/LICENSE) · Built by [@XAIHT](https://github.com/XAIHT) · [xaiht.org](https://xaiht.org)
