# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Coverage for the binary-content guard on the RAG context-loading chain.

Two layers:

* **Engine tests** exercise ``agent/rag/binary_guard.py`` directly. It is
  stdlib-only, so these import cleanly and run in milliseconds.
* **Wiring contract tests** read ``agent/rag/factory.py`` as SOURCE and pin the
  three ``DirectoryLoader`` call sites, the loader hook and the log calls. This
  mirrors the ``test_django_port_config.py`` trick: it proves the feature is
  actually connected without importing the whole LangChain stack.
"""

import os
import tempfile
import threading
import unittest

from agent.rag import binary_guard


def _write(directory, name, payload):
    path = os.path.join(directory, name)
    mode = 'wb' if isinstance(payload, (bytes, bytearray)) else 'w'
    kwargs = {} if 'b' in mode else {'encoding': 'utf-8'}
    with open(path, mode, **kwargs) as handle:
        handle.write(payload)
    return path


class BinaryGuardExtensionStageTests(unittest.TestCase):
    """Stage 1 — the zero-I/O extension short-circuit."""

    def test_known_binary_extension_is_dropped_without_reading(self):
        # Path deliberately does NOT exist: proving the verdict came from the
        # extension table alone, with no disk access whatsoever.
        verdict = binary_guard.classify_file(r'C:\nowhere\ghost.dll')
        self.assertTrue(verdict.is_binary)
        self.assertEqual('extension', verdict.stage)

    def test_source_extension_is_not_dropped_by_extension_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'module.py', 'print("hola Angela")\n')
            self.assertFalse(binary_guard.classify_file(path).is_binary)

    def test_extra_binary_extensions_from_config_are_honoured(self):
        verdict = binary_guard.classify_file(
            r'C:\nowhere\thing.weird', extra_binary_extensions=frozenset({'.weird'}))
        self.assertTrue(verdict.is_binary)

    def test_force_text_extension_overrides_the_denylist(self):
        """A user rescue must beat the built-in table — always."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'notes.dat', 'plain readable text, no NULs here\n')
            self.assertTrue(binary_guard.classify_file(path).is_binary)
            rescued = binary_guard.classify_file(
                path, force_text_extensions=frozenset({'.dat'}))
            self.assertFalse(rescued.is_binary)


class BinaryGuardContentStageTests(unittest.TestCase):
    """Stages 3-8 — content sniffing."""

    def test_empty_file_is_text(self):
        self.assertFalse(binary_guard.classify_bytes(b'').is_binary)

    def test_plain_ascii_is_text(self):
        verdict = binary_guard.classify_bytes(b'def main():\n    return 42\n')
        self.assertFalse(verdict.is_binary)
        self.assertEqual('text', verdict.stage)

    def test_nul_byte_is_binary(self):
        verdict = binary_guard.classify_bytes(b'some text\x00more text')
        self.assertTrue(verdict.is_binary)
        self.assertEqual('nul-byte', verdict.stage)

    def test_utf16_bom_beats_the_nul_test(self):
        """THE regression guard: UTF-16 text is full of legitimate NUL bytes.

        If the NUL stage ever runs before the BOM stage, every UTF-16 document
        on the user's disk silently vanishes from the context.
        """
        payload = b'\xff\xfe' + 'Angela López Mendoza'.encode('utf-16-le')
        self.assertIn(b'\x00', payload)  # the trap
        verdict = binary_guard.classify_bytes(payload)
        self.assertFalse(verdict.is_binary)
        self.assertEqual('bom', verdict.stage)

    def test_utf8_bom_is_text(self):
        verdict = binary_guard.classify_bytes(b'\xef\xbb\xbf# T\xc3\xadtulo\n')
        self.assertFalse(verdict.is_binary)
        self.assertEqual('bom', verdict.stage)

    def test_utf32_bom_is_text(self):
        verdict = binary_guard.classify_bytes(b'\xff\xfe\x00\x00A\x00\x00\x00')
        self.assertFalse(verdict.is_binary)
        self.assertEqual('bom', verdict.stage)

    def test_accented_utf8_without_bom_is_text(self):
        """Angela's Spanish source files must never be mistaken for binary."""
        payload = 'función: cálculo de la señal — ñ á é í ó ú\n'.encode('utf-8') * 40
        verdict = binary_guard.classify_bytes(payload)
        self.assertFalse(verdict.is_binary)

    def test_latin1_legacy_text_is_kept(self):
        """Undecodable-as-UTF-8 but control-clean = legacy encoding, keep it."""
        payload = 'función y cálculo repetidos '.encode('latin-1') * 40
        verdict = binary_guard.classify_bytes(payload)
        self.assertFalse(verdict.is_binary)

    def test_control_byte_soup_is_binary(self):
        payload = bytes(range(1, 7)) * 200
        verdict = binary_guard.classify_bytes(payload)
        self.assertTrue(verdict.is_binary)
        self.assertEqual('control-ratio', verdict.stage)

    def test_tiny_sample_skips_the_ratio_stage(self):
        """Below MIN_RATIO_SAMPLE a single odd byte must not condemn a file."""
        self.assertFalse(binary_guard.classify_bytes(b'ok\x01').is_binary)


