<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# Tlamatini — Gotchas, Build/Lint, Roadmap, Work Style

> **The chronological "Recent Fixes / Gotchas" fix log now lives in `docs/claude/recent-fixes.md`** — it was split out of this file and is **NOT auto-imported** into the assistant context, to keep every session lean. It holds the dated "do NOT revert this / keep these surfaces aligned" contracts for ACPX, the Flow Compiler, the planner, the Exec Report pipeline, the ACP canvas, wrapped chat-agent parsing, the desktop-UI agents, `prompt.pmt`, `regen_secrets.py`, and the logging filters. **Read `recent-fixes.md` before modifying or reverting code in any of those subsystems.**

## Claude API Client (opus_client)

Located in `agent/opus_client/claude_opus_client.py`. Features:
- Text chat, image analysis, PDF analysis, streaming
- Multi-turn conversations with `create_conversation()`
- Tool/function calling with auto-execution
- Models: `Model.OPUS_4_5`, `Model.SONNET_4_5`, `Model.HAIKU_4_5`

```python
from claude_opus_client import ClaudeClient
client = ClaudeClient()
response = client.chat("Hello")
```

---

## Building & Packaging

```bash
# Step 1: Build the app
python build.py
#   add --self-modify to ship the self-modify source tree (see below)

# Step 2: Build the uninstaller
python build_uninstaller.py

# Step 3: Build the installer
python build_installer.py
```

The frozen build resolves paths via `os.path.dirname(sys.executable)` vs source mode `os.path.dirname(os.path.abspath(__file__))`. Both modes must be supported in any new tool.

**`build.py --self-modify` (2026-05-25; snapshot generation 2026-06-12)** — when this flag is passed, the build bundles Tlamatini's own source tree `TlamatiniSourceCode/` next to the executable (it then flows into `pkg.zip`), producing a **self-able-modify** build the running app can read, rewrite, and REBUILD. Since 2026-06-12 the tree is **generated fresh** by `copy_source_assets.py` (repo root) from the live repo — full source surface (.py/.js/.css/.html/.ps1/.pmt/.yaml/build scripts + build-required .ico/.wav/.svg), with media (.pdf/.pptx/images/videos), jd-cli.jar, secrets (redacted to `<KEY goes here>`), and regenerable state omitted; the snapshot carries `_REBUILD_INSTRUCTIONS.md` + `_SOURCE_SNAPSHOT_MANIFEST.json` telling the runtime how to restore the omitted binaries from the install root and rebuild. A generation failure falls back to the legacy static copy of `Tlamatini/agent/TlamatiniSourceCode/`. Without the flag the directory is omitted entirely — a **not-self-able-modify** build. The build prints `Self-modify build : YES — bundling TlamatiniSourceCode` / `… no — source tree omitted`. Independently, `build.py` always ships `agent/Tlamatini.md` (the LLM self-knowledge file) both via `--add-data` and as an `optional_file_copies` copy to the install root, so the frozen "next to the exe" resolution of `{self_knowledge}` works. See `docs/claude/architecture.md` → *Self-Knowledge & Self-Modification*.

---

### numpy / OpenCV must be embedded in BOTH Pythons (2026-06-15)

The media agents (Recorder / Camcorder / AudioPlayer / VideoPlayer / Whisperer) run under the **carried** Python (`<install>/python`), NOT the frozen exe — so their native libs must be installed THERE. `build.py` asserts `numpy` + `cv2` in `_CARRIED_PYTHON_REQUIRED_IMPORTS` (the carried-Python probe → the build ABORTS if either is missing) and in the frozen-asset `_agent_libs` import-verify list, and adds `--collect-all cv2` so OpenCV is also embedded in the frozen `_internal` (numpy is handled by `pyinstaller_hooks/hook-numpy.py`). A dependency that is pinned in `requirements.txt` but NOT installed in the carried Python crashes the pool agent at runtime even though the source is correct — these guards exist to catch exactly that. See `docs/claude/recent-fixes.md` (2026-06-15).

---

## Linting

```bash
# Python
python -m ruff check

# JavaScript/CSS
npm run lint
```

---

## Versioning (SemVer 2.0.0, git-tag-derived) — see `VERSIONING.md`

Tlamatini uses SemVer 2.0.0 with git tags (`vMAJOR.MINOR.PATCH`) as the single source of truth. The full contract — including bump rules, the four-tier resolution precedence, the no-tag fallback behaviour (always the bare base tag — no `.devN`, no `+gSHA`, no `.dirty` ever appears in the version string), the step-by-step release cut, and the file-by-file integration map — lives in **`VERSIONING.md`** at the repo root. Quick map for AI assistants:

