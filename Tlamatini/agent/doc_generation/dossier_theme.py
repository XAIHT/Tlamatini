# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Shared visual identity of the project dossier (PDF + PPTX).

One palette, one type system and one set of ornaments feed both renderers, so
the printed dossier and the deck can never drift apart visually. Nothing here
reads configuration or credentials; it only needs the Windows system fonts and
the tracked avatar/logo images.

Raster work (deck backgrounds, the circular portrait) uses Pillow drawing
primitives only. It never captures the screen.
"""
from __future__ import annotations

import math
import os
import random
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[3]
BUILD_DIR = REPO_ROOT / "build" / "documentation_refresh"
ASSET_DIR = BUILD_DIR / "dossier_assets"
FONT_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

AVATAR = REPO_ROOT / "Tlamatini" / "agent" / "static" / "agent" / "img" / "avatar" / "eo_mo.jpg"
AVATAR_CALM = REPO_ROOT / "Tlamatini" / "agent" / "static" / "agent" / "img" / "avatar" / "eo_mc.jpg"
LOGO = REPO_ROOT / "Tlamatini.jpg"

# ── Palette ─────────────────────────────────────────────────────────
# Obsidian night, jade and copper: the codex identity of the dossier.
PALETTE = {
    "obsidian": "#090E10",
    "night": "#0D1518",
    "stone": "#151F23",
    "panel": "#121A1D",
    "panel2": "#18242A",
    "edge": "#2A3A40",
    "ivory": "#F7F2E8",
    "paper": "#FBF8F2",
    "parchment": "#EEE5D2",
    "rule": "#D9CDB5",
    "ink": "#1B2427",
    "ink2": "#3B474B",
    "muted": "#6B7678",
    "jade": "#3BBE93",
    "jade_deep": "#17705A",
    "jade_pale": "#E2F1EA",
    "copper": "#C98457",
    "copper_deep": "#8A5431",
    "copper_pale": "#F5E7DA",
    "gold": "#E2B462",
    "gold_pale": "#F8EFD9",
    "cyan": "#46D2E2",
    "magenta": "#D25CD6",
    "rose": "#D9576B",
    "rose_pale": "#F8E3E6",
    "light": "#ECE7DC",
    "light_muted": "#A7B2B0",
    "white": "#FFFFFF",
}

# Accent cycle for families, cards and chapters.
ACCENTS = ["jade", "copper", "gold", "cyan", "magenta", "rose"]


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def color(name: str) -> str:
    return PALETTE.get(name, name)


def mix(a: str, b: str, t: float) -> str:
    """Blend two palette colors; t=0 gives a, t=1 gives b."""
    ra, ga, ba = hex_to_rgb(color(a))
    rb, gb, bb = hex_to_rgb(color(b))
    return "#{:02X}{:02X}{:02X}".format(
        round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


# ── Typography ──────────────────────────────────────────────────────
# Logical font -> (Windows TTF file, PowerPoint family, bold flag, italic flag)
FONTS = {
    "serif": ("pala.ttf", "Palatino Linotype", False, False),
    "serif-bold": ("palab.ttf", "Palatino Linotype", True, False),
    "serif-italic": ("palai.ttf", "Palatino Linotype", False, True),
    "sans": ("segoeui.ttf", "Segoe UI", False, False),
    "sans-italic": ("segoeuii.ttf", "Segoe UI", False, True),
    "sans-light": ("segoeuil.ttf", "Segoe UI Light", False, False),
    "sans-semilight": ("segoeuisl.ttf", "Segoe UI Semilight", False, False),
    "sans-semibold": ("seguisb.ttf", "Segoe UI Semibold", False, False),
    "sans-bold": ("segoeuib.ttf", "Segoe UI", True, False),
    "mono": ("consola.ttf", "Consolas", False, False),
    "mono-bold": ("consolab.ttf", "Consolas", True, False),
    "symbol": ("seguisym.ttf", "Segoe UI Symbol", False, False),
}


def font_path(key: str) -> Path:
    return FONT_DIR / FONTS[key][0]


@lru_cache(maxsize=None)
def font_cmap(key: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont

    return frozenset(TTFont(str(font_path(key)), lazy=True).getBestCmap().keys())


@lru_cache(maxsize=None)
def font_line_factor(key: str) -> float:
    """Natural single-spaced line height of a font, as a multiple of its size."""
    from fontTools.ttLib import TTFont

    font = TTFont(str(font_path(key)), lazy=True)
    os2 = font["OS/2"]
    upm = font["head"].unitsPerEm
    return (os2.usWinAscent + os2.usWinDescent) / upm


def split_fallback(text: str, key: str) -> list[tuple[str, str]]:
    """Split text into (chunk, font) so glyphs missing from ``key`` use Segoe UI Symbol."""
    cmap = font_cmap(key)
    symbols = font_cmap("symbol")
    chunks: list[tuple[str, str]] = []
    for char in text:
        target = key if (ord(char) in cmap or ord(char) not in symbols or char.isspace()) else "symbol"
        if chunks and chunks[-1][1] == target:
            chunks[-1] = (chunks[-1][0] + char, target)
        else:
            chunks.append((char, target))
    return chunks


class GlyphLedger:
    """Records every string rendered in a font so missing glyphs fail the build.

    A missing glyph renders as an empty box in print and as a silent font
    substitution in PowerPoint; neither is acceptable in a finished dossier.
    """

    def __init__(self) -> None:
        self.missing: dict[str, set[str]] = {}

    def check(self, text: str, key: str) -> None:
        cmap = font_cmap(key)
        for char in text:
            if char in "\n\r\t\u00ad\u200b":
                continue
            if ord(char) not in cmap:
                self.missing.setdefault(key, set()).add(char)

    def assert_clean(self, surface: str) -> None:
        if self.missing:
            detail = "; ".join(f"{k}: {''.join(sorted(v))!r}" for k, v in self.missing.items())
            raise RuntimeError(f"{surface}: glyphs missing from their fonts -> {detail}")


# ── Lightweight markup shared by both renderers ─────────────────────
# **bold**   `code`   _italic_   are the only inline marks used in content.
# Italic underscores must sit at word boundaries, so identifiers such as
# unified_agent_max_iterations or AUTH_FAILED keep every underscore.
_MARK = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<!\w)_[^_\s][^_]*?_(?!\w))")


def runs(text: str) -> list[tuple[str, str]]:
    """Split marked-up text into (fragment, style) with style in plain/bold/code/italic."""
    parts: list[tuple[str, str]] = []
    position = 0
    for match in _MARK.finditer(text):
        if match.start() > position:
            parts.append((text[position:match.start()], "plain"))
        token = match.group(0)
        if token.startswith("**"):
            parts.append((token[2:-2], "bold"))
        elif token.startswith("`"):
            parts.append((token[1:-1], "code"))
        else:
            parts.append((token[1:-1], "italic"))
        position = match.end()
    if position < len(text):
        parts.append((text[position:], "plain"))
    return parts


def plain(text: str) -> str:
    return "".join(fragment for fragment, _ in runs(text))


# ── Raster assets for the deck ──────────────────────────────────────
SLIDE_PX = (1920, 1080)


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    width, height = size
    top_rgb, bottom_rgb = hex_to_rgb(top), hex_to_rgb(bottom)
    column = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top_rgb, bottom_rgb)))
    return column.resize(size)


def _glow(size: tuple[int, int], center: tuple[float, float], radius: float, tint: str, strength: float) -> Image.Image:
    layer = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    r, g, b = hex_to_rgb(tint)
    for step in range(40, 0, -1):
        k = step / 40
        alpha = (1 - k) ** 2 * strength
        rad = radius * k
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                     fill=(round(r * alpha), round(g * alpha), round(b * alpha)))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.08))


def _add(base: Image.Image, layer: Image.Image) -> Image.Image:
    from PIL import ImageChops

    return ImageChops.add(base, layer)


def _stars(draw: ImageDraw.ImageDraw, size: tuple[int, int], count: int, seed: int, bright: float = 1.0) -> None:
    rng = random.Random(seed)
    width, height = size
    for _ in range(count):
        x, y = rng.random() * width, rng.random() * height
        level = rng.random()
        radius = 0.6 + level * 1.5
        shade = round((70 + level * 150) * bright)
        tint = rng.choice([(shade, shade, shade), (round(shade * 0.75), shade, round(shade * 0.9)),
                           (shade, round(shade * 0.85), round(shade * 0.7))])
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=tint)


def draw_sunstone(draw: ImageDraw.ImageDraw, center: tuple[float, float], radius: float,
                  line: str, accent: str, width: int = 2) -> None:
    """Concentric codex rings with tick marks and twenty day-sign beads (original art)."""
    cx, cy = center
    rgb, acc = hex_to_rgb(line), hex_to_rgb(accent)
    for k, w in ((1.0, width), (0.93, 1), (0.78, width), (0.70, 1), (0.52, 1), (0.34, width)):
        r = radius * k
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgb, width=w)
    for i in range(80):
        angle = math.tau * i / 80
        inner = radius * (0.93 if i % 4 else 0.86)
        outer = radius * 1.0
        draw.line((cx + inner * math.cos(angle), cy + inner * math.sin(angle),
                   cx + outer * math.cos(angle), cy + outer * math.sin(angle)), fill=rgb, width=1)
    for i in range(20):
        angle = math.tau * i / 20 - math.pi / 2
        r = radius * 0.74
        bead = radius * 0.028
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        draw.rectangle((x - bead, y - bead, x + bead, y + bead), outline=acc, width=1)
    for i in range(8):
        angle = math.tau * i / 8 - math.pi / 2
        tip = radius * 0.50
        base = radius * 0.36
        spread = math.tau / 32
        pts = [(cx + tip * math.cos(angle), cy + tip * math.sin(angle)),
               (cx + base * math.cos(angle - spread), cy + base * math.sin(angle - spread)),
               (cx + base * math.cos(angle + spread), cy + base * math.sin(angle + spread))]
        draw.polygon(pts, outline=acc)


def draw_stepfret(draw: ImageDraw.ImageDraw, x: float, y: float, length: float, unit: float,
                  line: str, width: int = 2, vertical: bool = False) -> None:
    """A stepped-fret band: a continuous line of rising and falling steps (original art)."""
    rgb = hex_to_rgb(line)
    points: list[tuple[float, float]] = []
    pos = 0.0
    while pos < length - unit * 6:
        for step in range(3):
            points += [(pos + step * unit, -step * unit), (pos + step * unit, -(step + 1) * unit)]
        pos += 3 * unit
        points.append((pos, -3 * unit))
        for step in range(3):
            points += [(pos + step * unit, -(3 - step) * unit), (pos + step * unit, -(2 - step) * unit)]
        pos += 3 * unit
        points.append((pos, 0))
    if vertical:
        mapped = [(x - py, y + px) for px, py in points]
    else:
        mapped = [(x + px, y + py) for px, py in points]
    if len(mapped) > 1:
        draw.line(mapped, fill=rgb, width=width, joint="curve")


def _supersample(size: tuple[int, int], painter) -> Image.Image:
    big = (size[0] * 2, size[1] * 2)
    image = painter(big)
    return image.resize(size, Image.LANCZOS)


def deck_background(kind: str) -> Path:
    """Render (once) a 1920x1080 slide background: cover, divider, content or appendix."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSET_DIR / f"bg_{kind}.png"
    if target.exists():
        return target

    def paint(size):
        width, height = size
        if kind == "cover":
            image = _vertical_gradient(size, "#060A0C", "#0C171A")
            image = _add(image, _glow(size, (width * 0.30, height * 0.52), width * 0.42, PALETTE["jade"], 0.30))
            image = _add(image, _glow(size, (width * 0.86, height * 0.10), width * 0.30, PALETTE["copper"], 0.18))
            draw = ImageDraw.Draw(image)
            _stars(draw, size, 900, 29, 0.9)
            draw_sunstone(draw, (width * 0.30, height * 0.52), height * 0.46, mix("jade", "obsidian", 0.55),
                          mix("copper", "obsidian", 0.35), width=4)
            draw_stepfret(draw, width * 0.06, height * 0.965, width * 0.88, height * 0.012,
                          mix("copper", "obsidian", 0.45), width=3)
        elif kind == "divider":
            image = _vertical_gradient(size, "#070C0E", "#0E1B1E")
            image = _add(image, _glow(size, (width * 0.80, height * 0.50), width * 0.40, PALETTE["jade"], 0.26))
            image = _add(image, _glow(size, (width * 0.15, height * 0.95), width * 0.30, PALETTE["copper"], 0.14))
            draw = ImageDraw.Draw(image)
            _stars(draw, size, 600, 7, 0.8)
            draw_sunstone(draw, (width * 0.80, height * 0.50), height * 0.62, mix("jade", "obsidian", 0.62),
                          mix("copper", "obsidian", 0.45), width=4)
            draw_stepfret(draw, width * 0.055, height * 0.94, width * 0.50, height * 0.012,
                          mix("copper", "obsidian", 0.45), width=3)
        elif kind == "appendix":
            image = _vertical_gradient(size, "#0A1013", "#0B1316")
            draw = ImageDraw.Draw(image)
            _stars(draw, size, 120, 3, 0.35)
        else:
            image = _vertical_gradient(size, "#0B1114", "#0E181B")
            image = _add(image, _glow(size, (width * 0.92, height * 0.06), width * 0.26, PALETTE["jade"], 0.12))
            image = _add(image, _glow(size, (width * 0.04, height * 1.02), width * 0.22, PALETTE["copper"], 0.08))
            draw = ImageDraw.Draw(image)
            _stars(draw, size, 160, 11, 0.45)
        return image

    _supersample(SLIDE_PX, paint).save(target, optimize=True)
    return target


