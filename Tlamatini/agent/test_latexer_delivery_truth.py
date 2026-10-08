"""LaTeXer must verify the delivered file before reporting a finished PDF.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
import os
import tempfile
import unittest
from unittest import mock

from agent.test_latexer_repair_ladder import LX


class DeliveryTruthTests(unittest.TestCase):
    def result(self, pdf):
        diag = LX._parse_latex_log('Output written on document.pdf (1 page, 1234 bytes).')
        return dict(ok=True, produced=True, pdf=pdf, diag=diag, steps=[], passes=1,
                    work_dir=os.path.dirname(pdf), jobname='document', bibliography='none')

    def finish(self, result):
        outcome, notes = {}, []
        ok = LX._finish_compile(result, {'keep_aux': True},
                                {'distribution': 'miktex', 'engine': 'pdflatex'}, outcome, notes)
        return ok, outcome, notes

    def test_missing_pdf_never_claims_success_or_log_byte_count(self):
        with tempfile.TemporaryDirectory() as root:
            ok, outcome, notes = self.finish(self.result(os.path.join(root, 'missing.pdf')))
        self.assertFalse(ok)
        self.assertEqual(outcome['status'], 'error')
        self.assertEqual(outcome['bytes'], 0)
        self.assertEqual(outcome['output_path'], '')
        self.assertFalse(any('DONE - a CLEAN PDF' in note for note in notes))

    def test_empty_pdf_is_not_a_preservable_build(self):
        with tempfile.TemporaryDirectory() as root:
            pdf = os.path.join(root, 'empty.pdf')
            with open(pdf, 'wb'):
                pass
            self.assertFalse(LX._pdf_is_present(self.result(pdf)))
            self.assertEqual(LX._keep_best_pdf(self.result(pdf), os.path.join(root, 'x.tex')), (None, ''))

    def test_empty_pdf_never_claims_compile_success(self):
        with tempfile.TemporaryDirectory() as root:
            pdf = os.path.join(root, 'empty.pdf')
            with open(pdf, 'wb'):
                pass
            ok, outcome, notes = self.finish(self.result(pdf))
        self.assertFalse(ok)
        self.assertEqual(outcome['bytes'], 0)
        self.assertEqual(outcome['status'], 'error')

    def test_delivery_disappearance_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as root:
            pdf = os.path.join(root, 'built.pdf')
            with open(pdf, 'wb') as handle:
                handle.write(b'%PDF-1.4 content')
            with mock.patch.object(LX, '_deliver_pdf', return_value=(os.path.join(root, 'gone.pdf'), 'delivered')):
                ok, outcome, notes = self.finish(self.result(pdf))
        self.assertFalse(ok)
        self.assertEqual(outcome['output_path'], '')
        self.assertEqual(outcome['bytes'], 0)


if __name__ == '__main__':
    unittest.main()
