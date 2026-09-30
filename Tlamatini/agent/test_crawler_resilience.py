# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""The Crawler must read the page it was given, never hang, and never lie (2026-09-28).

Found in Angela's own session log that night:
  * on Wikipedia and MkDocs pages it downloaded 760 KB of HTML, extracted ZERO
    characters and skipped the page: its text extractor opened a skip region at
    ``<meta>`` / ``<link>`` (void elements, no end tag) that never closed;
  * asked to read the Humanity's Last Exam article, it never analyzed that page at
    all - ``small-range`` only visits the LINKS - and walked 347 side pages with no
    page limit until the model killed it after 97 s;
  * ``Content-Type`` was looked up case-sensitively, so Wikipedia's lower-case
    header read as "unknown" and the binary guard went blind.

Every fix is pinned here without any network: hung and dribbling servers are local
sockets, and the refusal pages are the shapes real bot walls serve.

Run:  python Tlamatini/manage.py test agent.test_crawler_resilience
"""
import importlib.util
import logging
import os
import socket
import threading
import time
import unittest
from unittest import mock

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_CRAWLER_DIR = os.path.join(_HERE, 'agents', 'crawler')


def _load_crawler():
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        spec = importlib.util.spec_from_file_location(
            'crawler_resilience_mod', os.path.join(_CRAWLER_DIR, 'crawler.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


C = _load_crawler()

# The shape of Wikipedia's head: HTML5 void <meta>/<link> with NO end tags.
WIKI_LIKE = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
    "<title>Humanity's Last Exam - Wikipedia</title>"
    '<link rel="stylesheet" href="/w/load.php"><meta name="viewport" content="width=1000">'
    '<script>var RLCONF = {"wgTitle": "x"};</script><style>.x{color:red}</style></head>'
    "<body><h1>Humanity's Last Exam</h1>"
    '<p>A benchmark of 2,500 questions across dozens of subjects.</p>'
    '<svg><title>external link icon</title></svg></body></html>'
)
CLOUDFLARE_WALL = (
    '<!DOCTYPE html><html><head><title>Just a moment...</title>'
    '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1"></script></head>'
    '<body><h1>Checking your browser before accessing the site.</h1>'
    '<p>Enable JavaScript and cookies to continue</p></body></html>'
)


def _serve_once(response: bytes):
    """A local server that answers ONE request with ``response`` and closes."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    sock.listen(4)
    port = sock.getsockname()[1]

    def run():
        try:
            conn, _addr = sock.accept()
            conn.recv(65536)
            conn.sendall(response)
            conn.close()
        except OSError:
            pass
        finally:
            sock.close()

    threading.Thread(target=run, daemon=True).start()
    return f'http://127.0.0.1:{port}/page'


class _HangingServer:
    """Accepts and never answers - or dribbles one byte at a time, forever."""

    def __init__(self, dribble=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.dribble = dribble
        self._stop = threading.Event()
        self._conns = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self._stop.is_set():
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            self._conns.append(conn)
            if self.dribble:
                threading.Thread(target=self._drip, args=(conn,), daemon=True).start()

    def _drip(self, conn):
        try:
            conn.recv(65536)
            conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html>')
            while not self._stop.is_set():
                conn.sendall(b'x')
                time.sleep(0.2)
        except OSError:
            return

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}/'

    def close(self):
        self._stop.set()
        for conn in self._conns:
            try:
                conn.close()
            except OSError:
                pass
        self.sock.close()


# =============================================================================
# 1. It reads the TEXT of a modern page (the 0-characters bug)
# =============================================================================

