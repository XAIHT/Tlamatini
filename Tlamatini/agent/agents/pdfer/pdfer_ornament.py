# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer ornament — generated artwork, and the judgement about when to use it.

WHAT ANGELA ASKED FOR
---------------------
    *"and enable it to embed images!!!: **EXTREMELLY IMPORTANT**, so if it
    knows that is plenty safe due to the content to add an image of the type
    decoration in some parts"*

Two halves, and the second one matters more than the first.

**The images.** PDFer has no image library, no network access and must add no
dependency — so it *draws* them. Every motif in this module is generated at
render time with Pillow, in the document's own palette, from the document's
own content hash. A physics paper and a marketing brochure get genuinely
different artwork because the artwork is *derived from the design system*,
not chosen from a folder of stock assets that would look wrong in half the
documents and would have to ship in the installer.

**The judgement.** *"if it knows that is plenty safe"* is the real
requirement, and it is a safety property, not an aesthetic one. Decoration on
a drug dosage chart competes for attention with the dosage. Decoration on a
contract makes it look like a marketing mock-up of a contract. So no motif is
ever drawn on the say-so of this module: `DesignSystem.may_decorate(surface)`
must permit it, and that gate is closed by `pdfer_nuance`'s decoration budget
whenever the content is precision-critical or the classification was
uncertain. **This module can only draw what it has already been given
permission to draw.**

WHY GENERATED, NOT BUNDLED
---------------------------
* **Zero new dependencies.** Pillow already ships with Tlamatini.
* **Zero bytes in the installer.** The release must stay under 2 GiB.
* **Always on-palette.** A generated wash uses ``palette.cover_from →
  cover_to``, so it matches a seeded ``predominant_color`` automatically. A
  stock image never could.
* **Deterministic.** The RNG is seeded from the content, so re-rendering the
  same document produces byte-identical art. A document that looks different
  every time it is generated is a document nobody trusts.

CONTRACTS (do NOT weaken)
-------------------------
1. **NEVER RAISES.** Every generator returns ``None`` on any failure — a
   missing Pillow, an unwritable temp dir, a degenerate size. A PDF with no
   ornament is a fine PDF; a crashed render is not.
2. **NEVER draws without permission.** Generators are pure; the *caller* asks
   `may_decorate` first. This module holds the brush, not the decision.
3. **Everything lands under ``<app>/Temp/PDFer``**, via the ``TLAMATINI_TEMP``
   handle — never ``%TEMP%``, never ``C:\\Temp`` (the 2026-06-02 policy).
4. **Cache by content hash.** The same motif at the same size in the same
   palette is generated once per run.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import hashlib
import math
import os
import random

__all__ = [
    "OrnamentFactory",
    "MOTIFS",
    "available",
]

#: Every motif this module can draw. `pdfer_theme.ORNAMENT_PROGRAMMES`
#: composes these into per-nuance programmes.
MOTIFS = (
    "gradient_wash", "particle_field", "orbital_arcs", "grid_mesh",
    "circuit_trace", "sine_field", "spectrum_bar", "hairline_rule",
    "corner_wedge", "diagonal_split", "halftone_dots", "organic_blob",
    "scanline", "drop_cap_panel",
)

# Supersampling factor. Everything is drawn at 3× and downsampled with
# LANCZOS, because PIL has no anti-aliasing on primitives — a 1px diagonal
# drawn directly looks like a staircase in a 600 dpi PDF.
_SS = 3


def available() -> bool:
    """Is Pillow importable? Checked once, cheaply, before any generation."""
    try:
        import PIL.Image  # noqa: F401
        return True
    except Exception:
        return False


def _temp_root() -> str:
    """``<app>/Temp/PDFer`` per the Temp policy — never the OS temp dir."""
    base = (os.environ.get("TLAMATINI_TEMP") or "").strip()
    if not base:
        here = os.path.dirname(os.path.abspath(__file__))
        # agents/<pool>/<agent> → walk up to the application root.
        for _ in range(4):
            candidate = os.path.join(here, "Temp")
            if os.path.isdir(candidate):
                base = candidate
                break
            here = os.path.dirname(here)
    if not base:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_art")
    root = os.path.join(base, "PDFer")
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        pass
    return root


