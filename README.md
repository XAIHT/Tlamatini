# Tlamatini

![Project Logo](Tlamatini.jpg)

A sophisticated, locally-run AI developer assistant featuring an advanced Retrieval-Augmented Generation (RAG) system, real-time web interface, visual agentic workflow designer, and multi-model LLM support.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Default Login Credentials](#default-login-credentials)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Manual Setup from Source](#manual-setup-from-source)
  - [Using the GUI Installer](#using-the-gui-installer)
- [Configuration](#configuration)
  - [LLM Settings](#llm-settings)
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
  - [RAG Chain Types](#rag-chain-types)
  - [Unified Agent with Tools](#unified-agent-with-tools)
  - [Agentic Workflow Designer](#agentic-workflow-designer)
    - [Pause, Stop, and Reanimation of a Flow](#pause-stop-and-reanimation-of-a-flow)
    - [Flow Validation](#flow-validation)
  - [Database Models](#database-models)
  - [Design Patterns](#design-patterns)
  - [MCP Integration](#mcp-integration)
  - [Claude API Client](#claude-api-client)
  - [Image Analysis](#image-analysis)
- [Available Tools](#available-tools)
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
  - [Supported Source Agents and Their Output Fields](#supported-source-agents-and-their-output-fields)
  - [Iterative Execution Model](#iterative-execution-model)
  - [The Visual Mapping Dialog](#the-visual-mapping-dialog)
  - [Practical Examples](#practical-examples)
  - [Design Constraints](#design-constraints)
- [Custom Agent Development](#custom-agent-development)
  - [Using the `create_new_agent` Skill](#using-the-create_new_agent-skill)
    - [In Antigravity IDE / Gemini CLI](#in-antigravity-ide--gemini-cli)
    - [In Claude CLI (claude-code) / Cursor](#in-claude-cli-claude-code--cursor)
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
    - [WebSocket Disconnections](#websocket-disconnections)
    - [Agent Not Starting](#agent-not-starting)
    - [Memory Issues](#memory-issues)
    - [Image Analysis Fails](#image-analysis-fails)
    - [Forker/Asker Not Routing](#forkerasker-not-routing)
  - [Debug Mode](#debug-mode)
  - [Log Locations](#log-locations)
- [Glossary](#glossary)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Tlamatini** is a powerful, locally-deployed AI assistant built with Django that provides a real-time, web-based interface for interacting with Large Language Models (LLMs). Designed as a comprehensive developer assistant, it excels at answering questions, generating code, analyzing codebases, and performing complex tasks with full awareness of your local files and project context.

The system leverages a highly advanced, custom-built **Retrieval-Augmented Generation (RAG)** pipeline that goes far beyond simple text retrieval. It performs detailed source code analysis including metadata extraction, architectural role classification, dependency mapping, and intelligent context budgeting to provide deeply context-aware responses.

Additionally, Tlamatini features a **Visual Agentic Workflow Designer** that allows you to create automated workflows using drag-and-drop agents. These workflows can monitor logs, execute commands, send notifications via email, WhatsApp, and Telegram, execute SQL/MongoDB scripts, SSH into remote hosts, route decisions through conditional logic, and much more — all orchestrated through an intuitive visual interface with 53 pre-built agent types.

The entire application can be packaged into a standalone executable using PyInstaller, with a user-friendly Tkinter-based GUI installer for easy deployment.

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

pip install -r requirements.txt
```

### 2. Configure LLM Backend

Ensure [Ollama](https://ollama.ai/) is installed and running, then pull the required models:

```bash
ollama pull bge-m3:latest         # Embedding model
ollama pull llama3.1:8b           # Chat model (or your preferred model)
```

### 3. Initialize Database

```bash
cd Tlamatini
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

### 4. Run the Application

```bash
python manage.py runserver --noreload
```

### 5. Access the Interface

1. Open `http://127.0.0.1:8000/` in your browser
2. Log in with your superuser credentials
3. Navigate to `/agent/` for the chat interface
4. (Optional) Set a context folder to enable code-aware responses

**First Steps:**
- Click "Set Context" and select a project directory
- Ask questions about your code: "How does the authentication work?"
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
- Modular frontend architecture (23 JS modules: 8 chat interface + 11 ACP workflow designer + 4 shared)

### Advanced RAG System
- **Dynamic Context Loading**: Set local files or entire directories as context directly from the web interface
- **Code-Aware Analysis**: Parses source code to extract classes, functions, imports, and dependencies
- **Architectural Classification**: Identifies file roles (controller, data_model, service_layer, etc.)
- **Hybrid Retrieval**: Combines FAISS vector search with BM25 keyword matching via Reciprocal Rank Fusion
- **Intelligent Context Budgeting**: Prioritizes and selects the most relevant document chunks within token limits
- **Metadata Enrichment**: Tracks cross-file references and dependency graphs

### Unified Agent with Tool Calling
- Execute Python scripts and shell commands
- Image analysis with dual vision backends (Claude Opus and Qwen/Ollama)
- Java decompilation (JAR/WAR files)
- ZIP file extraction
- Agent lifecycle management (start/stop/status)
- Per-tool enable/disable via global state

### Visual Workflow Designer
- Drag-and-drop agentic workflow creation
- 53 pre-built agent types for diverse automation tasks
- Logic gates (AND/OR) for complex flow control
- Conditional routing agents (Forker, Asker) for branching workflows
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
- Only enabled when a directory is fully loaded as context
- Each entry displays the application's icon for quick recognition

### Enterprise Features
- Django-based user authentication
- Secret redaction in context (configurable)
- Session-based multi-user isolation
- Comprehensive logging and metrics
- Process management with PID tracking and cleanup

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
│ - Text splitters  │   │ - LangChain tools │   │   (WebSocket)     │
│ - FAISS + BM25    │   │ - Function calls  │   │ - File search     │
│ - Context budget  │   │                   │   │   (gRPC)          │
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

1. **User sends message** via WebSocket
2. **AgentConsumer** receives and processes the message
3. **Context determination**: Check if RAG context is loaded
4. **Internet check**: Classify if web search is needed
5. **Chain selection**: Choose appropriate chain (RAG, Basic, or Unified Agent)
6. **LLM invocation**: Send to configured backend with context
7. **Streaming response**: Return chunks via WebSocket
8. **Tool execution**: If tools requested, execute and continue

---

## Technology Stack

| Category | Technologies |
|----------|--------------|
| **Backend** | Python 3.12+, Django 5.2.4, Django Channels 4.1, Daphne (ASGI) |
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
│   │   ├── views.py                # HTTP request handlers (100 endpoints)
│   │   ├── consumers.py            # WebSocket consumer (async chat handler)
│   │   ├── models.py               # Database models (12 models)
│   │   ├── urls.py                 # URL routing definitions
│   │   ├── routing.py              # WebSocket URL patterns
│   │   ├── config.json             # LLM and RAG configuration
│   │   ├── prompt.pmt              # System prompt template
│   │   ├── global_state.py         # Thread-safe singleton state (Singleton pattern)
│   │   ├── constants.py            # Application constants and regex patterns
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
│   │   ├── mcp_agent.py            # MCP unified agent builder
│   │   ├── tools.py                # LangChain tool definitions (12 tools)
│   │   ├── web_search_llm.py       # Internet search integration
│   │   ├── inet_determiner.py      # Search requirement classifier
│   │   │
│   │   ├── path_guard.py           # Centralized path validation and traversal prevention
│   │   ├── tests.py                # Security hardening test suite (P0/P1/P2)
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
│   │   ├── agents/                 # Workflow agent templates (53 types)
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
│   │   │   ├── kyber_keygen/   # CRYSTALS-Kyber key pair generation agent
│   │   │   ├── kyber_cipher/  # CRYSTALS-Kyber encryption agent
│   │   │   ├── kyber_decipher/ # CRYSTALS-Kyber decryption agent
│   │   │   ├── parametrizer/  # Utility interconnection agent (maps outputs to inputs)
│   │   │   ├── flowbacker/    # Session backup and cleanup handoff agent
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

- **Python 3.12+**
- **Ollama** installed and running (for local LLM inference)
- Required LLM models pulled in Ollama:
  - Embedding model (e.g., `bge-m3:latest`)
  - Chat model (e.g., `llama3.1:8b` or any preferred model)
  - (Optional) Vision model for image analysis (e.g., `qwen3.5:cloud`)

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
     "embeding-model": "bge-m3:latest",
     "chained-model": "your-preferred-model",
     "ollama_base_url": "http://127.0.0.1:11434"
   }
   ```

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

### LLM Settings

```json
{
  "embeding-model": "bge-m3:latest",
  "chained-model": "deepseek-v3.1:671b-cloud",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_token": "",
  "ANTHROPIC_API_KEY": "",
  "enable_unified_agent": true,
  "unified_agent_model": "deepseek-v3.1:671b-cloud",
  "unified_agent_base_url": "http://127.0.0.1:11434",
  "unified_agent_temperature": 0.0
}
```

| Key | Description |
|-----|-------------|
| `embeding-model` | Ollama model for text embeddings |
| `chained-model` | Primary chat model |
| `ollama_base_url` | Ollama server URL |
| `ollama_token` | Bearer token for authenticated Ollama instances (optional) |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude image analysis |
| `enable_unified_agent` | Enable tool-calling agent |
| `unified_agent_model` | Model for the unified agent |
| `unified_agent_base_url` | Base URL for the unified agent's LLM |
| `unified_agent_temperature` | Temperature for agent responses (0.0 = deterministic) |

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
2. **App ready hook** (`agent/apps.py`) - Cleans pools directory, clears `AgentProcess` records, registers signal handlers
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
5. Copies the `jd-cli/` directory (Java decompiler) into the distribution
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
result = agent.invoke({"input": "Run the tests and show me the results"})
```

### Agentic Workflow Designer

Access via `/agentic_control_panel/` URL. Features:
- Drag-and-drop agent placement from sidebar
- Visual connection drawing between agents
- Start/Stop/Pause controls
- **Pause/Resume**: Pause stores the session's running agents in `paused_agents.reanim`, kills the active processes without clearing logs or `.pos` reanimation files, and moves the ACP into the paused state. Resume reanimates the stored agents with `AGENT_REANIMATED=1` so they preserve logs and reload their `reanim*` state files
- Real-time LED status indicators: green (running), red (not running while the flow is active), yellow blinking (paused), gray (stopped/idle)
- Log viewer for debugging
- Save/Load workflows as `.flw` files
- Undo/Redo with 1024 action history
- Agent restart and process management
- Session-scoped pool directories
- Canvas auto-configuration (connections auto-populate agent configs)
- Flow validation with detailed error reporting

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

Before executing a workflow, the Validate button performs a comprehensive 6-point structural verification by building an NxN adjacency matrix from all agent connections and checking:

| Check | Rule | Example Violation |
|-------|------|-------------------|
| **V1** | Starter agents have no incoming connections | Another agent targeting a Starter |
| **V2** | Ender agents only connect to Cleaner agents | Ender targeting an Executer |
| **V3** | Cleaner agents only receive input from Ender agents | Cleaner connected to a Monitor |
| **V4** | No self-connections (diagonal must be zero) | Agent targeting itself |
| **V5** | All non-Starter agents have at least one input | Orphaned agent with no upstream |
| **V6** | Referenced agents exist and accept input connections | Dangling reference or targeting a Starter |

The validation endpoint (`/validate_flow/`) lists all deployed agents in the session pool, loads their configurations, builds the connection matrix, and runs all six checks. Results are displayed in a dialog with per-agent error details and suggestions.

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

The application uses Django ORM with SQLite and defines the following models in `agent/models.py`:

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

| Tool | Description | Example Usage |
|------|-------------|---------------|
| `get_current_time` | Returns current datetime | "What time is it?" |
| `execute_file` | Runs Python scripts in new terminal | "Run the test script at /path/script.py" |
| `execute_command` | Executes shell commands | "List files in the current directory" |
| `execute_netstat` | Network diagnostics | "Show network connections" |
| `execute_agent` | Starts a workflow agent | "Start the monitor_log agent" |
| `stop_agent` | Stops a running agent | "Stop the emailer agent" |
| `agent_status` | Checks agent status | "Is the monitor running?" |
| `launch_view_image` | Opens images in viewer | "Show me the screenshot" |
| `unzip_file` | Extracts ZIP archives | "Extract archive.zip to /output" |
| `decompile_java` | Decompiles JAR/WAR files | "Decompile the application.jar" |
| `opus_analyze_image` | Image analysis with Claude | "Describe with Opus the image photo.jpg" |
| `qwen_analyze_image` | Image analysis with Qwen/Ollama | "Describe the image diagram.png" |

---

## Workflow Agents

Pre-built agents for the visual workflow designer, organized by category. **53 agent types** total.

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
- **Deterministic** (no LLM): `starter`, `ender`, `stopper`, `cleaner`, `executer`, `pythonxer`, `sqler`, `mongoxer`, `sleeper`, `deleter`, `mover`, `shoter`, `mouser`, `raiser`, `croner`, `asker`, `forker`, `counter`, `ssher`, `scper`, `gitter`, `dockerer`, `telegramer`, `telegramrx`, `and`, `or`, `kuberneter`, `apirer`, `jenkinser`, `gatewayer`, `gateway_relayer`, `node_manager`, `file_creator`, `file_extractor`, `flowbacker`, `kyber_keygen`, `kyber_cipher`, `kyber_decipher`, `parametrizer`
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
| **mouser** | Moves the mouse pointer randomly for a duration or to a specific screen position. Starts downstream agents after completion | `movement_type`: "random"/"localized"<br>`actual_position`: true<br>`ini_posx`/`ini_posy`: Start coords<br>`end_posx`/`end_posy`: End coords<br>`total_time`: Duration (seconds)<br>`target_agents`: Downstream agents |
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
| **parametrizer** | Short-running active utility interconnection agent that maps structured outputs from a source agent's log to a target agent's config.yaml via an interconnection-scheme.csv. When multiple output elements exist, iterates sequentially: fill config, start target, wait, repeat. Only connects to agents with structured output (Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher). | `source_agent`: Source agent name<br>`target_agent`: Target agent name<br>`source_agents`: [] (max 1)<br>`target_agents`: [] (max 1) |

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

Parametrizer is the **glue between agents** — a short-running utility agent that reads the structured output of one agent and writes it into the configuration of another, enabling fully automated data pipelines where no human touches a `config.yaml` between stages.

In most workflow systems, data hand-off between stages is either hardcoded or requires a scripting layer. Parametrizer eliminates that: you visually draw lines from output fields to config parameters, and at runtime the agent handles everything — parsing, mapping, writing, launching, waiting, and iterating.

### Why Parametrizer Exists

Tlamatini agents communicate through **log files** (structured output) and **config.yaml files** (input parameters). This is deliberate — each agent is a self-contained process with no shared memory, no message bus, and no coupling. But this design creates a gap: how does the response body from an API call (Apirer) become the `buffer` parameter for encryption (Kyber-Cipher)? How do Kyber-KeyGen's generated keys flow into Kyber-Cipher's `public_key` field?

Before Parametrizer, the answer was: manually edit `config.yaml` between runs, or write a custom agent. Parametrizer turns this into a **zero-code, visual wiring operation** that works with any combination of the 13 agents that produce structured output.

### How It Works

Parametrizer operates in five phases:

```
┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌─────────────┐    ┌──────────┐
│  1. VALIDATE │───▶│ 2. LOAD SCHEME   │───▶│ 3. PARSE SOURCE  │───▶│ 4. MAP & WRITE│───▶│ 5. LAUNCH │
│  connections │    │  (CSV mappings)  │    │  (read log, run  │    │  (fill target │    │  (start   │
│  & agent type│    │                  │    │   parser)        │    │   config.yaml)│    │   target) │
└─────────────┘    └──────────────────┘    └──────────────────┘    └─────────────┘    └──────────┘
```

**Phase 1 — Validate.** Confirms exactly one source and one target are connected, and that the source is one of the 13 recognized structured-output agents.

**Phase 2 — Load Scheme.** Reads `interconnection-scheme.csv` from its own directory. This CSV is the single source of truth for which output fields map to which config parameters.

**Phase 3 — Parse Source.** Reads the source agent's log file and runs the appropriate parser from the `OUTPUT_PARSERS` registry. Each of the 13 supported source agents has a dedicated regex-based parser that extracts structured blocks into dictionaries.

**Phase 4 — Map & Write.** For each extracted output block, applies the CSV mappings: looks up each `source_field` in the parsed dictionary and writes the value into the corresponding `target_param` in the target agent's `config.yaml`.

**Phase 5 — Launch.** Starts the target agent via subprocess and writes its PID file, exactly as Starter or Raiser would.

### The Interconnection Scheme

The mapping between source output fields and target config parameters is stored in a simple CSV file:

```csv
source_field,target_param
response_body,buffer
url,api_endpoint
public_key,public_key
```

Each row is one wire: "take `source_field` from the parsed output and write it into `target_param` in the target's config.yaml." This file is created and managed through the visual mapping dialog on the canvas, but can also be edited by hand.

The CSV lives inside the Parametrizer agent's own directory (`agents/parametrizer/interconnection-scheme.csv`) and is versioned with the flow when saved.

### Supported Source Agents and Their Output Fields

Parametrizer includes dedicated parsers for 13 agent types. Each parser understands the agent's unique log format and extracts named fields:

| Source Agent | Log Pattern | Extracted Fields |
|---|---|---|
| **Apirer** | `<url> RESPONSE {\n...\n}` | `url`, `response_body` |
| **Gitter** | `<git command> RESPONSE {\n...\n}` | `git_command`, `response_body` |
| **Kuberneter** | `KUBECTL EXECUTION PARAMETERS: ..., STATUS: code {\n...\n}` | `parameters`, `status`, `response_body` |
| **Crawler** | `INI_RESPONSE_<LABEL><<<\n...\n>>>END_RESPONSE_<LABEL>` | `label`, `response_body` |
| **Summarizer** | `INI_RESPONSE_SUMMARIZER<<<\n...\n>>>END_RESPONSE_SUMMARIZER` | `response_body` |
| **File-Interpreter** | `INI_FILE: [path] (mode)\n...\nEND_FILE` | `file_path`, `mode`, `response_body` |
| **Image-Interpreter** | `INI_IMAGE_FILE: [path]\n...\nEND_FILE` | `file_path`, `response_body` |
| **File-Extractor** | `INI_FILE: [path] (extracted)\n...\nEND_FILE` | `file_path`, `response_body` |
| **Prompter** | `INI_RESPONSE<<<\n...\n>>>END_RESPONSE` | `response_body` |
| **FlowCreator** | `INI_RESPONSE\n...\n>>>END_RESPONSE` | `response_body` |
| **Kyber-KeyGen** | `KYBER PUBLIC KEY {\n...\n}` + `KYBER PRIVATE KEY {\n...\n}` | `public_key`, `private_key` |
| **Kyber-Cipher** | `KYBER GENERATED ENCAPSULATION/INIT VECTOR/CIPHER TEXT {\n...\n}` | `encapsulation`, `initialization_vector`, `cipher_text` |
| **Kyber-DeCipher** | `KYBER DECIPHERED BUFFER {\n...\n}` | `deciphered_buffer` |

### Iterative Execution Model

A critical capability of Parametrizer is its handling of **multiple structured output elements** in a single source log. This commonly happens when:

- An Apirer calls multiple API endpoints in sequence
- A Crawler scrapes several pages
- A File-Extractor processes a wildcard pattern matching many files

When the parser returns N output blocks, Parametrizer does not batch them. Instead, it **iterates sequentially**:

```
For each output block (1..N):
   1. Write mapped fields into target's config.yaml
   2. Wait for target agent to stop (if still running from previous iteration)
   3. Start target agent
   4. Wait for target agent to finish
   → Next block
```

This guarantees that each output element gets its own full execution cycle in the target agent. For example, if Apirer hit 5 endpoints and the target is Kyber-Cipher, the Parametrizer will encrypt each response body individually, producing 5 separate cipher texts — one per API response.

### The Visual Mapping Dialog

On the canvas, double-clicking or right-clicking a Parametrizer agent opens its custom mapping dialog (not the standard config editor). The dialog:

1. **Validates connections first** — if the source or target is missing, or the source type is unsupported, an error overlay appears before the dialog opens.
2. **Shows two columns** — left column lists the source agent's available output fields (cyan theme), right column lists the target agent's config.yaml parameters (orange theme).
3. **Click-to-wire** — click a source field, then click a target parameter to create a mapping. A curved SVG Bezier line (gradient from cyan to orange) visually confirms the connection.
4. **Click-to-remove** — click any existing line to remove that mapping.
5. **Save** — writes the `interconnection-scheme.csv` to the backend.

The dialog dynamically adapts to whatever source and target agents are connected — the field lists are always current with the actual agent types.

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

- **One-to-one only.** Exactly one source agent and one target agent per Parametrizer instance. For fan-out or fan-in patterns, use multiple Parametrizer instances.
- **Source must produce structured output.** Only the 13 agents listed above are valid sources. Connecting an unsupported source (e.g., Starter, Sleeper) will fail validation at both dialog-open time and runtime.
- **Target can be any agent.** The target side has no type restriction — Parametrizer writes into whatever fields exist in the target's `config.yaml`.
- **Mappings are static per run.** The CSV is read once at startup. To change mappings, stop the flow, update via the dialog, and restart.
- **Sequential, not parallel.** When iterating over multiple output blocks, the target agent runs one-at-a-time. This is by design — it prevents race conditions on the target's config file and ensures deterministic ordering.

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

---

## API Reference

### WebSocket Protocol

**Endpoint:** `ws://localhost:8000/ws/agent/`

#### Client to Server Messages

**Chat Message:**
```json
{
  "type": "chat_message",
  "message": "Your question here"
}
```

**Set Context (Directory):**
```json
{
  "type": "set_context",
  "path": "/path/to/project",
  "context_type": "directory"
}
```

**Set Context (File):**
```json
{
  "type": "set_context",
  "path": "/path/to/file.py",
  "context_type": "file",
  "filename": "file.py"
}
```

**Clear Context:**
```json
{
  "type": "clear_context"
}
```

**Cancel Generation:**
```json
{
  "type": "cancel_generation"
}
```

**Toggle Internet Search:**
```json
{
  "type": "toggle_inet",
  "enabled": true
}
```

#### Server to Client Messages

**Chat Response (Streaming):**
```json
{
  "type": "chat_log",
  "message": "Response text chunk",
  "done": false
}
```

**Code Canvas:**
```json
{
  "type": "canvas",
  "name": "program.py",
  "content": "def hello():\n    print('Hello')",
  "language": "python"
}
```

**Status Update:**
```json
{
  "type": "status",
  "message": "Processing..."
}
```

**Error:**
```json
{
  "type": "error",
  "message": "Error description"
}
```

**Session Restored:**
```json
{
  "type": "session_restored",
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
| `/validate_flow/` | GET | Run 6-point flow structure validation |

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
| `/update_kyber_keygen_connection/<agent_name>/` | POST | Update kyber_keygen connections |
| `/update_kyber_cipher_connection/<agent_name>/` | POST | Update kyber_cipher connections |
| `/update_kyber_decipher_connection/<agent_name>/` | POST | Update kyber_decipher connections |
| `/update_parametrizer_connection/<agent_name>/` | POST | Update parametrizer connections |
| `/get_parametrizer_dialog_data/<agent_name>/` | GET | Get Parametrizer mapping dialog data |
| `/save_parametrizer_scheme/<agent_name>/` | POST | Save Parametrizer interconnection scheme |

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
4. User receives `session_restored` message
5. RAG chain rebuilt with previous context

### Clearing Session

- Explicit: Use "Clear Context" button
- Automatic: After 24 hours of inactivity
- Manual: Close browser (in-memory state cleared)
- API: POST to `/cleanup_session/` or `/clear_session_state/`

---

## Open in... External Editors

Tlamatini includes an **"Open in..."** dropdown button in the navigation bar that lets you open the currently loaded context directory directly in an external editor or file manager, without leaving the application.

### Supported Applications

| Application     | Detection Method                                                                 |
|-----------------|----------------------------------------------------------------------------------|
| **File Explorer** | Always available (Windows built-in)                                            |
| **VS Code**       | Detected via the `code` command on PATH, or common Windows install locations   |
| **Antigravity**   | Detected via the `antigravity` command on PATH, or common Windows install locations |

Only applications that are actually installed on the system will appear in the dropdown. File Explorer is always shown.

### How to Use

1. **Load a directory as context** using the **Context > Set directory as context** menu entry.
2. Wait for the context to be fully loaded (the context bar at the top will display the directory path).
3. The **"Open in..."** dropdown becomes enabled in the navigation bar (between the Context and MCPs menus).
4. Click **"Open in..."** and select the desired application from the dropdown.
5. The context directory will open in a new window of the selected application.

### Behavior Details

- **Visibility:** The dropdown only appears if at least one supported application is detected on the system (File Explorer is always detected on Windows, so the dropdown is always visible).
- **Disabled state:** The dropdown is grayed out and non-interactive until a directory is successfully loaded as context. File-based contexts do not enable the dropdown.
- **During long operations:** The dropdown is automatically disabled while the LLM is processing a request or a context is being loaded, and re-enabled once the operation completes.
- **Reconnect / Clear context:** If the context is cleared or the session is reconnected, the dropdown returns to its disabled state.

### API Endpoints

The feature relies on two HTTP endpoints:

- **`GET /agent/detect_installed_apps/`** — Returns a JSON list of applications and whether each is available on the system.
- **`POST /agent/open_in_app/`** — Accepts `app_id` and `directory` fields, validates the directory, and launches the requested application with that directory.

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

Enable verbose logging in config.json:

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

### Log Locations

- Django logs: Console output
- Agent logs: `<pool_directory>/<agent_name>/<agent_name>.log`
- System logs: `Tlamatini/logs/` (if configured)

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
| **Recmailer** | LangGraph agent that monitors IMAP email inbox with LLM-based keyword analysis |
| **Whatsapper** | Agent that sends WhatsApp notifications via TextMeBot API with LLM summarization |
| **Forker** | Deterministic agent that routes workflows to Path A or B based on log patterns |
| **Gitter** | Deterministic agent that executes Git operations (clone, pull, push, commit, etc.) on local repositories |
| **Mouser** | Deterministic agent that moves the mouse pointer randomly or to a specific position, then triggers downstream agents |
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
| **Flow Validation** | Pre-execution 6-point structural verification that builds an NxN adjacency matrix from agent connections and validates topology rules (Starter inputs, Ender outputs, self-connections, orphaned agents, dangling references) |
| **jd-cli** | Java Decompiler CLI tool bundled with the application for decompiling JAR/WAR files to source code |
| **PyAutoGUI** | Python library for programmatic mouse and keyboard control, used by the Mouser agent |
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
| **Kyber-KeyGen** | Short-running infrastructure deterministic agent that generates CRYSTALS-Kyber public/private key pairs (Kyber-512/768/1024) in base64 format, logs keys, and triggers downstream agents |
| **Kyber-Cipher** | Short-running infrastructure deterministic agent that encrypts a buffer using a CRYSTALS-Kyber public key via encapsulation + AES-256-CTR, logs encapsulation/IV/ciphertext in base64, and triggers downstream agents |
| **Kyber-DeCipher** | Short-running infrastructure deterministic agent that decrypts cipher text using a CRYSTALS-Kyber private key via decapsulation + AES-256-CTR, logs deciphered buffer, and triggers downstream agents |
| **Parametrizer** | Short-running active utility interconnection agent that maps structured outputs from a source agent's log to a target agent's config.yaml via interconnection-scheme.csv, supporting iterative execution for multiple output elements |

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

- **Added Parametrizer Agent** - Short-running active utility interconnection agent that maps structured outputs from source agent logs to target agent config.yaml parameters via a visual mapping dialog and interconnection-scheme.csv. Supports iterative execution for multiple output elements, connecting agents that produce structured output (Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher) to any target agent
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
- **New API Endpoints** - Added `/validate_flow/` (GET) for flow structure validation, `/execute_flowhypervisor/<agent_name>/` (POST), `/check_flowhypervisor_alert/<agent_name>/` (GET), `/update_mouser_connection/<agent_name>/` (POST), `/update_counter_connection/<agent_name>/` (POST), `/update_file_interpreter_connection/<agent_name>/` (POST), `/update_image_interpreter_connection/<agent_name>/` (POST), and `/update_flowbacker_connection/<agent_name>/` (POST). Total endpoints now at 100
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
- **100 HTTP Endpoints** - Comprehensive REST API for agent management, connection updates, session control

---

*For support or questions, please open an issue on GitHub.*
