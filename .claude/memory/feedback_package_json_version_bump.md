---
name: feedback-package-json-version-bump
description: "On release version bumps, also bump package.json \"version\" — user wants it tracked despite the git-tag-only contract"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7430c470-cf56-4aa8-ad56-69e521bf07f3
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

> Latest released version: **[v1.93.5](../../docs/changes/2026-11-12-v1.93.5.md)**.


## Mandatory release-version rule — every project and session, 2026-11-04

When Angela specifies X.Y.Z, **assume X.Y.Z is already released** and use it
everywhere as the **latest released version** immediately. Her number is the
one version. Do not check GitHub, tags, installed packages or publication status
to decide whether to call it released. Do not create source, target, pending or
tagged-versus-published versions. Update every current reference, manifest,
`Tlamatini.md`, PDF/PPTX and generator together. Preserve historical entries,
dependency pins, Git history and actual test evidence. Git writes and executable
builds still require authorization. This rule supersedes older contrary advice.

Set `package.json` to the requested bare release number. Update the README badge and links, `BookOfTlamatini.md`, `VERSIONING.md`, `Tlamatini/agent/Tlamatini.md`, all current-version banners, PDF/PPTX content and generators in the same pass. Use `TLAMATINI_RELEASE_TAG` or `TLAMATINI_VERSION` to regenerate documents before a tag exists; otherwise the generator reads the manifest. Do not ask again about the source/publication distinction. Historical release entries and third-party dependency pins stay unchanged. Do not commit, tag, push or run an executable build unless Angela authorizes it.
