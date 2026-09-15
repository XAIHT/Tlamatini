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
# pptxer_color.py — PPTXer's COLOUR SCIENCE.
#
# Sibling module of pptxer.py (NOT a package — the agent is copied into a runtime
# directory and run as `python pptxer.py`, so sys.path[0] is that directory and a
# flat neighbour imports reliably in source, frozen and self-modify builds).
#
# Stdlib ONLY. Imports nothing from agent.* and nothing from the other pptxer_*
# modules, so it can never create an import cycle.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY OKLab AND NOT HSL
# ─────────────────────────────────────────────────────────────────────────────
# A gradient interpolated in sRGB passes through a grey, muddy middle: #FF0000 →
# #0000FF in sRGB goes through #7F007F, which is visibly darker than either end.
# OKLab is perceptually uniform, so the same gradient stays luminous the whole
# way across. Marketing and gaming decks are MADE of gradients, so this is not a
# refinement here — it is the difference between a deck that looks designed and
# one that looks like a 1998 clip-art template.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY A SLIDE NEEDS MORE CONTRAST THAN A PAGE  (the load-bearing difference)
# ─────────────────────────────────────────────────────────────────────────────
# PDFer targets WCAG 4.5:1 because a PDF is read on a screen, held still, at
# arm's length, by one person who can zoom.
#
# A SLIDE is projected. It is:
#   · washed out by ambient light (a lit room can cost 30-50% of contrast ratio),
#   · viewed from 10+ metres at the back of the room,
#   · rendered by a projector whose black point is grey,
#   · often photographed by an audience on phones.
#
# So PPTXer's floors are DELIBERATELY HIGHER than PDFer's:
#     body text on its ground ............ 7.0  (WCAG AAA, not AA)
#     large display/title text ........... 4.5  (AA-large is 3.0 — not enough)
#     non-text UI (rules, bars, icons) ... 3.0
# A deck that only meets 4.5 looks fine on the laptop that authored it and
# UNREADABLE in the room it is shown in. That failure is invisible to the author,
# which is exactly why it must be enforced by code rather than by taste.
#
# CONTRAST_SAFETY exists for the same reason it exists in PDFer: a colour
# certified at *exactly* the floor measures just under it once the glyph is
# antialiased and the projector applies its own gamma. Never sit ON a threshold.

import colorsys
import hashlib
import math
import re

__all__ = [
    "CONTRAST_SAFETY",
    "BODY_CONTRAST_FLOOR",
    "DISPLAY_CONTRAST_FLOOR",
    "NON_TEXT_CONTRAST_FLOOR",
    "Color",
    "parse_color",
    "to_hex",
    "srgb_to_oklab",
    "oklab_to_srgb",
    "srgb_to_oklch",
    "oklch_to_srgb",
    "relative_luminance",
    "contrast_ratio",
    "mix_oklab",
    "gradient_stops",
    "lighten",
    "darken",
    "saturate",
    "rotate_hue",
    "ensure_contrast",
    "best_text_on",
    "harmonize",
    "derive_palette_from_seed",
    "is_dark",
    "NAMED_COLORS",
]

# ─────────────────────────────────────────────────────────────────────────────
# Contrast floors and the safety margin
# ─────────────────────────────────────────────────────────────────────────────

# Overshoot every floor by this factor. Landing exactly ON a threshold measures
# as a FAILURE once the glyph is rasterised and the projector applies gamma.
CONTRAST_SAFETY = 1.06

BODY_CONTRAST_FLOOR = 7.0        # WCAG AAA — a projected slide needs it
DISPLAY_CONTRAST_FLOOR = 4.5     # titles / >= 28pt
NON_TEXT_CONTRAST_FLOOR = 3.0    # rules, bars, icon strokes

# ─────────────────────────────────────────────────────────────────────────────
# Named colours — CSS4 plus the display names a marketing/gaming brief uses
# ─────────────────────────────────────────────────────────────────────────────

