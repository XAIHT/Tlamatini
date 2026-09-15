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
# pptxer_nuance.py — WHAT KIND OF DECK IS THIS?
#
# Sibling module of pptxer.py (flat neighbour, NOT a package). Stdlib only.
# Imports nothing from agent.* and nothing from the other pptxer_* modules.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE JOB
# ─────────────────────────────────────────────────────────────────────────────
# Read the CONTENT before rendering anything and decide which deck
# treatments it really is — an esports tournament recap is not a Series-A
# pitch, and neither is a safety briefing. The treatment then drives the
# palette, the type pairing, the layout rhythm, the artwork programme and the
# decoration ceiling.
#
# An EXPLICIT `nuance` from the user always WINS. This module only answers when
# nobody said.
#
# ─────────────────────────────────────────────────────────────────────────────
# CONTRACTS LEARNED FROM PDFer's CLASSIFIER (2026-09-06) — do NOT weaken
# ─────────────────────────────────────────────────────────────────────────────
#  1. STRUCTURE OUTWEIGHS VOCABULARY (~3x). Anyone can say "revenue"; only a
#     financial deck actually carries a currency table. Structure is expensive
#     to fake and therefore trustworthy.
#
#  2. AN AMBIGUOUS SIGNAL NEEDS CORROBORATION. PDFer's bug: SI units scored
#     "scientific" equally well for a physics paper and a parts list. Here the
#     equivalent trap is that "level", "player" and "build" are as common in a
#     software release deck as in a game design document. So a structural
#     signal whose domain has NO independent lexical support is DAMPED.
#
#  3. LOG-DAMP THE LEXICON. A word repeated 40 times must not outweigh four
#     different words appearing once each. Breadth of vocabulary identifies a
#     domain; repetition identifies an obsession.
#
#  4. AN UNCERTAIN CLASSIFIER MUST *ACT* UNCERTAIN. Low confidence lowers the
#     decoration ceiling, because a confidently-wrong treatment looks
#     deliberate while a hedged one merely looks plain.
#
#  5. NEVER LET DECORATION REACH A DECK WHERE IT IS DANGEROUS OR DISHONEST.
#     A safety briefing, a medical protocol, a legal/compliance deck and a
#     financial disclosure get NO generated ornament, at any confidence.

import math
import re

__all__ = [
    "NUANCES",
    "NUANCE_ALIASES",
    "STYLE_PRESETS",
    "classify",
    "resolve_nuance",
    "NuanceVerdict",
    "SAFETY_CRITICAL_NUANCES",
]

# ─────────────────────────────────────────────────────────────────────────────
# Content treatments and explicitly selected visual styles.
#
# `register` is the emotional pitch, `decoration_ceiling` is the MAXIMUM
# artwork level the content can safely carry, and `pairing`/`palette_seed`/
# `scheme` seed the theme. `density` says how much text a slide may hold.
# ─────────────────────────────────────────────────────────────────────────────

