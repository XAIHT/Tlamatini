# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Daily backup of Tlamatini's database."""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sqlite3
import sys
import traceback

REPO = os.path.dirname(os.path.abspath(__file__))
LIVE_DB = os.path.join(REPO, "Tlamatini", "db.sqlite3")
DEST_DIR = os.path.join(REPO, "Backups")
LOG_PATH = os.path.join(DEST_DIR, "backup_db.log")

# Tables whose row counts are logged: if a backup ever comes back with zero
# users, the log will have been shouting about it long before a restore is
# needed.
CHECK_TABLES = ("auth_user", "agent_prompt", "agent_agent", "agent_tool",
                "agent_skill", "django_migrations")


def log(msg: str) -> None:
    line = "%s  %s" % (_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(DEST_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def verify(path: str) -> "tuple[bool, dict]":
    """Actually open the backup and inspect it. Returns (ok, row_counts)."""
    counts: dict = {}
    try:
        con = sqlite3.connect(path)
        try:
            state = con.execute("pragma integrity_check").fetchone()[0]
            if state != "ok":
                log("!! integrity_check said: %s" % state)
                return False, counts
            for t in CHECK_TABLES:
                try:
                    counts[t] = con.execute(
                        "select count(*) from %s" % t).fetchone()[0]
                except sqlite3.Error:
                    counts[t] = -1
        finally:
            con.close()
    except Exception as exc:
        log("!! could not verify the backup: %s" % exc)
        return False, counts
    return True, counts


def prune(keep: int) -> None:
    """Keep the `keep` newest backups and delete the rest."""
    try:
        files = sorted(
            (os.path.join(DEST_DIR, f) for f in os.listdir(DEST_DIR)
             if f.startswith("db_") and f.endswith(".sqlite3")),
            key=os.path.getmtime, reverse=True)
    except OSError:
        return
    for old in files[keep:]:
        try:
            os.remove(old)
            log("   pruned: %s" % os.path.basename(old))
        except OSError as exc:
            log("   could not prune %s: %s" % (os.path.basename(old), exc))


def back_up(keep: int) -> int:
    if not os.path.isfile(LIVE_DB):
        log("!! REFUSING: live database not found at %s" % LIVE_DB)
        return 2
    try:
        size = os.path.getsize(LIVE_DB)
    except OSError as exc:
        log("!! REFUSING: cannot stat the live database: %s" % exc)
        return 2
    if size <= 0:
        log("!! REFUSING: the live database is empty (0 bytes)")
        return 2

    # Verify the LIVE database before trusting it enough to snapshot.
    ok, counts = verify(LIVE_DB)
    if not ok:
        log("!! REFUSING: the live database did not pass verification")
        return 2
    if counts.get("auth_user", -1) == 0:
        log("!! REFUSING: the live database has ZERO users - not something to snapshot")
        return 2

    os.makedirs(DEST_DIR, exist_ok=True)
    name = "db_%s.sqlite3" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(DEST_DIR, name)
    try:
        src = sqlite3.connect(LIVE_DB)
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)              # ONLINE backup - safe while running
            finally:
                dst.close()
        finally:
            src.close()
    except Exception as exc:
        log("!! backup FAILED: %s" % exc)
        log(traceback.format_exc())
        try:
            if os.path.exists(dest):
                os.remove(dest)              # never leave a half-written backup
        except OSError:
            pass
        return 1

    ok, counts = verify(dest)
    if not ok:
        log("!! the backup did NOT verify - deleting it rather than keeping a lie")
        try:
            os.remove(dest)
        except OSError:
            pass
        return 1

    log("backup OK  %s  (%.2f MB)" % (name, os.path.getsize(dest) / 1048576.0))
    log("   " + "  ".join("%s=%s" % kv for kv in counts.items()))
    prune(keep)
    return 0


def check_newest() -> int:
    try:
        files = sorted(
            (os.path.join(DEST_DIR, f) for f in os.listdir(DEST_DIR)
             if f.startswith("db_") and f.endswith(".sqlite3")),
            key=os.path.getmtime, reverse=True)
    except OSError:
        files = []
    if not files:
        log("!! there is NO backup at all in %s" % DEST_DIR)
        return 2
    newest = files[0]
    age_days = (_dt.datetime.now()
                - _dt.datetime.fromtimestamp(os.path.getmtime(newest))).days
    ok, counts = verify(newest)
    log("newest backup: %s  (%d day(s) old)  verified=%s"
        % (os.path.basename(newest), age_days, ok))
    if counts:
        log("   " + "  ".join("%s=%s" % kv for kv in counts.items()))
    if not ok:
        return 2
    if age_days >= 3:
        log("!! the newest backup is %d days old - the daily job is not running"
            % age_days)
        return 2
    return 0


ALARM_PATH = os.path.join(REPO, ".backup_status")


def _set_alarm(rc: int) -> None:
    """Write a marker while backups are failing; remove it on success."""
    try:
        if rc == 0:
            if os.path.exists(ALARM_PATH):
                os.remove(ALARM_PATH)
            return
        with open(ALARM_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "backup: not completed (exit %d)\n"
                "last attempt: %s\n"
                "details: Backups/backup_db.log\n"
                "cleared automatically on the next successful backup\n"
                % (rc, _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up Tlamatini's database.")
    ap.add_argument("--keep", type=int, default=30,
                    help="how many backups to keep (default 30)")
    ap.add_argument("--check", action="store_true",
                    help="only inspect the newest backup; write nothing")
    args = ap.parse_args()
    if args.check:
        return check_newest()
    rc = back_up(max(1, args.keep))
    _set_alarm(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
