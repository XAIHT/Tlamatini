# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Terminater reliability: the chat model's door to the terminal can no longer lie, guess or glue.

WHY THESE TESTS EXIST (a Rust tutorial, 2026-10-21).  Over eleven turns Tlamatini told the user a
line was "typed and sitting on your prompt" in turns where she had called NO tool, ran commands
through invisible shells although the user said "I will execute them, not you", opened a NEW
terminal because a sentence-parser read ``terminal='t2' (title Rust Lesson) using action='run``
as the terminal's name, and pressed Enter on a line the user had asked to leave alone because
``submit=false -- type the line but do NOT press Enter`` was read as TRUE.

Five layers, one suite:

* the strict ARGUMENT helpers (``parse_flag``, ``terminal_ref_problem``, ``line_matches``);
* the TYPED tool (``terminater_tool``): a schema, not a sentence;
* the ENGINE read-back, in REAL shells (typed means *the screen shows it*);
* the GUARD (``terminal_guard``): the live-tutorial mode, the ledger and the claim audit;
* the EXECUTOR wiring (``mcp_agent``) that makes the guard bind.

Real shells are skipped (never faked) on a machine without ConPTY.
"""
from __future__ import annotations

import ast
import base64
import json
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from . import agent_verdict
from . import terminal_guard as guard
from . import terminater_testkit as kit
from . import terminater_tool as door
from .chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
from .services import agent_contracts

AGENT_DIR = Path(__file__).resolve().parent
SPEC = WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_terminater"]
TX = kit.tx()
ENG = kit.engine()
U = "reliability-test"

# What Angela's install really answered in the Rust lesson (the sentence that broke the tool).
THE_RUST_TOOL_SENTENCE = (
    "Type into the terminal with terminal='t2' (title Rust Lesson) using action='run', "
    "text='cargo --version', submit=false -- type the line but do NOT press Enter."
)
THE_GARBAGE_TERMINAL_REF = "t2' (title Rust Lesson) using action='run"
THE_RUST_USER_SENTENCE = "you show me the commands and I will execute them, not you"


def _ascii(value):
    return json.loads(json.dumps(value))


def _wrap(payload):
    return json.dumps(payload, ensure_ascii=False)


def _read(relative):
    return (AGENT_DIR / relative).read_text(encoding="utf-8")


class _Launch:
    """Stands in for ``tools._launch_wrapped_chat_agent`` and records what the door sent."""

    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply if reply is not None else {"status": "completed", "agent_status": "typed",
                                                       "typed": "x", "verified": True, "enter_pressed": False}

    def __call__(self, spec, request, *, auto_diagnose=True, config_overrides=None):
        self.calls.append({"spec": spec, "request": request, "cfg": dict(config_overrides or {})})
        return _wrap(self.reply)


def _tool(launch=None):
    launch = launch or _Launch()
    return door.build_tool(SPEC, launch, _wrap), launch


# --------------------------------------------------------------------------- #
# 1. Strict argument helpers                                                   #
# --------------------------------------------------------------------------- #

class ParseFlagTests(SimpleTestCase):
    def test_clean_true_tokens(self):
        for value in (True, 1, "true", "True", "YES", "y", "on", "1", " true "):
            self.assertEqual(TX.parse_flag(value, default=False), (True, ""), repr(value))

    def test_clean_false_tokens(self):
        for value in (False, 0, "false", "False", "NO", "n", "off", "0", "none", "null"):
            self.assertEqual(TX.parse_flag(value, default=True), (False, ""), repr(value))

    def test_blank_and_none_mean_the_default(self):
        for value in (None, "", "   "):
            self.assertEqual(TX.parse_flag(value, default=True), (True, ""))
            self.assertEqual(TX.parse_flag(value, default=False), (False, ""))

    def test_the_sentence_that_pressed_enter_is_read_as_the_safe_side_with_a_note(self):
        sentence = "false - type the line but do NOT press Enter, leave it sitting on the prompt"
        flag, note = TX.parse_flag(sentence, default=True, safe=False)
        self.assertIs(flag, False)
        self.assertIn("not a clear yes/no", note)
        self.assertIn("false", note.lower())

    def test_the_safe_side_can_be_true_for_secret(self):
        flag, note = TX.parse_flag("kind of", default=False, safe=True)
        self.assertIs(flag, True)
        self.assertTrue(note)

    def test_without_a_safe_side_the_default_is_used(self):
        self.assertEqual(TX.parse_flag("maybe", default=True)[0], True)
        self.assertEqual(TX.parse_flag("maybe", default=False)[0], False)

    def test_numbers_other_than_zero_and_one_are_not_a_yes_no(self):
        flag, note = TX.parse_flag(7, default=True, safe=False)
        self.assertIs(flag, False)
        self.assertTrue(note)

    def test_it_never_raises(self):
        for value in (object(), [], {}, b"x", float("nan")):
            flag, _note = TX.parse_flag(value, default=True, safe=False)
            self.assertIsInstance(flag, bool)


class TerminalReferenceTests(SimpleTestCase):
    def test_ids_and_short_titles_are_fine(self):
        for ref in ("t1", "T12", "Rust Lesson", "build", "ps main", ""):
            self.assertEqual(TX.terminal_ref_problem(ref), "", repr(ref))

    def test_the_real_garbage_from_the_rust_lesson_is_refused(self):
        problem = TX.terminal_ref_problem(THE_GARBAGE_TERMINAL_REF)
        self.assertTrue(problem)
        self.assertIn("sentence", problem)

    def test_each_forbidden_character_is_named(self):
        for ch in ("'", chr(34), "=", "<", ">", "|", ";", "`"):
            self.assertTrue(TX.terminal_ref_problem("ab" + ch + "cd"), repr(ch))

    def test_control_characters_are_refused(self):
        self.assertTrue(TX.terminal_ref_problem("a" + chr(10) + "b"))
        self.assertTrue(TX.terminal_ref_problem("a" + chr(0) + "b"))

    def test_very_long_or_wordy_references_are_refused(self):
        self.assertTrue(TX.terminal_ref_problem("x" * 61))
        self.assertTrue(TX.terminal_ref_problem("one two three four five six seven eight nine"))

    def test_looks_like_terminal_id(self):
        for ref in ("t1", "T2", "t1234", " t9 "):
            self.assertTrue(TX.looks_like_terminal_id(ref), ref)
        for ref in ("t", "t12345", "terminal", "x1", "1t", "", None):
            self.assertFalse(TX.looks_like_terminal_id(ref), repr(ref))


class LineComparisonTests(SimpleTestCase):
    def test_norm_line_collapses_whitespace_and_nbsp(self):
        self.assertEqual(TX.norm_line("  a \t b" + chr(0xA0) + "c  "), "a b c")
        self.assertEqual(TX.norm_line(None), "")

    def test_last_line_is_the_last_non_empty(self):
        self.assertEqual(TX.last_line("a" + chr(13) + chr(10) + "b" + chr(10) + chr(10)), "b")
        self.assertEqual(TX.last_line(""), "")

    def test_exact_contains_mismatch_and_empty(self):
        self.assertEqual(TX.line_matches("cargo  --version", "cargo --version"), (True, "exact"))
        self.assertEqual(TX.line_matches("PS> cargo --version", "cargo --version"), (True, "contains"))
        self.assertEqual(TX.line_matches("cargo build", "cargo --version"), (False, "mismatch"))
        self.assertEqual(TX.line_matches("", "cargo --version"), (False, "empty"))

    def test_an_empty_expectation_matches_only_an_empty_screen(self):
        self.assertEqual(TX.line_matches("", "")[0], True)
        self.assertEqual(TX.line_matches("junk", "")[0], False)


class VirtualScreenWrapFlagTests(SimpleTestCase):
    """A stale 'continuation' flag glued the next output line onto the echo of a command."""

    def screen(self, cols=10, rows=4):
        return TX.VTScreen(cols, rows, 100)

    def test_text_from_rejoins_a_wrapped_line(self):
        s = self.screen()
        s.feed("0123456789AB")
        self.assertEqual(s.text_from(0, 0), "0123456789AB")

    def test_text_from_honours_the_start_column(self):
        s = self.screen(cols=20)
        s.feed("PS> dir")
        self.assertEqual(s.text_from(0, 4), "dir")

    def test_a_real_line_feed_clears_a_stale_continuation_flag(self):
        s = self.screen()
        s.wrap[1] = True                       # left over from text that was erased
        s.feed("first" + chr(13) + chr(10) + "second")
        self.assertEqual(s.text(), "first" + chr(10) + "second")

    def test_a_genuine_autowrap_still_joins(self):
        s = self.screen(cols=5)
        s.feed("abcdefgh")
        self.assertEqual(s.text(), "abcdefgh")

    def test_erasing_a_whole_row_clears_its_flag_but_a_partial_erase_keeps_it(self):
        s = self.screen()
        s.wrap[1] = True
        s.feed("x" + chr(27) + "[2;1H" + chr(27) + "[K")      # cursor to row 2 col 1, erase to the end
        self.assertIs(s.wrap[1], False)
        s.wrap[1] = True
        s.feed(chr(27) + "[2;5H" + chr(27) + "[K")              # from column 5: only part of the row
        self.assertIs(s.wrap[1], True)


# --------------------------------------------------------------------------- #
# 2. The typed door                                                            #
# --------------------------------------------------------------------------- #

class PrepareTests(SimpleTestCase):
    def test_text_alone_means_run(self):
        prepared = door.prepare({"text": "cargo --version"})
        self.assertEqual(prepared.action, "run")
        self.assertEqual(prepared.cfg["action"], "run")
        self.assertEqual(prepared.cfg["text"], "cargo --version")

    def test_no_action_and_no_text_is_refused_with_advice(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({})
        self.assertEqual(ctx.exception.code, "missing_action")
        self.assertIn("sentence", ctx.exception.message)

    def test_action_aliases_and_spacing(self):
        self.assertEqual(door.prepare({"action": "Force-Kill", "terminal": "t1"}).action, "force_kill")
        self.assertEqual(door.prepare({"action": "execute", "text": "dir"}).action, "run")
        self.assertEqual(door.prepare({"action": "output"}).action, "read")

    def test_an_unknown_action_lists_the_valid_ones(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "typo"})
        self.assertEqual(ctx.exception.code, "unknown_action")
        for action in ("run", "open", "handover"):
            self.assertIn(action, ctx.exception.message)

    def test_an_unknown_argument_is_refused_not_dropped(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "run", "text": "x", "submitt": False})
        self.assertEqual(ctx.exception.code, "unknown_argument")
        self.assertIn("submitt", ctx.exception.message)

    def test_the_garbage_terminal_reference_is_refused_before_anything_runs(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "run", "terminal": THE_GARBAGE_TERMINAL_REF, "text": "cargo --version"})
        self.assertEqual(ctx.exception.code, "bad_terminal_ref")
        self.assertIn("terminal_id", ctx.exception.message)

    def test_an_integer_terminal_becomes_its_id(self):
        self.assertEqual(door.prepare({"action": "read", "terminal": 3}).cfg["terminal"], "t3")

    def test_run_and_type_need_text(self):
        for action in ("run", "type"):
            with self.assertRaises(door.ArgError) as ctx:
                door.prepare({"action": action, "terminal": "t1"})
            self.assertEqual(ctx.exception.code, "empty_text")

    def test_send_key_needs_keys(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "send_key", "terminal": "t1"})
        self.assertEqual(ctx.exception.code, "missing_keys")

    def test_create_if_missing_defaults_to_false_for_the_chat(self):
        self.assertIs(door.prepare({"action": "run", "text": "x"}).cfg["create_if_missing"], False)
        self.assertIs(door.prepare({"action": "run", "text": "x", "create_if_missing": True}).cfg["create_if_missing"],
                      True)

    def test_a_kind_is_normalised_or_refused(self):
        self.assertEqual(door.prepare({"action": "open", "kind": "PS"}).cfg["kind"], "powershell")
        self.assertEqual(door.prepare({"action": "open", "kind": "cmd.exe"}).cfg["kind"], "cmd")
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "open", "kind": "bash"})
        self.assertEqual(ctx.exception.code, "bad_kind")

    def test_a_severity_is_checked(self):
        self.assertEqual(door.prepare({"action": "warn_user", "message": "x", "severity": "DANGER"}).cfg["severity"],
                         "danger")
        with self.assertRaises(door.ArgError):
            door.prepare({"action": "warn_user", "message": "x", "severity": "loud"})

    def test_zero_seconds_echoed_from_a_schema_default_mean_not_set(self):
        cfg = door.prepare({"action": "run", "text": "x", "hang_seconds": 0, "wait_seconds": 0, "typing_wpm": 0,
                            "idle_seconds": 0, "read_chars": 0}).cfg
        for key in ("hang_seconds", "wait_seconds", "typing_wpm", "idle_seconds", "read_chars"):
            self.assertNotIn(key, cfg, key)

    def test_real_numbers_are_kept_with_their_type(self):
        cfg = door.prepare({"action": "run", "text": "x", "wait_seconds": 30, "typing_wpm": 80.0}).cfg
        self.assertEqual(cfg["wait_seconds"], 30.0)
        self.assertIsInstance(cfg["wait_seconds"], float)
        self.assertEqual(cfg["typing_wpm"], 80)
        self.assertIsInstance(cfg["typing_wpm"], int)

    def test_text_is_passed_through_untouched(self):
        raw = "echo 'a b' C:\\x\\y " + chr(0xF1) + '  "q"  '
        self.assertEqual(door.prepare({"action": "run", "text": raw}).cfg["text"], raw)

    def test_text_b64_wins_over_text_with_a_note(self):
        blob = base64.b64encode(b"echo from-b64").decode()
        prepared = door.prepare({"action": "run", "text": "echo plain", "text_b64": blob})
        self.assertNotIn("text", prepared.cfg)
        self.assertEqual(prepared.cfg["text_b64"], blob)
        self.assertTrue(any("text_b64" in note for note in prepared.notes))

    def test_the_request_record_is_readable_and_hides_base64(self):
        blob = base64.b64encode(b"secret-ish").decode()
        prepared = door.prepare({"action": "run", "text_b64": blob, "terminal": "t1"})
        self.assertIn("terminal='t1'", prepared.request_text)
        self.assertNotIn(blob, prepared.request_text)

    def test_none_values_are_ignored(self):
        prepared = door.prepare({"action": "list", "terminal": None, "text": None, "submit": None})
        self.assertEqual(prepared.cfg["action"], "list")
        self.assertNotIn("submit", prepared.cfg)


class LiveTutorialModeInThePreparedCallTests(SimpleTestCase):
    def test_submit_is_forced_false_and_the_user_is_told(self):
        prepared = door.prepare({"action": "run", "terminal": "t1", "text": "cargo --version", "submit": True},
                                user_runs=True)
        self.assertIs(prepared.cfg["submit"], False)
        self.assertTrue(any(note.startswith("LIVE-TUTORIAL MODE") for note in prepared.notes))

    def test_a_missing_submit_is_also_forced_false(self):
        prepared = door.prepare({"action": "run", "terminal": "t1", "text": "ls"}, user_runs=True)
        self.assertIs(prepared.cfg["submit"], False)

    def test_an_explicit_false_adds_no_note(self):
        prepared = door.prepare({"action": "run", "terminal": "t1", "text": "ls", "submit": False}, user_runs=True)
        self.assertIs(prepared.cfg["submit"], False)
        self.assertEqual(prepared.notes, [])

    def test_a_multi_line_text_is_refused_because_each_break_is_an_enter(self):
        with self.assertRaises(door.ArgError) as ctx:
            door.prepare({"action": "run", "terminal": "t1", "text": "cd src" + chr(10) + "cargo build"},
                         user_runs=True)
        self.assertEqual(ctx.exception.code, "user_runs_multiline")

    def test_pressing_enter_is_refused(self):
        for keys in ("enter", "Return", "ctrl+m", "up up enter", "ctrl + m"):
            with self.assertRaises(door.ArgError, msg=keys) as ctx:
                door.prepare({"action": "send_key", "terminal": "t1", "keys": keys}, user_runs=True)
            self.assertEqual(ctx.exception.code, "user_runs_enter")

    def test_other_keys_are_allowed(self):
        for keys in ("ctrl+c", "up", "esc", "tab"):
            self.assertEqual(door.prepare({"action": "send_key", "terminal": "t1", "keys": keys},
                                          user_runs=True).cfg["keys"], keys)

    def test_reading_and_listing_are_untouched(self):
        for action in ("read", "list", "status", "commands", "wait"):
            prepared = door.prepare({"action": action, "terminal": "t1"}, user_runs=True)
            self.assertNotIn("submit", prepared.cfg, action)
            self.assertEqual(prepared.notes, [], action)

    def test_without_the_mode_nothing_is_forced(self):
        prepared = door.prepare({"action": "run", "terminal": "t1", "text": "ls", "submit": True}, user_runs=False)
        self.assertIs(prepared.cfg["submit"], True)
        self.assertEqual(prepared.notes, [])


class TypedSchemaTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = door.build_args_model()
        cls.schema = cls.model.model_json_schema()

    def test_one_property_per_setting(self):
        self.assertEqual(tuple(self.schema["properties"]), door.FIELD_NAMES)

    def test_nothing_is_required(self):
        self.assertFalse(self.schema.get("required"))

    def test_unknown_arguments_are_forbidden(self):
        self.assertIs(self.schema.get("additionalProperties"), False)
        with self.assertRaises(Exception):
            self.model.model_validate({"submitt": False})

    def test_the_types_are_simple_so_a_local_model_can_follow_them(self):
        props = self.schema["properties"]
        for name in ("submit", "wait", "secret", "create_if_missing", "clear_line", "check_line"):
            self.assertEqual(props[name]["type"], "boolean", name)
        for name in ("typing_wpm", "read_chars", "offset", "cursor"):
            self.assertEqual(props[name]["type"], "integer", name)
        for name in ("wait_seconds", "hang_seconds", "user_wait_seconds", "idle_seconds"):
            self.assertEqual(props[name]["type"], "number", name)
        for name in ("action", "terminal", "text", "kind", "title"):
            self.assertEqual(props[name]["type"], "string", name)
        for name, prop in props.items():
            self.assertNotIn("anyOf", prop, name)

    def test_every_setting_is_documented(self):
        for name, prop in self.schema["properties"].items():
            self.assertTrue(prop.get("description"), name)

    def test_a_sentence_is_not_a_yes_no(self):
        with self.assertRaises(Exception):
            self.model.model_validate({"submit": "false - type the line but do NOT press Enter"})

    def test_clean_words_are_accepted(self):
        self.assertIs(self.model.model_validate({"submit": "false"}).submit, False)
        self.assertIs(self.model.model_validate({"submit": "no"}).submit, False)
        self.assertIs(self.model.model_validate({"submit": "yes"}).submit, True)

    def test_an_integer_terminal_is_accepted(self):
        self.assertEqual(self.model.model_validate({"terminal": 2}).terminal, "t2")

    def test_numbers_must_be_numbers(self):
        with self.assertRaises(Exception):
            self.model.model_validate({"typing_wpm": "fast"})

    def test_the_fields_exist_in_the_agent_config(self):
        import yaml

        config = yaml.safe_load(_read("agents/terminater/config.yaml"))
        for name in door.FIELD_NAMES:
            self.assertIn(name, config, name)

    def test_the_actions_equal_the_engine_actions_and_aliases(self):
        self.assertEqual(door.ACTIONS, tuple(ENG.ACTIONS))
        self.assertEqual(door.ACTION_ALIASES, dict(ENG._ACTION_ALIASES))

    def test_the_kinds_equal_the_engine_kinds(self):
        self.assertEqual(door.KINDS, tuple(ENG.KINDS))


class TypedToolTests(SimpleTestCase):
    def setUp(self):
        guard.reset()

    def test_the_tool_carries_the_name_and_the_typed_schema(self):
        tool, _ = _tool()
        self.assertEqual(tool.name, "chat_agent_terminater")
        self.assertEqual(set(tool.args), set(door.FIELD_NAMES))
        self.assertIn("ONE ARGUMENT PER SETTING", tool.description)

    def test_the_openai_tool_form_is_what_a_model_is_given(self):
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool, _ = _tool()
        function = convert_to_openai_tool(tool)["function"]
        self.assertEqual(function["name"], "chat_agent_terminater")
        self.assertEqual(function["parameters"]["properties"]["submit"]["type"], "boolean")

    def test_typed_arguments_reach_the_launcher_as_a_config_never_as_a_sentence(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"action": "run", "terminal": "t2", "text": "cargo --version", "submit": False,
                                      "title": "Rust Lesson"}))
        self.assertEqual(out["status"], "completed")
        sent = launch.calls[0]
        self.assertEqual(sent["cfg"]["terminal"], "t2")
        self.assertEqual(sent["cfg"]["title"], "Rust Lesson")
        self.assertIs(sent["cfg"]["submit"], False)
        self.assertIs(sent["cfg"]["create_if_missing"], False)

    def test_the_title_can_no_longer_swallow_the_next_parameter(self):
        tool, launch = _tool()
        tool.invoke({"action": "run", "terminal": "t2", "title": "Rust Lesson", "text": "cargo --version",
                     "submit": False})
        cfg = launch.calls[0]["cfg"]
        self.assertEqual(cfg["terminal"], "t2")
        self.assertNotIn("using", cfg["terminal"])
        self.assertEqual(cfg["text"], "cargo --version")

    def test_null_arguments_are_treated_as_not_given(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"action": "list", "terminal": None, "text": None, "submit": None,
                                      "wait_seconds": None}))
        self.assertEqual(out["status"], "completed")
        self.assertEqual(launch.calls[0]["cfg"]["action"], "list")
        self.assertNotIn("submit", launch.calls[0]["cfg"])

    def test_a_bad_value_is_a_refusal_the_model_can_act_on_and_nothing_runs(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"action": "run", "text": "x", "submit": "false - do NOT press Enter"}))
        self.assertEqual(out["status"], "refused")
        self.assertEqual(out["code"], "bad_argument")
        self.assertIs(out["success"], False)
        self.assertEqual(out["error_kind"], "request")
        self.assertIn("submit", out["message"])
        self.assertEqual(launch.calls, [])

    def test_an_unknown_argument_is_a_refusal_and_nothing_runs(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"action": "run", "text": "x", "submitt": False}))
        self.assertEqual(out["status"], "refused")
        self.assertEqual(launch.calls, [])

    def test_the_old_request_sentence_is_refused_with_the_new_form(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"request": THE_RUST_TOOL_SENTENCE}))
        self.assertEqual(out["status"], "refused")
        self.assertEqual(launch.calls, [])
        out = json.loads(tool.invoke(THE_RUST_TOOL_SENTENCE))
        self.assertEqual(out["code"], "sentence_not_accepted")
        self.assertIn("separate fields", out["message"])
        self.assertEqual(launch.calls, [])

    def test_a_json_object_in_a_single_string_is_accepted(self):
        tool, launch = _tool()
        tool.invoke(json.dumps({"action": "list"}))
        self.assertEqual(launch.calls[0]["cfg"]["action"], "list")

    def test_the_garbage_terminal_is_refused_at_the_door(self):
        tool, launch = _tool()
        out = json.loads(tool.invoke({"action": "run", "terminal": THE_GARBAGE_TERMINAL_REF, "text": "x"}))
        self.assertEqual(out["code"], "bad_terminal_ref")
        self.assertEqual(launch.calls, [])

    def test_live_tutorial_mode_is_applied_from_the_call_context(self):
        tool, launch = _tool()
        token = guard.enter_mode(True)
        try:
            out = json.loads(tool.invoke({"action": "run", "terminal": "t1", "text": "cargo --version",
                                          "submit": True}))
        finally:
            guard.leave_mode(token)
        self.assertIs(launch.calls[0]["cfg"]["submit"], False)
        self.assertIs(out["live_tutorial_mode"], True)
        self.assertTrue(any("Enter was NOT pressed" in note for note in out["request_notes"]))
        self.assertFalse(guard.user_runs_active())

    def test_outside_the_mode_submit_is_left_alone(self):
        tool, launch = _tool()
        tool.invoke({"action": "run", "terminal": "t1", "text": "ls", "submit": True})
        self.assertIs(launch.calls[0]["cfg"]["submit"], True)

    def test_other_wrapped_agents_keep_their_sentence_tool(self):
        from . import tools

        pdfer = tools._build_wrapped_chat_agent_tool(WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_pdfer"])
        self.assertNotIn("action", pdfer.args)
        self.assertEqual(len(pdfer.args), 1, "a sentence tool takes ONE argument")
        mine = tools._build_wrapped_chat_agent_tool(SPEC)
        self.assertIn("action", mine.args)
        self.assertIs(tools._build_wrapped_chat_agent_tool(SPEC), mine)     # cached


class LauncherTypedPathTests(SimpleTestCase):
    def test_the_typed_helper_sets_each_value_as_given(self):
        from . import tools

        config = {"action": "run", "submit": True, "text": "", "create_if_missing": True}
        out, error, notes = tools._apply_typed_overrides_to_config(
            config, {"action": "type", "submit": False, "text": "C:\\x\\y 'q'"})
        self.assertIsNone(error)
        self.assertEqual(out["text"], "C:\\x\\y 'q'")
        self.assertIs(out["submit"], False)
        self.assertEqual(sorted(notes), ["action", "submit", "text"])

    def test_a_key_the_agent_does_not_have_is_an_error_not_a_guess(self):
        from . import tools

        out, error, _notes = tools._apply_typed_overrides_to_config({"action": "run"}, {"bogus": 1})
        self.assertIsNone(out)
        self.assertIn("bogus", error)

    def test_a_non_mapping_is_an_error(self):
        from . import tools

        self.assertIsNone(tools._apply_typed_overrides_to_config({"a": 1}, ["a"])[0])

    def test_the_launcher_has_a_typed_path_that_skips_the_sentence_parsers(self):
        source = _read("tools.py")
        self.assertIn("config_overrides=None", source)
        self.assertIn("_apply_typed_overrides_to_config(", source)
        tree = ast.parse(source)
        launcher = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                        and n.name == "_launch_wrapped_chat_agent")
        self.assertIn("config_overrides", [a.arg for a in launcher.args.kwonlyargs])
        for node in ast.walk(launcher):
            if isinstance(node, ast.If) and "config_overrides" in ast.unparse(node.test):
                break
        else:
            self.fail("the launcher never branches on config_overrides")
        text = ast.get_source_segment(source, launcher)
        self.assertIn("[] if config_overrides is not None", text)                 # prose fallbacks skipped
        self.assertIn("() if config_overrides is not None", text)                 # verbatim re-extract skipped


# --------------------------------------------------------------------------- #
# 3. The guard: mode, ledger, audit                                            #
# --------------------------------------------------------------------------- #

class ClassifyMessageTests(SimpleTestCase):
    def kind(self, text):
        return guard.classify_message(text)[0]

    def test_the_sentence_from_the_rust_lesson(self):
        self.assertEqual(self.kind(THE_RUST_USER_SENTENCE), "user_runs")
        self.assertEqual(self.kind("I will execute them, not you"), "user_runs")

    def test_other_ways_people_say_it(self):
        for text in ("I'll run it myself", "let me run the commands", "I want to type the commands", "I will press Enter",
                     "don't run anything", "do not execute those", "just show me the commands",
                     "you only show me the commands", "I run each command"):
            self.assertEqual(self.kind(text), "user_runs", text)

    def test_spanish(self):
        for text in ("yo los ejecuto", "yo las corro", "no los ejecutes", "mu\u00e9strame los comandos"):
            self.assertEqual(self.kind(text), "user_runs", text)

    def test_giving_the_keyboard_back(self):
        for text in ("you run them", "go ahead and run it", "you can execute the commands", "you take over",
                     "the tutorial is over", "run it yourself", "can you run it?", "hazlo t\u00fa",
                     "t\u00fa los ejecutas", "ejec\u00fatalo t\u00fa"):
            self.assertEqual(self.kind(text), "lift", text)

    def test_the_latest_instruction_in_a_message_wins(self):
        self.assertEqual(self.kind("you run them - no wait, I will run them"), "user_runs")
        self.assertEqual(self.kind("I will run them... actually, you run them"), "lift")

    def test_ordinary_requests_are_not_a_mode(self):
        for text in ("run the tests please", "install rust for me", "what does cargo do",
                     "the build will run into problems", ""):
            self.assertEqual(self.kind(text), "", text)

    def test_it_never_raises(self):
        for value in (None, 5, object(), "x" * 100000):
            self.assertIn(self.kind(value), ("", "user_runs", "lift"))


class TutorialModeTests(SimpleTestCase):
    def setUp(self):
        guard.reset()

    tearDown = setUp

    def test_the_mode_is_sticky_until_lifted(self):
        self.assertTrue(guard.observe("u1", THE_RUST_USER_SENTENCE).user_runs)
        self.assertTrue(guard.observe("u1", "next, show me how to create a project").user_runs)
        self.assertTrue(guard.observe("u1", "ok, done").user_runs)
        self.assertFalse(guard.observe("u1", "go ahead and run it").user_runs)
        self.assertFalse(guard.observe("u1", "now what").user_runs)

    def test_it_is_read_from_the_recent_history_too(self):
        history = [{"type": "human", "content": THE_RUST_USER_SENTENCE}, {"type": "ai", "content": "Sure."}]
        self.assertTrue(guard.observe("u2", "continue", history).user_runs)

    def test_users_do_not_share_a_mode(self):
        guard.observe("alice", THE_RUST_USER_SENTENCE)
        self.assertTrue(guard.get_mode("alice").user_runs)
        self.assertFalse(guard.observe("bob", "hello").user_runs)

    def test_a_forgotten_mode_expires(self):
        guard.observe("u3", THE_RUST_USER_SENTENCE)
        guard._MODES["3"] = guard._MODES.pop("u3")
        guard._MODES["u3"] = guard.TutorialMode(True, "I will execute them", time.time() - guard.MODE_TTL_SECONDS - 5)
        self.assertFalse(guard.observe("u3", "hello again").user_runs)

    def test_the_phrase_is_kept_so_the_refusal_can_quote_it(self):
        mode = guard.observe("u4", THE_RUST_USER_SENTENCE)
        self.assertTrue(mode.phrase)

    def test_the_contextvar_enter_and_leave(self):
        self.assertFalse(guard.user_runs_active())
        token = guard.enter_mode(True)
        self.assertTrue(guard.user_runs_active())
        guard.leave_mode(token)
        self.assertFalse(guard.user_runs_active())

    def test_the_switch(self):
        with mock.patch.object(guard, "enabled", return_value=False):
            mode = guard.TutorialMode(True, "x", time.time())
            self.assertEqual(guard.runner_block("execute_command", mode), "")
            self.assertEqual(guard.audit_answer("I typed it on your prompt.", [], mode, None, "terminal"), [])


class RunnerBlockTests(SimpleTestCase):
    MODE = guard.TutorialMode(True, "I will execute them", 1.0)

    def test_every_general_command_runner_is_refused_with_an_explanation(self):
        for name in sorted(guard.COMMAND_RUNNER_TOOLS):
            text = guard.runner_block(name, self.MODE)
            self.assertIn("LIVE-TUTORIAL MODE", text, name)
            self.assertIn("NOT run", text, name)
            self.assertIn("submit=false", text, name)
            self.assertIn("I will execute them", text, name)

    def test_terminater_itself_is_not_blocked_it_only_types(self):
        self.assertEqual(guard.runner_block("chat_agent_terminater", self.MODE), "")

    def test_other_tools_are_not_blocked(self):
        for name in ("chat_agent_pdfer", "chat_agent_file_creator", "get_current_time", "chat_agent_globber"):
            self.assertEqual(guard.runner_block(name, self.MODE), "", name)

    def test_without_the_mode_nothing_is_blocked(self):
        self.assertEqual(guard.runner_block("execute_command", None), "")
        self.assertEqual(guard.runner_block("execute_command", guard.TutorialMode()), "")

    def test_the_runner_list_is_what_the_executer_family_is(self):
        for name in ("execute_command", "execute_file", "chat_agent_executer", "chat_agent_pythonxer",
                     "chat_agent_ssher"):
            self.assertIn(name, guard.COMMAND_RUNNER_TOOLS)


def _evidence(status="typed", verified=True, enter=False, ok=True, typed="cargo --version", action="run", **extra):
    payload = {"tool": "chat_agent_terminater", "status": "completed", "agent_status": status,
               "terminal_id": "t1", "typed": typed, "enter_pressed": enter}
    if verified is not None:
        payload["verified"] = verified
    payload.update(extra)
    return guard.evidence_from("chat_agent_terminater", {"action": action, "terminal": "t1", "text": typed},
                               json.dumps(payload), ok)


class LedgerTests(SimpleTestCase):
    def test_a_verified_typed_line_is_proof(self):
        evidence = _evidence()
        self.assertTrue(evidence.typed_proof)
        self.assertEqual(evidence.status, "typed")
        self.assertFalse(evidence.ran)

    def test_the_agents_own_status_outranks_the_process_status(self):
        self.assertEqual(_evidence(status="typing_unverified", verified=False).status, "typing_unverified")

    def test_an_unverified_or_failed_line_is_not_proof(self):
        self.assertFalse(_evidence(status="typing_unverified", verified=False).typed_proof)
        self.assertFalse(_evidence(ok=False).typed_proof)
        self.assertFalse(_evidence(typed="").typed_proof)

    def test_a_missing_verified_flag_is_not_a_contradiction(self):
        self.assertTrue(_evidence(verified=None).typed_proof)

    def test_pressing_enter_means_it_ran(self):
        evidence = _evidence(status="completed", enter=True)
        self.assertTrue(evidence.ran)
        self.assertTrue(evidence.typed_proof)

    def test_a_failed_call_never_counts_as_ran(self):
        self.assertFalse(_evidence(status="completed", enter=True, ok=False).ran)

    def test_listing_is_not_running(self):
        self.assertFalse(_evidence(status="listed", action="list", typed="").ran)

    def test_a_command_runner_is_recorded_as_having_run(self):
        evidence = guard.evidence_from("execute_command", {"command": "ls"}, "done", True)
        self.assertTrue(evidence.ran)
        self.assertIsNone(guard.evidence_from("chat_agent_pdfer", {}, "{}", True))

    def test_garbage_results_never_raise(self):
        for result in (None, "", "not json", "[1, 2]", 5):
            guard.evidence_from("chat_agent_terminater", {"action": "run"}, result, True)

    def test_describe_call_says_what_will_happen(self):
        self.assertEqual(guard.describe_call({"action": "run", "terminal": "t2", "text": "cargo build"}),
                         "run [t2] cargo build")
        typed_only = guard.describe_call({"action": "run", "terminal": "t2", "text": "ls", "submit": False})
        self.assertIn("Enter NOT pressed", typed_only)
        self.assertEqual(guard.describe_call({"text": "dir"}), "run dir")
        self.assertEqual(guard.describe_call({"action": "list"}), "list")
        self.assertEqual(guard.describe_call({"request": "old style sentence"}), "old style sentence")
        self.assertIn("<base64 text>", guard.describe_call({"action": "run", "text_b64": "QQ=="}))

    def test_the_result_summary_is_the_tools_own_words(self):
        summary = guard.result_summary(json.dumps({"agent_status": "typed", "verified": True, "enter_pressed": False}))
        self.assertIn("typed", summary)
        self.assertIn("the screen shows it", summary)
        self.assertIn("Enter NOT pressed", summary)
        bad = guard.result_summary(json.dumps({"agent_status": "typing_unverified", "verified": False}))
        self.assertIn("NOT on the screen", bad)

    def test_the_exec_report_row_joins_both(self):
        row = guard.exec_report_command({"action": "run", "terminal": "t1", "text": "ls", "submit": False},
                                        json.dumps({"agent_status": "typed", "verified": True}))
        self.assertIn("  ->  ", row)
        self.assertIn("ls", row)


class ClaimAuditTests(SimpleTestCase):
    MODE = guard.TutorialMode(True, "I will execute them", 1.0)

    def audit(self, answer, ledger=(), mode=None, user_text="", bound=("chat_agent_terminater",)):
        return guard.audit_answer(answer, list(ledger), mode, bound, user_text)

    def codes(self, *args, **kw):
        return [problem.code for problem in self.audit(*args, **kw)]

    def test_typing_claims_with_no_call_are_flagged(self):
        for answer in ("I've typed `cargo --version` and it is now sitting on your prompt.",
                       "The line is typed and sitting on your prompt, ready for you to press Enter.",
                       "Done - cargo --version is typed and waiting on your terminal.",
                       "I put the command on your prompt for you.",
                       "It's now waiting on your terminal."):
            self.assertEqual(self.codes(answer, mode=self.MODE), ["claim_typed_no_call"], answer)

    def test_spanish_claims_are_flagged(self):
        self.assertEqual(self.codes("Ya escrib\u00ed el comando en la terminal.", mode=self.MODE),
                         ["claim_typed_no_call"])

    def test_a_proven_line_supports_the_claim(self):
        self.assertEqual(self.codes("I typed `cargo --version`, it is sitting on your prompt.",
                                    [_evidence()], self.MODE), [])

    def test_an_unverified_line_does_not(self):
        problems = self.audit("I typed it, it is on your prompt.", [_evidence(status="typing_unverified",
                                                                           verified=False)], self.MODE)
        self.assertEqual([p.code for p in problems], ["claim_typed_unverified"])
        self.assertIn("typing_unverified", problems[0].detail)

    def test_ran_claims_with_no_execution_are_flagged(self):
        for answer in ("I just ran the executable and it printed Hello.",
                       "I executed the program for you.",
                       "I pressed Enter."):
            self.assertEqual(self.codes(answer, mode=self.MODE), ["claim_ran_no_call"], answer)

    def test_a_ran_claim_is_supported_by_a_command_that_really_ran(self):
        ran = _evidence(status="completed", enter=True)
        self.assertEqual(self.codes("I ran the program and it printed Hello.", [ran], self.MODE), [])

    def test_questions_plans_and_conditions_are_not_claims(self):
        for answer in ("Do you want me to type it on your prompt?",
                       "Once I type it on your prompt, press Enter.",
                       "If I typed it in your terminal you would see it.",
                       "When I put it on the prompt, tell me.",
                       "Shall I run the executable?"):
            self.assertEqual(self.codes(answer, mode=self.MODE), [], answer)

    def test_code_blocks_are_not_prose(self):
        answer = "Here is the transcript:\n```\nI typed it on your prompt\nI ran the exe\n```\nTell me when it works."
        self.assertEqual(self.codes(answer, mode=self.MODE), [])

    def test_an_ordinary_coding_answer_is_never_audited(self):
        answer = "I put the line in the config file, and I ran the formatter over the module."
        self.assertEqual(self.codes(answer), [])
        self.assertEqual(self.codes(answer, user_text="please update my config"), [])

    def test_a_request_that_names_a_terminal_is_audited(self):
        answer = "I typed the command on your prompt."
        self.assertEqual(self.codes(answer, user_text="type cargo build in my terminal"), ["claim_typed_no_call"])

    def test_a_terminater_call_this_turn_makes_the_request_live(self):
        self.assertEqual(self.codes("I ran the program.", [_evidence(status="listed", action="list", typed="")]),
                         ["claim_ran_no_call"])

    def test_without_the_tool_bound_a_typing_claim_is_not_judged(self):
        self.assertEqual(self.codes("I typed it on your prompt.", mode=self.MODE, bound=("chat_agent_pdfer",)), [])

    def test_the_correction_names_each_claim_and_what_to_do(self):
        problems = self.audit("I typed it on your prompt.", mode=self.MODE)
        text = guard.nudge_text(problems)
        self.assertIn("never mention it to the user", text)
        self.assertIn("I typed it on your prompt", text)
        self.assertIn("submit=false when the user presses Enter themselves", text)
        self.assertIn("THIS turn", text.replace("this turn", "THIS turn"))

    def test_the_banner_is_visible_and_honest(self):
        banner = guard.banner_text(self.audit("I typed it on your prompt.", mode=self.MODE))
        self.assertIn("Please check before you act", banner)
        self.assertIn("I could not verify", banner)
        self.assertIn("I typed it on your prompt", banner)

    def test_the_audit_never_raises(self):
        for answer in (None, 5, "", "x" * 200000, object()):
            self.assertIsInstance(guard.audit_answer(answer, [], self.MODE, None, None), list)


# --------------------------------------------------------------------------- #
# 4. The executor wiring                                                       #
# --------------------------------------------------------------------------- #

class _ScriptedLLM:
    """Plays a fixed script of replies and remembers the messages of every model step."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, *args, **kwargs):
        self.seen.append([getattr(m, "content", "") for m in messages])
        step = self.script.pop(0) if self.script else {"content": "wrap up"}
        calls = [{"id": f"c{i}", "name": name, "args": args_} for i, (name, args_) in enumerate(step.get("calls", []))]
        return SimpleNamespace(content=step.get("content", ""), tool_calls=calls)


