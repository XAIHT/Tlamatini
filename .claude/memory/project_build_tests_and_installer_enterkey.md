---
name: project_build_tests_and_installer_enterkey
description: "build-script contract tests (test_build_scripts.py, 28) + Enter-key triggers install/uninstall in the Tkinter GUIs"
metadata: 
  node_type: memory
  type: project
  originSessionId: 434332c6-6b89-4961-8110-df04b2046f17
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-26 (not committed):

**Build-script contract tests** — `Tlamatini/agent/test_build_scripts.py` (28 tests, ruff clean, all green via `manage.py test agent.test_build_scripts`). STATIC completeness tests for build.py / build_installer.py / build_uninstaller.py — NOT a real PyInstaller build (multi-GB, no CI). Repo root resolved as `Path(__file__).resolve().parents[2]`. Asserts: all 3 scripts parse; build.py references + on-disk-exists every runtime asset (templates/static/staticfiles/config.json/prompt.pmt/Tlamatini.md/skills_pkg/agents_descriptions.md/README.md/jd-cli); the agents/ pool tree is copied into the install (every workflow agent ships) with STM32er present + each runnable agent has its config.yaml; requirements.txt covers EVERY third-party import across agents/ (AST sweep + import→PyPI alias map + stdlib filter); mcp/pyserial/PDF-backends pinned; build.py `_agent_libs` verify list (AST-extracted) includes mcp/serial/PyPDF2/pypdf/fitz/odf and every entry is pinned; version wiring (extract_cli_version/resolve_build_version/--version-file) in all 3; installer pkg.zip+install.py prereqs + Tlamatini_Release_v naming + _verified_move (SHA-256) + tkinter collect; uninstaller uninstall.py prereq + --onefile + tkinter collect + copies Uninstaller.exe to root.

**Enter-key in installer/uninstaller** — install.py + uninstall.py (Tkinter): bound `<Return>` on `self.path_entry` AND `self.root` to a new `_on_enter_key` handler that calls `_start_install` / `_start_uninstall` (same directory-verify + install/uninstall as the button) and returns `"break"` to avoid double-fire; both `_start_*` are already re-entry-guarded (`_installing` / `_uninstalling`). Not live-tested (Tk mainloop would hang a headless shell); ruff + ast.parse pass.
