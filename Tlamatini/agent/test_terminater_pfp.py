# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""The Terminater step (the parallelogram) inside the Prompt Flow Panel.

Four layers, each of which can silently disagree with the others:

* the **Python validator / interpreter** (``services/prompt_flow_panel.py``),
* the **JavaScript model** the editor runs in the browser (``prompt-flow-panel-model.js``) --
  a node-hosted parity run feeds both the same documents and compares every verdict,
* the **runtime adapter** (``PromptFlowPanelRuntime.terminal``) that talks to the hub,
* the **engine** the step finally reaches (its action table must contain every PFP action).
"""
from __future__ import annotations

import asyncio
import copy
import json
import shutil
import subprocess
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from . import terminal_hub
from . import terminater_testkit as kit
from .services import prompt_flow_panel as fm

AGENT_DIR = Path(__file__).resolve().parent
MODEL_JS = AGENT_DIR / "static" / "agent" / "js" / "prompt-flow-panel-model.js"
CONFIG_YAML = AGENT_DIR / "agents" / "terminater" / "config.yaml"
eng = kit.engine()


def node(key="t", **config):
    settings = {"text": "dir"}
    settings.update(config)
    return {"id": key, "type": "terminater", "label": key, "x": 10, "y": 20, "config": settings}


def prompt(key="p", text="Say hi", **config):
    settings = {"text": text, "multi_turn": False, "acpx": False}
    settings.update(config)
    return {"id": key, "type": "prompt", "label": key, "x": 10, "y": 20, "config": settings}


def decision(key="d", value="ok"):
    return {"id": key, "type": "decision", "label": key, "x": 10, "y": 20,
            "config": {"text": "", "comparison": "contains", "value": value, "case_sensitive": False}}


def diagram(nodes, edges=(), max_steps=20):
    return {"format": fm.FORMAT, "version": fm.VERSION, "name": "Test",
            "start": next((n["id"] for n in nodes if n["type"] != "user_commentary"), None),
            "max_steps": max_steps, "nodes": nodes,
            "edges": [{"id": f"e{i}", "source": a, "target": b, "branch": c} for i, (a, b, c) in enumerate(edges)]}


def cfg(result, key="t"):
    return next(n for n in result["nodes"] if n["id"] == key)["config"]


# --------------------------------------------------------------------------- #
# Python validator                                                             #
# --------------------------------------------------------------------------- #

class ValidatorTests(SimpleTestCase):
    def valid(self, **config):
        return fm.validate_flow(diagram([node(**config)]), playable=config.pop("_playable", True))

    def bad(self, **config):
        with self.assertRaises(fm.FlowError):
            fm.validate_flow(diagram([node(**config)]), playable=True)

    def test_the_operation_is_known(self):
        self.assertIn("terminater", fm.OPERATIONS)

    def test_defaults_fill_in(self):
        config = cfg(fm.validate_flow(diagram([node()]), playable=True))
        for key, value in fm.TERMINATER_DEFAULTS.items():
            self.assertEqual(config[key], value, key)
        self.assertEqual(config["text"], "dir")

    def test_every_action_is_accepted(self):
        for action in fm.TERMINATER_ACTIONS:
            with self.subTest(action=action):
                result = fm.validate_flow(diagram([node(action=action, text="x", keys="enter")]), playable=True)
                self.assertEqual(cfg(result)["action"], action)

    def test_an_unknown_action_is_rejected(self):
        with self.assertRaisesRegex(fm.FlowError, "Unknown Terminater action"):
            fm.validate_flow(diagram([node(action="selfdestruct")]))

    def test_every_kind_is_accepted(self):
        for kind in fm.TERMINATER_KINDS:
            self.assertEqual(cfg(fm.validate_flow(diagram([node(kind=kind)])))["kind"], kind)

    def test_an_unknown_kind_is_rejected(self):
        for kind in ("zsh", "", "CMD", "bash", 5, None):
            with self.subTest(kind=kind), self.assertRaisesRegex(fm.FlowError, "CMD, PowerShell"):
                fm.validate_flow(diagram([node(kind=kind)]))

    def test_run_needs_a_command_when_playing(self):
        for action in fm.TERMINATER_TEXT_ACTIONS:
            with self.subTest(action=action), self.assertRaisesRegex(fm.FlowError, "needs a command"):
                fm.validate_flow(diagram([node(action=action, text="   ")]), playable=True)

    def test_a_draft_may_be_saved_without_a_command(self):
        fm.validate_flow(diagram([node(text="")]), playable=False)

    def test_send_key_needs_keys_when_playing(self):
        with self.assertRaisesRegex(fm.FlowError, "needs the keys"):
            fm.validate_flow(diagram([node(action="send_key", text="", keys="  ")]), playable=True)
        fm.validate_flow(diagram([node(action="send_key", text="", keys="ctrl+c")]), playable=True)

    def test_actions_without_text_play_fine(self):
        for action in ("list", "status", "kill", "kill_all", "abort", "commands", "read", "clear", "focus"):
            with self.subTest(action=action):
                fm.validate_flow(diagram([node(action=action, text="")]), playable=True)

    def test_booleans_must_be_booleans(self):
        for key in fm.TERMINATER_BOOLEANS:
            for value in ("yes", 1, 0, None, "true"):
                with self.subTest(key=key, value=value), self.assertRaises(fm.FlowError):
                    fm.validate_flow(diagram([node(**{key: value})]))

    def test_booleans_accept_both_values(self):
        for key in fm.TERMINATER_BOOLEANS:
            for value in (True, False):
                self.assertEqual(cfg(fm.validate_flow(diagram([node(**{key: value})])))[key], value)

    def test_number_bounds(self):
        cases = {
            "typing_wpm": (20, 250, 19, 251),
            "wait_seconds": (1, 3600, 0.5, 3601),
            "hang_seconds": (3, 3600, 2.9, 3601),
            "user_wait_seconds": (5, 3600, 4, 3601),
            "idle_seconds": (0.2, 600, 0.1, 601),
        }
        for key, (low, high, under, over) in cases.items():
            for ok in (low, high):
                with self.subTest(key=key, ok=ok):
                    self.assertEqual(cfg(fm.validate_flow(diagram([node(**{key: ok})])))[key], ok)
            for bad in (under, over):
                with self.subTest(key=key, bad=bad), self.assertRaises(fm.FlowError):
                    fm.validate_flow(diagram([node(**{key: bad})]))

    def test_typing_speed_must_be_whole(self):
        with self.assertRaises(fm.FlowError):
            fm.validate_flow(diagram([node(typing_wpm=50.5)]))
        self.assertEqual(cfg(fm.validate_flow(diagram([node(typing_wpm=50.0)])))["typing_wpm"], 50)

    def test_numbers_must_be_real_numbers(self):
        for key in fm.TERMINATER_NUMBERS:
            for value in (True, "50", None, float("nan"), float("inf"), [], {}):
                with self.subTest(key=key, value=repr(value)), self.assertRaises(fm.FlowError):
                    fm.validate_flow(diagram([node(**{key: value})]))

    def test_severity(self):
        for value in ("info", "hint", "warning", "danger"):
            self.assertEqual(cfg(fm.validate_flow(diagram([node(severity=value)])))["severity"], value)
        for value in ("critical", "", "WARNING", None):
            with self.subTest(value=value), self.assertRaises(fm.FlowError):
                fm.validate_flow(diagram([node(severity=value)]))

    def test_layout_and_area(self):
        for layout in ("", "tabs", "tile", "tile-h", "tile-v", "grid"):
            for area in ("", "dock", "full"):
                result = cfg(fm.validate_flow(diagram([node(layout=layout, area=area)])))
                self.assertEqual((result["layout"], result["area"]), (layout, area))
        for layout, area in (("spiral", ""), ("", "moon"), ("Tabs", ""), ("", "FULL")):
            with self.subTest(layout=layout, area=area), self.assertRaises(fm.FlowError):
                fm.validate_flow(diagram([node(layout=layout, area=area)]))

    def test_text_limits(self):
        for key, limit in fm.TERMINATER_TEXT_LIMITS.items():
            with self.subTest(key=key):
                self.assertEqual(cfg(fm.validate_flow(diagram([node(**{key: "x" * limit})])))[key], "x" * limit)
                with self.assertRaises(fm.FlowError):
                    fm.validate_flow(diagram([node(**{key: "x" * (limit + 1)})]))

    def test_text_fields_must_be_text(self):
        for key in fm.TERMINATER_TEXT_LIMITS:
            for value in (5, None, [], {}, True):
                with self.subTest(key=key, value=repr(value)), self.assertRaises(fm.FlowError):
                    fm.validate_flow(diagram([node(**{key: value})]))

    def test_the_command_text_has_a_large_limit(self):
        fm.validate_flow(diagram([node(text="x" * 100_000)]))
        with self.assertRaises(fm.FlowError):
            fm.validate_flow(diagram([node(text="x" * 100_001)]))

    def test_unknown_settings_are_dropped(self):
        result = fm.validate_flow(diagram([node(arbitrary_code="rm -rf /", shell=True)]))
        self.assertNotIn("arbitrary_code", cfg(result))
        self.assertNotIn("shell", cfg(result))

    def test_validation_does_not_mutate_its_input(self):
        original = diagram([node()])
        before = copy.deepcopy(original)
        fm.validate_flow(original, playable=True)
        self.assertEqual(original, before)

    def test_validation_is_idempotent(self):
        once = fm.validate_flow(diagram([node(kind="cmd", text="echo hi", typing_wpm=90)]), playable=True)
        self.assertEqual(fm.validate_flow(once, playable=True), once)

    def test_a_json_roundtrip_is_stable(self):
        once = fm.validate_flow(diagram([node(text="ping <<USER:host>> -n 2")]), playable=True)
        again = fm.validate_flow(json.loads(json.dumps(once, ensure_ascii=False)), playable=True)
        self.assertEqual(again, once)

    def test_the_handover_placeholder_survives(self):
        text = "ping <<USER:the host to ping>> -n 2"
        self.assertEqual(cfg(fm.validate_flow(diagram([node(text=text)])))["text"], text)

    def test_unicode_and_newlines_survive(self):
        text = "Write-Output 'héllo ñ 日本'\nGet-Date"
        self.assertEqual(cfg(fm.validate_flow(diagram([node(text=text)])))["text"], text)

    def test_the_default_label_is_kept(self):
        result = fm.validate_flow(diagram([node()]))
        self.assertEqual(result["nodes"][0]["label"], "t")

    def test_a_terminater_can_start_a_flow_and_feed_a_prompt(self):
        result = fm.validate_flow(diagram([node("t"), prompt("p")], [("t", "p", "next")]), playable=True)
        self.assertEqual(result["start"], "t")
        self.assertEqual(result["edges"][0]["branch"], "next")

    def test_a_terminater_has_one_next_output_only(self):
        with self.assertRaises(fm.FlowError):
            fm.validate_flow(diagram([node("t"), prompt("a"), prompt("b")],
                                     [("t", "a", "next"), ("t", "b", "next")]))
        with self.assertRaises(fm.FlowError):
            fm.validate_flow(diagram([node("t"), prompt("a")], [("t", "a", "yes")]))

    def test_a_terminater_can_follow_a_decision_branch(self):
        flow = diagram([decision("d"), node("t"), prompt("p")],
                       [("d", "t", "yes"), ("d", "p", "no")])
        fm.validate_flow(flow, playable=True)

    def test_a_terminater_can_loop_back(self):
        fm.validate_flow(diagram([node("t"), decision("d")], [("t", "d", "next"), ("d", "t", "no")]))

    def test_an_unreachable_terminater_is_rejected_when_playing(self):
        with self.assertRaisesRegex(fm.FlowError, "unreachable"):
            fm.validate_flow(diagram([prompt("p"), node("t")]), playable=True)

    def test_many_terminaters_fit(self):
        nodes = [node(f"t{i}") for i in range(60)]
        edges = [(f"t{i}", f"t{i + 1}", "next") for i in range(59)]
        fm.validate_flow(diagram(nodes, edges), playable=True)

    def test_the_hub_has_every_action_a_flow_can_name(self):
        self.assertLessEqual(set(fm.TERMINATER_ACTIONS), set(eng.ACTIONS))

    def test_only_resize_is_missing_from_the_editor(self):
        self.assertEqual(set(eng.ACTIONS) - set(fm.TERMINATER_ACTIONS), {"resize"})

    def test_kinds_match_the_engine(self):
        self.assertEqual(tuple(fm.TERMINATER_KINDS), tuple(eng.KINDS))

    def test_layout_and_area_values_match_the_engine(self):
        layouts = {"", "tabs", "tile", "tile-h", "tile-v", "grid"}
        self.assertEqual(layouts - {""}, set(eng.LAYOUTS))
        self.assertEqual({"dock", "full"}, set(eng.AREAS))

    def test_text_actions_are_the_ones_that_type(self):
        self.assertEqual(set(fm.TERMINATER_TEXT_ACTIONS), {"run", "type", "handover"})

    def test_defaults_agree_with_the_agent_config(self):
        import yaml

        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))
        # Legacy flow files retain explicit values. Newly created nodes and
        # newly deployed agents opt in to the user's defaults.
        self.assertIs(fm.TERMINATER_DEFAULTS['use_my_defaults'], False)
        self.assertIs(data['use_my_defaults'], True)
        for key, value in fm.TERMINATER_DEFAULTS.items():
            if key in data and key != 'use_my_defaults':
                self.assertEqual(data[key], value, f"{key}: PFP default differs from agents/terminater/config.yaml")

    def test_number_ranges_agree_with_the_engine_clamps(self):
        self.assertEqual(fm.TERMINATER_NUMBERS["typing_wpm"][:2], (20, 250))
        self.assertEqual((kit.tx().MIN_WPM, kit.tx().MAX_WPM), (20, 250)) if hasattr(kit.tx(), "MIN_WPM") else None

    def test_format_and_version_are_unchanged(self):
        self.assertEqual(fm.FORMAT, "tlamatini-prompting-flow")
        self.assertEqual(fm.VERSION, 2)


# --------------------------------------------------------------------------- #
# JS <-> Python parity (the editor and the server must give one verdict)        #
# --------------------------------------------------------------------------- #

_NODE_SCRIPT = r"""
const fs = require('fs');
const window = {};
new Function('window', fs.readFileSync(process.argv[1], 'utf8'))(window);
const M = window.PromptFlowPanelModel;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(c => {
  try { const r = M.validate(JSON.parse(JSON.stringify(c.flow)), c.playable); return { ok: true, flow: r }; }
  catch (e) { return { ok: false, error: String(e && e.message || e) }; }
});
process.stdout.write(JSON.stringify(out));
"""


def _parity_cases():
    cases = []

    def add(name, nodes, edges=(), playable=False):
        cases.append({"name": name, "flow": diagram(nodes, edges), "playable": playable})

    add("default", [node()])
    add("default playable", [node()], playable=True)
    add("empty text playable", [node(text="")], playable=True)
    add("empty text draft", [node(text="")])
    for action in fm.TERMINATER_ACTIONS:
        add(f"action {action}", [node(action=action, text="x", keys="enter")], playable=True)
        add(f"action {action} bare", [node(action=action, text="", keys="")], playable=True)
    add("bad action", [node(action="nope")])
    for kind in ("cmd", "powershell", "pwsh", "zsh", "", 5):
        add(f"kind {kind!r}", [node(kind=kind)])
    for key in ("submit", "secret", "wait", "close_after", "load_profile", "advisor"):
        for value in (True, False, "yes", 1, None):
            add(f"bool {key}={value!r}", [node(**{key: value})])
    numbers = {"typing_wpm": (19, 20, 50, 50.5, 160, 161, 250, 251, "50", True),
               "wait_seconds": (0.5, 1, 120, 3600, 3601),
               "hang_seconds": (2.9, 3, 45, 3600, 3601),
               "user_wait_seconds": (4, 5, 300, 3601),
               "idle_seconds": (0.1, 0.2, 2, 600, 601)}
    for key, values in numbers.items():
        for value in values:
            add(f"number {key}={value!r}", [node(**{key: value})])
    for value in ("info", "hint", "warning", "danger", "critical", ""):
        add(f"severity {value!r}", [node(severity=value)])
    for layout in ("", "tabs", "tile", "tile-h", "tile-v", "grid", "spiral"):
        add(f"layout {layout!r}", [node(layout=layout)])
    for area in ("", "dock", "full", "moon"):
        add(f"area {area!r}", [node(area=area)])
    for key, limit in fm.TERMINATER_TEXT_LIMITS.items():
        add(f"limit {key} at", [node(**{key: "x" * limit})])
        add(f"limit {key} over", [node(**{key: "x" * (limit + 1)})])
        add(f"limit {key} number", [node(**{key: 5})])
    add("send_key no keys", [node(action="send_key", keys=" ")], playable=True)
    add("send_key keys", [node(action="send_key", keys="ctrl+c")], playable=True)
    add("chain", [node("a"), node("b")], [("a", "b", "next")], playable=True)
    add("double output", [node("a"), node("b"), node("c")], [("a", "b", "next"), ("a", "c", "next")])
    add("yes from terminater", [node("a"), node("b")], [("a", "b", "yes")])
    add("unreachable", [prompt("p"), node("t")], playable=True)
    return cases


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class JsParityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cases = _parity_cases()
        proc = subprocess.run(
            [shutil.which("node"), "-e", _NODE_SCRIPT, str(MODEL_JS)],
            input=json.dumps(cls.cases), capture_output=True, text=True, encoding="utf-8", timeout=60)
        if proc.returncode != 0:
            raise AssertionError(f"node failed: {proc.stderr[:2000]}")
        cls.js = json.loads(proc.stdout)

    def python_verdict(self, case):
        try:
            return True, fm.validate_flow(copy.deepcopy(case["flow"]), playable=case["playable"])
        except fm.FlowError as exc:
            return False, str(exc)

    def test_same_number_of_results(self):
        self.assertEqual(len(self.js), len(self.cases))
        self.assertGreater(len(self.cases), 150)

    def test_the_browser_and_the_server_accept_and_reject_the_same_documents(self):
        disagreements = []
        for case, js in zip(self.cases, self.js):
            ok, detail = self.python_verdict(case)
            if ok != js["ok"]:
                disagreements.append(f"{case['name']}: python={'ok' if ok else detail!r} js={'ok' if js['ok'] else js['error']!r}")
        self.assertEqual(disagreements, [], "\n".join(disagreements))

    def test_accepted_documents_normalise_to_the_same_terminater_settings(self):
        differences = []
        for case, js in zip(self.cases, self.js):
            ok, py = self.python_verdict(case)
            if not (ok and js["ok"]):
                continue
            for py_node, js_node in zip(py["nodes"], js["flow"]["nodes"]):
                if py_node["type"] != "terminater":
                    continue
                if py_node["config"] != js_node["config"]:
                    keys = sorted(set(py_node["config"]) ^ set(js_node["config"])
                                  | {k for k in py_node["config"] if k in js_node["config"] and py_node["config"][k] != js_node["config"][k]})
                    differences.append(f"{case['name']}: {keys}")
        self.assertEqual(differences, [], "\n".join(differences))

    def test_the_browser_enforces_every_text_limit(self):
        for key, limit in fm.TERMINATER_TEXT_LIMITS.items():
            case = next(c for c in self.cases if c["name"] == f"limit {key} over")
            result = self.js[self.cases.index(case)]
            self.assertFalse(result["ok"], f"the browser accepted a {key} of {limit + 1} characters")

    def test_the_browser_tables_equal_the_server_tables(self):
        text = MODEL_JS.read_text(encoding="utf-8")
        for action in fm.TERMINATER_ACTIONS:
            self.assertIn(f"'{action}'", text, action)
        self.assertIn("terminaterKinds = ['cmd', 'powershell', 'pwsh']", text)


# --------------------------------------------------------------------------- #
# The interpreter                                                              #
# --------------------------------------------------------------------------- #

class BuildGateTests(SimpleTestCase):
    """The release build refused to package the panel when Terminater became its ninth operation:
    the gate required the PROMPTING kickoff example to contain every operation."""

    def test_the_shipped_example_covers_every_prompting_operation(self):
        sample = AGENT_DIR.parents[1] / "docs" / "examples" / "prompting-kickoff.fpmt"
        flow = fm.validate_flow(json.loads(sample.read_text(encoding="utf-8-sig")), playable=True)
        self.assertEqual({n["type"] for n in flow["nodes"]}, fm.OPERATIONS - {"terminater"})

    def test_terminater_is_validated_by_the_gate_on_its_own(self):
        text = (AGENT_DIR / "management" / "commands" / "check_prompt_flow_panel.py").read_text(encoding="utf-8")
        self.assertIn("PROMPTING_OPERATIONS = OPERATIONS - TERMINAL_OPERATIONS", text)
        self.assertIn("!= PROMPTING_OPERATIONS", text)
        # a Terminater node must still go through the validator of the FROZEN build
        self.assertIn("'type': 'terminater'", text)
        self.assertIn("validate_flow(terminal_flow, playable=True)", text)

    def test_the_node_the_gate_validates_is_accepted(self):
        flow = {"format": fm.FORMAT, "version": fm.VERSION, "name": "Terminater release check",
                "start": "terminal", "edges": [],
                "nodes": [{"id": "terminal", "type": "terminater",
                           "config": {"action": "run", "text": "Write-Output release-check"}}]}
        self.assertEqual([n["type"] for n in fm.validate_flow(flow, playable=True)["nodes"]], ["terminater"])


class FakeRuntime:
    def __init__(self, terminal_output="C:\\ listing", fail=None):
        self.calls = []
        self.cancelled = False
        self.terminal_output = terminal_output
        self.fail = fail

    async def prompt(self, text, config):
        self.calls.append(("prompt", text))
        return "ok, understood"

    async def feed(self, text):
        self.calls.append(("feed", text))

    async def flush(self):
        self.calls.append(("flush",))

    async def clean_history(self):
        self.calls.append(("clean",))

    async def comment(self, text):
        self.calls.append(("comment", text))

    async def terminal(self, text, config):
        self.calls.append(("terminal", text, dict(config)))
        if self.fail:
            raise self.fail
        return self.terminal_output(text) if callable(self.terminal_output) else self.terminal_output

    def cancel(self):
        self.cancelled = True


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []

    async def emit(self, event, **data):
        self.events.append((event, data))

    async def run_flow(self, nodes, edges=(), runtime=None):
        runtime = runtime or FakeRuntime()
        flow = fm.validate_flow(diagram(nodes, edges), playable=True)
        runner = fm.FlowRunner(flow, runtime, self.emit)
        await runner.run()
        return runner, runtime

    async def test_a_terminater_step_reaches_the_runtime_with_its_settings(self):
        _, runtime = await self.run_flow([node(text="dir C:\\", kind="cmd", typing_wpm=120)])
        call = [c for c in runtime.calls if c[0] == "terminal"][0]
        self.assertEqual(call[1], "dir C:\\")
        self.assertEqual(call[2]["kind"], "cmd")
        self.assertEqual(call[2]["typing_wpm"], 120)
        self.assertEqual(call[2]["action"], "run")

    async def test_its_output_becomes_last_output(self):
        runner, _ = await self.run_flow([node()], runtime=FakeRuntime("DIR-OUTPUT"))
        self.assertEqual(runner.last_output, "DIR-OUTPUT")

    async def test_last_output_is_available_to_the_next_prompt(self):
        _, runtime = await self.run_flow(
            [node("t"), prompt("p", "Summarise: {{last_output}}")], [("t", "p", "next")],
            runtime=FakeRuntime("ABC"))
        self.assertIn(("prompt", "Summarise: ABC"), runtime.calls)

    async def test_last_output_is_available_to_the_terminal_command(self):
        _, runtime = await self.run_flow(
            [prompt("p", "Name a file"), node("t", text="type {{last_output}}")], [("p", "t", "next")])
        self.assertEqual([c for c in runtime.calls if c[0] == "terminal"][0][1], "type ok, understood")

    async def test_substitution_is_literal(self):
        _, runtime = await self.run_flow(
            [prompt("p", "x"), node("t", text="echo {{last_output}} {{unknown}}")], [("p", "t", "next")])
        self.assertEqual([c for c in runtime.calls if c[0] == "terminal"][0][1], "echo ok, understood {{unknown}}")

    async def test_a_decision_can_branch_on_the_terminals_output(self):
        flow_nodes = [node("t"), decision("d", "BUILD OK"), prompt("yes", "good"), prompt("no", "bad")]
        _, runtime = await self.run_flow(flow_nodes, [("t", "d", "next"), ("d", "yes", "yes"), ("d", "no", "no")],
                                         runtime=FakeRuntime("... build ok ..."))
        texts = [c[1] for c in runtime.calls if c[0] == "prompt"]
        self.assertEqual(texts, ["good"])

    async def test_the_no_branch(self):
        flow_nodes = [node("t"), decision("d", "BUILD OK"), prompt("yes", "good"), prompt("no", "bad")]
        _, runtime = await self.run_flow(flow_nodes, [("t", "d", "next"), ("d", "yes", "yes"), ("d", "no", "no")],
                                         runtime=FakeRuntime("failed"))
        self.assertEqual([c[1] for c in runtime.calls if c[0] == "prompt"], ["bad"])

    async def test_the_node_events_are_emitted(self):
        await self.run_flow([node()])
        statuses = [d["status"] for e, d in self.events if e == "node"]
        self.assertEqual(statuses, ["running", "completed"])
        self.assertTrue([d for e, d in self.events if e == "output" and d["text"] == "C:\\ listing"])

    async def test_an_empty_output_still_replaces_last_output(self):
        runner, _ = await self.run_flow([prompt("p"), node("t")], [("p", "t", "next")], runtime=FakeRuntime(""))
        self.assertEqual(runner.last_output, "")

    async def test_a_hub_refusal_stops_the_flow(self):
        runtime = FakeRuntime(fail=fm.FlowError("Terminater could not run: refused."))
        flow = fm.validate_flow(diagram([node(), prompt("p")], [("t", "p", "next")]), playable=True)
        runner = fm.FlowRunner(flow, runtime, self.emit)
        with self.assertRaises(fm.FlowError):
            await runner.run()
        self.assertEqual([c for c in runtime.calls if c[0] == "prompt"], [])

    async def test_a_loop_is_bounded_by_the_step_limit(self):
        flow = fm.validate_flow(diagram([node("t")], [("t", "t", "next")], max_steps=5), playable=True)
        runner = fm.FlowRunner(flow, FakeRuntime(), self.emit)
        with self.assertRaisesRegex(fm.FlowError, "Step limit"):
            await runner.run()

    async def test_stop_cancels_the_runtime(self):
        flow = fm.validate_flow(diagram([node()]), playable=True)
        runtime = FakeRuntime()
        runner = fm.FlowRunner(flow, runtime, self.emit)
        runner.stop()
        with self.assertRaises(fm.FlowStopped):
            await runner.run()
        self.assertTrue(runtime.cancelled)

    async def test_pause_holds_the_next_terminal_step(self):
        flow = fm.validate_flow(diagram([node()]), playable=True)
        runtime = FakeRuntime()
        runner = fm.FlowRunner(flow, runtime, self.emit)
        runner.resumed.clear()
        task = asyncio.ensure_future(runner.run())
        await asyncio.sleep(0.4)
        self.assertEqual(runtime.calls, [])
        runner.resumed.set()
        await asyncio.wait_for(task, 5)
        self.assertEqual(len([c for c in runtime.calls if c[0] == "terminal"]), 1)


# --------------------------------------------------------------------------- #
# The runtime adapter                                                          #
# --------------------------------------------------------------------------- #

class RuntimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make(self, pk=7):
        from .prompt_flow_panel_runtime import PromptFlowPanelRuntime

        rt = PromptFlowPanelRuntime.__new__(PromptFlowPanelRuntime)
        rt.cancelled = False
        rt.user = SimpleNamespace(pk=pk)
        rt.active_epoch = None
        rt.events = []

        async def emit(event, **data):
            rt.events.append((event, data))

        rt.emit = emit
        return rt

    async def test_the_action_and_settings_reach_the_hub(self):
        rt = self.make(pk=9)
        seen = {}

        def fake(action, params, wait):
            seen.update(action=action, params=params, wait=wait)
            return {"ok": True, "status": "completed", "output": "hello"}

        with patch.object(terminal_hub, "run_action", side_effect=fake):
            out = await rt.terminal("echo hello", {"action": "run", "kind": "cmd", "typing_wpm": 90, "text": "stale"})
        self.assertEqual(out, "hello")
        self.assertEqual(seen["action"], "run")
        self.assertTrue(seen["wait"])
        self.assertEqual(seen["params"]["text"], "echo hello")
        self.assertEqual(seen["params"]["user"], "9")
        self.assertEqual(seen["params"]["kind"], "cmd")
        self.assertEqual(seen["params"]["typing_wpm"], 90)
        self.assertNotIn("action", seen["params"])

    async def test_a_progress_event_names_the_action_and_status(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action", return_value={"ok": True, "status": "completed", "output": "x"}):
            await rt.terminal("x", {"action": "run"})
        self.assertIn(("progress", {"message": "Terminater run: completed"}), rt.events)

    async def test_without_output_the_message_is_used(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action", return_value={"ok": True, "status": "killed", "message": "closed it"}):
            self.assertEqual(await rt.terminal("", {"action": "kill"}), "closed it")

    async def test_without_either_the_result_is_empty(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action", return_value={"ok": True, "status": "killed"}):
            self.assertEqual(await rt.terminal("", {"action": "kill"}), "")

    async def test_output_is_cut_at_one_hundred_thousand_characters(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action", return_value={"ok": True, "status": "completed", "output": "x" * 150_000}):
            self.assertEqual(len(await rt.terminal("x", {"action": "run"})), 100_000)

    async def test_a_failed_command_is_a_result_not_an_error(self):
        rt = self.make()
        for status in ("command_failed", "hung", "timeout", "operator_required", "aborted"):
            with self.subTest(status=status), patch.object(terminal_hub, "run_action", return_value={
                    "ok": True, "status": status, "success": False, "output": f"out-{status}"}):
                self.assertEqual(await rt.terminal("x", {"action": "run"}), f"out-{status}")

    async def test_a_refusal_is_an_error(self):
        rt = self.make()
        from .services.prompt_flow_panel import FlowError

        with patch.object(terminal_hub, "run_action", return_value={
                "ok": False, "status": "refused", "message": "No terminal named 'x'."}):
            with self.assertRaisesRegex(FlowError, "No terminal named"):
                await rt.terminal("x", {"action": "type"})

    async def test_error_and_unavailable_statuses_are_errors_even_when_ok(self):
        rt = self.make()
        from .services.prompt_flow_panel import FlowError

        for status in ("error", "unavailable", "refused"):
            with self.subTest(status=status), patch.object(terminal_hub, "run_action", return_value={
                    "ok": True, "status": status}):
                with self.assertRaisesRegex(FlowError, "Terminater could not"):
                    await rt.terminal("x", {"action": "run"})

    async def test_a_cancelled_run_never_reaches_the_hub(self):
        rt = self.make()
        rt.cancelled = True
        from .services.prompt_flow_panel import FlowStopped

        with patch.object(terminal_hub, "run_action") as fake:
            with self.assertRaises(FlowStopped):
                await rt.terminal("x", {"action": "run"})
        fake.assert_not_called()

    async def test_a_cancel_during_the_action_raises_after_it_returns(self):
        rt = self.make()
        from .services.prompt_flow_panel import FlowStopped

        def slow(action, params, wait):
            rt.cancelled = True
            return {"ok": True, "status": "completed", "output": "late"}

        with patch.object(terminal_hub, "run_action", side_effect=slow):
            with self.assertRaises(FlowStopped):
                await rt.terminal("x", {"action": "run"})

    async def test_the_busy_flag_is_released_after_an_exception(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                await rt.terminal("x", {"action": "run"})
        self.assertFalse(rt._terminal_busy)

    async def test_cancel_while_typing_aborts_the_terminal_off_the_loop(self):
        rt = self.make(pk=5)
        calls = []
        done = threading.Event()

        def fake(action, params, wait):
            calls.append((action, params))
            if action == "abort":
                done.set()
            return {"ok": True, "status": "aborted"}

        rt._terminal_busy = True
        rt._terminal_id = "t2"
        with patch.object(terminal_hub, "run_action", side_effect=fake):
            rt.cancel()
            self.assertTrue(await asyncio.to_thread(done.wait, 5))
        self.assertTrue(rt.cancelled)
        self.assertEqual(calls[0], ("abort", {"user": "5", "terminal": "t2"}))

    async def test_cancel_when_idle_does_not_touch_the_hub(self):
        rt = self.make()
        with patch.object(terminal_hub, "run_action") as fake:
            rt.cancel()
            await asyncio.sleep(0.1)
        fake.assert_not_called()

    async def test_abort_failures_are_swallowed(self):
        rt = self.make()
        rt._terminal_busy = True
        rt._terminal_id = "t2"
        with patch.object(terminal_hub, "run_action", side_effect=RuntimeError("hub gone")):
            rt._abort_terminal()

    async def test_stop_during_shell_creation_never_aborts_an_unrelated_terminal(self):
        rt = self.make()
        rt._terminal_busy = True
        rt._terminal_id = None
        with patch.object(terminal_hub, "run_action") as action:
            rt.cancel()
            await asyncio.sleep(.1)
        action.assert_not_called()
        with self.assertRaises(eng.TerminaterError):
            rt._select_terminal("t1")


@unittest.skipUnless(kit.conpty_ok(), "ConPTY is not available on this machine")
class RealTerminalStepTests(unittest.IsolatedAsyncioTestCase):
    """A whole flow whose Terminater step really types into a real shell."""

    async def asyncSetUp(self):
        terminal_hub.reset_for_tests()
        self.hub = kit.fresh_hub(max_terminals=4)
        terminal_hub._HUB = self.hub
        self.fast = kit.FastTyping(0.04)
        self.fast.__enter__()

    async def asyncTearDown(self):
        self.fast.__exit__(None, None, None)
        await asyncio.to_thread(terminal_hub.reset_for_tests)

    def runtime(self):
        from .prompt_flow_panel_runtime import PromptFlowPanelRuntime

        rt = PromptFlowPanelRuntime.__new__(PromptFlowPanelRuntime)
        rt.cancelled = False
        rt.user = SimpleNamespace(pk=77)
        rt.active_epoch = None

        async def emit(event, **data):
            pass

        rt.emit = emit
        return rt

    async def test_a_real_command_returns_its_real_output(self):
        out = await self.runtime().terminal(
            "echo flow-step-real-output", {"action": "run", "kind": "cmd", "wait_seconds": 30, "title": "pfp"})
        self.assertIn("flow-step-real-output", out)

    async def test_two_steps_share_one_titled_terminal(self):
        rt = self.runtime()
        await rt.terminal("set STEPVAR=kept", {"action": "run", "kind": "cmd", "terminal": "shared", "wait_seconds": 30})
        out = await rt.terminal("echo %STEPVAR%", {"action": "run", "kind": "cmd", "terminal": "shared", "wait_seconds": 30})
        self.assertIn("kept", out)
        listing = self.hub.call("list", {"user": "77"})["terminals"]
        self.assertEqual(len(listing), 1)

    async def test_a_failing_native_command_is_delivered_as_a_result(self):
        out = await self.runtime().terminal(
            "cmd /c exit 3", {"action": "run", "kind": "powershell", "wait_seconds": 40, "load_profile": False})
        self.assertIsInstance(out, str)

    async def test_stop_aborts_a_command_in_progress(self):
        rt = self.runtime()
        task = asyncio.ensure_future(rt.terminal(
            "ping -n 60 127.0.0.1", {"action": "run", "kind": "cmd", "wait_seconds": 120, "typing_wpm": 160}))
        for _ in range(100):
            sessions = self.hub.space("77").sessions if "77" in self.hub._spaces else {}
            if any(s.state == eng.ST_RUNNING for s in sessions.values()):
                break
            await asyncio.sleep(0.2)
        running = next(iter(self.hub.space("77").sessions.values()))
        other = await asyncio.to_thread(self.hub.open, "77", kind="cmd", title="unrelated")
        self.assertNotEqual(other["terminal"]["id"], running.id)
        rt.cancel()
        from .services.prompt_flow_panel import FlowStopped

        with self.assertRaises(FlowStopped):
            await asyncio.wait_for(task, 60)
        session = running
        self.assertTrue(await asyncio.to_thread(kit.wait_until, lambda: session.state == eng.ST_PROMPT, 20))
        self.assertEqual(self.hub._get(self.hub.space("77"), other["terminal"]["id"]).state, eng.ST_PROMPT)
