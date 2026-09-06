# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer colour science — the pigment bench of the document composer.

WHY THIS MODULE EXISTS
----------------------
Until 2026-09 PDFer had exactly ONE look: ``#7F1D1D`` headings on cream
``#FDF6E3`` code panels with ``#F3E9D2`` table headers — a single brown/ochre
scheme hardcoded into ``DEFAULT_CSS``, applied to a quantum-mechanics paper and
a birthday menu alike. A document composer that cannot change its colours is a
rubber stamp, not a composer.

Colour is not decoration here; it is *legibility*, and legibility is a
measurable quantity. So this module is deliberately built on real colour
science rather than a table of pretty hex codes:

* **sRGB ⇄ linear ⇄ XYZ ⇄ OKLab/OKLCh.** Every mix, tint, shade and gradient
  ramp is computed in **OKLab**, not in sRGB. Interpolating ``#0000FF`` →
  ``#FFFF00`` in naive sRGB marches through a dead grey mud at the midpoint;
  in OKLab it stays luminous the whole way. Gradients are the single most
  visible thing Angela asked for, and a gradient computed in the wrong space
  looks cheap no matter how good the endpoints are.
* **WCAG 2.1 relative luminance + contrast ratio.** Every foreground PDFer
  places is checked against the background it lands on, and `ensure_contrast`
  will walk a colour's lightness until it *passes* — so a generated theme can
  never ship white-on-pale-yellow. This is the hard floor beneath every
  aesthetic choice in `pdfer_theme.py`.
* **Harmony generation from ONE seed.** ``predominant_color`` (Angela's new
  parameter) is a single colour; a document needs ~24 that agree with it.
  `palette_from_seed` derives the whole set by rotating hue in OKLCh and
  solving for lightness against the contrast floor — which is why passing one
  colour produces a coherent document rather than one coloured heading.

CONTRACTS (do NOT weaken)
-------------------------
1. **NOTHING HERE RAISES INTO A CALLER.** Every parser fails open to a stated
   fallback. A malformed ``predominant_color`` from a chat prompt must produce
   a slightly-wrong-but-beautiful document, never a traceback and never a
   refusal — the user asked for a PDF, not a colour lecture.
2. **Contrast is a FLOOR, not a preference.** `Palette.validated()` raises the
   text colour until it clears the floor. A theme author may pick any hue;
   they may not pick an unreadable one.
3. **Stdlib only.** Pool agents never import ``agent.*`` and must behave
   identically frozen and from source, so all of this is pure Python + math.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import colorsys
import math
import re

__all__ = [
    "Color",
    "Palette",
    "parse_color",
    "clamp",
    "contrast_ratio",
    "relative_luminance",
    "ensure_contrast",
    "mix",
    "ramp",
    "palette_from_seed",
    "harmonies",
    "CSS_COLORS",
    "WCAG_AA_NORMAL",
    "WCAG_AA_LARGE",
    "WCAG_AAA_NORMAL",
]


