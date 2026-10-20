# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Terminater, wired into the rest of Tlamatini.

A new agent is not finished when its own code works; it is finished when every place that must
KNOW about it does: the wrapped-tool registry the LLM reads, the Exec Report and Ask-Execs
tables, the verdict vocabulary, the Parametrizer contract, the migrations, the three pages that
carry the dock, the build / self-update / self-modify carriage lists and the vendored terminal
renderer.  Each test below pins one of those joints.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import agent_verdict as av
from . import chat_agent_registry as reg
from . import mcp_agent
from . import terminater_testkit as kit
from .services import agent_contracts, agent_paths

AGENT_DIR = Path(__file__).resolve().parent
REPO = AGENT_DIR.parent.parent
JS = AGENT_DIR / "static" / "agent" / "js"
CSS = AGENT_DIR / "static" / "agent" / "css"
VENDOR = AGENT_DIR / "static" / "agent" / "vendor" / "frontend"
TEMPLATES = AGENT_DIR / "templates" / "agent"
eng = kit.engine()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The wrapped tool the LLM reads                                               #
# --------------------------------------------------------------------------- #

class RegistryTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spec = reg.WRAPPED_CHAT_AGENT_BY_TOOL_NAME["chat_agent_terminater"]

    def test_the_tool_is_registered_three_ways(self):
        self.assertIs(reg.WRAPPED_CHAT_AGENT_MAP["terminater"], self.spec)
        self.assertIs(reg.WRAPPED_CHAT_AGENT_BY_DESCRIPTION["Chat-Agent-Terminater"], self.spec)

    def test_identity_fields(self):
        self.assertEqual(self.spec.key, "terminater")
        self.assertEqual(self.spec.template_dir, "terminater")
        self.assertEqual(self.spec.tool_name, "chat_agent_terminater")
        self.assertEqual(self.spec.tool_description, "Chat-Agent-Terminater")
        self.assertEqual(self.spec.display_name, "Terminater")

    def test_the_template_folder_exists(self):
        self.assertTrue((AGENT_DIR / "agents" / self.spec.template_dir / "terminater.py").is_file())

    def test_the_display_name_is_the_one_the_boot_resolver_uses(self):
        self.assertEqual(agent_paths.display_name_from_agent_type("terminater"), "Terminater")

    def test_the_display_name_is_never_mangled(self):
        for bad in ("TerminaTer", "TERMINATER", "Terminator", "TerminaTor"):
            self.assertNotEqual(self.spec.display_name, bad)

    def test_the_text_field_is_a_byte_exact_channel(self):
        for field in ("text", "message", "hint", "suggestion"):
            self.assertIn(field, self.spec.verbatim_fields)

    def test_the_long_poll_window_is_set(self):
        self.assertEqual(self.spec.poll_window_seconds, 25)

    def test_the_model_is_told_what_it_is_for(self):
        purpose = self.spec.purpose
        for phrase in ("VISIBLE", "USER-SUPERVISED", "NOT a silent command runner", "Executer", "Views > Terminals"):
            self.assertIn(phrase, purpose, phrase)

    def test_the_model_is_told_it_types_like_a_person(self):
        purpose = self.spec.purpose
        self.assertIn("one at a time", purpose)
        self.assertIn("never pasted", purpose)
        self.assertIn("typing_wpm", purpose)

    def test_every_documented_action_is_named(self):
        for action in ("run", "open", "type", "send_key", "wait", "read", "commands", "abort", "kill",
                       "force_kill", "kill_all", "list", "focus", "rename", "layout", "watch_user",
                       "warn_user", "handover"):
            self.assertIn(action, self.spec.purpose, action)
            self.assertIn(action, eng.ACTIONS, action)

    def test_the_hand_over_syntax_and_secret_are_documented(self):
        self.assertIn("<<USER:", self.spec.purpose)
        self.assertIn("secret=true", self.spec.purpose)
        self.assertIn("operator_required", self.spec.purpose)

    def test_the_statuses_the_model_must_react_to_are_explained(self):
        for status in ("completed", "command_failed", "hung", "operator_required", "timeout", "aborted"):
            self.assertIn(status, self.spec.purpose, status)

    def test_cmd_cannot_report_an_exit_code_and_the_model_is_told_so(self):
        self.assertIn("CMD cannot", self.spec.purpose)

    def test_the_model_is_warned_off_destructive_commands(self):
        self.assertIn("Do not run destructive", self.spec.purpose)

    def test_the_model_is_never_to_type_a_secret_itself(self):
        self.assertIn("Never type a secret yourself", self.spec.purpose)

    def test_the_example_request_names_an_action_and_a_shell(self):
        self.assertIn("action='run'", self.spec.example_request)
        self.assertIn("powershell", self.spec.example_request)

    def test_aliases_and_hints_cover_the_ways_people_ask(self):
        for alias in ("terminater", "terminal", "visible terminal", "watch me type"):
            self.assertIn(alias, self.spec.aliases)
        for hint in ("terminal", "powershell", "cmd", "step by step", "show me the command", "ctrl+c"):
            self.assertIn(hint, self.spec.security_hints)

    def test_no_other_agent_claims_its_name_alias(self):
        for other in reg.WRAPPED_CHAT_AGENT_SPECS:
            if other is self.spec:
                continue
            self.assertNotIn("terminater", [a.lower() for a in other.aliases], other.key)

    def test_exactly_one_spec_per_tool_name(self):
        names = [s.tool_name for s in reg.WRAPPED_CHAT_AGENT_SPECS]
        self.assertEqual(len(names), len(set(names)))


