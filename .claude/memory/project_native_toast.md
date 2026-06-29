---
name: project-native-toast
description: Notifier toast/desktop-popup experiment was REMOVED entirely (never worked); only the Windows "Installed apps" registration was kept.
metadata:
  node_type: memory
  type: project
  originSessionId: 65ac72ed-17ef-4daa-aed8-e8852de637ef
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

**2026-05-30: the Notifier "toast"/native-desktop-popup experiment was REMOVED COMPLETELY** at the user's explicit request — it "never worked" and burned a lot of effort/tokens. **Do NOT re-introduce any desktop/OS-toast notification surface for the Notifier.** History (all gone): first a WinRT/OS toast (`native_toast.py` + PowerShell 5.1 + HKCU AUMID + `tlamatini:` focus protocol), then a self-drawn pure-ctypes Win32 top-most popup (`toast_popup.py`). Neither was reliable — an *unpackaged* app's banners get silently dropped by Focus Assist / DND / throttling even when `Show()`=ok, and the self-drawn window was abandoned too. The Notifier is back to its single, reliable surface: it drops `notification.json`, the chat UI polls it and renders an in-page popup (+ optional `.wav`).

**Removed:** `agent/native_toast.py`, `test_native_toast.py`, `agent/agents/notifier/toast_popup.py`, `test_toast_popup.py`, `static/agent/img/Tlamatini.png`, the `apps.py` icon-export / `native_toast.register_all()` blocks, the `build.py` PNG copy, and all toast config keys (`native_toast`/`toast_title`/`toast_image`/`toast_seconds`/`toast_click`). `agent/agents/notifier/notifier.py` + `notifier/config.yaml` were restored byte-identical to their pre-toast state (commit `a300710`). Toast doc mentions scrubbed from `agents_descriptions.md`, `docs/claude/agents.md`, `docs/claude/recent-fixes.md`, `BookOfTlamatini.md`, `KIMI.md`. (`manage.py`'s `SetCurrentProcessExplicitAppUserModelID` AUMID stays — that's **taskbar** identity, never part of the toast.)

**KEPT — separate, independent feature the user wants: Windows "Installed apps" / Control-Panel registration.** `agent/windows_app_registration.py` (+ `test_windows_app_registration.py`) writes the per-user HKCU ARP key `Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini` (→ `Uninstaller.exe`). `install.py::_register_programs_entry` writes it, `uninstall.py::_unregister_programs_entry` deletes it, `apps.py` `windows_app_registration.self_heal_for_frozen()` self-heals it on every **frozen** launch (HKCU/non-admin; no-op in source mode).

**Also unrelated, untouched/kept:** the prompt-catalog rectangle badges (`tools_dialog.js`/`.css` — see [[project_prompt_catalog_mode_badges]]) and the `execute_file` foreground fix in `tools.py`/`tests.py` (see [[project_execute_file_foreground_fix]]).

**"Performing system checks..."** in `tlamatini.log` is **Django's standard `runserver` startup output** — NOT toast code, NOT something we wrote. Left in place (removing it would mean disabling Django's own system check).

Status: source-tree edits, ruff clean, `apps.py`+`notifier.py` compile, no broken imports. NOT committed (user owns git — [[feedback_user_owns_git]] / [[feedback_main_branch_only]]). Frozen `C:\Tlamatini` still carries the old toast (Python is baked into the PYZ inside `Tlamatini.exe`) → a `python build.py` is the eventual step to ship the cleanup there.
