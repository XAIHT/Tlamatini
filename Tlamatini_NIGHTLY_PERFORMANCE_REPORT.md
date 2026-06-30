# Tlamatini Nightly Performance Report

## 2026-06-30 08:00 America/Mexico_City

Automation: `tlamatini-nightly-performance-drive`

Scope: non-destructive performance and health drive. Production source code was not modified. Existing user changes were preserved.

### Worktree State Before Checks

Dirty files already present before this run:

- `Tlamatini/agent/agents/emailer/config.yaml`
- `Tlamatini/agent/agents/recmailer/config.yaml`
- `Tlamatini/agent/agents/telegrammer/config.yaml`
- `Tlamatini/agent/agents/teletlamatini/config.yaml`
- `Tlamatini/agent/agents/whatsapper/config.yaml`
- `Tlamatini/agent/agents/zavuerer/config.yaml`
- `Tlamatini/agent/config.json`
- `Tlamatini/agent/migrations/0164_dedup_zavuerer_setup_wizards.py` (untracked)

### Health And Performance Commands

| Path | Command | Duration | Exit | Result |
|---|---:|---:|---:|---|
| Source inventory | `rg --files` | 0.120 s | 0 | PASS |
| Risk-pattern scan | `rg -n --glob '*.py' ...` | 0.042 s | 0 | PASS |
| Python compile | `python -m compileall -q Tlamatini tlamatini_acpx.py tlamatini_mcp_server.py build.py` | 3.189 s | 0 | PASS |
| Django check | `python Tlamatini/manage.py check` | 7.951 s | 0 | PASS |
| Django deploy check | `python Tlamatini/manage.py check --deploy` | 3.368 s | 0 | PASS with 6 expected deployment warnings |
| 3x hermetic suite | `python Tlamatini/manage.py test agent.tests_perf_3x --verbosity 1` | 16.345 s | 0 | PASS, 116 tests |
| Visual 3x dashboard | `PYTHONIOENCODING=utf-8 python test_perf_3x_visual.py` | 8.794 s | 0 | PASS, 5/5 levers |
| Frontend lint | `npm run lint` | 7.567 s | 0 | PASS with 239 warnings |
| AST parse `views.py` | `python -c "ast.parse(...)"` | 0.754 s process / 0.624 s parse | 0 | PASS |

Notes:

- First visual-dashboard run failed in Windows `cp1252` because box-drawing characters could not be encoded. Rerun with `PYTHONIOENCODING=utf-8` passed. This is a harness environment issue, not a runtime performance failure.
- `npm run lint` produced 0 errors and 239 warnings. The largest categories are unused exported/global ACP helpers and `prefer-const`; not a blocker for this non-destructive run.
- `manage.py check --deploy` warns about local/dev security settings: HSTS, SSL redirect, weak/dev `SECRET_KEY`, secure session cookie, secure CSRF cookie, and `DEBUG=True`.

### 3x Target Status

Baseline/target values come from `surgical_improving_speed_of_Tlamatini_by_a_factor_of_3X.md` section 2.1.

| Measured path | Prior baseline | 3x target | Current | 3x reached? |
|---|---:|---:|---:|---|
| `manage.py check` | 4.501 s | 1.500 s | 7.951 s | NO |
| `manage.py check --deploy` | 2.823 s | 0.941 s | 3.368 s | NO |
| Python core compile check | 0.930 s | 0.310 s | 3.189 s | NO |
| AST parse `views.py` | 0.719 s | 0.239 s | 0.624 s parse | NO; improved only ~1.15x |
| Django + import `agent.views` | 3.542 s | 1.180 s | 3.843 s process | NO |
| Django + import `agent.tools` | 3.147 s | 1.049 s | 2.759 s process | NO; improved only ~1.14x |
| Django + import `agent.consumers` | 5.926 s | 1.975 s | 4.719 s process | NO; improved only ~1.26x |
| Django + import `agent.rag.factory` | 6.059 s | 2.020 s | 3.623 s process | NO; improved only ~1.67x |
| Source inventory | 0.057 s | 0.019 s | 0.120 s | NO |
| Risk pattern scan | 0.102 s | 0.034 s | 0.042 s | NO; close but still above target |
| L1a keep-alive matrix | n/a | Correct default resident pin | PASS | YES |
| L1d warm embeddings singleton | naive 2.425 s / cached 0.041 s | >=3x | 59.6x | YES |
| L1b Ollama reachable | n/a | Healthy serving layer | 39.6 ms `/api/version` | YES |
| L1b serving health | n/a | No source-build race banner | Clean | YES |
| L2 orphan reaper proc-index | O(N²) historical | O(N), <1 s at 8000 | 3.79 ms at 8000 | YES |

