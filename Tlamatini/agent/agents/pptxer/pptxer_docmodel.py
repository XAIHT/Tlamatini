# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
#
# pptxer_docmodel.py — CONTENT → DECK MODEL.
#
# Turns whatever the user supplied (Tlamatini's own answer, Markdown, plain
# text, an outline, a JSON deck spec) into an ordered list of typed Slide
# objects the builder can place without guessing.
#
# Sibling module of pptxer.py. Stdlib only. Imports nothing from agent.* and
# nothing from the other pptxer_* modules.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE CENTRAL JUDGEMENT: A SLIDE IS NOT A PAGE
# ─────────────────────────────────────────────────────────────────────────────
# The commonest way machine-made decks fail is not ugliness — it is pouring a
# document onto slides. Twelve bullets at 11pt is a printed page that happens
# to be projected, and nobody at the back of the room can read it.
#
# So this module does real editorial work:
#   · it SPLITS a section that carries more than the theme's density allows,
#     continuing the heading rather than shrinking the type;
#   · it PROMOTES content to the right slide TYPE — a table becomes a table
#     slide, four short parallel facts become stat tiles, a long quotation
#     becomes a quote slide;
#   · it never silently DROPS anything. Overflow becomes another slide.
#
# ⚠️ Shrinking type to make content fit is the one repair this module will not
# make. The layout solver may shrink a title by a few points to fit its box;
# taking body copy below the projected-legibility floor is not "fitting" it, it
# is losing it while appearing to keep it.

import json
import re

__all__ = [
    "Slide", "Deck", "parse_content", "parse_markdown", "parse_json_deck",
    "parse_outline", "detect_format", "SLIDE_TYPES",
]

SLIDE_TYPES = (
    "title_slide", "section_break", "bullets", "statement", "two_column",
    "image_left", "image_right", "image_full", "quote", "stats", "comparison",
    "timeline", "table", "chart", "diagram", "gallery", "media", "code",
    "closing", "agenda",
)


class Slide:
    """One slide's CONTENT. Carries no geometry — that is the builder's job."""

    __slots__ = ("kind", "title", "subtitle", "kicker", "bullets", "body",
                 "notes", "images", "video", "audio", "table", "stats",
                 "quote", "attribution", "code", "language", "columns",
                 "timeline", "diagram", "chart", "meta")

    def __init__(self, kind="bullets", title="", subtitle="", kicker="",
                 bullets=None, body="", notes="", images=None, video="",
                 audio="", table=None, stats=None, quote="", attribution="",
                 code="", language="", columns=None, timeline=None,
                 diagram=None, chart=None, meta=None):
        self.kind = kind if kind in SLIDE_TYPES else "bullets"
        self.title = str(title or "")
        self.subtitle = str(subtitle or "")
        self.kicker = str(kicker or "")
        self.bullets = list(bullets or [])
        self.body = str(body or "")
        self.notes = str(notes or "")
        self.images = list(images or [])
        self.video = str(video or "")
        self.audio = str(audio or "")
        self.table = table            # {"headers": [...], "rows": [[...], ...]}
        self.stats = list(stats or [])  # [{"value": "3.4M", "label": "Players"}]
        self.quote = str(quote or "")
        self.attribution = str(attribution or "")
        self.code = str(code or "")
        self.language = str(language or "")
        self.columns = list(columns or [])
        self.timeline = list(timeline or [])
        self.diagram = diagram
        self.chart = chart
        self.meta = meta or {}

    @property
    def word_count(self) -> int:
        parts = [self.title, self.subtitle, self.body, self.quote]
        parts.extend(self.bullets)
        for col in self.columns:
            parts.append(col.get("title", ""))
            parts.extend(col.get("bullets", []))
        return sum(len(str(p).split()) for p in parts)

    @property
    def has_media(self) -> bool:
        return bool(self.images or self.video or self.audio)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "title": self.title, "subtitle": self.subtitle,
            "kicker": self.kicker, "bullets": self.bullets, "body": self.body,
            "images": self.images, "video": self.video, "audio": self.audio,
            "table": self.table, "stats": self.stats, "quote": self.quote,
            "attribution": self.attribution, "code": self.code,
            "columns": self.columns, "timeline": self.timeline,
            "words": self.word_count,
        }

    def __repr__(self) -> str:
        return f"Slide({self.kind}: {self.title[:40]!r}, {self.word_count}w)"