NUANCES = {
    # ═══ GAMING ═════════════════════════════════════════════════════════════
    "esports_tournament": {
        "label": "Esports tournament",
        "register": "loud, competitive, scoreboard-driven",
        "pairing": "esports", "palette_seed": "#12E2A3", "scheme": "neon",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "low", "ornament": "hex_grid",
        "note": "Team colours, bracket geometry, big numbers, motion streaks.",
    },
    "game_design_doc": {
        "label": "Game design document",
        "register": "technical but playful; systems and loops",
        "pairing": "esports", "palette_seed": "#7B2FF7", "scheme": "triad",
        "background_mode": "dark", "decoration_ceiling": "moderate",
        "density": "medium", "ornament": "circuitry",
        "note": "Mechanics diagrams, state loops, progression curves.",
    },
    "game_trailer_beat": {
        "label": "Game reveal / trailer beat sheet",
        "register": "cinematic, high-drama, image-first",
        "pairing": "cyberpunk", "palette_seed": "#FF10F0", "scheme": "complementary",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "minimal", "ornament": "glitch_scan",
        "note": "Full-bleed key art, one line of type, heavy vignette.",
    },
    "cyberpunk_tech": {
        "label": "Cyberpunk / near-future tech",
        "register": "neon, glitched, terminal",
        "pairing": "cyberpunk", "palette_seed": "#00F0FF", "scheme": "neon",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "low", "ornament": "glitch_scan",
        "note": "Scanlines, chromatic aberration, mono captions.",
    },
    "fantasy_lore": {
        "label": "Fantasy / RPG lore",
        "register": "mythic, warm, hand-made",
        "pairing": "fantasy_rpg", "palette_seed": "#B7410E", "scheme": "analogous",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "medium", "ornament": "runic_border",
        "note": "Parchment textures, carved titling, gold leaf accents.",
    },
    "retro_arcade": {
        "label": "Retro / arcade",
        "register": "8-bit joy, chunky, saturated",
        "pairing": "arcade", "palette_seed": "#FF2E63", "scheme": "triad",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "low", "ornament": "pixel_grid",
        "note": "Hard pixel edges, CRT curvature, primary colours.",
    },
    "military_tactical": {
        "label": "Military / tactical shooter",
        "register": "austere, briefing-room, stencilled",
        "pairing": "military_tactical", "palette_seed": "#6B8E23", "scheme": "monochrome",
        "background_mode": "dark", "decoration_ceiling": "moderate",
        "density": "medium", "ornament": "tactical_grid",
        "note": "Map grids, stencil type, desaturated olive and sand.",
    },
    "streamer_kit": {
        "label": "Streamer / creator kit",
        "register": "personable, brand-forward, energetic",
        "pairing": "brand_bold", "palette_seed": "#9146FF", "scheme": "split",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "low", "ornament": "particle_burst",
        "note": "Channel colours, overlay frames, big social proof numbers.",
    },

    # ═══ MARKETING ══════════════════════════════════════════════════════════
    "product_launch": {
        "label": "Product launch",
        "register": "confident, benefit-led, hero-image",
        "pairing": "brand_bold", "palette_seed": "#FF4757", "scheme": "complementary",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "low", "ornament": "gradient_mesh",
        "note": "One promise per slide, product photography, strong CTA.",
    },
    "brand_story": {
        "label": "Brand story / manifesto",
        "register": "emotive, spacious, cinematic",
        "pairing": "brand_bold", "palette_seed": "#F72585", "scheme": "analogous",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "minimal", "ornament": "gradient_mesh",
        "note": "Full-bleed imagery, very large type, generous silence.",
    },
    "campaign_report": {
        "label": "Campaign performance report",
        "register": "data-forward but persuasive",
        "pairing": "startup_pitch", "palette_seed": "#3FA9F5", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "high", "ornament": "corporate_band",
        "note": "KPI tiles, trend charts, channel comparison tables.",
    },
    "startup_pitch": {
        "label": "Startup / investor pitch",
        "register": "crisp, momentum-driven, numbers that land",
        "pairing": "startup_pitch", "palette_seed": "#5B5BD6", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "medium", "ornament": "corporate_band",
        "note": "Problem-solution-market-traction-ask. One idea per slide.",
    },
    "sales_enablement": {
        "label": "Sales enablement",
        "register": "practical, objection-handling, comparative",
        "pairing": "corporate", "palette_seed": "#0F8B5B", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "high", "ornament": "corporate_band",
        "note": "Battlecards, comparison matrices, pricing tiers.",
    },
    "luxury_brand": {
        "label": "Luxury / premium brand",
        "register": "restrained, expensive, high-contrast",
        "pairing": "luxury", "palette_seed": "#C8A96A", "scheme": "monochrome",
        "background_mode": "dark", "decoration_ceiling": "moderate",
        "density": "minimal", "ornament": "thin_rule",
        "note": "Enormous margins, hairline rules, gold on near-black.",
    },
    "social_media_kit": {
        "label": "Social / content kit",
        "register": "punchy, scroll-stopping, modular",
        "pairing": "friendly_consumer", "palette_seed": "#FF6AD5", "scheme": "triad",
        "background_mode": "light", "decoration_ceiling": "rich",
        "density": "minimal", "ornament": "blob_shapes",
        "note": "Square-safe compositions, quote cards, bold blocks.",
    },
    "event_keynote": {
        "label": "Event keynote",
        "register": "stage-scale, theatrical, one-thought-per-slide",
        "pairing": "brand_bold", "palette_seed": "#8F00FF", "scheme": "split",
        "background_mode": "dark", "decoration_ceiling": "rich",
        "density": "minimal", "ornament": "spotlight",
        "note": "Designed to be read from the back row. Very large type.",
    },

    # ═══ CORPORATE / TECHNICAL ══════════════════════════════════════════════
    "corporate_update": {
        "label": "Corporate / business update",
        "register": "neutral, orderly, unshowy",
        "pairing": "corporate", "palette_seed": "#2F5D8C", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "high", "ornament": "corporate_band",
        "note": "The boardroom default. Clear hierarchy, no theatrics.",
    },
    "technical_architecture": {
        "label": "Technical architecture",
        "register": "precise, diagram-led, mono captions",
        "pairing": "technical", "palette_seed": "#1F8A8A", "scheme": "analogous",
        "background_mode": "dark", "decoration_ceiling": "restrained",
        "density": "medium", "ornament": "circuitry",
        "note": "Boxes and arrows must be readable before they are pretty.",
    },
    "research_findings": {
        "label": "Research / scientific findings",
        "register": "sober, evidence-first, chart-heavy",
        "pairing": "scientific", "palette_seed": "#3B5BA5", "scheme": "monochrome",
        "background_mode": "light", "decoration_ceiling": "none",
        "density": "high", "ornament": "none",
        "note": "Figures carry the argument; decoration would undermine it.",
    },
    "training_course": {
        "label": "Training / course material",
        "register": "patient, structured, example-led",
        "pairing": "friendly_consumer", "palette_seed": "#2E8B57", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "high", "ornament": "soft_shapes",
        "note": "Objectives, worked examples, check-your-understanding.",
    },
    "project_status": {
        "label": "Project status / roadmap",
        "register": "factual, timeline-driven",
        "pairing": "corporate", "palette_seed": "#4A6FA5", "scheme": "analogous",
        "background_mode": "light", "decoration_ceiling": "restrained",
        "density": "high", "ornament": "corporate_band",
        "note": "Gantt-ish timelines, RAG status, owners and dates.",
    },

    # ═══ SAFETY-CRITICAL (never decorated) ══════════════════════════════════
    "financial_disclosure": {
        "label": "Financial disclosure",
        "register": "exact, auditable, unembellished",
        "pairing": "corporate", "palette_seed": "#1F3A5F", "scheme": "monochrome",
        "background_mode": "light", "decoration_ceiling": "none",
        "density": "high", "ornament": "none",
        "note": "A decorated financial statement looks manipulated.",
    },
    "legal_compliance": {
        "label": "Legal / compliance",
        "register": "formal, numbered, unambiguous",
        "pairing": "corporate", "palette_seed": "#3A3A44", "scheme": "monochrome",
        "background_mode": "light", "decoration_ceiling": "none",
        "density": "high", "ornament": "none",
        "note": "A decorated contract slide looks forged.",
    },
    "safety_briefing": {
        "label": "Safety / medical briefing",
        "register": "unmissable, hazard-coded, plain",
        "pairing": "technical", "palette_seed": "#D62828", "scheme": "monochrome",
        "background_mode": "light", "decoration_ceiling": "none",
        "density": "medium", "ornament": "none",
        "note": "Ornament near a dosage or a hazard step is dangerous.",
    },
}

