<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Discoverer — New Agent Design (ProjectDiscovery suite bridge)

> **Status:** DESIGN / proposal (no code written yet). Authored 2026-06-20.
> **Doc filename:** `Discoverier-new-agent.md` (per request). **Agent display name:** `Discoverer`
> *(pending final confirmation — see "Open decisions" at the end).*

---

## 1. Summary

**Discoverer** is a new Tlamatini workflow agent that runs the **ProjectDiscovery**
security tool suite (`https://github.com/projectdiscovery`) locally, both as a
**canvas agent** and as a **Multi-Turn** wrapped tool (`chat_agent_discoverer`).

It is a **direct-CLI bridge** — self-contained, stdlib-only, **no MCP server** —
exactly like the existing **Kalier / ESP32er / Arduiner** agents. It runs **ONE
tool per run**, selected by a `tool:` field, and is **zero-config**: on the
**first call** (Multi-Turn or canvas) it installs a **private Go compiler** into
`<install_dir>/Go/` and uses it to compile the requested ProjectDiscovery tools —
no system Go, no developer setup, no PATH pollution.

| Tool | Purpose | Target flag | API key |
|---|---|---|---|
| `subfinder` | passive subdomain enumeration | `-d` / `-dL` | provider keys (optional) |
| `httpx` | HTTP probe / fingerprint | `-u` / `-l` | none |
| `naabu` | port scanner | `-host` / `-l` | none (connect-scan on Windows) |
| `katana` | crawler / spider | `-u` / `-list` | none |
| `nuclei` | template vulnerability scanner | `-u` / `-l` | PDCP for AI/cloud only (optional) |
| `cvemap` → `vulnx` | CVE search CLI | `-id` / `-product` | PDCP boosts rate limit (optional) |
| *(meta)* | `bootstrap` / `validate` / `update_templates` / `list_tools` | — | — |

> **Naming note:** ProjectDiscovery **renamed `cvemap` to `vulnx`**. The agent runs
> `vulnx` and keeps `cvemap` as an accepted alias for the `tool:` value.

---

## 2. Identity & naming convention

`agentDescription` (DB) is the single source of truth, rendered verbatim as the
canvas/sidebar label. Every other surface is a transform of it.

| Context | Form |
|---|---|
| Display (DB `agentDescription`, canvas/sidebar label, `"DISCOVERER AGENT STARTED"` log) | `Discoverer` |
| Pool / agent dir, `<name>.py`, pool name | `discoverer`, `discoverer_N` |
| CSS class, JS classMap key, connection checks | `discoverer-agent`, `discoverer` |
| Wrapped tool name | `chat_agent_discoverer` |
| Parametrizer section token | `INI_SECTION_DISCOVERER` / `END_SECTION_DISCOVERER` |
| JS connector symbol | `updateDiscovererConnection` |

---

## 3. Architecture

```
Starter -> ... -> Discoverer(tool=subfinder) -> Parametrizer -> Discoverer(tool=httpx) -> ... -> Ender
```

- **Self-contained subprocess** (`agent/agents/discoverer/discoverer.py`): stdlib
  only (`subprocess`, `urllib`, `zipfile`, `json`) — does **not** import `agent.*`,
  so it works identically in source and frozen builds.
- Reads `config.yaml`, resolves the chosen `tool`, builds its CLI argv, runs it
  with a bounded timeout, parses JSON output, emits `INI_SECTION_DISCOVERER`, and
  **ALWAYS triggers `target_agents`** (success or failure — fail-safe).
- Sibling of **Kalier** but complementary: Kalier drives a *remote Kali box* over
  the MCP-Kali-Server HTTP API; Discoverer runs ProjectDiscovery's own Go tools
  *locally*, cross-platform, with no Kali required.

---

## 4. Self-contained Go toolchain bootstrap (the key requirement)

On the **first call**, if the private toolchain is absent and `go_bootstrap: true`:

1. **Detect** OS/arch (`windows-amd64` / `windows-arm64` / `386`).
2. **Download** the official Go release zip `go<go_version>.windows-<arch>.zip`
   from `https://go.dev/dl/` into `<app>/Temp` (honors the Temp policy —
   `TLAMATINI_TEMP`, never `%TEMP%` / `C:\Temp`).
3. **Extract** to `<install_dir>/Go/` so the compiler lands at
   `<install_dir>/Go/bin/go.exe` (this is **GOROOT**).
4. **Environment** (process-scoped, never the user/system registry):
   - `GOROOT = <install_dir>/Go`
   - `GOPATH = <install_dir>/Go/gopath`
   - `GOBIN  = <install_dir>/Go/bin-tools`  (compiled PD tools land here = `tools_bin`)
   - `GOCACHE = <app>/Temp/go-build`, `GOMODCACHE = <install_dir>/Go/gopath/pkg/mod`
