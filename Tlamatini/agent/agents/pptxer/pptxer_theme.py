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
# pptxer_theme.py — the DESIGN SYSTEM: nuance + seed colour → a complete,
# validated, machine-usable specification for every slide in the deck.
#
# Sibling module of pptxer.py. Stdlib + the sibling modules pptxer_color,
# pptxer_fonts, pptxer_nuance, pptxer_layout. Imports nothing from agent.*.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT A THEME IS HERE
# ─────────────────────────────────────────────────────────────────────────────
# Not "a colour and a font". A Theme carries:
#   · 44 named COLOUR ROLES, every text role already contrast-corrected against
#     the exact ground it will sit on;
#   · three RESOLVED font faces (display / body / mono) that exist on THIS
#     machine and can therefore be measured;
#   · a modular TYPE SCALE with explicit sizes for every slide role;
#   · SPACING, margins and gutters in EMU;
#   · a SHAPE LANGUAGE (corner radius, stroke weights, shadow, glow);
#   · the ORNAMENT programme and its safety ceiling;
#   · per-LAYOUT recipes that say how each kind of slide is built.
#
# ─────────────────────────────────────────────────────────────────────────────
# THE ORDER OF OPERATIONS IS LOAD-BEARING  (PDFer contract, restated)
# ─────────────────────────────────────────────────────────────────────────────
#   1. the nuance proposes a palette;
#   2. a `predominant_color` seed, if given, REPLACES the hue family;
#   3. per-role overrides from the user are applied;
#   4. a model consultation may adjust roles (validated first);
#   5. ⚠️ `validate()` runs LAST, ALWAYS, and forces every text role over its
#      contrast floor.
#
# Step 5 is not negotiable and is not a style opinion. A theme author — human
# or model — picks hues; legibility is a property of the projected result. If
# validation ran before the overrides, a single user colour could make the deck
# unreadable and nothing downstream would notice.

from pptxer_color import (
    BODY_CONTRAST_FLOOR,
    CONTRAST_SAFETY,
    DISPLAY_CONTRAST_FLOOR,
    NON_TEXT_CONTRAST_FLOOR,
    Color,
    contrast_ratio,
    darken,
    derive_palette_from_seed,
    ensure_contrast,
    gradient_stops,
    is_dark,
    lighten,
    mix_oklab,
    parse_color,
    rotate_hue,
    saturate,
)
from pptxer_color import srgb_to_oklab as _srgb_to_oklab
from pptxer_fonts import get_inventory, resolve_pairing
from pptxer_layout import EMU_PER_POINT, modular_scale
from pptxer_nuance import NUANCES, SAFETY_CRITICAL_NUANCES, decoration_ceiling_for

__all__ = ["Theme", "build_theme", "LAYOUT_RECIPES", "TYPE_ROLES"]


def srgb_to_oklab_lightness(color) -> float:
    """OKLab L only — the perceptual lightness used to pick a worst-case ground."""
    return _srgb_to_oklab(color)[0]


# ─────────────────────────────────────────────────────────────────────────────
# Type roles. Multipliers against the modular scale, so a change of base size
# or ratio moves the whole hierarchy together instead of drifting apart.
# ─────────────────────────────────────────────────────────────────────────────

TYPE_ROLES = {
    "mega":      {"step": 6, "face": "display", "bold": True,  "spacing": -0.02},
    "title":     {"step": 5, "face": "display", "bold": True,  "spacing": -0.01},
    "subtitle":  {"step": 3, "face": "body",    "bold": False, "spacing": 0.0},
    "heading":   {"step": 4, "face": "display", "bold": True,  "spacing": -0.01},
    "subheading": {"step": 2, "face": "body",   "bold": True,  "spacing": 0.0},
    "body":      {"step": 1, "face": "body",    "bold": False, "spacing": 0.0},
    "bullet":    {"step": 1, "face": "body",    "bold": False, "spacing": 0.0},
    "caption":   {"step": 0, "face": "body",    "bold": False, "spacing": 0.01},
    "footnote":  {"step": 0, "face": "body",    "bold": False, "spacing": 0.01},
    "quote":     {"step": 3, "face": "display", "bold": False, "spacing": 0.0},
    "stat_value": {"step": 6, "face": "display", "bold": True, "spacing": -0.03},
    "stat_label": {"step": 0, "face": "body",   "bold": True,  "spacing": 0.08},
    "code":      {"step": 0, "face": "mono",    "bold": False, "spacing": 0.0},
    "kicker":    {"step": 0, "face": "body",    "bold": True,  "spacing": 0.14},
    "table":     {"step": 0, "face": "body",    "bold": False, "spacing": 0.0},
    "table_head": {"step": 0, "face": "body",   "bold": True,  "spacing": 0.04},
    "label":     {"step": 0, "face": "body",    "bold": True,  "spacing": 0.02},
}

