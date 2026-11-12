# Torrenter recovery and truthful status — 10 November 2026

Release recorded for this 2026-11-10 change: **1.92.4**. This record covers development
corrections and their verification; it does not certify a new installed package.

## What changed

- A completed download whose peer session is stopped or paused still reports
  `completed`. `desired_state` retains the user's intent. An older service's stale
  verification message becomes `previous_error`; a current failure or failed
  delivery remains visible.
- Status and list results include `download_complete`, `restart_action` and
  `recovery_note`. Use Start for an incomplete stopped download, Resume for a
  paused one, and Recheck for a failure. Read the latest revision before writing.
- Workspace controls apply only to eligible selections and report skipped jobs.
  Completed downloads cannot be started or cancelled again. Their stopped file
  selection and source-list controls remain available. Recheck verifies retained
  pieces; Reseed explicitly enables sharing again.
- The workspace retries an empty or truncated session JSON response at most
  twice, with 200 ms between attempts. It never automatically repeats torrent
  mutations. Existing login, CSRF and account boundaries remain in place.
- The activity log includes recovery guidance and distinguishes historical and
  current errors. `Tlamatini.md` teaches the same rules to the chat agent.

## Coordinated Tlachihuani Jobs changes

The service still allows two active transfers per account and four per host.
After 180 seconds without payload progress, a transfer yields its slot only when
another eligible queued download is blocked. Partial files and running intent
remain intact. It waits at least 60 seconds and retries behind waiting work.
Stopped, paused, checking, verifying and finished transfers are not rotated.
Metadata discovery has its own queue; these are different limits.

Before SHA-256 publication, Jobs waits for libtorrent's disk-complete pause
acknowledgment, with a bounded 60-second failure. Label/revision edits preserve
that acknowledgment. Rapid Stop/Start completes release of the previous handle
before reopening it. Recheck clears the current failure and validates retained
pieces without deleting partial files.

These engine changes require a **separate Jobs service update**. Updating only
Tlamatini does not activate them. This work did not build, install, restart the
installed services, change the live queue, or commit anything.

## Installed diagnosis, separate from source tests

The read-only observation of Angela's account on 10 November found 24 records:
21 finished downloads and three unfinished jobs. All **432 delivered files** in
the finished jobs independently matched their manifest SHA-256 values. One
finished job appeared stopped, and another retained an obsolete verification
error. Neither condition proved a missing delivered file.

Two unfinished jobs were intentionally stopped (0% and approximately 61%); the
third was waiting for peers at 0%. Reported seed counts are not connected seed
counts. Restarting cannot guarantee that peers return, and testing a UDP tracker
port with a TCP connection does not establish its health. The historical disk
race is plausible from the code; the exact writer behind that old error was not
established from the available logs.

## Verification and reproduction

- **64 automated checks passed:** 12 engine recovery tests, 2 magnet-queue tests,
  8 delivery tests, 30 table tests, and 6 client tests in each edition.
- The recovery suite completed **four real BitTorrent payload transfers** from
  controlled local peers while two silent swarms competed for slots. Saved bytes
  and SHA-256 matched independently. Its scheduling timers are shortened only
  inside the test; production defaults remain 180/60 seconds.
- **48 headed Chrome checks passed** across both source workspaces, authenticated Django and the
  Jobs API/journal with isolated QA records: recovery actions, session-read retry,
  all twelve sortable columns, keyboard access, filters, saved views, account
  isolation and 1600/390/320-pixel layouts. Historical UI fixtures are not evidence
  of downloading; the peer test provides that evidence.
- Python Ruff checks passed for changed client/activity/tests and Jobs code.
  JavaScript ESLint passed for the workspace in both editions.

Run from a verified visible development console, using the prepared Python
environment and application-owned scratch directories:

```powershell
# From this edition's Tlamatini Django directory:
python -m unittest agent.test_torrenter_recovery -v
# From the separate Tlachihuani checkout, with its private libtorrent runtime:
python tests/integration/test_transfer_recovery.py
python tests/integration/test_magnet_queue.py
python tests/integration/test_delivery.py
node --test tests/unit/workspace_table.test.cjs
python tests/desktop/torrenter_table.py --output artifacts/verification/torrenter-recovery --english C:\Development\XAIHT\Tlamatini --spanish C:\Development\XAIHT\Tlamatini-Spanish
```

The workstation evidence is retained under
`C:\Development\XAIHT\Tlachihuani\artifacts\verification\torrenter-state-20261110`:
`session.log`, suite logs, `visual/results.json`, `visual/SUMMARY.html`, desktop
screenshots and `download-file-checks.json`. It is local verification evidence,
not a release payload or proof of an upgraded installed executable.

See the [Torrenter operating guide](../torrenter.md).
