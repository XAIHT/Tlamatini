# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""The printed dossier: an A4 codex with a dark cover, dark chapter openers and
ivory reading pages.

Every block of text is a ReportLab Paragraph or a measured string, so nothing
is ever drawn wider than its box; every diagram computes its own height from
its measured content. The glyph ledger fails the build if any character is
missing from the font it is set in.
"""
from __future__ import annotations

import math
import random
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

from dossier_theme import AVATAR, PALETTE, GlyphLedger, runs, split_fallback

W, H = A4
ML, MR, MT, MB = 58, 58, 78, 66
FRAME_W = W - ML - MR

RL = {  # logical font -> registered ReportLab name
    "serif": "DSerif", "serif-bold": "DSerifB", "serif-italic": "DSerifI",
    "sans": "DSans", "sans-italic": "DSansI", "sans-light": "DSansL", "sans-semilight": "DSansSL",
    "sans-semibold": "DSansSB", "sans-bold": "DSansB", "mono": "DMono", "mono-bold": "DMonoB",
    "symbol": "DSym",
}
_FILES = {
    "DSerif": "pala.ttf", "DSerifB": "palab.ttf", "DSerifI": "palai.ttf", "DSans": "segoeui.ttf",
    "DSansI": "segoeuii.ttf", "DSansL": "segoeuil.ttf", "DSansSL": "segoeuisl.ttf", "DSansSB": "seguisb.ttf",
    "DSansB": "segoeuib.ttf", "DMono": "consola.ttf", "DMonoB": "consolab.ttf", "DSym": "seguisym.ttf",
}
LEDGER = GlyphLedger()


def c(name: str, alpha: float | None = None):
    value = colors.HexColor(PALETTE.get(name, name))
    if alpha is not None:
        value = colors.Color(value.red, value.green, value.blue, alpha=alpha)
    return value


def register_fonts() -> None:
    from dossier_theme import FONT_DIR

    for name, filename in _FILES.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))
    registerFontFamily("DSans", normal="DSans", bold="DSansSB", italic="DSansI", boldItalic="DSansSB")
    registerFontFamily("DSerif", normal="DSerif", bold="DSerifB", italic="DSerifI", boldItalic="DSerifB")


# ── Markup ──────────────────────────────────────────────────────────
_BOLD = {"sans": "sans-semibold", "sans-light": "sans-semibold", "sans-semilight": "sans-semibold",
         "serif": "serif-bold", "serif-italic": "serif-bold", "sans-semibold": "sans-bold",
         "serif-bold": "serif-bold", "sans-bold": "sans-bold", "mono": "mono-bold"}
_ITALIC = {"sans": "sans-italic", "sans-light": "sans-italic", "sans-semilight": "sans-italic",
           "serif": "serif-italic", "serif-bold": "serif-italic"}


def _chunks_xml(fragment: str, key: str) -> str:
    """Escape a fragment set in ``key``, routing glyphs it lacks to Segoe UI Symbol."""
    out = []
    for chunk, font in split_fallback(fragment, key):
        LEDGER.check(chunk, font)
        out.append(f'<font name="{RL[font]}">{escape(chunk)}</font>')
    return "".join(out)


def xml(text: str, base: str, size: float, code_color: str = "copper_deep") -> str:
    out = []
    for fragment, kind in runs(text):
        if kind == "code":
            out.append(f'<font size="{size * 0.9:.2f}" color="{PALETTE[code_color]}">'
                       f'{_chunks_xml(fragment, "mono")}</font>')
        elif kind == "bold":
            out.append(_chunks_xml(fragment, _BOLD.get(base, base)))
        elif kind == "italic":
            out.append(_chunks_xml(fragment, _ITALIC.get(base, base)))
        else:
            out.append(_chunks_xml(fragment, base))
    return "".join(out)


def style(name: str, font: str, size: float, leading: float, color_name: str = "ink", **kw) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=RL[font], fontSize=size, leading=leading,
                          textColor=c(color_name), splitLongWords=1, **kw)


def para(text: str, st: ParagraphStyle, font: str, code_color: str = "copper_deep") -> Paragraph:
    return Paragraph(xml(text, font, st.fontSize, code_color), st)


class Styles:
    def __init__(self) -> None:
        self.lede = style("lede", "sans-semilight", 12.2, 17.8, "ink2", spaceAfter=9)
        self.body = style("body", "sans", 10.2, 15.8, "ink", spaceAfter=8)
        self.small = style("small", "sans", 8.4, 12.0, "ink2")
        self.card_title = style("card_title", "sans-semibold", 10.2, 13.6, "ink")
        self.card_text = style("card_text", "sans", 9.1, 13.0, "ink2")
        self.cell = style("cell", "sans", 8.4, 11.6, "ink")
        self.cell_head = style("cell_head", "sans-semibold", 8.2, 11.0, "ivory")
        self.cell_first = style("cell_first", "sans-semibold", 8.4, 11.6, "ink")
        self.h1 = style("h1", "serif", 23, 27.5, "ink", spaceAfter=4)
        self.toc0 = style("toc0", "serif", 12.5, 20, "ink", leftIndent=0)
        self.toc1 = style("toc1", "sans", 8.8, 13.4, "ink2", leftIndent=22)


# ── Canvas helpers ──────────────────────────────────────────────────
def text_width(text: str, font: str, size: float, space: float = 0.0) -> float:
    width = sum(stringWidth(chunk, RL[key], size) for chunk, key in split_fallback(text, font))
    return width + space * max(0, len(text) - 1)


def draw_text(canv, x: float, y: float, text: str, font: str, size: float, color_name: str,
              space: float = 0.0, anchor: str = "left", alpha: float | None = None) -> float:
    width = text_width(text, font, size, space)
    if anchor == "center":
        x -= width / 2
    elif anchor == "right":
        x -= width
    canv.saveState()
    canv.setFillColor(c(color_name, alpha))
    for chunk, key in split_fallback(text, font):
        LEDGER.check(chunk, key)
        canv.setFont(RL[key], size)
        canv.drawString(x, y, chunk, charSpace=space)
        x += stringWidth(chunk, RL[key], size) + space * len(chunk)
    canv.restoreState()
    return width


def rounded(canv, x, y, w, h, r, fill=None, stroke=None, width=0.6, fill_alpha=None, stroke_alpha=None):
    canv.saveState()
    if fill:
        canv.setFillColor(c(fill, fill_alpha))
    if stroke:
        canv.setStrokeColor(c(stroke, stroke_alpha))
        canv.setLineWidth(width)
    canv.roundRect(x, y, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)
    canv.restoreState()


def diamond(canv, cx, cy, r, fill=None, stroke=None, width=0.8):
    canv.saveState()
    path = canv.beginPath()
    path.moveTo(cx, cy + r)
    path.lineTo(cx + r, cy)
    path.lineTo(cx, cy - r)
    path.lineTo(cx - r, cy)
    path.close()
    if fill:
        canv.setFillColor(c(fill))
    if stroke:
        canv.setStrokeColor(c(stroke))
        canv.setLineWidth(width)
    canv.drawPath(path, stroke=1 if stroke else 0, fill=1 if fill else 0)
    canv.restoreState()


def arrow(canv, x1, y1, x2, y2, color_name="copper", width=1.0, head=4.0):
    canv.saveState()
    canv.setStrokeColor(c(color_name))
    canv.setFillColor(c(color_name))
    canv.setLineWidth(width)
    canv.line(x1, y1, x2, y2)
    angle = math.atan2(y2 - y1, x2 - x1)
    path = canv.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(x2 - head * math.cos(angle - 0.45), y2 - head * math.sin(angle - 0.45))
    path.lineTo(x2 - head * math.cos(angle + 0.45), y2 - head * math.sin(angle + 0.45))
    path.close()
    canv.drawPath(path, stroke=0, fill=1)
    canv.restoreState()


def stepfret(canv, x, y, length, unit, color_name, width=0.8, alpha=1.0):
    canv.saveState()
    canv.setStrokeColor(c(color_name, alpha))
    canv.setLineWidth(width)
    path = canv.beginPath()
    pos = 0.0
    path.moveTo(x, y)
    while pos <= length - 6 * unit:
        for step in range(3):
            path.lineTo(x + pos + step * unit, y + (step + 1) * unit)
            path.lineTo(x + pos + (step + 1) * unit, y + (step + 1) * unit)
        pos += 3 * unit
        for step in range(3):
            path.lineTo(x + pos + step * unit, y + (2 - step) * unit)
            path.lineTo(x + pos + (step + 1) * unit, y + (2 - step) * unit)
        pos += 3 * unit
    canv.drawPath(path, stroke=1, fill=0)
    canv.restoreState()


def sunstone(canv, cx, cy, radius, line="jade", accent="copper", alpha=0.5):
    canv.saveState()
    canv.setStrokeColor(c(line, alpha))
    for k, lw in ((1.0, 1.1), (0.93, 0.5), (0.78, 1.0), (0.70, 0.45), (0.52, 0.45), (0.34, 0.9)):
        canv.setLineWidth(lw)
        canv.circle(cx, cy, radius * k, stroke=1, fill=0)
    canv.setLineWidth(0.45)
    for i in range(80):
        angle = math.tau * i / 80
        inner = radius * (0.93 if i % 4 else 0.86)
        canv.line(cx + inner * math.cos(angle), cy + inner * math.sin(angle),
                  cx + radius * math.cos(angle), cy + radius * math.sin(angle))
    canv.setStrokeColor(c(accent, alpha))
    canv.setLineWidth(0.6)
    for i in range(20):
        angle = math.tau * i / 20 + math.pi / 2
        bx, by = cx + radius * 0.74 * math.cos(angle), cy + radius * 0.74 * math.sin(angle)
        bead = radius * 0.026
        canv.rect(bx - bead, by - bead, 2 * bead, 2 * bead, stroke=1, fill=0)
    for i in range(8):
        angle = math.tau * i / 8 + math.pi / 2
        tip, base, spread = radius * 0.50, radius * 0.36, math.tau / 32
        path = canv.beginPath()
        path.moveTo(cx + tip * math.cos(angle), cy + tip * math.sin(angle))
        path.lineTo(cx + base * math.cos(angle - spread), cy + base * math.sin(angle - spread))
        path.lineTo(cx + base * math.cos(angle + spread), cy + base * math.sin(angle + spread))
        path.close()
        canv.drawPath(path, stroke=1, fill=0)
    canv.restoreState()


def night_sky(canv, seed: int, glow_at=(0.3, 0.6), glow_color="jade") -> None:
    canv.saveState()
    canv.linearGradient(0, H, 0, 0, (c("#060A0C"), c("#0D191C")), extend=True)
    gx, gy = W * glow_at[0], H * glow_at[1]
    for i in range(34, 0, -1):
        canv.setFillColor(c(glow_color, 0.012))
        canv.circle(gx, gy, 12 + i * 11, stroke=0, fill=1)
    rng = random.Random(seed)
    for _ in range(260):
        level = rng.random()
        canv.setFillColor(c(rng.choice(["light", "jade", "gold"]), 0.15 + level * 0.55))
        canv.circle(rng.random() * W, rng.random() * H, 0.25 + level * 0.8, stroke=0, fill=1)
    canv.restoreState()


# ── Page templates ──────────────────────────────────────────────────
class DossierDoc(BaseDocTemplate):
    def __init__(self, filename, facts: dict):
        super().__init__(
            filename, pagesize=A4, leftMargin=ML, rightMargin=MR, topMargin=MT, bottomMargin=MB,
            title="Tlamatini — Complete Project Dossier",
            author="Angela López Mendoza",
            subject=f"Tlamatini {facts['version']}: what she is, how she works, how to use her, and the "
                    f"complete repository inventory",
            creator="Tlamatini dossier generator (refresh_project_docs.py)",
            keywords="Tlamatini, AI developer assistant, agents, Multi-Turn, ACPX, MCP, workflow designer")
        self.facts = facts
        full = Frame(0, 0, W, H, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="full")
        body = Frame(ML, MB, FRAME_W, H - MT - MB, leftPadding=0, rightPadding=0, topPadding=0,
                     bottomPadding=0, id="body")
        self.addPageTemplates([
            PageTemplate("cover", [full], onPage=self._dark),
            PageTemplate("dark", [full], onPage=self._dark),
            PageTemplate("body", [body], onPage=self._paper, onPageEnd=self._chrome),
        ])
        self.chapter_label = ""

    def _dark(self, canv, doc):
        night_sky(canv, doc.page, glow_at=(0.5, 0.64) if doc.page == 1 else (0.86, 0.62))

    def _paper(self, canv, doc):
        canv.saveState()
        canv.setFillColor(c("ivory"))
        canv.rect(0, 0, W, H, stroke=0, fill=1)
        canv.setFillColor(c("parchment", 0.55))
        canv.rect(0, H - 40, W, 40, stroke=0, fill=1)
        canv.restoreState()
        stepfret(canv, ML, H - 30, FRAME_W, 2.2, "copper", 0.5, 0.45)

    def _chrome(self, canv, doc):
        label = getattr(canv, "_dossier_chapter", "")
        draw_text(canv, ML, H - 58, "TLAMATINI", "sans-semibold", 7.2, "copper_deep", space=1.8)
        if label:
            draw_text(canv, ML + 64, H - 58, "·  " + label.upper(), "sans", 7.0, "muted", space=1.0)
        draw_text(canv, W - MR, H - 58, "COMPLETE PROJECT DOSSIER", "sans", 7.0, "muted", space=1.0,
                  anchor="right")
        canv.saveState()
        canv.setStrokeColor(c("rule"))
        canv.setLineWidth(0.6)
        canv.line(ML, H - 64, W - MR, H - 64)
        canv.line(ML, 44, W - MR, 44)
        canv.restoreState()
        diamond(canv, W / 2, 30, 11, fill="ivory", stroke="copper", width=0.8)
        draw_text(canv, W / 2, 27.4, str(doc.page), "sans-semibold", 7.6, "copper_deep", anchor="center")
        draw_text(canv, ML, 27.4, f"Version {self.facts['version']}  ·  {self.facts['generated_date']}",
                  "sans", 7.0, "muted")
        draw_text(canv, W - MR, 27.4, "github.com/XAIHT/Tlamatini", "sans", 7.0, "muted", anchor="right")

    def afterFlowable(self, flowable):
        toc = getattr(flowable, "_toc", None)
        if toc:
            level, text, key = toc
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=(level == 0))
            self.notify("TOCEntry", (level, text, self.page, key))


# ── Flowables ───────────────────────────────────────────────────────
class ChapterMarker(Flowable):
    def __init__(self, label: str):
        super().__init__()
        self.label = label

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        self.canv._dossier_chapter = self.label


class Anchor(Flowable):
    """A zero-height flowable that registers a TOC entry and a PDF bookmark."""

    def __init__(self, level: int, text: str, key: str):
        super().__init__()
        self._toc = (level, text, key)

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        pass


class Kicker(Flowable):
    def __init__(self, text: str, color_name: str = "copper_deep"):
        super().__init__()
        self.text = text
        self.color_name = color_name

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 13

    def draw(self):
        diamond(self.canv, 3, 4.2, 3, fill=self.color_name)
        draw_text(self.canv, 12, 1.6, self.text, "sans-semibold", 7.4, self.color_name, space=1.6)


class TitleRule(Flowable):
    def __init__(self, color_name="jade", length=46):
        super().__init__()
        self.color_name = color_name
        self.length = length

    def wrap(self, aw, ah):
        return aw, 9

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setStrokeColor(c(self.color_name))
        canv.setLineWidth(2.2)
        canv.line(0, 5, self.length, 5)
        canv.setStrokeColor(c("rule"))
        canv.setLineWidth(0.6)
        canv.line(self.length + 6, 5, self.length + 90, 5)
        canv.restoreState()


class CardGrid(Flowable):
    def __init__(self, cards, st: Styles, cols=2, accent="jade", gap=10, pad=10, title_font="sans-semibold",
                 title_style=None, compact=False):
        super().__init__()
        self.cards = cards
        self.st = st
        self.cols = cols
        self.accent = accent
        self.gap = gap
        self.pad = pad
        self.title_font = title_font
        self.title_style = title_style or st.card_title
        self.compact = compact
        self._rows = None

    def _layout(self, aw):
        col_w = (aw - self.gap * (self.cols - 1)) / self.cols
        inner = col_w - 2 * self.pad - 4
        rows = []
        for start in range(0, len(self.cards), self.cols):
            chunk = self.cards[start:start + self.cols]
            built = []
            for title, text, *rest in chunk:
                tp = para(title, self.title_style, self.title_font)
                bp = para(text, self.st.card_text, "sans")
                th = tp.wrap(inner, 10000)[1]
                bh = bp.wrap(inner, 10000)[1]
                built.append((tp, th, bp, bh, rest[0] if rest else self.accent))
            height = max(th + bh for _, th, _, bh, _ in built) + 2 * self.pad + (3 if self.compact else 5)
            rows.append((built, height))
        return col_w, rows

    def wrap(self, aw, ah):
        self.aw = aw
        self.col_w, self._rows = self._layout(aw)
        self.height = sum(h for _, h in self._rows) + self.gap * (len(self._rows) - 1)
        return aw, self.height

    def split(self, aw, ah):
        col_w, rows = self._layout(aw)
        used, count = 0.0, 0
        for _, h in rows:
            if used + h > ah:
                break
            used += h + self.gap
            count += 1
        if count == 0 or count == len(rows):
            return []
        first = CardGrid(self.cards[:count * self.cols], self.st, self.cols, self.accent, self.gap, self.pad,
                         self.title_font, self.title_style, self.compact)
        rest = CardGrid(self.cards[count * self.cols:], self.st, self.cols, self.accent, self.gap, self.pad,
                        self.title_font, self.title_style, self.compact)
        return [first, rest]

    def draw(self):
        canv = self.canv
        y = self.height
        for built, h in self._rows:
            y -= h
            for index, (tp, th, bp, bh, accent) in enumerate(built):
                x = index * (self.col_w + self.gap)
                rounded(canv, x, y, self.col_w, h, 5, fill="paper", stroke="rule", width=0.6)
                canv.saveState()
                canv.setFillColor(c(accent))
                canv.rect(x, y + 6, 2.6, h - 12, stroke=0, fill=1)
                canv.restoreState()
                top = y + h - self.pad
                tp.drawOn(canv, x + self.pad + 4, top - th)
                bp.drawOn(canv, x + self.pad + 4, top - th - (2 if self.compact else 3) - bh)
            y -= self.gap


class Callout(Flowable):
    def __init__(self, title, text, st: Styles, tone="jade"):
        super().__init__()
        self.title, self.text, self.st, self.tone = title, text, st, tone

    def wrap(self, aw, ah):
        self.aw = aw
        inner = aw - 34
        self.tp = para(self.title, style("co_t", "sans-semibold", 9.4, 12.6, self.tone + "_deep"
                                         if self.tone in ("jade", "copper") else "ink"), "sans-semibold")
        self.bp = para(self.text, style("co_b", "sans", 9.8, 14.4, "ink"), "sans")
        self.th = self.tp.wrap(inner, 10000)[1]
        self.bh = self.bp.wrap(inner, 10000)[1]
        self.height = self.th + self.bh + 24
        return aw, self.height

    def draw(self):
        canv = self.canv
        pale = {"jade": "jade_pale", "copper": "copper_pale", "gold": "gold_pale", "rose": "rose_pale"}
        rounded(canv, 0, 0, self.aw, self.height, 6, fill=pale.get(self.tone, "jade_pale"))
        canv.saveState()
        canv.setFillColor(c(self.tone))
        canv.rect(0, 0, 4, self.height, stroke=0, fill=1)
        canv.restoreState()
        diamond(canv, 16, self.height - 15.5, 3.2, fill=self.tone)
        self.tp.drawOn(canv, 26, self.height - 11 - self.th)
        self.bp.drawOn(canv, 26, self.height - 14 - self.th - self.bh)


class CodeBlock(Flowable):
    def __init__(self, code: str, size=7.8):
        super().__init__()
        self.lines = code.splitlines()
        self.size = size
        for line in self.lines:
            LEDGER.check(line, "mono")

    def wrap(self, aw, ah):
        self.aw = aw
        self.lead = self.size * 1.42
        widest = max(stringWidth(line, RL["mono"], self.size) for line in self.lines)
        if widest > aw - 28:
            raise RuntimeError(f"Code line wider than its block: {widest:.1f} > {aw - 28:.1f}")
        self.height = len(self.lines) * self.lead + 20
        return aw, self.height

    def draw(self):
        canv = self.canv
        rounded(canv, 0, 0, self.aw, self.height, 6, fill="night")
        for dot, tone in enumerate(("rose", "gold", "jade")):
            canv.saveState()
            canv.setFillColor(c(tone, 0.8))
            canv.circle(12 + dot * 9, self.height - 9, 2.2, stroke=0, fill=1)
            canv.restoreState()
        y = self.height - 20 - self.size * 0.2
        for line in self.lines:
            tone = "light_muted" if line.lstrip().startswith("#") else "light"
            if line.startswith("INI_SECTION") or line.startswith(">>>END"):
                tone = "gold"
            draw_text(canv, 14, y - self.size * 0.55, line, "mono", self.size, tone)
            y -= self.lead


def styled_table(columns, rows, ratios, st: Styles, align=None):
    widths = [FRAME_W * ratio for ratio in ratios]
    align = align or ["LEFT"] * len(columns)
    head_cells = [para(text, style(f"th{i}", "sans-semibold", 8.6, 11.6, "ivory",
                                   alignment=TA_LEFT if align[i] == "LEFT" else 2), "sans-semibold")
                  for i, text in enumerate(columns)]
    body = []
    for r_index, row in enumerate(rows):
        total_row = str(row[0]).strip().lower() == "total"
        cells = []
        for i, text in enumerate(row):
            font = "sans-semibold" if (i == 0 or total_row) else "sans"
            cst = style(f"td{i}", font, 8.9, 12.6, "ink",
                        alignment=TA_LEFT if align[i] == "LEFT" else 2)
            cells.append(para(str(text), cst, font))
        body.append(cells)
    table = Table([head_cells] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), c("stone")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.2),
        ("LINEBELOW", (0, 0), (-1, 0), 1.4, c("copper")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, c("rule")),
    ]
    for index in range(1, len(body) + 1):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), c("parchment", 0.45)))
        else:
            commands.append(("BACKGROUND", (0, index), (-1, index), c("paper")))
    if rows and str(rows[-1][0]).strip().lower() == "total":
        commands.append(("BACKGROUND", (0, len(body)), (-1, len(body)), c("jade_pale")))
        commands.append(("LINEABOVE", (0, len(body)), (-1, len(body)), 1.0, c("jade")))
    table.setStyle(TableStyle(commands))
    return table


class Planes(Flowable):
    SPEC = [
        ("jade", "Local control plane", "Your machine",
         ["Django, Channels and Daphne", "Chat, canvases and dialogs", "SQLite database and settings",
          "Agent programs and permissions", "Files, tools and hardware"]),
        ("gold", "Local retrieval", "Your machine",
         ["nomic-embed-text embeddings", "FAISS vectors and BM25 keywords", "Context budgeting",
          "Binary-content guard"]),
        ("copper", "Cloud reasoning", "Ollama cloud models",
         ["Chat and tool calling", "Long context", "Vision observers and mergers",
          "Multi-Turn planning"]),
    ]

    def wrap(self, aw, ah):
        self.aw = aw
        self.height = 176
        return aw, self.height

    def draw(self):
        canv = self.canv
        gap = 22
        col_w = (self.aw - 2 * gap) / 3
        for index, (tone, title, place, items) in enumerate(self.SPEC):
            x = index * (col_w + gap)
            rounded(canv, x, 18, col_w, self.height - 18, 7, fill="paper", stroke="rule")
            canv.saveState()
            canv.setFillColor(c(tone))
            canv.roundRect(x, self.height - 34, col_w, 34, 7, stroke=0, fill=1)
            canv.rect(x, self.height - 34, col_w, 10, stroke=0, fill=1)
            canv.restoreState()
            draw_text(canv, x + 10, self.height - 21, title, "sans-semibold", 10.2, "white")
            y = self.height - 52
            for item in items:
                diamond(canv, x + 13, y + 3.2, 2.2, fill=tone)
                draw_text(canv, x + 21, y, item, "sans", 8.3, "ink")
                y -= 16
            draw_text(canv, x + col_w / 2, 4, place.upper(), "sans-semibold", 6.8, tone + "_deep"
                      if tone in ("jade", "copper") else "copper_deep", space=1.2, anchor="center")
            if index < 2:
                ax = x + col_w + 3
                arrow(canv, ax, self.height / 2 + 12, ax + gap - 6, self.height / 2 + 12, "copper", 0.9)
                arrow(canv, ax + gap - 6, self.height / 2 + 2, ax, self.height / 2 + 2, "jade", 0.9)


class LayerStack(Flowable):
    def __init__(self, layers, st: Styles):
        super().__init__()
        self.layers, self.st = layers, st

    def wrap(self, aw, ah):
        self.aw = aw
        self.inner = aw - 150
        self.built = []
        for title, text in self.layers:
            p = para(text, self.st.card_text, "sans")
            self.built.append((title, p, p.wrap(self.inner, 1000)[1]))
        self.row_h = [max(30, h + 14) for _, _, h in self.built]
        self.height = 30 + sum(self.row_h) + 6 * (len(self.row_h) - 1) + 30 + 16
        return aw, self.height

    def draw(self):
        canv = self.canv
        top = self.height
        rounded(canv, 0, top - 26, self.aw, 26, 5, fill="stone")
        draw_text(canv, 12, top - 17, "BROWSER", "sans-semibold", 7.4, "gold", space=1.4)
        draw_text(canv, 90, top - 17, "Chat page  ·  Agentic Control Panel  ·  Prompt Flow Panel  "
                  "·  WebSockets", "sans", 8.4, "light")
        y = top - 34
        tones = ["jade", "gold", "copper", "cyan", "magenta"]
        for index, ((title, p, h), row_h) in enumerate(zip(self.built, self.row_h)):
            y -= row_h
            tone = tones[index % len(tones)]
            rounded(canv, 0, y, self.aw, row_h, 5, fill="paper", stroke="rule")
            canv.saveState()
            canv.setFillColor(c(tone))
            canv.roundRect(0, y, 30, row_h, 5, stroke=0, fill=1)
            canv.rect(20, y, 10, row_h, stroke=0, fill=1)
            canv.restoreState()
            draw_text(canv, 15, y + row_h / 2 - 3.5, str(index + 1), "serif-bold", 11, "white", anchor="center")
            draw_text(canv, 40, y + row_h / 2 - 3.2, title, "sans-semibold", 9.2, "ink")
            p.drawOn(canv, 142, y + (row_h - h) / 2)
            y -= 6
        y += 6
        y -= 30
        rounded(canv, 0, y, self.aw, 26, 5, fill="stone")
        draw_text(canv, 12, y + 9, "MODELS", "sans-semibold", 7.4, "gold", space=1.4)
        draw_text(canv, 90, y + 9, "Ollama (local and cloud)  ·  Anthropic Claude  ·  Qwen vision",
                  "sans", 8.4, "light")


class StepGrid(Flowable):
    def __init__(self, steps, st: Styles, cols=3):
        super().__init__()
        self.steps, self.st, self.cols = steps, st, cols

    def wrap(self, aw, ah):
        self.aw = aw
        self.gap = 14
        self.col_w = (aw - self.gap * (self.cols - 1)) / self.cols
        inner = self.col_w - 44
        self.cells = []
        for title, text in self.steps:
            p = para(text, self.st.card_text, "sans")
            self.cells.append((title, p, p.wrap(inner, 1000)[1]))
        self.rows = []
        for start in range(0, len(self.cells), self.cols):
            chunk = self.cells[start:start + self.cols]
            self.rows.append(max(h for _, _, h in chunk) + 34)
        self.height = sum(self.rows) + 12 * (len(self.rows) - 1)
        return aw, self.height

    def draw(self):
        canv = self.canv
        y = self.height
        number = 0
        for r_index, row_h in enumerate(self.rows):
            y -= row_h
            for col in range(self.cols):
                idx = r_index * self.cols + col
                if idx >= len(self.cells):
                    break
                title, p, h = self.cells[idx]
                number += 1
                x = col * (self.col_w + self.gap)
                rounded(canv, x, y, self.col_w, row_h, 6, fill="paper", stroke="rule")
                canv.saveState()
                canv.setFillColor(c("stone"))
                canv.circle(x + 18, y + row_h - 17, 10, stroke=0, fill=1)
                canv.restoreState()
                draw_text(canv, x + 18, y + row_h - 20.6, str(number), "serif-bold", 10, "gold", anchor="center")
                draw_text(canv, x + 34, y + row_h - 21, title, "sans-semibold", 9.6, "ink")
                p.drawOn(canv, x + 34, y + row_h - 28 - h)
                if col < self.cols - 1 and idx + 1 < len(self.cells):
                    arrow(canv, x + self.col_w + 2, y + row_h - 17, x + self.col_w + self.gap - 2,
                          y + row_h - 17, "copper", 0.9, 3.2)
            y -= 12


class Ladder(Flowable):
    def __init__(self, rungs, st: Styles, tone="jade"):
        super().__init__()
        self.rungs, self.st, self.tone = rungs, st, tone

    def wrap(self, aw, ah):
        self.aw = aw
        inner = aw - 170
        self.built = []
        for num, name, text in self.rungs:
            p = para(text, self.st.card_text, "sans")
            self.built.append((num, name, p, p.wrap(inner, 1000)[1]))
        self.row_h = [max(24, h + 10) for *_, h in self.built]
        self.height = sum(self.row_h) + 5 * (len(self.row_h) - 1)
        return aw, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setStrokeColor(c(self.tone))
        canv.setLineWidth(1.6)
        canv.line(14, 8, 14, self.height - 8)
        canv.restoreState()
        y = self.height
        for (num, name, p, h), row_h in zip(self.built, self.row_h):
            y -= row_h
            rounded(canv, 34, y, self.aw - 34, row_h, 4, fill="paper", stroke="rule")
            canv.saveState()
            canv.setFillColor(c("stone"))
            canv.circle(14, y + row_h / 2, 10, stroke=0, fill=1)
            canv.restoreState()
            draw_text(canv, 14, y + row_h / 2 - 3.4, num, "serif-bold", 9.6, "gold", anchor="center")
            draw_text(canv, 46, y + row_h / 2 - 3.2, name, "mono-bold", 8.8, self.tone + "_deep"
                      if self.tone in ("jade", "copper") else "ink")
            p.drawOn(canv, 170, y + (row_h - h) / 2)
            y -= 5


class Cascade(Flowable):
    def __init__(self, stages):
        super().__init__()
        self.stages = stages

    def wrap(self, aw, ah):
        self.aw = aw
        self.height = 118
        return aw, self.height

    def draw(self):
        canv = self.canv
        per_row = 4
        gap = 12
        box_w = (self.aw - gap * (per_row - 1)) / per_row
        box_h = 44
        for index, (name, note) in enumerate(self.stages):
            row, col = divmod(index, per_row)
            x = col * (box_w + gap)
            y = self.height - (row + 1) * box_h - row * 22
            tone = "jade" if name in ("BOM", "Empty") else ("copper" if index in (0, 4, 5, 6, 7) else "gold")
            rounded(canv, x, y, box_w, box_h, 5, fill="paper", stroke=tone, width=0.9)
            draw_text(canv, x + 8, y + box_h - 15, f"{index + 1}  {name}", "sans-semibold", 8.8, "ink")
            draw_text(canv, x + 8, y + 9, note, "sans", 7.4, "ink2")
            if col < per_row - 1:
                arrow(canv, x + box_w + 1, y + box_h / 2, x + box_w + gap - 1, y + box_h / 2, "copper", 0.8, 3)
        draw_text(canv, 0, 1, "Copper stages can drop a binary file; jade stages can only keep a file as text. "
                  "Any doubt keeps the file.", "sans-italic", 7.6, "ink2")


def _glyph(canv, kind, x, y, w, h, tone):
    canv.saveState()
    canv.setStrokeColor(c(tone))
    canv.setFillColor(c(tone, 0.14))
    canv.setLineWidth(1.3)
    path = canv.beginPath()
    if kind in ("prompt", "programmed"):
        canv.roundRect(x, y, w, h, 3, stroke=1, fill=1)
        if kind == "programmed":
            canv.setFillColor(c("paper"))
            canv.circle(x + w - 7, y + h - 7, 5.2, stroke=1, fill=1)
            canv.line(x + w - 7, y + h - 7, x + w - 7, y + h - 4)
            canv.line(x + w - 7, y + h - 7, x + w - 5, y + h - 8)
    elif kind == "decision":
        path.moveTo(x + w / 2, y + h)
        path.lineTo(x + w, y + h / 2)
        path.lineTo(x + w / 2, y)
        path.lineTo(x, y + h / 2)
        path.close()
        canv.drawPath(path, stroke=1, fill=1)
    elif kind == "feed":
        path.moveTo(x + w / 2, y + h)
        path.lineTo(x + w, y)
        path.lineTo(x, y)
        path.close()
        canv.drawPath(path, stroke=1, fill=1)
    elif kind == "flush":
        path.moveTo(x, y + h)
        path.lineTo(x + w, y + h)
        path.lineTo(x + w / 2, y)
        path.close()
        canv.drawPath(path, stroke=1, fill=1)
    elif kind == "clean":
        path.moveTo(x + w * 0.2, y + h)
        path.lineTo(x + w * 0.8, y + h)
        path.lineTo(x + w, y)
        path.lineTo(x, y)
        path.close()
        canv.drawPath(path, stroke=1, fill=1)
    elif kind == "input":
        # The panel's notched figure: a V-notch on top, straight sides, a point below.
        fw = h * 0.8
        x0 = x + (w - fw) / 2
        points = [(0, 0), (0.5, 0.283), (1, 0), (1, 0.7), (0.5, 1), (0, 0.7)]
        path.moveTo(x0, y + h)
        for nx, ny in points[1:]:
            path.lineTo(x0 + nx * fw, y + h - ny * h)
        path.close()
        canv.drawPath(path, stroke=1, fill=1)
    elif kind == "commentary":
        canv.roundRect(x, y + h * 0.25, w, h * 0.75, 6, stroke=1, fill=1)
        path.moveTo(x + w * 0.25, y + h * 0.26)
        path.lineTo(x + w * 0.18, y)
        path.lineTo(x + w * 0.42, y + h * 0.26)
        canv.drawPath(path, stroke=1, fill=0)
    canv.restoreState()


class Operations(Flowable):
    TONES = {"prompt": "jade", "programmed": "jade", "decision": "gold", "feed": "cyan", "flush": "cyan",
             "clean": "copper", "input": "magenta", "commentary": "rose"}

    def __init__(self, ops, st: Styles):
        super().__init__()
        self.ops, self.st = ops, st

    def wrap(self, aw, ah):
        self.aw = aw
        self.gap = 12
        self.col_w = (aw - self.gap) / 2
        inner = self.col_w - 78
        self.cells = []
        for kind, name, text in self.ops:
            p = para(text, self.st.card_text, "sans")
            self.cells.append((kind, name, p, p.wrap(inner, 1000)[1]))
        self.rows = []
        for start in range(0, len(self.cells), 2):
            chunk = self.cells[start:start + 2]
            self.rows.append(max(56, max(h for *_, h in chunk) + 30))
        self.height = sum(self.rows) + 10 * (len(self.rows) - 1)
        return aw, self.height

    def draw(self):
        canv = self.canv
        y = self.height
        for r_index, row_h in enumerate(self.rows):
            y -= row_h
            for col in range(2):
                idx = r_index * 2 + col
                if idx >= len(self.cells):
                    break
                kind, name, p, h = self.cells[idx]
                x = col * (self.col_w + self.gap)
                tone = self.TONES[kind]
                rounded(canv, x, y, self.col_w, row_h, 6, fill="paper", stroke="rule")
                _glyph(canv, kind, x + 12, y + row_h / 2 - 16, 46, 32, tone)
                draw_text(canv, x + 70, y + row_h - 20, name, "sans-semibold", 9.6, "ink")
                p.drawOn(canv, x + 70, y + row_h - 26 - h)
            y -= 10


class MetricGrid(Flowable):
    def __init__(self, metrics, cols=4):
        super().__init__()
        self.metrics, self.cols = metrics, cols

    def wrap(self, aw, ah):
        self.aw = aw
        rows = math.ceil(len(self.metrics) / self.cols)
        self.tile_h = 72
        self.gap = 10
        self.height = rows * self.tile_h + (rows - 1) * self.gap
        return aw, self.height

    def draw(self):
        canv = self.canv
        tile_w = (self.aw - self.gap * (self.cols - 1)) / self.cols
        tones = ["jade", "copper", "gold", "cyan", "magenta", "rose", "jade", "copper"]
        for index, (value, label) in enumerate(self.metrics):
            row, col = divmod(index, self.cols)
            x = col * (tile_w + self.gap)
            y = self.height - (row + 1) * self.tile_h - row * self.gap
            tone = tones[index % len(tones)]
            rounded(canv, x, y, tile_w, self.tile_h, 7, fill="stone")
            canv.saveState()
            canv.setFillColor(c(tone))
            canv.rect(x + 12, y + self.tile_h - 5, 26, 2.4, stroke=0, fill=1)
            canv.restoreState()
            size = 25 if text_width(value, "serif-bold", 25) < tile_w - 24 else 19
            draw_text(canv, x + 12, y + 30, value, "serif-bold", size, "ivory")
            draw_text(canv, x + 12, y + 13, label.upper(), "sans-semibold", 6.8, tone, space=1.1)


class Chain(Flowable):
    def __init__(self, items, caption=""):
        super().__init__()
        self.items, self.caption = items, caption

    def wrap(self, aw, ah):
        self.aw = aw
        self.height = 58 if self.caption else 40
        return aw, self.height

    def draw(self):
        canv = self.canv
        gap = 14
        n = len(self.items)
        box_w = (self.aw - gap * (n - 1)) / n
        y = self.height - 34
        for index, name in enumerate(self.items):
            x = index * (box_w + gap)
            tone = "jade" if index in (0, n - 1) else "stone"
            rounded(canv, x, y, box_w, 30, 15, fill=tone)
            size = 8.8
            while text_width(name, "sans-semibold", size) > box_w - 12 and size > 6:
                size -= 0.2
            draw_text(canv, x + box_w / 2, y + 11.5, name, "sans-semibold", size,
                      "white" if tone == "jade" else "gold", anchor="center")
            if index < n - 1:
                arrow(canv, x + box_w + 2, y + 15, x + box_w + gap - 2, y + 15, "copper", 1.0, 3.4)
        if self.caption:
            draw_text(canv, 0, 4, self.caption, "sans-italic", 8, "ink2")


class Timeline(Flowable):
    def __init__(self, rows, st: Styles):
        super().__init__()
        self.rows, self.st = rows, st

    def wrap(self, aw, ah):
        self.aw = aw
        inner = aw - 176
        self.built = []
        for row in self.rows:
            p = para(row["subject"], self.st.card_text, "sans")
            self.built.append((row, p, p.wrap(inner, 1000)[1]))
        self.row_h = [max(22, h + 9) for *_, h in self.built]
        self.height = sum(self.row_h)
        return aw, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setStrokeColor(c("copper"))
        canv.setLineWidth(1.2)
        canv.line(86, 4, 86, self.height - 4)
        canv.restoreState()
        y = self.height
        for index, ((row, p, h), row_h) in enumerate(zip(self.built, self.row_h)):
            y -= row_h
            mid = y + row_h / 2
            last = index == len(self.built) - 1
            draw_text(canv, 0, mid - 3, row["date"], "mono", 8, "muted")
            diamond(canv, 86, mid, 5 if last else 3.6, fill="jade" if last else "copper")
            draw_text(canv, 100, mid - 3.4, row["tag"], "serif-bold", 10, "ink")
            p.drawOn(canv, 170, y + (row_h - h) / 2)


class BarChart(Flowable):
    def __init__(self, rows, unit="", label_w=128):
        super().__init__()
        self.rows, self.unit, self.label_w = rows, unit, label_w

    def wrap(self, aw, ah):
        self.aw = aw
        self.height = len(self.rows) * 19 + 4
        return aw, self.height

    def draw(self):
        canv = self.canv
        peak = max(value for _, value in self.rows) or 1
        track = self.aw - self.label_w - 70
        tones = ["jade", "copper", "gold", "cyan", "magenta", "rose"]
        y = self.height - 17
        for index, (label, value) in enumerate(self.rows):
            draw_text(canv, 0, y + 3.5, label, "sans", 8.4, "ink")
            length = max(1.5, track * value / peak)
            rounded(canv, self.label_w, y + 1, track, 11, 3, fill="parchment", fill_alpha=0.6)
            rounded(canv, self.label_w, y + 1, length, 11, 3, fill=tones[index % len(tones)])
            draw_text(canv, self.label_w + track + 8, y + 3.5, f"{value:,}{self.unit}", "sans-semibold", 8.4,
                      "ink")
            y -= 19


class FamilyTiles(Flowable):
    def __init__(self, families):
        super().__init__()
        self.families = families

    def wrap(self, aw, ah):
        self.aw = aw
        self.cols = 4
        self.tile_h = 58
        self.gap = 9
        rows = math.ceil(len(self.families) / self.cols)
        self.height = rows * self.tile_h + (rows - 1) * self.gap
        return aw, self.height

    def draw(self):
        canv = self.canv
        tile_w = (self.aw - self.gap * (self.cols - 1)) / self.cols
        for index, (name, tone, count) in enumerate(self.families):
            row, col = divmod(index, self.cols)
            x = col * (tile_w + self.gap)
            y = self.height - (row + 1) * self.tile_h - row * self.gap
            rounded(canv, x, y, tile_w, self.tile_h, 6, fill="stone")
            canv.saveState()
            canv.setFillColor(c(tone))
            canv.rect(x, y + 8, 3, self.tile_h - 16, stroke=0, fill=1)
            canv.restoreState()
            draw_text(canv, x + 12, y + 32, str(count), "serif-bold", 20, "ivory")
            name_st = style("tile_name", "sans-semibold", 7.8, 9.4, tone)
            np_ = para(name, name_st, "sans-semibold")
            nw, nh = np_.wrap(tile_w - 22, 40)
            np_.drawOn(canv, x + 12, y + 27 - nh)


class FamilyGrid(CardGrid):
    pass


# ── Full-page flowables ─────────────────────────────────────────────
class FullPage(Flowable):
    def wrap(self, aw, ah):
        return aw, ah - 0.5


class CoverPage(FullPage):
    def __init__(self, facts):
        super().__init__()
        self.facts = facts

    def draw(self):
        canv = self.canv
        f = self.facts
        cx, cy, r = W / 2, H - 318, 124
        sunstone(canv, cx, cy, 208, "jade", "copper", 0.55)
        canv.saveState()
        for i in range(12, 0, -1):
            canv.setFillColor(c("jade", 0.025))
            canv.circle(cx, cy, r + i * 3.2, stroke=0, fill=1)
        path = canv.beginPath()
        path.circle(cx, cy, r)
        canv.clipPath(path, stroke=0, fill=0)
        canv.setFillAlpha(1)
        canv.setStrokeAlpha(1)
        canv.drawImage(str(AVATAR), cx - r, cy - r, 2 * r, 2 * r)
        canv.restoreState()
        canv.saveState()
        canv.setStrokeColor(c("jade"))
        canv.setLineWidth(2.2)
        canv.circle(cx, cy, r, stroke=1, fill=0)
        canv.setStrokeColor(c("copper", 0.8))
        canv.setLineWidth(0.7)
        canv.circle(cx, cy, r + 7, stroke=1, fill=0)
        canv.restoreState()
        draw_text(canv, cx, H - 72, "THE COMPLETE PROJECT DOSSIER", "sans-semibold", 8.6, "copper", space=3.2,
                  anchor="center")
        stepfret(canv, cx - 70, H - 92, 140, 2.2, "copper", 0.6, 0.7)
        draw_text(canv, cx, 238, "Tlamatini", "serif", 62, "ivory", anchor="center")
        draw_text(canv, cx, 210, "the one who knows", "serif-italic", 17, "jade", anchor="center", space=0.6)
        sub = style("cover_sub", "sans-light", 11.4, 16.2, "light_muted", alignment=TA_CENTER)
        p = para("A self-hosted AI developer assistant with a visual agent-workflow designer, a universal MCP "
                 "client, and the reach to drive real boards, engines and networks.", sub, "sans-light")
        pw, ph = p.wrap(380, 200)
        p.drawOn(canv, cx - 190, 196 - 12 - ph)
        metrics = [(str(f["agents"]), "agent types"), (str(f["tools"]), "Multi-Turn tools"),
                   (str(f["skills"]), "skills"), (f"v{f['version']}",
                    "current release" if f"v{f['version']}" == (f.get("release") or {}).get("latest_published")
                    else "version")]
        span = 400
        step = span / len(metrics)
        x0 = cx - span / 2
        for index, (value, label) in enumerate(metrics):
            mx = x0 + step * (index + 0.5)
            draw_text(canv, mx, 112, value, "serif-bold", 21, "gold", anchor="center")
            draw_text(canv, mx, 97, label.upper(), "sans-semibold", 6.6, "light_muted", space=1.3, anchor="center")
            if index:
                canv.saveState()
                canv.setStrokeColor(c("edge"))
                canv.setLineWidth(0.7)
                canv.line(x0 + step * index, 94, x0 + step * index, 132)
                canv.restoreState()
        stepfret(canv, 60, 70, W - 120, 2.4, "copper", 0.6, 0.55)
        draw_text(canv, cx, 50, "Created by Angela López Mendoza  ·  @angelahack1", "sans-semibold", 9.4,
                  "ivory", anchor="center")
        draw_text(canv, cx, 35, f"{f['generated_date']}  ·  github.com/XAIHT/Tlamatini  ·  MIT license",
                  "sans", 7.6, "light_muted", anchor="center", space=0.4)


class ChapterOpener(FullPage):
    def __init__(self, chapter, st: Styles, toc_key: str, label: str | None = None):
        super().__init__()
        self.chapter = chapter
        self.st = st
        self._toc = (0, label or f"{chapter.numeral}  ·  {chapter.title}", toc_key)

    def draw(self):
        canv = self.canv
        ch = self.chapter
        sunstone(canv, W * 0.86, H * 0.62, 250, "jade", "copper", 0.35)
        draw_text(canv, 64, H - 112, "CHAPTER" if ch.numeral[0] in "IVX" else "APPENDIX", "sans-semibold",
                  8.4, ch.accent, space=3.0)
        draw_text(canv, 60, H - 236, ch.numeral, "serif", 118, "copper", alpha=0.92)
        title_st = style("op_title", "serif", 36, 41, "ivory")
        tp = para(ch.title, title_st, "serif")
        tw, th = tp.wrap(430, 300)
        top = H - 262
        tp.drawOn(canv, 64, top - th)
        y = top - th - 14
        canv.saveState()
        canv.setStrokeColor(c(ch.accent))
        canv.setLineWidth(2.4)
        canv.line(64, y, 120, y)
        canv.restoreState()
        tag_st = style("op_tag", "sans-light", 13, 19.4, "light")
        gp = para(ch.tagline, tag_st, "sans-light")
        gw, gh = gp.wrap(400, 300)
        gp.drawOn(canv, 64, y - 16 - gh)
        y = y - 16 - gh - 40
        titles = [s.title for s in ch.sections]
        if titles:
            draw_text(canv, 64, y, "IN THIS CHAPTER", "sans-semibold", 7.4, "gold", space=2.2)
            y -= 12
            two_cols = len(titles) > 8
            col_w = 230 if two_cols else 440
            per_col = math.ceil(len(titles) / 2) if two_cols else len(titles)
            item_st = style("op_item", "sans", 9.4, 12.6, "light")
            for col in range(2 if two_cols else 1):
                x = 64 + col * (col_w + 16)
                cy = y
                for title in titles[col * per_col:(col + 1) * per_col]:
                    ip = para(title, item_st, "sans")
                    iw, ih = ip.wrap(col_w - 16, 100)
                    diamond(canv, x + 3, cy - 5.6, 2.6, fill=ch.accent)
                    ip.drawOn(canv, x + 12, cy - ih)
                    cy -= ih + 7
        stepfret(canv, 60, 64, W * 0.55, 2.4, "copper", 0.6, 0.55)
        draw_text(canv, W - 60, 36, f"Tlamatini · Complete Project Dossier · page {canv.getPageNumber()}",
                  "sans", 7.2, "light_muted", anchor="right")


class ClosingPage(FullPage):
    def __init__(self, facts):
        super().__init__()
        self.facts = facts

    def draw(self):
        canv = self.canv
        cx = W / 2
        sunstone(canv, cx, H * 0.62, 150, "jade", "copper", 0.6)
        canv.saveState()
        path = canv.beginPath()
        path.circle(cx, H * 0.62, 88)
        canv.clipPath(path, stroke=0, fill=0)
        from dossier_theme import AVATAR_CALM

        canv.setFillAlpha(1)
        canv.drawImage(str(AVATAR_CALM), cx - 88, H * 0.62 - 88, 176, 176)
        canv.restoreState()
        canv.saveState()
        canv.setStrokeColor(c("jade"))
        canv.setLineWidth(1.8)
        canv.circle(cx, H * 0.62, 88, stroke=1, fill=0)
        canv.restoreState()
        draw_text(canv, cx, H * 0.62 - 190, "Tlamatini", "serif", 40, "ivory", anchor="center")
        draw_text(canv, cx, H * 0.62 - 214, "one who knows", "serif-italic", 14, "jade", anchor="center")
        body = style("close", "sans-light", 10.6, 16, "light", alignment=TA_CENTER)
        p = para("Conceived, designed and built by **Angela López Mendoza**. Every fact in this dossier was "
                 "counted from the source tree when it was generated; regenerate it at any time with "
                 "`refresh_project_docs.py` and it will tell the truth again.", body, "sans-light", "gold")
        pw, ph = p.wrap(380, 200)
        p.drawOn(canv, cx - 190, H * 0.62 - 246 - ph)
        colophon = style("colo", "sans", 7.6, 11.2, "light_muted", alignment=TA_CENTER)
        q = para(f"Set in Palatino Linotype, Segoe UI and Consolas. Generated {self.facts['generated_at']} from "
                 f"commit {self.facts['head_short']}. MIT license · github.com/XAIHT/Tlamatini", colophon,
                 "sans")
        qw, qh = q.wrap(400, 100)
        q.drawOn(canv, cx - 200, 70)
        stepfret(canv, 60, 58, W - 120, 2.4, "copper", 0.6, 0.55)


# ── Tree appendix ───────────────────────────────────────────────────
TREE_SIZE = 6.3
TREE_LEAD = 7.35


def wrap_tree_line(line: str, width: float) -> list[str]:
    """Split a tree line that is wider than its column; continuations start with a guide and '»'."""
    if stringWidth(line, RL["mono"], TREE_SIZE) <= width:
        return [line]
    marker = max(line.find("├── "), line.find("└── "))
    guide = line[:marker] + ("│   " if line[marker] == "├" else "    ")
    head, rest = line, ""
    pieces = []
    while stringWidth(head, RL["mono"], TREE_SIZE) > width:
        cut = len(head) - 1
        while cut > marker + 8 and stringWidth(head[:cut], RL["mono"], TREE_SIZE) > width:
            cut -= 1
        pieces.append(head[:cut])
        rest = head[cut:]
        head = guide + "  » " + rest
    pieces.append(head)
    return pieces


class TreeColumns(Flowable):
    def __init__(self, left: list[str], right: list[str]):
        super().__init__()
        self.left, self.right = left, right
        for line in left + right:
            LEDGER.check(line, "mono")

    def wrap(self, aw, ah):
        self.aw = aw
        self.height = max(len(self.left), len(self.right)) * TREE_LEAD + 4
        return aw, self.height

    def draw(self):
        canv = self.canv
        col_w = (self.aw - 18) / 2
        canv.saveState()
        canv.setStrokeColor(c("rule"))
        canv.setLineWidth(0.5)
        canv.line(col_w + 9, 0, col_w + 9, self.height)
        canv.restoreState()
        for col, lines in enumerate((self.left, self.right)):
            x = col * (col_w + 18)
            y = self.height - TREE_LEAD
            for line in lines:
                tone = "jade_deep" if line.endswith("/") else "ink"
                draw_text(canv, x, y, line, "mono", TREE_SIZE, tone)
                y -= TREE_LEAD


def tree_pages(tree_text: str, first_height: float, next_height: float) -> list[TreeColumns]:
    col_w = (FRAME_W - 18) / 2
    lines: list[str] = []
    for raw in tree_text.splitlines():
        lines.extend(wrap_tree_line(raw, col_w - 2))
    pages = []
    index = 0
    height = first_height
    while index < len(lines):
        per_col = int((height - 4) // TREE_LEAD)
        left = lines[index:index + per_col]
        right = lines[index + per_col:index + 2 * per_col]
        pages.append(TreeColumns(left, right))
        index += 2 * per_col
        height = next_height
    return pages


# ── Story ───────────────────────────────────────────────────────────
def section_flow(section, facts, st: Styles, chapter) -> list:
    flow: list = []
    kicker = section.kicker
    if section.deck == "family":
        kicker = f"AGENT FAMILY  ·  {section.visual_data['count']} AGENTS"
    head = [Kicker(kicker, "copper_deep"), Spacer(1, 3), para(section.title, st.h1, "serif"),
            TitleRule(section.visual_data.get("accent", chapter.accent)), Spacer(1, 4),
            para(section.lede, st.lede, "sans-semilight")]
    anchor = Anchor(1, section.title, f"sec_{chapter.key}_{section.key}")
    flow.append(anchor)
    flow.append(KeepTogether(head))
    for text in section.body:
        flow.append(para(text, st.body, "sans"))
    visual = build_visual(section, facts, st)
    if visual is not None:
        flow.append(Spacer(1, 6))
        flow.append(visual)
        flow.append(Spacer(1, 10))
    if section.points:
        if section.deck == "family":
            tone = section.visual_data.get("accent", "jade")
            flow.append(Spacer(1, 2))
            flow.append(FamilyGrid([(name, text, tone) for name, text in section.points], st, cols=2,
                                   accent=tone, gap=8, pad=8, title_font="serif-bold",
                                   title_style=style("fam", "serif-bold", 11.2, 14, "ink"), compact=True))
        else:
            tones = ["jade", "copper", "gold", "cyan", "magenta", "rose"]
            cards = [(head_text, text, tones[i % len(tones)]) for i, (head_text, text) in enumerate(section.points)]
            flow.append(Spacer(1, 4))
            flow.append(CardGrid(cards, st, cols=2))
        flow.append(Spacer(1, 10))
    if section.table:
        t = section.table
        table = styled_table(t["columns"], t["rows"], t["widths"], st, t.get("align"))
        flow.append(KeepTogether([Spacer(1, 4), table, Spacer(1, 10)]) if len(t["rows"]) <= 20
                    else table)
        if len(t["rows"]) > 20:
            flow.append(Spacer(1, 10))
    if section.code:
        flow.append(KeepTogether([Spacer(1, 2), CodeBlock(section.code), Spacer(1, 10)]))
    if section.callout:
        tone = {"trust": "rose", "architecture": "copper", "capabilities": "jade"}.get(chapter.key, "jade")
        note = [Callout(section.callout[0], section.callout[1], st, tone), Spacer(1, 10)]
        glued: list = []
        while flow and not isinstance(flow[-1], Anchor):
            previous = flow.pop()
            glued[:0] = previous._content if isinstance(previous, KeepTogether) else [previous]
            if not isinstance(previous, Spacer):
                break
        flow.append(KeepTogether(glued + note))
    flow.append(Spacer(1, 8))
    # A heading never ends a page alone: glue it to the first real block that follows it.
    for index in range(2, len(flow)):
        if not isinstance(flow[index], Spacer):
            tail = []
            for item in flow[2:index + 1]:
                tail.extend(item._content if isinstance(item, KeepTogether) else [item])
            flow[1:index + 1] = [KeepTogether(head + tail)]
            break
    return [CondPageBreak(keep_height(flow))] + flow


def keep_height(flow) -> float:
    """Room to demand before a section starts: the whole section when it fits on one page."""
    frame_h = H - MT - MB

    def measure(items) -> float:
        height = 0.0
        for item in items:
            if isinstance(item, KeepTogether):
                height += measure(item._content)
            elif isinstance(item, CondPageBreak):
                continue
            else:
                height += item.wrap(FRAME_W, frame_h)[1] + item.getSpaceBefore() + item.getSpaceAfter()
        return height

    try:
        total = measure(flow)
    except Exception as exc:  # a measurement problem must be visible, never a silent fallback
        raise RuntimeError(f"Cannot measure a dossier section: {exc}") from exc
    # Short sections stay whole; longer ones start only with at least half a page of room, and their
    # tables and callouts are glued so a continuation never strands a lone row or note.
    return min(total + 4, frame_h * 0.5) if total <= frame_h * 0.86 else 230


def build_visual(section, facts, st: Styles):
    kind = section.visual
    data = section.visual_data
    if kind == "planes":
        return Planes()
    if kind == "layers":
        return LayerStack(data["layers"], st)
    if kind == "steps":
        return StepGrid(data["steps"], st, cols=3)
    if kind == "ladder":
        return Ladder(data["rungs"], st)
    if kind == "cascade":
        return Cascade(data["stages"])
    if kind == "operations":
        return Operations(data["ops"], st)
    if kind == "metrics":
        return MetricGrid(metric_tiles(facts))
    if kind == "chain":
        return Chain(data["chain"], data.get("caption", ""))
    if kind == "timeline":
        return Timeline(facts["timeline"], st)
    if kind == "language_bars":
        return BarChart(language_series(facts, 16))
    if kind == "bars_models":
        return BarChart([(name, count) for name, count in facts["model_groups"]], label_w=150)
    if kind == "family_wheel":
        from dossier_content import AGENT_FAMILIES

        return FamilyTiles([(name, tone, len(members)) for name, tone, _, members in AGENT_FAMILIES])
    return None


def metric_tiles(facts) -> list[tuple[str, str]]:
    return [
        (str(facts["agents"]), "agent types"),
        (str(facts["tools"]), "Multi-Turn tools"),
        (str(facts["wrapped"]), "wrapped agents"),
        (str(facts["skills"]), "skills"),
        (str(len(facts["acpx_peers"])), "ACPX peers"),
        (str(facts["migrations"]), "migrations"),
        (f"{facts['tracked_count']:,}", "tracked files"),
        (f"{facts['total_effective']:,}", "effective lines"),
    ]


def language_series(facts, limit: int) -> list[tuple[str, int]]:
    rows = [(row.language, row.effective_lines) for row in facts["languages"]]
    head, tail = rows[:limit - 1], rows[limit - 1:]
    if tail:
        head.append((f"{len(tail)} more", sum(value for _, value in tail)))
    return head


def about_flow(facts, st: Styles) -> list:
    flow = [ChapterMarker("About this dossier"), Anchor(0, "About this dossier", "about"),
            Kicker("BEFORE YOU BEGIN"), Spacer(1, 3), para("About this dossier", st.h1, "serif"),
            TitleRule("copper"), Spacer(1, 4),
            para("This is the complete dossier of Tlamatini: what she is, how she works, how to use her, every "
                 "agent she can run, the promises she keeps, and a full inventory of her source tree.",
                 st.lede, "sans-semilight")]
    for text in [
        "It is written for three readers at once. A **newcomer** can read the first three chapters and know "
        "what Tlamatini is and how to start. An **operator** will find the surfaces, the bestiary and the "
        "configuration chapters. A **maintainer** will find the architecture, the contracts behind the "
        "honesty rules and the complete repository inventory.",
        "Nothing here is typed from memory. Counts, versions, commits, the language inventory and the file "
        "tree were derived from Git and the source files when this edition was generated, and the generator "
        "then reopened this document to prove that no text overflows or is clipped and that the file tree "
        "matches the repository exactly. Configuration values, credentials and private addresses are never "
        "reproduced.",
    ]:
        flow.append(para(text, st.body, "sans"))
    flow.append(Spacer(1, 6))
    flow.append(styled_table(["This edition", ""], [
        ["Generated", facts["generated_at"]],
        ["Inspected commit", f"{facts['head_short']} — {facts['head_subject']}"],
        ["Version", facts['version']],
        ["Latest published release", facts["release"]["latest_published"] or "unknown"],
        ["Companion deck", "Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx"],
    ], [0.30, 0.70], st))
    flow.append(Spacer(1, 12))
    flow.append(Callout("A note on the numbers",
                        "Figures that move with every release — agents, tools, skills, migrations, lines — "
                        "describe this edition only. Regenerate the dossier and they update themselves.", st,
                        "gold"))
    return flow


def build_pdf(facts: dict, chapters, output) -> int:
    register_fonts()
    st = Styles()
    doc = DossierDoc(str(output), facts)
    story: list = [CoverPage(facts), NextPageTemplate("body"), PageBreak()]
    story += about_flow(facts, st)
    story += [PageBreak(), ChapterMarker("Contents"), Kicker("CONTENTS"), Spacer(1, 3),
              para("Contents", st.h1, "serif"), TitleRule("jade"), Spacer(1, 10)]
    toc = TableOfContents(dotsMinLevel=0)
    toc.levelStyles = [
        ParagraphStyle("toc0", fontName=RL["serif"], fontSize=12.4, leading=15, textColor=c("ink"),
                       leftIndent=0, firstLineIndent=0, spaceBefore=5, spaceAfter=0.5),
        ParagraphStyle("toc1", fontName=RL["sans"], fontSize=8.6, leading=10.6, textColor=c("ink2"),
                       leftIndent=20, firstLineIndent=0, spaceBefore=0, spaceAfter=0),
    ]
    story.append(toc)
    for chapter in chapters:
        story += [NextPageTemplate("dark"), PageBreak(), ChapterOpener(chapter, st, f"ch_{chapter.key}"),
                  NextPageTemplate("body"), PageBreak(), ChapterMarker(f"{chapter.numeral} · {chapter.title}")]
        for section in chapter.sections:
            story += section_flow(section, facts, st, chapter)

    from dossier_content import Chapter

    appendix = Chapter("tree", "A", "The Complete Tracked File Tree",
                       f"Every one of the {facts['tracked_count']:,} files Git tracks, drawn as a tree. "
                       "Directories are shown in jade.", [], accent="gold")
    story += [NextPageTemplate("dark"), PageBreak(),
              ChapterOpener(appendix, st, "appendix_tree", "Appendix A  ·  The complete tracked file tree"),
              NextPageTemplate("body"), PageBreak(), ChapterMarker("Appendix A · File tree")]
    intro = [Kicker("APPENDIX A"), Spacer(1, 3), para("The complete tracked file tree", st.h1, "serif"),
             TitleRule("gold"), Spacer(1, 4),
             para(f"{facts['tracked_count']:,} tracked files at commit `{facts['head_short']}`. Within each "
                  "directory, files come first and sub-directories follow; a line too long for its column "
                  "continues on the next line after a » mark.", st.lede, "sans-semilight"), Spacer(1, 8)]
    intro_height = sum(item.wrap(FRAME_W, 1000)[1] + item.getSpaceAfter() for item in intro) + 14
    frame_h = H - MT - MB
    pages = tree_pages(facts["tree_text"], frame_h - intro_height, frame_h)
    story += intro
    for index, page in enumerate(pages):
        if index:
            story.append(PageBreak())
        story.append(page)
    story += [NextPageTemplate("dark"), PageBreak(), ClosingPage(facts)]
    doc.multiBuild(story)
    LEDGER.assert_clean("PDF")
    return doc.page
