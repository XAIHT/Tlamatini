# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""LaTeXer's portable design catalogue. Standard library only; no agent.* imports.

Styles are independent of document structure and never inferred from body text.
All emitted text colors are checked against their actual background AFTER the
optional seed and print conversion. Artwork colors need not be text colors.
"""
import re
import unicodedata


def _style(label, family, background, primary, secondary, motif, aliases=(),
           body="sans", heading="sans", leading=1.12):
    return dict(label=label, family=family, background=background, primary=primary,
                secondary=secondary, motif=motif, aliases=aliases,
                body=body, heading=heading, leading=leading)


STYLES = {
    "scholarly": _style("Scholarly Ivory", "editorial", "FBF8F0", "35475C", "916839", "folio", ("academic", "paper"), body="serif", heading="serif"),
    "swiss": _style("Swiss Precision", "editorial", "FAFAF7", "B92C36", "243B53", "swiss", ("minimal", "swiss precision")),
    "atelier": _style("Atelier Editorial", "editorial", "F5EEE6", "69453A", "486A63", "arches", ("editorial", "elegant"), body="serif", heading="serif", leading=1.16),
    "cute_candy": _style("Cute Candy", "playful", "FFF6FB", "AB397C", "557DC5", "candy", ("cute", "kawaii", "candy"), leading=1.18),
    "baby_blush": _style("Baby Blush", "playful", "FFF5F0", "AF5670", "788D71", "clouds", ("baby", "baby pink", "nursery"), leading=1.22),
    "baby_sky": _style("Baby Sky", "playful", "F0F9FF", "437C9E", "A7789E", "balloons", ("baby blue", "sky"), leading=1.22),
    "storybook": _style("Storybook Garden", "playful", "F7F7E9", "49744C", "B36B48", "garden", ("fairytale", "storybook garden"), body="serif", leading=1.18),
    "lullaby": _style("Lullaby Moon", "playful", "F7F3FF", "79609D", "9C7650", "mobile", ("lullaby moon", "sweet dreams"), leading=1.22),
    "cyberpunk": _style("Cyberpunk Voltage", "cyberpunk", "09121F", "61E9EF", "FF81B7", "city", ("cyber", "cyber punk"), heading="mono"),
    "neon_noir": _style("Neon Noir", "cyberpunk", "180F23", "F99CD6", "96BFFF", "neon", ("noir", "neon")),
    "holographic": _style("Holographic Prism", "cyberpunk", "F0F9FA", "426F98", "8A4F9D", "prism", ("hologram", "iridescent")),
    "synthwave": _style("Synthwave Horizon", "cyberpunk", "1B1030", "FFAACB", "C6B2FF", "horizon", ("retrowave", "vaporwave")),
    "cosmic_nebula": _style("Cosmic Nebula", "cosmic", "0C122C", "B6C4FF", "F3B0E1", "nebula", ("cosmic", "space", "nebula", "galaxy", "astronomical")),
    "astral_atlas": _style("Astral Atlas", "cosmic", "111E30", "E5CC94", "A3C8EE", "orbits", ("astronomy", "constellation", "star chart"), body="serif"),
    "lunar_minimal": _style("Lunar Silence", "cosmic", "F5F5F0", "505D76", "927354", "eclipse", ("moon", "lunar", "lunar silence")),
    "solar_flare": _style("Solar Flare", "cosmic", "24101B", "FFC48F", "FFA0BE", "solar", ("sun", "solar")),
    "aurora": _style("Aurora Borealis", "cosmic", "091E2B", "9AE8D5", "C1B8FF", "aurora", ("northern lights",)),
    "deep_space": _style("Deep Space Observatory", "cosmic", "0B1522", "A1CFFF", "B3E4DB", "telescope", ("observatory", "deep space"), heading="mono"),
    "circuit_board": _style("Circuit Board", "electronics", "0A211D", "A7E9C0", "E8C88E", "circuit", ("electronics", "electronica", "pcb", "circuit"), heading="mono"),
    "blueprint": _style("Blueprint Studio", "electronics", "102D53", "DFEEFF", "9BCEE9", "blueprint", ("schematic", "blue print"), heading="mono"),
    "quantum_chip": _style("Quantum Chip", "electronics", "191629", "C8BEFF", "90E0E9", "chip", ("quantum", "silicon", "chip"), heading="mono"),
    "oscilloscope": _style("Oscilloscope", "electronics", "0C2018", "B2EDAC", "93DECF", "signal", ("waveform", "signal", "scope"), heading="mono"),
    "aztec_obsidian": _style("Aztec Obsidian", "tlamatini", "1C1819", "E6C482", "8CD1C3", "temple", ("aztec", "azteca", "obsidian"), heading="serif"),
    "quetzal_jade": _style("Quetzal Jade", "tlamatini", "F4F2E5", "286A59", "8E593A", "feathers", ("quetzal", "jade"), body="serif"),
    "tlamatini_celestial": _style("Tlamatini Celestial", "tlamatini", "091D29", "88E6DA", "EDD08D", "celestial", ("tlamatini", "extraterrestrial aztec", "aztec beyond this planet")),
    "xeno_codex": _style("Xeno Codex", "tlamatini", "1B152D", "DAC5FF", "A0EADF", "glyphs", ("alien", "extraterrestrial", "xeno"), heading="mono"),
    "alien_biolume": _style("Alien Bioluminescence", "tlamatini", "082129", "92ECCB", "AACCF4", "biolume", ("biolume", "bioluminescent")),
    "solar_codex": _style("Solar Codex", "tlamatini", "F9EFDB", "965020", "386C69", "calendar", ("sun stone", "solar codex"), body="serif", heading="serif"),
    "obsidian_portal": _style("Obsidian Portal", "tlamatini", "111324", "BCBBFA", "8CE4DC", "portal", ("stargate", "portal")),
    "quetzal_supernova": _style("Quetzal Supernova", "tlamatini", "1C1229", "F7B7D8", "9DE4D5", "supernova", ("supernova", "cosmic quetzal")),
}


def _key(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return re.sub(r"[^a-z0-9]+", "_", "".join(
        char for char in text if not unicodedata.combining(char))).strip("_")


_ALIASES = {_key(alias): key for key, spec in STYLES.items()
            for alias in (key, spec["label"], *spec["aliases"])}


def normalise_style(value):
    """An omitted style preserves the legacy renderer; unknown names are errors."""
    key = _key(value)
    if key in ("", "none", "default", "plain"):
        return ""
    if key not in _ALIASES:
        raise ValueError("Unknown LaTeXer style %r. Use action='list_styles' for the catalogue." % value)
    return _ALIASES[key]


def _rgb(value):
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def luminance(value):
    rgb = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
           for c in _rgb(value)]
    return sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722)))


def contrast(foreground, background):
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def mix(a, b, weight):
    return "".join("%02X" % round(255 * (x * (1 - weight) + y * weight))
                   for x, y in zip(_rgb(a), _rgb(b)))


def readable(color, background, floor=4.5):
    if contrast(color, background) >= floor:
        return color
    target = max(("000000", "FFFFFF"), key=lambda c: contrast(c, background))
    for step in range(1, 101):
        candidate = mix(color, target, step / 100)
        if contrast(candidate, background) >= floor:
            return candidate
    return target


def _bool(value, default=True):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    key = str(value).strip().lower()
    if key in ("true", "yes", "1", "on"):
        return True
    if key in ("false", "no", "0", "off"):
        return False
    raise ValueError("style_cover must be true or false")


def build_theme(config):
    key = normalise_style(config.get("style"))
    if not key:
        return None
    spec = dict(STYLES[key])
    mode = str(config.get("style_mode") or "screen").strip().lower()
    decoration = str(config.get("style_decoration") or "rich").strip().lower()
    if mode not in ("screen", "print"):
        raise ValueError("style_mode must be screen or print")
    if decoration not in ("none", "restrained", "rich"):
        raise ValueError("style_decoration must be none, restrained or rich")
    seed = str(config.get("predominant_color") or "").strip().lstrip("#")
    if seed and not re.fullmatch(r"[0-9a-fA-F]{6}", seed):
        raise ValueError("predominant_color must be a six-digit hex color, e.g. #238D87")
    background = "FFFFFF" if mode == "print" else spec["background"]
    ink = "EDF2F7" if luminance(background) < .18 else "29323B"
    primary = readable(seed.upper() or spec["primary"], background)
    secondary = readable(spec["secondary"], background)
    surface = mix(background, primary, .09)
    palette = dict(Background=background, Ink=readable(ink, background),
                   Primary=primary, Secondary=secondary, Surface=surface,
                   Muted=readable(mix(ink, background, .22), background),
                   SurfaceInk=readable(ink, surface),
                   SurfaceAccent=readable(primary, surface),
                   OnPrimary=readable(ink, primary), Rule=mix(background, primary, .35))
    spec.update(id=key, mode=mode, decoration=decoration, palette=palette,
                cover=_bool(config.get("style_cover")))
    return spec


def style_catalog():
    return [dict(id=key, label=spec["label"], family=spec["family"],
                 motif=spec["motif"], aliases=list(spec["aliases"]),
                 dark=luminance(spec["background"]) < .18,
                 body=spec["body"], heading=spec["heading"],
                 modes=["screen", "print"], engines=["pdflatex", "xelatex", "lualatex"])
            for key, spec in STYLES.items()]
