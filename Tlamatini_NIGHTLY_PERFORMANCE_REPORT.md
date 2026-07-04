# Tlamatini Nightly Performance Report

## 2026-07-04 13:41:32 -06:00

Automation: `tlamatini-nightly-performance-drive`

### Scope and Worktree

- Mode: non-destructive measurement/reporting only. No production source implementation was authorized or performed.
- Initial dirty files preserved:
  - `Tlamatini/agent/agents/emailer/config.yaml`
  - `Tlamatini/agent/agents/recmailer/config.yaml`
  - `Tlamatini/agent/agents/telegrammer/config.yaml`
  - `Tlamatini/agent/agents/teletlamatini/config.yaml`
  - `Tlamatini/agent/agents/whatsapper/config.yaml`
  - `Tlamatini/agent/agents/zavuerer/config.yaml`
  - `Tlamatini/agent/config.json`
- Additional dirty file observed before report write and left untouched: `Tlamatini/agent/doc_generation/complete_project_docs.py`.
- Report status: this file was missing at the start of the run, so comparison used automation memory from the 2026-07-03 run.

### Environment

- CWD: `C:\Development\Tlamatini`
- Python resolution:
  - `C:\Program Files\Python312\python.exe`
  - `C:\Development\Tlamatini\python\python.exe`
  - `C:\Users\angel\AppData\Local\Microsoft\WindowsApps\python.exe`
- Active `python --version`: `Python 3.12.10`
- Tlamatini runtime banner during Django checks: `Tlamatini 1.33.2`
- Ollama check: `Test-NetConnection 127.0.0.1 -Port 11434` returned `TcpTestSucceeded=False`; no `ollama` process was reported.

### Source Inventory

- Tracked files: 799
- Main tracked extensions:
  - `.py`: 444
  - `.md`: 156
  - `.yaml`: 87
  - `.js`: 31
  - `.css`: 9
  - `.json`: 8
  - `.html`: 4
  - `.yml`: 1
- `Tlamatini/agent/views.py`: 503,914 bytes, 10,396 lines.
- `Tlamatini/agent/views.py` AST parse timing: 0.683s.

### Large File and Runtime Artifact Inventory

Largest non-`.git` / non-`node_modules` files observed:

| Size | Path |
| ---: | --- |
| 1845.68 MB | `dist/Tlamatini_Release_v1.33.2_win11x64.zip` |
| 1843.43 MB | `dist/Tlamatini_Release_v1.33.2/pkg.zip` |
| 293.52 MB | `python/Lib/site-packages/torch/lib/torch_cpu.dll` |
| 101.66 MB | `python/Lib/site-packages/llvmlite/binding/llvmlite.dll` |
| 79.48 MB | `python/Lib/site-packages/playwright/driver/node.exe` |
| 73.74 MB | `python/share/ffpyplayer/ffmpeg/bin/avcodec-60.dll` |
| 71.35 MB | `python/Lib/site-packages/cv2/cv2.pyd` |
| 56.55 MB | `python/Lib/site-packages/ctranslate2/ctranslate2.dll` |

Runtime artifact hot spot: `dist/` contains two ~1.8 GB release zip artifacts. Nightly scans should keep explicit exclusions for release payloads when the check objective is source/runtime performance rather than release artifact validation.

### Timed Commands

| Command | Duration | Exit | Result |
| --- | ---: | ---: | --- |
| `python -m compileall -q Tlamatini` | 3.363s | 0 | Pass |
| `python Tlamatini/manage.py check` | 6.551s | 0 | Pass, no issues |
| `python Tlamatini/manage.py check --deploy` | 2.496s | 0 | Pass with 6 expected deployment warnings |
| `python Tlamatini/manage.py test agent.tests_perf_3x --verbosity 1` | 14.199s | 0 | Pass, 116 tests |
| `PYTHONIOENCODING=utf-8 python test_perf_3x_visual.py` | 9.600s | 1 | Fail: Ollama unreachable |
| `npm run lint` | 4.880s | 0 | Pass with 239 warnings, 0 errors |
| `python -m unittest test_check_private_data -v` | 3.233s | 1 | Fail: 4 private-data scanner tests |

Captured outputs are under `Temp/nightly_perf/`.

### Django and Import Timings

| Probe | Duration | Status |
| --- | ---: | --- |
| `django.setup()` | 1.486s | Measured with `DJANGO_SETTINGS_MODULE=tlamatini.settings` |
| `django.setup()` + `import agent.views` | 2.535s total | `agent.views` import after setup: 1.098s |
| `django.setup()` + `import agent.rag.factory` | 4.173s total | `agent.rag.factory` import after setup: 2.758s |
| Raw `import tlamatini.settings` wrapper | 0.154s | Fast settings import |