def _visual_style(label, pairing, seed, ground, *, dark=False, ornament="none",
                  radius=0, rule=1, density="medium", uppercase=False,
                  margin=2.6, panel_pad=0.95, colors=None, note=""):
    """Style defaults use the same measured, validated theme pipeline."""
    return {
        "label": label, "register": note, "pairing": pairing,
        "palette_seed": seed, "scheme": "curated",
        "background_mode": "dark" if dark else "light",
        "background_color": ground, "palette_roles": colors or {},
        "decoration_ceiling": "restrained", "density": density,
        "ornament": ornament, "note": note,
        "shape_defaults": {"radius": radius, "rule": rule,
                           "uppercase_titles": uppercase},
        "spacing_factors": {"margin": margin, "panel_pad": panel_pad},
        "visual_style": True,
    }


# These are opt-in visual directions, not guesses about a document's subject.
# Keeping them out of the lexical classifier preserves existing auto-detection.
STYLE_PRESETS = {
    "swiss_editorial": _visual_style(
        "Swiss Editorial", "swiss", "#B52B32", "#FAFAF7", rule=3,
        uppercase=True, density="high", margin=2.8,
        colors={"title": "#181B1E", "heading": "#181B1E"},
        note="Crisp sans serif, red rules, square cards, and a strict white grid."),
    "warm_editorial": _visual_style(
        "Warm Editorial", "editorial", "#844C36", "#FBF5E9", rule=0.75,
        margin=2.9, panel_pad=1.1,
        colors={"title": "#3D3028", "heading": "#3D3028"},
        note="Magazine serifs, warm paper, fine rules, and generous margins."),
    "midnight_luxe": _visual_style(
        "Midnight Luxe", "luxury", "#D6B875", "#111A2B", dark=True,
        rule=0.75, margin=3.0, panel_pad=1.1,
        note="Gold didone headings over midnight blue with quiet hairline details."),
    "botanical": _visual_style(
        "Botanical", "editorial", "#356548", "#F1F5EC", radius=18,
        ornament="soft_shapes", panel_pad=1.05,
        note="Leaf green, soft sage panels, rounded cards, and organic serif type."),
    "oceanic": _visual_style(
        "Oceanic", "technical", "#61DAE5", "#092B3B", dark=True,
        ornament="wave_field", radius=8, rule=2, density="high",
        note="Deep ocean blue, bright aqua, technical headings, and restrained waves."),
    "blueprint": _visual_style(
        "Blueprint", "blueprint", "#96DAF2", "#102D56", dark=True,
        ornament="tactical_grid", rule=0.75, uppercase=True, density="high",
        note="Drafting blue, monospaced headings, square geometry, and fine grid marks."),
    "terracotta": _visual_style(
        "Terracotta", "luxury", "#A3472C", "#FAEDE0", radius=8,
        ornament="soft_shapes", rule=2.5, panel_pad=1.05,
        note="Clay accents, sand paper, sculptural serif headings, and warm panels."),
    "nordic_frost": _visual_style(
        "Nordic Frost", "minimal", "#3E6179", "#F3F7FA", radius=8,
        rule=0.75, margin=3.0, panel_pad=1.1,
        note="Cool white, slate blue, quiet sans serif, and open spacing."),
    "bauhaus": _visual_style(
        "Bauhaus", "brutalist", "#B6242F", "#FFF9E9", rule=4,
        uppercase=True, density="high", ornament="corporate_band",
        colors={"title": "#17191C", "heading": "#17191C",
                "accent_2": "#2455A4", "accent_3": "#E8AF22",
                "series_1": "#B6242F", "series_2": "#2455A4", "series_3": "#B07900"},
        note="Heavy black type, primary red and blue, cream ground, and bold rules."),
    "lavender_studio": _visual_style(
        "Lavender Studio", "friendly_consumer", "#735099", "#F5EFFA",
        radius=18, ornament="soft_shapes", rule=1.5, panel_pad=1.1,
        note="Plum headings, pale lavender, friendly rounded type, and soft cards."),
    "monochrome_ink": _visual_style(
        "Monochrome Ink", "brutalist", "#242424", "#FFFFFF", rule=3,
        uppercase=True, density="high", ornament="none",
        colors={"title": "#111111", "heading": "#111111",
                "text": "#171717", "text_muted": "#444444", "on_surface": "#171717",
                "accent": "#222222", "rule": "#222222",
                "accent_2": "#555555", "accent_3": "#999999",
                "series_1": "#222222", "series_2": "#555555", "series_3": "#888888",
                "series_4": "#333333", "series_5": "#666666", "series_6": "#777777",
                "series_7": "#444444", "series_8": "#111111"},
        note="Black and white, bold grotesque type, square panels, and strong rules."),
    "sunset_coral": _visual_style(
        "Sunset Coral", "startup_pitch", "#FFAE8F", "#352038", dark=True,
        ornament="gradient_mesh", radius=18, rule=2.5,
        colors={"subtitle": "#EDD9D2"},
        note="Apricot highlights, aubergine ground, geometric type, and rounded panels."),
}
NUANCES.update(STYLE_PRESETS)

