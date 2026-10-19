# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Real filesystem setup regressions; run in a visible foreground console."""
from pathlib import Path
from contextlib import nullcontext
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from setup_recovery import Recovery, remove_tree  # noqa: E402
from install import FancyInstaller, PRESERVED_AGENTS_MARKER  # noqa: E402
from uninstall import FancyUninstaller, PRESERVED_WHEN_NOT_EMPTY, removal_cleanup_pending, CLEANUP_RECEIPT  # noqa: E402


class EmptyPackageDirectoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'Tlamatini'

    def test_failed_clean_install_removes_empty_package_directories(self):
        recovery = Recovery(self.target)
        recovery.prepare(['application.bin'], windows=False,
                         created_directories=['agents/empty', 'DB', 'content_generated'])
        for relative in ('agents/empty', 'DB', 'content_generated'):
            (self.target / relative).mkdir(parents=True, exist_ok=True)
        (self.target / 'application.bin').write_bytes(b'partial extraction')
        recovery.rollback()
        self.assertFalse(self.target.exists())

    def test_reinstall_rollback_preserves_preexisting_empty_directory(self):
        original = self.target / 'content_generated'
        original.mkdir(parents=True)
        recovery = Recovery(self.target)
        recovery.prepare([], windows=False, created_directories=['content_generated', 'agents/empty'])
        (self.target / 'agents/empty').mkdir(parents=True)
        recovery.rollback()
        self.assertEqual(list(self.target.iterdir()), [original])
        self.assertEqual(list(original.iterdir()), [])

    def test_rollback_keeps_a_file_added_by_another_actor(self):
        recovery = Recovery(self.target)
        recovery.prepare([], windows=False, created_directories=['content_generated'])
        folder = self.target / 'content_generated'
        folder.mkdir()
        document = folder / 'keep.txt'
        document.write_bytes(b'created after setup preparation')
        recovery.rollback()
        self.assertEqual(document.read_bytes(), b'created after setup preparation')

    def test_directory_collision_is_refused_before_journal_creation(self):
        self.target.mkdir()
        collision = self.target / 'agents'
        collision.write_bytes(b'keep the existing file')
        recovery = Recovery(self.target)
        with self.assertRaisesRegex(RuntimeError, 'occupied by a file'):
            recovery.prepare([], windows=False, created_directories=['agents'])
        self.assertFalse(recovery.folder.exists())
        self.assertEqual(collision.read_bytes(), b'keep the existing file')

    def test_unsafe_directory_is_refused_before_mutation(self):
        recovery = Recovery(self.target)
        with self.assertRaisesRegex(ValueError, 'Unsafe recovery path'):
            recovery.prepare([], windows=False, created_directories=['../outside'])
        self.assertFalse(self.target.exists())


