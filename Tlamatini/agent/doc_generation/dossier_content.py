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
                "chat, tool calling, long context, vision and Multi-Turn planning. A smaller local model also works: "
                "a request it cannot hold is sent in Compact mode, and the Model Brain tunes every model from its "
                "maker's published settings.",
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
                 f"surface of {tools} built-in tools, self-healing steps and Compact mode for small models."),
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
                ("Chain", "The RAG, Basic or Unified-Agent chain is selected and fitted to the model."),
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
        Section("compact", "COMPACT MODE", "Every request fits the model it is sent to",
            "A model whose real window cannot hold the complete request receives a compact one; a model "
            "that can hold it receives exactly the request it always did.",
            body=[
                "Ollama does not refuse an oversized request for a local model: it keeps the end and answers "
                "from that. A local qwen2.5 whose 32,768 tokens were split between two request slots read "
                "16,386 tokens of a request of about 52,000, lost the live system metrics, and answered a "
                "CPU question with the time.",
                "Ollama's own count is now the proof. When the characters sent cannot fit the tokens Ollama "
                "says it read, the request was cut, and that count is learned as the model's real window. A "
                "local model's reported context length is never taken as its per-request window, because "
                "parallel request slots divide it.",
                "A request that fits the usable window is sent byte for byte, as before. Otherwise Compact "
                "mode keeps System-Metrics and Files-Search, whose context rides inside the question, and "
                "binds only the rows you tick. Since v1.75.0 that is a toolbar switch: ticking it unticks every "
                "Configure row but those three and pauses External MCPs, and each row shows its price. The "
                "system prompt is rebuilt by rule priority and closed by a "
                "seven-rule note, and history keeps the six newest messages. A first step that Ollama still "
                "cut is re-fitted and resent before any tool runs.",
            ],
            points=[
                ("Full", "A model that can hold the request receives it unchanged, byte for byte."),
                ("Compact", "A toolbar switch: only the rows you tick are bound, each with its price."),
                ("Locked", "A model too small for everything turns Compact on by itself and locks it."),
                ("Your choice", "`context_compact_mode` is auto by default, or always or never, obeyed exactly."),
            ],
            callout=("It fails open to the full request",
                     "Every part of the fitter fails open: when anything is uncertain, the complete request is "
                     "sent exactly as before."),
            deck="cards"),
        Section("brain", "MODEL BRAIN", "Every model tuned from formal sources",
            "Since v1.76.0 each model receives its own sampling, thinking level and context size, taken from "
            "formal sources, instead of one fixed set of values for every model.",
            body=[
                "The values come, in this order, from your own `model_brain_overrides`; a built-in knowledge base "
                "whose every profile cites its vendor model card or Hugging Face `generation_config.json` (GLM-5, "
                "DeepSeek-V4, MiniMax-M3, Gemma 4, Qwen 3.5, Qwen 2.5, gpt-oss, Kimi, Mistral Large 3 and "
                "Nemotron 3); a profile learned once, in the background, for a model she does not know yet and "
                "kept outside the installation so it survives updates; the parameters Ollama publishes for the "
                "model; and finally the model's own defaults. The requested context never exceeds what the model "
                "can really read.",
                "Inside one answer, between tool calls, a thinking model gets its own earlier reasoning back, as "
                "its maker requires, instead of starting over at every step; it is dropped between your "
                "questions, and the context gauge counts it. In Config ▸ Models, Save opens an Auto-tuning "
                "dialog that tunes every configured model in front of you, with the source of each value.",
                "The stall clocks that abandoned a slow model and started again from scratch were removed. "
                "Measured with Ollama's own numbers, reading even a very long prompt is not the bottleneck on "
                "Ollama cloud: the time is the reasoning the model generates, and a clock cannot tell a dead call "
                "from a model that is still thinking. The self-healing watchdog and the client time limit remain.",
            ],
            points=[
                ("Formal sources", "Your overrides, cited profiles, learned profiles, Ollama, model defaults."),
                ("Real context", "The requested window never exceeds what the model can read."),
                ("Reasoning kept", "Thinking models keep their train of thought between tool calls."),
                ("Auto-tuning", "Config ▸ Models ▸ Save shows each model tuned, with its sources."),
                ("No stall clocks", "A slow model is never thrown away and restarted."),
                ("Your choice", "`model_brain: off` restores the legacy fixed sampler exactly."),
            ],
            callout=("No model name in the code",
                     "A new model gets its values from the knowledge base, research, Ollama or its own defaults, "
                     "never from a branch written for one model name, and a value you set always wins."),
            deck="cards"),
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
                 "queue, so clicking the console cannot freeze her. Since v1.76.0 lines are coloured by level."),
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
            "The chat page is where you talk to her. Up to eight toolbar switches decide how each request runs.",
            body=[
                "Beside the conversation sits a canvas that shows code, text and PDFs. Paste a screenshot with "
                "Ctrl+V or drop images on the chat: she saves them to her Temp folder and writes the full path "
                "into your message, ready for Image-Interpreter. A context ring between the toolbar and the "
                "message box shows how much of the model's window the real request uses, measured by the "
                "backend in bytes. Tokens use Ollama's own prompt_eval_count for the request; an "
                "estimate is labeled until a measured count arrives. When Ollama cut a request the ring says "
                "so, and an answer built from a cut request carries a CONTEXT-WINDOW warning.",
                "Her avatar speaks answers aloud when you ask. Since v1.72.3, clearer syllable movement and "
                "faster closure make her lips easier to follow, with opening capped to her portrait. After "
                "login, pressing Enter on the welcome page takes you straight to the chat.",
                "Answer tables stay readable with every model: only a cell whose text would fall below 3:1 "
                "contrast is recoloured, while readable tables, Exec Report tables and gradient backgrounds "
                "keep their colours.",
            ],
            table={"columns": ["Switch", "What it does"], "widths": [0.24, 0.76], "rows": [
                ["Multi-Turn", "Planned, tool-calling operator mode; unchecked means direct one-shot answers."],
                ["Exec Report", "Appends per-agent execution tables; available while Multi-Turn is on."],
                ["ACPX", "Adds the twelve ACPX and Skill tools to the bound surface; off by default."],
                ["Ask Execs", "Proceed/Deny before each risky tool; a Deny stops the chain."],
                ["Step-by-Step", "One concrete action at a time, waiting for your reply before the next."],
                ["Internet", "Allows a web search to add context to the answer."],
                ["Compact mode", "Binds only the rows you tick; locked on when the model cannot hold all."],
                ["Self-modify", "Sends her self-knowledge; only in self-modify builds, locked off if too big."],
            ]}, deck="table"),
        Section("drop", "CHAT HISTORY", "Drop a message from the conversation",
            "Every message card has Drop beside Copy, for your prompts and Tlamatini's answers.",
            body=[
                "Press Drop and read the themed confirmation. Cancel starts focused, so Enter cancels by "
                "default. The red Drop button confirms deletion. Escape and the close button also cancel. "
                "The saved message disappears from the chat and the database history used for future requests.",
                "The other messages stay. Dropping only a prompt leaves its answer; dropping only an answer "
                "leaves its prompt. Remove both cards to remove the exchange. A user prompt also takes its "
                "directly following Referenced Rephrase rows, so a reload cannot show those duplicate words.",
                "Connected tabs for the same user remove the saved cards after the server confirms. A status, "
                "error or retry card without a saved message id only disappears from the current screen. "
                "The connection refuses Drop while it is answering, and a disconnected chat asks you to reconnect.",
            ],
            points=[
                ("Choose", "Drop sits beside Copy on both user and assistant message cards."),
                ("Confirm", "Cancel starts focused. Red Drop confirms; Escape and close cancel."),
                ("Remove", "Delete the saved message from chat history. Its paired prompt or answer stays."),
                ("Continue", "The next request reads the updated history without a reconnect."),
            ], deck="cards"),
        Section("drop_scope", "MEMORY AND EFFECTS", "What remains after Drop",
            "Deleting a chat card changes future conversation context. Separate saved notes and completed work remain.",
            body=[
                "Each request reloads up to eight newest AgentMessage rows through DBChatHistoryLoader, then "
                "filters status and rephrase content. No cached conversation summary or LangGraph checkpoint "
                "needs clearing. Removing a row lets the window reach an older row when one exists.",
                "An enabled External MCP memory tool stores notes separately from AgentMessage. Drop does "
                "not erase that knowledge graph; ask Tlamatini to forget the saved note too. Retained messages "
                "may also repeat a fact from a deleted card, so Drop is not a guarantee of complete forgetting.",
                "Files created, messages sent, agent runs and Exec Report rows remain real completed work. "
                "Dropping their prompt or answer cannot undo those effects. A Create Flow button belongs to "
                "its answer card and disappears with it, so download a needed .flw before deleting the card.",
            ],
            points=[
                ("History", "Every request reloads a window of up to eight newest database rows."),
                ("Saved notes", "External MCP memory is separate. Ask her to forget its note too."),
                ("Other messages", "The paired answer or prompt stays and may repeat the same information."),
                ("Completed work", "Files and sent messages remain. Save a needed flow before dropping its card."),
            ], deck="cards"),
        Section("dictation", "DIRECT VOICE INPUT", "Speak beside Send",
            "The microphone captures first; no model tool-selection step stands between the click and recording.",
            body=[
                "Click Mic beside Send, wait for Listening, and speak into the microphone on the "
                "Tlamatini host. Real input level, elapsed time and the silence countdown stay in the chat. "
                "After the configured silence window (shipped default 3.5 seconds), recognition runs and the "
                "text is appended to the existing draft. Config > Mic selects automatic normal-form submission "
                "or an editable draft for manual Send.",
                "Review mode starts no task until Send. A second click or Escape cancels; empty or failed "
                "recognition sends nothing. Current modes and permission behavior remain in force. "
                "The avatar acknowledges dispatch through browser speech and respects Silent mode.",
            ],
            points=[
                ("Click", "Direct Whisperer start; the host microphone opens only for a recording."),
                ("Listen", "Live samples drive the in-chat indicator and the configured silence gate."),
                ("Recognize", "Local faster-whisper or the explicitly configured cloud speech engine."),
                ("Send or review", "Submit once with current modes, or review the editable draft and press Send yourself."),
            ], deck="cards"),
        Section("micsettings", "CONFIGURATION", "Config ends with Mic",
            "Choose automatic Send or an editable draft, using the same dialog style as the rest of Tlamatini.",
            body=[
                "The button label is Mic. Config > Mic follows Voice and controls what happens after recognition. "
                "Send automatically is the default. Keep in the chat input restores editing without launching "
                "a task or processing acknowledgment; correct the words, then press Send.",
                "Preferences are saved in this browser for the next recording. Each recording owns a snapshot. "
                "Unset fields inherit the current Whisperer template; Reset then Save restores that inheritance. "
                "Cancel, close and Escape discard unsaved edits; outside clicks leave the dialog open. "
                "Config > Voice controls avatar playback; Config > Models > Speech selects the recognizer.",
            ],
            points=[
                ("Input", "Configured/default/listed host device, refresh and software gain from 0 to 300%."),
                ("Sound gate", "Silence 0.3-20 seconds, cap 5-600 seconds, adaptive or manual sensitivity."),
                ("Recognition", "Language, English translation, capture rate/channels, local beam size and VAD."),
                ("Guardrails", "Validate settings before capture; removed or ambiguous saved devices cannot silently change inputs."),
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
                ("Configuration", "Model/template inheritance plus validated, per-recording Mic capture overrides."),
                ("Boundary", "The direct button is input, not a wrapped tool or an Exec Report row."),
                ("Release", "Ship consumer/runtime/settings modules, carried validator and worker, Mic JS/CSS and template."),
            ], deck="cards"),
        Section("dictationevidence", "VERIFICATION SCOPE", "Measured source behavior",
            "Dated source checks are evidence, not a claim that an older installer contains the change.",
            body=[
                "On September 27, 2026, 108 voice regressions and 42 existing dialog-theme tests passed. "
                "The worker refreshed 16 host inputs and restarted twice without extra windows or focus changes. "
                "Earlier real host capture yielded samples in 297 ms after direct start; "
                "cancellation and normal worker exit were observed. Two startup/shutdown cycles created "
                "no additional visible windows and left foreground focus unchanged.",
                "The updated headed-browser suite passed 62 controlled-transport checks, including both modes, "
                "settings persistence, shared control styles and narrow layouts. Earlier cached "
                "recognition of a 5.768-second synthetic speech file took 0.203 seconds, versus 11.094 "
                "seconds on first decode. These are separate observations, not end-to-end latency guarantees. "
                "No new live Ollama task or rebuilt installer was certified by those checks.",
            ],
            points=[
                ("Current source", "108 voice regressions, 42 theme tests and real worker metadata/lifecycle probes."),
                ("Browser evidence", "62 headed checks with controlled transport; separate from live ASR."),
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
                 "Voice, then Mic (dictation behavior and capture preferences)."],
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
            "The Prompt Flow Panel turns a chain of prompts into a diagram of seven operations plus static "
            "review notes, saved as a portable `.fpmt` file and played against your configured models.",
            visual="operations",
            visual_data={"ops": [
                ("prompt", "Prompt", "Sends its text to the model; Multi-Turn and ACPX can be enabled."),
                ("programmed", "Programmed Prompt", "Waits for a scheduled time or a delay, then sends."),
                ("decision", "Decision", "Takes Yes or No from the last answer, or asks you."),
                ("feed", "Feed embeddings", "Adds reference text to this run's retrieval context."),
                ("flush", "Flush embeddings", "Clears the run's retrieval context."),
                ("clean", "Clean History", "Clears the run's conversation and last output."),
                ("input", "User Input", "Stops to ask you something; your reply joins the run."),
                ("commentary", "User Commentary", "A static speech-bubble note for reviewers; it never runs."),
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
                "start. Opening a file never runs it, and a User Commentary note never runs at all.",
                "Feed embeddings requires a real vector store. A provider error cannot become success "
                "through the chat stack's prompt-only fallback, including with tools enabled. The flow "
                "reports failure before its next operation and keeps any previously accepted context.",
            ],
            points=[
                ("Format", "JSON `tlamatini-prompting-flow`, version 2; version 1 files migrate."),
                ("Limits", "5 MiB, 500 assets, 1,000 connections."),
                ("Isolation", "Empty history and embeddings at every start."),
                ("Validation", "Checked in the browser and again on the server."),
                ("Not .pmt", "Plain-text system prompts keep .pmt and are refused."),
                ("Drafts", "Kept per user in browser storage."),
            ], deck="cards"),
        Section("pfpnotes", "STATIC REVIEW NOTES", "Writing and formatting a commentary",
            "User Commentary is a review note on the canvas. User Input is the operation that pauses "
            "playback for a reply, using the notched figure.",
            body=[
                "Double-click a bubble or press Enter to write directly in it. Select words or paragraphs, "
                "then use the floating mini toolbar for font, size, text color, bold, italic and underline. "
                "For example, one bubble can have a large Verdana heading, an italic Arial sentence and a "
                "Georgia paragraph. With only a caret, formatting applies to subsequent typing. Outside "
                "editing, it applies to the whole selected note. Bubble color and alignment affect the note.",
                "Drag any of the eight borders or corners to resize, even while writing. The handles also "
                "accept arrow keys. Fit text removes spare height, and the bubble grows to contain all "
                "wrapped text. There are no internal scrollbars, numeric size fields or commentary "
                "configuration dialogs.",
                "Done or Ctrl+Enter saves the complete edit. Cancel or Escape restores its original text, "
                "styles, dimensions and position. Ctrl+Z/Y works inside the editor. Completed edits, moves, "
                "resizes and duplicates participate in the diagram's Undo/Redo. Copying between comment "
                "editors preserves formatting. External clipboard text stays literal.",
            ], deck="list", deck_points=[
                ("Write in place", "Double-click or Enter edits the bubble. No configuration dialog or numeric dimensions."),
                ("Mixed styles", "Floating toolbar: font, size, text color, bold, italic and underline for each passage."),
                ("Selection or caret", "Format selected text or subsequent typing; outside editing, format the whole note."),
                ("Direct sizing", "Drag any edge/corner, even while writing. Fit text removes spare height. No internal scrollbars."),
                ("Finish or restore", "Done/Ctrl+Enter saves; Cancel/Escape restores text, styles and geometry. Editor and flow Undo/Redo."),
            ]),
        Section("pfpfiles", "PORTABLE FLOW FILES", "Comments survive save, open and draft recovery",
            "Version 2 .fpmt files retain independent notes with their full text, formatting and geometry.",
            body=[
                "Each note stores allowlisted text runs plus matching literal text. Runs carry font, size, "
                "text color, bold, italic and underline. Older plain version 2 notes normalize to one run. "
                "Version 1 executable commentary migrates to User Input with its identifiers, connections, "
                "settings and reply/cancellation behavior intact. Opening a file never starts playback.",
                "A note has no connection ports or Start state and never enters model context, conversation "
                "history or playback step counts. Tokens such as {{last_output}} and HTML-like text remain "
                "literal in a comment. Several independently styled notes can share a diagram.",
                "The per-user browser draft keeps the existing .draft.v1 key for compatibility. Portable "
                "files retain the .fpmt extension. The similarly named .pmt files belong to system prompts "
                "and remain a separate format. Limits are 5 MiB per flow, 500 assets, 1,000 connections, "
                "100,000 characters and 10,000 formatted runs per note.",
            ], deck="list", deck_points=[
                ("Version 2", "Literal text and allowlisted runs preserve mixed formatting."),
                ("Older files", "Plain v2 notes normalize. Version 1 reply steps become User Input with IDs, edges and settings intact."),
                ("Static isolation", "No ports, Start or execution steps. Text stays literal and never enters context or history."),
                ("Recovery", "Independent notes retain text, styles and geometry. Opening never plays the flow; draft key stays compatible."),
            ]),
        Section("flowopen", "OPENING FLOW FILES", "The right editor, from chat or Windows",
            "October 4 source changes: .flw opens agents; .fpmt opens prompting flows. Opening never runs them.",
            body=[
                "The main chat routes both formats into their own editor tabs and keeps its current document. "
                "An external file launch validates a bounded snapshot and reuses a matching running server "
                "before any database startup work. A cold launch starts the application on its configured port.",
                "Login returns to the requested file. Short-lived, single-use opening links carry a random "
                "token rather than a filesystem path; browser uploads are bound to the signed-in user. "
                "Invalid formats, unsupported versions and files over 5 MiB are rejected before replacement.",
                "Unsaved diagrams and recovered drafts require confirmation. Rich commentary runs retain "
                "their fonts, styles and layout through .fpmt save/open. Agent-flow opening now awaits "
                "validation and session preparation; failed credential redaction blocks unsafe .flw downloads.",
            ],
            points=[
                ("From chat", "Open either flow in its editor and keep the chat document."),
                ("From Windows", "Start once or reuse the running app; return through login."),
                ("Preserve work", "Validate before replacement; confirm unsaved changes."),
                ("No automatic run", "Opening prepares the diagram. Play remains a user action."),
            ], deck="cards"),
        Section("flowwindows", "WINDOWS FILE TYPES", "Register, repair and remove both formats",
            "Per-user associations, installation ownership and Windows default-app choices.",
            body=[
                "A shared PowerShell helper registers .flw and .fpmt with separate ProgIDs, friendly names, "
                "icons, Open With entries and Default Apps capabilities. Status reports the current registration; "
                "DefaultApps opens Windows Settings so the user can choose a default.",
                "Installation registers both formats. Update Repair preserves explicit unregistration and never "
                "takes another installation's owned entry. Removal deletes only this installation's values, "
                "preserving Windows UserChoice and other applications' Open With entries. Historical .flw "
                "wrappers cover both formats so existing installer/uninstaller binaries remain compatible.",
                "The scripts and opening modules are included in frozen and self-modify packaging. Native "
                "registry checks use an isolated test key, and visible Chrome tests exercise real file opening "
                "and login. The October 4 release campaign also rebuilt local main and uninstaller executables. "
                "The work was committed to main that day and is carried by the v1.76.0 tag; compiled acceptance is "
                "recorded separately from source tests. "
                "See docs/windows-flow-files.md for commands, contracts and verification.",
            ],
            points=[
                ("Install", "Register both types with names, icons and the correct editor destinations."),
                ("Administer", "Inspect Status, register or remove one type, or open Default Apps."),
                ("Update", "Repair owned entries without undoing the user's opt-out."),
                ("Uninstall", "Remove owned registrations; keep other apps and user documents."),
            ], deck="cards"),
        Section("uninstallworkers", "WINDOWS LIFECYCLE", "Remove the application and its owned workers",
            "Confirmation, installation ownership, retryable errors and preserved user content.",
            body=[
                "The real installer registration failure came from an omitted InstallDir whose parameter "
                "default evaluated before Windows PowerShell populated PSScriptRoot. The wrappers now "
                "resolve that default inside the script. Fresh powershell.exe -File tests exercise the "
                "same entry point from an unrelated working directory.",
                "The uninstaller first requires the main application to close. After confirmation it stops "
                "workers belonging to the selected installation and their descendants. Exact path boundaries, "
                "creation times and inherited TLAMATINI_AGENTS_ROOT identify agent children even after "
                "reparenting; unrelated processes and Explorer remain running.",
                "A temporary independent copy allows the installed uninstaller itself to be removed. "
                "Helpers and the installation marker remain until file and owned-registry removal succeed, "
                "so a partial failure can be retried. Locked files and denied registry deletion report failure. "
                "Drive roots, shared folders, source checkouts and redirected targets are rejected.",
                "Since v1.76.0, when Windows still holds Uninstaller.exe itself, the file is retried, moved aside "
                "and removed by a hidden cleanup after the uninstaller exits, so the uninstall finishes cleanly.",
                "Agents and nonempty user-content directories remain under the existing preservation contract. "
                "A full directory/registry reset is a separate authorized action. Verification distinguishes "
                "real compiled GUI outcomes from backend tests and records any blocked native launch explicitly.",
            ], deck="cards", points=[
                ("Installer entry points", "Resolve the installation directory inside PowerShell script bodies."),
                ("Owned workers", "Stop this installation's agents and surviving descendants after confirmation."),
                ("Honest retry", "Retain removal support until success; report locked files and registry errors."),
                ("Preserve user work", "Keep agents and nonempty content; notify the shell without restarting Explorer."),
            ]),
        Section("release_repair", "LOCAL RELEASE VALIDATION", "Repair the boundary, then repeat the real operation",
            "The October 4 repairs, now carried by v1.76.0, have separate source, frozen, package and visual "
            "evidence.",
            body=[
                "The visible campaign checks the actual installer, Windows associations, authenticated "
                "file opening, administration, main chat and both flow panels. It also compares several "
                "rich comments across repeated file writes and reads, executes local agents, and audits "
                "owned workers after shutdown. A configuration dialog opening is not proof that a "
                "hardware or external-service agent executed successfully.",
                "System-Metrics and Files-Search now honor the effective configuration and nondefault "
                "ports, including UTF-8 BOM files. The path-security and chat-chain readers accept the same "
                "encoding without weakening directory boundaries. Both auxiliary context chains use the same "
                "effective paths and endpoints; system sockets close after each request and file RPCs have deadlines. "
                "Parametrizer restores connections when a saved file "
                "contains mappings without explicit connection lists. Model-free agents avoid unrelated "
                "model-setting reads. Numeric messaging identifiers keep the same string/integer "
                "contract in public and keyed templates.",
                "A rejected embedding request must fail the flow before its next operation. The campaign's "
                "provider returned HTTP 401; this is recorded as a blocked capability with a tested failure "
                "path. The desktop-control tool also blocked the compiled uninstaller launch. Backend "
                "cleanup tests do not certify its unobserved native confirmation and completion screens.",
                "Detailed results and retained failed attempts are in "
                "docs/changes/2026-10-04-release-validation.md. The review profile requested by Angela "
                "lists each changed file and code segment. The work was committed on October 4 and is carried by "
                "the v1.76.0 tag.",
            ], deck="cards", points=[
                ("Real user paths", "Installer, login, Admin, chat, both panels and Windows file opening."),
                ("File fidelity", "Mixed styles, geometry and rendered text checked across save/open cycles."),
                ("Runtime boundaries", "Configured MCP endpoints, agent defaults, mappings and identifier types."),
                ("Explicit limits", "Provider failure and blocked native launch remain visible in the verdict."),
            ]),
        Section("pfpoutput", "RUN OUTPUT", "More room for the canvas or the log",
            "Drag the horizontal divider above Run output to give it 5% to 95% of the available pane height.",
            body=[
                "The percentage uses the combined canvas and output height, excluding headers, the status "
                "strip and the divider. The initial allocation is 20%. The canvas and Run output each keep "
                "their own scrollbar. Moving the divider preserves canvas zoom, node dimensions and text "
                "size. The Operations bar keeps its separate horizontal sizing control.",
                "Tab to the divider and use Up/Down for one percentage point, or Shift+Up/Down for five. "
                "Home selects 5% and End selects 95%. Escape ends a drag. Click the Run output heading to "
                "collapse it. Reopening restores the chosen height, and resizing the window retains the ratio.",
                "The browser remembers the output height per signed-in user. This layout preference does "
                "not modify a flow file, mark the diagram as edited or add an Undo step. Resizing the panel "
                "also leaves the run and its output unchanged.",
            ], deck="list", deck_points=[
                ("5% to 95%", "Share of canvas/output height, excluding headers, status and divider. Initial share: 20%."),
                ("Stable content", "Independent scrolling. Canvas zoom and text sizes stay unchanged."),
                ("Keyboard", "Up/Down: 1 point; Shift: 5. Home: 5%; End: 95%. Escape ends the drag."),
                ("Remembered layout", "Collapse/reopen and window resizing retain the ratio. Saved per user, outside flow files and Undo/Redo."),
            ]),
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
                "A second account signed in from the same browser takes over every open tab, while an open chat "
                "keeps its first account, so loading is refused. Since v1.76.0 the message names that cause and "
                "the fix, reloading with F5, the header comes back and the progress dialog marks the failed step.",
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
                "next configuration load. The model list comes from the configured Ollama servers, asked by "
                "the backend with their token, so a remote server's models are offered and accepted. Since v1.76.0 "
                "Save also opens the Model Brain's Auto-tuning dialog, which tunes each configured model in front "
                "of you and names the source of every value.",
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
                ("Save", "Keeps unrelated settings, downloads nothing, then auto-tunes each model."),
                ("Catalog", "Listed by the configured Ollama servers, asked with their token."),
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
                 "convergence; readable diagnostics; an eight-rung repair ladder; a mostly-cut build delivered as "
                 "`<name>.DEGRADED.pdf`; MiKTeX recommended."],
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
                "Since v1.76.0 a PDF is reported only when the delivered file really exists. A build that had to "
                "cut a quarter or more of its body is delivered as `<name>.DEGRADED.pdf`, never under the name you "
                "asked for, and in a document over 8,000 characters the model rung first repairs only the lines "
                "around the compiler's error with a capped request; a reply that never came forbids bisect.",
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
                "written confirmation under those catalog instructions. Config > Mic selects automatic submission "
                "or an editable draft. Actual dispatch uses browser speech for acknowledgment, respecting Silent mode.",
            ], deck="list",
            deck_points=[
                ("Sound gate", "Records while you talk; stops after 3.5 s of silence."),
                ("Workflow duration", "Standalone/workflow recording can use an explicit fixed duration."),
                ("Local first", "faster-whisper on GPU or CPU, or a cloud provider."),
                ("Her voice", "Female only: tara, leah, jess, mia or zoe."),
                ("Direct microphone", "Gate, recognize, then send or keep an editable draft; no extra console."),
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
        Section("web", "WEB SEARCH", "Three search tiers, one time budget",
            "The chat search tool and pool agent use the same Googler implementation, with a default "
            "120-second budget and explicit outcomes.",
            body=[
                "With no engine pinned, six plain-HTTP routes race for relevant results. If none answers, "
                "real installed Chrome uses a persistent profile across eight browser routes. Open knowledge "
                "sources form the final tier: Wikipedia, arXiv, OpenAlex, Hacker News, GitHub, Internet Archive "
                "and Project Gutenberg. The log names the answering engine and tier.",
                "A shared health ledger rests refusing engines for 3, 10 or 30 minutes; an off-topic result "
                "is rejected, and a refusing route is not asked again in the same run. Blocked, timed out, "
                "unreachable and no matches are separate outcomes. The chat wrapper supports Cancel and "
                "enforces a process deadline with a cleanup allowance.",
                "Structured dorks retain presets, grouped filters and links_only URL delivery. An explicit "
                "engines list skips the HTTP and open-source tiers. Pin Google when Google-only operators "
                "matter; fallback engines may broaden their meaning. Licensing and authorization remain yours.",
            ], deck="list",
            deck_points=[
                ("Tier 0", "Six hedged HTTP routes; relevance checked before acceptance."),
                ("Tier 1", "Eight browser routes in health-ledger order; persistent Chrome profile."),
                ("Tier 2", "Clearly attributed open knowledge sources when search routes fail."),
                ("Bounded work", "120-second default, cancellation and named failure outcomes."),
                ("Dork contract", "Explicit engines skip fallback tiers; links_only delivers URLs."),
            ]),
        Section("crawler_current", "WEB READING", "Read the requested page, report what happened",
            "Crawler starts with the supplied page, bounds its work and keeps refusal pages away from the model.",
            body=[
                "The default crawl_type is page, with include_seed enabled. A range crawl defaults to "
                "25 pages and a 900-second whole-run budget. Each download has a 45-second default wall-clock "
                "limit and an 8,000,000-byte cap. These are configurable defaults; zero disables the page "
                "count or whole-crawl limit, so unlimited operation must be a deliberate choice.",
                "Headers are read case-insensitively. Bot walls, CAPTCHA pages and access refusals are "
                "reported before analysis; timeouts and unreachable pages remain named outcomes. If nothing "
                "was analyzed, the final report says so. Crawler reads fetched HTML; it does not execute JavaScript.",
                "Since v1.72.4, both Crawler and Googler use a stack of skipped HTML regions, handle omitted "
                "head endings and self-closing tags, and compare the extraction with a plain-text fallback. "
                "When that fallback has at least 200 characters and the parser kept less than 25 percent, "
                "the fallback takes over. Crawler warns in its log; Googler returns an extraction_note. "
                "Parser exceptions also use the fallback; healthy extractions stay unchanged.",
            ], deck="cards",
            points=[
                ("Page first", "Read the seed URL by default; range crawling is explicit."),
                ("Budgets", "Defaults: 25 pages, 900 seconds overall, 45 seconds per download."),
                ("Truthful outcome", "Refusals never become source content; no analysis is reported plainly."),
                ("Text safety net", "Below 25% of a 200+ character fallback: recover and disclose."),
            ]),
        Section("network_measurement", "NETWORK MEASUREMENT", "Speed measured with its error bar",
            "NetSpeed-Calculator publishes a speed with a confidence interval and measures latency under load.",
            body=[
                "Several keyless providers run in parallel. The measurement discards the TCP slow-start "
                "ramp, samples throughput as a derivative, rejects outliers and fuses providers with a "
                "random-effects meta-analysis. It grades bufferbloat from A+ to F. A full run transfers about "
                "100 to 200 MB, so it asks before running.",
            ], deck="list",
            deck_points=[
                ("Throughput", "Parallel streams, Student-t intervals, random-effects fusion."),
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
                ["Compact-mode fitter", "Open", "Any doubt sends the complete request, exactly as before."],
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
            "The October 1 static coverage check includes all 89 agents, build helpers, optional imports and tests.",
            body=[
                "The refreshed static guard scanned 762 Python files and 69 directly referenced distributions. The "
                "main requirements file contains 87 declarations; missing Autobahn, lxml, six, pip and "
                "PlatformIO declarations were added. Existing framework and compatibility pins remain.",
                "ESPHome has a separate requirements-esphome.txt manifest because its py7zr and PlatformIO "
                "pins conflict with the main environment. Keep it in its private runtime. Blender bpy, "
                "Unreal unreal, device toolchains, npm packages and model weights follow their own runtime "
                "contracts; they are not missing pip packages.",
            ],
            points=[
                ("Coverage guard", "scripts/check_requirements_coverage.py checks source and build inventories."),
                ("Verification", "October 1: no missing declarations, syntax errors or unreviewed dynamic imports."),
                ("Earlier evidence", "September 27: main/ESPHome dry runs and temporary-environment dependency smoke checks passed."),
                ("Limits", "Static coverage and selective smoke tests do not certify a clean installation or frozen build."),
            ], deck="cards"),
        Section("modes", "RUNTIME", "Two modes and their service ports",
            "Tlamatini runs either from source or as a frozen executable built by PyInstaller. Only path "
            "resolution differs, and `CONFIG_PATH` overrides the configuration location in both.",
            body=[
                "An installed build resolves `config.json` beside `Tlamatini.exe`; a source run uses "
                "`Tlamatini/agent/config.json`. A second, independent axis is self-modification: a build made "
                "with `--self-modify` carries her complete, rebuildable source beside the executable, and her "
                "self-knowledge travels with it. Without the flag, neither ships. A source run is always "
                "self-able, and a toolbar Self-modify switch decides per request whether her self-knowledge "
                "is sent; it locks off when the model cannot hold it.",
                "Direct dictation additionally uses a private ephemeral loopback listener for its worker "
                "handshake. It closes after authentication; it is not a fourth public service or fixed port.",
                "Both MCP services honor their configured hosts and ports in source and frozen mode; "
                "their client URIs must match. Files-Search also honors its worker count and bounds RPC "
                "waits. UTF-8 BOM configuration files and CONFIG_PATH overrides are supported by both clients.",
            ],
            table={"columns": ["Port", "Protocol", "Service"], "widths": [0.20, 0.22, 0.58], "rows": [
                ["8000 (default)", "HTTP + WebSocket", "Web interface and chat; change it with django_port."],
                ["8765 (default)", "WebSocket", "System-Metrics MCP; match server port and client URI."],
                ["50051 (default)", "gRPC", "Files-Search MCP; match server port and client URI."],
            ]}, deck="split",
            deck_points=[
                ("Source", "Run from the repository with manage.py."),
                ("Frozen", "A PyInstaller executable with its own Python."),
                ("Self-modify", "Always from source; optional in a build; a switch sends it."),
                ("Ports", "Defaults: 8000, 8765 and 50051; configure clients and servers together."),
            ]),
        Section("settings", "CONFIGURATION", "The settings that matter most",
            "A handful of `config.json` keys shape her behaviour; everything else has sensible defaults.",
            table={"columns": ["Key", "Default", "Purpose"], "widths": [0.37, 0.16, 0.47], "rows": [
                ["django_port", "8000", "Web port for every launch path; fails open to 8000."],
                ["unified_agent_max_iterations", "4096", "Upper bound on Multi-Turn tool-loop turns."],
                ["unified_agent_llm_step_timeout_seconds", "900", "Watchdog for one model attempt."],
                ["llm_client_timeout_seconds", "600", "How long one model call may take."],
                ["model_brain", "auto", "Tunes each model from formal sources; off restores the legacy sampler."],
                ["ollama_repeat_penalty", "1.2", "Legacy sampler, sent only when model_brain is off."],
                ["ollama_num_ctx", "1048576", "Legacy requested window; the brain clamps it to the real one."],
                ["context_sidecar_llm_timeout_seconds", "60", "Time limit on the context helpers' own model calls."],
                ["context_compact_mode", "auto", "Compact mode locks on for models that cannot hold everything."],
                ["binary_context_detection", "true", "Screens files by content before embedding."],
                ["console_quick_edit", "false", "Keeps a click from pausing a frozen console."],
                ["console_colors", "true", "Colours console lines by level; the log stays plain text."],
                ["runtime_autoprovision", "true", "Lets MCP servers provision Node or uv privately."],
            ]},
            callout=("Measured, not chosen by taste",
                     "The legacy sampler comes from repeated trials on real workloads, and one fast run never "
                     "justifies a change. "
                     "The Model Brain now tunes each model from formal sources."),
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
                ("Receipt", "SHA-256 for every payload file and all required root helpers, checked before use."),
                ("Ceiling", "Under 1,990,000,000 bytes, nothing dropped to fit."),
            ]),
        Section("root_carriage", "BUILD REPAIR · SEPTEMBER 27", "One inventory ships every required helper",
            "A September 27 repair, carried since v1.72.1, ships the Whisperer settings helper without weakening package verification.",
            body=[
                "A build correctly refused a runtime receipt because chat_voice_settings.py was missing. "
                "The verifier required the loose helper, but build.py used a separate copy dictionary that "
                "omitted it. Compiling agent.chat_voice_settings does not satisfy the standalone Whisperer "
                "worker running under the carried Python.",
                "build.py now calls copy_root_sources using the verifier's ROOT_SOURCES inventory. All "
                "inputs are checked before copying. Every mapped destination is mandatory in both ZIP and "
                "extracted-stage receipts, so removing a required file and its receipt entry still fails. "
                "The pre-freeze hash baseline continues to reject source changes during a build.",
            ],
            points=[
                ("One carrier", "Copy and verification share ROOT_SOURCES; a new required helper needs no second list."),
                ("Worker import", "Carry chat_voice_settings.py at the installation root as well as compiling the Django module."),
                ("Integrity", "Reject missing, edited or unmanifested files, including otherwise consistent incomplete receipts."),
                ("Rebuild inputs", "Mirrored self-update/self-modify sweeps include the shared inventory and report omitted Git checks."),
            ], deck="cards"),
        Section("carriage_evidence", "RECORDED VERIFICATION", "Packaging evidence and its limits",
            "The September 27 file-level checks establish carriage and integrity; a full installer is a separate verification.",
            body=[
                "The recorded focused suite ran 146 tests: 145 passed and one Git-dependent census was skipped. "
                "It exercised the real carrier with source files, imported the worker from a staged installation, "
                "and verified ZIP creation, extraction and receipts with synthetic runtime binaries. "
                "Missing or corrupted helpers and extra files were rejected.",
                "The recorded self-update sweep with --no-git had no findings. A self-modify snapshot copied "
                "1,579 files with zero copy errors and accounted for all 778 runtime source inputs. "
                "These are that audit's dated counts. Neither those checks nor this dossier regeneration ran "
                "a complete PyInstaller build, installed a release or performed a live update swap.",
            ],
            points=[
                ("Focused suite", "146 tests recorded: 145 passed, one skipped; file-only harness exited successfully."),
                ("Real files", "Every mapped source destination matched; the staged worker resolved its settings helper."),
                ("Snapshot", "Recorded audit: 1,579 files, 11 redacted, 778 runtime inputs covered, zero copy errors."),
                ("Evidence", "docs/build-root-assets-verification.md records scope, skipped checks and local transcripts."),
            ], deck="cards"),
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

    release = Chapter("release", "VIII", "Version and Release Status",
        (f"Version {f['release_tag']}, the current release, published on GitHub."
         if f['release']['latest_published'] == f['release_tag'] else
         f"Version {f['release_tag']}; the latest release published on GitHub is "
         f"{f['release']['latest_published'] or 'not verified'}."),
        accent="gold", sections=[
        Section("working_firstperson", "NEW IN v1.77.0", "She speaks to you, by name",
            "Tagged on October 9 and published as the current release, so self-update delivers it.",
            body=[
                "Every fixed line Tlamatini sends to the chat, and that her avatar reads aloud, is now written in the "
                "first person and addressed to the user by name: “I'm ready, Angela! You can start chatting with me "
                "now.” replaces “Your agent is ready.” The lines live in one place, `agent/constants.py`; a helper "
                "fills in the first name, or the user name when there is no first name, and leaves the name out "
                "cleanly when there is neither.",
                "Some of these lines are recognised by their words: the chat page uses them to know it is busy or "
                "ready, the avatar to decide what to say, and the Telegram bridge to filter its replies. Every one "
                "of those matchers changed in the same commit and still accepts the old wording, so a saved chat "
                "history and an older server still read correctly.",
                "The uninstaller no longer erases the user's own work. Uninstalling an installation had deleted the "
                "projects kept in `Templates/`, where STM32er, ESP32er, Arduiner, ESPHomer, Unrealer and LaTeXer "
                "create their projects by default. It now keeps `application`, `applications`, `content_generated`, "
                "`context_files`, `doc_generated` and `Templates` whenever they hold a file, always erases `Temp/`, "
                "and still keeps `agents/`. Only a rebuilt Uninstaller.exe carries this: a fresh install or a "
                "reinstall copies it, while an in-app update keeps the old one.",
                "Both changes are covered by unit tests (the message tests in `test_compact_mode_switch.py` and "
                "`test_uninstaller_mechanics.py`), which passed again in this documentation refresh.",
            ],
            points=[
                ("First person", "Fixed chat lines say “I” and use your name."),
                ("One source", "Every fixed line lives in agent/constants.py."),
                ("Old wording kept", "Matchers accept both, so old histories still read."),
                ("Templates kept", "Uninstalling keeps the projects in Templates/."),
                ("Temp erased", "Scratch goes; folders holding your files stay."),
                ("Rebuilt uninstaller", "A reinstall carries the fix; an in-app update does not."),
            ], deck="cards"),
        Section("working_brain", "NEW IN v1.76.0", "The Model Brain tunes every model",
            "Tagged on October 8; the Model Brain commit lands on main one commit after the tag. The published "
            "v1.76.0 release was built from main and carries it.",
            body=[
                "Every model Tlamatini calls now receives its own sampling, thinking level and context size from "
                "formal sources, as the How She Works chapter describes. Config ▸ Models ▸ Save opens an "
                "Auto-tuning dialog that tunes each configured model in front of you, thinking models keep their "
                "own reasoning between tool calls inside one answer, and the stall clocks that threw finished work "
                "away are gone.",
                "The console window paints each line by level: errors red, fatal errors white on red, warnings "
                "yellow, debug grey and successes green, while `tlamatini.log` stays plain text. At startup she "
                "logs which program draws the window, the classic console or Windows Terminal, the default on "
                "Windows 11. `console_colors` and the standard `NO_COLOR` variable turn the colours off.",
                "Two smaller repairs ship beside it. A PDF refused because a second account signed in from the "
                "same browser now names that cause and the fix, reloading with F5, and the progress dialog marks "
                "the failed step. Two chat pages on two different models no longer make each other measure again "
                "forever: a model's verdict updates the boxes and stops. On two idle test pages the re-sends fell "
                "from 1,081 in one minute to none.",
                "On October 8 the visible Model Brain test passed 25 of 25 checks in a source run and the visible "
                "PDF-account test passed 20 of 20. These are dated results, not a claim that this documentation "
                "refresh reran them. Publication status is stated in the Release Identity section.",
            ],
            points=[
                ("Model Brain", "Per-model settings from cited sources; Auto-tuning shows each one."),
                ("Reasoning kept", "Thinking models keep their train of thought between tool calls."),
                ("Coloured console", "Lines coloured by level; the log file stays plain text."),
                ("Truthful refusal", "A PDF refused for a second account says why and how to fix it."),
                ("Quiet tabs", "Two pages on two models no longer re-measure each other."),
                ("Evidence", "25 of 25 and 20 of 20 visible checks on October 8."),
            ], deck="cards"),
        Section("working_truth", "NEW IN v1.76.0", "Documents and files that tell the truth",
            "October 7 and 8: LaTeXer, Mover and the document agents report what really happened.",
            body=[
                "LaTeXer reports a PDF only when the delivered file really exists and is not empty, and a PDF whose "
                "text sticks out more than five points past the margin is reported as created with findings, not "
                "as clean. When it had to cut a quarter or more of a broken document's body to produce any PDF at "
                "all, it saves the result as `<name>.DEGRADED.pdf` and leaves the requested name untouched. In a "
                "document longer than 8,000 characters the model rung first repairs only the lines around the "
                "compiler's error with a capped request; an unusable reply falls back to the whole-document "
                "request, and a reply that never came forbids the bisect rung.",
                "Mover no longer erases a destination folder to copy into it: folders are merged, each file is "
                "staged and published whole, a move removes its source only afterwards, and a failure ends with a "
                "failure receipt and a non-zero exit instead of a success. Document and capture agents keep a "
                "finished file when Windows Controlled Folder Access blocks the folder, and the security whitelist "
                "script now finds every Tlamatini installation and lets its Python save files.",
                "The October 8 LaTeXer change added 37 tests, and all 549 LaTeXer tests passed with it. The October "
                "7 Mover and LaTeXer delivery work passed 126 focused tests.",
            ],
            points=[
                ("Real PDFs", "Success only when the delivered file exists and is not empty."),
                ("Layout findings", "Text past the margin is reported, never called clean."),
                ("DEGRADED name", "A mostly-cut build never wears the name you asked for."),
                ("Region repair", "Large documents: the lines around the error are repaired first."),
                ("Mover", "Destinations are merged, never erased; failures are reported."),
                ("Protected folders", "Finished files survive Controlled Folder Access."),
            ], deck="cards"),
        Section("working_fixes", "IN v1.76.0 · OCTOBER 5 AND 8", "Smaller fixes that keep the chat moving",
            "Committed after the v1.75.0 tag and carried by the v1.76.0 tag.",
            body=[
                "The Files-Search and System-Metrics helpers ask Ollama their own questions before the main answer. "
                "Those calls now have a time limit, `context_sidecar_llm_timeout_seconds`, 60 seconds by default; "
                "at the limit, or when you press Cancel, a helper skips its context and the answer goes ahead, so a "
                "slow reply can no longer freeze the chat.",
                "When Windows still holds `Uninstaller.exe` while the uninstaller finishes, the file is retried, "
                "moved aside and deleted by a hidden cleanup after exit, so the uninstall completes. File-Creator "
                "gained `append`: true adds the content to the end of a file, byte for byte, instead of "
                "overwriting it.",
            ],
            points=[
                ("Context helpers", "Their own model calls stop at a time limit or on Cancel."),
                ("Uninstaller", "A held Uninstaller.exe is moved aside and removed after exit."),
                ("File-Creator", "`append: true` adds to a file instead of overwriting it."),
            ], deck="cards"),
        Section("working_canvas", "IN v1.76.0 · OCTOBER 4", "Graphical notes and resizable Run output",
            "Committed to main on October 4 and carried by the v1.76.0 tag; local executables were rebuilt to validate them.",
            body=[
                "User Commentary is edited entirely on the canvas. Double-click or press Enter to write, "
                "then format selected words with the floating mini toolbar. A single note can combine "
                "different fonts, sizes, text colors, bold, italic and underline. A caret styles the next "
                "text you type. Bubble color and alignment apply to the whole note.",
                "Drag any border or corner, including while writing. Fit text removes spare height. "
                "Every wrapped line stays inside the bubble without an internal scrollbar. Done or "
                "Ctrl+Enter saves the edit. Cancel or Escape restores its text, styles, size and position.",
                "The divider above Run output allocates 5% to 95% of the usable canvas/output height. "
                "Only the two viewports change. Canvas zoom, figure dimensions and text sizes stay fixed, "
                "and each pane scrolls independently. The browser remembers the ratio per signed-in user.",
                "The October 4 commentary verification passed 29 diagram/runner tests, 3 carriage tests "
                "and 23 visible Chrome checkpoints, including three mixed-style comments through three "
                "file save/open cycles with identical data and rendered line boxes. The output-divider "
                "verification separately passed 14 visible Chrome checkpoints and 3 carriage tests. "
                "These are dated results, not a claim that this documentation refresh reran them.",
            ], deck="list", deck_points=[
                ("Rich notes", "Selected text keeps its own fonts, sizes, colors and emphasis."),
                ("Direct editing", "Floating tools and all-border resizing. No commentary dialog."),
                ("Run output", "5% to 95% height. Independent scrolling with content sizes preserved."),
                ("File fidelity", "Three mixed-style notes rendered identically across three save/open cycles."),
                ("Delivery", "Committed October 4 and carried by v1.76.0; builds were validated separately."),
            ]),
        Section("working_main", "IN v1.76.0 · OCTOBER 3", "Four stop sequences and a clearer Prompt Flow Panel",
            "Committed on main after the v1.75.0 tag and carried by the v1.76.0 tag.",
            body=[
                "Ollama's cloud models refuse a request that carries more than four stop sequences, and the chat "
                "model used to send nine, so the chat-history summary, the first call once a conversation grows "
                "long, failed the whole request. Every stop list now passes through one fitter that keeps at "
                "most four, most important first, and a failed summary no longer fails the answer: the request "
                "continues without it, while Cancel still stops it.",
                "The Prompt Flow Panel separates two things that shared one name. User Input is the operation "
                "that stops to ask you something; it keeps exactly its old behaviour under a new notched figure. "
                "User Commentary is now a static speech-bubble note for reviewers: written in place, coloured "
                "and styled freely, growing to hold its whole text without a scrollbar, and never run. New "
                "files are saved as version 2; version 1 files open with their old commentary steps turned into "
                "User Input, identifiers and connections kept.",
                "The October 3 refresh reran 430 targeted unit tests, the offline Prompt Flow check, ESLint with zero "
                "errors, the skills inventory and both inclusion sweeps; all passed, and ruff now reports a "
                "clean tree. In a visible Chrome on the real desktop, the commentary test passed all nine "
                "checkpoints: long notes without scrollbars, fonts and colours, resize with Undo and Redo, "
                "save and reopen, a real User Input run, Escape stopping it, and a version 1 file migrating.",
            ],
            points=[
                ("Four stop sequences", "Every Ollama request; a failed summary never fails the answer."),
                ("User Input", "The step that asks you: same mechanism, new figure."),
                ("User Commentary", "A static review note; it never runs and never reaches the model."),
                ("Version 2 files", "Version 1 flows migrate on open; identifiers and links are kept."),
                ("October 3 evidence", "430 unit tests; 9 of 9 visible Chrome checkpoints."),
            ], deck="cards"),
        Section("working_switches", "NEW IN v1.75.0", "Compact mode and Self-modify become switches",
            "Tagged on October 3: Compact mode is a toolbar switch; the Self-modify switch followed and ships in v1.76.0.",
            body=[
                "Compact mode as tagged in v1.74.0 was a verdict made behind the user's back. In v1.75.0 it is "
                "a toolbar box. Ticking it unticks every row in Configure MCPs, Configure Agents and "
                "ACPX-Skills except System-Metrics, Files-Search and Current-Time, and pauses the External "
                "MCPs; unticking it ticks every row again. Each row shows the tokens it adds, a model that "
                "cannot hold everything turns the box on and locks it, and an answer built from a cut request "
                "carries a CONTEXT-WINDOW warning.",
                "Right after the tag, commit 70aeeb87 added the Self-modify box, which ships in v1.76.0. A source "
                "run always shows it; "
                "a frozen build shows it only when built with --self-modify. On, it sends her self-knowledge, "
                "about 28,900 tokens per request; off, one line tells her not to change her own code. A model "
                "that cannot hold it shows the box locked off.",
                "The visible Compact-switch run passed 57 of 57 checks on a local qwen2.5 and a free cloud "
                "model. The visible Self-modify run passed 28 of 28: with the same 119 tools, the request with "
                "the self-knowledge was 117,517 bytes larger than without it. 473 unit tests passed, including "
                "a render of the page as a frozen build.",
            ],
            points=[
                ("Compact switch", "Only the rows you tick; locked on when the model cannot hold everything."),
                ("Prices", "Every Configure row shows the tokens it adds to each request."),
                ("Self-modify", "Her self-knowledge on or off; locked off when it does not fit."),
                ("Proof", "57/57 and 28/28 visible checks; 473 unit tests."),
            ], deck="cards"),
        Section("working_compact", "CARRIED FROM v1.74.0", "Compact mode and readable tables",
            "Tagged on October 1: every request is fitted to the model it is sent to.",
            body=[
                "A model that can hold Tlamatini's complete request still receives it byte for byte. A model "
                "whose real window is smaller receives Compact mode, described in the How She Works chapter, "
                "with a once-per-model dialog, a Compact badge and a locked ACPX box, replaced in v1.75.0 by a switch.",
                "The visible run on a local qwen2.5 exposed three more problems, fixed in the same release. In "
                "Compact mode the one-shot file guard now states the real reason a file cannot be opened, and a "
                "table the user asked to see is shown as a table instead of fenced code. For every model, an "
                "answer-table cell whose text would be unreadable is recoloured.",
                "On October 1 the visible Compact run on the installed qwen2.5:latest passed 37 of 37 checks at "
                "about 8,100 tokens per request, with no cuts. On nemotron-3-ultra:cloud every request stayed "
                "complete, with Ollama reading 102,539 to 104,259 tokens. A small model can still sometimes "
                "re-answer an earlier question before the new one. The v1.74.0 dossier refresh reran the 43 "
                "Compact-mode regression tests; all passed.",
            ],
            points=[
                ("Fitted", "Full when the model can hold the request; Compact when it cannot."),
                ("Compact proof", "37/37 visible checks on a local qwen2.5, about 8.1K tokens, no cuts."),
                ("Full proof", "A large cloud model read every request complete: about 103K tokens."),
                ("Readable tables", "Cells below 3:1 contrast are recoloured, for every model."),
            ], deck="cards"),
        Section("working_catalog", "CARRIED FROM v1.73.1", "Model lists from the server you configured",
            "Tagged on October 1: Config ▸ Models asks the configured Ollama servers, with their token.",
            body=[
                "Config ▸ Models used to ask the browser's own Ollama for the model list, at an address fixed "
                "when the page loaded. After Config ▸ URLs pointed Tlamatini at a remote server, a model "
                "installed only there was marked red and could not be saved.",
                "A login-protected endpoint now reads config.json on every call, asks each distinct configured "
                "Ollama address in parallel with the same bearer token the chat sends, and merges their model "
                "names. Each server reports its own status, and the dialog names the server and the reason "
                "when one cannot answer, such as an HTTP 401 that points to the token.",
                "The same release made the start-up GPU step send the token too, so a token-protected remote "
                "server no longer answers 401 at every start. A visible run against a simulated "
                "token-protected server passed 16 of 16 checks, with every request carrying the token. The "
                "v1.74.0 dossier refresh reran the 18 model-catalog regression tests; all passed.",
            ],
            points=[
                ("Fresh address", "Read from config.json on every call, never fixed at page load."),
                ("Token", "Every configured server is asked with the chat's own bearer token."),
                ("Clear errors", "Each server reports its status; a 401 points at the token."),
                ("Start-up", "The GPU warm-up sends the token too: no 401 at every start."),
            ], deck="cards"),
        Section("working_drop", "CARRIED FROM v1.73.0", "One card removed from future context",
            "Tagged and published on September 30: Drop throughout chat, with confirmation and history updates.",
            body=[
                "Saved greetings, user prompts and answers carry their AgentMessage id from the first page "
                "render and subsequent WebSocket frames. The drop-message request validates that id against "
                "the signed-in conversation owner before deleting rows. A busy guard checks this connection's "
                "active run; it is not a global lock across all of the user's tabs.",
                "Successful deletion broadcasts message-dropped with all deleted ids to the user's tabs, "
                "then schedules a context-gauge refresh. Dropping a user prompt also removes up to twenty "
                "directly following Referenced Rephrase rows, stopping at the first other row. An answer "
                "or another user's message is never included in that cleanup.",
                "All 23 focused Drop regression tests passed on September 30, covering ownership, both message roles, neighboring rows, "
                "the history window, busy refusal, rephrases and browser/server protocol contracts. The "
                "September 30 maintainer record reports 42/42 checks in the extended visible browser harness, "
                "including a new real context count after every drop that ends lower than before; "
                "this dossier refresh reruns the focused suite without writing to the real memory graph.",
            ],
            points=[
                ("Owned rows", "Server deletion is scoped to the signed-in user's conversation."),
                ("Tabs and gauge", "Confirmed ids remove saved cards across tabs and refresh the context estimate."),
                ("Rephrases", "Prompt cleanup removes following rephrase copies and keeps the answer."),
                ("Run guard", "An active answer blocks Drop on that connection. Other tabs have separate runs."),
            ], deck="cards"),
        Section("working_web", "CARRIED FROM v1.72.4", "Web pages that cannot vanish in silence",
            "Tagged and published on September 29: no web page loses its text without saying so.",
            body=[
                "Crawler and Googler strip a page to its words by skipping scripts, styles and similar "
                "blocks. A block that never closed, such as an omitted closing head tag or a cut-off "
                "download, used to swallow the rest of the page. Both now track open blocks with a stack, "
                "and a plain-text safety net replaces any result that kept too little, logging a warning "
                "when it does.",
                "Two tags travel with it. v1.72.2 added deadline-bound defaults to both agents, and a "
                "CAPTCHA or bot wall is reported as blocked, never read as content. "
                "v1.72.3 made the chat avatar's lips move clearly while she speaks, never wider than her "
                "own portrait.",
            ],
            points=[
                ("No silent loss", "A stack of open tags replaces a counter in both agents."),
                ("Safety net", "A plain reading takes over when a parse keeps too little."),
                ("Bounded defaults", "v1.72.2: search and crawl budgets, cancellation and explicit outcomes."),
                ("Refusals named", "A CAPTCHA or bot wall comes back as blocked, never as content."),
                ("Visible lips", "v1.72.3: her lips open and close clearly, without gaping."),
            ], deck="cards"),
        Section("working_gauge", "CARRIED FROM v1.72.1", "A context gauge that tells the truth",
            "Tagged and published on September 28: the ring beside the message box shows Ollama's own count.",
            body=[
                "The ring now reports the exact request Tlamatini's main chain sends. Bytes are measured; "
                "the token figure is Ollama's own prompt_eval_count for that request, and the ceiling is the "
                "context length Ollama reports. An estimate is shown only until Ollama answers, and says so.",
                "Between questions the ring shows what the next request will cost, recalculated whenever the "
                "state changes: page open, Clear history, Drop, Clear context, a context loaded, an answer finished "
                "or a mode toggled. It is exact in one-shot and Multi-Turn alike, per connected user, and "
                "one-shot questions no longer carry an empty System-Metrics line.",
            ],
            points=[
                ("Real tokens", "Ollama's prompt_eval_count, paired to its own request."),
                ("Exact in both modes", "Live = at-rest prediction + the question + the Multi-Turn plan."),
                ("Main chain only", "Out-of-band calls never reach the ring; each user sees their own."),
                ("Less waste", "The question is sent once; the one-shot placeholder line is gone."),
                ("Proof", "A visible lab passed 60 of 60 checks against tlamatini.log."),
            ], deck="cards"),
        Section("working_voice", "CARRIED FROM v1.72.0", "Direct dictation and dependency coverage",
            "These September 27 changes were tagged v1.72.0 and published on September 28.",
            body=[
                "The chat microphone starts Whisperer directly, stops on the configured silence gate, "
                "recognizes speech and sends or leaves an editable draft as selected in Config > Mic. "
                "The dialog also saves browser-local input, gain, gate and recognition preferences. The worker uses the main "
                "application logger and creates no second console. Developer tests remain visibly executed.",
                "The root dependency manifest and separate ESPHome manifest now account for referenced "
                "libraries across agents and source. The static guard and detailed dependency audit record "
                "coverage and runtime boundaries. They shipped in the published v1.72.0 release; the "
                "shared root-asset carrier repair that followed is committed and carried by v1.72.1.",
            ],
            points=[
                ("User guide", "README.md and BookOfTlamatini.md explain Mic settings, recording, cancellation and both modes."),
                ("Runtime contract", "docs/chat-microphone-design.md records ownership, protocol, configuration and limits."),
                ("Dependencies", "docs/dependency-coverage-audit.md records declarations, isolation and verification."),
                ("Delivery", "Published as v1.72.0 and carried by v1.72.1, with the root-asset carrier repair."),
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
