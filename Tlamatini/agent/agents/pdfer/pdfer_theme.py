# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer themes — turning a nuance into a complete, legible design system.

THE ONE JOB
-----------
`pdfer_nuance` answers *what is this document?* This module answers *so what
should it look like?* — and it answers with a **complete** specification:
thirty-eight colour roles, three type families, a modular scale, a spacing
rhythm, an ornament programme and a page setup. The renderer then asks only
for roles (``design.palette.table_header_bg``), never for a literal value,
which is exactly why replacing the old single brown scheme was a change to
this file rather than an archaeology dig through a renderer.

ANGELA'S TWO NAMED LOOKS, IMPLEMENTED HERE LITERALLY
-----------------------------------------------------
    *"if the content is detected to be of science and technology the
    background must be set to black and the foreground font white with
    gradients, and perfect differentiated titles, sub-titles"*

``scientific_dark`` — ``#07090F`` ground, ``#F2F6FF`` text, a cyan→violet
gradient programme, a condensed technical display face over a humanist sans,
and a 1.25 modular scale so H1…H4 are unmistakably four different things.

    *"if the file has an abstract and it seems to be a paper, then white
    background and black font, and LaTeX 100% styled"*

``academic_paper`` — ``#FFFFFF`` ground, ``#101010`` text, Palatino (the
closest widely-installed relative of Computer Modern's old-style feel) at a
restrained 1.2 ratio, justified body copy, a hairline rule under the title
and **nothing else** — because that is what a typeset journal article is.

