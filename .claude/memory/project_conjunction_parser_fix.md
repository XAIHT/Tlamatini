---
name: Wrapped-agent assignment parser and/with fix
description: 2026-04-24 fix — _split_assignment_segments and _closes_outer_quote now split on `and KEY=` / `with KEY=`, not just `,`/`;`. Root-cause of AngysBackInCUDA file_creator loop.
type: project
originSessionId: 3b708931-1bbc-41a0-b46c-857631a3a9a0
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
On 2026-04-24, six consecutive `file_creator_00N` runs failed while the user was generating CUDA knapsack sources into `C:\Development\AngysBackInCUDA`. Each run's `file_path` looked like `C:\Development\AngysBackInCUDA\drone_knap.h' and content='/*...` — the LLM's whole `content=` payload was absorbed into `file_path`, Python raised `WinError 123`, and one run left a literal directory named `drone_knapsack.h' and content='` inside `include/`.

Root cause: `_split_assignment_segments` in `agent/tools.py` only split on `,`/`;`, and `_closes_outer_quote` only closed single-line quotes on `,`/`;`/EOF. Every `example_request` in `chat_agent_registry.py` separates params with the natural-language conjunction `and` (occasionally `with`), and the LLM reliably copies that style. Multi-arg calls like `filepath='X' and content='Y'` therefore collapsed into one segment whose file_path value was `X' and content='Y`.

Fix: added `_looks_like_conjunction_assignment_start(text, pos)` matching `(and|with) <ident>=`, wired into both `_closes_outer_quote` (both single-line and multi-line modes) and `_split_assignment_segments` (as a top-level split when a whitespace char outside quotes/brackets is followed by the conjunction pattern). Coverage: `AssignmentParserRobustnessTests` gained `test_and_conjunction_splits_file_creator_pair`, `test_with_conjunction_also_splits`, `test_parametric_file_creator_example_request_parses`, and the sweep `test_no_registry_example_leaks_conjunction_into_a_value`.

**Why:** Any regression in this area silently re-breaks every multi-arg wrapped chat-agent call (file_creator, emailer, apirer, crawler, etc.) — the failure mode is invisible until a file or HTTP call actually fires.

**How to apply:** Whenever touching `_split_assignment_segments`, `_split_assignment_segment`, `_closes_outer_quote`, or `_is_multiline_quote_open` in `agent/tools.py`, keep the conjunction rule intact and run `python manage.py test agent.tests.AssignmentParserRobustnessTests`. Also update the relevant registry `example_request` strings if the separator convention itself changes. Full contract in `docs/claude/gotchas.md`.
