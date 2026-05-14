# DB / ToLoad

This directory is the **drop zone** for replacing Tlamatini's live SQLite
database on the next start-up.

## How it works

Each time Tlamatini boots, `manage.py::_apply_pending_db_swap` runs
*before* Django is imported (so before any connection is opened to the
live database). The swap-in performs three steps, only when a file
named exactly `db.sqlite3` is present in this directory:

1. A timestamped subdirectory is created under `../Older/`:
   `../Older/YYYY-MM-DD_HHMMSS/`.
2. The current live `db.sqlite3` is **moved** (not copied) into that
   subdirectory so it can be recovered later.
3. `ToLoad/db.sqlite3` is **moved** on top of the live database path.

After the swap, Tlamatini continues its normal start-up against the
freshly promoted database. Because the moves consume the source, a
second run with no file in `ToLoad/` is a no-op.

## How to use this directory

There are two supported ways to place a `db.sqlite3` file here:

1. **From the chat UI**: menu `DB -> Set DB`. The dialog validates the
   file path (live, server-side) and copies the file here for you.
2. **Manually**: drop your own `db.sqlite3` here; the filename must be
   exactly `db.sqlite3` (lower-case). Subdirectories and other file
   names are ignored.

After the file is in place, **fully restart Tlamatini** (close the
process and start it again) so the swap-in window can run. A simple
"Reconnect" is not enough — the swap-in only runs on a brand-new
process.

## What NOT to do

- Do not place a `.db`, `.sqlite`, or arbitrarily-named SQLite file
  here — the swap-in matches on `db.sqlite3` only.
- Do not edit, lock, or open the file while Tlamatini is starting; on
  Windows the move will fail and the swap will be skipped with a log
  line in `tlamatini.log`.

## Audit trail

Every successful swap leaves the **previous** `db.sqlite3` in
`../Older/<timestamp>/`. To roll back, copy the archived file back to
this directory and restart Tlamatini again.