THE SEED OVERRIDE  (Angela's ``predominant_color``)
----------------------------------------------------
    *"'predominant_color' … must be taken as the most important color
    (gradients used) across all of the document by parts, depending of the
    type of content: title, footer, normal text, etc."*

When a seed colour is supplied, the theme's hand-picked palette is *replaced*
by one derived from that seed via `pdfer_color.palette_from_seed` — but the
theme still decides the **character**: whether the document is dark or light,
how saturated it is, how warm its neutrals are. So ``predominant_color`` on a
legal document produces a restrained tinted-paper look, and the same colour on
a marketing brochure produces a loud one. One parameter, appropriate results,
because the seed sets the *hue* and the nuance sets the *register*.

CONTRACTS (do NOT weaken)
-------------------------
1. **EVERY design system passes contrast validation before it is returned.**
   `Palette.validated()` is the last call in `build_design_system`, without
   exception. A theme author picks hues; legibility is not negotiable.
2. **FAIL-OPEN.** An unknown nuance, an unparseable colour, a missing font —
   all degrade to a stated fallback. `build_design_system` cannot raise.
3. **The decoration budget from the verdict is a CEILING.** A theme may ask
   for less ornament than the budget allows; it may never ask for more. That
   is what keeps a mis-read contract from getting a gradient cover.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import pdfer_color as pc
import pdfer_nuance as pn
import pdfer_typography as ptypo

__all__ = [
    "THEMES",
    "DesignSystem",
    "build_design_system",
    "ORNAMENT_PROGRAMMES",
]


# ─────────────────────────────────────────────────────────────────────────
#  ORNAMENT PROGRAMMES
#
#  What kind of generated artwork suits this document, and where it may go.
#  ``motifs`` names generators in `pdfer_ornament`; ``surfaces`` says which
#  parts of the page may carry art at all. A programme is a REQUEST — the
#  decoration budget from the nuance verdict can veto any of it.
# ─────────────────────────────────────────────────────────────────────────
ORNAMENT_PROGRAMMES = {
    "constellation": {
        "motifs": ("particle_field", "orbital_arcs", "grid_mesh"),
        "surfaces": ("cover", "section_rule", "page_edge"),
        "note": "Points and arcs on a dark ground — the visual language of "
                "physics and astronomy.",
    },
    "circuitry": {
        "motifs": ("circuit_trace", "grid_mesh", "spectrum_bar"),
        "surfaces": ("cover", "section_rule", "header_band"),
        "note": "Traces and vias — computation and electronics.",
    },
    "waveform": {
        "motifs": ("sine_field", "spectrum_bar", "gradient_wash"),
        "surfaces": ("cover", "section_rule"),
        "note": "Signal and oscillation — data, audio, measurement.",
    },
    "scholarly_rule": {
        "motifs": ("hairline_rule",),
        "surfaces": ("title_rule",),
        "note": "A single hairline under the title. Nothing else. The "
                "restraint IS the design.",
    },
    "corporate_band": {
        "motifs": ("gradient_wash", "corner_wedge"),
        "surfaces": ("cover", "header_band"),
        "note": "A quiet gradient band — present, never loud.",
    },
    "editorial_flourish": {
        "motifs": ("gradient_wash", "drop_cap_panel", "hairline_rule"),
        "surfaces": ("cover", "section_rule", "drop_cap"),
        "note": "Magazine furniture: a washed cover, a drop cap, thin rules.",
    },
    "botanical": {
        "motifs": ("organic_blob", "gradient_wash"),
        "surfaces": ("cover", "section_rule"),
        "note": "Soft organic shapes — warmth without noise.",
    },
    "bold_geometry": {
        "motifs": ("diagonal_split", "gradient_wash", "corner_wedge",
                   "halftone_dots"),
        "surfaces": ("cover", "header_band", "section_rule", "page_edge"),
        "note": "Big diagonal colour — built to be seen across a room.",
    },
    "alert_grid": {
        "motifs": ("grid_mesh", "spectrum_bar", "scanline"),
        "surfaces": ("cover", "section_rule", "header_band"),
        "note": "Terminal-flavoured: mesh, scanlines, severity bars.",
    },
    "none": {
        "motifs": (),
        "surfaces": (),
        "note": "No generated artwork at all. Correct for anything the "
                "reader must follow exactly.",
    },
}


# ─────────────────────────────────────────────────────────────────────────
#  THE THEME CATALOG
#
#  One entry per nuance. Palettes are hand-picked rather than derived,
#  because a signature look is a set of *decisions* — deriving everything
#  from an algorithm gives twenty variations of the same document.
#  `palette_from_seed` exists for when the user supplies a colour instead.
# ─────────────────────────────────────────────────────────────────────────
THEMES = {
    # ═══ ANGELA'S NAMED LOOK #1 ═══════════════════════════════════════
    "scientific_dark": {
        "label": "Obsidian Instrument",
        "dark": True,
        "pairing": "technical",
        "scale": {"base": 10.2, "ratio": 1.25, "leading": 1.50},
        "ornament": "constellation",
        "justify": False,
        "palette": {
            "background": "#07090F", "background_alt": "#0C111C",
            "surface": "#111827", "surface_alt": "#18202F",
            "text": "#F2F6FF", "text_muted": "#9AA9C4",
            "text_inverse": "#07090F",
            "primary": "#38BDF8", "primary_soft": "#12283A",
            "secondary": "#A78BFA", "accent": "#22D3EE",
            "border": "#25324A", "border_soft": "#18202F",
            "rule": "#38BDF8",
            "link": "#67E8F9",
            "code_bg": "#0B1220", "code_fg": "#A5F3FC",
            "code_border": "#1E293B",
            "table_header_bg": "#152238", "table_header_fg": "#E0F2FE",
            "table_row_alt": "#0C1220", "table_border": "#233149",
            "quote_bar": "#A78BFA", "quote_bg": "#101827",
            "quote_fg": "#C7D2E8",
            "success": "#34D399", "warning": "#FBBF24",
            "danger": "#FB7185", "info": "#60A5FA",
            "heading_1": "#7DD3FC", "heading_2": "#38BDF8",
            "heading_3": "#A78BFA", "heading_4": "#94A3B8",
            "caption": "#8FA0BC", "footer": "#64748B",
            "cover_from": "#05070C", "cover_to": "#1E3A8A",
            "ornament": "#22D3EE",
        },
        "note": "Near-black ground, luminous cyan and violet, condensed "
                "technical display. Angela's brief, literally.",
    },

    # ═══ ANGELA'S NAMED LOOK #2 ═══════════════════════════════════════
    "academic_paper": {
        "label": "Journal Vellum",
        "dark": False,
        "pairing": "scholarly",
        "scale": {"base": 10.0, "ratio": 1.20, "leading": 1.42},
        "ornament": "scholarly_rule",
        "justify": True,           # journals justify. So do we.
        "palette": {
            "background": "#FFFFFF", "background_alt": "#FAFAF8",
            "surface": "#F7F7F4", "surface_alt": "#F0F0EC",
            "text": "#101010", "text_muted": "#4A4A48",
            "text_inverse": "#FFFFFF",
            "primary": "#1A1A1A", "primary_soft": "#EDEDEA",
            "secondary": "#3A3A38", "accent": "#7C2D12",
            "border": "#C9C9C4", "border_soft": "#E4E4DF",
            "rule": "#1A1A1A",
            "link": "#7C2D12",
            "code_bg": "#F5F5F1", "code_fg": "#1F2937",
            "code_border": "#D8D8D2",
            "table_header_bg": "#EFEFEB", "table_header_fg": "#101010",
            "table_row_alt": "#FBFBF9", "table_border": "#BFBFB9",
            "quote_bar": "#8A8A85", "quote_bg": "#FAFAF8",
            "quote_fg": "#3A3A38",
            "success": "#166534", "warning": "#854D0E",
            "danger": "#991B1B", "info": "#1E40AF",
            "heading_1": "#0A0A0A", "heading_2": "#141414",
            "heading_3": "#1E1E1E", "heading_4": "#3A3A38",
            "caption": "#5A5A56", "footer": "#6B6B66",
            "cover_from": "#FFFFFF", "cover_to": "#F2F2EE",
            "ornament": "#1A1A1A",
        },
        "note": "Pure white, near-black old-style serif, justified, one "
                "hairline rule. What LaTeX would do.",
    },

    "software_manual": {
        "label": "Developer Slate",
        "dark": False,
        "pairing": "technical_mono",
        "scale": {"base": 10.2, "ratio": 1.25, "leading": 1.48},
        "ornament": "circuitry",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F8FAFC",
            "surface": "#F1F5F9", "surface_alt": "#E2E8F0",
            "text": "#0F172A", "text_muted": "#475569",
            "text_inverse": "#FFFFFF",
            "primary": "#0E7490", "primary_soft": "#E0F2FE",
            "secondary": "#7C3AED", "accent": "#0891B2",
            "border": "#CBD5E1", "border_soft": "#E2E8F0",
            "rule": "#0E7490",
            "link": "#0369A1",
            "code_bg": "#0F172A", "code_fg": "#E2E8F0",
            "code_border": "#1E293B",
            "table_header_bg": "#0E7490", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F8FAFC", "table_border": "#CBD5E1",
            "quote_bar": "#0891B2", "quote_bg": "#ECFEFF",
            "quote_fg": "#155E75",
            "success": "#047857", "warning": "#B45309",
            "danger": "#BE123C", "info": "#1D4ED8",
            "heading_1": "#0C4A6E", "heading_2": "#0E7490",
            "heading_3": "#155E75", "heading_4": "#334155",
            "caption": "#64748B", "footer": "#94A3B8",
            "cover_from": "#0C4A6E", "cover_to": "#06B6D4",
            "ornament": "#0891B2",
        },
        "note": "White page, DARK code panels (the way an editor shows "
                "code), teal accents, monospaced headings.",
    },

    "engineering_spec": {
        "label": "Drafting Table",
        "dark": False,
        "pairing": "technical",
        "scale": {"base": 9.8, "ratio": 1.20, "leading": 1.40},
        "ornament": "corporate_band",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F6F7F9",
            "surface": "#EEF1F5", "surface_alt": "#E1E6ED",
            "text": "#14181F", "text_muted": "#4B5563",
            "text_inverse": "#FFFFFF",
            "primary": "#1E4B7A", "primary_soft": "#DCE7F3",
            "secondary": "#475569", "accent": "#B45309",
            "border": "#C2CBD6", "border_soft": "#DFE5EC",
            "rule": "#1E4B7A",
            "link": "#1E4B7A",
            "code_bg": "#F2F4F7", "code_fg": "#1F2937",
            "code_border": "#D3DAE3",
            "table_header_bg": "#1E4B7A", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F6F8FA", "table_border": "#B6C0CC",
            "quote_bar": "#B45309", "quote_bg": "#FEF7EC",
            "quote_fg": "#4B5563",
            "success": "#15803D", "warning": "#B45309",
            "danger": "#B91C1C", "info": "#1E40AF",
            "heading_1": "#12395E", "heading_2": "#1E4B7A",
            "heading_3": "#2C3E50", "heading_4": "#4B5563",
            "caption": "#5B6674", "footer": "#8894A3",
            "cover_from": "#12395E", "cover_to": "#3E7CB1",
            "ornament": "#1E4B7A",
        },
        "note": "Blueprint blue on white, tight leading, tables first. "
                "Precision, not personality.",
    },

    "business_report": {
        "label": "Boardroom Navy",
        "dark": False,
        "pairing": "corporate",
        "scale": {"base": 10.5, "ratio": 1.25, "leading": 1.50},
        "ornament": "corporate_band",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F7F9FC",
            "surface": "#EFF3F9", "surface_alt": "#E1E9F3",
            "text": "#16202E", "text_muted": "#4A5768",
            "text_inverse": "#FFFFFF",
            "primary": "#173A5E", "primary_soft": "#DEE9F5",
            "secondary": "#0F766E", "accent": "#C2410C",
            "border": "#C6D0DD", "border_soft": "#E2E9F2",
            "rule": "#173A5E",
            "link": "#1D4E85",
            "code_bg": "#F3F6FA", "code_fg": "#1F2937",
            "code_border": "#D5DEE9",
            "table_header_bg": "#173A5E", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F6F9FC", "table_border": "#BCC8D7",
            "quote_bar": "#0F766E", "quote_bg": "#EEF7F6",
            "quote_fg": "#3C4A5A",
            "success": "#15803D", "warning": "#A16207",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#102A45", "heading_2": "#173A5E",
            "heading_3": "#2A4763", "heading_4": "#4A5768",
            "caption": "#5C6B7D", "footer": "#8593A5",
            "cover_from": "#102A45", "cover_to": "#2F6FA8",
            "ornament": "#0F766E",
        },
        "note": "Navy and teal on white. Quiet, evidential, boardroom-safe.",
    },

    "financial_ledger": {
        "label": "Ledger Green",
        "dark": False,
        "pairing": "dense",
        "scale": {"base": 9.4, "ratio": 1.20, "leading": 1.34},
        "ornament": "none",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F8FAF8",
            "surface": "#F1F5F1", "surface_alt": "#E3EBE4",
            "text": "#14201A", "text_muted": "#4B5B52",
            "text_inverse": "#FFFFFF",
            "primary": "#14532D", "primary_soft": "#DCEBE2",
            "secondary": "#334155", "accent": "#92400E",
            "border": "#C4D2C8", "border_soft": "#E1EAE3",
            "rule": "#14532D",
            "link": "#166534",
            "code_bg": "#F4F7F4", "code_fg": "#1F2937",
            "code_border": "#D6E0D8",
            "table_header_bg": "#14532D", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F6FAF7", "table_border": "#B7C7BC",
            "quote_bar": "#92400E", "quote_bg": "#FDF7EE",
            "quote_fg": "#4B5B52",
            "success": "#15803D", "warning": "#A16207",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#0E3D21", "heading_2": "#14532D",
            "heading_3": "#28453A", "heading_4": "#4B5B52",
            "caption": "#5C6B62", "footer": "#8A968E",
            "cover_from": "#0E3D21", "cover_to": "#2F7A4E",
            "ornament": "#14532D",
        },
        "note": "Ledger green, condensed faces, no ornament at all. Every "
                "point of width goes to a column of figures.",
    },

    "legal_instrument": {
        "label": "Statute Bond",
        "dark": False,
        "pairing": "legal",
        "scale": {"base": 10.5, "ratio": 1.15, "leading": 1.55},
        "ornament": "none",
        "justify": True,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#FCFCFA",
            "surface": "#F7F7F4", "surface_alt": "#F0F0EB",
            "text": "#000000", "text_muted": "#3D3D3A",
            "text_inverse": "#FFFFFF",
            "primary": "#1C1C1A", "primary_soft": "#EDEDE9",
            "secondary": "#3D3D3A", "accent": "#4A3520",
            "border": "#C8C8C2", "border_soft": "#E6E6E1",
            "rule": "#1C1C1A",
            "link": "#1C1C1A",
            "code_bg": "#F6F6F2", "code_fg": "#1C1C1A",
            "code_border": "#DCDCD6",
            "table_header_bg": "#EDEDE8", "table_header_fg": "#000000",
            "table_row_alt": "#FBFBF9", "table_border": "#BEBEB8",
            "quote_bar": "#8A8A83", "quote_bg": "#FAFAF7",
            "quote_fg": "#3D3D3A",
            "success": "#14532D", "warning": "#713F12",
            "danger": "#7F1D1D", "info": "#1E3A8A",
            "heading_1": "#000000", "heading_2": "#0F0F0E",
            "heading_3": "#1C1C1A", "heading_4": "#3D3D3A",
            "caption": "#4D4D48", "footer": "#6B6B65",
            "cover_from": "#FFFFFF", "cover_to": "#F4F4F0",
            "ornament": "#1C1C1A",
        },
        "note": "Black on white, Times, justified, generous leading, no "
                "colour. A decorated contract looks forged.",
    },

    "medical_clinical": {
        "label": "Clinical Calm",
        "dark": False,
        "pairing": "corporate",
        "scale": {"base": 10.4, "ratio": 1.20, "leading": 1.52},
        "ornament": "none",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F7FBFB",
            "surface": "#EDF6F6", "surface_alt": "#DCEDEE",
            "text": "#14201F", "text_muted": "#48605F",
            "text_inverse": "#FFFFFF",
            "primary": "#0F5E5A", "primary_soft": "#DBEEED",
            "secondary": "#1E4B7A", "accent": "#B45309",
            "border": "#BFD6D5", "border_soft": "#DEECEC",
            "rule": "#0F5E5A",
            "link": "#0F5E5A",
            "code_bg": "#F3F8F8", "code_fg": "#14201F",
            "code_border": "#D2E3E3",
            "table_header_bg": "#0F5E5A", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F6FBFB", "table_border": "#B4CCCB",
            "quote_bar": "#B45309", "quote_bg": "#FEF8EF",
            "quote_fg": "#48605F",
            "success": "#15803D", "warning": "#B45309",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#0B4643", "heading_2": "#0F5E5A",
            "heading_3": "#245C58", "heading_4": "#48605F",
            "caption": "#587170", "footer": "#87A09F",
            "cover_from": "#0B4643", "cover_to": "#2E9490",
            "ornament": "#0F5E5A",
        },
        "note": "Calm teal on white, generous leading, zero ornament. "
                "Nothing decorative near a dosage.",
    },

    "security_briefing": {
        "label": "Threat Console",
        "dark": True,
        "pairing": "technical_mono",
        "scale": {"base": 10.0, "ratio": 1.25, "leading": 1.48},
        "ornament": "alert_grid",
        "justify": False,
        "palette": {
            "background": "#0A0A0C", "background_alt": "#101014",
            "surface": "#16161C", "surface_alt": "#1E1E26",
            "text": "#EDEDF0", "text_muted": "#9C9CA8",
            "text_inverse": "#0A0A0C",
            "primary": "#F59E0B", "primary_soft": "#2A2113",
            "secondary": "#F87171", "accent": "#FBBF24",
            "border": "#2C2C36", "border_soft": "#1E1E26",
            "rule": "#F59E0B",
            "link": "#FCD34D",
            "code_bg": "#0D0D11", "code_fg": "#86EFAC",
            "code_border": "#22222B",
            "table_header_bg": "#25201A", "table_header_fg": "#FDE68A",
            "table_row_alt": "#0F0F13", "table_border": "#33333E",
            "quote_bar": "#F87171", "quote_bg": "#17151A",
            "quote_fg": "#C4C4CE",
            "success": "#4ADE80", "warning": "#FBBF24",
            "danger": "#F87171", "info": "#60A5FA",
            "heading_1": "#FBBF24", "heading_2": "#F59E0B",
            "heading_3": "#F87171", "heading_4": "#9C9CA8",
            "caption": "#8A8A96", "footer": "#5C5C68",
            "cover_from": "#08080A", "cover_to": "#7C2D12",
            "ornament": "#F59E0B",
        },
        "note": "Console black with amber/red severity accents and green "
                "terminal code. Reads like the tools it reports on.",
    },

    "data_analysis": {
        "label": "Measured Light",
        "dark": False,
        "pairing": "technical",
        "scale": {"base": 10.2, "ratio": 1.25, "leading": 1.46},
        "ornament": "waveform",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F8F9FC",
            "surface": "#F1F3F9", "surface_alt": "#E4E8F2",
            "text": "#151824", "text_muted": "#4C5468",
            "text_inverse": "#FFFFFF",
            "primary": "#4338CA", "primary_soft": "#E6E4FB",
            "secondary": "#0F766E", "accent": "#DB2777",
            "border": "#CBD1E0", "border_soft": "#E4E8F2",
            "rule": "#4338CA",
            "link": "#4338CA",
            "code_bg": "#F3F4FA", "code_fg": "#1F2937",
            "code_border": "#D8DDEA",
            "table_header_bg": "#4338CA", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#F8F9FD", "table_border": "#C2C9DA",
            "quote_bar": "#DB2777", "quote_bg": "#FDF2F8",
            "quote_fg": "#4C5468",
            "success": "#047857", "warning": "#A16207",
            "danger": "#BE123C", "info": "#1D4ED8",
            "heading_1": "#312A9E", "heading_2": "#4338CA",
            "heading_3": "#0F766E", "heading_4": "#4C5468",
            "caption": "#5E6779", "footer": "#8B93A5",
            "cover_from": "#312A9E", "cover_to": "#06B6D4",
            "ornament": "#4338CA",
        },
        "note": "Indigo and teal on white — a palette that survives being "
                "used for chart series as well as furniture.",
    },

    "editorial_feature": {
        "label": "Feature Press",
        "dark": False,
        "pairing": "editorial",
        "scale": {"base": 10.8, "ratio": 1.333, "leading": 1.58},
        "ornament": "editorial_flourish",
        "justify": True,
        "palette": {
            "background": "#FDFCF9", "background_alt": "#F7F4EE",
            "surface": "#F2EEE6", "surface_alt": "#E8E2D6",
            "text": "#1B1917", "text_muted": "#585048",
            "text_inverse": "#FDFCF9",
            "primary": "#9A3412", "primary_soft": "#F7E6DC",
            "secondary": "#1E3A5F", "accent": "#B45309",
            "border": "#D6CFC2", "border_soft": "#EBE5DA",
            "rule": "#9A3412",
            "link": "#9A3412",
            "code_bg": "#F5F1E9", "code_fg": "#2A2622",
            "code_border": "#DED7C9",
            "table_header_bg": "#E8DFD1", "table_header_fg": "#1B1917",
            "table_row_alt": "#FAF7F1", "table_border": "#CEC5B5",
            "quote_bar": "#B45309", "quote_bg": "#F8F3E9",
            "quote_fg": "#4A423A",
            "success": "#15803D", "warning": "#A16207",
            "danger": "#B91C1C", "info": "#1E40AF",
            "heading_1": "#7C2D12", "heading_2": "#9A3412",
            "heading_3": "#1E3A5F", "heading_4": "#585048",
            "caption": "#6B6259", "footer": "#8C8378",
            "cover_from": "#7C2D12", "cover_to": "#D97706",
            "ornament": "#B45309",
        },
        "note": "Warm paper, terracotta and deep blue, Georgia justified, "
                "a drop cap. Magazine cadence.",
    },

    "creative_literary": {
        "label": "Quiet Paper",
        "dark": False,
        "pairing": "literary",
        "scale": {"base": 11.0, "ratio": 1.333, "leading": 1.65},
        "ornament": "botanical",
        "justify": True,
        "palette": {
            "background": "#FDFBF6", "background_alt": "#F8F4EB",
            "surface": "#F3EEE3", "surface_alt": "#EAE3D4",
            "text": "#22201C", "text_muted": "#5E574C",
            "text_inverse": "#FDFBF6",
            "primary": "#5B4636", "primary_soft": "#EFE7DA",
            "secondary": "#4A5D52", "accent": "#8C6239",
            "border": "#D9D0BF", "border_soft": "#EDE7DA",
            "rule": "#5B4636",
            "link": "#5B4636",
            "code_bg": "#F5F1E7", "code_fg": "#2E2A24",
            "code_border": "#E0D8C7",
            "table_header_bg": "#EAE1D0", "table_header_fg": "#22201C",
            "table_row_alt": "#FAF7EF", "table_border": "#D2C8B5",
            "quote_bar": "#8C6239", "quote_bg": "#F8F4EA",
            "quote_fg": "#544C42",
            "success": "#3F6212", "warning": "#854D0E",
            "danger": "#9F1239", "info": "#1E3A8A",
            "heading_1": "#43342A", "heading_2": "#5B4636",
            "heading_3": "#4A5D52", "heading_4": "#5E574C",
            "caption": "#6E665A", "footer": "#8F8578",
            "cover_from": "#43342A", "cover_to": "#A98352",
            "ornament": "#8C6239",
        },
        "note": "Cream paper, umber ink, wide leading. Type that gets out "
                "of the way of the words.",
    },

    "marketing_brochure": {
        "label": "Signal Bloom",
        "dark": False,
        "pairing": "promotional",
        "scale": {"base": 11.0, "ratio": 1.414, "leading": 1.52},
        "ornament": "bold_geometry",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#FBF7FF",
            "surface": "#F5EDFF", "surface_alt": "#EADDFC",
            "text": "#160F22", "text_muted": "#5A4B70",
            "text_inverse": "#FFFFFF",
            "primary": "#7C3AED", "primary_soft": "#F0E7FE",
            "secondary": "#DB2777", "accent": "#F59E0B",
            "border": "#DDD0F0", "border_soft": "#EFE7FA",
            "rule": "#7C3AED",
            "link": "#6D28D9",
            "code_bg": "#F7F3FE", "code_fg": "#2E1A47",
            "code_border": "#E3D7F7",
            "table_header_bg": "#7C3AED", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#FBF8FF", "table_border": "#D6C7EE",
            "quote_bar": "#DB2777", "quote_bg": "#FDF2F8",
            "quote_fg": "#5A4B70",
            "success": "#059669", "warning": "#D97706",
            "danger": "#DC2626", "info": "#2563EB",
            "heading_1": "#5B21B6", "heading_2": "#7C3AED",
            "heading_3": "#DB2777", "heading_4": "#5A4B70",
            "caption": "#6B5C82", "footer": "#9585AC",
            "cover_from": "#5B21B6", "cover_to": "#EC4899",
            "ornament": "#F59E0B",
        },
        "note": "Violet to magenta, heavy display, diagonal colour. The one "
                "place where loud is the correct answer.",
    },

    "educational_course": {
        "label": "Classroom Warm",
        "dark": False,
        "pairing": "friendly",
        "scale": {"base": 10.8, "ratio": 1.25, "leading": 1.56},
        "ornament": "botanical",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#FBF9F4",
            "surface": "#F4F1E8", "surface_alt": "#E9E4D6",
            "text": "#1E1B16", "text_muted": "#565043",
            "text_inverse": "#FFFFFF",
            "primary": "#1D6F5C", "primary_soft": "#DCEFE9",
            "secondary": "#B45309", "accent": "#2563EB",
            "border": "#D5CFC0", "border_soft": "#EBE6D9",
            "rule": "#1D6F5C",
            "link": "#1D6F5C",
            "code_bg": "#F4F2EA", "code_fg": "#28241C",
            "code_border": "#DDD7C7",
            "table_header_bg": "#1D6F5C", "table_header_fg": "#FFFFFF",
            "table_row_alt": "#FAF8F2", "table_border": "#CBC4B2",
            "quote_bar": "#B45309", "quote_bg": "#FDF7EC",
            "quote_fg": "#565043",
            "success": "#15803D", "warning": "#B45309",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#155345", "heading_2": "#1D6F5C",
            "heading_3": "#B45309", "heading_4": "#565043",
            "caption": "#65604F", "footer": "#8B8574",
            "cover_from": "#155345", "cover_to": "#5EAD8F",
            "ornament": "#B45309",
        },
        "note": "Warm paper, forest green, amber callouts. Open and "
                "encouraging without being childish.",
    },

    "government_policy": {
        "label": "Civic Grey",
        "dark": False,
        "pairing": "legal",
        "scale": {"base": 10.4, "ratio": 1.20, "leading": 1.52},
        "ornament": "scholarly_rule",
        "justify": True,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F7F8F9",
            "surface": "#EFF1F3", "surface_alt": "#E2E5E9",
            "text": "#15181C", "text_muted": "#4A5058",
            "text_inverse": "#FFFFFF",
            "primary": "#1F3A5F", "primary_soft": "#DEE6F0",
            "secondary": "#5B4636", "accent": "#7C2D12",
            "border": "#C7CCD3", "border_soft": "#E3E6EA",
            "rule": "#1F3A5F",
            "link": "#1F3A5F",
            "code_bg": "#F3F5F7", "code_fg": "#1F2937",
            "code_border": "#D8DCE2",
            "table_header_bg": "#E5E9EE", "table_header_fg": "#15181C",
            "table_row_alt": "#F8F9FB", "table_border": "#BEC4CC",
            "quote_bar": "#7C2D12", "quote_bg": "#FAF6F3",
            "quote_fg": "#4A5058",
            "success": "#15803D", "warning": "#A16207",
            "danger": "#991B1B", "info": "#1E40AF",
            "heading_1": "#152A46", "heading_2": "#1F3A5F",
            "heading_3": "#33404F", "heading_4": "#4A5058",
            "caption": "#59606A", "footer": "#858C96",
            "cover_from": "#152A46", "cover_to": "#41648F",
            "ornament": "#1F3A5F",
        },
        "note": "Neutral civic grey-blue, justified, numbered. Formal "
                "without being ceremonial.",
    },

    "historical_archive": {
        "label": "Archive Sepia",
        "dark": False,
        "pairing": "literary",
        "scale": {"base": 10.6, "ratio": 1.25, "leading": 1.58},
        "ornament": "editorial_flourish",
        "justify": True,
        "palette": {
            "background": "#FBF7EE", "background_alt": "#F5EFE1",
            "surface": "#EFE7D5", "surface_alt": "#E4D9C2",
            "text": "#2A2318", "text_muted": "#645845",
            "text_inverse": "#FBF7EE",
            "primary": "#6B4423", "primary_soft": "#EEE3CF",
            "secondary": "#4A5240", "accent": "#96552B",
            "border": "#D6C8AC", "border_soft": "#EBE1CD",
            "rule": "#6B4423",
            "link": "#6B4423",
            "code_bg": "#F3ECDC", "code_fg": "#332B1E",
            "code_border": "#DDD0B6",
            "table_header_bg": "#E6DAC0", "table_header_fg": "#2A2318",
            "table_row_alt": "#F8F3E7", "table_border": "#CBBB9C",
            "quote_bar": "#96552B", "quote_bg": "#F6F0E2",
            "quote_fg": "#5A4E3C",
            "success": "#3F6212", "warning": "#854D0E",
            "danger": "#7F1D1D", "info": "#1E3A8A",
            "heading_1": "#513219", "heading_2": "#6B4423",
            "heading_3": "#4A5240", "heading_4": "#645845",
            "caption": "#726550", "footer": "#93866E",
            "cover_from": "#513219", "cover_to": "#B08147",
            "ornament": "#96552B",
        },
        "note": "Aged paper and sepia ink — a chronicle, not a pastiche.",
    },

    "culinary_recipe": {
        "label": "Kitchen Table",
        "dark": False,
        "pairing": "friendly",
        "scale": {"base": 11.0, "ratio": 1.25, "leading": 1.56},
        "ornament": "botanical",
        "justify": False,
        "palette": {
            "background": "#FFFCF7", "background_alt": "#FDF6EA",
            "surface": "#F9EEDC", "surface_alt": "#F1E1C7",
            "text": "#241A12", "text_muted": "#6A5744",
            "text_inverse": "#FFFCF7",
            "primary": "#B4451F", "primary_soft": "#FAE5DA",
            "secondary": "#4D7C0F", "accent": "#D97706",
            "border": "#E4D2B6", "border_soft": "#F3E7D4",
            "rule": "#B4451F",
            "link": "#B4451F",
            "code_bg": "#FAF2E5", "code_fg": "#2E2317",
            "code_border": "#E8D9BF",
            "table_header_bg": "#B4451F", "table_header_fg": "#FFFCF7",
            "table_row_alt": "#FEFAF3", "table_border": "#DEC9A9",
            "quote_bar": "#4D7C0F", "quote_bg": "#F6F8EC",
            "quote_fg": "#5C4C3B",
            "success": "#4D7C0F", "warning": "#B45309",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#8C3517", "heading_2": "#B4451F",
            "heading_3": "#4D7C0F", "heading_4": "#6A5744",
            "caption": "#7A6752", "footer": "#9C8A74",
            "cover_from": "#8C3517", "cover_to": "#E8A33D",
            "ornament": "#4D7C0F",
        },
        "note": "Terracotta and olive on cream — appetising, while the "
                "quantities stay perfectly unambiguous.",
    },

    "personal_letter": {
        "label": "Letter Hand",
        "dark": False,
        "pairing": "literary",
        "scale": {"base": 11.2, "ratio": 1.25, "leading": 1.62},
        "ornament": "scholarly_rule",
        "justify": False,
        "palette": {
            "background": "#FFFDF9", "background_alt": "#FAF6EE",
            "surface": "#F5F0E5", "surface_alt": "#ECE4D4",
            "text": "#252119", "text_muted": "#5F584B",
            "text_inverse": "#FFFDF9",
            "primary": "#4A5D52", "primary_soft": "#E7EEE9",
            "secondary": "#6B4423", "accent": "#7C6A4F",
            "border": "#DBD3C2", "border_soft": "#EFE9DC",
            "rule": "#4A5D52",
            "link": "#4A5D52",
            "code_bg": "#F6F2E9", "code_fg": "#2E2A22",
            "code_border": "#E2DACA",
            "table_header_bg": "#ECE5D6", "table_header_fg": "#252119",
            "table_row_alt": "#FBF8F1", "table_border": "#D3CAB7",
            "quote_bar": "#7C6A4F", "quote_bg": "#F8F4EB",
            "quote_fg": "#574F43",
            "success": "#3F6212", "warning": "#854D0E",
            "danger": "#9F1239", "info": "#1E3A8A",
            "heading_1": "#3A4A41", "heading_2": "#4A5D52",
            "heading_3": "#6B4423", "heading_4": "#5F584B",
            "caption": "#6F6759", "footer": "#928A7B",
            "cover_from": "#3A4A41", "cover_to": "#8FA396",
            "ornament": "#7C6A4F",
        },
        "note": "Writing paper, sage and umber, wide leading. Personal "
                "without being twee.",
    },

    "presentation_deck": {
        "label": "Stage Dark",
        "dark": True,
        "pairing": "promotional",
        "scale": {"base": 13.0, "ratio": 1.414, "leading": 1.44},
        "ornament": "bold_geometry",
        "justify": False,
        "palette": {
            "background": "#0B0B14", "background_alt": "#12121F",
            "surface": "#1A1A2B", "surface_alt": "#232338",
            "text": "#F5F5FA", "text_muted": "#A5A5BC",
            "text_inverse": "#0B0B14",
            "primary": "#A78BFA", "primary_soft": "#221B36",
            "secondary": "#F472B6", "accent": "#FBBF24",
            "border": "#2E2E45", "border_soft": "#202033",
            "rule": "#A78BFA",
            "link": "#C4B5FD",
            "code_bg": "#0E0E1A", "code_fg": "#C7D2FE",
            "code_border": "#252540",
            "table_header_bg": "#241D3D", "table_header_fg": "#EDE9FE",
            "table_row_alt": "#101020", "table_border": "#32324B",
            "quote_bar": "#F472B6", "quote_bg": "#17172A",
            "quote_fg": "#CFCFE0",
            "success": "#4ADE80", "warning": "#FBBF24",
            "danger": "#FB7185", "info": "#60A5FA",
            "heading_1": "#C4B5FD", "heading_2": "#A78BFA",
            "heading_3": "#F472B6", "heading_4": "#A5A5BC",
            "caption": "#9494AC", "footer": "#63637C",
            "cover_from": "#09090F", "cover_to": "#6D28D9",
            "ornament": "#FBBF24",
        },
        "note": "Stage black, violet and gold, very large type. Legible "
                "from the back of a room.",
    },

    "minimal_note": {
        "label": "Plain",
        "dark": False,
        "pairing": "neutral",
        "scale": {"base": 10.5, "ratio": 1.25, "leading": 1.48},
        "ornament": "scholarly_rule",
        "justify": False,
        "palette": {
            "background": "#FFFFFF", "background_alt": "#F8F8F8",
            "surface": "#F2F2F2", "surface_alt": "#E7E7E7",
            "text": "#181818", "text_muted": "#4F4F4F",
            "text_inverse": "#FFFFFF",
            "primary": "#2C4A6E", "primary_soft": "#E3EAF2",
            "secondary": "#4F4F4F", "accent": "#8A5A2B",
            "border": "#CFCFCF", "border_soft": "#E6E6E6",
            "rule": "#2C4A6E",
            "link": "#2C4A6E",
            "code_bg": "#F4F4F4", "code_fg": "#1F2937",
            "code_border": "#DCDCDC",
            "table_header_bg": "#E9EDF2", "table_header_fg": "#181818",
            "table_row_alt": "#FAFAFA", "table_border": "#C6C6C6",
            "quote_bar": "#8A5A2B", "quote_bg": "#FAF8F5",
            "quote_fg": "#4F4F4F",
            "success": "#15803D", "warning": "#A16207",
            "danger": "#B91C1C", "info": "#1D4ED8",
            "heading_1": "#1F3550", "heading_2": "#2C4A6E",
            "heading_3": "#3A3A3A", "heading_4": "#4F4F4F",
            "caption": "#5E5E5E", "footer": "#8A8A8A",
            "cover_from": "#1F3550", "cover_to": "#5A7FA8",
            "ornament": "#2C4A6E",
        },
        "note": "Quiet, correct, unopinionated. The honest answer when the "
                "content says nothing about itself.",
    },
}


