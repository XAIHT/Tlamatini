# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Startup health guard for the live ``db.sqlite3`` — shout NOW, keep the body.

WHY THIS EXISTS (Angela, 2026-08-02/03). The live database was found at **zero
bytes**. It was restored from the 13:00 backup and nothing was lost, but two
things went wrong around it:

1. **Nobody noticed at the time.** The app happily started on a broken file;
   the emptiness surfaced hours later, by accident.
2. **The evidence did not survive.** The broken file was supposedly set aside
   for a post-mortem and was gone when we went looking, so *why* it emptied is
   still unknown. A cause we cannot see is a cause we cannot fix.

So this module runs BEFORE Django opens the database and does three things, in
this order of importance:

  1. **PRESERVES THE BODY.** On a bad verdict the broken file is copied aside
     as ``DB/Corrupted/db.sqlite3.broken_<timestamp>`` *first*, before anything
     else can overwrite it. Diagnosis comes later; the evidence is now.
  2. **SHOUTS.** A loud, unmissable banner naming what is wrong, where the
     evidence went, and the newest backup available — with a ready-to-paste
     restore command.
  3. **REMEMBERS.** On a healthy start it records a fingerprint (size + row
     counts) so the NEXT start can notice a silent shrink, not just an
     outright corruption.

TWO CONTRACTS THAT MUST NOT BE WEAKENED
---------------------------------------
**FAIL-OPEN.** Every entry point swallows its own errors. A guard that stops
Tlamatini from starting is worse than the bug it watches for: the user is then
locked out of the very app that holds their data. Nothing here raises, and
nothing here blocks startup.

**IT NEVER RESTORES BY ITSELF.** It preserves, reports and points at the
backup — the decision to overwrite a database is Angela's, never the
program's. An automatic restore would be a destructive act taken on a guess,
and a "corrupt" verdict on a database that merely looks odd would then destroy
real data.

Stdlib only (``sqlite3`` ships with Python), no Django import, no ``agent.*``
import — it has to run in the pre-Django window and in frozen builds alike.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time

# SQLite writes this at byte 0 of every database file it creates.
SQLITE_MAGIC = b"SQLite format 3\x00"

# A real SQLite file always carries at least one 512-byte page of header.
MIN_PLAUSIBLE_BYTES = 512

# integrity_check walks every page; quick_check is O(1)-ish. Databases above
# this size use the cheap check so startup never stalls on a huge file.
FULL_CHECK_MAX_BYTES = 64 * 1024 * 1024

# A healthy database does not lose this much between two consecutive starts.
# Above the threshold we SHOUT but do not call it corrupt: the user may have
# legitimately cleared their chat history.
SHRINK_FRACTION = 0.40
ROW_DROP_FRACTION = 0.50

SENTINEL_NAME = "db_health.json"
EVIDENCE_DIRNAME = "Corrupted"

# Verdicts
OK = "ok"
FIRST_RUN = "first_run"
SUSPICIOUS = "suspicious"
CRITICAL = "critical"


# ──────────────────────────────────────────────────────────────────────
#  Inspection
# ──────────────────────────────────────────────────────────────────────

def inspect_database(db_path: str) -> dict:
    """Look at *db_path* and decide whether it is healthy. NEVER raises.

    Returns a report dict: ``verdict``, ``reason``, ``size``, ``tables``
    (name -> row count) and ``integrity``.
    """
    report = {"verdict": OK, "reason": "", "size": 0, "tables": {},
              "integrity": "", "path": db_path}
    try:
        if not db_path or not os.path.isfile(db_path):
            report["verdict"] = FIRST_RUN
            report["reason"] = "no database file yet (Django will create one)"
            return report

        size = os.path.getsize(db_path)
        report["size"] = size

        # THE failure that started all this.
        if size == 0:
            report["verdict"] = CRITICAL
            report["reason"] = "the database file is ZERO BYTES"
            return report

        if size < MIN_PLAUSIBLE_BYTES:
            report["verdict"] = CRITICAL
            report["reason"] = (
                "the database file is %d bytes — smaller than a single SQLite "
                "page, so it is truncated" % size)
            return report

        with open(db_path, "rb") as fh:
            header = fh.read(len(SQLITE_MAGIC))
        if header != SQLITE_MAGIC:
            report["verdict"] = CRITICAL
            report["reason"] = ("the file does not start with the SQLite "
                                "signature — it is not a database")
            return report

        # Read-only URI: cannot create the file, cannot write to it.
        uri = "file:%s?mode=ro" % db_path.replace("?", "%3f").replace("#", "%23")
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            pragma = ("quick_check" if size > FULL_CHECK_MAX_BYTES
                      else "integrity_check")
            row = con.execute("PRAGMA %s" % pragma).fetchone()
            report["integrity"] = (row[0] if row else "unknown")
            if str(report["integrity"]).lower() != "ok":
                report["verdict"] = CRITICAL
                report["reason"] = ("SQLite reports the file is damaged: %s"
                                    % report["integrity"])
                return report
            report["tables"] = _table_counts(con)
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        # SQLite REFUSED the file — "database disk image is malformed", "file
        # is not a database", "file is encrypted". Damaging a whole interior
        # page produces exactly this, and integrity_check never gets to speak.
        # That is a destroyed database, so it is CRITICAL, not merely odd:
        # calling it "suspicious" would understate it in the banner and in the
        # log. (Found while testing — the first draft mislabelled this.)
        report["verdict"] = CRITICAL
        report["reason"] = "SQLite refuses to read the file: %s" % (exc,)
    except Exception as exc:                     # noqa: BLE001 - fail-open
        # Anything else (permissions, a vanished file, a locked handle) is a
        # red flag we cannot classify. A guard that throws is worse than the
        # bug it watches for, so: report, never raise.
        report["verdict"] = SUSPICIOUS
        report["reason"] = "could not inspect the database (%s)" % (exc,)
    return report


