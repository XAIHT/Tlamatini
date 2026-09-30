# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Googler must never hang, never lie, and never hammer (2026-09-28).

Measured on Angela's machine that day: the chat's `googler` tool had asked Google
and DuckDuckGo twenty times and got "No search results found" twenty times, ~39 s
each, every call recorded as a success. A live probe showed why: plain HTTP was
refused almost everywhere, Bing answered with POISONED results (Poki online games
for "Humanity's Last Exam benchmark results"), a real Chrome met Google's CAPTCHA,
and gutendex.com hung for 15 s.

Every behaviour that fixes that is pinned here, with no network at all: hangs are
simulated with local sockets that accept and never answer, and every refusal /
poisoning shape is copied from the measured pages.

Run:  python Tlamatini/manage.py test agent.test_googler_resilience
"""
import importlib.util
import json
import logging
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

from django.test import SimpleTestCase

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOOGLER = os.path.join(_HERE, 'agents', 'googler', 'googler.py')


def _load_googler():
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        spec = importlib.util.spec_from_file_location('googler_resilience_mod', _GOOGLER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


G = _load_googler()
E = G.E   # the resilience core, exactly as the agent imports it


def _hits(*pairs):
    return [{'url': url, 'title': title} for url, title in pairs]


# The poisoned answer Bing gave a script on 2026-09-28, verbatim titles.
POKI = _hits(
    ('https://poki.com/en/g/free-games', 'Free Online Games at Poki - Play Now!'),
    ('https://poki.com/en/g/subway-surfers', 'Subway Surfers - Play Online for Free! | Poki'),
    ('https://poki.com/en/boys', 'Games For Boys - Play Online for Free! - Poki'),
    ('https://poki.com/id', 'Poki - Game Online Gratis - Main Sekarang!'),
    ('https://poki.com/en/g/crossy-road', 'Play Crossy Road: No Download, Instant Play - Poki'),
)
HLE_QUERY = "Humanity's Last Exam benchmark results"


class _SilentServer:
    """Accepts TCP connections and never answers: the shape of a hung engine."""

    def __init__(self, dribble: bool = False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.dribble = dribble
        self._conns = []
        self._stop = threading.Event()
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
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html>")
            while not self._stop.is_set():
                conn.sendall(b"x")
                time.sleep(0.2)
        except OSError:
            return

    @property
    def url(self):
        return 'http://127.0.0.1:%d/search?q=x' % self.port

    def close(self):
        self._stop.set()
        for conn in self._conns:
            try:
                conn.close()
            except OSError:
                pass
        self.sock.close()


# =============================================================================
# 1. NEVER LIE: relevance and refusal classification
# =============================================================================

class QueryTermsTests(unittest.TestCase):

    def test_a_dork_is_split_into_constraints_and_anchors(self):
        terms = E.parse_query_terms('"Moby Dick" filetype:epub site:gutenberg.org')
        self.assertEqual(terms.sites, ['gutenberg.org'])
        self.assertEqual(terms.filetypes, ['epub'])
        self.assertEqual(terms.phrases, ['moby dick'])
        self.assertEqual(terms.plain_text, 'Moby Dick')

    def test_filler_words_do_not_count_as_proof(self):
        terms = E.parse_query_terms(HLE_QUERY)
        self.assertIn('humanity', terms.words)
        self.assertIn('benchmark', terms.words)
        self.assertNotIn('results', terms.words)
        self.assertNotIn('last', terms.words)

    def test_negations_and_or_groups_are_not_anchors(self):
        terms = E.parse_query_terms('(solar OR wind) turbine -review -site:scribd.com')
        self.assertNotIn('review', terms.words)
        self.assertEqual(terms.not_sites, ['scribd.com'])
        self.assertIn('turbine', terms.words)

    def test_accents_fold(self):
        self.assertEqual(E.normalize('Ángela López-Mendoza'), 'angela lopez mendoza')


class RelevanceTests(unittest.TestCase):

    def test_bings_poki_answer_is_rejected_as_poisoned(self):
        verdict, ordered, relevant = E.assess_hits(POKI, E.parse_query_terms(HLE_QUERY))
        self.assertEqual(verdict, 'poisoned')
        self.assertEqual(ordered, [])
        self.assertEqual(relevant, 0)

    def test_a_real_answer_is_accepted_relevant_first(self):
        hits = _hits(
            ('https://unrelated.example.com/', 'Cooking pasta at home'),
            ('https://en.wikipedia.org/wiki/Humanity%27s_Last_Exam', "Humanity's Last Exam"),
            ('https://lastexam.ai/', 'Humanity’s Last Exam: a benchmark at the frontier'),
        )
        verdict, ordered, relevant = E.assess_hits(hits, E.parse_query_terms(HLE_QUERY))
        self.assertEqual(verdict, 'ok')
        self.assertEqual(relevant, 2)
        self.assertIn('wikipedia.org', ordered[0]['url'])

    def test_an_engine_that_ignored_site_is_poisoned(self):
        """Bing answered `site:gutenberg.org filetype:epub` with Wikipedia."""
        hits = _hits(('https://es.m.wikipedia.org/wiki/Moby_Dick', 'Moby Dick - Wikipedia'),
                     ('https://en.m.wikipedia.org/wiki/Moby-Dick', 'Moby-Dick'))
        verdict, _ordered, _relevant = E.assess_hits(
            hits, E.parse_query_terms('"Moby Dick" filetype:epub site:gutenberg.org'))
        self.assertEqual(verdict, 'poisoned')

    def test_an_on_site_hit_is_proof_even_with_a_generic_title(self):
        """Brave's pg15.epub IS Moby Dick, titled only 'Project Gutenberg'."""
        hits = _hits(('https://www.gutenberg.org/cache/epub/15/pg15.epub', 'Project Gutenberg'),
                     ('https://www.gutenberg.org/ebooks/15', 'Project Gutenberg'))
        verdict, ordered, _relevant = E.assess_hits(
            hits, E.parse_query_terms('"Moby Dick" filetype:epub site:gutenberg.org'))
        self.assertEqual(verdict, 'ok')
        self.assertEqual(len(ordered), 2)

    def test_off_site_hits_are_dropped_under_a_site_constraint(self):
        hits = _hits(('https://target.com/a.pdf', 'A'), ('https://other.com/x', 'X'))
        verdict, ordered, _relevant = E.assess_hits(hits, E.parse_query_terms('site:target.com'))
        self.assertEqual(verdict, 'ok')
        self.assertEqual([h['url'] for h in ordered], ['https://target.com/a.pdf'])

    def test_an_operator_only_query_cannot_be_judged_and_is_kept(self):
        hits = _hits(('https://x.com/a.pdf', 'A'), ('https://y.com/b', 'B'))
        verdict, ordered, _relevant = E.assess_hits(hits, E.parse_query_terms('filetype:pdf'))
        self.assertEqual(verdict, 'ok')
        self.assertEqual(len(ordered), 2)

    def test_a_snippet_can_prove_relevance(self):
        hits = [{'url': 'https://example.org/a', 'title': 'Report',
                 'snippet': 'Terminal-Bench measures agents in the terminal'}]
        verdict, _o, _r = E.assess_hits(hits, E.parse_query_terms('"Terminal-Bench" benchmark AI'))
        self.assertEqual(verdict, 'ok')