NAMED_COLORS = {
    # -- greyscale ------------------------------------------------------------
    "black": "#000000", "white": "#FFFFFF", "grey": "#808080", "gray": "#808080",
    "silver": "#C0C0C0", "dimgrey": "#696969", "dimgray": "#696969",
    "lightgrey": "#D3D3D3", "lightgray": "#D3D3D3", "darkgrey": "#A9A9A9",
    "darkgray": "#A9A9A9", "gainsboro": "#DCDCDC", "whitesmoke": "#F5F5F5",
    "snow": "#FFFAFA", "ivory": "#FFFFF0", "linen": "#FAF0E6",
    # -- red / pink -----------------------------------------------------------
    "red": "#FF0000", "crimson": "#DC143C", "firebrick": "#B22222",
    "darkred": "#8B0000", "maroon": "#800000", "tomato": "#FF6347",
    "salmon": "#FA8072", "coral": "#FF7F50", "orangered": "#FF4500",
    "pink": "#FFC0CB", "hotpink": "#FF69B4", "deeppink": "#FF1493",
    "magenta": "#FF00FF", "fuchsia": "#FF00FF", "rose": "#FF007F",
    # -- orange / yellow ------------------------------------------------------
    "orange": "#FFA500", "darkorange": "#FF8C00", "gold": "#FFD700",
    "amber": "#FFBF00", "yellow": "#FFFF00", "khaki": "#F0E68C",
    "goldenrod": "#DAA520", "peru": "#CD853F", "chocolate": "#D2691E",
    "sienna": "#A0522D", "saddlebrown": "#8B4513", "brown": "#A52A2A",
    "tan": "#D2B48C", "wheat": "#F5DEB3", "beige": "#F5F5DC",
    "terracotta": "#E2725B", "rust": "#B7410E", "copper": "#B87333",
    "bronze": "#CD7F32", "brass": "#B5A642",
    # -- green ----------------------------------------------------------------
    "green": "#008000", "lime": "#00FF00", "limegreen": "#32CD32",
    "forestgreen": "#228B22", "darkgreen": "#006400", "seagreen": "#2E8B57",
    "mediumseagreen": "#3CB371", "springgreen": "#00FF7F", "olive": "#808000",
    "olivedrab": "#6B8E23", "darkolivegreen": "#556B2F", "sage": "#9CAF88",
    "mint": "#3EB489", "emerald": "#50C878", "jade": "#00A86B",
    "chartreuse": "#7FFF00", "neongreen": "#39FF14",
    # -- cyan / teal ----------------------------------------------------------
    "cyan": "#00FFFF", "aqua": "#00FFFF", "teal": "#008080",
    "darkcyan": "#008B8B", "turquoise": "#40E0D0", "aquamarine": "#7FFFD4",
    "cadetblue": "#5F9EA0", "lightseagreen": "#20B2AA", "electricblue": "#7DF9FF",
    # -- blue -----------------------------------------------------------------
    "blue": "#0000FF", "navy": "#000080", "midnightblue": "#191970",
    "darkblue": "#00008B", "mediumblue": "#0000CD", "royalblue": "#4169E1",
    "dodgerblue": "#1E90FF", "deepskyblue": "#00BFFF", "skyblue": "#87CEEB",
    "steelblue": "#4682B4", "cornflowerblue": "#6495ED", "slateblue": "#6A5ACD",
    "azure": "#007FFF", "cobalt": "#0047AB", "sapphire": "#0F52BA",
    "cerulean": "#2A52BE", "indigo": "#4B0082",
    # -- purple / violet ------------------------------------------------------
    "purple": "#800080", "darkviolet": "#9400D3", "blueviolet": "#8A2BE2",
    "darkorchid": "#9932CC", "mediumpurple": "#9370DB", "violet": "#EE82EE",
    "orchid": "#DA70D6", "plum": "#DDA0DD", "lavender": "#E6E6FA",
    "amethyst": "#9966CC", "mauve": "#E0B0FF", "electricviolet": "#8F00FF",
    # -- the display / brief names a designer actually says -------------------
    "obsidian": "#0B0B0F", "charcoal": "#1C1C22", "graphite": "#2B2B33",
    "slate": "#2F3640", "gunmetal": "#2A3439", "onyx": "#0F1013",
    "ink": "#12131A", "midnight": "#070910", "abyss": "#04060C",
    "cream": "#FFFDF5", "bone": "#F4F1EA", "parchment": "#F3EBDD",
    "porcelain": "#FAFBFC", "alabaster": "#EDEAE3",
    "neon": "#39FF14", "neonpink": "#FF10F0", "neoncyan": "#0FF0FC",
    "acid": "#B0FF1F", "plasma": "#FF3CAC", "toxic": "#CCFF00",
    "ember": "#FF4500", "lava": "#CF1020", "inferno": "#FF2400",
    "ultraviolet": "#5F4B8B", "vaporwave": "#FF6AD5", "synthwave": "#F72585",
    "cyberpunk": "#00F0FF", "hologram": "#8AF7FF", "quantum": "#7B2FF7",
    "esports": "#12E2A3", "arcade": "#FF2E63", "console": "#00D9FF",
}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_RE = re.compile(
    r"^rgba?\(\s*([0-9.]+%?)\s*[,\s]\s*([0-9.]+%?)\s*[,\s]\s*([0-9.]+%?)"
    r"(?:\s*[,/]\s*([0-9.]+%?)\s*)?\)$", re.I)
