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
# pptxer_draw.py — GENERATED ARTWORK.  PPTXer draws its own visuals.
#
# Sibling module of pptxer.py. Pillow + stdlib. Imports pptxer_color only.
# Nothing from agent.*.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHY AN AGENT SHOULD DRAW ITS OWN ART
# ─────────────────────────────────────────────────────────────────────────────
# A marketing or gaming deck is mostly VISUAL. The three obvious ways to get
# visuals are all wrong for a shipped agent:
#
#   · bundle a stock library → hundreds of MB in an installer that must stay
#     under 2 GiB, and the same twelve images in everybody's deck;
#   · download art at render time → a network dependency on the critical path,
#     plus a licence question PPTXer cannot answer for the user;
#   · use clip-art → it looks like 2003.
#
# So PPTXer PAINTS. Every motif here is drawn with Pillow, at render
# resolution, in the deck's OWN palette, seeded from the content hash. That
# gives three properties worth more than a stock library:
#
#   1. it always matches the theme, because the colours ARE the theme's;
#   2. it costs nothing to ship and needs no network;
#   3. it is DETERMINISTIC — the same deck re-renders byte-identically, which
#      is what makes a diff meaningful and a regression test possible.
#
# ─────────────────────────────────────────────────────────────────────────────
# CONTRACTS (do NOT weaken)
# ─────────────────────────────────────────────────────────────────────────────
#  1. FAIL-OPEN. Every generator returns None rather than raising. A missing
#     ornament is a plainer slide; an exception is a lost deck.
#  2. DETERMINISTIC. Randomness comes from a seeded random.Random, never the
#     global RNG, so two runs of the same content agree exactly.
#  3. ART NEVER SITS WHERE TEXT WILL. The caller places art in regions the
#     layout solver has already reserved; nothing here positions itself.
#  4. EVERY MOTIF RESPECTS THE CONTRAST FLOOR OF WHAT SITS ON TOP. A background
#     that is busy where the title lands is a background that made the title
#     unreadable — so busy motifs ship with a built-in scrim.

import hashlib
import math
import os
import random

from pptxer_color import Color, gradient_stops, mix_oklab, parse_color

__all__ = [
    "ORNAMENTS",
    "draw_ornament",
    "draw_gradient_field",
    "draw_scrim",
    "draw_glow_orb",
    "make_seed",
    "available",
]

ORNAMENTS = (
    "hex_grid", "circuitry", "glitch_scan", "pixel_grid", "runic_border",
    "tactical_grid", "particle_burst", "gradient_mesh", "corporate_band",
    "thin_rule", "blob_shapes", "soft_shapes", "spotlight", "constellation",
    "wave_field", "none",
)


def available() -> bool:
    """Is Pillow importable? Checked once, lazily, never raises."""
    try:
        from PIL import Image, ImageDraw  # noqa: F401
        return True
    except Exception:                                             # noqa: BLE001
        return False


