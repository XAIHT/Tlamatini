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
  <i>"one who knows" — she doesn't just edit code. She flashes your board, drives your engine, and orchestrates whole agent workflows on a canvas. On your machine.</i>
</p>

<p align="center">
  <b>⚠️ Ollama Pro or higher is required for the complete Tlamatini experience.</b><br/>
  <b>Tlamatini is free and open-source</b>; an Ollama subscription is purchased directly from Ollama. We are <b>not sponsored by, affiliated with, or paid by Ollama</b>. Tlamatini was engineered around Ollama's cloud-model interface, capacity, and tool-calling characteristics, so <b>at least the Pro plan</b> is part of the intended system requirements—not a promotion.
</p>

<p align="center">
  <a href="https://discord.gg/WFQsrskgc"><img src="https://img.shields.io/badge/DISCORD-JOIN%20US-5865F2?style=for-the-badge&labelColor=2D2D2D&logo=discord&logoColor=white" alt="Join our Discord"/></a>
  <a href="https://github.com/XAIHT/Tlamatini/releases"><img src="https://img.shields.io/badge/RELEASE-v1.49.1-1E90FF?style=for-the-badge&labelColor=2D2D2D" alt="Release v1.49.1"/></a>
  <a href="https://www.python.org/downloads/release/python-31210/"><img src="https://img.shields.io/badge/PYTHON-3.12.10-3776AB?style=for-the-badge&labelColor=2D2D2D&logo=python&logoColor=white" alt="Python"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/PLATFORM-WIN%2010%20%7C%2011-0078D6?style=for-the-badge&labelColor=2D2D2D&logo=windows&logoColor=white" alt="Platform"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/AGENT%20TYPES-88-8A2BE2?style=for-the-badge&labelColor=2D2D2D" alt="88 agent types"/></a>
  <a href="#-the-full-capability-list"><img src="https://img.shields.io/badge/MULTI--TURN%20TOOLS-108-16A34A?style=for-the-badge&labelColor=2D2D2D" alt="108 built-in Multi-Turn tools"/></a>
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

## What is Tlamatini

Tlamatini is a **local-first AI development and automation environment** for Windows. It combines a conversational assistant, whole-project code operations, a visual workflow designer, **88 specialized agent types**, **108 built-in Multi-Turn tools**, hardware and firmware control, Unreal Engine and Blender automation, security tooling, and a universal External-MCP client in one application.

“Local-first” describes **where control lives**: the application, workflow canvas, database, configuration, credentials, agent code, project access, and small embedding model run under your control on your machine. It does **not** mean that Tlamatini was designed as a local-model-only assistant. Its complete reasoning and orchestration experience was designed and coded primarily around the larger **cloud models exposed through Ollama**.

## How it works

Tlamatini has three cooperating layers:

1. **Local control plane** — the Django application, chat interface, SQLite database, visual workflow designer, agent programs, permissions, files, tools, and hardware connections remain on your computer.
2. **Local retrieval** — `nomic-embed-text` builds embeddings locally so Tlamatini can retrieve relevant project context efficiently.
3. **Ollama cloud reasoning** — configured `:cloud` models perform the demanding chat, tool-calling, coding, long-context, vision, planning, and Multi-Turn reasoning that coordinates Tlamatini's agents. Ollama keeps the same local API experience while offloading these larger models to its cloud service.

> [!IMPORTANT]
> **To use Tlamatini with its complete intended functionality, an active Ollama Pro plan—or a higher Ollama plan such as Max—is mandatory.** A free Ollama account or local-only model may be enough to launch the application or experiment with limited requests, but it is **not the supported baseline for Tlamatini's full workloads**. Multi-Turn orchestration, long agent runs, parallel vision calls, repeated tool decisions, and large project contexts can consume cloud usage and concurrency rapidly. Tlamatini therefore treats **Pro as the minimum system tier**.

