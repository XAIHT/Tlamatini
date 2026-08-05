# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Tests for the startup database guard (``agent/db_guard.py``).

The guard exists because the live database was found at ZERO BYTES on
2026-08-02, nobody noticed at the time, and the broken file was gone by the
time we tried to diagnose it. So the tests are organised around what actually
went wrong, not around the code's shape:

* ``ZeroByteDatabaseTests``  — the exact failure, reproduced.
* ``EvidenceTests``          — the body survives. This is the point.
* ``FailOpenTests``          — the guard NEVER raises and NEVER blocks startup,
                               even when it is itself broken.
* ``NeverRestoresTests``     — the guard must not touch the live file. An
                               automatic restore would be a destructive act
                               taken on a guess.
* ``SilentShrinkTests``      — a database that quietly loses most of its rows
                               is caught too, not just an obviously corrupt one.
* ``WiringTests``            — manage.py actually calls it, in the right place.
"""
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
import unittest

from agent import db_guard


ROOT = Path(__file__).resolve().parent
MANAGE_PY = ROOT.parent / "manage.py"


def _make_healthy_db(path, rows=25):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE agent_chat (id INTEGER PRIMARY KEY, texto TEXT)")
    con.executemany("INSERT INTO agent_chat (texto) VALUES (?)",
                    [("mensaje %d" % i,) for i in range(rows)])
    con.commit()
    con.close()
    return path


def _corrupt_range(path, desde, hasta):
    """Overwrite [desde, hasta) with 0xFF, keeping the file length."""
    datos = bytearray(open(path, "rb").read())
    hasta = min(hasta, len(datos))
    datos[desde:hasta] = b"\xff" * max(0, hasta - desde)
    with open(path, "wb") as fh:
        fh.write(bytes(datos))
    return path


class _Caso(unittest.TestCase):
    """Temp workspace with a live DB path and a DB/ root, like the real app."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tlm_dbguard_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = os.path.join(self.tmp, "db.sqlite3")
        self.db_root = os.path.join(self.tmp, "DB")
        os.makedirs(self.db_root, exist_ok=True)
        self.dicho = []

    def echo(self, mensaje):
        self.dicho.append(str(mensaje))

    @property
    def salida(self):
        return "\n".join(self.dicho)


class ZeroByteDatabaseTests(_Caso):
    """The failure that started all this."""

    def test_a_zero_byte_database_is_critical(self):
        open(self.db, "wb").close()
        report = db_guard.inspect_database(self.db)
        self.assertEqual(report["verdict"], db_guard.CRITICAL)
        self.assertIn("ZERO BYTES", report["reason"])

    def test_the_alarm_is_impossible_to_miss(self):
        open(self.db, "wb").close()
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertIn("[DB GUARD]", self.salida)
        self.assertIn("DATABASE IS DAMAGED", self.salida)
        self.assertIn("ZERO BYTES", self.salida)

    def test_a_truncated_database_is_critical(self):
        with open(self.db, "wb") as fh:
            fh.write(b"SQLite format 3\x00")     # header only, nothing else
        self.assertEqual(db_guard.inspect_database(self.db)["verdict"],
                         db_guard.CRITICAL)

    def test_a_file_that_is_not_sqlite_at_all_is_critical(self):
        with open(self.db, "wb") as fh:
            fh.write(b"this is not a database, it is a thousand bytes of junk"
                     * 40)
        report = db_guard.inspect_database(self.db)
        self.assertEqual(report["verdict"], db_guard.CRITICAL)
        self.assertIn("SQLite signature", report["reason"])

    def test_a_wrecked_interior_page_is_critical(self):
        """SQLite REFUSES this one — it raises instead of reporting.

        Measured, not guessed: overwriting a whole interior page makes
        sqlite3 raise ``DatabaseError('database disk image is malformed')``,
        so ``integrity_check`` never gets to answer. The first draft of the
        guard filed that under 'suspicious'; a destroyed database is CRITICAL.
        """
        _corrupt_range(_make_healthy_db(self.db, rows=2000), 4096, 8192)
        report = db_guard.inspect_database(self.db)
        self.assertEqual(report["verdict"], db_guard.CRITICAL)
        self.assertIn("refuses to read", report["reason"])

    def test_a_wrecked_tail_is_critical_whichever_way_sqlite_complains(self):
        """Half the file destroyed must be CRITICAL — by either route.

        SQLite answers in one of two ways depending on exactly which pages the
        damage hits: it either REFUSES to open the file, or opens it and lets
        ``integrity_check`` report the damage. Both mean the same thing to the
        user, so the test pins the VERDICT, not which sentence came back —
        pinning the wording made this test fail on a layout change that
        mattered to nobody.
        """
        _make_healthy_db(self.db, rows=2000)
        tam = os.path.getsize(self.db)
        _corrupt_range(self.db, tam // 2, tam)
        report = db_guard.inspect_database(self.db)
        self.assertEqual(report["verdict"], db_guard.CRITICAL)
        self.assertTrue(
            "refuses to read" in report["reason"]
            or "damaged" in report["reason"],
            "unexpected explanation: %r" % report["reason"])

    def test_untouched_free_space_is_NOT_called_corruption(self):
        """Scribbling on a b-tree's free space changes nothing SQLite cares
        about — and the guard must not cry wolf over it."""
        _corrupt_range(_make_healthy_db(self.db, rows=25), 2000, 2400)
        self.assertEqual(db_guard.inspect_database(self.db)["verdict"],
                         db_guard.OK)

    def test_a_healthy_database_passes(self):
        _make_healthy_db(self.db)
        report = db_guard.inspect_database(self.db)
        self.assertEqual(report["verdict"], db_guard.OK)
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(report["tables"]["agent_chat"], 25)

    def test_a_missing_database_is_first_run_not_an_alarm(self):
        """A fresh install has no DB yet — that must not cry wolf."""
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.FIRST_RUN)
        self.assertNotIn("DAMAGED", self.salida)


