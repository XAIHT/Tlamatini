"""Tests for the Context Governor — STEP 1, measurement only.

Two halves, deliberately:

* **Behaviour** — the arithmetic, the zones, the ceiling, the sink, and above
  all FAIL-OPEN: nothing here may raise into a caller.
* **Source contracts** — the wiring that a later edit could quietly undo. The
  four model-call sites, the gauge sink's registration AND teardown, and the
  TWO layout edits that keep the Send button on the screen. Missing either
  layout edit is the single most likely way to ship this feature broken, so
  both are pinned.

The module under test is stdlib-only and imports nothing from ``agent.*``;
one test asserts exactly that, because the moment it grows such an import it
can create a cycle between ``tools.py`` and ``mcp_agent.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from agent import context_governor as cg

_AGENT_DIR = Path(__file__).resolve().parent
_MCP_AGENT = _AGENT_DIR / "mcp_agent.py"
_CONSUMERS = _AGENT_DIR / "consumers.py"
_LAYOUT_JS = _AGENT_DIR / "static" / "agent" / "js" / "agent_page_layout.js"
_CHAT_JS = _AGENT_DIR / "static" / "agent" / "js" / "agent_page_chat.js"
_GAUGE_JS = _AGENT_DIR / "static" / "agent" / "js" / "context_gauge.js"
_TEMPLATE = _AGENT_DIR / "templates" / "agent" / "agent_page.html"
_GOVERNOR = _AGENT_DIR / "context_governor.py"


class _Msg:
    """A minimal duck-type of a LangChain message."""

    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class MeasurementTests(SimpleTestCase):
    def test_bytes_are_utf8_exact_not_character_count(self):
        """The headline figure is the size ON THE WIRE, not len(str)."""
        m = cg.measure([_Msg("áéíóú")], prefix_message_count=1, loop_start_index=1)
        self.assertEqual(m.total_bytes, 10)   # 5 two-byte characters
        self.assertEqual(m.total_chars, 5)

    def test_buckets_sum_to_the_total(self):
        msgs = [_Msg("s" * 100), _Msg("h" * 50), _Msg("l" * 200)]
        m = cg.measure(msgs, prefix_message_count=1, loop_start_index=2,
                       extra_prefix_bytes=1000)
        self.assertEqual(
            m.prefix_bytes + m.history_bytes + m.loop_bytes, m.total_bytes
        )
        self.assertEqual(m.prefix_bytes, 1100)
        self.assertEqual(m.history_bytes, 50)
        self.assertEqual(m.loop_bytes, 200)
        self.assertEqual(m.loop_messages, 1)

    def test_tool_schema_bytes_land_in_the_prefix(self):
        """The bound tool surface is sent every turn but lives outside the
        message list; ignoring it would under-report the wire size badly."""
        without = cg.measure([_Msg("x" * 10)], prefix_message_count=1, loop_start_index=1)
        with_schemas = cg.measure([_Msg("x" * 10)], prefix_message_count=1,
                                  loop_start_index=1, extra_prefix_bytes=50_000)
        self.assertEqual(with_schemas.total_bytes - without.total_bytes, 50_000)
        self.assertEqual(with_schemas.loop_bytes, without.loop_bytes)

    def test_tool_calls_are_counted(self):
        """A tool CALL is part of what goes on the wire."""
        plain = cg.measure([_Msg("")], loop_start_index=1)
        with_calls = cg.measure(
            [_Msg("", tool_calls=[{"name": "grepper", "args": {"pattern": "x"}}])],
            loop_start_index=1,
        )
        self.assertGreater(with_calls.total_bytes, plain.total_bytes)

    def test_content_blocks_and_dict_messages_are_understood(self):
        blocks = cg.measure([_Msg([{"type": "text", "text": "hello"}])], loop_start_index=1)
        self.assertGreater(blocks.total_bytes, 0)
        as_dict = cg.measure([{"role": "user", "content": "hello"}], loop_start_index=1)
        self.assertEqual(as_dict.total_bytes, 5)

    def test_tokens_are_an_estimate_derived_from_characters(self):
        m = cg.measure([_Msg("x" * 4000)], prefix_message_count=1, loop_start_index=1)
        self.assertEqual(m.tokens_estimated, int(4000 / cg.CHARS_PER_TOKEN))

    def test_measuring_never_mutates_the_caller_s_list(self):
        """Step 1 folds NOTHING. This is the contract that lets it run all day."""
        msgs = [_Msg("a"), _Msg("b"), _Msg("c")]
        before = list(msgs)
        cg.measure(msgs, loop_start_index=1)
        self.assertEqual(msgs, before)
        self.assertEqual(len(msgs), 3)


class FailOpenTests(SimpleTestCase):
    def test_measure_never_raises_on_garbage(self):
        for bad in (object(), 12345, {"not": "iterable-of-messages"}):
            self.assertIsInstance(cg.measure(bad), cg.Measurement)

    def test_measure_of_none_is_an_empty_but_valid_reading(self):
        m = cg.measure(None)
        self.assertTrue(m.ok)
        self.assertEqual(m.total_bytes, 0)

    def test_unmeasurable_input_reports_itself_rather_than_lying(self):
        m = cg.measure(object())
        self.assertFalse(m.ok)
        self.assertIn("unavailable", cg.format_log_line(m))

    def test_a_message_that_explodes_on_access_is_survived(self):
        class Hostile:
            @property
            def content(self):
                raise RuntimeError("boom")

        self.assertIsInstance(cg.measure([Hostile()], loop_start_index=1), cg.Measurement)

    def test_malformed_settings_fall_back_to_the_shipped_values(self):
        s = cg.resolve_settings({
            "context_governor_enable": "maybe",
            "context_watermark_fold": "nonsense",
            "context_gauge_history_turns": -4,
        })
        self.assertTrue(s.enabled)
        self.assertEqual(s.watermark_fold, cg.DEFAULT_WATERMARK_FOLD)
        self.assertEqual(s.gauge_history_turns, cg.DEFAULT_GAUGE_HISTORY_TURNS)

    def test_out_of_order_watermarks_are_rejected_wholesale(self):
        """Corrected watermarks would be a guess at her intent; the shipped
        set is the honest fallback."""
        s = cg.resolve_settings({
            "context_watermark_compact": 0.9,
            "context_watermark_fold": 0.2,
        })
        self.assertEqual(s.watermark_compact, cg.DEFAULT_WATERMARK_COMPACT)
        self.assertEqual(s.watermark_fold, cg.DEFAULT_WATERMARK_FOLD)

    def test_settings_survive_a_non_dict_config(self):
        self.assertTrue(cg.resolve_settings("not a dict").enabled)
        self.assertTrue(cg.resolve_settings(None).enabled)


class CeilingAndZoneTests(SimpleTestCase):
    def test_ceiling_resolution_order(self):
        self.assertEqual(
            cg.resolve_ceiling_tokens({"context_ceiling_tokens": 32000,
                                       "ollama_num_ctx": 8192}),
            (32000, "config"),
        )
        self.assertEqual(
            cg.resolve_ceiling_tokens({"ollama_num_ctx": 8192}),
            (8192, "ollama_num_ctx"),
        )
        self.assertEqual(
            cg.resolve_ceiling_tokens({}),
            (cg.FALLBACK_CEILING_TOKENS, "fallback"),
        )

    def test_unknown_ceiling_assumes_the_larger_budget(self):
        """On doubt, report LESS pressure — over-reporting would train the
        watermarks wrong, and later would fold work that did not need it."""
        self.assertGreaterEqual(cg.FALLBACK_CEILING_TOKENS, 1_000_000)

    def test_the_four_zones_and_their_edges(self):
        s = cg.GovernorSettings()
        self.assertEqual(cg.zone_for(0.0, s), cg.ZONE_GREEN)
        self.assertEqual(cg.zone_for(0.599, s), cg.ZONE_GREEN)
        self.assertEqual(cg.zone_for(0.60, s), cg.ZONE_AMBER)
        self.assertEqual(cg.zone_for(0.749, s), cg.ZONE_AMBER)
        self.assertEqual(cg.zone_for(0.75, s), cg.ZONE_RED)
        self.assertEqual(cg.zone_for(0.849, s), cg.ZONE_RED)
        self.assertEqual(cg.zone_for(0.85, s), cg.ZONE_FLOOR)
        self.assertEqual(cg.zone_for(4.0, s), cg.ZONE_FLOOR)


class ReportingTests(SimpleTestCase):
    def _line(self):
        m = cg.measure([_Msg("x" * 1000)], prefix_message_count=1, loop_start_index=1,
                       config={"ollama_num_ctx": 1000})
        return cg.format_log_line(m, "working on step 3")

    def test_log_line_is_grep_able_and_names_the_step(self):
        line = self._line()
        self.assertTrue(line.startswith("--- [CONTEXT]"))
        self.assertIn("working on step 3", line)

    def test_log_line_qualifies_the_estimate_and_not_the_measurement(self):
        """Bytes are measured, tokens are estimated, and the line says so."""
        line = self._line()
        self.assertRegex(line, r"\d+ B \(")
        self.assertIn("tokens est.", line)
        self.assertIn("% est.", line)
        self.assertNotRegex(line, r"\d+ B est\.")

    def test_log_line_names_the_three_streams(self):
        line = self._line()
        for stream in ("prefix", "history", "loop"):
            self.assertIn(stream, line)

    def test_humanize_bytes(self):
        self.assertEqual(cg.humanize_bytes(512), "512 B")
        self.assertEqual(cg.humanize_bytes(1024), "1.0 KB")
        self.assertEqual(cg.humanize_bytes(402551), "393.1 KB")
        self.assertEqual(cg.humanize_bytes("bad"), "0 B")

    def test_gauge_payload_carries_the_exact_integer_and_flags_the_estimate(self):
        m = cg.measure([_Msg("x" * 4096)], prefix_message_count=1, loop_start_index=1)
        payload = cg.gauge_payload(m, cg.GovernorSettings(), "answering")
        self.assertEqual(payload["bytes_total"], 4096)      # never rounded away
        self.assertTrue(payload["tokens_are_estimated"])
        self.assertIn("watermarks", payload)
        self.assertEqual(payload["label"], "answering")


class GaugeSinkTests(SimpleTestCase):
    def tearDown(self):
        for key in ("u-test", "u-raise", "u-two-tabs"):
            cg.unregister_gauge_sink(key)

    def test_publish_without_a_sink_is_a_silent_no_op(self):
        self.assertFalse(cg.publish_gauge("nobody", {"bytes_total": 1}))

    def test_publish_reaches_the_registered_sink(self):
        seen = []
        cg.register_gauge_sink("u-test", seen.append)
        self.assertTrue(cg.publish_gauge("u-test", {"bytes_total": 7}))
        self.assertEqual(seen, [{"bytes_total": 7}])

    def test_a_sink_that_raises_never_reaches_the_caller(self):
        """The chat path owes the gauge nothing."""
        def boom(_payload):
            raise RuntimeError("browser went away")

        cg.register_gauge_sink("u-raise", boom)
        self.assertFalse(cg.publish_gauge("u-raise", {}))

    def test_unregister_is_identity_guarded(self):
        """Two browser tabs share one user id: a finishing request must not
        tear down the other tab's live sink."""
        first, second = [], []
        cg.register_gauge_sink("u-two-tabs", first.append)
        cg.register_gauge_sink("u-two-tabs", second.append)
        cg.unregister_gauge_sink("u-two-tabs", first.append)   # stale handle
        self.assertTrue(cg.publish_gauge("u-two-tabs", {"still": "live"}))
        self.assertEqual(second, [{"still": "live"}])

    def test_a_none_user_id_is_ignored_everywhere(self):
        cg.register_gauge_sink(None, lambda _p: None)
        self.assertFalse(cg.publish_gauge(None, {}))