class BinaryGuardSignatureTests(unittest.TestCase):
    """Stage 5 — magic numbers beat a lying extension."""

    CASES = {
        'pe-exe': (b'MZ\x90\x00\x03' + b'\x04' * 64, 'DOS/PE executable'),
        'elf': (b'\x7fELF\x02\x01\x01' + b'\x04' * 64, 'ELF executable'),
        'zip': (b'PK\x03\x04\x14\x00' + b'\x04' * 64, 'ZIP container'),
        'pdf': (b'%PDF-1.7\n' + b'\x04' * 64, 'PDF document'),
        'png': (b'\x89PNG\r\n\x1a\n' + b'\x04' * 64, 'PNG image'),
        'jpeg': (b'\xff\xd8\xff\xe0' + b'\x04' * 64, 'JPEG image'),
        'gzip': (b'\x1f\x8b\x08\x00' + b'\x04' * 64, 'gzip stream'),
        'sqlite': (b'SQLite format 3\x00' + b'\x04' * 64, 'SQLite database'),
        'gguf': (b'GGUF\x03\x00\x00\x00' + b'\x04' * 64, 'GGUF model'),
        'wasm': (b'\x00asm\x01\x00\x00\x00' + b'\x04' * 64, 'WebAssembly module'),
    }

    def test_every_signature_is_detected(self):
        for label, (payload, expected) in self.CASES.items():
            with self.subTest(signature=label):
                verdict = binary_guard.classify_bytes(payload)
                self.assertTrue(verdict.is_binary, f'{label} was not detected')
                self.assertEqual(expected, verdict.reason)

    def test_signature_wins_over_a_lying_text_extension(self):
        """A PNG renamed to notes.md must still be dropped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'notes.md', b'\x89PNG\r\n\x1a\n' + b'\x00' * 512)
            verdict = binary_guard.classify_file(path)
            self.assertTrue(verdict.is_binary)
            self.assertEqual('signature', verdict.stage)


class BinaryGuardFailOpenTests(unittest.TestCase):
    """The guard may never remove a file it is not sure about."""

    def test_missing_file_without_extension_is_text(self):
        verdict = binary_guard.classify_file(os.path.join(tempfile.gettempdir(), 'no_such_file_here'))
        self.assertFalse(verdict.is_binary)
        self.assertEqual('unreadable', verdict.stage)

    def test_directory_path_is_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(binary_guard.classify_file(tmp).is_binary)

    def test_classify_file_never_raises(self):
        for candidate in ('', None, 12345, r'C:\?*<>|invalid'):
            with self.subTest(candidate=candidate):
                try:
                    verdict = binary_guard.classify_file(candidate)
                except Exception as exc:  # pragma: no cover - contract breach
                    self.fail(f'classify_file raised on {candidate!r}: {exc}')
                self.assertFalse(verdict.is_binary)


class BinaryGuardSettingsTests(unittest.TestCase):
    """config.json -> kwargs, fail-open on every malformed value."""

    def test_defaults_when_config_is_empty(self):
        settings = binary_guard.resolve_settings({})
        self.assertTrue(settings['enabled'])
        self.assertEqual(binary_guard.DEFAULT_SAMPLE_BYTES, settings['sample_bytes'])
        self.assertEqual(binary_guard.DEFAULT_CONTROL_RATIO, settings['control_ratio'])

    def test_feature_can_be_disabled(self):
        self.assertFalse(binary_guard.resolve_settings(
            {'binary_context_detection': False})['enabled'])
        self.assertFalse(binary_guard.resolve_settings(
            {'binary_context_detection': 'false'})['enabled'])

    def test_garbage_values_fall_back_to_defaults(self):
        settings = binary_guard.resolve_settings({
            'binary_detection_sample_bytes': 'not-a-number',
            'binary_detection_control_ratio': 99.0,
        })
        self.assertEqual(binary_guard.DEFAULT_SAMPLE_BYTES, settings['sample_bytes'])
        self.assertEqual(binary_guard.DEFAULT_CONTROL_RATIO, settings['control_ratio'])

    def test_non_dict_config_is_tolerated(self):
        self.assertTrue(binary_guard.resolve_settings(None)['enabled'])

    def test_extension_lists_are_normalized(self):
        settings = binary_guard.resolve_settings({
            'binary_detection_extra_binary_extensions': ['*.Foo', 'bar', '.BAZ'],
            'binary_detection_force_text_extensions': '*.log, .cfg',
        })
        self.assertEqual({'.foo', '.bar', '.baz'}, set(settings['extra_binary_extensions']))
        self.assertEqual({'.log', '.cfg'}, set(settings['force_text_extensions']))


class BinaryOmissionRecorderTests(unittest.TestCase):
    """The recorder must survive DirectoryLoader's 12 worker threads."""

    def test_empty_recorder_reports_nothing(self):
        self.assertEqual('', binary_guard.BinaryOmissionRecorder().format_report())

    def test_report_names_every_dropped_file_with_its_reason(self):
        recorder = binary_guard.BinaryOmissionRecorder()
        recorder.record(binary_guard.BinaryVerdict(True, 'signature', 'PNG image', 'a.png'))
        recorder.record(binary_guard.BinaryVerdict(True, 'nul-byte', 'NUL byte', 'b.bin'))
        report = recorder.format_report()
        self.assertIn('2 binary file(s) OMITTED', report)
        self.assertIn('a.png', report)
        self.assertIn('b.bin', report)
        self.assertIn('signature', report)
        self.assertIn('OMITTED', report)
        for line in report.splitlines():
            self.assertTrue(line.startswith('--- [BINARY-GUARD]'),
                            f'log line lacks the grep-able prefix: {line!r}')

    def test_listing_is_capped_but_the_total_is_still_truthful(self):
        recorder = binary_guard.BinaryOmissionRecorder()
        for index in range(250):
            recorder.record(binary_guard.BinaryVerdict(True, 'extension', 'x', f'f{index}.dll'))
        report = recorder.format_report(max_listed=10)
        self.assertIn('250 binary file(s) OMITTED', report)
        self.assertIn('and 240 more', report)

    def test_concurrent_records_are_not_lost(self):
        recorder = binary_guard.BinaryOmissionRecorder()

        def worker(base):
            for index in range(200):
                recorder.record(
                    binary_guard.BinaryVerdict(True, 'extension', 'x', f'{base}-{index}'))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(12 * 200, len(recorder))

    def test_reset_clears_between_loads(self):
        recorder = binary_guard.BinaryOmissionRecorder()
        recorder.record(binary_guard.BinaryVerdict(True, 'extension', 'x', 'a.dll'))
        recorder.reset()
        self.assertEqual(0, len(recorder))
        self.assertEqual('', recorder.format_report())