# Minimum readable size per role, in points, for a PROJECTED slide.
# 18pt is the widely-taught floor for body text in a room; PPTXer refuses to go
# below it for body copy and warns instead, because going smaller does not make
# the content fit — it makes it unreadable, which is the same as losing it.
_ROLE_MIN_PT = {
    "mega": 44.0, "title": 30.0, "subtitle": 20.0, "heading": 24.0,
    "subheading": 18.0, "body": 16.0, "bullet": 16.0, "caption": 11.0,
    "footnote": 10.0, "quote": 20.0, "stat_value": 36.0, "stat_label": 11.0,
    "code": 12.0, "kicker": 11.0, "table": 11.0, "table_head": 11.0,
    "label": 11.0,
}

# Density → base body size and how much the deck is allowed to say per slide.
_DENSITY = {
    "minimal": {"base_pt": 24.0, "ratio": 1.5,   "max_bullets": 3,  "max_words": 28},
    "low":     {"base_pt": 21.0, "ratio": 1.414, "max_bullets": 5,  "max_words": 55},
    "medium":  {"base_pt": 18.0, "ratio": 1.333, "max_bullets": 6,  "max_words": 95},
    "high":    {"base_pt": 16.0, "ratio": 1.25,  "max_bullets": 8,  "max_words": 150},
}

# ─────────────────────────────────────────────────────────────────────────────
# Layout recipes — how each KIND of slide is composed.
#
# The builder reads these; they are data, not code, so a new nuance can
# re-weight the deck's rhythm without touching the builder.
# ─────────────────────────────────────────────────────────────────────────────

LAYOUT_RECIPES = {
    "title_slide":    {"regions": ("full",),        "art": "hero",    "text_align": "left"},
    "section_break":  {"regions": ("full",),        "art": "band",    "text_align": "left"},
    "statement":      {"regions": ("full",),        "art": "subtle",  "text_align": "center"},
    "bullets":        {"regions": ("header", "body"), "art": "corner", "text_align": "left"},
    "two_column":     {"regions": ("header", "left", "right"), "art": "none",
                       "text_align": "left"},
    "image_left":     {"regions": ("header", "image", "text"), "art": "none",
                       "text_align": "left"},
    "image_right":    {"regions": ("header", "text", "image"), "art": "none",
                       "text_align": "left"},
    "image_full":     {"regions": ("bleed", "overlay"), "art": "scrim",
                       "text_align": "left"},
    "quote":          {"regions": ("full",),        "art": "subtle",  "text_align": "center"},
    "stats":          {"regions": ("header", "tiles"), "art": "corner",
                       "text_align": "center"},
    "comparison":     {"regions": ("header", "left", "right"), "art": "none",
                       "text_align": "left"},
    "timeline":       {"regions": ("header", "body"), "art": "none",  "text_align": "left"},
    "table":          {"regions": ("header", "body"), "art": "none",  "text_align": "left"},
    "chart":          {"regions": ("header", "body"), "art": "none",  "text_align": "left"},
    "diagram":        {"regions": ("header", "body"), "art": "none",  "text_align": "center"},
    "gallery":        {"regions": ("header", "grid"), "art": "none",  "text_align": "center"},
    "media":          {"regions": ("header", "body"), "art": "none",  "text_align": "center"},
    "code":           {"regions": ("header", "body"), "art": "none",  "text_align": "left"},
    "closing":        {"regions": ("full",),        "art": "hero",    "text_align": "center"},
    "agenda":         {"regions": ("header", "body"), "art": "corner",
                       "text_align": "left"},
}


