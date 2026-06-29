<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
# DB / Older

This directory is the **archive** of previously-live `db.sqlite3` files
that the start-up swap-in has retired.

## How it works

Each time `manage.py::_apply_pending_db_swap` swaps a new database in
from `../ToLoad/`, the prior live `db.sqlite3` is **moved** here under
a fresh timestamped subdirectory before the new one is promoted:

```
Older/
  2026-05-14_153022/
    db.sqlite3      <-- the database that was live before the swap
  2026-05-14_164410/
    db.sqlite3      <-- and so on, one folder per swap
```

The timestamp format is `YYYY-MM-DD_HHMMSS` (local time), filesystem-safe
on Windows / Linux / macOS.

## Why archives are kept

The swap-in is **destructive** for the previous database (it is moved,
not copied). The Older archive is the only built-in recovery path — if
you change your mind after a swap, copy the archived `db.sqlite3` back
into `../ToLoad/` and restart Tlamatini.

## Housekeeping

Tlamatini never deletes anything from this directory. If swaps become a
regular habit you may want to periodically prune the oldest folders by
hand — but read each `db.sqlite3` is the database that contains all
chat history, agent definitions, sessions, and credentials, so think
twice before deleting any of them.

## Manual restore

To roll back to a previous database:

1. Copy the archived `db.sqlite3` from `Older/<timestamp>/` back to
   `../ToLoad/db.sqlite3`.
2. Restart Tlamatini completely (close the process and launch it again).
3. The swap-in will archive the **current** live database into a new
   `Older/<timestamp>/` folder and promote the copy you just placed.
