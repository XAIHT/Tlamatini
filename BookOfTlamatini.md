# Tlamatini

![Project Logo](Tlamatini.jpg)

> **The Book of Tlamatini** — a step-by-step guide to running, using, and mastering a locally-deployed AI developer assistant with RAG, Multi-Turn tool orchestration, ACPX external-CLI delegation, a visual workflow designer, 60 drag-and-drop agent types, and a backend Flow Compiler that turns the live canvas — or a chat-generated tool-call log — into a registry-validated, secret-redacted, source-and-frozen-portable workflow.
>
> Visit our site at **https://xaiht.org**, or get a one-minute taste of Tlamatini on YouTube: **https://youtu.be/a51miZ1JIe0**.

---

## How to read this book

Tlamatini does a lot. This README is organized so you can stop reading at the depth you need.

- **Part I — Getting Tlamatini Running**: prerequisites, Ollama, install, first login. *Read this once.*
- **Part II — Using the Chat**: the four toolbar checkboxes (Multi-Turn, Exec Report, ACPX, internet) walked through one by one. *This is the dummy-friendly heart of the book.*
- **Part III — The Visual Workflow Designer**: drag-and-drop flows, FlowCreator, FlowHypervisor, Parametrizer, Gatewayer.
- **Part IV — The Tlamatini Bestiary**: compact one-row-per-agent reference for all 60 workflow agents.
- **Part V — The Tool Surface**: every LLM-facing tool the chat can call, organized by family.
- **Part VI — Inside Tlamatini**: architecture, RAG, Multi-Turn pipeline, ACPX runtime mechanics. *For the curious.*
- **Part VII — Configuration Reference**: every `config.json` knob.
- **Part VIII — Deploying & Packaging**: build, installer, frozen mode.
- **Part IX — The Command Deck**: WebSocket protocol, HTTP endpoints.
- **Part X — Survival Guide**: troubleshooting, `tlamatini.log`, common issues.
- **Appendix A** — Keyboarder key reference.
- **Appendix B** — Glossary.
- **Appendix C** — Full changelog (preserved verbatim).
- **Appendix D** — Acknowledgments / Contributing / License.

If you only have ten minutes, read Part I §3–§5 (install + first login), then Part II §11 (Multi-Turn).

---

## Demo videos