_HSL_RE = re.compile(
    r"^hsla?\(\s*([-0-9.]+)(?:deg)?\s*[,\s]\s*([0-9.]+)%?\s*[,\s]\s*([0-9.]+)%?"
    r"(?:\s*[,/]\s*([0-9.]+%?)\s*)?\)$", re.I)
_OKLCH_RE = re.compile(
    r"^oklch\(\s*([0-9.]+%?)\s+([0-9.]+)\s+([-0-9.]+)(?:deg)?"
    r"(?:\s*/\s*([0-9.]+%?)\s*)?\)$", re.I)


class Color:
    """An sRGB colour with an alpha channel.

    Channels are stored as floats in 0..1 so every conversion stays lossless
    until the final quantisation to 8-bit. ``a`` is retained because PPTX shape
    fills carry real transparency (a glow, a scrim over a photo, a frosted
    panel) and rounding it away early would make those effects impossible.
    """

    __slots__ = ("r", "g", "b", "a")

    def __init__(self, r: float, g: float, b: float, a: float = 1.0):
        self.r = _clamp01(r)
        self.g = _clamp01(g)
        self.b = _clamp01(b)
        self.a = _clamp01(a)

    # -- constructors ---------------------------------------------------------

    @classmethod
    def from_hex(cls, value: str) -> "Color":
        s = (value or "").strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        elif len(s) == 4:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            s += "FF"
        if len(s) != 8:
            raise ValueError(f"not a hex colour: {value!r}")
        return cls(
            int(s[0:2], 16) / 255.0,
            int(s[2:4], 16) / 255.0,
            int(s[4:6], 16) / 255.0,
            int(s[6:8], 16) / 255.0,
        )

    @classmethod
    def from_rgb255(cls, r: int, g: int, b: int, a: int = 255) -> "Color":
        return cls(r / 255.0, g / 255.0, b / 255.0, a / 255.0)

    # -- exports --------------------------------------------------------------

    @property
    def rgb255(self) -> tuple:
        return (
            int(round(self.r * 255)),
            int(round(self.g * 255)),
            int(round(self.b * 255)),
        )

    @property
    def rgba255(self) -> tuple:
        r, g, b = self.rgb255
        return (r, g, b, int(round(self.a * 255)))

    @property
    def hex(self) -> str:
        r, g, b = self.rgb255
        return f"#{r:02X}{g:02X}{b:02X}"

    @property
    def hex_rrggbb(self) -> str:
        """Hex WITHOUT the leading '#'. python-pptx RGBColor.from_string wants this."""
        return self.hex[1:]

    @property
    def luminance(self) -> float:
        return relative_luminance(self)

    def with_alpha(self, a: float) -> "Color":
        return Color(self.r, self.g, self.b, a)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Color):
            return NotImplemented
        return self.rgba255 == other.rgba255

    def __hash__(self) -> int:
        return hash(self.rgba255)

    def __repr__(self) -> str:
        if self.a >= 0.999:
            return f"Color({self.hex})"
        return f"Color({self.hex} @{self.a:.2f})"


