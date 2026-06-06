---
name: TeleTlamatini ACPX parity
description: TeleTlamatini AND WhatsTlamatini carry `acpx_enabled` end-to-end (config default true); 2026-06-04 both also hardened for "Ask Execs" — ungated by design, `ask_execs_enabled` hard-pinned False, exec-permission frames skipped, dedicated-account docs
type: project
originSessionId: 156f0765-c90e-440e-a266-922659ec55f5
---
**2026-06-04 update — WhatsTlamatini parity DONE + both bots adapted to "Ask Execs".** WhatsTlamatini now has the same `acpx_enabled` end-to-end wiring as TeleTlamatini (it previously carried none), and BOTH bots were hardened against everything since Ask Execs (2026-05-29):
- `ask_execs_enabled` is **hard-pinned `False`** in both `_send_and_collect.send_payload` (sent explicitly, not omitted) — bots are **fully authorized / ungated by user decision** (a Telegram/WhatsApp user can't answer a browser Proceed/Deny modal). Do NOT wire up chat-side approval; it was explicitly declined.
- `'exec-permission-request'` / `'exec-permission-response'` added to `_SPECIAL_TYPES_TO_SKIP` in both (the consumer group-broadcasts the request frame to `chat_user_<id>`, so a browser human on the SAME account leaks it onto the bot's socket).
- Both resolvers warn (non-fatal) when `acpx_enabled and not multi_turn_enabled`.
- Both `config.yaml`s document: **run the bot on a dedicated Tlamatini account** (room group + request global-state + Ask-Execs broker all keyed by user id) and the fully-authorized authority model.
- Tests: `agent/test_chat_bridge_bots.py` (9 SimpleTestCase, importlib-loads both pool modules). Docs: `docs/claude/agents.md` + `recent-fixes.md` (2026-06-04). ruff clean, no migration. **Frozen needs `python build.py`.** Not committed.

---

(Original 2026-05-08 entry — TeleTlamatini only) TeleTlamatini's `TlamatiniBridge` and `_resolve_tlamatini_cfg` carry `acpx_enabled` end-to-end (constructor → `_send_and_collect` payload → startup-ready log line), mirroring `multi_turn_enabled` / `exec_report_enabled`. Touched:

- `agent/agents/teletlamatini/teletlamatini.py` — added `acpx_enabled: bool` constructor param + `'acpx_enabled': bool(self.acpx_enabled)` in `_send_and_collect`'s send_payload + key in `_resolve_tlamatini_cfg` (resolver default `False`) + bridge construction in `_telegram_main_loop` + appended `acpx={...}` to startup-ready log + auth-OK message now mentions ACPX example.
- `agent/agents/teletlamatini/config.yaml` — added `acpx_enabled: true` under `tlamatini:` with a multi-line comment explaining what the 12 ACPX/Skill tools enable, why ACPX implies Multi-Turn, and the recommended pairing.

**Why:** User explicitly asked to enable TeleTlamatini to execute the complete ACPX schemes, just like Multi-Turn is already wired. Without `acpx_enabled` on the WS frame, `consumers.py::receive` defaults to `False` and `agent.acpx.filter_acpx_tools()` strips the 12 tool names from the planner's bound list — so a Telegram user could never trigger `acp_doctor` / `acp_spawn` / `acp_relay` / `invoke_skill` even though the LLM behind Tlamatini supports them.

**How to apply:** When asked to mirror chat-toolbar surface to other bridge agents (WhatsTlamatini is the obvious next candidate — it's a Meta WhatsApp Cloud API mirror of TeleTlamatini), apply the same 5-edit pattern. The flag must default `False` in the resolver (preserves existing deploys) but `True` in the shipped YAML template (so fresh deploys get the full ACPX surface). Don't forget to update the file's docstring/banner / auth-OK message so the user-facing experience reflects the new capability.
