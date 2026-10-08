"""Large overfull TeX boxes must never receive the finished-document verdict."""
import os
import tempfile
import unittest

from agent.test_latexer_repair_ladder import LX


class LayoutTruthTests(unittest.TestCase):
    def finish(self, warning):
        with tempfile.TemporaryDirectory() as root:
            pdf = os.path.join(root, 'document.pdf')
            with open(pdf, 'wb') as handle:
                handle.write(b'%PDF-1.4 retained output')
            diag = LX._parse_latex_log(warning + '\nOutput written on document.pdf (1 page, 25 bytes).')
            result = dict(ok=True, produced=True, pdf=pdf, diag=diag, steps=[], passes=1,
                          work_dir=root, jobname='document', bibliography='none')
            outcome, notes = {}, []
            ok = LX._finish_compile(result, {'keep_aux': True, 'output_dir': root},
                                    {'distribution': 'miktex', 'engine': 'lualatex'}, outcome, notes)
            self.assertTrue(os.path.isfile(outcome['output_path']))
            return ok, outcome, notes

    def test_huge_table_overflow_is_not_clean_success(self):
        ok, outcome, notes = self.finish(r'Overfull \hbox (409.79837pt too wide) in paragraph at lines 71--90')
        self.assertFalse(ok)
        self.assertEqual(outcome['status'], 'created_with_findings')
        self.assertGreater(outcome['bytes'], 0)
        self.assertIn('LAYOUT REPAIR REQUIRED', notes[0])
        self.assertFalse(any('THE DOCUMENT IS FINISHED' in note for note in notes))

    def test_vertical_overflow_is_reported(self):
        ok, outcome, notes = self.finish(r'Overfull \vbox (22.5pt too high) detected at line 20')
        self.assertFalse(ok)
        self.assertEqual(outcome['status'], 'created_with_findings')

    def test_small_protrusion_does_not_break_clean_stop(self):
        ok, outcome, notes = self.finish(r'Overfull \hbox (0.75pt too wide) in paragraph at lines 1--2')
        self.assertTrue(ok)
        self.assertEqual(outcome['status'], 'compiled')
        self.assertIn('COMPILED', notes[0])
        self.assertIn('not content completeness or visual quality', notes[0])
        self.assertIn('STOP', notes[0])
        self.assertNotIn('THE DOCUMENT IS FINISHED', notes[0])

    def test_underfull_spacing_is_not_an_overflow(self):
        ok, outcome, notes = self.finish(r'Underfull \hbox (badness 10000) in paragraph at lines 1--2')
        self.assertTrue(ok)
        self.assertEqual(outcome['status'], 'compiled')

    def test_diagnostics_no_longer_dismiss_large_overflows(self):
        diag = LX._parse_latex_log(r'Overfull \hbox (200.0pt too wide) in paragraph at lines 1--2')
        text = LX._format_diagnostics(diag, 'miktex', True, 20000)
        self.assertNotIn('cosmetic, not an error', text)
        self.assertIn('200.0pt', text)


if __name__ == '__main__':
    unittest.main()