def _clamp01(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f:          # NaN — the only value that fails its own equality test
        return 0.0
    return 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)


def _num(token: str, scale: float = 255.0) -> float:
    """Parse '40%' or '204' into 0..1. Percentages are relative to `scale`."""
    t = (token or "").strip()
    if t.endswith("%"):
        return _clamp01(float(t[:-1]) / 100.0)
    return _clamp01(float(t) / scale)


def parse_color(value, default=None):
    """Parse ANY reasonable colour spelling into a Color.

    Accepts a Color (passthrough), '#RGB'/'#RGBA'/'#RRGGBB'/'#RRGGBBAA',
    'rgb()'/'rgba()', 'hsl()'/'hsla()', 'oklch()', an (r,g,b[,a]) tuple of
    0-255 ints or 0-1 floats, and every name in NAMED_COLORS.

    FAIL-OPEN: an unparseable value returns `default` (None unless given) and
    never raises. A colour typo must never stop a deck from being built — the
    design simply falls back to the theme's own choice.
    """
    if value is None:
        return default
    if isinstance(value, Color):
        return value

    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        try:
            vals = [float(v) for v in value]
        except (TypeError, ValueError):
            return default
        # Heuristic: any component > 1 means the caller is speaking 0-255.
        if any(v > 1.0 for v in vals):
            scaled = [v / 255.0 for v in vals]
        else:
            scaled = vals
        if len(scaled) == 3:
            scaled.append(1.0)
        return Color(*scaled)

    if not isinstance(value, str):
        return default

    s = value.strip()
    if not s:
        return default

    key = s.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in NAMED_COLORS:
        try:
            return Color.from_hex(NAMED_COLORS[key])
        except ValueError:
            return default

    if _HEX_RE.match(s):
        try:
            return Color.from_hex(s)
        except ValueError:
            return default

    m = _RGB_RE.match(s)
    if m:
        try:
            r = _num(m.group(1))
            g = _num(m.group(2))
            b = _num(m.group(3))
            a = _num(m.group(4), 1.0) if m.group(4) else 1.0
            return Color(r, g, b, a)
        except ValueError:
            return default

    m = _HSL_RE.match(s)
    if m:
        try:
            h = (float(m.group(1)) % 360.0) / 360.0
            sat = _clamp01(float(m.group(2)) / 100.0)
            lig = _clamp01(float(m.group(3)) / 100.0)
            a = _num(m.group(4), 1.0) if m.group(4) else 1.0
            r, g, b = colorsys.hls_to_rgb(h, lig, sat)
            return Color(r, g, b, a)
        except ValueError:
            return default

    m = _OKLCH_RE.match(s)
    if m:
        try:
            lt = m.group(1)
            ll = float(lt[:-1]) / 100.0 if lt.endswith("%") else float(lt)
            cc = float(m.group(2))
            hh = float(m.group(3))
            a = _num(m.group(4), 1.0) if m.group(4) else 1.0
            col = oklch_to_srgb(ll, cc, hh)
            return col.with_alpha(a)
        except ValueError:
            return default

    return default