- [First system-usage walkthrough](https://www.youtube.com/watch?v=CkvDPSd_c-g)
- [Loading a complete project and summarizing its source code](https://www.youtube.com/watch?v=Lrpbt_dPIXw)
- [Installing OpenCV end-to-end in Multi-Turn](https://www.youtube.com/watch?v=bBlqbZVK-Wk)
- [Uninstalling Poco — Exec Report and matching flow](https://www.youtube.com/watch?v=E5vi0q5FxXQ)
- [Designing a flow with FlowCreator's help](https://www.youtube.com/watch?v=Tgoa7Tmoo0o)

---

# Part I — Getting Tlamatini Running

## 1. What is Tlamatini?

**Tlamatini** (Nahuatl for "one who knows") is a locally-deployed AI developer assistant. It runs in your browser, talks to a local or cloud LLM, knows your code, and can actually *do* things on your machine — not just describe how to do them.

The four things Tlamatini gives you that a plain ChatGPT-style box does not:

1. **A real RAG pipeline** that reads your project files, classifies their architectural roles, and grounds answers in your real source code.
2. **Multi-Turn mode** that turns the chat into a tool operator: the LLM can run shell commands, hit APIs, send emails, take screenshots, type into windows, query SQL — and chain those steps to finish the job.
3. **ACPX** that lets the LLM delegate sub-tasks to external coding-agent CLIs you already have installed (Claude Code, Cursor, Codex, Gemini CLI, Qwen Code, and more).
4. **A visual workflow designer** where you drag 60 different agent types onto a canvas, wire them up, and run the result as an unattended `.flw` workflow. Save, Validate, and Start all funnel the canvas through a backend **Flow Compiler** (`agent/services/flow_compiler.py`) that consults a single Agent Contract registry — so a flow that runs in source mode runs identically in a frozen `.exe` install.

Everything is local. No cloud lock-in (though cloud LLMs are an option). The whole app packages into a standalone Windows `.exe` if you want to ship it.

## 2. What you need before installing

| Requirement | Recommended | Notes |
|---|---|---|
| **Python** | 3.12.10 | The only version Tlamatini has been fully tested with. |
| **Operating system** | Windows 11 | The visual designer is cross-platform; some Windows-specific helpers (Mouser, Keyboarder, `.flw` file association) are best on Windows. |
| **Disk space** | ~10 GB | Most of this is the local LLM models you pull through Ollama. |
| **RAM** | 16 GB minimum | 32 GB is comfortable for the bigger embedding models. |
| **A local LLM server** | **Ollama** | The default. You can also point Tlamatini at the Anthropic API for cloud Claude. |
| **An IDE or editor** | Optional | Tlamatini ships with built-in "Open in VS Code / Antigravity / File Explorer" buttons if those are installed. |

You do **not** need administrator rights to install Tlamatini or Ollama if you follow the per-user paths in chapters 3 and 5.

## 3. Installing Ollama (no admin rights needed)

The official Windows PowerShell installer supports a per-user installation. Open PowerShell normally (do *not* right-click → Run as administrator).

### 3.1. Install Ollama into your user profile

```powershell
$env:OLLAMA_INSTALL_DIR = "$env:LOCALAPPDATA\Programs\Ollama"
irm https://ollama.com/install.ps1 | iex
```

This forces the install into a folder you already own (`%LOCALAPPDATA%\Programs\Ollama`) — no machine-wide location, no elevation prompt.

### 3.2. Reopen PowerShell, then verify

Close the PowerShell window. Open a fresh one. Then:

```powershell
ollama --version
```

If you see a version number, Ollama is installed and on `PATH`. If PowerShell complains it does not recognize `ollama`, close it once more, open a fresh window, and try again — the new `PATH` only takes effect in shells launched *after* the install.

### 3.3. Make sure the Ollama service is up

Tlamatini expects Ollama at `http://127.0.0.1:11434`. On most Windows installs Ollama starts on its own. If it is not running, leave a dedicated terminal open with:

```powershell
ollama serve
```

Verify it answers:

```powershell
Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing
```

A normal HTTP response (any non-error code) means Ollama is reachable.

## 4. Pulling the default models

Tlamatini ships with default model names in `Tlamatini/agent/config.json` and several agent `config.yaml` files. Pull them exactly as written:

```powershell
ollama pull qwen3-embedding:8b
ollama pull glm-5:cloud
ollama pull qwen3.5:cloud
ollama pull gpt-oss:120b-cloud
ollama pull qwen3.5:397b-cloud
ollama pull llama3.2-vision:11b
```

| Model tag | Used by |
|---|---|
| `qwen3-embedding:8b` | RAG embedding model |
| `glm-5:cloud` | Default chat model + Multi-Turn unified-agent model + MCP file-search model |
| `qwen3.5:cloud` | Default Image-Interpreter vision model |
| `gpt-oss:120b-cloud` | Several workflow-agent templates (Monitor Log, Notifier, Prompter, Summarizer, Pser, Recmailer, Whatsapper, File-Interpreter, FlowHypervisor) |
| `qwen3.5:397b-cloud` | Default FlowCreator model |
| `llama3.2-vision:11b` | Local vision fallback |

Some pulls are large and slow. Start them, walk away, come back.

> **Free to substitute.** None of the model tags above are mandatory. If you prefer a different local model, edit the relevant entry in `config.json` (Part VII) or the agent's `config.yaml`. Just match the model name to something `ollama list` actually returns.

## 5. Installing Tlamatini

You have three paths. Pick one.

### Path A — From source (developers, contributors, full control)

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

When the migrations finish and you have a superuser, run the server (chapter 6).

### Path B — Pre-built one-click installer (end users)

If somebody handed you a `Tlamatini_Release/` folder (or you built one — see Part VIII):

1. Open the folder.
2. Double-click **`Installer.exe`**.
3. Pick a destination directory (any folder you can write to — no admin needed).
4. Click **Install**.
5. The installer creates a desktop shortcut, registers `.flw` as a Tlamatini file type, copies in the bundled Ollama-default `config.json`, and creates a default user (`user` / `changeme`).

That is it. Double-click the desktop shortcut to launch.

### Path C — Build the installer yourself (releasers)

See **Part VIII — Deploying & Packaging**. Three scripts, run in order: `build.py` → `build_uninstaller.py` → `build_installer.py`.

## 6. First login

After step 5 (any path), run the server:

```bash
python Tlamatini/manage.py runserver --noreload
```

(For installer builds, just double-click the desktop shortcut.)

Open `http://127.0.0.1:8000/` in your browser.

| You used... | Log in with |
|---|---|
| Path A (from source) | The superuser you created with `createsuperuser` |
| Path B (installer) | `user` / `changeme` |
| Path C (your own build) | Whatever the build configured |

> **Change the default password.** If you used the installer's default `user / changeme`, the very first thing to do after logging in is open `/admin/`, find your user, and change the password. Especially before exposing the host on a network.

After login you arrive at the welcome page. Click into **`/agent/`** for the chat or **`/agentic_control_panel/`** for the visual designer. The chat is what Part II is about.

---

# Part II — Using the Chat (the dummy walkthrough)

## 7. A tour of the chat page

Open `/agent/`. Here is what you are looking at:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Tlamatini  [Context ▼] [Open in… ▼] [MCPs ▼] [Tools ▼] [Agents ▼]  [Logout] │ ← Top navigation
├─────────────────────────────────────────────────────────────────────────────┤
│  Multi-Turn ☐   Exec Report ☐   ACPX ☐   Add internet context ☐   Clear ⌫  │ ← Toolbar (the four checkboxes!)
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────┐   ┌───────────────────────────────┐  │
│   │  CHAT WINDOW                    │   │   CODE CANVAS                 │  │
│   │  (conversation history)         │   │   (generated code lives here, │  │
│   │                                 │   │    syntax-highlighted, with   │  │
│   │                                 │   │    copy / save buttons)       │  │
│   │                                 │   │                               │  │
│   └─────────────────────────────────┘   └───────────────────────────────┘  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Type your prompt here…                                          [ Send ] │ ← Input bar
└─────────────────────────────────────────────────────────────────────────────┘
```

The four checkboxes in the toolbar are **the** thing to learn. Each one is explained in its own chapter below. They are independent — tick whatever combination fits your task.

## 8. Asking your first question (no toggles)

Leave every checkbox unticked. This is the **simplest** possible chat: one question in, one answer out.

**Try this:**

> "Write a Python function that validates an email address using a regular expression. Just the function, no main."

The bot answers in the chat panel. If it generates code, you will see it appear in the code canvas on the right with a filename header and a copy button.

What is happening under the hood:

1. Your message goes to the server over WebSocket.
2. Tlamatini decides it is a programming question (not a system / files question), runs prompt-shape validation, and sends it to the LLM.
3. The LLM responds in one shot. Done.

This is the **legacy one-shot chat path**. It is fast, deterministic, and uses no tools. It is also intentionally limited: the LLM cannot run anything on your machine, cannot search the web, cannot read files. For that, you tick checkboxes.

## 9. Setting code as context

Most of the time, you want the bot to answer questions about *your* code, not generic Python. Click **Context** in the top nav:

| Menu entry | What it does |
|---|---|
| **Set directory as context** | Loads a folder. Tlamatini reads every text file in it, splits them into chunks, embeds them, builds a hybrid FAISS+BM25 index, and grounds every answer in those files. |
| **Set file as context** | Loads a single file (smaller scope, faster). |
| **Set canvas as context** | Uses the code currently shown in the right-hand canvas as context (handy for iterative editing). |
| **Clear context** | Removes the current context and rebuilds the chain empty. |

After you set a context, the top of the page shows a green banner with the path. Now ask:

> "How does authentication work in this project?"

The bot will quote real files, reference real classes, and stay grounded. If it cannot find the answer in the loaded files, it will say so rather than hallucinate.

> **What if my model runs out of memory?** If Ollama returns "model requires more system memory" while building the embedding index, Tlamatini does **not** wipe the loaded files. It packs them into a fallback context and keeps answering from the raw source until embeddings can be built again. Retrieval quality drops; access to your code does not.

## 10. The "Add internet context" toggle

Tick **Add internet context** when the question genuinely needs information from the web. Examples:

- "What is the latest stable version of FastAPI as of right now?"
- "Show me a current example of using OpenAI's responses API."
- "What does the `2024-11-30` row in the React 19 changelog say?"

Tlamatini classifies your question with a small LLM call ("does this need the web?"), then runs a DuckDuckGo search, fetches and summarizes the top results, and inlines the summary into the LLM's context.

Leave it **unticked** for everything that does not need fresh web data. The classifier is fast but a web round-trip still adds latency.

## 11. The "Multi-Turn" toggle (turning Tlamatini into a *doer*)

This is the big one. Until you tick **Multi-Turn**, Tlamatini only *describes* things. With Multi-Turn ticked, Tlamatini can *do* them.

### What it does

Multi-Turn flips Tlamatini from "answerer" to **operator**:

- The chat skips its prompt-shape validator (you no longer have to phrase requests as questions).
- A request-scoped **planner** picks the relevant tools out of all 36+ wrapped chat-agents, the 12 ACPX tools, and the core Python tools.
- The unified-agent loop runs **up to 100 iterations**: the LLM calls a tool, sees the result, decides what to call next, and chains its way to the goal.
- Wrapped sub-agents launch **silently** in the background (no console window pop-ups).

### When to use it

- "Run my project's test suite and tell me what failed."
- "Crawl this URL, summarize the result, and email it to me."
- "Open Notepad, type 'Hello world', save it as `out.txt`, then close it."
- "Install OpenCV in the `venv` here and verify it works." (See the demo video.)
- Any task where you would otherwise paste commands one at a time.

### Step-by-step: your first Multi-Turn run

1. Tick **Multi-Turn**. Leave the others unticked for now.
2. Type:
   > "Take a screenshot of my desktop and save it to `C:\Tlamatini-test\shot.png`."
3. Hit **Send**.
4. Watch the chat. You will see:
   - A short "Working on it…" sort of message.
   - A final answer like "Done — saved to C:\Tlamatini-test\shot.png."
5. Open the file. The screenshot is there.

What just happened: the planner picked `chat_agent_shoter` (the wrapped Shoter agent), the LLM called it with the right `output_dir`, the agent took a screenshot, the LLM read the JSON result, and replied with the path.

### What you'll see if it goes well

- The LLM does **not** ask you for permission to take the screenshot — Multi-Turn means "you're an operator, not an advisor."
- A **Create Flow** button appears in the message header (chapter 15 explains it).
- The answer ends in a period, with no `END-RESPONSE` sentinel leaking through.

### Common pitfalls

| Symptom | Fix |
|---|---|
| LLM says "Tool X is not available" | The planner did not bind that tool. Check the `[Planner._select]` log lines in the console — adjust your prompt so the relevant keywords are present, or relax the threshold by raising `max_selected_tools` in `config.json`. |
| LLM tries to do everything in plain text | You forgot to tick Multi-Turn. Tick it and resend. |
| Tool runs but the LLM calls the same tool twice with identical args | This is suppressed by the dedup guard. The second call returns "skipped — duplicate" and the LLM moves on. |
| 100 iterations exhausted | Your task probably hit a polling loop (e.g. waiting for an external service). Use `chat_agent_sleeper` instead of busy-polling, or break the task into two prompts. |

### Combine Multi-Turn with context

Multi-Turn and **Set context** stack. If your project is loaded as context, the LLM can ask the codebase about itself *and* run tools on the result. Example:

> "Find the file in this project that defines the `User` model, then run `python -c \"...\"` to dump its `__dict__` schema."

The planner pulls `chat_agent_executer` for the shell call; the loaded context tells the LLM where the model lives.

## 12. The "Exec Report" toggle (seeing every step)

### What it does

Below the LLM's prose answer, Tlamatini appends **per-agent execution tables** — one HTML table per *kind* of state-changing agent that fired during the request, each row a real tool call with a SUCCESS/FAILURE verdict.

This is the "show your work" view. It is the ground-truth counterpart to the prose summary. The prose can be ambiguous; the tables are not.

### When to use it

- Always when you are debugging a Multi-Turn run.
- Always when you want to convert a chat into a flow (chapter 15).
- Whenever you want to be sure what *actually* happened on disk / on the network.

### Step-by-step

1. Tick **Multi-Turn** AND **Exec Report**. Both must be on.
2. Run a Multi-Turn task that touches multiple state-changing tools, e.g.:
   > "Create the file `C:\test\hello.txt` with the content `Hi from Tlamatini`, then read it back and tell me its size."
3. Send.
4. After the prose answer, scroll down. You will see a styled table:

   ```
   ┌──────────────────────────────── List of File Creator Operations ─┐
   │ # │  Command                                              │ ✓/✗ │
   │ 1 │  filepath='C:\test\hello.txt' content='Hi from Tla…'  │  ✓  │
   └──────────────────────────────────────────────────────────────────┘
   ┌──────────────────────────────── List of Executer Operations ─────┐
   │ # │  Command                                              │ ✓/✗ │
   │ 1 │  type C:\test\hello.txt                               │  ✓  │
   └──────────────────────────────────────────────────────────────────┘
   ```

### What gets a table

State-changing tools only. The full list is in `_EXEC_REPORT_TOOLS` in `agent/mcp_agent.py` and includes:

- **Direct tools**: `execute_command`, `execute_file`, `unzip_file`, `decompile_java`.
- **Wrapped chat-agents**: every `chat_agent_*` that touches the system (executer, pythonxer, dockerer, kuberneter, ssher, scper, sqler, mongoxer, gitter, file_creator, mover, deleter, apirer, send_email, telegramer, whatsapper, notifier, kyber_keygen/cipher/decipher, **keyboarder**, **mouser**, jenkinser).
- **ACPX**: `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_kill`, `acp_relay` — all merge into one "List of ACPx Operations" table.
- **Skills**: `invoke_skill` gets its own table.

Read-only tools (Crawler, Googler, Prompter, Summarizer, File-Interpreter, File-Extractor, Image-Interpreter, **Shoter**, Sleeper, monitor_*, recmailer, run_*, window_present) and management tools never appear — they did not change anything to report on.

### A persistence detail worth knowing

The Exec Report tables are **persisted into the chat history**, not just broadcast live. Reload the page — the tables are still there. This is intentional, and the order in `process_llm_response()` is strict: classify success → append exec-report HTML → save → broadcast. Do not reorder.

## 13. The "ACPX" toggle (delegating to external coding-agent CLIs)

### What it does

ACPX is the most ambitious feature. It lets Tlamatini **spawn external coding-agent CLIs** (Anthropic's `claude` CLI, Cursor's `cursor-agent`, OpenAI's `codex`, Google's `gemini`, Alibaba's `qwen-code`, plus eight more) **as child processes**, talk to them over stdin/stdout, and broker their output back to the LLM as if they were native tools.

Picture it like this:

```
┌──────────────────────────────────────┐
│ You (in the chat)                    │
└──────────────┬───────────────────────┘
               │ "Use claude to refactor X, then have gemini critique it"
               ▼
┌──────────────────────────────────────┐
│ Tlamatini chat (the Multi-Turn LLM)  │
│   acp_doctor → acp_spawn(claude) →   │
│   acp_send_and_wait → acp_relay →    │
│   acp_spawn(gemini) → acp_kill       │
└──────────────┬───────────────────────┘
               │ subprocess.Popen
               ▼
┌──────────────────────────────────────┐
│ External CLIs running on your box    │
│   claude, gemini, cursor, codex, …   │
└──────────────────────────────────────┘
```

The full ACPX deep-dive is in **Part VI §44**. This chapter is just the toolbar walkthrough.

### When to use it

Tick **ACPX** when:

- You want a sub-task delegated to a *different* LLM than the one driving Tlamatini's chat. (Example: your chat runs glm-5, but you want Claude Code to do the actual refactor because it is better at long-context Python.)
- You want a **multi-CLI relay** — Claude does the first pass, Gemini critiques, Cursor applies the fix.
- You need a coding agent that can edit files in the *current working directory* without the wrapping ceremony of Multi-Turn.

Untick **ACPX** when you don't have any external CLIs installed, or when you want the legacy pre-ACPX Multi-Turn flow. The 12-tool ACPX surface is filtered out of the planner — the LLM never sees it.

### Step-by-step: your first ACPX run

**Prereq:** at least one external CLI installed and on PATH. The simplest is Anthropic's:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

Then put your API key into `Tlamatini/agent/config.json`:

```json
{
  "ANTHROPIC_API_KEY": "sk-ant-api03-...",
  "acpx": {
    "agents": {
      "claude": { "env": { "ANTHROPIC_API_KEY": "sk-ant-api03-..." } }
    }
  }
}
```

(Two layers — top-level for Tlamatini's own Anthropic calls, and `acpx.agents.claude.env` for the spawned `claude` CLI. The skill `setup-new-acpx-key` automates this; see chapter 14.)

Now in the chat, tick **Multi-Turn** AND **ACPX** AND **Exec Report**, and type:

> "Use ACPX to spawn the claude CLI in `C:/Development/Tlamatini`, ask it to summarize CLAUDE.md in 5 bullet points, harvest the answer, and kill the session."

You will see:

1. The LLM calls `acp_doctor` first (always).
2. Then `acp_spawn(agent_id="claude", task="...summarize CLAUDE.md...")`.
3. A `session_id` comes back; the LLM uses it.
4. `acp_send_and_wait` to ensure the answer is fully drained.
5. `acp_kill` to shut the child cleanly.
6. The 5-bullet summary appears in the prose answer.
7. The Exec Report shows a "List of ACPx Operations" table with all four tool calls.

### Common pitfalls

| Symptom | Fix |
|---|---|
| `acp_doctor` says `claude` is not resolvable | The CLI is not on `PATH`. Either fix `PATH`, or set `acpx.agents.claude.command` to the absolute path of `claude.cmd`. |
| Transcript only shows the outbound prompt, no answer | This used to be the bug for TUI-style CLIs (claude/gemini/cursor/qwen on Windows). It is fixed in current builds via the `oneshot-prompt` transport. If you see it, your build is older than May 2026 — update. |
| Session left running | Always end with `acp_kill`. The LLM is rule-instructed to do so, but if a request times out, manually call `acp_list_sessions` and `acp_kill`. |
| API key not picked up | Order matters: per-agent `acpx.agents.<id>.env` wins over a shell-exported variable. Double-check both layers. |

## 14. Combining the four toggles — worked examples

### Example A — "Set up a new ACPX agent_id from scratch"

**Tick:** Multi-Turn + ACPX + Exec Report.

> "Use the `setup-new-acpx-key` skill to register my Gemini API key (paste your key) for the `gemini` agent_id. Then run `acp_doctor` to verify it works."

The LLM picks `invoke_skill`, the skill walks itself through writing `data.keys`, patching `config.json` at both layers, and finishes with `acp_doctor` confirming `gemini` is resolvable.

### Example B — "Build a feature with three different LLMs in sequence"

**Tick:** all four (Multi-Turn + Exec Report + ACPX + internet).

> "Crawl https://docs.python.org/3/library/asyncio-task.html, summarize it. Then have claude propose a refactor of `myapp/worker.py` using those new patterns. Hand the proposal to gemini and ask it to critique. Apply the cleaned-up critique to the file with cursor. Use `acp_relay` between legs."

This is the multi-CLI relay flow. The Exec Report at the end shows every spawn, send, relay and kill — auditable.

### Example C — "Just answer this code question, please"

**Tick:** nothing. Set context to your project. Ask:

> "Where do we cap the connection-pool size in the database client?"

You get a quoted-and-cited answer in <2 seconds. No tools, no wait, no overhead.

### Example D — "Run my tests, but don't crash my desktop with popups"

**Tick:** Multi-Turn + Exec Report.

> "Run `pytest -x -k auth` in this project and summarize the output. If anything fails, show me the failing assertion."

Multi-Turn suppresses console pop-ups for wrapped runtimes; Exec Report gives you an audit table after.

## 15. From chat to flow — the Create Flow button

When a Multi-Turn run **succeeds** and used at least one state-changing tool, Tlamatini renders a **Create Flow** button in the message header. Click it to download a `.flw` JSON file that mirrors the exact tool sequence the LLM ran, laid out left-to-right, ready to load in the visual designer.

How the gating works (all four conditions must be true):

| # | Condition | Why |
|---|---|---|
| 1 | Multi-Turn was on | One-shot chats never use tools. |
| 2 | At least one tool that maps to an ACP agent succeeded | Read-only tools are excluded from flow generation. |
| 3 | Answer was classified `SUCCESS` by an LLM-based classifier | Hides the button on failures. |
| 4 | The user is logged in (not anonymous) | Sanity. |

The classifier is a tiny `chained-model` call with a strict binary prompt. It fails *open* (returns SUCCESS on internal error) so the button is never hidden by a flake.

What the generated `.flw` looks like (3-tool example):

```
Starter ──► Crawler ──► File Creator ──► Ender
```

You can immediately re-open it in `/agentic_control_panel/` and run it as an unattended workflow — the LLM is no longer involved.

**Behind the scenes** (since commit `0bea21d`, May 2026), clicking Create Flow does NOT just dump the legacy draft. The browser POSTs the draft + `tool_calls_log` to `/agent/flow_from_tool_calls/`, which runs it through `agent/services/flow_spec.py::normalize_flow_payload()` and returns `flow_spec_to_legacy_json(spec, redact=True)` — a registry-canonical `.flw` whose agent / pool names match the backend Agent Contract registry and whose known secret fields (e.g. `tlamatini.password`) are stripped before the file ever touches your disk. If the round-trip fails (offline frozen install, backend down), the browser gracefully falls back to the un-normalized legacy draft so you still get a usable file.

---

# Part III — The Visual Workflow Designer

## 16. Why drag-and-drop flows

The chat is amazing for one-off tasks. But some jobs you want to:

- Run on a schedule (every hour, every Monday at 9 a.m.)
- Run unattended on a remote server
- Run identically every time, with no LLM creativity in the loop
- Compose at design-time so the steps are auditable before any LLM is involved

Those are flows. You drag agents from a sidebar onto a canvas, draw lines between them, configure their parameters, save the result as a `.flw` file, and run it.

## 17. Anatomy of the canvas

Open `/agentic_control_panel/`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ▶ Start  ⏸ Pause  ⏹ Stop  ⚠ Hypervisor  💾 Save  📂 Load  ✓ Validate  │ ← Toolbar
├──────────────────┬──────────────────────────────────────────────────────┤
│  Sidebar         │                                                      │
│  ─ Control       │                                                      │
│    Starter       │                                                      │
│    Ender         │                                                      │
│  ─ Routing       │             CANVAS                                   │
│    Forker        │       (draggable agents,                             │
│    Asker         │        connections, LEDs)                            │
│  ─ Logic Gates   │                                                      │
│    AND  OR  …    │                                                      │
│  ─ Action        │                                                      │
│    Executer      │                                                      │
│    …             │                                                      │
│  …               │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

A few facts about the canvas you need to internalize:

- **It scrolls.** The visible area is a viewport (`#submonitor-container`). The actual canvas (`#canvas-content`) grows to the right and bottom as you drop more agents. Use the themed scrollbars.
- **Each agent is a draggable item.** Double-click to open its config. Right-click for the context menu (description, log, explore directory, open cmd, restart).
- **Connections are typed.** A green line means "start the target after this finishes" (`target_agents`). A blue line means "monitor this source's log" (`source_agents`). The direction matters.
- **LEDs show state.** Green = running, red = down while the flow is active, yellow blinking = paused, gray = stopped/idle.

## 18. Your first flow (3-agent example)

Goal: run a shell command, take a screenshot, end.

**Step-by-step:**

1. Drag **Starter** onto the canvas (top-left).
2. Drag **Executer** to its right.
3. Drag **Shoter** further right.
4. Drag **Ender** at the far right.
5. Connect: Starter → Executer → Shoter → Ender (click the right edge of one, drag to the left edge of the next).
6. Double-click **Executer** and set its `command` to `dir C:\` (or `ls /tmp` on Linux).
7. Double-click **Shoter** and set `output_dir` to a folder you can write to.
8. Double-click **Ender** and confirm its `target_agents` lists every other agent (Starter, Executer, Shoter) — Ender's job is to terminate them on completion.
9. Click **✓ Validate** — Tlamatini runs structural checks (no orphans, no self-connections, terminal agents reachable).
10. Click **▶ Start**.

You'll see LEDs go green, then sequential outputs in the log viewer, then everything turns gray. Open your `output_dir` — there is a screenshot.

## 19. Saving and loading `.flw` files

Click **💾 Save**, pick a name. You get a JSON file with all node positions, configs, and connections. Distribute it; somebody else loads it via **📂 Load**, gets the same flow.

`.flw` files are also what the chat's **Create Flow** button (chapter 15) emits.

## 20. Pause, Resume, and Stop

The three buttons each do something different:

| Button | What happens |
|---|---|
| **⏸ Pause** | Stores the currently-running agents into `paused_agents.reanim`, kills their processes, **leaves logs and `reanim*` state files intact**. The ACP enters paused state (yellow LEDs). |
| **▶ Resume** (after pause) | Reanimates each saved agent with `AGENT_REANIMATED=1`. Each agent reads its `reanim*` files and continues from exactly where it stopped. |
| **⏹ Stop** | Hard stop. Ender runs its termination logic; reanimation files are cleared. |

This is why long-running workflows (Crawler scraping 10,000 URLs, Parametrizer iterating through segments) survive pauses without data loss.

## 21. FlowHypervisor (your watchdog)

Click **⚠ Hypervisor** and a system-managed FlowHypervisor agent starts watching every other running agent. It is an LLM that:

- Reads each agent's log incrementally.
- Builds an NxN connection matrix from the canvas wiring.
- Looks for: stuck agents (started >5 min ago, no output, downstream never fired); broken chains (agent finished, but its `target_agents` never started); fatal/critical errors; user-imposed time constraints.
- Outputs exactly **`OK`** when healthy or **`ATTENTION NEEDED { explanation }`** when not.

If a problem fires, the browser shows an alert dialog. You can append your own rules to the watchdog through the FlowHypervisor agent's `user_instructions` config field — useful for "don't flag this known false-positive" or "wake me if X is silent for >10 min."

## 22. FlowCreator — let an LLM design the flow for you

Drag a **FlowCreator** node onto the canvas, double-click it, and type a natural-language objective:

> "Every hour, crawl our status page; if it shows ERROR, email the on-call engineer; otherwise, do nothing."

Click **Generate**. FlowCreator reads `agentic_skill.md` (its design playbook), produces a JSON description of the agents and connections, and renders them onto the canvas. You can edit, tweak parameters, and run.

This is the highest-leverage feature for non-technical users: you describe what you want, the system *draws* the flow.

## 23. Parametrizer (chaining outputs into the next agent's config)

This is the agent that makes multi-stage pipelines work without manual `config.yaml` editing.

### The problem it solves

Tlamatini agents communicate through **log files** and **`config.yaml` files** — they have no shared memory. So if you want Apirer's response to become Kyber-Cipher's input, somebody has to copy data between agents.

Parametrizer is that somebody. It reads structured output segments from one source agent's log, injects mapped values into one target agent's `config.yaml`, runs that target, waits for it to finish, restores the target config, advances its source cursor, and only then moves to the next source segment.

### The unified section format

Every "Parametrizer-friendly" agent emits its results in **one** format:

```
INI_SECTION_<AGENT_TYPE><<<
key1: value1
key2: value2

multi-line body content (becomes 'response_body')
>>>END_SECTION_<AGENT_TYPE>
```

Rules:

- `<AGENT_TYPE>` is the agent's UPPERCASE name (`APIRER`, `CRAWLER`, `KYBER_KEYGEN`, …).
- The first blank line separates the KV header from the body.
- The whole section must be emitted in a **single `logging.info()` call** — concurrent log writes from other threads could otherwise interleave and corrupt the block.
- One section per output unit. If the agent produces N results, emit N sections.

### Supported source agents

17 agents emit Parametrizer-compatible sections:

Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Gatewayer, Gateway-Relayer, Googler, **ACPXer**.

### How the visual mapping works

On the canvas, double-click a Parametrizer node to open its custom mapping dialog (not the standard config editor):

1. Left column shows the source agent's available output fields (cyan).
2. Right column shows the target agent's `config.yaml` parameters, flattened to dot-notation if nested (orange).
3. Click a source field, then a target parameter, to draw a curved Bezier line connecting them.
4. Click any line to remove it.
5. Save. Tlamatini writes the mapping to `interconnection-scheme.csv` in the deployed Parametrizer pool directory.

### Iterative execution

If the source produces 5 segments (e.g. Apirer hits 5 endpoints), Parametrizer processes them **one at a time**, in order, with a full `config.yaml.bck` backup-and-restore around each one. The target agent gets a clean config every time, and its log is archived as `<target>_segment_1.log`, `<target>_segment_2.log`, … so each segment outcome stays inspectable.

### A canonical example

```
Apirer ──▶ Parametrizer ──▶ Kyber-Cipher
```

- Apirer calls 3 endpoints, emits 3 `INI_SECTION_APIRER<<<` blocks.
- Parametrizer maps `response_body → buffer` (the value to encrypt).
- Kyber-Cipher runs 3 times, once per response body, encrypting each.

No manual config editing. No race conditions. Pause-safe.

## 24. Gatewayer (external triggers into a flow)

Gatewayer is the **inbound gateway** — the entrypoint that lets external systems kick off your flow.

### Two trigger modes

| Mode | When to use |
|---|---|
| **HTTP webhook** | A CI server, a SaaS callback, a cron job, a curl, a button on an internal portal — anything that can POST. Gatewayer authenticates (`bearer` / `hmac` / `none`), validates, dedups, persists, and starts `target_agents`. |
| **Folder-drop watcher** | Industrial / IoT scenarios where a sensor writes a JSON file to a shared folder. Gatewayer polls the folder, reads new files, archives them, and starts `target_agents`. |

### Authentication modes

| Mode | What it does |
|---|---|
| `none` | Open endpoint, dev/test only. |
| `bearer` | Validates `Authorization: Bearer <token>` against a configured secret. |
| `hmac` | Validates a hex SHA-256 HMAC signature over `timestamp + body`, with configurable header names and clock-skew tolerance. |

> **Note:** `hmac` mode is **not** directly compatible with providers like GitHub that sign only the body (`X-Hub-Signature-256`) and put the event type in headers. To accept those webhooks unchanged, put a small relay in front (Tlamatini ships a **Gateway-Relayer** agent for exactly this) or patch the HMAC logic.

### Worked example: HMAC-signed CI webhook → build → email

```
HTTP POST (timestamped HMAC)
  │
  ▼
Starter → Gatewayer_1 → Executer_1 → Pythonxer_1 → Emailer_1 → Ender_1
            (port 8787,    build.sh     test.py       results
             /gatewayer)
```

Gatewayer_1 `config.yaml` essentials:

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
  required_fields: ["event_type", "ref", "repository"]
  event_type_field: "event_type"

queue:
  dedup_enabled: true
  dedup_key_fields: ["body_hash"]
  dedup_window_sec: 10
```

The sender POSTs JSON with `X-Tlamatini-Timestamp` and `X-Tlamatini-Signature`. Gatewayer verifies, dedups, queues, and dispatches Executer_1. Crash recovery is automatic — pending events survive in `reanim_queue.json`.

Gatewayer logs stable markers (`GATEWAY_EVENT_ACCEPTED`, `GATEWAY_EVENT_QUEUED`, `GATEWAY_EVENT_DISPATCHED`, `GATEWAY_ERROR`), so a Monitor-Log or Summarizer agent can build meta-flows that watch your gateway's health.

---

# Part IV — The Tlamatini Bestiary

A compact reference for all 60 workflow-agent types. Spotlight chapters for **Parametrizer** (§23) and **Gatewayer** (§24) above.

> **Naming reminder.** The `agentDescription` (set by each migration) is the single source of truth. CSS classmap key, sidebar visual, and connection-handler name all derive from it.

> **Description-tooltip source.** The hover tooltip and right-click "Description" dialog both pull their text from `agents_descriptions.md` at the repo root (the Django view parses its `## Workflow Agents` tables and injects them as `agent_purpose_map`). `README.md` is kept as a legacy fallback only. Editing a row in `agents_descriptions.md` changes both human docs AND the live UI text.

## Control

| Agent | Purpose |
|---|---|
| **Starter** | Entry point. Launches first agents. |
| **Ender** | Terminates all agents in `target_agents`, then launches `output_agents` (typically Cleaners, FlowBackers). |
| **Stopper** | Single-threaded pattern-matcher that kills agents when patterns appear in source logs. |
| **Cleaner** | Post-Ender cleanup of logs / PIDs. |
| **Sleeper** | Wait `duration_ms` and trigger downstream. |
| **Croner** | Scheduled trigger (`HH:MM`). |

## Routing

| Agent | Purpose |
|---|---|
| **Raiser** | Watches a source log for a pattern; starts downstream when found. The "event-driven launcher". |
| **Forker** | Auto-routes to Path A or Path B based on two pattern sets. |
| **Asker** | Interactive A/B chooser; pauses the flow until the user picks in the browser. 5-min timeout. |
| **Counter** | Persistent counter; routes to Path L (`<` threshold) or Path G (`>=` threshold). |

## Logic gates

| Agent | Purpose |
|---|---|
| **OR** | Fires when EITHER of two sources completes. |
| **AND** | Fires when BOTH of two sources complete. |
| **Barrier** | Generalized AND: fires when ALL N sources complete. |

## Action

| Agent | Purpose |
|---|---|
| **Executer** | Shell command. |
| **Pythonxer** | Inline Python with Ruff lint and exit-code gating. |
| **Prompter** | LLM prompt → log. |
| **Summarizer** | LLM polls source logs for events; one-shot mode also accepts `input_text`. |
| **Crawler** | Web crawl with raw-content capture and LLM analysis. |
| **Googler** | Google search via Playwright + readable-text extraction. |
| **Apirer** | HTTP REST request with structured logging. |
| **Gitter** | Git operations on a local repo. |
| **Ssher / Scper** | SSH command execution / SCP file transfer. |
| **Dockerer / Kuberneter** | Docker / Kubernetes commands. |
| **Pser** | LLM-powered semantic process finder. |
| **Jenkinser** | Jenkins pipeline trigger with CSRF crumb support. |
| **Sqler / Mongoxer** | SQL Server / MongoDB scripting (external windows). |
| **Mover / Deleter** | File move/copy / deletion (glob, recursive, `filetype_exclusions`). |
| **Shoter** | Screenshot capture (read-only). |
| **Mouser** | Pointer movement, click, drag, scroll, click-at-window, locate-image. |
| **Keyboarder** | Keyboard typing / hotkey chords (PyAutoGUI). |
| **File-Creator** | Write a file. |
| **File-Interpreter / File-Extractor** | Document parsing (DOCX, PPTX, XLSX, PDF, …); raw text extraction with strings-fallback for unknowns. |
| **Image-Interpreter** | LLM vision analysis of images. |
| **J-Decompiler** | JAR/WAR/CLASS decompilation via bundled `jd-cli`. |
| **Telegramer** | Outbound Telegram message. |
| **TeleTlamatini** | Long-running Telegram bridge that exposes the full Multi-Turn + Exec Report Tlamatini chat to authorized Telegram users. |
| **WhatsTlamatini** | WhatsApp counterpart of TeleTlamatini, via Meta's WhatsApp Cloud API. |
| **ACPXer** | Visual canvas counterpart of the 12 LLM-facing ACPX tools. One node = one external-CLI session lifecycle. |

## Cryptography (post-quantum)

| Agent | Purpose |
|---|---|
| **Kyber-KeyGen** | CRYSTALS-Kyber public/private key pair (Kyber-512/768/1024). |
| **Kyber-Cipher** | Kyber encapsulation + AES-256-CTR encryption. |
| **Kyber-DeCipher** | Kyber decapsulation + AES-256-CTR decryption. |

## Utility

| Agent | Purpose |
|---|---|
| **Parametrizer** | Strict single-lane queue mapping source-agent log segments into target-agent config. (See §23.) |
| **FlowBacker** | Post-Ender backup of session logs/configs. |
| **Gatewayer** | Inbound HTTP webhook / folder-drop ingress. (See §24.) |
| **Gateway-Relayer** | Bridges provider webhooks (GitHub) into Gatewayer's HMAC format. |
| **Node-Manager** | Live infrastructure registry; probes nodes via ping/TCP/SSH/WinRM/HTTP. |

## Terminal / monitoring (do NOT start downstream)

| Agent | Purpose |
|---|---|
| **Monitor-Log** | LLM-powered log file monitor. |
| **Monitor-Netstat** | LLM-powered network port monitor. |
| **Emailer** | SMTP email on pattern detection. |
| **RecMailer** | IMAP receiver with LLM keyword analysis. |
| **Notifier** | Browser notification + sound on pattern detection (LangGraph). |
| **Whatsapper** | WhatsApp messages via TextMeBot. |
| **TelegramRX** | Telegram message receiver. |
| **FlowHypervisor** | LLM watchdog over running agents. (See §21.) |

## AI / design

| Agent | Purpose |
|---|---|
| **FlowCreator** | LLM that designs flows from natural-language objectives. (See §22.) |

---

# Part V — The Tool Surface

Every tool the chat LLM can call in Multi-Turn mode. Tools can be individually enabled/disabled via the **Tools Dialog** in the chat.

## 25. Core tools

| Tool | What it does |
|---|---|
| `get_current_time` | Returns current datetime. |
| `execute_command` | Shell command. |
| `execute_file` | Run a Python script in a new terminal. |
| `execute_netstat` | Network diagnostics. |
| `launch_view_image` | Open an image in a viewer. |
| `unzip_file` | Extract ZIP archives. |
| `decompile_java` | Decompile JAR/WAR via bundled `jd-cli`. |
| `opus_analyze_image` | Image analysis with Claude Opus. |
| `qwen_analyze_image` | Image analysis with Qwen via Ollama. |
| `googler` | Web search with Playwright + readable-text extraction. |
| `agent_parametrizer` | Configure a template workflow agent from chat. |
| `agent_starter` | Start a template workflow agent from chat. |
| `agent_stopper` | Stop a template workflow agent. |
| `agent_stat_getter` | Check template-agent runtime status. |

## 26. Wrapped chat-agent tools (36)

Each wrapped tool launches an isolated, sequenced runtime copy of a workflow agent template under `agent/agents/pools/_chat_runs_/{agent}_{seq:03d}_{short_id}/`. Failed runs are preserved.

| Family | Tool names |
|---|---|
| **Execution & files** | `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_pser`, `chat_agent_move_file`, `chat_agent_deleter`, `chat_agent_sleeper` |
| **DevOps & infra** | `chat_agent_gitter`, `chat_agent_dockerer`, `chat_agent_kuberneter`, `chat_agent_jenkinser`, `chat_agent_ssher`, `chat_agent_scper` |
| **Data & interpretation** | `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_file_creator`, `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`, `chat_agent_summarize_text` |
| **Notifications & comms** | `chat_agent_send_email`, `chat_agent_notifier`, `chat_agent_telegramer`, `chat_agent_whatsapper`, `chat_agent_recmailer` |
| **Desktop UI automation** | `chat_agent_shoter` (read-only), `chat_agent_keyboarder`, `chat_agent_mouser` |
| **Routing** | `chat_agent_asker` |
| **Crawling, monitoring, APIs, prompts, crypto** | `chat_agent_crawler`, `chat_agent_monitor_log`, `chat_agent_monitor_netstat`, `chat_agent_apirer`, `chat_agent_prompter`, `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph` |

## 27. Wrapped runtime lifecycle tools (6)

After launching a wrapped agent, you can monitor and control it:

| Tool | What it does |
|---|---|
| `chat_agent_run_list` | List recent runs (capped by `chat_agent_limit_runs`). |
| `chat_agent_run_status` | Inspect status of one run. |
| `chat_agent_run_log` | Read the latest log excerpt. |
| `chat_agent_run_stop` | Stop a run by `run_id`. |
| `chat_agent_run_wait` | **Block** until a run reaches a terminal status (or `max_seconds` fires). Replaces busy-poll loops. |
| `window_present(title)` | Fast (<100 ms) yes/no helper for "is this window open?" — use this instead of `chat_agent_image_interpreter` for window-presence gates. |

## 28. ACPX & Skills tools (12)

The ACPX/Skill surface. Every tool returns a JSON envelope. Failure envelopes are always `{ ok: false, reason: "...", code: "..." }`.

| Tool | What it does |
|---|---|
| `acp_doctor` | Health-probe the runtime + enumerate every registered ACP agent with on-PATH `resolvable` and `cli_version`. **Always call first** when starting an ACPX flow. |
| `list_acp_agents` | Cheap enumeration without the probe. |
| `acp_spawn(agent_id, task, …)` | Spawn an external CLI as a child process. Returns `session_id`, `transport`, `transcript_path`, `events`. **TUI agents return sub-second**; pass `timeout_seconds>0` to force a drain on spawn. |
| `acp_send(session_id, text, …)` | Send a follow-up turn. |
| `acp_send_and_wait(session_id, text, until_idle_seconds=10, max_wait_seconds=180)` | Send and **block until the child settles**. Prefer this for "wait for the full answer" prompts. |
| `acp_kill(session_id)` | Terminate a session. Returns `transcript_path` so the row in Exec Report can cite it. |
| `acp_transcript(session_id, max_chars, direction)` | Read the on-disk NDJSON transcript. Use for harvest / cite-evidence prompts. |
| `acp_session_status(session_id)` | `{alive, pid, transcript_size, last_event_at, closed}`. |
| `acp_list_sessions` | Enumerate live sessions. |
| `acp_relay(session_id_src, session_id_dst, transform, …)` | **Single-call hand-off** between sessions. Replaces transcript→manipulate→send. |
| `invoke_skill(skill_name, args_json)` | Run a registered SKILL.md package inside the `SkillHarness`. |
| `list_skills(filter_keywords)` | List every registered skill. |

The 21 seed skills (`agent/skills_pkg/<name>/SKILL.md`) cover: `hello-world`, `skill-creator`, `acp-router`, `setup-new-acpx-key`, `summarize`, `weather`, `tlamatini-*` (8 maintenance skills: csrf-exempt-audit, exec-report-row-adder, allowed-hosts-tighten, planner-trace-replay, flow-from-objective, flw-doctor, new-acp-agent, static-version-bumper), and OpenClaw-format ports for `github`, `notion`, `jira`, `slack`, `gmail`, `todoist`, `trello`.

---

# Part VI — Inside Tlamatini

This is the deep-dive section. Skip if you only want to use Tlamatini.

## 29. The big picture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser (Chat UI / ACP Workflow Designer)                          │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ WebSocket (ws://)
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Django Channels (Daphne ASGI)                                      │
│    AgentConsumer  →  routing, session, heartbeat                    │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
┌──────────────────┐   ┌────────────────────┐   ┌─────────────────────┐
│  RAG Pipeline    │   │  Unified Agent     │   │  MCP Services       │
│  Document loader │   │  Multi-Turn loop   │   │  System metrics     │
│  FAISS + BM25    │   │  Tool execution    │   │  (WebSocket)        │
│  Context budget  │   │  Planner / DAG     │   │  File search (gRPC) │
│  Fallback mode   │   │  Wrapped runtimes  │   │                     │
└──────────────────┘   └────────────────────┘   └─────────────────────┘
       │                           │                           │
       └─────────────┬─────────────┴─────────────┬─────────────┘
                     ▼                           ▼
       ┌─────────────────────────┐   ┌──────────────────────────┐
       │ LLM Backends            │   │  ACPX Runtime            │
       │ Ollama  Claude  Qwen    │   │  External CLIs as kids   │
       └─────────────────────────┘   └──────────────────────────┘
```

## 30. The Five Layers

The system is organized in five conceptual layers. Each layer has a single responsibility.

| Layer | Responsibility | Where it lives |
|---|---|---|
| **1. Persisted toggles** | Database rows for `Mcp`, `Tool`, and `Agent` — the UI's enable/disable state. | `agent/models.py` |
| **2. Runtime MCP services** | System-Metrics (WebSocket) and Files-Search (gRPC) running as daemon threads. | `agent/mcp_*` |
| **3. Context fetcher chains** | LCEL sidecars that fetch system / files context and inject it into the answer chain. | `agent/chain_*_lcel.py` |
| **4. Main answer chains** | Basic / History-aware / Unified chains. `factory.py` monkey-patches `invoke()` to wire context from sidecars. | `agent/rag/chains/` |
| **5. Unified-agent tools** | Synchronous LangChain `@tool` functions returned by `get_mcp_tools()`. Only active when the unified-agent chain is selected. | `agent/tools.py` |

## 31. RAG pipeline

When you set a directory as context:

1. **Load** every text file under the path.
2. **Chunk** into 3000-character windows with 800-char overlap.
3. **Extract metadata** — class names, function names, imports, file roles (`controller`, `data_model`, `service_layer`, …).
4. **Embed** each chunk using the model in `config.embeding-model`.
5. **Build** the FAISS index.
6. **Build** the BM25 index in parallel.
7. At query time, both indexes return their top-K hits; **Reciprocal Rank Fusion** combines them; **context budgeting** picks chunks within token limits, allocating 60% to high-relevance, 20% to architecture, 15% to related, 5% to documentation.

If embedding fails (out-of-memory), **memory-insufficient fallback** kicks in: the loaded source files are packed into a raw context block and injected directly into the prompt-only / unified-agent path. You get reduced retrieval quality, not a wiped chat.

## 32. Multi-Turn execution pipeline

Below the toolbar checkbox, here is what really happens when you tick **Multi-Turn**:

```
1. FRONTEND
   User types message + ticks Multi-Turn
   → WebSocket sends {message, multi_turn_enabled: true,
                      exec_report_enabled: ?, acpx_enabled: ?}
                                ↓
2. WEBSOCKET CONSUMER (consumers.py)
   Saves to DB, broadcasts user message, queues LLM retrieval
                                ↓
3. RAG INTERFACE (rag/interface.py)
   Bypasses prompt-shape validation (acpx_enabled OR multi_turn_enabled)
   Bypasses path-access validation
   Passes flags into the chain payload
                                ↓
4. UNIFIED RAG CHAIN (rag/chains/unified.py)
   Retrieves docs, builds enhanced input
   Bypasses file-listing short-circuit
   Filters tools through agent.acpx.filter_acpx_tools(tools, acpx_enabled)
                                ↓
5. CAPABILITY-AWARE EXECUTOR (mcp_agent.py)
   Picks the relevant tool subset (default cap: 20 tools)
   Builds a request-scoped MultiTurnToolAgentExecutor
                                ↓
6. MULTI-TURN TOOL LOOP
   for i in 1..unified_agent_max_iterations (default 100):
     LLM call with bind_tools(selected_tools)
     if tool_calls: execute each, append ToolMessage, continue
     if pure text: that's the final answer, exit loop
                                ↓
7. EXEC REPORT (if exec_report_enabled)
   Capture every state-changing tool call into _exec_report_entries
   Render <table class="exec-report-...">
   Append to llm_response BEFORE save_message (strict ordering)
                                ↓
8. WEBSOCKET BROADCAST
   {message, tool_calls_log, multi_turn_used, answer_success}
                                ↓
9. FRONTEND
   appendChatMessage() renders prose, then exec-report tables
   if all four gates pass → render "Create Flow" button
```

The capability-aware selector scores each tool with name match (+14 exact), alias / hint phrase match (+10–12), example-request token overlap (up to +3), description token overlap (up to +10), plus a +15 history-aware boost on short follow-ups (≤4 meaningful tokens). The cap is 20 tools per request by default — lowered from 50 after observing keyword inflation pulled in everything.

## 33. ACPX runtime mechanics

ACPX is a Python port of OpenClaw's ACPX plugin. The `agent_id` mapping, `permissionMode` vocabulary, and SKILL.md frontmatter contract match OpenClaw verbatim.

### Three transport profiles

| Transport | Used by | Drain mechanic |
|---|---|---|
| `oneshot-prompt` | claude, codex, cursor, gemini, qwen | Re-spawn the CLI fresh per turn with the prompt as a CLI arg (`claude -p "<task>"`, `codex exec "<task>"`, …). Close stdin. `proc.communicate(timeout=180)` captures stdout to EOF. **The only transport that reliably captures TUI agents on Windows** — long-lived stdin-fed children only capture the outbound prompt because TUI CLIs detect a piped stdout and refuse to flush. |
| `json-acp` | tlamatini self-host | Strict ACP envelope: drain until `{"done": true}` line. |
| `tui-repl` | kiro, kimi, iflow, kilocode, opencode, pi, droid, copilot | Long-lived REPL. Drain via the **transport-aware idle rule**: armed after `startup_grace + idle_seconds` even with zero events (a silent TUI is, by definition, finished). |

### The idle-rule fix

Before the redesign, every TUI spawn burned the full 45 s timeout because the idle rule required `event_count > 0`, but TUIs almost never emit stdout when fed JSON on a piped stdin (Node block-buffers stdout to 64 KB when piped). The transport-aware idle rule fires on `tui-repl` even with zero events. **Per-leg latency dropped from ~91 s to ~9 s.**

### Per-event payload trimming

Every event-returning tool caps each event body at `max_event_chars` (default 2048) before returning it to the LLM. A chatty REPL paste-back of a long document cannot blow the LLM's context budget on the next iteration. Trimmed events carry `_truncated: true`.

### Permission gating

| Mode | What it does |
|---|---|
| `approve-reads` (default) | Reads auto-approved; writes / shell / network / db need a prompt. |
| `approve-all` | Auto-approves everything. **Flagged DANGEROUS.** |
| `deny-all` | Lockdown — even `acp_spawn` returns `PERMISSION_DENIED`. `acp_doctor` still works. |

Plus a non-interactive policy (`deny` / `fail`) for unattended runs.

### Persisted artifacts on disk

| Path | What |
|---|---|
| `<stateDir>/<session>.json` | `AcpSessionRecord` (session_id, agent_id, cwd, paths, pid, timestamps, closed). |
| `<stateDir>/<session>.transcript.ndjson` | Per-session full transcript: one `{"direction":"out", "text":..., "ts":...}` line per outbound, one `{"direction":"in", "raw":..., "ts":...}` per inbound. |
| `~/.tlamatini/skill-audit/<YYYY-MM>/<epoch>_<skill>_<id8>.ndjson` | Per-`invoke_skill` audit. Append-only. Replayable byte-for-byte. |

### ACPX visual canvas counterpart

The **ACPXer** workflow agent is the canvas counterpart of the 12 LLM-facing tools. One ACPXer node = one ACPX session lifecycle. It mirrors the runtime mechanics inline (in ~120 lines) because workflow agents in the pool run as separate Python subprocesses and cannot import `agent.acpx`. The transcript format is byte-identical, so an ACPXer transcript is interchangeable with a chat-driven one.

## 34. Database models

13 models in `agent/models.py`. The ones that matter day-to-day:

| Model | Purpose |
|---|---|
| `Agent` | Type registry — one row per agent type in the sidebar (`idAgent`, `agentName`, `agentDescription`, `agentContent`). |
| `Mcp` | UI toggle rows for MCP context providers. |
| `Tool` | UI toggle rows for unified-agent tools. |
| `ChatHistory` | Chat messages, with per-user isolation via `conversation_user`. |
| `AgentMessage` | Per-message records, `conversation_user` foreign key for user isolation. |
| `AcpAgent` | Mirrors `agent_registry.py + config.json` overrides. Reconciled by `service.boot_acpx()` on every start. |
| `Skill` | Mirrors `SKILL.md` packages. Reconciled by `service.boot_skills()`. |
| `AcpSession` | One row per real (or recently-real) ACP child. |
| `SkillInvocation` | Append-only audit row per `invoke_skill` call. |
| `ChatAgentRun` | Per wrapped chat-agent run — run_id, status, runtime_dir, log_path, start/end times. |
| `SessionState` | Per-user session state (24-hour TTL). |
| `AgentProcess` | Tracked PIDs for canvas agents. Cleared on shutdown. |
| `Omission` | Secret-redaction patterns for context. |

## 35. The application log (`tlamatini.log`)

`Tlamatini/manage.py` defines a `_TeeStream` wrapper that replaces `sys.stdout` and `sys.stderr` **before Django initializes**. Every print, every Django logger (they all use `StreamHandler`), and every tool's stdout/stderr lands in both the console and a single file:

| Mode | Path |
|---|---|
| Source | `Tlamatini/tlamatini.log` (next to `manage.py`) |
| Frozen (PyInstaller) | Next to the executable |

Characteristics:

- **Truncated on every restart** (mode `'w'`).
- **No rotation, no size cap.** Long sessions grow unbounded — copy or rename before restart if you need history.
- **Stream-level**, upstream of Django's logging config — picks up `print()` calls and third-party stdout too.
- **HTTP GET noise filter**: successful `"GET /…" 200/304` lines are silenced (the per-poll runtime status pings flooded the log otherwise). Non-2xx/3xx GETs stay visible — real failures are still surfaced.

When debugging an issue, `tlamatini.log` is the first artifact to consult.

## 36. ASCII / box-drawing diagrams in chat

LLM-generated ASCII art / flowcharts / column layouts render in the chat with a fixed-width font and preserved whitespace. The LLM is instructed (rule 13 in `prompt.pmt`) to wrap diagrams in `BEGIN-DIAGRAM` / `END-DIAGRAM` markers. There is also auto-detection: any run of consecutive lines containing box-drawing characters (`│┃|─━┌┐└┘├┤┬┴┼╭╮╯╰`), arrow glyphs (`▲▼►◄→←↑↓`), or ASCII-art runs (`+`, `-`, `=`, `|`) is wrapped automatically. Both pipelines emit `<pre class="ascii-diagram">…</pre>` HTML.

---

# Part VII — Configuration Reference

The main file is `Tlamatini/agent/config.json`.

| Mode | Resolution order |
|---|---|
| Source | `Tlamatini/agent/config.json` |
| Frozen | `<install-dir>/config.json` next to the executable |
| Both | `CONFIG_PATH` env var, if set, wins over both |

## 37. LLM settings

```json
{
  "embeding-model": "qwen3-embedding:8b",
  "chained-model": "glm-5:cloud",
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_token": "",
  "ANTHROPIC_API_KEY": "config you api key here by claude",
  "GEMINI_API_KEY": "config your api key here by gemini",
  "enable_unified_agent": true,
  "unified_agent_model": "glm-5:cloud",
  "unified_agent_base_url": "http://127.0.0.1:11434",
  "unified_agent_temperature": 0.0,
  "unified_agent_max_iterations": 100,
  "chat_agent_limit_runs": 100
}
```

| Key | What it does |
|---|---|
| `embeding-model` | RAG embedding model. |
| `chained-model` | Primary chat model. |
| `unified_agent_model` | Multi-Turn tool-loop model. Can differ from `chained-model`. |
| `unified_agent_max_iterations` | Hard cap on the tool loop. Default 100. |
| `unified_agent_temperature` | 0.0 for deterministic. |
| `ollama_token` | Bearer token for authenticated remote Ollama. |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | Top-level keys for Tlamatini's own cloud paths (image analysis, Opus client). |
| `enable_unified_agent` | Master switch for the tool-calling chain. |
| `chat_agent_limit_runs` | Wrapped-run listing cap. |

## 38. RAG settings

```json
{
  "chunk_size": 3000,
  "chunk_overlap": 800,
  "max_chunks_per_file": 50,
  "k_vector": 100,
  "k_bm25": 100,
  "k_fused": 150,
  "enable_bm25": true,
  "rrf_k": 60,
  "fetch_k": 300,
  "max_doc_chars": 150000,
  "max_context_chars": 250000,
  "context_budget_allocation": {
    "high_relevance": 0.60,
    "architecture": 0.20,
    "related": 0.15,
    "documentation": 0.05
  },
  "use_llm_extractor": true,
  "use_long_context_reorder": true,
  "metadata_extraction": {
    "enable_code_structure": true,
    "enable_file_role_classification": true,
    "enable_dependency_tracking": true,
    "enable_cross_references": true
  },
  "retrieval_strategy": {
    "enable_multi_stage": false,
    "enable_query_expansion": true,
    "enable_hierarchical_context": true,
    "enable_context_budget_allocation": true
  }
}
```

## 39. Internet search settings

```json
{
  "internet_classifier_model": "deepseek-v3.2:cloud",
  "internet_classifier_max_iterations": 4,
  "internet_hint_words_mode": "extend",
  "internet_hint_words": [],
  "web_summarizer_model": "deepseek-v3.2:cloud",
  "web_context_max_chars": 10000
}
```

## 40. MCP services

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

## 41. ACPX settings

The whole `acpx` block is **optional**. When missing or partial, every value falls back to a safe default. On first boot of an upgrade build, `agent/acpx/service.py::boot_acpx()` calls `ensure_acpx_block_in_config_json()` and **appends the documented default block to your existing `config.json` atomically**.

```json
{
  "acpx": {
    "cwd": "C:/Development/Tlamatini",
    "stateDir": "C:/Users/angel/.tlamatini/acpx-state",
    "probeAgent": "gemini",
    "permissionMode": "approve-reads",
    "nonInteractivePermissions": "deny",
    "timeoutSeconds": 180,
    "agents": {
      "claude":  {
        "command": "C:/Users/angel/AppData/Roaming/npm/claude.cmd",
        "env": { "ANTHROPIC_API_KEY": "sk-ant-api03-..." }
      },
      "gemini":  {
        "command": "C:/Users/angel/AppData/Roaming/npm/gemini.cmd",
        "env": {
          "GEMINI_API_KEY": "AIza...",
          "GOOGLE_API_KEY": "AIza..."
        }
      },
      "qwen":   { "command": "qwen-code", "env": { "DASHSCOPE_API_KEY": "sk-..." } },
      "codex":  { "command": "codex",     "env": { "OPENAI_API_KEY":    "sk-..." } }
    }
  }
}
```

| Key | Default | Description |
|---|---|---|
| `cwd` | Django process cwd | Default working directory used when `acp_spawn` is called without `cwd`. |
| `stateDir` | `~/.tlamatini/acpx-state/` | Directory for `<session>.json` and `<session>.transcript.ndjson`. |
| `probeAgent` | first resolvable | `agent_id` used by `acp_doctor`'s `--version` probe. |
| `permissionMode` | `approve-reads` | One of `approve-reads`, `approve-all` (DANGEROUS), `deny-all`. |
| `nonInteractivePermissions` | `deny` | What to do when a permission prompt fires unattended. `deny` or `fail`. |
| `timeoutSeconds` | 120 | Per-turn timeout for the embedded runtime. |
| `agents` | `{}` | Per-`agent_id` command + `env` overrides on top of the built-in registry. |

### API key setup — two layers, in plain English

**Layer 1 — top-level config keys** (consumed by Tlamatini's own cloud calls):

```json
{ "ANTHROPIC_API_KEY": "sk-ant-...", "GEMINI_API_KEY": "AIza..." }
```

**Layer 2 — per-`agent_id` `env` injection** (consumed by the spawned ACP child):

```json
{
  "acpx": {
    "agents": {
      "claude": { "env": { "ANTHROPIC_API_KEY": "sk-ant-..." } },
      "gemini": { "env": { "GEMINI_API_KEY": "AIza...", "GOOGLE_API_KEY": "AIza..." } }
    }
  }
}
```

How the merge works at spawn time:

1. `build_agent_registry(overrides, env_overrides)` merges per-agent `env` on top of `DEFAULT_ACP_AGENTS[agent_id].env` (override wins on conflict).
2. `AcpSession.spawn_child()` builds the child env as `{**os.environ, **self.spec.env}` — parent process env first, then per-agent override on top. **Explicit `acpx.agents.<id>.env` value wins over an exported shell variable.**

Canonical env var per CLI:

| Agent | Env var(s) | Where to put it |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | Both layers (top-level for Tlamatini, per-agent for the spawned `claude`). |
| `gemini` | `GEMINI_API_KEY` (newer builds also accept `GOOGLE_API_KEY`) | Both layers; per-agent should set both names. |
| `qwen` | `DASHSCOPE_API_KEY` | `acpx.agents.qwen.env`. |
| `codex` | `OPENAI_API_KEY` | `acpx.agents.codex.env`. |
| `cursor` | (own credential store) | usually no env injection needed. |
| `copilot` | (`gh auth login`) | usually no env injection needed. |
| `pi`, `droid`, `iflow`, `kilocode`, `kimi`, `kiro`, `opencode` | per upstream | check each CLI's docs. |

> **Security warning.** `config.json` is tracked by git. Three safer patterns:
>
> 1. **Don't commit the keys.** Use the `regen_secrets.py` script:
>    ```bash
>    python regen_secrets.py --mode push-able   # rewrite secrets to placeholders before commit
>    python regen_secrets.py --mode keyed       # restore from data.keys (gitignored) for local use
>    ```
>    Or run `git update-index --skip-worktree Tlamatini/agent/config.json` after configuring locally.
> 2. **Use shell env vars in development.** Export the keys; leave `acpx.agents.<id>.env` empty.
> 3. **Rotate immediately if a key has been pushed.** Any leaked key should be revoked at the provider before reuse.

### The `setup-new-acpx-key` skill (the easy button)

Instead of editing `config.json` by hand, in chat (Multi-Turn + ACPX ticked):

> "Use `invoke_skill` with `setup-new-acpx-key` to register my Anthropic key for the `claude` agent_id." (paste the key)

The skill walks itself through writing `data.keys`, patching both `config.json` layers, optionally extending `regen_secrets.py`, and verifying via `acp_doctor`.

## 42. Image interpreter

```json
{
  "image_interpreter_base_url": "http://127.0.0.1:11434",
  "image_interpreter_model": "qwen3.5:cloud",
  "image_interpreter_temperature": 0
}
```

## 43. Advanced options

```json
{
  "history_summary_enable": true,
  "history_summary_trigger_tokens": 150,
  "history_keep_last_turns": 3,
  "performance": { "enable_caching": true, "cache_embeddings": true, "parallel_processing": true, "max_workers": 12 },
  "logging": { "log_retrieval_metrics": true, "log_context_size": true, "log_query_rewrites": true, "verbose_metadata": true },
  "load_hidden": true,
  "ssl_verify": false,
  "max_input_tokens": 5000,
  "keep_last_turns": 3
}
```

---

# Part VIII — Deploying & Packaging

## 44. The three-step build pipeline

```
build.py  ──►  build_uninstaller.py  ──►  build_installer.py
   │                   │                         │
   ▼                   ▼                         ▼
pkg.zip          Uninstaller.exe        dist/Tlamatini_Release/
(app bundle)     (project root)           ├─ Installer.exe
                                          ├─ Uninstaller.exe
                                          ├─ pkg.zip
                                          └─ _internal/
```

The final distributable is `dist/Tlamatini_Release/` — zip the folder, share it.

### Step 1 — `build.py`

```bash
python build.py
```

Installs deps, runs `collectstatic`, executes PyInstaller, copies required payloads (including `README.md` and bundled `jd-cli/`), runs migrations, creates the default user (`user`/`changeme`), renames the exe to `Tlamatini.exe`, copies agent templates, bundles support scripts (`register_flw.ps1`, `CreateShortcut.ps1`, `Tlamatini.ps1`, `.ico`), and zips it all into **`pkg.zip`**.

`build.py` is strict: missing `README.md`, missing `jd-cli/`, or missing `jd-cli.bat` causes a non-zero exit instead of a silent half-package.

### Step 2 — `build_uninstaller.py`

```bash
python build_uninstaller.py
```

Builds `uninstall.py` into a single `--onefile` Tkinter exe. Output: `Uninstaller.exe` at the project root.

### Step 3 — `build_installer.py`

```bash
python build_installer.py
```

Requires `pkg.zip` and `Uninstaller.exe` from steps 1 and 2. Builds `install.py` with `--onedir --windowed` and a splash screen, copies `pkg.zip` and `Uninstaller.exe` into `dist/Installer/`, and assembles `dist/Tlamatini_Release/` with SHA-256 verification.

## 45. What the installer does

When an end user runs `Installer.exe`:

1. Tkinter GUI to choose installation directory.
2. Extracts `pkg.zip` into `<install_path>/Tlamatini/`.
3. Locks agent venv permissions.
4. Writes `config.json` with installation settings.
5. Copies `Uninstaller.exe` into the install dir.
6. Creates desktop and Start Menu shortcuts (`Tlamatini.lnk`).
7. Registers `.flw` extension to open with Tlamatini.
8. Cleans the PyInstaller bundle path from helper subprocess environments so PowerShell helpers and Explorer restarts don't stall.

## 46. What the uninstaller does

1. Removes shortcuts (with Explorer restart for immediate effect).
2. Unregisters the `.flw` association and clears cached shell state.
3. Deletes all application files **except** `<install_path>/Tlamatini/agents/*` (preserves user-created agents).
4. Removes the install directory if empty.

## 47. Frozen-mode behavior

The Multi-Turn implementation carries frozen-build awareness in supporting runtime code:

- `config_loader.py` resolves `CONFIG_PATH`, then executable-local `config.json`, then module-local.
- `FileSearchRAGChain` resolves its default `config.json` from the executable directory in frozen mode.
- Template-agent discovery checks both `<install_dir>/agents` and `<install_dir>/Tlamatini/agent/agents`.
- `_get_agents_root()` in `chat_agent_runtime.py` resolves from `sys.executable` in frozen mode, from `__file__` in source mode — both paths are logged at INFO level.
- `_resolve_python_executable()` tries `PYTHON_HOME`, then bundled `python.exe` beside the frozen executable, then PATH.

---

# Part IX — The Command Deck (API + WebSocket)

## 48. WebSocket protocol

Endpoint: `ws://<host>/ws/agent/`.

### Client → Server (chat)

```json
{
  "message": "Your question here",
  "multi_turn_enabled": true,
  "exec_report_enabled": true,
  "acpx_enabled": true
}
```

Optional toggles. `multi_turn_enabled=false` falls back to legacy one-shot.

### Client → Server (control)

| Type | Purpose |
|---|---|
| `set-canvas-as-context` | Use the current canvas file as context |
| `unset-canvas-as-context` | Remove the canvas file from context |
| `set-directory-as-context` | Load a directory as context |
| `set-file-as-context` | Load a single file as context |
| `cancel-current` | Cancel the current generation |
| `reconnect-llm-agent` | Rebuild the current LLM/RAG chain |
| `clean-history-and-reconnect` | Clear chat history and rebuild |
| `clear-context` | Remove persisted context and rebuild |
| `cancel-all` | Cancel all active generation |
| `save-files-from-db` | Persist canvas / DB-backed files |
| `enable-llm-internet-access` | Enable internet access for the LLM |
| `disable-llm-internet-access` | Disable internet access for the LLM |
| `view-context-dir-in-canvas` | Show the current context directory tree in the canvas |
| `set-file-omissions` | Update file omission patterns |
| `set-mcps` | Persist MCP enablement |
| `set-tools` | Persist tool enablement |
| `set-agents` | Persist agent enablement |

### Server → Client

```json
{ "message": "Processing request...", "username": "Tlamatini" }
```

```json
{ "type": "session-restored", "context_type": "directory", "context_path": "/path/to/project" }
```

A successful Multi-Turn message also carries `tool_calls_log`, `multi_turn_used`, `answer_success` for the Create Flow gate.

## 49. HTTP endpoints

The backend currently exposes 103 routes. Highlights:

### Pages

| Endpoint | Method |
|---|---|
| `/` | GET/POST (login) |
| `/welcome/` | GET |
| `/agent/` | GET (chat) |
| `/agentic_control_panel/` | GET (designer) |
| `/logout/` | GET |

### Data loading

| Endpoint | Method |
|---|---|
| `/load_canvas/<filename>/` | GET |
| `/load_prompt/<prompt_name>/` | GET |
| `/load_omissions/<omission_name>/` | GET |
| `/load_mcp/<mcp_name>/` | GET |
| `/load_tool/<tool_name>/` | GET |
| `/load_agent/<agent_name>/` | GET |
| `/load_agent_description/<agent_name>/` | GET |
| `/load_agent_config/<agent_name>/` | GET |

### Agent management

| Endpoint | Method |
|---|---|
| `/save_agent_config/<agent_name>/` | POST |
| `/deploy_agent_template/<agent_name>/` | POST |
| `/ensure_agent_exists/<agent_name>/` | GET |
| `/execute_starter_agent/<agent_name>/` | POST |
| `/execute_ender_agent/<agent_name>/` | POST |
| `/check_starter_log/<agent_name>/` | GET |
| `/check_ender_log/<agent_name>/` | GET |
| `/check_agents_running/<agent_name>/` | GET |
| `/check_all_agents_status/` | GET |
| `/read_agent_log/<agent_name>/` | GET |
| `/restart_agent/<agent_name>/` | POST |
| `/restart_agents/` | POST |
| `/asker_choice/<agent_name>/` | POST |
| `/execute_flowhypervisor/<agent_name>/` | POST |
| `/check_flowhypervisor_alert/<agent_name>/` | GET |
| `/validate_flow/` | GET |

### Flow Compiler & Agent Contracts (since commit `0bea21d`, May 2026)

| Endpoint | Method | Notes |
|---|---|---|
| `/agent/compile_flow/` | POST | Backend Flow Compiler. Body: `{ "mode": "dry_run"\|"write", "flow": <ACP snapshot> }`. Save / Validate use `dry_run`; Start uses `write` to materialize `config.yaml` and `interconnection-scheme.csv` into the session pool. |
| `/agent/flow_from_tool_calls/` | POST | Chat Create-Flow normalizer. Body: `{ "tool_calls_log": [...], "flow_data": <legacy draft> }`. Returns a registry-canonical, secret-redacted `.flw` JSON. |
| `/agent/agent_contracts/` | GET | Returns the live `AgentContract` registry summary — connection-field shape, parametrizer source-fields, secret paths, singleton/long-running/never-starts-targets/excluded-from-validation flags. Used for diagnostics and for any out-of-tree client (e.g. a future MCP server) that needs to introspect the agent surface. |

### Connection updates (canvas auto-configuration)

`/update_<agent>_connection/<agent_name>/` for every agent type that has connections — Starter, Ender, Stopper, Raiser, Emailer, Monitor-Log, Notifier, Executer, Pythonxer, Sqler, Whatsapper, Recmailer, OR, AND, Croner, Mover, Mouser, Keyboarder, Sleeper, Cleaner, Deleter, Asker, Forker, Dockerer, Pser, Kuberneter, Apirer, Jenkinser, Crawler, Summarizer, FlowHypervisor, Counter, File-Interpreter, Image-Interpreter, Gatewayer, Gateway-Relayer, Node-Manager, File-Creator, File-Extractor, J-Decompiler, Kyber-KeyGen/Cipher/DeCipher, Parametrizer, FlowBacker, Barrier, Googler, TeleTlamatini, WhatsTlamatini, ACPXer.

Plus the Parametrizer-specific pair:

| Endpoint | Method |
|---|---|
| `/get_parametrizer_dialog_data/<agent_name>/` | GET |
| `/save_parametrizer_scheme/<agent_name>/` | POST |

### Session & pool

| Endpoint | Method |
|---|---|
| `/session_state/` | GET |
| `/save_session_state/` | POST |
| `/clear_session_state/` | POST |
| `/clear_pool/` | POST |
| `/cleanup_session/` | POST |
| `/clear_agent_logs/` | POST |
| `/clear_pos_files/` | POST |
| `/reanimate_agents/` | POST |
| `/save_paused_agents/` | POST |
| `/load_paused_agents/` | GET |
| `/delete_paused_agents/` | POST |
| `/delete_agent_pool_dir/<agent_name>/` | POST |
| `/get_session_running_processes/` | GET |
| `/kill_session_processes/` | POST |

### Open in… external editors

| Endpoint | Method |
|---|---|
| `/agent/detect_installed_apps/` | GET — returns which of File Explorer / VS Code / Antigravity are installed |
| `/agent/open_in_app/` | POST — accepts `app_id` plus `directory` or `agent_name`; resolves the current session pool instance directory |

---

# Part X — Survival Guide (Troubleshooting)

## 50. Common issues

### Ollama connection failed

- Run `ollama serve` in a dedicated terminal.
- Check `ollama_base_url` in `config.json` is `http://127.0.0.1:11434`.
- `ollama list` shows your pulled models.
- Remote Ollama? Set `ollama_token` for bearer auth.

### RAG context not loading

- Look for the green confirmation banner after Set Context.
- Check file permissions and that files are text (not binary).
- Hit `max_doc_chars`? Bump the limit.
- "Out of memory" during embedding? You're now in fallback mode — answers still work, retrieval quality degrades. Fix by switching to a smaller embedding model.

### Multi-Turn not engaging

- Did you tick the **Multi-Turn** checkbox?
- `enable_unified_agent: true` in `config.json`?
- Look for `[Planner._select]` in the console — it shows scoring decisions.
- "Tool X is not available"? The planner did not select X. Verify X is enabled in the Tools dialog and that your prompt has matching keywords.

### ACPX child not capturing answers

If transcripts only show outbound prompts and no inbound responses, your build is older than May 2026. Update — the fix is `transport="oneshot-prompt"` for claude/gemini/cursor/qwen/codex (re-spawn per turn with `-p "<task>"`).

### Frozen build uses wrong config

- Place `config.json` next to the executable, or set `CONFIG_PATH`.
- Verify `agents/` directory exists in the install.
- Rebuild if `README.md`, `jd-cli/`, or template directories are missing.

### WebSocket disconnections

- Check network stability.
- Increase Daphne timeouts.
- Verify no proxy is interfering.
- Browser console for errors.

### Agent not starting

- Check the agent's log in the pool directory.
- `config.yaml` valid YAML?
- Port conflicts with MCP servers? Change ports in config.
- Use **Read Log** in the workflow designer.

### Memory issues

- Reduce `chunk_size` and `k_vector` / `k_bm25`.
- Lower `max_chunks_per_file`.
- Reduce `max_context_chars`.

### Image analysis fails

- Claude path: check `ANTHROPIC_API_KEY` (and that you have credits).
- Qwen path: verify the vision model is pulled (`ollama list`) and that `image_interpreter_base_url` points at the right Ollama.
- Image format must be supported (jpg/png/gif/bmp/tiff/webp/svg/ico/heic/avif).

### Forker / Asker not routing

- Verify `pattern_a` / `pattern_b` actually appear in the source agent's log output.
- `source_agents` and `target_agents_a/b` populated by the canvas auto-config?
- Read the Forker/Asker log for pattern-matching diagnostics.
- Asker only: did the browser dialog appear? Check console errors.

## 51. Debug mode

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

INFO-level loggers configured in `tlamatini/settings.py`:

| Logger | What it logs |
|---|---|
| `agent.chat_agent_runtime` | Runtime dir creation, template copy, subprocess launch, PID, Python executable selection |
| `agent.tools` | Wrapped chat-agent launch lifecycle |
| `agent.mcp_agent` | Multi-turn tool invocation: which tools called, args, return values |
| `agent.global_execution_planner` | Planner scoring, selected tools, threshold, top score |
| `agent.capability_registry` | Capability scoring details |

All log lines are prefixed with timestamp and logger name (e.g. `2026-04-13 12:28:39 [agent.tools] INFO …`).

## 52. Log locations

| What | Where |
|---|---|
| Django / Multi-Turn console | stdout |
| **Application-wide** | `Tlamatini/tlamatini.log` (truncated on every start; see §35) |
| ACP workflow agent logs | `<pool_directory>/<agent_name>/<agent_name>.log` |
| Chat-launched wrapped agents | `agent/agents/pools/_chat_runs_/<agent>_<seq>_<id>/<agent>_<seq>_<id>.log` (failed runs preserved) |

---

# Appendix A — Keyboarder Supported Keys

The **Keyboarder** agent simulates human keyboard input through the `input_sequence` field.

- **Literal strings**: enclose in single or double quotes — `'Hello World'`.
- **Simultaneous keys**: join with `+` — `ctrl+c`, `shift+alt+delete`.
- **Sequential commands**: separate with commas — `escape, escape, ctrl+c, 'hello'`.

| Category | Supported keys |
|---|---|
| **Modifiers** | `ctrl`, `shift`, `alt`, `altgr`, `win`, `windows`, `command`, `option` |
| **Arrows** | `left`, `<-(left arrow)`, `right`, `->(right arrow)`, `up`, `up arrow`, `down`, `down arrow` |
| **Navigation** | `home`, `end`, `pageup`, `pgup`, `pagedown`, `pgdn` |
| **Editing** | `enter`, `return`, `esc`, `escape`, `backspace`, `space`, `tab`, `del`, `delete`, `insert` |
| **Locks** | `capslock`, `mayus`, `mayuscula`, `numlock`, `scrolllock` |
| **Function keys** | `f1` through `f24` |
| **Media & system** | `volumedown`, `volumeup`, `volumemute`, `playpause`, `nexttrack`, `printscreen`, `prtsc`, `pause`, `apps` |
| **Symbols & numbers** | digits `0`–`9`, common punctuation, `\n`, `\r`, and `/`, `\\`, `[`, `]`, `-`, `=`, `,`, `.`, `;`, `'`, `` ` ``, `{`, `}`, `~`, `!`, `?`, `@`, `#`, `$`, `%`, `&`, `*`, `+`, `<`, `>` |

*Commands are case-insensitive internally; literal quoted text preserves your exact capitalization.*

---

# Appendix B — Glossary

| Term | Definition |
|---|---|
| **ACPX** | Agent Communication Protocol eXtension — Tlamatini's runtime for spawning external coding-agent CLIs as child processes and brokering them as LLM tools. |
| **Agent** | An autonomous Python process that performs a specific workflow task. |
| **Apirer** | HTTP/REST API agent. |
| **Asker** | Interactive A/B path chooser; pauses for user dialog. |
| **ASGI** | Asynchronous Server Gateway Interface — Python standard for async web servers. |
| **Barrier** | Synchronization barrier; fires when ALL N source agents have started. |
| **BM25** | Best Matching 25 — probabilistic keyword retrieval algorithm. |
| **Canvas** | The right-hand code panel in the chat *and* the drag-and-drop area in the designer. Context-dependent. |
| **Cardinal** | Numeric suffix added to deployed agents to support multiple instances (e.g. `monitor_log_1`). |
| **Chunk** | A segment of a document after splitting for processing. |
| **Context Budget** | Allocation strategy that distributes the token limit across document types. |
| **Counter** | Persistent counter agent with L/G threshold routing. |
| **Crawler** | Developer-oriented web crawler (raw mode + LLM analysis). |
| **Daphne** | HTTP/HTTP2/WebSocket protocol server for ASGI. |
| **Dockerer** | Docker container management agent. |
| **Embedding** | Numerical vector representation of text for similarity comparison. |
| **FAISS** | Facebook AI Similarity Search — vector similarity library. |
| **File-Creator / File-Extractor / File-Interpreter** | File creation / raw-text extraction / LLM-aided document parsing. |
| **Flow Validation** | Pre-execution structural check (no orphans, no self-connections, terminal agents reachable). |
| **FlowBacker** | Post-Ender backup of session logs/configs. |
| **FlowCreator** | LLM that designs flows from natural-language objectives. |
| **FlowHypervisor** | LLM watchdog over running agents; outputs `OK` or `ATTENTION NEEDED { … }`. |
| **Forker** | Automatic A/B path router based on log patterns. |
| **Gatewayer** | Inbound webhook / folder-drop gateway. |
| **Gateway-Relayer** | Bridges provider-native webhooks (GitHub) into Gatewayer's HMAC format. |
| **Gitter** | Git operations agent. |
| **Googler** | Google search via Playwright. |
| **Image-Interpreter** | LLM vision agent for image analysis. |
| **J-Decompiler** | Java JAR/WAR decompiler using bundled `jd-cli`. |
| **jd-cli** | Java Decompiler CLI tool bundled with the application. |
| **Jenkinser** | CI/CD pipeline trigger agent. |
| **Keyboarder** | Deterministic PyAutoGUI-based keyboard automation. |
| **Kyber-KeyGen / Cipher / DeCipher** | CRYSTALS-Kyber post-quantum encryption agents. |
| **LangChain** | Framework for LLM applications. |
| **LangGraph** | Stateful, multi-actor LangChain extension. |
| **Logic Gate** | Agent that performs boolean operations (AND/OR/Barrier) on events. |
| **MCP** | Model Context Protocol — standard for tool/context communication. |
| **Mouser** | PyAutoGUI-based pointer movement agent. |
| **NodeManager** | Long-running infrastructure registry that probes nodes. |
| **Notifier** | LangGraph-based browser-notification agent. |
| **output_agents** | Config field used by Ender, Stopper, Cleaner for downstream canvas wiring (vs `target_agents` for "agents to start"). |
| **Parametrizer** | Strict single-lane queue that maps source-agent log segments into target-agent config.yaml. |
| **Pool** | Directory where deployed agent instances are stored. |
| **Pser** | LLM-powered fuzzy process finder. |
| **Pythonxer** | Inline-Python agent with Ruff lint + exit-code gating. |
| **PyAutoGUI** | Python library for mouse/keyboard control, used by Mouser and Keyboarder. |
| **RAG** | Retrieval-Augmented Generation. |
| **Reanimation Offset** | Saved log-file position to handle restarts and rotation. |
| **Recmailer** | LangGraph IMAP receiver with LLM keyword analysis. |
| **RRF** | Reciprocal Rank Fusion — method for combining ranked lists. |
| **Ruff** | Fast Python linter used by Pythonxer. |
| **Skill** | Markdown-driven extension package — a directory under `agent/skills_pkg/<name>/` with a `SKILL.md` (YAML frontmatter + body). 21 seed skills ship. |
| **Stopper** | Single-threaded pattern-based agent terminator. |
| **Summarizer** | LLM polls source logs for events. |
| **Tlamatini** | Nahuatl for "one who knows" — and the name of this assistant. The LLM responds to it as a self-reference. |
| **TextMeBot** | Third-party WhatsApp messaging API. |
| **WebSocket** | Full-duplex protocol over TCP. |

---

# Appendix C — Changelog

### Recent Updates

- **Flow Compiler + Agent Contracts + 60-agent catalog — May 2026** — A backend pipeline that turns the live ACP canvas snapshot OR a Chat-generated Create-Flow draft into validated, secret-redacted, source-and-frozen-portable `config.yaml` files (commit `0bea21d`). Four new modules under `agent/services/`: `agent_contracts.py` (the `AgentContract` registry — per-agent connection-field shape per slot, parametrizer source-fields, `secret_paths`, plus `singleton` / `long_running` / `never_starts_targets` / `exclude_from_validation` flags; lru-cached, alias-normalized, disk-discovered + builtin overrides), `agent_paths.py` (frozen/source-aware pool resolution + canvas-id normalization that handles `Node Manager` → `node_manager`, `Gateway-Relayer` → `gateway_relayer`, `(2)` cardinal stripping), `flow_spec.py` (`FlowNode` / `FlowConnection` / `FlowSpec` dataclasses + `normalize_flow_payload()` / `flow_spec_to_legacy_json(redact=True)` — schema_version=2 in-memory representation that both browser surfaces compile through), and `flow_compiler.py` (`compile_flow_spec()` / `compile_flow_payload()` / `list_pool_agents_for_validation()` — wires every connection per its contract, clears stale wiring before re-writing, redacts secrets, and writes `config.yaml` + `interconnection-scheme.csv` into the session pool when called with `write=True`). Three new endpoints expose the pipeline: `POST /agent/compile_flow/` (called from the new `acp-flow-snapshot.js::compileCurrentACPFlow` with `mode='write'` from Start and `mode='dry_run'` from Validate), `POST /agent/flow_from_tool_calls/` (called from `agent_page_chat.js::_normalizeChatFlowBeforeDownload`), and `GET /agent/agent_contracts/` (registry diagnostics). **User-visible effect**: Start now compiles the live canvas before launching agents, so an edited-but-unsaved canvas behaves identically to a fresh `.flw` load; Create Flow downloads are now registry-canonical and have known secret fields stripped server-side; Validate previews the same compiled output Start would write, without touching disk. The catalog count is now **60** (was 59 — FlowCreator was always present on disk and in `agents_descriptions.md` but missing from the AI-onboarding catalog list). Coverage: `Tlamatini/agent/test_flow_contracts.py` pins source-mode resolution, alias normalization, the Ender kill-list contract, and Parametrizer-mappings-as-CSV-artifact behavior.

- **`agents_descriptions.md` becomes the authoritative source for sidebar tooltips and canvas Description dialogs — May 2026** — A new file at the repo root (commit `88dd99b`) holds the human-readable description for every workflow agent in `## Workflow Agents` Markdown tables. The Django view `agent.views.agentic_control_panel` parses it via `_load_agent_purpose_map()` → `_resolve_agent_descriptions_search_paths()`, probing `agents_descriptions.md` first (next to `manage.py` in source mode, next to `sys.executable` in frozen mode) and falling back to `README.md` only if it's absent or yields zero rows. The lookup is case- and punctuation-insensitive — `re.sub(r'[^a-z0-9]+', '', name.lower())` keys "Kyber-KeyGen", "Kyber KeyGen", and "kyberkeygen" to the same row. Editing a row changes both human docs AND the live UI text — **there is no other source of truth**. `build.py` ships `agents_descriptions.md` next to the executable in frozen mode (`required_file_copies` was extended). UI fallback strings in `acp-canvas-core.js::showAgentPurposeTooltip` and `contextual_menus.js::openDescriptionDialog` were updated to mention the new file. The legacy alias `_load_agent_purpose_map_from_readme = _load_agent_purpose_map` is preserved so any out-of-tree caller keeps working. Companion change: `regen_secrets.py` was extended to scrub `emailer/config.yaml` and `recmailer/config.yaml` (Gmail app-password fields). Coverage: `agent/tests.py::AgentPurposeMapResolutionTests`.

- **TeleTlamatini Three-Flag Bridging (Multi-Turn + Exec Report + ACPX) — May 2026** — Each Telegram message TeleTlamatini forwards to Tlamatini now carries `multi_turn_enabled`, `exec_report_enabled`, AND `acpx_enabled` verbatim (commit `1287e56`), so a Telegram user gets exactly the operational surface a browser user with all three checkboxes ticked would. `TlamatiniBridge.__init__` accepts `acpx_enabled`, includes it in the request envelope, and logs it; `agent/agents/teletlamatini/config.yaml` ships `acpx_enabled: true` so a fresh deploy can drive the full ACPX scheme out of the box. The resolver-level default stays `False` — that's the legacy-deploy backstop, not the user-facing knob. Practical pairing for users wiring TeleTlamatini today: leave all three flags `true` in `config.yaml`, and Telegram becomes a full ACPX-aware Tlamatini console — "use ACPX to spawn claude and ask it to summarize the current branch" works the same from a phone. WhatsTlamatini is the next mirror candidate; until then it remains Multi-Turn + Exec Report only.

- **Autonomous Multi-Turn Mode + 4 New Wrapped Tools (Sleeper, Mouser, run_wait, window_present) — May 2026** — A focused pass to make Multi-Turn fully autonomous on desktop-UI tasks ("open notepad, type X, wait 30 s, close it" — five tool calls, no vision LLM, no polling). Eight changes landed together (commit `84de29b`):
    1. **Repetition-breaker exemption** for the new background-friendly waiters so they don't get short-circuited as duplicates.
    2. **`filetype_exclusions` analyzer fix** so the parameter is correctly forwarded across File-Interpreter / Image-Interpreter / File-Extractor / Mover / Deleter.
    3. **Tighter prompt rule 11 (Desktop-UI lifecycle)** — codifies the canonical pattern `launch → interact → close (alt+f4) → handle save dialog (alt+n / alt+s) → optional verify`, **forbids** the Shoter+Image-Interpreter "did the window open?" gate between launch and the first Keyboarder/Mouser action, and adds the locate-then-click decision matrix (window-title click / locate_image / vision pipeline / drag / scroll / chain-click).
    4. **Capability-registry boost** for the desktop-UI siblings so the planner reliably co-selects Keyboarder + Mouser + Sleeper on Notepad-style requests.
    5. **Shoter `output_path`** exposed so the LLM can pass the screenshot path directly into the next tool call.
    6. **`chat_agent_sleeper`** registered (migration `0080_add_chat_agent_sleeper_tool`) — canonical millisecond waiter; do NOT spin Pythonxer for `time.sleep`, do NOT use `execute_command` with `timeout /t`.
    7. **`window_present(title)`** — fast (<100 ms) yes/no helper backed by `pyautogui.getWindowsWithTitle`. Reserve `chat_agent_image_interpreter` for genuine vision tasks (reading content, OCR), never for "is X visible?" gates that exhaust the 256-iteration budget waiting on 20-30 s vision calls.
    8. **`chat_agent_run_wait`** — blocks until a wrapped run reaches a terminal status (or `max_seconds` fires); replaces busy-poll loops over `chat_agent_run_status`. Migration `0081_add_window_present_and_run_wait_tools` seeds both `Tool` rows. Keyboarder and Mouser quote-decoding got a precise lookahead fix in the same pass (`''Hi!, I''m Tlamatini''` now types `Hi!, I'm Tlamatini` correctly across all 5 input variants the LLM produces).

    **Test coverage:** 266-test suite green, zero regressions, ruff clean.

- **Mouser Wrapped for Multi-Turn (`chat_agent_mouser`) — May 2026** — Mouser becomes a first-class Multi-Turn tool (commit `4eb6fc7`, migration `0079_add_chat_agent_mouser_tool`). Six movement modes: `click_at_window` (focuses a window by title substring + anchor — bullet-proof for "click into Notepad before typing", no screenshot/vision call), `locate_image` (`pyautogui.locateCenterOnScreen` against a reference PNG with configurable confidence), `localized` (smooth-easing move to absolute coordinates with optional click), `random` (across-screen movement for a configurable duration), `drag` (button held between two points), and `scroll`. Wrapped result exposes `movement_type`, `end_posx`, `end_posy`, `button_click`, `clicked` (bool), and `located_via` as top-level fields. Mouser is state-changing (it switches the foreground window and fires button events), so the row is captured under `agent_key="mouser"` in `_EXEC_REPORT_TOOLS` with its own caption gradient mirroring `.canvas-item.mouser-agent`.

- **Keyboarder + Shoter Wrapped for Multi-Turn (`chat_agent_keyboarder` / `chat_agent_shoter`) — May 2026** — Both desktop-UI agents become Multi-Turn tools (commit `93804e7`, migration `0078_add_chat_agent_keyboarder_tool`). Shoter (`chat_agent_shoter`) is read-only screenshot capture; Keyboarder (`chat_agent_keyboarder`) accepts `input_sequence` (literal text in single/double quotes; key names and `+`-joined chords go bare; comma-separated tokens) and `stride_delay` (ms between strokes). Unblocks the canonical "open notepad → verify → type into it" flow. Keyboarder is state-changing (keystrokes target the foreground window) so its row appears in the Exec Report under `agent_key="keyboarder"`; Shoter remains read-only and stays out of the report on purpose. pyautogui hotkey names are normalized via `get_pyautogui_key()` (`escape→esc`, `windows→win`, `altgr→altright`, `mayus/caps→capslock`); pass `'win+r'`, `'ctrl+alt+t'`, etc.

- **ASCII / Box-Drawing Diagrams Rule (Rule 13) — May 2026** — A new prompt rule (#13 in `agent/prompt.pmt`) and a corresponding renderer in `agent/services/response_parser.py` ensure that LLM-generated ASCII art / box-drawing flowcharts / column layouts render in the chat with a fixed-width font and preserved whitespace. The LLM is instructed to wrap diagrams in `BEGIN-DIAGRAM` / `END-DIAGRAM` markers (mirroring the `BEGIN-CODE` / `END-CODE` pair, but without a filename slot). Two pipelines feed the same renderer: explicit `BEGIN-DIAGRAM` blocks AND auto-detection of consecutive lines that contain box-drawing characters (`│┃|─━┌┐└┘├┤┬┴┼╭╮╯╰`), arrow glyphs (`▲▼►◄→←↑↓`), or ASCII-art runs (`+`, `-`, `=`, `|`). Both replace the matched region with a `\x00DGRM_<idx>\x00` placeholder so the bold/inline-code/lang-marker substitutions that run later cannot corrupt the diagram contents — placeholders are restored last as `<pre class="ascii-diagram">…</pre>` in the rendered HTML. New regex `REGEX_DIAGRAM_BLOCK` lives in `agent/constants.py`. Coverage: `agent/tests.py` adds 178 lines of regression tests covering box-drawing, arrow, piped-box, and pure ASCII-art runs.

- **`tlamatini.log` HTTP-GET Noise Filter — May 2026** — `Tlamatini/tlamatini/logging_filters.py` now silences successful `"GET /…" 200` and `"GET /…" 304` lines (the per-poll runtime status pings that flooded the unified log every ~3 s when the runtime poller was active) but keeps any GET that returned a non-2xx/3xx status, so real failures stay visible. Combined with the earlier fix that promoted `disappearing boring log lines` (commit `8bb4047`), the application log is now a near-zero-noise debugging artefact during normal operation.

- **ACPX Toolbar Toggle (Per-Request Enable/Disable, defaults to OFF) — May 2026** — The chat toolbar now exposes three checkboxes side-by-side: **Multi-Turn**, **Exec Report**, and **ACPX**. The new ACPX checkbox (`#acpx-enabled` in `agent/templates/agent/agent_page.html`) **defaults to unchecked** — JS hydration in `agent_page_state.js::applyStoredAcpxState` falls back to `false` when sessionStorage has no prior value, and every backend read site defaults `acpx_enabled` to `False` (`rag/interface.py::ask_rag` dict + raw-string paths, `rag/factory.py`, `rag/chains/unified.py` payload-rebuild whitelist in three places, `mcp_agent.py::CapabilityAwareToolAgentExecutor.invoke`, and `consumers.py::receive` plus the `queue_llm_retrieval` signature). The flag is sent on every WebSocket request; the planner / executor call `agent.acpx.filter_acpx_tools(tools, acpx_enabled)` to strip the entire 12-tool ACPX/Skill surface from the bound tool list when the flag is `False`. Net result: the default Multi-Turn request behaves exactly like the legacy pre-ACPX Multi-Turn flow — the planner never even sees the ACPX tools — and the user must explicitly tick the box to opt into the ACPX-aided flow.

- **Summarizer One-Shot Mode + `chat_agent_summarize_text` Tool — May 2026** — `agent/agents/summarizer/summarizer.py` now accepts a one-shot path: when `input_text` is non-empty AND `source_agents` is empty, the agent skips the polling loop entirely, sends `input_text` directly to the LLM with the resolved prompt (built from `target_words` if no `system_prompt` is provided), emits exactly one `INI_SECTION_SUMMARIZER<<<` block, and triggers `target_agents` whenever the summary is non-empty. The wrapped chat tool `chat_agent_summarize_text` is the canonical caller — its `example_request` is `Summarize with input_text='<full text>' and target_words=40`.

- **`setup-new-acpx-key` Skill — May 2026** — A new in-process skill (`agent/skills_pkg/setup_new_acpx_key/SKILL.md`, registered as skill #21) that walks the LLM through credential injection for any `agent_id` from the ACPX registry end-to-end: writes `data.keys`, patches both layers of `config.json` (top-level for callers like `image_interpreter.py` / `opus_client.py`; `acpx.agents.<id>.env` for the spawned child), optionally extends `regen_secrets.py` when introducing a brand-new key, then verifies via `acp_doctor`. Documents the canonical env-var map (claude → `ANTHROPIC_API_KEY`, gemini → `GEMINI_API_KEY` + `GOOGLE_API_KEY` alias, codex → `OPENAI_API_KEY`, qwen → `DASHSCOPE_API_KEY`) and the `{**os.environ, **spec.env}` merge order so explicit `acpx.agents.<id>.env` always wins over an exported shell variable.

- **`regen_secrets.py` Two-Mode Scrubber/Restorer — May 2026** — A new repo-root script (`regen_secrets.py`) that toggles `Tlamatini/agent/config.json` between two states: `--mode push-able` rewrites real secrets (top-level `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_TOKEN` and the `acpx.agents.<id>.env` blocks) into `<KEY goes here>` placeholders so the file is safe to commit; `--mode keyed` restores values from `data.keys` (gitignored, `KEY=VALUE` format) so the local working tree stays usable.

- **Console Window + App-Icon Polish, Restrictive-Policy-Friendly Shortcut — May 2026** — `Tlamatini/manage.py` now sets the console window title to `Tlamatini` and binds the `Tlamatini.ico`. The same icon is wired into `build.py` (PyInstaller exe icon), `templates/agent/{login,welcome,agent_page,agentic_control_panel}.html` (favicon for every web page), and `register_flw.ps1`. `CreateShortcut.ps1` was rewritten to fall back to user-scoped paths when machines have restrictive Group Policies that disallow Public Desktop / All-Users Start Menu writes.

- **ACPX `oneshot-prompt` Transport — Capturing Claude / Gemini / Cursor / Qwen / Codex Responses on Windows — May 2026** — The previous transport-aware drain landed sub-second spawns and a fast idle rule, but on Windows the actual answer text from TUI agents (Gemini CLI, Cursor, Qwen, Claude Code) was **never captured**. Their JS-based TUIs detect a piped stdout and refuse to flush — so the transcript only carried the outbound prompt. Fix: new `transport="oneshot-prompt"` profile re-spawns the CLI fresh per turn with the prompt as a CLI argument; stdin is closed immediately, and `proc.communicate(timeout=180)` captures stdout and stderr to EOF — the same non-interactive mode each CLI ships for unattended use. Five agents migrated. Generous defaults (180 s timeout / 10 s idle / 2 s grace). No inter-turn child state — each `acp_send` is a brand-new CLI invocation. ACPXer canvas counterpart updated in lockstep.

- **ACPXer — Visual ACPX Session Driver — May 2026** — A new workflow agent (#59 in the visual ACP designer; migration `0076_add_acpxer`) that brings ACPX mechanics into the canvas. One ACPXer node = one ACPX session lifecycle. Self-contained; does NOT import `agent.acpx` (mirrors runtime mechanics inline because pool subprocesses can't import `agent.*`). Byte-compatible NDJSON transcripts. Parametrizer-compatible `INI_SECTION_ACPXER<<<` output enables visual multi-CLI relay flows like `Starter → ACPXer(claude) → Parametrizer → ACPXer(gemini) → File-Creator → Ender`. Aurora Conduit gradient (cosmic-navy → electric-violet → luminous-magenta → cyan-radiance) distinct from the `.acpx-agent` exec-report row.

- **ACPX Reliability Pass — May 2026** — Cross-cutting changes that took ACPX execution from "hangs at 45 s per spawn on TUI agents" to "sub-second spawn + 2 s idle on silent REPLs". Per-leg latency dropped from ~91 s to **~9 s** (~10× faster end-to-end). Bundles eight related improvements: expanded ACPX tool surface (5 new tools, migration `0075`); `acp_spawn` drain-knob exposure; `acp_kill` returns transcript_path + agent_id + pid; `acp_doctor` enriched envelope; per-event payload trimming (`max_event_chars`, default 2048); capability-registry boost for ACPX tools; transport-aware drain redesign; authoritative ACPX documentation in `docs/claude/acpx.md` and `prompt.pmt` rule 12. **127 ACPX-adjacent tests green, 0 regressions, ruff clean.**

- **Added ACPX Runtime + 20-Skill Catalog** - New `agent/acpx/` package implements an OpenClaw-compatible runtime that spawns external coding-agent CLIs (Claude Code, Cursor, Codex, Copilot, Gemini, Qwen, Pi, Droid, iFlow, Kilocode, Kimi, Kiro, OpenCode, plus a reserved `tlamatini` self-host slot) as child processes. Seven new LangChain `@tool`s seeded as togglable rows by migration `0071_acpx_skills`. Permission gating with three modes plus a non-interactive policy. API keys injected per-agent through `acpx.agents.<id>.env`. 20 seed `SKILL.md` packages cover hello-world, skill-creator, acp-router, eight Tlamatini-specific maintenance skills, and ten OpenClaw-format ports.

- **Added WhatsTlamatini Agent** - WhatsApp counterpart of TeleTlamatini. Long-running active agent that exposes the full Tlamatini chat (`agent_page.html` Multi-Turn behavior, including the per-agent Exec Report tables) over **WhatsApp**, via Meta's WhatsApp Cloud API. Reuses TeleTlamatini's persistent Tlamatini WebSocket bridge verbatim, per-chat phase state machine, reanim-aware state, and optional Ollama-backed completeness classifier. Inbound messages arrive via a stdlib `http.server` ThreadingHTTPServer on a configurable host:port path — the user exposes the URL publicly (ngrok / cloudflared / domain / port-forward) and registers it as the app's webhook in Meta App → Webhooks. WhatsApp text messages are not editable, so the answer is delivered as a separate "✅ Result:" reply. Migration `0077_add_whatstlamatini.py`.

- **Added TeleTlamatini Agent** - Long-running active agent that exposes the full Tlamatini chat over Telegram. Stays alive waiting for messages, password-gates each chat on first contact, uses an Ollama-backed completeness classifier to decide whether each user message is a clear and complete request (asking follow-up questions until it is), proxies the request into the local Tlamatini WebSocket chat with `multi_turn_enabled=true` and `exec_report_enabled=true`, sends the assembled answer back to the Telegram user, and starts the configured `target_agents` after every completed user request cycle.

- **Multi-Turn Planner Max-Tool Cap Lowered 50 → 20** - `build_global_execution_plan()` and `_select_planner_tool_names()` now default to `max_selected_tools=20`. After observing MXNet-installation sessions where the planner selected every tool at once due to keyword inflation, the default was reduced to 20 to force the scoring threshold to do the real filtering.

- **Planner Short Follow-Up Scoring Fix** - Short follow-up messages like "continue", "go ahead", "proceed" used to score near-zero for every capability. The planner now accepts a `chat_history_text` argument and applies a history-aware boost of up to +15 points per capability when the current request has ≤4 meaningful tokens.

- **Wrapped Chat-Agent Deduplication** - `MultiTurnToolAgentExecutor.invoke()` now tracks a per-request `_wrapped_agent_signatures` set keyed on `tool_name + sorted-JSON args`. When the LLM attempts to relaunch the same `chat_agent_*` tool with identical arguments, the executor short-circuits with a `ToolMessage` explaining the skip.

- **Googler Playwright Async-Loop Fix** - `googler` tool now runs its `sync_playwright()` block inside a dedicated `ThreadPoolExecutor(max_workers=1)` with a 120-second timeout. `sync_playwright()` cannot be invoked from within Django Channels' running asyncio event loop.

- **Cancel-Current RAG Rebuild Race Fix** - `consumers.py` now `await`s `setup_rag_chain()` during cancel-current handling instead of firing it with `asyncio.create_task(...)`. Otherwise the `MSG_LLM_REESTABLISHED` confirmation reached the client before the httpx rebuild completed.

- **Multi-Turn Answer SUCCESS/FAILURE Classifier** - Added `agent/services/answer_analizer.py` — a LangChain-based binary classifier that asks the configured `chained-model` whether the final answer reflects a successful outcome or a failure. Replaces fragile regex/keyword heuristics. Fails open (returns `True`) on internal errors so the "Create Flow" button is not hidden unnecessarily.

- **Create-Flow-From-Answer Button** - On Multi-Turn SUCCESS the chat message header renders a **"Create Flow"** button. Clicking it walks the executor's per-request `_tool_calls_log`, maps each tool invocation to its sidebar agent display name, lays out nodes left-to-right, wires sequential `target_agents` connections, and downloads a `.flw` workflow file the user can re-open in the ACP designer.

- **Unified Application Log (`tlamatini.log`)** - `manage.py` defines a `_TeeStream` wrapper that replaces `sys.stdout` and `sys.stderr` before Django initializes, so every print, Django logger, and third-party stdout line lands in both the console and a single `tlamatini.log` file.

- **Documentation Regeneration Pipeline** - Added `agent/doc_generation/refresh_project_docs.py` and `agent/doc_generation/mardown_to_pdf.py` (sic) to rebuild the repository-root `tlamatini_app_summary.pdf` from the current source tree.

- **Sequenced Runtime Directories for Wrapped Chat-Agent Runs** - Each `chat_agent_*` tool invocation now creates a unique, sequenced directory under `_chat_runs_/{agent}_{seq:03d}_{short_id}/`. Failed runs are never overwritten.

- **Planner Tool Selection Fix** - Fixed a critical bug where the Global Execution Planner excluded wrapped agent tools from Multi-Turn requests. Run-control tools no longer inflate the scoring floor since they are auto-injected.

- **Comprehensive Multi-Turn Runtime Logging** - Added INFO-level logging across the entire wrapped chat-agent launch pipeline: `chat_agent_runtime.py`, `tools.py`, `mcp_agent.py`, and `global_execution_planner.py`. All loggers configured in `tlamatini/settings.py` with timestamped console output.

- **Multi-Turn UI Toggle and Explicit Opt-In Path** - The main chat toolbar now includes a dedicated **Multi-Turn** checkbox beside **Clear history**, persists it per browser session, and forwards `multi_turn_enabled` with each request.

- **Phase 1 Capability Selection** - `capability_registry.py` now scores request/tool affinity and lets checked Multi-Turn requests bind only the relevant tools or wrapped agents instead of exposing the entire enabled tool universe.

- **Phase 2 Context Capability Selection** - `rag/factory.py` now selectively prefetches `system_context` and `files_context` for checked Multi-Turn requests.

- **Phase 3 Global Execution Planner** - `global_execution_planner.py` now builds request-scoped execution DAGs with `prefetch`, `execute`, `monitor`, and `answer` nodes, plus `direct_model`, `context_only`, and `tool_augmented` execution modes.

- **Focused File-Context Hardening for Multi-Turn** - Project-home requests such as root `README.md` lookups are narrowed more deterministically.

- **Checked-Mode Runtime Hardening** - Checked Multi-Turn requests suppress visible console popups for wrapped/background launches.

- **Verification Status Raised to Full Green** - `agent/tests.py` now includes Multi-Turn planner, gating, background-launch, and frozen-mode regression coverage.

- **Main Chat Context UI State Sync** - `agent_page_ui.js` now centralizes restored context handling.

- **RAG Loaded-Documents Fallback Hardening** - `rag/factory.py` now preserves successfully loaded documents as a packed fallback context with a file manifest when retrieval-chain construction fails.

- **Configurable Runtime Limits and Demo Prompts** - `config.json` now sets `unified_agent_max_iterations` and `chat_agent_limit_runs` to `100`, `config_loader.py` centralizes frozen/source-aware config loading.

- **Keyboarder Canvas Wiring** - `keyboarder` is now a first-class ACP auto-configuration participant.

- **Mouser Localized Click Actions** - Mouser now supports `button_click` values such as `left`, `right`, `middle`, and `double-left/right/middle`.

- **Added Keyboarder Agent** - Issues a sequence of keys to emulate human typing on the keyboard.

- **Added Googler Agent** - Searches Google for a configured query using Playwright, fetches top N result pages, extracts readable text, and saves results to an output file.

- **ACP Agent Descriptions and Instance Context Menus** - `agentic_control_panel()` now parses the `## Workflow Agents` Purpose column from `README.md`, injects an `agent_purpose_map` into the ACP template, and the frontend uses it for sidebar hover tooltips and the new canvas **Description** dialog. The right-click menu for deployed agents now also exposes **`Explore dir...`** and **`Open cmd...`**.

- **Parametrizer Nested Target Mapping** - The Parametrizer dialog now flattens nested target `config.yaml` dictionaries into dot-notation keys.

- **Build and Installer Robustness** - `build.py` now treats `README.md` and `jd-cli/` as required release payloads.

- **Extension Query Parsing Hardening** - `history_aware.py` and `unified.py` now require a non-word boundary before `.ext`-style extension matches.

- **J-Decompiler Development Path Fix** - `agent/agents/j_decompiler/j_decompiler.py` now climbs one more directory level before locating the bundled `jd-cli/` payload in development mode.

- **Main Chat Multi-Turn Tool Loop** - `agent/mcp_agent.py` now builds a `MultiTurnToolAgentExecutor` for the unified chat path.

- **Wrapped Chat-Agent Runtime Layer** - Added `chat_agent_registry.py`, `chat_agent_runtime.py`, migration `0064_add_chat_agent_run_model.py`, migration `0065_add_chat_wrapped_agent_tools.py`, and the `ChatAgentRun` model. The chat surface can now launch 32 isolated `chat_agent_*` runtime copies of template agents plus 4 run-management tools.

- **Chat Runtime Isolation from ACP Flow Control** - ACP/session process scans now skip the `agent/agents/pools/_chat_runs_/` runtime root.

- **Added J-Decompiler Agent** - Short-running deterministic action agent that decompiles `.class`, `.jar`, `.war`, and `.ear` artifacts using the bundled `jd-cli`.

- **Added Barrier Agent** - Short-running passive utility flow-control agent that acts as a synchronization barrier.

- **Added Parametrizer Agent** - Short-running active utility interconnection agent that maps structured outputs from source agent logs to target agent config.yaml parameters.

- **Added Kyber-DeCipher / Kyber-Cipher / Kyber-KeyGen Agents** - CRYSTALS-Kyber post-quantum cryptography agents.

- **Added `filetype_exclusions` and `recursive` parameters** to File-Interpreter, Image-Interpreter, File-Extractor, Mover, and Deleter.

- **Added File-Extractor / File-Creator / NodeManager / GatewayRelayer / Gatewayer Agents**.

- **FlowHypervisor User Instructions / Core Auto-Stop**.

- **Crawler Substantially Improved** - Now captures **raw content** by default.

- **Ender Reanimation Asset Clearing**.

- **Concurrency Guard for All Starter-Capable Agents**.

- **Chat History Per-User Isolation** (migration 0043).

- **FlowHypervisor Monitoring Prompt Enhanced**.

- **Stopper Refactored to Single-Threaded**.

- **Added Image-Interpreter / File-Interpreter / Counter Agents**.

- **Added Flow Validation System** - Structural verification engine (`acp-validate.js`).

- **Added FlowHypervisor Agent**.

- **Added Mouser Agent**.

- **Improved Gitter / Apirer Agent Content Reporting** - Structured `<command> RESPONSE { ... }` format.

- **jd-cli Bundled in Installation**.

- **FlowCreator Skill Enhancements**.

- **Added PyAutoGUI Dependency**.

- **New API Endpoints** (the app now exposes 103 routes).

- **P0/P1/P2 Security Hardening** - Comprehensive tiered security test suite covering user isolation, CSRF, login enforcement, path traversal prevention, and prompt injection defense.

- **Added Path Guard Module** (`path_guard.py`) - Centralized path validation layer.

- **Improved File Search Chain** - Integrates with `path_guard.py`.

- **Enhanced RAG Interface Security** - LLM-based indirect file access detection and prompt-level path validation.

- **Improved Crawler Agent** - Raw content capture mode.

- **UI Refinements** - MCP/agents dialog improved with golden-ratio styled columns.

- **ESLint Configuration** - Added `eslint.config.mjs` for frontend JavaScript quality assurance.

- **Added Summarizer / FlowHypervisor / Crawler / Jenkinser / Apirer / Pser / Dockerer / Telegramer / Telegramrx Agents**.

- **Enhanced Security Guardrails** - Local file system access strictly limited to explicitly allowed paths.

- **Smart Prompts Improvement** - Enhanced LLM lookup prompts for Monitor-Log and Monitor-Netstat.

- **Interpreter Path Improvements** - Avoided hardcoded Python interpreter path execution dependencies within workflows.

- **Added Forker / Asker / Pythonxer / Stopper / Recmailer / Whatsapper / Notifier / Executer / Deleter / Mover / Sleeper / Croner / Cleaner Agents**.

- **Added Qwen Image Analysis** - Dual-backend image analysis supporting both Claude (cloud) and Qwen/Ollama (local) vision models.

- **Modular Frontend** - Split `agent_page.js` into 8 focused modules (init, chat, canvas, context, dialogs, layout, state, ui).

- **Canvas Auto-Configuration** - Agent connections on the workflow designer auto-populate config.yaml files.

- **Improved Session Persistence** - 24-hour session state with automatic restoration.

- **Enhanced RAG Pipeline** - Better context budgeting, metadata extraction, and advanced retrieval strategies.

- **Workflow Save/Load** - Export and import workflows as `.flw` files.

- **Tools Dialog** - Per-tool enable/disable via the chat interface.

- **Image Format Conversion** - Added `converter.py` module.

- **Chat History Management** - Added `chat_history_loader.py` for persistent conversation history.

- **103 HTTP Endpoints** - Comprehensive REST API for agent management, connection updates, session control.

---

# Appendix D — Acknowledgments / Contributing / License

## Acknowledgments

- [Django](https://www.djangoproject.com/) — Web framework
- [LangChain](https://github.com/langchain-ai/langchain) — LLM orchestration
- [LangGraph](https://github.com/langchain-ai/langgraph) — Stateful agent workflows
- [Ollama](https://ollama.ai/) — Local LLM inference
- [FAISS](https://github.com/facebookresearch/faiss) — Vector similarity search
- [Anthropic](https://www.anthropic.com/) — Claude API
- [Bootstrap](https://getbootstrap.com/) — Frontend framework
- [TextMeBot](https://textmebot.com/) — WhatsApp messaging API
- [Ruff](https://github.com/astral-sh/ruff) — Python linter
- [PyAutoGUI](https://github.com/asweigart/pyautogui) — Mouse/keyboard automation
- [JD-CLI](https://github.com/intoolswetrust/jd-cli) — Java decompiler CLI

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/your-feature`.
3. Commit your changes: `git commit -m 'Add your feature'`.
4. Push to the branch: `git push origin feature/your-feature`.
5. Open a Pull Request.

Development guidelines:

- Follow PEP 8.
- Add tests for new features (the suite lives in `Tlamatini/agent/tests.py`).
- Update documentation when API or behavior changes (this file, plus `docs/claude/*.md`, plus `agentic_skill.md` for new agents).
- Use meaningful commit messages.

## License

This project is licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE) for details.

---

*For support or questions, please open an issue on GitHub.*
