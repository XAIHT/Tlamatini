# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer typography — the type case of the document composer.

WHY THIS MODULE EXISTS
----------------------
Angela's complaint was exact: *"the same stupid font"*. Every PDF PDFer had
ever produced was set in **Helvetica**, because ``DEFAULT_CSS`` said
``font-family: Helvetica, Arial, sans-serif`` and nothing ever changed it. A
quantum-mechanics preprint, a legal notice and a dinner menu all came out
looking like a 1994 fax cover sheet.

The fix is not "add a second font". It is to give PDFer a real **type case**:
a set of registered families, a set of *pairings* chosen the way a typographer
chooses them, and a modular scale that makes a title unmistakably a title.

THE THREE THINGS THIS MODULE OWNS
---------------------------------
1. **DISCOVERY + REGISTRATION.** ReportLab ships only the PDF base-14
   (Helvetica/Times/Courier). Everything beautiful is a TrueType file sitting
   on the host. `FontBook.boot()` hunts the platform font directories, and
   for each family registers all four faces AND calls
   ``registerFontFamily`` — which is the non-obvious step that makes ``<b>``
   and ``<i>`` inside a Platypus ``Paragraph`` actually render bold and
   italic instead of silently staying regular.

2. **PAIRINGS, NOT FONTS.** A theme never names a font file. It names a
   *pairing* (``"scholarly"``, ``"technical_mono"``, ``"editorial"``), and the
   book resolves it against what this machine actually has, degrading down a
   preference chain to the base-14 floor. That is why the same theme produces
   a beautiful document on Angela's Windows box and a *correct* one on a bare
   Linux container with no fonts at all.

3. **A MODULAR SCALE.** Heading sizes are computed from one base size and one
   ratio, not typed in. Angela asked for "perfect differentiated titles,
   sub-titles" — differentiation is a *ratio* problem. At 1.25 (major third)
   an H2 is unmistakably bigger than an H3 at every base size, and the whole
   document rescales coherently when a dense report needs 9.5pt body copy.

CONTRACTS (do NOT weaken)
-------------------------
* **FAIL-OPEN, ALWAYS.** A missing font, an unreadable TTF, a corrupt font
  directory — every one degrades to the next candidate and finally to
  Helvetica. `FontBook.boot()` cannot raise; a PDF in the wrong typeface is
  infinitely better than no PDF.
* **REGISTER ONCE PER PROCESS.** ReportLab's font registry is global and
  re-registering is wasteful, so the book memoises. It is also idempotent, so
  a second `boot()` is a cheap no-op.
* **NEVER return an unregistered font name.** Every accessor resolves through
  `resolve()`, which is guaranteed to return something ReportLab can set.
  Handing Platypus an unknown font name is a hard KeyError at render time —
  the exact class of late failure this agent must never have.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import os
import sys

__all__ = [
    "FontBook",
    "TypeScale",
    "FONT_CANDIDATES",
    "PAIRINGS",
    "BASE14_SERIF",
    "BASE14_SANS",
    "BASE14_MONO",
]

# The PDF base-14 — always present, never registered, the absolute floor.
BASE14_SERIF = "Times-Roman"
BASE14_SANS = "Helvetica"
BASE14_MONO = "Courier"

_BASE14_FAMILIES = {
    BASE14_SERIF: ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    BASE14_SANS: ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique",
                  "Helvetica-BoldOblique"),
    BASE14_MONO: ("Courier", "Courier-Bold", "Courier-Oblique",
                  "Courier-BoldOblique"),
}


