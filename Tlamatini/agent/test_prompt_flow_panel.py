# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Run in a visible foreground console:
python Tlamatini/agent/test_prompt_flow_panel.py. No model calls or database writes.
"""
import asyncio
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("prompt_flow_panel_contract", Path(__file__).parent / "services" / "prompt_flow_panel.py")
flow_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow_module)
FlowError, FlowRunner, FlowStopped = flow_module.FlowError, flow_module.FlowRunner, flow_module.FlowStopped


def node(key, kind="prompt", **config):
    settings = {"text": "Explain a graph", "multi_turn": False, "acpx": False,
                "delay_seconds": 0, "scheduled_at": "", "comparison": "contains",
                "value": "yes", "case_sensitive": False}
    settings.update(config)
    return {"id": key, "type": kind, "label": key, "x": 10, "y": 20, "config": settings}


def diagram(nodes, edges=(), max_steps=20):
    return {"format": flow_module.FORMAT, "version": flow_module.VERSION, "name": "Test", "start": next((n["id"] for n in nodes if n["type"] != "user_commentary"), None),
            "max_steps": max_steps, "nodes": nodes,
            "edges": [{"id": f"e{i}", "source": a, "target": b, "branch": c} for i, (a, b, c) in enumerate(edges)]}


class Runtime:
    def __init__(self):
        self.calls = []
        self.cancelled = False

    async def prompt(self, text, config):
        self.calls.append(("prompt", text))
        return "YES, useful output"

    async def feed(self, text):
        self.calls.append(("feed", text))

    async def flush(self):
        self.calls.append(("flush",))

    async def clean_history(self):
        self.calls.append(("clean",))

    async def comment(self, text):
        self.calls.append(("comment", text))

    def cancel(self):
        self.cancelled = True


class ValidationTests(unittest.TestCase):
    def test_normalizes_without_mutation(self):
        original = diagram([node("a")])
        original["nodes"][0]["config"]["arbitrary_code"] = "ignored"
        before = copy.deepcopy(original)
        result = flow_module.validate_flow(original, playable=True)
        self.assertEqual(original, before)
        self.assertNotIn("arbitrary_code", result["nodes"][0]["config"])

    def test_empty_draft_can_save_but_not_play(self):
        flow_module.validate_flow(diagram([]))
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([]), playable=True)

    def test_legacy_and_future_files_rejected(self):
        for payload in ("You are Tlamatini", {"format": flow_module.FORMAT, "version": 99}, {}):
            with self.subTest(payload=payload), self.assertRaises(FlowError):
                flow_module.validate_flow(payload)

    def test_duplicate_and_dangling_ids_rejected(self):
        for payload in (diagram([node("a"), node("a")]), diagram([node("a")], [("a", "missing", "next")])):
            with self.assertRaises(FlowError):
                flow_module.validate_flow(payload)

    def test_incomplete_decision_rejected(self):
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([node("a", "decision"), node("b")], [("a", "b", "yes")]), playable=True)

    def test_two_connections_on_one_output_rejected(self):
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([node("a"), node("b"), node("c")], [("a", "b", "next"), ("a", "c", "next")]))

    def test_unreachable_operation_rejected(self):
        with self.assertRaisesRegex(FlowError, "unreachable"):
            flow_module.validate_flow(diagram([node("a"), node("b")]), playable=True)

    def test_invalid_numbers_and_boolean_step_limit(self):
        for value in (-1, float("nan"), float("inf"), True, "12"):
            payload = diagram([node("a")])
            payload["max_steps"] = value
            with self.subTest(value=value), self.assertRaises(FlowError):
                flow_module.validate_flow(payload)

    def test_schedule_needs_timezone(self):
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([node("a", "programmed_prompt", scheduled_at="2030-01-01T12:00")]))

    def test_acpx_requires_multi_turn(self):
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([node("a", acpx=True)]))

    def test_substitution_is_literal(self):
        self.assertEqual(flow_module.expand_text("Use {{last_output}} and {{unknown}}", "<script>x</script>"), "Use <script>x</script> and {{unknown}}")

    def test_legacy_commentary_migrates_without_changing_user_input_graph(self):
        original = diagram([node("input", "user_commentary"), node("p")], [("input", "p", "next")])
        original.update(version=1, start="input")
        original["nodes"][0]["label"] = "User Commentary"
        before = copy.deepcopy(original)
        result = flow_module.validate_flow(original, playable=True)
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["nodes"][0]["type"], "user_input")
        self.assertEqual(result["nodes"][0]["label"], "User Input")
        self.assertEqual(result["edges"], original["edges"])
        self.assertEqual(result["nodes"][0]["config"]["text"], original["nodes"][0]["config"]["text"])
        self.assertEqual(original, before)

    def test_static_comment_roundtrip_preserves_long_literal_text_and_formatting(self):
        note = node("note", "user_commentary", text=("Paragraph ñ <script> {{last_output}}\n" * 500),
                    width=650, height=450, color="#dbeafe", font_family="Georgia", font_size=22,
                    bold=True, italic=True, align="right")
        result = flow_module.validate_flow(diagram([node("p"), note]), playable=True)
        self.assertEqual(result["nodes"][1]["config"], {k: note["config"][k] for k in result["nodes"][1]["config"]})
        self.assertEqual(flow_module.validate_flow(result), result)

    def test_static_comments_save_alone_but_cannot_be_start_or_connected(self):
        note = node("note", "user_commentary")
        flow_module.validate_flow(diagram([note]))
        with self.assertRaises(FlowError):
            flow_module.validate_flow(diagram([note]), playable=True)
        for source, target in [("note", "p"), ("p", "note")]:
            with self.assertRaisesRegex(FlowError, "cannot have connections"):
                flow_module.validate_flow(diagram([node("p"), note], [(source, target, "next")]))
        payload = diagram([node("p"), note])
        payload["start"] = "note"
        with self.assertRaisesRegex(FlowError, "Start"):
            flow_module.validate_flow(payload)

    def test_comment_style_rejects_unsafe_or_out_of_range_values(self):
        for key, value in [("color", "url(javascript:evil)"), ("font_family", "evil; color:red"),
                           ("width", 199), ("height", 2401), ("font_size", 0), ("bold", 1), ("align", "evil")]:
            with self.subTest(key=key), self.assertRaises(FlowError):
                flow_module.validate_flow(diagram([node("note", "user_commentary", **{key: value})]))


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.runtime = Runtime()

    async def emit(self, event, **data):
        self.events.append((event, data))

    async def test_model_answer_selects_exactly_one_branch(self):
        flow = diagram([node("a"), node("d", "decision"), node("yes"), node("no")],
                       [("a", "d", "next"), ("d", "yes", "yes"), ("d", "no", "no")])
        runner = FlowRunner(flow, self.runtime, self.emit)
        await runner.run()
        completed = [data["node_id"] for event, data in self.events if event == "node" and data["status"] == "completed"]
        self.assertEqual(completed, ["a", "d", "yes"])

    async def test_context_and_history_operations_in_order(self):
        flow = diagram([node("a"), node("feed", "feed_embeddings", text="{{last_output}}"), node("flush", "flush_embeddings"), node("clean", "clean_history"), node("b", text="Explain {{last_output}}")],
                       [("a", "feed", "next"), ("feed", "flush", "next"), ("flush", "clean", "next"), ("clean", "b", "next")])
        await FlowRunner(flow, self.runtime, self.emit).run()
        self.assertEqual(self.runtime.calls, [("prompt", "Explain a graph"), ("feed", "YES, useful output"), ("flush",), ("clean",), ("prompt", "Explain ")])

    async def test_cycle_stops_at_limit(self):
        runner = FlowRunner(diagram([node("a")], [("a", "a", "next")], 3), self.runtime, self.emit)
        with self.assertRaisesRegex(FlowError, "Step limit"):
            await runner.run()
        self.assertEqual(len(self.runtime.calls), 3)

    async def test_pause_prevents_execution_until_resume(self):
        runner = FlowRunner(diagram([node("a")]), self.runtime, self.emit)
        runner.resumed.clear()
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(.02)
        self.assertEqual(self.runtime.calls, [])
        runner.resumed.set()
        await task
        self.assertEqual(len(self.runtime.calls), 1)

    async def test_stop_interrupts_programmed_delay(self):
        runner = FlowRunner(diagram([node("a", "programmed_prompt", delay_seconds=30)]), self.runtime, self.emit)
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(.02)
        runner.stop()
        with self.assertRaises(FlowStopped):
            await asyncio.wait_for(task, 1)
        self.assertEqual(self.runtime.calls, [])
        self.assertTrue(self.runtime.cancelled)

    async def test_commentary_rejects_stale_reply(self):
        runner = FlowRunner(diagram([node("a", "user_input")]), self.runtime, self.emit)
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0)
        with self.assertRaises(FlowError):
            runner.reply("stale", "ignored")
        runner.reply(runner.reply_id, "My reply")
        await task
        self.assertEqual(runner.last_output, "My reply")
        self.assertEqual(self.runtime.calls, [("comment", "My reply")])

    async def test_stop_releases_pending_user_input(self):
        runner = FlowRunner(diagram([node("a", "user_input")]), self.runtime, self.emit)
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0)
        runner.stop()
        with self.assertRaises(FlowStopped):
            await task

    async def test_runtime_failure_prevents_next_operation(self):
        async def broken(*args):
            raise RuntimeError("Provider unavailable")
        self.runtime.prompt = broken
        runner = FlowRunner(diagram([node("a"), node("b", "flush_embeddings")], [("a", "b", "next")]), self.runtime, self.emit)
        with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
            await runner.run()
        self.assertEqual(self.runtime.calls, [])

    async def test_manual_no_branch(self):
        flow = diagram([node("d", "decision", comparison="user"), node("yes"), node("no")], [("d", "yes", "yes"), ("d", "no", "no")])
        runner = FlowRunner(flow, self.runtime, self.emit)
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0)
        runner.reply(runner.reply_id, "no")
        await task
        self.assertEqual([d["node_id"] for e, d in self.events if e == "node" and d["status"] == "completed"], ["d", "no"])

    async def test_static_comments_never_emit_input_or_change_run_state(self):
        flow = diagram([node("p"), node("note1", "user_commentary", text="{{last_output}}"),
                        node("note2", "user_commentary", text="Review only")], max_steps=1)
        runner = FlowRunner(flow, self.runtime, self.emit)
        await runner.run()
        self.assertEqual(self.runtime.calls, [("prompt", "Explain a graph")])
        self.assertEqual(runner.step, 1)
        self.assertEqual(runner.last_output, "YES, useful output")
        self.assertFalse(any(e == "input" or d.get("node_id") in {"note1", "note2"} for e, d in self.events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
