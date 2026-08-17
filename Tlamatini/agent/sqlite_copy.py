# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""WAL-safe SQLite copying + sidecar hygiene — what "Backup database" and
"Set DB" must use instead of a plain file copy.

WHY THIS EXISTS (Angela, 2026-08-16)
------------------------------------
``tlamatini/settings.py`` turns the database into **WAL mode**
(``PRAGMA journal_mode=WAL``) and says so in a comment right there:

    "Under WAL, back up with sqlite3's online backup API, never a plain
     file copy."

Both DB menu options were written before WAL was switched on and were never
updated, so both did ``shutil.copy2(db.sqlite3)`` — and under WAL that is
**wrong in both directions**:

* **Backup database** copied ONLY ``db.sqlite3``. Every change committed
  since the last checkpoint lives in ``db.sqlite3-wal``, so the backup was a
  snapshot of an older database while the dialog reported success. Measured
  on Angela's live install: ``db.sqlite3`` 839,680 bytes last written at
  13:39, ``db.sqlite3-wal`` **3,514,392 bytes** last written at 22:49 — nine
  hours of work outside the "backup".

* **Set DB** dropped the chosen file over ``db.sqlite3`` but left the OLD
  ``-wal`` / ``-shm`` beside it. SQLite then replays that stale WAL on the
  next open, so the pages it carries **override the database that was just
  loaded** — the user gets the old data back (or a mixture of two databases,
  which is real corruption). That is why Set DB appeared to do nothing when
  run three times in a row.

WHAT THIS MODULE GUARANTEES
---------------------------
1. **A copy is COMPLETE.** ``consistent_copy`` uses SQLite's online backup
   API, which reads through the WAL, and then puts the copy in ``DELETE``
   journal mode so what lands on disk is ONE self-contained file — exactly
   what the dialogs promise ("saved as db.sqlite3").
2. **A copy is VERIFIED.** ``PRAGMA quick_check`` runs on the result before
   it is reported as a success. A backup that silently produced garbage is
   worse than no backup, because it is trusted.
3. **A swap leaves NO stale sidecar behind.** ``move_with_sidecars`` /
   ``remove_sidecars`` keep the ``-wal``/``-shm``/``-journal`` trio together
   with the database they belong to, so an archived copy stays restorable and
   a freshly loaded database is never poisoned by the previous one's WAL.

CONTRACTS (do NOT weaken)
-------------------------
* **Never claim success without checking.** Every path ends by re-reading the
  produced file: SQLite magic + ``quick_check``. ``ok`` means verified.
* **Never delete the source.** This module only ever writes the destination
  and prunes files it is about to overwrite. Losing Angela's database while
  "backing it up" is the worst outcome available.
* **Fail-SAFE, not fail-open.** Unlike the context loaders, an unclear result
  here is reported as a FAILURE (``ok=False`` with the reason), because the
  caller's alternative is to tell the user their data is safe when it is not.
* **Stdlib only, imports nothing from ``agent.*``** — ``manage.py`` uses it in
  the pre-Django window and ``views.py`` uses it inside Django, and both must
  behave identically frozen and from source.