5. **Compile the requested tool(s)** with the private Go:
   `go install github.com/projectdiscovery/<tool>/v3/cmd/<tool>@latest`
   (e.g. `.../nuclei/v3/cmd/nuclei@latest`). Binaries land in `GOBIN`.
6. **nuclei** auto-downloads its templates to `~/nuclei-templates` on first scan
   (or via the `update_templates` meta action / `-ut`).

**Resolution order at run time** (each run): explicit `<tool>_executable` (config)
→ `<install_dir>/Go/bin-tools/<tool>.exe` → `pdtm` bin (`~/.pdtm/go/bin`) → bare
`PATH`. The agent invokes the **absolute binary path** — it never depends on the
user's PATH.

- **`install_method: go`** (default, per your requirement) = private Go compiler +
  `go install`. **`install_method: pdtm`** = a faster alternative that downloads
  *prebuilt* PD binaries (no compiler) — kept as an option, not the default.
- **First-run cost:** Go zip is ~70–90 MB; compiling each tool takes ~30–90 s
  (cached afterward, so subsequent calls are instant). Surfaced in the report.
- **Go version:** pinned and configurable (`go_version`); ProjectDiscovery tools
  require **Go ≥ 1.24**.

---

## 5. Proposed `config.yaml`

```yaml
# Discoverer Agent — ProjectDiscovery security-tool suite bridge.
# AUTHORIZED TARGETS ONLY. Runs ONE tool per run (direct CLI, no MCP server).

tool: "subfinder"          # subfinder|httpx|naabu|katana|nuclei|cvemap
                           # meta: bootstrap|validate|update_templates|list_tools

# ── Target(s) ──
target: ""                 # one target: domain / url / host / ip / cidr
targets_file: ""           # OR a file (one per line); overrides `target`

# ── Common run controls ──
json_output: true          # emit JSON/JSONL (parsed into the report)
output_dir: ""             # results dir; empty = <app>/Temp/Discoverer
rate_limit: 0              # 0 = tool default (150 r/s; naabu 1000 pkt/s)
concurrency: 0             # 0 = tool default
command_timeout: 1800      # hard cap (seconds) on the CLI run (first compile is slow)
extra_args: ""             # raw passthrough appended verbatim (escape hatch)

# ── Per-tool knobs (only the selected tool's block is used) ──
subfinder: { all_sources: false, sources: "", include_ip: false }
httpx:     { probes: "status_code,title,tech_detect", follow_redirects: false }
naabu:     { ports: "", top_ports: "100", scan_type: "c" }   # c=connect (no Npcap); s=SYN
katana:    { depth: 3, js_crawl: true, headless: false }     # headless needs Chrome
nuclei:    { templates: "", severity: "", tags: "", template_ids: "", automatic_scan: false }
cvemap:    { cve_id: "", product: "", severity: "" }         # runs vulnx

# ── ProjectDiscovery Cloud Platform key (OPTIONAL for ALL tools) ──
pdcp_api_key: ""           # empty = read PDCP_API_KEY env / credentials file.
                           # Boosts cvemap/vulnx rate limit; enables nuclei -ai + cloud.
cloud_upload: false        # nuclei/httpx/naabu dashboard upload (needs pdcp_api_key)

# ── subfinder provider keys (OPTIONAL — more subdomains) ──
subfinder_provider_config: ""   # path to provider-config.yaml (shodan/censys/vt/…)
                                # empty = subfinder's own default config

# ── Self-contained Go toolchain (installed on FIRST use) ──
go_bootstrap: true         # on first call, download + install the Go compiler
install_method: "go"       # go = compile tools with the private Go (go install)
                           # pdtm = download prebuilt PD binaries instead (no compiler)
go_dir: ""                 # empty = <install_dir>/Go   (GOROOT)
tools_bin: ""              # empty = <install_dir>/Go/bin-tools   (GOBIN; compiled tools)
go_version: "1.24.5"       # Go release fetched from https://go.dev/dl/ (PD needs >= 1.24)
auto_update: false         # re-install/update the tool before running
preflight: true            # fail-safe checks; REFUSE rather than misfire

# ── Canvas wiring ──
source_agents: []          # upstream logs to monitor
target_agents: []          # downstream agents to start after (ALWAYS triggered)
```

Global defaults (`go_dir`, `tools_bin`, `pdcp_api_key`, `go_version`) seeded into
`config.json` via `tools._seed_global_agent_defaults`, so chat runs never repeat them.

---

## 6. API-key model (what is / isn't required)

- **Nothing is hard-required** to RUN any of the seven tools.
- **PDCP key** (`PDCP_API_KEY`, ProjectDiscovery Cloud Platform, free): the key you
  remembered. **Optional.** Lifts `cvemap/vulnx`'s 10-req/min cap; enables nuclei
  `-ai` + cloud dashboard upload. One key, set once. Priority: config field →
  `PDCP_API_KEY` env → on-disk credentials file.