class TextExtractionTests(unittest.TestCase):

    def test_an_html5_page_with_void_meta_and_link_keeps_its_text(self):
        text = C.strip_html(WIKI_LIKE)
        self.assertIn('A benchmark of 2,500 questions across dozens of subjects.', text)
        self.assertNotEqual(text.strip(), '', 'the old extractor returned NOTHING here')

    def test_the_title_leads_and_scripts_styles_and_svg_stay_out(self):
        text = C.strip_html(WIKI_LIKE)
        self.assertTrue(text.startswith("Humanity's Last Exam - Wikipedia"))
        for noise in ('RLCONF', 'color:red', 'external link icon'):
            self.assertNotIn(noise, text)

    def test_an_unclosed_head_ends_where_the_body_begins(self):
        page = '<html><head><meta charset=utf-8><title>T</title><p>Body text here</p></html>'
        self.assertIn('Body text here', C.strip_html(page))

    def test_an_unclosed_title_does_not_swallow_the_page(self):
        page = '<html><head><title>Broken<body><p>Real content</p></body></html>'
        self.assertIn('Real content', C.strip_html(page))

    def test_header_names_are_case_insensitive(self):
        headers = {'content-type': 'application/pdf'}
        self.assertEqual(C._header_value(headers, 'Content-Type'), 'application/pdf')
        self.assertEqual(C._header_value(headers, 'X-Missing', 'unknown'), 'unknown')

    def test_the_example_com_page_that_came_back_empty_for_another_user(self):
        # 2026-09-29: an OLD copy of this agent logged "Extracted 0 chars" here.
        page = ('<!doctype html><html><head><title>Example Domain</title>'
                '<meta charset="utf-8" /><meta http-equiv="Content-type" '
                'content="text/html; charset=utf-8" /><meta name="viewport" '
                'content="width=device-width, initial-scale=1" />'
                '<style type="text/css">body { background-color: #f0f0f2; }</style></head>'
                '<body><div><h1>Example Domain</h1><p>This domain is for use in illustrative '
                'examples in documents.</p><p><a href="https://www.iana.org/domains/example">'
                'More information...</a></p></div></body></html>')
        text = C.strip_html(page)
        self.assertIn('This domain is for use in illustrative examples in documents.', text)
        self.assertNotIn('background-color', text)

    def test_a_minified_page_without_head_or_body_tags_keeps_its_text(self):
        page = ('<!doctype html><meta charset=utf-8><title>T</title>'
                '<link rel=stylesheet href=a.css><h1>Hello</h1><p>World</p>')
        text = C.strip_html(page)
        self.assertIn('Hello', text)
        self.assertIn('World', text)

    def test_a_region_that_never_closes_cannot_swallow_the_page(self):
        # The same CLASS of bug as the void <meta>/<link> one: any region the
        # parser opens and never closes. The safety net must rescue the text AND say so.
        body = 'This paragraph must survive the broken markup. ' * 20
        page = f'<html><body><p>Intro</p><svg><path d="M0 0"><p>{body}</p></body></html>'
        with self.assertLogs(level='WARNING') as logs:
            text = C.strip_html(page)
        self.assertIn('This paragraph must survive the broken markup.', text)
        self.assertIn('plain-text fallback', '\n'.join(logs.output))

    def test_a_healthy_page_never_uses_the_fallback(self):
        page = ('<html><head><title>T</title></head><body>'
                + '<p>Plenty of real words here.</p>' * 30 + '</body></html>')
        with self.assertNoLogs(level='WARNING'):
            text = C.strip_html(page)
        self.assertTrue(text.startswith('T\n'))

    def test_the_plain_fallback_keeps_text_and_drops_code(self):
        text = C.plain_text_fallback(
            '<p>a &amp; b</p><script>var secret = 1;</script><style>.x{}</style>'
            '<!-- hidden --><div>visible</div><svg/><p>after a self-closing svg</p>'
            '<svg><title>icon label</title></svg>')
        for kept in ('a & b', 'visible', 'after a self-closing svg'):
            self.assertIn(kept, text)
        for noise in ('secret', '.x{}', 'hidden', 'icon label'):
            self.assertNotIn(noise, text)


# =============================================================================
# 2. It analyzes the page it was GIVEN, inside a bounded crawl
# =============================================================================