class SourceContractTests(SimpleTestCase):
    """Wiring a later edit could quietly undo."""

    def test_module_imports_nothing_from_agent(self):
        src = _GOVERNOR.read_text(encoding="utf-8")
        self.assertNotRegex(src, r"^\s*from\s+\.\s*\w*\s+import", msg="no agent.* imports")
        self.assertNotRegex(src, r"^\s*from\s+agent[.\s]", msg="no agent.* imports")
        self.assertNotRegex(src, r"^\s*import\s+agent\b", msg="no agent.* imports")

    def test_every_model_call_site_goes_through_the_one_helper(self):
        src = _MCP_AGENT.read_text(encoding="utf-8")
        self.assertEqual(src.count("self._model_step("), 4,
                         "the four model-call sites must all use the helper")
        # The ONLY remaining direct healer call is the one INSIDE the helper.
        self.assertEqual(src.count("self._healer.invoke("), 1)
        self.assertIn("return self._healer.invoke(llm, messages, label=label)", src)

    def test_the_helper_measures_logs_and_publishes(self):
        src = _MCP_AGENT.read_text(encoding="utf-8")
        helper = src.split("def _model_step(", 1)[1].split("\n    def ", 1)[0]
        for needed in ("_context_measure(", "_context_log_line(", "_context_publish_gauge("):
            self.assertIn(needed, helper)

    def test_the_loop_and_prefix_boundaries_are_recorded(self):
        src = _MCP_AGENT.read_text(encoding="utf-8")
        self.assertIn("self._context_prefix_count = len(messages)", src)
        self.assertIn("self._context_loop_start = len(messages)", src)

    def test_consumer_registers_and_tears_down_the_gauge_sink(self):
        src = _CONSUMERS.read_text(encoding="utf-8")
        self.assertIn("register_gauge_sink(broker_key, _emit_context_gauge)", src)
        self.assertIn("unregister_gauge_sink(broker_key, _emit_context_gauge)", src)
        self.assertIn("async def context_gauge(self, event):", src)
        self.assertIn("'type': 'context_gauge', 'detail': detail", src)

    def test_chat_js_routes_the_frame_without_a_new_global(self):
        src = _CHAT_JS.read_text(encoding="utf-8")
        self.assertIn("data.type === 'context-gauge'", src)
        self.assertIn("tlm:context-gauge", src)

    def test_the_gauge_module_declares_no_cross_file_global(self):
        src = _GAUGE_JS.read_text(encoding="utf-8")
        self.assertTrue(src.lstrip().startswith("/*"))
        self.assertIn("(function ()", src)
        self.assertNotRegex(src, r"^(var|let|const|function)\s", msg="must stay an IIFE")

    def test_BOTH_layout_edits_are_present(self):
        """Fig 21: the most likely way to ship this broken is to get the
        widget right and the layout wrong. Miss either edit and the Send
        button leaves the screen."""
        src = _LAYOUT_JS.read_text(encoding="utf-8")
        self.assertIn("getElementById('context-gauge-row')", src,
                      "computeFormMinHeight must measure the gauge row")
        self.assertIn("toolsDivH + chipsH + gaugeH + formAreaPx", src,
                      "the gauge row must be ADDED to the form min height")
        self.assertIn("'tools-div', 'chat-image-chips', 'context-gauge-row'", src,
                      "the ResizeObserver must watch the gauge row too")

    def test_template_carries_the_row_and_both_assets(self):
        src = _TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('id="context-gauge-row"', src)
        self.assertIn("agent/css/context_gauge.css", src)
        self.assertIn("agent/js/context_gauge.js", src)
        # The row is a SIBLING of the toolbar and sits ABOVE the chips row.
        self.assertLess(src.index('id="context-gauge-row"'), src.index('id="chat-image-chips"'))
        self.assertLess(src.index('id="tools-div"'), src.index('id="context-gauge-row"'))

    def test_the_row_is_invisible_until_it_has_data(self):
        css = (_AGENT_DIR / "static" / "agent" / "css" / "context_gauge.css").read_text(
            encoding="utf-8")
        block = css.split("#context-gauge-row {", 1)[1].split("}", 1)[0]
        self.assertRegex(block, r"display:\s*none")
        self.assertIn(".ctxg-visible", css)

    def test_step_one_folds_nothing_anywhere(self):
        """A guard against scope creep: the folding rungs are steps 2-10 and
        must not appear until their watermarks are set from real numbers."""
        src = _GOVERNOR.read_text(encoding="utf-8")
        for absent in ("def fold", "def dedupe", "def demote", "def spill", "def ledger"):
            self.assertNotIn(absent, src)

    def test_config_ships_every_key_the_module_reads(self):
        import json

        config = json.loads((_AGENT_DIR / "config.json").read_text(encoding="utf-8-sig"))
        for key in (
            "context_governor_enable",
            "context_ceiling_tokens",
            "context_watermark_compact",
            "context_watermark_fold",
            "context_watermark_floor",
            "context_governor_log_each_fold",
            "context_gauge_enable",
            "context_gauge_history_turns",
        ):
            self.assertIn(key, config)
        # Every key the module reads must be a key the shipped config has.
        read_by_module = set(re.findall(r'cfg\.get\("(context_[a-z_]+)"\)',
                                        _GOVERNOR.read_text(encoding="utf-8")))
        self.assertTrue(read_by_module.issubset(set(config)), read_by_module - set(config))