class Deck:
    """The ordered slides plus deck-level metadata."""

    def __init__(self, slides=None, title="", subtitle="", author="",
                 source_format="", notes=None):
        self.slides = list(slides or [])
        self.title = str(title or "")
        self.subtitle = str(subtitle or "")
        self.author = str(author or "")
        self.source_format = source_format
        self.notes = list(notes or [])

    def __len__(self) -> int:
        return len(self.slides)

    def __iter__(self):
        return iter(self.slides)

    @property
    def image_count(self) -> int:
        return sum(len(s.images) for s in self.slides)

    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.slides)

    def kinds(self) -> dict:
        out = {}
        for s in self.slides:
            out[s.kind] = out.get(s.kind, 0) + 1
        return out

    def plain_text(self) -> str:
        """Everything as text — what the nuance classifier reads."""
        parts = [self.title, self.subtitle]
        for s in self.slides:
            parts.extend([s.title, s.subtitle, s.kicker, s.body, s.quote])
            parts.extend(s.bullets)
            for st in s.stats:
                parts.extend([str(st.get("value", "")), str(st.get("label", ""))])
            if s.table:
                parts.extend(str(h) for h in (s.table.get("headers") or []))
                for row in (s.table.get("rows") or []):
                    parts.extend(str(c) for c in row)
            for col in s.columns:
                parts.append(col.get("title", ""))
                parts.extend(col.get("bullets", []))
            for item in s.timeline:
                parts.extend([str(item.get("when", "")), str(item.get("what", ""))])
        return "\n".join(p for p in parts if p)

    def as_dict(self) -> dict:
        return {
            "title": self.title, "subtitle": self.subtitle,
            "author": self.author, "source_format": self.source_format,
            "slides": [s.as_dict() for s in self.slides],
            "slide_count": len(self.slides), "word_count": self.word_count,
            "image_count": self.image_count, "kinds": self.kinds(),
            "notes": self.notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_format(text: str) -> str:
    """'json' | 'markdown' | 'outline' | 'text'. Cheap and ordered."""
    s = (text or "").strip()
    if not s:
        return "text"

    if s.startswith("{") or s.startswith("["):
        try:
            json.loads(s)
            return "json"
        except (ValueError, TypeError):
            pass

    if re.search(r"^#{1,6}\s+\S", s, re.M):
        return "markdown"
    if re.search(r"^\s*(?:[-*+]|\d+\.)\s+\S", s, re.M) and "\n" in s:
        return "markdown"
    if re.search(r"^\s{2,}[-*+•]\s+\S", s, re.M):
        return "outline"
    if re.search(r"^---\s*$", s, re.M):
        return "markdown"
    return "text"


# ─────────────────────────────────────────────────────────────────────────────
# JSON deck spec — the precise path
# ─────────────────────────────────────────────────────────────────────────────

def parse_json_deck(text) -> Deck:
    """Parse an explicit deck spec. The caller said exactly what it wants.

    Shape:
      {"title": "...", "subtitle": "...", "author": "...",
       "slides": [{"kind": "stats", "title": "...", "stats": [...]}, ...]}

    A list at the top level is accepted as a bare slide list, because that is
    what an LLM most often produces when asked for "the slides".
    """
    try:
        data = json.loads(text) if isinstance(text, str) else text
    except (ValueError, TypeError) as exc:
        return Deck(source_format="json",
                    notes=[f"the JSON deck spec could not be parsed: {exc}"])

    if isinstance(data, list):
        data = {"slides": data}
    if not isinstance(data, dict):
        return Deck(source_format="json",
                    notes=["the JSON deck spec is not an object or a list"])

    slides = []
    notes = []
    for i, raw in enumerate(data.get("slides") or [], start=1):
        if not isinstance(raw, dict):
            notes.append(f"slide {i} in the spec is not an object and was skipped")
            continue
        kind = str(raw.get("kind") or raw.get("type") or "bullets").strip().lower()
        if kind not in SLIDE_TYPES:
            notes.append(f"slide {i}: unknown kind {kind!r}; treated as 'bullets'")
            kind = "bullets"
        slides.append(Slide(
            kind=kind,
            title=raw.get("title", ""), subtitle=raw.get("subtitle", ""),
            kicker=raw.get("kicker", ""),
            bullets=_as_list(raw.get("bullets") or raw.get("points")),
            body=raw.get("body", "") or raw.get("text", ""),
            notes=raw.get("notes", ""),
            images=_as_list(raw.get("images") or raw.get("image")),
            video=raw.get("video", ""), audio=raw.get("audio", ""),
            table=raw.get("table"), stats=raw.get("stats") or [],
            quote=raw.get("quote", ""), attribution=raw.get("attribution", ""),
            code=raw.get("code", ""), language=raw.get("language", ""),
            columns=raw.get("columns") or [], timeline=raw.get("timeline") or [],
            diagram=raw.get("diagram"), chart=raw.get("chart"),
            meta=raw.get("meta") or {},
        ))

    return Deck(slides=slides, title=data.get("title", ""),
                subtitle=data.get("subtitle", ""), author=data.get("author", ""),
                source_format="json", notes=notes)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


# ─────────────────────────────────────────────────────────────────────────────
# Markdown — the common path
# ─────────────────────────────────────────────────────────────────────────────

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITAL_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:.-]*\|[\s|:-]*$")


