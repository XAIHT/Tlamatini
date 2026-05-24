# Tlamatini

![Project Logo](Tlamatini.jpg)

> **The Book of Tlamatini** — a step-by-step guide to running, using, and mastering a locally-deployed AI developer assistant with RAG, Multi-Turn tool orchestration, ACPX external-CLI delegation, an Unreal MCP client for driving Unreal Engine 5 from chat or canvas, a visual workflow designer, 67 drag-and-drop agent types, and a backend Flow Compiler that turns the live canvas — or a chat-generated tool-call log — into a registry-validated, secret-redacted, source-and-frozen-portable workflow.
>
> Visit our site at **https://xaiht.org**, or get a one-minute taste of Tlamatini on YouTube: **https://youtu.be/a51miZ1JIe0**.

---

## How to read this book

Tlamatini does a lot. This README is organized so you can stop reading at the depth you need.

- **Part I — Getting Tlamatini Running**: prerequisites, Ollama, **Ollama Pro/Max subscription for the default `:cloud` models**, install, first login. *Read this once.*
- **Part II — Using the Chat**: the four toolbar checkboxes (Multi-Turn, Exec Report, ACPX, internet) walked through one by one. *This is the dummy-friendly heart of the book.*
- **Part III — The Visual Workflow Designer**: drag-and-drop flows, FlowCreator, FlowHypervisor, Parametrizer, Gatewayer.
- **Part IV — The Tlamatini Bestiary**: compact one-row-per-agent reference for all 67 workflow agents.
- **Part V — The Tool Surface**: every LLM-facing tool the chat can call, organized by family.
- **Part VI — Inside Tlamatini**: architecture, RAG, the embedding-memory pre-flight guard, Multi-Turn pipeline, ACPX runtime mechanics. *For the curious.*
- **Part VII — Configuration Reference**: every `config.json` knob.
- **Part VIII — Deploying & Packaging**: build, installer, frozen mode.
- **Part IX — The Command Deck**: WebSocket protocol, HTTP endpoints.
- **Part X — Survival Guide**: troubleshooting, `tlamatini.log`, common issues.
- **Bonus chapter §57** — Driving Unreal Engine 5 from Tlamatini (the Unrealer agent + Unreal MCP plugin). Read this if you build games or simulations in UE5 and want a chat / canvas surface for the editor.
- **Appendix A** — Keyboarder key reference.
- **Appendix B** — Glossary.
- **Appendix C** — Full changelog (preserved verbatim).
- **Appendix D** — Acknowledgments / Contributing / License.