class EvidenceTests(_Caso):
    """The body must survive. Last time it did not, and the cause is unknown."""

    def test_a_broken_database_is_copied_aside_before_anything_else(self):
        open(self.db, "wb").close()
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        evidencia = report.get("evidence")
        self.assertTrue(evidencia, "the broken database was NOT preserved")
        self.assertTrue(os.path.isfile(evidencia))
        self.assertIn("Corrupted", evidencia)
        self.assertIn(evidencia, self.salida,
                      "the alarm must say WHERE the evidence went")

    def test_evidence_is_a_copy_so_the_live_file_stays_put(self):
        _make_healthy_db(self.db, rows=2000)
        _corrupt_range(self.db, 4096, 8192)       # a wreck SQLite really sees
        antes = open(self.db, "rb").read()

        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)

        self.assertTrue(os.path.isfile(self.db), "the live file was MOVED away")
        self.assertEqual(open(self.db, "rb").read(), antes,
                         "the live file was modified")
        self.assertEqual(open(report["evidence"], "rb").read(), antes,
                         "the evidence is not a faithful copy")

    def test_two_bad_starts_do_not_overwrite_the_first_body(self):
        open(self.db, "wb").close()
        primero = db_guard.preserve_evidence(self.db, self.db_root)
        # Same second: the name must still not collide with the first body.
        segundo = db_guard.preserve_evidence(self.db, self.db_root)
        self.assertTrue(primero and segundo)
        if primero == segundo:
            self.skipTest("same-second collision; timestamps have 1s "
                          "resolution — acceptable, the first body survives")
        self.assertTrue(os.path.isfile(primero))


class FailOpenTests(_Caso):
    """A guard that stops Tlamatini booting is worse than the bug it watches."""

    def test_inspect_never_raises_on_a_directory(self):
        os.makedirs(os.path.join(self.tmp, "soy_un_directorio"))
        db_guard.inspect_database(os.path.join(self.tmp, "soy_un_directorio"))

    def test_inspect_never_raises_on_none_or_empty(self):
        for entrada in (None, "", "   "):
            db_guard.inspect_database(entrada)

    def test_guard_survives_an_unwritable_evidence_directory(self):
        open(self.db, "wb").close()
        # db_root points at a FILE, so makedirs inside it must fail.
        roto = os.path.join(self.tmp, "no_soy_carpeta")
        open(roto, "w").close()
        report = db_guard.guard_database(self.db, roto, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.CRITICAL)
        self.assertIn("COULD NOT be preserved", self.salida)

    def test_guard_survives_a_broken_echo(self):
        """Even the shouting can fail without taking startup down."""
        def echo_roto(_):
            raise RuntimeError("la consola se cayó")
        open(self.db, "wb").close()
        db_guard.guard_database(self.db, self.db_root, echo=echo_roto)

    def test_a_corrupt_sentinel_file_is_ignored_not_fatal(self):
        _make_healthy_db(self.db)
        with open(db_guard.sentinel_path(self.db_root), "w",
                  encoding="utf-8") as fh:
            fh.write("{ esto no es json válido")
        self.assertEqual(db_guard.read_sentinel(self.db_root), {})
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.OK)


