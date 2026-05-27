"""Automated tests for the STM32er workflow agent and its surrounding infrastructure.

STM32er bridges Tlamatini to the **STM32 Template Project MCP server**
(https://github.com/XAIHT/STM32TemplateProjectMCP). It is a standalone pool agent
under ``agent/agents/stm32er/`` that runs as a separate Python subprocess and
drives the MCP **stdio** server (newline-delimited JSON-RPC) using ONLY the
stdlib (``subprocess`` + ``json`` + ``threading``) — exactly like Kalier /
ACPXer. Like the other pool-agent test modules it is loaded through
``importlib.util.spec_from_file_location`` with a cwd save/restore so its
module-level ``os.chdir`` + ``open(LOG_FILE_PATH)`` + ``logging.basicConfig`` side
effects land in its own directory and do not leak handlers into the test process.

The agent itself does NOT compile anything — the bundled arm-none-eabi toolchain
lives inside the MCP **server**. STM32er's job is to (a) build the correct JSON
``arguments`` for each of the 23 MCP tools, (b) perform the MCP initialize
handshake, (c) call ONE tool over ``tools/call``, (d) faithfully extract the
server's result (toolchain paths / build stdout / artifact paths / success), and
(e) ALWAYS trigger downstream regardless of success. These tests prove all five —
including an END-TO-END run of the REAL ``_McpStdioClient`` against a tiny FAKE
STM32 MCP stdio server (written to a temp file, spawned as a real subprocess)
that mimics the upstream server's responses for:

  • discover_toolchain_tool  -> "finding the correct compiler" (arm-none-eabi-gcc)
  • build                    -> compiling + LINKING the .elf
  • list_artifacts           -> .elf / .hex / .bin generation
  • build_and_flash / flash  -> upload over ST-LINK/SWD
  • a failing build          -> a compile error is ROUTABLE evidence, not a crash

No real STM32 hardware, no STM32CubeIDE, and no ``mcp`` package are required: the
fake server is pure stdlib and answers the JSON-RPC protocol directly, so the
exact code path the real server would exercise in STM32er is covered
deterministically.

Covers:
- _DIRECT_TOOLS / _COMPOSITE_ACTIONS / _ALL_ACTIONS: all 23 + 2 actions present
- _build_arguments: per-action argument shape (only declared keys), int/bool/float
  coercion (jobs, clean_first, overwrite, baud, width, ...), optional-key omission
- _subject_for / _cfg / _as_int / _as_float / _as_bool helpers
- _McpStdioClient._parse_call_result: text-JSON content, structuredContent mirror,
  {'result': ...} unwrap, isError -> ok=False, malformed result
- _tool_ok: explicit ok, no-ok-key (toolchain/get_config), error/_rpc_error
- END-TO-END via the real client + fake stdio server: handshake, toolchain
  discovery, build->elf, list_artifacts->hex/bin, flash, build-failure routability,
  banner/notification swallowing, initialize-error, timeout backstop, early exit
- _run_action routing (direct, serial_session, live_monitor composites, unknown)
- _emit_section: single atomic INI_SECTION_STM32ER block
- main() end-stage: section always emitted + target_agents always started, on a
  real build run AND on the server-not-found / unknown-action error paths
- Registry integration: ChatWrappedAgentSpec, Exec Report row, get_mcp_tools bind,
  agent contract + parametrizer fields, name normalization, URL route, capability
  hints, CSS gradient (unique), config.yaml defaults, config.json globals + seed
- Parametrizer round-trip: SECTION_AGENT_TYPES, OUTPUT_PARSERS parse, views reg
- Migration presence: Agent row (0101) + Tool row (0102)
"""

import importlib.util
import inspect
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from functools import lru_cache
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, TestCase


# ---------------------------------------------------------------------------
# Module loader — exec the pool-agent script with cwd + handler save/restore
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_stm32er_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'stm32er', 'stm32er.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_stm32er_module_for_tests', module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load STM32er module from {module_path}')

    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    current_dir = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(current_dir)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


class _LogCapture:
    """Context manager that captures root-logger messages into a list."""

    def __init__(self):
        self.records = []

    def __enter__(self):
        outer = self

        class _H(logging.Handler):
            def emit(self, record):
                outer.records.append(record.getMessage())

        self._handler = _H()
        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(self, *_a):
        logging.getLogger().removeHandler(self._handler)
        return False


# A tiny FAKE STM32 MCP stdio server. Pure stdlib; answers the MCP JSON-RPC
# protocol the real ``mcp/stm32_mcp_server.py`` speaks. Written verbatim to a
# temp file and spawned by the REAL ``_McpStdioClient`` so the protocol path is
# genuinely exercised. RAW string: ``\n`` survives as backslash-n into the file
# and is interpreted as a newline by the fake server's own Python.
_FAKE_STM32_MCP_SERVER = r'''
import sys, json, os, time

def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

# "Finding the correct compiler" — the discovered-toolchain result, matching the
# REAL server's Toolchain dataclass field names (gcc_bin / make_bin / programmer_cli).
TOOLCHAIN = {
    "ide_root": "C:/ST/STM32CubeIDE",
    "gcc_bin": "C:/ST/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32/tools/bin/arm-none-eabi-gcc.exe",
    "make_bin": "C:/ST/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.make/tools/bin/make.exe",
    "cmake_bin": "C:/ST/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.cmake/tools/bin/cmake.exe",
    "ninja_bin": "C:/ST/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.ninja/tools/bin/ninja.exe",
    "programmer_cli": "C:/ST/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer/tools/bin/STM32_Programmer_CLI.exe",
    "openocd_bin": "C:/ST/STM32CubeIDE/plugins/openocd/tools/bin/openocd.exe",
}

# A successful compile + LINK + objcopy producing .elf/.hex/.bin.
_BUILD_STDOUT = "\n".join([
    "arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -c Core/Src/main.c -o build/Core/Src/main.o",
    "arm-none-eabi-gcc -mcpu=cortex-m4 -T STM32F407VGTX_FLASH.ld -Wl,-Map=build/firmware.map -o build/firmware.elf",
    "arm-none-eabi-objcopy -O ihex build/firmware.elf build/firmware.hex",
    "arm-none-eabi-objcopy -O binary -S build/firmware.elf build/firmware.bin",
    "   text    data     bss     dec     hex filename",
    "   9184      20    1568   10772    2a14 build/firmware.elf",
    "Built target firmware.elf",
])

_BUILD_FAIL_STDERR = "\n".join([
    "Core/Src/main.c:42:5: error: 'GPIOX' undeclared (first use in this function)",
    "make: *** [build/Core/Src/main.o] Error 1",
])

def _tool_response(name):
    if name == "discover_toolchain_tool":
        return dict(TOOLCHAIN), False          # no "ok" key -> success-by-absence
    if name == "get_config":
        return {"ok": True, "toolchain_ok": True,
                "discovered_toolchain": dict(TOOLCHAIN),
                "config": {"mcu": {"device": "STM32F407VG", "cpu_define": "STM32F407xx",
                                   "core": "cortex-m4"}}}, False
    if name == "create_project":
        return {"ok": True, "project_dir": "C:/robot/fw/leg_ctrl", "created": True}, False
    if name == "build":
        if os.environ.get("STM32_FAKE_BUILD_OK", "1") == "0":
            return {"ok": False, "returncode": 2,
                    "stdout": "arm-none-eabi-gcc -c Core/Src/main.c",
                    "stderr": _BUILD_FAIL_STDERR,
                    "project_dir": "C:/robot/fw/leg_ctrl", "stage": "build"}, False
        return {"ok": True, "returncode": 0, "stdout": _BUILD_STDOUT, "stderr": "",
                "project_dir": "C:/robot/fw/leg_ctrl", "elf": "build/firmware.elf",
                "stage": "build"}, False
    if name == "list_artifacts":
        return {"ok": True, "project_dir": "C:/robot/fw/leg_ctrl",
                "artifacts": {"elf": "build/firmware.elf", "hex": "build/firmware.hex",
                              "bin": "build/firmware.bin", "map": "build/firmware.map"}}, False
    if name == "build_and_flash":
        return {"ok": True, "returncode": 0,
                "stdout": _BUILD_STDOUT + "\nDownload verified successfully",
                "stderr": "", "project_dir": "C:/robot/fw/leg_ctrl", "stage": "flash"}, False
    if name == "flash":
        return {"ok": True, "returncode": 0,
                "stdout": "ST-LINK SN: 0667FF...\nFlash programming complete.\nDownload verified successfully",
                "stderr": "", "project_dir": "C:/robot/fw/leg_ctrl", "stage": "flash"}, False
    return {"ok": False, "error": "unknown tool: " + str(name)}, True

def main():
    # FastMCP / its deps sometimes print a non-JSON banner first; the client MUST
    # ignore stray prints, so emit one to prove it.
    sys.stdout.write("FAKE STM32 MCP server starting (this banner is NOT json-rpc)\n")
    sys.stdout.flush()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            if os.environ.get("STM32_FAKE_INIT_ERROR") == "1":
                _send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32603, "message": "init boom"}})
                continue
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-stm32-mcp", "version": "0.0.1"}}})
            continue
        if method == "notifications/initialized":
            if os.environ.get("STM32_FAKE_EXIT_EARLY") == "1":
                sys.exit(0)
            # Unrelated notification -> the client must swallow it while waiting
            # for the real tool response.
            _send({"jsonrpc": "2.0", "method": "notifications/message",
                   "params": {"level": "info", "data": "server ready"}})
            continue
        if method == "tools/call":
            if os.environ.get("STM32_FAKE_HANG") == "1":
                while True:
                    time.sleep(0.2)
            params = msg.get("params") or {}
            payload, is_error = _tool_response(params.get("name"))
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "isError": is_error}})
            continue
        if mid is not None:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": "method not found"}})

main()
'''


