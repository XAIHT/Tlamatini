# Tlamatini Nightly Performance Report

## 2026-07-06 07:50:12 -06:00

Automation: `tlamatini-nightly-performance-drive`

Raw logs: `Temp/nightly_perf/20260706_074838/`

### Worktree protection

Initial and final `git status --short` both showed the same pre-existing modified files:

- `Tlamatini/agent/agents/emailer/config.yaml`
- `Tlamatini/agent/agents/recmailer/config.yaml`
- `Tlamatini/agent/agents/telegrammer/config.yaml`
- `Tlamatini/agent/agents/teletlamatini/config.yaml`
- `Tlamatini/agent/agents/whatsapper/config.yaml`
- `Tlamatini/agent/agents/zavuerer/config.yaml`
- `Tlamatini/agent/config.json`

No production source code was modified by this nightly pass.

### Command results

| Check | Command | Duration | Exit | Result |
|---|---:|---:|---:|---|
| Worktree | `git status --short` | 0.203s | 0 | Dirty before run; preserved |
| Source inventory | `git ls-files ...` | 0.341s | 0 | 806 tracked files |
| Large/runtime inventory | `Get-ChildItem -Recurse ...` | 11.282s | 0 | Largest runtime artifacts listed below |
| Compileall | `python -m compileall -q Tlamatini check_private_data.py test_check_private_data.py test_private_data_guard.py test_perf_3x_visual.py` | 0.522s | 0 | PASS |
| Django check | `python Tlamatini/manage.py check` | 3.416s | 0 | PASS |
| Django deploy check | `python Tlamatini/manage.py check --deploy` | 1.876s | 0 | PASS with 6 expected dev deploy warnings |
| Focused 3x harness | `python Tlamatini/manage.py test agent.tests_perf_3x --verbosity 1` | 12.070s wall / 8.216s test time | 0 | PASS, 116 tests |
| Visual 3x dashboard | `PYTHONIOENCODING=utf-8 python test_perf_3x_visual.py` | 7.697s | 1 | FAIL: Ollama unreachable |
| JS lint | `npm run lint` | 2.442s | 0 | PASS with 239 warnings |
| Private-data scanner tests | `python -m unittest test_check_private_data -v` | 2.038s | 1 | FAIL: 4 normalization/fuzzy tests |
| Author banner guard | `python test_author_banner.py` | 0.578s | 1 | FAIL: missing banner in `_version.py` |
| Private-data guard | `python test_private_data_guard.py` | 0.904s | 1 | FAIL: tag, token-shape, scrub placeholder |
| Ollama port/process probe | `Test-NetConnection 127.0.0.1 -Port 11434; Get-Process ollama` | 10.225s | 1 | FAIL: port closed |
| Django import probe | `python -c <django.setup import timing probe>` | 2.787s wall | 0 | PASS; timings below |

### Current measurements

Source inventory:

- 806 tracked files.
- Top tracked extensions: `.py` 451, `.md` 155, `.yaml` 88, `.js` 31, `.jpg` 11, `.css` 9, `.json` 8.

Large/runtime inventory highlights:

- `dist/Tlamatini_Release_v1.36.0_PRIVATE_KEYED_win11x64_20260705_191748.zip`: 1800.70 MB.
- `dist/Tlamatini_Release_v1.36.0/pkg.zip`: 1798.03 MB.
- `python/Lib/site-packages/torch/lib/torch_cpu.dll`: 252.67 MB.
- `python/Lib/site-packages/llvmlite/binding/llvmlite.dll`: 114.79 MB.
- `python/Lib/site-packages/playwright/driver/node.exe`: 79.48 MB.
- Top repo media/runtime duplicates include three copies of `XAIHT-Tlamatini.mp4` at 10.84 MB each.

Django/import timings:

- `total_seconds=2.290`
- `import_django=0.016`
- `django_setup=0.634`
- `agent.views=0.668`
- `agent.rag.factory=0.972`

Visual 3x dashboard:

- L1a keep-alive resolution: PASS, 12 cases.
- L1d warm embeddings: PASS, 1 build vs 60, 59.4x speedup.
- L1b live Ollama serving: FAIL, `/api/version` unreachable.
- L2 orphan reaper O(N): PASS, 8000 procs in 2.92 ms.
- Overall: 3/4 dominant levers verified.

### Prior-run comparison and 3x status

Prior baseline is from the 2026-07-05 automation memory because no previous `Tlamatini_NIGHTLY_PERFORMANCE_REPORT.md` exists in this checkout.

