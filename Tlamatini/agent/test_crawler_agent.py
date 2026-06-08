"""Tests for the Crawler agent's recon / multi-seed / safety improvements.

Covers the four changes (the "equivalent" of the Googler dork work):
  1. Multi-seed crawling (``_collect_seed_urls`` + the ``urls`` config field).
  2. Safety / politeness bounds (``CrawlBudget``: max_pages cap, delay, robots.txt).
  3. Recon extraction (``extract_recon_findings`` / ``format_recon_summary``).
  4. Binary-content guard before the LLM (``_is_binary_for_llm``).

The Crawler agent is a POOL script (module-level ``os.chdir`` / log truncation /
``logging.basicConfig``), so it is loaded through ``importlib.util.spec_from_file_location``
with a cwd save/restore + logging-handler cleanup (same pattern as ``test_kalier_agent.py``).

The orchestration tests drive the REAL ``crawl`` / ``_process_link_list`` /
``_crawl_recursive`` code with ``fetch_page`` + ``process_url_with_llm`` patched to canned
HTML / recorders, so the seed-fan-out, visited de-dup, page cap, depth, robots, and delay
wiring is exercised end-to-end without any network or LLM.
"""

import importlib.util
import logging
import os
import unittest
from functools import lru_cache
from unittest.mock import patch


@lru_cache(maxsize=1)
def _load_crawler_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'crawler', 'crawler.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_crawler_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load Crawler module from {module_path}')

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


C = _load_crawler_module()


# ===========================================================================
# _collect_seed_urls
# ===========================================================================

class CollectSeedUrlsTests(unittest.TestCase):
    def test_single_url(self):
        self.assertEqual(C._collect_seed_urls({'url': 'https://a.com'}), ['https://a.com'])

    def test_url_plus_list(self):
        seeds = C._collect_seed_urls({'url': 'https://a.com', 'urls': ['https://b.com', 'https://c.com']})
        self.assertEqual(seeds, ['https://a.com', 'https://b.com', 'https://c.com'])

    def test_urls_comma_separated_string(self):
        seeds = C._collect_seed_urls({'urls': 'https://a.com, https://b.com'})
        self.assertEqual(seeds, ['https://a.com', 'https://b.com'])

    def test_dedup_preserves_order(self):
        seeds = C._collect_seed_urls({'url': 'https://a.com', 'urls': ['https://a.com', 'https://b.com']})
        self.assertEqual(seeds, ['https://a.com', 'https://b.com'])

    def test_non_http_and_blank_dropped(self):
        seeds = C._collect_seed_urls({'url': 'ftp://x', 'urls': ['', '   ', 'https://ok.com']})
        self.assertEqual(seeds, ['https://ok.com'])

    def test_empty_config(self):
        self.assertEqual(C._collect_seed_urls({}), [])


# ===========================================================================
# _is_binary_for_llm
# ===========================================================================

class BinaryGuardTests(unittest.TestCase):
    def test_html_is_not_binary(self):
        self.assertFalse(C._is_binary_for_llm('text/html; charset=utf-8', 'https://a.com/p'))

    def test_image_content_type(self):
        self.assertTrue(C._is_binary_for_llm('image/png', 'https://a.com/p'))

    def test_pdf_content_type(self):
        self.assertTrue(C._is_binary_for_llm('application/pdf', 'https://a.com/p'))

    def test_octet_stream(self):
        self.assertTrue(C._is_binary_for_llm('application/octet-stream', 'https://a.com/x'))

    def test_officedocument(self):
        self.assertTrue(C._is_binary_for_llm(
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'https://a.com/x'))

    def test_binary_by_url_extension_even_if_ct_generic(self):
        self.assertTrue(C._is_binary_for_llm('text/html', 'https://a.com/report.pdf'))

    def test_query_string_after_extension(self):
        self.assertTrue(C._is_binary_for_llm('text/html', 'https://a.com/a.jpg?v=2'))


# ===========================================================================
# extract_recon_findings / format_recon_summary
# ===========================================================================

