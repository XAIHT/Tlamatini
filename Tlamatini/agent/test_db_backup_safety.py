# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""The daily DB backup must refuse bad input and must never fail quietly."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_REPO, "backup_db.py")


def _load():
    spec = importlib.util.spec_from_file_location("tlamatini_backup_db", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db(path, users=1):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE auth_user (id INTEGER PRIMARY KEY, username TEXT)")
    con.execute("CREATE TABLE agent_prompt (id INTEGER PRIMARY KEY)")
    for i in range(users):
        con.execute("INSERT INTO auth_user (username) VALUES (?)", ("u%d" % i,))
    con.commit()
    con.close()


@unittest.skipUnless(os.path.isfile(_SCRIPT), "backup_db.py not present in this tree")
class DatabaseBackupSafetyTests(unittest.TestCase):

    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.mkdtemp(prefix="tlm_backup_test_")
        self.live = os.path.join(self.tmp, "db.sqlite3")
        self.dest = os.path.join(self.tmp, "Backups")
        os.makedirs(self.dest, exist_ok=True)
        self.alarm_attr = ("ALARM_PATH" if hasattr(self.mod, "ALARM_PATH")
                           else "ALARMA_PATH")
        self.alarm = os.path.join(self.tmp, ".backup_status")
        self.mod.LIVE_DB = self.live
        self.mod.DEST_DIR = self.dest
        self.mod.LOG_PATH = os.path.join(self.dest, "backup_db.log")
        setattr(self.mod, self.alarm_attr, self.alarm)
        self.back_up = (getattr(self.mod, "back_up", None)
                        or getattr(self.mod, "respaldar"))
        self.prune = (getattr(self.mod, "prune", None)
                      or getattr(self.mod, "podar"))
        self.set_alarm = (getattr(self.mod, "_set_alarm", None)
                          or getattr(self.mod, "_prender_alarma"))

    def _backups(self):
        return [f for f in os.listdir(self.dest)
                if f.startswith("db_") and f.endswith(".sqlite3")]

    # ── the refusals: a backup of garbage is worse than no backup ───────────
    def test_refuses_a_missing_database(self):
        self.assertEqual(self.back_up(30), 2)
        self.assertEqual(self._backups(), [])

    def test_refuses_a_zero_byte_database(self):
        open(self.live, "wb").close()
        self.assertEqual(self.back_up(30), 2,
                         "a ZERO-BYTE database must never be snapshotted")
        self.assertEqual(self._backups(), [])

    def test_refuses_a_database_with_no_users(self):
        _make_db(self.live, users=0)
        self.assertEqual(self.back_up(30), 2,
                         "zero users must never be snapshotted - retention would then flush "
                         "every good copy away")
        self.assertEqual(self._backups(), [])

    # ── the happy path still works ─────────────────────────────────────────
    def test_backs_up_a_healthy_database_and_verifies_it(self):
        _make_db(self.live, users=2)
        self.assertEqual(self.back_up(30), 0)
        made = self._backups()
        self.assertEqual(len(made), 1)
        con = sqlite3.connect(os.path.join(self.dest, made[0]))
        try:
            self.assertEqual(con.execute("pragma integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                con.execute("SELECT count(*) FROM auth_user").fetchone()[0], 2,
                "the backup must carry the rows the live database had")
        finally:
            con.close()

    def test_retention_keeps_only_the_newest_n(self):
        for i in range(6):
            p = os.path.join(self.dest, "db_2026080%d_120000.sqlite3" % i)
            _make_db(p, users=1)
            os.utime(p, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
        self.prune(3)
        self.assertEqual(len(self._backups()), 3)

    # ── and a failure is never silent again ────────────────────────────────
    def test_the_alarm_appears_on_failure_and_clears_on_success(self):
        self.set_alarm(2)
        self.assertTrue(os.path.exists(self.alarm),
                        "a failing backup MUST leave a visible marker")
        body = open(self.alarm, encoding="utf-8").read()
        # Language-neutral: this file guards both trees.
        self.assertTrue(body.strip(), "the alarm file must not be empty")
        self.assertIn("2", body,
                      "the alarm must name the exit code that caused it")
        self.set_alarm(0)
        self.assertFalse(os.path.exists(self.alarm),
                         "a successful backup must clear the alarm")

    def test_the_alarm_never_raises(self):
        setattr(self.mod, self.alarm_attr,
                os.path.join(self.tmp, "no", "such", "dir", "alarm.txt"))
        try:
            self.set_alarm(2)          # must not raise into the caller
        except Exception as exc:       # pragma: no cover
            self.fail("the alarm raised into the backup: %r" % exc)


if __name__ == "__main__":
    unittest.main()