def parse_markdown(text: str, max_bullets=6) -> Deck:
    """Markdown → slides.

    Rules, chosen to match how people actually write decks:
      · `#`  starts the deck (its title) or a section break;
      · `##` starts a new slide;
      · `###` becomes a sub-heading INSIDE the current slide;
      · `---` forces a slide break wherever it appears;
      · a fenced block becomes a code slide;
      · a pipe table becomes a table slide;
      · `> ` becomes a quote slide when it is the slide's main content;
      · images are collected and the slide is promoted to an image layout.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    deck_title = ""
    deck_subtitle = ""
    slides = []
    notes = []

    cur = None
    buf = []
    in_fence = False
    fence_lang = ""
    fence_buf = []

    def flush_buffer():
        """Turn the accumulated lines into the current slide's content."""
        nonlocal buf
        if cur is None or not buf:
            buf = []
            return
        bullets, para, table, quote, images = _digest_block(buf)
        if images:
            cur.images.extend(images)
        if table and not cur.table:
            cur.table = table
            cur.kind = "table"
        if quote and not cur.quote and not bullets and len(para.split()) < 60:
            cur.quote = quote
            cur.kind = "quote"
        if bullets:
            cur.bullets.extend(bullets)
        if para:
            cur.body = (cur.body + "\n\n" + para).strip() if cur.body else para
        buf = []

    def start_slide(kind, title):
        nonlocal cur
        flush_buffer()
        if cur is not None:
            slides.append(cur)
        cur = Slide(kind=kind, title=title)

    for raw in lines:
        line = raw.rstrip()

        fence = _FENCE_RE.match(line.strip())
        if fence:
            if in_fence:
                if cur is None:
                    cur = Slide(kind="code", title="")
                code_text = "\n".join(fence_buf)
                if cur.code:
                    start_slide("code", cur.title)
                cur.code = code_text
                cur.language = fence_lang
                cur.kind = "code"
                fence_buf = []
                in_fence = False
            else:
                flush_buffer()
                in_fence = True
                fence_lang = fence.group(1) or ""
                fence_buf = []
            continue

        if in_fence:
            fence_buf.append(raw)
            continue

        if re.match(r"^\s*---+\s*$", line):
            flush_buffer()
            if cur is not None:
                slides.append(cur)
                cur = Slide(kind="bullets", title="")
            continue

        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level = len(h.group(1))
            title = _strip_inline(h.group(2).strip())
            if level == 1:
                if not deck_title:
                    deck_title = title
                    flush_buffer()
                    continue
                start_slide("section_break", title)
            elif level == 2:
                start_slide("bullets", title)
            else:
                if cur is None:
                    cur = Slide(kind="bullets", title=title)
                else:
                    flush_buffer()
                    if cur.subtitle:
                        cur.body = ((cur.body + "\n\n") if cur.body else "") + title
                    else:
                        cur.subtitle = title
            continue

        if cur is None and line.strip() and not deck_subtitle and deck_title:
            deck_subtitle = _strip_inline(line.strip())
            continue

        if cur is None and line.strip():
            cur = Slide(kind="bullets", title="")

        buf.append(line)

    if in_fence and fence_buf:
        if cur is None:
            cur = Slide(kind="code", title="")
        cur.code = "\n".join(fence_buf)
        cur.language = fence_lang
        cur.kind = "code"
        notes.append("an unclosed code fence was closed at the end of the content")

    flush_buffer()
    if cur is not None:
        slides.append(cur)

    slides = [s for s in slides if _has_content(s)]
    deck = Deck(slides=slides, title=deck_title, subtitle=deck_subtitle,
                source_format="markdown", notes=notes)
    return _refine(deck, max_bullets)