# ---------------------------------------------------------------------------
# Action contract — all 23 MCP tools + 2 composites
# ---------------------------------------------------------------------------


class ActionContractTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_all_23_direct_tools_present(self):
        expected = {
            'get_config', 'discover_toolchain_tool',
            'create_project', 'write_source', 'read_source', 'list_sources', 'clean',
            'build', 'list_artifacts', 'flash', 'build_and_flash', 'erase', 'reset',
            'serial_list_ports', 'serial_connect', 'serial_send', 'serial_read',
            'serial_disconnect',
            'read_memory', 'write_memory',
            'live_memory_start', 'live_memory_read', 'live_memory_stop',
        }
        self.assertEqual(self.s._DIRECT_TOOLS, expected)
        self.assertEqual(len(self.s._DIRECT_TOOLS), 23)

    def test_two_composite_actions(self):
        self.assertEqual(self.s._COMPOSITE_ACTIONS, {'serial_session', 'live_monitor'})

    def test_all_actions_is_union(self):
        self.assertEqual(
            self.s._ALL_ACTIONS,
            self.s._DIRECT_TOOLS | self.s._COMPOSITE_ACTIONS | self.s._META_ACTIONS,
        )
        self.assertEqual(len(self.s._ALL_ACTIONS), 27)

    def test_meta_actions_are_bootstrap_and_validate(self):
        self.assertEqual(self.s._META_ACTIONS, {'bootstrap', 'validate'})
        for meta in ('bootstrap', 'validate'):
            self.assertIn(meta, self.s._ALL_ACTIONS)
            # Meta actions are handled by STM32er itself — NOT MCP tool calls.
            self.assertNotIn(meta, self.s._DIRECT_TOOLS)
            self.assertNotIn(meta, self.s._COMPOSITE_ACTIONS)

    def test_action_classification_for_safety_gate(self):
        # Compile-only must NOT require hardware; hardware actions must.
        self.assertIn('build', self.s._BUILD_ACTIONS)
        self.assertNotIn('build', self.s._HARDWARE_ACTIONS)
        for hw in ('flash', 'erase', 'reset', 'serial_session', 'read_memory', 'live_monitor'):
            self.assertIn(hw, self.s._HARDWARE_ACTIONS)
        # build_and_flash is BOTH (it builds AND flashes).
        self.assertIn('build_and_flash', self.s._BUILD_ACTIONS)
        self.assertIn('build_and_flash', self.s._HARDWARE_ACTIONS)
        # Pure compile actions are not hardware actions.
        for compile_only in ('build', 'list_artifacts', 'clean', 'create_project',
                             'write_source', 'get_config', 'discover_toolchain_tool'):
            self.assertNotIn(compile_only, self.s._HARDWARE_ACTIONS)

    def test_build_pipeline_actions_are_direct_tools(self):
        # The compiler-discovery / compile / link / artifact / flash surface the
        # user explicitly asked about.
        for action in ('discover_toolchain_tool', 'build', 'list_artifacts',
                       'flash', 'build_and_flash'):
            self.assertIn(action, self.s._DIRECT_TOOLS)


# ---------------------------------------------------------------------------
# _build_arguments — per-action JSON arguments (build pipeline emphasis)
# ---------------------------------------------------------------------------


class BuildArgumentsTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_get_config_takes_no_args(self):
        self.assertEqual(self.s._build_arguments('get_config', {}), {})

    def test_discover_toolchain_empty_when_no_ide_root(self):
        self.assertEqual(self.s._build_arguments('discover_toolchain_tool', {}), {})

    def test_discover_toolchain_passes_ide_root_when_set(self):
        args = self.s._build_arguments(
            'discover_toolchain_tool', {'discover_ide_root': 'C:/ST/STM32CubeIDE'})
        self.assertEqual(args, {'ide_root': 'C:/ST/STM32CubeIDE'})

    def test_create_project_shape_and_bool_coercion(self):
        args = self.s._build_arguments('create_project', {
            'name': 'leg_ctrl', 'dest_parent': 'C:/robot/fw', 'overwrite': 'true',
        })
        self.assertEqual(args['name'], 'leg_ctrl')
        self.assertEqual(args['dest_parent'], 'C:/robot/fw')
        self.assertIs(args['overwrite'], True)

    def test_build_arguments_full_shape_and_coercion(self):
        # The crux: build must carry project_dir + system + an INT jobs + a BOOL
        # clean_first so FastMCP schema validation accepts it and the server can
        # invoke the compiler/linker correctly.
        args = self.s._build_arguments('build', {
            'project_dir': 'C:/robot/fw/leg_ctrl', 'system': 'make',
            'jobs': '12', 'clean_first': 'true',
        })
        self.assertEqual(args, {
            'project_dir': 'C:/robot/fw/leg_ctrl', 'system': 'make',
            'jobs': 12, 'clean_first': True,
        })
        self.assertIsInstance(args['jobs'], int)
        self.assertIsInstance(args['clean_first'], bool)

    def test_build_defaults_system_make_and_jobs_8(self):
        args = self.s._build_arguments('build', {'project_dir': 'C:/p'})
        self.assertEqual(args['system'], 'make')
        self.assertEqual(args['jobs'], 8)
        self.assertIs(args['clean_first'], False)

    def test_build_accepts_cmake_system(self):
        args = self.s._build_arguments('build', {'project_dir': 'C:/p', 'system': 'cmake'})
        self.assertEqual(args['system'], 'cmake')

    def test_list_artifacts_shape(self):
        args = self.s._build_arguments('list_artifacts',
                                       {'project_dir': 'C:/p', 'system': 'make'})
        self.assertEqual(args, {'project_dir': 'C:/p', 'system': 'make'})

    def test_flash_carries_binary_kind(self):
        args = self.s._build_arguments('flash',
                                       {'project_dir': 'C:/p', 'binary': 'hex'})
        self.assertEqual(args['binary'], 'hex')
        self.assertEqual(args['system'], 'make')

    def test_flash_defaults_binary_bin(self):
        args = self.s._build_arguments('flash', {'project_dir': 'C:/p'})
        self.assertEqual(args['binary'], 'bin')

    def test_build_and_flash_shape(self):
        args = self.s._build_arguments('build_and_flash',
                                       {'project_dir': 'C:/p', 'jobs': '4'})
        self.assertEqual(args, {'project_dir': 'C:/p', 'system': 'make', 'jobs': 4})

    def test_erase_and_reset_take_only_project_dir(self):
        self.assertEqual(self.s._build_arguments('erase', {'project_dir': 'C:/p'}),
                         {'project_dir': 'C:/p'})
        self.assertEqual(self.s._build_arguments('reset', {'project_dir': 'C:/p'}),
                         {'project_dir': 'C:/p'})

    def test_write_source_shape(self):
        args = self.s._build_arguments('write_source', {
            'project_dir': 'C:/p', 'rel_path': 'Core/Src/main.c', 'content': 'int main(){}',
        })
        self.assertEqual(args, {'project_dir': 'C:/p', 'rel_path': 'Core/Src/main.c',
                                'content': 'int main(){}'})

    def test_serial_connect_baud_coercion(self):
        args = self.s._build_arguments('serial_connect', {'port': 'COM7', 'baud': '115200'})
        self.assertEqual(args, {'port': 'COM7', 'baud': 115200})
        self.assertIsInstance(args['baud'], int)

    def test_serial_send_optional_line_ending_omitted(self):
        args = self.s._build_arguments('serial_send', {'port': 'COM7', 'data': 'PING'})
        self.assertNotIn('line_ending', args)
        self.assertEqual(args['port'], 'COM7')
        self.assertEqual(args['data'], 'PING')
        self.assertIs(args['read_response'], True)

    def test_serial_send_optional_line_ending_included(self):
        args = self.s._build_arguments('serial_send',
                                       {'port': 'COM7', 'data': 'PING', 'line_ending': 'crlf'})
        self.assertEqual(args['line_ending'], 'crlf')

    def test_read_memory_includes_only_set_locators(self):
        args = self.s._build_arguments('read_memory', {
            'symbol': 'g_blink_count', 'project_dir': 'C:/p', 'count': '4', 'width': '32',
        })
        self.assertEqual(args['symbol'], 'g_blink_count')
        self.assertEqual(args['project_dir'], 'C:/p')
        self.assertEqual(args['count'], 4)
        self.assertEqual(args['width'], 32)
        self.assertNotIn('address', args)
        self.assertNotIn('elf', args)

    def test_write_memory_carries_value(self):
        args = self.s._build_arguments('write_memory',
                                       {'value': '0xFF', 'address': '0x20000000', 'width': '8'})
        self.assertEqual(args['value'], '0xFF')
        self.assertEqual(args['address'], '0x20000000')
        self.assertEqual(args['width'], 8)

    def test_live_memory_start_shape(self):
        args = self.s._build_arguments('live_memory_start', {
            'variables': '["g_blink_count"]', 'interval_ms': '250', 'elf': 'C:/p/build/x.elf',
        })
        self.assertEqual(args['variables'], '["g_blink_count"]')
        self.assertEqual(args['interval_ms'], 250)
        self.assertEqual(args['elf'], 'C:/p/build/x.elf')

    def test_live_memory_read_and_stop(self):
        self.assertEqual(
            self.s._build_arguments('live_memory_read', {'session_id': 'abc', 'last_n': '5'}),
            {'session_id': 'abc', 'last_n': 5})
        self.assertEqual(
            self.s._build_arguments('live_memory_stop', {'session_id': 'abc'}),
            {'session_id': 'abc'})