class ReconExtractionTests(unittest.TestCase):
    def test_emails(self):
        f = C.extract_recon_findings('contact admin@example.com or sales@example.com')
        self.assertEqual(f['emails'], ['admin@example.com', 'sales@example.com'])

    def test_emails_deduped(self):
        f = C.extract_recon_findings('a@b.com a@b.com a@b.com')
        self.assertEqual(f['emails'], ['a@b.com'])

    def test_html_comments(self):
        f = C.extract_recon_findings('<div><!-- TODO: remove debug key --></div>')
        self.assertEqual(f['comments'], ['TODO: remove debug key'])

    def test_comment_whitespace_collapsed(self):
        f = C.extract_recon_findings('<!--   multi\n   line   comment   -->')
        self.assertEqual(f['comments'], ['multi line comment'])

    def test_source_map_inline_directive(self):
        f = C.extract_recon_findings('console.log(1)\n//# sourceMappingURL=app.min.js.map')
        self.assertIn('app.min.js.map', f['source_maps'])

    def test_aws_key_detected(self):
        f = C.extract_recon_findings('key=AKIAIOSFODNN7EXAMPLE end')
        self.assertIn('aws_access_key_id: AKIAIOSFODNN7EXAMPLE', f['secrets'])

    def test_google_api_key_detected(self):
        token = 'AIza' + 'B' * 35
        f = C.extract_recon_findings(f'var k = "{token}";')
        self.assertTrue(any(s.startswith('google_api_key: AIza') for s in f['secrets']))

    def test_slack_token_detected(self):
        # Assembled at runtime so this source file carries no literal Slack token
        # (GitHub push-protection flags one) while still exercising the regex.
        slack = 'xox' + 'b-111111111111-abcdefghijklmnop'
        f = C.extract_recon_findings(f'token: {slack}')
        self.assertTrue(any(s.startswith('slack_token: xoxb-') for s in f['secrets']))

    def test_private_key_header_detected(self):
        f = C.extract_recon_findings('-----BEGIN RSA PRIVATE KEY-----\nMIIE...')
        self.assertIn('private_key: -----BEGIN RSA PRIVATE KEY-----', f['secrets'])

    def test_generic_secret_assignment(self):
        f = C.extract_recon_findings('const api_key = "s3cr3t-value-1234"')
        self.assertTrue(any('generic_secret_assignment' in s for s in f['secrets']))

    def test_secrets_deduped(self):
        f = C.extract_recon_findings('AKIAIOSFODNN7EXAMPLE AKIAIOSFODNN7EXAMPLE')
        aws = [s for s in f['secrets'] if s.startswith('aws_access_key_id')]
        self.assertEqual(len(aws), 1)

    def test_empty_content(self):
        f = C.extract_recon_findings('')
        self.assertEqual(f, {'emails': [], 'comments': [], 'source_maps': [], 'secrets': []})

    def test_format_summary_includes_titles_and_omits_empty(self):
        f = {'emails': ['a@b.com'], 'comments': [], 'source_maps': [], 'secrets': ['aws_access_key_id: AKIA...']}
        out = C.format_recon_summary(f)
        self.assertIn('=== RECON: EMAIL ADDRESSES (1) ===', out)
        self.assertIn('=== RECON: POTENTIAL SECRETS / API KEYS (1) ===', out)
        self.assertIn('  a@b.com', out)
        self.assertNotIn('HTML COMMENTS', out)  # empty category omitted

    def test_format_summary_empty_when_nothing_found(self):
        self.assertEqual(C.format_recon_summary(
            {'emails': [], 'comments': [], 'source_maps': [], 'secrets': []}), '')


# ===========================================================================
# CrawlBudget
# ===========================================================================

class CrawlBudgetTests(unittest.TestCase):
    def test_unlimited_when_zero(self):
        b = C.CrawlBudget(max_pages=0)
        self.assertIsNone(b.remaining())
        b.note_processed()
        self.assertFalse(b.exhausted())

    def test_cap_enforced(self):
        b = C.CrawlBudget(max_pages=2)
        self.assertFalse(b.exhausted())
        b.note_processed()
        self.assertEqual(b.remaining(), 1)
        b.note_processed()
        self.assertTrue(b.exhausted())
        self.assertEqual(b.remaining(), 0)

    def test_invalid_values_coerced(self):
        b = C.CrawlBudget(max_pages='oops', delay_seconds=None)
        self.assertEqual(b.max_pages, 0)
        self.assertEqual(b.delay_seconds, 0.0)

    def test_wait_sleeps_only_when_delay_positive(self):
        with patch.object(C.time, 'sleep') as slept:
            C.CrawlBudget(delay_seconds=0).wait()
            slept.assert_not_called()
            C.CrawlBudget(delay_seconds=1.5).wait()
            slept.assert_called_once_with(1.5)

    def test_robots_allowed_true_when_disabled(self):
        b = C.CrawlBudget(respect_robots=False)
        self.assertTrue(b.robots_allowed('https://any.com/whatever'))

    def test_robots_blocks_disallowed_path(self):
        robots = "User-agent: *\nDisallow: /private"
        with patch.object(C, '_fetch_robots_txt', return_value=robots):
            b = C.CrawlBudget(respect_robots=True)
            self.assertFalse(b.robots_allowed('https://a.com/private/x'))
            self.assertTrue(b.robots_allowed('https://a.com/public/y'))

    def test_robots_fail_open_when_unfetchable(self):
        with patch.object(C, '_fetch_robots_txt', return_value=None):
            b = C.CrawlBudget(respect_robots=True)
            self.assertTrue(b.robots_allowed('https://a.com/anything'))


