# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Selectable visual identities, independent of the document's semantic nuance.

All artwork is vector geometry. No network, downloaded fonts, model calls, or
additional dependencies are needed. Aztec-inspired geometry is original art,
not a transcription of historical glyphs or a claim of archaeological meaning.
"""
from __future__ import annotations

import re
import unicodedata

import pdfer_color as pc


def _style(label, family, colors, motif, pairing, aliases=(), *, base=10.5,
           ratio=1.28, leading=1.5, airy=1.05, centered=False):
    background, primary, secondary, accent = colors
    return dict(label=label, family=family, background=background,
                primary=primary, secondary=secondary, accent=accent,
                motif=motif, pairing=pairing, aliases=aliases,
                scale=dict(base=base, ratio=ratio, leading=leading),
                airy=airy, centered=centered)


STYLES = {
    "kawaii_cloud": _style("Kawaii Cloud", "playful", ("#FFF7FC", "#A33170", "#8765C5", "#E7A94C"), "clouds", "friendly", ("cute", "kawaii", "cute clouds", "tierno"), centered=True),
    "baby_dream": _style("Baby Dream", "playful", ("#F4F8FF", "#45649A", "#B386B6", "#D9B35C"), "dream", "friendly", ("baby", "bebe", "baby blue", "nursery"), leading=1.6, centered=True),
    "baby_peach": _style("Baby Peach", "playful", ("#FFF5EE", "#A65C46", "#7B9272", "#D29971"), "clouds", "friendly", ("peach", "baby pink"), leading=1.6, centered=True),
    "candy_pop": _style("Candy Pop", "playful", ("#FFF7E6", "#B12969", "#6455B5", "#00A59B"), "confetti", "promotional", ("candy", "pop", "birthday"), ratio=1.33),
    "storybook_garden": _style("Storybook Garden", "playful", ("#F7F7EA", "#43643C", "#A5596B", "#C79942"), "petals", "literary", ("storybook", "garden", "fairytale"), leading=1.6, airy=1.12),
    "pastel_sorbet": _style("Pastel Sorbet", "playful", ("#FBF5FF", "#805298", "#488A86", "#DA937D"), "ribbons", "friendly", ("pastel", "sorbet"), centered=True),
    "cyberpunk": _style("Cyberpunk Afterglow", "cyberpunk", ("#090E1B", "#56F1EF", "#FF5FB7", "#EFF75C"), "city", "technical", ("cyber punk", "cyber"), ratio=1.33),
    "neon_noir": _style("Neon Noir", "cyberpunk", ("#130C1E", "#FF75CA", "#B599FF", "#75E1ED"), "city", "promotional", ("neon", "noir"), ratio=1.33),
    "holographic": _style("Holographic Prism", "cyberpunk", ("#EFFBFB", "#37679B", "#9A469C", "#20836B"), "prism", "technical", ("hologram", "holographic prism", "iridescent")),
    "synthwave": _style("Synthwave Sunset", "cyberpunk", ("#170C2D", "#F58ABF", "#ABAAFF", "#FAD878"), "horizon", "promotional", ("retrowave", "vaporwave", "synth"), ratio=1.33, centered=True),
    "cosmic_nebula": _style("Cosmic Nebula", "cosmic", ("#080D26", "#AABFFF", "#E2A5EC", "#69DDE7"), "nebula", "technical", ("space", "cosmic", "nebula", "galaxy", "astronomical"), ratio=1.3),
    "astral_atlas": _style("Astral Atlas", "cosmic", ("#111B2C", "#DFC98D", "#94BCED", "#B7D5CE"), "orbits", "scholarly", ("astronomy", "astral", "star chart", "constellation")),
    "lunar_minimal": _style("Lunar Silence", "cosmic", ("#F5F5F0", "#444D64", "#7485A7", "#AB8663"), "eclipse", "neutral", ("moon", "lunar", "lunar silence"), airy=1.15),
    "solar_flare": _style("Solar Flare", "cosmic", ("#1F1016", "#FFBD83", "#F88EAE", "#FFE2A7"), "solar", "promotional", ("solar", "sun", "supernova"), ratio=1.33),
    "aurora": _style("Aurora Borealis", "cosmic", ("#071D29", "#8EF1CE", "#AEACF5", "#A9DEEE"), "aurora", "neutral", ("northern lights", "aurora borealis")),
    "circuit_board": _style("Circuit Board", "electronics", ("#07201D", "#95E8BC", "#E5C57E", "#73C5EC"), "circuit", "technical_mono", ("electronics", "pcb", "circuit", "electronica"), base=10.2),
    "blueprint": _style("Blueprint Studio", "electronics", ("#102B53", "#DAEEFF", "#81C9EB", "#F0D495"), "blueprint", "technical", ("blue print", "schematic"), base=10.2, ratio=1.25),
    "quantum_chip": _style("Quantum Chip", "electronics", ("#141322", "#B9B4FF", "#7CDDE8", "#E7B583"), "chip", "technical", ("quantum", "chip", "silicon"), ratio=1.3),
    "oscilloscope": _style("Oscilloscope", "electronics", ("#091B13", "#AAECA6", "#87DACC", "#F2D17D"), "signal", "technical_mono", ("waveform", "signal", "scope"), ratio=1.25),
    "aztec_obsidian": _style("Aztec Obsidian", "tlamatini", ("#181515", "#E0BB70", "#73C3B7", "#DF8F71"), "temple", "promotional", ("aztec", "azteca", "obsidian"), ratio=1.3),
    "quetzal_jade": _style("Quetzal Jade", "tlamatini", ("#F4F2E5", "#216457", "#8A5439", "#B68A31"), "feathers", "editorial", ("quetzal", "jade"), airy=1.1),
    "tlamatini_celestial": _style("Tlamatini Celestial", "tlamatini", ("#071925", "#71E0D2", "#E9C77D", "#BAA5F4"), "celestial", "technical", ("tlamatini", "extraterrestrial aztec", "aztec beyond this planet"), ratio=1.33),
    "xeno_codex": _style("Xeno Codex", "tlamatini", ("#161226", "#D5BEFA", "#8DE5D9", "#EEC78F"), "portal", "technical_mono", ("alien", "extraterrestrial", "xeno", "alien codex"), ratio=1.28),
    "alien_biolume": _style("Alien Bioluminescence", "tlamatini", ("#061E23", "#83EDBD", "#88D9F2", "#DABCFF"), "biolume", "neutral", ("bioluminescent", "biolume", "alien bioluminescence"), leading=1.55),
}


def _key(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


_ALIASES = {_key(alias): name for name, spec in STYLES.items()
            for alias in (name, spec["label"], *spec["aliases"])}


def normalise_style(value):
    """Exact normalized aliases only: prose content never triggers a style."""
    return _ALIASES.get(_key(value), "")


def style_catalog():
    """Serializable catalogue for tools, galleries and future selectors."""
    return [dict(id=name, label=spec["label"], family=spec["family"],
                 aliases=list(spec["aliases"]), motif=spec["motif"],
                 dark=pc.parse_color(spec["background"]).is_dark)
            for name, spec in STYLES.items()]


def theme_for(name):
    """Expand a curated identity to every palette role before validation."""
    spec = STYLES[name]
    bg, primary, secondary, accent = (
        pc.parse_color(spec[k]) for k in ("background", "primary", "secondary", "accent"))
    dark = bg.is_dark
    ink = pc.parse_color("#EDF3FA" if dark else "#28313C")
    surface = pc.mix(bg, primary, 0.08 if dark else 0.055)
    border = pc.mix(bg, primary, 0.28)
    palette = pc.palette_from_seed(primary.hex, dark=dark, name=name).copy_with(
        background=bg, background_alt=surface, surface=surface,
        surface_alt=pc.mix(bg, primary, 0.13), text=ink,
        text_muted=pc.mix(ink, bg, 0.20), primary=primary,
        primary_soft=surface, secondary=secondary, accent=accent,
        border=border, border_soft=pc.mix(bg, primary, 0.16), rule=primary,
        heading_1=primary, heading_2=primary, heading_3=secondary,
        heading_4=ink, link=primary, caption=pc.mix(ink, bg, 0.20),
        footer=pc.mix(ink, bg, 0.25), code_bg=surface, code_fg=ink,
        code_border=border, table_header_bg=pc.mix(bg, primary, 0.16),
        table_header_fg=ink, table_row_alt=surface, table_border=border,
        quote_bar=secondary, quote_bg=surface, quote_fg=ink,
        cover_from=bg, cover_to=pc.mix(bg, secondary, 0.30), ornament=accent)
    return dict(label=spec["label"], dark=dark, pairing=spec["pairing"],
                scale=dict(spec["scale"]), palette={r: palette.get(r).hex for r in pc.Palette.ROLES},
                ornament="signature", justify=False, airy=spec["airy"],
                motif=spec["motif"], centered=spec["centered"], family=spec["family"],
                note="%s collection; original vector %s artwork." % (spec["family"], spec["motif"]))