class CrawlScopeTests(unittest.TestCase):

    def _run(self, config, html_by_url=None, result=None):
        processed = []

        def fake_process(page_url, host, model, system_prompt, crawl_type, timestamp, **kw):
            processed.append(page_url)
            return result

        fetch = mock.Mock(side_effect=lambda url: (html_by_url or {}).get(url, '<html></html>'))
        with mock.patch.object(C, 'fetch_page', fetch), \
                mock.patch.object(C, 'process_url_with_llm', side_effect=fake_process):
            count = C.crawl(dict({'system_prompt': 'go'}, **config), 'http://h', 'm', 'go')
        return processed, count, fetch

    def test_the_default_reads_exactly_the_given_page(self):
        processed, count, fetch = self._run({'url': 'https://en.wikipedia.org/wiki/HLE'})
        self.assertEqual(processed, ['https://en.wikipedia.org/wiki/HLE'])
        self.assertEqual(count, 1)
        fetch.assert_not_called()   # no link harvesting in page mode

    def test_single_is_an_alias_for_page(self):
        processed, _count, _fetch = self._run({'url': 'https://a.com', 'crawl_type': 'single'})
        self.assertEqual(processed, ['https://a.com'])

    def test_a_range_crawl_analyzes_the_seed_first_then_its_links(self):
        seed = 'https://seed.com'
        html = {seed: '<a href="https://seed.com/a">a</a><a href="https://other.com/x">x</a>'}
        processed, count, _fetch = self._run({'url': seed, 'crawl_type': 'small-range'}, html)
        self.assertEqual(processed, [seed, 'https://seed.com/a'])
        self.assertEqual(count, 2)

    def test_include_seed_false_restores_links_only(self):
        seed = 'https://seed.com'
        html = {seed: '<a href="https://seed.com/a">a</a>'}
        processed, _count, _fetch = self._run(
            {'url': seed, 'crawl_type': 'small-range', 'include_seed': 'false'}, html)
        self.assertEqual(processed, ['https://seed.com/a'])

    def test_the_template_ships_bounded_defaults(self):
        with open(os.path.join(_CRAWLER_DIR, 'config.yaml'), encoding='utf-8') as handle:
            config = yaml.safe_load(handle)
        self.assertEqual(config['crawl_type'], 'page')
        self.assertIs(config['include_seed'], True)
        self.assertEqual(config['max_pages'], 25)
        self.assertEqual(config['deadline_seconds'], 900)
        self.assertEqual(config['page_timeout_seconds'], 45)

    def test_a_deadline_stops_the_crawl_and_says_so(self):
        budget = C.CrawlBudget(deadline_seconds=0.05)
        self.assertFalse(budget.exhausted())
        time.sleep(0.1)
        self.assertTrue(budget.exhausted())
        self.assertIn('deadline', budget.stop_reason())
        self.assertEqual(budget.page_timeout(45.0), 5.0)

    def test_an_explicit_page_timeout_is_obeyed_exactly(self):
        # Live, 2026-09-29: page_timeout_seconds 4 stopped at 5 s, because the 5 s
        # grace meant for a page begun near the deadline was applied to EVERY page.
        budget = C.CrawlBudget(deadline_seconds=900)
        self.assertEqual(budget.page_timeout(4.0), 4.0)
        self.assertEqual(budget.page_timeout(45.0), 45.0)
        self.assertEqual(C.CrawlBudget().page_timeout(4.0), 4.0)


# =============================================================================
# 3. It never hangs on a server
# =============================================================================

