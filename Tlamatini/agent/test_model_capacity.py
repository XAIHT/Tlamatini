"""COMPACT MODE - every request fits the model it is sent to (Angela, 2026-10-01).

Pins the whole chain that keeps a small local model from being fed a request
Ollama silently cuts:

* ``context_governor.note_real_count`` - a request is called CUT only when the
  characters sent cannot fit in the tokens Ollama says it read; the count IS
  the window; ``resolve_ceiling_tokens`` then answers with it.
* ``context_fitter`` - Angela's prompt.pmt rebuilt by rule priority, the
  question never cut before its attached context, the newest history kept.
* ``CapabilityAwareToolAgentExecutor.fit_request`` - a big model gets the
  COMPLETE request byte for byte; a small one gets ONLY Current-Time, ACPX off,
  External MCPs paused, and the verdict reaches the page.
* the first-step cut guard + re-fit, and the page wiring (template, JS module).

Every number in the real-world tests comes from the 2026-10-01 log of the
installed build: qwen2.5:latest, 210,845 bytes sent, prompt_eval_count 16386.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from agent import compact_mode as cm
from agent import context_fitter as cf
from agent import context_governor as cg

AGENT_DIR = Path(__file__).resolve().parent
PROMPT = (AGENT_DIR / "prompt.pmt").read_text(encoding="utf-8")


class _Reset(SimpleTestCase):
    def setUp(self):
        cg.forget_learned_windows()
        cm.reset_cache()          # the Self-modify verdict is process-wide too
        with cg._CAPACITY_LOCK:
            cg._CAPACITY.clear()

    def tearDown(self):
        cg.forget_learned_windows()
        cm.reset_cache()
        with cg._CAPACITY_LOCK:
            cg._CAPACITY.clear()


# ── The effective window ────────────────────────────────────────────────────
class EffectiveWindowTests(_Reset):
    MODEL = "qwen2.5:latest"
    BASE = "http://127.0.0.1:11434"

    def test_the_real_cut_from_the_installed_log_is_detected_and_learned(self):
        verdict = cg.note_real_count(self.MODEL, self.BASE, 16386, 207_000, source="test")
        self.assertTrue(verdict["truncated"])
        self.assertEqual(verdict["window"], 16386)
        self.assertEqual(cg.learned_window(self.MODEL, self.BASE), 16386)

    def test_localhost_and_127_are_the_same_server(self):
        cg.note_real_count(self.MODEL, "http://localhost:11434", 16386, 207_000)
        self.assertEqual(cg.learned_window(self.MODEL, "http://127.0.0.1:11434/"), 16386)

    def test_an_ordinary_request_is_not_called_cut(self):
        verdict = cg.note_real_count(self.MODEL, self.BASE, 11_000, 40_000)
        self.assertFalse(verdict["truncated"])
        self.assertIsNone(cg.learned_window(self.MODEL, self.BASE))
        self.assertAlmostEqual(cg.measured_chars_per_token(self.MODEL, self.BASE), 40_000 / 11_000, 3)

    def test_a_tiny_request_is_never_judged(self):
        verdict = cg.note_real_count(self.MODEL, self.BASE, 10, 3_000)
        self.assertFalse(verdict["truncated"])

    def test_the_learned_window_wins_the_ceiling(self):
        cg.note_real_count(self.MODEL, self.BASE, 16386, 207_000)
        tokens, source = cg.resolve_ceiling_tokens(
            {"ollama_base_url": self.BASE, "ollama_num_ctx": 1048576}, model=self.MODEL)
        self.assertEqual(tokens, 16386)
        self.assertIn("learned", source)

    def test_an_explicit_config_ceiling_still_wins_over_learning(self):
        cg.note_real_count(self.MODEL, self.BASE, 16386, 207_000)
        tokens, source = cg.resolve_ceiling_tokens({"context_ceiling_tokens": 64000}, model=self.MODEL)
        self.assertEqual((tokens, source), (64000, "config"))

    def test_reading_more_than_the_learned_window_forgets_it(self):
        cg.note_real_count(self.MODEL, self.BASE, 16386, 207_000)
        cg.note_real_count(self.MODEL, self.BASE, 30_000, 100_000)
        self.assertIsNone(cg.learned_window(self.MODEL, self.BASE))

    def test_a_cut_count_is_never_drawn_as_half_full(self):
        frame = {"chars_total": 207_000, "tokens_estimated": 51_678, "ceiling_tokens": 32768,
                 "watermarks": {"compact": 0.6, "fold": 0.75, "floor": 0.85}}
        cg.apply_real_tokens(frame, {"prompt_tokens": 16386})
        self.assertTrue(frame["truncated"])
        # 2026-10-02: the TRUE share - what was sent against what the model
        # read (207,000 chars / 3 per token = 69,000 of 16,386 = ~421%).
        self.assertEqual(frame["window_real"], 16386)
        self.assertEqual(frame["tokens_sent_estimate"], 69_000)
        self.assertAlmostEqual(frame["ratio"], 69_000 / 16386, 3)
        self.assertGreater(frame["ratio"], 1.0)
        self.assertEqual(frame["zone"], cg.ZONE_FLOOR)
        self.assertIn("16386 of about 69000", frame["truncated_note"])

    def test_every_gauge_frame_carries_the_capacity_verdict(self):
        sent = []
        cg.register_gauge_sink("u1", sent.append)
        try:
            cg.set_capacity("u1", {"mode": "compact", "model": self.MODEL, "window_tokens": 16386})
            cg.publish_gauge("u1", {"ok": True})
        finally:
            cg.unregister_gauge_sink("u1")
        self.assertEqual(sent[-1]["capacity"]["mode"], "compact")

    def test_set_capacity_reports_only_real_changes(self):
        info = {"mode": "compact", "model": self.MODEL, "window_tokens": 16386}
        self.assertTrue(cg.set_capacity("u2", info))
        self.assertFalse(cg.set_capacity("u2", dict(info)))
        self.assertTrue(cg.set_capacity("u2", dict(info, mode="full")))


# ── Angela's prompt, rebuilt by priority ────────────────────────────────────
class CompactPromptTests(SimpleTestCase):
    def test_every_rule_is_found(self):
        titles = [s.title for s in cf.split_prompt(PROMPT) if s.kind == "rule"]
        self.assertTrue(any(t.startswith("2) System Context rule") for t in titles))
        self.assertTrue(any("Conflict resolution" in t for t in titles))

    def test_a_16k_budget_keeps_the_core_and_drops_what_a_small_model_lacks(self):
        out, info = cf.compact_prompt(PROMPT, 15_700)
        self.assertLessEqual(len(out), 15_700)
        for must in ("System Context rule", "END-RESPONSE", "BEGIN-CODE", "Tlamatini",
                     "Angela López Mendoza", "Conflict resolution"):
            self.assertIn(must, out)
        for gone in ("Tool-usage and Multi-Turn workflow rule", "ACPX mechanics rule",
                     "External MCP runtime", "Voice command rule", "QUICK MAP"):
            self.assertNotIn(gone, out)
        self.assertEqual(info["prompt_profile"], "compact")

    def test_no_sentinel_or_template_debris_reaches_the_agent(self):
        out, _ = cf.compact_prompt(PROMPT, 30_000, keep_placeholders=False)
        self.assertNotIn("<!--", out)
        for ph in ("{system_context}", "{files_context}", "{context}"):
            self.assertNotIn(ph, out)

    def test_a_template_keeps_its_placeholders(self):
        out, _ = cf.compact_prompt(PROMPT, 15_700, keep_placeholders=True)
        for ph in ("{system_context}", "{files_context}", "{context}"):
            self.assertIn(ph, out)

    def test_a_tiny_window_gets_the_micro_prompt(self):
        out, info = cf.compact_prompt(PROMPT, 2_000)
        self.assertEqual(info["prompt_profile"], "micro")
        self.assertIn("END-RESPONSE", out)
        self.assertIn("Angela López Mendoza", out)
        tmpl, _ = cf.compact_prompt(PROMPT, 2_000, keep_placeholders=True)
        self.assertIn("{system_context}", tmpl)

    def test_a_loaded_project_keeps_the_context_usage_rule(self):
        without, _ = cf.compact_prompt(PROMPT, 15_700)
        with_ctx, _ = cf.compact_prompt(PROMPT, 15_700, context_loaded=True)
        self.assertNotIn("5) Context usage rule", without)
        self.assertIn("5) Context usage rule", with_ctx)

    def test_the_compact_note_is_honest_about_what_is_missing(self):
        note = cf.compact_tool_rule(["get_current_time"], model="qwen2.5:latest", window_tokens=16386)
        self.assertIn("`get_current_time`", note)
        self.assertIn("16,386", note)
        self.assertIn("Config > Models", note)
        self.assertIn("never claim you ran something", note)

    def test_the_compact_note_carries_the_three_rules_qwen_needed(self):
        # Each rule answers a failure measured on qwen2.5:latest (2026-10-01).
        note = cf.compact_tool_rule(["get_current_time"], model="qwen2.5:latest")
        self.assertIn("Answer ONLY the user's newest message", note)        # re-answered the factorial
        self.assertIn("raw HTML <table>", note)                              # fenced table shown as text
        self.assertIn("Never put a table inside ``` fences", note)
        self.assertIn("I can't do that right now", note)                    # "use absolute paths" lecture
        self.assertIn("qwen2.5:latest is a small model", note)
        self.assertTrue(note.rstrip().endswith("END-RESPONSE."))

    def test_the_tool_less_rules_are_safe_inside_a_prompt_template(self):
        rules = cf.compact_answer_rules(model="qwen2.5:latest", window_tokens=16386)
        self.assertNotIn("{", rules)
        self.assertNotIn("}", rules)
        self.assertIn("Tools you may call now: none", rules)


# ── Fitting the question and the history ────────────────────────────────────
class FitInputAndHistoryTests(SimpleTestCase):
    def test_the_attached_context_shrinks_before_the_question(self):
        question = "What does main() do?"
        text = (cg.CONTEXT_FALLBACK_OPEN + ("x" * 50_000) + cg.CONTEXT_FALLBACK_CLOSE
                + " fallback note.\n\nUser Question: " + question)
        out, info = cf.fit_input(text, 8_000)
        self.assertLessEqual(len(out), 8_000)
        self.assertTrue(out.endswith(question))
        self.assertTrue(info["input_clipped"])
        self.assertIn("omitted so this request fits", out)

    def test_a_small_input_is_untouched(self):
        out, info = cf.fit_input("System Context: {'cpu_usage': 8.5}\n\nCPU?", 8_000)
        self.assertEqual(out, "System Context: {'cpu_usage': 8.5}\n\nCPU?")
        self.assertFalse(info["input_clipped"])

    def test_the_newest_history_is_kept_and_long_answers_are_clipped(self):
        history = [{"role": "user", "content": f"q{i}"} for i in range(6)]
        history.append({"role": "assistant", "content": "A" * 9_000})
        history.append({"role": "user", "content": "CPU?"})
        kept, info = cf.fit_history(history, 3_000, input_text="System Context: x\n\nCPU?",
                                    max_messages=6, per_message_cap=1_200)
        self.assertEqual(kept[-1]["content"], "CPU?")            # the question itself, intact
        self.assertLessEqual(len(kept[-2]["content"]), 1_200)    # the long answer, clipped
        self.assertGreaterEqual(info["history_clipped"], 1)
        self.assertEqual(history[-2]["content"], "A" * 9_000)    # the original is never mutated


# ── The decision: complete or compact ───────────────────────────────────────
class _FakeLLM:
    model = "qwen2.5:latest"
    base_url = "http://127.0.0.1:11434"

    def bind_tools(self, tools):
        return self


def _tool(name, description="A tool."):
    return SimpleNamespace(name=name, description=description, args={})


def _cae(tools):
    from agent.mcp_agent import CapabilityAwareToolAgentExecutor
    return CapabilityAwareToolAgentExecutor(llm=_FakeLLM(), preeliminary_prompt=PROMPT,
                                            tools=tools, max_iterations=2)


_TOOLS = ([_tool("get_current_time", "Return the current date and time.")]
          + [_tool(f"chat_agent_demo_{i}", "Demo agent. " * 400) for i in range(40)]
          + [_tool("acp_spawn", "Spawn an ACP child."), _tool("ext__memory__read_graph", "Read.")])


class FitRequestTests(_Reset):
    def _fit(self, cae, *, ceiling, setting="auto", acpx=False, multi_turn=False):
        cfg = {"context_ceiling_tokens": ceiling, "context_compact_mode": setting}
        with patch("agent.mcp_agent._load_config", return_value=cfg), \
             patch.object(type(cae), "_active_external_servers", return_value=["memory"]):
            from agent.acpx import filter_acpx_tools
            return cae.fit_request(input_text="What is the CPU usage?", chat_history=[],
                                   request_tools=filter_acpx_tools(cae.tools, acpx),
                                   multi_turn=multi_turn, acpx_requested=acpx, user_id="u9")

    def test_a_big_model_gets_the_complete_request_byte_for_byte(self):
        from agent.mcp_agent import _build_system_prompt
        cae = _cae(list(_TOOLS))
        fit = self._fit(cae, ceiling=1_000_000)
        self.assertEqual(fit["mode"], cf.MODE_FULL)
        self.assertEqual(fit["executor"].system_prompt,
                         _build_system_prompt(PROMPT, fit["tools"]))
        self.assertEqual(fit["input"], "What is the CPU usage?")

    def test_a_small_model_runs_compact_with_current_time_only(self):
        cae = _cae(list(_TOOLS))
        fit = self._fit(cae, ceiling=16386, acpx=True)
        self.assertEqual(fit["mode"], cf.MODE_COMPACT)
        self.assertEqual([t.name for t in fit["tools"]], ["get_current_time"])
        report = fit["report"]
        self.assertEqual(report.tools_kept, ["get_current_time"])
        self.assertEqual(report.external_mcps_paused, ["memory"])
        self.assertTrue(report.as_capacity()["acpx_off"])
        self.assertIn("COMPACT MODE", fit["executor"].system_prompt)
        self.assertNotIn("acp_spawn", [t.name for t in fit["executor"].tools])
        self.assertLess(report.fitted_tokens_estimate, 16386)

    def test_the_verdict_reaches_the_page(self):
        cae = _cae(list(_TOOLS))
        self._fit(cae, ceiling=16386)
        cap = cg.capacity_for("u9")
        self.assertEqual(cap["mode"], "compact")
        self.assertEqual(cap["window_tokens"], 16386)
        self.assertIn("System-Metrics", cap["sidecars"])

    def test_a_current_time_the_user_switched_off_stays_off(self):
        cae = _cae([t for t in _TOOLS if t.name != "get_current_time"])
        fit = self._fit(cae, ceiling=16386)
        self.assertEqual(fit["tools"], [])

    def test_explicit_settings_are_obeyed_exactly(self):
        cae = _cae(list(_TOOLS))
        self.assertEqual(self._fit(cae, ceiling=16386, setting="never")["mode"], cf.MODE_FULL)
        self.assertEqual(self._fit(cae, ceiling=1_000_000, setting="always")["mode"], cf.MODE_COMPACT)

    def test_a_cut_first_step_is_refitted_and_sent_again(self):
        from agent.mcp_agent import CapabilityAwareToolAgentExecutor
        cae = _cae(list(_TOOLS))
        calls = {"n": 0}

        def _run(self_, fit, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise cf.ContextWindowExceeded(16386, "qwen2.5:latest")
            return {"output": "answered from a fitted request", "mode": fit["mode"]}

        with patch.object(CapabilityAwareToolAgentExecutor, "_run_fitted", _run), \
             patch("agent.mcp_agent._load_config", return_value={"context_ceiling_tokens": 16386}), \
             patch.object(CapabilityAwareToolAgentExecutor, "_active_external_servers", return_value=[]):
            result = cae.invoke({"input": "CPU?", "chat_history": []})
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result["output"], "answered from a fitted request")


# ── What the user SEES from a small model ───────────────────────────────────
class DisplayTableTests(SimpleTestCase):
    """qwen2.5:latest fenced the planets table twice in the visible test, so
    the user saw tags instead of a table."""

    TABLE = "<table><tr><th>Planet</th></tr><tr><td>Mars</td></tr></table>"
    FENCED = "Here it is:\n\n```html\n" + TABLE + "\n```\nEND-RESPONSE"

    def test_a_fenced_table_the_user_asked_to_see_is_shown_as_a_table(self):
        out, n = cf.unwrap_display_tables(self.FENCED, "Show me an HTML table of three planets.")
        self.assertEqual(n, 1)
        self.assertNotIn("```", out)
        self.assertIn(self.TABLE, out)
        self.assertTrue(out.rstrip().endswith("END-RESPONSE"))

    def test_a_table_wrapped_in_one_div_is_shown_too(self):
        fenced = "```html\n<div style=\"overflow:auto\">" + self.TABLE + "</div>\n```"
        out, n = cf.unwrap_display_tables(fenced, "Show me the planets in a table")
        self.assertEqual(n, 1)
        self.assertNotIn("```", out)

    def test_a_table_put_in_an_html_file_block_is_shown_too(self):
        # qwen2.5:latest, third run: BEGIN-CODE<<<planets_diameters.html>>>.
        for body in (self.TABLE, "```html\n" + self.TABLE + "\n```"):
            answer = "BEGIN-CODE<<<planets_diameters.html>>>\n" + body + "\nEND-CODE\nEND-RESPONSE"
            out, n = cf.unwrap_display_tables(answer, "Show me an HTML table of three planets.")
            self.assertEqual(n, 1, body)
            self.assertNotIn("BEGIN-CODE", out)
            self.assertNotIn("```", out)
            self.assertIn(self.TABLE, out)
        py = "BEGIN-CODE<<<factorial.py>>>\ndef f(): pass\nEND-CODE"
        self.assertEqual(cf.unwrap_display_tables(py + "\n" + self.TABLE, "Show me a table")[1], 0)

    def test_a_comment_after_the_table_does_not_hide_it(self):
        # qwen2.5:latest, fifth run: "<!-- END-RESPONSE -->" inside the fence.
        answer = "```html\n<div>" + self.TABLE + "</div>\n<!-- END-RESPONSE -->\n```"
        out, n = cf.unwrap_display_tables(answer, "Show me an HTML table of three planets.")
        self.assertEqual(n, 1)
        self.assertNotIn("<!--", out)
        self.assertIn("END-RESPONSE", out)                 # the sentinel survives

    def test_a_table_asked_for_as_code_or_a_file_stays_fenced(self):
        for question in ("Give me the HTML code for a planets table.",
                         "Write an HTML page with a planets table",
                         "Dame el código HTML de una tabla"):
            out, n = cf.unwrap_display_tables(self.FENCED, question)
            self.assertEqual((n, out), (0, self.FENCED), question)

    def test_anything_beyond_plain_table_markup_stays_fenced(self):
        for body in (self.TABLE.replace("<td>Mars", "<td onclick=\"steal()\">Mars"),
                     self.TABLE + "<script>alert(1)</script>",
                     "<div>" + self.TABLE + "<img src=x></div>",
                     "<p>no table here</p>"):
            fenced = "```html\n" + body + "\n```"
            out, n = cf.unwrap_display_tables(fenced, "Show me a table")
            self.assertEqual((n, out), (0, fenced), body)


class CompactAccessGuardTests(SimpleTestCase):
    """The one-shot file-access guard used to answer a Compact user with
    "give me an absolute path" - a dead end when no file tool is bound."""

    UID = "test-compact-access-guard"

    def tearDown(self):
        with cg._CAPACITY_LOCK:
            cg._CAPACITY.pop(self.UID, None)

    def test_compact_mode_gets_the_true_reason(self):
        from agent.rag import interface
        cg.set_capacity(self.UID, {"mode": "compact", "model": "qwen2.5:latest",
                                   "window_tokens": 32768})
        msg = interface._compact_mode_access_message(self.UID)
        self.assertIn("I can't do that right now", msg)
        self.assertIn("qwen2.5:latest", msg)
        self.assertIn("32,768", msg)
        self.assertIn("Config", msg)
        self.assertNotIn("absolute", msg)

    def test_full_mode_keeps_the_guards_own_message(self):
        from agent.rag import interface
        cg.set_capacity(self.UID, {"mode": "full", "model": "glm-5.3:cloud"})
        self.assertIsNone(interface._compact_mode_access_message(self.UID))
        self.assertIsNone(interface._compact_mode_access_message("nobody-has-this-id"))


# ── The page ────────────────────────────────────────────────────────────────
class PageWiringTests(SimpleTestCase):
    TEMPLATE = (AGENT_DIR / "templates" / "agent" / "agent_page.html").read_text(encoding="utf-8")
    JS = (AGENT_DIR / "static" / "agent" / "js" / "model_capacity.js").read_text(encoding="utf-8")

    def test_the_module_and_its_styles_are_loaded(self):
        self.assertIn("agent/js/model_capacity.js", self.TEMPLATE)
        self.assertIn("agent/css/model_capacity.css", self.TEMPLATE)

    def test_dialog_theme_stays_the_last_stylesheet(self):
        links = re.findall(r'<link rel="stylesheet" href="\{% static \'agent/css/([^\']+)\'', self.TEMPLATE)
        self.assertEqual(links[-1], "dialog_theme.css")

    def test_the_dialog_follows_the_dismissal_policy(self):
        self.assertIn("'tlm-compact-overlay'", self.JS)          # matches [id$="-overlay"]
        self.assertIn("overlay.tlmDismiss = closeDialog", self.JS)
        self.assertIn("aria-label', 'Close'", self.JS)
        self.assertNotIn("closeOnEscape", self.JS)

    def test_it_reads_the_verdict_from_every_gauge_frame(self):
        self.assertIn("'tlm:context-gauge'", self.JS)
        self.assertIn("frame.capacity", self.JS)

    def test_it_exports_one_global_only(self):
        assigned = set(re.findall(r"window\.([A-Za-z_]\w*)\s*=(?!=)", self.JS))
        self.assertEqual(assigned, {"TlmModelCapacity"})


class ReadableTableTests(SimpleTestCase):
    """qwen2.5:latest painted its table white and left the cells inheriting
    the chat's near-white text - the table rendered and nobody could read it."""

    TEMPLATE = PageWiringTests.TEMPLATE
    JS = (AGENT_DIR / "static" / "agent" / "js" / "chat_table_contrast.js").read_text(encoding="utf-8")

    def test_the_guard_is_loaded_on_the_chat_page(self):
        self.assertIn("agent/js/chat_table_contrast.js", self.TEMPLATE)

    def test_it_measures_against_the_wcag_floor_and_fixes_only_unreadable_cells(self):
        self.assertIn("MIN_RATIO = 3.0", self.JS)
        self.assertIn("contrast(fg, bg) >= MIN_RATIO", self.JS)    # readable cells keep their colours
        self.assertIn("0.2126", self.JS)                            # WCAG relative luminance

    def test_it_never_touches_exec_report_tables_or_unmeasurable_backgrounds(self):
        self.assertIn(".exec-report-table, .exec-report", self.JS)
        self.assertIn("backgroundImage", self.JS)

    def test_it_declares_no_globals(self):
        self.assertEqual(re.findall(r"window\.([A-Za-z_]\w*)\s*=(?!=)", self.JS), [])

    def test_it_ships_with_the_build(self):
        repo = AGENT_DIR.parents[1]
        self.assertIn("agent/js/chat_table_contrast.js",
                      (repo / "build_runtime_assets.py").read_text(encoding="utf-8"))
        snapshot = (repo / "copy_source_assets.py").read_text(encoding="utf-8")
        for name in ("context_fitter.py", "model_capacity.js", "chat_table_contrast.js"):
            self.assertIn(name, snapshot)
