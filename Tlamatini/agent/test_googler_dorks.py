# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for Googler's Google-dork query builder (2026-08-23).

The builder exists so the CALLER cannot get Google's syntax wrong, because every
one of these mistakes silently degrades a filter into an ordinary keyword search
and returns plausible-looking rubbish rather than an error:

  * a space after the colon   -> `filetype: pdf` filters NOTHING
  * lowercase `or`            -> treated as a stop word
  * unparenthesised OR        -> binds to one adjacent term only
  * a space after `-`         -> the exclusion is ignored

So the syntax rules are asserted directly, not just the happy paths.

Run:  python Tlamatini/manage.py test agent.test_googler_dorks
"""
import importlib.util
import logging
import os
import unittest
from unittest import mock

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOOGLER = os.path.join(_HERE, 'agents', 'googler', 'googler.py')
_CFG = os.path.join(_HERE, 'agents', 'googler', 'config.yaml')


def _load_googler():
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        spec = importlib.util.spec_from_file_location('googler_dork_mod', _GOOGLER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


g = _load_googler()


def build(**cfg):
    cfg.setdefault('query', '')
    return g.build_dork_query(cfg)


# ══════════════════════════════════════════════════════════════════════════
# THE FIVE SYNTAX RULES
# ══════════════════════════════════════════════════════════════════════════

class SyntaxRuleTests(unittest.TestCase):

    def test_no_space_after_the_filetype_colon(self):
        self.assertIn('filetype:pdf', build(filetypes='pdf'))
        self.assertNotIn('filetype: pdf', build(filetypes='pdf'))

    def test_no_space_after_the_site_colon(self):
        self.assertIn('site:example.com', build(sites='example.com'))
        self.assertNotIn('site: example.com', build(sites='example.com'))

    def test_or_is_uppercase(self):
        q = build(filetypes=['epub', 'pdf'])
        self.assertIn(' OR ', q)
        self.assertNotIn(' or ', q)

    def test_alternatives_are_parenthesised(self):
        self.assertIn('(filetype:epub OR filetype:pdf)', build(filetypes=['epub', 'pdf']))

    def test_exclusion_has_no_space_after_the_hyphen(self):
        q = build(exclude=['review'])
        self.assertIn('-review', q)
        self.assertNotIn('- review', q)

    def test_exact_phrase_is_double_quoted(self):
        self.assertIn('"The Time Machine"', build(exact='The Time Machine'))

    def test_multi_word_intitle_is_auto_quoted(self):
        self.assertIn('intitle:"user manual"', build(intitle='user manual'))

    def test_single_word_intitle_is_not_quoted(self):
        self.assertIn('inurl:manual', build(inurl='manual'))


# ══════════════════════════════════════════════════════════════════════════
# FILETYPES — the headline file-grabbing capability
# ══════════════════════════════════════════════════════════════════════════

class FiletypeTests(unittest.TestCase):

    def test_single_filetype_needs_no_group(self):
        q = build(filetypes='pdf')
        self.assertIn('filetype:pdf', q)
        self.assertNotIn('OR', q)

    def test_two_filetypes_become_an_or_group(self):
        self.assertIn('(filetype:epub OR filetype:pdf)', build(filetypes=['epub', 'pdf']))

    def test_ebook_alias_expands_to_four_formats(self):
        q = build(filetypes='ebook')
        for ext in ('epub', 'pdf', 'mobi', 'azw3'):
            with self.subTest(ext=ext):
                self.assertIn(f'filetype:{ext}', q)

    def test_book_alias_expands_to_epub_and_pdf(self):
        q = build(filetypes='book')
        self.assertIn('filetype:epub', q)
        self.assertIn('filetype:pdf', q)

    def test_sheets_alias_expands(self):
        q = build(filetypes='sheets')
        for ext in ('xls', 'xlsx', 'csv'):
            with self.subTest(ext=ext):
                self.assertIn(f'filetype:{ext}', q)

    def test_already_prefixed_filetype_is_not_doubled(self):
        q = build(filetypes=['filetype:pdf'])
        self.assertIn('filetype:pdf', q)
        self.assertNotIn('filetype:filetype:', q)

    def test_ext_prefix_is_accepted(self):
        self.assertIn('filetype:epub', build(filetypes=['ext:epub']))

    def test_leading_dot_is_tolerated(self):
        self.assertIn('filetype:pdf', build(filetypes=['.pdf']))

    def test_legacy_singular_filetype_still_works(self):
        self.assertIn('filetype:pdf', build(filetype='pdf'))

    def test_singular_and_plural_merge_without_duplicates(self):
        q = build(filetype='pdf', filetypes=['pdf', 'epub'])
        self.assertEqual(q.count('filetype:pdf'), 1)

    def test_comma_separated_string_is_accepted(self):
        q = build(filetypes='epub, pdf')
        self.assertIn('(filetype:epub OR filetype:pdf)', q)


# ══════════════════════════════════════════════════════════════════════════
# SITES
# ══════════════════════════════════════════════════════════════════════════

class SiteTests(unittest.TestCase):

    def test_multiple_sites_become_an_or_group(self):
        self.assertIn('(site:a.com OR site:b.com)', build(sites=['a.com', 'b.com']))

    def test_bare_tld_is_allowed(self):
        self.assertIn('site:.edu', build(sites='.edu'))

    def test_legacy_singular_site_still_works(self):
        self.assertIn('site:example.com', build(site='example.com'))

    def test_excluded_sites_are_negated(self):
        self.assertIn('-site:scribd.com', build(exclude_sites=['scribd.com']))

    def test_excluded_site_accepts_a_prefixed_value(self):
        self.assertIn('-site:scribd.com', build(exclude_sites=['site:scribd.com']))

    def test_site_operator_detector_sees_a_plain_site(self):
        self.assertTrue(g._query_has_site_operator('foo site:example.com'))

    def test_site_operator_detector_sees_an_or_group(self):
        """REGRESSION: the detector's regex required whitespace before `site:`,
        so a parenthesised OR-group was NOT recognised as site-restricted and
        same-domain de-dup would throw away every hit but one per host."""
        self.assertTrue(g._query_has_site_operator('(site:a.com OR site:b.com)'))

    def test_site_operator_detector_is_false_for_plain_words(self):
        self.assertFalse(g._query_has_site_operator('just some keywords'))

    def test_allow_same_domain_auto_enables_for_an_or_group(self):
        self.assertTrue(g._resolve_allow_same_domain({}, '(site:a.com OR site:b.com)'))


# ══════════════════════════════════════════════════════════════════════════
# PRESETS
# ══════════════════════════════════════════════════════════════════════════

class PresetTests(unittest.TestCase):

    def test_book_preset_searches_both_ebook_formats(self):
        self.assertIn('(filetype:epub OR filetype:pdf)', build(exact='X', preset='book'))

    def test_book_preset_removes_about_the_book_noise(self):
        q = build(exact='X', preset='book')
        self.assertIn('-review', q)
        self.assertIn('-summary', q)

    def test_book_public_preset_targets_lawful_full_text_libraries(self):
        q = build(exact='X', preset='book_public')
        for host in ('gutenberg.org', 'standardebooks.org', 'archive.org'):
            with self.subTest(host=host):
                self.assertIn(f'site:{host}', q)

    def test_paper_preset_targets_open_access_sources(self):
        q = build(exact='X', preset='paper')
        self.assertIn('filetype:pdf', q)
        self.assertIn('site:arxiv.org', q)

    def test_directory_preset_builds_the_index_of_dork(self):
        self.assertIn('intitle:"index of"', build(preset='directory'))

    def test_explicit_field_overrides_the_preset(self):
        """The preset only fills what the caller left EMPTY."""
        q = build(exact='X', preset='book', filetypes='epub')
        self.assertIn('filetype:epub', q)
        self.assertNotIn('filetype:pdf', q)

    def test_unknown_preset_is_ignored_not_fatal(self):
        q = build(exact='X', preset='not-a-real-preset')
        self.assertIn('"X"', q)

    def test_empty_preset_changes_nothing(self):
        self.assertEqual(build(exact='X', preset=''), build(exact='X'))


# ══════════════════════════════════════════════════════════════════════════
# THE REST OF THE OPERATOR SURFACE
# ══════════════════════════════════════════════════════════════════════════

class OperatorCoverageTests(unittest.TestCase):

    def test_every_documented_operator_is_emitted(self):
        cases = {
            'allintitle': 'allintitle:annual report',
            'allinurl': 'allinurl:docs api',
            'allintext': 'allintext:installation guide',
            'inanchor': 'inanchor:download',
            'allinanchor': 'allinanchor:free ebook',
            'related': 'related:example.com',
            'cache': 'cache:example.com',
            'define': 'define:entropy',
            'source': 'source:reuters',
            'before': 'before:2020-01-01',
            'after': 'after:2025-01-01',
        }
        for field, expected in cases.items():
            with self.subTest(operator=field):
                self.assertIn(expected, build(**{field: expected.split(':', 1)[1]}))

    def test_intext_multi_word_is_quoted(self):
        self.assertIn('intext:"exact sentence"', build(intext='exact sentence'))

    def test_author_becomes_a_quoted_phrase_not_an_operator(self):
        q = build(exact='Title', author='H G Wells')
        self.assertIn('"H G Wells"', q)
        self.assertNotIn('author:', q)

    def test_or_terms_build_a_group(self):
        self.assertIn('(epub OR mobi OR azw3)', build(or_terms=['epub', 'mobi', 'azw3']))

    def test_single_or_term_needs_no_group(self):
        q = build(or_terms=['epub'])
        self.assertIn('epub', q)
        self.assertNotIn('(', q)

    def test_around_builds_the_proximity_operator(self):
        self.assertIn('tesla AROUND(3) battery',
                      build(around_terms=['tesla', 'battery'], around_distance=3))

    def test_around_needs_two_terms(self):
        self.assertNotIn('AROUND', build(around_terms=['tesla']))

    def test_around_distance_defaults_when_unparseable(self):
        self.assertIn('AROUND(5)',
                      build(around_terms=['a', 'b'], around_distance='not a number'))

    def test_numeric_range_passes_through(self):
        self.assertIn('2020..2026', build(numeric_range='2020..2026'))

    def test_numeric_range_accepts_a_hyphen_form(self):
        self.assertIn('2020..2026', build(numeric_range='2020-2026'))

    def test_exclude_accepts_a_string(self):
        q = build(exclude='review summary')
        self.assertIn('-review', q)
        self.assertIn('-summary', q)

    def test_exclude_does_not_double_the_hyphen(self):
        self.assertNotIn('--review', build(exclude=['-review']))


# ══════════════════════════════════════════════════════════════════════════
# COMPOSITION & BACK-COMPAT
# ══════════════════════════════════════════════════════════════════════════

class CompositionTests(unittest.TestCase):

    def test_freeform_dork_is_preserved_verbatim(self):
        raw = 'intitle:"index of" site:example.com'
        self.assertEqual(build(query=raw), raw)

    def test_freeform_and_structured_fields_combine(self):
        q = build(query='"device model"', intitle='user manual', filetypes='pdf')
        self.assertIn('"device model"', q)
        self.assertIn('intitle:"user manual"', q)
        self.assertIn('filetype:pdf', q)

    def test_exact_phrase_leads_the_query(self):
        self.assertTrue(build(query='extra', exact='Lead Phrase').startswith('"Lead Phrase"'))

    def test_empty_config_yields_an_empty_query(self):
        self.assertEqual(build(), '')

    def test_no_double_spaces_survive(self):
        q = build(exact='X', filetypes='pdf', exclude=['a'])
        self.assertNotIn('  ', q)

    def test_angelas_canonical_book_query_is_reproducible(self):
        q = build(exact='exact book title', author='author name', filetypes='epub')
        self.assertIn('"exact book title"', q)
        self.assertIn('"author name"', q)
        self.assertIn('filetype:epub', q)

    def test_angelas_trusted_domain_query_is_reproducible(self):
        q = build(exact='quantum computing', filetypes='pdf', sites='.edu')
        self.assertIn('"quantum computing"', q)
        self.assertIn('filetype:pdf', q)
        self.assertIn('site:.edu', q)

    def test_angelas_date_window_query_is_reproducible(self):
        q = build(exact='research topic', filetypes='pdf',
                  after='2023-01-01', before='2026-01-01')
        self.assertIn('after:2023-01-01', q)
        self.assertIn('before:2026-01-01', q)


class ConfigAndToolContractTests(SimpleTestCase):

    def test_config_declares_every_builder_field(self):
        import yaml
        with open(_CFG, 'r', encoding='utf-8') as fh:
            cfg = yaml.safe_load(fh) or {}
        for key in ('preset', 'filetypes', 'filetype', 'sites', 'site', 'exclude_sites',
                    'exact', 'author', 'intitle', 'allintitle', 'inurl', 'allinurl',
                    'intext', 'allintext', 'inanchor', 'allinanchor', 'or_terms',
                    'around_terms', 'around_distance', 'numeric_range', 'before',
                    'after', 'related', 'cache', 'define', 'source', 'exclude'):
            with self.subTest(key=key):
                self.assertIn(key, cfg)

    def test_config_still_carries_the_original_fields(self):
        import yaml
        with open(_CFG, 'r', encoding='utf-8') as fh:
            cfg = yaml.safe_load(fh) or {}
        for key in ('query', 'number_of_results', 'content_mode', 'output_file',
                    'target_agents', 'source_agents', 'allow_same_domain'):
            with self.subTest(key=key):
                self.assertIn(key, cfg)

    def test_config_declares_resilient_engine_controls(self):
        import yaml
        with open(_CFG, 'r', encoding='utf-8') as fh:
            cfg = yaml.safe_load(fh) or {}
        self.assertIs(cfg['headless'], False)
        self.assertEqual(cfg['engines'], [])
        self.assertEqual(cfg['attempts_per_engine'], 2)

    def test_tool_description_teaches_the_operator_language(self):
        """Angela's requirement: the LLM must learn the dork vocabulary FROM the
        tool description, so the operators have to actually be in it."""
        from agent.tools import googler
        doc = (googler.description or '')
        for token in ('filetype:', 'site:', 'intitle:', 'inurl:', 'intext:',
                      'inanchor:', 'related:', 'cache:', 'define:', 'source:',
                      'before:', 'after:', 'allintitle:', 'AROUND(', '..',
                      'epub', 'pdf', 'OR'):
            with self.subTest(token=token):
                self.assertIn(token, doc)

    def test_tool_description_states_the_syntax_rules(self):
        from agent.tools import googler
        doc = (googler.description or '').lower()
        self.assertIn('no space after', doc)
        self.assertIn('uppercase', doc)
        self.assertIn('quote', doc)

    def test_tool_description_points_at_lawful_full_text_sources(self):
        from agent.tools import googler
        doc = (googler.description or '')
        self.assertIn('gutenberg.org', doc)
        self.assertIn('copyright', doc.lower())

    def test_binary_hit_is_reported_as_a_found_file_not_an_error(self):
        """REGRESSION: a `filetype:pdf` hunt returned every result marked
        'skipped', so a perfectly successful file hunt read as N failures."""
        from agent.tools import _googler_fetch_page_text
        out = _googler_fetch_page_text(None, 'https://example.com/book.pdf')
        self.assertEqual(out.get('kind'), 'file')
        self.assertNotIn('error', out)
        self.assertEqual(out.get('filetype'), 'pdf')

    def test_url_extension_ignores_the_query_string(self):
        from agent.tools import _googler_url_extension
        self.assertEqual(_googler_url_extension('https://x.com/a/b.epub?dl=1'), 'epub')

    def test_url_extension_is_empty_for_a_plain_page(self):
        from agent.tools import _googler_url_extension
        self.assertEqual(_googler_url_extension('https://example.com/articles/'), '')


class SearchResilienceTests(unittest.TestCase):

    def test_string_false_does_not_enable_headless_or_same_domain(self):
        self.assertIs(g._as_bool('false', True), False)
        self.assertIs(g._as_bool('true', False), True)
        self.assertIs(g._resolve_allow_same_domain(
            {'allow_same_domain': 'false'}, 'ordinary words'), False)

    def test_default_chain_is_seven_routes_and_js_free_first(self):
        names = [engine['name'] for engine in g._SEARCH_ENGINES]
        self.assertEqual(names, [
            'duckduckgo-html', 'duckduckgo-lite', 'mojeek', 'bing',
            'google', 'brave', 'startpage',
        ])
        self.assertTrue(all(engine['js_free'] for engine in g._SEARCH_ENGINES[:3]))

    @mock.patch.object(g.time, 'sleep')
    @mock.patch.object(g.random, 'uniform', return_value=0.2)
    def test_chain_retries_then_stops_at_first_answer(self, _uniform, sleep):
        engines = [{'name': 'first'}, {'name': 'second'}, {'name': 'third'}]
        with mock.patch.object(g, '_SEARCH_ENGINES', engines), \
                mock.patch.object(g, '_search_one_engine', side_effect=[
                    [], [], [{'url': 'https://example.com/file.pdf'}],
                ]) as search:
            hits = g._search_with_fallback(
                object(), 'query', 5,
                engine_order=['first', 'second', 'third'],
                attempts_per_engine=2,
            )
        self.assertEqual(hits, [{'url': 'https://example.com/file.pdf'}])
        self.assertEqual(search.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @mock.patch.object(g.time, 'sleep')
    @mock.patch.object(g.random, 'uniform', return_value=0.2)
    def test_pinned_engine_does_not_call_other_routes(self, _uniform, _sleep):
        engines = [{'name': 'first'}, {'name': 'second'}]
        with mock.patch.object(g, '_SEARCH_ENGINES', engines), \
                mock.patch.object(g, '_search_one_engine', return_value=[
                    {'url': 'https://example.com/result'},
                ]) as search:
            g._search_with_fallback(
                object(), 'query', 5, engine_order=['second'])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.args[1]['name'], 'second')

    def test_plain_http_tier_has_four_server_rendered_routes(self):
        self.assertEqual(
            [engine['name'] for engine in g._HTTP_ENGINES],
            ['duckduckgo-html', 'bing-http', 'duckduckgo-lite', 'mojeek-http'],
        )

    def test_links_only_http_answer_returns_before_playwright_import(self):
        expected = [{'url': 'https://example.com/open.pdf', 'title': ''}]
        with mock.patch.object(g, '_search_http_tier', return_value=expected), \
                mock.patch('builtins.__import__', side_effect=AssertionError(
                    'Playwright must not be imported after a Tier-0 links-only answer',
                )):
            hits = g.googler_search('query', content_mode='links_only')
        self.assertEqual(hits[0]['url'], expected[0]['url'])
        self.assertEqual(hits[0]['status_code'], 'listed')

    def test_pinning_a_browser_engine_skips_plain_http_tier(self):
        with mock.patch.object(g, '_search_http_tier') as http, \
                mock.patch('builtins.__import__', side_effect=ImportError):
            g.googler_search(
                'query', content_mode='links_only', engines=['google'])
        http.assert_not_called()

    def test_duckduckgo_redirect_unwraps_to_direct_file(self):
        wrapped = ('//duckduckgo.com/l/?uddg='
                   'https%3A%2F%2Fexample.com%2Fbooks%2Fwork.epub%3Fdownload%3D1')
        self.assertEqual(
            g._unwrap_redirect(wrapped),
            'https://example.com/books/work.epub?download=1',
        )


if __name__ == '__main__':
    unittest.main()