# Nuances where generated artwork is FORBIDDEN regardless of confidence,
# user request or model suggestion. This set is checked by the theme layer and
# is the one place the decoration ceiling cannot be raised.
SAFETY_CRITICAL_NUANCES = frozenset({
    "financial_disclosure", "legal_compliance", "safety_briefing",
    "research_findings",
})

# English + Spanish aliases. Angela works in both languages, and a brief that
# says "presentación gamer" must land on the same treatment as "gaming deck".
NUANCE_ALIASES = {
    # esports
    "esports": "esports_tournament", "e-sports": "esports_tournament",
    "tournament": "esports_tournament", "torneo": "esports_tournament",
    "competitive": "esports_tournament", "competitivo": "esports_tournament",
    # game design
    "gdd": "game_design_doc", "gamedesign": "game_design_doc",
    "game_design": "game_design_doc", "diseno_de_juego": "game_design_doc",
    "videojuego": "game_design_doc", "juego": "game_design_doc",
    "gaming": "game_design_doc", "gamer": "game_design_doc",
    # trailer
    "trailer": "game_trailer_beat", "reveal": "game_trailer_beat",
    "cinematic": "game_trailer_beat", "cinematica": "game_trailer_beat",
    # cyberpunk
    "cyber": "cyberpunk_tech", "cyberpunk": "cyberpunk_tech",
    "neon": "cyberpunk_tech", "scifi": "cyberpunk_tech",
    "sci_fi": "cyberpunk_tech", "futurista": "cyberpunk_tech",
    # fantasy
    "fantasy": "fantasy_lore", "rpg": "fantasy_lore", "lore": "fantasy_lore",
    "fantasia": "fantasy_lore", "medieval": "fantasy_lore",
    # arcade
    "arcade": "retro_arcade", "retro": "retro_arcade", "pixel": "retro_arcade",
    "8bit": "retro_arcade", "8_bit": "retro_arcade",
    # military
    "military": "military_tactical", "tactical": "military_tactical",
    "fps": "military_tactical", "militar": "military_tactical",
    "tactico": "military_tactical",
    # streamer
    "streamer": "streamer_kit", "twitch": "streamer_kit",
    "creator": "streamer_kit", "influencer": "streamer_kit",
    # marketing
    "launch": "product_launch", "lanzamiento": "product_launch",
    "product": "product_launch", "producto": "product_launch",
    "brand": "brand_story", "marca": "brand_story",
    "manifesto": "brand_story", "manifiesto": "brand_story",
    "campaign": "campaign_report", "campana": "campaign_report",
    "marketing": "campaign_report", "performance": "campaign_report",
    "pitch": "startup_pitch", "investor": "startup_pitch",
    "startup": "startup_pitch", "inversionista": "startup_pitch",
    "vc": "startup_pitch", "seed": "startup_pitch",
    "sales": "sales_enablement", "ventas": "sales_enablement",
    "luxury": "luxury_brand", "premium": "luxury_brand", "lujo": "luxury_brand",
    "social": "social_media_kit", "instagram": "social_media_kit",
    "tiktok": "social_media_kit", "redes": "social_media_kit",
    "keynote": "event_keynote", "conference": "event_keynote",
    "conferencia": "event_keynote", "evento": "event_keynote",
    # corporate / technical
    "corporate": "corporate_update", "business": "corporate_update",
    "corporativo": "corporate_update", "empresa": "corporate_update",
    "architecture": "technical_architecture", "arquitectura": "technical_architecture",
    "technical": "technical_architecture", "tecnico": "technical_architecture",
    "engineering": "technical_architecture", "ingenieria": "technical_architecture",
    "research": "research_findings", "science": "research_findings",
    "scientific": "research_findings", "investigacion": "research_findings",
    "cientifico": "research_findings", "academic": "research_findings",
    "training": "training_course", "course": "training_course",
    "education": "training_course", "capacitacion": "training_course",
    "curso": "training_course", "educacion": "training_course",
    "roadmap": "project_status",
    # ⚠️ NOT a bare "status" key here. `agent/test_status_vocabulary.py` scans
    # every pool-agent source for status tokens, and a dict literal
    # {"status": "project_status"} is indistinguishable to it from an agent
    # emitting `status: project_status`. The guard is right to be strict — this
    # table is what was ambiguous. The longer phrases are better aliases anyway:
    # a bare "status" is a weak signal, while "status deck" / "status update" is
    # what somebody actually says, and `resolve_nuance`'s loose suffix match
    # still catches "weekly_status_update".
    "status_deck": "project_status", "status_update": "project_status",
    "project": "project_status", "proyecto": "project_status",
    "sprint": "project_status",
    # safety-critical
    "financial": "financial_disclosure", "finance": "financial_disclosure",
    "financiero": "financial_disclosure", "earnings": "financial_disclosure",
    "legal": "legal_compliance", "compliance": "legal_compliance",
    "contract": "legal_compliance", "cumplimiento": "legal_compliance",
    "safety": "safety_briefing", "medical": "safety_briefing",
    "seguridad": "safety_briefing", "medico": "safety_briefing",
    "clinical": "safety_briefing", "health": "safety_briefing",
}

