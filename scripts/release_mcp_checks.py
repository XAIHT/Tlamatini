# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Read-only client probes inside the actual source/frozen Django shell.

The visible panel harness owns the running server and supplies a bounded fixture
directory already present in allowed_paths. No model or external service is used.
"""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys

from agent import mcp_files_search_client as files
from agent import path_guard
from agent.mcp_system_client import MCPSystemClient
from agent.chain_files_search_lcel import FileSearchRAGChain
from agent.chain_system_lcel import SystemRAGChain


def main():
    output = Path(os.environ['TLAMATINI_RELEASE_MCP_OUTPUT'])
    fixture = Path(os.environ['TLAMATINI_RELEASE_MCP_FIXTURE']).resolve()
    filename = 'MCP Unicode ñ.txt'
    assert (fixture / filename).is_file(), 'The bounded MCP fixture is missing'
    assert path_guard.is_path_allowed(str(fixture / filename)), 'Path security did not load the configured fixture'
    with contextlib.redirect_stdout(io.StringIO()):
        directories = files.list_allowed_directories(verbose=False)
    key = next((key for key, value in directories.items() if Path(value).resolve() == fixture), None)
    assert key, 'The live server did not honor the configured allowed directory'
    found = files.call_grpc_server(filename, key.upper(), False, verbose=False)
    assert {Path(value).resolve() for value in found} == {fixture / filename}
    assert files.call_grpc_server('../*', key, False, verbose=False) == []
    file_chain = FileSearchRAGChain()
    assert file_chain.llm.model == 'nemotron-3-ultra:cloud'
    assert file_chain.grpc_target == files._grpc_endpoint()
    assert file_chain._call_grpc_list_dirs_sync(False) == directories
    chain_found = file_chain._call_grpc_server_sync(filename, key.upper(), False, False)
    assert {Path(value).resolve() for value in chain_found} == {fixture / filename}

    async def system_probe():
        client = MCPSystemClient()
        assert await client.connect(), 'Could not reach the configured System-Metrics endpoint'
        try:
            resources = await client.list_resources()
            moment = await client.get_system_time()
            assert resources and moment, 'The live MCP returned no resources or time'
            cpu = await client.get_resource('cpu_usage')
            memory = await client.get_resource('memory_usage')
            assert 0 <= float(str(cpu).removesuffix('%')) <= 100
            assert 0 <= float(str(memory).removesuffix('%')) <= 100
            return dict(uri=client.uri, resources=len(resources), system_time=moment,
                        cpu_usage=cpu, memory_usage=memory)
        finally:
            await client.disconnect()

    async def system_chain_probe():
        chain = SystemRAGChain()
        assert chain.llm.model == 'nemotron-3-ultra:cloud'
        assert chain.mcp_client.uri == MCPSystemClient().uri
        # The explicit CPU keyword uses deterministic routing: no model call.
        response = await chain.intelligent_context_fetch({'question': 'What is the CPU usage?'})
        assert 'cpu_usage:' in response['context'] and 'memory_usage:' in response['context']
        assert 'Error' not in response['context']
        assert chain.mcp_client.websocket is None
        return dict(uri=chain.mcp_client.uri, context_received=True, socket_closed=True)

    result = dict(status='PASS', mode='frozen' if getattr(sys, 'frozen', False) else 'source',
                  files_endpoint=files._grpc_endpoint(), exact_unicode_match=True,
                  case_insensitive_key=True, traversal_rejected=True,
                  path_security_fixture_allowed=True,
                  system=asyncio.run(system_probe()), system_chain=asyncio.run(system_chain_probe()),
                  file_chain_exact_unicode_match=True, model_invocations=0)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('LIVE_MCP_CLIENTS_PASS: configured endpoints, Unicode match and traversal rejection', flush=True)


main()