| Path | 2026-07-05 | 2026-07-06 | Change | 3x target status |
|---|---:|---:|---:|---|
| Compileall | 2.805s | 0.522s | 5.37x faster day-over-day, likely warm-cache aided | Reached vs yesterday, but do not treat as stable 3x until cold/warm split is measured |
| `manage.py check` | 3.825s | 3.416s | 1.12x faster | Not reached |
| `manage.py check --deploy` | 3.334s | 1.876s | 1.78x faster | Not reached |
| `agent.tests_perf_3x` wall | 13.812s | 12.070s | 1.14x faster | Not a 3x wall-clock win |
| `agent.tests_perf_3x` test body | 7.775s | 8.216s | 0.95x, slight regression | Not reached |
| Visual warm embeddings | 60.2x | 59.4x | Stable | Reached for this lever |
| Visual reaper scaling | O(N) green | O(N) green | Stable | Reached for this lever |
| Live Ollama serving | Unverified, service down | Unverified, service down | Still blocked | Not reached |
| Startup/import surfaces | `agent.views` total/import picture still not proven 3x; `agent.rag.factory` 2.379s | `django.setup` 0.634s, `agent.views` 0.668s, `agent.rag.factory` 0.972s | Better `agent.rag.factory` timing in this probe, but benchmark shape changed | Not proven 3x |

Conclusion: the 3x objective remains mixed. The harness-level wins are real for warm embeddings and reaper scaling, but startup/check/import paths and live Ollama serving are not fully verified at 3x. Keep the 500+ action security/performance objective active.

### Failures and diagnosis

Visual dashboard and Ollama:

- `test_perf_3x_visual.py` failed only the L1b live serving lever.
- `Test-NetConnection 127.0.0.1 -Port 11434` reported `TcpTestSucceeded: False`.
- `Get-Process ollama` returned no process rows.
- Smallest safe next action: start/restore local Ollama, then rerun only `PYTHONIOENCODING=utf-8 python test_perf_3x_visual.py`.

Private-data scanner:

- 143 tests ran; 4 failed.
- Failing tests: `test_normalized_accented`, `test_accent_insensitive`, `test_spaced`, `test_mixed`.
- Code evidence points to normalization/fuzzy matching in `check_private_data.py`, especially accent replacement, redaction placeholder preservation, and spaced-character matching.
- Smallest safe next action: patch only `_normalize`, `byte_variants`, and `fuzzy_regex` behavior covered by those four tests, then rerun `python -m unittest test_check_private_data -v`.

Author banner:

- `test_author_banner.py` failed `test_banner_in_every_source_file`.
- Missing banner: `Tlamatini/agent/_version.py`.
- Smallest safe next action: add the established Angela author banner to that one generated/version source file, or explicitly exempt it if version files are intentionally generated.

Private-data guard:

- `test_private_data_guard.py` failed 3 assertions and skipped the deep local target scan by design.
- Missing published tag: `v1.31.0`.
- Token-shaped tracked files: `Tlamatini/agent/agents/whatsapper/config.yaml`, `Tlamatini/agent/config.json`, and `Tlamatini/agent/test_image_interpreter_agent.py`.
- Scrub placeholder missing in `Tlamatini/agent/Tlamatini.md`: expected `The project maintainer`.
- Important scope note: two token-shape offenders are currently dirty user-edited config files. Preserve those changes until the user confirms whether they are intentional local secrets/configuration.
- Smallest safe next action: restore/confirm tag `v1.31.0`, sanitize or fixture-mark token-shaped values without exposing secrets, and restore the scrub placeholder in `Tlamatini.md`.

Deploy warnings:

- `manage.py check --deploy` exits 0 but still reports the expected 6 development warnings: `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, weak/insecure `SECRET_KEY`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and `DEBUG=True`.

Lint warnings:

- `npm run lint` exits 0 with 239 warnings and 0 errors.
- 39 warnings are potentially fixable with `--fix`.

### Next recommended implementation batch

1. Restore Ollama and rerun only the visual dashboard to verify L1b live serving.
2. Patch the private-data scanner normalization/fuzzy matching tests without broad scanner rewrites.
3. Resolve the private-data guard separately: tag restoration, token-shaped fixture/config cleanup, and scrub-placeholder repair.
4. Add or explicitly exempt the author banner for `Tlamatini/agent/_version.py`.
5. Add a stable B1-B10 timing probe that separates cold cache, warm cache, `django.setup`, `agent.views`, `agent.rag.factory`, and first live request timing so the broader 3x claim is measured consistently.
6. Only after those blockers are green, profile remaining startup/check import cost. Current bottlenecks are still `django.setup`, `agent.views`, and `agent.rag.factory`, not the already-green warm embedding or reaper levers.
