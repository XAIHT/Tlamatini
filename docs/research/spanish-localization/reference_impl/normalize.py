"""Language-neutral normalization for Tlamatini's deterministic scoring core.

REFERENCE IMPLEMENTATION -- not wired into Tlamatini. See DESIGN.md section 7.

This module is the whole Surface-F fix. It exists because
``capability_registry._TOKEN_RE = re.compile(r"[a-z0-9_]+")`` treats every
non-ASCII byte as a delimiter, so Spanish is shredded before any logic runs::

    'codigo'  -> ['codigo']      # accent-less spelling
    'codigo'  -> ['digo']        # WITH the accent, today
    'analisis'-> ['lisis']       # WITH the accent, today

and because phrase matching is unbounded substring containment, so the 4-char
alias ``ue`` (Unrealer) matches inside *prueba*, *que*, *puede*, *respuesta* --
scoring 24 and ranking FIRST on a Spanish e-mail request while the correct
``chat_agent_send_email`` scores 0.

THREE HARD CONTRACTS
--------------------
1. IDENTITY ON ASCII. ``fold_tokenize`` is byte-identical to the current
   tokenizer for pure-ASCII input, and ``phrase_hit`` only ever REMOVES
   accidental substring hits -- it never adds one. Pinned by a 200-prompt
   golden corpus (DESIGN.md section 12).
2. FAIL-OPEN. Any internal error falls back to today's expression. A scoring
   helper that raises would take down the planner.
3. NO ``agent.*`` IMPORTS. ``capability_registry`` imports this module
   DIRECTLY, never through the ``agent.i18n`` facade -- an ImportError-
   swallowing facade cannot rescue you when the facade is what failed to
   import. Pool agents vendor a copy of the tokenizer via portable_langkit.

Stdlib only: re, unicodedata, functools.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, Mapping, Sequence, Set

__all__ = [
    "ASCII_IDENTITY_GUARANTEED",
    "fold_text",
    "fold_tokenize",
    "phrase_hit",
    "expand_request_for_scoring",
    "legacy_tokenize",
]

ASCII_IDENTITY_GUARANTEED = True

# Mirrors capability_registry._TOKEN_RE exactly. Do not "improve" it: the
# whole point is that after folding, the SAME rule applies, so English
# behaviour is provably unchanged.
_TOKEN_RE = re.compile(r"[a-z0-9_]+")

# Characters that count as "inside a word" for boundary purposes. Latin-1
# Supplement + Latin Extended-A/B cover every accented character Spanish,
# Portuguese, Catalan, Galician, French and Italian can produce.
_WORD_CLASS = r"0-9A-Za-z_\u00c0-\u024f"

_PHRASE_CACHE_SIZE = 4096


# ---------------------------------------------------------------------------
# 1. Folding
# ---------------------------------------------------------------------------

def fold_text(text: str) -> str:
    """NFKD-fold ``text``: decompose, drop combining marks, lowercase.

    'Codigo' with an acute accent folds to 'codigo'; 'ANALISIS' with an acute
    folds to 'analisis'; 'ano' with a tilde folds to 'ano'.

    Guaranteed identical to ``text.lower()`` when ``text`` is pure ASCII,
    because NFKD is the identity on ASCII and ASCII has no combining marks.
    """
    if not text:
        return ""
    try:
        decomposed = unicodedata.normalize("NFKD", text)
        stripped = "".join(
            ch for ch in decomposed if not unicodedata.combining(ch)
        )
        return stripped.lower()
    except Exception:
        # FAIL-OPEN: behave exactly like the current code path.
        try:
            return text.lower()
        except Exception:
            return ""


def legacy_tokenize(text: str, stopwords: FrozenSet[str]) -> Set[str]:
    """Exactly what capability_registry does today. Kept for the golden test."""
    return {
        tok
        for tok in _TOKEN_RE.findall((text or "").lower())
        if len(tok) > 1 and tok not in stopwords
    }


def fold_tokenize(text: str, stopwords: FrozenSet[str]) -> Set[str]:
    """Tokenize ``text`` after folding. Drop 1-char tokens and stopwords.

    This is the drop-in replacement for the tokenizer inside
    ``capability_registry._tokenize``.

    >>> fold_tokenize('codigo', frozenset())          # ASCII, unchanged
    {'codigo'}

    For the accented spelling the legacy tokenizer yields {'digo'}; this
    yields {'codigo'} -- so the SAME intent now scores the SAME way whether or
    not the user typed the accent, which also removes an accent-dependent
    nondeterminism that already affects English users pasting accented
    filenames.
    """
    try:
        folded = fold_text(text)
        return {
            tok
            for tok in _TOKEN_RE.findall(folded)
            if len(tok) > 1 and tok not in stopwords
        }
    except Exception:
        return legacy_tokenize(text, stopwords)


# ---------------------------------------------------------------------------
# 2. Word-boundary phrase matching
# ---------------------------------------------------------------------------

def _has_word_edges(phrase: str) -> bool:
    """True when BOTH ends of the phrase are word characters.

    A phrase like ``--noreload`` or ``INI_SECTION_`` or ``send email:`` has a
    non-word edge; applying a boundary assertion there would wrongly reject a
    legitimate hit, so those fall back to plain containment.
    """
    if not phrase:
        return False
    edge_re = re.compile(f"[{_WORD_CLASS}]")
    return bool(edge_re.match(phrase[0])) and bool(edge_re.match(phrase[-1]))


@lru_cache(maxsize=_PHRASE_CACHE_SIZE)
def _bounded_pattern(phrase: str):
    """Compile (and cache) a boundary-anchored pattern for ``phrase``."""
    return re.compile(
        f"(?<![{_WORD_CLASS}])" + re.escape(phrase) + f"(?![{_WORD_CLASS}])"
    )


def phrase_hit(phrase: str, haystack: str) -> bool:
    """Word-boundary-aware replacement for ``phrase in haystack``.

    Both arguments are expected to be already folded/lowercased by the caller
    (``capability_registry`` folds the request once and folds each phrase at
    registry-build time).

    The behaviour difference is deliberately one-directional -- it can only
    remove accidental hits:

    >>> phrase_hit('ue', 'envia un correo de prueba')     # was True
    False
    >>> phrase_hit('image', 'interpreta la imagen')       # was True
    False
    >>> phrase_hit('send email', 'please send email now') # unchanged
    True
    >>> phrase_hit('--noreload', 'run with --noreload')   # punctuated edge
    True

    The first two also fix ENGLISH defects: 'api' inside 'rapid', 'ls' inside
    'false', 'pid' inside 'rapid'.
    """
    if not phrase or not haystack:
        return False
    try:
        if not _has_word_edges(phrase):
            return phrase in haystack
        return _bounded_pattern(phrase).search(haystack) is not None
    except Exception:
        # FAIL-OPEN to today's expression.
        return phrase in haystack


# ---------------------------------------------------------------------------
# 3. Canonical-key expansion
# ---------------------------------------------------------------------------

def expand_request_for_scoring(
    text: str,
    lang: str,
    lexicon: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """Append canonical ENGLISH hint tokens implied by a non-English request.

    ``lexicon`` maps a folded non-English term to hint tokens that ALREADY
    EXIST in ``capability_registry._EXTRA_HINTS_BY_TOOL_NAME`` or in a
    ``ChatWrappedAgentSpec.security_hints`` -- enforced by
    ``test_i18n_lexicon_closure``. Nothing new is ever invented, so the
    scorer's tuned English behaviour remains the only behaviour.

    Short-circuits to the identity for English or a missing lexicon, so the
    English path pays one comparison.

    >>> lex = {'correo': ('email', 'mail', 'send'), 'captura': ('screenshot',)}
    >>> expand_request_for_scoring('envia un correo', 'es', lex)
    'envia un correo email mail send'
    >>> expand_request_for_scoring('send an email', 'en', lex)
    'send an email'
    """
    if not text:
        return text or ""
    if not lang or lang == "en" or not lexicon:
        return text
    try:
        folded = fold_text(text)
        tokens = set(_TOKEN_RE.findall(folded))
        additions: list[str] = []
        seen: Set[str] = set()

        # Single-token lookups.
        for tok in tokens:
            for hint in lexicon.get(tok, ()):  # type: ignore[arg-type]
                if hint not in seen:
                    seen.add(hint)
                    additions.append(hint)

        # Multi-word lexicon entries (e.g. 'captura de pantalla').
        for key, hints in lexicon.items():
            if " " not in key:
                continue
            if phrase_hit(key, folded):
                for hint in hints:
                    if hint not in seen:
                        seen.add(hint)
                        additions.append(hint)

        if not additions:
            return text
        return text + " " + " ".join(additions)
    except Exception:
        # FAIL-OPEN: unexpanded text scores exactly as it does today.
        return text


# ---------------------------------------------------------------------------
# 4. Self-check -- run this file directly to see the fix
# ---------------------------------------------------------------------------

def _demo() -> None:  # pragma: no cover - developer aid
    stop = frozenset(
        "a an and are as at be by for from get how i if in into is it its me "
        "my of on or please show that the this to up use using want what with "
        "you".split()
    )

    print("--- IDENTITY ON ASCII (must be True for every row) ---")
    ascii_cases = [
        "Take a screenshot of the desktop",
        "run the command dir and show me the output",
        "decompile_java the jar at C:/tmp/app.jar",
        "send email to support with subject='Report'",
    ]
    for case in ascii_cases:
        same = legacy_tokenize(case, stop) == fold_tokenize(case, stop)
        print(f"  {same!s:<5}  {case}")

    print("\n--- FOLDING (legacy -> folded) ---")
    for word in ["c\u00f3digo", "an\u00e1lisis", "ejecuci\u00f3n",
                 "contrase\u00f1a", "a\u00f1os", "env\u00eda"]:
        print(f"  {word:<14} {sorted(legacy_tokenize(word, stop))!s:<16}"
              f" -> {sorted(fold_tokenize(word, stop))}")

    print("\n--- PHRASE BOUNDARIES (True = scores a hit) ---")
    pairs = [
        ("ue", "envia un correo de prueba a soporte"),
        ("image", "interpreta la imagen del proyecto"),
        ("api", "hazlo rapido por favor"),
        ("ls", "eso es falso"),
        ("send email", "please send email to support"),
        ("--noreload", "run it with --noreload set"),
    ]
    for phrase, hay in pairs:
        folded_hay = fold_text(hay)
        print(f"  '{phrase}' in '{hay}'\n"
              f"      legacy={phrase in folded_hay!s:<6}"
              f" bounded={phrase_hit(phrase, folded_hay)}")

    print("\n--- EXPANSION ---")
    lex: Dict[str, Iterable[str]] = {
        "correo": ("email", "mail", "send"),
        "captura de pantalla": ("screenshot", "screen", "capture"),
        "borra": ("delete", "remove"),
    }
    for req in ["envia un correo a soporte",
                "toma una captura de pantalla",
                "send an email to support"]:
        lang = "en" if req.startswith("send") else "es"
        print(f"  [{lang}] {req}\n      -> "
              f"{expand_request_for_scoring(req, lang, lex)}")  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover
    _demo()
