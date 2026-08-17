# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""DB ▸ Backup database and DB ▸ Set DB must work under WAL. (Angela, 2026-08-16)

THE INCIDENT
------------
Both DB menu options were written when the database used the rollback journal,
where copying ``db.sqlite3`` is a complete copy. ``settings.py`` later switched
the database to **WAL** — and said so in a comment right above the setting:

    "Under WAL, back up with sqlite3's online backup API, never a plain file
     copy."

Nothing updated the two options, so on Angela's live install:

    C:\\Tlamatini\\_internal\\db.sqlite3        839,680 bytes   13:39
    C:\\Tlamatini\\_internal\\db.sqlite3-wal   3,514,392 bytes   22:49   <-- the data

* **Backup** copied the 13:39 file and reported success → nine hours of work
  silently absent from the "backup".
* **Set DB** wrote the chosen database over ``db.sqlite3`` but left that 3.5 MB
  ``-wal`` beside it, so SQLite replayed the OLD database's pages on the next
  open → the loaded database was overwritten by the one it replaced. Angela ran
  Set DB three times in a row (22:46, 22:48, 22:49) and kept getting the old
  data back.

WHAT IS PINNED HERE
-------------------
These are REAL databases in REAL WAL mode — nothing about the thing under test
is mocked. The suite proves, in both directions:

  1. a plain file copy genuinely loses WAL-resident data (the bug, reproduced);
  2. ``sqlite_copy.consistent_copy`` genuinely keeps it (the fix);
  3. the produced copy is ONE self-contained, integrity-checked file;
  4. the start-up swap archives the outgoing database **with** its sidecars and
     leaves **none** of them beside the incoming one;
  5. the archived pair is still restorable afterwards;
  6. neither view has quietly gone back to ``shutil.copy2``.

Run:
    python Tlamatini/manage.py test agent.test_db_backup_restore_wal
    python -m unittest agent.test_db_backup_restore_wal        # Django-free too