# ---------------------------------------------------------------------------
# _subject_for / coercion helpers
# ---------------------------------------------------------------------------


class SubjectAndCoercionTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_subject_for_build_uses_project_dir(self):
        self.assertEqual(self.s._subject_for('build', {'project_dir': 'C:/p'}), 'C:/p')

    def test_subject_for_create_project(self):
        self.assertEqual(
            self.s._subject_for('create_project', {'name': 'leg', 'dest_parent': 'C:/fw'}),
            'leg -> C:/fw')

    def test_subject_for_discover_auto(self):
        self.assertEqual(self.s._subject_for('discover_toolchain_tool', {}), '(auto-discover)')

    def test_subject_for_serial(self):
        self.assertEqual(self.s._subject_for('serial_send', {'port': 'COM7'}), 'COM7')

    def test_subject_for_get_config_environment(self):
        self.assertEqual(self.s._subject_for('get_config', {}), '(environment)')

    def test_cfg_coerces_none_to_default(self):
        self.assertEqual(self.s._cfg({'a': None}, 'a', 'fallback'), 'fallback')
        self.assertEqual(self.s._cfg({}, 'b', 'd'), 'd')
        self.assertEqual(self.s._cfg({'c': 'v'}, 'c', 'd'), 'v')

    def test_as_int(self):
        self.assertEqual(self.s._as_int('12', 8), 12)
        self.assertEqual(self.s._as_int('  9 ', 8), 9)
        self.assertEqual(self.s._as_int('nope', 8), 8)
        self.assertEqual(self.s._as_int(None, 8), 8)
        # bools must NOT be treated as ints
        self.assertEqual(self.s._as_int(True, 8), 8)

    def test_as_float(self):
        self.assertEqual(self.s._as_float('2.5', 2.0), 2.5)
        self.assertEqual(self.s._as_float('x', 2.0), 2.0)

    def test_as_bool(self):
        for truthy in ('true', '1', 'yes', 'on', True):
            self.assertIs(self.s._as_bool(truthy, False), True)
        for falsy in ('false', '0', 'no', 'off', '', False):
            self.assertIs(self.s._as_bool(falsy, True), False)
        self.assertIs(self.s._as_bool(None, True), True)
        self.assertIs(self.s._as_bool('weird', True), True)


# ---------------------------------------------------------------------------
# _McpStdioClient._parse_call_result + _tool_ok (pure parsing, no subprocess)
# ---------------------------------------------------------------------------


class ResultParsingTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_parses_text_content_json(self):
        result_obj = {
            'content': [{'type': 'text', 'text': json.dumps({'ok': True, 'returncode': 0})}],
            'isError': False,
        }
        parsed = self.s._McpStdioClient._parse_call_result(result_obj)
        self.assertEqual(parsed, {'ok': True, 'returncode': 0})

    def test_text_content_non_json_becomes_text_field(self):
        result_obj = {'content': [{'type': 'text', 'text': 'plain output'}], 'isError': False}
        parsed = self.s._McpStdioClient._parse_call_result(result_obj)
        self.assertEqual(parsed, {'text': 'plain output'})

    def test_structured_content_fallback(self):
        result_obj = {'content': [], 'structuredContent': {'ok': True, 'artifacts': {'hex': 'a.hex'}}}
        parsed = self.s._McpStdioClient._parse_call_result(result_obj)
        self.assertEqual(parsed['artifacts'], {'hex': 'a.hex'})

    def test_structured_content_result_envelope_unwrapped(self):
        result_obj = {'content': [], 'structuredContent': {'result': {'ok': True, 'gcc': '/x/gcc'}}}
        parsed = self.s._McpStdioClient._parse_call_result(result_obj)
        self.assertEqual(parsed, {'ok': True, 'gcc': '/x/gcc'})

    def test_is_error_sets_ok_false_when_absent(self):
        result_obj = {'content': [{'type': 'text', 'text': json.dumps({'error': 'boom'})}],
                      'isError': True}
        parsed = self.s._McpStdioClient._parse_call_result(result_obj)
        self.assertIs(parsed['ok'], False)

    def test_malformed_result(self):
        parsed = self.s._McpStdioClient._parse_call_result('not a dict')
        self.assertIs(parsed['ok'], False)
        self.assertIn('Malformed', parsed['error'])

    def test_tool_ok_explicit(self):
        self.assertIs(self.s._tool_ok({'ok': True}), True)
        self.assertIs(self.s._tool_ok({'ok': False}), False)

    def test_tool_ok_no_key_is_success(self):
        # get_config / discover_toolchain_tool return a plain dict with NO ok key.
        self.assertIs(self.s._tool_ok({'gcc': '/x/gcc', 'toolchain_ok': True}), True)

    def test_tool_ok_error_field_is_failure(self):
        self.assertIs(self.s._tool_ok({'error': 'nope'}), False)
        self.assertIs(self.s._tool_ok({'_rpc_error': {'message': 'x'}}), False)

    def test_tool_ok_non_dict_is_failure(self):
        self.assertIs(self.s._tool_ok('string'), False)


# ---------------------------------------------------------------------------
# END-TO-END — REAL _McpStdioClient driving the FAKE stdio server (subprocess)
# This is the "be sure" suite: finding the compiler, compiling, linking the elf,
# hex generation, flashing, and failure routability over the genuine protocol.
# ---------------------------------------------------------------------------


class McpStdioClientEndToEndTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.s = _load_stm32er_module()
        cls.tmp = tempfile.mkdtemp(prefix='stm32er_fake_mcp_')
        cls.server_path = os.path.join(cls.tmp, 'fake_stm32_mcp_server.py')
        with open(cls.server_path, 'w', encoding='utf-8') as f:
            f.write(_FAKE_STM32_MCP_SERVER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def _client(self, env_extra=None, call_timeout=15.0):
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        return self.s._McpStdioClient(
            python_cmd=[sys.executable], server_script=self.server_path,
            env=env, cwd=self.tmp, startup_timeout=15.0, call_timeout=call_timeout,
        )

    def test_handshake_and_toolchain_discovery_finds_compiler(self):
        client = self._client()
        try:
            client.start()
            info = client.initialize()
            self.assertEqual(info.get('serverInfo', {}).get('name'), 'fake-stm32-mcp')
            result = client.call_tool(
                'discover_toolchain_tool',
                self.s._build_arguments('discover_toolchain_tool', {}))
            self.assertTrue(self.s._tool_ok(result))   # no 'ok' key -> success by absence
            # Found the correct compiler (real Toolchain field name is gcc_bin).
            self.assertIn('arm-none-eabi-gcc', result['gcc_bin'])
            self.assertIn('STM32_Programmer_CLI', result['programmer_cli'])
        finally:
            client.close()

    def test_build_compiles_links_and_reports_elf(self):
        client = self._client()
        try:
            client.start()
            client.initialize()
            result = client.call_tool(
                'build', self.s._build_arguments('build', {'project_dir': 'C:/robot/fw/leg_ctrl'}))
            self.assertTrue(self.s._tool_ok(result))
            self.assertEqual(result['returncode'], 0)
            # Compiling + linking evidence.
            self.assertIn('arm-none-eabi-gcc', result['stdout'])
            self.assertIn('firmware.elf', result['stdout'])
            self.assertIn('-T STM32F407VGTX_FLASH.ld', result['stdout'])   # linker script
            self.assertEqual(result['elf'], 'build/firmware.elf')
        finally:
            client.close()

    def test_list_artifacts_reports_hex_and_bin(self):
        client = self._client()
        try:
            client.start()
            client.initialize()
            result = client.call_tool(
                'list_artifacts',
                self.s._build_arguments('list_artifacts', {'project_dir': 'C:/robot/fw/leg_ctrl'}))
            self.assertTrue(self.s._tool_ok(result))
            arts = result['artifacts']
            self.assertTrue(arts['hex'].endswith('.hex'))
            self.assertTrue(arts['bin'].endswith('.bin'))
            self.assertTrue(arts['elf'].endswith('.elf'))
        finally:
            client.close()

    def test_full_firmware_cycle_over_one_server_lifetime(self):
        # create_project -> build -> list_artifacts -> flash, all on one process,
        # proving multi-call session continuity through the real client.
        client = self._client()
        try:
            client.start()
            client.initialize()
            created = client.call_tool('create_project',
                                       self.s._build_arguments('create_project',
                                                               {'name': 'leg_ctrl',
                                                                'dest_parent': 'C:/robot/fw'}))
            self.assertTrue(self.s._tool_ok(created))
            project_dir = created['project_dir']

            built = client.call_tool('build',
                                     self.s._build_arguments('build', {'project_dir': project_dir}))
            self.assertTrue(self.s._tool_ok(built))

            arts = client.call_tool('list_artifacts',
                                    self.s._build_arguments('list_artifacts',
                                                            {'project_dir': project_dir}))
            self.assertIn('hex', arts['artifacts'])

            flashed = client.call_tool('flash',
                                       self.s._build_arguments('flash', {'project_dir': project_dir}))
            self.assertTrue(self.s._tool_ok(flashed))
            self.assertIn('verified successfully', flashed['stdout'])
        finally:
            client.close()

    def test_build_failure_is_routable_not_a_crash(self):
        # A compile error must come back as ok=False WITH the compiler diagnostics,
        # so a downstream Forker can branch on {success}.
        client = self._client(env_extra={'STM32_FAKE_BUILD_OK': '0'})
        try:
            client.start()
            client.initialize()
            result = client.call_tool(
                'build', self.s._build_arguments('build', {'project_dir': 'C:/robot/fw/leg_ctrl'}))
            self.assertFalse(self.s._tool_ok(result))
            self.assertEqual(result['returncode'], 2)
            self.assertIn("error: 'GPIOX' undeclared", result['stderr'])
        finally:
            client.close()

    def test_unknown_tool_returns_error_envelope(self):
        client = self._client()
        try:
            client.start()
            client.initialize()
            result = client.call_tool('definitely_not_a_tool', {})
            self.assertFalse(self.s._tool_ok(result))
            self.assertIn('unknown tool', result.get('error', ''))
        finally:
            client.close()

    def test_initialize_error_raises_contained_runtime_error(self):
        client = self._client(env_extra={'STM32_FAKE_INIT_ERROR': '1'})
        try:
            client.start()
            with self.assertRaises(RuntimeError) as ctx:
                client.initialize()
            self.assertIn('initialize failed', str(ctx.exception))
        finally:
            client.close()

    def test_timeout_backstop_when_server_hangs(self):
        client = self._client(env_extra={'STM32_FAKE_HANG': '1'}, call_timeout=1.5)
        try:
            client.start()
            client.initialize()
            with self.assertRaises(RuntimeError) as ctx:
                client.call_tool('build',
                                 self.s._build_arguments('build', {'project_dir': 'C:/p'}))
            self.assertIn('Timed out', str(ctx.exception))
        finally:
            client.close()

    def test_server_exit_before_response_raises(self):
        client = self._client(env_extra={'STM32_FAKE_EXIT_EARLY': '1'})
        try:
            client.start()
            client.initialize()   # handshake completes before the server exits
            with self.assertRaises(RuntimeError):
                client.call_tool('build',
                                 self.s._build_arguments('build', {'project_dir': 'C:/p'}))
        finally:
            client.close()


# ---------------------------------------------------------------------------
# _run_action routing + composites (deterministic, in-memory stub client)
# ---------------------------------------------------------------------------


class _StubClient:
    """In-memory stand-in for _McpStdioClient — records calls, returns canned dicts."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        resp = self.responses.get(name, {'ok': True})
        return resp(arguments) if callable(resp) else resp


class RunActionTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_direct_tool_routes_and_reports_ok(self):
        client = _StubClient({'build': {'ok': True, 'returncode': 0, 'stdout': 'Built target'}})
        env = self.s._run_action(client, 'build', {'project_dir': 'C:/p'})
        self.assertTrue(env['ok'])
        self.assertEqual(env['tool'], 'build')
        self.assertEqual(client.calls[0][0], 'build')
        self.assertEqual(client.calls[0][1]['project_dir'], 'C:/p')

    def test_unknown_action_envelope(self):
        client = _StubClient({})
        env = self.s._run_action(client, 'not_a_real_action', {})
        self.assertFalse(env['ok'])
        self.assertIn('Unknown action', env['result']['error'])

    def test_serial_session_chains_connect_send_disconnect(self):
        client = _StubClient({
            'serial_connect': {'ok': True},
            'serial_send': {'ok': True, 'response': 'PONG'},
            'serial_disconnect': {'ok': True},
        })
        env = self.s._composite_serial_session(client, {'port': 'COM7', 'data': 'PING'})
        self.assertTrue(env['ok'])
        called = [c[0] for c in client.calls]
        self.assertEqual(called, ['serial_connect', 'serial_send', 'serial_disconnect'])
        self.assertIn('serial_connect', env['results'])
        self.assertIn('serial_disconnect', env['results'])

    def test_serial_session_read_path_when_no_data(self):
        client = _StubClient({
            'serial_connect': {'ok': True},
            'serial_read': {'ok': True, 'data': 'boot ok'},
            'serial_disconnect': {'ok': True},
        })
        env = self.s._composite_serial_session(client, {'port': 'COM7'})
        called = [c[0] for c in client.calls]
        self.assertEqual(called, ['serial_connect', 'serial_read', 'serial_disconnect'])
        self.assertTrue(env['ok'])

    def test_serial_session_aborts_on_connect_failure(self):
        client = _StubClient({'serial_connect': {'ok': False, 'error': 'no port'}})
        env = self.s._composite_serial_session(client, {'port': 'COM9', 'data': 'x'})
        self.assertFalse(env['ok'])
        # Never tried to send/disconnect after a failed connect.
        self.assertEqual([c[0] for c in client.calls], ['serial_connect'])

    def test_live_monitor_chains_start_read_stop(self):
        client = _StubClient({
            'live_memory_start': {'ok': True, 'session_id': 'sess-1'},
            'live_memory_read': {'ok': True, 'samples': [1, 2, 3]},
            'live_memory_stop': {'ok': True},
        })
        env = self.s._composite_live_monitor(
            client, {'variables': '["g_blink_count"]', 'monitor_seconds': 0, 'last_n': 3})
        self.assertTrue(env['ok'])
        self.assertEqual(env['session_id'], 'sess-1')
        called = [c[0] for c in client.calls]
        self.assertEqual(called, ['live_memory_start', 'live_memory_read', 'live_memory_stop'])

    def test_live_monitor_aborts_on_start_failure(self):
        client = _StubClient({'live_memory_start': {'ok': False, 'error': 'no stlink'}})
        env = self.s._composite_live_monitor(client, {'variables': '[]', 'monitor_seconds': 0})
        self.assertFalse(env['ok'])
        self.assertEqual([c[0] for c in client.calls], ['live_memory_start'])


# ---------------------------------------------------------------------------
# _emit_section — single atomic INI_SECTION_STM32ER block
# ---------------------------------------------------------------------------


class EmitSectionTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()

    def test_single_atomic_block_with_header_and_body(self):
        with _LogCapture() as cap:
            self.s._emit_section(
                {'action': 'build', 'tool': 'build', 'ok': 'true', 'returncode': 0,
                 'success': 'true', 'project_dir': 'C:/p', 'session_id': '',
                 'stage': 'build', 'server_script': 'C:/srv.py'},
                'arm-none-eabi-gcc ... -o build/firmware.elf',
            )
        blocks = [r for r in cap.records if 'INI_SECTION_STM32ER' in r]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn('INI_SECTION_STM32ER<<<', block)
        self.assertIn('>>>END_SECTION_STM32ER', block)
        self.assertIn('action: build', block)
        self.assertIn('success: true', block)
        self.assertIn('firmware.elf', block)


# ---------------------------------------------------------------------------
# main() end-stage — real build run + error paths; ALWAYS one section + targets
# ---------------------------------------------------------------------------


class MainEndStageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.s = _load_stm32er_module()
        cls.srv_tmp = tempfile.mkdtemp(prefix='stm32er_main_srv_')
        cls.server_path = os.path.join(cls.srv_tmp, 'fake_stm32_mcp_server.py')
        with open(cls.server_path, 'w', encoding='utf-8') as f:
            f.write(_FAKE_STM32_MCP_SERVER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.srv_tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='stm32er_main_run_')
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_main(self, cfg_dict):
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)

        started = []
        from unittest.mock import patch
        exit_code = None
        with _LogCapture() as cap, \
                patch.object(self.s, 'start_agent',
                             side_effect=lambda n: (started.append(n) or True)), \
                patch.object(self.s, 'wait_for_agents_to_stop'):
            try:
                self.s.main()
            except SystemExit as e:
                exit_code = e.code
        return exit_code, started, cap.records

    def test_real_build_run_emits_section_and_starts_targets(self):
        code, started, records = self._run_main({
            'action': 'build',
            'server_script': self.server_path,
            'project_dir': 'C:/robot/fw/leg_ctrl',
            'target_agents': ['parametrizer_1', 'notifier_1'],
        })
        self.assertEqual(code, 0)
        self.assertEqual(started, ['parametrizer_1', 'notifier_1'])
        blocks = [r for r in records if 'INI_SECTION_STM32ER' in r]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertIn('action: build', block)
        self.assertIn('success: true', block)
        # The genuine server build output flowed all the way into the section body.
        self.assertIn('firmware.elf', block)
        self.assertIn('arm-none-eabi-gcc', block)

    def test_real_discover_run_reports_toolchain(self):
        code, started, records = self._run_main({
            'action': 'discover_toolchain_tool',
            'server_script': self.server_path,
            'target_agents': ['next_1'],
        })
        self.assertEqual(code, 0)
        self.assertEqual(started, ['next_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('success: true', block)
        self.assertIn('arm-none-eabi-gcc', block)

    def test_server_script_not_found_emits_failure_section_and_starts_targets(self):
        code, started, records = self._run_main({
            'action': 'build',
            'server_script': 'C:/does/not/exist/stm32_mcp_server.py',
            'auto_bootstrap': False,  # take the missing-server path, not a network bootstrap
            'target_agents': ['downstream_1'],
        })
        self.assertEqual(code, 0)
        # Always triggers downstream so the chain is never stranded.
        self.assertEqual(started, ['downstream_1'])
        blocks = [r for r in records if 'INI_SECTION_STM32ER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('success: false', blocks[0])
        self.assertTrue(any('not found' in r for r in records))

    def test_unknown_action_emits_failure_section_and_starts_targets(self):
        code, started, records = self._run_main({
            'action': 'definitely_not_an_action',
            'server_script': self.server_path,
            'target_agents': ['x_1'],
        })
        self.assertEqual(code, 0)
        self.assertEqual(started, ['x_1'])
        blocks = [r for r in records if 'INI_SECTION_STM32ER' in r]
        self.assertEqual(len(blocks), 1)
        self.assertIn('success: false', blocks[0])
        self.assertTrue(any('Unknown action' in r for r in records))


# ---------------------------------------------------------------------------
# Registry / contract / config / docs integration
# ---------------------------------------------------------------------------


class RegistryIntegrationTests(SimpleTestCase):
    def _read(self, *parts):
        path = os.path.join(os.path.dirname(__file__), *parts)
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_chat_wrapped_agent_spec_registered(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_stm32er')
        self.assertIsNotNone(spec, 'chat_agent_stm32er must be registered')
        self.assertEqual(spec.key, 'stm32er')
        self.assertEqual(spec.template_dir, 'stm32er')
        self.assertEqual(spec.tool_description, 'Chat-Agent-STM32er')
        self.assertEqual(spec.display_name, 'STM32er')
        self.assertTrue(spec.long_running)

    def test_exec_report_tool_row_registered(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS.get('chat_agent_stm32er'), ('stm32er', 'STM32er'))

    def test_get_mcp_tools_binds_chat_agent_stm32er(self):
        from agent.tools import get_mcp_tools
        names = [t.name for t in get_mcp_tools()]
        self.assertIn('chat_agent_stm32er', names)

    def test_agent_contract_resolves_stm32er(self):
        from agent.services.agent_contracts import get_agent_contract
        contract = get_agent_contract('stm32er')
        self.assertEqual(contract.agent_type, 'stm32er')
        self.assertFalse(contract.never_starts_targets)
        self.assertFalse(contract.no_output)

    def test_parametrizer_fields_registered(self):
        from agent.services.agent_contracts import get_parametrizer_source_fields
        fields = get_parametrizer_source_fields().get('stm32er')
        self.assertIsNotNone(fields)
        for expected in ('action', 'tool', 'ok', 'returncode', 'success',
                         'project_dir', 'session_id', 'stage', 'server_script', 'response_body'):
            self.assertIn(expected, fields)

    def test_name_variants_normalize(self):
        from agent.services.agent_paths import normalize_agent_type
        self.assertEqual(normalize_agent_type('STM32er'), 'stm32er')
        self.assertEqual(normalize_agent_type('stm32er-1'), 'stm32er_1')

    def test_url_route_exists(self):
        from django.urls import reverse
        url = reverse('update_stm32er_connection', kwargs={'agent_name': 'stm32er-1'})
        self.assertIn('update_stm32er_connection', url)

    def test_capability_hints_present(self):
        from agent.capability_registry import _EXTRA_HINTS_BY_TOOL_NAME
        hints = _EXTRA_HINTS_BY_TOOL_NAME.get('chat_agent_stm32er')
        self.assertIsNotNone(hints)
        for token in ('stm32', 'firmware', 'mcu', 'st-link'):
            self.assertIn(token, hints)

    def test_canvas_classmap_and_js_wiring(self):
        core = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertIn("'stm32er': 'stm32er-agent'", core)
        connectors = self._read('static', 'agent', 'js', 'acp-agent-connectors.js')
        self.assertIn('async function updateStm32erConnection', connectors)
        undo = self._read('static', 'agent', 'js', 'acp-canvas-undo.js')
        self.assertIn('updateStm32erConnection', undo)
        fileio = self._read('static', 'agent', 'js', 'acp-file-io.js')
        self.assertIn("case 'stm32er':", fileio)
        chat = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        self.assertIn("lower === 'stm32er'", chat)

    def test_css_gradient_is_unique(self):
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        gradient = '#0A0E17 0%, #1E63FF 33%, #8A97A8 66%, #EEF3FB 100%'
        self.assertEqual(css.count(gradient), 1,
                         'The STM32er canvas gradient must be unique to its rule')
        self.assertIn('.canvas-item.stm32er-agent', css)
        exec_css = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn('.exec-report-caption-stm32er', exec_css)
        self.assertIn('.exec-report-stm32er thead th', exec_css)

    def test_config_yaml_defaults_and_all_param_keys_present(self):
        cfg = yaml.safe_load(self._read('agents', 'stm32er', 'config.yaml'))
        self.assertEqual(cfg.get('action'), 'get_config')
        self.assertEqual(cfg.get('system'), 'make')
        self.assertEqual(cfg.get('jobs'), 8)
        self.assertEqual(cfg.get('binary'), 'bin')
        self.assertEqual(cfg.get('target_agents'), [])
        self.assertEqual(cfg.get('source_agents'), [])
        # Every action's params must exist as keys (the wrapped-tool config writer
        # ignores any requested key not already present in config.yaml).
        for key in ('server_script', 'mcp_python', 'template_dir', 'ide_root',
                    'startup_timeout', 'call_timeout', 'project_dir', 'name',
                    'dest_parent', 'overwrite', 'rel_path', 'content', 'system',
                    'jobs', 'clean_first', 'binary', 'discover_ide_root', 'port',
                    'baud', 'data', 'read_response', 'read_timeout', 'line_ending',
                    'serial_timeout', 'max_bytes', 'address', 'symbol', 'elf',
                    'count', 'width', 'value', 'variables', 'interval_ms',
                    'output_path', 'session_id', 'last_n', 'monitor_seconds'):
            self.assertIn(key, cfg, f'config.yaml missing key {key!r}')

    def test_config_json_globals_present(self):
        cfg = json.loads(self._read('config.json'))
        for key in ('stm32_mcp_server_script', 'stm32_mcp_python',
                    'stm32_template_dir', 'stm32_ide_root'):
            self.assertIn(key, cfg)

    def test_seed_injects_configured_globals(self):
        from agent import tools
        from unittest.mock import patch
        runtime_config = {'action': 'build', 'server_script': '', 'mcp_python': '',
                          'template_dir': '', 'ide_root': ''}

        def fake_get(key, default=''):
            return {
                'stm32_mcp_server_script': 'C:/srv/stm32_mcp_server.py',
                'stm32_mcp_python': 'C:/venv/python.exe',
                'stm32_template_dir': 'C:/tmpl',
                'stm32_ide_root': 'C:/ST/STM32CubeIDE',
            }.get(key, default)

        with patch.object(tools, 'get_config_value', side_effect=fake_get):
            out = tools._seed_global_agent_defaults('stm32er', runtime_config)
        self.assertEqual(out['server_script'], 'C:/srv/stm32_mcp_server.py')
        self.assertEqual(out['mcp_python'], 'C:/venv/python.exe')
        self.assertEqual(out['template_dir'], 'C:/tmpl')
        self.assertEqual(out['ide_root'], 'C:/ST/STM32CubeIDE')

    def test_seed_leaves_other_templates_untouched(self):
        from agent import tools
        from unittest.mock import patch
        runtime_config = {'server_script': ''}
        with patch.object(tools, 'get_config_value', return_value='C:/srv.py'):
            out = tools._seed_global_agent_defaults('apirer', runtime_config)
        self.assertEqual(out['server_script'], '')

    def test_seed_runs_before_assignments_in_launcher(self):
        from agent import tools
        src = inspect.getsource(tools._launch_wrapped_chat_agent)
        self.assertIn('_seed_global_agent_defaults(spec.template_dir', src)
        seed_at = src.index('_seed_global_agent_defaults(spec.template_dir')
        assign_at = src.index('_apply_requested_assignments_to_config(')
        self.assertLess(seed_at, assign_at)


# ---------------------------------------------------------------------------
# Parametrizer round-trip — read INI_SECTION_STM32ER from STM32er output
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_parametrizer_module():
    module_path = os.path.join(
        os.path.dirname(__file__), 'agents', 'parametrizer', 'parametrizer.py',
    )
    spec = importlib.util.spec_from_file_location(
        'agent_parametrizer_for_stm32er_tests', module_path)
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        for handler in list(root.handlers):
            if handler not in handlers_before:
                root.removeHandler(handler)
    return module


class ParametrizerRoundTripTests(SimpleTestCase):
    def setUp(self):
        self.p = _load_parametrizer_module()

    def test_stm32er_registered_as_section_source(self):
        self.assertIn('stm32er', self.p.SECTION_AGENT_TYPES)
        self.assertIn('stm32er', self.p.OUTPUT_PARSERS)

    def test_source_base_resolves_cardinal(self):
        self.assertEqual(self.p.get_source_base_name('stm32er_3'), 'stm32er')
        self.assertEqual(self.p.get_source_base_name('stm32er'), 'stm32er')

    def test_parser_extracts_all_stm32er_fields(self):
        section = (
            'INI_SECTION_STM32ER<<<\n'
            'action: build\ntool: build\nok: true\nreturncode: 0\nsuccess: true\n'
            'project_dir: C:/robot/fw/leg_ctrl\nsession_id: \nstage: build\n'
            'server_script: C:/srv/stm32_mcp_server.py\n\n'
            'arm-none-eabi-gcc -o build/firmware.elf\nBuilt target firmware.elf\n'
            '>>>END_SECTION_STM32ER'
        )
        parsed = self.p.OUTPUT_PARSERS['stm32er'](section)
        self.assertTrue(parsed)
        fields = parsed[0]
        self.assertEqual(fields['action'], 'build')
        self.assertEqual(fields['success'], 'true')
        self.assertEqual(fields['project_dir'], 'C:/robot/fw/leg_ctrl')
        self.assertIn('firmware.elf', fields['response_body'])

    def test_views_registration(self):
        from agent import views
        self.assertIn('stm32er', views.PARAMETRIZER_SOURCE_OUTPUT_FIELDS)
        self.assertIn('stm32er', views.PARAMETRIZER_ALLOWED_SOURCES)


# ---------------------------------------------------------------------------
# Migration presence — need the test DB
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MCP AUTO-BOOTSTRAP engine — download(repo/zip) -> pip deps -> validate.
# Subprocess + network are mocked: NO real git clone / pip / urllib happens.
# ---------------------------------------------------------------------------


def _make_fake_repo(install_dir, with_git=True):
    """Create a fake MCP checkout (mcp/stm32_mcp_server.py [+ .git]) on disk."""
    mcp_dir = os.path.join(install_dir, 'mcp')
    os.makedirs(mcp_dir, exist_ok=True)
    with open(os.path.join(mcp_dir, 'stm32_mcp_server.py'), 'w', encoding='utf-8') as f:
        f.write('# fake server\n')
    with open(os.path.join(mcp_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
        f.write('mcp>=1.2.0\npyserial>=3.5\n')
    if with_git:
        os.makedirs(os.path.join(install_dir, '.git'), exist_ok=True)


class BootstrapEngineTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()
        self.tmp = tempfile.mkdtemp(prefix='stm32er_boot_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers -----------------------------------------------------------

    def test_default_install_dir_is_per_user_writable(self):
        path = self.s._default_install_dir()
        self.assertIn('Tlamatini', path)
        self.assertTrue(path.endswith('STM32TemplateProjectMCP'))

    def test_zip_urls_strip_git_and_fallback_branches(self):
        urls = self.s._zip_urls_for('https://github.com/XAIHT/STM32TemplateProjectMCP.git', '')
        self.assertEqual(urls[0],
                         'https://github.com/XAIHT/STM32TemplateProjectMCP/archive/refs/heads/main.zip')
        self.assertIn('master.zip', urls[1])

    def test_zip_urls_honor_explicit_ref_first(self):
        urls = self.s._zip_urls_for('https://github.com/x/y', 'dev')
        self.assertTrue(urls[0].endswith('/archive/refs/heads/dev.zip'))

    # -- clone / update ----------------------------------------------------

    def test_clone_with_git_creates_checkout(self):
        install_dir = os.path.join(self.tmp, 'mcp_repo')

        def fake_run(cmd, env=None, cwd=None, timeout=120.0):
            if cmd[:2] == ['git', '--version']:
                return 0, 'git version 2.0', ''
            if cmd[:2] == ['git', 'clone']:
                _make_fake_repo(install_dir, with_git=True)  # simulate the clone
                return 0, 'Cloning...', ''
            return 1, '', 'unexpected'

        with patch.object(self.s, '_run_cmd', side_effect=fake_run):
            res = self.s._clone_or_update_repo(
                'https://github.com/XAIHT/STM32TemplateProjectMCP.git',
                install_dir, '', do_update=False, env={})
        self.assertTrue(res['ok'])
        self.assertEqual(res['action'], 'cloned')
        self.assertEqual(res['method'], 'git')
        self.assertTrue(os.path.exists(self.s._server_script_in(install_dir)))

    def test_present_repo_is_reused_without_update(self):
        install_dir = os.path.join(self.tmp, 'present')
        _make_fake_repo(install_dir, with_git=True)
        with patch.object(self.s, '_run_cmd', side_effect=AssertionError('must not run git')):
            res = self.s._clone_or_update_repo('url', install_dir, '', do_update=False, env={})
        self.assertTrue(res['ok'])
        self.assertEqual(res['action'], 'present')

    def test_clone_falls_back_to_zip_when_git_missing(self):
        install_dir = os.path.join(self.tmp, 'ziprepo')

        def fake_run(cmd, env=None, cwd=None, timeout=120.0):
            if cmd[:2] == ['git', '--version']:
                return 127, '', 'git not found'
            return 1, '', ''

        def fake_zip(repo_url, idir, ref):
            _make_fake_repo(idir, with_git=False)
            return {'ok': True, 'action': 'downloaded-zip', 'method': 'zip'}

        with patch.object(self.s, '_run_cmd', side_effect=fake_run), \
                patch.object(self.s, '_download_zip_fallback', side_effect=fake_zip):
            res = self.s._clone_or_update_repo('url', install_dir, '', do_update=False, env={})
        self.assertTrue(res['ok'])
        self.assertEqual(res['method'], 'zip')

    # -- deps --------------------------------------------------------------

    def test_deps_skip_pip_when_already_importable(self):
        install_dir = os.path.join(self.tmp, 'deps_ok')
        _make_fake_repo(install_dir)
        with patch.object(self.s, '_imports_ok', return_value={'mcp': True, 'serial': True}), \
                patch.object(self.s, '_run_cmd', side_effect=AssertionError('pip must NOT run')):
            res = self.s._ensure_python_deps([sys.executable], install_dir, {}, do_pip=True)
        self.assertTrue(res['ok'])
        self.assertEqual(res['action'], 'already-installed')
        self.assertTrue(os.path.exists(os.path.join(install_dir, self.s._DEPS_SENTINEL)))

    def test_deps_pip_installs_then_revalidates(self):
        install_dir = os.path.join(self.tmp, 'deps_pip')
        _make_fake_repo(install_dir)
        # First probe: missing. After pip: present.
        probes = [{'mcp': False, 'serial': False}, {'mcp': True, 'serial': True}]
        with patch.object(self.s, '_imports_ok', side_effect=probes), \
                patch.object(self.s, '_run_cmd', return_value=(0, 'Successfully installed mcp', '')) as run:
            res = self.s._ensure_python_deps([sys.executable], install_dir, {}, do_pip=True)
        self.assertTrue(res['ok'])
        self.assertEqual(res['action'], 'pip-install')
        # pip was actually invoked
        self.assertTrue(any('pip' in str(c.args[0]) for c in run.call_args_list))

    def test_deps_respects_pip_disabled(self):
        install_dir = os.path.join(self.tmp, 'deps_nopip')
        _make_fake_repo(install_dir)
        with patch.object(self.s, '_imports_ok', return_value={'mcp': False, 'serial': False}):
            res = self.s._ensure_python_deps([sys.executable], install_dir, {}, do_pip=False)
        self.assertFalse(res['ok'])
        self.assertEqual(res['action'], 'missing-pip-disabled')

    # -- validate ----------------------------------------------------------

    def test_validate_install_reports_checks(self):
        install_dir = os.path.join(self.tmp, 'val')
        _make_fake_repo(install_dir)
        server = self.s._server_script_in(install_dir)
        with patch.object(self.s, '_imports_ok', return_value={'mcp': True, 'serial': False}):
            res = self.s._validate_install([sys.executable], server, {})
        self.assertTrue(res['ok'])  # server exists + mcp importable (pyserial optional)
        self.assertTrue(res['checks']['server_script_exists'])
        self.assertFalse(res['checks']['pyserial_importable'])

    # -- orchestration -----------------------------------------------------

    def test_bootstrap_mcp_happy_path(self):
        install_dir = os.path.join(self.tmp, 'full')
        cfg = {'mcp_install_dir': install_dir, 'auto_update': False, 'pip_install': True}

        def fake_clone(repo_url, idir, ref, do_update, env):
            _make_fake_repo(idir, with_git=True)
            return {'ok': True, 'action': 'cloned', 'method': 'git'}

        with patch.object(self.s, '_clone_or_update_repo', side_effect=fake_clone), \
                patch.object(self.s, '_imports_ok', return_value={'mcp': True, 'serial': True}):
            server, report, ok = self.s._bootstrap_mcp(cfg, [sys.executable], {})
        self.assertTrue(ok)
        self.assertEqual(server, self.s._server_script_in(install_dir))
        self.assertTrue(report['ok'])
        names = [n for n, _r in report['steps']]
        self.assertEqual(names, ['download', 'deps', 'validate'])

    def test_bootstrap_mcp_download_failure_short_circuits(self):
        cfg = {'mcp_install_dir': os.path.join(self.tmp, 'nope')}
        with patch.object(self.s, '_clone_or_update_repo',
                          return_value={'ok': False, 'action': 'zip-failed', 'error': 'offline'}):
            server, report, ok = self.s._bootstrap_mcp(cfg, [sys.executable], {})
        self.assertFalse(ok)
        self.assertFalse(report['ok'])
        self.assertEqual([n for n, _r in report['steps']], ['download'])  # never reached deps

    def test_bootstrap_mcp_never_raises(self):
        cfg = {'mcp_install_dir': os.path.join(self.tmp, 'boom')}
        with patch.object(self.s, '_clone_or_update_repo', side_effect=RuntimeError('kaboom')):
            server, report, ok = self.s._bootstrap_mcp(cfg, [sys.executable], {})
        self.assertFalse(ok)
        self.assertIn('kaboom', report.get('error', ''))

    def test_format_report_and_note(self):
        report = {
            'repo_url': 'u', 'install_dir': 'd', 'server_script': 's', 'ok': True,
            'steps': [
                ('download', {'ok': True, 'action': 'cloned', 'method': 'git'}),
                ('deps', {'ok': True, 'action': 'already-installed'}),
                ('validate', {'ok': True, 'checks': {'server_script_exists': True,
                                                     'mcp_importable': True}}),
            ],
        }
        text = self.s._format_bootstrap_report(report)
        self.assertIn('overall     : OK', text)
        self.assertIn('mcp_importable: True', text)
        note = self.s._bootstrap_note(report, True)
        self.assertIn('bootstrap:', note)
        self.assertIn('ready=yes', note)


# ---------------------------------------------------------------------------
# main() bootstrap integration — action='bootstrap', auto-bootstrap->build, fail
# ---------------------------------------------------------------------------


class MainBootstrapTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.s = _load_stm32er_module()
        cls.srv_tmp = tempfile.mkdtemp(prefix='stm32er_boot_srv_')
        cls.server_path = os.path.join(cls.srv_tmp, 'fake_stm32_mcp_server.py')
        with open(cls.server_path, 'w', encoding='utf-8') as f:
            f.write(_FAKE_STM32_MCP_SERVER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.srv_tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='stm32er_boot_run_')
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_main(self, cfg_dict, bootstrap_return):
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)
        started = []
        exit_code = None
        with _LogCapture() as cap, \
                patch.object(self.s, '_bootstrap_mcp', return_value=bootstrap_return), \
                patch.object(self.s, 'start_agent',
                             side_effect=lambda n: (started.append(n) or True)), \
                patch.object(self.s, 'wait_for_agents_to_stop'):
            try:
                self.s.main()
            except SystemExit as e:
                exit_code = e.code
        return exit_code, started, cap.records

    def test_action_bootstrap_reports_and_starts_targets(self):
        report = {'install_dir': 'C:/cache/mcp', 'ok': True,
                  'steps': [('download', {'ok': True, 'action': 'cloned', 'method': 'git'}),
                            ('deps', {'ok': True, 'action': 'already-installed'}),
                            ('validate', {'ok': True, 'checks': {'server_script_exists': True,
                                                                'mcp_importable': True}})]}
        code, started, records = self._run_main(
            {'action': 'bootstrap', 'target_agents': ['next_1']},
            bootstrap_return=(self.server_path, report, True),
        )
        self.assertEqual(code, 0)
        self.assertEqual(started, ['next_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('action: bootstrap', block)
        self.assertIn('stage: bootstrap', block)
        self.assertIn('success: true', block)
        self.assertIn('overall     : OK', block)

    def test_auto_bootstrap_then_runs_build_against_resolved_server(self):
        # bootstrap resolves to our fake stdio server; main() then drives a real
        # build call through it — proving the end-to-end provision->run pipeline.
        report = {'install_dir': self.srv_tmp, 'ok': True,
                  'steps': [('download', {'ok': True, 'action': 'cloned', 'method': 'git'}),
                            ('deps', {'ok': True, 'action': 'already-installed'}),
                            ('validate', {'ok': True, 'checks': {'server_script_exists': True,
                                                                'mcp_importable': True}})]}
        code, started, records = self._run_main(
            {'action': 'build', 'server_script': '', 'auto_bootstrap': True,
             'project_dir': 'C:/robot/fw/leg_ctrl', 'target_agents': ['param_1']},
            bootstrap_return=(self.server_path, report, True),
        )
        self.assertEqual(code, 0)
        self.assertEqual(started, ['param_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('action: build', block)
        self.assertIn('success: true', block)
        self.assertIn('firmware.elf', block)          # the build actually ran
        self.assertIn('[bootstrap:', block)            # bootstrap note prepended to body

    def test_bootstrap_failure_emits_error_and_still_starts_targets(self):
        report = {'install_dir': 'C:/cache/mcp', 'ok': False,
                  'steps': [('download', {'ok': False, 'action': 'zip-failed',
                                          'error': 'offline'})]}
        code, started, records = self._run_main(
            {'action': 'build', 'server_script': '', 'auto_bootstrap': True,
             'target_agents': ['ds_1']},
            bootstrap_return=('', report, False),
        )
        self.assertEqual(code, 0)
        self.assertEqual(started, ['ds_1'])           # chain never stranded
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('success: false', block)
        self.assertIn('could not be auto-installed', block)


# ---------------------------------------------------------------------------
# SAFETY PREFLIGHT — environment validation + fail-safe gate (critical-mission)
# ---------------------------------------------------------------------------


class _CfgStubClient:
    """Stub MCP client returning a canned get_config for _preflight."""

    def __init__(self, cfg_response):
        self.cfg = cfg_response
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == 'get_config':
            return self.cfg
        return {'ok': True}


def _cfg_response(ide_root, gcc=True, make=True, cmake=True, programmer=True,
                  device='STM32F407VG'):
    tc = {
        'ide_root': ide_root,
        'gcc_bin': (ide_root + '/bin/arm-none-eabi-gcc.exe') if gcc else None,
        'make_bin': (ide_root + '/bin/make.exe') if make else None,
        'cmake_bin': (ide_root + '/bin/cmake.exe') if cmake else None,
        'programmer_cli': (ide_root + '/bin/STM32_Programmer_CLI.exe') if programmer else None,
    }
    return {'ok': True, 'toolchain_ok': True, 'discovered_toolchain': tc,
            'config': {'mcu': {'device': device}}}


class PreflightEngineTests(SimpleTestCase):
    def setUp(self):
        self.s = _load_stm32er_module()
        # A real dir so the stm32cubeide check resolves True.
        self.tmp = tempfile.mkdtemp(prefix='stm32er_pf_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_device_family_mapping(self):
        self.assertEqual(self.s._device_family('STM32F407VG'), 'STM32F4')
        self.assertEqual(self.s._device_family('stm32f091rc'), 'STM32F0')
        self.assertEqual(self.s._device_family('STM32F746ZG'), 'STM32F7')
        self.assertEqual(self.s._device_family('STM32F103C8'), 'STM32F1')
        self.assertEqual(self.s._device_family('not-a-chip'), '')

    def test_probe_stlink_present(self):
        out = '------ Connected ST-LINK Probes List ------\nST-Link Probe 0 :\n   ST-LINK SN  : 0667FF\n'
        with patch.object(self.s, '_run_cmd', return_value=(0, out, '')), \
                patch('os.path.exists', return_value=True):
            res = self.s._probe_stlink('C:/STM32_Programmer_CLI.exe', {})
        self.assertTrue(res['present'])
        self.assertTrue(res['driver_ok'])

    def test_probe_stlink_no_board_but_driver_ok(self):
        with patch.object(self.s, '_run_cmd', return_value=(0, 'Error: No ST-LINK detected', '')), \
                patch('os.path.exists', return_value=True):
            res = self.s._probe_stlink('C:/STM32_Programmer_CLI.exe', {})
        self.assertFalse(res['present'])
        self.assertTrue(res['driver_ok'])

    def test_probe_stlink_programmer_missing(self):
        with patch('os.path.exists', return_value=False):
            res = self.s._probe_stlink('C:/nope.exe', {})
        self.assertFalse(res['present'])
        self.assertFalse(res['driver_ok'])

    def test_build_preflight_ready_when_env_complete(self):
        client = _CfgStubClient(_cfg_response(self.tmp))
        report = self.s._preflight(client, 'build', {'system': 'make'}, {})
        self.assertTrue(report['ok'], report['fatals'])
        self.assertTrue(report['checks']['arm_none_eabi_gcc'])
        self.assertFalse(report['requires_hardware'])      # build needs NO board
        self.assertNotIn('stlink', report)

    def test_build_refused_when_compiler_missing(self):
        client = _CfgStubClient(_cfg_response(self.tmp, gcc=False))
        report = self.s._preflight(client, 'build', {}, {})
        self.assertFalse(report['ok'])
        self.assertTrue(any('arm-none-eabi-gcc' in f for f in report['fatals']))

    def test_build_refused_on_cross_family_device(self):
        client = _CfgStubClient(_cfg_response(self.tmp, device='STM32F407VG'))
        report = self.s._preflight(client, 'build', {'device': 'STM32F091RC'}, {})
        self.assertFalse(report['ok'])
        self.assertTrue(any('not supported' in f.lower() for f in report['fatals']))

    def test_build_warns_on_same_family_different_part(self):
        client = _CfgStubClient(_cfg_response(self.tmp, device='STM32F407VG'))
        report = self.s._preflight(client, 'build', {'device': 'STM32F405RG'}, {})
        self.assertTrue(report['ok'])           # same family -> allowed
        self.assertTrue(report['warnings'])     # ...but warned about linker/startup

    def test_flash_ready_when_stlink_present(self):
        client = _CfgStubClient(_cfg_response(self.tmp))
        with patch.object(self.s, '_probe_stlink',
                          return_value={'present': True, 'driver_ok': True, 'rc': 0, 'detail': ''}):
            report = self.s._preflight(client, 'flash', {}, {})
        self.assertTrue(report['ok'], report['fatals'])
        self.assertTrue(report['requires_hardware'])
        self.assertTrue(report['checks']['stlink_connected'])

    def test_flash_refused_when_no_board(self):
        client = _CfgStubClient(_cfg_response(self.tmp))
        with patch.object(self.s, '_probe_stlink',
                          return_value={'present': False, 'driver_ok': True, 'rc': 0, 'detail': ''}):
            report = self.s._preflight(client, 'flash', {}, {})
        self.assertFalse(report['ok'])
        self.assertTrue(any('No ST-LINK probe detected' in f for f in report['fatals']))

    def test_flash_refused_when_driver_missing(self):
        client = _CfgStubClient(_cfg_response(self.tmp))
        with patch.object(self.s, '_probe_stlink',
                          return_value={'present': False, 'driver_ok': False, 'rc': 127, 'detail': ''}):
            report = self.s._preflight(client, 'flash', {}, {})
        self.assertFalse(report['ok'])
        self.assertTrue(any('driver' in f.lower() for f in report['fatals']))

    def test_flash_refused_when_programmer_missing(self):
        client = _CfgStubClient(_cfg_response(self.tmp, programmer=False))
        with patch.object(self.s, '_probe_stlink',
                          return_value={'present': False, 'driver_ok': False, 'rc': 127, 'detail': ''}):
            report = self.s._preflight(client, 'flash', {}, {})
        self.assertFalse(report['ok'])
        self.assertTrue(any('STM32_Programmer_CLI' in f for f in report['fatals']))

    def test_validate_probes_stlink_but_never_fatals_on_it(self):
        client = _CfgStubClient(_cfg_response(self.tmp))
        with patch.object(self.s, '_probe_stlink',
                          return_value={'present': False, 'driver_ok': True, 'rc': 0, 'detail': ''}):
            report = self.s._preflight(client, 'validate', {}, {})
        # No board, yet validate stays OK (it is a diagnostic, not a gate).
        self.assertTrue(report['ok'])
        self.assertIn('stlink', report)
        self.assertFalse(report['checks']['stlink_connected'])


class MainPreflightTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.s = _load_stm32er_module()
        cls.srv_tmp = tempfile.mkdtemp(prefix='stm32er_pf_srv_')
        cls.server_path = os.path.join(cls.srv_tmp, 'fake_stm32_mcp_server.py')
        with open(cls.server_path, 'w', encoding='utf-8') as f:
            f.write(_FAKE_STM32_MCP_SERVER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.srv_tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='stm32er_pf_run_')
        self.cwd_before = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd_before)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_main(self, cfg_dict, stlink=None):
        cfg_dict.setdefault('server_script', self.server_path)
        cfg_dict.setdefault('auto_bootstrap', False)  # explicit fake server; no network
        with open(os.path.join(self.tmp, 'config.yaml'), 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg_dict, f)
        started = []
        exit_code = None
        probe = stlink or {'present': True, 'driver_ok': True, 'rc': 0, 'detail': ''}
        with _LogCapture() as cap, \
                patch.object(self.s, '_probe_stlink', return_value=probe), \
                patch.object(self.s, 'start_agent',
                             side_effect=lambda n: (started.append(n) or True)), \
                patch.object(self.s, 'wait_for_agents_to_stop'):
            try:
                self.s.main()
            except SystemExit as e:
                exit_code = e.code
        return exit_code, started, cap.records

    def test_validate_action_reports_environment(self):
        code, started, records = self._run_main(
            {'action': 'validate', 'target_agents': ['next_1']})
        self.assertEqual(code, 0)
        self.assertEqual(started, ['next_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('action: validate', block)
        self.assertIn('stage: validate', block)
        self.assertIn('arm-none-eabi-gcc', block)
        self.assertIn('[OK] arm_none_eabi_gcc: True', block)

    def test_compile_allowed_without_a_board(self):
        # No ST-LINK at all, yet a pure build must proceed (compile needs no board).
        code, started, records = self._run_main(
            {'action': 'build', 'project_dir': 'C:/p', 'target_agents': ['t_1']},
            stlink={'present': False, 'driver_ok': True, 'rc': 0, 'detail': ''})
        self.assertEqual(code, 0)
        self.assertEqual(started, ['t_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('action: build', block)
        self.assertIn('success: true', block)
        self.assertIn('firmware.elf', block)

    def test_flash_refused_without_board_but_chain_continues(self):
        code, started, records = self._run_main(
            {'action': 'flash', 'project_dir': 'C:/p', 'target_agents': ['ds_1']},
            stlink={'present': False, 'driver_ok': True, 'rc': 0, 'detail': ''})
        self.assertEqual(code, 0)
        self.assertEqual(started, ['ds_1'])      # downstream still triggered
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('success: false', block)
        self.assertIn('PREFLIGHT REFUSED', block)
        self.assertIn('No ST-LINK probe detected', block)

    def test_cross_family_build_refused(self):
        code, started, records = self._run_main(
            {'action': 'build', 'project_dir': 'C:/p', 'device': 'STM32F091RC',
             'target_agents': ['ds_1']})
        self.assertEqual(code, 0)
        self.assertEqual(started, ['ds_1'])
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertIn('success: false', block)
        self.assertIn('PREFLIGHT REFUSED', block)
        self.assertIn('not supported', block.lower())

    def test_preflight_can_be_disabled(self):
        # With preflight off, a flash with no board reaches the server (which then
        # reports its own flash result) instead of being gated.
        code, started, records = self._run_main(
            {'action': 'flash', 'project_dir': 'C:/p', 'preflight': False,
             'target_agents': ['ds_1']},
            stlink={'present': False, 'driver_ok': True, 'rc': 0, 'detail': ''})
        self.assertEqual(code, 0)
        block = next(r for r in records if 'INI_SECTION_STM32ER' in r)
        self.assertNotIn('PREFLIGHT REFUSED', block)
        self.assertIn('action: flash', block)


class MigrationPresenceTests(TestCase):
    def test_agent_row_seeded_by_migration_0101(self):
        from agent.models import Agent
        self.assertTrue(
            Agent.objects.filter(agentDescription='STM32er').exists(),
            "Migration 0101 must seed an Agent row with agentDescription='STM32er'",
        )

    def test_tool_row_seeded_by_migration_0102(self):
        from agent.models import Tool
        self.assertTrue(
            Tool.objects.filter(toolDescription='Chat-Agent-STM32er').exists(),
            "Migration 0102 must seed a Tool row with toolDescription='Chat-Agent-STM32er'",
        )


if __name__ == '__main__':
    unittest.main()
