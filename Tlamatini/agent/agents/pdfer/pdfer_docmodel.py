# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer document model — content parsed into blocks a renderer can lay out.

WHY THERE IS A MODEL AT ALL
---------------------------
The old PDFer had no model. It handed a string of HTML to ``xhtml2pdf`` and
hoped. That is precisely why it could not be fixed incrementally: with no
representation of "this is a table with these cells", there was nothing to
measure, nothing to solve, and nothing to style differently per nuance. The
overlap bug was unfixable *in that architecture* because the layout decision
happened inside a library that never told anyone what it had decided.

So content is parsed **once** into a list of typed blocks — heading,
paragraph, list, table, code, quote, image, rule, callout — and every
downstream stage works on that:

* `pdfer_tables` measures a ``TableBlock``'s real cells with real font metrics.
* `pdfer_atelier` styles each block from the design system.
* `pdfer_audit` checks the result against what the model said should be there.

INPUT SHAPES
------------
Markdown (via the bundled ``markdown`` library), HTML (from Tlamatini's own
answers — ``prompt.pmt`` Rule 6 makes her emit HTML tables), and plain text.
All three converge on the same block list, which is why ``mode='auto'`` can
sniff the input and still produce one consistent document.

THE PARSER IS STDLIB
--------------------
``html.parser.HTMLParser``, not BeautifulSoup. bs4 does ship with Tlamatini,
but a pool agent that can run with *fewer* moving parts should: this parser is
~250 lines, has no failure mode more exotic than "unclosed tag", and behaves
identically frozen and from source. Malformed HTML degrades to text rather
than raising — an LLM-authored table with a missing ``</td>`` must still
produce a document.

INLINE MARKUP
-------------
Platypus ``Paragraph`` speaks its own small HTML dialect: ``<b> <i> <u>
<font> <a> <br/> <super> <sub>``. It does **not** know ``<strong>``,
``<em>``, ``<code>`` or ``<mark>``. `inline_to_platypus` translates, and —
importantly — **escapes everything else**, because an unescaped ``&`` or a
stray ``<`` inside a cell is a ``ValueError`` from deep inside ReportLab's
paragraph parser at render time, which is exactly the kind of late failure
this agent must not have.

CONTRACTS (do NOT weaken)
-------------------------
1. **NEVER RAISES.** `parse()` returns blocks for any input. Unparseable
   content becomes a single ``CodeBlock`` holding the raw text — visibly
   imperfect, never lost.
2. **NEVER LOSES CONTENT.** Every character of the input ends up in some
   block. A parser that silently drops a section is worse than one that
   renders it plainly.
3. **Table cells keep their inline markup** (as Platypus markup), because a
   bolded header cell that arrives as plain text has lost information the
   author put there on purpose.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser

__all__ = [
    "Block", "HeadingBlock", "ParagraphBlock", "ListBlock", "TableBlock",
    "CodeBlock", "QuoteBlock", "ImageBlock", "RuleBlock", "CalloutBlock",
    "Document", "parse", "parse_markdown", "parse_html", "parse_text",
    "inline_to_platypus", "escape_inline",
]


# ─────────────────────────────────────────────────────────────────────────
#  Blocks
# ─────────────────────────────────────────────────────────────────────────
class Block:
    kind = "block"

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def text_len(self) -> int:
        return 0

    def __repr__(self) -> str:
        return "<%s>" % self.kind


class HeadingBlock(Block):
    kind = "heading"

    def __init__(self, level, text, anchor=""):
        Block.__init__(self, level=max(1, min(int(level or 1), 6)),
                       text=text or "", anchor=anchor)

    def text_len(self):
        return len(self.text)

    def __repr__(self):
        return "<h%d %r>" % (self.level, self.text[:40])


class ParagraphBlock(Block):
    kind = "paragraph"

    def __init__(self, text, lead=False):
        Block.__init__(self, text=text or "", lead=bool(lead))

    def text_len(self):
        return len(self.text)

    def __repr__(self):
        return "<p %r>" % self.text[:40]