class Theme:
    """A complete, validated slide design system."""

    def __init__(self, nuance_key, palette, fonts, scale, spacing, shape,
                 ornament, decoration, density, background_mode, meta=None):
        self.nuance = nuance_key
        self.palette = palette            # {role: Color}
        self.fonts = fonts                # {'display','body','mono'} ResolvedFont
        self.scale = scale                # {role: size_pt}
        self.spacing = spacing            # {name: emu}
        self.shape = shape                # {name: value}
        self.ornament = ornament
        self.decoration = decoration      # 'none'|'restrained'|'moderate'|'rich'
        self.density = density
        self.background_mode = background_mode
        self.meta = meta or {}
        self._validation = []
        self._role_fonts = {}

    # -- accessors ------------------------------------------------------------

    def color(self, role, default="#808080") -> Color:
        c = self.palette.get(role)
        if c is None:
            c = parse_color(default) or Color(0.5, 0.5, 0.5)
        return c

    def hex(self, role, default="#808080") -> str:
        """Hex WITHOUT '#', ready for python-pptx RGBColor.from_string."""
        return self.color(role, default).hex_rrggbb

    def size(self, role, default=18.0) -> float:
        return float(self.scale.get(role, default))

    def font_for(self, role):
        face = TYPE_ROLES.get(role, {}).get("face", "body")
        base = self.fonts.get(face) or self.fonts.get("body")
        if base is None:
            return None
        key = (role, base.family, base.path, self.is_bold(role), self.letter_spacing(role))
        if key not in self._role_fonts:
            from copy import copy
            resolved = copy(get_inventory().resolve(base.family, base.category,
                                                    bold=self.is_bold(role), italic=base.italic))
            resolved.tracking_em = self.letter_spacing(role)
            self._role_fonts[key] = resolved
        return self._role_fonts[key]

    def is_bold(self, role) -> bool:
        return bool(TYPE_ROLES.get(role, {}).get("bold", False))

    def letter_spacing(self, role) -> float:
        return float(TYPE_ROLES.get(role, {}).get("spacing", 0.0))

    def space(self, name, default_pt=12.0) -> int:
        return int(self.spacing.get(name, default_pt * EMU_PER_POINT))

    @property
    def is_dark(self) -> bool:
        return is_dark(self.color("ground"))

    @property
    def decorations_allowed(self) -> bool:
        return self.decoration != "none"

    @property
    def validation_notes(self) -> list:
        return list(self._validation)

    # -- gradients ------------------------------------------------------------

    def gradient(self, name="hero", steps=10) -> list:
        """A named multi-stop OKLab gradient.

        Emitting MANY stops is the trick that makes PowerPoint gradients look
        expensive: PowerPoint interpolates in sRGB between whatever stops it is
        given, so short hops between pre-corrected OKLab stops never pass
        through the muddy middle a two-stop fill would.
        """
        pal = self.palette
        if name == "hero":
            return gradient_stops(pal["accent"], pal["accent_2"], steps,
                                  via=pal.get("accent_3"))
        if name == "ground":
            return gradient_stops(pal["ground_deep"], pal["ground"], steps)
        if name == "accent":
            return gradient_stops(pal["accent"], pal["accent_2"], steps)
        if name == "scrim":
            base = pal["ground_deep"]
            return [base.with_alpha(a / 100.0) for a in (0, 18, 42, 66, 86, 96)]
        if name == "surface":
            return gradient_stops(pal["surface"], pal["surface_high"], steps)
        return gradient_stops(pal["accent"], pal["accent_2"], steps)

    # -- the final guarantee --------------------------------------------------

    def validate(self) -> list:
        """Force EVERY text role over its contrast floor. Runs LAST, always.

        Returns the list of repairs made, so the agent can report exactly which
        colours it had to move and why — a designer will accept an enforced
        change they can see explained, and will rightly distrust a silent one.
        """
        notes = []
        # ⚠️ VALIDATE AGAINST THE WORST GROUND THE TEXT CAN ACTUALLY LAND ON,
        # NOT THE NOMINAL ONE.
        #
        # Measured 2026-09-14, first integration run: every text role cleared
        # 7:1 against the flat `ground` (#001308) and the PowerPoint render
        # still measured bullets at 6.19:1 and footers at 5.71:1. The reason is
        # that the slide's real background is a GENERATED GRADIENT with an
        # ornament composited over it, so the pixels behind the text are
        # lighter than the nominal ground by a margin nobody declared.
        #
        # This is the PDFer failure in a new costume: the design's own opinion
        # of itself is not evidence. So the floor is enforced against
        # `ground_worst` — the lightest ground a dark deck can produce (or the
        # darkest a light deck can), including the ornament's contribution.
        ground = self.color("ground_worst", self.color("ground").hex)
        surface = self.color("surface_high", self.color("surface").hex)
        accent = self.color("accent")

        checks = (
            # (role, background, floor, label)
            ("text", ground, BODY_CONTRAST_FLOOR, "body text"),
            ("text_muted", ground, DISPLAY_CONTRAST_FLOOR, "muted text"),
            ("title", ground, DISPLAY_CONTRAST_FLOOR, "title"),
            ("heading", ground, DISPLAY_CONTRAST_FLOOR, "heading"),
            ("subtitle", ground, DISPLAY_CONTRAST_FLOOR, "subtitle"),
            ("on_surface", surface, BODY_CONTRAST_FLOOR, "text on panels"),
            ("on_accent", accent, DISPLAY_CONTRAST_FLOOR, "text on the accent"),
            ("caption", ground, BODY_CONTRAST_FLOOR, "captions"),
            ("footer", ground, BODY_CONTRAST_FLOOR, "footer"),
            ("stat_value", ground, DISPLAY_CONTRAST_FLOOR, "stat values"),
            ("stat_label", ground, BODY_CONTRAST_FLOOR, "stat labels"),
            ("code_text", self.color("code_bg", "#101014"),
             BODY_CONTRAST_FLOOR, "code"),
            ("table_text", surface, BODY_CONTRAST_FLOOR, "table cells"),
            ("table_head_text", self.color("table_head_bg", accent.hex),
             DISPLAY_CONTRAST_FLOOR, "table headers"),
            ("rule", ground, NON_TEXT_CONTRAST_FLOOR, "rules"),
            ("link", ground, BODY_CONTRAST_FLOOR, "links"),
            ("kicker", ground, BODY_CONTRAST_FLOOR, "kickers"),
            ("accent_text", ground, BODY_CONTRAST_FLOOR, "accent labels"),
            ("accent_text", surface, BODY_CONTRAST_FLOOR, "accent labels on panels"),
        )

        for role, bg, floor, label in checks:
            if role not in self.palette:
                continue
            before = self.color(role)
            ratio = contrast_ratio(before, bg)
            if ratio >= floor * CONTRAST_SAFETY:
                continue
            after = ensure_contrast(before, bg, floor)
            self.palette[role] = after
            notes.append(
                f"{label}: {before.hex} on {parse_color(bg).hex} measured "
                f"{ratio:.2f}:1, below the {floor:.1f}:1 floor for a projected "
                f"slide — corrected to {after.hex} ({contrast_ratio(after, bg):.2f}:1), "
                f"keeping the hue"
            )

        # Captions and footnotes take the FULL body floor, deliberately. They
        # are the SMALLEST type in the deck and therefore the first thing lost
        # at the back of a room; giving them a lower floor because they are
        # "secondary" is exactly backwards.
        self._validation = notes
        return notes

    def as_dict(self) -> dict:
        return {
            "nuance": self.nuance,
            "decoration": self.decoration,
            "ornament": self.ornament,
            "density": self.density,
            "background_mode": self.background_mode,
            "dark": self.is_dark,
            "fonts": {
                "display": self.fonts["display"].family,
                "body": self.fonts["body"].family,
                "mono": self.fonts["mono"].family,
                "substitutions": self.meta.get("font_substitutions", []),
            },
            "palette": {k: v.hex for k, v in sorted(self.palette.items())},
            "scale": dict(sorted(self.scale.items())),
            "validation": self._validation,
        }

    def describe(self) -> str:
        """A short human account of the design. Printed into the agent log."""
        spec = NUANCES.get(self.nuance, {})
        lines = [
            f"Treatment    : {spec.get('label', self.nuance)} "
            f"({'dark' if self.is_dark else 'light'} ground)",
            f"Register     : {spec.get('register', '—')}",
            f"Type         : {self.fonts['display'].family} display / "
            f"{self.fonts['body'].family} body / {self.fonts['mono'].family} mono",
            f"Sizes        : title {self.size('title'):.0f}pt · "
            f"body {self.size('body'):.0f}pt · caption {self.size('caption'):.0f}pt",
            f"Palette      : ground {self.color('ground').hex} · "
            f"text {self.color('text').hex} · accent {self.color('accent').hex} · "
            f"accent2 {self.color('accent_2').hex}",
            f"Decoration   : {self.decoration} (ornament: {self.ornament})",
            f"Density      : {self.density} "
            f"(<= {self.meta.get('max_bullets', 6)} bullets/slide)",
        ]
        if self.meta.get("font_substitutions"):
            for note in self.meta["font_substitutions"]:
                lines.append(f"Font note    : {note}")
        if self._validation:
            for note in self._validation:
                lines.append(f"Contrast fix : {note}")
        return "\n".join(lines)