Interpretation: the dominant live 3x levers that have harness coverage are verified. The broader startup/check/import paths have not reached the 3x targets and several regressed relative to the 2026-06-28 baseline.

### Inventory

Source inventory excluding `node_modules`, bundled `python`, `.git`, `build`, `dist`, `__pycache__`, and `.ruff_cache`:

- 694 files
- Top extensions: `.py` 432, `.yaml` 87, `.md` 69, `.js` 31, `.jpg` 11, `.css` 9, `.mp4` 6, `.ps1` 6, `.png` 6, `.json` 5

Risk-pattern counts in Python files:

- `json.load`: 311
- `json.loads`: 267
- `yaml.safe_load`: 246
- `sync_to_async`: 41
- `database_sync_to_async`: 29
- `asyncio.create_task`: 15
- `asyncio.to_thread`: 8
- `threading.Thread`: 51
- `queue.Queue`: 12
- `ThreadPoolExecutor`: 7

Large-file/runtime-artifact inventory highlights:

- `dist/Tlamatini_Release_v1.33.0/pkg.zip`: 1985.32 MB
- `Temp/remote_phone_audit_20260627_155314/.../Tlamatini_Release_v1.26.5_win11x64.zip`: 1836.27 MB
- `Temp/remote_phone_audit_20260627_155314/.../Tlamatini_Release_v1.26.1_win11x64.zip`: 1836.26 MB
- `Temp/remote_phone_audit_20260627_155314/.../Tlamatini_Release_v1.26.0_win11x64.zip`: 1836.19 MB
- Extracted historical `pkg.zip` copies under `Temp/remote_phone_audit_20260627_155314`: about 1832 MB each
- Git mirror pack files under `Temp/remote_phone_audit_*`: 78.30 MB each
- Historical source release zips under `Temp/remote_phone_audit_20260627_155314`: about 61-63 MB each
- `Temp/security_perf_ast_inventory.jsonl`: 15.55 MB
- Current duplicated media assets: `Tlamatini/agent/images/XAIHT-Tlamatini.mp4` and `Tlamatini/agent/static/agent/video/XAIHT-Tlamatini.mp4`, each 10.84 MB

### Bottlenecks And Failures

- Startup/check/import surfaces remain the main unmet 3x target. `manage.py check` is 7.951 s against a 1.500 s target.
- Python compile time regressed materially against the prior 0.930 s baseline, now 3.189 s.
- Import process timings remain above target even where improved: `agent.rag.factory` is 3.623 s against a 2.020 s target.
- `views.py` remains very large: 491,989 bytes and 11,926 lines. AST parse is improved but still not 3x.
- Large release archives and extracted historical release payloads in `Temp`/`dist` dominate runtime-artifact footprint and can slow inventories, backups, and broad scans if not excluded.
- Lint has no errors, but 239 warnings indicate frontend cleanup debt. This is not the next performance batch unless lint debt starts obscuring real failures.

### Next Recommended Implementation Batch

Keep the 500+ action security/performance objective active. It is not fully verified complete.

Recommended next batch, pending explicit implementation approval:

1. Add or tighten benchmarks for missing live paths B1-B10 from the surgical plan: chat first-token, path-reference request, reconnect-to-ready, wrapped-agent launch, sidecar fetch, frozen reaper sweep, app startup, Ollama timing, build wall-clock, and DB query counts.
2. Attack startup/check/import cost before more micro-optimizations: profile `django.setup()` and `apps.ready()` to identify synchronous agent scans, migrations/config reads, ACPX/skills startup, and avoidable import-time work.
3. Add scan exclusions or cleanup policy for `Temp/remote_phone_audit_*` and historical release zips so nightly inventories do not repeatedly traverse multi-GB artifacts.
4. Preserve and expand the verified L1/L2 harnesses. The 5/5 visual dashboard is the strongest current evidence that the dominant live levers are healthy.
5. Only after live B1-B10 baselines exist, implement the next surgical batch from the plan: L3 request hot-path caches, L4 access-validation collapse/cache, and L5 sidecar parallelism.

