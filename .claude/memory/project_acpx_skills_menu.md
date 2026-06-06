---
name: project-acpx-skills-menu
description: "2026-05-17 — Added \"ACPX-Skills\" navbar dropdown (Browse / Configure / Diagnostics / Reload). Skill DB model + boot_skills() were pre-existing from 0071 — UI was the only missing layer"
metadata: 
  node_type: memory
  type: project
  originSessionId: d193b695-d7fe-4b71-922d-23fdd6e12d4a
---

Shipped v1 of the ACPX-Skills admin UI on 2026-05-17. The chat navbar now has a fourth dropdown between **Agents** and **Config** with four entries:

| Entry | Backing | What it does |
|---|---|---|
| Browse Skills | `GET /agent/skills/` + `GET /agent/skills/<name>/` | List + detail pane with frontmatter, requires, inputs/outputs, permissions, body. Search-filterable. |
| Configure Skills | WebSocket `set-skills` (mirrors `set-mcps`/`set-agents`) | Checkbox grid toggling `Skill.enabled` per row |
| Diagnostics | `GET /agent/skills/_/diagnostics/` | Cross-checks `requires_tools`/`requires_mcps` against disabled rows; flags `runtime:acpx` skills with unknown `acpx_agent`; surfaces orphan DB rows |
| Reload Registry | `POST /agent/skills/_/reload/` | Re-runs `agent.acpx.service.boot_skills()` — no server restart needed |

**Why:** User wanted a "very capable" admin surface for the 21 SKILL.md packages, with the explicit constraint *"use the DB only for enumeration and enable/disable like MCPs config or Agents config already made but no more"* — keeping per-skill permissions/budget overrides out of the DB (those stay in the SKILL.md frontmatter on disk).

**How to apply:**
- **The `Skill` model already existed** from migration `0071_acpx_skills.py` and is auto-seeded by `agent/acpx/service.py::boot_skills()` (called from `apps.AgentConfig.ready()` on a background thread). Tasks 1-3 of the v1 plan were no-ops — only the UI + HTTP endpoints + tool-gating + WebSocket wiring were missing. If you ever need to add a similar admin surface for another disk-discovered registry, **check for the model first** before writing a migration.
- **Tool surface gates on `Skill.enabled`** via `_disabled_skill_names()` in `agent/acpx/tools.py` (fails open on DB exception so a broken admin layer never silently hides skills). Adding a 13th LLM-facing skill-related tool? Make sure it also consults this helper.
- **The DB row's vestigial fields** (`frontmatter_json`, `body_sha256`, `last_loaded_at`, `runtime`, `acpx_agent`) are owned by `boot_skills()` and intentionally ignored by the admin UI — Browse / Diagnostics read fresh from `skill_registry` (the SKILL.md on disk is the only source of truth). `save_skill(name, enabled)` only touches `Skill.enabled`. Don't ever write user-configurable settings into those fields; boot_skills will overwrite them on restart.
- **WebSocket parity** with Mcps/Agents/Tools: `consumers.skill_establishment()` sends `type: 'skill'` system messages on connect; frontend `agent_page_chat.js` pushes them into the module-level `skills = []` array; Configure dialog reads from that array; Continue sends `set-skills` with the `name=description=true/false,...` shape.
- **Skill name vs `<prefix>-N` pattern**: Skills key on the SKILL.md frontmatter `name` directly (no `skill-N` prefix), because the `Skill` DB row uses `name` as its unique key. The `_normalize_toggle_record_name('skill', ...)` helper does NOT apply.
- **Frontend dialogs** are jQuery-UI (not Bootstrap modals) per the existing Mcps/Tools/Agents convention — see `agent/static/agent/js/skills_dialog.js` for the canonical Configure-dialog pattern when adding a new toggle-able registry.
- **Coverage**: 14 new tests in `agent/tests.py` — `SkillsAdminEndpointTests` (7), `SkillsToolSurfaceGatingTests` (3), `SkillsNavbarTemplateContractTests` (4). The template-contract class pins the dropdown HTML so a careless edit doesn't silently drop the menu.
- **ESLint globals** for the new functions live in `eslint.config.mjs` (added: `skills`, `computeCheckboxGridLayout`, `OpenSkills*Dialog`/`preRender`/`render`/`open`/`reload` family). New `skills_dialog.js`-defined functions must be declared there to stay no-undef-clean.

**Files touched (~12)**: `agent/views.py`, `agent/urls.py`, `agent/consumers.py`, `agent/acpx/tools.py`, `agent/tests.py`, `agent/templates/agent/agent_page.html`, `agent/static/agent/js/{agent_page_state,agent_page_init,agent_page_chat,skills_dialog}.js`, `agent/static/agent/css/skills_dialog.css`, `eslint.config.mjs`, `docs/claude/mcp-tools.md`.

**Not in v1 (deferred to v2)**: Test/Invoke modal (form-driven manual skill invocation), Audit log browser (NDJSON at `<install>/.tlamatini/skill-audit/<YYYY-MM>/`), in-browser SKILL.md editor, Create-skill wizard, Import/Export, Triggers Inspector. The original proposal in this turn's conversation has the full v2/v3 scope if the user comes back asking for more.

**Doc refresh pass (same day, 2026-05-17)**: After the implementation landed, the user asked for a comprehensive doc update across "every file in this project". The full surface that got the ACPX-Skills section added:
- `README.md` §3.11 — full user-facing chapter (Browse / Configure / Diagnostics / Reload, the DB-scope rationale, file-pointer block)
- `BookOfTlamatini.md` — both a top-of-Recent-Updates entry (one long narrative paragraph) AND a new §17.5 chapter in Part II with the same long-form style as §17 (DB menu)
- `ACPX.md` — new §6.5 between the visual-canvas Phase-5 section and the day-one walkthrough, with what-it-changes references back to §7 and §10 of the original ACPX dossier
- `CLAUDE.md` — extended the Skills bullet in Project Identity with the admin-menu mention
- `docs/claude/INDEX.md` — extended the mcp-tools.md description line
- `docs/claude/architecture.md` — added `Skill` (and `AcpAgent` / `AcpSession` / `SkillInvocation`) to the Database Models section
- `docs/claude/acpx.md` — new `ACPX-Skills admin menu` section above the decision matrix
- `docs/claude/frontend.md` — new `skills_dialog.js` entry under Shared / chat-runtime auxiliary, JS module count bumped 27→28
- `docs/claude/gotchas.md` — long Recent-Fixes entry covering the DB constraint, tool-surface gating, WebSocket parity, naming convention
- `docs/claude/mcp-tools.md` — was already updated during the implementation pass (no re-edit needed)
- **Skipped intentionally:** the 21 `agent/skills_pkg/*/SKILL.md` files (they describe individual skills, not platform UI; bolting a generic admin-menu section onto them would be wrong) and `agents_descriptions.md` (sidebar tooltips for canvas agents, not navbar dropdowns).
- **PDF + PPTX regenerated** by running `python agent/doc_generation/refresh_project_docs.py` from `Tlamatini/` cwd (the script paths assume the inner Tlamatini/ directory). Both outputs land at the repo root (`tlamatini_app_summary.pdf`, `Tlamatini_eXtended_Artificial_Intelligence_Humanly_Tempered.pptx`). The same script produces both binaries — there is no separate PPTX generator. **Bash-tool cwd quirk:** subsequent Bash invocations sometimes reset cwd unpredictably; prefer absolute paths (`/c/Development/Tlamatini/Tlamatini/...`) over `cd`-then-command for any verification commands.