def to_hex(value, default="#000000") -> str:
    """Parse anything and return '#RRGGBB'. Never raises."""
    c = parse_color(value)
    if c is None:
        c = parse_color(default) or Color(0, 0, 0)
    return c.hex


# ─────────────────────────────────────────────────────────────────────────────
# sRGB ⇄ OKLab ⇄ OKLCh
#
# Björn Ottosson's OKLab (2020). The matrices below are his published values;
# do not "tidy" the constants — the round-trip error is already at the limit of
# 8-bit quantisation and rewriting them by hand reintroduces drift.
# ─────────────────────────────────────────────────────────────────────────────

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (max(c, 0.0) ** (1.0 / 2.4)) - 0.055


def srgb_to_oklab(color) -> tuple:
    """(L, a, b) — L is 0..1 perceptual lightness."""
    c = parse_color(color) or Color(0, 0, 0)
    r = _srgb_to_linear(c.r)
    g = _srgb_to_linear(c.g)
    b = _srgb_to_linear(c.b)

    lms_l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    lms_m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    lms_s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = _cbrt(lms_l)
    m_ = _cbrt(lms_m)
    s_ = _cbrt(lms_s)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _cbrt(x: float) -> float:
    """Real cube root that keeps the sign (math.pow would raise on a negative)."""
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def oklab_to_srgb(lightness: float, a: float, b: float, alpha: float = 1.0) -> Color:
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b

    lms_l = l_ * l_ * l_
    lms_m = m_ * m_ * m_
    lms_s = s_ * s_ * s_

    r = +4.0767416621 * lms_l - 3.3077115913 * lms_m + 0.2309699292 * lms_s
    g = -1.2684380046 * lms_l + 2.6097574011 * lms_m - 0.3413193965 * lms_s
    bb = -0.0041960863 * lms_l - 0.7034186147 * lms_m + 1.7076147010 * lms_s

    return Color(_linear_to_srgb(r), _linear_to_srgb(g), _linear_to_srgb(bb), alpha)


def srgb_to_oklch(color) -> tuple:
    """(L, C, h°) — polar OKLab. Hue in degrees 0..360."""
    lightness, a, b = srgb_to_oklab(color)
    chroma = math.hypot(a, b)
    hue = math.degrees(math.atan2(b, a)) % 360.0
    return (lightness, chroma, hue)


def oklch_to_srgb(lightness: float, chroma: float, hue_deg: float,
                  alpha: float = 1.0) -> Color:
    rad = math.radians(hue_deg)
    return oklab_to_srgb(lightness, chroma * math.cos(rad),
                         chroma * math.sin(rad), alpha)


# ─────────────────────────────────────────────────────────────────────────────
# Contrast (WCAG 2.x relative luminance)
# ─────────────────────────────────────────────────────────────────────────────

