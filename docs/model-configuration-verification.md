# Runtime and model configuration verification — 2026-09-20

Installed application: `C:\Tlamatini\Tlamatini.exe`, version **1.63.0**.

## Corrections

- Frozen runtime preparation imports the compiled model registry. Portable helpers come from the resolved agents directory beside the executable. A non-model agent no longer depends on a nonexistent loose source file under `_internal`.
- Runtime failures identify whether template copying or helper refresh failed.
- Monitor-Log, Monitor-Netstat and RecMailer read UTF-8 YAML, including a BOM. The first execution of the new frozen build gate exposed their previous dependence on Windows' default encoding.
- The build now requires the registry and verification command in its compiled archive, executes `check_agent_runtimes` before packaging, and requires their source and tests in self-modification snapshots.

## Executed checks

| Check | Result |
|---|---|
| Original installed executable | Reproduced File-Creator failure at the missing `_internal/agent/agents/model_settings.py` path |
| Source mode, UTF-8 enabled | 89 runtimes prepared; 21 actual YAML/model loaders checked; 3 planning catalogs refreshed; File-Creator wrote exact bytes |
| Source mode, `-X utf8=0` | Same checks passed using Windows' default encoding |
| Newly compiled executable | Same checks passed with bundled Python |
| Frozen staging, source snapshot absent | Same checks passed; execution does not depend on the self-modification snapshot |
| Installed executable in `C:\Tlamatini` | Same checks passed |
| Full wrapped-chat File-Creator | Completed in source and frozen modes, including database registration, subprocess completion and exact output bytes |
| Standalone MCP File-Creator | Completed with system Python and the installed bundled Python |
| Regression suites | 394 distinct tests passed; 5 skipped. Includes model configuration, video analysis, speech agents, planning, self-management, packaging and chat completion |
| Inclusion skills | Both sweeps clean; mirrored instructions synchronized. Source database and collected static are regenerated; optional gallery omission and two documented heavy-asset restore mappings remain intentional |
| Visible installed Models dialog | 38 settings; 6 tabs; Talker voice changed to `jess`, saved and reopened; actual Talker loader read `jess`; original `tara` restored and session reconnected |
| Configuration and database | All original config values preserved; 3 accounts and row counts across all 28 tables preserved before adding the verification run |
| Final source coherence | Installed executable matches the rebuild; corrected portable scripts and critical snapshot files match repository source |

The runtime checks prepare all agent types. They do not execute every external-service, messaging, hardware or desktop workflow. Actual execution checks use harmless File-Creator output; model providers are covered by targeted regression tests and configuration loading here.

## Package and recovery

`Temp/models-build/pkg.zip` contains **77,084 payload files**, with **1,315 source mappings** verified. Every archived file was checked against its SHA-256/size receipt. Size: **1,904,313,181 bytes**, below the 1,990,000,000-byte release limit. Nothing was published remotely.

The executable was freshly compiled. After the new gate caught the three portable readers, those scripts were corrected, the gate passed, and assembly resumed with a fresh sanitized snapshot and complete manifest/package verification. The three portable scripts are not compiled modules in this executable's archive.

Rollback copies and a verified SQLite online backup are retained at:
`C:\Tlamatini\Temp\runtime-implementation-1.63.0-backup`.

At the end of the 2026-09-20 verification, the installed app served `http://127.0.0.1:8000/agent/agent/`. This is dated evidence, not a current process-health assertion. Local diagnostic logs are under repository `Temp/runtime-fix-*.log`; they are untracked operator artifacts, not release prerequisites. See [model configuration](model_configuration.md) for repeatable commands.