"""
from __future__ import annotations

import os
import shutil
import sqlite3

# SQLite writes this at byte 0 of every database file it creates.
SQLITE_MAGIC = b"SQLite format 3\x00"

# The files SQLite keeps BESIDE the database. Under WAL the ``-wal`` file
# holds every committed change not yet checkpointed — routinely megabytes of
# the NEWEST data, which is precisely why it must never be left behind or
# separated from its database.
SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

# Generous: the live database is in use by Daphne while a backup is taken.
CONNECT_TIMEOUT_SECONDS = 30.0


# ──────────────────────────────────────────────────────────────────────
#  Sidecars
# ──────────────────────────────────────────────────────────────────────

def sidecar_paths(db_path):
    """Every path SQLite may keep beside *db_path* (existing or not)."""
    if not db_path:
        return []
    return [db_path + suffix for suffix in SIDECAR_SUFFIXES]


def existing_sidecars(db_path):
    """Only the sidecars that are actually on disk right now."""
    found = []
    for candidate in sidecar_paths(db_path):
        try:
            if os.path.isfile(candidate):
                found.append(candidate)
        except OSError:
            continue
    return found


def remove_sidecars(db_path, strict=False):
    """Delete the sidecars of *db_path*. Returns what was removed.

    Called AFTER the database they belong to has been archived — a WAL is
    data, so it is preserved first and deleted second, never the other way
    round.
    """
    removed = []
    failures = []
    for candidate in existing_sidecars(db_path):
        try:
            os.remove(candidate)
            removed.append(candidate)
        except OSError as exc:
            failures.append((candidate, exc))
    if strict and failures:
        detail = "; ".join("%s: %s" % item for item in failures)
        raise OSError("could not remove SQLite sidecar(s): %s" % detail)
    return removed


def move_with_sidecars(db_path, destination_dir):
    """Move *db_path* AND its sidecars into *destination_dir*.

    Keeping the trio together is what makes ``DB/Older/<timestamp>/`` a real
    audit trail: archiving ``db.sqlite3`` alone would file away a database
    whose newest pages were left behind in the ``-wal`` that got deleted.
    Returns the list of destination paths actually written.
    """
    origins = [db_path] + existing_sidecars(db_path)
    moved = []
    os.makedirs(destination_dir, exist_ok=True)
    try:
        for origin in origins:
            if not os.path.isfile(origin):
                continue
            target = os.path.join(destination_dir, os.path.basename(origin))
            if os.path.exists(target):
                raise FileExistsError("archive target already exists: %s" % target)
            shutil.move(origin, target)
            moved.append(target)
    except Exception:
        # A partial archive is worse than no archive: put every file already
        # moved back beside its database, then let the caller abort the swap.
        for target in reversed(moved):
            origin = os.path.join(os.path.dirname(db_path),
                                  os.path.basename(target))
            try:
                if os.path.exists(target) and not os.path.exists(origin):
                    shutil.move(target, origin)
            except OSError:
                pass
        raise
    return moved


# ──────────────────────────────────────────────────────────────────────
#  Copying
# ──────────────────────────────────────────────────────────────────────

def looks_like_sqlite(path):
    """True when *path* starts with the documented SQLite signature."""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _clear_destination(destination):
    """Remove the destination and any sidecar of it.

    The online backup API OPENS the destination as a database; writing into a
    pre-existing file would merge two databases instead of replacing one, and
    a leftover ``-wal`` next to the destination would resurrect the previous
    backup's pages.
    """
    failures = []
    for candidate in [destination] + sidecar_paths(destination):
        try:
            if os.path.isfile(candidate):
                os.remove(candidate)
        except OSError as exc:
            failures.append((candidate, exc))
    if failures:
        detail = "; ".join("%s: %s" % item for item in failures)
        raise OSError("cannot replace the destination database: %s" % detail)


def _read_only_uri(source):
    absolute = os.path.abspath(source)
    return "file:%s?mode=ro" % absolute.replace("?", "%3f").replace("#", "%23")


def _online_backup(source, destination, source_uri=None):
    """SQLite's online backup API. Returns the destination's quick_check."""
    src = sqlite3.connect(source_uri or source, uri=bool(source_uri),
                          timeout=CONNECT_TIMEOUT_SECONDS, isolation_level=None)
    try:
        dst = sqlite3.connect(destination, timeout=CONNECT_TIMEOUT_SECONDS,
                              isolation_level=None)
        try:
            src.backup(dst)
            # ONE self-contained file: DELETE mode checkpoints the copy and
            # drops its own -wal/-shm, so the artifact the user keeps (or
            # picks later in Set DB) needs no companion files at all.
            try:
                dst.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.Error:
                pass
            row = dst.execute("PRAGMA quick_check").fetchone()
            return str(row[0]) if row else "unknown"
        finally:
            dst.close()
    finally:
        src.close()


def consistent_copy(source, destination):
    """Write a COMPLETE, VERIFIED copy of the SQLite database *source*.

    Returns a report dict::

        {"ok": bool, "method": str, "bytes": int, "integrity": str,
         "sidecars": [...], "attempts": [...], "error": str}

    ``ok`` is only True when the produced file was re-read and passed both
    the magic-header test and ``PRAGMA quick_check``.

    Ordered ladder — deterministic, each rung recorded in ``attempts``:

      1. ``online-backup``          — read/write source connection, so a WAL
                                      left by a crashed process is recovered
                                      and its contents travel with the copy.
      2. ``online-backup-readonly`` — same, but the source is opened
                                      ``mode=ro`` (a database on read-only
                                      media, or one we must not touch).
      3. ``file-copy-with-sidecars``— last resort: byte copy of the database
                                      **and its ``-wal``/``-shm``**, so even
                                      here no committed data is stranded.
    """
    report = {"ok": False, "method": "", "bytes": 0, "integrity": "",
              "sidecars": [], "attempts": [], "error": "",
              "source": source, "destination": destination}

    if not source or not os.path.isfile(source):
        report["error"] = "source database does not exist: %s" % source
        return report
    if not looks_like_sqlite(source):
        report["error"] = ("source is not a SQLite database "
                           "(missing the 'SQLite format 3' signature)")
        return report

    try:
        parent = os.path.dirname(os.path.abspath(destination))
        if parent:
            os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        report["error"] = "cannot create the destination directory: %s" % exc
        return report

    for method, uri in (("online-backup", None),
                        ("online-backup-readonly", _read_only_uri(source))):
        try:
            _clear_destination(destination)
            integrity = _online_backup(source, destination, source_uri=uri)
        except Exception as exc:                 # noqa: BLE001 - try next rung
            report["attempts"].append("%s failed: %s" % (method, exc))
            continue
        if not looks_like_sqlite(destination):
            report["attempts"].append(
                "%s produced a file that is not a SQLite database" % method)
            continue
        if integrity.lower() != "ok":
            report["attempts"].append(
                "%s produced a damaged copy (quick_check: %s)" % (method, integrity))
            continue
        report.update(ok=True, method=method, integrity=integrity,
                      bytes=file_size(destination))
        return report

    # Last resort: carry the whole SQLite family, then open and verify that
    # family before claiming success. This is intentionally not a bare copy
    # of db.sqlite3: committed pages may exist only in the WAL.
    try:
        _clear_destination(destination)
        shutil.copy2(source, destination)
        carried = []
        for lateral in existing_sidecars(source):
            suffix = lateral[len(source):]
            try:
                shutil.copy2(lateral, destination + suffix)
                carried.append(destination + suffix)
            except OSError as exc:
                report["attempts"].append(
                    "could not carry %s: %s" % (suffix, exc))
        report["sidecars"] = carried
        report["method"] = "file-copy-with-sidecars"
        report["bytes"] = file_size(destination)
        if not looks_like_sqlite(destination):
            raise sqlite3.DatabaseError("copied file has no SQLite signature")

        verify = sqlite3.connect(destination, timeout=CONNECT_TIMEOUT_SECONDS,
                                 isolation_level=None)
        try:
            row = verify.execute("PRAGMA quick_check").fetchone()
            integrity = str(row[0]) if row else "unknown"
            if integrity.lower() != "ok":
                raise sqlite3.DatabaseError("quick_check: %s" % integrity)
            # Opening the copied family recovers its WAL. Checkpoint it into
            # the main file so the result is the promised single-file backup.
            verify.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            verify.execute("PRAGMA journal_mode=DELETE")
        finally:
            verify.close()

        remove_sidecars(destination, strict=True)
        final_check = _online_backup(destination, destination + ".verify")
        try:
            if final_check.lower() != "ok":
                raise sqlite3.DatabaseError("final quick_check: %s" % final_check)
        finally:
            _clear_destination(destination + ".verify")
        report.update(ok=True, integrity="ok", sidecars=[],
                      bytes=file_size(destination))
    except Exception as exc:                     # noqa: BLE001 - report, never raise
        report["error"] = "copy/verification failed: %s" % exc
        try:
            _clear_destination(destination)
        except OSError:
            pass
    return report


def describe(report):
    """One log-friendly line summarising a :func:`consistent_copy` report."""
    if report.get("ok"):
        line = "%s via %s (%s bytes, integrity: %s)" % (
            report.get("destination", "?"), report.get("method", "?"),
            format(report.get("bytes", 0), ","), report.get("integrity", "?"))
        if report.get("sidecars"):
            line += " + %d sidecar(s)" % len(report["sidecars"])
        return line
    detail = report.get("error") or "; ".join(report.get("attempts", [])) or "unknown"
    return "FAILED: %s" % detail