class ReinstallPreservedCatalogTests(unittest.TestCase):
    """Real extraction/recovery with UI and Windows integration isolated.

    Package integrity has its own suite; this tiny ZIP isolates the installer
    transaction. These source regressions do not certify a compiled installer.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'Tlamatini'
        self.marker = self.target / PRESERVED_AGENTS_MARKER
        self.marker.parent.mkdir(parents=True)
        self.marker.write_bytes(b'{"preserved":true,"note":"original receipt"}\n')
        self.original_marker = self.marker.read_bytes()
        self.manifest = self.marker.parent / '_tlamatini_agents_manifest.json'
        self.manifest.write_bytes(b'{"agents_root_kind":"preserved"}\n')
        self.original_manifest = self.manifest.read_bytes()
        self.user_file = self.marker.parent / 'custom-agent.txt'
        self.user_file.write_bytes(b'user agent retained byte for byte')
        self.package = Path(self.temp.name) / 'pkg.zip'
        self.payload = {'agents/_tlamatini_agents_manifest.json': b'{"agents_root_kind":"installed"}\n',
                        'Tlamatini.exe': b'isolated filesystem fixture'}
        with zipfile.ZipFile(self.package, 'w') as archive:
            for name, content in self.payload.items():
                archive.writestr(name, content)
        self.installer = FancyInstaller.__new__(FancyInstaller)
        self.installer.zip_path = str(self.package)
        self.installer.root = Mock()
        self.installer.root.after.side_effect = lambda delay, callback, *args: callback(*args)
        for method in ('_set_progress', '_activate_step', '_mark_step',
                       '_copy_uninstaller', '_register_programs_entry',
                       '_register_companion_discovery', '_run_ps1',
                       '_restart_explorer', '_show_success', '_show_error'):
            setattr(self.installer, method, Mock())

    def run_install(self):
        class FileOnlyRecovery(Recovery):
            def prepare(self, names, **kwargs):
                super().prepare(names, windows=False, **kwargs)

        document = {'files': {name: {'bytes': len(content)}
                              for name, content in self.payload.items()}}
        with patch('install.verify_package', return_value=document), \
                patch('install.setup_lock', side_effect=nullcontext), \
                patch('install.owned_processes', return_value=[]), \
                patch('install.Recovery', FileOnlyRecovery):
            self.installer._run_install(str(self.target))

    def test_success_clears_uninstall_marker_and_keeps_user_agents(self):
        self.run_install()
        self.installer._show_success.assert_called_once_with(str(self.target))
        self.installer._show_error.assert_not_called()
        self.assertFalse(self.marker.exists())
        self.assertEqual(json.loads(self.manifest.read_bytes())['agents_root_kind'], 'installed')
        self.assertEqual(self.user_file.read_bytes(), b'user agent retained byte for byte')
        self.assertFalse((self.target / 'Temp/.setup-recovery').exists())

    def test_later_failure_restores_both_original_metadata_files(self):
        self.installer._run_ps1.side_effect = RuntimeError('late shortcut failure')
        self.run_install()
        self.installer._show_success.assert_not_called()
        self.assertIn('late shortcut failure', self.installer._show_error.call_args.args[0])
        self.assertEqual(self.marker.read_bytes(), self.original_marker)
        self.assertEqual(self.manifest.read_bytes(), self.original_manifest)
        self.assertEqual(self.user_file.read_bytes(), b'user agent retained byte for byte')
        self.assertFalse((self.target / 'Tlamatini.exe').exists())
        self.assertFalse((self.target / 'Temp/.setup-recovery').exists())

    def test_install_without_prior_marker_succeeds(self):
        self.marker.unlink()
        self.run_install()
        self.installer._show_success.assert_called_once()
        self.assertFalse(self.marker.exists())

    def test_locked_marker_reports_warning_without_failing_install(self):
        import os
        unlink = os.unlink

        def refuse_marker(path, *args, **kwargs):
            if Path(path) == self.marker:
                raise PermissionError('locked by test')
            return unlink(path, *args, **kwargs)

        with patch('install.os.unlink', side_effect=refuse_marker):
            self.run_install()
        self.installer._show_success.assert_called_once()
        self.assertEqual(self.marker.read_bytes(), self.original_marker)
        self.assertEqual(len(self.installer.setup_warnings), 1)
        self.assertIn('locked by test', self.installer.setup_notice)


class RemovalRenameRecoveryTests(unittest.TestCase):
    """Native filesystem failures and crash windows, never a personal install."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'Tlamatini'
        self.target.mkdir()
        self.payload = self.file('python/Lib/package/data.bin', b'application payload' * 500)
        self.executable = self.file('Tlamatini.exe', b'application image')
        self.kept = ['agents', *PRESERVED_WHEN_NOT_EMPTY]
        self.content = {}
        for name in self.kept:
            path = self.file(name + '/nested/keep-ñ.txt', ('original ' + name).encode())
            self.content[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.file('Temp/UpdateMedia/cache.bin', b'temporary update download')

    def file(self, name, content):
        path = self.target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def prepare(self):
        recovery = Recovery(self.target)
        recovery.prepare_removal(self.kept, windows=False)
        return recovery

    def assert_content_unchanged(self):
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in self.content}, self.content)

    def stage_all(self, recovery):
        for name in recovery.data['moves']:
            recovery.stage_removal(name)

    def lock(self, path, *, directory=False, share=0):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                      ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(path), 0x80000000, share, None, 3,
                                   0x02000000 if directory else 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
        return lambda: kernel.CloseHandle(handle)

    def test_payload_is_never_copied_or_hashed_before_removal(self):
        with patch('setup_recovery.shutil.copy2', wraps=shutil.copy2) as copy, \
                patch('setup_recovery.digest', side_effect=AssertionError('Payload hashing is forbidden')):
            recovery = self.prepare()
            self.stage_all(recovery)
            self.assertEqual(recovery.commit(), '')
            copy.assert_not_called()
        self.assertFalse(self.payload.exists())
        self.assertFalse(self.executable.exists())
        self.assert_content_unchanged()
        self.assertTrue((self.target / 'Temp/UpdateMedia/cache.bin').is_file())

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_transient_journal_lock_retries_atomic_replacement(self):
        from setup_recovery import atomic_json
        journal = self.target / 'atomic-journal.json'
        atomic_json(journal, {'state': 'original'})
        release = self.lock(journal)
        timer = threading.Timer(.15, release)
        timer.start()
        try:
            atomic_json(journal, {'state': 'replacement'})
        finally:
            timer.join(timeout=5)
        self.assertEqual(json.loads(journal.read_text()), {'state': 'replacement'})
        self.assertFalse(journal.with_suffix('.new').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_persistent_journal_lock_is_bounded_and_keeps_both_documents(self):
        from setup_recovery import atomic_json
        journal = self.target / 'atomic-journal.json'
        atomic_json(journal, {'state': 'original'})
        release = self.lock(journal)
        started = time.monotonic()
        try:
            with patch('setup_recovery.JOURNAL_REPLACE_RETRY_SECONDS', .15):
                with self.assertRaises(PermissionError):
                    atomic_json(journal, {'state': 'replacement'})
        finally:
            release()
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual(json.loads(journal.read_text()), {'state': 'original'})
        self.assertEqual(json.loads(journal.with_suffix('.new').read_text()), {'state': 'replacement'})

    def test_recovery_restores_exact_file_identities_without_copying(self):
        original_id = self.payload.stat().st_ino
        recovery = self.prepare()
        self.stage_all(recovery)
        with patch('setup_recovery.shutil.copy2', side_effect=AssertionError('No payload copying')):
            Recovery(self.target).recover_previous()
        self.assertEqual(self.payload.stat().st_ino, original_id)
        self.assertEqual(self.payload.read_bytes(), b'application payload' * 500)
        self.assert_content_unchanged()

    def test_process_exit_between_rename_and_receipt_is_recoverable(self):
        recovery = self.prepare()
        from setup_recovery import atomic_json
        calls = 0

        def interrupt_after_rename(path, document):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('simulated process exit after rename')
            return atomic_json(path, document)

        with patch('setup_recovery.atomic_json', side_effect=interrupt_after_rename):
            with self.assertRaisesRegex(RuntimeError, 'simulated process exit'):
                recovery.stage_removal('python')
        self.assertFalse(self.payload.exists())
        self.assertTrue(Recovery(self.target).recover_previous())
        self.assertEqual(self.payload.read_bytes(), b'application payload' * 500)
        self.assert_content_unchanged()

    def test_recovery_never_overwrites_new_content_at_original_path(self):
        recovery = self.prepare()
        recovery.stage_removal('Tlamatini.exe')
        self.executable.write_bytes(b'new content from another actor')
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            Recovery(self.target).recover_previous()
        self.assertEqual(self.executable.read_bytes(), b'new content from another actor')
        self.assertEqual((recovery.folder / 'quarantine/Tlamatini.exe').read_bytes(), b'application image')
        self.executable.unlink()
        Recovery(self.target).recover_previous()
        self.assertEqual(self.executable.read_bytes(), b'application image')

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_locked_application_fails_before_payload_deletion_then_restores(self):
        recovery = self.prepare()
        recovery.stage_removal('python')
        release = self.lock(self.executable)
        started = time.monotonic()
        try:
            with self.assertRaises(PermissionError):
                recovery.stage_removal('Tlamatini.exe')
        finally:
            release()
        recovery.rollback()
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(self.executable.read_bytes(), b'application image')
        self.assertTrue(self.payload.is_file())
        self.assert_content_unchanged()

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_committed_cleanup_failure_keeps_journal_and_never_restores_app(self):
        recovery = self.prepare()
        recovery.stage_removal('python')
        held = recovery.folder / 'quarantine/python/Lib/package/data.bin'
        release = self.lock(held)
        try:
            self.assertIn('recovery copy could not be cleared', recovery.commit())
            self.assertEqual(json.loads(recovery.journal.read_text())['state'], 'committed')
            self.assertFalse(self.payload.exists())
        finally:
            release()
        Recovery(self.target).recover_previous()
        self.assertFalse(self.payload.exists())
        self.assertFalse(recovery.folder.exists())
        self.assert_content_unchanged()

    def test_cleanup_deadline_retains_resumable_committed_journal(self):
        recovery = self.prepare()
        recovery.stage_removal('python')
        recovery.cleanup_deadline = time.monotonic() - 1
        self.assertIn('could not be cleared', recovery.commit())
        self.assertEqual(json.loads(recovery.journal.read_text())['state'], 'committed')
        Recovery(self.target).recover_previous()
        self.assertFalse(self.payload.exists())
        self.assert_content_unchanged()

    @unittest.skipUnless(os.name == 'nt', 'Windows directory sharing semantics')
    def test_locked_update_media_is_cleanup_warning_not_application_rollback(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        self.assertEqual(recovery.commit(), '')
        cache = self.target / 'Temp/UpdateMedia'
        (cache / 'cache.bin').unlink()
        release = self.lock(cache, directory=True)
        app = FancyUninstaller.__new__(FancyUninstaller)
        app.cleanup_warnings = []
        app._cleanup_deadline = time.monotonic() + 10
        app._set_progress = Mock()
        try:
            app._cleanup_temporary_files(str(self.target))
        finally:
            release()
        self.assertEqual(len(app.cleanup_warnings), 1)
        self.assertIn('UpdateMedia', app.cleanup_warnings[0])
        self.assertFalse(self.executable.exists())
        self.assertFalse(self.payload.exists())
        self.assert_content_unchanged()
        app.cleanup_warnings = []
        app._cleanup_temporary_files(str(self.target))
        self.assertEqual(app.cleanup_warnings, [])
        self.assertFalse((self.target / 'Temp').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows directory sharing semantics')
    def test_locked_empty_temp_root_is_not_reported_as_complete(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        self.assertEqual(recovery.commit(), '')
        remove_tree(self.target / 'Temp/UpdateMedia')
        folder = self.target / 'Temp'
        release = self.lock(folder, directory=True, share=3)
        app = self.cleanup_app(recovery)
        try:
            with patch('uninstall.setup_lock', side_effect=nullcontext):
                app._run_cleanup_retry(str(self.target))
        finally:
            release()
        self.assertIn('Temporary cleanup could not finish', app.setup_notice)
        self.assertTrue(folder.is_dir())
        self.assert_content_unchanged()

    def test_metadata_and_legacy_journals_remain_recoverable(self):
        marker = self.file('agents/.tlamatini-preserved-agents.json', b'original marker')
        recovery = self.prepare()
        self.stage_all(recovery)
        marker.write_bytes(b'changed by uninstall')
        recovery.rollback()
        self.assertEqual(marker.read_bytes(), b'original marker')
        legacy = Recovery(self.target)
        legacy.prepare(['Tlamatini.exe'], windows=False)
        self.executable.write_bytes(b'partial legacy modification')
        Recovery(self.target).recover_previous()
        self.assertEqual(self.executable.read_bytes(), b'application image')

    def test_recovery_progress_advances_even_when_files_already_match(self):
        progress = []
        recovery = Recovery(self.target, rollback_progress=progress.append)
        recovery.prepare(['Tlamatini.exe'], windows=False)
        recovery.rollback()
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 1)
        self.assertTrue(any(0 < value < 1 for value in progress))

    def cleanup_app(self, recovery):
        app = FancyUninstaller.__new__(FancyUninstaller)
        app._cleanup_recovery = recovery
        app._set_progress = Mock()
        app._show_success = Mock()
        app.root = Mock()
        app.root.after.side_effect = lambda delay, callback, *args: callback(*args)
        return app

    def pipeline_app(self):
        app = self.cleanup_app(None)
        app.ui = Mock()
        for method in ('_activate_step', '_mark_step', '_run_ps1',
                       '_unregister_programs_entry', '_restart_explorer', '_show_error'):
            setattr(app, method, Mock())
        return app

    def run_pipeline(self, app):
        class FileOnlyRecovery(Recovery):
            def prepare_removal(self, kept_names, **kwargs):
                return super().prepare_removal(kept_names, windows=False)

        with patch('uninstall.setup_lock', side_effect=nullcontext), \
                patch('uninstall.stop_owned_workers', return_value={'stopped': [], 'survivors': []}), \
                patch('uninstall.Recovery', FileOnlyRecovery), \
                patch('setup_logging.registry_context'):
            app._run_uninstall(str(self.target))

    def test_full_removal_pipeline_preserves_content_and_finishes_cleanup(self):
        self.file('unregister_flw.ps1', b'registration fixture')
        app = self.pipeline_app()
        self.run_pipeline(app)
        app._show_success.assert_called_once_with(str(self.target))
        app._show_error.assert_not_called()
        self.assertEqual(app.setup_notice, '')
        self.assertEqual({p.name for p in self.target.iterdir()}, set(self.kept))
        self.assert_content_unchanged()

    def test_late_pipeline_failure_restores_payload_and_never_schedules_deletion(self):
        self.file('unregister_flw.ps1', b'registration fixture')
        app = self.pipeline_app()
        app._unregister_programs_entry.side_effect = RuntimeError('late integration failure')
        original_id = self.payload.stat().st_ino
        self.run_pipeline(app)
        app._show_success.assert_not_called()
        self.assertIn('were restored', app._show_error.call_args.args[0])
        self.assertEqual(self.payload.stat().st_ino, original_id)
        self.assertEqual(app.deferred_in_place, [])
        self.assertEqual(app.removal_target, '')
        self.assertFalse((self.target / 'Temp/.setup-recovery').exists())
        self.assert_content_unchanged()

    def test_cleanup_retry_finishes_committed_removal_without_restoring(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        recovery.cleanup_deadline = time.monotonic() - 1
        self.assertTrue(recovery.commit())
        app = self.cleanup_app(recovery)
        with patch('uninstall.setup_lock', side_effect=nullcontext):
            app._run_cleanup_retry(str(self.target))
        self.assertEqual(app.setup_notice, '')
        self.assertFalse(self.payload.exists())
        self.assertFalse((self.target / 'Temp').exists())
        self.assert_content_unchanged()
        app._show_success.assert_called_once_with(str(self.target))

    def test_cleanup_retry_refuses_new_installation(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        recovery.cleanup_deadline = time.monotonic() - 1
        recovery.commit()
        self.executable.write_bytes(b'new installation image')
        app = self.cleanup_app(recovery)
        with patch('uninstall.setup_lock', side_effect=nullcontext):
            app._run_cleanup_retry(str(self.target))
        self.assertIn('protect the new installation', app.setup_notice)
        self.assertEqual(self.executable.read_bytes(), b'new installation image')
        self.assertTrue(recovery.journal.exists())
        self.assert_content_unchanged()

    def test_cleanup_retry_repeatedly_refuses_another_journal(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        recovery.cleanup_deadline = time.monotonic() - 1
        recovery.commit()
        different = dict(recovery.data, temp_existed=False)
        recovery.journal.write_text(json.dumps(different))
        app = self.cleanup_app(recovery)
        with patch('uninstall.setup_lock', side_effect=nullcontext):
            for _ in range(2):
                app._run_cleanup_retry(str(self.target))
                self.assertIn('changed since this removal', app.setup_notice)
                self.assertTrue(recovery.journal.exists())
                self.assertTrue((recovery.folder / 'quarantine/python').exists())
        self.assert_content_unchanged()

    def test_interrupted_rollback_cleanup_does_not_restore_again(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        with patch.object(recovery, 'discard', side_effect=OSError('cleanup interrupted')):
            with self.assertRaisesRegex(OSError, 'cleanup interrupted'):
                recovery.rollback()
        self.assertEqual(json.loads(recovery.journal.read_text())['state'], 'committed')
        self.assertTrue(self.payload.exists())
        with patch('setup_recovery.Recovery.rollback', side_effect=AssertionError('already restored')):
            Recovery(self.target).recover_previous()
        self.assertTrue(self.payload.exists())
        self.assert_content_unchanged()

    def test_new_wizard_resumes_committed_cleanup_without_running_windows_removal(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        recovery.commit(defer_cleanup=True)
        self.assertTrue(removal_cleanup_pending(self.target))
        app = self.pipeline_app()
        self.run_pipeline(app)
        app._show_success.assert_called_once()
        app._show_error.assert_not_called()
        app._run_ps1.assert_not_called()
        app._unregister_programs_entry.assert_not_called()
        self.assertEqual({p.name for p in self.target.iterdir()}, set(self.kept))
        self.assert_content_unchanged()

    @unittest.skipUnless(os.name == 'nt', 'Windows directory sharing semantics')
    def test_new_wizard_finishes_temp_only_cleanup_from_durable_receipt(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        recovery.commit(defer_cleanup=True)
        cache = self.target / 'Temp/UpdateMedia'
        (cache / 'cache.bin').unlink()
        release = self.lock(cache, directory=True)
        app = self.pipeline_app()
        try:
            self.run_pipeline(app)
        finally:
            release()
        self.assertIn('Temporary cleanup', app.setup_notice)
        self.assertFalse(recovery.journal.exists())
        self.assertTrue((self.target / CLEANUP_RECEIPT).is_file())
        self.assertTrue(removal_cleanup_pending(self.target))
        replacement = self.pipeline_app()
        self.run_pipeline(replacement)
        replacement._show_success.assert_called_once()
        replacement._run_ps1.assert_not_called()
        self.assertEqual(replacement.setup_notice, '')
        self.assertEqual({p.name for p in self.target.iterdir()}, set(self.kept))
        self.assert_content_unchanged()

    def test_rollback_receipt_is_not_a_completed_removal(self):
        recovery = self.prepare()
        self.stage_all(recovery)
        with patch.object(recovery, 'discard', side_effect=OSError('cleanup interrupted')):
            with self.assertRaises(OSError):
                recovery.rollback()
        self.assertFalse(removal_cleanup_pending(self.target))
        self.assertEqual(recovery.data['outcome'], 'restored')
        self.assertTrue(self.payload.exists())
        self.assert_content_unchanged()

    def test_cleanup_receipt_must_match_the_original_directory_identity(self):
        receipt = self.target / CLEANUP_RECEIPT
        receipt.write_text(json.dumps({'schema': 1, 'state': 'removed', 'target': str(self.target),
                                       'identity': [0, 0]}))
        self.assertFalse(removal_cleanup_pending(self.target))
        self.assert_content_unchanged()

    @unittest.skipUnless(os.name == 'nt', 'Windows junctions')
    def test_cleanup_never_traverses_directory_junction(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        protected = outside / 'keep.txt'
        protected.write_bytes(b'outside the installation')
        link = self.payload.parent / 'junction'
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(outside)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        remove_tree(self.target / 'python')
        self.assertEqual(protected.read_bytes(), b'outside the installation')
        self.assert_content_unchanged()


if __name__ == '__main__':
    unittest.main(verbosity=2)
