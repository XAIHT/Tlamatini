---
name: project_carried_python_for_agents
description: Frozen installer now ships its OWN Python 3.12.10 for pool agents; agents ALWAYS use it (no system Python needed)
metadata: 
  node_type: memory
  type: project
  originSessionId: 47b36155-df46-4343-a841-b1ae71269bf8
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-05: Fixed a real architectural hole — the frozen installer assumed the end user already had Python 3.12.10 + all `requirements.txt` deps + `PYTHON_HOME`. The `Tlamatini.exe` is self-contained, but **every pool agent (~74) is launched as a SEPARATE subprocess** via `get_python_command()` / `_resolve_python_executable()`, which needed an EXTERNAL python. The installer never provided one → on a clean machine NO agent could run.

**User's hard requirements (emphatic):** pool agents must ALWAYS, no matter what, use the Python CARRIED inside Tlamatini's installation; the carried version is EXCLUSIVELY 3.12.10. Chosen approach (AskUserQuestion): "ship a Python+deps inside the install dir."

**Implementation (two halves):**
1. **build.py** `bundle_carried_python()` copies a VERIFIED Python 3.12.10 (full install, NOT venv, deps importable) into `dist/manage/python/`. `_probe_carried_python` ABORTS the build unless source is exactly `CARRIED_PYTHON_VERSION=(3,12,10)`, non-venv, can `import yaml,langgraph,langchain,requests`. Ships to `<install_dir>\python\` automatically via the existing `os.walk(dist_manage)` → `pkg.zip` → `install.py` extractall pipeline — **NO install.py/build_installer.py change needed**.
2. **Resolvers** rewritten to prefer `<install_dir>\python\python.exe` FIRST, immune to PYTHON_HOME: the shared helper **`get_user_python_home()` (62 agents + views.py)** returns the carried dir in frozen mode (flows into get_python_command + get_agent_env PATH); `cleaner.py` (no helper) + 3 app-side resolvers (`tools.py` ×2, `chat_agent_runtime.py`) patched directly. Patched via an AST line-span patcher (the 62 agents had 16 cosmetic variants of get_python_command but identical logic; rewriting the single shared helper was the lever). Proven by functional test: carried python wins even vs a hijacked PYTHON_HOME; falls back gracefully if missing; dev mode unchanged (sys.executable).

**Contract (do NOT weaken):** carried interpreter is EXCLUSIVELY 3.12.10 and the mandatory first-choice for pool agents in frozen mode. Never re-introduce PYTHON_HOME/PATH preference ABOVE the carried path; never relax the build preflight (only guarantee the shipped python has deps).

**Playwright browsers also carried (2026-06-05 follow-up):** the carried python copies site-packages but Playwright browsers live in `%LOCALAPPDATA%\ms-playwright` (OUTSIDE site-packages) → Playwrighter+Googler would fail on a clean machine. Fix: `build.py::bundle_playwright_browsers()` copies them to `dist/manage/ms-playwright`; `manage.py::_pin_playwright_browsers()` (frozen) exports `PLAYWRIGHT_BROWSERS_PATH=<install_dir>\ms-playwright`, inherited by the in-process Googler AND every spawned agent (os.environ.copy). 2 more contract tests (9 total in CarriedPythonContractTests).

**Java + Git also carried (2026-06-05 — "carry ALL the things, size doesn't matter"):** J-Decompiler needs Java; Gitter (bare `git`) + STM32er MCP git-clone need Git. `build.py::bundle_java_runtime()` copies $JAVA_HOME (or `which java`) → `dist/manage/jre`; `bundle_git()` copies the Git-for-Windows root (resolved via shutil.which, has cmd+mingw64) → `dist/manage/git`. `manage.py::_pin_bundled_tools()` (frozen) sets `JAVA_HOME=<install>/jre` + prepends `jre/bin`, `git/cmd`, `git/mingw64/bin`, `git/usr/bin` to PATH (inherited by all agents). `jd-cli/jd-cli.bat` REWRITTEN: removed the dead hardcoded `JAVA_HOME=D:\devenv\...GlassFish...`, now resolves ambient JAVA_HOME or `%~dp0..\jre` and runs `java -jar "%~dp0jd-cli.jar"`. De-Compresser .7z uses py7zr (carried lib) — no external 7z. Build-machine resolvers verified (found C:\jdk-21.0.10 + C:\Program Files\Git). 42 build-script tests total.

**GENUINELY external (cannot/should-not bundle — document as prereqs):** Ollama LLM server + models (the backend; user installs+pulls), STM32CubeIDE (STM32 compiler/IDE — user installs), firmware toolchains gcc-arm etc. (self-download at runtime via pio/arduino-cli — network), remote infra targets for Dockerer/Kuberneter/Ssher/Scper/Sqler/Mongoxer (client agents to USER infra), Kalier's MCP-Kali-Server (remote Kali box), ACPX external coding CLIs claude/codex/gemini/... (user-installed by design).

**Takes effect only after a fresh `python build.py` + reinstall** — the carried `python/` cannot be hot-copied into an existing frozen `C:\Tlamatini` (must come from pkg.zip). 37 build-script tests pass (incl. 7 new `CarriedPythonContractTests`); ruff clean. Docs: `docs/claude/recent-fixes.md` (2026-06-05) + README §2.1 prereqs (installer users no longer need Python). Not committed (user owns git writes). Related: [[project_build_concurrency_guard]] (don't run a background build.py — ~18 min, collides).