class ListBlock(Block):
    kind = "list"

    def __init__(self, items, ordered=False, level=0, start=1):
        Block.__init__(self, items=list(items or ()), ordered=bool(ordered),
                       level=int(level or 0), start=int(start or 1))

    def text_len(self):
        return sum(len(str(i)) for i in self.items)

    def __repr__(self):
        return "<%s list %d items>" % ("ol" if self.ordered else "ul",
                                       len(self.items))


class TableBlock(Block):
    kind = "table"

    def __init__(self, rows, has_header=True, caption=""):
        Block.__init__(self, rows=[list(r) for r in (rows or ())],
                       has_header=bool(has_header), caption=caption or "")

    @property
    def ncols(self):
        return max((len(r) for r in self.rows), default=0)

    def normalised(self):
        """Every row padded to the same width.

        A ragged table is the single most common shape an LLM emits, and it
        is also the shape that makes a naive renderer index off the end of a
        row. Padding here means every consumer downstream can assume a
        rectangle.
        """
        width = self.ncols
        return [list(row) + [""] * (width - len(row)) for row in self.rows]

    def text_len(self):
        return sum(len(str(c)) for row in self.rows for c in row)

    def __repr__(self):
        return "<table %dx%d>" % (len(self.rows), self.ncols)


class CodeBlock(Block):
    kind = "code"

    def __init__(self, text, language="", filename=""):
        Block.__init__(self, text=text or "", language=language or "",
                       filename=filename or "")

    def text_len(self):
        return len(self.text)

    def __repr__(self):
        return "<code %s %d chars>" % (self.language or "?", len(self.text))


class QuoteBlock(Block):
    kind = "quote"

    def __init__(self, blocks, attribution=""):
        Block.__init__(self, blocks=list(blocks or ()),
                       attribution=attribution or "")

    def text_len(self):
        return sum(b.text_len() for b in self.blocks)

    def __repr__(self):
        return "<quote %d blocks>" % len(self.blocks)


class CalloutBlock(Block):
    kind = "callout"

    def __init__(self, tone, title, blocks):
        Block.__init__(self, tone=tone or "info", title=title or "",
                       blocks=list(blocks or ()))

    def text_len(self):
        return sum(b.text_len() for b in self.blocks)

    def __repr__(self):
        return "<callout %s>" % self.tone


class ImageBlock(Block):
    kind = "image"

    def __init__(self, src, alt="", caption="", width=0, height=0):
        Block.__init__(self, src=src or "", alt=alt or "",
                       caption=caption or "", width=width, height=height)

    def __repr__(self):
        return "<img %r>" % self.src[:40]


class RuleBlock(Block):
    kind = "rule"

    def __init__(self):
        Block.__init__(self)


class Document:
    """A parsed document plus the shape statistics the renderer reasons over."""

    def __init__(self, blocks, title="", source="", notes=None):
        self.blocks = list(blocks or ())
        self.title = title or ""
        self.source = source
        self.notes = list(notes or ())

    # ── shape ───────────────────────────────────────────────────────────
    def count(self, kind):
        return sum(1 for b in self.blocks if b.kind == kind)

    def tables(self):
        return [b for b in self.blocks if b.kind == "table"]

    def headings(self):
        return [b for b in self.blocks if b.kind == "heading"]

    def images(self):
        return [b for b in self.blocks if b.kind == "image"]

    def total_text(self):
        return sum(b.text_len() for b in self.blocks)

    def first_heading(self):
        for block in self.blocks:
            if block.kind == "heading":
                return block
        return None

    def infer_title(self):
        """Best available document title.

        An explicit ``title`` wins; otherwise the first H1; otherwise the
        first heading of any level; otherwise nothing. It deliberately does
        NOT fall back to the first paragraph — a title invented from prose is
        a title the author did not write.
        """
        if self.title.strip():
            return self.title.strip()
        for block in self.blocks:
            if block.kind == "heading" and block.level == 1:
                return strip_inline(block.text)
        head = self.first_heading()
        return strip_inline(head.text) if head else ""

    def outline(self):
        """(level, text) pairs — the input to a generated table of contents."""
        return [(b.level, strip_inline(b.text)) for b in self.blocks
                if b.kind == "heading"]

    def stats(self):
        return {
            "blocks": len(self.blocks),
            "headings": self.count("heading"),
            "paragraphs": self.count("paragraph"),
            "tables": self.count("table"),
            "lists": self.count("list"),
            "code_blocks": self.count("code"),
            "quotes": self.count("quote"),
            "callouts": self.count("callout"),
            "images": self.count("image"),
            "rules": self.count("rule"),
            "characters": self.total_text(),
            "max_table_cols": max((t.ncols for t in self.tables()), default=0),
        }

    def __repr__(self):
        return "Document(%d blocks, %s)" % (len(self.blocks), self.stats())


