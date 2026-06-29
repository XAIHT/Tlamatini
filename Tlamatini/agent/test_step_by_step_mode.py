# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Deep certification of the Step-by-Step toolbar mode (step_by_step_enabled).

Codex added a per-request flag that injects a STEP-BY-STEP system-prompt block
so Tlamatini teaches one paced step at a time (and waits for the user's READY).
This suite certifies the WHOLE plumbing the flag rides — the same per-request
flag path that has historically broken when one hop drops the key
(exec_report_enabled / ask_execs_enabled were both bitten by the
drop-on-rebuild bug class):

    toolbar checkbox -> sessionStorage -> WebSocket send
      -> consumers.receive -> queue_llm_retrieval
        -> interface.ask_rag (bypass_prompt_validation + payload)
          -> unified.py (3 payload-rebuild sites = the whitelist)
            -> CapabilityAwareToolAgentExecutor.invoke
              -> _get_executor_for_tools (cache keyed on step_by_step)
                -> _build_system_prompt (injects _STEP_BY_STEP_SYSTEM_GUIDANCE)

Three layers of certification:
  1. UNIT     — _build_system_prompt injects/omits the block; it is .format-safe.
  2. RUNTIME  — a capturing fake LLM proves the flag reaches the SYSTEM MESSAGE
                at invoke() time, in the standalone (no-Multi-Turn) path, and
                that the executor cache never cross-contaminates on/off prompts.
  3. SOURCE   — regression guards pin the flag at every backend hop so a future
                edit cannot silently drop it from the whitelist.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from django.test import SimpleTestCase

from agent.mcp_agent import (
    CapabilityAwareToolAgentExecutor,
    MultiTurnToolAgentExecutor,
    _build_system_prompt,
    _STEP_BY_STEP_SYSTEM_GUIDANCE,
)

_AGENT_DIR = Path(__file__).resolve().parent


def _read(rel: str) -> str:
    return (_AGENT_DIR / rel).read_text(encoding="utf-8")


def _noop_tool(name="noop", description="a no-op tool"):
    return SimpleNamespace(name=name, description=description)


# ── 1. UNIT: prompt injection on/off + format safety ────────────────────────

class StepByStepPromptInjectionTests(SimpleTestCase):
    def test_block_injected_when_enabled(self):
        prompt = _build_system_prompt("BASE PROMPT.", [_noop_tool()], step_by_step_enabled=True)
        self.assertIn("STEP-BY-STEP MODE", prompt)
        self.assertIn("wait for the user's requested short reply", prompt)
        self.assertIn("bare username, DONE, ERROR, NOWINDOW", prompt)
        self.assertIn("external_mcp_doctor", prompt)

    def test_block_absent_when_disabled(self):
        prompt = _build_system_prompt("BASE PROMPT.", [_noop_tool()], step_by_step_enabled=False)
        self.assertNotIn("STEP-BY-STEP MODE", prompt)

    def test_default_is_off(self):
        # The keyword defaults to False — a caller that forgets it gets no block.
        self.assertNotIn("STEP-BY-STEP MODE", _build_system_prompt("BASE.", [_noop_tool()]))

    def test_guidance_is_format_safe(self):
        # The block is inserted into the system prompt AFTER brace-escaping, so it
        # must not introduce a stray single brace that a later .format() would choke on.
        self.assertNotIn("{", _STEP_BY_STEP_SYSTEM_GUIDANCE)
        self.assertNotIn("}", _STEP_BY_STEP_SYSTEM_GUIDANCE)


# ── 2. RUNTIME: the flag reaches the real system message via invoke() ───────

class _CapturingLLM:
    """Fake LLM that records the system prompt of every invoke and never tool-calls."""

    def __init__(self):
        self.system_prompts = []
        self.message_batches = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.message_batches.append(list(messages))
        try:
            self.system_prompts.append(getattr(messages[0], "content", "") or "")
        except Exception:
            self.system_prompts.append("")
        return SimpleNamespace(content="done", tool_calls=[])


class StepByStepRuntimeWiringTests(SimpleTestCase):
    def _executor(self, llm):
        return CapabilityAwareToolAgentExecutor(
            llm=llm, preeliminary_prompt="BASE PROMPT.", tools=[_noop_tool()]
        )

    def test_cache_keeps_on_and_off_prompts_separate(self):
        cae = self._executor(_CapturingLLM())
        ex_on = cae._get_executor_for_tools(cae.tools, step_by_step_enabled=True)
        ex_off = cae._get_executor_for_tools(cae.tools, step_by_step_enabled=False)
        self.assertIsNot(ex_on, ex_off)
        self.assertIn("STEP-BY-STEP MODE", ex_on.system_prompt)
        self.assertNotIn("STEP-BY-STEP MODE", ex_off.system_prompt)
        # cache hit: same args return the SAME executor object (no rebuild drift)
        self.assertIs(ex_on, cae._get_executor_for_tools(cae.tools, step_by_step_enabled=True))

    def test_invoke_standalone_threads_flag_into_system_message(self):
        """No Multi-Turn, just Step-by-Step: the flag must still reach the LLM."""
        cap = _CapturingLLM()
        cae = self._executor(cap)
        with patch("agent.external_mcp_manager.get_external_mcp_tools", return_value=[]):
            cae.invoke({"input": "walk me through redis setup",
                        "multi_turn_enabled": False, "step_by_step_enabled": True})
            on_prompts = list(cap.system_prompts)
            cap.system_prompts.clear()
            cae.invoke({"input": "walk me through redis setup",
                        "multi_turn_enabled": False, "step_by_step_enabled": False})
            off_prompts = list(cap.system_prompts)
        self.assertTrue(on_prompts and any("STEP-BY-STEP MODE" in p for p in on_prompts),
                        "Step-by-Step guidance never reached the system message")
        self.assertTrue(off_prompts and all("STEP-BY-STEP MODE" not in p for p in off_prompts),
                        "Step-by-Step guidance leaked into an off request")

    def test_invoke_multiturn_threads_flag_into_system_message(self):
        """Multi-Turn ON + Step-by-Step ON: the guidance reaches the executor too."""
        cap = _CapturingLLM()
        cae = self._executor(cap)
        with patch("agent.external_mcp_manager.get_external_mcp_tools", return_value=[]):
            cae.invoke({"input": "set up the mcp",
                        "multi_turn_enabled": True, "step_by_step_enabled": True})
            prompts = list(cap.system_prompts)
        self.assertTrue(prompts and any("STEP-BY-STEP MODE" in p for p in prompts))

    def test_multiturn_executor_includes_scoped_history_before_current_turn(self):
        """Short Step-by-Step replies must reach the tool loop with prior wizard context."""
        cap = _CapturingLLM()
        executor = MultiTurnToolAgentExecutor(llm=cap, system_prompt="SYSTEM", tools=[])
        executor.invoke({
            "input": "alice",
            "chat_history": [
                HumanMessage(content="Tlamatini, help me create a NEW user named ----<set name here>----."),
                AIMessage(content="Please tell me the actual username you want."),
                HumanMessage(content="alice"),
            ],
        })
        contents = [getattr(m, "content", "") for m in cap.message_batches[-1]]
        self.assertIn("Tlamatini, help me create a NEW user named ----<set name here>----.", contents)
        self.assertIn("Please tell me the actual username you want.", contents)
        self.assertEqual(contents.count("alice"), 1)


# ── 3. SOURCE: regression guards for every backend hop of the flag ──────────

class StepByStepPlumbingContractTests(SimpleTestCase):
    def test_consumers_reads_and_forwards_the_flag(self):
        text = _read("consumers.py")
        self.assertIn("step_by_step_enabled = bool(text_data_json.get('step_by_step_enabled'", text)
        self.assertIn("step_by_step_enabled=step_by_step_enabled", text)  # passed to queue_llm_retrieval
        self.assertIn('"step_by_step_enabled": bool(step_by_step_enabled)', text)  # into the question payload
        self.assertIn("load_recent_chat_history(conversation_user", text)
        self.assertIn("chat_history=chat_history", text)

    def test_interface_bypass_and_payload(self):
        text = _read("rag/interface.py")
        self.assertIn("or bool(step_by_step_enabled)", text)  # part of bypass_prompt_validation
        self.assertIn('payload["step_by_step_enabled"] = step_by_step_enabled', text)

    def test_unified_whitelist_has_all_three_rebuild_sites(self):
        text = _read("rag/chains/unified.py")
        occurrences = text.count('"step_by_step_enabled": bool(payload.get("step_by_step_enabled"')
        self.assertEqual(occurrences, 3,
                         f"expected the flag at all 3 payload-rebuild sites, found {occurrences}")

    def test_mcp_agent_cache_key_and_guidance(self):
        text = _read("mcp_agent.py")
        self.assertIn("_STEP_BY_STEP_SYSTEM_GUIDANCE", text)
        self.assertIn("__step_by_step__=", text)  # executor cache key includes the flag
        self.assertIn('"chat_history": chat_history', text)

    def test_frontend_sends_the_flag(self):
        text = _read("static/agent/js/agent_page_init.js")
        self.assertIn("'step_by_step_enabled': isStepByStepEnabled()", text)

    def test_frontend_state_helpers_present(self):
        text = _read("static/agent/js/agent_page_state.js")
        for needle in ("STEP_BY_STEP_STORAGE_KEY", "isStepByStepEnabled",
                       "persistStepByStepState", "applyStoredStepByStepState"):
            self.assertIn(needle, text)

    def test_checkbox_in_template(self):
        self.assertIn('id="step-by-step-enabled"', _read("templates/agent/agent_page.html"))