class ClassifyResponseTests(unittest.TestCase):

    def test_duckduckgo_anomaly_is_blocked(self):
        verdict, detail = E.classify_response(
            status_code=202, final_url='https://html.duckduckgo.com/html/?q=x',
            body='<div class="anomaly-modal">Unfortunately, bots use DuckDuckGo too.</div>')
        self.assertEqual((verdict, detail), ('blocked', 'anomaly'))

    def test_google_text_browser_refusal_is_blocked(self):
        verdict, detail = E.classify_response(
            status_code=200, body="Update your browser. Your browser isn't supported any more.")
        self.assertEqual((verdict, detail), ('blocked', 'browser refused'))

    def test_startpage_error_page_is_blocked(self):
        verdict, _detail = E.classify_response(
            status_code=200, final_url='https://www.startpage.com/errors/',
            body='Startpage.com has encountered an error.')
        self.assertEqual(verdict, 'blocked')

    def test_rate_limit_status_is_blocked(self):
        self.assertEqual(E.classify_response(status_code=429, body='')[0], 'blocked')
        self.assertEqual(E.classify_response(status_code=403, body='')[0], 'blocked')

    def test_markers_never_override_relevant_results(self):
        """Brave's NORMAL page mentions 'captcha' in its scripts."""
        self.assertEqual(E.classify_response(status_code=200, body='window.captcha = 0',
                                             hits_verdict='ok')[0], 'ok')

    def test_an_honest_no_results_page_is_no_matches(self):
        verdict, _d = E.classify_response(status_code=200,
                                          body='Your search did not match any documents.')
        self.assertEqual(verdict, 'no_matches')

    def test_poisoned_and_timeout_and_error(self):
        self.assertEqual(E.classify_response(status_code=200, body='<html>games</html>',
                                             hits_verdict='poisoned')[0], 'poisoned')
        self.assertEqual(E.classify_response(timed_out=True, error='slow')[0], 'timeout')
        self.assertEqual(E.classify_response(status_code=0, error='DNS failure')[0], 'error')