# ─────────────────────────────────────────────────────────────────────────
#  Inline markup
# ─────────────────────────────────────────────────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>")

#: What Platypus' Paragraph parser genuinely understands. Anything outside
#: this set must be translated or escaped — handing it an unknown tag is a
#: hard error from inside ReportLab at render time.
_PLATYPUS_SAFE = {"b", "i", "u", "strike", "sub", "super", "br", "font",
                  "a", "para", "greek", "span", "link"}

_INLINE_MAP = (
    (re.compile(r"<\s*strong\s*>", re.I), "<b>"),
    (re.compile(r"<\s*/\s*strong\s*>", re.I), "</b>"),
    (re.compile(r"<\s*em\s*>", re.I), "<i>"),
    (re.compile(r"<\s*/\s*em\s*>", re.I), "</i>"),
    (re.compile(r"<\s*ins\s*>", re.I), "<u>"),
    (re.compile(r"<\s*/\s*ins\s*>", re.I), "</u>"),
    (re.compile(r"<\s*(del|s)\s*>", re.I), "<strike>"),
    (re.compile(r"<\s*/\s*(del|s)\s*>", re.I), "</strike>"),
    (re.compile(r"<\s*small\s*>", re.I), "<font size='-1'>"),
    (re.compile(r"<\s*/\s*small\s*>", re.I), "</font>"),
    (re.compile(r"<\s*/?\s*(mark|abbr|cite|q|dfn|var|kbd|samp|time|bdi|"
                r"wbr|ruby|rt)\s*>", re.I), ""),
)


def escape_inline(text: str) -> str:
    """Escape for Platypus. ``&`` first, always — order is not optional."""
    return (str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def strip_inline(text: str) -> str:
    """Plain text with all markup removed and entities resolved."""
    return _html.unescape(_TAG_RE.sub("", str(text or ""))).strip()


def inline_to_platypus(fragment: str, mono_font: str = "Courier",
                       code_color: str = "") -> str:
    """Translate an HTML inline fragment into Platypus' dialect.

    ``<code>`` becomes a ``<font face=...>`` run because Platypus has no code
    element, and a code span rendered in the body face is indistinguishable
    from prose — which matters in exactly the documents (manuals, papers)
    where the distinction carries meaning.
    """
    text = str(fragment or "")
    for pattern, replacement in _INLINE_MAP:
        text = pattern.sub(replacement, text)

    if code_color:
        code_open = "<font face='%s' color='%s'>" % (mono_font, code_color)
    else:
        code_open = "<font face='%s'>" % mono_font
    text = re.sub(r"<\s*code\s*>", code_open, text, flags=re.I)
    text = re.sub(r"<\s*/\s*code\s*>", "</font>", text, flags=re.I)

    # Drop every tag Platypus does not know, keeping its inner text.
    def _keep_or_strip(match):
        tag = re.sub(r"[^a-zA-Z]", "", match.group(0).split()[0])
        return match.group(0) if tag.lower() in _PLATYPUS_SAFE else ""

    text = _TAG_RE.sub(_keep_or_strip, text)
    # A stray & that is not already an entity would break the parser.
    text = re.sub(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]{1,8}|#\d{1,6}|#x[0-9a-fA-F]{1,6});)",
                  "&amp;", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────
#  The HTML → blocks parser
# ─────────────────────────────────────────────────────────────────────────
_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
               "li", "table", "thead", "tbody", "tr", "th", "td", "pre",
               "blockquote", "hr", "img", "figure", "figcaption", "section",
               "article", "header", "footer", "main", "aside", "dl", "dt",
               "dd"}

