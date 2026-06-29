# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for the Googler agent's dork-search improvements.

Covers the three changes:
  1. Blocker #1 — same-domain de-dup fix (``_dedup_links`` / ``allow_same_domain``).
  2. The structured Google-dork query builder (``build_dork_query``).
  3. ``links_only`` content mode (list SERP hits without fetching the pages).

The Googler agent is a POOL script, not an importable package module — it is loaded
through ``importlib.util.spec_from_file_location`` with a cwd save/restore and a
logging-handler cleanup so its module-level ``os.chdir`` / ``open(LOG_FILE_PATH)`` /
``logging.basicConfig`` side effects don't leak into the test process (same pattern as
``test_kalier_agent.py``).

The integration tests drive the REAL ``googler_search`` / ``_search_google_playwright``
/ ``_extract_links_with_selectors`` code over a FAKE Playwright (no browser, no network)
injected into ``sys.modules``, so the de-dup + links_only + fetch wiring is exercised
end-to-end exactly as it runs in production — only the browser is stubbed.
"""

import importlib.util
import logging
import os
import sys
import tempfile
import types
import unittest
from functools import lru_cache
from unittest.mock import patch


@lru_cache(maxsize=1)
def _load_googler_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'googler', 'googler.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_googler_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Googler module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


G = _load_googler_module()


# ===========================================================================
# Fake Playwright — drives the real search/extract code with no browser
# ===========================================================================

class _FakeH3:
    def __init__(self, text):
        self._text = text

    def inner_text(self):
        return self._text


class _FakeElement:
    """Stand-in for a Playwright result-anchor handle."""

    def __init__(self, href, title=''):
        self._href = href
        self._title = title

    def get_attribute(self, name):
        return self._href if name == 'href' else None

    def query_selector(self, selector):
        if selector == 'h3' and self._title:
            return _FakeH3(self._title)
        return None

    def inner_text(self):
        return self._title


class _FakeResponse:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {'content-type': 'text/html; charset=utf-8'}


class _FakeBox:
    def fill(self, *_a, **_k):
        pass

    def press(self, *_a, **_k):
        pass


class _FakePage:
    """Stand-in for a Playwright page. Records every goto() so a test can assert
    that links_only never fetches result pages."""

    def __init__(self, elements, body_text='VISIBLE BODY TEXT', html='<html>raw-source</html>'):
        self._elements = list(elements)
        self._body_text = body_text
        self._html = html
        self.goto_calls = []

    def goto(self, url, **_kw):
        self.goto_calls.append(url)
        return _FakeResponse()

    def query_selector(self, _selector):
        return None  # no consent banner

    def query_selector_all(self, _selector):
        return list(self._elements)

    def wait_for_selector(self, *_a, **_k):
        return _FakeBox()

    def wait_for_timeout(self, *_a, **_k):
        pass

    def wait_for_load_state(self, *_a, **_k):
        pass

    def inner_text(self, _selector):
        return self._body_text

    def content(self):
        return self._html

    def screenshot(self, *_a, **_k):
        pass


def _install_fake_playwright(page):
    """Build fake ``playwright`` / ``playwright.sync_api`` modules whose
    ``sync_playwright()`` yields a context that hands back ``page``."""

    class _Chromium:
        def launch(self, **_kw):
            return _Browser()

    class _Browser:
        def new_context(self, **_kw):
            return _Context()

        def close(self):
            pass

    class _Context:
        def add_init_script(self, *_a, **_k):
            pass

        def new_page(self):
            return page

    class _P:
        chromium = _Chromium()

    class _CM:
        def __enter__(self):
            return _P()

        def __exit__(self, *_a):
            return False

    fake_sync_api = types.ModuleType('playwright.sync_api')
    fake_sync_api.sync_playwright = lambda: _CM()
    fake_pkg = types.ModuleType('playwright')
    fake_pkg.sync_api = fake_sync_api
    return {'playwright': fake_pkg, 'playwright.sync_api': fake_sync_api}


# ===========================================================================
# build_dork_query
# ===========================================================================

class BuildDorkQueryTests(unittest.TestCase):
    def test_empty_config_yields_empty_string(self):
        self.assertEqual(G.build_dork_query({}), '')

    def test_raw_query_only_passthrough(self):
        self.assertEqual(G.build_dork_query({'query': 'login portal'}), 'login portal')

    def test_site_only(self):
        self.assertEqual(G.build_dork_query({'site': 'example.com'}), 'site:example.com')

    def test_raw_plus_site_plus_filetype(self):
        q = G.build_dork_query({'query': 'confidential', 'site': 'example.com', 'filetype': 'pdf'})
        self.assertEqual(q, 'confidential site:example.com filetype:pdf')

    def test_filetype_accepts_ext_prefix(self):
        self.assertEqual(G.build_dork_query({'filetype': 'ext:pdf'}), 'filetype:pdf')

    def test_filetype_accepts_filetype_prefix(self):
        self.assertEqual(G.build_dork_query({'filetype': 'filetype:xls'}), 'filetype:xls')

    def test_intitle_multiword_is_quoted(self):
        self.assertEqual(G.build_dork_query({'intitle': 'index of'}), 'intitle:"index of"')

    def test_intext_multiword_is_quoted(self):
        self.assertEqual(G.build_dork_query({'intext': 'api key'}), 'intext:"api key"')

    def test_inurl_singleword_not_quoted(self):
        self.assertEqual(G.build_dork_query({'inurl': 'admin'}), 'inurl:admin')

    def test_exact_phrase_wrapped(self):
        self.assertEqual(G.build_dork_query({'exact': 'top secret'}), '"top secret"')

    def test_exclude_list(self):
        self.assertEqual(
            G.build_dork_query({'query': 'cats', 'exclude': ['ads', 'shop']}),
            'cats -ads -shop',
        )

    def test_exclude_comma_separated_string(self):
        self.assertEqual(
            G.build_dork_query({'query': 'cats', 'exclude': 'ads, shop'}),
            'cats -ads -shop',
        )

    def test_exclude_preserves_leading_dash(self):
        self.assertEqual(G.build_dork_query({'query': 'x', 'exclude': ['-already']}), 'x -already')

    def test_before_after(self):
        q = G.build_dork_query({'query': 'breach', 'after': '2020-01-01', 'before': '2021-01-01'})
        self.assertEqual(q, 'breach before:2021-01-01 after:2020-01-01')

    def test_operator_value_with_existing_prefix_not_doubled(self):
        # User accidentally wrote the prefix inside the field value.
        self.assertEqual(G.build_dork_query({'site': 'site:example.com'}), 'site:example.com')

    def test_full_combo_order_is_stable(self):
        q = G.build_dork_query({
            'exact': 'db dump',
            'query': 'backup',
            'intitle': 'index of',
            'site': 'example.com',
            'filetype': 'sql',
            'exclude': ['github'],
        })
        self.assertEqual(q, '"db dump" backup intitle:"index of" site:example.com filetype:sql -github')

    def test_none_and_whitespace_values_ignored(self):
        self.assertEqual(G.build_dork_query({'query': '  ', 'site': None, 'filetype': ''}), '')


# ===========================================================================
# _query_has_site_operator / _resolve_allow_same_domain
# ===========================================================================

class SiteOperatorDetectionTests(unittest.TestCase):
    def test_detects_site_operator(self):
        self.assertTrue(G._query_has_site_operator('foo site:example.com'))

    def test_detects_site_operator_case_insensitive(self):
        self.assertTrue(G._query_has_site_operator('SITE:example.com'))

    def test_detects_site_at_start(self):
        self.assertTrue(G._query_has_site_operator('site:example.com filetype:pdf'))

    def test_no_false_positive_on_substring(self):
        # "website:" should not match the site: operator.
        self.assertFalse(G._query_has_site_operator('my website: cool'))

    def test_empty_query(self):
        self.assertFalse(G._query_has_site_operator(''))
        self.assertFalse(G._query_has_site_operator(None))

    def test_resolve_respects_explicit_flag(self):
        self.assertTrue(G._resolve_allow_same_domain({'allow_same_domain': True}, 'plain query'))

    def test_resolve_auto_enables_for_site_dork(self):
        self.assertTrue(G._resolve_allow_same_domain({}, 'foo site:example.com'))

    def test_resolve_off_by_default(self):
        self.assertFalse(G._resolve_allow_same_domain({}, 'plain query'))


# ===========================================================================
# _dedup_links — Blocker #1
# ===========================================================================

class DedupLinksTests(unittest.TestCase):
    def _links(self, *urls):
        return [{'url': u, 'title': f'title-{i}'} for i, u in enumerate(urls)]

    def test_legacy_dedup_keeps_one_per_domain(self):
        links = self._links(
            'https://target.com/a', 'https://target.com/b', 'https://other.com/x',
        )
        out = G._dedup_links(links, skip_domains=set(), allow_same_domain=False)
        domains = {u['url'] for u in out}
        self.assertEqual(len(out), 2)  # target.com collapsed to 1 + other.com
        self.assertIn('https://target.com/a', domains)
        self.assertIn('https://other.com/x', domains)
        self.assertNotIn('https://target.com/b', domains)

    def test_blocker1_allow_same_domain_keeps_all_urls(self):
        links = self._links(
            'https://target.com/a.pdf', 'https://target.com/b.pdf',
            'https://target.com/c.pdf', 'https://other.com/x',
        )
        out = G._dedup_links(links, skip_domains=set(), allow_same_domain=True)
        self.assertEqual(len(out), 4)  # ALL site:target.com hits survive

    def test_exact_duplicate_url_removed_even_when_same_domain_allowed(self):
        links = self._links('https://target.com/a', 'https://target.com/a')
        out = G._dedup_links(links, skip_domains=set(), allow_same_domain=True)
        self.assertEqual(len(out), 1)

    def test_skip_domains_filtered(self):
        links = self._links('https://google.com/search', 'https://real.com/page')
        out = G._dedup_links(links, allow_same_domain=True)  # default skip set incl. google
        self.assertEqual([u['url'] for u in out], ['https://real.com/page'])

    def test_non_http_and_blank_filtered(self):
        links = [
            {'url': 'ftp://x.com/file', 'title': ''},
            {'url': '', 'title': ''},
            {'url': 'https://ok.com/p', 'title': 'ok'},
        ]
        out = G._dedup_links(links, skip_domains=set(), allow_same_domain=True)
        self.assertEqual([u['url'] for u in out], ['https://ok.com/p'])

    def test_title_is_preserved_and_stripped(self):
        out = G._dedup_links(
            [{'url': 'https://ok.com/p', 'title': '  My Title  '}],
            skip_domains=set(), allow_same_domain=True,
        )
        self.assertEqual(out[0]['title'], 'My Title')


# ===========================================================================
# save_results — Title line + links_only (no content)
# ===========================================================================

class SaveResultsTests(unittest.TestCase):
    def test_links_only_writes_title_and_no_content_section(self):
        results = [
            {'index': 1, 'url': 'https://t.com/a', 'title': 'Doc A',
             'status_code': 'listed', 'content_length': 0},
        ]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'res.txt')
            path = G.save_results(results, out, 'site:t.com filetype:pdf')
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
        self.assertIn('URL: https://t.com/a', text)
        self.assertIn('Title: Doc A', text)
        self.assertIn('Status: listed', text)
        # No body content for a links_only entry.
        self.assertNotIn('VISIBLE BODY TEXT', text)

    def test_text_result_writes_content(self):
        results = [
            {'index': 1, 'url': 'https://t.com/a', 'title': 'Page A',
             'status_code': 200, 'content_length': 11, 'content': 'hello world'},
        ]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'res.txt')
            path = G.save_results(results, out, 'foo')
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
        self.assertIn('Title: Page A', text)
        self.assertIn('hello world', text)

    def test_error_result_writes_error_line(self):
        results = [{'index': 1, 'url': 'https://t.com/a', 'error': 'boom'}]
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'res.txt')
            path = G.save_results(results, out, 'foo')
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
        self.assertIn('ERROR: boom', text)


# ===========================================================================
# googler_search — end-to-end over fake Playwright
# ===========================================================================

class GooglerSearchIntegrationTests(unittest.TestCase):
    def _run(self, page, query, n, mode, allow_same_domain):
        with patch.dict(sys.modules, _install_fake_playwright(page)):
            return G.googler_search(query, n, mode, allow_same_domain)

    def test_links_only_blocker1_keeps_all_same_domain_urls(self):
        page = _FakePage([
            _FakeElement('https://target.com/a.pdf', 'A'),
            _FakeElement('https://target.com/b.pdf', 'B'),
            _FakeElement('https://target.com/c.pdf', 'C'),
            _FakeElement('https://other.com/x', 'X'),
        ])
        results = self._run(page, 'site:target.com filetype:pdf', 10, 'links_only', True)
        urls = [r['url'] for r in results]
        self.assertEqual(len(results), 4)
        self.assertEqual(urls.count('https://target.com/a.pdf'), 1)
        self.assertIn('https://target.com/c.pdf', urls)
        # Every entry carries a title + the "listed" sentinel status.
        self.assertTrue(all(r['status_code'] == 'listed' for r in results))
        self.assertEqual(results[0]['title'], 'A')

    def test_links_only_legacy_dedup_collapses_same_domain(self):
        page = _FakePage([
            _FakeElement('https://target.com/a.pdf', 'A'),
            _FakeElement('https://target.com/b.pdf', 'B'),
            _FakeElement('https://other.com/x', 'X'),
        ])
        results = self._run(page, 'filetype:pdf', 10, 'links_only', False)
        self.assertEqual(len(results), 2)

    def test_links_only_does_not_fetch_result_pages(self):
        page = _FakePage([
            _FakeElement('https://target.com/a.pdf', 'A'),
            _FakeElement('https://target.com/b.pdf', 'B'),
        ])
        self._run(page, 'site:target.com', 10, 'links_only', True)
        # Only the SERP page (google.com) is fetched — never the result URLs.
        self.assertEqual(page.goto_calls, ['https://www.google.com'])

    def test_links_only_honors_number_of_results_slice(self):
        page = _FakePage([
            _FakeElement('https://target.com/a', 'A'),
            _FakeElement('https://target.com/b', 'B'),
            _FakeElement('https://target.com/c', 'C'),
            _FakeElement('https://target.com/d', 'D'),
        ])
        results = self._run(page, 'site:target.com', 2, 'links_only', True)
        self.assertEqual(len(results), 2)

    def test_text_mode_fetches_each_result_and_extracts_content(self):
        page = _FakePage([
            _FakeElement('https://a.com/page1', 'P1'),
            _FakeElement('https://b.com/page2', 'P2'),
        ], body_text='VISIBLE BODY TEXT')
        results = self._run(page, 'foo', 5, 'text', False)
        self.assertEqual(len(results), 2)
        # google.com + the 2 result pages were fetched.
        self.assertEqual(page.goto_calls,
                         ['https://www.google.com', 'https://a.com/page1', 'https://b.com/page2'])
        self.assertEqual(results[0]['content'], 'VISIBLE BODY TEXT')
        self.assertEqual(results[0]['title'], 'P1')
        self.assertGreater(results[0]['content_length'], 0)

    def test_raw_mode_returns_html_and_title(self):
        page = _FakePage([_FakeElement('https://a.com/p', 'Raw')], html='<html>RAWHTML</html>')
        results = self._run(page, 'foo', 5, 'raw', False)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], '<html>RAWHTML</html>')
        self.assertEqual(results[0]['title'], 'Raw')

    def test_no_results_returns_empty_list(self):
        page = _FakePage([])  # no anchors found by any selector
        results = self._run(page, 'whatever', 5, 'links_only', False)
        self.assertEqual(results, [])


if __name__ == '__main__':
    unittest.main()
