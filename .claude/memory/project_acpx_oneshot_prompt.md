---
name: ACPX oneshot-prompt capture fix
description: 2026-05-04 fix for ACPX losing TUI agent responses; claude/gemini/cursor/qwen/codex now re-spawn per turn with prompt as CLI arg
type: project
originSessionId: ccfb8f0a-8b12-4ab6-acd1-f6af3336f728
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->
2026-05-04: Switched `claude`, `gemini`, `cursor`, `qwen`, `codex` in
`agent/acpx/agent_registry.py::DEFAULT_ACP_AGENTS` from
`json-acp` / `tui-repl` to **`transport="oneshot-prompt"`** with
per-agent `prompt_arg_flag` (`-p` for claude/cursor/gemini/qwen) and
`prompt_subcommand_args` (`["exec"]` for codex).

**Why:** Long-lived stdin-fed children captured ONLY the outbound prompt
on Windows because TUI CLIs detect a piped stdout and refuse to flush
their answer. User report verbatim: *"the transcript only shows the
outbound prompts, not the inbound responses"*. The fix re-spawns the CLI
fresh per turn with the prompt as a CLI arg, closes stdin immediately,
and reads stdout/stderr to EOF via `proc.communicate(timeout=180)`. This
is the same `-p`/`--print` mode each CLI ships for non-interactive use.

**How to apply:**
- Implementation lives in `AcpSession._oneshot_send_turn` (runtime.py)
  and the mirror `run_oneshot_prompt` in `agent/agents/acpxer/acpxer.py`.
- New `AcpAgentSpec` fields: `prompt_arg_flag: Optional[str]`,
  `prompt_subcommand_args: List[str]`. Both are propagated by
  `build_agent_registry`.
- The emitted event has `event="assistant_message"`, `role="assistant"`,
  `text=stdout`, `exit_code`, `elapsed_seconds`. `extract_last_assistant_text`
  picks it up unchanged.
- Inter-turn child state does NOT persist — caller must carry context.
- Tests: `OneshotPromptCaptureTests` (4 tests) +
  `AgentRegistryTransportProfileTests.test_oneshot_prompt_agents_have_capture_path`.
- DO NOT revert any of these agents to a long-lived stdin-fed child or
  to `json-acp` mode without first proving capture in a running
  instance against a real `claude -p` / `gemini -p` invocation.
