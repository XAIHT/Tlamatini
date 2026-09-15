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
# pptxer_fonts.py — PPTXer's TYPEFACE ENGINE.
#
# Sibling module of pptxer.py (flat neighbour, NOT a package). Stdlib + Pillow.
# Imports nothing from agent.* and nothing from the other pptxer_* modules
# except pptxer_color (one-way, so no cycle is possible).
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT THIS MODULE IS FOR, AND WHY IT IS NOT OPTIONAL
# ─────────────────────────────────────────────────────────────────────────────
# Two completely different jobs, and confusing them is the classic PPTX bug:
#
#   1. NAMING a font in the .pptx file.
#      python-pptx writes a font NAME into the XML. PowerPoint resolves that
#      name on whatever machine OPENS the deck. Writing "Terminator Two" is
#      free and always "succeeds" — the XML is valid either way.
#
#   2. MEASURING that font so the text actually FITS its box.
#      This needs the real TrueType file on THIS machine, read through
#      PIL.ImageFont, at the real point size.
#
# Job 1 without job 2 is exactly the PDFer disaster in a new costume: the file
# is written, the library reports success, and the deck has a title running off
# the slide. A character-count estimate is +116% wrong on "lllllllllll" and
# −43% wrong on "WWWWWWWWWWW" — and a marketing title is USUALLY set in a
# condensed or extended display face, where the error is worse still.
#
# So every font PPTXer names, it also RESOLVES to a file and MEASURES. When a
# named font cannot be found on this machine, that is reported honestly and a
# metrically-similar substitute is measured instead — never silently assumed.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE SUBSTITUTION CONTRACT (do NOT weaken)
# ─────────────────────────────────────────────────────────────────────────────
# A substitute is chosen by CATEGORY and WIDTH CLASS, never alphabetically.
# Swapping a condensed display face (Agency FB) for a normal-width one (Arial)
# makes text ~20% wider, which is how a title that measured fine on the
# author's machine overflows on the reviewer's. When PPTXer substitutes, it
# measures the SUBSTITUTE, so the box is solved for what will actually render.

import glob
import os
import sys
import threading
from functools import lru_cache

# Office can place the first/last glyph slightly beyond a font's nominal
# ascent/descent. Keep this allowance separate from the frame's padding.
TEXT_RENDER_GUARD_PT = 2.0

__all__ = [
    "FontInventory",
    "ResolvedFont",
    "get_inventory",
    "measure_text",
    "wrap_text_to_width",
    "fit_point_size",
    "PAIRINGS",
    "POWERPOINT_CORE_FONTS",
    "FONT_CATEGORIES",
]

# ─────────────────────────────────────────────────────────────────────────────
# The fonts PowerPoint / Word ship with, grouped so substitution is sane.
#
# "Core" here means: a font a deck may name with a high chance of resolving on
# another Windows machine. PPTXer prefers these for BODY text (portability) and
# is free to use anything installed for DISPLAY text (impact), because a display
# face that substitutes degrades gracefully while body text that substitutes
# reflows the whole slide.
# ─────────────────────────────────────────────────────────────────────────────

POWERPOINT_CORE_FONTS = (
    # Office UI / theme defaults
    "Calibri", "Calibri Light", "Cambria", "Candara", "Consolas", "Constantia",
    "Corbel", "Segoe UI", "Segoe UI Light", "Segoe UI Semibold", "Aptos",
    # The universal Windows set
    "Arial", "Arial Black", "Arial Narrow", "Arial Rounded MT Bold",
    "Times New Roman", "Courier New", "Verdana", "Tahoma", "Georgia",
    "Trebuchet MS", "Impact", "Comic Sans MS", "Palatino Linotype",
    "Book Antiqua", "Garamond", "Century Gothic", "Century Schoolbook",
    "Franklin Gothic Book", "Franklin Gothic Medium", "Franklin Gothic Demi",
    "Franklin Gothic Heavy", "Lucida Sans", "Lucida Console", "Lucida Bright",
    "MS Gothic", "MS Mincho", "Sylfaen", "Rockwell", "Rockwell Condensed",
    "Rockwell Extra Bold", "Bell MT", "Berlin Sans FB", "Bodoni MT",
    "Bookman Old Style", "Britannic Bold", "Broadway", "Californian FB",
    "Castellar", "Centaur", "Copperplate Gothic Bold", "Copperplate Gothic Light",
    "Curlz MT", "Elephant", "Engravers MT", "Eras Bold ITC", "Eras Demi ITC",
    "Felix Titling", "Footlight MT Light", "Forte", "Gill Sans MT",
    "Gill Sans MT Condensed", "Gloucester MT Extra Condensed", "Goudy Old Style",
    "Haettenschweiler", "Harrington", "High Tower Text", "Imprint MT Shadow",
    "Informal Roman", "Jokerman", "Juice ITC", "Kristen ITC", "Lucida Calligraphy",
    "Lucida Fax", "Lucida Handwriting", "Magneto", "Maiandra GD",
    "Matura MT Script Capitals", "Mistral", "Modern No. 20", "Monotype Corsiva",
    "Niagara Engraved", "Niagara Solid", "OCR A Extended", "Old English Text MT",
    "Onyx", "Papyrus", "Parchment", "Perpetua", "Perpetua Titling MT",
    "Playbill", "Poor Richard", "Pristina", "Rage Italic", "Ravie", "Rockwell",
    "Script MT Bold", "Showcard Gothic", "Snap ITC", "Stencil", "Tempus Sans ITC",
    "Tw Cen MT", "Tw Cen MT Condensed", "Viner Hand ITC", "Vivaldi",
    "Vladimir Script", "Wide Latin", "Agency FB", "Algerian", "Bahnschrift",
    "Bauhaus 93", "Bernard MT Condensed", "Blackadder ITC", "Bradley Hand ITC",
    "Brush Script MT", "Chiller", "Colonna MT", "Cooper Black", "Corbel Light",
    "Ebrima", "Gabriola", "Gadugi", "Harlow Solid Italic", "Ink Free",
    "Javanese Text", "Leelawadee UI", "Malgun Gothic", "Microsoft Sans Serif",
    "Mongolian Baiti", "MV Boli", "Myanmar Text", "Nirmala UI", "Sitka Text",
    "Wingdings", "Wingdings 2", "Wingdings 3", "Webdings", "Symbol",
)