# ─────────────────────────────────────────────────────────────────────────────
# Lexicons. Breadth matters more than depth (see contract 3).
# ─────────────────────────────────────────────────────────────────────────────

_LEXICON = {
    "esports_tournament": (
        "tournament", "bracket", "roster", "scrim", "playoff", "grand final",
        "seed", "group stage", "prize pool", "lan", "team", "clan", "squad",
        "mvp", "kda", "elo", "rank", "ladder", "qualifier", "caster",
        "torneo", "equipo", "clasificatoria", "premio", "ronda", "campeonato",
    ),
    "game_design_doc": (
        "gameplay", "mechanic", "core loop", "progression", "level design",
        "balance", "playtest", "prototype", "sandbox", "quest", "npc",
        "inventory", "skill tree", "difficulty curve", "onboarding",
        "game feel", "spawn", "respawn", "hitbox", "damage", "buff", "nerf",
        "mecanica", "jugabilidad", "nivel", "personaje", "mision",
    ),
    "game_trailer_beat": (
        "trailer", "beat sheet", "reveal", "teaser", "cinematic", "key art",
        "hero shot", "logo sting", "voice over", "cut", "montage", "reveal moment",
        "title card", "establishing shot", "climax", "b-roll",
    ),
    "cyberpunk_tech": (
        "neon", "dystopia", "augment", "implant", "netrunner", "megacorp",
        "chrome", "glitch", "hologram", "synth", "grid", "mainframe",
        "hack", "cyberspace", "android", "replicant", "neural",
    ),
    "fantasy_lore": (
        "kingdom", "realm", "dragon", "sorcerer", "mage", "artifact", "rune",
        "prophecy", "guild", "dungeon", "elf", "dwarf", "orc", "spell",
        "enchant", "relic", "legend", "myth", "quest giver", "tavern",
        "reino", "hechicero", "dragon", "leyenda", "mazmorra",
    ),
    "retro_arcade": (
        "arcade", "pixel", "8-bit", "16-bit", "sprite", "chiptune", "high score",
        "coin-op", "crt", "scanline", "power-up", "extra life", "game over",
        "side-scroller", "platformer", "retro",
    ),
    "military_tactical": (
        "squad", "objective", "loadout", "breach", "recon", "ops", "mission brief",
        "rules of engagement", "extraction", "insertion", "callsign", "hostile",
        "waypoint", "suppression", "flank", "tactical", "deployment",
    ),
    "streamer_kit": (
        "stream", "subscriber", "follower", "channel", "overlay", "donation",
        "sponsor", "brand deal", "watch time", "ccv", "vod", "clip",
        "community", "discord", "merch", "creator",
    ),
    "product_launch": (
        "launch", "introducing", "available now", "pre-order", "release date",
        "feature", "benefit", "pricing", "tier", "early access", "beta",
        "ship", "roadmap", "customer", "value proposition", "cta",
        "lanzamiento", "disponible", "precio", "caracteristica",
    ),
    "brand_story": (
        "our story", "mission", "vision", "values", "purpose", "believe",
        "founded", "journey", "why we", "brand", "identity", "promise",
        "manifesto", "heritage", "craft",
        "mision", "vision", "valores", "historia", "proposito",
    ),
    "campaign_report": (
        "impressions", "reach", "engagement", "ctr", "cpc", "cpm", "roas",
        "conversion", "funnel", "attribution", "channel", "spend", "budget",
        "a/b test", "audience", "segment", "retargeting", "campaign",
        "alcance", "conversion", "campana", "presupuesto",
    ),
    "startup_pitch": (
        "problem", "solution", "market size", "tam", "sam", "som", "traction",
        "runway", "burn rate", "arr", "mrr", "cac", "ltv", "churn",
        "go to market", "competitive landscape", "the ask", "round",
        "valuation", "cap table", "milestone", "founder",
    ),
    "sales_enablement": (
        "objection", "battlecard", "competitor", "differentiator", "pricing",
        "discount", "proposal", "close", "pipeline", "quota", "prospect",
        "discovery call", "demo", "use case", "roi", "procurement",
    ),
    "luxury_brand": (
        "craftsmanship", "atelier", "bespoke", "heritage", "exclusive",
        "limited edition", "artisan", "curated", "timeless", "refined",
        "couture", "connoisseur", "provenance", "handcrafted",
    ),
    "social_media_kit": (
        "post", "story", "reel", "carousel", "caption", "hashtag", "feed",
        "grid", "thumbnail", "cta", "swipe", "engagement", "viral",
        "content calendar", "platform", "creator",
    ),
    "event_keynote": (
        "keynote", "welcome", "agenda", "speaker", "session", "stage",
        "audience", "announcement", "today we", "thank you", "q and a",
        "conference", "summit", "attendee",
    ),
    "corporate_update": (
        "quarter", "objective", "key result", "okr", "kpi", "headcount",
        "department", "initiative", "stakeholder", "governance", "alignment",
        "operating", "leadership", "organisation", "organization",
        "trimestre", "objetivo", "equipo", "direccion",
    ),
    "technical_architecture": (
        "architecture", "service", "api", "endpoint", "latency", "throughput",
        "database", "cache", "queue", "load balancer", "microservice",
        "deployment", "container", "kubernetes", "schema", "protocol",
        "scalability", "availability", "failover", "pipeline", "sdk",
    ),
    "research_findings": (
        "hypothesis", "methodology", "sample size", "control group", "p-value",
        "confidence interval", "correlation", "regression", "significance",
        "dataset", "literature", "citation", "peer review", "abstract",
        "findings", "limitations", "future work", "et al",
    ),
    "training_course": (
        "learning objective", "module", "lesson", "exercise", "worked example",
        "practice", "assessment", "quiz", "curriculum", "prerequisite",
        "takeaway", "recap", "hands-on", "walkthrough", "certification",
        "objetivo de aprendizaje", "leccion", "ejercicio", "practica",
    ),
    "project_status": (
        "milestone", "deliverable", "blocker", "dependency", "owner",
        "due date", "on track", "at risk", "off track", "sprint", "backlog",
        "scope", "timeline", "phase", "gantt", "status update", "next steps",
        "hito", "entregable", "riesgo", "cronograma",
    ),
    "financial_disclosure": (
        "revenue", "ebitda", "gross margin", "net income", "cash flow",
        "balance sheet", "income statement", "fiscal year", "guidance",
        "shareholder", "dividend", "amortisation", "amortization", "audit",
        "gaap", "restated", "year over year", "quarter over quarter",
    ),
    "legal_compliance": (
        "hereby", "pursuant", "shall", "liability", "indemnify", "warranty",
        "jurisdiction", "clause", "termination", "confidential", "gdpr",
        "regulation", "compliance", "breach", "consent", "data processing",
        "agreement", "party", "obligation",
    ),
    "safety_briefing": (
        "hazard", "ppe", "evacuation", "emergency", "first aid", "risk assessment",
        "incident", "dosage", "contraindication", "adverse", "protocol",
        "sterile", "biohazard", "lockout", "tagout", "exposure limit",
        "warning", "caution", "do not", "must not",
    ),
}