class NeverRestoresTests(_Caso):
    """Overwriting a database is Angela's call, never the program's."""

    def test_the_guard_does_not_replace_a_broken_database_with_a_backup(self):
        open(self.db, "wb").close()
        respaldo = os.path.join(self.db_root, "db_20260801_130001.sqlite3")
        _make_healthy_db(respaldo, rows=99)

        db_guard.guard_database(self.db, self.db_root, echo=self.echo)

        self.assertEqual(os.path.getsize(self.db), 0,
                         "the guard RESTORED on its own — it must not")
        self.assertIn(respaldo, self.salida,
                      "it should still point at the backup")
        self.assertIn("did NOT restore", self.salida)

    def test_a_zero_byte_backup_is_never_offered_as_a_rescue(self):
        open(self.db, "wb").close()
        inutil = os.path.join(self.db_root, "db_20260801_130001.sqlite3")
        open(inutil, "wb").close()
        self.assertEqual(db_guard.find_newest_backup([self.db_root]), "")


class SilentShrinkTests(_Caso):
    """A database that quietly loses its rows is a failure too."""

    def test_losing_most_rows_between_starts_is_flagged(self):
        _make_healthy_db(self.db, rows=100)
        primero = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(primero["verdict"], db_guard.OK)

        con = sqlite3.connect(self.db)
        con.execute("DELETE FROM agent_chat WHERE id > 5")
        con.commit()
        con.close()

        self.dicho.clear()
        segundo = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(segundo["verdict"], db_guard.SUSPICIOUS)
        self.assertIn("agent_chat", segundo["reason"])
        self.assertIn("DATABASE LOOKS WRONG", self.salida)

    def test_a_table_vanishing_is_flagged(self):
        _make_healthy_db(self.db, rows=40)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE agent_chat")
        con.commit()
        con.close()
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.SUSPICIOUS)
        self.assertIn("disappeared", report["reason"])

    def test_normal_growth_is_not_flagged(self):
        """It must not cry wolf, or everyone learns to ignore it."""
        _make_healthy_db(self.db, rows=20)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        con = sqlite3.connect(self.db)
        con.executemany("INSERT INTO agent_chat (texto) VALUES (?)",
                        [("nuevo %d" % i,) for i in range(500)])
        con.commit()
        con.close()
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.OK)

    def test_a_healthy_start_records_the_fingerprint(self):
        _make_healthy_db(self.db, rows=7)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        huella = db_guard.read_sentinel(self.db_root)
        self.assertEqual(huella["tables"]["agent_chat"], 7)
        self.assertGreater(huella["size"], 0)

    def test_a_bad_start_does_NOT_overwrite_the_good_fingerprint(self):
        """Otherwise one broken boot erases what 'healthy' looked like."""
        _make_healthy_db(self.db, rows=50)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        bueno = db_guard.read_sentinel(self.db_root)

        open(self.db, "wb").close()               # now it is zero bytes
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)

        self.assertEqual(db_guard.read_sentinel(self.db_root), bueno,
                         "the broken start overwrote the last known-good shape")


