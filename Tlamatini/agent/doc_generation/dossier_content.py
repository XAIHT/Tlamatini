# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""The written content of the project dossier, shared by the PDF and the deck.

Every chapter is built from ``facts`` — numbers derived from the source tree at
generation time — so no count in the finished documents is typed by hand. The
prose describes behaviour documented in the repository (README, the Book,
``docs/``, ``agents_descriptions.md``, the self-knowledge file and the source).
It never reproduces a configuration value, credential or private address.

Inline marks: ``**bold**``, ```code``` and ``_italic_`` (see dossier_theme.runs).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Section:
    key: str
    kicker: str
    title: str
    lede: str
    body: list[str] = field(default_factory=list)
    points: list[tuple[str, str]] = field(default_factory=list)
    table: dict | None = None
    callout: tuple[str, str] | None = None
    visual: str | None = None
    visual_data: dict = field(default_factory=dict)
    deck: str = "cards"          # deck layout: cards | list | table | visual | none
    deck_points: list[tuple[str, str]] | None = None
    code: str | None = None


@dataclass
class Chapter:
    key: str
    numeral: str
    title: str
    tagline: str
    sections: list[Section]
    accent: str = "jade"


# ── The bestiary ────────────────────────────────────────────────────
# Families group the installed agent directories; the generator verifies that
# every installed agent appears exactly once, so a new agent cannot be missed.
AGENT_FAMILIES: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    ("Flow control", "jade", "Begin, pause, schedule and end a flow.", [
        ("starter", "The entry point of every flow; launches its targets when you press Start."),
        ("ender", "Ends a flow gracefully: kills its targets, then starts backups and cleaners."),
        ("stopper", "Watches logs for a pattern and stops exactly those source agents."),
        ("cleaner", "Post-run janitor that removes the logs and PID files of finished agents."),
        ("sleeper", "Waits a configured number of milliseconds, then starts its targets."),
        ("croner", "A daily clock trigger that starts its targets at a configured HH:MM."),
    ]),
    ("Routing and logic", "copper", "Decide where the flow goes next.", [
        ("raiser", "Fires its targets the moment a pattern appears in a watched log."),
        ("forker", "Automatic A/B router: whichever of two patterns appears first picks the path."),
        ("asker", "Asks you in the chat to choose Path A or Path B: a human in the loop."),
        ("counter", "A persistent tally that routes below, or at and above, a threshold."),
        ("and", "Two-input gate that fires once both sources have matched."),
        ("or", "Two-input gate that fires as soon as either source matches."),
        ("barrier", "N-input fan-in that releases once every configured source has arrived."),
    ]),
    ("Orchestration and intelligence", "gold", "Design, connect, supervise and reason.", [
        ("parametrizer", "Maps one agent's structured output into the next agent's configuration."),
        ("flowcreator", "Designs a complete, validated .flw workflow from a plain objective."),
        ("flowhypervisor", "A model watchdog that reads a running flow: OK or ATTENTION NEEDED."),
        ("flowbacker", "Backs up a session's logs and configurations before clean-up."),
        ("gatewayer", "Webhook and folder-drop ingress that turns outside events into triggers."),
        ("gateway_relayer", "Relays GitHub and GitLab webhooks into Gatewayer."),
        ("node_manager", "Infrastructure registry: discovers nodes, probes heartbeats and capabilities."),
        ("prompter", "Sends one prompt to a model and logs a structured answer."),
        ("summarizer", "Summarizes text once, or watches logs and fires on a detected event."),
        ("acpxer", "Runs one external coding-agent CLI turn on the canvas and captures its answer."),
        ("mcp_doctor", "Diagnoses an external MCP server on paper, before any live connection."),
    ]),
    ("Code, files and shell", "cyan", "Find, read, change and run.", [
        ("executer", "Runs a shell command, optionally in its own visible console."),
        ("pythonxer", "Runs inline Python behind a compile() and Ruff correctness gate."),
        ("editor", "Byte-exact find-and-replace in one file; refuses an ambiguous match."),
        ("grepper", "Encoding-aware regex search, plus verbatim reads of a line range."),
        ("globber", "Finds files by glob pattern, newest first."),
        ("file_creator", "Creates a file with exact content, including a base64 channel."),
        ("mover", "Moves or copies files by glob pattern."),
        ("deleter", "Deletes by glob inside a guarded working directory."),
        ("file_interpreter", "Reads DOCX, PPTX, XLSX, PDF and more, optionally summarizing them."),
        ("file_extractor", "Extracts raw text from PDF, DOCX and similar documents."),
        ("de_compresser", "Compresses or decompresses .zip, .7z, .gz and tar archives."),
        ("j_decompiler", "Decompiles JAR and WAR archives with the bundled jd-cli."),
        ("gitter", "Runs git operations and custom git commands."),
    ]),
    ("Documents", "magenta", "Compose, typeset and present.", [
        ("pdfer", "Composes PDFs from text, Markdown, HTML and images: 24 styles, 20 themes."),
        ("pptxer", "Builds editable PowerPoint decks whose text is measured, never truncated."),
        ("latexer", "Typesets LaTeX projects, with a self-healing eight-rung repair ladder."),
    ]),
    ("Web, data and APIs", "jade", "Search, browse, call and measure.", [
        ("googler", "Resilient two-tier web search with a structured Google-dork builder."),
        ("crawler", "Fetches a page raw or as text and analyzes it with a model."),
        ("playwrighter", "Drives a real browser through scripted steps: log in, fill, click, extract."),
        ("apirer", "Calls REST APIs with any method, headers, body and timeout."),
        ("sqler", "Runs Python against Microsoft SQL Server with a ready cursor."),
        ("mongoxer", "Runs Python against MongoDB with a ready database handle."),
        ("netspeed_calculator", "Measures your connection with confidence intervals and bufferbloat."),
    ]),
    ("DevOps and infrastructure", "copper", "Containers, clusters, pipelines and hosts.", [
        ("dockerer", "A Docker and docker-compose front-end."),
        ("kuberneter", "A kubectl front-end with a structured, truthful result."),
        ("jenkinser", "Triggers Jenkins jobs, handling the CSRF crumb."),
        ("ssher", "Runs a command on a remote host over SSH."),
        ("scper", "Sends or receives files over SCP."),
        ("pser", "Finds a running process from a fuzzy name with a model's help."),
    ]),
    ("Quality and security", "rose", "Review, analyze, assess and protect.", [
        ("reviewer", "Model-driven review of a git diff with an APPROVE or REQUEST_CHANGES verdict."),
        ("analyzer", "Deterministic static analysis: bandit, semgrep, ruff, eslint, gitleaks, pip-audit."),
        ("kalier", "Authorized Kali Linux tooling through MCP-Kali-Server."),
        ("discoverer", "The ProjectDiscovery recon suite on a private, self-installing Go toolchain."),
        ("nmapper", "A local, use-only nmap bridge; unprivileged connect scan by default."),
        ("kyber_keygen", "Generates CRYSTALS-Kyber post-quantum key pairs."),
        ("kyber_cipher", "Encrypts with Kyber post-quantum cryptography."),
        ("kyber_decipher", "Decrypts Kyber-protected data."),
    ]),
    ("Firmware and engines", "gold", "Real boards and live editors.", [
        ("stm32er", "STM32 firmware from Blue Pill to H7: build, flash, observe, fail-safe."),
        ("esp32er", "ESP32 firmware through PlatformIO, from a template that compiles at once."),
        ("arduiner", "Arduino firmware through arduino-cli, with cores installed automatically."),
        ("esphomer", "ESPHome smart-home devices from YAML, no C++ required."),
        ("unrealer", "Drives a live Unreal Engine 5 editor: 53 commands in nine categories."),
        ("blenderer", "Drives Blender over the official Blender MCP add-on socket."),
    ]),
    ("Desktop and capture", "cyan", "See the screen, move the pointer, type.", [
        ("mouser", "Moves and clicks in explicitly declared coordinate spaces."),
        ("keyboarder", "Types Unicode into a verified foreground window."),
        ("windower", "Focuses, tiles, resizes, lists and closes windows by title."),
        ("shoter", "Whole-desktop screenshots with published capture geometry."),
        ("camcorder", "Webcam photo or video at the camera's native resolution."),
    ]),
    ("Voice, audio and vision", "magenta", "Hear, speak, play and look.", [
        ("recorder", "Microphone capture to WAV at the device's native sample rate."),
        ("whisperer", "Speech to text that keeps listening until you stop talking."),
        ("talker", "Text to speech, always in Tlamatini's female voice."),
        ("audioplayer", "Plays audio files with volume, truncate and loop control."),
        ("videoplayer", "Plays video with its audio on a chosen display."),
        ("image_interpreter", "Two vision models in parallel, merged by a third into one report."),
        ("video_analyzer", "Rules on robot motion, transcribes audio tracks, or summarizes a video."),
    ]),
    ("Messaging and monitoring", "rose", "Reach people and watch systems.", [
        ("notifier", "Shows an in-browser notification, optionally with a sound."),
        ("emailer", "Sends email over SMTP."),
        ("recmailer", "Watches an IMAP mailbox for new messages."),
        ("telegrammer", "Telegram as the bot or as your own account."),
        ("whatsapper", "WhatsApp through Meta's Cloud API, or explicitly from your own number."),
        ("zavuerer", "SMS, WhatsApp, Telegram, email and voice through one Zavu key."),
        ("teletlamatini", "Brings the full Tlamatini chat, Multi-Turn included, into Telegram."),
        ("instant_messaging_doctor", "Diagnoses and safely repairs Telegram and WhatsApp readiness."),
        ("monitor_log", "Model-powered log monitor."),
        ("monitor_netstat", "Model-powered network-port monitor."),
    ]),
]


def validate_families(installed: list[str]) -> None:
    listed = [name for _, _, _, members in AGENT_FAMILIES for name, _ in members]
    duplicates = sorted({n for n in listed if listed.count(n) > 1})
    missing = sorted(set(installed) - set(listed))
    stale = sorted(set(listed) - set(installed))
    if duplicates or missing or stale:
        raise RuntimeError(
            f"Bestiary drift: duplicates={duplicates} missing={missing} stale={stale}")


