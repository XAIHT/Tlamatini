# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Every Windows `.cmd` / `.exe` spawn scenario Tlamatini has to survive.

This suite exists because the SAME bug class bit three separate subsystems, and
each time it looked like a different bug:

* **External MCPs, 2026-09-07** — `deepwebresearch` died with
  ``[WinError 2] The system cannot find the file specified``.
  `external_mcp_manager._resolve_argv` HAD a correct `.cmd`→COMSPEC fallback,
  but `runtime_provisioner.resolve_spawn` returned a NON-EMPTY pass-through
  argv for every command outside `MANAGED_TOOLS`, and the caller does
  ``if argv: return argv`` — so that fallback was unreachable dead code.
* **ACPX** — a `.cmd` command was run with ``shell=True``…
* **The stdio MCP server** — …or spawned bare, hanging until its timeout.

And the "obvious" repair is itself a trap: **cmd.exe stops reading its command
line at the first newline**, so a 2,205-character multi-line ACPX prompt reached
the child as 40 characters, silently. The shell is a LAST resort, never the
default; the real answer is to rewrite an npm/pnpm shim to the `node.exe
<script.js>` it actually launches.

The tests below pin all of it: resolution order, both shim dialects, every
fail-open path, the exact `deepwebresearch` regression, and the source-level
contract that there is only ONE definition of this logic in the tree.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent import win_shim

WINDOWS_ONLY = unittest.skipUnless(os.name == "nt", "Windows spawn semantics")

PCT = chr(37)

#: A real npm shim ends in: "%_prog%"  "%dp0%\node_modules\<pkg>\bin\<tool>.js" %*
NPM_SHIM = (
    "@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=@@~dp0\r\nEXIT /b\r\n:start\r\n"
    "SETLOCAL\r\nCALL :find_dp0\r\n\r\n"
    'IF EXIST "@@dp0@@\\node.exe" (\r\n'
    '  SET "_prog=@@dp0@@\\node.exe"\r\n'
    ") ELSE (\r\n"
    '  SET "_prog=node"\r\n'
    ")\r\n\r\n"
    'endLocal & goto #_undefined_# 2>NUL || title @@COMSPEC@@ & "@@_prog@@"  '
    '"@@dp0@@\\{script}" @@*\r\n'
).replace("@@", PCT)

#: A real pnpm shim uses %~dp0 (no trailing %) and a ..\global\<hash>\ path.
PNPM_SHIM = (
    "@SETLOCAL\r\n"
    '@IF EXIST "@@~dp0\\node.exe" (\r\n'
    '  "@@~dp0\\node.exe"  "@@~dp0\\{script}" @@*\r\n'
    ") ELSE (\r\n"
    "  @SET PATHEXT=@@PATHEXT:;.JS;=;@@\r\n"
    '  node  "@@~dp0\\{script}" @@*\r\n'
    ")\r\n"
).replace("@@", PCT)


