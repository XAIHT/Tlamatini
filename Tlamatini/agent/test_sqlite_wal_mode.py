# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""SQLite must stay in WAL mode."""
from __future__ import annotations

import os
import sqlite3
import unittest

from django.conf import settings
from django.test import SimpleTestCase


class SqliteWalModeTests(SimpleTestCase):

    def _options(self):
        return (settings.DATABASES.get("default", {}) or {}).get("OPTIONS", {}) or {}

    def test_settings_ask_for_wal(self):
        init = (self._options().get("init_command") or "").lower()
        self.assertIn("journal_mode=wal", init.replace(" ", ""),
                      "settings.py must put SQLite in WAL")

    def test_settings_set_a_busy_timeout(self):
        init = (self._options().get("init_command") or "").lower()
        self.assertIn("busy_timeout", init,
                      "a concurrent writer must wait, not fail instantly")

    def test_the_live_database_file_is_actually_in_wal(self):
        db = settings.DATABASES["default"]["NAME"]
        if not os.path.isfile(db):
            self.skipTest("no live database in this environment")
        con = sqlite3.connect(str(db))
        try:
            mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(
            mode.lower(), "wal",
            "the live database is in %r, not WAL. The journal mode is stored "
            "IN THE FILE, so a database restored from an old backup comes back "
            "in 'delete' mode and is vulnerable again - re-run "
            "'PRAGMA journal_mode=WAL' on it." % mode)


if __name__ == "__main__":
    unittest.main()