class CryingWolfTests(_Caso):
    """It must not alarm on normal operation — measured against a real event.

    On 2026-08-05 the guard quarantined a PERFECTLY HEALTHY database **11
    times in 40 minutes**. Every copy in ``DB/Corrupted`` reported
    ``integrity=ok`` with all 211 migrations and all 87 agents, and 8 of the 11
    were byte-identical to the live file. The trigger was ``agent_chatagentrun``
    dropping 16 -> 0 — the wrapped-agent run ledger, which is pruned on purpose.

    Two faults, both fixed and both pinned here:

    1. The row-drop rule fired on tables that churn by design, even though the
       SIZE rule had already been made lenient for that exact reason.
    2. A SUSPICIOUS start returned BEFORE ``write_sentinel``, so the stale
       fingerprint was compared again next start — the same ordinary change
       alarming forever, one copy of the database per start.

    This is not cosmetic. A guard that cries wolf is a guard that gets ignored,
    and the next alarm might be the zero-byte file again.
    """

    def _db_con_tablas(self, tablas):
        """Build the live DB with an exact row count per named table."""
        if os.path.exists(self.db):
            os.remove(self.db)
        con = sqlite3.connect(self.db)
        for nombre, filas in tablas.items():
            con.execute('CREATE TABLE "%s" (id INTEGER PRIMARY KEY, t TEXT)'
                        % nombre)
            con.executemany('INSERT INTO "%s" (t) VALUES (?)' % nombre,
                            [("r%d" % i,) for i in range(filas)])
        con.commit()
        con.close()

    # ── 1. the exact false positive ────────────────────────────────────
    def test_the_run_ledger_emptying_is_NOT_an_alarm(self):
        """agent_chatagentrun 16 -> 0: the real trigger of the 11 quarantines."""
        self._db_con_tablas({"agent_prompt": 117, "agent_chatagentrun": 16})
        self.assertEqual(
            db_guard.guard_database(self.db, self.db_root, echo=self.echo)["verdict"],
            db_guard.OK)

        self._db_con_tablas({"agent_prompt": 117, "agent_chatagentrun": 0})
        self.dicho.clear()
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)

        self.assertEqual(report["verdict"], db_guard.OK,
                         "the run ledger emptying is normal operation, not loss")
        self.assertNotIn("LOOKS WRONG", self.salida)
        self.assertFalse(os.path.isdir(os.path.join(self.db_root, "Corrupted")),
                         "a healthy database was copied aside as evidence")

    def test_clearing_chat_history_and_sessions_is_NOT_an_alarm(self):
        """The docstring's own example: the user clears their chat history."""
        self._db_con_tablas({"agent_prompt": 117, "agent_agentmessage": 400,
                             "django_session": 3})
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self._db_con_tablas({"agent_prompt": 117, "agent_agentmessage": 0,
                             "django_session": 0})
        self.assertEqual(
            db_guard.guard_database(self.db, self.db_root, echo=self.echo)["verdict"],
            db_guard.OK)

    # ── 2. but real loss must STILL be caught ──────────────────────────
    def test_a_precious_table_gutted_is_STILL_flagged(self):
        """The exemption must not blunt the guard on data that matters."""
        self._db_con_tablas({"agent_prompt": 117, "agent_chatagentrun": 16})
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self._db_con_tablas({"agent_prompt": 10, "agent_chatagentrun": 16})
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.SUSPICIOUS)
        self.assertIn("agent_prompt", report["reason"])

    def test_a_volatile_table_VANISHING_is_still_flagged(self):
        """Exempt from the row rule, never from the structural one: a table
        that disappeared is schema damage, not churn."""
        self._db_con_tablas({"agent_prompt": 117, "agent_chatagentrun": 16})
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE agent_chatagentrun")
        con.commit()
        con.close()
        report = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(report["verdict"], db_guard.SUSPICIOUS)
        self.assertIn("disappeared", report["reason"])

    # ── 3. re-baseline: report once, not forever ───────────────────────
    def test_the_same_real_change_is_reported_ONCE_not_every_start(self):
        """The 11-copies fault: it used to return before write_sentinel."""
        self._db_con_tablas({"agent_prompt": 117})
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self._db_con_tablas({"agent_prompt": 10})          # a real drop, once

        primero = db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        self.assertEqual(primero["verdict"], db_guard.SUSPICIOUS)

        self.dicho.clear()
        for _ in range(5):                                  # five more starts
            siguiente = db_guard.guard_database(self.db, self.db_root,
                                                echo=self.echo)
            self.assertEqual(siguiente["verdict"], db_guard.OK,
                             "it alarmed again on an unchanged database")
        self.assertNotIn("LOOKS WRONG", self.salida)

        copias = os.listdir(os.path.join(self.db_root, "Corrupted"))
        self.assertEqual(len(copias), 1,
                         "one copy per start again — this was 9.2 MB of junk")

    def test_a_CRITICAL_database_never_re_baselines_and_keeps_shouting(self):
        """A damaged file must alarm on EVERY start until Angela decides.

        Re-baselining here would record a broken database as the new 'healthy'
        shape and silence the one alarm that actually matters.
        """
        _make_healthy_db(self.db, rows=50)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        bueno = db_guard.read_sentinel(self.db_root)

        open(self.db, "wb").close()                         # zero bytes
        for _ in range(3):
            self.dicho.clear()
            report = db_guard.guard_database(self.db, self.db_root,
                                             echo=self.echo)
            self.assertEqual(report["verdict"], db_guard.CRITICAL)
            self.assertIn("DATABASE IS DAMAGED", self.salida)
        self.assertEqual(db_guard.read_sentinel(self.db_root), bueno,
                         "a broken database was recorded as the healthy shape")

    def test_a_report_we_could_not_inspect_never_becomes_the_baseline(self):
        """Writing a blank fingerprint would blind the next start."""
        _make_healthy_db(self.db, rows=50)
        db_guard.guard_database(self.db, self.db_root, echo=self.echo)
        bueno = db_guard.read_sentinel(self.db_root)

        ciego = {"verdict": db_guard.SUSPICIOUS, "reason": "could not inspect",
                 "size": 0, "tables": {}, "integrity": "", "path": self.db}
        if (ciego.get("verdict") == db_guard.SUSPICIOUS
                and ciego.get("integrity") == "ok" and ciego.get("tables")):
            db_guard.write_sentinel(self.db_root, ciego)    # must NOT happen
        self.assertEqual(db_guard.read_sentinel(self.db_root), bueno)

    # ── 4. evidence cannot grow without bound ──────────────────────────
    def test_evidence_is_capped_but_only_our_own_files(self):
        _make_healthy_db(self.db, rows=5)
        destino = os.path.join(self.db_root, "Corrupted")
        os.makedirs(destino, exist_ok=True)
        for i in range(db_guard.MAX_EVIDENCE_COPIES + 8):
            ruta = os.path.join(destino, "db.sqlite3.broken_2026080%d_0000%02d"
                                % (i % 9, i))
            shutil.copy2(self.db, ruta)
            os.utime(ruta, (1_700_000_000 + i, 1_700_000_000 + i))
        ajeno = os.path.join(destino, "NOT-OURS-keep-me.sqlite3")
        with open(ajeno, "wb") as fh:
            fh.write(b"x")

        nueva = db_guard.preserve_evidence(self.db, self.db_root)

        nuestras = [f for f in os.listdir(destino)
                    if f.startswith("db.sqlite3.broken_")]
        self.assertEqual(len(nuestras), db_guard.MAX_EVIDENCE_COPIES)
        self.assertTrue(os.path.exists(nueva), "the copy just taken was pruned")
        self.assertTrue(os.path.exists(ajeno),
                        "a file this module did not write was deleted")

    def test_pruning_never_raises_on_a_missing_directory(self):
        """Fail-open: losing an old copy must never cost a start."""
        self.assertEqual(
            db_guard._prune_evidence(os.path.join(self.tmp, "nope"), keep=3), 0)