class DesignSystem:
    """Everything the renderer needs to dress a document, already validated.

    The renderer NEVER reads content and NEVER picks a colour; it asks this
    object. That is what makes the whole look swappable, and what makes
    ``nuance`` / ``predominant_color`` single-parameter changes rather than a
    rewrite.
    """

    def __init__(self, nuance, palette, fonts, scale, spacing, ornament,
                 decoration, page, meta):
        self.nuance = nuance
        self.palette = palette
        self.fonts = fonts
        self.scale = scale
        self.sizes = scale.as_dict()
        self.spacing = spacing
        self.ornament = ornament
        self.decoration = decoration
        self.page = page
        self.meta = meta

    @property
    def dark(self) -> bool:
        return bool(self.palette.dark)

    @property
    def justify(self) -> bool:
        return bool(self.page.get("justify", False))

    def may_decorate(self, surface: str) -> bool:
        """Is generated artwork allowed on *surface* for this document?

        Two gates, both must pass: the theme's ornament programme has to list
        the surface, AND the decoration budget from the nuance verdict has to
        permit that much. The budget is a CEILING the theme cannot raise —
        which is the mechanism that keeps a misclassified contract from
        getting a gradient cover.
        """
        if self.decoration == "none":
            return False
        programme = ORNAMENT_PROGRAMMES.get(self.ornament,
                                            ORNAMENT_PROGRAMMES["none"])
        if surface not in programme["surfaces"]:
            return False
        allowance = {
            "restrained": ("title_rule", "section_rule"),
            "moderate": ("title_rule", "section_rule", "header_band",
                         "drop_cap"),
            "rich": ("title_rule", "section_rule", "header_band", "drop_cap",
                     "cover", "page_edge"),
        }.get(self.decoration, ())
        return surface in allowance

    def motifs(self) -> tuple:
        if self.decoration == "none":
            return ()
        return ORNAMENT_PROGRAMMES.get(
            self.ornament, ORNAMENT_PROGRAMMES["none"])["motifs"]

    def describe(self) -> str:
        """A block the agent prints so the design is auditable, not magic."""
        lines = [
            "Design system: %s (%s)" % (self.meta.get("label", "?"), self.nuance),
            "  ground     : %s %s   text %s"
            % ("DARK" if self.dark else "light",
               self.palette.background.hex, self.palette.text.hex),
            "  primary    : %s   secondary %s   accent %s"
            % (self.palette.primary.hex, self.palette.secondary.hex,
               self.palette.accent.hex),
            "  gradient   : %s → %s"
            % (self.palette.cover_from.hex, self.palette.cover_to.hex),
            "  type       : %s display / %s body / %s mono%s"
            % (self.fonts["display_family"], self.fonts["body_family"],
               self.fonts["mono_family"],
               "  (DEGRADED — some faces unavailable)"
               if self.fonts.get("degraded") else ""),
            "  scale      : base %.1fpt ratio %.3f → h1 %.1f h2 %.1f h3 %.1f "
            "h4 %.1f" % (self.scale.base, self.scale.ratio, self.sizes["h1"],
                         self.sizes["h2"], self.sizes["h3"], self.sizes["h4"]),
            "  ornament   : %s programme, budget=%s, motifs=%s"
            % (self.ornament, self.decoration,
               ", ".join(self.motifs()) or "none"),
            "  page       : %s %s, margins %.0fmm, justified=%s"
            % (self.page.get("size", "A4"), self.page.get("orientation",
                                                          "portrait"),
               self.page.get("margin_mm", 18), self.justify),
            "  seed       : %s" % (self.meta.get("seed") or "(theme palette)"),
        ]
        failing = [row for row in self.palette.contrast_report()
                   if not row["pass"]]
        if failing:
            lines.append("  ⚠ contrast still failing after validation:")
            for row in failing:
                lines.append("      %s %.2f < %.1f (%s on %s)"
                             % (row["check"], row["ratio"], row["floor"],
                                row["fg"], row["bg"]))
        else:
            lines.append("  contrast   : every text role clears its WCAG floor")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "nuance": self.nuance,
            "label": self.meta.get("label", ""),
            "dark": self.dark,
            "palette": self.palette.as_dict(),
            "fonts": {k: v for k, v in self.fonts.items()
                      if k.endswith("_family") or k in ("note", "degraded",
                                                        "requested")},
            "sizes": self.sizes,
            "spacing": self.spacing,
            "ornament": self.ornament,
            "motifs": list(self.motifs()),
            "decoration": self.decoration,
            "page": self.page,
            "seed": self.meta.get("seed", ""),
            "source": self.meta.get("source", ""),
        }