# ===========================================================================
# crawl() — end-to-end over patched fetch_page + process_url_with_llm
# ===========================================================================

class CrawlOrchestrationTests(unittest.TestCase):
    def _links_html(self, hrefs):
        anchors = ''.join(f'<a href="{h}">x</a>' for h in hrefs)
        return f'<html><body>{anchors}</body></html>'

    def _run(self, config, html_by_url, default_html='<html></html>'):
        """Run crawl() with fetch_page returning canned HTML per URL and
        process_url_with_llm recording each processed link."""
        processed = []

        def fake_fetch(url):
            return html_by_url.get(url, default_html)

        def fake_process(page_url, host, model, system_prompt, crawl_type, timestamp, **kw):
            processed.append(page_url)

        with patch.object(C, 'fetch_page', side_effect=fake_fetch), \
                patch.object(C, 'process_url_with_llm', side_effect=fake_process):
            count = C.crawl(config, 'http://h', 'm', 'analyze')
        return processed, count

    def test_small_range_keeps_same_domain_only(self):
        seed = 'https://seed.com'
        html = {seed: self._links_html([
            'https://seed.com/a', 'https://seed.com/b', 'https://other.com/x',
        ])}
        processed, count = self._run(
            {'url': seed, 'crawl_type': 'small-range', 'system_prompt': 'go'}, html)
        self.assertEqual(sorted(processed), ['https://seed.com/a', 'https://seed.com/b'])
        self.assertEqual(count, 2)

    def test_medium_range_keeps_cross_domain(self):
        seed = 'https://seed.com'
        html = {seed: self._links_html(['https://seed.com/a', 'https://other.com/x'])}
        processed, count = self._run(
            {'url': seed, 'crawl_type': 'medium-range', 'system_prompt': 'go'}, html)
        self.assertEqual(sorted(processed), ['https://other.com/x', 'https://seed.com/a'])
        self.assertEqual(count, 2)

    def test_multi_seed_processes_all_seeds_with_shared_visited(self):
        html = {
            'https://a.com': self._links_html(['https://a.com/p', 'https://shared.com/s']),
            'https://b.com': self._links_html(['https://b.com/q', 'https://shared.com/s']),
        }
        processed, count = self._run(
            {'url': 'https://a.com', 'urls': ['https://b.com'],
             'crawl_type': 'medium-range', 'system_prompt': 'go'}, html)
        # shared.com/s appears under both seeds but is processed ONCE (shared visited set).
        self.assertEqual(processed.count('https://shared.com/s'), 1)
        self.assertIn('https://a.com/p', processed)
        self.assertIn('https://b.com/q', processed)
        self.assertEqual(count, 3)

    def test_max_pages_cap_stops_processing(self):
        seed = 'https://seed.com'
        html = {seed: self._links_html([f'https://seed.com/{i}' for i in range(10)])}
        processed, count = self._run(
            {'url': seed, 'crawl_type': 'small-range', 'max_pages': 3, 'system_prompt': 'go'}, html)
        self.assertEqual(count, 3)
        self.assertEqual(len(processed), 3)

    def test_large_range_recurses_to_depth(self):
        seed = 'https://seed.com'
        html = {
            seed: self._links_html(['https://seed.com/level1']),
            'https://seed.com/level1': self._links_html(['https://seed.com/level2']),
            'https://seed.com/level2': self._links_html(['https://seed.com/level3']),
        }
        processed, count = self._run(
            {'url': seed, 'crawl_type': 'large-range', 'depth': 2, 'system_prompt': 'go'}, html)
        # depth=2 -> level1 (depth1) + level2 (depth2); level3 is NOT reached.
        self.assertIn('https://seed.com/level1', processed)
        self.assertIn('https://seed.com/level2', processed)
        self.assertNotIn('https://seed.com/level3', processed)

    def test_robots_disallow_skips_link(self):
        seed = 'https://seed.com'
        html = {seed: self._links_html(['https://seed.com/public/a', 'https://seed.com/private/b'])}
        robots = "User-agent: *\nDisallow: /private"
        with patch.object(C, '_fetch_robots_txt', return_value=robots):
            processed, count = self._run(
                {'url': seed, 'crawl_type': 'small-range', 'respect_robots': True,
                 'system_prompt': 'go'}, html)
        self.assertEqual(processed, ['https://seed.com/public/a'])
        self.assertEqual(count, 1)

    def test_unknown_crawl_type_returns_zero(self):
        processed, count = self._run(
            {'url': 'https://a.com', 'crawl_type': 'bogus', 'system_prompt': 'go'}, {})
        self.assertEqual(count, 0)
        self.assertEqual(processed, [])

    def test_no_seeds_returns_zero(self):
        processed, count = self._run({'crawl_type': 'small-range', 'system_prompt': 'go'}, {})
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