class OverallStatusTests(unittest.TestCase):

    def test_found_is_ok(self):
        self.assertEqual(E.overall_status([], found=True), 'ok')

    def test_refusals_are_blocked_not_no_results(self):
        attempts = [E.attempt_record('google', 'browser', 'blocked', 'captcha'),
                    E.attempt_record('bing-http', 'http', 'poisoned', '')]
        self.assertEqual(E.overall_status(attempts, found=False), 'blocked')

    def test_an_engine_that_answered_nothing_is_no_matches(self):
        attempts = [E.attempt_record('google', 'browser', 'no_matches', ''),
                    E.attempt_record('bing-http', 'http', 'blocked', '')]
        self.assertEqual(E.overall_status(attempts, found=False), 'no_matches')

    def test_all_network_errors_is_unreachable(self):
        attempts = [E.attempt_record('google', 'http', 'error', 'DNS'),
                    E.attempt_record('bing', 'http', 'error', 'DNS')]
        self.assertEqual(E.overall_status(attempts, found=False), 'unreachable')

    def test_every_status_word_is_in_the_shared_vocabulary(self):
        from agent import agent_verdict
        for word in ('ok', 'no_matches', 'blocked', 'unreachable', 'timeout', 'error'):
            with self.subTest(word=word):
                self.assertIn(word, agent_verdict.KNOWN_STATUSES)


# =============================================================================
# 2. NEVER HAMMER: the health ledger
# =============================================================================

class EngineHealthTests(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, 'health.json')
        self.now = [1_000_000.0]
        self.health = E.EngineHealth(path=self.path, clock=lambda: self.now[0])

    def tearDown(self):
        self._dir.cleanup()

    def test_refusals_cool_down_on_a_rising_ladder_and_success_resets(self):
        key = 'browser:google'
        ladder = E.COOLDOWNS['blocked']
        for step in ladder:
            self.health.record(key, 'blocked', 'captcha')
            self.assertAlmostEqual(self.health.cooling_left(key), step)
        self.health.record(key, 'blocked', 'captcha')           # stays at the top
        self.assertAlmostEqual(self.health.cooling_left(key), ladder[-1])
        self.health.record(key, 'ok')
        self.assertEqual(self.health.cooling_left(key), 0.0)

    def test_no_results_is_not_a_refusal(self):
        self.health.record('http:bing-http', 'no_matches')
        self.assertEqual(self.health.cooling_left('http:bing-http'), 0.0)

    def test_recent_success_first_and_cooling_last(self):
        self.health.record('browser:brave', 'ok')
        self.health.record('browser:google', 'blocked', 'captcha')
        order = self.health.order(['browser:google', 'browser:bing', 'browser:brave'])
        self.assertEqual(order, ['browser:brave', 'browser:bing', 'browser:google'])

    def test_when_everything_cools_the_soonest_is_still_probed(self):
        self.health.record('browser:google', 'blocked')
        self.health.record('browser:google', 'blocked')     # 600 s
        self.health.record('browser:brave', 'timeout')      # 60 s
        runnable, skipped = self.health.plan(['browser:google', 'browser:brave'])
        self.assertEqual(runnable, ['browser:brave'])
        self.assertEqual(skipped, ['browser:google'])

    def test_the_ledger_is_shared_through_its_file(self):
        self.health.record('http:duckduckgo-html', 'blocked', 'anomaly')
        self.health.save()
        other = E.EngineHealth(path=self.path, clock=lambda: self.now[0])
        self.assertGreater(other.cooling_left('http:duckduckgo-html'), 0)

    def test_a_corrupt_ledger_is_unknown_not_an_error(self):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write('{not json')
        self.assertEqual(E.EngineHealth(path=self.path).data, {})


# =============================================================================
# 3. NEVER HANG: bounded fetch and the hedged runner
# =============================================================================