class OrnamentFactory:
    """Draws the document's artwork, in the document's own palette.

    One factory per render. It owns the temp directory, the deterministic
    RNG, and a small cache so a motif reused on twelve section headings is
    rasterised once.
    """

    def __init__(self, design, seed_text: str = "", logger=None,
                 scale: int = _SS):
        self.design = design
        self.palette = design.palette
        self.logger = logger
        self.scale = max(1, min(int(scale or _SS), 4))
        self.root = _temp_root()
        self._cache = {}
        self._made = []
        # Deterministic: the same document always draws the same art.
        digest = hashlib.sha256((seed_text or design.nuance)
                                .encode("utf-8", "replace")).hexdigest()
        self.seed = int(digest[:16], 16)
        self.token = digest[:10]

    # ── plumbing ────────────────────────────────────────────────────────
    def _log(self, message):
        if self.logger:
            try:
                self.logger(message)
            except Exception:
                pass

    def _rng(self, salt: str = "") -> "random.Random":
        return random.Random(self.seed ^ (hash(salt) & 0xFFFFFFFF))

    def _path(self, motif: str, width: int, height: int, salt: str = "") -> str:
        key = "%s_%dx%d_%s_%s" % (motif, width, height,
                                  self.palette.primary.hex.lstrip("#"),
                                  hashlib.md5(
                                      ("%s|%s|%s" % (self.token, salt,
                                                     self.palette.background.hex))
                                      .encode()).hexdigest()[:8])
        return os.path.join(self.root, "orn_%s.png" % key)

    def _finish(self, image, path, supersampled=True):
        """Downsample, save, remember. Returns the path or None."""
        try:
            from PIL import Image
            if supersampled and self.scale > 1:
                target = (max(1, image.width // self.scale),
                          max(1, image.height // self.scale))
                image = image.resize(target, Image.LANCZOS)
            image.save(path, "PNG", optimize=True)
            self._made.append(path)
            return path
        except Exception as exc:
            self._log("⚠️ ornament save failed (%s) — the document simply "
                      "goes without it" % type(exc).__name__)
            return None

    def _rgba(self, color, alpha=1.0):
        return color.rgb255 + (int(round(255 * max(0.0, min(1.0, alpha)))),)

    def artefacts(self) -> list:
        return list(self._made)

    # ── the public entry point ──────────────────────────────────────────
    def draw(self, motif: str, width: int, height: int, salt: str = "",
             **options):
        """Generate *motif* at *width*×*height* points. Returns a path or None.

        NEVER RAISES — an unknown motif, a missing Pillow, a zero size and a
        disk error all return None, and the renderer simply omits the image.
        """
        if not available():
            return None
        width, height = int(max(1, width)), int(max(1, height))
        if width * height > 12_000_000:      # sanity ceiling
            return None
        path = self._path(motif, width, height, salt)
        if path in self._cache:
            return self._cache[path]
        if os.path.isfile(path):
            self._cache[path] = path
            return path
        generator = getattr(self, "_draw_" + motif, None)
        if generator is None:
            return None
        try:
            result = generator(width, height, salt, options)
        except Exception as exc:
            self._log("⚠️ ornament '%s' failed (%s: %s) — omitted"
                      % (motif, type(exc).__name__, exc))
            result = None
        self._cache[path] = result
        return result

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: gradient_wash — the workhorse
    #
    #  A true perceptual gradient. The ramp is computed in OKLab by
    #  `pdfer_color.ramp`, which is why it stays luminous instead of dipping
    #  through grey at the midpoint the way a naive sRGB interpolation does.
    # ─────────────────────────────────────────────────────────────────
    def _draw_gradient_wash(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, height * scale
        start = options.get("start") or self.palette.cover_from
        end = options.get("end") or self.palette.cover_to
        angle = float(options.get("angle", 135.0))
        ease = options.get("ease", "ease_in_out")
        steps = max(24, min(360, int(options.get("steps", 128))))

        image = Image.new("RGBA", (w, h), self._rgba(start))
        draw = ImageDraw.Draw(image)
        colors = pc.ramp(start, end, steps, ease=ease)

        radians = math.radians(angle % 360.0)
        dx, dy = math.cos(radians), math.sin(radians)
        # Project the four corners onto the gradient axis so the ramp always
        # spans the whole rectangle regardless of angle.
        projections = [x * dx + y * dy for x in (0, w) for y in (0, h)]
        low, high = min(projections), max(projections)
        span = (high - low) or 1.0

        # Draw as bands perpendicular to the axis. Bands are over-drawn by
        # one step so no seam line survives the downsample.
        diagonal = math.hypot(w, h)
        for index, color in enumerate(colors):
            t0 = index / float(steps)
            offset = low + t0 * span
            cx, cy = dx * offset, dy * offset
            px, py = -dy * diagonal, dx * diagonal
            thickness = (span / steps) + 2
            draw.polygon(
                [(cx + px, cy + py), (cx - px, cy - py),
                 (cx - px + dx * thickness, cy - py + dy * thickness),
                 (cx + px + dx * thickness, cy + py + dy * thickness)],
                fill=self._rgba(color))
        return self._finish(image, self._path("gradient_wash", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: particle_field — stars. The signature of `scientific_dark`.
    # ─────────────────────────────────────────────────────────────────
    def _draw_particle_field(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, height * scale
        rng = self._rng("particles" + salt)
        base = options.get("background") or self.palette.cover_from
        top = options.get("end") or self.palette.cover_to
        image = Image.new("RGBA", (w, h), self._rgba(base))
        draw = ImageDraw.Draw(image)

        # A faint wash beneath so the field has depth rather than sitting on
        # a flat rectangle.
        for index, color in enumerate(pc.ramp(base, top, 64, ease="ease_out")):
            y0 = int(h * index / 64.0)
            y1 = int(h * (index + 1) / 64.0) + 1
            draw.rectangle([0, y0, w, y1], fill=self._rgba(color, 0.55))

        count = int(options.get("count", max(40, (width * height) // 900)))
        count = min(count, 1400)
        glow = self.palette.ornament
        accent = self.palette.accent
        for _ in range(count):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            radius = rng.choice([0.6, 0.8, 1.0, 1.2, 1.6, 2.2]) * scale
            brightness = rng.uniform(0.18, 0.95)
            color = glow if rng.random() < 0.72 else accent
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=self._rgba(color, brightness))
            # A few stars get a soft halo — cheap, and it reads as depth.
            if rng.random() < 0.07:
                halo = radius * 3.4
                draw.ellipse([x - halo, y - halo, x + halo, y + halo],
                             fill=self._rgba(color, brightness * 0.10))
        return self._finish(image, self._path("particle_field", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: orbital_arcs — concentric ellipses, off-centre
    # ─────────────────────────────────────────────────────────────────
    def _draw_orbital_arcs(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        rng = self._rng("orbits" + salt)
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        cx = w * float(options.get("cx", 0.78))
        cy = h * float(options.get("cy", 0.28))
        rings = int(options.get("rings", 7))
        color = options.get("color") or self.palette.ornament

        for index in range(rings):
            spread = (index + 1) / float(rings)
            rx = w * 0.16 * (index + 1) * rng.uniform(0.92, 1.10)
            ry = rx * rng.uniform(0.42, 0.78)
            alpha = 0.36 * (1.0 - spread * 0.72)
            draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                         outline=self._rgba(color, alpha),
                         width=max(1, int(1.15 * scale)))
            # One body on the orbit — the detail that turns rings into a
            # system rather than a target.
            if rng.random() < 0.55:
                theta = rng.uniform(0, math.tau)
                px, py = cx + rx * math.cos(theta), cy + ry * math.sin(theta)
                dot = rng.uniform(1.4, 3.0) * scale
                draw.ellipse([px - dot, py - dot, px + dot, py + dot],
                             fill=self._rgba(color, min(0.85, alpha * 3.2)))
        return self._finish(image, self._path("orbital_arcs", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: grid_mesh — a technical lattice
    # ─────────────────────────────────────────────────────────────────
    def _draw_grid_mesh(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        pitch = max(6, int(float(options.get("pitch", 18)) * scale))
        color = options.get("color") or self.palette.border
        alpha = float(options.get("alpha", 0.42))
        fade = bool(options.get("fade", True))

        line_width = max(1, int(0.6 * scale))
        for x in range(0, w + pitch, pitch):
            a = alpha * (1.0 - (x / float(w)) * 0.72) if fade else alpha
            draw.line([(x, 0), (x, h)], fill=self._rgba(color, a),
                      width=line_width)
        for y in range(0, h + pitch, pitch):
            a = alpha * (1.0 - (y / float(h)) * 0.72) if fade else alpha
            draw.line([(0, y), (w, y)], fill=self._rgba(color, a),
                      width=line_width)
        return self._finish(image, self._path("grid_mesh", width, height, salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: circuit_trace — orthogonal routing with vias
    # ─────────────────────────────────────────────────────────────────
    def _draw_circuit_trace(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        rng = self._rng("circuit" + salt)
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = options.get("color") or self.palette.primary
        accent = self.palette.accent
        traces = int(options.get("traces", max(6, w // (26 * scale))))
        line_width = max(1, int(1.1 * scale))
        step = max(8, int(11 * scale))

        for _ in range(min(traces, 90)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            alpha = rng.uniform(0.22, 0.62)
            horizontal = rng.random() < 0.5
            for _segment in range(rng.randint(3, 9)):
                length = rng.randint(2, 7) * step
                if horizontal:
                    nx, ny = x + length * rng.choice((1, -1)), y
                else:
                    nx, ny = x, y + length * rng.choice((1, -1))
                nx, ny = max(0, min(w, nx)), max(0, min(h, ny))
                draw.line([(x, y), (nx, ny)], fill=self._rgba(color, alpha),
                          width=line_width)
                x, y = nx, ny
                horizontal = not horizontal
                if rng.random() < 0.28:      # a via
                    r = 2.0 * scale
                    draw.ellipse([x - r, y - r, x + r, y + r],
                                 outline=self._rgba(accent, alpha * 1.3),
                                 width=max(1, int(0.8 * scale)))
        return self._finish(image, self._path("circuit_trace", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: sine_field — layered waves
    # ─────────────────────────────────────────────────────────────────
    def _draw_sine_field(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, height * scale
        rng = self._rng("sine" + salt)
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        layers = int(options.get("layers", 6))
        colors = pc.ramp(self.palette.primary, self.palette.accent,
                         max(2, layers))

        for index in range(layers):
            amplitude = h * rng.uniform(0.06, 0.20)
            frequency = rng.uniform(1.2, 3.6)
            phase = rng.uniform(0, math.tau)
            centre = h * (0.18 + 0.64 * index / max(1, layers - 1))
            alpha = 0.20 + 0.30 * (1.0 - index / float(layers))
            points = []
            samples = max(48, w // (2 * scale))
            for sample in range(samples + 1):
                t = sample / float(samples)
                x = t * w
                y = centre + amplitude * math.sin(phase + t * math.tau * frequency)
                points.append((x, y))
            draw.line(points, fill=self._rgba(colors[index % len(colors)], alpha),
                      width=max(1, int(1.4 * scale)), joint="curve")
        return self._finish(image, self._path("sine_field", width, height, salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: spectrum_bar — a solid gradient rule
    #
    #  This is the one that replaces the old ``border-bottom: 2px solid
    #  #C1272D`` under every heading. Same job; it is a gradient now.
    # ─────────────────────────────────────────────────────────────────
    def _draw_spectrum_bar(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, max(1, height * scale)
        start = options.get("start") or self.palette.primary
        end = options.get("end") or self.palette.accent
        taper = bool(options.get("taper", True))
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        colors = pc.ramp(start, end, min(256, max(16, w // scale)))
        band = w / float(len(colors))
        for index, color in enumerate(colors):
            t = index / float(max(1, len(colors) - 1))
            # Taper the alpha to the right so the rule fades out instead of
            # stopping dead — a hard stop reads as a truncated line.
            alpha = 1.0 if not taper else max(0.05, 1.0 - (t ** 2.2) * 0.92)
            draw.rectangle([index * band, 0, (index + 1) * band + 1, h],
                           fill=self._rgba(color, alpha))
        return self._finish(image, self._path("spectrum_bar", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: hairline_rule — the ENTIRE ornament of an academic paper
    # ─────────────────────────────────────────────────────────────────
    def _draw_hairline_rule(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, max(scale, height * scale)
        color = options.get("color") or self.palette.rule
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        thickness = max(1, int(round(float(options.get("thickness", 0.6))
                                     * scale)))
        draw.rectangle([0, 0, w, thickness], fill=self._rgba(color, 0.92))
        return self._finish(image, self._path("hairline_rule", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: corner_wedge / diagonal_split — big flat colour
    # ─────────────────────────────────────────────────────────────────
    def _draw_corner_wedge(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = options.get("color") or self.palette.accent
        corner = str(options.get("corner", "tr")).lower()
        extent = float(options.get("extent", 0.42))
        points = {
            "tr": [(w, 0), (w, h * extent), (w * (1 - extent), 0)],
            "tl": [(0, 0), (0, h * extent), (w * extent, 0)],
            "br": [(w, h), (w, h * (1 - extent)), (w * (1 - extent), h)],
            "bl": [(0, h), (0, h * (1 - extent)), (w * extent, h)],
        }.get(corner, [(w, 0), (w, h * extent), (w * (1 - extent), 0)])
        draw.polygon(points, fill=self._rgba(color,
                                             float(options.get("alpha", 0.9))))
        return self._finish(image, self._path("corner_wedge", width, height,
                                              salt))

    def _draw_diagonal_split(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, height * scale
        start = options.get("start") or self.palette.cover_from
        end = options.get("end") or self.palette.cover_to
        image = Image.new("RGBA", (w, h), self._rgba(start))
        draw = ImageDraw.Draw(image)
        lean = float(options.get("lean", 0.38))
        # Stack translucent wedges to fake a soft diagonal edge.
        colors = pc.ramp(start, end, 40, ease="ease_in_out")
        for index, color in enumerate(colors):
            t = index / float(len(colors))
            offset = h * (lean + t * 0.6)
            draw.polygon([(0, offset), (w, offset - h * lean), (w, h), (0, h)],
                         fill=self._rgba(color, 0.10 + 0.9 * t))
        return self._finish(image, self._path("diagonal_split", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: halftone_dots — a printed-ink texture
    # ─────────────────────────────────────────────────────────────────
    def _draw_halftone_dots(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = options.get("color") or self.palette.primary
        pitch = max(5, int(float(options.get("pitch", 10)) * scale))
        biggest = pitch * 0.42
        for y in range(0, h + pitch, pitch):
            row = y // pitch
            for x in range(0, w + pitch, pitch):
                # Offset alternate rows: a square grid of dots reads as a
                # grid; a staggered one reads as ink.
                cx = x + (pitch * 0.5 if row % 2 else 0)
                t = 1.0 - (cx / float(w)) * 0.85
                radius = biggest * max(0.06, t)
                if radius < 0.4:
                    continue
                draw.ellipse([cx - radius, y - radius, cx + radius, y + radius],
                             fill=self._rgba(color, 0.16 + 0.42 * t))
        return self._finish(image, self._path("halftone_dots", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: organic_blob — soft botanical shapes
    # ─────────────────────────────────────────────────────────────────
    def _draw_organic_blob(self, width, height, salt, options):
        from PIL import Image, ImageDraw, ImageFilter

        scale = self.scale
        w, h = width * scale, height * scale
        rng = self._rng("blob" + salt)
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        colors = [options.get("color") or self.palette.primary,
                  self.palette.accent, self.palette.secondary]

        for index in range(int(options.get("blobs", 3))):
            color = colors[index % len(colors)]
            cx, cy = rng.uniform(0, w), rng.uniform(0, h)
            radius = min(w, h) * rng.uniform(0.22, 0.48)
            points = []
            lobes = rng.randint(5, 9)
            for step in range(72):
                theta = step / 72.0 * math.tau
                wobble = 1.0 + 0.22 * math.sin(theta * lobes + rng.random())
                points.append((cx + radius * wobble * math.cos(theta),
                               cy + radius * wobble * 0.78 * math.sin(theta)))
            draw.polygon(points, fill=self._rgba(color, rng.uniform(0.07, 0.17)))
        try:
            image = image.filter(ImageFilter.GaussianBlur(radius=2.5 * scale))
        except Exception:
            pass                      # a crisp blob is still a blob
        return self._finish(image, self._path("organic_blob", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: scanline — CRT texture for the security theme
    # ─────────────────────────────────────────────────────────────────
    def _draw_scanline(self, width, height, salt, options):
        from PIL import Image, ImageDraw

        scale = self.scale
        w, h = width * scale, height * scale
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = options.get("color") or self.palette.ornament
        pitch = max(2, int(float(options.get("pitch", 3)) * scale))
        for y in range(0, h, pitch):
            draw.line([(0, y), (w, y)],
                      fill=self._rgba(color, float(options.get("alpha", 0.10))),
                      width=max(1, scale // 2))
        return self._finish(image, self._path("scanline", width, height, salt))

    # ─────────────────────────────────────────────────────────────────
    #  MOTIF: drop_cap_panel — the tinted square behind an initial
    # ─────────────────────────────────────────────────────────────────
    def _draw_drop_cap_panel(self, width, height, salt, options):
        from PIL import Image, ImageDraw
        import pdfer_color as pc

        scale = self.scale
        w, h = width * scale, height * scale
        image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        start = options.get("start") or self.palette.primary
        end = options.get("end") or self.palette.accent
        colors = pc.ramp(start, end, 48, ease="ease_in_out")
        for index, color in enumerate(colors):
            y0 = h * index / len(colors)
            y1 = h * (index + 1) / len(colors) + 1
            draw.rectangle([0, y0, w, y1], fill=self._rgba(color, 0.92))
        return self._finish(image, self._path("drop_cap_panel", width, height,
                                              salt))

    # ─────────────────────────────────────────────────────────────────
    #  COMPOSITES — what the renderer actually asks for
    # ─────────────────────────────────────────────────────────────────
    def cover_art(self, width, height, salt="cover"):
        """The full-bleed cover image: a wash, plus this theme's motifs on top.

        Returns a path or None. The renderer calls this only after
        ``design.may_decorate('cover')`` has said yes.
        """
        if not available():
            return None
        motifs = self.design.motifs()
        base = self.draw("gradient_wash", width, height, salt=salt + "base",
                         ease="ease_in_out")
        if not base:
            return None
        overlays = [m for m in motifs if m != "gradient_wash"][:3]
        if not overlays:
            return base
        try:
            from PIL import Image
            canvas = Image.open(base).convert("RGBA")
            for motif in overlays:
                layer_path = self.draw(motif, width, height,
                                       salt=salt + motif)
                if not layer_path:
                    continue
                layer = Image.open(layer_path).convert("RGBA")
                if layer.size != canvas.size:
                    layer = layer.resize(canvas.size, Image.LANCZOS)
                canvas = Image.alpha_composite(canvas, layer)
            out = self._path("cover_composite", width, height, salt)
            canvas.save(out, "PNG", optimize=True)
            self._made.append(out)
            return out
        except Exception as exc:
            self._log("⚠️ cover composite failed (%s) — using the plain wash"
                      % type(exc).__name__)
            return base

    def section_rule(self, width, thickness=3, salt="rule"):
        """The gradient rule that replaces the old flat 2px border."""
        motifs = self.design.motifs()
        motif = ("spectrum_bar" if "spectrum_bar" in motifs
                 or self.decoration_rich() else "hairline_rule")
        return self.draw(motif, int(width), int(max(1, thickness)), salt=salt)

    def decoration_rich(self) -> bool:
        return self.design.decoration in ("moderate", "rich")

    def header_band(self, width, height=26, salt="band"):
        return self.draw("gradient_wash", int(width), int(height),
                         salt=salt, angle=0.0, ease="ease_out")

    def cleanup(self, keep: bool = True) -> int:
        """Remove generated art. Kept by default: the PDF references the files
        only while it is being built, but a user debugging a strange cover
        wants to be able to look at it."""
        if keep:
            return 0
        removed = 0
        for path in self._made:
            try:
                os.remove(path)
                removed += 1
            except Exception:
                pass
        return removed
