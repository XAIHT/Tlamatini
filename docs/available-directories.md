<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Ask which directories are available

> Latest released version: **[v1.93.5](changes/2026-11-12-v1.93.5.md)**.

Ask **“Show me the available directories”** or
**“Muéstrame los directorios disponibles”**. Tlamatini answers with the roots
allowed by this instance's active path guard. You do not need to provide a path
to request the list.

A complete, standalone inventory question is handled directly without an LLM
intent decision or filesystem scan. The list uses the same resolved snapshot
that currently enforces access, rather than rereading a changed configuration
that has not taken effect yet. Repeated roots are removed, paths are escaped
for display, and an empty list is reported explicitly.

This reply does not grant access, prove that a directory exists, or override
Windows file permissions. Questions containing another action or an explicit
path continue through ordinary request processing and access checks. After
changing allowed paths, follow the application's normal reload/reconnect
instructions before expecting the active list to change.

Implementation: `agent/rag/directory_listing.py`, called by
`agent/rag/interface.py`. Regression coverage:
`agent.test_available_directories` (English/Spanish questions, mixed-request
exclusion, escaping, empty results and enforced-snapshot consistency). See
[model configuration](model_configuration.md) for the model-driven paths.