def circular_portrait(source: Path = AVATAR, size: int = 1200, ring: str = "jade") -> Path:
    """The avatar cut into a disc with a soft jade halo, saved as RGBA PNG."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSET_DIR / f"portrait_{source.stem}_{ring}.png"
    if target.exists():
        return target
    scale = 2
    full = size * scale
    photo = Image.open(source).convert("RGB").resize((full, full), Image.LANCZOS)
    canvas = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    pad = int(full * 0.06)
    disc = Image.new("L", (full, full), 0)
    ImageDraw.Draw(disc).ellipse((pad, pad, full - pad, full - pad), fill=255)
    inner = photo.resize((full - 2 * pad, full - 2 * pad), Image.LANCZOS)
    layer = Image.new("RGB", (full, full))
    layer.paste(inner, (pad, pad))
    canvas.paste(layer, (0, 0), disc)
    halo = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    draw = ImageDraw.Draw(halo)
    r, g, b = hex_to_rgb(PALETTE[ring])
    for i in range(18):
        grow = pad * (0.15 + i * 0.05)
        alpha = max(0, 120 - i * 7)
        draw.ellipse((pad - grow, pad - grow, full - pad + grow, full - pad + grow),
                     outline=(r, g, b, alpha), width=scale * 2)
    halo = halo.filter(ImageFilter.GaussianBlur(scale * 3))
    result = Image.alpha_composite(halo, canvas)
    ImageDraw.Draw(result).ellipse((pad, pad, full - pad, full - pad), outline=(r, g, b, 255), width=scale * 4)
    result.resize((size, size), Image.LANCZOS).save(target)
    return target