> [!NOTE]
> **This is an independent technical recommendation, not an advertisement.** XAIHT/Tlamatini is not sponsored, endorsed, funded, or compensated by Ollama, and receives no referral fee or commission. Your Ollama subscription is a separate purchase made directly from [Ollama](https://ollama.com). We specify Pro only because Tlamatini's architecture was built around Ollama cloud models and needs their practical capacity to operate as designed.

Ollama currently advertises Pro at **$20/month or $200/year**, with greater cloud usage and concurrency than the free account; Max also satisfies Tlamatini's requirement. Pricing and limits belong to Ollama and may change, so verify them on [Ollama's official site](https://ollama.com) before subscribing. Ollama's official cloud documentation explains that cloud models are offloaded to Ollama's service while remaining accessible through the familiar local Ollama API: [Ollama cloud-model documentation](https://docs.ollama.com/cloud).

## 🚀 Get Started — 5 steps to a cloud-powered Tlamatini

**Tlamatini itself is free**, but a complete installation assumes **Ollama Pro or higher** as an operating requirement. Subscribe directly with Ollama, sign in through the Ollama CLI, and Tlamatini can coordinate **88 agent types and 108 built-in Multi-Turn tools** from your machine using the cloud-model capacity around which it was designed. XAIHT receives no payment or benefit from that subscription.

### 1 · Install Tlamatini

Pick **one** of two paths. **Tlamatini itself is free** — you never pay us; the only cost is Ollama (Step 3).

#### 🟢 Option A — Release installer (recommended · no Python needed)

Best for most people. The installer bundles its own **Python 3.12.10** and every dependency, so you install nothing else.

1. Open the **[Releases page](https://github.com/XAIHT/Tlamatini/releases)** and download the latest installer (`.exe`).
2. Run it and follow the wizard.
3. Launch **Tlamatini** from the Start-menu shortcut.
4. Your browser opens at **`http://127.0.0.1:8000/`** — log in with **user / changeme**. *(`8000` is the default port; if it's taken or Windows has reserved it, set `django_port` in `config.json` — see the port note below.)*

> 🔄 Updating later is one click: **About ▸ Check for updates** inside the app — it keeps your config, database, keys, templates, external-MCP catalog, and existing `Uninstaller.exe`.

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

> **`--noreload` is optional (since 2026-07-11):** plain `python Tlamatini/manage.py runserver` now boots clean and auto-reloads on code edits. It used to double-start the MCP helper ports `:8765` / `:50051` and crash with `WinError 10048`; fixed by a reloader-aware gate in `agent/apps.py`.

<details>
<summary><b>🔌 Port 8000 already taken? Tlamatini won't start? (<code>WinError 10013</code>) — change one line</b></summary>

<br>

**`8000` is only the default.** Since **v1.40.1** the web port lives in your **`config.json`**:

```jsonc
"django_port": 8000     // ← put any free port here, e.g. 9000
```

Restart Tlamatini and she comes up on the new port — **no rebuild, no code edit**. Every launch path follows it: the desktop shortcut, double-clicking a `.flw` file, the browser that auto-opens, and `runserver` / `startserver` from source.

**Why you might need this.** If Windows (usually **Hyper-V / WSL / Docker**) has *reserved* port 8000, Tlamatini cannot bind it and dies at startup with:

> `WinError 10013` — *an attempt was made to access a socket in a way forbidden by its access permissions*

To confirm that's what happened, list the ports Windows has reserved:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

If `8000` falls inside one of those ranges, pick a port outside them (9000 is a common safe choice).

**Good to know**
- A port passed on the command line still wins: `python Tlamatini/manage.py runserver 9100`.
- It's **fail-safe** — if you typo the value, Tlamatini falls back to 8000 and still starts (she prints a `--- [PORT] …` line explaining why).
- Where's `config.json`? Next to `Tlamatini.exe` in an installed build; at `Tlamatini/agent/config.json` from source.
- If you also run the **TeleTlamatini** Telegram bridge, point its `tlamatini.base_url` at the same port.

</details>

### 2 · Install Ollama

Install **[Ollama](https://ollama.com/download)** for Windows. Ollama is the engine that serves every model to Tlamatini — the local embedding model **and** the cloud chat models.

### 3 · Activate Ollama Pro or higher — required for complete operation

Go to **[ollama.com](https://ollama.com)**, sign in, and activate **at least Ollama Pro**. Ollama currently lists Pro at **$20/month or $200/year** and describes it as providing substantially more cloud usage plus concurrent cloud-model capacity; **Ollama Max also satisfies this requirement**. Check Ollama's site for current pricing and limits.

Ollama may provide limited cloud access with a free account, but **Tlamatini does not treat the free allowance as a fully functional production configuration**. Its Multi-Turn loops can make many model calls during one task, and its vision and orchestration paths may use multiple cloud models in parallel. Pro is therefore the minimum intended capacity tier, not an optional donation or affiliate offer.

> **Independence disclosure:** Tlamatini/XAIHT is **not sponsored by, affiliated with, endorsed by, or compensated by Ollama**. There is no referral relationship. You pay Ollama directly; this README names Pro solely because Tlamatini was engineered around Ollama's cloud-model behavior and capacity.

After subscribing, connect the Ollama installation on your machine to your Ollama account:

```bash
ollama signin
```

### 4 · Download the models

Pull the small local embedding model, plus the cloud chat models Tlamatini will use:

```bash
# Local embedding model (small, runs on your own GPU/CPU)
ollama pull nomic-embed-text

# Cloud models — use a signed-in Pro-or-higher account for full Tlamatini operation
ollama pull glm-5.2:cloud
ollama pull qwen3.5:cloud
```

Any cloud model works — these two are the current recommended pair (older screenshots below may still show earlier model names).

### 5 · Point Tlamatini at the models

In the Tlamatini navbar, open the **Config** menu:

<p align="center"><img src="Tlamatini/agent/images/MenuConfig.jpg" alt="Config menu — Models, URLs, Access Keys Wizard" width="420"/></p>

**a) Config ▸ Models** — set the Ollama model for each subsystem (each one must already exist in your Ollama catalog), then click **Save**:

<p align="center"><img src="Tlamatini/agent/images/ConfigureModels.jpg" alt="Configure Models dialog" width="480"/></p>

**b) Config ▸ Access Keys Wizard** — whether you need an **Ollama token** depends on *where* Ollama runs:

> - 🖥️ **Ollama on your own machine (localhost)?** Leave the token **blank** — a local Ollama needs no auth.
> - ☁️ **Ollama on a remote server (e.g. [Vast.ai](https://vast.ai))?** Paste the **Ollama token** so Tlamatini can reach it.

Add any cloud-CLI keys here too — plus the messaging keys, the Kali server URL, and the **OPTIONAL** ProjectDiscovery Cloud (PDCP) key under **"Security Recon (ProjectDiscovery)"**. Blank fields keep what's already configured; click **Save**:

<p align="center"><img src="Tlamatini/agent/images/ACPXKeysConfigureWizard.jpg" alt="Access Keys Wizard" width="640"/></p>

Done — tick **Multi-Turn** in the chat toolbar and put Tlamatini to work.

---

## Current release — v1.49.1

`v1.49.1` is the newest annotated release and the current documentation/package version. The tag resolves to commit `6adf3623`; the aligned local/remote `HEAD` is one commit later at `abc7899a`, and runtime identity still comes from Git/build metadata rather than this prose. The release adds **NetSpeed-Calculator**, the 88th workflow agent and 66th wrapped launcher; WAL-aware database backup, staged replacement, and pre-Django hot-swap through SQLite's online backup API; Googler's structured Google-dork builder and lawful-source presets; an External MCP Adder skill with a diagnose-before-activate lifecycle; the append-only Deep Internet Research starter prompt; Ollama Pro-or-higher guidance for complete operation; and private-release contact synchronization that keeps public builds empty of contact PII.

NetSpeed-Calculator measures download, upload, latency, jitter, packet loss, and bufferbloat against several keyless providers. It discards TCP slow start, samples throughput as `d(bytes)/dt`, rejects outliers, publishes Student-t confidence intervals, and fuses providers with fixed- or random-effects meta-analysis plus Cochran's Q/I². Its `full`, `download`, and `upload` actions consume real bandwidth; `validate` only checks provider reachability, while `providers` lists the catalog. A full run commonly transfers about 100-200 MB, so the wrapped tool is in Ask-Execs tier D and must not be repeated casually.

Database copies no longer treat a bare WAL-mode `db.sqlite3` file as complete. `agent/sqlite_copy.py::consistent_copy()` reads through the live WAL with SQLite's online backup API, converts the destination to a self-contained DELETE-journal database, and requires `PRAGMA quick_check` before success. Backup DB and Set DB both use that path; pre-Django hot-swap archives the outgoing database with its `-wal`/`-shm`/`-journal` sidecars, clears stale destination sidecars, and only then promotes the staged copy.

Googler's visual/pool agent now compiles structured search fields into valid Google syntax instead of making operators a fragile hand-written exercise. Presets cover books, public/open books, papers, manuals, documents, slides, sheets, and directory listings; aliases expand classes such as `ebook`, `docs`, `code`, and `data`; multiple sites or file types become parenthesized uppercase-`OR` groups; and exact phrases, exclusions, proximity, ranges, dates, title/URL/text/anchor filters, and discovery operators are normalized mechanically. Explicit fields always override preset defaults. For PDF/EPUB/file hunts, use `content_mode: links_only`: Googler's deliverable is the indexed URL list, which Apirer can download and File-Extractor/File-Interpreter can read. The direct Multi-Turn `googler` tool accepts equivalent operators inside its query string, while the structured fields belong to the visual/pool agent. Googler finds only publicly indexed URLs; she does not bypass access controls, and the user remains responsible for copyright, licensing, authorization, and use.

Search execution is also resilient rather than a brittle Google-then-one-fallback path. **Tier 0 uses plain `urllib` HTTP first** against four server-rendered routes (DuckDuckGo HTML, Bing, DuckDuckGo Lite, Mojeek), harvesting outbound result links without browser fingerprints, consent dialogs, JavaScript-app failures, or CSS-selector dependence. If those routes return nothing, Tier 1 opens a **visible installed Chrome** window (`headless: false`), falls back to bundled Chromium if needed, and tries seven direct-results routes (DuckDuckGo HTML/Lite, Mojeek, Bing, Google, Brave, Startpage) with bounded jittered retries. The log always names the route that answered. `site:` and `filetype:` carry broadly, but advanced `before:`/`after:`/`AROUND()`/numeric-range semantics are Google-specific, so a fallback may intentionally return broader candidates; pin `engines: [google]` when exact full-vocabulary behavior matters (pinning also skips Tier 0). Headless mode remains available for unattended browser fallback but is explicitly the more refusal-prone path.

The new `adding-external-mcp` skill turns External-MCP setup into one guarded sequence: classify transport, write/import a secret-separated catalog entry, run MCP Doctor, activate only on operator intent, wait for healthy tools, inspect status/list output, then call the remote tool. The Deep Internet Research card is appended as prompt 118 in Getting Started and requests Multi-Turn plus Exec Report for a long, link-rich search that may use Sequential Thinking, Memory, MCPs, and agents.

The previous annotated release, `v1.48.17` (2026-08-16), remains fully carried. Its same-day lineage is **`v1.48.15`** (encoding-safe Grepper + the closed Exec-Report status vocabulary), **`v1.48.16`** (themed pop-ups + a post-build frozen-bundle proof), and **`v1.48.17`** (Escape dismissal standardization and the sealed updater). Grepper recognizes BOM-marked UTF-8/16/32 before cp1252/Latin-1 fallbacks, so valid Windows text is searchable while genuine binaries remain skipped.

Exec-Report status handling now uses a closed, source-guarded vocabulary with five disjoint classes: completed diagnostics, intact completed work, degraded work, work not done, and agent errors. Degraded deliverables such as inaudible token-only speech or a compromised PDF are red rather than falsely clean; named completions are auditable greens; an unknown token still fails open but is identified by rule `R8b`. The repository-wide guard scans every pool-agent `status:` literal so a newly invented token fails during tests instead of silently defaulting green. Kuberneter now reports numeric `returncode`, explicit `success`, and a real `ok`/`failed` status token, preventing a failed `kubectl` call from being painted green.

Updater coverage protects the separately built `Uninstaller.exe` during self-update and keeps the preserve-list parser from being confused by comments. Public release builders forcibly clear inherited private External-MCP catalog and contact opt-ins; only the explicit keyed/private builder can bundle private state, and it first merges same-machine contact sources into gitignored `contacts.private.json` without putting PII into a public build or self-modify snapshot. Drift-proof tests derive supervisor counts and prompt rules from source. The source-verified worktree surface is **88 workflow agents**, **66 wrapped chat agents**, **108 Multi-Turn tools** (**20 core + 66 wrapped + 12 ACPX/Skill + 10 External-MCP supervisors**), **37 JavaScript modules**, **29 runtime skills**, and **197 migrations**. The `v1.48.14` private MCP runtimes, inactive Memory/Sequential-Thinking defaults, public/private catalog separation, and lossless diagram restoration remain carried.

Dialog behaviour is now uniform on both pages: **Escape dismisses every dialog and means exactly what the titlebar ✕ means**, while an outside click still never dismisses anything — so a guarded prompt cannot be lost to a stray click, and no dialog can trap you either. A single dispatcher finds the topmost dialog and activates *that dialog's own* dismiss control, so an Ask-Execs permission prompt still answers **Deny**, a confirmation still resolves to "no", scroll locks are still released, and a sealed update step still refuses to close. The last native browser pop-ups are gone: `alert()` / `confirm()` inside the contacts book and the External-MCP dialog were replaced by themed `tlmAlert` / `tlmConfirm` panels that match the app instead of showing OS chrome over it.

The build now also proves what it ships. Several modules reach the frozen app only through fail-open imports, which cannot report their own absence — the app would boot perfectly and silently lose the capability. After PyInstaller succeeds, `build.py` opens the archive it just produced and verifies that the runtime provisioner, the External-MCP defaults and client, the verdict engine, the path guard, the self-update module, and the version resolver are all really inside it, aborting the build if any is missing.

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
| 🦠 | **Windows Defender hardening** | Two path-independent scripts that auto-detect any install directory, grant Tlamatini 10 monitoring privileges while keeping all protections active, then scan 7 attack surfaces for hacker activity. No other AI assistant ships its own Defender integration. |
| 📟 | **STM32 · ESP32 · Arduino firmware** | Scaffold → build → **flash a real connected board** → read serial, with a safety preflight that refuses mis-targeted firmware. |
| 🧩 | **A VISUAL WORKFLOW DESIGNER** | **88 drag-and-drop agent types** on a canvas you wire into runnable, savable `.flw` flows. *No other coding agent — Claude Code, Codex, none of them — gives you this.* This is the crown jewel. |

> **The headline no competitor can copy:** Tlamatini is the only local-first AI dev assistant where you *design the agent workflow visually*, then have it flash firmware, drive Unreal/Blender, run security tools, and command any external MCP — all from one machine.

---

## 🔒 And it's yours alone

Tlamatini's application, database, workflows, agent code, credentials, and embedding model remain under your control on your machine. **Its intended chat, planning, vision, and tool-calling configuration uses Ollama cloud models**, so the prompts and context sent to those configured models are processed through Ollama's cloud service. Direct Claude API use, external coding-agent CLIs, remote MCP servers, and other third-party integrations remain separately configurable. Review each provider's privacy terms and decide what project material you authorize Tlamatini to send outside your machine.

## ⚠️ CLEAR DISCLAIMER — USER CONTROL, JURISDICTION, AND RESPONSIBILITY FOR AGENTS

Every agent in `Tlamatini/agent/agents/` is intentionally provided as a **plain-Python program** so its operating code can be read, audited, edited, restricted, or disabled by the user. This transparency is a user-control mechanism, **not a warranty that an agent is secure or suitable for a particular environment**. The agents do not have independent authority or jurisdiction: the user alone decides whether, where, how, and with which permissions they run.

When you enable, configure, modify, chain, or execute an agent, **that agent and its execution are under your control and your jurisdiction**. You are solely responsible for reviewing its code and configuration; protecting and limiting its secrets, credentials, and permissions; selecting and authorizing every file, folder, network target, browser, shell, API, external MCP server, machine, hardware device, and downstream system it can access; supervising its output; and complying with every law, policy, license, contract, and authorization that applies to your use.

**BY RUNNING AN AGENT, YOU ACCEPT RESPONSIBILITY FOR ITS ACTIONS AND CONSEQUENCES. TO THE FULLEST EXTENT PERMITTED BY APPLICABLE LAW, ANY SECURITY BREACH, DATA EXPOSURE OR LOSS, UNAUTHORIZED ACTION, CREDENTIAL LEAK, UNSAFE AUTOMATION, POLICY OR LEGAL VIOLATION, SYSTEM COMPROMISE, DEVICE DAMAGE, FINANCIAL LOSS, OR OTHER HARM ARISING FROM YOUR USE, CONFIGURATION, MODIFICATION, OR EXECUTION OF AN AGENT OR AGENT WORKFLOW IS THE RESPONSIBILITY OF THE USER WHO RUNS IT.** Tlamatini's orchestration, documentation, examples, and guardrails do not authorize access to third-party systems and cannot replace the user's own security review, permission controls, monitoring, or legal compliance.

---

## 📋 The full capability list

Everything Tlamatini can do, grouped:

**🧩 Orchestration & design**
- **Visual Workflow Designer (ACP)** — 88 drag-and-drop agent types wired into runnable flows; save/load `.flw` files; Flow Compiler validates the canvas into `config.yaml`.
- **Multi-Turn orchestration** — a tool-calling loop with **108 built-in tools** and a global execution planner; **Step-by-Step** mode paces hands-on setup one action at a time; **self-healing model steps** mean a network/model hiccup never freezes her — she retries under a watchdog, finishes gracefully from work already done, and always tells you what happened.
- **FlowCreator / FlowHypervisor** — let an LLM design a flow; a watchdog monitors flow health. FlowCreator is now also **callable from chat** (`chat_agent_flowcreator`): describe a flow in plain words and it writes a real, canvas-loadable `.flw` file to disk.
- **Parametrizer / Gatewayer / Gateway-Relayer / Node Manager** — chain agent outputs into the next agent's config; trigger flows from webhooks, folder-drops, or GitHub/GitLab.
- **ACPX** — spawn external coding-agent CLIs (Claude Code, Codex, Cursor, Gemini, Qwen, and more) as tools and relay between them.

**📟 Firmware & hardware**
- **STM32er** — zero-config STM32 build/flash/observe across the whole ST 32-bit line (Blue Pill → F7/G/L/H7/U5/WB) via a dual backend (PlatformIO `ststm32` + the STM32F407VG template MCP), with a critical-mission safety preflight.
- **ESP32er** — direct PlatformIO build/flash/monitor, zero-config bootstrap.
- **Arduiner** — direct `arduino-cli`, auto-installs binary + core, build/upload.
- **ESPHomer** — ESPHome smart-home device configs (YAML, no C++), zero-config.

**🎬 3D & creative engines**
- **Unrealer** — Unreal Engine control from chat.
- **Blenderer** — Blender scene/object/render/code over the official MCP socket.

**🛠️ Code & projects**
- **PDFer** — the **document composer**: turn Tlamatini's own answer, some Markdown/HTML, plain text, a folder of images, or several existing PDFs into ONE styled PDF — with a cover page, real tables, page numbers and an optional table of contents. It is the WRITE side of the document family (File-Extractor / File-Interpreter *read* documents; PDFer *authors* them). **Needs no installation** — every engine it uses already ships inside Tlamatini. Modes: `auto` (it sniffs the content for you) / `markdown` / `html` / `text` / `images` (one-per-page, fit, or grid) / `mixed` (prose + embedded figures) / `merge` / `info` / `validate`. Optionally let an Ollama model tidy the text into clean Markdown first (off by default; a failed tidy never loses your document). PDFs land in **Documents/TlamatiniPDF** with a collision-proof name, and a fail-safe preflight refuses rather than write an empty or wrong file.
- **LaTeXer** — the **LaTeX typesetter**, and the typesetting sibling of PDFer: PDFer *composes* a PDF out of Markdown, HTML and pictures; LaTeXer *typesets* one from real `.tex` source — proper mathematics, a real bibliography, numbered cross-references, an index. Hand it a whole folder of `.tex` files and it finds the master document itself, follows every `\input`, runs `biber`/`bibtex` and `makeindex`, and keeps re-running the compiler until the cross-references settle — then it turns the famously unreadable LaTeX log into a short list of real errors. You can also hand it a bare fragment (even just `$E = mc^2$`) and it wraps it in a proper preamble for you. Eight built-in templates (article, report, book, beamer, letter, cv, homework, spanish-article), plus authoring actions to create, edit, read, list, lint and inspect `.tex` files. PDFs land in **Documents/TlamatiniLaTeX**.

  > ### ⚠️ LaTeXer needs **MiKTeX** — and that is the *only* thing it needs
  >
  > Tlamatini does **not** ship a TeX distribution: a full one is several gigabytes, and the whole release is kept small on purpose. So install **MiKTeX** once — **https://miktex.org/download** — and then install Tlamatini. That is it: **MiKTeX + Tlamatini = LaTeXer works, forever, with nothing else to configure.**
  >
  > **Why MiKTeX specifically?** Because when a document asks for a LaTeX package you have never installed, **MiKTeX downloads and installs it by itself, in the middle of the build** — so the document still comes out. That single feature is what lets LaTeXer typeset *anything* out of the box. TeX Live and MacTeX are detected and used if you already have one, but neither can do that, so you would have to hunt down missing packages yourself. **MiKTeX is the recommended choice.**
  >
  > No LaTeX installed? LaTeXer tells you so plainly and refuses — it never crashes and never pretends a PDF was made. Ask it to run `action: validate` to see exactly what it found, or `action: install` and it will download and launch the official **MiKTeX** installer for you.
- **Editor / Grepper / Globber** — surgical find-and-replace, regex content search, and filename glob (Claude-Edit/Grep/Glob equivalents). Grepper searches UTF-8, BOM-marked UTF-16/32, cp1252, and Latin-1 text without confusing valid Windows text with NUL-bearing binary data.
- **File-Creator / Mover / Deleter / File-Interpreter / File-Extractor** — create, move, delete, read-and-interpret, extract from PDF/DOCX.
- **Executer / Pythonxer** — run shell commands and gated Python.
- **Gitter** — full git control. **Googler** — resilient two-tier search + extraction: plain-HTTP server-rendered routes first, then visible Chrome/bundled Chromium across seven browser routes, plus a structured Google-dork builder, lawful-source presets, grouped site/filetype filters, and `links_only` output for downstream file retrieval.
- **Hybrid RAG** — FAISS + BM25 retrieval, metadata extraction, context budgeting, grounded in your codebase.
- **Skills** — `SKILL.md` packages: code-review, security-audit, kali-pentest, flow-making, skill-creator, summarize, audit/lint/refactor helpers, and integration stubs (GitHub, Gmail, Slack, Jira, Notion, Todoist, Trello, Weather).

**🛡️ Security**
- **Kalier** — authorized Kali Linux / MCP-Kali-Server offensive-security assessments.
- **Discoverer** — ProjectDiscovery recon suite (subfinder/httpx/naabu/katana/nuclei/cvemap — the CVE search runs ProjectDiscovery's `vulnx`, since cvemap's own API was retired Aug 2025) via a self-installing private Go toolchain in <install_dir>/Go; authorized recon, attack-surface mapping & vulnerability discovery. The **ProjectDiscovery Cloud (PDCP) key is OPTIONAL** (lifts cvemap/vulnx rate limits, enables nuclei `-ai`/cloud upload) — set it once in **Config ▸ Access Keys Wizard ▸ "Security Recon (ProjectDiscovery)"** (auto-injected into every run; redacted from `.flw` exports and by `regen_secrets.py` before a push).
- **Nmapper** — LOCAL, **use-only** nmap bridge for pentesters / CTF: runs a real `nmap` the user installed themselves (Nmapper **NEVER bundles or redistributes nmap** — nmap's NPSL forbids embedding it in a product without a paid OEM licence), resolving it from PATH → `C:\Program Files\Nmap` → a `%LOCALAPPDATA%\Tlamatini\nmap` copy; if it's absent it refuses gracefully and `action='install'` fetches the OFFICIAL free nmap installer (admin/UAC; also brings Npcap). The default is an UNPRIVILEGED TCP connect scan (`-sT`, no Npcap, no admin) so a fresh install scans immediately; SYN / `-O` / UDP auto-downgrade to a connect scan on Windows without Npcap. Actions: `quick` / `full` / `top_ports` / `version` / `scripts` (NSE) / `host_discovery` / `udp` / `custom` / `validate` / `install`; emits `INI_SECTION_NMAPPER`. Distinct from **Kalier** (a remote Kali box) and **Discoverer** (ProjectDiscovery). **Authorized targets only.**
- **NetSpeed-Calculator** — measures **your** Internet connection and gives you the answer *with its error bar*: download, upload, latency, jitter, packet loss and **bufferbloat**. It does not trust a single speed-test site — it measures against **several keyless public providers at once** (Cloudflare, Ookla, Fast.com, LibreSpeed, Hetzner, CacheFly; no account, no API key) and then fuses them with a real random-effects meta-analysis, so you get a 95% confidence interval and a plain statement of whether the providers actually *agreed*. It follows RFC 6349: several parallel TCP streams, the slow-start ramp thrown away, throughput sampled as a derivative instead of the naive total÷elapsed, outliers rejected. **Bufferbloat is the one most people are missing** — it is graded A+ to F and it is usually the real reason a "fast" connection has choppy video calls. Dead or moved endpoints are skipped **with a named reason**, never as a silent `0.00 Mbps`. ⚠️ It consumes real, possibly **metered** bandwidth (~100-200 MB per full run), so it asks before running.
- **Zavuerer** — **Zavu** unified messaging: SMS / WhatsApp / Telegram / Email / Voice from ONE API key (`channel: auto` smart-routes to the best channel with auto-fallback). Set the key once in **Config ▸ Access Keys Wizard ▸ "Unified Messaging (Zavu)"**; direct HTTP, fail-safe preflight, refuses safely when no key is set. **Zavu pricing:** sign-up is free (no card), but sending is pay-as-you-go — Zavu charges per message.
- **Security Hardening scripts** — two path-independent v2 scripts (`enable_tlamatini_v2.bat` + `run_defender.bat`) that auto-detect any install directory and grant Tlamatini 10 monitoring privileges (Defender exclusions, CFA whitelist, ASR audit, firewall, Security log, WMI, Task Scheduler, Registry, SCM, auditing) while keeping all protections active, then scan 7 attack surfaces (logons, network, processes, tasks, services, registry, critical dirs) for hacker activity. Zero hardcoded paths — works from any drive/folder.
- **security-audit / kali-pentest** skills.

**🔌 External integration**
- **Universal External-MCP client** — connect to any MCP server over 4 transports, up to 5 active, with 10 supervisor tools and an **MCP Doctor** agent that triages a server before you wire it.
- **External MCP Adder skill** — follow the complete classify → configure/import → doctor → activate → wait → status/list → call lifecycle instead of guessing at a transport or declaring an unproven server ready.
- **Memory + Sequential Thinking included, inactive by default** — open **External ▸ MCPs**, select `memory` or `sequential-thinking`, and activate only what you want. Memory stores its graph in `%LOCALAPPDATA%\Tlamatini\memory\memory.json`, outside the install directory so updates preserve it. Removing a shipped default records a tombstone instead of resurrecting it on the next launch.
- **Private MCP runtime, no admin required** — npx/uvx servers can trigger one-time provisioning of Node/npm/npx/pnpm or uv/uvx into `%LOCALAPPDATA%\Tlamatini\runtimes`. The External MCP dialog's runtime strip shows exactly which managers are ready and whether Tlamatini is using her private copy; **Install now** performs the same operation explicitly. Nothing is added to the system `PATH`, nothing is bundled into the installer, and a failed download never prevents Tlamatini from starting.
- **Companion-app discovery (Tlamatini-FlowPills)** — sister XAIHT apps locate Tlamatini's agent-template catalog instantly, with **no Python and no drive scan**: at install and on every launch Tlamatini publishes a per-user `HKCU\Software\XAIHT\Tlamatini` registry key + an `_tlamatini_agents_manifest.json` (each agent's `sha256`) next to the agents, and leaves a preserved-agents marker if you uninstall but keep the agents. HKCU-only, no admin, fail-open.

**🖥️ Desktop & browser automation**
- **Playwrighter** — scripted browser automation.
- **Windower** — Win32 window manager (focus/move/resize/tile/close).
- **Shoter / Mouser / Keyboarder** — screenshots, mouse, keyboard.

**🎙️ Audio, video, vision & speech**
- **Talker (TTS)** — text-to-speech via Ollama. **Whisperer (STT)** — speech-to-text (faster-whisper local + cloud fallback).
- **Recorder / Camcorder** — microphone and webcam capture.
- **AudioPlayer / VideoPlayer** — audio and video playback with volume/loop control.
- **Image-Interpreter** — triple-model vision analysis: qwen3.5:cloud + gemma4:cloud interpret each image **in parallel** on two dedicated Ollama connections, then glm-5.2:cloud merges both interpretations into one definitive report (mockup/GUI inventories in % coordinates, full OCR, people described exhaustively with identity clues taken from the image file name).

- **Screenshot → chat (paste or drop)** — hit Print Screen (or snip), Alt+Tab back to Tlamatini and press **Ctrl+V** — or drag image files onto the chat column. She saves the image into her own `Temp` folder as `image_<timestamp>.jpg`, shows a thumbnail above the input, and drops the **full path into your message at the cursor**, so you can finish the sentence — *"…what's wrong in this screenshot?"* — and send. The path is what Image-Interpreter reads.

**📨 Messaging, bridges & platform**
- **Telegrammer** — Telegram send/receive that can send under **two identities**, picked per message with `provider`: **as the bot** (`provider=bot`, Bot API + a `@BotFather` token) or **as your own account** (`provider=user`, official Telegram user session). Plain English works — say *"send it as me"* (→ your account) or *"as the bot"*. `auto` (the default) uses your account for private `@usernames`/`+phone` and the bot for numeric ids/channels. Sending as you needs a one-time login; human configs stay readable as `@username`.
- **Whatsapper** — WhatsApp send/receive with a `provider` switch for **which number sends**: **`cloud`** (default, the official Meta WhatsApp Cloud API — business number, templates, System User) or **`web`** (say *"send it as me"* / *"from my own WhatsApp"*) which sends from **your own personal number** by automating WhatsApp Web after a one-time QR login — no templates, no System User. The `web` path is unofficial (it drives WhatsApp Web) and carries Meta-ban risk; the `cloud` path remains the official, supported route.
- **Instant Messaging Doctor** — automatically diagnoses Telegrammer/Whatsapper failures and can be called directly before critical sends; validates official tokens, contacts, readable `@username` routing, Meta templates/webhooks, and emits Parametrizer-ready repair actions.
- **TeleTlamatini** — Telegram bridge into the full chat.
- **Multi-model** — Ollama (local), Anthropic Claude (cloud), Qwen (vision).
- **Self-knowledge & self-modification** — can read, modify, and rebuild her own source.
- **PyInstaller packaging** — ships as a standalone Windows `.exe`.

---

## 🧹 Your context stays clean — automatic binary detection

When you point Tlamatini at a folder (**Context ▸ Set directory as context**), real projects are full of files that are not text: compiled binaries, images, archives, model weights, databases, build artefacts. Feeding those into an embedding index is pure damage — it wastes VRAM and time, and it buries your real code under noise.

Tlamatini screens **every** file by its actual bytes before loading it, and silently skips the binary ones. It is on by default and needs no setup.

- **Fast by design** — at most one 8 KiB read per file, and known binary extensions are never opened at all. Screening a 4 GB video costs the same as screening a README.
- **Content-based, not name-based** — a PNG renamed `notes.md` is still caught. This works *alongside* **Context ▸ Set file type omissions**, which stays exactly as it was for the files *you* choose to ignore.
- **Never silent** — every skipped file is listed in `tlamatini.log` with the reason it was skipped, so you always know why something is not in your context:

```
--- [BINARY-GUARD] 3 binary file(s) OMITTED from the context / embedding chain
--- [BINARY-GUARD]   ✗ OMITTED C:\proj\assets\logo.png  [extension: known binary extension .png]
```

- **Safe by default** — if anything is uncertain or unreadable, the file is loaded as text rather than dropped. Your context is never removed on a guess. Accented and legacy-encoded text files (Spanish, French, cp1252 …) are always kept.

Turn it off with `"binary_context_detection": false` in `config.json`; tune it with `binary_detection_control_ratio`, or rescue a specific extension with `binary_detection_force_text_extensions`.

## See it work

- ▶️ **[One-minute teaser](https://www.youtube.com/watch?v=4MyRXBahHuU&t=41s)** · 🎬 more demos on **[xaiht.org](https://xaiht.org)**.

---

## 🛡️ Security Hardening — Windows Defender Whitelist & Active Defender

Tlamatini ships with **two path-independent security scripts** that grant her the monitoring privileges she needs (whitelist) and actively scan your system for hacker activity (defender). Both scripts **auto-detect** their installation directory — they work from **any drive, any folder, any install path** with zero configuration.

### What they do

| Script | Purpose | Requires Admin |
|---|---|---|
| **`enable_tlamatini_v2.bat`** | Grants Tlamatini 10 monitoring privileges: Defender exclusions, CFA whitelist, ASR audit mode, PowerShell RemoteSigned, firewall rules, Security log access, WMI/Task Scheduler/Registry/SCM access, plus Security auditing policies. **All protections remain active** — Tlamatini gets a pass, hackers stay blocked. | ✅ UAC elevation |
| **`run_defender.bat`** | Scans 7 attack surfaces: logons (failed/success), network connections, suspicious processes, scheduled tasks, services, registry Run keys, and critical directories. Auto-blocks malicious IPs and kills malware processes. Logs everything to `security_logs/`. | ✅ UAC elevation |

### How to use them

1. **Right-click** `enable_tlamatini_v2.bat` → **Run as administrator** (a UAC prompt appears; click **Yes**).
2. Wait for the 10 privileges to be granted. Restart Tlamatini for full effect.
3. **Right-click** `run_defender.bat` → **Run as administrator** to scan for hacker activity.
4. Check `security_logs\alerts.log` for any `CRITICAL` or `ALERT` entries — those are your hackers.

### Path-independent auto-detection (v2)

The v2 scripts contain **zero hardcoded paths**. They use:

- **Batch files** — `%~dp0` (the directory where the `.bat` file lives) to locate their companion `.ps1` scripts.
- **PowerShell scripts** — `$PSScriptRoot` (the directory where the `.ps1` file lives) → `Split-Path -Parent` to find the Tlamatini root → `Join-Path` to build paths to `Tlamatini.exe`, `python\python.exe`, and `security_logs\`.

This means you can install Tlamatini in `C:\Tlamatini\`, `F:\AI\PowerDefenderFramework\GodessOfGods\TlamatiniX-1\`, or any other directory — the scripts auto-detect their own location and work correctly. No modifications needed.

> **Created by Angela López Mendoza (@angelahack1)** — Tlamatini, the one who knows.

---

## Installation

See **[the full docs](https://github.com/XAIHT/Tlamatini/blob/main/BookOfTlamatini.md)** for complete setup — cloud models (Ollama Pro/Max, Claude API), the visual workflow designer, and building a frozen Windows distribution with PyInstaller. In short: install Ollama → clone, venv, `pip install -r requirements.txt`, `migrate` → `runserver` (`--noreload` optional since 2026-07-11) → open `http://127.0.0.1:8000/`.

---

## Tech stack

Python 3.12 · Django 5.2.4 · Django Channels (Daphne ASGI) · LangChain / LangGraph · FAISS + rank-bm25 · Ollama / Anthropic Claude / Qwen vision · SQLite · PyInstaller. **Platform: Windows 10/11.**

---

## Contributing

Tested it on your board, in your engine, or on the canvas? **[Open an issue](https://github.com/XAIHT/Tlamatini/issues)** and tell me what worked and what didn't — that feedback is the most useful thing right now. PRs welcome.

---

## License

[MIT](https://github.com/XAIHT/Tlamatini/blob/main/LICENSE) · Built by [@XAIHT](https://github.com/XAIHT) · [xaiht.org](https://xaiht.org)