# Category → the kind of job the face is good for. Used for substitution and
# for the pairing engine. A face may legitimately be in several lists.
FONT_CATEGORIES = {
    "display_tech": (
        # Sci-fi / esports / hardware — the gaming brief's bread and butter.
        "Nasalization", "Terminator Two", "Good Times", "Agency FB",
        "Bank Gothic", "Eurostile", "Michroma", "Orbitron", "Audiowide",
        "Rajdhani", "Exo", "Exo 2", "Russo One", "Teko", "Saira",
        "Chakra Petch", "Electrolize", "Quantico", "Syncopate", "Wallpoet",
        "Bahnschrift", "OCR A Extended", "Square 721", "Handel Gothic",
        "Zrnic", "Aldrich", "Iceberg", "Jura", "Share Tech", "Play",
    ),
    "display_impact": (
        # Loud, heavy, poster-scale. Marketing headlines.
        "Impact", "Haettenschweiler", "Arial Black", "Anton", "Antonio",
        "Bebas Neue", "Oswald", "Franklin Gothic Heavy", "Cooper Black",
        "Bernard MT Condensed", "Showcard Gothic", "Bauhaus 93", "Broadway",
        "Wide Latin", "Elephant", "Britannic Bold", "Gill Sans Ultra Bold",
        "Stencil", "Algerian", "Playbill", "Onyx", "Berlin Sans FB Demi",
    ),
    "display_elegant": (
        "Didot", "Bodoni MT", "Playfair Display", "Perpetua Titling MT",
        "Copperplate Gothic Light", "Copperplate Gothic Bold", "Felix Titling",
        "Engravers MT", "Castellar", "Trajan Pro", "Optima", "Cinzel",
        "Centaur", "High Tower Text", "Modern No. 20", "Colonna MT",
    ),
    "sans_body": (
        "Segoe UI", "Calibri", "Arial", "Verdana", "Tahoma", "Corbel",
        "Candara", "Trebuchet MS", "Franklin Gothic Book", "Gill Sans MT",
        "Century Gothic", "Lucida Sans", "Microsoft Sans Serif", "Aptos",
        "Open Sans", "Source Sans Pro", "Lato", "Roboto", "Inter",
        "Helvetica", "Helvetica Neue", "Montserrat", "Nunito Sans",
    ),
    "sans_condensed": (
        "Arial Narrow", "Franklin Gothic Demi Cond", "Franklin Gothic Medium Cond",
        "Tw Cen MT Condensed", "Gill Sans MT Condensed", "Oswald",
        "Roboto Condensed", "Barlow Condensed", "Archivo Narrow",
        "Bernard MT Condensed", "Rockwell Condensed", "Agency FB",
    ),
    "serif_body": (
        "Georgia", "Cambria", "Constantia", "Times New Roman",
        "Palatino Linotype", "Book Antiqua", "Garamond", "Century Schoolbook",
        "Bookman Old Style", "Goudy Old Style", "Perpetua", "Sitka Text",
        "Bell MT", "Lucida Bright", "Merriweather", "Source Serif Pro",
    ),
    "slab": (
        "Rockwell", "Rockwell Extra Bold", "Roboto Slab", "Zilla Slab",
        "Museo Slab", "Courier New", "Bitter", "Arvo",
    ),
    "mono": (
        "Consolas", "Courier New", "Lucida Console", "Cascadia Code",
        "Cascadia Mono", "JetBrains Mono", "Fira Code", "Source Code Pro",
        "Roboto Mono", "IBM Plex Mono", "OCR A Extended", "Menlo", "Monaco",
    ),
    "script": (
        "Segoe Script", "Brush Script MT", "Lucida Handwriting",
        "Monotype Corsiva", "Mistral", "Bradley Hand ITC", "Pristina",
        "Vladimir Script", "Kristen ITC", "Ink Free", "Gabriola",
        "Freestyle Script", "Rage Italic", "Segoe Print",
    ),
    "grunge": (
        "Chiller", "Jokerman", "Ravie", "Snap ITC", "Harlow Solid Italic",
        "Blackadder ITC", "Old English Text MT", "Magneto", "Curlz MT",
        "Papyrus", "Juice ITC", "Tempus Sans ITC", "Viner Hand ITC",
    ),
}