If you only have ten minutes, read Part I §3–§7 (install + first login), then Part II §12 (Multi-Turn).

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
4. **A visual workflow designer** where you drag 66 different agent types onto a canvas (including the new **Unrealer** for driving Unreal Engine 5 — see bonus chapter §57), wire them up, and run the result as an unattended `.flw` workflow. Save, Validate, and Start all funnel the canvas through a backend **Flow Compiler** (`agent/services/flow_compiler.py`) that consults a single Agent Contract registry — so a flow that runs in source mode runs identically in a frozen `.exe` install.

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
ollama pull Nomic-Embed-Text:latest
ollama pull glm-5:cloud
ollama pull qwen3.5:cloud
ollama pull gpt-oss:120b-cloud
ollama pull qwen3.5:397b-cloud
ollama pull llama3.2-vision:11b
```

| Model tag | Used by |
|---|---|
| `Nomic-Embed-Text:latest` | RAG embedding model (default — light VRAM footprint, ~600 MB resident) |
| `glm-5:cloud` | Default chat model + Multi-Turn unified-agent model + MCP file-search model |
| `qwen3.5:cloud` | Default Image-Interpreter vision model |
| `gpt-oss:120b-cloud` | Several workflow-agent templates (Monitor Log, Notifier, Prompter, Summarizer, Pser, Recmailer, Whatsapper, File-Interpreter, FlowHypervisor) |
| `qwen3.5:397b-cloud` | Default FlowCreator model |
| `llama3.2-vision:11b` | Local vision fallback |

Some pulls are large and slow. Start them, walk away, come back.

> **Free to substitute.** None of the model tags above are mandatory. If you prefer a different local model, edit the relevant entry in `config.json` (Part VII) or the agent's `config.yaml`. Just match the model name to something `ollama list` actually returns.

> **High-detail embedding opt-in.** If your retrieval quality on dense, technical corpora is not good enough with `Nomic-Embed-Text:latest`, you can swap it for `qwen3-embedding:8b` from the **Config → Models** menu inside the app (or by editing the `embeding-model` key in `config.json` and reconnecting). **Use with caution**: `qwen3-embedding:8b` is roughly **10× heavier in VRAM** than the default (~6.24 GB resident vs ~600 MB on a Q4_K_M quant) and will trip the embedding-memory pre-flight guard (Part §34) on 8 GB consumer GPUs. Pull it first with `ollama pull qwen3-embedding:8b`.

## 5. Cloud models require an Ollama Pro/Max plan

Four of the six default model tags in chapter §4 carry the `:cloud` suffix — `glm-5:cloud`, `qwen3.5:cloud`, `gpt-oss:120b-cloud`, and `qwen3.5:397b-cloud`. Those models are not actually running on your machine. They live on **Ollama Cloud**, and the `ollama pull <tag>:cloud` command only registers a thin stub on the local daemon that proxies inference requests to Ollama's servers. To make those proxied requests actually return something, three things have to be true: you have an Ollama account, you are signed in on the host that runs Tlamatini, and the account is on a subscription tier that allows the workload you are about to run.

### 5.1. The three tiers, in plain English

This README deliberately omits dollar amounts because the pricing changes over time. Check the current numbers on **<https://ollama.com/pricing>**. The plan structure (Free, Pro, Max) and what each one lets you do with cloud models is what matters here:

![Ollama plan structure — Free / Pro / Max (prices intentionally not shown — check ollama.com/pricing)](OllamaPricing.png)

| Plan | Cloud-model entitlements | Honest fit for Tlamatini |
|---|---|---|
| **Free** | 1 cloud model concurrent, light monthly usage, access to a smaller subset of cloud-only models. Unlimited *local* open-weights models. | OK for kicking the tires with a single cloud-backed chat. **Not enough** to run Tlamatini's stock config, because a normal Multi-Turn session can easily touch two or three cloud models in the same request (chat model, FlowCreator model when Create Flow fires, vision model when an Image-Interpreter step runs). The second concurrent model will simply 429. |
| **Pro** | 3 concurrent cloud models, ~50× the Free monthly quota, full access to the larger cloud-only models (the `*120b-cloud`, `*397b-cloud` tags Tlamatini ships with), and you can upload / share your own private models. | The realistic minimum to run Tlamatini out of the box with the model tags from chapter §4 *as written*. Comfortable for interactive Multi-Turn + Exec Report use, occasional FlowCreator runs, and a handful of ACPX relays per day. |
| **Max** | 10 concurrent cloud models, ~5× the Pro quota, intended for sustained heavy agentic workloads. | Recommended if you live in long-running ACPX relays, FlowHypervisor-supervised flows, or Croner-driven unattended runs that chain many cloud calls per hour. Also the right choice when several wrapped chat-agents (Summarizer, File-Interpreter, Image-Interpreter, Prompter…) fan out cloud calls concurrently inside a single Multi-Turn iteration. |

### 5.2. What if I do not want to subscribe?

Tlamatini does not *require* Ollama Cloud. The cloud tags are convenience defaults — large, capable models you do not need to host yourself. You can run the whole stack on local open-weights models instead. Open `Tlamatini/agent/config.json` and replace every cloud tag with a model you have pulled locally:

| Config key | Default (cloud) | A reasonable local substitute |
|---|---|---|
| `chained-model` | `glm-5:cloud` | `qwen2.5-coder:14b` or `llama3.1:8b` |
| `unified_agent_model` | `glm-5:cloud` | same as above |
| `mcp_file_search_model` | `glm-5:cloud` | same as above |
| `flow_creator_model` | `qwen3.5:397b-cloud` | `qwen2.5:32b` or any large local model you can fit in VRAM |
| `image_interpreter_model` | `qwen3.5:cloud` | `llama3.2-vision:11b` (already in chapter §4's pull list as the local fallback) |

Then also walk through `Tlamatini/agent/agents/*/config.yaml` and replace any cloud tag the agent templates name (several workflow agents — Prompter, Summarizer, Monitor-Log, FlowHypervisor, Recmailer, Whatsapper, File-Interpreter — all default to `gpt-oss:120b-cloud`). After the swap, restart Tlamatini. Quality and latency will scale with your hardware, but Multi-Turn and ACPX both work fine on a sufficiently large local model.

### 5.3. This subscription is separate from your coding-agent API keys

The Ollama plan only governs `*:cloud` Ollama models. If you plan to use **ACPX** (chapter §46) to delegate sub-tasks to external coding-agent CLIs (`claude`, `cursor-agent`, `codex`, `gemini`, `qwen-code`, …), each of those carries its own credentials: the Anthropic API key for `claude`, OpenAI for `codex`, Google for `gemini`, and so on. Those keys are configured in `Tlamatini/agent/config.json` under the top-level fields *and* the per-agent `acpx.agents.<id>.env` blocks, and they are completely independent of your Ollama subscription. The `setup-new-acpx-key` skill (chapter §15) automates that wiring.

### 5.4. Troubleshooting the cloud path

| Symptom | Likely cause | What to try |
|---|---|---|
| `ollama pull glm-5:cloud` succeeds but inference returns "unauthorized" / "401" | Not signed in to Ollama on this host. | Run `ollama signin` (or use the Ollama desktop app) and confirm `ollama whoami` prints your account. |
| Inference returns "rate limit exceeded" / "429" right after a Multi-Turn step | Your plan's concurrent-model or monthly-usage cap is full. | Either upgrade the plan, drop concurrency by running fewer wrapped agents in parallel, or swap one of the cloud tags for a local model in `config.json`. |
| Inference returns "model not available on this plan" | The tag you pulled is gated to a higher tier (Pro/Max only). | Check `ollama.com/pricing` for which models each tier covers, and pick a tag your plan includes — or upgrade. |
| Tlamatini chat says "Ollama backend unreachable" | Local daemon is down, **not** a cloud problem. | `ollama serve` and `Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing` per chapter §3.3. Cloud requests still go through the local daemon. |

## 6. Installing Tlamatini

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

When the migrations finish and you have a superuser, run the server (chapter 7).

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

## 7. First login

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

## 8. A tour of the chat page

Open `/agent/`. Here is what you are looking at:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Tlamatini  [Context ▼] [Open in… ▼] [MCPs ▼] [Tools ▼] [Agents ▼] [Config ▼] [Logout] │ ← Top navigation
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

The navbar also has a **Config** dropdown now. It exposes two validated dialogs: **Models** for the main model-name fields and **URLs** for the Ollama / unified-agent / MCP endpoint values. That means the most common runtime settings can now be changed from the chat UI without manually editing `config.json`. The chat/canvas divider was also polished so width changes feel steadier while you work.

## 9. Asking your first question (no toggles)

Leave every checkbox unticked. This is the **simplest** possible chat: one question in, one answer out.

**Try this:**

> "Write a Python function that validates an email address using a regular expression. Just the function, no main."

The bot answers in the chat panel. If it generates code, you will see it appear in the code canvas on the right with a filename header and a copy button.

What is happening under the hood:

1. Your message goes to the server over WebSocket.
2. Tlamatini decides it is a programming question (not a system / files question), runs prompt-shape validation, and sends it to the LLM.
3. The LLM responds in one shot. Done.

This is the **legacy one-shot chat path**. It is fast, deterministic, and uses no tools. It is also intentionally limited: the LLM cannot run anything on your machine, cannot search the web, cannot read files. For that, you tick checkboxes.

## 10. Setting code as context

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

One subtle but important reliability fix landed here: when a browser refresh restores a saved context, the chat input is now disabled immediately and remains disabled until the contextual RAG chain has really finished rebuilding. In older builds, the user could briefly type into a half-restored session because the welcome-back banner arrived before the context-loading lifecycle had finished.

## 11. The "Add internet context" toggle

Tick **Add internet context** when the question genuinely needs information from the web. Examples:

- "What is the latest stable version of FastAPI as of right now?"
- "Show me a current example of using OpenAI's responses API."
- "What does the `2024-11-30` row in the React 19 changelog say?"

Tlamatini classifies your question with a small LLM call ("does this need the web?"), then runs a DuckDuckGo search, fetches and summarizes the top results, and inlines the summary into the LLM's context.

Leave it **unticked** for everything that does not need fresh web data. The classifier is fast but a web round-trip still adds latency.

## 12. The "Multi-Turn" toggle (turning Tlamatini into a *doer*)

This is the big one. Until you tick **Multi-Turn**, Tlamatini only *describes* things. With Multi-Turn ticked, Tlamatini can *do* them.

### What it does

Multi-Turn flips Tlamatini from "answerer" to **operator**:

- The chat skips its prompt-shape validator (you no longer have to phrase requests as questions).
- A request-scoped **planner** picks the relevant tools out of all 40 wrapped chat-agents, the 12 ACPX tools, and the core Python tools.
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
- A **Create Flow** button appears in the message header (chapter 16 explains it).
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

## 13. The "Exec Report" toggle (seeing every step)

### What it does

Below the LLM's prose answer, Tlamatini appends **per-agent execution tables** — one HTML table per *kind* of state-changing agent that fired during the request, each row a real tool call with a SUCCESS/FAILURE verdict.

This is the "show your work" view. It is the ground-truth counterpart to the prose summary. The prose can be ambiguous; the tables are not.

### When to use it

- Always when you are debugging a Multi-Turn run.
- Always when you want to convert a chat into a flow (chapter 16).
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
- **Wrapped chat-agents**: every `chat_agent_*` that touches the system (executer, pythonxer, dockerer, kuberneter, ssher, scper, sqler, mongoxer, gitter, file_creator, mover, deleter, apirer, send_email, telegramer, whatsapper, notifier, kyber_keygen/cipher/decipher, **keyboarder**, **mouser**, **playwrighter**, jenkinser, unrealer).
- **ACPX**: `acp_spawn`, `acp_send`, `acp_send_and_wait`, `acp_kill`, `acp_relay` — all merge into one "List of ACPx Operations" table.
- **Skills**: `invoke_skill` gets its own table.

Read-only tools (Crawler, Googler, Prompter, Summarizer, File-Interpreter, File-Extractor, Image-Interpreter, **Shoter**, Sleeper, monitor_*, recmailer, run_*, window_present) and management tools never appear — they did not change anything to report on.

### A persistence detail worth knowing

The Exec Report tables are **persisted into the chat history**, not just broadcast live. Reload the page — the tables are still there. This is intentional, and the order in `process_llm_response()` is strict: classify success → append exec-report HTML → save → broadcast. Do not reorder.

## 14. The "ACPX" toggle (delegating to external coding-agent CLIs)

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

The full ACPX deep-dive is in **Part VI §46**. This chapter is just the toolbar walkthrough.

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

(Two layers — top-level for Tlamatini's own Anthropic calls, and `acpx.agents.claude.env` for the spawned `claude` CLI. The skill `setup-new-acpx-key` automates this; see chapter 15.)

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

## 15. Combining the four toggles — worked examples

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

## 16. From chat to flow — the Create Flow button

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

## 17. The DB menu — backups and the next-session swap-in

Tlamatini's whole world — chat history, agent definitions, Tool/MCP toggle rows, session state, deployed-pool metadata, the per-user account that gates the chat — lives inside a single SQLite file: `db.sqlite3`. The top-of-page **DB** dropdown gives you a safe, GUI-first way to handle that file without ever stopping Tlamatini, opening Explorer, or remembering where the database actually sits in frozen vs. source mode.

The dropdown has two entries:

| Entry | What it does | When you use it |
|---|---|---|
| **Backup database** | Copies the live `db.sqlite3` to a directory you pick — keeps the live database in place. | Before risky changes (mass-deploying agents, migrating, experimenting), or as a routine snapshot. |
| **Set DB** | Stages a `db.sqlite3` file of *your* choice so Tlamatini swaps it in on the **next start-up**. The current database is moved into a timestamped archive folder. | Restoring a backup, importing a friend's database, switching between project-specific databases. |

### 17.1. Backup database — the read-only copy

`DB → Backup database` opens a dialog with one input — the **target directory** you want the copy written into. The input is **live-validated** (350 ms debounce): as you type, the page asks the server `GET /agent/check_backup_directory/?path=…` and colors the status line green / amber / red:

| State | Status line | Meaning |
|---|---|---|
| Green | `Directory exists. db.sqlite3 will be saved here.` | Ready to backup. |
| Amber | `A filename was specified — please specify the directory only.` | You typed a file path instead of a directory; Tlamatini always names the output `db.sqlite3` so it can be loaded back later. |
| Red | `Directory does not exist.` | Path is missing on disk. |

Click **Backup** and Tlamatini calls `POST /agent/backup_db/`, which resolves the live database path via `settings.DATABASES['default']['NAME']` (so source-mode and frozen-mode work identically) and `shutil.copy2`s the file into `<your-dir>/db.sqlite3`. A success alert confirms the destination path. **The live database stays open and unchanged** — Backup is purely additive.

### 17.2. Set DB — staging a database for the next session

`DB → Set DB` is the harder direction: it replaces the database the next time Tlamatini boots. The dialog has one input — the **full path to a `db.sqlite3` file** you want loaded — and the same live-validation behavior as Backup, but with stricter rules:

| State | Status line | Meaning |
|---|---|---|
| Green | `File exists. It will be loaded on the next start-up.` | Real `db.sqlite3` with a valid SQLite header. |
| Amber | `File found, but its name is not "db.sqlite3". Tlamatini will still stage it as db.sqlite3.` | Some users keep snapshot files named like `db_2026-05-14.sqlite3` — they still work because Tlamatini renames on stage. |
| Amber | `Specify the full path to a db.sqlite3 file, not a directory.` | You typed a directory; Set DB needs a file path. |
| Red | `The selected file does not look like a SQLite database.` | The first 16 bytes don't match the `SQLite format 3\x00` magic header. |
| Red | `File does not exist.` | Path is missing on disk. |

The SQLite header check is a cheap sanity guard — it catches the common "I picked the wrong file" mistake (a `.csv`, an `.flw`, a screenshot, an empty file) before Tlamatini commits to swapping it in.

When you click **Set** and the file passes validation, the page POSTs `POST /agent/set_db/`. The view computes the deployment-specific **staging directory** — `<exe_dir>/DB/ToLoad/` in frozen mode, `<repo>/Tlamatini/DB/ToLoad/` in source mode — creates it if needed, and copies your file there as `DB/ToLoad/db.sqlite3`. **The live database is NOT touched.** SQLite is open in-process while Tlamatini runs; replacing it mid-flight would corrupt the live connection pool, so Set DB *only stages*.

Immediately after staging succeeds, the dialog is replaced by a second one — a yellow ⚠ warning panel — telling you in two sentences:

> **The selected database will be loaded the next time Tlamatini starts.**
> If you want it loaded immediately, you must restart Tlamatini completely so the swap-in can run BEFORE Django opens the live database.

Click **OK** and the dialog closes. There is no Cancel — by the time you see this dialog the file is already staged.

### 17.3. The start-up swap-in (what "next session" actually means)

The third leg of the DB mechanic — and the only one without a UI surface — is the start-up swap-in itself. It lives at the very top of `Tlamatini/manage.py` and runs in this exact order before *anything Django* is imported:

```
_apply_pending_db_swap()           ← runs BEFORE Django
    ↓
[ os.path detection: frozen or source? ]
    ↓
[ DB/ToLoad/db.sqlite3 exists? ]
    │
    ├─ NO  ──► return (no-op, normal start-up continues)
    │
    └─ YES ──► [1] mkdir DB/Older/<YYYY-MM-DD_HHMMSS>/
               [2] shutil.move(live db.sqlite3 → Older/<timestamp>/db.sqlite3)
               [3] shutil.move(DB/ToLoad/db.sqlite3 → live db.sqlite3 path)
               [4] return (Django opens the freshly-swapped file)
```

The three guarantees this gives you:

1. **Pre-Django timing.** Because the swap-in runs before the `from django.core.management import execute_from_command_line` line, Django's SQLite connection pool is never holding a stale file descriptor at the moment of the swap. A simple **Reconnect** from the navbar is NOT enough to trigger the swap-in — you must restart the entire process (close the console, launch Tlamatini again).
2. **Atomic moves, no copies.** Both legs use `shutil.move` (filesystem rename when possible, copy+delete across mounts) so the source files are consumed. A second launch with `DB/ToLoad/` empty is automatically a no-op — there's no "stuck flag" to clear.
3. **Mode-correct path resolution.** Frozen mode looks at `<exe_dir>/DB/ToLoad/db.sqlite3` (where you can browse to in Explorer); source mode looks at `<repo>/Tlamatini/DB/ToLoad/db.sqlite3` (where `manage.py` lives). The live `db.sqlite3` path is computed the same way Django does — `_MEIPASS/db.sqlite3` under PyInstaller, `<manage.py dir>/db.sqlite3` in source mode — so the swap-in writes to exactly the location Django will open.

If anything fails inside the swap-in (locked file on Windows, corrupt source, permission error), the function catches the exception, prints `--- [DB SWAP] Skipped due to error: <reason>` to `tlamatini.log`, and lets Tlamatini start normally with the previous database. **A bad ToLoad file must never block start-up** — that would lock you out of your own database.

### 17.4. The Older audit trail

Every successful swap-in leaves a complete record under `<base>/DB/Older/<YYYY-MM-DD_HHMMSS>/db.sqlite3`. The timestamp is the local time at the moment the swap happened, filesystem-safe on Windows / Linux / macOS:

```
DB/
├─ ToLoad/
│   └─ (empty most of the time; momentary home of the next-session pick)
└─ Older/
    ├─ 2026-05-14_153022/
    │   └─ db.sqlite3      ← database that was live before swap #1
    ├─ 2026-05-14_164410/
    │   └─ db.sqlite3      ← database that was live before swap #2
    └─ 2026-05-14_172908/
        └─ db.sqlite3      ← and so on
```

Because Set DB **moves** (not copies) the prior live database into Older, this archive is the only built-in recovery path. To roll back to a previous database, you do exactly the same thing you did to load a new one: copy the archived `db.sqlite3` back into `DB/ToLoad/` and restart. The swap-in archives the *current* live one under a fresh timestamp and promotes your roll-back pick.

Tlamatini **never** deletes anything from `DB/Older/`. If swaps become routine, you may want to prune the oldest folders by hand — but read each carefully first, because each `db.sqlite3` contains chat history, agent definitions, session state, and your user account, so think twice before deleting any of them.

### 17.5. The DB tree ships in both modes

The `DB/ToLoad/` and `DB/Older/` directories must exist on day one — the swap-in opens them with `os.makedirs(exist_ok=True)`, but having them pre-seeded with documentation prevents user confusion. So:

- **Source / dev mode**: `Tlamatini/Tlamatini/DB/ToLoad/README.md` and `Tlamatini/Tlamatini/DB/Older/README.md` are checked into the repo. Each is a short standalone guide describing the contract, how to use the directory, and the rollback recipe. They survive in git only because git ignores empty directories; the README is the trick that keeps the tree.
- **Frozen mode**: `build.py` extends its `empty_dirs` tuple to include `"DB/ToLoad"` and `"DB/Older"`. The PyInstaller post-build step creates both under `dist/manage/` (which becomes the install root next to `Tlamatini.exe`), and the `pkg.zip` packager preserves empty directories via explicit zip entries. End-users get the same `DB/{ToLoad,Older}/` tree from the very first launch, ready to receive a drop or archive a swap.

### 17.6. Mental model — three questions to ask before each operation

When you reach for `DB → Backup database`, ask:

> *"Do I want a copy I can come back to, while continuing to use the live database?"*

When you reach for `DB → Set DB`, ask:

> *"Am I prepared to restart Tlamatini? Do I want the current database moved out of the way and replaced?"*

When you reach into `DB/Older/` by hand, ask:

> *"Which timestamp do I trust? Am I about to overwrite the only running database with one that may be older / smaller / from a different machine?"*

The DB menu is intentionally small — three primitives (backup, stage, archive), one swap window (process restart), one audit trail (timestamps). Everything else is just discipline.

---

## 17.5. The ACPX-Skills menu — admining the skill catalog

Tlamatini ships with 23 markdown skill packages under `Tlamatini/agent/skills_pkg/`. Each one is a small playbook the LLM can run: `acp-router` picks the right external coding-agent CLI for an intent, `summarize` compresses text to a target word count, `setup-new-acpx-key` walks the user through plugging in a new API key, `skill-creator` bootstraps a brand-new SKILL.md, `code-review` runs a senior-engineer pass over a git diff (returning an APPROVE / REQUEST_CHANGES verdict) and `security-audit` sweeps a path with the installed SAST / secret / dependency scanners, the `tlamatini_*` family audits and refactors Tlamatini's own codebase, and a handful of integration stubs (`github`, `gmail`, `notion`, `slack`, `jira`, `todoist`, `trello`, `weather`) reach out to third-party services through their REST APIs. They run inside a sandbox called the **SkillHarness**: budgets cap iterations, wall-clock, and tokens; declared filesystem / shell / network / db permissions gate side effects; declared inputs and outputs are validated on the way in and the way out.

Before May 2026, the only way to interact with this catalog was through the LLM itself. You'd type "list the skills you have" and the chat would call `list_skills` and read out the rows; you'd type "use the summarize skill to compress this" and the chat would call `invoke_skill('summarize', '{...}')` and surface the result. Catalog hygiene — knowing exactly what was installed, picking which skills the planner was allowed to surface, reloading the registry after editing a SKILL.md on disk — all of it had to be routed through the model. That worked but it felt wrong: a piece of catalog admin that belongs to the person at the keyboard kept asking permission from the model.

The **ACPX-Skills** dropdown closes that gap. It lives between **Agents** and **Config** in the chat navbar and has four entries:

### `ACPX-Skills → Browse Skills`

Opens a two-pane modal: a search-filterable list on the left with one row per skill (a small green dot for enabled, a small grey dot for disabled, the skill's name, and a runtime tag — `IN-PROCESS` or `ACPX`), and a detail pane on the right that fills in when you click a row. The detail pane is read-only and pulled fresh from the registry on every click — it shows the description, the runtime (and the `acpx_agent` if `runtime: acpx`), the budget triple (`12 iter · 180 s · 30000 tokens` style), the trigger keywords the planner uses to score the skill against a prompt, the `requires_tools` and `requires_mcps` arrays (so you can immediately see if a skill depends on something you've disabled), the inputs and outputs (with required-field markers and per-field types), the on-disk path to the SKILL.md, the first sixteen characters of its body SHA-256, and finally the full markdown body of the skill in a scrollable pre block. A search box at the top of the dialog filters the list as you type — matching against name + description + keywords. The list shows `N / 21` so you always know how much was hidden by your search. There's also a small note at the right when the registry has orphan DB rows — skills the database thinks exist but whose SKILL.md was deleted on disk; Diagnostics gives you the full list.

Use Browse when (a) you've just authored a new SKILL.md and you want to confirm it parsed correctly, (b) you want to know exactly what permissions a third-party integration skill is asking for before you enable it, (c) you're debugging a failing `invoke_skill` and you want to look at the body the LLM was supposed to follow.

### `ACPX-Skills → Configure Skills`

A checkbox grid, one row per skill, that mirrors the **MCPs** and **Agents** dialogs you already know. Each row is `[ ] skill-name — description`. Toggle a checkbox off, click **Continue**, and a couple of things happen simultaneously: the `Skill.enabled` column flips to `false` in the database, and the change broadcasts over the same WebSocket channel the existing MCPs/Tools/Agents toggles ride — the payload is encoded as `name=description=true|false,...` exactly the way `set-mcps` / `set-tools` / `set-agents` encode their payloads. The backend's new `set-skills` handler in `consumers.AgentConsumer.receive` parses the payload and calls `save_skill(name, enabled)` for each row.

After the toggle lands, two consequences arrive immediately for the next request:

- The LLM's `list_skills` tool filters disabled rows out of its returned array — disabled skills become invisible to enumeration, so the planner won't surface them.
- The LLM's `invoke_skill('<disabled-skill>', '{...}')` returns `{"ok": false, "code": "SKILL_DISABLED"}` instead of running.

Toggling the row back to enabled restores both behaviors. This is the right knob when you want to hide an unfinished skill from the planner, when you don't have the API key for an integration skill (no point letting the LLM keep trying `notion` without `NOTION_TOKEN`), or when you're running a demo and you want a minimal tool surface so the model doesn't waste turns picking obscure options.

### `ACPX-Skills → Diagnostics`

A cross-check report that catches the kind of drift you'd otherwise only discover at runtime. It has four sections; each is collapsed when clean (green ✓) and expanded with a red ⚠ count when something's wrong:

- **Missing tool dependencies** — for each skill whose `requires_tools` lists a Tool you've currently disabled in the **Tools** dialog. A disabled tool means the skill would fail at runtime; Diagnostics surfaces it before the LLM tries.
- **Missing MCP dependencies** — same idea against disabled `Mcp` rows.
- **Unknown ACPX agents** — for `runtime: acpx` skills, flags any `acpx_agent` value that isn't in the live `AcpAgent` table (typo, removed CLI, etc).
- **Orphan DB rows** — `Skill` rows whose SKILL.md file no longer exists on disk; typically a sign that someone deleted a skill directory without running Reload.

A header strip at the top gives you the counts at a glance: how many skills are on disk, how many DB rows exist, how many Tools/MCPs/ACPX agents are tracked. The endpoint is `GET /agent/skills/_/diagnostics/` — pure read, no writes.

### `ACPX-Skills → Reload Registry`

A single-click action that re-runs the registry boot pipeline: rescan `agent/skills_pkg/`, refresh every `Skill` DB row's metadata cache (description, runtime, acpx_agent, frontmatter_json, body_sha256), prune any DB row whose SKILL.md is gone. The user-toggled `enabled` field is preserved. A toast confirms the new count.

Use Reload after authoring a new SKILL.md or editing an existing one. No server restart needed.

### The line the database deliberately does not cross

The `Skill` model itself was older than this dropdown — it was added back in migration `0071_acpx_skills.py` with a richer shape than the `Tool` / `Mcp` / `Agent` toggle rows: it has `name`, `description`, `runtime`, `acpx_agent`, `enabled`, `frontmatter_json`, `body_sha256`, `last_loaded_at`. Building this admin UI on top of it required a small but deliberate decision: the dropdown **only** ever writes the `enabled` boolean. Every other column is owned by `agent/acpx/service.py::boot_skills()` and is overwritten on every reload from the SKILL.md on disk. The cached `frontmatter_json` and `body_sha256` are present because earlier work needed them for fast lookups; the admin UI ignores them and reads fresh from the registry instead, so the disk stays the only source of truth for permissions, budgets, and body.

This matters because the obvious alternative — "let the user override a skill's `max_seconds` from the browser" — is a trap. The next backup would silently archive that override, the next `git pull` would not show it in `git diff`, and a user on a different machine would have no way to know why their identical SKILL.md behaved differently. Editing the SKILL.md and clicking Reload keeps every behavioural change visible in a file and a commit. The DB stays at "enumeration plus enable/disable", exactly the way the Mcps and Agents dialogs constrain themselves.

### Where to look in the code

- `agent/views.py` — `list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`.
- `agent/urls.py` — `/agent/skills/`, `/agent/skills/<name>/`, `/agent/skills/_/reload/`, `/agent/skills/_/diagnostics/`.
- `agent/consumers.py` — `skill_establishment`, `get_all_skills`, `save_skill`, the new `set-skills` branch, the establishment loops in both the session-restore and rebuild paths.
- `agent/acpx/tools.py` — `_disabled_skill_names()` plus the gating clauses in `list_skills` and `invoke_skill`. Fails OPEN on DB exception by design.
- `agent/templates/agent/agent_page.html` — the dropdown, the three dialog containers, the asset includes.
- `agent/static/agent/js/skills_dialog.js` — all four dialogs (Configure / Browse / Diagnostics / Reload) in one module.
- `agent/static/agent/css/skills_dialog.css` — styling.
- Coverage: 14 tests across `SkillsAdminEndpointTests`, `SkillsToolSurfaceGatingTests`, `SkillsNavbarTemplateContractTests`.

---

# Part III — The Visual Workflow Designer

## 18. Why drag-and-drop flows

The chat is amazing for one-off tasks. But some jobs you want to:

- Run on a schedule (every hour, every Monday at 9 a.m.)
- Run unattended on a remote server
- Run identically every time, with no LLM creativity in the loop
- Compose at design-time so the steps are auditable before any LLM is involved

Those are flows. You drag agents from a sidebar onto a canvas, draw lines between them, configure their parameters, save the result as a `.flw` file, and run it.

## 19. Anatomy of the canvas

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

Another recent change matters if you use the config dialogs heavily: dialog-edited wiring fields now survive the compile pass. In practice that means a user-edited `source_agents`, `target_agents`, or Ender kill list is preserved, while the canvas still contributes its live connections where appropriate. Validate and Start no longer flatten those deliberate edits back into stale pool defaults.

## 20. Your first flow (3-agent example)

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

## 21. Saving and loading `.flw` files

Click **💾 Save**, pick a name. You get a JSON file with all node positions, configs, and connections. Distribute it; somebody else loads it via **📂 Load**, gets the same flow.

`.flw` files are also what the chat's **Create Flow** button (chapter 16) emits.

## 22. Pause, Resume, and Stop

The three buttons each do something different:

| Button | What happens |
|---|---|
| **⏸ Pause** | Stores the currently-running agents into `paused_agents.reanim`, kills their processes, **leaves logs and `reanim*` state files intact**. The ACP enters paused state (yellow LEDs). |
| **▶ Resume** (after pause) | Reanimates each saved agent with `AGENT_REANIMATED=1`. Each agent reads its `reanim*` files and continues from exactly where it stopped. |
| **⏹ Stop** | Hard stop. Ender runs its termination logic; reanimation files are cleared. |

This is why long-running workflows (Crawler scraping 10,000 URLs, Parametrizer iterating through segments) survive pauses without data loss.

The stop path also got harder to break in mixed flows. Current builds are better at killing lingering session processes during cleanup, so a half-manual / half-compiled run is less likely to leave zombie agents behind before the next start.

## 23. FlowHypervisor (your watchdog)

Click **⚠ Hypervisor** and a system-managed FlowHypervisor agent starts watching every other running agent. It is an LLM that:

- Reads each agent's log incrementally.
- Builds an NxN connection matrix from the canvas wiring.
- Looks for: stuck agents (started >5 min ago, no output, downstream never fired); broken chains (agent finished, but its `target_agents` never started); fatal/critical errors; user-imposed time constraints.
- Outputs exactly **`OK`** when healthy or **`ATTENTION NEEDED { explanation }`** when not.

If a problem fires, the browser shows an alert dialog. You can append your own rules to the watchdog through the FlowHypervisor agent's `user_instructions` config field — useful for "don't flag this known false-positive" or "wake me if X is silent for >10 min."

## 24. FlowCreator — let an LLM design the flow for you

Drag a **FlowCreator** node onto the canvas, double-click it, and type a natural-language objective:

> "Every hour, crawl our status page; if it shows ERROR, email the on-call engineer; otherwise, do nothing."

Click **Generate**. FlowCreator reads `agentic_skill.md` (its design playbook), produces a JSON description of the agents and connections, and renders them onto the canvas. You can edit, tweak parameters, and run.

This is the highest-leverage feature for non-technical users: you describe what you want, the system *draws* the flow.

## 25. Parametrizer (chaining outputs into the next agent's config)

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

24 agents emit Parametrizer-compatible sections:

Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, Image-Interpreter, File-Extractor, Prompter, FlowCreator, Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Gatewayer, Gateway-Relayer, Googler, **Playwrighter**, **ACPXer**, Shoter, Mouser, **Windower**, **Unrealer**, **Reviewer**, **Analyzer**, **Kalier**.

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

## 26. Gatewayer (external triggers into a flow)

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

A compact reference for all 67 workflow-agent types. Spotlight chapters for **Parametrizer** (§25) and **Gatewayer** (§26) above; **Unrealer** gets a full bonus chapter at §57.

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
| **Playwrighter** | Scripted interactive browser automation via Playwright (Chromium/Firefox/WebKit). Drives a REAL browser through an ordered list of declarative steps — `goto` / `click` / `fill` / `press` / `wait_for` / `extract_text` / `extract_attr` / `screenshot` / `assert_visible` / `assert_text` / `download` — for authenticated, JS-rendered, multi-step flows (logins, forms, wizards, SPA scraping, end-to-end UI checks) that Crawler (static fetch) and Googler (search) cannot do. Deterministic (no LLM). Set `headless: false` to watch it drive and `hold_open_seconds: N` (alias `hold_open_ms`) to keep the browser visible N seconds after the last step before it closes. Emits an `INI_SECTION_PLAYWRIGHTER<<<` block (`start_url`, `final_url`, `status`, `steps_run`, `assert_result`, `response_body`) and always triggers `target_agents`. Canvas counterpart of the `chat_agent_playwrighter` Multi-Turn tool. |
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
| **Windower** | Deterministic Win32 window manager (pywin32 + ctypes). Locates an application window by title (`match_mode` ∈ substring/exact/regex, plus `match_index` to disambiguate same-titled windows) and runs ONE window-lifecycle operation: `focus`, `minimize`, `maximize`, `restore`, `move`, `resize`, `move_resize`, `close`, `topmost` / `untopmost` (always-on-top), or `arrange` (snap/tile to left/right/top/bottom halves, four quadrants, center, or full) — or `list` every open window with its position, size, and state. The window member of the desktop-UI trio (Windower = the window, Mouser = clicks, Keyboarder = typing). Ports the window-management subset of Microsoft's Windows-MCP (incl. the AttachThreadInput cross-process focus-transfer dance). Emits an `INI_SECTION_WINDOWER<<<` block (`action`, `window_title`, `matched`, `match_count`, `state`, `left`, `top`, `width`, `height`, `response_body`) and always triggers `target_agents`. Canvas counterpart of the `chat_agent_windower` Multi-Turn tool. |
| **Kalier** | Kali Linux offensive-security bridge to the **MCP-Kali-Server** (`server.py` Flask API; default `http://127.0.0.1:5000`; stdlib `urllib`, self-contained — no `requests`/`mcp` deps in the pool). `action` ∈ `command` / `nmap` / `gobuster` / `dirb` / `nikto` / `sqlmap` / `metasploit` / `hydra` / `john` / `wpscan` / `enum4linux` / `health`. Emits an `INI_SECTION_KALIER<<<` block (`action`, `endpoint`, `method`, `subject`, `return_code`, `success`, `timed_out`, `server_url`, `response_body`) and always triggers `target_agents` so a Forker can branch on `{success}`/`{return_code}`. Canvas counterpart of the `chat_agent_kalier` Multi-Turn tool. **Authorized targets only.** |
| **File-Creator** | Write a file. |
| **File-Interpreter / File-Extractor** | Document parsing (DOCX, PPTX, XLSX, PDF, …); raw text extraction with strings-fallback for unknowns. |
| **Image-Interpreter** | LLM vision analysis of images. |
| **J-Decompiler** | JAR/WAR/CLASS decompilation via bundled `jd-cli`. |
| **De-Compresser** | Deterministic archive worker (compress OR decompress). Inferred direction: `input` ext or `output` ext picks the operation. Supports `.gz`, `.zip`, `.7z`, `.tar.gz`/`.gz.tar`. Password from `DE_COMPRESSER_PWD` env var when `passwordless=false`. |
| **Telegramer** | Outbound Telegram message. |
| **TeleTlamatini** | Long-running Telegram bridge that exposes the full Multi-Turn + Exec Report Tlamatini chat to authorized Telegram users. |
| **WhatsTlamatini** | WhatsApp counterpart of TeleTlamatini, via Meta's WhatsApp Cloud API. |
| **ACPXer** | Visual canvas counterpart of the 12 LLM-facing ACPX tools. One node = one external-CLI session lifecycle. |
| **Unrealer** | Drives Unreal Engine 5 via the Unreal MCP plugin's TCP socket protocol (`127.0.0.1:55557` by default — plugin must already be running inside an UE5 editor instance). One node sends one JSON command (`{"type": <verb>, "params": {...}}`) and captures the engine's response into an `INI_SECTION_UNREALER<<<` block. Full 28-command surface across editor / blueprint / node / project / umg categories. (See bonus chapter §57.) |
| **Reviewer** | LLM-powered code reviewer. Resolves a `git diff` for `repo_path` (`diff_ref` like `HEAD~1` / `origin/main`, or empty = uncommitted working-tree + staged changes), sends it to an Ollama model with a senior-engineer prompt, and emits an `INI_SECTION_REVIEWER<<<` block whose first field is a `verdict` (`APPROVE` / `REQUEST_CHANGES` / `COMMENT`). Always triggers `target_agents`, so a downstream Forker can branch on `{verdict}`. Canvas counterpart of the `code-review` skill. |
| **Analyzer** | Deterministic static-analysis / security scanner (no LLM). Runs whichever of `bandit` / `semgrep` / `ruff` / `eslint` / `gitleaks` / `pip-audit` are on PATH over `target_path`, aggregates findings, and emits an `INI_SECTION_ANALYZER<<<` block whose `status` is `clean` / `findings` / `error` and whose `total_findings` is routable. Always triggers `target_agents`, so a downstream Forker can gate on `{status}` / `{total_findings}`. Canvas counterpart of the `security-audit` skill. |

## Cryptography (post-quantum)

| Agent | Purpose |
|---|---|
| **Kyber-KeyGen** | CRYSTALS-Kyber public/private key pair (Kyber-512/768/1024). |
| **Kyber-Cipher** | Kyber encapsulation + AES-256-CTR encryption. |
| **Kyber-DeCipher** | Kyber decapsulation + AES-256-CTR decryption. |

## Utility

| Agent | Purpose |
|---|---|
| **Parametrizer** | Strict single-lane queue mapping source-agent log segments into target-agent config. (See §25.) |
| **FlowBacker** | Post-Ender backup of session logs/configs. |
| **Gatewayer** | Inbound HTTP webhook / folder-drop ingress. (See §26.) |
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
| **FlowHypervisor** | LLM watchdog over running agents. (See §23.) |

## AI / design

| Agent | Purpose |
|---|---|
| **FlowCreator** | LLM that designs flows from natural-language objectives. (See §24.) |

---

# Part V — The Tool Surface

Every tool the chat LLM can call in Multi-Turn mode. Tools can be individually enabled/disabled via the **Tools Dialog** in the chat.

## 27. Core tools

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

## 28. Wrapped chat-agent tools (42)

Each wrapped tool launches an isolated, sequenced runtime copy of a workflow agent template under `agent/agents/pools/_chat_runs_/{agent}_{seq:03d}_{short_id}/`. Failed runs are preserved.

| Family | Tool names |
|---|---|
| **Execution & files** | `chat_agent_executer`, `chat_agent_pythonxer`, `chat_agent_pser`, `chat_agent_move_file`, `chat_agent_deleter`, `chat_agent_sleeper` |
| **DevOps & infra** | `chat_agent_gitter`, `chat_agent_dockerer`, `chat_agent_kuberneter`, `chat_agent_jenkinser`, `chat_agent_ssher`, `chat_agent_scper` |
| **Data & interpretation** | `chat_agent_sqler`, `chat_agent_mongoxer`, `chat_agent_file_creator`, `chat_agent_file_extractor`, `chat_agent_file_interpreter`, `chat_agent_image_interpreter`, `chat_agent_summarize_text` |
| **Notifications & comms** | `chat_agent_send_email`, `chat_agent_notifier`, `chat_agent_telegramer`, `chat_agent_whatsapper`, `chat_agent_recmailer` |
| **Desktop UI automation** | `chat_agent_shoter` (read-only), `chat_agent_keyboarder`, `chat_agent_mouser`, `chat_agent_windower` |
| **Routing** | `chat_agent_asker` |
| **Archives & decompilation** | `chat_agent_j_decompiler`, `chat_agent_de_compresser` |
| **Game engines** | `chat_agent_unrealer` (drives an Unreal Engine 5 editor via the Unreal MCP plugin's TCP socket; canvas counterpart is the Unrealer workflow agent — see §57) |
| **Web & browser** | `chat_agent_playwrighter` (drives a real browser through a scripted step list — login, forms, clicks, waits, extraction, screenshots, asserts, downloads; canvas counterpart is the Playwrighter workflow agent) |
| **Crawling, monitoring, APIs, prompts, crypto** | `chat_agent_crawler`, `chat_agent_monitor_log`, `chat_agent_monitor_netstat`, `chat_agent_apirer`, `chat_agent_prompter`, `chat_agent_kyber_keygen`, `chat_agent_kyber_cipher`, `chat_agent_kyber_deciph` |

## 29. Wrapped runtime lifecycle tools (6)

After launching a wrapped agent, you can monitor and control it:

| Tool | What it does |
|---|---|
| `chat_agent_run_list` | List recent runs (capped by `chat_agent_limit_runs`). |
| `chat_agent_run_status` | Inspect status of one run. |
| `chat_agent_run_log` | Read the latest log excerpt. |
| `chat_agent_run_stop` | Stop a run by `run_id`. |
| `chat_agent_run_wait` | **Block** until a run reaches a terminal status (or `max_seconds` fires). Replaces busy-poll loops. |
| `window_present(title)` | Fast (<100 ms) yes/no helper for "is this window open?" — use this instead of `chat_agent_image_interpreter` for window-presence gates. |

## 30. ACPX & Skills tools (12)

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

The 24 seed skills (`agent/skills_pkg/<name>/SKILL.md`) cover: `hello-world`, `skill-creator`, `acp-router`, `setup-new-acpx-key`, `summarize`, `weather`, `code-review` (senior-engineer git-diff review with a verdict), `security-audit` (multi-scanner SAST/secret/dependency sweep), `kali-pentest` (authorized Kali Linux / MCP-Kali-Server assessment runbook driving the Kalier agent), `tlamatini-*` (8 maintenance skills: csrf-exempt-audit, exec-report-row-adder, allowed-hosts-tighten, planner-trace-replay, flow-from-objective, flw-doctor, new-acp-agent, static-version-bumper), and OpenClaw-format ports for `github`, `notion`, `jira`, `slack`, `gmail`, `todoist`, `trello`.

---

# Part VI — Inside Tlamatini

This is the deep-dive section. Skip if you only want to use Tlamatini.

## 31. The big picture

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

## 32. The Five Layers

The system is organized in five conceptual layers. Each layer has a single responsibility.

| Layer | Responsibility | Where it lives |
|---|---|---|
| **1. Persisted toggles** | Database rows for `Mcp`, `Tool`, and `Agent` — the UI's enable/disable state. | `agent/models.py` |
| **2. Runtime MCP services** | System-Metrics (WebSocket) and Files-Search (gRPC) running as daemon threads. | `agent/mcp_*` |
| **3. Context fetcher chains** | LCEL sidecars that fetch system / files context and inject it into the answer chain. | `agent/chain_*_lcel.py` |
| **4. Main answer chains** | Basic / History-aware / Unified chains. `factory.py` monkey-patches `invoke()` to wire context from sidecars. | `agent/rag/chains/` |
| **5. Unified-agent tools** | Synchronous LangChain `@tool` functions returned by `get_mcp_tools()`. Only active when the unified-agent chain is selected. | `agent/tools.py` |

## 33. RAG pipeline

When you set a directory as context:

1. **Load** every text file under the path.
2. **Chunk** into 3000-character windows with 800-char overlap.
3. **Extract metadata** — class names, function names, imports, file roles (`controller`, `data_model`, `service_layer`, …).
4. **Embed** each chunk using the model in `config.embeding-model`.
5. **Build** the FAISS index.
6. **Build** the BM25 index in parallel.
7. At query time, both indexes return their top-K hits; **Reciprocal Rank Fusion** combines them; **context budgeting** picks chunks within token limits, allocating 60% to high-relevance, 20% to architecture, 15% to related, 5% to documentation.

If embedding fails (out-of-memory), **memory-insufficient fallback** kicks in: the loaded source files are packed into a raw context block and injected directly into the prompt-only / unified-agent path. You get reduced retrieval quality, not a wiped chat.

## 34. Embedding-memory pre-flight guard (GPU hosts)

When you click **Set directory as context** in the Context menu, Tlamatini is about to do something dangerously bursty: walk every text file under the path, split each into chunks, push every chunk through Ollama's embedding API to build a FAISS index, and only then return control to the chat. On a laptop or consumer GPU this is the moment of truth — if the embedding model needs more VRAM than the GPU can spare, Ollama starts evicting and re-loading on every batch, and what should be a thirty-second operation turns into a multi-hour stall while RAM and VRAM swap back and forth across the PCIe bus. The dev box this codebase is calibrated on — an RTX 4070 Laptop with 8 188 MiB of VRAM — sees exactly this with the default embedding model `qwen3-embedding:8b`, which sits at ~6.24 GB resident, 77.9 % of total. Add a chat model on top, and the GPU is over capacity.

The **embedding-memory pre-flight guard** (`Tlamatini/agent/embedding_memory_guard.py`, introduced 2026-05-12) catches the problem before the embed burst starts. It runs only when an NVIDIA GPU is detected. On CPU-only, AMD, and Apple Silicon hosts it is a silent no-op, and the legacy load path is unchanged. The guard is informational and non-blocking — it raises a chat-bubble warning, then lets the load proceed. The choice of whether to wait it out, hit Cancel, or change models in `config.json` belongs to the user.

### Where the guard fires

There is exactly one hook in the codebase, and it lives in `agent/consumers.py::setup_contextual_rag_chain`. After the consumer broadcasts the "Loading context…" banner to the chat (`MSG_AGENT_LOADING_CONTEXT`), and before it schedules the heavy `asyncio.to_thread(setup_llm_with_context, …)` call that drives `FAISS.from_documents(...)`, the guard runs inside its own `asyncio.to_thread` — both so a slow `nvidia-smi` probe never blocks the Channels event loop, and so the whole step can be wrapped in `try/except Exception` to enforce a strict fail-open contract.

```
WebSocket "set-directory-as-context"
        ↓
consumers.py:setup_contextual_rag_chain(path_only)
        ↓
broadcast MSG_AGENT_LOADING_CONTEXT  ──→  user sees "Loading context…"
        ↓
► embedding_memory_guard.check_embedding_memory_for_directory(...)
        │
        ├── returns None     → proceed silently
        │                      (no GPU, under threshold, or any probe failed)
        │
        └── returns warning  → broadcast HTML warning chat bubble
                             → proceed anyway (informational, non-blocking)
        ↓
asyncio.to_thread(setup_llm_with_context, ...)
        └─ OllamaEmbeddings + FAISS.from_documents(...)   ← the VRAM burst
```

If anything goes wrong inside the guard — `nvidia-smi` missing, Ollama unreachable, a JSON-shape change in a future Ollama release — the `try/except` swallows the exception, prints a one-line `--- [EMBED-MEM] Pre-flight check skipped (fail-open): …` to `tlamatini.log`, and the load continues. A diagnostic must never block the user. This is the same fail-open philosophy `agent/gpu_perf.py` uses for its model-pinning hook, and it pairs naturally with the existing `_has_nvidia_gpu()` cache that the guard re-uses for its first gate.

### Detection — who pays for the check

The guard's very first action is to ask the cached `gpu_perf._has_nvidia_gpu()` probe whether this host has an NVIDIA GPU at all. That helper runs `nvidia-smi -L` exactly once per process and caches the result in a module-level boolean. On a CPU-only Linux or Windows machine, an AMD GPU, or Apple Silicon, the probe returns `False` once at server start, and **every subsequent call to the guard returns `None` immediately** — no subprocesses spawned, no HTTP calls made, no overhead beyond a single boolean check.

This is the portability guarantee. A fresh `git pull` on a no-GPU box behaves exactly as before the guard existed. The 28 dedicated no-GPU compatibility tests in `agent/test_embedding_memory_guard.py::NoGpuCompatibilityTests` pin the contract in place; the most consequential of them, `test_real_entry_point_call_never_raises`, calls the real entry point with the real subprocess + real urllib code paths and asserts the return is **either** `None` **or** a well-formed warning dict — never an exception. The same test passes on this RTX 4070 dev box and on a CPU-only CI image.

### Three-tier VRAM prediction

When the GPU gate passes, the guard predicts the embedding model's resident VRAM in three tiers, in priority order — each more accurate than the next is convenient:

**Tier A — model already resident.** A `GET /api/ps` against the Ollama daemon returns a list of currently-loaded models, each with a `size_vram` field that is the exact bytes Ollama allocated for that model. If the configured `embeding-model` shows up in the list, the guard uses `size_vram` verbatim. There is no estimation here — this is daemon ground truth.

**Tier B — model on disk but not loaded.** A `POST /api/show` returns the model's metadata: parameter count, quantization level, embedding dimension, layer count, attention shape. The guard computes weights bytes as `parameter_count × bits_per_weight(quant) / 8`, then multiplies by an overhead factor that accounts for KV cache, activation buffers, and the GGML allocator's slack. The bits-per-weight table follows the standard llama.cpp / GGUF averages — `F16` is 16 bits, `Q8_0` is 8.5, `Q4_K_M` is 4.83, `Q2_K` is 2.96. Unknown quants fall back to a conservative `5.0`. The overhead is **×1.40** for models with at least one billion parameters and **×2.20** for sub-1 B models, where the proportional cost of fixed KV/buffer overhead is larger.

**Tier C — anything else.** If Ollama is down, the model has not been pulled, or it is a cloud model (`:cloud` suffix), the guard returns `None` and lets the load proceed. This is fail-open by design.

The overhead numbers are not guesses; they were calibrated on this dev box against two real models:

| Model | params × bits/8 (raw) | × overhead = predicted | Ollama-reported resident | error |
|---|---|---|---|---|
| `qwen3-embedding:8b` (Q4_K_M) | 4.54 GB | **6.36 GB** (× 1.40) | 6.24 GB | +1.9 % |
| `Nomic-Embed-Text:latest` (F16) | 274 MB | **603 MB** (× 2.20) | 600 MB | +0.5 % |

Both predictions land within 2 % of the measured value. The two-tier overhead split (large vs small) gives a tighter fit than any single multiplier would have. When a future model family proves the calibration off by more than 10 %, the two `_OVERHEAD_*` constants in the module are the only knobs to recalibrate.

The same `/api/show` payload also tells the guard the model's embedding dimension. The key is architecture-prefixed — `qwen3.embedding_length=4096`, `nomic-bert.embedding_length=768` — and the guard finds it by suffix match, so a new architecture (whatever Ollama adopts next) does not need code changes.

### What VRAM is the model competing against?

The guard reads total VRAM via `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits`, parses one integer per line, and **picks the smallest of the values**. Why the smallest? Because Ollama loads each model into a **single device** by default. Using the sum of all GPUs would silently under-report the constraint on a heterogeneous rig (e.g. an 8 GiB laptop card paired with a 4 GiB eGPU), and using the largest would mis-predict on the bad cases the warning is meant to catch. The smallest single-GPU value is the conservative constraint.

The 80 % threshold then compares: when **predicted_vram ≥ 0.80 × smallest_gpu_total**, the warning fires. The threshold is a function argument (default `0.80`) so the trigger can be tuned per installation. The number was picked to leave room for chat-model overhead, OS-reserved memory, and the activation buffers Ollama needs on every embed batch — anything tighter than 80 % is already in the "expect slow embed throughput or RAM↔VRAM swap" zone.

### The chat-bubble warning

When the threshold trips, the guard returns a structured dict and the consumer renders it as an HTML chat bubble — the same `agent_message` surface the chat already uses for every Tlamatini-side message. A real example from this dev box, with the threshold artificially lowered to 70 % so `qwen3-embedding:8b` trips:

> ⚠️ **Embedding-memory warning**
>
> Embedding model `qwen3-embedding:8b` needs ~6,378 MiB of VRAM (currently resident in VRAM), which is **77.9 %** of the smallest GPU's total (8,188 MiB) — above the safety threshold of 70 %.
>
> Projected FAISS vector store (RAM, not VRAM): ~28 MiB across 1,847 chunks at dim 4096.
>
> Context loading will continue, but expect slow embedding throughput or RAM↔VRAM swap. To eliminate the pressure, switch `embeding-model` in `config.json` to a smaller model (e.g. `nomic-embed-text:v1.5`) and restart.

Notice the source qualifier: *currently resident in VRAM* means the prediction came from Tier A — exact `/api/ps`. *Estimated from model parameters* means Tier B. The user always knows whether they are looking at ground truth or an extrapolation.

The FAISS line is an informational projection. The guard pre-scans the chosen directory the same way `CustomTextLoader` will, applying the same exclusions (`package-lock.json`, `yarn.lock`, `*.<user-omitted>`, …), and counts projected chunks per file using `ceil(file_size / (chunk_size − chunk_overlap))`, capped by `max_chunks_per_file`. Multiplied by `embedding_dim × 4` bytes (float32 vector storage), that gives the FAISS index's RAM footprint. This is **not** VRAM; FAISS lives on CPU. It is shown for one reason: very large directories produce very large indexes that can matter for the host's RAM budget independently of the GPU question.

### Tuning, overrides, and explicit non-goals

The guard exposes four knobs, all in the module:

| Knob | Default | When to change |
|---|---|---|
| `threshold` (function argument) | `0.80` | Pass `0.70` on small GPUs (6 GB cards) where 80 % is already too tight. |
| `_OVERHEAD_LARGE` constant | `1.40` | Recalibrate against `/api/ps` if a new model family proves it off by > 10 %. |
| `_OVERHEAD_SMALL` constant | `2.20` | Same calibration story for sub-1 B models. |
| `_QUANT_BITS` dict | standard table | Add an entry when a new GGUF quant ships. |

And four things the guard deliberately does **not** do:

It does not abort context loading. The warning is informational. If you want abort-on-warning behavior, you can wire a confirm/cancel WebSocket round-trip — the surface is described in `agent_page_init.js` near the `set-dir-context` listener.

It does not estimate the chat model's VRAM. Only the embedding model is checked, because that is the model the directory-load path forces into VRAM at this exact moment. The chat model is handled separately by `gpu_perf.pin_ollama_model`.

It does not persist warnings. Each context-load runs an independent check; toggling `config.json` and reloading will surface a fresh prediction next time.

It does not call `nvidia-smi` on CPU-only hosts. Both gates — the cached `_has_nvidia_gpu_cached()` and the `_gpu_total_memory_bytes()` query — short-circuit before any subprocess spawn. `top` on a CPU-only box will show zero new processes when a user clicks **Set directory as context**.

### Test coverage

The guard ships with **49 automated tests** in `agent/test_embedding_memory_guard.py`, organized into seven `SimpleTestCase` classes. Two of them deserve special mention.

`PredictFromShowTests` (3 tests) pins the Tier-B math against the two reference models the calibration was derived from: `qwen3-embedding:8b` must predict within ±5 % of the 6.24 GB measured, and `Nomic-Embed-Text:latest` within reasonable bounds of the 600 MB measured. If a future change to the overhead constants or the bits-per-weight table breaks these, the suite fails loudly.

`NoGpuCompatibilityTests` (28 tests) is the portability proof. Its coverage matrix walks every failure mode a non-NVIDIA / no-driver / no-Ollama machine can hit: `nvidia-smi` binary missing entirely; `nvidia-smi` present but driver unloaded; the binary hangs and `subprocess.run` raises `TimeoutExpired`; permission denied; generic `OSError`; empty or unparseable output; heterogeneous multi-GPU rig; `gpu_perf` module missing or its probe raising; Ollama daemon offline; closed port; malformed URLs; model not in `/api/ps`; entry on a CPU-only host; GPU detected but `--query-gpu` fails; GPU detected but Ollama offline; pathological 0 MiB GPU readings; empty `ollama_base_url`; deleted or non-existent directory paths; unreadable files inside the walked tree; partial warning dicts with missing optional keys. The capstone test, `test_real_entry_point_call_never_raises`, makes the *actual* `subprocess.run(["nvidia-smi", …])` and `urlopen("http://127.0.0.1:11434/…")` calls against whatever the runner offers, and asserts the return is **either** `None` **or** a well-formed warning dict — never an exception. The same test passes on this RTX 4070 dev box (returns `None` because qwen3-embed sits at 77.9 %, just under the 80 % gate) and on a CPU-only CI image (returns `None` because the GPU gate fails fast).

To run the full guard suite:

```
cd Tlamatini
python manage.py test agent.test_embedding_memory_guard --verbosity=2
```

Forty-nine tests in roughly 2.3 seconds, no database setup, no GPU required.

## 35. Multi-Turn execution pipeline

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

## 36. ACPX runtime mechanics

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

## 37. Database models

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

## 38. The application log (`tlamatini.log`)

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

## 39. ASCII / box-drawing diagrams in chat

LLM-generated ASCII art / flowcharts / column layouts render in the chat with a fixed-width font and preserved whitespace. The LLM is instructed (rule 13 in `prompt.pmt`) to wrap diagrams in `BEGIN-DIAGRAM` / `END-DIAGRAM` markers. There is also auto-detection: any run of consecutive lines containing box-drawing characters (`│┃|─━┌┐└┘├┤┬┴┼╭╮╯╰`), arrow glyphs (`▲▼►◄→←↑↓`), or ASCII-art runs (`+`, `-`, `=`, `|`) is wrapped automatically. Both pipelines emit `<pre class="ascii-diagram">…</pre>` HTML.

---

# Part VII — Configuration Reference

The main file is `Tlamatini/agent/config.json`.

| Mode | Resolution order |
|---|---|
| Source | `Tlamatini/agent/config.json` |
| Frozen | `<install-dir>/config.json` next to the executable |
| Both | `CONFIG_PATH` env var, if set, wins over both |

## 40. LLM settings

```json
{
  "embeding-model": "Nomic-Embed-Text:latest",
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
| `kali_server_url` | Base URL of the MCP-Kali-Server (`server.py`) on your Kali box. Tlamatini is the **embedded client** — the `chat_agent_kalier` tool auto-injects this as the default `server_url` on every run, so chat pentest prompts never repeat the address (the LLM may still override per-call). Default `http://127.0.0.1:5000` (works for WSL2 localhost-forwarding or an SSH tunnel); editable via `Config -> URLs`. |

You can still edit `config.json` by hand, but you no longer have to for the common cases. The chat navbar's `Config -> Models` dialog writes the model-name subset, and `Config -> URLs` writes the endpoint / host / port subset. The browser validates shape first, the backend validates again, and `config_loader.save_config_updates()` merges only the changed keys atomically into whichever `config.json` is active for the current mode (source or frozen).

## 41. RAG settings

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

## 42. Internet search settings

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

## 43. MCP services

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

## 44. ACPX settings

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

## 45. Image interpreter

```json
{
  "image_interpreter_base_url": "http://127.0.0.1:11434",
  "image_interpreter_model": "qwen3.5:cloud",
  "image_interpreter_temperature": 0
}
```

## 46. Advanced options

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

## 47. The three-step build pipeline

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

## 48. Versioning

Tlamatini follows [Semantic Versioning 2.0.0](https://semver.org/) — `MAJOR.MINOR.PATCH` — but the **single source of truth is a git tag**, not a number sitting in any source file. You never hand-edit a version anywhere. You tag, then you build, and the three build scripts in §47 each bake the resolved value into the artefact they produce.

### What the three numbers mean

- **MAJOR** bumps when something that already shipped breaks for the user: the `.flw` file schema changes, an Agent Contract is removed, an LLM tool is renamed, a public endpoint URL changes. The first `2.0.0` is the first release where loading an old `.flw` might not just work.
- **MINOR** bumps when you add a backward-compatible feature: a new agent (ACPXer was a minor bump), a new toolbar checkbox, a new SKILL package, a new HTTP endpoint, a new optional field on an existing API.
- **PATCH** bumps for backward-compatible fixes: the conjunction-parser fix, the exec-report ordering fix, the ACPX `oneshot-prompt` capture fix — anything that closes a regression without changing surface.

Pre-releases use the standard SemVer suffixes — `2.0.0-alpha.1`, `2.0.0-beta.1`, `2.0.0-rc.1`. They sort **before** the final release, so `2.0.0-rc.2` < `2.0.0` for the Windows installer registry and for Python tooling alike.

### Cutting a release in five commands

```powershell
git status                                          # clean tree, on main
git tag -a v1.7.1 -m "Release 1.7.1: <one-liner>"   # annotated tag
git push origin v1.7.1
python build.py
python build_uninstaller.py
python build_installer.py
```

All three build scripts pick the tag up from `git describe --tags` automatically. The final artefact lands in `dist/Tlamatini_Release_v1.7.1/`, named for the version so the file you hand to a user is unambiguous before they even unzip it.

### Where the version shows up in a running install

The build computes the version once and bakes it into four surfaces:

- **`Tlamatini/agent/_version.py`** — generated at build time, gitignored, read at runtime by `agent.version.get_version()`. This is what every in-process surface reads.
- **Win32 `VERSIONINFO`** — `Tlamatini.exe`, `Installer.exe`, and `Uninstaller.exe` all carry the version in their resource fork. Right-click the file → Properties → Details → ProductVersion.
- **Release folder name** — `dist/Tlamatini_Release_v1.7.1/`.
- **Runtime surfaces** — the About dialog renders `Tlamatini v{{ version }}` (Django context processor); the startup banner prints `--- [VERSION] Tlamatini 1.7.1` to both the console and `tlamatini.log`; `GET /agent/version/` returns `{"version":"1.7.1","commit":"abc1234","date":"…","source":"generated"}` as an **open** endpoint suitable for a health-check.

If the four surfaces ever disagree, your build was run with a stale `$env:TLAMATINI_VERSION` or against an out-of-date `_version.py` — clear them and re-run `build.py`.

### What happens if you don't tag

The build never fails for "no version" — and the version surface is always a clean SemVer like `1.1.1`. The resolver returns the **bare base tag** reachable from HEAD; distance / commit / dirty state are deliberately stripped from the displayed version:

| Situation | Version baked in |
|---|---|
| Tag exists, HEAD exactly on `v1.2.0` | `1.2.0` |
| Tag exists, HEAD 17 commits past, clean tree | `1.2.0` |
| Tag exists, HEAD 17 commits past, uncommitted edits | `1.2.0` |
| No tags at all | `0.0.0` |
| Not a git repo (e.g. download zip) | `0.0.0+unknown` |

No `.devN`, no `+gSHA`, no `.dirty` ever appears in the version string. Distance from the tag and dirty state are git concerns and live in `git status` / `git describe --long --dirty`, not in the user-facing version.

### Overriding the resolver

There are four sources of the version, in precedence order:

1. `--version X.Y.Z` on the build script's command line (highest).
2. `$env:TLAMATINI_VERSION` exported in the shell.
3. `git describe --tags --abbrev=0 --match 'v[0-9]*'` against the working tree — the bare base tag, no distance/dirty suffix (the normal path).
4. The sentinel `0.0.0+unknown` (lowest — only fires when there is no git at all).

`build.py` exports `$env:TLAMATINI_VERSION` after it resolves, so `build_installer.py` and `build_uninstaller.py` in the same shell see exactly the same value — the three artefacts cannot disagree. Even on an untagged commit, the git-derived dev version stays consistent across all three.

The full contract — including the recovery path for a mis-tagged release, the runtime resolver internals, the file-by-file integration map, and the FAQ — lives in [`VERSIONING.md`](VERSIONING.md) at the repo root.

## 49. What the installer does

When an end user runs `Installer.exe`:

1. Tkinter GUI to choose installation directory.
2. Extracts `pkg.zip` into `<install_path>/Tlamatini/`.
3. Locks agent venv permissions.
4. Writes `config.json` with installation settings.
5. Copies `Uninstaller.exe` into the install dir.
6. Creates desktop and Start Menu shortcuts (`Tlamatini.lnk`).
7. Registers `.flw` extension to open with Tlamatini.
8. Cleans the PyInstaller bundle path from helper subprocess environments so PowerShell helpers and Explorer restarts don't stall.

## 50. What the uninstaller does

1. Removes shortcuts (with Explorer restart for immediate effect).
2. Unregisters the `.flw` association and clears cached shell state.
3. Deletes all application files **except** `<install_path>/Tlamatini/agents/*` (preserves user-created agents).
4. Removes the install directory if empty.

## 51. Frozen-mode behavior

The Multi-Turn implementation carries frozen-build awareness in supporting runtime code:

- `config_loader.py` resolves `CONFIG_PATH`, then executable-local `config.json`, then module-local.
- `FileSearchRAGChain` resolves its default `config.json` from the executable directory in frozen mode.
- Template-agent discovery checks both `<install_dir>/agents` and `<install_dir>/Tlamatini/agent/agents`.
- `_get_agents_root()` in `chat_agent_runtime.py` resolves from `sys.executable` in frozen mode, from `__file__` in source mode — both paths are logged at INFO level.
- `_resolve_python_executable()` tries `PYTHON_HOME`, then bundled `python.exe` beside the frozen executable, then PATH.

---

# Part IX — The Command Deck (API + WebSocket)

## 52. WebSocket protocol

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

## 53. HTTP endpoints

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

`/update_<agent>_connection/<agent_name>/` for every agent type that has connections — Starter, Ender, Stopper, Raiser, Emailer, Monitor-Log, Notifier, Executer, Pythonxer, Sqler, Whatsapper, Recmailer, OR, AND, Croner, Mover, Mouser, Keyboarder, Windower, Sleeper, Cleaner, Deleter, Asker, Forker, Dockerer, Pser, Kuberneter, Apirer, Jenkinser, Crawler, Summarizer, FlowHypervisor, Counter, File-Interpreter, Image-Interpreter, Gatewayer, Gateway-Relayer, Node-Manager, File-Creator, File-Extractor, J-Decompiler, Kyber-KeyGen/Cipher/DeCipher, Parametrizer, FlowBacker, Barrier, Googler, TeleTlamatini, WhatsTlamatini, ACPXer.

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

## 54. Common issues

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

## 55. Debug mode

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

## 56. Log locations

| What | Where |
|---|---|
| Django / Multi-Turn console | stdout |
| **Application-wide** | `Tlamatini/tlamatini.log` (truncated on every start; see §37) |
| ACP workflow agent logs | `<pool_directory>/<agent_name>/<agent_name>.log` |
| Chat-launched wrapped agents | `agent/agents/pools/_chat_runs_/<agent>_<seq>_<id>/<agent>_<seq>_<id>.log` (failed runs preserved) |

---

# Bonus Chapter — § 57. The Day Tlamatini Learned to Drive Unreal Engine

> *A bonus chapter, in the spirit of the book — narrative first, reference second. Read this if you want to understand not just **how** Tlamatini talks to Unreal Engine 5, but **why** the conversation looks the way it does, and how to make it bullet-proof on your own box. If you only need the dry reference, the matching coverage lives in **README §6** and in the agent's own `agents_descriptions.md` entry.*

## 57.1. The shape of the problem

For most of the work Tlamatini does, the universe is plain text. Files have lines, lines have characters, the LLM produces a string, a tool consumes a string, and the world rearranges itself. Even the visual workflow designer is, at the end of the day, a YAML file the engine reads and obeys.

Unreal Engine is not like that. Unreal Engine is a **running editor process** holding a hierarchy of in-memory objects — actors, components, blueprints, widgets, level streaming volumes — and it does not want you to reach in from outside. It wants you to drive it through its own UI: click here, drag this into the level, type this transform, press Compile. That is fine if you are a human at a desk. It is a problem if you want a chat agent to *do* something — anything — in the editor without you needing to take your hands off the keyboard.

The **Unreal MCP** project, hosted at `https://github.com/chongdashu/unreal-mcp` (MIT-licensed, UE5.5+), solves that problem from the engine side. It is a small C++ plugin that you drop into your project's `Plugins/UnrealMCP/` folder, enable from `Edit → Plugins`, and forget. From the moment the editor opens, the plugin starts listening on `127.0.0.1:55557` for **JSON commands over a TCP socket**. The wire shape is brutally simple — one command per connection, going in as `{"type": "<verb>", "params": {...}}`, coming back as `{"status": "ok"|"error", "result": {...}, "error": "..."}`. That is the whole API. There is no SDK. There is no authentication. There is just a socket, and a script that knows the right verbs.

The Tlamatini side is even simpler. The **Unrealer** agent (`agent/agents/unrealer/unrealer.py`, the 62nd entry in the catalog) is a pool subprocess that opens that socket, sends one command, captures one response, writes it as an `INI_SECTION_UNREALER<<<` block to its own log, triggers any downstream agents, and exits. The plugin does the heavy lifting; Tlamatini does the orchestration. It is, structurally, the smallest agent in the whole catalog — about 120 lines of business logic on top of the standard pool-agent boilerplate — and it gives you the entire 28-command surface of the Unreal MCP plugin.

## 57.2. Where the plugin lives (the MCP git location, repeated for emphasis)

You install the plugin once, per Unreal project. The canonical reference implementation is:

- **Repository**: `https://github.com/chongdashu/unreal-mcp`
- **License**: MIT
- **Supported Unreal Engine versions**: 5.5 and newer
- **Plugin folder name (inside your project)**: `Plugins/UnrealMCP/`
- **Default in-engine TCP port**: `55557` on `127.0.0.1`

Two community forks ship the same wire protocol on the same port and work with Tlamatini's Unrealer with no client-side changes:

- `https://github.com/CrispyW0nton/Unreal-MCP-Ghost`
- `https://github.com/gingerol/vhcilab-unreal-engine-mcp`

You are also welcome to fork the plugin and add your own command verbs. Tlamatini's Unrealer does not maintain a client-side allow-list of verbs — it forwards whatever `command` + `params` pair you give it, verbatim. If your fork understands a new verb like `spawn_one_thousand_grass_blades`, your fork will get a call for `spawn_one_thousand_grass_blades`, and Tlamatini will pass the response back into the conversation the same way it does for any other verb. The decoupling is intentional, and it is the entire reason Tlamatini does not need to track the plugin's version.

## 57.3. Wiring up your UE5 project

There is no shortcut, but there are no surprises either:

1. **Clone the plugin** from your chosen upstream (or download the ZIP and unzip it).
2. **Drop the `UnrealMCP` folder** into your project's `Plugins/` directory so the path ends `<YourProject>/Plugins/UnrealMCP/UnrealMCP.uplugin`. If you do not have a `Plugins` directory in your project root, create one — UE5 expects exactly that name.
3. **Open the project in the UE5 editor.** Because the plugin is C++, the editor will offer to rebuild it for your engine version. Accept. If the project is Blueprint-only and you have never built a C++ project before, the editor will first nudge you to install Visual Studio Build Tools (Windows) or the Xcode command-line tools (macOS). This is a one-time set-up.
4. **Enable the plugin** via `Edit → Plugins`, search "UnrealMCP", tick **Enabled**, restart the editor when prompted.
5. **Confirm the listener** by opening `Window → Developer Tools → Output Log` and watching for a line such as `LogTemp: UnrealMCP listening on 127.0.0.1:55557`. That line is the *single* green light you need. Without it, every Unrealer call from Tlamatini will return `Failed to connect to Unreal at 127.0.0.1:55557` — which is the right error message, but not the one you want to chase if you can avoid it.

> A subtlety worth knowing: **you do not need to press Play (PIE)** to drive the editor through Unreal MCP. The plugin operates at editor level — spawning actors, building blueprints, compiling them — and that work happens against the open project, not the running game. Some UMG operations like `add_widget_to_viewport` queue the widget for the next PIE session, so if you are testing a HUD widget you will need to press Play to actually see it. That is an Unreal MCP behaviour, not a Tlamatini one.

## 57.4. The thirty-second conceptual model

```
┌─────────────────────────────────────────┐
│ You (in the Tlamatini chat)             │
└────────────┬────────────────────────────┘
             │ "Run Unreal command with command='spawn_actor' …"
             ▼
┌─────────────────────────────────────────┐
│ Tlamatini Multi-Turn LLM                │
│   → chat_agent_unrealer (one call)      │
└────────────┬────────────────────────────┘
             │ writes config.yaml, spawns child process
             ▼
┌─────────────────────────────────────────┐
│ unrealer.py (pool subprocess, ~120 LOC) │
│   opens socket → 127.0.0.1:55557        │
│   sends {"type":"spawn_actor", …}        │
│   reads JSON until complete             │
│   logs INI_SECTION_UNREALER<<<          │
└────────────┬────────────────────────────┘
             │ TCP/JSON
             ▼
┌─────────────────────────────────────────┐
│ UnrealMCP plugin (inside UE5 editor)    │
│   schedules work on the game thread     │
│   returns {"status":"ok", "result":…}   │
└─────────────────────────────────────────┘
```

The diagram is not lying for the sake of clarity — that **is** the whole pipeline. There is no middle service to start, no daemon to register, no broker to authenticate against. The plugin listens, the agent calls, the answer comes back.

## 57.5. The 28-command surface, organised the way a builder thinks

The wrapped tool `chat_agent_unrealer` and the canvas **Unrealer** node both forward whatever verb you pick, but the upstream plugin's catalog naturally splits into five reasoning units:

- **Reading the level (editor reads).** `get_actors_in_level`, `find_actors_by_name`, `get_actor_properties`. These are the safe, side-effect-free probes you sprinkle through any flow to give the LLM enough context to make decisions ("the level already has a `MyCube`; do I need to spawn another?").
- **Modifying the level (editor writes).** `spawn_actor`, `spawn_blueprint_actor`, `delete_actor`, `set_actor_transform`, `set_actor_property`. The bread-and-butter of any procedural-content flow.
- **Authoring Blueprints (blueprint).** `create_blueprint`, `add_component_to_blueprint`, `set_static_mesh_properties`, `set_component_property`, `set_physics_properties`, `compile_blueprint`, `set_blueprint_property`. You can scaffold an entire new Actor class from chat — give it a static-mesh component, configure its physics, compile it — and then spawn instances of it back into the level in the same conversation.
- **Wiring Blueprint event graphs (node).** `add_blueprint_event_node`, `add_blueprint_input_action_node`, `add_blueprint_function_node`, `connect_blueprint_nodes`, `add_blueprint_variable`, `add_blueprint_get_self_component_reference`, `add_blueprint_self_reference`. This is the niche that ties Tlamatini to *gameplay* engineering and not just level-decoration tooling.
- **Project input + UMG widgets (project, umg).** `create_input_mapping`, `create_umg_widget_blueprint`, `add_text_block_to_widget`, `add_button_to_widget`, `bind_widget_event`, `add_widget_to_viewport`, `set_text_block_binding`. A complete HUD pipeline in seven verbs.

If you forget which verb does what, ask Tlamatini. The agent's `purpose` string in `chat_agent_registry.py` carries the full taxonomy, so the LLM has it in its tool-description prompt at all times.

## 57.6. The smallest possible "hello, Unreal" you can run today

Once UE5 is open with the plugin enabled and Tlamatini is running:

1. Open the chat at `http://127.0.0.1:8000/agent/`.
2. Tick **Multi-Turn**. Tick **Exec Report** too — you will want the run table.
3. Send: `"Run Unreal command with command='get_actors_in_level'."`

A few seconds later you should see:

- The chat LLM picked `chat_agent_unrealer` from the planner.
- The wrapped runtime spawned `unrealer_001_<id>` under `agent/agents/pools/_chat_runs_/`.
- The agent's log contains the outbound JSON and the inbound JSON.
- The chat answer carries a one-line summary ("Level contains N actors: …") followed by the per-step **Unrealer Operations** table.

If that round-trip works, the rest of the 28-command surface is just paperwork. If it does not, jump to §57.10 (troubleshooting).

## 57.7. The full demo (built in, no setup beyond the plugin)

Tlamatini ships with a seeded demo prompt — `idPrompt=32`, *Unreal MCP End-to-End Editor Drive* — that puts every command category through its paces in a single Multi-Turn run. It:

1. Sanity-probes the connection (`get_actors_in_level`).
2. Spawns a bare `StaticMeshActor` named `TlamatiniProbe_Cube` (`spawn_actor`).
3. Verifies the spawn (`find_actors_by_name`).
4. Scaffolds a brand-new Blueprint Actor (`create_blueprint`) called `BP_TlamatiniProbe`.
5. Gives it a `StaticMeshComponent` (`add_component_to_blueprint`).
6. Compiles it (`compile_blueprint`).
7. Spawns a `BP_TlamatiniProbe` instance (`spawn_blueprint_actor`) called `TlamatiniProbe_Spawned`.
8. Builds a UMG HUD widget called `WBP_TlamatiniProbeHUD` (`create_umg_widget_blueprint` → `add_text_block_to_widget` → `add_button_to_widget` → `add_widget_to_viewport`).
9. Renders the whole run as an HTML report table at the bottom of the answer.
10. Closes with a banner — ✅ FULLY OPERATIONAL, ⚠️ PARTIALLY OPERATIONAL, or ❌ UNREACHABLE — that mirrors the verdict the row-by-row table already gave you.

After the demo finishes, your project will have three new artifacts in it (one actor, one Blueprint, one widget). They are intentionally left in place so you can poke at them in the editor; delete them via the Content Browser when you are done.

If you have never run an Unreal MCP demo before, this is the **one** prompt to start with. It also doubles as a regression test — any change to the plugin, to Unrealer, to the contract registry, or to the wrapped-tool registration that breaks this prompt will be immediately visible in the final per-step table.

## 57.8. Chaining Unreal calls on the visual canvas

For long unattended flows that should run from a `.flw` or a Croner schedule, the **Unrealer** node on the canvas is the right surface. One node executes one command; you chain several together with **Parametrizer** nodes between them to copy a JSON field from one Unreal response into the next Unreal call's params.

The canonical "scaffold a Blueprint and spawn an instance of it" canvas flow looks like this:

```
Starter
  → Unrealer (command: create_blueprint, params.name=BP_X, params.parent_class=Actor)
    → Parametrizer
      → Unrealer (command: add_component_to_blueprint, params.blueprint_name=BP_X, …)
        → Parametrizer
          → Unrealer (command: compile_blueprint, params.blueprint_name=BP_X)
            → Parametrizer
              → Unrealer (command: spawn_blueprint_actor, params.blueprint_name=BP_X, …)
                → Ender
```

The Parametrizer between each leg gives you a place to copy `response_body.result.name` (or any other JSON field the previous step returned) into the next step's `params`. Tlamatini's Agent Contract registry knows about Unrealer's six source fields — `host`, `port`, `command`, `status`, `error`, `response_body` — so the Parametrizer dialog will offer them in its dropdown when you wire the connection.

If you want a branching flow — "if `compile_blueprint` failed, fire a Notifier instead of continuing" — drop a Raiser between the Unrealer and the next Parametrizer and have it watch for `status: error` in the log. That is exactly the pattern any non-Unreal agent uses; nothing about Unrealer is special there.

## 57.9. The bullet-proof checklist (copy this to a sticky note)

Before you start any Tlamatini-driven Unreal session:

| Check | How |
|---|---|
| UE5 5.5+ open with a project loaded | `File → Open Project → <yours>`, leave the editor focused — not minimised to the tray |
| Plugin enabled | `Edit → Plugins → UnrealMCP = Enabled`, editor restarted since you enabled it |
| Listener bound | UE5 Output Log shows `UnrealMCP listening on 127.0.0.1:55557` |
| Port not blocked | PowerShell: `Test-NetConnection -ComputerName 127.0.0.1 -Port 55557` → `TcpTestSucceeded: True` |
| Tlamatini server up | `python Tlamatini/manage.py runserver --noreload` shows the startup banner |
| **Multi-Turn** ticked | The toolbar checkbox left of **Exec Report** |
| Tool enabled | Tools dialog shows `Chat-Agent-Unrealer` ticked (it ships ticked by default after migration `0086`) |

Then run the seeded **Unreal MCP End-to-End Editor Drive** demo (Prompts dropdown → idPrompt 32) as your smoke test. If the demo's final banner is ✅, everything from the wire up to the LLM's understanding is healthy and you can move on to your real work.

## 57.10. When it goes wrong (and what each failure actually means)

Tlamatini's Unrealer agent is designed never to raise into the caller — every failure mode turns into a `status: error` row in the response and, if the call was driven from chat, a clean error message in the Multi-Turn loop instead of a crashed conversation. Reading those messages with a clear head is half the battle.

- **`Failed to connect to Unreal at 127.0.0.1:55557`.** The plugin's listener is not bound. Either UE5 is not running, the plugin is disabled, the plugin failed to rebuild for your current engine version, or — rarely — you have a second editor instance also bound to the same port. Open UE5's Output Log and find the `UnrealMCP listening on …` line; that is your ground truth.
- **`Timeout receiving Unreal response`.** UE5's game thread is busy. Most often this happens during `compile_blueprint` on a non-trivial graph. Widen `read_timeout` in the canvas node's `config.yaml` or in the wrapped-tool call. Do not lower `connect_timeout` to compensate; the two are independent.
- **`status: error` from a Blueprint command, no obvious reason.** Check the capitalisation of `parent_class` and similar string params — UE5 type names are case-sensitive and the plugin will not auto-resolve `actor` → `Actor`.
- **The widget appears in the Content Browser but never shows up in the game.** `add_widget_to_viewport` queues the widget at editor level; you still need to press **Play** in the editor to enter PIE and see it. This is an Unreal MCP plugin design choice, not a Tlamatini bug.
- **An actor spawn silently no-ops.** Most often: you spawned inside another object's collision volume. Raise `params.location` to `[0, 0, 150]` (or any sufficiently free patch of world space) and retry.
- **Output Log shows a backtrace from the plugin, not a JSON response.** That is an upstream plugin bug. Reproduce it with the canonical Unreal MCP Python client (the upstream repo ships one in its `Python/` folder), report it upstream, and in the meantime work around it from the Tlamatini side by avoiding that verb.

For the full debugging trail: pool-agent log lives at `<pool>/unrealer_<n>/unrealer_<n>.log`; chat-wrapped runs land under `agent/agents/pools/_chat_runs_/unrealer_<seq>_<id>/unrealer_<seq>_<id>.log`. Both contain the outbound JSON command and the inbound Unreal response verbatim. When you file a bug report — to us, or to the upstream plugin maintainers — paste those two lines, and the conversation gets a lot shorter.

## 57.11. Why this matters

A drag-and-drop workflow designer that can issue real, structured commands to a real, running Unreal Engine 5 editor is not the kind of bridge a small project usually ships. Tlamatini gets to ship it cheaply for three reasons that are worth naming explicitly, because each is the result of a design choice we made on other parts of the system long before Unreal entered the picture.

1. **The pool-subprocess model.** Every workflow agent in Tlamatini already runs as its own short-lived Python interpreter, talking to the engine over plain text logs and `INI_SECTION_<TYPE><<<` blocks. The Unreal MCP plugin's TCP/JSON protocol slotted into that model without any new runtime — the Unrealer agent is just a pool subprocess that happens to open a socket instead of running `git log` or sending an email.
2. **The Agent Contract registry.** Every agent's connection-field shape, parametrizer source fields, and `secret_paths` are declared once in `agent/services/agent_contracts.py`. Adding Unrealer was a single contract entry — and from that one entry the Flow Compiler, the canvas wiring, the Parametrizer dialog, the `.flw` save/load redaction, and the Validate dry-run all "just worked".
3. **The wrapped chat-agent runtime.** Adding `chat_agent_unrealer` was one entry in `chat_agent_registry.py` plus two migrations (one for the Agent row, one for the Tool row). The wrapped runtime did the rest — sequencing, isolation, log capture, deduplication, exec-report integration, Parametrizer-compatibility, the lot.

In other words: when a future engine — Unity, Godot, Blender, Houdini — exposes an equivalent MCP-style socket, **the cost of supporting it from Tlamatini is one new pool agent file, one contract entry, and two migrations**. The hard work is already done. That is the architectural payoff of the past year of refactoring, and Unreal MCP is the first place outside the existing 62-agent catalog where the cheque cashes for a brand-new domain.

Welcome to driving Unreal Engine 5 from chat. Mind the collision volumes.

---

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
| **De-Compresser** | Deterministic short-running compression / decompression agent (`.gz` / `.zip` / `.7z` / `.tar.gz` / `.gz.tar`). |
| **jd-cli** | Java Decompiler CLI tool bundled with the application. |
| **Jenkinser** | CI/CD pipeline trigger agent. |
| **Kalier** | Kali Linux / MCP-Kali-Server bridge agent for AI-assisted pentesting (nmap, gobuster, dirb, nikto, sqlmap, metasploit, hydra, john, wpscan, enum4linux, raw commands). |
| **Keyboarder** | Deterministic PyAutoGUI-based keyboard automation. |
| **Kyber-KeyGen / Cipher / DeCipher** | CRYSTALS-Kyber post-quantum encryption agents. |
| **LangChain** | Framework for LLM applications. |
| **LangGraph** | Stateful, multi-actor LangChain extension. |
| **Logic Gate** | Agent that performs boolean operations (AND/OR/Barrier) on events. |
| **MCP** | Model Context Protocol — standard for tool/context communication. |
| **Mouser** | PyAutoGUI-based pointer movement agent. |
| **NodeManager** | Long-running infrastructure registry that probes nodes. |
| **Unreal MCP** | Open-source UE5 plugin (`https://github.com/chongdashu/unreal-mcp`, MIT, UE5.5+) that listens on `127.0.0.1:55557` for JSON commands and dispatches them onto the editor's game thread. Tlamatini is a client of this plugin — it does not embed it. |
| **Unrealer** | Tlamatini agent that drives Unreal Engine 5 through the Unreal MCP plugin's TCP/JSON protocol. Available both as a wrapped Multi-Turn tool (`chat_agent_unrealer`) and as a visual canvas node. The 62nd entry in the agent catalog. |
| **Notifier** | LangGraph-based browser-notification agent. |
| **output_agents** | Config field used by Ender, Stopper, Cleaner for downstream canvas wiring (vs `target_agents` for "agents to start"). |
| **Parametrizer** | Strict single-lane queue that maps source-agent log segments into target-agent config.yaml. |
| **Playwrighter** | Tlamatini agent that drives a REAL browser (Playwright — Chromium/Firefox/WebKit) through a scripted, interactive step list (goto/click/fill/wait_for/extract/assert/screenshot/download). Set `headless: false` to watch it and `hold_open_seconds: N` (alias `hold_open_ms`) to keep the browser visible N seconds after the last step before it closes. Available both as the wrapped Multi-Turn tool `chat_agent_playwrighter` and as a visual canvas node. The 65th entry in the agent catalog. |
| **Pool** | Directory where deployed agent instances are stored. |
| **Pser** | LLM-powered fuzzy process finder. |
| **Pythonxer** | Inline-Python agent with Ruff lint + exit-code gating. |
| **PyAutoGUI** | Python library for mouse/keyboard control, used by Mouser and Keyboarder. |
| **RAG** | Retrieval-Augmented Generation. |
| **Reanimation Offset** | Saved log-file position to handle restarts and rotation. |
| **Recmailer** | LangGraph IMAP receiver with LLM keyword analysis. |
| **RRF** | Reciprocal Rank Fusion — method for combining ranked lists. |
| **Ruff** | Fast Python linter used by Pythonxer. |
| **Skill** | Markdown-driven extension package — a directory under `agent/skills_pkg/<name>/` with a `SKILL.md` (YAML frontmatter + body). 24 seed skills ship. |
| **Stopper** | Single-threaded pattern-based agent terminator. |
| **Summarizer** | LLM polls source logs for events. |
| **Tlamatini** | Nahuatl for "one who knows" — and the name of this assistant. The LLM responds to it as a self-reference. |
| **TextMeBot** | Third-party WhatsApp messaging API. |
| **WebSocket** | Full-duplex protocol over TCP. |
| **Windower** | Deterministic Win32 window manager — locates an application window by title and runs one window-lifecycle operation (focus / minimize / maximize / restore / move / resize / close / topmost / arrange / list). The third member of the desktop-UI trio (Windower = the window, Mouser = clicks, Keyboarder = typing). |

---

# Appendix C — Changelog

### Recent Updates

- **Kalier "Embedded Client" — Configure the Kali Box Once (v1.7.1) — 2026-05-23** — A usability refinement that turns the chat-side Kalier experience into "set it once, then just ask." Before this, every Multi-Turn pentest prompt had to spell out the Kali box URL (*"using Kali at http://127.0.0.1:5000, run an nmap…"*) — the same friction as Claude Desktop's `client.py --server http://IP:5000`. Now **Tlamatini itself is the embedded MCP-Kali-Server client**: a new top-level **`kali_server_url`** key in `config.json` (default `http://127.0.0.1:5000`, a non-secret that works out of the box for WSL2 localhost-forwarding or an SSH tunnel) is editable through the navbar's **`Config ▸ URLs → Kali server (Kalier)`** dialog, and the wrapped **`chat_agent_kalier`** tool auto-injects it as the default `server_url` on every run. So *"scan 10.0.0.5 and give me a report"* now Just Works — the user (and the LLM) never repeats the address. The injection happens in **`tools.py::_seed_global_agent_defaults(template_dir, runtime_config)`**, called from `_launch_wrapped_chat_agent` **before** the LLM's per-call assignments are applied, so an explicit `server_url=` in the request still wins (override a one-off box); it is Kalier-only, reads via `get_config_value`, and **fails open** (a blank/None/broken config read leaves the template default — a config error must never crash a wrapped-tool launch). Plumbed end-to-end: `views.CONFIG_URL_KEYS` + `CONFIG_URL_URL_FIELDS` register the key, `agent_page.html` adds the `data-config-key="kali_server_url"` input, and the registry `purpose` flipped from "ALWAYS pass server_url" to "DO NOT pass server_url normally — Tlamatini injects the configured box; only override for a one-off." The standalone canvas **Kalier** node and its `config.yaml` are **unchanged** — `.flw`/canvas runs still set `server_url` in the node dialog. A new repo-root guide **`Tlamatini-Kali-Setup.md`** documents the zero-client walkthrough (the legacy Claude-Desktop path lives on in `Claude-Desktop-KALI-MCP-Session.md`). Coverage: `EmbeddedClientConfigTests` + `EmbeddedClientEndpointTests` in `agent/test_kalier_agent.py` (25 new tests; that module now 83 green), ruff clean. Agent / tool / skill counts unchanged (**67** agents / **74** Multi-Turn tools / **42** wrapped / **24** skills) — this is a configuration-UX refinement, not new capability. **⚠️ Authorized targets only.**

- **Added Kalier Agent — The Kali Linux / MCP-Kali-Server Bridge — 2026-05-22** — The agent catalog grows to **67** with **Kalier**, Tlamatini's integration of the **MCP-Kali-Server** (`https://www.kali.org/tools/mcp-kali-server/`) for AI-assisted **penetration testing, recon, and CTF solving**. The upstream project ships two halves — `server.py` (a Flask HTTP API that runs ON the Kali box exposing `/api/command`, `/api/tools/{nmap,gobuster,dirb,nikto,sqlmap,metasploit,hydra,john,wpscan,enum4linux}`, and `/health`) and `client.py` (a thin FastMCP stdio bridge that just forwards to that API). Kalier talks **directly to the Flask API over HTTP using only the Python stdlib (`urllib`)** — exactly like Apirer — so it is fully self-contained, needs no `requests`/`mcp` packages in the agent-pool subprocess, and works identically in source and frozen builds (it does NOT import `agent.*` or the mcp-kali-server code, the same self-contained discipline as ACPXer/Windower). Point `server_url` at the running API server (default `http://127.0.0.1:5000`; for a remote Kali box tunnel it with `ssh -L 5000:localhost:5000 user@KALI_IP`). The `action` field selects ONE capability per run: `command` (any shell command on the Kali box), `nmap`, `gobuster`, `dirb`, `nikto`, `sqlmap`, `metasploit`, `hydra`, `john`, `wpscan`, `enum4linux`, or `health` (probe the server + which tools are installed). It captures the tool's stdout/stderr into one atomic `INI_SECTION_KALIER<<<` block (header `action`, `endpoint`, `method`, `subject`, `return_code`, `success`, `timed_out`, `server_url`; body = the tool output) and ALWAYS triggers `target_agents` (success OR failure) so a downstream Forker can branch on `{success}` / `{return_code}`. Two surfaces ship in lock-step, the same dual pattern as Playwrighter/Unrealer/Windower: the visual **Kalier** canvas node and the wrapped Multi-Turn tool **`chat_agent_kalier`** (the LLM passes the operation as a free-form key=value request; metasploit `options` may be passed as a JSON string). Wiring follows the established 8-step agent pattern: migrations `0097_add_kalier` (Agent row) + `0098_add_chat_agent_kalier_tool` (Tool row); `views.update_kalier_connection_view` + the `POST /update_kalier_connection/<agent_name>/` route; Parametrizer source fields registered in `agent/services/agent_contracts.py` (`_PARAMETRIZER_OUTPUT_FIELDS` + a builtin contract with `secret_paths=('password',)` so the hydra single-password is redacted from `.flw` exports) and `parametrizer.py` (`SECTION_AGENT_TYPES`); `_EXEC_REPORT_TOOLS` under `agent_key="kalier"` (state-changing — it runs live offensive tooling); planner capability hints in `capability_registry.py` so it out-scores generic `execute_command`/`apirer` on pentest prompts; the canvas gradient — deliberately the **only monochromatic ramp** in the whole 67-agent palette: a single-hue black→neon-green "matrix terminal" ramp (`#000000` → `#00471B` → `#00892A` → `#39FF14`). Because every other agent is a multi-hue gradient, a single-hue black→neon ramp is structurally unmistakable at a glance, the black-terminal/neon-green aesthetic is the canonical Kali offensive-security cliché, and the black base keeps it clear of both the mid-green agents (Starter/Whatsapper/Mongoxer/NodeManager) and the red+green agents (Mouser/J-Decompiler/FlowCreator); the four ACP JS files plus the `eslint.config.mjs`-style cross-file global; FlowCreator (`agentic_skill.md` #66) and FlowHypervisor (`monitoring-prompt.pmt` KALIER SPECIAL NOTES — a silent scan up to ~3 min is normal, `success:false`/`timed_out:true` is routable content not an error, only "Cannot reach MCP-Kali-Server" is a real fault). It is an Action agent (starts downstream). Wrapped chat-agent tools move to **42** and total Multi-Turn tools to **74** (20 core + 42 wrapped + 12 ACPX/Skill). The skill catalog also grows to **24** with a new `kali-pentest` SKILL.md — the chat-surface procedural runbook companion (authorized scoped assessment: health → nmap recon → service enumeration → confirm-then-exploit), the same agent+skill dual pattern as Reviewer→code-review and Analyzer→security-audit. **⚠️ Authorized use only** — Kalier is a thin transport to offensive-security tooling; the operator is responsible for ensuring every target is owned or explicitly in-scope. Verified end-to-end: ruff clean, ESLint 0 errors, both migrations applied, `manage.py check` clean, 19 targeted tests (Exec-Report + flow contracts) green, and the planner selects `chat_agent_kalier` on pentest prompts. Reference companions live in README §3.14 + §9.5, `agents_descriptions.md`, `docs/claude/agents.md`, and `agentic_skill.md` entry #66.

- **Playwrighter "Hold the Browser Open" Knob — 2026-05-21** — Fixes a reported bug where Playwrighter closed the browser the *instant* the last step finished, so a user running the **BROWSER SPOTLIGHT** demo with "please wait 10 seconds before closing the browser so I can see it" never got to watch anything — the whole `headless=false` run flashed by in ~2 seconds. The root cause was that `run_browser_flow`'s `finally` block tore the browser down with no delay, and the only way to linger was for the LLM to *happen* to append a `{"action":"wait"}` step (it didn't, and depending on that is fragile). The fix adds a dedicated **`hold_open_seconds`** knob (with **`hold_open_ms`** as a finer-grained alias that wins when both are set) that the agent honors *after* the last step and *before* it closes the browser — on success **or** a mid-flow error, since a failed run is exactly when you want to look at the screen. It is honored regardless of `headless` (harmless when `headless=true`). Because the wrapped-tool config writer only accepts request keys that already exist in `config.yaml`, both fields were added to `agent/agents/playwrighter/config.yaml` (default `0` = close immediately); a new `_coerce_int` helper means a malformed value can never abort an otherwise-good run. Five surfaces move together so the capability is discoverable and reachable: the pool agent (`playwrighter.py`), the template `config.yaml`, the wrapped-tool `purpose` in `agent/chat_agent_registry.py` (which now tells the LLM to pass `hold_open_seconds=<N>` whenever you ask it to keep the browser open / wait before closing), the Create-Flow node mapping in `agent_page_chat.js`, and migration `0095`'s **BROWSER SPOTLIGHT** (#53) + **BROWSER WIZARD** demos (now `hold_open_seconds=10`). Six new tests land in `agent/test_playwrighter_agent.py` (60 total green); ruff + ESLint clean. Agent/skill counts unchanged (**66** / **23**) — this is a behavioural fix, not new capability. Note for existing frozen installs: the agent files were patched on disk so the linger works immediately, but the LLM only *automatically* maps natural-language "wait 10 seconds" → `hold_open_seconds` after a rebuild (the tool description + demo prompts are baked into the executable); until then, include `hold_open_seconds=10` explicitly in the request.

- **Catalog-of-Prompts Demos & Full Test Suites for Windower + Playwrighter — 2026-05-21** — Two follow-ups that make the desktop/browser pair *demonstrable* and *regression-proof*. First, migration `0095_add_windower_playwrighter_demo_prompts.py` seeds **four new fancy demo prompts** into the Catalog of Prompts (the chat **Prompts** dropdown), two per agent — one basic, one medium — each designed so the agent *physically performs on screen* while the user watches: **51 WINDOW SPOTLIGHT** (Windower basic — launch Notepad, maximize it to the foreground, `list`, close) and **52 WINDOW CHOREOGRAPHY** (Windower medium — restore → arrange left half → right half → top-left quadrant → explicit `move_resize` → enumerate every window → close, one move per call so the window visibly dances around the screen); **53 BROWSER SPOTLIGHT** (Playwrighter basic — open `example.com` with `headless=false` so the real browser is visible, extract the heading, assert the link, full-page screenshot) and **54 BROWSER WIZARD** (Playwrighter medium — a multi-step Wikipedia search with `headless=false`: fill the search box → click → wait for the article → extract the title + first paragraph → assert → screenshot). Each prompt renders the agent's house-style HTML report (banner in the agent's own canvas gradient + an `exec-report-table` + a closing banner, all WCAG-contrast-safe per the Prime Directive) and reminds the user to tick **only the Multi-Turn checkbox** — NOT ACPX, because `chat_agent_windower` / `chat_agent_playwrighter` are standard wrapped Multi-Turn tools, not behind the ACPX/Skill surface (unlike the 0090 Reviewer/Analyzer *skill* demos). The four prompts **append** at slots 51-54 with no renumber, preserving the catalog's gap-free `prompt-1..54` contiguity contract (the dropdown breaks at the first missing slot); forward+reverse migration round-trips were verified clean. Second, two comprehensive automated test suites land: `agent/test_windower_agent.py` (**54 tests**) and `agent/test_playwrighter_agent.py` (**54 tests**), both following the established `test_de_compresser.py` pattern — the pool-agent module is loaded via `importlib.util.spec_from_file_location` with a cwd save/restore, and the Win32 API / a real browser are NEVER touched (Windower's `enum_windows` + `win32gui` are mocked; Playwrighter runs against a fake `playwright.sync_api` injected into `sys.modules`). They cover title-matching modes, arrange/tile geometry, the `AttachThreadInput` focus dance, every Windower action verb and every Playwrighter step verb, the `main()` end-stage contract (downstream always triggered + exactly one INI_SECTION block), and full registry/contract/migration integration. Verified: ruff clean, ESLint 0 errors, all 108 new tests green (162 with the related suites), no migration drift. Agent/skill counts unchanged (**66** / **23**) — this is demonstration + test hardening, not new capability.

- **Added Windower Agent — The Win32 Window Manager — 2026-05-21** — The agent catalog grows to **66** with **Windower**, the third member of the desktop-UI trio: where **Mouser** clicks inside a window and **Keyboarder** types into one, **Windower** manages the *window itself*. On trigger it locates an application window by title — `match_mode` ∈ `substring` (default) / `exact` / `regex`, with `match_index` to pick among same-titled windows — and runs exactly ONE window-lifecycle operation: `focus` (raise / bring to front), `minimize`, `maximize`, `restore`, `move`, `resize`, `move_resize`, `close` (by title), `topmost` / `untopmost` (always-on-top), or `arrange` (snap / tile to a screen region: left / right / top / bottom halves, the four quadrants, center, or full). It can also `list` every open window with its position, size, and state. It is **deterministic** (no LLM), implemented **self-contained on the Win32 API** (pywin32 — `win32gui` / `win32con` / `win32process` — plus `ctypes`), porting the window-management subset of Microsoft's **Windows-MCP** (`https://github.com/CursorTouch/Windows-MCP`) — including the reliable cross-process focus-transfer **`AttachThreadInput`** dance that lets a background process raise a foreground window without the OS rejecting the request. It emits one atomic `INI_SECTION_WINDOWER<<<` block (header `action`, `window_title`, `matched`, `match_count`, `state`, `left`, `top`, `width`, `height`; body = a result description or the formatted window list), so Parametrizer can chain its output (e.g. read `state` / geometry) into a downstream agent, and it ALWAYS triggers `target_agents` (success OR failure) so a Forker can branch on `{matched}` / `{state}`. Two surfaces ship in lock-step, the same dual pattern as Playwrighter and Unrealer: the visual **Windower** canvas node (`config.yaml` fields `action`, `window_title`, `match_mode`, `match_index`, `pos_x`, `pos_y`, `width`, `height`, `arrange_mode`, `activate_after`, `fail_if_absent`, `target_agents`) and the wrapped Multi-Turn tool **`chat_agent_windower`** (the LLM passes the operation as a free-form key=value request). It is **state-changing** (it moves, resizes, focuses, and closes real windows), so its row appears in the Exec Report. Wiring follows the established 8-step agent pattern: migrations `0093` (Agent row) + `0094` (Tool row); `views.update_windower_connection_view` + the `POST /update_windower_connection/<agent_name>/` route; Parametrizer source fields registered in `agent/services/agent_contracts.py` and `parametrizer.py`; the desktop-UI canvas gradient; the four ACP JS files plus the `eslint.config.mjs` cross-file global. As an Action agent it starts downstream agents. Wrapped chat-agent tools move to **41** and total Multi-Turn tools to **73** (20 core + 41 wrapped + 12 ACPX/Skill). The reference companions live in README §9.5, `agents_descriptions.md`, `docs/claude/agents.md`, and `agent/agents/flowcreator/agentic_skill.md`.

- **Added Playwrighter Agent — Scripted Interactive Browser Automation — 2026-05-20** — The agent catalog grows to **65** with **Playwrighter**, the first agent that drives a *real* browser through a scripted, interactive flow. Where **Crawler** does a one-shot static `urllib` fetch and **Googler** only runs a web search, Playwrighter (built on **Playwright** — Chromium / Firefox / WebKit) walks an ordered list of declarative steps — `goto`, `click`, `dblclick`, `fill`, `type`, `press`, `select`, `check`/`uncheck`, `wait_for`, `wait`, `extract_text`, `extract_attr`, `screenshot`, `assert_visible`, `assert_text`, `download` — so it can log into a site, submit a multi-step form, click through a wizard, scrape a JavaScript-rendered single-page-app behind a login, run an end-to-end UI check, or capture a screenshot of a specific post-interaction state. It is **deterministic** (no LLM), supports a `headless` toggle (set `false` to watch it drive) and `storage_state_in`/`storage_state_out` for carrying a logged-in session across runs, emits one atomic `INI_SECTION_PLAYWRIGHTER<<<` block (`start_url`, `final_url`, `status`, `steps_run`, `assert_result`, plus a `response_body` of extracted values + step trace), and ALWAYS triggers `target_agents` (success OR failure) so a downstream Forker can branch on `{status}` / `{assert_result}` and Parametrizer can pipe scraped data onward. Two surfaces ship in lock-step, the same dual pattern as Unrealer: the wrapped Multi-Turn tool **`chat_agent_playwrighter`** (the LLM passes the whole script as a single JSON string in `steps_json`, because the flat key=value request grammar cannot express a list-of-dicts; the agent `json.loads` it and it wins over the YAML `steps`) and the visual **Playwrighter** canvas node (the YAML `steps` list is the canvas authoring form). Wiring follows the established 8-step agent pattern: migrations `0091_add_playwrighter` (Agent row) + `0092_add_chat_agent_playwrighter_tool` (Tool row); `views.update_playwrighter_connection_view` + URL route; Parametrizer source fields registered in `agent/services/agent_contracts.py` (`_PARAMETRIZER_OUTPUT_FIELDS`, auto-discovered contract) and `parametrizer.py` (`SECTION_AGENT_TYPES`); `_EXEC_REPORT_TOOLS` under `agent_key="playwrighter"` (state-changing — it submits forms, logs in, downloads files); planner capability hints tuned so it out-scores Googler/Crawler only on interactive/authenticated/multi-step prompts; the "Theatre Spotlight" canvas gradient (curtain-violet → spotlight-magenta → peacock-teal → aqua-mint, a nod to Playwright's two-theatre-masks logo, distinct from every other 4-color gradient); the four ACP JS files plus the `eslint.config.mjs` cross-file global. Self-contained pool subprocess: it calls `playwright.sync_api` directly (no `ThreadPoolExecutor` — that is only needed by the in-process `googler` tool, which runs inside Django Channels' asyncio loop). Tool counts move to **72** Multi-Turn tools (20 core + **40** wrapped chat-agent + 12 ACPX/Skill). Verified end-to-end: ruff clean, ESLint 0 errors, both migrations applied, 19 targeted tests (Exec-Report capture + flow contracts) green, and `get_mcp_tools()` binds `chat_agent_playwrighter` for a total of 72. The reference companions live in README §9.5, `agents_descriptions.md`, `docs/claude/agents.md`, and `agent/agents/flowcreator/agentic_skill.md` entry #64.

- **Reviewer Commit-State & Secret-Handling Precision — v1.4.2, 2026-05-20** — A focused patch (commit `2e1c2d0`, tag `v1.4.2`) that fixes the Reviewer agent's most common false positive: reporting the developer's *local* working-copy credentials as "API keys committed to source". `agent/agents/reviewer/reviewer.py::build_review_prompt` now takes the `diff_ref` and prepends two grounding blocks to the LLM prompt. The first is a **COMMIT-STATE** block: when `diff_ref` is empty the diff is the UNCOMMITTED working tree + staged area (`git diff HEAD` + `git diff --staged`), so the model is told it MUST NOT call anything in it "committed" or "pushed" — at most "staged" or "in the working tree"; only a non-empty `diff_ref` that names committed history may be described as "committed". The second is a **SECRET-HANDLING CONVENTION** block teaching the model Tlamatini's own scrub convention: `agent/config.json` and `agent/agents/*/config.yaml` legitimately hold local credentials in the "keyed" working copy and are scrubbed back to `<NAME goes here>` placeholders by `regen_secrets.py --mode push-able` before any commit (the real values live only in gitignored `data.keys`), so the committed/pushed copies contain only placeholders — therefore a placeholder or empty string is never a secret, and real-looking credentials in those managed files inside an uncommitted diff are the expected local state (at most one low-severity reminder to scrub before committing), while genuine secrets hard-coded into source code or in any file outside that managed set are still hard-flagged. The same two rules are mirrored into the chat-surface twin `agent/skills_pkg/code_review/SKILL.md` (a new "Secret findings — read before flagging credentials" section plus commit-state wording in the diff-resolution and Security steps), so the `code-review` skill and the canvas Reviewer agent stay in lock-step. Bundled alongside: migration `0090_add_reviewer_analyzer_demo_prompts.py` seeds two demo prompts (idPrompt 26 code-review, 27 security-audit) ahead of the Multi-Turn samples. No agent/skill count change (still **64** / **23**) — this is a behavioural-accuracy patch, not a new capability.

- **Reviewer & Analyzer — Code Review and Security Audit on Both Surfaces — v1.4.2, 2026-05-20** — The agent catalog grows to **64** and the skill catalog to **23**, delivering the roadmap's long-standing Reviewer (#2) and Analyzer (#3) recommendations in one release (commit `efb8c13`, tag `v1.4.2`). **Reviewer** (`agent/agents/reviewer/`) is an LLM-powered code reviewer: on trigger it resolves a `git diff` for the configured `repo_path` — a ref like `HEAD~1` or `origin/main`, or the uncommitted working-tree + staged changes when `diff_ref` is empty — sends the diff to an Ollama model with a rigorous senior-engineer prompt, and emits an `INI_SECTION_REVIEWER<<<` block whose first field is a `verdict` (`APPROVE` / `REQUEST_CHANGES` / `COMMENT`) followed by line-anchored findings. **Analyzer** (`agent/agents/analyzer/`) is its deterministic counterpart — no LLM, reproducible output — running whichever of `bandit`, `semgrep`, `ruff`, `eslint`, `gitleaks`, and `pip-audit` are installed on PATH over `target_path`, aggregating their findings into an `INI_SECTION_ANALYZER<<<` block whose `status` is `clean` / `findings` / `error` and whose `total_findings` count is a routable header field; scanners that aren't installed are reported as skipped rather than failing the run. Both agents ALWAYS trigger `target_agents`, so a downstream Forker can branch the flow on `{verdict}` or `{status}` — auto-merge on APPROVE, block a deploy on findings, email a report otherwise. They are deliberately **canvas-only** (no wrapped `chat_agent_*` tool, hence not in `_EXEC_REPORT_TOOLS`): their LLM/chat surface is covered instead by two new `SKILL.md` packages — `code-review` (senior-engineer git-diff review with a verdict) and `security-audit` (multi-scanner SAST/secret/dependency sweep) — so the same capability is reachable both from a `.flw` canvas and from `invoke_skill` in a Multi-Turn chat, without a redundant third surface. Wiring follows the established 8-step agent pattern: migrations `0088_add_reviewer` / `0089_add_analyzer`; per-agent connection views + routes; Parametrizer source fields registered in `agent/services/agent_contracts.py` (`_PARAMETRIZER_OUTPUT_FIELDS`) and `parametrizer.py` (`SECTION_AGENT_TYPES`); two new canvas gradients (Reviewer = teal→indigo→violet, Analyzer = a dark-red→amber→yellow severity heatmap); and the four ACP JS files plus the `eslint.config.mjs` cross-file globals (the real source of truth for connector functions — not the per-file `/* global */` comments). Skills auto-discover from disk, so they need no migration. Verified end-to-end in both source and frozen modes: `build.py` copies the whole `agent/agents` and `agent/skills_pkg` trees wholesale, runs `migrate` + `collectstatic`, and ships `agents_descriptions.md`, so the new agents, DB rows, skills, and static assets all land exactly where the frozen path resolvers (`get_agents_root`, `skill_registry._default_roots`, `views._find_path`) look — there is no enumerated allow-list anywhere that could silently drop a new agent type. The reference companion lives in README §9.5, `docs/claude/agents.md`, and `agent/agents/flowcreator/agentic_skill.md` entries #62/#63.

- **Prime Directive on Visual Readability + Sorted Prompt Catalog — v1.3.2, 2026-05-19** — Two changes ship together in `v1.3.2` (commit `141d104`). First, `agent/prompt.pmt` gains a **Prime Directive** banner at the top of the rules block that outranks every other styling concern in the file: text must be readable on its background, every styled HTML element the LLM emits MUST carry BOTH an explicit `background` AND an explicit `color:` on the SAME element AND on every text-bearing child, body text is `#0f172a` on any light background and `#ffffff` on any dark background, the medium-grey list (`#94a3b8` / `#9ca3af` / `#a0a0a0` / `#c0c0c0` / etc.) is HARD-BANNED for body text on a coloured background, and every `<tbody> <td>` MUST be `background:#ffffff;color:#0f172a;…` (even rows) or `background:#f1f5f9;color:#0f172a;…` (odd rows) — header rows can be dark + white but body cells cannot. The Prime Directive is paired with a full styling contract in the renumbered Rule 14 (palette pairings ≥ 7:1 / WCAG AAA, banner & table templates, banned-grey hex list, the `'background:transparent'` → grey-on-dark failure pattern, the mandatory silent self-check before `END-RESPONSE`); the old Rule 14 (conflict resolution) becomes Rule 15. The Directive was forced into existence by three consecutive user-reported failures (`image.png`, `image copy.png`, `image copy 2.png`) where the LLM emitted light-on-light banners and dark `<tbody>` rows with grey body text — all three exact failure patterns are now hard-banned by name. Second, the seeded `Prompts` dropdown catalog is sorted along the learner's path documented in BookOfTlamatini.md chapters 9-14 — Tier 1 context-only Q&A → Tier 2 system metrics → Tier 3 files-search → Tier 4 single shell command → Tier 5 code generation → Tier 6 vision → Tier 7 specialized single-tool actions → Tier 8 agent control → Tier 9 Unrealer → Tier 10-12 Multi-Turn / ACPX flavours of increasing setup cost — so a first-time user picks prompts top-down without bouncing across difficulty levels. The change touches migrations `0002_populate_db.py` (ranges 1-20 and 26-28), `0062_sync_agent_control_tools_and_prompts.py` (21-24), `0063_add_agent_parametrizer_prompt.py`, `0067_add_multi_turn_demo_prompts.py`, `0072_add_acpx_demo_prompts.py`, `0073_acpx_demo_gemini_uplift.py`, `0074_simplify_demo_prompts.py`, and `0087_add_unrealer_demo_prompt.py` — the canonical home of each idPrompt range is documented in the `populate_initial_values` docstring so a future migration knows which range it owns. Net effect: every chat answer the LLM produces is forced through a contrast-checked HTML emission path AND the Prompts dropdown reads as a guided curriculum instead of a chronological log of demos. Coverage: existing `agent/tests.py` rule-numbering and answer-rendering tests still green.