class BoundedFetchTests(unittest.TestCase):

    def test_a_server_that_never_answers_cannot_hold_the_caller(self):
        server = _SilentServer()
        try:
            started = time.monotonic()
            result = E.bounded_fetch(server.url, timeout=1.0)
            elapsed = time.monotonic() - started
        finally:
            server.close()
        self.assertTrue(result['timed_out'])
        self.assertLess(elapsed, 3.0)

    def test_a_server_that_dribbles_bytes_forever_is_cut_off(self):
        server = _SilentServer(dribble=True)
        try:
            started = time.monotonic()
            result = E.bounded_fetch(server.url, timeout=1.5)
            elapsed = time.monotonic() - started
        finally:
            server.close()
        self.assertTrue(result['timed_out'])
        self.assertLess(elapsed, 3.5)

    def test_the_shared_deadline_wins_over_the_per_call_timeout(self):
        server = _SilentServer()
        try:
            deadline = E.Deadline(1.0)
            started = time.monotonic()
            E.bounded_fetch(server.url, timeout=30.0, deadline=deadline)
            elapsed = time.monotonic() - started
        finally:
            server.close()
        self.assertLess(elapsed, 3.0)

    def test_no_budget_left_means_no_request(self):
        deadline = E.Deadline(0.5)
        time.sleep(0.6)
        result = E.bounded_fetch('http://127.0.0.1:9/', deadline=deadline)
        self.assertTrue(result['timed_out'])


class HedgedRunnerTests(unittest.TestCase):

    def test_a_fast_answer_beats_a_hung_route(self):
        def hung():
            time.sleep(30)
            return {'verdict': 'ok'}

        def fast():
            time.sleep(0.1)
            return {'verdict': 'ok', 'hits': [1]}

        started = time.monotonic()
        winner, _finished = E.run_hedged([('hung', hung), ('fast', fast)], deadline=E.Deadline(10),
                                         stagger=0.2, max_parallel=2,
                                         accept=lambda r: r.get('verdict') == 'ok')
        self.assertEqual(winner[0], 'fast')
        self.assertLess(time.monotonic() - started, 3.0)

    def test_everything_hung_returns_at_the_deadline(self):
        def hung():
            time.sleep(30)
            return {}

        started = time.monotonic()
        winner, finished = E.run_hedged([('a', hung), ('b', hung)], deadline=E.Deadline(1.0),
                                        stagger=0.0, max_parallel=2)
        self.assertIsNone(winner)
        self.assertEqual(finished, [])
        self.assertLess(time.monotonic() - started, 2.5)

    def test_a_crashing_job_is_an_error_result_not_a_crash(self):
        def boom():
            raise RuntimeError('boom')

        winner, finished = E.run_hedged([('x', boom)], deadline=E.Deadline(5))
        self.assertIsNone(winner)
        self.assertEqual(finished[0][1]['verdict'], 'error')


# =============================================================================
# 4. TIERS: hedged HTTP engines and open knowledge sources
# =============================================================================

class HttpTierTests(unittest.TestCase):

    ENGINES = [{'name': 'duckduckgo-html', 'url': 'https://a/{q}'},
               {'name': 'bing-http', 'url': 'https://b/{q}'},
               {'name': 'duckduckgo-lite', 'url': 'https://c/{q}'}]

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.health = E.EngineHealth(path=os.path.join(self._dir.name, 'h.json'))

    def tearDown(self):
        self._dir.cleanup()

    def _answers(self, mapping):
        def fake(engine, query, n, **_kw):
            verdict, hits = mapping.get(engine['name'], ('empty', []))
            if verdict == 'hang':
                time.sleep(30)
            return E.attempt_record(engine['name'], 'http', verdict, verdict, 5, hits=hits)
        return fake

    def _search(self, fake, seconds=10.0):
        with mock.patch.object(E, 'http_search_one', side_effect=fake):
            return E.http_tier_search('q', 5, terms=E.parse_query_terms('q'),
                                      deadline=E.Deadline(seconds), health=self.health,
                                      engines=self.ENGINES, stagger=0.0, max_parallel=1)

    def test_refusals_are_remembered_and_a_relevant_answer_wins(self):
        answer = [{'url': 'https://ok.example/q', 'title': 'q'}]
        hits, winner, attempts = self._search(self._answers({
            'duckduckgo-html': ('blocked', []), 'bing-http': ('poisoned', []),
            'duckduckgo-lite': ('ok', answer)}))
        self.assertEqual(hits, answer)
        self.assertEqual(winner['engine'], 'duckduckgo-lite')
        self.assertGreater(self.health.cooling_left('http:duckduckgo-html'), 0)
        self.assertGreater(self.health.cooling_left('http:bing-http'), 0)
        self.assertEqual([a['verdict'] for a in attempts], ['blocked', 'poisoned', 'ok'])

    def test_a_cooling_route_is_not_asked_again(self):
        self.health.record('http:duckduckgo-html', 'blocked', 'anomaly')
        calls = []

        def fake(engine, query, n, **_kw):
            calls.append(engine['name'])
            return E.attempt_record(engine['name'], 'http', 'empty', '', 1, hits=[])

        _hits, _winner, attempts = self._search(fake)
        self.assertNotIn('duckduckgo-html', calls)
        self.assertIn('skipped', [a['verdict'] for a in attempts])

    def test_hung_routes_end_at_the_deadline_as_timeouts(self):
        started = time.monotonic()
        hits, winner, attempts = self._search(self._answers({
            'duckduckgo-html': ('hang', []), 'bing-http': ('hang', []),
            'duckduckgo-lite': ('hang', [])}), seconds=1.0)
        self.assertEqual(hits, [])
        self.assertIsNone(winner)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertTrue(any(a['verdict'] == 'timeout' for a in attempts))


