---
name: project_native_picker_tcltk_fix
description: "Server file picker rewritten tkinter-free (Win32 ctypes); tkinter REMOVED from server build. Earlier Tcl/Tk-bundling approach superseded."
metadata: 
  node_type: memory
  type: project
  originSessionId: bcca9652-ff3d-42a9-8039-7ceaa0b68d3b
---

## SUPERSEDED 2026-05-20 — tkinter removed from the server entirely

The Tcl/Tk bundling described further below kept failing for the user (frozen build still showed "Can't find a usable init.tcl", picker dead). Per user request ("get rid of tkinter completely"), the server file picker was **rewritten to NOT use tkinter at all**:

- **New `agent/native_dialogs.py`** — Win32 common dialogs via pure `ctypes`: `pick_open_file` (`comdlg32.GetOpenFileNameW`) + `pick_folder` (`shell32.SHBrowseForFolderW` + `SHGetPathFromIDListW`), STA `CoInitialize`. comdlg32/shell32 ship with every Windows → nothing to bundle, no Tcl/Tk. Non-Windows raises `NativeDialogUnavailable` (graceful → manual entry). Struct classes factored into `_openfilenamew_cls()`/`_browseinfow_cls()` + `_struct_sizes()` test hook (verified x64: OPENFILENAMEW=152, BROWSEINFOW=64).
- **`views.py::_run_native_picker`** — no longer imports tkinter; dispatches to native_dialogs on its existing daemon thread. `_picker_failure_payload` markers updated ("requires windows" etc.).
- **`build.py`** — REMOVED the Tcl/Tk bundling + `--hidden-import=tkinter/_tkinter`; ADDED `--exclude-module=tkinter,_tkinter` so Tcl/Tk can never be dragged in. Simpler/smaller server build; the init.tcl failure is now impossible on the server.
- **Tests** — deleted `test_tkinter_availability.py`; added `test_native_dialogs.py` (24 tests: struct sizeof, Win32 symbol resolution, dispatch, endpoints, no-tkinter AST scan, build.py-has-no-tkinter). All pass; ruff clean; eslint 0 errors. Reaper tests still 22 OK.
- **install.py / uninstall.py / build_installer.py / build_uninstaller.py LEFT ALONE** — those are the SEPARATE Tkinter Installer/Uninstaller GUI exes; they build & bundle their own Tcl/Tk and work. Only the SERVER dropped tkinter.
- **requirements.txt** — tkinter comment rewritten: server no longer needs it; installer GUIs still do.
- Manual test (source mode, instant, no rebuild): `python -c "import sys; sys.path.insert(0,'Tlamatini/agent'); import native_dialogs as n; print(n.pick_open_file('Pick a file',[('All','*.*')]))"` → native dialog pops, returns chosen path.

The historical Tcl/Tk-bundling notes below are kept for context but are no longer the implementation.

### Foreground fix (2026-05-20, same day) — picker opened behind the browser / only in taskbar
The Win32 dialogs opened behind the browser and only blinked in the taskbar, because the server is a BACKGROUND process and Windows denies it foreground activation. Added `native_dialogs._force_window_foreground(hwnd)`: (1) `SetWindowPos(HWND_TOPMOST)` — pure z-order, needs no focus rights, so the dialog is drawn ABOVE the browser regardless (this is the guaranteed-visibility part); (2) `AttachThreadInput` dance + `SetForegroundWindow` to also grab focus. Wired in via the folder browser's `BFFM_INITIALIZED` callback (clean — gives the dialog HWND) and, for `GetOpenFileNameW` (no init callback), a 5s daemon **watcher thread** that finds the picker thread's visible top-level window (`EnumThreadWindows`) and raises it. Fail-open, never breaks the picker. Tests: 26 in test_native_dialogs.py (added ForceForegroundHelperTests). Manual: `python -c "import sys; sys.path.insert(0,'Tlamatini/agent'); import native_dialogs as n; print(n.pick_folder('Pick a folder'))"` → folder dialog now appears in front.

---

2026-05-20: The Set-DB / Backup-DB **Browse** buttons (server-side native tkinter picker, `agent/views.py::_run_native_picker`) failed in the frozen build with a browser alert: *"Could not open the file picker. Can't find a usable init.tcl in … _MEI…/_tcl_data …"*.