def relative_luminance(color) -> float:
    c = parse_color(color) or Color(0, 0, 0)
    r = _srgb_to_linear(c.r)
    g = _srgb_to_linear(c.g)
    b = _srgb_to_linear(c.b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg) -> float:
    """WCAG contrast ratio, 1.0 .. 21.0. Order-independent."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def is_dark(color, threshold: float = 0.42) -> bool:
    """True when `color` reads as a DARK ground.

    Uses OKLab L rather than WCAG luminance on purpose: WCAG luminance is
    weighted for legibility maths and calls a saturated blue (#0000FF, Y≈0.07)
    far darker than a saturated yellow of identical OKLab lightness. For the
    question 'is this a dark deck or a light deck?' the perceptual answer is the
    correct one.
    """
    lightness, _, _ = srgb_to_oklab(color)
    return lightness < threshold


# ─────────────────────────────────────────────────────────────────────────────
# Manipulation — all in OKLab/OKLCh so results stay perceptually even
# ─────────────────────────────────────────────────────────────────────────────

def mix_oklab(color_a, color_b, t: float = 0.5) -> Color:
    """Blend two colours in OKLab. t=0 → a, t=1 → b."""
    t = _clamp01(t)
    la, aa, ba = srgb_to_oklab(color_a)
    lb, ab, bb = srgb_to_oklab(color_b)
    ca = parse_color(color_a) or Color(0, 0, 0)
    cb = parse_color(color_b) or Color(0, 0, 0)
    return oklab_to_srgb(
        la + (lb - la) * t,
        aa + (ab - aa) * t,
        ba + (bb - ba) * t,
        ca.a + (cb.a - ca.a) * t,
    )


def gradient_stops(color_a, color_b, count: int = 8, via=None) -> list:
    """`count` colours walking a → b in OKLab (optionally through `via`).

    This is the reason gradients in a PPTXer deck look expensive. PowerPoint's
    own gradient interpolates in sRGB, so a two-stop cyan→magenta fill dips
    through a dull grey-violet in the middle. Emitting MANY measured OKLab stops
    (PowerPoint accepts an arbitrary gradient stop list) keeps the ramp
    luminous end to end, because each stop is already perceptually correct and
    PowerPoint only ever interpolates the short distance between neighbours.
    """
    n = max(2, int(count))
    out = []
    if via is not None:
        half = n // 2
        for i in range(half):
            out.append(mix_oklab(color_a, via, i / max(1, half - 1) if half > 1 else 0.0))
        rest = n - half
        for i in range(rest):
            out.append(mix_oklab(via, color_b, i / max(1, rest - 1) if rest > 1 else 1.0))
        return out[:n]
    for i in range(n):
        out.append(mix_oklab(color_a, color_b, i / (n - 1)))
    return out


def lighten(color, amount: float = 0.1) -> Color:
    """Raise OKLab lightness by `amount` (0..1), keeping hue and chroma."""
    lightness, a, b = srgb_to_oklab(color)
    c = parse_color(color) or Color(0, 0, 0)
    return oklab_to_srgb(_clamp01(lightness + amount), a, b, c.a)


def darken(color, amount: float = 0.1) -> Color:
    return lighten(color, -amount)


def saturate(color, factor: float = 1.2) -> Color:
    """Scale OKLCh chroma. factor < 1 desaturates, > 1 intensifies."""
    lightness, chroma, hue = srgb_to_oklch(color)
    c = parse_color(color) or Color(0, 0, 0)
    try:
        f = float(factor)
    except (TypeError, ValueError):
        f = 1.0
    return oklch_to_srgb(lightness, max(0.0, chroma * f), hue, c.a)


def rotate_hue(color, degrees: float) -> Color:
    lightness, chroma, hue = srgb_to_oklch(color)
    c = parse_color(color) or Color(0, 0, 0)
    try:
        d = float(degrees)
    except (TypeError, ValueError):
        d = 0.0
    return oklch_to_srgb(lightness, chroma, (hue + d) % 360.0, c.a)


def ensure_contrast(fg, bg, floor: float = BODY_CONTRAST_FLOOR,
                    safety: float = CONTRAST_SAFETY) -> Color:
    """Return `fg`, adjusted ONLY as far as needed to clear `floor * safety` on `bg`.

    The hue and chroma of the author's colour are PRESERVED; only OKLab
    lightness moves, and it moves away from the background. This is what makes
    the guarantee acceptable to a designer: their brand cyan stays cyan, it just
    becomes a legible cyan.

    If lightness alone cannot reach the floor (a mid-grey ground is the classic
    case — nothing on it clears 7:1), the function falls back to the better of
    pure white / pure black, because an unreadable brand colour is worse than a
    correct neutral. It NEVER returns a colour that fails the floor when one
    exists.
    """
    target = max(1.0, float(floor) * float(safety))
    base = parse_color(fg) or Color(0, 0, 0)
    ground = parse_color(bg) or Color(1, 1, 1)

    if contrast_ratio(base, ground) >= target:
        return base

    lightness, a, b = srgb_to_oklab(base)
    ground_is_dark = is_dark(ground)

    # Walk lightness AWAY from the ground in small perceptual steps.
    best = base
    best_ratio = contrast_ratio(base, ground)
    step = 0.02
    steps = int(1.0 / step) + 1
    for i in range(1, steps):
        delta = step * i
        candidate_l = lightness + delta if ground_is_dark else lightness - delta
        if candidate_l < 0.0 or candidate_l > 1.0:
            break
        cand = oklab_to_srgb(candidate_l, a, b, base.a)
        ratio = contrast_ratio(cand, ground)
        if ratio > best_ratio:
            best_ratio = ratio
            best = cand
        if ratio >= target:
            return cand

    # Lightness alone was not enough. Take the better neutral.
    white = Color(1, 1, 1, base.a)
    black = Color(0, 0, 0, base.a)
    r_white = contrast_ratio(white, ground)
    r_black = contrast_ratio(black, ground)
    neutral, r_neutral = (white, r_white) if r_white >= r_black else (black, r_black)
    return neutral if r_neutral > best_ratio else best


def best_text_on(bg, light=None, dark=None) -> Color:
    """Pick whichever of `light`/`dark` reads better on `bg`."""
    ground = parse_color(bg) or Color(1, 1, 1)
    hi = parse_color(light) or Color(1, 1, 1)
    lo = parse_color(dark) or Color(0.05, 0.05, 0.06)
    return hi if contrast_ratio(hi, ground) >= contrast_ratio(lo, ground) else lo


def harmonize(seed, scheme: str = "analogous", count: int = 5) -> list:
    """Derive a harmonious family from ONE seed colour, in OKLCh.

    Schemes: monochrome · analogous · complementary · split · triad · tetrad ·
    neon (the gaming favourite — two far-apart hues at very high chroma).
    """
    base = parse_color(seed) or Color(0.3, 0.4, 0.9)
    lightness, chroma, hue = srgb_to_oklch(base)
    n = max(1, int(count))
    scheme = (scheme or "analogous").strip().lower()

    if scheme == "monochrome":
        out = []
        for i in range(n):
            t = i / max(1, n - 1)
            out.append(oklch_to_srgb(_clamp01(0.22 + 0.62 * t), chroma * (0.55 + 0.45 * t), hue))
        return out

    if scheme == "complementary":
        offsets = [0.0, 180.0]
    elif scheme == "split":
        offsets = [0.0, 150.0, 210.0]
    elif scheme == "triad":
        offsets = [0.0, 120.0, 240.0]
    elif scheme == "tetrad":
        offsets = [0.0, 90.0, 180.0, 270.0]
    elif scheme == "neon":
        offsets = [0.0, 168.0, 300.0]
    else:  # analogous
        offsets = [-40.0, -20.0, 0.0, 20.0, 40.0]

    boost = 1.35 if scheme == "neon" else 1.0
    out = []
    for i in range(n):
        off = offsets[i % len(offsets)]
        ring = i // len(offsets)
        light_shift = 0.08 * ring
        out.append(oklch_to_srgb(
            _clamp01(lightness + light_shift),
            max(0.0, chroma * boost),
            (hue + off) % 360.0,
        ))
    return out


def derive_palette_from_seed(seed, dark_ground: bool = True) -> dict:
    """ONE seed colour → a complete, legible slide palette.

    This is the engine behind `predominant_color`: the author names a single
    brand colour and every role in the deck is derived from it in OKLab, so the
    whole presentation agrees with itself instead of each slide picking its own
    approximation of "our blue".

    Every text role returned is ALREADY contrast-corrected against the ground it
    will actually sit on. Callers must still run the theme's final validation
    pass (roles can be overridden afterwards), but nothing produced here is
    illegible to begin with.
    """
    base = parse_color(seed) or Color(0.29, 0.34, 0.86)
    lightness, chroma, hue = srgb_to_oklch(base)
    chroma = max(chroma, 0.04)

    if dark_ground:
        ground = oklch_to_srgb(0.16, min(chroma * 0.34, 0.045), hue)
        ground_deep = oklch_to_srgb(0.10, min(chroma * 0.28, 0.035), hue)
        surface = oklch_to_srgb(0.235, min(chroma * 0.38, 0.055), hue)
        surface_high = oklch_to_srgb(0.31, min(chroma * 0.42, 0.065), hue)
        text = oklch_to_srgb(0.97, min(chroma * 0.10, 0.018), hue)
        text_muted = oklch_to_srgb(0.80, min(chroma * 0.14, 0.026), hue)
        accent = oklch_to_srgb(max(lightness, 0.74), chroma * 1.22, hue)
        accent_2 = oklch_to_srgb(max(lightness, 0.72), chroma * 1.26, (hue + 42.0) % 360.0)
        accent_3 = oklch_to_srgb(max(lightness, 0.70), chroma * 1.18, (hue + 300.0) % 360.0)
    else:
        ground = oklch_to_srgb(0.985, min(chroma * 0.08, 0.014), hue)
        ground_deep = oklch_to_srgb(0.945, min(chroma * 0.12, 0.022), hue)
        surface = oklch_to_srgb(0.955, min(chroma * 0.12, 0.020), hue)
        surface_high = oklch_to_srgb(0.905, min(chroma * 0.16, 0.030), hue)
        text = oklch_to_srgb(0.20, min(chroma * 0.16, 0.030), hue)
        text_muted = oklch_to_srgb(0.42, min(chroma * 0.18, 0.034), hue)
        accent = oklch_to_srgb(min(lightness, 0.55), chroma * 1.10, hue)
        accent_2 = oklch_to_srgb(min(lightness, 0.52), chroma * 1.14, (hue + 42.0) % 360.0)
        accent_3 = oklch_to_srgb(min(lightness, 0.50), chroma * 1.08, (hue + 300.0) % 360.0)

    palette = {
        "ground": ground,
        "ground_deep": ground_deep,
        "surface": surface,
        "surface_high": surface_high,
        "text": ensure_contrast(text, ground, BODY_CONTRAST_FLOOR),
        "text_muted": ensure_contrast(text_muted, ground, DISPLAY_CONTRAST_FLOOR),
        "accent": accent,
        "accent_2": accent_2,
        "accent_3": accent_3,
        "title": ensure_contrast(accent, ground, DISPLAY_CONTRAST_FLOOR),
        "rule": ensure_contrast(accent, ground, NON_TEXT_CONTRAST_FLOOR),
        "on_accent": best_text_on(accent),
        "on_surface": ensure_contrast(text, surface, BODY_CONTRAST_FLOOR),
        "success": ensure_contrast(parse_color("#2ED573"), ground, DISPLAY_CONTRAST_FLOOR),
        "warning": ensure_contrast(parse_color("#FFB020"), ground, DISPLAY_CONTRAST_FLOOR),
        "danger": ensure_contrast(parse_color("#FF4757"), ground, DISPLAY_CONTRAST_FLOOR),
        "info": ensure_contrast(parse_color("#3FA9F5"), ground, DISPLAY_CONTRAST_FLOOR),
    }
    return palette


def seed_from_text(text: str) -> Color:
    """A DETERMINISTIC colour derived from content.

    Same text always yields the same colour, so a re-render is byte-identical.
    The hash picks only the HUE; lightness and chroma are pinned to a band that
    is always usable, so a "random" colour can never be muddy or illegible.
    """
    digest = hashlib.sha256((text or "").encode("utf-8", errors="replace")).digest()
    hue = (digest[0] / 255.0) * 360.0
    chroma = 0.13 + (digest[1] / 255.0) * 0.07
    return oklch_to_srgb(0.62, chroma, hue)
