"""The COMPACT MODE switch (Angela, 2026-10-02).

Pins Angela's design, piece by piece:

* entering Compact mode REALLY unticks every MCP / tool / agent / skill row
  except System-Metrics, Files-Search and Current-Time, and pauses the
  External MCPs (saved, then restored);
* unticking it ticks EVERYTHING again - refused while the model cannot hold
  everything activated (strict), and a strict model switches it ON by itself;
* the rows apply AT ONCE (global_state + a moving version) - no restart;
* in Compact mode the request binds EXACTLY what is ticked (a gate with no row
  reads OFF), and ticking an agent ticks its tool (and the run companions);
* a CUT answer carries the CONTEXT-WINDOW warning; the not-ready message is ONE
  constant and names the CONTEXT WINDOW;
* the page: the toolbar box, its lock, the cost labels, the CONTEXT-WINDOW
  legend and the CUT reading.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from agent import compact_mode as cm
from agent import context_fitter as cf
from agent import context_governor as cg
from agent.global_state import global_state
from agent.models import Agent, CompactState, Mcp, Skill, Tool

AGENT_DIR = Path(__file__).resolve().parent
REPO = AGENT_DIR.parents[1]


def _seed_rows():
    Mcp.objects.all().delete()
    Tool.objects.all().delete()
    Agent.objects.all().delete()
    Skill.objects.all().delete()
    CompactState.objects.all().delete()
    Mcp.objects.create(idMcp=1, mcpName="mcp-1", mcpDescription="System-Metrics", mcpContent="true")
    Mcp.objects.create(idMcp=2, mcpName="mcp-2", mcpDescription="Files-Search", mcpContent="false")
    for i, descr in enumerate(["Current-Time", "Execute-File", "Chat-Agent-PDFer", "ACPX-Spawn",
                               "Chat-Agent-Run-Wait", "Chat-Agent-Run-Status", "View-Image"], 1):
        Tool.objects.create(idTool=i, toolName=f"tool-{i}", toolDescription=descr, toolContent="true")
    for i, descr in enumerate(["PDFer", "Pythonxer", "ESPHomer"], 1):
        Agent.objects.create(idAgent=i, agentName=f"agent-{i}", agentDescription=descr, agentContent="true")
    Skill.objects.create(name="summarize", enabled=True)
    Skill.objects.create(name="acp-router", enabled=True)


class _SwitchCase(TestCase):
    def setUp(self):
        # global_state is process-wide: every gate these tests flip is put
        # back afterwards, so no other test inherits a Compact selection.
        self._saved_state = dict(global_state._state)
        self.addCleanup(self._restore_state)
        cm.reset_cache()
        _seed_rows()
        self.external_calls = []
        self._patches = [
            patch.object(cm, "_external_active", return_value=["memory"]),
            patch.object(cm, "_set_external_active", side_effect=self.external_calls.append),
            patch.object(cm, "notify", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        cm.reset_cache()

    def _restore_state(self):
        global_state._state.clear()
        global_state._state.update(self._saved_state)

    def tools_on(self):
        return sorted(Tool.objects.filter(toolContent="true").values_list("toolDescription", flat=True))

    def agents_on(self):
        return sorted(Agent.objects.filter(agentContent="true").values_list("agentDescription", flat=True))


# ── Entering and leaving ─────────────────────────────────────────────────────
class EnterLeaveTests(_SwitchCase):
    def test_entering_unticks_everything_but_the_three(self):
        result = cm.enter_compact("test")
        self.assertTrue(result["ok"] and result["changed"])
        self.assertEqual(dict(Mcp.objects.values_list("mcpDescription", "mcpContent")),
                         {"System-Metrics": "true", "Files-Search": "true"})
        self.assertEqual(self.tools_on(), ["Current-Time"])
        self.assertEqual(self.agents_on(), [])
        self.assertFalse(Skill.objects.filter(enabled=True).exists())
        self.assertEqual(self.external_calls, [[]])                       # External MCPs paused
        row = CompactState.objects.get(pk=1)
        self.assertTrue(row.active)
        self.assertEqual(row.saved_external_active, '["memory"]')
        self.assertTrue(cm.is_active())

    def test_leaving_reticks_everything_and_restores_external_mcps(self):
        cm.enter_compact("test")
        result = cm.leave_compact("test")
        self.assertTrue(result["ok"] and result["changed"])
        self.assertEqual(Tool.objects.exclude(toolContent="true").count(), 0)
        self.assertEqual(Agent.objects.exclude(agentContent="true").count(), 0)
        self.assertEqual(Mcp.objects.exclude(mcpContent="true").count(), 0)
        self.assertFalse(Skill.objects.filter(enabled=False).exists())
        self.assertEqual(self.external_calls, [[], ["memory"]])
        self.assertFalse(cm.is_active())

    def test_entering_twice_changes_nothing(self):
        cm.enter_compact("test")
        Agent.objects.filter(agentDescription="PDFer").update(agentContent="true")   # her pick
        again = cm.enter_compact("test")
        self.assertFalse(again["changed"])
        self.assertEqual(self.agents_on(), ["PDFer"])

    def test_a_strict_model_switches_compact_on_by_itself_and_locks_it(self):
        entered = cm.note_capacity(model="qwen2.5:latest", strict=True, window_tokens=16386,
                                   everything_tokens=110_000)
        self.assertTrue(entered)
        self.assertTrue(cm.is_active())
        self.assertEqual(self.tools_on(), ["Current-Time"])
        refused = cm.leave_compact("test")
        self.assertEqual(refused.get("refused"), "strict")
        self.assertIn("qwen2.5:latest", refused["message"])
        self.assertIn("16,386", refused["message"])
        self.assertTrue(cm.is_active())
        self.assertTrue(cm.state()["locked"])

    def test_a_big_model_never_switches_it_on(self):
        self.assertFalse(cm.note_capacity(model="glm-5.3:cloud", strict=False,
                                          window_tokens=1_048_576, everything_tokens=110_000))
        self.assertFalse(cm.is_active())
        self.assertEqual(Tool.objects.exclude(toolContent="true").count(), 0)

    def test_the_lock_lifts_with_a_big_model_and_compact_stays_on(self):
        cm.note_capacity(model="qwen2.5:latest", strict=True, window_tokens=16386)
        cm.note_capacity(model="glm-5.3:cloud", strict=False, window_tokens=1_048_576)
        self.assertTrue(cm.is_active())                  # Angela: "keep compact"
        self.assertFalse(cm.state()["locked"])
        self.assertTrue(cm.leave_compact("test")["ok"])

    def test_the_rows_apply_at_once_and_the_version_moves(self):
        before = cm.toggles_version()
        cm.enter_compact("test")
        self.assertGreater(cm.toggles_version(), before)
        self.assertEqual(global_state.get_state("tool_current-time_status"), "enabled")
        self.assertEqual(global_state.get_state("tool_execute-file_status"), "disabled")
        self.assertEqual(global_state.get_state("agent_pdfer_status"), "disabled")
        self.assertEqual(global_state.get_state("mcp_files_search_status"), "enabled")
        self.assertTrue(global_state.get_state(cm.GLOBAL_ACTIVE_KEY))


# ── Chained rows ─────────────────────────────────────────────────────────────
class LinkedRowsTests(_SwitchCase):
    def _save_agent(self, display, content):
        before = list(Agent.objects.values("agentName", "agentDescription", "agentContent"))
        Agent.objects.filter(agentDescription=display).update(agentContent=content)
        return cm.after_toggles_saved("agent", before)

    def _save_tool(self, descr, content):
        before = list(Tool.objects.values("toolName", "toolDescription", "toolContent"))
        Tool.objects.filter(toolDescription=descr).update(toolContent=content)
        return cm.after_toggles_saved("tool", before)

    def test_ticking_an_agent_ticks_its_tool_and_the_run_companions(self):
        cm.enter_compact("test")
        result = self._save_agent("PDFer", "true")
        self.assertIn("Chat-Agent-PDFer", self.tools_on())
        self.assertIn("Chat-Agent-Run-Wait", self.tools_on())
        self.assertIn("Chat-Agent-Run-Status", self.tools_on())
        self.assertTrue(result["applied"])
        self.assertEqual(global_state.get_state("tool_chat-agent-pdfer_status"), "enabled")

    def test_unticking_an_agent_unticks_its_tool(self):
        self._save_agent("PDFer", "false")
        self.assertNotIn("Chat-Agent-PDFer", self.tools_on())

    def test_ticking_a_wrapped_tool_ticks_its_agent(self):
        cm.enter_compact("test")
        self._save_tool("Chat-Agent-PDFer", "true")
        self.assertIn("PDFer", self.agents_on())

    def test_ticking_a_direct_tool_ticks_the_agent_that_gates_it(self):
        cm.enter_compact("test")
        self._save_tool("Execute-File", "true")
        self.assertIn("Pythonxer", self.agents_on())

    def test_companions_are_left_alone_outside_compact_mode(self):
        Tool.objects.filter(toolDescription__startswith="Chat-Agent-Run").update(toolContent="false")
        Agent.objects.filter(agentDescription="PDFer").update(agentContent="false")
        self._save_agent("PDFer", "true")
        self.assertNotIn("Chat-Agent-Run-Wait", self.tools_on())


# ── What a request binds ─────────────────────────────────────────────────────
class BindingTests(_SwitchCase):
    def setUp(self):
        super().setUp()
        self._ext = patch("agent.external_mcp_manager.get_external_mcp_tools", return_value=[])
        self._ext.start()

    def tearDown(self):
        self._ext.stop()
        super().tearDown()

    def names(self):
        from agent.tools import get_mcp_tools
        return [t.name for t in get_mcp_tools()]

    def test_compact_mode_binds_exactly_the_selection(self):
        cm.enter_compact("test")
        self.assertEqual(self.names(), ["get_current_time"])
        before = list(Agent.objects.values("agentName", "agentDescription", "agentContent"))
        Agent.objects.filter(agentDescription="PDFer").update(agentContent="true")
        cm.after_toggles_saved("agent", before)
        names = self.names()
        self.assertIn("chat_agent_pdfer", names)
        self.assertIn("chat_agent_run_wait", names)
        self.assertNotIn("chat_agent_esphomer", names)       # not ticked: not bound
        self.assertNotIn("window_present", names)            # no row: OFF in Compact mode

    def test_outside_compact_mode_a_missing_row_still_fails_open(self):
        cm.apply_rows_to_global_state("test")
        self.assertIn("window_present", self.names())

    def test_everything_activated_is_every_built_in_tool(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        from agent.tools import get_mcp_tools
        cm.enter_compact("test")
        every = [t.name for t in get_mcp_tools(ignore_gates=True)]
        self.assertGreaterEqual(len([n for n in every if n.startswith("chat_agent_") and
                                     n not in {"chat_agent_run_list", "chat_agent_run_status",
                                               "chat_agent_run_log", "chat_agent_run_stop",
                                               "chat_agent_run_wait"}]),
                                len(WRAPPED_CHAT_AGENT_SPECS))
        self.assertIn("get_current_time", every)

    def test_the_costs_project_every_gate(self):
        data = cm.costs()
        self.assertTrue(data["ok"])
        entry = next(e for e in data["entries"] if e["key"] == "chat-agent-pdfer")
        self.assertEqual(entry["agent"], "pdfer")
        self.assertGreater(entry["tokens"], 50)
        self.assertGreater(data["agents"]["pdfer"], 50)
        self.assertIn("current-time", data["enabled_tools"])
        self.assertIn("pdfer", data["enabled_agents"])

    def test_an_acpx_row_is_gated_by_its_name(self):
        # The seeded ACPX rows are named "acpx-spawn" but described "ACP spawn";
        # the gate reads the NAME, so ticking the row must reach the tool.
        Tool.objects.create(idTool=50, toolName="acpx-spawn", toolDescription="ACP spawn",
                            toolContent="false")
        cm.enter_compact("test")
        self.assertNotIn("acp_spawn", self.names())
        before = list(Tool.objects.values("toolName", "toolDescription", "toolContent"))
        Tool.objects.filter(toolName="acpx-spawn").update(toolContent="true")
        cm.after_toggles_saved("tool", before)
        self.assertEqual(global_state.get_state("tool_acpx-spawn_status"), "enabled")
        self.assertIn("acp_spawn", self.names())
        entry = next(e for e in cm.costs()["entries"] if e["key"] == "acp spawn")
        self.assertGreater(entry["tokens"], 50)          # labelled by the text the dialog shows


# ── The fitter obeys the switch ──────────────────────────────────────────────
class _FakeLLM:
    model = "qwen2.5:latest"
    base_url = "http://127.0.0.1:11434"

    def bind_tools(self, tools):
        return self


def _tool(name, description="A tool."):
    return SimpleNamespace(name=name, description=description, args={})


class FitObeysTheSwitchTests(SimpleTestCase):
    PROMPT = (AGENT_DIR / "prompt.pmt").read_text(encoding="utf-8")

    def _cae(self, tools):
        from agent.mcp_agent import CapabilityAwareToolAgentExecutor
        cae = CapabilityAwareToolAgentExecutor(llm=_FakeLLM(), preeliminary_prompt=self.PROMPT,
                                               tools=tools, max_iterations=2)
        cae._everything_chars = 400_000          # everything activated ~133K tokens
        return cae

    def _fit(self, cae, *, ceiling, acpx=False):
        from agent.acpx import filter_acpx_tools
        cfg = {"context_ceiling_tokens": ceiling}
        with patch("agent.mcp_agent._load_config", return_value=cfg), \
             patch.object(cm, "is_active", return_value=True), \
             patch.object(cm, "note_capacity", return_value=False), \
             patch.object(cm, "note_self_modify", return_value=False), \
             patch.object(type(cae), "_refresh_toggle_tool_surface", return_value=False):
            return cae.fit_request(input_text="Make a PDF of the plan", chat_history=[],
                                   request_tools=filter_acpx_tools(cae.tools, acpx),
                                   acpx_requested=acpx, user_id="u-compact")

    def test_a_big_model_in_compact_mode_sends_exactly_the_ticked_tools(self):
        picks = [_tool("get_current_time"), _tool("chat_agent_pdfer"), _tool("chat_agent_run_wait"),
                 _tool("external_mcp_status"), _tool("ext__memory__read_graph")]
        fit = self._fit(self._cae(picks), ceiling=1_000_000)
        self.assertEqual(fit["mode"], cf.MODE_COMPACT)
        self.assertEqual([t.name for t in fit["tools"]],
                         ["get_current_time", "chat_agent_pdfer", "chat_agent_run_wait"])
        report = fit["report"]
        self.assertTrue(report.compact_active)
        self.assertFalse(report.strict)
        self.assertIn("Compact mode is switched on", fit["executor"].system_prompt)
        self.assertIn("`chat_agent_pdfer`", fit["executor"].system_prompt)

    def test_a_small_model_is_strict_and_keeps_her_selection(self):
        picks = [_tool("get_current_time"), _tool("chat_agent_esphomer")]
        fit = self._fit(self._cae(picks), ceiling=16386)
        report = fit["report"]
        self.assertTrue(report.strict)
        self.assertEqual([t.name for t in fit["tools"]], ["get_current_time", "chat_agent_esphomer"])
        self.assertTrue(report.as_capacity()["locked"])
        self.assertIn("qwen2.5:latest is a small model", fit["executor"].system_prompt)

    def test_ticked_acpx_tools_ride_along_when_acpx_is_on(self):
        picks = [_tool("get_current_time"), _tool("acp_spawn")]
        fit = self._fit(self._cae(picks), ceiling=1_000_000, acpx=True)
        self.assertIn("acp_spawn", [t.name for t in fit["tools"]])
        self.assertFalse(fit["report"].as_capacity()["acpx_off"])
        self.assertTrue(fit["acpx_bound"])


# ── A CUT answer says so ─────────────────────────────────────────────────────
class CutWarningTests(SimpleTestCase):
    UID = "test-compact-cut"

    def setUp(self):
        cg.begin_turn(self.UID, label="cut test")

    def tearDown(self):
        cg.end_turn(self.UID)

    def test_a_live_cut_is_remembered_for_the_answer(self):
        cg._note_frame_cut(self.UID, {"truncated": True, "kind": "live", "window_real": 16386,
                                      "tokens_sent_estimate": 69_000, "model": "qwen2.5:latest"})
        cut = cg.turn_cut(self.UID)
        self.assertEqual(cut["window"], 16386)
        html = cm.cut_warning_html(cut)
        self.assertIn("CONTEXT-WINDOW exceeded", html)
        self.assertIn("16,386", html)
        self.assertIn("69,000", html)
        self.assertIn('class="tlm-cut-warning"', html)

    def test_an_at_rest_probe_never_leaves_a_warning(self):
        cg._note_frame_cut(self.UID, {"truncated": True, "kind": cg.KIND_REST, "window_real": 16386})
        self.assertIsNone(cg.turn_cut(self.UID))

    def test_a_refitted_first_step_forgets_its_cut(self):
        cg._note_frame_cut(self.UID, {"truncated": True, "kind": "live", "window_real": 16386})
        cg.clear_turn_cut(self.UID)
        self.assertIsNone(cg.turn_cut(self.UID))

    def _executor(self, accept):
        from agent.mcp_agent import MultiTurnToolAgentExecutor
        ex = MultiTurnToolAgentExecutor.__new__(MultiTurnToolAgentExecutor)
        ex._fit_steps = 0
        ex._tool_calls_log = []
        ex._healer = SimpleNamespace(last_tactic="", UNCHANGED_REQUEST_TACTICS=frozenset())
        ex.bound_llm = None
        ex.accept_context_cut = accept
        return ex

    def test_the_last_attempt_answers_from_a_cut_request(self):
        llm = SimpleNamespace(model="qwen2.5:latest", base_url="http://127.0.0.1:11434")
        with patch("agent.mcp_agent._context_usage_from", return_value={"prompt_tokens": 16386}), \
             patch.object(cg, "note_real_count", return_value={"truncated": True, "window": 16386}):
            self._executor(True)._check_context_cut(llm, [], object(), "step")      # no raise
            with self.assertRaises(cf.ContextWindowExceeded):
                self._executor(False)._check_context_cut(llm, [], object(), "step")


# ── One message, and the page ────────────────────────────────────────────────
class MessageAndPageTests(SimpleTestCase):
    def test_the_not_ready_message_is_one_constant_that_names_the_context_window(self):
        from agent import constants
        msg = constants.ERROR_AGENT_NOT_READY
        # First person, to the user by name (Angela, 2026-10-09).
        self.assertTrue(msg.startswith("I'm sorry, {name}, I can't process your requests right now. <br>"))
        self.assertTrue(constants.say(msg, "Angela").startswith(
            "I'm sorry, Angela, I can't process your requests right now. <br>"))
        self.assertTrue(constants.say(msg, "").startswith(
            "I'm sorry, I can't process your requests right now. <br>"))
        self.assertIn("outside of the root directory", msg)
        self.assertIn("CONTEXT WINDOW", msg)
        self.assertIn("CONTEXT-WINDOW gauge", msg)
        consumers = (AGENT_DIR / "consumers.py").read_text(encoding="utf-8")
        self.assertNotIn('not_ready_response = "', consumers)
        bridge = (AGENT_DIR / "agents" / "teletlamatini" / "teletlamatini.py").read_text(encoding="utf-8")
        self.assertIn("i can't process your requests", bridge)
        self.assertIn("i can't process your requests", msg.lower())

    def test_saving_a_dialog_no_longer_asks_for_a_restart(self):
        consumers = (AGENT_DIR / "consumers.py").read_text(encoding="utf-8")
        for kind in ("MCPs activation: ", "Tools activation: ", "Agents activation: "):
            self.assertNotIn(kind, consumers)
        for kind in ("'mcp'", "'tool', before_rows", "'agent', before_rows", "'skill'"):
            self.assertIn("self._after_toggles_saved(" + kind, consumers)
        self.assertIn("type == 'set-compact-mode'", consumers)
        self.assertIn("type == 'compact-mode-sync'", consumers)

    def test_a_saved_dialog_is_summarised_not_dumped(self):
        from agent.consumers import AgentConsumer
        msg = AgentConsumer._toggles_summary(
            "Agents", "agent-1=ACPXer=false,agent-23=ESPHomer=true,agent-24=Executer=false,")
        self.assertEqual(msg, "I've saved your Agents activation: 1 of 3 on (ESPHomer).")
        many = ",".join(f"agent-{i}=A{i}=true" for i in range(1, 21))
        self.assertIn("20 of 20 on", AgentConsumer._toggles_summary("Agents", many))
        self.assertIn("and 5 more", AgentConsumer._toggles_summary("Agents", many))

    def test_agent_choices_survive_a_restart(self):
        apps = (AGENT_DIR / "apps.py").read_text(encoding="utf-8")
        self.assertIn("agentContent=previous_flags.get(display_name.lower(), new_agent_flag)", apps)
        self.assertNotIn("agentContent='true' # Keeps existing convention", apps)

    def test_the_toolbar_box_and_its_scripts(self):
        tpl = (AGENT_DIR / "templates" / "agent" / "agent_page.html").read_text(encoding="utf-8")
        self.assertIn('id="compact-mode-enabled"', tpl)
        self.assertIn('id="compact-mode-toggle"', tpl)
        self.assertLess(tpl.index("agent/js/model_capacity.js"), tpl.index("agent/js/compact_costs.js"))
        js = (AGENT_DIR / "static" / "agent" / "js" / "model_capacity.js").read_text(encoding="utf-8")
        self.assertIn("'set-compact-mode'", js)
        self.assertIn("'compact-mode-sync'", js)
        self.assertIn("'tlm:compact-mode-state'", js)
        self.assertNotIn("lockAcpx", js)                     # ACPX follows the rows now
        chat = (AGENT_DIR / "static" / "agent" / "js" / "agent_page_chat.js").read_text(encoding="utf-8")
        self.assertIn("data.type === 'compact-mode-state'", chat)

    def test_the_cost_labels_read_the_real_route(self):
        js = (AGENT_DIR / "static" / "agent" / "js" / "compact_costs.js").read_text(encoding="utf-8")
        route = re.search(r"COSTS_URL = '/agent/([^']+)'", js).group(1)
        self.assertIn(f"path('{route}'", (AGENT_DIR / "urls.py").read_text(encoding="utf-8"))
        self.assertEqual(re.findall(r"window\.([A-Za-z_]\w*)\s*=(?!=)", js), [])

    def test_the_gauge_says_context_window_and_shows_the_true_share(self):
        js = (AGENT_DIR / "static" / "agent" / "js" / "context_gauge.js").read_text(encoding="utf-8")
        self.assertIn("'CONTEXT-WINDOW'", js)
        self.assertIn("var pctTrue = Math.max(0, ratio * 100);", js)
        self.assertIn("'CUT · read '", js)
        self.assertIn("Math.round(pctTrue) + '%'", js)

    def test_no_template_comment_spans_two_lines(self):
        # Django hides a {# #} comment ONLY when it fits on one line; a comment
        # split over lines is printed on the page as text (Angela saw it there).
        bad = []
        for path in (AGENT_DIR / "templates").rglob("*.html"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    bad.append(f"{path.name}:{n}")
        self.assertEqual(bad, [], "use {% comment %}...{% endcomment %} for a long comment")

    def test_it_ships_with_the_build(self):
        runtime = (REPO / "build_runtime_assets.py").read_text(encoding="utf-8")
        self.assertIn("agent/js/compact_costs.js", runtime)
        snapshot = (REPO / "copy_source_assets.py").read_text(encoding="utf-8")
        for name in ("compact_mode.py", "0211_compact_state.py", "compact_costs.js"):
            self.assertIn(name, snapshot)
