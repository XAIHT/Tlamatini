<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Required runtime files: packaging repair and verification

Verified on 2026-09-27 in visible foreground PowerShell consoles, retained with
`-NoExit`. Every workload first confirmed its console was visible, foreground
and not minimized. No Git command, commit, live update or database operation
was executed.

## Failure and repair

The build stopped while creating the verified runtime receipt:

```text
Frozen release lost or changed a required source asset: chat_voice_settings.py
```

`build_runtime_assets.ROOT_SOURCES` required the worker's loose settings helper,
but `build.py` maintained a separate required-file copy dictionary that omitted
it. A compiled `agent.chat_voice_settings` module alone cannot satisfy the
standalone Whisperer worker running under carried Python.

`build.py` now calls `copy_root_sources(repo_root, dist_manage)`. The copier uses
the verifier's inventory directly, checks all inputs before copying, creates
destination directories and copies source bytes. The pre-freeze hash baseline
still rejects files changed during a build. Required receipt entries now include
every `ROOT_SOURCES` destination, so both ZIP and extracted update verification
reject a missing helper even if someone also removes it from the receipt.

The self-update sweep understands this carrier and offers explicit `--no-git`
working-file checks. Normal sweeps retain their tracked-file/history checks.
The self-modify sweep includes the same inventory in its build-input census;
snapshot validation already checks every runtime source input. Both `.claude`
and `.gemini` skill/script mirrors document the shared contract.

## Verification results

| Check | Result |
| --- | --- |
| Focused build, root-asset, panel-carriage, self-update, self-modify, preservation, security-carriage and pip-policy suite | 146 tests run: 145 passed, 1 skipped; exit 0 |
| Actual build carrier invoked against source files | Every mapped destination matched its source bytes |
| Newly declared root asset | Copied without editing another build list |
| Missing/empty input and source changes during freezing | Refused |
| ZIP creation, verification, extraction and staging verification | Passed using real carried source files and synthetic runtime binaries |
| Packaged Whisperer worker import | Resolved `chat_voice_settings.py` from the staged installation root |
| Missing helper, edited helper, extra unmanifested file | Rejected by package and staging verifiers |
| Every root destination removed from a receipt | Rejected, including otherwise self-consistent receipts |
| Self-modify receipt | Required snapshot markers/build helpers and both identity copies |
| Self-update inclusion sweep with `--no-git` | No findings; source/vendor, preservation and pre-shutdown integrity wiring passed; exit 0 |
| Generated self-modify snapshot | 1,579 files, 33.08 MB, 11 redacted files, zero copy errors; exit 0 |
| Snapshot runtime carriage | All 778 runtime source inputs carried or explicitly restore-mapped |
| Snapshot redaction and rebuild instructions | Passed; optional gallery omission and regenerated collected static explicitly reported |

The dependency test now recognizes `chat_voice_settings` as a carried local
module, rather than a missing pip dependency. The skipped test uses a Git-based
repository dependency census; fresh-clone/public-release tests that require
Git were excluded. An audit hook blocked all real subprocess creation inside
the file-only Python verification harness, including a Git-dependent check
encountered in the initial test attempt. The initial harness also required
isolation of the pure `rag.config` module from application model initialization;
the successful run tested its real functions without starting app services.

## Evidence and limits

Local transcripts and workload logs are under
`Temp/build-voice-asset-fix/`: `verification3-*`, `update-audit-*` and
`snapshot-audit-*`. The inspected source snapshot is retained at
`Temp/_self_modify_sweep_a2lgn7tg/`. These are local development evidence,
not release artifacts.

This verifies copying, receipt enforcement, update wiring and generated rebuild
inputs. It does **not** certify a newly frozen executable or a complete installer:
no full PyInstaller release/rebuild, live update swap or Git-history census ran.
The normal build path uses Git and was not invoked under the user's prohibition.
No failed/partial package was promoted. Existing installations need a normal
rebuild/update to receive the fix; source changes alone do not update an exe.

For future development checks, use a verified visible forked foreground console,
keep it open afterward, and monitor its live output. Use the update sweep's
`--no-git` only when that limitation is required and report the omitted coverage.
