# Tlamatini Author Banner — Angela López Mendoza
"""Deep menu suite: launch in a verified visible PowerShell -NoExit console.

Chrome is explicitly headed. Before browser tests start, Shoter photographs all
screens and the runner waits for a fresh browser-visible-confirmed file. The
operator verifies that image, then creates the file. No headless fallback exists.
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Temp/menu-state-tests'


class LiveResult(unittest.TextTestResult):
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.writeln(self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.writeln(self._exc_info_to_string(err, test))


def coverage_report(coverage):
    graph = json.loads((OUT / 'javascript-references.json').read_text(encoding='utf-8'))
    functions = graph['functions']
    observations = {}
    for case in coverage:
        for script in case['scripts']:
            filename = script['url'].split('?')[0].rsplit('/', 1)[-1]
            for function in script['functions']:
                span = function['ranges'][0]
                if not span['count']:
                    continue
                for symbol in functions:
                    if (symbol['file'].endswith('/' + filename)
                            and abs(symbol['end'] - span['endOffset']) <= 1
                            and abs(symbol['start'] - span['startOffset']) < 100):
                        observations.setdefault(symbol['id'], set()).add(case['mode'] + ':' + case['test'])
    rows = [{**symbol, 'observed_in': sorted(observations.get(symbol['id'], []))} for symbol in functions]
    (OUT / 'function-coverage-map.json').write_text(json.dumps({
        'functions': rows, 'observed_functions': len(observations), 'indexed_functions': len(functions),
        'limitations': ['V8 function-entry evidence is not full branch coverage.',
                        'Unobserved functions remain explicit; static reachability is not a pass.',
                        'Native apps, live providers and the frozen executable are not exercised by browser transport fixtures.']}, indent=2), encoding='utf-8')


def python_references():
    """Every Python symbol/ref in modules reached through menu routes or playback.

    AST ownership is precise; dynamic attributes retain their expression rather
    than claiming an inferred Python call target is certain.
    """
    names = ['views.py', 'urls.py', 'routing.py', 'consumers.py', 'constants.py',
             'prompt_flow_panel_consumer.py', 'prompt_flow_panel_runtime.py',
             'services/prompt_flow_panel.py', 'management/commands/check_prompt_flow_panel.py']
    js_graph = json.loads((OUT / 'javascript-references.json').read_text(encoding='utf-8'))
    interface_names = {ref['name'] for ref in js_graph.get('interfaceReferences', [])}
    symbols, references, hashes = [], [], {}
    for name in names:
        target = ROOT / 'Tlamatini/agent' / name
        source = target.read_text(encoding='utf-8-sig')
        file = target.relative_to(ROOT).as_posix()
        hashes[file] = hashlib.sha256(source.encode()).hexdigest()
        tree = ast.parse(source, filename=file)

        def visit(node, owner=file + ':module'):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owner = f'{file}:{node.lineno}:{node.name}'
                symbols.append({'id': owner, 'name': node.name, 'file': file,
                                'line': node.lineno, 'kind': type(node).__name__})
            if isinstance(node, ast.Name):
                references.append({'owner': owner, 'name': node.id, 'file': file,
                                   'line': node.lineno, 'kind': type(node.ctx).__name__})
                if isinstance(node.ctx, ast.Store):
                    symbols.append({'id': f'{owner}:{node.id}:{node.lineno}', 'name': node.id,
                                    'file': file, 'line': node.lineno, 'kind': 'variable'})
            if isinstance(node, (ast.arg, ast.alias)):
                name = node.arg if isinstance(node, ast.arg) else (node.asname or node.name.split('.')[0])
                symbols.append({'id': f'{owner}:{name}:{node.lineno}', 'name': name,
                                'file': file, 'line': node.lineno,
                                'kind': 'parameter' if isinstance(node, ast.arg) else 'import'})
            if isinstance(node, ast.Attribute):
                references.append({'owner': owner, 'name': ast.unparse(node), 'file': file,
                                   'line': node.lineno, 'kind': 'dynamic-attribute-' + type(node.ctx).__name__})
            if isinstance(node, ast.Call):
                references.append({'owner': owner, 'name': ast.unparse(node.func), 'file': file,
                                   'line': node.lineno, 'kind': 'call-expression'})
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                    '/agent/' in node.value or 'context' in node.value or 'prompt_flow_panel' in node.value
                    or node.value in interface_names):
                references.append({'owner': owner, 'name': node.value[:250], 'file': file,
                                   'line': node.lineno, 'kind': 'protocol-or-route-literal'})
            for child in ast.iter_child_nodes(node):
                visit(child, owner)
        visit(tree)
    result = {'symbols': symbols, 'references': references, 'fileHashes': hashes,
              'scope': names, 'limitation': 'Dynamic attributes and string dispatch are explicit candidates, not runtime proof.'}
    (OUT / 'python-references.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'Python references: {len(symbols)} symbols; {len(references)} references', flush=True)


def tree_report():
    """Interactive per-symbol definition/caller/reference tree, preserving cycles."""
    js = json.loads((OUT / 'javascript-references.json').read_text(encoding='utf-8'))
    py = json.loads((OUT / 'python-references.json').read_text(encoding='utf-8'))
    payload = json.dumps({'js': js, 'py': py}).replace('<', '\\u003c')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Tlamatini menu reference tree</title>
<style>body{font:16px system-ui;background:#191a21;color:#ececf1;margin:30px}input{width:80%;padding:12px}details{margin:9px 0 9px 18px}summary{cursor:pointer}code{color:#8bded2}small{color:#bcbcca}li{margin:5px}</style>
<h1>Menu and panel reference tree</h1><p>Definitions → callers / reads / writes / calls, with file and line. Static references are not test results. Search any variable or function. Dynamic and ambiguous references remain labelled.</p>
<input id="filter" placeholder="Find a variable, function, file, menu, or spinner"><p id="counts"></p><main id="tree"></main>
<script id="data" type="application/json">PAYLOAD</script><script>
const data=JSON.parse(document.getElementById('data').textContent), rows=[];
const refs=new Map(); for(const r of data.js.references){if(!refs.has(r.to))refs.set(r.to,[]);refs.get(r.to).push(r)}
function item(s,list){const box=document.createElement('details'),title=document.createElement('summary');title.textContent=s.name+' — '+s.file+':'+s.line+' ('+s.kind+')';box.append(title);const ul=document.createElement('ul');for(const r of list){const li=document.createElement('li');li.textContent=(r.call?'CALL ':r.write?'WRITE ':r.kind||'READ ')+' '+r.file+':'+r.line+' ← '+(r.from||r.owner||r.name)+' '+(r.resolution||'');ul.append(li)}box.append(ul);rows.push({box,text:(title.textContent+' '+ul.textContent).toLowerCase()});document.getElementById('tree').append(box)}
for(const s of data.js.symbols)item(s,refs.get(s.id)||[]);
for(const s of data.js.functions)item(s,data.js.references.filter(r=>r.from===s.id));
const pyRefs=new Map();for(const r of data.py.references){if(!pyRefs.has(r.name))pyRefs.set(r.name,[]);pyRefs.get(r.name).push({...r,resolution:'Python name candidate; verify scope at the displayed location'})}
for(const s of data.py.symbols)item(s,pyRefs.get(s.name)||[]);
for(const s of data.js.interfaceReferences||[])item(s,[s,...(data.py.references.filter(r=>r.kind==='protocol-or-route-literal'&&r.name===s.name).map(r=>({...r,resolution:'Cross-language literal candidate'})))]);
document.getElementById('counts').textContent=rows.length+' symbol/function entries. JavaScript globals with multiple candidates are marked ambiguous.';
document.getElementById('filter').oninput=e=>{const q=e.target.value.toLowerCase();for(const row of rows)row.box.hidden=!row.text.includes(q)};
</script></html>'''.replace('PAYLOAD', payload)
    (OUT / 'reference-tree.html').write_text(page, encoding='utf-8')


def shoter(name):
    """Run the real Shoter with inherited visible console output, all screens."""
    destination = OUT / 'shoter-runtime'
    if not destination.exists():
        shutil.copytree(ROOT / 'Tlamatini/agent/agents/shoter', destination,
                        ignore=shutil.ignore_patterns('__pycache__', '*.log', '*.pid'))
    (destination / 'config.yaml').write_text(
        f'output_dir: {OUT.as_posix()}\nfilename: {name}\nall_screens: true\ntarget_agents: []\n', encoding='utf-8')
    subprocess.run([sys.executable, '-u', str(destination / 'shoter.py')], cwd=destination,
                   check=True, timeout=60)
    if not (OUT / name).is_file():
        raise RuntimeError('Shoter produced no desktop evidence: ' + name)


def inclusion_checks():
    """Run the requested shipping skills in the same verified visible console."""
    commands = {
        'self_update': [sys.executable, '-u', '.claude/skills/tlamatini-self-update-inclusion/scripts/sweep_self_update.py'],
        'self_modify': [sys.executable, '-u', '.claude/skills/tlamatini-self-modify-inclusion/scripts/sweep_self_modify.py', '--keep'],
        'python_lint': [sys.executable, '-m', 'ruff', 'check',
                        'scripts/run_menu_state_checks.py', 'scripts/menu_browser_checks.py',
                        'Tlamatini/agent/test_prompt_flow_panel_websocket.py',
                        'Tlamatini/agent/test_frontend_mutable_state.py',
                        'Tlamatini/agent/test_prompt_flow_panel.py',
                        'Tlamatini/agent/test_prompt_flow_panel_runtime.py',
                        'Tlamatini/agent/test_prompt_flow_panel_carriage.py',
                        'Tlamatini/agent/prompt_flow_panel_consumer.py',
                        'Tlamatini/agent/prompt_flow_panel_runtime.py',
                        'Tlamatini/agent/services/prompt_flow_panel.py',
                        'Tlamatini/agent/management/commands/check_prompt_flow_panel.py',
                        'build.py', 'build_runtime_assets.py', 'copy_source_assets.py'],
        'diff_check': ['git', 'diff', '--check'],
    }
    results = {}
    for name, command in commands.items():
        print('INCLUSION CHECK:', name, flush=True)
        results[name] = subprocess.run(command, cwd=ROOT).returncode
        print(name, 'EXIT CODE:', results[name], flush=True)
    subprocess.run(['git', 'status', '--short'], cwd=ROOT, check=True)
    (OUT / 'inclusion-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    return results


def main():
    if '--headless' in sys.argv:
        raise SystemExit('HEADLESS IS FORBIDDEN. Use the visible console launcher.')
    OUT.mkdir(parents=True, exist_ok=True)
    print('MENU SUITE: actual source templates and JS; deterministic WebSocket/HTTP fixtures.', flush=True)
    print('NO live model, production database, updater, native picker or external tool calls.', flush=True)
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node is required for scope-aware reference extraction and JavaScript lint.')
    subprocess.run([node, str(ROOT / 'scripts/menu_reference_graph.mjs'), str(OUT / 'javascript-references.json')],
                   cwd=ROOT, check=True)
    python_references()
    tree_report()

    sys.path.insert(0, str(ROOT / 'Tlamatini'))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tlamatini.settings'
    project_settings = importlib.import_module('tlamatini.settings')
    project_settings.DATABASES['default']['NAME'] = OUT / 'isolated-checks.sqlite3'
    import django
    django.setup()
    from django.core.management import call_command
    from django.http import HttpRequest
    from django.template.loader import render_to_string
    from django.conf import settings

    print('Collecting static assets for the source/collected parity run.', flush=True)
    call_command('collectstatic', interactive=False, verbosity=1)
    call_command('check_prompt_flow_panel')
    unit_names = ['agent.test_context_restore_spinner', 'agent.test_frontend_mutable_state.FrontendMutableStateTests',
                  'agent.test_dialog_dismissal_policy', 'agent.test_prompt_flow_panel',
                  'agent.test_prompt_flow_panel_runtime', 'agent.test_prompt_flow_panel_carriage',
                  'agent.test_chain_readiness', 'agent.test_prompt_flow_panel_websocket']
    unit_result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(unittest.TestLoader().loadTestsFromNames(unit_names))
    lint = subprocess.run([node, str(ROOT / 'node_modules/eslint/bin/eslint.js'),
                           '--quiet', 'Tlamatini/agent/static/agent/js/'], cwd=ROOT).returncode
    print('JavaScript lint exit:', lint, flush=True)
    inclusion = inclusion_checks()

    request = HttpRequest()
    request.user = SimpleNamespace(pk=1, username='menu-fixture', is_authenticated=True, is_staff=False)
    request.session = {}
    context = {'initial_messages': [], 'ollama_base_url': 'http://tlamatini.test/fixture-model',
               'version': 'source-under-test', 'STATIC_VERSION': settings.STATIC_VERSION}
    html = render_to_string('agent/agent_page.html', context, request=request)
    panel_html = render_to_string('agent/prompt_flow_panel.html', context, request=request)
    from playwright.sync_api import sync_playwright
    from menu_browser_checks import MenuBrowserChecks
    results = []
    gate = OUT / 'browser-visible-confirmed'
    gate.unlink(missing_ok=True)
    # Django installs a Selector policy; Playwright's subprocess needs Proactor.
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=False,
                                             args=['--start-maximized'])
        holding = browser.new_page()
        holding.set_content('<h1>Tlamatini: deep menu tests</h1><p>Waiting for verification of this visible Chrome window. No browser test has started.</p>')
        holding.bring_to_front()
        holding.wait_for_timeout(1000)
        shoter('browser-waiting.png')
        print('BROWSER WAITING: inspect Temp/menu-state-tests/browser-waiting.png; then create browser-visible-confirmed.', flush=True)
        while not gate.exists():
            holding.wait_for_timeout(500)
        MenuBrowserChecks.browser = browser
        MenuBrowserChecks.html = html
        MenuBrowserChecks.panel_html = panel_html
        MenuBrowserChecks.artifacts = OUT
        MenuBrowserChecks.capture = staticmethod(shoter)
        for mode, asset_root in (('source', ROOT / 'Tlamatini/agent/static'),
                                 ('collected', Path(settings.STATIC_ROOT))):
            print(f'BROWSER MODE: {mode}; assets: {asset_root}', flush=True)
            MenuBrowserChecks.mode = mode
            MenuBrowserChecks.asset_root = asset_root
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, resultclass=LiveResult).run(unittest.TestLoader().loadTestsFromTestCase(MenuBrowserChecks))
            results.append({'mode': mode, 'run': result.testsRun, 'failures': len(result.failures),
                            'errors': len(result.errors), 'skipped': len(result.skipped)})
        (OUT / 'javascript-coverage.json').write_text(json.dumps(MenuBrowserChecks.coverage), encoding='utf-8')
        coverage_report(MenuBrowserChecks.coverage)
        (OUT / 'state-snapshots.json').write_text(json.dumps(MenuBrowserChecks.snapshots, indent=2), encoding='utf-8')
        success = (unit_result.wasSuccessful() and lint == 0 and not any(inclusion.values())
                   and all(not r['failures'] and not r['errors'] for r in results))
        summary = {'timestamp': datetime.now(timezone.utc).isoformat(), 'success': success,
                   'python_tests': unit_result.testsRun, 'python_failures': len(unit_result.failures),
                   'python_errors': len(unit_result.errors), 'python_skipped': len(unit_result.skipped),
                   'javascript_lint_exit': lint, 'browser': results,
                   'inclusion': inclusion,
                   'real_frozen_executable_tested': False, 'live_model_tested': False,
                   'transport': 'deterministic fixture', 'source_root': str(ROOT)}
        (OUT / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary, indent=2), flush=True)
        holding.bring_to_front()
        holding.goto((OUT / 'reference-tree.html').as_uri())
        shoter('reference-tree-desktop.png')
        print('RESULTS SAVED. Browser remains open for 60 seconds; console stays open afterward.', flush=True)
        holding.wait_for_timeout(60_000)
        browser.close()
    return 0 if success else 1


if __name__ == '__main__':
    # Normal execution always exercises the actual served app and normal login.
    # The deterministic suite remains an explicitly named supplemental option.
    if '--transport-fixtures' in sys.argv:
        raise SystemExit(main())
    from menu_live_checks import main as live_main
    raise SystemExit(live_main())