- Runtime resolver: `Tlamatini/agent/version.py::get_version()` (no Django dep, safe to import from `manage.py` before Django init).
- Build-time shim used by all three build scripts: `versioning.py` at the repo root.
- Generated bundle file (gitignored): `Tlamatini/agent/_version.py`.
- Template surface: `{{ version }}` via `tlamatini.context_processors.app_version`, currently consumed only by `agent_page.html` (the About dialog).
- HTTP surface: `GET /agent/version/` (open endpoint).
- **Never** re-introduce a hardcoded `Tlamatini v1.0.0` anywhere. The About dialog HTML now reads `{{ version }}`.
- **Never** commit `_version.py` — it's gitignored and rewritten on every build.
- When adding a new artefact-producing script that ships an `.exe` (or any binary with VERSIONINFO), mirror the `build_uninstaller.py` pattern: import `extract_cli_version` + `resolve_build_version` + `render_versioninfo_for` from `versioning.py`, write a `<Name>.version.txt`, pass `--version-file=…` to PyInstaller, and `.gitignore` the .txt.

---

## Known Hardcoded Assumptions

1. `factory.py` recognizes only `System-Metrics` and `Files-Search` by Mcp description
2. Frontend MCP dialog is hardcoded for two checkboxes
3. Tool UI is dynamic; MCP UI is not
4. `get_mcp_tools()` returns LangChain tools, not MCP services
5. `ask_rag()` does not fetch MCP data itself
6. Files-Search main path uses `FileSearchRAGChain`, not `mcp_files_search_client.py`
7. `mcp_files_search_client_uri` in config is unused by the main chain
8. `FileSearchRAGChain` falls back to `localhost:50051` for gRPC
9. Tool status keys are handwritten and can drift
10. `mcpContent` is stored as string, not boolean
11. Planner default `max_selected_tools` was lowered from 50 → **20** to prevent keyword inflation from selecting every tool on a single request *(historical: since 2026-06 Multi-Turn binds the FULL enabled surface — the planner subset no longer drops tools from the bind; the constant now only shapes capability hints/ordering — see `multi-turn.md`)*
12. `tlamatini.log` is truncated on every server start (mode `'w'`) and has no rotation
13. **The web port is NOT hardcoded any more (v1.40.1)** — it is `config.json` → `django_port` (default `8000`), resolved by `manage.py::_resolve_django_port()` and injected into every launch path by `_apply_configured_port()` (frozen double-click, `.flw` association, browser auto-open, source `runserver`, `startserver`). An explicit CLI `[ipaddr:]port` wins; resolution is fail-open to 8000. **Do not re-introduce a literal `8000` in a launch path.** Still genuinely hardcoded and NOT covered by the key: a direct `daphne`/`uvicorn` launch (bypasses `manage.py`), the MCP helper listeners `:8765` / `:50051`, and TeleTlamatini's own `tlamatini.base_url`. See `docs/claude/architecture.md` → *Configurable web port*.

---

## Recent Fixes / Gotchas

The dated fix log moved to **`docs/claude/recent-fixes.md`** (consult-on-demand, not auto-imported). Prepend new fix entries there, not here. See the note at the top of this file for when to read it.

---

## Recommended New Agents (Roadmap)

From `NEW_AGENT_RECOMMENDATIONS.md`:

| Priority | Agent | Purpose |
|----------|-------|---------|
| 1 | **Tester** | Test runner (pytest, jest, junit) with pass/fail routing |
| 2 | **Reviewer** | ✅ **Implemented v1.4.2** — AI code review (LLM-powered git-diff analysis); canvas agent (#63) + `code-review` skill |
| 3 | **Analyzer** | ✅ **Implemented v1.4.2** — Static analysis / SAST (bandit, semgrep, ruff, eslint, gitleaks, pip-audit); canvas agent (#64) + `security-audit` skill |
| 4 | **Jiraer** | Issue tracker integration (Jira/GitHub Issues) |
| 5 | **Logger** | Structured log writer / report aggregator |
| 6 | **Vaulter** | Secrets / environment injection |
| 7 | **Webhooker** | Webhook listener (inbound HTTP endpoint) |
| 8 | **Terraformer** | Infrastructure as Code (Terraform/Pulumi) |
| 9 | **Metrixer** | Metrics collector (Prometheus/Grafana) |
| 10 | **Diffr** | File/content comparison |
| 11 | **Zipper** | Archive creation (ZIP/TAR) |

---

## Work Style Preferences (for AI assistants)

- When given a broad directive ("Go!", "modify everything"), execute comprehensively across all relevant files without asking for confirmation at each step
- Use parallel subagents to maximize throughput
- Read broadly first, plan the full scope, then execute in parallel batches
- Only ask for confirmation on truly ambiguous architectural decisions
- The developer values robustness ("bullet-proof") and uniformity in system design
- Comfortable with large cross-cutting changes (16+ files in one session)