**Root cause:** `build.py` only passed `--hidden-import=tkinter/_tkinter` (bundles the Python modules + Tcl/Tk DLLs) but **never set `TCL_LIBRARY`/`TK_LIBRARY` nor bundled the Tcl/Tk *data* tree** (init.tcl, tcl8.6/, tk8.6/). PyInstaller's runtime hook `pyi_rth__tkinter` still sets `TCL_LIBRARY = _MEIPASS/_tcl_data` at startup, but that dir was empty → init.tcl not found. `build_installer.py` already set these env vars (which is why its frozen tkinter GUI works); `build.py` had the gap.

**Diagnostic note:** the running frozen Tlamatini.exe is **onefile** (`_MEI<digits>` temp extraction) and leaks `TCL_LIBRARY=_MEIPASS/_tcl_data` into child processes (inherited by the shell hosting this session). This is process-scoped only (User/Machine env are empty) and harmless once the data is bundled, but it breaks `tkinter.Tcl()` for any other Python launched as a descendant. Pool agents run via system Python and inherit it too — fine today since no agent uses tkinter.

**Fix:**
- `build.py` (step 4a): resolve Tcl/Tk dirs from `sys.prefix`/`sys.base_prefix` (gated on `init.tcl` existing), set `TCL_LIBRARY`/`TK_LIBRARY`, AND explicitly `--add-data` the trees to `_tcl_data`/`_tk_data` (the exact dest the runtime hook reads). Mirrors `build_installer.py`. Plus a **post-build verification** (step 5a) that `rglob("init.tcl")` in `dist/manage` and prints a loud WARNING if missing — catches regressions at build time.
- `views.py`: new `_picker_failure_payload(exc)` classifies picker errors via `_PICKER_UNAVAILABLE_MARKERS` (init.tcl / no tkinter / no display / TclError) → returns `{path:"", error:<raw>, message:<friendly>, picker_unavailable:bool}`. Both `pick_db_sqlite_file_view` / `pick_backup_directory_view` use it.
- `agent_page_init.js`: new `_notifyPickerUnavailable(body, fallbackReason, inputEl, kindLabel)` — on `picker_unavailable`, focuses the manual path field + sets a "type the full path here" placeholder instead of dumping the raw Tcl error. Both Browse handlers use it.

**Tests:** extended `agent/test_tkinter_availability.py` (now 47, all pass with stale TCL_LIBRARY cleared) — build.py TCL_LIBRARY/`_tcl_data`/init.tcl-check assertions + `PickerFailurePayloadTests` + `PickerUnavailableEndpointTests`. Ruff clean, ESLint 0 errors.

**User must rebuild** (`build.py`) for the frozen Browse button to work; manual path entry already works and is now the friendly fallback. Separate from [[project_reaper_console_window_fix]].

**Empirically verified (2026-05-20):** built a minimal probe (`tkinter.Tk()` + `filedialog`) with the exact build.py flags (TCL_LIBRARY env + `--add-data _tcl_data/_tk_data` + hidden-imports) in BOTH PyInstaller 6.18 onefile AND onedir. Both ran `PROBE_OK` (init.tcl resolved from the bundled `_tcl_data`) even with a stale bogus `TCL_LIBRARY` injected — the runtime hook `pyi_rth__tkinter` overrides env and reads `_MEIPASS/_tcl_data`. `--add-data _tcl_data` does NOT collide with the stock hook (no build error). Source mode unaffected (build.py never runs; system tkinter self-resolves). NOTE: the user's running frozen build is **onefile** (`_MEI…`), but current build.py is **onedir** — both work.

**requirements.txt completeness pass (2026-05-20):** dependency audit (AST scan of agent + build scripts vs requirements) found used-but-undeclared packages. Changes: pinned `psutil==7.2.2` (was unpinned; reaper dep), added `pypdf==6.10.0` (PDF fallback) + `reportlab==4.4.10` (doc pipeline), added File-Extractor optional format backends `striprtf`/`odfpy`/`ebooklib`/`xlrd` (RTF/ODT/EPUB/legacy-.xls were silently failing — guarded try/except imports, not installed anywhere). Skipped deprecated `PyPDF2` (pymupdf+pypdf cover PDF). Documented tkinter as a STDLIB requirement (not pip-installable) in a comment block. `pip install --dry-run` confirmed no conflicts (only new transitive: defusedxml via odfpy). lxml/six/pillow already present.