# Width class per category — the substitution safety net. Substituting ACROSS
# width classes is what silently overflows boxes on another machine.
_CATEGORY_WIDTH = {
    "display_tech": "normal",
    "display_impact": "normal",
    "display_elegant": "normal",
    "sans_body": "normal",
    "sans_condensed": "condensed",
    "serif_body": "normal",
    "slab": "normal",
    "mono": "mono",
    "script": "normal",
    "grunge": "normal",
}

# Guaranteed-present last resorts, per category. These exist on every Windows
# install, so the ladder can always terminate.
_LAST_RESORT = {
    "display_tech": "Arial Black",
    "display_impact": "Impact",
    "display_elegant": "Georgia",
    "sans_body": "Arial",
    "sans_condensed": "Arial Narrow",
    "serif_body": "Times New Roman",
    "slab": "Georgia",
    "mono": "Courier New",
    "script": "Comic Sans MS",
    "grunge": "Impact",
}


class ResolvedFont:
    """A font NAME paired with the real file that will be measured for it."""

    __slots__ = ("requested", "family", "path", "substituted", "category",
                 "reason", "bold", "italic", "tracking_em")

    def __init__(self, requested, family, path, substituted=False,
                 category="sans_body", reason="", bold=False, italic=False):
        self.requested = requested
        self.family = family
        self.path = path
        self.substituted = bool(substituted)
        self.category = category
        self.reason = reason
        self.bold = bool(bold)
        self.italic = bool(italic)
        self.tracking_em = 0.0

    @property
    def measurable(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)

    def __repr__(self) -> str:
        tag = " (substituted)" if self.substituted else ""
        return f"ResolvedFont({self.requested!r} -> {self.family!r}{tag})"