_STRUCTURE_TESTS = (
    # (nuance, weight, compiled pattern, needs_lexical_corroboration)
    #
    # `needs_lexical_corroboration` is contract 2: the signal is real but its
    # domain is ambiguous, so it only counts when the lexicon agrees.
    ("financial_disclosure", 3.2,
     re.compile(r"(?:[$€£¥]\s?\d[\d,.]*\s?(?:[kmb]|million|billion)?)|(?:\d+\.\d%\s*(?:yoy|qoq))",
                re.I), False),
    ("financial_disclosure", 2.4,
     re.compile(r"\b(?:q[1-4]\s*(?:fy)?\s*'?\d{2,4}|fy\d{2,4})\b", re.I), True),
    ("research_findings", 3.0,
     re.compile(r"\bp\s*[<=>]\s*0?\.\d+|\b(?:n\s*=\s*\d+)|\b95%\s*ci\b", re.I), False),
    ("research_findings", 2.2,
     re.compile(r"\b(?:et\s+al\.?|doi:\s*10\.\d{4,})", re.I), False),
    ("legal_compliance", 3.0,
     re.compile(r"^\s*\d+(?:\.\d+){1,3}\s+\S", re.M), True),
    ("legal_compliance", 2.6,
     re.compile(r"\b(?:section|clause|article|artículo|cláusula)\s+\d+", re.I), False),
    ("safety_briefing", 3.4,
     re.compile(r"\b(?:danger|warning|caution|peligro|advertencia)\b\s*[:!]", re.I), False),
    ("safety_briefing", 2.8,
     re.compile(r"\b\d+\s*(?:mg|ml|mcg|µg|mmol)\b", re.I), True),
    ("startup_pitch", 2.8,
     re.compile(r"\b(?:tam|sam|som|arr|mrr|cac|ltv)\b", re.I), False),
    ("startup_pitch", 2.4,
     re.compile(r"\b(?:series\s+[a-d]|seed\s+round|pre-seed)\b", re.I), False),
    ("campaign_report", 2.6,
     re.compile(r"\b(?:ctr|cpc|cpm|roas|cpa)\b\s*[:=]?\s*\d", re.I), False),
    ("esports_tournament", 2.8,
     re.compile(r"\b(?:\d+\s*[-–]\s*\d+)\s*(?:win|loss|series|map)\b", re.I), False),
    ("esports_tournament", 2.4,
     re.compile(r"\b(?:bo[1357]|best\s+of\s+[1357]|group\s+[a-d]|quarterfinal|semifinal)\b",
                re.I), False),
    ("game_design_doc", 2.6,
     re.compile(r"\b(?:core\s+loop|game\s*play\s+loop|skill\s+tree|tech\s+tree)\b", re.I), False),
    ("game_design_doc", 2.0,
     re.compile(r"\b(?:lvl|level)\s*\d+\s*(?:→|->|to)\s*(?:lvl|level)?\s*\d+", re.I), True),
    ("technical_architecture", 2.6,
     re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/\S+|\bhttps?://\S+/v\d\b"), False),
    ("technical_architecture", 2.2,
     re.compile(r"\b(?:p9[59]|p50)\s*(?:latency)?\s*[:=]?\s*\d+\s*ms\b", re.I), False),
    ("project_status", 2.6,
     re.compile(r"\b(?:on\s+track|at\s+risk|off\s+track|blocked)\b", re.I), False),
    ("project_status", 2.0,
     re.compile(r"\b(?:sprint\s+\d+|week\s+\d+\s+of\s+\d+)\b", re.I), True),
    ("training_course", 2.6,
     re.compile(r"\b(?:learning\s+objectives?|by\s+the\s+end\s+of\s+this)\b", re.I), False),
    ("game_trailer_beat", 2.8,
     re.compile(r"\b(?:\d{1,2}:\d{2})\s*[-–—]\s*\S|\b(?:fade\s+(?:in|out)|cut\s+to)\b", re.I),
     True),
    ("retro_arcade", 2.4,
     re.compile(r"\b(?:8[-\s]?bit|16[-\s]?bit|high\s+score|game\s+over|1up)\b", re.I), False),
    ("event_keynote", 2.2,
     re.compile(r"\b(?:agenda|welcome\s+to|thank\s+you\s+for\s+joining)\b", re.I), True),
    ("luxury_brand", 2.2,
     re.compile(r"\b(?:limited\s+to\s+\d+|hand\s*(?:crafted|made)|made\s+in\s+[A-Z])\b"), True),
)

_TITLE_HINTS = (
    # A title is a strong, cheap signal — it is the one line the author wrote
    # deliberately to say what the deck IS.
    ("esports_tournament", ("tournament", "championship", "cup", "league",
                            "torneo", "copa", "liga")),
    ("game_design_doc", ("game design", "gdd", "gameplay", "diseño de juego")),
    ("game_trailer_beat", ("trailer", "reveal", "teaser", "announce")),
    ("product_launch", ("launch", "introducing", "meet the", "lanzamiento")),
    ("startup_pitch", ("pitch", "investor", "series a", "series b", "seed")),
    ("brand_story", ("brand", "manifesto", "our story", "who we are")),
    ("campaign_report", ("campaign", "performance", "results", "campaña")),
    ("event_keynote", ("keynote", "summit", "conference", "conf ")),
    ("research_findings", ("study", "research", "findings", "analysis",
                           "investigación", "estudio")),
    ("financial_disclosure", ("earnings", "financial", "fiscal", "annual report")),
    ("legal_compliance", ("compliance", "policy", "terms", "agreement", "legal")),
    ("safety_briefing", ("safety", "hazard", "emergency", "protocol",
                         "seguridad", "protocolo")),
    ("training_course", ("training", "course", "workshop", "curso", "taller")),
    ("project_status", ("status", "roadmap", "sprint", "update", "estado")),
    ("technical_architecture", ("architecture", "system design", "infrastructure",
                                "arquitectura")),
    ("corporate_update", ("quarterly", "business review", "qbr", "all hands")),
    ("luxury_brand", ("collection", "atelier", "maison", "couture")),
    ("cyberpunk_tech", ("cyber", "neon", "2077", "neural")),
    ("fantasy_lore", ("realm", "kingdom", "chronicles", "saga", "reino")),
    ("retro_arcade", ("arcade", "retro", "pixel", "8-bit")),
    ("military_tactical", ("tactical", "operation", "mission", "ops",
                           "táctico", "operación")),
    ("streamer_kit", ("stream", "channel", "creator", "twitch", "youtube")),
    ("social_media_kit", ("social", "content kit", "instagram", "tiktok")),
    ("sales_enablement", ("sales", "battlecard", "pricing", "ventas")),
)

_STRUCTURE_WEIGHT = 3.0     # contract 1: structure outweighs vocabulary ~3x
_TITLE_WEIGHT = 2.2
_AMBIGUOUS_DAMP = 0.35      # contract 2: no lexical support ⇒ heavily damped


class NuanceVerdict:
    """The classifier's answer, with its evidence."""

    __slots__ = ("nuance", "confidence", "source", "scores", "evidence", "spec")

    def __init__(self, nuance, confidence, source, scores=None, evidence=None):
        self.nuance = nuance
        self.confidence = float(confidence)
        self.source = source                 # 'explicit' | 'alias' | 'detected' | 'fallback'
        self.scores = scores or {}
        self.evidence = evidence or []
        self.spec = NUANCES.get(nuance, NUANCES["corporate_update"])

    @property
    def is_safety_critical(self) -> bool:
        return self.nuance in SAFETY_CRITICAL_NUANCES

    @property
    def label(self) -> str:
        return self.spec.get("label", self.nuance)

    def reasoning(self) -> str:
        """A human-readable account of WHY. Printed into the agent's log."""
        if self.source == "explicit":
            return f"Nuance '{self.nuance}' was requested explicitly; detection was not run."
        if self.source == "alias":
            return f"Nuance '{self.nuance}' resolved from the alias the user gave."
        if self.source == "fallback":
            return ("No treatment scored above the floor, so the deck falls back to "
                    "'corporate_update' and decoration is held back.")
        top = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)[:4]
        parts = ", ".join(f"{k}={v:.1f}" for k, v in top if v > 0)
        ev = "; ".join(self.evidence[:6])
        return (f"Detected '{self.nuance}' at confidence {self.confidence:.2f} "
                f"[{parts}]" + (f" — evidence: {ev}" if ev else ""))

    def __repr__(self) -> str:
        return f"NuanceVerdict({self.nuance!r}, {self.confidence:.2f}, {self.source})"


