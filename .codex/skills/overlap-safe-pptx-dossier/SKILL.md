---
name: overlap-safe-pptx-dossier
description: Use when asked to create or update a complete technical PPTX deck, especially a Tlamatini-style presentation, where slides must describe the whole system, architecture, usage, line inventory, complete file tree, and must never contain overlapping text, images, cards, tables, or diagrams.
---

# Overlap-Safe PPTX Dossier

Use this skill when a deck must be complete, polished, and layout-safe.

## Non-Negotiable Layout Rules

- Never cram dense content onto one slide. Split into more slides.
- Track every intentional content rectangle: title, subtitle, panels, cards, diagrams, tables, images, and tree text.
- Validate that every tracked rectangle stays within slide bounds.
- Validate that tracked rectangles do not overlap unless the overlap is deliberate containment, such as text inside its own card.
- Use `TextFrame.fit_text()` or conservative font sizes, but do not rely on auto-fit to rescue overloaded slides.
- For file-tree appendix slides, chunk the tree into small fixed-size line groups; keep one monospaced text box per slide.
- For tables, prefer monospaced text or pre-sized rows over huge PowerPoint tables.

## Visual Style Guidance

When the user supplies a reference presentation:

- Inspect the deck with `python-pptx`; if slides are image-only, extract media from `ppt/media/` and use the images as style references or cover backgrounds.
- Match the visual language rather than copying old content blindly.
- For the Tlamatini reference style, prefer obsidian/dark stone backgrounds, copper and jade accents, thin ornamental lines, translucent cards, geometric diagrams, and light display typography.
- Use icons as simple labeled glyphs, line shapes, or small cards when assets are not available.
- Keep contrast high enough for extracted text and projected viewing.

## Required Deck Content

The deck must include:

- What the system is and what it does.
- How the system works end to end.
- How to use it from source, in chat, in Multi-Turn mode, and in the workflow designer.
- Packaging/build path.
- Agent catalog overview.
- Repository facts and current HEAD.
- Effective line counts by language, total effective lines, and methodology.
- Largest files by effective lines.
- Complete tracked file tree, split across appendix slides.
- Latest changes or optimizations as a section, not as the whole deck.

## Preferred Tlamatini Workflow

In the Tlamatini repo, run:

```powershell
python Tlamatini\agent\doc_generation\refresh_project_docs.py
```

The generator builds the full PPTX and performs an internal geometry audit while building slides. If it fails, fix layout by adding slides, shortening bullet groups, or reducing line chunks. Do not ignore audit failures.

## Validation Checklist

- Open the PPTX with `python-pptx` and confirm slide count.
- Extract text from the first content slides and at least one tree appendix slide.
- Confirm the line-inventory slide contains the total effective line count.
- Confirm the tree appendix count covers the complete tracked file tree.
- Confirm no audit exceptions were raised during generation.