class OpenSourcesTests(unittest.TestCase):

    @staticmethod
    def _wiki(terms, n, deadline):
        return ([{'url': 'https://en.wikipedia.org/wiki/Humanity%27s_Last_Exam',
                  'title': "Humanity's Last Exam", 'snippet': 'a benchmark', 'source': 'wikipedia'},
                 {'url': 'https://en.wikipedia.org/wiki/Cooking', 'title': 'Cooking',
                  'snippet': 'food', 'source': 'wikipedia'}],
                E._empty_fetch('wiki', ''))

    @staticmethod
    def _slow(terms, n, deadline):
        time.sleep(30)
        return [], E._empty_fetch('slow', '')

    def test_a_hung_source_cannot_hold_the_others_and_off_topic_hits_are_dropped(self):
        sources = {'wikipedia': (self._wiki, ('wikipedia.org',)), 'gutenberg': (self._slow, ('gutenberg.org',))}
        with mock.patch.dict(E.OPEN_SOURCES, sources, clear=True), \
                mock.patch.object(E, 'DEFAULT_OPEN_SOURCES', ('wikipedia', 'gutenberg')):
            started = time.monotonic()
            hits, attempts = E.open_sources_search(E.parse_query_terms(HLE_QUERY), 5,
                                                   deadline=E.Deadline(20), budget_seconds=1.0)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual([h['title'] for h in hits], ["Humanity's Last Exam"])
        verdicts = {a['engine']: a['verdict'] for a in attempts}
        self.assertEqual(verdicts['wikipedia'], 'ok')
        self.assertEqual(verdicts['gutenberg'], 'timeout')

    def test_a_site_constraint_selects_only_the_matching_sources(self):
        self.assertEqual(E.select_open_sources(E.parse_query_terms('site:github.com agents')), ['github'])
        self.assertEqual(E.select_open_sources(E.parse_query_terms('site:en.wikipedia.org x')), ['wikipedia'])
        self.assertEqual(E.select_open_sources(E.parse_query_terms('site:.gov climate')), [])

    def test_book_hunts_ask_gutenberg_first(self):
        names = E.select_open_sources(E.parse_query_terms('"Moby Dick" filetype:epub'))
        self.assertEqual(names[0], 'gutenberg')