def _table_counts(con) -> dict:
    """Row count per user table. Skips SQLite's own bookkeeping tables."""
    counts = {}
    try:
        nombres = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        for nombre in nombres:
            # The name comes from sqlite_master, not from user input, and is
            # quoted anyway — a table cannot be parameterized in SQL.
            try:
                counts[nombre] = con.execute(
                    'SELECT COUNT(*) FROM "%s"' % nombre.replace('"', '""')
                ).fetchone()[0]
            except sqlite3.Error:
                continue
    except sqlite3.Error:
        pass
    return counts


# ──────────────────────────────────────────────────────────────────────
#  Remembering what "healthy" looked like
# ──────────────────────────────────────────────────────────────────────

def sentinel_path(db_root: str) -> str:
    return os.path.join(db_root, SENTINEL_NAME)


def read_sentinel(db_root: str) -> dict:
    """Last known-good fingerprint, or {} when there isn't one. Never raises."""
    import json
    try:
        with open(sentinel_path(db_root), encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:                            # noqa: BLE001 - fail-open
        return {}


def write_sentinel(db_root: str, report: dict) -> bool:
    """Record this healthy start. Never raises; returns whether it stuck."""
    import json
    try:
        os.makedirs(db_root, exist_ok=True)
        payload = {
            "size": report.get("size", 0),
            "tables": report.get("tables", {}),
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        tmp = sentinel_path(db_root) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, sentinel_path(db_root))
        return True
    except Exception:                            # noqa: BLE001 - fail-open
        return False


def compare_with_sentinel(report: dict, sentinel: dict) -> str:
    """'' when nothing looks wrong, else a human sentence describing the drop.

    Deliberately only SUSPICIOUS, never CRITICAL: a user who clears their chat
    history legitimately shrinks the database, and a guard that cried
    corruption over that would teach everyone to ignore it.
    """
    if not sentinel:
        return ""
    quejas = []
    antes = sentinel.get("size") or 0
    ahora = report.get("size") or 0
    if antes and ahora < antes * (1 - SHRINK_FRACTION):
        quejas.append("the file shrank from %s to %s bytes"
                      % (format(antes, ","), format(ahora, ",")))

    tablas_antes = sentinel.get("tables") or {}
    tablas_ahora = report.get("tables") or {}
    for nombre, previo in sorted(tablas_antes.items()):
        if not isinstance(previo, int) or previo <= 0:
            continue
        actual = tablas_ahora.get(nombre)
        if actual is None:
            quejas.append("table %s disappeared (had %d rows)" % (nombre, previo))
        elif actual < previo * (1 - ROW_DROP_FRACTION):
            quejas.append("table %s dropped from %d to %d rows"
                          % (nombre, previo, actual))
    return "; ".join(quejas)


# ──────────────────────────────────────────────────────────────────────
#  Evidence + backups
# ──────────────────────────────────────────────────────────────────────

def preserve_evidence(db_path: str, db_root: str) -> str:
    """Copy the broken database aside BEFORE anything can overwrite it.

    This is the single most important thing this module does — last time the
    body was lost and the cause is still unknown. Returns the evidence path,
    or '' when it could not be saved. Never raises.
    """
    try:
        if not db_path or not os.path.exists(db_path):
            return ""
        destino = os.path.join(db_root, EVIDENCE_DIRNAME)
        os.makedirs(destino, exist_ok=True)
        nombre = "db.sqlite3.broken_%s" % time.strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(destino, nombre)
        # copy2, never move: the live file stays where Django expects it.
        shutil.copy2(db_path, ruta)
        return ruta
    except Exception:                            # noqa: BLE001 - fail-open
        return ""


def find_newest_backup(search_roots) -> str:
    """Newest ``db_<timestamp>.sqlite3`` written by backup_db.py. Never raises."""
    mejor, mejor_mtime = "", -1.0
    try:
        for raiz in search_roots:
            if not raiz or not os.path.isdir(raiz):
                continue
            for base, _dirs, archivos in os.walk(raiz):
                for f in archivos:
                    if not (f.startswith("db_") and f.endswith(".sqlite3")):
                        continue
                    ruta = os.path.join(base, f)
                    try:
                        if os.path.getsize(ruta) <= MIN_PLAUSIBLE_BYTES:
                            continue           # a zero-byte backup is no backup
                        mtime = os.path.getmtime(ruta)
                    except OSError:
                        continue
                    if mtime > mejor_mtime:
                        mejor, mejor_mtime = ruta, mtime
    except Exception:                            # noqa: BLE001 - fail-open
        return mejor
    return mejor


# ──────────────────────────────────────────────────────────────────────
#  The alarm
# ──────────────────────────────────────────────────────────────────────

def format_alarm(report: dict, evidence: str, backup: str, db_root: str) -> str:
    """The banner. Loud on purpose — this is the moment nobody may miss."""
    critico = report.get("verdict") == CRITICAL
    titulo = ("DATABASE IS DAMAGED" if critico
              else "DATABASE LOOKS WRONG")
    linea = "=" * 72
    partes = [
        "",
        linea,
        "  !!!  [DB GUARD]  %s  !!!" % titulo,
        linea,
        "  What is wrong : %s" % (report.get("reason") or "unknown"),
        "  File          : %s" % report.get("path", "?"),
        "  Size          : %s bytes" % format(report.get("size", 0), ","),
    ]
    if evidence:
        partes.append("  Evidence KEPT : %s" % evidence)
    else:
        partes.append("  Evidence      : COULD NOT be preserved — copy the file "
                      "aside by hand BEFORE restarting")
    if backup:
        partes += [
            "  Newest backup : %s" % backup,
            "",
            "  Tlamatini did NOT restore anything on its own — that is your call.",
            "  To restore it, stop Tlamatini and run:",
            '      copy /Y "%s" "%s"' % (backup, report.get("path", "")),
        ]
    else:
        partes += ["  Newest backup : NONE FOUND — do not overwrite anything yet"]
    partes += [linea, ""]
    return "\n".join(partes)


# ──────────────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────────────

def guard_database(db_path: str, db_root: str, backup_roots=None,
                   echo=print) -> dict:
    """Inspect, preserve, shout, remember. NEVER raises, NEVER blocks startup.

    Returns the report so callers (and tests) can see what happened.
    """
    try:
        report = inspect_database(db_path)

        if report["verdict"] == FIRST_RUN:
            echo("--- [DB GUARD] no database yet — Django will create one")
            return report

        if report["verdict"] == OK:
            drift = compare_with_sentinel(report, read_sentinel(db_root))
            if drift:
                report["verdict"] = SUSPICIOUS
                report["reason"] = drift

        if report["verdict"] in (CRITICAL, SUSPICIOUS):
            evidencia = preserve_evidence(db_path, db_root)
            report["evidence"] = evidencia
            raices = list(backup_roots or []) or [db_root,
                                                  os.path.dirname(db_path or ".")]
            echo(format_alarm(report, evidencia, find_newest_backup(raices),
                              db_root))
            return report

        # Healthy: remember this shape so the next start can spot a silent drop.
        write_sentinel(db_root, report)
        echo("--- [DB GUARD] database healthy — %s bytes, %d table(s)"
             % (format(report["size"], ","), len(report["tables"])))
        return report
    except Exception as exc:                     # noqa: BLE001 - fail-open
        # Last line of defence. Tlamatini starts even if the guard is broken.
        try:
            echo("--- [DB GUARD] guard failed, continuing anyway (%s)" % (exc,))
        except Exception:
            pass
        return {"verdict": SUSPICIOUS, "reason": str(exc), "path": db_path}
