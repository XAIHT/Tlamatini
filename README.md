# Tlamatini

![Project Logo](Tlamatini.jpg)

A sophisticated, locally-run AI developer assistant featuring an advanced Retrieval-Augmented Generation (RAG) system, a request-scoped Multi-Turn orchestration layer, a real-time web interface, a visual agentic workflow designer, and multi-model LLM support.

## Table of Contents

- [Overview](#overview)
- [Videos](#videos)
- [Quick Start](#quick-start)
- [Default Login Credentials](#default-login-credentials)
- [Key Features](#key-features)
- [Multi-Turn Chat Mode](#multi-turn-chat-mode)
  - [Toolbar Controls](#toolbar-controls)
  - [Checked and Unchecked Paths](#checked-and-unchecked-paths)
  - [Execution Stages](#execution-stages)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Manual Setup from Source](#manual-setup-from-source)
  - [Using the GUI Installer](#using-the-gui-installer)
- [Configuration](#configuration)
  - [LLM Settings](#llm-settings)
  - [Multi-Turn Mode](#multi-turn-mode)
  - [Image Interpreter Settings](#image-interpreter-settings)
  - [RAG Settings](#rag-settings)
    - [Chunking](#chunking)
    - [Retrieval](#retrieval)
    - [Context Limits](#context-limits)
    - [Compression](#compression)
    - [Metadata Extraction](#metadata-extraction)
    - [Advanced Retrieval Strategy](#advanced-retrieval-strategy)
  - [Internet Search Settings](#internet-search-settings)
  - [MCP Services](#mcp-services)
  - [Advanced Options](#advanced-options)
    - [History Management](#history-management)
    - [Performance Tuning](#performance-tuning)
    - [Debugging](#debugging)
    - [Miscellaneous](#miscellaneous)
- [Ollama Installation Without Administrative Rights](#ollama-installation-without-administrative-rights)
- [Running the Application](#running-the-application)
- [Building & Release Process](#building--release-process)
  - [Overview](#release-overview)
  - [Prerequisites](#release-prerequisites)
  - [Step 1: Build the Application (build.py)](#step-1-build-the-application-buildpy)
  - [Step 2: Build the Uninstaller (build_uninstaller.py)](#step-2-build-the-uninstaller-build_uninstallerpy)
  - [Step 3: Build the Installer (build_installer.py)](#step-3-build-the-installer-build_installerpy)
  - [Release Distribution](#release-distribution)
  - [What the Installer Does](#what-the-installer-does)
  - [What the Uninstaller Does](#what-the-uninstaller-does)
- [Core Components](#core-components)
  - [RAG System](#rag-system)
    - [Memory-Insufficient Context Fallback](#memory-insufficient-context-fallback)
  - [RAG Chain Types](#rag-chain-types)
  - [Unified Agent with Tools](#unified-agent-with-tools)
    - [Multi-Turn Tool Loop](#multi-turn-tool-loop)
    - [Capability Selection and Context Prefetch](#capability-selection-and-context-prefetch)
    - [Global Execution Planner](#global-execution-planner)
    - [Wrapped Chat-Agent Runtime Tools](#wrapped-chat-agent-runtime-tools)
    - [Runtime Isolation and Lifecycle](#runtime-isolation-and-lifecycle)
    - [Legacy Compatibility Guarantee](#legacy-compatibility-guarantee)
    - [Frozen-Mode and Runtime Behavior](#frozen-mode-and-runtime-behavior)
  - [Agentic Workflow Designer](#agentic-workflow-designer)
    - [Canvas Context Menus and Agent Descriptions](#canvas-context-menus-and-agent-descriptions)
    - [Pause, Stop, and Reanimation of a Flow](#pause-stop-and-reanimation-of-a-flow)
    - [Flow Validation](#flow-validation)
  - [Database Models](#database-models)
  - [Design Patterns](#design-patterns)
  - [MCP Integration](#mcp-integration)
  - [Claude API Client](#claude-api-client)
  - [Image Analysis](#image-analysis)
- [Available Tools](#available-tools)
  - [Core Tools](#core-tools)
  - [Wrapped Chat-Agent Tools](#wrapped-chat-agent-tools)
    - [Wrapped Runtime Lifecycle Tools](#wrapped-runtime-lifecycle-tools)
- [Workflow Agents](#workflow-agents)
  - [Agent Architecture](#agent-architecture)
  - [Control Agents](#control-agents)
  - [Monitoring Agents](#monitoring-agents)
  - [Notification Agents](#notification-agents)
  - [Action Agents](#action-agents)
  - [Logic Gates](#logic-gates)
  - [Routing Agents](#routing-agents)
  - [Utility Agents](#utility-agents)
- [Gatewayer: The Inbound Gateway Agent](#gatewayer-the-inbound-gateway-agent)
  - [How It Works](#how-it-works)
  - [Authentication Modes](#authentication-modes)
  - [Gatewayer vs. OpenClaw's Gateway](#gatewayer-vs-openclaws-gateway)
  - [Usage Examples](#usage-examples)
    - [Example A: Timestamped HMAC Webhook Triggers a Build-and-Notify Pipeline](#example-a-timestamped-hmac-webhook-triggers-a-build-and-notify-pipeline)
    - [Example B: IoT Sensor Alerts via Folder-Drop with Conditional Routing](#example-b-iot-sensor-alerts-via-folder-drop-with-conditional-routing)
  - [When to Use Gatewayer](#when-to-use-gatewayer)
- [Parametrizer: The Interconnection Engine](#parametrizer-the-interconnection-engine)
  - [Why Parametrizer Exists](#why-parametrizer-exists)
  - [How It Works](#how-it-works-1)
  - [The Interconnection Scheme](#the-interconnection-scheme)
  - [Unified Section Format](#unified-section-format)
  - [Supported Source Agents and Their Output Fields](#supported-source-agents-and-their-output-fields)
  - [Iterative Execution Model](#iterative-execution-model)
  - [Pause, Resume, and Reanimation](#pause-resume-and-reanimation)
  - [The Visual Mapping Dialog](#the-visual-mapping-dialog)
  - [Completion Semantics](#completion-semantics)
  - [Practical Examples](#practical-examples)
  - [Design Constraints](#design-constraints)
- [Multi-Turn Chat Mode: The Agentic Execution Engine](#multi-turn-chat-mode-the-agentic-execution-engine)
  - [What Multi-Turn Mode Enables](#what-multi-turn-mode-enables)
  - [Architecture: The Complete Pipeline](#architecture-the-complete-pipeline)
  - [Tool Categories](#tool-categories)
  - [The Multi-Turn Tool Loop](#the-multi-turn-tool-loop)
  - [Capability-Aware Tool Selection](#capability-aware-tool-selection)
  - [Wrapped Chat-Agent Lifecycle](#wrapped-chat-agent-lifecycle)
- [Flow Creation from Multi-Turn Answers](#flow-creation-from-multi-turn-answers)
  - [Overview: Turning Conversations into Workflows](#overview-turning-conversations-into-workflows)
  - [End-to-End Data Flow](#end-to-end-data-flow)
    - [Phase 1: Tool Call Recording (Backend)](#phase-1-tool-call-recording-backend)
    - [Phase 2: Answer Success Classification (Backend)](#phase-2-answer-success-classification-backend)
    - [Phase 3: WebSocket Broadcast (Backend to Frontend)](#phase-3-websocket-broadcast-backend-to-frontend)
    - [Phase 4: Button Rendering and Gate Conditions (Frontend)](#phase-4-button-rendering-and-gate-conditions-frontend)
    - [Phase 5: Flow Generation and Download (Frontend)](#phase-5-flow-generation-and-download-frontend)
  - [The Answer Analizer: LLM-Based Success Classification](#the-answer-analizer-llm-based-success-classification)
    - [Why Not Regex or Keyword Matching](#why-not-regex-or-keyword-matching)
    - [Classification Prompt Design](#classification-prompt-design)
    - [Classification Rules](#classification-rules)
    - [Error Handling and Defaults](#error-handling-and-defaults)
  - [Tool-Call Log Structure](#tool-call-log-structure)
    - [Log Entry Schema](#log-entry-schema)
    - [Tool Name to Agent Display Name Mapping](#tool-name-to-agent-display-name-mapping)
    - [Management Tools (Excluded from Flows)](#management-tools-excluded-from-flows)
  - [Flow File (.flw) Generation](#flow-file-flw-generation)
    - [Node Layout Strategy](#node-layout-strategy)
    - [Connection Wiring](#connection-wiring)
    - [Agent Config Mapping](#agent-config-mapping)
  - [Complete Pipeline Diagram](#complete-pipeline-diagram)
  - [Files Involved](#files-involved)
- [Custom Agent Development](#custom-agent-development)
  - [Using the `create_new_agent` Skill](#using-the-create_new_agent-skill)
    - [In Antigravity IDE / Gemini CLI](#in-antigravity-ide--gemini-cli)
    - [In Claude CLI (claude-code) / Cursor](#in-claude-cli-claude-code--cursor)
- [Custom MCP Development](#custom-mcp-development)
  - [Using the `create_new_mcp` Skill](#using-the-create_new_mcp-skill)
    - [Antigravity IDE / Gemini CLI Example](#antigravity-ide--gemini-cli-example)
    - [Claude CLI (claude-code) / Cursor Example](#claude-cli-claude-code--cursor-example)
- [Workflow Examples](#workflow-examples)
- [API Reference](#api-reference)
  - [WebSocket Protocol](#websocket-protocol)
    - [Client to Server Messages](#client-to-server-messages)
    - [Server to Client Messages](#server-to-client-messages)
  - [HTTP Endpoints](#http-endpoints)
    - [Pages](#pages)
    - [Data Loading](#data-loading)
    - [Agent Management](#agent-management)
    - [Connection Updates (Canvas Auto-Configuration)](#connection-updates-canvas-auto-configuration)
    - [Session & Pool Management](#session--pool-management)
- [Session Management](#session-management)
- [Open in... External Editors](#open-in-external-editors)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
    - [Ollama Connection Failed](#ollama-connection-failed)
    - [RAG Context Not Loading](#rag-context-not-loading)
    - [Multi-Turn Not Engaging](#multi-turn-not-engaging)
    - [Frozen Build Uses Wrong Config](#frozen-build-uses-wrong-config)
    - [WebSocket Disconnections](#websocket-disconnections)
    - [Agent Not Starting](#agent-not-starting)
    - [Memory Issues](#memory-issues)
    - [Image Analysis Fails](#image-analysis-fails)
    - [Forker/Asker Not Routing](#forkerasker-not-routing)
  - [Debug Mode](#debug-mode)
  - [Log Locations](#log-locations)
- [Application Log (tlamatini.log)](#application-log-tlamatinilog)
  - [Location](#tlamatini-log-location)
  - [How It Works: The Tee Stream Architecture](#how-it-works-the-tee-stream-architecture)
  - [What the Log Contains](#what-the-log-contains)
  - [Django Logger Integration](#django-logger-integration)
  - [Lifecycle and Rotation](#lifecycle-and-rotation)
- [Glossary](#glossary)
- [Keyboarder Supported Keys](#keyboarder-supported-keys)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Tlamatini** is a powerful, locally-deployed AI assistant built with Django that provides a real-time, web-based interface for interacting with Large Language Models (LLMs). Designed as a comprehensive developer assistant, it answers questions, generates code, analyzes codebases, and performs local technical tasks with awareness of your files, project structure, runtime state, and selected tools.

The system leverages a highly advanced, custom-built **Retrieval-Augmented Generation (RAG)** pipeline that goes far beyond simple text retrieval. It performs detailed source-code analysis including metadata extraction, architectural role classification, dependency mapping, context budgeting, and controlled fallback behavior to provide deeply grounded responses.

Additionally, Tlamatini features a **Visual Agentic Workflow Designer** that allows you to create automated workflows using drag-and-drop agents. These workflows can monitor logs, execute commands, send notifications via email, WhatsApp, and Telegram, execute SQL/MongoDB scripts, SSH into remote hosts, route decisions through conditional logic, and much more — all orchestrated through an intuitive visual interface with 57 pre-built agent types.

The main chat surface is now substantially more agentic as well. When **Multi-Turn** is enabled in the toolbar, the chat stack switches from the legacy one-shot tool exposure path to a request-scoped orchestration path that can:

- score and select relevant MCP-backed contexts
- score and bind only the relevant tool and wrapped-agent capabilities
- build a real global execution plan/DAG for the current request
- prefetch system/file context before tool execution
- monitor wrapped agent runs through follow-up runtime tools
- suppress visible console popups for chat-launched background work

Just as important, when **Multi-Turn** is unchecked the chat path intentionally preserves the legacy one-shot behavior, including the original prompt-shape validation and full-tool binding surface.

The entire application can be packaged into a standalone executable using PyInstaller, with a user-friendly Tkinter-based GUI installer for easy deployment.

---

## Videos

- [First video of system usage getting in Tlamatini](https://www.youtube.com/watch?v=CkvDPSd_c-g)
- [Video showing tlamatini loading a complete project and summarizing its entire source code](https://www.youtube.com/watch?v=Lrpbt_dPIXw)

---

## Quick Start

Get Tlamatini running in 5 minutes:

### 1. Clone and Setup

```bash
git clone https://github.com/XAIHT/Tlamatini.git
cd Tlamatini
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
python Tlamatini/manage.py migrate
python Tlamatini/manage.py createsuperuser
```

### 4. Run the Application

```bash
python Tlamatini/manage.py runserver --noreload
```

### 5. Access the Interface

1. Open `http://127.0.0.1:8000/` in your browser
2. Log in with your superuser credentials
3. Navigate to `/agent/` for the chat interface
4. (Optional) Set a context folder to enable code-aware responses

**First Steps:**
- Click "Set Context" and select a project directory
- Check **Multi-Turn** in the main chat toolbar if you want request-scoped planning, selective context prefetch, and dynamic tool binding
- Ask questions about your code: "How does the authentication work?"
- Try a checked Multi-Turn prompt such as: "Show me README.md in the project home and summarize it"
- Try generating code: "Write a Python function to validate email addresses"
- Access the workflow designer at `/agentic_control_panel/`

---

## Default Login Credentials

When Tlamatini is built and installed using the installer (or via `build.py`), a default user account is automatically created during the build process:

| Field | Value |
|-------|-------|
| **Username** | `user` |
| **Password** | `changeme` |
| **Email** | `user@xaiht.com` |

Use these credentials to log in at `http://127.0.0.1:8000/` after installation.

> **Security Note:** It is strongly recommended to change the default password after your first login, especially if the application is accessible on a network. You can change the password via the Django admin panel at `/admin/` or by running:
> ```bash
> python Tlamatini/manage.py changepassword user
> ```

If you are setting up from source (manual setup), you will create your own superuser account via `python manage.py createsuperuser` instead, and the default `user` account will not exist.

---

## Key Features

### Real-Time Chat Interface
- WebSocket-based communication via Django Channels for instant responses
- Syntax-highlighted code rendering with line numbers
- Canvas area for viewing, editing, and copying generated code
- Session persistence across browser reconnections (24-hour expiry)
- Generation cancellation support
- Modular frontend architecture (24 JS modules: 8 chat interface + 11 ACP workflow designer + 5 shared/auxiliary)

### Advanced RAG System
- **Dynamic Context Loading**: Set local files or entire directories as context directly from the web interface
- **Code-Aware Analysis**: Parses source code to extract classes, functions, imports, and dependencies
- **Architectural Classification**: Identifies file roles (controller, data_model, service_layer, etc.)
- **Hybrid Retrieval**: Combines FAISS vector search with BM25 keyword matching via Reciprocal Rank Fusion
- **Memory-Insufficient Context Fallback**: If embeddings or vector-store construction fail because the local model lacks RAM, Tlamatini preserves the already loaded source files and continues answering from a packed raw context instead of dropping to an empty-context chat
- **Intelligent Context Budgeting**: Prioritizes and selects the most relevant document chunks within token limits
- **Metadata Enrichment**: Tracks cross-file references and dependency graphs

### Unified Agent with Tool Calling
- Explicit multi-turn tool execution instead of a single opaque tool-call pass
- Request-scoped capability selection for tools, wrapped agents, and MCP-backed contexts
- Global execution planner/DAG for checked Multi-Turn requests
- Exact preservation of the legacy one-shot path when Multi-Turn is unchecked
- Execute Python scripts and shell commands
- Image analysis with dual vision backends (Claude Opus and Qwen/Ollama)
- Java decompilation (JAR/WAR files)
- ZIP file extraction
- Template-agent lifecycle management (`agent_parametrizer`, `agent_starter`, `agent_stopper`, `agent_stat_getter`)
- 32 wrapped chat-agent launchers plus 4 wrapped-runtime follow-up tools
- Per-tool enable/disable via global state and the chat Tools dialog
- Background/headless wrapped-runtime launch suppression for checked Multi-Turn requests

### Visual Workflow Designer
- Drag-and-drop agentic workflow creation
- 57 pre-built agent types for diverse automation tasks
- Logic gates (AND/OR) for complex flow control
- Conditional routing agents (Forker, Asker) for branching workflows
- README-backed agent purpose tooltips in the sidebar and per-node Description dialogs on the canvas
- Right-click canvas shortcuts for logs, instance-directory exploration, and instance-scoped `cmd.exe`
- Real-time LED status indicators: green (running), red (agent down while the flow is active), yellow blinking (paused), gray (stopped/idle)
- Undo/Redo support (1024 actions)
- Workflow save/load as `.flw` files
- Canvas auto-configuration of agent connections
- Flow validation with structural verification before execution

### Multi-Model Support
- **Ollama**: Local LLM inference (default)
- **Anthropic Claude**: Cloud API integration via included client library
- **Qwen**: Vision model support via Ollama for image interpretation
- Configurable models for different tasks (embedding, chat, image interpretation, internet classification)
- Bearer token authentication for remote Ollama instances

### Internet Search Integration
- LLM-based query classification for internet requirements
- DuckDuckGo web search with result summarization
- Configurable hint words for search triggering
- Dedicated summarizer model configuration

### Open in External Editors
- **"Open in..." dropdown** in the navigation bar to launch the context directory in an external editor
- Auto-detects installed applications: VS Code, Antigravity IDE, and Windows File Explorer
- Enabled for directory contexts and for file contexts through parent-directory resolution
- Each entry displays the application's icon for quick recognition

### Enterprise Features
- Django-based user authentication
- Secret redaction in context (configurable)
- Session-based multi-user isolation
- Comprehensive logging and metrics
- Process management with PID tracking and cleanup

---

## Multi-Turn Chat Mode

The chat toolbar now exposes two session-scoped execution modifiers beside **Clear history**:

- **Multi-Turn**: enables the request-scoped orchestration path described in this document
- **Add internet context**: independently controls web-search/context enrichment

The Multi-Turn toggle is intentionally narrow in scope. It changes how the unified chat stack plans and binds capabilities for the current request, but it does **not** rewrite the ACP/runtime model or replace the legacy chat path globally.

### Toolbar Controls

- The toggle is rendered directly in the main chat toolbar and persisted per browser session.
- Frontend state is stored in `sessionStorage`, restored on load, and sent with each plain chat request as `multi_turn_enabled`.
- The visual style is shared with the internet-context toggle so both controls read as request-execution modifiers rather than as modal settings.

### Checked and Unchecked Paths

When **Multi-Turn is checked**, the request uses the Phase 1 to Phase 3 orchestration path:

1. `ask_rag()` bypasses only the prompt-shape rephrase gate.
2. `rag/factory.py` builds a request-scoped global execution plan.
3. MCP-backed contexts are prefetched selectively instead of indiscriminately.
4. The unified agent binds only the planned tool subset for the current request.
5. Wrapped agent subprocesses launch in background/headless mode to avoid console popups.

When **Multi-Turn is unchecked**, the system deliberately preserves the legacy path:

1. prompt-shape validation still runs
2. legacy MCP context prefetch behavior is kept
3. the legacy full-tool binding surface is exposed
4. legacy visible-console launch behavior remains in place

That separation is intentional. Multi-Turn is an opt-in execution mode, not a silent rewrite of the original chat behavior.

### Execution Stages

At a high level, a checked Multi-Turn request now moves through these stages:

1. **Frontend flagging**: the browser sends `multi_turn_enabled: true`.
2. **Prompt gate**: prompt-shape validation is skipped only for this mode.
3. **Context planning**: file/system MCP contexts are selected based on the request.
4. **Global planning**: a DAG is built with `prefetch`, `execute`, `monitor`, and `answer` nodes.
5. **Dynamic binding**: only the relevant tools or wrapped agents are bound.
6. **Multi-turn execution**: the backend loops through tool calls and observations until a final answer is produced.
7. **Final synthesis**: the response is grounded in prefetched context, tool output, and any monitored wrapped-agent run data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Web Browser                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │           Chat Interface / Agentic Control Panel                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │ WebSocket (ws://)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Django Channels (Daphne)                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     AgentConsumer (WebSocket Handler)               │   │
│  │   - Message routing       - Session management                      │   │
│  │   - Command processing    - Heartbeat/keep-alive                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│    RAG Pipeline   │   │   Unified Agent   │   │   MCP Services    │
│                   │   │                   │   │                   │
│ - Document loader │   │ - Tool execution  │   │ - System metrics  │
│ - Text splitters  │   │ - Multi-turn loop │   │   (WebSocket)     │
│ - FAISS + BM25    │   │ - Function calls  │   │ - File search     │
│ - Context budget  │   │ - Planner / DAG   │   │   (gRPC)          │
│ - Fallback mode   │   │ - Wrapped runtimes│   │                   │
└───────────────────┘   └───────────────────┘   └───────────────────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            LLM Backends                                     │
│   ┌─────────────────────────┐     ┌─────────────────────────────────────┐  │
│   │    Ollama (Local)       │     │    Anthropic Claude (Cloud)         │  │
│   │  - Embedding models     │     │  - Claude Opus                      │  │
│   │  - Chat models          │     │  - Image/PDF analysis               │  │
│   │  - Vision models (Qwen) │     │  - Tool calling                     │  │
│   └─────────────────────────┘     └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Request Flow

1. **User sends message** via WebSocket, optionally with `multi_turn_enabled`
2. **AgentConsumer** receives the request and forwards the execution flag into the chat stack
3. **Context determination**: Check whether local RAG context is already loaded
4. **Internet check**: Classify whether live internet context is needed
5. **Chain selection**: Choose the appropriate chain (RAG, Basic, or Unified Agent)
6. **Multi-Turn gate**:
   - unchecked: use the legacy one-shot/full-tool path
   - checked: build a request-scoped planner, select contexts, and dynamically bind tools
7. **Context prefetch**: selectively fetch system/file MCP context for checked requests
8. **Execution loop**: run the multi-turn tool loop, optionally monitor wrapped agent runs, and synthesize the answer
9. **Streaming/broadcast**: return the resulting answer and status messages via WebSocket

---

## Technology Stack

| Category | Technologies |
|----------|--------------|
| **Backend** | Python 3.12.10 (recommended), Django 5.2.4, Django Channels 4.1, Daphne (ASGI) |
| **Frontend** | HTML5, Bootstrap 5, JavaScript (modular), jQuery, jQuery UI |
| **AI/ML** | LangChain 0.3.27, LangGraph 0.2.74, Ollama (ollama 0.5.3), FAISS, rank-bm25, NumPy 2.3.4, PyAutoGUI 0.9.54 |
| **LLM APIs** | Anthropic Claude (anthropic 0.74.1), Ollama REST API, MCP 1.25.0 |
| **Database** | SQLite (default) |
| **Communication** | WebSockets, gRPC (grpcio 1.76.0), MCP 1.25.0 |
| **Document Processing** | pymupdf, python-docx, python-pptx, unstructured |
| **Messaging** | IMAP (email monitoring), TextMeBot API (WhatsApp), SMTP (email sending) |
| **Packaging** | PyInstaller |
| **Installer** | Tkinter GUI |

---

## Project Structure

```
Tlamatini/
├── Tlamatini/                      # Django project root
│   ├── manage.py                    # Django CLI utility
│   ├── db.sqlite3                   # SQLite database
│   ├── .agents/                     # AI workflow docs for agent scaffolding
│   │   └── workflows/
│   │       └── create_new_agent.md  # Skill for creating new workflow agents
│   ├── .mcps/                       # AI workflow docs for MCP/tool extensions
│   │   └── create_new_mcp.md        # Skill for adding MCP-backed capabilities and tool wiring
│   │
│   ├── tlamatini/                 # Django project configuration
│   │   ├── settings.py             # Django settings (Channels, WhiteNoise)
│   │   ├── urls.py                 # Root URL routing
│   │   ├── asgi.py                 # ASGI config with WebSocket routing
│   │   ├── middleware.py           # Custom middlewares
│   │   └── context_processors.py   # Template context processors
│   │
│   ├── agent/                       # Core application
│   │   ├── apps.py                  # App config (MCP startup, signal handlers, cleanup)
│   │   ├── admin.py                 # Django admin model registration
│   │   ├── views.py                # HTTP request handlers (103 endpoints)
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # Database models (13 models)
│   │   ├── urls.py                 # URL routing definitions
│   │   ├── routing.py              # WebSocket URL patterns
│   │   ├── config.json             # LLM and RAG configuration
│   │   ├── config_loader.py        # Shared frozen/source-aware config reader
│   │   ├── prompt.pmt              # System prompt template
│   │   ├── global_state.py         # Thread-safe singleton state (Singleton pattern)
│   │   ├── constants.py            # Application constants and regex patterns
│   │   ├── chat_agent_registry.py  # Wrapped chat-agent tool registry and metadata
│   │   ├── chat_agent_runtime.py   # Isolated wrapped-runtime lifecycle helpers
│   │   │
│   │   ├── rag/                    # RAG system package
│   │   │   ├── __init__.py        # Package exports
│   │   │   ├── factory.py         # Chain builders (LLM + chain creation)
│   │   │   ├── interface.py       # Public API (ask_rag, token counting, etc.)
│   │   │   ├── interaction.py     # User interaction (context caching, rephrasing)
│   │   │   ├── loaders.py         # Document loaders with size reporting
│   │   │   ├── splitters.py       # Text chunking (RecursiveCharacterTextSplitter)
│   │   │   ├── retrieval.py       # Retrieval strategies (FAISS+BM25, RRF)
│   │   │   ├── config.py          # Configuration file loader
│   │   │   ├── prompts.py         # Prompt templates for contextualization
│   │   │   ├── utils.py           # Utilities (tokens, hashing, sanitization)
│   │   │   └── chains/            # LangChain chain implementations
│   │   │       ├── base.py        # Base chain with cancellation callbacks
│   │   │       ├── basic.py       # BasicPromptOnlyChain (no docs)
│   │   │       ├── history_aware.py # History-aware RAG with reranking
│   │   │       └── unified.py     # Tool-enabled agent chains (LangGraph)
│   │   │
│   │   ├── rag_enhancements.py     # Advanced metadata extraction
│   │   ├── capability_registry.py  # Request-scoped capability scoring and selection
│   │   ├── mcp_agent.py            # MCP unified agent builder and multi-turn executor
│   │   ├── global_execution_planner.py # Request-scoped DAG planner for Multi-Turn mode
│   │   ├── tools.py                # LangChain tool definitions and wrapped chat-agent launchers
│   │   ├── web_search_llm.py       # Internet search integration
│   │   ├── inet_determiner.py      # Search requirement classifier
│   │   │
│   │   ├── path_guard.py           # Centralized path validation and traversal prevention
│   │   ├── tests.py                # Security, Multi-Turn, runtime, and frozen-mode regression suite
│   │   ├── chat_history_loader.py  # Chat history management
│   │   ├── chain_system_lcel.py    # System metrics chain
│   │   ├── chain_files_search_lcel.py # File search chain (with path-safe lookups)
│   │   ├── mcp_system_server.py    # MCP WebSocket server
│   │   ├── mcp_system_client.py    # MCP system metrics client
│   │   ├── mcp_files_search_server.py # gRPC file search server
│   │   ├── mcp_files_search_client.py # gRPC file search client
│   │   ├── filesearch.proto        # Protobuf service definition
│   │   ├── filesearch_pb2.py       # gRPC generated protobuf
│   │   ├── filesearch_pb2_grpc.py  # gRPC generated service stubs
│   │   │
│   │   ├── services/               # Business logic services
│   │   │   ├── filesystem.py      # File operations
│   │   │   └── response_parser.py # LLM response parsing
│   │   │
│   │   ├── management/commands/    # Django management commands
│   │   │   └── startserver.py     # Custom server startup command
│   │   │
│   │   ├── opus_client/            # Claude API client library
│   │   │   ├── claude_opus_client.py # Full-featured Anthropic client
│   │   │   ├── examples.py        # Usage examples
│   │   │   └── README.md          # Client documentation
│   │   │
│   │   ├── imaging/                # Image analysis module
│   │   │   ├── image_interpreter.py  # Dual-backend image analysis (Claude + Qwen)
│   │   │   └── converter.py         # Image format conversion / base64 encoding
│   │   │
│   │   ├── agents/                 # Workflow agent templates (56 types)
│   │   │   ├── starter/           # Flow initiator
│   │   │   ├── ender/             # Flow terminator (+ output_agents for Cleaners)
│   │   │   ├── stopper/           # Pattern-based agent terminator
│   │   │   ├── cleaner/           # Post-termination cleanup agent
│   │   │   ├── raiser/            # Event-driven launcher (log pattern → start agents)
│   │   │   ├── executer/          # Shell command executor
│   │   │   ├── pythonxer/         # Python script executor with Ruff validation
│   │   │   ├── sqler/             # SQL Server query execution agent
│   │   │   ├── mongoxer/          # MongoDB script execution agent
│   │   │   ├── mouser/            # Mouse pointer movement agent
│   │   │   ├── keyboarder/        # Keyboard typing / hotkey automation agent
│   │   │   ├── deleter/           # File deletion agent
│   │   │   ├── mover/             # File move/copy agent
│   │   │   ├── shoter/            # Screenshot capture agent
│   │   │   ├── monitor_log/       # Log file monitor (LLM-powered)
│   │   │   ├── monitor_netstat/   # Network port monitor (LLM-powered)
│   │   │   ├── notifier/          # Event notification agent (LangGraph)
│   │   │   ├── emailer/           # Email sender (SMTP)
│   │   │   ├── recmailer/         # Email receiver/monitor (IMAP + LLM)
│   │   │   ├── whatsapper/        # WhatsApp notifications (TextMeBot + LLM)
│   │   │   ├── telegramer/        # Telegram message sender
│   │   │   ├── telegramrx/        # Telegram message receiver/monitor
│   │   │   ├── ssher/             # SSH remote command execution
│   │   │   ├── scper/             # SCP file transfer agent
│   │   │   ├── prompter/          # LLM prompt execution agent
│   │   │   ├── gitter/            # Git operations agent
│   │   │   ├── dockerer/          # Docker container management agent
│   │   │   ├── kuberneter/        # Kubernetes command executor agent
│   │   │   ├── apirer/           # HTTP/REST API request agent
│   │   │   ├── jenkinser/        # CI/CD pipeline trigger agent
│   │   │   ├── crawler/          # Developer-oriented web crawler with raw content + LLM analysis
│   │   │   ├── summarizer/       # Log monitoring with LLM event detection
│   │   │   ├── flowhypervisor/   # System-managed LLM anomaly detector
│   │   │   ├── pser/             # LLM-powered process finder agent
│   │   │   ├── asker/             # Interactive A/B path chooser (user dialog)
│   │   │   ├── forker/            # Automatic A/B path router (pattern-based)
│   │   │   ├── counter/            # Persistent counter with L/G threshold routing
│   │   │   ├── file_interpreter/      # Document parsing and text/image extraction
│   │   │   ├── image_interpreter/     # LLM vision-based image analysis and description
│   │   │   ├── gatewayer/         # Inbound gateway: HTTP webhook / folder-drop ingress
│   │   │   ├── gateway_relayer/  # Ingress relay: bridges provider webhooks into Gatewayer
│   │   │   ├── node_manager/     # Infrastructure registry and node supervision agent
│   │   │   ├── file_creator/    # File creation utility agent
│   │   │   ├── file_extractor/  # File text extraction utility agent
│   │   │   ├── j_decompiler/    # Java artifact decompiler using bundled jd-cli
│   │   │   ├── keyboarder/            # Simulates human keyboard typing
│   │   │   ├── kyber_keygen/   # CRYSTALS-Kyber key pair generation agent
│   │   │   ├── kyber_cipher/  # CRYSTALS-Kyber encryption agent
│   │   │   ├── kyber_decipher/ # CRYSTALS-Kyber decryption agent
│   │   │   ├── parametrizer/  # Utility interconnection agent (maps outputs to inputs)
│   │   │   ├── flowbacker/    # Session backup and cleanup handoff agent
│   │   │   ├── barrier/       # Synchronization barrier for flow control
│   │   │   ├── googler/       # Google search agent (Playwright + text extraction)
│   │   │   ├── sleeper/           # Delay agent
│   │   │   ├── croner/            # Scheduled trigger
│   │   │   ├── flowcreator/       # AI-powered flow designer (LLM)
│   │   │   ├── and/               # AND logic gate
│   │   │   └── or/                # OR logic gate
│   │   │
│   │   ├── templates/agent/        # HTML templates
│   │   │   ├── agent_page.html    # Main chat interface
│   │   │   ├── agentic_control_panel.html # Workflow designer
│   │   │   ├── login.html         # Login page
│   │   │   └── welcome.html       # Home page
│   │   │
│   │   └── static/agent/           # Frontend assets
│   │       ├── sounds/            # Audio alerts
│   │       │   ├── notification.wav       # Notifier browser alert sound
│   │       │   └── hypervisor_alert.wav   # FlowHypervisor anomaly alert sound
│   │       ├── css/               # Stylesheets
│   │       │   ├── agent_page.css
│   │       │   ├── agentic_control_panel.css
│   │       │   ├── login.css
│   │       │   ├── tools_dialog.css
│   │       │   └── welcome.css
│   │       └── js/                # JavaScript modules (23 files)
│   │           ├── agent_page_init.js     # App initialization & WebSocket setup
│   │           ├── agent_page_chat.js     # Chat message handling
│   │           ├── agent_page_canvas.js   # Code canvas rendering
│   │           ├── agent_page_context.js  # RAG context management
│   │           ├── agent_page_dialogs.js  # Modal dialogs
│   │           ├── agent_page_layout.js   # UI layout management
│   │           ├── agent_page_state.js    # Client-side state
│   │           ├── agent_page_ui.js       # General UI utilities
│   │           ├── agentic_control_panel.js # Flow designer entry point
│   │           ├── acp-globals.js          # ACP shared global state & constants
│   │           ├── acp-canvas-core.js      # ACP canvas rendering & drag-and-drop
│   │           ├── acp-canvas-undo.js      # ACP undo/redo state management
│   │           ├── acp-agent-connectors.js # ACP agent connection logic (50 handlers)
│   │           ├── acp-control-buttons.js  # ACP start/stop/pause/hypervisor controls
│   │           ├── acp-file-io.js          # ACP workflow save/load (.flw files)
│   │           ├── acp-running-state.js    # ACP LED indicators & process monitoring
│   │           ├── acp-session.js          # ACP session pool management
│   │           ├── acp-layout.js           # ACP canvas layout utilities
│   │           ├── acp-undo-manager.js     # ACP undo stack manager
│   │           ├── acp-validate.js         # Flow validation engine (structural rules)
│   │           ├── canvas_item_dialog.js   # Agent config dialog on canvas
│   │           ├── contextual_menus.js     # Right-click menus
│   │           └── tools_dialog.js         # Tool enable/disable dialog
│   │
│   ├── jd-cli/                      # Java decompiler CLI tool
│   │   ├── jd-cli.bat               # Batch wrapper for JAR/WAR decompilation
│   │   └── jd-cli.jar               # Java Decompiler engine
│   │
│   └── staticfiles/                # Collected static files (WhiteNoise)
│
├── build.py                         # PyInstaller build script
├── build_installer.py               # NSIS-based installer builder
├── build_uninstaller.py             # Uninstaller builder (--onefile)
├── install.py                       # Tkinter GUI installer
├── uninstall.py                     # Tkinter GUI uninstaller
├── eslint.config.mjs                # ESLint configuration for frontend JS
├── requirements.txt                 # Python dependencies
├── LICENSE                          # GPL-3.0 License
└── README.md                        # This file
```

---

## Installation

### Prerequisites

- **Python 3.12.10** (strongly recommended — this is the only version the project has been fully tested with)
- Either:
  - the current checked-in cloud/back-end configuration from `Tlamatini/agent/config.json`, or
  - **Ollama** installed and running with your chosen local models configured in `config.json`

### Manual Setup from Source

1. **Clone the repository**
   ```bash
   git clone https://github.com/XAIHT/Tlamatini.git
   cd Tlamatini
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the LLM backend**

   Edit `Tlamatini/agent/config.json`:
   ```json
   {
     "embeding-model": "qwen3-embedding:8b",
     "chained-model": "glm-5:cloud",
     "unified_agent_model": "glm-5:cloud",
     "image_interpreter_model": "qwen3.5:cloud",
     "ollama_base_url": "http://127.0.0.1:11434",
     "chat_agent_limit_runs": 100
   }
   ```

   Replace those defaults if you want a fully local Ollama configuration.

5. **Apply database migrations**
   ```bash
   python Tlamatini/manage.py migrate
   ```

6. **Create a superuser**
   ```bash
   python Tlamatini/manage.py createsuperuser
   ```

7. **Collect static files**
   ```bash
   python Tlamatini/manage.py collectstatic --noinput
   ```

### Using the GUI Installer

1. Obtain the installer package (`installer.exe` or `pkg.zip`)
2. Run the installer
3. Click "Browse" to select the installation directory
4. Click "Install"
5. Navigate to the chosen directory and run `Tlamatini.exe`

---

## Configuration

The main configuration file is located at `Tlamatini/agent/config.json`:

When running a frozen/PyInstaller build, the effective `config.json` is resolved from the install directory next to the executable. In source mode, it is resolved from `Tlamatini/agent/config.json`. If `CONFIG_PATH` is set, that file takes precedence.

### LLM Settings

```json
{
  "embeding-model": "qwen3-embedding:8b",
  "chained-model": "glm-5:cloud",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_token": "",
  "ANTHROPIC_API_KEY": "config you api key here by claude",
  "enable_unified_agent": true,
  "unified_agent_model": "glm-5:cloud",
  "unified_agent_base_url": "http://127.0.0.1:11434",
  "unified_agent_temperature": 0.0,
  "unified_agent_max_iterations": 100
}
```

| Key | Description |
|-----|-------------|
| `embeding-model` | Embedding model for the retrieval pipeline |
| `chained-model` | Primary chat model used by non-tool chat chains |
| `ollama_base_url` | Ollama server URL |
| `ollama_token` | Bearer token for authenticated Ollama instances (optional) |
| `ANTHROPIC_API_KEY` | Anthropic API key placeholder for Claude-backed image analysis |
| `enable_unified_agent` | Enable tool-calling agent |
| `unified_agent_model` | Model used by the unified agent multi-turn tool loop |
| `unified_agent_base_url` | Base URL for the unified agent's LLM |
| `unified_agent_temperature` | Temperature for agent responses (0.0 = deterministic) |
| `unified_agent_max_iterations` | Maximum number of tool-call / observation turns the unified agent may execute before it must stop and summarize the latest state |

### Multi-Turn Mode

Multi-Turn mode is controlled from the chat toolbar rather than from `config.json`, but it depends on several configuration-backed behaviors:

- `enable_unified_agent` must remain enabled for the unified tool-capable chat path
- `unified_agent_model`, `unified_agent_base_url`, and `unified_agent_temperature` govern the model used by the explicit loop
- `unified_agent_max_iterations` caps the maximum turn count of the explicit loop
- `chat_agent_limit_runs` controls the default wrapped-run listing limit used by runtime follow-up tools

Operationally:

- **checked Multi-Turn** enables request-scoped capability selection, context prefetch, global planning, and headless wrapped-runtime launch behavior
- **unchecked Multi-Turn** keeps the legacy prompt validation, legacy context prefetch, and full-tool binding behavior

The frontend persists the toggle per browser session, not as a server-global setting.

### Image Interpreter Settings

```json
{
  "image_interpreter_base_url": "http://127.0.0.1:11434",
  "image_interpreter_model": "qwen3.5:cloud",
  "image_interpreter_temperature": 0,
  "image_interpreter_image_path": ""
}
```

| Key | Description |
|-----|-------------|
| `image_interpreter_base_url` | Ollama URL for vision model |
| `image_interpreter_model` | Vision model name (e.g., Qwen, LLaVA) |
| `image_interpreter_temperature` | Temperature for image descriptions |
| `image_interpreter_image_path` | Default image path (optional) |

### RAG Settings

#### Chunking
```json
{
  "chunk_size": 3000,
  "chunk_overlap": 800,
  "max_chunks_per_file": 50
}
```

#### Retrieval
```json
{
  "k_vector": 100,
  "k_bm25": 100,
  "k_fused": 150,
  "enable_bm25": true,
  "use_mmr": false,
  "rrf_k": 60,
  "fetch_k": 300
}
```

| Key | Description |
|-----|-------------|
| `k_vector` | Number of results from FAISS vector search |
| `k_bm25` | Number of results from BM25 keyword search |
| `k_fused` | Final number after Reciprocal Rank Fusion |
| `enable_bm25` | Enable hybrid retrieval |
| `rrf_k` | RRF constant for rank combination |
| `fetch_k` | Candidate pool size for MMR |

#### Context Limits
```json
{
  "max_doc_chars": 150000,
  "max_context_chars": 250000,
  "context_budget_allocation": {
    "high_relevance": 0.60,
    "architecture": 0.20,
    "related": 0.15,
    "documentation": 0.05
  }
}
```

The context budget allocates token space to different document types:
- **High relevance** (60%): Documents matching the query directly
- **Architecture** (20%): Core structural files (models, controllers)
- **Related** (15%): Documents with dependency relationships
- **Documentation** (5%): README, docs, comments

#### Compression
```json
{
  "use_llm_extractor": true,
  "use_embeddings_filter": false,
  "embeddings_filter_threshold": 0.4,
  "use_long_context_reorder": true
}
```

#### Metadata Extraction
```json
{
  "metadata_extraction": {
    "enable_code_structure": true,
    "enable_file_role_classification": true,
    "enable_dependency_tracking": true,
    "enable_cross_references": true
  }
}
```

#### Advanced Retrieval Strategy
```json
{
  "retrieval_strategy": {
    "enable_multi_stage": false,
    "enable_query_expansion": true,
    "enable_hierarchical_context": true,
    "enable_context_budget_allocation": true
  }
}
```

### Internet Search Settings

```json
{
  "internet_classifier_model": "deepseek-v3.2:cloud",
  "internet_classifier_verbose": true,
  "internet_classifier_max_iterations": 4,
  "internet_classifier_streaming": true,
  "internet_hint_words_mode": "extend",
  "internet_hint_words": [],
  "web_summarizer_model": "deepseek-v3.2:cloud",
  "web_context_max_chars": 10000
}
```

| Key | Description |
|-----|-------------|
| `internet_classifier_model` | Model used to decide if web search is needed |
| `internet_hint_words_mode` | `extend` adds to defaults, `replace` overrides |
| `internet_hint_words` | Extra keywords that trigger web search |
| `web_summarizer_model` | Model used to summarize web results |
| `web_context_max_chars` | Max characters from web results to include |

### MCP Services

```json
{
  "mcp_system_server_host": "127.0.0.1",
  "mcp_system_server_port": 8765,
  "mcp_files_search_server_port": 50051,
  "mcp_files_search_server_max_workers": 10,
  "mcp_files_search_model": "deepseek-v3.2:cloud",
  "max_lines_search_files": 1024
}
```

### Advanced Options

#### History Management
```json
{
  "history_summary_enable": true,
  "history_summary_trigger_tokens": 150,
  "history_keep_last_turns": 3
}
```

#### Wrapped Chat-Agent Runtime
```json
{
  "chat_agent_limit_runs": 100
}
```

| Key | Description |
|-----|-------------|
| `chat_agent_limit_runs` | Maximum number of recent wrapped chat-agent runs returned by `chat_agent_run_list`, and the default limit used by the runtime listing helper unless an explicit override is supplied |

#### Performance Tuning
```json
{
  "performance": {
    "enable_caching": true,
    "cache_embeddings": true,
    "parallel_processing": true,
    "max_workers": 12
  }
}
```

#### Debugging
```json
{
  "logging": {
    "log_retrieval_metrics": true,
    "log_context_size": true,
    "log_query_rewrites": true,
    "verbose_metadata": true
  }
}
```

#### Miscellaneous
```json
{
  "load_hidden": true,
  "ssl_verify": false,
  "disable_proxies": false,
  "max_input_tokens": 5000,
  "keep_last_turns": 3
}
```

---

## Ollama Installation Without Administrative Rights

The official Windows PowerShell installer supports a per-user installation. You do not need to open PowerShell as Administrator, and you do not need to install Ollama into `Program Files`.

If you want the safest no-admin path, follow these steps exactly.

### 1. Open a normal PowerShell window

Open PowerShell normally.

- Do not right-click and choose Run as administrator.
- A normal user shell is the correct choice for this setup.

### 2. Install Ollama into your user profile

Run this command exactly as shown:

```powershell
$env:OLLAMA_INSTALL_DIR = "$env:LOCALAPPDATA\Programs\Ollama"
irm https://ollama.com/install.ps1 | iex
```

What this does:

- Forces the install directory to a folder you already own: `%LOCALAPPDATA%\Programs\Ollama`
- Avoids any machine-wide location that could require elevation
- Uses Ollama's official Windows installer script

If the install succeeds, the `ollama` executable will be available from your user account.

### 3. Close and reopen PowerShell

After installation finishes, close the PowerShell window and open a new one. This ensures the updated `PATH` is visible in the new session.

### 4. Verify that Ollama is installed

Run:

```powershell
ollama --version
```

If PowerShell says `ollama` is not recognized:

1. Close PowerShell again and open a fresh window.
2. Run `ollama --version` one more time.
3. If it still fails, check that this folder exists:

```powershell
Test-Path "$env:LOCALAPPDATA\Programs\Ollama"
```

If that command returns `True`, you can temporarily run Ollama directly like this:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" --version
```

### 5. Start the Ollama service if needed

Tlamatini expects Ollama to answer on:

```text
http://127.0.0.1:11434
```

In many Windows installs, Ollama starts automatically. If it is not running, start it manually in a dedicated terminal:

```powershell
ollama serve
```

Leave that terminal open while you use the application.

### 6. Verify the local API is responding

Run:

```powershell
Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing
```

If you get an HTTP response instead of a connection error, Ollama is reachable and Tlamatini will be able to call it.

### Pull All Default Ollama Models Used by Tlamatini

If you want the application to work with the default model names shipped in this repository, pull the models below exactly as written.

Run them one by one:

```powershell
ollama pull qwen3-embedding:8b
ollama pull glm-5:cloud
ollama pull qwen3.5:cloud
ollama pull gpt-oss:120b-cloud
ollama pull qwen3.5:397b-cloud
ollama pull llama3.2-vision:11b
```

These model tags come from the default configuration files included with the project:

- `qwen3-embedding:8b`: default embedding model in `Tlamatini/agent/config.json`
- `glm-5:cloud`: default chained/chat, unified-agent, internet, and MCP file-search model in `Tlamatini/agent/config.json`
- `qwen3.5:cloud`: default image interpreter model in `Tlamatini/agent/config.json`
- `gpt-oss:120b-cloud`: default model in several shipped workflow-agent templates such as Monitor Log, Monitor Netstat, Notifier, Prompter, Summarizer, Pser, Recmailer, Whatsapper, File-Interpreter, and FlowHypervisor
- `qwen3.5:397b-cloud`: default FlowCreator model in `Tlamatini/agent/agents/flowcreator/config.yaml`
- `qwen3.5:cloud`: default Image-Interpreter model in `Tlamatini/agent/agents/image_interpreter/config.yaml`

Important notes:

- Some default tags in this repository use `:cloud` variants. Pull them exactly as written if you want to keep the shipped defaults unchanged.
- These models are not all small. Depending on your hardware, bandwidth, and Ollama account access, some pulls may take a long time.
- `telegramrx` also uses a default `whisper.model` value of `medium`, but that is not an Ollama model, so it is not installed with `ollama pull`.

### Quick Post-Install Checklist

Before starting Tlamatini, confirm all of these are true:

1. `ollama --version` works in a normal PowerShell window.
2. `ollama serve` is running, or the Ollama background service is already active.
3. `Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing` returns successfully.
4. The required default models have been pulled.

If all four checks pass, the Ollama side is ready.

---

## Running the Application

### Development Server

```bash
python Tlamatini/manage.py runserver --noreload
```

Access the application at `http://127.0.0.1:8000/`

### Custom Start Server (with MCP initialization)

```bash
python Tlamatini/manage.py startserver
```

This custom management command explicitly starts the MCP system and file search servers in separate threads before launching Django's development server. Preferred for stable async operation.

### Production Server (ASGI with Daphne)

```bash
daphne -b 127.0.0.1 -p 8000 tlamatini.asgi:application
```

### Startup Sequence

When the application starts, the following sequence occurs automatically:

1. **Django initialization** (`manage.py`) - Sets `FOR_DISABLE_CONSOLE_CTRL_HANDLER=1` (Intel Fortran runtime fix), loads settings
2. **App ready hook** (`agent/apps.py`) - Cleans pools directory, clears `AgentProcess` and `ChatAgentRun` records, repopulates the Agent table from the current `agent/agents/` directory, and registers signal handlers
3. **MCP servers launch** - System metrics server (WebSocket:8765) and file search server (gRPC:50051) start in daemon threads
4. **Web server** - Daphne ASGI server listens on `0.0.0.0:8000` (HTTP + WebSocket)

### Shutdown Sequence

On Ctrl+C or console close:

1. **Signal handler** catches SIGINT/SIGBREAK
2. **Process cleanup** - Kills tracked agents from DB, finds untracked agents in pool directory, recursively kills child processes
3. **Database cleanup** - Clears `AgentProcess` records
4. **Pool cleanup** - Deletes pool directory contents
5. **Exit** via `os._exit()` to avoid atexit recursion

### MCP Servers (Standalone, Optional)

MCP servers normally start automatically with the application. For standalone testing:

Start the MCP system metrics server:
```bash
python Tlamatini/agent/mcp_system_server.py
```

Start the gRPC file search server:
```bash
python Tlamatini/agent/mcp_files_search_server.py
```

---

## Building & Release Process

### Release Overview

A complete Tlamatini release is produced by running three build scripts **in order**. Each step depends on artifacts produced by the previous one:

```
build.py  ──►  build_uninstaller.py  ──►  build_installer.py
   │                   │                         │
   ▼                   ▼                         ▼
pkg.zip          Uninstaller.exe        dist/Tlamatini_Release/
(app bundle)     (at project root)        ├─ Installer.exe
                                          ├─ Uninstaller.exe
                                          ├─ pkg.zip
                                          └─ _internal/
```

The final distributable is the `dist/Tlamatini_Release/` folder, which you zip and share with end users.

### Release Prerequisites

- **Python 3.10+** with `pip` available
- **PyInstaller** (`pip install pyinstaller`)
- All project dependencies from `requirements.txt`
- Windows environment (the installer/uninstaller are Windows-specific)

### Step 1: Build the Application (`build.py`)

```bash
python build.py
```

This is the main application build. It:

1. Installs dependencies from `requirements.txt`
2. Runs Django `collectstatic`
3. Executes PyInstaller with all necessary configurations
4. Creates required directories (`application`, `applications`, `content_generated`, etc.)
5. Copies required payloads into the installed application root, including `README.md` and the bundled `jd-cli/` directory, while still treating `config.json` and `prompt.pmt` as optional copies
6. Runs database migrations
7. Creates a default superuser
8. Renames the executable to `Tlamatini.exe`
9. Copies agent templates
10. Bundles support scripts into `dist/manage/`:
   - `register_flw.ps1` / `unregister_flw.ps1` — `.flw` file association
   - `CreateShortcut.ps1` / `RemoveShortcut.ps1` — desktop & local shortcuts
   - `Tlamatini.ps1` — PowerShell launcher
   - `CreateShortcut.json`, `Tlamatini.ico`
11. Generates **`pkg.zip`** from the `dist/manage/` directory

**Output:** `pkg.zip` at the project root (contains the entire packaged application).

Current `build.py` is stricter than older builds: it now treats `README.md` and `jd-cli/` as required post-build assets, verifies that `jd-cli/jd-cli.bat` is present in the copied payload, and exits non-zero instead of silently shipping a partial package when those required artifacts are missing.

### Step 2: Build the Uninstaller (`build_uninstaller.py`)

```bash
python build_uninstaller.py
```

This builds `uninstall.py` into a single-file executable using PyInstaller `--onefile` mode. It:

1. Gathers Tcl/Tk libraries and system DLLs required by the Tkinter GUI
2. Runs PyInstaller with `--onefile --windowed` to produce a single portable `.exe`
3. Copies the resulting `Uninstaller.exe` to the **project root**
4. Cleans up all intermediate build artifacts (`build/`, `dist/`, `.spec`)

**Output:** `Uninstaller.exe` at the project root.

> **Why `--onefile`?** The Uninstaller is built as a single file (unlike the Installer which uses `--onedir`) so it can sit alongside `Installer.exe` without conflicting `_internal/` directories.

### Step 3: Build the Installer (`build_installer.py`)

```bash
python build_installer.py
```

**Requires:** `pkg.zip` (from Step 1) and `Uninstaller.exe` (from Step 2) at the project root.

This builds `install.py` into the Installer executable. It:

1. Generates a splash screen image (shown immediately on double-click)
2. Runs PyInstaller with `--onedir --windowed` and splash support
3. Copies `pkg.zip` into `dist/Installer/` (with SHA-256 verification)
4. Copies `Uninstaller.exe` into `dist/Installer/`
5. Assembles the final release folder at `dist/Tlamatini_Release/`
6. Verifies the integrity of `pkg.zip` inside the release folder

**Output:** `dist/Tlamatini_Release/` — the complete distributable release.

### Release Distribution

After all three steps complete:

1. Navigate to `dist/Tlamatini_Release/`
2. Zip the **entire folder** contents
3. Distribute the zip to end users

Users extract the zip and double-click `Installer.exe` to install. No admin privileges are required.

### What the Installer Does

When an end user runs `Installer.exe`, it:

1. Presents a Tkinter GUI to choose the installation directory
2. Extracts `pkg.zip` into `<install_path>/Tlamatini/`
3. Secures agent virtual environments (locks permissions)
4. Writes `config.json` with installation settings
5. Copies `Uninstaller.exe` into the installed directory
6. Creates desktop and local shortcuts (`Tlamatini.lnk`)
7. Registers the `.flw` file extension to open with Tlamatini
8. Runs its PowerShell helper scripts and Explorer restart logic with a cleaned environment when frozen, so PyInstaller bundle DLL paths do not stall or lock those helper subprocesses

### What the Uninstaller Does

When an end user runs `Uninstaller.exe` from the installed directory, it:

1. Removes desktop and local shortcuts (with Explorer restart for immediate effect)
2. Unregisters the `.flw` file association and clears cached shell state
3. Deletes all application files **except** `<install_path>/Tlamatini/agents/*` (preserving user-created agents and their data)
4. Removes the installation directory if empty after cleanup

---

## Core Components

### RAG System

The RAG system (`agent/rag/`) provides intelligent document retrieval:

```python
from agent.rag import setup_llm_with_context, ask_rag

# Create a RAG chain with context
rag_chain = setup_llm_with_context("/path/to/project", "filename.py")

# Query the chain
response = ask_rag(rag_chain, "How does the authentication work?", chat_history=[])
```

**Key Features:**
- **Metadata Extraction**: Parses code to identify classes, functions, imports
- **Architectural Classification**: Labels files by role (controller, model, service, etc.)
- **Dependency Tracking**: Maps file relationships and imports
- **Hybrid Search**: Combines semantic (FAISS) and keyword (BM25) retrieval
- **Context Budgeting**: Allocates token budget by document priority

**Supported File Types:**
- Python (`.py`) - Classes, functions, decorators, imports
- Java (`.java`) - Packages, classes, methods
- JavaScript/TypeScript (`.js`, `.ts`, `.tsx`) - Components, exports
- HTML (`.html`) - Links, forms, structure
- Configuration (`.json`, `.yaml`, `.xml`) - Dependencies, settings
- Documentation (`.md`, `.txt`) - Content, headings

#### Memory-Insufficient Context Fallback

Tlamatini now treats low-memory embedding failures as a degraded-mode scenario rather than a hard loss of loaded context.

When source files are loaded successfully but FAISS or embedding construction fails because the selected Ollama model cannot allocate enough memory, the system does **not** discard the loaded files. Instead, it:

1. Preserves the already loaded documents in memory
2. Builds a packed fallback context block directly from those loaded files
3. Injects that fallback context into the prompt-only or unified-agent path
4. Continues answering from the loaded project code even though semantic retrieval is temporarily unavailable

This is important because it separates two failure domains:

- **Document loading succeeded**: The project files were read correctly and remain usable
- **Embedding/vector build failed**: Semantic retrieval could not start, usually because the local model exceeded available RAM

In practical terms, this means Tlamatini can still summarize code, explain loaded files, and answer questions grounded in the already loaded context even during memory pressure. What degrades is retrieval quality and ranking depth, not total access to the loaded source code.

Typical trigger example:

- Ollama returns an error such as `model requires more system memory ... than is available`

Expected behavior after this fallback:

- The chat stays grounded in the loaded files instead of claiming the context is empty
- File manifests and packed source excerpts remain available to the answering chain
- The packed fallback blob is propagated into both `BasicPromptOnlyChain` and `UnifiedAgentChain`, and the current test suite includes explicit regression coverage for both paths
- The system continues operating in a reduced-capability mode until embeddings can be built again

This fallback is especially valuable on constrained developer machines, remote desktops, or shared environments where larger embedding models may intermittently fail to initialize.

### RAG Chain Types

The system dynamically selects the appropriate chain type based on configuration and context:

| Chain | Class | Use Case |
|-------|-------|----------|
| **BasicPromptOnlyChain** | `rag/chains/basic.py` | No documents loaded; uses LLM with conversation history and history summarization |
| **HistoryAwareNoDocsChain** | `rag/chains/history_aware.py` | History-aware conversations without document retrieval |
| **OptimizedHistoryAwareRAGChain** | `rag/chains/history_aware.py` | Full RAG with FAISS+BM25 retrieval, document reranking, context compression, and history summarization |
| **UnifiedAgentChain** | `rag/chains/unified.py` | Chat with tool-calling capabilities (no document retrieval) |
| **UnifiedAgentRAGChain** | `rag/chains/unified.py` | Full RAG combined with LangGraph tool-calling agent |

All chains support:
- **Streaming**: Token-by-token output via custom `Callbacks` handler
- **Cancellation**: User-initiated generation stop via `GenerationCancelledException`
- **History summarization**: Automatic compression when conversation exceeds token thresholds
- **Question contextualization**: Reformulates follow-up questions into standalone queries
- **Connection abort**: Aggressive httpx client termination on cancellation for fast response

### Unified Agent with Tools

The unified agent (`agent/mcp_agent.py`) enables tool calling:

```python
from agent.mcp_agent import create_unified_agent

agent = create_unified_agent(llm, system_prompt)
result = agent.invoke({
    "input": "Run the tests and show me the results",
    "multi_turn_enabled": True,
})
```

The current chat implementation is no longer a single opaque agent-executor hop. `create_unified_agent()` now builds a `CapabilityAwareToolAgentExecutor`, which can either:

- preserve the legacy full-tool, one-shot-compatible execution path, or
- switch into the Multi-Turn orchestration path with request-scoped context selection, dynamic tool binding, and planner guidance

This separation is deliberate and is now one of the most important architectural guarantees in the repository.

#### Multi-Turn Tool Loop

The explicit loop still remains the core execution primitive:

1. Build or select the tool surface for the current request.
2. Bind those tools to the configured unified-agent model.
3. Send the user request plus the system prompt to the model.
4. If the model emits `tool_calls`, execute them directly in the backend.
5. Append each tool result as a `ToolMessage`.
6. Re-invoke the model until it returns a final answer or the iteration limit is reached.

If the planner produces a `context_only` path with no selected tools, the executor still uses the same request-scoped pathway but falls back to a direct model answer with the planner summary injected as a system instruction.

The current default iteration limit is `100` turns unless `unified_agent_max_iterations` is explicitly set in `config.json`.

#### Capability Selection and Context Prefetch

Checked Multi-Turn requests now use `capability_registry.py` as the Phase 1 and Phase 2 selector layer.

For tools and wrapped agents, the selector:

- scores normal tools, template-agent tools, wrapped chat-agent launchers, and run-control tools
- uses aliases, example requests, security hints, and token overlap against the current request
- automatically includes runtime follow-up tools when wrapped agents or `run_id`-style monitoring requests are detected
- run-control tools (`chat_agent_run_list/status/log/stop`) are excluded from scoring-floor calculations and auto-injected when wrapped agents are selected, preventing them from inflating the threshold and crowding out actual agent tools
- up to 50 tools can be selected per request (matching the full agent catalogue), with the scoring threshold as the real filter rather than an artificial hard cap

For MCP-backed context prefetch, the selector currently supports:

- `system_context`
- `files_context`

Those contexts are fetched selectively from `rag/factory.py` only when Multi-Turn is enabled. When Multi-Turn is disabled, the old prefetch behavior is preserved exactly.

This is the key Phase 1 and Phase 2 shift: all capabilities remain available to the system, but only the relevant subset is surfaced and prefetched for the current request.

#### Global Execution Planner

Checked Multi-Turn requests also use `global_execution_planner.py`, which introduces a real request-scoped execution DAG.

The planner produces:

- a planner version identifier
- an execution mode: `direct_model`, `context_only`, or `tool_augmented`
- selected MCP contexts
- selected tool/agent names
- planner notes
- explicit DAG nodes

The current node stages are:

1. `prefetch`
2. `execute`
3. `monitor`
4. `answer`

This means the request path is no longer just "LLM sees all tools and decides." Instead, a checked Multi-Turn request can now be pre-shaped into a concrete orchestration graph that says, in effect:

- fetch these contexts first
- execute these tool/agent stages next
- monitor these wrapped runs if needed
- then synthesize the final answer

The planner summary is injected into the executor so the model is guided by the already-selected execution plan instead of re-discovering the whole capability surface from scratch.

**Scoring and selection details:**

- Each tool is scored against the request using name matching (+14 for exact tool-name match), alias/hint phrase matching (+10-12), example-request token overlap (+up to 3), and description token overlap (+up to 10)
- Run-control tools are excluded from the scoring floor calculation since they are auto-injected whenever wrapped agents are selected
- Every tool scoring above the entry threshold (6 when MCP contexts are active, 2 otherwise) is selected, up to a maximum of 50 tools per request
- The planner, capability selector, and tool executor all emit detailed `INFO`-level logs (prefixed `[Planner._select]`, `[tools._launch_wrapped_chat_agent]`, etc.) visible in the Django console for debugging tool selection issues

#### Wrapped Chat-Agent Runtime Tools

The wrapped runtime layer remains the second execution tier above classic MCP tools: the main chat can launch isolated runtime copies of selected workflow-agent templates via `chat_agent_*` tools.

The current wrapped launchers are:

- `chat_agent_crawler`
- `chat_agent_send_email`
- `chat_agent_executer`
- `chat_agent_gitter`
- `chat_agent_sqler`
- `chat_agent_ssher`
- `chat_agent_scper`
- `chat_agent_pythonxer`
- `chat_agent_dockerer`
- `chat_agent_kuberneter`
- `chat_agent_jenkinser`
- `chat_agent_mongoxer`
- `chat_agent_file_creator`
- `chat_agent_file_extractor`
- `chat_agent_file_interpreter`
- `chat_agent_image_interpreter`
- `chat_agent_summarize_text`
- `chat_agent_pser`
- `chat_agent_notifier`
- `chat_agent_shoter`
- `chat_agent_telegramer`
- `chat_agent_whatsapper`
- `chat_agent_apirer`
- `chat_agent_prompter`
- `chat_agent_monitor_log`
- `chat_agent_monitor_netstat`
- `chat_agent_kyber_keygen`
- `chat_agent_kyber_cipher`
- `chat_agent_kyber_deciph`
- `chat_agent_move_file`
- `chat_agent_deleter`
- `chat_agent_recmailer`

#### Runtime Isolation and Lifecycle

Wrapped chat-agent tools do **not** mutate the template agent directories in place. Instead, the backend:

1. Copies the selected template agent into a **unique, sequenced directory** under `agent/agents/pools/_chat_runs_/{agent}_{seq}_{id}/`
2. Parses natural-language `key=value` assignments from the request and applies them to the runtime `config.yaml`
3. Rejects launches that are still missing mandatory non-flow parameters
4. Starts the runtime copy as a detached subprocess
5. Persists run metadata in the `ChatAgentRun` model
6. Returns structured JSON including `run_id`, `status`, `runtime_dir`, `log_path`, and `log_excerpt`

**Sequenced runtime directories** ensure that every invocation — including retries and failures — is preserved for inspection. The naming format is `{agent_type}_{sequence:03d}_{short_run_id}`, for example:

```
_chat_runs_/
├── executer_001_a1b2c3d4/    ← 1st try (failed)
├── executer_002_e5f67890/    ← 2nd try (failed)
├── file_creator_003_1234abcd/ ← 3rd overall (different agent)
├── executer_004_deadbeef/    ← 3rd try of executer (succeeded)
└── notifier_005_cafe0123/    ← 5th overall
```

The global sequence counter is thread-safe (monotonically increasing across all agent types) and re-seeds from existing directories on server restart so numbers never collide. Failed runs are **never overwritten**, allowing the user to inspect the full execution history, logs, and configs of every attempt.

Follow-up inspection/control is exposed through four runtime tools:

- `chat_agent_run_list`
- `chat_agent_run_status`
- `chat_agent_run_log`
- `chat_agent_run_stop`

These wrapped runtimes are intentionally isolated from ACP flow control. The current `/check_all_agents_status/`, `/get_session_running_processes/`, and `/kill_session_processes/` views skip the `_chat_runs_` pool subtree, so pausing or stopping a canvas flow does not accidentally kill chat-launched wrapped runtimes.

For checked Multi-Turn requests, launch behavior was also hardened to suppress visible console popups. Request-scoped state flags now let the same runtime-launch helpers choose:

- legacy visible console behavior when Multi-Turn is unchecked
- detached/headless background launch behavior when Multi-Turn is checked

#### Legacy Compatibility Guarantee

The unchecked path is intentionally conservative.

When `multi_turn_enabled` is false:

- `ask_rag()` keeps the original prompt-shape validation
- the legacy context prefetch path remains active
- the executor binds the full enabled tool surface
- planner output, if present, is ignored
- visible console launch behavior remains unchanged

This guarantee matters because the Multi-Turn implementation was added as an opt-in execution characteristic, not as a breaking rewrite of the original chat system.

#### Frozen-Mode and Runtime Behavior

The Multi-Turn implementation now also carries frozen-build awareness in the supporting runtime code:

- `config_loader.py` resolves `CONFIG_PATH`, then executable-local `config.json`, then module-local `config.json`
- `FileSearchRAGChain` resolves its default `config.json` from the executable directory in frozen mode
- template-agent discovery checks both `<install_dir>/agents` and `<install_dir>/Tlamatini/agent/agents`
- wrapped runtime/background launch helpers adapt correctly to frozen execution
- `_get_agents_root()` in `chat_agent_runtime.py` resolves from `sys.executable` in frozen mode, from `__file__` in source mode — both paths are logged at `INFO` level with absolute paths for easy debugging
- `_resolve_python_executable()` tries `PYTHON_HOME`, then bundled `python.exe` beside the frozen executable, then falls back to PATH — each decision is logged

This matters because the Multi-Turn path depends on file context, wrapped runtimes, and config-driven behavior that must work both from source and from the packaged desktop build. All path resolution decisions are now logged with absolute paths so that frozen-mode issues can be diagnosed from the console output alone.

### Agentic Workflow Designer

Access via `/agentic_control_panel/` URL. Features:
- Drag-and-drop agent placement from sidebar
- Visual connection drawing between agents
- Start/Stop/Pause controls
- Hover tooltips in the sidebar that show each agent's purpose
- Right-click canvas actions for Configure, Description, See log, Explore dir..., Open cmd..., and Restart (when enabled)
- **Pause/Resume**: Pause stores the session's running agents in `paused_agents.reanim`, kills the active processes without clearing logs or `.pos` reanimation files, and moves the ACP into the paused state. Resume reanimates the stored agents with `AGENT_REANIMATED=1` so they preserve logs and reload their `reanim*` state files
- Real-time LED status indicators: green (running), red (not running while the flow is active), yellow blinking (paused), gray (stopped/idle)
- Log viewer for debugging
- Save/Load workflows as `.flw` files
- Undo/Redo with 1024 action history
- Agent restart and process management
- Session-scoped pool directories
- Canvas auto-configuration (connections auto-populate agent configs)
- Flow validation with detailed error reporting

#### Canvas Context Menus and Agent Descriptions

The ACP now uses the `Purpose` column text from the `## Workflow Agents` tables in this README as live UI content. On page render, `agentic_control_panel()` loads those Purpose values into an `agent_purpose_map`, injects that JSON into `agentic_control_panel.html`, and the frontend uses it in two places:

1. **Sidebar hover tooltips**: Hovering an agent in the left-hand agent list shows the current README-backed purpose text in a floating tooltip.
2. **Canvas Description dialog**: Right-clicking a deployed agent instance and selecting **`Description`** opens a draggable modal showing the same purpose text for that agent.

The formatter is intentionally minimal and matches the current frontend code: inline code spans, `**bold**`, and `<br>` line breaks render, while arbitrary HTML remains escaped.

The same right-click menu also exposes deployed-instance actions that operate on the current session pool rather than on template folders under `agent/agents/`:

- **`See log`** tails the selected deployed agent's log.
- **`Explore dir...`** opens File Explorer in the selected deployed agent-instance directory.
- **`Open cmd...`** opens `cmd.exe` with its working directory set to that deployed agent-instance directory.

Internally the backend converts a canvas id such as `counter-1` into its session-pool folder (for example `counter_1`) through `get_pool_path()` plus strict path validation. This keeps the context-menu actions tied to the correct deployed instance in both development mode and frozen/installed builds.

#### Pause, Stop, and Reanimation of a Flow

The Agentic Control Panel entry point is `agentic_control_panel.html`. These controls are stateful and intentionally distinct. For long-running flows, Pause is the cost-control action: it halts the current session's running processes without discarding their resumable context. That matters when the flow includes non-deterministic agents that may keep polling, classifying, summarizing, or calling remote APIs and metered models. While the flow is paused, those processes are no longer running, so further model/API consumption can stop until the user explicitly resumes the flow.

1. **Fresh start (`STOPPED` -> `RUNNING`)**: Pressing Start from a stopped flow triggers a new execution. The frontend first kills leftover session processes, ensures every canvas agent exists in the session pool, clears agent logs, and then launches the Starter agents.
2. **Pause capture (`RUNNING` -> `PAUSED`)**: When Pause is pressed, the frontend asks `/get_session_running_processes/` for the current session's live agents and sends that list to `/save_paused_agents/`. The backend stores the result as `paused_agents.reanim` inside the current session pool directory, under a `paused_agents` key. The frontend also keeps the same list in browser memory for paused-state tracking, then kills the session processes through `/kill_session_processes/`. This preserves logs and existing `reanim*` artifacts so the flow can be resumed later instead of restarted from scratch.
3. **Resume trigger (`PAUSED` -> `RUNNING`)**: Reanimation is only available while the ACP is still in `PAUSED`. If the user presses Start, or presses Pause again while already paused, the frontend loads `paused_agents.reanim` through `/load_paused_agents/`. If that file is missing, the frontend falls back to its in-memory paused-process list. If neither source has agents, the ACP returns to `STOPPED` instead of inventing a restart path.
4. **Reanimation request and backend contract**: Before calling the backend, the frontend reduces the stored process list to unique `{canvas_id, folder_name, script_name}` records and sends them to `/reanimate_agents/`. The backend resolves each `folder_name` under the current session pool, verifies that the corresponding `script_name` still exists, starts that script as a detached subprocess, and rewrites the agent's `agent.pid` file. Reanimated subprocesses receive `AGENT_REANIMATED=1`, which is how agent templates know to preserve existing log files and reload the `reanim*` artifacts they implement, such as `reanim.pos` or `reanim.counter`, instead of behaving like a fresh launch. After the reanimation request returns, the frontend deletes `paused_agents.reanim` through `/delete_paused_agents/` and moves the ACP back to `RUNNING`.
5. **Stop (`RUNNING` -> `STOPPED`)**: Stop is the graceful shutdown path, and it is driven by Ender agents rather than by the pause file. The ACP requires at least one Ender agent on the canvas, executes all Enders in parallel, polls until each Ender's log file is seen as modified after the stop request, then marks the flow as stopped, stops the system-managed FlowHypervisor, and calls `/clear_pos_files/` to remove `.pos` reanimation-position files for the current session.
6. **Stop after a pause (`PAUSED` -> `STOPPED`)**: A paused flow has already had its processes killed. If the user presses Stop from that state, the ACP exits the reanimation path, clears `.pos` files with `/clear_pos_files/`, and the next Start is treated as a fresh run rather than as a resume.
7. **LED semantics**: During normal execution, each canvas LED is green when that canvas agent is running and red when the flow is active but that agent is not running. In the stopped state all LEDs are gray. In the paused state all canvas agents switch to a yellow blinking LED, regardless of which ones were running at the moment of pause.

#### Flow Validation

Before executing a workflow, the Validate button builds an NxN adjacency matrix from all deployed pool agents and applies the current structural rules implemented in `acp-validate.js`:

| Check | Rule | Example Violation |
|-------|------|-------------------|
| **V1** | Starter agents have no incoming connections | Another agent targeting a Starter |
| **V2** | Ender output agents can only be Cleaner or FlowBacker | Ender targeting an Executer |
| **V2b** | Ender must not launch Cleaner directly when it also launches FlowBacker | Ender launching Cleaner and FlowBacker in parallel |
| **V3** | Cleaner agents only receive input from Ender or FlowBacker | Cleaner connected to a Monitor |
| **V3b** | Cleaner must be triggered by either Ender or FlowBacker, never both in the same branch | Mixed Ender and FlowBacker input into one Cleaner |
| **V4** | FlowBacker agents only receive input from Starter, Ender, Forker, or Asker | FlowBacker connected from Monitor Log |
| **V5** | FlowBacker output agents can only be Cleaner | FlowBacker targeting Executer |
| **V6** | No self-connections (diagonal must be zero) | Agent targeting itself |
| **V7** | All non-Starter agents have at least one input | Orphaned agent with no upstream |
| **V8** | Referenced agents exist and accept input connections where required | Dangling reference or targeting a Starter |

The validation endpoint (`/validate_flow/`) lists all deployed agents in the session pool, loads their configurations, builds the connection matrix, and runs the full rule set above. Results are displayed in a dialog with per-agent error details and suggestions.

### MCP Integration

Tlamatini implements two MCP servers that start automatically on application boot (via `apps.py` ready hook):

**System Metrics Server (WebSocket on port 8765)**:
- `mcp_system_server.py` -> `MCPSystemHandler` class
- CPU usage detection via `typeperf` (Windows) or `/proc/stat` (Linux)
- Memory tracking via `GlobalMemoryStatusEx` (Windows) or `psutil`
- Disk space monitoring via `shutil.disk_usage()`
- Client: `mcp_system_client.py` connects via WebSocket
- Chain: `chain_system_lcel.py` (`SystemRAGChain`) provides intelligent context from metrics

**File Search Server (gRPC on port 50051)**:
- `mcp_files_search_server.py` -> `FileSearcherServicer` class
- Windows known-folder path resolution via `win32com.shell`
- Pattern matching with `fnmatch`, hidden file filtering
- Protobuf definitions: `filesearch.proto`, `filesearch_pb2.py`, `filesearch_pb2_grpc.py`
- Client: `mcp_files_search_client.py` connects via gRPC
- Chain: `chain_files_search_lcel.py` (`FileSearchRAGChain`) provides intelligent file content retrieval

### Database Models

The application uses Django ORM with SQLite and currently defines 13 models in `agent/models.py`:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| **AgentMessage** | Chat messages between users and LLM | `user` (FK->User), `conversation_user` (FK->User, per-user history isolation), `message`, `timestamp` |
| **LLMProgram** | Stored code programs with metadata | `programName`, `programLanguage`, `programContent` |
| **LLMSnippet** | Code snippets with language info | `snippetName`, `snippetLanguage`, `snippetContent` |
| **Prompt** | Reusable prompt templates | `promptName`, `promptContent` |
| **Omission** | Patterns to exclude/redact from context | `omissionName`, `omissionContent` |
| **ContextCache** | SHA1 hash-based query context caching | `query_hash` (unique), `context_blob`, `timestamp` |
| **Mcp** | MCP (Model Context Protocol) definitions | `mcpName`, `mcpDescription`, `mcpContent` |
| **Tool** | Tool definitions for the unified agent | `toolName`, `toolDescription`, `toolContent` |
| **Agent** | Agent metadata and configuration | `agentName`, `agentDescription`, `agentContent` |
| **AgentProcess** | Running process tracking (PID registry) | `agentProcessDescription`, `agentProcessPid` |
| **ChatAgentRun** | Runtime metadata for chat-launched wrapped template agents | `runId`, `toolDescription`, `templateAgentDir`, `runtimeDir`, `logPath`, `pid`, `status`, `exitCode`, `startedAt`, `finishedAt` |
| **Asset** | Asset definitions | `assetName`, `assetDescription`, `assetContent` |
| **SessionState** | Per-user session persistence (24-hour expiry) | `user` (1:1->User), `context_path`, `context_type`, `context_filename`, `last_active` |

### Design Patterns

The codebase employs several well-established design patterns:

| Pattern | Implementation | Location |
|---------|---------------|----------|
| **Singleton** | Thread-safe global state manager | `agent/global_state.py` |
| **Factory** | Creates appropriate RAG chain based on config | `agent/rag/factory.py` |
| **Chain of Responsibility** | Layered chain selection (Basic -> History -> RAG) | `agent/rag/chains/` |
| **Observer** | Token-by-token callbacks with cancellation | `agent/rag/chains/base.py` |
| **Strategy** | Switchable retrieval strategies (Vector, BM25, RRF) | `agent/rag/retrieval.py` |
| **State Machine** | LangGraph-based agent execution loops | `agent/agents/notifier/`, `agent/agents/recmailer/` |
| **Template Method** | Common agent structure: load -> validate -> execute -> log | `agent/agents/*/` |
| **Decorator** | LangChain `@tool` for function-based tools | `agent/tools.py` |

### Claude API Client

The included Claude client (`agent/opus_client/`) provides full Anthropic API support:

```python
from agent.opus_client.claude_opus_client import ClaudeClient, Model

client = ClaudeClient(model=Model.OPUS_4_5)
response = client.chat("Explain quantum computing")

# With images
response = client.chat_with_image("Describe this", "image.jpg")

# With tools
tool = client.create_tool(name="calculator", ...)
response = client.chat("What is 15% of 200?", tools=[tool])
```

### Image Analysis

Tlamatini supports two image analysis backends:

**Claude Opus (Cloud)** - `opus_analyze_image` tool:
- Uses the Anthropic API via `ClaudeClient`
- Requires `ANTHROPIC_API_KEY` in config.json
- High-quality image descriptions and analysis

**Qwen / Ollama Vision (Local)** - `qwen_analyze_image` tool:
- Uses any Ollama-hosted vision model (e.g., Qwen, LLaVA)
- Converts images to base64 and sends via Ollama REST API
- Streaming response with configurable parameters
- No cloud API key required

---

## Available Tools

Tools can be individually enabled/disabled via the Tools Dialog in the chat interface.

### Core Tools

| Tool | Description | Example Usage |
|------|-------------|---------------|
| `get_current_time` | Returns current datetime | "What time is it?" |
| `execute_file` | Runs Python scripts in a new terminal | "Run the test script at /path/script.py" |
| `execute_command` | Executes shell commands | "List files in the current directory" |
| `execute_netstat` | Network diagnostics | "Show network connections" |
| `launch_view_image` | Opens images in a viewer | "Show me the screenshot" |
| `unzip_file` | Extracts ZIP archives | "Extract archive.zip to /output" |
| `decompile_java` | Decompiles JAR/WAR files | "Decompile the application.jar" |
| `opus_analyze_image` | Image analysis with Claude | "Describe with Opus the image photo.jpg" |
| `qwen_analyze_image` | Image analysis with Qwen/Ollama | "Describe the image diagram.png" |
| `agent_parametrizer` | Parametrize a template agent from chat | "Configure the template emailer agent with sender_email='ops@example.com'" |
| `agent_starter` | Start a template workflow agent from chat | "Start the monitor_log agent" |
| `agent_stopper` | Stop a template workflow agent from chat | "Stop the emailer agent" |
| `agent_stat_getter` | Check template-agent runtime status | "Is the monitor_log agent running?" |

### Wrapped Chat-Agent Tools

Wrapped chat-agent launchers create isolated, sequenced runtime copies of selected template agents under `agent/agents/pools/_chat_runs_/{agent}_{seq}_{id}/` and return structured JSON with run metadata. Each invocation gets its own directory — failed runs are preserved for inspection.

| Family | Tool Names | Purpose |
|--------|------------|---------|
| Execution and file actions | `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_pser`, `chat_agent_move_file`, `chat_agent_deleter` | Command execution, inline Python, process inspection, and file movement/deletion |
| DevOps and infrastructure | `chat_agent_gitter`, `chat_agent_dockerer`, `chat_agent_kuberneter`, `chat_agent_jenkinser`, `chat_agent_ssher`, `chat_agent_scper` | Git, Docker, Kubernetes, Jenkins, SSH, and SCP operations |
| Data and interpretation | `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_file_creator`, `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`, `chat_agent_summarize_text` | SQL/MongoDB access, file creation/extraction, multimodal file interpretation, and summarization |
| Notifications and comms | `chat_agent_send_email`, `chat_agent_notifier`, `chat_agent_telegramer`, `chat_agent_whatsapper`, `chat_agent_recmailer` | Outbound/inbound notification and messaging workflows |
| Crawling, monitoring, APIs, prompting, and crypto | `chat_agent_crawler`, `chat_agent_monitor_log`, `chat_agent_monitor_netstat`, `chat_agent_shoter`, `chat_agent_apirer`, `chat_agent_prompter`, `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph` | Crawling, monitoring, screenshots, API calls, sub-prompts, and Kyber operations |

#### Wrapped Runtime Lifecycle Tools

| Tool | Description | Typical Follow-Up |
|------|-------------|-------------------|
| `chat_agent_run_list` | List recent wrapped chat-agent runs, capped by `chat_agent_limit_runs` from `config.json` | Get a `run_id` to inspect |
| `chat_agent_run_status` | Inspect the current status of a wrapped runtime | Poll a running wrapped agent |
| `chat_agent_run_log` | Read the latest log excerpt for a wrapped runtime | Inspect progress or failure details |
| `chat_agent_run_stop` | Stop a wrapped runtime by `run_id` | Cancel a long-running wrapped agent |

---

## Workflow Agents

Pre-built agents for the visual workflow designer, organized by category. **57 agent types** total.

The `Purpose` text in the agent tables below is no longer documentation-only. The ACP now parses these table rows from `README.md` and uses them as the live source for sidebar agent-purpose tooltips and the canvas **Description** dialog, so edits to a Purpose cell affect both the documentation and the UI text shown to users.

### Agent Architecture

All workflow agents follow a common structural pattern:

1. **Config loading**: Read `config.yaml` from the agent's pool directory
2. **PID management**: Write `agent.pid` for process tracking; remove on exit
3. **Logging**: `FlushingFileHandler` writes to `<agent_name>.log` with immediate flush for real-time visibility
4. **Reanimation**: All agents detect the `AGENT_REANIMATED=1` environment variable. On fresh start, agents truncate their own log files and log a "STARTED" marker. On reanimation (resume from pause), agents preserve their log files, log a "🔄 REANIMATED" marker, and load `reanim*` state files (e.g., `reanim.pos` for file offsets, `reanim.counter` for counter state) to continue from the saved state each agent persists
5. **Pool navigation**: Agents resolve sibling agent directories relative to their pool root (supports both frozen/PyInstaller and development modes)
6. **Subprocess spawning**: Target agents are started as new processes using the resolved Python command
7. **Concurrency guard**: Before starting any target agents, the caller waits until ALL targets have stopped running. If they are still running after 10 seconds, an ERROR is logged every 10 seconds until they stop. The agent NEVER proceeds to start targets while any of them are still alive — this prevents duplicate/orphaned processes in looping flows
8. **Cardinal naming**: Deployed agents get numeric suffixes (e.g., `monitor_log_1`, `emailer_2`)

Agents are classified as:
- **Deterministic** (no LLM): `starter`, `ender`, `stopper`, `cleaner`, `executer`, `pythonxer`, `sqler`, `mongoxer`, `sleeper`, `deleter`, `mover`, `shoter`, `mouser`, `keyboarder`, `raiser`, `croner`, `asker`, `forker`, `counter`, `ssher`, `scper`, `gitter`, `dockerer`, `telegramer`, `telegramrx`, `and`, `or`, `kuberneter`, `apirer`, `jenkinser`, `gatewayer`, `gateway_relayer`, `node_manager`, `file_creator`, `file_extractor`, `j_decompiler`, `flowbacker`, `barrier`, `kyber_keygen`, `kyber_cipher`, `kyber_decipher`, `parametrizer`
- **LLM-powered**: `monitor_log` (LLM-based log analysis), `monitor_netstat` (port monitoring), `notifier` (LangGraph state machine), `emailer` (SMTP), `recmailer` (IMAP + LLM), `whatsapper` (TextMeBot + LLM), `prompter` (Ollama prompting), `flowcreator` (AI flow design), `pser` (LLM-powered process finder), `crawler` (web crawling + LLM analysis), `summarizer` (log monitoring + LLM event detection), `flowhypervisor` (system-managed LLM flow anomaly detection), `file_interpreter` (document parsing + optional LLM summarization), `image_interpreter` (LLM vision-based image analysis)

### Control Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **starter** | Initiates workflow execution | `target_agents`: List of agents to start<br>`exit_after_start`: Boolean |
| **ender** | Terminates all agents in target_agents, then launches post-termination agents such as FlowBackers or Cleaners | `target_agents`: Agents to KILL<br>`source_agents`: Graphical input connections only (never killed/started)<br>`output_agents`: Agents to LAUNCH after termination (typically FlowBackers and/or Cleaners). Also auto-discovers Cleaners in pool. |
| **stopper** | Single-threaded pattern-based agent terminator. Monitors source agent logs and kills agents when patterns are detected. Sequential polling of all source agents. Does NOT start downstream agents. | `source_agents`: Agents to monitor and terminate<br>`patterns`: One pattern per source agent<br>`poll_interval`: Check frequency<br>`output_agents`: Canvas wiring only (not used for starting agents) |

### Monitoring Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **monitor_log** | LLM-based log file monitoring | `logfile_path`: Log to watch<br>`keywords`: ERROR, FATAL, WARN, etc.<br>`outcome_word`: TARGET_FOUND<br>`poll_interval`: Check frequency |
| **monitor_netstat** | Network connection monitoring | Similar to monitor_log |
| **flowhypervisor** | System-managed LLM anomaly detector with reanimation support, incremental log reading, NxN connection matrix analysis, user-configurable supervision instructions, and dual-layer auto-stop: the core system polls `flow_alive` and stops the agent immediately when no non-system agents are running; the agent also self-stops after 3 idle cycles as a safety net for when the core/browser is killed or frozen | `llm.model`: Ollama model<br>`llm.host`: Ollama URL<br>`llm.temperature`: LLM temperature<br>`monitoring_poll_time`: Check frequency (default: 10s)<br>`user_instructions`: Custom directives appended to the monitoring prompt |

### Notification Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **notifier** | LangGraph-based event notification agent that monitors source agent logs for configurable string patterns and triggers frontend notifications and downstream agents | `source_agents`: List of agent names whose logs to monitor<br>`target.search_strings`: Comma-separated patterns to detect (e.g., `"ERROR, FATAL, EXCEPTION"`)<br>`target.poll_interval`: Seconds between log checks (default: 2)<br>`target.sound_enabled`: Enable browser notification sound<br>`target.shutdown_on_match`: Exit after first match<br>`target_agents`: Downstream agents to start on detection |
| **emailer** | Send email notifications via SMTP | `smtp_server`, `smtp_port`: Server config<br>`sender_email`, `sender_password`: Credentials<br>`recipient_emails`: List of recipients<br>`email_subject`, `email_body`: Content |
| **recmailer** | IMAP email receiver with LLM analysis. Monitors an inbox for new emails, uses an LLM to classify content against keywords, and logs matches. Built on LangGraph StateGraph. | `imap.host`, `imap.port`: IMAP server<br>`imap.username`, `imap.password`: Credentials<br>`keywords_or_phrases`: Keywords to detect<br>`llm.model`: Ollama model for analysis<br>`outcome_word`: Marker written on match |
| **whatsapper** | WhatsApp notification agent. Monitors source agent logs in parallel threads for keywords, uses LLM to summarize issues, and sends alerts via TextMeBot API. | `source_agents`: Agents to monitor<br>`keywords`: Detection patterns<br>`llm.model`: Ollama model for summarization<br>`textmebot.phone`: Recipient phone number<br>`textmebot.apikey`: TextMeBot API key<br>`poll_interval`: Check frequency |
| **telegramer** | Send Telegram notifications | `telegram_bot_token`: Token<br>`telegram_chat_id`: Receiver<br>`message`: Content |
| **telegramrx** | Telegram receiver / monitor bot | Monitor incoming Telegram messages using Telegram Bot API |

**Notifier Architecture Details:**
- Built on **LangGraph StateGraph** with a continuous-loop state machine (`tools -> tools`)
- Maintains per-source-agent **file offsets** for incremental log reading (no reprocessing)
- Supports **reanimation** via `reanim.pos` file (survives agent restarts without re-reading old data)
- Handles **log rotation** detection (file size shrinks -> offset reset)
- Writes `notification.json` files that the frontend polls for real-time browser alerts
- Each match triggers all configured `target_agents` via subprocess spawning
- Supports **`outcome_detail`** parameter: an optional descriptive caption displayed in the notification dialog below the detected pattern, giving the user human-readable context about what the detection means (e.g., *"The remote server state file has changed from its baseline value. Immediate review recommended."*)

### Action Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **executer** | Execute shell commands | `command`: Shell command string<br>`target_agents`: Downstream agents |
| **pythonxer** | Execute Python scripts with Ruff linting validation. Triggers downstream agents only if script exits with code 0 (True). Supports forked window execution for real-time stdout visibility. | `script`: Python source code to execute<br>`execute_forked_window`: Run in new console (boolean)<br>`target_agents`: Agents triggered on success |
| **sqler** | Execute database operations on MS SQL Server instances using `pyodbc`. Injects `cursor` and `conn` globals directly into an inner Python scope. Triggers downstream agents on success. | `sql_connection` map: `driver`, `server`, `database`, `username`, `password` credentials<br>`script`: Python script wrapping SQL execution<br>`target_agents`: Success agents |
| **deleter** | Delete files by pattern | `files_to_delete`: List of patterns (supports wildcards)<br>`trigger_mode`: immediate / event<br>`recursive`: false (scan subdirs)<br>`filetype_exclusions`: "" (exclude extensions/filenames)<br>`source_agents`: For event mode |
| **mover** | Move or copy files | `operation`: move / copy<br>`sources_list`: File patterns<br>`destination_folder`: Target directory<br>`recursive`: false (scan subdirs)<br>`filetype_exclusions`: "" (exclude extensions/filenames) |
| **shoter** | Takes screenshots and saves to output directory | `output_dir`: Screenshot destination<br>`target_agents`: Downstream agents |
| **mouser** | Moves the mouse pointer randomly for a duration or to a specific screen position. In localized mode it can also issue a configured click only after the destination has been effectively reached. Starts downstream agents after completion | `movement_type`: "random"/"localized"<br>`actual_position`: true<br>`ini_posx`/`ini_posy`: Start coords<br>`end_posx`/`end_posy`: End coords<br>`button_click`: none/left/right/middle/double-left/double-right/double-middle<br>`total_time`: Duration (seconds)<br>`target_agents`: Downstream agents |
| **keyboarder** | Issues keyboard sequences through PyAutoGUI to emulate human typing, literal text entry, and hotkey chords, then triggers downstream agents after the sequence completes. The ACP auto-populates its `source_agents` / `target_agents` lists through the dedicated keyboarder connection endpoint. | `input_sequence`: Comma-separated sequence of keys, hotkeys, or quoted literal strings<br>`stride_delay`: Delay in milliseconds between sequence steps<br>`source_agents`: Upstream wiring / trigger sources<br>`target_agents`: Downstream agents |
| **ssher** | SSH remote command execution. Requires pre-configured SSH keys. | `user`: SSH username<br>`ip`: Remote host<br>`script`: Command to execute<br>`target_agents`: Triggered on success |
| **scper** | SCP file transfer to/from remote host | `user`: SSH username<br>`ip`: Remote host<br>`file`: Path to transfer<br>`direction`: send / receive<br>`target_agents`: Triggered on success |
| **mongoxer** | Execute Python scripts against MongoDB using pre-connected `db` object | `mongo_connection`: Connection config map<br>`script`: Python script using `db`<br>`target_agents`: Success agents |
| **prompter** | Sends configured prompt to Ollama LLM and logs response | `prompt`: Prompt text<br>`llm.host`: Ollama URL<br>`llm.model`: Model name<br>`target_agents`: Downstream agents |
| **gitter** | Execute Git operations on a local repository (clone, pull, push, commit, checkout, branch, diff, log, status, or custom commands). Produces structured content reports: `<git {command}> RESPONSE { ... }` with stdout/stderr capture | `repo_path`: Local repo path<br>`command`: Git command to run<br>`branch`: Branch name<br>`commit_message`: Commit message<br>`remote`: Remote URL<br>`custom_command`: Raw git command<br>`target_agents`: Downstream agents |
| **dockerer** | Docker container management (build, up, down, restart, stop, logs, ps, pull) | `command`: Docker operation<br>`compose_file`: docker-compose path<br>`target_agents`: Downstream agents |
| **kuberneter** | Kubernetes command executor (kubectl commands like get, apply, logs, exec) | `command`: kubectl operation<br>`namespace`: target namespace<br>`extra_args`: Additional arguments<br>`custom_command`: Custom kubectl command<br>`target_agents`: Downstream agents |
| **apirer** | HTTP/REST API agent — makes GET/POST/PUT/DELETE requests, logs response status and latency, triggers downstream agents regardless of outcome. Produces structured content reports: `<{url}> RESPONSE { ... }` with timing in milliseconds and Authorization header masking for security | `url`: Target URL<br>`method`: HTTP method<br>`headers`: Request headers map<br>`body`: Request body<br>`expected_status`: Expected HTTP status<br>`timeout`: Timeout in seconds<br>`target_agents`: Downstream agents |
| **pser** | LLM-powered process finder — searches running processes by likely name using semantic matching | `likely_process_name`: Process to find<br>`llm.host`: Ollama URL<br>`llm.model`: Model name<br>`target_agents`: Downstream agents |
| **jenkinser** | CI/CD pipeline trigger — triggers Jenkins builds with CSRF crumb support, logs trigger result, and starts downstream agents regardless of outcome | `jenkins_url`: Jenkins server URL<br>`job_name`: Job to trigger<br>`user`: Jenkins username<br>`api_token`: API token<br>`parameters`: Build parameters map<br>`target_agents`: Downstream agents |
| **crawler** | Developer-oriented web crawler with LLM analysis — fetches URLs via HTTP GET and captures **raw content** by default (complete HTML markup, inline/external JavaScript, CSS, meta tags, HTTP response headers, JSON-LD structured data) or plain text. Generates resource inventories cataloging all scripts, styles, forms, images, endpoints, and data-* attributes. Processes content with an LLM using a developer-centric preamble for deep technical analysis. Supports three crawl modes: small-range (single URL), medium-range (same-domain links), large-range (all links) | `url`: Target URL<br>`system_prompt`: LLM prompt<br>`crawl_type`: small-range / medium-range / large-range<br>`content_mode`: raw (default) / text<br>`llm.host`: Ollama URL<br>`llm.model`: Model name<br>`target_agents`: Downstream agents |
| **summarizer** | Log monitoring with LLM event detection — continuously polls source agent log files and sends content to an LLM with a configurable system prompt. When the LLM detects a positive event ([EVENT_TRIGGERED]), starts all configured downstream target agents | `source_agents`: Agents to monitor<br>`system_prompt`: LLM analysis prompt<br>`llm.host`: Ollama URL<br>`llm.model`: Model name<br>`poll_interval`: Seconds between polls<br>`target_agents`: Downstream agents |
| **file_interpreter** | Reads and interprets documents (DOCX, PPTX, XLSX, PDF, TXT, TeX, CSV, HTML, RTF, etc.), extracting text and optionally images. Supports three reading modes: `fast` (text only), `complete` (text + image extraction to images/ subdirectory), and `summarized` (text + LLM summarization). Outputs structured INI/END_FILE blocks. Supports wildcards for batch processing | `path_filenames`: File path or wildcard pattern<br>`reading_type`: fast / complete / summarized<br>`recursive`: false (scan subdirs)<br>`filetype_exclusions`: "" (exclude extensions/filenames)<br>`llm.host`: Ollama URL (for summarized mode)<br>`llm.model`: Model name (for summarized mode)<br>`target_agents`: Downstream agents |
| **image_interpreter** | Analyzes and describes images using an LLM vision model. Converts images to base64 for LLM transmission. Supports 12+ image formats (jpg, png, gif, bmp, tiff, webp, svg, ico, heic, avif). Can accept wildcards, directories, File-Interpreter pool names, or single files. Outputs structured INI_IMAGE_FILE/END_FILE blocks | `images_pathfilenames`: Wildcards, directory, File-Interpreter pool name, or file<br>`recursive`: false (scan subdirs)<br>`filetype_exclusions`: "" (exclude extensions/filenames)<br>`llm.host`: Ollama URL<br>`llm.model`: Vision model name<br>`system_prompt`: Custom analysis prompt (default: "Describe this image in detail.")<br>`target_agents`: Downstream agents |
| **j_decompiler** | Java artifact decompiler that scans wildcard-enabled directories for `.class`, `.jar`, `.war`, and `.ear` files, uses the bundled `jd-cli` asset to generate Java sources beside classes or into sibling archive directories, and then starts downstream agents | `directory`: Base path or wildcard list for Java artifacts<br>`recursive`: false (scan subdirs when enabled)<br>`source_agents`: Informative upstream connections<br>`target_agents`: Downstream agents |

### Logic Gates

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **and** | AND logic gate (latched) | `source_1`, `source_2`: Source agents<br>`pattern_1`, `pattern_2`: Patterns to detect<br>`target_agents`: Trigger if BOTH found |
| **or** | OR logic gate | `source_1`, `source_2`: Source agents<br>`target_agents`: Trigger if ANY found |

### Routing Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **asker** | Interactive A/B path chooser. Writes `ASKER_CHOICE_NEEDED` to its log, which the frontend detects and shows a dialog. The user picks Path A or Path B, and the corresponding agents are triggered. 5-minute timeout. Optional `legend_path_a`/`legend_path_b` captions describe each choice in the dialog. | `target_agents_a`: Agents for Path A<br>`target_agents_b`: Agents for Path B<br>`legend_path_a`: Caption for Path A button<br>`legend_path_b`: Caption for Path B button<br>`source_agents`: Upstream agents |
| **forker** | Automatic A/B path router. Continuously monitors source agent logs for two sets of patterns and automatically routes to Path A or Path B when detected. Supports reanimation offsets. | `pattern_a`: Patterns for Path A (comma-separated)<br>`pattern_b`: Patterns for Path B (comma-separated)<br>`target_agents_a`: Path A agents<br>`target_agents_b`: Path B agents<br>`source_agents`: Agents to monitor<br>`poll_interval`: Check frequency |
| **counter** | Persistent counter with threshold-based routing. Increments a counter on each execution, compares against a threshold, and routes to Path L (less than) or Path G (greater than or equal). Supports reanimation for persistent state across flow restarts. | `initial_value`: 0<br>`threshold_value`: 10<br>`target_agents_l`: Path L agents<br>`target_agents_g`: Path G agents |

### Utility Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **raiser** | Event-driven launcher. Primary bridge between monitoring agents and action agents. | `source_agents`: Agents whose logs to monitor<br>`pattern`: Text to detect<br>`target_agents`: Agents to start on detection<br>`poll_interval`: Check frequency |
| **sleeper** | Delay execution | `duration_ms`: Wait time in milliseconds<br>`target_agents`: Trigger after delay |
| **croner** | Time-scheduled trigger | `trigger_time`: HH:MM format<br>`target_agents`: Agents to trigger<br>`poll_interval`: Check frequency |
| **cleaner** | Post-termination cleanup. Deletes .log and .pid files for specified agents, then launches agents in `output_agents`. Accepts input from Ender or FlowBacker. | `agents_to_clean`: Agent pool names to clean (auto-populated by Ender/dialog)<br>`cleaned_agents`: Pre-configured agent pool names to always clean on execution<br>`output_agents`: Agents to start after cleanup |
| **flowbacker** | Short-running passive utility batch backing agent. Copies the entire deployed session directory to a configured backup root, overwriting any previous backup for the same session, then launches connected Cleaner agents. Accepts input only from Starter, Ender, Forker, or Asker; outputs only to Cleaner. | `target_directory`: Backup root directory<br>`source_agents`: Upstream trigger agents<br>`target_agents`: Cleaner agents to launch after backup |
| **flowcreator** | LLM-powered AI flow designer. Reads `agentic_skill.md` and generates complete flow configurations from natural language descriptions. | `llm.base_url`: Ollama URL<br>`llm.model`: Model for flow design |
| **gatewayer** | Inbound gateway agent. Receives external events via HTTP webhook or folder-drop, normalizes into canonical envelopes, persists to disk, queues, and dispatches to downstream agents. HTTP ingress performs authentication/validation and optional dedup; folder-drop performs best-effort parsing plus persistence/dispatch. Long-running active ingress agent. | `http.port`: 8787<br>`auth.mode`: bearer<br>`storage.output_dir`: Event artifact path<br>`target_agents`: Downstream agents |
| **gateway_relayer** | Long-running deterministic ingress relay that bridges provider-native webhooks (e.g. GitHub) into Gatewayer's canonical timestamp+body HMAC format. Validates upstream signatures, transforms payloads, HMAC-signs the forwarded body, and relays to a configured Gatewayer endpoint. Does NOT use any LLM. | `listen_port`: 9090<br>`provider_mode`: github<br>`forward_url`: Gatewayer endpoint<br>`forward_hmac_secret`: Gatewayer HMAC secret<br>`target_agents`: Downstream agents |
| **node_manager** | Long-running infrastructure agent that maintains a live registry of local/remote nodes, probes health (ping, TCP, SSH, WinRM, HTTP), classifies node state (ONLINE/OFFLINE/DEGRADED/UNKNOWN), detects capability changes, persists state, exports filtered manifests, and triggers downstream agents on configured node events. | `heartbeat.poll_interval`: 30<br>`inventory.inline_nodes`: Static nodes<br>`triggers.trigger_events`: Event types<br>`target_agents`: Downstream agents |
| **file_creator** | Short-running infrastructure agent that creates a file with specified content, then triggers downstream agents regardless of file creation result. | `file_path`: Target file path<br>`content`: Raw file content<br>`target_agents`: Downstream agents |
| **file_extractor** | Short-running infrastructure agent that reads/loads files (supports wildcards), extracts text content using the same file type support as file_interpreter, falls back to strings extraction for unknown types, then triggers downstream agents regardless of extraction result. | `path_filenames`: File path or wildcard pattern<br>`recursive`: false (scan subdirs)<br>`filetype_exclusions`: "" (exclude extensions/filenames)<br>`target_agents`: Downstream agents |
| **kyber_keygen** | Short-running infrastructure deterministic agent that generates CRYSTALS-Kyber public/private key pairs in base64 format. Supports Kyber-512, Kyber-768, and Kyber-1024 variants. | `kyber_variant`: kyber-768<br>`source_agents`: Upstream agents<br>`target_agents`: Downstream agents |
| **kyber_cipher** | Short-running infrastructure deterministic agent that encrypts a buffer using a CRYSTALS-Kyber public key via encapsulation + AES-256-CTR. Logs encapsulation, IV, and cipher text in base64. | `kyber_variant`: kyber-768<br>`public_key`: Base64 public key<br>`buffer`: Plaintext to encrypt<br>`target_agents`: Downstream agents |
| **kyber_decipher** | Short-running infrastructure deterministic agent that decrypts cipher text using a CRYSTALS-Kyber private key via decapsulation + AES-256-CTR. Logs deciphered buffer in original format. | `kyber_variant`: kyber-768<br>`private_key`: Base64 private key<br>`encapsulation`: Base64 encapsulation<br>`initialization_vector`: Base64 IV<br>`cipher_text`: Base64 cipher text<br>`target_agents`: Downstream agents |
| **parametrizer** | Short-running active utility interconnection agent that maps structured outputs from a source agent's log to a target agent's config.yaml via an interconnection scheme saved for the deployed pool instance. When multiple output elements exist, it iterates sequentially: fill config, start target, wait, repeat. Current structured-output sources are Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Gatewayer, and Gateway-Relayer. | `source_agent`: Source agent name<br>`target_agent`: Target agent name<br>`source_agents`: [] (max 1)<br>`target_agents`: [] (max 1) |
| **barrier** | Short-running passive utility flow-control agent that acts as a synchronization barrier. Waits for ALL configured source agents to start before triggering downstream target agents. Each source agent starts a separate barrier process (input sub-process) that creates a flag file; the first arrival becomes the output sub-process that polls until all flags are present, then fires. Uses cross-process file-based locking to avoid race conditions. | `source_agents`: Upstream agents whose startup is awaited<br>`target_agents`: Downstream agents to start when all sources have checked in |
| **googler** | Short-running web-search agent that searches Google for a configured query using Playwright browser automation, fetches the top N result pages, extracts readable text content, and saves the combined results to an output file for downstream processing. | `query`: Search query<br>`number_of_results`: 5 (max 10)<br>`content_mode`: text or raw<br>`output_file`: googler_results.txt<br>`source_agents`: Upstream agents<br>`target_agents`: Downstream agents |

Each agent has a `config.yaml` file for customization.

---

## Gatewayer: The Inbound Gateway Agent

Gatewayer is Tlamatini's **ingress controller** — a long-running, deterministic agent that turns your workflow canvas into a system that reacts to the outside world. While most Tlamatini agents are triggered internally (a Starter fires, a Croner ticks, a Monitor detects), Gatewayer opens a controlled door to external callers: CI/CD webhooks, third-party SaaS event notifications, IoT telemetry pushes, file drops, or any HTTP client that can send a request.

It does **one thing and does it well**: receive, normalize, persist, and queue inbound events — then hand them off to whatever downstream agents you wire on the canvas. On the HTTP ingress path it also authenticates, validates, and can deduplicate requests before they are queued. Gatewayer never executes privileged actions itself. It is purely an ingress and orchestration boundary.

### How It Works

When Gatewayer starts (via Starter or Croner), it remains alive indefinitely. In the current implementation, HTTP and folder-watch can both run at the same time if both are enabled in `config.yaml`; `listen_mode` is informational only.

**1. HTTP Webhook (enabled by default)**
A lightweight `HTTPServer` binds to a configurable host/port (default `127.0.0.1:8787`). The configured path (default `/gatewayer`) is currently logged for operator clarity, but not enforced by the handler. The current handler accepts `POST`, `PUT`, and `PATCH`, executes the ingress pipeline synchronously, and returns a JSON acknowledgment with the generated `event_id` on accepted requests. Optional TLS support is available for production-facing deployments.

**2. Folder-Drop Watcher (optional, disabled by default)**
A polling loop watches a directory for files matching a glob pattern (default `*.json`). Each new file is read, parsed as JSON when possible, wrapped into a similar canonical envelope, persisted, enqueued, and then archived or deleted. In the current code, folder-drop does **not** call the HTTP authentication or `validate_request()` helpers, and it does not apply the HTTP dedup or overflow checks. This channel is useful for air-gapped integrations, batch file ingestion, or systems that write to shared network drives.

The current implementation uses two related pipelines:

```
HTTP Request
    │
    v
Authenticate -> Validate -> Normalize -> Dedup -> Persist -> Enqueue -> 202/401/500
    │
    v
Dispatch Loop (serial drain, wait for target_agents to stop, then start them)

Folder-Drop File
    │
    v
Read/Parse best-effort -> Normalize -> Persist -> Enqueue -> Archive/Delete
    │
    v
Dispatch Loop (same shared queue and serial dispatch thread)
```

**Crash recovery**: The pending queue and dedup window are continuously persisted to `reanim_queue.json` and `reanim_dedup.json`. If the agent crashes or the host reboots, accepted-but-not-yet-dispatched events are automatically restored on restart. Ender clears any `reanim*` files for target agents it resolves, which includes Gatewayer's queue/dedup files when Gatewayer is part of the flow shutdown kill list.

**Stable log markers**: Every event transition emits a configurable log word (`GATEWAY_EVENT_ACCEPTED`, `GATEWAY_EVENT_REJECTED`, `GATEWAY_EVENT_QUEUED`, `GATEWAY_EVENT_DISPATCHED`, `GATEWAY_ERROR`), making Gatewayer fully observable by Tlamatini's own Monitor Log and Summarizer agents — so you can build meta-workflows that monitor your gateway's health.

**Current implementation notes**:
- `listen_mode` is currently informational; startup is controlled by `http.enabled` and `folder_watch.enabled`
- `http.path`, `http.methods`, and `http.request_timeout_sec` are declared in config but not enforced/used by the current handler
- The response path always emits JSON via `_send_json()`; `response.mode` and `response.body_template` are currently unused
- `queue.enabled`, `queue.dispatch_mode`, `runtime.worker_threads`, `storage.write_response_json`, `payload.attachments_enabled`, and `payload.max_attachment_bytes` are currently declared but unused in `gatewayer.py`
- Dedup, max-pending overflow checks, and payload validation currently apply to HTTP ingress only

### Authentication Modes

| Mode | Description |
|------|-------------|
| `none` | Open endpoint, no authentication (development/testing only) |
| `bearer` | Validates `Authorization: Bearer <token>` header against a configured secret |
| `hmac` | Validates a raw hex SHA-256 HMAC signature over `timestamp + body`, with configurable signature and timestamp header names plus clock-skew tolerance. Suitable for custom senders or relays that can generate Gatewayer's expected signature format |

All modes support an optional IP allowlist (`allowed_ips`) as an additional layer.

**Important**: Current HMAC mode is **not** directly compatible with providers like GitHub that sign only the body (for example `X-Hub-Signature-256`) and expose event type in headers. To accept those webhooks unchanged, add a small translating relay or patch `gatewayer.py`.

### Gatewayer vs. OpenClaw's Gateway

OpenClaw (the open-source personal AI assistant with 180K+ GitHub stars) uses a **Gateway** as its central control plane. On the surface, both are "gateways" that receive external events and route them to downstream processing. Under the hood, the two designs solve fundamentally different problems — and Tlamatini's Gatewayer carries several architectural advantages for **automation workflows**.

| Dimension | OpenClaw Gateway | Tlamatini Gatewayer |
|-----------|-----------------|---------------------|
| **Core purpose** | AI chat routing — shuttles messages between 30+ messaging platforms and an LLM agent runtime | Workflow ingress — receives arbitrary structured events and dispatches deterministic automation pipelines |
| **Protocol** | WebSocket (persistent bidirectional connection) | HTTP request/response (stateless, fire-and-forget). Accepted and duplicate requests get an immediate JSON ack with the `event_id`; rejected requests return 401/500 |
| **Ingress channels** | Messaging platform adapters (WhatsApp, Slack, Telegram, etc.) — tightly coupled to chat semantics | Generic HTTP webhook + folder-drop watcher. Any system that can send an HTTP request or write a file can trigger a workflow. Current HTTP handler accepts `POST`/`PUT`/`PATCH`; folder-drop is polling-based |
| **Event model** | Chat messages with platform-specific schemas (reactions, threads, attachments, presence) | Canonical event envelope with `event_id`, `event_type`, `session_id`, `correlation_id`, `body_hash`, raw body, headers, query params. Content-agnostic — JSON, plaintext, or form-encoded payloads are all first-class |
| **Authentication** | Platform-level OAuth/bot tokens managed per adapter | Built-in bearer token, Gatewayer-specific timestamp+body HMAC verification, and IP allowlists — configurable in YAML. Direct compatibility with third-party webhook HMAC schemes may require a relay or code patch |
| **Persistence** | Session state stored in memory/database; messages are consumed | Every event is written to disk as a structured artifact directory (`event.json`, `headers.json`, `request_body.txt`) with configurable retention. Full audit trail by default |
| **Crash recovery** | Relies on the messaging platform to redeliver (platform-dependent) | `reanim_queue.json` and `reanim_dedup.json` files persist pending events and dedup state locally. On restart, accepted-but-undispatched events resume automatically |
| **Deduplication** | No built-in dedup — relies on message IDs from each platform | Configurable sliding-window dedup for HTTP ingress, keyed on any combination of event fields (`event_type`, `session_id`, `body_hash`). Folder-drop does not currently apply dedup |
| **Downstream dispatch** | Routes to a single LLM agent runtime; responses flow back through the same WebSocket | Triggers any number of `target_agents` on the Tlamatini canvas via the standard concurrency guard. Downstream can be anything: Executer, Pythonxer, SSHer, Emailer, another Gatewayer — the full agent catalog |
| **Concurrency model** | Serializes messages per session, parallel across sessions. Heavy LLM calls are the bottleneck | Serial dispatch per event with explicit concurrency guard (`wait_for_agents_to_stop`). Gatewayer waits for all target agents to stop before launching them for the next event |
| **Multi-tenant security** | Single-user trust boundary by design. Shared gateways are explicitly discouraged for mixed-trust users (cited by Microsoft, DigitalOcean, Nebius security analyses) | Session-scoped pool isolation. Each Tlamatini session gets its own pool directory, PID files, logs, and reanim state. Multiple Gatewayer instances can coexist in the same flow or across sessions without interference |
| **Dependencies** | Node.js 22+, npm ecosystem, platform-specific adapter packages, LLM API keys | Python runtime plus `PyYAML`; optionally uses `psutil` when available for process checks and otherwise falls back to OS-level probing. Core networking/storage logic uses the standard library (`http.server`, `threading`, `queue`, `hashlib`, `ssl`) |

**In short**: OpenClaw's Gateway is a **chat router** — it excels at connecting messaging platforms to an LLM loop. Tlamatini's Gatewayer is a **workflow trigger** — it excels at turning arbitrary external signals into deterministic, auditable, crash-recoverable automation pipelines. If your goal is to build a chatbot that responds on Slack, use OpenClaw. If your goal is to receive a custom webhook, a CI callback, or a translated third-party webhook and trigger a build-test-deploy-notify pipeline that you can see, inspect, and replay on a visual canvas — Gatewayer is purpose-built for that.

### Usage Examples

#### Example A: Timestamped HMAC Webhook Triggers a Build-and-Notify Pipeline

A CI system, relay, or custom sender sends a timestamped HMAC-signed `push` event to Gatewayer. On each accepted event, the workflow executes a build script, runs tests, and sends the result via email.

```
                         HTTP POST (timestamped HMAC webhook)
                                  │
                                  v
┌─────────┐     ┌──────────────┐     ┌─────────────┐     ┌───────────┐     ┌───────────┐
│ Starter │────>│ Gatewayer_1  │────>│ Executer_1  │────>│Pythonxer_1│────>│ Emailer_1 │
└─────────┘     │ :8787        │     │ build.sh    │     │ test.py   │     │ results   │
                │ /gatewayer   │     └─────────────┘     └───────────┘     └───────────┘
                └──────────────┘                                                 │
                 (long-running)                                                  v
                                                                           ┌───────────┐
                                                                           │  Ender_1  │
                                                                           └───────────┘
```

**Gatewayer_1 config.yaml** (key fields):
```yaml
target_agents: ["executer_1"]

http:
  enabled: true
  host: "0.0.0.0"
  port: 8787
  path: "/gatewayer"

auth:
  mode: "hmac"
  hmac_secret: "shared-secret-between-sender-and-gatewayer"
  signature_header: "X-Tlamatini-Signature"
  timestamp_header: "X-Tlamatini-Timestamp"
  max_clock_skew_sec: 600

payload:
  accepted_content_types: ["application/json"]
  required_fields: ["event_type", "ref", "repository"]
  event_type_field: "event_type"
  save_raw_body: true

queue:
  dedup_enabled: true
  dedup_key_fields: ["body_hash"]
  dedup_window_sec: 10
```

**What happens when the sender posts a push event**:
1. The sender POSTs to `http://your-host:8787/gatewayer` with a JSON body plus `X-Tlamatini-Timestamp` and `X-Tlamatini-Signature`
2. Gatewayer verifies the raw hex SHA-256 HMAC over `timestamp + body` using the shared secret
3. Validates that `event_type`, `ref`, and `repository` fields exist in the payload
4. Generates a unique `event_id`, builds the canonical envelope, checks dedup, persists to `gateway_events/<event_id>/`
5. Returns `HTTP 202 {"status":"accepted","event_id":"a3f8..."}` — the sender sees success immediately
6. The dispatch loop waits for Executer_1 to be free, then starts it
7. Executer_1 runs `build.sh`, triggers Pythonxer_1 for tests, and the downstream notification stage can be wired to send the result based on the upstream agents' logs/output
8. If Gatewayer crashes mid-queue, pending events survive in `reanim_queue.json` and resume on restart

If your original sender is GitHub, GitLab, Stripe, Shopify, or another provider with a different signing convention, put a tiny relay in front of Gatewayer or patch the HMAC logic so the provider's native webhook format is translated into the expected timestamp+body scheme.

#### Example B: IoT Sensor Alerts via Folder-Drop with Conditional Routing

An industrial monitoring system writes JSON sensor readings to a shared network folder. Gatewayer watches the folder and feeds events into a Forker that routes critical alerts to Telegram and normal readings to a database logger.

```
  [Sensor drops alert.json]
            │
            v
┌─────────┐     ┌──────────────┐     ┌───────────┐
│ Croner  │────>│ Gatewayer_1  │────>│ Forker_1  │
│ (boot)  │     │ folder_watch │     └─────┬─────┘
└─────────┘     └──────────────┘           │
                 (long-running)       ┌────┴────┐
                                      v         v
                              ┌────────────┐  ┌──────────┐
                              │Telegramer_1│  │ Sqler_1  │
                              │"ALERT: ..."│  │INSERT log│
                              └────────────┘  └──────────┘
                                      │           │
                                      v           v
                                ┌───────────────────┐
                                │      Ender_1      │
                                └───────────────────┘
```

**Gatewayer_1 config.yaml** (key fields):
```yaml
target_agents: ["forker_1"]
listen_mode: "folder_watch"  # informational; actual startup is driven by http.enabled/folder_watch.enabled

http:
  enabled: false

folder_watch:
  enabled: true
  watch_path: "/mnt/sensors/incoming"
  file_pattern: "*.json"
  poll_interval: 5
  archive_processed: true
  processed_dir: "archived"

payload:
  event_type_field: "severity"

storage:
  output_dir: "/var/tlamatini/sensor_events"
  keep_days: 30
```

**What happens when a sensor drops a file**:
1. The external monitoring system writes `alert_20260322_143055.json` to `/mnt/sensors/incoming/`
2. Gatewayer's folder watcher detects the new file within 5 seconds
3. Reads the file, attempts to parse it as JSON, and if successful extracts `severity` into the envelope's `event_type`
4. Builds the canonical envelope, persists artifacts, and enqueues the event
5. Archives the original file to `/mnt/sensors/incoming/archived/`
6. The dispatch loop starts Forker_1, which reads the latest event and routes: `severity: "critical"` goes to Telegramer_1 (instant Telegram alert), while `severity: "normal"` goes to Sqler_1 (INSERT into time-series database)
7. All events — normal and critical — are persisted for 30 days in `/var/tlamatini/sensor_events/`, creating a complete audit trail

Current folder-drop note: `payload.required_fields`, HTTP dedup, and queue overflow limits are not applied by the folder watcher in the current code path.

### When to Use Gatewayer

- **Webhook receivers**: Internal services, CI/CD tools, SaaS callbacks, or any system that can send an HTTP request. Third-party providers with non-matching HMAC schemes may need a tiny relay or auth patch
- **CI/CD triggers**: Jenkins, GitHub Actions, or ArgoCD calling back to Tlamatini on pipeline completion
- **IoT / edge ingestion**: Sensors, PLCs, or edge gateways writing JSON files to a shared folder
- **Cross-system orchestration**: System A finishes a job and POSTs a signal to Tlamatini, which triggers a multi-step pipeline in System B
- **Manual triggers**: A curl command or a simple HTML form that sends an HTTP request to Gatewayer, useful for one-off administrative tasks wired to complex workflows
- **Event replay and auditing**: Because every event is persisted with its full envelope, you can inspect, replay, or debug any past event by reading its artifact directory

---

## Parametrizer: The Interconnection Engine

Parametrizer is the **strict sequential hand-off agent** of Tlamatini. It reads structured output segments from exactly one source agent's log file, injects mapped values into exactly one target agent's `config.yaml`, runs that target, waits for it to finish, restores the target configuration, advances its source cursor, and only then moves to the next source segment.

The key point is that **the source log itself becomes a queue**. Parametrizer does not batch all source results and it does not run the target in parallel. If the source agent emits segments `A`, `B`, `C`, and `D` very quickly, Parametrizer still processes them one by one in order:

1. fully process `A`
2. restore the target config
3. commit the source cursor
4. then begin `B`

This is the mechanism that lets one agent safely feed another without race conditions or manual editing between stages.

### Why Parametrizer Exists

Tlamatini agents communicate through **log files** and **`config.yaml` files**. This is deliberate: agents are independent processes with no shared memory and no hidden in-process coupling. The consequence is that a workflow still needs a disciplined way to move data from one agent's structured output into the next agent's input parameters.

Examples:

- an Apirer response body must become the `buffer` of a Kyber-Cipher
- a Kyber-KeyGen `public_key` must become the `public_key` of a Kyber-Cipher
- each extracted file from File-Extractor must be fed one-at-a-time into a Summarizer or Prompter

Before Parametrizer, that required manual `config.yaml` editing or custom scripting. Parametrizer turns it into a **visual mapping plus deterministic runtime queue**.

### How It Works

Parametrizer operates as a persistent single-threaded loop. The runtime is intentionally simple:

```
source log unread bytes -> next complete structured segment -> target config backup
-> apply mappings -> start target -> wait target finish -> archive target log
-> restore original config -> commit source cursor -> repeat
```

At startup Parametrizer does the following:

1. Validates that exactly one source agent and exactly one target agent are configured.
2. Validates that the source agent belongs to the supported structured-output set.
3. Loads `interconnection-scheme.csv`.
4. Initializes or restores its persisted progress state from `reanim_<source_agent>.pos`.
5. Restores any stale `config.yaml.bck` backup if needed.
6. Enters a polling loop over the unread bytes of the source log.

Inside that loop it always works on **the next complete segment only**:

1. Reads the source log starting from the last committed byte offset.
2. Uses the source-specific `NEXT_OUTPUT_PARSERS` parser to extract only the next complete structured segment.
3. If no complete segment exists yet and the source is still running, waits and polls again.
4. If a complete segment exists, queues it and processes it immediately.

That segment-processing cycle is always:

1. Wait until the target agent is stopped.
2. Back up the target `config.yaml` as `config.yaml.bck`.
3. Save in-flight state to `reanim_<source_agent>.pos`.
4. Apply the field mappings to the target config.
5. Start the target agent.
6. Wait until the target agent finishes.
7. Copy the target agent's current log into a preserved segment archive such as `prompter_1_segment_1.log` or `crawler_2_segment_3.log`.
8. Restore the original target config from `config.yaml.bck`.
9. Advance the committed source cursor to the byte immediately after the processed segment.
10. Clear the in-flight state and continue with the next segment.

This order is what guarantees deterministic behavior. Parametrizer never advances the cursor before the target has finished and the target configuration has been restored.

The segment-log archive is important because many target agents reuse a single live log file name such as `prompter_1.log`. Without archiving, the result of segment 1 would be overwritten by segment 2, then by segment 3. Parametrizer now preserves each completed target outcome in its own file, named with the sequential segment number that was committed.

### The Interconnection Scheme

The mapping between source output fields and target config parameters is stored in `interconnection-scheme.csv`. The file supports both whole-field assignment and marker-level substitution.

```csv
source_field,target_param,target_marker
response_body,buffer,
url,target.metadata.url,
response_body,prompt_template,content
```

Each row means:

- `source_field`: the key extracted from the source segment
- `target_param`: the target config key to write; dot notation is allowed
- `target_marker`: optional placeholder name inside an existing target string value

There are two mapping modes:

- **Whole-value assignment**: if `target_marker` is empty, Parametrizer writes the entire source value into `target_param`
- **Marker replacement**: if `target_marker` is present, Parametrizer replaces `{target_marker}` inside the existing target string

That means Parametrizer can either overwrite a config field completely or inject data into a template string already present in the target config.

This CSV is created from the visual mapping dialog and saved in the deployed Parametrizer pool directory. It is loaded once when the agent starts or resumes.

### Unified Section Format

Every section-generating agent writes its structured output to its log file using **one single, universal format**. This is the only format that Parametrizer knows how to parse. Any agent that needs to produce data consumable by Parametrizer must emit sections in exactly this shape:

```
INI_SECTION_<AGENT_TYPE><<<
field1: value1
field2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

**Rules (mandatory, no exceptions):**

1. **`<AGENT_TYPE>`** is the UPPERCASE base name of the agent: `APIRER`, `CRAWLER`, `KYBER_KEYGEN`, `FILE_INTERPRETER`, `GOOGLER`, etc.
2. **Start marker**: `INI_SECTION_<AGENT_TYPE><<<` on its own line, immediately followed by a newline.
3. **End marker**: `>>>END_SECTION_<AGENT_TYPE>` on its own line.
4. **KV header**: Lines before the **first blank line** are key-value metadata. Each line is split on the first `: ` (colon followed by a space). Keys must be single-line and must not contain `: `.
5. **Body**: Everything **after** the first blank line is stored under the key `response_body`. The body can be arbitrarily large and multi-line.
6. **No blank line → no body**: If the content between markers contains no blank line, the entire content is parsed as KV fields and no `response_body` is produced. This is the correct format for agents whose output is purely metadata (e.g., Kyber-KeyGen emitting `public_key` and `private_key`).
7. **Single atomic call**: The section **must** be emitted as a **single** `logging.info()` call. Never split the section across multiple `logging.info()` calls — concurrent log writes from other threads could interleave and corrupt the block.
8. **One section per output unit**: If the agent produces N results, emit N separate sections. Parametrizer processes them sequentially, one at a time.

**Example — agent with KV metadata and body (Googler):**

```
INI_SECTION_GOOGLER<<<
url: https://example.com
status: 200
content_length: 4523

This is the extracted page text content.
It can span multiple lines.
>>>END_SECTION_GOOGLER
```

Parametrizer extracts: `{'url': 'https://example.com', 'status': '200', 'content_length': '4523', 'response_body': 'This is the extracted page text content.\nIt can span multiple lines.'}`

**Example — agent with KV fields only (Kyber-KeyGen):**

```
INI_SECTION_KYBER_KEYGEN<<<
public_key: MIIBIjANBgkq...
private_key: MIIEvgIBADAN...
>>>END_SECTION_KYBER_KEYGEN
```

Parametrizer extracts: `{'public_key': 'MIIBIjANBgkq...', 'private_key': 'MIIEvgIBADAN...'}`

**The generic parser** in `parametrizer.py` handles all 16 agent types with a single regex and a single content-splitting function. No per-agent parser code exists. Adding a new section-generating agent requires only:

1. Adding the agent's base name to the `SECTION_AGENT_TYPES` list in `parametrizer.py`
2. Adding the agent's field list to `PARAMETRIZER_SOURCE_OUTPUT_FIELDS` in `views.py`
3. Emitting sections in the agent's Python code using the format above

### Supported Source Agents and Their Output Fields

Parametrizer supports 16 structured-output source agent types. All use the unified `INI_SECTION / END_SECTION` format described above.

| Source Agent | KV Header Fields | Has Body (`response_body`)? |
|---|---|---|
| **Apirer** | `url` | Yes |
| **Gitter** | `git_command` | Yes |
| **Kuberneter** | `parameters`, `status` | Yes |
| **Crawler** | `label`, `model`, `url`, `crawl_type`, `content_mode` | Yes |
| **Summarizer** | `model`, `source` | Yes |
| **File-Interpreter** | `file_path`, `mode` | Yes |
| **Image-Interpreter** | `file_path` | Yes |
| **File-Extractor** | `file_path` | Yes |
| **Prompter** | `model` | Yes |
| **FlowCreator** | `model` | Yes |
| **Kyber-KeyGen** | `public_key`, `private_key` | No |
| **Kyber-Cipher** | `encapsulation`, `initialization_vector`, `cipher_text` | No |
| **Kyber-DeCipher** | `deciphered_buffer` | No |
| **Gatewayer** | `event_id`, `event_type`, `session_id`, `correlation_id`, `content_type`, `method`, `path`, `body` | No |
| **Gateway-Relayer** | `event_type`, `delivery_id`, `action`, `ref`, `repository`, `sender`, `body` | No |
| **Googler** | `url`, `status`, `content_length` | Yes |

### Iterative Execution Model

A critical capability of Parametrizer is its handling of **multiple structured output segments** in a single source log. This happens when, for example:

- An Apirer calls multiple API endpoints in sequence
- A Crawler scrapes several pages
- A File-Extractor processes a wildcard pattern matching many files

When the source produces `N` segments, Parametrizer does **not** batch them and does **not** launch `N` target processes in parallel. It treats the source log as an ordered queue:

```
For each complete source segment:
   1. Wait target stopped
   2. Back up target config.yaml
   3. Fill mappings for that segment
   4. Start target
   5. Wait target finish
   6. Archive target log as <target_agent>_segment_<n>.log
   7. Restore original target config.yaml
   8. Commit source byte cursor
   9. Move to the next segment
```

Example:

- the source log already contains segments `A`, `B`, `C`, and `D`
- Parametrizer detects `A`
- while Parametrizer is running the target for `A`, the source may continue writing more data
- Parametrizer still does **not** touch `B` until `A` has finished, the target config has been restored, and the byte cursor has been advanced past `A`

This is the behavior that prevents race conditions on the target `config.yaml` and ensures each source segment gets its own isolated target execution.

### Pause, Resume, and Reanimation

Parametrizer is fully pause/resume aware. Its restart-safe behavior is built around two persisted artifacts:

- `config.yaml.bck`: the original target configuration captured before the current segment is applied
- `reanim_<source_agent>.pos`: a state file containing the committed source offset, file size, processed count, current stage, and any in-flight segment boundary

In addition, every completed target execution now produces a preserved segment log in the target agent directory:

- `<target_agent>_segment_1.log`
- `<target_agent>_segment_2.log`
- `<target_agent>_segment_3.log`
- and so on

These files are snapshots of the target agent's live log immediately after each segment finishes. They are not reanimation state; they are execution artifacts kept so each segment outcome remains inspectable even after the target agent runs again.

Parametrizer tracks these runtime stages:

- `idle`
- `backup_ready`
- `config_applied`
- `waiting_target`
- `target_finished_restore_pending`

On resume (`AGENT_REANIMATED=1`), Parametrizer inspects the saved stage and repairs the state before continuing:

- If it was interrupted **before the target finished**, it restores `config.yaml.bck`, keeps the last committed source offset, clears the in-flight state, and retries that same segment.
- If it was interrupted **after the target finished but before the cursor commit**, it archives that finished target log into the correct `*_segment_N.log` file, restores `config.yaml.bck`, advances the source cursor to the saved segment end, increments the processed count, and continues with the next unread segment without replaying the already finished target run.
- If it starts fresh and finds a stale backup, it restores the target to a clean baseline before doing any new work.

This is why pause/resume does not duplicate already completed target runs, does not leave the target config permanently modified by an interrupted segment, and does not lose the finished target log of a segment that completed right before the pause.

### The Visual Mapping Dialog

On the canvas, double-clicking or right-clicking a Parametrizer agent opens its custom mapping dialog (not the standard config editor). The dialog:

1. **Validates connections first** — if the source or target is missing, or the source type is unsupported, an error overlay appears before the dialog opens.
2. **Shows two columns** — left column lists the source agent's available output fields (cyan theme), right column lists the target agent's config.yaml parameters (orange theme).
3. **Click-to-wire** — click a source field, then click a target parameter to create a mapping. A curved SVG Bezier line (gradient from cyan to orange) visually confirms the connection.
4. **Click-to-remove** — click any existing line to remove that mapping.
5. **Save** — writes the interconnection scheme CSV for the deployed Parametrizer instance to the backend.

The dialog dynamically adapts to whatever source and target agents are connected — the field lists are always current with the actual agent types.

For nested target configurations, the dialog now flattens the target `config.yaml` dictionary into dot-notation keys before rendering the right-hand column. That means mappings such as `response_body -> target.email.body` are represented explicitly in the dialog and then written back into the nested YAML structure at runtime.

### Completion Semantics

Parametrizer stops only when **both** of these are true:

1. the source agent is no longer running
2. the source log has no more complete unread segments after the last committed byte offset

At that point it writes a completion message to its own log and stops itself.

There are two important edge cases:

- If the source stops and no complete segment was ever available, Parametrizer stops without starting the target.
- If the source stops with trailing log content that does not form a complete structured segment, Parametrizer logs a warning and stops at the last committed segment boundary.

For every committed segment, the corresponding target log archive remains in the target directory. That means after a five-segment run you should expect files such as:

- `prompter_1_segment_1.log`
- `prompter_1_segment_2.log`
- `prompter_1_segment_3.log`
- `prompter_1_segment_4.log`
- `prompter_1_segment_5.log`

### Practical Examples

**Example 1: API Response → Encryption Pipeline**

```
Apirer ──▶ Parametrizer ──▶ Kyber-Cipher
```
Apirer calls an external API. Parametrizer maps `response_body` → `buffer` and `url` → (any tracking field). Kyber-Cipher encrypts each response. If Apirer hit 3 endpoints, the pipeline runs 3 encryption cycles automatically.

**Example 2: Key Generation → Cipher Configuration**

```
Kyber-KeyGen ──▶ Parametrizer ──▶ Kyber-Cipher
```
Kyber-KeyGen produces a public/private key pair. Parametrizer maps `public_key` → `public_key` in Kyber-Cipher's config. This wires key generation directly into encryption without manual config editing.

**Example 3: File Extraction → Summarization**

```
File-Extractor ──▶ Parametrizer ──▶ Summarizer
```
File-Extractor reads multiple files matching a wildcard. Parametrizer maps `response_body` → the Summarizer's input field. Each extracted file gets summarized individually — if 10 files matched the pattern, 10 summarization runs occur.

**Example 4: Full Encrypt-Decrypt Round Trip**

```
Kyber-KeyGen ──▶ Parametrizer₁ ──▶ Kyber-Cipher ──▶ Parametrizer₂ ──▶ Kyber-DeCipher
```
Two Parametrizer instances chain the entire cryptographic lifecycle: the first maps generated keys into the cipher, the second maps cipher output (encapsulation, IV, cipher text) into the decipher agent's config.

### Design Constraints

- **One-to-one only.** One Parametrizer instance supports exactly one source and one target. Use multiple Parametrizers for fan-out or fan-in designs.
- **Source must be structured-output capable.** Only the supported 16 source agents can feed Parametrizer. All must emit the unified `INI_SECTION / END_SECTION` format.
- **Target can be any normal agent with a `config.yaml`.** Parametrizer writes only to fields that exist or can be created through dot-notation traversal.
- **Mappings are static while the process is running.** The CSV is loaded on startup/resume, not continuously re-read during each segment.
- **Strictly sequential.** Parametrizer is intentionally single-threaded and processes only one in-flight segment at a time.
- **Target config is temporary per segment.** The live target config is modified only for the current segment and is then restored from `config.yaml.bck`.
- **Target logs are preserved per segment.** After each finished target run, Parametrizer copies the live target log to `<target_agent>_segment_<n>.log` so earlier segment outcomes are not lost when the target runs again.
- **The source log is authoritative.** Progress is tracked by byte offset in the source log, not by counting assumptions or external queues.

---

## Multi-Turn Chat Mode: The Agentic Execution Engine

Multi-Turn mode transforms Tlamatini from a chat-based Q&A assistant into a fully autonomous agentic execution engine. When the user enables the **Multi-Turn** checkbox in the chat interface, the LLM gains access to 50+ local tools and can chain them across up to 100 iterations to complete complex, multi-step tasks.

### What Multi-Turn Mode Enables

In **standard chat** mode, the LLM answers questions using only the provided context (RAG documents, file search results, system metrics). In **Multi-Turn** mode, the LLM becomes an autonomous operator that can:

- **Crawl websites** and extract content (JavaScript-rendered SPAs supported)
- **Execute shell commands** and Python scripts
- **Query databases** (SQL, MongoDB)
- **Call HTTP APIs** (GET, POST, PUT, DELETE, PATCH)
- **SSH into remote servers** and run commands
- **Transfer files** via SCP
- **Send messages** (Email, Telegram, WhatsApp, desktop notifications)
- **Manage containers** (Docker, Kubernetes)
- **Run git operations** (clone, pull, push, commit, etc.)
- **Analyze images** with vision AI
- **Encrypt/decrypt data** with post-quantum cryptography (Kyber)
- **Search the web** via Google (with DuckDuckGo fallback)
- **Create, read, and transform files**
- **Monitor logs and network connections** in real time
- **Chain all of the above** into multi-step workflows within a single conversation turn

The key behavioral differences when Multi-Turn is enabled:

| Behavior | Standard Chat | Multi-Turn |
|----------|:---:|:---:|
| Prompt shape validation (must be a question) | Enforced | Bypassed |
| File-listing short-circuit (returns listing without LLM) | Active | Bypassed — request always reaches the LLM |
| Tool binding | All tools (legacy mode) | Capability-aware selective binding |
| Tool execution loop | Single LLM call | Up to 100 iterations with tool calls |
| Console window suppression | Normal | Suppressed (agents run silently) |

### Architecture: The Complete Pipeline

When a user sends a message with Multi-Turn enabled, the request traverses the following pipeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. FRONTEND                                                         │
│    User types message + enables Multi-Turn checkbox                 │
│    → WebSocket sends {message, multi_turn_enabled: true}            │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 2. WEBSOCKET CONSUMER (consumers.py)                                │
│    Receives JSON, extracts multi_turn_enabled flag                  │
│    → Saves message to DB                                            │
│    → Broadcasts user message to chat UI                             │
│    → Queues async LLM retrieval task                                │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 3. RAG INTERFACE (rag/interface.py)                                 │
│    ask_rag() receives the payload                                   │
│    → Bypasses prompt-shape validation (Multi-Turn allows ANY input) │
│    → Bypasses path-access validation                                │
│    → Passes multi_turn_enabled to the RAG chain                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 4. UNIFIED RAG CHAIN (rag/chains/unified.py)                        │
│    Retrieves relevant documents from the knowledge base             │
│    → Builds enhanced input with context (RAG docs + file context)   │
│    → Bypasses file-listing short-circuit in Multi-Turn              │
│    → Invokes the Unified Agent with enhanced_input + tools          │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 5. CAPABILITY-AWARE EXECUTOR (mcp_agent.py)                         │
│    Receives enhanced_input + multi_turn_enabled flag                │
│    → If execution plan exists: use ONLY planned tools               │
│    → Otherwise: select_tools_for_request() (smart scoring)          │
│    → Creates a MultiTurnToolAgentExecutor with selected tools       │
└────────────────────────────────┬────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ 6. MULTI-TURN TOOL LOOP (mcp_agent.py)                              │
│    Builds messages: [SystemMessage, HumanMessage]                   │
│    → LOOP (up to 100 iterations):                                   │
│       1. Call LLM with bound tools                                  │
│       2. If LLM returns tool_calls:                                 │
│          - Execute each tool                                        │
│          - Append ToolMessage with result to message history        │
│          - Continue loop (next iteration)                           │
│       3. If LLM returns text (no tool_calls):                      │
│          - Return final answer → stream to user                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Tool Categories

Tools available in Multi-Turn mode fall into five categories:

**Basic System Tools** — Direct operations on the local machine:
`get_current_time`, `execute_file`, `execute_command`, `execute_netstat`, `launch_view_image`, `unzip_file`, `decompile_java`

**Template Agent Management** — Configure and control template agents from the chat:
`agent_parametrizer`, `agent_starter`, `agent_stopper`, `agent_stat_getter`

**Wrapped Chat-Agent Tools** (~35 agents) — Each launches an isolated subprocess agent:
`chat_agent_crawler`, `chat_agent_executer`, `chat_agent_ssher`, `chat_agent_sqler`, `chat_agent_pythonxer`, `chat_agent_dockerer`, `chat_agent_kuberneter`, `chat_agent_apirer`, `chat_agent_gitter`, `chat_agent_file_creator`, `chat_agent_file_extractor`, `chat_agent_image_interpreter`, `chat_agent_summarize_text`, `chat_agent_prompter`, `chat_agent_send_email`, `chat_agent_telegramer`, `chat_agent_whatsapper`, `chat_agent_notifier`, `chat_agent_shoter`, `chat_agent_pser`, `chat_agent_scper`, `chat_agent_jenkinser`, `chat_agent_mongoxer`, `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph`, `chat_agent_monitor_log`, `chat_agent_monitor_netstat`, `chat_agent_recmailer`, `chat_agent_move_file`, `chat_agent_deleter`, `chat_agent_file_interpreter`

**Runtime Management Tools** — Monitor and control running agent instances:
`chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`, `chat_agent_run_stop`

**Web Search** — Search the internet using Playwright browser automation:
`googler`

### The Multi-Turn Tool Loop

The core execution engine is the `MultiTurnToolAgentExecutor`. It implements an explicit tool-calling loop (not using LangChain's opaque AgentExecutor) that gives the backend direct control over every tool-call/observation turn:

1. **System prompt** is constructed from `prompt.pmt` + a tool selection guide + grounding rules.
2. **User message** (enhanced with RAG context) is added as a `HumanMessage`.
3. The LLM is called with `bind_tools(selected_tools)` so it can request tool invocations.
4. If the LLM response contains `tool_calls`, each tool is executed and the result is appended as a `ToolMessage`.
5. The loop continues — the LLM sees all prior tool results and can request more tools.
6. When the LLM responds with pure text (no tool calls), that text is the final answer.
7. The loop runs for up to `unified_agent_max_iterations` (default: 100) iterations.

This architecture allows the LLM to orchestrate multi-step workflows: crawl a website, extract data, query a database, compose a report, and send it via email — all within a single conversation turn.

### Capability-Aware Tool Selection

When 50+ tools are available, binding all of them to the LLM wastes context and confuses smaller models. The `CapabilityAwareToolAgentExecutor` solves this with intelligent tool selection:

1. **Global Execution Plan** (highest priority): If a planner has pre-selected tools for this request, use only those.
2. **Smart Scoring** (`select_tools_for_request`): Each tool is scored against the user's input text using name matching, alias phrases, description tokens, and security hints. Every tool scoring above the entry threshold is selected (up to 50 tools per request).
3. **Run-Control Isolation**: Run-control tools (`chat_agent_run_list/status/log/stop`) are excluded from score-floor calculations and auto-injected whenever wrapped agents are selected. This prevents monitoring tools from inflating the threshold and crowding out the actual agent tools the user requested.
4. **Fallback**: If no tools score above threshold, all tools are bound (safe default).

This means a request like "use File Creator to create a file, then File Extractor to read it, then Summarize Text to summarize it" correctly binds all three wrapped agent tools plus runtime monitoring — even though the user referred to them by natural name rather than their internal tool identifiers.

### Wrapped Chat-Agent Lifecycle

When the LLM invokes a `chat_agent_*` tool, the following happens:

1. **Template Copy**: The agent's template directory is copied to a **unique, sequenced** runtime directory under `pools/_chat_runs_/{agent}_{seq:03d}_{short_id}/` (e.g. `executer_001_a1b2c3d4`). The template is never mutated. Previous runs are never overwritten — every attempt (including failures) is preserved.
2. **Config Parametrization**: The LLM's `key='value'` assignments are parsed and applied to the runtime copy's `config.yaml`.
3. **Subprocess Launch**: The agent starts as an independent subprocess with its own PID. The tool waits briefly (default 8 seconds) for initial output.
4. **JSON Response**: The tool returns a JSON object with `run_id`, `status`, `pid`, `runtime_dir`, `log_path`, and `log_excerpt`.
5. **Monitoring**: If `status="running"`, the LLM can call `chat_agent_run_status` or `chat_agent_run_log` in subsequent iterations to check progress.
6. **Completion**: When the agent finishes, its status transitions to `completed` or `failed`, and the full log is available via `chat_agent_run_log`.

This design ensures that each tool invocation is isolated, traceable, and monitorable. The global sequence number shows the exact execution order across all agent types, so the user can reconstruct the full timeline of what the LLM attempted — including retries and failures.

---

## Flow Creation from Multi-Turn Answers

### Overview: Turning Conversations into Workflows

One of Tlamatini's most powerful capabilities is the ability to **automatically convert a successful Multi-Turn chat session into a reusable `.flw` workflow file**. When the LLM uses tools during a Multi-Turn conversation — crawling websites, executing commands, creating files, querying APIs, etc. — the system records every tool invocation along with its arguments and success status. Once the LLM delivers its final answer, the system determines whether the overall task succeeded and, if so, presents a **"Create Flow"** button directly in the chat message header.

Clicking this button generates a complete `.flw` workflow file that mirrors the exact sequence of agent operations the LLM performed. The user can then load this file in the **Agentic Workflow Designer (ACP)** and run the same pipeline as a repeatable, automated workflow — without involving the LLM again.

This creates a unique feedback loop:

```
                        ┌───────────────────────────────┐
                        │   User asks the LLM to do     │
                        │   a multi-step task            │
                        └───────────────┬───────────────┘
                                        ↓
                        ┌───────────────────────────────┐
                        │   LLM autonomously uses tools  │
                        │   (crawl, execute, create...)  │
                        └───────────────┬───────────────┘
                                        ↓
                        ┌───────────────────────────────┐
                        │   System records tool calls    │
                        │   + classifies answer success  │
                        └───────────────┬───────────────┘
                                        ↓
                        ┌───────────────────────────────┐
                        │   "Create Flow" button appears │
                        │   in the chat response         │
                        └───────────────┬───────────────┘
                                        ↓
                        ┌───────────────────────────────┐
                        │   User downloads .flw file     │
                        │   → Loads it in ACP Designer   │
                        │   → Runs it as a workflow      │
                        └───────────────────────────────┘
```

### End-to-End Data Flow

The "Create Flow" feature spans the full stack — from the Multi-Turn tool loop in Python to the browser-side flow generator in JavaScript. This section traces the complete path of data.

#### Phase 1: Tool Call Recording (Backend)

**File:** `agent/mcp_agent.py` — Class `MultiTurnToolAgentExecutor`

Every time the LLM invokes a tool during the Multi-Turn execution loop, the executor appends a structured log entry to its internal `_tool_calls_log` list. This happens for **every** tool invocation — successful, failed, or unavailable:

```python
# Recorded after each tool invocation in mcp_agent.py
self._tool_calls_log.append({
    "tool_name": tool_name,              # Internal tool identifier
    "args": dict(tool_input),            # Arguments passed to the tool
    "success": call_success,             # Boolean: True if tool succeeded
    "agent_display_name": _tool_name_to_agent_display(tool_name),
                                         # ACP display name or None
})
```

When the Multi-Turn loop finishes (the LLM emits a text response with no further tool calls), the executor returns the complete log:

```python
return {"output": str(answer), "tool_calls_log": list(self._tool_calls_log)}
```

The log then propagates upward through the chain hierarchy:

```
MultiTurnToolAgentExecutor.invoke()
    → UnifiedAgentChain.invoke()           (unified.py)
        → result_dict["tool_calls_log"]
        → result_dict["multi_turn_used"] = True
            → ask_rag()                    (interface.py)
                → global_state['last_tool_calls_log']
                → global_state['last_multi_turn_used']
                    → AgentConsumer         (consumers.py)
                        → picks up from global_state
                        → passes to process_llm_response()
```

#### Phase 2: Answer Success Classification (Backend)

**File:** `agent/services/answer_analizer.py`

Before broadcasting the response to the browser, the system determines whether the LLM's answer indicates the task was completed successfully. This classification is **not** performed with regex or keyword matching — instead, it uses the same `chained-model` LLM configured in `config.json` as a sub-prompt classifier.

This step runs only when **both** conditions are met:
- `multi_turn_used` is `True` (the request went through the Multi-Turn pipeline)
- `tool_calls_log` is non-empty (the LLM actually used tools)

```python
# In response_parser.py — after cleaning the LLM response
answer_success = None
if multi_turn_used and tool_calls_log:
    answer_success = await analyze_answer_success(llm_response)
```

The `analyze_answer_success()` function:
1. Creates a lightweight `OllamaLLM` instance using `chained-model` and `ollama_base_url` from config
2. Sends the LLM response text (truncated to 4,000 characters) as context to a classification prompt
3. The classifier LLM responds with exactly one word: `SUCCESS` or `FAILURE`
4. Returns `True` for SUCCESS, `False` for FAILURE

#### Phase 3: WebSocket Broadcast (Backend to Frontend)

**Files:** `agent/services/response_parser.py` → `agent/consumers.py`

The response parser builds the WebSocket broadcast message with all metadata:

```python
broadcast_msg = {
    'type': 'agent_message',
    'message': llm_response,             # The cleaned LLM answer text
    'username': 'Tlamatini',             # Bot username
    'tool_calls_log': tool_calls_log,    # Full list of tool call records
    'multi_turn_used': True,             # Flag indicating Multi-Turn was active
    'answer_success': answer_success,    # Boolean from LLM classifier
}
```

The `AgentConsumer.agent_message()` handler forwards all fields to the browser:

```python
ws_payload = {'message': message, 'username': username}
if event.get('tool_calls_log'):
    ws_payload['tool_calls_log'] = event['tool_calls_log']
if event.get('multi_turn_used'):
    ws_payload['multi_turn_used'] = True
if 'answer_success' in event:
    ws_payload['answer_success'] = event['answer_success']
await self.send(text_data=json.dumps(ws_payload))
```

#### Phase 4: Button Rendering and Gate Conditions (Frontend)

**File:** `agent/static/agent/js/agent_page_chat.js`

The WebSocket `onmessage` handler passes all received fields to `appendChatMessage()`:

```javascript
appendChatMessage(data.username, data.message, filesAnchorElement, null,
    data.tool_calls_log || null, data.multi_turn_used || false,
    data.answer_success != null ? data.answer_success : null);
```

Inside `appendChatMessage()`, the **"Create Flow"** button renders only when **all four conditions** are satisfied:

| # | Condition | Purpose |
|---|-----------|---------|
| 1 | `username === 'Tlamatini'` | Only bot messages (not user messages) |
| 2 | `multiTurnUsed === true` | Only Multi-Turn sessions (not standard chat) |
| 3 | `_hasSuccessfulToolCalls(toolCallsLog)` | At least one tool call succeeded and maps to an ACP agent |
| 4 | `answerSuccess === true` | The LLM classifier determined the answer indicates success |

```javascript
if (username === 'Tlamatini' && multiTurnUsed
    && _hasSuccessfulToolCalls(toolCallsLog)
    && answerSuccess === true) {
    // Render the "Create Flow" button in the message header
}
```

The `_hasSuccessfulToolCalls()` helper validates that the tool calls log contains at least one entry where both `success` is `true` and `agent_display_name` is non-null (meaning the tool maps to an ACP agent type, not a management-only tool):

```javascript
function _hasSuccessfulToolCalls(toolCallsLog) {
    if (!Array.isArray(toolCallsLog) || toolCallsLog.length === 0) return false;
    return toolCallsLog.some(entry => entry.success && entry.agent_display_name);
}
```

#### Phase 5: Flow Generation and Download (Frontend)

**File:** `agent/static/agent/js/agent_page_chat.js` — Function `_generateAndDownloadFlow()`

When the user clicks "Create Flow", the following algorithm builds a `.flw` file:

**Step 1 — Collect unique successful agents:**
- Iterates through `toolCallsLog`, filters to `success === true && agent_display_name != null`
- Deduplicates by display name, preserving execution order
- Keeps the **last** config seen for each agent type (latest invocation wins)

**Step 2 — Build nodes (Starter + Agents + Ender):**
- **Starter** node at position `x=50px`, `y=80px` — its `target_agents` points to the first agent
- **Agent nodes** laid out horizontally with 220px spacing — each carries `configData` mapped from the tool call arguments
- **Ender** node at the end — its `target_agents` lists all agent pool names (for termination)

**Step 3 — Build connections (linear chain):**
```
Starter → Agent₁ → Agent₂ → … → AgentN → Ender
```
Each connection links `sourceIndex → targetIndex` with `inputSlot: 0, outputSlot: 0`.

**Step 4 — Prompt and download:**
- Prompts the user for a filename (default: `multi-turn-flow`)
- Appends `.flw` extension if missing
- Triggers a browser file download with the JSON content

**Example — Generated `.flw` structure for a 3-tool session:**
```json
{
  "nodes": [
    {
      "text": "Starter",
      "left": "50px",
      "top": "80px",
      "agentPurpose": "Entry point, launches first agents",
      "configData": { "target_agents": ["crawler"] }
    },
    {
      "text": "Crawler",
      "left": "270px",
      "top": "80px",
      "agentPurpose": "Web crawling with LLM analysis",
      "configData": {
        "url": "https://example.com",
        "system_prompt": "Extract all links",
        "target_agents": ["file_creator"],
        "source_agents": ["starter"]
      }
    },
    {
      "text": "File Creator",
      "left": "490px",
      "top": "80px",
      "agentPurpose": "Creates files with specified content",
      "configData": {
        "filepath": "output.txt",
        "content": "...",
        "target_agents": ["ender"],
        "source_agents": ["crawler"]
      }
    },
    {
      "text": "Ender",
      "left": "710px",
      "top": "80px",
      "agentPurpose": "Terminates all agents, launches Cleaners",
      "configData": {
        "target_agents": ["crawler", "file_creator"],
        "source_agents": ["file_creator"]
      }
    }
  ],
  "connections": [
    { "sourceIndex": 0, "targetIndex": 1, "inputSlot": 0, "outputSlot": 0 },
    { "sourceIndex": 1, "targetIndex": 2, "inputSlot": 0, "outputSlot": 0 },
    { "sourceIndex": 2, "targetIndex": 3, "inputSlot": 0, "outputSlot": 0 }
  ]
}
```

### The Answer Analizer: LLM-Based Success Classification

#### Why Not Regex or Keyword Matching

Early implementations used a `_messageIndicatesSuccess()` function that scanned the LLM response text for hardcoded keywords like "successfully", "completed", "done", "finished", etc. This approach was **fundamentally unreliable** for several reasons:

| Problem | Example |
|---------|---------|
| Synonyms and paraphrases | "Here is the full analysis" (success, but no keyword match) |
| Partial word collisions | "Complete Image Summary" — "Complete" ≠ "completed" |
| Language variation | "The file has been generated and saved" (no exact keyword match) |
| False negatives | Image interpretations, data analysis, and informational responses rarely use "success" vocabulary |
| False positives | "I'm done looking, but I couldn't find anything" — contains "done" but is a failure |
| Multilingual answers | Non-English responses would never match English keywords |

Using an LLM to classify the answer solves all of these problems at once: the classifier understands semantic meaning, not string patterns.

#### Classification Prompt Design

The Answer Analizer uses a strict binary classification prompt with the same `chained-model` configured in `config.json`. The prompt is intentionally narrow — one job, one word output:

**System message:**
```
You are a strict binary classifier. Your ONLY job is to decide
whether an AI assistant's answer indicates that the requested task
was completed successfully or that it failed / could not be done.
```

**Human message template:**
```
Classify the following AI assistant answer as SUCCESS or FAILURE:

--- BEGIN ANSWER ---
{answer}
--- END ANSWER ---
```

The classifier receives up to 4,000 characters of the LLM response as context. This cap keeps token usage bounded for very long responses while providing enough text for accurate classification.

#### Classification Rules

The classifier follows these explicit rules:

| Verdict | Criteria |
|---------|----------|
| **SUCCESS** | Task was accomplished, results were delivered, information was provided, or the objective was met in any form |
| **SUCCESS** | Partial results that still provide useful output |
| **FAILURE** | Task failed, encountered unrecoverable errors, was refused, or the assistant could not fulfill the request |
| **FAILURE** | A polite refusal or an apology for not being able to help |

The classifier responds with exactly one word: `SUCCESS` or `FAILURE`. No explanation, no punctuation, no extra text.

#### Error Handling and Defaults

The Answer Analizer is designed to **never block or break the response pipeline**:

| Scenario | Behavior |
|----------|----------|
| LLM returns `SUCCESS` | `answer_success = True` → button shown |
| LLM returns `FAILURE` | `answer_success = False` → button hidden |
| LLM returns unexpected text | Parsed as not-SUCCESS → `answer_success = False` |
| Ollama is unreachable | Exception caught → defaults to `True` (show button) |
| Empty response text | Returns `False` (no answer to classify) |
| Multi-Turn not used | Classifier is **not called at all** → `answer_success = None` |
| No tool calls | Classifier is **not called at all** → `answer_success = None` |

The fail-open default (`True` on error) is a deliberate UX decision: it is better to show a "Create Flow" button unnecessarily than to hide it when the user expects it.

### Tool-Call Log Structure

#### Log Entry Schema

Each entry in the `tool_calls_log` array follows this schema:

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `string` | Internal tool identifier (e.g., `"chat_agent_crawler"`, `"execute_command"`) |
| `args` | `object` | Arguments passed to the tool (may contain `__arg1` request string for wrapped agents) |
| `success` | `boolean` | `true` if the tool executed without errors; `false` if it failed or was unavailable |
| `agent_display_name` | `string\|null` | ACP agent display name (e.g., `"Crawler"`, `"Executer"`) or `null` for management tools |

Only entries where **both** `success === true` and `agent_display_name !== null` are included in the generated flow.

#### Tool Name to Agent Display Name Mapping

Non-wrapped tools are mapped via a static dictionary in `mcp_agent.py`:

| Tool Name | Display Name |
|-----------|-------------|
| `execute_command` | Executer |
| `execute_file` | Pythonxer |
| `execute_netstat` | Monitor Netstat |
| `googler` | Googler |
| `agent_parametrizer` | Parametrizer |
| `agent_starter` | Starter |
| `agent_stopper` | Stopper |
| `launch_view_image` | Image Interpreter |
| `unzip_file` | Executer |
| `decompile_java` | J-Decompiler |

Wrapped chat-agent tools (prefixed `chat_agent_*`) are resolved dynamically from the `WRAPPED_CHAT_AGENT_BY_TOOL_NAME` registry, using their `display_name` attribute.

#### Management Tools (Excluded from Flows)

The following tools are classified as management/monitoring-only and **never produce flow nodes** (their `agent_display_name` is always `null`):

- `agent_stat_getter` — Agent status viewer
- `get_current_time` — Clock utility
- `chat_agent_run_list` — List running agent instances
- `chat_agent_run_status` — Check agent run status
- `chat_agent_run_log` — Read agent run log
- `chat_agent_run_stop` — Stop a running agent

### Flow File (.flw) Generation

#### Node Layout Strategy

The flow generator uses a **horizontal linear layout** with fixed spacing:

| Property | Value |
|----------|-------|
| Starting X offset | `50px` |
| Horizontal gap between nodes | `220px` |
| Vertical position (all nodes) | `80px` |

Nodes are laid out left-to-right in execution order:

```
 50px     270px     490px     710px     930px
  │         │         │         │         │
  ▼         ▼         ▼         ▼         ▼
┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐
│Start│→ │ A₁  │→ │ A₂  │→ │ A₃  │→ │Ender│
└─────┘  └─────┘  └─────┘  └─────┘  └─────┘
```

#### Connection Wiring

Connections form a **strict linear chain**. Each agent node includes:
- `target_agents`: the pool name of the next agent (or `"ender"`)
- `source_agents`: the pool name of the previous agent (or `"starter"`)

The Ender node's `target_agents` lists **all** agent pool names (the agents it needs to terminate). Pool names are derived from display names by lowercasing and replacing spaces/hyphens with underscores (e.g., `"File Creator"` → `"file_creator"`).

#### Agent Config Mapping

The function `_mapToolArgsToAgentConfig()` translates raw tool-call arguments into `config.yaml`-compatible structures for each known agent type. It parses the `__arg1` request string (which contains `key='value'` pairs) and maps them to agent-specific config keys:

| Agent Type | Mapped Config Keys |
|------------|-------------------|
| **Pythonxer** | `script`, `execute_forked_window` |
| **Image Interpreter** | `images_pathfilenames`, `llm.prompt`, `recursive` |
| **Prompter** | `prompt` |
| **Crawler** | `url`, `system_prompt`, `content_mode` |
| **Executer** | `command`, `working_directory` |
| **Gitter** | `repo_path`, `operation`, `args` |
| **Apirer** | `url`, `method`, `headers`, `body` |
| **SSHer** | `host`, `command`, `username` |
| **File Creator** | `filepath`, `content` |
| **File Extractor** | `path` |
| **File Interpreter** | `path`, `system_prompt`, `reading_type` |
| **SQLer** | `connection_string`, `query` |
| **Summarizer** | `input_text`, `system_prompt` |
| **Dockerer** | `command` |
| **Kuberneter** | `command` |
| **Googler** | `query` |
| **Notifier** | `title`, `message` |
| **Emailer** | `smtp.host`, `smtp.username`, `to`, `subject`, `body` |
| *(other)* | All parsed key-value pairs copied as-is (fallback) |

### Complete Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MULTI-TURN TOOL LOOP (mcp_agent.py)                                    │
│                                                                         │
│  LLM calls tools → _invoke_tool() records each call:                   │
│    { tool_name, args, success, agent_display_name }                     │
│                                                                         │
│  Loop ends → returns:                                                   │
│    { "output": final_answer, "tool_calls_log": [...] }                 │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  UNIFIED RAG CHAIN (unified.py)                                         │
│                                                                         │
│  Attaches metadata to result:                                           │
│    result_dict["tool_calls_log"] = tool_calls_log                       │
│    result_dict["multi_turn_used"] = True                                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  RAG INTERFACE (interface.py)                                            │
│                                                                         │
│  Stores in thread-safe global state:                                    │
│    global_state['last_tool_calls_log'] = response["tool_calls_log"]    │
│    global_state['last_multi_turn_used'] = True                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  WEBSOCKET CONSUMER (consumers.py)                                       │
│                                                                         │
│  Retrieves and clears from global state:                                │
│    tool_calls_log = global_state.get('last_tool_calls_log')            │
│    multi_turn_used = global_state.get('last_multi_turn_used')          │
│                                                                         │
│  Passes to process_llm_response()                                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  RESPONSE PARSER (response_parser.py)                                    │
│                                                                         │
│  1. Cleans and processes the LLM response text                          │
│  2. If multi_turn_used AND tool_calls_log:                              │
│     → Calls analyze_answer_success(llm_response)                        │
│     → Returns answer_success: True/False                                │
│  3. Builds broadcast message with all metadata                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  ANSWER ANALIZER (answer_analizer.py)                                    │
│                                                                         │
│  1. Creates lightweight OllamaLLM (chained-model, temperature=0)       │
│  2. Sends classification prompt with answer text (max 4000 chars)       │
│  3. LLM responds: "SUCCESS" or "FAILURE"                                │
│  4. Returns True/False (defaults to True on error)                      │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  WEBSOCKET BROADCAST (consumers.py → browser)                            │
│                                                                         │
│  JSON payload:                                                           │
│  {                                                                       │
│    "message": "...",                                                     │
│    "username": "Tlamatini",                                              │
│    "tool_calls_log": [ {tool_name, args, success, agent_display_name} ],│
│    "multi_turn_used": true,                                              │
│    "answer_success": true/false                                          │
│  }                                                                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (agent_page_chat.js)                                           │
│                                                                         │
│  Gate check (ALL must be true):                                          │
│    ✓ username === 'Tlamatini'                                           │
│    ✓ multiTurnUsed === true                                              │
│    ✓ _hasSuccessfulToolCalls(toolCallsLog)                              │
│    ✓ answerSuccess === true                                              │
│                                                                         │
│  → Renders "Create Flow" button in message header                       │
│  → On click: _generateAndDownloadFlow(toolCallsLog)                     │
│    → Builds nodes: Starter → Agent₁ → Agent₂ → … → Ender              │
│    → Maps tool args to agent config.yaml format                         │
│    → Prompts for filename → downloads .flw file                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Files Involved

| File | Role | Key Functions / Classes |
|------|------|------------------------|
| `agent/mcp_agent.py` | Tool call recording and name mapping | `MultiTurnToolAgentExecutor._invoke_tool()`, `_tool_name_to_agent_display()`, `_TOOL_TO_AGENT_DISPLAY_NAME`, `_MANAGEMENT_TOOLS` |
| `agent/rag/chains/unified.py` | Attaches `tool_calls_log` and `multi_turn_used` to chain result | `UnifiedAgentChain.invoke()` |
| `agent/rag/interface.py` | Stores metadata in thread-safe global state for consumer pickup | `ask_rag()` |
| `agent/consumers.py` | Retrieves metadata from global state, forwards through WebSocket | `AgentConsumer.queue_llm_retrieval()`, `AgentConsumer.agent_message()` |
| `agent/services/response_parser.py` | Triggers answer classification, builds broadcast message | `process_llm_response()` |
| `agent/services/answer_analizer.py` | LLM-based success/failure classifier | `analyze_answer_success()`, `_classify_sync()`, `_build_llm()` |
| `agent/static/agent/js/agent_page_chat.js` | Button rendering, flow generation, and download | `appendChatMessage()`, `_hasSuccessfulToolCalls()`, `_generateAndDownloadFlow()`, `_mapToolArgsToAgentConfig()`, `_toPoolName()`, `_agentPurpose()` |
| `agent/static/agent/css/agent_page.css` | Button styling (`.create-flow`, `.create-flow:hover`, `.create-flow:active`) | CSS rules at lines 152–177 |
| `agent/config.json` | Provides `chained-model` and `ollama_base_url` for the classifier LLM | Configuration keys |

---

## Custom Agent Development

Tlamatini includes a detailed workflow document (Skill) to guide AI assistants in creating new agents correctly. This ensures that new agents integrate perfectly with the backend Django views, database migrations, frontend CSS gradients, and Canvas connection logic.

### Using the `create_new_agent` Skill

The core instruction set is located at:
`Tlamatini/.agents/workflows/create_new_agent.md`

You can seamlessly instruct AI coding assistants (like Antigravity IDE, claude-cli, or gemini-cli) to build a new agent by explicitly referencing this skill in your prompt.

#### In Antigravity IDE / Gemini CLI
Simply use the `@` context referencing or direct path injection in your prompt:
> "Load the Skill @[c:\\Development\\Tlamatini\\Tlamatini\\.agents\\workflows\\create_new_agent.md] and create a new agent named `MyAgent` that connects to an external API. Make its gradient color purple to pink."

#### In Claude CLI (claude-code) / Cursor
Reference the file directly so the LLM reads the constraints before generating code:
> "Please read `Tlamatini/.agents/workflows/create_new_agent.md` first. Then, create an agent named `MyAgent` that takes a screenshot."

The AI will automatically follow the 4-step checklist (Backend Script, Django Integration, Frontend CSS, Frontend JS) handling all connections and migrations seamlessly.

## Custom MCP Development

Tlamatini also includes a dedicated MCP/tool-extension workflow document for AI assistants. Use this skill when the work is not "create a new workflow agent under `agent/agents/`", but instead "extend the MCP/tool/chain stack" by touching files such as `agent/tools.py`, `agent/mcp_agent.py`, `agent/rag/factory.py`, `chain_system_lcel.py`, `chain_files_search_lcel.py`, MCP startup code, database toggle rows, or the MCP frontend dialogs.

This is important because Tlamatini separates four concerns that are easy to confuse:

- persisted `Mcp` toggle rows in the database
- runtime MCP-style services such as `System-Metrics` and `Files-Search`
- sidecar context-fetch chains that inject `system_context` and `files_context`
- unified-agent LangChain tools returned by `get_mcp_tools()`

### Using the `create_new_mcp` Skill

The core instruction set is located at:
`Tlamatini/.mcps/create_new_mcp.md`

Use this skill whenever you need an AI assistant to add or modify any of the following:

- a new MCP-backed context provider
- a new runtime service plus its chain wrapper
- a new unified-agent tool in `agent/tools.py`
- factory wiring in `agent/rag/factory.py`
- MCP persistence, startup, or frontend toggle handling

In other words:

- use `create_new_agent.md` for new workflow nodes on the canvas
- use `create_new_mcp.md` for MCP/tool/chain extensions behind the chat and context system

### Antigravity IDE / Gemini CLI Example

Load the skill file directly in the prompt and describe the MCP capability you want:

> "Load the Skill @[c:\\Development\\Tlamatini\\Tlamatini\\.mcps\\create_new_mcp.md] and add a new MCP-backed capability named `Service-Health` that injects service status context into the RAG pipeline and adds the required frontend toggle."

### Claude CLI (claude-code) / Cursor Example

Reference the file explicitly so the assistant reads the architecture constraints before generating code:

> "Please read `Tlamatini/.mcps/create_new_mcp.md` first. Then add a new MCP-backed capability for local service health checks, wire it through `factory.py`, and update the UI and database toggle path correctly."

## Workflow Examples

### Example 1: Log Monitoring with Email Alert

Monitor an application log for errors and send email notifications.

```
┌─────────┐     ┌───────────────┐     ┌───────────┐
│ Starter │────>│ Monitor_Log_1 │────>│ Emailer_1 │
└─────────┘     └───────────────┘     └───────────┘
                      │
                      │ (on ERROR detected)
                      v
                ┌───────────┐
                │  Ender_1  │
                └───────────┘
```

**Monitor_Log_1 config.yaml:**
```yaml
target:
  logfile_path: "/var/log/myapp/app.log"
  keywords: "ERROR, FATAL, EXCEPTION"
  outcome_word: "TARGET_FOUND"
  poll_interval: 5
```

### Example 2: Scheduled Cleanup Workflow

Run maintenance tasks at a scheduled time.

```
┌──────────┐     ┌───────────┐     ┌───────────┐
│ Croner_1 │────>│ Deleter_1 │────>│ Executer_1│
└──────────┘     └───────────┘     └───────────┘
(2:00 AM)       (delete *.tmp)    (run backup.sh)
                                        │
                                        v
                                  ┌───────────┐
                                  │  Ender_1  │
                                  └───────────┘
```

### Example 3: Conditional Logic with AND Gate

Trigger only when BOTH conditions are met.

```
┌─────────────────┐
│  Monitor_Log_1  │──────┐
│  (ERROR found)  │      │
└─────────────────┘      v
                    ┌─────────┐     ┌───────────┐
                    │  AND_1  │────>│ Executer_1│
                    └─────────┘     └───────────┘
┌─────────────────┐      ^
│Monitor_Netstat_1│──────┘
│ (High Traffic)  │
└─────────────────┘
```

### Example 4: Real-Time Notification Pipeline

Monitor logs with the notifier agent and trigger alerts plus cleanup.

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌───────────┐
│ Starter │────>│ Monitor_Log_1 │────>│ Notifier_1  │────>│ Emailer_1 │
└─────────┘     └───────────────┘     └─────────────┘     └───────────┘
                                      (browser alert)           │
                                                                v
                                                          ┌───────────┐
                                                          │  Ender_1  │
                                                          └───────────┘
```

### Example 5: Branching Workflow with Forker

Automatically route based on execution outcome.

```
┌─────────┐     ┌─────────────┐     ┌──────────┐
│ Starter │────>│ Executer_1  │────>│ Forker_1 │
└─────────┘     └─────────────┘     └──────────┘
                                     │        │
                        (SUCCESS)    │        │  (FAILURE)
                                     v        v
                              ┌──────────┐  ┌──────────┐
                              │Emailer_1 │  │Emailer_2 │
                              │(success) │  │(failure) │
                              └──────────┘  └──────────┘
```

**Forker_1 config.yaml:**
```yaml
pattern_a: "EXECUTION SUCCESS"
pattern_b: "EXECUTION FAILED"
source_agents:
  - executer_1
target_agents_a:
  - emailer_1
target_agents_b:
  - emailer_2
poll_interval: 5
```

### Example 6: Interactive Decision with Asker

Pause workflow for user decision. Use `legend_path_a` and `legend_path_b` to describe each choice in the runtime dialog.

```
┌─────────┐     ┌───────────────┐     ┌──────────┐
│ Starter │────>│ Monitor_Log_1 │────>│ Asker_1  │
└─────────┘     └───────────────┘     └──────────┘
                                       │        │
                         (User: A)     │        │  (User: B)
                                       v        v
                                ┌──────────┐  ┌──────────┐
                                │Executer_1│  │ Ender_1  │
                                │(fix it)  │  │(ignore)  │
                                └──────────┘  └──────────┘
```

**Asker_1 config.yaml:**
```yaml
target_agents_a:
  - executer_1
target_agents_b:
  - ender_1
legend_path_a: 'Apply hotfix and restart'
legend_path_b: 'Ignore and escalate'
source_agents:
  - monitor_log_1
```

### Example 7: Python Validation with Pythonxer

Run a Python script to validate a condition before continuing.

```
┌─────────┐     ┌─────────────┐     ┌───────────┐
│ Starter │────>│ Pythonxer_1 │────>│ Emailer_1 │
└─────────┘     └─────────────┘     └───────────┘
              (exit 0 = proceed)   (only if True)
```

**Pythonxer_1 config.yaml:**
```yaml
script: |
  import os
  import sys
  # Check if disk usage is above 90%
  import shutil
  usage = shutil.disk_usage("/")
  percent = usage.used / usage.total * 100
  print(f"Disk usage: {percent:.1f}%")
  sys.exit(0 if percent > 90 else 1)
execute_forked_window: false
target_agents:
  - emailer_1
```

### Example 8: Email Monitoring with WhatsApp Alerts

Monitor incoming emails and send WhatsApp notifications on keyword matches.

```
┌─────────┐     ┌─────────────┐     ┌──────────────┐
│ Starter │────>│ Recmailer_1 │────>│ Whatsapper_1 │
└─────────┘     └─────────────┘     └──────────────┘
              (IMAP inbox monitor)  (WhatsApp alert)
```

### Example 9: Parallel Processing with Barrier Synchronization

Run multiple file-processing agents in parallel and synchronize them through a Barrier before continuing. The Barrier waits until **all** upstream agents have reported in, then unlocks and triggers the next stage. This is the fundamental fan-out / fan-in pattern.

```
                    ┌─────────────────┐
               ┌───>│ File Creator_1  │───┐
               │    └─────────────────┘   │
               │    ┌─────────────────┐   │
               ├───>│File Extractor_1 │───┤
┌─────────┐    │    └─────────────────┘   │    ┌───────────┐    ┌────────────┐    ┌────────┐    ┌────────────┐    ┌───────────┐
│ Starter │────┤                          ├───>│ Barrier_1 │───>│ Notifier_1 │───>│Ender_1 │───>│Flowbacker_1│───>│ Cleaner_1 │
└─────────┘    │    ┌─────────────────┐   │    └───────────┘    └────────────┘    └────────┘    └────────────┘    └───────────┘
               ├───>│File Interpreter_1│──┤     (waits for      (watches barrier   (stops all
               │    └─────────────────┘   │      all 4 flags)    log for unlock)    agents)
               │    ┌──────────────────┐  │
               └───>│Image Interpreter_1│─┘
                    └──────────────────┘
```

**Flow description:**

1. **Starter** launches four agents in parallel: File Creator, File Extractor, File Interpreter, and Image Interpreter.
2. Each agent processes its task independently (create files, extract content, interpret documents, analyze images).
3. When each agent finishes, it triggers `barrier_1` as its target. The Barrier creates a flag file for that agent.
4. The **last agent to arrive** detects all 4/4 flags present, deletes all flags, and fires `notifier_1`.
5. **Notifier** monitors the Barrier log for `"All flags present"`, triggers a browser notification, then starts the **Ender**.
6. **Ender** gracefully stops all running agents, then **Flowbacker** backs up the flow, and **Cleaner** removes temporary files.

**Barrier_1 config.yaml:**
```yaml
source_agents:
  - file_creator_1
  - file_extractor_1
  - file_interpreter_1
  - image_interpreter_1
target_agents:
  - notifier_1
```

**Notifier_1 config.yaml:**
```yaml
target:
  search_strings: "All flags present"
  outcome_detail: "Barrier passed!!"
  poll_interval: 2
source_agents:
  - barrier_1
target_agents:
  - ender_1
```

> **Key point:** The Barrier agent has no long-running process. Each input sub-process is short-lived: it creates its flag, atomically checks if all flags are present, and the *last arrival* fires the downstream targets. This avoids deadlocks with the `wait_for_agents_to_stop` pattern used by all agents.

---

## API Reference

### WebSocket Protocol

**Endpoint:** `ws://localhost:8000/ws/agent/`

#### Client to Server Messages

The current consumer accepts either a plain chat payload or one of the explicit control message types implemented in `agent/consumers.py`.

**Plain chat request:**
```json
{
  "message": "Your question here",
  "multi_turn_enabled": true
}
```

`multi_turn_enabled` is optional. If omitted or `false`, the request follows the legacy one-shot-compatible path. If `true`, the request uses the request-scoped Multi-Turn planner/selector path.

**Current explicit control message types:**

| Type | Purpose |
|------|---------|
| `set-canvas-as-context` | Use the current canvas file as context |
| `unset-canvas-as-context` | Remove the canvas file from context |
| `set-directory-as-context` | Load a directory as context |
| `set-file-as-context` | Load a single file as context |
| `cancel-current` | Cancel the current generation |
| `reconnect-llm-agent` | Rebuild the current LLM/RAG chain |
| `clean-history-and-reconnect` | Clear chat history and rebuild the chain |
| `clear-context` | Remove persisted context and rebuild the chain |
| `cancel-all` | Cancel all active generation work |
| `save-files-from-db` | Persist canvas/database-backed files |
| `enable-llm-internet-access` | Enable internet access for the LLM |
| `disable-llm-internet-access` | Disable internet access for the LLM |
| `view-context-dir-in-canvas` | Show the current context directory tree in the canvas |
| `set-file-omissions` | Update file omission patterns |
| `set-mcps` | Persist MCP enablement/configuration |
| `set-tools` | Persist tool enablement/configuration |
| `set-agents` | Persist agent enablement/configuration |

#### Server to Client Messages

**Chat / status broadcast:**
```json
{
  "message": "Processing request...",
  "username": "Tlamatini"
}
```

**Session Restored:**
```json
{
  "type": "session-restored",
  "context_type": "directory",
  "context_path": "/path/to/project"
}
```

### HTTP Endpoints

#### Pages

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET/POST | Login page (home) |
| `/welcome/` | GET | Welcome page |
| `/agent/` | GET | Main chat interface |
| `/agentic_control_panel/` | GET | Workflow designer |
| `/logout/` | GET | Logout |

#### Data Loading

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/load_canvas/<filename>/` | GET | Retrieve generated code |
| `/load_prompt/<prompt_name>/` | GET | Retrieve system prompt |
| `/load_omissions/<omission_name>/` | GET | Retrieve omission patterns |
| `/load_mcp/<mcp_name>/` | GET | Retrieve MCP definition |
| `/load_tool/<tool_name>/` | GET | Retrieve tool definition |
| `/load_agent/<agent_name>/` | GET | Retrieve agent content |
| `/load_agent_description/<agent_name>/` | GET | Retrieve agent description |
| `/load_agent_config/<agent_name>/` | GET | Load agent YAML configuration |

#### Agent Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/save_agent_config/<agent_name>/` | POST | Save agent YAML configuration |
| `/deploy_agent_template/<agent_name>/` | POST | Deploy agent to session pool |
| `/ensure_agent_exists/<agent_name>/` | GET | Verify agent exists in pool |
| `/execute_starter_agent/<agent_name>/` | POST | Start workflow via starter agent |
| `/execute_ender_agent/<agent_name>/` | POST | Stop workflow via ender agent |
| `/check_starter_log/<agent_name>/` | GET | Read starter agent log |
| `/check_ender_log/<agent_name>/` | GET | Read ender agent log |
| `/check_agents_running/<agent_name>/` | GET | Check if agent is running |
| `/check_all_agents_status/` | GET | Get status of all agents |
| `/read_agent_log/<agent_name>/` | GET | Read any agent's log file |
| `/restart_agent/<agent_name>/` | POST | Restart a specific agent |
| `/restart_agents/` | POST | Restart multiple agents |
| `/asker_choice/<agent_name>/` | POST | Submit user choice for Asker agent |
| `/execute_flowhypervisor/<agent_name>/` | POST | Start the FlowHypervisor agent |
| `/check_flowhypervisor_alert/<agent_name>/` | GET | Check for FlowHypervisor alerts |
| `/validate_flow/` | GET | Run the current ACP structural flow validation rules |

#### Connection Updates (Canvas Auto-Configuration)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/update_starter_connection/<agent_name>/` | POST | Update starter targets |
| `/update_ender_connection/<agent_name>/` | POST | Update ender targets |
| `/update_stopper_connection/<agent_name>/` | POST | Update stopper sources/patterns |
| `/update_raiser_connection/<agent_name>/` | POST | Update raiser connections |
| `/update_emailer_connection/<agent_name>/` | POST | Update emailer connections |
| `/update_monitor_log_connection/<agent_name>/` | POST | Update monitor_log connections |
| `/update_notifier_connection/<agent_name>/` | POST | Update notifier connections |
| `/update_executer_connection/<agent_name>/` | POST | Update executer connections |
| `/update_pythonxer_connection/<agent_name>/` | POST | Update pythonxer connections |
| `/update_sqler_connection/<agent_name>/` | POST | Update sqler connections |
| `/update_whatsapper_connection/<agent_name>/` | POST | Update whatsapper connections |
| `/update_recmailer_connection/<agent_name>/` | POST | Update recmailer connections |
| `/update_or_agent_connection/<agent_name>/` | POST | Update OR gate connections |
| `/update_and_agent_connection/<agent_name>/` | POST | Update AND gate connections |
| `/update_croner_connection/<agent_name>/` | POST | Update croner connections |
| `/update_mover_connection/<agent_name>/` | POST | Update mover connections |
| `/update_mouser_connection/<agent_name>/` | POST | Update mouser connections |
| `/update_keyboarder_connection/<agent_name>/` | POST | Update keyboarder connections |
| `/update_sleeper_connection/<agent_name>/` | POST | Update sleeper connections |
| `/update_cleaner_connection/<agent_name>/` | POST | Update cleaner connections |
| `/update_deleter_connection/<agent_name>/` | POST | Update deleter connections |
| `/update_asker_connection/<agent_name>/` | POST | Update asker A/B connections |
| `/update_forker_connection/<agent_name>/` | POST | Update forker A/B connections |
| `/update_dockerer_connection/<agent_name>/` | POST | Update dockerer connections |
| `/update_pser_connection/<agent_name>/` | POST | Update pser connections |
| `/update_kuberneter_connection/<agent_name>/` | POST | Update kuberneter connections |
| `/update_apirer_connection/<agent_name>/` | POST | Update apirer connections |
| `/update_jenkinser_connection/<agent_name>/` | POST | Update jenkinser connections |
| `/update_crawler_connection/<agent_name>/` | POST | Update crawler connections |
| `/update_summarizer_connection/<agent_name>/` | POST | Update summarizer connections |
| `/update_flowhypervisor_connection/<agent_name>/` | POST | Update flowhypervisor connections |
| `/update_counter_connection/<agent_name>/` | POST | Update counter connections |
| `/update_file_interpreter_connection/<agent_name>/` | POST | Update file-interpreter connections |
| `/update_image_interpreter_connection/<agent_name>/` | POST | Update image-interpreter connections |
| `/update_gatewayer_connection/<agent_name>/` | POST | Update gatewayer connections |
| `/update_gateway_relayer_connection/<agent_name>/` | POST | Update gateway_relayer connections |
| `/update_node_manager_connection/<agent_name>/` | POST | Update node_manager connections |
| `/update_file_creator_connection/<agent_name>/` | POST | Update file_creator connections |
| `/update_file_extractor_connection/<agent_name>/` | POST | Update file_extractor connections |
| `/update_j_decompiler_connection/<agent_name>/` | POST | Update j_decompiler connections |
| `/update_kyber_keygen_connection/<agent_name>/` | POST | Update kyber_keygen connections |
| `/update_kyber_cipher_connection/<agent_name>/` | POST | Update kyber_cipher connections |
| `/update_kyber_decipher_connection/<agent_name>/` | POST | Update kyber_decipher connections |
| `/update_parametrizer_connection/<agent_name>/` | POST | Update parametrizer connections |
| `/update_flowbacker_connection/<agent_name>/` | POST | Update flowbacker connections |
| `/get_parametrizer_dialog_data/<agent_name>/` | GET | Get Parametrizer mapping dialog data |
| `/save_parametrizer_scheme/<agent_name>/` | POST | Save Parametrizer interconnection scheme |
| `/update_barrier_connection/<agent_name>/` | POST | Update barrier connections |
| `/update_googler_connection/<agent_name>/` | POST | Update googler connections |

#### Session & Pool Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session_state/` | GET | Load current session state |
| `/save_session_state/` | POST | Save session state |
| `/clear_session_state/` | POST | Clear session state |
| `/clear_pool/` | POST | Clear agent pool directory |
| `/cleanup_session/` | POST | Full session cleanup |
| `/clear_agent_logs/` | POST | Clear all agent log files |
| `/clear_pos_files/` | POST | Clear all reanimation position files |
| `/reanimate_agents/` | POST | Reanimate agents from pause with AGENT_REANIMATED=1 env var |
| `/save_paused_agents/` | POST | Save running agents list to paused_agents.reanim |
| `/load_paused_agents/` | GET | Load paused agents list from paused_agents.reanim |
| `/delete_paused_agents/` | POST | Delete paused_agents.reanim after the reanimation request returns |
| `/delete_agent_pool_dir/<agent_name>/` | POST | Delete specific agent from pool |
| `/get_session_running_processes/` | GET | List running agent processes |
| `/kill_session_processes/` | POST | Kill all session agent processes |

---

## Session Management

Tlamatini maintains session state for continuous user experience:

### Session Persistence

- **Duration:** 24 hours from last activity
- **Storage:** Database (`SessionState` model)
- **Scope:** Per-user isolation
- **UI toggle persistence:** The Multi-Turn checkbox state is preserved per browser session in `sessionStorage`

### What's Preserved

- Current context path and type (directory/file)
- RAG chain state (in-memory)
- Chat history
- Active tool configurations

### Session Restoration

When reconnecting:
1. WebSocket connection established
2. System checks for existing session state
3. If valid (not expired), context is automatically restored
4. User receives `session-restored` message
5. RAG chain rebuilt with previous context

The frontend now reapplies restored context through a shared UI-state helper, so both directory contexts and file contexts recover the correct top-bar state. For file contexts, the UI derives the parent directory when filename metadata is present, which keeps directory-oriented actions such as **Open in...** and **View context dir in canvas** in sync after restore.

### Clearing Session

- Explicit: Use "Clear Context" button
- Automatic: After 24 hours of inactivity
- Manual: Close browser (in-memory state cleared)
- API: POST to `/cleanup_session/` or `/clear_session_state/`

---

## Open in... External Editors

Tlamatini includes an **"Open in..."** dropdown button in the navigation bar that lets you open the currently loaded context directory, or the parent directory of a loaded file context, directly in an external editor or file manager without leaving the application.

### Supported Applications

| Application     | Detection Method                                                                 |
|-----------------|----------------------------------------------------------------------------------|
| **File Explorer** | Always available (Windows built-in)                                            |
| **VS Code**       | Detected via the `code` command on PATH, or common Windows install locations   |
| **Antigravity**   | Detected via the `antigravity` command on PATH, or common Windows install locations |

Only applications that are actually installed on the system will appear in the dropdown. File Explorer is always shown.

### How to Use

1. **Load a directory or file as context** using the **Context** menu entries.
2. Wait for the context to be fully loaded (the context bar at the top will display the directory path).
3. The **"Open in..."** dropdown becomes enabled in the navigation bar (between the Context and MCPs menus).
4. Click **"Open in..."** and select the desired application from the dropdown.
5. The context directory, or the parent directory of the loaded file context, will open in a new window of the selected application.

### Behavior Details

- **Visibility:** The dropdown only appears if at least one supported application is detected on the system (File Explorer is always detected on Windows, so the dropdown is always visible).
- **Disabled state:** The dropdown is grayed out and non-interactive until a directory or file context is successfully loaded. When the active context is a file, the frontend resolves the containing directory and uses that as the target for **Open in...**.
- **During long operations:** The dropdown is automatically disabled while the LLM is processing a request or a context is being loaded, and re-enabled once the operation completes.
- **Reconnect / Clear context:** If the context is cleared or the session is reconnected, the dropdown returns to its disabled state.

### Canvas Agent Instance Shortcuts

The Agentic Control Panel canvas also exposes directory shortcuts for deployed agent instances through each node's right-click context menu:

- **`Explore dir...`** opens Windows File Explorer directly in the selected agent instance directory.
- **`Open cmd...`** opens a new `cmd.exe` window with its working directory set to the selected agent instance directory.

These shortcuts operate on the current session's deployed pool instance, not the template agent under `agent/agents/`. Internally the backend resolves the canvas id (for example `flowcreator-1`) to the session pool folder name (for example `flowcreator_1`) through `get_pool_path()`, so the behavior stays correct in both development mode and frozen/installed builds.

### API Endpoints

The feature relies on two HTTP endpoints:

- **`GET /agent/detect_installed_apps/`** — Returns a JSON list of applications and whether each is available on the system.
- **`POST /agent/open_in_app/`** — Accepts `app_id` plus either `directory` or `agent_name`. When `directory` is provided, it validates and opens that explicit path. When `agent_name` is provided, it resolves the current session's deployed agent-instance directory and opens it there. The endpoint is used by both the navigation-bar **"Open in..."** dropdown and the ACP canvas shortcuts, and supports `explorer`, `vscode`, `antigravity`, and `cmd` (Windows).

---

## Security Considerations

### Authentication

- Django user authentication required for all pages
- WebSocket connections authenticated via Django Channels middleware
- Session-based multi-user isolation
- CSRF protection on all state-changing endpoints

### Tiered Security Hardening (Test Suite)

The project includes a dedicated security test suite (`agent/tests.py`) with three hardening levels:

| Level | Class | What It Covers |
|-------|-------|----------------|
| **P0 (Critical)** | `P0HardeningTests` | User message isolation (users cannot see other users' messages), login requirement enforcement on all views, CSRF protection verification, WebSocket authentication |
| **P1 (High)** | `P1HardeningTests` | Path traversal prevention (`../` sequences, encoded escapes), `safe_join_under()` validation, runtime agent path resolution safety |
| **P2 (Prompt)** | `PromptPathHardeningTests` | Prompt injection defense — rejects absolute paths outside allowed directories, validates gRPC results against path escaping attempts |

The same `agent/tests.py` module now also includes regression coverage for:

- Ender cleanup/restart behavior
- prompt-validation decision paths
- loaded-documents fallback propagation into both prompt-only and unified chains
- `open_in_app` resolution for deployed canvas-agent instances
- Multi-Turn capability selection
- context-prefetch gating
- global execution planner/DAG behavior
- background console suppression for checked Multi-Turn launches
- frozen-mode compatibility for config and template-agent discovery

On the April 6, 2026 verification rerun in this workspace, `python Tlamatini/manage.py test agent.tests --verbosity 1` completed with **63/63 tests passing**.

### Path Guard (`path_guard.py`)

A centralized path validation module that protects all file operations:

- Resolves Windows known folders (Documents, Downloads, Desktop, etc.) via `win32com.shell`
- Validates every file path against `allowed_paths` from `config.json`
- Prevents directory traversal attacks (`../`, absolute paths, symlink escapes)
- Used by `chain_files_search_lcel.py`, `@tool` functions, and `consumers.py`

### Secret Redaction

Configure patterns to automatically redact sensitive data from context:

```json
{
  "redact_secrets_in_context": true
}
```

Add patterns in the `Omission` model via Django admin:
- API keys
- Passwords
- Connection strings
- Tokens

### Network Security

- Default binding: `127.0.0.1` (localhost only)
- SSL/TLS configuration available:
  ```json
  {
    "ssl_verify": true,
    "ssl_cert_file": "/path/to/cert.pem"
  }
  ```

### File Access

- Context loading respects OS permissions
- Centralized path validation via `path_guard.py`, restricting all file operations to explicitly configured safe directories in `config.json`
- Prompt-level path validation — the RAG interface detects and rejects indirect file access attempts via LLM analysis
- No automatic execution of uploaded files
- Sandbox-style tool execution (configurable)

### Recommendations

1. Run behind reverse proxy (nginx) in production
2. Enable HTTPS for all connections
3. Use strong passwords for superuser accounts
4. Regularly rotate API keys (Anthropic, TextMeBot, SMTP credentials)
5. Monitor agent execution logs
6. Keep `ANTHROPIC_API_KEY` and SMTP passwords out of version control

---

## Troubleshooting

### Common Issues

#### Ollama Connection Failed

**Symptom:** "Connection refused" or "Cannot connect to Ollama"

**Solutions:**
1. Ensure Ollama is running: `ollama serve`
2. Check URL in config.json: `"ollama_base_url": "http://127.0.0.1:11434"`
3. Verify model is pulled: `ollama list`
4. If using a remote Ollama, set `ollama_token` for authentication

#### RAG Context Not Loading

**Symptom:** Responses don't reflect project context

**Solutions:**
1. Check context was set (look for confirmation message)
2. Verify path permissions
3. Ensure files are text-based (not binary)
4. Check `max_doc_chars` limit in config
5. If Ollama reports insufficient memory during embedding initialization, Tlamatini now falls back to a loaded-context mode; answers should still use the loaded files, but retrieval quality may be reduced until the embedding model can run normally

#### Multi-Turn Not Engaging

**Symptom:** Requests still behave like the old one-shot chat path, or the LLM says tools are "not available"

**Solutions:**
1. Ensure the **Multi-Turn** checkbox beside **Clear history** is checked before sending the prompt
2. Confirm the request payload is sending `multi_turn_enabled: true`
3. Verify `enable_unified_agent` is enabled in `config.json`
4. Check that the relevant MCPs/tools are enabled in the chat configuration dialogs
5. Remember that unchecked mode intentionally preserves the old prompt validation and full-tool behavior
6. Check the Django console for `[Planner._select]` log lines — they show which tools were scored and selected. If the tools you need were excluded, the planner's scoring threshold may need adjustment
7. If the LLM reports "Tool X is not available in this session", look for `[Planner._select] SELECTED` lines to confirm which tools were actually bound. Run-control tools are auto-injected and should not inflate the scoring floor

#### Frozen Build Uses Wrong Config

**Symptom:** The packaged build ignores expected config or Multi-Turn file-context behavior differs from source mode

**Solutions:**
1. Place the effective `config.json` beside the packaged executable, or set `CONFIG_PATH`
2. Verify the packaged install includes the expected `agents/` directory structure
3. Confirm the executable-local `config.json` contains the expected unified-agent and MCP settings
4. Rebuild if the packaged payload omitted required runtime assets such as `README.md`, `jd-cli/`, or template-agent directories

#### WebSocket Disconnections

**Symptom:** Chat disconnects frequently

**Solutions:**
1. Check network stability
2. Increase Daphne timeout settings
3. Verify no proxy is interfering
4. Check browser console for errors

#### Agent Not Starting

**Symptom:** Workflow agent fails to start

**Solutions:**
1. Check agent log file in pool directory
2. Verify config.yaml syntax (valid YAML)
3. Ensure Python path is correct
4. Check for port conflicts (MCP servers)
5. Use "Read Log" in the workflow designer for real-time debugging

#### Memory Issues

**Symptom:** Application becomes slow or crashes

**Solutions:**
1. Reduce `chunk_size` in config
2. Lower `k_vector` and `k_bm25` values
3. Limit `max_chunks_per_file`
4. Reduce `max_context_chars`

#### Image Analysis Fails

**Symptom:** "Error analyzing image" or no response

**Solutions:**
1. For Claude (Opus): Check `ANTHROPIC_API_KEY` in config.json
2. For Qwen: Verify vision model is pulled in Ollama (`ollama list`)
3. Check `image_interpreter_base_url` points to running Ollama
4. Ensure image file exists and is a supported format

#### Forker/Asker Not Routing

**Symptom:** Routing agents don't trigger target paths

**Solutions:**
1. Verify `pattern_a` / `pattern_b` match the actual log output of source agents
2. Check that `source_agents` and `target_agents_a/b` are populated (canvas auto-config)
3. Read the forker/asker log file for pattern matching diagnostics
4. For Asker: ensure the frontend dialog appeared (check browser console)

### Debug Mode

Enable verbose RAG logging in config.json:

```json
{
  "logging": {
    "verbose_metadata": true,
    "log_retrieval_metrics": true,
    "log_context_size": true,
    "log_query_rewrites": true
  }
}
```

**Multi-Turn and runtime logging** is configured via Django's `LOGGING` setting in `tlamatini/settings.py`. The following loggers emit `INFO`-level diagnostics to the console:

| Logger | What it logs |
|--------|-------------|
| `agent.chat_agent_runtime` | Runtime directory creation, template copy, script resolution, subprocess launch, PID, Python executable selection (frozen vs source) |
| `agent.tools` | Wrapped chat-agent launch lifecycle: template discovery, config.yaml load/write, parameter assignment, script resolution, final runtime directory contents |
| `agent.mcp_agent` | Multi-turn tool invocation: which tools are called, arguments, return values for `chat_agent_*` tools |
| `agent.global_execution_planner` | Planner scoring: per-tool score, selected tools, threshold, top score |
| `agent.capability_registry` | Capability scoring details |

All log lines are prefixed with timestamps and logger names (e.g. `2026-04-13 12:28:39 [agent.tools] INFO [tools._launch_wrapped_chat_agent] ...`).

### Log Locations

- **Django/Multi-Turn logs**: Console output (stdout) — includes planner scoring, tool selection, runtime creation, and subprocess launch diagnostics
- **ACP workflow agent logs**: `<pool_directory>/<agent_name>/<agent_name>.log`
- **Chat-launched wrapped agent logs**: `agent/agents/pools/_chat_runs_/<agent>_<seq>_<id>/<agent>_<seq>_<id>.log` — each run gets its own sequenced directory, failed runs are preserved
- **Application-wide log**: `Tlamatini/tlamatini.log` — see [Application Log](#application-log-tlamatinilog) below

---

## Application Log (tlamatini.log)

Tlamatini ships a built-in application log that captures **all console output** (stdout and stderr) into a single file. This is the primary diagnostic artifact for the running server — every print statement, Django startup message, HTTP request log, warning, traceback, and structured logger message ends up here alongside the normal console output.

### <a id="tlamatini-log-location"></a>Location

| Mode | Log file path |
|------|---------------|
| **Source (development)** | `Tlamatini/tlamatini.log` — same directory as `manage.py` |
| **Frozen (PyInstaller .exe)** | Next to the executable, e.g. `C:\Program Files\Tlamatini\tlamatini.log` |

The path is resolved at startup in `manage.py` using the standard frozen-mode detection pattern:

```python
if getattr(sys, 'frozen', False):
    log_dir = os.path.dirname(sys.executable)        # frozen .exe directory
else:
    log_dir = os.path.dirname(os.path.abspath(__file__))  # manage.py directory
```

### How It Works: The Tee Stream Architecture

The log is **not** implemented through Django's `LOGGING` setting or a file-based logging handler. Instead, `manage.py` defines a lightweight `_TeeStream` class that **wraps `sys.stdout` and `sys.stderr`** before Django even initializes:

```
┌──────────────────────────────────────────────────┐
│  Any Python output (print, logging, tracebacks)  │
└──────────────────┬───────────────────────────────┘
                   │
            ┌──────▼──────┐
            │  _TeeStream  │
            └──┬───────┬──┘
               │       │
     ┌─────────▼─┐  ┌──▼──────────────┐
     │  Console   │  │  tlamatini.log  │
     │  (original │  │  (file on disk) │
     │   stream)  │  │                 │
     └───────────┘  └─────────────────┘
```

Every call to `write()` on either stream is duplicated: the original console receives the data as usual, and a second copy is written to the log file with an **immediate `flush()`** to ensure nothing is lost if the process crashes. Write failures to the file are silently ignored so that a full disk or permission error never breaks the console output.

The tee is installed at **module import time** (line 61 of `manage.py`), which means it captures output from the earliest moments of Django's startup — including the `Watching for file changes with StatReloader` banner and `collectstatic` summaries.

### What the Log Contains

Because the tee captures all of stdout/stderr, the log file includes:

| Source | Example content |
|--------|----------------|
| **Django startup** | System check messages, migration status, server address |
| **HTTP request log** | `"GET /agent/ HTTP/1.1" 200` lines from Django's dev server |
| **Structured loggers** | Timestamped `INFO`/`WARNING`/`ERROR` lines from the five configured loggers (see below) |
| **Print statements** | Any `print()` call anywhere in the codebase |
| **Tracebacks** | Full Python exception tracebacks written to stderr |
| **Third-party library output** | Warnings from LangChain, FAISS, gRPC, etc. |
| **Subprocess output** | If a subprocess inherits stdout/stderr, its output appears here too |

### Django Logger Integration

Django's `LOGGING` configuration in `settings.py` defines five module-specific loggers, all routed to a `StreamHandler` (i.e. console). Because the console is wrapped by `_TeeStream`, these structured log lines automatically flow into `tlamatini.log` as well:

| Logger name | What it captures |
|-------------|-----------------|
| `agent.chat_agent_runtime` | Wrapped chat-agent runtime lifecycle — creation, start, stop, status transitions |
| `agent.tools` | Tool invocation details — which tools are called, arguments, return values |
| `agent.mcp_agent` | Multi-turn tool loop execution, MCP agent decisions |
| `agent.global_execution_planner` | Planner scoring: per-tool scores, selected tools, threshold, top score |
| `agent.capability_registry` | Capability scoring and tool-selection details |

All five loggers use the same formatter:

```
%(asctime)s [%(name)s] %(levelname)s %(message)s
```

Producing lines like:

```
2026-04-15 10:42:17 [agent.tools] INFO [tools._launch_wrapped_chat_agent] Launching executer run #3 ...
```

### Lifecycle and Rotation

- **Truncated on every restart**: The log file opens in **write mode (`'w'`)**, not append mode. Each time the server starts, the previous log is overwritten. This keeps the file relevant to the current session and prevents unbounded growth.
- **No size limit or rotation**: There is no `RotatingFileHandler` or max-size cap on `tlamatini.log`. For long-running sessions, the file grows as long as the server runs.
- **Encoding**: UTF-8.
- **Graceful degradation**: If the log file cannot be created (e.g. read-only filesystem), the tee setup is silently skipped and the application runs normally with console-only output.

> **Tip**: If you need to preserve logs across restarts, copy or rename `tlamatini.log` before restarting the server. For workflow agent logs (which are per-agent and per-session), see [Log Locations](#log-locations) above.

---

## Glossary

| Term | Definition |
|------|------------|
| **RAG** | Retrieval-Augmented Generation - technique to provide LLMs with relevant context from documents |
| **FAISS** | Facebook AI Similarity Search - library for efficient similarity search of vectors |
| **BM25** | Best Matching 25 - probabilistic information retrieval algorithm |
| **RRF** | Reciprocal Rank Fusion - method to combine multiple ranked lists |
| **MCP** | Model Context Protocol - standardized protocol for tool/context communication |
| **LangChain** | Framework for developing applications powered by language models |
| **LangGraph** | LangChain extension for building stateful, multi-actor applications |
| **ASGI** | Asynchronous Server Gateway Interface - Python standard for async web servers |
| **Daphne** | HTTP, HTTP2, and WebSocket protocol server for ASGI |
| **WebSocket** | Protocol providing full-duplex communication over TCP |
| **Embedding** | Numerical vector representation of text for similarity comparison |
| **FlushingFileHandler** | Custom logging handler that flushes after every write for real-time log visibility |
| **Context Budget** | Allocation strategy for distributing token limits across document types |
| **Chunk** | Segment of a document after splitting for processing |
| **Agent** | Autonomous process that performs specific workflow tasks |
| **Logic Gate** | Agent that performs boolean operations (AND/OR) on events |
| **Routing Agent** | Agent that directs workflow flow to one of multiple paths (Asker, Forker) |
| **Notifier** | LangGraph-based agent that monitors logs and triggers browser notifications |
| **Stopper** | Single-threaded agent that sequentially polls and terminates other agents based on patterns. Uses `output_agents` (not `target_agents`) for canvas wiring |
| **Pythonxer** | Agent that executes Python scripts with Ruff validation and boolean exit code |
| **Keyboarder** | Deterministic PyAutoGUI-based keyboard automation agent that parses comma-separated key sequences, hotkey chords joined with `+`, and quoted literal strings, then emits them step by step according to `stride_delay` before triggering downstream agents |
| **Recmailer** | LangGraph agent that monitors IMAP email inbox with LLM-based keyword analysis |
| **Whatsapper** | Agent that sends WhatsApp notifications via TextMeBot API with LLM summarization |
| **Forker** | Deterministic agent that routes workflows to Path A or B based on log patterns |
| **Gitter** | Deterministic agent that executes Git operations (clone, pull, push, commit, etc.) on local repositories |
| **Mouser** | Deterministic agent that moves the mouse pointer randomly or to a specific position and, in localized mode, can optionally issue a configured click after reaching the destination, then triggers downstream agents |
| **Dockerer** | Manages Docker containers and docker-compose operations, starting downstream agents after execution |
| **Pser** | LLM-powered agent that finds running processes by fuzzy name matching and logs the best match |
| **Apirer** | HTTP/REST API agent that makes HTTP requests to any URL and starts downstream agents regardless of outcome |
| **Jenkinser** | CI/CD pipeline trigger agent that triggers Jenkins builds and starts downstream agents regardless of trigger result |
| **Counter** | Deterministic agent that maintains a persistent counter and routes workflows to Path L or G based on threshold comparison |
| **Crawler** | LLM-powered developer-oriented web crawler that fetches pages in raw mode (full HTML/JS/CSS/headers) or text mode, generates resource inventories, and processes content with an LLM in three range modes (small/medium/large) |
| **Summarizer** | LLM-powered log monitoring agent that polls source agent logs and uses an LLM to detect events, triggering downstream agents on positive detection |
| **File-Interpreter** | Hybrid agent that reads and parses document files, extracting text and images, with optional LLM-powered summarization |
| **Image-Interpreter** | Non-deterministic agent that analyzes images using an LLM vision model, logging structured descriptions for each image |
| **FlowHypervisor** | System-managed LLM anomaly detector that watches all running agents' processes and log files, builds NxN connection matrices, performs incremental log analysis, and alerts the user to anomalies. Supports reanimation via `reanim.json` for crash recovery, user-configurable `user_instructions` for fine-tuning supervision, and dual-layer auto-stop |
| **Flow Validation** | Pre-execution structural verification that builds an NxN adjacency matrix from agent connections and validates the current Starter, Ender, Cleaner, FlowBacker, self-connection, orphan, and dangling-reference rules |
| **jd-cli** | Java Decompiler CLI tool bundled with the application for decompiling JAR/WAR files to source code |
| **PyAutoGUI** | Python library for programmatic mouse and keyboard control, used by the Mouser and Keyboarder agents |
| **Asker** | Deterministic agent that pauses workflow for interactive user A/B choice |
| **Workflow** | Connected sequence of agents performing automated tasks |
| **Canvas** | UI area for displaying and editing generated code |
| **Session State** | Persisted user context and preferences |
| **Pool** | Directory where deployed agent instances are stored |
| **output_agents** | Config field used by Ender, Stopper, and Cleaner for downstream canvas wiring. Ender uses `target_agents` for its kill list and `output_agents` for Cleaners to launch, while most other agents use `target_agents` for starting downstream agents |
| **FlowCreator** | AI-powered agent that generates complete flow configurations from natural language using an LLM and the `agentic_skill.md` schema |
| **Cardinal** | Numeric suffix added to deployed agents (e.g., `_1`, `_2`) to support multiple instances |
| **Reanimation Offset** | Saved position in log file to handle restarts and log rotation |
| **TextMeBot** | Third-party API service for sending WhatsApp messages programmatically |
| **Ruff** | Fast Python linter used by Pythonxer for script validation |
| **Gatewayer** | Inbound gateway agent that receives external events via HTTP webhook or folder-drop watcher, persists them as event artifacts, and dispatches to downstream agents. HTTP ingress authenticates/validates; folder-drop is best-effort parsing plus dispatch |
| **GatewayRelayer** | Long-running deterministic ingress relay that bridges provider-native webhooks (e.g. GitHub) into Gatewayer's canonical timestamp+body HMAC format without modifying Gatewayer itself |
| **NodeManager** | Long-running infrastructure agent that maintains a live registry of local/remote nodes, probes health, classifies state (ONLINE/OFFLINE/DEGRADED/UNKNOWN), detects capability changes, and triggers downstream agents on node events |
| **File-Creator** | Short-running infrastructure agent that creates a file with specified content (path + filename, raw content), triggers downstream agents regardless of file creation result, then stops |
| **File-Extractor** | Short-running infrastructure agent that reads/loads files (supports wildcards), extracts text content for all file types supported by File-Interpreter, uses strings extraction for unknown binary types, triggers downstream agents regardless of result, then stops |
| **J-Decompiler** | Short-running deterministic action agent that decompiles `.class`, `.jar`, `.war`, and `.ear` artifacts using the bundled `jd-cli`, generating source trees beside the original files and triggering downstream agents afterward |
| **Kyber-KeyGen** | Short-running infrastructure deterministic agent that generates CRYSTALS-Kyber public/private key pairs (Kyber-512/768/1024) in base64 format, logs keys, and triggers downstream agents |
| **Kyber-Cipher** | Short-running infrastructure deterministic agent that encrypts a buffer using a CRYSTALS-Kyber public key via encapsulation + AES-256-CTR, logs encapsulation/IV/ciphertext in base64, and triggers downstream agents |
| **Kyber-DeCipher** | Short-running infrastructure deterministic agent that decrypts cipher text using a CRYSTALS-Kyber private key via decapsulation + AES-256-CTR, logs deciphered buffer, and triggers downstream agents |
| **Parametrizer** | Short-running active utility interconnection agent that maps structured outputs from a source agent's log to a target agent's config.yaml via a deployed interconnection scheme CSV, supporting iterative execution for multiple output elements |
| **Barrier** | Short-running passive utility flow-control agent that acts as a synchronization barrier, waiting for ALL configured source agents to start before triggering downstream target agents via cross-process file-based locking and flag files |
| **Googler** | Short-running web-search agent that searches Google for a configured query using Playwright browser automation, fetches the top N result pages, extracts readable text content, and saves the combined results to an output file for downstream processing |

---

## Keyboarder Supported Keys

The **Keyboarder** agent simulates human keyboard input through the `input_sequence` field.

- **Literal strings**: Enclose them in single or double quotes, for example `'Hello World'`.
- **Simultaneous keys**: Join keys with `+`, for example `ctrl+c` or `shift+alt+delete`.
- **Sequential commands**: Separate each action with commas, for example `escape, escape, ctrl+c, 'hello'`.

Below is the practical Windows-oriented key reference for `input_sequence`:

| Category | Supported Keys |
|---|---|
| **Modifiers** | `ctrl`, `shift`, `alt`, `altgr`, `win`, `windows`, `command`, `option` |
| **Arrows** | `left`, `<-(left arrow)`, `right`, `->(right arrow)`, `up`, `up arrow`, `down`, `down arrow` |
| **Navigation** | `home`, `end`, `pageup`, `pgup`, `pagedown`, `pgdn` |
| **Editing** | `enter`, `return`, `esc`, `escape`, `backspace`, `space`, `tab`, `del`, `delete`, `insert` |
| **Locks** | `capslock`, `mayus`, `mayuscula`, `numlock`, `scrolllock` |
| **Function Keys** | `f1` through `f24` |
| **Media and System** | `volumedown`, `volumeup`, `volumemute`, `playpause`, `nexttrack`, `printscreen`, `prtsc`, `pause`, `apps` |
| **Symbols and Numbers** | digits `0` through `9`, common punctuation, `tab`, newline-style escapes such as `\n` and `\r`, and standard symbol keys including `/`, `\\`, `[`, `]`, `-`, `=`, `,`, `.`, `;`, `'`, `` ` ``, `{`, `}`, `~`, `!`, `?`, `@`, `#`, `$`, `%`, `&`, `*`, `+`, `<`, `>` |

*Note: Commands are case-insensitive internally, but literal quoted text preserves the exact capitalization you write.*

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add tests for new features
- Update documentation for API changes
- Use meaningful commit messages

---

## License

This project is licensed under the **GNU General Public License v3.0** - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Django](https://www.djangoproject.com/) - Web framework
- [LangChain](https://github.com/langchain-ai/langchain) - LLM orchestration
- [LangGraph](https://github.com/langchain-ai/langgraph) - Stateful agent workflows
- [Ollama](https://ollama.ai/) - Local LLM inference
- [FAISS](https://github.com/facebookresearch/faiss) - Vector similarity search
- [Anthropic](https://www.anthropic.com/) - Claude API
- [Bootstrap](https://getbootstrap.com/) - Frontend framework
- [TextMeBot](https://textmebot.com/) - WhatsApp messaging API
- [Ruff](https://github.com/astral-sh/ruff) - Python linter
- [PyAutoGUI](https://github.com/asweigart/pyautogui) - Mouse/keyboard automation
- [JD-CLI](https://github.com/intoolswetrust/jd-cli) - Java decompiler CLI

---

## Changelog

### Recent Updates
- **Sequenced Runtime Directories for Wrapped Chat-Agent Runs** - Each `chat_agent_*` tool invocation now creates a **unique, sequenced directory** under `_chat_runs_/{agent}_{seq:03d}_{short_id}/` (e.g. `executer_001_a1b2c3d4`, `executer_002_e5f67890`). Failed runs are never overwritten, preserving the full execution history including logs, configs, and exit codes from every attempt. The global sequence counter is thread-safe, monotonically increasing across all agent types, and re-seeds from existing directories on server restart
- **Planner Tool Selection Fix** - Fixed a critical bug where the Global Execution Planner excluded wrapped agent tools from Multi-Turn requests. Run-control tools (`chat_agent_run_list/status/log/stop`) no longer inflate the scoring floor since they are auto-injected. The dynamic floor was replaced with a simple threshold filter, and the max tool selection cap was raised from 12 to 50 to match the full agent catalogue
- **Comprehensive Multi-Turn Runtime Logging** - Added `INFO`-level logging across the entire wrapped chat-agent launch pipeline: `chat_agent_runtime.py` (directory creation, template copy, script resolution, subprocess launch, Python executable selection), `tools.py` (template discovery, config.yaml lifecycle, launch result), `mcp_agent.py` (tool invocation/result for `chat_agent_*` tools), and `global_execution_planner.py` (per-tool scoring, selection decisions). All loggers are configured in `tlamatini/settings.py` with timestamped console output
- **Multi-Turn UI Toggle and Explicit Opt-In Path** - The main chat toolbar now includes a dedicated **Multi-Turn** checkbox beside **Clear history**, persists it per browser session, and forwards `multi_turn_enabled` with each request so the orchestration path is opt-in rather than silently forced on every chat turn
- **Phase 1 Capability Selection** - `capability_registry.py` now scores request/tool affinity and lets checked Multi-Turn requests bind only the relevant tools or wrapped agents instead of exposing the entire enabled tool universe on every request
- **Phase 2 Context Capability Selection** - `rag/factory.py` now selectively prefetches `system_context` and `files_context` for checked Multi-Turn requests, while unchecked requests still use the legacy context-prefetch behavior
- **Phase 3 Global Execution Planner** - `global_execution_planner.py` now builds request-scoped execution DAGs with `prefetch`, `execute`, `monitor`, and `answer` nodes, plus `direct_model`, `context_only`, and `tool_augmented` execution modes
- **Focused File-Context Hardening for Multi-Turn** - Project-home requests such as root `README.md` lookups are narrowed more deterministically, exact single-file reads no longer force unnecessary global file-manifest prompt bloat in checked mode, and the file-search chain now resolves default frozen-mode config from the executable directory
- **Checked-Mode Runtime Hardening** - Checked Multi-Turn requests suppress visible console popups for wrapped/background launches, bypass only the prompt-shape validation gate, and preserve the legacy launch and validation behavior when unchecked
- **Verification Status Raised to Full Green** - `agent/tests.py` now includes Multi-Turn planner, gating, background-launch, and frozen-mode regression coverage, and the current April 6 verification rerun completed with `63/63` passing tests
- **Main Chat Context UI State Sync** - `agent_page_ui.js` now centralizes restored context handling through `applyContextUiState()`, while `agent_page_chat.js` routes both `session-restored` and `context-path-set` through that shared helper. File contexts now recover a parent-directory-backed `actualContextDir`, which keeps **Open in...** and **View context dir in canvas** aligned after reconnects and context reloads
- **RAG Loaded-Documents Fallback Hardening** - `rag/factory.py` now preserves successfully loaded documents as a packed fallback context with a file manifest when retrieval-chain construction fails. That fallback is propagated into both `BasicPromptOnlyChain` and `UnifiedAgentChain`, and `agent/tests.py` now includes `LoadedContextFallbackTests` to verify both code paths
- **Configurable Runtime Limits and Demo Prompts** - `config.json` now sets `unified_agent_max_iterations` and `chat_agent_limit_runs` to `100`, `config_loader.py` centralizes frozen/source-aware config loading, `chat_agent_runtime.py` uses the configured run-list cap by default, and migrations `0002_populate_db.py` / `0067_add_multi_turn_demo_prompts.py` seed three multi-turn demo prompts (`idPrompt` 25-27)
- **Keyboarder Canvas Wiring** - `keyboarder` is now a first-class ACP auto-configuration participant: the frontend styles it explicitly, `acp-agent-connectors.js` posts to `/update_keyboarder_connection/<agent_name>/`, and the backend updates its `source_agents` / `target_agents` lists in the deployed pool instance `config.yaml`
- **Mouser Localized Click Actions** - Mouser now supports `button_click` values such as `left`, `right`, `middle`, and `double-left/right/middle`. The properties dialog only enables those options for localized movement, and the runtime only emits the configured click after the cursor has actually reached the intended destination
- **Added Keyboarder Agent** - Issues a sequence of keys to emulate human typing on the keyboard.
- **Added Googler Agent** - Searches Google for a configured query using Playwright, fetches top N result pages, extracts readable text, and saves results to an output file. Includes full ACP canvas wiring with Google brand-inspired 4-color gradient.

- **ACP Agent Descriptions and Instance Context Menus** - `agentic_control_panel()` now parses the `## Workflow Agents` Purpose column from `README.md`, injects an `agent_purpose_map` into the ACP template, and the frontend uses it for sidebar hover tooltips and the new canvas **Description** dialog. The right-click menu for deployed agents now also exposes **`Explore dir...`** and **`Open cmd...`**, and `/agent/open_in_app/` accepts `agent_name` so those actions resolve the current session-pool instance directory instead of the template folder. `agent/tests.py` now includes regression coverage for those instance-directory actions
- **Parametrizer Nested Target Mapping** - The Parametrizer dialog now flattens nested target `config.yaml` dictionaries into dot-notation keys, and runtime mapping now writes dot-notation targets back into nested YAML structures. This lets a source output field populate sub-config entries such as `target.smtp.username` instead of only top-level keys
- **Build and Installer Robustness** - `build.py` now treats `README.md` and `jd-cli/` as required release payloads, verifies that `jd-cli.bat` is present after copy, and exits non-zero if those assets are missing instead of silently shipping a partial package. `install.py` now strips PyInstaller bundle paths from helper subprocess environments when running PS1 scripts or restarting Explorer, which is intended to prevent the frozen installer from stalling on locked DLL paths
- **Extension Query Parsing Hardening** - `history_aware.py` and `unified.py` now require a non-word boundary before `.ext`-style extension matches, reducing false-positive "list .ext files" detection on dotted tokens and embedded code-like text
- **J-Decompiler Development Path Fix** - `agent/agents/j_decompiler/j_decompiler.py` now climbs one more directory level before locating the bundled `jd-cli/` payload in development mode, so local-source runs resolve the decompiler asset from the project root correctly
- **Main Chat Multi-Turn Tool Loop** - `agent/mcp_agent.py` now builds a `MultiTurnToolAgentExecutor` for the unified chat path. Instead of a single opaque tool-call pass, the backend now iterates through model tool requests explicitly, executes them in-process, appends `ToolMessage` observations, and continues until a final answer or the iteration limit is reached
- **Wrapped Chat-Agent Runtime Layer** - Added `chat_agent_registry.py`, `chat_agent_runtime.py`, migration `0064_add_chat_agent_run_model.py`, migration `0065_add_chat_wrapped_agent_tools.py`, and the `ChatAgentRun` model. The chat surface can now launch 32 isolated `chat_agent_*` runtime copies of template agents plus 4 run-management tools (`chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`, `chat_agent_run_stop`)
- **Chat Runtime Isolation from ACP Flow Control** - ACP/session process scans now skip the `agent/agents/pools/_chat_runs_/` runtime root, so flow pause/status/kill logic tracks only deployed canvas agents and does not accidentally terminate chat-launched wrapped runtimes. Each run now gets a unique sequenced directory (`{agent}_{seq:03d}_{short_id}`) instead of overwriting the previous run
- **Added J-Decompiler Agent** - Short-running deterministic action agent that decompiles `.class`, `.jar`, `.war`, and `.ear` artifacts using the bundled `jd-cli`, supports wildcard and recursive scans, writes Java sources beside the original artifacts, and triggers downstream agents after completion
- **Added Barrier Agent** - Short-running passive utility flow-control agent that acts as a synchronization barrier. Waits for ALL configured source agents to start before triggering downstream target agents. Uses cross-process file-based locking and flag files to coordinate multiple separate barrier processes started by source agents
- **Added Parametrizer Agent** - Short-running active utility interconnection agent that maps structured outputs from source agent logs to target agent config.yaml parameters via a visual mapping dialog and a deployed interconnection-scheme CSV saved for the current pool instance. Supports iterative execution for multiple output elements, connecting current structured-output sources (Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Gatewayer, and Gateway-Relayer) to any target agent
- **Added Kyber-DeCipher Agent** - Short-running infrastructure deterministic agent that decrypts cipher text using a CRYSTALS-Kyber private key via decapsulation + AES-256-CTR, logs deciphered buffer in original format
- **Added Kyber-Cipher Agent** - Short-running infrastructure deterministic agent that encrypts a buffer using a CRYSTALS-Kyber public key via Kyber encapsulation + AES-256-CTR, logs encapsulation, initialization vector, and cipher text in base64 format
- **Added Kyber-KeyGen Agent** - Short-running infrastructure deterministic agent that generates CRYSTALS-Kyber public/private key pairs (Kyber-512, Kyber-768, Kyber-1024) in base64 format, logs keys in structured format, and triggers downstream agents
- **Added `filetype_exclusions` parameter to File-Interpreter, Image-Interpreter, File-Extractor, Mover, and Deleter** — Comma-separated string (default: empty) that accepts extensions (e.g. `exe`, `msi`), dotfiles (e.g. `.profile`), or specific filenames (e.g. `main.cpp`). Matching files are excluded from each agent's core processing. Appears as a single-line text input in each agent's configuration dialog.
- **Added `recursive` parameter to File-Interpreter, Image-Interpreter, File-Extractor, Mover, and Deleter** — Boolean checkbox (default: false) that enables recursive subdirectory scanning. When enabled, patterns like `C:\data\*.txt` automatically expand to `C:\data\**\*.txt`, and bare directories scan their entire tree. Appears as a checkbox in each agent's configuration dialog.
- **Added File-Extractor Agent** - Short-running infrastructure agent that reads/loads files (supports wildcards), extracts text content for all file types File-Interpreter supports, uses strings-like extraction for unknown binary types, logs content in INI_FILE/END_FILE format, triggers downstream agents regardless of result, then stops itself
- **Added File-Creator Agent** - Short-running infrastructure agent that creates a file with specified content (path + filename + extension, raw content), triggers downstream agents regardless of file creation result, then stops itself
- **Added NodeManager Agent** - Long-running infrastructure agent that maintains a live registry of local and remote Windows/Linux nodes, probes health via ping, TCP, SSH, WinRM, and HTTP checks, classifies node state (ONLINE/OFFLINE/DEGRADED/UNKNOWN), detects capability changes, persists normalized node state to disk via reanim files, exports filtered selected-node manifests, and triggers downstream agents on configured node events. Supports static inventory, optional discovery, parallel probing, per-node file export, and event-based triggers
- **Added GatewayRelayer Agent** - Long-running deterministic ingress relay that bridges provider-native webhooks (e.g. GitHub) into Gatewayer's canonical timestamp+body HMAC format. Validates upstream X-Hub-Signature-256 signatures, transforms payloads into Gatewayer-compatible canonical input, HMAC-signs the forwarded body, and relays to a configured Gatewayer HTTP endpoint. Supports configurable event/ref filtering, ping handling, TLS, and downstream agent triggering after successful forwards
- **Added Gatewayer Agent** - Inbound gateway agent for receiving external events via HTTP webhook or folder-drop watcher. Validates, authenticates, normalizes into canonical envelopes, persists to disk, queues with dedup, and dispatches to downstream target_agents. Supports bearer/HMAC auth, TLS, crash-recovery via reanim files, and configurable event retention
- **FlowHypervisor User Instructions** - FlowHypervisor now supports a `user_instructions` config field (editable as a textarea in the properties dialog) that lets users append custom directives to the monitoring prompt — e.g. dismiss known false positives, emphasize specific agents, adjust sensitivity thresholds, or add domain-specific rules
- **FlowHypervisor Core Auto-Stop** - The core system now stops the FlowHypervisor agent immediately when no non-system agents are running in the flow, via a `flow_alive` flag returned by the alert-check endpoint. The agent's existing 3-cycle self-stop is retained as a safety net for when the core/browser is killed or frozen
- **Crawler Substantially Improved** - Now captures **raw content** by default (complete HTML markup, JavaScript, CSS, meta tags, HTTP response headers, JSON-LD structured data) instead of plain text. Generates resource inventories cataloging scripts, styles, forms, images, endpoints, and data-* attributes. Developer-oriented LLM preamble for deep technical analysis of page structure, security patterns, and framework signatures
- **Ender Reanimation Asset Clearing** - Ender now deletes all `reanim*` prefixed files (reanim.pos, reanim.counter, reanim_\<source\>.pos) from terminated agent directories, enabling clean contextual restarts in looping flows
- **Concurrency Guard for All Starter-Capable Agents** - Starter, Ender, and all agents that spawn downstream targets now implement a mandatory blocked wait: before starting any target agents, the caller waits until ALL targets have stopped running, logging ERROR every 10 seconds while waiting. Prevents duplicate/orphaned processes in looping workflows
- **Chat History Per-User Isolation** - Added `conversation_user` foreign key to `AgentMessage` model (migration 0043), enabling per-user conversation history filtering and preventing cross-user message leakage
- **FlowHypervisor Monitoring Prompt Enhanced** - Now recognizes 42 distinct agent startup markers, 30+ error patterns, 16+ warning patterns, concurrency guard messages ("WAITING FOR AGENTS TO STOP"), reanimation asset cleanup validation, and agent categorization (short-lived vs. long-running vs. mixed-mode)
- **Stopper Refactored to Single-Threaded** - Changed from multi-threaded per-source monitoring to sequential polling of all source agents in a single main loop for more reliable pattern matching
- **Added Image-Interpreter Agent** - Non-deterministic LLM vision agent that analyzes images in 12+ formats (jpg, png, gif, bmp, tiff, webp, svg, ico, heic, avif), supports wildcards, directories, or File-Interpreter coupling, logs structured INI_IMAGE_FILE/END_FILE blocks, and triggers downstream agents
- **Added File-Interpreter Agent** - Hybrid deterministic/non-deterministic agent for document parsing with three reading modes (fast/complete/summarized), support for DOCX, PPTX, XLSX, PDF, TXT, TeX, CSV, HTML, RTF, and more file formats, optional image extraction, and LLM-powered summarization
- **Added Counter Agent** - Deterministic persistent counter with threshold-based L/G routing, overflow protection, and reanimation support
- **Added Flow Validation System** - Structural verification engine (`acp-validate.js`) that builds an NxN adjacency matrix from agent connections and validates: no inputs to Starters, Ender outputs only to Cleaner/FlowBacker, Cleaner inputs only from Ender/FlowBacker, FlowBacker inputs only from Starter/Ender/Forker/Asker, FlowBacker outputs only to Cleaner, no self-connections, all non-Starters have inputs, and all referenced agents exist with appropriate input types. Results shown with per-agent error details and suggestions
- **Added FlowHypervisor Agent** - System-managed LLM-powered anomaly detector that monitors all running agents in a flow. Features include: reanimation support via `reanim.json` for crash recovery, incremental log reading (only processes new content), NxN connection matrix analysis, `hypervisor_alert.json` generation for frontend alerts, and smart exit logic (stops after 3 consecutive cycles with no running agents)
- **Added Mouser Agent** - Mouse pointer movement agent using PyAutoGUI, supporting two modes: random (moves across screen for configurable duration) and localized (smooth easing movement from initial to final coordinates). Includes fail-safe exception handling and downstream agent triggering
- **Improved Gitter Agent Content Reporting** - Now produces structured response format: `<git {command}> RESPONSE { ... }` with stdout/stderr capture and per-line logging
- **Improved Apirer Agent Content Reporting** - Now produces structured response format: `<{url}> RESPONSE { ... }` with timing in milliseconds, body size reporting, and Authorization header masking for security
- **jd-cli Bundled in Installation** - The Java decompiler CLI tool (`jd-cli/`) is now included in `pkg.zip` during the build process, available at the application root alongside `agents/`, `application/`, etc.
- **FlowCreator Skill Enhancements** - Updated `agentic_skill.md` with Mouser agent documentation, improved validation instructions for agent connection rules, and enhanced button behavior for the Validate flow action
- **Added PyAutoGUI Dependency** - `PyAutoGUI==0.9.54` added to `requirements.txt` for Mouser agent mouse control
- **New API Endpoints** - Added `/validate_flow/` (GET) for flow structure validation, `/execute_flowhypervisor/<agent_name>/` (POST), `/check_flowhypervisor_alert/<agent_name>/` (GET), `/update_mouser_connection/<agent_name>/` (POST), `/update_counter_connection/<agent_name>/` (POST), `/update_file_interpreter_connection/<agent_name>/` (POST), `/update_image_interpreter_connection/<agent_name>/` (POST), and `/update_flowbacker_connection/<agent_name>/` (POST). That earlier expansion brought the app route total to 100 at the time; the current code now exposes 103 app routes
- **P0/P1/P2 Security Hardening** - Comprehensive, tiered security test suite covering user isolation, CSRF, login enforcement (P0), path traversal prevention and safe path joining (P1), and prompt injection defense with indirect file access detection (P2)
- **Added Path Guard Module** (`path_guard.py`) - Centralized path validation layer that resolves Windows known folders, enforces `allowed_paths` from config, and prevents directory traversal across all file operations
- **Improved File Search Chain** - `chain_files_search_lcel.py` now integrates with `path_guard.py` for secure path validation, supports non-explicit lookup crawling, and validates all gRPC results against path escaping
- **Expanded Security Tests** - `tests.py` now includes three test classes (`P0HardeningTests`, `P1HardeningTests`, `PromptPathHardeningTests`) covering critical to prompt-level hardening scenarios
- **Enhanced RAG Interface Security** - `rag/interface.py` now performs LLM-based indirect file access detection and prompt-level path validation before file operations
- **Improved Crawler Agent** - Raw content capture mode (HTML/JS/CSS/headers), resource inventory generation, developer-oriented LLM analysis preamble, and updated source LLM model configuration
- **UI Refinements** - MCP/agents dialog improved with golden-ratio styled columns for better readability
- **ESLint Configuration** - Added `eslint.config.mjs` for frontend JavaScript quality assurance
- **Added Summarizer Agent** - LLM-powered log monitoring agent that continuously polls source agent log files, sends content to an LLM with a configurable system prompt for event detection, and triggers downstream agents when positive events are found
- **Added FlowHypervisor Agent** - System-managed LLM anomaly detector that watches all running agents' processes and log files, builds a connection matrix, and alerts the user to anomalies via an interactive UI dialog
- **Added Crawler Agent** - Developer-oriented web page crawler that fetches URLs in raw mode (full HTML/JS/CSS/headers with resource inventory) or text mode, saves to local files, and processes content with a configurable LLM prompt across three crawl modes (small-range, medium-range, large-range)
- **Added Jenkinser Agent** - CI/CD pipeline trigger agent that triggers Jenkins builds with CSRF crumb and authentication support, and starts downstream agents regardless of trigger outcome
- **Added Apirer Agent** - HTTP/REST API agent that makes GET/POST/PUT/DELETE requests, logs response details, and triggers downstream agents regardless of success or failure
- **Added Pser Agent** - LLM-powered process finder that semantically matches running processes by likely name and logs detailed process info
- **Added Dockerer Agent** - Docker container and docker-compose management with automatic downstream agent triggering
- **Added Telegramer & Telegramrx Agents** - New agents for bidirectional Telegram interactions and rule-based notifications
- **Enhanced Security Guardrails** - Local file system access is now strictly limited to explicitly allowed paths in `config.json`
- **Smart Prompts Improvement** - Enhanced LLM lookup prompts for Monitor-Log and Monitor-Netstat for better accuracy
- **Interpreter Path Improvements** - Avoided hardcoded Python interpreter path execution dependencies within workflows

- **Added Forker Agent** - Deterministic A/B path router that monitors source agent logs for configurable patterns and automatically routes to Path A or Path B
- **Added Asker Agent** - Interactive A/B path chooser that pauses workflow for user decision via browser dialog, with 5-minute timeout
- **Added Pythonxer Agent** - Python script executor with Ruff linting validation, boolean exit code logic, and optional forked window execution
- **Added Stopper Agent** - Single-threaded pattern-based agent terminator with sequential polling of all source agents, per-source reanimation offsets, and continuous execution
- **Added Recmailer Agent** - IMAP email receiver with LangGraph-based LLM analysis for keyword detection in incoming emails
- **Added Whatsapper Agent** - WhatsApp notification agent using TextMeBot API with LLM-powered log summarization
- **Added Qwen Image Analysis** - Dual-backend image analysis supporting both Claude (cloud) and Qwen/Ollama (local) vision models
- **Added Notifier Agent** - LangGraph-based event notification agent with frontend browser alerts, configurable pattern matching, reanimation offsets, and downstream agent triggering
- **Added Executer Agent** - Execute shell commands within workflows
- **Added Deleter Agent** - Delete files by pattern with event triggering
- **Added Mover Agent** - Move or copy files between locations
- **Added Sleeper Agent** - Introduce delays in workflow execution
- **Added Croner Agent** - Time-scheduled workflow triggers
- **Added Cleaner Agent** - Automated cleanup of temporary files
- **Modular Frontend** - Split `agent_page.js` into 8 focused modules (init, chat, canvas, context, dialogs, layout, state, ui)
- **Canvas Auto-Configuration** - Agent connections on the workflow designer auto-populate config.yaml files
- **Improved Session Persistence** - 24-hour session state with automatic restoration
- **Enhanced RAG Pipeline** - Better context budgeting, metadata extraction, and advanced retrieval strategies
- **Workflow Save/Load** - Export and import workflows as `.flw` files
- **Tools Dialog** - Per-tool enable/disable via the chat interface
- **Image Format Conversion** - Added `converter.py` module for image format transformations and base64 encoding
- **Chat History Management** - Added `chat_history_loader.py` for persistent conversation history
- **103 HTTP Endpoints** - Comprehensive REST API for agent management, connection updates, session control

---

*For support or questions, please open an issue on GitHub.*