# ─────────────────────────────────────────────────────────────────────────
#  Contrast thresholds (WCAG 2.1 §1.4.3 / §1.4.6)
#
#  These are the numbers the whole theme system is anchored to. "Large" is
#  ≥18pt, or ≥14pt bold — which is why headings may legitimately sit at 3.0
#  while body copy may not.
# ─────────────────────────────────────────────────────────────────────────
WCAG_AA_LARGE = 3.0
WCAG_AA_NORMAL = 4.5
WCAG_AAA_NORMAL = 7.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp *value* into [low, high]. Total: never raises, even on NaN."""
    try:
        if value != value:          # NaN — the one float that fails every test
            return low
        return low if value < low else (high if value > high else float(value))
    except Exception:
        return low


# ─────────────────────────────────────────────────────────────────────────
#  CSS named colours
#
#  A working subset of the CSS Color Module Level 4 list — the names a human
#  or an LLM actually types ("midnightblue", "teal", "crimson"). Kept as a
#  plain dict of ints so a lookup costs nothing and cannot go stale.
# ─────────────────────────────────────────────────────────────────────────
CSS_COLORS = {
    "aliceblue": 0xF0F8FF, "antiquewhite": 0xFAEBD7, "aqua": 0x00FFFF,
    "aquamarine": 0x7FFFD4, "azure": 0xF0FFFF, "beige": 0xF5F5DC,
    "bisque": 0xFFE4C4, "black": 0x000000, "blanchedalmond": 0xFFEBCD,
    "blue": 0x0000FF, "blueviolet": 0x8A2BE2, "brown": 0xA52A2A,
    "burlywood": 0xDEB887, "cadetblue": 0x5F9EA0, "chartreuse": 0x7FFF00,
    "chocolate": 0xD2691E, "coral": 0xFF7F50, "cornflowerblue": 0x6495ED,
    "cornsilk": 0xFFF8DC, "crimson": 0xDC143C, "cyan": 0x00FFFF,
    "darkblue": 0x00008B, "darkcyan": 0x008B8B, "darkgoldenrod": 0xB8860B,
    "darkgray": 0xA9A9A9, "darkgreen": 0x006400, "darkgrey": 0xA9A9A9,
    "darkkhaki": 0xBDB76B, "darkmagenta": 0x8B008B, "darkolivegreen": 0x556B2F,
    "darkorange": 0xFF8C00, "darkorchid": 0x9932CC, "darkred": 0x8B0000,
    "darksalmon": 0xE9967A, "darkseagreen": 0x8FBC8F, "darkslateblue": 0x483D8B,
    "darkslategray": 0x2F4F4F, "darkslategrey": 0x2F4F4F,
    "darkturquoise": 0x00CED1, "darkviolet": 0x9400D3, "deeppink": 0xFF1493,
    "deepskyblue": 0x00BFFF, "dimgray": 0x696969, "dimgrey": 0x696969,
    "dodgerblue": 0x1E90FF, "firebrick": 0xB22222, "floralwhite": 0xFFFAF0,
    "forestgreen": 0x228B22, "fuchsia": 0xFF00FF, "gainsboro": 0xDCDCDC,
    "ghostwhite": 0xF8F8FF, "gold": 0xFFD700, "goldenrod": 0xDAA520,
    "gray": 0x808080, "green": 0x008000, "greenyellow": 0xADFF2F,
    "grey": 0x808080, "honeydew": 0xF0FFF0, "hotpink": 0xFF69B4,
    "indianred": 0xCD5C5C, "indigo": 0x4B0082, "ivory": 0xFFFFF0,
    "khaki": 0xF0E68C, "lavender": 0xE6E6FA, "lavenderblush": 0xFFF0F5,
    "lawngreen": 0x7CFC00, "lemonchiffon": 0xFFFACD, "lightblue": 0xADD8E6,
    "lightcoral": 0xF08080, "lightcyan": 0xE0FFFF,
    "lightgoldenrodyellow": 0xFAFAD2, "lightgray": 0xD3D3D3,
    "lightgreen": 0x90EE90, "lightgrey": 0xD3D3D3, "lightpink": 0xFFB6C1,
    "lightsalmon": 0xFFA07A, "lightseagreen": 0x20B2AA,
    "lightskyblue": 0x87CEFA, "lightslategray": 0x778899,
    "lightslategrey": 0x778899, "lightsteelblue": 0xB0C4DE,
    "lightyellow": 0xFFFFE0, "lime": 0x00FF00, "limegreen": 0x32CD32,
    "linen": 0xFAF0E6, "magenta": 0xFF00FF, "maroon": 0x800000,
    "mediumaquamarine": 0x66CDAA, "mediumblue": 0x0000CD,
    "mediumorchid": 0xBA55D3, "mediumpurple": 0x9370DB,
    "mediumseagreen": 0x3CB371, "mediumslateblue": 0x7B68EE,
    "mediumspringgreen": 0x00FA9A, "mediumturquoise": 0x48D1CC,
    "mediumvioletred": 0xC71585, "midnightblue": 0x191970,
    "mintcream": 0xF5FFFA, "mistyrose": 0xFFE4E1, "moccasin": 0xFFE4B5,
    "navajowhite": 0xFFDEAD, "navy": 0x000080, "oldlace": 0xFDF5E6,
    "olive": 0x808000, "olivedrab": 0x6B8E23, "orange": 0xFFA500,
    "orangered": 0xFF4500, "orchid": 0xDA70D6, "palegoldenrod": 0xEEE8AA,
    "palegreen": 0x98FB98, "paleturquoise": 0xAFEEEE,
    "palevioletred": 0xDB7093, "papayawhip": 0xFFEFD5, "peachpuff": 0xFFDAB9,
    "peru": 0xCD853F, "pink": 0xFFC0CB, "plum": 0xDDA0DD,
    "powderblue": 0xB0E0E6, "purple": 0x800080, "rebeccapurple": 0x663399,
    "red": 0xFF0000, "rosybrown": 0xBC8F8F, "royalblue": 0x4169E1,
    "saddlebrown": 0x8B4513, "salmon": 0xFA8072, "sandybrown": 0xF4A460,
    "seagreen": 0x2E8B57, "seashell": 0xFFF5EE, "sienna": 0xA0522D,
    "silver": 0xC0C0C0, "skyblue": 0x87CEEB, "slateblue": 0x6A5ACD,
    "slategray": 0x708090, "slategrey": 0x708090, "snow": 0xFFFAFA,
    "springgreen": 0x00FF7F, "steelblue": 0x4682B4, "tan": 0xD2B48C,
    "teal": 0x008080, "thistle": 0xD8BFD8, "tomato": 0xFF6347,
    "turquoise": 0x40E0D0, "violet": 0xEE82EE, "wheat": 0xF5DEB3,
    "white": 0xFFFFFF, "whitesmoke": 0xF5F5F5, "yellow": 0xFFFF00,
    "yellowgreen": 0x9ACD32,
    # ── Convenience names an LLM or a human reaches for that CSS lacks ──
    "obsidian": 0x0B0F17, "charcoal": 0x1F2933, "graphite": 0x2D3339,
    "ink": 0x101418, "slate": 0x334155, "cobalt": 0x0047AB,
    "emerald": 0x10B981, "amber": 0xF59E0B, "ruby": 0xE11D48,
    "sapphire": 0x0F52BA, "cream": 0xFDFBF5, "parchment": 0xF6F1E4,
    "sepia": 0x704214, "bone": 0xE3DAC9, "oxblood": 0x4A0404,
    "mint": 0x98FF98, "peach": 0xFFE5B4, "lilac": 0xC8A2C8,
}


# ─────────────────────────────────────────────────────────────────────────
#  Colour parsing
# ─────────────────────────────────────────────────────────────────────────
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
_FUNC_RE = re.compile(
    r"^(rgba?|hsla?|oklch|gray|grey)\s*\(([^)]*)\)$", re.IGNORECASE)


def _split_args(raw: str) -> list:
    """Split ``12, 34, 56 / 0.5`` or ``12 34 56`` into component strings."""
    cleaned = raw.replace("/", " ").replace(",", " ")
    return [tok for tok in cleaned.split() if tok]


def _num(token: str, scale: float = 1.0) -> float:
    """Parse ``50%`` / ``0.5`` / ``128`` into a float. Fails open to 0.0."""
    try:
        token = token.strip()
        if token.endswith("%"):
            return float(token[:-1]) / 100.0
        value = float(token)
        return value / scale if scale != 1.0 else value
    except Exception:
        return 0.0


class Color:
    """An sRGB colour with perceptual (OKLab/OKLCh) operations.

    Stored as three floats in [0, 1] plus alpha. Immutable in spirit: every
    operation returns a NEW Color, so a palette can never be mutated from
    under a renderer that already read it.
    """

    __slots__ = ("r", "g", "b", "a")

    def __init__(self, r: float, g: float, b: float, a: float = 1.0):
        self.r = clamp(r)
        self.g = clamp(g)
        self.b = clamp(b)
        self.a = clamp(a)

    # ── constructors ────────────────────────────────────────────────────
    @classmethod
    def from_hex(cls, text: str, fallback: str = "#000000") -> "Color":
        """``#RGB`` / ``#RGBA`` / ``#RRGGBB`` / ``#RRGGBBAA`` → Color."""
        match = _HEX_RE.match((text or "").strip())
        if not match:
            return cls.from_hex(fallback) if text != fallback else cls(0, 0, 0)
        digits = match.group(1)
        try:
            if len(digits) in (3, 4):
                parts = [int(ch * 2, 16) / 255.0 for ch in digits]
            elif len(digits) in (6, 8):
                parts = [int(digits[i:i + 2], 16) / 255.0
                         for i in range(0, len(digits), 2)]
            else:
                return cls.from_hex(fallback) if text != fallback else cls(0, 0, 0)
        except Exception:
            return cls(0, 0, 0)
        if len(parts) == 3:
            parts.append(1.0)
        return cls(*parts[:4])

    @classmethod
    def from_int(cls, value: int) -> "Color":
        return cls(((value >> 16) & 0xFF) / 255.0,
                   ((value >> 8) & 0xFF) / 255.0,
                   (value & 0xFF) / 255.0)

    @classmethod
    def from_hsl(cls, h: float, s: float, lightness: float,
                 a: float = 1.0) -> "Color":
        """*h* in degrees, *s* and *lightness* in [0, 1]."""
        r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0,
                                      clamp(lightness), clamp(s))
        return cls(r, g, b, a)

    @classmethod
    def from_oklab(cls, lightness: float, a_axis: float, b_axis: float,
                   alpha: float = 1.0) -> "Color":
        """OKLab → sRGB (Björn Ottosson's matrices, gamut-clipped)."""
        l_ = lightness + 0.3963377774 * a_axis + 0.2158037573 * b_axis
        m_ = lightness - 0.1055613458 * a_axis - 0.0638541728 * b_axis
        s_ = lightness - 0.0894841775 * a_axis - 1.2914855480 * b_axis
        l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
        lr = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
        lg = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
        lb = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3
        return cls(_linear_to_srgb(lr), _linear_to_srgb(lg),
                   _linear_to_srgb(lb), alpha)

    @classmethod
    def from_oklch(cls, lightness: float, chroma: float, hue_deg: float,
                   alpha: float = 1.0) -> "Color":
        rad = math.radians(hue_deg % 360.0)
        return cls.from_oklab(lightness, chroma * math.cos(rad),
                              chroma * math.sin(rad), alpha)

    # ── exporters ───────────────────────────────────────────────────────
    @property
    def hex(self) -> str:
        return "#%02X%02X%02X" % (int(round(self.r * 255)),
                                  int(round(self.g * 255)),
                                  int(round(self.b * 255)))

    @property
    def rgb255(self) -> tuple:
        return (int(round(self.r * 255)), int(round(self.g * 255)),
                int(round(self.b * 255)))

    @property
    def rgba255(self) -> tuple:
        return self.rgb255 + (int(round(self.a * 255)),)

    def as_reportlab(self):
        """A ``reportlab.lib.colors.Color``. Imported lazily on purpose: this
        module must stay usable (for tests, for the auditor) on a machine
        where ReportLab is missing."""
        from reportlab.lib.colors import Color as _RLColor
        return _RLColor(self.r, self.g, self.b, alpha=self.a)

    def css(self) -> str:
        if self.a >= 0.999:
            return self.hex
        return "rgba(%d, %d, %d, %.3f)" % (self.rgb255 + (self.a,))

    # ── colour-space conversions ────────────────────────────────────────
    def to_hsl(self) -> tuple:
        h, lightness, s = colorsys.rgb_to_hls(self.r, self.g, self.b)
        return (h * 360.0, s, lightness)

    def to_oklab(self) -> tuple:
        lr, lg, lb = (_srgb_to_linear(self.r), _srgb_to_linear(self.g),
                      _srgb_to_linear(self.b))
        l_ = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
        m_ = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
        s_ = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
        lc = _cbrt(l_)
        mc = _cbrt(m_)
        sc = _cbrt(s_)
        return (0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
                1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
                0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc)

    def to_oklch(self) -> tuple:
        lightness, a_axis, b_axis = self.to_oklab()
        chroma = math.hypot(a_axis, b_axis)
        hue = math.degrees(math.atan2(b_axis, a_axis)) % 360.0
        return (lightness, chroma, hue)

    # ── perceptual operations (all in OKLCh) ────────────────────────────
    def lighten(self, amount: float) -> "Color":
        """Raise OKLab lightness by *amount* (0..1). Hue and chroma survive."""
        lightness, chroma, hue = self.to_oklch()
        return Color.from_oklch(clamp(lightness + amount), chroma, hue, self.a)

    def darken(self, amount: float) -> "Color":
        return self.lighten(-amount)

    def saturate(self, factor: float) -> "Color":
        lightness, chroma, hue = self.to_oklch()
        return Color.from_oklch(lightness, max(0.0, chroma * factor), hue, self.a)

    def desaturate(self, factor: float) -> "Color":
        return self.saturate(max(0.0, 1.0 - factor))

    def rotate(self, degrees: float) -> "Color":
        lightness, chroma, hue = self.to_oklch()
        return Color.from_oklch(lightness, chroma, hue + degrees, self.a)

    def with_lightness(self, lightness: float) -> "Color":
        _, chroma, hue = self.to_oklch()
        return Color.from_oklch(clamp(lightness), chroma, hue, self.a)

    def with_chroma(self, chroma: float) -> "Color":
        lightness, _, hue = self.to_oklch()
        return Color.from_oklch(lightness, max(0.0, chroma), hue, self.a)

    def with_alpha(self, alpha: float) -> "Color":
        return Color(self.r, self.g, self.b, alpha)

    def over(self, backdrop: "Color") -> "Color":
        """Composite self over *backdrop* — flatten alpha into an opaque hex.

        PDF viewers honour real alpha, but a *table cell background* or a
        generated PNG needs a concrete colour. Everywhere PDFer wants "10 %
        of the accent on the page", this is what produces it.
        """
        alpha = self.a
        return Color(self.r * alpha + backdrop.r * (1 - alpha),
                     self.g * alpha + backdrop.g * (1 - alpha),
                     self.b * alpha + backdrop.b * (1 - alpha), 1.0)

    # ── measurement ─────────────────────────────────────────────────────
    @property
    def luminance(self) -> float:
        return relative_luminance(self)

    @property
    def is_dark(self) -> bool:
        """Would white text sit better on this than black text?

        The 0.179 threshold is the luminance at which contrast against white
        and against black are exactly equal — the mathematically correct
        switch point, not the eyeballed 0.5 that makes mid-blues unreadable.
        """
        return self.luminance < 0.179

    def contrast(self, other: "Color") -> float:
        return contrast_ratio(self, other)

    def readable_on(self, background: "Color",
                    floor: float = WCAG_AA_NORMAL) -> bool:
        return self.contrast(background) >= floor

    # ── dunder ──────────────────────────────────────────────────────────
    def __repr__(self) -> str:
        return "Color(%s)" % self.hex

    def __eq__(self, other) -> bool:
        return isinstance(other, Color) and self.rgba255 == other.rgba255

    def __hash__(self) -> int:
        return hash(self.rgba255)