class BinaryGuardEfficiencyTests(unittest.TestCase):
    """The 'super efficient' requirement, pinned as a contract."""

    def test_at_most_one_read_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'big.txt', 'x' * 200000)
            reads = {'count': 0}
            real_open = open

            def counting_open(*args, **kwargs):
                handle = real_open(*args, **kwargs)
                if 'b' in str(kwargs.get('mode', args[1] if len(args) > 1 else '')):
                    original_read = handle.read

                    def wrapped(*a, **k):
                        reads['count'] += 1
                        return original_read(*a, **k)

                    handle.read = wrapped
                return handle

            import builtins
            builtins.open = counting_open
            try:
                binary_guard.classify_file(path)
            finally:
                builtins.open = real_open
            self.assertLessEqual(reads['count'], 1,
                                 'the guard must sample a file with a single read()')

    def test_only_the_sample_is_read_not_the_whole_file(self):
        """A 4 GB video must cost the same as a README."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, 'huge.unknownext', b'A' * (5 * 1024 * 1024))
            captured = {}
            real_open = open

            def spy_open(*args, **kwargs):
                handle = real_open(*args, **kwargs)
                original_read = handle.read

                def wrapped(size=-1, *a, **k):
                    captured['size'] = size
                    return original_read(size, *a, **k)

                handle.read = wrapped
                return handle

            import builtins
            builtins.open = spy_open
            try:
                binary_guard.classify_file(path, sample_bytes=4096)
            finally:
                builtins.open = real_open
            self.assertEqual(4096, captured.get('size'))


class BinaryGuardFactoryWiringTests(unittest.TestCase):
    """Source contract: prove the engine is actually connected to the chain."""

    @classmethod
    def setUpClass(cls):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, 'rag', 'factory.py'), 'r', encoding='utf-8') as handle:
            cls.source = handle.read()

    def test_factory_imports_the_engine(self):
        self.assertIn('from . import binary_guard', self.source)

    def test_custom_text_loader_accepts_and_applies_the_settings(self):
        self.assertIn('binary_guard_settings=None', self.source)
        self.assertIn('binary_guard.classify_file(', self.source)
        self.assertIn('binary_guard.omission_recorder.record(verdict)', self.source)

    def test_all_three_directory_loaders_receive_the_settings(self):
        """Miss one call site and that context path silently loads binaries."""
        self.assertEqual(3, self.source.count('"binary_guard_settings": binary_settings'))

    def test_every_load_announces_its_omissions(self):
        # Count the DEFINITION and the CALL SITES separately - counting the
        # bare name matches both and silently inflates the total.
        self.assertEqual(1, self.source.count('def _announce_binary_omissions('))
        self.assertEqual(3, self.source.count('_announce_binary_omissions(binary_settings,'))
        self.assertEqual(1, self.source.count('def _announce_binary_guard_settings('))
        self.assertEqual(2, self.source.count('_announce_binary_guard_settings(binary_settings)'))

    def test_settings_are_resolved_in_both_entry_points(self):
        self.assertEqual(2, self.source.count('binary_guard.resolve_settings(config)'))

    def test_binary_drop_uses_the_same_valueerror_mechanism_as_user_omissions(self):
        """DirectoryLoader(silent_errors=True) swallows ValueError — that is the
        contract both the name-based omissions and this guard ride on."""
        self.assertIn('is excluded as binary content', self.source)
        self.assertIn('silent_errors=True', self.source)

    def test_log_lines_are_grepable_in_the_application_log(self):
        self.assertIn('--- [BINARY-GUARD]', self.source)


class BinaryGuardTableSanityTests(unittest.TestCase):
    """Guard against a careless edit to the extension tables."""

    def test_tables_do_not_overlap(self):
        overlap = binary_guard.BINARY_EXTENSIONS & binary_guard.TEXT_EXTENSIONS
        self.assertEqual(set(), overlap,
                         f'an extension cannot be both text and binary: {overlap}')

    def test_every_extension_is_lowercase_and_dotted(self):
        for ext in binary_guard.BINARY_EXTENSIONS | binary_guard.TEXT_EXTENSIONS:
            self.assertTrue(ext.startswith('.'), f'{ext} lacks a leading dot')
            self.assertEqual(ext.lower(), ext, f'{ext} is not lower-cased')

    def test_core_source_extensions_are_never_binary(self):
        for ext in ('.py', '.js', '.md', '.json', '.yaml', '.html', '.css', '.txt',
                    '.pmt', '.flw', '.csv', '.sql', '.ps1'):
            self.assertNotIn(ext, binary_guard.BINARY_EXTENSIONS)

    def test_longest_signature_constant_matches_the_table(self):
        expected = max(len(sig) for sig, _ in binary_guard.MAGIC_SIGNATURES)
        self.assertEqual(expected, binary_guard._MAX_SIGNATURE_LEN)

    def test_bom_table_is_ordered_longest_prefix_first(self):
        """\\xff\\xfe is a prefix of the UTF-32-LE BOM: order decides correctness."""
        boms = [bom for bom, _ in binary_guard.BOM_SIGNATURES]
        utf32_le = boms.index(b'\xff\xfe\x00\x00')
        utf16_le = boms.index(b'\xff\xfe')
        self.assertLess(utf32_le, utf16_le,
                        'UTF-32-LE BOM must be tested before its UTF-16-LE prefix')


class BinaryGuardDocumentationTests(unittest.TestCase):
    """Angela's rule: a feature is not shipped until the docs say so."""

    REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

    REQUIRED = {
        os.path.join('CLAUDE.md'): 'binary',
        os.path.join('docs', 'claude', 'architecture.md'): 'BINARY-GUARD',
        os.path.join('docs', 'claude', 'gotchas.md'): 'binary_context_detection',
        os.path.join('docs', 'claude', 'recent-fixes.md'): 'binary_guard',
        os.path.join('README.md'): 'binary',
    }

    def test_documentation_mentions_the_feature(self):
        for relative, needle in self.REQUIRED.items():
            path = os.path.join(self.REPO_ROOT, relative)
            with self.subTest(document=relative):
                self.assertTrue(os.path.isfile(path), f'missing document: {path}')
                with open(path, 'r', encoding='utf-8') as handle:
                    body = handle.read()
                # assertTrue, not assertIn: a failing assertIn would dump the
                # entire markdown file into the test report.
                self.assertTrue(needle.lower() in body.lower(),
                                f'{relative} does not document the binary guard')

    def test_self_knowledge_file_knows_about_the_guard(self):
        path = os.path.join(self.REPO_ROOT, 'Tlamatini', 'agent', 'Tlamatini.md')
        if not os.path.isfile(path):
            self.skipTest('Tlamatini.md not present in this checkout')
        with open(path, 'r', encoding='utf-8') as handle:
            body = handle.read().lower()
        self.assertTrue('binary' in body, 'Tlamatini.md does not mention the binary guard')


if __name__ == '__main__':
    unittest.main()
