"""Executer must report its forked window TRUTHFULLY (2026-10-09).

On Windows 11 a new console is handed to Windows Terminal. What reaches the
screen is a Windows Terminal window (class CASCADIA_HOSTING_WINDOW_CLASS), and
the console host keeps a zero-size helper window (class PseudoConsoleWindow)
that is never meant to be seen.

Executer's window check used to count that helper as "the console". When the
helper stayed invisible it logged "could NOT be shown - it is on another window
station/desktop", while the real window was on screen the whole time. Measured
the same day through the session MCP host: the agents run on WinSta0 Default
and the window appears.

Source-level on purpose: importing executer.py changes the working directory
and truncates its log, so the pure helpers are lifted out of the source.
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXECUTER = os.path.join(HERE, "agents", "executer", "executer.py")


def _source():
    with open(EXECUTER, "r", encoding="utf-8") as fh:
        return fh.read()


def _lift(names):
    """Compile only the named top-level functions/assignments into a namespace."""
    tree = ast.parse(_source())
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(t in names for t in targets):
                keep.append(node)
    module = ast.Module(body=keep, type_ignores=[])
    namespace = {}
    exec(compile(module, EXECUTER, "exec"), namespace)
    return namespace


class DescribeWindowCheckTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.describe = staticmethod(_lift({"_describe_window_check"})["_describe_window_check"])

    def test_handoff_to_windows_terminal_is_not_reported_as_hidden(self):
        level, text = self.describe({"handed_off": 1})
        self.assertEqual(level, "info")
        self.assertIn("Windows Terminal", text)
        self.assertNotIn("window station", text)
        self.assertNotIn("could NOT be shown", text)

    def test_a_real_window_on_screen_is_reported_on_screen(self):
        level, text = self.describe({"appeared": 1, "already_visible": 1,
                                     "still_visible": 1, "handed_off": 1})
        self.assertEqual(level, "info")
        self.assertIn("on screen", text)

    def test_a_revealed_window_says_so(self):
        level, text = self.describe({"appeared": 1, "revealed": 1, "still_visible": 1})
        self.assertEqual(level, "info")
        self.assertIn("REVEALED", text)

    def test_a_real_window_that_stayed_hidden_is_a_warning(self):
        level, text = self.describe({"appeared": 1})
        self.assertEqual(level, "warning")
        self.assertIn("stayed hidden", text)

    def test_nothing_found_is_a_warning_without_inventing_a_cause(self):
        level, text = self.describe({})
        self.assertEqual(level, "warning")
        self.assertIn("IS running", text)
        self.assertNotIn("another window station", text)

    def test_never_raises_on_odd_input(self):
        for odd in (None, "text", 7, {"still_visible": "x"}, {"handed_off": None}):
            with self.subTest(odd=odd):
                level, text = self.describe(odd)
                self.assertIn(level, ("info", "warning"))
                self.assertTrue(text)


class WindowCheckSourceTests(unittest.TestCase):

    def test_the_handoff_helper_is_not_a_real_window(self):
        ns = _lift({"_REAL_CONSOLE_WINDOW_CLASSES", "_HANDOFF_HELPER_CLASS"})
        self.assertEqual(ns["_HANDOFF_HELPER_CLASS"], "PseudoConsoleWindow")
        self.assertNotIn("PseudoConsoleWindow", ns["_REAL_CONSOLE_WINDOW_CLASSES"])
        self.assertIn("CASCADIA_HOSTING_WINDOW_CLASS", ns["_REAL_CONSOLE_WINDOW_CLASSES"])
        self.assertIn("ConsoleWindowClass", ns["_REAL_CONSOLE_WINDOW_CLASSES"])

    def test_only_real_windows_are_counted_as_still_visible(self):
        tree = ast.parse(_source())
        func = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_force_show_new_consoles")
        loops = [n for n in ast.walk(func)
                 if isinstance(n, ast.For) and isinstance(n.iter, ast.Name)]
        self.assertIn("real", [loop.iter.id for loop in loops],
                      "the final visibility count must iterate the REAL windows only")
        self.assertNotIn("seen", [loop.iter.id for loop in loops])

    def test_the_false_window_station_claim_is_gone(self):
        src = _source()
        self.assertNotIn("is on another window station", src)
        self.assertNotIn("launched by a host whose desktop is not the", src)

    def test_both_launch_paths_log_what_they_found(self):
        src = _source()
        self.assertIn("_report_forked_window(consoles_before, timeout_seconds=6.0)", src)
        self.assertIn("target=_report_forked_window,", src)


if __name__ == "__main__":
    unittest.main()