# ─────────────────────────────────────────────────────────────────────────
#  Free functions
# ─────────────────────────────────────────────────────────────────────────
def _srgb_to_linear(channel: float) -> float:
    return (channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(channel: float) -> float:
    if channel <= 0.0031308:
        return clamp(channel * 12.92)
    return clamp(1.055 * (max(channel, 0.0) ** (1 / 2.4)) - 0.055)


def _cbrt(value: float) -> float:
    return math.copysign(abs(value) ** (1.0 / 3.0), value)


def relative_luminance(color: "Color") -> float:
    """WCAG 2.1 relative luminance — the basis of every contrast decision."""
    return (0.2126 * _srgb_to_linear(color.r)
            + 0.7152 * _srgb_to_linear(color.g)
            + 0.0722 * _srgb_to_linear(color.b))


def contrast_ratio(first: "Color", second: "Color") -> float:
    """WCAG contrast ratio in [1, 21]. Order-independent."""
    lum_a, lum_b = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def parse_color(value, fallback="#000000") -> "Color":
    """Parse ANYTHING a human, an LLM or a config file might hand us.

    Accepts ``#abc``, ``#aabbcc``, ``#aabbccdd``, ``rgb(1,2,3)``,
    ``rgba(1,2,3,.5)``, ``hsl(210, 50%, 40%)``, ``oklch(0.7 0.15 250)``,
    ``gray(0.5)``, a CSS colour name, an ``int``, an ``(r, g, b)`` tuple, or
    an existing ``Color``.

    FAIL-OPEN, ALWAYS: an unparseable value returns *fallback*, never raises.
    This is the function that stands between a chat prompt saying
    ``predominant_color='dark bluish'`` and a crashed render.
    """
    if isinstance(value, Color):
        return value
    if isinstance(value, int):
        return Color.from_int(value)
    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        try:
            nums = [float(component) for component in value]
            if max(nums[:3]) > 1.0:
                nums = [component / 255.0 for component in nums]
            return Color(*nums[:4]) if len(nums) == 4 else Color(*nums[:3])
        except Exception:
            return parse_color(fallback, "#000000")

    text = str(value or "").strip().lower()
    if not text:
        return parse_color(fallback, "#000000")

    # Named colour — checked BEFORE hex so "tan" is a colour, not bad hex.
    if text in CSS_COLORS:
        return Color.from_int(CSS_COLORS[text])

    if _HEX_RE.match(text.lstrip("#")) and (text.startswith("#")
                                            or len(text.lstrip("#")) in (6, 8)):
        return Color.from_hex(text)

    func = _FUNC_RE.match(text)
    if func:
        kind = func.group(1).lower()
        args = _split_args(func.group(2))
        try:
            if kind in ("rgb", "rgba") and len(args) >= 3:
                # ``_num`` already folded a ``50%`` into 0.5; a bare 0..255
                # integer has NOT been normalised, so anything above 1 is a
                # byte value. (0 and 1 are ambiguous and read as "off/full",
                # which is what every real ``rgb(0,0,0)`` means anyway.)
                nums = [_num(tok) for tok in args[:3]]
                nums = [component if component <= 1.0 else component / 255.0
                        for component in nums]
                alpha = _num(args[3]) if len(args) > 3 else 1.0
                return Color(nums[0], nums[1], nums[2], alpha)
            if kind in ("hsl", "hsla") and len(args) >= 3:
                hue = _num(args[0].rstrip("deg"))
                if hue <= 1.0 and "%" not in args[0] and "." in args[0]:
                    hue *= 360.0
                sat, light = _num(args[1]), _num(args[2])
                alpha = _num(args[3]) if len(args) > 3 else 1.0
                return Color.from_hsl(hue if hue > 1 else hue * 360.0,
                                      sat, light, alpha)
            if kind == "oklch" and len(args) >= 3:
                return Color.from_oklch(_num(args[0]), _num(args[1]),
                                        _num(args[2].rstrip("deg")),
                                        _num(args[3]) if len(args) > 3 else 1.0)
            if kind in ("gray", "grey") and args:
                level = _num(args[0])
                level = level if level <= 1.0 else level / 255.0
                return Color(level, level, level)
        except Exception:
            pass

    # Last resort: a name with spaces/punctuation ("dark blue", "sea-green").
    squashed = re.sub(r"[^a-z]", "", text)
    if squashed in CSS_COLORS:
        return Color.from_int(CSS_COLORS[squashed])

    return parse_color(fallback, "#000000") if value != fallback else Color(0, 0, 0)


def mix(first: "Color", second: "Color", ratio: float = 0.5,
        space: str = "oklab") -> "Color":
    """Blend two colours. *ratio* 0 → all *first*, 1 → all *second*.

    ``space='oklab'`` (the default and the right answer) keeps the midpoint
    luminous. ``space='srgb'`` is offered only for the rare case where a
    caller must match some other tool's naive blend.
    """
    ratio = clamp(ratio)
    if space == "srgb":
        return Color(first.r + (second.r - first.r) * ratio,
                     first.g + (second.g - first.g) * ratio,
                     first.b + (second.b - first.b) * ratio,
                     first.a + (second.a - first.a) * ratio)
    l1, a1, b1 = first.to_oklab()
    l2, a2, b2 = second.to_oklab()
    return Color.from_oklab(l1 + (l2 - l1) * ratio,
                            a1 + (a2 - a1) * ratio,
                            b1 + (b2 - b1) * ratio,
                            first.a + (second.a - first.a) * ratio)


def ramp(start: "Color", end: "Color", steps: int = 16,
         space: str = "oklab", ease: str = "linear") -> list:
    """A perceptually even gradient ramp of *steps* colours, inclusive.

    This is what every gradient PDFer draws is built from — the cover wash,
    the heading rules, the table-header sweep, the section dividers.

    *ease* shapes the distribution: ``linear`` for a plain wash,
    ``ease_in_out`` for a gradient that lingers at both ends (much better for
    a page background, where the eye should not notice a "seam"), ``ease_out``
    for a rule that fades away.
    """
    steps = max(2, int(steps or 2))
    easings = {
        "linear": lambda t: t,
        "ease_in": lambda t: t * t,
        "ease_out": lambda t: 1.0 - (1.0 - t) ** 2,
        "ease_in_out": lambda t: (2 * t * t if t < 0.5
                                  else 1.0 - ((-2 * t + 2) ** 2) / 2),
        "sine": lambda t: 0.5 - 0.5 * math.cos(math.pi * t),
    }
    shape = easings.get(ease, easings["linear"])
    return [mix(start, end, shape(index / float(steps - 1)), space=space)
            for index in range(steps)]


#: Aim this fraction ABOVE the requested floor.
#
#: ⚠️ NOT a fudge factor — a measurement one. `ensure_contrast` used to stop
#: the instant it TOUCHED the floor, so a role could land at exactly 4.50:1 on
#: paper. The rendered-page auditor then rasterises the glyph, antialiasing
#: shifts the sampled ink by a hundredth, and the same colour measures 4.48:1
#: — a failure report for a colour the palette had certified. Sitting exactly
#: on a threshold is a bug regardless of which side of it you land on, so the
#: search overshoots by 4 % and the certification survives contact with a
#: renderer.
CONTRAST_SAFETY = 1.04


def ensure_contrast(foreground: "Color", background: "Color",
                    floor: float = WCAG_AA_NORMAL,
                    preserve_hue: bool = True) -> "Color":
    """Return a colour like *foreground* that PASSES *floor* on *background*.

    THE GUARANTEE THIS FUNCTION MAKES is the reason a generated theme can be
    trusted: whatever hue a theme author (or the LLM, or Angela's
    ``predominant_color``) proposes, the text that lands on the page is
    legible. It walks OKLab lightness away from the background — up if the
    background is dark, down if it is light — in fine steps, and only
    surrenders to pure white/black if nothing in between clears the bar.

    *preserve_hue* keeps chroma and hue intact so the result still belongs to
    the palette; setting it False allows a full desaturation, which is the
    honest last resort for a hue with no legible form at that lightness
    (a saturated yellow on white, for instance).
    """
    target = floor * CONTRAST_SAFETY
    if foreground.contrast(background) >= target:
        return foreground

    lightness, chroma, hue = foreground.to_oklch()
    going_up = background.is_dark
    best, best_ratio = foreground, foreground.contrast(background)

    for step in range(1, 101):
        offset = step * 0.01
        candidate_l = clamp(lightness + offset) if going_up else clamp(lightness - offset)
        candidate = Color.from_oklch(candidate_l, chroma, hue, foreground.a)
        ratio = candidate.contrast(background)
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
        if ratio >= target:
            return candidate

    if not preserve_hue:
        # Bleed the chroma out: a muted colour has more lightness range.
        for chroma_scale in (0.6, 0.35, 0.15, 0.0):
            for step in range(0, 101):
                offset = step * 0.01
                candidate_l = clamp(lightness + offset) if going_up else clamp(lightness - offset)
                candidate = Color.from_oklch(candidate_l, chroma * chroma_scale,
                                             hue, foreground.a)
                if candidate.contrast(background) >= target:
                    return candidate

    # Nothing in the hue works. Legibility outranks the palette, always.
    monochrome = Color(1, 1, 1, foreground.a) if going_up else Color(0, 0, 0, foreground.a)
    return monochrome if monochrome.contrast(background) > best_ratio else best


def harmonies(seed: "Color") -> dict:
    """Classical colour harmonies around *seed*, computed in OKLCh.

    Used by `palette_from_seed` and offered to the theme layer so a document
    can pick a *relationship* ("give me the triadic partner for callouts")
    rather than a hardcoded second colour.
    """
    return {
        "complement": seed.rotate(180),
        "analogous_warm": seed.rotate(30),
        "analogous_cool": seed.rotate(-30),
        "triadic_a": seed.rotate(120),
        "triadic_b": seed.rotate(240),
        "split_a": seed.rotate(150),
        "split_b": seed.rotate(210),
        "tetradic": seed.rotate(90),
        "square": seed.rotate(270),
    }


# ─────────────────────────────────────────────────────────────────────────
#  Palette — the full set of roles a document needs
# ─────────────────────────────────────────────────────────────────────────
class Palette:
    """Every colour role a PDFer document uses, in one validated object.

    A theme names these; the renderer only ever asks for a *role*
    (``palette.table_header_bg``), never for a literal hex. That indirection
    is what made it possible to replace the old brown scheme everywhere at
    once instead of hunting hardcoded ``#7F1D1D`` through a renderer.
    """

    ROLES = (
        "background", "background_alt", "surface", "surface_alt",
        "text", "text_muted", "text_inverse",
        "primary", "primary_soft", "secondary", "accent",
        "border", "border_soft", "rule",
        "link", "code_bg", "code_fg", "code_border",
        "table_header_bg", "table_header_fg", "table_row_alt", "table_border",
        "quote_bar", "quote_bg", "quote_fg",
        "success", "warning", "danger", "info",
        "heading_1", "heading_2", "heading_3", "heading_4",
        "caption", "footer", "cover_from", "cover_to", "ornament",
    )

    def __init__(self, **roles):
        for role in self.ROLES:
            setattr(self, role, parse_color(roles.get(role, "#000000")))
        self.dark = bool(roles.get("dark", self.background.is_dark))
        self.name = str(roles.get("name", "custom"))

    # ── access ──────────────────────────────────────────────────────────
    def get(self, role: str, fallback: str = "#000000") -> "Color":
        return getattr(self, role, None) or parse_color(fallback)

    def as_dict(self) -> dict:
        out = {role: getattr(self, role).hex for role in self.ROLES}
        out["dark"] = self.dark
        out["name"] = self.name
        return out

    def copy_with(self, **overrides) -> "Palette":
        merged = {role: getattr(self, role) for role in self.ROLES}
        merged["dark"] = self.dark
        merged["name"] = self.name
        merged.update(overrides)
        return Palette(**merged)

    # ── the legibility gate ─────────────────────────────────────────────
    def validated(self, body_floor: float = WCAG_AA_NORMAL,
                  large_floor: float = WCAG_AA_LARGE) -> "Palette":
        """Force every text role to clear its contrast floor.

        Called ONCE, at the end of theme assembly, on whatever the theme
        catalog, the seed derivation and the LLM between them produced. After
        this the renderer may place any role on its stated ground and know it
        is readable — which is the whole promise.
        """
        bg, surf = self.background, self.surface
        fixed = {
            "text": ensure_contrast(self.text, bg, body_floor, preserve_hue=False),
            "text_muted": ensure_contrast(self.text_muted, bg, large_floor),
            "heading_1": ensure_contrast(self.heading_1, bg, large_floor),
            "heading_2": ensure_contrast(self.heading_2, bg, large_floor),
            "heading_3": ensure_contrast(self.heading_3, bg, large_floor),
            "heading_4": ensure_contrast(self.heading_4, bg, large_floor),
            "link": ensure_contrast(self.link, bg, body_floor),
            # ⚠️ CAPTIONS AND FOOTERS ARE **SMALL** TEXT — they take the FULL
            # body floor, not the large-text one.
            #
            # The first version gave captions 3.0 and footers 2.5, on the
            # convention that page furniture is "supposed to be quiet". The
            # rendered-page audit then measured real folios at 2.78:1 on
            # ``medical_clinical`` and 3.07:1 on ``financial_ledger`` — an
            # 8pt page number that a reader has to squint at. Convention is
            # not a reason to ship illegible type, the cost of fixing it is a
            # slightly darker grey, and these are the two roles set at the
            # SMALLEST sizes in the whole document.
            "caption": ensure_contrast(self.caption, bg, body_floor),
            "footer": ensure_contrast(self.footer, bg, body_floor),
            "code_fg": ensure_contrast(self.code_fg, self.code_bg, body_floor,
                                       preserve_hue=False),
            "table_header_fg": ensure_contrast(
                self.table_header_fg, self.table_header_bg, body_floor,
                preserve_hue=False),
            "quote_fg": ensure_contrast(self.quote_fg, self.quote_bg, large_floor),
            "text_inverse": ensure_contrast(self.text_inverse, self.primary,
                                            large_floor, preserve_hue=False),
        }
        # Alternating table rows must not swallow the body text either.
        fixed["table_row_alt"] = (self.table_row_alt
                                  if self.text.contrast(self.table_row_alt) >= large_floor
                                  else mix(surf, bg, 0.5))
        return self.copy_with(**fixed)

    def contrast_report(self) -> list:
        """Human-readable audit rows — surfaced in the agent's own log so a
        questionable theme is *visible*, not merely survived."""
        checks = (
            ("text on background", self.text, self.background, WCAG_AA_NORMAL),
            ("muted on background", self.text_muted, self.background, WCAG_AA_LARGE),
            ("h1 on background", self.heading_1, self.background, WCAG_AA_LARGE),
            ("h2 on background", self.heading_2, self.background, WCAG_AA_LARGE),
            ("code fg on code bg", self.code_fg, self.code_bg, WCAG_AA_NORMAL),
            ("th fg on th bg", self.table_header_fg, self.table_header_bg,
             WCAG_AA_NORMAL),
            ("link on background", self.link, self.background, WCAG_AA_NORMAL),
            ("quote on quote bg", self.quote_fg, self.quote_bg, WCAG_AA_LARGE),
            ("text on row-alt", self.text, self.table_row_alt, WCAG_AA_LARGE),
        )
        rows = []
        for label, fg, bg, floor in checks:
            ratio = fg.contrast(bg)
            rows.append({
                "check": label, "ratio": round(ratio, 2), "floor": floor,
                "pass": ratio >= floor, "fg": fg.hex, "bg": bg.hex,
            })
        return rows

    def __repr__(self) -> str:
        return "Palette(%s, %s bg=%s text=%s primary=%s)" % (
            self.name, "dark" if self.dark else "light",
            self.background.hex, self.text.hex, self.primary.hex)


def palette_from_seed(seed, dark: bool = False, name: str = "seeded",
                      warmth: float = 0.0, intensity: float = 1.0) -> "Palette":
    """Derive a COMPLETE, harmonious, legible palette from ONE colour.

    This is the engine behind Angela's ``predominant_color`` parameter: the
    user (or an upstream agent in a flow) names a single colour and gets a
    whole document that agrees with it — headings, rules, table headers,
    callout bars, code panels, the cover wash, the footer.

    HOW IT WORKS
    ------------
    The seed is decomposed into OKLCh. Hue is treated as the document's
    identity and is *preserved*; lightness and chroma are re-derived per role
    against the chosen ground, because the same hue needs very different
    lightness to work as a page background, as a heading and as a hairline.
    Secondary and accent are pulled from the harmony wheel (analogous for
    calm agreement, split-complementary for the accent that must catch the
    eye) rather than invented, so nothing clashes.

    *warmth* nudges the neutral greys toward the seed's hue (0 = clinical
    neutral, 1 = strongly tinted paper). *intensity* scales chroma globally,
    so the same seed can produce a restrained legal document or a loud
    marketing brochure.
    """
    base = parse_color(seed, "#1F4E79")
    lightness, chroma, hue = base.to_oklch()
    chroma = max(0.02, chroma) * clamp(intensity, 0.0, 2.0)
    tint = clamp(warmth, 0.0, 1.0)
    wheel = harmonies(base)

    if dark:
        background = Color.from_oklch(0.14 + 0.05 * tint, min(chroma * 0.28, 0.035), hue)
        background_alt = Color.from_oklch(0.19 + 0.05 * tint, min(chroma * 0.30, 0.040), hue)
        surface = Color.from_oklch(0.22, min(chroma * 0.25, 0.035), hue)
        surface_alt = Color.from_oklch(0.27, min(chroma * 0.22, 0.032), hue)
        text = Color.from_oklch(0.96, min(chroma * 0.05, 0.012), hue)
        text_muted = Color.from_oklch(0.76, min(chroma * 0.12, 0.022), hue)
        primary = Color.from_oklch(max(0.68, lightness), max(chroma, 0.11), hue)
        code_bg = Color.from_oklch(0.18, min(chroma * 0.30, 0.038), hue)
        code_fg = Color.from_oklch(0.90, min(chroma * 0.20, 0.045), hue + 25)
        header_bg = Color.from_oklch(0.30, min(chroma * 0.55, 0.075), hue)
        row_alt = Color.from_oklch(0.20, min(chroma * 0.25, 0.030), hue)
        quote_bg = Color.from_oklch(0.21, min(chroma * 0.35, 0.045), hue)
        border = Color.from_oklch(0.36, min(chroma * 0.35, 0.045), hue)
        border_soft = Color.from_oklch(0.28, min(chroma * 0.28, 0.035), hue)
        cover_from = Color.from_oklch(0.10, min(chroma * 0.4, 0.05), hue)
        cover_to = Color.from_oklch(0.34, chroma * 0.9, hue + 20)
    else:
        background = Color.from_oklch(0.995 - 0.012 * tint, min(chroma * 0.05, 0.008), hue)
        background_alt = Color.from_oklch(0.975 - 0.02 * tint, min(chroma * 0.10, 0.014), hue)
        surface = Color.from_oklch(0.965, min(chroma * 0.12, 0.016), hue)
        surface_alt = Color.from_oklch(0.94, min(chroma * 0.15, 0.020), hue)
        text = Color.from_oklch(0.20, min(chroma * 0.12, 0.022), hue)
        text_muted = Color.from_oklch(0.48, min(chroma * 0.18, 0.030), hue)
        primary = Color.from_oklch(min(0.52, max(0.34, lightness)), max(chroma, 0.10), hue)
        code_bg = Color.from_oklch(0.958, min(chroma * 0.22, 0.026), hue)
        code_fg = Color.from_oklch(0.32, min(chroma * 0.40, 0.070), hue + 25)
        header_bg = Color.from_oklch(0.90, min(chroma * 0.45, 0.060), hue)
        row_alt = Color.from_oklch(0.975, min(chroma * 0.14, 0.018), hue)
        quote_bg = Color.from_oklch(0.965, min(chroma * 0.25, 0.030), hue)
        border = Color.from_oklch(0.80, min(chroma * 0.30, 0.040), hue)
        border_soft = Color.from_oklch(0.90, min(chroma * 0.20, 0.026), hue)
        cover_from = Color.from_oklch(0.42, chroma * 0.9, hue)
        cover_to = Color.from_oklch(0.68, chroma * 0.7, hue + 25)

    secondary = wheel["analogous_cool"].with_chroma(chroma * 0.85)
    accent = wheel["split_a"].with_chroma(max(chroma * 1.15, 0.13))
    if dark:
        secondary = secondary.with_lightness(0.72)
        accent = accent.with_lightness(0.76)
    else:
        secondary = secondary.with_lightness(0.46)
        accent = accent.with_lightness(0.52)

    # Semantic colours keep their universally-understood hue (a red danger is
    # red in every culture PDFer ships to) but adopt the palette's lightness
    # regime so they sit on the page instead of shouting off it.
    sem_l = 0.74 if dark else 0.45
    palette = Palette(
        name=name, dark=dark,
        background=background, background_alt=background_alt,
        surface=surface, surface_alt=surface_alt,
        text=text, text_muted=text_muted,
        text_inverse=Color.from_oklch(0.98, 0.005, hue) if not dark
        else Color.from_oklch(0.14, 0.01, hue),
        primary=primary,
        primary_soft=mix(primary, background, 0.78),
        secondary=secondary, accent=accent,
        border=border, border_soft=border_soft,
        rule=primary,
        link=accent if dark else primary.darken(0.04),
        code_bg=code_bg, code_fg=code_fg,
        code_border=border_soft,
        table_header_bg=header_bg,
        table_header_fg=Color.from_oklch(0.97, 0.01, hue) if dark
        else Color.from_oklch(0.22, min(chroma * 0.3, 0.05), hue),
        table_row_alt=row_alt, table_border=border,
        quote_bar=accent, quote_bg=quote_bg, quote_fg=text_muted,
        success=Color.from_oklch(sem_l, 0.15, 150),
        warning=Color.from_oklch(sem_l, 0.16, 75),
        danger=Color.from_oklch(sem_l, 0.19, 25),
        info=Color.from_oklch(sem_l, 0.14, 245),
        heading_1=primary if not dark else primary.lighten(0.10),
        heading_2=primary.darken(0.04) if not dark else primary.lighten(0.04),
        heading_3=text if not dark else text_muted.lighten(0.10),
        heading_4=text_muted,
        caption=text_muted, footer=text_muted.desaturate(0.4),
        cover_from=cover_from, cover_to=cover_to,
        ornament=accent,
    )
    return palette.validated()