class PageTextTests(unittest.TestCase):

    def test_scripts_and_styles_never_reach_the_text(self):
        title, text = E.html_to_text(
            '<html><head><title>T</title><style>.x{}</style></head><body><script>var a=1;'
            '</script><p>Hello</p><div>World</div></body></html>')
        self.assertEqual(title, 'T')
        self.assertIn('Hello', text)
        self.assertIn('World', text)
        self.assertNotIn('var a', text)
        self.assertNotIn('.x', text)

    def test_a_page_that_leaves_out_its_closing_head_keeps_its_text(self):
        # HTML5 allows it and minified pages do it; the old depth counter then
        # waited for </head> forever and returned NO text at all (2026-09-29).
        title, text = E.html_to_text('<html><head><meta charset=utf-8><title>T</title>'
                                     '<link rel=stylesheet href=a.css><p>Body text here</p></html>')
        self.assertEqual(title, 'T')
        self.assertIn('Body text here', text)

    def test_a_minified_page_without_head_or_body_tags_keeps_its_text(self):
        _title, text = E.html_to_text('<!doctype html><meta charset=utf-8><title>T</title>'
                                      '<link rel=stylesheet href=a.css><h1>Hello</h1><p>World</p>')
        self.assertIn('Hello', text)
        self.assertIn('World', text)

    def test_a_self_closing_skip_tag_never_opens_a_region(self):
        _title, text = E.html_to_text('<body><p>Alpha</p><svg/><p>Beta</p></body>')
        self.assertIn('Alpha', text)
        self.assertIn('Beta', text)

    def test_a_region_that_never_closes_falls_back_and_says_so(self):
        body = 'This paragraph must survive the broken markup. ' * 20
        notes = []
        _title, text = E.html_to_text(
            f'<html><body><p>Intro</p><svg><path d="M0 0"><p>{body}</p></body></html>', report=notes)
        self.assertIn('This paragraph must survive the broken markup.', text)
        self.assertEqual(len(notes), 1)
        self.assertIn('plain-text fallback', notes[0])

    def test_a_healthy_page_never_uses_the_fallback(self):
        notes = []
        page = ('<html><head><title>T</title></head><body>'
                + '<p>Plenty of real words here.</p>' * 30 + '</body></html>')
        _title, text = E.html_to_text(page, report=notes)
        self.assertEqual(notes, [])
        self.assertIn('Plenty of real words here.', text)

    def test_a_binary_url_is_a_found_file(self):
        result = E.fetch_page_text('https://www.gutenberg.org/cache/epub/15/pg15.epub',
                                   deadline=E.Deadline(5))
        self.assertEqual(result['kind'], 'file')
        self.assertEqual(result['filetype'], 'epub')

    def test_redirectors_unwrap(self):
        self.assertEqual(E.unwrap_redirect(
            'https://r.search.yahoo.com/_ylt=A/RV=2/RE=1/RO=10/RU=https%3a%2f%2fwww.tbench.ai%2f/RK=2/RS=x-'),
            'https://www.tbench.ai/')
        self.assertEqual(E.unwrap_redirect('/url?q=https://example.com/a&sa=U'), 'https://example.com/a')


# =============================================================================
# 5. THE AGENT'S ORCHESTRATOR: the tiers in order, one budget, a truthful report
# =============================================================================

