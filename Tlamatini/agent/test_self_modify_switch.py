"""The SELF-MODIFY switch (Angela, 2026-10-03).

Pins Angela's design, piece by piece:

* the Self-modify box exists ONLY in a build that can self-modify - ALWAYS in
  dev mode (a source run of this checkout, folder or no folder), and in a
  FROZEN build only when ``build.py --self-modify`` bundled
  TlamatiniSourceCode/ - and is COMPLETELY absent from the page otherwise;
* OFF: the identity bullets give way to one honest line and the whole
  <self_knowledge> section (Tlamatini.md, ~28K tokens) is NOT sent; ON: the
  prompt is byte-for-byte what it always was;
* it can be ticked if and only if the model can hold the self-knowledge on
  top of the request - otherwise it is locked OFF, and the server refuses a
  forged tick;
* the choice is persisted (CompactState.self_modify, ON by default) and the
  verdict reaches the page on every gauge frame.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from agent import compact_mode as cm
from agent import context_fitter as cf
from agent import context_governor as cg
from agent.models import CompactState
from agent.rag import config as rc

AGENT_DIR = Path(__file__).resolve().parent
REPO = AGENT_DIR.parents[1]
_SELF_TEXT = "I am Tlamatini and this is my private self-knowledge sentinel."
_FAKE_PROMPT = """Rules that always apply.
- Identity bullet that always stays.
<!--SELF_KNOWLEDGE_BEGIN-->
- Your self-knowledge lives in Tlamatini.md, and your source may be bundled in
  TlamatiniSourceCode/.
<!--SELF_KNOWLEDGE_END-->
<!--NOT_SELF_MODIFY_BEGIN-->
- This build is a not-self-able-modify build.
<!--NOT_SELF_MODIFY_END-->

<!--SELF_KNOWLEDGE_BEGIN-->
<self_knowledge>
The block below is your own self-knowledge.
{self_knowledge}
</self_knowledge>
<!--SELF_KNOWLEDGE_END-->