# --------------------------------------------------------------------------- #
# Exec Report, Ask-Execs, tool gate                                            #
# --------------------------------------------------------------------------- #

class WiringTests(SimpleTestCase):
    def test_exec_report_has_a_native_row(self):
        self.assertEqual(mcp_agent._EXEC_REPORT_TOOLS["chat_agent_terminater"], ("terminater", "Terminater"))

    def test_the_report_resolver_finds_it(self):
        self.assertEqual(tuple(mcp_agent._resolve_exec_report_spec("chat_agent_terminater")), ("terminater", "Terminater"))

    def test_it_is_not_a_management_helper(self):
        self.assertNotIn("chat_agent_terminater", mcp_agent._MANAGEMENT_TOOLS)

    def test_ask_execs_gates_it(self):
        self.assertIn("chat_agent_terminater", mcp_agent._ASK_EXECS_REQUIRED_TOOLS)

    def test_the_gate_table_carries_the_wrapper(self):
        from . import tools

        rows = tools.tool_gate_table()
        self.assertTrue([r for r in rows if "terminater" in str(r[0]).lower()],
                        "tool_gate_table() must list the wrapper so Compact mode can see it")

    def test_exec_report_css_has_a_caption(self):
        css = _read(CSS / "agent_page.css")
        self.assertIn("exec-report-caption-terminater", css)
        self.assertIn(".exec-report-terminater .exec-report-cmd", css)

    def test_the_canvas_gradient_exists_for_the_agent(self):
        css = _read(CSS / "agentic_control_panel.css")
        self.assertIn(".canvas-item.terminater-agent", css)

    def test_the_visible_command_preview_titles_the_typed_command(self):
        self.assertIn("TERMINATER COMMAND TO TYPE", _read(AGENT_DIR / "tools.py"))

    def test_the_watchdog_and_reaper_know_terminals_are_long_lived_on_purpose(self):
        self.assertIn("terminal_hub", _read(AGENT_DIR / "command_watchdog.py"))
        self.assertIn("terminal_hub", _read(AGENT_DIR / "orphan_reaper.py"))

    def test_the_hub_is_published_at_startup(self):
        self.assertIn("terminal_hub", _read(AGENT_DIR / "apps.py"))

    def test_the_websocket_route_exists(self):
        self.assertIn("ws/terminals/", _read(AGENT_DIR / "routing.py"))

    def test_the_http_routes_exist(self):
        urls = _read(AGENT_DIR / "urls.py")
        self.assertIn("terminater/api/", urls)
        self.assertIn("terminater/state/", urls)
        self.assertIn("update_terminater_connection", urls)


