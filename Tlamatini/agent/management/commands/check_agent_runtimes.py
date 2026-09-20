"""Offline runtime-carriage check, executed in source and by the frozen build.

Created by Angela López Mendoza · @angelahack1 — Tlamatini.
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

import yaml
from django.core.management.base import BaseCommand, CommandError

from agent import chat_agent_runtime as runtime
from agent.agents import model_settings
from agent.services.agent_paths import get_agents_root
from agent.services.flow_knowledge import KNOWLEDGE_AGENTS, write_runtime_knowledge


def check_model_loader(script, config_path):
    """Execute the real YAML reader and resolver without an agent's startup code."""
    tree = ast.parse(script.read_text(encoding='utf-8-sig'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'_load_config_file', 'load_config'}]
    if len(functions) != 2:
        raise CommandError(f'{script.parent.name}: model loader functions are missing')
    namespace = {'__file__': str(script), 'yaml': yaml, 'logging': logging,
                 'sys': sys, 'traceback': traceback}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(script), 'exec'), namespace)
    return namespace['load_config'](str(config_path))


class Command(BaseCommand):
    help = ('Prepare every agent, refresh reusable helpers, check model inheritance, '
            'and execute File-Creator in scratch space. No LLM/network/desktop actions.')

    def handle(self, *args, **options):
        root = get_agents_root()
        templates = sorted(path for path in root.iterdir()
                           if (path / f'{path.name}.py').is_file()
                           and (path / 'config.yaml').is_file())
        if not templates:
            raise CommandError(f'No agent templates found at {root}')
        missing = model_settings.AGENTS - {path.name for path in templates}
        if missing:
            raise CommandError(f'Missing model agent templates: {sorted(missing)}')
        pools = root / 'pools'
        pools.mkdir(exist_ok=True)
        # This private subtree retains the real agents/config.json ancestry.
        # Only TemporaryDirectory's own files are removed, never existing pools.
        with tempfile.TemporaryDirectory(prefix='_runtime_check_', dir=pools) as temp:
            scratch = Path(temp)
            copies = {}
            for template in templates:
                name = template.name
                _, folder, _ = runtime.create_isolated_runtime_copy(
                    str(template), name, runtime_root=str(scratch))
                folder = Path(folder)
                copies[name] = folder
                if not runtime.resolve_runtime_script_path(str(folder), name):
                    raise CommandError(f'{name}: runtime script missing')
                if name in model_settings.AGENTS:
                    helper = folder / 'model_settings.py'
                    if helper.read_bytes() != (root / helper.name).read_bytes():
                        raise CommandError(f'{name}: shared model helper differs')
                    # A reusable pool must replace a stale helper on its next run.
                    helper.write_text('# stale helper\n', encoding='utf-8')
                write_runtime_knowledge(folder, name)
                if name in KNOWLEDGE_AGENTS:
                    catalog = json.loads((folder / 'flow_catalog.json').read_text(encoding='utf-8'))
                    if set(catalog['agents']) != {path.name for path in templates}:
                        raise CommandError(f'{name}: incomplete planning catalog')
                if name in model_settings.AGENTS:
                    config_path = folder / 'config.yaml'
                    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
                    expected = model_settings.resolve_agent_models(name, config, agent_file=folder / f'{name}.py')
                    actual = check_model_loader(folder / f'{name}.py', config_path)
                    if actual != expected:
                        raise CommandError(f'{name}: copied loader ignores saved model configuration')

            # Reproduce the reported File-Creator execution with harmless bytes.
            folder = copies['file_creator']
            output = scratch / 'created.txt'
            content = 'Tlamatini runtime check: ñ / \\ / "quoted"\n'
            (folder / 'config.yaml').write_text(yaml.safe_dump({
                'file_path': str(output), 'content': content, 'content_b64': '',
                'source_agents': [], 'target_agents': [],
            }), encoding='utf-8')
            env = runtime._build_child_env()
            env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
            env.pop('AGENT_REANIMATED', None)
            result = subprocess.run(
                [runtime._resolve_python_executable(), str(folder / 'file_creator.py')],
                cwd=folder, env=env, capture_output=True, timeout=45,
            )
            if result.returncode or not output.is_file() or output.read_bytes() != content.encode('utf-8'):
                raise CommandError(f'File-Creator did not write the expected bytes (exit {result.returncode})')
        self.stdout.write(self.style.SUCCESS(json.dumps({
            'frozen': bool(getattr(sys, 'frozen', False)),
            'agent_runtimes': len(templates), 'model_loaders': len(model_settings.AGENTS),
            'planner_catalogs': len(KNOWLEDGE_AGENTS), 'existing_helpers_refreshed': True,
            'file_creator_executed': True,
        })))