# ── Content ─────────────────────────────────────────────────────────
def build_chapters(f: dict) -> list[Chapter]:
    """Return every chapter of the dossier, filled with source-derived facts."""
    agents = f["agents"]
    tools = f["tools"]
    wrapped = f["wrapped"]
    skills = f["skills"]
    version = f["version"]
    sections_count = len(f["catalog_sections"])
    catalog_names = ", ".join(label for _, label in f["catalog_sections"])
    peers = f["acpx_peers"]
    model_fields = f["model_fields"]
    model_groups = f["model_groups"]
    model_agents = f["model_agents"]
    groups_text = ", ".join(f"{name} {count}" for name, count in model_groups)

    identity = Chapter("identity", "I", "Who She Is",
        "A self-hosted developer assistant that reads, reasons, builds and acts, and lets you design how.",
        accent="jade", sections=[
        Section("identity", "IDENTITY", "Tlamatini, the one who knows",
            "Tlamatini is a self-hosted AI developer assistant for Windows 10 and 11: a Django application "
            "that converses, retrieves, plans, runs agents, and lets you draw whole agent workflows on a canvas.",
            body=[
                "Her name is Nahuatl. In the Nahua world a _tlamatini_ was a sage, literally “one who "
                "knows”: a keeper of the painted books who carried knowledge and taught others to see. The "
                "name is a promise about behaviour. She should know what she is doing, say what she actually "
                "did, and never pretend.",
                "Tlamatini was conceived, designed and built by **Angela López Mendoza** (`@angelahack1`), "
                "who gave her the name. Her birthday is October 29, 2025. She is female by design, including "
                "her spoken voice, which is always a female voice, and she refers to herself as _she_.",
                f"She is free, open-source software under the MIT license, published at "
                f"`github.com/XAIHT/Tlamatini`. The repository carries the application and every one of its "
                f"{agents} workflow-agent programs as plain, readable Python.",
            ],
            points=[
                ("Creator", "Angela López Mendoza · @angelahack1"),
                ("Born", "October 29, 2025"),
                ("Platform", "Windows 10 and 11 · Python 3.12.10 · Django 5.2.15"),
                ("License", "MIT: free and open source"),
            ], deck="identity"),
        Section("planes", "WHERE THINGS RUN", "Local control, cloud reasoning",
            "“Local-first” describes where control lives: the application, database, workflows, "
            "credentials, agent code and the small embedding model stay on your machine, while the demanding "
            "reasoning is done by cloud models reached through Ollama.",
            body=[
                "Three planes cooperate. The **local control plane** is the Django application with its chat, "
                "canvases, SQLite database, agent programs, permissions, files and hardware connections. "
                "**Local retrieval** builds embeddings with `nomic-embed-text` so project context is found "
                "quickly. **Cloud reasoning** — configured `:cloud` models served through Ollama — performs "
                "chat, tool calling, long context, vision and Multi-Turn planning.",
                "Because the complete experience was engineered around Ollama's cloud-model capacity, an active "
                "**Ollama Pro plan or higher** is part of the intended system requirements. This is an "
                "independent technical recommendation: Tlamatini and XAIHT are not sponsored by, affiliated "
                "with or compensated by Ollama.",
                "Whatever you send to a configured cloud model is processed by that provider. Direct Claude API "
                "use, external coding-agent CLIs and remote MCP servers are configured separately, so you "
                "decide what material leaves your machine.",
            ],
            visual="planes", deck="visual"),
        Section("pillars", "THE PILLARS", "Seven subsystems, one assistant",
            "Everything Tlamatini does rests on seven cooperating subsystems.",
            points=[
                ("Hybrid RAG", "FAISS vectors, BM25 keywords, metadata extraction, context budgeting and a "
                 "binary-content guard keep answers grounded in your real project."),
                ("Multi-Turn", f"A planner and a tool loop of up to 4,096 iterations over the full enabled "
                 f"surface of {tools} built-in tools, with self-healing model steps."),
                ("Agentic Control Panel", f"{agents} drag-and-drop agent types wired into runnable, savable "
                 f"`.flw` workflows."),
                ("Prompt Flow Panel", "New in v1.70.0: prompts, decisions and embeddings drawn as a diagram, "
                 "saved as `.fpmt`, and played against your models."),
                ("ACPX", f"{len(peers)} external coding-agent CLIs, from Claude Code to Codex and Gemini, "
                 f"spawned as children and brokered through 12 tools."),
                ("External MCPs", "A universal client for any MCP server over four transports, with up to "
                 "five servers active at once."),
                ("Skills", f"{skills} `SKILL.md` runbooks, from code review to MCP onboarding, handed to the "
                 f"model as complete procedures."),
            ], deck="cards"),
        Section("jewels", "WHAT SETS HER APART", "The jewels",
            "Coding assistants edit text files. Tlamatini does that too, then reaches into engines, boards "
            "and networks, and lets you wire all of it together visually.",
            points=[
                ("Visual workflow design", f"{agents} agent types on a canvas you connect, validate, run, "
                 "pause and save."),
                ("Unreal Engine", "Drive a live UE5 editor from chat or canvas: actors, Blueprints, levels, "
                 "assets and materials."),
                ("Blender", "Scenes, objects, materials, renders and raw bpy code over the official add-on "
                 "socket."),
                ("Real firmware", "Scaffold, build and flash STM32, ESP32, Arduino and ESPHome boards behind "
                 "fail-safe preflights."),
                ("Whole projects", "Find, read, edit and rebuild entire codebases with grounded retrieval."),
                ("Any MCP server", "One client for the MCP ecosystem: stdio, streamable HTTP, SSE and "
                 "WebSocket."),
                ("Security assessment", "Authorized Kali, ProjectDiscovery and nmap work, driven from chat."),
                ("Blue-hat defence", "An administrator-run Windows monitoring and response toolkit."),
            ], deck="cards"),
        Section("glance", "AT A GLANCE", "The numbers, derived from source",
            "Every figure below was counted from the repository while this dossier was generated.",
            body=[
                f"The built-in Multi-Turn surface is {f['core']} core tools + {wrapped} wrapped agent "
                f"launchers + {f['acpx_tools']} ACPX and Skill tools + {f['supervisors']} External-MCP "
                f"supervisors = **{tools} tools**. Healthy, active external MCP servers add their own "
                f"`ext__<server>__<tool>` tools on top.",
                f"The application ships {f['js']} JavaScript modules, {f['css']} stylesheets and "
                f"{f['templates']} page templates, {f['migrations']} database migrations and "
                f"{f['requirements']} pinned Python requirements.",
            ],
            visual="metrics", deck="metrics"),
    ])

    architecture = Chapter("architecture", "II", "How She Works",
        "From a keystroke in the browser to a verified result on disk: the layers, the loop and the verdict.",
        accent="copper", sections=[
        Section("layers", "ARCHITECTURE", "Five layers, from toggle to tool",
            "A request passes through five layers, each with one responsibility, between the browser above "
            "and the model back-ends below.",
            body=[
                "Above the layers sit the browser pages — the chat, the Agentic Control Panel and the Prompt "
                "Flow Panel — talking to Django Channels over WebSockets under the Daphne ASGI server. Below "
                "them sit the language-model back-ends: Ollama (local and cloud), Anthropic Claude and Qwen vision.",
                "A row in the database only switches a capability on or off. It never creates one: an MCP "
                "provider needs its runtime service and context chain, and a tool needs its implementation.",
            ],
            visual="layers",
            visual_data={"layers": [
                ("Persisted toggles", "Mcp, Tool, Agent and Skill rows decide what is enabled; the "
                 "Configure dialogs flip them."),
                ("Runtime MCP services", "System-Metrics (WebSocket :8765) and Files-Search (gRPC :50051) "
                 "start with the application."),
                ("Context sidecars", "Chains that decide whether system or file context is needed and "
                 "inject it into the payload."),
                ("Answer chains", "Basic, history-aware RAG and unified-agent chains compose the prompt and "
                 "produce the answer."),
                ("Unified-agent tools", f"{f['core']} core, {wrapped} wrapped agents, {f['acpx_tools']} "
                 f"ACPX/Skill and {f['supervisors']} External-MCP supervisor tools."),
            ]}, deck="visual"),
        Section("journey", "REQUEST JOURNEY", "The life of one message",
            "Eleven steps take a message from the browser to a verified, reported result.",
            visual="steps",
            visual_data={"steps": [
                ("Send", "The browser sends the text and its toolbar flags over the chat WebSocket."),
                ("Route", "AgentConsumer receives it, attributes it to the user and queues retrieval."),
                ("Context", "It decides whether RAG context is loaded and whether web search is needed."),
                ("Chain", "The RAG, Basic or Unified-Agent chain is selected."),
                ("Gate", "Multi-Turn selects planned execution; ACPX filters its twelve tools in or out."),
                ("Permission", "With Ask Execs on, a risky tool waits for Proceed or Deny."),
                ("Prefetch", "System-metrics and file-search sidecars add context when it helps."),
                ("Loop", "Tool calls run, wrapped agents launch, every model step is self-healed."),
                ("Verdict", "Each agent's own self-report decides SUCCESS or FAILED."),
                ("Answer", "The reply streams back with Exec Report tables and Create Flow."),
                ("Clean-up", "The orphan reaper sweeps console hosts left by child processes."),
            ]}, deck="visual"),
        Section("multiturn", "MULTI-TURN", "The operator loop",
            "With Multi-Turn checked, Tlamatini stops being an advisor and becomes an operator: she plans, "
            "calls tools, reads their results and continues until the task is done.",
            body=[
                "A global execution planner builds a request-scoped plan and capability hints, but the executor "
                "binds the **full enabled tool surface**: every enabled tool, wrapped agent and skill, with ACPX "
                "still filtered by its own checkbox. An earlier design bound only a narrow planner subset and "
                "could starve the loop of the one tool it needed.",
                "The loop runs up to 4,096 iterations. Identical wrapped-agent calls in one request are "
                "deduplicated, a repetition breaker nudges a model that circles, and each wrapped agent runs in "
                "its own isolated runtime folder, so templates are never modified.",
                "When at least one agent succeeded, the answer carries a **Create Flow** button. It turns exactly "
                "the successful tool calls into a canvas-loadable `.flw` workflow, normalized and secret-redacted "
                "by the backend, so a conversation can become a reusable workflow.",
            ],
            points=[
                ("Step-by-Step", "One concrete action at a time; she waits for your READY or output."),
                ("Ask Execs", "A human Proceed/Deny gate before each risky step."),
                ("Exec Report", "One table per agent family, one row per real tool call."),
                ("ACPX", "Adds the external coding-agent and Skill tools to the surface."),
            ], deck="split"),
        Section("healing", "SELF-HEALING", "Never hang, never discard, never lie",
            "Every model call inside the loop goes through a per-request self-healing invoker that switches "
            "to a genuinely different tactic each time a transient failure strikes.",
            body=[
                "Each attempt runs under a watchdog. The shipped configuration allows 900 seconds, deliberately "
                "longer than the 600-second model-client timeout, so the watchdog never abandons a call the "
                "client would still finish; the Cancel button is polled every quarter of a second, so she never "
                "blocks forever. The ladder cycles through six tactics and keeps going up to 4,096 of them. Only "
                "you, with Cancel, stop her.",
                "If the ladder is ever exhausted after agents already ran, she finishes gracefully from that real "
                "work: the Create Flow button and the Exec Report survive, and the answer says what happened.",
                "Recovery is narrated live. Status lines such as “Tactic #3 … I will NOT hang” stream "
                "into the chat as they happen, and a SELF-HEALING NOTE opens the final answer.",
            ],
            callout=("Real bugs are not hidden",
                     "Only transient failures — timeouts, resets, HTTP 429 and 5xx — trigger new "
                     "tactics. A deterministic error such as a bad schema is raised at once so it gets fixed."),
            visual="ladder",
            visual_data={"rungs": [
                ("1", "normal", "The full request again."),
                ("2", "retry", "The same tool-bound request; most blips clear here."),
                ("3", "patient retry", "Wait, then retry with extra patience."),
                ("4", "trim context", "Keep the system messages and the last twelve."),
                ("5", "minimal", "Keep the last six messages; tools stay bound."),
                ("6", "plain summary", "Last resort: summarize truthfully what was gathered."),
            ]}, deck="visual"),
        Section("verdict", "EXEC REPORT", "A verdict you can trust",
            "An exit code is one bit. An agent's own structured self-report is a typed record, and it "
            "outranks the exit code.",
            body=[
                "`agent_verdict.py` parses each agent's `INI_SECTION` block into a typed tree and runs an ordered "
                "rule table over it. There is no model call and no heuristic, so the same input always yields "
                "the same colour. The status vocabulary is closed: five disjoint sets, united as "
                "`KNOWN_STATUSES`, and a repository-wide test rejects any status token an agent invents.",
                "A read-only diagnostic that reports a problem has succeeded, because the finding is the "
                "deliverable. Degraded work, work not done and agent errors stay red. A red row therefore "
                "means that no clean requested deliverable exists, never merely that a check found something.",
            ],
            table={"columns": ["Rule", "Fires when", "Verdict"], "widths": [0.10, 0.66, 0.24], "rows": [
                ["R1", "The agent wrote no self-report", "Exit code decides"],
                ["R2", "The agent declares error or failed", "FAILED"],
                ["R3", "Work not done: refused, not_found, engine_unavailable …", "FAILED"],
                ["R3b", "Degraded: tokens_only, compiled_with_errors, operator_required …", "FAILED"],
                ["R4", "A diagnostic completed: invalid, findings, no_matches, listed …", "SUCCESS"],
                ["R5", "An explicit success or ok flag", "That flag"],
                ["R6", "A non-zero errors count", "FAILED"],
                ["R7", "Nothing decisive and a non-zero exit code", "FAILED"],
                ["R7b", "A named completion: ok, created, sent …", "SUCCESS"],
                ["R8b", "A status token outside the vocabulary", "SUCCESS, flagged"],
                ["R8", "No failure signal at all", "SUCCESS"],
            ]},
            callout=("Why R4 outranks R5 and R6",
                     "A linter that worked perfectly reports `status: invalid`, `success: False` and "
                     "`errors: 2` together. The last two describe the document, not the agent."),
            deck="table"),
        Section("askexecs", "PERMISSION", "Ask Execs: a human gate before risky steps",
            "With Ask Execs on, the executor blocks before each risky tool and waits for Proceed or Deny in "
            "the browser. A single Deny halts the whole chain and leaves a red “Execution interrupted” "
            "banner.",
            body=[
                "The gate is an explicit allowlist, chosen tier by tier. Every doubtful path resolves to Deny: a "
                "failed prompt, a Cancel or a disconnected browser never lets a risky tool run unconfirmed. "
                "Unchecking Ask Execs during a run relaxes that run; checking it again re-arms the prompts.",
            ],
            table={"columns": ["Tier", "Prompted", "Agents"], "widths": [0.26, 0.16, 0.58], "rows": [
                ["Command and script runners", "Yes", "Executer, Pythonxer, SSHer, Kalier, Dockerer, "
                 "Kuberneter, SQLer, Mongoxer, Gitter, Jenkinser, PSer, J-Decompiler"],
                ["A · destroys or overwrites", "Yes", "Deleter, Mover, File-Creator, Editor, De-Compresser, "
                 "unzip, PDFer, LaTeXer"],
                ["D · remote systems", "Yes", "SCPer, Apirer, Nmapper, Discoverer, Crawler, "
                 "NetSpeed-Calculator"],
                ["B · messaging", "No", "Emailer, Whatsapper, Telegrammer, Zavuerer, Instant Messaging "
                 "Doctor: sending is the model's own judgement"],
                ["C · desktop and hardware", "No", "Keyboarder, Mouser, Windower, Playwrighter, firmware "
                 "agents, Blenderer, Unrealer: visible while they act"],
            ]}, deck="table"),
        Section("rag", "RETRIEVAL", "Grounded in your project, and only its text",
            "Hybrid retrieval combines FAISS vectors with BM25 keywords, extracts metadata, budgets the "
            "context and falls back gracefully when a chain cannot retrieve.",
            body=[
                "When you load a directory or file, that loaded context outranks her self-knowledge: a request "
                "to “summarize the project” is answered from your project, not from a description of "
                "herself.",
                "Before any file is embedded, a binary-content guard screens its bytes in a short-circuiting "
                "cascade that reads at most one 8 KiB block. Binary files are dropped exactly like a name you "
                "chose to omit, and every drop is named in `tlamatini.log` under `--- [BINARY-GUARD]`.",
                "The guard fails open: any doubt means “load it as text”, because silently deleting real "
                "context is worse than embedding one odd file. The byte-order-mark stage runs before the NUL-byte "
                "stage, or every UTF-16 document would vanish.",
            ],
            visual="cascade",
            visual_data={"stages": [
                ("Extension", "Known binary suffix, no I/O"),
                ("Sample", "One 8 KiB read"),
                ("Empty", "Nothing to embed"),
                ("BOM", "UTF-8/16/32 is text"),
                ("Signature", "45 magic numbers"),
                ("NUL byte", "Classic binary test"),
                ("Control ratio", "Non-text byte share"),
                ("UTF-8", "Undecodable and dirty"),
            ]}, deck="visual"),
        Section("compiler", "FLOW COMPILER", "One compiler for the canvas and the chat",
            "Canvas snapshots and chat-generated drafts compile through the same Agent Contract registry "
            "before any file reaches the session pool.",
            body=[
                "Each agent's contract declares which configuration field a connection on each slot writes, "
                "which fields Parametrizer may read, which paths are secrets to redact, and whether it is a "
                "singleton, long-running or never starts its targets. Both surfaces normalize into one "
                "`FlowSpec` (schema version 2).",
                "The canvas Start button compiles the live snapshot in write mode, so an edited but unsaved flow "
                "runs under the same validation as a freshly loaded file. Validate uses a dry run that previews "
                "the compiled configuration without touching disk.",
                f"Agents that feed Parametrizer emit one atomic `INI_SECTION` block per result. "
                f"{f['parametrizer_sources']} agents currently declare structured outputs.",
            ],
            code=("INI_SECTION_APIRER<<<\n"
                  "url: https://example.org/status\n"
                  "status: 200\n"
                  "\n"
                  "{\"service\": \"ok\"}\n"
                  ">>>END_SECTION_APIRER"),
            deck="split",
            deck_points=[
                ("Contracts", "Connection slots, Parametrizer fields, secret paths, lifecycle flags."),
                ("Start", "Compiles the live canvas in write mode before any agent runs."),
                ("Validate", "A dry run that previews the compiled configuration."),
                ("Create Flow", "Chat drafts pass the same normalizer and redaction."),
            ]),
        Section("resilience", "RELIABILITY", "Built to keep running",
            "Small, deliberate mechanisms keep the core alive under the conditions that used to stop it.",
            points=[
                ("Console shield", "The log file is written first; console output goes through a bounded "
                 "queue, so clicking the console can no longer freeze the application."),
                ("Orphan reaper", "Three tiers sweep dead descendants and orphaned console hosts after tools, "
                 "after answers and at shutdown, without ever raising into the chat."),
                ("Per-user log lines", "Lines carry a five-character tag such as [a3] so concurrent users "
                 "and turns never blur."),
                ("Clean Ctrl+C", "The signal handler only sets an event; a worker cleans up, a watchdog "
                 "guarantees exit, and a second Ctrl+C exits at once."),
                ("Configurable port", "`django_port` moves the web port with no rebuild and falls back to "
                 "8000 on any bad value."),
                ("Temp and Templates", "Scratch files live under the application's Temp folder; scaffolded "
                 "projects default to its Templates folder."),
            ], deck="cards"),
    ])

    surfaces = Chapter("surfaces", "III", "Where You Work With Her",
        "The chat, the two canvases, the catalog and the dialogs that operate everything else.",
        accent="gold", sections=[
        Section("chat", "THE CHAT PAGE", "Conversation with modes",
            "The chat page is where you talk to her. Six toolbar switches decide how each request runs.",
            body=[
                "Beside the conversation sits a canvas that shows code, text and PDFs. Paste a screenshot with "
                "Ctrl+V or drop images on the chat: she saves them to her Temp folder and writes the full path "
                "into your message, ready for Image-Interpreter. A context ring between the toolbar and the "
                "message box shows how much of the model's window the real request uses, measured by the "
                "backend in bytes with tokens estimated.",
                "Her avatar speaks answers aloud when you ask, with a mouth that follows the spoken words. After "
                "login, pressing Enter on the welcome page takes you straight to the chat.",
            ],
            table={"columns": ["Switch", "What it does"], "widths": [0.24, 0.76], "rows": [
                ["Multi-Turn", "Planned, tool-calling operator mode; unchecked means direct one-shot answers."],
                ["Exec Report", "Appends per-agent execution tables; available while Multi-Turn is on."],
                ["ACPX", "Adds the twelve ACPX and Skill tools to the bound surface; off by default."],
                ["Ask Execs", "Proceed/Deny before each risky tool; a Deny stops the chain."],
                ["Step-by-Step", "One concrete action at a time, waiting for your reply before the next."],
                ["Internet", "Allows a web search to add context to the answer."],
            ]}, deck="table"),
        Section("dictation", "DIRECT VOICE INPUT", "Speak beside Send",
            "The microphone captures first; no model tool-selection step stands between the click and recording.",
            body=[
                "Click the microphone beside Send, wait for Listening, and speak into the microphone on the "
                "Tlamatini host. Real input level, elapsed time and the silence countdown stay in the chat. "
                "After the configured silence window (shipped default 3.5 seconds), recognition runs and the "
                "text is appended to the existing draft and sent automatically through the normal form.",
                "There is no transcript review step. A second click or Escape cancels; empty or failed "
                "recognition sends nothing. Current modes and permission behavior remain in force. "
                "The avatar acknowledges dispatch through browser speech and respects Silent mode.",
            ],
            points=[
                ("Click", "Direct Whisperer start; the host microphone opens only for a recording."),
                ("Listen", "Live samples drive the in-chat indicator and the configured silence gate."),
                ("Recognize", "Local faster-whisper or the explicitly configured cloud speech engine."),
                ("Send", "Automatically submit once, with the current draft and mode switches; no review dialog."),
            ], deck="cards"),
        Section("dictationruntime", "INTERNAL SERVICE", "One main console, no extra window",
            "Developer visibility requirements do not become additional product windows.",
            body=[
                "The authenticated same-origin /ws/chat-voice/ connection prepares one resident worker per "
                "web process. Source/carried Python runs chat_worker.py; the frozen Django process stays "
                "free of the speech ML stack. A private token-authenticated loopback socket carries control "
                "and result frames. Preparation does not open the microphone.",
                "No PowerShell, conhost, focus activation or console-visibility prerequisite is involved. "
                "The worker's stdout/stderr flows through agent.chat_voice_runtime into the main console/log. "
                "Failed startup and shutdown reap the child. Config reloads per job; compatible models are "
                "cached, and late cancelled results cannot submit.",
            ],
            points=[
                ("UI ownership", "The composer displays recording and transcription; no second console."),
                ("Configuration", "Speech model settings and explicit template overrides still apply."),
                ("Boundary", "The direct button is input, not a wrapped tool or an Exec Report row."),
                ("Release", "Ship the consumer/runtime modules, carried worker, JS/CSS and matching template."),
            ], deck="cards"),
        Section("dictationevidence", "VERIFICATION SCOPE", "Measured source behavior",
            "Dated source checks are evidence, not a claim that an older installer contains the change.",
            body=[
                "On September 27, 2026, 98 voice tests passed: 26 direct-voice and 72 existing Whisperer "
                "checks. A real host microphone began yielding samples in 297 ms after direct start; "
                "cancellation and normal worker exit were observed. Two startup/shutdown cycles created "
                "no additional visible windows and left foreground focus unchanged.",
                "The earlier headed-browser suite passed 33 controlled-transport checks. Earlier cached "
                "recognition of a 5.768-second synthetic speech file took 0.203 seconds, versus 11.094 "
                "seconds on first decode. These are separate observations, not end-to-end latency guarantees. "
                "No new live Ollama task or rebuilt installer was certified by those checks.",
            ],
            points=[
                ("Current source", "98 voice regressions plus real microphone and worker lifecycle probes."),
                ("Browser evidence", "33 earlier headed checks with controlled transport; not live ASR."),
                ("Limits", "Cold model loading, provider latency and hardware vary; no zero-latency promise."),
                ("Detailed guide", "docs/chat-microphone-design.md records configuration, protocol and evidence."),
            ], deck="cards"),
        Section("navbar", "NAVIGATION", "The menu bar, reorganized in v1.70.0",
            "A new Panels menu opens the two canvases, and every configuration dialog lives under Config.",
            table={"columns": ["Menu", "What you find there"], "widths": [0.20, 0.80], "rows": [
                ["Open · Save", "Load a file into the canvas or save its contents."],
                ["Context", "Load a directory or file as context, and set file-type omissions."],
                ["Panels", "Agentic Control Panel, Prompt Flow Panel and, for staff, the Admin Panel. "
                 "It stays usable while she is busy."],
                ["ACPX-Skills", "Browse, configure, diagnose and reload the skill catalog."],
                ["External", "The External MCPs dialog: catalog, activation and runtime readiness."],
                ["Config", "Configure MCPs, Configure Agents, Models, URLs, Contacts, Access Keys Wizard, "
                 "Voice."],
                ["DB", "WAL-safe database backup and staged replacement."],
                ["Reconnect · About", "Rebuild the chat connection; version, credits and Check for "
                 "updates."],
            ]}, deck="table"),
        Section("acp", "AGENTIC CONTROL PANEL", "Design agent workflows visually",
            f"Drag any of the {agents} agent types onto the canvas, connect output triangles to input "
            "triangles, configure each node, validate, and press Start.",
            body=[
                "Agents run as separate, log-emitting processes that talk through their `config.yaml` files, "
                "with a live LED for each. Flows can be paused, resumed and stopped, and saved or loaded as "
                "`.flw` files. FlowCreator can design a flow from a sentence, and FlowHypervisor watches a "
                "running flow and raises an alert when something looks wrong.",
                "Since v1.70.0 the canvas is a real editor. Duplicate copies agents together with their saved "
                "settings and the connections between them; Undo also restores an agent's configuration. "
                "Editing locks while a flow runs, so a flow is never changed underneath its own processes.",
            ],
            points=[
                ("Undo and Redo", "Up to 1,024 steps, configuration included."),
                ("Duplicate", "Copies settings and internal connections."),
                ("Zoom", "25 to 200 percent, and Fit."),
                ("Agent search", f"Filters the {agents} agent types by name."),
                ("Starters", "Locates each Starter on a large canvas."),
                ("Help", "Explains every gesture; • marks unsaved changes."),
            ], deck="split"),
        Section("pfp", "PROMPT FLOW PANEL", "Draw a conversation, then press Play",
            "The Prompt Flow Panel turns a chain of prompts into a diagram of seven operations, saved as a "
            "portable `.fpmt` file and played against your configured models.",
            visual="operations",
            visual_data={"ops": [
                ("prompt", "Prompt", "Sends its text to the model; Multi-Turn and ACPX can be enabled."),
                ("programmed", "Programmed Prompt", "Waits for a scheduled time or a delay, then sends."),
                ("decision", "Decision", "Takes Yes or No from the last answer, or asks you."),
                ("feed", "Feed embeddings", "Adds reference text to this run's retrieval context."),
                ("flush", "Flush embeddings", "Clears the run's retrieval context."),
                ("clean", "Clean History", "Clears the run's conversation and last output."),
                ("commentary", "User Commentary", "Stops to ask you something; your reply joins the run."),
            ]}, deck="visual"),
        Section("pfprun", "PROMPT FLOW PANEL", "Playback that stays in its own lane",
            "Validate checks the diagram, Play runs it, and every run keeps its own conversation, embeddings "
            "and cancellation identity, so it never disturbs your chat.",
            body=[
                "Write `{{last_output}}` to pass the previous answer forward. Decisions compare strings — "
                "contains, does not contain, equals, empty, with optional case matching — and never evaluate "
                "expressions from a file. Cycles are allowed and bounded by a maximum number of executed "
                "operations, 500 by default and up to 5,000.",
                "The running figure lights up and traversed connections are highlighted. Pause lets the current "
                "operation finish and holds the next; Stop drains the running worker before another run may "
                "start. Opening a file never runs it.",
            ],
            points=[
                ("Format", "JSON `tlamatini-prompting-flow`, version 1."),
                ("Limits", "5 MiB, 500 operations, 1,000 connections."),
                ("Isolation", "Empty history and embeddings at every start."),
                ("Validation", "Checked in the browser and again on the server."),
                ("Not .pmt", "Plain-text system prompts keep .pmt and are refused."),
                ("Drafts", "Kept per user in browser storage."),
            ], deck="cards"),
        Section("catalog", "CATALOG OF PROMPTS", "Ready-made prompts, grouped by purpose",
            f"The Catalog of Prompts opens with {sections_count} sections, each beginning with a guided "
            f"Step-by-Step wizard and growing from simple to advanced.",
            body=[
                f"Sections: {catalog_names}. VOICE COMMANDS comes first, because speaking is the shortest way "
                f"to use her: you talk, Whisperer transcribes, and the transcript becomes the prompt. "
                "These catalog workflows use the model-mediated wrapped tool and their card-specific modes; "
                "they are distinct from the direct microphone button beside Send.",
                "The mode badges on each card are derived from the prompt text itself, and clicking a card sets "
                "the toolbar switches to exactly those modes. Every prompt uses one grammar, so it is always "
                "clear whose blank is whose.",
            ],
            table={"columns": ["Mark", "Filled by", "Meaning"], "widths": [0.18, 0.22, 0.60], "rows": [
                ["[[ … ]]", "You", "A value you provide, collected at the top with a safe default."],
                ["{{ … }}", "Tlamatini", "A value she fills at run time."],
                ["< … >", "Report slot", "Where an answer is printed; never an input."],
            ]}, deck="split",
            deck_points=[
                ("Sections", f"{sections_count}, beginning with VOICE COMMANDS."),
                ("Openers", "Every section starts with a guided Step-by-Step wizard."),
                ("Badges", "Derived from the prompt text; a click sets the modes."),
                ("Grammar", "[[ you ]], {{ runtime }}, < report slot >."),
            ]),
        Section("pdfcanvas", "PDF CANVAS", "Read a PDF, then hand her the whole document",
            "Open a PDF beside the chat in a vendored Mozilla PDF.js viewer, then use it as context.",
            body=[
                "Reading uploads nothing and calls no model: the viewer reads byte ranges straight from your "
                "disk, so there is no size or page cutoff on Tlamatini's side. Text selection, navigation, zoom, "
                "fit, rotation and in-viewer passwords behave as you expect; Copy lifts the text of every page "
                "and Save As returns the original bytes.",
                "**Use as context** asks one question first: Process images? It starts unticked every time, and "
                "nothing runs until you press Continue. Unticked, she reads the selectable text only. Ticked, she "
                "also renders every page and analyzes every embedded image with Image-Interpreter. Progress is "
                "honest, Cancel really cancels, and partial image failures are reported, not hidden. A PDF "
                "password is used in memory only: never written to disk, to the context text or to the log.",
            ], deck="list",
            deck_points=[
                ("Private reading", "Byte ranges from your disk; nothing uploaded, no model called."),
                ("Viewer", "Mozilla PDF.js 6.3.289, vendored under Apache-2.0; no CDN."),
                ("Use as context", "Text only by default; images only when you tick the box."),
                ("Honest progress", "Four progress rows, a real Cancel, failures reported."),
                ("Passwords", "Used in memory only; never stored or logged."),
            ]),
        Section("models", "CONFIG ▸ MODELS", "Every model choice in one place",
            f"The Models dialog exposes {model_fields} model, engine and voice settings for the core services "
            f"and {model_agents} model-backed agents, in six searchable categories.",
            body=[
                f"Categories: {groups_text}. Save submits all values, preserves unrelated configuration and "
                "downloads nothing. Reconnect the chat to rebuild its clients; agents pick up a choice at their "
                "next configuration load.",
                "Agent templates marked `\"@config\"` follow the global choice, while a literal value in a "
                "workflow remains an explicit override. Wrapped chat launches seed the global choices before "
                "any explicit tool argument, and the frozen build proves every model loader runs before it "
                "packages.",
            ],
            visual="bars_models", deck="split",
            deck_points=[
                ("Settings", f"{model_fields} model, engine and voice choices."),
                ("Agents", f"{model_agents} model-backed agents configured centrally."),
                ("Inheritance", "\"@config\" follows the global choice; literals override."),
                ("Save", "Preserves unrelated configuration; downloads nothing."),
            ]),
        Section("dialogs", "OPERATOR DIALOGS", "Everything else, without editing files",
            "Configuration, credentials, databases and updates are handled from the browser.",
            points=[
                ("Access Keys Wizard", "One guided place for provider keys; blank fields keep what is set."),
                ("Contacts", "Names resolve to addresses, phones and @usernames for messaging agents."),
                ("DB menu", "WAL-safe backup, and a verified database staged for the next start."),
                ("External ▸ MCPs", "Search the catalog, activate up to five servers, install runtimes."),
                ("ACPX-Skills", "Browse, enable, diagnose and reload skills."),
                ("Check for updates", "Stage the latest published release and swap it in safely."),
            ],
            callout=("One dismissal rule everywhere",
                     "Escape means exactly what a dialog's ✕ means, and an outside click never dismisses "
                     "anything. A downloading updater is the single dialog that refuses to close."),
            deck="cards"),
    ])

    bestiary_sections = []
    for name, accent, blurb, members in AGENT_FAMILIES:
        bestiary_sections.append(Section(
            "family_" + name.lower().replace(" ", "_").replace(",", ""), "AGENT FAMILY",
            name, blurb,
            points=[(f["display_names"][key], text) for key, text in members],
            visual_data={"accent": accent, "count": len(members)}, deck="family"))
    bestiary = Chapter("bestiary", "IV", "The Bestiary",
        f"{agents} agent types in twelve families. Each is a plain-Python program you can read, audit and change.",
        accent="magenta", sections=[
            Section("bestiary_intro", "THE AGENTS", f"{agents} agents, twelve families",
                "Every agent follows one skeleton: a template directory, a `config.yaml`, a session-scoped "
                "pool copy, PID and log files, and explicit source and target wiring.",
                body=[
                    f"{wrapped} of them also run from the chat as wrapped `chat_agent_*` tools, each in its own "
                    "isolated runtime folder. Every wrapped agent appears in the Exec Report automatically, and "
                    "each ships at least one example prompt in the catalog.",
                    "Display names keep their exact designed casing — STM32er, PDFer, LaTeXer, ACPXer — while "
                    "directories, pools and style classes use lowercase forms.",
                ],
                visual="family_wheel", deck="visual"),
            *bestiary_sections,
        ])

    capabilities = Chapter("capabilities", "V", "Deep Capabilities",
        "The subsystems that give her reach: other agents, other servers, documents, boards, engines and senses.",
        accent="cyan", sections=[
        Section("acpx", "ACPX", "Other coding agents as her children",
            "ACPX spawns external coding-agent CLIs as out-of-process children, talks to them over "
            "stdin and stdout, keeps an NDJSON transcript of every turn, and brokers it all to the model as "
            "twelve tools.",
            body=[
                f"{len(peers)} peers are registered: {', '.join(peers)}. One-shot peers receive the prompt as a "
                "command-line argument and are read to completion; the Tlamatini self-host speaks strict JSON; "
                "interactive peers are drained by a transport-aware idle rule. ACPX is a Python port of "
                "OpenClaw's ACPX plugin, so its agent identifiers and skill contract are compatible.",
                "ACPX tells the truth about its peers. A version check is not health and exit code 0 is not "
                "success: a stdlib-only classifier decides whether a child actually delivered, and a refusal is "
                "returned as `ok: false` with a named code instead of a green row. `acp_doctor(deep=True)` sends "
                "a real one-line prompt to each peer and names what is broken.",
                "Children are never spawned through the shell, because cmd.exe silently cuts a command line at "
                "its first newline. npm and pnpm shims are rewritten to `node.exe` with the script path.",
            ],
            table={"columns": ["Non-delivery code", "Meaning"], "widths": [0.42, 0.58], "rows": [
                ["PERMISSION_BLOCKED", "The child stopped at its own permission prompt."],
                ["AUTH_FAILED · CONFIG_INVALID", "It could not authenticate, or refused its own config."],
                ["NO_CREDIT · USAGE_LIMIT", "No credit, or a plan or rate limit was reached."],
                ["UPSTREAM_ERROR", "The model provider returned a server-side error."],
                ["NO_OUTPUT · CHILD_ERROR", "Nothing legible came back, or it failed without an answer."],
                ["WORKSPACE_NOT_TRUSTED", "Its working folder is untrusted, so permissions were ignored."],
            ]}, deck="split",
            deck_points=[
                ("Peers", f"{len(peers)} CLIs, including Claude Code, Codex, Gemini, Cursor and Qwen."),
                ("Twelve tools", "Spawn, send, wait, relay, transcript, status, kill, doctor, skills."),
                ("Truthful", "A refusal returns ok: false with a named code."),
                ("No shell", "Shims are rewritten so long prompts are never cut."),
            ]),
        Section("mcps", "EXTERNAL MCPS", "A universal MCP client",
            "Connect Tlamatini to any MCP server declared in a JSON catalog and use its tools at once, with "
            "no code written for the server.",
            body=[
                "The catalog uses the standard `mcpServers` shape and lives beside `config.json`, preserved "
                "across updates. Four transports connect — stdio, streamable HTTP, SSE and WebSocket — lazily "
                "on a background thread, so a slow server can never delay an answer. Up to five servers are "
                "active at once, and each remote tool appears as `ext__<server>__<tool>`.",
                "Most servers start with `npx` or `uvx`, which a fresh machine lacks. A private runtime "
                "provisioner downloads Node and uv once from their official sources into the user's profile, "
                "verifies checksums, installs atomically, needs no administrator rights and never changes the "
                "system PATH.",
                "Memory and Sequential Thinking ship in every installation, inactive. A default you delete is "
                "remembered and never resurrected; one you edit is never overwritten.",
            ],
            visual="chain",
            visual_data={"chain": ["Classify", "Import", "Doctor", "Activate", "Wait", "List", "Call"],
                         "caption": "The adding-external-mcp skill: one guarded onboarding sequence."},
            deck="split",
            deck_points=[
                ("Transports", "stdio, streamable HTTP, SSE and WebSocket."),
                ("Ten supervisors", "Status, reconnect, doctor, runtimes, import, list, call, activate, wait."),
                ("Private runtimes", "Node and uv provisioned per user, no admin, no PATH change."),
                ("Defaults", "Memory and Sequential Thinking, inactive until you choose."),
            ]),
        Section("skills", "SKILLS", "Procedures, handed over complete",
            f"{skills} `SKILL.md` packages are loaded at start-up and offered to the model through "
            "`list_skills` and `invoke_skill`.",
            body=[
                "Invoking an in-process skill is a planning handoff, not a hidden execution. It returns the "
                "complete procedure, the contract of outputs still owed, and an honest statement of what is "
                "enforced — argument checks, secret redaction and time budgets — and what remains declared "
                "policy, gated by the normal Configure and Ask Execs surfaces.",
                "Skills include code review, security audit, the Kali pentest runbook, flow making, skill "
                "creation, summarization, the adding-external-mcp runbook, Roblox Studio, repository audit and "
                "refactor helpers, and integration guides for GitHub, Gmail, Slack, Jira, Notion, Todoist, "
                "Trello and weather. The ACPX-Skills menu enables, diagnoses and reloads them without a restart.",
            ],
            callout=("Credentials stay inside",
                     "An input marked sensitive, or named like a credential, is redacted from every audit "
                     "event and from the returned result: no prefix, no length, no hash."),
            deck="list",
            deck_points=[
                ("Catalog", f"{skills} packages, validated by one shared routine."),
                ("Handoff", "invoke_skill returns the full procedure and the outputs still owed."),
                ("Honest enforcement", "It states what is enforced and what is declared policy."),
                ("Administered", "Browse, Configure, Diagnostics and Reload from the menu."),
            ]),
        Section("documents", "THE DOCUMENT FAMILY", "Compose, present, typeset",
            "Three agents produce documents, each with its own craft, and none of them calls a file clean "
            "just because it was created.",
            table={"columns": ["Agent", "Craft", "Signature features"], "widths": [0.14, 0.24, 0.62], "rows": [
                ["PDFer", "Composes PDFs from text, Markdown, HTML and images",
                 "24 visual styles in five families over 20 content themes; measured tables and covers; a "
                 "layout audit that reopens the file and checks overlap, off-page text, blank pages and "
                 "contrast."],
                ["PPTXer", "Builds editable PowerPoint decks",
                 "36 named treatments and 17 font pairings; text measured before it is placed, so long "
                 "content continues onto a new slide; native PowerPoint verification when installed."],
                ["LaTeXer", "Typesets real LaTeX",
                 "Eight templates and 30 signature styles; whole-project builds with bibliography and index "
                 "convergence; readable diagnostics; an eight-rung repair ladder; MiKTeX recommended."],
            ]},
            callout=("Created is not verified",
                     "A saved file only proves it exists. Read PDFer's `layout_clean`, PPTXer's "
                     "`ground_truth`, or LaTeXer's `status` before calling a document clean."),
            deck="table"),
        Section("ladder", "LATEXER", "A repair ladder that protects your words",
            "When a build fails, LaTeXer climbs eight rungs in a fixed order, each tried only if the one "
            "before produced no PDF.",
            body=[
                "Every repair is applied to a copy and re-linted; a repair that makes the lint worse is reverted. "
                "The author's file is never overwritten unless `repair_write_back` is set, every rung is recorded "
                "in an audit trace, and any block set aside is named with its line number.",
                "Bisect is strictly last because it is the only rung that removes content, and it is skipped when "
                "the model rung merely could not be reached. A clean build tells the model plainly that the "
                "document is finished, so a good PDF is never “improved” into a broken one.",
            ],
            visual="ladder",
            visual_data={"rungs": [
                ("1", "lint", "Static structural repair before any compiler runs."),
                ("2", "preamble", "Infer packages from the commands actually used."),
                ("3", "rules", "Deterministic rewrites of known-bad constructs."),
                ("4", "log-directed", "Compile, read the real error, fix that line."),
                ("5", "acquire", "Install a package that is genuinely missing."),
                ("6", "engine swap", "Retry with XeLaTeX or LuaLaTeX."),
                ("7", "model", "Ask a model; its answer re-enters at rung 1."),
                ("8", "bisect", "Last: set the failing block aside, and say so."),
            ]}, deck="visual"),
        Section("firmware", "FIRMWARE", "Real boards, fail-safe by design",
            "Four agents take firmware from scaffold to a running board, and each refuses rather than flash "
            "something that cannot be right.",
            table={"columns": ["Agent", "Toolchain", "Highlights"], "widths": [0.14, 0.26, 0.60], "rows": [
                ["STM32er", "PlatformIO ststm32 and the STM32 Template Project MCP",
                 "Blue Pill through F7, G, L, H7, U5 and WB; zero-config bootstrap; ST-LINK probe checks; "
                 "newest silicon refused cleanly until its native backend exists."],
                ["ESP32er", "PlatformIO Core, called directly",
                 "Copies a blink-and-print template so a new project compiles at once; serial-aware preflight."],
                ["Arduiner", "arduino-cli, downloaded on demand",
                 "The board is chosen by its FQBN; the board's core is installed automatically."],
                ["ESPHomer", "The esphome CLI",
                 "Smart-home devices from YAML; headless config generator; USB first flash, OTA after."],
            ]},
            callout=("Authorized hardware only",
                     "Flash, erase, reset and upload change a real attached device. STM32er drives "
                     "mission-critical robot firmware, which is why its preflight fails safe."),
            deck="table"),
        Section("engines", "CREATIVE ENGINES", "Unreal Engine and Blender, live",
            "Two agents drive running editors over their own sockets, from chat or from the canvas.",
            points=[
                ("Unrealer", "Talks to the Unreal MCP plugin over TCP: 53 commands in nine categories "
                 "— editor, Blueprint, nodes, project, UMG, system, level, asset and material."),
                ("Tlamatini's Unreal fork", "XaihtUnrealEngineMCP ships the full surface plus a scaffolder for "
                 "a ready-to-build UE 5.8 C++ project with a Visual Studio 2026 solution."),
                ("Blenderer", "Speaks the official Blender MCP add-on's code-execution protocol on its local "
                 "socket, with a rich action catalog so most tasks need no hand-written Python."),
                ("Chainable", "Both return structured blocks, so Parametrizer can carry a result into the "
                 "next step and a Forker can branch on it."),
            ], deck="cards"),
        Section("security", "SECURITY", "Assessment for authorized targets",
            "Offensive and defensive tooling is part of the catalog, always limited to systems you own or are "
            "explicitly authorized to test.",
            points=[
                ("Kalier", "Kali Linux tools through MCP-Kali-Server: nmap, gobuster, nikto, sqlmap and more."),
                ("Discoverer", "subfinder, httpx, naabu, katana, nuclei and vulnx on a private Go toolchain."),
                ("Nmapper", "Uses the nmap you installed; never bundles it; connect scan needs no admin."),
                ("Analyzer", "bandit, semgrep, ruff, eslint, gitleaks and pip-audit, deterministically."),
                ("Reviewer", "A senior-engineer review of a diff, with a verdict a flow can branch on."),
                ("Kyber", "Post-quantum key generation, encryption and decryption."),
            ], deck="cards"),
        Section("bluehat", "BLUE-HAT TOOLKIT", "Windows defence, operated by a human",
            "The `security/` toolkit is an administrator-run monitoring and response kit, not a chat tool: a "
            "person launches it, reads its evidence and decides.",
            body=[
                "Enablement makes persistent changes. Defender and the firewall keep running, but the "
                "installation is excluded from scans, allowed through Controlled Folder Access, and six attack "
                "surface reduction rules move to Audit. Those exceptions are real trade-offs, so record a "
                "baseline before elevation; there is no automatic rollback.",
                "The monitor watches ten signal families, from Defender health and logons to persistence, "
                "ransomware indicators and administrator-group changes. Start with a detect-only baseline, "
                "investigate, and arm only when justified. A non-destructive visible harness validates the "
                "assets themselves.",
            ],
            table={"columns": ["Mode", "Behaviour"], "widths": [0.28, 0.72], "rows": [
                ["-DetectOnly", "Reports what it would block or stop; the safe first run."],
                ["default", "One armed sweep; may block an attacking IP and stop known attacker tools."],
                ["-Watch", "Continuous sweeps until Ctrl+C, every 60 seconds by default."],
                ["-Aggressive", "Also stops dual-use tools outside Tlamatini's paths; incidents only."],
            ]}, deck="split",
            deck_points=[
                ("Operator-run", "A human launches it and owns every policy change."),
                ("Ten families", "Defender, logons, network, processes, persistence, ransomware, accounts."),
                ("Detect first", "Baseline with -DetectOnly before arming."),
                ("Trade-offs", "Exclusions and Audit-mode rules are recorded and explained."),
            ]),
        Section("voice", "VOICE", "She listens until you stop, and answers in her voice",
            "Direct chat dictation, workflow Whisperer, Talker and catalog commands have distinct voice contracts.",
            body=[
                "In standalone/workflow Whisperer, no duration means the gate records while you talk and stops "
                "after 3.5 seconds of silence, with a 300-second ceiling. `record_seconds: 0` is the switch; name "
                "a duration and it is honoured exactly. The gate starts at a sensitive floor so a speaker who "
                "begins at once is heard, and if a sound driver refuses the live stream she records a fixed "
                "length and says so. Direct chat dictation instead requires the gate and refuses that fallback.",
                "Transcription runs locally with faster-whisper, on a GPU when present and on the CPU otherwise, "
                "or through a cloud Whisper provider. Talker speaks through an Orpheus-compatible model in a "
                "female voice — tara, leah, jess, mia or zoe. A male voice is refused by design.",
                "The catalog's first section, VOICE COMMANDS, makes the microphone the keyboard: she transcribes "
                "your instruction, reads it back, and only then acts. Anything irreversible still needs your "
                "written confirmation under those catalog instructions. The direct chat microphone submits "
                "automatically and uses browser speech for its acknowledgment, respecting Silent mode.",
            ], deck="list",
            deck_points=[
                ("Sound gate", "Records while you talk; stops after 3.5 s of silence."),
                ("Workflow duration", "Standalone/workflow recording can use an explicit fixed duration."),
                ("Local first", "faster-whisper on GPU or CPU, or a cloud provider."),
                ("Her voice", "Female only: tara, leah, jess, mia or zoe."),
                ("Direct microphone", "Gate, recognize, automatically send; no review dialog or extra console."),
                ("Catalog commands", "Model-mediated cards can request readback before acting."),
            ]),
        Section("vision", "VISION AND VIDEO", "Eyes that report their limits",
            "Image and video analysis combine independent observers, so one model's guess is never presented "
            "as fact.",
            points=[
                ("Image-Interpreter", "Two vision models read each image in parallel on their own connections; "
                 "a third merges both into one definitive report."),
                ("Video-Analyzer · robotics", "A deterministic motion gate plus two vision models; PASS only "
                 "when both agree."),
                ("Video-Analyzer · transcription", "Timestamped speech from chosen audio tracks, locally."),
                ("Video-Analyzer · summary", "Speech plus sampled visual evidence: scenes, text, facts, "
                 "decisions and limits."),
                ("Capture", "Shoter, Camcorder and Recorder save to your known folders with exact names."),
                ("Paste to chat", "A screenshot pasted into the chat becomes a path she can analyze."),
            ], deck="cards"),
        Section("desktop", "DESKTOP AND BROWSER", "Precise hands on a real desktop",
            "Desktop agents state their coordinate spaces and their evidence, because a click that lands in "
            "the wrong place is worse than no click.",
            points=[
                ("Mouser", "Coordinates are declared: physical screen, desktop, normalized, window or "
                 "screenshot."),
                ("Shoter", "Publishes the exact captured rectangle, image size and monitor geometry."),
                ("Keyboarder", "Binds each keystroke to a verified window and stops on focus loss."),
                ("Delivery is not acceptance", "`input_sent` proves delivery only; interrupted input is "
                 "inspected before any replay."),
                ("Playwrighter", "A real browser through declared steps, with a hold-open knob to watch."),
                ("Windower", "Focus, move, resize, tile, pin and close windows by title."),
            ], deck="cards"),
        Section("web", "WEB AND NETWORK", "Search that survives, measurement that shows its error bar",
            "Googler keeps finding results when browsers are refused, and NetSpeed-Calculator publishes a "
            "speed with its confidence interval.",
            body=[
                "Googler tries four plain-HTTP, server-rendered routes first, then a visible installed Chrome "
                "across seven browser routes with bounded retries, and always names the route that answered. "
                "Its structured dork builder writes valid operators, presets and grouped site or file-type "
                "filters, and `links_only` returns URLs for downloads handled downstream. Indexed is not "
                "permitted: licensing and authorization remain yours.",
                "NetSpeed-Calculator measures several keyless providers at once, discards the TCP slow-start "
                "ramp, samples throughput as a derivative, rejects outliers and fuses providers with a "
                "random-effects meta-analysis. It grades bufferbloat from A+ to F. A full run transfers about "
                "100 to 200 MB, so it asks before running.",
            ], deck="list",
            deck_points=[
                ("Googler tiers", "Four plain-HTTP routes, then visible Chrome across seven."),
                ("Dork builder", "Valid operators, presets, grouped filters, links_only output."),
                ("NetSpeed", "Parallel streams, Student-t intervals, random-effects fusion."),
                ("Bufferbloat", "Latency under load, graded A+ to F."),
                ("Metered", "About 100 to 200 MB per full run; it asks first."),
            ]),
        Section("messaging", "MESSAGING", "Reaching people deliberately",
            "Messaging agents use official surfaces by default and make every unofficial route an explicit "
            "choice.",
            points=[
                ("Telegrammer", "Sends as the bot or as your own account; “send it as me” picks yours."),
                ("Whatsapper", "Meta's official Cloud API by default; your own number only when you say so."),
                ("Zavuerer", "One Zavu key for SMS, WhatsApp, Telegram, email and voice, with smart routing."),
                ("TeleTlamatini", "The full chat in Telegram, on a dedicated account."),
                ("Instant Messaging Doctor", "Checks tokens, contacts, templates and policy windows."),
                ("Contacts", "A contact name resolves to the real address when a message is sent."),
            ], deck="cards"),
    ])

    trust = Chapter("trust", "VI", "Promises She Keeps",
        "Honesty, consent, safety and control, written into the code rather than into a brochure.",
        accent="rose", sections=[
        Section("honesty", "HONESTY", "Truth over comfort",
            "Where a system can be confidently wrong, Tlamatini is built to say what she knows and what she "
            "does not.",
            points=[
                ("Self-report first", "An agent's typed result outranks a one-bit exit code."),
                ("Degraded is red", "A compromised deliverable is never painted green."),
                ("Silence is named", "Skipped files, dead transfers and refusals carry a reason."),
                ("Recovery is narrated", "Retries are shown live and summarized in the answer."),
                ("Created is not clean", "Documents report their audits before being called finished."),
                ("Delivered is not accepted", "Desktop input evidence is kept distinct from success."),
            ], deck="cards"),
        Section("failmodes", "FAILURE MODES", "Fail open or fail safe, on purpose",
            "Every guard chooses its failure direction deliberately, by asking which mistake would hurt you "
            "more.",
            table={"columns": ["Mechanism", "Direction", "Why"], "widths": [0.30, 0.16, 0.54], "rows": [
                ["Binary-content guard", "Open", "Dropping real context is worse than embedding one odd file."],
                ["Verdict parsing", "Open", "A parse error falls through to the next rule; it never raises."],
                ["Port and console settings", "Open", "A typo must never stop the server from starting."],
                ["Runtime provisioner", "Open", "A failed download never blocks start-up."],
                ["Ask Execs", "Safe", "Any doubt resolves to Deny."],
                ["Database copies", "Safe", "An unclear or unchecked copy is reported as a failure."],
                ["LaTeXer bisect guard", "Safe", "When in doubt, protect the author's content."],
                ["Firmware preflights", "Safe", "Refuse rather than build or flash the wrong target."],
                ["Deleter", "Safe", "Refuses protected folders, repository roots and drive roots."],
            ]}, deck="table"),
        Section("responsibility", "RESPONSIBILITY", "Your agents, your jurisdiction",
            "Every agent is a plain-Python program so you can read, audit, edit, restrict or disable it. That "
            "transparency is a means of control, not a warranty of safety.",
            body=[
                "Agents have no independent authority. You decide whether, where, how and with which permissions "
                "they run. When you enable, configure, modify, chain or execute an agent, that execution is under "
                "your control and your jurisdiction.",
                "You are responsible for reviewing code and configuration, limiting secrets and permissions, "
                "authorizing every file, target, browser, shell, API, MCP server, machine and device an agent "
                "can reach, supervising its output and complying with the law, policies, licenses and "
                "agreements that apply.",
                "By running an agent you accept responsibility for its actions and consequences. Tlamatini's "
                "orchestration, documentation and guardrails do not authorize access to third-party systems and "
                "cannot replace your own security review, permission controls, monitoring or legal compliance.",
            ], deck="list",
            deck_points=[
                ("Readable", "Every agent is plain Python you can audit and change."),
                ("Your decision", "You choose whether, where and how an agent runs."),
                ("Your scope", "You authorize every file, target, machine and device."),
                ("Your responsibility", "Running an agent accepts its consequences."),
            ]),
        Section("datasafety", "DATA SAFETY", "Your data, handled carefully",
            "Databases, secrets and scratch files each have one well-defined path.",
            points=[
                ("WAL-safe database", "Backups read through the write-ahead log with SQLite's online backup "
                 "API and are verified with quick_check."),
                ("Staged replacement", "A new database waits in DB/ToLoad; the old one is archived with its "
                 "sidecars before Django starts."),
                ("Secrets", "Known secret fields are redacted from exported .flw files and public builds."),
                ("Private contacts", "Public builds and source snapshots carry no contact data."),
                ("Scratch files", "Temporary files stay inside the application's own Temp folder."),
                ("Passwords", "PDF passwords live in memory only."),
            ], deck="cards"),
        Section("visible", "TESTED IN THE OPEN", "Nothing runs where nobody can see it",
            "Tlamatini's development rule is that every test, build and diagnostic runs visibly, on a real "
            "desktop, where its creator can watch each step.",
            body=[
                "Browser tests run headed in real Chrome, consoles open in the foreground, and whole-desktop "
                "photographs are taken by Tlamatini's own Shoter agent — because using the agent is the test "
                "of the agent. A stale, transient or timed-out answer is never recorded as a pass.",
                "Source-derived guards stop drift before it ships: the status vocabulary, display names, dialog "
                "dismissal, catalog ordering, the Ask Execs allowlist, the self-modify gate and the frozen-bundle "
                "module proof are all checked by tests that read the real source.",
            ], deck="list",
            deck_points=[
                ("Visible", "Headed browsers and foreground consoles only."),
                ("Photographed", "Whole-desktop evidence taken by the Shoter agent."),
                ("Truthful", "Stale or timed-out results are never counted as passes."),
                ("Drift guards", "Tests read the real source to stop silent drift."),
            ]),
    ])

    running = Chapter("running", "VII", "Install, Configure, Run",
        "From a fresh Windows machine to a working assistant, and from source to a signed-off release.",
        accent="jade", sections=[
        Section("start", "GET STARTED", "Five steps to a working Tlamatini",
            "Tlamatini itself is free. The only purchase is an Ollama plan, bought directly from Ollama.",
            visual="steps",
            visual_data={"steps": [
                ("Install", "Run the release installer, which bundles Python 3.12.10, or clone the source."),
                ("Ollama", "Install Ollama for Windows."),
                ("Pro plan", "Activate Ollama Pro or higher, then run `ollama signin`."),
                ("Models", "Pull nomic-embed-text and the cloud models Tlamatini uses."),
                ("Configure", "Open Config ▸ Models and the Access Keys Wizard, then tick Multi-Turn."),
            ]},
            code=("git clone https://github.com/XAIHT/Tlamatini.git\n"
                  "cd Tlamatini\n"
                  "python -m venv venv && venv\\Scripts\\activate\n"
                  "pip install -r requirements.txt\n"
                  "python Tlamatini/manage.py migrate\n"
                  "python Tlamatini/manage.py runserver --noreload\n"
                  "# open http://127.0.0.1:8000/   (default login: user / changeme)"),
            deck="visual"),
        Section("dependencies", "DEPENDENCY COVERAGE", "Every referenced Python library is accounted for",
            "The September 27 source audit covers all 89 agents, build helpers, optional imports and tests.",
            body=[
                "The static guard scanned 743 Python files and 69 directly referenced distributions. The "
                "main requirements file contains 87 declarations; missing Autobahn, lxml, six, pip and "
                "PlatformIO declarations were added. Existing framework and compatibility pins remain.",
                "ESPHome has a separate requirements-esphome.txt manifest because its py7zr and PlatformIO "
                "pins conflict with the main environment. Keep it in its private runtime. Blender bpy, "
                "Unreal unreal, device toolchains, npm packages and model weights follow their own runtime "
                "contracts; they are not missing pip packages.",
            ],
            points=[
                ("Coverage guard", "scripts/check_requirements_coverage.py checks source and build inventories."),
                ("Verification", "Zero missing declarations; 10 guard tests and four build dependency checks passed."),
                ("Resolution", "Main and separate ESPHome dry runs passed; new dependencies passed temporary-environment smoke checks."),
                ("Limits", "Static coverage and selective smoke tests do not certify a clean installation or frozen build."),
            ], deck="cards"),
        Section("modes", "RUNTIME", "Two modes and their service ports",
            "Tlamatini runs either from source or as a frozen executable built by PyInstaller. Only path "
            "resolution differs, and `CONFIG_PATH` overrides the configuration location in both.",
            body=[
                "An installed build resolves `config.json` beside `Tlamatini.exe`; a source run uses "
                "`Tlamatini/agent/config.json`. A second, independent axis is self-modification: a build made "
                "with `--self-modify` carries her complete, rebuildable source beside the executable, and her "
                "self-knowledge travels with it. Without the flag, neither ships.",
                "Direct dictation additionally uses a private ephemeral loopback listener for its worker "
                "handshake. It closes after authentication; it is not a fourth public service or fixed port.",
            ],
            table={"columns": ["Port", "Protocol", "Service"], "widths": [0.20, 0.22, 0.58], "rows": [
                ["8000 (default)", "HTTP + WebSocket", "Web interface and chat; change it with django_port."],
                ["8765", "WebSocket", "System-Metrics MCP context provider."],
                ["50051", "gRPC", "Files-Search MCP context provider."],
            ]}, deck="split",
            deck_points=[
                ("Source", "Run from the repository with manage.py."),
                ("Frozen", "A PyInstaller executable with its own Python."),
                ("Self-modify", "Optional: her rebuildable source ships beside her."),
                ("Ports", "8000 (configurable), 8765 and 50051 on loopback."),
            ]),
        Section("settings", "CONFIGURATION", "The settings that matter most",
            "A handful of `config.json` keys shape her behaviour; everything else has sensible defaults.",
            table={"columns": ["Key", "Default", "Purpose"], "widths": [0.37, 0.16, 0.47], "rows": [
                ["django_port", "8000", "Web port for every launch path; fails open to 8000."],
                ["unified_agent_max_iterations", "4096", "Upper bound on Multi-Turn tool-loop turns."],
                ["unified_agent_llm_step_timeout_seconds", "900", "Watchdog for one model attempt."],
                ["llm_client_timeout_seconds", "600", "How long one model call may take."],
                ["ollama_repeat_penalty", "1.2", "Repetition penalty; 1.9 emptied answers."],
                ["ollama_repeat_last_n", "256", "How far back that penalty looks."],
                ["ollama_num_ctx", "1048576", "Requested context window."],
                ["binary_context_detection", "true", "Screens files by content before embedding."],
                ["console_quick_edit", "false", "Keeps a click from pausing a frozen console."],
                ["runtime_autoprovision", "true", "Lets MCP servers provision Node or uv privately."],
            ]},
            callout=("Measured, not chosen by taste",
                     "The sampler values come from repeated trials on real workloads. That failure is "
                     "heavy-tailed, so a single fast run is never a reason to change them."),
            deck="table"),
        Section("pipeline", "BUILD AND RELEASE", "From source tree to installer",
            "Three build scripts produce a standalone Windows release, and the build proves what it ships "
            "before it packages anything.",
            visual="chain",
            visual_data={"chain": ["build.py", "Frozen checks", "Uninstaller", "Installer", "pkg.zip",
                                   "Release"],
                         "caption": "Every stage verifies the one before it."},
            points=[
                ("PyInstaller bundle", "Collected static files, templates, agents, skills and helpers, with "
                 "numpy and OpenCV embedded in both shipped Pythons."),
                ("Carriage proof", "The build opens the archive it produced and aborts if a required "
                 "fail-open module is missing."),
                ("Runtime gates", "Every agent runtime and every model loader is executed inside the new "
                 "frozen executable, and the Prompt Flow Panel check runs there too."),
                ("Integrity receipt", "A SHA-256 receipt covers every payload file and is checked again when "
                 "the installer is assembled."),
                ("Size ceiling", "The final release ZIP stays under 1,990,000,000 bytes; required files are "
                 "never dropped to fit."),
            ], deck="split",
            deck_points=[
                ("Bundle", "Static files, templates, agents, skills and both Pythons."),
                ("Carriage proof", "Aborts if a required fail-open module is missing."),
                ("Runtime gates", "Every agent runtime and model loader runs frozen."),
                ("Receipt", "SHA-256 for every payload file, checked twice."),
                ("Ceiling", "Under 1,990,000,000 bytes, nothing dropped to fit."),
            ]),
        Section("update", "SELF-UPDATE", "Updating herself without losing you",
            "About ▸ Check for updates fetches the latest published release, stages it, and hands the "
            "locked-file swap to an external script.",
            body=[
                "The swap preserves `config.json`, the database, contacts, the external-MCP catalog, Temp, "
                "Templates, generated content and the separately built uninstaller. The database is copied "
                "through SQLite's online backup API before shutdown, then new migrations are applied to it on "
                "the next launch, so chat history and settings survive while new agents and prompts arrive.",
                "Downloads and staging receipts are verified before shutdown, and a failed prerequisite stops "
                "before any file is replaced. While the download runs, the update dialog is sealed and refuses "
                "to close.",
            ], deck="list",
            deck_points=[
                ("Published releases", "Only releases published on GitHub are offered."),
                ("Preserved", "Configuration, database, contacts, catalogs, content."),
                ("Migrated", "Your database receives new migrations on the next launch."),
                ("Verified", "Receipts are checked before anything is replaced."),
            ]),
        Section("versioning", "VERSIONING", "One number, from one source",
            "Tlamatini follows Semantic Versioning, with annotated Git tags as the single source of truth.",
            body=[
                "The runtime resolver, the About window, the `/agent/version/` endpoint and every build artefact "
                "report the same base tag. The reported version never carries a development or dirty suffix, "
                "and `TLAMATINI_VERSION` can document a release before its tag is cut.",
                f"This dossier reports version {version} and states the exact tag, commit and publication status "
                f"in its Release chapter.",
            ], deck="list",
            deck_points=[
                ("SemVer", "MAJOR.MINOR.PATCH from annotated Git tags."),
                ("One resolver", "version.py, the About window and /agent/version/."),
                ("Base tag only", "No .devN, +gSHA or .dirty suffix."),
                ("Override", "TLAMATINI_VERSION documents a release ahead of its tag."),
            ]),
    ])

    release = Chapter("release", "VIII", "Source and Release Status",
        f"Source tag {f['release_tag']}; latest published release "
        f"{f['release']['latest_published'] or 'unverified'}. Local changes are stated separately.",
        accent="gold", sections=[
        Section("working_voice", "LOCAL DEVELOPMENT", "Direct dictation and dependency coverage",
            "These September 27 changes are in the working tree; a source tag does not publish them.",
            body=[
                "The chat microphone starts Whisperer directly, stops on the configured silence gate, "
                "recognizes speech and submits the normal chat form. The internal worker uses the main "
                "application logger and creates no second console. Developer tests remain visibly executed.",
                "The root dependency manifest and separate ESPHome manifest now account for referenced "
                "libraries across agents and source. The static guard and detailed dependency audit record "
                "coverage and runtime boundaries. Neither this work nor the regenerated dossiers establishes "
                "that the published v1.70.0 installer contains the local microphone changes.",
            ],
            points=[
                ("User guide", "README.md and BookOfTlamatini.md explain recording, cancellation and automatic Send."),
                ("Runtime contract", "docs/chat-microphone-design.md records ownership, protocol, configuration and limits."),
                ("Dependencies", "docs/dependency-coverage-audit.md records declarations, isolation and verification."),
                ("Delivery", "Restart source runs; rebuild and validate an installer before distributing these changes."),
            ], deck="cards"),
        Section("whatsnew", "CARRIED RELEASE", "v1.70.0: the Prompt Flow Panel",
            "Version 1.70.0 is about designing conversations and editing flows with the same ease.",
            points=[
                ("Prompt Flow Panel", "Seven operations, `.fpmt` files, validated playback, isolated runs."),
                ("Panels and Config", "The canvases live under Panels; every Configure dialog under Config."),
                ("A real editor", "Undo and Redo, Duplicate with settings, zoom, Fit, agent search, Help."),
                ("Shared mechanics", "Both canvases connect, drag, select and zoom the same way."),
                ("Busy-safe menus", "Panels stays usable while she answers; one path re-arms the menus."),
                ("Context line carried", "The context meter, Context Governor and context gauge of v1.65."),
            ], deck="cards"),
        Section("lineage", "LINEAGE", "How the line arrived here",
            "Recent tags, oldest first, read from Git.",
            visual="timeline", deck="visual"),
        Section("identity_release", "RELEASE IDENTITY", "Tag, commit and publication, stated plainly",
            "A tag is not a release, and a commit after a tag is not a new tag. This dossier keeps the three "
            "apart.",
            body=f["release_statements"],
            table={"columns": ["Fact", "Value"], "widths": [0.40, 0.60], "rows": f["release_rows"]},
            deck="split", deck_points=f["release_points"]),
    ])

    facts = Chapter("facts", "IX", "Repository Facts",
        "The source tree measured: files, languages, effective lines, the largest files and recent history.",
        accent="copper", sections=[
        Section("facts_table", "INVENTORY", "The repository in numbers",
            "Counts come from Git and from the source files at the moment of generation.",
            table={"columns": ["Measure", "Value"], "widths": [0.46, 0.54], "rows": f["fact_rows"]},
            deck="table"),
        Section("languages", "LINE INVENTORY", "Effective lines by language",
            f"{f['total_effective']:,} effective lines across {f['text_files']:,} text files; "
            f"{f['total_physical']:,} physical lines.",
            visual="language_bars", deck="visual"),
        Section("language_table", "LINE INVENTORY", "Every language, counted",
            "Effective lines exclude blank lines, comment-only lines and Python docstrings.",
            table={"columns": ["Language", "Files", "Physical", "Effective", "Share"],
                   "widths": [0.34, 0.12, 0.18, 0.18, 0.18], "rows": f["language_rows"],
                   "align": ["LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"]},
            deck="table"),
        Section("authored", "PROVENANCE", "Authored and vendored",
            "Third-party frontend libraries are vendored so the application needs no CDN at runtime; their "
            "lines are counted separately here so they are never mistaken for Tlamatini's own logic.",
            table={"columns": ["Portion", "Files", "Effective lines"], "widths": [0.50, 0.20, 0.30],
                   "rows": f["provenance_rows"], "align": ["LEFT", "RIGHT", "RIGHT"]},
            deck="table"),
        Section("largest", "LARGEST FILES", "The largest source files",
            "Ranked by effective lines.",
            table={"columns": ["File", "Language", "Effective"], "widths": [0.64, 0.18, 0.18],
                   "rows": f["largest_rows"], "align": ["LEFT", "LEFT", "RIGHT"]},
            deck="table"),
        Section("commits", "HISTORY", "Recent commits",
            "The most recent commits on the inspected branch, newest first.",
            table={"columns": ["Commit", "Date", "Subject"], "widths": [0.12, 0.14, 0.74],
                   "rows": f["commit_rows"]},
            deck="table"),
        Section("method", "METHOD", "How these numbers were produced",
            "The inventory is reproducible: run the generator again and the same tree yields the same counts.",
            points=[
                ("Scope", "Every Git-tracked file plus unignored working-tree additions; ignored build "
                 "output, caches and runtime state are excluded."),
                ("Text only", "Binary assets such as images, fonts and archives are counted as files, never "
                 "as lines."),
                ("Python", "Tokenized: comments, blank lines and module, class and function docstrings are "
                 "excluded."),
                ("Other languages", "Block and line comments are stripped, then non-blank lines are counted."),
                ("No private values", "Configuration values, credentials and addresses are never reproduced."),
                ("Regenerate", "`python Tlamatini\\agent\\doc_generation\\refresh_project_docs.py`"),
            ], deck="cards"),
    ])

    return [identity, architecture, surfaces, bestiary, capabilities, trust, running, release, facts]
