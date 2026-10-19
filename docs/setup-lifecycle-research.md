<!-- Tlamatini Author Banner — Angela López Mendoza · @angelahack1 -->
# Windows setup: research and implementation decisions

> Current release: **[v1.87.0](changes/2026-10-18-v1.87.0.md)**. Dated records below retain their original evidence dates.


Research date: 2026-10-11. This is a custom EXE installer, not an MSI package;
MSI guidance informs the design but does not confer MSI transactional guarantees.

## Removal redesign — 2026-10-18, v1.87.0

The reported removal of `C:\Tlamatini` copied 80,186 files (4,899.2 MB) for
recovery, then failed on `Temp\UpdateMedia` with Windows access denied and
restored the payload. This makes ordinary removal perform unnecessary full
copies and hashes. The log confirms restoration completed; it does not identify
the cause of the directory access denial. A working-directory lock is one
possible explanation, not an established diagnosis.

Additional primary sources were consulted before this redesign:

- [Microsoft: Moving directories](https://learn.microsoft.com/en-us/windows/win32/fileio/moving-directories)
  and [MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)
  support moves of directories on the same drive. The new removal transaction
  moves explicit root entries into its recovery folder without copying their
  contents, refuses an occupied destination, and has no cross-drive copy fallback.
- [Microsoft: Rollback installation](https://learn.microsoft.com/en-us/windows/win32/msi/rollback-installation)
  describes reverse operations and the cost of retaining rollback files. Here,
  file identities and a durable journal make a completed move reversible;
  only the small setup-owned metadata files need verified backup copies.
- [NSIS: Rename and RMDir](https://nsis.sourceforge.io/Docs/Chapter4.html)
  documents same-drive directory moves, removal failures when a directory is
  in use as a working directory, and the danger of recursively deleting an
  installation root that contains user files. Removal therefore targets explicit
  entries and never recursively erases the installation root.
- [Inno Setup: UninstallDelete](https://jrsoftware.org/ishelp/topic_uninstalldeletesection.htm)
  warns against broad deletion of user files. The six named content directories
  retain the existing content-preservation contract, and `agents/` is always kept.
- [Inno Setup: Installation order](https://jrsoftware.org/ishelp/topic_installorder.htm)
  separates reversible operations and completion. Tlamatini likewise commits
  application/Windows removal before deleting disposable caches; a locked cache
  cannot initiate a full application restore.

The acceptance target is a measured complete removal within 180 seconds, with
300 seconds as the maximum requested by Angela. Helpers receive bounded waits;
cleanup checks an overall deadline and retains a resumable journal on failure.
A timeout or locked residue is **cleanup incomplete**, never a timing pass.
Windows I/O can itself block; a software deadline is not proof of the requested
elapsed time. Compiled full-package timing and independent preservation checks
are required before release acceptance. Source regressions and UI previews are
separate evidence. No background bulk deletion is used to manufacture a fast
completion result.

Schema 1 installation recovery stays readable. Schema 2 removal recovery tracks
each move before and after it occurs, detects destination collisions, and leaves
its journal until cleanup succeeds. Restoration progress names recovery and
advances even when existing files already match their saved hashes. A successful
restore is durably marked before deleting recovery material, so an interruption
during housekeeping cannot require backup files already removed.

## Primary sources consulted before changing the lifecycle

- [Microsoft: Windows Installer best practices](https://learn.microsoft.com/en-us/windows/win32/msi/windows-installer-best-practices)
  recommends serviceable packages, explicit errors, protection of system resources,
  and testing installation and removal. Keep the existing per-user installation;
  do not introduce elevation or modify Windows-owned resources.
- [Microsoft: Rollback custom actions](https://learn.microsoft.com/en-us/windows/win32/msi/rollback-custom-actions)
  describes retaining replaced files and reversing direct system changes, including
  partially executed actions. Prepare recovery before mutation; persist its state;
  distinguish successful rollback from rollback that needs attention.
- [Microsoft: Rollback installation](https://learn.microsoft.com/en-us/windows/win32/msi/rollback-installation)
  explains the cost of retaining recovery data. Preflight space and retain the
  recovery copy until the operation has completed successfully.
- [Microsoft: Job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
  and [TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
  describe containing helper processes and ending their job on timeout. Avoid
  unbounded waits and killing unrelated processes by name.
- [Microsoft: Restart Manager application guidelines](https://learn.microsoft.com/en-us/windows/win32/rstmgr/guidelines-for-applications)
  explains orderly shutdown and the data-loss risk of forced shutdown. Retain
  Tlamatini's requirement to close the main app normally; only confirmed,
  installation-owned leftover workers may be terminated after consent.
- [Microsoft: Uninstall registry key](https://learn.microsoft.com/en-us/windows/win32/msi/uninstall-registry-key)
  documents application metadata. Keep registration ownership explicit, preserve
  Windows UserChoice and other programs' Open With entries, and do not advertise
  unsupported silent uninstall behavior.
- [Microsoft: Terminating a process](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process)
  and [TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)
  distinguish abrupt termination from normal cleanup: children can survive their
  parent, and termination handlers do not run. The real crash campaign therefore
  records process identities, terminates only the installed server without
  Ctrl+C, waits for its exit, and independently proves that actual agent workers
  survived before the compiled uninstaller is allowed to remove them.
- [Microsoft: Restart Manager resource registration](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmregisterresources)
  and [Restart Manager functions](https://learn.microsoft.com/en-us/windows/win32/rstmgr/functions)
  provide read-only identification of applications holding a file. A persistent
  sharing/access failure gets a bounded five-second retry and a named-file error;
  Restart Manager is queried for diagnostic owners only, never asked to terminate
  an unrelated application. Recovery checks readability before bulk copying and
  still verifies the subsequent copy because an early check cannot eliminate races.

## Audit findings and intended checks

The original installer extracts into the live destination before later helper
steps succeed. It has no file rollback. The shortcut creator has Read-Host error
paths, invokes another scripting host, and can swallow a shortcut failure.
The uninstaller removes shortcuts and registrations before file deletion can
fail. A subprocess timeout alone does not guarantee its descendants stop.
The original fixed-height layouts also clip their action rows; the installer's
body was accidentally conditional on the optional version badge.

The implementation must preserve the existing database migration and backup
contracts, retained API/provider configuration, External MCP configuration,
contacts, user folders and uninstaller preservation rules. Recovery journals
must not contain credentials, execute scripts from a journal, or accept paths
outside the selected installation. Active work cannot be abandoned through the
title-bar close button. Recoverable errors remain inspectable in the window.

## Validation scope

Angela's final requested count is **five complete installations and five
complete uninstallations**, using the compiled standalone clients and a full
local package in disposable destinations. Additional focused checks cover
locked files, failure recovery, interrupted operations, registration ownership,
helper timeouts, missing/corrupt packages, concurrent operations, long/Unicode
paths and GUI scaling. Source UI previews are recorded separately and never
count as complete installations. No claim of invulnerability or full application
release acceptance follows from these focused setup checks.

All development execution is visible on the real desktop, with live transcripts
and Shoter desktop evidence. At the time of this research nothing was committed; the implementation was committed in `880a335e` (2026-10-12) and published in `v1.82.0`.