def _norm(name: str) -> str:
    """Normalise a family name for matching: case/space/punctuation-insensitive."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())


class FontInventory:
    """Every font FILE on this machine, indexed by family name.

    Built ONCE, lazily, and cached (see get_inventory). Enumerating ~630 font
    files and reading each one's internal name table costs ~0.4 s, which is fine
    once per run and ruinous per text box.

    FAIL-OPEN throughout: a corrupt font file, an unreadable directory or a
    missing Pillow all degrade to a smaller inventory, never an exception. A
    deck must still build on a machine with an unusual font setup.
    """

    def __init__(self, extra_dirs=None):
        self._by_norm = {}          # normalised family -> {style_key: path}
        self._families = []         # display-cased family names, sorted
        self._scanned_dirs = []
        self._errors = []
        self._measure_cache = {}
        self._lock = threading.Lock()
        self._scan(extra_dirs or [])

    # -- construction ---------------------------------------------------------

    def _font_dirs(self, extra):
        dirs = []
        if sys.platform.startswith("win"):
            windir = os.environ.get("WINDIR") or r"C:\Windows"
            dirs.append(os.path.join(windir, "Fonts"))
            local = os.environ.get("LOCALAPPDATA")
            if local:
                dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        elif sys.platform == "darwin":
            dirs.extend([
                "/System/Library/Fonts", "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"),
            ])
        else:
            dirs.extend([
                "/usr/share/fonts", "/usr/local/share/fonts",
                os.path.expanduser("~/.fonts"),
                os.path.expanduser("~/.local/share/fonts"),
            ])
        for d in (extra or []):
            if d:
                dirs.append(str(d))
        return [d for d in dirs if d and os.path.isdir(d)]

    def _scan(self, extra_dirs):
        try:
            from PIL import ImageFont
        except Exception as exc:                                  # noqa: BLE001
            self._errors.append(f"Pillow unavailable: {exc}")
            return

        for directory in self._font_dirs(extra_dirs):
            self._scanned_dirs.append(directory)
            patterns = ("*.ttf", "*.TTF", "*.otf", "*.OTF", "*.ttc", "*.TTC")
            paths = []
            for pat in patterns:
                try:
                    paths.extend(glob.glob(os.path.join(directory, pat)))
                except Exception:                                 # noqa: BLE001
                    continue
                try:
                    paths.extend(glob.glob(os.path.join(directory, "**", pat),
                                           recursive=True))
                except Exception:                                 # noqa: BLE001
                    continue

            # ⚠️ SORTED, NOT JUST DE-DUPLICATED — THIS IS A CORRECTNESS FIX.
            # Python randomises string hashing per process, so iterating a
            # bare `set` visits these paths in a DIFFERENT ORDER EVERY RUN.
            # Because the loop below keeps the FIRST file it sees for a given
            # (family, style), two files that claim the same style — very
            # common on Windows, e.g. a variable font beside its static
            # instances — would take turns winning, and the winner's metrics
            # decide how text wraps.
            #
            # Measured 2026-09-14: the SAME deck, same content, same code,
            # built twice, audited LAYOUT CLEAN once and "statlabel needs 41pt
            # in a 40pt frame" the next — the reported family was identical
            # (Bahnschrift / Segoe UI) because only the FILE behind it had
            # changed. A deck that lays out differently between runs is one
            # nobody can trust, and it makes every layout bug unreproducible.
            for path in sorted(set(paths)):
                try:
                    font = ImageFont.truetype(path, 12)
                    family, style = font.getname()
                except Exception:                                 # noqa: BLE001
                    # A .ttc collection or a broken file. Not worth reporting
                    # individually — a missing face degrades to a substitute.
                    continue
                if not family:
                    continue
                family, style = _fold_width_into_family(family, style or "")
                key = _norm(family)
                style_key = _style_key(style)
                bucket = self._by_norm.setdefault(key, {})
                # Prefer the first file found for a given style; a duplicate in
                # the user font dir should not displace the system one.
                bucket.setdefault(style_key, path)
                bucket.setdefault("_display_name", family)

        self._families = sorted(
            {v.get("_display_name", "") for v in self._by_norm.values() if v.get("_display_name")}
        )

    # -- queries --------------------------------------------------------------

    @property
    def families(self) -> list:
        return list(self._families)

    @property
    def family_count(self) -> int:
        return len(self._families)

    @property
    def scanned_dirs(self) -> list:
        return list(self._scanned_dirs)

    @property
    def errors(self) -> list:
        return list(self._errors)

    def has(self, family: str) -> bool:
        return _norm(family) in self._by_norm

    def installed_from(self, candidates) -> list:
        """Filter a candidate list down to what is REALLY installed here."""
        return [c for c in (candidates or []) if self.has(c)]

    def file_for(self, family: str, bold: bool = False, italic: bool = False):
        """Best file for a family+style, or None."""
        bucket = self._by_norm.get(_norm(family))
        if not bucket:
            return None
        for key in _style_preference(bold, italic):
            path = bucket.get(key)
            if path:
                return path
        for key, path in bucket.items():
            if key != "_display_name" and path:
                return path
        return None

    def display_name(self, family: str) -> str:
        bucket = self._by_norm.get(_norm(family))
        if bucket and bucket.get("_display_name"):
            return bucket["_display_name"]
        return family

    # -- resolution (the contract) -------------------------------------------

    def resolve(self, family: str, category: str = "sans_body",
                bold: bool = False, italic: bool = False) -> ResolvedFont:
        """Resolve a requested family to something MEASURABLE on this machine.

        The ladder, in order:
          1. the exact family, if installed;
          2. another face in the SAME category with the SAME width class;
          3. the category's guaranteed last resort;
          4. any measurable font at all (so measurement never becomes impossible).

        Every rung below the first sets ``substituted=True`` and records WHY, so
        the caller can report it rather than pretend the request was honoured.
        """
        want = (family or "").strip()
        cat = category if category in FONT_CATEGORIES else "sans_body"

        if want and self.has(want):
            return ResolvedFont(
                requested=want, family=self.display_name(want),
                path=self.file_for(want, bold, italic), substituted=False,
                category=cat, bold=bold, italic=italic,
            )

        width = _CATEGORY_WIDTH.get(cat, "normal")
        for candidate in FONT_CATEGORIES.get(cat, ()):
            if not self.has(candidate):
                continue
            cand_cat = _category_of(candidate) or cat
            if _CATEGORY_WIDTH.get(cand_cat, "normal") != width:
                continue
            return ResolvedFont(
                requested=want, family=self.display_name(candidate),
                path=self.file_for(candidate, bold, italic), substituted=True,
                category=cat, bold=bold, italic=italic,
                reason=(f"{want!r} is not installed on this machine; "
                        f"substituted {candidate!r} from the same category "
                        f"and width class"),
            )

        fallback = _LAST_RESORT.get(cat, "Arial")
        if self.has(fallback):
            return ResolvedFont(
                requested=want, family=self.display_name(fallback),
                path=self.file_for(fallback, bold, italic), substituted=True,
                category=cat, bold=bold, italic=italic,
                reason=(f"{want!r} is not installed and no category sibling was "
                        f"available; fell back to {fallback!r}"),
            )

        for fam in self._families:
            path = self.file_for(fam, bold, italic)
            if path:
                return ResolvedFont(
                    requested=want, family=fam, path=path, substituted=True,
                    category=cat, bold=bold, italic=italic,
                    reason=(f"{want!r} is not installed and no category fallback "
                            f"resolved; using {fam!r} so text can still be measured"),
                )

        return ResolvedFont(
            requested=want, family=want or "Arial", path=None, substituted=True,
            category=cat, bold=bold, italic=italic,
            reason="no measurable font file was found on this machine",
        )

    # -- measurement ----------------------------------------------------------

    def pil_font(self, resolved: ResolvedFont, size_pt: float, dpi: int = 96):
        """A PIL font object at a REAL pixel size for the given point size.

        Points are a physical unit; PIL wants pixels. 1pt = 1/72 inch, so at
        `dpi` the pixel size is pt * dpi / 72. Higher sampling density reduces
        the accumulated advance rounding in long lines of text.
        """
        if not resolved or not resolved.measurable:
            return None
        px = max(1, int(round(float(size_pt) * float(dpi) / 72.0)))
        cache_key = (resolved.path, px)
        with self._lock:
            hit = self._measure_cache.get(cache_key)
        if hit is not None:
            return hit
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(resolved.path, px)
        except Exception:                                         # noqa: BLE001
            return None
        with self._lock:
            self._measure_cache[cache_key] = font
        return font


# Most specific first — "semicondensed" contains "condensed", so a plain
# left-to-right scan must meet the longer token before the shorter one.
_WIDTH_TOKENS = (
    ("postercompressed", "Poster Compressed"),
    ("ultracompressed", "Ultra Compressed"),
    ("extracompressed", "Extra Compressed"),
    ("ultracondensed", "Ultra Condensed"),
    ("extracondensed", "Extra Condensed"),
    ("semicondensed", "Semi Condensed"),
    ("ultraexpanded", "Ultra Expanded"),
    ("extraexpanded", "Extra Expanded"),
    ("semiexpanded", "Semi Expanded"),
    ("condensed", "Condensed"),
    ("compressed", "Compressed"),
    ("narrow", "Narrow"),
    ("expanded", "Expanded"),
    ("extended", "Extended"),
)


def _fold_width_into_family(family: str, style: str) -> tuple:
    """Move a WIDTH word out of the style and into the family name.

    ⚠️ WINDOWS PUTS THE WIDTH IN THE STYLE, AND IT COSTS YOU THE REAL FACE.
    `ARIALN.TTF` reports `('Arial', 'Narrow')` — the width lives in the STYLE
    field, not the family. `_style_key` understands only weight and slant, so
    "Narrow" fell through to "regular", and the four Arial Narrow files
    claimed regular/bold/italic/bolditalic of the **Arial** bucket and evicted
    `arial.ttf` from all four. Measured 2026-09-14: `resolve("Arial")`
    returned `ARIALN.TTF` while reporting `substituted=False` — text measured
    and declared as Arial, drawn narrower than Arial. Meanwhile
    `resolve("Arial Narrow")` found no such family at all and substituted
    Segoe UI. Both answers were wrong and neither said so.

    A width is a property of the TYPEFACE, not a slant or a weight, so it
    belongs in the family name: ("Arial", "Narrow") -> ("Arial Narrow",
    "Regular"). That restores real Arial to the Arial bucket AND makes
    "Arial Narrow" resolvable by its own name.

    Fail-open: a style naming no width is returned untouched, and a family
    that already carries the width (family "Arial Narrow", style "Regular")
    is left alone rather than doubled into "Arial Narrow Narrow".
    """
    raw = (style or "").lower().replace("-", " ").replace("_", " ")
    squashed = "".join(raw.split())
    if not squashed:
        return family, style

    for token, pretty in _WIDTH_TOKENS:
        if token not in squashed:
            continue
        if token in _norm(family or ""):
            return family, style          # the family already says it
        rest = " ".join(squashed.replace(token, " ").split()) or "regular"
        return ("%s %s" % ((family or "").strip(), pretty)).strip(), rest
    return family, style


def _style_key(style: str) -> str:
    s = (style or "").lower()
    bold = "bold" in s or "heavy" in s or "black" in s
    italic = "italic" in s or "oblique" in s
    if bold and italic:
        return "bolditalic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def _style_preference(bold: bool, italic: bool) -> tuple:
    if bold and italic:
        return ("bolditalic", "bold", "italic", "regular")
    if bold:
        return ("bold", "bolditalic", "regular", "italic")
    if italic:
        return ("italic", "bolditalic", "regular", "bold")
    return ("regular", "italic", "bold", "bolditalic")


_CATEGORY_INDEX = None


def _category_of(family: str):
    global _CATEGORY_INDEX
    if _CATEGORY_INDEX is None:
        idx = {}
        for cat, names in FONT_CATEGORIES.items():
            for n in names:
                idx.setdefault(_norm(n), cat)
        _CATEGORY_INDEX = idx
    return _CATEGORY_INDEX.get(_norm(family))


# ─────────────────────────────────────────────────────────────────────────────
# The single cached inventory
# ─────────────────────────────────────────────────────────────────────────────

_INVENTORY = None
_INVENTORY_LOCK = threading.Lock()


def get_inventory(extra_dirs=None, force: bool = False) -> FontInventory:
    """The process-wide font inventory. Built once; ~0.4 s on a 630-font box."""
    global _INVENTORY
    with _INVENTORY_LOCK:
        if _INVENTORY is None or force:
            _INVENTORY = FontInventory(extra_dirs=extra_dirs)
        return _INVENTORY


# ─────────────────────────────────────────────────────────────────────────────
# Measurement API — the part that stops text leaving its box
# ─────────────────────────────────────────────────────────────────────────────

def measure_text(text: str, resolved: ResolvedFont, size_pt: float,
                 inventory: FontInventory = None) -> tuple:
    """(width_pt, height_pt) of ONE line, measured with the real face.

    Falls back to a per-category average-advance estimate ONLY when the font is
    genuinely unmeasurable, and the caller can tell the difference because the
    estimate is deliberately CONSERVATIVE (it over-estimates width). Over-
    estimating makes a box too big — ugly. Under-estimating makes text overflow
    — broken. Always fail toward ugly.
    """
    if not text:
        return (0.0, float(size_pt) * 1.2)

    inv = inventory or get_inventory()
    # A quarter-point grid can accumulate several points of advance error
    # across a long line (Courier New at 16pt underestimated 87 glyphs by
    # 10.875pt). A sixteenth-point grid matches Office much more closely.
    dpi = 1152
    font = inv.pil_font(resolved, size_pt, dpi=dpi) if resolved else None
    tracking = max(0, len(text) - 1) * float(size_pt) * getattr(resolved, "tracking_em", 0.0)

    if font is not None:
        try:
            bbox = font.getbbox(text)
            width_px = max(float(bbox[2] - min(0, bbox[0])), float(font.getlength(text)))
            height_px = float(bbox[3] - bbox[1])
            # Convert the sampled pixels back to physical points.
            return (max(0.0, width_px * 72.0 / dpi + tracking), max(height_px * 72.0 / dpi,
                                                float(size_pt) * 1.15))
        except Exception:                                         # noqa: BLE001
            pass

    # Conservative estimate. 0.62 em average advance is wider than almost every
    # real proportional face, so the box comes out too large rather than too small.
    avg = 0.62
    if resolved is not None and resolved.category == "mono":
        avg = 0.60
    elif resolved is not None and resolved.category == "sans_condensed":
        avg = 0.50
    elif resolved is not None and resolved.category == "display_impact":
        avg = 0.56
    return (len(text) * float(size_pt) * avg + max(0.0, tracking), float(size_pt) * 1.2)


@lru_cache(maxsize=128)
def _font_coverage(path):
    try:
        from fontTools.ttLib import TTFont
        with TTFont(path, fontNumber=0, lazy=True) as font:
            return frozenset((font.getBestCmap() or {}).keys())
    except Exception:
        return None


def font_for_text(resolved, text, inventory=None):
    """Resolve unsupported Unicode before measuring Office's substitute."""
    if not resolved or not resolved.path or str(text).isascii():
        return resolved
    required = {ord(c) for c in str(text) if not c.isspace() and ord(c) >= 32}
    coverage = _font_coverage(resolved.path)
    if coverage is None or required <= coverage:
        return resolved
    from copy import copy
    inv = inventory or get_inventory()
    for family in ("Segoe UI", "Arial", "Microsoft YaHei", "Yu Gothic",
                   "Microsoft JhengHei", "Noto Sans CJK SC", "Noto Sans", "DejaVu Sans", "Segoe UI Emoji"):
        if not inv.has(family):
            continue
        candidate = inv.resolve(family, "sans_body", bold=resolved.bold, italic=resolved.italic)
        if required <= (_font_coverage(candidate.path) or frozenset()):
            candidate = copy(candidate)
            candidate.tracking_em = resolved.tracking_em
            candidate.substituted = True
            candidate.reason = f"{resolved.family} lacks characters required by this text"
            return candidate
    return resolved