"""
import ast
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import sqlite_copy  # noqa: E402

#   <repo>/Tlamatini/agent/test_db_backup_restore_wal.py  ->  <repo>/Tlamatini
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANAGE_PY = os.path.join(_PROJECT_DIR, 'manage.py')
_VIEWS_PY = os.path.join(_PROJECT_DIR, 'agent', 'views.py')
_SETTINGS_PY = os.path.join(_PROJECT_DIR, 'tlamatini', 'settings.py')

_SWAP_FUNCS = ('_resolve_db_folder_root', '_resolve_live_db_path',
               '_apply_pending_db_swap')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _load_swap_helper():
    """Exec ONLY the swap helpers out of manage.py — never import the module.

    Same trick ``test_django_port_config`` / ``test_temp_dir_policy`` use:
    importing ``manage.py`` would run its whole start-up preamble (tee, temp
    pinning, the swap itself). Lifting the functions gives the REAL code under
    test with none of the side effects.
    """
    tree = ast.parse(_read(_MANAGE_PY), filename=_MANAGE_PY)
    picked = [node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name in _SWAP_FUNCS]
    namespace = {'os': os, 'sys': sys}
    exec(compile(ast.Module(body=picked, type_ignores=[]), _MANAGE_PY, 'exec'),  # noqa: S102
         namespace)
    return namespace


# ──────────────────────────────────────────────────────────────────────
#  Real WAL fixtures
# ──────────────────────────────────────────────────────────────────────

def _open_wal_db(path):
    """A real WAL database whose commits STAY in the -wal file.

    ``wal_autocheckpoint=0`` plus an open connection is exactly the live app's
    steady state: Daphne holds connections open and the ``-wal`` grows (3.5 MB
    of it on Angela's machine) until something checkpoints.
    """
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    return con


def _seed(con, marker, rows):
    con.execute("CREATE TABLE IF NOT EXISTS agent_agentmessage "
                "(id INTEGER PRIMARY KEY, message TEXT)")
    con.executemany("INSERT INTO agent_agentmessage (message) VALUES (?)",
                    [("%s %d" % (marker, i),) for i in range(rows)])


def _messages(db_path):
    """Every message in *db_path*, or [] when the table is not even there."""
    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        return [r[0] for r in con.execute(
            "SELECT message FROM agent_agentmessage ORDER BY id").fetchall()]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def _detach(con, db_path, destination_dir):
    """Freeze a live WAL database (db + -wal + -shm) into *destination_dir*.

    Copying the trio while the connection is open, then dropping the original,
    reproduces what a killed/again-started Tlamatini leaves on disk: an
    uncheckpointed WAL next to a database, with no process holding it.
    """
    os.makedirs(destination_dir, exist_ok=True)
    frozen = os.path.join(destination_dir, os.path.basename(db_path))
    for suffix in ('', '-wal', '-shm'):
        origin = db_path + suffix
        if os.path.isfile(origin):
            shutil.copy2(origin, frozen + suffix)
    con.close()
    return frozen


class _Caso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tlm_dbwal_")
        self.addCleanup(shutil.rmtree, self.tmp, True)


# ──────────────────────────────────────────────────────────────────────
#  1. The bug, reproduced — and the fix, proven
# ──────────────────────────────────────────────────────────────────────

class WalDataMustSurviveACopyTests(_Caso):

    def setUp(self):
        super().setUp()
        self.live = os.path.join(self.tmp, "db.sqlite3")
        self.con = _open_wal_db(self.live)
        self.addCleanup(lambda: self.con.close())
        _seed(self.con, "today", 40)

    def test_the_wal_really_holds_the_data(self):
        """Guard for the fixture itself: without this the suite proves nothing."""
        self.assertTrue(os.path.isfile(self.live + "-wal"))
        self.assertGreater(os.path.getsize(self.live + "-wal"), 0)
        self.assertEqual(len(_messages(self.live)), 40)   # read through the WAL

    def test_plain_file_copy_LOSES_the_data(self):
        """The bug: this is what Backup used to do."""
        naive = os.path.join(self.tmp, "naive.sqlite3")
        shutil.copy2(self.live, naive)
        self.assertNotEqual(
            len(_messages(naive)), 40,
            "if a bare copy2 kept the rows there would have been no incident")

    def test_consistent_copy_KEEPS_the_data(self):
        """The fix: every row committed into the WAL travels with the backup."""
        backup = os.path.join(self.tmp, "backup", "db.sqlite3")
        report = sqlite_copy.consistent_copy(self.live, backup)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(_messages(backup)), 40)
        self.assertEqual(_messages(backup), _messages(self.live))

    def test_the_backup_is_ONE_self_contained_file(self):
        """The dialog promises "saved as db.sqlite3" — so no companions."""
        backup = os.path.join(self.tmp, "backup", "db.sqlite3")
        report = sqlite_copy.consistent_copy(self.live, backup)
        self.assertTrue(report["ok"], report)
        for suffix in sqlite_copy.SIDECAR_SUFFIXES:
            self.assertFalse(os.path.exists(backup + suffix),
                             "left a %s beside the backup" % suffix)

    def test_the_backup_is_verified_not_merely_written(self):
        report = sqlite_copy.consistent_copy(
            self.live, os.path.join(self.tmp, "b", "db.sqlite3"))
        self.assertEqual(report["method"], "online-backup")
        self.assertEqual(report["integrity"], "ok")
        self.assertGreater(report["bytes"], 0)

    def test_a_later_backup_replaces_the_earlier_one_completely(self):
        """A stale destination (and its stale -wal) must never bleed through."""
        backup = os.path.join(self.tmp, "backup", "db.sqlite3")
        self.assertTrue(sqlite_copy.consistent_copy(self.live, backup)["ok"])
        with open(backup + "-wal", "wb") as fh:      # junk left by an old tool
            fh.write(b"stale wal from a previous backup")

        _seed(self.con, "later", 5)
        report = sqlite_copy.consistent_copy(self.live, backup)
        self.assertTrue(report["ok"], report)
        self.assertFalse(os.path.exists(backup + "-wal"))
        self.assertEqual(len(_messages(backup)), 45)


class ConsistentCopyRefusesRatherThanLieTests(_Caso):

    def test_missing_source_is_a_failure_not_an_empty_backup(self):
        report = sqlite_copy.consistent_copy(
            os.path.join(self.tmp, "nope.sqlite3"),
            os.path.join(self.tmp, "out.sqlite3"))
        self.assertFalse(report["ok"])
        self.assertIn("does not exist", report["error"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "out.sqlite3")))

    def test_a_file_that_is_not_a_database_is_refused(self):
        bogus = os.path.join(self.tmp, "notadb.sqlite3")
        with open(bogus, "wb") as fh:
            fh.write(b"I am a text file wearing a .sqlite3 hat")
        report = sqlite_copy.consistent_copy(
            bogus, os.path.join(self.tmp, "out.sqlite3"))
        self.assertFalse(report["ok"])
        self.assertIn("not a SQLite database", report["error"])

    def test_describe_says_FAILED_out_loud(self):
        report = sqlite_copy.consistent_copy(
            os.path.join(self.tmp, "nope.sqlite3"),
            os.path.join(self.tmp, "out.sqlite3"))
        self.assertTrue(sqlite_copy.describe(report).startswith("FAILED"))


# ──────────────────────────────────────────────────────────────────────
#  2. Sidecar hygiene
# ──────────────────────────────────────────────────────────────────────

class SidecarHelperTests(_Caso):

    def setUp(self):
        super().setUp()
        self.live = os.path.join(self.tmp, "db.sqlite3")
        con = _open_wal_db(self.live)
        _seed(con, "old", 10)
        self.frozen_dir = os.path.join(self.tmp, "live")
        self.live = _detach(con, self.live, self.frozen_dir)

    def test_existing_sidecars_finds_the_wal(self):
        found = [os.path.basename(p) for p in sqlite_copy.existing_sidecars(self.live)]
        self.assertIn("db.sqlite3-wal", found)

    def test_move_with_sidecars_keeps_the_family_together(self):
        archive = os.path.join(self.tmp, "Older", "2026-08-16_000000")
        moved = sqlite_copy.move_with_sidecars(self.live, archive)
        self.assertIn(os.path.join(archive, "db.sqlite3"), moved)
        self.assertIn(os.path.join(archive, "db.sqlite3-wal"), moved)
        self.assertFalse(os.path.exists(self.live))
        # And the archived pair is genuinely restorable — the whole point.
        self.assertEqual(len(_messages(os.path.join(archive, "db.sqlite3"))), 10)

    def test_remove_sidecars_leaves_the_database_alone(self):
        removed = sqlite_copy.remove_sidecars(self.live)
        self.assertTrue(removed)
        self.assertTrue(os.path.isfile(self.live))
        for suffix in sqlite_copy.SIDECAR_SUFFIXES:
            self.assertFalse(os.path.exists(self.live + suffix))


# ──────────────────────────────────────────────────────────────────────
#  3. The start-up swap (DB ▸ Set DB, second half)
# ──────────────────────────────────────────────────────────────────────

class StartupSwapTests(_Caso):
    """The REAL ``manage.py::_apply_pending_db_swap``, on real WAL databases."""

    def setUp(self):
        super().setUp()
        self.db_root = os.path.join(self.tmp, "DB")
        self.internal = os.path.join(self.tmp, "_internal")
        os.makedirs(os.path.join(self.db_root, "ToLoad"), exist_ok=True)
        os.makedirs(self.internal, exist_ok=True)
        self.live = os.path.join(self.internal, "db.sqlite3")
        self.staged = os.path.join(self.db_root, "ToLoad", "db.sqlite3")

        # The outgoing database: OLD rows, with an uncheckpointed WAL beside it.
        # It must be BUILT as db.sqlite3 so _detach lands it on the live path.
        seed_dir = os.path.join(self.tmp, "seed")
        os.makedirs(seed_dir, exist_ok=True)
        seed = os.path.join(seed_dir, "db.sqlite3")
        con = _open_wal_db(seed)
        _seed(con, "OLD", 30)
        _detach(con, seed, self.internal)
        self.assertTrue(os.path.isfile(self.live), "fixture: live db not staged")
        self.assertTrue(os.path.isfile(self.live + "-wal"),
                        "fixture: the outgoing database must carry a live WAL")

        # The incoming database the user picked: NEW rows, self-contained
        # (this is what the fixed ``set_db_view`` stages).
        chosen = os.path.join(self.tmp, "chosen.sqlite3")
        con2 = _open_wal_db(chosen)
        _seed(con2, "NEW", 7)
        con2.close()
        self.assertTrue(sqlite_copy.consistent_copy(chosen, self.staged)["ok"])

        ns = _load_swap_helper()
        ns['_resolve_db_folder_root'] = lambda: self.db_root
        ns['_resolve_live_db_path'] = lambda: self.live
        self.swap = ns['_apply_pending_db_swap']

    def _archives(self):
        older = os.path.join(self.db_root, "Older")
        if not os.path.isdir(older):
            return []
        return [os.path.join(older, d) for d in sorted(os.listdir(older))]

    def test_the_stale_wal_would_have_overridden_the_new_database(self):
        """Characterization of the incident — WHY step 3 of the swap exists.

        Doing what the old code did (move the file, keep the sidecars) does NOT
        give the user the database they chose.
        """
        shutil.move(self.staged, self.live)          # no sidecar cleanup
        self.assertNotEqual(
            _messages(self.live), ["NEW %d" % i for i in range(7)],
            "leaving the previous database's -wal in place was harmless?! "
            "then the swap's sidecar cleanup needs a different justification")

    def test_the_swap_actually_loads_the_chosen_database(self):
        self.assertTrue(self.swap())
        self.assertEqual(_messages(self.live), ["NEW %d" % i for i in range(7)])

    def test_no_sidecar_of_the_previous_database_survives(self):
        self.swap()
        for suffix in sqlite_copy.SIDECAR_SUFFIXES:
            self.assertFalse(os.path.exists(self.live + suffix),
                             "a stale %s survived the swap" % suffix)

    def test_the_outgoing_database_is_archived_WITH_its_wal(self):
        self.swap()
        archives = self._archives()
        self.assertEqual(len(archives), 1)
        kept = sorted(os.listdir(archives[0]))
        self.assertIn("db.sqlite3", kept)
        self.assertIn("db.sqlite3-wal", kept)

    def test_the_archived_database_is_still_restorable(self):
        """An audit trail that cannot be restored is not an audit trail."""
        self.swap()
        archived = os.path.join(self._archives()[0], "db.sqlite3")
        self.assertEqual(_messages(archived), ["OLD %d" % i for i in range(30)])

    def test_the_staged_file_is_consumed_so_a_relaunch_is_a_no_op(self):
        self.swap()
        self.assertFalse(os.path.exists(self.staged))
        self.assertFalse(self.swap())
        self.assertEqual(len(self._archives()), 1)

    def test_nothing_to_swap_returns_false_and_touches_nothing(self):
        os.remove(self.staged)
        self.assertFalse(self.swap())
        self.assertTrue(os.path.isfile(self.live))
        self.assertEqual(self._archives(), [])


# ──────────────────────────────────────────────────────────────────────
#  4. Source contracts — so this cannot silently regress again
# ──────────────────────────────────────────────────────────────────────

class SourceContractTests(unittest.TestCase):

    def test_settings_still_documents_the_rule_this_suite_enforces(self):
        settings = _read(_SETTINGS_PY)
        self.assertIn("journal_mode=WAL", settings)
        self.assertIn("never a plain file copy", settings)

    def test_neither_db_view_uses_a_plain_file_copy(self):
        views = _read(_VIEWS_PY)
        for marker in ("def backup_db_view", "def set_db_view"):
            start = views.index(marker)
            end = views.index("\ndef ", start + len(marker))
            cuerpo = views[start:end]
            self.assertNotIn(
                "shutil.copy2", cuerpo,
                "%s went back to a plain file copy — under WAL that silently "
                "loses every change still sitting in db.sqlite3-wal" % marker)
            self.assertIn("sqlite_copy.consistent_copy", cuerpo)

    def test_the_swap_archives_and_then_clears_the_sidecars(self):
        manage = _read(_MANAGE_PY)
        start = manage.index("def _apply_pending_db_swap")
        end = manage.index("\ndef ", start)
        cuerpo = manage[start:end]
        self.assertIn("move_with_sidecars", cuerpo)
        self.assertIn("remove_sidecars", cuerpo)
        self.assertLess(cuerpo.index("move_with_sidecars"),
                        cuerpo.index("remove_sidecars"),
                        "the WAL must be ARCHIVED before it is deleted — it is "
                        "data, not litter")

    def test_the_swap_runs_directly_before_django(self):
        manage = _read(_MANAGE_PY)
        call = manage.index("\n_apply_pending_db_swap()\n")
        django = manage.index("from django.core.management import")
        self.assertLess(call, django)

    def test_sqlite_copy_stays_stdlib_only(self):
        """It runs in the pre-Django window, so it must remain stdlib-only."""
        modulo = _read(os.path.join(_PROJECT_DIR, 'agent', 'sqlite_copy.py'))
        tree = ast.parse(modulo)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertFalse(
                    node.module.startswith('agent') or node.level,
                    "sqlite_copy must not import from agent.* (%s)" % node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith(('agent', 'django')),
                                     "sqlite_copy must stay stdlib-only (%s)"
                                     % alias.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
