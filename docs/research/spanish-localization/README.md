# Spanish Localization of Tlamatini — Research Package

**Date:** 2026-07-27 · **System:** Tlamatini v1.47.0 (commit `3e6d514f`)
**Status:** Research and design only. **No Tlamatini source code was modified.**

---

## What is here

| File | What it is |
|---|---|
| **[`PAPER-v2.md`](PAPER-v2.md)** | **★ THE PAPER.** Standalone doctoral-level treatment centred on **NEPANTLA**, the algorithm that guarantees Spanish execution is at least as correct as English *for any backend model the user binds* — including models with no Spanish at all. 2 propositions, 1 theorem with proof, 2 corollaries, full pseudocode, 3 worked traces, complexity analysis, falsifiable evaluation protocol. Contains the absolute asset-naming invariant. |
| [`PAPER.md`](PAPER.md) | Earlier edition. Same evidence base, organised as a comparative analysis of localization architectures. Superseded by v2 for the algorithmic content; still useful for the surface-by-surface inventory. |
| **[`paper/nepantla.pdf`](paper/nepantla.pdf)** | **★ THE PAPER, TYPESET.** 39 pages, formal LaTeX — numbered theorems, TikZ architecture figure, BibTeX bibliography. Built clean: 0 errors, 0 undefined references, 0 undefined citations. Sources in [`paper/`](paper/): `nepantla.tex` (master + preamble), `sections/*.tex`, `nepantla.bib`. Rebuild with `pdflatex → bibtex → pdflatex → pdflatex`. |
| **[`DESIGN.md`](DESIGN.md)** | **★ THE IMPLEMENTATION.** How NEPANTLA is built into Tlamatini: the translation-boundary contract, module map with full interfaces, every integration point verified against the real code (including the exact pre-execution hook in the Multi-Turn executor), config keys, a mandatory **shadow-mode** phase, test plan, packaging and risk register. |
| [`reference_impl/normalize.py`](reference_impl/normalize.py) | **The core fix.** NFKD-folding tokenizer + word-boundary phrase matching + canonical-key expansion. Identity-preserving on ASCII. |
| [`reference_impl/detector.py`](reference_impl/detector.py) | Closed-set language ID with prose masking, decoy classes, evidence-weighted confidence. |
| [`reference_impl/policy.py`](reference_impl/policy.py) | Conversation-sticky routing with hysteresis and a per-path route vector. |
| [`reference_impl/noninferiority.py`](reference_impl/noninferiority.py) | Tango score CI, mid-p McNemar, BCa bootstrap, power calculations, BH FDR. |

All reference modules are **stdlib-only** and run standalone:

```bash
cd docs/research/spanish-localization/reference_impl && python normalize.py && python detector.py && python policy.py && python noninferiority.py
```

---

## The finding in one paragraph

The Spanish problem in Tlamatini is **not a model problem**. For Spanish the model-side gap is 1–4 points on reasoning and approximately **zero on tool selection**. The problem is that Tlamatini's *deterministic control plane* is monolingually English: an ASCII-only tokenizer that turns `código` into `digo`, ~2,389 hardcoded English lexemes with zero non-ASCII characters, and unbounded substring matching that lets the 2-character alias `ue` (Unrealer) match inside *pr**ue**ba*. Measured on the real scorer with twelve matched prompt pairs: **English top-1 tool selection 10/12, Spanish 0/12**, with the correct tool scoring exactly zero in 7 of 12 Spanish cases. A translation pivot cannot fix this and would make it worse — it injects a conjunctive failure mode of roughly 10% at realistic argument density, because an operator task fails completely if *any* file path is damaged.

## The recommendation in one paragraph

**Asymmetric Localization.** Keep program text (system prompt, tool names, schemas, the 18 machine sentinel families) in English and byte-stable. Pass user content through **verbatim** — zero MT hops, so literal fidelity is exact. Generate the answer **natively in Spanish**, once. Make the deterministic core **language-neutral** (fold, then map to the *existing* canonical English hint tokens) rather than bilingual. Enforce two invariants — Identifier/Label Separation and the Label Round-Trip Prohibition — both machine-checked. Ship the output guard **read-only** until its false-positive rate is measured. Then prove parity as a pre-registered non-inferiority claim with assay sensitivity, not as a demo.

---

## The five things that will break if this is done naively

1. **Translating the two MCP checkbox labels disables both MCPs permanently.** The label's `innerText` is round-tripped into `Mcp.mcpDescription`, which `factory.py` compares against the English literal. That table is never rebuilt on boot and survives self-update. `DESIGN.md` §8.4.
2. **Translating agent descriptions silently drops every agent from generated `.flw` files** — `_resolveCanonicalAgentName` resolves nothing, and all 56 CSS attribute selectors miss.
3. **A Spanish conjunction corrupts file paths today.** `filepath='C:/a.txt' y content='hola'` parses to a single argument whose value is `C:/a.txt' y content='hola`. Verified against the live parser.
4. **A Spanish error message is scored as SUCCESS** and gets baked into a saved workflow, because the failure classifier tests eleven English prefixes.
5. **`is_valid_prompt` rejects 7 of 8 well-formed Spanish commands** — in English.

## The one thing to build first

**Phase P1** — the deterministic-core neutrality fix in `normalize.py`. Two hook lines and a data file. It is invisible to English users (identity on ASCII, pinned by a golden corpus), it converts Spanish tool selection from 0/12 to functional, and it **fixes real English defects too**: `api` matching inside *rapid*, `ls` inside *false*, and the accent-dependent nondeterminism that already affects any English user who pastes an accented filename.

---

## Method and integrity

Fourteen parallel analysis agents read the repository directly (684 tool calls, 4.3M tokens), each required to attach `file:line` evidence it had actually observed. Every scientific claim then went through an adversarial verification pass that re-fetched each cited work to confirm title, authors, year and identifier, and re-checked every numeric claim against the source table. That pass found **one misattributed reference** (a real paper cited for figures it does not contain), which was removed — see `PAPER.md` §10.4. Two further adversarial agents attempted to refute the architecture; their surviving objections were **incorporated into the design rather than rebutted**, which is why the design specifies a read-only guard, per-path routing, calibrated rather than asserted thresholds, and conversation hysteresis.

The reference implementations were executed and their output verified before publication.