def wrap_text_to_width(text: str, resolved: ResolvedFont, size_pt: float,
                       max_width_pt: float, inventory: FontInventory = None,
                       break_long_words: bool = False) -> list:
    """Break `text` into lines that each MEASURE within `max_width_pt`.

    Returns the list of lines. A single word longer than the box is NOT broken
    and NOT mutated — it is returned on its own line and the caller decides
    (shrink the type, widen the box, or report an overflow). Injecting a hyphen
    or a space into a product name, a URL or a file path is *wrong data*, and an
    agent that corrupts the thing it is presenting is worse than one that
    reports a box it could not satisfy.
    """
    if not text:
        return []
    inv = inventory or get_inventory()
    limit = max(1.0, float(max_width_pt))

    if break_long_words:
        # Preserve spaces and indentation. Soft breaks do not insert hyphens
        # into identifiers, URLs, code, or scripts without word separators.
        import re
        import unicodedata
        lines = []
        for paragraph in str(text).replace("\v", "\n").split("\n"):
            if not paragraph:
                lines.append("")
                continue
            current = ""
            for token in re.findall(r"\S+\s*|\s+", paragraph):
                if current and measure_text(current + token, resolved, size_pt, inv)[0] > limit:
                    lines.append(current)
                    current = ""
                if measure_text(token, resolved, size_pt, inv)[0] <= limit:
                    current += token
                    continue
                # Keep combining marks, variation selectors and joiner
                # sequences attached to their base character.
                clusters = []
                for char in token:
                    if clusters and (unicodedata.combining(char) or char in "\ufe0e\ufe0f\u200d" or clusters[-1].endswith("\u200d")):
                        clusters[-1] += char
                    else:
                        clusters.append(char)
                for cluster in clusters:
                    if current and measure_text(current + cluster, resolved, size_pt, inv)[0] > limit:
                        lines.append(current)
                        current = ""
                    current += cluster
            if current:
                lines.append(current)
        return lines

    lines = []
    for paragraph in str(text).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            width, _ = measure_text(candidate, resolved, size_pt, inv)
            if width <= limit or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def line_height_pt(resolved, size_pt, line_spacing=1.18, inventory=None):
    """Reserve the font's ascent and descent, not only its nominal em size."""
    import math
    inv = inventory or get_inventory()
    font = inv.pil_font(resolved, size_pt, dpi=288) if resolved else None
    natural = float(size_pt) * 1.25
    if font is not None:
        try:
            ascent, descent = font.getmetrics()
            natural = (ascent + descent) * 72.0 / 288.0
        except Exception:
            pass
    # Office quantizes some display-font leading to whole points. Rounding
    # upward here prevents that sub-point difference accumulating over lines.
    return float(math.ceil(max(float(size_pt) * float(line_spacing), natural)))