# ─────────────────────────────────────────────────────────────────────────
#  The candidate table
#
#  Each entry: logical family name -> (regular, bold, italic, bold-italic)
#  file names, plus a classification used by the pairing resolver.
#
#  File names are listed WITHOUT a directory so the same table works on
#  Windows (C:\Windows\Fonts), macOS (/Library/Fonts) and Linux
#  (/usr/share/fonts, which is searched recursively). Case is normalised
#  during the scan because Windows is case-insensitive and ships a wild mix
#  of ``arial.ttf`` and ``ARIALN.TTF``.
# ─────────────────────────────────────────────────────────────────────────
FONT_CANDIDATES = {
    # ── Old-style / transitional serifs — scholarship, literature, law ──
    "Palatino": {
        "files": ("pala.ttf", "palab.ttf", "palai.ttf", "palabi.ttf",
                  "Palatino.ttc", "PalatinoLinotype-Roman.ttf"),
        "class": "serif", "voice": "scholarly", "weight_feel": "warm",
    },
    "BookAntiqua": {
        "files": ("BOOKOS.TTF", "BOOKOSB.TTF", "BOOKOSI.TTF", "BOOKOSBI.TTF"),
        "class": "serif", "voice": "scholarly", "weight_feel": "warm",
    },
    "Georgia": {
        "files": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
        "class": "serif", "voice": "editorial", "weight_feel": "sturdy",
    },
    "Cambria": {
        "files": ("cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
        "class": "serif", "voice": "technical", "weight_feel": "sturdy",
    },
    "Constantia": {
        "files": ("constan.ttf", "constanb.ttf", "constani.ttf", "constanz.ttf"),
        "class": "serif", "voice": "scholarly", "weight_feel": "refined",
    },
    "TimesNewRoman": {
        "files": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf",
                  "Times New Roman.ttf", "liberationserif-regular.ttf"),
        "class": "serif", "voice": "formal", "weight_feel": "neutral",
    },
    "Garamond": {
        "files": ("GARA.TTF", "GARABD.TTF", "GARAIT.TTF", "GARABD.TTF",
                  "EBGaramond-Regular.ttf"),
        "class": "serif", "voice": "literary", "weight_feel": "delicate",
    },
    "Sylfaen": {
        "files": ("sylfaen.ttf",), "class": "serif", "voice": "literary",
        "weight_feel": "delicate",
    },
    "Rockwell": {
        "files": ("ROCK.TTF", "ROCKB.TTF", "ROCKI.TTF", "ROCKBI.TTF"),
        "class": "slab", "voice": "assertive", "weight_feel": "heavy",
    },
    "DejaVuSerif": {
        "files": ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf",
                  "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf"),
        "class": "serif", "voice": "neutral", "weight_feel": "sturdy",
    },

    # ── Humanist / geometric sans — reports, interfaces, technical ──────
    "Calibri": {
        "files": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
        "class": "sans", "voice": "corporate", "weight_feel": "friendly",
    },
    "Candara": {
        "files": ("Candara.ttf", "Candarab.ttf", "Candarai.ttf", "Candaraz.ttf"),
        "class": "sans", "voice": "humanist", "weight_feel": "friendly",
    },
    "Corbel": {
        "files": ("corbel.ttf", "corbelb.ttf", "corbeli.ttf", "corbelz.ttf"),
        "class": "sans", "voice": "corporate", "weight_feel": "refined",
    },
    "SegoeUI": {
        "files": ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
        "class": "sans", "voice": "modern", "weight_feel": "neutral",
    },
    "Verdana": {
        "files": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
        "class": "sans", "voice": "plain", "weight_feel": "sturdy",
    },
    "Tahoma": {
        "files": ("tahoma.ttf", "tahomabd.ttf"),
        "class": "sans", "voice": "plain", "weight_feel": "neutral",
    },
    "TrebuchetMS": {
        "files": ("trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
        "class": "sans", "voice": "friendly", "weight_feel": "friendly",
    },
    "Arial": {
        "files": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf",
                  "LiberationSans-Regular.ttf"),
        "class": "sans", "voice": "neutral", "weight_feel": "neutral",
    },
    "ArialNarrow": {
        "files": ("ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF", "ARIALNBI.TTF"),
        "class": "sans", "voice": "dense", "weight_feel": "condensed",
    },
    "DejaVuSans": {
        "files": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
                  "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf"),
        "class": "sans", "voice": "neutral", "weight_feel": "sturdy",
    },
    "CenturyGothic": {
        "files": ("GOTHIC.TTF", "GOTHICB.TTF", "GOTHICI.TTF", "GOTHICBI.TTF"),
        "class": "geometric", "voice": "modern", "weight_feel": "airy",
    },

    # ── Display / headline — covers, marketing, section marks ───────────
    "FranklinGothic": {
        "files": ("framd.ttf", "framdit.ttf", "FRAMDCN.TTF"),
        "class": "display", "voice": "assertive", "weight_feel": "heavy",
    },
    "Bahnschrift": {
        "files": ("bahnschrift.ttf",),
        "class": "display", "voice": "technical", "weight_feel": "condensed",
    },
    "Impact": {
        "files": ("impact.ttf",),
        "class": "display", "voice": "loud", "weight_feel": "heavy",
    },
    "SegoeUIBlack": {
        "files": ("seguibl.ttf", "seguibli.ttf"),
        "class": "display", "voice": "modern", "weight_feel": "heavy",
    },
    "SegoeUILight": {
        "files": ("segoeuil.ttf", "seguili.ttf"),
        "class": "display", "voice": "modern", "weight_feel": "airy",
    },

    # ── Monospace — code panels, data, terminal transcripts ─────────────
    "Consolas": {
        "files": ("consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
        "class": "mono", "voice": "technical", "weight_feel": "neutral",
    },
    "CascadiaCode": {
        "files": ("CascadiaCode.ttf", "CascadiaMono.ttf",
                  "CascadiaCode-Regular.otf"),
        "class": "mono", "voice": "modern", "weight_feel": "neutral",
    },
    "LucidaConsole": {
        "files": ("lucon.ttf",),
        "class": "mono", "voice": "plain", "weight_feel": "neutral",
    },
    "CourierNew": {
        "files": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
        "class": "mono", "voice": "formal", "weight_feel": "delicate",
    },
    "DejaVuSansMono": {
        "files": ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
                  "DejaVuSansMono-Oblique.ttf",
                  "DejaVuSansMono-BoldOblique.ttf"),
        "class": "mono", "voice": "neutral", "weight_feel": "neutral",
    },
}


