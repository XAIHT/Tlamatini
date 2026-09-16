# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Original, deterministic TikZ artwork. A clipped 120 x 60 mm art region.

No text nodes, images, shell escape, downloads or external random state. The
Mesoamerican-inspired geometries are contemporary inventions, not reproductions
of historical glyphs. Artwork lives in normal TeX flow, never behind body text.
"""
import math
import random


def artwork(motif, decoration="rich"):
    if decoration == "none":
        return ""
    out = [r"\begin{tikzpicture}[x=1mm,y=1mm,line cap=round,line join=round]",
           r"\path[use as bounding box] (0,0) rectangle (120,60);",
           r"\clip (0,0) rectangle (120,60);"]

    def point(x, y):
        return "(%.3f,%.3f)" % (x, y)

    def line(points, opts="TLPrimary,line width=.45pt", close=False):
        out.append("\\draw[%s] %s%s;" % (
            opts, " -- ".join(point(*p) for p in points), " -- cycle" if close else ""))

    def circle(x, y, radius, opts="TLPrimary,line width=.45pt"):
        out.append("\\draw[%s] %s circle[radius=%.3fmm];" % (opts, point(x, y), radius))

    def rect(x, y, w, h, opts="TLPrimary,line width=.4pt"):
        out.append("\\draw[%s] %s rectangle %s;" % (opts, point(x, y), point(x + w, y + h)))

    def curve(start, c1, c2, end, opts="TLPrimary,line width=.5pt"):
        out.append("\\draw[%s] %s .. controls %s and %s .. %s;" % (
            opts, point(*start), point(*c1), point(*c2), point(*end)))

    def polar(x, y, r, a):
        return x + r * math.cos(math.radians(a)), y + r * math.sin(math.radians(a))

    def star(x, y, r, opts="TLSecondary,line width=.6pt"):
        line([(x - r, y), (x + r, y)], opts)
        line([(x, y - r), (x, y + r)], opts)
        circle(x, y, .4, "draw=none,fill=TLSecondary")

    def field(count=32):
        rng = random.Random(motif)
        for _ in range(count):
            x, y = rng.uniform(3, 117), rng.uniform(3, 57)
            circle(x, y, rng.uniform(.13, .45), "draw=none,fill=TLPrimary,opacity=.55")
        for x, y in ((12, 47), (104, 41), (96, 10)):
            star(x, y, 1.4)

    def grid(step=10):
        for x in range(0, 121, step):
            line([(x, 0), (x, 60)], "TLPrimary,opacity=.16,line width=.25pt")
        for y in range(0, 61, step):
            line([(0, y), (120, y)], "TLPrimary,opacity=.16,line width=.25pt")

    def rings(x=60, y=30, radii=(12, 22, 28)):
        for r in radii:
            circle(x, y, r, "TLPrimary,opacity=.7,line width=.45pt")
        for a in range(0, 360, 30):
            line([polar(x, y, radii[-1] - 1, a), polar(x, y, radii[-1] + 1, a)],
                 "TLSecondary,line width=1pt")

    def temple():
        line([(26, 7), (26, 13), (33, 13), (33, 20), (40, 20), (40, 27),
              (47, 27), (47, 34), (54, 34), (54, 40), (66, 40), (66, 34),
              (73, 34), (73, 27), (80, 27), (80, 20), (87, 20), (87, 13),
              (94, 13), (94, 7)], "TLPrimary,fill=TLSurface,line width=1pt", True)
        for y in range(8, 39, 4):
            line([(57, y), (63, y)], "TLSecondary,line width=.65pt")

    if motif == "folio":
        for x in (8, 80):
            rect(x, 5, 32, 50, "TLPrimary,line width=.55pt")
            for y in (14, 19, 24, 29, 34, 39):
                line([(x + 5, y), (x + 25, y)], "TLRule,line width=.5pt")
        circle(60, 30, 14, "TLSecondary,line width=1pt")
        line([(52, 30), (60, 38), (68, 30), (60, 22)], close=True)
    elif motif == "swiss":
        rect(0, 3, 72, 15, "draw=none,fill=TLPrimary")
        rect(77, 3, 15, 54, "draw=none,fill=TLSecondary")
        circle(104, 44, 12, "draw=none,fill=TLPrimary")
        for y in (27, 37, 47, 57):
            line([(0, y), (68, y)], "TLRule,line width=.5pt")
    elif motif == "arches":
        for i in range(7):
            x = 6 + i * 16
            curve((x, 4), (x, 65), (x + 13, 65), (x + 13, 4),
                  "TLPrimary,line width=1pt,opacity=%.2f" % (.35 + i * .08))
        circle(84, 24, 12, "draw=none,fill=TLSecondary,opacity=.18")
    elif motif in ("candy", "balloons"):
        for i, (x, y) in enumerate(((16, 32), (39, 43), (65, 27), (91, 43), (109, 23))):
            color = "TLPrimary" if i % 2 else "TLSecondary"
            if motif == "candy":
                circle(x, y, 8, "draw=%s,fill=%s,fill opacity=.12,line width=.8pt" % (color, color))
                for r in (3, 5):
                    circle(x, y, r, color + ",opacity=.5")
                line([(x, y - 8), (x - 3, y - 23)], color)
            else:
                out.append("\\draw[%s,fill=%s,fill opacity=.12] %s ellipse[x radius=7mm,y radius=9mm];" % (color, color, point(x, y)))
                curve((x, y - 9), (x - 8, y - 17), (x + 6, 7), (x - 2, 2), color)
        star(54, 50, 2)
        star(80, 9, 2)
    elif motif == "clouds":
        for x, y, s in ((25, 18, 1.0), (70, 35, 1.3), (101, 14, .7)):
            for dx, dy, r in ((-9, 0, 7), (0, 5, 10), (11, 1, 8)):
                circle(x + dx * s, y + dy * s, r * s, "draw=none,fill=TLSurface")
            curve((x - 16 * s, y - 4), (x - 5, y - 7), (x + 8, y - 6), (x + 19 * s, y - 4), "TLPrimary,opacity=.6")
        for x, y in ((13, 46), (49, 16), (108, 47), (43, 50)):
            star(x, y, 1.8)
    elif motif == "garden":
        for i in range(9):
            x, h = 8 + 13 * i, 15 + (i * 11) % 30
            curve((x, 2), (x - 8, 13), (x + 6, h - 4), (x, h), "TLPrimary,line width=.7pt")
            for angle in range(0, 360, 60):
                px, py = polar(x, h, 4, angle)
                circle(px, py, 3, "draw=TLSecondary,fill=TLSurface,line width=.4pt")
            circle(x, h, 2, "draw=none,fill=TLPrimary")
    elif motif == "mobile":
        line([(18, 48), (100, 48)], "TLSecondary,line width=.8pt")
        for x, y in ((27, 23), (50, 32), (73, 17), (96, 29)):
            line([(x, 48), (x, y + 5)], "TLRule")
            star(x, y, 4)
        circle(12, 39, 8, "draw=none,fill=TLPrimary,opacity=.35")
        circle(15, 42, 7, "draw=none,fill=TLBackground")
    elif motif == "city":
        for i in range(14):
            x, h = 2 + i * 8.5, 8 + ((i * 17) % 33)
            rect(x, 1, 6.5, h, "TLPrimary,fill=TLSurface,line width=.6pt")
            for y in range(5, int(h), 6):
                line([(x + 2, y), (x + 4.5, y)], "TLSecondary,line width=1.2pt")
        line([(2, 51), (43, 51), (49, 57), (118, 57)], "TLSecondary,line width=1pt")
    elif motif == "neon":
        for i in range(7):
            x = 17 + i * 5
            rect(x, 4 + i * 2.5, 90 - i * 10, 51 - i * 5,
                 ("TLPrimary" if i % 2 else "TLSecondary") + ",rounded corners=3mm,line width=1pt")
    elif motif == "prism":
        for i in range(7):
            line([(15 + i * 4, 5), (60, 55 - i * 3), (105 - i * 4, 5)],
                 ("TLPrimary" if i % 2 else "TLSecondary") + ",line width=.7pt", True)
        line([(0, 32), (43, 32), (116, 47)], "TLSecondary,line width=1.1pt")
    elif motif == "horizon":
        circle(60, 34, 21, "draw=none,fill=TLSecondary,opacity=.24")
        for y in range(3, 35, 5):
            line([(0, y), (120, y)], "TLPrimary,opacity=.55")
        for x in range(-80, 201, 20):
            line([(60, 31), (x, 0)], "TLPrimary,opacity=.45")
        line([(0, 32), (120, 32)], "TLSecondary,line width=1pt")
    elif motif == "nebula":
        field()
        for i in range(17):
            curve((4, 10 + i * 1.5), (25, 70 - i * 2), (88, -10 + i * 2), (116, 42 + i * .8),
                  ("TLSecondary" if i % 3 else "TLPrimary") + ",opacity=.5,line width=.6pt")
    elif motif == "orbits":
        field(18)
        for angle in (-30, 0, 30):
            out.append("\\draw[TLPrimary,rotate around={%d:(60,30)}] (60,30) ellipse[x radius=43mm,y radius=13mm];" % angle)
        circle(60, 30, 5, "draw=TLSecondary,fill=TLSurface,line width=1pt")
        circle(94, 38, 2, "draw=none,fill=TLSecondary")
    elif motif == "eclipse":
        for x, r in ((14, 5), (36, 9), (64, 17), (95, 9), (115, 3)):
            circle(x, 30, r, "draw=TLPrimary,fill=TLSurface,line width=.7pt")
        circle(70, 34, 16, "draw=none,fill=TLBackground")
        line([(2, 7), (118, 7)], "TLRule")
    elif motif in ("solar", "supernova"):
        field(16)
        rings(radii=(11, 14, 18))
        for a in range(0, 360, 10 if motif == "solar" else 8):
            r = 23 + 6 * math.sin(math.radians(a * 7))
            line([polar(60, 30, 20, a), polar(60, 30, r, a)],
                 "TLSecondary,line width=.8pt")
        if motif == "supernova":
            for dx in (-37, 37):
                curve((60, 10), (60 + dx, 12), (60 + dx, 47), (60, 51), "TLPrimary,line width=1.3pt")
    elif motif == "aurora":
        field(25)
        for i in range(23):
            curve((0, 8 + i), (30, 58 + i * .5), (58, -2 + i), (120, 38 + i * .8),
                  ("TLPrimary" if i % 3 else "TLSecondary") + ",opacity=.45,line width=.6pt")
    elif motif == "telescope":
        field(40)
        line([(24, 16), (44, 44), (69, 36), (92, 49), (105, 18), (77, 9), (44, 44)], "TLPrimary,opacity=.7")
        for x, y in ((24, 16), (44, 44), (69, 36), (92, 49), (105, 18), (77, 9)):
            circle(x, y, 1.4, "draw=none,fill=TLSecondary")
        rings(69, 36, (5, 8))
    elif motif == "circuit":
        for i in range(7):
            y = 5 + i * 8
            line([(3, y), (24 + i * 3, y), (36 + i * 3, 30), (70 + i * 2, 30), (85 + i * 2, y), (117, y)],
                 "TLPrimary,line width=.8pt")
            circle(3, y, 1.5, "TLSecondary,line width=.7pt")
            circle(117, y, 1.5, "TLSecondary,line width=.7pt")
        rect(47, 21, 25, 18, "TLSecondary,fill=TLBackground,line width=1pt")
    elif motif == "blueprint":
        grid(5)
        rect(22, 14, 76, 32, "TLPrimary,line width=.9pt")
        circle(43, 30, 10)
        rect(67, 22, 19, 16)
        line([(22, 9), (22, 4), (98, 4), (98, 9)], "TLSecondary,arrows=|-|")
        line([(43, 8), (43, 52)], "TLPrimary,dashed")
    elif motif == "chip":
        rect(43, 13, 34, 34, "TLPrimary,fill=TLSurface,line width=1pt")
        rect(48, 18, 24, 24, "TLSecondary,line width=.7pt")
        for i in range(8):
            q = 16 + i * 4
            line([(36, q), (43, q)], "TLPrimary,line width=1pt")
            line([(77, q), (84, q)], "TLPrimary,line width=1pt")
            line([(46 + i * 4, 6), (46 + i * 4, 13)], "TLPrimary,line width=1pt")
            line([(46 + i * 4, 47), (46 + i * 4, 54)], "TLPrimary,line width=1pt")
        line([(52, 24), (60, 36), (68, 24)], "TLSecondary", True)
    elif motif == "signal":
        grid(5)
        for phase, color in ((0, "TLPrimary"), (1.4, "TLSecondary")):
            line([(x, 30 + 16 * math.sin(x * .13 + phase)) for x in range(121)], color + ",line width=1pt")
        line([(60, 0), (60, 60)], "TLSecondary,dashed,opacity=.5")
    elif motif in ("temple", "celestial"):
        if motif == "celestial":
            field(25)
            rings(60, 31, (24, 28))
        else:
            circle(60, 40, 15, "TLSecondary,opacity=.5")
        temple()
        for x in (6, 102):
            line([(x, 15), (x, 42), (x + 12, 42), (x + 12, 34), (x + 5, 34), (x + 5, 23)], "TLSecondary,line width=1.2pt")
    elif motif == "feathers":
        for i in range(9):
            a = 24 + i * 16.5
            end = polar(60, 5, 49, a)
            curve((60, 5), (end[0] - 17, end[1] - 4), (end[0] + 8, end[1] + 6), end,
                  ("TLSecondary" if i % 2 else "TLPrimary") + ",line width=1pt")
            circle(*end, 2.2, "TLPrimary,fill=TLSurface")
        circle(60, 6, 4, "draw=none,fill=TLPrimary")
    elif motif == "glyphs":
        for row in range(3):
            for col in range(8):
                x, y = 4 + col * 15, 4 + row * 19
                rot = (row + col) % 3
                line([(x, y), (x, y + 13), (x + 10, y + 13), (x + 10, y + 7), (x + 4, y + 7), (x + 4, y + 3 + rot)],
                     ("TLPrimary" if rot else "TLSecondary") + ",line width=1pt")
                circle(x + 9, y + 1, .8, "draw=none,fill=TLSecondary")
    elif motif == "biolume":
        field(18)
        for x, h in ((13, 24), (35, 43), (61, 51), (87, 38), (109, 20)):
            curve((x, 0), (x - 13, 16), (x + 10, 22), (x, h), "TLPrimary,line width=.8pt")
            for r in (3, 6, 9):
                circle(x, h, r, "TLSecondary,opacity=%.2f,line width=.6pt" % (1 - r / 12))
            circle(x, h, 1.2, "draw=none,fill=TLPrimary")
    elif motif == "calendar":
        rings(radii=(9, 17, 25, 28))
        for a in range(0, 360, 15):
            line([polar(60, 30, 19, a), polar(60, 30, 23, a), polar(60, 30, 23, a + 9)], "TLSecondary,line width=1pt")
        line([(54, 24), (54, 36), (66, 36), (66, 24)], "TLPrimary,line width=1pt", True)
        for x in (9, 103):
            rect(x, 23, 8, 14, "TLPrimary,line width=.8pt")
    elif motif == "portal":
        field(24)
        for r in range(9, 30, 4):
            line([polar(60, 30, r, a) for a in range(0, 360, 45)],
                 "TLPrimary,line width=.7pt", True)
        for a in range(0, 360, 45):
            line([polar(60, 30, 12, a), polar(60, 30, 28, a)], "TLSecondary,line width=.7pt")
    else:
        raise ValueError("Unknown artwork motif: %s" % motif)

    if decoration == "restrained":
        # A smaller, still distinct motif within the same normal-flow region.
        out.insert(3, r"\begin{scope}[shift={(24,12)},scale=.6]")
        out.append(r"\end{scope}")
    out.append(r"\end{tikzpicture}")
    return "\n".join(out)