class ExecutorGuardTests(TestCase):
    def setUp(self):
        guard.reset()

    tearDown = setUp

    def executor(self, script, tools):
        from agent.mcp_agent import MultiTurnToolAgentExecutor

        llm = _ScriptedLLM(script)
        return MultiTurnToolAgentExecutor(llm=llm, system_prompt="test", tools=tools, max_iterations=12), llm

    @staticmethod
    def runner_tools():
        from langchain_core.tools import tool

        ran = []

        @tool
        def execute_command(command: str) -> str:
            """Run a shell command."""
            ran.append(command)
            return f"Command '{command}' executed successfully."

        return execute_command, ran

    @staticmethod
    def payload(text, user="exec-user", **extra):
        body = {"input": text, "exec_report_enabled": True, "ask_execs_user_id": user, "chat_history": []}
        body.update(extra)
        return body

    # -- the runner block ----------------------------------------------------
    def test_a_command_runner_is_refused_while_the_user_runs_the_commands(self):
        tool, ran = self.runner_tools()
        exe, llm = self.executor([{"calls": [("execute_command", {"command": "cargo --version"})]},
                                  {"content": "I could not run it myself, so please run it."}], [tool])
        result = exe.invoke(self.payload(THE_RUST_USER_SENTENCE + ". First check cargo."))
        self.assertEqual(ran, [], "the command runner ran although the user said they run the commands")
        reply = llm.seen[1][-1]
        self.assertIn("LIVE-TUTORIAL MODE", reply)
        self.assertIn("NOT run", reply)
        row = result["exec_report_entries"][0]
        self.assertFalse(row["success"])
        self.assertIn("NOT run - live-tutorial mode", row["command"])
        self.assertFalse(result["tool_calls_log"][0]["success"])

    def test_the_same_command_runs_normally_without_the_mode(self):
        tool, ran = self.runner_tools()
        exe, _ = self.executor([{"calls": [("execute_command", {"command": "cargo --version"})]},
                                {"content": "done"}], [tool])
        result = exe.invoke(self.payload("please check the cargo version"))
        self.assertEqual(ran, ["cargo --version"])
        self.assertTrue(result["exec_report_entries"][0]["success"])

    def test_the_block_does_not_poison_the_dedup_memory(self):
        tool, ran = self.runner_tools()
        exe, _ = self.executor([{"calls": [("execute_command", {"command": "dir"})]}, {"content": "ok"}], [tool])
        exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="poison"))
        self.assertEqual(ran, [])
        exe2, _ = self.executor([{"calls": [("execute_command", {"command": "dir"})]}, {"content": "ok"}], [tool])
        exe2.invoke(self.payload("you run them, go ahead and run it", user="poison"))
        self.assertEqual(ran, ["dir"])

    def test_the_mode_lifts_when_the_user_says_so(self):
        tool, ran = self.runner_tools()
        history = [{"type": "human", "content": THE_RUST_USER_SENTENCE}]
        exe, _ = self.executor([{"calls": [("execute_command", {"command": "dir"})]}, {"content": "ok"}], [tool])
        exe.invoke(self.payload("go ahead and run it yourself", user="lift", chat_history=history))
        self.assertEqual(ran, ["dir"])

    # -- the typed tool inside the loop -------------------------------------
    def test_terminater_is_forced_to_type_only_and_the_user_is_told(self):
        launch = _Launch({"status": "completed", "agent_status": "typed", "terminal_id": "t1",
                          "typed": "cargo --version", "verified": True, "enter_pressed": False})
        tool = door.build_tool(SPEC, launch, _wrap)
        exe, llm = self.executor([
            {"calls": [("chat_agent_terminater", {"action": "run", "terminal": "t1", "text": "cargo --version",
                                                  "submit": True})]},
            {"content": "I typed `cargo --version`; it is sitting on your prompt - press Enter."}], [tool])
        result = exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="forced"))
        self.assertIs(launch.calls[0]["cfg"]["submit"], False)
        self.assertIn("live_tutorial_mode", llm.seen[1][-1])
        row = result["exec_report_entries"][0]["command"]
        self.assertIn("cargo --version", row)
        self.assertIn("typed", row)
        self.assertIn("Enter NOT pressed", row)
        self.assertEqual(len(llm.seen), 2, "a claim backed by a verified typed line must not be challenged")
        self.assertNotIn("Please check before you act", result["output"])

    def test_repeated_identical_terminal_reads_are_not_swallowed_by_the_dedup(self):
        launch = _Launch({"status": "completed", "agent_status": "read", "output": "x"})
        tool = door.build_tool(SPEC, launch, _wrap)
        call = ("chat_agent_terminater", {"action": "read", "terminal": "t1", "which": "screen"})
        exe, _ = self.executor([{"calls": [call]}, {"calls": [call]}, {"content": "done"}], [tool])
        exe.invoke(self.payload("show me my terminal", user="dedup"))
        self.assertEqual(len(launch.calls), 2)

    # -- the claim audit -----------------------------------------------------
    def test_a_claim_with_no_call_gets_one_correction_and_an_honest_second_answer(self):
        launch = _Launch()
        tool = door.build_tool(SPEC, launch, _wrap)
        exe, llm = self.executor([
            {"content": "Done - `cargo --version` is typed and sitting on your prompt. Press Enter."},
            {"content": "I have not typed anything yet. Which terminal should I use?"}], [tool])
        result = exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="nudge"))
        self.assertEqual(len(llm.seen), 2)
        self.assertIn("[VERIFICATION", llm.seen[1][-1])
        self.assertIn("never mention it to the user", llm.seen[1][-1])
        self.assertEqual(launch.calls, [])
        self.assertNotIn("Please check before you act", result["output"])
        self.assertIn("I have not typed anything yet", result["output"])

    def test_a_claim_that_survives_the_correction_is_flagged_on_the_answer(self):
        tool = door.build_tool(SPEC, _Launch(), _wrap)
        exe, llm = self.executor([
            {"content": "The line is typed and sitting on your prompt."},
            {"content": "Really, the line is typed and sitting on your prompt."}], [tool])
        result = exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="stubborn"))
        self.assertEqual(len(llm.seen), 2)
        self.assertIn("Please check before you act", result["output"])
        self.assertIn("I could not verify", result["output"])

    def test_the_correction_is_given_only_once(self):
        tool = door.build_tool(SPEC, _Launch(), _wrap)
        exe, llm = self.executor([{"content": "It is typed and sitting on your prompt."},
                                  {"content": "It is typed and sitting on your prompt."},
                                  {"content": "It is typed and sitting on your prompt."}], [tool])
        exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="once"))
        self.assertEqual(len(llm.seen), 2)

    def test_a_line_that_was_not_verified_is_not_called_typed(self):
        launch = _Launch({"status": "completed", "agent_status": "typing_unverified", "typed": "cargo",
                          "verified": False, "enter_pressed": False})
        tool = door.build_tool(SPEC, launch, _wrap)
        exe, llm = self.executor([
            {"calls": [("chat_agent_terminater", {"action": "run", "terminal": "t1", "text": "cargo"})]},
            {"content": "I typed it and it is on your prompt."},
            {"content": "The screen does not show the line, so I cannot say it is typed."}], [tool])
        result = exe.invoke(self.payload(THE_RUST_USER_SENTENCE, user="unverified"))
        self.assertEqual(len(llm.seen), 3)
        self.assertIn("claim_typed_unverified".replace("claim_typed_unverified", "typing_unverified"),
                      llm.seen[2][-1])
        self.assertNotIn("Please check before you act", result["output"])

    def test_an_ordinary_answer_is_untouched(self):
        exe, llm = self.executor([{"content": "I put the line in the config file."}],
                                 [self.runner_tools()[0]])
        result = exe.invoke(self.payload("update my config", user="plain"))
        self.assertEqual(len(llm.seen), 1)
        self.assertEqual(result["output"], "I put the line in the config file.")

    def test_a_broken_guard_never_breaks_the_chat(self):
        exe, llm = self.executor([{"content": "I typed it on your prompt."}], [self.runner_tools()[0]])
        with mock.patch.object(guard, "audit_answer", side_effect=RuntimeError("boom")):
            result = exe.invoke(self.payload("type it in my terminal", user="boom"))
        self.assertEqual(result["output"], "I typed it on your prompt.")
        self.assertEqual(len(llm.seen), 1)

    def test_the_shell_label_reads_the_typed_kind(self):
        from agent.mcp_agent import _infer_execution_shell

        self.assertIn("cmd.exe", _infer_execution_shell("chat_agent_terminater", {"kind": "cmd"}))
        self.assertIn("PowerShell 7", _infer_execution_shell("chat_agent_terminater", {"kind": "pwsh"}))
        self.assertIn("Windows PowerShell", _infer_execution_shell("chat_agent_terminater", {"action": "run"}))
        self.assertIn("cmd.exe", _infer_execution_shell("chat_agent_terminater", {"request": "kind='cmd'"}))

    def test_the_permission_dialog_shows_the_typed_line(self):
        from agent.mcp_agent import MultiTurnToolAgentExecutor

        text = MultiTurnToolAgentExecutor._extract_exec_report_command(
            {"action": "run", "terminal": "t1", "text": "cargo build", "submit": False}, "chat_agent_terminater")
        self.assertIn("cargo build", text)
        self.assertIn("Enter NOT pressed", text)