Raw pre-setup imports of `agent.views` and `agent.rag.factory` fail with `django.core.exceptions.AppRegistryNotReady`, so startup probes must bootstrap Django before timing those modules.

### Health Check Details

- `manage.py check`: passed with `System check identified no issues (0 silenced)`.
- `manage.py check --deploy`: passed but still reports 6 deployment warnings:
  - `SECURE_HSTS_SECONDS` unset
  - `SECURE_SSL_REDIRECT` not true
  - weak/insecure `SECRET_KEY`
  - `SESSION_COOKIE_SECURE` not true
  - `CSRF_COOKIE_SECURE` not true
  - `DEBUG=True`
- `npm run lint`: exit 0, `239 problems (0 errors, 239 warnings)`, with 39 warnings potentially fixable by `--fix`.
- `agent.tests_perf_3x`: passed 116 tests in 8.229s of Django test time.

### 3x Target Status by Measured Path

| Path | Current result | Prior comparison | 3x status |
| --- | --- | --- | --- |
| Compile/import baseline | `compileall` 3.363s | Prior automation memory: 11.809s on 2026-07-03 | Improved vs prior, but not a direct 3x product-path proof |
| Django system check | 6.551s | Prior automation memory: 7.952s on 2026-07-03 | Improved, but 3x not reached/verified |
| Django deploy check | 2.496s | Prior automation memory: 3.262s on 2026-07-03 | Improved, but 3x not reached/verified |
| Focused 3x Django harness | 116 tests pass | Prior run also green | Harness path remains verified |
| L1a keep_alive matrix | Pass in visual dashboard | Prior run green | Verified |
| L1d warm embeddings | 59.6x speedup, 1 build vs 60 | Prior memory about 60.1x | 3x reached |
| L1b Ollama serving | Unreachable on `127.0.0.1:11434` | Prior run had live-path uncertainty tied to local service | Not verified tonight; environment blocked |
| L2 reaper scaling | 8000 procs in 4.13ms, flat/O(N) growth | Prior run green | 3x objective remains satisfied for this lever |
| `agent.views` startup path | 2.535s total with setup | Prior memory flagged views as hotspot | Not verified as 3x reached |
| `agent.rag.factory` startup path | 4.173s total with setup | Prior memory flagged factory as main bottleneck | Not reached; remains main measured import bottleneck |

Overall: the dominant harness levers are still mostly healthy, but the broad startup/check/import paths have not been verified at 3x. The 500+ action security/performance objective remains active.

### Failures and Diagnosis

1. `test_perf_3x_visual.py` failed only because L1b Ollama serving was unreachable:
   - Visual output: `/api/version : UNREACHABLE`.
   - `Test-NetConnection 127.0.0.1 -Port 11434`: `TcpTestSucceeded=False`.
   - Smallest safe next action: restore local Ollama service and rerun only `PYTHONIOENCODING=utf-8 python test_perf_3x_visual.py`.

2. `python -m unittest test_check_private_data -v` failed 4 of 143 tests:
   - `TestByteVariants.test_normalized_accented`
   - `TestFuzzyRegex.test_accent_insensitive`
   - `TestFuzzyRegex.test_spaced`
   - `TestNormalize.test_mixed`
   - Code evidence points to `check_private_data.py` functions `_normalize()`, `byte_variants()`, and `fuzzy_regex()`.
   - Smallest safe next action: implement a focused normalization/fuzzy matcher fix in `check_private_data.py`, then rerun `python -m unittest test_check_private_data -v`.

### Bottlenecks

- `agent.rag.factory` remains the largest measured import/startup bottleneck tonight: 2.758s after Django setup, 4.173s total.
- `agent.views` remains large and nontrivial: 503,914 bytes, 10,396 lines, 1.098s import after setup, 0.683s AST parse.
- Release artifacts in `dist/` are large enough to distort broad scans unless explicitly excluded.
- Lint is not failing, but the 239 warning count remains noise that can hide new regressions.

### Next Recommended Implementation Batch

1. Restore Ollama locally and rerun only the visual 3x dashboard to verify L1b.
2. Patch the private-data scanner normalization/fuzzy matching failure in `check_private_data.py` and rerun `python -m unittest test_check_private_data -v`.
3. Profile `agent.rag.factory` import dependencies after Django setup and move heavyweight optional work behind call-site lazy imports where safe.
4. Add stable B1-B10 live-path timing probes for startup/check/import paths so the nightly can prove or disprove 3x per user-facing path instead of relying mainly on harness levers.
5. Keep release artifact exclusions in nightly source/performance scans; validate `dist/` payloads in the separate release-verification workflow.

