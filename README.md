# Tlamatini

![Project Logo](Tlamatini.jpg)

A sophisticated, locally-run AI developer assistant featuring an advanced Retrieval-Augmented Generation (RAG) system, real-time web interface, visual agentic workflow designer, and multi-model LLM support.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
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
  - [Internet Search Settings](#internet-search-settings)
  - [MCP Services](#mcp-services)
  - [Advanced Options](#advanced-options)
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
- [Workflow Examples](#workflow-examples)
- [API Reference](#api-reference)
  - [WebSocket Protocol](#websocket-protocol)
  - [HTTP Endpoints](#http-endpoints)
- [Session Management](#session-management)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)
- [Glossary](#glossary)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**Tlamatini** is a powerful, locally-deployed AI assistant built with Django that provides a real-time, web-based interface for interacting with Large Language Models (LLMs). Designed as a comprehensive developer assistant, it excels at answering questions, generating code, analyzing codebases, and performing complex tasks with full awareness of your local files and project context.

The system leverages a highly advanced, custom-built **Retrieval-Augmented Generation (RAG)** pipeline that goes far beyond simple text retrieval. It performs detailed source code analysis including metadata extraction, architectural role classification, dependency mapping, and intelligent context budgeting to provide deeply context-aware responses.

Additionally, Tlamatini features a **Visual Agentic Workflow Designer** that allows you to create automated workflows using drag-and-drop agents. These workflows can monitor logs, execute commands, send notifications via email, WhatsApp, and Telegram, execute SQL/MongoDB scripts, SSH into remote hosts, route decisions through conditional logic, and much more — all orchestrated through an intuitive visual interface with 31 pre-built agent types.

The entire application can be packaged into a standalone executable using PyInstaller, with a user-friendly Tkinter-based GUI installer for easy deployment.

---

## Quick Start

Get Tlamatini running in 5 minutes:

### 1. Clone and Setup

```bash
git clone https://github.com/your-repo/Tlamatini.git
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

## Key Features

### Real-Time Chat Interface
- WebSocket-based communication via Django Channels for instant responses
- Syntax-highlighted code rendering with line numbers
- Canvas area for viewing, editing, and copying generated code
- Session persistence across browser reconnections (24-hour expiry)
- Generation cancellation support
- Modular frontend architecture (8 JS modules for maintainability)

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
- 31 pre-built agent types for diverse automation tasks
- Logic gates (AND/OR) for complex flow control
- Conditional routing agents (Forker, Asker) for branching workflows
- Real-time LED status indicators (red/green/yellow)
- Undo/Redo support (1024 actions)
- Workflow save/load as `.flw` files
- Canvas auto-configuration of agent connections

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
| **AI/ML** | LangChain 0.3.27, LangGraph 0.2.74, Ollama (ollama 0.5.3), FAISS, rank-bm25, NumPy 2.3.4 |
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
│   │   ├── views.py                # HTTP request handlers (60+ endpoints)
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
│   │   ├── chat_history_loader.py  # Chat history management
│   │   ├── chain_system_lcel.py    # System metrics chain
│   │   ├── chain_files_search_lcel.py # File search chain
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
│   │   ├── agents/                 # Workflow agent templates (31 types)
│   │   │   ├── starter/           # Flow initiator
│   │   │   ├── ender/             # Flow terminator (+ output_agents for Cleaners)
│   │   │   ├── stopper/           # Pattern-based agent terminator
│   │   │   ├── cleaner/           # Post-termination cleanup agent
│   │   │   ├── raiser/            # Event-driven launcher (log pattern → start agents)
│   │   │   ├── executer/          # Shell command executor
│   │   │   ├── pythonxer/         # Python script executor with Ruff validation
│   │   │   ├── sqler/             # SQL Server query execution agent
│   │   │   ├── mongoxer/          # MongoDB script execution agent
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
│   │   │   ├── asker/             # Interactive A/B path chooser (user dialog)
│   │   │   ├── forker/            # Automatic A/B path router (pattern-based)
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
│   │       ├── css/               # Stylesheets
│   │       │   ├── agent_page.css
│   │       │   ├── agentic_control_panel.css
│   │       │   ├── login.css
│   │       │   ├── tools_dialog.css
│   │       │   └── welcome.css
│   │       └── js/                # JavaScript modules
│   │           ├── agent_page_init.js     # App initialization & WebSocket setup
│   │           ├── agent_page_chat.js     # Chat message handling
│   │           ├── agent_page_canvas.js   # Code canvas rendering
│   │           ├── agent_page_context.js  # RAG context management
│   │           ├── agent_page_dialogs.js  # Modal dialogs
│   │           ├── agent_page_layout.js   # UI layout management
│   │           ├── agent_page_state.js    # Client-side state
│   │           ├── agent_page_ui.js       # General UI utilities
│   │           ├── agentic_control_panel.js # Flow designer
│   │           ├── canvas_item_dialog.js  # Agent config dialog on canvas
│   │           ├── contextual_menus.js    # Right-click menus
│   │           └── tools_dialog.js        # Tool enable/disable dialog
│   │
│   └── staticfiles/                # Collected static files (WhiteNoise)
│
├── build.py                         # PyInstaller build script
├── install.py                       # Tkinter GUI installer
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
   git clone https://github.com/your-repo/Tlamatini.git
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
5. Runs database migrations
6. Creates a default superuser
7. Renames the executable to `Tlamatini.exe`
8. Copies agent templates
9. Bundles support scripts into `dist/manage/`:
   - `register_flw.ps1` / `unregister_flw.ps1` — `.flw` file association
   - `CreateShortcut.ps1` / `RemoveShortcut.ps1` — desktop & local shortcuts
   - `Tlamatini.ps1` — PowerShell launcher
   - `CreateShortcut.json`, `Tlamatini.ico`
10. Generates **`pkg.zip`** from the `dist/manage/` directory

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
- Real-time LED status indicators (red/green/yellow)
- Log viewer for debugging
- Save/Load workflows as `.flw` files
- Undo/Redo with 1024 action history
- Agent restart and process management
- Session-scoped pool directories
- Canvas auto-configuration (connections auto-populate agent configs)

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
| **AgentMessage** | Chat messages between users and LLM | `user` (FK->User), `message`, `timestamp` |
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

Pre-built agents for the visual workflow designer, organized by category. **30 agent types** total.

### Agent Architecture

All workflow agents follow a common structural pattern:

1. **Config loading**: Read `config.yaml` from the agent's pool directory
2. **PID management**: Write `agent.pid` for process tracking; remove on exit
3. **Logging**: `FlushingFileHandler` writes to `<agent_name>.log` with immediate flush for real-time visibility
4. **Reanimation**: `.pos` files store file offsets to survive restarts without re-reading old data
5. **Pool navigation**: Agents resolve sibling agent directories relative to their pool root (supports both frozen/PyInstaller and development modes)
6. **Subprocess spawning**: Target agents are started as new processes using the resolved Python command
7. **Cardinal naming**: Deployed agents get numeric suffixes (e.g., `monitor_log_1`, `emailer_2`)

Agents are classified as:
- **Deterministic** (no LLM): `starter`, `ender`, `stopper`, `cleaner`, `executer`, `pythonxer`, `sqler`, `mongoxer`, `sleeper`, `deleter`, `mover`, `shoter`, `raiser`, `croner`, `asker`, `forker`, `ssher`, `scper`, `telegramer`, `telegramrx`, `and`, `or`
- **LLM-powered**: `monitor_log` (LLM-based log analysis), `monitor_netstat` (port monitoring), `notifier` (LangGraph state machine), `emailer` (SMTP), `recmailer` (IMAP + LLM), `whatsapper` (TextMeBot + LLM), `prompter` (Ollama prompting), `flowcreator` (AI flow design)

### Control Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **starter** | Initiates workflow execution | `target_agents`: List of agents to start<br>`exit_after_start`: Boolean |
| **ender** | Terminates all connected agents, then launches Cleaners | `source_agents`: Agents to TERMINATE<br>`output_agents`: Agents to LAUNCH after termination (typically Cleaners). Also auto-discovers Cleaners in pool. |
| **stopper** | Multi-threaded pattern-based agent terminator. Monitors source agent logs and kills agents when patterns are detected. One thread per source agent. Does NOT start downstream agents. | `source_agents`: Agents to monitor and terminate<br>`patterns`: One pattern per source agent<br>`poll_interval`: Check frequency<br>`output_agents`: Canvas wiring only (not used for starting agents) |

### Monitoring Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **monitor_log** | LLM-based log file monitoring | `logfile_path`: Log to watch<br>`keywords`: ERROR, FATAL, WARN, etc.<br>`outcome_word`: TARGET_FOUND<br>`poll_interval`: Check frequency |
| **monitor_netstat** | Network connection monitoring | Similar to monitor_log |

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

### Action Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **executer** | Execute shell commands | `command`: Shell command string<br>`target_agents`: Downstream agents |
| **pythonxer** | Execute Python scripts with Ruff linting validation. Triggers downstream agents only if script exits with code 0 (True). Supports forked window execution for real-time stdout visibility. | `script`: Python source code to execute<br>`execute_forked_window`: Run in new console (boolean)<br>`target_agents`: Agents triggered on success |
| **sqler** | Execute database operations on MS SQL Server instances using `pyodbc`. Injects `cursor` and `conn` globals directly into an inner Python scope. Triggers downstream agents on success. | `sql_connection` map: `driver`, `server`, `database`, `username`, `password` credentials<br>`script`: Python script wrapping SQL execution<br>`target_agents`: Success agents |
| **deleter** | Delete files by pattern | `files_to_delete`: List of patterns (supports wildcards)<br>`trigger_mode`: immediate / event<br>`source_agents`: For event mode |
| **mover** | Move or copy files | `operation`: move / copy<br>`sources_list`: File patterns<br>`destination_folder`: Target directory |
| **shoter** | Takes screenshots and saves to output directory | `output_dir`: Screenshot destination<br>`target_agents`: Downstream agents |
| **ssher** | SSH remote command execution. Requires pre-configured SSH keys. | `user`: SSH username<br>`ip`: Remote host<br>`script`: Command to execute<br>`target_agents`: Triggered on success |
| **scper** | SCP file transfer to/from remote host | `user`: SSH username<br>`ip`: Remote host<br>`file`: Path to transfer<br>`direction`: send / receive<br>`target_agents`: Triggered on success |
| **mongoxer** | Execute Python scripts against MongoDB using pre-connected `db` object | `mongo_connection`: Connection config map<br>`script`: Python script using `db`<br>`target_agents`: Success agents |
| **prompter** | Sends configured prompt to Ollama LLM and logs response | `prompt`: Prompt text<br>`llm.host`: Ollama URL<br>`llm.model`: Model name<br>`target_agents`: Downstream agents |

### Logic Gates

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **and** | AND logic gate (latched) | `source_1`, `source_2`: Source agents<br>`pattern_1`, `pattern_2`: Patterns to detect<br>`target_agents`: Trigger if BOTH found |
| **or** | OR logic gate | `source_1`, `source_2`: Source agents<br>`target_agents`: Trigger if ANY found |

### Routing Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **asker** | Interactive A/B path chooser. Writes `ASKER_CHOICE_NEEDED` to its log, which the frontend detects and shows a dialog. The user picks Path A or Path B, and the corresponding agents are triggered. 5-minute timeout. | `target_agents_a`: Agents for Path A<br>`target_agents_b`: Agents for Path B<br>`source_agents`: Upstream agents |
| **forker** | Automatic A/B path router. Continuously monitors source agent logs for two sets of patterns and automatically routes to Path A or Path B when detected. Supports reanimation offsets. | `pattern_a`: Patterns for Path A (comma-separated)<br>`pattern_b`: Patterns for Path B (comma-separated)<br>`target_agents_a`: Path A agents<br>`target_agents_b`: Path B agents<br>`source_agents`: Agents to monitor<br>`poll_interval`: Check frequency |

### Utility Agents

| Agent | Purpose | Key Configuration |
|-------|---------|-------------------|
| **raiser** | Event-driven launcher. Primary bridge between monitoring agents and action agents. | `source_agents`: Agents whose logs to monitor<br>`pattern`: Text to detect<br>`target_agents`: Agents to start on detection<br>`poll_interval`: Check frequency |
| **sleeper** | Delay execution | `duration_ms`: Wait time in milliseconds<br>`target_agents`: Trigger after delay |
| **croner** | Time-scheduled trigger | `trigger_time`: HH:MM format<br>`target_agents`: Agents to trigger<br>`poll_interval`: Check frequency |
| **cleaner** | Post-termination cleanup. Deletes .log and .pid files for specified agents, then launches agents in `output_agents`. Only accepts input from Ender (auto-discovered). | `agents_to_clean`: Agent pool names to clean<br>`output_agents`: Agents to start after cleanup |
| **flowcreator** | LLM-powered AI flow designer. Reads `agentic_skill.md` and generates complete flow configurations from natural language descriptions. | `llm.base_url`: Ollama URL<br>`llm.model`: Model for flow design |

Each agent has a `config.yaml` file for customization.

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

Pause workflow for user decision.

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
| `/update_sleeper_connection/<agent_name>/` | POST | Update sleeper connections |
| `/update_cleaner_connection/<agent_name>/` | POST | Update cleaner connections |
| `/update_deleter_connection/<agent_name>/` | POST | Update deleter connections |
| `/update_asker_connection/<agent_name>/` | POST | Update asker A/B connections |
| `/update_forker_connection/<agent_name>/` | POST | Update forker A/B connections |

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

## Security Considerations

### Authentication

- Django user authentication required for all pages
- WebSocket connections authenticated via Django Channels middleware
- Session-based multi-user isolation

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
- Strict guardrails enforce local access routes/paths, restricting operations to explicitly configured safe directories in `config.json`
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
| **Stopper** | Multi-threaded agent that monitors and terminates other agents based on patterns. Uses `output_agents` (not `target_agents`) for canvas wiring |
| **Pythonxer** | Agent that executes Python scripts with Ruff validation and boolean exit code |
| **Recmailer** | LangGraph agent that monitors IMAP email inbox with LLM-based keyword analysis |
| **Whatsapper** | Agent that sends WhatsApp notifications via TextMeBot API with LLM summarization |
| **Forker** | Deterministic agent that routes workflows to Path A or B based on log patterns |
| **Asker** | Deterministic agent that pauses workflow for interactive user A/B choice |
| **Workflow** | Connected sequence of agents performing automated tasks |
| **Canvas** | UI area for displaying and editing generated code |
| **Session State** | Persisted user context and preferences |
| **Pool** | Directory where deployed agent instances are stored |
| **output_agents** | Config field used by Ender, Stopper, and Cleaner for downstream canvas wiring. Ender uses `source_agents` for its termination list, while most other agents use `target_agents` for starting downstream agents |
| **FlowCreator** | AI-powered agent that generates complete flow configurations from natural language using an LLM and the `agentic_skill.md` schema |
| **Cardinal** | Numeric suffix added to deployed agents (e.g., `_1`, `_2`) to support multiple instances |
| **Reanimation Offset** | Saved position in log file to handle restarts and log rotation |
| **TextMeBot** | Third-party API service for sending WhatsApp messages programmatically |
| **Ruff** | Fast Python linter used by Pythonxer for script validation |

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

---

## Changelog

### Recent Updates

- **Added Telegramer & Telegramrx Agents** - New agents for bidirectional Telegram interactions and rule-based notifications
- **Enhanced Security Guardrails** - Local file system access is now strictly limited manually configured, explicitly allowed paths in `config.json`
- **Smart Prompts Improvement** - Enhanced LLM lookup prompts for Monitor-Log and Monitor-Netstat for better accuracy
- **Interpreter Path Improvements** - Avoided hardcoded Python interpreter path execution dependencies within workflows

- **Added Forker Agent** - Deterministic A/B path router that monitors source agent logs for configurable patterns and automatically routes to Path A or Path B
- **Added Asker Agent** - Interactive A/B path chooser that pauses workflow for user decision via browser dialog, with 5-minute timeout
- **Added Pythonxer Agent** - Python script executor with Ruff linting validation, boolean exit code logic, and optional forked window execution
- **Added Stopper Agent** - Multi-threaded pattern-based agent terminator with per-source monitoring threads and continuous execution
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
- **60+ HTTP Endpoints** - Comprehensive REST API for agent management, connection updates, session control

---

*For support or questions, please open an issue on GitHub.*