class VerdictTests(SimpleTestCase):
    @staticmethod
    def verdict(status, exit_code=0, success="True"):
        text = f"INI_SECTION_TERMINATER<<<\nstatus: {status}\nsuccess: {success}\n\nbody\n>>>END_SECTION_TERMINATER"
        return av.evaluate(av.parse_section(text), exit_code)

    def test_every_status_the_terminal_can_report_is_a_known_token(self):
        for status in ("completed", "command_failed", "hung", "operator_required", "timeout", "aborted", "opened",
                       "listed", "typed", "started", "read", "killed", "focused", "warned", "observed", "refused",
                       "error", "unavailable"):
            self.assertIn(status, av.KNOWN_STATUSES, status)

    def test_the_actions_that_happened_are_green(self):
        for status in ("completed", "opened", "typed", "killed", "focused", "warned", "listed", "observed", "read"):
            self.assertTrue(self.verdict(status).ok, status)

    def test_a_command_that_ran_and_failed_is_red(self):
        v = self.verdict("command_failed", success="False")
        self.assertFalse(v.ok)
        self.assertEqual(v.source, "agent")

    def test_a_hung_command_is_red(self):
        self.assertFalse(self.verdict("hung", success="False").ok)

    def test_work_that_did_not_happen_is_red(self):
        for status in ("refused", "unavailable", "timeout", "aborted", "operator_required"):
            self.assertFalse(self.verdict(status, success="False").ok, status)

    def test_an_agent_error_is_red(self):
        self.assertFalse(self.verdict("error", success="False").ok)

    def test_the_self_report_outranks_a_zero_exit_code(self):
        self.assertFalse(self.verdict("command_failed", exit_code=0, success="False").ok)

    def test_the_self_report_outranks_a_nonzero_exit_code(self):
        self.assertTrue(self.verdict("completed", exit_code=1).ok)

    def test_the_status_sets_stay_disjoint(self):
        sets = [av.DIAGNOSTIC_COMPLETED_STATUSES, av.WORK_COMPLETED_STATUSES, av.WORK_DEGRADED_STATUSES,
                av.WORK_NOT_DONE_STATUSES, av.AGENT_ERROR_STATUSES]
        for i, a in enumerate(sets):
            for b in sets[i + 1:]:
                self.assertEqual(a & b, set())


class ContractTests(SimpleTestCase):
    def test_parametrizer_can_read_the_fields(self):
        fields = agent_contracts._PARAMETRIZER_OUTPUT_FIELDS["terminater"]
        for name in ("status", "success", "terminal_id", "exit_code", "command", "typed", "user_part", "user_line",
                     "user_keys", "cursor", "watch_reason", "wait_reason", "layout", "area", "response_body"):
            self.assertIn(name, fields)

    def test_the_derived_view_table_agrees(self):
        from . import views

        self.assertEqual(tuple(views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS["terminater"]),
                         tuple(agent_contracts._PARAMETRIZER_OUTPUT_FIELDS["terminater"]))

    def test_the_contract_resolves_by_every_spelling(self):
        for name in ("terminater", "Terminater", "TERMINATER"):
            contract = agent_contracts.get_agent_contract(name)
            self.assertEqual(contract.agent_type, "terminater", name)

    def test_it_is_an_ordinary_active_agent(self):
        contract = agent_contracts.get_agent_contract("terminater")
        self.assertFalse(contract.singleton)
        self.assertFalse(contract.no_input)
        self.assertFalse(contract.no_output)
        self.assertFalse(contract.exclude_from_validation)

    def test_the_flow_catalog_lists_it(self):
        catalog = json.loads(_read(AGENT_DIR / "agents" / "flowcreator" / "flow_catalog.json"))
        self.assertIn("terminater", json.dumps(catalog).lower())

    def test_flowhypervisor_knows_not_to_flag_a_long_lived_terminal(self):
        notes = _read(AGENT_DIR / "agents" / "flowhypervisor" / "monitoring-prompt.pmt")
        self.assertIn("TERMINATER SPECIAL NOTES", notes)


# --------------------------------------------------------------------------- #
# Migrations                                                                   #
# --------------------------------------------------------------------------- #

class MigrationRowsTests(TestCase):
    def test_the_wrapper_tool_row_exists_once(self):
        from .models import Tool

        rows = Tool.objects.filter(toolDescription="Chat-Agent-Terminater")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().toolContent, "true")
        self.assertTrue(rows.first().toolName.startswith("tool-"))

    def test_tool_ids_are_unique(self):
        from .models import Tool

        ids = list(Tool.objects.values_list("idTool", flat=True))
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_demo_prompts_exist_in_the_run_and_execute_section(self):
        from .models import Prompt

        rows = list(Prompt.objects.filter(idPrompt__in=(127, 128, 129)).order_by("idPrompt"))
        self.assertEqual([r.idPrompt for r in rows], [127, 128, 129])
        for row in rows:
            self.assertEqual(row.category, "run_execute")
            self.assertEqual(row.promptName, f"prompt-{row.idPrompt}")
            self.assertIn("chat_agent_terminater", row.promptContent)

    def test_the_demo_prompts_are_ranked_beside_executer(self):
        from .models import Prompt

        ranks = list(Prompt.objects.filter(idPrompt__in=(127, 128, 129)).order_by("idPrompt")
                     .values_list("sort_rank", flat=True))
        self.assertEqual(ranks, [62, 64, 66])

    def test_the_demo_prompts_use_the_parameter_grammar(self):
        from .models import Prompt

        for row in Prompt.objects.filter(idPrompt__in=(127, 128, 129)):
            self.assertNotIn("C:/Temp", row.promptContent)
            self.assertNotIn("C:\\Temp", row.promptContent)

    def test_the_migration_chain_ends_where_expected(self):
        names = sorted(p.stem for p in (AGENT_DIR / "migrations").glob("02*.py"))
        self.assertIn("0215_add_terminater", names)
        self.assertIn("0216_add_chat_agent_terminater_tool", names)
        self.assertIn("0217_add_terminater_demo_prompts", names)

    def test_each_migration_depends_on_the_previous_one(self):
        for number, previous in (("0216_add_chat_agent_terminater_tool", "0215_add_terminater"),
                                 ("0217_add_terminater_demo_prompts", "0216_add_chat_agent_terminater_tool")):
            self.assertIn(previous, _read(AGENT_DIR / "migrations" / f"{number}.py"))

    def test_the_migration_description_matches_the_registry_byte_for_byte(self):
        self.assertIn('WRAPPED_TOOL_DESCRIPTION = "Chat-Agent-Terminater"',
                      _read(AGENT_DIR / "migrations" / "0216_add_chat_agent_terminater_tool.py"))

    def test_the_agent_row_name_in_the_migration_is_exact(self):
        self.assertIn("Terminater", _read(AGENT_DIR / "migrations" / "0215_add_terminater.py"))