def fit_point_size(text: str, resolved: ResolvedFont, max_width_pt: float,
                   max_height_pt: float, start_pt: float, min_pt: float = 8.0,
                   line_spacing: float = 1.18,
                   inventory: FontInventory = None,
                   break_long_words: bool = False) -> tuple:
    """Largest point size at which `text` fits the box. → (size_pt, lines).

    Searches the half-point grid from `min_pt` to `start_pt`. This is the honest way to make
    "autofit" deterministic: PowerPoint's own autofit is applied at render time
    by the viewer and cannot be measured from the file, so a deck that relies on
    it looks different everywhere. PPTXer solves the size itself and writes an
    explicit one.

    When even `min_pt` does not fit, it returns `min_pt` and the lines anyway —
    the caller MUST treat that as an overflow and act (the audit will flag it).
    Silently returning a size that does not fit is the failure mode this whole
    module exists to prevent.
    """
    import math
    inv = inventory or get_inventory()
    floor = max(1.0, float(min_pt))
    start = max(floor, float(start_pt))
    # Search the same half-point grid, with the exact fractional floor as an
    # additional candidate. Dense cards previously measured every word at
    # hundreds of sizes per trial, making adaptive pagination needlessly slow.
    sizes = sorted(set([floor] + [start - 0.5 * i
                                  for i in range(int(math.floor((start - floor) / 0.5)) + 1)]))

    def measured(size):
        lines = wrap_text_to_width(text, resolved, size, max_width_pt, inv,
                                   break_long_words=break_long_words)
        height = len(lines) * line_height_pt(resolved, size, line_spacing, inv)
        if lines:
            height += TEXT_RENDER_GUARD_PT
        widest = max((measure_text(line, resolved, size, inv)[0] for line in lines), default=0)
        return height <= float(max_height_pt) and widest <= float(max_width_pt), lines

    fits, best_lines = measured(floor)
    if not fits:
        return floor, best_lines
    best = floor
    lo, hi = 1, len(sizes) - 1
    while lo <= hi:
        middle = (lo + hi) // 2
        fits, lines = measured(sizes[middle])
        if fits:
            best, best_lines = sizes[middle], lines
            lo = middle + 1
        else:
            hi = middle - 1
    return best, best_lines


