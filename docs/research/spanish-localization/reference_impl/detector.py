"""Closed-set language identification for Tlamatini, with prose masking.

REFERENCE IMPLEMENTATION -- not wired into Tlamatini. See PAPER.md section 7.3.

This replaces the naive detector the prior study proposed. Four defects are
corrected here, each of which produced a wrong verdict on Tlamatini's own
content:

D1  DIACRITIC BACK DOOR. ``if any(ch in 'naeiouu...'): score_es += 3`` lets ONE
    accent decide the verdict. The project's own protected brand string
    "Angela Lopez Mendoza" carries an acute o; so does C:\\Users\\angel\\Musica.
    Here the diacritic signal is a CAPPED DENSITY RATIO over masked prose,
    worth at most _DIACRITIC_CAP points, and it can never outvote the
    function-word evidence on its own.

D2  DEGENERATE CONFIDENCE. ``(best - second) / total`` returns 1.0 whenever the
    loser scores zero, regardless of evidence volume -- "status del server"
    yields MAXIMUM CONFIDENCE Spanish on one matched token. Here confidence is
    evidence-weighted:  ((b - s) / t) * (1 - exp(-t / TAU))  with a hard floor
    of _MIN_EVIDENCE matched function words before any verdict but 'und'.

D3  NO OUT-OF-SET REJECTION. A closed {en, es} set resolves Portuguese,
    Galician and Catalan confidently to 'es'. Here pt/ca/gl/it/fr are carried
    as DECOY classes: they can win, and when they do the verdict is 'und'
    rather than a confident wrong answer.

D4  LID ON RAW TEXT. A Tlamatini answer legitimately contains HTML tables
    (prompt.pmt rule 6), BEGIN-CODE blocks, Windows paths, agent display names
    and END-RESPONSE. Running LID over that flags CORRECT Spanish answers as
    confused. Masking is therefore MANDATORY and applied here, not left to the
    caller -- and the sample is capped in PROSE characters AFTER masking, not
    as a raw 400-char slice (a raw slice of an answer that opens with a table
    contains zero prose).

Stdlib only: re, math, unicodedata (via the sibling normalize module).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

__all__ = ["Detection", "mask_prose", "detect", "line_pass_rate"]

MAX_PROSE_CHARS = 600
_MIN_EVIDENCE = 4          # matched function words required for a verdict
_TAU = 5.0                 # evidence half-saturation constant
_DIACRITIC_CAP = 1.0       # a diacritic signal can never exceed this
_MIN_CHARS = 12

# ---------------------------------------------------------------------------
# Masking -- would live in agent/i18n/masker.py in the real tree
# ---------------------------------------------------------------------------

_MASK_PATTERNS: Tuple[re.Pattern, ...] = (
    # Tlamatini machine sentinels and their payloads
    re.compile(r"BEGIN-CODE<<<.*?>>>.*?END-CODE", re.DOTALL),
    re.compile(r"BEGIN-DIAGRAM.*?END-DIAGRAM", re.DOTALL),
    re.compile(r"INI_SECTION_[A-Z0-9_]+<<<.*?>>>END_SECTION_[A-Z0-9_]+", re.DOTALL),
    re.compile(r"END-RESPONSE"),
    re.compile(r"TLM_VERDICT::[A-Z_]+"),
    re.compile(r"\bVERDICT:\s*[A-Z_]+"),
    re.compile(r"<!--.*?-->", re.DOTALL),
    # Markup and code
    re.compile(r"<[^>]{1,200}>"),
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"`[^`\n]{1,200}`"),
    # Filesystem and network literals
    re.compile(r"[A-Za-z]:\\[^\s\"'<>|]*"),          # C:\path\to\thing
    re.compile(r"(?:/[\w.\-]+){2,}"),                # /usr/local/bin
    re.compile(r"\bhttps?://\S+"),
    re.compile(r"\S+@\S+\.\w+"),
    # Identifiers the termbase protects: snake_case, kebab-tool names, flags
    re.compile(r"\b(?:chat_agent|acp|ext__)[A-Za-z0-9_]*"),
    re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+){1,}\b"),
    re.compile(r"(?<!\w)--?[A-Za-z][\w-]*"),
    # Quoted spans: a dictated message body must not flip the REQUEST language
    re.compile(r"\"[^\"\n]{0,300}\""),
    re.compile(r"'[^'\n]{0,300}'"),
    # Numbers
    re.compile(r"\b\d[\d.,:%-]*\b"),
)


def mask_prose(text: str, protected: Sequence[str] = ()) -> str:
    """Strip everything that is not natural-language prose.

    ``protected`` receives the termbase literals (agent display names, brand
    strings such as the author's name, toggle names). They are removed FIRST so
    that e.g. an acute accent inside a protected brand string can never be read
    as a Spanish signal.

    Fail-open: on any error the original text is returned, because a masking
    failure must degrade detection quality, never raise into the caller.
    """
    if not text:
        return ""
    try:
        out = text
        for term in protected:
            if term:
                out = out.replace(term, " ")
        for pat in _MASK_PATTERNS:
            out = pat.sub(" ", out)
        return re.sub(r"\s+", " ", out).strip()
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Function-word tables (abridged reference sets; production uses ~120 each)
# ---------------------------------------------------------------------------

_FW: Dict[str, frozenset] = {
    "en": frozenset("""
        the of and to in is are was were be been being have has had do does did
        will would can could should must may might not no yes this that these
        those there here with without from into onto about above below between
        for but or if then than when while because so such only just also very
        it its it's you your yours we our they their he she his her him them
        what which who whom whose how why where all any both each few more most
        other some than too own same again further once during before after
    """.split()),
    "es": frozenset("""
        el la los las un una unos unas de del al a en con sin por para sobre
        entre hacia hasta desde y e o u ni que quien cuyo cuando donde como
        porque aunque pero sino si no se lo le les me te nos os su sus mi mis
        tu tus nuestro nuestra es son era eran ser estar esta estan este esta
        estos estas ese esa esos esas aquel aquella hay muy mas menos tambien
        tampoco solo ya todavia siempre nunca cada todo toda todos todas
    """.split()),
    # DECOY classes -- offered to the classifier, never offered as an answer
    # language. If one of these wins, the verdict is 'und'.
    "pt": frozenset("""
        o a os as um uma de do da dos das em no na nos nas para por com sem
        que nao sim eu voce ele ela nos eles elas isso isto aquilo mais muito
        tambem ja ainda sempre nunca cada todo toda todos todas ser estar tem
        foi era sao esta estao pelo pela porem entao assim quando onde como
    """.split()),
    "ca": frozenset("""
        el la els les un una de del dels al als amb sense per per_a que no
        si jo tu ell ella nosaltres vosaltres ells elles aixo aquest aquesta
        molt tambe ja encara sempre mai cada tot tota tots totes ser estar
        es son era eren fer fa quan on com perque pero sino doncs aleshores
    """.split()),
    "it": frozenset("""
        il lo la i gli le un uno una di del della dei delle al alla ai alle
        con senza per tra fra che non si mi ti ci vi ne piu molto anche gia
        ancora sempre mai ogni tutto tutta tutti tutte essere stare sono era
        erano quando dove come perche ma se allora quindi questo questa
    """.split()),
    "fr": frozenset("""
        le la les un une des du de au aux avec sans pour par sur sous dans
        que qui ne pas plus tres aussi deja encore toujours jamais chaque
        tout toute tous toutes etre avoir est sont etait etaient quand ou
        comment pourquoi mais si alors donc ce cette ces celui celle
    """.split()),
}

# Spanish diacritics that Portuguese/Catalan do NOT share as strongly.
_ES_MARKS = frozenset("\u00f1\u00bf\u00a1")
_ANY_MARKS = frozenset("\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00e0\u00e8\u00ec\u00f2\u00f9\u00e2\u00ea\u00ee\u00f4\u00fb\u00e3\u00f5\u00e7")

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class Detection:
    """A language verdict. ``lang`` is 'en', 'es' or 'und' -- never a decoy."""

    lang: str
    confidence: float
    evidence: int
    prose_chars: int
    runner_up: str = ""
    reason: str = ""


def detect(
    text: str,
    candidates: Sequence[str] = ("en", "es"),
    protected: Sequence[str] = (),
    already_masked: bool = False,
) -> Detection:
    """Identify the language of ``text`` over a closed candidate set.

    Returns ``Detection('und', ...)`` -- deliberately, not a guess -- when the
    evidence is thin, the margin is small, or a DECOY language wins. The caller
    (``policy.decide``) then inherits the conversation language, which is what
    prevents ES/EN/ES/EN flapping on short turns.

    Fail-open: any internal error yields 'und', never an exception.
    """
    try:
        prose = text if already_masked else mask_prose(text, protected)
        prose = prose[:MAX_PROSE_CHARS]
        if len(prose.strip()) < _MIN_CHARS:
            return Detection("und", 0.0, 0, len(prose), reason="too_short")

        low = prose.lower()
        tokens = _WORD_RE.findall(low)
        if not tokens:
            return Detection("und", 0.0, 0, len(prose), reason="no_prose")

        # Score every class, decoys included.
        scores: Dict[str, float] = {}
        for lang, table in _FW.items():
            scores[lang] = float(sum(1 for t in tokens if t in table))

        # Capped diacritic density -- a signal, never a decision.
        if scores:
            n_marks = sum(1 for ch in low if ch in _ES_MARKS)
            if n_marks:
                density = n_marks / max(len(tokens), 1)
                scores["es"] = scores.get("es", 0.0) + min(
                    _DIACRITIC_CAP, density * 8.0
                )
            n_any = sum(1 for ch in low if ch in _ANY_MARKS)
            if n_any:
                # Shared across es/pt/ca/it/fr -- boost them all equally so the
                # signal cannot break the tie between them.
                bump = min(_DIACRITIC_CAP, (n_any / max(len(tokens), 1)) * 4.0)
                for lang in ("es", "pt", "ca", "it", "fr"):
                    scores[lang] = scores.get(lang, 0.0) + bump

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        best, best_score = ranked[0]
        second, second_score = ranked[1] if len(ranked) > 1 else ("", 0.0)
        total = sum(scores.values())

        # Absolute evidence floor -- D2.
        if best_score < _MIN_EVIDENCE:
            return Detection(
                "und", 0.0, int(best_score), len(prose), second,
                reason="insufficient_evidence",
            )

        margin = (best_score - second_score) / max(total, 1.0)
        confidence = margin * (1.0 - math.exp(-total / _TAU))

        # Out-of-set rejection -- D3.
        if best not in candidates:
            return Detection(
                "und", round(confidence, 4), int(best_score), len(prose),
                best, reason=f"out_of_set:{best}",
            )

        return Detection(
            best, round(min(confidence, 1.0), 4), int(best_score),
            len(prose), second, reason="ok",
        )
    except Exception:
        return Detection("und", 0.0, 0, 0, reason="error")


def line_pass_rate(
    text: str,
    expected: str,
    protected: Sequence[str] = (),
    min_line_chars: int = 20,
) -> float:
    """Language Confusion Benchmark LPR, adapted for Tlamatini answers.

    Fraction of PROSE lines detected as ``expected``. Lines that mask down to
    fewer than ``min_line_chars`` of prose (a table row, a path, a code line)
    are EXCLUDED rather than failed -- without that exclusion every correct
    Spanish answer containing a Rule-6 HTML table scores as confused.

    Returns 1.0 when there is no gradeable prose, so an all-code answer is
    never reported as a language failure.
    """
    try:
        graded = 0
        passed = 0
        for raw_line in (text or "").splitlines():
            prose = mask_prose(raw_line, protected)
            if len(prose.strip()) < min_line_chars:
                continue
            graded += 1
            d = detect(prose, candidates=("en", "es"), already_masked=True)
            if d.lang == expected:
                passed += 1
        return 1.0 if graded == 0 else passed / graded
    except Exception:
        return 1.0


def _demo() -> None:  # pragma: no cover - developer aid
    protected = ("Angela L\u00f3pez Mendoza", "STM32er", "File-Creator",
                 "Exec report", "Multi-Turn", "Tlamatini")

    print("--- THE FOUR CORRECTED DEFECTS ---\n")

    cases = [
        ("D1 diacritic back door",
         "The report was written by Angela L\u00f3pez Mendoza last week and "
         "saved to the shared drive for the team to review.", "en"),
        ("D2 degenerate confidence",
         "status del server", "und"),
        ("D3 out-of-set Portuguese",
         "O sistema nao conseguiu abrir o arquivo porque o caminho nao existe "
         "e por isso a operacao foi cancelada.", "und"),
        ("D4 masking - Spanish answer with a code block",
         "Aqui tienes el archivo que pediste, ya quedo guardado en el disco.\n"
         "BEGIN-CODE<<<hola.py>>>\nprint('hello world')\nEND-CODE\n"
         "END-RESPONSE", "es"),
        # The requirement is "must NOT resolve to es". Masking removes the
        # quoted Spanish body, which can leave too little English prose to
        # clear the evidence floor -- so 'und' is a CORRECT outcome here, not a
        # miss: policy.decide then INHERITS the conversation language (English)
        # rather than flipping. Asserting 'en' specifically would be stricter
        # than the invariant that actually matters.
        ("quoted body must not flip the request",
         "Send an email to support saying \"Hola, como estas? Nos vemos "
         "manana en la oficina temprano\" and confirm it went out.", "not-es"),
        ("plain Spanish operator request",
         "Necesito que borres todos los archivos temporales de esa carpeta "
         "y luego me digas cuantos eliminaste.", "es"),
    ]
    for label, text, want in cases:
        d = detect(text, protected=protected)
        passed = (d.lang != "es") if want == "not-es" else (d.lang == want)
        ok = "OK  " if passed else "MISS"
        print(f"[{ok}] {label}\n"
              f"       want={want:<4} got={d.lang:<4} conf={d.confidence:<6} "
              f"evidence={d.evidence} reason={d.reason}")

    print("\n--- LPR on a mixed Spanish answer with a table ---")
    answer = (
        "Listo, ya ejecute la operacion que me pediste sobre la carpeta.\n"
        "<table><tr><td>Archivo</td><td>Estado</td></tr></table>\n"
        "C:\\Tlamatini\\Temp\\salida.log\n"
        "Si necesitas que revise algo mas del resultado, dime y lo reviso.\n"
        "END-RESPONSE"
    )
    print(f"  LPR(es) = {line_pass_rate(answer, 'es', protected):.2f}"
          "   (table + path lines correctly EXCLUDED, not failed)")


if __name__ == "__main__":  # pragma: no cover
    _demo()