class BoundedFetchTests(unittest.TestCase):

    def test_a_server_that_never_answers_is_cut_off(self):
        server = _HangingServer()
        try:
            started = time.monotonic()
            with self.assertRaises(C.FetchError) as caught:
                C.fetch_page_raw(server.url, page_timeout=1.5)
            self.assertTrue(caught.exception.timed_out)
            self.assertLess(time.monotonic() - started, 4.0)
        finally:
            server.close()

    def test_a_server_that_dribbles_forever_is_cut_off(self):
        server = _HangingServer(dribble=True)
        try:
            started = time.monotonic()
            with self.assertRaises(C.FetchError) as caught:
                C.fetch_page_raw(server.url, page_timeout=1.5)
            self.assertTrue(caught.exception.timed_out)
            self.assertLess(time.monotonic() - started, 4.0)
        finally:
            server.close()

    def test_a_huge_page_is_capped(self):
        body = b'<html><body><p>' + b'x' * 300_000 + b'</p></body></html>'
        url = _serve_once(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n'
                          b'Content-Length: %d\r\n\r\n' % len(body) + body)
        text, _headers, status = C.fetch_page_raw(url, page_timeout=10, max_bytes=10_000)
        self.assertEqual(status, 200)
        self.assertLessEqual(len(text), 10_000)

    def test_a_403_keeps_what_the_server_said(self):
        body = CLOUDFLARE_WALL.encode()
        url = _serve_once(b'HTTP/1.1 403 Forbidden\r\nContent-Type: text/html\r\n'
                          b'Content-Length: %d\r\n\r\n' % len(body) + body)
        with self.assertRaises(C.FetchError) as caught:
            C.fetch_page_raw(url, page_timeout=10)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn('Just a moment', caught.exception.body)

    def test_an_llm_timeout_is_a_runtime_error_not_a_crash(self):
        with mock.patch.object(C.urllib.request, 'urlopen', side_effect=TimeoutError('timed out')):
            with self.assertRaises(RuntimeError):
                C.query_ollama('http://127.0.0.1:1', 'm', 'sys', 'ctx')

    def test_an_llm_call_never_outlives_the_crawl_deadline_by_much(self):
        saved = C._CRAWL_DEADLINE
        try:
            C._CRAWL_DEADLINE = time.monotonic() + 10
            self.assertLessEqual(C._llm_timeout(), 40.1)
            C._CRAWL_DEADLINE = None
            self.assertEqual(C._llm_timeout(), C.LLM_TIMEOUT_SECONDS)
        finally:
            C._CRAWL_DEADLINE = saved


# =============================================================================
# 4. It never passes a refusal off as content
# =============================================================================

class RefusalTests(unittest.TestCase):

    def test_a_cloudflare_wall_is_blocked(self):
        self.assertIsNotNone(C.detect_block(200, CLOUDFLARE_WALL))
        self.assertIsNotNone(C.detect_block(503, CLOUDFLARE_WALL))

    def test_401_403_429_are_always_blocked(self):
        for code in (401, 403, 429):
            self.assertIsNotNone(C.detect_block(code, '<html>anything</html>'), code)

    def test_a_long_article_that_mentions_captcha_is_content(self):
        article = '<html><body><p>' + 'How a CAPTCHA works. ' * 200 + '</p></body></html>'
        self.assertIsNone(C.detect_block(200, article))

    def test_a_short_honest_page_is_content(self):
        page = ('<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1>'
                '<p>This domain is for use in illustrative examples.</p></body></html>')
        self.assertIsNone(C.detect_block(200, page))

    def test_fetch_errors_get_honest_names(self):
        cases = {
            'timeout': C.FetchError('slow', timed_out=True),
            'blocked': C.FetchError('HTTP 403', status_code=403),
            'not_found': C.FetchError('HTTP 404', status_code=404),
            'unreachable': C.FetchError('refused', network=True),
            'error': C.FetchError('HTTP 500', status_code=500),
        }
        for expected, error in cases.items():
            self.assertEqual(C._classify_fetch_error('https://x', error)[0], expected)


class ProcessPageTests(unittest.TestCase):

    def _process(self, fetched=None, fetch_error=None, answer='A real answer.'):
        def fake_fetch(url, include_headers=True, page_timeout=None, max_bytes=None):
            if fetch_error is not None:
                raise fetch_error
            return fetched
        with mock.patch.object(C, 'fetch_page_raw', side_effect=fake_fetch), \
                mock.patch.object(C, 'query_ollama_chunked', return_value=answer) as llm, \
                mock.patch.object(C, 'save_crawled_content', return_value='x.txt'):
            with self.assertLogs(level='INFO') as logs:
                result = C.process_url_with_llm('https://en.wikipedia.org/wiki/HLE', 'h', 'm',
                                                'Summarize', 'page', 'ts', content_mode='text')
        return result, llm, '\n'.join(logs.output)

    def test_a_wikipedia_like_page_is_analyzed_and_reported_ok(self):
        result, llm, log = self._process((WIKI_LIKE, {'content-type': 'text/html'}, 200))
        self.assertEqual(result[0], 'ok')
        sent = llm.call_args[0][3]
        self.assertIn('A benchmark of 2,500 questions', sent)
        self.assertIn('status: ok', log)
        self.assertIn('http_status: 200', log)

    def test_a_bot_wall_never_reaches_the_llm(self):
        result, llm, log = self._process((CLOUDFLARE_WALL, {'Content-Type': 'text/html'}, 200))
        self.assertEqual(result[0], 'blocked')
        llm.assert_not_called()
        self.assertNotIn('INI_SECTION_CRAWLER', log)

    def test_a_lower_case_pdf_header_is_still_binary(self):
        result, llm, _log = self._process(('%PDF-1.7 ...', {'content-type': 'application/pdf'}, 200))
        self.assertEqual(result[0], 'skipped')
        llm.assert_not_called()

    def test_an_empty_llm_answer_is_not_a_result(self):
        result, _llm, log = self._process((WIKI_LIKE, {}, 200), answer='   ')
        self.assertEqual(result[0], 'error')
        self.assertNotIn('INI_SECTION_CRAWLER', log)

    def test_a_timeout_is_reported_as_one(self):
        result, llm, _log = self._process(fetch_error=C.FetchError('slow', timed_out=True))
        self.assertEqual(result[0], 'timeout')
        llm.assert_not_called()


