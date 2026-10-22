# OOB_shift_reaper and NAMU - v1.90.0 source review

Created by Angela López Mendoza · @angelahack1.
Reviewed against source d274f89c, 2026-10-22; tag v1.90.0 resolves to ebc5c3b4.

## 1. Two lifecycle boundaries

OOB_shift_reaper governs long-running reconnaissance during an ordinary application run.
NAMU is the priority reconnaissance cleanup in AgentConfig.ready()'s shutdown path.
These are different boundaries: a grace window during a run does not grant permission
to outlive the owning application.

Nmapper and Discoverer stream subprocess output. Their runner treats a live process
as possibly hung after startup grace and hang_detect_idle_seconds without output.
Before the free-run threshold it logs a warning and continues. After that threshold,
a still-hung process is tree-killed and partial output is retained. A process that has
already exited is drained and reported as finished. A process producing output is
not killed merely because this particular OOB threshold has elapsed.

The condition is elapsed > OOB_shift_reaper, evaluated by the polling loop.
“Exactly second 3601” is an illustration, not a scheduling guarantee.
Other explicit user cancellation, operating-system failures or application shutdown
remain independent causes of termination.

## 2. Agent-specific behavior and settings

Nmapper and Discoverer use _run_cmd_oob in their own agent modules. The default
OOB_shift_reaper is 3600 seconds and the default hang_detect_idle_seconds is 120.
A no-output interval is an operational heuristic, not proof that a scan is deadlocked.
Startup grace and logging cadence belong to the runner. Setup/bootstrap/meta commands
can retain their own shorter timeouts. User-specified scanner limits remain relevant.

Kalier is different: its request waits over HTTP for a remote Kali service. It cannot
stream that remote scan through these local runners. The source uses OOB_shift_reaper
as the HTTP wait budget, with 3600 as its default. Remote service timeouts and remote
process lifetime are controlled by the Kali host. Raising the local wait does not
raise a remote server cap, and closing a local HTTP client does not prove remote
execution stopped.

Primary source locations: agents/nmapper/nmapper.py::_run_cmd_oob;
agents/discoverer/discoverer.py::_run_cmd_oob; agents/kalier/kalier.py.
Use function names instead of historical line numbers, which change between releases.

## 3. Shutdown cleanup: scope and limits

apps.py::namu_kill_recon_gods runs first in cleanup_pool_on_shutdown. It chooses
the pool root according to source versus frozen mode, enumerates local processes,
matches pool paths and the nmapper/discoverer/kalier names, and invokes recursive_kill.
It attempts descendants and then parents, tolerating disappeared processes and access
denials. The broader cleanup also handles other tracked processes.

The priority is unconditional with respect to the OOB elapsed-time window. It is
not an absolute guarantee of instantaneous cleanup: process enumeration, permissions,
races and forced termination of the application can prevent normal cleanup code
from completing. In particular, the local cleanup cannot certify that a remote Kali
service killed its scan. The previous design's universal “every child instantly”
wording described intent more strongly than the implementation can prove.

This document reviews source behavior. It does not claim a new shutdown stress test,
remote cancellation test or frozen-package acceptance.

## 4. Relationship to Terminater and Interactor

Terminater owns real terminal sessions through TerminalHub. Reapers consult
terminal_hub.live_pids(); closing a browser page does not itself kill the shells.
Terminal lifetime and its own hung-command/user-takeover controls are separate from
the reconnaissance OOB grace window.

Interactor is a module, not an agent process or terminal. It operates the live editor
through an authenticated browser bridge. It reads unsaved text, types short teaching
segments and hands fields to the user. User input, Stop and disconnect interrupt
typing while preserving the prefix; hidden tabs pause with a bounded recovery period.
It does not run the edited code, and editing does not implicitly save a file.

Native canvas Save As writes to a user-selected local destination outside Downloads,
using revision checks and account/session-bound capabilities. These editor mechanisms
do not change NAMU or database backup/restore.

Related contracts: docs/terminater.md, docs/interactor.md, docs/canvas-editing.md and
docs/changes/2026-10-22-v1.90.0.md. The complete architecture and summary dossiers
describe the broader application and distinguish source evidence from installed tests.