def _normalise_key(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")


def resolve_nuance(requested: str):
    """Resolve an EXPLICIT request (canonical name or alias) → nuance key or None."""
    key = _normalise_key(requested)
    if not key:
        return None
    if key in NUANCES:
        return key
    if key in NUANCE_ALIASES:
        return NUANCE_ALIASES[key]
    for style in STYLE_PRESETS:
        if key in (f"{style}_style", f"{style}_deck", f"{style}_presentation"):
            return style
    # De-accented Spanish (campaña → campana) is already handled by the alias
    # table; try a last loose contains-match so "gaming_deck" finds "gaming".
    for alias, target in NUANCE_ALIASES.items():
        if alias and (key == alias or key.startswith(alias + "_") or key.endswith("_" + alias)):
            return target
    return None


def classify(text: str, title: str = "", requested: str = "",
             image_count: int = 0, slide_hint: int = 0) -> NuanceVerdict:
    """Decide the deck's treatment. An explicit `requested` always wins.

    Scoring, per contract:
      structure  ×3.0  (damped ×0.35 when the signal is ambiguous and the
                        lexicon gives it no independent support)
      title      ×2.2
      lexicon    ×1.0  with log damping: 1 + ln(hits) per DISTINCT term
    """
    explicit = resolve_nuance(requested)
    if explicit:
        src = "explicit" if _normalise_key(requested) in NUANCES else "alias"
        return NuanceVerdict(explicit, 1.0, src)

    body = str(text or "")
    head = str(title or "")
    haystack = (head + "\n" + body).lower()
    if not haystack.strip():
        return NuanceVerdict("corporate_update", 0.0, "fallback")

    scores = {k: 0.0 for k in NUANCES}
    evidence = []

    # -- 1. lexicon, log-damped per distinct term ----------------------------
    lex_support = {}
    for nuance, terms in _LEXICON.items():
        distinct = 0
        total = 0
        for term in terms:
            count = haystack.count(term)
            if count:
                distinct += 1
                total += count
        if distinct:
            # Breadth (distinct) is the signal; depth (total) is damped hard.
            scores[nuance] += distinct * (1.0 + math.log1p(total / max(1, distinct)))
            lex_support[nuance] = distinct
            if distinct >= 3:
                evidence.append(f"{nuance}: {distinct} distinct domain terms")

    # -- 2. structure, weighted, with the ambiguity damper -------------------
    for nuance, weight, pattern, needs_support in _STRUCTURE_TESTS:
        try:
            hits = len(pattern.findall(body))
        except Exception:                                         # noqa: BLE001
            continue
        if not hits:
            continue
        gain = weight * _STRUCTURE_WEIGHT * (1.0 + math.log1p(hits)) / 3.0
        if needs_support and lex_support.get(nuance, 0) < 2:
            gain *= _AMBIGUOUS_DAMP
            evidence.append(f"{nuance}: structural hit damped (no lexical support)")
        else:
            evidence.append(f"{nuance}: structural pattern x{hits}")
        scores[nuance] += gain

    # -- 3. title ------------------------------------------------------------
    head_l = head.lower()
    if head_l:
        for nuance, hints in _TITLE_HINTS:
            for hint in hints:
                if hint in head_l:
                    scores[nuance] += _TITLE_WEIGHT
                    evidence.append(f"{nuance}: title says {hint!r}")
                    break

    # -- 4. shape of the deck ------------------------------------------------
    # Many images and little text is a visual deck; the reverse is a document.
    words = len(body.split())
    if image_count >= 4 and words < 400:
        for nuance in ("brand_story", "game_trailer_beat", "product_launch",
                       "social_media_kit", "event_keynote"):
            scores[nuance] += 1.4
        evidence.append("image-heavy with little text ⇒ visual treatments favoured")
    if words > 2500:
        for nuance in ("training_course", "corporate_update", "research_findings",
                       "legal_compliance", "sales_enablement"):
            scores[nuance] += 1.2
        evidence.append("long-form text ⇒ dense treatments favoured")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    runner_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # A floor, so a deck of three bullet points does not get a confident
    # esports treatment off one stray word.
    if best_score < 3.0:
        return NuanceVerdict("corporate_update", min(0.34, best_score / 9.0),
                             "fallback", scores, evidence)

    # Confidence blends absolute strength with the MARGIN over the runner-up.
    # A narrow win means two treatments both fit, which is exactly when the
    # agent should decorate less (contract 4).
    margin = (best_score - runner_score) / best_score if best_score else 0.0
    strength = min(1.0, best_score / 16.0)
    confidence = max(0.0, min(1.0, 0.45 * strength + 0.55 * margin))

    return NuanceVerdict(best, confidence, "detected", scores, evidence)


def decoration_ceiling_for(verdict: NuanceVerdict, requested: str = "auto") -> str:
    """The FINAL decoration level. Can only ever be LOWERED, never raised.

    Order of restriction:
      1. a safety-critical nuance ⇒ 'none', unconditionally;
      2. the nuance's own ceiling;
      3. low classifier confidence pulls it down one step;
      4. the user's `decorations` value, if it is lower than all of the above.
    """
    order = ("none", "restrained", "moderate", "rich")
    rank = {name: i for i, name in enumerate(order)}

    if verdict.is_safety_critical:
        return "none"

    ceiling = verdict.spec.get("decoration_ceiling", "restrained")
    level = rank.get(ceiling, 1)

    # Contract 4 — an uncertain classifier acts uncertain.
    if verdict.source == "detected":
        if verdict.confidence < 0.35:
            level = min(level, 1)
        elif verdict.confidence < 0.55:
            level = max(0, min(level, level - 1))

    want = _normalise_key(requested)
    if want in rank:
        level = min(level, rank[want])
    elif want in ("", "auto"):
        pass

    return order[max(0, min(len(order) - 1, level))]