class NothingDeliveredTests(unittest.TestCase):

    def test_an_all_blocked_crawl_ends_with_a_named_failure(self):
        with mock.patch.object(C, 'process_url_with_llm',
                               return_value=('blocked', 'https://a.com: HTTP 403')):
            with self.assertLogs(level='INFO') as logs:
                C.crawl({'url': 'https://a.com', 'system_prompt': 'go'}, 'h', 'm', 'go')
        log = '\n'.join(logs.output)
        self.assertIn('INI_SECTION_CRAWLER', log)
        self.assertIn('status: blocked', log)
        self.assertIn('NOTHING WAS ANALYZED', log)

    def test_a_crawl_out_of_time_before_any_page_says_timeout(self):
        # Every clock reading is one second later, so a 0.5 s deadline is gone by
        # the first check. (A real 1 us deadline is not: Windows' monotonic clock
        # ticks every ~15.6 ms, so two readings can return the very same value.)
        ticks = iter(range(1000, 1000000))
        with mock.patch.object(C.time, 'monotonic', side_effect=lambda: float(next(ticks))), \
                mock.patch.object(C, 'process_url_with_llm') as process:
            with self.assertLogs(level='INFO') as logs:
                C.crawl({'url': 'https://a.com', 'system_prompt': 'go',
                         'deadline_seconds': 0.5}, 'h', 'm', 'go')
        process.assert_not_called()
        self.assertIn('status: timeout', '\n'.join(logs.output))

    def test_a_successful_crawl_adds_no_failure_section(self):
        with mock.patch.object(C, 'process_url_with_llm', return_value=('ok', 'https://a.com')):
            with self.assertLogs(level='INFO') as logs:
                C.crawl({'url': 'https://a.com', 'system_prompt': 'go'}, 'h', 'm', 'go')
        log = '\n'.join(logs.output)
        self.assertIn('Crawl summary: 1 ok', log)
        self.assertNotIn('NOTHING WAS ANALYZED', log)


# =============================================================================
# 5. Its words, its contract and its description are consistent
# =============================================================================

class ContractTests(unittest.TestCase):

    def test_every_outcome_word_is_in_the_shared_vocabulary(self):
        from agent import agent_verdict
        for word in ('ok',) + C._FAILURE_PRIORITY:
            self.assertIn(word, agent_verdict.KNOWN_STATUSES, word)

    def test_parametrizer_can_branch_on_the_status(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS['crawler']
        self.assertIn('status', fields)
        self.assertIn('http_status', fields)
        self.assertEqual(fields[-1], 'response_body')

    def test_the_chat_description_tells_the_truth(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        purpose = WRAPPED_CHAT_AGENT_BY_TOOL_NAME['chat_agent_crawler'].purpose
        self.assertNotIn('SPA', purpose)
        self.assertIn("crawl_type='page'", purpose)
        self.assertIn('playwrighter', purpose.lower())

    def test_the_agent_imports_nothing_from_tlamatini(self):
        with open(os.path.join(_CRAWLER_DIR, 'crawler.py'), encoding='utf-8') as handle:
            source = handle.read()
        self.assertNotIn('from agent', source)
        self.assertNotIn('import agent', source)


if __name__ == '__main__':
    unittest.main()