# ─────────────────────────────────────────────────────────────────────────────
# Pairings — a display face and a body face that belong together
#
# Each pairing lists CANDIDATES in preference order; the theme picks the first
# that is actually installed. That is why a pairing can name Orbitron or Bebas
# Neue without risk: if they are absent the ladder walks on, and the deck still
# gets a coherent, measurable pair.
# ─────────────────────────────────────────────────────────────────────────────

PAIRINGS = {
    "swiss": {
        "display": ("Helvetica Neue", "Arial", "Liberation Sans"),
        "body": ("Helvetica Neue", "Arial", "Liberation Sans"),
        "mono": ("Consolas", "Courier New"),
        "note": "Neutral Swiss sans serif with a compact, consistent hierarchy.",
    },
    "blueprint": {
        "display": ("Consolas", "Cascadia Mono", "Courier New"),
        "body": ("Segoe UI", "Arial", "Liberation Sans"),
        "mono": ("Consolas", "Cascadia Mono", "Courier New"),
        "note": "Measured monospaced headings with a readable engineering body.",
    },
    # ---- gaming / esports ---------------------------------------------------
    "esports": {
        "display": ("Nasalization", "Good Times", "Orbitron", "Michroma",
                    "Agency FB", "Bank Gothic", "Arial Black"),
        "body": ("Rajdhani", "Exo 2", "Saira", "Segoe UI", "Arial"),
        "mono": ("Consolas", "Cascadia Mono", "Courier New"),
        "note": "Wide technical caps over a squarish humanist body.",
    },
    "cyberpunk": {
        "display": ("Terminator Two", "Nasalization", "Wallpoet", "Syncopate",
                    "Agency FB", "Impact"),
        "body": ("Chakra Petch", "Rajdhani", "Quantico", "Segoe UI", "Arial"),
        "mono": ("OCR A Extended", "Consolas", "Courier New"),
        "note": "Glitched display caps, technical body, terminal mono.",
    },
    "arcade": {
        "display": ("Good Times", "Bauhaus 93", "Audiowide", "Impact",
                    "Arial Black"),
        "body": ("Verdana", "Trebuchet MS", "Segoe UI", "Arial"),
        "mono": ("Consolas", "Courier New"),
        "note": "Chunky retro display over a friendly, very legible body.",
    },
    "fantasy_rpg": {
        "display": ("Old English Text MT", "Cinzel", "Castellar", "Felix Titling",
                    "Perpetua Titling MT", "Georgia"),
        "body": ("Sitka Text", "Constantia", "Cambria", "Georgia",
                 "Times New Roman"),
        "mono": ("Consolas", "Courier New"),
        "note": "Carved titling over a warm old-style serif.",
    },
    "military_tactical": {
        "display": ("Agency FB", "Bank Gothic", "Stencil", "Oswald",
                    "Franklin Gothic Heavy", "Arial Narrow"),
        "body": ("Franklin Gothic Book", "Arial Narrow", "Segoe UI", "Arial"),
        "mono": ("OCR A Extended", "Consolas", "Courier New"),
        "note": "Condensed military caps, tight utilitarian body.",
    },
    # ---- marketing ----------------------------------------------------------
    "brand_bold": {
        "display": ("Anton", "Bebas Neue", "Antonio", "Oswald", "Impact",
                    "Haettenschweiler", "Arial Black"),
        "body": ("Montserrat", "Segoe UI", "Calibri", "Arial"),
        "mono": ("Consolas", "Courier New"),
        "note": "Poster-scale condensed display over a geometric sans.",
    },
    "startup_pitch": {
        "display": ("Montserrat", "Segoe UI Semibold", "Century Gothic",
                    "Corbel", "Segoe UI", "Arial"),
        "body": ("Segoe UI", "Calibri", "Corbel", "Arial"),
        "mono": ("Consolas", "Cascadia Mono", "Courier New"),
        "note": "Clean geometric sans throughout — the VC-deck default.",
    },
    "luxury": {
        "display": ("Didot", "Bodoni MT", "Playfair Display",
                    "Perpetua Titling MT", "Copperplate Gothic Light", "Georgia"),
        "body": ("Garamond", "Palatino Linotype", "Book Antiqua", "Georgia",
                 "Times New Roman"),
        "mono": ("Consolas", "Courier New"),
        "note": "High-contrast didone over a quiet old-style serif.",
    },
    "editorial": {
        "display": ("Playfair Display", "Georgia", "Bodoni MT",
                    "Bookman Old Style", "Times New Roman"),
        "body": ("Georgia", "Constantia", "Cambria", "Times New Roman"),
        "mono": ("Consolas", "Courier New"),
        "note": "Magazine feature: serif display, serif body.",
    },
    "friendly_consumer": {
        "display": ("Arial Rounded MT Bold", "Nunito", "Quicksand",
                    "Century Gothic", "Verdana", "Trebuchet MS"),
        "body": ("Verdana", "Trebuchet MS", "Segoe UI", "Calibri", "Arial"),
        "mono": ("Consolas", "Courier New"),
        "note": "Rounded, warm, approachable — consumer and education.",
    },
    # ---- corporate / technical ---------------------------------------------
    "corporate": {
        "display": ("Segoe UI Semibold", "Calibri Light", "Franklin Gothic Demi",
                    "Corbel", "Arial"),
        "body": ("Segoe UI", "Calibri", "Corbel", "Arial"),
        "mono": ("Consolas", "Courier New"),
        "note": "The safe boardroom default. Ships everywhere.",
    },
    "technical": {
        "display": ("Bahnschrift", "Segoe UI Semibold", "Franklin Gothic Demi",
                    "Arial"),
        "body": ("Segoe UI", "Calibri", "Arial"),
        "mono": ("Consolas", "Cascadia Mono", "JetBrains Mono", "Courier New"),
        "note": "Engineering-report clarity with a strong mono.",
    },
    "scientific": {
        "display": ("Cambria", "Constantia", "Georgia", "Times New Roman"),
        "body": ("Cambria", "Constantia", "Georgia", "Times New Roman"),
        "mono": ("Consolas", "Courier New"),
        "note": "Journal-style serif; maths-friendly.",
    },
    "minimal": {
        "display": ("Segoe UI Light", "Calibri Light", "Century Gothic",
                    "Corbel", "Arial"),
        "body": ("Segoe UI", "Calibri", "Arial"),
        "mono": ("Consolas", "Courier New"),
        "note": "Thin, quiet, lots of air.",
    },
    "brutalist": {
        "display": ("Arial Black", "Impact", "Haettenschweiler",
                    "Franklin Gothic Heavy"),
        "body": ("Arial", "Helvetica", "Segoe UI"),
        "mono": ("Courier New", "Consolas"),
        "note": "Raw, heavy, unapologetic. Big type, hard edges.",
    },
}


