---
name: project_build_concurrency_guard
description: "build.py error 'FileNotFoundError build/manage/warn-manage.txt' = TWO concurrent builds clobbering shared build/ dist/ work dirs; fixed with a PID lock (.build.lock) in build.py. NEVER run a background build.py while the user may also build."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1a71dd21-db6d-4b82-90fd-ae1bb71f8f48
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-30: A PyInstaller build died with `FileNotFoundError: [Errno 2] No such file or directory: 'C:\Development\Tlamatini\build\manage\warn-manage.txt'` (during `_write_warnings` in assemble). **Root cause = TWO `python build.py` runs in the same dir at once** — I had a background build.py running AND the user started a manual one. build.py cleans `build/` + `dist/` at step 0 ("Cleaning previous build artifacts") AND at end-of-run; whichever finishes first rmtrees the OTHER build's `build/manage` workpath mid-flight → the loser crashes writing warn-manage.txt. It is NOT an asset/build-script bug.

**LESSON (do this every time): NEVER launch a background `build.py` (or build_installer/build_uninstaller) while the user might run one themselves.** A build is ~16-18 min; if you must build, say so and let it be the only build running. Two builds in one repo dir always collide.

**Fix added to `build.py`** (verified in isolation, ruff clean, parses OK): a PID lock `.build.lock` (gitignored). New module-level helpers before `if __name__=='__main__'`: `_pid_alive(pid)` (psutil → Windows ctypes OpenProcess+GetExitCodeProcess STILL_ACTIVE → os.kill fallback; errs toward "alive"), `_acquire_build_lock()` (abort `sys.exit(2)` with a clear message if another build's PID is genuinely alive; reclaim a stale lock from a crashed build; fail-OPEN if it can't write the lock so it never blocks a legit single build), `_release_build_lock()` (removes the lock only if we own it). `__main__` now does `_acquire_build_lock(); try: main() finally: _release_build_lock()` — main() body unchanged, releases even on sys.exit (SystemExit runs finally). 5 isolated tests passed (no-lock acquire / release / stale reclaim / live-other→exit2 / foreign-lock preserved).

**Asset audit of all 3 build scripts (user asked "check again the assets"): 0 real problems.**
- `build.py`: all 25+ referenced source assets exist (icon, --add-data trees templates/static/staticfiles/config.json/prompt.pmt/Tlamatini.md/skills_pkg, README.md, agents_descriptions.md, images/agents/skills_pkg dirs, TlamatiniSourceCode, jd-cli + jd-cli.bat, the 7 support .ps1/.ico/.json + cat_art.py). 0 missing.
- `build_uninstaller.py`: entry `uninstall.py` present; only --add-binary DLLs otherwise.
- `build_installer.py`: entry `install.py` ✓, `pkg.zip` ✓. `Uninstaller.exe` "missing" is EXPECTED — produced by build_uninstaller.py which must run BEFORE build_installer.py (3-step order build.py → build_uninstaller.py → build_installer.py; installer only WARNS if absent). COSMETIC dead code: `_SPLASH_FILE = "splash_installer.png"` (line 30) is defined but NEVER used and `--splash` only appears in a stale comment (line 7) — no actual splash is embedded; `splash_installer.png` legitimately absent. Left as-is (harmless); offered cleanup.

**State after the incident:** the earlier SUCCESSFUL combined build (`bswyu8e5i`) produced the current `pkg.zip` (15:56, 3.1 GB) containing BOTH the [[project_execute_file_foreground_fix]] compiled fix AND the [[project_prompt_catalog_mode_badges]] static — pkg.zip is GOOD and complete; build.py's lock edit does NOT affect pkg.zip. Not committed.