_CALLOUT_TONES = {
    "note": "info", "info": "info", "tip": "success", "success": "success",
    "warning": "warning", "caution": "warning", "danger": "danger",
    "error": "danger", "important": "warning", "nota": "info",
    "aviso": "warning", "peligro": "danger", "consejo": "success",
}
_CALLOUT_RE = re.compile(
    r"^\s*(?:>\s*)?\[!(\w+)\]\s*(.*)$|^\s*\*\*(note|warning|tip|important|"
    r"caution|danger|nota|aviso|consejo)\s*[::]\*\*\s*(.*)$", re.IGNORECASE)


class _BlockParser(HTMLParser):
    """HTML → block list. Tolerant by design; never raises on bad markup."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.blocks = []
        self.notes = []
        self._buf = []                 # inline text of the current block
        self._stack = []               # open block contexts
        self._list_stack = []          # (ordered, items, start)
        self._table = None             # rows being collected
        self._row = None
        self._cell = None
        self._pre = None
        self._pre_lang = ""
        self._quote_depth = 0
        self._quote_blocks = []
        self._skip_depth = 0           # inside <script>/<style>

    # ── helpers ─────────────────────────────────────────────────────────
    def _flush_paragraph(self):
        text = "".join(self._buf).strip()
        self._buf = []
        if not text:
            return
        collapsed = re.sub(r"\s+", " ", text).strip()
        if not collapsed:
            return
        block = self._as_callout(collapsed) or ParagraphBlock(collapsed)
        self._emit(block)

    @staticmethod
    def _as_callout(text):
        """Recognise ``[!NOTE]`` / ``**Warning:**`` openers.

        These are the two conventions people actually use for an admonition,
        and rendering one as an ordinary paragraph throws away the author's
        signal that this block is *more important than the ones around it*.
        """
        match = _CALLOUT_RE.match(text)
        if not match:
            return None
        keyword = (match.group(1) or match.group(3) or "").lower()
        body = (match.group(2) or match.group(4) or "").strip()
        tone = _CALLOUT_TONES.get(keyword)
        if not tone:
            return None
        return CalloutBlock(tone, keyword.title(),
                            [ParagraphBlock(body)] if body else [])

    def _emit(self, block):
        if self._quote_depth > 0:
            self._quote_blocks.append(block)
        else:
            self.blocks.append(block)

    # ── tag handling ────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attributes = dict((k.lower(), v or "") for k, v in attrs)

        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "br":
            self._buf.append("<br/>")
            return
        if tag == "hr":
            self._flush_paragraph()
            self._emit(RuleBlock())
            return
        if tag == "img":
            self._flush_paragraph()
            self._emit(ImageBlock(attributes.get("src", ""),
                                  attributes.get("alt", ""),
                                  attributes.get("title", "")))
            return

        if tag == "pre":
            self._flush_paragraph()
            self._pre = []
            return
        if tag == "code" and self._pre is not None:
            cls = attributes.get("class", "")
            match = re.search(r"(?:language|lang|highlight)-([\w+#.-]+)", cls)
            if match:
                self._pre_lang = match.group(1)
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_paragraph()
            self._stack.append(("heading", int(tag[1])))
            return
        if tag == "blockquote":
            self._flush_paragraph()
            self._quote_depth += 1
            return
        if tag in ("ul", "ol"):
            self._flush_paragraph()
            start = 1
            try:
                start = int(attributes.get("start", 1))
            except Exception:
                start = 1
            self._list_stack.append([tag == "ol", [], start])
            return
        if tag == "li":
            self._flush_paragraph()
            self._buf = []
            return
        if tag == "table":
            self._flush_paragraph()
            self._table = {"rows": [], "header": False, "caption": ""}
            return
        if tag == "tr" and self._table is not None:
            self._row = []
            return
        if tag in ("td", "th") and self._table is not None:
            self._cell = []
            if tag == "th":
                self._table["header"] = True
            # colspan is honoured by padding: a merged header cell that
            # silently swallows its neighbours misaligns every row below it.
            try:
                self._cell_span = max(1, int(attributes.get("colspan", 1)))
            except Exception:
                self._cell_span = 1
            return
        if tag in ("figcaption", "caption") and self._table is not None:
            self._cell = []
            return

        # Any other inline tag: keep it, the inline translator will decide.
        if tag not in _BLOCK_TAGS:
            rendered = "<%s%s>" % (tag, "".join(
                ' %s="%s"' % (k, _html.escape(v, quote=True))
                for k, v in attributes.items() if k in ("href", "color",
                                                        "face", "size")))
            self._buf.append(rendered)
        elif tag in ("p", "div", "section", "article", "header", "footer",
                     "main", "aside", "dl", "dt", "dd"):
            self._flush_paragraph()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "pre":
            if self._pre is not None:
                text = "".join(self._pre)
                self._emit(CodeBlock(text.rstrip("\n"), self._pre_lang))
            self._pre, self._pre_lang = None, ""
            return
        if tag == "code" and self._pre is not None:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = 1
            if self._stack and self._stack[-1][0] == "heading":
                level = self._stack.pop()[1]
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._buf = []
            if text:
                self._emit(HeadingBlock(level, text))
            return
        if tag == "blockquote":
            self._flush_paragraph()
            self._quote_depth = max(0, self._quote_depth - 1)
            if self._quote_depth == 0 and self._quote_blocks:
                self.blocks.append(QuoteBlock(self._quote_blocks))
                self._quote_blocks = []
            return
        if tag == "li":
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._buf = []
            if self._list_stack and text:
                self._list_stack[-1][1].append(text)
            elif text:
                self._emit(ParagraphBlock(text))
            return
        if tag in ("ul", "ol"):
            self._flush_paragraph()
            if self._list_stack:
                ordered, items, start = self._list_stack.pop()
                if items:
                    block = ListBlock(items, ordered,
                                      level=len(self._list_stack), start=start)
                    if self._list_stack:
                        # A nested list is flattened one level with its own
                        # indent rather than being lost inside its parent.
                        self._emit(block)
                    else:
                        self._emit(block)
            return
        if tag in ("td", "th"):
            if self._cell is not None and self._row is not None:
                value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
                self._row.append(value)
                for _ in range(max(0, getattr(self, "_cell_span", 1) - 1)):
                    self._row.append("")
            self._cell = None
            return
        if tag == "tr":
            if self._row is not None and self._table is not None:
                if any(str(c).strip() for c in self._row):
                    self._table["rows"].append(self._row)
            self._row = None
            return
        if tag == "table":
            if self._table is not None and self._table["rows"]:
                self._emit(TableBlock(self._table["rows"],
                                      self._table["header"],
                                      self._table["caption"]))
            self._table = None
            return
        if tag in ("caption", "figcaption"):
            if self._cell is not None and self._table is not None:
                self._table["caption"] = "".join(self._cell).strip()
            self._cell = None
            return
        if tag in ("p", "div", "section", "article", "header", "footer",
                   "main", "aside", "dl", "dt", "dd"):
            self._flush_paragraph()
            return
        if tag not in _BLOCK_TAGS:
            self._buf.append("</%s>" % tag)

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._pre is not None:
            self._pre.append(data)
        elif self._cell is not None:
            self._cell.append(data)
        else:
            self._buf.append(data)

    def close(self):
        try:
            HTMLParser.close(self)
        except Exception:
            pass
        # Unclosed structures still yield their content — LLM-authored HTML
        # loses a closing tag often enough that dropping the rest of the
        # document over it would be a real, frequent data loss.
        if self._pre is not None:
            self._emit(CodeBlock("".join(self._pre).rstrip("\n"),
                                 self._pre_lang))
            self.notes.append("an unclosed <pre> was recovered")
            self._pre = None
        while self._list_stack:
            ordered, items, start = self._list_stack.pop()
            if items:
                self._emit(ListBlock(items, ordered, start=start))
                self.notes.append("an unclosed list was recovered")
        if self._table is not None and self._table["rows"]:
            if self._row and any(str(c).strip() for c in self._row):
                self._table["rows"].append(self._row)
            self._emit(TableBlock(self._table["rows"], self._table["header"]))
            self.notes.append("an unclosed <table> was recovered")
            self._table = None
        if self._quote_blocks:
            self.blocks.append(QuoteBlock(self._quote_blocks))
            self._quote_blocks = []
        self._flush_paragraph()


def parse_html(source: str, title: str = "") -> "Document":
    """HTML → Document. Never raises; malformed markup degrades gracefully."""
    parser = _BlockParser()
    try:
        parser.feed(source or "")
    except Exception as exc:
        parser.notes.append("HTML parse interrupted (%s) — the recovered "
                            "portion is kept" % type(exc).__name__)
    parser.close()
    blocks = parser.blocks
    if not blocks and (source or "").strip():
        blocks = [ParagraphBlock(escape_inline(strip_inline(source)))]
        parser.notes.append("no structure recognised — rendered as prose")
    return Document(blocks, title=title, source="html", notes=parser.notes)


def parse_markdown(source: str, title: str = "") -> "Document":
    """Markdown → Document, via the bundled ``markdown`` library.

    Falls back to `parse_text` when the library is missing, so a stripped
    environment still produces a readable document instead of an error.
    """
    text = source or ""
    try:
        from markdown import markdown as _md
        rendered = _md(text, extensions=["fenced_code", "tables", "toc",
                                         "sane_lists", "nl2br"],
                       output_format="html5")
    except Exception as exc:
        doc = parse_text(text, title=title)
        doc.notes.append("markdown unavailable (%s) — rendered as plain text"
                         % type(exc).__name__)
        return doc
    doc = parse_html(rendered, title=title)
    doc.source = "markdown"
    return doc


def parse_text(source: str, title: str = "") -> "Document":
    """Plain text → Document.

    Blank-line-separated paragraphs, and a run of indented lines becomes a
    code block — the two conventions every plain-text document already uses.
    """
    text = (source or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks, buffer, code = [], [], []

    def flush_text():
        if buffer:
            joined = " ".join(line.strip() for line in buffer).strip()
            if joined:
                blocks.append(ParagraphBlock(escape_inline(joined)))
            buffer[:] = []

    def flush_code():
        if code:
            blocks.append(CodeBlock("\n".join(code).rstrip()))
            code[:] = []

    for line in text.split("\n"):
        if line.startswith(("    ", "\t")) and line.strip():
            flush_text()
            code.append(line[4:] if line.startswith("    ") else line[1:])
        elif not line.strip():
            flush_code()
            flush_text()
        else:
            flush_code()
            buffer.append(line)
    flush_code()
    flush_text()
    if not blocks and text.strip():
        blocks = [CodeBlock(text)]
    return Document(blocks, title=title, source="text")


_HTML_HINT = re.compile(
    r"<\s*(html|body|div|p|h[1-6]|table|tr|td|ul|ol|li|pre|span|section|"
    r"article|strong|em|br|img)\b", re.IGNORECASE)


def looks_like_html(text: str) -> bool:
    """Two or more distinct HTML block tags — the same test the agent uses to
    resolve ``mode='auto'``, kept here so the model and the mode agree."""
    return len(set(m.group(1).lower()
                   for m in _HTML_HINT.finditer(text or ""))) >= 2


def parse(source: str, kind: str = "auto", title: str = "") -> "Document":
    """Parse *source* as *kind* (``auto`` | ``markdown`` | ``html`` | ``text``).

    NEVER RAISES: any failure returns the raw content as a single code block,
    which is ugly but complete. Losing the user's document is never an
    acceptable outcome of a parse error.
    """
    try:
        mode = (kind or "auto").strip().lower()
        if mode == "auto":
            mode = "html" if looks_like_html(source) else "markdown"
        if mode == "html":
            return parse_html(source, title)
        if mode == "text":
            return parse_text(source, title)
        return parse_markdown(source, title)
    except Exception as exc:
        return Document([CodeBlock(source or "")], title=title, source="raw",
                        notes=["parse failed (%s: %s) — the content is "
                               "preserved verbatim as a code block"
                               % (type(exc).__name__, exc)])
