# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Googler resilience core: the part of Googler that must never hang and never lie.

WHY THIS FILE EXISTS  (measured on Angela's machine, 2026-09-28)
---------------------------------------------------------------
The chat's ``googler`` tool asked Google and DuckDuckGo twenty times in a row and
got "No search results found" twenty times, ~39 s each, while every call was
recorded as a success. A live probe of thirteen routes explained why:

* plain HTTP was refused by almost every engine: DuckDuckGo (all three routes)
  answered 202 "bots use DuckDuckGo too", Brave 429 + captcha, Mojeek a captcha
  and then 403, Ecosia a 403 firewall page, Yahoo a bot-verification redirect,
  Startpage its /errors/ page, and Google told text browsers "Your browser isn't
  supported any more";
* Bing DID answer, with POISONED results: Poki online games for "Humanity's Last
  Exam benchmark results", and Wikipedia for a ``site:gutenberg.org
  filetype:epub`` dork. Accepting that as an answer is worse than failing,
  because it looks plausible;
* even a visible, real Chrome met Google's /sorry/ CAPTCHA and DuckDuckGo's
  anomaly page, while Brave and Yahoo answered it correctly;
* open knowledge APIs (Wikipedia, arXiv, Hacker News, OpenAlex, GitHub, the
  Internet Archive) all answered in under a second, and gutendex.com hung for
  15 s: exactly the kind of stall that must never freeze a chat.

THE CONTRACT (do NOT weaken)
  1. NEVER HANG. Every network call runs on a daemon thread under ONE shared
     wall-clock :class:`Deadline`. A straggler is abandoned, never awaited.
  2. NEVER LIE. "blocked", "poisoned", "no results" and "timed out" are four
     different answers and are reported as four different answers. Result sets
     that do not mention the query are rejected, never passed off as an answer.
  3. NEVER HAMMER. A refusal puts that route on a cooldown in a small health
     ledger shared by every Googler run on the machine, so repeated searches
     stop provoking the engines that already refused. Hammering a refusing
     engine is what makes a block last longer. A route that answered recently
     is tried first.
  4. FIND A WAY. Independent routes are tried in health order; when every web
     engine refuses, the open knowledge APIs still answer, and are labelled.
  5. STDLIB ONLY, no side effects at import (no logging configuration, no file
     writes), and no ``agent.*`` imports: this file travels inside every pool
     copy of the Googler agent and must behave identically frozen and from
     source. Every import is at module level on purpose: code that runs after a
     search must never trigger an import.
"""

from __future__ import annotations

import base64
import gzip
import html
import json
import os
import queue
import re
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from html.parser import HTMLParser

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

#: Identifies Tlamatini honestly to the open APIs, which ask for exactly that.
API_UA = "Tlamatini-Googler/2.0 (+https://github.com/XAIHT/Tlamatini)"

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "close",
}


# =============================================================================
# 1. ONE WALL-CLOCK BUDGET FOR THE WHOLE SEARCH
# =============================================================================

class Deadline:
    """A monotonic wall-clock budget shared by every stage of one search."""

    def __init__(self, seconds: float):
        self.start = time.monotonic()
        self.end = self.start + max(0.5, float(seconds))

    def remaining(self, reserve: float = 0.0) -> float:
        return max(0.0, self.end - float(reserve) - time.monotonic())

    def expired(self, reserve: float = 0.0) -> bool:
        return self.remaining(reserve) <= 0.0

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def child(self, seconds: float | None = None, reserve: float = 0.0) -> "Deadline":
        """A sub-budget that ends no later than this one (minus ``reserve``)."""
        now = time.monotonic()
        end = self.end - float(reserve)
        if seconds is not None:
            end = min(end, now + float(seconds))
        sub = Deadline.__new__(Deadline)
        sub.start = now
        sub.end = max(now, end)
        return sub


# =============================================================================
# 2. BOUNDED FETCH: an HTTP request that CANNOT outlive its budget
# =============================================================================
#
# urllib's ``timeout`` bounds each socket operation, not the whole transfer: a
# server that dribbles a byte every few seconds would hold the caller forever,
# and DNS resolution is not covered by it at all. So the request runs on a
# DAEMON thread and the caller waits on a queue with the real budget. A request
# that overruns is abandoned (its thread dies with its socket later) and is
# reported as a timeout, never waited on.

def _decode_body(raw: bytes, content_type: str = "", content_encoding: str = "") -> str:
    encoding = (content_encoding or "").lower()
    try:
        if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif "deflate" in encoding:
            raw = zlib.decompress(raw)
    except Exception:
        pass
    charset = "utf-8"
    match = re.search(r"charset=([\w\-]+)", content_type or "", re.IGNORECASE)
    if match:
        charset = match.group(1)
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _empty_fetch(url: str, error: str, timed_out: bool = False, elapsed: float = 0.0) -> dict:
    return {"url": url, "status_code": 0, "final_url": url, "body": "",
            "content_type": "", "error": error, "timed_out": timed_out,
            "elapsed": round(elapsed, 3)}


def _fetch_worker(url, headers, data, sock_timeout, max_bytes, stop_at, out_q):
    started = time.monotonic()
    result = _empty_fetch(url, "")
    try:
        method = "POST" if data is not None else "GET"
        request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
        with urllib.request.urlopen(request, timeout=sock_timeout) as response:
            result["status_code"] = int(getattr(response, "status", 200) or 200)
            result["final_url"] = response.geturl() or url
            result["content_type"] = response.headers.get("Content-Type", "") or ""
            content_encoding = response.headers.get("Content-Encoding", "") or ""
            # read1() returns whatever has arrived, so a server that dribbles a
            # byte at a time cannot pin this loop inside one giant read().
            read_some = getattr(response, "read1", None) or response.read
            chunks, total = [], 0
            while total < max_bytes:
                if time.monotonic() > stop_at:
                    result["timed_out"] = True
                    result["error"] = "the transfer outlived its time budget"
                    break
                chunk = read_some(min(65536, max_bytes - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            result["body"] = _decode_body(b"".join(chunks), result["content_type"], content_encoding)
    except urllib.error.HTTPError as exc:
        result["status_code"] = int(getattr(exc, "code", 0) or 0)
        result["error"] = "HTTP %s" % result["status_code"]
        try:
            result["final_url"] = exc.geturl() or url
        except Exception:
            pass
        try:
            headers_in = exc.headers
            content_type = (headers_in.get("Content-Type", "") if headers_in else "") or ""
            content_encoding = (headers_in.get("Content-Encoding", "") if headers_in else "") or ""
            result["content_type"] = content_type
            result["body"] = _decode_body(exc.read(300_000), content_type, content_encoding)
        except Exception:
            pass
    except Exception as exc:
        text = str(exc)
        result["error"] = "%s: %s" % (type(exc).__name__, text[:160])
        if isinstance(exc, TimeoutError) or "timed out" in text.lower():
            result["timed_out"] = True
    result["elapsed"] = round(time.monotonic() - started, 3)
    try:
        out_q.put_nowait(result)
    except Exception:
        pass


def bounded_fetch(url: str, *, headers: dict | None = None, data: bytes | None = None,
                  timeout: float = 10.0, deadline: Deadline | None = None,
                  max_bytes: int = 1_500_000) -> dict:
    """Fetch ``url`` and return within ``min(timeout, deadline)``. Never raises.

    Returns a dict with ``status_code``, ``final_url``, ``body``, ``content_type``,
    ``error`` (empty on success), ``timed_out`` and ``elapsed``.
    """
    budget = float(timeout)
    if deadline is not None:
        budget = min(budget, deadline.remaining())
    if budget <= 0.05:
        return _empty_fetch(url, "no time left in the search budget", timed_out=True)
    out_q: queue.Queue = queue.Queue(maxsize=1)
    stop_at = time.monotonic() + budget
    worker = threading.Thread(
        target=_fetch_worker,
        args=(url, headers or BROWSER_HEADERS, data, budget, max_bytes, stop_at, out_q),
        name="googler-fetch", daemon=True,
    )
    worker.start()
    try:
        return out_q.get(timeout=budget + 0.5)
    except queue.Empty:
        return _empty_fetch(url, "no answer within %.1fs (abandoned)" % budget,
                            timed_out=True, elapsed=budget)


# =============================================================================
# 3. HEDGED RUNNER: start the next route before the slow one gives up
# =============================================================================

def run_hedged(jobs, *, deadline: Deadline, stagger: float = 0.8, max_parallel: int = 3,
               accept=None, wait_all: bool = False, started=None):
    """Run ``jobs`` (``[(name, callable), ...]``) on daemon threads.

    A new job starts every ``stagger`` seconds, or immediately when a running
    one finishes without being accepted, never more than ``max_parallel`` at
    once. Returns ``(winner, finished)``: ``winner`` is the first ``(name,
    result)`` for which ``accept(result)`` is true (``None`` if nothing was),
    ``finished`` lists every ``(name, result)`` that completed in time. Jobs
    still running at the deadline are ABANDONED; their threads are daemons, so
    this function always returns on time. ``wait_all`` keeps collecting after a
    winner (used when every answer that arrives in time is merged). ``started``
    (an optional list) receives the name of every job actually launched, so a
    caller never blames a route that was never even tried.
    """
    accept = accept or (lambda _result: False)
    pending = list(jobs)
    results_q: queue.Queue = queue.Queue()
    finished: list = []
    winner = None
    in_flight = 0
    next_start = 0.0

    def _run(job_name, job):
        try:
            job_result = job()
        except Exception as exc:  # a job must never take the runner down
            job_result = {"verdict": "error", "detail": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
        results_q.put((job_name, job_result))

    while True:
        now = time.monotonic()
        while pending and in_flight < max_parallel and now >= next_start and not deadline.expired():
            name, job = pending.pop(0)
            threading.Thread(target=_run, args=(name, job), name="googler-%s" % name, daemon=True).start()
            if started is not None:
                started.append(name)
            in_flight += 1
            next_start = now + max(0.0, float(stagger))
        if deadline.expired() or (in_flight == 0 and not pending):
            break
        try:
            name, result = results_q.get(timeout=max(0.01, min(0.1, deadline.remaining())))
        except queue.Empty:
            continue
        in_flight -= 1
        finished.append((name, result))
        if winner is None and accept(result):
            winner = (name, result)
            if not wait_all:
                break
        next_start = 0.0  # a slot freed without an answer: start the next route now
    return winner, finished


# =============================================================================
# 4. TEXT, URL AND LINK HELPERS
# =============================================================================

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def clean_text(fragment) -> str:
    """Visible text of an HTML fragment, on one line."""
    text = _TAG_RE.sub(" ", str(fragment or ""))
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def normalize(text) -> str:
    """Lower-case ASCII words separated by single spaces.

    Accents are folded (``Ángela`` -> ``angela``) and every punctuation mark,
    apostrophe and hyphen becomes a separator, so ``Terminal-Bench``,
    ``terminal bench`` and ``/terminal_bench/`` all normalise the same way."""
    folded = unicodedata.normalize("NFKD", str(text or ""))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return _WS_RE.sub(" ", _NON_ALNUM_RE.sub(" ", folded)).strip()


def domain_of(url) -> str:
    try:
        netloc = urllib.parse.urlsplit(str(url or "")).netloc.lower()
    except Exception:
        return ""
    netloc = netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


def site_matches(domain: str, site: str) -> bool:
    """True when ``domain`` satisfies a ``site:`` value (host, parent or TLD)."""
    site = str(site or "").strip().lower().strip("/")
    site = site.split("/", 1)[0]
    if site.startswith("www."):
        site = site[4:]
    if not site:
        return True
    domain = str(domain or "").lower()
    if site.startswith("."):
        return domain.endswith(site) or domain == site[1:]
    if "." not in site:  # a bare TLD such as ``edu``
        return domain == site or domain.endswith("." + site)
    return domain == site or domain.endswith("." + site)


BINARY_EXTENSIONS = frozenset({
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf",
    "epub", "mobi", "azw3", "djvu", "zip", "gz", "tgz", "tar", "rar", "7z", "bz2",
    "xz", "exe", "msi", "dmg", "apk", "iso", "png", "jpg", "jpeg", "gif", "bmp",
    "svg", "webp", "ico", "tif", "tiff", "mp3", "mp4", "avi", "mov", "wav", "flac",
    "ogg", "mkv", "webm",
})

_BINARY_CONTENT_TYPES = (
    "application/pdf", "application/octet-stream", "application/zip", "application/gzip",
    "application/x-", "application/msword", "application/vnd.ms-", "application/epub",
    "application/vnd.openxmlformats-officedocument", "application/vnd.oasis.opendocument",
)


def url_extension(url) -> str:
    """Best-effort file extension of a URL, ignoring the query string."""
    tail = str(url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
    last = tail.rsplit("/", 1)[-1]
    return last.rsplit(".", 1)[-1].lower() if "." in last else ""


def is_binary_url(url) -> bool:
    return url_extension(url) in BINARY_EXTENSIONS


def is_binary_content_type(content_type) -> bool:
    ct = str(content_type or "").lower().split(";", 1)[0].strip()
    if not ct:
        return False
    if ct.startswith(("image/", "audio/", "video/", "font/")):
        return True
    return any(ct.startswith(prefix) for prefix in _BINARY_CONTENT_TYPES)


_YAHOO_RU_RE = re.compile(r"/RU=([^/]+)/R[KS]=", re.IGNORECASE)


def unwrap_redirect(url) -> str:
    """Return the real destination behind a search engine's redirector.

    DuckDuckGo hands back ``//duckduckgo.com/l/?uddg=<encoded>``, Google
    ``/url?q=<encoded>``, Yahoo ``r.search.yahoo.com/.../RU=<encoded>/RK=...``
    and Bing ``bing.com/ck/a?...&u=a1<base64url>``. Left wrapped they are
    useless as result URLs and all collapse onto one domain."""
    raw = html.unescape(str(url or "")).strip()
    if not raw:
        return raw
    low = raw.lower()
    try:
        parsed = urllib.parse.urlsplit("https:" + raw if raw.startswith("//") else raw)
        params = urllib.parse.parse_qs(parsed.query or "")
        if "bing.com/ck/a" in low:
            token = (params.get("u") or [""])[0]
            if token[:2].lower() in ("a1", "a2"):
                token = token[2:]
            if token:
                try:
                    decoded = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("utf-8", "replace")
                    if decoded.startswith("http"):
                        return decoded
                except Exception:
                    pass
        match = _YAHOO_RU_RE.search(raw)
        if match:
            candidate = urllib.parse.unquote(match.group(1))
            if candidate.startswith("http"):
                return candidate
        for key in ("uddg", "q", "u", "url"):
            candidate = (params.get(key) or [""])[0]
            if candidate.startswith("http"):
                return urllib.parse.unquote(candidate)
        if raw.startswith("//"):
            return "https:" + raw
    except Exception:
        pass
    return raw


DEFAULT_SKIP_DOMAINS = frozenset({
    "google.com", "google.co", "accounts.google", "support.google",
    "maps.google", "policies.google",
})

#: Never a search result, whichever engine's page it was found on.
GLOBAL_JUNK = ("google.com/", "gstatic.com", "googleusercontent.com", "w3.org/", "schema.org",
               "javascript:", "mailto:", "doubleclick.net", "googlesyndication")


def dedup_links(links, skip_domains=None, allow_same_domain: bool = False) -> list:
    """Filter junk / skip-domain links and de-duplicate ``{url, title}`` dicts.

    ``allow_same_domain`` False keeps at most one result per host (legacy);
    True de-duplicates by full URL, which a ``site:`` dork needs."""
    if skip_domains is None:
        skip_domains = set(DEFAULT_SKIP_DOMAINS)
    out: list = []
    seen: set = set()
    for item in links or ():
        href = str((item or {}).get("url") or "").strip()
        if not href.startswith("http"):
            continue
        domain = urllib.parse.urlsplit(href).netloc.lower()
        if not domain or any(skip in domain for skip in skip_domains):
            continue
        key = href if allow_same_domain else domain
        if key in seen:
            continue
        seen.add(key)
        entry = {"url": href, "title": str(item.get("title") or "").strip()}
        if item.get("snippet"):
            entry["snippet"] = str(item.get("snippet")).strip()
        if item.get("source"):
            entry["source"] = item.get("source")
        out.append(entry)
    return out


_ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_HREF_ATTR_RE = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)


def harvest_anchor_links(body, skip=(), limit: int = 400) -> list:
    """Every outbound ``<a href>`` of a results page as ``{url, title}``.

    Deliberately regex-based rather than DOM-based: a results page's CLASS
    NAMES change (that is what silently broke the old browser path), but an
    ``href`` to an off-site URL is the one thing a search result cannot stop
    being. Relevance is judged afterwards, by :func:`assess_hits`."""
    out: list = []
    skip = tuple(str(s).lower() for s in (skip or ()))
    for attrs, inner in _ANCHOR_RE.findall(str(body or "")):
        match = _HREF_ATTR_RE.search(attrs)
        if not match:
            continue
        target = unwrap_redirect(match.group(1) or match.group(2) or "")
        if not target.startswith("http"):
            continue
        low = target.lower()
        if any(s and s in low for s in skip) or any(j in low for j in GLOBAL_JUNK):
            continue
        out.append({"url": target, "title": clean_text(inner)[:200]})
        if len(out) >= limit:
            break
    return out


# =============================================================================
# 5. RELEVANCE: a result set that never mentions the query is not an answer
# =============================================================================

_STOPWORDS = frozenset("""
a an and are as at be but by for from how i if in into is it its of on or so than
that the their then there these this those to was were what when where which who
whom why will with you your yours we our us my me he she they them his her
de del el la las los en es un una unos unas y o que se por para con sin sobre
""".split())

#: Words that turn up on unrelated pages too often to prove a page is on topic.
_FILLER = frozenset("""
result results best top free online new latest list guide guides tutorial tutorials
official download downloads page pages home info information news review reviews
vs versus comparison compare about using use used make made does do did can could
get got find search query site sites web www com org net http https html htm
last first next good great year years time times day days way ways thing things
people world work works like want need help also just many much more most some
any all other another each every same different own part place case point fact
number numbers example examples one two three full complete version
""".split())

_OPERATOR_RE = re.compile(
    r"(^|[\s(])(-?)(site|filetype|ext|intitle|allintitle|inurl|allinurl|intext|allintext|"
    r"inanchor|allinanchor|related|cache|define|source|before|after|link|location|loc|"
    r"daterange|numrange)\s*:\s*(\"[^\"]*\"|[^\s()]+)",
    re.IGNORECASE,
)
_PHRASE_RE = re.compile(r"(^|[\s(])(-?)\"([^\"]+)\"")
_AROUND_RE = re.compile(r"\bAROUND\(\s*\d+\s*\)", re.IGNORECASE)
_CONTENT_OPERATORS = frozenset({"intitle", "allintitle", "inurl", "allinurl", "intext",
                                "allintext", "inanchor", "allinanchor", "define"})


class QueryTerms:
    """What a result must mention to count as an answer to ``raw``."""

    __slots__ = ("raw", "sites", "not_sites", "filetypes", "phrases", "words",
                 "search_text", "plain_text")

    def __init__(self, raw=""):
        self.raw = raw
        self.sites: list = []
        self.not_sites: list = []
        self.filetypes: list = []
        self.phrases: list = []
        self.words: list = []
        self.search_text = ""
        self.plain_text = ""

    @property
    def strong(self) -> list:
        return list(self.phrases) + [w for w in self.words if w not in self.phrases]


def _is_anchor_word(word: str) -> bool:
    return (len(word) >= 3 and not word.isdigit()
            and word not in _STOPWORDS and word not in _FILLER)


def parse_query_terms(query) -> QueryTerms:
    """Split a (possibly dorked) query into sites, file types and anchor terms."""
    terms = QueryTerms(str(query or ""))
    text = terms.raw
    content_values: list = []
    kept_phrases: list = []

    def _operator(match):
        negated, operator, value = match.group(2), match.group(3).lower(), match.group(4).strip().strip('"')
        if operator == "site" and value:
            (terms.not_sites if negated else terms.sites).append(value.lower())
        elif operator in ("filetype", "ext") and value and not negated:
            terms.filetypes.append(value.lower().lstrip("."))
        elif operator in _CONTENT_OPERATORS and value and not negated:
            content_values.append(value)
        return match.group(1) + " "

    def _phrase(match):
        if not match.group(2):
            phrase = normalize(match.group(3))
            if phrase:
                kept_phrases.append(match.group(3).strip())
                if " " in phrase:
                    terms.phrases.append(phrase)
                elif _is_anchor_word(phrase) and phrase not in terms.words:
                    terms.words.append(phrase)
        return match.group(1) + " "

    text = _OPERATOR_RE.sub(_operator, text)
    text = _PHRASE_RE.sub(_phrase, text)
    text = _AROUND_RE.sub(" ", text)

    raw_words: list = []
    for value in content_values:
        folded = normalize(value)
        if " " in folded:
            terms.phrases.append(folded)
            kept_phrases.append(value)
        else:
            text += " " + value
    for token in re.split(r"[\s()|]+", text):
        token = token.strip().strip('"')
        if not token or token.startswith("-") or token.upper() in ("OR", "AND") or ".." in token:
            continue
        raw_words.append(token)
        for word in normalize(token).split():
            if _is_anchor_word(word) and word not in terms.words:
                terms.words.append(word)
    terms.search_text = " ".join(['"%s"' % p for p in kept_phrases] + raw_words).strip()
    terms.plain_text = " ".join(kept_phrases + raw_words).strip()
    return terms


def hit_is_relevant(hit, terms: QueryTerms) -> bool:
    """Does this hit answer the query?

    A hit that satisfies the query's ``site:`` or ``filetype:`` operator is
    EVIDENCE the engine honoured the query: a poisoned page never lands on the
    requested site (Bing answered a ``site:gutenberg.org`` dork with Wikipedia),
    while a correct answer often does not repeat the words in its link text
    (Brave's ``pg15.epub`` IS Moby Dick, titled only "Project Gutenberg")."""
    url = str((hit or {}).get("url") or "")
    domain = domain_of(url)
    if terms.not_sites and any(site_matches(domain, s) for s in terms.not_sites):
        return False
    if terms.sites:
        return any(site_matches(domain, s) for s in terms.sites)
    if terms.filetypes and url_extension(url) in terms.filetypes:
        return True
    anchors = terms.strong
    if not anchors:
        return True
    hay = normalize(urllib.parse.unquote(url) + " " + str(hit.get("title") or "")
                    + " " + str(hit.get("snippet") or ""))
    padded = " %s " % hay
    squashed = hay.replace(" ", "")
    for anchor in anchors:
        if " " in anchor:
            if (" %s " % anchor) in padded or anchor.replace(" ", "") in squashed:
                return True
        elif len(anchor) >= 5:
            if anchor in hay:
                return True
        elif (" %s " % anchor) in padded:
            return True
    return False


def assess_hits(hits, terms: QueryTerms, min_ratio: float = 0.3):
    """Judge a result SET. Returns ``(verdict, ordered_hits, relevant_count)``.

    ``ok``       - enough of the set is about the query; relevant hits first
                   (and, under a ``site:`` constraint, off-site hits dropped,
                   because an engine that ignored the operator served them);
    ``poisoned`` - the set does not mention the query at all: a bot-poisoned
                   page (Bing's Poki games) or an ignored ``site:`` operator;
    ``empty``    - no hits."""
    hits = list(hits or ())
    if not hits:
        return "empty", [], 0
    if not terms.strong and not terms.sites and not terms.not_sites:
        return "ok", hits, len(hits)
    relevant = [h for h in hits if hit_is_relevant(h, terms)]
    if relevant and (len(relevant) >= 3 or len(relevant) / float(len(hits)) >= min_ratio):
        if terms.sites or terms.not_sites:
            return "ok", relevant, len(relevant)
        rest = [h for h in hits if not any(h is r for r in relevant)]
        return "ok", relevant + rest, len(relevant)
    return "poisoned", [], len(relevant)


# =============================================================================
# 6. WHAT A REFUSAL LOOKS LIKE
# =============================================================================

#: (marker, reason). Checked against the final URL and the page, but ONLY when
#: a page produced no relevant results: Brave's normal page mentions "captcha".
BLOCK_MARKERS = (
    ("/sorry/", "captcha"), ("unusual traffic", "captcha"), ("captcha-form", "captcha"),
    ("g-recaptcha", "captcha"), ("hcaptcha", "captcha"), ("captcha", "captcha"),
    ("are you a robot", "captcha"), ("not a robot", "captcha"),
    ("verify you are human", "captcha"), ("bots use duckduckgo", "anomaly"),
    ("anomaly-modal", "anomaly"), ("anomaly.js", "anomaly"),
    ("just a moment", "challenge"), ("cf-chl", "challenge"),
    ("challenge-platform", "challenge"), ("attention required", "challenge"),
    ("ddos-guard", "challenge"), ("automated queries", "rate-limited"),
    ("too many requests", "rate-limited"), ("ecosia firewall", "firewall"),
    ("access denied", "forbidden"), ("enablejs", "javascript wall"),
    ("httpservice/retry", "javascript wall"),
    ("your browser isn't supported", "browser refused"),
    ("your browser is not supported", "browser refused"),
    ("startpage.com/errors", "error page"), ("has encountered an error", "error page"),
    ("/_bv/", "bot verification"),
)

NO_RESULT_MARKERS = (
    "did not match any documents", "your search did not match any",
    "there are no results for", "no results found for", "we did not find results for",
    "no pages found", "not many great matches", "no results for",
)

REFUSAL_VERDICTS = frozenset({"blocked", "poisoned"})


def classify_response(*, status_code: int = 0, final_url: str = "", body: str = "",
                      hits_verdict: str = "empty", error: str = "", timed_out: bool = False):
    """``(verdict, detail)`` for one route's answer.

    verdicts: ``ok``, ``blocked``, ``poisoned``, ``no_matches`` (the engine
    answered: nothing found), ``empty`` (no links, no explanation), ``timeout``
    and ``error``."""
    if hits_verdict == "ok":
        return "ok", ""
    if timed_out:
        return "timeout", error or "timed out"
    low_url = str(final_url or "").lower()
    low = str(body or "")[:700_000].lower()
    for marker, reason in BLOCK_MARKERS:
        if marker in low_url or marker in low:
            return "blocked", reason
    if status_code in (401, 403, 429, 451, 503):
        return "blocked", "HTTP %s" % status_code
    if status_code == 202:
        return "blocked", "HTTP 202 challenge"
    if status_code >= 400 or (status_code == 0 and error):
        return "error", error or ("HTTP %s" % status_code)
    if hits_verdict == "poisoned":
        return "poisoned", "results did not match the query (bot-poisoned page or an ignored operator)"
    for marker in NO_RESULT_MARKERS:
        if marker in low:
            return "no_matches", "the engine answered: no results"
    return "empty", "no result links on the page"


# =============================================================================
# 7. THE HEALTH LEDGER: remember who refused, stop provoking them
# =============================================================================

#: Cooldown ladders in seconds, indexed by consecutive failures of one route.
COOLDOWNS = {
    "blocked": (180, 600, 1800),
    "poisoned": (180, 600, 1800),
    "timeout": (60, 180, 600),
    "error": (60, 180, 600),
    "empty": (30, 90, 300),
}

HEALTH_FILENAME = "googler_engine_health.json"


def default_health_path() -> str:
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip() or tempfile.gettempdir()
    return os.path.join(base, HEALTH_FILENAME)


class EngineHealth:
    """Per-route memory shared by every Googler run on this machine.

    Keys are ``"<tier>:<engine>"`` (``http:bing-http``, ``browser:google``):
    the same engine can refuse a script and welcome a real browser. The file
    is an advisory cache: unreadable means "unknown", never an error."""

    def __init__(self, path: str | None = None, clock=time.time):
        self.path = path if path is not None else default_health_path()
        self._clock = clock
        self.data = self._load()
        self._changed: dict = {}

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8-sig") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                return {str(k): v for k, v in loaded.items() if isinstance(v, dict)}
        except Exception:
            pass
        return {}

    def cooling_left(self, key: str) -> float:
        entry = self.data.get(key) or {}
        try:
            return max(0.0, float(entry.get("until", 0) or 0) - self._clock())
        except (TypeError, ValueError):
            return 0.0

    def record(self, key: str, verdict: str, detail: str = "") -> None:
        now = self._clock()
        entry = dict(self.data.get(key) or {})
        entry["last"] = verdict
        entry["last_at"] = now
        entry["detail"] = str(detail or "")[:160]
        if verdict in ("ok", "no_matches"):
            entry["streak"] = 0
            entry["until"] = 0
            if verdict == "ok":
                entry["ok_at"] = now
        elif verdict in COOLDOWNS:
            streak = int(entry.get("streak", 0) or 0) + 1
            ladder = COOLDOWNS[verdict]
            entry["streak"] = streak
            entry["until"] = now + ladder[min(streak, len(ladder)) - 1]
        self.data[key] = entry
        self._changed[key] = entry

    def order(self, keys) -> list:
        """Recently-successful routes first, unknown routes next, cooling last."""
        now = self._clock()

        def rank(key):
            entry = self.data.get(key) or {}
            cooling = float(entry.get("until", 0) or 0) > now
            ok_at = float(entry.get("ok_at", 0) or 0)
            fresh_ok = bool(ok_at) and (now - ok_at) < 6 * 3600
            return (1 if cooling else 0, 0 if fresh_ok else 1, -ok_at if fresh_ok else 0.0)

        return sorted(list(keys), key=rank)

    def plan(self, keys):
        """``(runnable, skipped)``. When EVERY route is cooling, the one whose
        cooldown ends first is still probed, so a lifted block is noticed."""
        ordered = self.order(keys)
        runnable = [k for k in ordered if self.cooling_left(k) <= 0]
        if not runnable and ordered:
            runnable = [min(ordered, key=self.cooling_left)]
        skipped = [k for k in ordered if k not in runnable]
        return runnable, skipped

    def save(self) -> None:
        if not self._changed:
            return
        try:
            merged = self._load()
            merged.update(self._changed)
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            tmp_path = "%s.%d.tmp" % (self.path, os.getpid())
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(merged, handle, indent=1, sort_keys=True)
            os.replace(tmp_path, self.path)
            self._changed = {}
        except Exception:
            pass

    def cooling_summary(self, keys=None) -> list:
        out = []
        for key in (keys if keys is not None else sorted(self.data)):
            left = self.cooling_left(key)
            if left > 0:
                entry = self.data.get(key) or {}
                out.append("%s (%s, retry in %dm%02ds)" % (
                    key, entry.get("last", "?"), int(left) // 60, int(left) % 60))
        return out


# =============================================================================
# 8. TIER 0: plain-HTTP engines, hedged
# =============================================================================

HTTP_ENGINES = (
    {"name": "duckduckgo-html", "url": "https://html.duckduckgo.com/html/?q={q}",
     "skip": ("duckduckgo.com",)},
    {"name": "bing-http", "url": "https://www.bing.com/search?q={q}&count=30&setlang=en",
     "skip": ("bing.com", "microsoft.com", "msn.com", "go.microsoft")},
    {"name": "duckduckgo-lite", "url": "https://lite.duckduckgo.com/lite/?q={q}",
     "skip": ("duckduckgo.com",)},
    {"name": "mojeek-http", "url": "https://www.mojeek.com/search?q={q}",
     "skip": ("mojeek.com", "mastodon.social/@mojeek", "buttondown.email/mojeek")},
    {"name": "brave-http", "url": "https://search.brave.com/search?q={q}&source=web",
     "skip": ("brave.com", "torproject.org")},
    {"name": "yahoo-http", "url": "https://search.yahoo.com/search?p={q}&n=30",
     "skip": ("yahoo.com", "yahoo.net", "yimg.com", "bing.com")},
)


def attempt_record(engine: str, tier: str, verdict: str, detail: str = "", ms: int = 0, **extra) -> dict:
    record = {"engine": engine, "tier": tier, "verdict": verdict, "detail": str(detail or "")[:200], "ms": int(ms)}
    record.update(extra)
    return record


def http_search_one(engine: dict, query: str, number_of_results: int, *, terms: QueryTerms,
                    allow_same_domain: bool = False, deadline: Deadline | None = None,
                    timeout: float = 8.0) -> dict:
    started = time.monotonic()
    url = engine["url"].format(q=urllib.parse.quote_plus(query))
    response = bounded_fetch(url, headers=BROWSER_HEADERS, timeout=timeout, deadline=deadline)
    raw_links = harvest_anchor_links(response["body"], skip=engine.get("skip", ()))
    hits = dedup_links(raw_links, skip_domains=set(DEFAULT_SKIP_DOMAINS), allow_same_domain=allow_same_domain)
    hits_verdict, ordered, relevant = assess_hits(hits, terms)
    verdict, detail = classify_response(
        status_code=response["status_code"], final_url=response["final_url"], body=response["body"],
        hits_verdict=hits_verdict, error=response["error"], timed_out=response["timed_out"],
    )
    return attempt_record(
        engine["name"], "http", verdict, detail, int((time.monotonic() - started) * 1000),
        status_code=response["status_code"], seen=len(hits), relevant=relevant,
        hits=ordered[:number_of_results] if verdict == "ok" else [],
    )


def http_tier_search(query: str, number_of_results: int, *, terms: QueryTerms, deadline: Deadline,
                     health: EngineHealth, allow_same_domain: bool = False, engines=None,
                     stagger: float = 0.7, max_parallel: int = 3):
    """Hedged plain-HTTP search. Returns ``(hits, winner_attempt, attempts)``."""
    engines = list(engines or HTTP_ENGINES)
    by_key = {"http:%s" % e["name"]: e for e in engines}
    runnable, skipped = health.plan(list(by_key))
    attempts = [attempt_record(by_key[k]["name"], "http", "skipped",
                               "cooling down %ds after: %s" % (health.cooling_left(k),
                                                               (health.data.get(k) or {}).get("last", "?")))
                for k in skipped]
    jobs = []
    for key in runnable:
        engine = by_key[key]
        jobs.append((key, lambda e=engine: http_search_one(
            e, query, number_of_results, terms=terms, allow_same_domain=allow_same_domain,
            deadline=deadline)))
    launched: list = []
    winner, finished = run_hedged(jobs, deadline=deadline, stagger=stagger, max_parallel=max_parallel,
                                  accept=lambda r: r.get("verdict") == "ok", started=launched)
    done = set()
    for key, result in finished:
        done.add(key)
        result.setdefault("engine", by_key[key]["name"])
        result.setdefault("tier", "http")
        health.record(key, result.get("verdict", "error"), result.get("detail", ""))
        attempts.append({k: v for k, v in result.items() if k != "hits"})
    for key in runnable:
        if key in done:
            continue
        if key not in launched:
            attempts.append(attempt_record(by_key[key]["name"], "http", "not_tried",
                                           "another route answered first" if winner
                                           else "the search budget ran out before its turn"))
        elif winner:
            attempts.append(attempt_record(by_key[key]["name"], "http", "abandoned",
                                           "another route answered first"))
        else:
            attempts.append(attempt_record(by_key[key]["name"], "http", "timeout",
                                           "no answer within the search budget"))
            health.record(key, "timeout", "no answer within the search budget")
    if winner:
        return list(winner[1].get("hits") or []), winner[1], attempts
    return [], None, attempts


# =============================================================================
# 9. TIER 2: open knowledge sources that do not block scripts
# =============================================================================

def _json_get(url: str, deadline: Deadline, timeout: float = 6.0, accept: str = "application/json"):
    response = bounded_fetch(url, headers={"User-Agent": API_UA, "Accept": accept,
                                           "Accept-Encoding": "identity"},
                             timeout=timeout, deadline=deadline, max_bytes=2_500_000)
    if response["error"] or response["status_code"] >= 400:
        return None, response
    try:
        return json.loads(response["body"]), response
    except ValueError:
        return None, response


def _source_wikipedia(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "format": "json", "utf8": 1,
        "srlimit": n, "srprop": "snippet", "srsearch": terms.search_text})
    data, response = _json_get(url, deadline)
    hits = []
    for item in ((data or {}).get("query") or {}).get("search") or []:
        title = str(item.get("title") or "")
        if title:
            hits.append({"url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                         "title": title, "snippet": clean_text(item.get("snippet") or ""),
                         "source": "wikipedia"})
    return hits, response


def _source_hackernews(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": terms.plain_text, "hitsPerPage": n, "tags": "story"})
    data, response = _json_get(url, deadline)
    hits = []
    for item in (data or {}).get("hits") or []:
        title = str(item.get("title") or item.get("story_title") or "")
        target = item.get("url") or ("https://news.ycombinator.com/item?id=%s" % item.get("objectID", ""))
        if title and str(target).startswith("http"):
            hits.append({"url": target, "title": title,
                         "snippet": "Hacker News: %s points, %s comments" % (
                             item.get("points", 0), item.get("num_comments", 0)),
                         "source": "hackernews"})
    return hits, response


def _source_arxiv(terms: QueryTerms, n: int, deadline: Deadline):
    parts = ['all:"%s"' % p for p in terms.phrases[:2]] + ["all:%s" % w for w in terms.words[:3]]
    if not parts:
        return [], _empty_fetch("arxiv", "no searchable terms")
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": " AND ".join(parts), "max_results": n})
    response = bounded_fetch(url, headers={"User-Agent": API_UA, "Accept": "application/atom+xml",
                                           "Accept-Encoding": "identity"},
                             timeout=7.0, deadline=deadline, max_bytes=2_500_000)
    hits = []
    if response["body"] and not response["error"]:
        try:
            namespace = {"a": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(response["body"])
            for entry in root.findall("a:entry", namespace):
                link = (entry.findtext("a:id", default="", namespaces=namespace) or "").strip()
                title = _WS_RE.sub(" ", entry.findtext("a:title", default="", namespaces=namespace) or "").strip()
                summary = _WS_RE.sub(" ", entry.findtext("a:summary", default="", namespaces=namespace) or "").strip()
                if link.startswith("http") and title:
                    hits.append({"url": link.replace("http://", "https://", 1), "title": title,
                                 "snippet": summary[:300], "source": "arxiv"})
        except ET.ParseError:
            pass
    return hits, response


def _source_openalex(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": terms.plain_text, "per-page": n})
    data, response = _json_get(url, deadline)
    hits = []
    for item in (data or {}).get("results") or []:
        title = str(item.get("display_name") or item.get("title") or "")
        target = item.get("doi") or item.get("id") or ""
        if title and str(target).startswith("http"):
            hits.append({"url": target, "title": title,
                         "snippet": "Scholarly work, %s" % (item.get("publication_year") or "year unknown"),
                         "source": "openalex"})
    return hits, response


def _source_github(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": terms.plain_text, "per_page": n})
    data, response = _json_get(url, deadline, accept="application/vnd.github+json")
    hits = []
    for item in (data or {}).get("items") or []:
        target = item.get("html_url") or ""
        if str(target).startswith("http"):
            hits.append({"url": target, "title": str(item.get("full_name") or ""),
                         "snippet": str(item.get("description") or "")[:300], "source": "github"})
    return hits, response


def _source_archive(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
        [("q", terms.plain_text), ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "description"),
         ("rows", n), ("output", "json")])
    data, response = _json_get(url, deadline)
    hits = []
    for item in ((data or {}).get("response") or {}).get("docs") or []:
        identifier = item.get("identifier")
        if identifier:
            description = item.get("description") or ""
            if isinstance(description, list):
                description = " ".join(str(d) for d in description)
            hits.append({"url": "https://archive.org/details/%s" % identifier,
                         "title": str(item.get("title") or identifier),
                         "snippet": clean_text(description)[:300], "source": "internet-archive"})
    return hits, response


def _source_gutenberg(terms: QueryTerms, n: int, deadline: Deadline):
    url = "https://gutendex.com/books?" + urllib.parse.urlencode({"search": terms.plain_text})
    data, response = _json_get(url, deadline, timeout=6.0)
    hits = []
    want_file = any(ft in ("epub", "mobi", "azw3", "pdf") for ft in terms.filetypes)
    for item in ((data or {}).get("results") or [])[:n]:
        formats = item.get("formats") or {}
        epub = formats.get("application/epub+zip") or ""
        page = "https://www.gutenberg.org/ebooks/%s" % item.get("id", "")
        authors = ", ".join(str(a.get("name", "")) for a in item.get("authors") or [] if a.get("name"))
        hits.append({"url": epub if (want_file and epub) else page,
                     "title": "%s%s" % (item.get("title", ""), (" - " + authors) if authors else ""),
                     "snippet": ("EPUB: %s" % epub) if epub else "Project Gutenberg ebook",
                     "source": "gutenberg"})
    return hits, response


#: name -> (function, the domains its results live on)
OPEN_SOURCES = {
    "wikipedia": (_source_wikipedia, ("wikipedia.org",)),
    "arxiv": (_source_arxiv, ("arxiv.org",)),
    "hackernews": (_source_hackernews, ("news.ycombinator.com",)),
    "github": (_source_github, ("github.com",)),
    "openalex": (_source_openalex, ("openalex.org", "doi.org")),
    "internet-archive": (_source_archive, ("archive.org",)),
    "gutenberg": (_source_gutenberg, ("gutenberg.org",)),
}

DEFAULT_OPEN_SOURCES = ("wikipedia", "arxiv", "hackernews", "github", "openalex", "internet-archive")
_BOOK_HINTS = frozenset({"epub", "mobi", "azw3", "ebook", "book", "novel", "gutenberg"})


def select_open_sources(terms: QueryTerms) -> list:
    """Which open sources can honour this query (and its ``site:`` filter)."""
    if terms.sites:
        # both directions: site:wikipedia.org AND site:en.wikipedia.org -> wikipedia
        return [name for name, (_fn, domains) in OPEN_SOURCES.items()
                if any(site_matches(domain, site) or site_matches(site.split("/", 1)[0], domain)
                       for domain in domains for site in terms.sites)]
    names = list(DEFAULT_OPEN_SOURCES)
    if _BOOK_HINTS.intersection(set(terms.filetypes) | set(terms.words)):
        names.insert(0, "gutenberg")
    return names


def open_sources_search(terms: QueryTerms, number_of_results: int, *, deadline: Deadline,
                        budget_seconds: float = 9.0):
    """Query every suitable open source in parallel; merge what arrives in time.

    Returns ``(hits, attempts)``. Results are interleaved source by source,
    de-duplicated, and still relevance-checked: an API search that drifts off
    topic is filtered exactly like a web engine."""
    names = select_open_sources(terms)
    if not names or not terms.plain_text.strip():
        return [], [attempt_record("open-sources", "open", "skipped",
                                   "no open source can serve this query")]
    sub = deadline.child(budget_seconds)
    per_source = max(3, min(8, number_of_results))

    def _job(fn):
        started = time.monotonic()
        found, response = fn(terms, per_source, sub)
        verdict = "ok" if found else ("timeout" if response.get("timed_out") else
                                      ("error" if response.get("error") else "empty"))
        return attempt_record("", "open", verdict, response.get("error", ""),
                              int((time.monotonic() - started) * 1000), hits=found)

    jobs = [(name, (lambda fn=OPEN_SOURCES[name][0]: _job(fn))) for name in names]
    _winner, finished = run_hedged(jobs, deadline=sub, stagger=0.0, max_parallel=len(jobs), wait_all=True)
    results_by_name = {name: result for name, result in finished}
    attempts = []
    buckets = []
    for name in names:
        result = results_by_name.get(name)
        if result is None:
            attempts.append(attempt_record(name, "open", "timeout", "no answer within the budget"))
            continue
        result = dict(result)
        result["engine"] = name
        found = [h for h in result.pop("hits", []) or [] if hit_is_relevant(h, terms)]
        attempts.append(result)
        if found:
            buckets.append(found)
    merged, seen = [], set()
    while buckets and len(merged) < number_of_results:
        for bucket in list(buckets):
            if not bucket:
                buckets.remove(bucket)
                continue
            hit = bucket.pop(0)
            if hit["url"] not in seen:
                seen.add(hit["url"])
                merged.append(hit)
            if len(merged) >= number_of_results:
                break
    return merged, attempts


# =============================================================================
# 10. PAGE TEXT, fetched over plain HTTP under the same deadline
# =============================================================================

class _HTMLToText(HTMLParser):
    """Visible text of a page, for the model.

    Skipped regions are a STACK of open tags, never a bare counter, and <head>
    ends at the first element that cannot live inside a head. HTML5 lets a page
    leave </head> out (minified pages do), and a counter waiting for it drops
    every word of the page - the class of bug that cost the Crawler ALL of its
    text on 2026-09-28 (void <meta>/<link> opening regions that never closed).
    A self-closing <x/> never opens a region.
    """
    _SKIP = frozenset({"script", "style", "noscript", "svg", "template", "iframe", "canvas", "object", "head"})
    #: The only elements allowed inside <head>; any other one means the body began.
    _HEAD_TAGS = frozenset({"title", "meta", "link", "style", "script", "noscript", "base", "template"})
    _BLOCK = frozenset({"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
                        "header", "footer", "nav", "aside", "main", "form", "pre", "blockquote",
                        "dd", "dt", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list = []
        self.title: list = []
        self._open: list = []
        self._in_title = False

    def _leave_head(self, tag):
        if "head" in self._open and tag not in self._HEAD_TAGS:
            self._open = [name for name in self._open if name != "head"]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._in_title and tag != "title":
            self._in_title = False          # a <title> never contains elements
        self._leave_head(tag)
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP:
            self._open.append(tag)
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        self._leave_head(tag)
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in self._open:
            while self._open and self._open.pop() != tag:
                pass
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        if not self._open:
            self.parts.append(data)


_FALLBACK_OPEN_RE = re.compile(r"<(script|style|noscript|template|svg)\b", re.IGNORECASE)
_FALLBACK_BREAK_RE = re.compile(
    r"<(?:br|/p|/div|/li|/tr|/h[1-6]|/section|/article|/blockquote|/pre|/dd|/dt)\b[^>]*>",
    re.IGNORECASE)
_FALLBACK_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FALLBACK_TAG_RE = re.compile(r"<[^>]*>")
#: A parse that keeps less than this share of the plain text has lost the page...
FALLBACK_MIN_SHARE = 0.25
#: ...once the page holds at least this much plain text at all.
FALLBACK_MIN_CHARS = 200


def plain_text_fallback(markup: str) -> str:
    """Visible text by plain tag-stripping: no parser state that can get stuck.

    Script/style/noscript/template/svg blocks are dropped only when they are
    CLOSED. An unclosed one keeps everything after it, because a region that
    never closes is exactly the failure this fallback exists to survive.
    """
    markup = _FALLBACK_COMMENT_RE.sub(" ", str(markup or ""))
    lower = markup.lower()
    pieces, pos, never_closed = [], 0, set()
    for match in _FALLBACK_OPEN_RE.finditer(markup):
        tag = match.group(1).lower()
        if match.start() < pos or tag in never_closed:
            continue
        gt = lower.find(">", match.end())
        if gt > 0 and markup[gt - 1] == "/":
            continue                   # <svg/> opens nothing
        end = lower.find("</" + tag, match.end())
        if end < 0:
            never_closed.add(tag)      # every later one is unclosed too: never rescan
            continue
        close = lower.find(">", end)
        pieces.append(markup[pos:match.start()])
        pos = len(markup) if close < 0 else close + 1
    pieces.append(markup[pos:])
    text = _FALLBACK_BREAK_RE.sub("\n", " ".join(pieces))
    text = html.unescape(_FALLBACK_TAG_RE.sub(" ", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(markup: str, report: list = None):
    """``(title, text)`` of an HTML document, blank lines collapsed.

    Two layers: the parser, then ``plain_text_fallback`` as a safety net. If the
    parser failed, or kept less than a quarter of the plain text, a parser state
    got stuck and the plain text is used instead; ``report`` (a list) receives a
    note saying so, so a page can never silently lose its text.
    """
    parser = _HTMLToText()
    failed = ""
    try:
        parser.feed(str(markup or ""))
        parser.close()
    except Exception as exc:
        failed = str(exc) or type(exc).__name__
    lines = [_WS_RE.sub(" ", line).strip() for line in "".join(parser.parts).splitlines()]
    text_lines, blank = [], 0
    for line in lines:
        if line:
            blank = 0
            text_lines.append(line)
        else:
            blank += 1
            if blank == 1 and text_lines:
                text_lines.append("")
    title = _WS_RE.sub(" ", "".join(parser.title)).strip()
    text = "\n".join(text_lines).strip()
    fallback = plain_text_fallback(markup)
    lost = len(fallback) >= FALLBACK_MIN_CHARS and len(text) < len(fallback) * FALLBACK_MIN_SHARE
    if (failed or lost) and len(fallback) > len(text):
        if report is not None:
            report.append("plain-text fallback: the HTML parser "
                          + ("failed (%s)" % failed if failed else
                             "kept only %d of %d characters" % (len(text), len(fallback))))
        text = fallback
    return title, text


#: A page this short is probably a JavaScript shell or a challenge: the
#: browser may render it better when there is time left.
THIN_PAGE_CHARS = 400


def fetch_page_text(url: str, *, deadline: Deadline, timeout: float = 10.0, mode: str = "text",
                    max_chars: int = 50_000) -> dict:
    """One result page over plain HTTP. A binary hit is a FOUND FILE, not an error."""
    if is_binary_url(url):
        return {"url": url, "kind": "file", "filetype": url_extension(url),
                "note": "downloadable file located (not fetched as text)"}
    response = bounded_fetch(url, headers=BROWSER_HEADERS, timeout=timeout, deadline=deadline,
                             max_bytes=3_000_000)
    if is_binary_content_type(response["content_type"]):
        return {"url": url, "kind": "file", "status_code": response["status_code"],
                "content_type": response["content_type"], "filetype": url_extension(url),
                "note": "downloadable file located (not fetched as text)"}
    if response["error"] and not response["body"]:
        return {"url": url, "error": response["error"], "thin": True, "fetched_by": "http",
                "timed_out": bool(response["timed_out"])}
    body = response["body"]
    notes: list = []
    if mode == "raw":
        content = body[:500_000]
    elif "html" in response["content_type"].lower() or "<html" in body[:2000].lower():
        _title, content = html_to_text(body, report=notes)
    else:
        content = body
    content = content.strip()
    verdict, reason = classify_response(status_code=response["status_code"], final_url=response["final_url"],
                                        body=body if len(content) < 3000 else "", hits_verdict="empty")
    if verdict == "blocked" and len(content) < 3000:
        return {"url": url, "status_code": response["status_code"], "thin": True, "fetched_by": "http",
                "error": "the site answered with a bot challenge (%s)" % reason}
    if len(content) > max_chars:
        content = content[:max_chars] + "\n... [truncated]"
    result = {"url": url, "status_code": response["status_code"], "content": content,
              "content_length": len(content), "fetched_by": "http",
              "thin": len(content) < THIN_PAGE_CHARS}
    if notes:
        result["extraction_note"] = notes[0]   # the safety net had to step in
    return result


def fetch_pages(urls, *, deadline: Deadline, mode: str = "text", max_chars: int = 50_000,
                per_page_timeout: float = 10.0, max_parallel: int = 5) -> list:
    """Fetch several pages in parallel; whatever misses the deadline says so."""
    urls = list(urls or ())
    jobs = [(str(index), (lambda u=url: fetch_page_text(u, deadline=deadline, timeout=per_page_timeout,
                                                        mode=mode, max_chars=max_chars)))
            for index, url in enumerate(urls)]
    _winner, finished = run_hedged(jobs, deadline=deadline, stagger=0.0,
                                   max_parallel=max(1, max_parallel), wait_all=True)
    by_index = {int(name): result for name, result in finished}
    out = []
    for index, url in enumerate(urls):
        result = by_index.get(index)
        if result is None:
            result = {"url": url, "error": "not fetched: the search time budget ran out", "thin": True,
                      "timed_out": True}
        out.append(result)
    return out


# =============================================================================
# 11. SMALL SHARED HELPERS
# =============================================================================

def default_profile_dir() -> str:
    """Where Googler's own persistent Chrome profile lives (outside the install,
    so it survives updates, like Tlamatini's private runtimes)."""
    base = (os.environ.get("LOCALAPPDATA") or "").strip() or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Tlamatini", "googler", "chrome-profile")


def describe_refusals(attempts) -> list:
    """``["google (browser: captcha)", ...]`` for every route that refused."""
    out = []
    for attempt in attempts or ():
        if attempt.get("verdict") in REFUSAL_VERDICTS:
            out.append("%s (%s: %s)" % (attempt.get("engine"), attempt.get("tier"),
                                        attempt.get("detail") or attempt.get("verdict")))
    return out


def overall_status(attempts, found: bool, deadline: Deadline | None = None) -> str:
    """The one word that describes a search.

    ``ok`` results found; ``no_matches`` an engine answered "nothing found";
    ``blocked`` engines refused / poisoned / stayed silent; ``unreachable``
    every attempt was a network error (offline, DNS); ``timeout`` the budget
    ran out first; ``error`` nothing was attempted at all."""
    if found:
        return "ok"
    verdicts = [a.get("verdict") for a in attempts or () if a.get("tier") != "open"]
    all_verdicts = [a.get("verdict") for a in attempts or ()]
    if "no_matches" in all_verdicts:
        return "no_matches"
    if any(v in REFUSAL_VERDICTS or v == "skipped" for v in verdicts):
        return "blocked"
    tried = [v for v in all_verdicts if v not in ("skipped", "abandoned", "not_tried")]
    if tried and all(v == "error" for v in tried):
        return "unreachable"
    if deadline is not None and deadline.expired():
        return "timeout"
    if tried and all(v == "timeout" for v in tried):
        return "timeout"
    if any(v in ("empty", "error", "timeout") for v in tried):
        return "blocked"
    return "error"