<context>
{context}
</context>
"""


def _app_dir(with_tree=True, prompt=_FAKE_PROMPT, self_text=_SELF_TEXT):
    app = tempfile.mkdtemp(prefix="selfmodswitch_")
    with open(os.path.join(app, "config.json"), "w", encoding="utf-8") as fh:
        fh.write('{"x": 1}')
    with open(os.path.join(app, "prompt.pmt"), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    with open(os.path.join(app, "Tlamatini.md"), "w", encoding="utf-8") as fh:
        fh.write(self_text)
    if with_tree:
        os.makedirs(os.path.join(app, rc.SELF_MODIFY_DIRNAME))
    return app


class _Dirs(SimpleTestCase):
    def setUp(self):
        self._dirs = []
        cm.reset_cache()

    def tearDown(self):
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)
        cm.reset_cache()

    def app(self, **kw):
        d = _app_dir(**kw)
        self._dirs.append(d)
        return d


# ── Who can self-modify: DEV always, FROZEN only with --self-modify ───────────
class AvailabilityTests(_Dirs):
    def test_dev_mode_is_always_like_self_modify_folder_or_no_folder(self):
        with patch.object(rc, "is_self_able_modify", return_value=False):
            self.assertTrue(rc.self_modify_available(str(AGENT_DIR)))
            self.assertTrue(rc.self_modify_available())

    def test_a_frozen_build_without_the_source_tree_cannot(self):
        exe_dir = self.app(with_tree=False)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", os.path.join(exe_dir, "Tlamatini.exe")):
            self.assertEqual(rc.default_application_path(), exe_dir)
            self.assertFalse(rc.self_modify_available())

    def test_a_frozen_self_modify_build_can(self):
        exe_dir = self.app(with_tree=True)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", os.path.join(exe_dir, "Tlamatini.exe")):
            self.assertTrue(rc.self_modify_available())

    def test_frozen_never_inherits_the_dev_rule(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(rc, "is_self_able_modify", return_value=False):
            self.assertFalse(rc.is_source_checkout(str(AGENT_DIR)))
            self.assertFalse(rc.self_modify_available(str(AGENT_DIR)))

    def test_any_other_directory_is_gated_like_an_install(self):
        self.assertFalse(rc.self_modify_available(self.app(with_tree=False)))
        self.assertTrue(rc.self_modify_available(self.app(with_tree=True)))

    def test_the_dev_checkout_loads_her_self_knowledge(self):
        _, prompt, _ = rc.load_config_and_prompt(str(AGENT_DIR))
        self.assertIn("<self_knowledge>", prompt)
        self.assertIn("</self_knowledge>", prompt)
        self.assertNotIn("not-self-able-modify build", prompt)


# ── The prompt: OFF drops it, ON is byte-for-byte unchanged ───────────────────
class PromptSwitchTests(_Dirs):
    def test_off_swaps_the_bullets_for_one_line_and_drops_the_section(self):
        app = self.app()
        _, prompt, _ = rc.load_config_and_prompt(app)
        self.assertIn(_SELF_TEXT, prompt)
        off = rc.apply_self_modify_switch(prompt, False, app)
        self.assertNotIn("<self_knowledge>", off)
        self.assertNotIn(_SELF_TEXT, off)
        self.assertNotIn("Your self-knowledge lives in Tlamatini.md", off)
        self.assertEqual(off.count(rc.SELF_MODIFY_OFF_NOTICE), 1)
        self.assertIn("Rules that always apply.", off)
        self.assertIn("- Identity bullet that always stays.", off)
        self.assertIn("{context}", off)
        self.assertNotIn("<!--", off)

    def test_on_is_byte_for_byte_unchanged(self):
        app = self.app()
        _, prompt, _ = rc.load_config_and_prompt(app)
        self.assertEqual(rc.apply_self_modify_switch(prompt, True, app), prompt)

    def test_a_build_that_cannot_self_modify_is_untouched(self):
        app = self.app(with_tree=False)
        _, prompt, _ = rc.load_config_and_prompt(app)
        self.assertEqual(rc.apply_self_modify_switch(prompt, False, app), prompt)
        self.assertEqual(rc.self_knowledge_segments(app), ())

    def test_a_reshaped_prompt_still_never_sends_the_section(self):
        app = self.app()
        _, prompt, _ = rc.load_config_and_prompt(app)
        reshaped = prompt.replace("The block below is your own self-knowledge.", "Reshaped.")
        off = rc.apply_self_modify_switch(reshaped, False, app)
        self.assertNotIn(_SELF_TEXT, off)
        self.assertNotIn("</self_knowledge>", off)

    def test_the_notice_is_template_safe(self):
        self.assertNotIn("{", rc.SELF_MODIFY_OFF_NOTICE)
        self.assertNotIn("}", rc.SELF_MODIFY_OFF_NOTICE)
        self.assertIn("Self-modify", rc.SELF_MODIFY_OFF_NOTICE)

    def test_the_real_prompt_saves_the_whole_self_knowledge(self):
        _, prompt, _ = rc.load_config_and_prompt(str(AGENT_DIR))
        off = rc.apply_self_modify_switch(prompt, False, str(AGENT_DIR))
        saved = len(prompt) - len(off)
        self.assertGreater(saved, 100_000)          # Tlamatini.md is ~112K characters
        self.assertNotIn("</self_knowledge>", off)
        self.assertIn(rc.SELF_MODIFY_OFF_NOTICE, off)
        print(f"\n    [self-modify switch] real prompt {len(prompt):,} -> {len(off):,} chars "
              f"(saved {saved:,}, ~{saved // 4:,} tokens per request)")

    def test_build_system_prompt_obeys_the_switch(self):
        from agent.mcp_agent import _build_system_prompt
        _, prompt, _ = rc.load_config_and_prompt(str(AGENT_DIR))
        on = _build_system_prompt(prompt, [], self_knowledge=True)
        off = _build_system_prompt(prompt, [], self_knowledge=False)
        self.assertGreater(len(on) - len(off), 100_000)
        self.assertIn("Self-modify is switched OFF", off)
        with patch.object(rc, "self_modify_on", return_value=False):
            self.assertEqual(_build_system_prompt(prompt, []), off)
        with patch.object(rc, "self_modify_on", return_value=True):
            self.assertEqual(_build_system_prompt(prompt, []), on)

    def test_the_tool_less_path_obeys_the_switch(self):
        from agent.rag.chains import unified
        _, prompt, _ = rc.load_config_and_prompt(str(AGENT_DIR))
        with patch.object(unified, "self_modify_on", return_value=False):
            self.assertNotIn("</self_knowledge>", unified._non_tool_system_prompt(prompt))
        with patch.object(unified, "self_modify_on", return_value=True):
            self.assertIn("</self_knowledge>", unified._non_tool_system_prompt(prompt))


# ── The switch: persisted, refused when it does not fit ───────────────────────
class SwitchStateTests(TestCase):
    def setUp(self):
        cm.reset_cache()
        CompactState.objects.all().delete()
        self._notify = patch.object(cm, "notify", return_value=True)
        self._notify.start()

    def tearDown(self):
        self._notify.stop()
        cm.reset_cache()

    def test_it_is_on_by_default(self):
        snap = cm.state()
        self.assertTrue(snap["self_modify"])
        self.assertTrue(snap["self_modify_available"])          # dev mode
        self.assertTrue(snap["self_modify_active"])
        self.assertFalse(snap["self_modify_locked"])

    def test_off_and_on_are_persisted(self):
        result = cm.set_self_modify(False, "test")
        self.assertTrue(result["ok"] and result["changed"])
        self.assertFalse(CompactState.objects.get(pk=1).self_modify)
        cm.reset_cache()
        self.assertFalse(cm.self_modify_wanted())
        self.assertFalse(cm.self_modify_active())
        self.assertTrue(cm.set_self_modify(True, "test")["changed"])
        self.assertTrue(CompactState.objects.get(pk=1).self_modify)

    def test_a_tick_is_refused_while_the_model_cannot_hold_it(self):
        cm.set_self_modify(False, "test")
        cm.note_capacity(model="qwen2.5:latest", strict=True, window_tokens=16386, auto_enter=False)
        cm.note_self_modify(fits=False, tokens=28_000, need_tokens=36_000)
        snap = cm.state()
        self.assertTrue(snap["self_modify_locked"])
        self.assertFalse(snap["self_modify_active"])
        result = cm.set_self_modify(True, "forged")
        self.assertFalse(result["ok"])
        self.assertEqual(result["refused"], "too_small")
        self.assertIn("16,386", result["message"])
        self.assertFalse(CompactState.objects.get(pk=1).self_modify)

    def test_a_locked_model_keeps_her_choice_and_a_big_one_unlocks_it(self):
        cm.note_self_modify(fits=False, tokens=28_000, need_tokens=36_000)
        self.assertTrue(cm.self_modify_wanted())        # her choice is NOT rewritten
        self.assertFalse(cm.self_modify_active())       # ...but nothing is sent
        cm.note_self_modify(fits=True, tokens=28_000, need_tokens=130_000)
        self.assertTrue(cm.self_modify_active())

    def test_a_build_that_cannot_self_modify_refuses_and_says_so(self):
        with patch.object(cm, "self_modify_available", return_value=False):
            result = cm.set_self_modify(True, "test")
            self.assertEqual(result["refused"], "unavailable")
            self.assertFalse(cm.state()["self_modify_available"])
            self.assertFalse(cm.self_modify_active())
            self.assertFalse(cm.note_self_modify(fits=True))


# ── The fitter: sent only when it fits ────────────────────────────────────────
class _FakeLLM:
    model = "qwen2.5:latest"
    base_url = "http://127.0.0.1:11434"

    def bind_tools(self, tools):
        return self


def _tool(name, description="A tool."):
    return SimpleNamespace(name=name, description=description, args={})


class FitTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _, cls.PROMPT, _ = rc.load_config_and_prompt(str(AGENT_DIR))

    def setUp(self):
        cm.reset_cache()
        cg.forget_learned_windows()

    def tearDown(self):
        cm.reset_cache()
        cg.forget_learned_windows()

    def _fit(self, *, ceiling, wanted=True, compact=False):
        from agent.mcp_agent import CapabilityAwareToolAgentExecutor
        cae = CapabilityAwareToolAgentExecutor(llm=_FakeLLM(), preeliminary_prompt=self.PROMPT,
                                               tools=[_tool("get_current_time")], max_iterations=2)
        cae._everything_chars = 120_000              # everything activated ~40K tokens
        cfg = {"context_ceiling_tokens": ceiling}
        noted = []
        with patch("agent.mcp_agent._load_config", return_value=cfg), \
             patch.object(cm, "is_active", return_value=compact), \
             patch.object(cm, "enter_compact", return_value={"ok": False}), \
             patch.object(cm, "note_capacity", return_value=False), \
             patch.object(cm, "self_modify_available", return_value=True), \
             patch.object(cm, "self_modify_wanted", return_value=wanted), \
             patch.object(cm, "note_self_modify", side_effect=lambda **kw: noted.append(kw)), \
             patch.object(type(cae), "_refresh_toggle_tool_surface", return_value=False):
            fit = cae.fit_request(input_text="Who made you?", chat_history=[],
                                  request_tools=list(cae.tools), user_id="u-selfmod")
        return fit, noted

    def test_a_big_model_gets_her_self_knowledge(self):
        fit, noted = self._fit(ceiling=1_000_000)
        self.assertEqual(fit["mode"], cf.MODE_FULL)
        self.assertIn("</self_knowledge>", fit["executor"].system_prompt)
        cap = fit["report"].as_capacity()["self_modify"]
        self.assertTrue(cap["active"] and cap["fits"] and not cap["locked"])
        self.assertGreater(cap["tokens"], 20_000)
        self.assertTrue(noted and noted[-1]["fits"])

    def test_switched_off_she_is_not_sent_even_on_a_big_model(self):
        fit, _ = self._fit(ceiling=1_000_000, wanted=False)
        self.assertNotIn("</self_knowledge>", fit["executor"].system_prompt)
        self.assertIn("Self-modify is switched OFF", fit["executor"].system_prompt)
        cap = fit["report"].as_capacity()["self_modify"]
        self.assertFalse(cap["active"])
        self.assertFalse(cap["locked"])

    def test_a_model_that_holds_everything_but_her_is_locked_off(self):
        # 50K tokens (~125K chars at the pessimistic 3.0): everything activated
        # (120K chars) fits, the self-knowledge (~112K chars) on top does not.
        fit, noted = self._fit(ceiling=50_000)
        self.assertEqual(fit["mode"], cf.MODE_FULL)
        self.assertNotIn("</self_knowledge>", fit["executor"].system_prompt)
        cap = fit["report"].as_capacity()["self_modify"]
        self.assertTrue(cap["locked"])
        self.assertFalse(cap["active"])
        self.assertFalse(noted[-1]["fits"])

    def test_a_small_model_in_compact_mode_is_locked_off(self):
        fit, _ = self._fit(ceiling=16386)
        self.assertEqual(fit["mode"], cf.MODE_COMPACT)
        self.assertNotIn("Tlamatini.md", fit["executor"].system_prompt)
        self.assertTrue(fit["report"].as_capacity()["self_modify"]["locked"])

    def test_a_big_model_in_compact_mode_carries_her_when_she_fits(self):
        fit, _ = self._fit(ceiling=1_000_000, compact=True)
        self.assertEqual(fit["mode"], cf.MODE_COMPACT)
        self.assertIn("</self_knowledge>", fit["executor"].system_prompt)
        self.assertTrue(fit["report"].as_capacity()["self_modify"]["active"])

    def test_strict_is_measured_without_her(self):
        from agent.mcp_agent import CapabilityAwareToolAgentExecutor
        cae = CapabilityAwareToolAgentExecutor(llm=_FakeLLM(), preeliminary_prompt=self.PROMPT,
                                               tools=[_tool("get_current_time")], max_iterations=2)
        with patch("agent.mcp_agent.get_mcp_tools", return_value=[_tool("get_current_time")]):
            everything = cae._everything_static_chars()
        self.assertLess(everything, len(self.PROMPT) - 100_000)
        self.assertGreater(cae._self_knowledge_chars(), 100_000)


# ── The page: the box exists ONLY when the build can self-modify ──────────────
class PageTests(TestCase):
    def setUp(self):
        cm.reset_cache()
        user = get_user_model().objects.create_user("selfmod_page", password="x-test-only")
        self.client.force_login(user)

    def tearDown(self):
        cm.reset_cache()

    def _page(self, available):
        with patch("agent.rag.config.self_modify_available", return_value=available):
            response = self.client.get("/agent/agent/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def test_the_box_is_on_the_page_when_the_build_can_self_modify(self):
        html = self._page(True)
        self.assertIn('id="self-modify-toggle"', html)
        self.assertIn('id="self-modify-enabled"', html)
        self.assertIn("agent/js/self_modify_switch.js", html)

    def test_the_box_is_completely_absent_otherwise(self):
        html = self._page(False)
        self.assertNotIn("self-modify-toggle", html)
        self.assertNotIn("self-modify-enabled", html)
        self.assertNotIn("self_modify_switch.js", html)
        self.assertNotIn("Self-modify", html)


class FrozenPageTests(TestCase):
    """The real view, the real template and the real availability rule, run
    AS A FROZEN BUILD (sys.frozen + sys.executable): a build made without
    --self-modify must not show the box at all; one made with it must."""

    def setUp(self):
        cm.reset_cache()
        self._dirs = []
        user = get_user_model().objects.create_user("selfmod_frozen", password="x-test-only")
        self.client.force_login(user)

    def tearDown(self):
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)
        cm.reset_cache()

    def _frozen_page(self, with_tree):
        exe_dir = _app_dir(with_tree=with_tree)
        self._dirs.append(exe_dir)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", os.path.join(exe_dir, "Tlamatini.exe")):
            self.assertEqual(rc.self_modify_available(), with_tree)
            self.assertEqual(cm.self_modify_available(), with_tree)
            response = self.client.get("/agent/agent/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def test_a_frozen_build_without_self_modify_hides_the_box_completely(self):
        html = self._frozen_page(with_tree=False)
        self.assertNotIn("self-modify-toggle", html)
        self.assertNotIn("self_modify_switch.js", html)
        self.assertNotIn("Self-modify", html)

    def test_a_frozen_self_modify_build_shows_the_box(self):
        html = self._frozen_page(with_tree=True)
        self.assertIn('id="self-modify-toggle"', html)
        self.assertIn("agent/js/self_modify_switch.js", html)

    def test_a_frozen_build_without_self_modify_sends_no_self_knowledge(self):
        exe_dir = _app_dir(with_tree=False)
        self._dirs.append(exe_dir)
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", os.path.join(exe_dir, "Tlamatini.exe")):
            _, prompt, _ = rc.load_config_and_prompt(exe_dir)
            self.assertNotIn(_SELF_TEXT, prompt)
            self.assertIn("not-self-able-modify build", prompt)
            self.assertFalse(cm.self_modify_active())
            self.assertEqual(cm.set_self_modify(True)["refused"], "unavailable")


class SourceContractTests(SimpleTestCase):
    JS = (AGENT_DIR / "static" / "agent" / "js" / "self_modify_switch.js").read_text(encoding="utf-8")
    CONSUMERS = (AGENT_DIR / "consumers.py").read_text(encoding="utf-8")
    TEMPLATE = (AGENT_DIR / "templates" / "agent" / "agent_page.html").read_text(encoding="utf-8")

    def test_the_script_is_self_contained(self):
        self.assertIn("(function () {", self.JS)
        self.assertIn("window.TlmSelfModify", self.JS)
        self.assertIn("'set-self-modify'", self.JS)
        self.assertIn("window.tlmAlert", self.JS)
        self.assertIn("tlm:compact-mode-state", self.JS)
        self.assertIn("tlm:context-gauge", self.JS)

    def test_the_consumer_handles_the_box_and_spares_the_rows(self):
        self.assertIn("if type == 'set-self-modify':", self.CONSUMERS)
        self.assertIn("async def _handle_set_self_modify", self.CONSUMERS)
        self.assertIn("if kind == 'self_modify':", self.CONSUMERS)

    def test_the_box_and_its_script_sit_inside_the_same_condition(self):
        box = self.TEMPLATE.index('id="self-modify-toggle"')
        script = self.TEMPLATE.index("agent/js/self_modify_switch.js")
        self.assertLess(self.TEMPLATE.rfind("{% if self_modify_available %}", 0, box),
                        box)
        self.assertGreater(self.TEMPLATE.rfind("{% if self_modify_available %}", 0, box), -1)
        self.assertGreater(self.TEMPLATE.rfind("{% if self_modify_available %}", 0, script), box)
        self.assertLess(self.TEMPLATE.index("agent/js/model_capacity.js"), script)

    def test_carriage(self):
        runtime = (REPO / "build_runtime_assets.py").read_text(encoding="utf-8")
        snapshot = (REPO / "copy_source_assets.py").read_text(encoding="utf-8")
        self.assertIn("agent/js/self_modify_switch.js", runtime)
        for name in ("0212_compact_state_self_modify.py", "self_modify_switch.js"):
            self.assertIn(name, snapshot)
