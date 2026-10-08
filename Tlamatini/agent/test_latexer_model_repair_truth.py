"""A repair must typeset the document, not print its source as a code listing.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
import json
import unittest
from unittest import mock

from agent.test_latexer_repair_ladder import LX


class ModelRepairTruthTests(unittest.TestCase):
    def document(self, body):
        return '\\documentclass{article}\n\\begin{document}\n' + body + '\n\\end{document}'

    def repair(self, source, answer):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'response': answer}).encode('utf-8')
        trace = []
        with mock.patch.object(LX.urllib.request, 'urlopen', return_value=response):
            result = LX._ollama_repair(source, {}, {'repair_model': 'configured-model'}, trace)
        return result, trace

    def test_rejects_whole_document_replaced_with_literal_source(self):
        # The live chat repair wrapped corrupt generated LaTeX in lstlisting.
        # TeX then returned zero errors while the PDF contained only source code.
        body = r'\section{Hello from Tlamatini} LaTeXer is working. $E \eq mc^2$'
        source = self.document(body)
        for start, end in (
            (r'\begin{lstlisting}', r'\end{lstlisting}'),
            (r'\begin{verbatim}', r'\end{verbatim}'),
            (r'\begin{Verbatim}[fontsize=\small]', r'\end{Verbatim}'),
            (r'\begin{minted}{latex}', r'\end{minted}'),
        ):
            with self.subTest(environment=start):
                result, trace = self.repair(source, self.document(start + '\n' + body + '\n' + end))
                self.assertEqual(result, source)
                self.assertFalse(trace[-1]['applied'])
                self.assertIn('literal source', trace[-1]['detail'])

    def test_accepts_actual_latex_correction(self):
        source = self.document(r'LaTeXer is working. $E \eq mc^2$')
        answer = source.replace(r'\eq', '=')
        result, trace = self.repair(source, answer)
        self.assertEqual(result, answer)
        self.assertTrue(trace[-1]['applied'])

    def test_preserves_intentional_code_listing_documents(self):
        body = '\\begin{lstlisting}\nprint("Hello")\n\\end{lstlisting}'
        source = self.document(body)
        answer = source.replace('{article}', '[11pt]{article}')
        result, trace = self.repair(source, answer)
        self.assertEqual(result, answer)
        self.assertTrue(trace[-1]['applied'])
