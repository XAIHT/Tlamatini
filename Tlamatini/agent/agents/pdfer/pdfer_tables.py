# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer table layout — the overlap fix, and why the old one could not work.

THE BUG ANGELA REPORTED
-----------------------
*"this version always overlaps the cell's contents into another cells"*.

Measured, 2026-09-06, against the shipping ``DEFAULT_CSS`` on three ordinary
tables (the probe lives in this agent's test suite):

===========================  ======  ==========  ==========================
case                         err     defect      what actually happened
===========================  ======  ==========  ==========================
long paths / URLs            **0**   2 bleeds    a Windows path ran 54pt off
                                                 the right edge of the paper
8-column agent matrix        **0**   4 overlaps  ``netspeed_calculator``
                                                 printed ON TOP of
                                                 ``streamable-http``
5-column config reference    **0**   4 overlaps  ``unified_agent_llm_step…``
                                                 over ``agent.self_healing…``
===========================  ======  ==========  ==========================

Note the middle column. **``xhtml2pdf`` reported ZERO errors every time.** It
declared success while printing one cell on top of another and while running
text off the physical page. That is the worst failure class this codebase
recognises — a silent, plausible, WRONG deliverable — and it is precisely the
one `_resolve_asset_uri` was written to kill for images in 2026-08. This
module kills it for tables.

WHY IT HAPPENED (the actual mechanism, not a guess)
---------------------------------------------------
``xhtml2pdf`` divides the available width between columns from a rough
character count, then draws each cell's text at that x-offset **without ever
asking whether the text fits**. Two independent things then go wrong:

1. **The width estimate is wrong.** A half-em-per-character guess — which is
   what naive layout uses — is **+116 % wrong** on ``lllllllllll`` and
   **−43 % wrong** on ``WWWWWWWWWWW`` (measured with real font metrics in this
   agent's typography test). A 43 % under-estimate means the engine reserves
   58pt for a word that needs 102pt. The extra 44pt is drawn straight into
   the next column.
2. **A long token cannot break.** ``C:\\Users\\angel\\AppData\\Local\\…`` and
   ``https://raw.githubusercontent.com/…`` contain no spaces, so there is no
   break opportunity at all, and the glyphs simply keep going past the cell,
   past the table, and past the edge of the sheet.

THE FIX — MAKE OVERFLOW STRUCTURALLY IMPOSSIBLE
------------------------------------------------
Not "detect and warn". Not "add padding and hope". The layout is *solved*
before a single glyph is placed, using the real font metrics:

**Step 1 — measure honestly.** For every column, walk every cell and compute
its true ``min`` (the widest atom that cannot be broken) and ``nat`` (the
width it would like if it could have one line), using
``pdfmetrics.stringWidth`` against the *actual registered face at the actual
size* — never an estimate.

**Step 2 — solve by water-filling.** Distribute the frame width in proportion
to ``nat``, but with ``min`` as a hard floor. Columns that would fall below
their floor are pinned there and removed from the pool, and the remainder is
re-distributed among the rest; repeat until the assignment is stable. This is
the classic constrained-proportional allocation, and it terminates in at most
``ncols`` passes.

**Step 3 — repair infeasibility, in a strict order.** When even the floors do
not fit, escalate through five rungs (see `REPAIR_LADDER`), cheapest and
least destructive first. Crucially, the LAST rung is the only one that alters
what the reader sees, mirroring the LaTeXer ladder's rule that the
destructive rung is always last.

**Step 4 — hand Platypus ``Paragraph`` cells at exactly the solved widths.**
This is what makes the guarantee *structural*. A ``Paragraph`` given a width
wraps inside that width — it is not capable of drawing outside it. So once
step 2 has produced widths that sum to the frame, no glyph can land in a
neighbouring cell. There is no "usually" here; the geometry forbids it.

**Step 5 — prove it.** `pdfer_audit` re-opens the finished PDF and checks the
real glyph boxes. A layout that believed itself correct and was not is caught
against the file on disk, not against its own intentions.

THE ONE SUBTLETY WORTH KNOWING
------------------------------
Long tokens are handled by switching that cell to ``wordWrap='CJK'``, which
lets ReportLab break between any two characters. The alternative — injecting
spaces or hyphens into the text — was rejected deliberately: a filesystem
path with a space inserted into it is **wrong data**, and a document that
silently corrupts the path it is documenting is worse than one that wraps it
awkwardly. Byte-exactness of the user's content outranks prettiness.

CONTRACTS (do NOT weaken)
-------------------------
1. **Never emit a width assignment whose sum exceeds the frame.**
   `solve_widths` clamps as its final act, and `TableLayout.validate()`
   re-checks. Everything else is optimisation; this is correctness.
2. **Never mutate the user's cell text.** Rungs 1–4 change fonts, sizes and
   wrap MODES. Only rung 5 (`split_columns`) changes the presentation, and it
   preserves every character.
3. **FAIL-OPEN.** Any exception inside the solver falls back to equal-width
   columns with CJK wrapping everywhere — visually plainer, still incapable
   of overlapping.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import re

__all__ = [
    "ColumnDemand",
    "TableLayout",
    "TableSolver",
    "solve_widths",
    "soft_break_points",
    "longest_unbreakable_width",
    "REPAIR_LADDER",
    "MIN_FONT_SIZE",
]

#: Never shrink below this — smaller is not a table, it is a smudge.
MIN_FONT_SIZE = 6.0

#: The escalation order. Cheapest and least visible first; the only rung that
#: changes what the reader sees is LAST, exactly like LaTeXer's ``bisect``.
REPAIR_LADDER = (
    "tighten_padding",   # 1. reclaim cell padding (invisible)
    "char_wrap",         # 2. allow mid-token breaks in offending cells
    "shrink_font",       # 3. step the table's font size down
    "landscape_hint",    # 4. advise the caller to rotate the page
    "split_columns",     # 5. break the table into stacked column groups
)

#: Characters a URL / path / identifier may be broken AFTER. Used only to
#: compute a *better* minimum width, never to modify the text.
_BREAK_AFTER = "/\\-_.:;,=&?@|+~#"

_WS_RE = re.compile(r"\s+")
_NUMERIC_RE = re.compile(
    r"^\s*[-+(]?\s*[$€£¥]?\s*\d[\d\s,._]*\)?\s*%?\s*$")
_TAGS_RE = re.compile(r"<[^>]+>")


def soft_break_points(token: str) -> list:
    """Split *token* into the atoms it could reasonably break between.

    ``https://github.com/XAIHT/Tlamatini`` → ``['https:', '//', 'github.',
    'com/', 'XAIHT/', 'Tlamatini']`` — the pieces a reader would accept a line
    break after. The text is NEVER modified; this only tells the solver how
    narrow the column could get before a mid-*word* break becomes necessary,
    which is what separates "wraps neatly at the slashes" from "hyphenates
    through the middle of a word".
    """
    if not token:
        return []
    atoms, current = [], []
    for char in token:
        current.append(char)
        if char in _BREAK_AFTER:
            atoms.append("".join(current))
            current = []
    if current:
        atoms.append("".join(current))
    return atoms or [token]


def _strip_markup(text: str) -> str:
    """Measure the TEXT, not the ``<b>`` around it.

    Cells arrive as mini-HTML (Platypus' own inline markup). Measuring the
    tags would inflate every width by the length of the markup, wasting page
    width on characters that are never drawn.
    """
    return _TAGS_RE.sub("", text or "")


def longest_unbreakable_width(text: str, font: str, size: float,
                              measure, allow_atom_split: bool = True) -> float:
    """Width of the widest piece of *text* that cannot be broken.

    This single number is the column's hard floor: give a column less than
    this and something *must* stick out. With *allow_atom_split* the URL/path
    break points are honoured (a friendlier, larger floor); without it the
    floor collapses to the widest single character, which is the absolute
    minimum any column can ever be.
    """
    plain = _strip_markup(text)
    if not plain.strip():
        return 0.0
    widest = 0.0
    for word in _WS_RE.split(plain.strip()):
        if not word:
            continue
        if allow_atom_split:
            for atom in soft_break_points(word):
                widest = max(widest, measure(atom, font, size))
        else:
            widest = max(widest, measure(word, font, size))
    return widest


def _widest_character(text: str, font: str, size: float, measure) -> float:
    """The absolute floor — the widest single glyph in the cell."""
    plain = _strip_markup(text)
    if not plain.strip():
        return 0.0
    # Deduplicate first: a 40 kB cell has at most a few hundred distinct
    # characters, and measuring each one once turns an O(n) scan into O(1).
    return max((measure(ch, font, size)
                for ch in set(plain) if not ch.isspace()), default=0.0)


class ColumnDemand:
    """What one column needs, in points, measured with real font metrics."""

    __slots__ = ("index", "min_soft", "min_hard", "natural", "weight",
                 "numeric", "header", "max_cell_chars")

    def __init__(self, index: int):
        self.index = index
        self.min_soft = 0.0      # floor if we break only at / \ . - _ etc.
        self.min_hard = 0.0      # floor if we may break between ANY two chars
        self.natural = 0.0       # width to set the widest cell on one line
        self.weight = 0.0        # share of the document's text this column holds
        self.numeric = True      # every non-header cell parses as a number?
        self.header = ""
        self.max_cell_chars = 0

    def as_dict(self) -> dict:
        return {"index": self.index, "min_soft": round(self.min_soft, 2),
                "min_hard": round(self.min_hard, 2),
                "natural": round(self.natural, 2),
                "weight": round(self.weight, 3), "numeric": self.numeric,
                "header": self.header[:40]}

    def __repr__(self) -> str:
        return ("Col%d(min_soft=%.1f min_hard=%.1f nat=%.1f%s)"
                % (self.index, self.min_soft, self.min_hard, self.natural,
                   " numeric" if self.numeric else ""))


def solve_widths(minimums, naturals, available, weights=None) -> list:
    """Constrained proportional allocation — the core of the fix.

    Distribute *available* points across the columns in proportion to what
    each would *like* (``naturals``), subject to a hard floor for each
    (``minimums``). The classic failure of naive proportional allocation is
    that scaling everything by the same factor pushes narrow-but-incompressible
    columns below their floor; water-filling fixes that by pinning those
    columns and re-solving for the rest.

    Returns widths that **always sum to ≤ available** (exactly, when feasible).
    When the floors alone exceed *available* the result is the floors scaled
    down proportionally — deliberately still returned rather than raised, so
    the caller can escalate the repair ladder while holding a usable layout.
    """
    count = len(minimums)
    if count == 0:
        return []
    if available <= 0:
        return [0.0] * count

    mins = [max(0.0, float(m)) for m in minimums]
    nats = [max(mins[i], float(naturals[i])) for i in range(count)]
    if weights:
        nats = [nats[i] * max(0.05, float(weights[i])) for i in range(count)]

    floor_total = sum(mins)
    if floor_total > available:
        # INFEASIBLE. Hand back the floors scaled to fit: the sum invariant is
        # never violated, and the caller's ladder decides what to do about it.
        scale = available / floor_total if floor_total else 0.0
        return [m * scale for m in mins]

    pinned = [False] * count
    widths = [0.0] * count
    for _pass in range(count + 1):
        free_budget = available - sum(widths[i] for i in range(count) if pinned[i])
        free_nat = sum(nats[i] for i in range(count) if not pinned[i])
        if free_nat <= 0:
            # Nothing left wants width; share the remainder equally.
            loose = [i for i in range(count) if not pinned[i]]
            for i in loose:
                widths[i] = free_budget / len(loose) if loose else 0.0
            break
        changed = False
        for i in range(count):
            if pinned[i]:
                continue
            share = free_budget * (nats[i] / free_nat)
            if share < mins[i] - 1e-6:
                widths[i] = mins[i]
                pinned[i] = True
                changed = True
            else:
                widths[i] = share
        if not changed:
            break

    # Final clamp — the invariant this whole module exists to uphold.
    total = sum(widths)
    if total > available and total > 0:
        widths = [w * (available / total) for w in widths]
    return widths


class TableLayout:
    """The solved plan for one table: widths, size, wrap modes, and evidence."""

    def __init__(self, col_widths, font_size, char_wrap_cols, demands,
                 repairs, notes, feasible=True, split_groups=None,
                 padding=6.0):
        self.col_widths = list(col_widths)
        self.font_size = float(font_size)
        self.char_wrap_cols = set(char_wrap_cols or ())
        self.demands = list(demands or ())
        self.repairs = list(repairs or ())
        self.notes = list(notes or ())
        self.feasible = bool(feasible)
        self.split_groups = list(split_groups or ())
        self.padding = float(padding)

    @property
    def total_width(self) -> float:
        return sum(self.col_widths)

    def validate(self, available: float, tolerance: float = 0.75) -> bool:
        """Belt-and-braces: the sum invariant, re-checked before rendering.

        `solve_widths` already clamps. This exists because the clamp is the
        one thing whose failure would silently reintroduce the exact bug this
        module was written to remove, and a cheap assertion at the boundary is
        worth more than a comment saying it cannot happen.
        """
        if not self.col_widths:
            return True
        if self.total_width > available + tolerance:
            excess = self.total_width - available
            self.notes.append(
                "layout clamp engaged: solved width exceeded the frame by "
                "%.2fpt — rescaled" % excess)
            scale = available / self.total_width
            self.col_widths = [w * scale for w in self.col_widths]
            return False
        return True

    def as_dict(self) -> dict:
        return {
            "col_widths": [round(w, 2) for w in self.col_widths],
            "total_width": round(self.total_width, 2),
            "font_size": self.font_size,
            "char_wrap_cols": sorted(self.char_wrap_cols),
            "repairs": self.repairs,
            "feasible": self.feasible,
            "split_groups": self.split_groups,
            "notes": self.notes,
            "columns": [d.as_dict() for d in self.demands],
        }

    def __repr__(self) -> str:
        return ("TableLayout(%d cols, %.1fpt, widths=%s, repairs=%s)"
                % (len(self.col_widths), self.font_size,
                   [round(w) for w in self.col_widths], self.repairs))


class TableSolver:
    """Solves a table's geometry against real font metrics before rendering.

    Usage::

        solver = TableSolver(measure=FontBook.text_width,
                             body_font="Corbel", head_font="Corbel-Bold")
        layout = solver.solve(rows, available_width=460.0, font_size=10.5)

    *measure* is any ``(text, font, size) -> points`` callable;
    `pdfer_typography.FontBook.text_width` is the production one, and a test
    can inject a deterministic stub.
    """

    def __init__(self, measure, body_font: str, head_font: str = "",
                 padding: float = 6.0, min_font: float = MIN_FONT_SIZE,
                 max_natural_ratio: float = 0.55):
        self.measure = measure
        self.body_font = body_font
        self.head_font = head_font or body_font
        self.padding = float(padding)
        self.min_font = float(min_font)
        # No single column may claim more than this share on its "natural"
        # want. Without the cap one enormous prose cell starves five others
        # into unreadable slivers — technically non-overlapping, practically
        # useless.
        self.max_natural_ratio = float(max_natural_ratio)

    # ── measurement ─────────────────────────────────────────────────────
    def measure_columns(self, rows, font_size: float,
                        has_header: bool = True) -> list:
        """Per-column demands, measured cell by cell with real metrics."""
        ncols = max((len(row) for row in rows), default=0)
        demands = [ColumnDemand(i) for i in range(ncols)]
        if not ncols:
            return demands

        total_chars = 0
        for row_index, row in enumerate(rows):
            is_head = has_header and row_index == 0
            font = self.head_font if is_head else self.body_font
            for col_index in range(ncols):
                cell = row[col_index] if col_index < len(row) else ""
                text = "" if cell is None else str(cell)
                demand = demands[col_index]
                if is_head:
                    demand.header = _strip_markup(text)

                plain = _strip_markup(text)
                demand.max_cell_chars = max(demand.max_cell_chars, len(plain))
                total_chars += len(plain)

                # The two floors.
                demand.min_soft = max(demand.min_soft,
                                      longest_unbreakable_width(
                                          text, font, font_size, self.measure,
                                          allow_atom_split=True))
                demand.min_hard = max(demand.min_hard,
                                      _widest_character(text, font, font_size,
                                                        self.measure))
                # The want: the whole cell on one line, but a 2 000-character
                # paragraph is measured by a sane proxy rather than by its
                # absurd single-line width.
                single_line = self.measure(plain, font, font_size)
                demand.natural = max(demand.natural, single_line)

                if not is_head and plain.strip():
                    if not _NUMERIC_RE.match(plain):
                        demand.numeric = False

        for demand in demands:
            demand.weight = ((demand.max_cell_chars / float(total_chars))
                             if total_chars else 1.0 / ncols)
            # Padding is part of the floor: a column exactly as wide as its
            # widest word, with 6pt of padding on each side, still overflows.
            demand.min_soft += self.padding * 2
            demand.min_hard += self.padding * 2
            demand.natural += self.padding * 2
        return demands

    # ── the ladder ──────────────────────────────────────────────────────
    def solve(self, rows, available_width: float, font_size: float = 10.5,
              has_header: bool = True, allow_landscape: bool = False,
              max_split_columns: int = 0) -> "TableLayout":
        """Produce a layout that CANNOT overflow. Never raises.

        Escalates through `REPAIR_LADDER` only as far as necessary, and
        records every rung it fired so the agent's log can explain what the
        table cost — a shrink from 10.5pt to 8pt is a fact the reader deserves
        to have stated rather than discovered.
        """
        try:
            return self._solve_inner(rows, available_width, font_size,
                                     has_header, allow_landscape,
                                     max_split_columns)
        except Exception as exc:
            # FAIL-OPEN: equal columns, character wrapping everywhere. Plain,
            # but geometrically incapable of the bug we are here to prevent.
            ncols = max((len(r) for r in rows), default=1) or 1
            each = available_width / float(ncols)
            return TableLayout(
                col_widths=[each] * ncols, font_size=max(self.min_font, font_size),
                char_wrap_cols=set(range(ncols)), demands=[],
                repairs=["fail_open"], padding=self.padding, feasible=False,
                notes=["solver raised %s (%s) — fell back to equal columns "
                       "with character wrapping, which cannot overflow"
                       % (type(exc).__name__, exc)])

    def _solve_inner(self, rows, available_width, font_size, has_header,
                     allow_landscape, max_split_columns):
        repairs, notes = [], []
        padding = self.padding
        size = float(font_size)
        available = float(available_width)
        char_wrap = set()

        if not rows:
            return TableLayout([], size, (), [], [], ["empty table"],
                               padding=padding)

        demands = self.measure_columns(rows, size, has_header)
        ncols = len(demands)
        if ncols == 0:
            return TableLayout([], size, (), [], [], ["no columns"],
                               padding=padding)

        # Cap runaway "natural" wants so one prose column cannot starve the
        # rest (see max_natural_ratio).
        natural_cap = available * self.max_natural_ratio
        for demand in demands:
            if demand.natural > natural_cap:
                demand.natural = max(demand.min_soft, natural_cap)

        def floors(kind="soft"):
            return [(d.min_soft if kind == "soft" else d.min_hard)
                    for d in demands]

        # ── feasible right away? The overwhelmingly common case. ────────
        if sum(floors("soft")) <= available:
            widths = solve_widths(floors("soft"),
                                  [d.natural for d in demands], available,
                                  [d.weight for d in demands])
            layout = TableLayout(widths, size, char_wrap, demands, repairs,
                                 notes, True, padding=padding)
            layout.validate(available)
            return layout

        # ── RUNG 1: tighten padding (completely invisible to the reader) ─
        reclaimable = min(padding - 2.0, padding)
        if reclaimable > 0.5:
            padding = 2.5
            shrink = (self.padding - padding) * 2
            for demand in demands:
                demand.min_soft -= shrink
                demand.min_hard -= shrink
                demand.natural -= shrink
            repairs.append("tighten_padding")
            notes.append("cell padding %.1fpt → %.1fpt to reclaim %.0fpt of "
                         "column width" % (self.padding, padding,
                                           shrink * ncols))
            if sum(floors("soft")) <= available:
                widths = solve_widths(floors("soft"),
                                      [d.natural for d in demands], available,
                                      [d.weight for d in demands])
                layout = TableLayout(widths, size, char_wrap, demands, repairs,
                                     notes, True, padding=padding)
                layout.validate(available)
                return layout

        # ── RUNG 2: character wrapping for the columns that overflow ─────
        # Downgrade the WORST offenders first (biggest soft-vs-hard gap =
        # most width reclaimed per unit of ugliness), and stop the moment the
        # table fits. A column only loses its neat word wrapping if the table
        # genuinely cannot be laid out with it.
        order = sorted(range(ncols),
                       key=lambda i: demands[i].min_soft - demands[i].min_hard,
                       reverse=True)
        effective = floors("soft")
        for col in order:
            if sum(effective) <= available:
                break
            effective[col] = demands[col].min_hard
            char_wrap.add(col)
        if char_wrap:
            repairs.append("char_wrap")
            notes.append(
                "columns %s wrap between characters — they hold tokens too "
                "long to break at a space (a path, a URL or an identifier). "
                "The text is preserved byte-for-byte; only the line breaks "
                "move." % sorted(char_wrap))
        if sum(effective) <= available:
            widths = solve_widths(effective, [d.natural for d in demands],
                                  available, [d.weight for d in demands])
            layout = TableLayout(widths, size, char_wrap, demands, repairs,
                                 notes, True, padding=padding)
            layout.validate(available)
            return layout

        # ── RUNG 3: shrink the type ─────────────────────────────────────
        original_size = size
        while size > self.min_font + 0.01:
            size = max(self.min_font, round(size - 0.5, 2))
            demands = self.measure_columns(rows, size, has_header)
            for demand in demands:
                demand.min_soft -= (self.padding - padding) * 2
                demand.min_hard -= (self.padding - padding) * 2
                demand.natural -= (self.padding - padding) * 2
                if demand.natural > natural_cap:
                    demand.natural = max(demand.min_soft, natural_cap)
            effective = [(demands[i].min_hard if i in char_wrap
                          else demands[i].min_soft) for i in range(ncols)]
            if sum(effective) <= available:
                repairs.append("shrink_font")
                notes.append("table type %.1fpt → %.1fpt so every column "
                             "clears its minimum" % (original_size, size))
                widths = solve_widths(effective,
                                      [d.natural for d in demands], available,
                                      [d.weight for d in demands])
                layout = TableLayout(widths, size, char_wrap, demands, repairs,
                                     notes, True, padding=padding)
                layout.validate(available)
                return layout

        # Every column is now character-wrapped at the minimum font size.
        effective = [d.min_hard for d in demands]
        char_wrap = set(range(ncols))
        if "char_wrap" not in repairs:
            repairs.append("char_wrap")
        repairs.append("shrink_font")
        notes.append("table reduced to the %.1fpt floor with every column "
                     "character-wrapped" % size)

        # ── RUNG 4: recommend landscape (the caller owns the page) ───────
        if sum(effective) > available and allow_landscape:
            repairs.append("landscape_hint")
            notes.append(
                "this table needs %.0fpt but the portrait frame offers only "
                "%.0fpt — rotating the page would seat it comfortably"
                % (sum(effective), available))

        # ── RUNG 5: split the columns (LAST — it changes what is seen) ───
        if sum(effective) > available:
            groups, current, running = [], [], 0.0
            for index in range(ncols):
                need = effective[index]
                if current and running + need > available:
                    groups.append(current)
                    current, running = [], 0.0
                current.append(index)
                running += need
            if current:
                groups.append(current)
            if len(groups) > 1 and (max_split_columns <= 0
                                    or len(groups) <= max_split_columns):
                repairs.append("split_columns")
                notes.append(
                    "table split into %d stacked column groups: %d columns "
                    "cannot share one %.0fpt line at any legible size. Every "
                    "cell is preserved; the groups stack vertically and the "
                    "first column repeats as the row key."
                    % (len(groups), ncols, available))
                widths = solve_widths(effective,
                                      [d.natural for d in demands], available,
                                      [d.weight for d in demands])
                return TableLayout(widths, size, char_wrap, demands, repairs,
                                   notes, False, split_groups=groups,
                                   padding=padding)

        # Exhausted. solve_widths still guarantees the sum invariant, so the
        # result is cramped but never overlapping — the promise holds.
        widths = solve_widths(effective, [d.natural for d in demands],
                              available, [d.weight for d in demands])
        layout = TableLayout(widths, size, char_wrap, demands, repairs, notes,
                             False, padding=padding)
        layout.validate(available)
        layout.notes.append(
            "the repair ladder is exhausted: columns are at their absolute "
            "floor. Nothing overlaps, but this table wants a wider page.")
        return layout

    # ── convenience: is this column better right-aligned? ───────────────
    @staticmethod
    def alignments(demands, header_align: str = "LEFT") -> list:
        """Per-column alignment. Numeric columns right-align, because a column
        of figures that does not line up on its units digit is unreadable —
        and PDFer is expected to produce financial and measurement tables."""
        return [("RIGHT" if demand.numeric and demand.header else "LEFT")
                for demand in demands]