def _spacing_for(scale: "ptypo.TypeScale", airy: float = 1.0) -> dict:
    """Vertical rhythm derived from the type scale, not typed in.

    Every gap is a multiple of the body leading, so changing the base size
    rescales the whole document's breathing coherently instead of leaving
    9pt gaps around 14pt text.
    """
    unit = scale.leading(scale.base)
    return {
        "unit": round(unit, 2),
        "para_after": round(unit * 0.42 * airy, 2),
        "h1_before": round(unit * 1.30 * airy, 2),
        "h1_after": round(unit * 0.55 * airy, 2),
        "h2_before": round(unit * 1.05 * airy, 2),
        "h2_after": round(unit * 0.42 * airy, 2),
        "h3_before": round(unit * 0.85 * airy, 2),
        "h3_after": round(unit * 0.32 * airy, 2),
        "h4_before": round(unit * 0.70 * airy, 2),
        "h4_after": round(unit * 0.26 * airy, 2),
        "block_before": round(unit * 0.62 * airy, 2),
        "block_after": round(unit * 0.62 * airy, 2),
        "list_indent": round(unit * 1.05, 2),
        "list_gap": round(unit * 0.18, 2),
        "table_before": round(unit * 0.75 * airy, 2),
        "table_after": round(unit * 0.75 * airy, 2),
        "figure_gap": round(unit * 0.85 * airy, 2),
        "cell_padding": round(max(3.0, unit * 0.36), 2),
        "rule_gap": round(unit * 0.30, 2),
    }