- **Tool-Choice Rule: Executer / Pythonxer / File-Creator Preferred Over Keyboarder / Mouser — v1.3.1, 2026-05-18** — A bundle of three coordinated changes (commits `9392af4` + `fae830c`) that fix the failure mode where the LLM was driving Keyboarder to type Python source into Notepad and Mouser to click through an IDE's File → Save menu instead of just writing the file. `agent/prompt.pmt` gains a **Code-authorship tool-choice rule** at the top of Rule 8 plus a **Keyboarder / Mouser explicit-instruction rule** that codifies: to AUTHOR or WRITE code, scripts, configs, or any text-based artefact, ALWAYS prefer (in this order) `chat_agent_file_creator` (atomic, one-call), `chat_agent_pythonxer` (inline Python for computed content), and `chat_agent_executer` (shell/build CLIs); NEVER drive `chat_agent_keyboarder` or `chat_agent_mouser` to type source code or click through editors. Keyboarder/Mouser are reserved for genuine desktop-UI automation explicitly named by the user (Notepad demo, GUI replay, hotkey injection into a third-party app, anti-idle motion) or when there is no programmatic alternative. The same guidance is mirrored into `chat_agent_registry.py` (Executer / Pythonxer / File-Creator gain "PREFERRED over chat_agent_keyboarder for ..." in their `purpose` strings; Keyboarder / Mouser gain "DO NOT use this tool as part of a code-authoring or script-creation flow ..."), `agent/tools.py` (`execute_file` and `execute_command` direct `@tool` docstrings get the same paragraph), and `agents_descriptions.md` (the sidebar tooltips for Executer / Pythonxer / File-Creator / Keyboarder / Mouser carry the new guidance verbatim so the canvas hover text matches the chat behaviour). Net effect: a request like "write a Python script that prints hello" reliably produces `chat_agent_file_creator(filepath='C:\Temp\hello.py' and content='print(\"hello\")')` (optionally followed by `chat_agent_executer(script='python C:\Temp\hello.py')`) instead of the previous "launch Notepad → type each character through pyautogui → click Save → click OK in the Save dialog" parade.

- **Ruff Availability Across Multi-Turn Execution — v1.3.1, 2026-05-18** — `Tlamatini/agent/agents/pythonxer/pythonxer.py` and `Tlamatini/agent/tools.py` were hardened so the Ruff lint step inside Pythonxer runs even when the tool is invoked from a Multi-Turn wrapped runtime where the user's `venv\Scripts\ruff.exe` is not on PATH (commit `2c707e3`). The agent now resolves Ruff via a four-tier lookup (`sys.executable` → `python -m ruff` → bundled lint binary → bare `ruff` from PATH) and treats "ruff not found" as a non-fatal warning instead of a script failure, so a Pythonxer call in a flow that the user copy-pasted from `.flw` into a frozen install no longer dies on a missing lint binary.

- **ACPX-Skills Admin Menu — Browse / Configure / Diagnostics / Reload — 2026-05-17** — The chat navbar gained a fourth dropdown — **ACPX-Skills** — sitting between **Agents** and **Config**, and with it Tlamatini finally has an operator-grade surface for the 21 SKILL.md packages it ships. Until now the only way to see what skills existed, decide which ones the LLM should actually be allowed to call, or reload the catalog after editing a SKILL.md on disk was to ask the LLM itself — `list_skills`, then `invoke_skill`, both gated behind the ACPX toolbar checkbox and behind whatever the planner felt like surfacing on that particular turn. That worked, but it required the LLM to be the eyes and hands for a piece of catalog hygiene that belongs to the person sitting at the keyboard. So the dropdown was built to mirror the existing Mcps / Tools / Agents pattern as closely as possible: one entry for browsing (the **Browse Skills** modal — a left-pane list of every skill with a green-dot / red-dot enabled indicator and a search box, and a right-pane detail view that pulls the full SKILL.md body, frontmatter, requires, inputs/outputs, permissions, and budgets fresh from the registry on every click), one entry for toggling (the **Configure Skills** modal — the same checkbox-grid idiom the Mcps and Agents dialogs already use, sending its result over the same WebSocket channel as `set-mcps` / `set-agents` / `set-tools` with the payload encoded as `name=description=true/false,...`, decoded by a new `set-skills` branch in `consumers.AgentConsumer.receive` and written to `Skill.enabled` via `save_skill(name, enabled)`), one entry for cross-checking (the **Diagnostics** modal — a four-section report that flags every skill whose `requires_tools` references a Tool you've disabled, every skill whose `requires_mcps` references an MCP you've disabled, every `runtime: acpx` skill whose `acpx_agent` isn't in the `AcpAgent` registry, and every orphan `Skill` row whose SKILL.md was deleted from disk without a Reload), and one entry for the dev loop (the **Reload Registry** button — a single POST to `/agent/skills/_/reload/` that re-runs `agent/acpx/service.py::boot_skills()` so an edited SKILL.md shows up immediately, no server restart). The Configure-dialog toggle has real teeth: when `Skill.enabled = False`, the tool-surface gating in `agent/acpx/tools.py::_disabled_skill_names()` (called from both `list_skills` and `invoke_skill`) filters the row out of enumeration and rejects invocation with a `{"ok": false, "code": "SKILL_DISABLED"}` envelope — and it fails OPEN on any DB exception so a broken admin layer can never silently hide skills from the LLM, which is the opposite of the failure mode that would worry me. The single biggest design decision was deliberate restraint on the database: the `Skill` model already existed from migration `0071_acpx_skills.py` and had a richer schema than the `Tool` / `Mcp` / `Agent` toggle rows (cached `frontmatter_json`, `body_sha256`, `last_loaded_at`, `runtime`, `acpx_agent`), but the admin UI *only* ever writes the `enabled` boolean — the cached fields are owned by `boot_skills()` and refreshed from the on-disk SKILL.md on every reload, so the disk stays the only source of truth for permissions, budgets, and body. The user's stated rule is "DB only for enumeration and enable/disable like MCPs/Agents", and the implementation honors it: if you want to change a skill's network policy or its iteration cap, you edit the SKILL.md and click Reload, not a database row that the next backup would silently archive. Skills key on `Skill.name` directly (the SKILL.md frontmatter `name`, already unique) — there is no `skill-N` ID-prefix shim like the `mcp-N` / `tool-N` / `agent-N` pattern uses, because there was no reason to introduce one. Files touched: `agent/views.py` (`list_skills_view`, `skill_detail_view`, `reload_skills_view`, `skills_diagnostics_view`), `agent/urls.py` (4 routes under `/agent/skills/`), `agent/consumers.py` (`skill_establishment`, `get_all_skills`, `save_skill`, `set-skills` handler, establishment loops in both the session-restore path and the rebuild path), `agent/acpx/tools.py` (`_disabled_skill_names` helper + gating in `list_skills` and `invoke_skill`), `agent/templates/agent/agent_page.html` (navbar dropdown + 3 dialog containers + asset includes for `skills_dialog.js` and `skills_dialog.css`), `agent/static/agent/js/skills_dialog.js` (the four jQuery-UI dialogs — full implementation in ~360 lines, mirrors the existing tools_dialog.js pattern), `agent/static/agent/js/agent_page_init.js` (`OpenSkillsConfigureDialog`, `OpenSkillsBrowseDialog`, `OpenSkillsDiagnosticsDialog`, `ReloadSkillRegistry` entry points), `agent/static/agent/js/agent_page_chat.js` (`type: 'skill'` system-message handler that hydrates the module-level `skills = []` cache), `agent/static/agent/js/agent_page_state.js` (the `let skills = []` declaration alongside `tools` and `agents`), `agent/static/agent/css/skills_dialog.css` (styling), `eslint.config.mjs` (11 new globals — `skills`, `computeCheckboxGridLayout`, and the `OpenSkills*Dialog` / `preRender` / `render` / `open` / `reload` family — so the new JS lints clean with zero errors), and a full update pass across the documentation surface (`README.md` §3.11, `CLAUDE.md` Skills bullet, `docs/claude/{architecture,acpx,frontend,gotchas,INDEX,mcp-tools}.md`, and this Book entry). Coverage: 14 new tests in three classes — `SkillsAdminEndpointTests` (7 — list / detail / 404 / reload / get-rejection / diagnostics shape), `SkillsToolSurfaceGatingTests` (3 — list filters disabled, invoke rejects with SKILL_DISABLED, invoke unknown returns UNKNOWN_SKILL), `SkillsNavbarTemplateContractTests` (4 — pins the dropdown HTML so a careless template edit doesn't silently drop the menu). All 14 pass; the full agent-tests run shows the same 5 pre-existing failures it had before (multi-turn / parametrizer / acpx-config / prompt-validation) and zero new regressions. The narrative companion lives in Book §17.5; the reference companion lives in README §3.11 and `docs/claude/acpx.md`.

- **Unreal MCP Integration — Driving Unreal Engine 5 from Tlamatini — 2026-05-16** — Tlamatini grew a 62nd agent — **Unrealer** — and with it a brand-new MCP surface: the canonical open-source **Unreal MCP** plugin (`https://github.com/chongdashu/unreal-mcp`, MIT, UE5.5+) that runs inside an Unreal Engine 5 editor instance and accepts one JSON command per TCP connection on `127.0.0.1:55557`. Tlamatini is the *client* — `agent/agents/unrealer/unrealer.py` is a self-contained pool subprocess (no `agent.*` imports, mirrors the upstream `UnrealConnection` adapter inline in ~80 lines) that opens a fresh TCP socket per turn, sends `{"type": <command>, "params": {...}}`, captures the engine's JSON response, normalizes Unity-style `{"success": false}` into the registry's `{"status": "error"}` shape, and emits the whole exchange as one atomic `INI_SECTION_UNREALER<<<` block so Parametrizer can wire it into downstream agents. Two surfaces ship in lock-step: the wrapped Multi-Turn tool **`chat_agent_unrealer`** (`chat_agent_registry.py::ChatWrappedAgentSpec(key="unrealer", …)`, with the full 28-command surface documented in the tool `purpose` string so the LLM understands its taxonomy without extra prompting) and the visual **Unrealer** canvas node (one node = one command, chainable through Parametrizer into multi-step flows like *create_blueprint → compile_blueprint → spawn_blueprint_actor*). Three migrations land together: `0085_add_unrealer` (the Agent row), `0086_add_chat_agent_unrealer_tool` (the Tool row), and `0087_add_unrealer_demo_prompt` (a seeded end-to-end demo prompt at `idPrompt=32` that exercises every command category — editor sanity probe, actor spawn, Blueprint scaffold-compile-instance, UMG widget build, and a per-step HTML report table — in one guided Multi-Turn run). Exec Report integration: `chat_agent_unrealer` is registered in `_EXEC_REPORT_TOOLS` under `agent_key="unrealer"` so every call shows up as one row in a dedicated **List of Unrealer Operations** table at the bottom of the answer. Parametrizer source fields registered in `agent/services/agent_contracts.py`: `host`, `port`, `command`, `status`, `error`, `response_body`. Full coverage: README §6 (the new reference chapter) and Book bonus §57 (the narrative companion). Supports the full 28-command Unreal MCP surface across five categories (8 editor verbs, 7 blueprint verbs, 7 node-graph verbs, 1 project verb, 6 UMG verbs) — and because the wrapped tool forwards `command` + `params` verbatim, any fork that adds a new verb (`https://github.com/CrispyW0nton/Unreal-MCP-Ghost`, `https://github.com/gingerol/vhcilab-unreal-engine-mcp`, or your own) works with no client-side changes.

- **The Orphan Reaper — Quietly Closing the `conhost.exe` Loose End — 2026-05-16** — For most of Tlamatini's life, anyone who ran a long Multi-Turn session on Windows could end up staring at the Task Manager and counting little ghosts. Each ghost wore Tlamatini's icon — a yellow-and-black mask of *one who knows* — and each ghost was, in plain process-table terms, a `conhost.exe`: the console-host companion Windows insists on attaching to every command-line child. When the console child finished and its parent died before the operating system reaped the pair, the conhost lingered. The icon was inherited from whichever EXE had originally spawned the console; the EXE in our case was Tlamatini.exe; the inheritance was loyal; the user's reasonable conclusion was that Tlamatini was leaking processes — or, more darkly, that something had taken up residence and refused to leave. Neither was true, but the truth did not help the appearances. This release closes the gap on both sides at once. A new module — `Tlamatini/agent/orphan_reaper.py` — installs a three-tier broom that sweeps after every Multi-Turn tool call that may have spawned a child (Tier 1, silent and cheap, after each `execute_command`, `chat_agent_*`, `acp_*`, and a short list of allies), again after each final answer is delivered to the chat (Tier 2, with the wider agent-pool scan, running in a thread so the user never feels the pause), and one last time as Tlamatini.exe itself bows out (Tier 3, registered on the same `atexit` / SIGINT / SIGBREAK path that already tidied up the pools directory). Each tier escalates `terminate → wait → kill` on every candidate it finds, and each tier promises — in code and in spirit — to never raise an exception back into the chat path: a cleanup that crashes a conversation is worse than the orphans it tries to evict. When the reaper truly cannot kill something, the user does not have to discover the survivor on their own. A second chat bubble appears beneath the answer, in the same voice the rest of the application uses, listing each surviving `name` and `PID` so the user can finish the job from Task Manager themselves — informed, never blamed. And on the prevention side, the spawn sites were rewritten. `views.py`'s Starter, Ender, FlowCreator, and Restart paths now launch their Python children with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW | DETACHED_PROCESS` and stdio piped to `DEVNULL`; the ACPX runtime grew a `_kill_process_tree()` helper that walks past the top-level CLI wrapper and ends the `node.exe` helpers underneath it; and every pool-agent script (Ender first, the other fifty-odd siblings in lockstep) installs a top-of-module `subprocess.Popen.__init__` monkey-patch that quietly adds `CREATE_NO_WINDOW` to any descendant `Popen` whose caller forgot to ask for it. The seatbelt is now fastened by default. As a result, the orphan survivor list — the second chat bubble Tlamatini's reaper is prepared to send — should almost always be empty, which is exactly the point: most users will never know any of this happened, and that is the loudest a piece of plumbing should ever be allowed to speak. Documented in Book §17 of intent and the new README §10 of record; commit `dcd1613` carries the full diff.

- **Added De-Compresser Agent — 2026-05-15** — A new short-running deterministic action agent that COMPRESSES or DECOMPRESSES an archive (61st agent in the catalog). Direction is inferred from the file extensions: if `input` ends in `.gz`, `.7z`, `.zip`, `.tar.gz`, or `.gz.tar` the agent extracts into the `output` directory; if `output` ends in those extensions the agent packs `input` (a file OR a directory) into `output`. Per-format engines: `.gz` uses the stdlib `gzip` module; `.zip` uses the stdlib `zipfile` module; `.7z` uses the `7z` CLI when available (LZMA / LZMA2 + `-mhe=on` AES-encrypted headers) and falls back to `py7zr`; `.tar.gz` / `.gz.tar` decompresses through a temp `.tar` then untars (and routes through `7z` when a password is supplied since stdlib tar/gz has no native encryption). Password handling: pass `passwordless=true` to skip, or `passwordless=false` and the agent reads the password from the OS env var `DE_COMPRESSER_PWD` (a missing env var fails fast to the end-stage). The end-stage ALWAYS starts every agent in `target_agents`, even on failure, so a Raiser on a downstream Parametrizer can branch on the `success=true|false` field of the emitted `INI_SECTION_DE_COMPRESSER<<<` block. Files involved: `agent/agents/de_compresser/{de_compresser.py, config.yaml}` (the agent itself), `agent/views.py::update_de_compresser_connection_view` + `agent/urls.py` (canvas wiring), `agent/migrations/0083_add_de_compresser.py` (Agent row) + `0084_add_chat_agent_de_compresser_tool.py` (Tool row for the Multi-Turn wrapper), `agent/chat_agent_registry.py` (`ChatWrappedAgentSpec(key="de_compresser", ...)`), `agent/mcp_agent.py::_EXEC_REPORT_TOOLS` (registered under `agent_key="decompresser"`), `agent/static/agent/css/agentic_control_panel.css` (Vault-Unsealed gradient — slate-indigo → archival-bronze → sealing-wax-red → spring-mint, intentionally distinct from every other 4-color gradient in the file), `agent/static/agent/css/agent_page.css` (Exec Report caption + cmd-border accent + dark-header membership), `agent/static/agent/js/{acp-agent-connectors.js, acp-canvas-core.js, acp-canvas-undo.js, acp-file-io.js, agent_page_chat.js}` (full canvas wiring + Flow-Generator mapping for `chat_agent_de_compresser`), `agents_descriptions.md` (sidebar tooltip + canvas Description dialog), `agent/agents/flowcreator/agentic_skill.md` (FlowCreator AI catalog entry #54b), `agent/agents/flowhypervisor/monitoring-prompt.pmt` (watchdog knows the new startup banner and the Parametrizer-section it emits), `README.md` + `docs/claude/agents.md`. The agent is fully accessible through Multi-Turn via `chat_agent_de_compresser` (security_hints cover "compress", "decompress", "unzip", "extract archive", "zip up", "pack folder", "tar gz", "7z").

- **DB menu — Backup database + Set DB + start-up swap-in — 2026-05-14** — A new top-of-page **DB** dropdown adds two safe, GUI-first database operations and a third invisible one. **Backup database** (`DB → Backup database`, commit `47df564`) opens a dialog with a live-validated target-directory input (`GET /agent/check_backup_directory/`) that `shutil.copy2`s the live `db.sqlite3` to a directory of your choice via `POST /agent/backup_db/`, keeping the live database untouched. **Set DB** (`DB → Set DB`, the new entry) does the harder direction: a live-validated file-path input (`GET /agent/check_set_db_file/` — checks existence, basename, and the `SQLite format 3\x00` magic header) stages your pick into `<base>/DB/ToLoad/db.sqlite3` via `POST /agent/set_db/`, and a yellow ⚠ warning dialog tells you the file will be loaded on the next session (or restart now for immediate effect). The invisible third leg is `Tlamatini/manage.py::_apply_pending_db_swap` — a function that runs BEFORE Django is imported, detects frozen vs source mode, and (only when `DB/ToLoad/db.sqlite3` is present) (1) creates `DB/Older/<YYYY-MM-DD_HHMMSS>/`, (2) `shutil.move`s the current live `db.sqlite3` into that timestamped archive, (3) `shutil.move`s `DB/ToLoad/db.sqlite3` on top of the live path, then returns and lets Django open the freshly-promoted database. Both legs use `shutil.move` (not copy), so a re-launch with empty `ToLoad/` is automatically a no-op — no "stuck flag" to clear. Pre-Django timing is the entire safety story: a simple **Reconnect** from the navbar does NOT trigger the swap-in, because the swap window is only open before the Django process opens its SQLite connection pool. The deployment-aware path resolution mirrors Django's own `BASE_DIR / 'db.sqlite3'` — `_MEIPASS/db.sqlite3` under PyInstaller (the bundle-internal location Django actually opens), `<manage.py dir>/db.sqlite3` in source mode — while the user-facing `DB/` tree always lives next to the executable (frozen) or next to `manage.py` (source), where the user can actually browse to it in Explorer. `build.py` extends its `empty_dirs` tuple with `"DB/ToLoad"` and `"DB/Older"` so frozen installs ship with both directories on day one; `Tlamatini/Tlamatini/DB/{ToLoad,Older}/README.md` are checked into the repo as the "git keepers" that prevent the empty directories from being lost in source mode. The Older archive is never auto-pruned — it's the only built-in rollback path (copy a `db.sqlite3` from `Older/<timestamp>/` back into `ToLoad/`, restart, and the swap-in promotes it while archiving the *current* live database under a fresh timestamp). Failure-mode contract: a corrupt / locked / mismatched ToLoad file logs `--- [DB SWAP] Skipped due to error: …` to `tlamatini.log` and lets Tlamatini start normally with the previous database — a bad ToLoad pick must never lock you out of your own data. Files involved: `Tlamatini/manage.py` (swap-in), `Tlamatini/agent/views.py::{_resolve_db_sqlite_path, check_backup_directory_view, backup_db_view, _resolve_db_to_load_directory, _file_looks_like_sqlite, check_set_db_file_view, set_db_view}`, `Tlamatini/agent/urls.py` (four new routes), `Tlamatini/agent/templates/agent/agent_page.html` (DB dropdown + two dialog containers + warning panel), `Tlamatini/agent/static/agent/css/agent_page.css` (`backup-db-status`, `set-db-status`, `set-db-warning-icon` rules), `Tlamatini/agent/static/agent/js/agent_page_state.js` (DOM refs), `Tlamatini/agent/static/agent/js/agent_page_dialogs.js` (`makeBackupCancelButtons` / `makeSetCancelButtons` factories, three `preRender*` / `render*` pairs), `Tlamatini/agent/static/agent/js/agent_page_init.js` (`OpenBackupDbDialog`, `OpenSetDbDialog`, `_saveBackupDb`, `_saveSetDb`, debounced validators), `eslint.config.mjs` (15 new global declarations), and `build.py` (empty-dir extension). Documented end-to-end in Book chapter §17 and README §3.10.

- **Embedding-Memory Pre-Flight Guard — 2026-05-12** — A new module (`agent/embedding_memory_guard.py`) catches the "context loading hangs for hours" failure mode on GPU hosts before the embed burst starts. The guard is wired into `agent/consumers.py::setup_contextual_rag_chain` exactly once: after the consumer broadcasts `MSG_AGENT_LOADING_CONTEXT` and before it schedules the heavy `asyncio.to_thread(setup_llm_with_context, …)` call that drives `FAISS.from_documents(...)`. It runs **only** when an NVIDIA GPU is detected via the cached `gpu_perf._has_nvidia_gpu()` probe — CPU-only, AMD, and Apple Silicon hosts skip the check silently and the legacy load path is unchanged. Three-tier VRAM prediction: Tier A reads `size_vram` verbatim from `GET /api/ps` when the model is already resident (exact daemon ground truth); Tier B computes `parameter_count × bits_per_weight(quant) / 8 × overhead` from `POST /api/show`, with a standard llama.cpp / GGUF bits-per-weight table (`F16`=16, `Q8_0`=8.5, `Q4_K_M`=4.83, `Q2_K`=2.96 …) and a 2-tier overhead multiplier (×1.40 for ≥1B-param models, ×2.20 for sub-1B) calibrated against measurements on the dev box's RTX 4070 Laptop (`qwen3-embedding:8b` predicts 6.36 GB vs measured 6.24 GB, +1.9 %; `Nomic-Embed-Text:latest` predicts 603 MB vs measured 600 MB, +0.5 %); Tier C returns `None` for cloud models (`:cloud` suffix), missing Ollama, or any probe failure (fail-open). When predicted VRAM is at least **80 %** of the *smallest* GPU's total VRAM (smallest because Ollama loads each model into a single device by default), the consumer broadcasts an HTML chat-bubble warning naming the model, the percent, the threshold, and a projected FAISS index size — informational and non-blocking. Test coverage: **49 tests** in `agent/test_embedding_memory_guard.py`, organized into seven `SimpleTestCase` classes; the `NoGpuCompatibilityTests` class alone is **28 tests** covering every `nvidia-smi` / Ollama / path-input / driver-crash failure mode, with `test_real_entry_point_call_never_raises` as the CI gate that exercises the live subprocess + urllib paths and asserts the return is **either** `None` **or** a well-formed warning dict on any host. Book chapter §34 documents the full user-facing surface; README chapter 9 mirrors it as the reference companion.

- **Chat-page configuration dialogs + restore-flow reliability + canvas/stop polish — 2026-05-09 to 2026-05-11** — The `/agent/` navbar now includes **Config -> Models** and **Config -> URLs** (commit `ac747e3`). These dialogs load a validated subset of `config.json`, let the user edit the common model-name and endpoint fields from the browser, then save through `config_loader.save_config_updates()` so source-mode and frozen-mode builds write to the same effective config file. The views `load_config_section_view`, `save_config_models_view`, and `save_config_urls_view` enforce server-side validation for strings, URLs, hosts, and ports. Companion UI work enlarged and cleaned up the **Configure MCPs** dialog (`b286cd6`) and improved the chat/canvas vertical divider behavior on the main page (`1e62faa`). Another reliability fix (`484b8ec`) closes the old initial context-load race: when a saved session is restored, the frontend now keeps the input disabled until the contextual RAG chain is really ready, instead of briefly unlocking after the welcome-back banner. On the workflow side, dialog edits now win over stale pool wiring during compilation (`04502c3`), and the mixed-flow stop path is better at killing lingering processes before the next run (`6b0e3aa`).

- **Emailer / RecMailer quoting, placeholder cleanup, and TeleTlamatini copy polish — 2026-05-09** — A smaller but user-visible reliability pass landed across the messaging agents. Emailer and RecMailer quoting mechanics were corrected (`c1088bb`) so generated payloads survive nested quoting more predictably, placeholder handling was cleaned up (`2d27fa0`) so parametrized values are less likely to drift into malformed marker text, and TeleTlamatini's dynamic welcome / guidance strings were polished (`8c2e5a6`) so first-contact Telegram conversations read more naturally.

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
