# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Design invariants, caller contracts and copied-pool execution.

Real engine/render validation lives in scripts/verify_latexer_styles.py; these
tests also run on machines without TeX and never fake a successful PDF build.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    from .test_latexer_agent import _m, _has_latex
except ImportError:
    from test_latexer_agent import _m, _has_latex


class StyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = _m()
        cls.design, cls.styles = cls.agent._style_modules()

    def test_catalogue_has_thirty_distinct_identities_and_motifs(self):
        catalog = self.styles.style_catalog()
        self.assertEqual(len(catalog), 30)
        self.assertEqual(len({r['motif'] for r in catalog}), 30)
        self.assertEqual({r['family'] for r in catalog},
                         {'editorial', 'playful', 'cyberpunk', 'cosmic', 'electronics', 'tlamatini'})
        for row in catalog:
            for alias in [row['id'], row['label'], *row['aliases']]:
                self.assertEqual(self.styles.normalise_style(alias), row['id'])
        json.dumps(catalog)

    def test_selection_is_explicit_and_accent_insensitive(self):
        self.assertEqual(self.styles.normalise_style('ELECTRÓNICA'), 'circuit_board')
        self.assertEqual(self.styles.normalise_style('Baby Sky'), 'baby_sky')
        with self.assertRaises(ValueError):
            self.styles.normalise_style('write a baby sky report')
        self.assertNotIn('LaTeXer style:', self.agent._build_document({'content': 'cyberpunk baby sky'}))

    def test_all_text_roles_remain_readable_after_seed_and_print_override(self):
        for key in self.styles.STYLES:
            for mode in ('screen', 'print'):
                for seed in ('', '#FFFFFF', '#000000', '#777777', '#FFFF00', '#FF00FF'):
                    with self.subTest(style=key, mode=mode, seed=seed):
                        theme = self.styles.build_theme(dict(style=key, style_mode=mode, predominant_color=seed))
                        p = theme['palette']
                        pairs = [(role, 'Background') for role in ('Ink', 'Primary', 'Secondary', 'Muted')]
                        pairs += [('SurfaceInk', 'Surface'), ('SurfaceAccent', 'Surface'), ('OnPrimary', 'Primary')]
                        for fg, bg in pairs:
                            self.assertGreaterEqual(self.styles.contrast(p[fg], p[bg]), 4.5, (key, fg, bg))
                        if mode == 'print':
                            self.assertEqual(p['Background'], 'FFFFFF')

    def test_bad_options_refuse_instead_of_silently_falling_back(self):
        for changes in ({'style': 'not-a-style'}, {'style_mode': 'hologram'},
                        {'style_decoration': 'more'}, {'style_cover': 'maybe'},
                        {'predominant_color': r'}\input{secret}'}, {'documentclass': 'customthesis'}):
            cfg = dict(style='baby_sky', **{k: v for k, v in changes.items() if k != 'style'})
            cfg.update(changes)
            self.assertTrue(self.agent._style_preflight('create_file', cfg))

    def test_legacy_sources_are_identical_for_empty_and_plain_styles(self):
        for name in self.agent._TEMPLATES:
            cfg = dict(title='Title', author='A', content=r'Table: A & B \\')
            original = self.agent._render_template(name, cfg)
            for style in ('', 'none', 'plain', 'default'):
                self.assertEqual(original, self.agent._render_template(name, dict(cfg, style=style)))

    def test_content_is_not_rescanned_as_template_tokens(self):
        body = r'Literal @@TITLE@@; \verb|%%CONTENT%%|; $a_{i}^2$. A & B \\'
        source = self.agent._render_template('article', dict(style='cute', content=body, title='Hello'))
        self.assertIn(body, source)
        self.assertIn(r'\titleformat{\section}', source)

    def test_all_templates_and_fragments_are_supported(self):
        for template in self.agent._TEMPLATES:
            source = self.agent._render_template(template, dict(style='tlamatini', content='Sentinel'))
            self.assertTrue(self.agent._is_full_document(source), template)
            self.assertIn('Sentinel', source)
            self.assertNotIn('@@ART@@', source)
        source = self.agent._wrap_fragment(r'\section{Signal} $V=IR$', dict(style='pcb'))
        self.assertIn('LaTeXer style: circuit_board', source)
        self.assertNotIn(r'\begin{titlepage}', source)

    def test_existing_sources_cannot_silently_ignore_a_style(self):
        for cfg in ({'tex_path': 'old.tex'}, {'project_dir': 'old'},
                    {'input_text': r'\documentclass{article}\begin{document}X\end{document}'}):
            self.assertTrue(self.agent._style_preflight('compile', dict(cfg, style='tlamatini')))
        self.assertFalse(self.agent._style_preflight('compile', {'style': 'tlamatini', 'input_text': '$x$'}))

    def test_controls_change_document_behavior(self):
        cfg = dict(style='xeno', title='A title', content='Body')
        plain = self.agent._build_document(dict(cfg, style_decoration='none', style_cover='false'))
        self.assertNotIn(r'\begin{tikzpicture}', plain)
        self.assertNotIn(r'\begin{titlepage}', plain)
        rich = self.agent._build_document(cfg)
        self.assertIn(r'\begin{tikzpicture}', rich)
        self.assertIn(r'\begin{titlepage}', rich)

    def test_beamer_uses_its_own_layout_and_no_conflicting_packages(self):
        source = self.agent._render_template('beamer', {'style': 'tlamatini', 'content': r'\begin{itemize}\item A\end{itemize}'})
        self.assertIn(r'\setbeamercolor{normal text}', source)
        self.assertIn(r'\begin{frame}[fragile,allowframebreaks]', source)
        for package in ('titlesec', 'enumitem', 'fancyhdr'):
            self.assertNotIn(r'\usepackage{' + package + '}', source)

    def test_reported_design_is_canonical(self):
        outcome, notes = {}, []
        self.agent._record_style({'style': 'extraterrestrial aztec', 'style_mode': 'print'}, outcome, notes)
        self.assertEqual(outcome, dict(style='tlamatini_celestial', style_family='tlamatini', style_mode='print'))

    def test_styled_metadata_remains_visible_to_structure_action(self):
        for template in self.agent._TEMPLATES:
            source = self.agent._render_template(template, dict(style='tlamatini', title='A cosmic title',
                                                                author='A curious author'))
            structure = self.agent._document_structure(source)
            self.assertEqual(structure['title'], 'A cosmic title')
            self.assertEqual(structure['author'], 'A curious author')
            self.assertIn(r'\hypersetup{pdftitle={A cosmic title},pdfauthor={A curious author}}', source)

    def test_package_input_matches_the_existing_agent_contract(self):
        source = self.agent._build_document(dict(style='baby', packages='amsmath,\n graphicx,\n'))
        self.assertEqual(source.count(r'\usepackage{amsmath}'), 1)
        self.assertEqual(source.count(r'\usepackage{graphicx}'), 1)
        self.assertTrue(self.agent._style_preflight('create_file', {'style': 'baby', 'packages': 42}))

    @unittest.skipUnless(_has_latex(), 'real MiKTeX / TeX Live required')
    def test_copied_pool_scaffold_compiles_base64_through_default_repair_pipeline(self):
        import base64
        import yaml
        source = Path(self.agent.__file__).parent
        temp_root = Path(self.agent._temp_root())
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            for path in source.glob('*.py'):
                shutil.copy2(path, tmp)
            body = r'\subsection{SENTINEL} $E=mc^2$.'
            cfg = dict(action='scaffold_compile', style='extraterrestrial aztec',
                       title='A universe of ideas', template='article', content='SHOULD NOT APPEAR',
                       content_b64=base64.b64encode(body.encode()).decode(),
                       projects_dir=str(Path(tmp, 'project')), output_dir=str(Path(tmp, 'pdf')),
                       filename='proof.pdf', repair=True, repair_model='', use_latexmk=False,
                       keep_aux=True, command_timeout=120)
            Path(tmp, 'config.yaml').write_text(yaml.safe_dump(cfg), encoding='utf-8')
            run = subprocess.run([sys.executable, str(Path(tmp, 'latexer.py'))], cwd=tmp,
                                 capture_output=True, timeout=180)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors='replace'))
            log = Path(tmp, Path(tmp).name + '.log').read_text(encoding='utf-8')
            self.assertIn('status: compiled', log)
            self.assertIn('style: tlamatini_celestial', log)
            self.assertIn('errors: 0', log)
            pdf = Path(tmp, 'pdf', 'proof.pdf')
            self.assertTrue(pdf.is_file())
            self.assertEqual(pdf.read_bytes()[:5], b'%PDF-')
            tex = Path(tmp, 'project', 'proof', 'proof.tex').read_text(encoding='utf-8')
            self.assertIn(body, tex)
            self.assertNotIn('SHOULD NOT APPEAR', tex)

    def test_standalone_copied_pool_lists_styles_without_any_engine(self):
        import yaml
        source = Path(self.agent.__file__).parent
        with tempfile.TemporaryDirectory() as tmp:
            for path in source.glob('*.py'):
                shutil.copy2(path, tmp)
            Path(tmp, 'config.yaml').write_text(yaml.safe_dump({'action': 'list_styles'}), encoding='utf-8')
            env = dict(os.environ, PATH='', PYTHONPATH='')
            run = subprocess.run([sys.executable, str(Path(tmp, 'latexer.py'))],
                                 cwd=tmp, env=env, capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors='replace'))
            log = Path(tmp, Path(tmp).name + '.log').read_text(encoding='utf-8')
            self.assertIn('style_count: 30', log)
            self.assertIn('distribution: not_probed', log)
            self.assertIn('INI_SECTION_LATEXER<<<', log)
            self.assertIn('"id": "tlamatini_celestial"', log)
            self.assertFalse(list(Path(tmp).glob('*.pdf')))


if __name__ == '__main__':
    unittest.main()
