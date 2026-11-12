<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Executer: return when the launching script finishes

The installed Spanish Rust-cube run `executer_149_fae77897` started at
14:21:47.846 on 12 November 2026. Its command used `start ... cmd /c` to
launch a 90-second application, waited about three seconds, then ran
`tasklist`. The captured tasklist showed the cube alive, but Executer did
not deliver that already-produced output until 14:23:22.306.

`subprocess.run(capture_output=True)` waited for stdout/stderr pipe EOF.
The detached child shell still held inherited pipe handles after the outer
batch exited. Consequently, the next inspection could arrive only after
the application had closed.

The blocking-script path now captures stdout/stderr in unique regular files
inside the isolated run directory and waits for the direct script process.
It reads a bounded snapshot through separate read handles; it never seeks
the inherited writer handles. Capture paths are logged and files retained.
Direct commands still block; explicit `start` children can outlive the script.
No loop budget, model-based progress decision or new prompt rule was added.

## Same-asset reproduction

Real `executer`, `windower` and `shoter` calls were made through each edition's
existing stdio MCP server. The original Executer source was byte-identical
to the English pre-fix source. The executable was neither rebuilt nor edited:

`C:\Tlamatini-Spanish\applications\dxr_cube_cuda_rust\target\release\dxr_cube_cuda_rust.exe`

SHA-256: `c6e5071412d2477c51d6af7aa184fe064ca85db51fc402487afe27e60498a558`.
Its DXIL shader and CUDA PTX are embedded in the executable.

| Replay | Outer script finished by | Executer observed finished at | Cube alive at result |
|---|---:|---:|---|
| Original source | 5.03 s | 100.50 s | No |
| English fix | 5.05 s | 5.05 s | Yes |
| Spanish fix | 5.06 s | 5.06 s | Yes |

Times are sampled observations. All three runs exited naturally with code 0
and logged completed rendering. The command retained the original application,
90-second argument, `start`, `cmd /c`, ping and tasklist structure. The blanket
image-name kill was omitted, output went to a new owned log, and an outer-exit
marker was added. Original application logs were preserved.

`agent.test_executer_capture` exercises normal START, START /B shared streams,
late output appends, direct-child blocking and nonzero exits with real Windows
processes and explicit synchronization barriers. It uses application-owned
scratch directories and verified native handles for fixture cleanup.

On 12 November 2026, all 65 selected capture, command, window, orphan-cleanup
and watchdog tests passed in each edition. The changed Python files also
passed the fatal-error Ruff checks and the source diff passed whitespace checks.

Evidence is retained under `C:\Development\XAIHT\scratch\cube-loop-20261112`.
These are development-source results, not installed-package acceptance.
The later final-chat-response delivery gap in the original trace is a separate,
unresolved observation: no full draft or live stack was retained to identify it.