# ─────────────────────────────────────────────────────────────────────────
#  Pairings — a typographer's choices, expressed as preference chains
#
#  ``display`` sets titles and section heads, ``body`` sets running copy,
#  ``mono`` sets code and tabular data. Each is an ordered preference list;
#  the FIRST family present on this machine wins, and the final entry of
#  every chain is a base-14 name so resolution can never come up empty.
# ─────────────────────────────────────────────────────────────────────────
PAIRINGS = {
    # Academic paper: an old-style serif throughout, the way TeX does it.
    "scholarly": {
        "display": ("Palatino", "BookAntiqua", "Constantia", "Cambria",
                    "TimesNewRoman", "DejaVuSerif", BASE14_SERIF),
        "body": ("Palatino", "BookAntiqua", "Constantia", "TimesNewRoman",
                 "DejaVuSerif", BASE14_SERIF),
        "mono": ("Consolas", "CourierNew", "DejaVuSansMono", BASE14_MONO),
        "note": "Old-style serif set throughout, in the tradition of a "
                "typeset journal article.",
    },
    # Science & technology: condensed technical display over a clean sans.
    "technical": {
        "display": ("Bahnschrift", "FranklinGothic", "SegoeUI", "Corbel",
                    "Arial", BASE14_SANS),
        "body": ("Corbel", "Calibri", "SegoeUI", "DejaVuSans", "Arial",
                 BASE14_SANS),
        "mono": ("Consolas", "CascadiaCode", "DejaVuSansMono", BASE14_MONO),
        "note": "Condensed technical display over a humanist sans — "
                "instrument-panel clarity.",
    },
    # Software docs: mono-forward, code is a first-class citizen.
    "technical_mono": {
        "display": ("Consolas", "CascadiaCode", "Bahnschrift", "SegoeUI",
                    BASE14_SANS),
        "body": ("SegoeUI", "Corbel", "Calibri", "DejaVuSans", BASE14_SANS),
        "mono": ("CascadiaCode", "Consolas", "DejaVuSansMono", BASE14_MONO),
        "note": "Monospaced headings over a screen sans — reads like good "
                "developer documentation.",
    },
    # Corporate report: restrained, familiar, boardroom-safe.
    "corporate": {
        "display": ("Corbel", "Calibri", "SegoeUI", "Arial", BASE14_SANS),
        "body": ("Calibri", "Corbel", "SegoeUI", "DejaVuSans", BASE14_SANS),
        "mono": ("Consolas", "CourierNew", BASE14_MONO),
        "note": "Quiet humanist sans throughout — a business report that "
                "argues with evidence, not with typography.",
    },
    # Magazine feature: serif display, serif body, editorial warmth.
    "editorial": {
        "display": ("Georgia", "BookAntiqua", "Constantia", "Cambria",
                    BASE14_SERIF),
        "body": ("Georgia", "Constantia", "Cambria", "DejaVuSerif",
                 BASE14_SERIF),
        "mono": ("Consolas", "CourierNew", BASE14_MONO),
        "note": "Sturdy screen-bred serif — long-form reading, magazine "
                "cadence.",
    },
    # Literary: delicate old-style, generous leading, quiet.
    "literary": {
        "display": ("Garamond", "Sylfaen", "BookAntiqua", "Palatino",
                    BASE14_SERIF),
        "body": ("Garamond", "BookAntiqua", "Palatino", "Constantia",
                 BASE14_SERIF),
        "mono": ("CourierNew", "Consolas", BASE14_MONO),
        "note": "Delicate old-style faces set airily — for prose that wants "
                "to be read slowly.",
    },
    # Legal: Times, and nothing clever. Deliberately unremarkable.
    "legal": {
        "display": ("TimesNewRoman", "Cambria", "DejaVuSerif", BASE14_SERIF),
        "body": ("TimesNewRoman", "Cambria", "DejaVuSerif", BASE14_SERIF),
        "mono": ("CourierNew", "Consolas", BASE14_MONO),
        "note": "Times throughout. A legal instrument must look like every "
                "other legal instrument.",
    },
    # Marketing: loud display over an airy geometric.
    "promotional": {
        "display": ("SegoeUIBlack", "Impact", "FranklinGothic",
                    "CenturyGothic", BASE14_SANS),
        "body": ("CenturyGothic", "Candara", "Corbel", "SegoeUI", BASE14_SANS),
        "mono": ("Consolas", BASE14_MONO),
        "note": "Heavy display over an airy geometric — built to be seen "
                "before it is read.",
    },
    # Dense data: condensed everything, maximum rows per page.
    "dense": {
        "display": ("Bahnschrift", "ArialNarrow", "FranklinGothic",
                    BASE14_SANS),
        "body": ("ArialNarrow", "Corbel", "Calibri", "Tahoma", BASE14_SANS),
        "mono": ("Consolas", "DejaVuSansMono", BASE14_MONO),
        "note": "Condensed faces throughout — for documents that are mostly "
                "table.",
    },
    # Friendly / teaching material.
    "friendly": {
        "display": ("TrebuchetMS", "Candara", "CenturyGothic", "Verdana",
                    BASE14_SANS),
        "body": ("Candara", "TrebuchetMS", "Verdana", "Calibri", BASE14_SANS),
        "mono": ("Consolas", "CourierNew", BASE14_MONO),
        "note": "Open, rounded, approachable — teaching and onboarding "
                "material.",
    },
    # Neutral fallback that always looks deliberate.
    "neutral": {
        "display": ("SegoeUI", "Arial", "DejaVuSans", BASE14_SANS),
        "body": ("SegoeUI", "Arial", "DejaVuSans", BASE14_SANS),
        "mono": ("Consolas", "DejaVuSansMono", BASE14_MONO),
        "note": "Plain, correct, unopinionated.",
    },
}


