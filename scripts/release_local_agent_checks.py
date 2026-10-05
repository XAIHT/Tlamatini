# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Execute local file agents through the product runtime in source or frozen mode.

Run with Django's real shell command from a verified visible foreground console.
TLAMATINI_RELEASE_CHECK_DIR names a new evidence directory under the checkout's
Temp tree. Every mutation is confined to its fixtures. No model is invoked.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import yaml
from agent import chat_agent_runtime as runtime
from agent.services.agent_paths import get_agents_root


def main():
    out = Path(os.environ['TLAMATINI_RELEASE_CHECK_DIR']).resolve()
    if 'Temp' not in out.parts or out.exists():
        raise RuntimeError('Use a new evidence directory below the checkout Temp tree.')
    out.mkdir(parents=True)
    fixtures = out / 'fixtures'
    fixtures.mkdir()
    runs = out / 'agents'
    runs.mkdir()
    templates = Path(get_agents_root())
    python = runtime._resolve_python_executable()
    env = runtime._build_child_env()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    env.pop('AGENT_REANIMATED', None)
    results = []
    mode = 'frozen' if getattr(sys, 'frozen', False) else 'source'

    def execute(case, agent, values, verify):
        print(f'LOCAL AGENT START [{mode}] {case}: {agent}', flush=True)
        _, folder, log = runtime.create_isolated_runtime_copy(
            str(templates / agent), agent, runtime_root=str(runs))
        folder = Path(folder)
        config = yaml.safe_load((folder / 'config.yaml').read_text(encoding='utf-8-sig')) or {}
        config.update(source_agents=[], target_agents=[], **values)
        (folder / 'config.yaml').write_text(yaml.safe_dump(config, allow_unicode=True), encoding='utf-8')
        script = runtime.resolve_runtime_script_path(str(folder), agent)
        started = time.monotonic()
        result = subprocess.run([python, '-u', script], cwd=folder, env=env, timeout=90)
        text = Path(log).read_text(encoding='utf-8', errors='replace')
        assert result.returncode == 0, f'{agent} exited {result.returncode}'
        verify(text)
        assert not (folder / 'agent.pid').exists(), f'{agent} left its PID file'
        record = dict(case=case, agent=agent, mode=mode, status='PASS',
                      seconds=round(time.monotonic() - started, 3), log=log)
        results.append(record)
        (out / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f'LOCAL AGENT PASS [{mode}] {case}: artifact and semantic result verified', flush=True)

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    path = fixtures / 'Review ñ.txt'
    content = 'First line ñ — quoted "value" and C:\\sample\\path\r\nRepeated token\r\nRepeated token\r\n'
    execute('01-create-unicode-literal-bytes', 'file_creator',
            dict(file_path=str(path), content=content, content_b64=''),
            lambda text: require(path.read_bytes() == content.encode('utf-8'), 'File-Creator bytes differ'))
    execute('02-editor-rejects-ambiguous-replacement', 'editor',
            dict(file_path=str(path), old_string='Repeated token', new_string='Changed', replace_all=False),
            lambda text: require('status: not_unique' in text and path.read_bytes() == content.encode('utf-8'),
                                 'Ambiguous edit changed the file or did not report its refusal'))
    updated = content.replace('Repeated token', 'Changed ñ')
    execute('03-editor-replaces-all-preserving-crlf', 'editor',
            dict(file_path=str(path), old_string='Repeated token', new_string='Changed ñ', replace_all=True),
            lambda text: require('status: edited' in text and path.read_bytes() == updated.encode('utf-8'),
                                 'Editor did not preserve exact Unicode/CRLF bytes'))
    execute('04-grepper-verbatim-byte-channel', 'grepper',
            dict(path=str(path), output_mode='lines', line_numbers=False, start_line=0, end_line=0),
            lambda text: require(base64.b64encode(path.read_bytes()).decode() in text,
                                 'Grepper did not return the exact file bytes'))
    execute('05-globber-unicode-name', 'globber',
            dict(path=str(fixtures), pattern='*.txt', sort_by='name'),
            lambda text: require(str(path) in text and 'INI_SECTION_GLOBBER' in text,
                                 'Globber did not report the fixture'))
    copied = fixtures / 'copied'
    copied.mkdir()
    execute('06-mover-copy', 'mover',
            dict(trigger_mode='immediate', operation='copy', source_files=[str(path)], destination_folder=str(copied)),
            lambda text: require(path.exists() and (copied / path.name).read_bytes() == path.read_bytes(),
                                 'Mover copy lost bytes or removed the source'))
    moved = fixtures / 'moved'
    moved.mkdir()
    execute('07-mover-move', 'mover',
            dict(trigger_mode='immediate', operation='move', source_files=[str(copied / path.name)], destination_folder=str(moved)),
            lambda text: require(not (copied / path.name).exists() and (moved / path.name).read_bytes() == path.read_bytes(),
                                 'Mover did not move exactly the fixture'))
    archive = fixtures / 'roundtrip.zip'
    execute('08-compress', 'de_compresser', dict(input=str(path), output=str(archive), passwordless=True),
            lambda text: require(archive.is_file() and archive.stat().st_size > 0, 'Archive was not produced'))
    extracted = fixtures / 'extracted'
    execute('09-decompress', 'de_compresser', dict(input=str(archive), output=str(extracted), passwordless=True),
            lambda text: require((extracted / path.name).read_bytes() == path.read_bytes(), 'Archive round trip changed bytes'))
    execute('10-deleter-explicit-file', 'deleter',
            dict(trigger_mode='immediate', target_path=str(moved), files_to_delete=[path.name], allow_directory_delete=False),
            lambda text: require(moved.is_dir() and not (moved / path.name).exists() and path.is_file(),
                                 'Deleter did not confine removal to the named fixture'))
    execute('11-sleeper-short-completion', 'sleeper', dict(duration_ms=250),
            lambda text: require('error' not in text.lower(), 'Sleeper reported an error'))
    (out / 'summary.json').write_text(json.dumps(dict(mode=mode, status='PASS', cases=results,
                                                      model_invocations=0), indent=2), encoding='utf-8')
    print(f'LOCAL AGENT SUITE PASSED: {len(results)} real executions in {mode} mode.', flush=True)


main()