def make_seed(*parts) -> int:
    """A stable integer seed from arbitrary content."""
    joined = "\x1f".join(str(p) for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big")


def _rgba(color, alpha=None) -> tuple:
    c = parse_color(color) or Color(0, 0, 0)
    r, g, b = c.rgb255
    a = int(round((c.a if alpha is None else float(alpha)) * 255))
    return (r, g, b, max(0, min(255, a)))


def _canvas(width, height):
    from PIL import Image
    return Image.new("RGBA", (max(1, int(width)), max(1, int(height))), (0, 0, 0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# Gradient fields — the workhorse background
# ─────────────────────────────────────────────────────────────────────────────

def draw_gradient_field(width, height, colors, angle_deg=135.0, out_path=None,
                        noise=0.0, seed=0):
    """A smooth multi-stop OKLab gradient rendered at real pixel size.

    PowerPoint CAN fill a shape with a gradient, but only with a handful of
    stops interpolated in sRGB, which is what makes stock gradients look
    muddy. Rendering the ramp ourselves — with stops already corrected in
    OKLab — is the single biggest visual upgrade in the whole agent.

    `noise` adds a faint dither. A perfectly smooth digital gradient BANDS on a
    projector (8-bit per channel across 13 feet of screen), and a little noise
    is the standard print-and-broadcast fix for exactly that.
    """
    if not available():
        return None
    try:
        from PIL import Image

        w = max(1, int(width))
        h = max(1, int(height))
        stops = [parse_color(c) or Color(0, 0, 0) for c in (colors or [])]
        if len(stops) < 2:
            stops = [Color(0, 0, 0), Color(1, 1, 1)]

        ramp = gradient_stops(stops[0], stops[-1], 256,
                              via=stops[len(stops) // 2] if len(stops) > 2 else None)
        lut = [c.rgb255 for c in ramp]

        rad = math.radians(float(angle_deg))
        dx = math.cos(rad)
        dy = math.sin(rad)
        # Project each pixel onto the gradient axis and normalise to 0..255.
        denom = abs(dx) * w + abs(dy) * h
        denom = denom if denom else 1.0
        x0 = 0.0 if dx >= 0 else float(w)
        y0 = 0.0 if dy >= 0 else float(h)

        img = Image.new("RGB", (w, h))
        px = img.load()
        rng = random.Random(seed)
        amp = max(0.0, min(0.08, float(noise)))

        for y in range(h):
            yy = (y - y0) * dy
            for x in range(w):
                t = ((x - x0) * dx + yy) / denom
                idx = int(t * 255.0)
                idx = 0 if idx < 0 else (255 if idx > 255 else idx)
                r, g, b = lut[idx]
                if amp:
                    n = int((rng.random() - 0.5) * amp * 255)
                    r = max(0, min(255, r + n))
                    g = max(0, min(255, g + n))
                    b = max(0, min(255, b + n))
                px[x, y] = (r, g, b)

        return _save(img.convert("RGBA"), out_path)
    except Exception:                                             # noqa: BLE001
        return None


def draw_scrim(width, height, color, direction="bottom", strength=0.86,
               out_path=None):
    """A transparency ramp that makes text legible over a photograph.

    This is the honest answer to "put the title on the hero image". Without a
    scrim the title's contrast depends on whatever pixels happen to be behind
    it — which is unknowable at build time and different on every image. With
    one, the ground under the text is a KNOWN colour and the theme's contrast
    guarantee holds again.
    """
    if not available():
        return None
    try:
        from PIL import Image

        w = max(1, int(width))
        h = max(1, int(height))
        base = parse_color(color) or Color(0, 0, 0)
        r, g, b = base.rgb255
        s = max(0.0, min(1.0, float(strength)))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        px = img.load()

        d = (direction or "bottom").strip().lower()
        for y in range(h):
            for_x_alpha = None
            if d == "bottom":
                t = y / max(1, h - 1)
            elif d == "top":
                t = 1.0 - y / max(1, h - 1)
            elif d == "full":
                t = 1.0
            else:
                t = None
            if t is not None:
                # Ease-in so the clear end stays genuinely clear.
                a = int(255 * s * (t ** 1.9))
                for x in range(w):
                    px[x, y] = (r, g, b, a)
                continue
            for x in range(w):
                if d == "left":
                    tt = 1.0 - x / max(1, w - 1)
                elif d == "right":
                    tt = x / max(1, w - 1)
                else:
                    tt = 0.5
                for_x_alpha = int(255 * s * (tt ** 1.9))
                px[x, y] = (r, g, b, for_x_alpha)

        return _save(img, out_path)
    except Exception:                                             # noqa: BLE001
        return None


def draw_glow_orb(size, color, intensity=0.9, out_path=None):
    """A soft radial glow — the light source behind gaming/neon compositions."""
    if not available():
        return None
    try:
        from PIL import Image

        n = max(8, int(size))
        img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        px = img.load()
        c = parse_color(color) or Color(1, 1, 1)
        r, g, b = c.rgb255
        centre = (n - 1) / 2.0
        inten = max(0.0, min(1.0, float(intensity)))

        for y in range(n):
            dy = (y - centre) / centre
            for x in range(n):
                dx = (x - centre) / centre
                dist = math.hypot(dx, dy)
                if dist >= 1.0:
                    continue
                # Inverse-square-ish falloff reads as real light; a linear ramp
                # reads as a flat disc with a blurry edge.
                a = int(255 * inten * ((1.0 - dist) ** 2.4))
                px[x, y] = (r, g, b, a)

        return _save(img, out_path)
    except Exception:                                             # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# The ornament catalogue
# ─────────────────────────────────────────────────────────────────────────────

def draw_ornament(name, width, height, theme_colors, out_path=None, seed=0,
                  intensity="moderate"):
    """Draw one named motif. Returns the saved path, or None (fail-open).

    `theme_colors` is a dict with at least 'ground', 'accent', 'accent_2'.
    `intensity` ∈ restrained | moderate | rich, and scales density/opacity so
    the SAME motif can sit behind a dense chart slide or shout on a cover.
    """
    if not available():
        return None

    key = (name or "none").strip().lower()
    if key in ("", "none"):
        return None

    fn = _ORNAMENT_FNS.get(key)
    if fn is None:
        return None

    try:
        w = max(8, int(width))
        h = max(8, int(height))
        rng = random.Random(seed or make_seed(key, w, h))
        alpha, density = _INTENSITY.get(
            (intensity or "moderate").strip().lower(), (0.22, 1.0))
        cols = {
            "ground": parse_color(theme_colors.get("ground")) or Color(0.05, 0.05, 0.07),
            "accent": parse_color(theme_colors.get("accent")) or Color(0.2, 0.8, 0.9),
            "accent_2": parse_color(theme_colors.get("accent_2")) or Color(0.8, 0.2, 0.7),
            "accent_3": parse_color(theme_colors.get("accent_3")) or Color(0.9, 0.7, 0.2),
            "text": parse_color(theme_colors.get("text")) or Color(1, 1, 1),
        }
        img = fn(w, h, cols, rng, alpha, density)
        return _save(img, out_path) if img is not None else None
    except Exception:                                             # noqa: BLE001
        return None


_INTENSITY = {
    "restrained": (0.12, 0.55),
    "moderate": (0.22, 1.0),
    "rich": (0.34, 1.6),
}


def _hex_grid(w, h, cols, rng, alpha, density):
    """Interlocking hexagons — esports, tech, 'systems' decks."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    radius = max(14, int(min(w, h) / (9 * max(0.35, density))))
    dx = radius * 1.5
    dy = radius * math.sqrt(3)
    stroke = max(1, int(radius / 16))

    row = 0
    y = -dy
    while y < h + dy:
        x = -dx if row % 2 == 0 else -dx / 2
        while x < w + dx:
            pts = []
            for i in range(6):
                ang = math.radians(60 * i)
                pts.append((x + radius * math.cos(ang), y + radius * math.sin(ang)))
            t = rng.random()
            col = mix_oklab(cols["accent"], cols["accent_2"], t)
            a = alpha * (0.35 + 0.65 * rng.random())
            d.polygon(pts, outline=_rgba(col, a), width=stroke)
            x += dx * 2
        y += dy / 2
        row += 1
    return img


def _circuitry(w, h, cols, rng, alpha, density):
    """Orthogonal traces with via pads — technical architecture, GDD systems."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    step = max(18, int(min(w, h) / (14 * max(0.35, density))))
    stroke = max(1, step // 12)
    traces = int(26 * density)

    for _ in range(traces):
        x = rng.randrange(0, max(1, w), step)
        y = rng.randrange(0, max(1, h), step)
        col = mix_oklab(cols["accent"], cols["accent_2"], rng.random())
        a = alpha * (0.4 + 0.6 * rng.random())
        segments = rng.randint(3, 8)
        pts = [(x, y)]
        for _ in range(segments):
            if rng.random() < 0.5:
                x += step * rng.choice((-2, -1, 1, 2))
            else:
                y += step * rng.choice((-2, -1, 1, 2))
            x = max(0, min(w, x))
            y = max(0, min(h, y))
            pts.append((x, y))
        d.line(pts, fill=_rgba(col, a), width=stroke, joint="curve")
        pad = max(2, stroke * 2)
        d.ellipse([pts[-1][0] - pad, pts[-1][1] - pad,
                   pts[-1][0] + pad, pts[-1][1] + pad],
                  fill=_rgba(col, min(1.0, a * 1.8)))
    return img


def _glitch_scan(w, h, cols, rng, alpha, density):
    """CRT scanlines plus chromatic offset bars — cyberpunk, trailer beats."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)

    gap = max(3, int(4 / max(0.4, density)))
    for y in range(0, h, gap):
        d.line([(0, y), (w, y)], fill=_rgba(cols["ground"], alpha * 0.55), width=1)

    for _ in range(int(16 * density)):
        y = rng.randrange(0, h)
        bar_h = rng.randint(2, max(3, h // 44))
        off = rng.randint(-w // 26, w // 26)
        col = cols["accent"] if rng.random() < 0.5 else cols["accent_2"]
        d.rectangle([off, y, w + off, y + bar_h],
                    fill=_rgba(col, alpha * (0.45 + 0.55 * rng.random())))
    return img


def _pixel_grid(w, h, cols, rng, alpha, density):
    """Chunky pixel blocks — retro / arcade."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    cell = max(10, int(min(w, h) / (18 * max(0.35, density))))
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if rng.random() > 0.13 * density:
                continue
            col = mix_oklab(cols["accent"], cols["accent_2"], rng.random())
            d.rectangle([x, y, x + cell - 1, y + cell - 1],
                        fill=_rgba(col, alpha * (0.4 + 0.6 * rng.random())))
    return img


def _runic_border(w, h, cols, rng, alpha, density):
    """A carved double border with corner marks — fantasy / lore."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    inset = max(10, int(min(w, h) * 0.035))
    stroke = max(2, inset // 7)
    gold = cols["accent"]

    d.rectangle([inset, inset, w - inset, h - inset],
                outline=_rgba(gold, alpha * 1.5), width=stroke)
    d.rectangle([inset * 2, inset * 2, w - inset * 2, h - inset * 2],
                outline=_rgba(gold, alpha * 0.8), width=max(1, stroke // 2))

    mark = inset * 2
    for cx, cy, sx, sy in ((inset, inset, 1, 1), (w - inset, inset, -1, 1),
                           (inset, h - inset, 1, -1), (w - inset, h - inset, -1, -1)):
        d.line([(cx, cy + sy * mark), (cx, cy), (cx + sx * mark, cy)],
               fill=_rgba(gold, alpha * 1.9), width=stroke)
    return img


def _tactical_grid(w, h, cols, rng, alpha, density):
    """A map grid with reticle ticks — military / tactical."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    step = max(28, int(min(w, h) / (10 * max(0.35, density))))
    col = cols["accent"]

    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=_rgba(col, alpha * 0.45), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=_rgba(col, alpha * 0.45), width=1)

    tick = max(4, step // 6)
    for x in range(0, w, step * 3):
        for y in range(0, h, step * 3):
            d.line([(x - tick, y), (x + tick, y)], fill=_rgba(col, alpha * 1.6), width=2)
            d.line([(x, y - tick), (x, y + tick)], fill=_rgba(col, alpha * 1.6), width=2)
    return img


def _particle_burst(w, h, cols, rng, alpha, density):
    """Radiating particles — streamer kits, launch moments."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    cx, cy = w * 0.5, h * 0.5
    count = int(230 * density)
    for _ in range(count):
        ang = rng.random() * math.tau
        dist = (rng.random() ** 0.55) * min(w, h) * 0.62
        x = cx + math.cos(ang) * dist
        y = cy + math.sin(ang) * dist * 0.72
        r = max(1, int(rng.random() * min(w, h) / 140))
        col = mix_oklab(cols["accent"], cols["accent_2"], rng.random())
        fade = 1.0 - dist / (min(w, h) * 0.62)
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=_rgba(col, alpha * max(0.0, fade) * 1.7))
    return img


def _gradient_mesh(w, h, cols, rng, alpha, density):
    """Overlapping soft colour blooms — the modern brand/product background."""
    from PIL import Image, ImageFilter
    img = _canvas(w, h)
    blobs = max(3, int(5 * density))
    for i in range(blobs):
        layer = _canvas(w, h)
        from PIL import ImageDraw
        d = ImageDraw.Draw(layer)
        col = (cols["accent"], cols["accent_2"], cols["accent_3"])[i % 3]
        rx = w * (0.26 + rng.random() * 0.34)
        ry = h * (0.26 + rng.random() * 0.34)
        cx = rng.random() * w
        cy = rng.random() * h
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                  fill=_rgba(col, alpha * 1.5))
        layer = layer.filter(ImageFilter.GaussianBlur(radius=max(8, int(min(w, h) / 9))))
        img = Image.alpha_composite(img, layer)
    return img


def _corporate_band(w, h, cols, rng, alpha, density):
    """A restrained diagonal accent band — the corporate default."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    band = max(6, int(h * 0.055))
    d.polygon([(0, h), (0, h - band), (w, h - band * 3), (w, h - band * 2)],
              fill=_rgba(cols["accent"], alpha * 2.0))
    d.polygon([(0, h - band), (0, h - band * 1.35),
               (w, h - band * 3.35), (w, h - band * 3)],
              fill=_rgba(cols["accent_2"], alpha * 1.4))
    return img


def _thin_rule(w, h, cols, rng, alpha, density):
    """One hairline — luxury. The most restrained motif in the catalogue."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    y = int(h * 0.5)
    d.line([(int(w * 0.08), y), (int(w * 0.92), y)],
           fill=_rgba(cols["accent"], min(1.0, alpha * 3.0)), width=max(1, h // 260))
    return img


def _blob_shapes(w, h, cols, rng, alpha, density):
    """Organic rounded blobs — social / consumer."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    for i in range(max(3, int(6 * density))):
        col = (cols["accent"], cols["accent_2"], cols["accent_3"])[i % 3]
        rx = w * (0.10 + rng.random() * 0.20)
        ry = rx * (0.72 + rng.random() * 0.5)
        cx = rng.random() * w
        cy = rng.random() * h
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                  fill=_rgba(col, alpha * 1.25))
    return img


def _soft_shapes(w, h, cols, rng, alpha, density):
    """Rounded rectangles at low opacity — training / education."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    for i in range(max(3, int(7 * density))):
        col = (cols["accent"], cols["accent_2"])[i % 2]
        bw = w * (0.12 + rng.random() * 0.20)
        bh = h * (0.10 + rng.random() * 0.18)
        x = rng.random() * (w - bw)
        y = rng.random() * (h - bh)
        r = int(min(bw, bh) * 0.3)
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=r,
                            fill=_rgba(col, alpha * 0.9))
    return img


def _spotlight(w, h, cols, rng, alpha, density):
    """A stage wash from above — keynote."""
    from PIL import ImageFilter, ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    cx = w * 0.5
    d.polygon([(cx - w * 0.07, 0), (cx + w * 0.07, 0),
               (cx + w * 0.46, h), (cx - w * 0.46, h)],
              fill=_rgba(cols["accent"], alpha * 1.15))
    img = img.filter(ImageFilter.GaussianBlur(radius=max(10, int(min(w, h) / 11))))
    return img


def _constellation(w, h, cols, rng, alpha, density):
    """Points joined by faint lines — research, data, 'network' ideas."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    n = max(10, int(34 * density))
    pts = [(rng.random() * w, rng.random() * h) for _ in range(n)]
    link = min(w, h) * 0.24
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:]:
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist < link:
                a = alpha * (1.0 - dist / link) * 0.8
                d.line([(x1, y1), (x2, y2)], fill=_rgba(cols["accent"], a), width=1)
    for x, y in pts:
        r = max(1, int(min(w, h) / 320))
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=_rgba(cols["accent_2"], min(1.0, alpha * 2.4)))
    return img


def _wave_field(w, h, cols, rng, alpha, density):
    """Stacked sine waves — audio, motion, 'signal' themes."""
    from PIL import ImageDraw
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    lines = max(4, int(11 * density))
    for i in range(lines):
        t = i / max(1, lines - 1)
        col = mix_oklab(cols["accent"], cols["accent_2"], t)
        amp = h * 0.05 * (0.5 + rng.random())
        freq = 1.3 + rng.random() * 2.4
        phase = rng.random() * math.tau
        base = h * (0.12 + 0.76 * t)
        pts = []
        steps = max(24, w // 8)
        for s in range(steps + 1):
            x = w * s / steps
            y = base + math.sin(x / w * math.tau * freq + phase) * amp
            pts.append((x, y))
        d.line(pts, fill=_rgba(col, alpha * 1.3),
               width=max(1, int(h / 340)), joint="curve")
    return img


_ORNAMENT_FNS = {
    "hex_grid": _hex_grid,
    "circuitry": _circuitry,
    "glitch_scan": _glitch_scan,
    "pixel_grid": _pixel_grid,
    "runic_border": _runic_border,
    "tactical_grid": _tactical_grid,
    "particle_burst": _particle_burst,
    "gradient_mesh": _gradient_mesh,
    "corporate_band": _corporate_band,
    "thin_rule": _thin_rule,
    "blob_shapes": _blob_shapes,
    "soft_shapes": _soft_shapes,
    "spotlight": _spotlight,
    "constellation": _constellation,
    "wave_field": _wave_field,
}


def compose_background(width, height, theme, out_path, seed=0,
                       with_ornament=True, protect_text=True):
    """The full slide background: gradient field + optional ornament.

    One call, one PNG, already flattened — so the builder inserts exactly one
    picture rather than stacking three shapes PowerPoint would have to
    composite on every repaint.

    ═════════════════════════════════════════════════════════════════════════
     `protect_text` — THE ARTWORK YIELDS TO LEGIBILITY, NEVER THE REVERSE
    ═════════════════════════════════════════════════════════════════════════
    Measured 2026-09-14: a `restrained` gradient_mesh over a near-black ground
    still produced local blooms bright enough that body text rendered at
    6.19:1 against the 7.0:1 projected floor — even though the palette cleared
    the floor against the nominal ground.

    Two wrong fixes were tried and rejected:
      · estimate the ornament's contribution and darken the TEXT — this forced
        the title from #00E89C to flat white and destroyed the treatment;
      · estimate it more accurately — the estimate still missed, because a
        soft blob is locally opaque even when it is globally sparse.

    The right fix is to stop estimating. This function MEASURES the image it
    just composited and, while the worst pixel would break the text's floor,
    fades the ornament layer and re-composites. The palette is never touched,
    so the design survives intact and only the decoration gives ground.

    That is the correct priority: a deck whose ornament is 30% softer still
    looks designed; a deck whose body text cannot be read from the back of the
    room has failed at the only job it had.
    """
    if not available():
        return None
    try:
        from PIL import Image

        pal = {k: v.hex for k, v in theme.palette.items()}
        base_path = draw_gradient_field(
            width, height,
            [theme.color("ground_deep"), theme.color("ground")],
            angle_deg=118.0, noise=0.012, seed=seed,
        )
        if base_path is None:
            return None
        base = Image.open(base_path).convert("RGBA")
        _quiet_remove(base_path)

        if not (with_ornament and theme.decorations_allowed
                and theme.ornament != "none"):
            return _save(base, out_path)

        orn_path = draw_ornament(theme.ornament, width, height, pal,
                                 out_path=None, seed=seed,
                                 intensity=theme.decoration)
        if not orn_path:
            return _save(base, out_path)

        orn = Image.open(orn_path).convert("RGBA")
        _quiet_remove(orn_path)

        if not protect_text:
            return _save(Image.alpha_composite(base, orn), out_path)

        from pptxer_color import (BODY_CONTRAST_FLOOR, DISPLAY_CONTRAST_FLOOR,
                                  contrast_ratio, relative_luminance)

        # ⚠️ PROTECT THE WEAKEST TEXT ROLE, NOT THE MAIN ONE.
        # Measured 2026-09-14: guarding `text` (#EBF9F2) left the FOOTER
        # (#B1C3BA, dimmer and the smallest type on the slide) rendering at
        # 6.97:1 against the 7.0 floor. The footer and caption are the first
        # things lost at the back of a room, so the ornament must be faded
        # until the DIMMEST role clears — anything else protects the text that
        # needed protecting least.
        candidates = [theme.color(role) for role in
                      ("text", "footer", "caption", "text_muted")
                      if role in theme.palette]
        ground_is_dark = relative_luminance(theme.color("ground")) < 0.18
        text = (min(candidates, key=relative_luminance) if ground_is_dark
                else max(candidates, key=relative_luminance)) \
            if candidates else theme.color("text")

        # ⚠️ AND THE DISPLAY ROLES TOO — they are a DIFFERENT COLOUR SITTING ON
        # A DIFFERENT PART OF THE ARTWORK, so guarding the body roles says
        # nothing about them. Measured 2026-09-14 on the product_launch deck:
        # every body role cleared 7.0 while the cover title rendered at
        # 4.17:1 and the section title at 4.24:1 against their 4.5 floor.
        # Proved by construction rather than argued — the SAME deck rebuilt
        # with `ornament: none` audits LAYOUT CLEAN, so the motif, not the
        # palette, was the thing that had to yield.
        #
        # Each role answers to ITS OWN floor. Body type is small and read for
        # minutes; display type is enormous and read for seconds. Holding a
        # 54pt title to the 7.0 body floor would fade every motif to nothing
        # and buy no legibility at all.
        #
        # 1.04 not 1.02: a ratio computed on sampled pixels lands a hair below
        # the same ratio measured on the antialiased render.
        guarded = [(text, BODY_CONTRAST_FLOOR * 1.04)]
        for role in ("title", "heading", "subtitle"):
            if role in theme.palette:
                guarded.append((theme.color(role),
                                DISPLAY_CONTRAST_FLOOR * 1.04))

        scale = 1.0
        composed = Image.alpha_composite(base, orn)

        # Six rungs of 15% each: enough to rescue any realistic case, and it
        # terminates at 0.25 opacity rather than deleting the ornament — a
        # faint motif is still a design decision, an absent one is a blank.
        for _ in range(6):
            grounds = _worst_grounds_for(composed, [c for c, _ in guarded])
            if len(grounds) != len(guarded):
                break
            if all(ground is None or contrast_ratio(color, ground) >= floor
                   for (color, floor), ground in zip(guarded, grounds)):
                break
            scale *= 0.85
            faded = orn.copy()
            alpha = faded.getchannel("A").point(lambda a: int(a * scale))
            faded.putalpha(alpha)
            composed = Image.alpha_composite(base, faded)

        return _save(composed, out_path)
    except Exception:                                             # noqa: BLE001
        return None


def _worst_grounds_for(image, text_colors, percentile=0.985):
    """The hardest ground for EACH of several text colours, in ONE image pass.

    Scanning is the expensive half — decoding the image and touching every
    sampled pixel. The ratio itself is arithmetic on three numbers. So the
    grid is sampled once and every colour is scored against those same
    pixels, which is what makes guarding four roles cost very nearly what
    guarding one used to. Returns a list parallel to `text_colors` (a dict
    would need the colours to be hashable, which is not part of their
    contract); an empty list on any failure, so the caller can tell
    "measured nothing" from "measured and it was fine".
    """
    try:
        from pptxer_color import contrast_ratio

        colors = list(text_colors)
        if not colors:
            return []

        w, h = image.size
        step = max(2, min(w, h) // 90)
        rgb = image.convert("RGB")
        px = rgb.load()
        grounds = []
        for y in range(0, h, step):
            for x in range(0, w, step):
                r, g, b = px[x, y]
                grounds.append("#%02X%02X%02X" % (r, g, b))
        if not grounds:
            return []

        worst = []
        for text_color in colors:
            ratios = sorted((contrast_ratio(text_color, ground), ground)
                            for ground in grounds)
            idx = min(len(ratios) - 1, int(len(ratios) * (1.0 - percentile)))
            worst.append(ratios[idx][1])
        return worst
    except Exception:                                             # noqa: BLE001
        return []


def _worst_ground_for(image, text_color, percentile=0.985):
    """The background colour that is HARDEST for `text_color` to sit on.

    Samples a grid and returns the colour at the given percentile of *worst
    contrast*, not the single worst pixel — one stray antialiased pixel must
    not condemn an entire background, but 1.5% of the slide being illegible
    genuinely would be.
    """
    try:
        from pptxer_color import contrast_ratio

        w, h = image.size
        step = max(2, min(w, h) // 90)
        rgb = image.convert("RGB")
        px = rgb.load()
        ratios = []
        for y in range(0, h, step):
            for x in range(0, w, step):
                r, g, b = px[x, y]
                ratios.append((contrast_ratio(text_color,
                                              "#%02X%02X%02X" % (r, g, b)),
                               (r, g, b)))
        if not ratios:
            return None
        ratios.sort(key=lambda pair: pair[0])
        idx = min(len(ratios) - 1, int(len(ratios) * (1.0 - percentile)))
        r, g, b = ratios[idx][1]
        return "#%02X%02X%02X" % (r, g, b)
    except Exception:                                             # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Saving
# ─────────────────────────────────────────────────────────────────────────────

_TEMP_COUNTER = [0]


def _temp_dir() -> str:
    """Scratch under <app>/Temp, per the Tlamatini directory policy.

    TLAMATINI_TEMP is exported by the core and inherited by every pool agent;
    when it is absent (a bare unit test) we fall back to the CWD, never to
    C:\\Temp or the OS temp.
    """
    root = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if not root:
        root = os.getcwd()
    target = os.path.join(root, "PPTXer", "art")
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except Exception:                                             # noqa: BLE001
        return root


def _save(img, out_path):
    try:
        if not out_path:
            _TEMP_COUNTER[0] += 1
            out_path = os.path.join(
                _temp_dir(), f"art_{os.getpid()}_{_TEMP_COUNTER[0]:04d}.png")
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        img.save(out_path, "PNG", optimize=True)
        return out_path
    except Exception:                                             # noqa: BLE001
        return None


def _quiet_remove(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:                                             # noqa: BLE001
        pass
