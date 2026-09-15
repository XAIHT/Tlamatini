# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Resolution-independent signature artwork, clipped to a text-free cover zone."""
from __future__ import annotations

import hashlib
import math
import random

import pdfer_color as pc


def paint_signature(canvas, design, x, y, width, height, seed=""):
    """Draw in normalized 1000 x 500 coordinates; always restore canvas state."""
    if width <= 0 or height <= 0 or not design.may_decorate("cover"):
        return
    digest = hashlib.sha256((str(seed) + design.meta.get("style", "")).encode("utf-8")).digest()
    art = _Art(canvas, design.palette, random.Random(int.from_bytes(digest[:8], "big")))
    canvas.saveState()
    try:
        path = canvas.beginPath()
        path.rect(x, y, width, height)
        canvas.clipPath(path, stroke=0)
        canvas.translate(x, y)
        canvas.scale(width / 1000.0, height / 500.0)
        canvas.linearGradient(0, 0, 1000, 500,
                              [design.palette.cover_from.as_reportlab(),
                               design.palette.cover_to.as_reportlab()])
        art.draw(design.meta.get("motif", "orbits"))
    finally:
        canvas.restoreState()


class _Art:
    def __init__(self, canvas, palette, rng):
        self.c, self.p, self.rng = canvas, palette, rng

    def color(self, role="primary", strength=1):
        return pc.mix(self.p.cover_from, self.p.get(role), strength).as_reportlab()

    def line(self, points, role="primary", strength=0.65, weight=1):
        self.c.setStrokeColor(self.color(role, strength))
        self.c.setLineWidth(weight)
        path = self.c.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        self.c.drawPath(path)

    def circle(self, x, y, radius, role="primary", strength=0.5, fill=False, weight=1):
        self.c.setFillColor(self.color(role, strength))
        self.c.setStrokeColor(self.color(role, strength))
        self.c.setLineWidth(weight)
        self.c.circle(x, y, radius, stroke=not fill, fill=fill)

    def stars(self, count=95):
        for _ in range(count):
            x, y = self.rng.uniform(25, 975), self.rng.uniform(25, 475)
            radius = self.rng.uniform(0.5, 2.1)
            self.circle(x, y, radius, "accent", self.rng.uniform(0.25, 0.85), True)
            if radius > 1.9:
                self.line([(x - 6, y), (x + 6, y)], "accent", 0.5)
                self.line([(x, y - 6), (x, y + 6)], "accent", 0.5)

    def grid(self, step=50, strength=0.15):
        for x in range(0, 1001, step):
            self.line([(x, 0), (x, 500)], strength=strength)
        for y in range(0, 501, step):
            self.line([(0, y), (1000, y)], strength=strength)

    def rings(self, cx=590, cy=240):
        for r in (90, 145, 200):
            self.circle(cx, cy, r, strength=0.45, weight=1.2)
        for i in range(60):
            a = i * math.tau / 60
            r = 212 if i % 5 else 222
            self.line([(cx + 205 * math.cos(a), cy + 205 * math.sin(a)),
                       (cx + r * math.cos(a), cy + r * math.sin(a))],
                      "accent", 0.8 if i % 5 == 0 else 0.35)

    def temple(self, cx=500, base=52, scale=1):
        for i in range(6):
            half = (225 - i * 30) * scale
            yy = base + i * 43 * scale
            self.line([(cx - half, yy), (cx - half, yy + 40 * scale),
                       (cx + half, yy + 40 * scale), (cx + half, yy)],
                      "secondary", 0.9, 2.2)
        for dx in (-22, 22):
            self.line([(cx + dx * scale, base), (cx + dx * scale, base + 255 * scale)],
                      "accent", 0.8, 1.2)
        # A repeating stepped fret, intentionally abstract rather than a glyph.
        for xx in range(30, 960, 70):
            self.line([(xx, 430), (xx, 458), (xx + 42, 458), (xx + 42, 440),
                       (xx + 18, 440), (xx + 18, 448)], "primary", 0.6, 2)

    def draw(self, motif):
        if motif in ("clouds", "dream"):
            for xx, yy, radius in ((120, 95, 48), (730, 310, 62), (345, 280, 40), (910, 105, 55)):
                for dx, dy, factor in ((-1, 0, .7), (0, .35, 1), (1, 0, .75)):
                    self.circle(xx + dx * radius, yy + dy * radius, radius * factor,
                                "secondary", 0.20, True)
                self.c.setFillColor(self.color("secondary", .2))
                self.c.roundRect(xx - radius * 1.5, yy - radius * .55,
                                 radius * 3, radius, radius * .4, stroke=0, fill=1)
            for radius in range(90, 151, 15):
                self.c.setStrokeColor(self.color("accent" if radius % 30 else "primary", .4))
                self.c.setLineWidth(8)
                self.c.arc(420 - radius, 205 - radius, 420 + radius, 205 + radius, 0, 180)
            if motif == "dream":
                self.circle(780, 375, 49, "accent", .55, True)
                self.circle(798, 391, 44, "background", 1, True)
            self.stars(24)
        elif motif == "feathers":
            self.stars(20)
            for i in range(13):
                angle = (i - 6) * .19 + math.pi / 2
                length = 265 + 60 * math.cos(i * .8)
                cx, cy = 500, 40
                dx, dy = math.cos(angle), math.sin(angle)
                self.line([(cx, cy), (cx + dx * length, cy + dy * length)], "primary", .75, 1.4)
                for j in range(5, 21):
                    r = length * j / 22
                    spread = math.sin(j / 22 * math.pi) * 28
                    xx, yy = cx + dx * r, cy + dy * r
                    self.line([(xx - dy * spread - dx * 18, yy + dx * spread - dy * 18),
                               (xx, yy), (xx + dy * spread - dx * 18, yy - dx * spread - dy * 18)],
                              "secondary" if j % 4 == 0 else "primary", .45, 1)
                self.circle(cx + dx * length, cy + dy * length, 10, "accent", .7)
        elif motif == "biolume":
            self.stars(70)
            for cx, cy, radius in ((145, 265, 54), (390, 350, 75), (650, 230, 63), (875, 370, 46)):
                for ring in range(5):
                    self.c.setStrokeColor(self.color("primary", .35 + ring * .1))
                    self.c.setLineWidth(1.4)
                    rr = radius - ring * 5
                    self.c.arc(cx - rr, cy - rr * .6, cx + rr, cy + rr * .6, 0, 180)
                for j in range(-3, 4):
                    pts = [(cx + j * radius / 4 + 12 * math.sin(t / 18 + j), cy - t)
                           for t in range(0, 161, 4)]
                    self.line(pts, "secondary" if j % 2 else "accent", .55, 1.2)
                self.circle(cx, cy + radius * .3, 4, "primary", .9, True)
        elif motif == "petals":
            self.stars(12)
            for i in range(9):
                x = 85 + i * 110
                top = 160 + 200 * (0.5 + 0.5 * math.sin(i * 1.8))
                self.line([(x, 0), (x + 20, top)], "primary", .35, 1.7)
                for j in range(3, 10):
                    y = top * j / 10
                    spread = 34 * math.sin(math.pi * j / 12)
                    self.line([(x - spread, y + 24), (x + y / top * 20, y),
                               (x + spread + 20, y + 36)],
                              "secondary" if i % 2 else "accent", .55, 2)
                for a in range(5):
                    angle = a * math.tau / 5
                    self.circle(x + 20 + 13 * math.cos(angle), top + 13 * math.sin(angle),
                                12, "secondary", .25, True)
                self.circle(x + 20, top, 7, "accent", .55, True)
        elif motif in ("confetti", "ribbons", "aurora", "nebula"):
            if motif in ("aurora", "nebula"):
                self.stars()
            for j in range(20 if motif in ("aurora", "nebula") else 8):
                pts = [(x, 220 + 105 * math.sin(x / 215 + j * .09) + j * 6)
                       for x in range(-50, 1051, 8)]
                self.line(pts, "secondary" if j % 3 else "primary", .20 + j % 5 * .065,
                          3 if motif == "nebula" else 5)
            if motif == "nebula":
                self.rings(740, 235)
            if motif == "confetti":
                for _ in range(70):
                    x, y = self.rng.uniform(20, 980), self.rng.uniform(20, 480)
                    self.line([(x, y), (x + 10, y + 17)],
                              self.rng.choice(("primary", "secondary", "accent")), .65, 5)
        elif motif in ("city", "horizon"):
            self.circle(680, 290, 118, "secondary", .30, True)
            for i in range(12):
                self.line([(540, 195 + i * 16), (820, 195 + i * 16)], "accent", .22, 2)
            if motif == "city":
                for i in range(22):
                    x, h = i * 48, self.rng.uniform(60, 225)
                    self.c.setFillColor(self.color("background", 1))
                    self.c.setStrokeColor(self.color("primary", .6))
                    self.c.rect(x, 0, 37, h, stroke=1, fill=1)
                    for y in range(18, int(h) - 8, 22):
                        self.line([(x + 9, y), (x + 25, y)], "accent", .55, 2)
            else:
                for x in range(-600, 1700, 100):
                    self.line([(500, 165), (x, 0)], "primary", .35)
                for y in (5, 27, 54, 85, 122, 163):
                    self.line([(0, y), (1000, y)], "primary", .35)
        elif motif == "solar":
            self.stars(45)
            for i in range(9):
                self.circle(590, 245, 75 + i * 10, "secondary", .18 + i * .035, weight=2)
            self.circle(590, 245, 73, "accent", .9, True)
            for i in range(48):
                a = i * math.tau / 48
                length = 158 + 38 * math.sin(i * 2.4)
                pts = [(590 + r * math.cos(a + .12 * math.sin(r / 35)),
                        245 + r * math.sin(a + .12 * math.sin(r / 35)))
                       for r in range(87, int(length), 3)]
                self.line(pts, "primary", .65, 1.4)
        elif motif in ("orbits", "eclipse", "prism"):
            self.stars(60)
            self.rings()
            if motif == "eclipse":
                self.circle(590, 240, 112, "secondary", .7, True)
                self.circle(610, 256, 105, "background", 1, True)
            elif motif == "prism":
                for i in range(13):
                    d = i * 7
                    self.line([(380 - d, 80), (595, 450 - d), (810 + d, 80), (380 - d, 80)],
                              "secondary" if i % 2 else "primary", .5, 1.3)
            else:
                for angle, r in ((.6, 90), (2.5, 145), (4.3, 200)):
                    self.circle(590 + math.cos(angle) * r, 240 + math.sin(angle) * r,
                                9, "accent", .9, True)
        elif motif in ("circuit", "chip", "blueprint", "signal"):
            self.grid(40)
            if motif == "signal":
                for i, role in enumerate(("primary", "secondary", "accent")):
                    pts = [(x, 250 + 110 * math.sin(x / (42 + 14 * i) + i)
                            * math.sin(x / 450 + .5)) for x in range(0, 1001, 3)]
                    self.line(pts, role, .9, 2)
            else:
                self.c.setFillColor(self.color("background", 1))
                self.c.setStrokeColor(self.color("primary", .8))
                self.c.roundRect(385, 135, 230, 230, 8, stroke=1, fill=1)
                self.c.rect(421, 171, 158, 158, stroke=1, fill=0)
                for i in range(10):
                    yy = 151 + i * 21
                    for sign in (-1, 1):
                        xx = 500 + sign * 115
                        end = xx + sign * (75 + i % 4 * 35)
                        self.line([(xx, yy), (end, yy), (end + sign * 35, yy + 35),
                                   (end + sign * 100, yy + 35)], "accent", .7, 1.6)
                        self.circle(end + sign * 100, yy + 35, 4, "primary", .9)
                if motif == "blueprint":
                    self.circle(500, 250, 82, "secondary", .75)
                    self.line([(350, 105), (650, 105)], "secondary", .7)
                    for x in (350, 650):
                        self.line([(x, 95), (x, 115)], "secondary", .7)
                elif motif == "chip":
                    for r in (24, 46, 68):
                        self.circle(500, 250, r, "secondary", .75)
        elif motif in ("temple", "celestial", "portal"):
            self.stars(95)
            if motif == "temple":
                self.circle(500, 280, 144, "primary", .23, True)
                self.temple()
            elif motif == "celestial":
                self.rings(500, 258)
                self.temple(500, 45, .8)
            else:
                for i in range(12):
                    radius = 60 + i * 13
                    pts = [(500 + radius * math.cos(j * math.tau / 8 + .39),
                            250 + radius * math.sin(j * math.tau / 8 + .39)) for j in range(9)]
                    self.line(pts, "secondary" if i % 3 else "accent", .35 + i * .04, 1.5)
                self.temple(170, 60, .40)
                self.temple(830, 60, .40)
