---
name: project-netspeed-calculator-agent
description: NetSpeed-Calculator (agent #88) — COMPLETE and wired across ~30 surfaces; the 4 endpoint bugs, the silent-zero fix, and the spaced-impostor Agent row lesson.
metadata:
  type: project
---

**NetSpeed-Calculator** = Tlamatini's **agent #88** (`agent/agents/netspeed_calculator/`).
Measures this machine's Internet connection and reports it **with an error bar** — RFC 6349
throughput + RFC 3550 jitter across several keyless providers, fused by a DerSimonian-Laird
random-effects meta-analysis (95% CI + I² heterogeneity), plus **bufferbloat** graded A+..F.

**STATUS 2026-08-23: DONE.** Engine proven live (4/4 providers, 92.82 Mbps ±0.74) and ALL
wiring surfaces landed. Gate: **262 agent tests + 65 guard tests + 10 Exec-Report audit
green**, ruff 0, eslint 0 errors, `makemigrations --check` clean, **12-pass audit 91/91**,
and BOTH inclusion sweeps (self-modify + self-update) CLEAN.

**THE FOUR ENDPOINT BUGS** (all measured, never guessed — the previous session died mid-fix):
1. Cloudflare **403s** an oversized `bytes=` → clamp `_CF_MAX_DOWN_BYTES = 25_000_000`.
2. `librespeed.org/backend/` is **404** → discover from its **public server list**, pick by RTT.
3. `speed.hetzner.de` is **NXDOMAIN** → the `.com` mirror mesh + `_pick_by_rtt`.
4. **The cache-buster itself killed Hetzner**: `/100MB.bin` = 200, but the SAME url with
   `?nocache=` = RemoteDisconnected. Fixed by a per-provider `cache_bust` flag (False for
   hetzner) PLUS a runtime self-heal that drops the buster after a 0-byte failure.

**THE FIX THAT MATTERS MOST — never ship a silent zero.** The workers swallowed every
exception, so a dead endpoint printed a confident `0.00 Mbps` with no reason; that is
indistinguishable from a slow link and sends the user hunting their own router. Now
`_record_error` (first 5 distinct, deduped) + `_report_dead_transfer` name the cause in the
log AND in `red["why"]`. **Do not reintroduce a silent zero.**

**⚠️ THE SPACED-IMPOSTOR LESSON (found by the 12-pass recheck, worth remembering).** The DB
held TWO rows — `'Netspeed Calculator'` (spaced) and `'NetSpeed-Calculator'`. The spaced one
was seeded by a server boot that happened while the agent DIRECTORY existed but the
`display_name_from_agent_type` override did NOT, so `apps.py` derived it with `.title()`.
A spaced name matches nothing in `acp-canvas-core.js` (it lowercases without collapsing
whitespace) and would have silently dropped every canvas connection. The next boot
self-heals it (`ready()` deletes all rows and rebuilds via `_canonical_agent_display_name`),
**verified live: "Repopulating 88 agents" → exactly 1 row, id=55, `NetSpeed-Calculator`.**
Lesson: after creating an agent dir, ALWAYS restart the server once and re-check the row.
See [[feedback_agent_naming_conventions]] and [[project_agent_table_wiped_on_boot]].

**Naming**: `NetSpeed-Calculator` is hyphenated ON PURPOSE — then `<dash>` and `<space>` are
the same string, so the hyphen-vs-space trap cannot occur for this agent at all.
`<CAPS>`=`NETSPEED_CALCULATOR`, exec-report agent_key=`netspeedcalculator` (dash dropped),
CSS `.canvas-item.netspeed-calculator-agent`, gradient "Fiber Pulse"
`#041E2B → #0E6BA8 → #21D4B4 → #F9C80E`.

**Ask-Execs: TIER D (gated)** — reaches remote hosts like Crawler AND deliberately saturates
the link (~100-200 MB metered per full run). Migrations **0195/0196/0197**; catalog prompt
**119** (`run_execute`, `sort_rank=70`). Harness question uses `action='latency'` on purpose —
the bank may run 1000×/day and a `full` run would burn real bandwidth every time.

**⚠️ SECOND SWEEP — what the first audit MISSED (my audit shared my blind spots).**
A follow-up sweep on Angela's instruction found **9 more surfaces**, the worst being
functional: **`collectstatic` had not been run**, so every JS/CSS wiring edit existed in
`agent/static/` but NOT in the `staticfiles/` copies WhiteNoise actually serves — the
canvas wiring would have been invisible in the browser. **After ANY js/css/template edit:
run `collectstatic`, hash-verify source vs collected, then restart.** The rest were
per-agent doc tables a count-bump does not touch: `docs/claude/multi-turn.md` Ask-Execs
tier-D table, `docs/claude/exec-report.md` map, FlowCreator's **Quick-Reference table** AND
**Agent Selection Priority Rules** (both required by the runbook, both easy to miss after
adding the numbered entry), `Tlamatini.md` self-knowledge (3 counts + a capability bullet),
KIMI §13 catalog row, the Book's **Bestiary AND Glossary** tables, and the naming skill's
"N of M agents" override count. Lesson: **a count bump is not a catalog entry** — grep for
a SIBLING agent's name, not just for the old number.

Verified by generation, not assumption: `copy_source_assets.py --dest <tmp>` produced a real
snapshot (1049 files, 26.28 MB, 5 redacted) **carrying the agent, its config, the test
module and both migrations**; the root stdio MCP server is **dynamic** (`os.listdir`) so it
auto-exposes the agent; and the agent is **stdlib + yaml only**, so `requirements.txt` /
`build.py` needed no change.

**DOCUMENTATION REFACTOR (2026-08-23).** `docs/claude/recent-fixes.md` carries the full
dated contract entry (the four bugs with their measured evidence, the never-a-silent-zero
rule, the three traps). The Book gained the v1.49.1 release narrative. **The RUNBOOK ITSELF
was wrong in three places and is now corrected** in BOTH `.claude/skills/tlamatini-agent-creation/SKILL.md`
and `Tlamatini/.agents/workflows/create_new_agent.md`: (1) `views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS`
is DERIVED — never hand-edit it, register only in `agent_contracts._PARAMETRIZER_OUTPUT_FIELDS`;
(2) a new REQUIRED step to declare the agent in exactly one `_PRE_LAUNCH_PREVIEW_*` set
(a contract test enforces it); (3) a new REQUIRED `collectstatic` + hash-verify + restart
step. `docs/claude/multi-turn.md` said "Registration (3 places)" and named a README table
that no longer exists — now "2 places", with the derived-field warning.

Released as annotated **v1.49.1** at `6adf3623`; aligned local/remote `HEAD` is one
commit later. The frozen `C:\Tlamatini` install needs `python build.py` + reinstall to see it.