# --------------------------------------------------------------------------- #
# 5. Contracts that must stay in step                                          #
# --------------------------------------------------------------------------- #

class ContractTests(SimpleTestCase):
    def test_the_new_status_is_degraded_and_known(self):
        self.assertIn("typing_unverified", agent_verdict.WORK_DEGRADED_STATUSES)
        self.assertIn("typing_unverified", agent_verdict.KNOWN_STATUSES)
        for status in ("typed", "completed", "opened"):
            self.assertIn(status, agent_verdict.WORK_COMPLETED_STATUSES)

    def test_typing_unverified_is_a_red_row(self):
        verdict = agent_verdict.classify_payload({"status": "completed", "agent_status": "typing_unverified"})
        self.assertFalse(verdict.ok)

    def test_the_agent_declares_the_fields_the_contract_and_the_wrapper_promote(self):
        source = _read("agents/terminater/terminater.py")
        tree = ast.parse(source)
        declared = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SECTION_FIELDS" for t in node.targets):
                declared = tuple(ast.literal_eval(node.value))
        self.assertIsNotNone(declared)
        for name in ("verified", "screen_line", "enter_pressed", "notes"):
            self.assertIn(name, declared)
            self.assertIn(name, agent_contracts._PARAMETRIZER_OUTPUT_FIELDS["terminater"])
        from . import tools

        promoted = tools._PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR["terminater"]
        for name in ("verified", "screen_line", "enter_pressed", "notes", "typed", "terminal_id", "status"):
            self.assertIn(name, promoted)

    def test_the_agent_forwards_the_new_settings(self):
        source = _read("agents/terminater/terminater.py")
        tree = ast.parse(source)
        keys = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PARAM_KEYS" for t in node.targets):
                keys = list(ast.literal_eval(node.value))
        for name in ("create_if_missing", "clear_line", "check_line"):
            self.assertIn(name, keys)

    def test_the_model_is_taught_the_protocol_in_the_tool_description(self):
        purpose = SPEC.purpose
        for phrase in ("ONE ARGUMENT PER SETTING", "terminal_id", "submit=false", "typing_unverified",
                       "prompt_not_empty", "already_present", "no_terminal", "bad_terminal_ref", "LIVE TUTORIAL",
                       "ONLY when THIS call's result shows it", "verified", "screen_line", "enter_pressed",
                       "clear_line=true"):
            self.assertIn(phrase, purpose, phrase)
        self.assertNotIn("PARAMETERS:", purpose)

    def test_the_example_is_typed_not_a_sentence(self):
        self.assertIn("action='open'", SPEC.example_request)
        self.assertIn("submit=false", SPEC.example_request)

    def test_the_system_prompt_carries_the_live_tutorial_rule(self):
        prompt = _read("prompt.pmt")
        self.assertIn("18f) Live-tutorial and visible-terminal rule", prompt)
        for phrase in ("LIVE-TUTORIAL MODE", "submit=false", "terminal_id", "typing_unverified", "IN THIS TURN",
                       "Executer, Pythonxer"):
            self.assertTrue(phrase in prompt, phrase)
        order = [m.group(1) for m in re.finditer(r"^(\d+[a-z]?)\) ", prompt, re.MULTILINE)]
        self.assertLess(order.index("18e"), order.index("18f"))
        self.assertLess(order.index("18f"), order.index("19"))
        self.assertEqual(order[-1], "22", "Conflict resolution must stay the LAST rule")

    def test_create_flow_leaves_a_session_terminal_id_out_and_keeps_the_new_flags(self):
        js = _read("static/agent/js/agent_page_chat.js")
        start = js.index("lower === 'terminater'")
        block = js[start:start + 1800]
        for name in ("create_if_missing", "clear_line", "check_line"):
            self.assertIn(name, block)
        self.assertIn(r"/^t\d+$/i", block)

    def test_the_collected_static_copy_matches_the_source(self):
        collected = AGENT_DIR.parent / "staticfiles" / "agent" / "js" / "agent_page_chat.js"
        if not collected.is_file():
            self.skipTest("staticfiles/ is not collected on this checkout")
        self.assertEqual(collected.read_bytes(), (AGENT_DIR / "static/agent/js/agent_page_chat.js").read_bytes())

    def test_the_guard_modules_are_named_for_the_frozen_build(self):
        build = (AGENT_DIR.parent.parent / "build.py").read_text(encoding="utf-8", errors="replace")
        for module in ("agent.terminal_guard", "agent.terminater_tool"):
            self.assertTrue(module in build, f"build.py must name {module}: a fail-open import cannot report its absence")

    def test_the_release_gate_proves_the_typed_door_loads(self):
        gate = _read("management/commands/check_terminater.py")
        for phrase in ("def check_typed_door", "terminater_tool", "terminal_guard", "bad_terminal_ref",
                       "'typed_door'", "LIVE-TUTORIAL MODE"):
            self.assertTrue(phrase in gate, phrase)