def build_design_system(verdict, config=None, font_book=None,
                        logger=None) -> "DesignSystem":
    """Assemble the complete design system. NEVER raises.

    Precedence, highest first — a later stage may only refine what an earlier
    one decided, never silently ignore it:

    1. **Explicit per-role overrides** from config (``accent_color``,
       ``font_pairing``, ``page_size``…). The user asked by name.
    2. **``predominant_color``** — re-derives the whole palette from the seed,
       keeping the theme's dark/light character and intensity register.
    3. **The theme for the detected/declared nuance.**
    4. **``minimal_note``** as the floor.

    And then, unconditionally, `Palette.validated()`.
    """
    config = config or {}
    try:
        return _build_inner(verdict, config, font_book, logger)
    except Exception as exc:
        if logger:
            try:
                logger("⚠️ design assembly failed (%s: %s) — falling back to "
                       "the plain treatment, which is always safe"
                       % (type(exc).__name__, exc))
            except Exception:
                pass
        book = font_book or ptypo.FontBook()
        theme = THEMES["minimal_note"]
        scale = ptypo.TypeScale(10.5, 1.25, 1.48)
        return DesignSystem(
            nuance="minimal_note",
            palette=pc.Palette(name="plain", dark=False, **theme["palette"]).validated(),
            fonts=book.pairing("neutral"), scale=scale,
            spacing=_spacing_for(scale), ornament="none", decoration="none",
            page={"size": "A4", "orientation": "portrait", "margin_mm": 18,
                  "justify": False},
            meta={"label": "Plain (fallback)", "source": "fallback",
                  "error": "%s: %s" % (type(exc).__name__, exc)})