class OrchestratorTests(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.health = E.EngineHealth(path=os.path.join(self._dir.name, 'h.json'))

    def tearDown(self):
        self._dir.cleanup()

    def test_every_web_route_refuses_so_open_sources_answer_and_say_so(self):
        refused = [E.attempt_record('duckduckgo-html', 'http', 'blocked', 'anomaly')]
        answer = [{'url': 'https://en.wikipedia.org/wiki/X', 'title': 'X benchmark', 'source': 'wikipedia'}]
        report = {}
        with mock.patch.object(E, 'http_tier_search', return_value=([], None, refused)), \
                mock.patch.object(G, '_open_browser_session', return_value=None), \
                mock.patch.object(E, 'open_sources_search',
                                  return_value=(answer, [E.attempt_record('wikipedia', 'open', 'ok')])):
            results = G.googler_search('X benchmark', 3, 'links_only', deadline_seconds=30,
                                       report=report, health=self.health)
        self.assertEqual(results[0]['url'], answer[0]['url'])
        self.assertEqual(results[0]['source'], 'wikipedia')
        self.assertEqual(report['search_status'], 'ok')
        self.assertEqual(report['tier'], 'open_sources')
        self.assertEqual(report['engine'], 'wikipedia')
        self.assertIn('duckduckgo-html (http: anomaly)', report['refused'])

    def test_when_nothing_answers_the_report_says_blocked_not_no_results(self):
        refused = [E.attempt_record('bing-http', 'http', 'poisoned', 'games')]
        report = {}
        with mock.patch.object(E, 'http_tier_search', return_value=([], None, refused)), \
                mock.patch.object(G, '_open_browser_session', return_value=None), \
                mock.patch.object(E, 'open_sources_search', return_value=([], [])):
            results = G.googler_search('anything at all', 3, 'text', deadline_seconds=30,
                                       report=report, health=self.health)
        self.assertEqual(results, [])
        self.assertEqual(report['search_status'], 'blocked')

    def test_pinned_engines_skip_tier_zero_and_open_sources(self):
        with mock.patch.object(E, 'http_tier_search') as http_tier, \
                mock.patch.object(E, 'open_sources_search') as open_sources, \
                mock.patch.object(G, '_open_browser_session', return_value=None):
            G.googler_search('q', 3, 'links_only', engines=['google'], deadline_seconds=30,
                             health=self.health)
        http_tier.assert_not_called()
        open_sources.assert_not_called()

    def test_the_result_json_is_written_atomically(self):
        path = os.path.join(self._dir.name, 'out', 'r.json')
        G._write_result_json(path, 'q', 'q', [{'url': 'https://x'}],
                             {'search_status': 'ok', 'engine': 'brave', 'tier': 'browser'})
        with open(path, encoding='utf-8') as handle:
            payload = json.load(handle)
        self.assertEqual(payload['format'], 'tlamatini-googler-result')
        self.assertEqual(payload['search_status'], 'ok')
        self.assertFalse(os.path.exists(path + '.tmp'))

    def test_window_modes(self):
        self.assertEqual(G._resolve_window_mode('', False), 'visible')
        self.assertEqual(G._resolve_window_mode('', True), 'headless')
        self.assertEqual(G._resolve_window_mode('offscreen', True), 'offscreen')
        self.assertEqual(G._resolve_profile_dir('none'), '')
        self.assertTrue(G._resolve_profile_dir('').endswith(os.path.join('googler', 'chrome-profile')))

    def test_the_agent_never_imports_tlamatini_internals(self):
        with open(os.path.join(_HERE, 'agents', 'googler', 'googler_engines.py'), encoding='utf-8') as fh:
            source = fh.read()
        self.assertNotIn('from agent', source)
        self.assertNotIn('import agent', source)


# =============================================================================
# 6. THE CHAT TOOL: runs the agent as a process, bounded, and tells the truth
# =============================================================================

class _FakeProcess:
    pid = 999999

    def __init__(self, finishes=True):
        self.finishes = finishes
        self.killed = False

    def poll(self):
        return 0 if (self.finishes or self.killed) else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


class GooglerChatToolTests(SimpleTestCase):

    def test_blocked_is_an_error_line_that_counts_as_a_failure(self):
        from agent import tools
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        text = tools._format_googler_result('q', {
            'search_status': 'blocked', 'results': [], 'elapsed_seconds': 4.2,
            'refused': ['google (browser: captcha)', 'duckduckgo-html (http: anomaly)'],
            'cooling': ['browser:google (blocked, retry in 2m59s)']})
        self.assertTrue(text.startswith('Error: WEB SEARCH BLOCKED'))
        self.assertIn('Do NOT retry googler', text)
        self.assertIn('captcha', text)
        failed, _detail = MultiTurnToolAgentExecutor._result_is_failure(text)
        self.assertTrue(failed)

    def test_results_name_their_source_and_count_as_success(self):
        from agent import tools
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        text = tools._format_googler_result('q', {
            'search_status': 'ok', 'engine': 'wikipedia', 'tier': 'open_sources',
            'elapsed_seconds': 2.0, 'refused': [], 'cooling': [],
            'results': [{'url': 'https://en.wikipedia.org/wiki/Q', 'title': 'Q', 'status_code': 200,
                         'content': 'body', 'source': 'wikipedia'},
                        {'url': 'https://x.org/b.pdf', 'kind': 'file', 'filetype': 'pdf'}]})
        self.assertTrue(text.startswith("Web search for 'q': 2 result(s) via wikipedia"))
        self.assertIn('OPEN KNOWLEDGE SOURCES', text)
        self.assertIn('FILE FOUND [PDF]', text)
        self.assertFalse(MultiTurnToolAgentExecutor._result_is_failure(text)[0])

    def test_no_results_is_honest_and_not_a_failure(self):
        from agent import tools
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        text = tools._format_googler_result('q', {'search_status': 'no_matches', 'elapsed_seconds': 1})
        self.assertTrue(text.startswith('No results:'))
        self.assertFalse(MultiTurnToolAgentExecutor._result_is_failure(text)[0])

    def test_every_result_survives_the_executors_tool_reply_cap(self):
        # 2026-09-28: one 37,000-character page filled the executor's 24,000-char
        # tool-reply cap on its own, so results 2..5 never reached the model and it
        # spent 700 s hunting for them in the logs. The pages now share the reply.
        from agent import tools
        from agent.mcp_agent import _cap_tool_message_content
        results = [{'url': f'https://site{i}.example/page', 'title': f'Title {i}',
                    'status_code': 200, 'snippet': 's' * 200, 'content': f'P{i} ' + 'x' * 37000}
                   for i in range(1, 6)]
        with mock.patch.object(tools, 'get_config_value', return_value=24000):
            text = tools._format_googler_result('q', {
                'search_status': 'ok', 'engine': 'bing', 'tier': 'http',
                'elapsed_seconds': 3.0, 'results': results})
        self.assertLess(len(text), 24000)
        self.assertEqual(_cap_tool_message_content(text, cap=24000), text)
        first_section = text.index('=== Result 1 ===')
        self.assertLess(text.index('Results at a glance'), first_section)
        for i in range(1, 6):
            self.assertIn(f'https://site{i}.example/page', text[:first_section])
            self.assertIn(f'=== Result {i} ===', text)
            self.assertIn(f'P{i} ', text)
        self.assertEqual(text.count('page text shortened to'), 5)

    def test_short_pages_are_never_shortened(self):
        from agent import tools
        with mock.patch.object(tools, 'get_config_value', return_value=24000):
            text = tools._format_googler_result('q', {
                'search_status': 'ok', 'engine': 'bing', 'tier': 'http', 'elapsed_seconds': 1.0,
                'results': [{'url': 'https://a.example/', 'title': 'A', 'status_code': 200,
                             'content': 'short page body'}]})
        self.assertIn('short page body', text)
        self.assertNotIn('shortened', text)

    def _run(self, process, settings=(30.0, 'offscreen', 0.0), cancelled=False, payload=None):
        from agent import tools
        with tempfile.TemporaryDirectory() as root:
            runtime_dir = os.path.join(root, 'googler_001_abc')
            os.makedirs(runtime_dir)
            with open(os.path.join(runtime_dir, 'config.yaml'), 'w', encoding='utf-8') as handle:
                handle.write('query: ""\n')
            if payload is not None:
                with open(os.path.join(runtime_dir, 'googler_result.json'), 'w', encoding='utf-8') as fh:
                    json.dump(payload, fh)
            with mock.patch.object(tools, '_googler_chat_settings', return_value=settings), \
                    mock.patch.object(tools, '_GOOGLER_CHAT_KILL_GRACE', 0.5), \
                    mock.patch.object(tools, '_find_template_agent_by_dir_name',
                                      return_value={'agent_dir': root}), \
                    mock.patch('agent.path_guard.resolve_temp_path', return_value=root), \
                    mock.patch.object(tools, 'create_isolated_runtime_copy',
                                      return_value=('abc12345', runtime_dir, '')), \
                    mock.patch.object(tools, 'resolve_runtime_script_path',
                                      return_value=os.path.join(runtime_dir, 'googler.py')), \
                    mock.patch.object(tools, '_googler_search_cancelled', return_value=cancelled), \
                    mock.patch.object(tools.subprocess, 'Popen', return_value=process):
                started = time.monotonic()
                text = tools._run_googler_agent('q', 3)
                return text, time.monotonic() - started

    def test_the_agents_json_becomes_the_answer(self):
        text, _elapsed = self._run(_FakeProcess(finishes=True), payload={
            'search_status': 'ok', 'engine': 'brave', 'tier': 'browser', 'elapsed_seconds': 3.1,
            'results': [{'url': 'https://www.tbench.ai/', 'title': 'Terminal-Bench',
                         'status_code': 200, 'content': 'tbench'}]})
        self.assertIn("via brave", text)
        self.assertIn('https://www.tbench.ai/', text)

    def test_a_hung_agent_is_killed_at_the_hard_limit(self):
        process = _FakeProcess(finishes=False)
        text, elapsed = self._run(process, settings=(0.5, 'offscreen', 0.0))
        self.assertTrue(process.killed)
        self.assertTrue(text.startswith('Error: WEB SEARCH TIMED OUT'))
        self.assertLess(elapsed, 10.0)

    def test_cancel_stops_the_search_at_once(self):
        process = _FakeProcess(finishes=False)
        text, elapsed = self._run(process, cancelled=True)
        self.assertTrue(process.killed)
        self.assertTrue(text.startswith('Error: WEB SEARCH CANCELLED'))
        self.assertLess(elapsed, 10.0)

    def test_the_tool_still_teaches_the_operator_language(self):
        from agent.tools import googler
        doc = googler.description or ''
        for token in ('filetype:', 'site:', 'NEVER HANG', 'Error: WEB SEARCH BLOCKED'):
            with self.subTest(token=token):
                self.assertIn(token, doc)


if __name__ == '__main__':
    unittest.main()
