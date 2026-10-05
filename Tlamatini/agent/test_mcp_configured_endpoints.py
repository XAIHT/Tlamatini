# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Real nondefault MCP listeners and their configured clients, without inference."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import grpc
import websockets
import filesearch_pb2
import filesearch_pb2_grpc

from agent import mcp_files_search_client as client
from agent import path_guard
from agent.mcp_system_client import MCPSystemClient


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ConfiguredMCPTests(unittest.TestCase):
    def test_context_chains_use_override_frozen_and_explicit_bom_configs(self):
        from agent.chain_files_search_lcel import FileSearchRAGChain
        from agent.chain_system_lcel import SystemRAGChain
        with tempfile.TemporaryDirectory(prefix='tlamatini-context-config-') as folder:
            root = Path(folder)
            config = {'chained-model': 'nemotron-3-ultra:cloud',
                      'mcp_system_client_uri': 'ws://127.0.0.1:8767',
                      'mcp_files_search_client_uri': 'ws://127.0.0.1:50053'}
            override = root / 'override.json'
            installed = root / 'config.json'
            explicit = root / 'explicit.json'
            explicit_config = {**config, 'mcp_system_client_uri': 'ws://127.0.0.1:8770',
                               'mcp_files_search_client_uri': 'ws://127.0.0.1:50057'}
            explicit.write_text(json.dumps(explicit_config), encoding='utf-8-sig')
            for encoding in ('utf-8', 'utf-8-sig'):
                override.write_text(json.dumps(config), encoding=encoding)
                installed.write_text(json.dumps(config), encoding=encoding)
                for use_override in (True, False):
                    with self.subTest(encoding=encoding, override=use_override), \
                            patch.dict(os.environ, {'CONFIG_PATH': str(override) if use_override else ''}), \
                            patch.object(sys, 'frozen', True, create=True), \
                            patch.object(sys, 'executable', str(root / 'Tlamatini.exe')):
                        system = SystemRAGChain()
                        files = FileSearchRAGChain()
                        self.assertEqual(system.mcp_client.uri, config['mcp_system_client_uri'])
                        self.assertEqual(files.grpc_target, '127.0.0.1:50053')
                        self.assertEqual(system.llm.model, 'nemotron-3-ultra:cloud')
                        self.assertEqual(files.llm.model, 'nemotron-3-ultra:cloud')
                        self.assertEqual(SystemRAGChain(str(explicit)).mcp_client.uri,
                                         explicit_config['mcp_system_client_uri'])
                        self.assertEqual(FileSearchRAGChain(str(explicit)).grpc_target, '127.0.0.1:50057')

    def test_system_context_disconnects_even_when_routing_raises(self):
        from agent.chain_system_lcel import SystemRAGChain
        chain = SystemRAGChain.__new__(SystemRAGChain)
        chain.mcp_client = AsyncMock()
        chain.should_fetch_system_context = AsyncMock(side_effect=RuntimeError('routing failed'))
        with self.assertRaisesRegex(RuntimeError, 'routing failed'):
            asyncio.run(chain.intelligent_context_fetch({'question': 'fixture'}))
        chain.mcp_client.disconnect.assert_awaited_once()

    def test_chat_chain_reads_plain_and_bom_configuration(self):
        from agent.rag import config as rag_config
        with tempfile.TemporaryDirectory(prefix='tlamatini-chat-config-') as folder:
            root = Path(folder)
            (root / 'prompt.pmt').write_text('Answer {question}.', encoding='utf-8')
            expected = {'unified_agent_model': 'nemotron-3-ultra:cloud', 'allowed_paths': ['application']}
            for encoding in ('utf-8', 'utf-8-sig'):
                with self.subTest(encoding=encoding):
                    (root / 'config.json').write_text(json.dumps(expected), encoding=encoding)
                    with patch.object(rag_config, 'self_modify_available', return_value=False):
                        loaded, prompt, path = rag_config.load_config_and_prompt(str(root))
                    self.assertEqual(loaded, expected)
                    self.assertEqual(prompt, 'Answer {question}.')
                    self.assertEqual(Path(path), root / 'config.json')

    def test_path_guard_reads_bom_config_without_weakening_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='tlamatini-path-config-') as folder:
            root = Path(folder)
            allowed = root / 'allowed ñ'
            allowed.mkdir()
            config_path = root / 'config.json'
            expected = {'allowed_paths': [str(allowed)]}
            for encoding in ('utf-8', 'utf-8-sig'):
                with self.subTest(encoding=encoding):
                    config_path.write_text(json.dumps(expected), encoding=encoding)
                    with patch.dict(os.environ, {'CONFIG_PATH': str(config_path)}):
                        loaded = path_guard._load_config()
                    self.assertEqual(loaded, expected)
                    with patch.object(path_guard, '_ALLOWED_DIRS', path_guard._build_allowed_dirs(loaded)):
                        self.assertTrue(path_guard.is_path_allowed(str(allowed / 'inside.txt')))
                        self.assertFalse(path_guard.is_path_allowed(str(root / 'outside.txt')))
                        self.assertFalse(path_guard.is_path_allowed(str(allowed / '..' / 'outside.txt')))

    def test_frozen_clients_read_the_installation_config(self):
        with tempfile.TemporaryDirectory(prefix='tlamatini-frozen-config-') as folder:
            config = {'mcp_system_client_uri': 'ws://127.0.0.1:8766',
                      'mcp_files_search_client_uri': 'ws://127.0.0.1:50052'}
            (Path(folder) / 'config.json').write_text(json.dumps(config), encoding='utf-8-sig')
            with patch.dict(os.environ, {'CONFIG_PATH': ''}), patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', str(Path(folder) / 'Tlamatini.exe')), \
                    patch.object(client, '_CONFIG_CACHE', None):
                self.assertEqual(client._grpc_endpoint(), '127.0.0.1:50052')
                self.assertEqual(MCPSystemClient().uri, 'ws://127.0.0.1:8766')

    def test_client_endpoint_legacy_uri_ipv6_and_no_uri_fallback(self):
        cases = [
            ({'mcp_files_search_client_uri': 'ws://127.0.0.1:50052'}, '127.0.0.1:50052'),
            ({'mcp_files_search_client_uri': 'grpc://localhost:51234'}, 'localhost:51234'),
            ({'mcp_files_search_client_uri': '[::1]:50052'}, '[::1]:50052'),
            ({'mcp_files_search_grpc_target': 'localhost:51235'}, 'localhost:51235'),
            ({'mcp_files_search_client_uri': 'localhost:51236',
              'mcp_files_search_grpc_target': 'localhost:51235'}, 'localhost:51236'),
            ({'mcp_files_search_server_host': '127.0.0.1', 'mcp_files_search_server_port': 50053}, '127.0.0.1:50053'),
            ({}, 'localhost:50051'),
        ]
        for config, expected in cases:
            with self.subTest(config=config), patch.object(client, '_CONFIG_CACHE', config):
                self.assertEqual(client._grpc_endpoint(), expected)
        for uri in ('ws://user:password@localhost:50052', 'ws://localhost:50052/private', 'localhost', 'localhost:99999'):
            with self.subTest(uri=uri), patch.object(client, '_CONFIG_CACHE', {'mcp_files_search_client_uri': uri}):
                with self.assertRaises(ValueError):
                    client._grpc_endpoint()

    def test_live_files_search_nondefault_port_and_config_override(self):
        with tempfile.TemporaryDirectory(prefix='tlamatini-mcp-') as folder:
            root = Path(folder)
            fixture = root / 'release ñ.txt'
            fixture.write_text('Real configured search fixture', encoding='utf-8')
            port = available_port()
            config = {'mcp_files_search_server_host': '127.0.0.1',
                      'mcp_files_search_server_port': port, 'mcp_files_search_server_max_workers': 2,
                      'mcp_files_search_client_uri': f'ws://127.0.0.1:{port}',
                      'allowed_paths': [str(root)]}
            config_file = root / 'config.json'
            config_file.write_text(json.dumps(config), encoding='utf-8-sig')
            module_dir = Path(__file__).parent
            env = {**os.environ, 'CONFIG_PATH': str(config_file), 'PYTHONIOENCODING': 'utf-8'}
            worker = subprocess.Popen([sys.executable, '-u', str(module_dir / 'mcp_files_search_server.py')], env=env)
            try:
                with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
                    grpc.channel_ready_future(channel).result(timeout=20)
                    stub = filesearch_pb2_grpc.FileSearcherStub(channel)
                    listed = stub.ListAllowedDirs(filesearch_pb2.ListDirsRequest(), timeout=5)
                    self.assertEqual(dict(listed.allowed_dirs), {str(root): str(root)})
                    response = stub.SearchFiles(filesearch_pb2.SearchRequest(file_pattern='release *.txt'), timeout=5)
                    self.assertEqual(list(response.found_files), [str(fixture)])
                    self.assertFalse(response.error_message)
                    response = stub.SearchFiles(filesearch_pb2.SearchRequest(
                        file_pattern='release *.txt', base_path_key=str(root).upper()), timeout=5)
                    self.assertEqual(list(response.found_files), [str(fixture)])
                    self.assertFalse(response.error_message)
                with patch.dict(os.environ, {'CONFIG_PATH': str(config_file)}), patch.object(client, '_CONFIG_CACHE', None):
                    self.assertEqual(client.list_allowed_directories(verbose=False), {str(root): str(root)})
                    self.assertEqual(client.call_grpc_server('release *.txt', None, False, verbose=False), [str(fixture)])
                    self.assertEqual(client.call_grpc_server('release *.txt', None, False), [str(fixture)])
                    from agent.chain_files_search_lcel import FileSearchRAGChain
                    chain = FileSearchRAGChain()
                    self.assertEqual(chain._call_grpc_server_sync('release *.txt', None, False, False), [str(fixture)])
                    self.assertEqual(chain._call_grpc_list_dirs_sync(False), {str(root): str(root)})
            finally:
                worker.terminate()
                worker.wait(timeout=10)

    def test_live_system_server_uses_explicit_config(self):
        with tempfile.TemporaryDirectory(prefix='tlamatini-system-mcp-') as folder:
            port = available_port()
            config_file = Path(folder) / 'config.json'
            config_file.write_text(json.dumps({'mcp_system_server_host': '127.0.0.1', 'mcp_system_server_port': port,
                                               'mcp_system_client_uri': f'ws://127.0.0.1:{port}'}), encoding='utf-8-sig')
            env = {**os.environ, 'CONFIG_PATH': str(config_file), 'PYTHONIOENCODING': 'utf-8'}
            worker = subprocess.Popen([sys.executable, '-u', str(Path(__file__).parent / 'mcp_system_server.py')], env=env)
            async def probe():
                async with websockets.connect(f'ws://127.0.0.1:{port}', open_timeout=3) as ws:
                    await ws.send(json.dumps({'operation': 'get_system_time'}))
                    return json.loads(await asyncio.wait_for(ws.recv(), 10))
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        response = asyncio.run(probe())
                        break
                    except OSError:
                        if time.monotonic() >= deadline or worker.poll() is not None:
                            raise
                        time.sleep(.2)
                self.assertEqual(response['status'], 'success')
                self.assertIn('time', response['data'])
                async def configured_client():
                    connection = MCPSystemClient()
                    self.assertTrue(await connection.connect())
                    try:
                        return await connection.get_system_time()
                    finally:
                        await connection.disconnect()
                with patch.dict(os.environ, {'CONFIG_PATH': str(config_file)}):
                    self.assertTrue(asyncio.run(configured_client()))
                    from agent.chain_system_lcel import SystemRAGChain
                    chain = SystemRAGChain()
                    context = asyncio.run(chain.intelligent_context_fetch({'question': 'What is the CPU usage?'}))
                    self.assertIn('cpu_usage:', context['context'])
                    self.assertNotIn('Error', context['context'])
                    self.assertIsNone(chain.mcp_client.websocket)
            finally:
                worker.terminate()
                worker.wait(timeout=10)