def _cfg(config, key, default=""):
    value = config.get(key, default)
    return default if value is None else value


def _as_bool(raw, default):
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in ("true", "yes", "1", "on", "si", "sí"):
        return True
    if text in ("false", "no", "0", "off"):
        return False
    return default


def _build_inner(verdict, config, font_book, logger):
    book = font_book or ptypo.FontBook(logger=logger)
    nuance = verdict.nuance if verdict else "minimal_note"
    theme = THEMES.get(nuance) or THEMES["minimal_note"]
    meta = {"label": theme.get("label", nuance), "source": "theme",
            "note": theme.get("note", ""), "seed": ""}

    # ── 1. dark/light ───────────────────────────────────────────────────
    dark = bool(theme.get("dark", False))
    forced_dark = str(_cfg(config, "background_mode", "auto")).strip().lower()
    if forced_dark in ("dark", "oscuro", "night"):
        dark, meta["source"] = True, "theme+background_mode"
    elif forced_dark in ("light", "claro", "day", "white"):
        dark, meta["source"] = False, "theme+background_mode"

    # ── 2. palette: theme's own, or derived from the seed ───────────────
    seed_raw = str(_cfg(config, "predominant_color", "")).strip()
    if seed_raw:
        # The theme still owns the CHARACTER: intensity (how saturated) and
        # warmth (how tinted the neutrals are) come from what kind of
        # document this is, so one colour gives a restrained legal page and a
        # loud brochure rather than the same page twice.
        register = {
            "legal_instrument": (0.55, 0.05), "medical_clinical": (0.70, 0.05),
            "financial_ledger": (0.65, 0.05), "academic_paper": (0.60, 0.05),
            "government_policy": (0.70, 0.08), "engineering_spec": (0.85, 0.05),
            "business_report": (0.90, 0.08), "software_manual": (1.00, 0.05),
            "data_analysis": (1.05, 0.05), "scientific_dark": (1.15, 0.10),
            "security_briefing": (1.15, 0.08), "editorial_feature": (1.00, 0.45),
            "creative_literary": (0.85, 0.55), "historical_archive": (0.80, 0.60),
            "culinary_recipe": (1.10, 0.50), "personal_letter": (0.75, 0.45),
            "educational_course": (1.05, 0.30),
            "marketing_brochure": (1.35, 0.10),
            "presentation_deck": (1.30, 0.08),
        }.get(nuance, (1.0, 0.15))
        palette = pc.palette_from_seed(
            seed_raw, dark=dark, name="%s+seed" % nuance,
            intensity=register[0], warmth=register[1])
        meta["seed"] = pc.parse_color(seed_raw, "#1F4E79").hex
        meta["source"] = "predominant_color seed on the %s register" % nuance
        if logger:
            try:
                logger("🎨 predominant_color=%s → palette derived on the %s "
                       "register (intensity %.2f, warmth %.2f)"
                       % (meta["seed"], nuance, register[0], register[1]))
            except Exception:
                pass
    else:
        base = dict(theme["palette"])
        if dark != bool(theme.get("dark", False)):
            # The user flipped the ground but the theme has only one hand-
            # picked palette. Re-derive from the theme's own primary so the
            # identity survives the flip.
            palette = pc.palette_from_seed(base.get("primary", "#2C4A6E"),
                                           dark=dark, name="%s+flip" % nuance)
        else:
            palette = pc.Palette(name=nuance, dark=dark, **base)

    # ── 3. explicit per-role overrides ──────────────────────────────────
    overrides = {}
    for key, role in (("accent_color", "accent"),
                      ("text_color", "text"),
                      ("background_color", "background"),
                      ("heading_color", "heading_1"),
                      ("link_color", "link"),
                      ("table_header_color", "table_header_bg"),
                      ("rule_color", "rule")):
        raw = str(_cfg(config, key, "")).strip()
        if raw:
            overrides[role] = pc.parse_color(raw, palette.get(role).hex)
    if overrides:
        if "heading_1" in overrides:
            head = overrides["heading_1"]
            overrides.setdefault("heading_2", head)
            overrides.setdefault("heading_3", head.darken(0.05) if not dark
                                 else head.lighten(0.05))
        if "background" in overrides:
            ground = overrides["background"]
            overrides.setdefault("background_alt",
                                 ground.darken(0.03) if not ground.is_dark
                                 else ground.lighten(0.03))
            palette = palette.copy_with(dark=ground.is_dark)
            dark = ground.is_dark
        palette = palette.copy_with(**overrides)
        meta["source"] += " + %d explicit override(s)" % len(overrides)

    # ── 4. typography ───────────────────────────────────────────────────
    pairing_name = str(_cfg(config, "font_pairing", "")).strip().lower()
    if pairing_name not in ptypo.PAIRINGS:
        pairing_name = theme.get("pairing", "neutral")
    fonts = book.pairing(pairing_name)

    scale_spec = theme.get("scale", {"base": 10.5, "ratio": 1.25,
                                     "leading": 1.48})
    try:
        base_size = float(_cfg(config, "font_size", 0) or 0) or scale_spec["base"]
    except Exception:
        base_size = scale_spec["base"]
    try:
        ratio = float(_cfg(config, "scale_ratio", 0) or 0) or scale_spec["ratio"]
    except Exception:
        ratio = scale_spec["ratio"]
    scale = ptypo.TypeScale(base_size, ratio, scale_spec.get("leading", 1.48))

    # ── 5. ornament, capped by the verdict's budget ─────────────────────
    programme = str(_cfg(config, "ornament", "")).strip().lower()
    if programme not in ORNAMENT_PROGRAMMES:
        programme = theme.get("ornament", "none")

    budget = verdict.decoration_budget if verdict else "restrained"
    requested = str(_cfg(config, "decorations", "auto")).strip().lower()
    if requested in pn.DECORATION_LEVELS:
        # An explicit request may only ever LOWER the ceiling the content
        # safety analysis set. Angela asked for ornament "if it knows that is
        # plenty safe" — a config flag is not new knowledge about the content.
        budget = min(requested, budget,
                     key=lambda level: pn.DECORATION_LEVELS.index(level))
    elif requested in ("off", "no", "false", "none"):
        budget = "none"

    # ── 6. page ─────────────────────────────────────────────────────────
    page = {
        "size": str(_cfg(config, "page_size", "A4")).strip() or "A4",
        "orientation": (str(_cfg(config, "orientation", "portrait")).strip()
                        .lower() or "portrait"),
        "margin_mm": _cfg(config, "margins_mm", 18),
        "justify": _as_bool(_cfg(config, "justify", theme.get("justify", False)),
                            theme.get("justify", False)),
    }
    try:
        page["margin_mm"] = max(4.0, min(60.0, float(page["margin_mm"])))
    except Exception:
        page["margin_mm"] = 18.0
    if page["orientation"] not in ("portrait", "landscape"):
        page["orientation"] = "portrait"

    airy = {"legal_instrument": 1.05, "creative_literary": 1.15,
            "editorial_feature": 1.10, "financial_ledger": 0.80,
            "engineering_spec": 0.85, "presentation_deck": 1.20}.get(nuance, 1.0)

    return DesignSystem(
        nuance=nuance,
        palette=palette.validated(),       # ← the non-negotiable last step
        fonts=fonts, scale=scale, spacing=_spacing_for(scale, airy),
        ornament=programme, decoration=budget, page=page, meta=meta)