class _Fixture:
    """A throwaway directory that can hold fake executables and shims."""

    def __init__(self, root: str) -> None:
        self.root = root

    def binary(self, name: str) -> str:
        path = os.path.join(self.root, name)
        with open(path, "wb") as handle:
            handle.write(b"MZ")          # enough to look like a PE file
        return path

    def script(self, rel: str) -> str:
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("// payload\n")
        return path

    def shim(self, name: str, script_rel: str, template: str = NPM_SHIM) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(template.replace("{script}", script_rel.replace("/", "\\")))
        return path

    def raw(self, name: str, body: str) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def on_path(self):
        """Context manager putting this directory FIRST on PATH."""
        return mock.patch.dict(
            os.environ,
            {"PATH": self.root + os.pathsep + os.environ.get("PATH", ""),
             "PATHEXT": ".COM;.EXE;.BAT;.CMD"},
        )


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = _Fixture(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


# ══════════════════════════════════════════════════════════════════════
#  1. Resolution order — a real executable ALWAYS beats a batch shim
# ══════════════════════════════════════════════════════════════════════
class ResolutionOrderTests(_Base):

    @WINDOWS_ONLY
    def test_bare_name_resolves_to_a_real_exe_without_the_shell(self) -> None:
        self.fx.binary("tool.exe")
        with self.fx.on_path():
            prefix, needs_shell, _ = win_shim.resolve_argv_prefix("tool")
        self.assertFalse(needs_shell)
        self.assertTrue(prefix[0].lower().endswith("tool.exe"))

    @WINDOWS_ONLY
    def test_exe_wins_over_a_sibling_cmd_of_the_same_name(self) -> None:
        """The old _which tried .cmd BEFORE .exe, so `claude` took the shell."""
        self.fx.binary("tool.exe")
        self.fx.script("node_modules/pkg/bin/tool.js")
        self.fx.shim("tool.cmd", "node_modules/pkg/bin/tool.js")
        with self.fx.on_path():
            prefix, needs_shell, _ = win_shim.resolve_argv_prefix("tool")
        self.assertFalse(needs_shell)
        self.assertTrue(prefix[0].lower().endswith("tool.exe"),
                        "a real .exe must never be passed over for a shim")

    def test_exe_is_first_in_the_search_order(self) -> None:
        self.assertEqual(win_shim.WIN_EXTS[0], ".exe")

    @WINDOWS_ONLY
    def test_a_command_that_is_not_installed_is_returned_UNCHANGED(self) -> None:
        """Never invent a resolution -- the caller's own error must stay truthful."""
        with self.fx.on_path():
            prefix, needs_shell, why = win_shim.resolve_argv_prefix(
                "definitely-not-installed-xyz")
        self.assertEqual(prefix, ["definitely-not-installed-xyz"])
        self.assertFalse(needs_shell)
        self.assertIn("not found", why)

    def test_empty_command(self) -> None:
        self.assertEqual(win_shim.resolve_argv_prefix("")[0], [])
        self.assertEqual(win_shim.resolve_argv_prefix(None)[0], [])


# ══════════════════════════════════════════════════════════════════════
#  2. De-shimming — npm AND pnpm, and every refusal case
# ══════════════════════════════════════════════════════════════════════
class DeShimTests(_Base):

    @WINDOWS_ONLY
    def test_npm_shim_is_rewritten_to_node_plus_script(self) -> None:
        node = self.fx.binary("node.exe")
        script = self.fx.script("node_modules/@scope/pkg/bin/tool.js")
        shim = self.fx.shim("tool.cmd", "node_modules/@scope/pkg/bin/tool.js")
        direct = win_shim.deshim(shim)
        self.assertIsNotNone(direct)
        self.assertEqual(os.path.normcase(direct[0]), os.path.normcase(node))
        self.assertEqual(os.path.normcase(direct[1]), os.path.normcase(script))

    @WINDOWS_ONLY
    def test_pnpm_shim_dialect_is_also_recognised(self) -> None:
        """pnpm writes %~dp0, npm writes %dp0% -- both must work."""
        self.fx.binary("node.exe")
        self.fx.script("global/v11/hash/node_modules/pkg/bundle/tool.js")
        shim = self.fx.shim("tool.cmd",
                            "global/v11/hash/node_modules/pkg/bundle/tool.js",
                            template=PNPM_SHIM)
        direct = win_shim.deshim(shim)
        self.assertIsNotNone(direct)
        self.assertTrue(direct[1].endswith("tool.js"))

    @WINDOWS_ONLY
    def test_mjs_and_cjs_payloads_are_recognised(self) -> None:
        for ext in ("mjs", "cjs"):
            with self.subTest(ext=ext):
                with tempfile.TemporaryDirectory() as root:
                    fx = _Fixture(root)
                    fx.binary("node.exe")
                    fx.script("node_modules/pkg/bin/tool." + ext)
                    shim = fx.shim("tool.cmd", "node_modules/pkg/bin/tool." + ext)
                    self.assertIsNotNone(win_shim.deshim(shim))

    @WINDOWS_ONLY
    def test_node_next_to_the_shim_is_preferred_over_PATH(self) -> None:
        node = self.fx.binary("node.exe")
        self.fx.script("node_modules/pkg/bin/tool.js")
        shim = self.fx.shim("tool.cmd", "node_modules/pkg/bin/tool.js")
        direct = win_shim.deshim(shim)
        self.assertEqual(os.path.normcase(direct[0]), os.path.normcase(node))

    def test_a_shim_whose_script_is_MISSING_is_never_rewritten(self) -> None:
        """A confident wrong argv is worse than an honest 'not found'."""
        self.fx.binary("node.exe")
        shim = self.fx.shim("tool.cmd", "node_modules/pkg/bin/gone.js")
        self.assertIsNone(win_shim.deshim(shim))

    def test_an_unrecognised_shim_shape_is_not_rewritten(self) -> None:
        shim = self.fx.raw("weird.cmd", "@echo off\r\necho nothing here\r\n")
        self.assertIsNone(win_shim.deshim(shim))

    def test_deshim_of_a_missing_file_returns_none_and_does_not_raise(self) -> None:
        self.assertIsNone(win_shim.deshim(os.path.join(self.fx.root, "nope.cmd")))

    @WINDOWS_ONLY
    def test_unrewritable_shim_asks_for_the_shell_as_a_LAST_resort(self) -> None:
        shim = self.fx.raw("weird.cmd", "@echo off\r\necho nothing here\r\n")
        prefix, needs_shell, why = win_shim.resolve_argv_prefix(shim)
        self.assertTrue(needs_shell)
        self.assertEqual(prefix, [shim])
        self.assertIn("shell", why)


# ══════════════════════════════════════════════════════════════════════
#  3. Explicit paths
# ══════════════════════════════════════════════════════════════════════
class ExplicitPathTests(_Base):

    @WINDOWS_ONLY
    def test_absolute_path_to_an_exe_is_used_as_is(self) -> None:
        exe = self.fx.binary("real.exe")
        prefix, needs_shell, _ = win_shim.resolve_argv_prefix(exe)
        self.assertEqual(prefix, [exe])
        self.assertFalse(needs_shell)

    @WINDOWS_ONLY
    def test_absolute_path_to_a_cmd_is_de_shimmed(self) -> None:
        self.fx.binary("node.exe")
        self.fx.script("node_modules/pkg/bin/tool.js")
        shim = self.fx.shim("tool.cmd", "node_modules/pkg/bin/tool.js")
        prefix, needs_shell, _ = win_shim.resolve_argv_prefix(shim)
        self.assertFalse(needs_shell)
        self.assertEqual(len(prefix), 2)
        self.assertTrue(prefix[1].endswith("tool.js"))

    @WINDOWS_ONLY
    def test_absolute_path_that_does_not_exist_is_handed_back(self) -> None:
        ghost = os.path.join(self.fx.root, "ghost.exe")
        prefix, _needs_shell, why = win_shim.resolve_argv_prefix(ghost)
        self.assertEqual(prefix, [ghost])
        self.assertIn("does not exist", why)


# ══════════════════════════════════════════════════════════════════════
#  4. THE REGRESSION — runtime_provisioner.resolve_spawn
# ══════════════════════════════════════════════════════════════════════
class ResolveSpawnUnmanagedCommandTests(_Base):
    """`deepwebresearch`, 2026-09-07: [WinError 2] on every npm/pnpm MCP server."""

    @WINDOWS_ONLY
    def test_an_unmanaged_cmd_backed_command_is_DE_SHIMMED_not_passed_through(self) -> None:
        from agent import runtime_provisioner
        self.fx.binary("node.exe")
        self.fx.script("node_modules/mcp-deepwebresearch/dist/index.js")
        self.fx.shim("mcp-deepwebresearch.cmd",
                     "node_modules/mcp-deepwebresearch/dist/index.js")
        with self.fx.on_path():
            argv, _note = runtime_provisioner.resolve_spawn("mcp-deepwebresearch", [])
        self.assertNotEqual(argv, ["mcp-deepwebresearch"],
                            "the bare pass-through is what caused [WinError 2]")
        self.assertTrue(argv[0].lower().endswith("node.exe"))
        self.assertTrue(argv[1].endswith("index.js"))

    @WINDOWS_ONLY
    def test_unmanaged_command_keeps_its_arguments_in_order(self) -> None:
        from agent import runtime_provisioner
        self.fx.binary("node.exe")
        self.fx.script("node_modules/srv/dist/index.js")
        self.fx.shim("srv.cmd", "node_modules/srv/dist/index.js")
        with self.fx.on_path():
            argv, _ = runtime_provisioner.resolve_spawn("srv", ["--port", "9000"])
        self.assertEqual(argv[-2:], ["--port", "9000"])

    @WINDOWS_ONLY
    def test_unmanaged_real_exe_resolves_to_its_full_path(self) -> None:
        from agent import runtime_provisioner
        exe = self.fx.binary("someserver.exe")
        with self.fx.on_path():
            argv, _ = runtime_provisioner.resolve_spawn("someserver", [])
        self.assertEqual(os.path.normcase(argv[0]), os.path.normcase(exe))

    def test_unmanaged_command_not_installed_is_returned_UNCHANGED(self) -> None:
        """So the caller reports 'not found', not a silent substitution."""
        from agent import runtime_provisioner
        argv, _ = runtime_provisioner.resolve_spawn("no-such-tool-xyz", ["a"])
        self.assertEqual(argv, ["no-such-tool-xyz", "a"])

    def test_resolve_spawn_never_raises(self) -> None:
        from agent import runtime_provisioner
        for command, args in ((None, None), ("", []), (123, ["x"]),
                              ("tool", None)):
            with self.subTest(command=command):
                argv, note = runtime_provisioner.resolve_spawn(command, args)
                self.assertIsInstance(argv, list)
                self.assertIsInstance(note, str)

    @WINDOWS_ONLY
    def test_a_managed_tool_still_takes_its_own_path(self) -> None:
        """npx must keep going through the private-node rewrite, not this branch."""
        from agent import runtime_provisioner
        argv, _note = runtime_provisioner.resolve_spawn("npx", ["-y", "pkg"])
        self.assertEqual(argv[-2:], ["-y", "pkg"])
        self.assertTrue(argv)


# ══════════════════════════════════════════════════════════════════════
#  5. The dead code is reachable again — external_mcp_manager
# ══════════════════════════════════════════════════════════════════════
class ExternalMcpArgvTests(_Base):

    @WINDOWS_ONLY
    def test_a_cmd_backed_server_never_spawns_as_a_bare_name(self) -> None:
        from agent import external_mcp_manager
        self.fx.binary("node.exe")
        self.fx.script("node_modules/srv/dist/index.js")
        self.fx.shim("srv.cmd", "node_modules/srv/dist/index.js")

        spec = external_mcp_manager.ExternalMcpServer(
            key="srv", command="srv", args=[],
        ) if hasattr(external_mcp_manager, "ExternalMcpServer") else None
        if spec is None:                     # shape changed -- assert via provisioner
            from agent import runtime_provisioner
            with self.fx.on_path():
                argv, _ = runtime_provisioner.resolve_spawn("srv", [])
            self.assertNotEqual(argv, ["srv"])
            return
        with self.fx.on_path():
            argv = spec._resolve_argv()
        self.assertNotEqual(argv, ["srv"],
                            "[WinError 2] comes from spawning the bare shim name")


# ══════════════════════════════════════════════════════════════════════
#  6. Source contract — ONE definition, no drifting copies
# ══════════════════════════════════════════════════════════════════════
class SingleDefinitionContractTests(unittest.TestCase):

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def test_only_win_shim_parses_a_shim_script_path(self) -> None:
        """A second copy of this regex would drift and spawn the wrong thing."""
        root = self._repo_root()
        pattern = re.compile(r"dp0.{0,12}\\\\\+\(\[\^")
        offenders = []
        for path in list(root.glob("Tlamatini/agent/**/*.py")) + list(root.glob("*.py")):
            if path.name in ("win_shim.py", "test_win_shim.py"):
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if pattern.search(body):
                offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [],
                         "shim parsing must live only in agent/win_shim.py")

    def test_acpx_windows_spawn_delegates_instead_of_copying(self) -> None:
        body = (self._repo_root()
                / "Tlamatini/agent/acpx/windows_spawn.py").read_text(encoding="utf-8")
        self.assertIn("win_shim", body)
        self.assertIn("_win_shim.deshim", body)

    def test_runtime_provisioner_no_longer_passes_unmanaged_commands_through(self) -> None:
        body = (self._repo_root()
                / "Tlamatini/agent/runtime_provisioner.py").read_text(encoding="utf-8")
        self.assertNotIn(
            'if tool not in MANAGED_TOOLS:\n            return [raw,',
            body.replace("\r\n", "\n"),
            "the bare pass-through is the deepwebresearch bug; it must not return")
        self.assertIn("resolve_argv_prefix", body)

    def test_win_shim_imports_nothing_from_agent(self) -> None:
        """It must load from the Django app, a pool agent, and the stdio server."""
        body = (self._repo_root()
                / "Tlamatini/agent/win_shim.py").read_text(encoding="utf-8")
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                self.assertNotIn("agent", stripped.split("#")[0],
                                 "win_shim must stay stdlib-only: " + stripped)


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