def _digest_block(lines) -> tuple:
    """A block of markdown lines → (bullets, paragraph, table, quote, images)."""
    bullets = []
    paras = []
    quote_lines = []
    images = []
    table_lines = []
    plain = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if plain:
                paras.append(" ".join(plain))
                plain = []
            continue

        for match in _IMG_RE.finditer(stripped):
            images.append(match.group(2))
        stripped = _IMG_RE.sub("", stripped).strip()
        if not stripped:
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            continue

        if stripped.startswith(">"):
            quote_lines.append(_strip_inline(stripped.lstrip("> ").strip()))
            continue

        bullet = re.match(r"^\s*(?:[-*+•]|\d+[.)])\s+(.*)$", line)
        if bullet:
            if plain:
                paras.append(" ".join(plain))
                plain = []
            bullets.append(_strip_inline(bullet.group(1).strip()))
            continue

        plain.append(_strip_inline(stripped))

    if plain:
        paras.append(" ".join(plain))

    table = _parse_pipe_table(table_lines) if len(table_lines) >= 2 else None
    return (bullets, "\n\n".join(p for p in paras if p), table,
            " ".join(quote_lines).strip(), images)


def _parse_pipe_table(lines):
    """A markdown pipe table → {"headers": [...], "rows": [[...]]}."""
    rows = []
    header = None
    for line in lines:
        if _TABLE_SEP_RE.match(line) and header is not None:
            continue
        cells = [_strip_inline(c.strip()) for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
        else:
            rows.append(cells)
    if header is None:
        return None
    width = max([len(header)] + [len(r) for r in rows]) if rows else len(header)
    header = (header + [""] * width)[:width]
    rows = [(r + [""] * width)[:width] for r in rows]
    return {"headers": header, "rows": rows}


def _strip_inline(text: str) -> str:
    """Remove markdown emphasis, keeping the words.

    PowerPoint runs could carry bold/italic, but mixing inline formatting with
    the measured-fit engine means a bold run is measured with the regular face
    and overflows. Keeping the text plain and letting the THEME decide weight is
    both more consistent and measurable. Link text is kept, the URL dropped —
    a raw URL in a projected bullet is noise nobody can type down anyway.
    """
    s = _LINK_RE.sub(r"\1", text or "")
    s = _BOLD_RE.sub(r"\1", s)
    s = _ITAL_RE.sub(r"\1", s)
    s = _CODE_RE.sub(r"\1", s)
    return s.strip()


def _has_content(slide: Slide) -> bool:
    return bool(slide.title or slide.bullets or slide.body or slide.images
                or slide.table or slide.quote or slide.code or slide.stats
                or slide.columns or slide.timeline or slide.video)


# ─────────────────────────────────────────────────────────────────────────────
# Outline and plain text
# ─────────────────────────────────────────────────────────────────────────────

def parse_outline(text: str, max_bullets=6) -> Deck:
    """An indented outline → slides. Top level = a slide, indented = bullets."""
    slides = []
    cur = None
    for raw in (text or "").split("\n"):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        content = _strip_inline(re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s*", "", raw).strip())
        if not content:
            continue
        if indent == 0:
            if cur is not None:
                slides.append(cur)
            cur = Slide(kind="bullets", title=content)
        else:
            if cur is None:
                cur = Slide(kind="bullets", title="")
            cur.bullets.append(content)
    if cur is not None:
        slides.append(cur)
    return _refine(Deck(slides=slides, source_format="outline"), max_bullets)


def parse_plain_text(text: str, max_bullets=6) -> Deck:
    """Plain prose → slides, split on blank lines with a sensible first title."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    if not blocks:
        return Deck(source_format="text")

    title = ""
    first = blocks[0]
    # A short opening line with no terminal punctuation is a title, not a
    # paragraph — that is how people write.
    if len(first.split()) <= 12 and not first.rstrip().endswith((".", "!", "?", ":")):
        title = _strip_inline(first)
        blocks = blocks[1:]

    slides = []
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        bullet_lines = [ln for ln in lines
                        if re.match(r"^\s*(?:[-*+•]|\d+[.)])\s+", ln)]
        if bullet_lines and len(bullet_lines) >= max(1, len(lines) - 1):
            head = lines[0] if lines[0] not in bullet_lines else ""
            slides.append(Slide(
                kind="bullets", title=_strip_inline(head),
                bullets=[_strip_inline(re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", ln))
                         for ln in bullet_lines],
            ))
        else:
            head = lines[0]
            rest = " ".join(lines[1:])
            if len(head.split()) <= 12 and rest:
                slides.append(Slide(kind="bullets", title=_strip_inline(head),
                                    body=_strip_inline(rest)))
            else:
                slides.append(Slide(kind="statement",
                                    body=_strip_inline(" ".join(lines))))

    return _refine(Deck(slides=slides, title=title, source_format="text"),
                   max_bullets)


def parse_content(text, max_bullets=6, fmt="auto") -> Deck:
    """The single entry point. Detects the format unless told."""
    mode = (fmt or "auto").strip().lower()
    if mode == "auto":
        mode = detect_format(text)
    if mode == "json":
        return _refine(parse_json_deck(text), max_bullets)
    if mode == "markdown":
        return parse_markdown(text, max_bullets)
    if mode == "outline":
        return parse_outline(text, max_bullets)
    return parse_plain_text(text, max_bullets)


# ─────────────────────────────────────────────────────────────────────────────
# Refinement — the editorial pass
# ─────────────────────────────────────────────────────────────────────────────

# A "stat" is a NUMBER with an optional unit, followed by a short label.
#
# ⚠️ The unit list is the load-bearing part. The first version accepted only
# %/k/M/B, so "12ms Median server latency" did not parse — 'm' matched as the
# magnitude suffix and the stranded 's' broke the separator. One unmatched
# bullet makes the whole slide fall back to a bullet list, so a gaming or
# infrastructure deck (ms, fps, GB, TB, ×) silently lost its stat tiles.
# Units are therefore matched as a WHOLE token with a word boundary.
_STAT_RE = re.compile(
    r"^\s*("
    r"[$€£¥]?\s?"                                   # optional currency
    r"[\d][\d,.]*"                                  # the number
    r"\s?"
    r"(?:%|[kKmMbBxX]|"                             # magnitude / multiplier
    r"ms|s|min|h|hr|hrs|d|"                         # time
    r"fps|hz|kHz|MHz|GHz|"                          # rates
    r"KB|MB|GB|TB|PB|kb|mb|gb|tb|"                  # data
    r"px|pt|mm|cm|m|km|ft|"                         # size
    r"million|billion|trillion|"
    r"°|°C|°F"
    r")?"
    # ⚠️ NOT \b here. After '%' the next char is a space — both non-word — so
    # there is no word boundary and "47% Retention" would fail. A negative
    # lookahead for a letter is the correct guard: it lets '%' and ' ' through,
    # and it forces "12ms" to backtrack off the single-letter 'm' alternative
    # onto 'ms' instead of stranding the 's'.
    r")(?![A-Za-z])\s*[—–:\-]?\s+(.{2,44})$")


def _refine(deck: Deck, max_bullets=6) -> Deck:
    """Promote slide types and SPLIT overfull slides. Never drops content."""
    from copy import deepcopy
    out = []
    for slide in deck.slides:

        # ---- promote: parallel numeric facts become stat tiles -------------
        if (slide.kind == "bullets" and 2 <= len(slide.bullets) <= 6
                and not slide.table and not slide.code):
            parsed = [_STAT_RE.match(b) for b in slide.bullets]
            if all(parsed):
                slide.stats = [{"value": m.group(1).strip(),
                                "label": m.group(2).strip()} for m in parsed]
                slide.bullets = []
                slide.kind = "stats"

        # ---- promote: images decide the layout -----------------------------
        if slide.images and slide.kind in ("bullets", "statement"):
            if len(slide.images) >= 3:
                slide.kind = "gallery"
            elif not slide.bullets and not slide.body:
                slide.kind = "image_full"
            else:
                slide.kind = "image_right"

        if slide.video and slide.kind not in ("media",):
            slide.kind = "media"

        # ---- promote: a title with nothing under it is a section break -----
        if (slide.kind == "bullets" and slide.title and not slide.bullets
                and not slide.body and not slide.images and not slide.table):
            slide.kind = "section_break"

        # ---- promote: a short body alone is a statement --------------------
        if (slide.kind == "bullets" and not slide.bullets and slide.body
                and len(slide.body.split()) <= 26 and not slide.title):
            slide.kind = "statement"

        # ---- SPLIT rather than shrink --------------------------------------
        cap = max(2, int(max_bullets))
        if len(slide.bullets) > cap:
            chunks = [slide.bullets[i:i + cap]
                      for i in range(0, len(slide.bullets), cap)]
            for n, chunk in enumerate(chunks):
                clone = deepcopy(slide)
                clone.bullets = chunk
                if n:
                    clone.title = f"{slide.title} (cont.)"
                    clone.subtitle = clone.kicker = clone.body = ""
                    clone.images = []
                    clone.meta["continuation"] = True
                out.append(clone)
            continue

        # ---- SPLIT a very long body ----------------------------------------
        if slide.kind in ("bullets", "statement") and len(slide.body.split()) > 170:
            paras = [p.strip() for p in slide.body.split("\n\n") if p.strip()]
            if len(paras) > 1:
                acc, cur_words = [], 0
                groups = []
                for para in paras:
                    words = len(para.split())
                    if acc and cur_words + words > 150:
                        groups.append(acc)
                        acc, cur_words = [para], words
                    else:
                        acc.append(para)
                        cur_words += words
                if acc:
                    groups.append(acc)
                for n, group in enumerate(groups):
                    clone = deepcopy(slide)
                    clone.body = "\n\n".join(group)
                    if n:
                        clone.title = f"{slide.title} (cont.)"
                        clone.subtitle = clone.kicker = ""
                        clone.images = []
                        clone.meta["continuation"] = True
                    out.append(clone)
                continue

        # ---- SPLIT a very long table ---------------------------------------
        if slide.table and len(slide.table.get("rows") or []) > 12:
            headers = slide.table.get("headers") or []
            rows = slide.table.get("rows") or []
            for n in range(0, len(rows), 12):
                clone = deepcopy(slide)
                clone.kind = "table"
                clone.table = dict(clone.table, headers=headers, rows=rows[n:n + 12])
                if n:
                    clone.title = f"{slide.title} (cont.)"
                    clone.meta["continuation"] = True
                out.append(clone)
            continue

        out.append(slide)

    deck.slides = out
    return deck