- **subfinder providers:** subfinder does **not** use PDCP — it reads ~95 source
  keys (Shodan, Censys, VirusTotal, SecurityTrails, GitHub, FOFA, …) from
  `provider-config.yaml`. **Optional**, but more keys = more subdomains.
- **GitHub token / uncover / interactsh:** optional, provider-specific, via the
  subfinder/nuclei configs.

---

## 7. Fail-safe preflight (REFUSE, never crash)

Before running, validate and **refuse** (emit a failed report + still trigger
`target_agents`) on any fatal — mirroring ESP32er/Arduiner:
- the Go toolchain / chosen tool is resolvable (else bootstrap, else fatal);
- a `target` or `targets_file` is present for a scanning tool;
- **naabu on Windows:** SYN (`scan_type: s`) needs Npcap + admin → auto-fall back
  to connect-scan (`-s c`) with a warning, never a crash;
- **katana/nuclei headless** → warn if no Chrome found.

---

## 8. Output contract — `INI_SECTION_DISCOVERER`

Emitted in ONE atomic `logging.info()` call (Parametrizer-parseable):

```
INI_SECTION_DISCOVERER<<<
tool: subfinder
target: example.com
returncode: 0
success: true
findings_count: 42
json_path: <app>/Temp/Discoverer/subfinder_example.com_<ts>.jsonl
pdcp_used: false
stage: run

<stdout / parsed findings = response_body>
>>>END_SECTION_DISCOVERER
```

Registered as a Parametrizer source: `SECTION_AGENT_TYPES += 'discoverer'`
(`parametrizer.py`) and `PARAMETRIZER_SOURCE_OUTPUT_FIELDS['discoverer'] =
(tool, target, returncode, success, findings_count, json_path, pdcp_used, stage,
response_body)` (`views.py` / `agent_contracts.py`).

---

## 9. Implementation plan (file-by-file — the 8-step + Multi-Turn surfaces)

1. **Backend script** — `agent/agents/discoverer/discoverer.py` + `config.yaml`
   (boilerplate from `arduiner.py`; add `_bootstrap_go`, `_install_tool`,
   `_resolve_tool`, `_preflight`, per-tool `_build_argv`, `_emit_section`).
2. **View + URL** — `update_discoverer_connection_view` in `views.py`, route in `urls.py`.
3. **Migration** — `agent/migrations/<NNNN>_add_discoverer.py` (seeds the `Agent` row,
   `agentDescription='Discoverer'`).
4. **CSS** — unique 4-colour gradient `.canvas-item.discoverer-agent` (+ hover) in
   `agentic_control_panel.css`.
5. **JS (4 files)** — `updateDiscovererConnection` in `acp-agent-connectors.js`;
   classMap + 6 sites in `acp-canvas-core.js`; undo/redo in `acp-canvas-undo.js`;
   `.flw` load in `acp-file-io.js`; `/* global */` decls.
6. **FlowCreator** — entry in `agents/flowcreator/agentic_skill.md`.
7. **Docs** — `README.md` (count, tree, table, glossary, changelog, API),
   `agents_descriptions.md`, `docs/claude/agents.md`.
8. **Multi-Turn (7.5–7.8)** — `ChatWrappedAgentSpec` in `chat_agent_registry.py`;
   Tool-row migration (`Chat-Agent-Discoverer`); Flow-Generator branch in
   `agent_page_chat.js::_mapToolArgsToAgentConfig`; **≥1 Catalog-of-Prompts**
   demo migration (contiguous `prompt-N`). Exec-Report capture is **automatic**.
9. **Packaging** — `build.py`: ship `agents/discoverer/`; no new Python dep (the Go
   compiler is downloaded at runtime, not bundled). `.gitignore` the runtime
   `<install_dir>/Go/`. Verify with the two self-update / self-modify sweeps.
10. **Tests** — `agent/test_discoverer_agent.py` (argv-building per tool, preflight
    refusal, bootstrap path resolution) + Exec-Report capture audit stays green.

---

## 10. Safety

These are **active** recon/scan tools (naabu/nuclei/katana/httpx touch the target).
Doc + prompt make **authorized-targets-only** explicit (like Kalier), and the agent
is automatically gated by the **Ask Execs** toggle in Multi-Turn.

---

## 11. Open decisions (confirm before implementation)

1. **Agent name:** `Discoverer` (recommended) vs `Discoverier` vs other. Locks ~15 files.
2. **Bootstrap default:** `install_method: go` (private Go compiler → `<install_dir>/Go`,
   per your request) — confirmed. `pdtm` prebuilt kept as an option.
3. **Go version pin:** `1.24.5` default (PD requires ≥ 1.24) — OK to auto-track latest?
4. **`<install_dir>` resolution:** frozen = next to `Tlamatini.exe`; source = repo/app root.
```