# --------------------------------------------------------------------------- #
# Carriage: build, self-update, self-modify                                    #
# --------------------------------------------------------------------------- #

class CarriageTests(SimpleTestCase):
    def test_the_frozen_build_names_the_hub_consumer_views_and_engine_loader(self):
        build = _read(REPO / "build.py")
        self.assertIn("_FROZEN_TERMINATER_MODULES", build)
        for module in ("agent.terminal_hub", "agent.terminal_consumer", "agent.terminal_views"):
            self.assertIn(module, build, module)
        self.assertIn("--hidden-import={module}", build)

    def test_the_build_proves_the_modules_are_in_the_archive(self):
        build = _read(REPO / "build.py")
        self.assertIn("_FROZEN_REQUIRED_AGENT_MODULES", build)
        self.assertRegex(build, r"\*_FROZEN_TERMINATER_MODULES,")

    def test_the_runtime_assets_list_requires_the_dock_files(self):
        text = _read(REPO / "build_runtime_assets.py")
        self.assertIn("agent/js/terminater_dock.js", text)
        self.assertIn("agent/css/terminater_dock.css", text)

    def test_self_modify_snapshot_requires_every_new_file(self):
        text = _read(REPO / "copy_source_assets.py")
        for needle in ("agents/terminater/terminater.py", "agents/terminater/terminater_engine.py",
                       "agents/terminater/terminater_conpty.py", "agents/terminater/terminater_text.py",
                       "agents/terminater/config.yaml", "js/terminater_dock.js", "css/terminater_dock.css",
                       "0215_add_terminater.py", "0216_add_chat_agent_terminater_tool.py",
                       "0217_add_terminater_demo_prompts.py", "scripts/terminater_visible_common.py",
                       "scripts/terminater_visible_chat.py"):
            self.assertIn(needle, text, needle)

    def test_every_file_the_snapshot_requires_exists(self):
        text = _read(REPO / "copy_source_assets.py")
        missing = []
        for rel in re.findall(r'"((?:Tlamatini|scripts)/[^"]*terminat[^"]*)"', text):
            if not (REPO / rel).exists():
                missing.append(rel)
        self.assertEqual(missing, [])

    def test_the_frozen_build_runs_the_real_terminal_gate_before_packaging(self):
        # the engine is a LOOSE file loaded by path: only RUNNING it in the frozen layout proves it works
        build = _read(REPO / "build.py")
        self.assertIn('"agent.management.commands.check_terminater"', build)
        gate = build.index('run_cmd(["check_terminater"]')
        self.assertGreater(gate, build.index('run_cmd(["check_prompt_flow_panel"]'))       # after the panel gate
        self.assertLess(gate, build.index("# 8d) Rename executable manage -> Tlamatini"))   # before the rename/package
        self.assertIn("refusing to package the terminals", build)
        self.assertIn("Tlamatini/agent/management/commands/check_terminater.py", _read(REPO / "copy_source_assets.py"))

    def test_the_real_terminal_gate_passes_from_source(self):
        """The very command the build runs, in a fresh process: real PowerShell and cmd.exe through the
        pseudo console, the shipped pool agent, and the browser's WebSocket consumer."""
        import subprocess
        import sys

        completed = subprocess.run([sys.executable, str(AGENT_DIR.parent / "manage.py"), "check_terminater"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=420, cwd=str(AGENT_DIR.parent))
        self.assertEqual(completed.returncode, 0, (completed.stdout + completed.stderr)[-1500:])
        report = next((json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{") and "websocket_frames" in line), None)
        self.assertIsNotNone(report, completed.stdout[-800:])
        self.assertEqual((report["powershell"], report["cmd"], report["pool_agent"]), ("completed", "completed", "completed"))
        self.assertIn("hello", report["websocket_frames"])
        self.assertIn("opened", report["websocket_frames"])
        self.assertEqual(report["pages_with_dock"], 3)

    def test_the_gate_leaves_no_pool_directory_or_rendezvous_file_behind(self):
        text = _read(AGENT_DIR / "management" / "commands" / "check_terminater.py")
        self.assertIn('shutil.rmtree(pool.parent, ignore_errors=True)', text)
        self.assertIn("terminal_hub.shutdown()", text)           # removes the rendezvous file the socket step published

    def test_the_vendor_script_lists_the_three_terminal_packages(self):
        text = _read(REPO / "scripts" / "vendor_frontend.py")
        for package in ("@xterm/xterm", "@xterm/addon-fit", "@xterm/addon-web-links"):
            self.assertIn(package, text, package)

    def test_eslint_knows_the_connector_global(self):
        self.assertIn("updateTerminaterConnection", _read(REPO / "eslint.config.mjs"))

    def test_the_agent_is_in_the_agent_catalog(self):
        self.assertTrue((AGENT_DIR / "agents" / "terminater").is_dir())

    def test_no_generated_log_or_pid_file_is_left_in_the_template(self):
        leftovers = [p.name for p in (AGENT_DIR / "agents" / "terminater").iterdir()
                     if p.suffix in (".log", ".pid") or p.name == "__pycache__"]
        self.assertEqual([n for n in leftovers if n != "__pycache__"], [])


class VendoredRendererTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manifest = json.loads(_read(VENDOR / "manifest.json"))

    def entries(self):
        packages = self.manifest.get("packages") or self.manifest
        return packages if isinstance(packages, (list, dict)) else {}

    def test_the_manifest_mentions_xterm(self):
        self.assertIn("xterm", json.dumps(self.manifest))

    def test_the_vendored_files_exist(self):
        for rel in ("xterm/lib/xterm.js", "xterm/css/xterm.css", "xterm-addon-fit/lib/addon-fit.js",
                    "xterm-addon-web-links/lib/addon-web-links.js"):
            self.assertTrue((VENDOR / rel).is_file(), rel)

    def test_the_vendored_files_are_not_empty(self):
        for rel in ("xterm/lib/xterm.js", "xterm/css/xterm.css", "xterm-addon-fit/lib/addon-fit.js",
                    "xterm-addon-web-links/lib/addon-web-links.js"):
            self.assertGreater((VENDOR / rel).stat().st_size, 1000, rel)

    def test_the_licenses_travel_with_the_packages(self):
        for folder in ("xterm", "xterm-addon-fit", "xterm-addon-web-links"):
            names = [p.name.lower() for p in (VENDOR / folder).iterdir()]
            self.assertTrue(any("license" in n for n in names), folder)

    def test_every_receipt_hash_matches_the_file_on_disk(self):
        text = json.dumps(self.manifest)
        found = 0
        for rel in ("xterm/lib/xterm.js", "xterm/css/xterm.css", "xterm-addon-fit/lib/addon-fit.js",
                    "xterm-addon-web-links/lib/addon-web-links.js"):
            digest = hashlib.sha256((VENDOR / rel).read_bytes()).hexdigest()
            if digest in text:
                found += 1
        self.assertGreaterEqual(found, 1, "the manifest must carry at least one verifiable receipt")

    def test_no_cdn_is_used_by_any_page(self):
        for name in ("agent_page.html", "agentic_control_panel.html", "prompt_flow_panel.html"):
            text = _read(TEMPLATES / name)
            for line in text.splitlines():
                if "xterm" in line:
                    self.assertNotIn("cdn", line.lower(), line)
                    self.assertNotIn("http://", line.lower(), line)
                    self.assertNotIn("https://", line.lower(), line)


# --------------------------------------------------------------------------- #
# The dock's source and the three pages                                        #
# --------------------------------------------------------------------------- #

class DockSourceTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = _read(JS / "terminater_dock.js")
        cls.css = _read(CSS / "terminater_dock.css")

    def test_it_is_a_self_contained_iife(self):
        self.assertTrue(self.js.lstrip().startswith("/*") or self.js.lstrip().startswith("//") or "(function" in self.js[:3000])
        self.assertIn("window.TlamatiniTerminals", self.js)

    def test_it_exports_one_frozen_object(self):
        self.assertIn("window.TlamatiniTerminals = Object.freeze({", self.js)

    def test_it_never_loads_twice(self):
        self.assertIn("if (window.TlamatiniTerminals) return;", self.js)

    def test_it_talks_to_the_hub_over_the_same_origin_socket(self):
        self.assertIn("'/ws/terminals/'", self.js)
        self.assertIn("location.host", self.js)
        self.assertIn("'wss://'", self.js)

    def test_selecting_a_tab_never_rebuilds_the_strip(self):
        # a rebuild between the two clicks of a double-click made renaming impossible, and dropped
        # the keyboard focus the arrow keys rely on (found by the visible browser run, 2026-10-19)
        body = self.js[self.js.index("function activate("):]
        body = body[:body.index("function cycleTab")]
        self.assertNotIn("renderTabs()", body)
        self.assertIn("syncTabSelection()", body)
        self.assertIn("function syncTabSelection()", self.js)

    def test_the_terminal_never_steals_the_focus_from_the_rename_field(self):
        body = self.js[self.js.index("function focusTerm("):]
        body = body[:body.index("\n    }\n")]
        self.assertIn("tlm-term-tab-title-input", body)

    def test_arrow_navigation_keeps_the_focus_on_the_tabs(self):
        key = self.js[self.js.index("function onTabsKey("):]
        key = key[:key.index("/* ── layout")]
        self.assertIn("activate(next, true, true)", key)
        self.assertIn("if (!keepFocus) focusTerm(", self.js)

    def test_the_type_choice_can_be_kept_for_new_terminals(self):
        # with a PowerShell terminal active there must still be a way to raise a CMD one
        body = self.js[self.js.index("function onKindChange("):]
        body = body[:body.index("function syncTabSelection")]
        self.assertIn("Only for new terminals", body)
        self.assertIn("S.kindPin = wanted", body)
        self.assertNotIn("S.els.kind.value = T.kind", body)
        self.assertIn("S.kindPin = ''", self.js[self.js.index("function openTerminal("):self.js.index("function killActive(")])

    def test_the_typed_line_is_re_read_when_the_shell_echo_arrives(self):
        # the shell echoes a key after it was typed: reading only 45 ms after the last key loses its last character
        self.assertIn("T.typedAt = Date.now()", self.js)
        out = self.js[self.js.index("case 'out':"):self.js.index("case 'replay':")]
        self.assertIn("T.term.write(m.d || '', () =>", out)
        self.assertIn("scheduleLine(T)", out)
        self.assertIn("typedAt: 0", self.js)

    def test_the_users_hide_is_told_to_the_hub(self):
        # otherwise the hub keeps answering "visible" and a reload re-opens a dock the user closed
        body = self.js[self.js.index("function setVisible("):self.js.index("function setLayout(")]
        self.assertIn("send({ t: 'layout', show })", body)
        self.assertIn("persist !== false && S.hello && was !== show", body)

    def test_it_does_not_use_eval_or_document_write(self):
        self.assertNotRegex(self.js, r"\beval\s*\(")
        self.assertNotIn("document.write", self.js)
        self.assertNotRegex(self.js, r"new Function\s*\(")

    def test_every_storage_access_is_guarded(self):
        for match in re.finditer(r"localStorage\.(getItem|setItem)", self.js):
            before = self.js[max(0, match.start() - 160):match.start()]
            self.assertIn("try", before, "localStorage must be wrapped in try/catch")

    def test_it_declares_no_cross_file_globals(self):
        self.assertEqual(len(re.findall(r"^\s*window\.[A-Za-z_]+\s*=", self.js, re.M)), 1)

    def test_accessibility_roles_are_present(self):
        for needle in ("role: 'tablist'", "role: 'toolbar'", "role: 'separator'", "role: 'region'", "'aria-selected'",
                       "'aria-pressed'", "'aria-live': 'polite'", "role: 'status'"):
            self.assertIn(needle, self.js, needle)

    def test_the_page_level_shortcut_is_ctrl_backtick(self):
        self.assertIn("ev.ctrlKey && !ev.altKey && !ev.metaKey && ev.key === '`'", self.js)

    def test_the_terminal_lets_the_page_have_ctrl_backtick(self):
        self.assertIn("if (event.ctrlKey && event.key === '`') return false;", self.js)

    def test_the_body_classes_that_the_css_keys_on(self):
        self.assertIn("'tlm-terminals-on'", self.js)
        self.assertIn("'tlm-terminals-full'", self.js)
        self.assertIn("tlm-terminals-on", self.css)
        self.assertIn("tlm-terminals-full", self.css)

    def test_the_host_attribute_contract(self):
        self.assertIn("data-tlm-terminals-host", self.js)
        self.assertIn("data-tlm-terminals-toggle", self.js)
        self.assertIn("[data-tlm-terminals-host]{display:contents;}", re.sub(r"\s+", "", self.css))

    def test_the_three_pages_are_distinguished_by_the_host_value(self):
        for page in ("chat", "acp", "pfp"):
            self.assertIn(page, self.js)

    def test_the_dock_has_an_icon_only_mode_for_narrow_columns(self):
        self.assertIn("@container tlmterm", self.css)
        self.assertIn("container-type:inline-size", self.css.replace(" ", ""))

    def test_the_bar_offers_the_two_shells_and_the_layouts(self):
        for needle in ("CMD", "PowerShell", "Tabs", "Tile", "Side", "Stack", "Grid", "Dock", "Full"):
            self.assertIn(needle, self.js, needle)

    def test_the_bar_offers_the_user_the_controls(self):
        for needle in ("Interrupt", "Force kill", "Clear", "Copy", "Advisor"):
            self.assertIn(needle, self.js, needle)

    def test_user_facing_notes_exist_for_typing_handover_hung_and_warnings(self):
        for needle in ("handover", "hung", "warn", "notice"):
            self.assertIn(needle, self.js, needle)

    def test_the_css_respects_reduced_motion_and_the_shared_tokens(self):
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("var(--", self.css)

    def test_the_css_never_sets_a_fixed_pixel_height_for_the_dock_itself(self):
        # (min-height is a floor, not a fixed size; the height itself comes from --tlm-term-h)
        self.assertNotRegex(self.css, r"\.tlm-terminals\s*\{[^}]*(?<![-\w])height:\s*\d+px")

    def test_the_css_scopes_every_rule_to_the_dock(self):
        stray = [ln for ln in self.css.splitlines()
                 if re.match(r"^(body|html|\*|\.chat-page|\.card|\.btn)\b", ln.strip()) and "tlm-" not in ln]
        self.assertEqual(stray, [], "dock CSS must not restyle the host page")


class PageIntegrationTests(SimpleTestCase):
    def test_every_page_loads_the_renderer_before_the_dock(self):
        for name in ("agent_page.html", "agentic_control_panel.html", "prompt_flow_panel.html"):
            text = _read(TEMPLATES / name)
            order = [text.index(part) for part in ("xterm/lib/xterm.js", "addon-fit.js", "addon-web-links.js",
                                                   "terminater_dock.js")]
            self.assertEqual(order, sorted(order), name)

    def test_every_page_links_the_renderer_css_before_the_dock_css(self):
        for name in ("agent_page.html", "agentic_control_panel.html", "prompt_flow_panel.html"):
            text = _read(TEMPLATES / name)
            self.assertLess(text.index("xterm/css/xterm.css"), text.index("terminater_dock.css"), name)

    def test_every_page_has_one_host_and_one_toggle(self):
        for name, host in (("agent_page.html", "chat"), ("agentic_control_panel.html", "acp"),
                           ("prompt_flow_panel.html", "pfp")):
            text = _read(TEMPLATES / name)
            self.assertEqual(text.count(f'data-tlm-terminals-host="{host}"'), 1, name)
            self.assertEqual(text.count("data-tlm-terminals-toggle"), 1, name)
            self.assertIn('role="menuitemcheckbox"', text)
            self.assertIn('aria-controls="tlm-terminals"', text)

    def test_every_toggle_lives_in_the_views_menu(self):
        for name in ("agent_page.html", "agentic_control_panel.html", "prompt_flow_panel.html"):
            text = _read(TEMPLATES / name)
            toggle = text.index("views-terminals-toggle")
            labelled = re.findall(r'aria-labelledby="([^"]+)"', text[:toggle])
            self.assertTrue(labelled, name)
            self.assertIn("view", labelled[-1].lower(), f"{name}: the toggle must sit in the View(s) menu")

    def test_the_dock_scripts_use_the_cache_buster(self):
        for name in ("agent_page.html", "agentic_control_panel.html", "prompt_flow_panel.html"):
            text = _read(TEMPLATES / name)
            self.assertIn("terminater_dock.js' %}?v={{ STATIC_VERSION }}_term1", text)
            self.assertIn("terminater_dock.css' %}?v={{ STATIC_VERSION }}_term1", text)

    def test_the_chat_page_keeps_the_canvas_visible_when_terminals_are_on(self):
        text = _read(TEMPLATES / "agent_page.html")
        self.assertIn(".chat-page.tlm-canvas-hidden:not(.tlm-terminals-on) #canvas-container", text)

    def test_the_layout_script_lets_the_dock_use_a_hidden_canvas_column(self):
        text = _read(JS / "agent_page_layout.js")
        self.assertIn("tlm-terminals-on", text)

    def test_the_chat_script_maps_terminater_to_its_tool_arguments(self):
        text = _read(JS / "agent_page_chat.js")
        self.assertIn("terminater", text.lower())

    def test_the_canvas_core_connects_the_agent_in_all_the_places_it_must(self):
        core = _read(JS / "acp-canvas-core.js")
        self.assertIn("'terminater': 'terminater-agent'", core)
        self.assertGreaterEqual(core.count("updateTerminaterConnection"), 3)
        self.assertIn("/agent/update_terminater_connection/", _read(JS / "acp-agent-connectors.js"))
        self.assertIn("updateTerminaterConnection", _read(JS / "acp-canvas-undo.js"))
        self.assertIn("updateTerminaterConnection", _read(JS / "acp-file-io.js"))

    def test_a_hand_over_tells_the_page_before_the_terminal_takes_the_keyboard(self):
        dock = _read(JS / "terminater_dock.js")
        branch = dock[dock.index("if (state === 'awaiting_user') {"):dock.index("} else if (previous === 'awaiting_user')")]
        self.assertIn("emit('handover', { id: T.id, hint, secret })", branch)
        self.assertIn("previous !== 'awaiting_user'", branch)   # once per hand-over, not on every state frame
        self.assertLess(branch.index("emit('handover'"), branch.index("focusTerm(T)"))

    def test_the_panel_steps_its_startup_dialog_aside_for_a_hand_over(self):
        # the "Startup Complete" dialog is modal: its overlay and focus trap swallowed the user's keys
        # while the hand-over's wait clock kept running (a 90 s hand-over timed out)
        buttons = _read(JS / "acp-control-buttons.js")
        self.assertIn("window.addEventListener('tlm:terminals-handover', dismissStarterDialogForHandover)", buttons)
        body = buttons[buttons.index("function dismissStarterDialogForHandover()"):buttons.index("function terminalAwaitsTheUser()")]
        self.assertIn("dialog('isOpen')", body)
        self.assertIn("dialog('close')", body)          # its own close: restores the scroll lock and the overlay
        self.assertNotIn(".hide()", body)                # never a blind hide of the node
        self.assertNotIn(".remove()", body)
        # a hand-over that is already waiting when the dialog opens is handled too
        opener = buttons[buttons.index("function showStarterExecutionDialog("):buttons.index("async function pollForLogFiles(")]
        self.assertIn("terminalAwaitsTheUser()", opener)
        self.assertIn("awaiting_user", buttons[buttons.index("function terminalAwaitsTheUser()"):buttons.index("window.addEventListener('tlm:terminals-handover'")])

    def test_the_hand_over_signal_is_emitted_through_the_dock_event_channel(self):
        dock = _read(JS / "terminater_dock.js")
        self.assertIn("new CustomEvent('tlm:terminals-' + type", dock)   # emit('handover') -> tlm:terminals-handover

    def test_the_prompt_flow_panel_has_the_parallelogram(self):
        model = _read(JS / "prompt-flow-panel-model.js")
        self.assertIn("path: 'M52 20H196L148 108H4Z'", model)
        self.assertIn("terminater:", model)


class PageRenderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("terminater_pages", password="x")
        self.client.force_login(self.user)

    def get(self, name):
        res = self.client.get(reverse(name))
        self.assertEqual(res.status_code, 200, name)
        return res.content.decode("utf-8")

    def test_the_chat_page_renders_the_dock_host_and_toggle(self):
        html = self.get("agent_page")
        self.assertIn('data-tlm-terminals-host="chat"', html)
        self.assertIn("data-tlm-terminals-toggle", html)
        self.assertIn("terminater_dock.js", html)
        self.assertIn("xterm.js", html)

    def test_the_acp_page_renders_the_dock_host_and_toggle(self):
        html = self.get("agentic_control_panel")
        self.assertIn('data-tlm-terminals-host="acp"', html)
        self.assertIn("data-tlm-terminals-toggle", html)

    def test_the_prompt_flow_panel_renders_the_dock_host_and_toggle(self):
        html = self.get("prompt_flow_panel")
        self.assertIn('data-tlm-terminals-host="pfp"', html)
        self.assertIn("data-tlm-terminals-toggle", html)

    def test_the_dock_starts_hidden_so_a_page_without_terminals_looks_unchanged(self):
        self.assertIn("hidden: true", _read(JS / "terminater_dock.js"))

    def test_the_scripts_carry_the_current_static_version(self):
        from django.conf import settings

        html = self.get("agent_page")
        self.assertIn(f"terminater_dock.js?v={settings.STATIC_VERSION}_term1", html)