class WiringTests(unittest.TestCase):
    """manage.py must actually call the guard, and in the right order."""

    def setUp(self):
        self.manage = MANAGE_PY.read_text(encoding="utf-8", errors="replace")

    def test_manage_py_calls_the_guard(self):
        self.assertIn("_guard_live_database()", self.manage)
        self.assertIn("from agent import db_guard", self.manage)

    def _call_site(self, nombre):
        """Offset of the module-level CALL, not of a mention in a docstring.

        The first version of this test used ``rindex`` on the bare name and
        matched a docstring further down the file, so it read the order
        backwards. Anchor on a line that is exactly the call, at column 0.
        """
        import re
        m = re.search(r"(?m)^%s\(\)$" % re.escape(nombre), self.manage)
        self.assertIsNotNone(m, "no module-level call to %s()" % nombre)
        return m.start()

    def test_the_guard_runs_AFTER_the_pending_db_swap(self):
        """It must inspect the file Django will open, swap included."""
        self.assertLess(self._call_site("_apply_pending_db_swap"),
                        self._call_site("_guard_live_database"),
                        "the guard must run after DB/ToLoad has been applied")

    def test_the_guard_runs_before_django_is_imported(self):
        self.assertLess(self._call_site("_guard_live_database"),
                        self.manage.index("from django.core.management import"))


if __name__ == "__main__":
    unittest.main()