def _font_directories() -> list:
    """Every directory on this host that plausibly holds font files."""
    dirs = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(windir, "Fonts"))
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
                 "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts",
                 os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/.local/share/fonts")]
    # A font directory shipped beside the agent always wins if present — this
    # is the hook that lets a future release carry its own faces so a bare
    # container is not stuck at Helvetica.
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.insert(0, os.path.join(here, "fonts"))
    return [d for d in dirs if d and os.path.isdir(d)]


class FontBook:
    """Discovers, registers and resolves the fonts available on this host.

    One instance per render. `boot()` is idempotent and memoised at class
    level because ReportLab's font registry is a process-global.
    """

    #: family -> resolved ReportLab face names, shared across instances.
    _registered: dict = {}
    _index: dict = {}
    _booted = False
    _log: list = []

    def __init__(self, logger=None):
        self.logger = logger
        self.boot(logger=logger)

    # ── discovery + registration ────────────────────────────────────────
    @classmethod
    def boot(cls, logger=None, force: bool = False) -> dict:
        """Scan the host and register every candidate family we can find.

        NEVER RAISES. A machine with no font directories at all comes back
        with only the base-14 registered, and every downstream `resolve()`
        still returns a usable name.
        """
        if cls._booted and not force:
            return cls._registered
        cls._registered = {}
        cls._log = []

        # Build a case-insensitive filename -> full-path index once, so the
        # candidate table can be checked with a dict lookup instead of a
        # stat() per (family x file) pair.
        index = {}
        for directory in _font_directories():
            try:
                for root, _dirs, files in os.walk(directory):
                    for name in files:
                        lowered = name.lower()
                        if lowered.endswith((".ttf", ".otf", ".ttc")):
                            index.setdefault(lowered, os.path.join(root, name))
                    # Windows font dir is flat; Linux nests deeply. Cap the
                    # walk so a pathological tree cannot stall a render.
                    if len(index) > 20000:
                        break
            except Exception as exc:
                cls._log.append("font dir unreadable %s (%s)"
                                % (directory, type(exc).__name__))
        cls._index = index

        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except Exception as exc:
            cls._log.append("ReportLab font machinery unavailable (%s) — "
                            "base-14 only" % type(exc).__name__)
            cls._booted = True
            cls._install_base14_only()
            return cls._registered

        for family, spec in FONT_CANDIDATES.items():
            faces = cls._register_family(family, spec, index,
                                         pdfmetrics, TTFont)
            if faces:
                cls._registered[family] = faces

        cls._install_base14_only(merge=True)
        cls._booted = True
        if logger:
            try:
                logger("🔤 FontBook: %d families registered (%s)"
                       % (len(cls._registered),
                          ", ".join(sorted(cls._registered)[:12])
                          + ("…" if len(cls._registered) > 12 else "")))
            except Exception:
                pass
        return cls._registered

    @classmethod
    def _install_base14_only(cls, merge: bool = False) -> None:
        if not merge:
            cls._registered = {}
        for family, faces in _BASE14_FAMILIES.items():
            cls._registered.setdefault(family, {
                "regular": faces[0], "bold": faces[1],
                "italic": faces[2], "bolditalic": faces[3],
                "source": "base14", "class": (
                    "mono" if family == BASE14_MONO
                    else "serif" if family == BASE14_SERIF else "sans"),
            })

    @classmethod
    def _register_family(cls, family, spec, index, pdfmetrics, TTFont):
        """Register up to four faces of *family*. Returns a face map or None.

        The candidate ``files`` tuple is positional-with-slack: entry 0 is
        regular, 1 bold, 2 italic, 3 bold-italic, and any trailing entries are
        cross-platform alternates for the REGULAR face. A family that only
        ships a regular (Impact, Bahnschrift, Tahoma-italic-less) is
        registered anyway with the regular standing in for the missing faces —
        ReportLab will then synthesise nothing, but the text renders, which is
        the only thing that actually matters.
        """
        files = spec.get("files", ())
        found = {}
        roles = ("regular", "bold", "italic", "bolditalic")
        for position, filename in enumerate(files):
            path = index.get(filename.lower())
            if not path:
                continue
            role = roles[position] if position < 4 else "regular"
            found.setdefault(role, path)
        if "regular" not in found:
            return None

        face_names = {}
        for role in roles:
            path = found.get(role)
            if not path:
                continue
            registered_name = family if role == "regular" else "%s-%s" % (
                family, role.capitalize())
            try:
                # A .ttc (font collection) needs a subfont index; index 0 is
                # the family's primary face on every collection we ship
                # against. A collection that refuses index 0 is simply skipped.
                pdfmetrics.registerFont(TTFont(registered_name, path))
                face_names[role] = registered_name
            except Exception as exc:
                cls._log.append("%s/%s unusable (%s)"
                                % (family, role, type(exc).__name__))
        if "regular" not in face_names:
            return None

        # Missing faces fall back to the regular so a <b> never explodes.
        regular = face_names["regular"]
        bold = face_names.get("bold", regular)
        italic = face_names.get("italic", regular)
        bolditalic = face_names.get("bolditalic", bold)

        # ⚠️ registerFontFamily is the load-bearing call. WITHOUT it, <b> and
        # <i> inside a Platypus Paragraph silently render as regular text —
        # every emphasis in the document quietly disappears, and nothing
        # anywhere reports an error.
        try:
            pdfmetrics.registerFontFamily(family, normal=regular, bold=bold,
                                          italic=italic, boldItalic=bolditalic)
        except Exception as exc:
            cls._log.append("%s family map failed (%s)"
                            % (family, type(exc).__name__))

        return {"regular": regular, "bold": bold, "italic": italic,
                "bolditalic": bolditalic, "source": "truetype",
                "class": spec.get("class", "sans"),
                "voice": spec.get("voice", "neutral")}

    # ── resolution ──────────────────────────────────────────────────────
    def has(self, family: str) -> bool:
        return family in self._registered

    def resolve(self, preference, role: str = "regular",
                floor: str = BASE14_SANS) -> str:
        """First available family from *preference*, as a usable face name.

        GUARANTEED to return a name ReportLab can set. This is the single
        chokepoint every style in the renderer goes through, which is why a
        missing font is a cosmetic difference here instead of a KeyError deep
        inside a table cell three hundred lines later.
        """
        if isinstance(preference, str):
            preference = (preference,)
        for family in tuple(preference) + (floor,):
            faces = self._registered.get(family)
            if faces:
                return faces.get(role) or faces["regular"]
        return _BASE14_FAMILIES[floor][
            {"regular": 0, "bold": 1, "italic": 2, "bolditalic": 3}.get(role, 0)]

    def family_of(self, preference, floor: str = BASE14_SANS) -> str:
        """The winning FAMILY name (not face name) — what a stylesheet wants."""
        if isinstance(preference, str):
            preference = (preference,)
        for family in tuple(preference) + (floor,):
            if family in self._registered:
                return family
        return floor

    def pairing(self, name: str) -> dict:
        """Resolve a named pairing into concrete families for this host.

        Returns ``{display, body, mono, display_family, body_family,
        mono_family, note, requested, degraded}``. ``degraded`` is True when
        any of the three fell all the way through to a base-14 face, which the
        agent reports in its log so an ugly PDF has a stated cause.
        """
        spec = PAIRINGS.get(name) or PAIRINGS["neutral"]
        display_family = self.family_of(spec["display"], BASE14_SANS)
        body_family = self.family_of(spec["body"], BASE14_SERIF
                                     if "serif" in str(spec["body"][0]).lower()
                                     or spec["body"][-1] == BASE14_SERIF
                                     else BASE14_SANS)
        mono_family = self.family_of(spec["mono"], BASE14_MONO)
        degraded = any(fam in _BASE14_FAMILIES
                       for fam in (display_family, body_family, mono_family))
        return {
            "requested": name,
            "display": self.resolve(display_family),
            "display_bold": self.resolve(display_family, "bold"),
            "display_italic": self.resolve(display_family, "italic"),
            "body": self.resolve(body_family),
            "body_bold": self.resolve(body_family, "bold"),
            "body_italic": self.resolve(body_family, "italic"),
            "body_bolditalic": self.resolve(body_family, "bolditalic"),
            "mono": self.resolve(mono_family),
            "mono_bold": self.resolve(mono_family, "bold"),
            "display_family": display_family,
            "body_family": body_family,
            "mono_family": mono_family,
            "note": spec.get("note", ""),
            "degraded": degraded,
        }

    def available_pairings(self) -> list:
        """Pairings that resolve WITHOUT degrading — used by the LLM design
        consultation so the model is only ever offered choices this machine
        can actually honour."""
        return [name for name in PAIRINGS
                if not self.pairing(name)["degraded"]]

    @classmethod
    def diagnostics(cls) -> dict:
        return {
            "families_registered": sorted(cls._registered),
            "count": len(cls._registered),
            "font_files_indexed": len(cls._index),
            "notes": list(cls._log[:40]),
        }

    # ── measurement (the table solver's foundation) ─────────────────────
    @staticmethod
    def text_width(text: str, font_name: str, size: float) -> float:
        """Exact rendered width of *text* in points. Fails open to an estimate.

        This is the primitive the entire overlap fix rests on: you cannot lay
        out a table safely without knowing how wide a word REALLY is, and the
        0.5-em-per-character guess that most naive layout code uses is wrong
        by 40 % on ``lIi`` and by 30 % the other way on ``WWW``.
        """
        try:
            from reportlab.pdfbase import pdfmetrics
            return pdfmetrics.stringWidth(text or "", font_name, size)
        except Exception:
            # A pessimistic estimate is the safe direction: it over-reserves
            # width, which can only ever prevent an overlap, never cause one.
            return len(text or "") * size * 0.62