def resolve_pairing(name: str, inventory: FontInventory = None) -> dict:
    """Resolve a pairing's candidate lists to REAL installed faces.

    Returns {'display': ResolvedFont, 'body': ResolvedFont, 'mono': ResolvedFont,
    'pairing': name, 'note': str, 'substitutions': [str, ...]}.

    The `substitutions` list is what the agent reports: it is how Angela finds
    out that a deck asked for Orbitron on a machine that does not have it.
    """
    inv = inventory or get_inventory()
    key = (name or "corporate").strip().lower().replace("-", "_").replace(" ", "_")
    spec = PAIRINGS.get(key) or PAIRINGS["corporate"]

    def first_installed(candidates, category):
        for cand in candidates:
            if inv.has(cand):
                return inv.resolve(cand, category)
        # Nothing in the list is installed — let resolve() run its own ladder.
        return inv.resolve(candidates[0] if candidates else "", category)

    display = first_installed(spec["display"], _display_category(key))
    body = first_installed(spec["body"], "sans_body")
    mono = first_installed(spec["mono"], "mono")

    subs = [f.reason for f in (display, body, mono) if f.substituted and f.reason]
    return {
        "pairing": key,
        "display": display,
        "body": body,
        "mono": mono,
        "note": spec.get("note", ""),
        "substitutions": subs,
    }


def _display_category(pairing_key: str) -> str:
    if pairing_key == "blueprint":
        return "mono"
    if pairing_key in ("esports", "cyberpunk", "military_tactical"):
        return "display_tech"
    if pairing_key in ("brand_bold", "arcade", "brutalist"):
        return "display_impact"
    if pairing_key in ("luxury", "editorial", "fantasy_rpg"):
        return "display_elegant"
    if pairing_key in ("scientific",):
        return "serif_body"
    return "sans_body"