# --------------------------------------------------------------------------- #
# 6. The engine, in REAL shells                                                #
# --------------------------------------------------------------------------- #

@unittest.skipUnless(kit.conpty_ok(), "ConPTY is not available on this machine")
class RealShellReadBackTests(SimpleTestCase):
    """What the model is told about the terminal is what the SCREEN shows."""

    KINDS = ("powershell", "cmd")
    hub = None
    fast = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fast = kit.FastTyping(0.04)
        cls.fast.__enter__()
        cls.hub = kit.fresh_hub(max_terminals=10, hang_seconds=6.0)
        cls.ids = {}
        for kind in cls.KINDS:
            opened = cls.hub.call("open", {"user": U, "kind": kind, "title": f"reliability {kind}",
                                           "load_profile": False})
            cls.ids[kind] = opened.get("terminal_id", "")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.hub.shutdown()
        finally:
            cls.fast.__exit__(None, None, None)
            super().tearDownClass()

    def setUp(self):
        for kind in self.KINDS:
            self._recover(kind)
        time.sleep(0.25)        # let PSReadLine start reading: this suite types ~25x faster than a person

    # -- helpers ------------------------------------------------------------
    def session(self, kind):
        return self.hub.space(U).sessions[self.ids[kind]]

    def _recover(self, kind):
        session = self.hub.space(U).sessions.get(self.ids[kind])
        if session is None or session.state in (ENG.ST_EXITED, ENG.ST_CLOSED):
            opened = self.hub.call("open", {"user": U, "kind": kind, "title": f"reliability {kind}",
                                            "load_profile": False})
            self.ids[kind] = opened.get("terminal_id", "")
            return
        if session.state != ENG.ST_PROMPT:
            session.abort()
            session.send_keys("ctrl+c")
            session.wait(timeout=6)
        if session.state == ENG.ST_PROMPT and session.input_line().strip():
            session.clear_input_line()

    def run_line(self, kind, text, **extra):
        params = {"user": U, "terminal": self.ids[kind], "text": text, "wait_seconds": 40}
        params.update(extra)
        return self.hub.call("run", params)

    def terminal_count(self):
        return len(self.hub.space(U).sessions)

    def each_shell(self):
        for kind in self.KINDS:
            with self.subTest(shell=kind):
                yield kind

    # -- typed means: the screen shows it ----------------------------------------
    def test_a_line_typed_without_enter_is_read_back_from_the_screen(self):
        for kind in self.each_shell():
            res = self.run_line(kind, "echo hello world", submit=False)
            self.assertEqual(res["status"], "typed", res)
            self.assertIs(res["verified"], True, res)
            self.assertIs(res["enter_pressed"], False, res)
            self.assertEqual(TX.norm_line(res["screen_line"]), "echo hello world")
            self.assertEqual(self.session(kind).input_line(), "echo hello world")

    def test_the_same_line_is_not_typed_twice(self):
        for kind in self.each_shell():
            self.run_line(kind, "echo only once", submit=False)
            again = self.run_line(kind, "echo only once", submit=False)
            self.assertIs(again["already_present"], True, again)
            self.assertEqual(self.session(kind).input_line(), "echo only once")

    def test_a_different_line_is_refused_instead_of_being_glued_on(self):
        for kind in self.each_shell():
            self.run_line(kind, "echo first", submit=False)
            res = self.run_line(kind, "echo second", submit=False)
            self.assertEqual(res["status"], "refused", res)
            self.assertEqual(res["code"], "prompt_not_empty", res)
            self.assertEqual(self.session(kind).input_line(), "echo first", "the waiting line must be untouched")

    def test_clear_line_replaces_the_waiting_line(self):
        for kind in self.each_shell():
            self.run_line(kind, "echo first", submit=False)
            res = self.run_line(kind, "echo replaced", submit=False, clear_line=True)
            self.assertEqual(res["status"], "typed", res)
            self.assertIn("cleared first", res["notes"])
            self.assertEqual(self.session(kind).input_line(), "echo replaced")

    def test_enter_on_the_waiting_line_runs_it_without_retyping(self):
        for kind in self.each_shell():
            self.run_line(kind, "echo ran-after-review", submit=False)
            res = self.run_line(kind, "echo ran-after-review", submit=True)
            self.assertEqual(res["status"], "completed", res)
            self.assertIs(res["enter_pressed"], True, res)
            self.assertIs(res["already_present"], True, res)
            self.assertIn("ran-after-review", res["output"])

    def test_a_sentence_for_submit_never_presses_enter(self):
        sentence = "false - type the line but do NOT press Enter, leave it sitting on the prompt"
        for kind in self.each_shell():
            res = self.run_line(kind, "echo careful", submit=sentence)
            self.assertEqual(res["status"], "typed", res)
            self.assertIs(res["enter_pressed"], False, res)
            self.assertIn("not a clear yes/no", res["notes"])
            self.assertEqual(self.session(kind).input_line(), "echo careful")

    def test_a_submitted_command_is_checked_against_the_shells_echo(self):
        for kind in self.each_shell():
            res = self.run_line(kind, "echo checked-echo")
            self.assertEqual(res["status"], "completed", res)
            self.assertIs(res["verified"], True, res)
            self.assertEqual(TX.norm_line(res["screen_line"]), "echo checked-echo")

    def test_the_echo_is_exact_even_after_a_long_wrapped_line_was_cleared(self):
        long_text = "echo " + ("0123456789" * 16)
        for kind in self.each_shell():
            first = self.run_line(kind, long_text, submit=False)
            self.assertIs(first["verified"], True, first)
            self.assertEqual(TX.norm_line(first["screen_line"]), TX.norm_line(long_text))
            self.run_line(kind, "echo short-after-long", submit=False, clear_line=True)
            done = self.run_line(kind, "echo short-after-long", submit=True)
            self.assertEqual(done["status"], "completed", done)
            self.assertEqual(TX.norm_line(done["screen_line"]), "echo short-after-long",
                             "the output of the command must not be glued onto its echo")

    def test_quotes_backslashes_and_accents_survive_the_read_back(self):
        text = "echo 'a b' C:\\x\\y " + chr(0xF1)
        for kind in self.each_shell():
            res = self.run_line(kind, text, submit=False)
            self.assertIs(res["verified"], True, res)
            self.assertEqual(TX.norm_line(res["screen_line"]), TX.norm_line(text))

    # -- terminals are addressed by id or exact name, never by a guess ------------
    def test_the_garbage_reference_from_the_rust_lesson_opens_nothing(self):
        for kind in self.each_shell():
            before = self.terminal_count()
            res = self.hub.call("run", {"user": U, "terminal": THE_GARBAGE_TERMINAL_REF, "text": "echo x"})
            self.assertEqual(res["code"], "bad_terminal_ref", res)
            self.assertEqual(self.terminal_count(), before, "a NEW terminal was raised for a garbage reference")

    def test_an_id_that_does_not_exist_is_refused(self):
        before = self.terminal_count()
        res = self.hub.call("run", {"user": U, "terminal": "t99", "text": "echo x"})
        self.assertEqual(res["code"], "no_terminal", res)
        self.assertEqual(self.terminal_count(), before)

    def test_a_name_that_does_not_exist_is_refused_when_creation_is_off(self):
        before = self.terminal_count()
        res = self.hub.call("run", {"user": U, "terminal": "nowhere", "text": "echo x", "create_if_missing": False})
        self.assertEqual(res["code"], "no_terminal", res)
        self.assertEqual(self.terminal_count(), before)

    def test_a_name_that_does_not_exist_is_created_by_default_for_flows(self):
        before = self.terminal_count()
        res = self.hub.call("run", {"user": U, "terminal": "made on purpose", "kind": "cmd", "text": "echo created",
                                    "wait_seconds": 30})
        try:
            self.assertEqual(res["status"], "completed", res)
            self.assertEqual(self.terminal_count(), before + 1)
        finally:
            if res.get("terminal_id"):
                self.hub.call("kill", {"user": U, "terminal": res["terminal_id"]})

    # -- the read-back never leaks and can be switched off ---------------------
    def test_a_secret_is_never_read_back_or_returned(self):
        for kind in self.each_shell():
            res = self.run_line(kind, "echo top-secret-token", submit=False, secret=True)
            self.assertNotIn("top-secret-token", json.dumps(res), res)
            self.assertNotIn("verified", res)
            self.session(kind).clear_input_line()

    def test_check_line_off_skips_the_read_back(self):
        for kind in self.each_shell():
            res = self.run_line(kind, "echo unchecked", submit=False, check_line=False)
            self.assertEqual(res["status"], "typed", res)
            self.assertNotIn("verified", res)

    # -- the typed door, wired straight to the real engine -----------------------
    def _door_to_engine(self):
        hub = self.hub

        def launch(spec, request, *, auto_diagnose=True, config_overrides=None):
            cfg = dict(config_overrides)
            action = cfg.pop("action")
            cfg["user"] = U
            result = hub.call(action, cfg)
            result["agent_status"] = result.get("status")
            return _wrap(result)

        return door.build_tool(SPEC, launch, _wrap)

    def test_the_typed_tool_cannot_open_a_terminal_by_accident(self):
        tool = self._door_to_engine()
        before = self.terminal_count()
        out = json.loads(tool.invoke({"action": "run", "terminal": "Rust Lesson", "text": "echo hi"}))
        self.assertEqual(out["code"], "no_terminal", out)
        self.assertEqual(self.terminal_count(), before)

    def test_the_typed_tool_leaves_the_line_for_the_user_in_live_tutorial_mode(self):
        tool = self._door_to_engine()
        kind = "powershell"
        token = guard.enter_mode(True)
        try:
            out = json.loads(tool.invoke({"action": "run", "terminal": self.ids[kind], "text": "echo for-the-user",
                                          "submit": True, "wait_seconds": 20}))
        finally:
            guard.leave_mode(token)
        self.assertEqual(out["status"], "typed", out)
        self.assertIs(out["enter_pressed"], False, out)
        self.assertIs(out["live_tutorial_mode"], True)
        self.assertEqual(self.session(kind).input_line(), "echo for-the-user")
        self.session(kind).clear_input_line()


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