class TypeScale:
    """A modular type scale — the arithmetic behind "differentiated titles".

    One *base* size and one *ratio* generate every step. Angela asked for
    "perfect differentiated titles, sub-titles, etc"; differentiation is not a
    list of sizes someone typed, it is a geometric progression, and choosing
    the ratio is the whole design decision:

    ==========  =====  ==================================================
    ratio       name   character
    ==========  =====  ==================================================
    1.125       minor second   very tight — dense reference material
    1.200       minor third    calm, corporate
    1.250       major third    the reliable default; clear at every step
    1.333       perfect fourth confident, editorial
    1.414       augmented 4th  dramatic — covers and marketing
    1.618       golden         theatrical; only with few heading levels
    ==========  =====  ==================================================
    """

    def __init__(self, base: float = 10.5, ratio: float = 1.25,
                 leading_factor: float = 1.45):
        self.base = max(5.0, min(float(base or 10.5), 36.0))
        self.ratio = max(1.05, min(float(ratio or 1.25), 2.0))
        self.leading_factor = max(1.0, min(float(leading_factor or 1.45), 2.6))

    def step(self, n: int) -> float:
        """Size *n* steps up (or down, for negative *n*) from the base."""
        return round(self.base * (self.ratio ** n), 2)

    def leading(self, size: float, tighten: float = 0.0) -> float:
        """Line height for *size*.

        Big type needs proportionally LESS leading than small type — a 30pt
        title at 1.45 line-height looks like it fell apart. So the factor is
        eased down as size grows, which is what a typesetter does by hand.
        """
        eased = self.leading_factor - min(0.30, max(0.0, (size - self.base) * 0.012))
        return round(size * max(1.0, eased - tighten), 2)

    def as_dict(self) -> dict:
        """The complete scale the renderer builds its stylesheet from."""
        return {
            "base": self.base,
            "ratio": self.ratio,
            "body": self.base,
            "body_leading": self.leading(self.base),
            "small": self.step(-1),
            "tiny": self.step(-2),
            "caption": self.step(-1),
            "footer": self.step(-2),
            "code": round(self.base * 0.88, 2),
            "code_leading": round(self.base * 0.88 * 1.32, 2),
            "h6": self.step(0),
            "h5": self.step(1),
            "h4": self.step(1),
            "h3": self.step(2),
            "h2": self.step(3),
            "h1": self.step(4),
            "title": self.step(6),
            "subtitle": self.step(2),
            "cover_title": self.step(8),
            "cover_subtitle": self.step(3),
            "drop_cap": self.step(5),
        }

    def __repr__(self) -> str:
        return "TypeScale(base=%.2f, ratio=%.3f)" % (self.base, self.ratio)