def build_theme(verdict, config=None, inventory=None) -> Theme:
    """Build the deck's Theme from the nuance verdict plus the user's settings.

    `config` keys honoured (all optional, all winning over the nuance):
      predominant_color · accent_color · text_color · background_color ·
      heading_color · link_color · table_header_color · rule_color ·
      background_mode · font_pairing · font_size · scale_ratio ·
      decorations · ornament · density
    """
    cfg = config or {}
    inv = inventory or get_inventory()
    nuance_key = verdict.nuance if hasattr(verdict, "nuance") else str(verdict)
    spec = NUANCES.get(nuance_key, NUANCES["corporate_update"])

    # ---- 1. ground mode ----------------------------------------------------
    mode = str(cfg.get("background_mode") or "").strip().lower()
    if mode not in ("dark", "light"):
        mode = spec.get("background_mode", "light")
    explicit_bg = parse_color(cfg.get("background_color"))
    # A new seed or background mode keeps the user's palette in control.
    use_style_palette = not cfg.get("predominant_color") and mode == spec.get("background_mode")
    if explicit_bg is None and use_style_palette:
        explicit_bg = parse_color(spec.get("background_color"))
    if explicit_bg is not None:
        mode = "dark" if is_dark(explicit_bg) else "light"
    dark = (mode == "dark")

    # ---- 2. palette: nuance default, then the seed if the user gave one ----
    seed = parse_color(cfg.get("predominant_color")) or parse_color(
        spec.get("palette_seed", "#2F5D8C"))
    palette = derive_palette_from_seed(seed, dark_ground=dark)
    if use_style_palette:
        for role, value in spec.get("palette_roles", {}).items():
            color = parse_color(value)
            if color is not None:
                palette[role] = color
        if spec.get("visual_style") and not dark:
            # New light styles use white labels on accent-filled table headers
            # and diagram nodes. Reserve the small-text floor plus render headroom.
            palette["accent"] = ensure_contrast(palette["accent"], Color(1, 1, 1), 8.0)
            palette["on_accent"] = Color(1, 1, 1)

    if explicit_bg is not None:
        palette["ground"] = explicit_bg
        palette["ground_deep"] = darken(explicit_bg, 0.06) if dark else darken(explicit_bg, 0.04)
        palette["surface"] = (lighten(explicit_bg, 0.07) if dark
                              else darken(explicit_bg, 0.035))
        palette["surface_high"] = (lighten(explicit_bg, 0.13) if dark
                                   else darken(explicit_bg, 0.07))

    # ---- 3. the extra roles a SLIDE needs that a page does not -------------
    accent = palette["accent"]
    ground = palette["ground"]
    surface = palette["surface"]

    palette.setdefault("heading", palette["title"])
    palette.setdefault("subtitle", palette["text_muted"])
    palette.setdefault("caption", palette["text_muted"])
    palette.setdefault("footer", palette["text_muted"])
    palette.setdefault("link", palette["accent"])
    palette.setdefault("kicker", palette["accent"])
    palette.setdefault("accent_text", palette["accent"])
    palette.setdefault("quote", palette["text"])
    palette.setdefault("stat_value", palette["accent"])
    palette.setdefault("stat_label", palette["text_muted"])
    palette.setdefault("code_bg", darken(ground, 0.05) if dark else Color(0.96, 0.96, 0.97))
    palette.setdefault("code_text", palette["text"])
    palette.setdefault("code_keyword", palette["accent_2"])
    palette.setdefault("table_head_bg", accent)
    palette.setdefault("table_head_text", palette["on_accent"])
    palette.setdefault("table_text", palette["on_surface"])
    palette.setdefault("table_row_alt", mix_oklab(surface, ground, 0.45))
    palette.setdefault("table_border", palette["rule"])
    palette.setdefault("shadow", Color(0, 0, 0, 0.45 if dark else 0.18))
    palette.setdefault("glow", saturate(accent, 1.4))
    palette.setdefault("scrim", darken(ground, 0.10).with_alpha(0.72))
    palette.setdefault("panel_border", mix_oklab(surface, accent, 0.28))
    palette.setdefault("bullet_marker", accent)
    palette.setdefault("divider", palette["rule"])
    palette.setdefault("chart_grid", mix_oklab(ground, palette["text"], 0.18))
    palette.setdefault("chart_axis", palette["text_muted"])

    # (ground_worst is computed AFTER the decoration level is resolved — see
    #  below — because it depends on how much ornament is actually allowed.)

    # A categorical series for charts and diagrams, spaced around the hue wheel
    # so adjacent series never look like the same colour under a projector.
    for i, deg in enumerate((0, 48, 96, 204, 264, 312, 156, 24)):
        palette.setdefault(f"series_{i + 1}",
                           ensure_contrast(rotate_hue(saturate(accent, 1.12), deg),
                                           ground, NON_TEXT_CONTRAST_FLOOR))

    # ---- 4. per-role user overrides (BEFORE validation) -------------------
    for cfg_key, role in (
        ("accent_color", "accent"), ("text_color", "text"),
        ("heading_color", "heading"), ("link_color", "link"),
        ("table_header_color", "table_head_bg"), ("rule_color", "rule"),
    ):
        override = parse_color(cfg.get(cfg_key))
        if override is not None:
            palette[role] = override
            if role == "accent":
                palette["title"] = override
                palette["kicker"] = override
                palette["accent_text"] = override
                palette["stat_value"] = override
                palette["bullet_marker"] = override
                palette["on_accent"] = ensure_contrast(
                    palette.get("on_accent", Color(1, 1, 1)), override,
                    DISPLAY_CONTRAST_FLOOR)
            if role == "table_head_bg":
                palette["table_head_text"] = ensure_contrast(
                    palette.get("table_head_text", Color(1, 1, 1)), override,
                    DISPLAY_CONTRAST_FLOOR)

    # ---- 5. fonts ----------------------------------------------------------
    pairing_name = (str(cfg.get("font_pairing") or "").strip()
                    or spec.get("pairing", "corporate"))
    pairing = resolve_pairing(pairing_name, inv)
    fonts = {"display": pairing["display"], "body": pairing["body"],
             "mono": pairing["mono"]}

    # ---- 6. type scale -----------------------------------------------------
    density = str(cfg.get("density") or spec.get("density", "medium")).lower()
    if density not in _DENSITY:
        density = "medium"
    dspec = _DENSITY[density]

    try:
        base_pt = float(cfg.get("font_size") or 0) or dspec["base_pt"]
    except (TypeError, ValueError):
        base_pt = dspec["base_pt"]
    try:
        ratio = float(cfg.get("scale_ratio") or 0) or dspec["ratio"]
    except (TypeError, ValueError):
        ratio = dspec["ratio"]

    steps = modular_scale(base_pt, ratio, 8)
    scale = {}
    for role, rspec in TYPE_ROLES.items():
        idx = min(len(steps) - 1, max(0, int(rspec["step"])))
        size = steps[idx]
        floor = _ROLE_MIN_PT.get(role, 10.0)
        scale[role] = round(max(size, floor), 1)

    # ---- 7. spacing --------------------------------------------------------
    unit = base_pt
    spacing = {
        "unit": int(unit * EMU_PER_POINT),
        "margin": int((unit * 2.6) * EMU_PER_POINT),
        "gutter": int((unit * 1.15) * EMU_PER_POINT),
        "paragraph": int((unit * 0.52) * EMU_PER_POINT),
        "bullet_gap": int((unit * 0.42) * EMU_PER_POINT),
        "section": int((unit * 1.6) * EMU_PER_POINT),
        "panel_pad": int((unit * 0.95) * EMU_PER_POINT),
        "header_gap": int((unit * 1.0) * EMU_PER_POINT),
    }
    for name, factor in spec.get("spacing_factors", {}).items():
        if name in spacing:
            spacing[name] = int(unit * factor * EMU_PER_POINT)

    # ---- 8. shape language -------------------------------------------------
    sharp = nuance_key in ("cyberpunk_tech", "military_tactical", "retro_arcade",
                           "brutalist", "esports_tournament", "legal_compliance",
                           "financial_disclosure", "research_findings")
    soft = nuance_key in ("friendly_consumer", "training_course",
                          "social_media_kit", "startup_pitch")
    shape = {
        "radius": 0 if sharp else (int(18 * EMU_PER_POINT) if soft
                                   else int(8 * EMU_PER_POINT)),
        "stroke": int(1.25 * EMU_PER_POINT),
        "stroke_heavy": int(3.0 * EMU_PER_POINT),
        "rule": int(2.0 * EMU_PER_POINT),
        "rule_hair": int(0.75 * EMU_PER_POINT),
        "shadow": dark and not sharp,
        "glow": dark and nuance_key in ("cyberpunk_tech", "esports_tournament",
                                        "game_trailer_beat", "streamer_kit",
                                        "retro_arcade"),
        "uppercase_titles": nuance_key in (
            "esports_tournament", "cyberpunk_tech", "military_tactical",
            "retro_arcade", "brand_bold", "event_keynote", "game_trailer_beat",
        ),
    }
    for name, value in spec.get("shape_defaults", {}).items():
        if name in ("radius", "rule", "stroke", "stroke_heavy", "rule_hair"):
            shape[name] = int(value * EMU_PER_POINT)
        elif name in ("uppercase_titles", "shadow", "glow"):
            shape[name] = bool(value)

    # ---- 9. decoration ceiling (can only be LOWERED) ----------------------
    decoration = decoration_ceiling_for(verdict, str(cfg.get("decorations") or "auto"))
    ornament = (str(cfg.get("ornament") or "").strip()
                or spec.get("ornament", "none"))
    if decoration == "none" or nuance_key in SAFETY_CRITICAL_NUANCES:
        ornament = "none"

    # ── ground_worst: the REAL worst case behind body text ──────────────────
    # Measured 2026-09-14: text validated against the flat `ground` still
    # rendered at 6.19:1 because the actual background is a gradient with an
    # ornament composited over it. So the floor is enforced against the worst
    # ground the text can LAND on.
    #
    # ⚠️ ESTIMATE IT ACCURATELY, NOT PESSIMISTICALLY. The first attempt used
    # the RICH alpha for every deck and produced ground_worst = #00747A on a
    # near-black slide — which forced the title from #00E89C to flat white and
    # destroyed the treatment. Over-correcting contrast is not "safe": it
    # throws away the design to satisfy a number that was never true.
    #
    # The alphas mirror pptxer_draw._INTENSITY for the decoration level ACTUALLY
    # in force; 1.5 is the largest per-motif multiplier; 0.7 is a coverage
    # factor, because an ornament covers part of the slide, not all of it.
    _orn_alpha = {"none": 0.0, "restrained": 0.12,
                  "moderate": 0.22, "rich": 0.34}.get(decoration, 0.12)
    if ornament == "none":
        _orn_alpha = 0.0
    _effective = min(0.40, _orn_alpha * 1.5 * 0.7)

    _lightness = srgb_to_oklab_lightness
    _orn_colors = (palette["accent"], palette["accent_2"], palette["accent_3"])
    _deep = palette["ground_deep"]
    if dark:
        _extreme = ground if _lightness(ground) >= _lightness(_deep) else _deep
        _blend_to = max(_orn_colors, key=_lightness)
    else:
        _extreme = ground if _lightness(ground) <= _lightness(_deep) else _deep
        _blend_to = min(_orn_colors, key=_lightness)
    palette["ground_worst"] = (mix_oklab(_extreme, _blend_to, _effective)
                               if _effective > 0 else _extreme)

    theme = Theme(
        nuance_key=nuance_key, palette=palette, fonts=fonts, scale=scale,
        spacing=spacing, shape=shape, ornament=ornament, decoration=decoration,
        density=density, background_mode=mode,
        meta={
            "base_pt": base_pt, "ratio": ratio,
            "max_bullets": dspec["max_bullets"], "max_words": dspec["max_words"],
            "pairing": pairing["pairing"], "pairing_note": pairing.get("note", ""),
            "font_substitutions": pairing.get("substitutions", []),
            "seed": seed.hex,
            "confidence": getattr(verdict, "confidence", 1.0),
        },
    )

    # ---- 10. VALIDATE LAST, ALWAYS ---------------------------------------
    theme.validate()
    return theme
